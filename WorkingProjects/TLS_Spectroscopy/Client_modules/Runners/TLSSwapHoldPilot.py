"""Probe short-time q3 exchange at the persistent upper loss feature.

Prepare g/e at the park point, visit an anchored feature near 4.144 GHz or
its clean upper control for 0.1..6 us, apply the complete corrected return,
and read out once. Both site and dwell order reverse on the second pass.
Short dwell points include flux settling and cannot alone prove coherent
qubit-TLS exchange. No pump, active reset, or target microwave pulse is used.
"""

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
from statistics import mean, median
import uuid

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSPumpProbeAdaptiveParkPump as adaptive,
    TLSPumpProbeLocalizer as localizer,
    TLSPumpProbeProtocolCheck as protocol,
    TLSPumpProbeResidentDrive as resident,
    TLSPumpProbeResidentProbe as probe,
    TLSPumpProbeWidePassiveScan as wide,
)


ANCHOR_GHZ = 4.144
CONTROL_OFFSET_GHZ = 0.014
HOLDS_US = (0.1, 0.2, 0.35, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0)
SHOTS = 600
REFERENCE_SHOTS = 400


def select_anchored_feature(rows):
    """Select the upper feature, even when a lower dip becomes deeper."""
    indexed = {round(float(row["target_frequency_ghz"]), 3): row
               for row in rows}
    candidates = []
    for index in range(-2, 3):
        center = round(ANCHOR_GHZ + index * 0.001, 3)
        groups = {
            "feature": [round(center + i * 0.001, 3) for i in (-1, 0, 1)],
            "left": [round(center - i * 0.001, 3) for i in (4, 5, 6)],
            "right": [round(center + i * 0.001, 3) for i in (4, 5, 6)],
            "control": [round(center + CONTROL_OFFSET_GHZ + i * 0.001, 3)
                        for i in (-1, 0, 1)],
        }
        if any(f not in indexed for group in groups.values() for f in group):
            continue
        depths = {}
        control_levels = {}
        for direction in ("", "up", "down"):
            values = {name: [adaptive._survival(indexed[f], direction)
                             for f in frequencies]
                      for name, frequencies in groups.items()}
            if not all(math.isfinite(value)
                       for group in values.values() for value in group):
                break
            feature = mean(values["feature"])
            depths[direction or "combined"] = min(
                median(values["left"]) - feature,
                median(values["right"]) - feature)
            control_levels[direction or "combined"] = (
                mean(values["control"]) - feature)
        if len(depths) != 3:
            continue
        if (depths["combined"] < 0.15 or
                min(depths["up"], depths["down"]) < 0.08):
            continue
        candidates.append({"center_ghz": center,
                           "control_ghz": round(center + CONTROL_OFFSET_GHZ, 3),
                           "depth": depths["combined"],
                           "depth_scan_up": depths["up"],
                           "depth_scan_down": depths["down"],
                           "control_survival_advantage": control_levels})
    if not candidates:
        raise ValueError("anchored upper loss feature is absent")
    selected = max(candidates, key=lambda item: item["depth"])
    if min(selected["control_survival_advantage"].values()) < 0.15:
        raise ValueError("upper control is not cleanly away from the loss feature")
    return selected


def feature_stable(pre, post):
    return resident.feature_stable(pre, post)


def program_specs(feature_ghz, control_ghz):
    specs = []
    for repeat in (0, 1):
        holds = HOLDS_US if repeat == 0 else tuple(reversed(HOLDS_US))
        sites = (("feature", feature_ghz), ("control", control_ghz))
        if repeat:
            sites = tuple(reversed(sites))
        states = ("g", "e") if repeat == 0 else ("e", "g")
        for hold in holds:
            for site, flux in sites:
                for state in states:
                    label = f"{hold:g}".replace(".", "p")
                    specs.append({
                        "name": f"r{repeat}_{site}_t{label}_{state}",
                        "repeat": repeat, "site": site,
                        "flux_ghz": float(flux), "hold_us": hold,
                        "state": state, "shots": SHOTS, "status": "pending"})
    return specs


def swap_segments(compensation, *, hold_us):
    if not math.isfinite(float(hold_us)) or hold_us < 0.05:
        raise ValueError("swap hold must be finite and at least 0.05 us")
    target, recovery = ff_pulse.compensation_round_trip_segments(
        compensation, hold_us, recovery_us=40.0)
    if (abs(sum(duration for _, duration in target) - hold_us) > 1e-6 or
            sum(duration for _, duration in recovery) < 40.0 - 1e-6):
        raise ValueError("swap hold needs a complete corrected target/return")
    return target, recovery


