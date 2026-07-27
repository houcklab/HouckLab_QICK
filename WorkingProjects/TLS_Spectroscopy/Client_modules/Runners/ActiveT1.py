import os
import sys

_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d):
    if os.path.isdir(os.path.join(_d, "WorkingProjects")):
        if _d not in sys.path:
            sys.path.insert(0, _d)
        break
    _d = os.path.dirname(_d)

import numpy as np
import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import (
    SingleShot1Q, discriminate_shots)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mT1VsFlux import FFT1Program
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mActiveResetProbe import ActiveResetProbe
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.acquisition import suppress_stdout

QUBIT = "q4"
SHOTS = 1000
ROUNDS = 10
T_POINTS = 61
T_MIN_US = 1.0
T_MAX_US = 1500.0


def _decay(t, P0, P1, T1):
    return P0 + (P1 - P0) * np.exp(-t / T1)


def _t1_curve(soc, soccfg, cfg, calib, t_vec):
    reps = SHOTS // ROUNDS
    pe = np.full((ROUNDS, len(t_vec)), np.nan)
    for r in range(ROUNDS):
        for k, t in enumerate(t_vec):
            c = dict(cfg)
            c["shots"] = c["reps"] = int(reps)
            c["ff_gain"] = 0
            c["ff_hold"] = float(t)
            c["do_pi"] = True
            c["do_ff"] = True
            with suppress_stdout():
                prog = FFT1Program(soccfg, c)
                _i0, _q0, i1, q1 = prog.acquire(soc, load_pulses=True)
            pe[r, k] = float(np.asarray(discriminate_shots(i1, q1, calib)).mean())
    return np.nanmean(pe, axis=0)


def _fit(t_vec, pe):
    mid = 0.5 * (pe.max() + pe.min())
    t_seed = float(t_vec[int(np.argmin(np.abs(pe - mid)))])
    p0 = [float(pe.min()), float(pe.max()), max(1.0, t_seed)]
    popt, pcov = curve_fit(_decay, t_vec, pe, p0=p0,
                           bounds=([0.0, 0.0, 0.1], [1.0, 1.0, 1e5]), maxfev=40000)
    return popt, float(np.sqrt(pcov[2, 2]))


def main():
    soc, soccfg = makeProxy()

    probe = ActiveResetProbe(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                             suffix="ActiveT1_Phase", cfg=dict(BaseConfig))
    d = probe.calibrate_res_phase().get("data", {})
    if not d.get("supported") or not d.get("recommended"):
        print("[t1] no feedback discrimination; cannot force active reset.")
        return
    if d.get("best_res_phase") is not None:
        BaseConfig["res_phase"] = float(d["best_res_phase"])
    rec = d["recommended"]
    thr, oper, gb = int(rec["threshold_raw"]), str(rec.get("oper", "lower")), bool(rec["ground_below"])
    print(f"[t1] res_phase={float(BaseConfig['res_phase']):.1f} thr={thr} ground_below={gb} "
          "(FORCING active reset -- bypassing the residual gate)")

    ss_cfg = dict(BaseConfig)
    ss_cfg["shots"] = ss_cfg["reps"] = 1000
    ss_cfg["reset_mode"] = "passive"
    ss_cfg["relax_delay"] = 1500.0
    ss_cfg["qubit_gain"] = int(BaseConfig["qubit_pi_gain"])
    with suppress_stdout():
        ss = SingleShot1Q(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                          suffix="ActiveT1_SS", cfg=ss_cfg, plot=False, save=False, min_F=0.0)
        ss.acquire()
    calib = ss.calib_params
    print(f"[t1] SS cal F={ss.max_F:.3f}")

    t_vec = np.logspace(np.log10(T_MIN_US), np.log10(T_MAX_US), T_POINTS)

    active = dict(BaseConfig)
    active["reset_threshold_raw"] = thr
    active["reset_oper"] = oper
    active["reset_ground_below"] = gb
    active["reset_mode"] = "feedback"
    active["reset_max_iters"] = 3
    active["reset_thermalization_us"] = 25.0
    active["reset_meas_syncdelay_us"] = 0.2
    active["relax_delay"] = 25.0
    active["herald_delay"] = 4.4

    passive = dict(BaseConfig)
    passive["reset_mode"] = "passive"
    passive["relax_delay"] = 1500.0

    print("[t1] acquiring ACTIVE-reset T1 (feedback, 25us cadence) ...")
    pe_a = _t1_curve(soc, soccfg, active, calib, t_vec)
    print("[t1] acquiring PASSIVE T1 (1500us relax) ...")
    pe_p = _t1_curve(soc, soccfg, passive, calib, t_vec)

    (a0, a1, aT1), aerr = _fit(t_vec, pe_a)
    (p0, p1, pT1), perr = _fit(t_vec, pe_p)
    print("\n" + "=" * 60)
    print(f"ACTIVE-reset T1 = {aT1:.1f} +/- {aerr:.1f} us   "
          f"(floor {a0:.3f}, peak {a1:.3f}, contrast {a1 - a0:.3f})")
    print(f"PASSIVE     T1 = {pT1:.1f} +/- {perr:.1f} us   "
          f"(floor {p0:.3f}, peak {p1:.3f}, contrast {p1 - p0:.3f})")
    print("=" * 60)

    fig, ax = plt.subplots(figsize=(8, 5), constrained_layout=True)
    tt = np.logspace(np.log10(T_MIN_US), np.log10(T_MAX_US), 400)
    ax.plot(t_vec, pe_a, "o", ms=4, color="C0", label=f"active reset (T1={aT1:.0f}us)")
    ax.plot(tt, _decay(tt, a0, a1, aT1), "-", color="C0", lw=1)
    ax.plot(t_vec, pe_p, "o", ms=4, color="C1", label=f"passive (T1={pT1:.0f}us)")
    ax.plot(tt, _decay(tt, p0, p1, pT1), "-", color="C1", lw=1)
    ax.set_xscale("log")
    ax.set_xlabel("delay t (us)")
    ax.set_ylabel("P(e)")
    ax.set_title(f"{QUBIT} T1: active reset (forced) vs passive")
    ax.legend()
    png = os.path.join(outerFolder, f"{QUBIT}_ActiveT1.png")
    fig.savefig(png, bbox_inches="tight")
    plt.close(fig)
    print(f"[t1] saved {png}")


if __name__ == "__main__":
    main()
