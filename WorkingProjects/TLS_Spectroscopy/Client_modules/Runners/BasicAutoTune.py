"""Run the fixed-readout-duration single-qubit calibration portfolio.

This is intentionally a report-only entry point.  It measures the best screened
full parameter tuple at every integer readout duration from 1 through 20 us and
never modifies ``BaseConfig``; the operator makes the final manual choice.
"""

import copy
import datetime
import math
from statistics import NormalDist

from scipy.stats import t as student_t

from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import (
    BaseConfig,
    outerFolder,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mBasicAutoTuner import (
    BASIC_DEFAULTS,
    BasicAutoTuner,
    TUNED_KEYS,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import config_updater


QUBIT = "q4"
LIVE_PLOTS = False

# Portfolio rows are alternatives for an operator, not one automatically selected
# calibration.  Keep the destructive path disabled unconditionally for this runner.
APPLY_CONFIG = False

# This is a private deep copy so edits made for a run cannot mutate the module defaults
# or leak into a second experiment in the same Python process.
P_BASIC = copy.deepcopy(BASIC_DEFAULTS)

# Tests and interactive runners may replace ``BasicAutoTuner`` with an acquisition
# facade.  Keep the certificate implementation immutable so destructive-boundary
# validation can never be replaced along with the hardware-facing class.
_BASIC_AUTOTUNER_CERTIFICATE = BasicAutoTuner

# Discovery is device-independent by default: BASIC_DEFAULTS searches a validated
# +/-100-MHz prior around the frequencies loaded from initialize.py.  A device runner
# may still provide explicit search_min/max overrides, but this entry point contains
# no q4 frequency constants.


def _result_dict(acquired, experiment):
    """Accept both ExperimentClass-style and direct-dictionary acquire results."""
    if isinstance(acquired, dict):
        nested = acquired.get("data")
        if isinstance(nested, dict):
            return nested
        return acquired
    data = getattr(experiment, "data", None)
    return data if isinstance(data, dict) else {}


def _best_candidate(result):
    for key in ("best_found", "best_candidate", "best"):
        candidate = result.get(key)
        if isinstance(candidate, dict):
            return candidate
    working = result.get("working")
    if isinstance(working, dict) and any(
            _finite(_number(working, (key,)))
            for key in ("fidelity", "ss_fidelity", "fid", "mean_fidelity")):
        return working
    return None


def _number(mapping, keys, default=float("nan")):
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                pass
    return float(default)


def _finite(value):
    if isinstance(value, (str, bytes)):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def _rounded_int(value, default=0):
    try:
        if not math.isfinite(float(value)):
            return int(default)
        return int(round(float(value)))
    except (TypeError, ValueError, OverflowError):
        return int(default)


def _as_tuple(value):
    return tuple(value) if isinstance(value, (list, tuple)) else ()


def _as_sequence(value):
    if isinstance(value, (list, tuple)):
        return list(value)
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        converted = tolist()
        return converted if isinstance(converted, list) else [converted]
    return []


def _candidate_key(candidate):
    try:
        return (
            round(float(candidate["read_pulse_freq"]), 9),
            int(round(float(candidate["read_pulse_gain"]))),
            round(float(candidate["read_length"]), 9),
            round(float(candidate["qubit_pi_freq"]), 9),
            int(round(float(candidate["qubit_pi_gain"]))),
            round(float(candidate["sigma"]), 9),
            round(float(candidate.get("qubit_drag_beta", 0.0)), 9),
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return ()


def _crossfit_timing_evidence_errors(row):
    """Independently reconstruct one aggregate's held-out timing statistics."""
    if not isinstance(row, dict):
        return ["the timing certificate row is malformed"]
    evidence = _BASIC_AUTOTUNER_CERTIFICATE._latency_fidelity_evidence(row)
    blocks = _rounded_int(_number(row, ("confirmation_blocks",), 0))
    fidelities = list(evidence.get("block_fidelities", []))
    shot_ses = list(evidence.get("block_fidelity_ses", []))
    if (evidence.get("estimator") != "two_fold_crossfit" or blocks < 2
            or len(fidelities) != blocks or len(shot_ses) != blocks
            or not all(_finite(value) and 0.0 <= float(value) <= 1.0
                       for value in fidelities)
            or not all(_finite(value) and float(value) >= 0.0
                       for value in shot_ses)):
        return ["the timing certificate lacks complete cross-fit blocks"]
    values = [float(value) for value in fidelities]
    errors = [float(value) for value in shot_ses]
    mean = sum(values) / blocks
    between = math.sqrt(sum((value - mean) ** 2 for value in values)
                        / (blocks - 1)) / math.sqrt(blocks)
    within = math.sqrt(sum(value ** 2 for value in errors)) / blocks
    standard_error = max(between, within)
    spread = max(values) - min(values)
    reported_spread = _number(
        row, ("crossfit_block_spread", "block_spread"))
    if (not math.isclose(
                evidence["fidelity"], mean, rel_tol=0.0, abs_tol=1e-9)
            or not math.isclose(
                evidence["fidelity_se"], standard_error,
                rel_tol=0.0, abs_tol=1e-9)
            or not math.isclose(
                evidence["fidelity_lcb_95"], mean - 1.96 * standard_error,
                rel_tol=0.0, abs_tol=1e-9)
            or not _finite(reported_spread)
            or not math.isclose(
                reported_spread, spread, rel_tol=0.0, abs_tol=1e-9)):
        return ["the cross-fit timing-block summary is inconsistent"]
    return []


def _timing_recovery_rank(row):
    evidence = _BASIC_AUTOTUNER_CERTIFICATE._latency_fidelity_evidence(row)
    lcb = _number(evidence, ("fidelity_lcb_95",))
    mean = _number(evidence, ("fidelity",))
    if not _finite(lcb):
        lcb = float("-inf")
    if not _finite(mean):
        mean = float("-inf")
    return (float(lcb), float(mean))


def _same_tuned_value(key, first, second):
    try:
        if key.endswith("gain"):
            return int(round(float(first))) == int(round(float(second)))
        return math.isclose(float(first), float(second), rel_tol=0.0, abs_tol=1e-9)
    except (TypeError, ValueError, OverflowError):
        return first == second


def _leakage_policy(params, startup_cfg):
    """Reconstruct the leakage policy actually passed to the experiment."""
    settings = params.get("leakage", {}) if isinstance(params, dict) else {}
    if not isinstance(settings, dict):
        settings = {}
    mode = settings.get("enabled", "auto")
    if isinstance(mode, str) and mode.lower() == "auto":
        strict_active = any(_finite(_number(source, (key,))) for source, key in (
            (startup_cfg, "qubit_ef_freq"),
            (startup_cfg, "qubit_anharmonicity_mhz"),
            (settings, "anharmonicity_prior_mhz"),
        ))
    else:
        strict_active = bool(mode)
    operational_active = bool(settings.get("operational_enabled", True))
    active = bool(strict_active or operational_active)
    required = bool(active and settings.get("required_for_write", True))
    return strict_active, operational_active, active, required


def _write_contract_errors(result, eligible, startup_cfg, params=None):
    """Independently validate every certificate at the destructive boundary."""
    errors = []
    if not isinstance(result, dict):
        return ["result payload is not a dictionary"]
    if not isinstance(eligible, dict):
        return ["eligible_tuned is not a dictionary"]
    if not isinstance(startup_cfg, dict):
        return ["startup configuration snapshot is not a dictionary"]
    if params is None:
        params = P_BASIC
    if not isinstance(params, dict):
        return ["autotuner parameter snapshot is not a dictionary"]
    if not bool(result.get("final_stable", False)):
        errors.append("final_stable is false")
    if not bool(result.get("fidelity_replay_stable", False)):
        errors.append("the exact final fidelity replay is not stable")

    discovery = result.get("discovery")
    if (not isinstance(discovery, dict)
            or not bool(discovery.get("verified_for_write", False))
            or discovery.get("missing_for_write")):
        errors.append("critical discovery is not independently verified")
    maps = result.get("maps")
    for stage_name in ("resonator", "spectroscopy"):
        stage_policy = params.get(stage_name, {})
        if not isinstance(stage_policy, dict) or not stage_policy.get(
                "enabled", True):
            continue
        stage_map = maps.get(stage_name) if isinstance(maps, dict) else None
        if (not isinstance(stage_map, dict)
                or not bool(stage_map.get("search_complete", False))
                or not bool(stage_map.get("selection_confirmed", False))):
            errors.append(
                "%s discovery lacks its reproduced measurement map" % stage_name)
        absolute = bool(
            stage_policy.get("search_min_mhz") is not None
            and stage_policy.get("search_max_mhz") is not None)
        relative = stage_policy.get("search_radius_mhz") is not None
        bounded = bool(absolute or relative)
        if (bounded and isinstance(stage_map, dict)
                and not bool(stage_map.get("used_global_scan", False))):
            errors.append(
                "%s discovery did not use the configured search envelope"
                % stage_name)
        if isinstance(stage_map, dict) and bounded:
            if absolute:
                expected_min = _number(stage_policy, ("search_min_mhz",))
                expected_max = _number(stage_policy, ("search_max_mhz",))
            else:
                center_key = ("read_pulse_freq" if stage_name == "resonator"
                              else "qubit_pi_freq")
                center = _number(startup_cfg, (center_key,))
                radius = _number(stage_policy, ("search_radius_mhz",))
                expected_min, expected_max = center - radius, center + radius
            measured_min = _number(stage_map, ("allowed_min_mhz",))
            measured_max = _number(stage_map, ("allowed_max_mhz",))
            if (not all(_finite(value) for value in (
                    expected_min, expected_max, measured_min, measured_max))
                    or not math.isclose(
                        measured_min, expected_min,
                        rel_tol=0.0, abs_tol=1e-9)
                    or not math.isclose(
                        measured_max, expected_max,
                        rel_tol=0.0, abs_tol=1e-9)):
                errors.append(
                    "%s discovery map does not match the configured prior"
                    % stage_name)
    resonator_map = maps.get("resonator") if isinstance(maps, dict) else None
    spectroscopy_map = (
        maps.get("spectroscopy") if isinstance(maps, dict) else None)
    resonator_candidates = (_as_sequence(
        resonator_map.get("candidate_frequencies_mhz"))
        if isinstance(resonator_map, dict) else [])
    if len(resonator_candidates) > 1:
        if (not bool(resonator_map.get("branch_backtracking_complete", False))
                or not isinstance(spectroscopy_map, dict)
                or not bool(spectroscopy_map.get(
                    "branch_backtracking_complete", False))):
            errors.append(
                "multiple resonator candidates lack completed branch backtracking")
        selected_resonator = _number(
            resonator_map, ("selected_frequency_mhz",))
        selected_spectroscopy = _number(
            spectroscopy_map if isinstance(spectroscopy_map, dict) else {},
            ("selected_resonator_branch_mhz",))
        if (not _finite(selected_resonator)
                or not _finite(selected_spectroscopy)
                or not math.isclose(
                    selected_resonator, selected_spectroscopy,
                    rel_tol=0.0, abs_tol=1e-6)):
            errors.append(
                "the resonator and spectroscopy branch selections disagree")
        viable = _as_sequence(spectroscopy_map.get(
            "resonator_branch_valid")) if isinstance(
                spectroscopy_map, dict) else []
        if sum(bool(value) for value in viable) > 1:
            iq_map = maps.get("iq_rabi") if isinstance(maps, dict) else None
            iq_selected = _number(
                iq_map if isinstance(iq_map, dict) else {},
                ("selected_resonator_branch_mhz",))
            if (not isinstance(iq_map, dict)
                    or not bool(iq_map.get("branch_selection_confirmed", False))
                    or not _finite(iq_selected)
                    or not math.isclose(
                        iq_selected, selected_resonator,
                        rel_tol=0.0, abs_tol=1e-6)):
                errors.append(
                    "multiple spectral branches lack coherent Rabi/direct-SS "
                    "selection")
    joint_policy = params.get("joint_search", {})
    if isinstance(joint_policy, dict) and joint_policy.get("enabled", True):
        joint = result.get("joint_search")
        joint_map = maps.get("joint_search") if isinstance(maps, dict) else None
        coverage = joint.get("coverage") if isinstance(joint, dict) else None
        if (not isinstance(joint, dict)
                or str(joint.get("status")) != "complete"
                or not isinstance(coverage, dict)
                or not bool(coverage.get("complete", False))
                or int(coverage.get("expected_strata", 0)) < 1
                or int(coverage.get("measured_strata", -1))
                != int(coverage.get("expected_strata", 0))
                or coverage.get("missing_strata")):
            errors.append("the structured joint-search coverage is incomplete")
        if (not isinstance(joint_map, dict)
                or not bool(joint_map.get("search_complete", False))
                or not bool(joint_map.get("selection_confirmed", False))):
            errors.append("the joint-search winner lacks held-out confirmation")
    fidelity_gate = result.get("write_fidelity_gate")
    if (not isinstance(fidelity_gate, dict)
            or not bool(fidelity_gate.get("passed", False))):
        errors.append("the write-fidelity certificate did not pass")
    control = result.get("control_validation")
    if (not isinstance(control, dict)
            or not bool(control.get("required_for_write", False))
            or not bool(control.get("verified_for_write", False))):
        errors.append("the exact-waveform coherent-control certificate did not pass")
    else:
        selected_key = _as_tuple(control.get("selected_control_key"))
        audit_key = _as_tuple(control.get("fresh_exact_audit_key"))
        if not selected_key or selected_key != audit_key:
            errors.append("the fresh control audit does not match the selected tuple")

    leakage = result.get("leakage", {})
    strict_policy, operational_policy, leakage_policy_active, leakage_required = (
        _leakage_policy(params, startup_cfg))
    if not isinstance(leakage, dict):
        errors.append("the leakage certificate is malformed")
    else:
        if bool(leakage.get("active", False)) != leakage_policy_active:
            errors.append("the reported leakage mode disagrees with run policy")
        if bool(leakage.get("strict_direct_active", False)) != strict_policy:
            errors.append("the reported direct-leakage mode disagrees with run policy")
        if bool(leakage.get("operational_active", False)) != operational_policy:
            errors.append("the reported operational screen disagrees with run policy")
        if bool(leakage.get("required_for_write", False)) != leakage_required:
            errors.append("the reported leakage requirement disagrees with run policy")
        if leakage_required and not bool(leakage.get("verified", False)):
            errors.append("the required leakage/safety certificate did not pass")
        if leakage_required and operational_policy:
            settings = params.get("leakage", {})
            if not isinstance(settings, dict):
                settings = {}
            maximum_cluster = _number(
                settings, ("max_third_cluster_fraction",))
            maximum_single_state = _number(
                settings, ("max_single_state_third_cluster_fraction",))
            measured_cluster = _number(
                leakage, ("worst_third_cluster_fraction_ucb_95",))
            measured_single_state = _number(
                leakage,
                ("worst_third_cluster_single_state_fraction_ucb_95",))
            if not bool(leakage.get("third_cluster_guard", False)):
                errors.append("the 2-D third-population safety guard is absent")
            if (not all(_finite(value) for value in (
                    maximum_cluster, maximum_single_state,
                    measured_cluster, measured_single_state))
                    or measured_cluster > maximum_cluster
                    or measured_single_state > maximum_single_state):
                errors.append(
                    "the resolved third-population limits were not satisfied")

    eligibility = result.get("eligibility")
    if (not isinstance(eligibility, dict)
            or not bool(eligibility.get("atomic_tuple_safe", False))
            or not bool(eligibility.get("discovery_verified", False))
            or not bool(eligibility.get("write_fidelity_qualified", False))
            or not bool(eligibility.get("control_verified", False))):
        errors.append("the atomic eligibility certificate is incomplete")

    best = result.get("best_found")
    tuned = result.get("tuned")
    if not isinstance(best, dict) or not isinstance(tuned, dict):
        errors.append("the measured/tuned tuple payload is incomplete")
        return errors
    if not str(best.get("label", "")).startswith("final exact"):
        errors.append("best_found is not an exact final replay")
    if ("qubit_freq" not in best or "qubit_pi_freq" not in best
            or not _same_tuned_value(
                "qubit_pi_freq", best.get("qubit_freq"),
                best.get("qubit_pi_freq"))):
        errors.append("qubit_freq and qubit_pi_freq do not identify one transition")

    final_policy = params.get("final", {})
    if not isinstance(final_policy, dict):
        final_policy = {}
    minimum_lcb = _number(final_policy, ("minimum_write_fidelity_lcb",))
    confidence_sigma = _number(final_policy, ("confidence_sigma",))
    maximum_spread = _number(final_policy, ("max_block_spread",))
    required_blocks = _rounded_int(_number(final_policy, ("blocks",), 0))
    best_fidelity = _number(best, ("fidelity",))
    best_se = _number(best, ("fidelity_se",))
    best_lcb = _number(best, ("fidelity_lcb_95",))
    certified_lcb = (_number(fidelity_gate, ("measured_lcb",))
                     if isinstance(fidelity_gate, dict) else float("nan"))
    certified_minimum = (_number(fidelity_gate, ("minimum_lcb",))
                         if isinstance(fidelity_gate, dict) else float("nan"))
    blocks = _rounded_int(_number(best, ("confirmation_blocks",), 0))
    block_spread = _number(best, ("block_spread",))
    block_fidelities = best.get("block_fidelities")
    finite_fidelity = bool(
        _finite(best_fidelity) and 0.0 <= best_fidelity <= 1.0
        and _finite(best_se) and best_se >= 0.0
        and _finite(best_lcb) and _finite(confidence_sigma)
        and confidence_sigma > 0.0)
    if not finite_fidelity:
        errors.append("the final fidelity evidence is incomplete or nonphysical")
    else:
        independently_derived_lcb = best_fidelity - confidence_sigma * best_se
        if not math.isclose(
                best_lcb, independently_derived_lcb,
                rel_tol=0.0, abs_tol=1e-9):
            errors.append("best_found fidelity LCB is internally inconsistent")
    if (not _finite(minimum_lcb) or not _finite(certified_minimum)
            or not math.isclose(
                certified_minimum, minimum_lcb, rel_tol=0.0, abs_tol=1e-12)):
        errors.append("the certified fidelity floor disagrees with run policy")
    if (not _finite(certified_lcb) or not _finite(best_lcb)
            or not math.isclose(
                certified_lcb, best_lcb, rel_tol=0.0, abs_tol=1e-9)):
        errors.append("the fidelity gate does not identify best_found")
    independently_qualified = bool(
        _finite(best_lcb) and _finite(minimum_lcb) and best_lcb >= minimum_lcb)
    if (not isinstance(fidelity_gate, dict)
            or bool(fidelity_gate.get("passed", False)) != independently_qualified):
        errors.append("the fidelity-gate verdict is internally inconsistent")
    if (required_blocks < 1 or blocks < required_blocks
            or not _finite(block_spread) or not _finite(maximum_spread)
            or block_spread > maximum_spread):
        errors.append("the final repeated fidelity replay is incomplete or unstable")
    if (blocks < 1 or not isinstance(block_fidelities, (list, tuple))
            or len(block_fidelities) != blocks
            or not all(_finite(value) and 0.0 <= float(value) <= 1.0
                       for value in block_fidelities)):
        errors.append("the final fidelity blocks are missing or malformed")
    else:
        derived_mean = sum(float(value) for value in block_fidelities) / blocks
        derived_spread = max(block_fidelities) - min(block_fidelities)
        if (not math.isclose(
                    best_fidelity, derived_mean, rel_tol=0.0, abs_tol=1e-9)
                or not math.isclose(
                    block_spread, derived_spread,
                    rel_tol=0.0, abs_tol=1e-9)):
            errors.append("the final fidelity-block summary is inconsistent")

    # Reconstruct the timing policy from raw evidence.  Do not trust the experiment's
    # boolean: this is the last boundary before initialize.py is modified.
    latency_policy = params.get("latency", {})
    if not isinstance(latency_policy, dict):
        latency_policy = {}
    if bool(latency_policy.get("enabled", True)):
        latency = result.get("latency_optimization")
        if not isinstance(latency, dict):
            errors.append("the enabled latency policy has no timing record")
        else:
            minimum_latency_mean = _number(
                latency_policy, ("minimum_mean_fidelity",))
            minimum_latency_lcb = _number(
                latency_policy, ("minimum_lcb_fidelity",))
            maximum_loss = _number(latency_policy, ("max_fidelity_loss",))
            configured_final_drop = _number(
                latency_policy, ("max_final_fidelity_drop",))
            maximum_final_drop = (min(max(configured_final_drop, 0.0),
                                      max(maximum_loss, 0.0))
                                  if _finite(configured_final_drop)
                                  and _finite(maximum_loss) else float("nan"))
            certified = latency.get("certified_selected")
            certificate_valid = bool(latency.get(
                "latency_certificate_valid", False))
            status = str(latency.get("status", ""))
            certified_status = bool(
                status in ("selected", "selected_control_recovery")
                or (status.startswith("retained_reference")
                    and status != "retained_reference_timing_uncertain"))
            fallback_status = bool(
                status in ("not_run", "retained_reference_timing_uncertain")
                or status.startswith(("failed_", "not_run_", "invalidated_")))
            if not (certified_status or fallback_status):
                errors.append("the timing result has an unknown status")
            timing_was_active = bool(
                certified_status or status.startswith("invalidated_"))
            if (bool(latency.get("timing_certificate_was_active", False))
                    != timing_was_active):
                errors.append("the reported timing-certificate activity is inconsistent")

            final_timing = _BASIC_AUTOTUNER_CERTIFICATE._latency_fidelity_evidence(
                best)
            certified_timing = _BASIC_AUTOTUNER_CERTIFICATE._latency_fidelity_evidence(
                certified if isinstance(certified, dict) else best)
            final_timing_fidelity = _number(final_timing, ("fidelity",))
            final_timing_se = _number(final_timing, ("fidelity_se",))
            final_timing_lcb = _number(final_timing, ("fidelity_lcb_95",))
            certified_fidelity = _number(certified_timing, ("fidelity",))
            derived_final_guard = bool(
                not timing_was_active
                or (all(_finite(value) for value in (
                        final_timing_fidelity, final_timing_lcb,
                        minimum_latency_mean, minimum_latency_lcb,
                        certified_fidelity, maximum_final_drop))
                    and final_timing_fidelity >= minimum_latency_mean
                    and final_timing_lcb >= minimum_latency_lcb
                    and final_timing_fidelity
                    >= certified_fidelity - maximum_final_drop))
            if (bool(latency.get("final_fidelity_guard_passed", False))
                    != derived_final_guard):
                errors.append("the reported final timing-fidelity guard is inconsistent")
            if (not isinstance(eligibility, dict)
                    or bool(eligibility.get(
                        "latency_final_fidelity_guard", False))
                    != derived_final_guard):
                errors.append("the eligibility timing-fidelity guard is inconsistent")
            if not derived_final_guard:
                errors.append("the final tuple violates the latency fidelity floors")
            if (timing_was_active
                    and (not _finite(final_timing_se)
                         or final_timing_se < 0.0)):
                errors.append("the final held-out timing fidelity is incomplete")

            final_key = _candidate_key(best)
            certified_key = (_candidate_key(certified)
                             if isinstance(certified, dict) else ())
            reported_key = _as_tuple(latency.get("certified_selected_key"))
            exact_certificate_match = bool(
                certified_status and final_key and certified_key
                and final_key == certified_key
                and reported_key == certified_key and derived_final_guard)
            if (bool(latency.get("certificate_matches_final_tuple", False))
                    != exact_certificate_match):
                errors.append("the timing certificate tuple-match verdict is inconsistent")
            if certified_status and (not _finite(maximum_loss)
                    or not math.isclose(
                        _number(latency, ("max_fidelity_loss",)), maximum_loss,
                        rel_tol=0.0, abs_tol=1e-12)
                    or not math.isclose(
                        _number(latency, ("max_final_fidelity_drop",)),
                        maximum_final_drop, rel_tol=0.0, abs_tol=1e-12)):
                errors.append("the timing fidelity limits disagree with run policy")
            if fallback_status and (certificate_valid
                    or bool(latency.get("qualified_speedup", False))):
                errors.append("an uncertified timing fallback claims a speedup")
            recovery_exact_status = (
                status == "failed_final_timing_guard_retained_exact_final")
            recovery_reference_status = (
                status
                == "failed_final_timing_guard_retained_fidelity_reference")
            if recovery_exact_status or recovery_reference_status:
                recovery = latency.get("reference_recovery")
                probe = latency.get("late_final_guard_probe")
                selected_after_recovery = latency.get("selected")
                original = (recovery.get("original_final")
                            if isinstance(recovery, dict) else None)
                recovered = (recovery.get("recovered_reference")
                              if isinstance(recovery, dict) else None)
                original_key = _candidate_key(original)
                recovered_key = _candidate_key(recovered)
                selected_after_key = _candidate_key(selected_after_recovery)
                recovery_selected_key = _as_tuple(
                    recovery.get("selected_candidate_key")
                    if isinstance(recovery, dict) else None)
                original_rank = _timing_recovery_rank(original)
                recovered_rank = (_timing_recovery_rank(recovered)
                                  if isinstance(recovered, dict) else None)
                reported_original_rank = _as_tuple(
                    recovery.get("original_rank")
                    if isinstance(recovery, dict) else None)
                reported_recovered_rank = _as_tuple(
                    recovery.get("recovered_rank")
                    if isinstance(recovery, dict) else None)
                rank_record_valid = bool(
                    len(reported_original_rank) == 2
                    and all(_finite(value) for value in reported_original_rank)
                    and all(math.isclose(
                        float(reported_original_rank[index]), original_rank[index],
                        rel_tol=0.0, abs_tol=1e-9) for index in range(2)))
                if recovered_rank is not None:
                    rank_record_valid = bool(
                        rank_record_valid and len(reported_recovered_rank) == 2
                        and all(_finite(value)
                                for value in reported_recovered_rank)
                        and all(math.isclose(
                            float(reported_recovered_rank[index]),
                            recovered_rank[index], rel_tol=0.0, abs_tol=1e-9)
                            for index in range(2)))
                else:
                    rank_record_valid = bool(
                        rank_record_valid
                        and recovery.get("recovered_rank") is None)
                special_common_valid = bool(
                    isinstance(recovery, dict)
                    and isinstance(probe, dict)
                    and probe.get("passed") is False
                    and recovery.get("comparison_estimator")
                    == "two_fold_crossfit_lcb_then_mean"
                    and isinstance(recovery.get("original_stable"), bool)
                    and original_key and final_key
                    and not _crossfit_timing_evidence_errors(original)
                    and rank_record_valid)
                if recovery_reference_status:
                    special_valid = bool(
                        special_common_valid
                        and recovery.get("attempted") is True
                        and recovery.get("passed") is True
                        and recovery.get("adopted") is True
                        and recovered_key
                        and not _crossfit_timing_evidence_errors(recovered)
                        and (recovery.get("original_stable") is False
                             or recovered_rank > original_rank)
                        and final_key == recovered_key == selected_after_key
                        == recovery_selected_key
                        and _candidate_key(latency.get("reference"))
                        == recovered_key)
                else:
                    no_distinct_reference = bool(
                        recovery.get("attempted") is False
                        and recovery.get("passed") is False
                        and recovered is None
                        and _candidate_key(latency.get("reference"))
                        == original_key)
                    replayed_but_worse = bool(
                        recovery.get("attempted") is True
                        and recovery.get("passed") is True
                        and recovered_key
                        and not _crossfit_timing_evidence_errors(recovered)
                        and original_rank >= recovered_rank)
                    special_valid = bool(
                        special_common_valid
                        and recovery.get("original_stable") is True
                        and recovery.get("adopted") is False
                        and (no_distinct_reference or replayed_but_worse)
                        and final_key == original_key == selected_after_key
                        == recovery_selected_key)
                if not special_valid:
                    errors.append(
                        "the failed timing-reference recovery contract is invalid")
            if certificate_valid:
                if not exact_certificate_match:
                    errors.append("the timing certificate does not identify best_found")
                reference = latency.get("reference")
                comparisons = _rounded_int(_number(
                    latency, ("familywise_comparison_count",), 0))
                reported_z = _number(
                    latency, ("familywise_confidence_sigma",))
                family_alpha = _number(
                    latency_policy, ("familywise_alpha",), 0.05)
                base_z = _number(
                    latency_policy, ("confidence_sigma",), 1.96)
                if (not isinstance(reference, dict) or comparisons < 1
                        or not _finite(reported_z) or not _finite(family_alpha)
                        or not _finite(base_z)
                        or not 0.0 < family_alpha < 1.0):
                    errors.append("the familywise timing evidence is incomplete")
                else:
                    diagnostics = latency.get("diagnostics", [])
                    diagnostic_count = len({
                        _as_tuple(row.get("candidate_key"))
                        for row in diagnostics if isinstance(row, dict)
                        and _as_tuple(row.get("candidate_key"))
                    })
                    maximum_looks = 1 + max(_rounded_int(_number(
                        latency_policy, ("adaptive_confirmation_rounds",), 0)), 0)
                    minimum_comparisons = max(
                        diagnostic_count * max(diagnostic_count - 1, 0)
                        * maximum_looks, 1)
                    if comparisons < minimum_comparisons:
                        errors.append(
                            "the timing family omits candidate pairs or adaptive looks")
                    latency_map = maps.get("latency") if isinstance(maps, dict) else None
                    confirmations = (latency_map.get("confirmations", [])
                                     if isinstance(latency_map, dict) else [])
                    record_rejected = latency.get(
                        "infeasible_reference_keys",
                        latency.get("safety_rejected_anchor_keys", []))
                    rejected_keys = {
                        _as_tuple(value) for value in record_rejected
                        if _as_tuple(value)
                    }
                    mapped_rejected = {
                        _as_tuple(value) for value in (
                            latency_map.get("infeasible_reference_keys",
                                latency_map.get("safety_rejected_anchor_keys", []))
                            if isinstance(latency_map, dict) else [])
                        if _as_tuple(value)
                    }
                    if mapped_rejected != rejected_keys:
                        errors.append(
                            "the timing record and map disagree on infeasible arms")
                    failed_audit_keys = {
                        _as_tuple(row.get("candidate_key"))
                        for collection in (
                            latency.get("anchor_control_audits", []),
                            latency.get("anchor_safety_audits", []))
                        for row in collection if isinstance(row, dict)
                        and row.get("passed") is False
                        and _as_tuple(row.get("candidate_key"))
                    }
                    if not rejected_keys.issubset(failed_audit_keys):
                        errors.append(
                            "an excluded timing arm lacks a failed physical audit")
                    reference_rows = [
                        row for row in confirmations if isinstance(row, dict)
                        and _candidate_key(row) not in rejected_keys]
                    reference_blocks = [
                        _rounded_int(_number(
                            row, ("confirmation_blocks",), 0))
                        for row in reference_rows]
                    pairing_sets = []
                    for row, block_count in zip(
                            reference_rows, reference_blocks):
                        raw_ids = row.get("block_pairing_ids", [])
                        ids = (tuple(str(value) for value in raw_ids)
                               if isinstance(raw_ids, (list, tuple)) else ())
                        if (len(ids) != block_count
                                or len(set(ids)) != len(ids)):
                            pairing_sets = []
                            errors.append(
                                "the timing arms lack valid shared drift cohorts")
                            break
                        pairing_sets.append(set(ids))
                    common_pairing_count = (len(set.intersection(*pairing_sets))
                                            if pairing_sets else 0)
                    if (reference_blocks
                            and common_pairing_count < min(reference_blocks)):
                        errors.append(
                            "the timing arms were not replayed in one common "
                            "interleaved drift cohort")
                    derived_df = (min(reference_blocks) - 1
                                  if reference_blocks else -1)
                    reported_df = _rounded_int(_number(
                        latency, ("familywise_degrees_of_freedom",), -1), -1)
                    if (str(latency.get("familywise_distribution", ""))
                            != "student_t" or derived_df < 1
                            or reported_df != derived_df):
                        errors.append(
                            "the finite-block timing distribution is inconsistent")
                    required_z = max(
                        base_z,
                        NormalDist().inv_cdf(1.0 - family_alpha / comparisons),
                        float(student_t.ppf(
                            1.0 - family_alpha / comparisons,
                            max(derived_df, 1))))
                    if reported_z + 1e-12 < required_z:
                        errors.append("the timing confidence multiplier is too small")
                    for row in reference_rows + [certified, best]:
                        row_errors = _crossfit_timing_evidence_errors(row)
                        if row_errors:
                            errors.extend(row_errors)
                            break
                    pairwise = [_BASIC_AUTOTUNER_CERTIFICATE.
                                _latency_noninferiority(
                        row, certified, maximum_loss, reported_z)
                        for row in reference_rows]
                    recomputed = (max(pairwise, key=lambda row: float(
                        row.get("loss_ucb", float("inf")))) if pairwise else {})
                    diagnostic = next((row for row in diagnostics
                                       if isinstance(row, dict)
                                       and _as_tuple(row.get("candidate_key"))
                                       == certified_key), None)
                    selected_timing = (_BASIC_AUTOTUNER_CERTIFICATE.
                                       _latency_fidelity_evidence(certified))
                    selected_blocks = _rounded_int(_number(
                        certified, ("confirmation_blocks",), 0))
                    selected_spread = _number(
                        certified, ("crossfit_block_spread", "block_spread"))
                    maximum_timing_spread = _number(
                        latency_policy, ("max_block_spread",))
                    selected_simultaneous_lcb = float(
                        selected_timing["fidelity"]
                        - reported_z * selected_timing["fidelity_se"])
                    if (not pairwise
                            or not all(row.get("eligible", False)
                                       for row in pairwise)
                            or not isinstance(diagnostic, dict)
                            or not bool(diagnostic.get("accepted", False))
                            or not _finite(_number(diagnostic, ("loss_ucb",)))
                            or _number(diagnostic, ("loss_ucb",)) > maximum_loss
                            or not math.isclose(
                                _number(diagnostic, ("loss_ucb",)),
                                float(recomputed["loss_ucb"]),
                                rel_tol=0.0, abs_tol=1e-9)
                            or selected_timing["fidelity"] < minimum_latency_mean
                            or selected_simultaneous_lcb < minimum_latency_lcb
                            or selected_blocks < max(reference_blocks, default=0)
                            or not _finite(selected_spread)
                            or not _finite(maximum_timing_spread)
                            or selected_spread > maximum_timing_spread):
                        errors.append(
                            "the selected timing tuple lacks a valid loss certificate")
            if status in ("selected", "selected_control_recovery"):
                if (not certificate_valid or not exact_certificate_match
                        or not bool(latency.get("qualified_speedup", False))):
                    errors.append("the claimed timing speedup is not certified")
                reference_latency = _number(
                    latency, ("reference_latency_us",))
                selected_latency = _number(
                    latency, ("selected_latency_us",))
                if (not _finite(reference_latency) or not _finite(selected_latency)
                        or selected_latency >= reference_latency):
                    errors.append("the claimed timing speedup is not physically faster")
            elif status.startswith("retained_reference"):
                if (status != "retained_reference_timing_uncertain"
                        and (not certificate_valid or not exact_certificate_match
                             or bool(latency.get("qualified_speedup", False)))):
                    errors.append("the retained timing reference is inconsistent")
            elif certified_status and not certificate_valid:
                errors.append("the certified timing status has no valid certificate")
    try:
        expected_control_key = (
            round(float(best["qubit_pi_freq"]), 9),
            int(round(best["qubit_pi_gain"])),
            round(float(best["sigma"]), 9),
            round(float(best.get("qubit_drag_beta", 0.0)), 9),
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        expected_control_key = ()
    if (not expected_control_key or not isinstance(control, dict)
            or _as_tuple(control.get("selected_control_key"))
            != expected_control_key):
        errors.append("the control certificate does not identify best_found")
    control_policy = params.get("control_verify", {})
    if not isinstance(control_policy, dict):
        control_policy = {}
    required_control_blocks = _rounded_int(
        _number(control_policy, ("blocks",), 0))
    required_counts = tuple(sorted(set(
        _rounded_int(value) for value in _as_tuple(
            control_policy.get("pulse_counts"))
        if _rounded_int(value) > 0)))
    max_even = _number(control_policy, ("max_even_return_error_ucb",))
    max_odd = _number(control_policy, ("max_odd_inversion_error_ucb",))
    matching_witnesses = (control.get("matching_witnesses", [])
                          if isinstance(control, dict) else [])
    if not isinstance(matching_witnesses, (list, tuple)):
        matching_witnesses = []
    exact_witnesses = [
        row for row in matching_witnesses
        if isinstance(row, dict)
        and row.get("stage") == "final_control_verify"
        and bool(row.get("exact_tuple", False))
        and _as_tuple(row.get("control_key")) == expected_control_key
        and _rounded_int(row.get("blocks"), 0) >= required_control_blocks
        and tuple(sorted(set(_rounded_int(value) for value in
                             _as_tuple(row.get("pulse_counts")))))
        == required_counts
        and _finite(_number(row, ("worst_even_return_error_ucb",)))
        and _finite(_number(row, ("worst_odd_inversion_error_ucb",)))
        and _number(row, ("worst_even_return_error_ucb",)) <= max_even
        and _number(row, ("worst_odd_inversion_error_ucb",)) <= max_odd
    ]
    if (not bool(control_policy.get("enabled", True))
            or required_control_blocks < 1 or not required_counts
            or not _finite(max_even) or not _finite(max_odd)
            or not exact_witnesses):
        errors.append("the exact-waveform control witness is missing or inconsistent")
    expected_candidate_key = ()
    try:
        expected_candidate_key = (
            round(float(best["read_pulse_freq"]), 9),
            int(round(best["read_pulse_gain"])),
            round(float(best["read_length"]), 9),
            *expected_control_key,
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        pass

    for key in TUNED_KEYS:
        if key not in best or key not in tuned:
            errors.append("final tuned tuple is missing %s" % key)
        elif not _same_tuned_value(key, tuned[key], best[key]):
            errors.append("tuned.%s does not equal best_found" % key)
    derived_changed = {
        key for key in TUNED_KEYS
        if key in best and (
            key not in startup_cfg
            or not _same_tuned_value(key, best[key], startup_cfg[key]))
    }
    certified_changed = set(_as_tuple(
        eligibility.get("changed_keys")
        if isinstance(eligibility, dict) else None))
    eligible_keys = set(eligible)
    if certified_changed != derived_changed:
        errors.append(
            "eligibility.changed_keys does not match the independently derived "
            "atomic change set")
    if eligible_keys != derived_changed:
        errors.append(
            "eligible_tuned is not the complete independently derived atomic "
            "change set")
    if (isinstance(eligibility, dict)
            and bool(eligibility.get("write_needed", False))
            != bool(derived_changed)):
        errors.append("eligibility.write_needed disagrees with the final tuple")
    unknown = sorted(set(eligible) - set(TUNED_KEYS))
    if unknown:
        errors.append("eligible_tuned contains unknown keys: %s"
                      % ", ".join(str(key) for key in unknown))
    for key, value in eligible.items():
        if key not in TUNED_KEYS:
            continue
        if key not in best or key not in tuned:
            errors.append("eligible key %s is absent from the final tuple" % key)
            continue
        if (not _same_tuned_value(key, value, best[key])
                or not _same_tuned_value(key, value, tuned[key])):
            errors.append(
                "eligible key %s does not equal the measured final tuple" % key)
    if leakage_required:
        if (not isinstance(eligibility, dict)
                or not bool(eligibility.get("leakage_required", False))
                or not bool(eligibility.get("leakage_verified", False))
                or not bool(eligibility.get("leakage_tuple_match", False))
                or eligibility.get("final_replay_kind")
                != "leakage_constrained"):
            errors.append("the atomic leakage certificate is incomplete")
        if (not isinstance(leakage, dict)
                or not bool(leakage.get("selection_safe", False))
                or not bool(leakage.get("final_replay_complete", False))):
            errors.append("the required leakage-constrained replay is incomplete")
        if (not expected_candidate_key
                or _as_tuple(leakage.get("verified_candidate_key"))
                != expected_candidate_key):
            errors.append("the leakage certificate does not identify best_found")
    elif (isinstance(eligibility, dict)
          and bool(eligibility.get("leakage_required", False))):
        errors.append("eligibility invents a leakage requirement absent from policy")
    return errors


def _fmt_float(value, digits=6, suffix=""):
    return (("%%.%df" % int(digits)) % value) + suffix if _finite(value) else "n/a"


def _fmt_int(value, suffix=""):
    return (str(int(round(value))) + suffix) if _finite(value) else "n/a"


def _print_objective_candidate(heading, candidate, status=None):
    if not isinstance(candidate, dict):
        return
    read_freq = _number(candidate, ("read_pulse_freq", "read_freq"))
    read_gain = _number(candidate, ("read_pulse_gain", "read_gain"))
    read_length = _number(
        candidate, ("read_length", "read_length_us", "readout_length"))
    qubit_freq = _number(
        candidate, ("qubit_pi_freq", "drive_freq", "qubit_freq"))
    qubit_gain = _number(
        candidate, ("qubit_pi_gain", "pi_gain", "qubit_gain"))
    sigma = _number(candidate, ("sigma", "sigma_us", "qubit_sigma_us"))
    fidelity = _number(
        candidate, ("fidelity", "ss_fidelity", "fid", "mean_fidelity"))
    fidelity_se = _number(
        candidate, ("fidelity_se", "ss_fidelity_se", "fid_se"))
    safety_required = bool(candidate.get("safety_screen_required", False))
    safety_verified = bool(candidate.get(
        "safety_screen_verified_for_exact_tuple", not safety_required))
    print("\n[basic-auto-tune] %s" % heading)
    print("   readout %s / %s / %s | X180 %s / %s / %s | F %s%s"
          % (_fmt_float(read_freq, 6, " MHz"), _fmt_int(read_gain, " DAC"),
             _fmt_float(read_length, 3, " us"),
             _fmt_float(qubit_freq, 6, " MHz"), _fmt_int(qubit_gain, " DAC"),
             _fmt_float(4000.0 * sigma, 1, " ns"),
             _fmt_float(fidelity, 4),
             " +/- %.4f" % fidelity_se if _finite(fidelity_se) else ""))
    qualifiers = []
    if status:
        qualifiers.append(str(status).replace("_", " "))
    if safety_required:
        qualifiers.append("exact-tuple safety %s" % (
            "verified" if safety_verified else "not verified"))
    if qualifiers:
        print("   status  %s" % "; ".join(qualifiers))


def _print_duration_portfolio(result):
    """Print the twenty report-only parameter sets as one compact operator table."""
    portfolio = result.get("duration_portfolio", {})
    entries = portfolio.get("entries", []) if isinstance(portfolio, dict) else []
    if not entries:
        return False
    print("\n[basic-auto-tune] READOUT-DURATION PORTFOLIO (manual selection only)")
    print("   len  status        fidelity (95% LCB)   score    leakage 95% UCB   "
          "readout MHz/gain       X180 MHz/gain/length")
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        length = _number(entry, ("read_length_us",))
        status = str(entry.get("status", "INCONCLUSIVE")).upper()
        selected = entry.get("selected")
        if not isinstance(selected, dict):
            print("   %2sus %-13s no reportable tuple" % (
                _fmt_int(length), status))
            continue
        fidelity = _number(selected, ("fidelity",))
        fidelity_se = _number(selected, ("fidelity_se",))
        fidelity_lcb = _number(selected, ("fidelity_lcb_95",))
        score = _number(selected, ("portfolio_score",))
        third_ucb = _number(
            selected, ("portfolio_leakage_risk_ucb",
                       "third_cluster_fraction_ucb_95"))
        direct_p2 = _number(selected, ("single_p2_ucb",))
        leakage_text = (_fmt_float(100.0 * third_ucb, 1, "%")
                        if _finite(third_ucb) else "n/a")
        if _finite(direct_p2):
            leakage_text += "; P(f) %s" % _fmt_float(
                100.0 * direct_p2, 1, "%")
        gate_ns = 4000.0 * _number(selected, ("sigma",))
        print("   %2sus %-13s %s +/- %s (%s)   %s   %-19s   %s/%s   %s/%s/%s"
              % (_fmt_int(length), status,
                 _fmt_float(fidelity, 4), _fmt_float(fidelity_se, 4),
                 _fmt_float(fidelity_lcb, 4), _fmt_float(score, 4), leakage_text,
                 _fmt_float(_number(selected, ("read_pulse_freq",)), 6),
                 _fmt_int(_number(selected, ("read_pulse_gain",))),
                 _fmt_float(_number(selected, ("qubit_pi_freq",)), 6),
                 _fmt_int(_number(selected, ("qubit_pi_gain",))),
                 _fmt_float(gate_ns, 1, "ns")))
    print("   SAFE requires both the leakage-sensitive IQ/P(f) limits and the exact "
          "odd/even coherent-control audit. No row is written automatically.")
    print("   score = fidelity 95% LCB - IQ/direct-leakage 95% UCB"
          " (and 0.5 x amplified P(f) UCB when direct shelving is available).")
    return True


def _print_best(result):
    best = _best_candidate(result)
    if best is None:
        print("\n[basic-auto-tune] no single-shot candidate was measured.")
        return None

    if result.get("outcome") == "transition_qualification_failed":
        print("\n[basic-auto-tune] FREQUENCY QUALIFICATION FAILED -- "
              "THE 1-20 us PORTFOLIO WAS NOT RUN")
        gate = result.get("pre_expensive_gate", {})
        failures = gate.get("failures", []) if isinstance(gate, dict) else []
        if failures:
            print("   reason: %s" % "; ".join(str(value) for value in failures))
        qualification = result.get("control_branch_qualification", {})
        branches = qualification.get("branches", []) if isinstance(
            qualification, dict) else []
        for branch in branches:
            if not isinstance(branch, dict):
                continue
            detail = branch.get("parity_failure") or branch.get("control_failure")
            if detail:
                print("   %.6f MHz diagnostic: %s" % (
                    _number(branch, ("rabi_frequency_mhz",)), detail))
        _print_objective_candidate("BEST DIAGNOSTIC MEASUREMENT (NOT A TUNE)", best)
        return best

    portfolio_printed = _print_duration_portfolio(result)
    if not portfolio_printed:
        overall = result.get("best_overall_candidate")
        if not isinstance(overall, dict):
            overall = result.get("best_fidelity_replay")
        if isinstance(overall, dict):
            _print_objective_candidate("BEST OVERALL FIDELITY", overall)
        shortest = result.get("shortest_high_fidelity_candidate")
        if isinstance(shortest, dict):
            _print_objective_candidate(
                "SHORTEST HIGH-FIDELITY CANDIDATE", shortest,
                result.get("shortest_high_fidelity_status"))
        elif result.get("shortest_high_fidelity_status") == (
                "no_short_candidate_passed_exact_tuple_safety"):
            print("\n[basic-auto-tune] NO LEAKAGE-SAFE SHORT CANDIDATE WAS VERIFIED")
    else:
        return best

    read_freq = _number(best, ("read_pulse_freq", "read_freq"))
    read_gain = _number(best, ("read_pulse_gain", "read_gain"))
    read_length = _number(best, ("read_length", "read_length_us", "readout_length"))
    qubit_freq = _number(best, ("qubit_pi_freq", "drive_freq", "qubit_freq"))
    qubit_gain = _number(best, ("qubit_pi_gain", "pi_gain", "qubit_gain"))
    drag_beta = _number(
        best, ("qubit_drag_beta", "drag_beta"),
        BaseConfig.get("qubit_drag_beta", 0.0))
    sigma_us = _number(
        best, ("sigma", "sigma_us", "qubit_sigma_us"), BaseConfig.get("sigma", 0.0))
    fidelity = _number(best, ("fidelity", "ss_fidelity", "fid", "mean_fidelity"))
    fidelity_se = _number(best, ("fidelity_se", "ss_fidelity_se", "fid_se"))
    confirmations_value = _number(
        best, ("confirmation_blocks", "measurement_count", "blocks"), 0)
    confirmations = int(round(confirmations_value)) if _finite(confirmations_value) else 0

    leakage = result.get("leakage", {})
    leakage_active = bool(
        isinstance(leakage, dict) and leakage.get("active", False))
    leakage_verified = bool(
        isinstance(leakage, dict) and leakage.get("verified", False))
    if portfolio_printed:
        heading = "REPORT REFERENCE ONLY"
    elif leakage_active and leakage_verified:
        heading = "SELECTED CONFIG CANDIDATE (screened)"
    elif leakage_active:
        heading = "SELECTED CONFIG CANDIDATE (safety not verified)"
    else:
        heading = "SELECTED CONFIG CANDIDATE"
    print("\n[basic-auto-tune] %s%s" % (
        heading, " (not written)" if not APPLY_CONFIG else ""))
    print("   readout   %s / %s / %s"
          % (_fmt_float(read_freq, 6, " MHz"), _fmt_int(read_gain, " DAC"),
             _fmt_float(read_length, 3, " us")))
    gate_ns = 4000.0 * sigma_us if _finite(sigma_us) else float("nan")
    print("   X180      %s / %s / %s (sigma %s, DRAG %s)"
          % (_fmt_float(qubit_freq, 6, " MHz"), _fmt_int(qubit_gain, " DAC"),
             _fmt_float(gate_ns, 1, " ns"), _fmt_float(sigma_us, 6, " us"),
             _fmt_float(drag_beta, 5)))
    if _finite(fidelity_se):
        print("   step-5 F  %.4f +/- %.4f%s"
              % (fidelity, fidelity_se,
                 " (%d confirmation blocks)" % confirmations
                 if confirmations else ""))
    elif _finite(fidelity):
        print("   step-5 F  %.4f" % fidelity)
    else:
        print("   step-5 F  n/a")
    latency = result.get("latency_optimization", {})
    latency_status = str(latency.get("status", "")) if isinstance(
        latency, dict) else ""
    if (isinstance(latency, dict)
            and (latency_status in ("selected", "selected_control_recovery")
                 or latency_status.startswith("retained_reference"))):
        requested_chain = _number(
            latency, ("final_selected_integration_chain_us",
                      "integration_chain_us"))
        physical_chain = _number(
            latency, ("final_selected_latency_us", "selected_latency_us"))
        saved = _number(latency, ("latency_saved_us",))
        budget = _number(latency, ("max_fidelity_loss",))
        print("   timing     X180 + integration = %s; hardware chain %s"
              % (_fmt_float(requested_chain, 3, " us"),
                 _fmt_float(physical_chain, 3, " us")))
        if (latency_status in ("selected", "selected_control_recovery")
                and latency.get("latency_certificate_valid", False)
                and _finite(saved) and _finite(budget)):
            print("   tradeoff   saved %s versus the best-fidelity reference; "
                  "certified loss budget %.3f"
                  % (_fmt_float(saved, 3, " us"), budget))
        elif latency_status.startswith("retained_reference"):
            print("   tradeoff   no faster tuple proved the configured fidelity "
                  "requirement")
        timing_reference = latency.get("reference")
        if (latency.get("latency_certificate_valid", False)
                and isinstance(timing_reference, dict)
                and _candidate_key(timing_reference) != _candidate_key(best)):
            reference_step5 = _number(timing_reference, ("fidelity",))
            reference_crossfit = _number(
                timing_reference, ("crossfit_fidelity", "fidelity"))
            selected_crossfit = _number(
                best, ("crossfit_fidelity", "fidelity"))
            print("   reference  best held-out fidelity: step-5 %.4f, "
                  "cross-fit %.4f (selected cross-fit %.4f)"
                  % (reference_step5, reference_crossfit, selected_crossfit))
    elif latency_status == "failed_final_timing_guard_retained_fidelity_reference":
        print("   timing     the faster tuple did not reproduce within the fidelity "
              "budget; a fresh best-fidelity reference replay was retained")
    if isinstance(leakage, dict) and leakage.get("active", False):
        third = _number(leakage, ("worst_third_blob_excess_ucb",))
        if leakage.get("strict_direct_active", False):
            single = _number(leakage, ("worst_single_p2_ucb",))
            amplified = _number(leakage, ("worst_amplified_p2_ucb",))
            print("   leakage   %s | P(f) UCB one/amplified %s/%s | "
                  "third-cloud excess UCB %s"
                  % ("VERIFIED" if leakage.get("verified", False)
                     else "NOT VERIFIED",
                     _fmt_float(single, 4), _fmt_float(amplified, 4),
                     _fmt_float(third, 4)))
        else:
            if not _finite(third):
                third = _number(leakage, ("best_third_blob_excess_ucb",))
            cluster = _number(
                leakage, ("worst_third_cluster_fraction_ucb_95",))
            cluster_state = _number(
                leakage,
                ("worst_third_cluster_single_state_fraction_ucb_95",))
            print("   safety     fixed-Gaussian duration/power screen %s | "
                  "resolved third-population 95%% UCB %s overall/%s one-prep | "
                  "legacy tail-excess UCB %s (not a direct P(f) measurement)"
                  % ("PASSED" if leakage.get("verified", False) else "FAILED",
                     _fmt_float(100.0 * cluster, 1, "%"),
                     _fmt_float(100.0 * cluster_state, 1, "%"),
                     _fmt_float(third, 4)))
            if not leakage.get("verified", False) and leakage.get("failure"):
                print("   reason     %s" % leakage["failure"])
    fidelity_reference = result.get("best_fidelity_replay")
    if (isinstance(fidelity_reference, dict)
            and leakage_verified
            and _number(fidelity_reference, ("fidelity",))
            > fidelity + 5e-4):
        ref_fidelity = _number(fidelity_reference, ("fidelity",))
        ref_se = _number(fidelity_reference, ("fidelity_se",))
        print("   reference  unconstrained best F %.4f%s; the screened result above "
              "shows the measured safety tradeoff"
              % (ref_fidelity,
                 " +/- %.4f" % ref_se if _finite(ref_se) else ""))
    reset = result.get("reset", {})
    if isinstance(reset, dict):
        mode = str(reset.get("mode", "passive"))
        if mode == "feedback":
            print("   reset      feedback (%s, threshold %s, %.1f us cavity clear, "
                  "end-to-end validated)"
                  % (reset.get("oper", "?"), reset.get("threshold_raw", "?"),
                     _number(reset, ("thermalization_us",), 25.0)))
        else:
            print("   reset      passive fallback (%s us)" % _fmt_float(
                _number(reset, ("fallback_relax_delay_us",)), 1))
    return best


def _save_artifacts(experiment):
    """Make a best effort to retain partial data even after interruption/failure."""
    save_data = getattr(experiment, "save_data", None)
    if callable(save_data):
        try:
            save_data()
        except Exception as exc:
            print("[basic-auto-tune] save_data failed: %s" % exc)

    # Some experiment implementations create the composite plot during acquire;
    # others expose an explicit no-argument saver.  Support the latter without
    # depending on a private plotting method or plotting a second time.
    save_plot = getattr(experiment, "save_plot", None)
    if callable(save_plot):
        try:
            save_plot()
        except Exception as exc:
            print("[basic-auto-tune] save_plot failed: %s" % exc)


def _history_entry(result, eligible, applied, error=None):
    leakage = result.get("leakage", {})
    if not isinstance(leakage, dict):
        leakage = {}
    reset = result.get("reset", {})
    if not isinstance(reset, dict):
        reset = {}
    latency = result.get("latency_optimization", {})
    if not isinstance(latency, dict):
        latency = {}
    compact_latency = {key: latency.get(key) for key in (
        "enabled", "status", "status_before_invalidation", "reference_kind",
        "max_fidelity_loss", "familywise_confidence_sigma",
        "familywise_comparison_count", "familywise_distribution",
        "familywise_degrees_of_freedom", "confirmation_blocks",
        "reference_latency_us", "selected_latency_us", "latency_saved_us",
        "latency_reduction_fraction", "pre_safety_selected_fidelity_loss",
        "qualified_speedup", "control_screen_passed",
        "latency_certificate_valid", "certificate_matches_final_tuple",
        "timing_certificate_was_active", "final_fidelity_guard_passed",
        "final_timing_fidelity", "final_timing_fidelity_lcb_95",
        "final_timing_fidelity_estimator",
        "final_fidelity_drop_from_certificate",
        "max_final_fidelity_drop",
        "adaptive_rounds_completed", "final_selected_latency_us",
        "final_selected_integration_chain_us",
    ) if key in latency}
    candidate_keys = (
        "read_pulse_freq", "read_pulse_gain", "read_length",
        "qubit_pi_freq", "qubit_pi_gain", "sigma", "qubit_drag_beta",
        "fidelity", "fidelity_se", "fidelity_lcb_95", "latency_us",
        "crossfit_fidelity", "crossfit_fidelity_se",
        "crossfit_fidelity_lcb_95", "integration_chain_us",
    )
    for name in ("reference", "certified_selected", "final_selected"):
        candidate = latency.get(name)
        if isinstance(candidate, dict):
            compact_latency[name] = {
                key: candidate.get(key) for key in candidate_keys
                if key in candidate
            }
    selected_key = tuple(latency.get("certified_selected_key") or ())
    diagnostic = next((row for row in latency.get("diagnostics", [])
                       if tuple(row.get("candidate_key") or ()) == selected_key), None)
    if isinstance(diagnostic, dict):
        compact_latency["certificate"] = {
            key: diagnostic.get(key) for key in (
                "mean_loss", "loss_se", "loss_ucb", "confidence_z",
                "method", "accepted", "reason") if key in diagnostic
        }
    portfolio = result.get("duration_portfolio", {})
    compact_portfolio = None
    if isinstance(portfolio, dict) and portfolio.get("enabled", False):
        compact_portfolio = {key: portfolio.get(key) for key in (
            "enabled", "manual_selection_only", "automatic_write_allowed",
            "status", "requested_length_count", "reportable_length_count",
            "safe_length_count", "unsafe_length_count",
            "inconclusive_length_count", "equal_refinement_budget",
            "selection_objective", "leakage_penalty_weight",
            "amplified_leakage_penalty_weight",
        ) if key in portfolio}
        compact_portfolio["entries"] = []
        for entry in portfolio.get("entries", []):
            if not isinstance(entry, dict):
                continue
            selected = entry.get("selected")
            row = {key: entry.get(key) for key in (
                "read_length_us", "status", "leakage_status", "control_status")}
            if isinstance(selected, dict):
                row["selected"] = {key: selected.get(key) for key in (
                    *TUNED_KEYS, "fidelity", "fidelity_se",
                    "fidelity_lcb_95", "third_cluster_fraction_ucb_95",
                    "third_cluster_single_state_fraction_ucb_95",
                    "single_p2_ucb", "amplified_p2_ucb",
                    "portfolio_leakage_risk_ucb", "portfolio_score",
                ) if key in selected}
            compact_portfolio["entries"].append(row)
    return {
        "time": result.get(
            "time", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        "qubit": QUBIT,
        "tuner": "basic_manual_workflow",
        "revision": result.get("revision", result.get("autotuner_revision")),
        "outcome": result.get("outcome"),
        "failure": result.get("failure"),
        "runner_error": error,
        "best_found": result.get("best_found"),
        "best_fidelity_replay": result.get("best_fidelity_replay"),
        "best_overall_candidate": result.get("best_overall_candidate"),
        "shortest_high_fidelity_candidate": result.get(
            "shortest_high_fidelity_candidate"),
        "shortest_high_fidelity_status": result.get(
            "shortest_high_fidelity_status"),
        "duration_portfolio": compact_portfolio,
        "latency_optimization": compact_latency,
        "discovery": result.get("discovery"),
        "write_fidelity_gate": result.get("write_fidelity_gate"),
        "control_validation": result.get("control_validation"),
        "leakage": {
            "active": bool(leakage.get("active", False)),
            "strict_direct_active": bool(
                leakage.get("strict_direct_active", False)),
            "operational_active": bool(
                leakage.get("operational_active", False)),
            "verified": bool(leakage.get("verified", False)),
            "selection_safe": bool(leakage.get("selection_safe", False)),
            "worst_single_p2_ucb": leakage.get("worst_single_p2_ucb"),
            "worst_amplified_p2_ucb": leakage.get("worst_amplified_p2_ucb"),
            "worst_third_blob_excess_ucb": leakage.get(
                "worst_third_blob_excess_ucb"),
            "worst_third_cluster_fraction": leakage.get(
                "worst_third_cluster_fraction"),
            "worst_third_cluster_fraction_ucb_95": leakage.get(
                "worst_third_cluster_fraction_ucb_95"),
            "worst_third_cluster_single_state_fraction": leakage.get(
                "worst_third_cluster_single_state_fraction"),
            "worst_third_cluster_single_state_fraction_ucb_95": leakage.get(
                "worst_third_cluster_single_state_fraction_ucb_95"),
            "worst_even_return_error_ucb": leakage.get(
                "worst_even_return_error_ucb"),
            "worst_odd_inversion_error_ucb": leakage.get(
                "worst_odd_inversion_error_ucb"),
            "failure": leakage.get("failure"),
        },
        "reset": {
            "mode": reset.get("mode"), "fresh": reset.get("fresh"),
            "readout_key": reset.get("readout_key"),
            "threshold_raw": reset.get("threshold_raw"),
            "oper": reset.get("oper"),
            "ground_below": reset.get("ground_below"),
            "thermalization_us": reset.get("thermalization_us"),
            "validation": reset.get("validation"),
        },
        "eligible": dict(eligible),
        "applied": bool(applied),
        "old": {key: BaseConfig.get(key) for key in eligible},
        "new": dict(eligible) if applied else {},
    }


def main():
    # Capture the complete physical configuration before the first acquisition.  A
    # change to an untuned field (channels, switch/FF state, ADC timing, etc.) is
    # just as capable of creating an unmeasured hybrid tuple as a changed pi gain.
    startup_source_hash = config_updater.baseconfig_source_hash()
    soc, soccfg = makeProxy()
    cfg = dict(BaseConfig)
    experiment = BasicAutoTuner(
        soc=soc,
        soccfg=soccfg,
        path=QUBIT,
        outerFolder=outerFolder,
        suffix="Basic_Auto_Tune",
        cfg=cfg,
        params=copy.deepcopy(P_BASIC),
    )

    acquired = None
    acquire_error = None
    try:
        acquired = experiment.acquire(plotDisp=LIVE_PLOTS)
    except KeyboardInterrupt:
        acquire_error = "interrupted by operator"
        print("\n[basic-auto-tune] interrupted; preserving the best completed point.")
    except Exception as exc:
        acquire_error = "%s: %s" % (type(exc).__name__, exc)
        print("\n[basic-auto-tune] acquisition stopped (%s); preserving partial data."
              % acquire_error)
    finally:
        _save_artifacts(experiment)

    result = _result_dict(acquired, experiment)
    best = _print_best(result)

    # This is deliberately the sole source of configuration writes.  Diagnostic
    # ``tuned``/``working``/``best_found`` values must never reach initialize.py.
    eligible = result.get("eligible_tuned", {})
    if not isinstance(eligible, dict):
        print("[basic-auto-tune] invalid eligible_tuned payload; BaseConfig untouched.")
        eligible = {}
    else:
        eligible = dict(eligible)
    write_contract_errors = _write_contract_errors(
        result, eligible, cfg, params=P_BASIC)

    if not APPLY_CONFIG:
        try:
            config_updater.append_history(
                _history_entry(result, eligible, False, acquire_error))
        except Exception as exc:
            print("[basic-auto-tune] could not append calibration history: %s" % exc)
        if result.get("outcome") == "transition_qualification_failed":
            print("\n[basic-auto-tune] BaseConfig is untouched; resolve frequency "
                  "qualification before rerunning the portfolio.")
            if getattr(experiment, "iname", None):
                print("   Summary plot: %s" % experiment.iname)
            return 1
        if bool(result.get("manual_selection_required", False)):
            print("\n[basic-auto-tune] portfolio saved; BaseConfig is untouched. "
                  "Choose a row manually after reviewing fidelity and leakage.")
            if getattr(experiment, "iname", None):
                print("   Summary plot: %s" % experiment.iname)
            return 0 if best is not None else 1
        print("\n[basic-auto-tune] APPLY_CONFIG=False -- BaseConfig is untouched.")
        if eligible and not write_contract_errors:
            print("   The following repeated-final values would be eligible:")
            for key in sorted(eligible):
                print("   %-18s %-14s (current %s)"
                      % (key, eligible[key], BaseConfig.get(key)))
        elif write_contract_errors:
            print("   The measured result does not satisfy the independent write "
                  "contract: %s" % "; ".join(write_contract_errors))
        if getattr(experiment, "iname", None):
            print("   Summary plot: %s" % experiment.iname)
        # A completed or interrupted search with an empirical candidate is still a
        # useful dry run.  Reserve a nonzero code for runs that measured no candidate.
        return 0 if best is not None else 1

    if acquire_error is not None:
        print("\n[basic-auto-tune] the run did not finish cleanly; refusing to write "
              "even if a partial eligible_tuned payload exists.")
        try:
            config_updater.append_history(
                _history_entry(result, eligible, False, acquire_error))
        except Exception as exc:
            print("[basic-auto-tune] could not append calibration history: %s" % exc)
        return 0 if best is not None else 1

    if (bool(result.get("interrupted", False))
            or result.get("outcome") not in ("completed", "completed_with_warnings")
            or not bool(result.get("final_stable", False))
            or bool(write_contract_errors)):
        leakage = result.get("leakage", {})
        discovery = result.get("discovery", {})
        fidelity_gate = result.get("write_fidelity_gate", {})
        control = result.get("control_validation", {})
        missing_discovery = (discovery.get("missing_for_write", [])
                             if isinstance(discovery, dict) else [])
        if (bool(result.get("fidelity_replay_stable", False))
                and missing_discovery):
            print("\n[basic-auto-tune] the best tuple was replayed, but critical "
                  "discovery did not validate %s; BaseConfig is untouched."
                  % ", ".join(str(value) for value in missing_discovery))
        elif (bool(result.get("fidelity_replay_stable", False))
              and isinstance(fidelity_gate, dict)
              and not bool(fidelity_gate.get("passed", True))):
            print("\n[basic-auto-tune] the best tuple was replayed, but its fidelity "
                  "LCB %s is below the %s write floor; BaseConfig is untouched."
                  % (_fmt_float(_number(fidelity_gate, ("measured_lcb",)), 3),
                     _fmt_float(_number(fidelity_gate, ("minimum_lcb",)), 3)))
        elif (bool(result.get("fidelity_replay_stable", False))
              and isinstance(control, dict)
              and control.get("required_for_write", False)
              and not bool(control.get("verified_for_write", False))):
            print("\n[basic-auto-tune] the best tuple was replayed, but no coherent "
                  "Rabi/repeated-pulse witness matched its exact frequency, gain, "
                  "duration, and DRAG; BaseConfig is untouched.")
        elif (bool(result.get("fidelity_replay_stable", False))
                and isinstance(leakage, dict)
                and leakage.get("active", False)
                and not bool(result.get("final_stable", False))):
            print("\n[basic-auto-tune] the fidelity replay completed, but the required "
                  "safety/write checks were not fully verified; BaseConfig is "
                  "untouched.")
            if leakage.get("failure"):
                print("   %s" % leakage["failure"])
        elif write_contract_errors:
            print("\n[basic-auto-tune] the result failed the independent write "
                  "contract; BaseConfig is untouched.")
            for error in write_contract_errors:
                print("   %s" % error)
        else:
            print("\n[basic-auto-tune] the run did not complete a stable final replay; "
                  "refusing every config write while retaining the best measurement.")
        try:
            config_updater.append_history(
                _history_entry(result, eligible, False,
                               "non-completed or interrupted outcome"))
        except Exception as exc:
            print("[basic-auto-tune] could not append calibration history: %s" % exc)
        return 0 if best is not None else 1

    if not eligible:
        print("\n[basic-auto-tune] no repeatedly verified values are eligible; "
              "BaseConfig is untouched.")
        try:
            config_updater.append_history(_history_entry(result, {}, False))
        except Exception as exc:
            print("[basic-auto-tune] could not append calibration history: %s" % exc)
        return 0 if best is not None else 1

    try:
        expected = {key: cfg[key] for key in TUNED_KEYS if key in cfg}
        changed = config_updater.update_baseconfig(
            eligible, expected=expected,
            expected_source_hash=startup_source_hash)
    except Exception as exc:
        try:
            config_updater.append_history(
                _history_entry(result, eligible, False,
                               "%s: %s" % (type(exc).__name__, exc)))
        except Exception as history_exc:
            print("[basic-auto-tune] could not append calibration history: %s"
                  % history_exc)
        raise

    config_updater.append_history(_history_entry(result, eligible, True))
    config_updater.prune_backups(keep=10)
    print("\n[basic-auto-tune] BaseConfig updated (%s):"
          % config_updater.config_path())
    for key in sorted(changed):
        old, new = changed[key]
        print("   %-18s %-14s -> %s" % (key, old, new))
    if ("qubit_pi2_gain" in BaseConfig
            and any(key in eligible for key in
                    ("qubit_pi_gain", "qubit_pi_freq", "sigma",
                     "qubit_drag_beta"))):
        print("[basic-auto-tune] WARNING: qubit_pi2_gain was not calibrated and is "
              "now stale; it was deliberately left unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
