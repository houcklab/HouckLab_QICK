"""Zero-span parity validation primitives (modulation, contrast, bimodality, bin-size and threshold sweeps)."""

import numpy as np

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
