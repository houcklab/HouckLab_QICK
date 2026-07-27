import datetime
import time

import numpy as np
import matplotlib.pyplot as plt

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.progress import progress_counter
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.acquisition import (
    order_rng, resolve_rounds, split_reps, suppress_stdout, visit_order)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import discriminate_shots
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mT1VsFlux import FFT1Program
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset


def _fit_exp_decay(t_us, pe):
    from scipy.optimize import curve_fit
    t = np.asarray(t_us, dtype=float)
    y = np.asarray(pe, dtype=float)
    finite = np.isfinite(t) & np.isfinite(y)
    if finite.sum() < 4:
        return None
    t, y = t[finite], y[finite]
    p0 = float(np.min(y))
    p1 = float(np.max(y))
    if p1 - p0 < 1e-6:
        return None
    mid = p0 + (p1 - p0) / np.e
    t1_seed = max(0.1, float(t[np.argmin(np.abs(y - mid))]) / np.log(2))
    try:
        popt, pcov = curve_fit(lambda tt, a, b, tau: a + (b - a) * np.exp(-tt / tau),
                               t, y, p0=[p0, p1, t1_seed],
                               bounds=([0.0, 0.0, 0.01], [1.0, 1.0, 1e6]), maxfev=20000)
        err = float(np.sqrt(pcov[2, 2])) if np.isfinite(pcov[2, 2]) else np.nan
        return {"P0": float(popt[0]), "P1": float(popt[1]), "tau_us": float(popt[2]),
                "tau_err_us": err}
    except Exception:
        return None


class _CoherenceBase(ExperimentClass):

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data',
                 suffix='data', cfg=None, meta_dict=None, calib_params=None,
                 t_vec_us=None, reset_mode="passive", live_plot=False, save=True, **kw):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, suffix=suffix, cfg=cfg, meta_dict=meta_dict, **kw)
        if calib_params is None:
            calib_params = cfg.get("calib_params") if cfg else None
        if calib_params is None:
            raise ValueError("calib_params is required (run SingleShot1Q first).")
        self.element = str(path)
        self.calib_params = calib_params
        self.t_vec_us = np.asarray(t_vec_us, dtype=float)
        self.reset_mode = reset_mode
        cfg["reset_mode"] = reset_mode
        self.live_plot = bool(live_plot)
        self.save = bool(save)

    def _run_point_counts(self, wait_us, reps=None):
        raise NotImplementedError

    def _sweep(self, progress=True):
        cfg = self.cfg
        shots = int(cfg["shots"])
        rounds = resolve_rounds(cfg, shots, default=cfg.get("coherence_rounds"))
        n = len(self.t_vec_us)
        exc = np.zeros(n)
        kept = np.zeros(n)
        reps_per_round = split_reps(shots, rounds)
        saved = cfg["shots"]
        total = sum(1 for r in reps_per_round if r > 0) * n
        start = time.time()
        done = 0
        attempted = np.zeros(n)
        rng = order_rng(cfg)
        orders = []
        for reps in reps_per_round:
            if reps <= 0:
                continue
            order = visit_order(n, cfg, rng)
            orders.append(order.tolist())
            for idx in order:
                e, k = self._run_point_counts(float(self.t_vec_us[idx]), reps=reps)
                exc[idx] += e
                kept[idx] += k
                attempted[idx] += reps
                done += 1
                if progress:
                    progress_counter(done - 1, total, start_time=start, label=self.suffix)
        cfg["shots"] = saved
        self.point_visit_orders = orders
        with np.errstate(invalid="ignore", divide="ignore"):
            self.keep_fraction = np.where(attempted > 0, kept / attempted, np.nan)
            return np.where(kept > 0, exc / kept, np.nan)

    def _plot_decay(self, pe, fit, ylabel, title, plotDisp=False):
        fig, ax = plt.subplots(figsize=(8, 5), constrained_layout=True)
        ax.plot(self.t_vec_us, pe, "o", ms=4)
        if fit is not None:
            tt = np.logspace(np.log10(self.t_vec_us.min()), np.log10(self.t_vec_us.max()), 400)
            err = fit.get("tau_err_us", np.nan)
            metric = getattr(self, "_metric_name", "tau")
            label = (f"{metric} = {fit['tau_us']:.2f} +/- {err:.2f} us"
                     if np.isfinite(err) else f"{metric} = {fit['tau_us']:.2f} us")
            ax.plot(tt, fit["P0"] + (fit["P1"] - fit["P0"]) * np.exp(-tt / fit["tau_us"]),
                    "-r", lw=1.5, label=label)
            ax.legend()
        ax.set_xscale("log")
        ax.set_xlabel("Delay time [us]")
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        fig.savefig(self.iname, bbox_inches="tight")
        if plotDisp:
            plt.show(block=False)
            plt.pause(0.1)
        else:
            plt.close(fig)


