"""Two-readout qubit-mediated pump/probe pilot at a freshly scouted q3 feature.

One park pi followed by a 20-us visit to the loss feature loads it without a
parked microwave tone. A first park readout records the qubit's state; the
second, independently prepared qubit visits the feature for 2 us and is read
again. Offline ground heralding rejects shots with excitation left in the
qubit. Cold loading and off-feature loading are matched controls. Both readouts
and all paired raw IQ are retained. This tests return from population that
survives the compensated flux return and first readout; a null does not rule
out a shorter-lived TLS or an incoherent absorber.

This runner is experimental and does not change the production TLS scan.
"""

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import uuid

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSPumpProbeAdaptiveParkPump as adaptive,
    TLSPumpProbeLocalizer as localizer,
    TLSPumpProbeProtocolCheck as protocol,
    TLSPumpProbeWidePassiveScan as wide,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.programs import (
    OPXResetT1Program, _pulse_pi_and_align,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.records import signed32


SHOTS = 400
PUMP_US = 20.0
PROBE_US = 2.0
FLANK_OFFSET_GHZ = -0.014


@dataclass(frozen=True)
class PairedIQ:
    herald_i: int
    herald_q: int
    final_i: int
    final_q: int


def decode_paired_iq(words, expected_records=None):
    flat = np.asarray(words).ravel()
    if flat.size % 4:
        raise ValueError("paired IQ needs four words per shot")
    count = flat.size // 4
    if expected_records is not None and count != int(expected_records):
        raise ValueError(f"expected {expected_records} paired records; got {count}")
    signed = np.asarray([signed32(v) for v in flat], dtype=np.int64).reshape(-1, 4)
    return [PairedIQ(*(int(value) for value in row)) for row in signed]


class HeraldedPumpProbeProgram(OPXResetT1Program):
    """Experiment-only resident program; no tProc classification or feedback."""

    record_words = 4
    decode_dmem_records = staticmethod(decode_paired_iq)

    def __init__(self, soccfg, cfg, payload_calibration, loop_calibration):
        if not bool(cfg.get("opx_hard_flux_steps", False)):
            raise ValueError("paired probe requires calibrated hard flux steps")
        if not bool(cfg.get("opx_persistent_park", False)):
            raise ValueError("paired probe requires persistent qubit park")
        if bool(cfg.get("flux_predistortion_overlap_payload_readout", True)):
            raise ValueError("first readout must follow the complete flux return")
        if cfg.get("opx_reset_scheme") != "none":
            raise ValueError("paired probe has no active reset")
        for key in ("opx_herald_pump_state", "opx_herald_probe_state"):
            if cfg.get(key) not in ("g", "e"):
                raise ValueError(f"{key} must be g or e")
        for key in ("opx_herald_pump_us", "opx_herald_probe_us"):
            if not math.isfinite(float(cfg[key])) or float(cfg[key]) < 0.1:
                raise ValueError(f"{key} must be finite and at least 0.1 us")
        for key in ("ff_gain", "opx_herald_probe_gain"):
            if not -32768 <= int(cfg[key]) <= 32767:
                raise ValueError(f"{key} exceeds signed DAC range")
        super().__init__(soccfg, cfg, payload_calibration, loop_calibration)

    def _save_readout(self):
        for name in ("i", "q"):
            self.memw(self.reset_page, self.reset_regs[name], self.reset_regs["address"])
            self.mathi(self.reset_page, self.reset_regs["address"],
                       self.reset_regs["address"], "+", 1)

    def _prepare_state(self, state):
        self._set_payload_pulse(gain=0 if state == "g" else None)
        _pulse_pi_and_align(self)

    def _prepare_and_excursion(self, state, hold_us, *, after_return):
        # References must label the state *at readout*, after the long
        # compensated return. Science arms load the target before returning.
        self._prepare_state("g" if after_return else state)
        self._wait_t1_payload(float(hold_us))
        if after_return:
            self._prepare_state(state)

    def _emit_body(self):
        park_up, park_down = self._shot_park_callbacks()
        park_up()
        self._prepare_and_excursion(
            self.cfg["opx_herald_pump_state"],
            self.cfg["opx_herald_pump_us"],
            after_return=bool(self.cfg.get(
                "opx_herald_pump_prepare_after_return", False)))
        self._measure_raw()
        self._save_readout()

        # wait_all(read_delay) advances the tProc but not the pulse reference.
        # Give the second pi instruction headroom after the first accumulator.
        self.sync_all(self.us2cycles(float(self.reset_config.read_delay_us) + 10.0))
        pump_gain = self.cfg["ff_gain"]
        try:
            self.cfg["ff_gain"] = self.cfg["opx_herald_probe_gain"]
            self._prepare_and_excursion(
                self.cfg["opx_herald_probe_state"],
                self.cfg["opx_herald_probe_us"],
                after_return=bool(self.cfg.get(
                    "opx_herald_probe_prepare_after_return", False)))
        finally:
            self.cfg["ff_gain"] = pump_gain
        self._measure_raw()
        self._save_readout()
        park_down()
        self.sync_all(self.us2cycles(float(self.reset_config.inter_shot_delay_us)))


def reference_arms(center_ghz, *, phase):
    return [
        {"name": f"{name}_{phase}", "pump_state": pump_state,
         "probe_state": probe_state, "pump_ghz": center_ghz,
         "probe_ghz": center_ghz, "pump_us": 0.1,
         "probe_us": 0.1,
         "pump_prepare_after_return": True,
         "probe_prepare_after_return": True}
        for name, pump_state, probe_state in (
            ("ref_g", "g", "g"),
            ("ref_e", "e", "g"),
            ("ref_final_e", "g", "e"),
        )
    ]


def science_arms(*, center_ghz, flank_ghz):
    base = []
    for probe_state in ("g", "e"):
        for loading, pump_state, pump_ghz in (
            ("hot_on", "e", center_ghz),
            ("cold_on", "g", center_ghz),
            ("hot_off", "e", flank_ghz),
        ):
            base.append({"name": f"{loading}_{probe_state}",
                         "pump_state": pump_state, "probe_state": probe_state,
                         "pump_ghz": pump_ghz, "probe_ghz": center_ghz,
                         "pump_us": PUMP_US, "probe_us": PROBE_US,
                         "pump_prepare_after_return": False,
                         "probe_prepare_after_return": False})
    return base + [{**arm, "name": arm["name"] + "_repeat"}
                   for arm in reversed(base)]


def fit_readout_axis(ground_iq, excited_iq):
    ground = np.asarray(ground_iq, dtype=complex).reshape(-1)
    excited = np.asarray(excited_iq, dtype=complex).reshape(-1)
    if ground.size < 50 or excited.size < 50:
        raise RuntimeError("reference contrast: too few readout shots")
    delta = np.median(excited.real) - np.median(ground.real) + 1j * (
        np.median(excited.imag) - np.median(ground.imag))
    if not np.isfinite(delta) or abs(delta) < 1e-9:
        raise RuntimeError("reference contrast: IQ centroids overlap")
    theta = float(np.angle(delta))
    g = np.real(ground * np.exp(-1j * theta))
    e = np.real(excited * np.exp(-1j * theta))
    threshold = float((np.median(g) + np.median(e)) / 2.0)
    fidelity = float((np.mean(g < threshold) + np.mean(e > threshold)) / 2.0)
    # The lower excited tail bounds false-ground heralding. An overlapping
    # distribution must abort rather than manufacture a conditional signal.
    # With strict '<', the order statistic at floor(5% * N) admits at most
    # that many excited-reference shots, even for small conditioned samples.
    ground_limit = float(np.sort(e)[int(np.floor(0.05 * e.size))])
    accept = float(np.mean(g < ground_limit))
    false_ground = float(np.mean(e < ground_limit))
    if fidelity < 0.60 or accept < 0.20:
        raise RuntimeError(
            f"reference contrast: fidelity={fidelity:.3f}, "
            f"ground_accept={accept:.3f}, false_ground={false_ground:.3f}")
    return {"theta_rad": theta, "threshold": threshold,
            "ground_limit": ground_limit, "fidelity": fidelity,
            "ground_accept": accept, "false_ground": false_ground}


def _projection(iq, axis):
    return np.real(np.asarray(iq, dtype=complex) *
                   np.exp(-1j * axis["theta_rad"]))


def confident_ground(iq, axis):
    return _projection(iq, axis) < axis["ground_limit"]


def excited(iq, axis):
    return _projection(iq, axis) > axis["threshold"]


def record_iq(records, prefix):
    return np.asarray([complex(getattr(r, prefix + "_i"),
                               getattr(r, prefix + "_q")) for r in records])


def evaluate_reference_axis(axis, ground_iq, excited_iq):
    """Score an already fixed classifier on independent labeled readouts."""
    g = _projection(ground_iq, axis).reshape(-1)
    e = _projection(excited_iq, axis).reshape(-1)
    if g.size < 50 or e.size < 50:
        return {"valid": False, "ground_shots": int(g.size),
                "excited_shots": int(e.size), "reason": "too few reference shots"}
    ground_accept = float(np.mean(g < axis["ground_limit"]))
    false_ground = float(np.mean(e < axis["ground_limit"]))
    fidelity = float((np.mean(g < axis["threshold"]) +
                      np.mean(e > axis["threshold"])) / 2.0)
    # One-sided 95% Wilson upper bound reports the finite-sample uncertainty;
    # the pilot validity gate uses the independent empirical rate.
    z = 1.645
    n = int(e.size)
    denominator = 1.0 + z * z / n
    upper = ((false_ground + z * z / (2 * n)) +
             z * math.sqrt(false_ground * (1.0 - false_ground) / n +
                           z * z / (4 * n * n))) / denominator
    return {"valid": bool(fidelity >= 0.60 and ground_accept >= 0.20 and
                           false_ground <= 0.10),
            "ground_shots": int(g.size), "excited_shots": n,
            "fidelity": fidelity, "ground_accept": ground_accept,
            "false_ground": false_ground,
            "false_ground_upper_95": float(upper)}


def validate_pair_against_axes(axes, ground_records, excited_records,
                               final_excited_records):
    """Check the frozen pre-run axes on post-run data without refitting."""
    herald = evaluate_reference_axis(
        axes["herald"], record_iq(ground_records, "herald"),
        record_iq(excited_records, "herald"))
    ground_mask = confident_ground(record_iq(ground_records, "herald"),
                                   axes["herald"])
    excited_mask = confident_ground(record_iq(final_excited_records, "herald"),
                                    axes["herald"])
    final = evaluate_reference_axis(
        axes["final"], record_iq(ground_records, "final")[ground_mask],
        record_iq(final_excited_records, "final")[excited_mask])
    return {"valid": bool(herald["valid"] and final["valid"]),
            "herald": herald, "final": final}


def calibrate_pair(ground_records, excited_records, final_excited_records,
                   *, enforce_holdout=True):
    ground_herald = record_iq(ground_records, "herald")
    excited_herald = record_iq(excited_records, "herald")
    holdout = []
    for training, validation in ((slice(None, None, 2), slice(1, None, 2)),
                                 (slice(1, None, 2), slice(None, None, 2))):
        try:
            trial_axis = fit_readout_axis(ground_herald[training],
                                          excited_herald[training])
            report = evaluate_reference_axis(
                trial_axis, ground_herald[validation], excited_herald[validation])
        except RuntimeError as exc:
            if enforce_holdout:
                raise
            report = {"valid": False, "reason": str(exc)}
        holdout.append(report)
        if enforce_holdout and not report["valid"]:
            raise RuntimeError(f"independent herald reference rejected: {report}")
    herald_axis = fit_readout_axis(ground_herald, excited_herald)
    ground_mask = confident_ground(record_iq(ground_records, "herald"), herald_axis)
    excited_mask = confident_ground(
        record_iq(final_excited_records, "herald"), herald_axis)
    final_axis = fit_readout_axis(
        record_iq(ground_records, "final")[ground_mask],
        record_iq(final_excited_records, "final")[excited_mask])
    return {"herald": herald_axis, "final": final_axis,
            "herald_holdout": holdout}


def assess_pre_references(ground_records, excited_records,
                          final_excited_records):
    """Retain raw-acquisition progress even if offline heralding is uncertain."""
    try:
        axes = calibrate_pair(ground_records, excited_records,
                              final_excited_records, enforce_holdout=False)
    except RuntimeError as exc:
        return {"axes": None, "valid": False, "error": str(exc)}
    return {"axes": axes,
            "valid": all(report["valid"] for report in axes["herald_holdout"]),
            "error": None}


def summarize_records(records, axes):
    herald = confident_ground(record_iq(records, "herald"), axes["herald"])
    final = excited(record_iq(records, "final"), axes["final"])
    accepted = int(np.count_nonzero(herald))
    return {"shots": len(records), "herald_ground_shots": accepted,
            "herald_ground_fraction": float(np.mean(herald)),
            "final_excited_all": float(np.mean(final)),
            "final_excited_given_ground": (
                float(np.mean(final[herald])) if accepted else None)}


def finalize_arm_summaries(arms, *, controls_valid):
    for arm in arms:
        summary = arm.get("summary")
        if summary is None:
            continue
        summary["interpretation_valid"] = bool(controls_valid)
        if not controls_valid:
            summary["final_excited_given_ground"] = None


def feature_stability(pre_selected, post_selected):
    shift_mhz = round(1000.0 * (float(post_selected["center_ghz"]) -
                                  float(pre_selected["center_ghz"])), 3)
    return {"center_shift_mhz": shift_mhz, "stable": abs(shift_mhz) <= 1.0}


def plan():
    return {"hardware_access": False, "reset_mode": "passive",
            "pump_mechanism": "park pi then flux visit at selected loss feature",
            "pump_us": PUMP_US, "probe_us": PROBE_US,
            "probe_states": ["g", "e"], "shots_per_arm": SHOTS,
            "reference_arms": 6, "science_arms": 12,
            "pre_and_post_loss_scouts": True,
            "flank_offset_mhz": 1000 * FLANK_OFFSET_GHZ,
            "readouts_per_shot": 2,
            "first_readout_selection": (
                "offline confident ground only when independent references validate; "
                "always save paired raw IQ"),
            "flux_return_before_each_readout_us": 40.0,
            "interpretation_limit": "no sensitivity to TLS population lost before first readout",
            "note": __doc__}


def arm_config(base, arm, dc_lookup):
    cfg = dict(base)
    cfg.update({"ff_gain": dc_lookup[arm["pump_ghz"]],
                "opx_herald_probe_gain": dc_lookup[arm["probe_ghz"]],
                "ff_hold": max(arm["pump_us"], arm["probe_us"]),
                "opx_herald_pump_us": arm["pump_us"],
                "opx_herald_probe_us": arm["probe_us"],
                "opx_herald_pump_state": arm["pump_state"],
                "opx_herald_probe_state": arm["probe_state"],
                "opx_herald_pump_prepare_after_return": arm[
                    "pump_prepare_after_return"],
                "opx_herald_probe_prepare_after_return": arm[
                    "probe_prepare_after_return"],
                "shots": SHOTS, "reps": SHOTS})
    return cfg


def run(*, data_root=localizer.DATA_ROOT, correction_json=None):
    data_root = Path(data_root)
    correction = localizer.checked_correction(data_root, correction_json)
    pre_scout = localizer.run(
        data_root=data_root, correction_json=correction,
        parameter_overrides={**adaptive.scout_parameters(phase="pre"),
                             "output_suffix": "TLS_PumpProbe_Heralded_Scout"})
    selected = adaptive.select_loss_feature(adaptive.read_scout(pre_scout))
    center = round(float(selected["center_ghz"]), 3)
    flank = round(center + FLANK_OFFSET_GHZ, 3)
    print(f"[heralded] feature {center:.3f} GHz depth={selected['depth']:.3f}; "
          f"control {flank:.3f} GHz", flush=True)

    with localizer.scan_environment(correction):
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
            FivePointApplesToApples as five,
            TLSSpectroscopy as tls,
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
            raise RuntimeError("q3 park gain differs from the verified configuration")
        tls.QUBIT, tls.SET_YOKO, tls.outerFolder = "q3", False, str(data_root)
        five.install_scan_calibration(tls)
        grid = np.asarray([center, flank], dtype=float)
        dc, realized = _integer_dc_grid(wide.parameters(), grid, tls)
        dc_lookup = {float(f): int(g) for f, g in zip(grid, dc)}
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
                     "qubit_pulse_style": "arb",
                     "do_ff": True, "opx_reset_scheme": "none",
                     "opx_resident_dmem_stream": True,
                     "opx_inter_shot_delay_us": 500.0})
        session_id = ("q3_pump_probe_heralded_" +
                      datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") +
                      "_" + uuid.uuid4().hex[:8])
        folder = data_root / "q3" / session_id
        folder.mkdir(parents=True, exist_ok=False)
        manifest_path = folder / "manifest.json"
        arms = (reference_arms(center, phase="pre") +
                science_arms(center_ghz=center, flank_ghz=flank) +
                reference_arms(center, phase="post"))
        manifest = {"schema": "q3.pump-probe-heralded.v1",
                    "status": "running", "session_id": session_id,
                    "code_commit": os.environ.get("Q3_CODE_COMMIT", "unknown"),
                    "correction_json": str(correction),
                    "correction_sha256": localizer.CORRECTION_SHA256,
                    "scout_csv": str(pre_scout), "selected": selected,
                    "center_ghz": center, "flank_ghz": flank,
                    "dc_lookup": {str(k): v for k, v in dc_lookup.items()},
                    "realized_ghz": realized.tolist(),
                    "plan": plan(),
                    "arms": [{**arm, "status": "pending"} for arm in arms]}
        protocol.checkpoint(manifest_path, manifest)
        print(f"[heralded] manifest={manifest_path}", flush=True)
        soc, soccfg = tls.makeProxy()
        raw_by_name = {}
        axes = None
        bundle = runtime_bundle(base)
        try:
            for index, arm in enumerate(manifest["arms"], start=1):
                cfg = arm_config(base, arm, dc_lookup)
                print(f"[heralded] {index}/{len(arms)} {arm['name']}", flush=True)
                arm["status"] = "acquiring"
                protocol.checkpoint(manifest_path, manifest)
                program = HeraldedPumpProbeProgram(
                    soccfg, cfg, bundle.payload, bundle.loop)
                records = _run_program(
                    soc, program, max(30.0, _block_timeout_s(cfg, SHOTS)),
                    cfg, total_shots=SHOTS)
                if len(records) != SHOTS:
                    raise RuntimeError(f"{arm['name']}: received {len(records)} of {SHOTS} shots")
                raw_path = folder / f"{arm['name']}.npz"
                np.savez_compressed(raw_path,
                                    herald_i=[r.herald_i for r in records],
                                    herald_q=[r.herald_q for r in records],
                                    final_i=[r.final_i for r in records],
                                    final_q=[r.final_q for r in records])
                raw_by_name[arm["name"]] = records
                arm["raw_npz"] = str(raw_path)
                if arm["name"] == "ref_final_e_pre":
                    assessment = assess_pre_references(
                        raw_by_name["ref_g_pre"],
                        raw_by_name["ref_e_pre"], records)
                    axes = assessment["axes"]
                    manifest["pre_reference_valid"] = assessment["valid"]
                    if axes is None:
                        manifest["pre_readout_calibration_error"] = assessment["error"]
                        print(f"[heralded] readout interpretation unavailable: "
                              f"{assessment['error']}; acquiring raw IQ", flush=True)
                    else:
                        manifest["pre_readout_axes"] = axes
                        print(f"[heralded] pre readout F: first="
                              f"{axes['herald']['fidelity']:.3f}, "
                              f"second={axes['final']['fidelity']:.3f}; "
                              f"holdout_valid={assessment['valid']}", flush=True)
                if axes is not None:
                    arm["summary"] = summarize_records(records, axes)
                    arm["summary"]["interpretation_valid"] = False
                    if (not arm["name"].startswith("ref_") and
                            manifest.get("pre_reference_valid", False)):
                        s = arm["summary"]
                        print(f"[heralded] {arm['name']}: ground herald "
                              f"{s['herald_ground_shots']}/{SHOTS}, "
                              "conditional result pending post references", flush=True)
                    elif not arm["name"].startswith("ref_"):
                        print(f"[heralded] {arm['name']}: raw paired IQ saved; "
                              "conditional estimate unvalidated", flush=True)
                elif not arm["name"].startswith("ref_"):
                    print(f"[heralded] {arm['name']}: raw paired IQ saved; "
                          "no readout axis", flush=True)
                if arm["name"] == "ref_final_e_post":
                    post_assessment = assess_pre_references(
                        raw_by_name["ref_g_post"],
                        raw_by_name["ref_e_post"], records)
                    if post_assessment["axes"] is not None:
                        manifest["post_readout_axes"] = post_assessment["axes"]
                    if post_assessment["error"] is not None:
                        manifest["post_readout_calibration_error"] = (
                            post_assessment["error"])
                    manifest["post_reference_validation"] = (
                        validate_pair_against_axes(
                            axes, raw_by_name["ref_g_post"],
                            raw_by_name["ref_e_post"], records)
                        if axes is not None else
                        {"valid": False, "reason": "no pre-run readout axis"})
                arm["status"] = "complete"
                protocol.checkpoint(manifest_path, manifest)
            post_scout = localizer.run(
                data_root=data_root, correction_json=correction,
                parameter_overrides={**adaptive.scout_parameters(phase="post"),
                                     "output_suffix": "TLS_PumpProbe_Heralded_Scout_post"})
            manifest["post_scout_csv"] = str(post_scout)
            try:
                post_selected = adaptive.select_loss_feature(adaptive.read_scout(post_scout))
            except ValueError as exc:
                manifest["post_selection_error"] = str(exc)
                manifest["feature_stability"] = {"stable": False}
            else:
                manifest["post_selected"] = post_selected
                manifest["feature_stability"] = feature_stability(selected, post_selected)
            feature_stable = manifest["feature_stability"]["stable"]
            readout_stable = bool(
                manifest.get("pre_reference_valid", False) and
                manifest["post_reference_validation"]["valid"])
            finalize_arm_summaries(manifest["arms"],
                                   controls_valid=readout_stable and feature_stable)
            manifest["status"] = (
                "complete" if feature_stable and readout_stable
                else "complete_feature_unstable" if not feature_stable and readout_stable
                else "complete_readout_unstable" if feature_stable
                else "complete_controls_unstable")
            protocol.checkpoint(manifest_path, manifest)
            print(f"[heralded] {manifest['status']}: {manifest_path}", flush=True)
            return manifest_path
        except BaseException as exc:
            manifest["status"] = "failed"
            manifest["error"] = f"{type(exc).__name__}: {exc}"
            protocol.checkpoint(manifest_path, manifest)
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--data-root", type=Path, default=localizer.DATA_ROOT)
    parser.add_argument("--correction-json", type=Path)
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(plan(), indent=2))
    else:
        run(data_root=args.data_root, correction_json=args.correction_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
