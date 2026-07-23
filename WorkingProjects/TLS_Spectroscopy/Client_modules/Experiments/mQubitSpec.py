import datetime

import numpy as np
import matplotlib.pyplot as plt
from qick import RAveragerProgram
from scipy.signal import savgol_filter, find_peaks

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import set_readout_pulse


def _robust_scale(x):
    """MAD-based noise scale (x1.4826 -> Gaussian sigma), robust to the real line we keep."""
    x = np.asarray(x, dtype=float)
    mad = np.median(np.abs(x - np.median(x)))
    if mad > 0:
        return 1.4826 * float(mad)
    s = float(np.std(x))
    return s if s > 0 else 1.0


def locate_line(freqs, z, smooth_mhz=6.0, detrend_deg=2, max_candidates=5):
    """Find the qubit line the way the QM two-tone spec effectively does -- but robust to a
    reproducible spike-comb.

    The qubit is a BROAD bump (a strongly driven line is power-broadened over many MHz), while
    the spurious features that litter this readout are 1-2 point spikes.  Two moves separate
    them without erasing the qubit:

      1. GLOBAL low-order polynomial detrend of |S21| (degree 2-3 over the WHOLE span).  Unlike
         a windowed baseline, a single global polynomial cannot bend to follow a localized bump,
         so the qubit survives detrending; it only removes the slow resonator background.
      2. Smooth the detrended trace over ~smooth_mhz (the qubit's width).  A broad bump adds up
         through the smoothing; a 1-2 point spike averages away.  argmax of the smoothed
         deviation is then the qubit, not a spike.

    Returns the detrend baseline, the smoothed deviation, an SNR trace, the best (freq, snr),
    and SNR-ranked (freq, snr) candidates."""
    freqs = np.asarray(freqs, dtype=float)
    z = np.asarray(z, dtype=complex)
    n = freqs.size
    if z.size != n or n < 5:
        raise ValueError("locate_line needs matching freqs/z of length >= 5")
    step = float(np.median(np.abs(np.diff(freqs)))) or 1.0
    mag = np.abs(z)
    x = np.arange(n, dtype=float)
    deg = min(int(detrend_deg), n - 1)
    baseline = np.polyval(np.polyfit(x, mag, deg), x)
    resid = mag - baseline
    sp = max(3, int(round(smooth_mhz / step)))
    if sp % 2 == 0:
        sp += 1
    smoothed = savgol_filter(resid, sp, 1, mode="interp") if sp < n else resid
    noise = max(_robust_scale(smoothed), 1e-15)
    snr = np.abs(smoothed) / noise
    distance = max(1, sp // 2)
    peaks, props = find_peaks(snr, distance=distance, prominence=0.5)
    if peaks.size == 0:
        peaks = np.array([int(np.nanargmax(snr))])
        prom = snr[peaks]
    else:
        prom = props.get("prominences", snr[peaks])
    order = peaks[np.argsort(prom)[::-1]][:max(int(max_candidates), 1)]
    candidates = [(float(freqs[i]), float(snr[i])) for i in order]
    best = candidates[0] if candidates else (float(freqs[int(np.argmax(snr))]), float(np.max(snr)))
    return {"baseline": baseline, "resid": resid, "smoothed": smoothed, "snr": snr,
            "best": best, "candidates": candidates}


class QubitSpecProgram(RAveragerProgram):
    """Saturation-spectroscopy sweep (the QM two-tone spec sequence): a fixed-frequency drive
    tone is stepped across the qubit band on the generator's frequency register, and the
    resonator is read after each drive.  Driven steady state -- no qubit reset between points.
    Read at the resonator dip (cfg['read_pulse_freq']) for the strongest dispersive contrast.
    Default drive is a const tone; set cfg['qubit_pulse_style']='gauss' for a Gaussian."""

    def initialize(self):
        cfg = self.cfg
        self.q_rp = self.ch_page(cfg["qubit_ch"])
        self.r_freq = self.sreg(cfg["qubit_ch"], "freq")
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg.get("mixer_freq", 0), ro_ch=cfg["ro_chs"][0])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        for ro_ch in cfg["ro_chs"]:
            self.declare_readout(ch=ro_ch, freq=cfg["read_pulse_freq"],
                                 length=self.us2cycles(cfg["read_length"], ro_ch=cfg["ro_chs"][0]),
                                 gen_ch=cfg["res_ch"])
        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])
        self.f_start = self.freq2reg(cfg["start"], gen_ch=cfg["qubit_ch"])
        self.f_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])
        style = str(cfg.get("qubit_pulse_style", "const")).lower()
        if style == "gauss":
            sigma = self.us2cycles(float(cfg.get("qubit_sigma", cfg.get("sigma", 0.1))),
                                   gen_ch=cfg["qubit_ch"])
            self.add_gauss(ch=cfg["qubit_ch"], name="qspec", sigma=sigma, length=4 * sigma)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=self.f_start,
                                     phase=0, gain=int(cfg["qubit_gain"]), waveform="qspec")
        else:
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_start,
                                     phase=0, gain=int(cfg["qubit_gain"]),
                                     length=self.us2cycles(cfg["qubit_length"], gen_ch=cfg["qubit_ch"]))
        set_readout_pulse(self, read_freq)
        self.synci(200)

    def body(self):
        cfg = self.cfg
        self.pulse(ch=cfg["qubit_ch"])
        self.sync_all(self.us2cycles(cfg.get("spec_pre_read_us", 0.05)))
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.f_step)