class SwapHoldProgram(resident.ResidentDriveProgram):
    """One park-prepared g/e shot, with no target microwave pulse."""

    def _resident_excursion(self):
        if self._t1_ff_compensation is None:
            raise ValueError("swap hold requires the pinned flux correction")
        cfg = self.cfg
        target, recovery = swap_segments(
            self._t1_ff_compensation, hold_us=float(cfg["opx_swap_hold_us"]))
        park = float(cfg["ff_park_gain"])
        gain = float(cfg["ff_gain"])
        ff_pulse.play_relative_compensation_segments(self, park, gain, target)
        self.sync_all(0)
        ff_pulse.play_relative_compensation_segments(self, park, gain, recovery)
        ff_pulse.play_hard_step(self, park)
        self.sync_all(0)


def arm_config(base, arm, dc_lookup):
    cfg = resident.arm_config(base, {
        "flux_ghz": arm["flux_ghz"],
        "drive_mhz": 1000.0 * arm["flux_ghz"],
        "gain": 0, "preparation_state": arm["state"],
        "reference_state": None,
        "pre_drive_us": 0.05,
        "post_drive_us": arm["hold_us"],
        "shots": arm["shots"],
    }, dc_lookup)
    cfg["opx_swap_hold_us"] = float(arm["hold_us"])
    cfg["ff_hold"] = float(arm["hold_us"])
    return cfg


def plan():
    return {"hardware_access": False, "reset_mode": "passive",
            "feature": "anchored upper loss near 4.144 GHz",
            "control_offset_mhz": 14.0,
            "dwell_us": list(HOLDS_US),
            "orders": ["forward", "reverse"],
            "programs": 88, "shots_per_program": SHOTS,
            "pulse": "park pi for excited arm, zero-gain matched pulse for ground",
            "full_return_before_readout_us": 40.0,
            "raw_iq_saved": True,
            "interpretation": "look for reproducible nonmonotonic exchange; "
                              "early dwells also include flux settling"}


