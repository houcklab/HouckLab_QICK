"""Screen previously untested, weaker q3 loss sites for delayed energy return.

An excited/ground park preparation visits a freshly scouted weak loss site.
After the established corrected return and first park readout, a ground-prepared
qubit probes that site after 100--1000 us. Hot-on, cold-on and hot-off arms are
interleaved in each hardware shot, then reversed in a second block. This is an
experimental afterglow screen, not TLS identification or production reset.
"""

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
from statistics import mean, median
import time
import uuid

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSPumpProbeHeralded as heralded,
    TLSPumpProbeLocalizer as localizer,
    TLSPumpProbeProtocolCheck as protocol,
    TLSPumpProbeWidePassiveScan as wide,
    TLSSwapHoldPilot as swap,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.programs import (
    _declare_common, _reserved_registers, allocate_named_registers,
    resident_control_names,
)


WAITS_US = (100.0, 300.0, 1000.0)
PUMP_US = 10.0
PROBE_US = 10.0
SHOTS = 600
REFERENCE_SHOTS = 400
MAX_SITES = 3
LOGICAL_RECOVERY_US = 5000.0
SITE_SEPARATION_GHZ = .020
EXCLUDED_TESTED_BANDS_GHZ = ((3.982, 4.010), (4.080, 4.190),
                             (4.270, 4.290))
CONDITIONS = ("cold_on", "hot_on", "hot_off")


def _survival(row, delay_us, suffix=""):
    ground = float(row[f"P0{suffix}"])
    excited = float(row[f"P1{suffix}"])
    held = float(row[f"Ps_{delay_us}us{suffix}"])
    if (not all(map(math.isfinite, (ground, excited, held))) or
            excited - ground < .15):
        return math.nan
    return (held - ground) / (excited - ground)


def _candidate_pool(rows):
    indexed = {round(float(row["target_frequency_ghz"]), 3): row
               for row in rows}
    expected = {round(3.8 + .002 * i, 3) for i in range(251)}
    if len(rows) != 251 or set(indexed) != expected:
        raise ValueError("weak-site screen needs one complete 251-point scout")
    candidates = []
    for center in sorted(indexed):
        if not 3.83 <= center <= 4.27:
            continue
        if any(lo <= center <= hi for lo, hi in EXCLUDED_TESTED_BANDS_GHZ):
            continue
        positions = {"feature": [round(center + .002 * i, 3)
                                 for i in (-1, 0, 1)],
                     "left": [round(center - .002 * i, 3)
                              for i in (4, 5, 6)],
                     "right": [round(center + .002 * i, 3)
                               for i in (4, 5, 6)]}
        if any(f not in indexed for fs in positions.values() for f in fs):
            continue
        depths = {}
        for label, suffix in (("combined", ""), ("up", "_scan_up"),
                              ("down", "_scan_down")):
            values = {group: [_survival(indexed[f], 25, suffix) for f in fs]
                      for group, fs in positions.items()}
            if any(not math.isfinite(v) for vs in values.values() for v in vs):
                break
            depths[label] = (min(median(values["left"]),
                                 median(values["right"])) -
                             mean(values["feature"]))
        if (len(depths) != 3 or not .04 <= depths["combined"] <= .24 or
                min(depths["up"], depths["down"]) < .03):
            continue
        best = None
        for offset in (-.020, -.018, -.016, -.014, .014, .016, .018, .020):
            control = round(center + offset, 3)
            controls = [round(control + .002 * i, 3) for i in (-1, 0, 1)]
            if any(f not in indexed for f in controls):
                continue
            early, quiet = {}, {}
            for label, suffix in (("combined", ""), ("up", "_scan_up"),
                                  ("down", "_scan_down")):
                c25 = [_survival(indexed[f], 25, suffix) for f in controls]
                c10 = [_survival(indexed[f], 10, suffix) for f in controls]
                f10 = [_survival(indexed[f], 10, suffix)
                       for f in positions["feature"]]
                if any(not math.isfinite(v) for v in c25 + c10 + f10):
                    break
                quiet[label] = min(c25)
                early[label] = mean(c10) - mean(f10)
            if (len(early) != 3 or min(quiet.values()) < .65 or
                    early["combined"] < .05 or
                    min(early["up"], early["down"]) < .04):
                continue
            candidate = {"center_ghz": center, "control_ghz": control,
                         "control_offset_ghz": offset,
                         "depth": depths["combined"],
                         "depth_scan_up": depths["up"],
                         "depth_scan_down": depths["down"],
                         "early_advantage": early,
                         "control_min_survival": min(quiet.values()),
                         "selector": "weak_bidirectional_early_loadable"}
            if best is None or (min(early["up"], early["down"]),
                                min(quiet.values())) > (
                    min(best["early_advantage"]["up"],
                        best["early_advantage"]["down"]),
                    best["control_min_survival"]):
                best = candidate
        if best is not None:
            candidates.append(best)
    return candidates


