from qick import *
from q3diamond.Client_modules.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from Basil.Client_modules.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time

class PulseProbeSpectroscopyProgram(RAveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.declare_gen(ch=cfg["res_ch"], nqz=1)  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=2)  # Qubit
        for ch in [0, 1]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_freq = self.sreg(cfg["qubit_ch"], "freq")  # get frequency register for qubit_ch

        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=0)  # conver f_res to dac register value

        self.f_start = self.freq2reg(cfg["start"], gen_ch=cfg["qubit_ch"])  # get start/step frequencies
        self.f_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])

        # add qubit and readout pulses to respective channels
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_start, phase=0, gain=cfg["qubit_gain"],
                                 length=self.us2cycles(cfg["qubit_length"]))
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
                                 gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))

        self.sync_all(self.us2cycles(0.1))

    def body(self):
        self.sync_all(self.us2cycles(0.05))  # align channels and wait 50ns
        self.pulse(ch=self.cfg["qubit_ch"], t = self.us2cycles(0.1))  # play probe pulse
        self.sync_all()
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0, 1],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))


    def update(self):
        self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.f_step)  # update frequency list index
# ====================================================== #

class SpecSlice(ExperimentClass):
    """
    Basic spec experiement that takes a single slice of data
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):

        prog = PulseProbeSpectroscopyProgram(self.soccfg, self.cfg)
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