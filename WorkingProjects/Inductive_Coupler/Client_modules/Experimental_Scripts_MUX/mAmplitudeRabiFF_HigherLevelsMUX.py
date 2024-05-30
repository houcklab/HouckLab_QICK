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



class AmplitudeRabiProgram(RAveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_gain = self.sreg(cfg["qubit_ch"], "gain")  # get gain register for qubit_ch
        self.r_gain2 = 3

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

        # length=self.us2cycles(cfg["length"]))

        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit

        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])  # conver f_res to dac register value
        self.f_qubit01 = self.freq2reg(cfg["qubit_freq01"], gen_ch=cfg["qubit_ch"])
        self.f_qubit12 = self.freq2reg(cfg["qubit_freq12"], gen_ch=cfg["qubit_ch"])
        self.safe_regwi(self.q_rp, self.r_gain2, cfg["start"]) # send start frequency to r_freq2

        FF.FFDefinitions(self)

        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch = self.cfg["qubit_ch"])
        self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch = self.cfg["qubit_ch"])

        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma= self.pulse_sigma, length= self.pulse_qubit_lenth)
        # self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=self.f_qubit01,
        #                          phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["start"],
        #                          waveform="qubit")

        self.sync_all(self.us2cycles(0.05))

    def body(self):
        self.sync_all(gen_t0=self.gen_t0)

        self.FFPulses(self.FFPulse, 2 * self.cfg["sigma"] * 4 + 1.01)
        self.setup_and_pulse(ch=self.cfg["qubit_ch"], style="arb", freq=self.f_qubit01, phase=0,
                             gain=self.cfg["qubit_gain01"], waveform="qubit", t = self.us2cycles(1))
        self.set_pulse_registers(ch=self.cfg["qubit_ch"], style="arb", freq=self.f_qubit12,
                                 phase=self.deg2reg(90, gen_ch=self.cfg["qubit_ch"]), gain=self.cfg["start"],
                                 waveform="qubit")
        self.mathi(self.q_rp, self.r_gain, self.r_gain2, "+", 0)
        self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse

        self.sync_all(gen_t0=self.gen_t0)

        self.FFPulses(self.FFReadouts, self.cfg["length"])
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"], pins=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=False,
                     syncdelay=self.us2cycles(10))
        self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
        self.FFPulses(-1 * self.FFPulse, 2 * self.cfg["sigma"] * 4 + 1.01)
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]), gen_t0=self.gen_t0)

    def update(self):
        self.mathi(self.q_rp, self.r_gain2, self.r_gain2, '+', self.cfg["step"])  # update gain of the Gaussian

    def FFPulses(self, list_of_gains, length_us, t_start='auto'):
        FF.FFPulses(self, list_of_gains, length_us, t_start)




