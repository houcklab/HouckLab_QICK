"""Offline analysis of Modified-Ramsey charge-parity records: reset checks, control comparisons,
quality gates, plots and the analyze_modified_ramsey_record pipeline. Method and rate conventions:
docs/experiments/modified_ramsey.md#analysis. Tests: tests/test_modified_ramsey_offline.py."""

import json
import math
import os

import matplotlib
import numpy as np

matplotlib.use("Agg")  # B1: stays until its own fix commit (design.md)
import matplotlib.pyplot as plt

from qicklab.analysis.dwell import dwell_time_statistics
from qicklab.analysis.hmm import fit_two_state_hmm
from qicklab.analysis.rates import (
    autocorrelation_rate_estimate,
    psd_rate_estimate,
    rate_vs_bin_size,
    remove_slow_drift,
)
from qicklab.analysis.readout import project_iq_trace


def reset_success_vs_cycle(reset_I, reset_Q, calibration, post_reset_I=None, post_reset_Q=None):
    """Report what the saved active-reset readouts actually establish.

    Reset readout k is acquired before corrective flip k. Consequently row 0
    is the pre-reset population and row k validates only the k corrections
    preceding it. The last corrective flip is not observable unless an
    explicit post-reset verification readout is supplied.
    """
    reset_I = np.atleast_2d(np.asarray(reset_I, dtype=float))
    reset_Q = np.atleast_2d(np.asarray(reset_Q, dtype=float))
    if reset_I.shape != reset_Q.shape:
        raise ValueError("reset_I and reset_Q shapes differ")
    threshold = calibration["threshold"]
    e_above = calibration["e_above_threshold"]

    def ground_fraction(i_values, q_values):
        projected = project_iq_trace(i_values, q_values, calibration)
        ground = projected <= threshold if e_above else projected > threshold
        return float(np.mean(ground))

    pre_correction = np.asarray(
        [ground_fraction(reset_I[k], reset_Q[k]) for k in range(reset_I.shape[0])]
    )
    warnings = []
    final_fraction = float("nan")
    converged = None
    if post_reset_I is not None and post_reset_Q is not None:
        final_fraction = ground_fraction(post_reset_I, post_reset_Q)
        converged = bool(final_fraction > 0.9)
        if not converged:
            warnings.append(
                f"post-reset ground fraction {final_fraction:.3f} <= 0.9: "
                "active reset did not establish reliable initialization"
            )
    else:
        warnings.append(
            "no post-reset verification readout was saved; the final "
            "corrective flip cannot be validated from ModifiedRamsey reset "
            "buffers. Use mActiveResetVerify before trusting initialization"
        )

    return {
        "g_fraction": pre_correction,
        "pre_correction_g_fraction": pre_correction,
        "validated_after_reset_g_fraction": pre_correction[1:],
        "final_ground_fraction": final_fraction,
        "n_cycles": int(reset_I.shape[0]),
        "n_shots": int(reset_I.shape[1]),
        "n_resets_observed": max(0, int(reset_I.shape[0]) - 1),
        "converged": converged,
        "warnings": warnings,
    }


# Control verdict thresholds (docs/experiments/modified_ramsey.md#analysis, step 9).
ECHO_NULL_MAX_LAG_COV_RATIO = 0.25  # one-sided 95% upper bound, echo vs parity
DRIVE_OFF_MAX_CORRELATION_RATIO = 0.1  # drive_off vs parity: carryover / readout correlation
FLIP_MIN_OCCUPANCY_IMBALANCE = 0.15  # |occ1_main - 0.5| needed for the inversion to be visible
FLIP_MAX_INVERSION_ERROR = 0.15  # |occ1_flip - (1 - occ1_main)|
FLIP_RATE_AGREEMENT_SIGMA = 3.0  # |gamma_eff_flip - gamma_eff_main| / combined 1-sigma error
FLIP_RATE_MAX_RATIO = 2.0  # tolerated flip/main rate ratio (drift between records)
_HMM_IID_REASON_KEY = "uncorrelated (i.i.d.)"


