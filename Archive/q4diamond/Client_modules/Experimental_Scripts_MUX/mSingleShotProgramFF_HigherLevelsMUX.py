from qick import *
from qick import helpers
import matplotlib.pyplot as plt
import numpy as np
from q4diamond.Client_modules.Experiment import ExperimentClass
from q4diamond.Client_modules.Helpers.hist_analysis import *
from tqdm.notebook import tqdm
import time
import q4diamond.Client_modules.Helpers.FF_utils as FF

# class SingleShotProgramOldFF(AveragerProgram):
#     def __init__(self, soccfg, cfg):
#         super().__init__(soccfg, cfg)
#
#     def initialize(self):
#         cfg = self.cfg
#         cfg["reps"]=cfg["shots"]
#         self.cfg["rounds"] = 1
#
#         res_ch = cfg["res_ch"]
#         self.declare_gen(ch=res_ch, nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])
#
#         # Qubit configuration
#         qubit_ch = cfg["qubit_ch"]
#         self.declare_gen(ch=qubit_ch, nqz=cfg["qubit_nqz"])
#
#         for ro_ch in cfg["ro_chs"]:
#             self.declare_readout(ch=ro_ch, freq=cfg["pulse_freq"],
#                                  length=self.us2cycles(self.cfg["readout_length"]), gen_ch=cfg["res_ch"])
#
#         read_freq = self.freq2reg(cfg["pulse_freq"], gen_ch=res_ch, ro_ch=cfg["ro_chs"][0])
#         # convert frequency to dac frequency (ensuring it is an available adc frequency)
#         qubit_freq = self.freq2reg(cfg["qubit_freq"],
#                                    gen_ch=qubit_ch)  # convert frequency to dac frequency (ensuring it is an available adc frequency)
#         self.freq_01 = self.freq2reg(cfg["qubit_freq01"], gen_ch=qubit_ch)
#         self.freq_12 = self.freq2reg(cfg["qubit_freq12"], gen_ch=qubit_ch)
#
#         self.FFDefinitions()
#         #FF End
#
#         if cfg["qubit_pulse_style"] == "arb":
#             self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
#                            sigma=self.us2cycles(self.cfg["sigma"]),
#                            length=self.us2cycles(self.cfg["sigma"]) * 4)
#             self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
#                                      phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["start"],
#                                      waveform="qubit")
#             self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4
#
#         else:
#             print("define pi or flat top pulse")
#
#         self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=read_freq, phase=cfg["res_phase"],
#                                  gain=cfg["pulse_gain"],
#                                  length=self.us2cycles(cfg["length"]))
#         self.sync_all(200)  # give processor some time to configure pulses
#
#     def body(self):
#         print(self.cfg['pulse_expt'])
#         self.FFPulses(self.FFExpts, self.qubit_pulseLength + self.us2cycles(2))
#         if self.cfg['pulse_expt']['pulse_01'] or self.cfg['pulse_expt']['pulse_12']:
#             self.setup_and_pulse(ch=self.cfg["qubit_ch"], style="arb", freq=self.freq_01, phase=0, gain=self.cfg["qubit_gain01"],
#                                  waveform="qubit", t = self.us2cycles(2))
#
#         if self.cfg['pulse_expt']['pulse_12']:
#             print('1 to 2 transition')
#             self.setup_and_pulse(ch=self.cfg["qubit_ch"], style="arb", freq=self.freq_12, phase=0, gain=self.cfg["qubit_gain12"],
#                                  waveform="qubit")
#
#         self.sync_all()
#
#         self.FFPulses(self.FFReadouts, self.us2cycles(self.cfg["length"]))
#
#         self.measure(pulse_ch=self.cfg["res_ch"],
#                      adcs=[0],
#                      adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
#                      wait=True,
#                      syncdelay=self.us2cycles(20))
#
#         self.FFPulses(-1 * self.FFExpts, self.qubit_pulseLength + self.us2cycles(2))
#         self.FFPulses(-1 * self.FFReadouts, self.us2cycles(self.cfg["length"]))
#         self.sync_all(self.us2cycles(self.cfg["relax_delay"]))
#
#     def FFPulses(self, list_of_gains, length):
#         for i, gain in enumerate(list_of_gains):
#             self.set_pulse_registers(ch=self.FFChannels[i], style=self.ff_style, freq=self.ff_freq, phase=0,
#                                      gain=gain,
#                                      length=length)
#         self.pulse(ch=self.FF_Channel1)
#         self.pulse(ch=self.FF_Channel2)
#         self.pulse(ch=self.FF_Channel3)
#
#     def FFDefinitions(self):
#         ### Start fast flux
#         for FF_info in self.cfg["FF_list_readout"]:
#             self.declare_gen(ch=FF_info[0], nqz=self.cfg["ff_nqz"])
#
#         self.ff_freq = self.freq2reg(self.cfg["ff_freq"], gen_ch=self.cfg["ff_ch"])
#         self.ff_style = self.cfg["ff_pulse_style"]
#
#         ### Finish FF
#         self.FF_Channel1, self.FF_Gain1_readout = self.cfg["FF_list_readout"][0]
#         self.FF_Channel2, self.FF_Gain2_readout = self.cfg["FF_list_readout"][1]
#         self.FF_Channel3, self.FF_Gain3_readout = self.cfg["FF_list_readout"][2]
#
#         self.FF_Gain1_exp = self.cfg["FF_list_exp"][0][1]
#         self.FF_Gain2_exp = self.cfg["FF_list_exp"][1][1]
#         self.FF_Gain3_exp = self.cfg["FF_list_exp"][2][1]
#
#         self.FFChannels = np.array([self.FF_Channel1, self.FF_Channel2, self.FF_Channel3])
#         self.FFReadouts = np.array([self.FF_Gain1_readout, self.FF_Gain2_readout, self.FF_Gain3_readout])
#         self.FFExpts = np.array([self.FF_Gain1_exp, self.FF_Gain2_exp, self.FF_Gain3_exp])
#
#     def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=1, save_experiments=None,
#                 start_src="internal", progress=False, debug=False):
#         super().acquire(soc, load_pulses=load_pulses, progress=progress, debug=debug)
#
#         return self.collect_shots()
#
#     def collect_shots(self):
#         shots_i0 = self.di_buf[0] / self.us2cycles(self.cfg['readout_length'], ro_ch = self.cfg["ro_chs"][0])
#         shots_q0 = self.dq_buf[0] / self.us2cycles(self.cfg['readout_length'], ro_ch = self.cfg["ro_chs"][0])
#         return shots_i0,shots_q0
class SingleShotProgram_Higher(AveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg
        cfg["reps"]=cfg["shots"]
        self.cfg["rounds"] = 1

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["pulse_freqs"],
                         mux_gains=cfg["pulse_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", mask=cfg["ro_chs"],  # gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"], gen_ch=self.cfg["res_ch"]))

        # Qubit configuration
        qubit_ch = cfg["qubit_ch"]
        self.declare_gen(ch=qubit_ch, nqz=cfg["qubit_nqz"])

        self.freq_01 = self.freq2reg(cfg["qubit_freq01"], gen_ch=qubit_ch)
        self.freq_12 = self.freq2reg(cfg["qubit_freq12"], gen_ch=qubit_ch)

        FF.FFDefinitions(self)

        self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                       sigma=self.us2cycles(self.cfg["sigma"]),
                       length=self.us2cycles(self.cfg["sigma"]) * 4)

        self.sync_all(200)  # give processor some time to configure pulses
        print(self.cfg["sigma"],self.cfg["qubit_gain01"], self.cfg["qubit_gain12"], self.freq_01, self.freq_12,
              self.cfg["pulse_freqs"], self.cfg["pulse_gains"] )

    def body(self):
        print(self.cfg['pulse_expt'], self.cfg["qubit_gain01"], self.cfg["qubit_gain12"], self.cfg["qubit_freq01"], self.cfg["qubit_freq12"])
        self.sync_all(dac_t0=self.dac_t0)
        self.FFPulses(self.FFPulse, 2 * self.cfg["sigma"] * 4 + 1.01)
        # self.FFPulses_direct(self.FFPulse, (self.us2cycles(1 + 2 * self.cfg["sigma"] * 4) + 4) * 16,
        #                      np.array([0, 0, 0, 0]), IQPulseArray= self.cfg["IDataArray"])
        if self.cfg['pulse_expt']['pulse_01'] or self.cfg['pulse_expt']['pulse_12']:
            self.setup_and_pulse(ch=self.cfg["qubit_ch"], style="arb", freq=self.freq_01, phase=0, gain=self.cfg["qubit_gain01"],
                                 waveform="qubit", t = self.us2cycles(1))

        if self.cfg['pulse_expt']['pulse_12']:
            print('1 to 2 transition')
            self.setup_and_pulse(ch=self.cfg["qubit_ch"], style="arb", freq=self.freq_12, phase=0, gain=self.cfg["qubit_gain12"],
                                 waveform="qubit")

        self.sync_all(dac_t0=self.dac_t0)

        self.FFPulses(self.FFReadouts, self.cfg["length"])

        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"], pins=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=False,
                     syncdelay=self.us2cycles(10))

        # self.FFPulses(-1 * self.FFPulse, 2 * self.cfg["sigma"] * 4 + 1.01)
        self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
        # IQ_Array_Negative = np.array([-1 * array if type(array) != type(None) else None for array in self.cfg["IDataArray"]], dtype = object)
        # self.FFPulses_direct(-1 * self.FFPulse, (self.us2cycles(1 + 2 * self.cfg["sigma"] * 4) + 4) * 16,
        #                      np.array([0, 0, 0, 0]), IQPulseArray = IQ_Array_Negative, waveform_label='FF2')
        self.FFPulses(-1 * self.FFPulse, 2 * self.cfg["sigma"] * 4 + 1.01)

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))

    def FFPulses(self, list_of_gains, length_us, t_start='auto'):
        FF.FFPulses(self, list_of_gains, length_us, t_start)

    def FFPulses_direct(self, list_of_gains, length_dt, previous_gains, t_start='auto', IQPulseArray=None,
                        waveform_label = "FF"):
        FF.FFPulses_direct(self, list_of_gains, length_dt, previous_gains= previous_gains, t_start = t_start,
                           IQPulseArray=IQPulseArray, waveform_label = waveform_label)

    def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=1, save_experiments=None,
                start_src="internal", progress=False, debug=False):
        super().acquire(soc, load_pulses=load_pulses, progress=progress, debug=debug)

        return self.collect_shots()

    def collect_shots(self):
        shots_i0 = self.di_buf[0] / self.us2cycles(self.cfg['readout_length'], ro_ch = self.cfg["ro_chs"][0])
        shots_q0 = self.dq_buf[0] / self.us2cycles(self.cfg['readout_length'], ro_ch = self.cfg["ro_chs"][0])
        return shots_i0,shots_q0