class AmplitudeRabiFF_HigherExcMUX(ExperimentClass):
    """
    Basic AmplitudeRabi
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False):

        #### pull the data from the amp rabi sweep
        # prog = PulseProbeSpectroscopyProgram(self.soccfg, self.cfg)
        prog = AmplitudeRabiProgram(self.soccfg, self.cfg)

        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False)
        signal = (avgi + 1j * avgq) * np.exp(1j * (2 * np.pi * self.cfg['cavity_winding_freq'] *
                                                   self.cfg["pulse_freq"] + self.cfg['cavity_winding_offset']))
        avgi = signal.real
        avgq = signal.imag
        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        self.data = data

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

        while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
            figNum += 1
        fig = plt.figure(figNum)
        plt.plot(x_pts, avgi, 'o-', label="i", color = 'orange')
        plt.plot(x_pts, avgq, label="q", color = 'blue')
        plt.ylabel("a.u.")
        plt.xlabel("qubit gain")
        plt.legend()
        plt.title(self.titlename)

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

        fig = plt.figure(figNum+1)
        sig = avgi + 1j * avgq
        avgamp0 = np.abs(sig)
        plt.plot(x_pts, avgamp0, label="Amplitude; ADC 0")
        plt.ylabel("a.u.")
        plt.xlabel("qubit gain")
        plt.legend()
        plt.title(self.titlename)

        plt.savefig(self.iname)

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])




class AmplitudeRabiProgramWork(RAveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_gain = self.sreg(cfg["qubit_ch"], "gain")  # get gain register for qubit_ch
        self.r_gain2 = 3

        # print(self.r_gain)
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        for ch in [0, 1]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])

        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=0)  # conver f_res to dac register value
        self.f_qubit01 = self.freq2reg(cfg["qubit_freq01"], gen_ch=cfg["qubit_ch"])
        self.f_qubit12 = self.freq2reg(cfg["qubit_freq12"], gen_ch=cfg["qubit_ch"])
        self.safe_regwi(self.q_rp, self.r_gain2, cfg["start"]) # send start frequency to r_freq2

        self.FFDefinitions() #define the FF pulses

        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch = self.cfg["qubit_ch"])
        self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch = self.cfg["qubit_ch"])

        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma= self.pulse_sigma, length= self.pulse_qubit_lenth)
        # self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=self.f_qubit01,
        #                          phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["start"],
        #                          waveform="qubit")
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
                                 gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))

        self.sync_all(self.us2cycles(0.05))

    def body(self):

        offset_FFpulse = self.us2cycles(1.5)
        self.sync_all(self.us2cycles(0.05))  # align channels and wait 50ns

        self.FFPulses(self.FFExpts, 2 * self.pulse_qubit_lenth + offset_FFpulse)
        self.setup_and_pulse(ch=self.cfg["qubit_ch"], style="arb", freq=self.f_qubit01, phase=0,
                             gain=self.cfg["qubit_gain01"], waveform="qubit", t = offset_FFpulse)
        self.set_pulse_registers(ch=self.cfg["qubit_ch"], style="arb", freq=self.f_qubit12,
                                 phase=self.deg2reg(90, gen_ch=self.cfg["qubit_ch"]), gain=self.cfg["start"],
                                 waveform="qubit")
        self.mathi(self.q_rp, self.r_gain, self.r_gain2, "+", 0)
        self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse

        self.sync_all()

        # self.FFPulses(self.FFExpts, self.us2cycles(self.cfg["length"]))

        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.ro_chs,
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_gain2, self.r_gain2, '+', self.cfg["step"])  # update gain of the Gaussian

    def FFPulses(self, list_of_gains, length):
        for i, gain in enumerate(list_of_gains):
            self.set_pulse_registers(ch=self.FFChannels[i], style=self.ff_style, freq=self.ff_freq, phase=0,
                                     gain=gain,
                                     length=length)
        self.pulse(ch=self.FF_Channel1)
        self.pulse(ch=self.FF_Channel2)
        self.pulse(ch=self.FF_Channel3)

    def FFDefinitions(self):
        ### Start fast flux
        for FF_info in self.cfg["FF_list_readout"]:
            self.declare_gen(ch=FF_info[0], nqz=self.cfg["ff_nqz"])

        self.ff_freq = self.freq2reg(self.cfg["ff_freq"], gen_ch=self.cfg["ff_ch"])
        self.ff_style = self.cfg["ff_pulse_style"]

        ### Finish FF
        self.FF_Channel1, self.FF_Gain1_readout = self.cfg["FF_list_readout"][0]
        self.FF_Channel2, self.FF_Gain2_readout = self.cfg["FF_list_readout"][1]
        self.FF_Channel3, self.FF_Gain3_readout = self.cfg["FF_list_readout"][2]

        self.FF_Gain1_exp = self.cfg["FF_list_exp"][0][1]
        self.FF_Gain2_exp = self.cfg["FF_list_exp"][1][1]
        self.FF_Gain3_exp = self.cfg["FF_list_exp"][2][1]

        self.FFChannels = np.array([self.FF_Channel1, self.FF_Channel2, self.FF_Channel3])
        self.FFReadouts = np.array([self.FF_Gain1_readout, self.FF_Gain2_readout, self.FF_Gain3_readout])
        self.FFExpts = np.array([self.FF_Gain1_exp, self.FF_Gain2_exp, self.FF_Gain3_exp])
