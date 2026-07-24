"""Run the streamlined, manual-workflow single-qubit autotuner.

This is intentionally a separate entry point from ``AutoTune.py``.  After a
completed run, the basic tuner writes only the physical tuple that passed its
stable, repeated, exact final replay.  Interrupted, partial, or unstable runs
still save and report their best measurement without modifying ``BaseConfig``.
"""

import copy
import datetime
import math

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

# The write path remains guarded by a completed, stable exact final replay and a
# compare-and-swap check that initialize.py has not changed during acquisition.
# Set this to False only when an explicitly dry diagnostic run is desired.
APPLY_CONFIG = True

# This is a private deep copy so edits made for a run cannot mutate the module defaults
# or leak into a second experiment in the same Python process.
P_BASIC = copy.deepcopy(BASIC_DEFAULTS)

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
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def _rounded_int(value, default=0):
    try:
        if not math.isfinite(float(value)):
            return int(default)
        return int(round(float(value)))
    except (TypeError, ValueError, OverflowError):
        return int(default)


def _as_tuple(value):
    return tuple(value) if isinstance(value, (list, tuple)) else ()


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


def _print_best(result):
    best = _best_candidate(result)
    if best is None:
        print("\n[basic-auto-tune] no single-shot candidate was measured.")
        return None

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
    if leakage_active and leakage_verified and bool(result.get("final_stable", False)):
        heading = "BEST SCREENED CANDIDATE"
    elif leakage_active:
        heading = "BEST FIDELITY CANDIDATE (safety screen not verified)"
    else:
        heading = "BEST MEASURED CANDIDATE"
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
            print("   safety     fixed-Gaussian duration/power screen %s | "
                  "third-cloud excess UCB %s (not a direct P(f) measurement)"
                  % ("PASSED" if leakage.get("verified", False) else "FAILED",
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
