from qick import *
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.Tantalum_fluxonium.Client_modules.Helpers.hist_analysis import *
from WorkingProjects.Tantalum_fluxonium.Client_modules.Helpers.MixedShots_analysis import *
from WorkingProjects.Tantalum_fluxonium.Client_modules.Helpers.QND_analysis import QND_analysis
import WorkingProjects.Tantalum_fluxonium.Client_modules.Helpers.SingleShot_ErrorCalc_2 as sse2
from tqdm.notebook import tqdm
import time


##########################################################################################################
# Justin Case
# ### define functions to be used later for analysis
# #### define a rotation function
# def rotateBlob(i, q, theta):
#     i_rot = i * np.cos(theta) - q * np.sin(theta)
#     q_rot = i * np.sin(theta) + q * np.cos(theta)
#     return i_rot, q_rot
#
# def SelectShots(shots_1_i, shots_1_q, shots_0_igRot, gCen, eCen):
#     ### shots_1 refers to second measurement, shots_0_iRot is rotated i quad of first measurement
#     ### gCen and eCen are centers of the respective blobs from the ground state expirement
#     shots_1_iSel = np.array([])
#     shots_1_qSel = np.array([])
#     if gCen < eCen:
#         for i in range(len(shots_0_igRot)):
#             if shots_0_igRot[i] < gCen:
#                 shots_1_iSel = np.append(shots_1_iSel, shots_1_i[i])
#                 shots_1_qSel = np.append(shots_1_qSel, shots_1_q[i])
#     else:
#         for i in range(len(shots_0_igRot)):
#             if shots_0_igRot[i] > gCen:
#                 shots_1_iSel = np.append(shots_1_iSel, shots_1_i[i])
#                 shots_1_qSel = np.append(shots_1_qSel, shots_1_q[i])
#
#     return shots_1_iSel, shots_1_qSel

####################################################################################################################

