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
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.acquisition import suppress_stdout

QUBIT = "q4"
N_SHOTS = 500
M_REPEATS = 12


def _pe_once(soc, soccfg, cfg, calib, do_pi):
    c = dict(cfg)
    c["shots"] = c["reps"] = int(N_SHOTS)
    c["ff_gain"] = 0
    c["ff_hold"] = 0.1
    c["do_pi"] = bool(do_pi)
    c["do_ff"] = False
    with suppress_stdout():
        prog = FFT1Program(soccfg, c)
        _i0, _q0, i1, q1 = prog.acquire(soc, load_pulses=True)
    return float(np.asarray(discriminate_shots(i1, q1, calib)).mean())


def _stats(soc, soccfg, cfg, calib, do_pi):
    vals = np.array([_pe_once(soc, soccfg, cfg, calib, do_pi) for _ in range(M_REPEATS)])
    return float(vals.mean()), float(vals.std())


def main():
    soc, soccfg = makeProxy()

    probe = ActiveResetProbe(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                             suffix="ResetDiag_Phase", cfg=dict(BaseConfig))
    d = probe.calibrate_res_phase().get("data", {})
    if not d.get("supported") or not d.get("recommended"):
        print("[diag] no feedback discrimination available; cannot test feedback reset.")
        return
    if d.get("best_res_phase") is not None:
        BaseConfig["res_phase"] = float(d["best_res_phase"])
    rec = d["recommended"]
    thr = int(rec["threshold_raw"])
    oper = str(rec.get("oper", "lower"))
    gb = bool(rec["ground_below"])
    print(f"[diag] res_phase={float(BaseConfig['res_phase']):.1f} thr={thr} oper={oper} "
          f"ground_below={gb}")

    ss_cfg = dict(BaseConfig)
    ss_cfg["shots"] = ss_cfg["reps"] = 1000
    ss_cfg["reset_mode"] = "passive"
    ss_cfg["relax_delay"] = 1500.0
    ss_cfg["qubit_gain"] = int(BaseConfig["qubit_pi_gain"])
    with suppress_stdout():
        ss = SingleShot1Q(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                          suffix="ResetDiag_SS", cfg=ss_cfg, plot=False, save=False, min_F=0.0)
        ss.acquire()
    calib = ss.calib_params
    print(f"[diag] SS cal F={ss.max_F:.3f} calib={calib}")

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
        c.update(kw)
        return c

    passive = dict(BaseConfig)
    passive["reset_mode"] = "passive"
    passive["relax_delay"] = 1500.0

    tests = [
        ("passive relax=1500us", passive),
        ("feedback msync=0.2 iters=3 therm=25", fb()),
        ("feedback msync=3.0 iters=3 therm=25", fb(reset_meas_syncdelay_us=3.0)),
        ("feedback msync=0.2 iters=1 therm=25", fb(reset_max_iters=1)),
        ("feedback msync=0.2 iters=3 therm=100", fb(reset_thermalization_us=100.0)),
        ("feedback msync=5.0 iters=2 therm=100", fb(reset_meas_syncdelay_us=5.0,
                                                    reset_max_iters=2,
                                                    reset_thermalization_us=100.0)),
    ]

    print(f"\n{M_REPEATS} repeats x {N_SHOTS} shots -- P(excited) mean +/- std "
          f"(std = the shot-to-shot scatter we are hunting)")
    print(f"{'config':46s} | ground(no pi)     | excited(pi)")
    print("-" * 90)
    for name, cfg in tests:
        gm, gs = _stats(soc, soccfg, cfg, calib, False)
        em, es = _stats(soc, soccfg, cfg, calib, True)
        print(f"{name:46s} | {gm:.3f} +/- {gs:.3f}  | {em:.3f} +/- {es:.3f}")
    print(f"\n[diag] shot-noise floor ~ {np.sqrt(0.5 * 0.5 / N_SHOTS):.3f}. "
          "A feedback std much larger than the passive std localizes the reset scatter; "
          "the variant with the lowest std shows which knob (msync / iters / therm) fixes it.")


if __name__ == "__main__":
    main()
