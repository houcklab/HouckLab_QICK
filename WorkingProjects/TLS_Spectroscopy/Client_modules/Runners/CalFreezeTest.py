import os
import sys
import time

import numpy as np
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt

_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d):
    if os.path.isdir(os.path.join(_d, "WorkingProjects")):
        if _d not in sys.path:
            sys.path.insert(0, _d)
        break
    _d = os.path.dirname(_d)

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mTransmission import TransReadProgram
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.progress import progress_counter
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.rfdc_cal import (
    freeze_readout_cal, freeze_all_adc_cal, cal_freeze_status)

RO_CH = 0
N = 420
DWELL_S = 1.0
REPS = 500
RELAX_US = 20.0
FREEZE_ALL = False


def baseline_trace(soc, soccfg, cfg, n, dwell_s, label):
    prog = TransReadProgram(soccfg, cfg)
    t0 = time.time()
    ts, I, Q = np.empty(n), np.empty(n), np.empty(n)
    for k in range(n):
        i, q = prog.acquire(soc, load_pulses=(k == 0), progress=False)
        I[k] = float(np.asarray(i).ravel()[0])
        Q[k] = float(np.asarray(q).ravel()[0])
        ts[k] = time.time() - t0
        progress_counter(k, n, start_time=t0, label=label)
        if dwell_s:
            time.sleep(dwell_s)
    return ts, I, Q


def count_steps(x, k=6.0):
    d = np.abs(np.diff(np.asarray(x, dtype=float)))
    sig = 1.4826 * np.median(np.abs(d - np.median(d))) + 1e-12
    return int(np.sum(d > k * sig))


def steps(I, Q):
    return count_steps(I) + count_steps(Q)


def main():
    soc, soccfg = makeProxy()
    cfg = dict(BaseConfig)
    cfg["reps"] = REPS
    cfg["shots"] = REPS
    cfg["relax_delay"] = RELAX_US
    span_min = N * (DWELL_S + REPS * (cfg["read_length"] + RELAX_US) * 1e-6) / 60.0
    print(f"Readout baseline telegraph test @ {cfg['read_pulse_freq']:.3f} MHz gain {cfg['read_pulse_gain']}: "
          f"{N} samples x {DWELL_S}s dwell (~{span_min:.1f} min per trace)")
    cal_freeze_status(soc, RO_CH)

    print("\n[1/2] calibration RUNNING (not frozen) ...")
    freeze_readout_cal(soc, RO_CH, freeze=False)
    t1, I1, Q1 = baseline_trace(soc, soccfg, cfg, N, DWELL_S, "cal ON")

    print("\n[2/2] calibration FROZEN ...")
    if FREEZE_ALL:
        freeze_all_adc_cal(soc, freeze=True)
    else:
        freeze_readout_cal(soc, RO_CH, freeze=True)
    t2, I2, Q2 = baseline_trace(soc, soccfg, cfg, N, DWELL_S, "cal FROZEN")

    freeze_readout_cal(soc, RO_CH, freeze=False)

    s1, s2 = steps(I1, Q1), steps(I2, Q2)
    print("\n==== RESULT ====")
    print(f"discrete baseline steps  ->  cal ON: {s1}   |   cal FROZEN: {s2}")
    if s1 > 0 and s2 == 0:
        print("CONFIRMED: the telegraph is the RF-ADC background calibration. "
              "Fix: freeze_readout_cal(soc) before each run.")
    elif s1 == 0:
        print("Inconclusive: no telegraph event was captured while cal was ON (it is intermittent). "
              "Rerun (longer N / when you have been seeing the band).")
    else:
        print("Steps persist while FROZEN: not (only) ADC background cal -- "
              "next do the readout-only / loopback test.")

    fig, ax = plt.subplots(2, 1, sharex=True, figsize=(9, 6.5))
    for a, (t, I, Q, title) in zip(ax, [(t1, I1, Q1, f"cal ON  ({s1} steps)"),
                                        (t2, I2, Q2, f"cal FROZEN  ({s2} steps)")]):
        a.plot(t, I, ".-", ms=3, color="tab:orange", label="I")
        a.plot(t, Q, ".-", ms=3, color="tab:blue", label="Q")
        a.set_title(title)
        a.set_ylabel("a.u.")
        a.legend(fontsize=8)
    ax[1].set_xlabel("time [s]")
    plt.tight_layout()
    out = os.path.join(os.path.expanduser("~"), "Downloads", "cal_freeze_test.png")
    plt.savefig(out, dpi=110)
    print("saved", out)
    plt.show()


if __name__ == "__main__":
    main()
