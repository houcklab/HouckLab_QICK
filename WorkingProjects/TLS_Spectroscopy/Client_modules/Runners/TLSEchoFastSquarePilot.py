"""Bounded short-pulse coherence test before any target-resident echo map.

At the previously measured quiet 4.288-GHz site, find a square-pulse Rabi
turnover at gain 30000, then test two pi/2 pulses in forward and reversed
phase cycles. Interleaved zero controls and bracketing zero/pi references
make a drifting IQ baseline visible. This run does not scan for a TLS.
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
    TLSParkPi2Calibration as calibration,
    TLSPumpProbeLocalizer as localizer,
)


GAIN_DAC = 30000
DURATIONS_US = (.06, .08, .10, .12, .14, .16, .18, .20,
                .24, .28, .32, .36, .40, .48)
SHOTS = 1200
PHASE_SHOTS = 1600
PHASE_DURATIONS_US = (.04, .045, .05)
PHASE_SOURCE_SESSION = "q3_echo_fast_square_pilot_20260929T231147Z_0230fd65"


def validate_source(source):
    if (source.get("schema") != "q3.target-pi2-validation.v1" or
            source.get("status") != "complete_controls_unstable" or
            source.get("correction_sha256") != localizer.CORRECTION_SHA256):
        raise ValueError("source must be the pinned target phase validation")
    try:
        target = float(source["target_frequency_ghz"])
        gain = int(source["target_gain"])
        drive = float(source["drive_frequency_mhz"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("source lacks measured target drive") from exc
    if (target != 4.288 or gain != -20130 or
            not math.isfinite(drive) or not 4280 <= drive <= 4300):
        raise ValueError("source target drive is outside checked site")
    return target, gain, drive


def validate_phase_source(source):
    if (source.get("schema") != "q3.echo-fast-square-pilot.v1" or
            source.get("session_id") != PHASE_SOURCE_SESSION or
            source.get("status") != "complete_rabi_unresolved" or
            source.get("code_commit", "")[:8] != "75851bd6" or
            source.get("correction_sha256") != localizer.CORRECTION_SHA256):
        raise ValueError("phase-only source is not the pinned square Rabi run")
    try:
        target = float(source["target_frequency_ghz"])
        gain = int(source["target_gain"])
        drive = float(source["drive_frequency_mhz"])
        fit = fit_duration_rabi(source["duration_sweep"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("phase-only source lacks measured Rabi data") from exc
    if (target != 4.288 or gain != -20130 or drive != 4290.5 or
            not fit["valid"] or not .08 <= fit["pi_us"] <= .11 or
            not .04 <= fit["pi2_us"] <= .055):
        raise ValueError("phase-only source does not support short pi/2")
    return target, gain, drive, fit


def interpolated_zero(anchors, position):
    for (left_at, left), (right_at, right) in zip(anchors, anchors[1:]):
        if left_at <= position <= right_at:
            fraction = (position - left_at) / (right_at - left_at)
            return (1 - fraction) * complex(left) + fraction * complex(right)
    raise ValueError("duration arm is not bracketed by zero-drive controls")


def fit_duration_rabi(rows):
    points = sorted((float(row["duration_us"]), float(row["response"]),
                     float(row.get("sem", .05))) for row in rows)
    if (len(points) != len(DURATIONS_US) or
            len({duration for duration, _, _ in points}) != len(points) or
            any(not all(map(math.isfinite, point)) or point[2] <= 0
                for point in points)):
        return {"valid": False, "reason": "incomplete duration sweep"}
    times = np.asarray([row[0] for row in points])
    values = np.asarray([row[1] for row in points])
    sem = np.asarray([row[2] for row in points])
    weights = 1 / sem ** 2
    candidates = np.linspace(.08, .40, 3201)
    basis = np.sin(np.pi * times[None, :] /
                   (2 * candidates[:, None])) ** 2
    amplitude = (np.sum(weights * basis * values, axis=1) /
                 np.sum(weights * basis ** 2, axis=1))
    chi2 = np.sum(weights * (amplitude[:, None] * basis - values) ** 2,
                  axis=1)
    best = int(np.argmin(chi2))
    pi_us = float(candidates[best])
    height = float(amplitude[best])
    post_peak = values[times >= 1.5 * pi_us]
    peak_sample = values[abs(times - pi_us) <= .03]
    valid = bool(.04 <= pi_us / 2 <= .20 and height >= .65 and
                 peak_sample.size and np.max(peak_sample) >= .65 and
                 post_peak.size and np.min(post_peak) <= .70 * height and
                 chi2[best] / (len(points) - 2) <= 4)
    if not valid:
        return {"valid": False, "reason": "Rabi model lacks a resolved turnover",
                "pi_us": pi_us, "chi2": float(chi2[best])}
    return {"valid": True, "pi_us": pi_us, "pi2_us": pi_us / 2,
            "peak_response": height, "half_level": height / 2,
            "chi2": float(chi2[best]), "degrees_of_freedom": len(points) - 2}


def score_reference_bracket(ground_before, pi_before, ground_after, pi_after):
    first = complex(pi_before) - complex(ground_before)
    last = complex(pi_after) - complex(ground_after)
    sizes = (abs(first), abs(last))
    cosine = (float(np.real(last * np.conj(first)) /
                    (sizes[0] * sizes[1]))
              if min(sizes) else math.nan)
    ratio = min(sizes) / max(sizes) if max(sizes) else 0.
    return {"valid": bool(min(sizes) >= 600 and cosine >= .9 and
                          ratio >= .7),
            "before_iq_displacement": sizes[0],
            "after_iq_displacement": sizes[1],
            "axis_cosine": cosine, "contrast_ratio": ratio}


def bracketed_response(value, ground_before, pi_before,
                       ground_after, pi_after, fraction):
    if not 0 <= fraction <= 1:
        raise ValueError("phase-arm time fraction must be 0..1")
    ground = (1 - fraction) * complex(ground_before) + \
        fraction * complex(ground_after)
    pi = (1 - fraction) * complex(pi_before) + \
        fraction * complex(pi_after)
    difference = pi - ground
    if not abs(difference):
        raise ValueError("phase reference contrast vanished")
    return float(np.real((complex(value) - ground) *
                         np.conj(difference)) / abs(difference) ** 2)


def make_program(parent):
    """Play one or two short square pulses during a flat corrected hold."""
    class FastSquareProgram(parent):
        def _resident_excursion(self):
            from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
            cfg = self.cfg
            duration = float(cfg["fast_pulse_us"])
            if not .04 <= duration <= .5:
                raise ValueError("fast pulse duration outside checked range")
            phases = (0,) if cfg.get("fast_second_phase_deg") is None else (
                0, int(cfg["fast_second_phase_deg"]))
            park, target = int(cfg["ff_park_gain"]), int(cfg["ff_gain"])
            if target == park or self._t1_ff_compensation is None:
                raise ValueError("fast square pulse needs corrected target visit")
            window = len(phases) * (duration + .01)
            pre = float(cfg["opx_resident_pre_us"]) + self._t1_ff_settle_us
            post = float(cfg["opx_resident_post_us"])
            target_segments, recovery = ff_pulse.compensation_round_trip_segments(
                self._t1_ff_compensation, pre + window + post,
                recovery_us=self._t1_ff_predistortion_recovery_us)
            before, tail = ff_pulse.split_compensation_segments(
                target_segments, pre)
            during, after = ff_pulse.split_compensation_segments(tail, window)
            if not before or not during or not after:
                raise ValueError("correction does not cover fast-pulse window")
            held = float(before[-1][0])
            if max(abs(float(level) - held) for level, _ in during) > .0015:
                raise ValueError("correction varies during square pulses")
            ff_pulse.play_relative_compensation_segments(
                self, park, target, before)
            self.sync_all(0)
            for phase in phases:
                self.set_pulse_registers(
                    ch=cfg["qubit_ch"], style="const",
                    freq=self.freq2reg(float(cfg["opx_resident_freq_mhz"]),
                                       gen_ch=cfg["qubit_ch"]),
                    phase=self.deg2reg(phase, gen_ch=cfg["qubit_ch"]),
                    gain=int(cfg["opx_resident_gain"]),
                    length=self.us2cycles(duration,
                                          gen_ch=cfg["qubit_ch"]))
                self.pulse(ch=cfg["qubit_ch"])
                self.sync_all(self.us2cycles(.01))
            ff_pulse.play_relative_compensation_segments(
                self, park, target, after)
            ff_pulse.play_relative_compensation_segments(
                self, park, target, recovery)
            ff_pulse.play_hard_step(self, park)
            self.sync_all(0)

    return FastSquareProgram


def plan(*, phase_only=False):
    if phase_only:
        return {"hardware_access": False,
                "purpose": "test square-pulse phase contrast at 4.288 GHz",
                "source_session": PHASE_SOURCE_SESSION,
                "target_ghz": 4.288, "drive_mhz": 4290.5,
                "gain_dac": GAIN_DAC,
                "pi2_durations_us": list(PHASE_DURATIONS_US),
                "shots_per_arm": PHASE_SHOTS,
                "phase_blocks": 2, "reset_mode": "passive",
                "fresh_t1_scan": False, "duration_rescan": False,
                "wide_echo_map": False,
                "terminal": "no custom progress messages"}
    return {"hardware_access": False,
            "purpose": "check fast target-resident pulses before local echo",
            "target_ghz": 4.288, "drive_mhz": 4290.5,
            "gain_dac": GAIN_DAC, "durations_us": list(DURATIONS_US),
            "shots_per_duration": SHOTS,
            "shots_per_phase_and_reference": PHASE_SHOTS,
            "phase_blocks": 2, "reset_mode": "passive",
            "fresh_t1_scan": False, "wide_echo_map": False,
            "terminal": "no custom progress messages"}


def run(*, data_root=None, correction_json=None, source_manifest=None,
        phase_only=False):
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

    data_root = Path(data_root or localizer.DATA_ROOT)
    correction = localizer.checked_correction(data_root, correction_json)
    if source_manifest is None:
        if phase_only:
            source_manifest = (data_root / "q3" / PHASE_SOURCE_SESSION /
                               "manifest.json")
        else:
            matches = sorted((data_root / "q3").glob(
                "q3_target_pi2_validation_*/manifest.json"))
            if not matches:
                raise FileNotFoundError("no target phase validation on NAS")
            source_manifest = matches[-1]
    source_manifest = Path(source_manifest)
    source = json.loads(source_manifest.read_text(encoding="utf-8"))
    if phase_only:
        target, source_gain, drive, phase_fit = validate_phase_source(source)
    else:
        target, source_gain, drive = validate_source(source)
        phase_fit = None

    with localizer.scan_environment(correction):
        tls.QUBIT, tls.SET_YOKO, tls.outerFolder = "q3", False, str(data_root)
        five.install_scan_calibration(tls)
        base = ProductionResetSession.passive().apply(tls.BaseConfig)
        five.apply_verified_feedback_timing(base)
        if int(base["ff_park_gain"]) != -25146:
            raise RuntimeError("q3 park gain differs from verified configuration")
        dc, realized = _integer_dc_grid(wide.parameters(),
                                        np.asarray([target]), tls)
        target_gain = int(dc[0])
        if target_gain != source_gain:
            raise ValueError("target DAC differs from source phase run")
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
        session_id = (("q3_echo_fast_square_phase_" if phase_only else
                       "q3_echo_fast_square_pilot_") +
                      datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") +
                      "_" + uuid.uuid4().hex[:8])
        folder = data_root / "q3" / session_id
        folder.mkdir(parents=True, exist_ok=False)
        path = folder / "manifest.json"
        try:
            commit = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=Path(__file__).resolve().parents[4], text=True,
                stderr=subprocess.DEVNULL).strip()
        except (OSError, subprocess.CalledProcessError):
            commit = "unknown"
        manifest = {"schema": ("q3.echo-fast-square-phase.v1" if phase_only
                               else "q3.echo-fast-square-pilot.v1"),
                    "status": "running", "session_id": session_id,
                    "code_commit": commit,
                    "source_manifest": str(source_manifest),
                    "target_frequency_ghz": target,
                    "realized_frequency_ghz": float(realized[0]),
                    "target_gain": target_gain,
                    "drive_frequency_mhz": drive,
                    "gain_dac": GAIN_DAC,
                    "correction_json": str(correction),
                    "correction_sha256": localizer.CORRECTION_SHA256,
                    "plan": plan(phase_only=phase_only), "duration_sweep": [],
                    "phase_blocks": [], "phase_brackets": []}
        if phase_fit is not None:
            manifest["source_rabi_refit"] = phase_fit
        dual.checkpoint(path, manifest)
        program_class = make_program(resident.ResidentDriveProgram)
        try:
            soc, soccfg = tls.makeProxy()
            bundle = runtime_bundle(base)

            def configuration(duration, shots, *, gain=GAIN_DAC,
                              phase=None):
                arm = {"flux_ghz": target, "drive_mhz": drive,
                       "gain": int(gain), "reference_state": None,
                       "preparation_state": "g", "pre_drive_us": 30.,
                       "post_drive_us": .1, "shots": int(shots)}
                cfg = resident.arm_config(base, arm, {target: target_gain})
                count = 1 if phase is None else 2
                cfg["fast_pulse_us"] = float(duration)
                cfg["fast_second_phase_deg"] = phase
                cfg["ff_hold"] = 30. + .1 + count * (float(duration) + .01)
                return cfg

            def acquire(duration, shots, filename, *, gain=GAIN_DAC,
                        phase=None):
                cfg = configuration(duration, shots, gain=gain, phase=phase)
                program = program_class(soccfg, cfg, bundle.payload,
                                        bundle.loop)
                records = _run_program(
                    soc, program, max(30., _block_timeout_s(cfg, shots)),
                    cfg, total_shots=shots)
                if len(records) != shots:
                    raise RuntimeError(f"{filename}: incomplete IQ records")
                iq = resident.record_iq(records)
                np.savez_compressed(folder / filename,
                                    i=[r.i for r in records],
                                    q=[r.q for r in records])
                return iq

            def collect_phase_cycles(pi_us, pi2_us):
                zero_before = acquire(pi2_us, PHASE_SHOTS,
                                       "zero_b0_pre.npz", gain=0, phase=0)
                pi_before = acquire(pi_us, PHASE_SHOTS, "pi_b0_pre.npz")
                brackets_valid = True
                for block, phases in enumerate(((0, 90, 180, 270),
                                                (270, 180, 90, 0))):
                    raw = [(phase, acquire(
                        pi2_us, PHASE_SHOTS,
                        f"phase_block_{block}_phase_{phase}.npz",
                        phase=phase)) for phase in phases]
                    zero_after = acquire(pi2_us, PHASE_SHOTS,
                                          f"zero_b{block}_post.npz",
                                          gain=0, phase=0)
                    pi_after = acquire(pi_us, PHASE_SHOTS,
                                        f"pi_b{block}_post.npz")
                    refs = (zero_before.mean(), pi_before.mean(),
                            zero_after.mean(), pi_after.mean())
                    bracket = score_reference_bracket(*refs)
                    brackets_valid &= bracket["valid"]
                    values = {}
                    for position, (phase, iq) in enumerate(raw):
                        values[phase] = bracketed_response(
                            iq.mean(), *refs, fraction=(position + 1) / 5)
                    manifest["phase_blocks"].append(values)
                    manifest["phase_brackets"].append({
                        **bracket,
                        "reference_iq": [[float(z.real), float(z.imag)]
                                         for z in refs]})
                    dual.checkpoint(path, manifest)
                    zero_before, pi_before = zero_after, pi_after
                gate = calibration.phase_circle_gate(
                    *manifest["phase_blocks"], ground=0., pi=1.)
                manifest["two_pulse_gate"] = gate
                manifest["status"] = (
                    "complete_calibrated" if gate["valid"] and brackets_valid
                    else "complete_controls_unstable")
                dual.checkpoint(path, manifest)
                return path

            first_duration = (.04 if phase_only else DURATIONS_US[0])
            last_duration = (.05 if phase_only else DURATIONS_US[-1])
            program_class(soccfg, configuration(first_duration, SHOTS),
                          bundle.payload, bundle.loop)
            program_class(soccfg, configuration(last_duration, SHOTS,
                                                 phase=180),
                          bundle.payload, bundle.loop)
            manifest["compiled_pulse_edges"] = True
            dual.checkpoint(path, manifest)

            if phase_only:
                pi_us = phase_fit["pi_us"]
                zero_before = acquire(pi_us, PHASE_SHOTS,
                                       "zero_local_pre.npz", gain=0)
                pi_before = acquire(pi_us, PHASE_SHOTS,
                                     "pi_local_pre.npz")
                local = [(duration, acquire(
                    duration, PHASE_SHOTS,
                    f"pi2_local_{round(duration * 1000):03d}ns.npz"))
                         for duration in PHASE_DURATIONS_US]
                zero_after = acquire(pi_us, PHASE_SHOTS,
                                      "zero_local_post.npz", gain=0)
                pi_after = acquire(pi_us, PHASE_SHOTS,
                                    "pi_local_post.npz")
                refs = (zero_before.mean(), pi_before.mean(),
                        zero_after.mean(), pi_after.mean())
                bracket = score_reference_bracket(*refs)
                manifest["local_reference_bracket"] = bracket
                if not bracket["valid"]:
                    manifest["status"] = "complete_controls_unstable"
                    dual.checkpoint(path, manifest)
                    return path
                candidates = []
                for position, (duration, iq) in enumerate(local):
                    fraction = (position + 1) / 4
                    value = bracketed_response(iq.mean(), *refs,
                                               fraction=fraction)
                    contrast = ((1 - fraction) * (refs[1] - refs[0]) +
                                fraction * (refs[3] - refs[2]))
                    projected = (np.real(iq * np.conj(contrast)) /
                                 abs(contrast) ** 2)
                    sem = float(np.std(projected, ddof=1) /
                                math.sqrt(iq.size))
                    candidates.append({"duration_us": duration,
                                       "response": value, "shot_sem": sem})
                manifest["local_pi2_check"] = candidates
                chosen = min(candidates,
                             key=lambda row: abs(row["response"] - .5))
                manifest["chosen_pi2"] = chosen
                dual.checkpoint(path, manifest)
                if abs(chosen["response"] - .5) > max(
                        .15, 2.5 * chosen["shot_sem"]):
                    manifest["status"] = "complete_midpoint_unstable"
                    dual.checkpoint(path, manifest)
                    return path
                return collect_phase_cycles(pi_us, chosen["duration_us"])

            step = 0
            zero = acquire(.28, SHOTS, "zero_sweep_0.npz", gain=0)
            anchors = [(step, zero.mean())]
            observations = []
            for index, duration in enumerate(DURATIONS_US):
                step += 1
                iq = acquire(duration, SHOTS,
                             f"duration_{round(duration * 1000):03d}ns.npz")
                observations.append((duration, iq, step))
                manifest["duration_sweep"].append({
                    "duration_us": duration,
                    "mean_i": float(iq.real.mean()),
                    "mean_q": float(iq.imag.mean())})
                if (index + 1) % 4 == 0 or index == len(DURATIONS_US) - 1:
                    step += 1
                    control = acquire(.28, SHOTS,
                                      f"zero_sweep_{index + 1}.npz", gain=0)
                    anchors.append((step, control.mean()))
                dual.checkpoint(path, manifest)
            manifest["sweep_zero_anchors"] = [
                {"step": at, "mean_i": float(value.real),
                 "mean_q": float(value.imag)} for at, value in anchors]
            strongest = max(observations, key=lambda row: abs(
                row[1].mean() - interpolated_zero(anchors, row[2])))
            provisional = (strongest[1].mean() -
                           interpolated_zero(anchors, strongest[2]))
            manifest["strongest_duration_us"] = strongest[0]
            manifest["strongest_iq_displacement"] = abs(provisional)
            dual.checkpoint(path, manifest)
            if abs(provisional) < 600:
                manifest["status"] = "complete_no_fast_drive"
                dual.checkpoint(path, manifest)
                return path
            repeated = acquire(strongest[0], SHOTS, "strongest_repeat.npz")
            repeat_zero = acquire(.28, SHOTS, "zero_repeat_post.npz", gain=0)
            difference = repeated.mean() - (anchors[-1][1] +
                                            repeat_zero.mean()) / 2
            cosine = (float(np.real(difference * np.conj(provisional)) /
                            (abs(difference) * abs(provisional)))
                      if abs(difference) else math.nan)
            manifest["strongest_repeat"] = {
                "iq_displacement": abs(difference), "axis_cosine": cosine}
            dual.checkpoint(path, manifest)
            if abs(difference) < 600 or cosine < .7:
                manifest["status"] = "complete_fast_drive_unstable"
                dual.checkpoint(path, manifest)
                return path
            axis, scale = difference / abs(difference), abs(difference)
            zero_sem = (float(np.std(np.real(repeat_zero * np.conj(axis)),
                                     ddof=1)) /
                        math.sqrt(repeat_zero.size) / scale)
            peak_sem = (float(np.std(np.real(repeated * np.conj(axis)),
                                     ddof=1)) /
                        math.sqrt(repeated.size) / scale)

            def response(iq, baseline):
                values = np.real((np.asarray(iq) - baseline) *
                                 np.conj(axis)) / scale
                average = float(np.mean(values))
                shot_sem = float(np.std(values, ddof=1) /
                                 math.sqrt(values.size))
                sem = math.sqrt(shot_sem ** 2 +
                                ((1 - average) * zero_sem) ** 2 +
                                (average * peak_sem) ** 2)
                return {"mean": average, "sem": sem}

            for row, (_, iq, at) in zip(manifest["duration_sweep"],
                                         observations):
                row.update(response(iq, interpolated_zero(anchors, at)))
                row["response"] = row.pop("mean")
            fit = fit_duration_rabi(manifest["duration_sweep"])
            manifest["duration_fit"] = fit
            dual.checkpoint(path, manifest)
            if not fit["valid"]:
                manifest["status"] = "complete_rabi_unresolved"
                dual.checkpoint(path, manifest)
                return path

            pre_zero = acquire(.28, PHASE_SHOTS,
                               "zero_pi2_pre.npz", gain=0)
            pi2_iq = acquire(fit["pi2_us"], PHASE_SHOTS,
                              "pi2_independent.npz")
            post_zero = acquire(.28, PHASE_SHOTS,
                                "zero_pi2_post.npz", gain=0)
            pi2 = response(pi2_iq, (pre_zero.mean() + post_zero.mean()) / 2)
            manifest["pi2_independent"] = pi2
            dual.checkpoint(path, manifest)
            if abs(pi2["mean"] - fit["half_level"]) > max(
                    .20, 2.5 * pi2["sem"]):
                manifest["status"] = "complete_midpoint_unstable"
                dual.checkpoint(path, manifest)
                return path

            return collect_phase_cycles(fit["pi_us"], fit["pi2_us"])
        except BaseException as exc:
            manifest["status"] = "failed"
            manifest["error"] = f"{type(exc).__name__}: {exc}"
            dual.checkpoint(path, manifest)
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--data-root")
    parser.add_argument("--correction-json")
    parser.add_argument("--source-manifest")
    parser.add_argument("--phase-only", action="store_true",
                        help="continue the pinned square Rabi run at pi/2")
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(plan(phase_only=args.phase_only), indent=2))
    else:
        run(data_root=args.data_root,
            correction_json=args.correction_json,
            source_manifest=args.source_manifest,
            phase_only=args.phase_only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
