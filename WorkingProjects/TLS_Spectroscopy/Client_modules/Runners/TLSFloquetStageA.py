"""Calibrate a repeated 30-MHz flux waveform near q3's 3.992-GHz loss line.

This is a calibration-only gate for a later Floquet loss experiment. It does
not infer TLS control from carrier suppression alone. A fresh wide scout must
find the anchored loss and its clean 4.006-GHz flank; a weak qubit probe then
measures carrier and sideband spectra and checks that a repeating flux block
still produces sidebands when the probe is delayed to the fourth block.
"""

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import uuid

import numpy as np
from scipy.integrate import trapezoid
from scipy.special import jv

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.PulseFunctions import (
    ff_maxv,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSFluxModulationCalibration as calibration,
    TLSPumpProbeLocalizer as localizer,
    TLSPumpProbeProtocolCheck as protocol,
    TLSPumpProbeResidentDrive as resident,
    TLSPumpProbeWidePassiveScan as wide,
    TLSSwapHoldPilot as swap,
)


ANCHOR_GHZ = 3.992
MODULATION_MHZ = 30.0
AMPLITUDES_DAC = (0, 600, 900, 1200, 1400, 1600, 2000)
PROBE_GAIN_DAC = 3000
SHOTS = 500
CHECK_SHOTS = 1200
REFERENCE_SHOTS = 400
WINDOW_OFFSETS_MHZ = tuple(range(-10, 11, 2))
ORDERS = (-2, -1, 0, 1)
PERIODIC_BLOCKS = 4
J0_ZERO = 2.4048255577


def plan(*, periodic_check_only=False):
    if periodic_check_only:
        return {"hardware_access": False, "stage": "periodic_hardware_check",
                "purpose": "verify sustained 30-MHz flux waveform before loss science",
                "anchor_ghz": ANCHOR_GHZ,
                "calibration_site": "qualified +14-MHz quiet flank",
                "modulation_mhz": 30.0056,
                "amplitudes_dac": [0, 1400],
                "probe_gain_dac": 6000,
                "sideband_pilot_shots": 4000,
                "periodic_check_shots": 6000,
                "sideband_orders": [-1, 1],
                "sideband_offsets_mhz": list(range(-6, 7, 2)),
                "periodic_check": "early-versus-late first-sideband response",
                "periodic_blocks": PERIODIC_BLOCKS,
                "full_corrected_return_us": 40.0,
                "raw_iq_saved": True,
                "next_stage": "no loss run until periodic output is demonstrated"}
    return {"hardware_access": False, "stage": "calibration_only",
            "purpose": "measure modulation index and verify repeated flux waveform",
            "anchor_ghz": ANCHOR_GHZ,
            "calibration_site": "qualified +14-MHz quiet flank",
            "modulation_mhz": 30.0056,
            "amplitudes_dac": list(AMPLITUDES_DAC),
            "probe_gain_dac": PROBE_GAIN_DAC,
            "weak_carrier_excess_gate": [0.05, 0.20],
            "spectrum_orders": list(ORDERS),
            "window_offsets_mhz": list(WINDOW_OFFSETS_MHZ),
            "periodic_check": "early-versus-late first-sideband response",
            "periodic_blocks": PERIODIC_BLOCKS,
            "full_corrected_return_us": 40.0,
            "raw_iq_saved": True,
            "next_stage": "no loss run until beta, mean shift, and periodic output are reviewed"}


def fit_modulation_index(areas):
    """Fit one common scale to the four weak-probe Bessel sideband areas."""
    orders = np.asarray(ORDERS, dtype=int)
    observed = np.asarray([float(areas[int(n)]) for n in orders], dtype=float)
    if not np.all(np.isfinite(observed)) or max(observed) <= 0:
        raise ValueError("sideband areas must contain a positive finite signal")
    betas = np.linspace(0.0, 4.5, 4501)
    weights = jv(np.abs(orders)[None, :], betas[:, None]) ** 2
    scales = np.maximum((weights @ observed) /
                        np.sum(weights * weights, axis=1), 0.0)
    residuals = np.linalg.norm(weights * scales[:, None] - observed, axis=1)
    index = int(np.argmin(residuals))
    norm = max(float(np.linalg.norm(observed)), 1e-9)
    return {"beta": float(betas[index]), "probe_scale": float(scales[index]),
            "relative_residual": float(residuals[index] / norm),
            "areas": {str(n): float(areas[int(n)]) for n in ORDERS}}


