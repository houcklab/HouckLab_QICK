"""Shot-alternating target-resident pump/probe and timing controls.

Each hardware shot contains four or eight complete park-preparation,
corrected target-visit, return, and readout sequences. Cold/hot and sham/on
conditions are separated by milliseconds inside one compiled program,
rather than by separate Python acquisitions. Forward and reverse orders diagnose
condition-order carryover. Optional modes compare loading time or short/long
loss at the feature and flank. None of these alone establishes a TLS claim.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
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
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.programs import (
    _declare_common, _reserved_registers, allocate_named_registers,
    allocate_registers, resident_control_names,
)


SHOTS = 200
LOSS_SHOTS = 400
REFERENCE_SHOTS = 400
CONDITION_NAMES = ("sham_g", "sham_e", "on_g", "on_e")
LOADING_PREHOLDS_US = (4.0, 8.0, 12.0, 20.0)
LOSS_POSTHOLDS_US = (0.1, 2.0)
SATURATION_POSTHOLDS_US = (1.5, 16.0)
SATURATION_SHOTS = 1500
PAIRED_CYCLES = 8
PAIRED_SHOTS = 500
STRONG_LOAD_US = 12.0
STRONG_GAIN = 30000
MAPPED_GAIN = 20000
MAPPED_ON_DETUNING_MHZ = 5.0
MAPPED_OFF_DETUNING_MHZ = 20.0
MAPPED_CALIBRATION_SESSION_ID = (
    "q3_pump_probe_resident_drive_fresh_map_20260928T175415Z_eae54320")


def conditions(center_ghz, *, reverse=False, detuning_mhz=5.0,
               drive_gain=6000):
    center = float(center_ghz)
    result = [{"name": name, "preparation_state": name[-1],
               "gain": drive_gain if name.startswith("on") else 0,
               "drive_mhz": round(1000.0 * center + float(detuning_mhz), 3)}
              for name in CONDITION_NAMES]
    return list(reversed(result)) if reverse else result


def split_records(records, order, *, shots, holds=LOSS_POSTHOLDS_US,
                  paired_tones=False):
    records = list(records)
    if paired_tones and holds == LOSS_POSTHOLDS_US:
        holds = SATURATION_POSTHOLDS_US
    if len(records) != int(shots) * len(order):
        raise ValueError(f"expected {int(shots) * len(order)} IQ records; got {len(records)}")
    expected = ({f"{tone}_hold{hold:g}".replace(".", "p") + f"_{name}"
                 for tone in ("on", "detuned") for hold in holds
                 for name in CONDITION_NAMES}
                if paired_tones and len(order) == 16 else
                set(CONDITION_NAMES) if len(order) == 4 else
                {f"hold{hold:g}".replace(".", "p") + f"_{name}"
                 for hold in holds for name in CONDITION_NAMES}
                if len(order) == 8 else set())
    if set(order) != expected or len(order) != len(expected):
        raise ValueError("interleaved order must contain each condition exactly once")
    return {name: records[index::len(order)] for index, name in enumerate(order)}


def stream_dimensions(shots, *, records_per_shot=4):
    return {"total_shots": int(shots), "records_per_shot": int(records_per_shot),
            "total_units": int(shots), "records_per_unit": int(records_per_shot)}


def score_conditions(fractions):
    x = {name: float(fractions[name]) for name in CONDITION_NAMES}
    return {"fractions": x,
            "cold_drive_contrast": x["on_g"] - x["sham_g"],
            "hot_preparation_contrast": x["sham_e"] - x["sham_g"],
            "hot_minus_cold_drive_change": (
                x["on_e"] - x["on_g"] - x["sham_e"] + x["sham_g"])}


def loading_program_specs(center_ghz):
    """Pair each target loading time across reversed within-shot orders."""
    result = []
    for direction, preholds in (("forward", LOADING_PREHOLDS_US),
                                ("reverse", tuple(reversed(LOADING_PREHOLDS_US)))):
        for pre in preholds:
            condition_list = conditions(center_ghz, reverse=(direction == "reverse"))
            result.append({"name": f"load{pre:g}_{direction}",
                           "direction": direction, "pre_drive_us": pre,
                           "post_drive_us": resident.POST_DRIVE_US,
                           "order": [x["name"] for x in condition_list],
                           "conditions": condition_list})
    return result


def loss_program_specs(center_ghz):
    """Repeat a feature/flank, hold, and tone comparison in reversed order."""
    center = float(center_ghz)
    flank = round(center + resident.FLANK_OFFSET_GHZ, 3)
    result = []
    for repeat in (0, 1):
        sites = (("feature", center), ("flank", flank))
        holds = LOSS_POSTHOLDS_US
        tones = (("on", 5.0), ("detuned", -10.0))
        if repeat:
            sites, holds, tones = (tuple(reversed(x)) for x in (sites, holds, tones))
        direction = "reverse" if repeat else "forward"
        for site, flux in sites:
            for hold in holds:
                for tone, detuning in tones:
                    condition_list = conditions(
                        flux, reverse=bool(repeat), detuning_mhz=detuning)
                    result.append({
                        "name": f"r{repeat}_{site}_hold{hold:g}_{tone}".replace(".", "p"),
                        "repeat": repeat, "direction": direction,
                        "site": site, "flux_ghz": flux, "tone": tone,
                        "detuning_mhz": detuning,
                        "pre_drive_us": resident.PRE_DRIVE_US,
                        "post_drive_us": hold, "shots": LOSS_SHOTS,
                        "order": [x["name"] for x in condition_list],
                        "conditions": condition_list})
    return result


def hold_alternating_specs(center_ghz, *, holds=LOSS_POSTHOLDS_US,
                           shots=LOSS_SHOTS, pre_drive_us=resident.PRE_DRIVE_US,
                           drive_gain=6000, on_detuning_mhz=5.0,
                           off_detuning_mhz=-10.0, flank_ghz=None):
    """Alternate the two loss-probe holds inside each hardware shot."""
    center = float(center_ghz)
    flank = (round(center + resident.FLANK_OFFSET_GHZ, 3) if flank_ghz is None
             else float(flank_ghz))
    result = []
    for repeat in (0, 1):
        sites = (("feature", center), ("flank", flank))
        tones = (("on", float(on_detuning_mhz)),
                 ("detuned", float(off_detuning_mhz)))
        ordered_holds = tuple(holds)
        if repeat:
            sites = tuple(reversed(sites))
            tones = tuple(reversed(tones))
            ordered_holds = tuple(reversed(ordered_holds))
        direction = "reverse" if repeat else "forward"
        for site, flux in sites:
            for tone, detuning in tones:
                condition_list = []
                for hold in ordered_holds:
                    prefix = f"hold{hold:g}".replace(".", "p")
                    for base in conditions(flux, reverse=bool(repeat),
                                           detuning_mhz=detuning,
                                           drive_gain=drive_gain):
                        condition_list.append({**base, "base_name": base["name"],
                                               "name": f"{prefix}_{base['name']}",
                                               "post_drive_us": hold})
                result.append({
                    "name": f"r{repeat}_{site}_{tone}", "repeat": repeat,
                    "direction": direction, "site": site, "flux_ghz": flux,
                    "tone": tone, "detuning_mhz": detuning,
                    "pre_drive_us": pre_drive_us,
                    "shots": shots, "order": [x["name"] for x in condition_list],
                    "conditions": condition_list})
    return result


def short_gap_saturation_specs(center_ghz, *, strong=False, load_us=None):
    """Load a feature, re-excite at the target, then compare long probe holds."""
    if load_us is None:
        load_us = STRONG_LOAD_US if strong else resident.PRE_DRIVE_US
    return hold_alternating_specs(center_ghz, holds=SATURATION_POSTHOLDS_US,
                                  shots=SATURATION_SHOTS,
                                  pre_drive_us=float(load_us),
                                  drive_gain=(STRONG_GAIN if strong else 6000))


def mapped_short_gap_specs(center_ghz, *, flank_ghz=None):
    """Use the freshly mapped pulse for the actual hot/cold pump–probe."""
    return hold_alternating_specs(
        center_ghz, holds=SATURATION_POSTHOLDS_US,
        shots=SATURATION_SHOTS, pre_drive_us=resident.PRE_DRIVE_US,
        drive_gain=MAPPED_GAIN, on_detuning_mhz=MAPPED_ON_DETUNING_MHZ,
        off_detuning_mhz=MAPPED_OFF_DETUNING_MHZ, flank_ghz=flank_ghz)


def paired_tone_specs(center_ghz, flank_ghz, *, cycles=PAIRED_CYCLES,
                      shots=PAIRED_SHOTS):
    """Put both tones, both holds, and hot/cold sham/drive in each shot."""
    result = []
    for cycle in range(int(cycles)):
        reverse = bool(cycle % 2)
        sites = (("feature", float(center_ghz)), ("flank", float(flank_ghz)))
        if reverse:
            sites = tuple(reversed(sites))
        for site, flux in sites:
            tones = (("on", MAPPED_ON_DETUNING_MHZ),
                     ("detuned", MAPPED_OFF_DETUNING_MHZ))
            holds = SATURATION_POSTHOLDS_US
            if reverse:
                tones, holds = tuple(reversed(tones)), tuple(reversed(holds))
            entries = []
            for tone, detuning in tones:
                for hold in holds:
                    label = f"{tone}_hold{hold:g}".replace(".", "p")
                    for base in conditions(flux, reverse=reverse,
                                           detuning_mhz=detuning,
                                           drive_gain=MAPPED_GAIN):
                        entries.append({**base, "tone": tone,
                                        "base_name": base["name"],
                                        "name": f"{label}_{base['name']}",
                                        "post_drive_us": hold})
            result.append({"name": f"cycle{cycle}_{site}", "cycle": cycle,
                           "repeat": cycle, "site": site, "flux_ghz": flux,
                           "direction": "reverse" if reverse else "forward",
                           "pre_drive_us": resident.PRE_DRIVE_US,
                           "shots": int(shots),
                           "order": [x["name"] for x in entries],
                           "conditions": entries})
    return result


def mapped_drive_checks(center_ghz, flank_ghz):
    """Bracket the mapped pulse at each new flux coordinate before science."""
    arms = []
    for site, flux in (("feature", center_ghz), ("flank", flank_ghz)):
        for tone, gain, detuning in (
            ("sham_a", 0, MAPPED_ON_DETUNING_MHZ),
            ("on_20000", MAPPED_GAIN, MAPPED_ON_DETUNING_MHZ),
            ("detuned_20000", MAPPED_GAIN, MAPPED_OFF_DETUNING_MHZ),
            ("sham_b", 0, MAPPED_ON_DETUNING_MHZ),
        ):
            arms.append({"name": f"drivecheck_{site}_{tone}",
                         "drive_check": True, "site": site, "tone": tone,
                         "flux_ghz": float(flux),
                         "drive_mhz": round(1000.0 * float(flux) + detuning, 3),
                         "gain": gain, "preparation_state": "g",
                         "pre_drive_us": resident.PRE_DRIVE_US,
                         "post_drive_us": resident.POST_DRIVE_US,
                         "shots": 200})
    return arms


def evaluate_mapped_drive_check(fractions):
    result = {key: float(value) for key, value in fractions.items()}
    sham = (result["sham_a"] + result["sham_b"]) / 2.0
    result.update({"on_excess": result["on_20000"] - sham,
                   "detuned_excess": result["detuned_20000"] - sham,
                   "bracket_drift": abs(result["sham_b"] - result["sham_a"])})
    result["usable"] = bool(result["on_excess"] >= 0.10 and
                            abs(result["detuned_excess"]) <= 0.10 and
                            result["bracket_drift"] <= 0.10)
    return result


def checked_mapped_calibration(data_root):
    """Require a complete, stable map with a selective response at both sites."""
    path = (Path(data_root) / "q3" / MAPPED_CALIBRATION_SESSION_ID /
            "manifest.json")
    manifest = json.loads(path.read_text())
    if (manifest.get("schema") != "q3.pump-probe-resident-drive-fresh-map.v1" or
            manifest.get("status") != "complete" or
            manifest.get("correction_sha256") != localizer.CORRECTION_SHA256 or
            not manifest.get("feature_stable") or
            not manifest.get("pre_readout_valid") or
            not manifest.get("post_readout_score", {}).get("valid") or
            not all(manifest.get("transfer_control", {}).get(phase, {}).get("usable")
                    for phase in ("pre", "post"))):
        raise ValueError("fresh resident-drive map failed stability or calibration controls")
    prior_plan = manifest.get("plan", {})
    if (prior_plan.get("pre_drive_us") != resident.PRE_DRIVE_US or
            prior_plan.get("post_drive_us") != resident.POST_DRIVE_US or
            MAPPED_GAIN not in prior_plan.get("driven_gains_dac", ())):
        raise ValueError("fresh resident-drive map used different pulse settings")
    for site in ("feature", "flank"):
        for detuning in (MAPPED_ON_DETUNING_MHZ, MAPPED_OFF_DETUNING_MHZ):
            arms = [a for a in manifest["arms"] if a.get("site") == site and
                    a.get("detuning_mhz") == detuning]
            if (len(arms) < 3 or arms[0].get("gain") != 0 or
                    arms[-1].get("gain") != 0 or
                    any(a.get("status") != "complete" for a in arms)):
                raise ValueError(f"{site}: mapped drive brackets incomplete")
            driven = [a for a in arms if a.get("gain") == MAPPED_GAIN]
            if len(driven) != 1:
                raise ValueError(f"{site}: mapped drive arm incomplete")
            sham = (arms[0]["excited_fraction_pre_axis"] +
                    arms[-1]["excited_fraction_pre_axis"]) / 2.0
            excess = driven[0]["excited_fraction_pre_axis"] - sham
            if (detuning == MAPPED_ON_DETUNING_MHZ and excess < 0.10 or
                    detuning == MAPPED_OFF_DETUNING_MHZ and abs(excess) > 0.10):
                raise ValueError(f"{site}: mapped {detuning:+g}-MHz contrast failed")
    return path, manifest


def strong_drive_checks(center_ghz, flank_ghz, *, load_us=STRONG_LOAD_US):
    """Check gain 30000 at both current flux sites with sham brackets."""
    result = probe.carryover_drive_checks(center_ghz, flank_ghz)
    for arm in result:
        arm["pre_drive_us"] = float(load_us)
        if arm["tone"] in ("on_6000", "detuned_6000"):
            arm["gain"] = STRONG_GAIN
            arm["tone"] = arm["tone"].replace("6000", "30000")
            arm["name"] = arm["name"].replace("6000", "30000")
    return result


def evaluate_strong_drive_check(fractions):
    result = {key: float(value) for key, value in fractions.items()}
    sham = (result["sham_a"] + result["sham_b"]) / 2.0
    result.update({"on_excess": result["on_30000"] - sham,
                   "detuned_excess": result["detuned_30000"] - sham,
                   "bracket_drift": abs(result["sham_b"] - result["sham_a"])})
    result["usable"] = bool(result["on_excess"] >= 0.10 and
                            abs(result["detuned_excess"]) <= 0.10 and
                            result["bracket_drift"] <= 0.10)
    return result


def loss_control_report(scores):
    """Check drive specificity and sham baselines at both probe holds."""
    groups = {}
    for repeat in (0, 1):
        for site in ("feature", "flank"):
            for hold in ("0p1", "2"):
                on = scores[f"r{repeat}_{site}_hold{hold}_on"]
                detuned = scores[f"r{repeat}_{site}_hold{hold}_detuned"]
                hot_floor = 0.10 if hold == "0p1" else 0.05
                spread = abs(on["hot_preparation_contrast"] -
                             detuned["hot_preparation_contrast"])
                groups[f"r{repeat}_{site}_hold{hold}"] = {
                    "on_cold_drive_contrast": on["cold_drive_contrast"],
                    "detuned_cold_drive_contrast": detuned["cold_drive_contrast"],
                    "on_sham_hot_contrast": on["hot_preparation_contrast"],
                    "detuned_sham_hot_contrast": detuned["hot_preparation_contrast"],
                    "sham_hot_spread": spread, "minimum_sham_hot_contrast": hot_floor,
                    "usable": bool((hold != "0p1" or
                                    on["cold_drive_contrast"] >= 0.10) and
                                   abs(detuned["cold_drive_contrast"]) <= 0.10 and
                                   min(on["hot_preparation_contrast"],
                                       detuned["hot_preparation_contrast"]) >= hot_floor and
                                   spread <= 0.20)}
    return {"groups": groups,
            "usable": all(group["usable"] for group in groups.values())}


def loss_effect_report(scores):
    """Prespecified driven loss contrast after detuned and flank subtraction."""
    report = {}
    for repeat in (0, 1):
        row = {}
        for site in ("feature", "flank"):
            for tone in ("on", "detuned"):
                short = scores[f"r{repeat}_{site}_hold0p1_{tone}"][
                    "hot_minus_cold_drive_change"]
                long = scores[f"r{repeat}_{site}_hold2_{tone}"][
                    "hot_minus_cold_drive_change"]
                row[f"{site}_{tone}_incremental_loss"] = float(short - long)
        row["feature_specific_tone_selective_incremental_loss"] = (
            row["feature_on_incremental_loss"] -
            row["feature_detuned_incremental_loss"] -
            row["flank_on_incremental_loss"] +
            row["flank_detuned_incremental_loss"])
        report[f"r{repeat}"] = row
    return report


def short_gap_saturation_report(scores, *, repeats=range(2)):
    """Compare hot/cold survival ratios after their unequal short-time starts."""
    short, long = (f"hold{hold:g}".replace(".", "p")
                   for hold in SATURATION_POSTHOLDS_US)
    report = {}
    for repeat in repeats:
        row = {}
        for site in ("feature", "flank"):
            prefix = f"r{repeat}_{site}_"
            early = scores[f"{prefix}{short}_on"]["fractions"]
            late = scores[f"{prefix}{long}_on"]["fractions"]
            for loading, name in (("e", "loaded"), ("g", "cold")):
                early_signal = early[f"on_{loading}"] - early["sham_g"]
                late_signal = late[f"on_{loading}"] - late["sham_g"]
                row[f"{site}_{name}_early_signal"] = early_signal
                row[f"{site}_{name}_late_signal"] = late_signal
                row[f"{site}_{name}_survival"] = (
                    float(late_signal / early_signal) if early_signal > 0.05
                    else float("nan"))
            row[f"{site}_loaded_survival_advantage"] = (
                row[f"{site}_loaded_survival"] - row[f"{site}_cold_survival"])
        row["feature_specific_loaded_survival_advantage"] = (
            row["feature_loaded_survival_advantage"] -
            row["flank_loaded_survival_advantage"])
        report[f"r{repeat}"] = row
    return report


def short_gap_saturation_controls(scores, *, repeats=range(2)):
    """Gate pulse preparation at the short hold without demanding late feature survival."""
    short, long = (f"hold{hold:g}".replace(".", "p")
                   for hold in SATURATION_POSTHOLDS_US)
    groups = {}
    for repeat in repeats:
        for site in ("feature", "flank"):
            name = f"r{repeat}_{site}"
            early_on = scores[f"{name}_{short}_on"]
            early_off = scores[f"{name}_{short}_detuned"]
            late_on = scores[f"{name}_{long}_on"]
            late_off = scores[f"{name}_{long}_detuned"]
            groups[name] = {
                "short_cold_drive": early_on["cold_drive_contrast"],
                "short_loaded_signal": (
                    early_on["fractions"]["on_e"] -
                    early_on["fractions"]["sham_g"]),
                "short_detuned_drive": early_off["cold_drive_contrast"],
                "short_sham_hot": early_on["hot_preparation_contrast"],
                "late_cold_drive": late_on["cold_drive_contrast"],
                "late_detuned_drive": late_off["cold_drive_contrast"],
                "usable": bool(early_on["cold_drive_contrast"] >= 0.10 and
                               early_on["fractions"]["on_e"] -
                               early_on["fractions"]["sham_g"] >= 0.10 and
                               abs(early_off["cold_drive_contrast"]) <= 0.10 and
                               early_on["hot_preparation_contrast"] >= 0.05 and
                               early_off["hot_preparation_contrast"] >= 0.05 and
                               abs(early_on["hot_preparation_contrast"] -
                                   early_off["hot_preparation_contrast"]) <= 0.20 and
                               abs(late_off["cold_drive_contrast"]) <= 0.10 and
                               (site != "flank" or
                                late_on["cold_drive_contrast"] >= 0.05))}
    return {"groups": groups,
            "usable": all(group["usable"] for group in groups.values())}


def paired_cycle_quality(groups):
    """Keep only complete feature/flank pairs with both condition orders."""
    qualified = [cycle for cycle in range(PAIRED_CYCLES)
                 if all(groups[f"r{cycle}_{site}"]["usable"]
                        for site in ("feature", "flank"))]
    parity_counts = {"forward": sum(cycle % 2 == 0 for cycle in qualified),
                     "reverse": sum(cycle % 2 == 1 for cycle in qualified)}
    return {"qualified_cycles": qualified,
            "qualified_count": len(qualified),
            "parity_counts": parity_counts,
            "usable": bool(len(qualified) >= 6 and
                           min(parity_counts.values()) >= 2)}


def program_scores(entries, *, hold_alternating=False, holds=LOSS_POSTHOLDS_US,
                   paired_tones=False):
    if paired_tones and holds == LOSS_POSTHOLDS_US:
        holds = SATURATION_POSTHOLDS_US
    scores = {}
    for entry in entries:
        if paired_tones:
            for tone in ("on", "detuned"):
                for hold in holds:
                    hold_label = f"hold{hold:g}".replace(".", "p")
                    fractions = {c["base_name"]: c["excited_fraction_pre_axis"]
                                 for c in entry["conditions"]
                                 if c["tone"] == tone and c["post_drive_us"] == hold}
                    scores[f"r{entry['cycle']}_{entry['site']}_{hold_label}_{tone}"] = (
                        score_conditions(fractions))
        elif hold_alternating:
            for hold in holds:
                hold_label = f"hold{hold:g}".replace(".", "p")
                fractions = {c["base_name"]: c["excited_fraction_pre_axis"]
                             for c in entry["conditions"]
                             if c["post_drive_us"] == hold}
                scores[f"r{entry['repeat']}_{entry['site']}_{hold_label}_"
                       f"{entry['tone']}"] = score_conditions(fractions)
        else:
            fractions = {c["name"]: c["excited_fraction_pre_axis"]
                         for c in entry["conditions"]}
            scores[entry["name"]] = score_conditions(fractions)
    return scores


def usable_loading_times(scores):
    """Select preholds with repeatable hot preparation and local drive response."""
    usable = []
    for pre in LOADING_PREHOLDS_US:
        forward = scores[f"load{pre:g}_forward"]
        reverse = scores[f"load{pre:g}_reverse"]
        if (all(x["hot_preparation_contrast"] >= 0.10 and
                x["cold_drive_contrast"] >= 0.10 for x in (forward, reverse)) and
                abs(forward["hot_minus_cold_drive_change"] -
                    reverse["hot_minus_cold_drive_change"]) <= 0.25):
            usable.append(pre)
    return usable


def fresh_drive_arms(center_ghz):
    """Four short, locally bracketed drive checks at the current loss flux."""
    return [arm for arm in probe.carryover_drive_checks(
        center_ghz, center_ghz + resident.FLANK_OFFSET_GHZ)
            if arm["site"] == "feature"]


def condition_configs(base, entry, dc_lookup, center_ghz):
    """Apply each program's actual flux coordinate, hold, and shot count."""
    return [resident.arm_config(
        base, {"flux_ghz": entry.get("flux_ghz", center_ghz),
               "drive_mhz": cond["drive_mhz"], "gain": cond["gain"],
               "preparation_state": cond["preparation_state"],
               "pre_drive_us": entry["pre_drive_us"],
               "post_drive_us": cond.get("post_drive_us", entry.get("post_drive_us")),
               "shots": entry.get("shots", SHOTS)}, dc_lookup)
            for cond in entry["conditions"]]


