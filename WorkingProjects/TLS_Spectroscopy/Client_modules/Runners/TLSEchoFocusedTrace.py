"""Validate flux-ramp echoes at one site or over a small frequency range.

The --single-point mode first tests a 4.284-GHz corrected flux visit in
four reversed blocks, including a repeated short-delay echo sentinel.
The later default mode covers fixed sites around the blind-map candidate
and two quieter controls, with narrow five-point scans before and after.
The --local-map mode repeats five nearby frequencies with model-free echo
crossings. Neither T1 scan selects or gates the echo sites. All modes save IQ.
The --population-check mode interleaves a short 4.288-GHz echo trace with
ground/excited survival controls matched to each target-visit duration.
The --refocus-check mode compares Hahn X, Hahn Y and CPMG2 Y at matched
elapsed times at the same validated frequency, without a T1 scout.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time
import uuid

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSEchoFastSquarePilot as fast,
    TLSEchoRefocusProgram as refocus,
    TLSEchoSquareMap as square,
    TLSPumpProbeLocalizer as localizer,
)


SITES_GHZ = (4.2, 4.204, 4.208, 4.212, 4.216, 4.22, 4.232, 4.284)
DELAYS_US = (.15, .3, .5, .8, 1.2, 1.8, 2.6)
PHASES_DEG = (0, 90, 180, 270)
SHOTS = 800
PRE_US = square.PRE_US
POST_US = square.POST_US
PI_US = square.PI_US
PI2_US = square.PI2_US
TWO_PI_US = 2 * PI_US
SINGLE_SITE_GHZ = 4.284
SINGLE_DELAYS_US = (.08, .15, .3, .5, .8, 1.2, 1.8, 2.6, 4.)
SINGLE_SHOTS = 1600
SINGLE_BLOCKS = 4
SINGLE_SOURCE_SESSION = "q3_echo_focused_trace_20260930T001018Z_fdc72d98"
LOCAL_MAP_SITES_GHZ = (4.280, 4.284, 4.288, 4.292, 4.296)
LOCAL_MAP_SHOTS = 1200
LOCAL_MAP_BLOCKS = 3
POPULATION_SITE_GHZ = 4.288
POPULATION_DELAYS_US = (.08, .3, .5, .8, 1.2)
POPULATION_SHOTS = 1600
POPULATION_BLOCKS = 3


def refocus_schedule(block):
    """Compare all filters next to each other, rotating order across blocks."""
    if not isinstance(block, int) or block < 0:
        raise ValueError("block index must be a nonnegative integer")
    times = refocus.TIMES_US if block % 2 == 0 else tuple(reversed(refocus.TIMES_US))
    phases = PHASES_DEG if block % 2 == 0 else tuple(reversed(PHASES_DEG))
    offset = block % len(refocus.SEQUENCES)
    sequences = refocus.SEQUENCES[offset:] + refocus.SEQUENCES[:offset]
    return [(sequence, elapsed, phase) for elapsed in times
            for phase in phases for sequence in sequences]


def refocus_report(cycles):
    """Preserve absolute contrast as well as each filter's early-normalized trace."""
    if set(cycles) != set(refocus.SEQUENCES) or any(
            set(values) != set(refocus.TIMES_US) for values in cycles.values()):
        raise ValueError("refocus report needs every planned filter and elapsed time")
    visibility = {name: {t: square.phase_visibility(values)["visibility"]
                         for t, values in trace.items()}
                  for name, trace in cycles.items()}
    rows = {}
    for elapsed in refocus.TIMES_US:
        raw = {name: trace[elapsed] for name, trace in visibility.items()}
        normalized = {name: raw[name] / trace[refocus.TIMES_US[0]]
                      if trace[refocus.TIMES_US[0]] > 0 else None
                      for name, trace in visibility.items()}
        rows[elapsed] = {"visibility": raw, "normalized": normalized,
                         "hahn_y_minus_hahn_x_visibility": raw["hahn_y"] - raw["hahn_x"],
                         "cpmg2_minus_hahn_y_visibility": raw["cpmg2_y"] - raw["hahn_y"]}
    return {"by_requested_elapsed_us": rows,
            "timing_axis": "first-to-last pi/2 center separation; realized times saved per program",
            "interpretation": "A repeatable CPMG2 gain supports recoverable phase contrast; pulse and deterministic phase errors remain possible."}


def population_schedule(block):
    """Keep six arms at each delay together, reversing the complete sequence."""
    if not isinstance(block, int) or block < 0:
        raise ValueError("block index must be a nonnegative integer")
    arms = []
    for index, delay in enumerate(POPULATION_DELAYS_US):
        echo = [("echo", delay, phase) for phase in PHASES_DEG]
        population = [("pop_g", delay, None), ("pop_e", delay, None)]
        arms.extend(population + echo if index % 2 == 0 else echo + population)
    return arms if block % 2 == 0 else list(reversed(arms))


