"""Zero-span parity validation primitives (modulation, contrast, bimodality, bin-size and threshold
sweeps, stage-8 control statistics)."""

import numpy as np
from scipy import stats

from qicklab.analysis.dwell import dwell_time_statistics
from qicklab.analysis.zero_span import _bin_iq_time, classify_parity_trace


def verify_modulation(scores, t_us, modulation_reference, gap_indices=None):
    """Confirm a recovered projected trace carries an injected on/off square wave.

    Primary metrics: level_on/off, modulation_depth, snr, correlation, lag_samples.
    Secondary (diagnostic only): recovered_freq_hz vs injected_freq_hz.
    """
    scores = np.asarray(scores, dtype=float).ravel()
    ref = np.asarray(modulation_reference, dtype=float).ravel()
    t_us = np.asarray(t_us, dtype=float).ravel()
    out = {
        "level_on": np.nan,
        "level_off": np.nan,
        "modulation_depth": np.nan,
        "snr": np.nan,
        "correlation": np.nan,
        "lag_samples": 0,
        "recovered_freq_hz": np.nan,
        "injected_freq_hz": np.nan,
    }
    n = min(scores.size, ref.size, t_us.size)
    if n < 2:
        return out
    scores, ref, t_us = scores[:n], ref[:n], t_us[:n]
    on = ref > 0.5
    off = ~on
    if on.sum() == 0 or off.sum() == 0:
        return out
    level_on = float(np.mean(scores[on]))
    level_off = float(np.mean(scores[off]))
    pooled = float(np.sqrt(0.5 * (np.var(scores[on]) + np.var(scores[off]))))
    out["level_on"] = level_on
    out["level_off"] = level_off
    out["modulation_depth"] = abs(level_on - level_off)
    out["snr"] = abs(level_on - level_off) / pooled if pooled > 0 else np.inf
    # Normalised cross-correlation (primary)
    s = scores - scores.mean()
    r = ref - ref.mean()
    denom = float(np.sqrt(np.sum(s * s) * np.sum(r * r)))
    if denom > 0:
        full = np.correlate(s, r, mode="full") / denom
        k = int(np.argmax(np.abs(full)))
        out["correlation"] = float(full[k])
        out["lag_samples"] = int(k - (n - 1))
    # Injected freq from reference transitions: transitions + 1 whole half-periods span the
    # n samples, i.e. n * dt (the record starts and ends on a block boundary)
    dt_us = float(np.median(np.diff(t_us))) if n > 1 else 0.0
    duration_s = n * dt_us * 1e-6
    transitions = int(np.count_nonzero(np.diff((ref > 0.5).astype(int))))
    if duration_s > 0 and transitions > 0:
        out["injected_freq_hz"] = ((transitions + 1) / 2.0) / duration_s
    # Recovered freq from dominant FFT bin (diagnostic only)
    if dt_us > 0 and n > 4:
        freqs = np.fft.rfftfreq(n, d=dt_us * 1e-6)
        spec = np.abs(np.fft.rfft(scores - scores.mean()))
        if spec.size > 1:
            out["recovered_freq_hz"] = float(freqs[1:][int(np.argmax(spec[1:]))])
    return out


