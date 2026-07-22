"""
Automatic qubit tuner -- a calibration GRAPH with fixed-point iteration.

Replaces the previous straight-line pipeline (mAutoPiTuner.py).  The stages are mutually
dependent -- readout optimization needs a pi, the pi needs a readout, and a better
readout invalidates the spec/Rabi measured through the old one -- so the correct
structure is a dependency graph iterated to a fixed point, not a sequence.  Architecture
follows Optimus (Kelly et al., arXiv:1803.03226) and the QUAlibrate/QUA bring-up DAGs:

  * every node declares DEPENDENCIES, a cheap check() and a full calibrate(), and a spec
  * calibrating a node marks its dependents STALE (that is the invalidation engine)
  * maintain() sweeps the graph until nothing is stale and nothing is out of spec
  * BEST-SO-FAR state: a round that makes things worse can never be committed

Node order mirrors the QUA gate_calibration_flux_tunable workflow, which is:
    Transmission_Sweep (punch-out) -> Transmission -> Chi -> Qubit_Spec -> SS_Cal
    -> Rabi_Chevron_IQ -> Rabi_Chevron_SS -> Rabi_Linecut_SS
with the manual "read the number off the plot, paste it into the meta dict, re-run"
loop that a physicist performs replaced by the automatic fixed point.

KEY PHYSICS THIS ENCODES (and the old tuner did not)
----------------------------------------------------
* The optimal READOUT FREQUENCY is not the resonator dip.  With alpha_{g,e} =
  eps/((delta -/+ chi) + i kappa/2), the state separation D = |alpha_g - alpha_e| is
  maximized at the MIDPOINT between the dressed resonances when 2|chi| <= kappa, and on
  a dressed peak (offset ~ +/-chi) when 2|chi| > kappa.  So we measure chi and kappa from
  two scans (|g> and |e>) and place the tone analytically, then confirm with a scan of D.
* Readout POWER before FREQUENCY (power sets the regime), with an OUTLIER-FRACTION gate
  that rejects powers where measurement-induced transitions/ionization break the
  two-blob model -- raw fidelity alone does not catch that.
* Readout LENGTH trades sqrt(T_int) SNR against T1 decay during the measurement, so T1
  must be measured, not guessed.
* A same-phase pi TRAIN is CPMG-like: it refocuses quasi-static detuning, so its limit is
  T1/driven coherence, NOT T2*.  That is what makes pi calibration possible on a qubit
  whose T2* is too short for Ramsey.
* The pi-train residual is quadratically sensitive to DETUNING as well as amplitude, so
  the drive frequency is calibrated by minimizing the same residual (sign-free and
  T2*-free) instead of by a Ramsey.

CONVERGENCE STATISTIC (this was the previous tuner's worst bug)
--------------------------------------------------------------
The residual AT THE MINIMUM of a gain sweep is the decoherence/readout-noise FLOOR, not
an angle error -- at the minimum the angle error is zero by construction.  Using it as
the convergence test makes the tuner report FAILED on a perfect pulse.  We instead use
the UNCERTAINTY ON THE PARABOLA VERTEX (propagated from the fit covariance) and the
agreement of the vertex ACROSS M, which are the quantities that actually bound the
calibration error.

Everything is park-only (ff_gain = 0) and asserts it.  All frequencies are MHz floats
(never Hz ints -- Windows int32 trap), gains DAC ints, times us.  Prints are ASCII-only.
Verified against qick 0.2.133: AveragerProgram.acquire -> 2-tuple, RAveragerProgram ->
3-tuple, no get_raw() (per-shot data is di_buf/dq_buf).
"""

import datetime
import warnings

import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit, OptimizeWarning

from qick import AveragerProgram, RAveragerProgram

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.acquisition import suppress_stdout


# ======================================================================================
# Part 1 -- pure analysis (numpy/scipy only; importable and testable without a board)
# ======================================================================================

def lorentzian(f, f0, fwhm, a, off, slope=0.0):
    """Lorentzian on a LINEAR baseline.  The baseline term matters: over the wide spans
    the escalating search uses, the readout chain response is sloped, and a bare
    Lorentzian will happily fit the slope instead of the resonance."""
    return off + slope * (f - np.mean(f)) + a / (1.0 + ((f - f0) / (fwhm / 2.0)) ** 2)


def _mad_sigma(x):
    x = np.asarray(x, dtype=float)
    return float(np.median(np.abs(x - np.median(x)))) * 1.4826 + 1e-15


def _noise_sigma(y):
    """Robust noise estimate that is immune to smooth structure.

    Estimating noise as MAD(y - smooth(y)) FAILS on a well-averaged trace: the smoothed
    curve nearly equals the data, the difference collapses toward zero, and any SNR built
    on it explodes (observed: 8e15 on real hardware data, which made every fit pass its
    `snr > 5` gate and let a spurious bump be accepted as the qubit line).

    The second difference of a smooth curve is ~0, so MAD(diff(y, 2))/sqrt(6) measures the
    noise alone.  Floored relative to the trace range so it can never reach zero."""
    y = np.asarray(y, dtype=float)
    y = y[np.isfinite(y)]
    if y.size < 5:
        return _mad_sigma(y)
    d2 = np.diff(y, n=2)
    s = float(np.median(np.abs(d2 - np.median(d2)))) * 1.4826 / np.sqrt(6.0)
    # Averaged accumulator values are QUANTIZED, so a flat baseline can repeat exactly and
    # drive every difference-based estimate to zero.  The noise can never be smaller than
    # the quantization step / sqrt(12).
    uniq = np.unique(y)
    if uniq.size > 1:
        step = float(np.min(np.diff(uniq)))
        s = max(s, step / np.sqrt(12.0))
    rng = float(np.ptp(y))
    return float(max(s, 1e-4 * (rng if rng > 0 else 1.0)))