def population_config(cfg, kind, delay_us):
    """Match the echo visit using a fixed pi-duration g/e preparation pulse."""
    delay = float(delay_us)
    if kind not in ("pop_g", "pop_e") or delay not in POPULATION_DELAYS_US:
        raise ValueError("population control requires a planned short delay and g/e arm")
    window = square.echo_window_us(delay)
    return {**cfg, "fast_pulse_us": PI_US, "fast_second_phase_deg": None,
            "opx_resident_gain": 0 if kind == "pop_g" else square.GAIN_DAC,
            "opx_resident_post_us": POST_US + window - (PI_US + .01),
            "ff_hold": PRE_US + POST_US + window}


def validate_population_correction(compensation, *, settle_us=.5):
    """Require identical held commands for echo and survival science windows."""
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse

    if compensation is None or max(POPULATION_DELAYS_US) > 1.2:
        raise ValueError("population check needs the bounded corrected hold")
    pre = PRE_US + float(settle_us)
    window = square.echo_window_us(max(POPULATION_DELAYS_US))
    target, _ = ff_pulse.compensation_round_trip_segments(
        compensation, pre + window + POST_US, recovery_us=40.)
    before, tail = ff_pulse.split_compensation_segments(target, pre)
    during, _ = ff_pulse.split_compensation_segments(tail, window)
    if (not before or not during or
            sum(duration for _, duration in during) < window - 1e-9 or
            not all(math.isfinite(float(level)) and
                    abs(float(level) - float(before[-1][0])) <= 1e-12
                    for level, _ in during)):
        raise ValueError("population check requires constant correction across the science window")
    return {"window_start_us": pre, "window_end_us": pre + window,
            "constant_coefficient": float(before[-1][0])}


def population_report(cycles, populations):
    """Compare relative echo contrast with a conditional relaxation benchmark."""
    delays = POPULATION_DELAYS_US
    if set(cycles) != set(delays) or set(populations) != set(delays):
        raise ValueError("population report needs every planned echo and g/e pair")
    visibility = {delay: square.phase_visibility(cycles[delay])["visibility"]
                  for delay in delays}
    contrasts = {delay: float(populations[delay]["e"]) -
                       float(populations[delay]["g"]) for delay in delays}
    short = contrasts[delays[0]]
    short_valid = math.isfinite(short) and short >= .55
    echo_short = visibility[delays[0]]
    echo_valid = math.isfinite(echo_short) and echo_short >= .55
    rows = {}
    for delay in delays:
        contrast = contrasts[delay]
        valid = short_valid and math.isfinite(contrast) and contrast > 0
        ratio = contrast / short if valid else None
        reasons = []
        if not short_valid:
            reasons.append("invalid or weak shortest-delay population contrast")
        if not math.isfinite(contrast) or contrast <= 0:
            reasons.append("nonpositive or nonfinite population contrast")
        if not echo_valid:
            reasons.append("invalid or weak shortest-delay echo visibility")
        rows[delay] = {
            "valid": valid and echo_valid, "reasons": reasons,
            "ground_response": float(populations[delay]["g"]),
            "excited_response": float(populations[delay]["e"]),
            "population_contrast": contrast,
            "relative_population_contrast": ratio,
            "echo_visibility": visibility[delay],
            "relative_echo_visibility": visibility[delay] / echo_short if echo_valid else None,
            "relaxation_only_echo_ratio": math.sqrt(ratio) if ratio is not None else None}
    return {"valid": all(row["valid"] for row in rows.values()),
            "normalization_delay_us": delays[0], "by_delay_us": rows,
            "assumptions": [
                "Square-root population contrast is a relaxation-only benchmark under exponential, stationary Markovian relaxation.",
                "Preparation/readout transfer and rotation errors must remain stable; the fixed rotation-end offset cancels in ratios under that model.",
                "No intrinsic pure-dephasing rate is inferred from these measurements."]}


def json_safe(value):
    """Snapshot numeric configurations without lossy repr fallbacks or NaN JSON."""
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, complex):
        return {"__complex__": json_safe([value.real, value.imag])}
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise TypeError(f"unsupported acquisition metadata type: {type(value).__name__}")


def source_file_sha256(paths):
    return {str(Path(path)): hashlib.sha256(Path(path).read_bytes()).hexdigest()
            for path in paths}


def schedule(block, *, sites=SITES_GHZ, delays=DELAYS_US):
    if not isinstance(block, int) or block < 0:
        raise ValueError("block index must be a nonnegative integer")
    sites = tuple(sites) if block % 2 == 0 else tuple(reversed(sites))
    delays = tuple(delays) if block % 2 == 0 else tuple(reversed(delays))
    phases = PHASES_DEG if block % 2 == 0 else tuple(reversed(PHASES_DEG))
    return [{"frequency_ghz": frequency,
             "echo_arms": [(delay, phase) for delay in delays
                           for phase in phases],
             "control_pre_phases": phases,
             "control_post_phases": tuple(reversed(phases))}
            for frequency in sites]


