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

    if not APPLY_CONFIG:
        try:
            config_updater.append_history(
                _history_entry(result, eligible, False, acquire_error))
        except Exception as exc:
            print("[basic-auto-tune] could not append calibration history: %s" % exc)
        print("\n[basic-auto-tune] APPLY_CONFIG=False -- BaseConfig is untouched.")
        if eligible:
            print("   The following repeated-final values would be eligible:")
            for key in sorted(eligible):
                print("   %-18s %-14s (current %s)"
                      % (key, eligible[key], BaseConfig.get(key)))
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
            or not bool(result.get("final_stable", False))):
        leakage = result.get("leakage", {})
        if (bool(result.get("fidelity_replay_stable", False))
                and isinstance(leakage, dict)
                and leakage.get("active", False)
                and not bool(result.get("final_stable", False))):
            print("\n[basic-auto-tune] the fidelity replay completed, but the required "
                  "safety/write checks were not fully verified; BaseConfig is "
                  "untouched.")
            if leakage.get("failure"):
                print("   %s" % leakage["failure"])
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
