"""Measure q3's qubit sidebands under fast-flux modulation.

This is a transfer pilot, not a modulated-T1 or TLS-saturation measurement.
A passive loss scout chooses a current feature; the original 30-MHz mode runs
at its 14-MHz lower flank. The existing target-resident Gaussian qubit pulse and
the AC flux waveform play simultaneously after the corrected target settle.
The --frequency-response mode uses a wide scout and 20/30/40-MHz waveforms
at a quiet site separated from the current loss feature. It saves sideband
spectra for an on-chip amplitude estimate; it does not itself test TLS loss.
Each readout follows the complete 40-us corrected return. Ground/excited
references, unmodulated spectra, a repeated carrier and pre/post scouts bound
readout and frequency drift. Raw IQ and the actual compiled waveform are saved.
"""

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import uuid

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.PulseFunctions import (
    ff_envelope_samples, ff_maxv,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSPumpProbeAdaptiveParkPump as adaptive,
    TLSPumpProbeLocalizer as localizer,
    TLSPumpProbeProtocolCheck as protocol,
    TLSPumpProbeResidentDrive as resident,
    TLSPumpProbeWidePassiveScan as wide,
    TLSFloquetSwitch as switch,
    TLSSwapHoldPilot as swap,
)
MODULATION_MHZ = 30.0
AMPLITUDES_DAC = (0, 800, 1600)
RESPONSE_FREQUENCIES_MHZ = (20.0, 30.0, 40.0)
RESPONSE_AMPLITUDES_DAC = (0, 800)
PROBE_GAIN_DAC = 6000
SHOTS = 600
REFERENCE_SHOTS = 400
SETTLE_US = 20.0
POST_US = 0.1


def modulation_waveform(*, sample_rate_mhz, fabric_rate_mhz, cycles,
                        baseline_gain, amplitude_gain, modulation_mhz,
                        max_gain):
    """Return a phase-continuous, zero-mean AC envelope on a DC target bias."""
    fs = float(sample_rate_mhz)
    fabric = float(fabric_rate_mhz)
    ratio = fs / fabric
    samples_per_clock = int(round(ratio))
    if not (math.isfinite(ratio) and samples_per_clock > 0 and
            abs(ratio - samples_per_clock) < 1e-6):
        raise ValueError("fast-flux generator samples per clock are not integral")
    cycles = int(cycles)
    duration_us = cycles / fabric
    requested_cycles = float(modulation_mhz) * duration_us
    sine_cycles = int(round(requested_cycles))
    if (cycles < 3 or sine_cycles < 1 or
            abs(requested_cycles - sine_cycles) > 0.1):
        raise ValueError("waveform must contain nearly integral AC cycles")
    baseline = float(baseline_gain)
    amplitude = float(amplitude_gain)
    max_gain = min(float(max_gain), 32767.0)
    if (not all(math.isfinite(x) for x in (fs, fabric, baseline, amplitude, max_gain))
            or fs <= 0 or fabric <= 0 or amplitude < 0 or
            abs(baseline) + amplitude > max_gain):
        raise ValueError("AC waveform exceeds the fast-flux DAC range")
    count = cycles * samples_per_clock
    phase = 2.0 * np.pi * sine_cycles * np.arange(count) / count
    samples = np.rint(baseline + amplitude * np.sin(phase)).astype(np.int16)
    return samples, {"sample_rate_mhz": fs, "fabric_rate_mhz": fabric,
                     "samples_per_clock": samples_per_clock,
                     "samples": count, "duration_us": duration_us,
                     "cycles_per_waveform": sine_cycles,
                     "requested_modulation_mhz": float(modulation_mhz),
                     "actual_modulation_mhz": sine_cycles / duration_us,
                     "baseline_gain": baseline, "amplitude_gain": amplitude,
                     "waveform_min": int(samples.min()),
                     "waveform_max": int(samples.max())}


def carrier_grid(nominal_mhz):
    return [round(float(nominal_mhz) + offset, 3)
            for offset in np.arange(-8.0, 8.1, 1.0)]


def sideband_grid(carrier_mhz, *, modulation_mhz=MODULATION_MHZ):
    return [round(float(carrier_mhz) + order * float(modulation_mhz) + offset, 3)
            for order in (-1, 0, 1) for offset in (-4.0, -2.0, 0.0, 2.0, 4.0)]


