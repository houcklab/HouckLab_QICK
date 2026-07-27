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
T_POINTS = 41
T_MIN_US = 1.0
T_MAX_US = 1500.0


def _decay(t, P0, P1, T1):
    return P0 + (P1 - P0) * np.exp(-t / T1)


def _fit(t_vec, pe):
    good = np.isfinite(pe)
    t_vec, pe = t_vec[good], pe[good]
    mid = 0.5 * (pe.max() + pe.min())
    t_seed = float(t_vec[int(np.argmin(np.abs(pe - mid)))])
    p0 = [float(pe.min()), float(pe.max()), max(1.0, t_seed)]
    popt, pcov = curve_fit(_decay, t_vec, pe, p0=p0,
                           bounds=([0.0, 0.0, 0.1], [1.0, 1.0, 1e5]), maxfev=40000)
    resid = pe - _decay(t_vec, *popt)
    rms = float(np.sqrt(np.mean(resid ** 2)))
    ac = float(np.corrcoef(resid[:-1], resid[1:])[0, 1]) if resid.std() > 0 else float("nan")
    return float(popt[2]), float(np.sqrt(pcov[2, 2])), rms, ac, popt


def _feedback_both(soc, soccfg, cfg, calib, t_vec, herald_calib):
    reps = SHOTS // ROUNDS
    pe_all = np.full((ROUNDS, len(t_vec)), np.nan)
    pe_ps = np.full((ROUNDS, len(t_vec)), np.nan)
    keptfrac = np.zeros((ROUNDS, len(t_vec)))
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
                i0, q0, i1, q1 = prog.acquire(soc, load_pulses=True)
            final = np.asarray(discriminate_shots(i1, q1, calib))
            keep = np.asarray(discriminate_shots(i0, q0, herald_calib)) == 0
            pe_all[r, k] = float(final.mean())
            pe_ps[r, k] = float(final[keep].mean()) if keep.sum() > 0 else np.nan
            keptfrac[r, k] = float(keep.mean())
    return (np.nanmean(pe_all, 0), np.nanvar(pe_all, 0),
            np.nanmean(pe_ps, 0), np.nanvar(pe_ps, 0), float(np.nanmean(keptfrac)))


def _passive(soc, soccfg, cfg, calib, t_vec):
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
    return np.nanmean(pe, 0), np.nanvar(pe, 0)


def main():
    soc, soccfg = makeProxy()

    probe = ActiveResetProbe(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                             suffix="ResetPS_Phase", cfg=dict(BaseConfig))
    d = probe.calibrate_res_phase().get("data", {})
    if not d.get("supported") or not d.get("recommended"):
        print("[ps] no feedback discrimination; cannot test.")
        return
    if d.get("best_res_phase") is not None:
        BaseConfig["res_phase"] = float(d["best_res_phase"])
    rec = d["recommended"]
    thr, oper, gb = int(rec["threshold_raw"]), str(rec.get("oper", "lower")), bool(rec["ground_below"])
    print(f"[ps] res_phase={float(BaseConfig['res_phase']):.1f} thr={thr} oper={oper} ground_below={gb}")

    ss_cfg = dict(BaseConfig)
    ss_cfg["shots"] = ss_cfg["reps"] = 1000
    ss_cfg["reset_mode"] = "passive"
    ss_cfg["relax_delay"] = 1500.0
    ss_cfg["qubit_gain"] = int(BaseConfig["qubit_pi_gain"])
    with suppress_stdout():
        ss = SingleShot1Q(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                          suffix="ResetPS_SS", cfg=ss_cfg, plot=False, save=False, min_F=0.0)
        ss.acquire()
    calib = ss.calib_params
    herald_calib = dict(calib)
    herald_calib["threshold"] = calib.get("ground_threshold", calib["threshold"])
    print(f"[ps] SS cal F={ss.max_F:.3f} threshold={calib['threshold']:.3f} "
          f"ground_threshold={calib.get('ground_threshold')}")

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

    pe_all, var_all, pe_ps, var_ps, kept = _feedback_both(soc, soccfg, fb, calib, t_vec, herald_calib)
    pe_pas, var_pas = _passive(soc, soccfg, passive, calib, t_vec)

    floor = float(np.sqrt(0.25 / SHOTS))
    rows = [
        ("feedback KEEP-ALL (old)", pe_all, var_all, 1.0),
        ("feedback CONFIRMED-GROUND (QUA)", pe_ps, var_ps, kept),
        ("passive relax=1500", pe_pas, var_pas, 1.0),
    ]
    print(f"\n{SHOTS} shots ({ROUNDS} rounds) x {T_POINTS} waits.  binomial RMS floor ~ {floor:.4f}")
    print(f"{'analysis':34s} | {'T1 (us)':16s} | {'RMS':7s} | {'lag1':6s} | Var_r@t | yield")
    print("-" * 92)
    curves = []
    for name, pe, var_r, y in rows:
        T1, err, rms, ac, popt = _fit(t_vec, pe)
        t_peak = float(t_vec[int(np.nanargmax(var_r))])
        print(f"{name:34s} | {T1:7.1f} +/- {err:5.1f} | {rms:.4f} | {ac:+.2f} | {t_peak:7.1f} | {y:.2f}")
        curves.append((name, pe, var_r, popt))

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 9), constrained_layout=True)
    tt = np.logspace(np.log10(T_MIN_US), np.log10(T_MAX_US), 400)
    for name, pe, var_r, popt in curves:
        ax1.plot(t_vec, pe, "o", ms=3, label=name)
        ax1.plot(tt, _decay(tt, *popt), "-", lw=1)
        ax2.plot(t_vec, np.sqrt(var_r), "o-", ms=3, label=name)
    for ax in (ax1, ax2):
        ax.set_xscale("log")
        ax.set_xlabel("delay t (us)")
        ax.legend(fontsize=8)
    ax1.set_ylabel("P(e)")
    ax1.set_title(f"{QUBIT} T1: keep-all vs confirmed-ground post-selection vs passive")
    ax2.axhline(floor, color="k", ls="--", lw=1)
    ax2.set_ylabel("round-to-round std of P(e)")
    ax2.set_title("prep variance peaks at SHORT t for keep-all; post-selection should flatten it")
    png = os.path.join(outerFolder, f"{QUBIT}_ResetPostselect.png")
    fig.savefig(png, bbox_inches="tight")
    plt.close(fig)
    print(f"\n[ps] saved {png}")
    print("[ps] EXPECT: CONFIRMED-GROUND removes the short-t std spike of KEEP-ALL and its T1/RMS "
          "matches passive -> the port bug was keeping mis-reset shots (QUA drops them).")


if __name__ == "__main__":
    main()
