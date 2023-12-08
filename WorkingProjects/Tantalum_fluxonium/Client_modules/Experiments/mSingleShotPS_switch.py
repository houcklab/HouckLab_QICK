from qick import *
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.Tantalum_fluxonium.Client_modules.Helpers.hist_analysis import *
from WorkingProjects.Tantalum_fluxonium.Client_modules.Helpers.MixedShots_analysis import *
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

class LoopbackProgramSingleShotPS_switch(RAveragerProgram):
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
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4

        elif cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"]),
                           length=self.us2cycles(self.cfg["sigma"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit",  length=self.us2cycles(self.cfg["flat_top_length"]))
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4 + self.us2cycles(self.cfg["flat_top_length"], gen_ch=cfg["qubit_ch"])

        else:
            print("define pi or flat top pulse")

        self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0, gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"]),
                                 )  # mode="periodic")

        # Calculate length of trigger pulse
        self.cfg["trig_len"] = self.us2cycles(self.cfg["trig_buffer_start"] + self.cfg["trig_buffer_end"],
                                              gen_ch=cfg["qubit_ch"]) + self.qubit_pulseLength  ####

        self.synci(200)  # give processor some time to configure pulses

        # self.r_thresh = 6

    def body(self):
        ### intial pause
        self.sync_all(self.us2cycles(0.05))
        #### measure starting ground states
        self.measure(pulse_ch=self.cfg["res_ch"],
             adcs=[0],
             adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]) )

        #### wait 10us
        self.sync_all(self.us2cycles(0.01))

        if self.cfg["qubit_gain"] != 0:
            self.trigger(pins=[0], t=self.us2cycles(self.cfg["trig_delay"]), width=self.cfg["trig_len"]) # trigger for switch

        self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse
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

