"""Calibrate a target-resident pi/2 pulse at one quiet q3 flux site.

The previous full-band run proved a phase axis at park but had unresolved
short-delay contrast at its quiet target. This bounded follow-up first finds
the target microwave frequency with single-pulse response, then measures a
Rabi gain curve and validates the selected pi/2 with a two-pulse phase cycle.
No echo decay or full-band map is acquired in this calibration.
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
    TLSEchoDephasingMap as echo,
)


OFFSETS_MHZ = (-10., -7.5, -5., -2.5, 0., 2.5, 5., 7.5, 10.)
COARSE_GAINS = (4000, 8000, 12000, 16000, 20000)
RABI_GAINS = tuple(range(0, 30001, 1500))
SHOTS = 300


def validate_source(source):
    if (source.get("schema") != "q3.echo-dephasing-map.v1" or
            source.get("status") != "stopped_quiet_pilot"):
        raise ValueError("source must be a stopped echo-map quiet pilot")
    try:
        frequency = float(source["quiet_anchor"]["frequency_ghz"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("source has no measured quiet anchor") from exc
    if not math.isfinite(frequency) or not 3.8 <= frequency <= 4.3:
        raise ValueError("source quiet anchor is outside q3 scan")
    return frequency


def choose_detuning(rows, *, ground_fraction):
    groups = {}
    for row in rows:
        groups.setdefault(float(row["offset_mhz"]), []).append(row)
    choices = []
    for offset, group in groups.items():
        if len({int(row["gain"]) for row in group}) < 3:
            continue
        top = sorted(float(row["excited_fraction"]) for row in group)[-2:]
        choices.append({"offset_mhz": offset,
                        "response": sum(top) / 2 - float(ground_fraction)})
    if not choices:
        raise ValueError("frequency sweep has no complete gain groups")
    best = max(choices, key=lambda row: (row["response"],
                                          -abs(row["offset_mhz"])))
    return {**best, "valid": best["response"] >= .10}


def fit_rabi(rows):
    points = sorted((int(row["gain"]), float(row["excited_fraction"]))
                    for row in rows)
    if (len(points) < 8 or points[0][0] != 0 or
            len({gain for gain, _ in points}) != len(points) or
            any(not math.isfinite(fraction) for _, fraction in points)):
        return {"valid": False, "reason": "incomplete Rabi gain sweep"}
    gains = [gain for gain, _ in points]
    values = [value for _, value in points]
    smooth = [values[0]] + [(.25 * values[i - 1] + .5 * values[i] +
                            .25 * values[i + 1])
                           for i in range(1, len(values) - 1)] + [values[-1]]
    baseline = values[0]
    candidates = [i for i in range(2, len(points) - 3)
                  if smooth[i] >= smooth[i - 1] and
                  smooth[i] >= smooth[i + 1] and
                  smooth[i] - baseline >= .12 and
                  smooth[i] - min(smooth[i + 1:i + 4]) >= .07]
    if not candidates:
        return {"valid": False, "reason": "no resolved first Rabi turnover"}
    peak_index = candidates[0]
    pi_gain = gains[peak_index]
    peak = values[peak_index]
    half_level = baseline + .5 * (peak - baseline)
    for index in range(1, peak_index + 1):
        lo, hi = values[index - 1], values[index]
        if lo <= half_level <= hi and hi > lo:
            pi2_gain = int(round(gains[index - 1] +
                                 (half_level - lo) *
                                 (gains[index] - gains[index - 1]) / (hi - lo)))
            break
    else:
        return {"valid": False, "reason": "no rising half-height crossing"}
    ratio = pi2_gain / pi_gain
    if not .35 <= ratio <= .65:
        return {"valid": False, "reason": "half-height gain inconsistent with pi/2",
                "pi_gain": pi_gain, "pi2_gain": pi2_gain}
    return {"valid": True, "pi_gain": pi_gain, "pi2_gain": pi2_gain,
            "baseline_fraction": baseline, "peak_fraction": peak,
            "half_level": half_level}


def two_pulse_gate(first, second, *, ground, pi):
    first = {int(key): float(value) for key, value in first.items()}
    second = {int(key): float(value) for key, value in second.items()}
    if set(first) != set(echo.PHASES_DEG) or set(second) != set(echo.PHASES_DEG):
        raise ValueError("two-pulse validation needs four phases per block")
    midpoint = (float(ground) + float(pi)) / 2
    valid = bool(float(pi) - float(ground) >= .15)
    for block in (first, second):
        valid &= (block[0] - block[180] >= .18 and
                  abs(block[0] - pi) <= .12 and
                  abs(block[180] - ground) <= .12 and
                  abs(block[90] - midpoint) <= .15 and
                  abs(block[270] - midpoint) <= .15)
    valid &= abs((first[0] - first[180]) -
                 (second[0] - second[180])) <= .12
    return {"valid": bool(valid), "first_span": first[0] - first[180],
            "reverse_span": second[0] - second[180]}


def make_double_pulse_program(parent):
    """Run two calibrated target pulses in one settled corrected visit."""
    class DoublePulseProgram(parent):
        def _resident_excursion(self):
            from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
            cfg = self.cfg
            park = int(cfg["ff_park_gain"])
            target = int(cfg["ff_gain"])
            pulse_us = 2 * (4 * float(cfg["sigma"]) + .01)
            target_segments, recovery = ff_pulse.compensation_round_trip_segments(
                self._t1_ff_compensation,
                echo.PRE_ECHO_US + self._t1_ff_settle_us + pulse_us +
                echo.POST_ECHO_US,
                recovery_us=self._t1_ff_predistortion_recovery_us)
            before, tail = ff_pulse.split_compensation_segments(
                target_segments, echo.PRE_ECHO_US + self._t1_ff_settle_us)
            during, after = ff_pulse.split_compensation_segments(tail, pulse_us)
            if not before or not during or not after:
                raise ValueError("correction does not cover two-pulse window")
            held = float(before[-1][0])
            if max(abs(float(level) - held) for level, _ in during) > .0015:
                raise ValueError("flux correction varies too much during two-pulse window")
            ff_pulse.play_relative_compensation_segments(self, park, target, before)
            self.sync_all(0)
            for phase in (0, int(cfg["rabi_second_phase_deg"])):
                self.set_pulse_registers(
                    ch=cfg["qubit_ch"], style="arb",
                    freq=self.freq2reg(float(cfg["opx_resident_freq_mhz"]),
                                       gen_ch=cfg["qubit_ch"]),
                    phase=self.deg2reg(phase, gen_ch=cfg["qubit_ch"]),
                    gain=int(cfg["opx_resident_gain"]), waveform="qubit")
                self.pulse(ch=cfg["qubit_ch"])
                self.sync_all(self.us2cycles(.01))
            ff_pulse.play_relative_compensation_segments(self, park, target, after)
            ff_pulse.play_relative_compensation_segments(self, park, target, recovery)
            ff_pulse.play_hard_step(self, park)
            self.sync_all(0)

    return DoublePulseProgram


def plan():
    return {"hardware_access": False, "purpose": "single-site target pi/2 calibration",
            "offsets_mhz": list(OFFSETS_MHZ),
            "coarse_gains": list(COARSE_GAINS),
            "rabi_gain_sweep": list(RABI_GAINS),
            "two_pulse_phase_check": True,
            "phases_deg": list(echo.PHASES_DEG),
            "shots_per_arm": SHOTS,
            "fresh_t1_scan": True,
            "source": "latest stopped quiet-site echo map",
            "wide_echo_map": False,
            "terminal": "no custom progress messages"}


def run(*, data_root=None, correction_json=None, source_manifest=None):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
        TLSPumpProbeLocalizer as localizer,
    )
    data_root = Path(data_root or localizer.DATA_ROOT)
    correction = localizer.checked_correction(data_root, correction_json)
    if source_manifest is None:
        paths = sorted((data_root / "q3").glob("q3_echo_dephasing_map_*/manifest.json"))
        if not paths:
            raise FileNotFoundError("no prior echo-map quiet pilot on the NAS")
        source_manifest = paths[-1]
    source_manifest = Path(source_manifest)
    source = json.loads(source_manifest.read_text(encoding="utf-8"))
    validate_source(source)
    if source.get("correction_sha256") != localizer.CORRECTION_SHA256:
        raise ValueError("source echo map used another flux correction")

    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
        FivePointApplesToApples as five,
        TLSDualTransitionLoss as dual,
        TLSPumpProbeResidentDrive as resident,
        TLSPumpProbeWidePassiveScan as wide,
        TLSSpectroscopy as tls,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.ThreePointApplesToApples import _integer_dc_grid
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import (
        _block_timeout_s, _run_program, runtime_bundle,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import ProductionResetSession

    scout_path = localizer.run(
        data_root=data_root, correction_json=correction,
        parameter_overrides={**wide.parameters(),
                             "output_suffix": "TLS_Echo_Pi2_Calibration_Scout"},
        announce=False)
    anchor = echo.select_quiet_anchor(dual.read_scout(scout_path))
    center = anchor["frequency_ghz"]
    with localizer.scan_environment(correction):
        tls.QUBIT, tls.SET_YOKO, tls.outerFolder = "q3", False, str(data_root)
        five.install_scan_calibration(tls)
        if int(tls.BaseConfig["ff_park_gain"]) != -25146:
            raise RuntimeError("q3 park gain differs from verified configuration")
        dc, realized = _integer_dc_grid(wide.parameters(),
                                        np.asarray([center]), tls)
        target_gain = int(dc[0])
        compensation = tls._load_correction(str(correction), str(data_root))
        base = ProductionResetSession.passive().apply(tls.BaseConfig)
        five.apply_verified_feedback_timing(base)
        base.update({"apply_flux_tail_compensation": True,
                     "flux_tail_compensation": compensation,
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
        session_id = ("q3_echo_pi2_calibration_" +
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
        manifest = {"schema": "q3.echo-pi2-calibration.v1",
                    "status": "running", "session_id": session_id,
                    "code_commit": commit,
                    "source_manifest": str(source_manifest),
                    "scout_csv": str(scout_path), "quiet_anchor": anchor,
                    "target_gain": target_gain,
                    "realized_frequency_ghz": float(realized[0]),
                    "pulse_sigma_us": float(base["sigma"]),
                    "correction_json": str(correction),
                    "correction_sha256": localizer.CORRECTION_SHA256,
                    "plan": plan(), "frequency_sweep": [],
                    "rabi_sweep": [], "phase_blocks": []}
        dual.checkpoint(manifest_path, manifest)
        double_class = make_double_pulse_program(resident.ResidentDriveProgram)
        try:
            soc, soccfg = tls.makeProxy()
            bundle = runtime_bundle(base)

            def configuration(offset, gain, shots, second_phase=None):
                arm = {"flux_ghz": center,
                       "drive_mhz": 1000 * center + float(offset),
                       "gain": int(gain), "reference_state": None,
                       "preparation_state": "g",
                       "pre_drive_us": echo.PRE_ECHO_US,
                       "post_drive_us": echo.POST_ECHO_US,
                       "shots": int(shots)}
                cfg = resident.arm_config(base, arm, {center: target_gain})
                if second_phase is not None:
                    cfg["rabi_second_phase_deg"] = int(second_phase)
                    cfg["ff_hold"] = (echo.PRE_ECHO_US + echo.POST_ECHO_US +
                                      2 * (4 * float(cfg["sigma"]) + .01))
                return cfg

            def acquire(cfg, program_type, shots, filename):
                program = program_type(soccfg, cfg, bundle.payload, bundle.loop)
                records = _run_program(
                    soc, program, max(30., _block_timeout_s(cfg, shots)),
                    cfg, total_shots=shots)
                if len(records) != shots:
                    raise RuntimeError(f"{filename}: incomplete IQ records")
                np.savez_compressed(folder / filename,
                                    i=[r.i for r in records],
                                    q=[r.q for r in records])
                return records

            def reference(state, name):
                cfg = configuration(0, 0, 400)
                cfg["opx_resident_reference_state"] = state
                return acquire(cfg, resident.ResidentDriveProgram, 400,
                               name + ".npz")

            for offset in (OFFSETS_MHZ[0], OFFSETS_MHZ[-1]):
                resident.ResidentDriveProgram(
                    soccfg, configuration(offset, COARSE_GAINS[0], SHOTS),
                    bundle.payload, bundle.loop)
            double_class(soccfg, configuration(0, 6000, SHOTS,
                                               second_phase=180),
                         bundle.payload, bundle.loop)
            manifest["compiled_pulse_edges"] = True
            dual.checkpoint(manifest_path, manifest)

            ref_g, ref_e = reference("g", "ref_g_pre"), reference("e", "ref_e_pre")
            axis = resident.fit_axis(resident.record_iq(ref_g),
                                     resident.record_iq(ref_e))
            reference_contrast = (resident.classify(ref_e, axis) -
                                  resident.classify(ref_g, axis))
            manifest["readout_axis"] = axis
            manifest["reference_contrast"] = reference_contrast
            dual.checkpoint(manifest_path, manifest)
            if not axis["valid"] or reference_contrast < .4:
                manifest["status"] = "stopped_readout_reference"
                dual.checkpoint(manifest_path, manifest)
                return manifest_path

            zero = acquire(configuration(0, 0, 400),
                           resident.ResidentDriveProgram, 400,
                           "zero_pre.npz")
            ground = resident.classify(zero, axis)
            manifest["ground_fraction"] = ground
            dual.checkpoint(manifest_path, manifest)
            for offset in OFFSETS_MHZ:
                for gain in COARSE_GAINS:
                    records = acquire(
                        configuration(offset, gain, SHOTS),
                        resident.ResidentDriveProgram, SHOTS,
                        f"frequency_{offset:+05.1f}MHz_gain_{gain:05d}.npz")
                    manifest["frequency_sweep"].append({
                        "offset_mhz": offset, "gain": gain,
                        "excited_fraction": resident.classify(records, axis)})
                    dual.checkpoint(manifest_path, manifest)
            choice = choose_detuning(manifest["frequency_sweep"],
                                     ground_fraction=ground)
            manifest["chosen_detuning"] = choice
            dual.checkpoint(manifest_path, manifest)
            if not choice["valid"]:
                manifest["status"] = "complete_no_target_drive"
                dual.checkpoint(manifest_path, manifest)
                return manifest_path

            offset = choice["offset_mhz"]
            for gain in RABI_GAINS:
                records = acquire(
                    configuration(offset, gain, 300),
                    resident.ResidentDriveProgram, 300,
                    f"rabi_gain_{gain:05d}.npz")
                manifest["rabi_sweep"].append({
                    "gain": gain,
                    "excited_fraction": resident.classify(records, axis)})
                dual.checkpoint(manifest_path, manifest)
            zero_post = acquire(configuration(offset, 0, 400),
                                resident.ResidentDriveProgram, 400,
                                "zero_post.npz")
            ground_post = resident.classify(zero_post, axis)
            manifest["ground_fraction_post"] = ground_post
            fit = fit_rabi(manifest["rabi_sweep"])
            manifest["rabi_fit"] = fit
            dual.checkpoint(manifest_path, manifest)
            if abs(ground_post - ground) > .10:
                manifest["status"] = "complete_ground_drift"
                dual.checkpoint(manifest_path, manifest)
                return manifest_path
            if not fit["valid"]:
                manifest["status"] = "complete_rabi_unresolved"
                dual.checkpoint(manifest_path, manifest)
                return manifest_path

            pi2_gain = fit["pi2_gain"]
            pi2_records = acquire(
                configuration(offset, pi2_gain, 400),
                resident.ResidentDriveProgram, 400,
                "pi2_single_check.npz")
            pi2_fraction = resident.classify(pi2_records, axis)
            manifest["pi2_single_fraction"] = pi2_fraction
            dual.checkpoint(manifest_path, manifest)
            if abs(pi2_fraction - fit["half_level"]) > .10:
                manifest["status"] = "complete_pi2_midpoint_unstable"
                dual.checkpoint(manifest_path, manifest)
                return manifest_path

            for block, phases in enumerate((echo.PHASES_DEG,
                                            tuple(reversed(echo.PHASES_DEG)))):
                fractions = {}
                for phase in phases:
                    records = acquire(
                        configuration(offset, pi2_gain, 300,
                                      second_phase=phase),
                        double_class, 300,
                        f"two_pulse_block_{block}_phase_{phase}.npz")
                    fractions[phase] = resident.classify(records, axis)
                manifest["phase_blocks"].append(fractions)
                dual.checkpoint(manifest_path, manifest)
            gate = two_pulse_gate(
                *manifest["phase_blocks"],
                ground=(ground + ground_post) / 2,
                pi=fit["peak_fraction"])
            manifest["two_pulse_gate"] = gate
            dual.checkpoint(manifest_path, manifest)
            ref_g_post = reference("g", "ref_g_post")
            ref_e_post = reference("e", "ref_e_post")
            post_axis = resident.score_axis(
                axis, resident.record_iq(ref_g_post),
                resident.record_iq(ref_e_post))
            manifest["post_readout_score"] = post_axis
            manifest["status"] = ("complete_calibrated" if gate["valid"] and
                                  post_axis["valid"] else
                                  "complete_controls_unstable")
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
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--correction-json", type=Path)
    parser.add_argument("--source-manifest", type=Path)
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(plan(), indent=2))
    else:
        run(data_root=args.data_root, correction_json=args.correction_json,
            source_manifest=args.source_manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
