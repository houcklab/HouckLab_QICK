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

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import (
    SingleShot1Q, discriminate_shots)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mT1VsFlux import FFT1Program
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mActiveResetProbe import ActiveResetProbe
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.acquisition import suppress_stdout

QUBIT = "q4"
N_SHOTS = 500
M_REPEATS = 6


def _trajectory_once(soc, soccfg, cfg, calib, do_pi):
    c = dict(cfg)
    c["shots"] = c["reps"] = int(N_SHOTS)
    c["ff_gain"] = 0
    c["ff_hold"] = 0.1
    c["do_pi"] = bool(do_pi)
    c["do_ff"] = False
    with suppress_stdout():
        prog = FFT1Program(soccfg, c)
        prog.acquire(soc, load_pulses=True)
    n_reset = active_reset.active_reset_readouts(c)
    reads = 2 + n_reset
    length = prog.us2cycles(c["read_length"], ro_ch=c["ro_chs"][0])
    bi = prog.di_buf[0].reshape((int(c["reps"]), reads)) / length
    bq = prog.dq_buf[0].reshape((int(c["reps"]), reads)) / length
    return np.array([float(np.asarray(discriminate_shots(bi[:, k], bq[:, k], calib)).mean())
                     for k in range(reads)])


def _traj_stats(soc, soccfg, cfg, calib, do_pi):
    runs = np.array([_trajectory_once(soc, soccfg, cfg, calib, do_pi) for _ in range(M_REPEATS)])
    return runs.mean(axis=0), runs.std(axis=0)


def _fmt(mean, std):
    return "  ".join(f"{m:.3f}+/-{s:.3f}" for m, s in zip(mean, std))


def main():
    soc, soccfg = makeProxy()

    probe = ActiveResetProbe(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                             suffix="ResetLoc_Phase", cfg=dict(BaseConfig))
    d = probe.calibrate_res_phase().get("data", {})
    if not d.get("supported") or not d.get("recommended"):
        print("[loc] no feedback discrimination available; cannot test feedback reset.")
        return
    if d.get("best_res_phase") is not None:
        BaseConfig["res_phase"] = float(d["best_res_phase"])
    rec = d["recommended"]
    thr = int(rec["threshold_raw"])
    oper = str(rec.get("oper", "lower"))
    gb = bool(rec["ground_below"])
    print(f"[loc] res_phase={float(BaseConfig['res_phase']):.1f} thr={thr} oper={oper} "
          f"ground_below={gb}")

    ss_cfg = dict(BaseConfig)
    ss_cfg["shots"] = ss_cfg["reps"] = 1000
    ss_cfg["reset_mode"] = "passive"
    ss_cfg["relax_delay"] = 1500.0
    ss_cfg["qubit_gain"] = int(BaseConfig["qubit_pi_gain"])
    with suppress_stdout():
        ss = SingleShot1Q(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                          suffix="ResetLoc_SS", cfg=ss_cfg, plot=False, save=False, min_F=0.0)
        ss.acquire()
    calib = ss.calib_params
    print(f"[loc] SS cal F={ss.max_F:.3f}")

    fbbase = dict(BaseConfig)
    fbbase["reset_threshold_raw"] = thr
    fbbase["reset_oper"] = oper
    fbbase["reset_ground_below"] = gb

    def fb(**kw):
        c = dict(fbbase)
        c["reset_mode"] = "feedback"
        c["reset_max_iters"] = 3
        c["reset_thermalization_us"] = 25.0
        c["reset_meas_syncdelay_us"] = 0.2
        c["relax_delay"] = 25.0
        c["herald_delay"] = 4.4
        c.update(kw)
        return c

    tests = [
        ("feedback base (it3 msync0.2 th25 hd4.4)", fb()),
        ("feedback iters=1", fb(reset_max_iters=1)),
        ("feedback therm=300", fb(reset_thermalization_us=300.0)),
        ("feedback herald_delay=30", fb(herald_delay=30.0)),
        ("feedback relax_delay=1500", fb(relax_delay=1500.0)),
    ]

    print(f"\n{M_REPEATS}x{N_SHOTS} shots. P(excited) at EACH read in program order.")
    print("columns for iters=K: reset_0..reset_{K-1}, HERALD, FINAL")
    print("clean reset => every reset column marches toward ~0.06; HERALD ~0.06 both do_pi; "
          "FINAL ~0.06 (no pi) / ~0.76 (pi)")
    print("=" * 100)
    for name, cfg in tests:
        gm, gs = _traj_stats(soc, soccfg, cfg, calib, False)
        em, es = _traj_stats(soc, soccfg, cfg, calib, True)
        n_reset = active_reset.active_reset_readouts(cfg)
        labels = [f"rst{i}" for i in range(n_reset)] + ["HERALD", "FINAL"]
        print(f"\n{name}")
        print(f"   reads: {'  '.join(f'{l:>13s}' for l in labels)}")
        print(f"   no pi: {_fmt(gm, gs)}")
        print(f"   pi   : {_fmt(em, es)}")

    print("\n[loc] READ THE TRAJECTORY:")
    print("  * reset columns already climb toward ~0.4 and HERALD ~0.4 -> the reset block itself "
          "misfires/heats (fix lives in active_reset_block).")
    print("  * reset/HERALD clean ~0.06 but FINAL ~0.4 -> corruption is AFTER the reset "
          "(the dead herald measure or the herald->final gap).")
    print("  * therm=300 or relax_delay=1500 drags everything back to ~0.06 -> recoverable "
          "measurement-induced heating; 25us is just too short.")


if __name__ == "__main__":
    main()
