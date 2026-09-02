import datetime
import time

import numpy as np
import matplotlib.pyplot as plt

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import fit_functions as ff
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.progress import progress_counter
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.acquisition import (
    apply_device_interleave)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.glitch import remeasure_glitched_rows
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mQubitSpecVsFlux import QubitSpecProgram


def _freq_axis(cfg):
    cfg["start"] = cfg["qubit_freq_start"]
    cfg["expts"] = int(cfg["qubit_freq_expts"])
    cfg["step"] = (cfg["qubit_freq_stop"] - cfg["qubit_freq_start"]) / max(cfg["expts"] - 1, 1)
    return np.linspace(cfg["qubit_freq_start"], cfg["qubit_freq_stop"], cfg["expts"])


def _feature_freq(fpts, mag):
    sp, _ = ff.fit_spec_dip(fpts, mag, kind='auto')
    if sp is not None:
        return float(sp['f0'])
    return float(fpts[int(np.argmax(np.abs(mag - np.median(mag))))])


class QubitSpec(ExperimentClass):

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data',
                 suffix='Qubit_Spec', cfg=None, meta_dict=None, live_plot=False, save=True, **kw):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, suffix=suffix, cfg=cfg, meta_dict=meta_dict, **kw)
        self.element = str(path)
        self.live_plot = bool(live_plot)
        self.save = bool(save)

    def acquire(self, progress=False, plotDisp=False):
        cfg = self.cfg
        fpts = _freq_axis(cfg)
        reps, rounds, total = apply_device_interleave(cfg)
        if rounds > 1:
            print(f"[Qubit Spec] {cfg['expts']} freqs interleaved on the tProc: "
                  f"{rounds} rounds x {reps} shots = {total} shots/point, one upload")
        _x, avgi, avgq = QubitSpecProgram(self.soccfg, cfg).acquire(
            self.soc, load_pulses=True, progress=progress)
        sig = np.array(avgi[0][0]) + 1j * np.array(avgq[0][0])
        mag = np.abs(sig)
        phase = np.unwrap(np.angle(sig))
        f0 = _feature_freq(fpts, mag)
        self.data = {
            'config': dict(cfg), 'element': self.element,
            'fpts': fpts, 'magnitude': mag, 'phase': phase, 'qubit_freq_mhz': f0,
            'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        print(f"[Qubit Spec] qubit feature at {f0:.3f} MHz ({f0 / 1e3:.5f} GHz), "
              f"spec gain {cfg['qubit_gain']} DAC")
        if self.save:
            self._plot(fpts, mag, phase, f0, plotDisp=plotDisp)
            self.pickle_data()
        return {'config': cfg, 'data': self.data}

    def _plot(self, fpts, mag, phase, f0, plotDisp=False):
        fig, ax = plt.subplots(2, 1, sharex=True, figsize=(8, 6))
        ax[0].plot(fpts / 1e3, mag, '.-', ms=3)
        ax[0].axvline(f0 / 1e3, color='r', lw=1)
        ax[0].set_ylabel("|IQ| (a.u.)")
        ax[0].set_title(f"{self.element} two-tone spectroscopy  "
                        f"(f = {f0 / 1e3:.5f} GHz, gain {self.cfg['qubit_gain']} DAC)")
        ax[1].plot(fpts / 1e3, phase, '.-', ms=3)
        ax[1].axvline(f0 / 1e3, color='r', lw=1)
        ax[1].set_xlabel("Qubit drive frequency (GHz)"); ax[1].set_ylabel("phase (rad)")
        plt.tight_layout()
        plt.savefig(self.iname, bbox_inches="tight")
        if plotDisp:
            plt.show(block=False); plt.pause(0.1)
        else:
            plt.close(fig)

    def save_data(self, data=None):
        if data is None:
            data = self.data
        print(f'Saving {self.fname}')
        super().save_data(data={'fpts': self.data['fpts'], 'magnitude': self.data['magnitude'],
                                'phase': self.data['phase']})


class QubitSpecGainSweep(ExperimentClass):

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data',
                 suffix='Qubit_Spec_Gain_Sweep', cfg=None, meta_dict=None, gains=None,
                 live_plot=False, save=True, **kw):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, suffix=suffix, cfg=cfg, meta_dict=meta_dict, **kw)
        self.element = str(path)
        self.gains = np.asarray(gains)
        self.live_plot = bool(live_plot)
        self.save = bool(save)

    def acquire(self, progress=False, plotDisp=False):
        cfg = self.cfg
        fpts = _freq_axis(cfg)
        gains = self.gains
        n_g, n_f = len(gains), len(fpts)
        mag = np.full((n_g, n_f), np.nan)
        phase = np.full((n_g, n_f), np.nan)
        qubit_dip = np.full(n_g, np.nan)

        def measure_row(i):
            cfg["qubit_gain"] = int(gains[int(i)])
            _x, avgi, avgq = QubitSpecProgram(self.soccfg, cfg).acquire(
                self.soc, load_pulses=True, progress=False)
            sig = np.array(avgi[0][0]) + 1j * np.array(avgq[0][0])
            mag[int(i), :] = np.abs(sig)
            phase[int(i), :] = np.unwrap(np.angle(sig))
            qubit_dip[int(i)] = _feature_freq(fpts, np.abs(sig))

        print(f"[Qubit Spec gain sweep] {n_g} spec gains x {n_f} freqs, "
              f"{cfg['shots']} shots/pt ({n_g * n_f} points)")
        start = time.time()
        for i in range(n_g):
            measure_row(i)
            if progress:
                progress_counter(i, n_g, start_time=start, label="qubit spec gain sweep")

        if bool(cfg.get("remeasure_outliers", True)):
            remeasure_glitched_rows(
                lambda: np.median(mag, axis=1), measure_row,
                sigma=float(cfg.get("outlier_sigma", 6.0)),
                passes=int(cfg.get("outlier_passes", 2)), label="Qubit Spec gain sweep",
                row_labels=[f"{int(g)} DAC" for g in gains])

        self.data = {
            'config': dict(cfg), 'element': self.element,
            'fpts': fpts, 'gain_vec': gains, 'magnitude': mag, 'phase': phase,
            'qubit_dip_mhz': qubit_dip,
            'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        if self.save:
            self._plot(fpts, gains, mag, phase, qubit_dip, plotDisp=plotDisp)
            self.pickle_data()
        return {'config': cfg, 'data': self.data}

    def _plot(self, fpts, gains, mag, phase, qubit_dip, plotDisp=False):
        fig, ax = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True)
        for a, M, lbl in ((ax[0], mag, "|IQ| (a.u.)"), (ax[1], phase, "phase (rad)")):
            pc = a.pcolormesh(fpts / 1e3, gains, M, shading="nearest")
            a.plot(qubit_dip / 1e3, gains, 'rx', ms=5)
            a.set_xlabel("Qubit drive frequency (GHz)")
            fig.colorbar(pc, ax=a, label=lbl)
        ax[0].set_ylabel("Spec drive gain [DAC]")
        fig.suptitle(f"{self.element} two-tone spectroscopy vs drive power")
        plt.tight_layout()
        plt.savefig(self.iname, bbox_inches="tight")
        if plotDisp:
            plt.show(block=False); plt.pause(0.1)
        else:
            plt.close(fig)

    def save_data(self, data=None):
        if data is None:
            data = self.data
        print(f'Saving {self.fname}')
        super().save_data(data={'fpts': self.data['fpts'], 'gain_vec': self.data['gain_vec'],
                                'magnitude': self.data['magnitude'], 'phase': self.data['phase']})