def select_weak_sites(rows, *, max_sites=MAX_SITES):
    """Prefer early-loadable weak dips, separated from one another."""
    if not 1 <= int(max_sites) <= MAX_SITES:
        raise ValueError("max_sites must be 1..3")
    ranked = sorted(_candidate_pool(rows), key=lambda c: (
        min(c["early_advantage"]["up"], c["early_advantage"]["down"]),
        min(c["depth_scan_up"], c["depth_scan_down"])), reverse=True)
    chosen = []
    for candidate in ranked:
        if all(abs(candidate["center_ghz"] - previous["center_ghz"]) >=
               SITE_SEPARATION_GHZ - 1e-9 for previous in chosen):
            chosen.append(candidate)
        if len(chosen) == max_sites:
            break
    if not chosen:
        raise ValueError("no qualified weak loss site with a quiet control")
    return chosen


def fine_scout_parameters(seed_ghz, site_index):
    center = round(float(seed_ghz), 3)
    return {**wide.parameters(),
            "freq_min_ghz": round(center - .022, 3),
            "freq_max_ghz": round(center + .022, 3),
            "freq_step_mhz": 1.0,
            "shots_per_condition": 350,
            "output_suffix": f"TLS_Weak_Afterglow_Fine_site{site_index}"}


def refine_site(rows, *, seed_ghz):
    """Locate the 1-MHz local trough rather than a 2-MHz scout edge."""
    seed = round(float(seed_ghz), 3)
    indexed = {round(float(row["target_frequency_ghz"]), 3): row
               for row in rows}
    expected = {round(seed - .022 + .001 * i, 3) for i in range(45)}
    if len(rows) != 45 or set(indexed) != expected:
        raise ValueError("fine localization needs one complete 45-point scout")
    candidates = []
    for shift in range(-4, 5):
        center = round(seed + shift * .001, 3)
        positions = {"feature": [round(center + .001 * i, 3)
                                 for i in (-1, 0, 1)],
                     "left": [round(center - .001 * i, 3)
                              for i in (8, 10, 12)],
                     "right": [round(center + .001 * i, 3)
                               for i in (8, 10, 12)]}
        if any(f not in indexed for fs in positions.values() for f in fs):
            continue
        depths = {}
        center_survival = None
        for label, suffix in (("combined", ""), ("up", "_scan_up"),
                              ("down", "_scan_down")):
            values = {group: [_survival(indexed[f], 25, suffix) for f in fs]
                      for group, fs in positions.items()}
            if any(not math.isfinite(v) for vs in values.values() for v in vs):
                break
            depths[label] = (min(median(values["left"]),
                                 median(values["right"])) -
                             mean(values["feature"]))
            if label == "combined":
                center_survival = _survival(indexed[center], 25)
        if (len(depths) != 3 or not .06 <= depths["combined"] <= .35 or
                min(depths["up"], depths["down"]) < .04):
            continue
        for offset_mhz in (-20, -18, -16, -14, 14, 16, 18, 20):
            control = round(center + offset_mhz / 1000.0, 3)
            controls = [round(control + .001 * i, 3) for i in (-1, 0, 1)]
            if any(f not in indexed for f in controls):
                continue
            early, quiet = {}, {}
            for label, suffix in (("combined", ""), ("up", "_scan_up"),
                                  ("down", "_scan_down")):
                c25 = [_survival(indexed[f], 25, suffix) for f in controls]
                c10 = [_survival(indexed[f], 10, suffix) for f in controls]
                f10 = [_survival(indexed[f], 10, suffix)
                       for f in positions["feature"]]
                if any(not math.isfinite(v) for v in c25 + c10 + f10):
                    break
                quiet[label] = min(c25)
                early[label] = mean(c10) - mean(f10)
            if (len(early) != 3 or min(quiet.values()) < .65 or
                    min(early["up"], early["down"]) < .04):
                continue
            candidates.append({
                "center_ghz": center, "control_ghz": control,
                "wide_seed_ghz": seed, "control_offset_ghz": offset_mhz / 1000.0,
                "depth": depths["combined"],
                "depth_scan_up": depths["up"],
                "depth_scan_down": depths["down"],
                "center_survival": center_survival,
                "early_advantage": early,
                "control_min_survival": min(quiet.values()),
                "selector": "fine_weak_bidirectional"})
    if not candidates:
        raise ValueError("fine scout no longer contains a qualified weak loss site")
    return max(candidates, key=lambda item: (
        min(item["depth_scan_up"], item["depth_scan_down"]),
        -item["center_survival"],
        min(item["early_advantage"]["up"], item["early_advantage"]["down"])))


