"""
STEP 4 of the TLS pipeline: long-time qubit spectroscopy vs (fast-flux) target.

QUA analog: LabCode/Experiments/Flux_Predistortion/m_qubit_long_time_frequency_vs_flux.py
QICK model: escher FF_fromParth/mFFSpecVsDelay_wPulsePreDist (spec vs delay at a
            ramped flux point), looped over many flux targets.

For each fast-flux target we ramp there (predistorted), then probe the qubit
frequency at several LONG delays in a window around ``long_time_ns`` and check the
frequency is FLAT vs delay = the flux has settled (predistortion worked).  The
extracted long-time frequency f_q(ff_gain) is ALSO the fast-flux -> qubit-frequency
map that step 6 (T1 vs flux) uses to plot T1 vs qubit frequency and read off TLS
frequencies directly.

Flux-axis note (QUA -> QICK): QUA swept the flux target as an OPX DC voltage
(dc_vec, V).  QICK reaches a dynamic operating point with a fast-flux DAC pulse, so
the swept axis here is ``ff_gain`` (DAC units) -- the fast-flux excursion above the
Yokogawa DC baseline.  Use build_inclusive_sweep / a custom ff_gain vector.
"""

import time

import numpy as np
import matplotlib.pyplot as plt

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import fit_functions as ff
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_predistortion as fpd
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mQubitFluxStepResponse import (
    FFStepResponseSpecProgram,
)


