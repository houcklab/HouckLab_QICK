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

RO_CH = 0
LABEL = "on-resonance"
READ_FREQ_MHZ = None
N = 500
DWELL_S = 0.8
REPS = 500
RELAX_US = 20.0
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


def baseline_trace(soc, soccfg, cfg, n, dwell_s):
    prog = _ReadProg(soccfg, cfg)
    t0 = time.time()
    ts, I, Q = np.empty(n), np.empty(n), np.empty(n)
    for k in range(n):
        i, q = prog.acquire(soc, load_pulses=(k == 0), progress=False)
        I[k] = float(np.asarray(i).ravel()[0])
        Q[k] = float(np.asarray(q).ravel()[0])
        ts[k] = time.time() - t0
        pct = (k + 1) / n * 100.0
        sys.stdout.write(f"\r  {pct:5.1f}%  ({k + 1}/{n})  {ts[k]:.0f}s     ")
        sys.stdout.flush()
        if dwell_s:
            time.sleep(dwell_s)
    sys.stdout.write("\n")
    return ts, I, Q


def rolling_median(x, w):
    x = np.asarray(x, dtype=float)
    nn = x.size
    h = max(1, w // 2)
    return np.array([np.median(x[max(0, i - h):min(nn, i + h + 1)]) for i in range(nn)])


def analyze(I, Q):
    w = max(7, I.size // 20)
    sI, sQ = rolling_median(I, w), rolling_median(Q, w)
    fast = float(1.4826 * np.median(np.hypot(I - sI, Q - sQ)))
    step = np.hypot(np.diff(sI), np.diff(sQ))
    sig = 1.4826 * np.median(np.abs(step - np.median(step))) + 1e-12
    njump = int(np.sum(step > 8 * sig))
    span = float(np.hypot(sI.max() - sI.min(), sQ.max() - sQ.min()))
    return sI, sQ, span, njump, fast


def main():
    soc, soccfg = makeProxy()
    cfg = dict(BaseConfig)
    cfg["reps"] = REPS
    cfg["shots"] = REPS
    cfg["relax_delay"] = RELAX_US
    if READ_FREQ_MHZ is not None:
        cfg["read_pulse_freq"] = float(READ_FREQ_MHZ)
    span_min = N * (DWELL_S + REPS * (cfg["read_length"] + RELAX_US) * 1e-6) / 60.0
    print(f"Root-cause telegraph trace | label='{LABEL}' | read {cfg['read_pulse_freq']:.3f} MHz "
          f"gain {cfg['read_pulse_gain']} | {N} samples x {DWELL_S}s (~{span_min:.1f} min)")

    t, I, Q = baseline_trace(soc, soccfg, cfg, N, DWELL_S)
    sI, sQ, span, njump, fast = analyze(I, Q)

    npz = os.path.join(os.path.expanduser("~"), "Downloads", f"loopback_{LABEL.replace(' ', '_')}.npz")
    np.savez(npz, t=t, I=I, Q=Q)

    print("\n==== RESULT ({}) ====".format(LABEL))
    print(f"discrete baseline jumps = {njump}  | slow-drift span = {span:.3f}  | fast-noise sigma = {fast:.3f}")
    present = (njump >= 3) or (span > 3.0 * fast)
    print("=> telegraph/steps", "PRESENT" if present else "absent (clean)", "at this readout condition.")
    print("raw data:", npz)
    print("\ninterpret across conditions:")
    print("  on-resonance         : your known artifact (expect PRESENT).")
    print("  off-resonance (read far from the dip): PRESENT => instability is in the RFSoC/RF electronics")
    print("                         (clock/PLL/ADC), NOT the resonator.  absent => the resonator is involved.")
    print("  physical DAC->ADC loopback (cavity out of the loop): PRESENT => it is inside the RFSoC;")
    print("                         absent => it is the RF chain / cavity / fridge.")

    if PLOT:
        try:
            import matplotlib
            matplotlib.use("TkAgg")
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(9.5, 4.5))
            ax.plot(t, I, ".", ms=2, alpha=0.3, color="tab:orange")
            ax.plot(t, Q, ".", ms=2, alpha=0.3, color="tab:blue")
            ax.plot(t, sI, "-", color="darkorange", lw=2, label="I baseline")
            ax.plot(t, sQ, "-", color="navy", lw=2, label="Q baseline")
            ax.set_title(f"{LABEL}: jumps={njump}, slow span={span:.2f}, fast={fast:.2f}")
            ax.set_xlabel("time [s]")
            ax.set_ylabel("a.u.")
            ax.legend(fontsize=8)
            plt.tight_layout()
            png = os.path.join(os.path.expanduser("~"), "Downloads", f"loopback_{LABEL.replace(' ', '_')}.png")
            plt.savefig(png, dpi=110)
            print("saved", png)
            plt.show()
        except Exception as e:
            print(f"[plot skipped: {type(e).__name__}: {e}]")


if __name__ == "__main__":
    main()