# ====================================================== #
class SingleShotProgramFF_2StatesMUX(ExperimentClass):
    """
    Basic SingleShot experiement that takes a single piece of data
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg,
                         config_file=config_file, progress=progress)

    def acquire(self, ground_pulse = 0, excited_pulse = 1, progress=False, debug=False, ):
        self.cfg["length"] = self.cfg['readout_length'] + self.cfg["adc_trig_offset"] + 0.5
        self.cfg["IDataArray"] = [None, None, None, None]
        self.cfg["IDataArray"][0] = Compensated_Pulse(self.cfg['FF_Qubits']['1']['Gain_Pulse'], 0, 1)
        self.cfg["IDataArray"][1] = Compensated_Pulse(self.cfg['FF_Qubits']['2']['Gain_Pulse'], 0, 2)
        self.cfg["IDataArray"][2] = Compensated_Pulse(self.cfg['FF_Qubits']['3']['Gain_Pulse'], 0, 3)
        self.cfg["IDataArray"][3] = Compensated_Pulse(self.cfg['FF_Qubits']['4']['Gain_Pulse'], 0, 4)
        data= {}
        if ground_pulse == 0:
            self.cfg["pulse_expt"]["pulse_01"] = False
            self.cfg["pulse_expt"]["pulse_12"] = False
        elif ground_pulse == 1:
            self.cfg["pulse_expt"]["pulse_01"] = True
            self.cfg["pulse_expt"]["pulse_12"] = False
        histpro = SingleShotProgram_Higher(soccfg=self.soccfg, cfg=self.cfg)
        avgi, avgq = histpro.acquire(self.soc, threshold=None, load_pulses=True)
        data['I0'], data['Q0'] = histpro.collect_shots()

        if excited_pulse == 1:
            self.cfg["pulse_expt"]["pulse_01"] = True
            self.cfg["pulse_expt"]["pulse_12"] = False
        elif excited_pulse == 2:
            self.cfg["pulse_expt"]["pulse_01"] = True
            self.cfg["pulse_expt"]["pulse_12"] = True
        histpro = SingleShotProgram_Higher(soccfg=self.soccfg, cfg=self.cfg)
        avgi, avgq = histpro.acquire(self.soc, threshold=None, load_pulses=True)
        data['I1'], data['Q1'] = histpro.collect_shots()

        self.data = data
        return data

    def analyze(self, data=None, span=None, verbose=True, **kwargs):
        if data is None:
            data = self.data

        fid, threshold, angle = hist(data=data, plot=False, span=span, verbose=verbose)
        data['fid'] = fid
        data['angle'] = angle
        data['threshold'] = threshold

        return data

    def display(self, data=None, span=None, verbose=True, **kwargs):
        if data is None:
            data = self.data

        fid, threshold, angle = hist(data=data, plot=True, verbose=verbose, span=span, save_title=self.iname,
                                     display_title=self.titlename)

        print(f'fidelity: {fid}')
        print(f'rotation angle (deg): {angle}')
        # print(f'set angle to (deg): {self.cfg.device.readout.phase - angle}')
        print(f'threshold: {threshold}')

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data)


class SingleShotProgramFF_HigherLevelsMUX(ExperimentClass):
    """
    Basic SingleShot experiement that takes a single piece of data
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg,
                         config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
        data= {}

        # Ground state shots
        self.cfg["pulse_expt"]["pulse_01"] = False
        self.cfg["pulse_expt"]["pulse_12"] = False
        histpro = SingleShotProgram_Higher(soccfg=self.soccfg, cfg=self.cfg)
        avgi, avgq = histpro.acquire(self.soc, threshold=None, load_pulses=True)
        data['I0'], data['Q0'] = histpro.collect_shots()

        # Excited state shots
        self.cfg["pulse_expt"]["pulse_01"] = True
        self.cfg["pulse_expt"]["pulse_12"] = False
        histpro = SingleShotProgram_Higher(soccfg=self.soccfg, cfg=self.cfg)
        avgi, avgq = histpro.acquire(self.soc, threshold=None, load_pulses=True)
        data['I1'], data['Q1'] = histpro.collect_shots()

        # Excited state shots
        self.check_f = self.cfg["pulse_expt"]["check_12"]
        if self.check_f:
            self.cfg["pulse_expt"]["pulse_01"] = True
            self.cfg["pulse_expt"]["pulse_12"] = True
            histpro = SingleShotProgram_Higher(soccfg=self.soccfg, cfg=self.cfg)
            avgi, avgq = histpro.acquire(self.soc, threshold=None, load_pulses=True)
            data['I2'], data['Q2'] = histpro.collect_shots()

        self.data = data
        return data


        # #### pull the data from the single hots
        # prog = LoopbackProgramSingleShot(self.soccfg, self.cfg)
        # shots_i0,shots_q0 = prog.acquire(self.soc, load_pulses=True)
        #
        # i_g = shots_i0[0]
        # q_g = shots_q0[0]
        # i_e = shots_i0[1]
        # q_e = shots_q0[1]
        #
        # #
        # # plt.figure(10, figsize=(10, 7))
        # # plt.scatter(shots_i0[0], shots_q0[0], label='g', color='r', marker='*', alpha=0.5)
        # # plt.show()
        #
        # data = {'config': self.cfg, 'data': {'i_g': i_g, 'q_g': q_g, 'i_e': i_e, 'q_e': q_e}}
        # self.data = data
        #
        # ### use the helper histogram to find the fidelity and such
        # fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=None) ### arbitrary ran, change later
        # self.data_in_hist = [i_g, q_g, i_e, q_e]
        # # stop = 100
        # # plt.figure(101)
        # # plt.plot(i_g[0:stop], q_g[0:stop], 'o')
        # # plt.plot(i_e[0:stop], q_e[0:stop], 'o')
        # # plt.show()
        #
        #
        # self.fid = fid
        # self.threshold = threshold
        # self.angle = angle
        #
        # return data

    def analyze(self, data=None, span=None, verbose=True, **kwargs):
        if data is None:
            data = self.data

        fid, threshold, angle = hist(data=data, plot=False, span=span, verbose=verbose)
        data['fid'] = fid
        data['angle'] = angle
        data['threshold'] = threshold

        return data

    def display(self, data=None, span=None, verbose=True, **kwargs):
        if data is None:
            data = self.data

        fid, threshold, angle = hist(data=data, plot=True, verbose=verbose, span=span, save_title=self.iname,
                                     display_title=self.titlename)

        print(f'fidelity: {fid}')
        print(f'rotation angle (deg): {angle}')
        # print(f'set angle to (deg): {self.cfg.device.readout.phase - angle}')
        print(f'threshold: {threshold}')

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data)