class QubitSpec(ExperimentClass):
    """Qubit spectroscopy, in the spirit of the QM two-tone spec: sweep a saturation tone,
    show I/Q and |S21|, and pick the qubit line.  The line is a BROAD power-broadened bump, so
    detection is a global detrend + smoothing + argmax (see locate_line) -- which keeps the
    broad qubit and ignores the narrow reproducible spikes this readout produces, exactly where
    a windowed-baseline residual failed.  It always shows the data and reports the strongest
    line as self.qubitFreq, tagged with a confidence, and never hides a real feature."""

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data',
                 suffix='Qubit_Spec', cfg=None, meta_dict=None, f_min=None, f_max=None,
                 f_step=None, min_snr=None, n_passes=None, plot=True, save=True, **kw):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, suffix=suffix, cfg=cfg, meta_dict=meta_dict, **kw)
        c = cfg or {}
        self.element = str(path)
        self.f_min = float(f_min)
        self.f_max = float(f_max)
        self.f_step = float(f_step)
        self.f_vec = np.arange(self.f_min, self.f_max, self.f_step)
        self.min_snr = float(c.get("spec_min_snr", 3.0) if min_snr is None else min_snr)
        self.n_passes = int(c.get("spec_passes", 2) if n_passes is None else n_passes)
        self.smooth_mhz = float(c.get("spec_smooth_mhz", 6.0))
        self.detrend_deg = int(c.get("spec_detrend_deg", 2))
        self.plot = bool(plot)
        self.save = bool(save)
        self.qubitFreq = None

    def _run_once(self, cfg, progress):
        prog = QubitSpecProgram(self.soccfg, cfg)
        _x, avgi, avgq = prog.acquire(self.soc, load_pulses=True, progress=progress)
        i = np.asarray(avgi[0][0], dtype=float)
        q = np.asarray(avgq[0][0], dtype=float)
        # optional cavity-winding de-rotation (0 in the default config -> no-op), like the QM code
        wind = (2 * np.pi * float(cfg.get("cavity_winding_freq", 0.0)) * float(cfg["read_pulse_freq"])
                + float(cfg.get("cavity_winding_offset", 0.0)))
        return (i + 1j * q) * np.exp(1j * wind)

    def _locate(self, f, z):
        return locate_line(f, z, smooth_mhz=self.smooth_mhz, detrend_deg=self.detrend_deg)

    def acquire(self, progress=False, plotDisp=False):
        cfg = self.cfg
        cfg["reps"] = int(cfg.get("shots", cfg.get("reps", 1000)))
        cfg["start"] = float(self.f_min)
        cfg["step"] = float(self.f_step)
        cfg["expts"] = int(len(self.f_vec))
        n_passes = max(1, int(self.n_passes))

        traces = [self._run_once(cfg, progress and k == 0) for k in range(n_passes)]
        m = min(t.size for t in traces)
        traces = [t[:m] for t in traces]
        f = self.f_vec[:m]
        z_avg = np.mean(np.vstack(traces), axis=0)

        loc = self._locate(f, z_avg)
        best_f, best_snr = loc["best"]

        # reproducibility -> confidence only (never a gate that hides the line): the smoothed
        # deviation should bump at the same frequency in each pass.
        tol = max(3.0 * self.f_step, 0.5 * self.smooth_mhz)
        reproduced = False
        if n_passes >= 2:
            win = np.abs(f - best_f) <= tol
            per = [self._locate(f, t)["snr"] for t in traces]
            reproduced = bool(win.any() and all(float(np.max(s[win])) >= self.min_snr for s in per))
        confidence = ("high" if best_snr >= self.min_snr and (reproduced or n_passes < 2)
                      else "medium" if best_snr >= self.min_snr else "low")
        self.qubitFreq = float(best_f)

        I, Q = z_avg.real, z_avg.imag
        mag_db = 20.0 * np.log10(np.abs(z_avg) + 1e-12)
        self.data = {
            'meta_dict': dict(cfg), 'f_vec': f, 'I': I, 'Q': Q, 'IQ_magnitude_dBm': mag_db,
            'detrend_smoothed': loc["smoothed"], 'snr_trace': loc["snr"],
            'candidates_mhz': [c[0] for c in loc["candidates"]],
            'candidate_snr': [c[1] for c in loc["candidates"]],
            'qubit_freq_mhz': self.qubitFreq, 'confidence': confidence, 'reproduced': reproduced,
            'n_passes': n_passes, 'min_snr': self.min_snr,
            'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        others = ", ".join(f"{c[0]:.2f}({c[1]:.0f})" for c in loc["candidates"][1:4])
        print(f"[qubit spec] qubit line ~{best_f:.3f} MHz (SNR {best_snr:.1f}, {confidence} "
              f"confidence, {'reproduced' if reproduced else 'single/uncorroborated'} over "
              f"{n_passes} pass(es)) reading at {cfg['read_pulse_freq']:.3f} MHz."
              + (f" other candidates: {others}" if others else ""))

        if self.plot:
            self._plot(f, I, Q, mag_db, loc, best_f, best_snr, confidence, plotDisp)
        if self.save:
            self.pickle_data()
        return {'config': cfg, 'data': self.data}

    def _plot(self, f, I, Q, mag_db, loc, best_f, best_snr, confidence, plotDisp):
        fig, ax = plt.subplots(3, 1, sharex=True, constrained_layout=True, figsize=(7.5, 8))
        ax[0].plot(f, I, ".-", ms=3, lw=0.8, color="tab:orange", label="I")
        ax[0].plot(f, Q, ".-", ms=3, lw=0.8, color="tab:blue", label="Q")
        ax[0].set_ylabel("a.u.")
        ax[0].set_title(f"{self.element} Qubit Spec, gain {self.cfg.get('qubit_gain')}, "
                        f"len {self.cfg.get('qubit_length')} us, {self.data['n_passes']} pass(es)")
        ax[0].legend(loc="best", fontsize=8)
        ax[1].plot(f, mag_db, ".-", ms=3, lw=0.8, color="0.3", label="|S21|")
        base_db = 20.0 * np.log10(np.abs(loc["baseline"]) + 1e-12)
        ax[1].plot(f, base_db, "-", color="tab:red", lw=1.0, alpha=0.6, label="global detrend")
        ax[1].set_ylabel("Transmission (dB)")
        ax[1].legend(loc="best", fontsize=8)
        ax[2].plot(f, loc["snr"], "-", lw=1.1, color="tab:purple", label="smoothed |dev| SNR")
        ax[2].axhline(self.min_snr, color="k", ls=":", lw=1.0, label=f"SNR = {self.min_snr:.0f}")
        for cf, cs in loc["candidates"]:
            ax[2].plot(cf, cs, "v", color="tab:orange", ms=6)
        for a in ax:
            a.axvline(best_f, color="tab:red", ls="--", lw=1.0)
        ax[2].annotate(f"{best_f:.2f} MHz\nSNR {best_snr:.1f} ({confidence})",
                       xy=(best_f, best_snr), xytext=(6, 4), textcoords="offset points",
                       color="tab:red", fontsize=9)
        ax[2].set_ylabel("Detection SNR")
        ax[2].set_xlabel("Qubit frequency (MHz)")
        ax[2].legend(loc="best", fontsize=8)
        plt.savefig(self.iname, bbox_inches="tight")
        if plotDisp:
            plt.show(block=False)
            plt.pause(0.1)
        else:
            plt.close(fig)

    def save_data(self, data=None):
        if data is None:
            data = {'data': self.data}
        print(f'Saving {self.fname}')
        arr = {'f_vec': self.data['f_vec'], 'I': self.data['I'], 'Q': self.data['Q'],
               'IQ_magnitude_dBm': self.data['IQ_magnitude_dBm'], 'snr_trace': self.data['snr_trace']}
        super().save_data(data=arr)