def drive_check_gate(score, *, loading_check):
    if score["usable"]:
        return "passed"
    if loading_check:
        # This diagnostic measures drive contrast independently at every
        # loading time, including the checked 8-us time.
        return "diagnostic_only"
    raise RuntimeError(f"fresh feature drive check failed: {score}")


class ShotAlternatingResidentProgram(resident.ResidentDriveProgram):
    """Four, eight, or sixteen complete resident-probe subshots per shot."""

    def __init__(self, soccfg, condition_cfgs, payload_calibration, loop_calibration):
        configs = [dict(cfg) for cfg in condition_cfgs]
        if len(configs) not in (4, 8, 16):
            raise ValueError("four, eight, or sixteen condition configurations are required")
        self.conditions_per_shot = len(configs)
        common = ("ff_gain", "ff_park_gain", "opx_resident_pre_us",
                  "shots", "reps")
        if self.conditions_per_shot != 16:
            common += ("opx_resident_freq_mhz",)
        if self.conditions_per_shot == 4:
            common += ("opx_resident_post_us",)
        if any(any(cfg[key] != configs[0][key] for key in common)
               for cfg in configs[1:]):
            raise ValueError("interleaved conditions must share flux, timing, frequency, shots")
        actual_holds = ({float(cfg["opx_resident_post_us"]) for cfg in configs}
                        if self.conditions_per_shot in (8, 16) else set())
        actual_freqs = {float(cfg["opx_resident_freq_mhz"]) for cfg in configs}
        actual_gains = {int(cfg["opx_resident_gain"]) for cfg in configs}
        if self.conditions_per_shot == 4:
            observed = {(int(cfg["opx_resident_gain"]),
                         cfg["opx_resident_preparation_state"]) for cfg in configs}
            valid = observed == {(0, "g"), (0, "e"), (6000, "g"), (6000, "e")}
        elif self.conditions_per_shot == 8:
            observed = {(float(cfg["opx_resident_post_us"]),
                         int(cfg["opx_resident_gain"]),
                         cfg["opx_resident_preparation_state"]) for cfg in configs}
            valid = observed == {(hold, gain, state) for hold in actual_holds
                                 for gain in actual_gains for state in ("g", "e")}
        else:
            observed = {(float(cfg["opx_resident_freq_mhz"]),
                         float(cfg["opx_resident_post_us"]),
                         int(cfg["opx_resident_gain"]),
                         cfg["opx_resident_preparation_state"]) for cfg in configs}
            valid = observed == {(freq, hold, gain, state)
                                 for freq in actual_freqs for hold in actual_holds
                                 for gain in actual_gains for state in ("g", "e")}
        if (not valid or
                (self.conditions_per_shot in (8, 16) and
                 (len(actual_holds) != 2 or len(actual_gains) != 2 or
                  0 not in actual_gains or max(actual_gains) > 30000)) or
                (self.conditions_per_shot == 16 and len(actual_freqs) != 2)):
            raise ValueError("interleaved conditions must cover sham/on, g/e, and holds")
        self.logical_shots = int(configs[0]["shots"])
        if self.logical_shots <= 0:
            raise ValueError("logical shot count must be positive")
        self.condition_cfgs = configs
        run_cfg = dict(configs[0], reps=self.conditions_per_shot * self.logical_shots)
        super().__init__(soccfg, run_cfg, payload_calibration, loop_calibration)

    def make_program(self):
        _declare_common(self)
        self._declare_experiment()
        self.reset_page = self.ch_page(self.cfg["qubit_ch"])
        self.reset_regs = allocate_registers(self, self.reset_page)
        reserved = _reserved_registers(self, 0)
        if self.reset_page == 0:
            reserved.update(self.reset_regs.values())
        controls = allocate_named_registers(
            self, 0, resident_control_names(self.cfg, ("shot_loop", "done")),
            reserved=reserved)
        self.regwi(self.reset_page, self.reset_regs["address"], self.record_base)
        self.regwi(0, controls["done"], 0)
        self.memwi(0, controls["done"], self.done_addr)
        self.regwi(0, controls["shot_loop"], self.logical_shots - 1)
        self._initialize_stream(controls, **stream_dimensions(
            self.logical_shots, records_per_shot=len(self.condition_cfgs)),
                                prefix="Q3_INTERLEAVED_RESIDENT")
        self._begin_park_lifecycle()
        self.label("Q3_INTERLEAVED_SHOT_LOOP")
        base_cfg = self.cfg
        for condition_cfg in self.condition_cfgs:
            self.cfg = condition_cfg
            self._emit_body()
        self.cfg = base_cfg
        # The acquisition reader checks completed *records*, not logical shots.
        self.mathi(0, controls["done"], controls["done"], "+",
                   len(self.condition_cfgs))
        self.memwi(0, controls["done"], self.done_addr)
        self._stream_after_shot()
        self.loopnz(0, controls["shot_loop"], "Q3_INTERLEAVED_SHOT_LOOP")
        self._finish_stream()
        self._end_park_lifecycle()
        self.end()