def filter_refined_sites(sites):
    """Avoid probing one selected loss site as another's off-target control."""
    chosen = []
    for site in sites:
        center, control = float(site["center_ghz"]), float(site["control_ghz"])
        if any(abs(center - float(other["center_ghz"])) < .016 or
               abs(center - float(other["control_ghz"])) < .008 or
               abs(control - float(other["center_ghz"])) < .008
               for other in chosen):
            continue
        chosen.append(site)
    return chosen


def program_specs(sites):
    specs = []
    for cycle in (0, 1):
        waits = WAITS_US if cycle == 0 else tuple(reversed(WAITS_US))
        indexed_sites = list(enumerate(sites))
        if cycle:
            indexed_sites.reverse()
        for wait_us in waits:
            for site_index, site in indexed_sites:
                center = float(site["center_ghz"])
                control = float(site["control_ghz"])
                arms = [
                    {"name": name, "pump_state": state,
                     "probe_state": "g", "pump_ghz": pump_ghz,
                     "probe_ghz": center, "pump_us": PUMP_US,
                     "probe_us": PROBE_US, "interstage_extra_us": wait_us,
                     "pump_prepare_after_return": False,
                     "probe_prepare_after_return": False}
                    for name, state, pump_ghz in (
                        ("cold_on", "g", center),
                        ("hot_on", "e", center),
                        ("hot_off", "e", control))]
                if cycle:
                    arms.reverse()
                specs.append({"name": f"site{site_index}_wait{wait_us:g}_r{cycle}",
                              "site_index": site_index, "wait_us": wait_us,
                              "cycle": cycle, "shots": SHOTS,
                              "order": [arm["name"] for arm in arms],
                              "conditions": arms, "status": "pending"})
    return specs


def split_records(records, order, *, shots):
    records = list(records)
    if len(order) != 3 or set(order) != set(CONDITIONS):
        raise ValueError("afterglow order must contain three distinct controls")
    if len(records) != 3 * int(shots):
        raise ValueError("incomplete three-condition paired IQ stream")
    return {name: records[index::3] for index, name in enumerate(order)}