def lagged_autocovariance_sum(
    v,
    max_lag,
    n_boot=1000,
    seed=0,
    blocks_per_lag=10,
    min_blocks=20,
    max_blocks=2000,
    baseline_lags=None,
    drift_window=None,
):
    """
    Model-free correlation statistic of a uniformly sampled trace with a block-bootstrap CI.

    S = sum_{k=1..K} C(k), the autocovariance of the mean-subtracted trace summed over
    lags 1..K (lag 0, the readout-noise variance, is excluded). It is the mean of the
    lagged-product series w_t = x_t * (x_{t+1} + ... + x_{t+K}). The CI resamples
    non-overlapping blocks of w with replacement: block length
    max(blocks_per_lag * K, 2 * span, len(w) // max_blocks), capped at
    len(w) // min_blocks and at least 2K, where span is the largest lag used
    (max_blocks bounds the bootstrap memory on long records). No telegraph model is
    assumed: any shot-to-shot correlation within K samples (parity switching, T1
    carryover, correlated readout) contributes, uncorrelated shots of any P(e) give
    S ~ 0.

    Drift-corrected traces. Subtracting a centred rolling mean of W samples puts a
    flat offset on every lag 0 < k < W/2: C(k) -> C(k) - P/W * (1 + k/W), with P the
    record's total autocovariance sum over all lags (the trace variance for i.i.d.
    shots). Summed over lags 1..K that is about -P * K / W, as large as a weak parity
    record's own lag sum. Pass only the interior (drop W//2 samples at each end, where
    a mode="nearest" edge repeats the end samples and biases S upward) and give
    baseline_lags=(L1, L2), a lag band with K < L1 <= L2 < W/2 where the correlation
    of interest has decayed, and drift_window=W: the offset is then measured in that
    band and removed, w_t -> w_t - c * x_t * (x_{t+L1} + ... + x_{t+L2}) with
    c = (K + K(K+1)/(2W)) / ((L2 - L1 + 1) * (1 + (L1 + L2)/(2W))), so the bootstrap
    carries the baseline noise too. Without drift_window the band is taken as flat.

    Returns dict: available, value (baseline-corrected when baseline_lags is given),
    uncorrected_value, baseline_offset (value - uncorrected_value), baseline_lags
    (None when not used), boot (n_boot replicates of S), max_lag, block_len, n_blocks,
    reason ("" when available).
    """
    out = {
        "available": False,
        "value": float("nan"),
        "uncorrected_value": float("nan"),
        "baseline_offset": 0.0,
        "baseline_lags": None,
        "boot": np.zeros(0),
        "max_lag": int(max_lag),
        "block_len": 0,
        "n_blocks": 0,
        "reason": "",
    }
    x = np.ravel(np.asarray(v, dtype=float))
    k = int(max_lag)
    if k < 1:
        raise ValueError("max_lag must be >= 1")
    span = k
    if baseline_lags is not None:
        l1, l2 = (int(b) for b in baseline_lags)
        if not k < l1 <= l2:
            raise ValueError("baseline_lags must satisfy max_lag < L1 <= L2")
        if drift_window is not None and not 2 * l2 < int(drift_window):
            raise ValueError("baseline_lags must lie below half the drift window")
        span = l2
        out["baseline_lags"] = [l1, l2]
    n_w = x.size - span
    block_len = (
        min(max(blocks_per_lag * k, 2 * span, n_w // max_blocks), n_w // min_blocks)
        if n_w > 0
        else 0
    )
    if block_len < 2 * k:
        out["reason"] = (
            f"record of {x.size} samples too short for {min_blocks} blocks of >= {2 * k} "
            f"samples at max_lag {k}" + (f" (baseline to lag {span})" if span > k else "")
        )
        return out
    x = x - x.mean()
    cs = np.concatenate([[0.0], np.cumsum(x)])
    w_raw = x[:n_w] * (cs[k + 1 : k + 1 + n_w] - cs[1 : 1 + n_w])
    w = w_raw
    if baseline_lags is not None:
        width = l2 - l1 + 1
        if drift_window:
            dw = float(drift_window)
            scale = (k + k * (k + 1) / (2.0 * dw)) / (width * (1.0 + (l1 + l2) / (2.0 * dw)))
        else:
            scale = k / width
        w = w_raw - scale * x[:n_w] * (cs[l2 + 1 : l2 + 1 + n_w] - cs[l1 : l1 + n_w])
    n_blocks = n_w // block_len
    block_means = w[: n_blocks * block_len].reshape(n_blocks, block_len).mean(axis=1)
    rng = np.random.default_rng(seed)
    boot = block_means[rng.integers(0, n_blocks, size=(int(n_boot), n_blocks))].mean(axis=1)
    value, raw = float(w.mean()), float(w_raw.mean())
    out.update(
        available=True,
        value=value,
        uncorrected_value=raw,
        baseline_offset=value - raw,
        boot=boot,
        block_len=int(block_len),
        n_blocks=int(n_blocks),
    )
    return out


def drift_corrected_lag_sum(v_corr, window_samples, max_lag, seed=0, n_boot=1000):
    """
    lagged_autocovariance_sum of a trace corrected by remove_slow_drift (rolling mean of
    window_samples W; W <= 1 or W >= len means no time-dependent correction).

    Two artefacts of the rolling mean are removed. (1) Its mode="nearest" edges repeat
    the first and last sample over half a window, leaking a common ramp into those
    shots (a positive bias for an uncorrelated record): only the interior
    v_corr[W//2 : N - W//2] is used ("edge_trim_samples" = W//2), or the full trace
    when the interior is too short ("edge_trim_samples" = 0). (2) The flat offset
    -P/W per lag (about -var * K / W summed over lags 1..K, comparable to a weak parity
    record's own lag sum) is measured in the baseline band of lags 4K..min(8K, W/2 - 1)
    and removed (lagged_autocovariance_sum baseline_lags / drift_window); without room
    for a band of at least K lags, "baseline_lags" is None and the offset stays.
    """
    v_corr = np.ravel(np.asarray(v_corr, dtype=float))
    k = int(max_lag)
    w = int(window_samples)
    detrended = 1 < w < v_corr.size
    half = w // 2 if detrended else 0
    baseline = None
    if detrended:
        l1, l2 = 4 * k, min(8 * k, (w - 1) // 2)
        if l2 >= l1 + k:
            baseline = (l1, l2)
    # Preference: interior with baseline, interior without, then the full trace.
    candidates = []
    for trim in (half, 0) if half else (0,):
        for band in (baseline, None) if baseline else (None,):
            candidates.append((v_corr[trim : v_corr.size - trim], trim, band))
    for trace, trim, band in candidates:
        lag_sum = lagged_autocovariance_sum(
            trace,
            k,
            n_boot=n_boot,
            seed=seed,
            baseline_lags=band,
            drift_window=w if band else None,
        )
        if lag_sum["available"]:
            break
    lag_sum["edge_trim_samples"] = trim
    return lag_sum


def _lag_cov_ratio(ctl, main):
    """Control/parity ratio of lagged_autocovariance_sum with one-sided 95% / 5% bounds.

    "computed" is True when both records carry an available statistic, even if no ratio
    could be formed (parity lag sum not significantly > 0, or different max_lag).
    """
    c = (ctl.get("acf") or {}).get("lag_covariance_sum") or {}
    m = (main.get("acf") or {}).get("lag_covariance_sum") or {}
    out = {
        "ratio": float("nan"),
        "upper95": float("nan"),
        "lower05": float("nan"),
        "reason": "",
        "computed": bool(c.get("available") and m.get("available")),
    }
    if not out["computed"]:
        out["reason"] = "lag-covariance statistic unavailable: " + (
            c.get("reason") or m.get("reason") or "not computed (non-uniform timing?)"
        )
        return out
    if c["max_lag"] != m["max_lag"]:
        out["reason"] = f"lag-covariance max_lag differs ({c['max_lag']} vs {m['max_lag']})"
        return out
    m_boot = np.asarray(m["boot"], dtype=float)
    c_boot = np.asarray(c["boot"], dtype=float)
    n = min(m_boot.size, c_boot.size)
    if not (m["value"] > 0 and n and np.percentile(m_boot[:n], 5) > 0):
        out["reason"] = (
            "parity record shows no significant lag covariance to normalise by "
            "(weak contrast or short record: acquire more shots)"
        )
        return out
    # The records are independent; reverse one replicate list so equal seeds do not
    # pair identical block draws.
    ratio_boot = c_boot[:n] / m_boot[:n][::-1]
    out["ratio"] = float(c["value"] / m["value"])
    out["upper95"] = float(np.percentile(ratio_boot, 95))
    out["lower05"] = float(np.percentile(ratio_boot, 5))
    return out


def _effective_rate(hmm):
    """(gamma01 + gamma10)/2 and its 1-sigma error; label-invariant, so it survives a flip."""
    g01, g10 = hmm.get("gamma01_hz", float("nan")), hmm.get("gamma10_hz", float("nan"))
    e01, e10 = hmm.get("gamma01_err_hz", float("nan")), hmm.get("gamma10_err_hz", float("nan"))
    g = 0.5 * (g01 + g10)
    err = e01 if hmm.get("symmetric") else 0.5 * math.hypot(e01, e10)
    return float(g), float(err)


def compare_parity_controls(main_result, control_results):
    """
    Sanity checks between the parity-sensing run and its controls.

    Parameters
    ----------
    main_result : dict
        {"label", "hmm": fit_two_state_hmm output, "acf": autocorrelation
        output, "occupancy_state1": float} for the parity-sensing run. The
        "acf" dict of analyze_modified_ramsey_record also carries
        "lag_covariance_sum" (lagged_autocovariance_sum of the corrected trace).
    control_results : list of dicts
        Same structure plus "control_type" in
        {"flip_final_pi2", "echo_null", "tau_offset", "drive_detuned",
         "drive_off"}.

    Each control gets checked=True (passed) / False (failed) / None (not
    decisive), a verdict string and a note. "lag_cov_ratio" is the control's
    summed lag-1..K autocovariance over the parity record's, and
    "lag_cov_ratio_upper95" / "lag_cov_ratio_lower05" its one-sided 95%
    block-bootstrap upper / lower bounds.

      flip_final_pi2 : the telegraph must SURVIVE (ACF amplitude ratio > 0.25)
                       at the SAME effective HMM rate (gamma01+gamma10)/2: it
                       fails only if the rates differ by more than
                       FLIP_RATE_AGREEMENT_SIGMA combined 1-sigma errors AND by
                       more than a factor FLIP_RATE_MAX_RATIO (rate drift
                       between the two records is tolerated up to that factor).
                       Without finite rate errors only the factor rule applies.
                       The occupancy inversion occ1_flip ~ 1 - occ1_main
                       (within 0.15) is tested only when |occ1_main - 0.5| >
                       0.15; for a balanced parity record any balanced flip
                       record would "invert", so the verdict is then
                       "inversion uninformative" (checked=None) unless
                       survival or the rate check failed.
      echo_null      : the telegraph must be SUPPRESSED: the control HMM is
                       unidentifiable by its i.i.d. gate, OR
                       lag_cov_ratio_upper95 < 0.25. The model-free statistic
                       vetoes the HMM: when the lag ratio's 5% lower bound is
                       >= 0.25 the echo fails. The HMM's resolved-rate gate is
                       not null evidence (a partially refocused echo, fitted
                       with the parity mapping, can lock onto a fast rate),
                       and neither is an ACF fit failure (it also happens for
                       non-uniform timing). A control dict carrying
                       null_control_valid=False (build_control_variants: the
                       predicted echo keeps > 0.2x the parity contrast) is not
                       decisive: verdict "not a null at these settings".
      tau_offset     : judged as echo_null when its control dict carries
                       null_control_valid=True (build_control_variants: its
                       default tau, the even harmonic (k+1)/(2 df) or in the
                       symmetric scheme the solved zero just below it, is a
                       predicted null); otherwise informational.
      drive_detuned  : +df adds a common phase k*pi: an INVERTED mapping at
                       about full contrast, not a null. Judged as
                       flip_final_pi2 when its control dict carries
                       inverted_mapping_expected=True (predicted contrast <=
                       -0.8x the parity run's and, with active reset, the
                       reset pi at the detuned drive predicted to flip each
                       branch with >= 0.95); otherwise informational, with
                       its inverted_mapping_reason in the note.
      drive_off      : no pi/2 pulses, so no parity information: its
                       correlation must be < 0.1 of the parity record's.
                       Passes when lag_cov_ratio_upper95 < 0.1; fails when
                       lag_cov_ratio_lower05 >= 0.1 (inter-shot carryover /
                       readout correlation contaminates the parity record);
                       otherwise "inconclusive" (checked=None: the interval
                       straddles 0.1, acquire more shots). When both records
                       carry the lag statistic but no ratio can be formed (the
                       parity record's own lag sum is not significantly > 0:
                       weak contrast or short record), also "inconclusive".
                       Only when the lag statistic is absent does the ACF
                       amplitude ratio decide, by its point value (< 0.1
                       passes, >= 0.1 fails; no CI, so a noisy record can fail
                       by chance); with neither, "inconclusive".

    Returns dict: {"controls": [...], "all_expected": bool, "null_control_valid":
    False if an echo_null was excluded as not a null else True (None without one),
    "decisive_controls": [...], "notes": [...]}. all_expected needs a valid parity
    record, at least one decisive check, and no failed one.
    """

    def amp(res):
        a = res.get("acf", {}).get("amplitude", float("nan"))
        return a if (a is not None and math.isfinite(a) and a > 0) else float("nan")

    def fmt(x):
        return f"{x:.2f}" if math.isfinite(x) else "nan"

    main_amp = amp(main_result)
    main_occ1 = float(main_result.get("occupancy_state1", float("nan")))
    main_hmm = main_result.get("hmm") or {}
    main_identifiable = bool(main_hmm.get("identifiable", False))
    main_valid = main_identifiable and math.isfinite(main_amp)
    entries = []
    all_ok = main_valid
    n_decisive_checks = 0
    decisive = []
    null_control_valid = None
    notes = []
    for ctl in control_results:
        ctype = ctl.get("control_type", "unknown")
        c_amp = amp(ctl)
        ratio = (
            c_amp / main_amp
            if (math.isfinite(c_amp) and math.isfinite(main_amp) and main_amp > 0)
            else float("nan")
        )
        lag = _lag_cov_ratio(ctl, main_result)
        entry = {
            "control_type": ctype,
            "label": ctl.get("label", ctype),
            "amplitude_ratio": ratio,
            "lag_cov_ratio": lag["ratio"],
            "lag_cov_ratio_upper95": lag["upper95"],
            "lag_cov_ratio_lower05": lag["lower05"],
            "checked": None,
            "verdict": "informational",
            "note": "",
        }
        lag_note = (
            f"lag-covariance ratio {fmt(lag['ratio'])} (95% upper {fmt(lag['upper95'])})"
            if math.isfinite(lag["upper95"])
            else lag["reason"]
        )
        if ctype == "flip_final_pi2" or (
            ctype == "drive_detuned" and ctl.get("inverted_mapping_expected") is True
        ):
            occ1 = float(ctl.get("occupancy_state1", float("nan")))
            survives = math.isfinite(ratio) and ratio > 0.25
            ctl_hmm = ctl.get("hmm") or {}
            g_main, e_main = _effective_rate(main_hmm)
            g_flip, e_flip = _effective_rate(ctl_hmm)
            combined = math.hypot(e_main, e_flip)
            # hmm.py can report identifiable rates with NaN errors (singular Hessian);
            # without errors the factor-of-FLIP_RATE_MAX_RATIO rule decides alone.
            errors_ok = math.isfinite(combined) and combined > 0
            rates_ok = (
                bool(ctl_hmm.get("identifiable", False))
                and math.isfinite(g_main)
                and math.isfinite(g_flip)
                and g_main > 0
                and g_flip > 0
            )
            rate_ok = rates_ok and (
                max(g_flip / g_main, g_main / g_flip) <= FLIP_RATE_MAX_RATIO
                or (errors_ok and abs(g_flip - g_main) <= FLIP_RATE_AGREEMENT_SIGMA * combined)
            )
            informative = (
                math.isfinite(main_occ1) and abs(main_occ1 - 0.5) > FLIP_MIN_OCCUPANCY_IMBALANCE
            )
            inverted = (
                informative
                and math.isfinite(occ1)
                and abs(occ1 - (1.0 - main_occ1)) < FLIP_MAX_INVERSION_ERROR
            )
            if not (main_valid and survives and rate_ok) or (informative and not inverted):
                entry["checked"], entry["verdict"] = False, "failed"
            elif informative:
                entry["checked"], entry["verdict"] = True, "passed"
            else:
                entry["verdict"] = "inversion uninformative"
            entry["note"] = (
                f"amplitude ratio {fmt(ratio)} (expect ~1); effective HMM rate "
                f"{fmt(g_flip)} vs main {fmt(g_main)} Hz (combined 1-sigma "
                f"{fmt(combined)}; expect equal within "
                + (
                    f"{FLIP_RATE_AGREEMENT_SIGMA:g} sigma or a factor {FLIP_RATE_MAX_RATIO:g}); "
                    if errors_ok
                    else f"a factor {FLIP_RATE_MAX_RATIO:g}: rate errors unavailable); "
                )
                + f"occupancy(state1) {fmt(occ1)} vs 1-main={fmt(1.0 - main_occ1)} "
                + (
                    "(expect equal)"
                    if informative
                    else f"(inversion uninformative: |occ1_main - 0.5| <= "
                    f"{FLIP_MIN_OCCUPANCY_IMBALANCE:g})"
                )
            )
        elif ctype == "echo_null" and ctl.get("null_control_valid") is False:
            # The predicted echo keeps parity contrast: neither a pass nor a failure means
            # anything (docs/experiments/modified_ramsey.md#echo-is-a-null-only-for-short-pulses).
            null_control_valid = False
            entry["verdict"] = "not a null at these settings"
            entry["note"] = (
                (ctl.get("null_invalid_reason") or "predicted residual contrast too large")
                + f"; excluded from the decisive checks ({lag_note}; amplitude ratio "
                + f"{fmt(ratio)}, informational)"
            )
        elif ctype == "echo_null" or (
            ctype == "tau_offset" and ctl.get("null_control_valid") is True
        ):
            if ctype == "echo_null" and null_control_valid is None:
                null_control_valid = True
            ctl_hmm = ctl.get("hmm") or {}
            hmm_null = not ctl_hmm.get("identifiable", False) and any(
                _HMM_IID_REASON_KEY in reason
                for reason in ctl_hmm.get("unidentifiable_reasons", [])
            )
            lag_null = (
                math.isfinite(lag["upper95"]) and lag["upper95"] < ECHO_NULL_MAX_LAG_COV_RATIO
            )
            # Significant surviving correlation overrides the HMM's i.i.d. verdict.
            lag_veto = (
                math.isfinite(lag["lower05"]) and lag["lower05"] >= ECHO_NULL_MAX_LAG_COV_RATIO
            )
            ok = main_valid and (hmm_null or lag_null) and not lag_veto
            entry["checked"] = bool(ok)
            entry["verdict"] = "passed" if ok else "failed"
            entry["note"] = (
                f"HMM null (i.i.d. gate) {hmm_null}; {lag_note} "
                f"(expect < {ECHO_NULL_MAX_LAG_COV_RATIO:g}: "
                + (
                    "echo refocuses the static parity detuning)"
                    if ctype == "echo_null"
                    else "predicted-null tau (the even harmonic, or in the symmetric scheme "
                    "the solved zero just below it) returns both branches to the same state)"
                )
                + (
                    f"; 5% lower bound {fmt(lag['lower05'])} >= "
                    f"{ECHO_NULL_MAX_LAG_COV_RATIO:g}: the telegraph survived the "
                    + ("echo" if ctype == "echo_null" else "predicted-null tau")
                    if lag_veto
                    else ""
                )
                + f"; amplitude ratio {fmt(ratio)}"
            )
        elif ctype == "drive_off":
            thr = DRIVE_OFF_MAX_CORRELATION_RATIO
            if math.isfinite(lag["upper95"]):
                measure = (
                    f"lag-covariance ratio {fmt(lag['ratio'])} (5% lower "
                    f"{fmt(lag['lower05'])}, 95% upper {fmt(lag['upper95'])})"
                )
                # Symmetric: decisive only when the CI clears the threshold either way.
                passed = lag["upper95"] < thr
                failed = math.isfinite(lag["lower05"]) and lag["lower05"] >= thr
            elif lag["computed"]:
                # Both records carry the statistic but no ratio can be formed (e.g. the
                # parity record's own lag sum is not significant): the ACF amplitude of
                # such a weak record is fitted noise, so it does not decide either.
                measure = "lag-covariance ratio not formed"
                passed = failed = False
            else:
                measure = f"ACF amplitude ratio {fmt(ratio)}"
                passed = math.isfinite(ratio) and ratio < thr
                failed = math.isfinite(ratio) and ratio >= thr
            if main_valid and passed:
                entry["checked"], entry["verdict"] = True, "passed"
                tail = ""
            elif failed or not main_valid:
                entry["checked"], entry["verdict"] = False, "failed"
                if not failed:
                    tail = ": parity record not valid"
                else:
                    tail = ": inter-shot carryover / readout correlation contaminates the parity record"
            else:
                entry["verdict"] = "inconclusive"
                if math.isfinite(lag["upper95"]):
                    tail = (
                        f": 90% interval [{fmt(lag['lower05'])}, {fmt(lag['upper95'])}] "
                        f"straddles {thr:g}; acquire more shots"
                    )
                elif lag["computed"]:
                    tail = f": {lag['reason']}"
                else:
                    tail = f": no correlation evidence available ({lag['reason']})"
            entry["note"] = f"{measure} (expect < {thr:g})" + tail
        else:
            why = ""
            if ctype == "tau_offset" and ctl.get("null_control_valid") is False:
                why = (ctl.get("null_invalid_reason") or "not a null at these settings") + "; "
            elif ctype == "drive_detuned" and ctl.get("inverted_mapping_expected") is False:
                why = (
                    ctl.get("inverted_mapping_reason")
                    or "not predicted to invert the mapping at near-full contrast"
                ) + "; "
            entry["note"] = f"{why}amplitude ratio {fmt(ratio)}; {lag_note}"
        if entry["checked"] is not None:
            n_decisive_checks += 1
            decisive.append(entry["label"])
        if entry["checked"] is False:
            all_ok = False
        entries.append(entry)
    if null_control_valid is False:
        notes.append(
            "echo_null is not a null at these settings and was excluded from the decisive "
            "checks; remaining decisive checks: " + (", ".join(decisive) or "none")
        )
    return {
        "controls": entries,
        "all_expected": bool(all_ok and n_decisive_checks > 0),
        "null_control_valid": null_control_valid,
        "decisive_controls": decisive,
        "notes": notes,
    }


def assess_parity_record(
    calibration=None,
    hmm=None,
    acf=None,
    psd=None,
    drift=None,
    reset=None,
    estimator_agreement_factor=3.0,
):
    """
    Aggregate quality gates into a warnings list. Never upgrades a result --
    only flags reasons NOT to over-interpret it.
    """
    warnings = []
    for src in (calibration, hmm, acf, psd, drift, reset):
        if src:
            warnings.extend(src.get("warnings", []))
    if hmm and hmm.get("identifiable"):
        rates = [hmm.get("gamma01_hz"), hmm.get("gamma10_hz")]
        alt = []
        for est, name in ((acf, "autocorrelation"), (psd, "PSD")):
            if est and est.get("fit_ok") and math.isfinite(est.get("gamma_hz", float("nan"))):
                alt.append((name, est["gamma_hz"]))
        g_eff = 0.0
        if all(r and math.isfinite(r) and r > 0 for r in rates):
            # For asymmetric rates the ACF/PSD see gamma_eff = (g01+g10)/2.
            g_eff = 0.5 * (rates[0] + rates[1])
        for name, g_alt in alt:
            if g_eff > 0 and (
                g_alt / g_eff > estimator_agreement_factor
                or g_eff / g_alt > estimator_agreement_factor
            ):
                warnings.append(
                    f"HMM effective rate {g_eff:.1f} Hz and {name} rate "
                    f"{g_alt:.1f} Hz disagree by more than "
                    f"{estimator_agreement_factor:g}x: at least one estimator "
                    "is not measuring parity switching"
                )
    return {"warnings": warnings, "clean": not warnings}


def _plot_projected_trace(t_s, v, v_corr, drift, out_path, max_pts=200_000):
    stride = max(1, v.size // max_pts)
    fig, axes = plt.subplots(2, 1, figsize=(11, 5), sharex=True)
    axes[0].plot(t_s[::stride], v[::stride], lw=0.4, label="projected v(t)")
    if drift is not None:
        axes[0].plot(t_s[::stride], drift[::stride], "r-", lw=1.2, label="drift estimate")
    axes[0].set_ylabel("v (raw units)")
    axes[0].legend(loc="best")
    axes[1].plot(t_s[::stride], v_corr[::stride], lw=0.4, color="C2")
    axes[1].set_ylabel("v corrected")
    axes[1].set_xlabel("time (s)")
    fig.suptitle("Projected analog parity trace")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _plot_hmm(t_s, v, hmm, out_path, max_pts=200_000):
    stride = max(1, v.size // max_pts)
    fig, axes = plt.subplots(3, 1, figsize=(11, 7), sharex=True)
    axes[0].plot(t_s[::stride], v[::stride], lw=0.4)
    # Reference levels for the two PARITY states. Two emission models reach
    # here and they do not share key names: the plain Gaussian model carries
    # mu0/mu1 directly, while the ge_mixture model (which is what
    # analyze_modified_ramsey_record always builds) carries the calibrated
    # readout clouds mu_g/mu_e plus per-state excited-state probabilities. For
    # the mixture, the level a parity state actually emits at is the
    # probability-weighted mean of the two clouds, not either cloud itself.
    em = hmm["emissions_used"]
    if em.get("model") == "ge_mixture":
        mu_g, mu_e = em["mu_g"], em["mu_e"]
        state_means = (
            (1.0 - em["p_e_state0"]) * mu_g + em["p_e_state0"] * mu_e,
            (1.0 - em["p_e_state1"]) * mu_g + em["p_e_state1"] * mu_e,
        )
        # the underlying g/e clouds, for context
        for mu, lbl in ((mu_g, "readout |g>"), (mu_e, "readout |e>")):
            axes[0].axhline(mu, color="0.6", ls=":", lw=0.8, label=lbl)
        axes[0].legend(loc="best", fontsize="x-small")
    else:
        state_means = (em["mu0"], em["mu1"])
    for mu, c in zip(state_means, ("C0", "C1")):
        axes[0].axhline(mu, color=c, ls="--", lw=1)
    axes[0].set_ylabel("v")
    if hmm["posteriors"] is not None:
        axes[1].plot(t_s[::stride], hmm["posteriors"][::stride, 1], lw=0.5)
        axes[1].set_ylim(-0.05, 1.05)
    axes[1].set_ylabel("P(state1 | data)")
    if hmm["viterbi_path"] is not None:
        axes[2].step(t_s[::stride], hmm["viterbi_path"][::stride], where="post", lw=0.6)
        axes[2].set_ylim(-0.1, 1.1)
    axes[2].set_ylabel("Viterbi state")
    axes[2].set_xlabel("time (s)")
    title = "2-state HMM"
    if hmm["identifiable"]:
        title += f": g01={hmm['gamma01_hz']:.1f} Hz, g10={hmm['gamma10_hz']:.1f} Hz"
    else:
        title += ": UNIDENTIFIABLE (rates withheld)"
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _plot_acf_psd(acf_out, psd_out, out_path):
    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(11, 4))
    if acf_out["acf"].size:
        ax0.plot(acf_out["lags_s"] * 1e3, acf_out["acf"], ".-", ms=3)
        if acf_out["fit_ok"]:
            lags = acf_out["lags_s"]
            c0_amp = acf_out["amplitude"] / (
                acf_out["amplitude"] + max(acf_out["noise_variance"], 0.0)
            )
            ax0.plot(
                lags * 1e3,
                c0_amp * np.exp(-lags / acf_out["tau_corr_s"]),
                "r-",
                label=(
                    f"tau_corr={acf_out['tau_corr_s'] * 1e3:.2f} ms -> "
                    f"gamma={acf_out['gamma_hz']:.1f} Hz"
                ),
            )
            ax0.legend()
    ax0.set_xlabel("lag (ms)")
    ax0.set_ylabel("normalized ACF")
    ax0.set_title("Autocorrelation")
    if psd_out["freqs_hz"].size:
        ax1.loglog(psd_out["freqs_hz"], psd_out["psd"], lw=0.7)
        if psd_out["fit_ok"]:
            f = psd_out["freqs_hz"]
            fit = psd_out["s0"] / (1 + (f / psd_out["f_corner_hz"]) ** 2) + psd_out["white_floor"]
            ax1.loglog(
                f,
                fit,
                "r-",
                label=(
                    f"f_c={psd_out['f_corner_hz']:.1f} Hz -> gamma={psd_out['gamma_hz']:.1f} Hz"
                ),
            )
            ax1.legend()
    ax1.set_xlabel("frequency (Hz)")
    ax1.set_ylabel("PSD")
    ax1.set_title("Welch PSD")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _plot_calibration(calibration, out_path):
    fig, ax = plt.subplots(figsize=(6, 6))
    for c, cov, lbl, col in (
        (calibration["g_center"], calibration["cov_g"], "g", "C0"),
        (calibration["e_center"], calibration["cov_e"], "e", "C1"),
    ):
        ax.plot(*c, "x", color=col, ms=12, mew=3, label=f"|{lbl}> center")
        # 1-sigma covariance ellipse
        w, vecs = np.linalg.eigh(cov)
        th = np.linspace(0, 2 * np.pi, 100)
        ell = vecs @ (np.sqrt(np.maximum(w, 0))[:, None] * np.vstack([np.cos(th), np.sin(th)]))
        ax.plot(c[0] + ell[0], c[1] + ell[1], color=col, lw=1)
    mid = calibration["midpoint"]
    axv = calibration["axis"]
    span = calibration["separation"]
    ax.plot(
        [mid[0] - axv[0] * span, mid[0] + axv[0] * span],
        [mid[1] - axv[1] * span, mid[1] + axv[1] * span],
        "k--",
        lw=1,
        label="projection axis",
    )
    ax.set_xlabel("I")
    ax.set_ylabel("Q")
    ax.axis("equal")
    ax.legend()
    ax.set_title(
        f"Readout calibration: SNR={calibration['snr_analog']:.2f}, "
        f"contrast={calibration['contrast']:.3f},\n"
        f"F_assign=(1+C)/2={calibration['assignment_fidelity']:.3f}"
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _plot_rate_vs_bin(rvb, out_path):
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.semilogx(rvb["bin_us"], rvb["rate_hz"], "o-")
    ax.set_xlabel("bin size (us)")
    ax.set_ylabel("threshold switch rate (Hz)")
    ax.set_title("Rate stability vs visualization bin size")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _plot_dwells(hmm, out_path):
    if hmm["viterbi_path"] is None:
        return
    path = hmm["viterbi_path"]
    t_us = np.arange(path.size, dtype=float)  # unit spacing; scaled below
    stats = dwell_time_statistics(path, t_us)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, dw, lbl in (
        (axes[0], stats["dwell_0_us"], "state0"),
        (axes[1], stats["dwell_1_us"], "state1"),
    ):
        if dw.size:
            ax.hist(dw, bins=min(30, max(5, dw.size // 5)), log=True)
        ax.set_xlabel("dwell (samples)")
        ax.set_title(f"{lbl} dwells (Viterbi)")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


# clean_cloud_source values whose separation is that of the true g/e clouds: the labelled
# mixture fit, and the unlabelled record fit (calibrate_readout_from_record)
TRUE_STATE_SEPARATION_SOURCES = ("mixture", "record_mixture")


def true_state_separation(calibration):
    """(separation, source) of a readout calibration: |mu_e - mu_g| of the TRUE g/e clouds
    when they are known, else the raw labelled-set separation.

    The raw ``separation`` is the distance between the labelled sets' means; the pi-prepared
    set is a g/e mixture when the SingleShot pi pulse is imperfect (e.g. detuned from the
    parity branches at the MR bias), so it is shrunk by the e-cloud purity. When the joint
    mixture fit is resolved (clean_cloud_source == "mixture") the clean cloud means are the
    true-state means and their distance is returned; a "record_mixture" calibration's
    clouds are fitted components, so its separation is returned as is. A trace's lagged
    covariance divided by this squared is then the lagged covariance of the excited-state
    indicator, independent of the SingleShot's prep error.

    Otherwise (source "moments": the mixture did not raise the likelihood enough, which is
    the usual outcome at analog SNR <~ 1.5 even at a purity of 0.7; or "moments_fallback")
    the raw separation is returned. It is NOT the true-state one: it is still shrunk by the
    purity p, which is simply not measurable from these shots. A lagged covariance divided
    by it is then inflated by 1/p^2. Callers that compare biases must not treat it as
    prep-independent (null_lag_covariance_vs_mr flags it).
    """
    source = calibration.get("clean_cloud_source", "moments")
    if source == "mixture":
        sep = abs(float(calibration["proj_e_mean_clean"]) - float(calibration["proj_g_mean_clean"]))
    else:
        sep = float(calibration.get("separation", float("nan")))
    return sep, source


def _json_default(x):
    if isinstance(x, np.ndarray):
        return x.tolist()
    if isinstance(x, (np.floating, np.integer)):
        return x.item()
    if isinstance(x, (np.bool_,)):
        return bool(x)
    return str(x)


def analyze_modified_ramsey_record(
    I,
    Q,
    dt_s,
    calibration,
    drift_timescale_s=0.2,
    expected_dwell_s=2.5e-3,
    symmetric_hmm=True,
    n_boot=0,
    seed=0,
    mapping_probabilities=(0.1, 0.9),
    mapping_probabilities_calibrated=False,
    fit_mapping=True,
    mapping_seed_source=None,
    clean_readout_clouds=None,
    reset_I=None,
    reset_Q=None,
    out_dir=None,
    base_name="mr_parity",
    save_plots=True,
    save_sidecars=True,
    hmm_kwargs=None,
    readout_prep_e_predicted=None,
):
    """
    End-to-end offline analysis of one Modified-Ramsey parity record.

    Parameters
    ----------
    I, Q          : (N,) unthresholded per-shot IQ (final Ramsey readout).
    dt_s          : float or (N-1,) array, ACTUAL per-shot interval(s) in
                    seconds (use the scheduled rep period from the saved
                    timing, and per-step gaps where the record has them).
    calibration   : output of calibrate_readout_from_labeled_shots.
    drift_timescale_s : rolling drift window; default 0.2 s = 80x a 2.5 ms
                    expected dwell.
    expected_dwell_s  : expected parity dwell (2-3 ms on BFC devices).
    symmetric_hmm : fit a single symmetric rate by default (charge parity has
                    no preferred branch); set False for asymmetric rates.
    mapping_probabilities : P(e|state0), P(e|state1) for the Ramsey mapping:
                    the seed of the fit with fit_mapping=True (its order fixes
                    the neutral labels: state1 is the state seeded with the
                    larger P(e)), the fixed values otherwise. Fixed values must
                    come from a device-specific mapping calibration; g/e readout
                    fidelity alone is not sufficient.
    mapping_probabilities_calibrated : whether that independent calibration was
                    performed; False with fit_mapping=False adds an explicit
                    quality warning.
    fit_mapping   : fit the two mapping probabilities jointly with the rate(s)
                    (fit_two_state_hmm fit_mapping, the readout clouds fixed at
                    the calibration). A wrong fixed mapping biases the rate; the
                    emission-SNR gate is then evaluated at the fitted mapping.
                    hmm_kwargs["fit_mapping"] overrides it.
    mapping_seed_source : where mapping_probabilities came from (e.g.
                    "predicted", "fallback: <why>", "calibrated"); recorded
                    as summary["mapping_seed_source"], None if not given.
    clean_readout_clouds : build the ge_mixture emissions from the calibration's
                    clean clouds (proj_*_clean: the labelled-shot mixture fit
                    that removes the g shots of an imperfect pi pulse from the
                    e cloud) instead of the raw moments. None (default): clean
                    when the mapping is fitted or calibrated, raw when it is a
                    fixed assumption (the clean clouds raise the emission SNR
                    that gates the HMM; an explicit True with an assumed fixed
                    mapping warns). Recorded as summary["readout_clouds"].
    reset_I/Q     : optional (n_cycles, N) reset readouts for initialization
                    validation.
    out_dir/base_name/save_plots/save_sidecars : output control.
    hmm_kwargs    : extra kwargs forwarded to fit_two_state_hmm.
    readout_prep_e_predicted : the predicted e purity of the calibration's
                    pi-prepared set (ideal two-level, the pi's detuning from the
                    record's branches), or None if unknown. Stored in the
                    _analysis.json sidecar only, so a later comparison can tell
                    how much a raw ("moments") readout_separation is shrunk.

    Returns dict with sub-results: calibration, drift, hmm, acf, psd,
    rate_vs_bin, reset, assessment, plus scalar summary fields. acf also
    carries "lag_covariance_sum" (drift_corrected_lag_sum of the corrected
    trace, lags 1..ceil(expected_dwell_s/dt): the interior half a drift window
    away from either end, "edge_trim_samples" recording the trim, 0 when the
    full trace had to be used; the rolling mean's flat per-lag offset removed
    via the baseline band "baseline_lags"), the model-free statistic that
    compare_parity_controls uses.
    """
    I = np.ravel(np.asarray(I, dtype=float))
    Q = np.ravel(np.asarray(Q, dtype=float))
    if I.size != Q.size:
        raise ValueError("I and Q must have the same length")
    original_n = I.size
    finite = np.isfinite(I) & np.isfinite(Q)
    if np.count_nonzero(finite) < 10:
        raise ValueError("fewer than 10 jointly finite IQ samples remain")

    if np.isscalar(dt_s):
        dt_value = float(dt_s)
        if not math.isfinite(dt_value) or dt_value <= 0:
            raise ValueError("dt_s must be finite and positive")
        full_t = np.arange(original_n, dtype=float) * dt_value
    else:
        raw_steps = np.ravel(np.asarray(dt_s, dtype=float))
        if raw_steps.size != original_n - 1:
            raise ValueError("dt_s array must have length original_N-1")
        if np.any(~np.isfinite(raw_steps)) or np.any(raw_steps <= 0):
            raise ValueError("all dt steps must be finite and positive")
        full_t = np.concatenate([[0.0], np.cumsum(raw_steps)])

    I, Q = I[finite], Q[finite]
    t_s = full_t[finite]
    dt_steps = np.diff(t_s)
    dt_nominal = float(np.median(dt_steps))
    removed = int(original_n - I.size)
    v = project_iq_trace(I, Q, calibration)

    uniform_timing = bool(
        np.allclose(dt_steps, dt_nominal, rtol=1e-6, atol=max(1e-15, dt_nominal * 1e-9))
    )
    if uniform_timing:
        drift = remove_slow_drift(
            v, dt_nominal, drift_timescale_s, expected_dwell_s=expected_dwell_s
        )
    else:
        warning = (
            "nonuniform timing/gaps detected: drift filtering, "
            "autocorrelation, PSD, and bin-size estimates were skipped; "
            "the HMM alone uses exact per-step timing"
        )
        drift = {
            "v_original": v.copy(),
            "v_corrected": v.copy(),
            "drift": np.zeros_like(v),
            "window_samples": 0,
            "drift_span": 0.0,
            "safe": False,
            "warnings": [warning],
        }
    if removed:
        drift["warnings"].append(
            f"removed {removed} non-finite IQ samples and carried their "
            "elapsed time into HMM dt steps"
        )
    v_corr = drift["v_corrected"]

    p0, p1 = map(float, mapping_probabilities)
    if not (0.0 <= p0 <= 1.0 and 0.0 <= p1 <= 1.0):
        raise ValueError("mapping probabilities must lie in [0, 1]")
    if p0 == p1:
        raise ValueError(
            "mapping probabilities must differ; identical probabilities carry no parity information"
        )
    fit_options = dict(hmm_kwargs or {})
    fit_options.setdefault("fit_mapping", bool(fit_mapping))
    if not mapping_probabilities_calibrated and not fit_options["fit_mapping"]:
        drift["warnings"].append(
            "Ramsey mapping probabilities are assumed rather than independently "
            "calibrated; fitted rates are conditional on those assumptions"
        )
    mapping_trusted = bool(fit_options["fit_mapping"] or mapping_probabilities_calibrated)
    use_clean = mapping_trusted if clean_readout_clouds is None else bool(clean_readout_clouds)
    cloud_keys = ("proj_g_mean", "proj_e_mean", "proj_g_sigma", "proj_e_sigma")
    readout_clouds = (
        "clean" if use_clean and all(k + "_clean" in calibration for k in cloud_keys) else "raw"
    )
    suffix = "_clean" if readout_clouds == "clean" else ""
    if readout_clouds == "clean" and not mapping_trusted:
        drift["warnings"].append(
            "clean readout clouds with an assumed fixed mapping: the emission SNR gate is "
            "evaluated with the corrected clouds but uncorrected mapping probabilities (the "
            "Ramsey pulses share the pi pulse's bandwidth loss); fit or calibrate the mapping"
        )
    emissions = {
        "model": "ge_mixture",
        "mu_g": calibration["proj_g_mean" + suffix],
        "mu_e": calibration["proj_e_mean" + suffix],
        "sigma_g": calibration["proj_g_sigma" + suffix],
        "sigma_e": calibration["proj_e_sigma" + suffix],
        "p_e_state0": p0,
        "p_e_state1": p1,
    }
    if expected_dwell_s and expected_dwell_s > 0:
        fit_options.setdefault("gamma_init_hz", 1.0 / expected_dwell_s)
    hmm = fit_two_state_hmm(
        v_corr,
        dt_steps,
        emissions,
        symmetric=symmetric_hmm,
        n_boot=n_boot,
        seed=seed,
        **fit_options,
    )

    if uniform_timing:
        acf = autocorrelation_rate_estimate(v_corr, dt_nominal)
        psd = psd_rate_estimate(v_corr, dt_nominal)
        rvb = rate_vs_bin_size(v_corr, dt_nominal, calibration["threshold"])
        # Model-free correlation for compare_parity_controls: lags up to one
        # expected dwell (same K for the parity record and its controls).
        max_lag = (
            max(1, math.ceil(expected_dwell_s / dt_nominal - 1e-9))
            if expected_dwell_s and expected_dwell_s > 0
            else 1
        )
        acf["lag_covariance_sum"] = drift_corrected_lag_sum(
            v_corr, int(drift.get("window_samples", 0)), max_lag, seed=seed
        )
    else:
        skipped = drift["warnings"][0]
        acf = {
            "tau_corr_s": float("nan"),
            "gamma_hz": float("nan"),
            "amplitude": float("nan"),
            "noise_variance": float("nan"),
            "acf": np.zeros(0),
            "lags_s": np.zeros(0),
            "fit_ok": False,
            "warnings": [skipped],
            "lag_covariance_sum": {
                "available": False,
                "value": float("nan"),
                "boot": np.zeros(0),
                "max_lag": 0,
                "block_len": 0,
                "n_blocks": 0,
                "reason": skipped,
            },
        }
        psd = {
            "f_corner_hz": float("nan"),
            "gamma_hz": float("nan"),
            "s0": float("nan"),
            "white_floor": float("nan"),
            "freqs_hz": np.zeros(0),
            "psd": np.zeros(0),
            "fit_ok": False,
            "warnings": [skipped],
        }
        rvb = {
            "bin_sizes": [],
            "bin_us": [],
            "rate_hz": [],
            "n_switches": [],
            "warnings": [skipped],
        }

    reset = None
    if reset_I is not None and reset_Q is not None and np.size(reset_I):
        reset_i = np.asarray(reset_I)
        reset_q = np.asarray(reset_Q)
        if reset_i.shape[-1] == original_n:
            reset_i, reset_q = reset_i[..., finite], reset_q[..., finite]
        reset = reset_success_vs_cycle(reset_i, reset_q, calibration)
    assessment = assess_parity_record(
        calibration=calibration, hmm=hmm, acf=acf, psd=psd, drift=drift, reset=reset
    )

    t_s = (
        np.concatenate([[0.0], np.cumsum(dt_steps)])
        if dt_steps is not None
        else np.arange(v.size) * dt_nominal
    )

    summary = {
        "n_samples": int(v.size),
        "n_samples_removed_nonfinite": removed,
        "uniform_timing": uniform_timing,
        "dt_nominal_s": dt_nominal,
        "record_duration_s": float(t_s[-1]) if v.size else 0.0,
        "emission_model": "ge_mixture",
        "mapping_p_e_state0": p0,
        "mapping_p_e_state1": p1,
        "mapping_probabilities_calibrated": bool(mapping_probabilities_calibrated),
        "mapping_seed_source": mapping_seed_source,
        "mapping_fitted": hmm["mapping_fitted"],
        "mapping_p_e_state0_fit": hmm["p_e_state0_fit"],
        "mapping_p_e_state1_fit": hmm["p_e_state1_fit"],
        "mapping_p_e_state0_err": hmm["p_e_state0_err"],
        "mapping_p_e_state1_err": hmm["p_e_state1_err"],
        "emission_snr": hmm["emission_snr"],
        "emission_snr_seed": hmm["emission_snr_seed"],
        "iid_p_e": hmm["iid_p_e"],
        "identifiable": hmm["identifiable"],
        "gamma01_hz": hmm["gamma01_hz"],
        "gamma10_hz": hmm["gamma10_hz"],
        "gamma01_err_hz": hmm["gamma01_err_hz"],
        "gamma10_err_hz": hmm["gamma10_err_hz"],
        "acf_gamma_hz": acf["gamma_hz"],
        "psd_gamma_hz": psd["gamma_hz"],
        "posterior_ambiguity": hmm["posterior_ambiguity"],
        "expected_transitions": hmm["expected_transitions"],
        "occupancy_state1": float(hmm["occupancy"][1])
        if np.all(np.isfinite(hmm["occupancy"]))
        else float("nan"),
        "readout_contrast": calibration["contrast"],
        "assignment_fidelity": calibration["assignment_fidelity"],
        "snr_analog": calibration["snr_analog"],
        "readout_clouds": readout_clouds,
        "snr_analog_clean": calibration.get("snr_analog_clean", float("nan")),
        "prep_fidelity_e": calibration.get("prep_fidelity_e", float("nan")),
        "prep_excited_g": calibration.get("prep_excited_g", float("nan")),
        "clean_cloud_source": calibration.get("clean_cloud_source"),
        "drift_span": drift["drift_span"],
        "drift_safe": drift["safe"],
        "reset_converged": (reset or {}).get("converged"),
        "warnings": assessment["warnings"],
    }

    if out_dir is not None and (save_plots or save_sidecars):
        os.makedirs(out_dir, exist_ok=True)
        base = os.path.join(out_dir, base_name)
        if save_plots:
            _plot_calibration(calibration, base + "_calibration.png")
            _plot_projected_trace(t_s, v, v_corr, drift["drift"], base + "_projected_trace.png")
            _plot_hmm(t_s, v_corr, hmm, base + "_hmm.png")
            _plot_acf_psd(acf, psd, base + "_acf_psd.png")
            _plot_rate_vs_bin(rvb, base + "_rate_vs_bin.png")
            _plot_dwells(hmm, base + "_dwells.png")
            if reset is not None:
                fig, ax = plt.subplots(figsize=(5, 4))
                ax.plot(np.arange(reset["n_cycles"]), reset["pre_correction_g_fraction"], "o-")
                ax.set_xlabel("pre-correction readout index")
                ax.set_ylabel("ground fraction before correction")
                ax.set_ylim(0, 1.02)
                ax.set_title("Active-reset pre-correction populations")
                fig.tight_layout()
                fig.savefig(base + "_reset_success.png", dpi=150)
                plt.close(fig)
        if save_sidecars:
            with open(base + "_analysis.json", "w") as fh:
                json.dump(
                    {
                        **summary,
                        "acf": {
                            k: acf[k]
                            for k in (
                                "tau_corr_s",
                                "gamma_hz",
                                "amplitude",
                                "noise_variance",
                                "fit_ok",
                            )
                        }
                        | {
                            # lag-1 autocorrelation and the drift-corrected lag-covariance
                            # sum (with its bootstrap), so a later record (the sweet-spot
                            # null) can be compared with this one
                            "r1": float(acf["acf"][1]) if np.size(acf["acf"]) > 1 else float("nan"),
                            "lag_covariance_sum": acf.get("lag_covariance_sum"),
                        },
                        # the true-state (clean-cloud) separation and its source, which
                        # normalises the lag-covariance sum (true_state_separation)
                        "readout_separation": true_state_separation(calibration)[0],
                        "readout_separation_source": true_state_separation(calibration)[1],
                        # how much a raw (non-mixture) readout_separation is shrunk
                        "readout_prep_e_predicted": readout_prep_e_predicted,
                        "psd": {
                            k: psd[k]
                            for k in ("f_corner_hz", "gamma_hz", "s0", "white_floor", "fit_ok")
                        },
                        "rate_vs_bin": rvb,
                        "gamma_boot_ci": hmm["gamma_boot_ci"],
                        "dwell_mean_s": hmm["dwell_mean_s"],
                        "reset_pre_correction_g_fraction": (reset or {}).get(
                            "pre_correction_g_fraction"
                        ),
                        "reset_validated_after_reset_g_fraction": (reset or {}).get(
                            "validated_after_reset_g_fraction"
                        ),
                        "reset_final_ground_fraction": (reset or {}).get("final_ground_fraction"),
                    },
                    fh,
                    indent=2,
                    default=_json_default,
                )
            try:
                import h5py

                with h5py.File(base + "_analysis.h5", "w") as fh:
                    fh.create_dataset("v_projected", data=v)
                    fh.create_dataset("v_corrected", data=v_corr)
                    fh.create_dataset("drift", data=drift["drift"])
                    fh.create_dataset("t_s", data=t_s)
                    if hmm["posteriors"] is not None:
                        fh.create_dataset("posterior_state1", data=hmm["posteriors"][:, 1])
                    if hmm["viterbi_path"] is not None:
                        fh.create_dataset("viterbi_path", data=hmm["viterbi_path"])
                    for k, val in summary.items():
                        if k == "warnings":
                            fh.attrs[k] = json.dumps(val)
                        elif val is None:
                            fh.attrs[k] = "None"
                        else:
                            fh.attrs[k] = val
            except ImportError:
                pass

    return {
        "summary": summary,
        "calibration": calibration,
        "drift": drift,
        "hmm": hmm,
        "acf": acf,
        "psd": psd,
        "rate_vs_bin": rvb,
        "reset": reset,
        "assessment": assessment,
        "v_projected": v,
        "v_corrected": v_corr,
        "t_s": t_s,
    }
