"""Single-shot readout analysis: g/e empirical-CDF contrast (hist_process), labelled g/e
overlap error (labelled_overlap_error), labelled-shot calibration, an unlabelled record's
self-calibration (calibrate_readout_from_record) and IQ-trace projection.
Conventions and the meaning of "fidelity": docs/concepts/iq_conventions.md."""

import math

import matplotlib.pyplot as plt
import numpy as np
import scipy.optimize
import scipy.special
from sklearn.cluster import KMeans

from qicklab.analysis.iq import rotate_data

# labelled_overlap_error keeps the minority (prep-error) components only when they raise the
# joint log-likelihood by at least this much (2 Delta lnL) over the same fit with w_g = w_e = 0.
_MIXTURE_MIN_2DLNL = 9.0
# The e-cloud mixture of calibrate_readout_from_labeled_shots
# (docs/experiments/modified_ramsey.md#analysis): sigma_e / sigma_g bound, the e-set weight
# below which (or a clean SNR below 1) it falls back to the raw moments, and the e-cloud
# purity below which it warns.
_CLOUD_SIGMA_RATIO_BOUNDS = (0.8, 1.25)
_CLOUD_MIN_E_PURITY = 0.2
_CLOUD_WARN_E_PURITY = 0.9


def labelled_overlap_error(i_g, q_g, i_e, q_e):
    """Separation-limited overlap error of labelled g/e single shots, 2 Phi(-d/2).

    The shots are projected onto the g-median -> e-median line (hist_process's axis) and one
    unbinned maximum-likelihood fit is made to both labelled sets together:
    g shots ~ (1 - w_g) N(mu_g, sigma) + w_g N(mu_e, sigma) and
    e shots ~ (1 - w_e) N(mu_e, sigma) + w_e N(mu_g, sigma), with a shared sigma, minority
    weights w_g, w_e in [0, 0.5], centres seeded at the labelled medians and sigma at the
    pooled moment std. The minority components absorb state-preparation errors (thermal |e>
    in the g shots, pi-pulse infidelity and decay in the e shots), so with
    d = |mu_e - mu_g| / sigma the result 2 Phi(-d/2) is the readout error of two equal
    Gaussians at a midpoint threshold with ideal preparation. It does not include prep
    errors, unlike 1 - contrast or 2 Phi(-snr_analog/2) from the moment stds.
    The minority components are kept only when they raise the joint log-likelihood by
    2 Delta lnL >= _MIXTURE_MIN_2DLNL (9) over the w_g = w_e = 0 fit (class means and the
    pooled ML std, i.e. the moment separation); otherwise that w = 0 fit gives d. Without this
    test a weakly separated pair can be fitted as a symmetric two-component mixture
    (w_g = w_e = 0.5) with a spurious d ~ 1: at d = 0 one point in ~13 read below 0.8. With
    1000 + 1000 shots and ideal prep (1000-10000 trials per d) the mean is within 0.02 of
    2 Phi(-d/2) at every d, only just at d = 0, where the fitted |d| > 0 biases it ~0.019 low
    (single-trial sd ~0.013 at d = 0, ~0.018 at d = 1, ~0.014 at d = 2, spurious fits
    excluded). The test still keeps a spurious mixture in ~0.05% of trials at d = 0 (reading
    0.41-0.48; the rest stay above ~0.91) and in 0.3-1% at d = 0.25-0.5 (reading 0.2-0.55
    low), so an isolated low point in a poorly separated region may be one. Prep error the test
    cannot resolve is kept: with 5% thermal g and 10% unexcited e it reads ~0.05 high at
    d = 1, ~0.035 high at d = 1.5 and is exact at d >= 2. Deterministic. NaN when a class
    has fewer than 2 shots, the medians or the stds vanish, or the fit is not finite.
    docs/experiments/readout_optimize.md#analysis."""
    i_g, q_g, i_e, q_e = (np.ravel(np.asarray(x, dtype=float)) for x in (i_g, q_g, i_e, q_e))
    if i_g.size < 2 or i_e.size < 2:
        return np.nan
    c_g = np.array([np.median(i_g), np.median(q_g)])
    c_e = np.array([np.median(i_e), np.median(q_e)])
    norm = float(np.hypot(*(c_e - c_g)))
    if not norm > 0:
        return np.nan
    axis = (c_e - c_g) / norm
    v_g = np.column_stack([i_g, q_g]) @ axis
    v_e = np.column_stack([i_e, q_e]) @ axis
    s0 = math.sqrt(0.5 * (np.var(v_g) + np.var(v_e)))
    if not s0 > 0:
        return np.nan
    # Work in units of the moment std about the median midpoint (the fit is scale-free).
    m0 = 0.5 * (np.median(v_g) + np.median(v_e))
    z_g, z_e = (v_g - m0) / s0, (v_e - m0) / s0
    log_norm = 0.5 * math.log(2 * math.pi)

    def nll(p):
        mu_g, mu_e, log_s, w_g, w_e = p
        s = math.exp(log_s)

        def mix_logpdf(z, mu_major, mu_minor, w):
            a = -0.5 * ((z - mu_major) / s) ** 2
            b = -0.5 * ((z - mu_minor) / s) ** 2
            with np.errstate(divide="ignore"):
                return np.logaddexp(np.log1p(-w) + a, np.log(w) + b) - log_s - log_norm

        return -(mix_logpdf(z_g, mu_g, mu_e, w_g).sum() + mix_logpdf(z_e, mu_e, mu_g, w_e).sum())

    p0 = [np.median(z_g), np.median(z_e), 0.0, 0.01, 0.01]
    bounds = [(None, None), (None, None), (-20.0, 5.0), (0.0, 0.5), (0.0, 0.5)]
    fit = scipy.optimize.minimize(nll, p0, method="L-BFGS-B", bounds=bounds)
    mu_g, mu_e, log_s = fit.x[:3]
    d = abs(mu_e - mu_g) / math.exp(log_s)
    if not (np.all(np.isfinite(fit.x)) and np.isfinite(fit.fun) and math.isfinite(d)):
        return np.nan
    # Nested w_g = w_e = 0 fit in closed form: class means and the pooled ML std.
    mu0_g, mu0_e = z_g.mean(), z_e.mean()
    s_0 = math.sqrt(
        (((z_g - mu0_g) ** 2).sum() + ((z_e - mu0_e) ** 2).sum()) / (z_g.size + z_e.size)
    )
    if 2.0 * (nll([mu0_g, mu0_e, math.log(s_0), 0.0, 0.0]) - fit.fun) < _MIXTURE_MIN_2DLNL:
        d = abs(mu0_e - mu0_g) / s_0
    return float(scipy.special.erfc(d / (2 * math.sqrt(2))))  # 2 Phi(-d/2)


def cdf_gap_threshold(v_g, v_e):
    """Exact empirical-CDF threshold for the 1-D rule g := v <= thr, e := v > thr.

    Returns ``(contrast, threshold)`` with contrast = max over thr of
    P(v_g <= thr) - P(v_e <= thr) (per-class normalised, so unequal class sizes are handled)
    and threshold = the midpoint of the first maximal plateau (between the maximising
    sample value and the next distinct sample value). The comparison uses integer counts,
    so the result does not depend on float rounding or on the order of the shots. If no
    threshold separates g below e the contrast is 0 and the threshold is the largest
    sample (every shot classed g; its contrast is exactly 0, so the pair stays
    self-consistent). NaN, NaN for an empty class."""
    v_g = np.sort(np.ravel(np.asarray(v_g, dtype=float)))
    v_e = np.sort(np.ravel(np.asarray(v_e, dtype=float)))
    n_g, n_e = v_g.size, v_e.size
    if n_g == 0 or n_e == 0:
        return np.nan, np.nan
    u = np.unique(np.concatenate([v_g, v_e]))
    c_g = np.searchsorted(v_g, u, side="right").astype(np.int64)
    c_e = np.searchsorted(v_e, u, side="right").astype(np.int64)
    score = c_g * n_e - c_e * n_g  # exact (n_g * n_e) * gap; gap(u[-1]) == 0
    best = score.max()
    k = int(np.argmax(score == best))
    if best <= 0:
        return np.float64(0.0), np.float64(u[-1])  # gap(u[-1]) == 0 exactly
    j = k
    while j + 1 < u.size and score[j + 1] == best:
        j += 1
    threshold = 0.5 * (u[k] + u[j + 1])  # j + 1 exists: score[-1] == 0 < best
    return np.float64(c_g[k] / n_g - c_e[k] / n_e), np.float64(threshold)


