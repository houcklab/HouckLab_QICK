import numpy as np
import matplotlib.pyplot as plt
from h5py import File
import os
import datetime

def hist_process(data=None, plot=True, ran=None, figNum = 1, title = '', alpha = 0.5, label_ig = "g", label_ie = "e"):
    ig = data[0]
    qg = data[1]
    ie = data[2]
    qe = data[3]


    numbins = 200

    xg, yg = np.median(ig), np.median(qg)
    xe, ye = np.median(ie), np.median(qe)

    if plot == True:
        fig, axs = plt.subplots(nrows=1, ncols=4, figsize=(20, 10), num=figNum)

        # fig.tight_layout()
        fig.suptitle(title)

        axs[0].scatter(ig, qg, label= label_ig, color='r', marker='*', alpha=alpha)
        axs[0].scatter(ie, qe, label= label_ie, color='b', marker='*', alpha=alpha)
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
        axs[1].scatter(ig_new, qg_new, label= label_ig, color='r', marker='*', alpha=alpha)
        axs[1].scatter(ie_new, qe_new, label= label_ie, color='b', marker='*', alpha=alpha)
        axs[1].scatter(xg, yg, color='k', marker='o')
        axs[1].scatter(xe, ye, color='k', marker='o')
        axs[1].set_xlabel('I (a.u.)')
        axs[1].legend(loc='lower right')
        axs[1].set_title('Rotated')
        axs[1].axis('equal')

        """X and Y ranges for histogram"""

        ng, binsg, pg = axs[2].hist(ig_new, bins=numbins, range=xlims, color='r', label=label_ig, alpha=0.5)
        ne, binse, pe = axs[2].hist(ie_new, bins=numbins, range=xlims, color='b', label=label_ie, alpha=0.5)
        axs[2].set_xlabel('I(a.u.)')
        axs[2].legend(loc='upper right')
        plt.tight_layout()

    else:
        ng, binsg = np.histogram(ig_new, bins=numbins, range=xlims)
        ne, binse = np.histogram(ie_new, bins=numbins, range=xlims)

    if plot == True:
        # Plot a 2d histogram of all the data
        i_alldata = np.concatenate((ig_new, ie_new))
        q_alldata = np.concatenate((qg_new, qe_new))
        H, xedges, yedges = np.histogram2d(i_alldata, q_alldata, bins=100)
        H = H.T
        axs[3].imshow(H, extent=[xedges[0], xedges[-1], yedges[0], yedges[-1]], origin='lower', aspect='auto')
        axs[3].set_xlabel('I (a.u.)')
        axs[3].set_ylabel('Q (a.u.)')
        axs[3].set_title('2D Histogram')
        axs[3].axis('equal')
        plt.tight_layout()

    """Compute the fidelity using overlap of the histograms"""
    contrast = np.abs(((np.cumsum(ng) - np.cumsum(ne)) / (0.5 * ng.sum() + 0.5 * ne.sum())))
    tind = contrast.argmax()
    threshold = binsg[tind]
    fid = contrast[tind]
    if plot ==True:
        axs[2].set_title(f"Fidelity = {fid * 100:.2f}%")

    return fid, threshold, theta