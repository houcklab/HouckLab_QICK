from qick import *
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time

class CavitySpecFFProg(AveragerProgram):
    def initialize(self):
        cfg = self.cfg
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])  # Readout
        for ch in cfg["ro_chs"]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])
        freq = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"],
                             ro_ch=cfg["ro_chs"][0])  # convert frequency to dac frequency (ensuring it is an available adc frequency)
        if 'ro_periodic' in self.cfg.keys():
            if self.cfg['ro_periodic']:
                print("Readout periodic")
                self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=freq, phase=0,
                                         gain=cfg["pulse_gain"],
                                         length=self.us2cycles(cfg["length"], gen_ch=cfg["res_ch"]) , mode='periodic')
            else:
                self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=freq, phase=cfg["res_phase"],
                                         gain=cfg["pulse_gain"],
                                         length=self.us2cycles(cfg["length"]))  # , mode='periodic')
        else:
            self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=freq, phase=cfg["res_phase"],
                                     gain=cfg["pulse_gain"],
                                     length=self.us2cycles(cfg["length"]))
        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        self.sync_all(200)
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))
        self.sync_all(self.us2cycles(self.cfg["cav_relax_delay"]))

    # ====================================================== #

class CavitySpecFF(ExperimentClass):
    """
    Transmission Experiment basic
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
        fpts = np.linspace(self.cfg["pulse_freq"] - self.cfg["TransSpan"],
                           self.cfg["pulse_freq"] + self.cfg["TransSpan"],
                           self.cfg["TransNumPoints"])
        results = []
        start = time.time()
        for f in tqdm(fpts, position=0, disable=True):
            self.cfg["pulse_freq"] = f
            prog = CavitySpecFFProg(self.soccfg, self.cfg)
            results.append(prog.acquire(self.soc, load_pulses=True))
        print(f'Time: {time.time() - start}')
        results = np.transpose(results)
        data={'config': self.cfg, 'data': {'results': results, 'fpts':fpts}}
        self.data=data

        #### find the frequency corresponding to the peak
        sig = data['data']['results'][0][0][0] + 1j * data['data']['results'][0][0][1]
        avgamp0 = np.abs(sig)
        peak_loc = np.argmin(avgamp0)
        self.peakFreq_min = data['data']['fpts'][peak_loc]
        peak_loc = np.argmax(avgamp0)
        self.peakFreq_max = data['data']['fpts'][peak_loc]

        return data

    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        avgi = data['data']['results'][0][0][0]
        avgq = data['data']['results'][0][0][1]
        x_pts = (data['data']['fpts'] + self.cfg["cavity_LO"] / 1e6) / 1e3  #### put into units of frequency GHz
        sig = avgi + 1j * avgq

        signal = (avgi + 1j * avgq)
        avgi = signal.real
        avgq = signal.imag
        avgamp0 = np.abs(signal)

        plt.figure(figNum)
        plt.plot(x_pts, avgi, '.-', color = 'Green', label="I")
        plt.plot(x_pts, avgq, '.-', color = 'Blue', label="Q")
        plt.plot(x_pts, avgamp0, color = 'Magenta', label="Amp")
        plt.ylabel("a.u.")
        plt.xlabel("Cavity Frequency (GHz)")
        plt.title(self.iname)
        plt.legend()

        plt.savefig(self.iname)

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        plt.close(figNum)


    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])





