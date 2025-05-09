from qick import *
import time
import datetime
import numpy as np
import matplotlib.pyplot as plt
from qick.helpers import gauss
from tqdm.notebook import tqdm
from Pyro4 import Proxy
from qick import QickConfig

from MasterProject.Client_modules.Quarky_GUI.CoreLib.ExperimentPlus import ExperimentClassPlus
from MasterProject.Client_modules.Quarky_GUI.CoreLib.VoltageInterface import VoltageInterface

import WorkingProjects.Inductive_Coupler.Client_modules.Helpers.FF_utils as FF

class CavitySpecFFProg(AveragerProgram):
    def initialize(self):
        cfg = self.cfg
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["pulse_freqs"],
                         mux_gains= cfg["pulse_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", mask=cfg["ro_chs"], #gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"], gen_ch = self.cfg["res_ch"]))

        FF.FFDefinitions(self)
        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        cfg = self.cfg
        self.sync_all(gen_t0=self.gen_t0)
        self.FFPulses(self.FFReadouts, self.cfg["length"])
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"], pins=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))
        self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
        self.sync_all(self.us2cycles(self.cfg["cav_relax_delay"]), gen_t0=self.gen_t0)

    def FFPulses(self, list_of_gains, length_us, t_start='auto'):
        FF.FFPulses(self, list_of_gains, length_us, t_start)
# ====================================================== #

class QubitSpecSliceFFProg(RAveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["pulse_freqs"],
                         mux_gains= cfg["pulse_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", mask=cfg["ro_chs"], #gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_freq = self.sreg(cfg["qubit_ch"], "freq")  # get frequency register for qubit_ch

        ### Start fast flux
        FF.FFDefinitions(self)
        # f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=0)  # conver f_res to dac register value

        self.f_start = self.freq2reg(cfg["start"], gen_ch=cfg["qubit_ch"])  # get start/step frequencies
        self.f_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])


        # add qubit and readout pulses to respective channels
        if cfg['Gauss']:
            self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch = self.cfg["qubit_ch"])
            self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch = self.cfg["qubit_ch"])
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma= self.pulse_sigma, length= self.pulse_qubit_lenth)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=self.f_start,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit")
            self.qubit_length_us = cfg["sigma"] * 4
        else:
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_start, phase=0, gain=cfg["qubit_gain"],
                                     length=self.us2cycles(cfg["qubit_length"], gen_ch=self.cfg["qubit_ch"]))
            self.qubit_length_us = cfg["qubit_length"]

    def body(self):
        self.sync_all(gen_t0=self.gen_t0)
        self.FFPulses(self.FFPulse, self.qubit_length_us + 1)
        self.pulse(ch=self.cfg["qubit_ch"], t = self.us2cycles(1))  # play probe pulse
        # trigger measurement, play measurement pulse, wait for qubit to relax
        self.sync_all(gen_t0=self.gen_t0)
        self.FFPulses(self.FFReadouts, self.cfg["length"])
        # self.FFPulses(self.FFPulse, self.cfg["length"])
        # self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"], pins=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))
        self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
        self.FFPulses(-1 * self.FFPulse, self.qubit_length_us + 1)
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]), gen_t0=self.gen_t0)

    def FFPulses(self, list_of_gains, length_us, t_start='auto'):
        FF.FFPulses(self, list_of_gains, length_us, t_start)

    def update(self):
        self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.f_step)  # update frequency list index


# ====================================================== #