def run(*, data_root=localizer.DATA_ROOT, correction_json=None):
    data_root = Path(data_root)
    correction = localizer.checked_correction(data_root, correction_json)
    scout = localizer.run(
        data_root=data_root, correction_json=correction,
        parameter_overrides={**adaptive.scout_parameters(phase="pre"),
                             "output_suffix": "TLS_SwapHold_Pilot_Scout_pre"})
    selected = select_anchored_feature(adaptive.read_scout(scout))
    center, control = selected["center_ghz"], selected["control_ghz"]
    print(f"[swap-hold] feature={center:.3f} GHz; clean upper "
          f"control={control:.3f} GHz", flush=True)

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
        grid = np.asarray([center, control], dtype=float)
        dc, realized = _integer_dc_grid(wide.parameters(), grid, tls)
        dc_lookup = {float(f): int(g) for f, g in zip(grid, dc)}
        compensation = tls._load_correction(str(correction), str(data_root))
        for hold in HOLDS_US:
            swap_segments(compensation, hold_us=hold)
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
        session_id = ("q3_tls_swap_hold_" +
                      datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") +
                      "_" + uuid.uuid4().hex[:8])
        folder = data_root / "q3" / session_id
        folder.mkdir(parents=True, exist_ok=False)
        path = folder / "manifest.json"
        refs = (probe.reference_arms(center, phase="pre") +
                probe.reference_arms(center, phase="post"))
        for ref in refs:
            ref.update(shots=REFERENCE_SHOTS, status="pending")
        manifest = {"schema": "q3.tls-swap-hold.v1",
                    "status": "running", "session_id": session_id,
                    "code_commit": os.environ.get("Q3_CODE_COMMIT", "unknown"),
                    "correction_json": str(correction),
                    "correction_sha256": localizer.CORRECTION_SHA256,
                    "scout_csv": str(scout), "selected": selected,
                    "center_ghz": center, "control_ghz": control,
                    "dc_lookup": dc_lookup, "realized_ghz": realized.tolist(),
                    "plan": plan(), "references": refs,
                    "programs": program_specs(center, control)}
        protocol.checkpoint(path, manifest)
        print(f"[swap-hold] manifest={path}", flush=True)
        raw_refs = {}
        axis = None
        try:
            soc, soccfg = tls.makeProxy()
            bundle = runtime_bundle(base)
            for arm in manifest["programs"]:
                if arm["repeat"] != 0 or arm["hold_us"] not in (
                        HOLDS_US[0], HOLDS_US[-1]):
                    continue
                SwapHoldProgram(soccfg, arm_config(base, arm, dc_lookup),
                                bundle.payload, bundle.loop)
            for ref in refs:
                resident.ResidentDriveProgram(
                    soccfg, resident.arm_config(base, ref, dc_lookup),
                    bundle.payload, bundle.loop)
            manifest["preflight_complete"] = True
            protocol.checkpoint(path, manifest)

            def acquire_ref(ref):
                nonlocal axis
                cfg = resident.arm_config(base, ref, dc_lookup)
                ref["status"] = "acquiring"
                protocol.checkpoint(path, manifest)
                program = resident.ResidentDriveProgram(
                    soccfg, cfg, bundle.payload, bundle.loop)
                records = _run_program(
                    soc, program, max(30.0, _block_timeout_s(cfg, REFERENCE_SHOTS)),
                    cfg, total_shots=REFERENCE_SHOTS)
                if len(records) != REFERENCE_SHOTS:
                    raise RuntimeError(f"{ref['name']}: incomplete reference IQ")
                raw_refs[ref["name"]] = records
                raw_path = folder / f"{ref['name']}.npz"
                np.savez_compressed(raw_path, i=[r.i for r in records],
                                    q=[r.q for r in records])
                ref["raw_npz"] = str(raw_path)
                if ref["name"] == "ref_e_pre":
                    axis = resident.fit_axis(
                        resident.record_iq(raw_refs["ref_g_pre"]),
                        resident.record_iq(records))
                    manifest["pre_readout_axis"] = axis
                    if not axis["valid"]:
                        raise RuntimeError("pre-run readout reference invalid")
                if axis is not None:
                    ref["excited_fraction_pre_axis"] = resident.classify(records, axis)
                ref["status"] = "complete"
                protocol.checkpoint(path, manifest)

            for ref in refs[:4]:
                print(f"[swap-hold] {ref['name']}", flush=True)
                acquire_ref(ref)
            early = {}
            for index, arm in enumerate(manifest["programs"]):
                print(f"[swap-hold] {index+1}/{len(manifest['programs'])} "
                      f"{arm['name']}", flush=True)
                arm["status"] = "acquiring"
                protocol.checkpoint(path, manifest)
                cfg = arm_config(base, arm, dc_lookup)
                program = SwapHoldProgram(
                    soccfg, cfg, bundle.payload, bundle.loop)
                records = _run_program(
                    soc, program, max(30.0, _block_timeout_s(cfg, SHOTS)),
                    cfg, total_shots=SHOTS)
                if len(records) != SHOTS:
                    raise RuntimeError(f"{arm['name']}: incomplete raw IQ")
                raw_path = folder / f"{arm['name']}.npz"
                np.savez_compressed(raw_path, i=[r.i for r in records],
                                    q=[r.q for r in records])
                arm["raw_npz"] = str(raw_path)
                arm["excited_fraction_pre_axis"] = resident.classify(records, axis)
                arm["status"] = "complete"
                protocol.checkpoint(path, manifest)
                if index < 4:
                    early[(arm["site"], arm["state"])] = (
                        arm["excited_fraction_pre_axis"])
                if index == 3:
                    contrasts = {site: early[(site, "e")] - early[(site, "g")]
                                 for site in ("feature", "control")}
                    manifest["early_transfer_contrast"] = contrasts
                    protocol.checkpoint(path, manifest)
                    if min(contrasts.values()) < 0.15:
                        raise RuntimeError(
                            f"early prepared excitation is too weak: {contrasts}")

            for ref in refs[4:]:
                print(f"[swap-hold] {ref['name']}", flush=True)
                acquire_ref(ref)
            manifest["post_readout_score"] = resident.score_axis(
                axis, resident.record_iq(raw_refs["ref_g_post"]),
                resident.record_iq(raw_refs["ref_e_post"]))
            manifest["transfer_control"] = {
                phase: {"ground": resident.classify(
                            raw_refs[f"ref_transfer_g_{phase}"], axis),
                        "excited": resident.classify(
                            raw_refs[f"ref_transfer_e_{phase}"], axis)}
                for phase in ("pre", "post")}
            for item in manifest["transfer_control"].values():
                item["usable"] = resident.transfer_usable(item["ground"],
                                                           item["excited"])
            contrasts = {}
            for repeat in (0, 1):
                for site in ("feature", "control"):
                    by_key = {(arm["hold_us"], arm["state"]):
                              arm["excited_fraction_pre_axis"]
                              for arm in manifest["programs"]
                              if arm["repeat"] == repeat and arm["site"] == site}
                    contrasts[f"r{repeat}_{site}"] = {
                        str(hold): by_key[(hold, "e")] - by_key[(hold, "g")]
                        for hold in HOLDS_US}
            manifest["survival_contrasts"] = contrasts
            post_scout = localizer.run(
                data_root=data_root, correction_json=correction,
                parameter_overrides={**adaptive.scout_parameters(phase="post"),
                                     "output_suffix": "TLS_SwapHold_Pilot_Scout_post"})
            manifest["post_scout_csv"] = str(post_scout)
            try:
                manifest["post_selected"] = select_anchored_feature(
                    adaptive.read_scout(post_scout))
            except ValueError as exc:
                manifest["post_selection_error"] = str(exc)
            manifest["feature_stable"] = (
                feature_stable(selected, manifest["post_selected"])
                if "post_selected" in manifest else False)
            valid = (manifest["post_readout_score"]["valid"] and
                     all(x["usable"] for x in manifest["transfer_control"].values())
                     and manifest["feature_stable"])
            manifest["status"] = "complete" if valid else "complete_controls_unstable"
            protocol.checkpoint(path, manifest)
            print(f"[swap-hold] {manifest['status']}: {path}", flush=True)
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
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(plan(), indent=2))
    else:
        run(data_root=args.data_root, correction_json=args.correction_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
