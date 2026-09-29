"""Calibrate q3's park or target-resident pi/2 pulse without a T1 scout.

Single-pulse IQ displacement locates the drive frequency. A Rabi gain sweep
finds pi and pi/2, and two opposed phase cycles test the pi/2. The existing
park pi pulse is not used as a prerequisite for readout analysis.
"""

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import subprocess
import uuid

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSEchoPulseCalibration as target_cal,
)


OFFSETS_MHZ = (-6., -4., -2., 0., 2., 4., 6.)
COARSE_GAINS = (6000, 12000, 18000)
TARGET_OFFSETS_MHZ = (-10., -7.5, -5., -2.5, 0., 2.5, 5., 7.5, 10.)
TARGET_COARSE_GAINS = (4000, 8000, 12000, 16000, 20000)
RABI_GAINS = tuple(range(0, 30001, 1500))
COARSE_SHOTS = 300
CHECK_SHOTS = 400


def choose_frequency(rows, *, baseline):
    """Find the largest single-pulse IQ displacement from the no-drive cloud."""
    if not rows:
        raise ValueError("empty pulse frequency scan")
    baseline = complex(baseline)
    candidates = []
    for row in rows:
        value = complex(float(row["mean_i"]), float(row["mean_q"]))
        candidates.append((abs(value - baseline), row))
    amplitude, best = max(candidates,
                          key=lambda pair: (pair[0],
                                            -abs(float(pair[1]["offset_mhz"]))))
    return {"offset_mhz": float(best["offset_mhz"]),
            "gain": int(best["gain"]), "iq_displacement": float(amplitude),
            "valid": bool(math.isfinite(amplitude) and amplitude >= 800.)}


def projected_response(value, *, baseline, axis, scale):
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("invalid IQ projection scale")
    return float(np.real((complex(value) - complex(baseline)) *
                         np.conj(complex(axis))) / scale)


def fit_rabi_iq(rows):
    """Reuse the first-turnover test on normalized IQ, not assignment counts."""
    converted = [{"gain": row["gain"],
                  "excited_fraction": row["response"]} for row in rows]
    return target_cal.fit_rabi(converted)


def phase_circle_gate(first, second, *, ground, pi):
    """Validate a four-phase cycle without assuming its maximum is at zero.

    The relative phase includes a fixed delay between the two pulses.  Its
    offset may be nonzero, but the circle's radius and phase must repeat.
    """
    def fit(block):
        values = {int(key): float(value) for key, value in block.items()}
        if set(values) != {0, 90, 180, 270}:
            raise ValueError("phase cycle requires four cardinal phases")
        center = sum(values.values()) / 4
        x = (values[0] - values[180]) / 2
        y = (values[90] - values[270]) / 2
        amplitude = math.hypot(x, y)
        return {"center": center, "amplitude": amplitude,
                "phase_offset_deg": math.degrees(math.atan2(y, x)),
                "maximum": center + amplitude,
                "minimum": center - amplitude}

    a, b = fit(first), fit(second)
    phase_a = math.radians(a["phase_offset_deg"])
    phase_b = math.radians(b["phase_offset_deg"])
    drift = math.degrees(abs(math.atan2(math.sin(phase_a - phase_b),
                                        math.cos(phase_a - phase_b))))
    mean_phase = math.degrees(math.atan2(math.sin(phase_a) +
                                        math.sin(phase_b),
                                        math.cos(phase_a) +
                                        math.cos(phase_b)))
    valid = bool(float(pi) - float(ground) >= .3 and
                 all(math.isfinite(v) for fit_result in (a, b)
                     for v in fit_result.values()) and
                 all(fit_result["amplitude"] >= .25 and
                     abs(fit_result["maximum"] - pi) <= .20 and
                     abs(fit_result["minimum"] - ground) <= .20
                     for fit_result in (a, b)) and
                 abs(a["center"] - b["center"]) <= .12 and
                 abs(a["amplitude"] - b["amplitude"]) <= .15 and
                 drift <= 15.)
    return {"valid": valid, "first": a, "reversed": b,
            "phase_drift_deg": drift,
            "phase_offset_deg": mean_phase}


