from qick import *
from WorkingProjects.tProc_V2.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.Inductive_Coupler.Client_modules.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time
import WorkingProjects.tProc_V2.Helpers_V2.FF_utils as FF

from qick.asm_v2 import AveragerProgramV2


class QubitSpecSliceFFProg(AveragerProgramV2):
    def _initialize(self, cfg):
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit drive
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],  # Cavity drive
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["pulse_freqs"],
                         mux_gains=cfg["pulse_gains"],
                         ro_ch=cfg["ro_chs"][0])
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=cfg["readout_length"],
                                 freq=cfg["pulse_freqs"][iCh], gen_ch=cfg["res_ch"])
        # add cavity drive pulse
        self.add_pulse(ch=cfg["res_ch"], name="cavity_drive", style="const", mask=list(range(len(cfg["ro_chs"]))),
                       length=cfg["length"])

        ### Start fast flux
        FF.FFDefinitions(self)

        # sweep over the frequency of qubit_ch
        self.add_loop("qubit_freq_loop", self.cfg["SpecNumPoints"])
        # add qubit pulse
        if cfg['Gauss']:
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=self.pulse_sigma, length=4 * cfg["sigma"])
            self.add_pulse(ch=cfg["qubit_ch"], name='qubit_pulse', style="arb", freq=cfg["qubit_sweep_freq"],
                           phase=90, gain=cfg["qubit_gain"], waveform="qubit")
            self.qubit_length_us = cfg["sigma"] * 4
        else:
            self.add_pulse(ch=cfg["qubit_ch"], name='qubit_pulse', style="const", freq=cfg["qubit_sweep_freq"],
                           phase=0, gain=cfg["qubit_gain"], length=cfg["qubit_length"])
            self.qubit_length_us = cfg["qubit_length"]

        # print(cfg["qubit_length"], self.f_start, cfg['start'], cfg["qubit_gain"])
        print(self.FFPulse)
        print(cfg["mixer_freq"], cfg["pulse_freqs"], cfg["pulse_gains"], cfg["length"], self.cfg["adc_trig_offset"])

    def _body(self, cfg):
        # play probe pulse
        self.FFPulses(self.FFPulse, self.qubit_length_us + 1)
        self.pulse(ch=self.cfg["qubit_ch"], name='qubit_pulse', t=1)
        self.delay_auto()

        # trigger measurement, play measurement pulse
        self.FFPulses(self.FFReadouts, self.cfg["length"])
        self.trigger(ros=self.cfg["ro_chs"], pins=[0],
                     t=self.cfg["adc_trig_offset"])
        self.pulse(self.cfg["res_ch"], name='cavity_drive')
        self.delay_auto(10)  # delay for readout to finish

        # Apply negative of fast flux pulses
        self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
        self.FFPulses(-1 * self.FFPulse, self.qubit_length_us + 1)

    def FFPulses(self, list_of_gains, length_us, t_start='auto'):
        FF.FFPulses(self, list_of_gains, length_us, t_start)


# ====================================================== #

class QubitSpecSliceFFMUX(ExperimentClass):
    """
    Basic spec experiment that takes a single slice of data
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None,
                 progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg,
                         config_file=config_file, progress=progress)

    def acquire(self, progress=False):
        prog = QubitSpecSliceFFProg(soccfg=self.soccfg, cfg=self.cfg, reps=self.cfg['reps'],
                                    final_delay=self.cfg["relax_delay"])
        iq_list = prog.acquire(self.soc, soft_avgs=self.cfg['rounds'])
        avgi, avgq = iq_list[0][0, :, 0], iq_list[0][0, :, 1]
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

    def display(self, data=None, plotDisp=False, figNum=1, **kwargs):
        if data is None:
            data = self.data
        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi']  # [0][0]
        avgq = data['data']['avgq']  # [0][0]

        #### find the frequency corresponding to the qubit dip
        sig = avgi + 1j * avgq
        avgamp0 = np.abs(sig)

        plt.figure(figNum)
        plt.plot(x_pts, avgi, '.-', color='Orange', label="I")
        plt.plot(x_pts, avgq, '.-', color='Blue', label="Q")
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
