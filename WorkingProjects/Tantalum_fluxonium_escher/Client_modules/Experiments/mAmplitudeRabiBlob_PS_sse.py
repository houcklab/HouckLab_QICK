from qick import *
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.CoreLib.Experiment import ExperimentClass # used to be WTF
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Helpers import SingleShot_ErrorCalc_2 as sse2
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Helpers.MixedShots_analysis import *


class LoopbackProgramAmplitudeRabi_PS_sse(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        ### set up the experiment updates, only runs it once
        cfg["start"] = 0
        cfg["step"] = 0
        cfg["reps"] = cfg["shots"]
        cfg["expts"] = 1

        ### Configure Resonator Tone
        res_ch = cfg["res_ch"]
        self.declare_gen(ch=res_ch, nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"],
                         ro_ch=cfg["ro_chs"][0])  # Declare the resonator channel
        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=res_ch,
                                  ro_ch=cfg["ro_chs"][0])  # Convert to clock ticks
        self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0,
                                 gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"]), )  # define the pulse

        ### Configure the Qubit Tone
        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_gain = self.sreg(cfg["qubit_ch"], "gain")  # get frequency register for qubit_ch
        qubit_ch = cfg["qubit_ch"]  # Get the qubit channel
        self.declare_gen(ch=qubit_ch, nqz=cfg["qubit_nqz"])  # Declare the qubit channel
        qubit_freq = self.freq2reg(cfg["qubit_freq"], gen_ch=cfg["qubit_ch"])  # Convert qubit length to clock ticks
        self.qubit_freq = qubit_freq
        # Define the qubit pulse
        if cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit")
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4
        elif cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit", length=self.us2cycles(self.cfg["flat_top_length"]))
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4 + self.us2cycles(self.cfg["flat_top_length"])
        else:
            print("define pi or flat top pulse")

        ### Declare ADC Readout
        for ro_ch in cfg["ro_chs"]:
            self.declare_readout(ch=ro_ch, freq=cfg["read_pulse_freq"],
                                 length=self.us2cycles(self.cfg["read_length"]), gen_ch=cfg["res_ch"])

        # Calculate length of trigger pulse
        self.cfg["trig_len"] = self.us2cycles(self.cfg["trig_buffer_start"] + self.cfg["trig_buffer_end"],
                                              gen_ch=cfg["qubit_ch"]) + self.qubit_pulseLength  ####

        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        ### intial pause
        self.sync_all(self.us2cycles(0.010))

        if self.cfg["qubit_gain"] != 0 and self.cfg["use_switch"] and self.cfg["initialize_pulse"]:
            self.trigger(pins=[0], t=self.us2cycles(self.cfg["trig_delay"]),
                         width=self.cfg["trig_len"])  # trigger for switc

        if self.cfg["initialize_pulse"]:
            self.set_pulse_registers(ch=self.cfg["qubit_ch"], style=self.cfg["qubit_pulse_style"], freq=self.qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=self.cfg["qubit_ch"]), gain=self.cfg["initialize_qubit_gain"],
                                     waveform="qubit", length=self.us2cycles(self.cfg["flat_top_length"]))
            self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse

        ### Post Selection Measurement
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait = False)

        self.sync_all(self.us2cycles(0.01))

        if self.cfg["qubit_gain"] != 0 and self.cfg["use_switch"]:
            self.trigger(pins=[0], t=self.us2cycles(self.cfg["trig_delay"]),
                         width=self.cfg["trig_len"])  # trigger for switc

        self.set_pulse_registers(ch=self.cfg["qubit_ch"], style=self.cfg["qubit_pulse_style"], freq=self.qubit_freq,
                                 phase=self.deg2reg(90, gen_ch=self.cfg["qubit_ch"]), gain=self.cfg["qubit_gain"],
                                 waveform="qubit", length=self.us2cycles(self.cfg["flat_top_length"]))
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