def estimate_zero_dac(beta_by_amplitude):
    """Interpolate the first measured crossing of the J0 zero."""
    ordered = sorted((int(a), float(beta))
                     for a, beta in beta_by_amplitude.items())
    if not ordered or any(not math.isfinite(beta) for _, beta in ordered):
        raise ValueError("measured beta values must be finite")
    for (a0, b0), (a1, b1) in zip(ordered, ordered[1:]):
        if b0 <= J0_ZERO <= b1 and b1 > b0:
            return float(a0 + (J0_ZERO - b0) * (a1 - a0) / (b1 - b0))
    raise ValueError("measured amplitudes do not bracket the J0 zero")


def estimate_mean_shift_mhz(peaks, *, carrier_mhz):
    """Estimate the common carrier translation from resolved sideband peaks."""
    shifts, strengths = [], []
    for order in ORDERS:
        peak = peaks[str(order)]
        excess = float(peak["excess"])
        if peak["interior"] and excess >= .03:
            shifts.append(float(peak["frequency_mhz"]) -
                          float(carrier_mhz) - order * MODULATION_MHZ)
            strengths.append(excess)
    if not shifts:
        raise ValueError("no resolved peak for mean-shift estimate")
    return float(np.average(shifts, weights=strengths))


def validate_periodic_baseline(segments, *, park_gain, target_gain,
                               max_spread_dac=20):
    levels = [float(park_gain) + float(level) *
              (float(target_gain) - float(park_gain))
              for level, duration in segments if float(duration) > 0]
    if (not levels or not all(math.isfinite(value) for value in levels) or
            max(levels) - min(levels) > float(max_spread_dac)):
        raise ValueError("periodic DC correction spread exceeds 20 DAC")
    return levels[0]


def validate_block_report(report):
    if (int(report["cycles_per_waveform"]) != 24 or
            abs(float(report["duration_us"]) - .8) > .002 or
            abs(float(report["actual_modulation_mhz"]) - 30.0) > .1):
        raise ValueError("periodic check requires the verified 24-cycle, 0.8-us block")


def probe_arm(name, flank, frequency_mhz, amplitude_dac, *, shots=SHOTS,
              periodic_position=None, probe_gain_dac=PROBE_GAIN_DAC):
    if amplitude_dac not in AMPLITUDES_DAC:
        raise ValueError("undeclared modulation amplitude")
    return {"name": name, "flux_ghz": float(flank),
            "drive_mhz": float(frequency_mhz), "gain": int(probe_gain_dac),
            "reference_state": None, "preparation_state": "g",
            "pre_drive_us": calibration.SETTLE_US,
            "post_drive_us": calibration.POST_US,
            "shots": int(shots),
            "modulation_amplitude_dac": int(amplitude_dac),
            "periodic_position": periodic_position,
            "status": "pending"}


