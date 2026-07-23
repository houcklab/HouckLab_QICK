import datetime

import numpy as np
import matplotlib.pyplot as plt
from qick import RAveragerProgram
from scipy.signal import savgol_filter, find_peaks

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import set_readout_pulse


def _robust_scale(x):
    """MAD-based noise scale (x1.4826 -> Gaussian sigma).  Robust to the genuine lines we are
    trying to keep, unlike plain std which they would inflate."""
    x = np.asarray(x, dtype=float)
    med = np.median(x)
    mad = np.median(np.abs(x - med))
    if mad > 0:
        return 1.4826 * float(mad)
    s = float(np.std(x))
    return s if s > 0 else 1.0


def spectral_features(freqs, z, baseline_frac=0.5, smooth_mhz=5.0,
                      min_prominence=1.0, max_candidates=6):
    """Detect qubit/TLS lines of ANY width in a COMPLEX spectroscopy trace.

    Raw |S21| is dominated by the resonator's slow transmission/phase background, so a naive
    magnitude plot reads as a comb of spurious dips.  Two stages fix that without erasing the
    signal:

      1. Subtract a WIDE Savitzky-Golay baseline (~baseline_frac of the span) that follows only
         the slow background.  A NARROW baseline is the trap: a strongly driven qubit line is
         power-broadened to many MHz, and a narrow baseline follows and subtracts that broad
         line -- making a real, obvious feature vanish into flat residual.

      2. Matched-filter the complex residual: smooth (z - baseline) over ~smooth_mhz (the
         feature scale) and take its magnitude.  A coherent bump -- broad or narrow -- adds up
         through the smoothing while noise averages down, so a wide power-broadened line and a
         sharp TLS both register as a strong peak.  SNR is that matched-filter magnitude over a
         MAD noise scale.

    Returns the baseline, the matched-filter snr trace, and SNR-ranked (freq, snr) candidates."""
    freqs = np.asarray(freqs, dtype=float)
    z = np.asarray(z, dtype=complex)
    n = freqs.size
    if z.size != n or n < 5:
        raise ValueError("spectral_features needs matching freqs/z of length >= 5")
    step = float(np.median(np.abs(np.diff(freqs)))) or 1.0
    if n >= 7:
        w = max(11, int(baseline_frac * n))
        w = min(w, n if n % 2 else n - 1)
        if w % 2 == 0:
            w -= 1
        w = max(w, 7)
        baseline = (savgol_filter(z.real, w, 2, mode="interp")
                    + 1j * savgol_filter(z.imag, w, 2, mode="interp"))
    else:
        baseline = np.linspace(z[0], z[-1], n)
    resid = z - baseline
    sp = max(1, int(round(smooth_mhz / step)))
    if sp % 2 == 0:
        sp += 1
    if 3 <= sp < n:
        mf = np.abs(savgol_filter(resid.real, sp, 1, mode="interp")
                    + 1j * savgol_filter(resid.imag, sp, 1, mode="interp"))
    else:
        mf = np.abs(resid)
    floor = float(np.median(mf))
    noise = max(_robust_scale(mf), 1e-15)
    snr = (mf - floor) / noise
    distance = max(1, n // 30)
    peaks, props = find_peaks(snr, distance=distance, prominence=min_prominence)
    if peaks.size == 0:
        peaks = np.array([int(np.nanargmax(snr))])
        prom = snr[peaks]
    else:
        prom = props.get("prominences", snr[peaks])
    order = peaks[np.argsort(prom)[::-1]][:max(int(max_candidates), 1)]
    candidates = [(float(freqs[i]), float(snr[i])) for i in order]
    return {"baseline": baseline, "snr": snr, "candidates": candidates,
            "best_snr": float(np.nanmax(snr))}


class QubitSpecProgram(RAveragerProgram):
    """Saturation-spectroscopy sweep: a fixed-frequency drive tone is stepped across the qubit
    band on the generator's frequency register, and the resonator is read after each drive.
    Driven steady state -- no qubit reset between points.  A longer drive (cfg['qubit_length'])
    saturates the transition harder and gives a stronger, cleaner feature.  Default drive is a
    const tone; set cfg['qubit_pulse_style']='gauss' for a pulsed Gaussian (cfg['qubit_sigma'])."""

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
    """Robust qubit spectroscopy.

    Sweeps a saturation tone across the qubit band, then finds the line with a wide-baseline +
    matched-filter detector (see spectral_features) that handles a power-broadened line as well
    as a sharp one -- unlike a raw |S21| plot (reads as a comb) or a narrow-baseline residual
    (erases a broad line).  It ALWAYS shows the data and suggests the strongest line as
    self.qubitFreq, tagged with a confidence from its SNR and whether it reproduces across
    n_passes independent sweeps.  It never silently reports 'nothing' and hides a real feature."""

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
        self.baseline_frac = float(c.get("spec_baseline_frac", 0.5))
        self.smooth_mhz = float(c.get("spec_smooth_mhz", 5.0))
        self.plot = bool(plot)
        self.save = bool(save)
        self.qubitFreq = None

    def _run_once(self, cfg, progress):
        prog = QubitSpecProgram(self.soccfg, cfg)
        _x, avgi, avgq = prog.acquire(self.soc, load_pulses=True, progress=progress)
        return np.asarray(avgi[0][0], dtype=float) + 1j * np.asarray(avgq[0][0], dtype=float)

    def _features(self, f, z):
        return spectral_features(f, z, baseline_frac=self.baseline_frac, smooth_mhz=self.smooth_mhz)

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

        # Detect on the averaged trace (non-reproducing noise averages toward the baseline).
        feat = self._features(f, z_avg)
        candidates = feat["candidates"]

        # Reproducibility as a CONFIDENCE flag, not a gate: a real line shows an elevated
        # matched-filter bump at the SAME frequency in every pass.
        tol = max(2.5 * self.f_step, 0.5 * self.smooth_mhz)
        reproduced = set()
        if n_passes >= 2:
            per_pass = [self._features(f, t) for t in traces]
            repro_snr = float(cfg.get("spec_repro_snr", 3.0))
            for cf, _cs in candidates:
                win = np.abs(f - cf) <= tol
                if win.any() and all(float(np.max(pf["snr"][win])) >= repro_snr for pf in per_pass):
                    reproduced.add(round(cf, 3))

        # Always suggest the strongest line, preferring reproduced ones when any reproduced.
        best = None
        if candidates:
            repro_pool = [c for c in candidates if round(c[0], 3) in reproduced]
            best = max(repro_pool or candidates, key=lambda c: c[1])
        self.qubitFreq = None if best is None else float(best[0])

        mag_db = 20.0 * np.log10(np.abs(z_avg) + 1e-12)
        phase = np.unwrap(np.angle(z_avg))
        best_repro = bool(best is not None and round(best[0], 3) in reproduced)
        confidence = "none"
        if best is not None:
            if best[1] >= self.min_snr and (best_repro or n_passes < 2):
                confidence = "high"
            elif best[1] >= self.min_snr:
                confidence = "medium"
            else:
                confidence = "low"
        self.data = {
            'meta_dict': dict(cfg), 'f_vec': f, 'IQ_magnitude_dBm': mag_db, 'IQ_phase': phase,
            'snr_trace': feat["snr"], 'baseline_mag': np.abs(feat["baseline"]),
            'candidates_mhz': [c[0] for c in candidates], 'candidate_snr': [c[1] for c in candidates],
            'reproduced_mhz': sorted(reproduced), 'qubit_freq_mhz': self.qubitFreq,
            'confidence': confidence, 'n_passes': n_passes, 'min_snr': self.min_snr,
            'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        if best is None:
            print(f"[qubit spec] no candidate peaks in {f[0]:.1f}-{f[-1]:.1f} MHz -- check the plot.")
        else:
            others = ", ".join(f"{c[0]:.2f}({c[1]:.0f})" for c in candidates if c[0] != best[0])
            print(f"[qubit spec] qubit line ~{best[0]:.3f} MHz (matched-filter SNR {best[1]:.1f}, "
                  f"{confidence} confidence, {'reproduced' if best_repro else 'not reproduced'} "
                  f"across {n_passes} pass(es))." + (f" other candidates: {others}" if others else ""))

        if self.plot:
            self._plot(f, mag_db, phase, feat, candidates, reproduced, best, plotDisp)
        if self.save:
            self.pickle_data()
        return {'config': cfg, 'data': self.data}

    def _plot(self, f, mag_db, phase, feat, candidates, reproduced, best, plotDisp):
        base_db = 20.0 * np.log10(np.abs(feat["baseline"]) + 1e-12)
        fig, ax = plt.subplots(3, 1, sharex=True, constrained_layout=True, figsize=(7.5, 8))
        ax[0].plot(f, mag_db, ".-", ms=3, lw=0.8, label="|S21|")
        ax[0].plot(f, base_db, "-", color="0.6", lw=1.2, label="baseline")
        ax[0].set_ylabel("Transmission (dB)")
        ax[0].set_title(f"{self.element} Qubit Spec, gain {self.cfg.get('qubit_gain')}, "
                        f"len {self.cfg.get('qubit_length')} us, {self.data['n_passes']} pass(es)")
        ax[0].legend(loc="best", fontsize=8)
        ax[1].plot(f, phase, ".-", ms=3, lw=0.8, color="tab:green")
        ax[1].set_ylabel("Phase (rad)")
        ax[2].plot(f, feat["snr"], "-", lw=1.1, color="tab:purple", label="matched-filter SNR")
        ax[2].axhline(self.min_snr, color="k", ls=":", lw=1.0, label=f"SNR = {self.min_snr:.0f}")
        for cf, cs in candidates:
            marker = "v" if round(cf, 3) in reproduced else "x"
            ax[2].plot(cf, cs, marker, color="tab:orange", ms=7)
        if best is not None:
            for a in ax:
                a.axvline(best[0], color="tab:red", ls="--", lw=1.0)
            ax[2].annotate(f"{best[0]:.2f} MHz\nSNR {best[1]:.1f} ({self.data['confidence']})",
                           xy=(best[0], best[1]), xytext=(6, 4), textcoords="offset points",
                           color="tab:red", fontsize=9)
        ax[2].set_ylabel("Matched-filter SNR")
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
        arr = {'f_vec': self.data['f_vec'], 'IQ_magnitude_dBm': self.data['IQ_magnitude_dBm'],
               'IQ_phase': self.data['IQ_phase'], 'snr_trace': self.data['snr_trace']}
        super().save_data(data=arr)
