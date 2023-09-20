from qick import *
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium.Client_modules.CoreLib.Experiment import ExperimentClass
from WTF.Client_modules.Helpers.hist_analysis import *
from WorkingProjects.Tantalum_fluxonium.Client_modules.Helpers.MixedShots_analysis import *
from tqdm.notebook import tqdm
import time
from sklearn.cluster import KMeans
import math
from scipy.optimize import curve_fit

##########################################################################################################
### define functions to be used later for analysis
#### define a rotation function
def rotateBlob(i, q, theta):
    i_rot = i * np.cos(theta) - q * np.sin(theta)
    q_rot = i * np.sin(theta) + q * np.cos(theta)
    return i_rot, q_rot

def SelectAllShots(shots_1_i, shots_1_q, shots_0_igRot, Cen1, Cen2):
    ### selects out shots and defines based on left being 1 and right being 2
    shots_1_iSel = np.array([])
    shots_1_qSel = np.array([])
    shots_2_iSel = np.array([])
    shots_2_qSel = np.array([])
    if Cen1 < Cen2:
        for i in range(len(shots_0_igRot)):
            if shots_0_igRot[i] < Cen1:
                shots_1_iSel = np.append(shots_1_iSel, shots_1_i[i])
                shots_1_qSel = np.append(shots_1_qSel, shots_1_q[i])

            if shots_0_igRot[i] > Cen2:
                shots_2_iSel = np.append(shots_2_iSel, shots_1_i[i])
                shots_2_qSel = np.append(shots_2_qSel, shots_1_q[i])

        return shots_1_iSel, shots_1_qSel, shots_2_iSel, shots_2_qSel

    else:
        for i in range(len(shots_0_igRot)):
            if shots_0_igRot[i] > Cen1:
                shots_1_iSel = np.append(shots_1_iSel, shots_1_i[i])
                shots_1_qSel = np.append(shots_1_qSel, shots_1_q[i])

            if shots_0_igRot[i] < Cen2:
                shots_2_iSel = np.append(shots_2_iSel, shots_1_i[i])
                shots_2_qSel = np.append(shots_2_qSel, shots_1_q[i])

        return shots_2_iSel, shots_2_qSel, shots_1_iSel, shots_1_qSel

####################################################################################################################

class LoopbackProgramT1_PS(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        ##### set up the experiment updates, only runs it once
        cfg["start"]= 0
        cfg["step"]= 0
        cfg["reps"]=cfg["shots"]
        cfg["expts"]=1

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_gain = self.sreg(cfg["qubit_ch"], "gain")  # get frequency register for qubit_ch

        res_ch = cfg["res_ch"]
        #         r_freq=self.sreg(cfg["res_ch"], "freq")   #Get frequency register for res_ch
        self.declare_gen(ch=res_ch, nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])

        # Qubit configuration
        qubit_ch = cfg["qubit_ch"]
        self.declare_gen(ch=qubit_ch, nqz=cfg["qubit_nqz"])

        # configure the readout lengths and downconversion frequencies
        for ro_ch in cfg["ro_chs"]:
            # self.declare_readout(ch=ro_ch, freq=cfg["read_pulse_freq"],
            #                      length=self.us2cycles(self.cfg["state_read_length"]), gen_ch=cfg["res_ch"])
            self.declare_readout(ch=ro_ch, freq=cfg["read_pulse_freq"],
                                 length=self.us2cycles(self.cfg["read_length"]), gen_ch=cfg["res_ch"])

        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=res_ch, ro_ch=cfg["ro_chs"][0])
        qubit_freq = self.freq2reg(cfg["qubit_freq"], gen_ch=cfg[
            "qubit_ch"])  # convert frequency to dac frequency (ensuring it is an available adc frequency)
        # convert frequency to dac frequency (ensuring it is an available adc frequency)

        ### Declaration of Pulses
        if cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit")

        elif cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit",  length=self.us2cycles(self.cfg["flat_top_length"]))

        else:
            print("define pi or flat top pulse")

        self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0, gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"]),
                                 )  # mode="periodic")

        self.synci(200)  # give processor some time to configure pulses


    def body(self):
        ### intial pause
        self.sync_all(self.us2cycles(0.01))  # align channels and wait 50ns
        self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse
        self.sync_all(self.us2cycles(0.01))  # align channels and wait 50ns

        #### measure beginning thermal state
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait = False)

        # self.sync_all(self.us2cycles(0.01))  # align channels and wait 50ns
        # self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse
        self.sync_all(self.us2cycles(0.01))  # align channels and wait 50ns

        self.sync_all(self.us2cycles(self.cfg["wait_length"]))

        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))


    def update(self):
        self.mathi(self.q_rp, self.r_gain, self.r_gain, '+', self.cfg["step"]) # update frequency list index

    def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=2, save_experiments=[0,1],
                start_src="internal", progress=False, debug=False):

        super().acquire(soc, load_pulses=load_pulses, progress=progress, debug=debug,
                        readouts_per_experiment=2, save_experiments=[0,1])

        return self.collect_shots()

    def collect_shots(self):
        shots_i0=self.di_buf[0]/self.us2cycles(self.cfg['read_length'], ro_ch = 0)
        shots_q0=self.dq_buf[0]/self.us2cycles(self.cfg['read_length'], ro_ch = 0)

        i_0 = shots_i0[0::2]
        i_1 = shots_i0[1::2]
        q_0 = shots_q0[0::2]
        q_1 = shots_q0[1::2]

        return i_0, i_1, q_0, q_1