def plan(*, loading_check=False, loss_check=False, hold_alternating=False,
         short_gap_saturation=False, strong_short_gap=False,
         strong_long_load=False, mapped_short_gap=False,
         paired_tone_dynamics=False):
    if sum(map(bool, (loading_check, loss_check, hold_alternating,
                      short_gap_saturation, strong_short_gap,
                      strong_long_load, mapped_short_gap,
                      paired_tone_dynamics))) > 1:
        raise ValueError("select at most one check mode")
    if paired_tone_dynamics:
        return {"hardware_access": False, "reset_mode": "passive",
                "purpose": "repeat time-local hot/cold pump-probe with tone pairing",
                "sites": ["fresh loss feature", "qualified 14-MHz lower flank"],
                "calibration_session": MAPPED_CALIBRATION_SESSION_ID,
                "cycles": PAIRED_CYCLES, "programs": 2 * PAIRED_CYCLES,
                "conditions_per_shot": 16, "shots_per_program": PAIRED_SHOTS,
                "pre_drive_us": resident.PRE_DRIVE_US,
                "post_drive_holds_us": list(SATURATION_POSTHOLDS_US),
                "tones_mhz": [MAPPED_ON_DETUNING_MHZ, MAPPED_OFF_DETUNING_MHZ],
                "drive_gain_dac": MAPPED_GAIN,
                "on_off_tones_within_same_hardware_shot": True,
                "hot_cold_sham_drive_within_same_hardware_shot": True,
                "feature_flank_order_reversed_each_cycle": True,
                "intermediate_readout": False,
                "only_readout_after_full_return_us": 40.0,
                "raw_iq_saved": True,
                "primary_effect": "per-cycle loaded-minus-cold normalized "
                                  "1.5-to-16-us survival difference at feature "
                                  "minus flank; require at least six valid "
                                  "feature/flank cycle pairs and both orders"}
    if short_gap_saturation or strong_short_gap or strong_long_load or mapped_short_gap:
        return {"hardware_access": False, "reset_mode": "passive",
                "purpose": "test whether qubit loading suppresses subsequent on-feature loss",
                "sites": ["fresh loss feature", "qualified 14-MHz lower flank"],
                "load_us": STRONG_LOAD_US if strong_short_gap else resident.PRE_DRIVE_US,
                "post_drive_holds_us": list(SATURATION_POSTHOLDS_US),
                "tones_mhz": ([MAPPED_ON_DETUNING_MHZ, MAPPED_OFF_DETUNING_MHZ]
                               if mapped_short_gap else [5.0, -10.0]),
                "drive_gain_dac": (MAPPED_GAIN if mapped_short_gap else
                                   STRONG_GAIN if strong_short_gap or strong_long_load
                                   else 6000),
                "calibration_session": (MAPPED_CALIBRATION_SESSION_ID
                                        if mapped_short_gap else
                                        probe.CALIBRATION_SESSION_ID),
                "programs": 8, "conditions_per_shot": 8,
                "shots_per_program": SATURATION_SHOTS,
                "intermediate_readout": False,
                "only_readout_after_full_return_us": 40.0,
                "raw_iq_saved": True,
                "primary_effect": "loaded-minus-cold normalized 1.5-to-16-us "
                                  "survival difference at feature minus flank; "
                                  "detuned pulse gates drive specificity",
                "interpretation": "positive feature-specific effect is candidate "
                                  "saturation; a null result does not exclude fast TLS decay"}
    if hold_alternating:
        return {"hardware_access": False, "reset_mode": "passive",
                "purpose": "test short/long loss with both holds in each QICK shot",
                "sites": ["feature", "14-MHz lower flank"],
                "pre_drive_us": resident.PRE_DRIVE_US,
                "post_drive_holds_us": list(LOSS_POSTHOLDS_US),
                "tones_mhz": [5.0, -10.0], "drive_gain_dac": 6000,
                "programs": 8, "conditions_per_shot": 8,
                "shots_per_program": LOSS_SHOTS, "raw_iq_saved": True,
                "fresh_drive_check_arms": 8,
                "weak_drive_check_policy": "record and continue; each program measures its own drive control",
                "full_return_before_each_readout_us": 40.0,
                "inter_shot_delay_us": 500.0,
                "calibration_session": probe.CALIBRATION_SESSION_ID,
                "note": "Each logical shot contains both holds with sham/driven and hot/cold "
                        "conditions. The same tone/flank-subtracted statistic and controls "
                        "as the prior loss run apply. A response is not proof of one TLS."}
    if loss_check:
        return {"hardware_access": False, "reset_mode": "passive",
                "purpose": "compare target-resident drive-induced short/long loss",
                "sites": ["feature", "14-MHz lower flank"],
                "pre_drive_us": resident.PRE_DRIVE_US,
                "post_drive_holds_us": list(LOSS_POSTHOLDS_US),
                "tones_mhz": [5.0, -10.0], "drive_gain_dac": 6000,
                "programs": 16, "conditions_per_shot": 4,
                "shots_per_program": LOSS_SHOTS, "raw_iq_saved": True,
                "fresh_drive_check_arms": 8,
                "weak_drive_check_policy": "record and continue; on/detuned programs have their own drive controls",
                "full_return_before_each_readout_us": 40.0,
                "inter_shot_delay_us": 500.0,
                "calibration_session": probe.CALIBRATION_SESSION_ID,
                "note": "Compare driven-minus-sham hot/cold loss between 0.1 and 2 us, "
                        "then subtract detuned and flank controls in each order. "
                        "A selective response is not proof of one microscopic TLS."}
    if loading_check:
        return {"hardware_access": False, "reset_mode": "passive",
                "purpose": "choose a stable target loading time before shot-alternating loss test",
                "site": "freshly selected loss feature",
                "pre_drive_holds_us": list(LOADING_PREHOLDS_US),
                "post_drive_us": resident.POST_DRIVE_US,
                "programs": 8, "conditions_per_shot": 4,
                "shots_per_program": SHOTS, "raw_iq_saved": True,
                "fresh_drive_check_arms": 4,
                "fresh_drive_check_pre_us": 8.0,
                "weak_drive_check_policy": "record and continue; each loading time has its own drive control",
                "full_return_before_each_readout_us": 40.0,
                "inter_shot_delay_us": 500.0,
                "success_gate": "hot and cold-drive contrast >=0.10 in both orders",
                "calibration_session": probe.CALIBRATION_SESSION_ID,
                "note": "This checks preparation stability; it cannot establish TLS saturation."}
    return {"hardware_access": False, "reset_mode": "passive",
            "purpose": "validate shot-alternating target-resident condition order",
            "site": "freshly selected loss feature",
            "condition_names": list(CONDITION_NAMES),
            "condition_orders": [list(CONDITION_NAMES), list(reversed(CONDITION_NAMES))],
            "programs": 2, "conditions_per_shot": 4,
            "shots_per_program": SHOTS, "raw_iq_saved": True,
            "fresh_drive_check_arms": 4,
            "fresh_drive_check_shots_per_arm": 200,
            "fresh_drive_check_gate": "on minus sham >=0.10; abs(detuned minus sham) <=0.10; sham drift <=0.10",
            "pre_drive_us": resident.PRE_DRIVE_US,
            "post_drive_us": resident.POST_DRIVE_US,
            "full_return_before_each_readout_us": 40.0,
            "inter_shot_delay_us": 500.0,
            "calibration_session": probe.CALIBRATION_SESSION_ID,
            "note": __doc__}


