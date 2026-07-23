import datetime

import numpy as np
import matplotlib.pyplot as plt
from qick import RAveragerProgram
from scipy.signal import savgol_filter, find_peaks

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import set_readout_pulse


def _robust_scale(x):
    """MAD-based noise scale.  Uses the median absolute deviation (x1.4826 -> Gaussian sigma)
    so a few genuine spectral lines do not inflate the noise estimate the way plain std would."""
    x = np.asarray(x, dtype=float)
    med = np.median(x)
    mad = np.median(np.abs(x - med))
    if mad > 0:
        return 1.4826 * float(mad)
    s = float(np.std(x))
    return s if s > 0 else 1.0


def spectral_features(freqs, z, min_prominence=1.0, max_candidates=4):
    """Detect qubit/TLS lines in a COMPLEX spectroscopy trace by distance from a smooth baseline.

    Raw |S21| is dominated by the resonator's slow, frequency-dependent transmission and phase
    background -- the "comb" you see when you just plot magnitude is mostly that ripple plus
    noise.  Here a wide Savitzky-Golay curve models that background on the real and imaginary
    parts separately, and lines are ranked by the complex residual ``|z - baseline|`` turned
    into an SNR trace (residual minus its median, over a MAD noise scale).  Working on the
    complex residual catches the transition whether it appears as a dip, a peak, or a pure
    phase rotation, and the baseline subtraction is what makes a real line stand out of the
    ripple.  Returns the baseline, residual, snr trace, and SNR-ranked (freq, snr) candidates."""
    freqs = np.asarray(freqs, dtype=float)
    z = np.asarray(z, dtype=complex)
    n = freqs.size
    if z.size != n or n < 3:
        raise ValueError("spectral_features needs matching freqs/z of length >= 3")
    if n >= 7:
        # odd window, ~n/4 wide, at least 7 -- wide enough to ignore a narrow line, narrow
        # enough to follow the resonator background.
        window = max(11, 2 * (n // 8) + 1)
        window = min(window, n if n % 2 else n - 1)
        if window % 2 == 0:
            window -= 1
        window = max(window, 7)
        baseline = (savgol_filter(z.real, window, 2, mode="interp")
                    + 1j * savgol_filter(z.imag, window, 2, mode="interp"))
    else:
        baseline = np.linspace(z[0], z[-1], n)
    residual = np.abs(z - baseline)
    floor = float(np.median(residual))
    noise = max(_robust_scale(residual), 1e-15)
    snr = (residual - floor) / noise
    distance = max(1, n // 40)
    peaks, props = find_peaks(snr, distance=distance, prominence=min_prominence)
    if peaks.size == 0:
        peaks = np.array([int(np.nanargmax(snr))])
        prom = snr[peaks]
    else:
        prom = props.get("prominences", snr[peaks])
    order = peaks[np.argsort(prom)[::-1]][:max(int(max_candidates), 1)]
    candidates = [(float(freqs[i]), float(snr[i])) for i in order]
    return {"baseline": baseline, "residual": residual, "snr": snr,
            "candidates": candidates, "best_snr": float(np.nanmax(snr))}


class QubitSpecProgram(RAveragerProgram):
    """Saturation-spectroscopy sweep: a fixed-frequency drive tone is stepped across the qubit
    band on the generator's frequency register, and the resonator is read after each drive.
    This is a driven steady state, so there is deliberately no qubit reset between frequency
    points.  The drive defaults to a long const tone (best for finding a line); set
    cfg['qubit_pulse_style']='gauss' for a pulsed Gaussian (cfg['qubit_sigma'] us)."""

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
        self.sync_all(self.us2cycles(0.02))
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.f_step)


class QubitSpec(ExperimentClass):
    """Robust qubit spectroscopy.

    Sweeps a saturation tone across the qubit band and finds the line by subtracting the
    resonator's smooth baseline and thresholding the residual SNR (see spectral_features),
    instead of eyeballing raw |S21| -- which on this readout is mostly baseline ripple and
    reads as a comb of spurious dips.

    n_passes independent sweeps are run and averaged; with n_passes >= 2 a candidate is only
    accepted if a matching line REPRODUCES in every pass (within ~2.5 freq steps).  Random
    ripple/noise dips do not reproduce, so this is the single most effective rejection of the
    comb; the real transition does.  The best surviving line (SNR >= min_snr) is stored as
    self.qubitFreq (None if nothing clears the bound)."""

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data',
                 suffix='Qubit_Spec', cfg=None, meta_dict=None, f_min=None, f_max=None,
                 f_step=None, min_snr=None, n_passes=None, plot=True, save=True, **kw):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, suffix=suffix, cfg=cfg, meta_dict=meta_dict, **kw)
        self.element = str(path)
        self.f_min = float(f_min)
        self.f_max = float(f_max)
        self.f_step = float(f_step)
        self.f_vec = np.arange(self.f_min, self.f_max, self.f_step)
        self.min_snr = float((cfg or {}).get("spec_min_snr", 4.0) if min_snr is None else min_snr)
        self.n_passes = int((cfg or {}).get("spec_passes", 2) if n_passes is None else n_passes)
        self.plot = bool(plot)
        self.save = bool(save)
        self.qubitFreq = None

    def _run_once(self, cfg, progress):
        prog = QubitSpecProgram(self.soccfg, cfg)
        _x, avgi, avgq = prog.acquire(self.soc, load_pulses=True, progress=progress)
        return np.asarray(avgi[0][0], dtype=float) + 1j * np.asarray(avgq[0][0], dtype=float)

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

        # Rank on the AVERAGED trace: the non-reproducing comb averages toward the baseline
        # while the real line does not, so averaging alone already lifts the qubit above the
        # comb.  Then CONFIRM each averaged-trace candidate by reproducibility -- a real line
        # shows an elevated residual-SNR bump at the SAME frequency in every pass.  We test the
        # per-pass LOCAL SNR near the candidate, NOT its per-pass global rank: a deeper random
        # dip elsewhere in a pass must not be able to bury the real line out of that pass's
        # top-N and get it falsely rejected.
        tol = 2.5 * self.f_step
        feat_avg = spectral_features(f, z_avg, max_candidates=6)
        if n_passes >= 2:
            per_pass = [spectral_features(f, t) for t in traces]
            repro_snr = float(cfg.get("spec_repro_snr", 3.0))
            confirmed = []
            for cf, cs in feat_avg["candidates"]:
                win = np.abs(f - cf) <= tol
                if not win.any():
                    continue
                local = [float(np.max(pf["snr"][win])) for pf in per_pass]
                if all(v >= repro_snr for v in local):
                    # Rank by the AVERAGED-trace SNR: a line present at full depth in every
                    # pass keeps its depth through averaging, while a comb dip in only some
                    # passes is averaged down -- so the real line ranks above a comb overlap
                    # that happened to clear the reproducibility gate.
                    confirmed.append((cf, cs))
        else:
            confirmed = list(feat_avg["candidates"])
        confirmed.sort(key=lambda c: c[1], reverse=True)

        best = confirmed[0] if confirmed and confirmed[0][1] >= self.min_snr else None
        self.qubitFreq = None if best is None else float(best[0])

        mag_db = 20.0 * np.log10(np.abs(z_avg) + 1e-12)
        phase = np.unwrap(np.angle(z_avg))
        self.data = {
            'meta_dict': dict(cfg), 'f_vec': f, 'IQ_magnitude_dBm': mag_db, 'IQ_phase': phase,
            'snr_trace': feat_avg["snr"], 'baseline_mag': np.abs(feat_avg["baseline"]),
            'candidates_mhz': [c[0] for c in confirmed], 'candidate_snr': [c[1] for c in confirmed],
            'qubit_freq_mhz': self.qubitFreq, 'n_passes': n_passes, 'min_snr': self.min_snr,
            'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        if best is None:
            print(f"[qubit spec] no line above SNR {self.min_snr:.1f} in "
                  f"{f[0]:.1f}-{f[-1]:.1f} MHz (best residual SNR {feat_avg['best_snr']:.1f} over "
                  f"{n_passes} pass(es)). Try a longer pulse, lower gain, or a narrower range.")
        else:
            others = ", ".join(f"{c[0]:.2f}({c[1]:.0f})" for c in confirmed[1:4])
            print(f"[qubit spec] qubit line at {best[0]:.3f} MHz (SNR {best[1]:.1f}), reproduced "
                  f"across {n_passes} pass(es)." + (f" other lines: {others}" if others else ""))

        if self.plot:
            self._plot(f, mag_db, phase, feat_avg, confirmed, best, plotDisp)
        if self.save:
            self.pickle_data()
        return {'config': cfg, 'data': self.data}

    def _plot(self, f, mag_db, phase, feat, confirmed, best, plotDisp):
        base_db = 20.0 * np.log10(feat["baseline_mag"] if "baseline_mag" in feat
                                  else np.abs(feat["baseline"]) + 1e-12)
        fig, ax = plt.subplots(3, 1, sharex=True, constrained_layout=True, figsize=(7.5, 8))
        ax[0].plot(f, mag_db, ".-", ms=3, lw=0.8, label="|S21|")
        ax[0].plot(f, base_db, "-", color="0.6", lw=1.2, label="baseline")
        ax[0].set_ylabel("Transmission (dB)")
        ax[0].set_title(f"{self.element} Qubit Spec, gain {self.cfg.get('qubit_gain')}, "
                        f"len {self.cfg.get('qubit_length')} us, {self.data['n_passes']} pass(es)")
        ax[0].legend(loc="best", fontsize=8)
        ax[1].plot(f, phase, ".-", ms=3, lw=0.8, color="tab:green")
        ax[1].set_ylabel("Phase (rad)")
        ax[2].plot(f, feat["snr"], "-", lw=1.0, color="tab:purple", label="residual SNR")
        ax[2].axhline(self.min_snr, color="k", ls=":", lw=1.0, label=f"SNR = {self.min_snr:.0f}")
        for cf, cs in confirmed:
            ax[2].plot(cf, cs, "v", color="tab:orange", ms=7)
        if best is not None:
            for a in ax:
                a.axvline(best[0], color="tab:red", ls="--", lw=1.0)
            ax[2].annotate(f"{best[0]:.2f} MHz\nSNR {best[1]:.1f}", xy=(best[0], best[1]),
                           xytext=(6, 4), textcoords="offset points", color="tab:red", fontsize=9)
        ax[2].set_ylabel("Residual SNR")
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
