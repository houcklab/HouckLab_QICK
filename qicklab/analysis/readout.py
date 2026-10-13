#####  Class for taking in mixed state single shot data and finding the
##### blob seperation and fits

import math

import matplotlib.pyplot as plt
import numpy as np
import scipy

# import statsmodells.api as sm
from sklearn.cluster import KMeans


class MixedShots:
    def __init__(self, shots_i, shots_q, ran=None, numbins=200):
        ### take in raw data, rotate, split into groups
        ### create gaussian fits and store information

        ### store the data
        self.i_raw = shots_i
        self.q_raw = shots_q

        iqData = np.stack((shots_i, shots_q), axis=1)

        ### partition data into two cluster
        self.kmeans = KMeans(n_clusters=2, n_init=5, max_iter=1000).fit(iqData)

        ### pull out the centers of the clusters
        Centers = self.kmeans.cluster_centers_
        self.cen1 = Centers[0]
        self.cen2 = Centers[1]

        self._SeperateBlobs()
        self._Rotate()

        ### create histogram of data
        if ran == None:
            ran = np.ptp(self.i_rot) * 0.05

        self.ran = ran

        ### first find the range to use
        self.iRange = [np.min(self.i_rot) - self.ran, np.max(self.i_rot) + self.ran]

        self.nMixed, self.binsMixed = np.histogram(self.i_rot, bins=numbins, range=self.iRange)

        self.nBlob1, self.binsBlob1 = np.histogram(self.i_blob1, bins=numbins, range=self.iRange)

        self.nBlob2, self.binsBlob2 = np.histogram(self.i_blob2, bins=numbins, range=self.iRange)

        self._DoubleGausFit()

    def _SeperateBlobs(self):
        ### create arrays for each blob
        blobNums = self.kmeans.labels_
        self.i_blob1 = np.array([])
        self.q_blob1 = np.array([])
        self.i_blob2 = np.array([])
        self.q_blob2 = np.array([])

        for i in range(len(blobNums)):
            if blobNums[i] == 0:
                self.i_blob1 = np.append(self.i_blob1, self.i_raw[i])
                self.q_blob1 = np.append(self.q_blob1, self.q_raw[i])
            if blobNums[i] == 1:
                self.i_blob2 = np.append(self.i_blob2, self.i_raw[i])
                self.q_blob2 = np.append(self.q_blob2, self.q_raw[i])

                ### find the size of each blob
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
        ### create rotated data
        self.theta = -np.arctan((self.cen2[1] - self.cen1[1]) / (self.cen2[0] - self.cen1[0]))
        theta = self.theta

        self.i_rot = self.i_raw * np.cos(theta) - self.q_raw * np.sin(theta)
        self.q_rot = self.i_raw * np.sin(theta) + self.q_raw * np.cos(theta)

        ### rotate the blob centers
        self.cen1_rot = np.copy(self.cen1)
        self.cen1_rot[0] = self.cen1[0] * np.cos(theta) - self.cen1[1] * np.sin(theta)
        self.cen1_rot[1] = self.cen1[0] * np.sin(theta) + self.cen1[1] * np.cos(theta)

        self.cen2_rot = np.copy(self.cen2)
        self.cen2_rot[0] = self.cen2[0] * np.cos(theta) - self.cen2[1] * np.sin(theta)
        self.cen2_rot[1] = self.cen2[0] * np.sin(theta) + self.cen2[1] * np.cos(theta)

        ### rotate the seperated data
        self.i_blob1_rot = self.i_blob1 * np.cos(theta) - self.q_blob1 * np.sin(theta)
        self.q_blob1_rot = self.i_blob1 * np.sin(theta) + self.q_blob1 * np.cos(theta)

        self.i_blob2_rot = self.i_blob2 * np.cos(theta) - self.q_blob2 * np.sin(theta)
        self.q_blob2_rot = self.i_blob2 * np.sin(theta) + self.q_blob2 * np.cos(theta)

    def _DoubleGausFit(self):
        ### create a double gaussian fit to the histogram data
        amp1 = np.max(self.nBlob1)
        cen1 = self.cen1_rot[0]
        sig1 = self.blob1_avgSize
        amp2 = np.max(self.nBlob2)
        cen2 = self.cen2_rot[0]
        sig2 = self.blob2_avgSize

        self.FitX = np.linspace(self.iRange[0], self.iRange[1], 500)

        P0 = [amp1, cen1, sig1, amp2, cen2, sig2]

        #### define gaussian functions
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

        #### perform fit to the data
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

        #### find the overlap of the two
        self.OverlapFit = np.zeros(len(self.FitX))

        for i in range(len(self.FitX)):
            self.OverlapFit[i] = np.min([self.Blob1GaussFit[i], self.Blob2GaussFit[i]])

        #### find the areas of the histograms and compute error
        self.Blob1_area = np.trapezoid(self.Blob1GaussFit, self.FitX)
        self.Blob2_area = np.trapezoid(self.Blob2GaussFit, self.FitX)
        Overlap_area = np.trapezoid(self.OverlapFit, self.FitX)
        self.Overlap_area = Overlap_area
        self.OverlapErr = np.max([Overlap_area / self.Blob1_area, Overlap_area / self.Blob2_area])

        if self.Overlap_area / self.Blob1_area > 0.9:
            self.OverlapErr = math.nan

        if self.Overlap_area / self.Blob2_area > 0.9:
            self.OverlapErr = math.nan

    def PlotRaw(self, figNum=1):
        plt.figure(figNum)
        plt.scatter(self.i_raw, self.q_raw, alpha=0.5)
        plt.xlabel("I (AU)")
        plt.ylabel("Q (AU)")
        plt.title("Raw IQ data")

    def PlotRot(self, figNum=2):
        plt.figure(figNum)
        plt.scatter(self.i_rot, self.q_rot, alpha=0.5)
        plt.plot(self.cen1_rot[0], self.cen1_rot[1], "kx", markersize=10)
        plt.plot(self.cen2_rot[0], self.cen2_rot[1], "kx", markersize=10)
        plt.xlabel("I (AU)")
        plt.ylabel("Q (AU)")
        plt.title("Roted IQ data")

    def PlotSorted(self, figNum=3):
        plt.figure(figNum)
        plt.scatter(self.i_blob1, self.q_blob1, alpha=0.5)
        plt.scatter(self.i_blob2, self.q_blob2, alpha=0.5)
        plt.plot(self.cen1[0], self.cen1[1], "kx", markersize=10)
        plt.plot(self.cen2[0], self.cen2[1], "kx", markersize=10)
        plt.xlabel("I (AU)")
        plt.ylabel("Q (AU)")
        plt.title("Sorted IQ data")

    def PlotCounts(self, figNum=4):
        plt.figure(figNum)
        plt.plot(self.binsMixed[0:-1], self.nMixed, "o")
        plt.ylabel("counts")
        plt.xlabel("I (AU)")
        plt.title("Histogram Counts")

    def PlotGaussFit(self, figNum=5):
        ### plot the data
        plt.figure(figNum)
        plt.plot(self.binsMixed[0:-1], self.nMixed)
        plt.plot(self.FitX, self.DoubleGaussFit)
        plt.plot(self.FitX, self.Blob1GaussFit)
        plt.plot(self.FitX, self.Blob2GaussFit)
        plt.fill_between(self.FitX, 0, self.OverlapFit, alpha=0.5)
        plt.ylabel("counts")
        plt.xlabel("I (AU)")
        plt.title("Histogram Data Fit")

        #### for diagnostic purposes print out the parameters
        # fitVal = ["%.2f"  % i for i in self.popt_gauss2]
        # print('blob1, amp: '+fitVal[0]+', cen:'+fitVal[1]+', std:'+fitVal[2])
        # print('blob2, amp: '+fitVal[3]+', cen:'+fitVal[4]+', std:'+fitVal[5])