def rabi_gate(half_response, twice_response):
    half, twice = float(half_response), float(twice_response)
    return {"valid": bool(math.isfinite(half) and math.isfinite(twice) and
                          .25 <= half <= .75 and -.2 <= twice <= .25),
            "pi2_response": half, "two_pi_response": twice}


def trace_report(cycles, *, delays=DELAYS_US):
    delays = tuple(delays)
    visibilities = {float(delay): square.phase_visibility(values)
                    for delay, values in cycles.items()}
    if set(visibilities) != set(delays):
        raise ValueError("focused trace needs every planned delay")
    ordered = [visibilities[delay]["visibility"] for delay in delays]
    revivals = sum(b - a > .10 for a, b in zip(ordered, ordered[1:]))
    usable = [(delay, value) for delay, value in zip(delays, ordered)
              if .06 <= value <= 2.]
    report = {"visibility": visibilities,
              "one_over_e": one_over_e_crossing(dict(zip(delays, ordered))),
              "revival_count": revivals,
              "fit_points": len(usable)}
    if len(usable) < 4:
        report["status"] = "insufficient_echo_contrast"
        return report
    times = np.asarray([item[0] for item in usable])
    logs = np.log([item[1] for item in usable])
    slope, intercept = np.polyfit(times, logs, 1)
    residual = logs - (slope * times + intercept)
    report.update({"status": "fit",
                   "rate_per_us": float(-slope),
                   "t2_echo_us": float(-1 / slope) if slope < 0 else None,
                   "log_fit_rms": float(np.sqrt(np.mean(residual ** 2)))})
    return report


def one_over_e_crossing(visibility_by_delay):
    """Interpolate the first unambiguous 1/e crossing, without a decay fit."""
    pairs = sorted((float(delay), float(value))
                   for delay, value in visibility_by_delay.items())
    if (len(pairs) < 2 or any(not math.isfinite(t) or
                             not math.isfinite(v) or v < 0 for t, v in pairs)
            or any(b[0] <= a[0] for a, b in zip(pairs, pairs[1:]))
            or pairs[0][1] < .55):
        return {"valid": False, "reason": "invalid or weak early visibility"}
    threshold = pairs[0][1] / math.e
    states = [value >= threshold for _, value in pairs]
    transitions = [index for index in range(1, len(states))
                   if states[index] != states[index-1]]
    if len(transitions) != 1 or states[transitions[0]]:
        return {"valid": False, "reason": "unbracketed or ambiguous crossing"}
    index = transitions[0]
    left_t, left_v = pairs[index - 1]
    right_t, right_v = pairs[index]
    time_us = left_t + (threshold-left_v)*(right_t-left_t)/(right_v-left_v)
    return {"valid": True, "time_us": float(time_us),
            "bracket_us": [left_t, right_t], "threshold": threshold}


def short_echo_gate(first_cycle, repeated_cycle):
    first = square.phase_visibility(first_cycle)
    repeated = square.phase_visibility(repeated_cycle)
    ratio = (repeated["visibility"] / first["visibility"]
             if first["visibility"] else math.nan)
    drift = math.degrees(abs(math.atan2(
        math.sin(first["phase_rad"] - repeated["phase_rad"]),
        math.cos(first["phase_rad"] - repeated["phase_rad"]))))
    return {"valid": bool(first["visibility"] >= .55 and
                          .7 <= ratio <= 1.3 and drift <= 20.),
            "first_visibility": first["visibility"],
            "repeated_visibility": repeated["visibility"],
            "visibility_ratio": ratio, "phase_drift_deg": drift}


def assess_single_point(blocks):
    eligible = [site["trace"]["rate_per_us"]
                for block in blocks for site in block["sites"]
                if site["status"] == "valid_controls" and
                site["trace"]["status"] == "fit" and
                site["trace"]["rate_per_us"] > 0 and
                site["trace"]["log_fit_rms"] <= .25 and
                site["trace"]["revival_count"] <= 1]
    rate_cv = (float(np.std(eligible, ddof=1) / np.mean(eligible))
               if len(eligible) >= 2 else None)
    return {"repeatable": bool(len(eligible) >= 3 and rate_cv <= .25),
            "eligible_blocks": len(eligible),
            "total_blocks": len(blocks),
            "rates_per_us": eligible,
            "rate_coefficient_of_variation": rate_cv}