def contrast_from_sweeps(freqs, Z_on, Z_off):
    """|Z_on - Z_off|(f), best probe freq, robust contrast SNR.

    Z_on/Z_off are complex demodulated responses (proportional to S21, NOT
    calibrated S21).
    """
    freqs = np.asarray(freqs, dtype=float).ravel()
    Z_on = np.asarray(Z_on).ravel()
    Z_off = np.asarray(Z_off).ravel()
    out = {
        "freqs": freqs,
        "contrast": np.zeros(0),
        "best_freq": np.nan,
        "max_contrast": np.nan,
        "contrast_snr": np.nan,
        "Z_on": Z_on,
        "Z_off": Z_off,
    }
    n = min(freqs.size, Z_on.size, Z_off.size)
    if n == 0:
        return out
    freqs, Z_on, Z_off = freqs[:n], Z_on[:n], Z_off[:n]
    contrast = np.abs(Z_on - Z_off)
    idx = int(np.argmax(contrast))
    med = float(np.median(contrast))
    mad = float(np.median(np.abs(contrast - med)))
    noise_floor = 1.4826 * mad if mad > 0 else (med if med > 0 else 1.0)
    out.update(
        {
            "freqs": freqs,
            "contrast": contrast,
            "best_freq": float(freqs[idx]),
            "max_contrast": float(contrast[idx]),
            "contrast_snr": float(contrast[idx] / noise_floor) if noise_floor > 0 else np.inf,
            "Z_on": Z_on,
            "Z_off": Z_off,
        }
    )
    return out


def projected_histogram_snr(scores, bins="auto"):
    """Two-Gaussian fit of V(t) with conservative, BIC-based bimodality.

    A 2-component GMM almost always 'finds' two peaks, so is_bimodal requires
    delta_bic>0 AND separation_snr>1.5 AND both weights in (0.1, 0.9).
    """
    scores = np.asarray(scores, dtype=float).ravel()
    out = {
        "centers": np.array([np.nan, np.nan]),
        "sigmas": np.array([np.nan, np.nan]),
        "weights": np.array([np.nan, np.nan]),
        "separation_snr": 0.0,
        "overlap": np.nan,
        "is_bimodal": False,
        "bic_1": np.nan,
        "bic_2": np.nan,
        "delta_bic": np.nan,
        "hist": np.zeros(0),
        "bin_edges": np.zeros(0),
    }
    if scores.size < 10:
        return out
    from sklearn.mixture import GaussianMixture

    x = scores.reshape(-1, 1)
    g1 = GaussianMixture(n_components=1, random_state=0).fit(x)
    g2 = GaussianMixture(n_components=2, random_state=0).fit(x)
    bic_1 = float(g1.bic(x))
    bic_2 = float(g2.bic(x))
    means = g2.means_.ravel()
    sigmas = np.sqrt(g2.covariances_.ravel())
    weights = g2.weights_.ravel()
    order = np.argsort(means)
    centers, sig, w = means[order], sigmas[order], weights[order]
    denom = np.sqrt(0.5 * (sig[0] ** 2 + sig[1] ** 2))
    sep = float(abs(centers[1] - centers[0]) / denom) if denom > 0 else 0.0
    # Bhattacharyya coefficient (two gaussians) as overlap
    s2 = sig[0] ** 2 + sig[1] ** 2
    bc = (
        float(
            np.sqrt(2 * sig[0] * sig[1] / s2) * np.exp(-0.25 * (centers[0] - centers[1]) ** 2 / s2)
        )
        if s2 > 0
        else 1.0
    )
    hist, edges = np.histogram(scores, bins=bins)
    is_bimodal = (bic_1 - bic_2 > 0) and (sep > 1.5) and (0.1 < w[0] < 0.9) and (0.1 < w[1] < 0.9)
    out.update(
        {
            "centers": centers,
            "sigmas": sig,
            "weights": w,
            "separation_snr": sep,
            "overlap": bc,
            "is_bimodal": bool(is_bimodal),
            "bic_1": bic_1,
            "bic_2": bic_2,
            "delta_bic": bic_1 - bic_2,
            "hist": hist,
            "bin_edges": edges,
        }
    )
    return out