class FloquetProbeProgram(calibration.ModulatedResidentProgram):
    """Weak resident spectroscopy with optional four-block periodic AC."""

    def __init__(self, soccfg, cfg, payload_calibration, loop_calibration):
        if int(cfg.get("opx_modulation_amplitude_dac", -1)) not in AMPLITUDES_DAC:
            raise ValueError("undeclared modulation amplitude")
        if cfg.get("opx_floquet_periodic_position") not in (None, "early", "late"):
            raise ValueError("periodic probe position must be early or late")
        if (cfg.get("opx_floquet_periodic_position") is not None and
                int(cfg["opx_modulation_amplitude_dac"]) == 0):
            raise ValueError("periodic check needs nonzero AC amplitude")
        resident.ResidentDriveProgram.__init__(
            self, soccfg, cfg, payload_calibration, loop_calibration)

    def _resident_excursion(self):
        cfg = self.cfg
        position = cfg.get("opx_floquet_periodic_position")
        if position is None:
            return super()._resident_excursion()
        if self._t1_ff_compensation is None:
            raise ValueError("periodic check requires the pinned flux correction")
        block_us = float(self.modulation_waveform_report["duration_us"])
        window_us = PERIODIC_BLOCKS * block_us
        pre_us = float(cfg["opx_resident_pre_us"]) + self._t1_ff_settle_us
        target_segments, recovery = ff_pulse.compensation_round_trip_segments(
            self._t1_ff_compensation,
            pre_us + window_us + float(cfg["opx_resident_post_us"]),
            recovery_us=self._t1_ff_predistortion_recovery_us)
        before, rest = ff_pulse.split_compensation_segments(
            target_segments, pre_us)
        during, after = ff_pulse.split_compensation_segments(rest, window_us)
        if not before or not during or not after or not recovery:
            raise ValueError("periodic target and return segments are incomplete")
        baseline = validate_periodic_baseline(
            [(before[-1][0], .001), *during, (after[0][0], .001)],
            park_gain=cfg["ff_park_gain"], target_gain=cfg["ff_gain"])
        if abs(baseline - float(self.modulation_waveform_report["baseline_gain"])) > 1.0:
            raise ValueError("periodic block baseline differs from target DC")
        if sum(duration for _, duration in recovery) < 40.0 - 1e-6:
            raise ValueError("periodic check requires full corrected return")
        park = float(cfg["ff_park_gain"])
        target = float(cfg["ff_gain"])
        ff_pulse.play_relative_compensation_segments(self, park, target, before)
        self.sync_all(0)
        self.set_pulse_registers(
            ch=cfg["ff_ch"], freq=0, style="arb", phase=0,
            stdysel="last", mode="periodic", gain=ff_maxv(self),
            waveform="q3_flux_ac", outsel="input")
        self.set_pulse_registers(
            ch=cfg["qubit_ch"], style="arb",
            freq=self.freq2reg(float(cfg["opx_resident_freq_mhz"]),
                               gen_ch=cfg["qubit_ch"]),
            phase=self.deg2reg(0.0, gen_ch=cfg["qubit_ch"]),
            gain=int(cfg["opx_resident_gain"]), waveform="qubit")
        self.pulse(ch=cfg["ff_ch"])
        if position == "late":
            self.sync_all(self.us2cycles(2.0 * block_us))
        self.pulse(ch=cfg["qubit_ch"])
        self.sync_all(self.us2cycles(3.0 * block_us) if position == "early" else 0)
        # A new constant pulse on this generator explicitly ends periodic AC.
        ff_pulse.play_relative_compensation_segments(self, park, target, after)
        ff_pulse.play_relative_compensation_segments(self, park, target, recovery)
        ff_pulse.play_hard_step(self, park)
        self.sync_all(0)


