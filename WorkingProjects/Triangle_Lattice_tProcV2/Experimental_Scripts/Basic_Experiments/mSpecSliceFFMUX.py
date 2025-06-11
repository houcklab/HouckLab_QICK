from qick import *

from qick.asm_v2 import QickSweep1D

from WorkingProjects.Triangle_Lattice_tProcV2.Program_Templates.AveragerProgramFF import FFAveragerProgramV2
from WorkingProjects.Triangle_Lattice_tProcV2.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.Triangle_Lattice_tProcV2.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time
import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.FF_utils as FF


class QubitSpecSliceFFProg(FFAveragerProgramV2):
    def _initialize(self, cfg):
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"],
                         mixer_freq=cfg["qubit_mixer_freq"])  # Qubit

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["res_nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["res_freqs"],
                         mux_gains= cfg["res_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=cfg["readout_length"],
                                 freq=cfg["res_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.add_pulse(ch=cfg["res_ch"], name="res_drive", style="const", mask=cfg["ro_chs"],
                                 length=cfg["res_length"])


        ### Start fast flux
        FF.FFDefinitions(self)

        self.add_loop("qubit_freq_loop", self.cfg["SpecNumPoints"])
        # add qubit pulse
        if cfg['Gauss']:
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=cfg["sigma"], length=4 * cfg["sigma"])
            self.add_pulse(ch=cfg["qubit_ch"], name='qubit_drive', style="arb", freq=cfg["qubit_freq_sweep"],
                           phase=90, gain=cfg["qubit_gain"], waveform="qubit")
            self.qubit_length_us = cfg["sigma"] * 4
        else:
            self.add_pulse(ch=cfg["qubit_ch"], name='qubit_drive', style="const", freq=4500,#cfg["qubit_freq_sweep"],
                           phase=0, gain=cfg["qubit_gain"], length=cfg["qubit_length"])
            self.qubit_length_us = cfg["qubit_length"]


    def _body(self, cfg):

        self.FFPulses(self.FFPulse, self.qubit_length_us + 1)
        self.pulse(ch=cfg["qubit_ch"], name="qubit_drive", t = 1)  # play probe pulse
        # trigger measurement, play measurement pulse, wait for qubit to relax
        self.delay_auto()

        self.FFPulses(self.FFReadouts, cfg["res_length"])
        self.delay(0.5)  # delay trigger and pulse to 0.5 us after beginning of FF pulses
        self.trigger(ros=cfg["ro_chs"], pins=[0],
                     t=cfg["adc_trig_delay"])
        self.pulse(cfg["res_ch"], name='res_drive')
        self.wait_auto()
        self.delay_auto(10)  # us

        self.FFPulses(-1 * self.FFReadouts, cfg["res_length"])
        self.FFPulses(-1 * self.FFPulse, self.qubit_length_us + 1)

# ====================================================== #

class QubitSpecSliceFFMUX(ExperimentClass):
    """
    Basic spec experiement that takes a single slice of data
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False):
        cfg = self.cfg
        self.cfg["qubit_freq_sweep"] = QickSweep1D("qubit_freq_loop",
                                    start=cfg["qubit_freqs"][0] - cfg["SpecSpan"],
                                    end=cfg["qubit_freqs"][0] + cfg["SpecSpan"]),
        self.cfg.setdefault("qubit_length", 100) ### length of CW drive in us

        prog = QubitSpecSliceFFProg(self.soccfg, cfg=self.cfg, reps=self.cfg["reps"],
                                    final_delay=self.cfg["relax_delay"])
        iq_list = prog.acquire(self.soc, load_pulses=True,
                               soft_avgs=self.cfg.get('rounds', 1),
                               progress=progress)
        print(np.array(iq_list).shape)
        avgi, avgq = iq_list[0][0, :, 0], iq_list[0][0, :, 1]
        x_pts = prog.get_pulse_param("qubit_drive", "freq", as_array=True)
        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        self.data = data

        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi'][0]
        avgq = data['data']['avgq'][0]

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
        plt.close(figNum)



    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


