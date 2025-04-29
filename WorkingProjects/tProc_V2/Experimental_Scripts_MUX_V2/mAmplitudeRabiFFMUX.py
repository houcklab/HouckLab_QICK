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

class AmplitudeRabiFFProg(AveragerProgramV2):
    def initialize(self, cfg):

        # In V2, sweep is handled by QickSweep1D
        #self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        #self.r_gain = self.sreg(cfg["qubit_ch"], "gain")  # get gain register for qubit_ch

        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["pulse_freqs"],
                         mux_gains= cfg["pulse_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=cfg["readout_length"],
                                 freq=cfg["pulse_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.add_pulse(ch=cfg["res_ch"], name='res_pulse', style="const", mask=cfg["ro_chs"], #gain=cfg["pulse_gain"],
                                 length=cfg["length"])

        self.add_loop("qubit_gain_loop", self.cfg["expts"])

        FF.FFDefinitions(self)

        self.pulse_sigma = cfg["sigma"]
        self.pulse_qubit_length = cfg["sigma"] * 4
        #print(self.pulse_sigma, self.pulse_qubit_lenth)
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=self.pulse_sigma, length=self.pulse_qubit_length)

        self.add_pulse(ch=cfg["qubit_ch"], name="qubit_pulse", style="arb", freq=cfg["f_ge"],
                                 phase=90, gain=cfg["gain_sweep"],
                                 envelope="qubit")

        self.delay_auto(0.05)

    def body(self, cfg):
        self.delay_auto(0)
        #self.sync_all(gen_t0=self.gen_t0)

        self.FFPulses(self.FFPulse, self.cfg["sigma"] * 4 + 1)
        self.pulse(ch=self.cfg["qubit_ch"], name="qubit_pulse", t=1)  # play probe pulse
        self.delay_auto(0)
        #self.sync_all(gen_t0=self.gen_t0)
        self.FFPulses(self.FFReadouts, self.cfg["length"])

        # Measure
        self.trigger(ros=self.cfg["ro_chs"], pins=[0],
                     t=self.cfg["adc_trig_offset"])
        self.pulse(self.cfg["res_ch"], name='res_pulse')
        self.delay_auto(10)

        self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
        self.FFPulses(-1 * self.FFPulse, self.cfg["sigma"] * 4 + 1)

        # Relax delay placed in program declaration
        #self.delay_auto(self.cfg["relax_delay"])
        #self.sync_all(self.us2cycles(self.cfg["relax_delay"]), gen_t0=self.gen_t0)

    def FFPulses(self, list_of_gains, length_us, t_start='auto'):
        FF.FFPulses(self, list_of_gains, length_us, t_start)

    #def update(self):
    #    self.mathi(self.q_rp, self.r_gain, self.r_gain, '+', self.cfg["step"])  # update gain of the Gaussian

class AmplitudeRabiFFMUX(ExperimentClass):
    """
    Basic AmplitudeRabi
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False):

        #### pull the data from the amp rabi sweep
        # prog = PulseProbeSpectroscopyProgram(self.soccfg, self.cfg)
        prog = AmplitudeRabiFFProg(self.soccfg, cfg=self.cfg, reps=self.cfg["reps"], final_delay=self.cfg['relax_delay'])

        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         soft_avgs = self.cfg['rounds'],
                                         start_src="internal", progress=False)
        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        self.data = data

        return data


    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi'][0][0]
        avgq = data['data']['avgq'][0][0]

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

        # fig = plt.figure(figNum+1)
        # sig = avgi + 1j * avgq
        # avgamp0 = np.abs(sig)
        # plt.plot(x_pts, avgamp0, label="Amplitude; ADC 0")
        # plt.ylabel("a.u.")
        # plt.xlabel("qubit gain")
        # plt.legend()
        # plt.title(self.titlename)
        #
        # plt.savefig(self.iname)
        #
        # if plotDisp:
        #     plt.show(block=True)
        #     plt.pause(0.1)
        # else:
        #     fig.clf(True)
        #     plt.close(fig)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