def _smooth(y, npts_per_feature=None, w=None):
    """Moving average whose window is set by the EXPECTED FEATURE WIDTH IN SAMPLES, not a
    fixed sample count.  A fixed 7-sample boxcar is wider than the feature itself on a
    fine scan (3 MHz / 61 pts = 50 kHz spacing -> 350 kHz kernel vs a 216 kHz linewidth),
    which erases the very dip it is meant to reveal -- that single bug is why narrow
    resonator scans kept 'finding nothing' while wider, coarser ones succeeded."""
    y = np.asarray(y, dtype=float)
    if w is None:
        w = 3 if npts_per_feature is None else int(np.clip(npts_per_feature // 3, 1, 11))
    w = max(int(w), 1) | 1
    if w <= 1 or y.size < w + 2:
        return y.copy()
    k = np.ones(w) / w
    pad = np.concatenate([y[:w // 2][::-1], y, y[-(w // 2):][::-1]])
    return np.convolve(pad, k, mode="valid")


def fit_resonance(freqs, mag, polarity=None, expected_fwhm=None):
    """Fit a resonance on a sloped baseline.  `expected_fwhm` (MHz) sets the smoothing
    kernel so it can never be wider than the feature.  Returns dict with ok/f0/fwhm/
    snr/polarity/yfit/f0_err."""
    freqs = np.asarray(freqs, dtype=float)
    mag = np.asarray(mag, dtype=float)
    if freqs.size < 7 or not np.all(np.isfinite(mag)):
        return {"ok": False, "f0": float(freqs[0]) if freqs.size else np.nan,
                "fwhm": np.nan, "snr": 0.0, "polarity": polarity or "dip",
                "yfit": np.zeros_like(mag), "f0_err": np.inf}
    df = float(np.mean(np.diff(freqs)))
    npts_feat = None if expected_fwhm is None else max(expected_fwhm / max(df, 1e-9), 3.0)
    sm = _smooth(mag, npts_per_feature=npts_feat)
    # de-trend with a robust line before deciding polarity/depth
    coef = np.polyfit(freqs, sm, 1)
    base = np.polyval(coef, freqs)
    dev0 = sm - base
    if polarity is None:
        polarity = "dip" if abs(dev0.min()) >= abs(dev0.max()) else "peak"
    sgn = -1.0 if polarity == "dip" else 1.0
    dev = sgn * dev0
    i0 = int(np.argmax(dev))
    depth = float(dev[i0])
    half = depth / 2.0
    lo, hi = i0, i0
    while lo > 0 and dev[lo] > half:
        lo -= 1
    while hi < dev.size - 1 and dev[hi] > half:
        hi += 1
    fwhm0 = max(abs(freqs[hi] - freqs[lo]), 3.0 * abs(df))
    f0, fwhm, f0_err, yfit, ok = freqs[i0], fwhm0, np.inf, sm, False
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", OptimizeWarning)
        try:
            p0 = [freqs[i0], fwhm0, sgn * depth, float(coef[1]), float(coef[0])]
            popt, pcov = curve_fit(lorentzian, freqs, mag, p0=p0, maxfev=20000)
            if freqs.min() <= popt[0] <= freqs.max() and np.isfinite(popt[1]):
                f0, fwhm = float(popt[0]), float(abs(popt[1]))
                yfit = lorentzian(freqs, *popt)
                if np.all(np.isfinite(pcov)):
                    f0_err = float(np.sqrt(max(pcov[0, 0], 0.0)))
                ok = True
        except Exception:
            pass
    # Noise from the second difference of the RAW trace.  Neither the residual to the
    # model (which collapses when curve_fit falls back to the smoothed data) nor
    # MAD(mag - smooth) (which collapses on a well-averaged trace) is a valid noise
    # estimate -- both produce astronomically large SNRs that defeat the ok gate.
    snr = depth / _noise_sigma(mag)
    # require significance AND that the feature is actually resolved by this scan (at
    # least ~2 samples across it) and not absurdly wide compared with the window
    ok = bool(ok and snr > 5.0 and fwhm > 1.5 * abs(df)
              and fwhm < 0.7 * (freqs.max() - freqs.min()))
    return {"ok": ok, "f0": float(f0), "fwhm": float(fwhm), "snr": float(snr),
            "polarity": polarity, "yfit": np.asarray(yfit, dtype=float),
            "f0_err": float(f0_err), "depth": depth}


def _better_fit(new, cur):
    """A fit that SUCCEEDED always beats one that failed, whatever their SNRs."""
    if cur is None:
        return True
    if bool(new["ok"]) != bool(cur["ok"]):
        return bool(new["ok"])
    return new["snr"] > cur["snr"]


def optimal_readout_detuning(chi_mhz, kappa_mhz):
    """Drive detuning (relative to the BARE resonance) that maximizes the state
    separation D = |alpha_g - alpha_e|, with alpha_{g,e} = eps/((d -/+ chi) + i kappa/2).

    Closed form of the standard result: for 2|chi| <= kappa the maximum is exactly at the
    midpoint (d = 0); beyond that it moves onto a dressed peak, approaching +/-chi.  We
    evaluate D numerically on a fine grid, which is exact and costs nothing."""
    chi = float(chi_mhz)
    kap = max(float(kappa_mhz), 1e-9)
    if not np.isfinite(chi) or abs(chi) < 1e-9:
        return 0.0
    span = 3.0 * max(abs(chi), kap)
    d = np.linspace(0.0, span, 2001)          # D is EVEN in d -- only |d| is determined
    ag = 1.0 / ((d - chi) + 0.5j * kap)
    ae = 1.0 / ((d + chi) + 0.5j * kap)
    return float(abs(d[int(np.argmax(np.abs(ag - ae)))]))


def parabola_vertex(x, y, yerr=None):
    """Vertex of a local quadratic through the minimum, WITH its uncertainty.

    The uncertainty is the whole point: the residual at the minimum is a decoherence
    floor and says nothing about how well the minimum is LOCATED, whereas sigma(vertex)
    is exactly the calibration error.  Returns dict(x_min, x_err, interior, curvature)."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    good = np.isfinite(x) & np.isfinite(y)
    x, y = x[good], y[good]
    if x.size < 5:
        return {"x_min": float(x[int(np.argmin(y))]) if x.size else np.nan,
                "x_err": np.inf, "interior": False, "curvature": 0.0}
    k = int(np.argmin(y))
    lo, hi = max(0, k - 3), min(x.size, k + 4)
    xs, ys = x[lo:hi], y[lo:hi]
    if xs.size < 4:
        return {"x_min": float(x[k]), "x_err": np.inf, "interior": False, "curvature": 0.0}
    xc = float(np.mean(xs))
    sigma = None
    if yerr is not None:
        e = np.asarray(yerr, dtype=float)[good][lo:hi]
        sigma = np.where(np.isfinite(e) & (e > 0), e, np.nanmedian(e[np.isfinite(e)]) or 1.0)
    # Weighted least squares done explicitly: np.polyfit(cov=True) RESCALES the
    # covariance by chi2/dof, so supplied per-point sigmas act only as relative weights
    # and the absolute error comes from the scatter of the few points chosen AT the noise
    # dip -- systematically optimistic.  cov = inv(A^T W A) with W = 1/sigma^2 gives the
    # true absolute uncertainty.
    A = np.vstack([(xs - xc) ** 2, (xs - xc), np.ones_like(xs)]).T
    if sigma is None:
        try:
            resid_sd = float(np.std(ys - np.polyval(np.polyfit(xs - xc, ys, 2), xs - xc), ddof=3))
        except Exception:
            resid_sd = float(np.std(ys))
        sigma = np.full(xs.size, max(resid_sd, 1e-12))
    W = np.diag(1.0 / np.maximum(np.asarray(sigma, dtype=float), 1e-12) ** 2)
    try:
        ATA = A.T @ W @ A
        cov = np.linalg.inv(ATA)
        c = cov @ (A.T @ W @ ys)
    except Exception:
        try:
            c = np.polyfit(xs - xc, ys, 2)
            cov = np.full((3, 3), np.nan)
        except Exception:
            return {"x_min": float(x[k]), "x_err": np.inf, "interior": False, "curvature": 0.0}
    a, b = float(c[0]), float(c[1])
    if a <= 0:                                   # not a minimum -> fall back to the sample
        return {"x_min": float(x[k]), "x_err": np.inf,
                "interior": bool(0 < k < x.size - 1), "curvature": a}
    xv = -b / (2.0 * a) + xc
    xerr = np.inf
    if np.all(np.isfinite(cov)):
        # var(-b/2a) by first-order propagation
        dvda, dvdb = b / (2.0 * a * a), -1.0 / (2.0 * a)
        var = (dvda ** 2) * cov[0, 0] + (dvdb ** 2) * cov[1, 1] + 2 * dvda * dvdb * cov[0, 1]
        if np.isfinite(var) and var >= 0:
            xerr = float(np.sqrt(var))
    interior = bool(x.min() < xv < x.max() and 0 < k < x.size - 1)
    if not (x.min() <= xv <= x.max()):
        xv = float(x[k])
    return {"x_min": float(xv), "x_err": xerr, "interior": interior, "curvature": a}


def single_shot_analysis(ig, qg, ie, qe):
    """Single-shot readout analysis: rotation angle, threshold, fidelity, error
    directions, separation in shot-noise units, and an OUTLIER FRACTION.

    The outlier fraction (shots inconsistent with a two-Gaussian model) is the gate that
    rejects readout powers where measurement-induced transitions or ionization create a
    third population -- raw fidelity does not catch that and will happily climb into a
    destructive regime.

    Fidelity is reported with a TRAIN/TEST SPLIT: the threshold is chosen on half the
    shots and scored on the other half, so the number is not optimistically biased by
    fitting the threshold to the same data it is scored on."""
    ig, qg = np.asarray(ig, dtype=float), np.asarray(qg, dtype=float)
    ie, qe = np.asarray(ie, dtype=float), np.asarray(qe, dtype=float)
    n = min(ig.size, qg.size, ie.size, qe.size)
    if n < 20:
        return {"ok": False, "fidelity": np.nan, "sep_sigma": 0.0, "theta": 0.0,
                "threshold": np.nan, "p_e_given_g": np.nan, "p_g_given_e": np.nan,
                "outlier_frac": 1.0, "xg": np.zeros(0), "xe": np.zeros(0)}
    ig, qg, ie, qe = ig[:n], qg[:n], ie[:n], qe[:n]
    dx, dy = ie.mean() - ig.mean(), qe.mean() - qg.mean()
    th = float(np.arctan2(dy, dx))
    xg = ig * np.cos(th) + qg * np.sin(th)
    xe = ie * np.cos(th) + qe * np.sin(th)
    yg = -ig * np.sin(th) + qg * np.cos(th)
    ye = -ie * np.sin(th) + qe * np.cos(th)
    sd = float(0.5 * (np.std(xg) + np.std(xe)))
    sep = float(np.hypot(dx, dy))
    sep_sigma = sep / (sd + 1e-15)

    def _thr_fid(a, b):
        lo, hi = float(min(a.min(), b.min())), float(max(a.max(), b.max()))
        cand = np.linspace(lo, hi, 512)
        f = np.array([(a < t).mean() + (b >= t).mean() - 1.0 for t in cand])
        k = int(np.argmax(f))
        return float(cand[k])

    h = n // 2
    thr = _thr_fid(xg[:h], xe[:h])                       # chosen on the train half
    p_eg = float((xg[h:] >= thr).mean())                 # scored on the test half
    p_ge = float((xe[h:] < thr).mean())
    fid = 1.0 - p_eg - p_ge
    # Outlier fraction: shots far from BOTH blob centres.  The yardstick must be a
    # ROBUST width taken from the TIGHTER blob -- using the pooled variance lets a
    # smeared/ionized population inflate the very scale it is being judged against, so
    # ionization would hide itself.
    cg = np.array([np.median(xg), np.median(yg)])
    ce = np.array([np.median(xe), np.median(ye)])

    def _rob(a):
        return float(np.median(np.abs(a - np.median(a)))) * 1.4826

    s_g = 0.5 * (_rob(xg) + _rob(yg))
    s_e = 0.5 * (_rob(xe) + _rob(ye))
    s2 = max(min(s_g, s_e), 1e-12) ** 2
    allpts = np.column_stack([np.concatenate([xg, xe]), np.concatenate([yg, ye])])
    d2 = np.minimum(((allpts - cg) ** 2).sum(1), ((allpts - ce) ** 2).sum(1)) / s2
    outlier_frac = float((d2 > 16.0).mean())             # >4 robust sigma from both
    return {"ok": True, "fidelity": float(fid), "sep_sigma": float(sep_sigma),
            "theta": th, "threshold": float(thr), "p_e_given_g": p_eg,
            "p_g_given_e": p_ge, "outlier_frac": outlier_frac,
            "xg": xg, "xe": xe, "sep": sep, "sigma": sd}


def fit_rabi(gains, sig):
    """Damped anchored cosine: B + C exp(-g/gd) cos(c g).  The envelope matters -- an
    undamped fit absorbs driven decoherence into the offset and biases the extracted pi.
    Phase is locked (no free phase) because g=0 is |g> by construction."""
    gains = np.asarray(gains, dtype=float)
    sig = np.asarray(sig, dtype=float)
    good = np.isfinite(gains) & np.isfinite(sig)
    gains, sig = gains[good], sig[good]
    if gains.size < 8:
        return {"ok": False, "pi_gain": np.nan, "period": np.nan, "r2": 0.0,
                "yfit": np.zeros_like(sig)}
    span = float(gains.max() - gains.min())
    y = sig - sig.mean()
    n = gains.size
    fft = np.fft.rfft(y * np.hanning(n))
    fax = np.fft.rfftfreq(n, d=float(gains[1] - gains[0]))
    k = 1 + int(np.argmax(np.abs(fft[1:]))) if n > 3 else 1
    c_seed = 2.0 * np.pi * max(float(fax[min(k, fax.size - 1)]), 0.25 / max(span, 1.0))

    def model(g, B, C, c, gd):
        return B + C * np.exp(-g / gd) * np.cos(c * g)

    best = None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", OptimizeWarning)
        for mult in (0.5, 0.75, 1.0, 1.5, 2.0):
            try:
                popt, _ = curve_fit(model, gains, sig,
                                    p0=[sig.mean(), np.ptp(sig) / 2.0, c_seed * mult, 5.0 * span],
                                    bounds=([-np.inf, -np.inf, 1e-9, 0.2 * span],
                                            [np.inf, np.inf, np.inf, 1e6 * span]),
                                    maxfev=20000)
                r = sig - model(gains, *popt)
                sse = float(np.dot(r, r))
                if best is None or sse < best[0]:
                    best = (sse, popt)
            except Exception:
                continue
    if best is None:
        return {"ok": False, "pi_gain": np.nan, "period": np.nan, "r2": 0.0,
                "yfit": np.full_like(sig, sig.mean())}
    _, (B, C, c, gd) = best
    c = abs(float(c))
    pi_gain = np.pi / c if c > 0 else np.nan
    yfit = model(gains, B, C, c, gd)
    ss_res = float(np.sum((sig - yfit) ** 2))
    ss_tot = float(np.sum((sig - sig.mean()) ** 2)) + 1e-15
    r2 = 1.0 - ss_res / ss_tot
    ok = bool(np.isfinite(pi_gain) and 0.02 * span <= pi_gain <= gains.max() and r2 > 0.7)
    return {"ok": ok, "pi_gain": float(pi_gain), "period": float(2 * np.pi / c) if c > 0 else np.nan,
            "r2": float(r2), "yfit": yfit, "decay_gain": float(gd)}


def fit_exp_decay(t, y):
    """y = A exp(-t/tau) + c."""
    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)
    good = np.isfinite(t) & np.isfinite(y)
    t, y = t[good], y[good]
    if t.size < 4:
        return {"ok": False, "tau": np.nan, "A": 0.0, "c": 0.0, "yfit": np.zeros_like(y),
                "tau_err": np.inf}

    def model(tt, A, tau, c):
        return A * np.exp(-tt / tau) + c

    best = None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", OptimizeWarning)
        for tau0 in (t.max() / 5.0, t.max() / 2.0, t.max(), 3.0 * t.max()):
            try:
                popt, pcov = curve_fit(model, t, y, p0=[float(np.ptp(y)), tau0, float(np.min(y))],
                                       bounds=([-3.0, 1e-4, -2.0], [3.0, 1e5, 2.0]), maxfev=20000)
                r = y - model(t, *popt)
                sse = float(np.dot(r, r))
                if best is None or sse < best[0]:
                    best = (sse, popt, pcov)
            except Exception:
                continue
    if best is None:
        return {"ok": False, "tau": np.nan, "A": 0.0, "c": 0.0, "yfit": np.zeros_like(y),
                "tau_err": np.inf}
    _, (A, tau, c), pcov = best
    yfit = model(t, A, tau, c)
    tau_err = float(np.sqrt(max(pcov[1, 1], 0.0))) if np.all(np.isfinite(pcov)) else np.inf
    ok = bool(abs(A) > 4.0 * max(float(np.std(y - yfit)), 1e-9) and abs(A) > 0.05)
    return {"ok": ok, "tau": float(tau), "A": float(A), "c": float(c), "yfit": yfit,
            "tau_err": tau_err}


def iq_to_pop(I, Q, g_ref, e_ref):
    """Averaged IQ projected onto the |g>->|e> axis (0 = |g>, 1 = |e>).  Returns NaN when
    the references coincide; every consumer must treat NaN as 'no data', never as 0."""
    gI, gQ = g_ref
    eI, eQ = e_ref
    dx, dy = eI - gI, eQ - gQ
    denom = dx * dx + dy * dy
    if not np.isfinite(denom) or denom <= 0:
        return np.full(np.shape(I), np.nan)
    return ((np.asarray(I, dtype=float) - gI) * dx +
            (np.asarray(Q, dtype=float) - gQ) * dy) / denom


def nan_argmin(y):
    """argmin that refuses to select a NaN (np.argmin returns the NaN's index)."""
    y = np.asarray(y, dtype=float)
    if not np.any(np.isfinite(y)):
        return None
    return int(np.nanargmin(y))


def nan_argmax(y):
    y = np.asarray(y, dtype=float)
    if not np.any(np.isfinite(y)):
        return None
    return int(np.nanargmax(y))


# ======================================================================================
# Part 2 -- tProc programs (qick 0.2.133, tProc v1)
# ======================================================================================

def _declare_common(prog, include_qubit=True):
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
                             freq=read_freq, phase=prog.deg2reg(cfg.get("res_phase", 0.0),
                                                               gen_ch=cfg["res_ch"]),
                             gain=int(cfg["read_pulse_gain"]),
                             length=prog.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]))
    return read_freq


def _add_qubit_gauss(prog, name="qubit"):
    """Gaussian envelope on the QUBIT generator's fabric clock.  Passing gen_ch is not
    optional: without it us2cycles uses the tProc clock and every pi pulse comes out the
    wrong length (and the host-side t_pi = 4*sigma used for coherence bounds is wrong
    too)."""
    cfg = prog.cfg
    qch = cfg["qubit_ch"]
    sig = prog.us2cycles(cfg["sigma"], gen_ch=qch)
    sig = max(int(sig), 1)
    prog.add_gauss(ch=qch, name=name, sigma=sig, length=sig * 4)
    return sig


class TransProgram(AveragerProgram):
    """Readout-only point at cfg['read_pulse_freq'] (optionally after a qubit pulse, so
    the same program serves the |g> and |e> resonator scans that give chi)."""

    def initialize(self):
        cfg = self.cfg
        cfg.setdefault("reps", int(cfg.get("shots", 300)))
        need_q = int(cfg.get("prep_gain", 0)) > 0
        _declare_common(self, include_qubit=need_q)
        if need_q:
            _add_qubit_gauss(self)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb",
                                     freq=self.freq2reg(float(cfg["drive_freq"]), gen_ch=cfg["qubit_ch"]),
                                     phase=0, gain=int(cfg["prep_gain"]), waveform="qubit")
        self.synci(200)

    def body(self):
        cfg = self.cfg
        if int(cfg.get("prep_gain", 0)) > 0:
            self.pulse(ch=cfg["qubit_ch"])
            self.sync_all(self.us2cycles(0.01))
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(cfg["relax_delay"]))


class SpecProgram(RAveragerProgram):
    """Hardware qubit-frequency sweep with a const saturation probe."""

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


class RabiProgram(RAveragerProgram):
    """Hardware gain sweep of the gaussian drive at cfg['drive_freq']."""

    def initialize(self):
        cfg = self.cfg
        self.q_rp = self.ch_page(cfg["qubit_ch"])
        self.r_gain = self.sreg(cfg["qubit_ch"], "gain")
        _declare_common(self, include_qubit=True)
        _add_qubit_gauss(self)
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb",
                                 freq=self.freq2reg(float(cfg["drive_freq"]), gen_ch=cfg["qubit_ch"]),
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


class SeqProgram(AveragerProgram):
    """Generic sequence: cfg['seq'] is a list of ('pulse', gain, phase_deg) and
    ('delay', us) ops, then one readout.  Covers references, pi trains, T1 and any
    phase-swept sequence."""

    def initialize(self):
        cfg = self.cfg
        cfg.setdefault("reps", int(cfg.get("shots", 400)))
        _declare_common(self, include_qubit=True)
        _add_qubit_gauss(self)
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
                if gap > 0:
                    self.sync_all(gap)
            elif op[0] == "delay":
                self.sync_all(self.us2cycles(float(op[1])))
            else:
                raise ValueError("unknown seq op %r" % (op,))
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(cfg["relax_delay"]))