def hist(data, plot=True, span=None, verbose=True, save_title = '', display_title = ''):
    """
    span: histogram limit is the mean +/- span
    """
    I0 = data['I0']
    Q0 = data['Q0']
    I1 = data['I1']
    Q1 = data['Q1']
    plot_f = False
    if 'I2' in data.keys():
        plot_f = True
        I2 = data['I2']
        Q2 = data['Q2']

    numbins = 200

    x0, y0 = np.median(I0), np.median(Q0)
    if verbose: print(f'Ig {x0} +/- {np.std(I0)} \t Qg {y0} +/- {np.std(Q0)} \t Amp g {np.abs(x0+1j*y0)}')

    x1, y1 = np.median(I1), np.median(Q1)
    if verbose: print(f'Ie {x1} +/- {np.std(I1)} \t Qe {y1} +/- {np.std(Q1)} \t Amp e {np.abs(x1+1j*y1)}')

    if plot_f:
        x2, y2 = np.median(I2), np.median(Q2)
        if verbose: print(f'If {x2} +/- {np.std(I2)} \t Qf {y2} +/- {np.std(Q2)} \t Amp f {np.abs(x2+1j*y2)}')

    if plot:
        fig, axs = plt.subplots(nrows=1, ncols=3, figsize=(16, 8))
        # fig.tight_layout()

        axs[0].scatter(I0, Q0, label='g', color='r', marker='.')
        axs[0].scatter(I1, Q1, label='e', color='b', marker='.')
        if plot_f: axs[0].scatter(I2, Q2, label='f', color='g', marker='.')
        axs[0].scatter(x0, y0, color='k', marker='o')
        axs[0].scatter(x1, y1, color='k', marker='o')
        if plot_f: axs[0].scatter(x2, y2, color='k', marker='o')

        axs[0].set_xlabel('I [ADC levels]')
        axs[0].set_ylabel('Q [ADC levels]')
        axs[0].legend(loc='upper right')
        axs[0].set_title('Unrotated')
        axs[0].axis('equal')
    """Compute the rotation angle"""
    theta = -np.arctan2((y1-y0),(x1-x0))

    """Rotate the IQ data"""
    I0_new = I0*np.cos(theta) - Q0*np.sin(theta)
    Q0_new = I0*np.sin(theta) + Q0*np.cos(theta)

    I1_new = I1*np.cos(theta) - Q1*np.sin(theta)
    Q1_new = I1*np.sin(theta) + Q1*np.cos(theta)

    if plot_f:
        I2_new = I2*np.cos(theta) - Q2*np.sin(theta)
        Q2_new = I2*np.sin(theta) + Q2*np.cos(theta)

    """New means of each blob"""
    x0, y0 = np.median(I0_new), np.median(Q0_new)
    x1, y1 = np.median(I1_new), np.median(Q1_new)
    if plot_f: x2, y2 = np.median(I2_new), np.median(Q2_new)

    if span is None:
        span = (np.max(np.concatenate((I1_new, I0_new))) - np.min(np.concatenate((I1_new, I0_new))))/2
    xlims = [x0-span, x1+span]
    ylims = [y0-span, y1+span]
    print(xlims, x0, span)

    if plot:
        axs[1].scatter(I0_new, Q0_new, label='g', color='r', marker='.')
        axs[1].scatter(I1_new, Q1_new, label='e', color='b', marker='.')
        if plot_f: axs[1].scatter(I2_new, Q2_new, label='f', color='g', marker='.')
        axs[1].scatter(x0, y0, color='k', marker='o')
        axs[1].scatter(x1, y1, color='k', marker='o')
        if plot_f: axs[1].scatter(x2, y2, color='k', marker='o')

        axs[1].set_xlabel('I [ADC levels]')
        axs[1].legend(loc='upper right')
        axs[1].set_title(f'Rotated; Angle = {theta:.3f}')
        axs[1].axis('equal')

        """X and Y ranges for histogram"""

        n0, bins0, p0 = axs[2].hist(I0_new, bins=numbins, range = xlims, color='r', label='g', alpha=0.5)
        n1, bins1, p1 = axs[2].hist(I1_new, bins=numbins, range = xlims, color='b', label='e', alpha=0.5)
        if plot_f: n2, bins2, p2 = axs[2].hist(I2_new, bins=numbins, range = xlims, color='g', label='f', alpha=0.5)
        axs[2].set_xlabel('I [ADC levels]')
        axs[2].legend(loc='upper right')

    else:
        n0, bins0 = np.histogram(I0_new, bins=numbins, range = xlims)
        n1, bins1 = np.histogram(I1_new, bins=numbins, range = xlims)


    """Compute the fidelity using overlap of the histograms"""
    # contrast = np.abs(((np.cumsum(n0) - np.cumsum(n1)) / (0.5*n0.sum() + 0.5*n1.sum())))
    contrast = np.cumsum(n0) / n0.sum() - np.cumsum(n1)/ n1.sum()
    tind=contrast.argmax()
    threshold=bins0[tind]
    fid = contrast[tind]



    ne_contrast = np.cumsum(n1)[tind] / n1.sum()
    ng_contrast = 1 - np.cumsum(n0)[tind] / n0.sum()
    print("ne contrast: ", ne_contrast)
    print("ng contrast: ", ng_contrast)
    print(contrast[tind], n0.sum(), n1.sum())

    if plot:
        axs[2].axvline(threshold, color = 'black', alpha = 0.7, ls = '--')
        axs[2].set_title(f"Fid: {fid * 100:.1f}%; Thr: {threshold:.1f}; ne: {ne_contrast:.3f}, ng: {ng_contrast:.3f}")
        plt.savefig(save_title)
        plt.suptitle(display_title)
        plt.show(block=True)
        plt.pause(0.1)



    return fid, threshold, theta #*180/np.pi