def score_programs(programs, *, controls_valid):
    """Require both acquisition orders and both controls for a screen hit."""
    grouped = {}
    for program in programs:
        key = f"site{program['site_index']}_wait{program['wait_us']:g}"
        grouped.setdefault(key, {})[int(program["cycle"])] = program
    report = {}
    for key, cycles in grouped.items():
        scored = {}
        for cycle in (0, 1):
            program = cycles.get(cycle)
            if program is None or program.get("status") != "complete":
                scored[cycle] = None
                continue
            arms = {a["name"]: a.get("summary", {})
                    for a in program["conditions"]}
            if set(arms) != set(CONDITIONS) or any(
                    arms[name].get("herald_ground_shots", 0) < 100 or
                    arms[name].get("final_excited_given_ground") is None or
                    arms[name].get("projected_final_given_ground") is None
                    for name in CONDITIONS):
                scored[cycle] = None
                continue
            fractions = {name: float(arms[name]["final_excited_given_ground"])
                         for name in CONDITIONS}
            projection = {name: float(arms[name]["projected_final_given_ground"])
                          for name in CONDITIONS}
            if not all(map(math.isfinite, (*fractions.values(),
                                            *projection.values()))):
                scored[cycle] = None
                continue
            scored[cycle] = {
                "fractions": fractions,
                "accepted_shots": {name: int(arms[name]["herald_ground_shots"])
                                   for name in CONDITIONS},
                "hot_on_minus_cold_on": fractions["hot_on"] - fractions["cold_on"],
                "hot_on_minus_hot_off": fractions["hot_on"] - fractions["hot_off"],
                "raw_iq_hot_on_minus_cold_on": projection["hot_on"] - projection["cold_on"],
                "raw_iq_hot_on_minus_hot_off": projection["hot_on"] - projection["hot_off"],
            }
        hit = bool(controls_valid and all(scored.get(cycle) is not None for cycle in (0, 1))
                   and all(scored[cycle][metric] >= .04 for cycle in (0, 1)
                           for metric in ("hot_on_minus_cold_on",
                                          "hot_on_minus_hot_off"))
                   and all(scored[cycle][metric] > 0 for cycle in (0, 1)
                           for metric in ("raw_iq_hot_on_minus_cold_on",
                                          "raw_iq_hot_on_minus_hot_off")))
        report[key] = {"cycles": scored, "hit": hit,
                       "interpretation": "screen candidate only; local frequency and delay confirmation required"}
    return report


def post_site_stability(rows, site):
    """Check the same weak dip and original off-target loading control."""
    center = float(site["center_ghz"])
    matches = [candidate for candidate in _candidate_pool(rows)
               if abs(candidate["center_ghz"] - center) <= .002001]
    indexed = {round(float(row["target_frequency_ghz"]), 3): row
               for row in rows}
    control = float(site["control_ghz"])
    control = round(3.8 + .002 * round((control - 3.8) / .002), 3)
    try:
        quiet = min(_survival(indexed[round(control + .002 * i, 3)], 25, suffix)
                    for i in (-1, 0, 1)
                    for suffix in ("", "_scan_up", "_scan_down"))
    except KeyError:
        quiet = math.nan
    match = max(matches, key=lambda item: item["depth"]) if matches else None
    stable = bool(match is not None and math.isfinite(quiet) and quiet >= .65)
    return {"stable": stable, "post_center_ghz": None if match is None else
            match["center_ghz"], "center_shift_mhz": None if match is None else
            round(1000 * (match["center_ghz"] - center), 3),
            "original_control_min_survival": quiet}


def projected_final_given_ground(records, axes, *, ground_level, excited_level):
    """Unthresholded final IQ, conditioned on the frozen first-readout axis."""
    herald_iq = heralded.record_iq(records, "herald")
    final_iq = heralded.record_iq(records, "final")
    accepted = heralded.confident_ground(herald_iq, axes["herald"])
    if not np.any(accepted):
        return None
    span = float(excited_level) - float(ground_level)
    if not math.isfinite(span) or span <= 0:
        raise ValueError("final readout reference axis collapsed")
    projection = heralded._projection(final_iq[accepted], axes["final"])
    return float((np.mean(projection) - ground_level) / span)


