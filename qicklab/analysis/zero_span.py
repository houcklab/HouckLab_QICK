"""Offline zero-span parity analysis: classify_parity_trace, sliding_window_switch_rate,
event_switch_rate, detect_bursts, baseline_rate_and_bursts and the analyze_parity_run
pipeline (validation primitives: zero_span_checks).
Method: docs/experiments/zero_span_parity.md#analysis. Tests: tests/test_zero_span_analysis.py."""

import json
import os

import h5py
import matplotlib
import numpy as np

matplotlib.use("Agg")  # B1: stays until its own fix commit (design.md)
import matplotlib.pyplot as plt

from qicklab.analysis.dwell import _gap_segment_edges, dwell_time_statistics
from qicklab.analysis.hmm import fit_two_state_hmm
from qicklab.analysis.iq import project_iq_onto_separator
from qicklab.analysis.rates import autocorrelation_rate_us, psd_rate_estimate
from qicklab.analysis.undriven import two_gaussian_threshold
from qicklab.core.io import provenance


# classifier methods that use the SingleShot separator; "apriori" is the legacy name of
# "apriori_gmm" (docs/experiments/zero_span_parity.md#analysis)
SEPARATOR_METHODS = ("apriori_gmm", "apriori_midpoint", "apriori")


def _gmm_threshold_bits(scores):
    """Data-derived parity threshold on projected scores (method "apriori_gmm").

    Fits 1- and 2-component Gaussian mixtures to the scores (projected_histogram_snr) and,
    when the histogram passes its bimodality gate (delta BIC > 0, separation SNR > 1.5,
    both weights in (0.1, 0.9)), thresholds at the maximum-likelihood boundary of the two
    components (two_gaussian_threshold). Otherwise the bits are withheld (None) with a
    warning: a continuously driven qubit sits at g + p_e (e - g) with p_e <= 1/2, so no
    fixed point on the g/e axis (the SingleShot midpoint in particular) separates the
    parity branches.
    """
    from qicklab.analysis.zero_span_checks import projected_histogram_snr  # imports this module

    h = projected_histogram_snr(scores)
    thr = float("nan")
    if h["is_bimodal"]:
        thr = two_gaussian_threshold(h["centers"], h["sigmas"], h["weights"])
    if h["is_bimodal"] and np.isfinite(thr):
        return np.asarray(scores > thr, dtype=int), thr, h, None
    warning = (
        f"projected scores not bimodal (delta_bic={h['delta_bic']:.3g}, "
        f"separation_snr={h['separation_snr']:.3g}, weights={np.round(h['weights'], 3).tolist()}); "
        f"parity bits withheld"
    )
    return None, thr, h, warning


def _histogram_fit_summary(h):
    """Summary fields of the "apriori_gmm" score-histogram fit (NaN for other methods).

    Score units (midpoint-centred projection): an upper center at or above 0 sits at or
    above the SingleShot g/e midpoint, the resolved-qubit-jump signature.
    """
    nan = float("nan")
    if h is None:
        return {
            "classifier_separation_snr": nan,
            "classifier_delta_bic": nan,
            "classifier_centers": [nan, nan],
            "classifier_sigmas": [nan, nan],
            "classifier_weights": [nan, nan],
        }
    return {
        "classifier_separation_snr": float(h["separation_snr"]),
        "classifier_delta_bic": float(h["delta_bic"]),
        "classifier_centers": [float(x) for x in h["centers"]],
        "classifier_sigmas": [float(x) for x in h["sigmas"]],
        "classifier_weights": [float(x) for x in h["weights"]],
    }


def classify_parity_trace(I, Q, separator=None, method="apriori_gmm"):
    """
    Project (I, Q) samples onto a 2-state axis and return binary parity labels.

    Parameters
    ----------
    I, Q : array_like
        1-D arrays of equal length, the raw in-phase and quadrature samples.
    separator : dict or None
        For the separator methods ("apriori_gmm", "apriori_midpoint", legacy "apriori"):
        must contain "g_center" and "e_center", each a length-2 array-like (I, Q)
        coordinate from a prior single-shot calibration. Ignored if method="kmeans".
    method : {"apriori_gmm", "apriori_midpoint", "kmeans"} ("apriori" = "apriori_gmm")
        All project onto the g -> e axis about the g/e midpoint
        (scores = (iq - (g + e)/2) @ (e - g), project_iq_onto_separator); they differ in
        the threshold.
        "apriori_gmm" (default): the separator is only the projection axis; the threshold
        is the maximum-likelihood boundary of a 2-component Gaussian mixture fitted to
        the scores themselves, and the bits are None (withheld, with a warning) when the
        score histogram fails the bimodality gate of projected_histogram_snr.
        "apriori_midpoint": threshold at score 0, the SingleShot g/e midpoint. Wrong for
        driven zero-span data (the driven level sits at or below the midpoint, p_e <= 1/2);
        kept for scores-only callers and comparison.
        "kmeans": fit KMeans(n_clusters=2) on (I, Q); label 0 = cluster with
        the lower projection on the e-g (inter-centroid) axis, with a canonical
        axis sign so the remap is independent of KMeans' arbitrary centroid
        order and of the g/e separation direction (I, Q, or diagonal).

    Returns
    -------
    dict with keys:
      binary_states  : int array (N,), values 0 or 1; None when "apriori_gmm" withholds
      scores         : float array (N,), signed projection along separator axis
      separator_used : dict, the separator actually used (synthesized for kmeans)
      method         : "apriori_gmm", "apriori_midpoint" or "kmeans"
      threshold      : float, the score threshold (0.0 except for "apriori_gmm"; nan
                       when withheld)
      warning        : str or None, why the bits were withheld
      histogram_fit  : projected_histogram_snr output ("apriori_gmm" only)
    """
    if method in SEPARATOR_METHODS:
        if separator is None:
            raise ValueError(f"method={method!r} requires a separator dict")
        scores, bits = project_iq_onto_separator(I, Q, separator)
        out = {
            "binary_states": bits,
            "scores": scores,
            "separator_used": {
                "g_center": np.asarray(separator["g_center"], dtype=float),
                "e_center": np.asarray(separator["e_center"], dtype=float),
            },
            "method": "apriori_midpoint",
            "threshold": 0.0,
            "warning": None,
        }
        if method == "apriori_midpoint":
            return out
        bits, thr, h, warning = _gmm_threshold_bits(scores)
        out.update(
            {
                "binary_states": bits,
                "method": "apriori_gmm",
                "threshold": thr,
                "warning": warning,
                "histogram_fit": h,
            }
        )
        return out
    elif method == "kmeans":
        from sklearn.cluster import KMeans

        I = np.ravel(np.asarray(I, dtype=float))
        Q = np.ravel(np.asarray(Q, dtype=float))
        if I.size == 0:
            return {
                "binary_states": np.zeros(0, dtype=int),
                "scores": np.zeros(0, dtype=float),
                "separator_used": {
                    "g_center": np.array([0.0, 0.0]),
                    "e_center": np.array([0.0, 0.0]),
                },
                "method": "kmeans",
                "threshold": 0.0,
                "warning": None,
            }
        iq = np.column_stack([I, Q])
        km = KMeans(n_clusters=2, n_init=10, random_state=0).fit(iq)
        centers = km.cluster_centers_  # shape (2, 2)

        # Label 0 = lower projection on the inter-centroid axis. The axis sign is canonicalised to
        # its dominant +component: KMeans' centroid order is arbitrary, so the raw sign would
        # just echo it (docs/experiments/zero_span_parity.md#analysis).
        axis = centers[1] - centers[0]
        if abs(axis[0]) >= abs(axis[1]):
            if axis[0] < 0:
                axis = -axis
        else:
            if axis[1] < 0:
                axis = -axis
        proj = centers @ axis
        g_idx = int(np.argmin(proj))
        e_idx = 1 - g_idx
        g_center = centers[g_idx]
        e_center = centers[e_idx]
        synth_sep = {"g_center": g_center, "e_center": e_center}
        scores, bits = project_iq_onto_separator(I, Q, synth_sep)
        return {
            "binary_states": bits,
            "scores": scores,
            "separator_used": synth_sep,
            "method": "kmeans",
            "threshold": 0.0,
            "warning": None,
        }
    else:
        raise ValueError(f"Unknown method: {method!r}")


