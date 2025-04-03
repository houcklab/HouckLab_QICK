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


class QubitSpecSliceFFProg(AveragerProgram):
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

        ### Start fast flux
        FF.FFDefinitions(self)
        self.f_ge = self.freq2reg(cfg["qubit_freq"], gen_ch=cfg["qubit_ch"])  # get start/step frequencies
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit

        # add qubit and readout pulses to respective channels
        if cfg['Gauss']:
            self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch = self.cfg["qubit_ch"])
            self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch = self.cfg["qubit_ch"])
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma= self.pulse_sigma, length= self.pulse_qubit_lenth)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=self.f_ge,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit")
            self.qubit_length_us = cfg["sigma"] * 4
        else:
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_ge, phase=0, gain=cfg["qubit_gain"],
                                     length=self.us2cycles(cfg["qubit_length"], gen_ch = self.cfg["qubit_ch"]))
            self.qubit_length_us = cfg["qubit_length"]
            self.pulse_qubit_lenth = self.us2cycles(cfg["qubit_length"], gen_ch = self.cfg["qubit_ch"])

        # print(cfg['qubit_freq'], self.f_ge)


    def body(self):
        self.sync_all(gen_t0=self.gen_t0)
        self.FFPulses(self.FFPulse, self.qubit_length_us + 1)
        self.pulse(ch=self.cfg["qubit_ch"], t = self.us2cycles(1))  # play probe pulse
        # print(self.gen_t0, self._adc_ts, self._dac_ts, self.pulse_qubit_lenth, self.cycles2us(1, gen_ch = self.cfg["qubit_ch"]), self.us2cycles(self.cfg["qubit_length"]))
        self.sync_all(gen_t0=self.gen_t0)
        self.FFPulses(self.FFReadouts, self.cfg["length"])
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

# ====================================================== #

class QubitSpecSliceFFMUX_NoUpdate(ExperimentClass):
    """
    Basic spec experiement that takes a single slice of data
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False):

        # prog = QubitSpecSliceFFProg(self.soccfg, self.cfg)
        fpts = np.linspace(self.cfg["qubit_freq"] - self.cfg["SpecSpan"],
                           self.cfg["qubit_freq"] + self.cfg["SpecSpan"],
                           self.cfg["SpecNumPoints"])
        # print(fpts)


        results = []
        start = time.time()
        for f in tqdm(fpts, position=0, disable=True):
            self.cfg["qubit_freq"] = f
            prog = QubitSpecSliceFFProg(self.soccfg, self.cfg)
            results.append(prog.acquire(self.soc, load_pulses=True))
        print(f'Time: {time.time() - start}')
        results = np.transpose(results)
        # print(results)

        avgi = results[0][0][0]
        avgq = results[0][0][1]

        data = {'config': self.cfg, 'data': {'x_pts': fpts, 'avgi': avgi, 'avgq': avgq}}
        self.data = data

        return data

    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data
        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi']#[0][0]
        avgq = data['data']['avgq']#[0][0]

        # print(x_pts, avgi)

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


