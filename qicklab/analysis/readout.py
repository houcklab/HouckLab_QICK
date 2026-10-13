#####  Class for taking in mixed state single shot data and finding the
##### blob seperation and fits

import math

import matplotlib.pyplot as plt
import numpy as np
import scipy
# import statsmodells.api as sm
from sklearn.cluster import KMeans


class MixedShots:
    def __init__(self, shots_i, shots_q, ran=None,numbins=200):
        ### take in raw data, rotate, split into groups
        ### create gaussian fits and store information

        ### store the data
        self.i_raw = shots_i
        self.q_raw = shots_q

        iqData = np.stack((shots_i, shots_q), axis=1)

        ### partition data into two cluster
        self.kmeans = KMeans(
            n_clusters=2, n_init=5, max_iter=1000).fit(iqData)

        ### pull out the centers of the clusters
        Centers = self.kmeans.cluster_centers_
        self.cen1 = Centers[0]
        self.cen2 = Centers[1]

        self._SeperateBlobs()
        self._Rotate()

        ### create histogram of data
        if ran == None:
            ran = np.ptp(self.i_rot)*0.05

        self.ran = ran

        ### first find the range to use
        self.iRange = [np.min(self.i_rot) - self.ran, np.max(self.i_rot) + self.ran]

        self.nMixed, self.binsMixed = np.histogram(
            self.i_rot, bins=numbins, range=self.iRange)

        self.nBlob1, self.binsBlob1 = np.histogram(
            self.i_blob1, bins=numbins, range=self.iRange)

        self.nBlob2, self.binsBlob2 = np.histogram(
            self.i_blob2, bins=numbins, range=self.iRange)

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
                (self.cen1[0] - self.i_blob1[i]) ** 2 +
                (self.cen1[1] - self.q_blob1[i]) ** 2)
        for i in range(len(self.i_blob2)):
            distArr2[i] = np.sqrt(
                (self.cen2[0] - self.i_blob2[i]) ** 2 +
                (self.cen2[1] - self.q_blob2[i]) ** 2)

        self.blob1_avgSize = np.mean(distArr1)
        self.blob2_avgSize = np.mean(distArr2)

    def _Rotate(self):
        ### create rotated data
        self.theta = -np.arctan(
            (self.cen2[1] - self.cen1[1]) / (self.cen2[0] - self.cen1[0]))
        theta = self.theta

        self.i_rot = self.i_raw * np.cos(theta) - self.q_raw * np.sin(theta)
        self.q_rot = self.i_raw * np.sin(theta) + self.q_raw * np.cos(theta)

        ### rotate the blob centers
        self.cen1_rot = np.copy(self.cen1)
        self.cen1_rot[0] = (
                self.cen1[0] * np.cos(theta) - self.cen1[1] * np.sin(theta))
        self.cen1_rot[1] = (
                self.cen1[0] * np.sin(theta) + self.cen1[1] * np.cos(theta))

        self.cen2_rot = np.copy(self.cen2)
        self.cen2_rot[0] = (
                self.cen2[0] * np.cos(theta) - self.cen2[1] * np.sin(theta))
        self.cen2_rot[1] = (
                self.cen2[0] * np.sin(theta) + self.cen2[1] * np.cos(theta))

        ### rotate the seperated data
        self.i_blob1_rot = (
                self.i_blob1 * np.cos(theta) - self.q_blob1 * np.sin(theta))
        self.q_blob1_rot = (
                self.i_blob1 * np.sin(theta) + self.q_blob1 * np.cos(theta))

        self.i_blob2_rot = (
                self.i_blob2 * np.cos(theta) - self.q_blob2 * np.sin(theta))
        self.q_blob2_rot = (
                self.i_blob2 * np.sin(theta) + self.q_blob2 * np.cos(theta))


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
            return amp * (1 / (sig * (np.sqrt(2 * np.pi)))) * (
                np.exp((-1.0 / 2.0) * (((x - cen) / sig) ** 2)))

        def _2gaussian(x, amp1, cen1, sig1, amp2, cen2, sig2):
            return amp1 * (1 / (sig1 * (np.sqrt(2 * np.pi)))) * (
                np.exp((-1.0 / 2.0) * (((x - cen1) / sig1) ** 2))) + \
                   amp2 * (1 / (sig2 * (np.sqrt(2 * np.pi)))) * (
                       np.exp((-1.0 / 2.0) * (((x - cen2) / sig2) ** 2)))

        #### perform fit to the data
        try:
            self.popt_gauss2, self.pcov_gauss2 = scipy.optimize.curve_fit(_2gaussian, self.binsMixed[0:-1], self.nMixed, p0=P0)
        except RuntimeError:
            print("Error - curve_fit failed")
            self.popt_gauss2 = (1,1,1,1,1,1)
            self.pcov_gauss2 = (1,1,1,1,1,1)

        self.perr_gauss2 = np.sqrt(np.diag(self.pcov_gauss2))

        self.DoubleGaussFit = _2gaussian(self.FitX, *self.popt_gauss2)
        self.Blob1GaussFit = _gaussian(self.FitX, *self.popt_gauss2[0:3])
        self.Blob2GaussFit = _gaussian(self.FitX, *self.popt_gauss2[3:6])

        #### find the overlap of the two
        self.OverlapFit = np.zeros(len(self.FitX))

        for i in range(len(self.FitX)):
            self.OverlapFit[i] = np.min(
                [self.Blob1GaussFit[i], self.Blob2GaussFit[i]])

        #### find the areas of the histograms and compute error
        self.Blob1_area = np.trapezoid(self.Blob1GaussFit, self.FitX)
        self.Blob2_area = np.trapezoid(self.Blob2GaussFit, self.FitX)
        Overlap_area = np.trapezoid(self.OverlapFit, self.FitX)
        self.Overlap_area = Overlap_area
        self.OverlapErr = np.max(
            [Overlap_area / self.Blob1_area, Overlap_area / self.Blob2_area])

        if self.Overlap_area/self.Blob1_area >0.9:
            self.OverlapErr = math.nan

        if self.Overlap_area/self.Blob2_area > 0.9:
            self.OverlapErr = math.nan

    def PlotRaw(self, figNum = 1):
        plt.figure(figNum)
        plt.scatter(self.i_raw, self.q_raw, alpha=0.5)
        plt.xlabel('I (AU)')
        plt.ylabel('Q (AU)')
        plt.title('Raw IQ data')

    def PlotRot(self, figNum = 2):
        plt.figure(figNum)
        plt.scatter(self.i_rot, self.q_rot, alpha=0.5)
        plt.plot(self.cen1_rot[0], self.cen1_rot[1],
                 'kx', markersize=10)
        plt.plot(self.cen2_rot[0], self.cen2_rot[1],
                 'kx', markersize=10)
        plt.xlabel('I (AU)')
        plt.ylabel('Q (AU)')
        plt.title('Roted IQ data')

    def PlotSorted(self, figNum = 3):
        plt.figure(figNum)
        plt.scatter(self.i_blob1, self.q_blob1, alpha=0.5)
        plt.scatter(self.i_blob2, self.q_blob2, alpha=0.5)
        plt.plot(self.cen1[0], self.cen1[1],
                 'kx', markersize=10)
        plt.plot(self.cen2[0], self.cen2[1],
                 'kx', markersize=10)
        plt.xlabel('I (AU)')
        plt.ylabel('Q (AU)')
        plt.title('Sorted IQ data')

    def PlotCounts(self, figNum = 4):
        plt.figure(figNum)
        plt.plot(self.binsMixed[0:-1], self.nMixed, 'o')
        plt.ylabel('counts')
        plt.xlabel('I (AU)')
        plt.title('Histogram Counts')

    def PlotGaussFit(self, figNum = 5):
        ### plot the data
        plt.figure(figNum)
        plt.plot(self.binsMixed[0:-1], self.nMixed)
        plt.plot(self.FitX, self.DoubleGaussFit)
        plt.plot(self.FitX, self.Blob1GaussFit)
        plt.plot(self.FitX, self.Blob2GaussFit)
        plt.fill_between(self.FitX, 0, self.OverlapFit, alpha=0.5)
        plt.ylabel('counts')
        plt.xlabel('I (AU)')
        plt.title('Histogram Data Fit')

        #### for diagnostic purposes print out the parameters
        # fitVal = ["%.2f"  % i for i in self.popt_gauss2]
        # print('blob1, amp: '+fitVal[0]+', cen:'+fitVal[1]+', std:'+fitVal[2])
        # print('blob2, amp: '+fitVal[3]+', cen:'+fitVal[4]+', std:'+fitVal[5])