def plan(*, frequency_response=False):
    if frequency_response:
        return {"hardware_access": False, "stage": "calibration_only",
                "purpose": "measure on-chip fast-flux amplitude from qubit sidebands",
                "reset_mode": "passive", "scout_ghz": [3.8, 4.3],
                "site": "quiet flank 60-100 MHz from fresh loss",
                "modulation_frequencies_mhz": list(RESPONSE_FREQUENCIES_MHZ),
                "modulation_amplitudes_dac": list(RESPONSE_AMPLITUDES_DAC),
                "waveform_window_us": 0.8,
                "qubit_pulse_gain_dac": PROBE_GAIN_DAC,
                "qubit_pulse": "existing target-resident 4-sigma Gaussian",
                "carrier_scan_points": 17,
                "sideband_scan_points_per_frequency": 30,
                "shots_per_point": SHOTS, "raw_iq_saved": True,
                "full_return_before_readout_us": 40.0,
                "abort_if_carrier_excess_below": 0.08,
                "note": __doc__}
    return {"hardware_access": False,
            "purpose": "calibrate fast-flux transfer from qubit sidebands",
            "reset_mode": "passive", "site": "fresh loss feature minus 14 MHz",
            "modulation_frequency_mhz": MODULATION_MHZ,
            "modulation_amplitudes_dac": list(AMPLITUDES_DAC),
            "waveform_window_us": 0.8,
            "qubit_pulse_gain_dac": PROBE_GAIN_DAC,
            "qubit_pulse": "existing target-resident 4-sigma Gaussian",
            "carrier_scan_points": 17, "sideband_scan_points_per_amplitude": 15,
            "shots_per_point": SHOTS, "raw_iq_saved": True,
            "full_return_before_readout_us": 40.0,
            "abort_if_carrier_excess_below": 0.08,
            "note": __doc__}


class ModulatedResidentProgram(resident.ResidentDriveProgram):
    """One simultaneous flux-modulation and target-resident qubit pulse."""

    def __init__(self, soccfg, cfg, payload_calibration, loop_calibration):
        amplitude = int(cfg.get("opx_modulation_amplitude_dac", 0))
        if amplitude not in AMPLITUDES_DAC:
            raise ValueError("modulation amplitude is outside the predeclared pilot levels")
        super().__init__(soccfg, cfg, payload_calibration, loop_calibration)

    def _declare_experiment(self):
        super()._declare_experiment()
        cfg = self.cfg
        ff_ch = int(cfg["ff_ch"])
        generator = self.soccfg["gens"][ff_ch]
        cycles = int(self.us2cycles(4.0 * float(cfg["sigma"]), gen_ch=ff_ch))
        duration_us = cycles / float(generator["f_fabric"])
        before, _, _ = resident.resident_segments(
            self._t1_ff_compensation,
            pre_us=float(cfg["opx_resident_pre_us"]) + self._t1_ff_settle_us,
            pulse_us=duration_us + 0.01,
            post_us=float(cfg["opx_resident_post_us"]),
            recovery_us=self._t1_ff_predistortion_recovery_us)
        park = float(cfg["ff_park_gain"])
        target = float(cfg["ff_gain"])
        baseline = park + float(before[-1][0]) * (target - park)
        waveform, report = modulation_waveform(
            sample_rate_mhz=generator["fs"],
            fabric_rate_mhz=generator["f_fabric"], cycles=cycles,
            baseline_gain=baseline,
            amplitude_gain=cfg["opx_modulation_amplitude_dac"],
            modulation_mhz=cfg.get("opx_modulation_mhz", MODULATION_MHZ),
            max_gain=ff_maxv(self, scaled=True))
        if len(waveform) > ff_envelope_samples(self):
            raise ValueError("AC flux waveform exceeds this generator's envelope memory")
        self.add_pulse(ch=ff_ch, name="q3_flux_ac", idata=waveform,
                       qdata=np.zeros_like(waveform))
        self.modulation_waveform_report = report
        self.modulation_waveform = waveform

    def _resident_excursion(self):
        cfg = self.cfg
        if self._t1_ff_compensation is None:
            raise ValueError("AC flux pilot requires the pinned correction")
        park = float(cfg["ff_park_gain"])
        target = float(cfg["ff_gain"])
        duration_us = self.modulation_waveform_report["duration_us"]
        before, after, recovery = resident.resident_segments(
            self._t1_ff_compensation,
            pre_us=float(cfg["opx_resident_pre_us"]) + self._t1_ff_settle_us,
            pulse_us=duration_us + 0.01,
            post_us=float(cfg["opx_resident_post_us"]),
            recovery_us=self._t1_ff_predistortion_recovery_us)
        ff_pulse.play_relative_compensation_segments(self, park, target, before)
        self.sync_all(0)
        self.set_pulse_registers(
            ch=cfg["ff_ch"], freq=0, style="arb", phase=0,
            stdysel="last", gain=ff_maxv(self), waveform="q3_flux_ac",
            outsel="input")
        self.set_pulse_registers(
            ch=cfg["qubit_ch"], style="arb",
            freq=self.freq2reg(float(cfg["opx_resident_freq_mhz"]),
                               gen_ch=cfg["qubit_ch"]),
            phase=self.deg2reg(0.0, gen_ch=cfg["qubit_ch"]),
            gain=int(cfg["opx_resident_gain"]), waveform="qubit")
        # Distinct QICK generators schedule from the same channel-time origin.
        self.pulse(ch=cfg["ff_ch"])
        self.pulse(ch=cfg["qubit_ch"])
        self.sync_all(self.us2cycles(0.01))
        ff_pulse.play_relative_compensation_segments(self, park, target, after)
        ff_pulse.play_relative_compensation_segments(self, park, target, recovery)
        ff_pulse.play_hard_step(self, park)
        self.sync_all(0)