def bin_size_sweep(I, Q, t_us, separator, bin_list_us, gap_indices=None, method="apriori"):
    """Reprocess the same raw IQ at several bin sizes.

    Returns per-bin separation SNR and dwell tau. best_bin_us maximizes separation
    SNR. NO monotonic-then-degrade assertion: the optimum can occur before T_parity.
    """
    sep_snr, mean_dwell, exp_tau = [], [], []
    for b in bin_list_us:
        Ib, Qb, tb, gb, _ = _bin_iq_time(I, Q, t_us, float(b), gap_indices)
        cls = classify_parity_trace(Ib, Qb, separator=separator, method=method)
        h = projected_histogram_snr(cls["scores"])
        dw = dwell_time_statistics(
            cls["binary_states"], tb, gap_indices=gb, merge_short_segments=True, min_dwell_bins=2
        )
        sep_snr.append(h["separation_snr"])
        mean_dwell.append(0.5 * (dw["mean_0"] + dw["mean_1"]))
        taus = [dw["exp_fit_0"]["tau_us"], dw["exp_fit_1"]["tau_us"]]
        taus = [tt for tt in taus if np.isfinite(tt)]
        exp_tau.append(float(np.mean(taus)) if taus else np.nan)
    snr_arr = np.array(sep_snr, dtype=float)
    best_bin = (
        float(bin_list_us[int(np.nanargmax(snr_arr))]) if np.any(np.isfinite(snr_arr)) else np.nan
    )
    return {
        "bin_list_us": list(bin_list_us),
        "separation_snr_per_bin": sep_snr,
        "mean_dwell_per_bin": mean_dwell,
        "exp_tau_per_bin": exp_tau,
        "best_bin_us": best_bin,
    }


def threshold_stability(scores, t_us, threshold_list=None, gap_indices=None, min_dwell_bins=2):
    """Vary the classification threshold; report dwell tau stability.

    Low tau_cv (coefficient of variation across thresholds) = robust telegraph;
    high tau_cv = noise crossings.
    """
    scores = np.asarray(scores, dtype=float).ravel()
    if threshold_list is None:
        threshold_list = list(np.percentile(scores, [30, 40, 50, 60, 70])) if scores.size else [0.0]
    tau0, tau1 = [], []
    for th in threshold_list:
        bits = (scores > th).astype(int)
        dw = dwell_time_statistics(
            bits,
            t_us,
            gap_indices=gap_indices,
            merge_short_segments=True,
            min_dwell_bins=min_dwell_bins,
        )
        tau0.append(dw["exp_fit_0"]["tau_us"])
        tau1.append(dw["exp_fit_1"]["tau_us"])
    allt = np.array([x for x in (tau0 + tau1) if np.isfinite(x)], dtype=float)
    tau_cv = float(np.std(allt) / np.mean(allt)) if allt.size >= 2 and np.mean(allt) > 0 else np.inf
    return {
        "threshold_list": list(threshold_list),
        "tau0_per_threshold": tau0,
        "tau1_per_threshold": tau1,
        "tau_cv": tau_cv,
    }


def batch_means_se(x, t_us, batch_us, min_batches=4):
    """Mean of a correlated record and its standard error from non-overlapping batch means.

    A parity telegraph is correlated over its dwell time, so std/sqrt(N) of the raw samples
    understates the error. The record is cut into consecutive batches of
    round(batch_us / dt) samples (dt = median sample spacing, trailing partial batch
    dropped); se = std(batch means, ddof=1) / sqrt(n_batches), with n_batches - 1 degrees
    of freedom. batch_us must be much longer than the correlation time. se is NaN when
    fewer than min_batches fit. Returns (mean, se, n_batches); mean is over the whole record.
    """
    x = np.asarray(x, dtype=float).ravel()
    t_us = np.asarray(t_us, dtype=float).ravel()
    if x.size == 0:
        return np.nan, np.nan, 0
    mean = float(np.mean(x))
    dt = float(np.median(np.diff(t_us))) if t_us.size > 1 else 0.0
    if dt <= 0 or not np.isfinite(dt):
        return mean, np.nan, 0
    blen = max(1, int(round(float(batch_us) / dt)))
    n_b = x.size // blen
    if n_b < max(2, int(min_batches)):
        return mean, np.nan, int(n_b)
    bm = x[: n_b * blen].reshape(n_b, blen).mean(axis=1)
    return mean, float(np.std(bm, ddof=1) / np.sqrt(n_b)), int(n_b)


