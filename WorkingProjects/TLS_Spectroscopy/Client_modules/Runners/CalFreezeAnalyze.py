import glob
import os

import numpy as np

DL = os.path.join(os.path.expanduser("~"), "Downloads")


def _find_npz():
    prefer = os.path.join(DL, "cal_freeze_test.npz")
    cands = ([prefer] if os.path.exists(prefer) else []) + sorted(glob.glob(os.path.join(DL, "cal_freeze*.npz")))
    return cands[0] if cands else None


def rolling_median(x, w):
    x = np.asarray(x, dtype=float)
    n = x.size
    h = max(1, w // 2)
    return np.array([np.median(x[max(0, i - h):min(n, i + h + 1)]) for i in range(n)])


def analyze(t, I, Q, label, w):
    sI, sQ = rolling_median(I, w), rolling_median(Q, w)
    fast = float(np.median(np.hypot(I - sI, Q - sQ)) * 1.4826)
    step = np.hypot(np.diff(sI), np.diff(sQ))
    sig = 1.4826 * np.median(np.abs(step - np.median(step))) + 1e-12
    njump = int(np.sum(step > 8 * sig))
    span = float(np.hypot(sI.max() - sI.min(), sQ.max() - sQ.min()))
    print(f"{label}: slow-baseline span={span:6.3f} | slow jumps(>8sig)={njump:2d} | fast-noise sigma={fast:.3f}")
    return sI, sQ, span, njump, fast


def main():
    npz = _find_npz()
    if npz is None:
        print("No cal_freeze*.npz found in", DL)
        print("-> the .npz did not save. Re-run CalFreezeTest.py; the npz is written before the plot.")
        return
    print("loaded", npz)
    d = np.load(npz)
    n = d["I1"].size
    w = max(7, n // 20)
    print(f"{n} samples/trace, rolling-median window = {w}\n")
    a = analyze(d["t1"], d["I1"], d["Q1"], "cal ON   ", w)
    b = analyze(d["t2"], d["I2"], d["Q2"], "cal FROZEN", w)

    print("\n==== interpretation ====")
    print(f"slow drift span: ON {a[2]:.3f} vs FROZEN {b[2]:.3f}   (freezing should shrink this if it is the ADC cal)")
    print(f"slow jumps:      ON {a[3]}    vs FROZEN {b[3]}")
    print(f"fast noise:      ON {a[4]:.3f} vs FROZEN {b[4]:.3f}   (freezing should NOT change this much)")
    helped = (a[2] > 1.8 * b[2]) or (a[3] >= b[3] + 2)
    if helped:
        print("=> Freezing clearly reduced the SLOW telegraph/drift: the ADC background calibration is (a big part of) it. Fix: freeze during runs.")
    else:
        print("=> Freezing did NOT clearly reduce the slow drift: it is not (mainly) the ADC cal.")
        print("   Next: a true DAC->ADC loopback (cavity out of the loop) or reading well off the resonator,")
        print("   to split readout electronics (clock/PLL) from the resonator itself.")

    try:
        import matplotlib
        matplotlib.use("TkAgg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(2, 1, sharex=True, figsize=(9.5, 7))
        for axi, (t, I, Q, res, title) in zip(ax, [(d["t1"], d["I1"], d["Q1"], a, f"cal ON (slow span {a[2]:.2f})"),
                                                   (d["t2"], d["I2"], d["Q2"], b, f"cal FROZEN (slow span {b[2]:.2f})")]):
            axi.plot(t, I, ".", ms=2, alpha=0.25, color="tab:orange")
            axi.plot(t, Q, ".", ms=2, alpha=0.25, color="tab:blue")
            axi.plot(t, res[0], "-", color="darkorange", lw=2.2, label="I baseline")
            axi.plot(t, res[1], "-", color="navy", lw=2.2, label="Q baseline")
            axi.set_title(title)
            axi.set_ylabel("a.u.")
            axi.legend(fontsize=8)
        ax[1].set_xlabel("time [s]")
        plt.tight_layout()
        out = os.path.join(DL, "cal_freeze_analysis.png")
        plt.savefig(out, dpi=110)
        print("\nsaved", out)
        plt.show()
    except Exception as e:
        print(f"[plot skipped: {type(e).__name__}: {e}]")


if __name__ == "__main__":
    main()