def hist_process(data=None, plot=True, ran=None, figNum=1, title="", alpha=0.5):
    ig = data[0]
    qg = data[1]
    ie = data[2]
    qe = data[3]

    numbins = 200

    xg, yg = np.median(ig), np.median(qg)
    xe, ye = np.median(ie), np.median(qe)

    if plot == True:
        fig, axs = plt.subplots(nrows=1, ncols=3, figsize=(16, 8), num=figNum)

        # fig.tight_layout()
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
    """Compute the rotation angle"""
    theta = -np.arctan2((ye - yg), (xe - xg))
    """Rotate the IQ data"""
    ig_new = ig * np.cos(theta) - qg * np.sin(theta)
    qg_new = ig * np.sin(theta) + qg * np.cos(theta)
    ie_new = ie * np.cos(theta) - qe * np.sin(theta)
    qe_new = ie * np.sin(theta) + qe * np.cos(theta)

    """New means of each blob"""
    xg, yg = np.median(ig_new), np.median(qg_new)
    xe, ye = np.median(ie_new), np.median(qe_new)

    # print(xg, xe)

    if ran == None:
        xg_range = np.ptp(ig_new)
        xe_range = np.ptp(ie_new)
        if xg > xe:
            xlims = [xe - 0.6 * xe_range, xg + 0.6 * xg_range]
        else:
            xlims = [xg - 0.6 * xg_range, xe + 0.6 * xe_range]
    else:
        xlims = [xg - ran, xg + ran]
        ylims = [yg - ran, yg + ran]

    if plot == True:
        axs[1].scatter(ig_new, qg_new, label="g", color="r", marker="*", alpha=alpha)
        axs[1].scatter(ie_new, qe_new, label="e", color="b", marker="*", alpha=alpha)
        axs[1].scatter(xg, yg, color="k", marker="o")
        axs[1].scatter(xe, ye, color="k", marker="o")
        axs[1].set_xlabel("I (a.u.)")
        axs[1].legend(loc="lower right")
        axs[1].set_title("Rotated")
        axs[1].axis("equal")

        """X and Y ranges for histogram"""

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

    """Compute the fidelity using overlap of the histograms"""
    contrast = np.abs(((np.cumsum(ng) - np.cumsum(ne)) / (0.5 * ng.sum() + 0.5 * ne.sum())))
    tind = contrast.argmax()
    threshold = binsg[tind]
    fid = contrast[tind]
    if plot == True:
        axs[2].set_title(f"Fidelity = {fid * 100:.2f}%")

    return fid, threshold, theta


