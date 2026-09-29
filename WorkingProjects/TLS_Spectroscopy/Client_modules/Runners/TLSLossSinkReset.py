"""Test whether a fresh q3 loss feature acts as a cold, reusable reset sink.

This first stage measures feature/control cooling and ground-state heating as a
function of hold time. Every hardware shot interleaves both flux sites, both
preparations, and a 0.1-us reference hold. It uses the already verified passive
reset and corrected single-visit pulse path. A second-use test is conditional
on the measured cooling curve; this runner makes no TLS-identity claim.
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

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSPumpProbeLocalizer as localizer,
    TLSPumpProbeProtocolCheck as protocol,
    TLSPumpProbeResidentDrive as resident,
    TLSPumpProbeResidentProbe as probe,
    TLSPumpProbeWidePassiveScan as wide,
    TLSSwapHoldConfirm as confirm,
    TLSSwapHoldPilot as swap,
)


REFERENCE_HOLD_US = .1
HOLDS_US = (2.0, 5.0, 10.0, 20.0, 40.0, 60.0)
COLD_SPOT_HOLDS_US = (2.0, 10.0, 25.0, 50.0, 100.0, 200.0)
PLATEAU_HOLDS_US = (200.0, 500.0, 1000.0)
SHOTS = 800
REFERENCE_SHOTS = 400
RETURN_US = 40.0


def _normalized_scout_survival(row, delay, suffix):
    ground = float(row[f"P0{suffix}"])
    excited = float(row[f"P1{suffix}"])
    survival = float(row[f"Ps_{delay}us{suffix}"])
    contrast = excited - ground
    if not all(map(math.isfinite, (ground, excited, survival))) or contrast < .15:
        return math.nan
    return (survival - ground) / contrast


def select_reset_candidate(rows):
    """Qualify an isolated 25-us dip, then prefer its early 10-us sink rate."""
    indexed = {round(float(row["target_frequency_ghz"]), 3): row
               for row in rows}
    expected = {round(3.8 + .002 * index, 3) for index in range(251)}
    if len(rows) != 251 or set(indexed) != expected:
        raise ValueError("reset candidate needs a complete 251-point scout")
    candidates = {}
    for anchor in sorted(indexed):
        if not 3.820 <= anchor <= 4.280:
            continue
        try:
            candidate = confirm.select_crowded_wide_candidate(
                rows, preferred_center=anchor)
        except ValueError:
            continue
        center = candidate["center_ghz"]
        control = candidate["control_ghz"]
        advantages = {}
        for direction, suffix in (("combined", ""),
                                  ("up", "_scan_up"),
                                  ("down", "_scan_down")):
            feature = _normalized_scout_survival(indexed[center], 10, suffix)
            quiet = _normalized_scout_survival(indexed[control], 10, suffix)
            advantages[direction] = quiet - feature
        if (not all(math.isfinite(value) for value in advantages.values()) or
                min(advantages.values()) < .10):
            continue
        candidate = {**candidate, "anchor_ghz": center,
                     "early_advantage": min(advantages.values()),
                     "early_advantage_by_direction": advantages,
                     "selector": "wide_early_reset_candidate"}
        key = (center, control)
        candidates[key] = candidate
    if not candidates:
        raise ValueError("no qualified early-time loss sink with a quiet control")
    return max(candidates.values(), key=lambda item: (
        item["early_advantage"],
        min(item["depth_scan_up"], item["depth_scan_down"]),
        item["control_min_survival"]))


def _flank_quality(indexed, center, control, *, guard=False,
                   require_early=True):
    """Require three locally quiet scout points in both scan directions."""
    neighbors = [round(control + delta, 3) for delta in (-.002, 0, .002)]
    guard_points = ([round(control + delta, 3) for delta in (-.004, .004)]
                    if guard else [])
    if any(f not in indexed for f in (*neighbors, *guard_points)):
        return None
    margins = []
    for suffix in ("", "_scan_up", "_scan_down"):
        values = [_normalized_scout_survival(indexed[f], 25, suffix)
                  for f in neighbors]
        guards = [_normalized_scout_survival(indexed[f], 25, suffix)
                  for f in guard_points]
        control_10 = _normalized_scout_survival(indexed[control], 10, suffix)
        feature_10 = _normalized_scout_survival(indexed[center], 10, suffix)
        if (not all(math.isfinite(value) for value in
                    (*values, *guards, control_10, feature_10)) or
                min(values) < .65 or
                (guards and min(guards) < .65) or
                (require_early and control_10 - feature_10 < .10)):
            return None
        margins.append(min(values))
    return min(margins)


def _plateau_loss_feature(indexed, center):
    """Qualify a narrow dip while tolerating a one-bin directional shift."""
    groups = {
        "feature": [round(center + delta, 3)
                    for delta in (-.002, 0, .002)],
        "left": [round(center + delta, 3)
                 for delta in (-.008, -.006, -.004)],
        "right": [round(center + delta, 3)
                  for delta in (.004, .006, .008)],
    }
    if any(f not in indexed for group in groups.values() for f in group):
        return None
    depths = {}
    for suffix, direction in (("", "combined"), ("_scan_up", "up"),
                              ("_scan_down", "down")):
        values = {name: [_normalized_scout_survival(indexed[f], 25, suffix)
                         for f in frequencies]
                  for name, frequencies in groups.items()}
        if not all(math.isfinite(value) for group in values.values()
                   for value in group):
            return None
        if direction == "combined" and values["feature"][1] > min(
                values["feature"]) + 1e-9:
            return None
        feature = min(values["feature"])
        depths[direction] = min(np.median(values["left"]),
                                np.median(values["right"])) - feature
    if depths["combined"] < .15 or min(depths["up"], depths["down"]) < .08:
        return None
    return {"center_ghz": center, "anchor_ghz": center,
            "depth": float(depths["combined"]),
            "depth_scan_up": float(depths["up"]),
            "depth_scan_down": float(depths["down"])}


def select_plateau_candidate(rows):
    """Find one early-loss line and all independently qualified flanks."""
    indexed = {round(float(row["target_frequency_ghz"]), 3): row
               for row in rows}
    expected = {round(3.8 + .002 * index, 3) for index in range(251)}
    if len(rows) != 251 or set(indexed) != expected:
        raise ValueError("plateau candidate needs a complete 251-point scout")
    candidates = {}
    for anchor in sorted(indexed):
        if not 3.824 <= anchor <= 4.288:
            continue
        selected = _plateau_loss_feature(indexed, anchor)
        if selected is None:
            continue
        center = selected["center_ghz"]
        flanks = {}
        for side in (-1, 1):
            choices = []
            for offset_mhz in range(12, 25, 2):
                control = round(center + side * offset_mhz / 1000, 3)
                quality = _flank_quality(indexed, center, control, guard=True)
                if quality is not None:
                    choices.append((quality, -offset_mhz, control))
            if choices:
                flanks[side] = max(choices)[2]
        if not flanks:
            continue
        early_advantage = min(
            _normalized_scout_survival(indexed[f], 10, suffix) -
            _normalized_scout_survival(indexed[center], 10, suffix)
            for f in flanks.values()
            for suffix in ("", "_scan_up", "_scan_down"))
        if early_advantage < .10:
            continue
        primary = flanks.get(-1, flanks.get(1))
        candidates[center] = {
            **selected,
            "control_ghz": primary,
            "control_offset_ghz": round(primary - center, 3),
            "lower_control_ghz": flanks.get(-1),
            "upper_control_ghz": flanks.get(1),
            "flank_count": len(flanks),
            "early_advantage": early_advantage,
            "flank_min_survival": min(
                _flank_quality(indexed, center, control, guard=True)
                for control in flanks.values()),
            "selector": "shift_tolerant_early_loss_plateau_candidate",
        }
    if not candidates:
        raise ValueError("no early-loss feature with a clean flank")
    return max(candidates.values(), key=lambda item: (
        item["early_advantage"],
        min(item["depth_scan_up"], item["depth_scan_down"]),
        item["flank_count"],
        item["flank_min_survival"]))


def assess_plateau_post(rows, selected):
    """Allow a one-grid-step line shift but require both original flanks."""
    indexed = {round(float(row["target_frequency_ghz"]), 3): row
               for row in rows}
    center = selected["center_ghz"]
    centers = [round(center + delta, 3) for delta in (-.002, 0, .002)]
    if any(f not in indexed for f in centers):
        return {"valid": False, "reason": "feature outside post scout"}
    minima = {}
    for suffix, direction in (("", "combined"), ("_scan_up", "up"),
                              ("_scan_down", "down")):
        values = [(f, _normalized_scout_survival(indexed[f], 25, suffix))
                  for f in centers]
        if not all(math.isfinite(value) for _, value in values):
            return {"valid": False, "reason": "invalid post feature survival"}
        minima[direction] = min(values, key=lambda item: item[1])
    flank_quality = {}
    for side, key in (("lower", "lower_control_ghz"),
                      ("upper", "upper_control_ghz")):
        control = selected.get(key)
        if control is None:
            continue
        # Use the weakest of the three directional feature minima when
        # evaluating the original control, rather than reselecting a site.
        quality = _flank_quality(indexed, center, control,
                                 require_early=False)
        flank_quality[side] = quality
    quiet = bool(flank_quality) and all(
        value is not None for value in flank_quality.values())
    valid = (quiet and
             all(abs(f - center) <= .002001 for f, _ in minima.values()) and
             all(value < .60 for _, value in minima.values()) and
             min(flank_quality.values()) -
             max(value for _, value in minima.values()) >= .12)
    return {"valid": bool(valid), "feature_minima": minima,
            "flank_min_survival": flank_quality,
            "reason": None if valid else "feature or original flank changed"}


def program_specs(feature_ghz, control_ghz):
    specs = []
    for cycle in (0, 1):
        holds = HOLDS_US if cycle == 0 else tuple(reversed(HOLDS_US))
        for hold in holds:
            conditions = [
                {"name": f"{site}_{dwell}_{state}", "site": site,
                 "flux_ghz": float(frequency), "hold_us": duration,
                 "state": state}
                for site, frequency in (("feature", feature_ghz),
                                        ("control", control_ghz))
                for dwell, duration in (("early", REFERENCE_HOLD_US),
                                        ("late", hold))
                for state in ("g", "e")]
            if cycle:
                conditions.reverse()
            label = f"{hold:g}".replace(".", "p")
            specs.append({"name": f"r{cycle}_t{label}", "cycle": cycle,
                          "hold_us": hold, "shots": SHOTS,
                          "flux_ghz": float(feature_ghz),
                          "order": [condition["name"]
                                    for condition in conditions],
                          "conditions": conditions, "status": "pending"})
    return specs


def cold_spot_specs(feature_ghz, control_ghz):
    """Match a no-excursion park arm to each feature/control dwell."""
    specs = []
    for cycle in (0, 1):
        holds = COLD_SPOT_HOLDS_US if cycle == 0 else tuple(reversed(COLD_SPOT_HOLDS_US))
        for hold in holds:
            conditions = [
                {"name": f"{site}_{dwell}_{state}", "site": site,
                 "flux_ghz": float(frequency), "hold_us": duration,
                 "state": state}
                for site, frequency in (("feature", feature_ghz),
                                        ("control", control_ghz),
                                        ("park", feature_ghz))
                for dwell, duration in (("early", REFERENCE_HOLD_US),
                                        ("late", hold))
                for state in ("g", "e")]
            if cycle:
                conditions.reverse()
            label = f"{hold:g}".replace(".", "p")
            specs.append({"name": f"cold_r{cycle}_t{label}", "cycle": cycle,
                          "hold_us": hold, "shots": SHOTS,
                          "flux_ghz": float(feature_ghz),
                          "order": [item["name"] for item in conditions],
                          "conditions": conditions, "status": "pending"})
    return specs


def plateau_specs(feature_ghz, lower_ghz, upper_ghz):
    """Four matched sites in every shot, with late dwells to test the limit."""
    if lower_ghz is None and upper_ghz is None:
        raise ValueError("plateau needs at least one clean flank")
    sites = [("feature", feature_ghz)]
    if lower_ghz is not None:
        sites.append(("lower", lower_ghz))
    if upper_ghz is not None:
        sites.append(("upper", upper_ghz))
    sites.append(("park", feature_ghz))
    specs = []
    for cycle in (0, 1):
        holds = (PLATEAU_HOLDS_US if cycle == 0 else
                 tuple(reversed(PLATEAU_HOLDS_US)))
        for hold in holds:
            conditions = [
                {"name": f"{site}_{dwell}_{state}", "site": site,
                 "flux_ghz": float(frequency), "hold_us": duration,
                 "state": state}
                for site, frequency in sites
                for dwell, duration in (("early", REFERENCE_HOLD_US),
                                        ("late", hold))
                for state in ("g", "e")]
            if cycle:
                conditions.reverse()
            label = f"{hold:g}".replace(".", "p")
            specs.append({"name": f"plateau_r{cycle}_t{label}",
                          "cycle": cycle, "hold_us": hold,
                          "shots": SHOTS, "flux_ghz": float(feature_ghz),
                          "order": [item["name"] for item in conditions],
                          "conditions": conditions, "status": "pending"})
    return specs


def cold_spot_configs(base, entry, dc_lookup):
    configs = confirm._condition_configs(base, entry, dc_lookup)
    for arm, cfg in zip(entry["conditions"], configs):
        if arm["site"] == "park":
            cfg["ff_gain"] = int(base["ff_park_gain"])
    return configs


class ColdSpotProgram(confirm.EightSiteSwapHoldProgram):
    """Twelve complete feature/control/park subshots per logical shot."""

    def __init__(self, soccfg, condition_cfgs, payload_calibration, loop_calibration):
        configs = [dict(cfg) for cfg in condition_cfgs]
        if len(configs) != 12:
            raise ValueError("cold-spot program needs twelve conditions")
        common = ("ff_park_gain", "shots", "reps")
        if any(any(cfg[key] != configs[0][key] for key in common)
               for cfg in configs[1:]):
            raise ValueError("cold-spot subshots must share park and shots")
        observed = {(int(cfg["ff_gain"]), float(cfg["opx_swap_hold_us"]),
                     cfg["opx_resident_preparation_state"]) for cfg in configs}
        gains = {item[0] for item in observed}
        holds = {item[1] for item in observed}
        if (len(gains) != 3 or len(holds) != 2 or
                int(configs[0]["ff_park_gain"]) not in gains or
                observed != {(gain, hold, state) for gain in gains
                             for hold in holds for state in ("g", "e")}):
            raise ValueError("cold-spot subshots must cover three sites, two dwells, g/e")
        self.conditions_per_shot = 12
        self.logical_shots = int(configs[0]["shots"])
        self.condition_cfgs = configs
        # OPX initializes its flux correction from the constructor config.
        # Reversed streams start with a park arm, which would disable it.
        stepping_cfg = next(cfg for cfg in configs
                            if int(cfg["ff_gain"]) != int(cfg["ff_park_gain"]))
        run_cfg = dict(stepping_cfg, reps=12 * self.logical_shots)
        resident.ResidentDriveProgram.__init__(
            self, soccfg, run_cfg, payload_calibration, loop_calibration)

    def _resident_excursion(self):
        if int(self.cfg["ff_gain"]) == int(self.cfg["ff_park_gain"]):
            self.sync_all(self.us2cycles(
                float(self.cfg["opx_swap_hold_us"]) + RETURN_US))
        else:
            swap.SwapHoldProgram._resident_excursion(self)


class PlateauProgram(ColdSpotProgram):
    """Sixteen feature/lower/upper/park subshots with matched g/e arms."""

    def __init__(self, soccfg, condition_cfgs, payload_calibration, loop_calibration):
        configs = [dict(cfg) for cfg in condition_cfgs]
        if len(configs) != 16:
            raise ValueError("plateau program needs sixteen conditions")
        common = ("ff_park_gain", "shots", "reps")
        if any(any(cfg[key] != configs[0][key] for key in common)
               for cfg in configs[1:]):
            raise ValueError("plateau subshots must share park and shots")
        observed = {(int(cfg["ff_gain"]), float(cfg["opx_swap_hold_us"]),
                     cfg["opx_resident_preparation_state"]) for cfg in configs}
        gains = {item[0] for item in observed}
        holds = {item[1] for item in observed}
        if (len(gains) != 4 or len(holds) != 2 or
                int(configs[0]["ff_park_gain"]) not in gains or
                observed != {(gain, hold, state) for gain in gains
                             for hold in holds for state in ("g", "e")}):
            raise ValueError("plateau subshots must cover four sites, two dwells, g/e")
        self.conditions_per_shot = 16
        self.logical_shots = int(configs[0]["shots"])
        self.condition_cfgs = configs
        stepping_cfg = next(cfg for cfg in configs
                            if int(cfg["ff_gain"]) != int(cfg["ff_park_gain"]))
        run_cfg = dict(stepping_cfg, reps=16 * self.logical_shots)
        resident.ResidentDriveProgram.__init__(
            self, soccfg, run_cfg, payload_calibration, loop_calibration)


def split_cold_spot_records(records, order, *, shots):
    expected = {f"{site}_{dwell}_{state}"
                for site in ("feature", "control", "park")
                for dwell in ("early", "late") for state in ("g", "e")}
    records = list(records)
    if len(order) != 12 or set(order) != expected:
        raise ValueError("invalid twelve-condition cold-spot order")
    if len(records) != 12 * int(shots):
        raise ValueError("incomplete twelve-condition cold-spot stream")
    return {name: records[index::12] for index, name in enumerate(order)}


def split_plateau_records(records, order, *, shots):
    sites = {name.split("_", 1)[0] for name in order}
    if not ({"feature", "park"} <= sites and
            sites <= {"feature", "lower", "upper", "park"} and
            bool(sites & {"lower", "upper"})):
        raise ValueError("invalid plateau site set")
    expected = {f"{site}_{dwell}_{state}"
                for site in sites
                for dwell in ("early", "late") for state in ("g", "e")}
    records = list(records)
    if len(order) != len(expected) or set(order) != expected:
        raise ValueError("invalid plateau condition order")
    if len(records) != len(order) * int(shots):
        raise ValueError("incomplete plateau stream")
    return {name: records[index::len(order)]
            for index, name in enumerate(order)}


def score_plateau(fractions):
    sites = ("feature", "lower", "upper", "park")
    sites = tuple(site for site in sites
                  if f"{site}_early_g" in fractions)
    values = {name: float(fractions[name]) for name in (
        f"{site}_{dwell}_{state}"
        for site in sites
        for dwell in ("early", "late") for state in ("g", "e"))}
    return {"fractions": values,
            "late_contrast": {site: values[f"{site}_late_e"] -
                              values[f"{site}_late_g"]
                              for site in sites},
            "ground_increment": {site: values[f"{site}_late_g"] -
                                 values[f"{site}_early_g"]
                                 for site in sites}}


def score_cold_spot(fractions):
    values = {name: float(fractions[name]) for name in (
        f"{site}_{dwell}_{state}" for site in ("feature", "control", "park")
        for dwell in ("early", "late") for state in ("g", "e"))}
    def ground_increment(site):
        return values[f"{site}_late_g"] - values[f"{site}_early_g"]
    return {
        "fractions": values,
        "ground_feature_control_increment": (
            ground_increment("feature") - ground_increment("control")),
        "ground_feature_park_increment": (
            ground_increment("feature") - ground_increment("park")),
        "late_contrast": {site: values[f"{site}_late_e"] -
                          values[f"{site}_late_g"]
                          for site in ("feature", "control", "park")},
    }


def score_reset(fractions):
    values = {name: float(value) for name, value in fractions.items()}
    feature = {dwell: {state: values[f"feature_{dwell}_{state}"]
                       for state in ("g", "e")}
               for dwell in ("early", "late")}
    control = {dwell: {state: values[f"control_{dwell}_{state}"]
                       for state in ("g", "e")}
               for dwell in ("early", "late")}
    early_control_contrast = control["early"]["e"] - control["early"]["g"]
    late_control_contrast = control["late"]["e"] - control["late"]["g"]
    extra_cooling = control["late"]["e"] - feature["late"]["e"]
    extra_heating = feature["late"]["g"] - control["late"]["g"]
    early_cooling_offset = control["early"]["e"] - feature["early"]["e"]
    return {
        "feature": feature, "control": control,
        "extra_excited_cooling": extra_cooling,
        "incremental_excited_cooling": extra_cooling - early_cooling_offset,
        "extra_ground_heating": extra_heating,
        "early_control_contrast": early_control_contrast,
        "late_control_contrast": late_control_contrast,
        "cold_sink_candidate": bool(
            early_control_contrast >= .20 and extra_cooling >= .05 and
            extra_heating <= .05),
        "control_usable": bool(
            early_control_contrast >= .20 and
            control["late"]["g"] - control["early"]["g"] <= .08),
    }


def plan(*, cold_spot=False, plateau=False):
    if plateau:
        return {"hardware_access": False, "reset_mode": "passive",
                "purpose": "test whether the line changes late population, not just relaxation rate",
                "scout_range_ghz": [3.8, 4.3],
                "selection": "one fresh early-loss line with at least one locally quiet flank",
                "sites": ["feature", "one_or_two_flanks", "park_no_excursion"],
                "reference_hold_us": REFERENCE_HOLD_US,
                "later_holds_us": list(PLATEAU_HOLDS_US),
                "conditions_per_shot": [12, 16], "shots_per_program": SHOTS,
                "programs": 2 * len(PLATEAU_HOLDS_US),
                "condition_order": "feature, available flank(s), park; g/e and "
                                   "reference/test; reversed in block two",
                "full_return_before_readout_us": RETURN_US,
                "raw_iq_saved": True,
                "interpretation": "compare long-time g/e convergence at feature, "
                                  "available flank(s), and park; "
                                  "no defect temperature claim without population calibration"}
    if cold_spot:
        return {"hardware_access": False, "reset_mode": "passive",
                "purpose": "confirm feature-local reduction of ground-prepared excitation",
                "scout_range_ghz": [3.8, 4.3],
                "selection": "one fresh bidirectional early-loss line and quiet control",
                "sites": ["feature", "control", "park_no_excursion"],
                "reference_hold_us": REFERENCE_HOLD_US,
                "later_holds_us": list(COLD_SPOT_HOLDS_US),
                "conditions_per_shot": 12, "shots_per_program": SHOTS,
                "programs": 2 * len(COLD_SPOT_HOLDS_US),
                "condition_order": "feature/control/park, g/e, reference/test; "
                                   "reversed in second cycle",
                "full_return_before_readout_us": RETURN_US,
                "raw_iq_saved": True,
                "interpretation": "report baseline-corrected ground-state effect and "
                                  "g/e relaxation curves; no absolute temperature "
                                  "without return and population calibration"}
    return {"hardware_access": False, "reset_mode": "passive",
            "purpose": "test a fresh loss feature as a measurement-free reset sink",
            "scout_range_ghz": [3.8, 4.3],
            "selection": "qualified bidirectional loss with clean ±12–20-MHz control; "
                         "rank by 10-us rather than 25-us loss",
            "reference_hold_us": REFERENCE_HOLD_US,
            "later_holds_us": list(HOLDS_US), "conditions_per_shot": 8,
            "shots_per_program": SHOTS, "programs": 2 * len(HOLDS_US),
            "condition_order": "feature/control, g/e, reference/test; "
                               "all interleaved and reversed in second cycle",
            "full_return_before_readout_us": RETURN_US,
            "inter_shot_delay_us": 500.0,
            "raw_iq_saved": True,
            "interpretation": "report cooling, ground heating, and total reset latency; "
                              "do not infer an absolute fidelity from raw classifier fractions",
            "follow_up": "repeat-use stress test only if cooling is useful and controls pass"}


def _reference_arms(center):
    references = (probe.reference_arms(center, phase="pre") +
                  probe.reference_arms(center, phase="post"))
    for reference in references:
        reference.update(shots=REFERENCE_SHOTS, status="pending")
    return references


def _normalized_iq(records, axis, ground_iq, excited_iq):
    rotation = np.exp(-1j * axis["theta_rad"])
    ground = np.median(np.real(ground_iq * rotation))
    excited = np.median(np.real(excited_iq * rotation))
    if excited - ground <= 0:
        raise RuntimeError("readout IQ reference axis collapsed")
    return float((np.mean(np.real(resident.record_iq(records) * rotation)) -
                  ground) / (excited - ground))


def run(*, data_root=localizer.DATA_ROOT, correction_json=None,
        cold_spot=False, plateau=False):
    if cold_spot and plateau:
        raise ValueError("select one cold-spot mode")
    data_root = Path(data_root)
    correction = localizer.checked_correction(data_root, correction_json)
    scout = localizer.run(
        data_root=data_root, correction_json=correction,
        parameter_overrides={**wide.parameters(),
                             "output_suffix": ("TLS_Cold_Spot_Plateau_Scout_pre"
                                               if plateau else
                                               "TLS_Loss_Sink_Reset_Scout_pre")})
    selected = (select_plateau_candidate(swap.read_wide_scout(scout))
                if plateau else select_reset_candidate(swap.read_wide_scout(scout)))
    center = float(selected["center_ghz"])
    control = float(selected["control_ghz"])
    if plateau:
        lower = (float(selected["lower_control_ghz"])
                 if selected["lower_control_ghz"] is not None else None)
        upper = (float(selected["upper_control_ghz"])
                 if selected["upper_control_ghz"] is not None else None)
        print(f"[loss-sink-reset] feature={center:.3f} GHz; "
              f"quiet flank(s)={lower}, {upper} GHz; "
              f"10-us advantage={selected['early_advantage']:.3f}", flush=True)
    else:
        print(f"[loss-sink-reset] feature={center:.3f} GHz; "
              f"quiet control={control:.3f} GHz; "
              f"10-us advantage={selected['early_advantage']:.3f}", flush=True)

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
        specs = (plateau_specs(center, lower, upper) if plateau else
                 cold_spot_specs(center, control) if cold_spot else
                 program_specs(center, control))
        grid = np.asarray(([center] + [f for f in (lower, upper)
                                      if f is not None] if plateau else
                           [center, control]), dtype=float)
        dc, realized = _integer_dc_grid(wide.parameters(), grid, tls)
        dc_lookup = {float(f): int(g) for f, g in zip(grid, dc)}
        compensation = tls._load_correction(str(correction), str(data_root))
        holds = (PLATEAU_HOLDS_US if plateau else
                 COLD_SPOT_HOLDS_US if cold_spot else HOLDS_US)
        for hold in (REFERENCE_HOLD_US, *holds):
            swap.swap_segments(compensation, hold_us=hold)
        base = ProductionResetSession.passive().apply(tls.BaseConfig)
        five.apply_verified_feedback_timing(base)
        base.update({"apply_flux_tail_compensation": True,
                     "flux_tail_compensation": compensation,
                     "flux_fit_params": tls.FLUX_FIT_PARAMS,
                     "flux_settle_time_us": .5,
                     "flux_predistortion_return_prefix_us": .5,
                     "flux_predistortion_recovery_us": RETURN_US,
                     "flux_predistortion_overlap_payload_readout": False,
                     "flux_predistortion_round_trip_mode": "stateful",
                     "readout_thermalization_us": 10.0,
                     "qubit_pulse_style": "arb", "do_ff": True,
                     "opx_reset_scheme": "none",
                     "opx_resident_dmem_stream": True,
                     "opx_inter_shot_delay_us": 500.0})
        session_id = (("q3_tls_cold_spot_plateau_" if plateau else
                       "q3_tls_cold_spot_confirm_" if cold_spot else
                       "q3_tls_loss_sink_reset_") +
                      datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") +
                      "_" + uuid.uuid4().hex[:8])
        folder = data_root / "q3" / session_id
        folder.mkdir(parents=True, exist_ok=False)
        path = folder / "manifest.json"
        references = _reference_arms(center)
        manifest = {
            "schema": ("q3.tls-cold-spot-plateau.v1" if plateau else
                       "q3.tls-cold-spot-confirm.v1" if cold_spot else
                       "q3.tls-loss-sink-reset.v1"), "status": "running",
            "session_id": session_id,
            "code_commit": os.environ.get("Q3_CODE_COMMIT", "unknown"),
            "correction_json": str(correction),
            "correction_sha256": localizer.CORRECTION_SHA256,
            "scout_csv": str(scout), "selected": selected,
            "center_ghz": center, "control_ghz": control,
            "dc_lookup": {str(f): g for f, g in dc_lookup.items()},
            "realized_ghz": realized.tolist(),
            "plan": plan(cold_spot=cold_spot, plateau=plateau),
            "references": references, "programs": specs,
        }
        if plateau:
            manifest["controls_ghz"] = {
                side: frequency for side, frequency in
                (("lower", lower), ("upper", upper))
                if frequency is not None}
        protocol.checkpoint(path, manifest)
        print(f"[loss-sink-reset] manifest={path}", flush=True)
        raw_references = {}
        axis = None
        try:
            soc, soccfg = tls.makeProxy()
            bundle = runtime_bundle(base)
            programs = {}
            for entry in specs:
                cfgs = (cold_spot_configs(base, entry, dc_lookup)
                        if cold_spot or plateau
                        else confirm._condition_configs(base, entry, dc_lookup))
                program_class = (PlateauProgram if plateau and
                                 len(entry["order"]) == 16 else
                                 ColdSpotProgram if cold_spot else
                                 ColdSpotProgram if plateau else
                                 confirm.EightSiteSwapHoldProgram)
                programs[entry["name"]] = program_class(
                    soccfg, cfgs, bundle.payload, bundle.loop)
            for reference in references:
                resident.ResidentDriveProgram(
                    soccfg, resident.arm_config(base, reference, dc_lookup),
                    bundle.payload, bundle.loop)
            manifest["preflight_complete"] = True
            protocol.checkpoint(path, manifest)

            def acquire_reference(reference):
                nonlocal axis
                reference["status"] = "acquiring"
                protocol.checkpoint(path, manifest)
                cfg = resident.arm_config(base, reference, dc_lookup)
                program = resident.ResidentDriveProgram(
                    soccfg, cfg, bundle.payload, bundle.loop)
                records = _run_program(
                    soc, program,
                    max(30.0, _block_timeout_s(cfg, REFERENCE_SHOTS)),
                    cfg, total_shots=REFERENCE_SHOTS)
                if len(records) != REFERENCE_SHOTS:
                    raise RuntimeError(f"{reference['name']}: incomplete reference IQ")
                raw_references[reference["name"]] = records
                raw_path = folder / f"{reference['name']}.npz"
                np.savez_compressed(raw_path, i=[r.i for r in records],
                                    q=[r.q for r in records])
                reference["raw_npz"] = str(raw_path)
                if reference["name"] == "ref_e_pre":
                    axis = resident.fit_axis(
                        resident.record_iq(raw_references["ref_g_pre"]),
                        resident.record_iq(records))
                    manifest["pre_readout_axis"] = axis
                    if not axis["valid"]:
                        raise RuntimeError("pre-run readout reference invalid")
                if axis is not None:
                    reference["excited_fraction_pre_axis"] = resident.classify(
                        records, axis)
                reference["status"] = "complete"
                protocol.checkpoint(path, manifest)

            for reference in references[:4]:
                print(f"[loss-sink-reset] {reference['name']}", flush=True)
                acquire_reference(reference)
            ground_iq = resident.record_iq(raw_references["ref_g_pre"])
            excited_iq = resident.record_iq(raw_references["ref_e_pre"])
            if (resident.classify(raw_references["ref_transfer_e_pre"], axis) -
                    resident.classify(raw_references["ref_transfer_g_pre"], axis)
                    < .15):
                raise RuntimeError("park-prepared state fails transfer control")

            for entry in specs:
                entry["status"] = "acquiring"
                entry["acquisition_started_at_utc"] = (
                    datetime.now(timezone.utc).isoformat())
                protocol.checkpoint(path, manifest)
                print(f"[loss-sink-reset] {entry['name']} "
                      f"{entry['shots']} x {len(entry['order'])}", flush=True)
                start = time.monotonic()
                records = _run_program(
                    soc, programs[entry["name"]],
                    max(30.0, len(entry["order"]) *
                        _block_timeout_s(
                            dict(base, ff_hold=entry["hold_us"] + RETURN_US),
                            entry["shots"])),
                    base, total_shots=entry["shots"])
                entry["acquisition_elapsed_s"] = time.monotonic() - start
                entry["acquisition_finished_at_utc"] = (
                    datetime.now(timezone.utc).isoformat())
                split = (split_plateau_records(records, entry["order"],
                                               shots=entry["shots"])
                         if plateau else
                         split_cold_spot_records(records, entry["order"],
                                                 shots=entry["shots"])
                         if cold_spot else confirm.split_eight_records(
                             records, entry["order"], shots=entry["shots"]))
                for condition in entry["conditions"]:
                    subset = split[condition["name"]]
                    raw_path = folder / f"{entry['name']}_{condition['name']}.npz"
                    np.savez_compressed(raw_path, i=[r.i for r in subset],
                                        q=[r.q for r in subset])
                    condition["raw_npz"] = str(raw_path)
                    condition["excited_fraction_pre_axis"] = resident.classify(
                        subset, axis)
                    condition["projected_iq_pre_axis"] = _normalized_iq(
                        subset, axis, ground_iq, excited_iq)
                fractions = {
                    condition["name"]: condition["excited_fraction_pre_axis"]
                    for condition in entry["conditions"]}
                entry["score"] = (score_plateau(fractions) if plateau else
                                  score_cold_spot(fractions) if cold_spot else
                                  score_reset(fractions))
                entry["status"] = "complete"
                protocol.checkpoint(path, manifest)

            for reference in references[4:]:
                print(f"[loss-sink-reset] {reference['name']}", flush=True)
                acquire_reference(reference)
            manifest["post_readout_score"] = resident.score_axis(
                axis, resident.record_iq(raw_references["ref_g_post"]),
                resident.record_iq(raw_references["ref_e_post"]))
            manifest["transfer_control"] = {
                phase: {"ground": resident.classify(
                            raw_references[f"ref_transfer_g_{phase}"], axis),
                        "excited": resident.classify(
                            raw_references[f"ref_transfer_e_{phase}"], axis)}
                for phase in ("pre", "post")}
            for result in manifest["transfer_control"].values():
                result["usable"] = resident.transfer_usable(
                    result["ground"], result["excited"])

            post_scout = localizer.run(
                data_root=data_root, correction_json=correction,
                parameter_overrides={**wide.parameters(),
                                     "output_suffix": ("TLS_Cold_Spot_Plateau_Scout_post"
                                                       if plateau else
                                                       "TLS_Loss_Sink_Reset_Scout_post")})
            manifest["post_scout_csv"] = str(post_scout)
            try:
                post_rows = swap.read_wide_scout(post_scout)
                if plateau:
                    manifest["post_plateau_assessment"] = assess_plateau_post(
                        post_rows, selected)
                else:
                    manifest["post_selected"] = (
                        confirm.select_crowded_wide_candidate(
                            post_rows, preferred_center=center,
                            preferred_control_ghz=control))
            except ValueError as exc:
                manifest["post_selection_error"] = str(exc)
            manifest["feature_stable"] = bool(
                manifest.get("post_plateau_assessment", {}).get("valid")
                if plateau else "post_selected" in manifest and
                resident.feature_stable(selected, manifest["post_selected"]))
            manifest["control_usable"] = bool(
                manifest["post_readout_score"]["valid"] and
                all(item["usable"] for item in
                    manifest["transfer_control"].values()) and
                (cold_spot or plateau or all(entry["score"]["control_usable"]
                                  for entry in specs)))
            manifest["status"] = (
                "complete" if manifest["feature_stable"] and
                manifest["control_usable"] else "complete_controls_unstable")
            protocol.checkpoint(path, manifest)
            print(f"[loss-sink-reset] {manifest['status']}; "
                  f"manifest={path}", flush=True)
            return path
        except Exception as exc:
            manifest["status"] = "failed"
            manifest["error"] = f"{type(exc).__name__}: {exc}"
            protocol.checkpoint(path, manifest)
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--data-root", default=str(localizer.DATA_ROOT))
    parser.add_argument("--correction-json")
    parser.add_argument("--cold-spot", action="store_true",
                        help="confirm ground-prepared cooling with a park control")
    parser.add_argument("--plateau", action="store_true",
                        help="test long-time convergence with two flank controls")
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(plan(cold_spot=args.cold_spot,
                              plateau=args.plateau), indent=2))
        return 0
    run(data_root=args.data_root, correction_json=args.correction_json,
        cold_spot=args.cold_spot, plateau=args.plateau)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
