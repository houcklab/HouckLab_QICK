"""Probe short-time q3 exchange at a freshly verified loss feature.

Prepare g/e at the park point, visit an anchored feature near 4.144 GHz
(falling back to 4.127 GHz if absent) or its clean control for 0.1..6 us,
apply the complete corrected return,
and read out once. Both site and dwell order reverse on the second pass.
Short dwell points include flux settling and cannot alone prove coherent
qubit-TLS exchange. No pump, active reset, or target microwave pulse is used.
"""

import argparse
import csv
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


ANCHORS = ((4.144, 0.014, 2), (4.127, -0.014, 3))
HOLDS_US = (0.1, 0.2, 0.35, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0)
SHOTS = 600
REFERENCE_SHOTS = 400


def select_anchored_feature(rows, *, preferred_center=None):
    """Prefer the upper dip, but follow the lower dip if it is the target."""
    indexed = {round(float(row["target_frequency_ghz"]), 3): row
               for row in rows}
    anchors = ANCHORS
    if preferred_center is not None:
        anchors = tuple(item for item in ANCHORS
                        if abs(item[0] - float(preferred_center)) < 0.001)
        if len(anchors) != 1:
            raise ValueError("unknown anchored feature family")
    for anchor, offset, radius in anchors:
        candidates = []
        for index in range(-radius, radius + 1):
            center = round(anchor + index * 0.001, 3)
            groups = {
                "feature": [round(center + i * 0.001, 3) for i in (-1, 0, 1)],
                "left": [round(center - i * 0.001, 3) for i in (4, 5, 6)],
                "right": [round(center + i * 0.001, 3) for i in (4, 5, 6)],
                "control": [round(center + offset + i * 0.001, 3)
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
                               "control_ghz": round(center + offset, 3),
                               "anchor_ghz": anchor,
                               "control_offset_ghz": offset,
                               "depth": depths["combined"],
                               "depth_scan_up": depths["up"],
                               "depth_scan_down": depths["down"],
                               "control_survival_advantage": control_levels})
        if not candidates:
            continue
        selected = max(candidates, key=lambda item: item["depth"])
        if min(selected["control_survival_advantage"].values()) < 0.15:
            raise ValueError("control is not cleanly away from the loss feature")
        return selected
    raise ValueError("no anchored loss feature is present")


def feature_stable(pre, post):
    return (pre["anchor_ghz"] == post["anchor_ghz"] and
            resident.feature_stable(pre, post))


def select_moving_lower_dip(rows):
    """Locate a qualified lower-band trough across multi-MHz shifts."""
    indexed = {round(float(row["target_frequency_ghz"]), 3): row
               for row in rows}
    candidates = []
    for mhz in range(4105, 4135):
        center = round(mhz / 1000.0, 3)
        control = round(center - 0.014, 3)
        groups = {name: [round(base + 0.001 * offset, 3)
                         for offset in (-1, 0, 1)]
                  for name, base in (("feature", center),
                                     ("left", center - 0.008),
                                     ("right", center + 0.008),
                                     ("control", control))}
        if any(freq not in indexed for freqs in groups.values()
               for freq in freqs):
            continue
        depths = {}
        advantages = {}
        feature_survival = None
        for direction in ("", "up", "down"):
            values = {name: [adaptive._survival(indexed[freq], direction)
                             for freq in freqs]
                      for name, freqs in groups.items()}
            if not all(math.isfinite(value) for group in values.values()
                       for value in group):
                break
            feature = mean(values["feature"])
            control_survival = mean(values["control"])
            depths[direction or "combined"] = min(
                median(values["left"]), median(values["right"])) - feature
            advantages[direction or "combined"] = control_survival - feature
            if direction == "":
                feature_survival = feature
        if (len(depths) != 3 or depths["combined"] < 0.15 or
                min(depths["up"], depths["down"]) < 0.08 or
                min(advantages.values()) < 0.15):
            continue
        candidates.append({"center_ghz": center, "control_ghz": control,
                           "anchor_ghz": 4.127,
                           "control_offset_ghz": -0.014,
                           "depth": depths["combined"],
                           "depth_scan_up": depths["up"],
                           "depth_scan_down": depths["down"],
                           "control_survival_advantage": advantages,
                           "feature_survival": feature_survival,
                           "selector": "moving_lower_band"})
    if not candidates:
        raise ValueError("no qualified moving lower-band dip")
    return max(candidates, key=lambda item: (item["depth"],
                                              -item["feature_survival"]))