def _switch_events(bits, t, gap_indices=None):
    """
    Per-interval switch events of a binary trace (shared by the window and baseline rates).

    Returns (diffs, t_event, in_record), each of length N-1 for the N-1 sample
    intervals: diffs[i] = |bits[i+1] - bits[i]| (0 or 1), timestamped t_event[i] = t[i+1];
    in_record[i] is False for an interval that spans a `gap_indices` boundary, whose
    diff is forced to 0 so no spurious switch is counted across a gap.
    """
    diffs = np.abs(np.diff(bits))  # length N-1, value 0 or 1
    in_record = np.ones(diffs.size, dtype=bool)
    if gap_indices:
        for gi in gap_indices:
            if 1 <= gi < bits.size:
                diffs[gi - 1] = 0
                in_record[gi - 1] = False

    # diffs[i] corresponds to a transition that occurred between t[i] and t[i+1];
    # assign that switch event the timestamp t[i+1].
    t_event = t[1:]
    return diffs, t_event, in_record


def event_switch_rate(binary_states, t_us, gap_indices=None, exclude_us=()):
    """
    Switch rate in Hz from the raw switch events: n / T with a sqrt(n) standard error.

    n is the number of switches and T the observed time, the sum of the sample
    intervals t[i+1] - t[i] that do not span a `gap_indices` boundary (no uniform
    spacing is assumed). An interval whose event timestamp t[i+1] lies inside any
    closed [t_start_us, t_end_us] pair in `exclude_us` (e.g. a detected burst) is
    removed from both n and T, so the switches and the exposure stay matched.

    Returns
    -------
    dict with keys:
      rate_Hz      : n / T, or nan when T = 0 (fewer than 2 samples, or all excluded)
      rate_err_Hz  : sqrt(n) / T, the Gaussian (large-n) approximation to the Poisson
                     standard error; nan when T = 0. It is 0 when n = 0 and is not a
                     valid confidence interval for n of order 0-10 (at n = 0 the
                     one-sided 68 % upper limit is -ln(0.32) / T ~ 1.14 / T); use
                     n_switches and T_s for an exact Poisson interval there.
      n_switches   : int, n
      T_s          : float, T in seconds
    """
    bits = np.asarray(binary_states, dtype=int)
    t = np.asarray(t_us, dtype=float)
    if bits.shape != t.shape:
        raise ValueError(f"binary_states shape {bits.shape} != t_us shape {t.shape}")
    if bits.size < 2:
        return {"rate_Hz": float("nan"), "rate_err_Hz": float("nan"), "n_switches": 0, "T_s": 0.0}
    diffs, t_event, keep = _switch_events(bits, t, gap_indices)
    for t_start, t_end in exclude_us:
        keep &= ~((t_event >= t_start) & (t_event <= t_end))
    n = int(diffs[keep].sum())
    T_s = float(np.sum(np.diff(t)[keep])) * 1e-6
    if T_s <= 0:
        return {"rate_Hz": float("nan"), "rate_err_Hz": float("nan"), "n_switches": n, "T_s": 0.0}
    return {"rate_Hz": n / T_s, "rate_err_Hz": float(np.sqrt(n)) / T_s, "n_switches": n, "T_s": T_s}


RATE_AGREEMENT_MAX_RATIO = 2.0  # analyze_parity_run flags estimators further apart than this
HMM_MAX_SAMPLES = 100_000  # analyze_parity_run fits the HMM on at most this many leading samples
# HMM step (s) given to every gap-spanning step: saved t_us is stitched contiguously across
# acquisition gaps, so the dead time is not in it. 1e3 s decorrelates the chain for any rate
# above the fit's 1e-2 Hz lower bound (exp(-20)), so each gap-free segment is an independent
# restart, matching the other estimators that never count a switch across a gap.
HMM_GAP_DT_S = 1e3


def _readout_error_estimate(h, threshold):
    """Per-sample misassignment probabilities of thresholding the scores at `threshold`.

    From the two-Gaussian score fit h (projected_histogram_snr; component 0 = lower
    center = bit 0): eps_0 = P(score > thr | 0), eps_1 = P(score <= thr | 1) and the
    occupancy-weighted eps = w0 eps_0 + w1 eps_1. NaN when the fit or threshold is unusable.
    """
    from scipy.stats import norm

    nan = float("nan")
    if h is None or not np.isfinite(threshold):
        return nan, nan, nan
    mu = np.asarray(h["centers"], dtype=float)
    sig = np.asarray(h["sigmas"], dtype=float)
    w = np.asarray(h["weights"], dtype=float)
    if not (np.all(np.isfinite(mu)) and np.all(np.isfinite(w)) and np.all(sig > 0)):
        return nan, nan, nan
    eps0 = float(norm.sf((threshold - mu[0]) / sig[0]))
    eps1 = float(norm.cdf((threshold - mu[1]) / sig[1]))
    return eps0, eps1, float(w[0] * eps0 + w[1] * eps1)


