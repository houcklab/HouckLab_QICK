"""
Wideband qubit search -- sweep the ENTIRE drive band and report every frequency where
this qubit responds at all.

Motivation: a PNAX puts the qubit at 5112 MHz, but the RFSoC sees nothing there over a
150 MHz sweep at gains up to 30000, while it DOES respond around 2534 MHz.  Rather than
argue about which frequency should work, measure it: sweep both Nyquist zones and let the
qubit tell us where it responds.

The result distinguishes the live hypotheses:

  response ONLY near 2556 (= 5112/2)
      the drive chain does not deliver ~5 GHz -- a low-pass filter or cable rolloff in
      the qubit line -- and the only coupling is two-photon at half frequency.  Check the
      physical drive line.

  response at BOTH 2556 and 5112
      5112 works after all and the earlier failure was a scan/readout detail.

  response at 5112 only
      the 2534 feature was something else (a TLS, a spurious mode).

  response at NEITHER, but at some third frequency
      that frequency is what the RFSoC is actually coupled to; the PNAX number does not
      apply to this drive path.

  no response anywhere
      the drive line is not connected, or the readout is not reporting state.

Both zones are covered by running two passes: nqz=1 below fs/2 and nqz=2 above, since a
generator has one Nyquist setting per program.  Readout is our verified chain (res_ch,
ro_chs from BaseConfig) parked on the resonator.

    python WorkingProjects/TLS_Spectroscopy/Client_modules/Runners/FindQubit.py
"""

import datetime
import os

import numpy as np
import matplotlib.pyplot as plt

from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mAutoTuner import (
    SpecProgram, TransProgram, _avg_iq, fit_resonance, _noise_sigma, gen_sample_rate)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.acquisition import suppress_stdout

QUBIT = "q4"

# Search band.  Default covers everything the generator can reach in both zones.
F_MIN_MHZ = 1000.0
F_MAX_MHZ = 6800.0
STEP_MHZ = 2.0             # coarse: a strongly driven line is power-broadened
GAINS = (30000, 10000, 3000)   # strongest first; a real line survives as power drops
SHOTS = 200
RELAX_US = 200.0
PROBE_LEN_US = 5.0         # long saturation probe -> sensitive to a weak transition

# Re-find the resonator first so the readout is definitely on the dip.
FIND_RESONATOR = True
RES_SPAN_MHZ = 4.0
RES_POINTS = 81


def _sweep(soc, soccfg, cfg, f0, f1, step, gain, nqz):
    """One RAverager frequency sweep in a single Nyquist zone."""
    n = int(round((f1 - f0) / step)) + 1
    c = dict(cfg)
    c["qubit_nqz"] = int(nqz)
    c["start"], c["step"], c["expts"] = float(f0), float(step), n
    c["spec_gain"], c["spec_len_us"] = int(gain), float(PROBE_LEN_US)
    c["shots"] = c["reps"] = int(SHOTS)
    with suppress_stdout():
        prog = SpecProgram(soccfg, c)
        _x, avgi, avgq = prog.acquire(soc, load_pulses=True, progress=False)
    fs = f0 + step * np.arange(n)
    z = np.asarray(avgi[0][0], float) + 1j * np.asarray(avgq[0][0], float)
    base = np.median(z.real) + 1j * np.median(z.imag)
    return fs, np.abs(z - base)


def _peaks(fs, sig, n_report=6):
    """Report the strongest excursions above the local noise."""
    noise = _noise_sigma(sig)
    med = float(np.median(sig))
    snr = (sig - med) / max(noise, 1e-12)
    out, taken = [], np.zeros(fs.size, dtype=bool)
    for _ in range(n_report):
        cand = np.where(~taken, snr, -np.inf)
        k = int(np.argmax(cand))
        if not np.isfinite(cand[k]) or cand[k] < 4.0:
            break
        out.append((float(fs[k]), float(snr[k])))
        taken |= np.abs(fs - fs[k]) < 20.0     # suppress the same feature
    return out, noise