def choose_feature(rows, *, follow_moving_dip=False, preferred_center=None):
    if follow_moving_dip:
        return select_moving_lower_dip(rows)
    return select_anchored_feature(rows, preferred_center=preferred_center)


def read_wide_scout(path):
    if path is None:
        raise RuntimeError("wide scout completed without a CSV")
    with Path(path).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def select_wide_candidate(rows, *, preferred_center=None):
    """Find an isolated bidirectional loss dip outside the tested 4.1-GHz band."""
    indexed = {round(float(row["target_frequency_ghz"]), 3): row
               for row in rows}
    expected = {round(3.800 + .002 * i, 3) for i in range(251)}
    if len(rows) != 251 or set(indexed) != expected:
        raise ValueError("wide candidate needs one complete 251-point pass")
    candidates = []
    for center in sorted(indexed):
        if 4.080 <= center <= 4.190:
            continue
        if (preferred_center is not None and
                abs(center - float(preferred_center)) > .004001):
            continue
        immediate = [adaptive._survival(indexed[round(center + .002 * i, 3)])
                     for i in (-1, 0, 1)
                     if round(center + .002 * i, 3) in indexed]
        if (len(immediate) != 3 or
                not all(math.isfinite(value) for value in immediate) or
                min(immediate[0], immediate[2]) - immediate[1] < .08):
            continue
        groups = {
            "feature": [round(center + .002 * i, 3) for i in (-1, 0, 1)],
            "left": [round(center - .002 * i, 3) for i in (4, 5, 6)],
            "right": [round(center + .002 * i, 3) for i in (4, 5, 6)],
        }
        if any(f not in indexed for fs in groups.values() for f in fs):
            continue
        for offset in (.014, -.014):
            control = round(center + offset, 3)
            site_groups = {**groups,
                           "control": [round(control + .002 * i, 3)
                                       for i in (-1, 0, 1)]}
            if any(f not in indexed for fs in site_groups.values()
                   for f in fs):
                continue
            depths, advantages = {}, {}
            for direction in ("", "up", "down"):
                values = {name: [adaptive._survival(indexed[f], direction)
                                 for f in fs]
                          for name, fs in site_groups.items()}
                if any(not math.isfinite(v) for vs in values.values()
                       for v in vs):
                    break
                feature = mean(values["feature"])
                depths[direction or "combined"] = min(
                    median(values["left"]), median(values["right"])) - feature
                advantages[direction or "combined"] = (
                    mean(values["control"]) - feature)
            if (len(depths) != 3 or depths["combined"] < .15 or
                    min(depths["up"], depths["down"]) < .08 or
                    min(advantages.values()) < .15):
                continue
            candidates.append({"center_ghz": center, "control_ghz": control,
                               "anchor_ghz": (float(preferred_center)
                                              if preferred_center is not None
                                              else center),
                               "control_offset_ghz": offset,
                               "depth": depths["combined"],
                               "depth_scan_up": depths["up"],
                               "depth_scan_down": depths["down"],
                               "control_survival_advantage": advantages,
                               "selector": "wide_isolated_swap_candidate"})
    if not candidates:
        raise ValueError("no qualified loss outside the previously tested band")
    return max(candidates, key=lambda x: (min(x["depth_scan_up"],
                                              x["depth_scan_down"]),
                                          x["depth"]))


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


def plan(*, follow_moving_dip=False, wide_candidate=False):
    return {"hardware_access": False, "reset_mode": "passive",
            "wide_candidate": bool(wide_candidate),
            "pre_and_post_scout_frequencies": 251 if wide_candidate else 81,
            "feature": ("fresh qualified lower-band trough, 4.105–4.134 GHz"
                        if follow_moving_dip else
                        "fresh isolated trough outside 4.080–4.190 GHz"
                        if wide_candidate else
                        "anchored upper loss near 4.144 GHz, else lower near 4.127 GHz"),
            "control_offset_mhz": ("clean ±14" if wide_candidate else
                                   -14 if follow_moving_dip else
                                   "upper +14; lower -14"),
            "dwell_us": list(HOLDS_US),
            "orders": ["forward", "reverse"],
            "programs": 88, "shots_per_program": SHOTS,
            "pulse": "park pi for excited arm, zero-gain matched pulse for ground",
            "full_return_before_readout_us": 40.0,
            "raw_iq_saved": True,
            "interpretation": "look for reproducible nonmonotonic exchange; "
                              "early dwells also include flux settling"}