def _noise_robust_rates(
    scores, t_us, gap_indices, sample_period_us, h, threshold, bits, hmm_max_samples=None
):
    """Readout-error estimate and the rate estimators that need no threshold.

    Threshold counting adds about 2 eps (1 - eps) / sample period of spurious switches
    (each misassigned sample makes two), so analyze_parity_run reports it beside:
    the ACF rate (autocorrelation_rate_us on the scores, pooled over the gap-free
    segments), the Welch PSD Lorentzian rate (psd_rate_estimate, run across gaps, so it is
    left out of the agreement when the record has gaps) and a two-state HMM
    (fit_two_state_hmm, fixed Gaussian emissions from the score fit h, per-step dt from
    diff(t_us) with every gap-spanning step set to HMM_GAP_DT_S so each gap-free segment is
    an independent restart -- saved t_us is contiguous across gaps --, at most
    `hmm_max_samples` leading samples, default gates incl. min_emission_snr = 0.7). All
    estimators are compared as a switch rate (switches per second, what threshold counting
    measures): HMM 2 g01 g10 / (g01 + g10); ACF and PSD give (g01 + g10)/2, scaled by
    4 w0 w1 with the fit's weights. Each block
    is guarded: a failure leaves its fields NaN with a warning. The eps, the HMM emissions
    and the 4 w0 w1 scale need a usable score fit, delta BIC > 0 and separation SNR > 1.5
    (the bimodality gate without its weight condition, so a lopsided occupancy still
    counts); otherwise they are NaN and hmm_unidentifiable_reasons says why.
    """
    nan = float("nan")
    if hmm_max_samples is None:
        hmm_max_samples = HMM_MAX_SAMPLES
    scores = np.ravel(np.asarray(scores, dtype=float))
    t = np.ravel(np.asarray(t_us, dtype=float))
    warnings = []
    out = {}

    fit_usable = (
        h is not None
        and np.isfinite(h["delta_bic"])
        and h["delta_bic"] > 0
        and h["separation_snr"] > 1.5
    )
    if not fit_usable:
        h = None
    eps0, eps1, eps = _readout_error_estimate(h, threshold)
    sp = float(sample_period_us)
    spurious = 2.0 * eps * (1.0 - eps) / (sp * 1e-6) if np.isfinite(eps) and sp > 0 else nan
    out.update(
        {
            "readout_eps_0": eps0,
            "readout_eps_1": eps1,
            "readout_eps": eps,
            "threshold_spurious_rate_Hz_est": spurious,
        }
    )

    threshold_rate = nan
    if bits is not None:
        try:
            threshold_rate = float(event_switch_rate(bits, t, gap_indices=gap_indices)["rate_Hz"])
        except Exception as e:  # the sidecar must always be written
            warnings.append(f"threshold rate failed: {e}")
    out["threshold_switch_rate_Hz"] = threshold_rate

    acf = {"tau_corr_us": nan, "gamma_hz": nan, "fit_ok": False, "warnings": []}
    try:
        acf = autocorrelation_rate_us(scores, sp, gap_indices=gap_indices)
    except Exception as e:
        warnings.append(f"ACF rate failed: {e}")
    warnings.extend(f"ACF: {w}" for w in acf["warnings"])
    out.update(
        {
            "acf_tau_corr_us": float(acf["tau_corr_us"]),
            "acf_gamma_Hz": float(acf["gamma_hz"]),
            "acf_fit_ok": bool(acf["fit_ok"]),
        }
    )

    psd = {"f_corner_hz": nan, "gamma_hz": nan, "fit_ok": False, "warnings": []}
    try:
        psd = psd_rate_estimate(scores, sp * 1e-6)
    except Exception as e:
        warnings.append(f"PSD rate failed: {e}")
    psd_gapped = len(_gap_segment_edges(gap_indices, scores.size)) > 2
    if psd_gapped:
        warnings.append(
            "PSD: Welch windows run across the acquisition gaps; left out of the rate agreement"
        )
    warnings.extend(f"PSD: {w}" for w in psd["warnings"])
    out.update(
        {
            "psd_f_corner_Hz": float(psd["f_corner_hz"]),
            "psd_gamma_Hz": float(psd["gamma_hz"]),
            "psd_fit_ok": bool(psd["fit_ok"]),
        }
    )

    hmm_fields = {
        "hmm_identifiable": False,
        "hmm_gamma01_Hz": nan,
        "hmm_gamma10_Hz": nan,
        "hmm_gamma01_err_Hz": nan,
        "hmm_gamma10_err_Hz": nan,
        "hmm_switch_rate_Hz": nan,
        "hmm_emission_snr": nan,
        "hmm_n_samples": 0,
        "hmm_unidentifiable_reasons": "",
    }
    if h is None:
        hmm_fields["hmm_unidentifiable_reasons"] = (
            "score fit not bimodal (delta BIC <= 0 or separation SNR <= 1.5): "
            "no emissions for the HMM"
        )
    else:
        try:
            m = int(min(scores.size, max(10, int(hmm_max_samples))))
            if m < scores.size:
                warnings.append(f"HMM: fitted on the first {m} of {scores.size} samples")
            emissions = {
                "model": "gaussian",
                "mu0": float(h["centers"][0]),
                "mu1": float(h["centers"][1]),
                "sigma0": float(h["sigmas"][0]),
                "sigma1": float(h["sigmas"][1]),
            }
            dt_steps = np.diff(t[:m]) * 1e-6
            gap_steps = np.asarray(_gap_segment_edges(gap_indices, m)[1:-1], dtype=int) - 1
            in_seg = np.ones(dt_steps.size, dtype=bool)
            in_seg[gap_steps] = False
            # the HMM's own start value (midpoint crossings / total time / 2) without the
            # gap steps, whose HMM_GAP_DT_S would otherwise dominate the total time
            b = scores[:m] > 0.5 * (emissions["mu0"] + emissions["mu1"])
            n_cross = int(np.count_nonzero(np.diff(b)[in_seg]))
            gamma_init = max(n_cross, 1) / max(float(dt_steps[in_seg].sum()), 1e-12) / 2.0
            dt_steps[gap_steps] = HMM_GAP_DT_S
            hmm = fit_two_state_hmm(
                scores[:m],
                dt_steps,
                emissions,
                gamma_init_hz=gamma_init,
                compute_viterbi=False,
            )
            g01, g10 = float(hmm["gamma01_hz"]), float(hmm["gamma10_hz"])
            ok = bool(hmm["identifiable"])  # the HMM leaves its errors finite when it withholds
            hmm_fields.update(
                {
                    "hmm_identifiable": ok,
                    "hmm_gamma01_Hz": g01,
                    "hmm_gamma10_Hz": g10,
                    "hmm_gamma01_err_Hz": float(hmm["gamma01_err_hz"]) if ok else nan,
                    "hmm_gamma10_err_Hz": float(hmm["gamma10_err_hz"]) if ok else nan,
                    "hmm_switch_rate_Hz": 2.0 * g01 * g10 / (g01 + g10),
                    "hmm_emission_snr": float(hmm["emission_snr"]),
                    "hmm_n_samples": m,
                    "hmm_unidentifiable_reasons": "; ".join(hmm["unidentifiable_reasons"]),
                }
            )
            warnings.extend(f"HMM: {w}" for w in hmm["warnings"])
        except Exception as e:
            warnings.append(f"HMM rate failed: {e}")
            hmm_fields["hmm_unidentifiable_reasons"] = f"HMM fit failed: {e}"
    out.update(hmm_fields)

    occ = 4.0 * float(np.prod(h["weights"])) if h is not None else nan
    agree = {
        "threshold": threshold_rate,
        "acf": occ * out["acf_gamma_Hz"] if out["acf_fit_ok"] else nan,
        "psd": occ * out["psd_gamma_Hz"] if out["psd_fit_ok"] and not psd_gapped else nan,
        "hmm": out["hmm_switch_rate_Hz"] if out["hmm_identifiable"] else nan,
    }
    finite = [v for v in agree.values() if np.isfinite(v) and v > 0]
    ratio = float(max(finite) / min(finite)) if len(finite) >= 2 else nan
    disagree = bool(np.isfinite(ratio) and ratio > RATE_AGREEMENT_MAX_RATIO)
    line = "switch rate: " + ", ".join(f"{k} {v:.4g} Hz" for k, v in agree.items())
    if psd_gapped:
        line += " (psd left out: Welch runs across the gaps)"
    if np.isfinite(spurious):
        line += f" (threshold spurious est {spurious:.4g} Hz, eps {eps:.3g})"
    if np.isfinite(ratio):
        line += f"; max/min {ratio:.3g}"
        line += f" > {RATE_AGREEMENT_MAX_RATIO:g}: DISAGREE" if disagree else ": agree"
    else:
        line += "; fewer than two estimators available"
    out.update(
        {
            "rate_switch_threshold_Hz": agree["threshold"],
            "rate_switch_acf_Hz": agree["acf"],
            "rate_switch_psd_Hz": agree["psd"],
            "rate_switch_hmm_Hz": agree["hmm"],
            "rate_agreement_max_ratio": ratio,
            "rates_disagree": disagree,
            "rate_agreement": line,
            "rate_warnings": "; ".join(warnings),
        }
    )
    return out