# ====================================================== #

class T1_PS(ExperimentClass):
    """
    Use post selection at a thermal state (significant thermal population) to find T1
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):

        expt_cfg = {
            ### define the wait times
            "wait_start": self.cfg["wait_start"],
            "wait_stop": self.cfg["wait_stop"],
            "wait_num": self.cfg["wait_num"],
        }

        wait_vec = np.linspace(expt_cfg["wait_start"], expt_cfg["wait_stop"], expt_cfg["wait_num"])
        t_arr = wait_vec

        self.cfg["wait_length"] = expt_cfg["wait_start"]

        ##### create arrays to store all the raw data
        i_0_arr = np.full((expt_cfg["wait_num"], int(self.cfg["shots"]) ), np.nan)
        q_0_arr = np.full((expt_cfg["wait_num"], int(self.cfg["shots"]) ), np.nan)
        i_1_arr = np.full((expt_cfg["wait_num"], int(self.cfg["shots"]) ), np.nan)
        q_1_arr = np.full((expt_cfg["wait_num"], int(self.cfg["shots"]) ), np.nan)

        #### loop over all wait times and collect raw data
        for idx_wait in range(expt_cfg["wait_num"]):
            self.cfg["wait_length"] = wait_vec[idx_wait]

            #### pull the data from the single shots for the first run
            prog = LoopbackProgramT1_PS(self.soccfg, self.cfg)
            i_0, i_1, q_0, q_1 = prog.acquire(self.soc, load_pulses=True, readouts_per_experiment=2, save_experiments=[0,1])

            #### save all the data to arrays
            i_0_arr[idx_wait, :] = i_0
            q_0_arr[idx_wait, :] = q_0
            i_1_arr[idx_wait, :] = i_1
            q_1_arr[idx_wait, :] = q_1

            ####################################################
            cen_num = self.cfg["cen_num"]
            alpha_val = 0.5
            colors = ['b', 'r', 'm', 'c', 'g']
            ### store the data
            i_raw = i_0
            q_raw = q_0

            I = i_raw
            Q = q_raw

            iqData = np.stack((i_raw, q_raw), axis=1)

            ### partition data into two cluster
            kmeans = KMeans(
                n_clusters=cen_num, n_init=7, max_iter=1000).fit(iqData)

            ### pull out the centers of the clusters
            Centers = kmeans.cluster_centers_
            ### pull out labels for the blobs
            blobNums = kmeans.labels_
            ### create an array to store all seperated blobs
            ### indexed as blobs[BLOB NUMBER][0 for I, 1 for Q][shot number]
            blobs = np.full([cen_num, 2, len(i_raw)], np.nan)
            dists = np.full([cen_num, len(i_raw)], np.nan)

            for idx_shot in range(len(i_raw)):
                for idx_cen in range(cen_num):
                    if blobNums[idx_shot] == idx_cen:
                        #### fill blob with I and Q data
                        blobs[idx_cen][0][idx_shot] = i_raw[idx_shot]
                        blobs[idx_cen][1][idx_shot] = q_raw[idx_shot]
                        #### fill with distance info
                        dists[idx_cen][idx_shot] = np.sqrt(
                            (Centers[idx_cen][0] - i_raw[idx_shot]) ** 2 +
                            (Centers[idx_cen][1] - q_raw[idx_shot]) ** 2)

            # ###############################################
            if idx_wait == 0:
                ##### plot out
                fig, axs = plt.subplots(1, 2, figsize=[5, 5], num = 111)

                #### plot raw data only
                axs[0].plot(I, Q, '.', alpha=alpha_val)

                axs[0].set_xlabel('I')
                axs[0].set_ylabel('Q')

                # #### find the relative population amounts
                # blob_pops = np.zeros(cen_num)
                #  for idx in range

                #### plot the sorted blobs
                for idx in range(cen_num):
                    axs[1].plot(blobs[idx][0], blobs[idx][1], '.', alpha=alpha_val, color=colors[idx])
                    axs[1].plot(Centers[idx][0], Centers[idx][1], 'k*', markersize=15)

                ### plot circle around each center with radius of average blob size
                for idx in range(cen_num):
                    axs[1].add_patch(
                        plt.Circle((Centers[idx][0], Centers[idx][1]), np.nanmean(dists[idx]),
                                   color='k', fill=False, zorder=2)
                    )

                axs[1].set_xlabel('I')
                axs[1].set_ylabel('Q')

                axs[1].set_ylim(axs[0].get_ylim())
                axs[1].set_xlim(axs[0].get_xlim())

                lims = [axs[0].get_xlim(), axs[0].get_ylim()]

                plt.tight_layout()

            # #### look at slice of qubit trajectory
            # idx_t = 0
            # blobs_0 = np.full([cen_num, 2, len(I)], np.nan)
            # blobs_1 = np.full([cen_num, 2, len(I)], np.nan)
            #
            # for idx_shot in range(len(i_0_arr[idx_t])):
            #     for idx_cen in range(cen_num):
            #         pt_dist = np.sqrt((i_0_arr[idx_t][idx_shot] - Centers[idx_cen][0]) ** 2
            #                           + (q_0_arr[idx_t][idx_shot] - Centers[idx_cen][1]) ** 2)
            #         size_select = np.nanmean(dists[idx_cen])
            #
            #         if pt_dist <= size_select:
            #             #### fill blob with I and Q data
            #             blobs_0[idx_cen][0][idx_shot] = i_0_arr[idx_t][idx_shot]
            #             blobs_0[idx_cen][1][idx_shot] = q_0_arr[idx_t][idx_shot]
            #
            #             blobs_1[idx_cen][0][idx_shot] = i_1_arr[idx_t][idx_shot]
            #             blobs_1[idx_cen][1][idx_shot] = q_1_arr[idx_t][idx_shot]
            #
            # ##### plot out
            # fig, axs = plt.subplots(cen_num, 1, figsize=[8, 10], num = 112)
            #
            # alpha_val = 0.5
            #
            # #### plot the sorted blobs
            # for idx in range(cen_num):
            #     axs[idx].plot(blobs_0[idx][0], blobs_0[idx][1], '.', alpha=alpha_val, color=colors[idx])
            #     axs[idx].plot(blobs_1[idx][0], blobs_1[idx][1], '.', alpha=alpha_val)
            #     axs[idx].set_xlabel('I')
            #     axs[idx].set_ylabel('Q')
            #     axs[idx].set_xlim(lims[0])
            #     axs[idx].set_ylim(lims[1])
            #
            #     plt.tight_layout()
            #
            # plt.show()
            # ####################################################


        ### using desired number of clustors, seperate out the data

        ############# loop over all time slices and find distribuition of populations
        ### indexed as pops_arr[starting blob][resulting blob][time index]
        pops_arr = np.full([cen_num, cen_num, len(t_arr)], 0.0)

        #### using the blob centers sort out data
        blobSizes = dists

        #### loop over time steps
        for idx_t in range(len(t_arr)):
            #### create new set of blobs for each point in time
            blobs_0 = np.full([cen_num, 2, len(i_0_arr[idx_t])], np.nan)
            blobs_1 = np.full([cen_num, 2, len(i_0_arr[idx_t])], np.nan)

            for idx_shot in range(len(i_0_arr[idx_t])):
                for idx_cen in range(cen_num):
                    pt_dist = np.sqrt((i_0_arr[idx_t][idx_shot] - Centers[idx_cen][0]) ** 2
                                      + (q_0_arr[idx_t][idx_shot] - Centers[idx_cen][1]) ** 2)
                    size_select = np.nanmean(dists[idx_cen])

                    if pt_dist <= size_select:
                        #### fill blob with I and Q data
                        blobs_0[idx_cen][0][idx_shot] = i_0_arr[idx_t][idx_shot]
                        blobs_0[idx_cen][1][idx_shot] = q_0_arr[idx_t][idx_shot]

                        blobs_1[idx_cen][0][idx_shot] = i_1_arr[idx_t][idx_shot]
                        blobs_1[idx_cen][1][idx_shot] = q_1_arr[idx_t][idx_shot]

            #### using sorted blob data, find approximate population distribuitions
            for idx_cen_start in range(cen_num):
                #### grab i and q data from blob, removing out the nan values
                iData = blobs_1[idx_cen_start][0][~np.isnan(blobs_1[idx_cen_start][0])]
                qData = blobs_1[idx_cen_start][1][~np.isnan(blobs_1[idx_cen_start][1])]
                iq = np.stack((iData, qData), axis=1)
                ##### sort data into predicted blob distributions
                blob_distribution = kmeans.predict(iq)

                ##### calculate the distribuition of the blob populations
                for idx in range(len(blob_distribution)):
                    for idx_cen_stop in range(cen_num):
                        if blob_distribution[idx] == idx_cen_stop:
                            pops_arr[idx_cen_start][idx_cen_stop][idx_t] += 1
                pops_arr[idx_cen_start][:, idx_t] = pops_arr[idx_cen_start][:, idx_t] / len(blob_distribution)

        ##### plot out
        fig, axs = plt.subplots(cen_num, 1, figsize=[5, 6])

        alpha_val = 0.5
        colors = ['b', 'r', 'm', 'c', 'g']

        ### exponential fitting
        def expFit(x, a, T1, c):
            return a * np.exp(-1 * x / T1) + c

        #### loop over starting blobs
        for idx_plot in range(cen_num):
            #### loop over each final blob
            for idx_blob in range(cen_num):
                # Plot the data before the fits
                axs[idx_plot].plot(t_arr, pops_arr[idx_plot][idx_blob], 'o',
                                   label='blob ' + str(idx_blob), color=colors[idx_blob])

                #### find the T1 fit of the data
                if idx_plot == idx_blob:
                    pop_list = pops_arr[idx_plot][idx_blob]
                    a_guess = (np.max(pop_list) - np.min(pop_list)) * -1
                    T1_guess = np.max(t_arr) / 4.0
                    c_guess = np.min(pop_list)
                    guess = [a_guess, T1_guess, c_guess]

                    pOpt, pCov = curve_fit(expFit, t_arr, pop_list, p0=guess)
                    pErr = np.sqrt(np.diag(pCov))

                    T1 = pOpt[1]
                    T1_err = pErr[1]
                    fit = expFit(t_arr, *pOpt)

                    print(T1)

                    axs[idx_plot].plot(t_arr, fit, 'k-')
                ######



            #### label axes and title
            axs[idx_plot].set_xlabel('time (us)')
            axs[idx_plot].set_ylabel('population')
            # axs[idx_plot].set_title(
            #     'starting blob: ' + str(idx_plot) + ', T1: ' + str(round(T1, 1)) + ' +/- ' + str(round(T1_err)) + ' us')
            axs[idx_plot].set_title(
                'starting blob: ' + str(idx_plot) + ', T1: ' + str(round(T1, 1)) + ' us')
        #     axs[idx_plot].set_ylim([0.0,0.8])

        plt.tight_layout()
        plt.legend()
        # plt.show()

        plt.savefig(self.iname, dpi=600)  #### save the figure

        #### save the data
        data = {'config': self.cfg, 'data': {
                                             "wait_vec": wait_vec,
                                             'i_0_arr': i_0_arr, 'q_0_arr': q_0_arr,
                                             'i_1_arr': i_1_arr, 'q_1_arr': q_1_arr,
                                             'pop_arr': pops_arr,
                                             }
                }

        self.data = data

        return data


    def display(self, data=None, plotDisp = False, figNum = 1, ran=None, **kwargs):
        if data is None:
            data = self.data

        pop_arr = data['data']['pop_arr']
        wait_vec = data['data']['wait_vec']

        fig, axs = plt.subplots(1, 2, figsize=(10, 6), num=figNum)

        axs[0].plot(wait_vec, pop_arr[:,0], 'o-',
                    color='g')

        axs[0].plot(wait_vec, pop_arr[:,2], 'o-',
                    color='m')

        axs[0].plot(wait_vec, self.T1_fit1, label='fit 1')
        axs[0].plot(wait_vec, self.T1_fit2, label='fit 2')

        axs[0].set_ylim([-0.05, 1.05])
        axs[0].set_xlabel('wait time (us)')
        axs[0].set_ylabel('population (%)')
        axs[0].set_title("T1_1 = " + str(round(self.T1_est1, 3)) + " us, T1_2 = " + str(round(self.T1_est2, 3)))

        #### plot the excited state populations
        axs[1].plot(wait_vec, pop_arr[:,1], 'o-',
                    color='g')

        axs[1].plot(wait_vec, pop_arr[:,3], 'o-',
                    color='m')

        axs[1].set_ylim([-0.05, 1.05])
        axs[1].set_xlabel('wait time (us)')
        axs[1].set_ylabel('population (%)')
        axs[1].set_title('blob 2')

        if plotDisp:
            plt.show(block=False)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)


    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])
