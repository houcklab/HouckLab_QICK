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
    """Thermal-population classifier for undriven shots (``number_of_pulses`` = 0): MinCovDet main
    blob, Mahalanobis tail, one-sided protrusion threshold. A failed fit does not raise (all labels
    0). Method and defaults: docs/concepts/iq_conventions.md section 7."""
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

        thermal_population = float(np.mean(binary_states))

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
            f"P_excited_tail={thermal_population:.5f}, "
            f"N_excited={np.sum(binary_states)}, "
            f"threshold_proj={threshold_proj:.4f}, "
            f"sigma_proj={sigma_proj:.4f}, "
            f"angle={angle:.4f}"
        )

    except Exception as err:
        print(f"[SingleShot thermal mode] protrusion fit failed: {err}")

        binary_states = np.zeros(len(i_th), dtype=int)
        thermal_population = np.nan
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
        "population": thermal_population,
        "center_g": center_g,
        "center_e": center_e,
        "md2": md2,
        "projection": proj,
        "projection_threshold": threshold_proj,
        "angle": angle,
        "threshold": threshold,
        "fid": fid,
    }