MAX_BURST_PASSES = 5  # burst exclusion / re-detection passes in baseline_rate_and_bursts


def baseline_rate_and_bursts(
    binary_states, t_us, rate_out, gap_indices=None, k_sigma=5, min_duration_us=None
):
    """
    Event-based baseline switch rate with one pass of burst exclusion, and the bursts.

    1. Provisional baseline: all switches / all observed time (`event_switch_rate`).
    2. Flag bursts in the sliding-window rates (`rate_out`, from
       `sliding_window_switch_rate`) with `detect_bursts` at that provisional baseline;
       a partial last window (rate_out["covered_us"] < window_us) is held to its own,
       higher threshold.
    3. Baseline: switches / observed time outside those bursts, each widened to the
       full extent of its flagged windows (by (window_us - stride)/2 per side). If the
       bursts cover the whole record, the provisional baseline is kept.
    4. Re-run `detect_bursts` at the new baseline; bursts that only now cross the
       threshold are excluded too, until no span is added (at most MAX_BURST_PASSES
       passes). The returned bursts are the last detection, all of them excluded.

    Returns (baseline, bursts): baseline is a dict with keys baseline_rate_Hz,
    baseline_rate_err_Hz (sqrt(n)/T), n_switches_baseline, T_baseline_s and
    median_window_rate_Hz (median of the window rates, the former baseline).
    Method: docs/experiments/zero_span_parity.md#baseline-switch-rate.
    """
    rate = np.asarray(rate_out["rate_Hz"], dtype=float)
    centers = rate_out["window_t_us"]

    def _bursts(baseline_rate):
        return detect_bursts(
            rate,
            centers,
            baseline_rate=baseline_rate,
            k_sigma=k_sigma,
            min_duration_us=min_duration_us,
            window_us=rate_out["window_us"],
            covered_us=rate_out.get("covered_us"),
        )

    # detect_bursts reports a burst as centers[s] - stride/2 .. centers[e-1] + stride/2,
    # but the flagged windows themselves span centers[s] - window_us/2 .. centers[e-1]
    # + window_us/2. Pad the exclusion by the difference so the burst's edge switches
    # (window_us/4 each side at 50 % overlap) do not leak into the baseline; masking a
    # little quiet time with its own switches is unbiased.
    stride = float(np.median(np.diff(centers))) if len(centers) >= 2 else 0.0
    pad = max(float(rate_out["window_us"]) - stride, 0.0) / 2.0

    est = event_switch_rate(binary_states, t_us, gap_indices=gap_indices)
    bursts = []
    if np.isfinite(est["rate_Hz"]) and rate.size:
        # Iterate: a lower baseline lets more bursts cross the threshold, and every
        # reported burst must be excluded from the baseline. Stop when the detection
        # no longer adds a span (at most MAX_BURST_PASSES passes).
        masked = set()
        bursts = _bursts(est["rate_Hz"])
        for _ in range(MAX_BURST_PASSES):
            spans = {(b["t_start_us"], b["t_end_us"]) for b in bursts}
            if not spans or spans <= masked:
                break
            masked |= spans
            quiet = event_switch_rate(
                binary_states,
                t_us,
                gap_indices=gap_indices,
                exclude_us=[(s - pad, e + pad) for s, e in sorted(masked)],
            )
            if quiet["T_s"] <= 0:
                break
            est = quiet
            bursts = _bursts(est["rate_Hz"])
    baseline = {
        "baseline_rate_Hz": est["rate_Hz"],
        "baseline_rate_err_Hz": est["rate_err_Hz"],
        "n_switches_baseline": est["n_switches"],
        "T_baseline_s": est["T_s"],
        "median_window_rate_Hz": float(np.median(rate)) if rate.size else 0.0,
    }
    return baseline, bursts


