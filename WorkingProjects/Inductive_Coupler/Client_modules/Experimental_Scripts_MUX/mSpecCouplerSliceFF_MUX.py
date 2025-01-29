from qick import *
from WorkingProjects.Inductive_Coupler.Client_modules.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.Inductive_Coupler.Client_modules.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time
import WorkingProjects.Inductive_Coupler.Client_modules.Helpers.FF_utils as FF


class PulseProbeSpectroscopyProgramFFMultipleFF(RAveragerProgram):
    '''Attempt to readout coupler frequency on a coupler without a readout resonator
     qubit - coupler - q0
     Experiment:
         1. Pi pulse q0 at the coupler frequency to place an excitation on the coupler
         2. Drive the qubit
         3. Drive the resonator and do readout
     '''

    def initialize(self):
        cfg = self.cfg
        print((cfg['qubit_gain'], cfg['coupler_gain']))

        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit(s)

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["pulse_freqs"],
                         mux_gains=cfg["pulse_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", mask=cfg["ro_chs"],  # gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_freq = self.sreg(cfg["qubit_ch"], "freq")  # get frequency register for qubit_ch
        self.r_qfreq = 4  # to store coupler frequency while the qubit pulse frequency is loaded

        ### Start fast flux
        FF.FFDefinitions(self)
        # f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=0)  # conver f_res to dac register value

        self.f_start = self.freq2reg(cfg["start"], gen_ch=cfg["qubit_ch"])  # get start/step frequencies
        self.f_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])

        # add qubit pulse
        if cfg['Gauss']:
            self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=self.cfg["qubit_ch"])
            self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch=self.cfg["qubit_ch"])
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=self.pulse_sigma, length=self.pulse_qubit_lenth)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=cfg["qubit_freq"],
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit")
            self.qubit_length_us = cfg["sigma"] * 4
        else:
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=cfg["qubit_freq"], phase=0,
                                     gain=cfg["qubit_gain"],
                                     length=self.us2cycles(cfg["qubit_length"], gen_ch=self.cfg["qubit_ch"]))
            self.qubit_length_us = cfg["qubit_length"]

        # add coupler pulse
        if cfg['Coupler_Gauss']:
            self.coupler_sigma = self.us2cycles(cfg["coupler_sigma"], gen_ch=self.cfg["qubit_ch"])
            self.coupler_pulse_length = self.us2cycles(cfg["coupler_sigma"] * 4, gen_ch=self.cfg["qubit_ch"])
            self.add_gauss(ch=cfg["qubit_ch"], name="coupler", sigma=self.coupler_sigma,
                           length=self.coupler_pulse_length)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=self.f_start,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["coupler_gain"],
                                     waveform="coupler")
            self.coupler_length_us = cfg["coupler_sigma"] * 4
        else:
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_start, phase=0,
                                     gain=cfg["coupler_gain"],
                                     length=self.us2cycles(cfg["qubit_length"], gen_ch=self.cfg["qubit_ch"]))
            self.coupler_length_us = cfg["qubit_length"]
        self.mathi(self.q_rp, self.r_qfreq, self.r_freq, '+', 0)

    def body(self):
        self.sync_all(gen_t0=self.gen_t0)

        # First thing to try: 1) Pi pulse (gaussian) on coupler, then 2) drive qubit
        # Could we continuously drive the coupler and qubit at the same time? We only have one qubit channel
        #   so we'd have to figure out the muxing, maybe
        self.FFPulses(self.FFPulse, self.qubit_length_us + 1)

        # 1) Set up and play coupler pulse
        if self.cfg['Coupler_Gauss']:
            self.set_pulse_registers(ch=self.cfg["qubit_ch"], style="arb", freq=self.f_start,
                                     phase=self.deg2reg(90, gen_ch=self.cfg["qubit_ch"]), gain=self.cfg["coupler_gain"],
                                     waveform="coupler")
        else:
            self.set_pulse_registers(ch=self.cfg["qubit_ch"], style="const", phase=0,freq=self.f_start,
                                     gain=self.cfg["coupler_gain"],
                                     length=self.us2cycles(self.cfg["qubit_length"], gen_ch=self.cfg["qubit_ch"]))
        self.mathi(self.q_rp, self.r_freq, self.r_qfreq, '+', 0) # Sets the channel frequency
        self.pulse(ch=self.cfg["qubit_ch"])  # Drive at coupler frequency

        # 2) Set up and perform qubit drive
        if self.cfg['Gauss']:
            self.set_pulse_registers(ch=self.cfg["qubit_ch"], style="arb", freq=self.cfg["qubit_freq"],
                                     phase=self.deg2reg(90, gen_ch=self.cfg["qubit_ch"]), gain=self.cfg["qubit_gain"],
                                     waveform="qubit")
        else:
            self.set_pulse_registers(ch=self.cfg["qubit_ch"], style="const", freq=self.cfg["qubit_freq"], phase=0,
                                     gain=self.cfg["qubit_gain"],
                                     length=self.us2cycles(self.cfg["qubit_length"], gen_ch=self.cfg["qubit_ch"]))
        self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse

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
        self.mathi(self.q_rp, self.r_qfreq, self.r_qfreq, '+', self.f_step)  # update frequency list index

    def collect_shots(self):
        shots_i0 = self.di_buf[0].reshape((1, self.cfg["reps"])) / self.us2cycles(
            self.cfg['readout_length'], ro_ch=0)
        shots_q0 = self.dq_buf[0].reshape((1, self.cfg["reps"])) / self.us2cycles(
            self.cfg['readout_length'], ro_ch=0)

        return shots_i0, shots_q0