def assess_local_map(blocks):
    sites = {}
    for frequency in LOCAL_MAP_SITES_GHZ:
        crossings = [site["trace"]["one_over_e"]["time_us"]
                     for block in blocks for site in block["sites"]
                     if site["frequency_ghz"] == frequency and
                     site["status"] == "valid_controls" and
                     site["trace"]["one_over_e"]["valid"]]
        cv = (float(np.std(crossings, ddof=1)/np.mean(crossings))
              if len(crossings) >= 2 else None)
        resolved = len(crossings) >= 2 and cv <= .20
        sites[f"{frequency:.3f}"] = {
            "status": "resolved" if resolved else "unresolved",
            "valid_blocks": len(crossings), "crossings_us": crossings,
            "mean_crossing_us": float(np.mean(crossings)) if crossings else None,
            "coefficient_of_variation": cv}
    return {"sites": sites, "resolved_sites": sum(
        site["status"] == "resolved" for site in sites.values()),
        "total_sites": len(sites)}


def validate_single_point_source(source):
    if (source.get("schema") != "q3.echo-focused-trace.v1" or
            source.get("session_id") != SINGLE_SOURCE_SESSION or
            source.get("status") != "complete" or
            source.get("code_commit", "")[:8] != "f7c12262" or
            source.get("correction_sha256") != localizer.CORRECTION_SHA256 or
            len(source.get("blocks", [])) != 2):
        raise ValueError("single-point source must be the pinned focused run")
    for block in source["blocks"]:
        matches = [site for site in block.get("sites", [])
                   if site.get("frequency_ghz") == SINGLE_SITE_GHZ]
        if (len(matches) != 1 or matches[0].get("status") != "valid_controls" or
                not matches[0].get("rabi_gate", {}).get("valid") or
                not matches[0].get("control_gate", {}).get("valid") or
                not float(matches[0].get("trace", {}).get("rate_per_us", 0)) > 0):
            raise ValueError("source lacks two control-valid 4.284-GHz echoes")


def scout_parameters(phase):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
        TLSPumpProbeWidePassiveScan as wide,
    )
    return {**wide.parameters(), "freq_min_ghz": 4.18,
            "freq_max_ghz": 4.29, "freq_step_mhz": 2.,
            "output_suffix": f"TLS_Echo_Focused_Trace_{phase}_T1"}


def plan(*, single_point=False, local_map=False, population_check=False, refocus_check=False):
    if sum(map(bool, (single_point, local_map, population_check, refocus_check))) > 1:
        raise ValueError("choose one echo mode")
    if refocus_check:
        return {"hardware_access": False,
                "purpose": "single-frequency Hahn X / Hahn Y / CPMG2 Y comparison",
                "sites_ghz": [POPULATION_SITE_GHZ],
                "sequences": list(refocus.SEQUENCES),
                "requested_pi2_center_elapsed_us": list(refocus.TIMES_US),
                "phase_cycle_deg": list(PHASES_DEG),
                "shots_per_arm": POPULATION_SHOTS,
                "reversed_blocks": POPULATION_BLOCKS,
                "matched_pi2_center_elapsed_time": True,
                "same_flux_envelope_for_all_filters": True,
                "filters_interleaved_with_rotating_order": True,
                "short_sentinel_each_filter": True,
                "strictly_constant_correction_during_science": True,
                "metric": "raw and early-normalized four-phase visibility",
                "t1_scans": None, "native_corrected_return_us": 40.,
                "terminal": "no custom progress messages"}
    if population_check:
        return {"hardware_access": False,
                "purpose": "single-frequency echo with matched population survival",
                "sites_ghz": [POPULATION_SITE_GHZ],
                "delays_us": list(POPULATION_DELAYS_US),
                "phase_cycle_deg": list(PHASES_DEG),
                "shots_per_arm": POPULATION_SHOTS,
                "reversed_blocks": POPULATION_BLOCKS,
                "matched_ground_excited_pair_each_delay": True,
                "one_pulse_half_and_two_pi_checks_at_each_block": True,
                "two_pulse_phase_controls_before_and_after_echo": True,
                "short_echo_sentinel_repeated_each_block": True,
                "require_constant_correction_during_science_window": True,
                "metric": "relative echo and population contrast with conditional square-root relaxation benchmark",
                "intrinsic_pure_dephasing_inference": False,
                "t1_scans": None, "native_corrected_return_us": 40.,
                "terminal": "no custom progress messages"}
    if local_map:
        return {"hardware_access": False,
                "purpose": "replicated local flux-ramp echo map",
                "sites_ghz": list(LOCAL_MAP_SITES_GHZ),
                "delays_us": list(SINGLE_DELAYS_US),
                "phase_cycle_deg": list(PHASES_DEG),
                "shots_per_arm": LOCAL_MAP_SHOTS,
                "reversed_blocks": LOCAL_MAP_BLOCKS,
                "one_pulse_half_and_two_pi_checks_at_each_site": True,
                "two_pulse_phase_controls_before_and_after_echo": True,
                "short_echo_sentinel_repeated_each_site": True,
                "metric": "interpolated 1/e echo visibility crossing",
                "t1_scans": None,
                "native_corrected_return_us": 40.,
                "terminal": "no custom progress messages"}
    if single_point:
        return {"hardware_access": False,
                "purpose": "validate a repeatable flux-ramp Hahn echo at 4.284 GHz",
                "sites_ghz": [SINGLE_SITE_GHZ],
                "delays_us": list(SINGLE_DELAYS_US),
                "phase_cycle_deg": list(PHASES_DEG),
                "shots_per_arm": SINGLE_SHOTS,
                "reversed_blocks": SINGLE_BLOCKS,
                "one_pulse_half_and_two_pi_checks_at_each_block": True,
                "two_pulse_phase_controls_before_and_after_echo": True,
                "short_echo_sentinel_repeated_each_block": True,
                "t1_scans": None,
                "native_corrected_return_us": 40.,
                "terminal": "no custom progress messages"}
    return {"hardware_access": False,
            "purpose": "test whether the 4.212-GHz echo-rate peak repeats",
            "sites_ghz": list(SITES_GHZ),
            "delays_us": list(DELAYS_US),
            "phase_cycle_deg": list(PHASES_DEG),
            "shots_per_arm": SHOTS, "reversed_blocks": 2,
            "one_pulse_half_and_two_pi_checks_at_each_site": True,
            "two_pulse_phase_controls_before_and_after_echo": True,
            "t1_scans": "narrow pre and post; no site selection",
            "native_corrected_return_us": 40.,
            "terminal": "no custom progress messages"}