def hist_process_per_class(
    data=None, plot=True, ran=None, figNum=1, title="", alpha=0.5, print_fidelities=True
):
    ig = data[0]
    qg = data[1]
    ie = data[2]
    qe = data[3]

    numbins = 200

    xg, yg = np.median(ig), np.median(qg)
    xe, ye = np.median(ie), np.median(qe)

    if plot == True:
        fig, axs = plt.subplots(nrows=1, ncols=3, figsize=(16, 8), num=figNum)

        # fig.tight_layout()
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
    """Compute the rotation angle"""
    theta = -np.arctan2((ye - yg), (xe - xg))
    """Rotate the IQ data"""
    ig_new = ig * np.cos(theta) - qg * np.sin(theta)
    qg_new = ig * np.sin(theta) + qg * np.cos(theta)
    ie_new = ie * np.cos(theta) - qe * np.sin(theta)
    qe_new = ie * np.sin(theta) + qe * np.cos(theta)

    """New means of each blob"""
    xg, yg = np.median(ig_new), np.median(qg_new)
    xe, ye = np.median(ie_new), np.median(qe_new)

    # print(xg, xe)

    if ran == None:
        xg_range = np.ptp(ig_new)
        xe_range = np.ptp(ie_new)
        if xg > xe:
            xlims = [xe - 0.6 * xe_range, xg + 0.6 * xg_range]
        else:
            xlims = [xg - 0.6 * xg_range, xe + 0.6 * xe_range]
    else:
        xlims = [xg - ran, xg + ran]
        ylims = [yg - ran, yg + ran]

    if plot == True:
        axs[1].scatter(ig_new, qg_new, label="g", color="r", marker="*", alpha=alpha)
        axs[1].scatter(ie_new, qe_new, label="e", color="b", marker="*", alpha=alpha)
        axs[1].scatter(xg, yg, color="k", marker="o")
        axs[1].scatter(xe, ye, color="k", marker="o")
        axs[1].set_xlabel("I (a.u.)")
        axs[1].legend(loc="lower right")
        axs[1].set_title(f"Rotated; Angle = {theta:.3f}")
        axs[1].axis("equal")

        """X and Y ranges for histogram"""

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

    """Compute the fidelity using overlap of the histograms"""
    # contrast = np.abs(((np.cumsum(ng) - np.cumsum(ne)) / (0.5 * ng.sum() + 0.5 * ne.sum())))
    contrast = np.cumsum(ng) / ng.sum() - np.cumsum(ne) / ne.sum()

    tind = contrast.argmax()
    threshold = binsg[tind]
    fid = contrast[tind]
    ne_contrast = np.cumsum(ne)[tind] / ne.sum()
    ng_contrast = 1 - np.cumsum(ng)[tind] / ng.sum()
    if print_fidelities:
        print("ne contrast: ", np.cumsum(ne)[tind] / ne.sum())
        print("ng contrast: ", 1 - np.cumsum(ng)[tind] / ng.sum())
        print("ne contrast: ", ne_contrast)
        print("ng contrast: ", ng_contrast)

    if plot == True:
        axs[2].axvline(threshold, 0, 20, color="black", alpha=0.7, ls="--")

        # axs[2].set_title(f"Fidelity = {fid * 100:.2f}%; Thresh: {threshold:.3f}")
        axs[2].set_title(
            f"Fi: {fid * 100:.1f}%; Thr: {threshold:.1f}; ne: {ne_contrast:.2f}, ng: {ng_contrast:.2f}"
        )

    return fid, threshold, theta


# =========================================================================
# 1. Readout calibration from labeled g/e shots
# =========================================================================
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