class QubitLongTimeSpecVsFlux(ExperimentClass):
    """Long-time qubit spec vs fast-flux target (settling verification + f_q map).

    cfg keys: qubit_freq_start/stop/expts (MHz), ff_gain_vec (DAC units, the flux axis),
      long_time_us, average_window_us, average_step_us, plus the FF keys
      (ff_ramp_length, dt_pulseplay, dt_pulsedef) and flux_tail_compensation.

    reuse of classmethods (parity with the QUA API):
    """

    # --- predistortion-JSON helpers (mirror the QUA classmethods used by the runner) ---
    @staticmethod
    def find_latest_dc_compensation_json(outer_folder, qubit, baseline_dc_offset=None,
                                         dc_offset=None):
        return fpd.find_latest_compensation_json(outer_folder, qubit,
                                                 baseline_dc_offset=baseline_dc_offset,
                                                 dc_offset=dc_offset)

    @staticmethod
    def load_dc_compensation_json(json_path):
        return fpd.load_compensation_json(json_path)

    @staticmethod
    def build_inclusive_sweep(vmin, vmax, step):
        return fpd.build_inclusive_sweep(vmin, vmax, step)

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data',
                 suffix='Qubit_Long_Time_Frequency_vs_Flux', cfg=None, meta_dict=None,
                 flux_tail_compensation=None, **kw):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, suffix=suffix, cfg=cfg, meta_dict=meta_dict, **kw)
        if flux_tail_compensation is not None:
            cfg["flux_tail_compensation"] = flux_tail_compensation

    def _probe_window_us(self):
        cfg = self.cfg
        center = cfg.get("long_time_us", 5.0)
        width = cfg.get("average_window_us", 0.0)
        step = max(cfg.get("average_step_us", 0.016), 0.004)
        if width <= 0:
            return np.array([center])
        n = int(width / step) + 1
        return np.unique(np.round(np.linspace(center - width / 2, center + width / 2, n), 6))

    def _ff_gain_vec(self):
        cfg = self.cfg
        if "ff_gain_vec" in cfg:
            return np.asarray(cfg["ff_gain_vec"], dtype=float)
        return np.linspace(cfg["ff_gain_start"], cfg["ff_gain_stop"], int(cfg["ff_gain_num"]))

    def acquire(self, progress=False, plotDisp=False, figNum=1):
        cfg = self.cfg
        cfg["start"] = cfg["qubit_freq_start"]
        cfg["expts"] = int(cfg["qubit_freq_expts"])
        cfg["step"] = (cfg["qubit_freq_stop"] - cfg["qubit_freq_start"]) / (cfg["expts"] - 1)
        fpts = np.linspace(cfg["qubit_freq_start"], cfg["qubit_freq_stop"], cfg["expts"])
        ff_gains = self._ff_gain_vec()
        t_probe = self._probe_window_us()

        long_time_freq = np.full(len(ff_gains), np.nan)   # f_q(ff_gain) [GHz]
        long_time_std = np.full(len(ff_gains), np.nan)     # flatness vs delay [MHz]
        fq_cube = np.full((len(ff_gains), len(t_probe)), np.nan)

        start = time.time()
        for i, g in enumerate(ff_gains):
            cfg["ff_gain"] = float(g)
            for k, t in enumerate(t_probe):
                cfg["ff_hold"] = float(t)
                prog = FFStepResponseSpecProgram(self.soccfg, cfg)
                _x, avgi, avgq = prog.acquire(self.soc, load_pulses=True, progress=False)
                mag = np.abs(np.array(avgi[0][0]) + 1j * np.array(avgq[0][0]))
                sp, _ = ff.fit_spec_dip(fpts, mag, kind='auto')
                if sp is not None:
                    fq_cube[i, k] = sp['f0'] / 1e3
            row = fq_cube[i, :]
            good = row[np.isfinite(row)]
            if good.size:
                long_time_freq[i] = float(np.median(good))
                long_time_std[i] = float(np.std(good) * 1e3)  # MHz
            if i == 0:
                per = (time.time() - start)
                print(f"[4] ~{per*len(ff_gains)/60:.1f} min for {len(ff_gains)} flux x "
                      f"{len(t_probe)} probe-delays x {cfg['expts']} freqs")

        data = {'config': cfg, 'data': {
            'ff_gains': ff_gains, 't_probe_us': t_probe, 'fpts_MHz': fpts,
            'fq_cube_ghz': fq_cube, 'long_time_freq_ghz': long_time_freq,
            'long_time_std_MHz': long_time_std}}
        self.data = data

        raw_csv = self.iname[:-4] + "_raw_sweep.csv"
        rows = []
        for i, g in enumerate(ff_gains):
            for k, t in enumerate(t_probe):
                rows.append([g, t, fq_cube[i, k]])
        np.savetxt(raw_csv, np.array(rows), delimiter=",",
                   header="ff_gain,probe_time_us,fq_ghz", comments="")
        data['data']['raw_sweep_csv'] = raw_csv
        print(f"[4] raw sweep CSV: {raw_csv}")
        print(f"[4] median settling flatness over flux points: "
              f"{np.nanmedian(long_time_std):.3f} MHz")

        self.display(data, plotDisp=plotDisp, figNum=figNum)
        return data

    def display(self, data=None, plotDisp=False, figNum=1, **kw):
        if data is None:
            data = self.data
        d = data['data']
        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig, axs = plt.subplots(1, 2, figsize=(12, 5), num=figNum)
        axs[0].plot(d['ff_gains'], d['long_time_freq_ghz'], 'k.-')
        axs[0].set_xlabel("Fast-flux gain (DAC units)")
        axs[0].set_ylabel("Long-time qubit freq (GHz)")
        axs[0].set_title("f_q vs fast-flux target (settled)")
        axs[1].plot(d['ff_gains'], d['long_time_std_MHz'], 'r.-')
        axs[1].set_xlabel("Fast-flux gain (DAC units)")
        axs[1].set_ylabel("freq flatness over probe window (MHz)")
        axs[1].set_title("Settling residual (lower = better predistortion)")
        plt.tight_layout()
        plt.savefig(self.iname)
        if plotDisp:
            plt.show(block=False); plt.pause(0.1)
        else:
            fig.clf(); plt.close(fig)

    def save_data(self, data=None):
        if data is None:
            data = self.data
        print(f'Saving {self.fname}')
        arr = {k: v for k, v in data['data'].items() if not isinstance(v, str)}
        super().save_data(data=arr)