def sliding_window_switch_rate(binary_states, t_us, window_us, step_us=None, gap_indices=None):
    """
    Sliding-window switch rate in Hz from a binary parity trace.

    Parameters
    ----------
    binary_states : array_like of int (0 or 1), shape (N,)
    t_us          : array_like of float, shape (N,), monotonically increasing
    window_us     : float, window duration
    step_us       : float or None, window stride; default = window_us // 2 (50% overlap)
    gap_indices   : list[int] or None, indices i where bits[i] is the first sample
                    after an acquisition-gap boundary; the diff bits[i] - bits[i-1]
                    is set to 0 so no spurious switch is counted across a gap.

    Returns
    -------
    dict with keys:
      window_t_us         : array (M,), center time of each window
      rate_Hz             : array (M,), switches_per_window / covered_us
      switches_per_window : array (M,) of int
      covered_us          : array (M,), observed time of each window,
                            min(window_us, t_end - start + sample period) with the
                            sample period the median spacing of t_us; less than
                            window_us only for a final window that runs past the
                            record end (or a record shorter than one window). Such a
                            window is kept, its rate normalised to the time it covers.
                            A window starting after the last sample (possible only
                            when step_us > window_us) holds no data and is dropped.
      window_us, step_us  : echoed scalars
    """
    bits = np.asarray(binary_states, dtype=int)
    t = np.asarray(t_us, dtype=float)
    if bits.shape != t.shape:
        raise ValueError(f"binary_states shape {bits.shape} != t_us shape {t.shape}")

    if step_us is None:
        step_us = window_us // 2  # spec §3.2: 50% overlap, integer floor division

    if bits.size < 2:
        return {
            "window_t_us": np.zeros(0),
            "rate_Hz": np.zeros(0),
            "switches_per_window": np.zeros(0, dtype=int),
            "covered_us": np.zeros(0),
            "window_us": float(window_us),
            "step_us": float(step_us),
        }

    diffs, t_event, _ = _switch_events(bits, t, gap_indices)

    t_start = t[0]
    t_end = t[-1]
    if t_end - t_start < window_us:
        starts = np.array([t_start])
    else:
        starts = np.arange(t_start, t_end - window_us + step_us, step_us)
    centers = starts + window_us / 2.0
    # Half-open [s, s+window) so overlapping windows never double-count a boundary
    # event. The final window closes its right edge so a switch landing exactly at
    # t_end (possible when the record length is an exact multiple of the window) is
    # counted rather than silently dropped. Counted from the cumulative switch count
    # at the window edges (t_event = t[1:] is sorted), O((N + M) log N).
    cum = np.concatenate([[0], np.cumsum(diffs)])
    lo = np.searchsorted(t_event, starts, side="left")
    hi = np.searchsorted(t_event, starts + window_us, side="left")
    hi[-1] = np.searchsorted(t_event, starts[-1] + window_us, side="right")
    counts = (cum[hi] - cum[lo]).astype(int)
    # With step_us > window_us the arange can place a last start past t_end: that
    # window holds no sample (and no switch), so it is dropped rather than reported
    # as a zero rate over a non-positive observed time. Dropped after counting, so
    # the closed right edge stays on the arange's last window as before.
    keep = starts <= t_end
    starts, centers, counts = starts[keep], centers[keep], counts[keep]
    # Observed time per window: a sample at t stands for [t, t + sample period), so a
    # window starting at s covers min(window, t_end - s + sample period). Only the last
    # window (and a record shorter than one window) can be partial.
    sample_period_us = float(np.median(np.diff(t)))
    covered_us = np.minimum(float(window_us), t_end - starts + sample_period_us)
    rate_Hz = counts / (covered_us * 1e-6)

    return {
        "window_t_us": centers,
        "rate_Hz": rate_Hz,
        "switches_per_window": counts,
        "covered_us": covered_us,
        "window_us": float(window_us),
        "step_us": float(step_us),
    }


def detect_bursts(
    rate_Hz,
    window_t_us,
    baseline_rate=None,
    k_sigma=5,
    min_duration_us=None,
    window_us=None,
    covered_us=None,
):
    """
    Identify contiguous high-rate windows as bursts above a robust baseline.

    Parameters
    ----------
    rate_Hz       : array (M,) of switch rates per window (output of
                    sliding_window_switch_rate)
    window_t_us   : array (M,) of window center times
    baseline_rate : float or None; defaults to median(rate_Hz) (robust). analyze_parity_run
                    passes the event-based baseline (baseline_rate_and_bursts), which
                    need not be a whole number of switches per window.
    k_sigma       : float; threshold = baseline + k_sigma * sigma
    min_duration_us : float or None; filter bursts shorter than this
    window_us     : float or None; the sliding-window duration used to produce
                    `rate_Hz`. Used to derive the rate quantum (one switch per
                    window) for the Poisson sigma floor. If None it is estimated
                    from the smallest nonzero rate.
    covered_us    : array (M,) or None; the observed time of each window
                    (sliding_window_switch_rate's covered_us). Requires window_us. A
                    window with covered_us < window_us (a partial last window) gets
                    its own threshold, see below. None: every window is full.

    Threshold model
    ---------------
    sigma is the larger of the robust scale `1.4826 * MAD(rate_Hz)` (MAD taken
    about the *median* of rate_Hz, per spec §3.3) and a Poisson counting floor.
    In the normal regime most windows contain zero switches, so >50% of the
    rates are identical and MAD collapses to 0; a bare `baseline + k_sigma*0`
    threshold would then flag every window holding even one switch as a burst.
    The Poisson floor `sigma_floor = q * sqrt(max(baseline_counts, 1))`, where
    `q = 1/(window_us*1e-6)` is the rate per single switch, keeps the threshold
    a statistically meaningful margin above baseline tunneling.

    A partial window covering c < window_us has a rate n/c, so one switch there is
    worth q_c = q * window_us/c and its rate noise is larger. It is tested against
    baseline + k_sigma * max(1.4826 * MAD * sqrt(window_us/c),
    q_c * sqrt(max(baseline/q_c, 1))): the MAD scaled as a Poisson rate averaged over
    the shorter time, and the same Poisson floor for a window of length c. Full
    windows keep the threshold above, which is the reported threshold_Hz. In a burst
    holding a partial window, that window's excess (rate - baseline) * c enters
    integrated_excess_switches with the full windows' weight stride/window_us.

    Returns
    -------
    list of dicts, one per burst, with keys:
      t_start_us, t_end_us, duration_us,
      peak_rate_Hz, mean_rate_Hz, integrated_excess_switches,
      baseline_rate_Hz, threshold_Hz
    """
    rate = np.asarray(rate_Hz, dtype=float)
    centers = np.asarray(window_t_us, dtype=float)
    if rate.shape != centers.shape:
        raise ValueError(f"rate {rate.shape} and centers {centers.shape} differ")
    if rate.size == 0:
        return []

    median_rate = float(np.median(rate))
    if baseline_rate is None:
        baseline_rate = median_rate
    # MAD is a property of the rate distribution: always centered on the median,
    # independent of the (possibly caller-supplied) baseline (spec §3.3).
    mad = float(np.median(np.abs(rate - median_rate)))
    sigma = 1.4826 * mad

    # Rate quantum: the rate corresponding to a single switch in one window.
    if window_us is not None and window_us > 0:
        q = 1.0 / (float(window_us) * 1e-6)
    else:
        positive = rate[rate > 0]
        q = float(np.min(positive)) if positive.size else 0.0
    if q > 0:
        baseline_counts = max(baseline_rate, 0.0) / q
        sigma_floor = q * np.sqrt(max(baseline_counts, 1.0))
        sigma = max(sigma, sigma_floor)

    threshold = baseline_rate + k_sigma * sigma

    thresholds = np.full(rate.shape, threshold)
    partial = np.zeros(rate.shape, dtype=bool)
    if covered_us is not None:
        if not (window_us is not None and window_us > 0):
            raise ValueError("covered_us requires window_us")
        covered = np.asarray(covered_us, dtype=float)
        if covered.shape != rate.shape:
            raise ValueError(f"covered_us {covered.shape} and rate {rate.shape} differ")
        partial = covered < float(window_us)
        for i in np.where(partial)[0]:
            scale = float(window_us) / covered[i]
            q_c = q * scale
            floor_c = q_c * np.sqrt(max(max(baseline_rate, 0.0) / q_c, 1.0))
            sigma_c = max(1.4826 * mad * np.sqrt(scale), floor_c)
            thresholds[i] = baseline_rate + k_sigma * sigma_c

    above = rate > thresholds
    if not np.any(above):
        return []

    edges = np.diff(above.astype(int))
    starts = list(np.where(edges == 1)[0] + 1)
    ends = list(np.where(edges == -1)[0] + 1)
    if above[0]:
        starts = [0] + starts
    if above[-1]:
        ends = ends + [above.size]

    if centers.size >= 2:
        stride = float(np.median(np.diff(centers)))
    else:
        stride = 0.0

    bursts = []
    for s, e in zip(starts, ends):
        t_start = float(centers[s] - stride / 2.0)
        t_end = float(centers[e - 1] + stride / 2.0)
        duration = t_end - t_start
        if min_duration_us is not None and duration < min_duration_us:
            continue
        seg = rate[s:e]
        if partial[s:e].any():
            # a partial window's excess switches are (rate - baseline) * covered, of which
            # a full window's share stride/window_us is attributed to it, as for full ones
            w = covered[s:e] / float(window_us) * (stride * 1e-6)
            excess = float(np.sum((seg - baseline_rate) * w))
        else:
            excess = float(np.sum(seg - baseline_rate) * (stride * 1e-6))
        bursts.append(
            {
                "t_start_us": t_start,
                "t_end_us": t_end,
                "duration_us": duration,
                "peak_rate_Hz": float(np.max(seg)),
                "mean_rate_Hz": float(np.mean(seg)),
                "integrated_excess_switches": excess,
                "baseline_rate_Hz": baseline_rate,
                "threshold_Hz": threshold,
            }
        )
    return bursts