class InterleavedAfterglowProgram(heralded.HeraldedPumpProbeProgram):
    """Three complete two-readout subshots in one logical hardware shot."""

    def __init__(self, soccfg, condition_cfgs, payload_calibration,
                 loop_calibration):
        configs = [dict(cfg) for cfg in condition_cfgs]
        if len(configs) != 3:
            raise ValueError("afterglow needs cold-on, hot-on and hot-off configs")
        common = ("ff_park_gain", "opx_herald_probe_gain", "shots", "reps",
                  "opx_herald_interstage_extra_us", "opx_herald_probe_state")
        if any(any(cfg[key] != configs[0][key] for key in common)
               for cfg in configs[1:]):
            raise ValueError("interleaved afterglow controls must share probe and timing")
        observed = [(cfg["ff_gain"], cfg["opx_herald_pump_state"])
                    for cfg in configs]
        hot_on = [gain for gain, state in observed
                  if state == "e" and any(gain == other_gain and other_state == "g"
                                          for other_gain, other_state in observed)]
        if (len(hot_on) != 1 or
                sum(state == "g" for _, state in observed) != 1 or
                sum(state == "e" for _, state in observed) != 2 or
                len({gain for gain, _ in observed}) != 2):
            raise ValueError("afterglow requires matched hot/cold on and hot off")
        self.logical_shots = int(configs[0]["shots"])
        if self.logical_shots <= 0:
            raise ValueError("logical shot count must be positive")
        self.condition_cfgs = configs
        run_cfg = dict(configs[0], reps=3 * self.logical_shots)
        super().__init__(soccfg, run_cfg, payload_calibration, loop_calibration)

    def make_program(self):
        _declare_common(self)
        self._declare_experiment()
        self.reset_page = self.ch_page(self.cfg["qubit_ch"])
        names = ("i", "q", "z", "ground", "excited", "attempts", "pi_count",
                 "status", "address")
        self.reset_regs = allocate_named_registers(self, self.reset_page, names)
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
        self._initialize_stream(
            controls, total_shots=self.logical_shots, records_per_shot=3,
            total_units=self.logical_shots, records_per_unit=3,
            prefix="Q3_WEAK_AFTERGLOW")
        self._begin_park_lifecycle()
        self.label("Q3_WEAK_AFTERGLOW_SHOT_LOOP")
        run_cfg = self.cfg
        for condition_cfg in self.condition_cfgs:
            self.cfg = condition_cfg
            self._emit_body()
        self.cfg = run_cfg
        # The three arms are paired for drift rejection; let a millisecond-
        # lived environmental excitation decay before the next logical shot.
        for _ in range(5):
            self.sync_all(self.us2cycles(1000.0))
        self.mathi(0, controls["done"], controls["done"], "+", 3)
        self.memwi(0, controls["done"], self.done_addr)
        self._stream_after_shot()
        self.loopnz(0, controls["shot_loop"], "Q3_WEAK_AFTERGLOW_SHOT_LOOP")
        self._finish_stream()
        self._end_park_lifecycle()
        self.end()


def plan():
    return {
        "hardware_access": False, "reset_mode": "passive",
        "purpose": "screen weaker, previously untested loss sites for delayed energy return",
        "scout_ghz": [3.8, 4.3], "scout_step_mhz": 2,
        "fine_localization_step_mhz": 1,
        "maximum_weak_sites": MAX_SITES,
        "site_selection": "bidirectional 25-us dip, 10-us early loss, quiet 14--20-MHz control; exclude exhausted bands",
        "excluded_tested_bands_ghz": EXCLUDED_TESTED_BANDS_GHZ,
        "pump_us": PUMP_US, "probe_us": PROBE_US,
        "additional_waits_us": list(WAITS_US),
        "conditions_per_shot": 3,
        "condition_order": "cold-on/hot-on/hot-off then reverse in second block",
        "shots_per_program": SHOTS,
        "programs_per_site": 2 * len(WAITS_US),
        "reference_shots_per_arm": REFERENCE_SHOTS,
        "full_return_before_each_readout_us": 40.0,
        "inter_shot_delay_us": 500.0,
        "logical_shot_recovery_us": LOGICAL_RECOVERY_US,
        "raw_paired_iq_saved": True,
        "screen_candidate_rule": "both controls >=0.04 in both orders and unthresholded IQ agrees; post scout and references must pass",
        "interpretation_limit": "intermediate readout can perturb the qubit/environment; a hit requires a local confirmation without that confound",
    }


