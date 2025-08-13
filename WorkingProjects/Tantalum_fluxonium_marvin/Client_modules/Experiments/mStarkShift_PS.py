"""
Created on 11th August 2025
@author: pjatakia
This code performs qubit spectroscopy while sweeping cavity power to see the AC stark shift on the qubit.
This uses post selection on the qubit initial state so that it can be used at low frequency flux points.
There are going to be a lot of options in which the stark shift experiment can happen
1. The qubit tone is applied after the cavity is populated
2. The qubit tone is applied during the cavity is populated
    a. Along with the cavity population (left aligned)
    b. At the end of the cavity population (right aligned)
3. The qubit tone is periodic
4. The cavity tone is periodic
5. Both are periodic
"""
"""
Pulse Sequence Description — Stark Shift Experiment
----------------------------------------------------
This experiment applies a population (Stark shift) tone to the resonator,
followed by a qubit drive, and finally a readout pulse to measure the qubit
state. Timing is adjustable via cfg parameters.

Sequence:

Resonator channel (res_ch):
  1. Population pulse (pop_length, gain=pop_gain)
  2. Delay before readout (pre_meas_delay)
  3. Readout pulse (read_length, gain=read_pulse_gain)

Qubit channel (qubit_ch):
  0. Qubit Pulse (qubit_lenth, gain= initializede_qubit_gain)
     - Initializes the qubit to 50-50 ideally
  1. Qubit pulse (qubit_length, gain=qubit_gain)
     - Starts either simultaneously with resonator pop pulse 
       or after post_pop_tone_delay (cfg['simultaneous'] flag)

ADC:
  1. Samples during the readout pulse, starting after adc_trig_offset

Key cfg parameters controlling timing:
  pop_length, pop_gain
  qubit_length, qubit_gain, qubit_periodic
  post_pop_tone_delay, pre_meas_delay
  read_length, read_pulse_gain
  adc_trig_offset, relax_delay
"""

from qick import *
import matplotlib.pyplot as plt
import numpy as np
from tqdm.notebook import tqdm
import time
import datetime
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Helpers import SingleShot_ErrorCalc_2 as sse2
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Helpers.MixedShots_analysis import *
import matplotlib.gridspec as gridspec