def hist_process(
    data=None,
    plot=True,
    ran=None,
    figNum=1,
    title="",
    alpha=0.5,
    normalize="pooled",
    print_fidelities=False,
):
    """Rotate g/e shots onto the median-to-median line and return (contrast, threshold, theta).

    Contrast and threshold come from the exact empirical CDFs of the rotated I values
    (``cdf_gap_threshold``; rule g := I <= threshold, the rule ``iq.count_percentage``
    applies), so ``fid`` is exactly the contrast the saved threshold achieves on these shots.
    The 200-bin histogram is drawn for the plot only. ``normalize`` accepts "pooled" and
    "per_class" for the callers' sake; both give the same numbers (per-class normalisation).
    docs/concepts/iq_conventions.md section 4."""
    if normalize not in ("pooled", "per_class"):
        raise ValueError(f"normalize must be 'pooled' or 'per_class', got {normalize!r}")
    per_class = normalize == "per_class"

    ig = data[0]
    qg = data[1]
    ie = data[2]
    qe = data[3]

    numbins = 200

    xg, yg = np.median(ig), np.median(qg)
    xe, ye = np.median(ie), np.median(qe)

    if plot:
        fig, axs = plt.subplots(nrows=1, ncols=3, figsize=(16, 8), num=figNum)

        fig.suptitle(title)

        axs[0].scatter(ig, qg, label="g", color="r", marker="*", alpha=alpha)
        axs[0].scatter(ie, qe, label="e", color="b", marker="*", alpha=alpha)
        axs[0].scatter(xg, yg, color="k", marker="o")
        axs[0].scatter(xe, ye, color="k", marker="o")
        axs[0].set_xlabel("I (a.u.)")
        axs[0].set_ylabel("Q (a.u.)")
        axs[0].legend(loc="upper right")
        axs[0].set_title("Unrotated")
        axs[0].axis("equal")
    theta = -np.arctan2((ye - yg), (xe - xg))
    ig_new = ig * np.cos(theta) - qg * np.sin(theta)
    qg_new = ig * np.sin(theta) + qg * np.cos(theta)
    ie_new = ie * np.cos(theta) - qe * np.sin(theta)
    qe_new = ie * np.sin(theta) + qe * np.cos(theta)

    fid, threshold = cdf_gap_threshold(ig_new, ie_new)
    ne_contrast = np.mean(np.asarray(ie_new) <= threshold)  # P(assigned g | prepared e)
    ng_contrast = np.mean(np.asarray(ig_new) > threshold)  # P(assigned e | prepared g)
    if print_fidelities:
        # The relocated per-class variant printed the pair twice; kept verbatim.
        for _ in range(2):
            print("ne contrast: ", ne_contrast)
            print("ng contrast: ", ng_contrast)

    if plot:
        xg, yg = np.median(ig_new), np.median(qg_new)
        xe, ye = np.median(ie_new), np.median(qe_new)

        if ran is None:
            xg_range = np.ptp(ig_new)
            xe_range = np.ptp(ie_new)
            if xg > xe:
                xlims = [xe - 0.6 * xe_range, xg + 0.6 * xg_range]
            else:
                xlims = [xg - 0.6 * xg_range, xe + 0.6 * xe_range]
        else:
            xlims = [xg - ran, xg + ran]

        axs[1].scatter(ig_new, qg_new, label="g", color="r", marker="*", alpha=alpha)
        axs[1].scatter(ie_new, qe_new, label="e", color="b", marker="*", alpha=alpha)
        axs[1].scatter(xg, yg, color="k", marker="o")
        axs[1].scatter(xe, ye, color="k", marker="o")
        axs[1].set_xlabel("I (a.u.)")
        axs[1].legend(loc="lower right")
        axs[1].set_title(f"Rotated; Angle = {theta:.3f}" if per_class else "Rotated")
        axs[1].axis("equal")

        axs[2].hist(ig_new, bins=numbins, range=xlims, color="r", label="g", alpha=0.5)
        axs[2].hist(ie_new, bins=numbins, range=xlims, color="b", label="e", alpha=0.5)
        axs[2].set_xlabel("I(a.u.)")
        axs[2].legend(loc="upper right")
        axs[2].axvline(threshold, 0, 20, color="black", alpha=0.7, ls="--")
        if per_class:
            axs[2].set_title(
                f"Fi: {fid * 100:.1f}%; Thr: {threshold:.1f}; ne: {ne_contrast:.2f}, ng: {ng_contrast:.2f}"
            )
        else:
            axs[2].set_title(f"Contrast C = {fid * 100:.2f}% (F_assign = {50 * (1 + fid):.2f}%)")

    return fid, threshold, theta


