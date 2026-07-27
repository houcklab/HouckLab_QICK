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
N_SHOTS = 2000
M_REPEATS = 4
SHORT_WAIT_US = 1.0


def _pe_once(soc, soccfg, base, calib, mode, do_ff, iters, do_pi, thr, oper, gb):
    c = dict(base)
    c["shots"] = c["reps"] = int(N_SHOTS)
    c["reset_mode"] = mode
    c["reset_max_iters"] = int(iters)
    c["reset_threshold_raw"] = int(thr)
    c["reset_oper"] = oper
    c["reset_ground_below"] = gb
    c["reset_thermalization_us"] = 25.0
    c["reset_meas_syncdelay_us"] = 0.2
    c["herald_delay"] = 4.4
    c["relax_delay"] = 25.0 if mode == "feedback" else 1500.0
    c["ff_gain"] = 0
    c["ff_hold"] = float(SHORT_WAIT_US)
    c["do_pi"] = bool(do_pi)
    c["do_ff"] = bool(do_ff)
    with suppress_stdout():
        prog = FFT1Program(soccfg, c)
        i0, q0, i1, q1 = prog.acquire(soc, load_pulses=True)
    herald = float(np.asarray(discriminate_shots(i0, q0, calib)).mean())
    final = float(np.asarray(discriminate_shots(i1, q1, calib)).mean())
    return herald, final


def _stats(soc, soccfg, base, calib, mode, do_ff, iters, thr, oper, gb):
    off = np.array([_pe_once(soc, soccfg, base, calib, mode, do_ff, iters, False, thr, oper, gb)
                    for _ in range(M_REPEATS)])
    on = np.array([_pe_once(soc, soccfg, base, calib, mode, do_ff, iters, True, thr, oper, gb)
                   for _ in range(M_REPEATS)])
    return off.mean(axis=0), on.mean(axis=0)


def main():
    soc, soccfg = makeProxy()

    try:
        qch = int(BaseConfig["qubit_ch"])
        tpc = int(soccfg['gens'][qch]['tproc_ch'])
        clobber = "QUBIT freq (reg21) -- THIS was the bug" if tpc % 2 == 0 else \
            "paired-channel freq (reg21); qubit uses 11-20"
        print(f"[map] qubit gen={qch} tproc_ch={tpc} -> old reset regs 20/21 hit: {clobber}")
        for gi, g in enumerate(soccfg['gens']):
            print(f"[map] gen{gi} tproc_ch={g.get('tproc_ch')}")
    except Exception as e:
        print(f"[map] soccfg dump failed: {e}")

    probe = ActiveResetProbe(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                             suffix="ResetPrep_Phase", cfg=dict(BaseConfig))
    d = probe.calibrate_res_phase().get("data", {})
    if not d.get("supported") or not d.get("recommended"):
        print("[prep] no feedback discrimination.")
        return
    if d.get("best_res_phase") is not None:
        BaseConfig["res_phase"] = float(d["best_res_phase"])
    rec = d["recommended"]
    thr, oper, gb = int(rec["threshold_raw"]), str(rec.get("oper", "lower")), bool(rec["ground_below"])

    ss_cfg = dict(BaseConfig)
    ss_cfg["shots"] = ss_cfg["reps"] = 1000
    ss_cfg["reset_mode"] = "passive"
    ss_cfg["relax_delay"] = 1500.0
    ss_cfg["qubit_gain"] = int(BaseConfig["qubit_pi_gain"])
    with suppress_stdout():
        ss = SingleShot1Q(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                          suffix="ResetPrep_SS", cfg=ss_cfg, plot=False, save=False, min_F=0.0)
        ss.acquire()
    calib = ss.calib_params
    print(f"[prep] res_phase={float(BaseConfig['res_phase']):.1f} SS F={ss.max_F:.3f}")

    base = dict(BaseConfig)

    configs = [
        ("passive         ff=OFF", "passive", False, 3),
        ("passive         ff=ON ", "passive", True, 3),
        ("feedback it=3   ff=OFF", "feedback", False, 3),
        ("feedback it=3   ff=ON ", "feedback", True, 3),
        ("feedback it=0   ff=ON ", "feedback", True, 0),
        ("feedback it=0   ff=OFF", "feedback", False, 0),
    ]

    print(f"\nP(excited) at wait={SHORT_WAIT_US}us, {M_REPEATS}x{N_SHOTS} shots.  "
          "'final' pi-OFF vs pi-ON gives the PREP CONTRAST (should be ~0.7).")
    print(f"{'config':24s} | herald(noPi/Pi) | final noPi | final Pi | PREP CONTRAST")
    print("-" * 92)
    for name, mode, do_ff, iters in configs:
        (h_off, f_off), (h_on, f_on) = _stats(soc, soccfg, base, calib, mode, do_ff, iters,
                                               thr, oper, gb)
        contrast = f_on - f_off
        print(f"{name:24s} |   {h_off:.3f}/{h_on:.3f}   |   {f_off:.3f}    |  {f_on:.3f}   | "
              f"{contrast:+.3f}")

    print("\n[prep] READ THE PREP CONTRAST column:")
    print("  * passive ff=OFF/ON ~0.7 = the pi works and the flux path is fine.")
    print("  * whichever feedback row COLLAPSES the contrast is the culprit:")
    print("    - collapses only with ff=ON  -> the reset+flux-ramp interaction detunes/kills the prep pi")
    print("    - collapses with ff=OFF too  -> the reset block itself leaves the qubit unable to be excited")
    print("    - it=0 ff=ON restores contrast -> the RESET MEASUREMENTS (not feedback mode) are the cause")


if __name__ == "__main__":
    main()
