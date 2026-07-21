"""
Automatic pi-pulse tuner -- run once, get a calibrated pi (freq + gain) and an updated
BaseConfig.  Staged pipeline modeled on the production calibration suites (Qiskit
Experiments' RoughAmplitude / RamseyXY+FrequencyCal / FineAmplitude, Zurich LabOne Q,
arXiv:2212.01077):

  0. resonator   coarse+fine transmission scan -> Lorentzian fit      -> read_pulse_freq
  1. spec        hardware qubit-freq sweep (2-pass, low power pass 2) -> qubit_freq
  2. rough Rabi  hardware gain sweep, anchored-cosine fit             -> rough pi gain
  3. fine freq   RamseyXY (X/Y quadrature pair, virtual detuning),
                 HARDWARE-CALIBRATED sign convention (probe or persisted), iterated
                                                                      -> qubit_pi_freq
  4. fine amp    error amplification: sx + [pi]^N ping-pong,
                 P(N) = base + (amp/2)(-1)^N sin(N*dtheta + eps), iterated to
                 |dtheta| < tol; correction A -> A*pi/(pi+dtheta)     -> qubit_pi_gain
  5. verify      SNR + 2pi + sx populations + mini error-amp check    -> go/no-go

Design decisions driven by this board's observed behavior:
  * NO single-shot discrimination anywhere.  Every population is the projection of the
    averaged IQ onto the |g>->|e> axis measured from reference points (|g> = no pulse,
    |e> = current-best pi) taken immediately before AND after each data batch -- the
    drift-robust normalization production pipelines use (readout here drifted 2x between
    runs; single-shot separation is marginal).
  * NO trusted sign conventions.  The Ramsey detuning sign is measured on the hardware
    (deliberate +0.25 MHz drive offset -> which way does the fringe move?), persisted in
    the calibration history, and every fine stage re-measures after applying its
    correction, so an error that grew instead of shrank fails loudly.
  * qick 0.2.133 facts (verified against source): AveragerProgram.acquire returns a
    2-tuple (avg_di, avg_dq) indexed [ch][readout]; RAveragerProgram.acquire returns
    (xpts, avgi, avgq) indexed [ch][readout][expt]; there is NO get_raw() -- per-shot
    data is di_buf/dq_buf, shape (n_ro, reps*reads).
  * All frequencies MHz floats (never Hz ints -- Windows int32 trap), gains DAC ints,
    times us.  Prints ASCII-only (PowerShell code pages).

This tuner is PARK-ONLY (ff_gain = 0, the native flux point) -- the same operating
point as the QUA gate calibration's YOKO=0.  It never plays a flux pulse.
"""

import datetime

import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit

from qick import AveragerProgram, RAveragerProgram

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.acquisition import suppress_stdout


# ======================================================================================
# Pure fit functions (numpy/scipy only -- importable and testable without a board)
# ======================================================================================

def lorentzian(f, f0, fwhm, a, off):
    return off + a / (1.0 + ((f - f0) / (fwhm / 2.0)) ** 2)


def _mad(x):
    x = np.asarray(x, dtype=float)
    return float(np.median(np.abs(x - np.median(x)))) + 1e-15