class T1(_CoherenceBase):

    _metric_name = "T1"

    def __init__(self, *args, ff_gain=0.0, **kw):
        super().__init__(*args, **kw)
        self.ff_gain = float(ff_gain)

    def _run_point_counts(self, wait_us, reps=None):
        cfg = self.cfg
        cfg["ff_gain"] = self.ff_gain
        cfg["ff_hold"] = float(wait_us)
        cfg["do_pi"] = True
        cfg["do_ff"] = True
        if reps is not None:
            cfg["shots"] = int(reps)
        with suppress_stdout():
            prog = FFT1Program(self.soccfg, cfg)
            i0, q0, i1, q1 = prog.acquire(self.soc, load_pulses=True)
        final = np.asarray(discriminate_shots(i1, q1, self.calib_params))
        if active_reset.heralds(self.reset_mode):
            keep = active_reset.herald_keep(i0, q0, self.calib_params)
            return float(np.sum(final[keep])), int(np.sum(keep))
        return float(np.sum(final)), int(final.size)

    def acquire(self, progress=False, plotDisp=False):
        held = abs(self.ff_gain) > 0
        print(f"[T1{' flux ramp' if held else ''}] {len(self.t_vec_us)} waits "
              f"{self.t_vec_us[0]:.2f}..{self.t_vec_us[-1]:.1f} us, {self.cfg['shots']} shots/pt"
              + (f", flux excursion ff_gain={self.ff_gain:.0f} DAC" if held else " at park"))
        if self.cfg.get("randomize_point_order", False):
            print(f"[T1] delay order randomized per round "
                  f"(seed={self.cfg.get('point_order_seed', None)})")
        pe = self._sweep(progress=progress)
        fit = _fit_exp_decay(self.t_vec_us, pe)
        keep = getattr(self, "keep_fraction", None)
        if active_reset.heralds(self.reset_mode) and keep is not None:
            print(f"[T1] herald kept {100 * np.nanmean(keep):.1f}% of shots "
                  f"(min {100 * np.nanmin(keep):.1f}%, max {100 * np.nanmax(keep):.1f}%)")
        self.data = {
            'config': dict(self.cfg), 'element': self.element, 'ff_gain': self.ff_gain,
            't_vec_us': self.t_vec_us, 'population_pe': pe,
            'T1_us': fit["tau_us"] if fit else np.nan,
            'T1_err_us': fit["tau_err_us"] if fit else np.nan,
            'herald_keep_fraction': keep,
            'point_visit_orders': getattr(self, "point_visit_orders", None),
            'randomize_point_order': bool(self.cfg.get("randomize_point_order", False)),
            'point_order_seed': self.cfg.get("point_order_seed", None),
            'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        if fit:
            print(f"[T1{' flux ramp' if held else ''}] T1 = {fit['tau_us']:.2f} "
                  f"+/- {fit['tau_err_us']:.2f} us")
        else:
            print(f"[T1{' flux ramp' if held else ''}] decay fit failed")
        if self.save:
            self._plot_decay(pe, fit, "P(excited)",
                             f"{self.element} T1{' flux ramp' if held else ''}"
                             + (f" (ff_gain={self.ff_gain:.0f})" if held else ""),
                             plotDisp=plotDisp)
            self.pickle_data()
        return {'config': self.cfg, 'data': self.data}

    def save_data(self, data=None):
        if data is None:
            data = self.data
        print(f'Saving {self.fname}')
        super().save_data(data={'t_vec_us': self.data['t_vec_us'],
                                'population_pe': self.data['population_pe']})