def make_park_programs(parent):
    """Use the verified resident readout path without a nonexistent flux step."""
    class ParkDriveProgram(parent):
        def _resident_excursion(self):
            from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.programs import _pulse_pi_and_align
            cfg = self.cfg
            self.sync_all(self.us2cycles(float(cfg["opx_resident_pre_us"])))
            self.set_pulse_registers(
                ch=cfg["qubit_ch"], style="arb",
                freq=self.freq2reg(float(cfg["opx_resident_freq_mhz"]),
                                   gen_ch=cfg["qubit_ch"]),
                phase=self.deg2reg(0, gen_ch=cfg["qubit_ch"]),
                gain=int(cfg["opx_resident_gain"]), waveform="qubit")
            _pulse_pi_and_align(self)
            self.sync_all(self.us2cycles(float(cfg["opx_resident_post_us"])))

    class ParkDoublePulseProgram(ParkDriveProgram):
        def _resident_excursion(self):
            from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.programs import _pulse_pi_and_align
            cfg = self.cfg
            self.sync_all(self.us2cycles(float(cfg["opx_resident_pre_us"])))
            for phase in (0, int(cfg["rabi_second_phase_deg"])):
                self.set_pulse_registers(
                    ch=cfg["qubit_ch"], style="arb",
                    freq=self.freq2reg(float(cfg["opx_resident_freq_mhz"]),
                                       gen_ch=cfg["qubit_ch"]),
                    phase=self.deg2reg(phase, gen_ch=cfg["qubit_ch"]),
                    gain=int(cfg["opx_resident_gain"]), waveform="qubit")
                _pulse_pi_and_align(self)
            self.sync_all(self.us2cycles(float(cfg["opx_resident_post_us"])))

    return ParkDriveProgram, ParkDoublePulseProgram


def validate_target(target_ghz):
    if target_ghz is None:
        return None
    target = float(target_ghz)
    if not math.isfinite(target) or not 3.8 <= target <= 4.3:
        raise ValueError("target must lie inside the q3 3.8–4.3 GHz band")
    return target


def select_programs(parent, *, target_ghz=None):
    if validate_target(target_ghz) is None:
        return make_park_programs(parent)
    return parent, target_cal.make_double_pulse_program(parent)


def plan(*, target_ghz=None):
    target = validate_target(target_ghz)
    return {"hardware_access": False,
            "purpose": "calibrate and independently phase-check pi/2",
            "bias": "q3 park" if target is None else
                    f"{target:.3f} GHz target",
            "reset_mode": "passive",
            "frequency_offsets_mhz": list(OFFSETS_MHZ if target is None
                                          else TARGET_OFFSETS_MHZ),
            "coarse_gains": list(COARSE_GAINS if target is None
                                 else TARGET_COARSE_GAINS),
            "rabi_gains": list(RABI_GAINS),
            "phase_check_deg": [0, 90, 180, 270],
            "readout": "raw IQ displacement, no existing pi calibration required",
            "fresh_t1_scan": False, "wide_echo_map": False,
            "terminal": "no custom progress messages"}


