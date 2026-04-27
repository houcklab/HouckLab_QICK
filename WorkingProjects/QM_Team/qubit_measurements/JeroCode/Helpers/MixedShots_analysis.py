#####  Class for taking in mixed state single shot data and finding the
##### blob seperation and fits

import numpy as np
import pandas as pd
import scipy
# import statsmodells.api as sm
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.cluster import KMeans
import math


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
        self.Blob1_area = np.trapz(self.Blob1GaussFit, self.FitX)
        self.Blob2_area = np.trapz(self.Blob2GaussFit, self.FitX)
        Overlap_area = np.trapz(self.OverlapFit, self.FitX)
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
