from qick import *
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time
from scipy.optimize import curve_fit
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT1FF import Amplitude_IQ


class T1ACStarkProg(AveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        for ch in cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])

        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])
        self.f_ge = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])
        self.f_ACStark = self.freq2reg(cfg["f_ge"] + cfg["ACStark_detuning"], gen_ch=cfg["qubit_ch"])

        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=cfg["qubit_ch"])
        self.pulse_qubit_length = self.us2cycles(cfg["sigma"] * 4, gen_ch=cfg["qubit_ch"])
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=self.pulse_sigma, length=self.pulse_qubit_length)

        # self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=self.f_ge,
        #                          phase=0, gain=cfg["pi2_gain"], waveform="qubit")
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
                                 gain=cfg["pulse_gain"], length=self.us2cycles(cfg["length"]))

        self.sync_all(self.us2cycles(0.2))

        # pi pulse from T1FF.py
        if cfg["flattop_length"] != None:
            flattop_length = self.us2cycles(self.cfg["flattop_length"], gen_ch=self.cfg["qubit_ch"])
            self.set_pulse_registers(ch=cfg["qubit_ch"], style='flat_top', freq=self.f_ge,
                                     phase=self.deg2reg(0, gen_ch=cfg["qubit_ch"]), gain=cfg["pi_gain"],
                                     waveform="qubit",
                                     length=flattop_length) #Flat part of flattop does NOT update with gain
            self.pulse_qubit_lenth += flattop_length
        else:
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=self.f_ge,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["pi_gain"],
                                     waveform="qubit")

    def body(self):
        cfg = self.cfg

        # re-configure pi pulse each rep (setup_and_pulse overwrites these registers)
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=self.f_ge,
                                 phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["pi_gain"],
                                 waveform="qubit")
        self.pulse(ch=cfg["qubit_ch"])  # pi pulse
        self.sync_all()

        # AC Stark pulse — length equals current wait time, set in Python loop
        self.setup_and_pulse(ch=cfg["qubit_ch"], style="const", freq=self.f_ACStark,
                             phase=0, gain=cfg["ACStark_amplitude"],
                             length=self.us2cycles(cfg["current_wait"]))
        # self.sync_all()

        self.sync_all(self.us2cycles(0.05))
        self.measure(pulse_ch=cfg["res_ch"],
                     adcs=self.ro_chs,
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(cfg["relax_delay"]))


class T1ACStark(ExperimentClass):
    """
    Ramsey measurement with AC Stark pulse filling the wait time between pi/2 pulses.
    Uses AveragerProgram so the Stark pulse length can be set in Python each iteration.
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
        x_pts = np.arange(self.cfg["start"],
                          self.cfg["start"] + self.cfg["step"] * self.cfg["expts"],
                          self.cfg["step"])

        if self.cfg["ACStark_amplitude_list"] is None:
            amplitude_pts = np.arange(self.cfg["ACStark_amplitude_start"],
                              self.cfg["ACStark_amplitude_start"] + self.cfg["ACStark_amplitude_step"] * self.cfg["ACStark_amplitude_expts"],
                              self.cfg["ACStark_amplitude_step"])
        else:
            amplitude_pts = self.cfg["ACStark_amplitude_list"]
        amplitude_pts = amplitude_pts.astype(int)

        avgi_list_2D = []
        avgq_list_2D = []
        # now sweeping amplitude too
        for amplitude in amplitude_pts:
            self.cfg["ACStark_amplitude"] = amplitude
            avgi_list = []
            avgq_list = []
            for wait_time in x_pts:
                self.cfg["current_wait"] = float(wait_time)
                prog = T1ACStarkProg(self.soccfg, self.cfg)
                avgi, avgq = prog.acquire(self.soc, load_pulses=True,
                                          readouts_per_experiment=1,
                                          start_src="internal", progress=False)
                avgi_list.append(avgi[0][0])
                avgq_list.append(avgq[0][0])
            avgi_list_2D.append(avgi_list)
            avgq_list_2D.append(avgq_list)

        avgi_2D = np.array(avgi_list_2D)
        avgq_2D = np.array(avgq_list_2D)

        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'amp_pts': amplitude_pts, 'avgi_2D': avgi_2D, 'avgq_2D': avgq_2D}}
        self.data = data
        return data

    '''def Ramsey_Fit(self, x_pts, y_pts):
        def _decayingCos(t, A, T2, freq, phase, offset):
            return A * np.exp(-t / T2) * np.cos(2 * np.pi * freq * t + phase) + offset

        dt = x_pts[1] - x_pts[0]
        yf = np.fft.rfft(y_pts - np.mean(y_pts))
        xf = np.fft.rfftfreq(len(x_pts), dt)
        freq0 = xf[np.argmax(np.abs(yf[1:])) + 1]
        A0 = (np.max(y_pts) - np.min(y_pts)) / 2
        T2_0 = (x_pts[-1] - x_pts[0]) / 2
        offset0 = np.mean(y_pts)
        guess = [A0, T2_0, freq0, 0, offset0]

        try:
            pOpt, pCov = curve_fit(_decayingCos, x_pts, y_pts, p0=guess, maxfev=10000,
                                   bounds=([-np.inf, 0, 0, -np.pi, -np.inf],
                                           [np.inf, np.inf, np.inf, np.pi, np.inf]))
            return pOpt, pCov
        except Exception:
            return None, None'''
    def display(self, data=None, plotDisp=False, plot_Ramsey=False, figNum=1, **kwargs):
        if data is None:
            data = self.data

        x_pts = data['data']['x_pts']
        amp_pts = data['data']['amp_pts']
        avgi_2D = data['data']['avgi_2D']
        avgq_2D = data['data']['avgq_2D']
        freq_list = np.array([])
        freq_err_list = np.array([])

        avgi = avgi_2D[:, 0]
        avgq = avgq_2D[:, 0]

        # IQ rotation
        rotation_angle = self.cfg['rotation_angle']
        rotated_IQ = (avgi + 1j * avgq) * np.exp(1j * rotation_angle)

        avgi = rotated_IQ.real
        avgq = rotated_IQ.imag

        fig = plt.figure()
        plt.plot(amp_pts, avgi, 'o', label="i", color='orange')
        plt.ylabel("a.u.")
        plt.xlabel("Amplitude (a.u.)")
        plt.legend()
        plt.title(self.titlename)
        plt.savefig(self.iname[:-4] + 'T1ACStark_I_data.png')

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

        fig = plt.figure()
        plt.plot(amp_pts, avgq, 'o', label="q", color='blue')
        plt.ylabel("a.u.")
        plt.xlabel("Amplitude (a.u.)")
        plt.legend()
        plt.title(self.titlename)
        plt.savefig(self.iname[:-4] + 'T1ACStark_Q_data.png')

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])
