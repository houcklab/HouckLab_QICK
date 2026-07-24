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
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.save_paths import data_path

RO_CH = 0
ON_FREQ_MHZ = None
OFF_OFFSET_MHZ = 100.0
RUN_MINUTES = 120
DWELL_S = 0.5
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


def _one(prog, soc, first):
    i, q = prog.acquire(soc, load_pulses=first, progress=False)
    return float(np.asarray(i).ravel()[0]) + 1j * float(np.asarray(q).ravel()[0])


def rolling_median(x, w):
    x = np.asarray(x, dtype=float)
    n = x.size
    h = max(1, w // 2)
    return np.array([np.median(x[max(0, i - h):min(n, i + h + 1)]) for i in range(n)])


def jumps(Z, thresh=8.0):
    w = max(7, Z.size // 20)
    sI, sQ = rolling_median(Z.real, w), rolling_median(Z.imag, w)
    step = np.hypot(np.diff(sI), np.diff(sQ))
    sig = 1.4826 * np.median(np.abs(step - np.median(step))) + 1e-12
    idx = np.where(step > thresh * sig)[0]
    return idx, step, sig, (sI + 1j * sQ)


def main():
    soc, soccfg = makeProxy()
    base = dict(BaseConfig)
    base["reps"] = REPS
    base["shots"] = REPS
    base["relax_delay"] = RELAX_US
    on_f = base["read_pulse_freq"] if ON_FREQ_MHZ is None else float(ON_FREQ_MHZ)
    off_f = on_f + OFF_OFFSET_MHZ
    on_cfg = dict(base); on_cfg["read_pulse_freq"] = on_f
    off_cfg = dict(base); off_cfg["read_pulse_freq"] = off_f
    on_prog, off_prog = _ReadProg(soccfg, on_cfg), _ReadProg(soccfg, off_cfg)
    print(f"Interleaved on/off-resonance telegraph run | on {on_f:.3f} MHz, off {off_f:.3f} MHz | "
          f"up to {RUN_MINUTES:.0f} min, saving as it goes. Ctrl-C to stop early and still analyze.")

    dname = data_path("Loopback_interleaved")
    npz = dname + ".npz"
    t, on, off = [], [], []
    t0 = time.time()
    k = 0
    try:
        while (time.time() - t0) < RUN_MINUTES * 60.0:
            on.append(_one(on_prog, soc, k == 0))
            off.append(_one(off_prog, soc, k == 0))
            t.append(time.time() - t0)
            k += 1
            sys.stdout.write(f"\r  {(time.time() - t0) / 60:.1f}/{RUN_MINUTES:.0f} min  ({k} pairs)     ")
            sys.stdout.flush()
            if k % 200 == 0:
                np.savez(npz, t=np.asarray(t), on=np.asarray(on), off=np.asarray(off),
                         on_freq=on_f, off_freq=off_f)
            if DWELL_S:
                time.sleep(DWELL_S)
    except KeyboardInterrupt:
        print("\n[stopped early]")
    sys.stdout.write("\n")

    t = np.asarray(t); on = np.asarray(on); off = np.asarray(off)
    np.savez(npz, t=t, on=on, off=off, on_freq=on_f, off_freq=off_f)
    if on.size < 20:
        print("collected only", on.size, "pairs -- run longer.")
        return

    ion, son, sig_on, bon = jumps(on)
    iof, sof, sig_of, bof = jumps(off)
    print("\n==== RESULT ====")
    print(f"on-resonance : {len(ion)} baseline jumps (|Z| span {np.ptp(np.abs(bon)):.3f})")
    print(f"off-resonance: {len(iof)} baseline jumps (|Z| span {np.ptp(np.abs(bof)):.3f})")
    coincident = sum(1 for j in ion if np.any(np.abs(iof - j) <= 2))
    print(f"of the {len(ion)} on-resonance jumps, {coincident} also appear off-resonance (same time)")
    if len(ion) == 0:
        print("=> no telegraph fired in this window (still intermittent/dormant). Re-run longer, or when a chevron shows the band.")
    elif coincident >= max(1, len(ion) // 2):
        print("=> events show up ON and OFF resonance => the instability is in the RFSoC / RF electronics, NOT the resonator.")
    else:
        print("=> events show up mostly ON resonance only => the RESONATOR is involved (physical).")
    print("raw data:", npz)

    if PLOT:
        try:
            import matplotlib
            matplotlib.use("TkAgg")
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(2, 1, sharex=True, figsize=(10, 6.5))
            ax[0].plot(t, np.abs(on), ".", ms=2, alpha=0.3, color="tab:blue")
            ax[0].plot(t, np.abs(bon), "-", color="navy", lw=1.8)
            ax[0].set_title(f"on-resonance |Z| ({len(ion)} jumps)"); ax[0].set_ylabel("|Z|")
            for j in ion:
                ax[0].axvline(t[j], color="r", lw=0.6, alpha=0.5)
            ax[1].plot(t, np.abs(off), ".", ms=2, alpha=0.3, color="tab:orange")
            ax[1].plot(t, np.abs(bof), "-", color="darkorange", lw=1.8)
            ax[1].set_title(f"off-resonance |Z| ({len(iof)} jumps)"); ax[1].set_ylabel("|Z|"); ax[1].set_xlabel("time [s]")
            for j in iof:
                ax[1].axvline(t[j], color="r", lw=0.6, alpha=0.5)
            plt.tight_layout()
            png = dname + ".png"
            plt.savefig(png, dpi=110); print("saved", png); plt.show()
        except Exception as e:
            print(f"[plot skipped: {type(e).__name__}: {e}]")


if __name__ == "__main__":
    main()
