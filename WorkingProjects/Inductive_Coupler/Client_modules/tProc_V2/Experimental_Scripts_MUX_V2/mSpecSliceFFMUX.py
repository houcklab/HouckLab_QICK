from qick import *
from WorkingProjects.Inductive_Coupler.Client_modules.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.Inductive_Coupler.Client_modules.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time
import WorkingProjects.Inductive_Coupler.Client_modules.tProc_V2.Helpers_V2.FF_utils as FF

from qick.asm_v2 import AveragerProgramV2

class QubitSpecSliceFFProg(AveragerProgramV2):
    def initialize(self, cfg):

        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["pulse_freqs"],
                         mux_gains= cfg["pulse_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=cfg["readout_length"],
                                 freq=cfg["pulse_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.add_pulse(ch=cfg["res_ch"], name="mymux", style="const", mask=cfg["ro_chs"], #gain=cfg["pulse_gain"],
                                 length=cfg["length"])

        # want to sweep freq of qubit_ch
        # self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        # self.r_freq = self.sreg(cfg["qubit_ch"], "freq")  # get frequency register for qubit_ch

        ### Start fast flux
        FF.FFDefinitions(self)
        # f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=0)  # conver f_res to dac register value
        # not needed in v2
        #self.f_start = self.freq2reg(cfg["start"], gen_ch=cfg["qubit_ch"])  # get start/step frequencies
        #self.f_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])

        # add a loop to sweep over the frequency of qubit_ch
        self.add_loop("qubit_ch_freq_loop", self.cfg["SpecNumPoints"])
        # add qubit and readout pulses to respective channels
        if cfg['Gauss']:
            self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch = self.cfg["qubit_ch"])
            self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch = self.cfg["qubit_ch"])
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma= self.pulse_sigma, length= self.pulse_qubit_lenth)
            self.add_pulse(ch=cfg["qubit_ch"], name='qubit_pulse', style="arb", freq=cfg["qubit_sweep_freq"],
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit")
            self.qubit_length_us = cfg["sigma"] * 4
        else:
            self.add_pulse(ch=cfg["qubit_ch"], name='qubit_pulse', style="const", freq=cfg["qubit_sweep_freq"], phase=0,
                           gain=cfg["qubit_gain"], length=cfg["qubit_length"])
            self.qubit_length_us = cfg["qubit_length"]

        #print(cfg["qubit_length"], self.f_start, cfg['start'], cfg["qubit_gain"])
        print(self.FFPulse)
        print(cfg["mixer_freq"], cfg["pulse_freqs"], cfg["pulse_gains"], cfg["length"], self.cfg["adc_trig_offset"])

    def body(self, cfg):
        ###self.sync_all(gen_t0=self.gen_t0)
        self.FFPulses(self.FFPulse, self.qubit_length_us + 1)
        self.pulse(ch=self.cfg["qubit_ch"], name='qubit_pulse', t = 1)  # play probe pulse

        # trigger measurement, play measurement pulse, wait for qubit to relax
        ###self.sync_all(gen_t0=self.gen_t0)
        self.FFPulses(self.FFReadouts, self.cfg["length"])

        self.trigger(ros=self.cfg["ro_chs"], pins=[0],
                     t=self.cfg["adc_trig_offset"])
        self.pulse(self.cfg["res_ch"], name='mymux')
        # self.measure(pulse_ch=self.cfg["res_ch"],
        #              adcs=self.cfg["ro_chs"], pins=[0],
        #              adc_trig_offset=self.cfg["adc_trig_offset"],
        #              wait=False,
        #              syncdelay=self.us2cycles(10))
        self.delay_auto(10)
        self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
        self.FFPulses(-1 * self.FFPulse, self.qubit_length_us + 1)
        #self.sync_all(self.us2cycles(self.cfg["relax_delay"]), gen_t0=self.gen_t0)

    def FFPulses(self, list_of_gains, length_us, t_start='auto'):
        FF.FFPulses(self, list_of_gains, length_us, t_start)

    # Not needed with the v2 Sweep functionality
    #def update(self):
    #    self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.f_step)  # update frequency list index
# ====================================================== #

class QubitSpecSliceFFMUX(ExperimentClass):
    """
    Basic spec experiement that takes a single slice of data
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False):

        prog = QubitSpecSliceFFProg(soccfg=self.soccfg, cfg=self.cfg, reps=self.cfg['reps'], final_delay=self.cfg["relax_delay"])
        iq_list = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         start_src="internal", progress=False)

        avgi, avgq = iq_list[0][0,:,0], iq_list[0][0,:,1]
        x_pts = prog.get_pulse_param("qubit_pulse", "freq", as_array=True)

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
        avgi = data['data']['avgi']#[0][0]
        avgq = data['data']['avgq']#[0][0]

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
        plt.close(figNum)

        # plt.figure(figNum)
        # plt.plot(x_pts, avgamp0, label="Amplitude; ADC 0")
        # plt.ylabel("a.u.")
        # plt.xlabel("Qubit Frequency (GHz)")
        # plt.title(self.titlename)
        #
        # plt.savefig(self.iname[:-4] + '_Amplitude.png')
        #
        # if plotDisp:
        #     plt.show(block=True)
        #     plt.pause(0.1)
        # plt.close(figNum)


    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


