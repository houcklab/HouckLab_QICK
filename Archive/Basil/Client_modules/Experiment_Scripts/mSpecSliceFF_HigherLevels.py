from qick import *
from q3diamond.Client_modules.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from q3diamond.Client_modules.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time

class PulseProbeSpectroscopyProgramFFMultipleFF(RAveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.declare_gen(ch=cfg["res_ch"], nqz=1)  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=2)  # Qubit
        for ch in [0, 1]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["read_length"]),
                                 freq=cfg["read_pulse_freq"], gen_ch=cfg["res_ch"])

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_freq = self.sreg(cfg["qubit_ch"], "freq")  # get frequency register for qubit_ch
        self.r_freq2 = 3

        self.FFDefinitions() #define the FF pulses

        f_res = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=0)  # conver f_res to dac register value
        self.f_qubit01 = self.freq2reg(cfg["qubit_freq01"], gen_ch=cfg["qubit_ch"])
        self.f_start = self.freq2reg(cfg["start"], gen_ch=cfg["qubit_ch"])  # get start/step frequencies
        self.f_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])
        self.safe_regwi(self.q_rp, self.r_freq2, self.f_start) # send start frequency to r_freq2

        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch = self.cfg["qubit_ch"])
        self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch = self.cfg["qubit_ch"])
        # print(self.pulse_sigma, self.pulse_qubit_lenth)
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit01", sigma= self.pulse_sigma, length= self.pulse_qubit_lenth)
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
                                 gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))

        self.res_wait = self.pulse_qubit_lenth + self.us2cycles(0.02 + 0.05)

        self.sync_all(self.us2cycles(0.1))

    def body(self):
        self.sync_all(self.us2cycles(0.05))  # align channels and wait 50ns

        offset_FFpulse = self.us2cycles(1.5)
        self.FFPulses(self.FFExpts, self.us2cycles(self.cfg["qubit_length"]) + offset_FFpulse)

        # self.pulse(ch=self.cfg["qubit_ch"], t = self.us2cycles(0.01))  # play probe pulse
        self.setup_and_pulse(ch=self.cfg["qubit_ch"], style="arb", freq=self.f_qubit01, phase=0,
                             gain=self.cfg["qubit_gain01"], waveform="qubit01", t = offset_FFpulse)

        self.set_pulse_registers(
            ch=self.cfg["qubit_ch"],
            style="const",
            freq=self.f_start, # freq set by update
            phase=0,
            gain=self.cfg["qubit_gain"],
            length=self.us2cycles(self.cfg["qubit_length"]))
        self.mathi(self.q_rp, self.r_freq, self.r_freq2, "+", 0)
        self.pulse(ch=self.cfg["qubit_ch"], t = offset_FFpulse + self.pulse_qubit_lenth)


        # self.sync_all(self.us2cycles(0.05))  # align channels and wait 50ns
        # self.synci(self.res_wait)
        self.sync_all()
        # trigger measurement, play measurement pulse, wait for qubit to relax
        for i, gain in enumerate(self.FFReadouts):
            self.set_pulse_registers(ch=self.FFChannels[i], style=self.ff_style, freq=self.ff_freq, phase=0,
                                     gain=gain,
                                     length=self.us2cycles(self.cfg["length"]))

        self.pulse(ch=self.FF_Channel1)
        self.pulse(ch=self.FF_Channel2)
        self.pulse(ch=self.FF_Channel3)

        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0, 1],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))


    def update(self):
        # self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.f_step)  # update frequency list index
        self.mathi(self.q_rp, self.r_freq2, self.r_freq2, '+', self.f_step) # update frequency list index


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

        self.FFChannels = [self.FF_Channel1, self.FF_Channel2, self.FF_Channel3]
        self.FFReadouts = [self.FF_Gain1_readout, self.FF_Gain2_readout, self.FF_Gain3_readout]
        self.FFExpts = [self.FF_Gain1_exp, self.FF_Gain2_exp, self.FF_Gain3_exp]


class SpecSliceFF_HigherExc(ExperimentClass):
    """
    Basic spec experiement that takes a single slice of data
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):

        prog = PulseProbeSpectroscopyProgramFFMultipleFF(self.soccfg, self.cfg)
        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False, debug=False)
        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        self.data = data

        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']

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


