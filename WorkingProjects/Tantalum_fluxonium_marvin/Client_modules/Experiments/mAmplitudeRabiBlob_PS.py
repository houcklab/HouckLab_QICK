from qick import *
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Helpers.hist_analysis import *
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Helpers.MixedShots_analysis import *
from tqdm.notebook import tqdm
import time
from sklearn.cluster import KMeans
import math
from scipy.optimize import curve_fit

##########################################################################################################
# ### define functions to be used later for analysis
# #### define a rotation function
# def rotateBlob(i, q, theta):
#     i_rot = i * np.cos(theta) - q * np.sin(theta)
#     q_rot = i * np.sin(theta) + q * np.cos(theta)
#     return i_rot, q_rot
#
# def SelectAllShots(shots_1_i, shots_1_q, shots_0_igRot, Cen1, Cen2):
#     ### selects out shots and defines based on left being 1 and right being 2
#     shots_1_iSel = np.array([])
#     shots_1_qSel = np.array([])
#     shots_2_iSel = np.array([])
#     shots_2_qSel = np.array([])
#     if Cen1 < Cen2:
#         for i in range(len(shots_0_igRot)):
#             if shots_0_igRot[i] < Cen1:
#                 shots_1_iSel = np.append(shots_1_iSel, shots_1_i[i])
#                 shots_1_qSel = np.append(shots_1_qSel, shots_1_q[i])
#
#             if shots_0_igRot[i] > Cen2:
#                 shots_2_iSel = np.append(shots_2_iSel, shots_1_i[i])
#                 shots_2_qSel = np.append(shots_2_qSel, shots_1_q[i])
#
#         return shots_1_iSel, shots_1_qSel, shots_2_iSel, shots_2_qSel
#
#     else:
#         for i in range(len(shots_0_igRot)):
#             if shots_0_igRot[i] > Cen1:
#                 shots_1_iSel = np.append(shots_1_iSel, shots_1_i[i])
#                 shots_1_qSel = np.append(shots_1_qSel, shots_1_q[i])
#
#             if shots_0_igRot[i] < Cen2:
#                 shots_2_iSel = np.append(shots_2_iSel, shots_1_i[i])
#                 shots_2_qSel = np.append(shots_2_qSel, shots_1_q[i])
#
#         return shots_2_iSel, shots_2_qSel, shots_1_iSel, shots_1_qSel

####################################################################################################################

class LoopbackProgramAmplitudeRabi_PS(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        ##### set up the expirement updates, only runs it once
        cfg["start"] = 0
        cfg["step"] = 0
        cfg["reps"] = cfg["shots"]
        cfg["expts"] = 1

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

        # print("generator freq:", self.reg2freq(freq, gen_ch=res_ch))
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
                                     waveform="qubit", length=self.us2cycles(self.cfg["flat_top_length"]))
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4 + self.us2cycles(self.cfg["flat_top_length"])

        else:
            print("define pi or flat top pulse")

        self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0,
                                 gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"]),
                                 )  # mode="periodic")

        self.synci(200)  # give processor some time to configure pulses


    def body(self):
        ### intial pause
        self.sync_all(self.us2cycles(0.010))

        #### measure beginning thermal state
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait = False)

        self.sync_all(self.us2cycles(0.01))

        self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse
        self.sync_all(self.us2cycles(0.05))  # align channels and wait 50ns

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