def _labelled_cloud_mixture(vg, ve, max_iter=300, tol=1e-8):
    """Joint 1-D two-Gaussian mixture of the projected labelled shots (EM, deterministic).

    Both sets share the components N(mu_g, s_g) and N(mu_e, s_e), with s_e / s_g held in
    _CLOUD_SIGMA_RATIO_BOUNDS; each set has its own e weight: w_g in [0, 0.5] for the g shots
    (thermal |e>), w_e in [0.02, 1] for the e shots (e-cloud purity). Seeds: the g-set moments,
    mu_e at the mean of the e shots above the raw-mean midpoint, w_e from the raw mean ratio
    (mean_e - mu_g) / (mu_e - mu_g), w_g = 0.01. Returns (params dict, log-likelihood) of the
    mixture and the log-likelihood of the pure fit (w_g = 0, w_e = 1) with each set's own
    unconstrained moments (the fallback clouds; its sigma ratio is NOT bounded); NaN values
    when either set has no finite positive variance (noise-free or non-finite shots)."""
    lo, hi = _CLOUD_SIGMA_RATIO_BOUNDS
    if not (float(np.var(vg)) > 0 and float(np.var(ve)) > 0):
        nan_params = dict.fromkeys(("mu_g", "mu_e", "s_g", "s_e", "w_g", "w_e"), np.nan)
        return nan_params, np.nan, np.nan
    log_norm = 0.5 * math.log(2 * math.pi)

    def logpdf(v, mu, s):
        return -0.5 * ((v - mu) / s) ** 2 - math.log(s) - log_norm

    def m_sigmas(n_g, ss_g, n_e, ss_e):
        # ML sigmas under lo <= s_e / s_g <= hi (concave in log s: clip, then refit s_g)
        var_g, var_e = ss_g / n_g, ss_e / n_e
        if not (var_g > 0 and var_e > 0):
            return math.sqrt(max(var_g, 0.0)), math.sqrt(max(var_e, 0.0))  # ends the EM
        ratio = math.sqrt(var_e / var_g)
        if lo <= ratio <= hi:
            return math.sqrt(var_g), math.sqrt(var_e)
        ratio = min(max(ratio, lo), hi)
        s_g = math.sqrt((ss_g + ss_e / ratio**2) / (n_g + n_e))
        return s_g, ratio * s_g

    # pure fit: every g shot in g, every e shot in e, with the UNCLIPPED per-set ML moments,
    # i.e. exactly the clouds the caller falls back to. A pure cloud whose sigma ratio lies
    # outside the bounds must not count as a mixture just because the bounded pure fit is worse.
    mu_g0, mu_e0 = float(vg.mean()), float(ve.mean())
    s_g0, s_e0 = float(vg.std()), float(ve.std())
    ll_pure = float(logpdf(vg, mu_g0, s_g0).sum() + logpdf(ve, mu_e0, s_e0).sum())

    mu_g, s_g = mu_g0, float(vg.std())
    upper = ve[ve > 0.5 * (mu_g0 + mu_e0)]
    mu_e = float(upper.mean()) if upper.size else mu_e0
    s_e = s_g
    w_g = 0.01
    w_e = min(max((mu_e0 - mu_g) / (mu_e - mu_g), 0.02), 0.98) if mu_e > mu_g else 0.5

    def e_step(mu_g, mu_e, s_g, s_e, w_g, w_e):
        resp, total = [], 0.0
        for v, w in ((vg, w_g), (ve, w_e)):
            a = math.log1p(-w) + logpdf(v, mu_g, s_g) if w < 1 else np.full(v.size, -np.inf)
            b = math.log(w) + logpdf(v, mu_e, s_e) if w > 0 else np.full(v.size, -np.inf)
            tot = np.logaddexp(a, b)
            total += float(tot.sum())
            resp.append(np.exp(b - tot))
        return resp, total

    ll = -np.inf
    for _ in range(max_iter):
        if not (s_g > 0 and s_e > 0 and math.isfinite(mu_g) and math.isfinite(mu_e)):
            break
        resp, ll_new = e_step(mu_g, mu_e, s_g, s_e, w_g, w_e)
        r_all = np.concatenate(resp)
        v_all = np.concatenate([vg, ve])
        n_e = float(r_all.sum())
        n_g = float(r_all.size - n_e)
        if n_e <= 1.0 or n_g <= 1.0:
            break
        mu_g = float(((1.0 - r_all) * v_all).sum() / n_g)
        mu_e = float((r_all * v_all).sum() / n_e)
        s_g, s_e = m_sigmas(
            n_g,
            float(((1.0 - r_all) * (v_all - mu_g) ** 2).sum()),
            n_e,
            float((r_all * (v_all - mu_e) ** 2).sum()),
        )
        w_g = min(max(float(resp[0].mean()), 0.0), 0.5)
        w_e = min(max(float(resp[1].mean()), 0.02), 1.0)
        converged = abs(ll_new - ll) < tol * r_all.size
        ll = ll_new
        if converged:
            break
    params = {"mu_g": mu_g, "mu_e": mu_e, "s_g": s_g, "s_e": s_e, "w_g": w_g, "w_e": w_e}
    if all(math.isfinite(x) for x in params.values()) and s_g > 0 and s_e > 0:
        ll = e_step(mu_g, mu_e, s_g, s_e, w_g, w_e)[1]  # at the returned parameters
    else:
        ll = np.nan
    return params, ll, ll_pure


