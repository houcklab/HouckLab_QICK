"""Test whether a q3 loss feature retains excitation between two flux visits.

Prepare g/e at park, visit a freshly located loss feature or clean control,
detune briefly to park, then revisit feature or control before a single
corrected return and readout. The four visit combinations form a factorial
memory contrast. There is no intermediate readout or active reset.
"""

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import time
import uuid

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSPumpProbeHeralded as heralded,
    TLSPumpProbeLocalizer as localizer,
    TLSPumpProbeProtocolCheck as protocol,
    TLSPumpProbeResidentDrive as resident,
    TLSPumpProbeResidentProbe as probe,
    TLSPumpProbeShotAlternating as alternating,
    TLSPumpProbeWidePassiveScan as wide,
)


LOAD_US = 10.0
PROBE_US = 6.0
STORE_US = (0.5, 2.0, 10.0, 40.0)
RECOVERY_US = 40.0
SHOTS = 800
CONFIRM_SHOTS = 1200
CONFIRM_GAPS_US = (10.0, 40.0)
REFERENCE_SHOTS = 400
PAIR_NAMES = ("ff", "fc", "cf", "cc")
CONDITION_NAMES = tuple(f"{pair}_{state}" for pair in PAIR_NAMES
                        for state in ("g", "e"))
CONFIRM_CONDITION_NAMES = tuple(
    f"t{int(gap)}_{name}" for gap in CONFIRM_GAPS_US
    for name in CONDITION_NAMES)


def two_visit_segments(compensation, *, load_us, store_us, probe_us,
                       second_amplitude, recovery_us=RECOVERY_US):
    """Superpose four inverse step responses for target–park–target–park."""
    durations = (float(load_us), float(store_us), float(probe_us),
                 float(recovery_us))
    if not all(math.isfinite(x) and x >= 0.5 for x in durations):
        raise ValueError("two-visit durations must be finite and at least 0.5 us")
    ratio = float(second_amplitude)
    if not math.isfinite(ratio) or ratio <= 0 or ratio > 2.0:
        raise ValueError("second-visit amplitude ratio must be in (0,2]")
    edges, multipliers = ff_pulse._compensation_arrays(compensation)
    load, gap, probe, recovery = durations
    events = (0.0, load, load + gap, load + gap + probe)
    amplitudes = (1.0, -1.0, ratio, -ratio)
    horizon = events[-1] + recovery
    bounds = {0.0, horizon}
    for event in events:
        bounds.add(event)
        bounds.update(round(event + float(edge), 12) for edge in edges
                      if 0.0 < event + edge < horizon)
    bounds = sorted(bounds)
    segments = []
    for start, stop in zip(bounds[:-1], bounds[1:]):
        if stop - start <= 1e-12:
            continue
        midpoint = (start + stop) / 2.0
        level = sum(amplitude * ff_pulse._compensation_multiplier_at(
            edges, multipliers, midpoint - event)
            for event, amplitude in zip(events, amplitudes)
            if midpoint >= event)
        if segments and abs(segments[-1][0] - level) < 1e-10:
            segments[-1] = (segments[-1][0], segments[-1][1] + stop - start)
        else:
            segments.append((float(level), float(stop - start)))
    if abs(sum(duration for _, duration in segments) - horizon) > 1e-6:
        raise ValueError("two-visit waveform has incomplete return")
    return segments


def program_specs(feature_ghz, control_ghz):
    sites = {"f": float(feature_ghz), "c": float(control_ghz)}
    specs = []
    for repeat in (0, 1):
        gaps = STORE_US if repeat == 0 else tuple(reversed(STORE_US))
        for store_us in gaps:
            conditions = [{"name": f"{pair}_{state}",
                           "load_site": pair[0], "probe_site": pair[1],
                           "load_ghz": sites[pair[0]],
                           "probe_ghz": sites[pair[1]],
                           "state": state, "load_us": LOAD_US,
                           "store_us": store_us, "probe_us": PROBE_US}
                          for pair in PAIR_NAMES for state in ("g", "e")]
            if repeat:
                conditions.reverse()
            label = f"{store_us:g}".replace(".", "p")
            specs.append({"name": f"store{label}_r{repeat}",
                          "store_us": store_us, "repeat": repeat,
                          "shots": SHOTS, "order": [c["name"] for c in conditions],
                          "conditions": conditions, "status": "pending"})
    return specs


