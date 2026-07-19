"""
Rabi linecut, single-shot readout -- QICK port of Houck-Lab-Qua
LabCode/Experiments/Rabi/m_Rabi_Linecut_SS.py::RabiLinecutSS.

The final, precise pi-amplitude calibration.  QUA parity (reset substituted, see below):
  * 1D amplitude (gain) sweep at the FIXED drive frequency (cfg['qubit_pi_freq']),
    centered on the current pi gain +/- a_span/2; each point plays num_pi X180 (or
    2*num_pi X90) pulses, single-shot readout -> excited population vs gain.
  * analyze(): the VERBATIM QUA cosine^2 fit  A*cos((pi/T)*x)^2 + B  (curve_fit,
    p0=[gain_span, 1, 0]); the calibrated pi gain is argmax of the fitted curve over the
    sweep -- exactly the QUA "Max Amp".

RESET SUBSTITUTION: the QUA active feedback reset (measure -> conditional X180 -> loop)
is not possible on tProc v1; a passive relax_delay is used instead (shared RabiSSProgram
in mRabiChevronSS), identical to the TLS T1.  Only the reset physics differs.

Error amplification: pass a scalar num_pi_pulses (>1 amplifies a small per-pulse gain
error into a sharper cosine near the pi point).  The runner may loop over a list of
num_pi values (QUA behavior) and stack the resulting curves.
"""

import datetime

import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mRabiChevronIQ import n_drive_pulses
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mRabiChevronSS import sweep_gain_populations


def cosine_sq(x, T, A, B):
    """VERBATIM QUA fit function (m_Rabi_Linecut_SS.analyze)."""
    return A * np.cos((np.pi / T) * x) ** 2 + B


class RabiLinecutSS(ExperimentClass):
    """1D gain-sweep single-shot Rabi at fixed drive frequency + cosine^2 fit -> pi gain.
    cfg knobs: a_span (DAC, full span centered on the current pi gain), a_points, num_pi,
    pulse_type, shots.  Center gain = qubit_pi_gain (X180) or qubit_pi2_gain (X90).
    Requires calib_params from the step-5 single-shot calibration."""

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data',
                 suffix='Rabi_Linecut_SS', cfg=None, meta_dict=None, calib_params=None,
                 num_pi_pulses=1, pulse_type="X180", live_plot=False, save=True, **kw):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, suffix=suffix, cfg=cfg, meta_dict=meta_dict, **kw)
        if calib_params is None:
            raise ValueError("RabiLinecutSS needs calib_params from the single-shot calibration (step 5).")
        self.calib_params = calib_params
        self.element = str(path)
        self.num_pi = int(cfg.get("num_pi", num_pi_pulses))
        self.pulse_type = str(cfg.get("pulse_type", pulse_type)).upper()
        self.live_plot = bool(live_plot)
        self.save = bool(save)

    def acquire(self, progress=False, plotDisp=False):
        cfg = self.cfg
        cfg["num_pi"] = self.num_pi
        cfg["pulse_type"] = self.pulse_type
        cfg["n_pulses"] = n_drive_pulses(self.pulse_type, self.num_pi)
        cfg["shots"] = int(cfg.get("shots", cfg.get("reps", 1000)))

        # sweep centered on the current pi gain (QUA: amp +/- a_span/2 around pi_amp/pi2_amp)
        center = float(cfg["qubit_pi2_gain"] if self.pulse_type == "X90" else cfg["qubit_pi_gain"])
        a_span = float(cfg["a_span"])
        a_points = int(cfg["a_points"])
        cfg["amp_start"] = int(round(center - a_span / 2.0))
        cfg["amp_expts"] = a_points
        cfg["amp_step"] = int(round(a_span / max(a_points - 1, 1)))
        gains = cfg["amp_start"] + cfg["amp_step"] * np.arange(a_points)   # actual HW sweep
        cfg["amp_stop"] = int(gains[-1])
        pi_freq = float(cfg.get("qubit_pi_freq", cfg["qubit_freq"]))
        cfg["rabi_drive_freq"] = pi_freq

        print(f"[Rabi Linecut SS] {self.pulse_type} x{self.num_pi} pulses (error-amplified): "
              f"{a_points} gains around {center:.0f} DAC (+/-{a_span/2:.0f}), {cfg['shots']} shots/pt, "
              f"drive {pi_freq:.3f} MHz, passive relax {cfg['relax_delay']} us")
        pop = sweep_gain_populations(self, cfg, gains, self.calib_params)

        fit, pi_gain = None, None
        try:
            popt, pcov = curve_fit(cosine_sq, gains, pop,
                                   p0=[(gains[-1] - gains[0]), 1.0, 0.0], maxfev=20000)
            x_fit = np.linspace(gains[0], gains[-1], 400)
            y_fit = cosine_sq(x_fit, *popt)
            pi_gain = float(x_fit[np.argmax(y_fit)])
            fit = (popt, pcov)
            print(f"[Rabi Linecut SS] pi gain (cosine^2 argmax) = {pi_gain:.1f} DAC")
        except Exception:
            print("[Rabi Linecut SS] cosine^2 fit failed; falling back to raw argmax")
            pi_gain = float(gains[int(np.nanargmax(pop))])

        self.data = {
            'config': dict(cfg), 'element': self.element, 'pulse_type': self.pulse_type,
            'number_pulses': self.num_pi, 'shots': cfg["shots"],
            'gain_vec': gains, 'ss_data': pop, 'fit': fit, 'fit_func': 'cosine_sq',
            'pi_gain': pi_gain, 'center_gain': center,
            'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        if self.save:
            self._plot(gains, pop, fit, pi_gain, plotDisp=plotDisp)
            self.pickle_data()
        return {'config': cfg, 'data': self.data}

    def _plot(self, gains, pop, fit, pi_gain, plotDisp=False):
        fig = plt.figure(figsize=(6.5, 4.5))
        plt.plot(gains, pop, "o", label="data")
        if fit is not None:
            x_fit = np.linspace(gains[0], gains[-1], 400)
            plt.plot(x_fit, cosine_sq(x_fit, *fit[0]), "-", label="cosine$^2$ fit")
        if pi_gain is not None:
            plt.axvline(pi_gain, color="k", ls="--", label=f"pi gain = {pi_gain:.0f}")
        plt.ylim(top=1.02)
        plt.xlabel("Qubit pulse gain [DAC]"); plt.ylabel("Excited population")
        plt.minorticks_on(); plt.grid(which='minor', axis='both', linestyle='--', alpha=0.5)
        plt.legend()
        plt.suptitle(f"SS Rabi linecut {self.element} {self.pulse_type}, {self.num_pi} pulses, "
                     f"drive {self.data['config']['rabi_drive_freq']:.3f} MHz")
        plt.tight_layout()
        plt.savefig(self.iname, bbox_inches="tight")
        if plotDisp:
            plt.show(block=False); plt.pause(0.1)
        else:
            plt.close(fig)

    def save_data(self, data=None):
        if data is None:
            data = {'data': self.data}
        print(f'Saving {self.fname}')
        super().save_data(data={'ss_data': self.data['ss_data'], 'gain_vec': self.data['gain_vec']})
