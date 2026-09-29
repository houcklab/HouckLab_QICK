"""Calibrate q3's park pi/2 pulse without a TLS scout or an echo map.

Single-pulse IQ displacement locates the current park drive frequency. A Rabi
gain sweep finds pi and pi/2, and two opposed phase cycles test the pi/2.
The existing park pi pulse is not used as a prerequisite for readout analysis.
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
RABI_GAINS = tuple(range(0, 30001, 1500))
COARSE_SHOTS = 300
CHECK_SHOTS = 400


def choose_frequency(rows, *, baseline):
    """Find the largest single-pulse IQ displacement from the no-drive cloud."""
    if not rows:
        raise ValueError("empty park frequency scan")
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


def plan():
    return {"hardware_access": False,
            "purpose": "calibrate and independently phase-check park pi/2",
            "bias": "q3 park", "reset_mode": "passive",
            "frequency_offsets_mhz": list(OFFSETS_MHZ),
            "coarse_gains": list(COARSE_GAINS),
            "rabi_gains": list(RABI_GAINS),
            "phase_check_deg": [0, 90, 180, 270],
            "readout": "raw IQ displacement, no existing pi calibration required",
            "fresh_t1_scan": False, "wide_echo_map": False,
            "terminal": "no custom progress messages"}


def run(*, data_root=None, correction_json=None):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
        FivePointApplesToApples as five,
        TLSDualTransitionLoss as dual,
        TLSPumpProbeLocalizer as localizer,
        TLSPumpProbeResidentDrive as resident,
        TLSSpectroscopy as tls,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import (
        _block_timeout_s, _run_program, runtime_bundle,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import (
        ProductionResetSession,
    )

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

        session_id = ("q3_park_pi2_calibration_" +
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
        manifest = {"schema": "q3.park-pi2-calibration.v1",
                    "status": "running", "session_id": session_id,
                    "code_commit": commit, "park_frequency_mhz": park_mhz,
                    "park_gain": park_gain,
                    "pulse_sigma_us": float(base["sigma"]),
                    "correction_json": str(correction),
                    "correction_sha256": localizer.CORRECTION_SHA256,
                    "plan": plan(), "frequency_sweep": [],
                    "rabi_sweep": [], "phase_blocks": []}
        dual.checkpoint(manifest_path, manifest)
        single_class, double_class = make_park_programs(
            resident.ResidentDriveProgram)
        try:
            soc, soccfg = tls.makeProxy()
            bundle = runtime_bundle(base)

            def configuration(offset, gain, shots, second_phase=None):
                arm = {"flux_ghz": park_mhz / 1000.,
                       "drive_mhz": park_mhz + float(offset),
                       "gain": int(gain), "reference_state": None,
                       "preparation_state": "g",
                       "pre_drive_us": 30., "post_drive_us": .1,
                       "shots": int(shots)}
                cfg = resident.arm_config(
                    base, arm, {park_mhz / 1000.: park_gain})
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

            for offset in (OFFSETS_MHZ[0], OFFSETS_MHZ[-1]):
                single_class(
                    soccfg, configuration(offset, COARSE_GAINS[0],
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
            for offset in OFFSETS_MHZ:
                for gain in COARSE_GAINS:
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
                manifest["status"] = "complete_no_park_drive"
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
            gate = target_cal.two_pulse_gate(
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
