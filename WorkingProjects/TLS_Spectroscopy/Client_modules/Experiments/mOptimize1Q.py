import datetime
import time

import numpy as np
import matplotlib.pyplot as plt

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import SingleShot1Q
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.acquisition import suppress_stdout
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.progress import progress_counter


PULSE_TYPES = ("X180", "X90")


def normalize_pulse_type(pulse_type):
    value = str(pulse_type).upper()
    if value not in PULSE_TYPES:
        raise ValueError(f"pulse_type must be one of {PULSE_TYPES}, got {pulse_type!r}")
    return value


def optimizer_drive_pulses(pulse_type, num_pi_pulses):
    pulse_type = normalize_pulse_type(pulse_type)
    num_pi_pulses = int(num_pi_pulses)
    if num_pi_pulses < 1 or num_pi_pulses % 2 == 0:
        raise ValueError("num_pi_pulses must be a positive odd integer")
    return num_pi_pulses * (2 if pulse_type == "X90" else 1)


class _GridOptimizer(ExperimentClass):

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data',
                 suffix='data', cfg=None, meta_dict=None, freqs_mhz=None, gains=None,
                 shots=500, num_pi_pulses=1, num_pi=None, pulse_type="X180",
                 live_plot=False, save=True, **kw):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, suffix=suffix, cfg=cfg, meta_dict=meta_dict, **kw)
        self.element = str(path)
        self.freqs_mhz = np.asarray(freqs_mhz, dtype=float)
        self.gains = np.asarray(gains, dtype=int)
        self.shots = int(shots)
        self.pulse_type = normalize_pulse_type(
            self.cfg.get("pulse_type", pulse_type))
        requested_num_pi = num_pi_pulses if num_pi is None else num_pi
        self.num_pi_pulses = int(self.cfg.get(
            "num_pi", self.cfg.get("num_pi_pulses", requested_num_pi)))
        self.drive_pulses = optimizer_drive_pulses(
            self.pulse_type, self.num_pi_pulses)
        self.cfg["pulse_type"] = self.pulse_type
        self.cfg["num_pi"] = self.num_pi_pulses
        self.cfg["n_pulses"] = self.drive_pulses
        self.live_plot = bool(live_plot)
        self.save = bool(save)

    def _point_cfg(self, freq, gain):
        raise NotImplementedError

    def _fidelity_at(self, freq, gain):
        cfg = self._point_cfg(freq, gain)
        cfg["shots"] = cfg["reps"] = self.shots
        with suppress_stdout():
            ss = SingleShot1Q(soc=self.soc, soccfg=self.soccfg, path=self.element,
                              outerFolder=self.outerFolder, suffix="opt_pt", cfg=cfg,
                              plot=False, save=False, repeats=self.drive_pulses, min_F=0.0)
            ss.acquire(progress=False, plotDisp=False)
        return float(ss.max_F)

    def _sweep(self, progress=False):
        ng, nf = len(self.gains), len(self.freqs_mhz)
        fid = np.full((ng, nf), np.nan)
        total = ng * nf
        start = time.time()
        done = 0
        for ig, g in enumerate(self.gains):
            for jf, f in enumerate(self.freqs_mhz):
                fid[ig, jf] = self._fidelity_at(float(f), int(g))
                done += 1
                if progress:
                    progress_counter(done - 1, total, start_time=start, label=self.suffix)
        return fid

    def _best(self, fid):
        ig, jf = np.unravel_index(np.nanargmax(fid), fid.shape)
        return int(self.gains[ig]), float(self.freqs_mhz[jf]), float(fid[ig, jf])

    def _draw(self, fid, xlabel, ylabel, title, best_freq, best_gain, plotDisp):
        fig, ax = plt.subplots(figsize=(8, 5), constrained_layout=True)
        pcm = ax.pcolormesh(self.freqs_mhz, self.gains, fid * 100.0, shading="nearest")
        fig.colorbar(pcm, ax=ax, label="single-shot fidelity [%]")
        ax.plot([best_freq], [best_gain], "wx", ms=10, mew=2)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        fig.savefig(self.iname, bbox_inches="tight")
        if plotDisp:
            plt.show(block=False)
            plt.pause(0.1)
        else:
            plt.close(fig)