def calibrate_readout_from_labeled_shots(I_g, Q_g, I_e, Q_e, use_lda=True):
    """
    Calibrate the IQ projection and discrimination stats from LABELED shots.

    Parameters
    ----------
    I_g, Q_g : array_like
        Single-shot I/Q with the qubit prepared in |g> (no pi pulse).
    I_e, Q_e : array_like
        Single-shot I/Q with the qubit prepared in |e> (pi pulse).
    use_lda : bool
        If True (default) the projection axis is the Fisher/LDA direction
        Sigma_pooled^-1 (mu_e - mu_g), which is optimal for Gaussian clouds
        with shared covariance. If False, the plain mean-difference axis
        (mu_e - mu_g) is used (identical when the noise is isotropic).

    Returns
    -------
    dict with keys:
      g_center, e_center     : (2,) cloud means in (I, Q)
      cov_g, cov_e           : (2, 2) cloud covariances
      axis                   : (2,) UNIT projection vector (points g -> e)
      midpoint               : (2,) projection origin (midpoint of centers)
      proj_g_mean, proj_e_mean, proj_g_sigma, proj_e_sigma : floats,
                               moments of the projected clouds (raw units)
      separation             : |proj_e_mean - proj_g_mean|
      snr_analog             : separation / sqrt(0.5*(sg^2 + se^2))
      threshold              : equal-priors optimal projected threshold
                               (maximizes empirical assignment accuracy)
      confusion_matrix       : (2, 2) rows = prepared (g, e), cols = assigned
                               (g, e); P(assign col | prepared row)
      contrast               : P(g|g) + P(e|e) - 1 == max|CDF_g - CDF_e|
                               (this is what legacy code prints as "Fidelity")
      assignment_fidelity    : (1 + contrast) / 2, equal priors
      max_cdf_gap            : identical to contrast, kept under the explicit
                               name so the legacy number is traceable
      e_above_threshold      : bool, True if the |e> cloud projects ABOVE the
                               threshold (orientation of the mapping)
      n_g, n_e               : shot counts used
      proj_g_mean_clean, proj_e_mean_clean, proj_g_sigma_clean, proj_e_sigma_clean :
                               the clouds of a joint two-Gaussian mixture fit of
                               both projected labelled sets (shared component
                               means and sigmas, sigma_e / sigma_g in
                               [0.8, 1.25], a separate e weight per set), used
                               only when it raises the joint log-likelihood by
                               2 Delta lnL >= 9 over the pure fit (each set's
                               own raw moments, sigma ratio unbounded);
                               otherwise the raw moments above
      snr_analog_clean       : snr_analog of the clean clouds
      prep_fidelity_e        : e weight of the e shots, the e-CLOUD PURITY
                               (pi-pulse prep error plus decay during readout,
                               which the MR readout shares); 1.0 when no
                               mixture is resolved, NaN on a fallback
      prep_excited_g         : e weight of the g shots (thermal |e> etc.)
      clean_cloud_source     : "mixture", "moments" (not significant, or not
                               computable: a set without positive variance) or
                               "moments_fallback" (e weight < 0.2 or clean
                               SNR < 1; warns)
      mixture_2dlnl          : 2 Delta lnL of the mixture over the pure fit
                               (can be negative: the pure fit's sigmas are free)
      readout_gate_warnings  : the readout gates (SNR < 1, contrast < 0.3,
                               < 500 shots per class)
      warnings               : list of str: the readout gates, then the
                               e-cloud warnings (purity < 0.9, fallback)
    docs/experiments/modified_ramsey.md#analysis.
    """
    I_g = np.ravel(np.asarray(I_g, dtype=float))
    Q_g = np.ravel(np.asarray(Q_g, dtype=float))
    I_e = np.ravel(np.asarray(I_e, dtype=float))
    Q_e = np.ravel(np.asarray(Q_e, dtype=float))
    if I_g.size != Q_g.size or I_e.size != Q_e.size:
        raise ValueError("I/Q length mismatch in labeled shots")
    if I_g.size < 10 or I_e.size < 10:
        raise ValueError(
            f"need >= 10 shots per state to calibrate, got n_g={I_g.size}, n_e={I_e.size}"
        )
    warnings = []

    g_pts = np.column_stack([I_g, Q_g])
    e_pts = np.column_stack([I_e, Q_e])
    g_center = g_pts.mean(axis=0)
    e_center = e_pts.mean(axis=0)
    cov_g = np.cov(g_pts, rowvar=False)
    cov_e = np.cov(e_pts, rowvar=False)

    diff = e_center - g_center
    if not np.any(np.abs(diff) > 0):
        raise ValueError("g and e cloud centers coincide; cannot define an axis")

    if use_lda:
        pooled = 0.5 * (cov_g + cov_e)
        # Regularize so a rank-deficient pooled covariance (e.g. synthetic
        # noise-free data) cannot blow up the solve.
        eps = 1e-12 * max(np.trace(pooled), 1e-300)
        axis = np.linalg.solve(pooled + eps * np.eye(2), diff)
    else:
        axis = diff.copy()
    axis = axis / np.linalg.norm(axis)
    # Canonical orientation: axis points from g toward e.
    if float(axis @ diff) < 0:
        axis = -axis
    midpoint = 0.5 * (g_center + e_center)

    vg = (g_pts - midpoint) @ axis
    ve = (e_pts - midpoint) @ axis
    proj_g_mean = float(vg.mean())
    proj_e_mean = float(ve.mean())
    proj_g_sigma = float(vg.std(ddof=1))
    proj_e_sigma = float(ve.std(ddof=1))
    separation = float(abs(proj_e_mean - proj_g_mean))
    pooled_sigma = math.sqrt(0.5 * (proj_g_sigma**2 + proj_e_sigma**2))
    snr_analog = separation / pooled_sigma if pooled_sigma > 0 else np.inf

    # Equal-priors optimal threshold: maximize |CDF_g(t) - CDF_e(t)| over the
    # pooled empirical sample. This IS the threshold the legacy hist analysis
    # optimizes; the number it prints is the max gap itself (the contrast).
    both = np.sort(np.concatenate([vg, ve]))
    cdf_g = np.searchsorted(np.sort(vg), both, side="right") / vg.size
    cdf_e = np.searchsorted(np.sort(ve), both, side="right") / ve.size
    gap = np.abs(cdf_g - cdf_e)
    k = int(np.argmax(gap))
    contrast = float(gap[k])
    threshold = float(both[k])

    e_above = proj_e_mean > proj_g_mean  # True by axis construction
    # Confusion matrix at the optimized threshold, equal priors.
    if e_above:
        p_gg = float(np.mean(vg <= threshold))
        p_ee = float(np.mean(ve > threshold))
    else:  # pragma: no cover - axis is canonically oriented g -> e
        p_gg = float(np.mean(vg > threshold))
        p_ee = float(np.mean(ve <= threshold))
    confusion = np.array([[p_gg, 1.0 - p_gg], [1.0 - p_ee, p_ee]])
    assignment_fidelity = 0.5 * (1.0 + contrast)

    if snr_analog < 1.0:
        warnings.append(
            f"analog SNR {snr_analog:.2f} < 1: clouds barely separated; "
            "single-shot parity mapping will be dominated by readout noise"
        )
    if contrast < 0.3:
        warnings.append(
            f"readout contrast {contrast:.3f} < 0.3: parity trace will be "
            "heavily mixed; treat rate estimates with caution"
        )
    n_min = min(I_g.size, I_e.size)
    if n_min < 500:
        warnings.append(
            f"only {n_min} labeled shots in the smaller class; threshold and "
            "confusion-matrix estimates are coarse"
        )
    readout_gate_warnings = list(warnings)

    # Clean clouds: the e shots of a detuned or bandwidth-limited pi pulse are a g/e mixture
    # (plus decay during readout), which biases proj_e_mean toward g, inflates proj_e_sigma
    # and understates snr_analog. A joint mixture fit of both labelled sets separates them.
    mix, ll_mix, ll_pure = _labelled_cloud_mixture(vg, ve)
    mixture_2dlnl = 2.0 * (ll_mix - ll_pure)
    clean = (proj_g_mean, proj_e_mean, proj_g_sigma, proj_e_sigma)
    prep_fidelity_e, prep_excited_g = 1.0, 0.0
    if not mixture_2dlnl >= _MIXTURE_MIN_2DLNL:  # not significant, or not computable (NaN)
        clean_source = "moments"  # no resolvable mixture: the clean clouds are the moments
    else:
        sep_mix = mix["mu_e"] - mix["mu_g"]
        snr_mix = sep_mix / math.sqrt(0.5 * (mix["s_g"] ** 2 + mix["s_e"] ** 2))
        if not (mix["w_e"] >= _CLOUD_MIN_E_PURITY and snr_mix >= 1.0):
            clean_source = "moments_fallback"
            prep_fidelity_e = prep_excited_g = np.nan
            warnings.append(
                f"e-cloud mixture fit unresolved (e weight {mix['w_e']:.2f}, clean SNR "
                f"{snr_mix:.2f}): the clean clouds fall back to the raw moments"
            )
        else:
            clean_source = "mixture"
            clean = (mix["mu_g"], mix["mu_e"], mix["s_g"], mix["s_e"])
            prep_fidelity_e, prep_excited_g = mix["w_e"], mix["w_g"]
    pooled_clean = math.sqrt(0.5 * (clean[2] ** 2 + clean[3] ** 2))
    snr_analog_clean = abs(clean[1] - clean[0]) / pooled_clean if pooled_clean > 0 else np.inf
    if prep_fidelity_e < _CLOUD_WARN_E_PURITY:
        warnings.append(
            f"e-cloud purity {prep_fidelity_e:.2f} < {_CLOUD_WARN_E_PURITY}: the pi-prepared shots "
            "are a g/e mixture (pi-pulse infidelity, e.g. detuned from the parity branches, plus "
            f"decay during readout); clean analog SNR {snr_analog_clean:.2f} vs raw "
            f"{snr_analog:.2f}"
        )

    return {
        "g_center": g_center,
        "e_center": e_center,
        "cov_g": cov_g,
        "cov_e": cov_e,
        "axis": axis,
        "midpoint": midpoint,
        "proj_g_mean": proj_g_mean,
        "proj_e_mean": proj_e_mean,
        "proj_g_sigma": proj_g_sigma,
        "proj_e_sigma": proj_e_sigma,
        "separation": separation,
        "snr_analog": float(snr_analog),
        "threshold": threshold,
        "confusion_matrix": confusion,
        "contrast": contrast,
        "max_cdf_gap": contrast,
        "assignment_fidelity": float(assignment_fidelity),
        "e_above_threshold": bool(e_above),
        "n_g": int(I_g.size),
        "n_e": int(I_e.size),
        "use_lda": bool(use_lda),
        "proj_g_mean_clean": float(clean[0]),
        "proj_e_mean_clean": float(clean[1]),
        "proj_g_sigma_clean": float(clean[2]),
        "proj_e_sigma_clean": float(clean[3]),
        "snr_analog_clean": float(snr_analog_clean),
        "prep_fidelity_e": float(prep_fidelity_e),
        "prep_excited_g": float(prep_excited_g),
        "clean_cloud_source": clean_source,
        "mixture_2dlnl": float(mixture_2dlnl),
        "readout_gate_warnings": readout_gate_warnings,
        "warnings": warnings,
    }


def readout_assignment_errors(i_g, q_g, i_e, q_e, angle, threshold):
    """(P(e|g), P(g|e)) of single_shot calibration shots, counted exactly as T1_SS counts:
    rotate by ``angle`` (rotate_data) and call a shot excited when I' > threshold.

    These include the prep errors of the calibration (thermal |e> in the g shots, pi-pulse
    infidelity and decay during readout in the e shots), not only the readout overlap
    (docs/experiments/t1_single_shot.md#analysis). NaN for an empty set.
    """
    out = []
    for i, q, excited in ((i_g, q_g, False), (i_e, q_e, True)):
        i_rot, _ = rotate_data((np.ravel(i), np.ravel(q)), theta=angle)
        if i_rot.size == 0:
            out.append(float("nan"))
            continue
        frac_e = float(np.mean(i_rot > threshold))
        out.append(1.0 - frac_e if excited else frac_e)
    return tuple(out)