def confirmation_specs(feature_ghz, control_ghz):
    """Interleave both gaps within every shot; reverse temporal order twice."""
    sites = {"f": float(feature_ghz), "c": float(control_ghz)}
    specs = []
    for block in range(4):
        gaps = (CONFIRM_GAPS_US if block < 2 else
                tuple(reversed(CONFIRM_GAPS_US)))
        conditions = [{"name": f"t{int(gap)}_{pair}_{state}",
                       "load_site": pair[0], "probe_site": pair[1],
                       "load_ghz": sites[pair[0]],
                       "probe_ghz": sites[pair[1]], "state": state,
                       "load_us": LOAD_US, "store_us": gap,
                       "probe_us": PROBE_US}
                      for gap in gaps for pair in PAIR_NAMES
                      for state in ("g", "e")]
        if block % 2:
            conditions.reverse()
        specs.append({"name": f"confirm_b{block}", "block": block,
                      "shots": CONFIRM_SHOTS,
                      "order": [c["name"] for c in conditions],
                      "conditions": conditions, "status": "pending"})
    return specs


def split_records(records, order, *, shots):
    records = list(records)
    valid = ((len(order) == 8 and set(order) == set(CONDITION_NAMES)) or
             (len(order) == 16 and set(order) == set(CONFIRM_CONDITION_NAMES)))
    if not valid:
        raise ValueError("invalid two-visit stream order")
    if len(records) != len(order) * int(shots):
        raise ValueError("incomplete two-visit IQ stream")
    return {name: records[index::len(order)]
            for index, name in enumerate(order)}


def score(fractions):
    contrasts = {pair: float(fractions[f"{pair}_e"] - fractions[f"{pair}_g"])
                 for pair in PAIR_NAMES}
    usable = all(value >= .10 for value in contrasts.values())
    interaction = (math.log(contrasts["ff"] * contrasts["cc"] /
                            (contrasts["fc"] * contrasts["cf"]))
                   if usable else None)
    return {"contrasts": contrasts, "log_interaction": interaction,
            "usable": usable}


def score_entry(entry, *, confirm=False):
    if confirm:
        return {str(gap): score({
            cond["name"].removeprefix(f"t{int(gap)}_"):
            cond["excited_fraction_pre_axis"]
            for cond in entry["conditions"] if cond["store_us"] == gap})
            for gap in CONFIRM_GAPS_US}
    return score({cond["name"]: cond["excited_fraction_pre_axis"]
                  for cond in entry["conditions"]})


def arm_config(base, condition, dc_lookup, *, shots=SHOTS):
    """A park-prepared g/e subshot with two independent flux visit gains."""
    cfg = resident.arm_config(base, {
        "flux_ghz": condition["load_ghz"],
        "drive_mhz": 1000.0 * condition["load_ghz"],
        "gain": 0, "preparation_state": condition["state"],
        "reference_state": None, "pre_drive_us": .05,
        "post_drive_us": condition["load_us"], "shots": shots,
    }, dc_lookup)
    cfg.update({"opx_probe_ff_gain": int(dc_lookup[condition["probe_ghz"]]),
                "opx_load_us": float(condition["load_us"]),
                "opx_store_us": float(condition["store_us"]),
                "opx_probe_us": float(condition["probe_us"]),
                "ff_hold": (float(condition["load_us"]) +
                            float(condition["store_us"]) +
                            float(condition["probe_us"]))})
    return cfg