class LoopbackProgramQND(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        ##### set up the expirement updates, only runs it once
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
        # convert frequency to dac frequency (ensuring it is an available adc frequency)
        qubit_freq = self.freq2reg(cfg["qubit_freq"],
                                   gen_ch=qubit_ch)  # convert frequency to dac frequency (ensuring it is an available adc frequency)

        if cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"]),
                           length=self.us2cycles(self.cfg["sigma"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit")
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4

        elif cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"]),
                           length=self.us2cycles(self.cfg["sigma"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit",  length=self.us2cycles(self.cfg["flat_top_length"]))
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4 + self.us2cycles(self.cfg["flat_top_length"])

        else:
            print("define pi or flat top pulse")

        self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0, gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"]),
                                 )  # mode="periodic")

        self.synci(200)  # give processor some time to configure pulses

        # self.r_thresh = 6

    def body(self):
        ### intial pause
        self.sync_all(self.us2cycles(0.05))

        self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse

        self.sync_all(self.us2cycles(0.05))

        #### measure starting ground states
        self.measure(pulse_ch=self.cfg["res_ch"],
             adcs=[0],
             adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]) )

        #### wait 10us
        self.sync_all(self.us2cycles(0.01))

        self.sync_all(self.us2cycles(0.010)) # wait 10ns after pulse ends

        self.measure(pulse_ch=self.cfg["res_ch"],
             adcs=[0],
             adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
             wait=True,
             syncdelay=self.us2cycles(self.cfg["relax_delay"]))

        # self.sync_all(self.us2cycles(self.cfg["relax_delay"]))


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

class QNDmeas(ExperimentClass):
    """
    run a single shot expirement that utilizes a post selection process to handle thermal starting state
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
        #### pull the data from the single hots
        prog = LoopbackProgramQND(self.soccfg, self.cfg)
        i_0, i_1, q_0, q_1 = prog.acquire(self.soc, load_pulses=True, readouts_per_experiment=2, save_experiments=[0,1])

        ###### calculate the QND fidelity
        # Changing the way data is stored for kmeans
        iq_data = np.stack((i_0, q_0), axis=0)

        # Get centers of the data
        cen_num = 2
        centers = sse2.getCenters(
            iq_data, cen_num, plot=False, fname="Wait_Arr_0_0",
            loc="plots_QND/")

        (state0_probs, state0_probs_err, state0_num,
         state1_probs, state1_probs_err, state1_num) = QND_analysis(
            i_0, q_0, i_1, q_1, centers,
            confidence_selection = 0.999
        )

        ##### print out results
        print(
            'Note: labeling of states does not necessarily reflect actual qubit state'
        )

        #### print the number of samples
        print('Number of 0 state samples ' + str(round(state0_num, 1)))
        print('Number of 1 state samples ' + str(round(state1_num, 1)))

        ### Print probability and std for each gaussian in different lines.
        for idx in range(2):
            print("Probability of state 0 in state {} is {} +/- {}".format(
                idx, round(100 * state0_probs[idx], 8), round(100 * state0_probs_err[0], 8))
            )

            print("Probability of state 1 state {} is {} +/- {}".format(
                idx, round(100 * state1_probs[idx], 8), round(100 * state1_probs_err[0], 8))
            )

        QND = (state0_probs[0] + state1_probs[1]) / 2
        QND_err = np.sqrt(state0_probs_err[0] ** 2 + state1_probs_err[0] ** 2)

        print("QND fidelity is {} +/- {}".format(
            round(100 * QND, 8), round(100 * QND_err, 8))
        )

        #### save the data
        data = {'config': self.cfg, 'data': {
                                                'i_0': i_0, 'q_0': q_0,
                                                'i_1': i_1, 'q_1': q_1,
                        'state0_probs': state0_probs, 'state0_probs_err': state0_probs_err, 'state0_num': state0_num,
                        'state1_probs': state1_probs, 'state1_probs_err': state1_probs_err, 'state1_num': state1_num,
                        'QND': QND, 'QND_err': QND_err,
                                            }
                }
        self.data = data

        return data

    def display(self, data=None, plotDisp = False, figNum = 1, ran=None, **kwargs):
        if data is None:
            data = self.data

        i_0 = data["data"]["i_0"]
        q_0 = data["data"]["q_0"]
        i_1 = data["data"]["i_1"]
        q_1 = data["data"]["q_1"]

        ##### number of clusters to use
        cen_num = 2

        ########## using the initial ground state data, cluster into blobs
        ### store the data for clustering
        i_raw = i_0
        q_raw = q_0

        iqData = np.stack((i_raw, q_raw), axis=1)

        ### partition data into two cluster
        kmeans = KMeans(
            n_clusters=cen_num, n_init=11, max_iter=1000).fit(iqData)

        ### pull out the centers of the clusters
        Centers = kmeans.cluster_centers_
        ### pull out labels for the blobs
        blobNums = kmeans.labels_
        ### create an array to store all seperated blobs
        ### indexed as blobs[BLOB NUMBER][0 for I, 1 for Q][shot number]
        blobs_0 = np.full([cen_num, 2, len(i_raw)], np.nan)
        dists_0 = np.full([cen_num, len(i_raw)], np.nan)

        for idx_shot in range(len(i_raw)):
            for idx_cen in range(cen_num):
                if blobNums[idx_shot] == idx_cen:
                    #### fill blob with I and Q data
                    blobs_0[idx_cen][0][idx_shot] = i_raw[idx_shot]
                    blobs_0[idx_cen][1][idx_shot] = q_raw[idx_shot]
                    #### fill with distance info
                    dists_0[idx_cen][idx_shot] = np.sqrt(
                        (Centers[idx_cen][0] - i_raw[idx_shot]) ** 2 +
                        (Centers[idx_cen][1] - q_raw[idx_shot]) ** 2)

        #### create new set of blobs for each experiement
        blobs_1_0 = np.full([2, len(i_0)], np.nan)
        blobs_1_1 = np.full([2, len(i_0)], np.nan)

        for idx_shot in range(len(i_0)):
            for idx_cen in range(cen_num):
                #### find the distance of the point to the center of its cluster
                pt_dist = np.sqrt((i_0[idx_shot] - Centers[idx_cen][0]) ** 2
                                  + (q_0[idx_shot] - Centers[idx_cen][1]) ** 2)
                size_select = np.nanmean(dists_0[idx_cen])

                if pt_dist <= size_select and idx_cen == 0:
                    #### fill blob with I and Q data for 2nd measurement

                    blobs_1_0[0][idx_shot] = i_1[idx_shot]
                    blobs_1_0[1][idx_shot] = q_1[idx_shot]

                if pt_dist <= size_select and idx_cen == 1:
                    #### fill blob with I and Q data for 2nd measurement

                    blobs_1_1[0][idx_shot] = i_1[idx_shot]
                    blobs_1_1[1][idx_shot] = q_1[idx_shot]

        #### pull out centers for rotation
        numbins = 100
        x0, y0 = Centers[0][0], Centers[0][1]
        x1, y1 = Centers[1][0], Centers[1][1]

        """Compute the rotation angle"""
        theta = -np.arctan2((y1 - y0), (x1 - x0))

        #### rotate the data
        i0_new = i_0 * np.cos(theta) - q_0 * np.sin(theta)

        i0_0_new = ( blobs_0[0][0][~np.isnan(blobs_0[0][0])] * np.cos(theta) -
                     blobs_0[0][1][~np.isnan(blobs_0[0][1])] * np.sin(theta) )

        i0_1_new = ( blobs_0[1][0][~np.isnan(blobs_0[1][0])] * np.cos(theta) -
                     blobs_0[1][1][~np.isnan(blobs_0[1][1])] * np.sin(theta) )


        #### try plotting stuff out
        alpha_val = 0.5
        colors = ['b', 'r', 'm', 'c', 'g']

        ##### plot out raw initial data showing cluster locations
        fig0, axs0 = plt.subplots(1, 3, figsize=[10, 6], num=111)

        title = (self.outerFolder + '\n' + self.path_wDate + '\n Read Length: ' + str(
            self.cfg["read_length"]) + "us, freq: " + str(self.cfg["read_pulse_freq"])
                 + "MHz, gain: " + str(self.cfg["read_pulse_gain"]))

        #### plot raw data only
        axs0[0].plot(i_raw, q_raw, '.', alpha=alpha_val)

        axs0[0].set_xlabel('I')
        axs0[0].set_ylabel('Q')

        #### plot the sorted blobs
        for idx in range(cen_num):
            axs0[1].plot(blobs_0[idx][0], blobs_0[idx][1], '.', alpha=alpha_val,
                            color=colors[idx], label = 'blob '+str(idx))
            axs0[1].plot(Centers[idx][0], Centers[idx][1], 'k*', markersize=15)

        ### plot circle around each center with radius of average blob size
        for idx in range(cen_num):
            axs0[1].add_patch(
                plt.Circle((Centers[idx][0], Centers[idx][1]), np.nanmean(dists_0[idx]),
                           color='k', fill=False, zorder=2)
            )

        axs0[1].set_xlabel('I')
        axs0[1].set_ylabel('Q')

        axs0[1].set_ylim(axs0[0].get_ylim())
        axs0[1].set_xlim(axs0[0].get_xlim())

        ##### plot histogram
        i0_n, i0_bins, i0_p = axs0[2].hist(i0_new, bins=numbins, color='m', label='initial measurement',
                                                   alpha=0.5)

        xlims = [min(i0_bins), max(i0_bins)]
        thresh = np.median(i0_bins)

        i0_0_n, i0_0_bins, i0_0_p = axs0[2].hist(i0_0_new, bins=numbins, range=xlims, color='r', label='initial measurement',
                                                   alpha=0.5)

        i0_1_n, i0_1_bins, i0_1_p = axs0[2].hist(i0_1_new, bins=numbins, range=xlims, color='b', label='initial measurement',
                                                   alpha=0.5)

        axs0[2].axvline(thresh, color = 'k')
        axs0[2].set_xlabel('I')
        axs0[2].set_ylabel('Q')

        plt.legend()
        plt.tight_layout()

        ##### plot out sorted data
        fig, axs = plt.subplots(cen_num, 2, figsize=[10, 10])

        for idx_cen in range(cen_num):

            i1_0 = blobs_1_0[0]
            i1_1 = blobs_1_1[0]

            q1_0 = blobs_1_0[1]
            q1_1 = blobs_1_1[1]

            #### remove the nan values
            i1_0 = i1_0[~np.isnan(i1_0)]
            i1_1 = i1_1[~np.isnan(i1_1)]

            q1_0 = q1_0[~np.isnan(q1_0)]
            q1_1 = q1_1[~np.isnan(q1_1)]

            #### plot the sorted data
            #
            if idx_cen == 0:
                axs[idx_cen, 0].plot(i1_0, q1_0, 'r.', alpha = alpha_val, label = 'pulse')
            if idx_cen == 1:
                axs[idx_cen, 0].plot(i1_1, q1_1, 'r.', alpha = alpha_val, label = 'pulse')

            axs[idx_cen, 0].set_xlabel("I (AU)")
            axs[idx_cen, 0].set_ylabel("Q (AU)")
            axs[idx_cen, 0].set_title('blob '+str(idx_cen))

            """Rotate the IQ data"""
            i1_1_new = i1_1 * np.cos(theta) - q1_1 * np.sin(theta)
            i1_0_new = i1_0 * np.cos(theta) - q1_0 * np.sin(theta)


            #### plot
            if idx_cen == 0:
                n1_0, bins1_0, p1_0 = axs[idx_cen, 1].hist(i1_0_new, bins=numbins, range=xlims, color='r', label='no pulse', alpha=0.5)
            if idx_cen == 1:
                n1_1, bins1_1, p1_0 = axs[idx_cen, 1].hist(i1_1_new, bins=numbins, range=xlims, color='b', label='with pulse', alpha=0.5)
            axs[idx_cen, 1].set_xlabel('I(a.u.)')
            axs[idx_cen, 1].axvline(thresh, color='k')

            # """Compute the fidelity using overlap of the histograms"""
            # contrast = np.abs(((np.cumsum(ng) - np.cumsum(ne)) / (0.5 * ng.sum() + 0.5 * ne.sum())))
            # tind = contrast.argmax()
            # threshold = binsg[tind]
            # fid = contrast[tind]

            #### set title to fidelity
            # axs[idx_cen, 1].set_title(f"Fidelity = {fid * 100:.2f}%")
            plt.legend()

        plt.tight_layout()
        #### plot and save the figure
        plt.savefig(self.iname, dpi=600)  #### save the figure


    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


