import os
import sys
import time

import numpy as np

_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d):
    if os.path.isdir(os.path.join(_d, "WorkingProjects")):
        if _d not in sys.path:
            sys.path.insert(0, _d)
        break
    _d = os.path.dirname(_d)

from qick import AveragerProgram
from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import set_readout_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.rfdc_cal import (
    freeze_readout_cal, freeze_all_adc_cal, cal_freeze_status)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.save_paths import data_path

RO_CH = 0
N = 420
DWELL_S = 1.0
REPS = 500
RELAX_US = 20.0
FREEZE_ALL = False
PLOT = True


class _ReadProg(AveragerProgram):
    def initialize(self):
        cfg = self.cfg
        cfg.setdefault("reps", int(cfg.get("shots", 1000)))
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg.get("mixer_freq", 0), ro_ch=cfg["ro_chs"][0])
        for ro in cfg["ro_chs"]:
            self.declare_readout(ch=ro, freq=cfg["read_pulse_freq"],
                                 length=self.us2cycles(cfg["read_length"], ro_ch=cfg["ro_chs"][0]),
                                 gen_ch=cfg["res_ch"])
        rf = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])
        set_readout_pulse(self, rf)
        self.synci(200)

    def body(self):
        cfg = self.cfg
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(cfg["relax_delay"]))


def _progress(k, n, t0, label):
    pct = (k + 1) / n * 100.0
    el = time.time() - t0
    eta = el * (n - k - 1) / (k + 1) if k >= 0 else 0.0
    sys.stdout.write(f"\r  {label}: {pct:5.1f}%  ({k + 1}/{n})  {el:.0f}s elapsed, ETA {eta:.0f}s     ")
    sys.stdout.flush()
    if k + 1 >= n:
        sys.stdout.write("\n")


def baseline_trace(soc, soccfg, cfg, n, dwell_s, label):
    prog = _ReadProg(soccfg, cfg)
    t0 = time.time()
    ts, I, Q = np.empty(n), np.empty(n), np.empty(n)
    for k in range(n):
        i, q = prog.acquire(soc, load_pulses=(k == 0), progress=False)
        I[k] = float(np.asarray(i).ravel()[0])
        Q[k] = float(np.asarray(q).ravel()[0])
        ts[k] = time.time() - t0
        _progress(k, n, t0, label)
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

    dname = data_path("CalFreezeTest")
    npz = dname + ".npz"
    np.savez(npz, t1=t1, I1=I1, Q1=Q1, t2=t2, I2=I2, Q2=Q2)

    s1, s2 = steps(I1, Q1), steps(I2, Q2)
    print("\n==== RESULT ====")
    print(f"discrete baseline steps  ->  cal ON: {s1}   |   cal FROZEN: {s2}")
    if s1 > 0 and s2 == 0:
        print("CONFIRMED: the telegraph is the RF-ADC background calibration. "
              "Fix: freeze_readout_cal(soc) before each run.")
    elif s1 == 0:
        print("Inconclusive: no telegraph event captured while cal was ON (it is intermittent). "
              "Rerun (raise N / when you have been seeing the band).")
    else:
        print("Steps persist while FROZEN: not (only) ADC background cal -- "
              "next do the readout-only / loopback test.")
    print("raw data:", npz)

    if PLOT:
        try:
            import matplotlib
            matplotlib.use("TkAgg")
            import matplotlib.pyplot as plt
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
            png = dname + ".png"
            plt.savefig(png, dpi=110)
            print("saved", png)
            plt.show()
        except Exception as e:
            print(f"[plot skipped: {type(e).__name__}: {e}] -- verdict above stands; "
                  f"plot {npz} elsewhere if you want the figure.")


if __name__ == "__main__":
    main()