def single_shot_figures_of_merit(i_g, q_g, i_e, q_e, contrast, threshold, angle):
    """Readout figures of merit of one g/e single_shot read, saved per read in its h5.

    ``contrast``, ``threshold``, ``angle`` are the hist_process outputs (the saved pair).
    P_e_given_g / P_g_given_e are counted at that pair by readout_assignment_errors (the
    helper run_t1_ss uses, so both agree bit for bit) and assignment_fidelity =
    1 - (P_e_given_g + P_g_given_e)/2 = (1 + contrast)/2. snr_analog, cal_* and
    readout_gate_pass come from calibrate_readout_from_labeled_shots (mean/LDA axis, its own
    threshold relative to cal_midpoint); gate pass = none of its readout-gate warnings (SNR < 1,
    contrast < 0.3, fewer than 500 shots in a class), the gates the parity analysis uses; its
    e-cloud purity warnings are returned with them but do not fail the gate. Those are NaN
    when it raises (fewer than 10 shots per class, coincident centres). Returns
    (dict key -> value, list of warnings). docs/experiments/single_shot.md#outputs."""
    i_g, q_g, i_e, q_e = (np.ravel(np.asarray(x, dtype=float)) for x in (i_g, q_g, i_e, q_e))
    p_e_given_g, p_g_given_e = readout_assignment_errors(i_g, q_g, i_e, q_e, angle, threshold)
    fom = {
        "contrast_hist": contrast,
        "assignment_fidelity": 1.0 - 0.5 * (p_e_given_g + p_g_given_e),
        "P_e_given_g": p_e_given_g,
        "P_g_given_e": p_g_given_e,
        "g_center_median": np.array([np.median(i_g), np.median(q_g)]),
        "e_center_median": np.array([np.median(i_e), np.median(q_e)]),
        "g_center_mean": np.array([np.mean(i_g), np.mean(q_g)]),
        "e_center_mean": np.array([np.mean(i_e), np.mean(q_e)]),
    }
    try:
        cal = calibrate_readout_from_labeled_shots(i_g, q_g, i_e, q_e)
    except Exception as err:
        cal = None
        warnings = [f"labelled-shot calibration failed: {err}"]
    if cal is None:
        fom.update(
            snr_analog=np.nan,
            cal_contrast=np.nan,
            cal_threshold=np.nan,
            cal_axis=np.full(2, np.nan),
            cal_midpoint=np.full(2, np.nan),
            readout_gate_pass=np.nan,
        )
    else:
        warnings = list(cal["warnings"])
        fom.update(
            snr_analog=cal["snr_analog"],
            cal_contrast=cal["contrast"],
            cal_threshold=cal["threshold"],
            cal_axis=cal["axis"],
            cal_midpoint=cal["midpoint"],
            readout_gate_pass=float(not cal["readout_gate_warnings"]),
        )
    return fom, warnings


def project_iq_trace(I, Q, calibration):
    """
    Project an (I, Q) record onto the calibrated axis. Returns the analog
    trace v (same length, raw units, midpoint-referenced). No thresholding.
    """
    I = np.ravel(np.asarray(I, dtype=float))
    Q = np.ravel(np.asarray(Q, dtype=float))
    if I.size != Q.size:
        raise ValueError("I and Q must have the same length")
    axis = np.asarray(calibration["axis"], dtype=float)
    midpoint = np.asarray(calibration["midpoint"], dtype=float)
    return (np.column_stack([I, Q]) - midpoint) @ axis


def calibrate_readout_from_record(I, Q, random_state=0):
    """Readout calibration from an UNLABELLED record: a two-component Gaussian mixture of
    the record's own shots, for a record taken without a SingleShot calibration on its
    scale (the quasi-CW raw accumulator sums, docs/experiments/charge_dispersion.md#analysis).

    The more populated component is called g, so the record's mean P(e) is ``w_e`` <= 0.5.
    Returns the calibrate_readout_from_labeled_shots keys that project_iq_trace and
    analyze_modified_ramsey_record use (LDA axis g -> e, midpoint, projected cloud moments,
    separation, snr_analog, the equal-priors threshold / contrast / confusion matrix of the
    two fitted Gaussians), plus ``w_e`` and ``clean_cloud_source`` = "record_mixture".
    There are no labelled clouds, so no "_clean" keys: the fitted components are the clouds.
    """
    from sklearn.mixture import GaussianMixture  # third-party; local like kmeans_split's

    I = np.ravel(np.asarray(I, dtype=float))
    Q = np.ravel(np.asarray(Q, dtype=float))
    if I.size != Q.size:
        raise ValueError("I and Q must have the same length")
    pts = np.column_stack([I, Q])
    pts = pts[np.all(np.isfinite(pts), axis=1)]
    if pts.shape[0] < 10:
        raise ValueError(f"need >= 10 finite shots to self-calibrate, got {pts.shape[0]}")

    gm = GaussianMixture(
        n_components=2, covariance_type="full", random_state=random_state, n_init=5
    ).fit(pts)
    g_idx = int(np.argmax(gm.weights_))
    e_idx = 1 - g_idx
    g_center, e_center = gm.means_[g_idx], gm.means_[e_idx]
    cov_g, cov_e = gm.covariances_[g_idx], gm.covariances_[e_idx]
    w_e = float(gm.weights_[e_idx])

    diff = e_center - g_center
    if not np.any(np.abs(diff) > 0):
        raise ValueError("the two mixture components coincide; cannot define an axis")
    pooled = 0.5 * (cov_g + cov_e)
    eps = 1e-12 * max(np.trace(pooled), 1e-300)
    axis = np.linalg.solve(pooled + eps * np.eye(2), diff)
    axis = axis / np.linalg.norm(axis)
    if float(axis @ diff) < 0:
        axis = -axis
    midpoint = 0.5 * (g_center + e_center)

    proj_g_mean = float((g_center - midpoint) @ axis)
    proj_e_mean = float((e_center - midpoint) @ axis)
    proj_g_sigma = float(np.sqrt(axis @ cov_g @ axis))
    proj_e_sigma = float(np.sqrt(axis @ cov_e @ axis))
    separation = float(abs(proj_e_mean - proj_g_mean))
    pooled_sigma = math.sqrt(0.5 * (proj_g_sigma**2 + proj_e_sigma**2))
    snr_analog = separation / pooled_sigma if pooled_sigma > 0 else np.inf

    # equal-priors threshold of the two fitted Gaussians: max |CDF_g - CDF_e|
    lo = min(proj_g_mean - 5 * proj_g_sigma, proj_e_mean - 5 * proj_e_sigma)
    hi = max(proj_g_mean + 5 * proj_g_sigma, proj_e_mean + 5 * proj_e_sigma)
    grid = np.linspace(lo, hi, 4001)
    cdf_g = scipy.special.ndtr((grid - proj_g_mean) / proj_g_sigma)
    cdf_e = scipy.special.ndtr((grid - proj_e_mean) / proj_e_sigma)
    k = int(np.argmax(cdf_g - cdf_e))
    threshold = float(grid[k])
    p_gg, p_ee = float(cdf_g[k]), float(1.0 - cdf_e[k])
    contrast = p_gg + p_ee - 1.0
    confusion = np.array([[p_gg, 1.0 - p_gg], [1.0 - p_ee, p_ee]])

    warnings = [
        "readout self-calibrated from the record (no labelled shots): the g/e clouds come "
        "from an unlabelled two-Gaussian fit of the same shots, the more populated cloud "
        "taken as g"
    ]
    if snr_analog < 1.0:
        warnings.append(
            f"analog SNR {snr_analog:.2f} < 1: clouds barely separated; "
            "single-shot parity mapping will be dominated by readout noise"
        )
    if contrast < 0.3:
        warnings.append(
            f"readout contrast {contrast:.3f} < 0.3: parity trace will be "
            "heavily mixed; treat rate estimates with caution"
        )
    n = pts.shape[0]
    return {
        "g_center": g_center,
        "e_center": e_center,
        "cov_g": cov_g,
        "cov_e": cov_e,
        "axis": axis,
        "midpoint": midpoint,
        "proj_g_mean": proj_g_mean,
        "proj_e_mean": proj_e_mean,
        "proj_g_sigma": proj_g_sigma,
        "proj_e_sigma": proj_e_sigma,
        "separation": separation,
        "snr_analog": float(snr_analog),
        "threshold": threshold,
        "confusion_matrix": confusion,
        "contrast": float(contrast),
        "max_cdf_gap": float(contrast),
        "assignment_fidelity": float(0.5 * (1.0 + contrast)),
        "e_above_threshold": True,
        "n_g": int(round(n * (1.0 - w_e))),
        "n_e": int(round(n * w_e)),
        "use_lda": True,
        "w_e": w_e,
        "clean_cloud_source": "record_mixture",
        "readout_gate_warnings": warnings[1:],
        "warnings": warnings,
    }