def _smooth(y, w=7):
    """Centered moving average (no scipy.signal dependency), window forced odd."""
    y = np.asarray(y, dtype=float)
    if y.size < w + 2:
        return y.copy()
    w = int(w) | 1
    k = np.ones(w) / w
    pad = np.concatenate([y[:w // 2][::-1], y, y[-(w // 2):][::-1]])
    return np.convolve(pad, k, mode="valid")


def fit_resonance(freqs, mag, polarity=None):
    """Find a resonance in a magnitude trace.  polarity: 'dip'/'peak'/None (auto).
    Returns dict(ok, f0, fwhm, depth, snr, polarity, yfit)."""
    freqs = np.asarray(freqs, dtype=float)
    mag = np.asarray(mag, dtype=float)
    sm = _smooth(mag)
    med = float(np.median(sm))
    if polarity is None:
        polarity = "dip" if (med - sm.min()) >= (sm.max() - med) else "peak"
    sgn = -1.0 if polarity == "dip" else 1.0
    dev = sgn * (sm - med)                       # resonance is a positive bump in dev
    i0 = int(np.argmax(dev))
    depth = float(dev[i0])
    # FWHM estimate from half-depth crossings around the extremum
    half = depth / 2.0
    lo = i0
    while lo > 0 and dev[lo] > half:
        lo -= 1
    hi = i0
    while hi < dev.size - 1 and dev[hi] > half:
        hi += 1
    fwhm0 = max(abs(freqs[hi] - freqs[lo]), 2.0 * abs(freqs[1] - freqs[0]))
    try:
        popt, _ = curve_fit(lorentzian, freqs, mag,
                            p0=[freqs[i0], fwhm0, sgn * depth, med], maxfev=20000)
        f0, fwhm, a, off = popt
        yfit = lorentzian(freqs, *popt)
        ok = (freqs.min() <= f0 <= freqs.max()) and (np.sign(a) == np.sign(sgn * depth) or depth == 0)
    except Exception:
        # parabola through 3 points around the extremum
        yfit = sm
        if 0 < i0 < freqs.size - 1:
            x3, y3 = freqs[i0 - 1:i0 + 2], dev[i0 - 1:i0 + 2]
            den = (x3[0] - x3[1]) * (x3[0] - x3[2]) * (x3[1] - x3[2])
            A = (x3[2] * (y3[1] - y3[0]) + x3[1] * (y3[0] - y3[2]) + x3[0] * (y3[2] - y3[1])) / den
            B = (x3[2] ** 2 * (y3[0] - y3[1]) + x3[1] ** 2 * (y3[2] - y3[0]) + x3[0] ** 2 * (y3[1] - y3[2])) / den
            f0 = -B / (2 * A) if A != 0 else freqs[i0]
        else:
            f0 = freqs[i0]
        fwhm, ok = fwhm0, True
    resid = mag - (yfit if isinstance(yfit, np.ndarray) and yfit.shape == mag.shape else sm)
    snr = depth / (_mad(resid) * 1.4826)
    ok = bool(ok and snr > 5.0)
    return {"ok": ok, "f0": float(f0), "fwhm": float(abs(fwhm)), "depth": depth,
            "snr": float(snr), "polarity": polarity, "yfit": np.asarray(yfit, dtype=float)}


def principal_projection(I, Q):
    """Project an IQ trace onto its principal axis (the |g>-|e> line for a Rabi trace).
    Returns (signal, unit_vector) with the trace mean subtracted."""
    I = np.asarray(I, dtype=float)
    Q = np.asarray(Q, dtype=float)
    di, dq = I - I.mean(), Q - Q.mean()
    cov = np.array([[np.dot(di, di), np.dot(di, dq)], [np.dot(di, dq), np.dot(dq, dq)]])
    w, v = np.linalg.eigh(cov)
    u = v[:, int(np.argmax(w))]
    return di * u[0] + dq * u[1], u


def _rabi_model(g, B, C, c):
    # Anchored cosine: at g=0 the qubit is in |g>, so the signal must be at an extremum
    # of the oscillation (no free phase -- Qiskit locks the equivalent phase the same way).
    return B + C * np.cos(c * g)


def fit_rabi(gains, sig):
    """Fit sig(g) = B + C cos(c g); pi gain = pi/c (first half-period from g=0).
    Returns dict(ok, pi_gain, period, r2, contrast, yfit)."""
    gains = np.asarray(gains, dtype=float)
    sig = np.asarray(sig, dtype=float)
    span = gains.max() - gains.min()
    y = sig - sig.mean()
    # FFT seed for the oscillation frequency over the (uniform) gain grid
    n = gains.size
    fft = np.fft.rfft(y * np.hanning(n))
    fax = np.fft.rfftfreq(n, d=(gains[1] - gains[0]))
    k = 1 + int(np.argmax(np.abs(fft[1:])))
    c_seed = 2.0 * np.pi * max(fax[k], 0.25 / span)
    best = None
    for mult in (0.5, 0.75, 1.0, 1.5, 2.0):
        try:
            popt, _ = curve_fit(_rabi_model, gains, sig,
                                p0=[sig.mean(), (sig.max() - sig.min()) / 2.0, c_seed * mult],
                                maxfev=20000)
            r = sig - _rabi_model(gains, *popt)
            sse = float(np.dot(r, r))
            if best is None or sse < best[0]:
                best = (sse, popt)
        except Exception:
            continue
    if best is None:
        i0 = int(np.argmax(np.abs(sig - sig[0])))
        return {"ok": False, "pi_gain": float(gains[i0]), "period": np.nan, "r2": 0.0,
                "contrast": float(np.ptp(sig)), "yfit": np.full_like(sig, sig.mean())}
    _, (B, C, c) = best
    c = abs(float(c))
    pi_gain = np.pi / c
    yfit = _rabi_model(gains, B, C, c)
    ss_res = float(np.sum((sig - yfit) ** 2))
    ss_tot = float(np.sum((sig - sig.mean()) ** 2)) + 1e-15
    r2 = 1.0 - ss_res / ss_tot
    ok = (0.05 * span <= pi_gain <= 0.95 * (gains.max())) and r2 > 0.7
    return {"ok": bool(ok), "pi_gain": float(pi_gain), "period": float(2 * np.pi / c),
            "r2": float(r2), "contrast": float(2 * abs(C)), "yfit": yfit}


def fit_ramsey_xy(t_us, pop_x, pop_y):
    """Joint fit of the RamseyXY quadrature pair:
        X = base + amp exp(-t/tau) cos(2 pi f t + phi)
        Y = base + amp exp(-t/tau) sin(2 pi f t + phi)
    f is SIGNED (that is the whole point of taking both quadratures).  Seeded from the
    FFT of the complex signal (X-base) + i(Y-base), whose peak frequency is signed.
    Returns dict(ok, f_mhz, t2_us, amp, base, phi, xfit, yfit)."""
    t = np.asarray(t_us, dtype=float)
    X = np.asarray(pop_x, dtype=float)
    Y = np.asarray(pop_y, dtype=float)
    base0 = float((X.mean() + Y.mean()) / 2.0)
    z = (X - base0) + 1j * (Y - base0)
    dt = float(np.mean(np.diff(t)))
    fft = np.fft.fft(z * np.hanning(t.size))
    fax = np.fft.fftfreq(t.size, d=dt)
    k = int(np.argmax(np.abs(fft)))
    f_seed = float(fax[k])
    nyq = 0.5 / dt

    def model(tt, amp, tau, f, phi, base):
        env = amp * np.exp(-tt / tau)
        return np.concatenate([base + env * np.cos(2 * np.pi * f * tt + phi),
                               base + env * np.sin(2 * np.pi * f * tt + phi)])

    yy = np.concatenate([X, Y])
    best = None
    for fs in (f_seed, -f_seed):
        for tau0 in (t.max(), t.max() / 3.0):
            try:
                popt, pcov = curve_fit(
                    model, t, yy,
                    p0=[max(np.ptp(X), np.ptp(Y)) / 2.0, tau0, fs, 0.0, base0],
                    bounds=([0.0, dt, -nyq, -np.pi, -1.0],
                            [2.0, 200.0 * t.max(), nyq, np.pi, 2.0]),
                    maxfev=20000)
                r = yy - model(t, *popt)
                sse = float(np.dot(r, r))
                if best is None or sse < best[0]:
                    best = (sse, popt, pcov)
            except Exception:
                continue
    if best is None:
        return {"ok": False, "f_mhz": np.nan, "t2_us": np.nan, "amp": 0.0,
                "base": base0, "phi": 0.0, "xfit": np.zeros_like(X), "yfit": np.zeros_like(Y)}
    _, (amp, tau, f, phi, base), _ = best
    fit = model(t, amp, tau, f, phi, base)
    resid_sd = float(np.std(yy - fit))
    ok = amp > 4.0 * max(resid_sd, 1e-6) and amp > 0.05
    return {"ok": bool(ok), "f_mhz": float(f), "t2_us": float(tau), "amp": float(amp),
            "base": float(base), "phi": float(phi),
            "xfit": fit[:t.size], "yfit": fit[t.size:]}


def fit_decay_cosine(t, y):
    """A exp(-t/tau) cos(2 pi f t + phi) + base, with f >= 0 (UNSIGNED).  Used by the
    classic drive-detuned Ramsey, which has no quadrature partner to sign the frequency.
    Returns dict(ok, f_mhz, t2_us, amp, yfit)."""
    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)
    base0 = float(np.mean(y))
    dt = float(np.mean(np.diff(t)))
    nyq = 0.5 / dt
    n = t.size
    fft = np.fft.rfft((y - base0) * np.hanning(n))
    fax = np.fft.rfftfreq(n, d=dt)
    k = 1 + int(np.argmax(np.abs(fft[1:]))) if n > 3 else 1
    f_seed = float(fax[min(k, fax.size - 1)])

    def model(tt, amp, tau, f, phi, base):
        return base + amp * np.exp(-tt / tau) * np.cos(2 * np.pi * f * tt + phi)

    best = None
    for tau0 in (t.max(), t.max() / 3.0):
        for phi0 in (0.0, np.pi / 2, np.pi):
            try:
                popt, _ = curve_fit(
                    model, t, y,
                    p0=[max(np.ptp(y) / 2.0, 1e-3), tau0, max(f_seed, 0.05), phi0, base0],
                    bounds=([0.0, dt, 0.0, -np.pi, -1.0],
                            [2.0, 200.0 * t.max(), nyq, np.pi, 2.0]), maxfev=20000)
                r = y - model(t, *popt)
                sse = float(np.dot(r, r))
                if best is None or sse < best[0]:
                    best = (sse, popt)
            except Exception:
                continue
    if best is None:
        return {"ok": False, "f_mhz": np.nan, "t2_us": np.nan, "amp": 0.0,
                "yfit": np.zeros_like(y)}
    _, (amp, tau, f, phi, base) = best
    yfit = model(t, amp, tau, f, phi, base)
    resid = float(np.std(y - yfit))
    return {"ok": bool(amp > 4.0 * max(resid, 1e-6) and amp > 0.10),
            "f_mhz": float(abs(f)), "t2_us": float(tau), "amp": float(amp), "yfit": yfit}


def _ea_model(N, base, amp, dth, eps):
    N = np.asarray(N, dtype=float)
    return base + 0.5 * amp * ((-1.0) ** N) * np.sin(N * dth + eps)


def fit_error_amp(N, pop):
    """Ping-pong fit (Qiskit ErrorAmplificationAnalysis for the pi case, plus a free
    lead-pulse phase eps since our sx is just half-gain and not separately calibrated):
        P(N) = base + (amp/2) (-1)^N sin(N dtheta + eps)
    The populations are reference-normalized, so amp is PHYSICALLY ~1; bounding it to
    [0.3, 1.6] removes the tiny-amp degeneracy that would otherwise let (dtheta, eps)
    wander when the pattern is nearly flat (i.e. exactly when the pi is nearly right).
    Grid seed over (dtheta, eps) at fixed amp=1, then bounded curve_fit refinement.
    Returns dict(ok, d_theta, sigma, eps, amp, base, yfit)."""
    N = np.asarray(N, dtype=float)
    pop = np.asarray(pop, dtype=float)
    best = None
    for dth in np.linspace(-0.6, 0.6, 241):
        for eps in np.linspace(-0.3, 0.3, 13):
            x = 0.5 * ((-1.0) ** N) * np.sin(N * dth + eps)     # amp fixed at 1
            base = float(np.mean(pop - x))
            sse = float(np.sum((pop - base - x) ** 2))
            if best is None or sse < best[0]:
                best = (sse, dth, eps, base)
    _, dth0, eps0, base0 = best
    try:
        popt, pcov = curve_fit(
            _ea_model, N, pop,
            p0=[float(np.clip(base0, 0.0, 1.0)), 1.0, dth0, eps0],
            bounds=([0.0, 0.3, -0.8 * np.pi, -0.35], [1.0, 1.6, 0.8 * np.pi, 0.35]),
            maxfev=20000)
        base, amp, dth, eps = popt
        sigma = float(np.sqrt(max(pcov[2, 2], 0.0)))
    except Exception:
        base, amp, dth, eps = base0, 1.0, dth0, eps0
        sigma = 0.05
    yfit = _ea_model(N, base, amp, dth, eps)
    resid_sd = float(np.std(pop - yfit))
    # a FLAT pattern is valid data (a converged pi); reject only when the residual
    # scatter says the populations themselves are garbage
    ok = amp > 4.0 * max(resid_sd, 1e-6)
    return {"ok": bool(ok), "d_theta": float(dth), "sigma": sigma, "eps": float(eps),
            "amp": float(amp), "base": float(base), "yfit": yfit}


def iq_to_pop(I, Q, g_ref, e_ref):
    """Projection of averaged IQ onto the |g>->|e> axis: 0 = |g>, 1 = |e>."""
    gI, gQ = g_ref
    eI, eQ = e_ref
    dx, dy = eI - gI, eQ - gQ
    denom = dx * dx + dy * dy
    if denom <= 0:
        return np.full(np.shape(I), np.nan)
    return ((np.asarray(I, dtype=float) - gI) * dx + (np.asarray(Q, dtype=float) - gQ) * dy) / denom


# ======================================================================================
# tProc programs (qick 0.2.133, tProc v1) -- lean, park-only, no flux machinery
# ======================================================================================

def _declare_common(prog, include_qubit=True):
    """Shared initialize boilerplate (mirrors this repo's working programs verbatim)."""
    cfg = prog.cfg
    prog.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                     mixer_freq=cfg.get("mixer_freq", 0), ro_ch=cfg["ro_chs"][0])
    if include_qubit:
        prog.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
    for ro_ch in cfg["ro_chs"]:
        prog.declare_readout(ch=ro_ch, freq=cfg["read_pulse_freq"],
                             length=prog.us2cycles(cfg["read_length"], ro_ch=cfg["ro_chs"][0]),
                             gen_ch=cfg["res_ch"])
    read_freq = prog.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])
    prog.set_pulse_registers(ch=cfg["res_ch"], style=cfg.get("read_pulse_style", "const"),
                             freq=read_freq, phase=0, gain=cfg["read_pulse_gain"],
                             length=prog.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]))
    return read_freq


class TunerTransProgram(AveragerProgram):
    """Readout-only transmission point at cfg['read_pulse_freq'] (Python freq loop)."""

    def initialize(self):
        cfg = self.cfg
        cfg.setdefault("reps", int(cfg.get("shots", 300)))
        _declare_common(self, include_qubit=False)
        self.synci(200)

    def body(self):
        cfg = self.cfg
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(cfg["relax_delay"]))