class TwoVisitProgram(alternating.ShotAlternatingResidentProgram):
    """Matched visit-pair/preparation subshots per hardware shot."""

    def __init__(self, soccfg, condition_cfgs, payload_calibration, loop_calibration):
        configs = [dict(cfg) for cfg in condition_cfgs]
        if len(configs) not in (8, 16):
            raise ValueError("eight or sixteen two-visit conditions are required")
        common = ("ff_park_gain", "shots", "reps", "opx_load_us",
                  "opx_probe_us")
        if any(any(cfg[key] != configs[0][key] for key in common)
               for cfg in configs[1:]):
            raise ValueError("within-shot visits must share timing and shots")
        observed = {(int(cfg["ff_gain"]), int(cfg["opx_probe_ff_gain"]),
                     cfg["opx_resident_preparation_state"],
                     float(cfg["opx_store_us"])) for cfg in configs}
        gains = {cfg["ff_gain"] for cfg in configs}
        gaps = {float(cfg["opx_store_us"]) for cfg in configs}
        if (len(gains) != 2 or len(gaps) != len(configs) // 8 or
                observed != {(a, b, state, gap)
                            for a in gains for b in gains
                            for state in ("g", "e") for gap in gaps}):
            raise ValueError("conditions must span four visit pairs, g/e, and gaps")
        self.conditions_per_shot = len(configs)
        self.logical_shots = int(configs[0]["shots"])
        self.condition_cfgs = configs
        run_cfg = dict(configs[0], reps=len(configs) * self.logical_shots)
        resident.ResidentDriveProgram.__init__(
            self, soccfg, run_cfg, payload_calibration, loop_calibration)

    def _resident_excursion(self):
        if self._t1_ff_compensation is None:
            raise ValueError("two visits require the pinned flux correction")
        cfg = self.cfg
        park = float(cfg["ff_park_gain"])
        first = float(cfg["ff_gain"])
        second = float(cfg["opx_probe_ff_gain"])
        if first == park:
            raise ValueError("first visit gain equals park")
        segments = two_visit_segments(
            self._t1_ff_compensation,
            load_us=cfg["opx_load_us"], store_us=cfg["opx_store_us"],
            probe_us=cfg["opx_probe_us"],
            second_amplitude=(second - park) / (first - park),
            recovery_us=self._t1_ff_predistortion_recovery_us)
        ff_pulse.play_relative_compensation_segments(self, park, first, segments)
        ff_pulse.play_hard_step(self, park)
        self.sync_all(0)


def plan(*, confirm=False):
    return {"hardware_access": False, "goal": "direct two-visit TLS memory",
            "load_us": LOAD_US,
            "store_us": list(CONFIRM_GAPS_US if confirm else STORE_US),
            "probe_us": PROBE_US, "recovery_us": RECOVERY_US,
            "conditions_per_shot": 16 if confirm else 8,
            "programs": 4 if confirm else 8,
            "shots_per_program": CONFIRM_SHOTS if confirm else SHOTS,
            "intermediate_readouts": 0,
            "readout": "one readout after both visits and corrected return",
            "reset": "passive", "control": "four first/second site pairs, g/e",
            "interpretation": "short-gap interaction beyond independent qubit loss",
            "confirm": bool(confirm)}


def _condition_configs(base, entry, dc_lookup):
    return [arm_config(base, cond, dc_lookup, shots=entry["shots"])
            for cond in entry["conditions"]]


def _interaction_report(specs, scores):
    report = {}
    for gap in STORE_US:
        matched = [spec for spec in specs if spec["store_us"] == gap]
        values = [scores[spec["name"]]["log_interaction"] for spec in matched]
        valid = all(value is not None for value in values)
        report[str(gap)] = {
            "repeat_scores": values,
            "mean_log_interaction": float(np.mean(values)) if valid else None,
            "order_agrees": bool(values[0] * values[1] > 0) if valid else False,
        }
    return report


def _confirmation_report(specs, scores):
    paired = []
    for entry in specs:
        item = scores[entry["name"]]
        a = item["10.0"]["log_interaction"]
        b = item["40.0"]["log_interaction"]
        paired.append({"block": entry["block"], "log_interaction_10_us": a,
                       "log_interaction_40_us": b,
                       "difference": a - b if a is not None and b is not None
                       else None})
    differences = [item["difference"] for item in paired]
    return {"blocks": paired,
            "mean_paired_difference": (float(np.mean(differences))
                                       if all(x is not None for x in differences)
                                       else None)}