def hist_process(data=None, plot=True, ran=None, figNum = 1, title = '', alpha = 0.5):
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

        axs[0].scatter(ig, qg, label='g', color='r', marker='*', alpha=alpha)
        axs[0].scatter(ie, qe, label='e', color='b', marker='*', alpha=alpha)
        axs[0].scatter(xg, yg, color='k', marker='o')
        axs[0].scatter(xe, ye, color='k', marker='o')
        axs[0].set_xlabel('I (a.u.)')
        axs[0].set_ylabel('Q (a.u.)')
        axs[0].legend(loc='upper right')
        axs[0].set_title('Unrotated')
        axs[0].axis('equal')
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
            xlims = [xe - 0.6*xe_range, xg + 0.6*xg_range]
        else:
            xlims = [xg -  0.6*xg_range, xe +  0.6*xe_range]
    else:
        xlims = [xg - ran, xg + ran]
        ylims = [yg - ran, yg + ran]

    if plot == True:
        axs[1].scatter(ig_new, qg_new, label='g', color='r', marker='*', alpha=alpha)
        axs[1].scatter(ie_new, qe_new, label='e', color='b', marker='*', alpha=alpha)
        axs[1].scatter(xg, yg, color='k', marker='o')
        axs[1].scatter(xe, ye, color='k', marker='o')
        axs[1].set_xlabel('I (a.u.)')
        axs[1].legend(loc='lower right')
        axs[1].set_title('Rotated')
        axs[1].axis('equal')

        """X and Y ranges for histogram"""

        ng, binsg, pg = axs[2].hist(ig_new, bins=numbins, range=xlims, color='r', label='g', alpha=0.5)
        ne, binse, pe = axs[2].hist(ie_new, bins=numbins, range=xlims, color='b', label='e', alpha=0.5)
        axs[2].set_xlabel('I(a.u.)')
        axs[2].legend(loc='upper right')

    else:
        ng, binsg = np.histogram(ig_new, bins=numbins, range=xlims)
        ne, binse = np.histogram(ie_new, bins=numbins, range=xlims)

    """Compute the fidelity using overlap of the histograms"""
    contrast = np.abs(((np.cumsum(ng) - np.cumsum(ne)) / (0.5 * ng.sum() + 0.5 * ne.sum())))
    tind = contrast.argmax()
    threshold = binsg[tind]
    fid = contrast[tind]
    if plot ==True:
        axs[2].set_title(f"Fidelity = {fid * 100:.2f}%")

    return fid, threshold, theta