def classify_thermal_tail(i_th, q_th, cfg, read_index):
    """Tail classifier for undriven shots (``number_of_pulses`` = 0): MinCovDet main blob,
    Mahalanobis tail, one-sided protrusion threshold. A failed fit does not raise (all labels 0).
    Method and defaults: docs/concepts/iq_conventions.md section 7.

    Its labels are for the scatter plot only. ``tail_fraction`` (the fraction labelled 1) is NOT an
    estimate of the excited population: with isotropic noise, N = 2000, md2 6.0 and k = 2.5 it
    reads about 1 % at zero population (the protrusion axis is picked from the farthest 5 % of
    points, so the floor exceeds Q(2.5) = 0.62 %), and below a g-e separation of about 4 sigma most
    excited shots fall under the threshold (true 0/1/3/10 % -> about 1.0/1.2/1.5/2.7 % at
    d = 2 sigma, 1.1/1.8/3.8/10.9 % at d = 5 sigma). Use ``fit_thermal_population``."""
    iq = np.column_stack([i_th, q_th])

    try:
        from sklearn.covariance import MinCovDet

        mcd = MinCovDet(support_fraction=0.75, random_state=0).fit(iq)
        center_g = mcd.location_
        cov_g = mcd.covariance_
        inv_cov_g = np.linalg.pinv(cov_g)

        diff = iq - center_g
        md2 = np.einsum("ij,jk,ik->i", diff, inv_cov_g, diff)

        tail_md2_threshold = cfg.get("thermal_tail_md2_threshold", 6.0)
        tail_candidates = md2 > tail_md2_threshold

        n_tail_seed = max(10, int(0.05 * len(iq)))
        far_idx = np.argsort(md2)[-n_tail_seed:]
        center_e_seed = np.mean(iq[far_idx], axis=0)

        axis = center_e_seed - center_g
        axis_norm = np.linalg.norm(axis)

        if axis_norm < 1e-12:
            raise RuntimeError("Could not determine thermal protrusion axis.")

        axis = axis / axis_norm

        proj = diff @ axis

        proj_main = proj[~tail_candidates]
        if len(proj_main) < 10:
            proj_main = proj

        med_proj = np.median(proj_main)
        mad_proj = np.median(np.abs(proj_main - med_proj))
        sigma_proj = 1.4826 * mad_proj

        if sigma_proj <= 1e-12:
            sigma_proj = np.std(proj_main)

        tail_sigma_threshold = cfg.get("thermal_tail_sigma_threshold", 2.5)
        threshold_proj = med_proj + tail_sigma_threshold * sigma_proj

        binary_states = (proj > threshold_proj).astype(int)

        tail_fraction = float(np.mean(binary_states))

        i_g = i_th[binary_states == 0]
        q_g = q_th[binary_states == 0]
        i_e = i_th[binary_states == 1]
        q_e = q_th[binary_states == 1]

        center_e = np.array(
            [
                np.mean(i_e) if len(i_e) > 0 else np.nan,
                np.mean(q_e) if len(q_e) > 0 else np.nan,
            ]
        )

        angle = -np.arctan2(axis[1], axis[0])
        threshold = center_g[0] * np.cos(angle) - center_g[1] * np.sin(angle) + threshold_proj

        fid = np.nan

        print(
            f"[Thermal protrusion] Read {read_index}: "
            f"tail_fraction={tail_fraction:.5f}, "
            f"N_excited={np.sum(binary_states)}, "
            f"threshold_proj={threshold_proj:.4f}, "
            f"sigma_proj={sigma_proj:.4f}, "
            f"angle={angle:.4f}"
        )

    except Exception as err:
        print(f"[SingleShot thermal mode] protrusion fit failed: {err}")

        binary_states = np.zeros(len(i_th), dtype=int)
        tail_fraction = np.nan
        angle = 0.0
        threshold = np.nan
        fid = np.nan

        i_g = i_th
        q_g = q_th
        i_e = np.array([])
        q_e = np.array([])

        center_g = np.array([np.nan, np.nan])
        center_e = np.array([np.nan, np.nan])
        md2 = np.full(len(i_th), np.nan)
        proj = np.full(len(i_th), np.nan)
        threshold_proj = np.nan

    return {
        "i_g": i_g,
        "q_g": q_g,
        "i_e": i_e,
        "q_e": q_e,
        "labels": binary_states,
        "tail_fraction": tail_fraction,
        "center_g": center_g,
        "center_e": center_e,
        "md2": md2,
        "projection": proj,
        "projection_threshold": threshold_proj,
        "angle": angle,
        "threshold": threshold,
        "fid": fid,
    }


def _gauss_logpdf(pts, center, inv_cov, logdet):
    d = pts - center
    return -0.5 * np.einsum("ij,jk,ik->i", d, inv_cov, d) - math.log(2 * math.pi) - 0.5 * logdet


def _em_shared_cov(sets, weights, g_center, e_center, cov, fit_e, max_iter, tol):
    """EM for (1 - q_k) N(g, cov) + q_k N(e, cov) over the shot sets k, one weight q_k per set and
    one shared covariance; e is held fixed unless fit_e. Returns (weights, g, e, cov, log
    likelihood, n_iter, converged)."""
    X = np.vstack(sets)
    weights = list(weights)
    ll_old = -np.inf
    ll = -np.inf
    converged = False
    n_iter = 0
    for n_iter in range(1, max_iter + 1):
        inv_cov = np.linalg.inv(cov)
        logdet = np.linalg.slogdet(cov)[1]
        resp = []
        ll = 0.0
        for pts, q in zip(sets, weights):
            q = min(max(q, 1e-300), 1.0 - 1e-16)
            a = math.log1p(-q) + _gauss_logpdf(pts, g_center, inv_cov, logdet)
            b = math.log(q) + _gauss_logpdf(pts, e_center, inv_cov, logdet)
            m = np.logaddexp(a, b)
            ll += float(m.sum())
            resp.append(np.exp(b - m))
        weights = [float(r.mean()) for r in resp]
        R = np.concatenate(resp)
        g_center = ((1.0 - R)[:, None] * X).sum(axis=0) / (1.0 - R).sum()
        if fit_e:
            e_center = (R[:, None] * X).sum(axis=0) / R.sum()
        dg = X - g_center
        de = X - e_center
        cov = (
            np.einsum("i,ij,ik->jk", 1.0 - R, dg, dg) + np.einsum("i,ij,ik->jk", R, de, de)
        ) / len(X)
        if ll - ll_old < tol * abs(ll):
            converged = True
            break
        ll_old = ll
    return weights, g_center, e_center, cov, ll, n_iter, converged