class SpecVsVoltage(ExperimentClassPlus):
    """
    Spec experiment that finds the qubit spectrum as a function of flux
    Notes;
        - this is set up such that it plots out the rows of data as it sweeps through voltage
        - because the cavity frequency changes as a function of flux, it both finds the cavity peak then uses
            the cavity peak to perform the spec drive
    """

    ### define the template config
    config_template = {'res_ch': 6, 'qubit_ch': 4, 'mixer_freq': 500, 'ro_chs': [0], 'reps': 20, 'nqz': 1, 'qubit_nqz': 2,
         'relax_delay': 200, 'res_phase': 0, 'pulse_style': 'const', 'length': 20, 'pulse_gain': 5500,
         'adc_trig_offset': 0.5, 'cavity_LO': 6800000000.0, 'cavity_winding_freq': 1.0903695,
         'cavity_winding_offset': -15.77597, 'Additional_Delays': {'1': {'channel': 4, 'delay_time': 0}},
         'has_mixer': True, 'readout_length': 3, 'pulse_freq': -9.75, 'pulse_gains': [0.171875], 'pulse_freqs': [-9.75],
         'TransSpan': 1.5, 'TransNumPoints': 61, 'cav_relax_delay': 30, 'qubit_pulse_style': 'const',
         'qubit_gain': 1500, 'qubit_freq': 4608, 'qubit_length': 100, 'SpecSpan': 200, 'SpecNumPoints': 101,
         'step': 5.714285714285714, 'start': 4408, 'expts': 71,
         'FF_Qubits': {'1': {'channel': 2, 'delay_time': 0.005, 'Gain_Readout': 10000, 'Gain_Expt': 0, 'Gain_Pulse': 0},
                       '2': {'channel': 3, 'delay_time': 0.0, 'Gain_Readout': 0, 'Gain_Expt': 0, 'Gain_Pulse': 0},
                       '3': {'channel': 0, 'delay_time': 0.002, 'Gain_Readout': 10000, 'Gain_Expt': 0,
                             'Gain_Pulse': 10000},
                       '4': {'channel': 1, 'delay_time': 0.0, 'Gain_Readout': 10000, 'Gain_Expt': 0, 'Gain_Pulse': 0}},
         'Read_Indeces': [2], 'cavity_min': True, 'rounds': 20, 'VoltageNumPoints': 2, 'sleep_time': 0, 'DACs': [5],
         'VoltageStart': [-0.5], 'VoltageStop': [0], 'Gauss': False
    }

    ### Hardware Requirement
    hardware_requirement = [Proxy, QickConfig, VoltageInterface]

    def __init__(self, path='', outerFolder='', prefix='data', hardware=None,
                 cfg=None, config_file=None, progress=None):

        super().__init__(path=path, outerFolder=outerFolder, prefix=prefix, hardware=hardware,
                         hardware_requirement=self.hardware_requirement, cfg=cfg,
                         config_file=config_file, progress=progress)

        # retrieve the hardware that corresponds to what was required
        self.soc, self.soccfg, self.voltage_interface = hardware

    #### during the aquire function here the data is plotted while it comes in if plotDisp is true
    def acquire(self, progress=False, plotDisp = True, plotSave = True, figNum = 1,
                smart_normalize = True):

        expt_cfg = {
            ### define the voltage parameters
            "VoltageStart": self.cfg["VoltageStart"],
            "VoltageStop": self.cfg["VoltageStop"],
            "VoltageNumPoints": self.cfg["VoltageNumPoints"],
            ### transmission parameters
            # "trans_freq_start": self.cfg["trans_freq_start"],  # [MHz] actual frequency is this number + "cavity_LO"
            # "trans_freq_stop": self.cfg["trans_freq_stop"],  # [MHz] actual frequency is this number + "cavity_LO"
            # "TransNumPoints": self.cfg["TransNumPoints"],  ### number of points in the transmission frequency
            ### spec parameters
            "step": self.cfg["step"],
            "start": self.cfg["start"],
            "expts": self.cfg["expts"],
        }
        print(self.cfg["step"], self.cfg["start"], self.cfg["expts"])

        voltage_matrix = []
        # creates an n x VoltageNumPoints matrix where n should be the length of DACs
        # ie, voltageStart and VoltageStop should be n length arrays
        for n in range(len(expt_cfg["VoltageStart"])):
            voltage_matrix.append(np.linspace(expt_cfg["VoltageStart"][n],expt_cfg["VoltageStop"][n], expt_cfg["VoltageNumPoints"]))

        # create the figure and subplots that data will be plotted on
        while plt.fignum_exists(num = figNum):
            figNum += 1
        fig, axs = plt.subplots(1,1, figsize = (8,6), num = figNum)

        # create the frequency arrays for both transmission and spec
        # also create empty array to fill with transmission and spec data
        # self.trans_fpts = np.linspace(expt_cfg["trans_freq_start"], expt_cfg["trans_freq_stop"], expt_cfg["TransNumPoints"])
        # self.spec_fpts = np.linspace(expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"], expt_cfg["SpecNumPoints"])
        self.spec_fpts = expt_cfg["start"] + np.arange(expt_cfg["expts"]) * expt_cfg["step"]
        print(self.spec_fpts)

        # X_trans = (self.trans_fpts + self.cfg["cavity_LO"]/1e6) /1e3
        # X_trans_step = X_trans[1] - X_trans[0]
        X_spec = self.spec_fpts/1e3
        X_spec_step = X_spec[1] - X_spec[0]
        Y = voltage_matrix[0]
        Y_step = Y[1] - Y[0]
        # Z_trans = np.full((expt_cfg["VoltageNumPoints"], expt_cfg["TransNumPoints"]), np.nan)
        Z_spec = np.full((expt_cfg["VoltageNumPoints"], expt_cfg["expts"]), np.nan)

        ### create an initial data dictionary that will be filled with data as it is taken during sweeps
        # self.trans_Imat = np.zeros((expt_cfg["VoltageNumPoints"], expt_cfg["TransNumPoints"]))
        # self.trans_Qmat = np.zeros((expt_cfg["VoltageNumPoints"], expt_cfg["TransNumPoints"]))
        self.spec_Imat = np.zeros((expt_cfg["VoltageNumPoints"], expt_cfg["expts"]))
        self.spec_Qmat = np.zeros((expt_cfg["VoltageNumPoints"], expt_cfg["expts"]))
        self.data= {
            'config': self.cfg,
            'data': {#'trans_Imat': self.trans_Imat, 'trans_Qmat': self.trans_Qmat, 'trans_fpts':self.trans_fpts,
                        'spec_Imat': self.spec_Imat, 'spec_Qmat': self.spec_Qmat, 'spec_fpts': self.spec_fpts,
                        'voltage_matrix': voltage_matrix
                     }
        }

        print(voltage_matrix)

        # loop over the voltageVec
        for i in range(expt_cfg["VoltageNumPoints"]):
            if i != 0:
                time.sleep(self.cfg['sleep_time'])

            # Setting voltages
            if 'DACs' in self.cfg:
                for m in range(len(self.cfg['DACs'])):
                    self.voltage_interface.set_voltage(voltage_matrix[m][i], self.cfg['DACs'][m])
            else:
                self.voltage_interface.set_voltage(voltage_matrix[0][i])
                self.cfg['DACs'] = [1]
            time.sleep(1)

            ### take the transmission data
            # data_I, data_Q = self._aquireTransData()
            # self.data['data']['trans_Imat'][i,:] = data_I
            # self.data['data']['trans_Qmat'][i,:] = data_Q

            # #### plot out the transmission data
            # sig = data_I + 1j * data_Q
            # avgamp0 = np.abs(sig)
            # Z_trans[i, :] = avgamp0
            # # axs[0].plot(x_pts, avgamp0, label="Amplitude; ADC 0")
            # if i == 1:
            #     ax_plot_0 = axs[0].imshow(
            #         Z_trans,
            #         aspect='auto',
            #         extent=[np.min(X_trans)-X_trans_step/2,np.max(X_trans)+X_trans_step/2,np.min(Y)-Y_step/2,np.max(Y)+Y_step/2],
            #         origin= 'lower',
            #         interpolation= 'none',
            #     )
            #     cbar0 = fig.colorbar(ax_plot_0, ax=axs[0], extend='both')
            #     cbar0.set_label('a.u.', rotation=90)
            # else:
            #     ax_plot_0.set_data(Z_trans)
            #     ax_plot_0.autoscale()
            #     cbar0.remove()
            #     cbar0 = fig.colorbar(ax_plot_0, ax=axs[0], extend='both')
            #     cbar0.set_label('a.u.', rotation=90)
            #
            # axs[0].set_ylabel("Yoko Voltage (V)")
            # axs[0].set_xlabel("Cavity Frequency (GHz)")
            # axs[0].set_title("Cavity Transmission")
            #
            # if plotDisp:
            #     plt.show(block=False)
            #     plt.pause(0.1)

            if i != expt_cfg["VoltageNumPoints"]:
                time.sleep(self.cfg['sleep_time'])

            ### take the spec data
            data_I, data_Q = self._aquireSpecData()
            data_I = data_I[0]
            data_Q = data_Q[0]

            self.data['data']['spec_Imat'][i,:] = data_I
            self.data['data']['spec_Qmat'][i,:] = data_Q

            #### plot out the spec data
            sig = data_I + 1j * data_Q

            avgamp0 = np.abs(sig)
            if smart_normalize:
                avgamp0 = Normalize_Qubit_Data(data_I[0], data_Q[0])
            Z_spec[i, :] = avgamp0  #- self.cfg["minADC"]
            if i == 0:

                ax_plot_1 = axs.imshow(
                    Z_spec,
                    aspect='auto',
                    extent=[X_spec[0]-X_spec_step/2,X_spec[-1]+X_spec_step/2,Y[0]-Y_step/2,Y[-1]+Y_step/2],
                    origin='lower',
                    interpolation = 'none',
                )
                cbar1 = fig.colorbar(ax_plot_1, ax=axs, extend='both')
                cbar1.set_label('a.u.', rotation=90)
            else:
                ax_plot_1.set_data(Z_spec)
                ax_plot_1.autoscale()
                cbar1.remove()
                cbar1 = fig.colorbar(ax_plot_1, ax=axs, extend='both')
                cbar1.set_label('a.u.', rotation=90)
            # if i ==0: #### if first sweep add a colorbar
            #     cbar1 = fig.colorbar(ax_plot_1, ax=axs[1], extend='both')
            #     cbar1.set_label('a.u.', rotation=90)
            # else:
            #     cbar1.remove()
            #     cbar1 = fig.colorbar(ax_plot_1, ax=axs[1], extend='both')
            #     cbar1.set_label('a.u.', rotation=90)

            axs.set_ylabel("Voltage (V)")
            axs.set_xlabel("Spec Frequency (GHz)")
            axs.set_title(f"{self.titlename}, DACs: {self.cfg['DACs']}, "
                             f"Cav Freq: {np.round(self.cfg['pulse_freqs'][0] + self.cfg['mixer_freq'] + self.cfg['cavity_LO'] / 1e6, 3)}")

            if plotDisp:
                plt.show(block=False)
                plt.pause(0.1)

        if plotDisp == False:
            fig.clf(True)
            plt.close(fig)
        else:
            plt.show(block=True)

        return self.data

    # @classmethod
    # def plotter(cls, plot_widget, plots, data):
    #     # print(data)
    #     if 'data' in data:
    #         data = data['data']
    #
    #     return

    @classmethod
    def export_data(cls, data_file, data, config):
        super().export_data(data_file, data, config)
        pass

    def _aquireTransData(self, progress=False):
        fpts = np.linspace(self.cfg["mixer_freq"] - self.cfg["TransSpan"],
                           self.cfg["mixer_freq"] + self.cfg["TransSpan"],
                           self.cfg["TransNumPoints"])
        results = []
        start = time.time()
        for f in tqdm(fpts, position=0, disable=True):
            self.cfg["mixer_freq"] = f
            prog = CavitySpecFFProg(self.soccfg, self.cfg)
            results.append(prog.acquire(self.soc, load_pulses=True))
        print(f'Time: {time.time() - start}')
        results = np.transpose(results)
        print(results)
        # data={'config': self.cfg, 'data': {'results': results, 'fpts':fpts}}
        # self.data=data
        #
        # #### find the frequency corresponding to the peak
        # sig = data['data']['results'][0][0][0] + 1j * data['data']['results'][0][0][1]
        # avgamp0 = np.abs(sig)
        # peak_loc = np.argmin(avgamp0)
        # self.peakFreq_min = data['data']['fpts'][peak_loc]
        # peak_loc = np.argmax(avgamp0)
        # self.peakFreq_max = data['data']['fpts'][peak_loc]

        # return data
        return results[0][0][0], results['results'][0][0][1]

    # def _aquireTransData(self):
    #     ##### code to aquire just the cavity transmission data
    #     expt_cfg = {
    #         ### transmission parameters
    #         "trans_freq_start": self.cfg["trans_freq_start"],  # [MHz] actual frequency is this number + "cavity_LO"
    #         "trans_freq_stop": self.cfg["trans_freq_stop"],  # [MHz] actual frequency is this number + "cavity_LO"
    #         "TransNumPoints": self.cfg["TransNumPoints"],  ### number of points in the transmission frequecny
    #     }
    #     ### take the transmission data
    #     self.cfg["reps"] = self.cfg["trans_reps"]
    #     fpts = np.linspace(expt_cfg["trans_freq_start"], expt_cfg["trans_freq_stop"], expt_cfg["TransNumPoints"])
    #     results = []
    #     start = time.time()
    #     for f in tqdm(fpts, position=0, disable=True):
    #         self.cfg["pulse_freq"] = f
    #         prog = LoopbackProgramTrans(self.soccfg, self.cfg)
    #         results.append(prog.acquire(self.soc, load_pulses=True))
    #     results = np.transpose(results)
    #     #### pull out I and Q data
    #     data_I = results[0][0][0]
    #     data_Q = results[0][0][1]
    #
    #     #### find the frequency corresponding to the cavity peak and set as cavity transmission number
    #     sig = data_I + 1j * data_Q
    #     avgamp0 = np.abs(sig)
    #     filtered_amp = savgol_filter(avgamp0, 5, 2)
    #     peak_loc = np.argmin(filtered_amp)
    #     self.cfg["pulse_freq"] = self.trans_fpts[peak_loc]
    #     self.cfg['minADC'] = avgamp0[peak_loc]
    #
    #     return data_I, data_Q

    def _aquireSpecData(self, progress=False):

        prog = QubitSpecSliceFFProg(self.soccfg, self.cfg)
        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False)

        # data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        # self.data = data
        #
        # x_pts = data['data']['x_pts']
        # avgi = data['data']['avgi']
        # avgq = data['data']['avgq']
        #
        # #### find the frequency corresponding to the qubit dip
        # sig = avgi + 1j * avgq
        # avgamp0 = np.abs(sig)
        # peak_loc = np.argmax(avgamp0)
        # self.qubitFreq = x_pts[peak_loc]

        return avgi, avgq

    # def _aquireSpecData(self):
    #     ##### code to aquire just the cavity transmission data
    #     expt_cfg = {
    #         ### spec parameters
    #         "qubit_freq_start": self.cfg["qubit_freq_start"],
    #         "qubit_freq_stop": self.cfg["qubit_freq_stop"],
    #         "SpecNumPoints": self.cfg["SpecNumPoints"],  ### number of points
    #     }
    #     ### take the transmission data
    #     self.cfg["reps"] = self.cfg["spec_reps"]
    #     fpts = np.linspace(expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"], expt_cfg["SpecNumPoints"])
    #     results = []
    #     start = time.time()
    #     for f in tqdm(fpts, position=0, disable=True):
    #         self.cfg["qubit_freq"] = f
    #         prog = LoopbackProgramSpecSlice(self.soccfg, self.cfg)
    #         results.append(prog.acquire(self.soc, load_pulses=True))
    #     results = np.transpose(results)
    #     #### pull out I and Q data
    #     data_I = results[0][0][0]
    #     data_Q = results[0][0][1]
    #
    #     return data_I, data_Q


    def save_data(self, data=None):
        ##### save the data to a .h5 file
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