class LoopbackProgramSingleShotWorking(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        #### first do nothing, then apply the pi pulse
        cfg["start"]=0
        cfg["step"]=cfg["qubit_gain"]
        cfg["reps"]=cfg["shots"]
        cfg["expts"]=2

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_gain = self.sreg(cfg["qubit_ch"], "gain")  # get frequency register for qubit_ch
        self.r_gain2 = self.sreg(cfg["qubit_ch"], "gain2")  # get frequency register for qubit_ch

        res_ch = cfg["res_ch"]
        #         r_freq=self.sreg(cfg["res_ch"], "freq")   #Get frequency register for res_ch
        self.declare_gen(ch=res_ch, nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])

        # Qubit configuration
        qubit_ch = cfg["qubit_ch"]
        self.declare_gen(ch=qubit_ch, nqz=cfg["qubit_nqz"])

        # configure the readout lengths and downconversion frequencies
        for ro_ch in cfg["ro_chs"]:
            # self.declare_readout(ch=ro_ch, freq=cfg["pulse_freq"],
            #                      length=self.us2cycles(self.cfg["state_readout_length"]), gen_ch=cfg["res_ch"])
            self.declare_readout(ch=ro_ch, freq=cfg["pulse_freq"],
                                 length=self.us2cycles(self.cfg["readout_length"]), gen_ch=cfg["res_ch"])

        read_freq = self.freq2reg(cfg["pulse_freq"], gen_ch=res_ch, ro_ch=cfg["ro_chs"][0])
        # convert frequency to dac frequency (ensuring it is an available adc frequency)
        qubit_freq = self.freq2reg(cfg["qubit_freq"],
                                   gen_ch=qubit_ch)  # convert frequency to dac frequency (ensuring it is an available adc frequency)
        #FF Start
        for FF_info in cfg["FF_list_readout"]:
            self.declare_gen(ch=FF_info[0], nqz=cfg["ff_nqz"])

        self.ff_freq = self.freq2reg(cfg["ff_freq"], gen_ch=cfg["ff_ch"])
        self.ff_style = self.cfg["ff_pulse_style"]

        ### Finish FF
        self.FF_Channel1, self.FF_Gain1_readout = self.cfg["FF_list_readout"][0]
        self.FF_Channel2, self.FF_Gain2_readout = self.cfg["FF_list_readout"][1]
        self.FF_Channel3, self.FF_Gain3_readout = self.cfg["FF_list_readout"][2]


        self.FF_Gain1_exp = self.cfg["FF_list_exp"][0][1]
        self.FF_Gain2_exp = self.cfg["FF_list_exp"][1][1]
        self.FF_Gain3_exp = self.cfg["FF_list_exp"][2][1]

        self.FFChannels = [self.FF_Channel1, self.FF_Channel2, self.FF_Channel3]
        self.FFReadouts = np.array([self.FF_Gain1_readout, self.FF_Gain2_readout, self.FF_Gain3_readout])
        self.FFExpts = np.array([self.FF_Gain1_exp, self.FF_Gain2_exp, self.FF_Gain3_exp])

        #FF End

        # print("generator freq:", self.reg2freq(freq, gen_ch=res_ch))
        if cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"]),
                           length=self.us2cycles(self.cfg["sigma"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["start"],
                                     waveform="qubit")
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4

        elif cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"]),
                           length=self.us2cycles(self.cfg["sigma"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["start"],
                                     waveform="qubit",  length=self.us2cycles(self.cfg["flat_top_length"]))
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4 + self.us2cycles(self.cfg["flat_top_length"])

        else:
            print("define pi or flat top pulse")

        # self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0, gain=cfg["read_pulse_gain"],
        #                          length=self.us2cycles(self.cfg["readout_length"] + self.cfg["adc_trig_offset"]),
        #                          ) # mode="periodic")
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=read_freq, phase=cfg["res_phase"],
                                 gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))
        self.sync_all(200)  # give processor some time to configure pulses

    def body(self):
        self.sync_all(200)  # align channels and wait 50ns

        self.FFPulses(-1 * self.FFExpts, self.qubit_pulseLength + self.us2cycles(2))

        self.sync_all(self.us2cycles(2))  # align channels and wait 50ns

        self.FFPulses(self.FFExpts, self.qubit_pulseLength + self.us2cycles(2))

        self.pulse(ch=self.cfg["qubit_ch"], t = self.us2cycles(2))  #play probe pulse
        self.sync_all() # align


        self.FFPulses(self.FFReadouts, self.us2cycles(self.cfg["length"]))

        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(1))

        self.FFPulses(-1 * self.FFReadouts, self.us2cycles(self.cfg["length"]))

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))

        # wait = True
        # syncdelay=self.us2cycles(self.cfg["relax_delay"])
        # self.trigger([0], pins=None, adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]))
        # self.pulse(ch=self.cfg["res_ch"])
        # self.waiti(0, self.us2cycles(self.cfg["adc_trig_offset"]) + self.us2cycles(self.cfg["readout_length"]))
        # # self.waiti(0, self.us2cycles(self.cfg["readout_length"]) + 100)
        # if wait:
        #     # tProc should wait for the readout to complete.
        #     # This prevents loop counters from getting incremented before the data is available.
        #     self.wait_all()
        # if syncdelay is not None:
        #     self.sync_all(syncdelay)
        #
        # # self.synci(self.us2cycles(self.cfg["relax_delay"]))
        # self.measure(pulse_ch=self.cfg["res_ch"],
        #              adcs=[0],
        #              adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
        #              wait=True,
        #              syncdelay=self.us2cycles(self.cfg["relax_delay"]))



    def update(self):
        self.mathi(self.q_rp, self.r_gain, self.r_gain, '+', self.cfg["step"]) # update frequency list index
        self.mathi(self.q_rp, self.r_gain2, self.r_gain2, '+', int(self.cfg["step"]/2))  # update frequency list index

    def FFPulses(self, list_of_gains, length):
        for i, gain in enumerate(list_of_gains):
            self.set_pulse_registers(ch=self.FFChannels[i], style=self.ff_style, freq=self.ff_freq, phase=0,
                                     gain=gain,
                                     length=length)
        self.pulse(ch=self.FF_Channel1)
        self.pulse(ch=self.FF_Channel2)
        self.pulse(ch=self.FF_Channel3)

    def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=1, save_experiments=None,
                start_src="internal", progress=False, debug=False):

        super().acquire(soc, load_pulses=load_pulses, progress=progress, debug=debug)

        return self.collect_shots()

    def collect_shots(self):
        shots_i0=self.di_buf[0].reshape((self.cfg["expts"],self.cfg["reps"])) /self.us2cycles(self.cfg['readout_length'], ro_ch = 0)
        shots_q0=self.dq_buf[0].reshape((self.cfg["expts"],self.cfg["reps"])) /self.us2cycles(self.cfg['readout_length'], ro_ch = 0)

        return shots_i0,shots_q0