def run(*, data_root=localizer.DATA_ROOT, correction_json=None,
        loading_check=False, loss_check=False, hold_alternating=False,
        short_gap_saturation=False, strong_short_gap=False,
        strong_long_load=False, mapped_short_gap=False,
        paired_tone_dynamics=False):
    if sum(map(bool, (loading_check, loss_check, hold_alternating,
                      short_gap_saturation, strong_short_gap,
                      strong_long_load, mapped_short_gap,
                      paired_tone_dynamics))) > 1:
        raise ValueError("select at most one check mode")
    saturation_mode = (short_gap_saturation or strong_short_gap or
                       strong_long_load or mapped_short_gap or
                       paired_tone_dynamics)
    strong_drive_mode = strong_short_gap or strong_long_load
    loss_mode = loss_check or hold_alternating or saturation_mode
    science_pre_us = STRONG_LOAD_US if strong_short_gap else resident.PRE_DRIVE_US
    data_root = Path(data_root)
    calibration_path, calibration = (checked_mapped_calibration(data_root)
                                     if mapped_short_gap or paired_tone_dynamics else
                                     probe.checked_calibration(data_root))
    correction = localizer.checked_correction(data_root, correction_json)
    if saturation_mode:
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
            TLSPumpProbeHeralded as heralded,
        )
    scout_parameters = (heralded.postselection_scout_parameters("pre")
                        if saturation_mode else
                        adaptive.scout_parameters(phase="pre"))
    scout = localizer.run(
        data_root=data_root, correction_json=correction,
        parameter_overrides={**scout_parameters,
                             "output_suffix": ("TLS_PumpProbe_ShortGap_Scout_pre"
                                               if saturation_mode else
                                               "TLS_PumpProbe_ShotAlternating_Scout")})
    selected = (heralded.select_postselection_feature(
        heralded.read_postselection_scout(scout)) if saturation_mode else
        adaptive.select_loss_feature(adaptive.read_scout(scout)))
    center = round(float(selected["center_ghz"]), 3)
    print(f"[shot-alternating] feature={center:.3f} GHz", flush=True)

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
            raise RuntimeError("q3 park gain differs from verified configuration")
        tls.QUBIT, tls.SET_YOKO, tls.outerFolder = "q3", False, str(data_root)
        five.install_scan_calibration(tls)
        flank = (float(selected["control_ghz"]) if saturation_mode else
                 round(center + resident.FLANK_OFFSET_GHZ, 3))
        grid = np.asarray([center, flank] if loss_mode else [center], dtype=float)
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
                     "qubit_pulse_style": "arb", "do_ff": True,
                     "opx_reset_scheme": "none",
                     "opx_resident_dmem_stream": True,
                     "opx_inter_shot_delay_us": 500.0})
        pulse_us = 4.0 * float(base["sigma"]) + 0.01
        if abs(pulse_us - float(calibration["drive_pulse_nominal_us"])) > 0.01:
            raise RuntimeError("qubit Gaussian duration changed since drive calibration")
        windows = {}
        preholds = (LOADING_PREHOLDS_US if loading_check else
                    (resident.TRANSFER_PRE_US, resident.PRE_DRIVE_US,
                     STRONG_LOAD_US) if strong_short_gap else
                    (resident.TRANSFER_PRE_US, resident.PRE_DRIVE_US))
        for pre in preholds:
            if loss_mode and pre == science_pre_us:
                holds = (SATURATION_POSTHOLDS_US if saturation_mode else
                         LOSS_POSTHOLDS_US)
            else:
                holds = (resident.POST_DRIVE_US,)
            for post in holds:
                before, after, recovery = resident.resident_segments(
                    compensation, pre_us=pre + ff_pulse.flux_settle_us(base),
                    pulse_us=pulse_us, post_us=post, recovery_us=40.0)
                key = f"{pre:g}/{post:g}" if loss_mode else str(pre)
                windows[key] = {"held_multiplier": before[-1][0],
                                "post_multiplier": after[0][0],
                                "recovery_us": sum(duration for _, duration in recovery)}
        session_id = (("q3_pump_probe_paired_tone_dynamics_"
                       if paired_tone_dynamics else
                       "q3_pump_probe_mapped_short_gap_" if mapped_short_gap else
                       "q3_pump_probe_strong_long_load_" if strong_long_load else
                       "q3_pump_probe_strong_short_gap_" if strong_short_gap else
                       "q3_pump_probe_short_gap_saturation_" if short_gap_saturation else
                       "q3_pump_probe_hold_alternating_loss_" if hold_alternating else
                       "q3_pump_probe_shot_alternating_loss_" if loss_check else
                       "q3_pump_probe_shot_alternating_loading_" if loading_check
                       else "q3_pump_probe_shot_alternating_") +
                      datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") +
                      "_" + uuid.uuid4().hex[:8])
        folder = data_root / "q3" / session_id
        folder.mkdir(parents=True, exist_ok=False)
        path = folder / "manifest.json"
        refs = (probe.reference_arms(center, phase="pre") +
                probe.reference_arms(center, phase="post"))
        for ref in refs:
            ref["shots"] = REFERENCE_SHOTS
        drive_checks = (mapped_drive_checks(center, flank)
                        if mapped_short_gap or paired_tone_dynamics else
                        strong_drive_checks(center, flank, load_us=science_pre_us)
                        if strong_drive_mode else
                        probe.carryover_drive_checks(center, flank)
                        if loss_mode else fresh_drive_arms(center))
        if loading_check:
            for arm in drive_checks:
                arm["pre_drive_us"] = 8.0
        program_specs = (paired_tone_specs(center, flank)
                         if paired_tone_dynamics else
                         mapped_short_gap_specs(center, flank_ghz=flank)
                         if mapped_short_gap else
                         short_gap_saturation_specs(
                             center, strong=strong_drive_mode,
                             load_us=science_pre_us)
                         if saturation_mode else
                         hold_alternating_specs(center) if hold_alternating else
                         loss_program_specs(center) if loss_check else
                         loading_program_specs(center) if loading_check else [
            {"name": direction, "direction": direction,
             "pre_drive_us": resident.PRE_DRIVE_US,
             "post_drive_us": resident.POST_DRIVE_US,
             "order": [c["name"] for c in order], "conditions": order}
            for direction, order in (("forward", conditions(center)),
                                     ("reverse", conditions(center, reverse=True)))])
        manifest = {"schema": ("q3.pump-probe-paired-tone-dynamics.v1"
                               if paired_tone_dynamics else
                               "q3.pump-probe-mapped-short-gap.v1"
                               if mapped_short_gap else
                               "q3.pump-probe-strong-long-load.v1"
                               if strong_long_load else
                               "q3.pump-probe-strong-short-gap.v1"
                               if strong_short_gap else
                               "q3.pump-probe-short-gap-saturation.v1"
                               if short_gap_saturation else
                               "q3.pump-probe-hold-alternating-loss.v1"
                               if hold_alternating else
                               "q3.pump-probe-shot-alternating-loss.v1"
                               if loss_check else
                               "q3.pump-probe-shot-alternating-loading.v1"
                               if loading_check else
                               "q3.pump-probe-shot-alternating-pilot.v1"),
                    "status": "running", "session_id": session_id,
                    "code_commit": os.environ.get("Q3_CODE_COMMIT", "unknown"),
                    "calibration_manifest": str(calibration_path),
                    "correction_json": str(correction),
                    "correction_sha256": localizer.CORRECTION_SHA256,
                    "scout_csv": str(scout), "selected": selected,
                    "center_ghz": center, "flank_ghz": flank if loss_mode else None,
                    "dc_gain": int(dc[0]), "dc_lookup": dc_lookup,
                    "realized_ghz": realized.tolist(),
                    "plan": plan(loading_check=loading_check, loss_check=loss_check,
                                 hold_alternating=hold_alternating,
                                 short_gap_saturation=short_gap_saturation,
                                 strong_short_gap=strong_short_gap,
                                 strong_long_load=strong_long_load,
                                 mapped_short_gap=mapped_short_gap,
                                 paired_tone_dynamics=paired_tone_dynamics),
                    "correction_windows": windows,
                    "drive_pulse_nominal_us": pulse_us,
                    "references": [{**r, "status": "pending"} for r in refs],
                    "fresh_drive_checks": [{**a, "status": "pending"}
                                           for a in drive_checks],
                    "programs": [{**spec, "status": "pending"}
                                 for spec in program_specs]}
        protocol.checkpoint(path, manifest)
        print(f"[shot-alternating] manifest={path}", flush=True)
        raw_refs = {}
        axis = None
        try:
            soc, soccfg = tls.makeProxy()
            bundle = runtime_bundle(base)
            # Build every interleaved program before the first readout.
            programs = {}
            for entry in manifest["programs"]:
                cfgs = condition_configs(base, entry, dc_lookup, center)
                programs[entry["name"]] = ShotAlternatingResidentProgram(
                    soccfg, cfgs, bundle.payload, bundle.loop)
            for ref in manifest["references"]:
                resident.ResidentDriveProgram(
                    soccfg, resident.arm_config(base, ref, dc_lookup),
                    bundle.payload, bundle.loop)
            for arm in manifest["fresh_drive_checks"]:
                resident.ResidentDriveProgram(
                    soccfg, resident.arm_config(base, arm, dc_lookup),
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
                    raise RuntimeError(f"{ref['name']}: incomplete reference records")
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
                        raise RuntimeError("pre-run readout axis invalid")
                if axis is not None:
                    ref["excited_fraction_pre_axis"] = resident.classify(records, axis)
                ref["status"] = "complete"
                protocol.checkpoint(path, manifest)

            for ref in manifest["references"][:4]:
                print(f"[shot-alternating] {ref['name']}", flush=True)
                acquire_ref(ref)
            for arm in manifest["fresh_drive_checks"]:
                print(f"[shot-alternating] {arm['name']}", flush=True)
                arm["status"] = "acquiring"
                protocol.checkpoint(path, manifest)
                cfg = resident.arm_config(base, arm, dc_lookup)
                program = resident.ResidentDriveProgram(
                    soccfg, cfg, bundle.payload, bundle.loop)
                shots = int(arm["shots"])
                records = _run_program(
                    soc, program, max(30.0, _block_timeout_s(cfg, shots)),
                    cfg, total_shots=shots)
                if len(records) != shots:
                    raise RuntimeError(f"{arm['name']}: incomplete drive-check records")
                raw_path = folder / f"{arm['name']}.npz"
                np.savez_compressed(raw_path, i=[r.i for r in records],
                                    q=[r.q for r in records])
                arm["raw_npz"] = str(raw_path)
                arm["excited_fraction_pre_axis"] = resident.classify(records, axis)
                arm["status"] = "complete"
                protocol.checkpoint(path, manifest)
            if loss_mode:
                scorer = (evaluate_mapped_drive_check
                          if mapped_short_gap or paired_tone_dynamics else
                          evaluate_strong_drive_check if strong_drive_mode else
                          probe.evaluate_drive_check)
                manifest["fresh_drive_score"] = {
                    site: scorer({
                        a["tone"]: a["excited_fraction_pre_axis"]
                        for a in manifest["fresh_drive_checks"] if a["site"] == site})
                    for site in ("feature", "flank")}
                manifest["fresh_drive_gate"] = {
                    site: drive_check_gate(score, loading_check=True)
                    for site, score in manifest["fresh_drive_score"].items()}
            else:
                manifest["fresh_drive_score"] = probe.evaluate_drive_check(
                    {a["tone"]: a["excited_fraction_pre_axis"]
                     for a in manifest["fresh_drive_checks"]})
                manifest["fresh_drive_gate"] = drive_check_gate(
                    manifest["fresh_drive_score"], loading_check=loading_check)
            protocol.checkpoint(path, manifest)
            if (manifest["fresh_drive_gate"] == "diagnostic_only" or
                    isinstance(manifest["fresh_drive_gate"], dict) and
                    "diagnostic_only" in manifest["fresh_drive_gate"].values()):
                print("[shot-alternating] weak preliminary drive check; "
                      "continuing with per-program drive controls", flush=True)
            washout_start = time.monotonic()
            time.sleep(5.0)
            manifest["pre_pilot_washout_s_actual"] = time.monotonic() - washout_start
            protocol.checkpoint(path, manifest)
            for entry in manifest["programs"]:
                name = entry["name"]
                shots = int(entry.get("shots", SHOTS))
                n_conditions = len(entry["conditions"])
                print(f"[shot-alternating] {name} {shots} x {n_conditions} conditions",
                      flush=True)
                entry["status"] = "acquiring"
                protocol.checkpoint(path, manifest)
                start = time.monotonic()
                entry["acquisition_started_at_utc"] = datetime.now(timezone.utc).isoformat()
                records = _run_program(
                    soc, programs[name],
                    max(30.0, n_conditions * _block_timeout_s(base, shots)),
                    base, total_shots=shots)
                entry["acquisition_elapsed_s"] = time.monotonic() - start
                entry["acquisition_finished_at_utc"] = datetime.now(timezone.utc).isoformat()
                split = split_records(
                    records, entry["order"], shots=shots,
                    holds=(SATURATION_POSTHOLDS_US if saturation_mode else
                           LOSS_POSTHOLDS_US),
                    paired_tones=paired_tone_dynamics)
                for cond in entry["conditions"]:
                    subset = split[cond["name"]]
                    raw_path = folder / f"{name}_{cond['name']}.npz"
                    np.savez_compressed(raw_path, i=[r.i for r in subset],
                                        q=[r.q for r in subset])
                    cond["raw_npz"] = str(raw_path)
                    cond["excited_fraction_pre_axis"] = resident.classify(subset, axis)
                entry["status"] = "complete"
                protocol.checkpoint(path, manifest)
            for ref in manifest["references"][4:]:
                print(f"[shot-alternating] {ref['name']}", flush=True)
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
            order_scores = program_scores(
                manifest["programs"],
                hold_alternating=hold_alternating or saturation_mode,
                holds=(SATURATION_POSTHOLDS_US if saturation_mode else
                       LOSS_POSTHOLDS_US),
                paired_tones=paired_tone_dynamics)
            manifest["order_scores"] = order_scores
            post_scout_parameters = (heralded.postselection_scout_parameters("post")
                                     if saturation_mode else
                                     adaptive.scout_parameters(phase="post"))
            post_scout = localizer.run(
                data_root=data_root, correction_json=correction,
                parameter_overrides={**post_scout_parameters,
                                     "output_suffix": (
                                         "TLS_PumpProbe_ShortGap_Scout_post"
                                         if saturation_mode else
                                         "TLS_PumpProbe_ShotAlternating_Scout_post")})
            manifest["post_scout_csv"] = str(post_scout)
            try:
                manifest["post_selected"] = (
                    heralded.select_postselection_feature(
                        heralded.read_postselection_scout(post_scout))
                    if saturation_mode else
                    adaptive.select_loss_feature(adaptive.read_scout(post_scout)))
            except ValueError as exc:
                manifest["post_selection_error"] = str(exc)
            manifest["feature_stable"] = (
                resident.feature_stable(selected, manifest["post_selected"])
                if "post_selected" in manifest else False)
            controls_valid = (manifest["post_readout_score"]["valid"] and
                              all(x["usable"] for x in manifest["transfer_control"].values()) and
                              manifest["feature_stable"])
            if saturation_mode:
                repeats = (range(PAIRED_CYCLES) if paired_tone_dynamics else
                           range(2))
                manifest["saturation_control_report"] = (
                    short_gap_saturation_controls(order_scores, repeats=repeats))
                manifest["saturation_effect_report"] = (
                    short_gap_saturation_report(order_scores, repeats=repeats))
                if paired_tone_dynamics:
                    manifest["paired_cycle_quality"] = paired_cycle_quality(
                        manifest["saturation_control_report"]["groups"])
                    manifest["saturation_control_report"]["all_groups_usable"] = (
                        manifest["saturation_control_report"]["usable"])
                    manifest["saturation_control_report"]["usable"] = (
                        manifest["paired_cycle_quality"]["usable"])
                    valid = (controls_valid and
                             manifest["paired_cycle_quality"]["usable"])
                else:
                    valid = (controls_valid and
                             manifest["saturation_control_report"]["usable"])
            elif loss_mode:
                manifest["loss_control_report"] = loss_control_report(order_scores)
                manifest["loss_effect_report"] = loss_effect_report(order_scores)
                valid = controls_valid and manifest["loss_control_report"]["usable"]
            elif loading_check:
                manifest["usable_loading_times_us"] = usable_loading_times(order_scores)
                valid = controls_valid and bool(manifest["usable_loading_times_us"])
            else:
                valid = (controls_valid and
                         all(x["cold_drive_contrast"] >= 0.10
                             for x in order_scores.values()) and
                         all(x["hot_preparation_contrast"] >= 0.10
                             for x in order_scores.values()) and
                         abs(order_scores["forward"]["hot_minus_cold_drive_change"] -
                             order_scores["reverse"]["hot_minus_cold_drive_change"]) <= 0.25)
            manifest["status"] = "complete" if valid else "complete_controls_unstable"
            protocol.checkpoint(path, manifest)
            print(f"[shot-alternating] {manifest['status']}: {path}", flush=True)
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
    check_mode = parser.add_mutually_exclusive_group()
    check_mode.add_argument("--loading-check", action="store_true")
    check_mode.add_argument("--loss-check", action="store_true")
    check_mode.add_argument("--hold-alternating", action="store_true")
    check_mode.add_argument("--short-gap-saturation", action="store_true")
    check_mode.add_argument("--strong-short-gap", action="store_true")
    check_mode.add_argument("--strong-long-load", action="store_true")
    check_mode.add_argument("--mapped-short-gap", action="store_true")
    check_mode.add_argument("--paired-tone-dynamics", action="store_true")
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(plan(loading_check=args.loading_check,
                              loss_check=args.loss_check,
                              hold_alternating=args.hold_alternating,
                              short_gap_saturation=args.short_gap_saturation,
                              strong_short_gap=args.strong_short_gap,
                              strong_long_load=args.strong_long_load,
                              mapped_short_gap=args.mapped_short_gap,
                              paired_tone_dynamics=args.paired_tone_dynamics), indent=2))
    else:
        run(data_root=args.data_root, correction_json=args.correction_json,
            loading_check=args.loading_check, loss_check=args.loss_check,
            hold_alternating=args.hold_alternating,
            short_gap_saturation=args.short_gap_saturation,
            strong_short_gap=args.strong_short_gap,
            strong_long_load=args.strong_long_load,
            mapped_short_gap=args.mapped_short_gap,
            paired_tone_dynamics=args.paired_tone_dynamics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
