from qick import *
import matplotlib
#matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.CoreLib.Experiment import ExperimentClass # used to be WTF
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Helpers.hist_analysis import *
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Helpers.MixedShots_analysis import *
from tqdm.notebook import tqdm
import time
from sklearn.cluster import KMeans
import math
from scipy.optimize import curve_fit

class LoopbackProgramAmplitudeRabi_PS(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        # Set up the experiment
        cfg["start"] = 0
        cfg["step"] = 0
        cfg["reps"] = cfg["shots"]
        cfg["expts"] = 1

        # Define the resonator
        res_ch = cfg["res_ch"]
        self.declare_gen(ch=res_ch, nqz=cfg["nqz"], ro_ch=cfg["ro_chs"][0])
        '''Convert frequency to dac frequency (ensuring it is an available adc frequency)'''
        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=res_ch, ro_ch=cfg["ro_chs"][0])
        self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0,
                                 gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"], gen_ch = self.cfg["res_ch"]))

        # Define the readout ADC
        for ro_ch in cfg["ro_chs"]:
            self.declare_readout(ch=ro_ch, freq=cfg["read_pulse_freq"],
                                 length=self.us2cycles(self.cfg["read_length"], ro_ch = self.cfg["res_ch"]),
                                 gen_ch=cfg["res_ch"])

        # Define the qubit tone
        self.q_rp = self.ch_page(self.cfg["qubit_ch"])
        self.r_gain = self.sreg(self.cfg["qubit_ch"], "gain")
        qubit_ch = cfg["qubit_ch"]
        self.declare_gen(ch=qubit_ch, nqz=cfg["qubit_nqz"])
        ''' convert frequency to dac frequency (ensuring it is an available adc frequency) '''
        qubit_freq = self.freq2reg(cfg["qubit_freq"], gen_ch=qubit_ch)
        self.qubit_freq = qubit_freq
        if cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"], gen_ch = self.cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"], gen_ch = self.cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit")
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"], gen_ch = self.cfg["qubit_ch"]) * 4
        elif cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"], gen_ch = self.cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"], gen_ch = self.cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit", length=self.us2cycles(self.cfg["flat_top_length"], gen_ch = self.cfg["qubit_ch"]))
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"], gen_ch = self.cfg["qubit_ch"]) * 4 + self.us2cycles(self.cfg["flat_top_length"])

        else:
            print("define pi or flat top pulse")



        # Calculate length of trigger pulse
        self.cfg["trig_len"] = self.us2cycles(self.cfg["trig_buffer_start"] + self.cfg["trig_buffer_end"],
                                              gen_ch=cfg["qubit_ch"]) + self.qubit_pulseLength  ####

        self.synci(200)  # give processor some time to configure pulses


    def body(self):
        # Pause for sanity
        self.sync_all(self.us2cycles(0.010, gen_ch = self.cfg["res_ch"]))

        # Initialization Pulse, if desired. It will be a flat_top pulse
        if self.cfg["qubit_gain"] != 0 and self.cfg["use_switch"] and self.cfg["initialize_pulse"]:
            # Calculate pulse length
            self.qubit_pulseLength = (self.us2cycles(self.cfg["sigma"], gen_ch = self.cfg["qubit_ch"]) * 4
                                      + self.us2cycles(self.cfg["flat_top_length"],gen_ch = self.cfg["qubit_ch"]))

            trig_len = self.us2cycles(self.cfg["trig_buffer_start"] + self.cfg["trig_buffer_end"],
                                      gen_ch=self.cfg["qubit_ch"]) + self.qubit_pulseLength
            self.trigger(pins=[0], t=self.us2cycles(self.cfg["trig_delay"], gen_ch = self.cfg["qubit_ch"]),
                         width=trig_len)

        if self.cfg["initialize_pulse"]:
            init_qubit_freq =  self.freq2reg(self.cfg["initialize_qubit_freq"], gen_ch=self.cfg["qubit_ch"])
            self.set_pulse_registers(ch=self.cfg["qubit_ch"], style="flat_top", freq=init_qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=self.cfg["qubit_ch"]), gain=self.cfg["initialize_qubit_gain"],
                                     waveform="qubit", length=self.us2cycles(self.cfg["flat_top_length"]))
            self.pulse(ch=self.cfg["qubit_ch"])

        self.sync_all(self.us2cycles(0.005, gen_ch = self.cfg["res_ch"]))
        # measure beginning thermal state
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"], gen_ch = self.cfg["res_ch"]),
                     wait = False)

        self.sync_all(self.us2cycles(0.005))

        if self.cfg["qubit_gain"] != 0 and self.cfg["use_switch"]:
            self.trigger(pins=[0], t=self.us2cycles(self.cfg["trig_delay"]),
                         width=self.cfg["trig_len"])  # trigger for switc

        self.set_pulse_registers(ch=self.cfg["qubit_ch"], style=self.cfg["qubit_pulse_style"], freq=self.qubit_freq,
                                 phase=self.deg2reg(90, gen_ch=self.cfg["qubit_ch"]), gain=self.cfg["qubit_gain"],
                                 waveform="qubit",
                                 length=self.us2cycles(self.cfg["flat_top_length"], gen_ch=self.cfg["qubit_ch"]))
        self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse

        self.sync_all(self.us2cycles(0.005, gen_ch = self.cfg["res_ch"]))  # align channels and wait 50ns)

        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg['ro_chs'],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"], gen_ch = self.cfg["res_ch"]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))


    def update(self):
        self.mathi(self.q_rp, self.r_gain, self.r_gain, '+', self.cfg["step"]) # update frequency list index

    def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=2, save_experiments=[0,1],
                start_src="internal", progress=False, debug=False):

        super().acquire(soc, load_pulses=load_pulses, progress=progress) # qick update, debug=debug)

        length = self.us2cycles(self.cfg['read_length'], ro_ch=self.cfg["ro_chs"][0])
        data = self.get_raw()
        shots_i0 = np.array(data)[0, :, 0, 0]/ length
        shots_q0 = np.array(data)[0, :, 0, 1]/ length
        shots_i1 = np.array(data)[0, :, 1, 0]/ length
        shots_q1 = np.array(data)[0, :, 1, 1]/ length
        i_0 = shots_i0
        i_1 = shots_i1
        q_0 = shots_q0
        q_1 = shots_q1

        return i_0, i_1, q_0, q_1


    # def collect_shots(self):
    #     shots_i0=self.di_buf[0]/self.us2cycles(self.cfg['read_length'], ro_ch = 0)
    #     shots_q0=self.dq_buf[0]/self.us2cycles(self.cfg['read_length'], ro_ch = 0)
    #
    #     i_0 = shots_i0[0::2]
    #     i_1 = shots_i0[1::2]
    #     q_0 = shots_q0[0::2]
    #     q_1 = shots_q0[1::2]
    #
    #     return i_0, i_1, q_0, q_1