def run(*, data_root=None, correction_json=None,
        single_point=False, local_map=False, population_check=False, refocus_check=False):
    if sum(map(bool, (single_point, local_map, population_check, refocus_check))) > 1:
        raise ValueError("choose one echo mode")
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
    source_path = data_root / "q3" / square.SOURCE_SESSION / "manifest.json"
    square.validate_source(json.loads(source_path.read_text(encoding="utf-8")))
    focused_source_path = None
    if single_point:
        focused_source_path = (data_root / "q3" / SINGLE_SOURCE_SESSION /
                               "manifest.json")
        validate_single_point_source(json.loads(
            focused_source_path.read_text(encoding="utf-8")))
    audit_enabled = population_check or refocus_check
    sites = ((POPULATION_SITE_GHZ,) if audit_enabled else
             LOCAL_MAP_SITES_GHZ if local_map else
             (SINGLE_SITE_GHZ,) if single_point else SITES_GHZ)
    delays = (refocus.TIMES_US if refocus_check else
              POPULATION_DELAYS_US if population_check else
              SINGLE_DELAYS_US if (single_point or local_map) else DELAYS_US)
    shots = (POPULATION_SHOTS if audit_enabled else
             LOCAL_MAP_SHOTS if local_map else
             SINGLE_SHOTS if single_point else SHOTS)
    blocks = (POPULATION_BLOCKS if audit_enabled else
              LOCAL_MAP_BLOCKS if local_map else
              SINGLE_BLOCKS if single_point else 2)
    session_id = (("q3_echo_refocus_check_" if refocus_check else
                   "q3_echo_population_check_" if population_check else
                   "q3_echo_local_map_" if local_map else
                   "q3_echo_single_point_" if single_point else
                   "q3_echo_focused_trace_") +
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
    manifest = {"schema": ("q3.echo-refocus-check.v1" if refocus_check else
                            "q3.echo-population-check.v1" if population_check else
                            "q3.echo-local-map.v1" if local_map else
                            "q3.echo-single-point.v1" if single_point else
                            "q3.echo-focused-trace.v1"), "status": "running",
                "session_id": session_id, "code_commit": commit,
                "source_manifest": str(source_path),
                "correction_json": str(correction),
                "correction_sha256": localizer.CORRECTION_SHA256,
                "plan": plan(single_point=single_point, local_map=local_map,
                             population_check=population_check, refocus_check=refocus_check),
                "blocks": []}
    if focused_source_path is not None:
        manifest["focused_source_manifest"] = str(focused_source_path)
    dual.checkpoint(path, manifest)
    try:
        if not (single_point or local_map or audit_enabled):
            manifest["t1_pre_csv"] = str(localizer.run(
                data_root=data_root, correction_json=correction,
                parameter_overrides=scout_parameters("pre"), announce=False))
            dual.checkpoint(path, manifest)
        with localizer.scan_environment(correction):
            tls.QUBIT, tls.SET_YOKO, tls.outerFolder = "q3", False, str(data_root)
            five.install_scan_calibration(tls)
            base = ProductionResetSession.passive().apply(tls.BaseConfig)
            five.apply_verified_feedback_timing(base)
            if int(base["ff_park_gain"]) != -25146:
                raise RuntimeError("q3 park gain differs from verified setting")
            dc, realized = _integer_dc_grid(wide.parameters(),
                                            np.asarray(sites), tls)
            dc_lookup = {frequency: int(gain)
                         for frequency, gain in zip(sites, dc)}
            manifest["realized_frequency_ghz"] = realized.tolist()
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
            if audit_enabled:
                from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
                manifest["population_correction_window"] = validate_population_correction(
                    ff_pulse.load_compensation(base),
                    settle_us=base["flux_settle_time_us"])
            control_class = fast.make_program(resident.ResidentDriveProgram)
            echo_class = square.make_echo_program(resident.ResidentDriveProgram)
            refocus_class = refocus.make_program(resident.ResidentDriveProgram) if refocus_check else None
            soc, soccfg = tls.makeProxy()
            bundle = runtime_bundle(base)
            if audit_enabled:
                config_folder = folder / "program_configs"
                config_folder.mkdir()
                audit_path = folder / "acquisition_metadata.json"
                audit = {"effective_base_config": json_safe(base),
                         "board_configuration": json_safe(soc.get_cfg()),
                         "source_file_sha256": source_file_sha256([
                             __file__, fast.__file__, square.__file__,
                             resident.__file__, ff_pulse.__file__]),
                         "acquisitions": []}
                if refocus_check:
                    audit["source_file_sha256"].update(source_file_sha256([refocus.__file__]))
                manifest["acquisition_metadata_json"] = str(audit_path)
                dual.checkpoint(audit_path, audit)

            def configuration(frequency, kind, *, phase=0, delay=None,
                              duration=None):
                arm = {"flux_ghz": frequency,
                       "drive_mhz": 1000 * frequency + square.DRIVE_OFFSET_MHZ,
                       "gain": square.GAIN_DAC,
                       "reference_state": None,
                       "preparation_state": "g", "pre_drive_us": PRE_US,
                       "post_drive_us": POST_US, "shots": shots}
                cfg = resident.arm_config(base, arm, dc_lookup)
                if kind in refocus.SEQUENCES:
                    cfg["refocus_elapsed_us"] = float(delay)
                    cfg["refocus_sequence"] = kind
                    cfg["echo_phase_deg"] = int(phase)
                    # Exact clock-quantized window is recorded by the pulse builder.
                    cfg["ff_hold"] = PRE_US + POST_US + delay + PI2_US + .01
                elif kind in ("pop_g", "pop_e"):
                    cfg = population_config(cfg, kind, delay)
                elif kind == "echo":
                    cfg["echo_delay_us"] = float(delay)
                    cfg["echo_phase_deg"] = int(phase)
                    cfg["ff_hold"] = PRE_US + POST_US + square.echo_window_us(delay)
                else:
                    cfg["fast_pulse_us"] = float(
                        duration if duration is not None else
                        (PI2_US if kind in ("zero", "control") else PI_US))
                    cfg["fast_second_phase_deg"] = (
                        int(phase) if kind == "control" else None)
                    cfg["opx_resident_gain"] = (0 if kind == "zero"
                                                else square.GAIN_DAC)
                    count = 2 if kind == "control" else 1
                    cfg["ff_hold"] = (PRE_US + POST_US + count *
                                      (cfg["fast_pulse_us"] + .01))
                return cfg

            def program_class(kind):
                return (refocus_class if kind in refocus.SEQUENCES else
                        echo_class if kind == "echo" else control_class)

            compile_arms = ([("control", None)] +
                            [(kind, delay) for kind in refocus.SEQUENCES
                             for delay in delays]) if refocus_check else [
                                 ("control", None), ("echo", delays[0]), ("echo", delays[-1])]
            if population_check:
                compile_arms.extend((kind, delay) for kind in ("pop_g", "pop_e")
                                    for delay in (delays[0], delays[-1]))
            for frequency in dict.fromkeys((sites[0], sites[-1])):
                for kind, delay in compile_arms:
                    cfg = configuration(frequency, kind, phase=270, delay=delay)
                    program_class(kind)(soccfg, cfg, bundle.payload, bundle.loop)
            manifest["compiled_edges"] = True
            dual.checkpoint(path, manifest)

            def acquire(frequency, kind, *, phase=0, delay=None,
                        duration=None, label=None):
                cfg = configuration(frequency, kind, phase=phase,
                                    delay=delay, duration=duration)
                program = program_class(kind)(soccfg, cfg, bundle.payload, bundle.loop)
                if audit_enabled:
                    if label is None:
                        raise ValueError("audited acquisition needs an IQ label")
                    config_path = config_folder / f"block{block}_{label}.json"
                    config_path.write_text(json.dumps(
                        json_safe(program.cfg), indent=2, allow_nan=False) + "\n",
                        encoding="utf-8")
                    acquisition = {
                        "block": block, "frequency_ghz": frequency,
                        "label": label, "kind": kind, "delay_us": delay,
                        "phase_deg": phase if kind in ("echo", "control", *refocus.SEQUENCES) else None,
                        "program_class": type(program).__name__,
                        "program_config_json": str(config_path),
                        "raw_npz": str(folder / f"block{block}_{round(1000*frequency)}MHz.npz"),
                        "started_at_utc": datetime.now(timezone.utc).isoformat(),
                        "status": "running"}
                    audit["acquisitions"].append(acquisition)
                    dual.checkpoint(audit_path, audit)
                    started = time.monotonic()
                try:
                    records = _run_program(
                        soc, program, max(30., _block_timeout_s(cfg, shots)),
                        cfg, total_shots=shots)
                except BaseException as exc:
                    if audit_enabled:
                        acquisition["status"] = "failed"
                        acquisition["error"] = f"{type(exc).__name__}: {exc}"
                    raise
                else:
                    if audit_enabled:
                        acquisition["records_received"] = len(records)
                        acquisition["status"] = "complete" if len(records) == shots else "incomplete"
                finally:
                    if audit_enabled:
                        acquisition["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
                        acquisition["elapsed_s"] = time.monotonic() - started
                        dual.checkpoint(audit_path, audit)
                if len(records) != shots:
                    raise RuntimeError("incomplete focused-echo IQ records")
                return resident.record_iq(records)

            for block in range(blocks):
                block_entry = {"index": block, "sites": []}
                manifest["blocks"].append(block_entry)
                dual.checkpoint(path, manifest)
                for entry in schedule(block, sites=sites, delays=delays):
                    frequency = entry["frequency_ghz"]
                    raw = {}
                    zero_pre = acquire(frequency, "zero", label="zero_pre")
                    pi_pre = acquire(frequency, "pi", label="pi_pre")
                    raw["zero_pre"], raw["pi_pre"] = zero_pre, pi_pre
                    acquired = []

                    def take(name, kind, *, phase=0, delay=None,
                             duration=None):
                        iq = acquire(frequency, kind, phase=phase,
                                     delay=delay, duration=duration, label=name)
                        raw[name] = iq
                        acquired.append((name, iq))

                    take("rabi_half", "pi", duration=PI2_US)
                    take("rabi_twice", "pi", duration=TWO_PI_US)
                    for phase in entry["control_pre_phases"]:
                        take(f"control_pre_{phase}", "control", phase=phase)
                    if refocus_check:
                        for kind, delay, phase in refocus_schedule(block):
                            take(f"{kind}_{round(delay*1000)}ns_{phase}", kind,
                                 phase=phase, delay=delay)
                    elif population_check:
                        for kind, delay, phase in population_schedule(block):
                            label = f"{kind}_{round(delay*1000)}ns"
                            if kind == "echo":
                                label += f"_{phase}"
                            take(label, kind, phase=phase or 0, delay=delay)
                    else:
                        for delay, phase in entry["echo_arms"]:
                            take(f"echo_{round(delay * 1000)}ns_{phase}", "echo",
                                 phase=phase, delay=delay)
                    if refocus_check:
                        for phase in entry["control_post_phases"]:
                            for kind in refocus.SEQUENCES:
                                take(f"sentinel_{kind}_{phase}", kind,
                                     phase=phase, delay=delays[0])
                    elif single_point or local_map or population_check:
                        for phase in entry["control_post_phases"]:
                            take(f"sentinel_{round(delays[0]*1000)}ns_{phase}",
                                 "echo", phase=phase, delay=delays[0])
                    for phase in entry["control_post_phases"]:
                        take(f"control_post_{phase}", "control", phase=phase)
                    zero_post = acquire(frequency, "zero", label="zero_post")
                    pi_post = acquire(frequency, "pi", label="pi_post")
                    raw["zero_post"], raw["pi_post"] = zero_post, pi_post
                    raw_path = folder / f"block{block}_{round(1000*frequency)}MHz.npz"
                    np.savez_compressed(raw_path, **{
                        f"{name}_i": iq.real.astype(np.int64)
                        for name, iq in raw.items()}, **{
                        f"{name}_q": iq.imag.astype(np.int64)
                        for name, iq in raw.items()})
                    refs = (zero_pre.mean(), pi_pre.mean(),
                            zero_post.mean(), pi_post.mean())
                    bracket = fast.score_reference_bracket(*refs)
                    point = {"frequency_ghz": frequency,
                             "raw_npz": str(raw_path),
                             "reference_bracket": bracket,
                             "status": "unresolved_reference"}
                    if bracket["valid"]:
                        responses = {name: fast.bracketed_response(
                            iq.mean(), *refs, (position + 1) /
                            (len(acquired) + 1))
                            for position, (name, iq) in enumerate(acquired)}
                        point["rabi_gate"] = rabi_gate(
                            responses["rabi_half"], responses["rabi_twice"])
                        controls = {
                            label: {phase: responses[f"{label}_{phase}"]
                                    for phase in PHASES_DEG}
                            for label in ("control_pre", "control_post")}
                        point["control_gate"] = square.control_stability_gate(
                            controls["control_pre"], controls["control_post"])
                        if refocus_check:
                            point["control_phases"] = controls
                            cycles = {kind: {delay: {phase: responses[
                                f"{kind}_{round(delay*1000)}ns_{phase}"]
                                for phase in PHASES_DEG} for delay in delays}
                                for kind in refocus.SEQUENCES}
                            sentinels = {kind: {phase: responses[f"sentinel_{kind}_{phase}"]
                                                for phase in PHASES_DEG}
                                         for kind in refocus.SEQUENCES}
                            point["refocus_phases"] = cycles
                            point["sentinel_phases"] = sentinels
                            point["refocus_comparison"] = refocus_report(cycles)
                            point["short_echo_gates"] = {kind: short_echo_gate(
                                cycles[kind][delays[0]], sentinels[kind])
                                for kind in refocus.SEQUENCES}
                            common_valid = point["rabi_gate"]["valid"] and point["control_gate"]["valid"]
                            point["sequence_valid"] = {kind: common_valid and gate["valid"]
                                                       for kind, gate in point["short_echo_gates"].items()}
                            point["status"] = ("valid_controls" if all(point["sequence_valid"].values())
                                               else "unresolved_local_control")
                        else:
                            cycles = {delay: {
                                phase: responses[f"echo_{round(delay*1000)}ns_{phase}"]
                                for phase in PHASES_DEG} for delay in delays}
                            point["rabi_responses"] = {
                                "half": responses["rabi_half"],
                                "twice": responses["rabi_twice"]}
                            point["control_phases"] = controls
                            point["echo_phases"] = cycles
                            point["trace"] = trace_report(cycles, delays=delays)
                            if single_point or local_map or population_check:
                                sentinel = {phase: responses[
                                    f"sentinel_{round(delays[0]*1000)}ns_{phase}"]
                                    for phase in PHASES_DEG}
                                point["sentinel_phases"] = sentinel
                                point["short_echo_gate"] = short_echo_gate(
                                    cycles[delays[0]], sentinel)
                            point["status"] = (
                                "valid_controls" if point["rabi_gate"]["valid"] and
                                point["control_gate"]["valid"] and
                                (not (single_point or local_map or population_check) or
                                 point["short_echo_gate"]["valid"]) else
                                "unresolved_local_control")
                            if population_check:
                                populations = {delay: {state: responses[
                                    f"pop_{state}_{round(delay*1000)}ns"]
                                    for state in ("g", "e")} for delay in delays}
                                point["population_comparison"] = population_report(cycles, populations)
                                if (point["status"] == "valid_controls" and
                                        not point["population_comparison"]["valid"]):
                                    point["status"] = "unresolved_population_control"
                    block_entry["sites"].append(point)
                    dual.checkpoint(path, manifest)

        if refocus_check:
            manifest["refocus_assessment"] = {
                "valid_blocks_by_sequence": {kind: sum(site.get("sequence_valid", {}).get(kind, False)
                    for block in manifest["blocks"] for site in block["sites"])
                    for kind in refocus.SEQUENCES},
                "intrinsic_pure_dephasing_inferred": False}
        elif single_point:
            manifest["single_point_assessment"] = assess_single_point(
                manifest["blocks"])
        elif local_map:
            manifest["local_map_assessment"] = assess_local_map(
                manifest["blocks"])
        elif population_check:
            manifest["population_assessment"] = {
                "valid_blocks": sum(site["status"] == "valid_controls"
                                    for block in manifest["blocks"] for site in block["sites"]),
                "total_blocks": len(manifest["blocks"]),
                "intrinsic_pure_dephasing_inferred": False}
        else:
            manifest["t1_post_csv"] = str(localizer.run(
                data_root=data_root, correction_json=correction,
                parameter_overrides=scout_parameters("post"), announce=False))
        manifest["valid_site_blocks"] = sum(
            site["status"] == "valid_controls"
            for block in manifest["blocks"] for site in block["sites"])
        manifest["status"] = ("complete_refocus_check" if refocus_check else
                              "complete_population_check" if population_check else
                              "complete_local_map" if local_map else
                              "complete_repeatable_echo" if single_point and
                              manifest["single_point_assessment"]["repeatable"]
                              else "complete_echo_unresolved" if single_point
                              else "complete")
        dual.checkpoint(path, manifest)
        return path
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
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--correction-json", type=Path)
    experiment = parser.add_mutually_exclusive_group()
    experiment.add_argument("--single-point", action="store_true",
                        help="validate one 4.284-GHz flux-ramp echo before mapping")
    experiment.add_argument("--local-map", action="store_true",
                        help="map five nearby flux-ramp echoes with local checks")
    experiment.add_argument("--population-check", action="store_true",
                        help="compare one short echo trace with matched population survival")
    experiment.add_argument("--refocus-check", action="store_true",
                        help="compare Hahn X, Hahn Y, and CPMG2 at matched elapsed times")
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(plan(single_point=args.single_point,
                              local_map=args.local_map,
                              population_check=args.population_check,
                              refocus_check=args.refocus_check), indent=2))
    else:
        run(data_root=args.data_root, correction_json=args.correction_json,
            single_point=args.single_point, local_map=args.local_map,
            population_check=args.population_check, refocus_check=args.refocus_check)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