class TunerSpecProgram(RAveragerProgram):
    """Hardware qubit-frequency sweep: const saturation probe then readout.
    cfg: start/step (MHz), expts, reps, spec_gain (DAC), spec_len_us."""

    def initialize(self):
        cfg = self.cfg
        self.q_rp = self.ch_page(cfg["qubit_ch"])
        self.r_freq = self.sreg(cfg["qubit_ch"], "freq")
        _declare_common(self, include_qubit=True)
        self.f_start = self.freq2reg(cfg["start"], gen_ch=cfg["qubit_ch"])
        self.f_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_start,
                                 phase=0, gain=int(cfg["spec_gain"]),
                                 length=self.us2cycles(cfg["spec_len_us"], gen_ch=cfg["qubit_ch"]))
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


class TunerRabiProgram(RAveragerProgram):
    """Hardware gain sweep of the gaussian drive at fixed cfg['drive_freq'] (MHz).
    cfg: start/step (DAC), expts, reps."""

    def initialize(self):
        cfg = self.cfg
        self.q_rp = self.ch_page(cfg["qubit_ch"])
        self.r_gain = self.sreg(cfg["qubit_ch"], "gain")
        _declare_common(self, include_qubit=True)
        drive_freq = self.freq2reg(float(cfg["drive_freq"]), gen_ch=cfg["qubit_ch"])
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                       sigma=self.us2cycles(cfg["sigma"]), length=self.us2cycles(cfg["sigma"]) * 4)
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=drive_freq,
                                 phase=self.deg2reg(0, gen_ch=cfg["qubit_ch"]),
                                 gain=int(cfg["start"]), waveform="qubit")
        self.synci(200)

    def body(self):
        cfg = self.cfg
        self.pulse(ch=cfg["qubit_ch"])
        self.sync_all(self.us2cycles(0.01))
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_gain, self.r_gain, '+', self.cfg["step"])


class TunerSeqProgram(AveragerProgram):
    """Generic pulse-sequence program: cfg['seq'] is a list of ops,
        ("pulse", gain_dac, phase_deg)  -- gaussian drive pulse at cfg['drive_freq']
        ("delay", t_us)                 -- idle
    followed by one readout.  Covers refs, Ramsey, error amplification, 2pi checks.
    set_pulse_registers is only re-emitted when (gain, phase) changes, so N repeated
    pi pulses cost 2 instructions each (well within the 8192-word program memory)."""

    def initialize(self):
        cfg = self.cfg
        cfg.setdefault("reps", int(cfg.get("shots", 400)))
        _declare_common(self, include_qubit=True)
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                       sigma=self.us2cycles(cfg["sigma"]), length=self.us2cycles(cfg["sigma"]) * 4)
        self.synci(200)

    def body(self):
        cfg = self.cfg
        qch = cfg["qubit_ch"]
        freq_reg = self.freq2reg(float(cfg["drive_freq"]), gen_ch=qch)
        gap = self.us2cycles(float(cfg.get("seq_gap_us", 0.01)))
        last = None
        for op in cfg["seq"]:
            if op[0] == "pulse":
                gain, ph = int(op[1]), float(op[2])
                if (gain, ph) != last:
                    self.set_pulse_registers(ch=qch, style="arb", freq=freq_reg,
                                             phase=self.deg2reg(ph, gen_ch=qch),
                                             gain=gain, waveform="qubit")
                    last = (gain, ph)
                self.pulse(ch=qch)
                self.sync_all(gap)
            elif op[0] == "delay":
                self.sync_all(self.us2cycles(float(op[1])))
            else:
                raise ValueError("unknown seq op: %r" % (op,))
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(cfg["relax_delay"]))


# ======================================================================================
# Host-side acquisition helpers
# ======================================================================================

class TunerStageError(RuntimeError):
    """A stage failed its acceptance criteria; the pipeline stops and writes nothing."""


def _acquire_avg(exp, prog_cls, cfg):
    """Run an AveragerProgram, return (I, Q, seI, seQ): rep-averaged IQ (per-sample
    units, as the repo convention) + standard errors of the mean from di_buf/dq_buf."""
    with suppress_stdout():
        prog = prog_cls(exp.soccfg, cfg)
        avgi, avgq = prog.acquire(exp.soc, load_pulses=True, progress=False)
    I = float(np.asarray(avgi)[0][0])
    Q = float(np.asarray(avgq)[0][0])
    length = prog.us2cycles(cfg["read_length"], ro_ch=cfg["ro_chs"][0])
    reps = int(cfg["reps"])
    try:
        ish = np.asarray(prog.di_buf)[0][:reps] / length
        qsh = np.asarray(prog.dq_buf)[0][:reps] / length
        seI = float(np.std(ish, ddof=1) / np.sqrt(reps))
        seQ = float(np.std(qsh, ddof=1) / np.sqrt(reps))
    except Exception:
        seI = seQ = np.nan
    return I, Q, seI, seQ


def _acquire_sweep(exp, prog_cls, cfg):
    """Run an RAveragerProgram, return (avgi_trace, avgq_trace) each shape (expts,)."""
    with suppress_stdout():
        prog = prog_cls(exp.soccfg, cfg)
        _x, avgi, avgq = prog.acquire(exp.soc, load_pulses=True, progress=False)
    return np.asarray(avgi[0][0], dtype=float), np.asarray(avgq[0][0], dtype=float)


def _run_seq(exp, cfg, seq, drive_freq, shots):
    c = dict(cfg)
    c["seq"] = list(seq)
    c["drive_freq"] = float(drive_freq)
    c["shots"] = int(shots)
    c["reps"] = int(shots)
    return _acquire_avg(exp, TunerSeqProgram, c)


def _measure_refs(exp, cfg, drive_freq, pi_gain, shots):
    """|g> (no pulse) and |e> (current-best pi) reference IQ points."""
    Ig, Qg, seIg, seQg = _run_seq(exp, cfg, [], drive_freq, shots)
    Ie, Qe, seIe, seQe = _run_seq(exp, cfg, [("pulse", int(pi_gain), 0.0)], drive_freq, shots)
    sep = float(np.hypot(Ie - Ig, Qe - Qg))
    se = float(np.nanmean([seIg, seQg, seIe, seQe]))
    return {"g": (Ig, Qg), "e": (Ie, Qe), "sep": sep, "se": se}


def _combine_refs(pre, post, report, stage):
    """Average the pre/post-batch references; warn if the readout drifted mid-batch."""
    g = ((pre["g"][0] + post["g"][0]) / 2.0, (pre["g"][1] + post["g"][1]) / 2.0)
    e = ((pre["e"][0] + post["e"][0]) / 2.0, (pre["e"][1] + post["e"][1]) / 2.0)
    if pre["sep"] > 0:
        drift = abs(post["sep"] - pre["sep"]) / pre["sep"]
        if drift > 0.3:
            report(stage, "WARN", "readout refs drifted %.0f%% during the batch "
                                  "(sep %.4g -> %.4g); populations are less reliable"
                   % (100 * drift, pre["sep"], post["sep"]))
    return g, e


# ======================================================================================
# The tuner
# ======================================================================================

# Per-stage defaults; the runner can override any of these via params={...}.
DEFAULT_PARAMS = {
    "resonator": {"run": True, "span_mhz": 3.0, "coarse_points": 61, "fine_span_mhz": 0.8,
                  "fine_points": 41, "shots": 300, "relax_delay_us": 10.0,
                  "max_span_mhz": 60.0},      # widest auto-escalated search window
    "spec": {"run": True, "span_mhz": 12.0, "points": 121, "shots": 500,
             "spec_gain": None,          # None -> BaseConfig['qubit_gain']
             "spec_len_us": None,        # None -> BaseConfig['qubit_length']
             "two_pass": True, "relax_delay_us": 1000.0,
             "max_span_mhz": 150.0},     # widest auto-escalated search window
    "rabi": {"gain_max": 30000, "points": 61, "shots": 400, "relax_delay_us": None},
    "ramsey": {"f_virt_mhz": 1.0, "tau_max_us": 4.0, "points": 31, "shots": 500,
               "rounds": 3, "tol_mhz": 0.02, "sign": None,  # None -> history else probe
               "probe_offset_mhz": 0.25, "relax_delay_us": None,
               # fallback used when the virtual-Z phase check fails: drive-detuned
               # Ramsey at +/- this offset (must exceed the residual detuning)
               "classic_offset_mhz": 1.0},
    "fine_amp": {"n_max": 14, "shots": 700, "rounds": 4, "tol_rad": 0.010,
                 "relax_delay_us": None},
    "verify": {"shots": 1000, "snr_min": 4.0, "relax_delay_us": None},
}


def _merged_params(user):
    p = {}
    for stage, d in DEFAULT_PARAMS.items():
        p[stage] = dict(d)
        if user and stage in user:
            p[stage].update(user[stage])
    return p