class ReadoutOptimize(_GridOptimizer):

    def _point_cfg(self, freq, gain):
        cfg = dict(self.cfg)
        cfg["read_pulse_freq"] = float(freq)
        cfg["read_pulse_gain"] = int(gain)
        gain_key = "qubit_pi2_gain" if self.pulse_type == "X90" else "qubit_pi_gain"
        if gain_key not in cfg:
            raise ValueError(f"{self.pulse_type} readout optimization requires {gain_key}")
        cfg["qubit_gain"] = int(cfg[gain_key])
        cfg["pulse_type"] = self.pulse_type
        return cfg

    def acquire(self, progress=False, plotDisp=False):
        print(f"[readout opt] {len(self.freqs_mhz)} readout freqs x {len(self.gains)} gains, "
              f"{self.shots} shots/pt, {self.drive_pulses}x {self.pulse_type} drive pulses")
        fid = self._sweep(progress=progress)
        best_gain, best_freq, best_F = self._best(fid)
        self.data = {
            'config': dict(self.cfg), 'element': self.element,
            'pulse_type': self.pulse_type,
            'number_pi_pulses': self.num_pi_pulses,
            'number_drive_pulses': self.drive_pulses,
            'read_freqs_mhz': self.freqs_mhz, 'read_gains': self.gains, 'fidelity': fid,
            'best_read_pulse_freq': best_freq, 'best_read_pulse_gain': best_gain,
            'best_fidelity': best_F,
            'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        print(f"[readout opt] best F={best_F:.4f} at read_pulse_freq={best_freq:.3f} MHz, "
              f"read_pulse_gain={best_gain}")
        if self.save:
            self._draw(fid, "Readout freq [MHz]", "Readout gain [DAC]",
                       f"{self.element} readout optimization with {self.drive_pulses}x "
                       f"{self.pulse_type}", best_freq, best_gain, plotDisp)
            self.pickle_data()
        return {'config': self.cfg, 'data': self.data}

    def save_data(self, data=None):
        super().save_data(data={'read_freqs_mhz': self.data['read_freqs_mhz'],
                                'read_gains': self.data['read_gains'],
                                'fidelity': self.data['fidelity']})


class QubitPulseOptimize(_GridOptimizer):

    def _point_cfg(self, freq, gain):
        cfg = dict(self.cfg)
        cfg["qubit_pi_freq"] = float(freq)
        cfg["qubit_gain"] = int(gain)
        cfg["pulse_type"] = self.pulse_type
        return cfg

    def acquire(self, progress=False, plotDisp=False):
        print(f"[qubit opt] {len(self.freqs_mhz)} qubit freqs x {len(self.gains)} gains, "
              f"{self.shots} shots/pt, {self.drive_pulses}x {self.pulse_type} drive pulses")
        fid = self._sweep(progress=progress)
        best_gain, best_freq, best_F = self._best(fid)
        self.data = {
            'config': dict(self.cfg), 'element': self.element,
            'pulse_type': self.pulse_type,
            'number_pi_pulses': self.num_pi_pulses,
            'number_drive_pulses': self.drive_pulses,
            'qubit_freqs_mhz': self.freqs_mhz, 'qubit_gains': self.gains, 'fidelity': fid,
            'best_gain': best_gain, 'best_drive_freq_mhz': best_freq,
            'best_qubit_pi_freq': best_freq, 'best_fidelity': best_F,
            'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        if self.pulse_type == "X90":
            self.data['best_qubit_pi2_gain'] = best_gain
            result = f"qubit_pi2_gain={best_gain}"
        else:
            self.data['best_qubit_pi_gain'] = best_gain
            self.data['qubit_pi2_gain_seed'] = int(round(best_gain / 2))
            result = (f"qubit_pi_gain={best_gain} "
                      f"(uncalibrated pi/2 seed {self.data['qubit_pi2_gain_seed']})")
        print(f"[qubit opt] best F={best_F:.4f} at qubit_pi_freq={best_freq:.3f} MHz, "
              f"{result}")
        if self.save:
            self._draw(fid, "Qubit drive freq [MHz]", "Qubit drive gain [DAC]",
                       f"{self.element} {self.pulse_type} pulse optimization "
                       f"({self.drive_pulses} drive pulses)", best_freq, best_gain, plotDisp)
            self.pickle_data()
        return {'config': self.cfg, 'data': self.data}

    def save_data(self, data=None):
        super().save_data(data={'qubit_freqs_mhz': self.data['qubit_freqs_mhz'],
                                'qubit_gains': self.data['qubit_gains'],
                                'fidelity': self.data['fidelity']})