class LoopbackProgramStarkSlicePS(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)
        self.qubit_tone_delay = None
        self.pre_meas_delay = None
        self.post_pop_tone_delay = None
        self.qubit_pulseLength = None
        self.qubit_freq = None
        self.q_start = None
        self.q_step = None
        self.q_r_gain = None
        self.q_rp = None
        self.f_res = None

    def initialize(self):
        # # ----- Standard Declaration -------
        # # Define Readout
        for ch in self.cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(self.cfg["read_length"], gen_ch=self.cfg["res_ch"]),
                                 freq=self.cfg["read_pulse_freq"], gen_ch=self.cfg["res_ch"])

        # # Define Resonator tone
        self.declare_gen(ch=self.cfg["res_ch"], nqz=self.cfg["nqz"])
        # convert frequency to dac frequency (ensuring it is an available adc frequency)
        self.f_res = self.freq2reg(self.cfg["read_pulse_freq"], gen_ch=self.cfg["res_ch"], ro_ch=self.cfg["ro_chs"][0])
        # Adding the resonator pulse for pop_length duration with a gain of pop_gain
        if self.cfg['ro_periodic']:
            self.set_pulse_registers(ch=self.cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=self.f_res, phase=0,
                                     gain=self.cfg["read_pulse_gain"],
                                     length=self.us2cycles(self.cfg["read_length"], gen_ch=self.cfg["res_ch"]), mode="periodic")
        elif not self.cfg['ro_periodic']:
            self.set_pulse_registers(ch=self.cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=self.f_res, phase=0,
                                     gain=self.cfg["read_pulse_gain"],
                                     length=self.us2cycles(self.cfg["read_length"], gen_ch=self.cfg["res_ch"]))

        # # Define Qubit Tone
        self.declare_gen(ch=self.cfg["qubit_ch"], nqz=self.cfg["qubit_nqz"])  # Qubit
        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.q_r_gain = self.sreg(self.cfg["qubit_ch"], "gain")  # get frequency register for qubit_ch
        self.qubit_freq = self.freq2reg(self.cfg["qubit_freq"], gen_ch=self.cfg["qubit_ch"])
        self.qubit_freq_base = self.freq2reg(self.cfg["qubit_freq_base"], gen_ch = self.cfg['qubit_ch'])
        # add qubit and readout pulses to respective channels
        if self.cfg["qubit_pulse_style"] == "const":
            if self.cfg["qubit_periodic"]:
                self.set_pulse_registers(ch=self.cfg["qubit_ch"], style="const", freq=self.qubit_freq, phase=0,
                                         gain=self.cfg["qubit_gain"],
                                         length=self.us2cycles(self.cfg["qubit_length"], gen_ch=self.cfg["qubit_ch"]),
                                         mode="periodic")
                self.qubit_pulseLength = self.us2cycles(self.cfg["qubit_length"],gen_ch=self.cfg["qubit_ch"])
            else:
                self.set_pulse_registers(ch=self.cfg["qubit_ch"], style="const", freq=self.qubit_freq, phase=0,
                                         gain=self.cfg["qubit_gain"],
                                         length=self.us2cycles(self.cfg["qubit_length"],gen_ch=self.cfg["qubit_ch"]))
                self.qubit_pulseLength = self.us2cycles(self.cfg["qubit_length"],gen_ch=self.cfg["qubit_ch"])
        else:
            raise Exception("The code only supports const QUBIT pulses :(")

        # # ------ Declarations for Stark Shift ---------
        # # Defining two delays
        # Gap between the populating tone and qubit tone (In the case the qubit tone proceeds the cavity tone)
        self.post_pop_tone_delay = self.us2cycles(self.cfg["post_pop_tone_delay"], gen_ch = self.cfg['res_ch'])
        # Gap between the end of qubit tone / populating tone and the final measurement
        self.pre_meas_delay = self.us2cycles(self.cfg["pre_meas_delay"], gen_ch = self.cfg['res_ch'])

        # # Defining alignments
        self.qubit_tone_delay = 'auto'
        if 'align' in self.cfg.keys():
            if self.cfg['align'] == 'right':
                if self.cfg['pop_length'] < self.cfg["qubit_length"] :
                    raise Exception("The read length needs to be bigger to align right ")
                else:
                    self.qubit_tone_delay = self.us2cycles(self.cfg['pop_length'] - self.cfg["qubit_length"])

        # # Calculate length of trigger pulse
        # switch is open while populating pulse is playing
        self.cfg["trig_len"] = self.us2cycles(self.cfg["trig_buffer_start"] + self.cfg["trig_buffer_end"],
                                              gen_ch=self.cfg["res_ch"]) + self.us2cycles(self.cfg["pop_length"])

        # # --------- Miscellaneous Declaration
        self.cfg["start"] = 0
        self.cfg["step"] = 0
        self.cfg["reps"] = self.cfg["shots"]
        self.cfg["expts"] = 1

        # Just Displaying what the experiment is going to be
        if self.cfg['display_params']:
            print(f"The qubit mode is periodic = {self.cfg['qubit_periodic']}")
            print(f"The readout mode is periodic = {self.cfg['ro_periodic']}")
            if self.cfg['qubit_periodic'] or self.cfg['ro_periodic']:
                print(f"The qubit tone alignment may matter")
            print(f"The two tones are being played simultaneously = {self.cfg['simultaneous']}")
            if 'align' in self.cfg.keys():
                print(f"The current alignment setting is {self.cfg['align']}")
            print(f"The gain of the population pulse is {self.cfg['pop_gain']} and length is {self.cfg['pop_length']}")
            print(f"The gain of the readout pulse is {self.cfg['read_pulse_gain']} and length is {self.cfg['read_length']}")
            print(f"The gap between the population pulse and qubit tone pulse is {self.cfg['post_pop_tone_delay']}")
            print(f"The gap between the tones and the final readout is {self.cfg['pre_meas_delay']}")

        self.sync_all(self.us2cycles(200))

    def body(self):

        self.sync_all(self.us2cycles(1))  # align channels and wait 10ns

        if self.cfg['initialize_pulse']:
            if self.cfg["use_switch"]:
                self.trigger(pins=[0], t=self.us2cycles(self.cfg["trig_delay"]),
                             width=self.cfg["trig_len"])  # trigger for switch
            self.set_pulse_registers(ch=self.cfg["qubit_ch"], style='const', freq=self.qubit_freq_base,
                                     phase=0,
                                     gain=self.cfg["initialize_qubit_gain"],
                                     length=self.us2cycles(self.cfg["qubit_length"], gen_ch = self.cfg['qubit_ch']))
            self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse

        self.sync_all(self.us2cycles(0.01))  # align channels and wait 10ns

        # Post Selection Measurement
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True)

        self.sync_all(self.us2cycles(self.cfg["wait_before_exp"]))  # align channels and wait 10ns

        # Redefining the resonator pulse
        if self.cfg['ro_periodic']:
            self.set_pulse_registers(ch=self.cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=self.f_res, phase=0,
                                     gain=self.cfg["pop_gain"],
                                     length=self.us2cycles(self.cfg["pop_length"], gen_ch=self.cfg["res_ch"]), mode="periodic")
        elif not self.cfg['ro_periodic']:
            self.set_pulse_registers(ch=self.cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=self.f_res, phase=0,
                                     gain=self.cfg["pop_gain"],
                                     length=self.us2cycles(self.cfg["pop_length"], gen_ch=self.cfg["res_ch"]))

        # Redefining the qubit pulse
        if self.cfg["qubit_periodic"]:
            self.set_pulse_registers(ch=self.cfg["qubit_ch"], style="const", freq=self.qubit_freq, phase=0,
                                     gain=self.cfg["qubit_gain"],
                                     length=self.us2cycles(self.cfg["qubit_length"], gen_ch=self.cfg["qubit_ch"]),
                                     mode="periodic")
            self.qubit_pulseLength = self.us2cycles(self.cfg["qubit_length"], gen_ch=self.cfg["qubit_ch"])
        else:
            self.set_pulse_registers(ch=self.cfg["qubit_ch"], style="const", freq=self.qubit_freq, phase=0,
                                     gain=self.cfg["qubit_gain"],
                                     length=self.us2cycles(self.cfg["qubit_length"], gen_ch=self.cfg["qubit_ch"]))
            self.qubit_pulseLength = self.us2cycles(self.cfg["qubit_length"], gen_ch=self.cfg["qubit_ch"])

        self.sync_all(self.us2cycles(0.01))  # align channels and wait 10ns
        # Playing pulses
        if self.cfg["use_switch"]:
            self.trigger(pins=[0], t=self.us2cycles(self.cfg["trig_delay"]),
                         width=self.cfg["trig_len"])  # trigger for switch

        if self.cfg['simultaneous']:
            self.pulse(ch=self.cfg["res_ch"])   # Play a cavity tone
            self.pulse(ch=self.cfg["qubit_ch"], t=self.qubit_tone_delay)  # Play a qubit tone
        else:
            self.pulse(ch=self.cfg["res_ch"])  # Play a cavity tone
            self.sync_all(self.post_pop_tone_delay)  # align channels and wait 10ns
            self.pulse(ch=self.cfg["qubit_ch"])  # Play a qubit tone

        self.sync_all(self.pre_meas_delay)  # align channels and wait 10ns

        # Configure the cavity pulse for readout
        self.set_pulse_registers(ch=self.cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=self.f_res, phase=0,
                                 gain=self.cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"], gen_ch=self.cfg["res_ch"]))

        self.sync_all(self.us2cycles(0.01))  # align channels and wait 10ns

        # trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"], ro_ch=self.cfg["ro_chs"][0]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.q_r_gain, self.q_r_gain, '+', self.cfg['step'])  # update gain

    def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=2, save_experiments=[0,1],
                start_src="internal", progress=False):

        super().acquire(soc, load_pulses=load_pulses, progress=progress,
                        readouts_per_experiment=2, save_experiments=[0,1])

        return self.collect_shots()

    def collect_shots(self):
        length = self.us2cycles(self.cfg['read_length'], ro_ch=self.cfg["ro_chs"][0])
        shots_i0 = np.array(self.get_raw())[0, :, :, 0, 0].reshape((self.cfg["expts"], self.cfg["reps"])) / length
        shots_q0 = np.array(self.get_raw())[0, :, :, 0, 1].reshape((self.cfg["expts"], self.cfg["reps"])) / length
        shots_i1 = np.array(self.get_raw())[0, :, :, 1, 0].reshape((self.cfg["expts"], self.cfg["reps"])) / length
        shots_q1 = np.array(self.get_raw())[0, :, :, 1, 1].reshape((self.cfg["expts"], self.cfg["reps"])) / length
        i_0 = shots_i0[0]
        i_1 = shots_i1[0]
        q_0 = shots_q0[0]
        q_1 = shots_q1[0]

        return i_0, i_1, q_0, q_1