def main():
    soc, soccfg = makeProxy()
    cfg = dict(BaseConfig)
    cfg["relax_delay"] = RELAX_US
    fs_gen = gen_sample_rate(soccfg, cfg["qubit_ch"])
    print("=" * 78)
    print("WIDEBAND QUBIT SEARCH  %s" % QUBIT)
    print("  qubit gen %d, fs = %s MHz -> zone1 0-%.0f, zone2 %.0f-%.0f"
          % (cfg["qubit_ch"], fs_gen, (fs_gen or 0) / 2, (fs_gen or 0) / 2, fs_gen or 0))
    print("  sweeping %.0f-%.0f MHz in %.1f MHz steps at gains %s"
          % (F_MIN_MHZ, F_MAX_MHZ, STEP_MHZ, GAINS))
    print("=" * 78)

    if FIND_RESONATOR:
        f0 = float(cfg["read_pulse_freq"])
        fr = np.linspace(f0 - RES_SPAN_MHZ / 2, f0 + RES_SPAN_MHZ / 2, RES_POINTS)
        zz = np.empty(fr.size, dtype=complex)
        c = dict(cfg)
        c["shots"] = c["reps"] = 400
        c["prep_gain"] = 0
        for j, f in enumerate(fr):
            c["read_pulse_freq"] = float(f)
            I, Q, _, _ = _avg_iq(type("E", (), {"soc": soc, "soccfg": soccfg})(),
                                 TransProgram, c)
            zz[j] = I + 1j * Q
        rf = fit_resonance(fr, np.abs(zz) ** 2, expected_fwhm=0.3)
        if rf["ok"]:
            cfg["read_pulse_freq"] = round(float(rf["f0"]), 4)
            print("  resonator at %.4f MHz (kappa %.3f, snr %.0f) -- reading there"
                  % (rf["f0"], rf["fwhm"], rf["snr"]))
        else:
            print("  WARNING: resonator not found; reading at the configured %.4f MHz" % f0)

    edge = (fs_gen / 2.0) if fs_gen else 3440.64
    bands = []
    if F_MIN_MHZ < edge:
        bands.append((F_MIN_MHZ, min(F_MAX_MHZ, edge - STEP_MHZ), 1))
    if F_MAX_MHZ > edge:
        bands.append((max(F_MIN_MHZ, edge + STEP_MHZ), F_MAX_MHZ, 2))

    results, allpk = {}, []
    for gain in GAINS:
        for (lo, hi, nqz) in bands:
            print("\n  --- gain %5d, zone %d: %.0f-%.0f MHz ---" % (gain, nqz, lo, hi))
            fsx, sig = _sweep(soc, soccfg, cfg, lo, hi, STEP_MHZ, gain, nqz)
            results[(gain, nqz)] = (fsx, sig)
            pk, noise = _peaks(fsx, sig)
            if not pk:
                print("      nothing above 4 sigma (noise %.3g)" % noise)
            for f, s in pk:
                print("      candidate %9.3f MHz   snr %5.1f" % (f, s))
                allpk.append((gain, nqz, f, s))

    print("\n" + "=" * 78)
    if not allpk:
        print("NO response anywhere in %.0f-%.0f MHz at any gain." % (F_MIN_MHZ, F_MAX_MHZ))
        print("  -> the drive is not reaching the qubit, or the readout is not")
        print("     reporting state. Check the qubit drive line wiring end to end.")
    else:
        print("CANDIDATES (persisting across gains = real):")
        seen = {}
        for g, z, f, s in allpk:
            key = round(f / 20.0)
            seen.setdefault(key, []).append((g, f, s))
        for key in sorted(seen):
            hits = seen[key]
            fmean = float(np.mean([h[1] for h in hits]))
            gains_hit = sorted({h[0] for h in hits})
            print("   %9.3f MHz   seen at gains %s   max snr %.1f%s"
                  % (fmean, gains_hit, max(h[2] for h in hits),
                     "   <-- persists across power" if len(gains_hit) > 1 else ""))
        halves = [f for _, _, f, _ in allpk]
        for f in halves:
            for f2 in halves:
                if abs(f2 - 2 * f) < 30.0:
                    print("   NOTE: %.1f is ~half of %.1f -- consistent with two-photon "
                          "driving at half frequency" % (f, f2))
    print("=" * 78)

    fig, axs = plt.subplots(len(GAINS), 1, figsize=(13, 3.2 * len(GAINS)), sharex=True)
    axs = np.atleast_1d(axs)
    for ax, gain in zip(axs, GAINS):
        for (lo, hi, nqz) in bands:
            fsx, sig = results[(gain, nqz)]
            ax.plot(fsx, sig, lw=0.7, label="zone %d" % nqz)
        ax.axvline(5112.0, color="r", ls="--", lw=0.9, label="PNAX 5112")
        ax.axvline(2556.0, color="g", ls=":", lw=0.9, label="5112/2")
        ax.set_ylabel("|IQ - baseline|")
        ax.set_title("qubit drive gain %d" % gain, fontsize=9)
        ax.legend(fontsize=7)
    axs[-1].set_xlabel("drive frequency (MHz)")
    fig.suptitle("Wideband qubit search  %s  %s" % (QUBIT, datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
    fig.tight_layout()
    d = os.path.join(outerFolder, QUBIT)
    os.makedirs(d, exist_ok=True)
    png = os.path.join(d, "%s_FindQubit_%s.png" % (QUBIT, datetime.datetime.now().strftime("%Y%m%d_%H%M%S")))
    plt.savefig(png, dpi=140, bbox_inches="tight")
    print("plot: %s" % png)
    np.savez(png.replace(".png", ".npz"),
             **{"g%d_z%d_%s" % (g, z, k): v for (g, z), (fsx, sig) in results.items()
                for k, v in (("f", fsx), ("sig", sig))})
    print("data: %s" % png.replace(".png", ".npz"))


if __name__ == "__main__":
    main()