class AmplitudeRabi_PS_sse(ExperimentClass):
    """
    Use post selection at a thermal state and apply rabi pulse
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None,
                 progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg,
                         config_file=config_file, progress=progress)

    def acquire(self, plotProgress = False):

        # Defining the sweeps
        qubit_freq_vec = np.linspace(self.cfg["qubit_freq_start"], self.cfg["qubit_freq_stop"],
                                     self.cfg["RabiNumPoints"])
        qubit_gain_vec = (np.arange(0, self.cfg["qubit_gain_expts"]) * self.cfg["qubit_gain_step"] +
                          self.cfg["qubit_gain_start"])

        # Defining the variables to store all data
        i_0_arr = np.full((qubit_gain_vec.size, qubit_freq_vec.size, int(self.cfg["shots"])), np.nan)
        q_0_arr = np.full((qubit_gain_vec.size, qubit_freq_vec.size, int(self.cfg["shots"])), np.nan)
        i_1_arr = np.full((qubit_gain_vec.size, qubit_freq_vec.size, int(self.cfg["shots"])), np.nan)
        q_1_arr = np.full((qubit_gain_vec.size, qubit_freq_vec.size, int(self.cfg["shots"])), np.nan)

        for indx_gain in range(qubit_gain_vec.size):
            # Change qubit gain
            self.cfg["qubit_gain"] = qubit_gain_vec[indx_gain]

            for indx_freq in range(qubit_freq_vec.size):
                # Change qubit frequency
                self.cfg["qubit_freq"] = qubit_freq_vec[indx_freq]

                # Measure and get the data
                prog = LoopbackProgramAmplitudeRabi_PS_sse(self.soccfg, self.cfg)
                i_0, i_1, q_0, q_1 = prog.acquire(self.soc, load_pulses=True, readouts_per_experiment=2,
                                                  save_experiments=[0, 1])

                # Saving the data
                i_0_arr[indx_gain, indx_freq, :] = i_0
                q_0_arr[indx_gain, indx_freq, :] = q_0
                i_1_arr[indx_gain, indx_freq, :] = i_1
                q_1_arr[indx_gain, indx_freq, :] = q_1

        data = {'config': self.cfg, 'data': {'qubit_freq_vec': qubit_freq_vec, 'qubit_gain_vec': qubit_gain_vec,
                                             'i_0': i_0_arr, 'q_0': q_0_arr,'i_1': i_1_arr,
                                             'q_1': q_1_arr, }}
        self.data = data
        return data

    def process_data(self, data=None, **kwargs):
        if data is None:
            data = self.data

        i_0 = data["data"]["i_0"]
        q_0 = data["data"]["q_0"]
        i_1 = data["data"]["i_1"]
        q_1 = data["data"]["q_1"]
        qubit_freq_vec = data["data"]["qubit_freq_vec"]
        qubit_gain_vec = data["data"]["qubit_gain_vec"]

        if "cen_num" in kwargs:
            cen_num = kwargs["cen_num"]
        else:
            cen_num = 2

        ### Create empty arrays to save data
        # start blob x end blob x qubit_gain_vec x qubit_freq_vec
        pop = np.zeros((cen_num, cen_num, i_0.shape[0], i_0.shape[1]))
        centers = []

        for indx_gain in range(qubit_gain_vec.size):
            centers.append([])
            for indx_freq in range(qubit_freq_vec.size):
                ### Perform post selection for the initial data for two centers
                ### by selecting points withing some confidence bound.
                iq_data_0 = np.stack((i_0[indx_gain, indx_freq, :], q_0[indx_gain, indx_freq, :]), axis=0)
                iq_data_1 = np.stack((i_1[indx_gain, indx_freq, :], q_1[indx_gain, indx_freq, :]), axis=0)

                if indx_gain == 0 and indx_freq == 0:
                    # Get centers
                    centers[indx_gain].append(sse2.getCenters(iq_data_0, cen_num))
                else:
                    centers[indx_gain].append(sse2.getCenters(iq_data_0, cen_num, init_guess=centers[0][0]))

                # Fit Gaussian
                if 'bin_size' in kwargs:
                    bin_size = kwargs['bin_size']
                else:
                    bin_size = 51
                hist2d = sse2.createHistogram(iq_data_0, bin_size)
                no_of_params = 4
                gaussians_0, popt, x_points_0, y_points_0 = sse2.findGaussians(hist2d, centers[indx_gain][indx_freq], cen_num)

                # create bounds given current fit
                bound = [popt - 1e-5, popt + 1e-5]

                for idx_bound in range(cen_num):
                    bound[0][0 + int(idx_bound*no_of_params)] = 0
                    bound[1][0 + int(idx_bound * no_of_params)] = np.inf

                # Get probability function
                pdf_0 = sse2.calcPDF(gaussians_0)

                # Calculate the probability
                probability = np.zeros((cen_num, iq_data_0.shape[1]))
                for i in range(cen_num):
                    for j in range(iq_data_0.shape[1]):
                        # find the x,y point closest to the i,q point
                        indx_i = np.argmin(np.abs(x_points_0 - iq_data_0[0, j]))
                        indx_q = np.argmin(np.abs(y_points_0 - iq_data_0[1, j]))
                        # Calculate the probability
                        probability[i, j] = pdf_0[i][indx_i, indx_q]

                # Find the sorted data
                sorted_prob = np.zeros((cen_num, iq_data_0.shape[1]))
                sorted_data_0 = np.zeros((cen_num,) + iq_data_0.shape)
                sorted_data_1 = np.zeros((cen_num,) + iq_data_1.shape)

                for i in range(cen_num):
                    sorted_indx = np.argsort(-probability[i, :])
                    sorted_prob[i, :] = probability[i, sorted_indx]
                    sorted_data_0[i, :, :] = iq_data_0[:, sorted_indx]
                    sorted_data_1[i, :, :] = iq_data_1[:, sorted_indx]

                # Selecting the points in the confidence regime and calculating the populations
                if 'confidence' in kwargs:
                    confidence = kwargs["confidence"]
                else:
                    confidence = 0.80

                # Calculating the populations
                for i in range(cen_num):
                    indx_confidence = np.argmin(np.abs(sorted_prob[i, :] - confidence))
                    selected_data = sorted_data_1[i, :, 0:indx_confidence + 1]

                    # Fit Gaussians
                    bin_size = 25
                    hist2d = sse2.createHistogram(selected_data, bin_size)
                    gaussians_1, popt, x_points_1, y_points_1 = sse2.findGaussians(hist2d, centers[indx_gain][indx_freq], cen_num,
                                                                                   input_bounds=bound, p_guess=popt)

                    # Get probability function
                    pdf = sse2.calcPDF(gaussians_1)
                    # Get the expected values of probability and error
                    num_samples_1 = sse2.calcNumSamplesInGaussian(hist2d, pdf, cen_num)
                    num_std_1 = sse2.calcNumSamplesInGaussianSTD(hist2d, pdf, cen_num)
                    prob_1, std_1 = sse2.calcProbability(num_samples_1, num_std_1, cen_num)
                    pop[i, :, indx_gain, indx_freq] = prob_1

        update_data = {"data" : {"pdf_0": pdf_0, "gaussians_0": gaussians_0, "x_points_0": x_points_0,
                                 "y_points_0": y_points_0, "centers": centers, "pop": pop}}
        data["data"] = data["data"] | update_data["data"]
        self.data = data
        return data

    def display(self, data=None, plotDisp=False, saveFig = True, **kwargs):
        if data is None:
            data = self.data

        if "cen_num" in kwargs:
            cen_num = kwargs["cen_num"]
        else:
            cen_num = 2

        # Extracting data
        i_0 = data["data"]["i_0"]
        q_0 = data["data"]["q_0"]
        qubit_freq_vec = data["data"]["qubit_freq_vec"]
        qubit_gain_vec = data["data"]["qubit_gain_vec"]
        pop = data["data"]["pop"]
        pdf_0 = data["data"]["pdf_0"]
        gaussians_0 = data["data"]["gaussians_0"]
        x_points_0 = data["data"]["x_points_0"]
        y_points_0 = data["data"]["y_points_0"]
        centers = data["data"]["centers"]

        # Plotting
        gs = gridspec.GridSpec(cen_num, 2, width_ratios=[1, 1.2])
        fig = plt.figure(figsize=[12, 5 * cen_num])

        # Plot the blob distribution
        blob_axs = plt.subplot(gs[:, 0])
        iq_data = np.stack((i_0[-1, -1, :], q_0[-1,-1, :]), axis=0)
        sse2.plotFitAndData(pdf_0, gaussians_0, x_points_0, y_points_0, centers[-1][-1], iq_data, fig, blob_axs)

        # Plot the Rabi Blob Distribution
        subplot_right = []
        for idx_start in range(cen_num):
            subplot_right.append(plt.subplot(gs[idx_start, 1]))
            subplot_right[idx_start].imshow(pop[idx_start, idx_start, :,:],
                                            extent=[qubit_freq_vec[0], qubit_freq_vec[-1], qubit_gain_vec[0],
                                                    qubit_gain_vec[-1]],
                                            origin='lower',interpolation='none',aspect = 'auto')
            subplot_right[idx_start].set_xlabel("Qubit Frequency (in MHz)")
            subplot_right[idx_start].set_ylabel("Qubit Gain (DAC Unit)")

        data_information = ("Fridge Temperature = " + str(self.cfg["fridge_temp"]) + "mK, Yoko_Volt = "
                            + str(self.cfg["yokoVoltage_freqPoint"]) + "V, relax_delay = " + str(
                    self.cfg["relax_delay"])
                            + "us." )
        plt.suptitle(self.outerFolder + '\n' + self.path_wDate + '\n' + data_information)
        plt.tight_layout()
        if saveFig:
            plt.savefig(self.iname, dpi=400)

        if plotDisp:
            plt.show()
        plt.close()
    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