def fit_thermal_population(
    i_th,
    q_th,
    i_pi=None,
    q_pi=None,
    e_center=None,
    max_iter=5000,
    tol=1e-10,
    min_contrast_z=4.0,
    max_width_ratio=1.05,
):
    """Maximum-likelihood excited (thermal) population of undriven single shots.

    Model: every shot is drawn from (1 - q) N(g_center, cov) + q N(e_center, cov) with one shared
    (pooled) covariance; q = p for the undriven shots ``(i_th, q_th)`` and q = w for the labelled
    pi-pulse shots ``(i_pi, q_pi)``. The two sets are fitted jointly by EM, started both from
    p = 0.05, w = 0.9 and from a KMeans 2-cluster split of the pooled shots (the higher likelihood
    wins, so p near w, e.g. p ~ 0.5, still resolves; |e> is the state the pi pulse populates,
    w > p): the undriven shots pin g_center, the pi shots pin e_center, and each set's own
    weight absorbs its contamination (thermal population in the g set, pi infidelity and decay in
    the e set), so neither labelled set is used as a template. Without pi shots, ``e_center`` (an
    (I, Q) pair from an earlier calibration) is held fixed and g_center, cov and p are fitted from
    the undriven shots alone; with neither, p is NaN (``source`` = "none") and a warning is
    returned. With the components fixed at the EM result, p is then solved exactly (the log
    likelihood is concave in p: root of its score on [0, 1]). ``population_err`` is the standard
    error of p from the outer-product-of-scores information over all fitted parameters (weights,
    centres, covariance), so it includes the uncertainty of the centres.

    Undetermined fits return NaN for population, population_err, pi_population, e_width_ratio,
    g_center, e_center and cov (the labels may be mirrored), with a warning that gives the
    unguarded p and w; separation_sigma, pi_contrast and pi_contrast_err are kept to show why:
    g-e separation below 1 sigma, or, with pi shots, a pi contrast w - p below
    ``min_contrast_z`` (default 4) times its standard error, i.e. the pi pulse did not measurably
    move the populations of this read, so the data cannot say which cloud is |e>. This is
    normally the case for every read of a multiplexed run except the driven qubit's (the pi shots
    are then a second undriven cloud), for an off-resonant pi pulse, and near p = 0.5, where a pi
    pulse swaps nearly equal populations (w = F(1 - p) + (1 - F)p ~ p). The guard cannot tell a
    pi pulse from any other change between the two sets: if a non-driven read's second cloud
    moved (readout drift, cross-Kerr/ZZ to the driven qubit) the fit can return a finite,
    meaningless p with no warning (synthetic d = 3 sigma, p = 3 %, 2000 + 2000 shots, 20 seeds:
    finite in 0/20 unshifted, 1-4/20 at a 0.3-0.5 sigma shift, 14-16/20 at 1 sigma, where the
    shifted cloud is taken as |e>). Only the driven qubit's read is a population.

    Synthetic check (isotropic sigma = 1 for both states, N = 2000 undriven + 2000 pi shots at
    90 % fidelity, random rotation, d = 2/3/5 sigma, p = 0/1/3/10 %; and p = 0.45 with a 95 % pi
    pulse, where w - p ~ 0.1): unbiased within the SE. The SE is 0.86-0.94 of the trial-to-trial
    scatter of p (30-100 seeds, d = 1.5-2 sigma, p = 10 %) and within ~5 % of the
    observed-information SE (inverse numerical Hessian over all 9 parameters); scoring the
    weights alone would understate it by ~25-45 % (tests/test_thermal_population.py).

    Model bias, unequal widths: the shared covariance assumes the e cloud is as wide as the g
    cloud. If it is wider (measurement-induced transitions, long windows), the excess width is
    absorbed into g and p is biased LOW; if narrower, HIGH. N = 2000 + 2000, w = 0.9, 6 seeds:
    sigma_e = 1.2 sigma_g gives p = 3 % -> 1.9/2.6/3.1 % and 10 % -> 7.0/8.7/9.9 % at
    d = 2/3/5 sigma; 1.5 sigma_g gives 3 % -> 1.2/1.8/2.7 %; 0.8 sigma_g gives 0 % -> 3.2/0.6/0.0 %
    and 3 % -> 7.3/4.6/3.4 %. Diagnostic: ``e_width_ratio`` = (det Sigma_e / det Sigma_g)^(1/4) of
    the responsibility-weighted component covariances at the fit (0.99 +- 0.013 for equal widths;
    it reads closer to 1 than the truth: 1.2 reads 1.10-1.17, 1.5 reads 1.21-1.41, 0.8 reads
    0.80-0.86). A warning is added when |ln ratio| exceeds both ln(``max_width_ratio``) (default
    1.05) and 4 standard errors (0.5 sqrt(1/n_e + 1/n_g)).

    Model bias, T1 decay: decay during the readout window smears excited shots toward g. The fixed
    two-Gaussian model assigns part of the smear to g, so p is biased LOW. If a fraction P_dec of
    excited shots decays at a uniform time within the window (the same in both runs), p comes out
    low by about 0.5-0.9 x P_dec in relative terms (P_dec 0.1: -3 to -11 %; 0.2: -11 to -17 %,
    up to -27 % at d = 2 sigma and p = 3 %; 0.3: -16 to -28 %). The pi-run weight w is low by a
    similar amount. The smear barely moves ``e_width_ratio`` (1.00-1.05 for P_dec <= 0.3), so the
    width warning does not flag it.

    Returns a dict: population, population_err, pi_population (w; NaN without pi shots),
    e_width_ratio (NaN without pi shots), g_center, e_center, cov (all NaN when undetermined, see
    above), pi_contrast and pi_contrast_err (w - p of the unguarded fit and its SE; NaN without pi
    shots), separation_sigma (Mahalanobis g-e distance), n_iter, converged,
    source ("pi_shots", "cfg_e_center" or "none"), warnings (list of str).
    """
    und = np.column_stack(
        [np.ravel(np.asarray(i_th, dtype=float)), np.ravel(np.asarray(q_th, dtype=float))]
    )
    out = {
        "population": np.nan,
        "population_err": np.nan,
        "pi_population": np.nan,
        "pi_contrast": np.nan,
        "pi_contrast_err": np.nan,
        "e_width_ratio": np.nan,
        "g_center": np.full(2, np.nan),
        "e_center": np.full(2, np.nan),
        "cov": np.full((2, 2), np.nan),
        "separation_sigma": np.nan,
        "n_iter": 0,
        "converged": False,
        "source": "none",
        "warnings": [],
    }
    if i_pi is not None and q_pi is not None:
        pi = np.column_stack(
            [np.ravel(np.asarray(i_pi, dtype=float)), np.ravel(np.asarray(q_pi, dtype=float))]
        )
        out["source"] = "pi_shots"
    elif e_center is not None:
        pi = None
        e_fixed = np.ravel(np.asarray(e_center, dtype=float))
        if e_fixed.shape != (2,):
            raise ValueError(f"e_center must be an (I, Q) pair, got shape {e_fixed.shape}")
        out["source"] = "cfg_e_center"
    else:
        out["warnings"].append(
            "no labelled |e> reference (pi shots or e_center): thermal population not estimated; "
            "the tail fraction is not a population"
        )
        return out
    if len(und) < 10 or (pi is not None and len(pi) < 10):
        raise ValueError("need >= 10 undriven shots and >= 10 pi shots")

    sets = [und] if pi is None else [und, pi]
    X = np.vstack(sets)
    g0 = np.median(und, axis=0)
    cov0 = np.cov(und, rowvar=False)
    if pi is None:
        starts = [([0.05], g0, e_fixed, cov0)]
    else:
        # Start 1: mean(pi) - mean(und) = (w - p)(e - g), taking w - p = 0.85. This fails when the
        # pi pulse barely changes the populations (e.g. p ~ 0.5), so also start from a 2-cluster
        # split of the pooled shots (e = the cluster enriched in the pi shots) and keep the start
        # with the higher likelihood.
        starts = [([0.05, 0.9], g0, g0 + (pi.mean(axis=0) - und.mean(axis=0)) / 0.85, cov0)]
        lab = KMeans(n_clusters=2, random_state=0, n_init=10).fit_predict(X)
        lab_und, lab_pi = lab[: len(und)], lab[len(und) :]
        e_lab = int(np.mean(lab_pi == 1) > np.mean(lab_und == 1))  # pi-enriched cluster
        if np.all(np.bincount(lab, minlength=2) >= 2):
            c_g, c_e = X[lab != e_lab].mean(axis=0), X[lab == e_lab].mean(axis=0)
            within = np.where((lab == e_lab)[:, None], X - c_e, X - c_g)
            starts.append(
                (
                    [
                        float(np.clip(np.mean(lab_und == e_lab), 0.01, 0.99)),
                        float(np.clip(np.mean(lab_pi == e_lab), 0.01, 0.99)),
                    ],
                    c_g,
                    c_e,
                    within.T @ within / len(X),
                )
            )
    best = None
    for start in starts:
        res = _em_shared_cov(sets, *start, fit_e=pi is not None, max_iter=max_iter, tol=tol)
        if best is None or res[4] > best[4]:
            best = res
    weights, g_center, e_center_fit, cov, _, n_iter, converged = best
    if pi is not None and weights[1] < weights[0]:
        # The likelihood is symmetric under g <-> e with q -> 1 - q; |e> is by definition the
        # state the pi pulse populates.
        weights = [1.0 - q for q in weights]
        g_center, e_center_fit = e_center_fit, g_center
    if not converged:
        out["warnings"].append(f"EM did not converge in {max_iter} iterations")

    inv_cov = np.linalg.inv(cov)
    logdet = np.linalg.slogdet(cov)[1]
    lg = np.exp(_gauss_logpdf(und, g_center, inv_cov, logdet))
    le = np.exp(_gauss_logpdf(und, e_center_fit, inv_cov, logdet))
    diff = le - lg

    def score(q):
        return float(np.sum(diff / ((1.0 - q) * lg + q * le)))

    if score(0.0) <= 0:
        p = 0.0
    elif score(1.0) >= 0:
        p = 1.0
    else:
        p = float(scipy.optimize.brentq(score, 0.0, 1.0, xtol=1e-12))

    # Outer product of per-shot scores over (p, [w], g_center, [e_center], cov entries).
    blocks = []
    for k, (pts, q) in enumerate(zip(sets, [p] + weights[1:])):
        log_g = _gauss_logpdf(pts, g_center, inv_cov, logdet)
        log_e = _gauss_logpdf(pts, e_center_fit, inv_cov, logdet)
        with np.errstate(divide="ignore"):
            log_mix = np.logaddexp(np.log1p(-q) + log_g, np.log(q) + log_e)
            r = np.exp(np.log(q) + log_e - log_mix)
        cols = [
            np.exp(log_e - log_mix) - np.exp(log_g - log_mix) if j == k else np.zeros(len(pts))
            for j in range(len(sets))
        ]
        ug = (pts - g_center) @ inv_cov
        ue = (pts - e_center_fit) @ inv_cov
        cols += [(1.0 - r) * ug[:, 0], (1.0 - r) * ug[:, 1]]
        if pi is not None:
            cols += [r * ue[:, 0], r * ue[:, 1]]
        gmat = 0.5 * (
            (1.0 - r)[:, None, None] * np.einsum("ij,ik->ijk", ug, ug)
            + r[:, None, None] * np.einsum("ij,ik->ijk", ue, ue)
            - inv_cov[None]
        )
        cols += [gmat[:, 0, 0], gmat[:, 1, 1], 2.0 * gmat[:, 0, 1]]
        blocks.append(np.column_stack(cols))
    S = np.vstack(blocks)
    p_err = contrast_err = np.nan
    try:
        V = np.linalg.inv(S.T @ S)
        p_err = math.sqrt(V[0, 0]) if V[0, 0] > 0 else np.nan
        if pi is not None:
            var_c = V[0, 0] + V[1, 1] - 2.0 * V[0, 1]
            contrast_err = math.sqrt(var_c) if var_c > 0 else np.nan
    except np.linalg.LinAlgError:
        pass

    sep = e_center_fit - g_center
    separation_sigma = float(math.sqrt(max(float(sep @ inv_cov @ sep), 0.0)))
    reason = None
    if separation_sigma < 1.0:
        reason = f"g-e separation {separation_sigma:.2f} sigma < 1"
    elif pi is not None and not weights[1] - p >= min_contrast_z * contrast_err:
        reason = (
            f"the pi pulse moved only {100 * (weights[1] - p):.1f} +- {100 * contrast_err:.1f} % "
            f"of the shots to e (< {min_contrast_z:g} SE): this read's qubit was not driven, the "
            "pi pulse is off, or p ~ 0.5"
        )
    out.update(
        pi_contrast=float(weights[1] - p) if pi is not None else np.nan,
        pi_contrast_err=contrast_err,
        separation_sigma=separation_sigma,
        n_iter=n_iter,
        converged=converged,
    )
    if reason is not None:
        # Every fitted quantity is undetermined (and g/e may be mirrored): only the diagnostics
        # that explain why (separation, pi contrast) are returned.
        w_txt = f", pi-run excited {100 * weights[1]:.1f} %" if pi is not None else ""
        out["warnings"].append(
            f"{reason}: population, pi-run weight and fitted centres undetermined, saved as NaN "
            f"(unguarded fit p = {100 * p:.3f} %{w_txt})"
        )
        return out
    if pi is not None and weights[1] < 0.5:
        out["warnings"].append(
            f"only {100 * weights[1]:.1f} % of the pi-pulse shots fit as excited: check the pi pulse"
        )

    # Shared-covariance check: responsibility-weighted width of each component at the fit. A
    # wider e cloud biases p low, a narrower one high (docstring).
    width_ratio = np.nan
    if pi is not None:
        resp = []
        for pts, q in zip(sets, [p, weights[1]]):
            with np.errstate(divide="ignore"):
                a = np.log1p(-q) + _gauss_logpdf(pts, g_center, inv_cov, logdet)
                b = np.log(q) + _gauss_logpdf(pts, e_center_fit, inv_cov, logdet)
            resp.append(np.exp(b - np.logaddexp(a, b)))
        R = np.concatenate(resp)
        n_e, n_g = float(R.sum()), float((1.0 - R).sum())
        if n_e > 2 and n_g > 2:
            dg, de = X - g_center, X - e_center_fit
            cov_g = np.einsum("i,ij,ik->jk", 1.0 - R, dg, dg) / n_g
            cov_e = np.einsum("i,ij,ik->jk", R, de, de) / n_e
            width_ratio = float((np.linalg.det(cov_e) / np.linalg.det(cov_g)) ** 0.25)
            ln_se = 0.5 * math.sqrt(1.0 / n_e + 1.0 / n_g)
            if abs(math.log(width_ratio)) > max(math.log(max_width_ratio), 4.0 * ln_se):
                out["warnings"].append(
                    f"the e cloud is {width_ratio:.3f} x as wide as the g cloud (fitted "
                    "components), but the model assumes one shared covariance: p is biased "
                    f"{'low' if width_ratio > 1 else 'high'}, most at small g-e separation "
                    f"(here {separation_sigma:.1f} sigma)"
                )

    out.update(
        population=p,
        population_err=p_err,
        pi_population=float(weights[1]) if pi is not None else np.nan,
        e_width_ratio=width_ratio,
        g_center=g_center,
        e_center=e_center_fit,
        cov=cov,
    )
    return out
