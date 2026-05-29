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


class ACStarkCalibration(ExperimentClass):
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

        avgi = np.array(avgi_list)
        avgq = np.array(avgq_list)

        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        self.data = data
        return data

    def display(self, data=None, plotDisp=False, figNum=1, **kwargs):
        if data is None:
            data = self.data

        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']

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

        def _decayingCos(t, A, T2, freq, phase, offset):
            return A * np.exp(-t / T2) * np.cos(2 * np.pi * freq * t + phase) + offset

        dt = x_pts[1] - x_pts[0]
        yf = np.fft.rfft(avgi - np.mean(avgi))
        xf = np.fft.rfftfreq(len(x_pts), dt)
        freq0 = xf[np.argmax(np.abs(yf[1:])) + 1]
        A0 = (np.max(avgi) - np.min(avgi)) / 2
        T2_0 = (x_pts[-1] - x_pts[0]) / 2
        offset0 = np.mean(avgi)
        guess = [A0, T2_0, freq0, 0, offset0]

        try:
            pOpt, pCov = curve_fit(_decayingCos, x_pts, avgi, p0=guess, maxfev=10000,
                                   bounds=([-np.inf, 0, 0, -np.pi, -np.inf],
                                           [np.inf, np.inf, np.inf, np.pi, np.inf]))
            perr = np.sqrt(np.diag(pCov))
            T2_est = np.abs(pOpt[1])
            T2_err = perr[1]
            fit_success = True
        except Exception:
            fit_success = False

        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig = plt.figure(figNum)
        plt.plot(x_pts, avgi, 'o', label="i", color='orange')
        if fit_success:
            x_fit = np.linspace(x_pts[0], x_pts[-1], 1000)
            plt.plot(x_fit, _decayingCos(x_fit, *pOpt), '-', label="fit", color='black')
            title_str = self.titlename + "  ; T2R = " + str(round(T2_est, 1)) + r" $\pm$ " + str(round(T2_err, 1)) + " us"
            print(f"T2R: {T2_est:.4f} ± {T2_err:.4f} us,  freq: {pOpt[2]*1e3:.4f} kHz")
        else:
            title_str = self.titlename + "  ; T2R fit failed"
            print("T2R fit failed")
        plt.ylabel("a.u.")
        if "min_max" in data:
            plt.ylabel("Population")
        plt.xlabel("Wait time (us)")
        plt.legend()
        plt.title(title_str)
        plt.savefig(self.iname[:-4] + 'I_Data.png')

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

        fig = plt.figure(figNum + 1)
        plt.plot(x_pts, avgq, 'o', label="q")
        plt.ylabel("a.u.")
        plt.xlabel("Wait time (us)")
        plt.legend()
        plt.title(self.titlename)
        plt.savefig(self.iname[:-4] + 'Q_Data.png')

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

        # return fit param
        return pOpt

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])