def _save_records(path, records):
    np.savez_compressed(path,
                        herald_i=[record.herald_i for record in records],
                        herald_q=[record.herald_q for record in records],
                        final_i=[record.final_i for record in records],
                        final_q=[record.final_q for record in records])


def _reference_levels(raw_by_name, axes):
    ground = raw_by_name["ref_g_pre"]
    excited = raw_by_name["ref_final_e_pre"]
    gmask = heralded.confident_ground(
        heralded.record_iq(ground, "herald"), axes["herald"])
    emask = heralded.confident_ground(
        heralded.record_iq(excited, "herald"), axes["herald"])
    glevel = float(np.median(heralded._projection(
        heralded.record_iq(ground, "final")[gmask], axes["final"])))
    elevel = float(np.median(heralded._projection(
        heralded.record_iq(excited, "final")[emask], axes["final"])))
    if not math.isfinite(elevel - glevel) or elevel <= glevel:
        raise RuntimeError("pre-run final readout reference separation collapsed")
    return glevel, elevel


def run(*, data_root=localizer.DATA_ROOT, correction_json=None):
    data_root = Path(data_root)
    correction = localizer.checked_correction(data_root, correction_json)
    pre_scout = localizer.run(
        data_root=data_root, correction_json=correction,
        parameter_overrides={**wide.parameters(),
                             "output_suffix": "TLS_Weak_Afterglow_Scout_pre"})
    wide_sites = select_weak_sites(swap.read_wide_scout(pre_scout))
    sites = []
    fine_scans = []
    for index, seed in enumerate(wide_sites):
        fine_path = localizer.run(
            data_root=data_root, correction_json=correction,
            parameter_overrides=fine_scout_parameters(
                seed["center_ghz"], index))
        fine_scans.append({"wide_seed": seed, "csv": str(fine_path)})
        try:
            refined = refine_site(swap.read_wide_scout(fine_path),
                                  seed_ghz=seed["center_ghz"])
        except ValueError as exc:
            fine_scans[-1]["rejection"] = str(exc)
            print(f"[weak-afterglow] skip site {index}: {exc}", flush=True)
            continue
        refined["fine_scout_csv"] = str(fine_path)
        sites.append(refined)
    sites = filter_refined_sites(sites)
    if not sites:
        raise ValueError("no weak site survived 1-MHz localization; science not run")
    for index, site in enumerate(sites):
        print(f"[weak-afterglow] site {index}: {site['center_ghz']:.3f} GHz, "
              f"control {site['control_ghz']:.3f} GHz, "
              f"25-us depth {site['depth']:.3f}", flush=True)

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
        grid = np.asarray(sorted({float(s[key]) for s in sites
                                  for key in ("center_ghz", "control_ghz")}),
                          dtype=float)
        dc, realized = _integer_dc_grid(wide.parameters(), grid, tls)
        dc_lookup = {float(f): int(g) for f, g in zip(grid, dc)}
        compensation = tls._load_correction(str(correction), str(data_root))
        base = ProductionResetSession.passive().apply(tls.BaseConfig)
        five.apply_verified_feedback_timing(base)
        base.update({"apply_flux_tail_compensation": True,
                     "flux_tail_compensation": compensation,
                     "flux_fit_params": tls.FLUX_FIT_PARAMS,
                     "flux_settle_time_us": .5,
                     "flux_predistortion_return_prefix_us": .5,
                     "flux_predistortion_recovery_us": 40.0,
                     "flux_predistortion_overlap_payload_readout": False,
                     "flux_predistortion_round_trip_mode": "stateful",
                     "readout_thermalization_us": 10.0,
                     "qubit_pulse_style": "arb", "do_ff": True,
                     "opx_reset_scheme": "none",
                     "opx_resident_dmem_stream": True,
                     "opx_inter_shot_delay_us": 500.0})
        session_id = ("q3_tls_weak_afterglow_screen_" +
                      datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") +
                      "_" + uuid.uuid4().hex[:8])
        folder = data_root / "q3" / session_id
        folder.mkdir(parents=True, exist_ok=False)
        manifest_path = folder / "manifest.json"
        specs = program_specs(sites)
        refs = {phase: [dict(ref, shots=REFERENCE_SHOTS, status="pending")
                        for ref in heralded.reference_arms(
                            sites[0]["center_ghz"], phase=phase)]
                for phase in ("pre", "mid", "post")}
        manifest = {
            "schema": "q3.tls-weak-afterglow-screen.v1", "status": "running",
            "session_id": session_id,
            "code_commit": os.environ.get("Q3_CODE_COMMIT", "unknown"),
            "correction_json": str(correction),
            "correction_sha256": localizer.CORRECTION_SHA256,
            "pre_scout_csv": str(pre_scout), "fine_scans": fine_scans,
            "sites": sites,
            "dc_lookup": {str(k): v for k, v in dc_lookup.items()},
            "realized_ghz": realized.tolist(), "plan": plan(),
            "references": refs, "programs": specs,
        }
        protocol.checkpoint(manifest_path, manifest)
        print(f"[weak-afterglow] manifest={manifest_path}", flush=True)
        raw_by_name = {}
        axes = None
        try:
            soc, soccfg = tls.makeProxy()
            bundle = runtime_bundle(base)
            compiled = {}
            for spec in specs:
                configs = [heralded.arm_config(
                    base, {**arm, "shots": spec["shots"]}, dc_lookup)
                    for arm in spec["conditions"]]
                compiled[spec["name"]] = InterleavedAfterglowProgram(
                    soccfg, configs, bundle.payload, bundle.loop)
            for phase in refs:
                for ref in refs[phase]:
                    heralded.HeraldedPumpProbeProgram(
                        soccfg, heralded.arm_config(base, ref, dc_lookup),
                        bundle.payload, bundle.loop)
            manifest["preflight_complete"] = True
            protocol.checkpoint(manifest_path, manifest)

            def acquire_reference(ref):
                nonlocal axes
                ref["status"] = "acquiring"
                protocol.checkpoint(manifest_path, manifest)
                cfg = heralded.arm_config(base, ref, dc_lookup)
                program = heralded.HeraldedPumpProbeProgram(
                    soccfg, cfg, bundle.payload, bundle.loop)
                records = _run_program(
                    soc, program, max(30.0, _block_timeout_s(cfg, REFERENCE_SHOTS)),
                    cfg, total_shots=REFERENCE_SHOTS)
                if len(records) != REFERENCE_SHOTS:
                    raise RuntimeError(f"{ref['name']}: incomplete reference IQ")
                raw_by_name[ref["name"]] = records
                raw_path = folder / f"{ref['name']}.npz"
                _save_records(raw_path, records)
                ref["raw_npz"] = str(raw_path)
                if ref["name"] == "ref_final_e_pre":
                    assessment = heralded.assess_pre_references(
                        raw_by_name["ref_g_pre"], raw_by_name["ref_e_pre"],
                        records)
                    axes = assessment["axes"]
                    manifest["pre_reference_valid"] = assessment["valid"]
                    manifest["pre_readout_axes"] = axes
                    if not assessment["valid"]:
                        manifest["pre_reference_error"] = assessment["error"]
                if ref["name"] in ("ref_final_e_mid", "ref_final_e_post"):
                    phase = "mid" if ref["name"].endswith("_mid") else "post"
                    manifest[f"{phase}_reference_validation"] = (
                        heralded.validate_pair_against_axes(
                            axes, raw_by_name[f"ref_g_{phase}"],
                            raw_by_name[f"ref_e_{phase}"], records))
                ref["status"] = "complete"
                protocol.checkpoint(manifest_path, manifest)

            for ref in refs["pre"]:
                print(f"[weak-afterglow] {ref['name']}", flush=True)
                acquire_reference(ref)
            if not manifest["pre_reference_valid"]:
                manifest["status"] = "stopped_unusable_pre_reference"
                protocol.checkpoint(manifest_path, manifest)
                return manifest_path
            ground_level, excited_level = _reference_levels(raw_by_name, axes)

            for cycle in (0, 1):
                if cycle == 1:
                    for ref in refs["mid"]:
                        print(f"[weak-afterglow] {ref['name']}", flush=True)
                        acquire_reference(ref)
                for spec in (item for item in specs if item["cycle"] == cycle):
                    spec["status"] = "acquiring"
                    spec["started_at_utc"] = datetime.now(timezone.utc).isoformat()
                    protocol.checkpoint(manifest_path, manifest)
                    print(f"[weak-afterglow] {spec['name']} "
                          f"{spec['shots']} x 3", flush=True)
                    cfg = heralded.arm_config(
                        base, {**spec["conditions"][0], "shots": spec["shots"]},
                        dc_lookup)
                    start = time.monotonic()
                    records = _run_program(
                        soc, compiled[spec["name"]],
                        max(60.0, 3 * _block_timeout_s(cfg, spec["shots"]) +
                            (3 * spec["wait_us"] + LOGICAL_RECOVERY_US) *
                            spec["shots"] / 1e6),
                        cfg, total_shots=3 * spec["shots"])
                    spec["acquisition_elapsed_s"] = time.monotonic() - start
                    if len(records) != 3 * spec["shots"]:
                        raise RuntimeError(f"{spec['name']}: incomplete paired IQ")
                    split = split_records(records, spec["order"], shots=spec["shots"])
                    for arm in spec["conditions"]:
                        subset = split[arm["name"]]
                        raw_path = folder / f"{spec['name']}_{arm['name']}.npz"
                        _save_records(raw_path, subset)
                        arm["raw_npz"] = str(raw_path)
                        summary = heralded.summarize_records(subset, axes)
                        summary["projected_final_given_ground"] = (
                            projected_final_given_ground(
                                subset, axes, ground_level=ground_level,
                                excited_level=excited_level))
                        arm["summary"] = summary
                    spec["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
                    spec["status"] = "complete"
                    protocol.checkpoint(manifest_path, manifest)

            for ref in refs["post"]:
                print(f"[weak-afterglow] {ref['name']}", flush=True)
                acquire_reference(ref)
            post_scout = localizer.run(
                data_root=data_root, correction_json=correction,
                parameter_overrides={**wide.parameters(),
                                     "output_suffix": "TLS_Weak_Afterglow_Scout_post"})
            manifest["post_scout_csv"] = str(post_scout)
            post_rows = swap.read_wide_scout(post_scout)
            stability = [post_site_stability(post_rows, site) for site in sites]
            manifest["post_site_stability"] = stability
            readout_valid = bool(manifest["pre_reference_valid"] and
                                 manifest["mid_reference_validation"]["valid"] and
                                 manifest["post_reference_validation"]["valid"])
            manifest["readout_controls_valid"] = readout_valid
            report = score_programs(specs, controls_valid=readout_valid)
            for key, item in report.items():
                index = int(key.split("_", 1)[0][4:])
                item["site_stable"] = stability[index]["stable"]
                item["hit"] = bool(item["hit"] and item["site_stable"])
            manifest["screen_report"] = report
            manifest["status"] = ("complete" if readout_valid and
                                  all(item["stable"] for item in stability)
                                  else "complete_controls_uncertain")
            protocol.checkpoint(manifest_path, manifest)
            print(f"[weak-afterglow] {manifest['status']}; "
                  f"candidate hits={sum(item['hit'] for item in report.values())}: "
                  f"{manifest_path}", flush=True)
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