def run(*, data_root=localizer.DATA_ROOT, correction_json=None,
        follow_moving_dip=False, wide_candidate=False):
    if wide_candidate and follow_moving_dip:
        raise ValueError("select one swap-hold candidate mode")
    data_root = Path(data_root)
    correction = localizer.checked_correction(data_root, correction_json)
    scout_parameters = (wide.parameters() if wide_candidate else
                        adaptive.scout_parameters(phase="pre"))
    scout = localizer.run(
        data_root=data_root, correction_json=correction,
        parameter_overrides={**scout_parameters,
                             "output_suffix": ("TLS_SwapHold_Wide_Candidate_Scout_pre"
                                               if wide_candidate else
                                               "TLS_SwapHold_Pilot_Scout_pre")})
    selected = (select_wide_candidate(read_wide_scout(scout))
                if wide_candidate else
                choose_feature(adaptive.read_scout(scout),
                               follow_moving_dip=follow_moving_dip))
    center, control = selected["center_ghz"], selected["control_ghz"]
    print(f"[swap-hold] feature={center:.3f} GHz; clean "
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
        session_id = (("q3_tls_swap_hold_wide_candidate_" if wide_candidate
                       else "q3_tls_swap_hold_moving_trace_" if follow_moving_dip
                       else "q3_tls_swap_hold_") +
                      datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") +
                      "_" + uuid.uuid4().hex[:8])
        folder = data_root / "q3" / session_id
        folder.mkdir(parents=True, exist_ok=False)
        path = folder / "manifest.json"
        refs = (probe.reference_arms(center, phase="pre") +
                probe.reference_arms(center, phase="post"))
        for ref in refs:
            ref.update(shots=REFERENCE_SHOTS, status="pending")
        manifest = {"schema": ("q3.tls-swap-hold-wide-candidate.v1"
                               if wide_candidate else
                               "q3.tls-swap-hold-moving-trace.v1"
                               if follow_moving_dip else "q3.tls-swap-hold.v1"),
                    "status": "running", "session_id": session_id,
                    "code_commit": os.environ.get("Q3_CODE_COMMIT", "unknown"),
                    "correction_json": str(correction),
                    "correction_sha256": localizer.CORRECTION_SHA256,
                    "scout_csv": str(scout), "selected": selected,
                    "center_ghz": center, "control_ghz": control,
                    "dc_lookup": dc_lookup, "realized_ghz": realized.tolist(),
                    "plan": plan(follow_moving_dip=follow_moving_dip,
                                 wide_candidate=wide_candidate),
                    "references": refs,
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
            post_parameters = (wide.parameters() if wide_candidate else
                               adaptive.scout_parameters(phase="post"))
            post_scout = localizer.run(
                data_root=data_root, correction_json=correction,
                parameter_overrides={**post_parameters,
                                     "output_suffix": (
                                         "TLS_SwapHold_Wide_Candidate_Scout_post"
                                         if wide_candidate else
                                         "TLS_SwapHold_Pilot_Scout_post")})
            manifest["post_scout_csv"] = str(post_scout)
            try:
                manifest["post_selected"] = (
                    select_wide_candidate(
                        read_wide_scout(post_scout),
                        preferred_center=selected["anchor_ghz"])
                    if wide_candidate else
                    choose_feature(adaptive.read_scout(post_scout),
                                   follow_moving_dip=follow_moving_dip,
                                   preferred_center=selected["anchor_ghz"]))
            except ValueError as exc:
                manifest["post_selection_error"] = str(exc)
            manifest["feature_stable"] = (
                feature_stable(selected, manifest["post_selected"])
                if "post_selected" in manifest else False)
            if "post_selected" in manifest:
                manifest["feature_shift_mhz"] = round(
                    1000.0 * (manifest["post_selected"]["center_ghz"] - center),
                    3)
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
    parser.add_argument("--follow-moving-dip", action="store_true",
                        help="trace a freshly located lower-band loss dip")
    parser.add_argument("--wide-candidate", action="store_true",
                        help="search 3.8–4.3 GHz for a new isolated swap candidate")
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(plan(follow_moving_dip=args.follow_moving_dip,
                              wide_candidate=args.wide_candidate), indent=2))
    else:
        run(data_root=args.data_root, correction_json=args.correction_json,
            follow_moving_dip=args.follow_moving_dip,
            wide_candidate=args.wide_candidate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
