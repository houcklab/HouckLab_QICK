import os
import sys
import time

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
T_POINTS = 41
T_MIN_US = 1.0
T_MAX_US = 1500.0


def _decay(t, P0, P1, T1):
    return P0 + (P1 - P0) * np.exp(-t / T1)


def _run_curve(soc, soccfg, cfg, calib, t_vec, sleep_s):
    reps = SHOTS // ROUNDS
    pe_round = np.zeros((ROUNDS, len(t_vec)))
    for r in range(ROUNDS):
        if r > 0 and sleep_s > 0:
            time.sleep(float(sleep_s))
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
            pe_round[r, k] = float(np.asarray(discriminate_shots(i1, q1, calib)).mean())
    return pe_round.mean(axis=0), pe_round.var(axis=0), pe_round


def _fit(t_vec, pe):
    mid = 0.5 * (pe.max() + pe.min())
    t_seed = float(t_vec[int(np.argmin(np.abs(pe - mid)))])
    p0 = [float(pe.min()), float(pe.max()), max(1.0, t_seed)]
    popt, pcov = curve_fit(_decay, t_vec, pe, p0=p0,
                           bounds=([0.0, 0.0, 0.1], [1.0, 1.0, 1e5]), maxfev=40000)
    resid = pe - _decay(t_vec, *popt)
    rms = float(np.sqrt(np.mean(resid ** 2)))
    ac = float(np.corrcoef(resid[:-1], resid[1:])[0, 1]) if resid.std() > 0 else float("nan")
    return float(popt[2]), float(np.sqrt(pcov[2, 2])), rms, ac, resid, popt


def main():
    soc, soccfg = makeProxy()

    probe = ActiveResetProbe(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                             suffix="ResetScatter_Phase", cfg=dict(BaseConfig))
    d = probe.calibrate_res_phase().get("data", {})
    if not d.get("supported") or not d.get("recommended"):
        print("[scatter] no feedback discrimination; cannot test feedback reset.")
        return
    if d.get("best_res_phase") is not None:
        BaseConfig["res_phase"] = float(d["best_res_phase"])
    rec = d["recommended"]
    thr, oper, gb = int(rec["threshold_raw"]), str(rec.get("oper", "lower")), bool(rec["ground_below"])
    print(f"[scatter] res_phase={float(BaseConfig['res_phase']):.1f} thr={thr} oper={oper} "
          f"ground_below={gb}")

    ss_cfg = dict(BaseConfig)
    ss_cfg["shots"] = ss_cfg["reps"] = 1000
    ss_cfg["reset_mode"] = "passive"
    ss_cfg["relax_delay"] = 1500.0
    ss_cfg["qubit_gain"] = int(BaseConfig["qubit_pi_gain"])
    with suppress_stdout():
        ss = SingleShot1Q(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                          suffix="ResetScatter_SS", cfg=ss_cfg, plot=False, save=False, min_F=0.0)
        ss.acquire()
    calib = ss.calib_params
    print(f"[scatter] SS cal F={ss.max_F:.3f}")

    t_vec = np.logspace(np.log10(T_MIN_US), np.log10(T_MAX_US), T_POINTS)

    fb = dict(BaseConfig)
    fb["reset_threshold_raw"] = thr
    fb["reset_oper"] = oper
    fb["reset_ground_below"] = gb
    fb["reset_mode"] = "feedback"
    fb["reset_max_iters"] = 3
    fb["reset_thermalization_us"] = 25.0
    fb["reset_meas_syncdelay_us"] = 0.2
    fb["relax_delay"] = 25.0
    fb["herald_delay"] = 4.4

    passive = dict(BaseConfig)
    passive["reset_mode"] = "passive"
    passive["relax_delay"] = 1500.0

    fb_it1 = dict(fb)
    fb_it1["reset_max_iters"] = 1

    runs = [
        ("feedback S=0", fb, 0.0),
        ("passive relax=1500", passive, 0.0),
        ("feedback S=8s/round", fb, 8.0),
        ("feedback iters=1 S=0", fb_it1, 0.0),
    ]

    floor = float(np.sqrt(0.25 / SHOTS))
    print(f"\n{SHOTS} shots ({ROUNDS} rounds) x {T_POINTS} waits {T_MIN_US}..{T_MAX_US} us")
    print(f"binomial RMS floor ~ {floor:.4f}")
    print(f"{'config':22s} | {'T1 (us)':16s} | {'RMS resid':9s} | {'lag1 AC':7s} | Var_r peak @ t")
    print("-" * 92)
    curves = []
    for name, cfg, s in runs:
        pe, var_r, _ = _run_curve(soc, soccfg, cfg, calib, t_vec, s)
        T1, err, rms, ac, resid, popt = _fit(t_vec, pe)
        t_peak = float(t_vec[int(np.argmax(var_r))])
        print(f"{name:22s} | {T1:7.1f} +/- {err:5.1f} | {rms:9.4f} | {ac:+.3f}  | {t_peak:7.1f}")
        curves.append((name, pe, var_r, popt, T1))

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 9), constrained_layout=True)
    tt = np.logspace(np.log10(T_MIN_US), np.log10(T_MAX_US), 400)
    for name, pe, var_r, popt, T1 in curves:
        ax1.plot(t_vec, pe, "o", ms=3, label=f"{name} (T1={T1:.0f})")
        ax1.plot(tt, _decay(tt, *popt), "-", lw=1)
        ax2.plot(t_vec, np.sqrt(var_r), "o-", ms=3, label=name)
    ax1.set_xscale("log")
    ax1.set_xlabel("delay t (us)")
    ax1.set_ylabel("P(e)")
    ax1.set_title(f"{QUBIT} T1 decays: feedback vs passive vs feedback+inter-round dwell")
    ax1.legend(fontsize=8)
    ax2.set_xscale("log")
    ax2.set_xlabel("delay t (us)")
    ax2.set_ylabel("round-to-round std of P(e)")
    ax2.axhline(floor, color="k", ls="--", lw=1, label="binomial floor")
    ax2.set_title("round-to-round scatter vs delay (TLS peaks near t~T1; reset-variance peaks at short t)")
    ax2.legend(fontsize=8)
    png = os.path.join(outerFolder, f"{QUBIT}_ResetScatter.png")
    fig.savefig(png, bbox_inches="tight")
    plt.close(fig)
    print(f"\n[scatter] saved {png}")

    print("\n[scatter] DECISION:")
    print("  * feedback S=8s RMS/T1_err COLLAPSES toward passive -> TLS T1 wander under-sampled by "
          "the fast feedback cadence (B). Not a reset defect: give feedback more rounds / an "
          "inter-round dwell / ensemble error bars.")
    print("  * feedback S=8s stays high AND Var_r peaks at SHORT t, insensitive to iters -> "
          "reset-decision variance (C).")
    print("  * excess only in feedback, Var_r peaks near t~T1, present in passive too, lag1 AC>0 -> "
          "confirms TLS shape (B).")


if __name__ == "__main__":
    main()