# ======================================================================================
# Part 3 -- measurement primitives
# ======================================================================================

class TunerError(RuntimeError):
    """A node failed unrecoverably; the graph stops and nothing is written."""


def gen_sample_rate(soccfg, gen_ch):
    """Generator sample rate in MHz, or None if soccfg does not expose it."""
    try:
        g = soccfg['gens'][int(gen_ch)]
    except Exception:
        return None
    for key in ("fs", "f_dds", "fs_dac", "f_fabric"):
        v = g.get(key) if hasattr(g, "get") else None
        if v:
            return float(v)
    return None


def check_nyquist(soccfg, gen_ch, freq_mhz, nqz, label):
    """Report which Nyquist zone a frequency lands in and whether the declared zone
    boosts it.  This WARNS; it never refuses.

    qick's set_nyquist docstring is explicit that the setting "doesn't change the output
    frequencies: you will always have some power at both the demanded frequency and its
    image(s)" -- nqz only switches the DAC analog stage (NRZ vs mix-mode), raising output
    in zones 2/3.  A frequency outside the declared zone is therefore still emitted, just
    weakly, and refusing it would block working setups: this board's readout sits at
    7248.95 MHz, which is in zone 3 if fs = 6881.28 MHz, with nqz=2.

    What does matter: a 5112 MHz qubit driven with nqz=1 gets the NRZ envelope instead of
    the mix-mode boost, so it is driven far more weakly than it should be."""
    fs = gen_sample_rate(soccfg, gen_ch)
    if fs is None or not np.isfinite(freq_mhz) or float(freq_mhz) <= 0:
        return None
    f = float(freq_mhz)
    zone = int(f // (fs / 2.0)) + 1
    want = 1 if zone == 1 else 2
    if int(nqz) != want:
        return ("%s: %.4f MHz falls in Nyquist zone %d but nqz=%d is declared. The tone is "
                "still emitted, but zone %d is boosted by nqz=%d (mix-mode) and starved by "
                "nqz=%d -- set it to %d for full drive power."
                % (label, f, zone, int(nqz), zone, want, int(nqz), want))
    return None


def _read_shots(prog, cfg):
    """Per-shot I/Q, tolerant of the qick build.  0.2.133 (this board) exposes
    di_buf/dq_buf and has NO get_raw(); other builds used in this lab (0.2.401, the
    escher forks) expose get_raw() instead.  Prefer the verified path, fall back, and
    fail LOUDLY rather than silently returning nothing."""
    length = prog.us2cycles(cfg["read_length"], ro_ch=cfg["ro_chs"][0])
    n = int(cfg["reps"])
    di, dq = getattr(prog, "di_buf", None), getattr(prog, "dq_buf", None)
    if di is not None and dq is not None:
        return (np.asarray(di, dtype=float)[0][:n] / length,
                np.asarray(dq, dtype=float)[0][:n] / length)
    getraw = getattr(prog, "get_raw", None)
    if callable(getraw):
        raw = np.asarray(getraw(), dtype=float)
        flat = raw.reshape(-1, 2)
        return flat[:n, 0] / length, flat[:n, 1] / length
    raise TunerError("this qick build exposes neither di_buf/dq_buf nor get_raw(); "
                     "per-shot data cannot be read.")


def _avg_iq(exp, prog_cls, cfg):
    """Rep-averaged (I, Q) plus the per-shot standard errors.  A failure to read the shot
    buffer raises rather than silently returning NaN -- a NaN SEM previously turned the
    only readout gate into an always-pass."""
    with suppress_stdout():
        prog = prog_cls(exp.soccfg, cfg)
        avgi, avgq = prog.acquire(exp.soc, load_pulses=True, progress=False)
    I = float(np.asarray(avgi)[0][0])
    Q = float(np.asarray(avgq)[0][0])
    reps = int(cfg["reps"])
    ish, qsh = _read_shots(prog, cfg)
    seI = float(np.std(ish, ddof=1) / np.sqrt(max(reps, 2)))
    seQ = float(np.std(qsh, ddof=1) / np.sqrt(max(reps, 2)))
    return I, Q, seI, seQ


def _shots(exp, cfg, seq, drive_freq, shots):
    c = dict(cfg)
    c["seq"] = list(seq)
    c["drive_freq"] = float(drive_freq)
    c["shots"] = c["reps"] = int(shots)
    with suppress_stdout():
        prog = SeqProgram(exp.soccfg, c)
        prog.acquire(exp.soc, load_pulses=True, progress=False)
    return _read_shots(prog, c)


def _run_seq(exp, cfg, seq, drive_freq, shots):
    c = dict(cfg)
    c["seq"] = list(seq)
    c["drive_freq"] = float(drive_freq)
    c["shots"] = c["reps"] = int(shots)
    return _avg_iq(exp, SeqProgram, c)


def _pop_with_local_refs(exp, cfg, seq, drive_freq, pi_gain, shots):
    """Population for one sequence with |g> and |e> references measured IMMEDIATELY
    adjacent to it.  Batch-level references are useless on a readout that drifts tens of
    percent within a batch, so every point carries its own.  Returns (pop, sep, sem)."""
    Ig, Qg, sIg, sQg = _run_seq(exp, cfg, [], drive_freq, shots)
    Ie, Qe, sIe, sQe = _run_seq(exp, cfg, [("pulse", int(pi_gain), 0.0)], drive_freq, shots)
    Im, Qm, sIm, sQm = _run_seq(exp, cfg, list(seq), drive_freq, shots)
    sep = float(np.hypot(Ie - Ig, Qe - Qg))
    pop = float(iq_to_pop(Im, Qm, (Ig, Qg), (Ie, Qe)))
    sem = float(np.hypot(sIm, sQm) / max(sep, 1e-12))     # population uncertainty
    return pop, sep, sem


# ======================================================================================
# Part 4/5 -- calibration graph
# ======================================================================================

DEFAULTS = {
    "max_rounds": 4,
    "resonator": {"span_mhz": 4.0, "points": 81, "max_span_mhz": 60.0, "shots": 400,
                  "relax_delay_us": 50.0, "expected_fwhm_mhz": 0.3},
    "spec": {"span_mhz": 20.0, "points": 121, "max_span_mhz": 150.0, "shots": 500,
             "gain": None, "len_us": None, "relax_delay_us": 500.0,
             "power_ratios": (1.0, 0.35, 0.12)},
    "rough_pi": {"gain_max": 30000, "points": 61, "shots": 500, "relax_delay_us": None},
    "chi": {"span_mhz": 4.0, "points": 81, "shots": 500, "relax_delay_us": None},
    "readout_power": {"ratios": (0.25, 0.4, 0.6, 0.85, 1.2, 1.7, 2.4, 3.4),
                      "shots": 1500, "outlier_max": 0.02, "relax_delay_us": None},
    "t1": {"points": 12, "shots": 600, "t_max_us": None, "relax_delay_us": None},
    "readout_len": {"lengths_us": (1.0, 2.0, 4.0, 8.0, 14.0, 20.0, 30.0, 45.0),
                    "shots": 1500, "relax_delay_us": None},
    "single_shot": {"shots": 4000, "min_sep_sigma": 2.0, "target_sep_sigma": 4.0,
                    "relax_delay_us": None},
    "fine_pi_freq": {"M": 8, "span_mhz": 1.2, "points": 11, "shots": 500,
                     "relax_delay_us": None},
    "fine_pi_amp": {"M_list": (4, 10, 20), "frac": (0.14, 0.05, 0.025), "points": 13,
                    "shots": 500, "tol_frac": 0.004, "relax_delay_us": None},
}


def merge_params(user):
    p = {}
    for k, v in DEFAULTS.items():
        p[k] = dict(v) if isinstance(v, dict) else v
        if user and k in user:
            if isinstance(v, dict):
                p[k].update(user[k])
            else:
                p[k] = user[k]
    return p


# node name -> (dependencies, method name, significance key)
# Dependencies are deliberately CYCLIC: spec/rough_pi are measured THROUGH the readout,
# so a readout change must invalidate them, while chi/readout_* need a pi to prepare |e>.
# _mark_dependents_stale grows a bounded set and maintain() is bounded by max_rounds, so
# the cycle is safe -- and it is the whole point: without these back-edges a better
# readout could never force the spec and Rabi that were measured through the old one to
# be re-measured.
GRAPH = [
    ("resonator",     [],                              "_cal_resonator"),
    ("spec",          ["resonator", "chi", "readout_power", "readout_len"], "_cal_spec"),
    ("rough_pi",      ["spec", "resonator", "chi", "readout_power", "readout_len"],
                                                       "_cal_rough_pi"),
    # t1 runs EARLY: relax_delay defaults to a blind 3 ms, which dominates the wall
    # clock of every later node.  Measuring T1 first lets the rest run at 5*T1.
    ("t1",            ["rough_pi"],                    "_cal_t1"),
    ("chi",           ["resonator", "rough_pi"],       "_cal_chi"),
    ("readout_power", ["chi", "rough_pi"],             "_cal_readout_power"),
    ("readout_len",   ["readout_power", "t1"],         "_cal_readout_len"),
    ("single_shot",   ["readout_len"],                 "_cal_single_shot"),
    ("fine_pi_freq",  ["single_shot", "rough_pi"],     "_cal_fine_pi_freq"),
    ("fine_pi_amp",   ["fine_pi_freq"],                "_cal_fine_pi_amp"),
]


class AutoTuner(ExperimentClass):
    """Run-once automatic tuner.  acquire() maintains the calibration graph to a fixed
    point and returns {'config': cfg, 'data': self.data}; data['tuned'] holds the values
    the runner may write, data['success'] whether they are trustworthy."""

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data',
                 suffix='Auto_Tune', cfg=None, meta_dict=None, params=None, **kw):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, suffix=suffix, cfg=cfg, meta_dict=meta_dict, **kw)
        self.element = str(path)
        self.P = merge_params(params)
        self.report_lines = []
        self.stale = {name: True for name, _, _ in GRAPH}
        self.node_data = {}

    # ------------------------------------------------------------------ plumbing
    def _say(self, node, status, msg):
        line = "[%-13s] %-4s %s" % (node, status, msg)
        self.report_lines.append(line)
        print("  " + line)

    def _cfg_for(self, node):
        """Config for a node: BaseConfig + the CURRENT working values.  Nothing mutates
        self.cfg -- the working state `self.w` is the single source of truth, so stages
        before and after a readout change are never confounded."""
        c = dict(self.cfg)
        w = self.w
        c["read_pulse_freq"] = float(w["read_pulse_freq"])
        c["read_pulse_gain"] = int(w["read_pulse_gain"])
        c["read_length"] = float(w["read_length"])
        c["res_phase"] = float(w.get("res_phase", c.get("res_phase", 0.0)))
        rd = self.P[node].get("relax_delay_us")
        c["relax_delay"] = float(rd) if rd is not None else float(w["relax_delay"])
        # adc_trig_offset is the fixed DAC->cable->ADC round-trip delay, NOT a fraction
        # of the window: scaling it with read_length would open the ADC before the pulse
        # arrives and would unfairly penalise the short-length candidates in exactly the
        # comparison readout_len exists to make.
        c["adc_trig_offset"] = float(self.cfg.get("adc_trig_offset", 0.5))
        return c

    def _mark_dependents_stale(self, node):
        changed = True
        dirty = {node}
        while changed:
            changed = False
            for name, deps, _ in GRAPH:
                if name not in dirty and any(d in dirty for d in deps):
                    dirty.add(name)
                    self.stale[name] = True
                    changed = True

    # ------------------------------------------------------------------ nodes
    def _cal_resonator(self):
        P = self.P["resonator"]
        cfg = self._cfg_for("resonator")
        cfg["shots"] = cfg["reps"] = int(P["shots"])
        cfg["prep_gain"] = 0
        f0 = float(self.w["read_pulse_freq"])

        def scan(center, span, npts):
            fs = np.linspace(center - span / 2.0, center + span / 2.0, int(npts))
            z = np.empty(fs.size, dtype=complex)
            for j, f in enumerate(fs):
                c = dict(cfg)
                c["read_pulse_freq"] = float(f)
                I, Q, _, _ = _avg_iq(self, TransProgram, c)
                z[j] = I + 1j * Q
            return fs, z

        best = None
        span, npts = float(P["span_mhz"]), int(P["points"])
        while True:
            fs, z = scan(f0, span, npts)
            # fit the POWER |S21|^2: it is the quantity that is Lorentzian with FWHM =
            # kappa.  Fitting the amplitude |S21| inflates the fitted width by ~1.7x,
            # which would then mis-place the analytic optimal readout detuning.
            fit = fit_resonance(fs, np.abs(z) ** 2, expected_fwhm=P["expected_fwhm_mhz"])
            if _better_fit(fit, best[0] if best else None):
                best = (fit, fs, z)
            if fit["ok"] or span >= float(P["max_span_mhz"]):
                break
            self._say("resonator", "WARN", "nothing in %.1f MHz (snr %.1f) -- widening"
                      % (span, fit["snr"]))
            span, npts = min(span * 4.0, float(P["max_span_mhz"])), min(npts * 3, 401)
        fit, fs, z = best
        self.node_data["resonator"] = {"freqs": fs, "mag": np.abs(z) ** 2, "fit": fit["yfit"]}
        if not fit["ok"]:
            raise TunerError("resonator: no resonance within +/-%.1f MHz of %.4f (best "
                             "snr %.1f). Check the readout chain/power." % (span / 2, f0, fit["snr"]))
        self._say("resonator", "OK", "%s at %.4f +/- %.4f MHz, kappa/2pi = %.3f MHz (snr %.0f)"
                  % (fit["polarity"], fit["f0"], fit["f0_err"], fit["fwhm"], fit["snr"]))
        self.w["resonator_f0"] = float(fit["f0"])
        self.w["kappa_mhz"] = float(fit["fwhm"])
        self.w["read_pulse_freq"] = round(float(fit["f0"]), 4)
        self.w["updated"].add("read_pulse_freq")
        return {"f0": fit["f0"]}, {"f0": max(0.2 * fit["fwhm"], 3 * fit["f0_err"])}

    def _cal_spec(self):
        P = self.P["spec"]
        gain0 = int(P["gain"] if P["gain"] is not None else self.cfg["qubit_gain"])
        length = float(P["len_us"] if P["len_us"] is not None else self.cfg["qubit_length"])

        def scan(center, span, npts, gain, shots):
            cfg = self._cfg_for("spec")
            cfg["shots"] = cfg["reps"] = int(shots)
            cfg["start"] = float(center - span / 2.0)
            cfg["step"] = float(span / (int(npts) - 1))
            cfg["expts"] = int(npts)
            cfg["spec_gain"] = int(gain)
            cfg["spec_len_us"] = length
            with suppress_stdout():
                prog = SpecProgram(self.soccfg, cfg)
                _x, avgi, avgq = prog.acquire(self.soc, load_pulses=True, progress=False)
            fs = cfg["start"] + cfg["step"] * np.arange(cfg["expts"])
            z = np.asarray(avgi[0][0], float) + 1j * np.asarray(avgq[0][0], float)
            # complex-median baseline (not a rectified magnitude, which makes the noise
            # Rayleigh and biases the MAD-based snr)
            base = np.median(z.real) + 1j * np.median(z.imag)
            return fs, np.abs(z - base)

        # ---- find the line (escalate span, then power) ----
        span, npts, gain = float(P["span_mhz"]), int(P["points"]), gain0
        best = None
        while True:
            fs, sig = scan(self.w["qubit_freq"], span, npts, gain, P["shots"])
            fit = fit_resonance(fs, sig, polarity="peak", expected_fwhm=max(2.0, span / 40))
            if _better_fit(fit, best[0] if best else None):
                best = (fit, fs, sig, span, gain)
            if fit["ok"]:
                break
            if span < float(P["max_span_mhz"]):
                span, npts = min(span * 4.0, float(P["max_span_mhz"])), min(npts * 3, 601)
            elif gain < 30000:
                gain = min(gain * 3, 30000)
            else:
                break
            self._say("spec", "WARN", "no line in %.0f MHz at gain %d -- widening"
                      % (span, gain))
        fit, fs, sig, span_used, gain_used = best
        if not fit["ok"]:
            raise TunerError("spec: no qubit line within +/-%.0f MHz of %.3f (best snr "
                             "%.1f)." % (span_used / 2, self.w["qubit_freq"], fit["snr"]))
        self._say("spec", "OK", "candidate line at %.4f MHz (span %.0f MHz, gain %d, "
                                "snr %.1f, fwhm %.3f) -- confirming against power"
                  % (fit["f0"], span_used, gain_used, fit["snr"], fit["fwhm"]))
        # ---- re-centre if the peak sits near a scan edge (a clipped peak's centre is
        #      biased inward and may be the shoulder of a line outside the window) ----
        for _ in range(3):
            if min(abs(fit["f0"] - fs[0]), abs(fit["f0"] - fs[-1])) > 0.15 * span_used:
                break
            self._say("spec", "WARN", "line at %.3f is within 15%% of the scan edge -- "
                                      "re-centring" % fit["f0"])
            fs, sig = scan(fit["f0"], span_used, fs.size, gain_used, P["shots"])
            f2 = fit_resonance(fs, sig, polarity="peak", expected_fwhm=max(2.0, span_used / 40))
            if not f2["ok"]:
                raise TunerError("spec: the line vanished when re-centred on %.3f -- the "
                                 "original peak was a scan-edge artifact." % fit["f0"])
            fit = f2
        # ---- POWER EXTRAPOLATION: the saturation line is power-broadened and AC-Stark
        #      shifted, so a single low-power pass is not enough.  Take a ladder of
        #      powers and extrapolate the centre to zero power. ----
        centres, powers = [], []
        narrow = max(6.0 * fit["fwhm"], 1.5)
        for ratio in P["power_ratios"]:
            g = max(int(gain_used * ratio), 40)
            fs2, sig2 = scan(fit["f0"], narrow, max(41, npts // 3), g, P["shots"])
            f2 = fit_resonance(fs2, sig2, polarity="peak", expected_fwhm=fit["fwhm"])
            if f2["ok"]:
                centres.append(f2["f0"])
                powers.append(float(g) ** 2)          # Stark shift ~ drive power
                self.node_data["spec"] = {"freqs": fs2, "sig": sig2, "fit": f2["yfit"]}
        if len(centres) >= 2:
            c = np.polyfit(np.array(powers), np.array(centres), 1)
            f_q = float(c[-1])                        # zero-power intercept
            self._say("spec", "OK", "qubit line %.4f MHz (zero-power extrapolation over "
                                    "%d powers; highest-power centre %.4f)"
                      % (f_q, len(centres), centres[0]))
        else:
            # A REAL qubit line persists (and sharpens) as the drive comes down; a noise
            # artifact does not.  Failing to reproduce it at ANY lower power means the
            # candidate was not the qubit -- accepting it here is how a spurious bump in
            # the first window prevents the search from ever widening to the real line.
            raise TunerError(
                "spec: the candidate at %.4f MHz did NOT reproduce at any reduced drive "
                "power (%d of %d power steps found it), so it is not the qubit line. "
                "Widen params['spec']['span_mhz'] / raise max_span_mhz, or the line lies "
                "outside the searched window."
                % (fit["f0"], len(centres), len(P["power_ratios"])))
        self.w["qubit_freq"] = round(f_q, 4)
        self.w["spec_fwhm"] = float(fit["fwhm"])
        self.w["updated"].add("qubit_freq")
        if "drive_freq" not in self.w or self.stale.get("rough_pi", True):
            self.w["drive_freq"] = self.w["qubit_freq"]
        return {"f": f_q}, {"f": max(0.05, 0.1 * fit["fwhm"])}

    def _cal_rough_pi(self):
        P = self.P["rough_pi"]
        cfg = self._cfg_for("rough_pi")
        cfg["shots"] = cfg["reps"] = int(P["shots"])
        cfg["drive_freq"] = float(self.w["drive_freq"])
        npts = int(P["points"])
        step = max(int(round(int(P["gain_max"]) / (npts - 1))), 1)
        cfg["start"], cfg["step"], cfg["expts"] = 0, step, npts
        with suppress_stdout():
            prog = RabiProgram(self.soccfg, cfg)
            _x, avgi, avgq = prog.acquire(self.soc, load_pulses=True, progress=False)
        gains = np.arange(npts) * step
        I = np.asarray(avgi[0][0], float)
        Q = np.asarray(avgq[0][0], float)
        di, dq = I - I.mean(), Q - Q.mean()
        cov = np.array([[di @ di, di @ dq], [di @ dq, dq @ dq]])
        wv, vv = np.linalg.eigh(cov)
        u = vv[:, int(np.argmax(wv))]
        sig = di * u[0] + dq * u[1]
        if sig[nan_argmax(np.abs(sig))] < 0:
            sig = -sig                                # make g=0 the low end
        fit = fit_rabi(gains, sig)
        # If the fitted period is a small fraction of the swept range the oscillation is
        # badly undersampled -- which is exactly what happens the first time the drive
        # becomes efficient (e.g. moving from half-frequency to direct resonant driving,
        # where the pi can drop by an order of magnitude).  Re-sweep around the found
        # scale so the fit sees a couple of clean periods instead of dozens of aliased ones.
        if fit["ok"] and np.isfinite(fit["period"]) and fit["period"] < 0.25 * gains.max():
            new_max = int(np.clip(2.5 * fit["period"], 200, 32000))
            self._say("rough_pi", "OK", "period %.0f DAC is small next to the %d sweep -- "
                      "re-sweeping 0-%d so it is properly sampled"
                      % (fit["period"], int(gains.max()), new_max))
            step = max(int(round(new_max / (npts - 1))), 1)
            cfg["start"], cfg["step"], cfg["expts"] = 0, step, npts
            with suppress_stdout():
                prog = RabiProgram(self.soccfg, cfg)
                _x, avgi, avgq = prog.acquire(self.soc, load_pulses=True, progress=False)
            gains = np.arange(npts) * step
            I = np.asarray(avgi[0][0], float)
            Q = np.asarray(avgq[0][0], float)
            di, dq = I - I.mean(), Q - Q.mean()
            cov = np.array([[di @ di, di @ dq], [di @ dq, dq @ dq]])
            wv, vv = np.linalg.eigh(cov)
            u = vv[:, int(np.argmax(wv))]
            sig = di * u[0] + dq * u[1]
            if sig[nan_argmax(np.abs(sig))] < 0:
                sig = -sig
            fit = fit_rabi(gains, sig)
        self.node_data["rough_pi"] = {"gains": gains, "sig": sig, "fit": fit["yfit"]}
        if not fit["ok"]:
            raise TunerError("rough_pi: no clean Rabi (r2 %.2f). Check drive freq/power "
                             "or readout." % fit["r2"])
        pi0 = int(round(min(fit["pi_gain"], 32000)))
        pi0 = self._harmonic_check(pi0, cfg, int(P["shots"]))
        self.w["pi_gain"] = pi0
        self.w["updated"].add("qubit_pi_gain")
        self._say("rough_pi", "OK", "pi gain %d DAC (period %.0f, r2 %.2f)"
                  % (pi0, fit["period"], fit["r2"]))
        return {"g": pi0}, {"g": max(0.03 * pi0, 50)}

    def _harmonic_check(self, pi0, cfg, shots):
        """Confirm the Rabi fit picked the right harmonic, WITH a significance test.
        Repeating each point and requiring the winner to beat 1x by >3 sigma stops a
        noisy readout from silently halving the pi gain."""
        mults = [0.0, 0.5, 1.0, 1.5, 2.0]
        means, errs = [], []
        for m in mults:
            g = int(round(min(pi0 * m, 32000)))
            seq = [("pulse", g, 0.0)] if g > 0 else []
            vals = []
            for _ in range(2):
                I, Q, sI, sQ = _run_seq(self, cfg, seq, self.w["drive_freq"], shots)
                vals.append((I, Q, np.hypot(sI, sQ)))
            I0, Q0 = np.mean([v[0] for v in vals]), np.mean([v[1] for v in vals])
            means.append((I0, Q0))
            errs.append(float(np.mean([v[2] for v in vals])) / np.sqrt(2))
        base = means[0]
        seps = np.array([float(np.hypot(m[0] - base[0], m[1] - base[1])) for m in means])
        err = float(np.mean(errs)) * np.sqrt(2)
        k = nan_argmax(seps)
        self._say("rough_pi", "OK", "harmonic check |dIQ| at %s x pi = [%s] (+/- %.3g)"
                  % (mults, " ".join("%.3g" % s for s in seps), err))
        if k is None or seps[k] <= 0:
            raise TunerError("rough_pi: no drive response at any gain.")
        if k != 2 and (seps[k] - seps[2]) > 3.0 * err:
            new = int(round(min(pi0 * mults[k], 32000)))
            self._say("rough_pi", "WARN", "wrong harmonic: max at %.1f x pi (%.3g vs %.3g "
                      "at 1x, >3 sigma) -- correcting %d -> %d"
                      % (mults[k], seps[k], seps[2], pi0, new))
            return new
        return pi0

    def _cal_chi(self):
        """Dispersive shift and the ANALYTIC optimal readout frequency.

        Two resonator scans, |g> and |e>, give chi and kappa directly.  The optimal drive
        detuning then follows from maximizing |alpha_g - alpha_e|: the midpoint when
        2|chi| <= kappa, a dressed peak otherwise.  This replaces a noisy brute-force
        argmax over single-shot separation with a two-scan measurement -- exactly the
        Chi_Measurement step of the QUA workflow."""
        P = self.P["chi"]
        cfg = self._cfg_for("chi")
        cfg["shots"] = cfg["reps"] = int(P["shots"])
        cfg["drive_freq"] = float(self.w["drive_freq"])
        f_c = float(self.w.get("resonator_f0", self.w["read_pulse_freq"]))
        fs = np.linspace(f_c - P["span_mhz"] / 2, f_c + P["span_mhz"] / 2, int(P["points"]))
        zg = np.empty(fs.size, dtype=complex)
        ze = np.empty(fs.size, dtype=complex)
        for j, f in enumerate(fs):
            c = dict(cfg)
            c["read_pulse_freq"] = float(f)
            c["prep_gain"] = 0
            I, Q, _, _ = _avg_iq(self, TransProgram, c)
            zg[j] = I + 1j * Q
            c["prep_gain"] = int(self.w["pi_gain"])
            I, Q, _, _ = _avg_iq(self, TransProgram, c)
            ze[j] = I + 1j * Q
        fg = fit_resonance(fs, np.abs(zg) ** 2, expected_fwhm=self.w.get("kappa_mhz", 0.3))
        fe = fit_resonance(fs, np.abs(ze) ** 2, expected_fwhm=self.w.get("kappa_mhz", 0.3))
        D = np.abs(zg - ze)
        Ds = _smooth(D, w=5)
        self.node_data["chi"] = {"freqs": fs, "mag_g": np.abs(zg) ** 2, "mag_e": np.abs(ze) ** 2,
                                 "D": D, "D_smooth": Ds}
        k = nan_argmax(Ds)
        if k is None:
            raise TunerError("chi: separation trace is all NaN.")
        f_dmax = float(fs[k])
        if fg["ok"] and fe["ok"]:
            chi = 0.5 * (fe["f0"] - fg["f0"])
            kappa = 0.5 * (fg["fwhm"] + fe["fwhm"])
            f_mid = 0.5 * (fg["f0"] + fe["f0"])
            # |alpha_g - alpha_e| is exactly EVEN in the detuning, so the two dressed-peak
            # optima are degenerate and only |d| is determined by the model.  Pick the
            # branch the measured separation trace actually prefers.
            d_opt = optimal_readout_detuning(chi, kappa)
            cands = [f_mid - d_opt, f_mid + d_opt]
            f_analytic = min(cands, key=lambda x: abs(x - f_dmax))
            self.w["chi_mhz"], self.w["kappa_mhz"] = float(chi), float(kappa)
            # separation-per-photon versus the 2|chi| = kappa design optimum
            def _dsep(c, k):
                d = np.linspace(-3 * max(abs(c), k), 3 * max(abs(c), k), 2001)
                ag, ae = 1.0 / ((d - c) + 0.5j * k), 1.0 / ((d + c) + 0.5j * k)
                return float(np.max(np.abs(ag - ae)) / np.max(np.abs(ag)))
            d_now = _dsep(chi, kappa)
            d_opt = _dsep(0.5 * kappa, kappa)          # 2|chi| = kappa
            self.w["chi_kappa_penalty"] = float(d_opt / max(d_now, 1e-9))
            self._say("chi", "OK",
                      "separation-per-photon %.2f vs %.2f at the 2|chi|=kappa design "
                      "optimum -> this device is %.1fx below the best achievable at ANY "
                      "power; that is a CHIP property (chi and kappa), not a tuning knob"
                      % (d_now, d_opt, d_opt / max(d_now, 1e-9)))
            self._say("chi", "OK", "chi/2pi = %+.4f MHz, kappa/2pi = %.4f MHz, 2|chi|/kappa "
                                   "= %.2f -> %s" % (chi, kappa, abs(2 * chi) / max(kappa, 1e-9),
                      "drive the midpoint" if abs(2 * chi) <= kappa else "drive a dressed peak"))
            # trust the measured D-maximum, but only if it agrees with the model
            if abs(f_dmax - f_analytic) < max(kappa, 0.2):
                f_use = f_dmax
                note = "measured D-max (agrees with the analytic optimum to %.3f MHz)" % abs(f_dmax - f_analytic)
            else:
                f_use = f_analytic
                note = ("analytic optimum; the measured D-max at %.4f disagrees by %.3f MHz "
                        "and is probably noise" % (f_dmax, abs(f_dmax - f_analytic)))
        else:
            f_use, note = f_dmax, "measured D-max (chi fit failed, no analytic cross-check)"
        self.w["read_pulse_freq"] = round(float(f_use), 4)
        self.w["updated"].add("read_pulse_freq")
        self._say("chi", "OK", "readout frequency -> %.4f MHz [%s]" % (f_use, note))
        return {"f": f_use}, {"f": max(0.1 * self.w.get("kappa_mhz", 0.3), 0.01)}

    def _sweep_readout(self, node, candidates, apply_fn, shots):
        """Score a ladder of readout settings, drift-robustly.

        The readout on this system drifts tens of percent within a batch -- the SAME
        settings measured minutes apart gave 1.89 and 1.06 sigma on hardware -- so a
        single pass over a ladder partly ranks WHEN each point was measured rather than
        how good it is.  Sweeping twice in opposite order and averaging cancels a
        monotonic drift to first order, and the pass-to-pass spread is reported so the
        operator can see how much of the ranking is real."""
        n = len(candidates)
        seps = np.full((2, n), np.nan)
        fids = np.full((2, n), np.nan)
        outs = np.full((2, n), np.nan)
        for p_i, order in enumerate((list(range(n)), list(reversed(range(n))))):
            for j in order:
                cfg = self._cfg_for(node)
                apply_fn(cfg, candidates[j])
                ig, qg = _shots(self, cfg, [], self.w["drive_freq"], int(shots))
                ie, qe = _shots(self, cfg, [("pulse", int(self.w["pi_gain"]), 0.0)],
                                self.w["drive_freq"], int(shots))
                ss = single_shot_analysis(ig, qg, ie, qe)
                seps[p_i, j], fids[p_i, j] = ss["sep_sigma"], ss["fidelity"]
                outs[p_i, j] = ss["outlier_frac"]
        sep = np.nanmean(seps, axis=0)
        fid = np.nanmean(fids, axis=0)
        out = np.nanmax(outs, axis=0)
        spread = float(np.nanmax(np.abs(seps[0] - seps[1]))) if n else float("nan")
        best = float(np.nanmax(sep)) if np.any(np.isfinite(sep)) else float("nan")
        if np.isfinite(spread) and np.isfinite(best) and best > 0 and spread > 0.3 * best:
            self._say(node, "WARN",
                      "pass-to-pass spread %.2f sigma is %.0f%% of the best value -- the "
                      "readout is drifting faster than this ladder can be measured, so "
                      "the ranking is only partly real" % (spread, 100 * spread / best))
        return sep, fid, out, spread

    def _cal_readout_power(self):
        """Readout power, gated on the OUTLIER FRACTION.

        Fidelity alone rises monotonically with power until the blobs merge, and the
        power at which the readout stops being QND (measurement-induced transitions /
        ionization, which show up as shots belonging to neither blob) is BELOW that.  So
        only powers whose shots are consistent with a two-blob model are eligible."""
        P = self.P["readout_power"]
        g0 = int(self.w["read_pulse_gain"])
        gains = [int(round(min(max(g0 * r, 30), 32000))) for r in P["ratios"]]

        def _apply(cfg, g):
            cfg["read_pulse_gain"] = int(g)

        sep, fid, out, _spread = self._sweep_readout("readout_power", gains, _apply,
                                                     P["shots"])
        rows = []
        for j, g in enumerate(gains):
            rows.append({"gain": g, "sep": float(sep[j]), "fid": float(fid[j]),
                         "outlier": float(out[j])})
            self._say("readout_power", "OK", "gain %6d -> %.2f sigma, F=%.3f, outliers %.3f%s"
                      % (g, sep[j], fid[j], out[j],
                         "" if out[j] <= P["outlier_max"] else "  [REJECTED: not two-blob]"))
        self.node_data["readout_power"] = rows
        ok_rows = [r for r in rows if r["outlier"] <= P["outlier_max"] and np.isfinite(r["sep"])]
        if not ok_rows:
            raise TunerError("readout_power: every power failed the two-blob outlier gate "
                             "(min outlier fraction %.3f) -- the readout is not behaving "
                             "dispersively at any tested power."
                             % min(r["outlier"] for r in rows))
        best = max(ok_rows, key=lambda r: r["sep"])
        self.w["read_pulse_gain"] = int(best["gain"])
        self.w["updated"].add("read_pulse_gain")
        self._say("readout_power", "OK", "best eligible power: gain %d (%.2f sigma, F=%.3f)"
                  % (best["gain"], best["sep"], best["fid"]))
        return {"g": best["gain"]}, {"g": max(0.15 * best["gain"], 20)}

    def _cal_t1(self):
        """T1 -- required, not optional: it bounds the useful readout length, sets
        relax_delay, caps the pi-train length, and is the dominant contribution to the
        |e>-prep readout error that would otherwise be misread as pi infidelity."""
        P = self.P["t1"]
        cfg = self._cfg_for("t1")
        shots = int(P["shots"])
        tmax = P["t_max_us"]
        if tmax is None:
            tmax = 60.0
            # coarse bracket first so the fine grid is not wasted
            for probe in (10.0, 30.0, 90.0, 250.0):
                pop, sep, _ = _pop_with_local_refs(
                    self, cfg, [("pulse", int(self.w["pi_gain"]), 0.0), ("delay", probe)],
                    self.w["drive_freq"], self.w["pi_gain"], max(shots // 3, 150))
                if np.isfinite(pop) and pop < 0.4:
                    tmax = float(min(3.0 * probe, 400.0))
                    break
                tmax = float(min(3.0 * probe, 400.0))
        ts = np.linspace(0.05, float(tmax), int(P["points"]))
        order = np.random.permutation(ts.size)      # randomized: drift must not alias
        pops = np.full(ts.size, np.nan)
        errs = np.full(ts.size, np.nan)
        for idx in order:
            t = float(ts[idx])
            pop, sep, sem = _pop_with_local_refs(
                self, cfg, [("pulse", int(self.w["pi_gain"]), 0.0), ("delay", t)],
                self.w["drive_freq"], self.w["pi_gain"], shots)
            pops[idx], errs[idx] = pop, sem
        fit = fit_exp_decay(ts, pops)
        self.node_data["t1"] = {"t": ts, "pop": pops, "fit": fit["yfit"]}
        if not fit["ok"] or not np.isfinite(fit["tau"]):
            self._say("t1", "WARN", "T1 fit failed; assuming 30 us for downstream bounds")
            self.w["t1_us"] = 30.0
            return {"t1": 30.0}, {"t1": 1e9}
        self.w["t1_us"] = float(fit["tau"])
        # relax_delay was a blind BaseConfig value (3 ms here) applied to EVERY shot of
        # every later node.  5*T1 leaves <1% residual excitation and is typically 10-20x
        # faster, which is the difference between a 30-minute and a 3-hour run.
        old_relax = float(self.w["relax_delay"])
        new_relax = float(np.clip(5.0 * fit["tau"], 20.0, old_relax))
        if new_relax < 0.8 * old_relax:
            self.w["relax_delay"] = new_relax
            self._say("t1", "OK", "relax_delay %.0f -> %.0f us (5*T1; ~%.0fx less idle "
                                  "time per shot downstream)"
                      % (old_relax, new_relax, old_relax / max(new_relax, 1e-9)))
        self._say("t1", "OK", "T1 = %.1f +/- %.1f us" % (fit["tau"], fit["tau_err"]))
        return {"t1": fit["tau"]}, {"t1": max(0.3 * fit["tau"], 3 * fit["tau_err"])}

    def _cal_readout_len(self):
        """Integration length: SNR grows as sqrt(T) but the |e> state decays as T/T1, so
        there is a genuine optimum.  Candidates are capped at T1/2 -- beyond that the
        measurement is mostly watching the qubit decay."""
        P = self.P["readout_len"]
        t1 = float(self.w.get("t1_us", 30.0))
        cands = [L for L in P["lengths_us"] if L <= max(0.5 * t1, 2.0)]
        if not cands:
            cands = [min(P["lengths_us"])]
        def _apply(cfg, L):
            cfg["read_length"] = float(L)

        sep, fid, out, _spread = self._sweep_readout("readout_len", cands, _apply, P["shots"])
        rows = []
        for j, L in enumerate(cands):
            rows.append({"len": float(L), "sep": float(sep[j]), "fid": float(fid[j]),
                         "outlier": float(out[j])})
            self._say("readout_len", "OK", "%5.1f us -> %.2f sigma, F=%.3f"
                      % (L, sep[j], fid[j]))
        self.node_data["readout_len"] = rows
        ok_rows = [r for r in rows if np.isfinite(r["fid"])]
        if not ok_rows:
            raise TunerError("readout_len: no usable length.")
        best = max(ok_rows, key=lambda r: r["fid"])
        if len(ok_rows) > 1 and best["len"] in (ok_rows[0]["len"], ok_rows[-1]["len"]):
            self._say("readout_len", "WARN",
                      "the best length %.1f us is at an END of the tested ladder (%.1f-%.1f "
                      "us) -- the RANGE may be the limit rather than the optimum; extend "
                      "params['readout_len']['lengths_us'] (T1/2 = %.1f us allows more)"
                      % (best["len"], ok_rows[0]["len"], ok_rows[-1]["len"], 0.5 * t1))
        self.w["read_length"] = float(best["len"])
        self.w["updated"].add("read_length")
        self._say("readout_len", "OK", "best length %.1f us (F=%.3f, %.2f sigma; capped at "
                                       "T1/2 = %.1f us)" % (best["len"], best["fid"], best["sep"], 0.5 * t1))
        return {"L": best["len"]}, {"L": 0.4 * best["len"]}

    def _cal_single_shot(self):
        P = self.P["single_shot"]
        cfg = self._cfg_for("single_shot")
        shots = int(P["shots"])
        ig, qg = _shots(self, cfg, [], self.w["drive_freq"], shots)
        ie, qe = _shots(self, cfg, [("pulse", int(self.w["pi_gain"]), 0.0)],
                        self.w["drive_freq"], shots)
        ss = single_shot_analysis(ig, qg, ie, qe)
        self.node_data["single_shot"] = ss
        self.w["ss_fidelity"] = float(ss["fidelity"])
        self.w["ss_sep_sigma"] = float(ss["sep_sigma"])
        self._say("single_shot", "OK", "F=%.3f | P(e|g)=%.3f P(g|e)=%.3f | %.2f sigma | "
                                       "outliers %.3f | angle %.1f deg"
                  % (ss["fidelity"], ss["p_e_given_g"], ss["p_g_given_e"], ss["sep_sigma"],
                     ss["outlier_frac"], np.rad2deg(ss["theta"])))
        # separate what is readout overlap from what is real: at separation S the ideal
        # per-direction overlap error is Q(S/2); anything at or below that is pure overlap
        from math import erfc
        q_ideal = 0.5 * erfc(ss["sep_sigma"] / (2 * np.sqrt(2)))
        asym = ss["p_g_given_e"] - ss["p_e_given_g"]
        t1 = float(self.w.get("t1_us", np.nan))
        decay = 1.0 - np.exp(-float(self.w["read_length"]) / t1) if np.isfinite(t1) else np.nan
        self._say("single_shot", "OK",
                  "overlap floor for %.2f sigma is Q(S/2)=%.3f per direction; measured "
                  "asymmetry P(g|e)-P(e|g)=%.3f vs %.3f expected from T1 decay during the "
                  "%.1f us window" % (ss["sep_sigma"], q_ideal, asym,
                                      0.5 * decay if np.isfinite(decay) else float('nan'),
                                      self.w["read_length"]))
        # Persist the discrimination rotation so every OTHER runner integrates on the
        # separating axis.  theta was measured WITH the current res_phase already applied,
        # so the update must ACCUMULATE (overwriting rotates the axis to 2*theta and
        # compounds run over run); and the hardware sign convention is not knowable a
        # priori, so apply it, RE-MEASURE, and keep it only if the angle actually shrank.
        theta_deg = float(np.rad2deg(ss["theta"]))
        if abs(((theta_deg + 180.0) % 360.0) - 180.0) > 2.0:
            cur = float(self.w.get("res_phase", 0.0))
            applied = False
            for sgn in (-1.0, +1.0):
                trial = float((cur + sgn * theta_deg) % 360.0)
                c2 = dict(cfg)
                c2["res_phase"] = trial
                n2 = max(shots // 3, 400)
                g2 = _shots(self, c2, [], self.w["drive_freq"], n2)
                e2 = _shots(self, c2, [("pulse", int(self.w["pi_gain"]), 0.0)],
                            self.w["drive_freq"], n2)
                t2 = single_shot_analysis(g2[0], g2[1], e2[0], e2[1])
                new_ang = abs(((np.rad2deg(t2["theta"]) + 180.0) % 360.0) - 180.0)
                if new_ang < 0.5 * abs(((theta_deg + 180.0) % 360.0) - 180.0):
                    self.w["res_phase"] = trial
                    self.w["updated"].add("res_phase")
                    self._say("single_shot", "OK",
                              "res_phase %.1f -> %.1f deg (sign %+d verified: IQ angle "
                              "%.1f -> %.1f deg)" % (cur, trial, int(sgn), theta_deg, new_ang))
                    applied = True
                    break
            if not applied:
                self._say("single_shot", "WARN",
                          "res_phase correction reduced the IQ angle in NEITHER sign -- "
                          "not writing res_phase (an unverified sign would rotate every "
                          "other runner's readout the wrong way)")
        if ss["sep_sigma"] < float(P["min_sep_sigma"]):
            f_ideal = 1.0 - 2.0 * q_ideal          # best possible F at this separation
            at_limit = (f_ideal - ss["fidelity"]) < 0.03
            self._say("single_shot", "WARN",
                      "%.2f sigma < %.1f: single-shot discrimination is not meaningful. "
                      "Measured F=%.3f vs the ideal two-Gaussian limit %.3f for this "
                      "separation -> %s"
                      % (ss["sep_sigma"], P["min_sep_sigma"], ss["fidelity"], f_ideal,
                         "ALREADY AT THE LIMIT, so no discriminator or weighting change "
                         "can help -- only more SIGNAL (amplifier chain, chi/kappa, power)"
                         if at_limit else
                         "BELOW the limit, so there is headroom in the discrimination "
                         "itself (rotation angle, threshold, integration weights)"))
        return {"F": ss["fidelity"]}, {"F": 0.02}

    def _pi_train(self, cfg, gain, M, freq, shots):
        seq = int(M) * [("pulse", int(gain), 0.0)]
        return _pop_with_local_refs(self, cfg, seq, freq, self.w["pi_gain"], shots)

    def _cal_fine_pi_freq(self):
        """Drive frequency from the pi-train residual.

        A same-phase pi train is quadratically sensitive to detuning (the rotation axis
        tilts by atan(Delta/Omega)), so minimizing the SAME residual used for amplitude
        also calibrates the frequency -- sign-free, T2*-free, and using only driven
        evolution.  This is what replaces the Ramsey on a qubit whose T2* is too short."""
        P = self.P["fine_pi_freq"]
        cfg = self._cfg_for("fine_pi_freq")
        M = int(P["M"])
        f0 = float(self.w["drive_freq"])
        fs = f0 + np.linspace(-P["span_mhz"] / 2, P["span_mhz"] / 2, int(P["points"]))
        res = np.full(fs.size, np.nan)
        err = np.full(fs.size, np.nan)
        for j in np.random.permutation(fs.size):
            r, sep, sem = self._pi_train(cfg, self.w["pi_gain"], M, float(fs[j]), int(P["shots"]))
            res[j], err[j] = r, sem
        self.node_data["fine_pi_freq"] = {"freqs": fs, "res": res}
        v = parabola_vertex(fs, res, err)
        if not np.isfinite(v["x_min"]):
            self._say("fine_pi_freq", "WARN", "no usable minimum; keeping %.4f MHz" % f0)
            return {"f": f0}, {"f": 1e9}
        span = float(fs[-1] - fs[0])
        if not v["interior"] or not np.isfinite(v["x_err"]) or v["x_err"] > 0.25 * span:
            self._say("fine_pi_freq", "WARN",
                      "vertex %.4f +/- %.4f MHz is edge-pinned or poorly constrained "
                      "(window %.4f-%.4f) -- KEEPING %.4f MHz rather than committing it"
                      % (v["x_min"], v["x_err"], fs[0], fs[-1], f0))
            return {"f": f0}, {"f": 1e9}
        self.w["drive_freq"] = round(float(v["x_min"]), 4)
        self.w["updated"].add("qubit_pi_freq")
        self._say("fine_pi_freq", "OK", "pi drive frequency %.4f +/- %.4f MHz (M=%d train)"
                  % (v["x_min"], v["x_err"], M))
        return {"f": v["x_min"]}, {"f": max(3 * v["x_err"], 0.01)}

    def _cal_fine_pi_amp(self):
        """Pi amplitude by error-amplified minimization, with the CORRECT convergence
        statistic.

        The residual at the minimum is a decoherence floor and says nothing about how
        well the minimum is located; the calibration error is sigma(vertex), which the
        parabola fit gives directly.  We also require the vertex found at different M to
        AGREE -- a disagreement means one of them was noise or edge-pinned."""
        P = self.P["fine_pi_amp"]
        cfg = self._cfg_for("fine_pi_amp")
        shots = int(P["shots"])
        t1 = float(self.w.get("t1_us", 30.0))
        t_pi = 4.0 * float(self.cfg["sigma"])
        base = int(self.w["pi_gain"])
        history = []
        for M, frac in zip(P["M_list"], P["frac"]):
            M = int(M)
            if M * t_pi > 0.5 * t1:                  # train longer than T1/2 is noise
                self._say("fine_pi_amp", "WARN", "skipping M=%d (%.1f us train vs T1/2 = "
                          "%.1f us)" % (M, M * t_pi, 0.5 * t1))
                continue
            gains = np.unique(np.round(base * np.linspace(1 - frac, 1 + frac,
                                                          int(P["points"]))).astype(int))
            gains = gains[(gains > 0) & (gains <= 32000)]
            if gains.size < 5:
                continue
            res = np.full(gains.size, np.nan)
            err = np.full(gains.size, np.nan)
            for j in np.random.permutation(gains.size):
                r, sep, sem = self._pi_train(cfg, int(gains[j]), M, self.w["drive_freq"], shots)
                res[j], err[j] = r, sem
            if not np.any(np.isfinite(res)):
                self._say("fine_pi_amp", "WARN", "M=%d: all points NaN (dead reference)" % M)
                continue
            v = parabola_vertex(gains, res, err)
            if not np.isfinite(v["x_min"]):
                continue
            self.node_data.setdefault("fine_pi_amp", {})["M%d" % M] = \
                {"gains": gains, "res": res, "vertex": v["x_min"], "err": v["x_err"]}
            if not v["interior"]:
                self._say("fine_pi_amp", "WARN", "M=%d minimum at a window edge (%.0f in "
                          "%d-%d) -- widening next pass instead of narrowing"
                          % (M, v["x_min"], gains[0], gains[-1]))
                base = int(round(v["x_min"]))
                history.append({"M": M, "gain": base, "err": np.inf,
                                "floor": float(np.nanmin(res))})
                continue
            base = int(round(min(max(v["x_min"], 1), 32000)))
            history.append({"M": M, "gain": base, "err": float(v["x_err"]),
                            "floor": float(np.nanmin(res))})
            self._say("fine_pi_amp", "OK",
                      "M=%2d: pi gain %d +/- %.0f DAC (%.2f%% of pi); residual floor at the "
                      "minimum %.3f (a DECOHERENCE floor, not an angle error)"
                      % (M, base, v["x_err"], 100 * v["x_err"] / max(base, 1),
                         history[-1]["floor"]))
        if not history:
            raise TunerError("fine_pi_amp: no usable pass (all NaN, edge-pinned, or the "
                             "train exceeds T1/2).")
        finals = [h for h in history if np.isfinite(h["err"])]
        if not finals:
            raise TunerError("fine_pi_amp: every pass was edge-pinned -- widen "
                             "params['fine_pi_amp']['frac'].")
        best = min(finals, key=lambda h: h["err"])
        self.w["pi_gain"] = int(best["gain"])
        self.w["pi_gain_err"] = float(best["err"])
        self.w["updated"].add("qubit_pi_gain")
        # cross-M agreement: independent passes must land in the same place
        agree = True
        if len(finals) >= 2:
            spread = max(h["gain"] for h in finals) - min(h["gain"] for h in finals)
            tol = 3.0 * max(h["err"] for h in finals) + 0.005 * best["gain"]
            agree = spread <= tol
            self._say("fine_pi_amp", "OK" if agree else "WARN",
                      "cross-M agreement: vertices %s spread %d DAC vs %.0f tolerance -> %s"
                      % ([h["gain"] for h in finals], spread, tol,
                         "consistent" if agree else "INCONSISTENT (one pass is unreliable)"))
        frac_err = best["err"] / max(best["gain"], 1)
        self.w["pi_converged"] = bool(agree and frac_err <= float(P["tol_frac"]))
        self._say("fine_pi_amp", "OK" if self.w["pi_converged"] else "WARN",
                  "FINAL pi gain %d +/- %.0f DAC = %.3f%% (target %.1f%%) -> %s"
                  % (best["gain"], best["err"], 100 * frac_err, 100 * P["tol_frac"],
                     "converged" if self.w["pi_converged"] else "not converged"))
        return {"g": best["gain"]}, {"g": max(3 * best["err"], 0.004 * best["gain"])}

    # ------------------------------------------------------------------ engine
    def _score(self):
        """Scalar quality used for best-so-far.  Single-shot separation is the thing
        everything else is measured through, so it leads; the pi precision breaks ties."""
        sep = float(self.w.get("ss_sep_sigma", 0.0))
        pig = float(self.w.get("pi_gain", 1))
        pie = float(self.w.get("pi_gain_err", np.inf))
        prec = 0.0 if not np.isfinite(pie) else max(0.0, 1.0 - (pie / max(pig, 1)) / 0.02)
        return sep + 0.25 * prec

    def _snapshot(self):
        return {k: (set(v) if isinstance(v, set) else v) for k, v in self.w.items()}

    def maintain(self):
        """Sweep the graph until nothing is stale.  Recalibrating a node whose value MOVED
        by more than its own uncertainty marks its dependents stale, so a readout change
        automatically forces the spec/Rabi that were measured through the old readout to
        be re-measured -- the invalidation Optimus formalises and the manual QUA loop does
        by hand."""
        # Seed from the PRE-calibration state.  With an empty dict, `old` is None on
        # every node's first visit, the moved/stale block is skipped, and the graph
        # degenerates into exactly one straight-line pass while printing "FIXED POINT
        # reached" -- i.e. the entire architecture becomes dead code.
        values = {
            "resonator":     {"f0": float(self.w["read_pulse_freq"])},
            "spec":          {"f": float(self.w["qubit_freq"])},
            "rough_pi":      {"g": float(self.w["pi_gain"])},
            "chi":           {"f": float(self.w["read_pulse_freq"])},
            "readout_power": {"g": float(self.w["read_pulse_gain"])},
            "readout_len":   {"L": float(self.w["read_length"])},
        }
        best_score, best_state = -np.inf, None
        for rnd in range(1, int(self.P["max_rounds"]) + 1):
            todo = [n for n, _, _ in GRAPH if self.stale[n]]
            if not todo:
                self._say("graph", "OK", "round %d: nothing stale -- FIXED POINT reached" % rnd)
                break
            print("-" * 78)
            self._say("graph", "OK", "round %d: recalibrating %s" % (rnd, ", ".join(todo)))
            for name, deps, meth in GRAPH:
                if not self.stale[name]:
                    continue
                new, tol = getattr(self, meth)()
                self.stale[name] = False
                old = values.get(name)
                values[name] = new
                if old is not None:
                    moved = [k for k in new
                             if np.isfinite(new[k]) and np.isfinite(old.get(k, np.nan))
                             and abs(float(new[k]) - float(old[k])) > float(tol[k])]
                    if moved:
                        self._say("graph", "OK", "%s moved (%s) -> dependents stale"
                                  % (name, ", ".join("%s %.4g->%.4g" % (k, old[k], new[k])
                                                     for k in moved)))
                        self._mark_dependents_stale(name)
            s = self._score()
            self._say("graph", "OK", "round %d score %.3f (separation %.2f sigma, pi %s)"
                      % (rnd, s, self.w.get("ss_sep_sigma", float('nan')),
                         ("+/- %.0f DAC" % self.w["pi_gain_err"])
                         if np.isfinite(self.w.get("pi_gain_err", np.inf)) else "unmeasured"))
            if s > best_score:
                best_score, best_state = s, self._snapshot()
            else:
                self._say("graph", "WARN", "round %d did not improve on %.3f -- keeping the "
                          "best-so-far state (a worse round is never committed)" % (rnd, best_score))
        if best_state is not None and self._score() < best_score:
            self.w = best_state
            self._say("graph", "OK", "restored best-so-far state (score %.3f)" % best_score)
        return best_score

    # ------------------------------------------------------------------ orchestration
    def acquire(self, progress=False, plotDisp=False):
        cfg = self.cfg
        self.data = {}
        if self.soccfg is not None:
            for ch, f, z, lbl in ((cfg["qubit_ch"], cfg.get("qubit_pi_freq", cfg["qubit_freq"]),
                                   cfg["qubit_nqz"], "qubit drive"),
                                  (cfg["res_ch"], cfg["read_pulse_freq"], cfg["nqz"], "readout")):
                warn = check_nyquist(self.soccfg, ch, f, z, lbl)
                if warn:
                    self._say("nyquist", "WARN", warn)
            fsq = gen_sample_rate(self.soccfg, cfg["qubit_ch"])
            if fsq:
                fq = float(cfg.get("qubit_pi_freq", cfg["qubit_freq"]))
                self._say("nyquist", "OK",
                          "qubit gen fs = %.1f MHz; driving %.4f MHz (zone %d, nqz=%d). "
                          "Half of it is %.4f MHz -- a response there instead means the "
                          "qubit is being driven two-photon rather than directly."
                          % (fsq, fq, int(fq // (fsq / 2.0)) + 1, cfg["qubit_nqz"], fq / 2))
        if int(cfg.get("ff_park_gain", 0)) != 0:
            raise TunerError("this tuner is PARK-ONLY but ff_park_gain=%s; calibrating "
                             "here would write a pi measured at the wrong flux."
                             % cfg.get("ff_park_gain"))
        self.w = {
            "read_pulse_freq": float(cfg["read_pulse_freq"]),
            "read_pulse_gain": int(cfg["read_pulse_gain"]),
            "read_length": float(cfg["read_length"]),
            "res_phase": float(cfg.get("res_phase", 0.0)),
            "relax_delay": float(cfg["relax_delay"]),
            "qubit_freq": float(cfg["qubit_freq"]),
            "drive_freq": float(cfg.get("qubit_pi_freq", cfg["qubit_freq"])),
            "pi_gain": int(cfg["qubit_pi_gain"]),
            "pi_gain_err": np.inf,
            "pi_converged": False,
            "updated": set(),
        }
        orig = {k: cfg.get(k) for k in
                ("read_pulse_freq", "read_pulse_gain", "read_length", "res_phase",
                 "qubit_freq", "qubit_pi_freq", "qubit_pi_gain")}
        print("=" * 78)
        print("AUTO TUNER (calibration graph, fixed-point)  %s" % self.element)
        print("  start: read %.4f MHz / gain %d / %.1f us | qubit %.4f | pi %.4f @ %d"
              % (self.w["read_pulse_freq"], self.w["read_pulse_gain"], self.w["read_length"],
                 self.w["qubit_freq"], self.w["drive_freq"], self.w["pi_gain"]))
        print("=" * 78)
        failure, success = None, False
        try:
            self.maintain()
            ss_ok = self.w.get("ss_sep_sigma", 0.0) >= self.P["single_shot"]["min_sep_sigma"]
            pi_ok = bool(self.w.get("pi_converged", False))
            self.w["qubit_ok"], self.w["readout_ok"] = pi_ok, bool(ss_ok)
            success = bool(pi_ok and ss_ok)
            if pi_ok and not ss_ok:
                # The pi calibration is a MINIMUM-LOCATION measurement, which is far more
                # robust to readout SNR than an absolute fidelity -- and three independent
                # M values agreeing is strong evidence on its own.  Withholding a good pi
                # because the chip's readout is weak would be the wrong call, so the qubit
                # and readout results are gated separately.
                self._say("verdict", "OK",
                          "QUBIT calibration converged (pi %d +/- %.0f DAC) and IS "
                          "trustworthy: the pi-train vertex is a minimum LOCATION, which "
                          "does not need single-shot discrimination, and %d independent M "
                          "values agree."
                          % (self.w["pi_gain"], self.w.get("pi_gain_err", float('nan')),
                             len(self.node_data.get("fine_pi_amp", {}))))
                self._say("verdict", "WARN",
                          "READOUT separation %.2f sigma is below the %.1f sigma floor, so "
                          "the readout values are the best FOUND but are not a good "
                          "readout.%s"
                          % (self.w.get("ss_sep_sigma", float('nan')),
                             self.P["single_shot"]["min_sep_sigma"],
                             (" With 2|chi|/kappa = %.2f this chip is %.1fx below the best "
                              "separation achievable at any power, so the remaining gap is "
                              "the amplifier chain (TWPA/JPA) or the chip itself."
                              % (abs(2 * self.w["chi_mhz"]) / self.w["kappa_mhz"],
                                 self.w["chi_kappa_penalty"]))
                             if "chi_kappa_penalty" in self.w else ""))
        except TunerError as err:
            failure = str(err)
            self._say("verdict", "FAIL", failure)
        except KeyboardInterrupt:
            failure = "interrupted by user"
            self._say("verdict", "WARN", "interrupted -- partial data is still saved")

        tuned = {}
        keymap = [("read_pulse_freq", "read_pulse_freq"), ("read_pulse_gain", "read_pulse_gain"),
                  ("read_length", "read_length"), ("res_phase", "res_phase"),
                  ("qubit_freq", "qubit_freq"), ("qubit_pi_freq", "drive_freq"),
                  ("qubit_pi_gain", "pi_gain")]
        for cfg_key, w_key in keymap:
            if cfg_key in self.w["updated"]:
                v = self.w[w_key]
                tuned[cfg_key] = int(v) if cfg_key in ("read_pulse_gain", "qubit_pi_gain") else float(v)
        print("-" * 78)
        for line in self.report_lines:
            print("  " + line)
        print("-" * 78)
        print("RESULT: %s" % ("SUCCESS" if success else ("FAILED (%s)" % failure if failure
                                                         else "NOT CONVERGED")))
        for k in sorted(tuned):
            was = orig.get(k)
            print("   %-18s %-14s (was %s)" % (k, tuned[k], was))
        for k, label in (("t1_us", "T1"), ("chi_mhz", "chi/2pi"), ("kappa_mhz", "kappa/2pi"),
                         ("ss_fidelity", "SS fidelity"), ("ss_sep_sigma", "SS separation")):
            if k in self.w and np.isfinite(self.w[k]):
                print("   %-18s %.4g%s" % (label, self.w[k],
                                           " us" if k == "t1_us" else
                                           (" MHz" if "mhz" in k else
                                            (" sigma" if "sep" in k else ""))))
        if not success:
            print("   (config NOT written)")
        print("=" * 78)

        self.data.update({
            "success": success, "failure": failure, "tuned": tuned,
            "qubit_ok": bool(self.w.get("qubit_ok", False)),
            "readout_ok": bool(self.w.get("readout_ok", False)),
            "working": {k: (sorted(v) if isinstance(v, set) else v) for k, v in self.w.items()},
            "nodes": self.node_data, "report": list(self.report_lines),
            "time": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        })
        try:
            fig = self._plot(success)
            if plotDisp:
                plt.show(block=False)
                plt.pause(0.1)
            else:
                plt.close(fig)
        except Exception as perr:
            print("[auto-tune] summary plot failed (%s); data still saved." % perr)
            plt.close("all")
        self.pickle_data()
        return {'config': cfg, 'data': self.data}

    # ------------------------------------------------------------------ plotting
    @staticmethod
    def _pair(ax, x, y, *a, **kw):
        x, y = np.asarray(x), np.asarray(y)
        if x.ndim == 1 and y.ndim == 1 and x.size == y.size and x.size:
            ax.plot(x, y, *a, **kw)

    def _plot(self, success):
        d = self.node_data
        fig, axs = plt.subplots(3, 3, figsize=(16, 11))
        ax = axs[0, 0]
        if "resonator" in d:
            self._pair(ax, d["resonator"]["freqs"], d["resonator"]["mag"], ".", ms=3)
            self._pair(ax, d["resonator"]["freqs"], d["resonator"]["fit"], "-", lw=1)
        ax.set_title("resonator"); ax.set_xlabel("MHz")
        ax = axs[0, 1]
        if "spec" in d:
            self._pair(ax, d["spec"]["freqs"], d["spec"]["sig"], ".", ms=3)
            self._pair(ax, d["spec"]["freqs"], d["spec"]["fit"], "-", lw=1)
        ax.axvline(self.w.get("qubit_freq", np.nan), color="r", ls="--", lw=0.8)
        ax.set_title("qubit spec"); ax.set_xlabel("MHz")
        ax = axs[0, 2]
        if "rough_pi" in d:
            self._pair(ax, d["rough_pi"]["gains"], d["rough_pi"]["sig"], ".", ms=3)
            self._pair(ax, d["rough_pi"]["gains"], d["rough_pi"]["fit"], "-", lw=1)
        ax.axvline(self.w.get("pi_gain", np.nan), color="r", ls="--", lw=0.8)
        ax.set_title("rough Rabi"); ax.set_xlabel("gain")
        ax = axs[1, 0]
        if "chi" in d:
            self._pair(ax, d["chi"]["freqs"], d["chi"]["mag_g"], "-", lw=1, label="|g>")
            self._pair(ax, d["chi"]["freqs"], d["chi"]["mag_e"], "-", lw=1, label="|e>")
            ax2 = ax.twinx()
            self._pair(ax2, d["chi"]["freqs"], d["chi"]["D_smooth"], "k--", lw=1)
            ax2.set_ylabel("|g>-|e> separation")
            ax.legend(fontsize=7)
        ax.axvline(self.w.get("read_pulse_freq", np.nan), color="r", ls="--", lw=0.8)
        ax.set_title("chi: chi=%.3f kappa=%.3f MHz" % (self.w.get("chi_mhz", np.nan),
                                                       self.w.get("kappa_mhz", np.nan)))
        ax.set_xlabel("MHz")
        ax = axs[1, 1]
        if "readout_power" in d:
            r = d["readout_power"]
            g = [x["gain"] for x in r]
            self._pair(ax, g, [x["sep"] for x in r], "o-", ms=3, label="sigma")
            self._pair(ax, g, [10 * x["outlier"] for x in r], "s--", ms=3, label="10x outlier")
            ax.set_xscale("log"); ax.legend(fontsize=7)
        ax.set_title("readout power"); ax.set_xlabel("gain")
        ax = axs[1, 2]
        if "readout_len" in d:
            r = d["readout_len"]
            self._pair(ax, [x["len"] for x in r], [x["fid"] for x in r], "o-", ms=3)
        ax.set_title("readout length (T1=%.0f us)" % self.w.get("t1_us", np.nan))
        ax.set_xlabel("us")
        ax = axs[2, 0]
        if "t1" in d:
            self._pair(ax, d["t1"]["t"], d["t1"]["pop"], ".", ms=4)
            self._pair(ax, d["t1"]["t"], d["t1"]["fit"], "-", lw=1)
        ax.set_title("T1 = %.1f us" % self.w.get("t1_us", np.nan)); ax.set_xlabel("us")
        ax = axs[2, 1]
        ss = d.get("single_shot")
        if ss and len(ss.get("xg", [])):
            bins = np.linspace(min(ss["xg"].min(), ss["xe"].min()),
                               max(ss["xg"].max(), ss["xe"].max()), 70)
            ax.hist(ss["xg"], bins=bins, alpha=0.6, label="|g>")
            ax.hist(ss["xe"], bins=bins, alpha=0.6, label="|e>")
            ax.axvline(ss["threshold"], color="k", ls="--", lw=0.8)
            ax.legend(fontsize=7)
            ax.set_title("single shot F=%.3f (%.2f sigma)" % (ss["fidelity"], ss["sep_sigma"]))
        ax = axs[2, 2]
        if "fine_pi_amp" in d:
            for name, rd in sorted(d["fine_pi_amp"].items(), key=lambda kv: int(kv[0][1:])):
                self._pair(ax, rd["gains"], rd["res"], ".-", ms=3, lw=0.8, label=name)
            ax.legend(fontsize=7)
        ax.axvline(self.w.get("pi_gain", np.nan), color="r", ls="--", lw=0.8)
        ax.set_title("fine pi (train residual)"); ax.set_xlabel("gain")
        fig.suptitle("AutoTuner %s  %s  %s" % (self.element, self.time_string,
                                               "SUCCESS" if success else "FAILED"))
        fig.tight_layout()
        plt.savefig(self.iname, dpi=140, bbox_inches="tight")
        return fig

    def save_data(self, data=None):
        print('Saving %s' % self.fname)
        flat = {}
        for node, nd in self.node_data.items():
            if isinstance(nd, dict):
                for k, v in nd.items():
                    if isinstance(v, np.ndarray) and v.dtype != object:
                        flat["%s_%s" % (node, k)] = v
                    elif isinstance(v, dict):
                        for k2, v2 in v.items():
                            if isinstance(v2, np.ndarray) and v2.dtype != object:
                                flat["%s_%s_%s" % (node, k, k2)] = v2
            elif isinstance(nd, list) and nd and isinstance(nd[0], dict):
                for key in nd[0]:
                    try:
                        flat["%s_%s" % (node, key)] = np.array([r[key] for r in nd], dtype=float)
                    except Exception:
                        pass
        super().save_data(data=flat)