class SpecSliceFF_CouplerMUX(ExperimentClass):
    """
    Basic spec experiement that takes a single slice of data
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False):

        prog = PulseProbeSpectroscopyProgramFFMultipleFF(self.soccfg, self.cfg)
        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False)
        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        self.data = data

        x_pts = data['data']['x_pts']
        avgi = np.array(data['data']['avgi'])
        avgq = np.array(data['data']['avgq'])


        #### find the frequency corresponding to the qubit dip
        sig = avgi + 1j * avgq

        avgamp0 = np.abs(sig)
        peak_loc = np.argmax(avgamp0)
        self.qubitFreq = x_pts[peak_loc]

        return data

    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data
        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi'][0][0]
        avgq = data['data']['avgq'][0][0]
        signal = (avgi + 1j * avgq) * np.exp(1j * (2 * np.pi * self.cfg['cavity_winding_freq'] *
                                                   self.cfg["pulse_freq"] + self.cfg['cavity_winding_offset']))
        avgi = signal.real
        avgq = signal.imag
        #### find the frequency corresponding to the qubit dip
        sig = avgi + 1j * avgq
        avgamp0 = np.abs(sig)

        # plt.plot(x_pts, results[0][0][0],label="I value; ADC 0")
        # plt.plot(x_pts, results[0][0][1],label="Q value; ADC 0")

        plt.figure(figNum)
        plt.plot(x_pts, avgi, '.-', color = 'Orange', label="I")
        plt.plot(x_pts, avgq, '.-', color = 'Blue', label="Q")
        plt.ylabel("a.u.")
        plt.xlabel("Qubit Frequency (GHz)")
        plt.title(self.titlename)
        plt.legend()

        plt.savefig(self.iname[:-4] + '_IQ.png')

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)

        plt.figure(figNum)
        plt.plot(x_pts, avgamp0, label="Amplitude; ADC 0")
        plt.ylabel("a.u.")
        plt.xlabel("Qubit Frequency (GHz)")
        plt.title(self.titlename)

        plt.savefig(self.iname[:-4] + '_Amplitude.png')

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

# class QubitSpecSliceFFHigherStatesProg(RAveragerProgram):
#     def initialize(self):
#         cfg = self.cfg
#
#         self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
#         self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
#         for ch in [0, 1]:  # configure the readout lengths and downconversion frequencies
#             self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
#                                  freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])
#
#         self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
#         self.r_freq = self.sreg(cfg["qubit_ch"], "freq")  # get frequency register for qubit_ch
#         self.r_freq2 = 3
#
#         ### Start fast flux
#         FF.FFDefinitions(self)
#         f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=0)  # conver f_res to dac register value
#         self.f_01 = self.freq2reg(cfg["qubit_freq01"], gen_ch=cfg["qubit_ch"])
#
#         self.f_start = self.freq2reg(cfg["start"], gen_ch=cfg["qubit_ch"])  # get start/step frequencies
#         self.f_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])
#
#         # add qubit and readout pulses to respective channels
#         self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=self.cfg["qubit_ch"])
#         self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch=self.cfg["qubit_ch"])
#         self.add_gauss(ch=cfg["qubit_ch"], name="qubit01", sigma=self.pulse_sigma, length=self.pulse_qubit_lenth)
#         if cfg["Gauss"]:
#             self.qubit_length_us = cfg["sigma"] * 4
#             self.add_gauss(ch=cfg["qubit_ch"], name="qubit12", sigma=self.pulse_sigma, length=self.pulse_qubit_lenth)
#         else:
#             self.qubit_length_us = cfg["qubit_length"]
#         self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
#                                  gain=cfg["pulse_gain"],
#                                  length=self.us2cycles(cfg["length"]))
#
#     def body(self):
#         print(self.qubit_length_us, self.cfg['sigma'], self.cfg["qubit_gain"])
#
#         self.set_pulse_registers(ch=self.cfg["qubit_ch"], style="const", freq=self.f_start, phase=0, gain=self.cfg["qubit_gain"],
#                                  length=self.us2cycles(self.cfg["qubit_length"]))
#         self.qubit_length_us = self.cfg["qubit_length"]
#         self.sync_all(gen_t0=self.gen_t0)
#         self.FFPulses(self.FFPulse, self.qubit_length_us + 1)
#
#         # self.FFPulses(self.FFPulse, self.qubit_length_us + self.cfg['sigma'] * 4 + 1)
#         # self.setup_and_pulse(ch=self.cfg["qubit_ch"], style="arb", freq=self.f_01, phase=0,
#         #                      gain=self.cfg["qubit_gain01"], waveform="qubit01", t = self.us2cycles(1))
#         # if self.cfg['Gauss']:
#         #     self.set_pulse_registers(ch=self.cfg["qubit_ch"], style="const", freq=self.f_start, # freq set by update
#         #         phase=0, gain=self.cfg["qubit_gain"], length=self.us2cycles(self.cfg["qubit_length"]))
#         #     self.mathi(self.q_rp, self.r_freq, self.r_freq2, "+", 0)
#         #     self.pulse(ch=self.cfg["qubit_ch"], t = self.us2cycles(1) + self.pulse_qubit_lenth)
#         # # else:
#         # self.set_pulse_registers(ch=self.cfg["qubit_ch"], style="const", freq=self.f_start, # freq set by update
#         #     phase=0, gain=self.cfg["qubit_gain"], length=self.us2cycles(self.cfg["qubit_length"]))
#         self.mathi(self.q_rp, self.r_freq, self.r_freq2, "+", 0)
#         # self.pulse(ch=self.cfg["qubit_ch"])
#
#         self.pulse(ch=self.cfg["qubit_ch"], t = self.us2cycles(1))  # play probe pulse
#
#         # trigger measurement, play measurement pulse, wait for qubit to relax
#         self.sync_all(gen_t0=self.gen_t0)
#         self.FFPulses(self.FFReadouts, self.cfg["length"])
#         self.measure(pulse_ch=self.cfg["res_ch"],
#                      adcs=[0, 1],
#                      adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
#                      wait=True,
#                      syncdelay=self.us2cycles(10))
#         self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
#         self.FFPulses(-1 * self.FFPulse, self.qubit_length_us + 0.1)
#         self.sync_all(self.us2cycles(self.cfg["relax_delay"]), gen_t0=self.gen_t0)
#
#     def FFPulses(self, list_of_gains, length_us, t_start='auto'):
#         FF.FFPulses(self, list_of_gains, length_us, t_start)
#
#     def update(self):
#         self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.f_step)  # update frequency list index

# class QubitSpecSliceFFProg(RAveragerProgram):
#     def initialize(self):
#         cfg = self.cfg
#
#         self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
#         self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
#         for ch in [0, 1]:  # configure the readout lengths and downconversion frequencies
#             self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
#                                  freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])
#
#         self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
#         self.r_freq = self.sreg(cfg["qubit_ch"], "freq")  # get frequency register for qubit_ch
#         self.r_freq = self.sreg(cfg["qubit_ch"], "freq")  # get frequency register for qubit_ch
#         self.r_freq2 = 4
#         ### Start fast flux
#         FF.FFDefinitions(self)
#         f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=0)  # conver f_res to dac register value
#         self.f_ge_reg = self.freq2reg(cfg["qubit_freq"], gen_ch=cfg["res_ch"], ro_ch=0)  # conver f_res to dac register value
#
#         self.f_start = self.freq2reg(cfg["start"], gen_ch=cfg["qubit_ch"])  # get start/step frequencies
#         self.f_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])
#
#
#         # add qubit and readout pulses to respective channels
#         # if cfg['Gauss']:
#         #     self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch = self.cfg["qubit_ch"])
#         #     self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch = self.cfg["qubit_ch"])
#         #     self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma= self.pulse_sigma, length= self.pulse_qubit_lenth)
#         #     self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=self.f_start,
#         #                              phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
#         #                              waveform="qubit")
#         #     self.qubit_length_us = cfg["sigma"] * 4
#         # else:
#         # self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_start, phase=0, gain=cfg["qubit_gain"],
#         #                          length=self.us2cycles(cfg["qubit_length"]))
#         self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=self.cfg["qubit_ch"])
#         self.pulse_qubit_lenth = self.pulse_sigma * 4
#         self.add_gauss(ch=cfg["qubit_ch"], name="pi_qubit", sigma= self.pulse_sigma, length= self.pulse_qubit_lenth)
#         #
#         self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
#                                  gain=cfg["pulse_gain"],
#                                  length=self.us2cycles(cfg["length"]))
#
#     def body(self):
#         # self.sync_all(gen_t0=self.gen_t0)
#         # self.setup_and_pulse(ch=self.cfg["qubit_ch"], style="arb", freq=self.f_qubit01, phase=0,
#         #                      gain=self.cfg["qubit_gain"], waveform="qubit")
#         # self.mathi(self.q_rp, self.r_freq, self.r_freq2, "+", 0)
#         # self.set_pulse_registers(ch=self.cfg["qubit_ch"], style="const", freq=self.f_start, phase=0, gain=self.cfg["qubit_gain"],
#         #                          length=self.us2cycles(self.cfg["qubit_length"]))
#         # self.pulse(ch=self.cfg["qubit_ch"], t = self.us2cycles(1))  # play probe pulse
#         # # trigger measurement, play measurement pulse, wait for qubit to relax
#         # self.sync_all(gen_t0=self.gen_t0)
#         # self.measure(pulse_ch=self.cfg["res_ch"],
#         #              adcs=[0, 1],
#         #              adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
#         #              wait=True,
#         #              syncdelay=self.us2cycles(10))
#         # self.sync_all(self.us2cycles(self.cfg["relax_delay"]), gen_t0=self.gen_t0)
#
#         cfg=self.cfg
#
#         # init to qubit excited state
#         self.setup_and_pulse(ch=cfg["qubit_ch"], style="arb", freq=self.f_ge_reg,
#                              phase=0, gain=700, waveform="pi_qubit")
#
#         # setup and play ef probe pulse
#         self.set_pulse_registers(
#             ch=self.cfg["qubit_ch"],
#             style="const",
#             freq=0, # freq set by update
#             phase=0,
#             gain=500,
#             length=self.us2cycles(100, gen_ch=self.cfg["qubit_ch"]))
#         self.mathi(self.q_rp, self.r_freq, self.r_freq2, "+", 0)
#         self.pulse(ch=self.cfg["qubit_ch"])
#
#         # go back to ground state if in e to distinguish between e and f
#         self.setup_and_pulse(ch=cfg["qubit_ch"], style="arb", freq=self.f_ge_reg,
#                              phase=0, gain=700, waveform="pi_qubit")
#
#         self.sync_all(self.us2cycles(0.05)) # align channels and wait 50ns
#         self.measure(pulse_ch=self.cfg["res_ch"],
#                      adcs=[0, 1],
#                      adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
#                      wait=True,
#                      syncdelay=self.us2cycles(10))
#
#     def update(self):
#         self.mathi(self.q_rp, self.r_freq2, self.r_freq2, '+', self.f_step)  # update frequency list index
#
# class PulseProbeSpectroscopyProgramFFMultipleFFWorking(RAveragerProgram):
#     def initialize(self):
#         cfg = self.cfg
#
#         self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
#         self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
#         for ch in [0, 1]:  # configure the readout lengths and downconversion frequencies
#             self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
#                                  freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])
#
#         self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
#         self.r_freq = self.sreg(cfg["qubit_ch"], "freq")  # get frequency register for qubit_ch
#         self.r_freq2 = 3
#
#         # self.FFDefinitions() #define the FF pulses
#         f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=0)  # conver f_res to dac register value
#         self.f_qubit01 = self.freq2reg(cfg["qubit_freq01"], gen_ch=cfg["qubit_ch"])
#         self.f_start = self.freq2reg(cfg["start"], gen_ch=cfg["qubit_ch"])  # get start/step frequencies
#         self.f_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])
#         self.safe_regwi(self.q_rp, self.r_freq2, self.f_start) # send start frequency to r_freq2
#
#         self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch = self.cfg["qubit_ch"])
#         self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch = self.cfg["qubit_ch"])
#         # print(self.pulse_sigma, self.pulse_qubit_lenth)
#         self.add_gauss(ch=cfg["qubit_ch"], name="qubit01", sigma= self.pulse_sigma, length= self.pulse_qubit_lenth)
#         self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
#                                  gain=cfg["pulse_gain"],
#                                  length=self.us2cycles(cfg["length"]))
#
#         self.res_wait = self.pulse_qubit_lenth + self.us2cycles(0.02 + 0.05)
#
#         self.sync_all(self.us2cycles(0.1))
#
#     def body(self):
#         print(self.cfg["qubit_gain01"], self.cfg["qubit_freq01"], self.cfg["sigma"])
#         self.sync_all(self.us2cycles(0.05))  # align channels and wait 50ns
#
#         # offset_FFpulse = self.us2cycles(1.5)
#         # self.FFPulses(self.FFExpts, self.us2cycles(self.cfg["qubit_length"]) + offset_FFpulse)
#
#         # self.pulse(ch=self.cfg["qubit_ch"], t = self.us2cycles(0.01))  # play probe pulse
#         self.setup_and_pulse(ch=self.cfg["qubit_ch"], style="arb", freq=self.f_qubit01, phase=0,
#                              gain=self.cfg["qubit_gain01"], waveform="qubit01")
#
#         self.set_pulse_registers(
#             ch=self.cfg["qubit_ch"],
#             style="const",
#             freq=self.f_start, # freq set by update
#             phase=0,
#             gain=self.cfg["qubit_gain"],
#             length=self.us2cycles(self.cfg["qubit_length"] // 2))
#         self.mathi(self.q_rp, self.r_freq, self.r_freq2, "+", 0)
#         self.pulse(ch=self.cfg["qubit_ch"])
#
#
#         # self.sync_all(self.us2cycles(0.05))  # align channels and wait 50ns
#         # self.synci(self.res_wait)
#         self.sync_all()
#         # trigger measurement, play measurement pulse, wait for qubit to relax
#         # for i, gain in enumerate(self.FFReadouts):
#         #     self.set_pulse_registers(ch=self.FFChannels[i], style=self.ff_style, freq=self.ff_freq, phase=0,
#         #                              gain=gain,
#         #                              length=self.us2cycles(self.cfg["length"]))
#
#         # self.pulse(ch=self.FF_Channel1)
#         # self.pulse(ch=self.FF_Channel2)
#         # self.pulse(ch=self.FF_Channel3)
#
#         self.measure(pulse_ch=self.cfg["res_ch"],
#                      adcs=[0, 1],
#                      adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
#                      wait=True,
#                      syncdelay=self.us2cycles(self.cfg["relax_delay"]))
#
#
#     def update(self):
#         # self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.f_step)  # update frequency list index
#         self.mathi(self.q_rp, self.r_freq2, self.r_freq2, '+', self.f_step) # update frequency list index
#
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
#         self.FFChannels = [self.FF_Channel1, self.FF_Channel2, self.FF_Channel3]
#         self.FFReadouts = [self.FF_Gain1_readout, self.FF_Gain2_readout, self.FF_Gain3_readout]
#         self.FFExpts = [self.FF_Gain1_exp, self.FF_Gain2_exp, self.FF_Gain3_exp]