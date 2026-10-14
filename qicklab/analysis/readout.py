"""Single-shot readout analysis: g/e histogram contrast (hist_process), KMeans blob overlap
(MixedShots), labelled-shot calibration and IQ-trace projection.
Conventions and the meaning of "fidelity": docs/concepts/iq_conventions.md."""

import math

import matplotlib.pyplot as plt
import numpy as np
import scipy.optimize
from sklearn.cluster import KMeans


class MixedShots:
    """KMeans-split a mixed g/e shot cloud, rotate the centre line onto I and fit two Gaussians
    to the I histogram. ``OverlapErr`` = Gaussian overlap area / smaller blob area (NaN when the
    overlap exceeds 90% of either blob). Not deterministic: KMeans has no random_state."""

    def __init__(self, shots_i, shots_q, ran=None, numbins=200):
        self.i_raw = shots_i
        self.q_raw = shots_q

        iqData = np.stack((shots_i, shots_q), axis=1)

        self.kmeans = KMeans(n_clusters=2, n_init=5, max_iter=1000).fit(iqData)

        Centers = self.kmeans.cluster_centers_
        self.cen1 = Centers[0]
        self.cen2 = Centers[1]

        self._SeperateBlobs()
        self._Rotate()

        if ran is None:
            ran = np.ptp(self.i_rot) * 0.05

        self.ran = ran

        self.iRange = [np.min(self.i_rot) - self.ran, np.max(self.i_rot) + self.ran]

        self.nMixed, self.binsMixed = np.histogram(self.i_rot, bins=numbins, range=self.iRange)

        self.nBlob1, self.binsBlob1 = np.histogram(self.i_blob1, bins=numbins, range=self.iRange)

        self.nBlob2, self.binsBlob2 = np.histogram(self.i_blob2, bins=numbins, range=self.iRange)

        self._DoubleGausFit()

    def _SeperateBlobs(self):
        blobNums = self.kmeans.labels_
        empty = np.array([])
        i_raw = np.asarray(self.i_raw)
        q_raw = np.asarray(self.q_raw)
        self.i_blob1 = np.append(empty, i_raw[blobNums == 0])
        self.q_blob1 = np.append(empty, q_raw[blobNums == 0])
        self.i_blob2 = np.append(empty, i_raw[blobNums == 1])
        self.q_blob2 = np.append(empty, q_raw[blobNums == 1])

        distArr1 = np.zeros(len(self.i_blob1))
        distArr2 = np.zeros(len(self.i_blob2))

        for i in range(len(self.i_blob1)):
            distArr1[i] = np.sqrt(
                (self.cen1[0] - self.i_blob1[i]) ** 2 + (self.cen1[1] - self.q_blob1[i]) ** 2
            )
        for i in range(len(self.i_blob2)):
            distArr2[i] = np.sqrt(
                (self.cen2[0] - self.i_blob2[i]) ** 2 + (self.cen2[1] - self.q_blob2[i]) ** 2
            )

        self.blob1_avgSize = np.mean(distArr1)
        self.blob2_avgSize = np.mean(distArr2)

    def _Rotate(self):
        self.theta = -np.arctan((self.cen2[1] - self.cen1[1]) / (self.cen2[0] - self.cen1[0]))
        theta = self.theta

        self.i_rot = self.i_raw * np.cos(theta) - self.q_raw * np.sin(theta)
        self.q_rot = self.i_raw * np.sin(theta) + self.q_raw * np.cos(theta)

        self.cen1_rot = np.copy(self.cen1)
        self.cen1_rot[0] = self.cen1[0] * np.cos(theta) - self.cen1[1] * np.sin(theta)
        self.cen1_rot[1] = self.cen1[0] * np.sin(theta) + self.cen1[1] * np.cos(theta)

        self.cen2_rot = np.copy(self.cen2)
        self.cen2_rot[0] = self.cen2[0] * np.cos(theta) - self.cen2[1] * np.sin(theta)
        self.cen2_rot[1] = self.cen2[0] * np.sin(theta) + self.cen2[1] * np.cos(theta)

        self.i_blob1_rot = self.i_blob1 * np.cos(theta) - self.q_blob1 * np.sin(theta)
        self.q_blob1_rot = self.i_blob1 * np.sin(theta) + self.q_blob1 * np.cos(theta)

        self.i_blob2_rot = self.i_blob2 * np.cos(theta) - self.q_blob2 * np.sin(theta)
        self.q_blob2_rot = self.i_blob2 * np.sin(theta) + self.q_blob2 * np.cos(theta)

    def _DoubleGausFit(self):
        amp1 = np.max(self.nBlob1)
        cen1 = self.cen1_rot[0]
        sig1 = self.blob1_avgSize
        amp2 = np.max(self.nBlob2)
        cen2 = self.cen2_rot[0]
        sig2 = self.blob2_avgSize

        self.FitX = np.linspace(self.iRange[0], self.iRange[1], 500)

        P0 = [amp1, cen1, sig1, amp2, cen2, sig2]

        def _gaussian(x, amp, cen, sig):
            return (
                amp
                * (1 / (sig * (np.sqrt(2 * np.pi))))
                * (np.exp((-1.0 / 2.0) * (((x - cen) / sig) ** 2)))
            )

        def _2gaussian(x, amp1, cen1, sig1, amp2, cen2, sig2):
            return amp1 * (1 / (sig1 * (np.sqrt(2 * np.pi)))) * (
                np.exp((-1.0 / 2.0) * (((x - cen1) / sig1) ** 2))
            ) + amp2 * (1 / (sig2 * (np.sqrt(2 * np.pi)))) * (
                np.exp((-1.0 / 2.0) * (((x - cen2) / sig2) ** 2))
            )

        try:
            self.popt_gauss2, self.pcov_gauss2 = scipy.optimize.curve_fit(
                _2gaussian, self.binsMixed[0:-1], self.nMixed, p0=P0
            )
        except RuntimeError:
            print("Error - curve_fit failed")
            self.popt_gauss2 = (1, 1, 1, 1, 1, 1)
            self.pcov_gauss2 = (1, 1, 1, 1, 1, 1)

        self.perr_gauss2 = np.sqrt(np.diag(self.pcov_gauss2))

        self.DoubleGaussFit = _2gaussian(self.FitX, *self.popt_gauss2)
        self.Blob1GaussFit = _gaussian(self.FitX, *self.popt_gauss2[0:3])
        self.Blob2GaussFit = _gaussian(self.FitX, *self.popt_gauss2[3:6])

        self.OverlapFit = np.zeros(len(self.FitX))
        self.OverlapFit[:] = np.minimum(self.Blob1GaussFit, self.Blob2GaussFit)

        self.Blob1_area = np.trapezoid(self.Blob1GaussFit, self.FitX)
        self.Blob2_area = np.trapezoid(self.Blob2GaussFit, self.FitX)
        Overlap_area = np.trapezoid(self.OverlapFit, self.FitX)
        self.Overlap_area = Overlap_area
        self.OverlapErr = np.max([Overlap_area / self.Blob1_area, Overlap_area / self.Blob2_area])

        if self.Overlap_area / self.Blob1_area > 0.9:
            self.OverlapErr = math.nan

        if self.Overlap_area / self.Blob2_area > 0.9:
            self.OverlapErr = math.nan


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
    """Rotate g/e shots onto the median-to-median line, histogram I (200 bins) and return
    (contrast, threshold bin edge, theta). normalize="pooled" (single_shot) or "per_class"
    (readout_optimize); they give different numbers: docs/concepts/iq_conventions.md section 4."""
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

    if plot:
        axs[1].scatter(ig_new, qg_new, label="g", color="r", marker="*", alpha=alpha)
        axs[1].scatter(ie_new, qe_new, label="e", color="b", marker="*", alpha=alpha)
        axs[1].scatter(xg, yg, color="k", marker="o")
        axs[1].scatter(xe, ye, color="k", marker="o")
        axs[1].set_xlabel("I (a.u.)")
        axs[1].legend(loc="lower right")
        axs[1].set_title(f"Rotated; Angle = {theta:.3f}" if per_class else "Rotated")
        axs[1].axis("equal")

        ng, binsg, pg = axs[2].hist(
            ig_new, bins=numbins, range=xlims, color="r", label="g", alpha=0.5
        )
        ne, binse, pe = axs[2].hist(
            ie_new, bins=numbins, range=xlims, color="b", label="e", alpha=0.5
        )
        axs[2].set_xlabel("I(a.u.)")
        axs[2].legend(loc="upper right")

    else:
        ng, binsg = np.histogram(ig_new, bins=numbins, range=xlims)
        ne, binse = np.histogram(ie_new, bins=numbins, range=xlims)

    if per_class:
        contrast = np.cumsum(ng) / ng.sum() - np.cumsum(ne) / ne.sum()
    else:
        contrast = np.abs((np.cumsum(ng) - np.cumsum(ne)) / (0.5 * ng.sum() + 0.5 * ne.sum()))
    tind = contrast.argmax()
    threshold = binsg[tind]
    fid = contrast[tind]
    if per_class or print_fidelities:
        ne_contrast = np.cumsum(ne)[tind] / ne.sum()
        ng_contrast = 1 - np.cumsum(ng)[tind] / ng.sum()
    if print_fidelities:
        # The relocated per-class variant printed the pair twice; kept verbatim.
        for _ in range(2):
            print("ne contrast: ", ne_contrast)
            print("ng contrast: ", ng_contrast)

    if plot:
        if per_class:
            axs[2].axvline(threshold, 0, 20, color="black", alpha=0.7, ls="--")
            axs[2].set_title(
                f"Fi: {fid * 100:.1f}%; Thr: {threshold:.1f}; ne: {ne_contrast:.2f}, ng: {ng_contrast:.2f}"
            )
        else:
            axs[2].set_title(f"Fidelity = {fid * 100:.2f}%")

    return fid, threshold, theta


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
      warnings               : list of str
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
        "warnings": warnings,
    }


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