def _record_stats(rec, batch_us, min_batches):
    lvl, lvl_se, n_b = batch_means_se(rec["scores"], rec["t_us"], batch_us, min_batches)
    return {"level": lvl, "level_se": lvl_se, "n_batches": n_b}


def _combine(terms):
    """se and Welch-Satterthwaite dof of sum(c * level) over independent records.

    terms: (c, stats) pairs. Both are NaN when any se is undefined."""
    var_parts = [(c**2) * s["level_se"] ** 2 for c, s in terms]
    var = float(np.sum(var_parts))
    if not np.isfinite(var):
        return np.nan, np.nan
    if var <= 0:
        return 0.0, np.nan
    den = float(np.sum([v**2 / (s["n_batches"] - 1) for v, (_, s) in zip(var_parts, terms)]))
    return float(np.sqrt(var)), (var**2 / den if den > 0 else np.inf)


def critical_value(k_sigma, dof):
    """Student-t critical value with the tail probability of a normal k_sigma threshold.

    With few batches the se is itself uncertain, so delta/se is t-distributed with the
    Welch dof; comparing it to k_sigma would inflate the false-alarm rate (k_sigma = 3,
    4 batches per record: ~2 % instead of 0.27 %). The same value serves a one-sided
    test at k_sigma and a two-sided |z| test. NaN for an undefined dof."""
    if dof == np.inf:
        return float(k_sigma)
    if not np.isfinite(dof) or dof <= 0:
        return np.nan
    return float(stats.t.isf(stats.norm.sf(k_sigma), dof))


def _shift(on, off, k_sigma):
    """delta = level_on - level_off (independent records), se, z = delta/se, dof, t_crit."""
    delta = float(on["level"] - off["level"])
    se, dof = _combine([(1.0, on), (-1.0, off)])
    z = delta / se if (np.isfinite(se) and se > 0) else np.nan
    return {
        "delta": delta,
        "delta_se": float(se),
        "delta_z": float(z),
        "delta_dof": float(dof),
        "t_crit": critical_value(k_sigma, dof),
    }


def _defined(s):
    return bool(np.isfinite(s["delta_z"]) and np.isfinite(s["t_crit"]))


def level_shift_null(record, off_record, batch_us, k_sigma=3.0, min_batches=4):
    """Null control: the mean projected level must not move from the drive-off reference.

    record / off_record: dicts with "scores" and "t_us". null_ok is |z| < t_crit (two-sided,
    tail probability of a normal k_sigma, Welch dof from the batch means). Tri-state: None,
    with insufficient_batches True, when the se is undefined (a record holds fewer than
    min_batches batches), so a short record is not read as a null violation.
    """
    on = _record_stats(record, batch_us, min_batches)
    off = _record_stats(off_record, batch_us, min_batches)
    s = _shift(on, off, k_sigma)
    ok = _defined(s)
    return {
        **s,
        "null_ok": bool(abs(s["delta_z"]) < s["t_crit"]) if ok else None,
        "insufficient_batches": not ok,
        "n_batches": min(on["n_batches"], off["n_batches"]),
    }


