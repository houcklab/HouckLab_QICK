import numpy as np
import matplotlib.pyplot as plt
from h5py import File
import os
import datetime

def hist_process(data=None, plot=True, ran=None, figNum = 1, title = '', alpha = 0.5, print_fidelities = True, return_errors=False):
    ig = data[0]
    qg = data[1]
    ie = data[2]
    qe = data[3]

    numbins = 200

    xg, yg = np.median(ig), np.median(qg)
    xe, ye = np.median(ie), np.median(qe)

    if plot == True:
        while plt.fignum_exists(num=figNum):  # if figure with number already exists
            figNum += 1
        fig, axs = plt.subplots(nrows=1, ncols=3, figsize=(11.2, 5.6), num=figNum)

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
    contrast = np.cumsum(ng) / ng.sum() - np.cumsum(ne)/ ne.sum()

    tind = contrast.argmax()
    threshold = binsg[tind]
    fid = contrast[tind]
    ne_contrast = np.cumsum(ne)[tind] / ne.sum()
    ng_contrast = 1 - np.cumsum(ng)[tind] / ng.sum()
    if print_fidelities:
        print(f"Single shot: ne contrast={ne_contrast}, ng contrast={ng_contrast}")

    if plot ==True:
        axs[2].axvline(threshold, 0, 20, color = 'black', alpha = 0.7, ls = '--')

        axs[2].set_title(f"Fi: {fid * 100:.1f}%; Thr: {threshold:.1f}; ne: {ne_contrast:.2f}, ng: {ng_contrast:.2f}")

    if not return_errors:
        return fid, threshold, theta
    else:
        return fid, threshold, theta, ne_contrast, ng_contrast




