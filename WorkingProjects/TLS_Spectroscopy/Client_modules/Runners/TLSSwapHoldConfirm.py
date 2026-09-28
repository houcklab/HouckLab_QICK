"""Confirm q3's exploratory 1.5-to-6-us feature-local loss within each shot.

Each logical QICK shot contains four complete park-preparation, corrected
flux-visit, return, and readout subshots: early/late by ground/excited.
The lower loss feature is freshly located near 4.127 GHz, with a clean
14-MHz lower control. Feature/control and subshot order are reversed once.
This is a preregistered replication of the pilot's exploratory contrast,
not proof of a single coherent TLS or a successful pump-probe saturation.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import uuid

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSPumpProbeAdaptiveParkPump as adaptive,
    TLSPumpProbeLocalizer as localizer,
    TLSPumpProbeProtocolCheck as protocol,
    TLSPumpProbeResidentDrive as resident,
    TLSPumpProbeResidentProbe as probe,
    TLSPumpProbeShotAlternating as alternating,
    TLSPumpProbeWidePassiveScan as wide,
    TLSSwapHoldPilot as swap,
)
EARLY_US = 1.5
LATE_US = 6.0
SHOTS = 3000
MAP_SHOTS = 1000
MAP_RADIUS_MHZ = 8
PAIR_SHOTS = 800
PAIR_REFERENCE_US = 0.1
PAIR_DWELLS_US = swap.HOLDS_US[1:]
REFERENCE_SHOTS = 400
RECORDS_PER_SHOT = 4
CONDITION_NAMES = ("early_g", "early_e", "late_g", "late_e")


def conditions(*, reverse=False, early_us=EARLY_US, late_us=LATE_US):
    if not 0.05 <= float(early_us) < float(late_us):
        raise ValueError("paired dwells must be ordered and at least 0.05 us")
    result = [{"name": f"{label}_{state}", "hold_us": hold,
               "state": state}
              for label, hold in (("early", early_us), ("late", late_us))
              for state in ("g", "e")]
    return list(reversed(result)) if reverse else result


def program_specs(feature_ghz, control_ghz):
    specs = []
    for repeat in (0, 1):
        sites = (("feature", feature_ghz), ("control", control_ghz))
        if repeat:
            sites = tuple(reversed(sites))
        for site, flux in sites:
            conds = conditions(reverse=bool(repeat))
            specs.append({"name": f"r{repeat}_{site}", "repeat": repeat,
                          "site": site, "flux_ghz": float(flux),
                          "shots": SHOTS, "order": [c["name"] for c in conds],
                          "conditions": conds, "status": "pending"})
    return specs


def flux_map_specs(feature_ghz, control_ghz):
    """Sweep a fixed ±8-MHz grid in both directions, bracketing controls."""
    frequencies = [round(float(feature_ghz) + 0.001 * offset, 3)
                   for offset in range(-MAP_RADIUS_MHZ, MAP_RADIUS_MHZ + 1)]
    specs = []
    for repeat in (0, 1):
        reverse = bool(repeat)
        def append(name, site, flux):
            conds = conditions(reverse=reverse)
            specs.append({"name": name, "repeat": repeat, "site": site,
                          "flux_ghz": float(flux), "shots": MAP_SHOTS,
                          "order": [item["name"] for item in conds],
                          "conditions": conds,
                          "status": "pending"})
        append(f"r{repeat}_control_pre", "control", control_ghz)
        for index in (range(len(frequencies)) if not reverse
                      else reversed(range(len(frequencies)))):
            append(f"r{repeat}_f{index:02d}", "map", frequencies[index])
        append(f"r{repeat}_control_post", "control", control_ghz)
    return specs


def paired_dwell_specs(feature_ghz, control_ghz):
    """Pair each later hold with 0.1 us in both site and time orders."""
    specs = []
    for repeat in (0, 1):
        holds = PAIR_DWELLS_US if repeat == 0 else tuple(reversed(PAIR_DWELLS_US))
        sites = (("feature", feature_ghz), ("control", control_ghz))
        if repeat:
            sites = tuple(reversed(sites))
        for hold in holds:
            label = f"{hold:g}".replace(".", "p")
            for site, flux in sites:
                conds = conditions(reverse=bool(repeat),
                                   early_us=PAIR_REFERENCE_US, late_us=hold)
                specs.append({"name": f"r{repeat}_t{label}_{site}",
                              "repeat": repeat, "site": site,
                              "flux_ghz": float(flux), "hold_us": hold,
                              "shots": PAIR_SHOTS,
                              "order": [item["name"] for item in conds],
                              "conditions": conds, "status": "pending"})
    return specs


def paired_dwell_report(specs, scores):
    report = {}
    for repeat in (0, 1):
        rows = []
        holds = sorted({item["hold_us"] for item in specs})
        for hold in holds:
            items = {item["site"]: item for item in specs
                     if item["repeat"] == repeat and item["hold_us"] == hold}
            feature = scores[items["feature"]["name"]]
            control = scores[items["control"]["name"]]
            rows.append({"hold_us": hold,
                         "feature_drop": feature["drop"],
                         "control_drop": control["drop"],
                         "excess_drop": effect(feature, control),
                         "usable": feature["usable"] and control["usable"]})
        report[f"r{repeat}"] = rows
    return report


def preflight_entries(specs, *, flux_map=False, paired_dwell_scan=False):
    if paired_dwell_scan:
        return [specs[i] for i in (0, 1, 18, 19, 20, 21, 38, 39)]
    if flux_map:
        return [specs[i] for i in (0, 1, 17, 18, 19, 20, 36, 37)]
    return specs


def flux_map_report(specs, scores):
    report = {}
    for repeat in (0, 1):
        baseline = (scores[f"r{repeat}_control_pre"]["drop"] +
                    scores[f"r{repeat}_control_post"]["drop"]) / 2.0
        report[f"r{repeat}"] = [
            {"flux_ghz": item["flux_ghz"], "drop": scores[item["name"]]["drop"],
             "control_drop": baseline,
             "excess_drop": scores[item["name"]]["drop"] - baseline,
             "usable": scores[item["name"]]["usable"]}
            for item in sorted((item for item in specs if item["repeat"] == repeat
                                and item["site"] == "map"),
                               key=lambda item: item["flux_ghz"])]
    return report


def select_moving_lower_dip(rows):
    return swap.select_moving_lower_dip(rows)


def split_records(records, order, *, shots):
    records = list(records)
    if len(order) != RECORDS_PER_SHOT or set(order) != set(CONDITION_NAMES):
        raise ValueError("invalid four-condition stream order")
    if len(records) != RECORDS_PER_SHOT * int(shots):
        raise ValueError("incomplete four-condition IQ stream")
    return {name: records[index::RECORDS_PER_SHOT]
            for index, name in enumerate(order)}


def score(fractions):
    x = {name: float(fractions[name]) for name in CONDITION_NAMES}
    early = x["early_e"] - x["early_g"]
    late = x["late_e"] - x["late_g"]
    return {"early_contrast": early, "late_contrast": late,
            "drop": early - late,
            "ground_change": x["late_g"] - x["early_g"],
            "usable": bool(early >= 0.20 and late >= 0.10 and
                           abs(x["late_g"] - x["early_g"]) <= 0.08)}


def effect(feature, control):
    return float(feature["drop"] - control["drop"])


def plan(*, flux_map=False, follow_moving_dip=False,
         paired_dwell_scan=False):
    if flux_map and (follow_moving_dip or paired_dwell_scan):
        raise ValueError("select one swap-hold follow-up mode")
    if paired_dwell_scan:
        return {"hardware_access": False, "reset_mode": "passive",
                "feature_search_ghz": [4.105, 4.134],
                "control": "fresh qualified 14-MHz lower flux point",
                "reference_hold_us": PAIR_REFERENCE_US,
                "later_holds_us": list(PAIR_DWELLS_US),
                "conditions_per_shot": RECORDS_PER_SHOT,
                "shots_per_program": PAIR_SHOTS, "programs": 40,
                "orders": ["ascending", "descending"],
                "full_return_before_each_readout_us": 40.0,
                "raw_iq_saved": True,
                "primary_effect": "at each dwell, feature early-minus-late "
                                  "hot-cold contrast minus control drop",
                "interpretation": "0.1-us reference includes flux settling; "
                                  "compare 0.5–6-us structure cautiously"}
    if follow_moving_dip:
        return {"hardware_access": False, "reset_mode": "passive",
                "feature_search_ghz": [4.105, 4.134],
                "control": "14-MHz lower point qualified in both scout directions",
                "dwells_us": [EARLY_US, LATE_US],
                "conditions_per_shot": RECORDS_PER_SHOT,
                "shots_per_program": SHOTS, "programs": 4,
                "full_return_before_each_readout_us": 40.0,
                "raw_iq_saved": True,
                "primary_effect": "feature versus control extra 1.5-to-6-us "
                                  "hot-cold loss, forward and reverse"}
    if flux_map:
        return {"hardware_access": False, "reset_mode": "passive",
                "feature_anchor_ghz": 4.127,
                "map": "17 flux points, 1 MHz apart, centered on fresh lower feature",
                "control": "clean 14-MHz lower flux point, before/after each sweep",
                "dwells_us": [EARLY_US, LATE_US],
                "conditions_per_shot": RECORDS_PER_SHOT,
                "shots_per_program": MAP_SHOTS, "programs": 38,
                "orders": ["ascending", "descending"],
                "full_return_before_each_readout_us": 40.0,
                "raw_iq_saved": True,
                "primary_effect": "at each flux, early-minus-late hot-cold contrast "
                                  "minus bracketing-control mean"}
    return {"hardware_access": False, "reset_mode": "passive",
            "feature_anchor_ghz": 4.127,
            "control": "clean 14-MHz lower flux point",
            "dwells_us": [EARLY_US, LATE_US],
            "conditions_per_shot": RECORDS_PER_SHOT,
            "shots_per_program": SHOTS, "programs": 4,
            "full_return_before_each_readout_us": 40.0,
            "raw_iq_saved": True,
            "primary_effect": "(early hot-cold minus late hot-cold) at feature "
                              "minus the same drop at control",
            "note": __doc__}


class AlternatingSwapHoldProgram(alternating.ShotAlternatingResidentProgram):
    """Four matched short/long, g/e visits in each logical shot."""

    def __init__(self, soccfg, condition_cfgs, payload_calibration, loop_calibration):
        configs = [dict(cfg) for cfg in condition_cfgs]
        if len(configs) != RECORDS_PER_SHOT:
            raise ValueError("four swap-hold conditions are required")
        common = ("ff_gain", "ff_park_gain", "shots", "reps")
        if any(any(cfg[key] != configs[0][key] for key in common)
               for cfg in configs[1:]):
            raise ValueError("within-shot swap conditions must share flux and shots")
        observed = {(float(cfg["opx_swap_hold_us"]),
                     cfg["opx_resident_preparation_state"]) for cfg in configs}
        holds = {hold for hold, _ in observed}
        if (len(holds) != 2 or
                observed != {(hold, state) for hold in holds
                             for state in ("g", "e")}):
            raise ValueError("swap conditions must span both dwells and states")
        self.conditions_per_shot = RECORDS_PER_SHOT
        self.logical_shots = int(configs[0]["shots"])
        self.condition_cfgs = configs
        run_cfg = dict(configs[0], reps=RECORDS_PER_SHOT * self.logical_shots)
        resident.ResidentDriveProgram.__init__(
            self, soccfg, run_cfg, payload_calibration, loop_calibration)

    def _resident_excursion(self):
        swap.SwapHoldProgram._resident_excursion(self)


def _condition_configs(base, entry, dc_lookup):
    return [swap.arm_config(base, {
        "flux_ghz": entry["flux_ghz"], "hold_us": cond["hold_us"],
        "state": cond["state"], "shots": entry["shots"]}, dc_lookup)
        for cond in entry["conditions"]]


def run(*, data_root=localizer.DATA_ROOT, correction_json=None,
        flux_map=False, follow_moving_dip=False, paired_dwell_scan=False):
    if flux_map and (follow_moving_dip or paired_dwell_scan):
        raise ValueError("select one swap-hold follow-up mode")
    follow_moving_dip = follow_moving_dip or paired_dwell_scan
    data_root = Path(data_root)
    correction = localizer.checked_correction(data_root, correction_json)
    scout_suffix = ("TLS_SwapHold_Paired_Dwell_Scout_pre" if paired_dwell_scan
                    else "TLS_SwapHold_Confirm_Scout_pre")
    scout = localizer.run(
        data_root=data_root, correction_json=correction,
        parameter_overrides={**adaptive.scout_parameters(phase="pre"),
                             "output_suffix": scout_suffix})
    selector = (select_moving_lower_dip if follow_moving_dip else
                lambda rows: swap.select_anchored_feature(
                    rows, preferred_center=4.127))
    selected = selector(adaptive.read_scout(scout))
    center, control = selected["center_ghz"], selected["control_ghz"]
    print(f"[swap-confirm] lower feature={center:.3f} GHz; "
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
        specs = (flux_map_specs(center, control) if flux_map else
                 paired_dwell_specs(center, control) if paired_dwell_scan else
                 program_specs(center, control))
        grid = np.asarray(sorted({item["flux_ghz"] for item in specs}), dtype=float)
        dc, realized = _integer_dc_grid(wide.parameters(), grid, tls)
        dc_lookup = {float(f): int(g) for f, g in zip(grid, dc)}
        compensation = tls._load_correction(str(correction), str(data_root))
        holds = ({cond["hold_us"] for entry in specs
                  for cond in entry["conditions"]})
        for hold in sorted(holds):
            swap.swap_segments(compensation, hold_us=hold)
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
        session_id = (("q3_tls_swap_hold_paired_dwell_" if paired_dwell_scan else
                       "q3_tls_swap_hold_flux_map_" if flux_map else
                       "q3_tls_swap_hold_moving_dip_" if follow_moving_dip else
                       "q3_tls_swap_hold_confirm_") +
                      datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") +
                      "_" + uuid.uuid4().hex[:8])
        folder = data_root / "q3" / session_id
        folder.mkdir(parents=True, exist_ok=False)
        path = folder / "manifest.json"
        refs = (probe.reference_arms(center, phase="pre") +
                probe.reference_arms(center, phase="post"))
        for ref in refs:
            ref.update(shots=REFERENCE_SHOTS, status="pending")
        manifest = {"schema": ("q3.tls-swap-hold-paired-dwell.v1"
                               if paired_dwell_scan else
                               "q3.tls-swap-hold-flux-map.v1" if flux_map else
                               "q3.tls-swap-hold-moving-dip.v1"
                               if follow_moving_dip else
                               "q3.tls-swap-hold-confirm.v1"),
                    "status": "running", "session_id": session_id,
                    "code_commit": os.environ.get("Q3_CODE_COMMIT", "unknown"),
                    "correction_json": str(correction),
                    "correction_sha256": localizer.CORRECTION_SHA256,
                    "scout_csv": str(scout), "selected": selected,
                    "center_ghz": center, "control_ghz": control,
                    "dc_lookup": dc_lookup, "realized_ghz": realized.tolist(),
                    "plan": plan(flux_map=flux_map,
                                 follow_moving_dip=follow_moving_dip,
                                 paired_dwell_scan=paired_dwell_scan),
                    "references": refs,
                    "programs": specs}
        protocol.checkpoint(path, manifest)
        print(f"[swap-confirm] manifest={path}", flush=True)
        raw_refs = {}
        axis = None
        try:
            soc, soccfg = tls.makeProxy()
            bundle = runtime_bundle(base)
            programs = {}
            preflight = preflight_entries(
                manifest["programs"], flux_map=flux_map,
                paired_dwell_scan=paired_dwell_scan)
            for entry in preflight:
                cfgs = _condition_configs(base, entry, dc_lookup)
                programs[entry["name"]] = AlternatingSwapHoldProgram(
                    soccfg, cfgs, bundle.payload, bundle.loop)
            for ref in refs:
                resident.ResidentDriveProgram(
                    soccfg, resident.arm_config(base, ref, dc_lookup),
                    bundle.payload, bundle.loop)
            manifest["preflight_complete"] = True
            manifest["preflight_programs"] = list(programs)
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
                print(f"[swap-confirm] {ref['name']}", flush=True)
                acquire_ref(ref)
            for entry in manifest["programs"]:
                shots = int(entry["shots"])
                print(f"[swap-confirm] {entry['name']} {shots} x 4", flush=True)
                entry["status"] = "acquiring"
                protocol.checkpoint(path, manifest)
                program = programs.get(entry["name"])
                if program is None:
                    program = AlternatingSwapHoldProgram(
                        soccfg, _condition_configs(base, entry, dc_lookup),
                        bundle.payload, bundle.loop)
                records = _run_program(
                    soc, program,
                    max(30.0, RECORDS_PER_SHOT * _block_timeout_s(base, shots)),
                    base, total_shots=shots)
                split = split_records(records, entry["order"], shots=shots)
                for cond in entry["conditions"]:
                    subset = split[cond["name"]]
                    raw_path = folder / f"{entry['name']}_{cond['name']}.npz"
                    np.savez_compressed(raw_path, i=[r.i for r in subset],
                                        q=[r.q for r in subset])
                    cond["raw_npz"] = str(raw_path)
                    cond["excited_fraction_pre_axis"] = resident.classify(subset, axis)
                entry["status"] = "complete"
                protocol.checkpoint(path, manifest)
            for ref in refs[4:]:
                print(f"[swap-confirm] {ref['name']}", flush=True)
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
            scores = {entry["name"]: score({
                cond["name"]: cond["excited_fraction_pre_axis"]
                for cond in entry["conditions"]})
                for entry in manifest["programs"]}
            manifest["program_scores"] = scores
            if paired_dwell_scan:
                manifest["paired_dwell_report"] = paired_dwell_report(specs, scores)
            elif flux_map:
                manifest["flux_map_report"] = flux_map_report(specs, scores)
            else:
                manifest["effect_report"] = {
                    f"r{repeat}": effect(scores[f"r{repeat}_feature"],
                                         scores[f"r{repeat}_control"])
                    for repeat in (0, 1)}
            post_scout = localizer.run(
                data_root=data_root, correction_json=correction,
                parameter_overrides={**adaptive.scout_parameters(phase="post"),
                                     "output_suffix": (
                                         "TLS_SwapHold_Paired_Dwell_Scout_post"
                                         if paired_dwell_scan else
                                         "TLS_SwapHold_Confirm_Scout_post")})
            manifest["post_scout_csv"] = str(post_scout)
            try:
                manifest["post_selected"] = selector(
                    adaptive.read_scout(post_scout))
            except ValueError as exc:
                manifest["post_selection_error"] = str(exc)
            manifest["feature_stable"] = (
                swap.feature_stable(selected, manifest["post_selected"])
                if "post_selected" in manifest else False)
            if "post_selected" in manifest:
                manifest["feature_shift_mhz"] = round(
                    1000.0 * (manifest["post_selected"]["center_ghz"] - center),
                    3)
            valid = (manifest["post_readout_score"]["valid"] and
                     all(x["usable"] for x in manifest["transfer_control"].values())
                     and all(x["usable"] for x in scores.values()) and
                     manifest["feature_stable"])
            manifest["status"] = "complete" if valid else "complete_controls_unstable"
            protocol.checkpoint(path, manifest)
            print(f"[swap-confirm] {manifest['status']}: {path}", flush=True)
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
    parser.add_argument("--flux-map", action="store_true",
                        help="map the short/long excess loss across flux")
    parser.add_argument("--follow-moving-dip", action="store_true",
                        help="retarget the lower-band loss after larger spectral shifts")
    parser.add_argument("--paired-dwell-scan", action="store_true",
                        help="interleave 0.1 us and later holds at moving dip")
    args = parser.parse_args(argv)
    if args.flux_map and (args.follow_moving_dip or args.paired_dwell_scan):
        parser.error("--flux-map cannot be combined with another follow-up mode")
    if args.plan:
        print(json.dumps(plan(flux_map=args.flux_map,
                              follow_moving_dip=args.follow_moving_dip,
                              paired_dwell_scan=args.paired_dwell_scan), indent=2))
    else:
        run(data_root=args.data_root, correction_json=args.correction_json,
            flux_map=args.flux_map,
            follow_moving_dip=args.follow_moving_dip,
            paired_dwell_scan=args.paired_dwell_scan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