class AmplitudeRabi_PS(ExperimentClass):
    """
    Use post selection at a thermal state and apply rabi pulse
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False, plotDisp = True, figNum = 1):

        ### define frequencies to sweep over
        expt_cfg = {
            ### qubit freq parameters
            "qubit_freq_start": self.cfg["qubit_freq_start"],
            "qubit_freq_stop": self.cfg["qubit_freq_stop"],
            "RabiNumPoints": self.cfg["RabiNumPoints"],  ### number of points
            ### rabi amp parameters
            "qubit_gain_start": self.cfg["qubit_gain_start"],
            "qubit_gain_step": self.cfg["qubit_gain_step"],
            "qubit_gain_expts": self.cfg["qubit_gain_expts"], #### plus one to account for 0 index
        }

        ### define qubit frequency array
        self.qubit_freqs = np.linspace(expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"],
                                       expt_cfg["RabiNumPoints"])
        self.qubit_amps = np.arange(0, expt_cfg["qubit_gain_expts"]) * expt_cfg["qubit_gain_step"] + expt_cfg[
            "qubit_gain_start"]

        #### define the plotting X and Y and data holders Z
        X = self.qubit_freqs / 1e3  ### put into units of GHz
        X_step = X[1] - X[0]
        Y = self.qubit_amps
        Y_step = Y[1] - Y[0]
        Z_mat = np.full((self.cfg["cen_num"], len(Y), len(X)), np.nan)
        ### create array for storing the data
        self.data = {
            'config': self.cfg,
            'data': {'Z_mat': Z_mat,
                     'qubit_freqs': self.qubit_freqs, 'qubit_amps': self.qubit_amps,
                     }
        }

        ##### create arrays to store all the raw data
        i_0_arr = np.full((len(self.qubit_amps), len(self.qubit_freqs), int(self.cfg["shots"]) ), np.nan)
        q_0_arr = np.full((len(self.qubit_amps), len(self.qubit_freqs), int(self.cfg["shots"]) ), np.nan)
        i_1_arr = np.full((len(self.qubit_amps), len(self.qubit_freqs), int(self.cfg["shots"]) ), np.nan)
        q_1_arr = np.full((len(self.qubit_amps), len(self.qubit_freqs), int(self.cfg["shots"]) ), np.nan)

        ##### set up figure
        cen_num = self.cfg["cen_num"]
        fig, axs = plt.subplots(cen_num, 1, figsize=[10, 10])
        ax_plots = []
        colorbars = []

        #### start a timer for estimating the time for the scan
        startTime = datetime.datetime.now()
        print('')  ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        start = time.time()

        #### loop over qubit gains
        for idx_amp in range(len(self.qubit_amps)):
            #### set new qubit frequency and aquire data
            self.cfg["qubit_gain"] = self.qubit_amps[idx_amp]
            #### loop over qubit frequencies
            for idx_freq in range(len(self.qubit_freqs)):
                self.cfg["qubit_freq"] = self.qubit_freqs[idx_freq]

                #### pull the data from the single shots for the first run
                prog = LoopbackProgramAmplitudeRabi_PS(self.soccfg, self.cfg)
                i_0, i_1, q_0, q_1 = prog.acquire(self.soc, load_pulses=True, readouts_per_experiment=2, save_experiments=[0,1])

                #### save all the data to arrays
                i_0_arr[idx_amp, idx_freq, :] = i_0
                q_0_arr[idx_amp, idx_freq, :] = q_0
                i_1_arr[idx_amp, idx_freq, :] = i_1
                q_1_arr[idx_amp, idx_freq, :] = q_1

                ####################################################
                if idx_amp == 0 and idx_freq == 0:
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

                    #region plot out a slice for visual
                    # if idx_amp == 0 and idx_freq ==0:
                    #     ##### plot out
                    #     fig, axs = plt.subplots(1, 2, figsize=[5, 5], num = 111)
                    #
                    #     #### plot raw data only
                    #     axs[0].plot(I, Q, '.', alpha=alpha_val)
                    #
                    #     axs[0].set_xlabel('I')
                    #     axs[0].set_ylabel('Q')
                    #
                    #     #### plot the sorted blobs
                    #     for idx in range(cen_num):
                    #         axs[1].plot(blobs[idx][0], blobs[idx][1], '.', alpha=alpha_val, color=colors[idx])
                    #         axs[1].plot(Centers[idx][0], Centers[idx][1], 'k*', markersize=15)
                    #
                    #     ### plot circle around each center with radius of average blob size
                    #     for idx in range(cen_num):
                    #         axs[1].add_patch(
                    #             plt.Circle((Centers[idx][0], Centers[idx][1]), np.nanmean(dists[idx]),
                    #                        color='k', fill=False, zorder=2)
                    #         )
                    #
                    #     axs[1].set_xlabel('I')
                    #     axs[1].set_ylabel('Q')
                    #
                    #     axs[1].set_ylim(axs[0].get_ylim())
                    #     axs[1].set_xlim(axs[0].get_xlim())
                    #
                    #     lims = [axs[0].get_xlim(), axs[0].get_ylim()]
                    #
                    #     plt.tight_layout()
                    #
                    #     plt.show()
                    #endregion


                # ####################################################

                ### using desired number of clustors, seperate out the data
                pops_arr = np.full([cen_num, cen_num], 0.0)

                #### create new set of blobs for each point in time
                blobs_0 = np.full([cen_num, 2, len(i_0)], np.nan)
                blobs_1 = np.full([cen_num, 2, len(i_0)], np.nan)

                for idx_shot in range(len(i_0)):
                    for idx_cen in range(cen_num):
                        pt_dist = np.sqrt((i_0[idx_shot] - Centers[idx_cen][0]) ** 2
                                          + (q_0[idx_shot] - Centers[idx_cen][1]) ** 2)
                        size_select = np.nanmean(dists[idx_cen])

                        if pt_dist <= size_select:
                            #### fill blob with I and Q data
                            blobs_0[idx_cen][0][idx_shot] = i_0[idx_shot]
                            blobs_0[idx_cen][1][idx_shot] = q_0[idx_shot]

                            blobs_1[idx_cen][0][idx_shot] = i_1[idx_shot]
                            blobs_1[idx_cen][1][idx_shot] = q_1[idx_shot]

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
                                pops_arr[idx_cen_start][idx_cen_stop] += 1
                    pops_arr[idx_cen_start][:] = pops_arr[idx_cen_start][:] / len(blob_distribution)

                ##### using the population array, take out the Z data
                ##### Z_mat contains the amount of population remaining in the initial blob after a pulse
                ##### in theory when no pulse is applied, majority of population remains,
                ##### then when a pulse occurs the population should transfer to another state

                for idx_cen in range(cen_num):
                    Z_mat[idx_cen][idx_amp, idx_freq] = pops_arr[idx_cen, idx_cen]

                ####### plotting data
                if idx_freq == 0 and idx_amp==0:  #### if first sweep add a colorbar

                    ### loop over all clusters and plot out
                    for idx_cen in range(cen_num):
                        #### plotting
                        ax_plots.append(axs[idx_cen].imshow(
                                        Z_mat[idx_cen],
                                        aspect='auto',
                                        extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                                                Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                                        origin='lower',
                                        interpolation='none',
                        ) )

                        colorbars.append(fig.colorbar(ax_plots[idx_cen], ax=axs[idx_cen], extend='both') )
                        colorbars[idx_cen].set_label('population (%)', rotation=90)

                        axs[idx_cen].set_ylabel("qubit gain")
                        axs[idx_cen].set_xlabel("qubit frequency (GHz)")
                        axs[idx_cen].set_title("population of blob: " + str(idx_cen))

                else:
                    ### loop over all clusters and plot out
                    for idx_cen in range(cen_num):
                        ax_plots[idx_cen].set_data(Z_mat[idx_cen])
                        ax_plots[idx_cen].set_clim(vmin=np.nanmin(Z_mat[idx_cen]))
                        ax_plots[idx_cen].set_clim(vmax=np.nanmax(Z_mat[idx_cen]))
                        # colorbars[idx_cen].remove()
                        # cbar0 = fig.colorbar(ax_plots[idx_cen], ax=axs[0], extend='both')
                        # cbar0.set_label('a.u.', rotation=90)

                ### plot as data is taken
                plt.tight_layout()
                plt.show(block=False)
                plt.pause(0.1)

                if idx_freq == 0 and idx_amp ==0:  ### during the first run create a time estimate for the data aqcuisition
                    t_delta = time.time() - start  ### time for single full row in seconds
                    timeEst = t_delta * len(X) * len(Y)
                    StopTime = startTime + datetime.timedelta(seconds=timeEst)
                    print('Time for 1 sweep: ' + str(round(t_delta / 60, 2)) + ' min')
                    print('estimated total time: ' + str(round(timeEst / 60, 2)) + ' min')
                    print('estimated end: ' + StopTime.strftime("%Y/%m/%d %H:%M:%S"))




        #### save the data
        data = {'config': self.cfg, 'data': {
                                        'Z_mat': Z_mat,
                                        'qubit_freqs': self.qubit_freqs, 'qubit_amps': self.qubit_amps,
                                        'i_0_arr': i_0_arr, 'q_0_arr': q_0_arr,
                                        'i_1_arr': i_1_arr, 'q_1_arr': q_1_arr,
                                             }
                }

        self.data = data

        #### plot and save the figure
        plt.savefig(self.iname, dpi = 600)  #### save the figure
        plt.show()


        return data

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