def run(*, data_root=localizer.DATA_ROOT, correction_json=None,
        confirm=False):
    """Fresh loss scout, paired short-gap visits, references, and post scout."""
    data_root = Path(data_root)
    correction = localizer.checked_correction(data_root, correction_json)
    scout = localizer.run(
        data_root=data_root, correction_json=correction,
        parameter_overrides={**heralded.postselection_scout_parameters("pre"),
                             "output_suffix": "TLS_TwoVisit_Memory_Scout_pre"})
    selected = heralded.select_postselection_feature(
        heralded.read_postselection_scout(scout))
    center, control = selected["center_ghz"], selected["control_ghz"]
    print(f"[two-visit] feature={center:.3f} GHz; "
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
        specs = (confirmation_specs(center, control) if confirm else
                 program_specs(center, control))
        grid = np.asarray(sorted((center, control)), dtype=float)
        dc, realized = _integer_dc_grid(wide.parameters(), grid, tls)
        dc_lookup = {float(f): int(g) for f, g in zip(grid, dc)}
        compensation = tls._load_correction(str(correction), str(data_root))
        park = float(tls.BaseConfig["ff_park_gain"])
        for entry in specs:
            for condition in entry["conditions"]:
                first = dc_lookup[condition["load_ghz"]]
                second = dc_lookup[condition["probe_ghz"]]
                two_visit_segments(
                    compensation, load_us=LOAD_US,
                    store_us=condition["store_us"], probe_us=PROBE_US,
                    second_amplitude=(second - park) / (first - park))
        base = ProductionResetSession.passive().apply(tls.BaseConfig)
        five.apply_verified_feedback_timing(base)
        base.update({"apply_flux_tail_compensation": True,
                     "flux_tail_compensation": compensation,
                     "flux_fit_params": tls.FLUX_FIT_PARAMS,
                     "flux_settle_time_us": 0.5,
                     "flux_predistortion_return_prefix_us": 0.5,
                     "flux_predistortion_recovery_us": RECOVERY_US,
                     "flux_predistortion_overlap_payload_readout": False,
                     "flux_predistortion_round_trip_mode": "stateful",
                     "readout_thermalization_us": 10.0,
                     "qubit_pulse_style": "arb", "do_ff": True,
                     "opx_reset_scheme": "none",
                     "opx_resident_dmem_stream": True,
                     "opx_inter_shot_delay_us": 500.0})
        session_id = (("q3_tls_two_visit_memory_confirm_" if confirm else
                       "q3_tls_two_visit_memory_") +
                      datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") +
                      "_" + uuid.uuid4().hex[:8])
        folder = data_root / "q3" / session_id
        folder.mkdir(parents=True, exist_ok=False)
        path = folder / "manifest.json"
        refs = (probe.reference_arms(center, phase="pre") +
                probe.reference_arms(center, phase="post"))
        for ref in refs:
            ref.update(shots=REFERENCE_SHOTS, status="pending")
        manifest = {
            "schema": ("q3.tls-two-visit-memory-confirm.v1" if confirm else
                       "q3.tls-two-visit-memory.v1"), "status": "running",
            "session_id": session_id,
            "code_commit": os.environ.get("Q3_CODE_COMMIT", "unknown"),
            "correction_json": str(correction),
            "correction_sha256": localizer.CORRECTION_SHA256,
            "scout_csv": str(scout), "selected": selected,
            "center_ghz": center, "control_ghz": control,
            "dc_lookup": dc_lookup, "realized_ghz": realized.tolist(),
            "plan": plan(confirm=confirm), "references": refs,
            "programs": specs,
        }
        protocol.checkpoint(path, manifest)
        print(f"[two-visit] manifest={path}", flush=True)
        raw_refs = {}
        axis = None
        try:
            soc, soccfg = tls.makeProxy()
            bundle = runtime_bundle(base)
            programs = {}
            for entry in specs:
                programs[entry["name"]] = TwoVisitProgram(
                    soccfg, _condition_configs(base, entry, dc_lookup),
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
                records = _run_program(
                    soc, resident.ResidentDriveProgram(
                        soccfg, cfg, bundle.payload, bundle.loop),
                    max(30.0, _block_timeout_s(cfg, REFERENCE_SHOTS)),
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
                    ref["excited_fraction_pre_axis"] = resident.classify(
                        records, axis)
                ref["status"] = "complete"
                protocol.checkpoint(path, manifest)

            for ref in refs[:4]:
                print(f"[two-visit] {ref['name']}", flush=True)
                acquire_ref(ref)
            for entry in specs:
                shots = int(entry["shots"])
                records_per_shot = len(entry["conditions"])
                print(f"[two-visit] {entry['name']} "
                      f"{shots} x {records_per_shot}", flush=True)
                entry["status"] = "acquiring"
                protocol.checkpoint(path, manifest)
                entry["acquisition_started_at_utc"] = (
                    datetime.now(timezone.utc).isoformat())
                started = time.monotonic()
                records = _run_program(
                    soc, programs[entry["name"]],
                    max(30.0, records_per_shot * _block_timeout_s(base, shots)),
                    base, total_shots=shots)
                entry["acquisition_elapsed_s"] = time.monotonic() - started
                entry["acquisition_finished_at_utc"] = (
                    datetime.now(timezone.utc).isoformat())
                split = split_records(records, entry["order"], shots=shots)
                for cond in entry["conditions"]:
                    subset = split[cond["name"]]
                    raw_path = folder / f"{entry['name']}_{cond['name']}.npz"
                    np.savez_compressed(raw_path, i=[r.i for r in subset],
                                        q=[r.q for r in subset])
                    cond["raw_npz"] = str(raw_path)
                    cond["excited_fraction_pre_axis"] = resident.classify(
                        subset, axis)
                entry["status"] = "complete"
                protocol.checkpoint(path, manifest)
            for ref in refs[4:]:
                print(f"[two-visit] {ref['name']}", flush=True)
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
                item["usable"] = resident.transfer_usable(
                    item["ground"], item["excited"])
            scores = {entry["name"]: score_entry(entry, confirm=confirm)
                      for entry in specs}
            manifest["program_scores"] = scores
            manifest["interaction_report"] = (
                _confirmation_report(specs, scores) if confirm else
                _interaction_report(specs, scores))
            post_scout = localizer.run(
                data_root=data_root, correction_json=correction,
                parameter_overrides={**heralded.postselection_scout_parameters("post"),
                                     "output_suffix": "TLS_TwoVisit_Memory_Scout_post"})
            manifest["post_scout_csv"] = str(post_scout)
            try:
                manifest["post_selected"] = (
                    heralded.select_postselection_feature(
                        heralded.read_postselection_scout(post_scout)))
            except ValueError as exc:
                manifest["post_selection_error"] = str(exc)
            manifest["feature_stable"] = bool(
                "post_selected" in manifest and
                resident.feature_stable(selected, manifest["post_selected"]))
            manifest["status"] = (
                "complete" if manifest["post_readout_score"]["valid"] and
                all(item["usable"] for item in
                    manifest["transfer_control"].values()) and
                all((all(x["usable"] for x in item.values()) if confirm else
                     item["usable"]) for item in scores.values()) and
                manifest["feature_stable"] else "complete_controls_unstable")
            protocol.checkpoint(path, manifest)
            print(f"[two-visit] {manifest['status']}: {path}", flush=True)
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
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--data-root", default=str(localizer.DATA_ROOT))
    parser.add_argument("--correction-json")
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(plan(confirm=args.confirm), indent=2))
        return 0
    run(data_root=args.data_root, correction_json=args.correction_json,
        confirm=args.confirm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