def _reference(name, state, flank):
    return {"name": name, "flux_ghz": flank, "drive_mhz": flank * 1000.0,
            "gain": 0, "reference_state": state, "preparation_state": "g",
            "pre_drive_us": SETTLE_US, "post_drive_us": POST_US,
            "shots": REFERENCE_SHOTS, "modulation_amplitude_dac": 0,
            "status": "pending"}


def _arm(name, flank, freq, amplitude, *, shots=SHOTS,
         modulation_mhz=MODULATION_MHZ, order=None, offset_mhz=None):
    result = {"name": name, "flux_ghz": flank, "drive_mhz": float(freq),
            "gain": PROBE_GAIN_DAC, "reference_state": None,
            "preparation_state": "g", "pre_drive_us": SETTLE_US,
            "post_drive_us": POST_US, "shots": int(shots),
            "modulation_amplitude_dac": int(amplitude),
            "modulation_mhz": float(modulation_mhz), "status": "pending"}
    if order is not None:
        result["order"] = int(order)
    if offset_mhz is not None:
        result["offset_mhz"] = float(offset_mhz)
    return result


def _program_config(base, arm, dc_lookup):
    cfg = resident.arm_config(base, arm, dc_lookup)
    cfg["opx_modulation_amplitude_dac"] = arm["modulation_amplitude_dac"]
    cfg["opx_modulation_mhz"] = arm.get("modulation_mhz", MODULATION_MHZ)
    return cfg


def frequency_response_arms(site_ghz, carrier_mhz):
    """Interleave AC-off/on at each carrier and sideband detuning."""
    arms = []
    for order in (-1, 0, 1):
        for offset in (-4.0, -2.0, 0.0, 2.0, 4.0):
            for rate in RESPONSE_FREQUENCIES_MHZ:
                frequency = round(float(carrier_mhz) + order * rate + offset, 3)
                amplitudes = (RESPONSE_AMPLITUDES_DAC if len(arms) % 4 == 0
                              else tuple(reversed(RESPONSE_AMPLITUDES_DAC)))
                for amplitude in amplitudes:
                    arms.append(_arm(
                        f"f{int(rate)}_n{order:+d}_d{int(offset):+d}_a{amplitude}",
                        site_ghz, frequency, amplitude,
                        modulation_mhz=rate, order=order, offset_mhz=offset))
    return arms