# def Normalize_Qubit_Data(idata, qdata):
#     idata_rotated = Amplitude_IQ_angle(idata, qdata)
#     idata_rotated -= np.median(idata_rotated) #subtract the offset
#     range_ = max(idata_rotated) - min(idata_rotated)
#     idata_rotated *= 1 / range_   #normalize data to have amplitude of 1
#     if np.abs(max(idata_rotated)) < np.abs(min(idata_rotated)):
#         idata_rotated *= -1 #ensures that the spec has a peak rather than a dip
#     return(idata_rotated)

def Normalize_Qubit_Data(idata, qdata):
    idata_rotated = Amplitude_IQ_angle(idata, qdata)
    idata_rotated -= np.median(idata_rotated) #subtract the offset
    range_ = max(idata_rotated) - min(idata_rotated)
    if np.abs(max(idata_rotated)) < np.abs(min(idata_rotated)):
        idata_rotated *= -1 #ensures that the spec has a peak rather than a dip
    idata_rotated -= min(idata_rotated)
    idata_rotated *= 1 / range_   #normalize data to have amplitude of 1

    return(idata_rotated)

def Amplitude_IQ_angle(I, Q, phase_num_points = 50):
    '''
    IQ data is inputted and it will multiply by a phase such that all of the
    information is in I
    :param I:
    :param Q:
    :param phase_num_points:
    :return: Array of data all in I quadrature
    '''
    complexarg = I + 1j * Q
    phase_values = np.linspace(0, np.pi, phase_num_points)
    multiplied_phase = [complexarg * np.exp(1j * phase) for phase in phase_values]
    I_range = np.array([np.max(IQPhase.real) - np.min(IQPhase.real) for IQPhase in multiplied_phase])
    phase_index = np.argmax(I_range)
    angle = phase_values[phase_index]
    complexarg *= np.exp(1j * angle)
    return(complexarg.real)