def hist_process_2Q(data=None, ran=None, figNum = 1, title = '', alpha = 0.5, print_fidelities = True, return_errors=False):
    '''
    Plots histograms for two qubit singleshot measurements. First plot is unrotated IQ showing four blobs (00, 01, 10, 11).
    Second plot rotates IQ for the first qubit (traces out the second). Third plot shows histogram for first qubit.
    Third, fourth, and fifth plots show unrotated IQ, rotated IQ, and histogram for the second qubit.
    '''

    while plt.fignum_exists(num=figNum):  # if figure with number already exists
        figNum += 1
    fig, axs = plt.subplots(nrows=2, ncols=3, figsize=(16, 8), num=figNum)

    readout_list = data['config']["Qubit_Readout_List"]

    for i in range(len(readout_list)):

        read_index = readout_list[i]

        i_g = data["data"]["i_g" + str(read_index)]
        q_g = data["data"]["q_g" + str(read_index)]
        i_e = data["data"]["i_e" + str(read_index)]
        q_e = data["data"]["q_e" + str(read_index)]

        i_gg = data['data']['i_gg' + str(read_index)]
        q_gg = data['data']['q_gg' + str(read_index)]

        i_ge = data['data']['i_ge' + str(read_index)]
        q_ge = data['data']['q_ge' + str(read_index)]

        i_eg = data['data']['i_eg' + str(read_index)]
        q_eg = data['data']['q_eg' + str(read_index)]

        i_ee = data['data']['i_ee' + str(read_index)]
        q_ee = data['data']['q_ee' + str(read_index)]

        numbins = 200

        xg, yg = np.median(i_g), np.median(q_g)
        xe, ye = np.median(i_e), np.median(q_e)

        xgg, ygg = np.median(i_gg), np.median(q_gg)
        xge, yge = np.median(i_ge), np.median(q_ge)
        xeg, yeg = np.median(i_eg), np.median(q_eg)
        xee, yee = np.median(i_ee), np.median(q_ee)


        fig.tight_layout()
        fig.suptitle(title)

        axs[i,0].scatter(i_gg, q_gg, label='gg', color='r', marker='*', alpha=alpha)
        axs[i,0].scatter(i_ge, q_ge, label='ge', color='green', marker='*', alpha=alpha)
        axs[i,0].scatter(i_eg, q_eg, label='eg', color='b', marker='*', alpha=alpha)
        axs[i,0].scatter(i_ee, q_ee, label='ee', color='purple', marker='*', alpha=alpha)
        axs[i,0].scatter(xgg, ygg, color='k', marker='o')
        axs[i,0].scatter(xge, yge, color='k', marker='o')
        axs[i,0].scatter(xeg, yeg, color='k', marker='o')
        axs[i,0].scatter(xee, yee, color='k', marker='o')
        axs[i,0].set_xlabel('I (a.u.)')
        axs[i,0].set_ylabel('Q (a.u.)')
        axs[i,0].legend(loc='upper right')
        axs[i,0].set_title(f'Unrotated, Read: {read_index}')
        axs[i,0].axis('equal')

        """Compute the rotation angle"""
        theta = -np.arctan2((ye - yg), (xe - xg))
        """Rotate the IQ data"""
        i_g_new = i_g * np.cos(theta) - q_g * np.sin(theta)
        q_g_new = i_g * np.sin(theta) + q_g * np.cos(theta)
        i_e_new = i_e * np.cos(theta) - q_e * np.sin(theta)
        q_e_new = i_e * np.sin(theta) + q_e * np.cos(theta)

        i_gg_new = i_gg * np.cos(theta) - q_gg * np.sin(theta)
        q_gg_new = i_gg * np.sin(theta) + q_gg * np.cos(theta)
        i_ge_new = i_ge * np.cos(theta) - q_ge * np.sin(theta)
        q_ge_new = i_ge * np.sin(theta) + q_ge * np.cos(theta)
        i_eg_new = i_eg * np.cos(theta) - q_eg * np.sin(theta)
        q_eg_new = i_eg * np.sin(theta) + q_eg * np.cos(theta)
        i_ee_new = i_ee * np.cos(theta) - q_ee * np.sin(theta)
        q_ee_new = i_ee * np.sin(theta) + q_ee * np.cos(theta)

        """New means of each blob"""
        xg, yg = np.median(i_g_new), np.median(q_g_new)
        xe, ye = np.median(i_e_new), np.median(q_e_new)

        xgg, ygg = np.median(i_gg_new), np.median(q_gg_new)
        xge, yge = np.median(i_ge_new), np.median(q_ge_new)
        xeg, yeg = np.median(i_eg_new), np.median(q_eg_new)
        xee, yee = np.median(i_ee_new), np.median(q_ee_new)

        # print(xg, xe)

        if ran == None:
            xg_range = np.ptp(i_g_new)
            xe_range = np.ptp(i_e_new)
            if xg > xe:
                xlims = [xe - 0.6*xe_range, xg + 0.6*xg_range]
            else:
                xlims = [xg -  0.6*xg_range, xe +  0.6*xe_range]
        else:
            xlims = [xg - ran, xg + ran]
            ylims = [yg - ran, yg + ran]

        axs[i,1].scatter(i_gg_new, q_gg_new, label='gg', color='r', marker='*', alpha=alpha)
        axs[i,1].scatter(i_ge_new, q_ge_new, label='ge', color='green', marker='*', alpha=alpha)
        axs[i,1].scatter(i_eg_new, q_eg_new, label='eg', color='b', marker='*', alpha=alpha)
        axs[i,1].scatter(i_ee_new, q_ee_new, label='ee', color='purple', marker='*', alpha=alpha)
        axs[i,1].scatter(xgg, ygg, color='k', marker='o')
        axs[i,1].scatter(xge, yge, color='k', marker='o')
        axs[i,1].scatter(xeg, yeg, color='k', marker='o')
        axs[i,1].scatter(xee, yee, color='k', marker='o')
        axs[i,1].set_xlabel('I (a.u.)')
        axs[i,1].legend(loc='lower right')
        axs[i,1].set_title(f'Rotated; Angle = {theta:.3f}, Read: {read_index}')
        axs[i,1].axis('equal')

        """X and Y ranges for histogram"""

        ng, binsg, pg = axs[i,2].hist(i_g_new, bins=numbins, range=xlims, color='r', alpha=0)
        ne, binse, pe = axs[i,2].hist(i_e_new, bins=numbins, range=xlims, color='b', alpha=0)

        ngg, binsgg, pgg = axs[i, 2].hist(i_gg_new, bins=numbins, range=xlims, color='r', label='gg', alpha=0.5)
        nge, binsge, pge = axs[i, 2].hist(i_ge_new, bins=numbins, range=xlims, color='green', label='ge', alpha=0.5)
        neg, binseg, peg = axs[i, 2].hist(i_eg_new, bins=numbins, range=xlims, color='b', label='eg', alpha=0.5)
        nee, binsee, pee = axs[i, 2].hist(i_ee_new, bins=numbins, range=xlims, color='purple', label='ee', alpha=0.5)

        axs[i,2].set_xlabel('I(a.u.)')
        axs[i,2].legend(loc='upper right')

        """Compute the fidelity using overlap of the histograms"""
        contrast = np.cumsum(ng) / ng.sum() - np.cumsum(ne)/ ne.sum()

        tind = contrast.argmax()
        threshold = binsg[tind]
        fid = contrast[tind]
        ne_contrast = np.cumsum(ne)[tind] / ne.sum()
        ng_contrast = 1 - np.cumsum(ng)[tind] / ng.sum()
        if print_fidelities:
            print("Single shot:")
            print(" ne contrast: ", ne_contrast)
            print(" ng contrast: ", ng_contrast)

        axs[i,2].axvline(threshold, 0, 20, color = 'black', alpha = 0.7, ls = '--')

        axs[i,2].set_title(f"Fi: {fid * 100:.1f}%; Thr: {threshold:.1f}; ne: {ne_contrast:.2f}, ng: {ng_contrast:.2f}, Read: {read_index}")