def _plot_iq_scatter(I, Q, bits, separator, out_path):
    fig, ax = plt.subplots(figsize=(6, 6))
    if bits is None:  # withheld by the apriori_gmm bimodality gate
        ax.scatter(I, Q, s=1, alpha=0.3, c="gray", label="unclassified")
    else:
        ax.scatter(
            np.asarray(I)[bits == 0], np.asarray(Q)[bits == 0], s=1, alpha=0.3, label="state 0"
        )
        ax.scatter(
            np.asarray(I)[bits == 1], np.asarray(Q)[bits == 1], s=1, alpha=0.3, label="state 1"
        )
    g = np.asarray(separator["g_center"], dtype=float)
    e = np.asarray(separator["e_center"], dtype=float)
    ax.plot([g[0], e[0]], [g[1], e[1]], "k--", lw=1)
    ax.scatter([g[0], e[0]], [g[1], e[1]], c="k", marker="x", s=60, label="separator")
    ax.set_xlabel("I")
    ax.set_ylabel("Q")
    ax.legend(loc="best", markerscale=4)
    ax.set_title("Parity IQ scatter")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _plot_parity_vs_time(bits, t_us, out_path, max_pts=100_000):
    fig, ax = plt.subplots(figsize=(10, 3))
    n = bits.size
    if n > max_pts:
        # Downsample to max_pts time bins (mean state per bin) so PNG generation
        # stays well under ~1 s even for multi-million-sample records.
        time_bins = np.linspace(t_us[0], t_us[-1], max_pts)
        idx = np.clip(np.searchsorted(time_bins, t_us) - 1, 0, time_bins.size - 1)
        avg_state = np.bincount(idx, weights=bits.astype(float), minlength=time_bins.size)
        cnt = np.bincount(idx, minlength=time_bins.size).astype(float)
        avg_state[cnt > 0] /= cnt[cnt > 0]
        ax.plot(time_bins / 1e6, avg_state, lw=0.5)
        ax.set_ylabel("mean state (downsampled)")
    else:
        ax.step(t_us / 1e6, bits, where="post", lw=0.5)
        ax.set_ylabel("parity state")
    ax.set_xlabel("time (s)")
    ax.set_title("Parity vs time")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _plot_switch_rate(rate_out, bursts, out_path):
    fig, ax = plt.subplots(figsize=(10, 3))
    ax.plot(rate_out["window_t_us"] / 1e6, rate_out["rate_Hz"], lw=0.8)
    if bursts:
        baseline = bursts[0]["baseline_rate_Hz"]
        threshold = bursts[0]["threshold_Hz"]
        ax.axhline(baseline, color="gray", ls=":", label=f"baseline {baseline:.1f} Hz")
        ax.axhline(threshold, color="red", ls="--", label=f"threshold {threshold:.1f} Hz")
        for b in bursts:
            ax.axvspan(b["t_start_us"] / 1e6, b["t_end_us"] / 1e6, color="red", alpha=0.15)
        ax.legend(loc="best")
    ax.set_xlabel("time (s)")
    ax.set_ylabel("switch rate (Hz)")
    ax.set_title("Sliding-window switch rate")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _plot_dwell_histograms(stats, out_path):
    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(10, 4))
    sp = stats.get("sample_period_us", float("nan"))
    for ax, dwells, fit, tau, err, n_exits, p, title in [
        (
            ax0,
            stats["dwell_0_us"],
            stats["exp_fit_0"],
            stats.get("tau_mle_0_us", float("nan")),
            stats.get("tau_err_0_us", float("nan")),
            stats.get("n_exits_0", 0),
            stats.get("p_exit_0", float("nan")),
            "state 0 dwells",
        ),
        (
            ax1,
            stats["dwell_1_us"],
            stats["exp_fit_1"],
            stats.get("tau_mle_1_us", float("nan")),
            stats.get("tau_err_1_us", float("nan")),
            stats.get("n_exits_1", 0),
            stats.get("p_exit_1", float("nan")),
            "state 1 dwells",
        ),
    ]:
        if dwells.size > 0:
            nb = fit.get("bins_used") or min(30, max(5, dwells.size // 10))
            counts, edges, _ = ax.hist(dwells, bins=int(nb), log=True, alpha=0.7)
            if np.isfinite(tau) and np.isfinite(sp) and sp > 0 and 0 < p < 1:
                # Expected counts per bin of the MLE geometric run-length law (P = the
                # per-sample exit probability, min dwell one sample):
                # N * (bin width / sp) * P * (1 - P)^((x - sp) / sp).
                bw = float(edges[1] - edges[0])
                xs = np.linspace(dwells.min(), dwells.max(), 200)
                ax.plot(
                    xs,
                    dwells.size * bw / sp * p * np.exp((xs - sp) / sp * np.log1p(-p)),
                    "r-",
                    label=f"tau_MLE={tau:.1f} +/- {err:.1f} us ({n_exits} exits)",
                )
                ax.legend()
        ax.set_xlabel("dwell (us)")
        ax.set_title(title)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _bin_iq_time(I, Q, t_us, bin_us, gap_indices=None):
    """
    Mean-bin (I, Q, t_us) into windows of `bin_us` microseconds.

    Bins are split across `gap_indices` so a bin never spans an acquisition
    boundary. Returns (I_b, Q_b, t_b, gap_indices_b, n_dropped) where
    n_dropped is the total number of raw samples discarded because they
    didn't fill a complete trailing bin in any segment.
    """
    I = np.ravel(np.asarray(I, dtype=float))
    Q = np.ravel(np.asarray(Q, dtype=float))
    t = np.ravel(np.asarray(t_us, dtype=float))
    if I.size == 0:
        return I, Q, t, [], 0
    sp = float(t[1] - t[0]) if t.size > 1 else float(bin_us)
    if sp <= 0:
        sp = float(bin_us)
    bin_samples = max(1, int(round(float(bin_us) / sp)))
    segment_edges = _gap_segment_edges(gap_indices, I.size)
    I_parts, Q_parts, t_parts = [], [], []
    new_gaps = []
    cum = 0
    n_dropped = 0
    for seg_idx, (a, b) in enumerate(zip(segment_edges[:-1], segment_edges[1:])):
        n_in_seg = b - a
        n_bins = n_in_seg // bin_samples
        n_dropped += n_in_seg - n_bins * bin_samples
        if n_bins == 0:
            continue
        keep = n_bins * bin_samples
        I_seg = I[a : a + keep].reshape(n_bins, bin_samples).mean(axis=1)
        Q_seg = Q[a : a + keep].reshape(n_bins, bin_samples).mean(axis=1)
        t_seg = t[a : a + keep].reshape(n_bins, bin_samples).mean(axis=1)
        I_parts.append(I_seg)
        Q_parts.append(Q_seg)
        t_parts.append(t_seg)
        if seg_idx > 0:
            new_gaps.append(cum)
        cum += n_bins
    if not I_parts:
        return (np.zeros(0), np.zeros(0), np.zeros(0), [], int(n_dropped))
    return (
        np.concatenate(I_parts),
        np.concatenate(Q_parts),
        np.concatenate(t_parts),
        new_gaps,
        int(n_dropped),
    )


def analyze_parity_run(
    h5_path,
    separator=None,
    window_us=1000.0,
    k_sigma=5.0,
    classifier_method="apriori_gmm",
    step_us=None,
    min_burst_duration_us=None,
    save_plots=True,
    out_dir=None,
    analysis_bin_us=None,
    hmm_max_samples=HMM_MAX_SAMPLES,
):
    """
    Load a ZeroSpanParity raw .h5, classify into parity bits, compute switch rate,
    detect bursts, compute dwell statistics, save plots and a sidecar.

    Parameters
    ----------
    h5_path           : str, path to raw .h5 written by ZeroSpanParity.save_data
    separator         : dict or None; required for the separator methods
    window_us         : float, sliding-window size
    k_sigma           : float, burst threshold
    classifier_method : "apriori_gmm" (default; legacy alias "apriori") | "apriori_midpoint"
                        | "kmeans" (classify_parity_trace). When "apriori_gmm" withholds the
                        bits (score histogram not bimodal), every rate, burst and dwell field
                        is NaN, no bit-derived plot is drawn and classifier_warning says why.
    step_us           : float or None, window stride
    min_burst_duration_us : float or None
    save_plots        : bool
    out_dir           : str or None; defaults to directory of h5_path
    analysis_bin_us   : float or None
        Mean-bin the trace into this many microseconds before classification.
        Default: None (no binning). Per-sample SNR in a decimated trace is
        much lower than a strobe sample; if the apriori separator is in
        single-shot units, pass an explicit `analysis_bin_us` (e.g. equal
        to one read_length, or a fraction of it for finer time resolution).
        Real decimated captures cover a single `read_length` end-to-end,
        so binning by the full read_length collapses the capture to one
        point — choose a fraction.
    hmm_max_samples   : int, the HMM is fitted on at most this many leading samples
                        (usually 3-8 s per 1e5 samples; up to about 1 min when its
                        L-BFGS-B fit fails and the Powell fallback runs, e.g. the
                        flat likelihood of a gapped record with no time correlation;
                        rate_warnings then says "retried with Powell")

    Readout-error model and noise-robust rates (_noise_robust_rates): readout_eps_0/1 and
    readout_eps (per-sample misassignment at the threshold, from the score fit),
    threshold_spurious_rate_Hz_est = 2 eps (1 - eps) / sample_period_us (post-binning),
    threshold_switch_rate_Hz (all switches / all observed time), the ACF (acf_*), PSD
    (psd_*) and HMM (hmm_*) rates on the scores, and the agreement line rate_agreement with
    rate_switch_*_Hz (every estimator as switches per second), rate_agreement_max_ratio and
    rates_disagree (max/min > RATE_AGREEMENT_MAX_RATIO = 2). These run also when the bits
    are withheld (the threshold entry is then NaN); the HMM's own gates decide its rate.

    Returns
    -------
    dict with summary fields (matches sidecar JSON), including the "apriori_gmm" score-
    histogram fit (classifier_separation_snr, classifier_delta_bic and the two-component
    classifier_centers / classifier_sigmas / classifier_weights lists; NaN for the other
    methods).
    """
    if out_dir is None:
        out_dir = os.path.dirname(h5_path) or "."
    base = os.path.splitext(os.path.basename(h5_path))[0]

    with h5py.File(h5_path, "r") as f:
        I = np.array(f["I"])
        Q = np.array(f["Q"])
        t_us = np.array(f["t_us"])
        gap_indices = list(np.array(f["gap_indices"])) if "gap_indices" in f else []
        sample_period_us = float(
            f.attrs.get("sample_period_us", (t_us[1] - t_us[0]) if t_us.size > 1 else 0.0)
        )
        mode = str(f.attrs.get("mode", "strobe"))

    raw_sample_period_us = sample_period_us
    n_raw_samples = int(I.size)
    n_binned_samples = int(I.size)
    n_dropped = 0
    # Do NOT auto-bin: the spec's Path B intent is a raw decimated waveform.
    # Binning by the declared `read_length_us` would collapse the whole
    # capture to a single point (decimated mode captures one read_length
    # end-to-end). Callers that need integrated bins must pass
    # `analysis_bin_us` explicitly.
    if analysis_bin_us and float(analysis_bin_us) > 0:
        I, Q, t_us, gap_indices, n_dropped = _bin_iq_time(
            I, Q, t_us, float(analysis_bin_us), gap_indices=gap_indices
        )
        n_binned_samples = int(I.size)
        if t_us.size > 1:
            sample_period_us = float(t_us[1] - t_us[0])

    cls = classify_parity_trace(I, Q, separator=separator, method=classifier_method)
    bits = cls["binary_states"]
    sep_used = cls["separator_used"]
    withheld = bits is None
    if cls["warning"]:
        print(f"[analyze_parity_run] WARNING: {cls['warning']}")

    if withheld:
        # no parity bits: report NaN, never a rate thresholded at a guessed level
        nan = float("nan")
        rate_out = {
            "window_t_us": np.zeros(0),
            "rate_Hz": np.zeros(0),
            "switches_per_window": np.zeros(0, dtype=int),
            "covered_us": np.zeros(0),
            "window_us": float(window_us),
            "step_us": float(window_us // 2 if step_us is None else step_us),
        }
        baseline = {
            "baseline_rate_Hz": nan,
            "baseline_rate_err_Hz": nan,
            "n_switches_baseline": nan,
            "T_baseline_s": nan,
            "median_window_rate_Hz": nan,
        }
        bursts = []
        stats = {
            "mean_0": nan,
            "mean_1": nan,
            "n_runs_0": nan,
            "n_runs_1": nan,
            "tau_mle_0_us": nan,
            "tau_mle_1_us": nan,
            "tau_err_0_us": nan,
            "tau_err_1_us": nan,
            "n_exits_0": nan,
            "n_exits_1": nan,
            "n_interior_0": nan,
            "n_interior_1": nan,
            "exp_fit_0": {"tau_us": nan},
            "exp_fit_1": {"tau_us": nan},
            "dwell_0_us": np.zeros(0),
            "dwell_1_us": np.zeros(0),
        }
    else:
        rate_out = sliding_window_switch_rate(
            bits, t_us, window_us=window_us, step_us=step_us, gap_indices=gap_indices
        )
        baseline, bursts = baseline_rate_and_bursts(
            bits,
            t_us,
            rate_out,
            gap_indices=gap_indices,
            k_sigma=k_sigma,
            min_duration_us=min_burst_duration_us,
        )
        stats = dwell_time_statistics(bits, t_us, gap_indices=gap_indices)

    if save_plots:
        _plot_iq_scatter(I, Q, bits, sep_used, os.path.join(out_dir, base + "_iq_scatter.png"))
        if not withheld:
            _plot_parity_vs_time(bits, t_us, os.path.join(out_dir, base + "_parity_vs_time.png"))
            _plot_switch_rate(
                rate_out, bursts, os.path.join(out_dir, base + "_switch_rate_vs_time.png")
            )
            _plot_dwell_histograms(stats, os.path.join(out_dir, base + "_dwell_histograms.png"))

    h_fit = cls.get("histogram_fit")
    if h_fit is None:
        from qicklab.analysis.zero_span_checks import projected_histogram_snr

        h_fit = projected_histogram_snr(cls["scores"])
    robust = _noise_robust_rates(
        cls["scores"],
        t_us,
        gap_indices,
        sample_period_us,
        h_fit,
        float(cls["threshold"]),
        bits,
        hmm_max_samples=hmm_max_samples,
    )
    print(f"[analyze_parity_run] {robust['rate_agreement']}")

    summary = {
        "h5_path": h5_path,
        "sample_period_us": sample_period_us,
        "raw_sample_period_us": raw_sample_period_us,
        "n_samples": int(cls["scores"].size),
        "n_raw_samples": n_raw_samples,
        "n_binned_samples": n_binned_samples,
        "n_samples_dropped_by_binning": int(n_dropped),
        "analysis_bin_us": float(analysis_bin_us) if analysis_bin_us else 0.0,
        "mode": mode,
        "n_bursts": float("nan") if withheld else len(bursts),
        **baseline,
        "mean_dwell_0_us": stats["mean_0"],
        "mean_dwell_1_us": stats["mean_1"],
        "n_runs_0": stats["n_runs_0"],
        "n_runs_1": stats["n_runs_1"],
        "exp_fit_tau_0_us": stats["exp_fit_0"]["tau_us"],
        "exp_fit_tau_1_us": stats["exp_fit_1"]["tau_us"],
        "tau_mle_0_us": stats["tau_mle_0_us"],
        "tau_mle_1_us": stats["tau_mle_1_us"],
        "tau_err_0_us": stats["tau_err_0_us"],
        "tau_err_1_us": stats["tau_err_1_us"],
        "n_exits_0": stats["n_exits_0"],
        "n_exits_1": stats["n_exits_1"],
        "n_interior_0": stats["n_interior_0"],
        "n_interior_1": stats["n_interior_1"],
        "classifier_method": cls["method"],
        "classifier_threshold": float(cls["threshold"]),
        "bits_withheld": bool(withheld),
        "classifier_warning": cls["warning"] or "",
        **_histogram_fit_summary(cls.get("histogram_fit")),
        **robust,
    }

    with open(os.path.join(out_dir, base + "_analysis.json"), "w") as f:
        json.dump(
            {
                **summary,
                "bursts": bursts,
                "window_us": rate_out["window_us"],
                "step_us": rate_out["step_us"],
                "provenance": provenance(),  # of this analysis run (docs/architecture.md#provenance)
            },
            f,
            indent=2,
            default=lambda x: x.tolist() if isinstance(x, np.ndarray) else float(x),
        )
    with h5py.File(os.path.join(out_dir, base + "_analysis.h5"), "w") as f:
        f.create_dataset("binary_states", data=np.zeros(0, dtype=int) if withheld else bits)
        f.create_dataset("scores", data=cls["scores"])
        f.create_dataset("window_t_us", data=rate_out["window_t_us"])
        f.create_dataset("rate_Hz", data=rate_out["rate_Hz"])
        f.create_dataset("dwell_0_us", data=stats["dwell_0_us"])
        f.create_dataset("dwell_1_us", data=stats["dwell_1_us"])
        for k, v in summary.items():
            try:
                f.attrs[k] = v
            except TypeError:
                f.attrs[k] = str(v)
    return summary