class AutoPiTuner(ExperimentClass):
    """Run-once automatic pi-pulse tuner.  acquire() runs the staged pipeline and
    returns {'config': cfg, 'data': self.data}; self.data['success'] says whether the
    tuned values are trustworthy and self.data['tuned'] holds them.  This class only
    MEASURES -- writing BaseConfig is the runner's job (Helpers/config_updater)."""

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data',
                 suffix='Auto_Pi_Tune', cfg=None, meta_dict=None, params=None,
                 ramsey_sign_hint=None, **kw):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, suffix=suffix, cfg=cfg, meta_dict=meta_dict, **kw)
        self.element = str(path)
        self.P = _merged_params(params)
        self.ramsey_sign_hint = ramsey_sign_hint     # +1/-1 from history, or None
        self.report_lines = []

    # ---------------- reporting ----------------
    def _report(self, stage, status, msg):
        line = "[%s] %-4s %s" % (stage, status, msg)
        self.report_lines.append(line)
        print("  " + line)

    def _stage_cfg(self, relax_override=None):
        c = dict(self.cfg)
        if relax_override is not None:
            c["relax_delay"] = float(relax_override)
        return c

    # ---------------- stage 0: resonator ----------------
    def _stage_resonator(self, w):
        P = self.P["resonator"]
        cfg = self._stage_cfg(P["relax_delay_us"])
        cfg["shots"] = cfg["reps"] = int(P["shots"])
        base_gain = int(cfg["read_pulse_gain"])
        f0 = float(w["read_pulse_freq"])

        def scan(center, span, npts, gain):
            cfg["read_pulse_gain"] = int(gain)
            freqs = np.linspace(center - span / 2.0, center + span / 2.0, int(npts))
            z = np.empty(freqs.size, dtype=complex)
            for j, f in enumerate(freqs):
                cfg["read_pulse_freq"] = float(f)
                I, Q, _, _ = _acquire_avg(self, TunerTransProgram, cfg)
                z[j] = I + 1j * Q
            return freqs, z

        # Escalating search.  A resonator that has drifted needs a WIDER window; one that
        # is being over-driven has no dip at all until the power comes down (the dip only
        # sharpens in the low-power dispersive regime), so escalate on both axes.
        span0, npts0 = float(P["span_mhz"]), int(P["coarse_points"])
        lo_gain = max(base_gain // 6, 50)
        sh0 = int(P["shots"])
        plan = [(span0, npts0, base_gain, sh0),
                (span0 * 5, min(npts0 * 3, 241), base_gain, max(sh0 // 2, 150)),
                (span0 * 5, min(npts0 * 3, 241), lo_gain, max(sh0 // 2, 150)),
                (float(P["max_span_mhz"]), min(npts0 * 5, 401), lo_gain, max(sh0 // 3, 100))]
        best = None
        for span, npts, gain, sh in plan:
            cfg["shots"] = cfg["reps"] = int(sh)
            fr, z = scan(f0, span, npts, gain)
            fit = fit_resonance(fr, np.abs(z))
            if best is None or fit["snr"] > best[0]["snr"]:
                best = (fit, fr, z, span, gain)
            if fit["ok"]:
                break
            self._report("resonator", "WARN",
                         "nothing in %.1f MHz at readout gain %d (best snr %.1f) -- widening"
                         % (span, gain, fit["snr"]))
        fit_c, fr_c, z_c, span_used, gain_used = best
        cfg["shots"] = cfg["reps"] = sh0
        self.data["trans"] = {"freqs": fr_c, "mag": np.abs(z_c), "fit": fit_c["yfit"]}
        if not fit_c["ok"]:
            cfg["read_pulse_gain"] = base_gain
            mag = np.abs(z_c)
            self._report("resonator", "WARN",
                         "NO resonance found within +/-%.1f MHz of %.4f even at gain %d "
                         "(best snr %.1f, best candidate %.4f MHz; trace ptp %.3g vs noise "
                         "%.3g). Keeping read_pulse_freq -- the readout is suspect."
                         % (span_used / 2.0, f0, gain_used, fit_c["snr"], fit_c["f0"],
                            float(np.ptp(mag)), _mad(mag - _smooth(mag)) * 1.4826))
            return
        if gain_used != base_gain:
            self._report("resonator", "WARN",
                         "resonance only visible at readout gain %d (configured %d) -- the "
                         "configured readout power is likely SATURATING the resonator; "
                         "consider lowering BaseConfig['read_pulse_gain']."
                         % (gain_used, base_gain))
        fr_f, z_f = scan(fit_c["f0"], P["fine_span_mhz"], P["fine_points"], gain_used)
        fit_f = fit_resonance(fr_f, np.abs(z_f), polarity=fit_c["polarity"])
        use = fit_f if fit_f["ok"] else fit_c
        cfg["read_pulse_gain"] = base_gain
        w["read_pulse_freq"] = round(float(use["f0"]), 4)
        w["updated"].add("read_pulse_freq")
        self._report("resonator", "OK",
                     "%s at %.4f MHz (fwhm %.3f, snr %.0f); read_pulse_freq %.4f -> %.4f"
                     % (use["polarity"], use["f0"], use["fwhm"], use["snr"], f0,
                        w["read_pulse_freq"]))
        # NB: plot arrays must be self-consistent -- the fine trace pairs with the FINE
        # fit even when the coarse fit supplied the frequency (they differ in length).
        self.data["trans"] = {"freqs": fr_f, "mag": np.abs(z_f), "fit": fit_f["yfit"],
                              "coarse_freqs": fr_c, "coarse_mag": np.abs(z_c)}

    # ---------------- stage 1: spec ----------------
    def _spec_scan(self, w, center, span, npts, gain, length_us, shots, relax):
        cfg = self._stage_cfg(relax)
        cfg["shots"] = cfg["reps"] = int(shots)
        cfg["read_pulse_freq"] = float(w["read_pulse_freq"])
        cfg["start"] = float(center - span / 2.0)
        cfg["step"] = float(span / (int(npts) - 1))
        cfg["expts"] = int(npts)
        cfg["spec_gain"] = int(gain)
        cfg["spec_len_us"] = float(length_us)
        I, Q = _acquire_sweep(self, TunerSpecProgram, cfg)
        freqs = cfg["start"] + cfg["step"] * np.arange(cfg["expts"])
        z = I + 1j * Q
        # distance from the off-resonant baseline -- polarity-free peak
        sig = np.abs(z - np.median(z))
        return freqs, z, sig

    def _stage_spec(self, w):
        P = self.P["spec"]
        gain = int(P["spec_gain"] if P["spec_gain"] is not None else self.cfg["qubit_gain"])
        length = float(P["spec_len_us"] if P["spec_len_us"] is not None else self.cfg["qubit_length"])
        # Escalating search, same logic as the resonator: a drifted qubit needs a WIDER
        # window, and a faint line needs MORE drive (power-broadened but findable; the
        # low-power 2nd pass below then recovers the unshifted center).
        span0, npts0, sh0 = float(P["span_mhz"]), int(P["points"]), int(P["shots"])
        hi_gain = min(gain * 3, 30000)
        plan = [(span0, npts0, gain, sh0),
                (span0 * 4, min(npts0 * 3, 361), gain, max(sh0 // 2, 200)),
                (span0 * 4, min(npts0 * 3, 361), hi_gain, max(sh0 // 2, 200)),
                (float(P["max_span_mhz"]), min(npts0 * 5, 601), hi_gain, max(sh0 // 3, 150))]
        best = None
        for span, npts, g, sh in plan:
            freqs, z, sig = self._spec_scan(w, w["qubit_freq"], span, npts, g, length,
                                            sh, P["relax_delay_us"])
            fit = fit_resonance(freqs, sig, polarity="peak")
            if best is None or fit["snr"] > best[0]["snr"]:
                best = (fit, freqs, sig, span, g)
            if fit["ok"]:
                break
            self._report("spec", "WARN",
                         "no line in %.1f MHz at drive gain %d (best snr %.1f) -- widening"
                         % (span, g, fit["snr"]))
        fit1, freqs, sig, span_used, gain_used = best
        self.data["spec"] = {"freqs": freqs, "sig": sig, "fit": fit1["yfit"]}
        if not fit1["ok"]:
            raise TunerStageError(
                "spec: no qubit line within +/-%.1f MHz of %.3f MHz even at drive gain %d "
                "(best snr %.1f, best candidate %.3f MHz). Either the qubit moved further "
                "than that, or the READOUT is not reporting state (the resonator stage %s) "
                "-- fix the readout first."
                % (span_used / 2.0, w["qubit_freq"], gain_used, fit1["snr"], fit1["f0"],
                   "also found nothing" if "read_pulse_freq" not in w["updated"]
                   else "did find a resonance"))
        gain = gain_used
        # A peak sitting near the edge of the scan window is CLIPPED: its fitted center is
        # biased inward and it may be the shoulder of a line that lies outside.  Re-center
        # the window on it and re-scan until the peak is comfortably interior.
        for _ in range(3):
            if min(abs(fit1["f0"] - freqs[0]), abs(fit1["f0"] - freqs[-1])) > 0.15 * span_used:
                break
            self._report("spec", "WARN",
                         "line at %.3f MHz sits within 15%% of the scan edge (window "
                         "%.2f-%.2f MHz) -- re-centering on it and re-scanning"
                         % (fit1["f0"], freqs[0], freqs[-1]))
            freqs, z, sig = self._spec_scan(w, fit1["f0"], span_used, freqs.size, gain,
                                            length, P["shots"], P["relax_delay_us"])
            f2 = fit_resonance(freqs, sig, polarity="peak")
            self.data["spec"] = {"freqs": freqs, "sig": sig, "fit": f2["yfit"]}
            if not f2["ok"]:
                raise TunerStageError(
                    "spec: the line vanished when the window was re-centered on %.3f MHz "
                    "(snr %.1f) -- the original peak was a scan-edge artifact, not the "
                    "qubit." % (fit1["f0"], f2["snr"]))
            fit1 = f2
        f_q = fit1["f0"]
        note = ""
        if P["two_pass"]:
            span2 = max(6.0 * fit1["fwhm"], 1.5)
            freqs2, z2, sig2 = self._spec_scan(w, f_q, span2, max(41, P["points"] // 2),
                                               max(gain // 4, 500), length,
                                               P["shots"], P["relax_delay_us"])
            fit2 = fit_resonance(freqs2, sig2, polarity="peak")
            if fit2["ok"]:
                f_q = fit2["f0"]
                note = " (2nd pass at gain %d)" % max(gain // 4, 500)
                self.data["spec"] = {"freqs": freqs2, "sig": sig2, "fit": fit2["yfit"],
                                     "pass1_freqs": freqs, "pass1_sig": sig}
        w["qubit_freq"] = round(float(f_q), 4)
        w["drive_freq"] = w["qubit_freq"]
        w["updated"].add("qubit_freq")
        self._report("spec", "OK", "qubit line at %.4f MHz%s" % (w["qubit_freq"], note))

    # ---------------- stage 2: rough Rabi ----------------
    def _stage_rabi(self, w):
        P = self.P["rabi"]
        cfg = self._stage_cfg(P["relax_delay_us"])
        cfg["shots"] = cfg["reps"] = int(P["shots"])
        cfg["read_pulse_freq"] = float(w["read_pulse_freq"])
        cfg["drive_freq"] = float(w["drive_freq"])
        npts = int(P["points"])
        step = int(round(int(P["gain_max"]) / (npts - 1)))
        cfg["start"] = 0
        cfg["step"] = step
        cfg["expts"] = npts
        I, Q = _acquire_sweep(self, TunerRabiProgram, cfg)
        gains = np.arange(npts) * step
        sig, _u = principal_projection(I, Q)
        fit = fit_rabi(gains, sig)
        self.data["rabi"] = {"gains": gains, "sig": sig, "fit": fit["yfit"]}
        if not fit["ok"]:
            raise TunerStageError(
                "rabi: no clean oscillation (r2 %.2f, pi %.0f DAC). Check drive freq/"
                "power or readout SNR." % (fit["r2"], fit["pi_gain"]))
        w["pi_gain"] = int(round(min(fit["pi_gain"], 32766)))
        w["pi2_gain"] = int(round(w["pi_gain"] / 2.0))
        w["updated"].add("qubit_pi_gain")
        self._report("rabi", "OK", "rough pi gain %d DAC (period %.0f, r2 %.2f, contrast %.3g)"
                     % (w["pi_gain"], fit["period"], fit["r2"], fit["contrast"]))
        self._validate_pi_harmonic(w, cfg, int(P["shots"]))

    def _validate_pi_harmonic(self, w, cfg, shots):
        """Confirm the Rabi fit picked the RIGHT harmonic before anything depends on it.

        A gain sweep covering only ~1 period can fit a period that is 2x too large or too
        small.  That is silently catastrophic: if the true pi is pi_gain/2, then the
        'pi/2' used everywhere downstream is a full pi -- and a Ramsey built from pi
        pulses has no fringe at all (the first pulse parks the state at the pole, where
        the second pulse's phase does nothing), which a fitter then explains away as an
        impossibly short T2*.  So: measure the |g>-displacement at a few multiples of the
        candidate gain; the TRUE pi is the one with maximum displacement."""
        g0 = int(w["pi_gain"])
        mults = [0.0, 0.5, 1.0, 1.5, 2.0]
        pts = []
        for m in mults:
            g = int(round(min(g0 * m, 32766)))
            seq = [("pulse", g, 0.0)] if g > 0 else []
            I, Q, _, _ = _run_seq(self, cfg, seq, w["drive_freq"], shots)
            pts.append((m, g, I, Q))
        I0, Q0 = pts[0][2], pts[0][3]
        seps = [float(np.hypot(I - I0, Q - Q0)) for (_, _, I, Q) in pts]
        self.data["pi_check"] = {"mults": np.array(mults), "sep": np.array(seps)}
        best = int(np.argmax(seps))
        self._report("rabi", "OK", "pi check |IQ-IQ(0)| at %s x pi = %s"
                     % (mults, ", ".join("%.4g" % s for s in seps)))
        if seps[best] <= 0:
            raise TunerStageError("rabi: no drive response at any gain -- drive frequency "
                                  "or qubit is wrong.")
        if best == 2:
            return                                   # the fit had it right
        m_true = mults[best]
        if m_true == 0.0:
            raise TunerStageError(
                "rabi: the largest readout displacement is at ZERO drive gain -- the "
                "drive is not exciting the qubit (wrong drive frequency?).")
        new_pi = int(round(min(g0 * m_true, 32766)))
        self._report("rabi", "WARN",
                     "Rabi fit picked the WRONG harmonic: max excitation is at %.1f x the "
                     "fitted pi -- correcting pi gain %d -> %d.  (The half-period fit is "
                     "unreliable when the sweep covers only ~1 period; raise "
                     "params['rabi']['gain_max'] to cover 2+ periods.)"
                     % (m_true, g0, new_pi))
        w["pi_gain"] = new_pi
        w["pi2_gain"] = int(round(new_pi / 2.0))

    # ---------------- stage 3: Ramsey fine frequency ----------------
    def _ramsey_series(self, w, drive_freq, f_virt, tau_max, npts, shots, relax):
        cfg = self._stage_cfg(relax)
        cfg["read_pulse_freq"] = float(w["read_pulse_freq"])
        taus_nominal = np.linspace(0.05, float(tau_max), int(npts))
        # snap each delay to the actual tProc cycle grid so the fit axis is exact
        taus = np.array([self.soccfg.cycles2us(self.soccfg.us2cycles(t)) for t in taus_nominal])
        sx = int(w["pi2_gain"])
        refs_pre = _measure_refs(self, cfg, drive_freq, w["pi_gain"], shots)
        Ix = np.empty(taus.size)
        Qx = np.empty(taus.size)
        Iy = np.empty(taus.size)
        Qy = np.empty(taus.size)
        for j, t in enumerate(taus):
            phi = (360.0 * f_virt * t) % 360.0
            seq_x = [("pulse", sx, 0.0), ("delay", float(t)), ("pulse", sx, phi)]
            seq_y = [("pulse", sx, 0.0), ("delay", float(t)), ("pulse", sx, phi - 90.0)]
            Ix[j], Qx[j], _, _ = _run_seq(self, cfg, seq_x, drive_freq, shots)
            Iy[j], Qy[j], _, _ = _run_seq(self, cfg, seq_y, drive_freq, shots)
        refs_post = _measure_refs(self, cfg, drive_freq, w["pi_gain"], shots)
        g, e = _combine_refs(refs_pre, refs_post, self._report, "ramsey")
        pop_x = iq_to_pop(Ix, Qx, g, e)
        pop_y = iq_to_pop(Iy, Qy, g, e)
        fit = fit_ramsey_xy(taus, pop_x, pop_y)
        return taus, pop_x, pop_y, fit

    def _resolve_ramsey_sign(self, w, P):
        """Measure the hardware sign convention p in  f_osc = f_virt + p*(f_q - f_drive):
        offset the drive by +d and see which way the fitted fringe moves (slope = -p)."""
        if P["sign"] in (+1, -1):
            return int(P["sign"]), "forced by knob"
        if self.ramsey_sign_hint in (+1, -1):
            return int(self.ramsey_sign_hint), "from calibration history"
        d = float(P["probe_offset_mhz"])
        shots = max(300, int(P["shots"] * 0.7))
        _, _, _, fit1 = self._ramsey_series(w, w["drive_freq"], P["f_virt_mhz"],
                                            min(P["tau_max_us"], 3.0), 21, shots,
                                            P["relax_delay_us"])
        _, _, _, fit2 = self._ramsey_series(w, w["drive_freq"] + d, P["f_virt_mhz"],
                                            min(P["tau_max_us"], 3.0), 21, shots,
                                            P["relax_delay_us"])
        if not (fit1["ok"] and fit2["ok"]):
            raise TunerStageError("ramsey sign probe: fringe fit failed (contrast too "
                                  "low?) -- cannot establish the detuning sign safely.")
        slope = (abs(fit2["f_mhz"]) - abs(fit1["f_mhz"])) / d
        if not (0.4 <= abs(slope) <= 1.6):
            raise TunerStageError(
                "ramsey sign probe: fringe moved %.2f MHz per MHz of drive offset "
                "(expected ~ +/-1). Detuning may exceed the virtual detuning -- "
                "check the spec stage." % slope)
        p = -1 if slope > 0 else +1
        self._report("ramsey", "OK", "sign probe: slope %.2f -> convention p=%+d" % (slope, p))
        return p, "measured on hardware"

    def _check_virtual_z(self, w, P):
        """Decisive test of the virtual-Z phase -- the one ingredient the Ramsey needs
        that no earlier stage exercises.

        At an essentially ZERO delay, sweep the second pi/2's phase over 360 deg.  The
        population must trace a full cosine (swing ~1).  Flat means the phase register is
        not reaching the pulse, so no Ramsey can ever work -- and that failure would
        otherwise masquerade as a dead fringe / absurdly short T2*.  Because the delay is
        ~0, dephasing cannot explain a flat result: this separates a PHASE bug from real
        decoherence."""
        cfg = self._stage_cfg(P["relax_delay_us"])
        cfg["read_pulse_freq"] = float(w["read_pulse_freq"])
        cfg["seq_gap_us"] = 0.005
        shots = int(P["shots"])
        sx = int(w["pi2_gain"])
        phases = np.arange(0.0, 360.0, 30.0)
        refs_pre = _measure_refs(self, cfg, w["drive_freq"], w["pi_gain"], shots)
        I = np.empty(phases.size)
        Q = np.empty(phases.size)
        for j, ph in enumerate(phases):
            seq = [("pulse", sx, 0.0), ("delay", 0.01), ("pulse", sx, float(ph))]
            I[j], Q[j], _, _ = _run_seq(self, cfg, seq, w["drive_freq"], shots)
        refs_post = _measure_refs(self, cfg, w["drive_freq"], w["pi_gain"], shots)
        g, e = _combine_refs(refs_pre, refs_post, self._report, "ramsey")
        pop = iq_to_pop(I, Q, g, e)
        swing = float(np.ptp(pop))
        self.data["phase_check"] = {"phases": phases, "pop": pop}
        self._report("ramsey", "OK",
                     "virtual-Z check (pi/2, ~0 delay, pi/2 at phase phi): population "
                     "swing %.2f over 360 deg [%s]"
                     % (swing, " ".join("%.2f" % v for v in pop)))
        return swing

    def _ramsey_classic_series(self, w, offset_mhz, tau_max, npts, shots, relax):
        """Ramsey with NO phase control: both pi/2 pulses at phase 0, the drive itself
        deliberately offset.  Fringe frequency = |f_q - (drive + offset)|, unsigned."""
        cfg = self._stage_cfg(relax)
        cfg["read_pulse_freq"] = float(w["read_pulse_freq"])
        taus_nominal = np.linspace(0.05, float(tau_max), int(npts))
        taus = np.array([self.soccfg.cycles2us(self.soccfg.us2cycles(t))
                         for t in taus_nominal])
        sx = int(w["pi2_gain"])
        drive = float(w["drive_freq"]) + float(offset_mhz)
        # references use the ON-resonance drive: they only define the |g>->|e> IQ axis
        refs_pre = _measure_refs(self, cfg, w["drive_freq"], w["pi_gain"], shots)
        I = np.empty(taus.size)
        Q = np.empty(taus.size)
        for j, t in enumerate(taus):
            seq = [("pulse", sx, 0.0), ("delay", float(t)), ("pulse", sx, 0.0)]
            I[j], Q[j], _, _ = _run_seq(self, cfg, seq, drive, shots)
        refs_post = _measure_refs(self, cfg, w["drive_freq"], w["pi_gain"], shots)
        g, e = _combine_refs(refs_pre, refs_post, self._report, "ramsey")
        pop = iq_to_pop(I, Q, g, e)
        return taus, pop, fit_decay_cosine(taus, pop)

    def _stage_ramsey_classic(self, w, P):
        """Frequency calibration that needs no phase register and no sign convention.

        Run two Ramseys with the drive offset by +d and -d.  With x = f_q - f_drive,
        the (unsigned) fringe frequencies are f1 = |x - d| and f2 = |x + d|; as long as
        |x| < d this gives x = (f2 - f1)/2 exactly, sign included."""
        d = float(P["classic_offset_mhz"])
        tol = float(P["tol_mhz"])
        tau_max = float(P["tau_max_us"])
        for rnd in range(1, int(P["rounds"]) + 1):
            t1, p1, f1 = self._ramsey_classic_series(w, +d, tau_max, P["points"],
                                                     P["shots"], P["relax_delay_us"])
            t2_, p2, f2 = self._ramsey_classic_series(w, -d, tau_max, P["points"],
                                                      P["shots"], P["relax_delay_us"])
            self.data["ramsey"] = {"taus": t1, "pop_x": p1, "pop_y": p2,
                                   "xfit": f1["yfit"], "yfit": f2["yfit"]}
            if not (f1["ok"] and f2["ok"]):
                raise TunerStageError(
                    "ramsey (classic): fringe fit failed at offset %+0.2f/%0.2f MHz "
                    "(contrast %.2f/%.2f). With the pi confirmed good, a dead fringe at "
                    "BOTH offsets points at genuine dephasing (T2* << %.1f us)."
                    % (d, -d, f1["amp"], f2["amp"], tau_max))
            x = (f2["f_mhz"] - f1["f_mhz"]) / 2.0
            t2_us = float(0.5 * (f1["t2_us"] + f2["t2_us"]))
            w["t2_us"] = t2_us
            f_res = 1.0 / (2.0 * np.pi * max(t2_us, 1e-3))
            eff_tol = max(tol, f_res)
            self._report("ramsey", "OK",
                         "classic round %d: fringes %.4f / %.4f MHz at offsets %+.2f/%.2f "
                         "-> detuning %+.4f MHz, T2* %.2f us (resolution %.3f MHz)"
                         % (rnd, f1["f_mhz"], f2["f_mhz"], d, -d, x, t2_us, f_res))
            if max(f1["f_mhz"], f2["f_mhz"]) > 1.9 * d:
                raise TunerStageError(
                    "ramsey (classic): a fringe at %.3f MHz exceeds the +/-%.2f MHz "
                    "offset, so |detuning| > offset and x=(f2-f1)/2 is not valid -- "
                    "raise params['ramsey']['classic_offset_mhz'] above the residual "
                    "detuning." % (max(f1["f_mhz"], f2["f_mhz"]), d))
            if abs(x) <= eff_tol:
                self._report("ramsey", "OK", "converged: qubit_pi_freq = %.4f MHz "
                                             "(T2* %.2f us)" % (w["drive_freq"], t2_us))
                return
            w["drive_freq"] = round(float(w["drive_freq"] + x), 4)
        self._report("ramsey", "WARN", "classic Ramsey did not converge in %d rounds; "
                                        "using %.4f MHz" % (P["rounds"], w["drive_freq"]))

    def _stage_ramsey(self, w):
        P = self.P["ramsey"]
        swing = self._check_virtual_z(w, P)
        if swing < 0.3:
            self._report("ramsey", "WARN",
                         "virtual-Z phase is NOT working (swing %.2f at zero delay, where "
                         "dephasing cannot be the cause) -- switching to the CLASSIC "
                         "drive-detuned Ramsey, which needs no phase control." % swing)
            return self._stage_ramsey_classic(w, P)
        p, sign_src = self._resolve_ramsey_sign(w, P)
        w["ramsey_sign"] = p
        self._report("ramsey", "OK", "using sign p=%+d (%s)" % (p, sign_src))
        f_virt, tau_max = float(P["f_virt_mhz"]), float(P["tau_max_us"])
        tol = float(P["tol_mhz"])
        prev_abs_delta = None
        for rnd in range(1, int(P["rounds"]) + 1):
            taus, px, py, fit = self._ramsey_series(w, w["drive_freq"], f_virt, tau_max,
                                                    P["points"], P["shots"],
                                                    P["relax_delay_us"])
            self.data["ramsey"] = {"taus": taus, "pop_x": px, "pop_y": py,
                                   "xfit": fit["xfit"], "yfit": fit["yfit"]}
            if not fit["ok"]:
                raise TunerStageError("ramsey: fringe fit failed on round %d (contrast "
                                      "too low / T2* too short for tau_max=%.1f us?)"
                                      % (rnd, tau_max))
            # With reference-normalized populations and correct pi/2 pulses the fringe
            # swings |g> to |e>, i.e. amp ~ 0.5.  Much less than that means the PULSES are
            # wrong (wrong pi/2 amplitude, or off-resonant drive), and the fitted decay
            # would then be meaningless -- do NOT let a bad pulse masquerade as a short T2*.
            if fit["amp"] < 0.20:
                raise TunerStageError(
                    "ramsey: fringe contrast is only %.2f (expected ~0.5 for pi/2 pulses "
                    "against |g>/|e> references). The pi/2 AMPLITUDE or the drive "
                    "frequency is wrong -- the fitted T2*=%.2f us is an artifact of the "
                    "weak fringe, not a coherence measurement. Check the rough-Rabi pi "
                    "gain (harmonic!) and the drive frequency before believing any T2* "
                    "from this stage." % (fit["amp"], fit["t2_us"]))
            if abs(fit["f_mhz"]) < 0.3 * f_virt:
                raise TunerStageError(
                    "ramsey: fringe at %.3f MHz << virtual detuning %.2f MHz -- the "
                    "detuning is comparable to f_virt and |f_osc| may have folded "
                    "through zero. Re-run spec, or raise params['ramsey']['f_virt_mhz']."
                    % (abs(fit["f_mhz"]), f_virt))
            delta = (abs(fit["f_mhz"]) - f_virt) / p
            t2 = fit["t2_us"]
            # A Ramsey fringe cannot localize a frequency better than its own linewidth
            # ~1/(2*pi*T2*).  Any "detuning" below that is noise, not signal -- so the
            # convergence target must never be finer than the coherence allows.
            f_res = 1.0 / (2.0 * np.pi * max(t2, 1e-3))
            eff_tol = max(tol, f_res)
            w["t2_us"] = float(t2)          # record as soon as measured, for the report
            self._report("ramsey", "OK",
                         "round %d: f_osc %.4f MHz, T2* %.2f us -> detuning %+.4f MHz "
                         "(resolution limit %.3f MHz)"
                         % (rnd, abs(fit["f_mhz"]), t2, delta, f_res))
            if rnd == 1 and f_res > tol:
                self._report("ramsey", "WARN",
                             "T2*=%.2f us limits Ramsey resolution to ~%.3f MHz, coarser "
                             "than the %.3f MHz target -- using %.3f MHz as the target."
                             % (t2, f_res, tol, eff_tol))
            # A gate that is not short compared to T2* is decoherence-limited: the
            # rotation decays DURING the pulse, so no amplitude calibration is meaningful.
            t_pi_us = 4.0 * float(self.cfg["sigma"])
            if rnd == 1 and t_pi_us > 0.5 * t2 and fit["amp"] >= 0.35:
                # only trust a short T2* when the fringe had near-full contrast (a weak
                # fringe is a pulse problem, already caught above)
                moved = abs(w["qubit_freq"] - float(self.cfg["qubit_freq"]))
                raise TunerStageError(
                    "coherence: the pi pulse is %.3f us long (4*sigma) but T2* is only "
                    "%.2f us -- the gate does not fit inside the coherence time, so NO "
                    "amplitude calibration here can be meaningful.%s Fix the operating "
                    "point first (flux/sweet spot, or shorten sigma), then re-run."
                    % (t_pi_us, t2,
                       " The qubit also moved %.1f MHz from its configured frequency, "
                       "which is consistent with having drifted off its flux sweet spot "
                       "onto a flux-sensitive (short-T2*) slope." % moved
                       if moved > 1.0 else ""))
            if abs(delta) > 2.0:
                raise TunerStageError("ramsey: |detuning| %.2f MHz is implausibly large "
                                      "-- spec stage suspect; not applying." % delta)
            if abs(delta) <= eff_tol:
                self._report("ramsey", "OK", "converged: qubit_pi_freq = %.4f MHz "
                                             "(T2* %.2f us)" % (w["drive_freq"], t2))
                w["t2_us"] = float(t2)
                return
            if prev_abs_delta is not None and abs(delta) > 1.5 * prev_abs_delta:
                # Growth only implicates the SIGN if it is bigger than the measurement
                # can explain; otherwise both readings are consistent with noise and
                # blaming the sign would be a misdiagnosis.
                if (abs(delta) - prev_abs_delta) > 2.0 * f_res:
                    raise TunerStageError(
                        "ramsey: the correction made the detuning GROW (%.4f -> %.4f MHz, "
                        "well beyond the %.3f MHz resolution). Sign convention p=%+d is "
                        "wrong for this setup -- rerun with params['ramsey']['sign']=%+d."
                        % (prev_abs_delta, abs(delta), f_res, p, -p))
                raise TunerStageError(
                    "ramsey: detuning is not converging (%.4f -> %.4f MHz) but both "
                    "values are within the %.3f MHz resolution set by T2*=%.2f us -- the "
                    "fringe is too short-lived to measure the frequency this finely. "
                    "This is a COHERENCE problem, not a sign problem."
                    % (prev_abs_delta, abs(delta), f_res, t2))
            w["drive_freq"] = round(float(w["drive_freq"] + delta), 4)
            prev_abs_delta = abs(delta)
            # adapt the next round: longer window (T2*-limited), finer virtual detuning
            tau_max = float(np.clip(1.5 * t2, 2.0, 15.0))
            f_virt = max(0.3, 4.0 / tau_max)
        self._report("ramsey", "WARN", "did not reach |detuning| <= %.3f MHz in %d rounds; "
                                        "using last value %.4f MHz" % (tol, P["rounds"], w["drive_freq"]))
        w.setdefault("t2_us", 10.0)

    # ---------------- stage 4: fine amplitude (error amplification) ----------------
    def _stage_fine_amp(self, w):
        P = self.P["fine_amp"]
        cfg = self._stage_cfg(P["relax_delay_us"])
        cfg["read_pulse_freq"] = float(w["read_pulse_freq"])
        tol = float(P["tol_rad"])
        shots = int(P["shots"])
        t_pi = 4.0 * float(self.cfg["sigma"])
        t2 = float(w.get("t2_us", 10.0))
        hist = []
        # keep the whole train inside T2*/3 so decoherence doesn't flatten the envelope
        n_max = int(min(int(P["n_max"]), max(6, (t2 / 3.0) / max(t_pi, 1e-3))))
        for rnd in range(1, int(P["rounds"]) + 1):
            Ns = np.arange(0, n_max + 1)
            refs_pre = _measure_refs(self, cfg, w["drive_freq"], w["pi_gain"], shots)
            I = np.empty(Ns.size)
            Q = np.empty(Ns.size)
            for j, N in enumerate(Ns):
                seq = [("pulse", int(w["pi2_gain"]), 0.0)] + int(N) * [("pulse", int(w["pi_gain"]), 0.0)]
                I[j], Q[j], _, _ = _run_seq(self, cfg, seq, w["drive_freq"], shots)
            refs_post = _measure_refs(self, cfg, w["drive_freq"], w["pi_gain"], shots)
            g, e = _combine_refs(refs_pre, refs_post, self._report, "fine_amp")
            pop = iq_to_pop(I, Q, g, e)
            fit = fit_error_amp(Ns, pop)
            self.data.setdefault("fine_amp", {})["round%d" % rnd] = \
                {"N": Ns, "pop": pop, "fit": fit["yfit"]}
            if not fit["ok"]:
                raise TunerStageError("fine_amp: ping-pong fit failed on round %d "
                                      "(amplitude %.2f) -- readout SNR or pi too far off."
                                      % (rnd, fit["amp"]))
            dth, sig = fit["d_theta"], fit["sigma"]
            self._report("fine_amp", "OK",
                         "round %d (N<=%d): dtheta %+.4f +/- %.4f rad (%.2f%% gain error)"
                         % (rnd, n_max, dth, sig, 100 * dth / np.pi))
            if hist and abs(dth) > 1.5 * abs(hist[-1]) and abs(dth) > tol:
                raise TunerStageError(
                    "fine_amp: correction made the angle error GROW (%.4f -> %.4f rad) "
                    "-- model/sign problem, not applying." % (abs(hist[-1]), abs(dth)))
            hist.append(dth)
            # Convergence needs an ABSOLUTE guarantee, not a noisy fit's self-report:
            #  (a) the fitted angle is within tol and the fit constrains it, OR
            #  (b) the ping-pong pattern is flat -- deviations of the P(N) pattern are
            #      0.5*sin(N*dtheta), so half the peak-to-peak directly BOUNDS
            #      |dtheta| <= 2*dev/n_max with no fit involved.
            dev = 0.5 * float(np.ptp(pop))
            flat_bound = 2.0 * dev / max(n_max, 1)
            if (abs(dth) <= tol and sig <= 3.0 * tol) or flat_bound <= tol:
                resid = min(abs(dth), flat_bound)
                self._report("fine_amp", "OK", "converged: pi gain %d DAC (residual "
                                               "angle <= %.4f rad)" % (w["pi_gain"], resid))
                w["fine_amp_converged"] = True
                w["d_theta_final"] = float(resid)
                return
            if abs(dth) > 0.6:
                raise TunerStageError("fine_amp: |dtheta| %.2f rad is too large for the "
                                      "linear correction -- rough Rabi suspect." % dth)
            scale = np.pi / (np.pi + dth)
            scale = float(np.clip(scale, 0.8, 1.25))
            w["pi_gain"] = int(round(min(w["pi_gain"] * scale, 32766)))
            w["pi2_gain"] = int(round(w["pi_gain"] / 2.0))
            # more repetitions -> more precision, bounded by decoherence (N*t_pi < T2/3)
            n_max = int(min(30, max(n_max, (t2 / 3.0) / max(t_pi, 1e-3))))
        self._report("fine_amp", "WARN", "not converged after %d rounds (last dtheta "
                                          "%+.4f rad)" % (P["rounds"], hist[-1]))
        w["fine_amp_converged"] = False
        w["d_theta_final"] = float(hist[-1])

    # ---------------- stage 5: verification ----------------
    def _stage_verify(self, w):
        P = self.P["verify"]
        cfg = self._stage_cfg(P["relax_delay_us"])
        cfg["read_pulse_freq"] = float(w["read_pulse_freq"])
        shots = int(P["shots"])
        refs = _measure_refs(self, cfg, w["drive_freq"], w["pi_gain"], shots)
        snr = refs["sep"] / max(refs["se"] * np.sqrt(2.0), 1e-12)
        g, e = refs["g"], refs["e"]
        pi, sx = int(w["pi_gain"]), int(w["pi2_gain"])
        I2, Q2, _, _ = _run_seq(self, cfg, [("pulse", pi, 0.0), ("pulse", pi, 0.0)],
                                w["drive_freq"], shots)
        Ih, Qh, _, _ = _run_seq(self, cfg, [("pulse", sx, 0.0)], w["drive_freq"], shots)
        pop_2pi = float(iq_to_pop(I2, Q2, g, e))
        pop_sx = float(iq_to_pop(Ih, Qh, g, e))
        # mini ping-pong at the final settings
        Ns = np.array([1, 4, 7, 10, 13])
        I = np.empty(Ns.size)
        Q = np.empty(Ns.size)
        for j, N in enumerate(Ns):
            seq = [("pulse", sx, 0.0)] + int(N) * [("pulse", pi, 0.0)]
            I[j], Q[j], _, _ = _run_seq(self, cfg, seq, w["drive_freq"], shots)
        chk = fit_error_amp(Ns, iq_to_pop(I, Q, g, e))
        self.data["verify"] = {"snr": snr, "pop_2pi": pop_2pi, "pop_sx": pop_sx,
                               "check_dtheta": chk["d_theta"], "sep": refs["sep"]}
        ok = True
        if snr < float(P["snr_min"]):
            self._report("verify", "FAIL", "averaged-readout SNR %.1f < %.1f" % (snr, P["snr_min"]))
            ok = False
        else:
            self._report("verify", "OK", "readout SNR %.0f (|e>-|g| = %.4g)" % (snr, refs["sep"]))
        if abs(pop_2pi) > 0.2:
            self._report("verify", "WARN", "2pi residual population %.2f (expect ~0)" % pop_2pi)
        else:
            self._report("verify", "OK", "2pi residual %.3f" % pop_2pi)
        if not (0.3 <= pop_sx <= 0.7):
            self._report("verify", "WARN", "pi/2 population %.2f (expect ~0.5; the "
                                            "half-gain sx is only a linear estimate)" % pop_sx)
        else:
            self._report("verify", "OK", "pi/2 population %.2f" % pop_sx)
        if chk["ok"] and abs(chk["d_theta"]) > 3.0 * float(self.P["fine_amp"]["tol_rad"]):
            self._report("verify", "WARN", "independent ping-pong check: dtheta %+.4f rad"
                         % chk["d_theta"])
        else:
            self._report("verify", "OK", "ping-pong check dtheta %+.4f rad" % chk["d_theta"])
        return ok

    # ---------------- plotting ----------------
    @staticmethod
    def _pair(ax, x, y, *a, **kw):
        """Plot only when x and y line up -- a mismatched pair is a plotting bug, and it
        must never be allowed to kill a finished run (the measurement is the deliverable)."""
        x = np.asarray(x)
        y = np.asarray(y)
        if x.ndim == 1 and y.ndim == 1 and x.size == y.size and x.size:
            ax.plot(x, y, *a, **kw)

    def _plot_summary(self, w, success):
        fig, axs = plt.subplots(2, 3, figsize=(15, 8))
        d = self.data
        ax = axs[0, 0]
        if "trans" in d:
            self._pair(ax, d["trans"].get("coarse_freqs", []), d["trans"].get("coarse_mag", []),
                       ".", ms=2, color="0.7")
            self._pair(ax, d["trans"]["freqs"], d["trans"]["mag"], ".", ms=3)
            self._pair(ax, d["trans"]["freqs"], d["trans"]["fit"], "-", lw=1)
            ax.axvline(w["read_pulse_freq"], color="r", ls="--", lw=0.8)
        ax.set_title("resonator")
        ax.set_xlabel("MHz")
        ax = axs[0, 1]
        if "spec" in d:
            self._pair(ax, d["spec"]["freqs"], d["spec"]["sig"], ".", ms=3)
            self._pair(ax, d["spec"]["freqs"], d["spec"]["fit"], "-", lw=1)
            ax.axvline(w["qubit_freq"], color="r", ls="--", lw=0.8)
        ax.set_title("qubit spec")
        ax.set_xlabel("MHz")
        ax = axs[0, 2]
        if "rabi" in d:
            self._pair(ax, d["rabi"]["gains"], d["rabi"]["sig"], ".", ms=3)
            self._pair(ax, d["rabi"]["gains"], d["rabi"]["fit"], "-", lw=1)
            ax.axvline(w.get("pi_gain", np.nan), color="r", ls="--", lw=0.8)
        ax.set_title("rough Rabi")
        ax.set_xlabel("gain (DAC)")
        ax = axs[1, 0]
        if "ramsey" in d:
            self._pair(ax, d["ramsey"]["taus"], d["ramsey"]["pop_x"], ".", ms=3, label="X")
            self._pair(ax, d["ramsey"]["taus"], d["ramsey"]["pop_y"], ".", ms=3, label="Y")
            self._pair(ax, d["ramsey"]["taus"], d["ramsey"]["xfit"], "-", lw=1)
            self._pair(ax, d["ramsey"]["taus"], d["ramsey"]["yfit"], "-", lw=1)
            ax.legend(fontsize=7)
        ax.set_title("RamseyXY (last round)  T2*=%.2f us" % w.get("t2_us", np.nan))
        ax.set_xlabel("delay (us)")
        ax = axs[1, 1]
        if "fine_amp" in d:
            for name, rd in sorted(d["fine_amp"].items()):
                self._pair(ax, rd["N"], rd["pop"], ".-", ms=3, lw=0.7, label=name)
                self._pair(ax, rd["N"], rd["fit"], "--", lw=0.7, color="gray")
            ax.axhline(0.5, color="k", lw=0.5)
            ax.legend(fontsize=7)
        ax.set_title("fine amplitude (ping-pong)")
        ax.set_xlabel("N pi pulses after sx")
        ax = axs[1, 2]
        ax.axis("off")
        txt = ["AUTO PI TUNE  %s" % ("SUCCESS" if success else "FAILED"),
               "read  %.4f MHz" % w.get("read_pulse_freq", np.nan),
               "qubit %.4f MHz" % w.get("qubit_freq", np.nan),
               "pi f  %.4f MHz" % w.get("drive_freq", np.nan),
               "pi g  %s DAC" % w.get("pi_gain", "?"),
               "T2*   %.1f us" % w.get("t2_us", np.nan),
               "dtheta %.4f rad" % w.get("d_theta_final", np.nan)]
        ax.text(0.02, 0.95, "\n".join(txt), va="top", family="monospace", fontsize=11)
        fig.suptitle("AutoPiTuner  %s  %s" % (self.element, self.time_string))
        fig.tight_layout()
        plt.savefig(self.iname, dpi=150, bbox_inches="tight")
        return fig

    # ---------------- orchestration ----------------
    def acquire(self, progress=False, plotDisp=False):
        cfg = self.cfg
        self.data = {}
        w = {  # the working calibration state (starts from BaseConfig, never mutates it)
            "read_pulse_freq": float(cfg["read_pulse_freq"]),
            "qubit_freq": float(cfg["qubit_freq"]),                # spec center
            "drive_freq": float(cfg.get("qubit_pi_freq", cfg["qubit_freq"])),
            "pi_gain": int(cfg["qubit_pi_gain"]),
            "pi2_gain": int(cfg.get("qubit_pi2_gain", cfg["qubit_pi_gain"] // 2)),
            "updated": set(),      # keys a stage actually MEASURED (safe to write back)
        }
        print("=" * 72)
        print("AUTO PI TUNER  (%s)  starting from: read %.4f  qubit %.4f  pi %.4f MHz "
              "@ %d DAC" % (self.element, w["read_pulse_freq"], cfg["qubit_freq"],
                            w["drive_freq"], w["pi_gain"]))
        print("=" * 72)
        success = False
        failure = None
        try:
            if self.P["resonator"]["run"]:
                self._stage_resonator(w)
            if self.P["spec"]["run"]:
                self._stage_spec(w)
            self._stage_rabi(w)
            self._stage_ramsey(w)
            self._stage_fine_amp(w)
            verify_ok = self._stage_verify(w)
            success = bool(verify_ok and w.get("fine_amp_converged", False))
        except TunerStageError as err:
            failure = str(err)
            self._report("pipeline", "FAIL", failure)

        print("-" * 72)
        for line in self.report_lines:
            print("  " + line)
        print("-" * 72)
        # only values a stage actually MEASURED are eligible for the config write --
        # e.g. with the spec stage skipped, qubit_freq must NOT be (re)written
        tuned = {"qubit_pi_freq": w["drive_freq"],
                 "qubit_pi_gain": int(w["pi_gain"]),
                 "qubit_pi2_gain": int(w["pi2_gain"])}
        for key in ("read_pulse_freq", "qubit_freq"):
            if key in w["updated"]:
                tuned[key] = w[key]
        if success:
            print("TUNE SUCCESS:")
            for k, v in tuned.items():
                print("   %-18s %s" % (k, v))
        else:
            print("TUNE FAILED%s" % ("" if failure is None else " (%s)" % failure))
            print("Config NOT written.  But these WERE measured this run -- apply by hand "
                  "if you trust them:")
            start = {"read_pulse_freq": float(cfg["read_pulse_freq"]),
                     "qubit_freq": float(cfg["qubit_freq"]),
                     "qubit_pi_gain": int(cfg["qubit_pi_gain"])}
            for key, got in (("read_pulse_freq", w["read_pulse_freq"]),
                             ("qubit_freq", w["qubit_freq"]),
                             ("qubit_pi_gain", w["pi_gain"])):
                if key in w["updated"]:
                    was = start[key]
                    moved = " (moved %+.4f)" % (float(got) - was) if was else ""
                    print("   %-18s %-12s  was %s%s" % (key, got, was, moved))
            if "t2_us" in w:
                print("   %-18s %.2f us" % ("T2* (measured)", w["t2_us"]))
        print("=" * 72)

        self.data.update({
            "success": success, "failure": failure, "tuned": tuned,
            "working": {k: (sorted(v) if isinstance(v, set) else v) for k, v in w.items()},
            "report": list(self.report_lines),
            "ramsey_sign": int(w.get("ramsey_sign", 0)),
            "time": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        })
        try:
            fig = self._plot_summary(w, success)
            if plotDisp:
                plt.show(block=False)
                plt.pause(0.1)
            else:
                plt.close(fig)
        except Exception as perr:      # a plot must never lose a completed measurement
            print("[auto-pi] WARNING: summary plot failed (%s); data still saved." % perr)
            plt.close("all")
        self.pickle_data()
        self.save_config()
        return {'config': cfg, 'data': self.data}

    def save_data(self, data=None):
        print('Saving %s' % self.fname)
        flat = {}
        d = self.data
        for stage in ("trans", "spec", "rabi", "ramsey"):
            if stage in d:
                for k, v in d[stage].items():
                    if isinstance(v, np.ndarray):
                        flat["%s_%s" % (stage, k)] = v
        for name, rd in d.get("fine_amp", {}).items():
            for k, v in rd.items():
                if isinstance(v, np.ndarray):
                    flat["fine_amp_%s_%s" % (name, k)] = v
        super().save_data(data=flat)