class SingleShotPS_switch(ExperimentClass):
    """
    run a single shot expirement that utilizes a post selection process to handle thermal starting state
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
        #### pull the data from the single hots
        prog = LoopbackProgramSingleShotPS_switch(self.soccfg, self.cfg)
        ie_0, ie_1, qe_0, qe_1 = prog.acquire(self.soc, load_pulses=True, readouts_per_experiment=2, save_experiments=[0,1])
        ### run ground state expirement
        self.cfg["qubit_gain"] = 0
        prog = LoopbackProgramSingleShotPS_switch(self.soccfg, self.cfg)
        ig_0, ig_1, qg_0, qg_1 = prog.acquire(self.soc, load_pulses=True, readouts_per_experiment=2, save_experiments=[0,1])


        ##### number of clusters to use
        cen_num = self.cfg["cen_num"]

        ########## using the initial ground state data, cluster into blobs
        ### store the data for clustering
        i_raw = ig_0
        q_raw = qg_0

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

        #### create new set of blobs for each experiement
        blobs_0g = np.full([cen_num, 2, len(ig_0)], np.nan)
        blobs_1g = np.full([cen_num, 2, len(ig_0)], np.nan)
        blobs_0e = np.full([cen_num, 2, len(ig_0)], np.nan)
        blobs_1e = np.full([cen_num, 2, len(ig_0)], np.nan)

        for idx_shot in range(len(ig_0)):
            for idx_cen in range(cen_num):
                #### find the distance of the point to the center of its cluster
                pt_dist_g = np.sqrt((ig_0[idx_shot] - Centers[idx_cen][0]) ** 2
                                  + (qg_0[idx_shot] - Centers[idx_cen][1]) ** 2)
                pt_dist_e = np.sqrt((ie_0[idx_shot] - Centers[idx_cen][0]) ** 2
                                    + (qe_0[idx_shot] - Centers[idx_cen][1]) ** 2)
                size_select = np.nanmean(dists[idx_cen])

                if pt_dist_g <= size_select:
                    #### fill blob with I and Q data for "g" experiment
                    blobs_0g[idx_cen][0][idx_shot] = ig_0[idx_shot]
                    blobs_0g[idx_cen][1][idx_shot] = qg_0[idx_shot]

                    blobs_1g[idx_cen][0][idx_shot] = ig_1[idx_shot]
                    blobs_1g[idx_cen][1][idx_shot] = qg_1[idx_shot]

                if pt_dist_e <= size_select:
                    #### fill blob with I and Q data for "e" experiment
                    blobs_0e[idx_cen][0][idx_shot] = ie_0[idx_shot]
                    blobs_0e[idx_cen][1][idx_shot] = qe_0[idx_shot]

                    blobs_1e[idx_cen][0][idx_shot] = ie_1[idx_shot]
                    blobs_1e[idx_cen][1][idx_shot] = qe_1[idx_shot]

        #### try plotting stuff out
        alpha_val = 0.5
        colors = ['b', 'r', 'm', 'c', 'g']

        ##### plot out raw initial data showing cluster locations
        fig0, axs0 = plt.subplots(1, 2, figsize=[10, 10], num=111)

        #### plot raw data only
        axs0[0].plot(i_raw, q_raw, '.', alpha=alpha_val)

        axs0[0].set_xlabel('I')
        axs0[0].set_ylabel('Q')

        #### plot the sorted blobs
        for idx in range(cen_num):
            axs0[1].plot(blobs[idx][0], blobs[idx][1], '.', alpha=alpha_val,
                            color=colors[idx], label = 'blob '+str(idx))
            axs0[1].plot(Centers[idx][0], Centers[idx][1], 'k*', markersize=15)

        ### plot circle around each center with radius of average blob size
        for idx in range(cen_num):
            axs0[1].add_patch(
                plt.Circle((Centers[idx][0], Centers[idx][1]), np.nanmean(dists[idx]),
                           color='k', fill=False, zorder=2)
            )

        axs0[1].set_xlabel('I')
        axs0[1].set_ylabel('Q')

        axs0[1].set_ylim(axs0[0].get_ylim())
        axs0[1].set_xlim(axs0[0].get_xlim())

        plt.legend()
        plt.tight_layout()

        ##### plot out sorted data
        fig, axs = plt.subplots(cen_num, 2, figsize=[10, 10])

        for idx_cen in range(cen_num):

            ig = blobs_1g[idx_cen][0]
            ie = blobs_1e[idx_cen][0]

            qg = blobs_1g[idx_cen][1]
            qe = blobs_1e[idx_cen][1]

            #### remove the nan values
            ig = ig[~np.isnan(ig)]
            ie = ie[~np.isnan(ie)]

            qg = qg[~np.isnan(qg)]
            qe = qe[~np.isnan(qe)]

            ### filter arrays to be same size for each blob and experiement
            if len(ig) > len(ie):
                ig = ig[0:len(ie)]
                qg = qg[0:len(ie)]
            else:
                ie = ie[0:len(ig)]
                qe = qe[0:len(ig)]

            #### plot the sorted data
            # axs[idx_cen, 0].plot(blobs_1g[idx_cen][0], blobs_1g[idx_cen][1], 'r.', alpha = alpha_val, label = 'no pulse')
            # axs[idx_cen, 0].plot(blobs_1e[idx_cen][0], blobs_1e[idx_cen][1], 'b.', alpha = alpha_val, label='with pulse')
            axs[idx_cen, 0].plot(ig, qg, 'r.', alpha = alpha_val, label = 'no pulse')
            axs[idx_cen, 0].plot(ie, qe, 'b.', alpha = alpha_val, label = 'with pulse')

            axs[idx_cen, 0].set_xlabel("I (AU)")
            axs[idx_cen, 0].set_ylabel("Q (AU)")
            axs[idx_cen, 0].set_title('blob '+str(idx_cen))

            #### rotate data and fit to histogram
            numbins = 200
            # ig = blobs_1g[idx_cen][0]
            # ie = blobs_1e[idx_cen][0]
            #
            # qg = blobs_1g[idx_cen][1]
            # qe = blobs_1e[idx_cen][1]

            xg, yg = np.median(ig), np.median(qg)
            xe, ye = np.median(ie), np.median(qe)

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

            #### set the limits on the x bounds
            if np.min(ig_new) < np.min(ie_new):
                x_min = np.min(ig_new) - 0.1
            else:
                x_min = np.min(ie_new) - 0.1

            if np.max(ig_new) > np.max(ie_new):
                x_max = np.max(ig_new) + 0.1
            else:
                x_max = np.max(ie_new) + 0.1

            xlims = [x_min, x_max]

            #### plot
            ng, binsg, pg = axs[idx_cen, 1].hist(ig_new, bins=numbins, range=xlims, color='r', label='no pulse', alpha=0.5)
            ne, binse, pe = axs[idx_cen, 1].hist(ie_new, bins=numbins, range=xlims, color='b', label='with pulse', alpha=0.5)
            axs[idx_cen, 1].set_xlabel('I(a.u.)')

            """Compute the fidelity using overlap of the histograms"""
            contrast = np.abs(((np.cumsum(ng) - np.cumsum(ne)) / (0.5 * ng.sum() + 0.5 * ne.sum())))
            tind = contrast.argmax()
            threshold = binsg[tind]
            fid = contrast[tind]

            #### set title to fidelity
            axs[idx_cen, 1].set_title(f"Fidelity = {fid * 100:.2f}%")
            plt.legend()

        plt.tight_layout()
        #### plot and save the figure
        plt.savefig(self.iname, dpi=600)  #### save the figure



        #### save the data
        data = {'config': self.cfg, 'data': {
                                                'ig_0': ig_0, 'qg_0': qg_0, 'ie_0': ie_0, 'qe_0': qe_0,
                                                'ig_1': ig_1, 'qg_1': qg_1, 'ie_1': ie_1, 'qe_1': qe_1,
                                                'blobs_0g':blobs_0g, 'blobs_0e':blobs_0e,
                                                'blobs_1g': blobs_1g, 'blobs_1e': blobs_1e,
                                            }
                }
        self.data = data

        return data

    def display(self, data=None, plotDisp = False, figNum = 1, ran=None, **kwargs):
        if data is None:
            data = self.data

        i_g = data["data"]["i_g"]
        q_g = data["data"]["q_g"]
        i_e = data["data"]["i_e"]
        q_e = data["data"]["q_e"]

        ig_1 = data["data"]["ig_1"]
        qg_1 = data["data"]["qg_1"]
        ie_1 = data["data"]["ie_1"]
        qe_1 = data["data"]["qe_1"]

        #### plotting is handled by the helper histogram
        fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=plotDisp, ran=ran, figNum=1)
        plt.suptitle('selected data')
        plt.savefig(self.iname)

        fid, threshold, angle = hist_process(data=[ig_1, qg_1, ie_1, qe_1], plot=plotDisp, ran=ran, figNum=2)
        plt.suptitle('raw data')

        if plotDisp:
            plt.show(block=False)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