class StarkShiftPS(ExperimentClass):
    """
    to write
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, prefix=prefix,outerFolder=outerFolder, cfg=cfg,
                         config_file=config_file, progress=progress)
        self.data_one_run = None

    def d__init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, prefix=prefix,outerFolder=outerFolder, cfg=cfg, config_file=config_file, progress=progress)

    def acquire_one_run(self):
        # Defining the sweeps
        qubit_freq_vec = np.linspace(self.cfg["qubit_freq_start"], self.cfg["qubit_freq_stop"],
                                     self.cfg["SpecNumPoints"])
        self.cfg['shots'] = self.cfg['spec_reps']

        # Defining the variables to store all data
        i_0_arr = np.full((qubit_freq_vec.size, int(self.cfg["shots"])), np.nan)
        q_0_arr = np.full((qubit_freq_vec.size, int(self.cfg["shots"])), np.nan)
        i_1_arr = np.full((qubit_freq_vec.size, int(self.cfg["shots"])), np.nan)
        q_1_arr = np.full((qubit_freq_vec.size, int(self.cfg["shots"])), np.nan)

        for indx_freq in range(qubit_freq_vec.size):
            # Change qubit frequency
            self.cfg["qubit_freq"] = qubit_freq_vec[indx_freq]

            if indx_freq == 0:
                self.cfg['display_params'] = True
            else:
                self.cfg['display_params'] = False

            # Measure and get the data
            prog = LoopbackProgramStarkSlicePS(self.soccfg, self.cfg)
            i_0, i_1, q_0, q_1 = prog.acquire(self.soc, load_pulses=True, readouts_per_experiment=2,
                                              save_experiments=[0, 1])

            # Saving the data
            i_0_arr[indx_freq, :] = i_0
            q_0_arr[indx_freq, :] = q_0
            i_1_arr[indx_freq, :] = i_1
            q_1_arr[indx_freq, :] = q_1

        data = {'data': {'qubit_freq_vec': qubit_freq_vec, 'i_0': i_0_arr, 'q_0': q_0_arr, 'i_1': i_1_arr,
                         'q_1': q_1_arr, }}
        self.data_one_run = data
        return data

    def process_data_one_run(self, data=None, **kwargs):
        if data is None:
            data = self.data_one_run

        i_0 = data["data"]["i_0"]
        q_0 = data["data"]["q_0"]
        i_1 = data["data"]["i_1"]
        q_1 = data["data"]["q_1"]
        qubit_freq_vec = data["data"]["qubit_freq_vec"]

        if "cen_num" in kwargs:
            cen_num = kwargs["cen_num"]
        else:
            cen_num = 2

        # Create empty arrays to save data
        # start blob x end blob x qubit_freq_vec
        pop = np.zeros((cen_num, cen_num, i_0.shape[0]))
        centers = []

        for indx_freq in range(qubit_freq_vec.size):

            # Perform post selection for the initial data for two centers
            # by selecting points withing some confidence bound.
            iq_data_0 = np.stack((i_0[indx_freq, :], q_0[indx_freq, :]), axis=0)
            iq_data_1 = np.stack((i_1[indx_freq, :], q_1[indx_freq, :]), axis=0)

            if 'PS_data_0' in self.data.keys() and self.data['PS_data_0']['centers'] is not None:
                centers.append(sse2.getCenters(iq_data_0, cen_num, init_guess=self.data['PS_data_0']['centers'][0]))
            elif indx_freq == 0:
                # Get centers
                centers.append(sse2.getCenters(iq_data_0, cen_num))
            else:
                centers.append(sse2.getCenters(iq_data_0, cen_num, init_guess=centers[0]))

            # Fit Gaussian
            if 'bin_size' in kwargs:
                bin_size = kwargs['bin_size']
            else:
                bin_size = 101
            hist2d = sse2.createHistogram(iq_data_0, bin_size)
            no_of_params = 4
            gaussians_0, popt, x_points_0, y_points_0 = sse2.findGaussians(hist2d, centers[indx_freq], cen_num)

            # create bounds given current fit
            bound = [popt - 1e-5, popt + 1e-5]

            for idx_bound in range(cen_num):
                bound[0][0 + int(idx_bound*no_of_params)] = 0
                bound[1][0 + int(idx_bound * no_of_params)] = np.inf

            # Get probability function
            pdf_0 = sse2.calcPDF(gaussians_0)

            # Calculate the probability
            probability = np.zeros((cen_num, iq_data_0.shape[1]))
            # print("Shape of probability array is ", probability.shape)
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
                confidence = 0.95

            # Calculating the populations
            for i in range(cen_num):
                indx_confidence = np.argmin(np.abs(sorted_prob[i, :] - confidence))
                selected_data = sorted_data_1[i, :, 0:indx_confidence + 1]

                # Fit Gaussians
                hist2d = sse2.createHistogram(selected_data, bin_size)
                gaussians_1, popt, x_points_1, y_points_1 = sse2.findGaussians(hist2d, centers[indx_freq], cen_num,
                                                                               input_bounds=bound, p_guess=popt)

                # Get probability function
                pdf = sse2.calcPDF(gaussians_1)
                # Get the expected values of probability and error
                num_samples_1 = sse2.calcNumSamplesInGaussian(hist2d, pdf, cen_num)
                # print("Number of samples selected in state ", i , " is ", num_samples_1)
                num_std_1 = sse2.calcNumSamplesInGaussianSTD(hist2d, pdf, cen_num)
                prob_1, std_1 = sse2.calcProbability(num_samples_1, num_std_1, cen_num)
                pop[i, :, indx_freq] = prob_1

        # Find the resonant frequency
        resonant_freq = qubit_freq_vec[np.argmin(pop[0,0,:])]

        update_data = {"data" : {"pdf_0": pdf_0, "gaussians_0": gaussians_0, "x_points_0": x_points_0,
                                 "y_points_0": y_points_0, "centers": centers, "pop": pop, "resonant_freq": resonant_freq}}
        data["data"] = data["data"] | update_data["data"]
        self.data_one_run = data
        return data

    def display_one_run(self, data=None, plotDisp=False, saveFig = True, **kwargs):
        if data is None:
            data = self.data_one_run

        if "cen_num" in kwargs:
            cen_num = kwargs["cen_num"]
        else:
            cen_num = 2

        # Extracting data
        i_0 = data["data"]["i_0"]
        q_0 = data["data"]["q_0"]
        qubit_freq_vec = data["data"]["qubit_freq_vec"]
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
        iq_data = np.stack((i_0[-1, :], q_0[-1, :]), axis=0)
        sse2.plotFitAndData(pdf_0, gaussians_0, x_points_0, y_points_0, centers[-1], iq_data, fig, blob_axs)
        blob_axs.set_aspect('equal')

        # Plot the Rabi Blob Distribution
        subplot_right = []
        for idx_start in range(cen_num):
            subplot_right.append(plt.subplot(gs[idx_start, 1]))
            subplot_right[idx_start].scatter(qubit_freq_vec, pop[idx_start, idx_start, :])
            subplot_right[idx_start].set_xlabel("Qubit Frequency (in MHz)")
            subplot_right[idx_start].set_ylabel("Population")

        data_information = (" Yoko_Volt = " + str(self.cfg["yokoVoltage"]) + "V, relax_delay = " + str(
                    self.cfg["relax_delay"]) + "us." )
        plt.suptitle(self.outerFolder + '\n' + self.path_wDate + '\n' + data_information)
        plt.tight_layout()
        if saveFig:
            plt.savefig(self.path_wDate + "first_run.png" , dpi=400)

        if plotDisp:
            plt.show()
        else:
            plt.close()

    def acquire(self, progress=False, debug=False, plotDisp = True, plotSave = True, figNum = 1):
        expt_cfg = {
            ### define the gainuator parameters
            "trans_gain_start": self.cfg["trans_gain_start"],
            "trans_gain_stop": self.cfg["trans_gain_stop"],
            "trans_gain_num": self.cfg["trans_gain_num"],
            #spec parameters
            "qubit_freq_start": self.cfg["qubit_freq_start"],  # [MHz] actual frequency is this number + "cavity_LO"
            "qubit_freq_stop": self.cfg["qubit_freq_stop"],  # [MHz] actual frequency is this number + "cavity_LO"
            "SpecNumPoints": self.cfg["SpecNumPoints"],
        }

        if self.cfg["units"] == "DAC":
            gainVec = np.linspace(expt_cfg["trans_gain_start"], expt_cfg["trans_gain_stop"], expt_cfg["trans_gain_num"],
                                   dtype=int) ### for current simplicity set it to an int
        else:
            gainVec = np.logspace(np.log10(expt_cfg["trans_gain_start"]), np.log10(expt_cfg["trans_gain_stop"]), num= expt_cfg["trans_gain_num"],
                                   dtype = int)

        ### create the figure and subplots that data will be plotted on
        while plt.fignum_exists(num = figNum):
            figNum += 1
        fig, axs = plt.subplots(2, 1, figsize = (16,10), num = figNum)

        ### create the frequency array
        self.spec_fpts = np.linspace(expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"], expt_cfg["SpecNumPoints"])

        Y = gainVec
        print(f"The experiment will run stark shift for these resonator gain {gainVec} [DAC Units]")
        Y_step = Y[1] - Y[0]

        self.data = {
            'config': self.cfg,
            'data': {'gain_fpts': gainVec}
        }

        X_spec = self.spec_fpts / 1e3
        X_spec_step = X_spec[1] - X_spec[0]

        Z_pop0 = np.full((expt_cfg["trans_gain_num"], expt_cfg["SpecNumPoints"]), np.nan)
        Z_pop1 = np.full((expt_cfg["trans_gain_num"], expt_cfg["SpecNumPoints"]), np.nan)

        #### start a timer for estimating the time for the scan
        startTime = datetime.datetime.now()
        print('') ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        start = time.time()

        # Creating the extents of the plot
        if self.cfg['units'] == 'DAC':
            extents = [X_spec[0] - X_spec_step / 2, X_spec[-1] + X_spec_step / 2, Y[0] - Y_step / 2, Y[-1] + Y_step / 2]
        else:
            print(Y[-1]**2/Y[-2])
            extents = [X_spec[0] - X_spec_step / 2, X_spec[-1] + X_spec_step / 2, 10*np.log10(Y[0]**2/Y[1]), 10*np.log10(Y[-1]**2/Y[-2])]

        # Creating an entry in the dictionary for cavity pulse gain
        self.cfg["pop_gain"] = 0

        # Looping around all the cavity pulse gains
        for i in range(expt_cfg["trans_gain_num"]):
            self.cfg["pop_gain"] = gainVec[i]

            data_one_run = self.acquire_one_run()
            data_one_run = self.process_data_one_run(data = data_one_run)

            if i == 0 :
                self.display_one_run(data = data_one_run, plotDisp=False, saveFig=True)

            self.data['PS_data_'+str(i)] = data_one_run['data']

            Z_pop0[i, :] = data_one_run['data']['pop'][0, 0, :]
            Z_pop1[i, :] = data_one_run['data']['pop'][1, 1, :]

            if i == 0:  #### if first sweep add a colorbar
                ax_plot_1 = axs[0].imshow(
                    Z_pop0,
                    aspect='auto',
                    extent=[np.min(X_spec) - X_spec_step / 2, np.max(X_spec) + X_spec_step / 2, np.min(Y) - Y_step / 2,
                            np.max(Y) + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )
                cbar1 = fig.colorbar(ax_plot_1, ax=axs[0], extend='both')
                cbar1.set_label('a.u.', rotation=90)
            else:
                ax_plot_1.set_data(Z_pop0)
                ax_plot_1.set_clim(vmin=np.nanmin(Z_pop0))
                ax_plot_1.set_clim(vmax=1)
                cbar1.remove()
                cbar1 = fig.colorbar(ax_plot_1, ax=axs[0], extend='both')
                cbar1.set_label('a.u.', rotation=90)

            axs[0].set_ylabel("RO gain (DAC)")
            axs[0].set_xlabel("Spec Frequency (GHz)")
            axs[0].set_title(f"Qubit in state A at {self.data['PS_data_0']['centers'][0][0]}")

            if i == 0:  #### if first sweep add a colorbar
                ax_plot_2 = axs[1].imshow(
                    Z_pop1,
                    aspect='auto',
                    extent=[np.min(X_spec) - X_spec_step / 2, np.max(X_spec) + X_spec_step / 2, np.min(Y) - Y_step / 2,
                            np.max(Y) + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )
                cbar2 = fig.colorbar(ax_plot_2, ax=axs[1], extend='both')
                cbar2.set_label('Phase', rotation=90)
            else:
                ax_plot_2.set_data(Z_pop1)
                ax_plot_2.set_clim(vmin=np.nanmin(Z_pop1))
                ax_plot_2.set_clim(vmax=1)
                cbar2.remove()
                cbar2 = fig.colorbar(ax_plot_2, ax=axs[1], extend='both')
                cbar2.set_label('Phase', rotation=90)

            axs[1].set_ylabel("RO gain (DAC)")
            axs[1].set_xlabel("Spec Frequency (GHz)")
            axs[1].set_title(f"Qubit in State B at {self.data['PS_data_0']['centers'][0][1]}")

            plt.suptitle(self.iname)

            plt.tight_layout()

            if plotDisp and i == 0:
                plt.show(block=False)
                # Parth's fix
                plt.pause(5)
            elif plotDisp:
                plt.draw()
                plt.pause(5)

            if i == 0:  ### during the first run create a time estimate for the data aqcuisition
                t_delta = time.time() - start  ### time for single full row in seconds
                timeEst = t_delta * expt_cfg["trans_gain_num"]  ### estimate for full scan
                StopTime = startTime + datetime.timedelta(seconds=timeEst)
                print('Time for 1 sweep: ' + str(round(t_delta / 60, 2)) + ' min')
                print('estimated total time: ' + str(round(timeEst / 60, 2)) + ' min')
                print('estimated end: ' + StopTime.strftime("%Y/%m/%d %H:%M:%S"))

        print('actual end: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

        if plotSave:
            plt.savefig(self.iname)  #### save the figure

        if plotDisp == False:
            fig.clf(True)
            plt.close(fig)

        return self.data


    def save_data(self, data=None):
        ##### save the data to a .h5 file
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])




