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


class ACStarkCalibrationProg(AveragerProgram):
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

        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=self.f_ge,
                                 phase=0, gain=cfg["pi2_gain"], waveform="qubit")
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
                                 gain=cfg["pulse_gain"], length=self.us2cycles(cfg["length"]))

        self.sync_all(self.us2cycles(0.2))

    def body(self):
        cfg = self.cfg

        self.pulse(ch=cfg["qubit_ch"])  # first pi/2
        self.sync_all()

        # AC Stark pulse — length equals current wait time, set in Python loop
        self.setup_and_pulse(ch=cfg["qubit_ch"], style="const", freq=self.f_ACStark,
                             phase=0, gain=cfg["ACStark_amplitude"],
                             length=self.us2cycles(cfg["current_wait"]))
        self.sync_all()

        # second pi/2
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=self.f_ge,
                                 phase=0, gain=cfg["pi2_gain"], waveform="qubit")
        self.pulse(ch=cfg["qubit_ch"])

        self.sync_all(self.us2cycles(0.05))
        self.measure(pulse_ch=cfg["res_ch"],
                     adcs=self.ro_chs,
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(cfg["relax_delay"]))


class ACStarkCalibration_2(ExperimentClass):
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

        amplitude_pts = np.arange(self.cfg["ACStark_amplitude_start"],
                          self.cfg["ACStark_amplitude_start"] + self.cfg["ACStark_amplitude_step"] * self.cfg["ACStark_amplitude_expts"],
                          self.cfg["ACStark_amplitude_step"])
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
                prog = ACStarkCalibrationProg(self.soccfg, self.cfg)
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

    def Ramsey_Fit(self, x_pts, y_pts):
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
            return None, None
    def display(self, data=None, plotDisp=False, plot_Ramsey=False, figNum=1, **kwargs):
        if data is None:
            data = self.data

        x_pts = data['data']['x_pts']
        amp_pts = data['data']['amp_pts']
        avgi_2D = data['data']['avgi_2D']
        avgq_2D = data['data']['avgq_2D']
        freq_list = np.array([])
        freq_err_list = np.array([])

        for i in range(len(avgi_2D)):
            avgi = avgi_2D[i]
            avgq = avgq_2D[i]
            if 'rotation_angle' not in self.cfg:
                rotation_angle = Amplitude_IQ(avgi, avgq)
            else:
                rotation_angle = self.cfg['rotation_angle']
            rotated_IQ = (avgi + 1j * avgq) * np.exp(1j * rotation_angle)
            avgi = rotated_IQ.real
            avgq = rotated_IQ.imag

            if "min_max" in data:
                ground = data["min_max"][0]
                excited = data["min_max"][-1]
                avgi = (avgi - ground) / (excited - ground)

            pOpt, pCov = self.Ramsey_Fit(x_pts, avgi)
            if pOpt is None:
                freq_list = np.append(freq_list, np.nan)
                freq_err_list = np.append(freq_err_list, np.nan)
            else:
                perr = np.sqrt(np.diag(pCov))
                # T2 = np.abs(pOpt[1])
                # T2_err = perr[1]
                freq = pOpt[2]
                freq_err = perr[2]
                freq_list = np.append(freq_list, freq)
                freq_err_list = np.append(freq_err_list, freq_err)

        # fit ax^2 + b to non-nan points
        mask = ~np.isnan(freq_list)
        def _quad_no_linear(x, a, b):
            return a * x**2 + b
        try:
            fit_params, _ = curve_fit(_quad_no_linear, amp_pts[mask], freq_list[mask]*1e3)
            a_fit, b_fit = fit_params
            x_fit = np.linspace(amp_pts[0], amp_pts[-1], 300)
            y_fit = _quad_no_linear(x_fit, a_fit, b_fit)
            fit_success = True
        except Exception:
            fit_success = False

        fig = plt.figure()
        plt.errorbar(amp_pts, freq_list*1e3, yerr=freq_err_list*1e3, fmt='o', label="data", capsize=4)
        if fit_success:
            plt.plot(x_fit, y_fit, '-', color='black', label=f"fit: {a_fit:.4e}x² + {b_fit:.4f}")
        plt.ylabel("Ramsey Frequency (kHz)")
        plt.xlabel("Amplitude (a.u.)")
        plt.legend()
        plt.title(self.titlename)
        plt.savefig(self.iname[:-4] + 'ACStark_freq_sweep.png')

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])