import pickle
def QuadExponentialFit(t, A1, T1, A2, T2, A3, T3, A4, T4):
    return(A1 * np.exp(-t / T1) + A2 * np.exp(-t / T2) + A3 * np.exp(-t / T3) + A4 * np.exp(-t / T4))

def Compensated_AWG(Num_Points, Fit_Parameters, maximum = 1.5):
    step = 0.00232515 / 16
    time = np.arange(0,Num_Points)*step
    ideal_AWG = np.ones(Num_Points)
    analytic_n = QuadExponentialFit(time, Fit_Parameters[0], Fit_Parameters[1], Fit_Parameters[2],
                                   Fit_Parameters[3], Fit_Parameters[4], Fit_Parameters[5],
                                   Fit_Parameters[6], Fit_Parameters[7])
    analytic_n[analytic_n < -0.8] = -0.8
    v_awg = ideal_AWG / (1 + analytic_n)
    v_awg[v_awg > maximum] = maximum
    return(time, v_awg)

def DoubleExponentialFit(t, A1, T1, A2, T2):
    return (A1 * np.exp(-t / T1) + A2 * np.exp(-t / T2))

def Compensated_AWG_LongTimes(Num_Points, Fit_Parameters, maximum = 1.5):
    step = 0.00232515 / 16
    time = np.arange(0,Num_Points)*step
    ideal_AWG = np.ones(Num_Points)
    analytic_n = DoubleExponentialFit(time, Fit_Parameters[0], Fit_Parameters[1], Fit_Parameters[2],
                                   Fit_Parameters[3])
    print('analytic_n Before correction', analytic_n[:30])
    analytic_n[analytic_n < -0.7] = -0.7
    print('analytic_n After correction', analytic_n[:30])

    v_awg = ideal_AWG / (1 + analytic_n)
    print('v_awg Before correction', v_awg[:30])

    v_awg[v_awg > maximum] = maximum
    print('v_awg After correction', v_awg[:30])

    return(time, v_awg)

Qubit1_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit1_n_exp_Final.p', 'rb'))
Qubit2_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit2_n_exp_Final.p', 'rb'))
Qubit4_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit4_n_exp_Final.p', 'rb'))

v_awg_Q1 = Compensated_AWG(600 * 16 * 3, Qubit1_)[1]
v_awg_Q2 = Compensated_AWG(600 * 16 * 3, Qubit2_)[1]
v_awg_Q4 = Compensated_AWG(600 * 16 * 3, Qubit4_)[1]

Compensated_pulse_list = [v_awg_Q1, v_awg_Q2, v_awg_Q2, v_awg_Q4]

def Compensated_Pulse(final_gain, initial_gain, Qubit_number = 1, compensated = True):
    print(Qubit_number, final_gain, initial_gain)
    if not compensated:
        return(np.ones(16 * 2000) * final_gain)
    Pulse = Compensated_pulse_list[Qubit_number - 1]
    Comp_Difference = Pulse - 1
    Comp_Step_Gain = Comp_Difference * (final_gain - initial_gain) + np.ones(len(Comp_Difference)) * final_gain
    return(Comp_Step_Gain)