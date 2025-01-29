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

from scipy.optimize import minimize as scipy_minimize
def find_angle(Imat, Qmat):
    def newQvariance(theta):
        newQ = np.sin(theta)*Imat + np.cos(theta)*Qmat
        return np.max(newQ) - np.min(newQ)
    angle = scipy_minimize(newQvariance, (np.pi/4,)).x
    return angle
def rotate(theta, Imat, Qmat):
    return np.cos(theta)*Imat - np.sin(theta)*Qmat, np.sin(theta)*Imat + np.cos(theta)*Qmat # newI, newQ
def get_ampl(Imat, Qmat):
    angle = find_angle(Imat, Qmat)
    newI, newQ = rotate(angle, Imat, Qmat)
    return newI - np.mean(newI)

class YPulseFFProg(RAveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_phase = self.sreg(cfg["qubit_ch"], "phase")  # get phase register for qubit_ch
        self.r_phase2 = 4 # To store the phase of the Y-pulse
        self.regwi(self.q_rp, self.r_phase2, self.deg2reg(cfg['start'], gen_ch=cfg["qubit_ch"]))

        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["pulse_freqs"],
                         mux_gains= cfg["pulse_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", mask=cfg["ro_chs"], #gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))

        f_ge = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])

        FF.FFDefinitions(self)

        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch = self.cfg["qubit_ch"])
        self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch = self.cfg["qubit_ch"])
        print(self.pulse_sigma, self.pulse_qubit_lenth)
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma= self.pulse_sigma, length= self.pulse_qubit_lenth)

        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=f_ge,
                                 phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                 waveform="qubit")


        self.sync_all(self.us2cycles(0.05))

    def body(self):
        self.sync_all(gen_t0=self.gen_t0)
        # self.pulse(ch=self.cfg['ff_ch'])
        self.FFPulses(self.FFPulse, self.cfg["sigma"] * 4 + 1)

        self.regwi(self.q_rp, self.r_phase, self.deg2reg(0, gen_ch=self.cfg["qubit_ch"])) # X pi/2 pulse
        self.pulse(ch=self.cfg["qubit_ch"], t=self.us2cycles(1))
        self.mathi(self.q_rp, self.r_phase, self.r_phase2, '+', 0) # Y pi/2 pulse
        self.pulse(ch=self.cfg["qubit_ch"], t='auto')
        self.regwi(self.q_rp, self.r_phase, self.deg2reg(0, gen_ch=self.cfg["qubit_ch"]))  # X pi/2 pulse
        self.pulse(ch=self.cfg["qubit_ch"], t='auto')

        self.sync_all(gen_t0=self.gen_t0)
        self.FFPulses(self.FFReadouts, self.cfg["length"])

        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"], pins=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))
        self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
        self.FFPulses(-1 * self.FFPulse, self.cfg["sigma"] * 4 + 1)
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]), gen_t0=self.gen_t0)

    def FFPulses(self, list_of_gains, length_us, t_start='auto'):
        FF.FFPulses(self, list_of_gains, length_us, t_start)

    def update(self):
        self.mathi(self.q_rp, self.r_phase2, self.r_phase2, '+', self.deg2reg(self.cfg["step"], gen_ch=self.cfg["qubit_ch"]))  # update phase of the Gaussian

class YPulseFFMUX(ExperimentClass):
    """
    Basic AmplitudeRabi
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False):

        #### pull the data from the amp rabi sweep
        # prog = PulseProbeSpectroscopyProgram(self.soccfg, self.cfg)
        prog = YPulseFFProg(self.soccfg, self.cfg)

        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
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
        avg_ampl = get_ampl(avgi, avgq)

        while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
            figNum += 1
        fig = plt.figure(figNum)
        plt.plot(x_pts, avgi, 'o-', label="i", color = 'orange')
        plt.plot(x_pts, avgq, label="q", color = 'blue')
        plt.plot(x_pts, avg_ampl, label="normalized", color='green')
        plt.ylabel("a.u.")
        plt.xlabel("qubit phase")
        plt.legend()
        plt.title(self.titlename)

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