def branch_response_test(
    lower, higher, off_record, batch_us, e_minus_g, k_sigma=3.0, min_batches=4, pe_drive=0.5
):
    """Stage-8 variant D: does driving EACH parity branch raise the mean level above drive-off?

    Driving a branch excites only the samples in the parity whose transition is that peak,
    so both shifts are positive (toward e): delta_lower = P_lower * p_e,lower * |e - g| and
    delta_higher = P_higher * p_e,higher * |e - g| (projected). P_lower is the occupation of
    the parity whose transition is the lower peak; which parity that is depends on the
    offset charge. A sign comparison of the two shifts therefore cannot reverse for a
    genuine signal. Records are dicts with "scores" and "t_us"; e_minus_g is the projected
    e - g distance in score units (|e_center - g_center|^2 for project_iq_onto_separator).
    Reported:

    - both_branches_respond: z_lower > t_crit_lower and z_higher > t_crit_higher (one-sided,
      tail probability of a normal k_sigma, Welch dof); None, with insufficient_batches
      True, when an se is undefined;
    - branch_ratio = delta_lower / delta_higher, expected P_lower p_e,lower /
      (P_higher p_e,higher), with a delta-method se that includes the shared reference;
    - complementarity = (delta_lower + delta_higher) / (pe_drive * e_minus_g): ~1
      (P_lower + P_higher = 1) when both branches are driven to the same excited
      population pe_drive; below 1 when under-driven or with thermal population p_th
      (~1 - p_th / pe_drive); above 1 when e_minus_g is too small (the SingleShot
      calibration centres are plain means, pulled together by pi infidelity, T1 during
      the readout and p_th), so a value clearly above 1 means a separator or pe_drive
      miscalibration. Built from mean levels, which are linear in p_e whether a sample
      is a projective outcome or a time average over the near-CW drive (a thresholded
      bright fraction is not).
      Secondary: it depends on the assumed pe_drive and says nothing about P_lower itself.
      complementarity_z = (complementarity - 1) / complementarity_se.
    """
    lo = _record_stats(lower, batch_us, min_batches)
    hi = _record_stats(higher, batch_us, min_batches)
    off = _record_stats(off_record, batch_us, min_batches)
    s_lo = _shift(lo, off, k_sigma)
    s_hi = _shift(hi, off, k_sigma)
    d_lo, d_hi = s_lo["delta"], s_hi["delta"]
    ok = _defined(s_lo) and _defined(s_hi)
    respond = (
        bool(s_lo["delta_z"] > s_lo["t_crit"] and s_hi["delta_z"] > s_hi["t_crit"]) if ok else None
    )
    ratio = d_lo / d_hi if d_hi != 0 else np.nan
    if d_hi != 0 and ok:
        # var(d_lo) + r^2 var(d_hi) - 2 r cov(d_lo, d_hi); cov = var(off), the shared reference
        var = s_lo["delta_se"] ** 2 + ratio**2 * s_hi["delta_se"] ** 2
        var -= 2.0 * ratio * off["level_se"] ** 2
        ratio_se = float(np.sqrt(max(var, 0.0)) / abs(d_hi))
    else:
        ratio_se = np.nan
    norm = float(pe_drive) * float(e_minus_g)
    if norm > 0:
        comp = (d_lo + d_hi) / norm
        c_se, c_dof = _combine([(1.0, lo), (1.0, hi), (-2.0, off)])
        c_se = c_se / norm
    else:
        comp, c_se, c_dof = np.nan, np.nan, np.nan
    c_z = (comp - 1.0) / c_se if (np.isfinite(c_se) and c_se > 0) else np.nan
    out = {}
    for name, s in (("lower", s_lo), ("higher", s_hi)):
        out[f"delta_{name}"] = s["delta"]
        out[f"delta_{name}_se"] = s["delta_se"]
        out[f"delta_{name}_z"] = s["delta_z"]
        out[f"delta_{name}_dof"] = s["delta_dof"]
        out[f"t_crit_{name}"] = s["t_crit"]
    out.update(
        {
            "both_branches_respond": respond,
            "insufficient_batches": not ok,
            "branch_ratio": float(ratio),
            "branch_ratio_se": ratio_se,
            "complementarity": float(comp),
            "complementarity_se": float(c_se),
            "complementarity_z": float(c_z),
            "complementarity_dof": float(c_dof),
            "n_batches": min(lo["n_batches"], hi["n_batches"], off["n_batches"]),
        }
    )
    return out