# ====================================================== #

class AmplitudeRabi_PS(ExperimentClass):
    """
    Use post selection at a thermal state and apply rabi pulse
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False, plotDisp=True, figNum=1):
        plt.ion()
        ### define frequencies to sweep over
        expt_cfg = {
            ### qubit freq parameters
            "qubit_freq_start": self.cfg["qubit_freq_start"],
            "qubit_freq_stop": self.cfg["qubit_freq_stop"],
            "RabiNumPoints": self.cfg["RabiNumPoints"],  ### number of points
            ### rabi amp parameters
            "qubit_gain_start": self.cfg["qubit_gain_start"],
            "qubit_gain_step": self.cfg["qubit_gain_step"],
            "qubit_gain_expts": self.cfg["qubit_gain_expts"],  #### plus one to account for 0 index
        }

        ### define qubit frequency array
        self.qubit_freqs = np.linspace(expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"],
                                       expt_cfg["RabiNumPoints"])
        self.qubit_amps = np.arange(0, expt_cfg["qubit_gain_expts"]) * expt_cfg["qubit_gain_step"] + expt_cfg[
            "qubit_gain_start"]

        X = self.qubit_freqs / 1e3  # put into units of GHz
        Y = self.qubit_amps
        if len(self.qubit_freqs) != 1 and len(self.qubit_amps) !=  1:
            X_step = X[1] - X[0]
            Y_step = Y[1] - Y[0]
            self.single_sweep = False
        else:
            self.single_sweep = True

        Z_mat = np.full((self.cfg["cen_num"], len(Y), len(X)), np.nan)
        ### create array for storing the data
        self.data = {
            'config': self.cfg,
            'data': {'Z_mat': Z_mat,
                     'qubit_freqs': self.qubit_freqs, 'qubit_amps': self.qubit_amps,
                     }
        }

        ##### create arrays to store all the raw data
        i_0_arr = np.full((len(self.qubit_amps), len(self.qubit_freqs), int(self.cfg["shots"])), np.nan)
        q_0_arr = np.full((len(self.qubit_amps), len(self.qubit_freqs), int(self.cfg["shots"])), np.nan)
        i_1_arr = np.full((len(self.qubit_amps), len(self.qubit_freqs), int(self.cfg["shots"])), np.nan)
        q_1_arr = np.full((len(self.qubit_amps), len(self.qubit_freqs), int(self.cfg["shots"])), np.nan)

        ##### set up figure
        cen_num = self.cfg["cen_num"]
        fig, axs = plt.subplots(cen_num, cen_num, figsize=[14, 10])
        ax_plots = []
        colorbars = []

        #### start a timer for estimating the time for the scan
        startTime = datetime.datetime.now()
        print('')  ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        start = time.time()

        #### loop over qubit gains
        for idx_freq in range(len(self.qubit_freqs)):

            #### set new qubit frequency and aquire data
            self.cfg["qubit_freq"] = self.qubit_freqs[idx_freq]

            #### loop over qubit frequencies
            for idx_amp in range(len(self.qubit_amps)):

                self.cfg["qubit_gain"] = self.qubit_amps[idx_amp]

                #### pull the data from the single shots for the first run
                prog = LoopbackProgramAmplitudeRabi_PS(self.soccfg, self.cfg)
                i_0, i_1, q_0, q_1 = prog.acquire(self.soc, load_pulses=True, readouts_per_experiment=2,
                                                  save_experiments=[0, 1])

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
                    iData_0 = blobs_0[idx_cen_start][0][~np.isnan(blobs_0[idx_cen_start][0])]
                    qData_0 = blobs_0[idx_cen_start][1][~np.isnan(blobs_0[idx_cen_start][1])]
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

                    # Quick Plotting the selected data
                    axs[idx_cen_start, 0].clear()
                    axs[idx_cen_start, 0].plot(iData_0, qData_0, '.', c=colors[0], alpha=0.5,
                                               label="initial")
                    axs[idx_cen_start, 0].plot(iData, qData, '.', c=colors[1], alpha=0.5,
                                               label="final")
                    axs[idx_cen_start, 0].set_title("Cluster" + str(idx_cen_start))
                    axs[idx_cen_start, 0].set_xlabel("I")
                    axs[idx_cen_start, 0].set_ylabel("Q")
                    axs[idx_cen_start, 0].set_aspect('equal')

                ##### using the population array, take out the Z data
                ##### Z_mat contains the amount of population remaining in the initial blob after a pulse
                ##### in theory when no pulse is applied, majority of population remains,
                ##### then when a pulse occurs the population should transfer to another state

                for idx_cen in range(cen_num):
                    Z_mat[idx_cen][idx_amp, idx_freq] = pops_arr[idx_cen, idx_cen]

                # plotting data
                if idx_freq == 0 and idx_amp == 0:

                    if self.single_sweep:
                        # Check which axis of Z_mat is of size 1
                        if len(X) == 1:
                            sweep_axis = Y
                            sweep_name = "qubit gain"
                            Z_plot = Z_mat[:,:,0]
                            idx = idx_amp + 1
                        else:
                            sweep_axis = X
                            sweep_name = "qubit frequency (GHz)"
                            Z_plot = Z_mat[:, 0, :]
                            idx = idx_freq + 1

                        # Use scatter plot to plot the sweep axis
                        for idx_cen in range(cen_num):
                            sc = axs[idx_cen, 1].scatter(sweep_axis[0: idx], Z_plot[idx_cen,0:idx], c=colors[idx_cen], label="Cluster" + str(idx_cen))
                            ax_plots.append(sc)
                            axs[idx_cen, 1].set_xlabel(sweep_name)
                            axs[idx_cen, 1].set_ylabel("population (%)")
                            axs[idx_cen, 1].set_title("population of blob: " + str(idx_cen))


                    else:
                        ### loop over all clusters and plot out
                        for idx_cen in range(cen_num):
                            ax_plots.append(axs[idx_cen, 1].imshow(
                                Z_mat[idx_cen],
                                aspect='auto',
                                extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                                        Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                                origin='lower',
                                interpolation='none',
                            ))

                            colorbars.append(fig.colorbar(ax_plots[idx_cen], ax=axs[idx_cen, 1], extend='both'))
                            colorbars[idx_cen].set_label('population (%)', rotation=90)

                            axs[idx_cen, 1].set_ylabel("qubit gain")
                            axs[idx_cen, 1].set_xlabel("qubit frequency (GHz)")
                            axs[idx_cen, 1].set_title("population of blob: " + str(idx_cen))

                else:
                    if self.single_sweep:
                        # Check which axis of Z_mat is of size 1
                        if len(X) == 1:
                            sweep_axis = Y
                            sweep_name = "qubit gain"
                            Z_plot = Z_mat[:, :, 0]
                            idx = idx_amp + 1
                        else:
                            sweep_axis = X
                            sweep_name = "qubit frequency (GHz)"
                            Z_plot = Z_mat[:, 0, :]
                            idx = idx_freq + 1

                        for idx_cen in range(cen_num):
                            axs[idx_cen, 1].cla()
                            axs[idx_cen, 1].scatter(sweep_axis[0: idx], Z_plot[idx_cen,0:idx], c=colors[idx_cen], label="Cluster" + str(idx_cen))
                            axs[idx_cen, 1].set_xlabel(sweep_name)
                            axs[idx_cen, 1].set_ylabel("population (%)")
                            axs[idx_cen, 1].set_title("population of blob: " + str(idx_cen))


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
                if idx_freq == 0 and idx_amp == 0:
                    plt.show(block=False)
                else:
                    plt.draw()
                plt.pause(5)

                if idx_freq == 0 and idx_amp == 0:  ### during the first run create a time estimate for the data aqcuisition
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
        plt.savefig(self.iname, dpi=600)  #### save the figure
        plt.show()

        return data

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