def select_frequency_response_site(rows, center_ghz):
    """Choose a quiet 60-100-MHz flank in both wide-scout scan directions."""
    indexed = {round(float(row["target_frequency_ghz"]), 3): row
               for row in rows}
    expected = {round(3.8 + .002 * index, 3) for index in range(251)}
    if len(rows) != 251 or set(indexed) != expected:
        raise ValueError("frequency-response site needs a complete wide scout")
    candidates = []
    for distance_mhz in (60, 80, 100):
        for sign in (-1, 1):
            site = round(float(center_ghz) + sign * distance_mhz / 1000, 3)
            sampled = [round(site + delta / 1000.0, 3)
                       for delta in (-40, -30, -20, 0, 20, 30, 40)]
            if any(f not in indexed for f in sampled):
                continue
            survivals = [adaptive._survival(indexed[f], direction)
                         for f in sampled for direction in ("", "up", "down")]
            if not all(math.isfinite(value) for value in survivals):
                continue
            candidates.append({"site_ghz": site,
                               "distance_mhz": distance_mhz,
                               "sampled_ghz": sampled,
                               "min_survival": min(survivals),
                               "median_survival": float(np.median(survivals))})
    if not candidates:
        raise ValueError("no complete quiet-flank sampling window")
    chosen = max(candidates, key=lambda item: (item["min_survival"],
                                               item["median_survival"],
                                               -item["distance_mhz"]))
    if chosen["min_survival"] < 0.50:
        raise ValueError("no quiet 60-100-MHz calibration window")
    return chosen


def select_frequency_response_candidate(rows, *, preferred_center=4.118):
    """Select a fresh loss site only when a quiet calibration site exists."""
    site_reports = {}

    def has_site(candidate):
        center = candidate["center_ghz"]
        if center not in site_reports:
            try:
                site_reports[center] = select_frequency_response_site(rows, center)
            except ValueError:
                return False
        return True

    selected = switch.select_switch_candidate(
        rows, preferred_center=preferred_center, candidate_filter=has_site)
    return selected, site_reports[selected["center_ghz"]]


def _save_records(folder, arm, records, axis=None):
    raw_path = folder / f"{arm['name']}.npz"
    np.savez_compressed(raw_path, i=[r.i for r in records],
                        q=[r.q for r in records])
    arm["raw_npz"] = str(raw_path)
    if axis is not None:
        arm["excited_fraction_pre_axis"] = resident.classify(records, axis)