def hist_process_per_class(data=None, plot=True, ran=None, figNum = 1, title = '', alpha = 0.5, print_fidelities = True):
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

        axs[0].scatter(ig, qg, label='g', color='r', marker='*', alpha=alpha)
        axs[0].scatter(ie, qe, label='e', color='b', marker='*', alpha=alpha)
        axs[0].scatter(xg, yg, color='k', marker='o')
        axs[0].scatter(xe, ye, color='k', marker='o')
        axs[0].set_xlabel('I (a.u.)')
        axs[0].set_ylabel('Q (a.u.)')
        axs[0].legend(loc='upper right')
        axs[0].set_title('Unrotated')
        axs[0].axis('equal')
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
            xlims = [xe - 0.6*xe_range, xg + 0.6*xg_range]
        else:
            xlims = [xg -  0.6*xg_range, xe +  0.6*xe_range]
    else:
        xlims = [xg - ran, xg + ran]
        ylims = [yg - ran, yg + ran]

    if plot == True:
        axs[1].scatter(ig_new, qg_new, label='g', color='r', marker='*', alpha=alpha)
        axs[1].scatter(ie_new, qe_new, label='e', color='b', marker='*', alpha=alpha)
        axs[1].scatter(xg, yg, color='k', marker='o')
        axs[1].scatter(xe, ye, color='k', marker='o')
        axs[1].set_xlabel('I (a.u.)')
        axs[1].legend(loc='lower right')
        axs[1].set_title(f'Rotated; Angle = {theta:.3f}')
        axs[1].axis('equal')

        """X and Y ranges for histogram"""

        ng, binsg, pg = axs[2].hist(ig_new, bins=numbins, range=xlims, color='r', label='g', alpha=0.5)
        ne, binse, pe = axs[2].hist(ie_new, bins=numbins, range=xlims, color='b', label='e', alpha=0.5)
        axs[2].set_xlabel('I(a.u.)')
        axs[2].legend(loc='upper right')

    else:
        ng, binsg = np.histogram(ig_new, bins=numbins, range=xlims)
        ne, binse = np.histogram(ie_new, bins=numbins, range=xlims)

    """Compute the fidelity using overlap of the histograms"""
    # contrast = np.abs(((np.cumsum(ng) - np.cumsum(ne)) / (0.5 * ng.sum() + 0.5 * ne.sum())))
    contrast = np.cumsum(ng) / ng.sum() - np.cumsum(ne)/ ne.sum()

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

    if plot ==True:
        axs[2].axvline(threshold, 0, 20, color = 'black', alpha = 0.7, ls = '--')

        # axs[2].set_title(f"Fidelity = {fid * 100:.2f}%; Thresh: {threshold:.3f}")
        axs[2].set_title(f"Fi: {fid * 100:.1f}%; Thr: {threshold:.1f}; ne: {ne_contrast:.2f}, ng: {ng_contrast:.2f}")

    return fid, threshold, theta