def run(*, data_root=None, correction_json=None, target_ghz=None):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
        FivePointApplesToApples as five,
        TLSDualTransitionLoss as dual,
        TLSPumpProbeLocalizer as localizer,
        TLSPumpProbeResidentDrive as resident,
        TLSPumpProbeWidePassiveScan as wide,
        TLSSpectroscopy as tls,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.ThreePointApplesToApples import _integer_dc_grid
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import (
        _block_timeout_s, _run_program, runtime_bundle,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import (
        ProductionResetSession,
    )

    target_ghz = validate_target(target_ghz)
    offsets = OFFSETS_MHZ if target_ghz is None else TARGET_OFFSETS_MHZ
    coarse_gains = COARSE_GAINS if target_ghz is None else TARGET_COARSE_GAINS
    data_root = Path(data_root or localizer.DATA_ROOT)
    correction = localizer.checked_correction(data_root, correction_json)
    with localizer.scan_environment(correction):
        tls.QUBIT, tls.SET_YOKO, tls.outerFolder = "q3", False, str(data_root)
        five.install_scan_calibration(tls)
        base = ProductionResetSession.passive().apply(tls.BaseConfig)
        five.apply_verified_feedback_timing(base)
        park_gain = int(base["ff_park_gain"])
        if park_gain != -25146:
            raise RuntimeError("q3 park gain differs from verified configuration")
        park_mhz = float(base["qubit_pi_freq"])
        if not 4350. <= park_mhz <= 4380.:
            raise RuntimeError("q3 park drive is outside verified range")
        if target_ghz is None:
            site_ghz = park_mhz / 1000.
            site_gain = park_gain
            realized_ghz = site_ghz
        else:
            site_ghz = target_ghz
            dc, realized = _integer_dc_grid(
                wide.parameters(), np.asarray([site_ghz]), tls)
            site_gain = int(dc[0])
            realized_ghz = float(realized[0])
        base.update({"apply_flux_tail_compensation": True,
                     "flux_tail_compensation": tls._load_correction(
                         str(correction), str(data_root)),
                     "flux_fit_params": tls.FLUX_FIT_PARAMS,
                     "flux_settle_time_us": .5,
                     "flux_predistortion_return_prefix_us": .5,
                     "flux_predistortion_recovery_us": 40.,
                     "flux_predistortion_overlap_payload_readout": False,
                     "flux_predistortion_round_trip_mode": "stateful",
                     "readout_thermalization_us": 10.,
                     "qubit_pulse_style": "arb", "do_ff": True,
                     "opx_reset_scheme": "none",
                     "opx_resident_dmem_stream": True,
                     "opx_inter_shot_delay_us": 500.})

        session_id = (("q3_park_pi2_calibration_" if target_ghz is None
                       else "q3_target_pi2_calibration_") +
                      datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") +
                      "_" + uuid.uuid4().hex[:8])
        folder = data_root / "q3" / session_id
        folder.mkdir(parents=True, exist_ok=False)
        manifest_path = folder / "manifest.json"
        try:
            commit = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=Path(__file__).resolve().parents[4], text=True,
                stderr=subprocess.DEVNULL).strip()
        except (OSError, subprocess.CalledProcessError):
            commit = "unknown"
        manifest = {"schema": ("q3.park-pi2-calibration.v1"
                                if target_ghz is None else
                                "q3.target-pi2-calibration.v1"),
                    "status": "running", "session_id": session_id,
                    "code_commit": commit, "park_frequency_mhz": park_mhz,
                    "park_gain": park_gain,
                    "site_frequency_ghz": site_ghz,
                    "site_gain": site_gain,
                    "realized_frequency_ghz": realized_ghz,
                    "pulse_sigma_us": float(base["sigma"]),
                    "correction_json": str(correction),
                    "correction_sha256": localizer.CORRECTION_SHA256,
                    "plan": plan(target_ghz=target_ghz),
                    "frequency_sweep": [],
                    "rabi_sweep": [], "phase_blocks": []}
        dual.checkpoint(manifest_path, manifest)
        single_class, double_class = select_programs(
            resident.ResidentDriveProgram, target_ghz=target_ghz)
        try:
            soc, soccfg = tls.makeProxy()
            bundle = runtime_bundle(base)

            def configuration(offset, gain, shots, second_phase=None):
                arm = {"flux_ghz": site_ghz,
                       "drive_mhz": 1000 * site_ghz + float(offset),
                       "gain": int(gain), "reference_state": None,
                       "preparation_state": "g",
                       "pre_drive_us": 30., "post_drive_us": .1,
                       "shots": int(shots)}
                cfg = resident.arm_config(
                    base, arm, {site_ghz: site_gain})
                if second_phase is not None:
                    cfg["rabi_second_phase_deg"] = int(second_phase)
                    cfg["ff_hold"] = 30. + .1 + 2 * (
                        4 * float(cfg["sigma"]) + .01)
                return cfg

            def acquire(offset, gain, shots, filename, second_phase=None):
                cfg = configuration(offset, gain, shots, second_phase)
                program_type = (single_class if second_phase is None
                                else double_class)
                program = program_type(soccfg, cfg, bundle.payload, bundle.loop)
                records = _run_program(
                    soc, program, max(30., _block_timeout_s(cfg, shots)),
                    cfg, total_shots=shots)
                if len(records) != shots:
                    raise RuntimeError(f"{filename}: incomplete IQ records")
                np.savez_compressed(folder / filename,
                                    i=[r.i for r in records],
                                    q=[r.q for r in records])
                return complex(np.mean(resident.record_iq(records)))

            for offset in (offsets[0], offsets[-1]):
                single_class(
                    soccfg, configuration(offset, coarse_gains[0],
                                          COARSE_SHOTS),
                    bundle.payload, bundle.loop)
            double_class(soccfg, configuration(0, 6000, CHECK_SHOTS,
                                               second_phase=180),
                         bundle.payload, bundle.loop)
            manifest["compiled_pulse_edges"] = True
            dual.checkpoint(manifest_path, manifest)

            zero = acquire(0, 0, 600, "zero_pre.npz")
            manifest["zero_pre_iq"] = [zero.real, zero.imag]
            dual.checkpoint(manifest_path, manifest)
            for offset in offsets:
                for gain in coarse_gains:
                    value = acquire(offset, gain, COARSE_SHOTS,
                                    f"frequency_{offset:+05.1f}MHz_gain_{gain:05d}.npz")
                    manifest["frequency_sweep"].append({
                        "offset_mhz": offset, "gain": gain,
                        "mean_i": value.real, "mean_q": value.imag})
                    dual.checkpoint(manifest_path, manifest)
            choice = choose_frequency(manifest["frequency_sweep"],
                                      baseline=zero)
            manifest["chosen_frequency"] = choice
            dual.checkpoint(manifest_path, manifest)
            if not choice["valid"]:
                manifest["status"] = ("complete_no_park_drive"
                                      if target_ghz is None else
                                      "complete_no_target_drive")
                dual.checkpoint(manifest_path, manifest)
                return manifest_path

            offset = choice["offset_mhz"]
            witness = acquire(offset, choice["gain"], CHECK_SHOTS,
                              "frequency_repeat.npz")
            selected = next(row for row in manifest["frequency_sweep"]
                            if row["offset_mhz"] == offset and
                            row["gain"] == choice["gain"])
            first = complex(selected["mean_i"], selected["mean_q"]) - zero
            repeated = witness - zero
            repeat_amplitude = abs(repeated)
            repeat_cosine = (float(np.real(repeated * np.conj(first)) /
                                   (abs(repeated) * abs(first)))
                             if repeat_amplitude > 0 else math.nan)
            manifest["frequency_repeat"] = {
                "iq_displacement": repeat_amplitude,
                "axis_cosine": repeat_cosine,
                "valid": bool(repeat_amplitude >= 600. and
                              repeat_cosine >= .7)}
            dual.checkpoint(manifest_path, manifest)
            if not manifest["frequency_repeat"]["valid"]:
                manifest["status"] = "complete_frequency_unstable"
                dual.checkpoint(manifest_path, manifest)
                return manifest_path

            axis = repeated / repeat_amplitude
            scale = repeat_amplitude

            def response(value):
                return projected_response(value, baseline=zero,
                                          axis=axis, scale=scale)

            for gain in RABI_GAINS:
                value = acquire(offset, gain, COARSE_SHOTS,
                                f"rabi_gain_{gain:05d}.npz")
                manifest["rabi_sweep"].append({
                    "gain": gain, "response": response(value),
                    "mean_i": value.real, "mean_q": value.imag})
                dual.checkpoint(manifest_path, manifest)
            fit = fit_rabi_iq(manifest["rabi_sweep"])
            manifest["rabi_fit"] = fit
            dual.checkpoint(manifest_path, manifest)
            if not fit["valid"]:
                manifest["status"] = "complete_rabi_unresolved"
                dual.checkpoint(manifest_path, manifest)
                return manifest_path

            pi2_gain = fit["pi2_gain"]
            pi2 = response(acquire(offset, pi2_gain, CHECK_SHOTS,
                                   "pi2_single_check.npz"))
            manifest["pi2_single_response"] = pi2
            dual.checkpoint(manifest_path, manifest)
            if abs(pi2 - fit["half_level"]) > .15:
                manifest["status"] = "complete_pi2_midpoint_unstable"
                dual.checkpoint(manifest_path, manifest)
                return manifest_path

            for block, phases in enumerate(((0, 90, 180, 270),
                                            (270, 180, 90, 0))):
                values = {}
                for phase in phases:
                    value = acquire(
                        offset, pi2_gain, CHECK_SHOTS,
                        f"phase_block_{block}_phase_{phase}.npz",
                        second_phase=phase)
                    values[phase] = response(value)
                manifest["phase_blocks"].append(values)
                dual.checkpoint(manifest_path, manifest)
            gate = phase_circle_gate(
                *manifest["phase_blocks"],
                ground=fit["baseline_fraction"],
                pi=fit["peak_fraction"])
            manifest["two_pulse_gate"] = gate
            dual.checkpoint(manifest_path, manifest)

            zero_post = acquire(0, 0, 600, "zero_post.npz")
            pi_post = acquire(offset, fit["pi_gain"], CHECK_SHOTS,
                              "pi_post.npz")
            manifest["end_checks"] = {
                "zero_response": response(zero_post),
                "pi_response": response(pi_post)}
            stable = (abs(response(zero_post)) <= .15 and
                      abs(response(pi_post) - fit["peak_fraction"]) <= .20)
            manifest["status"] = ("complete_calibrated" if gate["valid"] and
                                  stable else "complete_controls_unstable")
            dual.checkpoint(manifest_path, manifest)
            return manifest_path
        except BaseException as exc:
            manifest["status"] = "failed"
            manifest["error"] = f"{type(exc).__name__}: {exc}"
            dual.checkpoint(manifest_path, manifest)
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--data-root")
    parser.add_argument("--correction-json")
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(plan(), indent=2))
        return 0
    run(data_root=args.data_root, correction_json=args.correction_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