def spectrum_arms(flank, carrier_mhz):
    arms = []
    for order in ORDERS:
        for offset in WINDOW_OFFSETS_MHZ:
            frequency = round(carrier_mhz + order * MODULATION_MHZ + offset, 3)
            levels = AMPLITUDES_DAC if (order + offset // 2) % 2 == 0 else tuple(reversed(AMPLITUDES_DAC))
            for amplitude in levels:
                arm = probe_arm(f"a{amplitude}_n{order:+d}_o{offset:+d}",
                                flank, frequency, amplitude)
                arm.update(order=order, offset_mhz=offset)
                arms.append(arm)
    return arms


def periodic_scan_arms(flank, carrier_mhz):
    arms = []
    for order in (-1, 1):
        for offset in range(-6, 7, 2):
            frequency = round(carrier_mhz + order * MODULATION_MHZ + offset, 3)
            for amplitude in (0, 1400):
                arm = probe_arm(f"pilot_n{order:+d}_o{offset:+d}_a{amplitude}",
                                flank, frequency, amplitude, shots=4000,
                                probe_gain_dac=6000)
                arm.update(order=order, offset_mhz=offset)
                arms.append(arm)
    return arms


def _fraction_se(on, off, on_shots, off_shots):
    return math.sqrt(on * (1.0 - on) / on_shots +
                     off * (1.0 - off) / off_shots)


def periodic_carrier_valid(fractions, *, ground_fraction, shots):
    """Require a centered carrier distinguished from the measured off-resonant floor."""
    values = np.asarray(fractions, dtype=float)
    if len(values) < 7 or not np.all(np.isfinite(values)):
        return False
    index = int(np.argmax(values))
    if index in (0, len(values) - 1):
        return False
    peak = float(values[index])
    floor = float(np.mean(np.r_[values[:3], values[-3:]]))
    se = _fraction_se(peak, floor, shots, 6 * shots)
    return bool(.06 <= peak - ground_fraction <= .45 and
                peak - floor >= max(.06, 4.0 * se))


def select_periodic_sideband(arms):
    by_point = {(arm["order"], arm["offset_mhz"],
                 arm["modulation_amplitude_dac"]): arm for arm in arms}
    candidates = []
    for order in (-1, 1):
        for offset in range(-4, 5, 2):
            on = by_point[(order, offset, 1400)]
            off = by_point[(order, offset, 0)]
            candidates.append({"order": order,
                               "frequency_mhz": on["drive_mhz"],
                               "on_off_excess": (
                                   on["excited_fraction_pre_axis"] -
                                   off["excited_fraction_pre_axis"]),
                               "standard_error": _fraction_se(
                                   on["excited_fraction_pre_axis"],
                                   off["excited_fraction_pre_axis"],
                                   on["shots"], off["shots"])})
    best = max(candidates, key=lambda item: item["on_off_excess"])
    if best["on_off_excess"] < max(.025, 3.0 * best["standard_error"]):
        raise ValueError("no resolved first sideband for periodic check")
    return {key: value for key, value in best.items() if key != "standard_error"}


def periodic_response_valid(fractions, *, shots=2000):
    off = float(fractions["off"])
    oneshot = float(fractions["oneshot"])
    early = float(fractions["early"])
    late = float(fractions["late"])
    return bool(all(value - off >= max(.02, 3.0 * _fraction_se(
                    value, off, shots, shots))
                    for value in (oneshot, early, late)) and
                abs(early - oneshot) <= .06 and
                abs(late - early) <= .06)


def summarize_spectra(arms, ground_fraction):
    fits = {}
    for amplitude in AMPLITUDES_DAC:
        areas = {}
        peaks = {}
        for order in ORDERS:
            group = sorted((arm for arm in arms if arm["modulation_amplitude_dac"] == amplitude
                            and arm["order"] == order), key=lambda arm: arm["offset_mhz"])
            if len(group) != len(WINDOW_OFFSETS_MHZ):
                raise ValueError("incomplete sideband frequency window")
            excess = np.asarray([arm["excited_fraction_pre_axis"] - ground_fraction
                                 for arm in group], dtype=float)
            areas[order] = float(trapezoid(excess, dx=2.0))
            best = int(np.argmax(excess))
            peaks[order] = {"frequency_mhz": group[best]["drive_mhz"],
                            "offset_mhz": group[best]["offset_mhz"],
                            "excess": float(excess[best]),
                            "interior": 0 < best < len(group)-1}
        fits[str(amplitude)] = {**fit_modulation_index(areas),
                                "peaks": {str(n): peaks[n] for n in ORDERS}}
    return fits


def _program_config(base, arm, dc_lookup):
    cfg = calibration._program_config(base, arm, dc_lookup)
    cfg["opx_floquet_periodic_position"] = arm.get("periodic_position")
    return cfg


def run(*, data_root=localizer.DATA_ROOT, correction_json=None,
        periodic_check_only=False):
    data_root = Path(data_root)
    correction = localizer.checked_correction(data_root, correction_json)
    scout = localizer.run(
        data_root=data_root, correction_json=correction,
        parameter_overrides={**wide.parameters(),
                             "output_suffix": (
                                 "TLS_Floquet_Periodic_Check_Scout_pre"
                                 if periodic_check_only else
                                 "TLS_Floquet_StageA_Scout_pre")})
    selected = swap.select_wide_candidate(
        swap.read_wide_scout(scout), preferred_center=ANCHOR_GHZ)
    center, flank = selected["center_ghz"], selected["control_ghz"]
    if selected["control_offset_ghz"] != .014:
        raise RuntimeError("Floquet calibration requires the clean upper flank")
    print(f"[floquet-A] feature={center:.3f} GHz; quiet flank={flank:.3f} GHz",
          flush=True)

    with localizer.scan_environment(correction):
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
            FivePointApplesToApples as five, TLSSpectroscopy as tls,
        )
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.ThreePointApplesToApples import (
            _integer_dc_grid,
        )
        from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import (
            _block_timeout_s, _run_program, runtime_bundle,
        )
        from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import (
            ProductionResetSession,
        )

        if int(tls.BaseConfig["ff_park_gain"]) != -25146:
            raise RuntimeError("q3 park gain differs from verified configuration")
        tls.QUBIT, tls.SET_YOKO, tls.outerFolder = "q3", False, str(data_root)
        five.install_scan_calibration(tls)
        dc, realized = _integer_dc_grid(wide.parameters(), np.asarray([flank]), tls)
        dc_lookup = {flank: int(dc[0])}
        compensation = tls._load_correction(str(correction), str(data_root))
        base = ProductionResetSession.passive().apply(tls.BaseConfig)
        five.apply_verified_feedback_timing(base)
        base.update({"apply_flux_tail_compensation": True,
                     "flux_tail_compensation": compensation,
                     "flux_fit_params": tls.FLUX_FIT_PARAMS,
                     "flux_settle_time_us": .5,
                     "flux_predistortion_return_prefix_us": .5,
                     "flux_predistortion_recovery_us": 40.0,
                     "flux_predistortion_overlap_payload_readout": False,
                     "flux_predistortion_round_trip_mode": "stateful",
                     "readout_thermalization_us": 10.0,
                     "qubit_pulse_style": "arb", "do_ff": True,
                     "opx_reset_scheme": "none",
                     "opx_resident_dmem_stream": True,
                     "opx_inter_shot_delay_us": 500.0})
        session_id = (("q3_floquet_periodic_check_"
                       if periodic_check_only else "q3_floquet_stage_a_") +
                      datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") +
                      "_" + uuid.uuid4().hex[:8])
        folder = data_root / "q3" / session_id
        folder.mkdir(parents=True, exist_ok=False)
        path = folder / "manifest.json"
        refs = [calibration._reference(f"ref_{state}_{phase}", state, flank)
                for phase in ("pre", "post") for state in ("g", "e")]
        for ref in refs:
            ref["shots"] = REFERENCE_SHOTS
        probe_gain = 6000 if periodic_check_only else PROBE_GAIN_DAC
        carrier = [probe_arm(f"carrier_{i:02d}", flank, f, 0,
                             probe_gain_dac=probe_gain)
                   for i, f in enumerate(calibration.carrier_grid(1000.0 * flank + 5.0))]
        manifest = {"schema": ("q3.floquet-periodic-check.v1"
                               if periodic_check_only else
                               "q3.floquet-stage-a.v1"), "status": "running",
                    "session_id": session_id,
                    "code_commit": os.environ.get("Q3_CODE_COMMIT", "unknown"),
                    "correction_json": str(correction),
                    "correction_sha256": localizer.CORRECTION_SHA256,
                    "scout_csv": str(scout), "selected": selected,
                    "flank_ghz": flank, "dc_gain": int(dc[0]),
                    "realized_ghz": float(realized[0]),
                    "plan": plan(periodic_check_only=periodic_check_only),
                    "references": refs,
                    "carrier_arms": carrier, "spectrum_arms": [],
                    "periodic_check_arms": []}
        protocol.checkpoint(path, manifest)
        print(f"[floquet-A] manifest={path}", flush=True)
        raw_refs = {}
        axis = None
        try:
            soc, soccfg = tls.makeProxy()
            bundle = runtime_bundle(base)

            def compile_arm(arm):
                cfg = _program_config(base, arm, dc_lookup)
                return cfg, FloquetProbeProgram(
                    soccfg, cfg, bundle.payload, bundle.loop)

            for arm in (refs[0], carrier[len(carrier)//2],
                        probe_arm("preflight_max", flank, flank*1000+5,
                                  1400 if periodic_check_only else 2000,
                                  probe_gain_dac=probe_gain),
                        probe_arm("preflight_periodic", flank, flank*1000+35,
                                  1400 if periodic_check_only else 1600,
                                  periodic_position="late",
                                  probe_gain_dac=probe_gain)):
                _, program = compile_arm(arm)
                if arm["name"] == "preflight_max":
                    report = program.modulation_waveform_report
                    validate_block_report(report)
                    manifest["waveform_report"] = report
                    wave_path = folder / "compiled_flux_waveform.npz"
                    np.savez_compressed(wave_path,
                                        idata=program.modulation_waveform)
                    manifest["waveform_npz"] = str(wave_path)
            manifest["preflight_complete"] = True
            protocol.checkpoint(path, manifest)

            def acquire(arm):
                arm["status"] = "acquiring"
                protocol.checkpoint(path, manifest)
                cfg, program = compile_arm(arm)
                shots = int(arm["shots"])
                records = _run_program(
                    soc, program, max(30.0, _block_timeout_s(cfg, shots)),
                    cfg, total_shots=shots)
                if len(records) != shots:
                    raise RuntimeError(f"{arm['name']}: incomplete IQ records")
                calibration._save_records(folder, arm, records, axis)
                arm["status"] = "complete"
                protocol.checkpoint(path, manifest)
                return records

            for ref in refs[:2]:
                raw_refs[ref["name"]] = acquire(ref)
            axis = resident.fit_axis(
                resident.record_iq(raw_refs["ref_g_pre"]),
                resident.record_iq(raw_refs["ref_e_pre"]))
            manifest["pre_readout_axis"] = axis
            if not axis["valid"]:
                raise RuntimeError("pre-run readout reference invalid")
            protocol.checkpoint(path, manifest)
            for arm in carrier:
                acquire(arm)
            ground = resident.classify(raw_refs["ref_g_pre"], axis)
            best = max(carrier, key=lambda arm: arm["excited_fraction_pre_axis"])
            carrier_excess = best["excited_fraction_pre_axis"] - ground
            manifest["carrier_center_mhz"] = best["drive_mhz"]
            manifest["carrier_excess"] = carrier_excess
            protocol.checkpoint(path, manifest)
            carrier_valid = (periodic_carrier_valid(
                [arm["excited_fraction_pre_axis"] for arm in carrier],
                ground_fraction=ground, shots=carrier[0]["shots"])
                if periodic_check_only else
                best is not carrier[0] and best is not carrier[-1] and
                .05 <= carrier_excess <= .20)
            if not carrier_valid:
                raise RuntimeError("probe carrier outside bracket or contrast gate")
            print(f"[floquet-A] carrier={best['drive_mhz']:.1f} MHz; "
                  f"excess={carrier_excess:.3f}", flush=True)

            if periodic_check_only:
                arms = periodic_scan_arms(flank, best["drive_mhz"])
                manifest["spectrum_arms"] = arms
                protocol.checkpoint(path, manifest)
                for index, arm in enumerate(arms, 1):
                    acquire(arm)
                    if index % 4 == 0:
                        print(f"[floquet-A] sideband pilot {index}/{len(arms)}",
                              flush=True)
                chosen = select_periodic_sideband(arms)
                manifest["selected_sideband"] = chosen
                check_amplitude = 1400
                check_arms = [probe_arm("periodic_off", flank,
                                        chosen["frequency_mhz"], 0,
                                        shots=6000, probe_gain_dac=probe_gain)]
                for position in (None, "early", "late"):
                    check_arms.append(probe_arm(
                        f"periodic_{position or 'oneshot'}", flank,
                        chosen["frequency_mhz"], check_amplitude,
                        shots=6000, periodic_position=position,
                        probe_gain_dac=probe_gain))
            else:
                arms = spectrum_arms(flank, best["drive_mhz"])
                manifest["spectrum_arms"] = arms
                protocol.checkpoint(path, manifest)
                for index, arm in enumerate(arms, 1):
                    acquire(arm)
                    if index % len(AMPLITUDES_DAC) == 0:
                        print(f"[floquet-A] spectrum {index}/{len(arms)}", flush=True)
                fits = summarize_spectra(arms, ground)
                for item in fits.values():
                    try:
                        item["measured_mean_shift_mhz"] = estimate_mean_shift_mhz(
                            item["peaks"], carrier_mhz=best["drive_mhz"])
                    except ValueError as exc:
                        item["mean_shift_error"] = str(exc)
                manifest["sideband_fits"] = fits
                beta_by_a = {int(a): item["beta"] for a, item in fits.items()}
                try:
                    manifest["estimated_j0_zero_dac"] = estimate_zero_dac(beta_by_a)
                except ValueError as exc:
                    manifest["zero_estimate_error"] = str(exc)
                protocol.checkpoint(path, manifest)
                check_amplitude = min(AMPLITUDES_DAC[1:],
                                      key=lambda a: abs(beta_by_a[a] - J0_ZERO))
                check_arms = []
                for order in (-1, 1):
                    peak = fits[str(check_amplitude)]["peaks"][str(order)]
                    frequency = peak["frequency_mhz"]
                    for position in (None, "early", "late"):
                        label = position or "oneshot"
                        arm = probe_arm(f"periodic_n{order:+d}_{label}", flank,
                                        frequency, check_amplitude,
                                        shots=CHECK_SHOTS,
                                        periodic_position=position)
                        arm["order"] = order
                        check_arms.append(arm)
            manifest["periodic_check_amplitude_dac"] = check_amplitude
            manifest["periodic_check_arms"] = check_arms
            protocol.checkpoint(path, manifest)
            for arm in check_arms:
                acquire(arm)
            if periodic_check_only:
                check_scores = {arm["periodic_position"] or "oneshot":
                                arm["excited_fraction_pre_axis"]
                                for arm in check_arms[1:]}
                check_scores["off"] = check_arms[0]["excited_fraction_pre_axis"]
            else:
                check_scores = {}
                for order in (-1, 1):
                    group = {arm["periodic_position"] or "oneshot":
                             arm["excited_fraction_pre_axis"] - ground
                             for arm in check_arms if arm["order"] == order}
                    check_scores[str(order)] = group
            manifest["periodic_check_excess"] = check_scores

            repeated = probe_arm("carrier_repeat", flank,
                                 best["drive_mhz"], 0,
                                 probe_gain_dac=probe_gain)
            manifest["carrier_repeat"] = repeated
            acquire(repeated)
            for ref in refs[2:]:
                raw_refs[ref["name"]] = acquire(ref)
            manifest["post_readout_score"] = resident.score_axis(
                axis, resident.record_iq(raw_refs["ref_g_post"]),
                resident.record_iq(raw_refs["ref_e_post"]))
            manifest["carrier_repeat_excess"] = (
                repeated["excited_fraction_pre_axis"] -
                resident.classify(raw_refs["ref_g_post"], axis))
            post_scout = localizer.run(
                data_root=data_root, correction_json=correction,
                parameter_overrides={**wide.parameters(),
                                     "output_suffix": (
                                         "TLS_Floquet_Periodic_Check_Scout_post"
                                         if periodic_check_only else
                                         "TLS_Floquet_StageA_Scout_post")})
            manifest["post_scout_csv"] = str(post_scout)
            try:
                post = swap.select_wide_candidate(
                    swap.read_wide_scout(post_scout),
                    preferred_center=center,
                    preferred_control_offset=selected["control_offset_ghz"])
                manifest["post_selected"] = post
            except ValueError as exc:
                manifest["post_selection_error"] = str(exc)
            manifest["feature_stable"] = (
                swap.feature_stable(selected, manifest["post_selected"])
                if "post_selected" in manifest else False)
            periodic_valid = (periodic_response_valid(
                                  check_scores, shots=check_arms[0]["shots"])
                              if periodic_check_only else
                              all(score["oneshot"] >= .025 and
                                  score["early"] >= .025 and
                                  score["late"] >= .025 and
                                  abs(score["early"] - score["oneshot"]) <= .08 and
                                  abs(score["late"] - score["early"]) <= .08
                                  for score in check_scores.values()))
            manifest["periodic_check_valid"] = periodic_valid
            if periodic_check_only:
                fit_valid = True
            else:
                fit_valid = ("estimated_j0_zero_dac" in manifest and
                             all(item["relative_residual"] <= .35
                                 for item in fits.values()) and
                             all(fits[str(check_amplitude)]["peaks"][str(order)]["interior"]
                                 for order in (-1, 1)))
                manifest["bessel_fit_valid"] = fit_valid
            valid = (manifest["feature_stable"] and
                     manifest["post_readout_score"]["valid"] and
                     abs(manifest["carrier_repeat_excess"] - carrier_excess) <= .10 and
                     periodic_valid and fit_valid)
            manifest["status"] = "complete" if valid else "complete_controls_unstable"
            protocol.checkpoint(path, manifest)
            print(f"[floquet-A] {manifest['status']}: {path}", flush=True)
            return path
        except BaseException as exc:
            manifest["status"] = "failed"
            manifest["error"] = f"{type(exc).__name__}: {exc}"
            protocol.checkpoint(path, manifest)
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--data-root", type=Path, default=localizer.DATA_ROOT)
    parser.add_argument("--correction-json", type=Path)
    parser.add_argument("--periodic-check-only", action="store_true",
                        help="use a strong-probe sideband pilot to verify repeated waveform playback")
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(plan(periodic_check_only=args.periodic_check_only),
                         indent=2))
    else:
        run(data_root=args.data_root, correction_json=args.correction_json,
            periodic_check_only=args.periodic_check_only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