def run(*, data_root=localizer.DATA_ROOT, correction_json=None,
        frequency_response=False):
    data_root = Path(data_root)
    correction = localizer.checked_correction(data_root, correction_json)
    scout_parameters = (wide.parameters() if frequency_response
                        else adaptive.scout_parameters(phase="pre"))
    suffix = ("TLS_FluxModulation_Frequency_Response_Scout_pre"
              if frequency_response else "TLS_FluxModulation_Calibration_Scout_pre")
    scout = localizer.run(
        data_root=data_root, correction_json=correction,
        parameter_overrides={**scout_parameters, "output_suffix": suffix})
    if frequency_response:
        scout_rows = swap.read_wide_scout(scout)
        selected, site_report = select_frequency_response_candidate(scout_rows)
    else:
        selected = adaptive.select_loss_feature(adaptive.read_scout(scout))
        site_report = None
    center = round(float(selected["center_ghz"]), 3)
    flank = (float(site_report["site_ghz"]) if frequency_response
             else round(center + resident.FLANK_OFFSET_GHZ, 3))
    print(f"[flux-mod] feature={center:.3f} GHz; calibration flank={flank:.3f} GHz",
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
                     "flux_settle_time_us": 0.5,
                     "flux_predistortion_return_prefix_us": 0.5,
                     "flux_predistortion_recovery_us": 40.0,
                     "flux_predistortion_overlap_payload_readout": False,
                     "flux_predistortion_round_trip_mode": "stateful",
                     "readout_thermalization_us": 10.0,
                     "qubit_pulse_style": "arb", "do_ff": True,
                     "opx_reset_scheme": "none",
                     "opx_resident_dmem_stream": True,
                     "opx_inter_shot_delay_us": 500.0})
        pulse_us = 4.0 * float(base["sigma"]) + 0.01
        resident.resident_segments(
            compensation, pre_us=SETTLE_US + ff_pulse.flux_settle_us(base),
            pulse_us=pulse_us, post_us=POST_US, recovery_us=40.0)
        session_id = (("q3_flux_modulation_frequency_response_"
                       if frequency_response else "q3_flux_modulation_calibration_") +
                      datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") +
                      "_" + uuid.uuid4().hex[:8])
        folder = data_root / "q3" / session_id
        folder.mkdir(parents=True, exist_ok=False)
        path = folder / "manifest.json"
        refs = [_reference("ref_g_pre", "g", flank),
                _reference("ref_e_pre", "e", flank),
                _reference("ref_g_post", "g", flank),
                _reference("ref_e_post", "e", flank)]
        carrier = [_arm(f"carrier_{i:02d}", flank, f, 0)
                   for i, f in enumerate(carrier_grid(1000.0 * flank + 5.0))]
        manifest = {"schema": ("q3.flux-modulation-frequency-response.v1"
                               if frequency_response else
                               "q3.flux-modulation-calibration.v1"),
                    "status": "running", "session_id": session_id,
                    "code_commit": os.environ.get("Q3_CODE_COMMIT", "unknown"),
                    "correction_json": str(correction),
                    "correction_sha256": localizer.CORRECTION_SHA256,
                    "scout_csv": str(scout), "selected": selected,
                    "calibration_site_report": site_report,
                    "flank_ghz": flank, "dc_gain": int(dc[0]),
                    "realized_ghz": float(realized[0]),
                    "plan": plan(frequency_response=frequency_response),
                    "references": refs,
                    "carrier_arms": carrier, "sideband_arms": []}
        protocol.checkpoint(path, manifest)
        print(f"[flux-mod] manifest={path}", flush=True)
        axis = None
        raw_refs = {}
        try:
            soc, soccfg = tls.makeProxy()
            bundle = runtime_bundle(base)

            def compile_arm(arm):
                cfg = _program_config(base, arm, dc_lookup)
                return cfg, ModulatedResidentProgram(
                    soccfg, cfg, bundle.payload, bundle.loop)

            # Fail on waveform memory, DAC clipping, QICK compile, or correction
            # timing before collecting the first reference shot.
            preflight = [refs[0], carrier[len(carrier)//2]]
            if frequency_response:
                preflight.extend(_arm(
                    f"preflight_{int(rate)}", flank, flank*1000+5, 800,
                    modulation_mhz=rate)
                    for rate in RESPONSE_FREQUENCIES_MHZ)
            else:
                preflight.append(_arm("preflight_max", flank, flank*1000+5,
                                      max(AMPLITUDES_DAC)))
            for representative in preflight:
                _, program = compile_arm(representative)
                if representative["name"].startswith("preflight_"):
                    report = program.modulation_waveform_report
                    manifest.setdefault("waveform_reports", {})[
                        representative["name"]] = report
                    if not frequency_response:
                        manifest["waveform_report"] = report
                    wave_path = folder / ("compiled_flux_waveform_" +
                                          representative["name"] + ".npz")
                    np.savez_compressed(wave_path, idata=program.modulation_waveform)
                    manifest.setdefault("waveform_npz_by_rate", {})[
                        representative["name"]] = str(wave_path)
                    if not frequency_response:
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
                _save_records(folder, arm, records, axis)
                arm["status"] = "complete"
                protocol.checkpoint(path, manifest)
                return records

            for ref in refs[:2]:
                print(f"[flux-mod] {ref['name']}", flush=True)
                raw_refs[ref["name"]] = acquire(ref)
                if ref["name"] == "ref_e_pre":
                    axis = resident.fit_axis(
                        resident.record_iq(raw_refs["ref_g_pre"]),
                        resident.record_iq(raw_refs["ref_e_pre"]))
                    manifest["pre_readout_axis"] = axis
                    if not axis["valid"]:
                        raise RuntimeError("pre-run readout reference invalid")
                    protocol.checkpoint(path, manifest)

            for arm in carrier:
                acquire(arm)
                print(f"[flux-mod] carrier {arm['drive_mhz']:.1f} MHz "
                      f"P={arm['excited_fraction_pre_axis']:.3f}", flush=True)
            ground = resident.classify(raw_refs["ref_g_pre"], axis)
            best = max(carrier, key=lambda x: x["excited_fraction_pre_axis"])
            manifest["carrier_center_mhz"] = best["drive_mhz"]
            manifest["carrier_excess"] = best["excited_fraction_pre_axis"] - ground
            protocol.checkpoint(path, manifest)
            if (best is carrier[0] or best is carrier[-1] or
                    manifest["carrier_excess"] < 0.08):
                raise RuntimeError("flank carrier not resolved within the scan bracket")
            print(f"[flux-mod] carrier={best['drive_mhz']:.1f} MHz; "
                  f"excess={manifest['carrier_excess']:.3f}", flush=True)

            if frequency_response:
                sideband_arms = frequency_response_arms(
                    flank, best["drive_mhz"])
            else:
                frequencies = sideband_grid(best["drive_mhz"])
                sideband_arms = []
                for index, freq in enumerate(frequencies):
                    amplitudes = (AMPLITUDES_DAC if index % 2 == 0
                                  else tuple(reversed(AMPLITUDES_DAC)))
                    for amplitude in amplitudes:
                        sideband_arms.append(_arm(
                            f"sideband_{index:02d}_a{amplitude}",
                            flank, freq, amplitude))
            manifest["sideband_arms"] = sideband_arms
            protocol.checkpoint(path, manifest)
            for index, arm in enumerate(sideband_arms, 1):
                acquire(arm)
                print(f"[flux-mod] {index}/{len(sideband_arms)} "
                      f"{arm['drive_mhz']:.1f} MHz "
                      f"f={arm['modulation_mhz']:.0f} MHz "
                      f"A={arm['modulation_amplitude_dac']} "
                      f"P={arm['excited_fraction_pre_axis']:.3f}", flush=True)
            repeated = _arm("carrier_repeat", flank, best["drive_mhz"], 0)
            manifest["carrier_repeat"] = repeated
            acquire(repeated)
            for ref in refs[2:]:
                print(f"[flux-mod] {ref['name']}", flush=True)
                raw_refs[ref["name"]] = acquire(ref)
            manifest["post_readout_score"] = resident.score_axis(
                axis, resident.record_iq(raw_refs["ref_g_post"]),
                resident.record_iq(raw_refs["ref_e_post"]))
            manifest["carrier_repeat_excess"] = (
                repeated["excited_fraction_pre_axis"] -
                resident.classify(raw_refs["ref_g_post"], axis))
            post_parameters = (wide.parameters() if frequency_response
                               else adaptive.scout_parameters(phase="post"))
            post_suffix = ("TLS_FluxModulation_Frequency_Response_Scout_post"
                           if frequency_response else
                           "TLS_FluxModulation_Calibration_Scout_post")
            post_scout = localizer.run(
                data_root=data_root, correction_json=correction,
                parameter_overrides={**post_parameters,
                                     "output_suffix": post_suffix})
            manifest["post_scout_csv"] = str(post_scout)
            try:
                if frequency_response:
                    manifest["post_selected"] = switch.select_switch_candidate(
                        swap.read_wide_scout(post_scout),
                        preferred_center=center,
                        candidate_filter=lambda item: abs(
                            item["center_ghz"] - center) <= .004001)
                else:
                    manifest["post_selected"] = adaptive.select_loss_feature(
                        adaptive.read_scout(post_scout))
            except ValueError as exc:
                manifest["post_selection_error"] = str(exc)
            manifest["feature_stable"] = (
                bool(abs(1000.0 * (manifest["post_selected"]["center_ghz"] -
                                    center)) <= 4.0 + 1e-6)
                if frequency_response and "post_selected" in manifest else
                resident.feature_stable(selected, manifest["post_selected"])
                if "post_selected" in manifest else False)
            valid = (manifest["post_readout_score"]["valid"] and
                     manifest["feature_stable"] and
                     abs(manifest["carrier_repeat_excess"] -
                         manifest["carrier_excess"]) <= 0.15)
            manifest["status"] = "complete" if valid else "complete_controls_unstable"
            protocol.checkpoint(path, manifest)
            print(f"[flux-mod] {manifest['status']}: {path}", flush=True)
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
    parser.add_argument("--frequency-response", action="store_true",
                        help="wide-scout 20/30/40-MHz on-chip sideband calibration")
    parser.add_argument("--data-root", type=Path, default=localizer.DATA_ROOT)
    parser.add_argument("--correction-json", type=Path)
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(plan(frequency_response=args.frequency_response), indent=2))
    else:
        run(data_root=args.data_root, correction_json=args.correction_json,
            frequency_response=args.frequency_response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
