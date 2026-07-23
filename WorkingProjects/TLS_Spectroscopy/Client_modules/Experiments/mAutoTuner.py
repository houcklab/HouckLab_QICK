import copy
import datetime
import warnings
from statistics import NormalDist

import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit, OptimizeWarning

from qick import AveragerProgram, RAveragerProgram

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.acquisition import suppress_stdout
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import (
    add_qubit_gaussian, explicit_flat_top_fields, pulse_fingerprint,
    readout_drive_length_us, set_readout_pulse,
)



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


def peak_significance(freqs, sig, f0, fwhm):
    """How many sigma of signal sit at a KNOWN frequency.

    Re-fitting a repeat scan blind asks the much harder question "is there a line
    anywhere", and a marginal-but-real line fails it.  Here the hypothesis is already
    fixed by the first scan, so the test is a targeted one: compare the peak inside one
    linewidth of the candidate against the baseline everywhere else."""
    f = np.asarray(freqs, dtype=float)
    y = np.asarray(sig, dtype=float)
    good = np.isfinite(f) & np.isfinite(y)
    f, y = f[good], y[good]
    if f.size < 8:
        return 0.0
    sel = np.abs(f - float(f0)) <= max(float(fwhm), 0.5)
    if sel.sum() < 2 or (~sel).sum() < 5:
        return 0.0
    base = float(np.median(y[~sel]))
    s = _noise_sigma(y)
    return float((np.max(y[sel]) - base) / max(s, 1e-12))


def fit_notch_complex(freqs, z, f0_guess=None, kappa_guess=None):
    """Complex notch-resonator fit that ALLOWS an asymmetric lineshape.

    A hanger resonator's dip is only symmetric when the feedline is perfectly matched.
    Real ones never are: the mismatch rotates the resonance circle, which appears in
    |S21| as a Fano-asymmetric dip with one shoulder higher than the other.  Fitting a
    symmetric Lorentzian to that pulls f0 toward the shallow shoulder and inflates kappa,
    and both errors propagate -- f0 sets where the readout sits and kappa sets the
    2|chi|/kappa verdict.

    Model, to first order in the environment across a narrow span:

        z(f) = exp(-2i*pi*tau*x) * [A + B*x - C / (1 + 2i*x/kappa)],   x = f - f0

    A (background), B (chain slope) and C (resonance) are COMPLEX and enter LINEARLY, so
    for any trial (f0, kappa, tau) they follow from an exact least-squares solve and only
    three real parameters are ever searched.  The phase of C/A is the mismatch angle: 0 for
    a symmetric dip, non-zero for a Fano-asymmetric one.  Fitting the complex trace rather
    than |S21| is also what makes kappa right -- magnitude-fitting discards the phase,
    which is where most of the linewidth information lives.

    tau (cable delay) is NOT optional.  Over a few MHz a metre of cable winds the phase by
    more than a radian and no linear background can absorb it.  Omitting it is exactly why
    this fit converged on synthetic traces with a flat background and then failed on real
    hardware data -- the synthetic test had been built to match the model's own
    assumption."""
    f = np.asarray(freqs, dtype=float)
    zz = np.asarray(z, dtype=complex)
    good = np.isfinite(f) & np.isfinite(zz.real) & np.isfinite(zz.imag)
    f, zz = f[good], zz[good]
    n = f.size
    out = {"ok": False, "f0": np.nan, "f0_err": np.nan, "fwhm": np.nan,
           "asym_deg": np.nan, "snr": 0.0, "yfit": None}
    if n < 12:
        return out
    span = float(f.max() - f.min())
    if span <= 0:
        return out
    if f0_guess is None or not np.isfinite(f0_guess):
        f0_guess = float(f[int(np.argmin(np.abs(zz)))])
    if kappa_guess is None or not np.isfinite(kappa_guess) or kappa_guess <= 0:
        kappa_guess = max(span / 10.0, 1e-6)

    tau_max = 2.0 / span
    try:
        ph = np.unwrap(np.angle(zz))
        k = max(int(0.3 * n), 4)
        idx = np.r_[0:k, n - k:n]
        slope = float(np.polyfit(f[idx], ph[idx], 1)[0])
        tau0 = float(np.clip(-slope / (2.0 * np.pi), -tau_max, tau_max))
    except Exception:
        tau0 = 0.0

    def solve(fr, kap, tau):
        x = f - fr
        M = np.column_stack([np.ones(n), x, -1.0 / (1.0 + 2j * x / kap)])
        w = zz * np.exp(2j * np.pi * tau * x)
        try:
            p, _res, _rank, _sv = np.linalg.lstsq(M, w, rcond=None)
        except np.linalg.LinAlgError:
            return np.inf, None, None
        r = w - M.dot(p)
        return float(np.real(np.vdot(r, r))), p, M

    def cost(theta):
        fr, lk, tau = float(theta[0]), float(theta[1]), float(theta[2])
        kap = float(np.exp(lk))
        if not (f.min() - span <= fr <= f.max() + span):
            return 1e30
        if not (1e-7 <= kap <= 10.0 * span) or abs(tau) > tau_max:
            return 1e30
        s = solve(fr, kap, tau)[0]
        return s if np.isfinite(s) else 1e30

    from scipy.optimize import minimize
    best = None
    starts = []
    for fr0 in (f0_guess, f0_guess - 0.1 * span, f0_guess + 0.1 * span):
        for kr in (0.3, 1.0, 3.0):
            for t0 in (tau0, 0.0):
                starts.append((fr0, np.log(max(kappa_guess * kr, 1e-7)), t0))
    for th0 in starts:
        try:
            r = minimize(cost, np.array(th0), method="Nelder-Mead",
                         options={"xatol": span * 1e-7, "fatol": 1e-12, "maxiter": 4000})
        except Exception:
            continue
        if r.fun < 1e29 and (best is None or r.fun < best.fun):
            best = r
    if best is None:
        return out
    fr = float(best.x[0])
    kap = float(np.exp(best.x[1]))
    tau = float(best.x[2])
    smin, p, M = solve(fr, kap, tau)
    if p is None or not np.isfinite(smin):
        return out
    if not (f.min() <= fr <= f.max()) or not (0 < kap <= 2.0 * span):
        return out

    dof = max(2 * n - 9, 1)
    sigma2 = smin / dof
    hf, hk = span * 1e-3, kap * 1e-2
    lk = np.log(kap)

    def _c(a, b):
        return cost([a, b, tau])

    try:
        sff = (_c(fr + hf, lk) - 2 * smin + _c(fr - hf, lk)) / hf ** 2
        skk = (_c(fr, np.log(kap + hk)) - 2 * smin
               + _c(fr, np.log(max(kap - hk, 1e-9)))) / hk ** 2
        sfk = (_c(fr + hf, np.log(kap + hk)) - _c(fr + hf, np.log(max(kap - hk, 1e-9)))
               - _c(fr - hf, np.log(kap + hk))
               + _c(fr - hf, np.log(max(kap - hk, 1e-9)))) / (4 * hf * hk)
        H = np.array([[sff, sfk], [sfk, skk]], dtype=float)
        cov = 2.0 * sigma2 * np.linalg.inv(H)
        f0_err = float(np.sqrt(abs(cov[0, 0])))
    except Exception:
        f0_err = float(kap / 10.0)
    if not np.isfinite(f0_err) or f0_err <= 0:
        f0_err = float(kap / 10.0)

    A, B, C = p[0], p[1], p[2]
    asym = float(np.rad2deg(np.angle(C / A))) if abs(A) > 0 else np.nan
    if asym > 180.0:
        asym -= 360.0
    model = M.dot(p)
    depth = float(abs(C))
    resid = float(np.sqrt(sigma2))
    out.update({"ok": bool(depth > 3.0 * resid), "f0": fr, "f0_err": f0_err,
                "fwhm": kap, "asym_deg": asym, "snr": depth / max(resid, 1e-15),
                "yfit": np.abs(model) ** 2, "freqs": f, "depth": depth})
    return out


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
    snr = depth / _noise_sigma(mag)
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
    d = np.linspace(0.0, span, 2001)
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
    if a <= 0:
        return {"x_min": float(x[k]), "x_err": np.inf,
                "interior": bool(0 < k < x.size - 1), "curvature": a}
    xv = -b / (2.0 * a) + xc
    xerr = np.inf
    if np.all(np.isfinite(cov)):
        dvda, dvdb = b / (2.0 * a * a), -1.0 / (2.0 * a)
        var = (dvda ** 2) * cov[0, 0] + (dvdb ** 2) * cov[1, 1] + 2 * dvda * dvdb * cov[0, 1]
        if np.isfinite(var) and var >= 0:
            xerr = float(np.sqrt(var))
    interior = bool(x.min() < xv < x.max() and 0 < k < x.size - 1)
    if not (x.min() <= xv <= x.max()):
        xv = float(x[k])
    return {"x_min": float(xv), "x_err": xerr, "interior": interior, "curvature": a}


def sparse_phase_estimate(y_minus, y_zero, y_plus, se_minus, se_zero, se_plus,
                          target_angle, beta=np.pi / 2.0):
    """Three-point, offset/contrast-independent phase estimate.

    For ``y(phi) = C + A*cos(phi)`` the samples are taken at ``phi-beta``,
    ``phi`` and ``phi+beta``.  The usual sparse phase estimator is recovered at
    beta=pi/2; keeping beta explicit accounts for the integer DAC rounding of the
    two probe gains.  ``target_angle`` selects the phase branch (N*pi for an odd
    N-pulse train).  Standard errors are propagated through atan2, including the
    covariance created because the same three samples enter both quadratures.
    """
    vals = np.asarray([y_minus, y_zero, y_plus], dtype=float)
    ses = np.asarray([se_minus, se_zero, se_plus], dtype=float)
    out = {"ok": False, "phase": np.nan, "phase_err": np.inf, "phase_snr": 0.0,
           "x": np.nan, "y": np.nan, "beta": float(beta)}
    if (not np.all(np.isfinite(vals)) or not np.all(np.isfinite(ses))
            or np.any(ses <= 0)):
        return out
    sb, cb = float(np.sin(beta)), float(np.cos(beta))
    if abs(sb) < 1e-6 or abs(1.0 - cb) < 1e-6:
        return out

    # atan2(yq, xq) estimates phi.  Coefficients are retained explicitly so the
    # uncertainty includes the shared-sample covariance.
    cy = np.array([1.0 / sb, 0.0, -1.0 / sb])
    cx = np.array([-1.0 / (1.0 - cb), 2.0 / (1.0 - cb),
                   -1.0 / (1.0 - cb)])
    yq, xq = float(cy @ vals), float(cx @ vals)
    var = ses ** 2
    vy, vx = float((cy ** 2) @ var), float((cx ** 2) @ var)
    cxy = float((cx * cy) @ var)
    radius2 = xq * xq + yq * yq
    if not np.isfinite(radius2) or radius2 <= 0:
        return out
    phase0 = float(np.arctan2(yq, xq))
    phase = phase0 + 2.0 * np.pi * round((float(target_angle) - phase0) / (2.0 * np.pi))
    vphase = (xq * xq * vy + yq * yq * vx - 2.0 * xq * yq * cxy) / (radius2 ** 2)
    phase_err = float(np.sqrt(max(vphase, 0.0)))
    # Full two-quadrature significance (Mahalanobis radius), not contrast divided
    # by the single-shot width.
    cov = np.array([[vx, cxy], [cxy, vy]], dtype=float)
    try:
        snr2 = float(np.array([xq, yq]) @ np.linalg.pinv(cov) @ np.array([xq, yq]))
        phase_snr = float(np.sqrt(max(snr2, 0.0)))
    except Exception:
        phase_snr = 0.0
    out.update({"ok": bool(np.isfinite(phase_err) and phase_snr > 0.0),
                "phase": phase, "phase_err": phase_err, "phase_snr": phase_snr,
                "x": xq, "y": yq})
    return out


def fit_zero_crossing(x, y, yerr, x_prior, min_slope_snr=3.0):
    """Locate the bracketed signed zero nearest a trusted prior.

    Repeated-pulse frequency and audit signals have many remote zeroes.  A global
    polynomial or sinusoid can therefore return a beautifully precise alias.  This
    helper first requires an observed sign bracket, chooses the bracket nearest the
    prior, and only then performs a local weighted line fit for a sub-grid root and
    uncertainty.  The covariance is inflated by reduced chi-square when the point
    errors do not explain the local scatter.
    """
    xx, yy, ee = (np.asarray(v, dtype=float) for v in (x, y, yerr))
    good = np.isfinite(xx) & np.isfinite(yy) & np.isfinite(ee) & (ee > 0)
    xx, yy, ee = xx[good], yy[good], ee[good]
    out = {"ok": False, "root": np.nan, "root_err": np.inf, "slope": 0.0,
           "slope_snr": 0.0, "bracket": None, "yfit": np.full(xx.shape, np.nan)}
    if xx.size < 3:
        return out
    order = np.argsort(xx)
    xx, yy, ee = xx[order], yy[order], ee[order]
    brackets = []
    for j in range(xx.size - 1):
        if yy[j] == 0.0 or yy[j + 1] == 0.0 or yy[j] * yy[j + 1] < 0.0:
            den = yy[j + 1] - yy[j]
            r = (0.5 * (xx[j] + xx[j + 1]) if den == 0 else
                 xx[j] - yy[j] * (xx[j + 1] - xx[j]) / den)
            brackets.append((abs(float(r) - float(x_prior)), j, float(r)))
    if not brackets:
        return out
    _, j, _ = min(brackets)
    lo, hi = max(0, j - 1), min(xx.size, j + 3)
    xs, ys, es = xx[lo:hi], yy[lo:hi], ee[lo:hi]
    if xs.size < 3:
        return out
    xc = float(np.mean(xs))
    A = np.column_stack([xs - xc, np.ones(xs.size)])
    W = np.diag(1.0 / es ** 2)
    try:
        cov = np.linalg.inv(A.T @ W @ A)
        coef = cov @ (A.T @ W @ ys)
    except np.linalg.LinAlgError:
        return out
    slope, intercept = float(coef[0]), float(coef[1])
    if abs(slope) < 1e-15:
        return out
    resid = ys - A @ coef
    dof = max(xs.size - 2, 1)
    red = float(np.sum((resid / es) ** 2) / dof)
    cov *= max(red, 1.0)
    root = xc - intercept / slope
    grad = np.array([intercept / (slope * slope), -1.0 / slope])
    root_var = float(grad @ cov @ grad)
    root_err = float(np.sqrt(max(root_var, 0.0)))
    slope_err = float(np.sqrt(max(cov[0, 0], 0.0)))
    slope_snr = abs(slope) / max(slope_err, 1e-15)
    dx = float(np.median(np.diff(xx))) if xx.size > 1 else 0.0
    interior = bool(xx[0] < root < xx[-1])
    local = bool(xx[j] - abs(dx) <= root <= xx[j + 1] + abs(dx))
    out.update({"ok": bool(interior and local and np.isfinite(root_err)
                            and slope_snr >= float(min_slope_snr)),
                "root": float(root), "root_err": root_err, "slope": slope,
                "slope_snr": float(slope_snr),
                "bracket": (float(xx[j]), float(xx[j + 1])),
                "yfit": slope * (xx - xc) + intercept, "x": xx, "y": yy})
    return out


def fit_symmetric_zero(x, y, yerr, x_prior, min_side_snr=4.0, wavenumber=None):
    """Signed zero from the centre and its nearest symmetric neighbours.

    This is the local, model-light audit estimator.  It uses only the maximally linear
    central half of the sine syndrome, so decoherence-induced envelope curvature at the
    outer diagnostic points cannot inflate or bias the answer.
    """
    xx, yy, ee = (np.asarray(v, dtype=float) for v in (x, y, yerr))
    good = np.isfinite(xx) & np.isfinite(yy) & np.isfinite(ee) & (ee > 0)
    xx, yy, ee = xx[good], yy[good], ee[good]
    out = {"ok": False, "root": np.nan, "root_err": np.inf, "slope_snr": 0.0,
           "yfit": np.full(xx.shape, np.nan)}
    if xx.size < 3:
        return out
    order = np.argsort(xx)
    xx, yy, ee = xx[order], yy[order], ee[order]
    k0 = int(np.argmin(np.abs(xx - float(x_prior))))
    if k0 == 0 or k0 == xx.size - 1:
        return out
    im, ip = k0 - 1, k0 + 1
    dx = float(xx[ip] - xx[im])
    if dx <= 0:
        return out
    slope = float((yy[ip] - yy[im]) / dx)
    slope_var = float((ee[ip] ** 2 + ee[im] ** 2) / dx ** 2)
    if wavenumber is not None:
        kh = abs(float(wavenumber)) * dx / 2.0
        if kh > 1e-9 and abs(np.sin(kh)) > 1e-9:
            # The neighbour secant of a sine is smaller than its central derivative by
            # sinc(kh).  Correcting it avoids an 11% root bias for the default kh=pi/4.
            corr = kh / np.sin(kh)
            slope *= corr
            slope_var *= corr ** 2
    if abs(slope) <= 0:
        return out
    root = float(xx[k0] - yy[k0] / slope)
    root_var = float(ee[k0] ** 2 / slope ** 2
                     + yy[k0] ** 2 * slope_var / slope ** 4)
    root_err = float(np.sqrt(max(root_var, 0.0)))
    side_snr = float(np.hypot(yy[im] / ee[im], yy[ip] / ee[ip]))
    slope_snr = abs(slope) / max(np.sqrt(slope_var), 1e-15)
    bracketed = (min(yy[im], yy[ip]) <= 0.0 <= max(yy[im], yy[ip]))
    local = xx[im] <= root <= xx[ip]
    intercept = yy[k0] - slope * xx[k0]
    out.update({"ok": bool(bracketed and local and side_snr >= float(min_side_snr)
                            and np.isfinite(root_err)),
                "root": root, "root_err": root_err, "slope": slope,
                "slope_snr": float(slope_snr), "side_snr": side_snr,
                "yfit": slope * xx + intercept, "x": xx, "y": yy})
    return out


def fit_cosine_peak(x, y, yerr, x_prior, wavenumber, min_amplitude_snr=4.0,
                    fixed_shape=None):
    """Local maximum of a known-period repeated-pulse fringe.

    A parabola across most of a cosine lobe has a deterministic vertex bias comparable
    to the 0.4% calibration target.  Fit the actual local fringe instead, allowing its
    wavenumber to move by 50% for gain nonlinearity and decoherence.  ``fixed_shape``
    may supply the pooled (linear, quadratic) phase coefficients when fitting individual
    acquisition blocks.  That leaves three identifiable block parameters for seven
    points while preserving independent roots for forward/reverse drift tests.  The
    root is bounded to the central scan lobe, and covariance is inflated by reduced
    chi-square.
    """
    xx, yy, ee = (np.asarray(v, dtype=float) for v in (x, y, yerr))
    good = np.isfinite(xx) & np.isfinite(yy) & np.isfinite(ee) & (ee > 0)
    xx, yy, ee = xx[good], yy[good], ee[good]
    out = {"ok": False, "root": np.nan, "root_err": np.inf,
           "amplitude_snr": 0.0, "contrast_snr": 0.0, "red_chi2": np.inf,
           "yfit": np.full(xx.shape, np.nan)}
    k0 = abs(float(wavenumber))
    if xx.size < 7 or k0 <= 0:
        return out
    scan_half = float(np.max(np.abs(xx - float(x_prior))))
    if scan_half <= 0:
        return out

    def model(g, off, amp, root, k, k2):
        dx = g - root
        return off + amp * np.cos(k * dx + k2 * dx ** 2)

    lo_root, hi_root = float(x_prior) - 0.80 * scan_half, float(x_prior) + 0.80 * scan_half
    best = None
    roots0 = (float(x_prior), float(xx[int(np.argmax(yy))]))
    k2_scale = 5.0 * k0 / max(abs(float(x_prior)), 1.0)
    if fixed_shape is None:
        trials = [(root0, k20) for root0 in roots0
                  for k20 in (0.0, -0.2 * k2_scale, 0.2 * k2_scale)]
        for root0, k20 in trials:
            try:
                popt, pcov = curve_fit(
                    model, xx, yy,
                    p0=[float(np.min(yy)), max(float(np.ptp(yy)), 1e-12),
                        float(np.clip(root0, lo_root, hi_root)), k0, k20],
                    sigma=ee, absolute_sigma=True,
                    bounds=([-np.inf, 0.0, lo_root, 0.2 * k0, -k2_scale],
                            [np.inf, np.inf, hi_root, 2.0 * k0, k2_scale]),
                    maxfev=30000)
                resid = yy - model(xx, *popt)
                chi2 = float(np.sum((resid / ee) ** 2))
                if best is None or chi2 < best[0]:
                    best = (chi2, popt, pcov, 5)
            except Exception:
                continue
    else:
        kval, k2 = (float(v) for v in fixed_shape)
        if not (np.isfinite(kval) and np.isfinite(k2) and kval > 0):
            return out

        def block_model(g, off, amp, root):
            return model(g, off, amp, root, kval, k2)

        for root0 in roots0:
            try:
                popt3, pcov3 = curve_fit(
                    block_model, xx, yy,
                    p0=[float(np.min(yy)), max(float(np.ptp(yy)), 1e-12),
                        float(np.clip(root0, lo_root, hi_root))],
                    sigma=ee, absolute_sigma=True,
                    bounds=([-np.inf, 0.0, lo_root], [np.inf, np.inf, hi_root]),
                    maxfev=30000)
                off, amp, root = popt3
                popt = np.array([off, amp, root, kval, k2], dtype=float)
                resid = yy - block_model(xx, *popt3)
                chi2 = float(np.sum((resid / ee) ** 2))
                if best is None or chi2 < best[0]:
                    best = (chi2, popt, pcov3, 3)
            except Exception:
                continue
    if best is None:
        return out
    chi2, (off, amp, root, kval, k2), pcov, npar = best
    dof = max(xx.size - npar, 1)
    red = chi2 / dof
    pcov = np.asarray(pcov, dtype=float) * max(red, 1.0)
    if np.all(np.isfinite(pcov)):
        root_err = float(np.sqrt(max(pcov[2, 2], 0.0)))
        amp_err = float(np.sqrt(max(pcov[1, 1], 0.0)))
    else:
        root_err, amp_err = np.inf, np.inf
    amp_snr = float(amp) / max(amp_err, 1e-15)
    ic = int(np.argmin(np.abs(xx - float(x_prior))))
    edge = 0.5 * (yy[0] + yy[-1])
    edge_err = np.sqrt(ee[ic] ** 2 + 0.25 * (ee[0] ** 2 + ee[-1] ** 2))
    contrast_snr = float(abs(yy[ic] - edge) / max(edge_err, 1e-15))
    interior = bool(xx.min() < root < xx.max() and lo_root < root < hi_root)
    k_interior = bool(fixed_shape is not None or 0.22 * k0 < kval < 1.98 * k0)
    # Relaxation during a long train can broaden the local lobe far beyond the unitary
    # n*pi/g prediction.  The fitted scale is therefore diagnostic, not an acceptance
    # gate.  Branch safety comes from the signed M=1 hierarchy; this held-out fit cannot
    # relocate it and must still pass central-root, direct-contrast, block/order, and
    # repeated two-depth checks.
    out.update({"ok": bool(interior and np.isfinite(root_err)
                            and contrast_snr >= float(min_amplitude_snr) and red <= 25.0),
                "root": float(root), "root_err": root_err,
                "amplitude": float(amp), "amplitude_snr": amp_snr,
                "contrast_snr": contrast_snr,
                "offset": float(off), "wavenumber": float(kval),
                "quadratic_phase": float(k2),
                "red_chi2": float(red), "interior": interior,
                "wavenumber_interior": k_interior,
                "yfit": model(xx, off, amp, root, kval, k2), "x": xx, "y": yy})
    return out


def single_shot_analysis(ig, qg, ie, qe):
    """Single-shot readout analysis: rotation angle, threshold, fidelity, error
    directions, separation in shot-noise units, and an OUTLIER FRACTION.

    The robust-tail fraction is diagnostic and only has a deliberately loose severe-
    pathology ceiling during search.  It is not called a QND or ionization measurement:
    a geometric two-blob heuristic cannot distinguish leakage, e->g transitions, and an
    ordinary anisotropic cloud.

    Fidelity is reported with two-fold CROSS-FITTING: each fold's median IQ axis and
    threshold are trained on one half and scored on the other.  The two held-out scores
    use every shot without fitting either discriminator coordinate on a scored shot."""
    ig, qg = np.asarray(ig, dtype=float), np.asarray(qg, dtype=float)
    ie, qe = np.asarray(ie, dtype=float), np.asarray(qe, dtype=float)
    n = min(ig.size, qg.size, ie.size, qe.size)
    if n < 20:
        return {"ok": False, "fidelity": np.nan, "fidelity_se": np.inf,
                "sep_sigma": 0.0, "theta": 0.0,
                "threshold": np.nan, "p_e_given_g": np.nan, "p_g_given_e": np.nan,
                "outlier_frac": 1.0, "xg": np.zeros(0), "xe": np.zeros(0)}
    ig, qg, ie, qe = ig[:n], qg[:n], ie[:n], qe[:n]
    # Use the robust blob centres that the QM-Team optimizer uses.  Means are a
    # disastrous axis estimator for precisely the high-power points this routine must
    # compare: a few class-correlated ionization/tail shots can rotate the mean-to-mean
    # axis almost orthogonal to the two main blobs.  A measured 4% tail is enough to turn
    # a real J~0.94 point into J~0.60 while still passing the old 8% outlier gate.
    dx = float(np.median(ie) - np.median(ig))
    dy = float(np.median(qe) - np.median(qg))
    th = float(np.arctan2(dy, dx))
    xg = ig * np.cos(th) + qg * np.sin(th)
    xe = ie * np.cos(th) + qe * np.sin(th)
    yg = -ig * np.sin(th) + qg * np.cos(th)
    ye = -ie * np.sin(th) + qe * np.cos(th)
    def _rob(a):
        return float(np.median(np.abs(a - np.median(a)))) * 1.4826

    # Separation is only a diagnostic/tie-breaker, but even a diagnostic must not be
    # destroyed by the same sparse tails the median axis was introduced to tolerate.
    # Keep the classical width for forensic output and report the robust within-blob
    # scale in sep_sigma.  Eligibility is based on held-out fidelity, never this model.
    sd_classical = float(0.5 * (np.std(xg) + np.std(xe)))
    sd = float(max(0.5 * (_rob(xg) + _rob(xe)), 1e-15))
    sep = float(np.hypot(dx, dy))
    sep_sigma = sep / (sd + 1e-15)

    def _thr_fid(a, b):
        # Exact empirical-CDF maximization.  A fixed 512-point linspace over raw
        # min..max catastrophically loses all resolution when a few axial shots sit far
        # away: a 94% discriminator became 4% because no threshold landed near either
        # main blob.  Only boundaries between observed values can change Youden J.
        a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
        values = np.concatenate([a, b])
        is_g = np.concatenate([np.ones(a.size, dtype=int), np.zeros(b.size, dtype=int)])
        order = np.argsort(values, kind="mergesort")
        sv, sg = values[order], is_g[order]
        uniq, first, counts = np.unique(sv, return_index=True, return_counts=True)
        ends = first + counts - 1
        cum_g = np.cumsum(sg)[ends].astype(float)
        cum_e = (np.arange(1, sv.size + 1) - np.cumsum(sg))[ends].astype(float)
        score = np.concatenate([[0.0], cum_g / max(a.size, 1)
                                - cum_e / max(b.size, 1)])
        k = int(np.argmax(score))
        if k == 0:
            return float(np.nextafter(uniq[0], -np.inf))
        if k >= uniq.size:
            return float(np.nextafter(uniq[-1], np.inf))
        return float(uniq[k - 1] + 0.5 * (uniq[k] - uniq[k - 1]))

    # Two-fold cross-fitting keeps both median-axis and threshold selection out of the
    # scored shots.  Alternating samples put slow within-acquisition drift into both
    # folds rather than assigning early shots to train and late shots to test.
    folds = (np.arange(n) % 2 == 0, np.arange(n) % 2 == 1)
    p_egs, p_ges, ns = [], [], []
    for test in folds:
        train = ~test
        if train.sum() < 10 or test.sum() < 10:
            continue
        fold_dx = float(np.median(ie[train]) - np.median(ig[train]))
        fold_dy = float(np.median(qe[train]) - np.median(qg[train]))
        fold_th = float(np.arctan2(fold_dy, fold_dx))
        ct, st = np.cos(fold_th), np.sin(fold_th)
        xg_train, xe_train = ig[train] * ct + qg[train] * st, \
            ie[train] * ct + qe[train] * st
        xg_test, xe_test = ig[test] * ct + qg[test] * st, \
            ie[test] * ct + qe[test] * st
        t = _thr_fid(xg_train, xe_train)
        p_egs.append(float((xg_test >= t).mean()))
        p_ges.append(float((xe_test < t).mean()))
        ns.append(int(test.sum()))
    if not ns:
        return {"ok": False, "fidelity": np.nan, "fidelity_se": np.inf,
                "sep_sigma": 0.0, "theta": th, "threshold": np.nan,
                "p_e_given_g": np.nan, "p_g_given_e": np.nan,
                "outlier_frac": 1.0, "xg": xg, "xe": xe}
    weights = np.asarray(ns, dtype=float) / float(np.sum(ns))
    # This full-data threshold is returned only as the operational/plotting threshold
    # corresponding to the returned full-data angle.  It is not used in ``fid``.
    thr = _thr_fid(xg, xe)
    p_eg = float(np.sum(weights * np.asarray(p_egs)))
    p_ge = float(np.sum(weights * np.asarray(p_ges)))
    fid = 1.0 - p_eg - p_ge
    # Jeffreys posterior variance stays finite when a finite sample happens to contain
    # zero errors.  The old Wald error became exactly zero at F=1 and made a 1500-shot
    # result look infinitely certain during winner selection.
    def _jeffreys_var(p, count):
        errors = float(np.clip(p, 0.0, 1.0)) * float(count)
        a, b = errors + 0.5, float(count) - errors + 0.5
        return float(a * b / ((a + b) ** 2 * (a + b + 1.0)))

    fid_se = float(np.sqrt(_jeffreys_var(p_eg, n) + _jeffreys_var(p_ge, n)))
    cg = np.array([np.median(xg), np.median(yg)])
    ce = np.array([np.median(xe), np.median(ye)])

    # Normalize distance to each blob by that blob's own robust scale.  The previous
    # shared *smaller* width falsely labelled a legitimate broader/elongated excited
    # cloud as ionized and could hard-reject the highest-fidelity point.
    s_g = max(0.5 * (_rob(xg) + _rob(yg)), 1e-12)
    s_e = max(0.5 * (_rob(xe) + _rob(ye)), 1e-12)
    allpts = np.column_stack([np.concatenate([xg, xe]), np.concatenate([yg, ye])])
    d2 = np.minimum(((allpts - cg) ** 2).sum(1) / s_g ** 2,
                    ((allpts - ce) ** 2).sum(1) / s_e ** 2)
    outlier_frac = float((d2 > 16.0).mean())
    return {"ok": True, "fidelity": float(fid), "fidelity_se": fid_se,
            "sep_sigma": float(sep_sigma),
            "theta": th, "threshold": float(thr), "p_e_given_g": p_eg,
            "p_g_given_e": p_ge, "outlier_frac": outlier_frac,
            "xg": xg, "xe": xe, "sep": sep, "sigma": sd,
            "sigma_classical": sd_classical}


def fidelity_lower_bound(fid, fid_se, confidence_sigma=1.96):
    """Finite-sample lower confidence score used consistently by search and gates."""
    fid, fid_se = float(fid), float(fid_se)
    if not np.isfinite(fid) or not np.isfinite(fid_se) or fid_se < 0:
        return -np.inf
    return float(fid - float(confidence_sigma) * fid_se)


def t1_timing_domain_valid(working):
    """Whether readout and reset timing remain inside the measured T1 domain."""
    t1_lo = float(working.get("t1_lo_us", np.nan))
    t1_hi = float(working.get("t1_hi_us", np.nan))
    cap = max(0.5 * t1_lo, 2.0) if np.isfinite(t1_lo) else np.nan
    return bool(
        working.get("t1_verified", False)
        and np.isfinite(cap) and np.isfinite(t1_hi)
        and float(working.get("read_length", np.inf)) <= cap + 1e-9
        and float(working.get("relax_delay", -np.inf)) >= 5.0 * t1_hi - 1e-9)


def simultaneous_confidence_sigma(n_comparisons, alpha=0.05, floor=1.96):
    """Two-sided Bonferroni z-score for a screened candidate family."""
    m = max(int(n_comparisons), 1)
    a = float(np.clip(alpha, 1e-9, 0.5))
    return float(max(float(floor), NormalDist().inv_cdf(1.0 - a / (2.0 * m))))


def select_verified_2d_candidate(rows, incumbent=None, confidence_sigma=1.96,
                                 min_improvement=0.01, max_outlier=0.25):
    """Choose a directly measured 2-D candidate by its held-out lower bound.

    ``rows`` are measurement dictionaries containing ``freq``, ``gain``, ``fid``,
    ``fid_se`` and ``outlier``.  A candidate must have reproduced (``verified=True``)
    and remain below only a deliberately loose severe-pathology ceiling; outlier rate is
    then a diagnostic/tie-breaker, not a way for a model to silently prefer 60% over a
    measured 90%.  The winner maximizes a confidence lower bound, which protects against
    winner's curse when tens of grid points are compared.
    """
    z = float(confidence_sigma)
    usable = []
    for row in rows:
        r = dict(row)
        fid = float(r.get("fid", np.nan))
        se = float(r.get("fid_se", np.inf))
        out = float(r.get("outlier", np.inf))
        if (not bool(r.get("verified", True)) or not np.isfinite(fid)
                or not np.isfinite(se) or se < 0 or not np.isfinite(out)
                or out > float(max_outlier)):
            continue
        r["lcb"] = fid - z * se
        r["ucb"] = fid + z * se
        usable.append(r)
    if not usable:
        return None
    best = max(usable, key=lambda r: (r["lcb"], r["fid"], -r["outlier"]))
    inc = None
    if incumbent is not None:
        if isinstance(incumbent, dict):
            inc = dict(incumbent)
        else:
            inc = next((r for r in usable if r is incumbent), None)
    if inc is not None:
        inc_fid_check = float(inc.get("fid", np.nan))
        inc_se_check = float(inc.get("fid_se", np.inf))
        inc_out_check = float(inc.get("outlier", np.inf))
        if (not bool(inc.get("verified", True))
                or not np.isfinite(inc_fid_check)
                or not np.isfinite(inc_se_check) or inc_se_check < 0
                or not np.isfinite(inc_out_check)
                or inc_out_check > float(max_outlier)):
            inc = None
    if inc is not None:
        inc_fid = float(inc["fid"])
        inc_se = float(inc.get("fid_se", np.inf))
        inc_ucb = inc_fid + z * inc_se
        regret = float(best["fid"] - inc_fid)
        significant = bool(best["lcb"] > inc_ucb + float(min_improvement))
    else:
        regret, significant = np.nan, True
    best["regret"] = regret
    best["improvement_significant"] = significant
    return best


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
                "pi_err": np.inf, "yfit": np.zeros_like(sig)}
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
                popt, pcov = curve_fit(model, gains, sig,
                                       p0=[sig.mean(), np.ptp(sig) / 2.0,
                                           c_seed * mult, 5.0 * span],
                                       bounds=([-np.inf, -np.inf, 1e-9, 0.2 * span],
                                               [np.inf, np.inf, np.inf, 1e6 * span]),
                                       maxfev=20000)
                r = sig - model(gains, *popt)
                sse = float(np.dot(r, r))
                if best is None or sse < best[0]:
                    best = (sse, popt, pcov)
            except Exception:
                continue
    if best is None:
        return {"ok": False, "pi_gain": np.nan, "period": np.nan, "r2": 0.0,
                "pi_err": np.inf, "yfit": np.full_like(sig, sig.mean())}
    _, (B, C, c, gd), pcov = best
    c = abs(float(c))
    pi_gain = np.pi / c if c > 0 else np.nan
    yfit = model(gains, B, C, c, gd)
    ss_res = float(np.sum((sig - yfit) ** 2))
    ss_tot = float(np.sum((sig - sig.mean()) ** 2)) + 1e-15
    r2 = 1.0 - ss_res / ss_tot
    try:
        c_err = float(np.sqrt(max(pcov[2, 2], 0.0)))
        pi_err = float(np.pi * c_err / (c * c))
    except Exception:
        pi_err = np.inf
    ok = bool(np.isfinite(pi_gain) and 0.02 * span <= pi_gain <= gains.max() and r2 > 0.7)
    return {"ok": ok, "pi_gain": float(pi_gain), "period": float(2 * np.pi / c) if c > 0 else np.nan,
            "pi_err": pi_err, "r2": float(r2), "yfit": yfit, "decay_gain": float(gd)}


def fit_exp_decay(t, y, yerr=None):
    """Fit the physically directed T1 model ``y = A exp(-t/tau) + c``.

    T1 population must fall with delay.  A negative-amplitude exponential is a rising
    reference/preparation artifact, not a lifetime.  When point SEMs are available they
    are used as absolute fit weights and to require a directly observed early-to-late
    drop; a good extrapolated curve alone is insufficient.
    """
    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)
    ee = None
    if yerr is not None:
        ee = np.asarray(yerr, dtype=float)
        n = min(t.size, y.size, ee.size)
        t, y, ee = t[:n], y[:n], ee[:n]
        good = np.isfinite(t) & np.isfinite(y) & np.isfinite(ee) & (ee > 0)
        t, y, ee = t[good], y[good], ee[good]
    else:
        good = np.isfinite(t) & np.isfinite(y)
        t, y = t[good], y[good]
    if t.size < 4:
        return {"ok": False, "tau": np.nan, "A": 0.0, "c": 0.0, "yfit": np.zeros_like(y),
                "tau_err": np.inf, "reduced_chi2": np.inf}

    def model(tt, A, tau, c):
        return A * np.exp(-tt / tau) + c

    best = None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", OptimizeWarning)
        for tau0 in (t.max() / 5.0, t.max() / 2.0, t.max(), 3.0 * t.max()):
            try:
                popt, pcov = curve_fit(
                    model, t, y,
                    p0=[max(float(np.ptp(y)), 1e-4), tau0, float(np.min(y))],
                    sigma=ee, absolute_sigma=ee is not None,
                    bounds=([0.0, 1e-4, -2.0], [3.0, 1e5, 2.0]), maxfev=20000)
                r = y - model(t, *popt)
                # With measured SEMs, choose the fit by the likelihood objective rather
                # than unweighted SSE.  The two objectives can rank seeds differently
                # when a few points are intrinsically noisier than the rest.
                objective = (float(np.dot(r / ee, r / ee)) if ee is not None
                             else float(np.dot(r, r)))
                if best is None or objective < best[0]:
                    best = (objective, popt, pcov)
            except Exception:
                continue
    if best is None:
        return {"ok": False, "tau": np.nan, "A": 0.0, "c": 0.0, "yfit": np.zeros_like(y),
                "tau_err": np.inf, "reduced_chi2": np.inf}
    _, (A, tau, c), pcov = best
    yfit = model(t, A, tau, c)
    if ee is not None:
        chi2 = float(np.sum(((y - yfit) / ee) ** 2))
        reduced_chi2 = chi2 / max(int(t.size) - 3, 1)
        # absolute_sigma=True assumes the supplied point errors explain the scatter.
        # Hardware drift and state-preparation systematics violate that assumption.  A
        # Birge-ratio inflation prevents an absurdly small formal T1 uncertainty from
        # certifying a visibly bad curve.  Never shrink an uncertainty when chi2 < 1.
        pcov = np.asarray(pcov, dtype=float) * max(reduced_chi2, 1.0)
    else:
        # curve_fit already scales unweighted covariance from its residual variance.
        reduced_chi2 = 1.0
    tau_err = float(np.sqrt(max(pcov[1, 1], 0.0))) if np.all(np.isfinite(pcov)) else np.inf
    order = np.argsort(t)
    k = max(int(t.size // 4), 1)
    early, late = order[:k], order[-k:]
    observed_drop = float(np.mean(y[early]) - np.mean(y[late]))
    if ee is not None:
        drop_err = float(np.sqrt(np.sum(ee[early] ** 2) / k ** 2
                                 + np.sum(ee[late] ** 2) / k ** 2))
    else:
        drop_err = float(max(np.std(y - yfit), 1e-9) * np.sqrt(2.0 / k))
    residual_noise = max(float(np.std(y - yfit)),
                         float(np.median(ee)) if ee is not None else 0.0, 1e-9)
    ok = bool(A > 4.0 * residual_noise and A > 0.05
              and observed_drop > max(4.0 * drop_err, 0.05))
    return {"ok": ok, "tau": float(tau), "A": float(A), "c": float(c), "yfit": yfit,
            "tau_err": tau_err, "observed_drop": observed_drop,
            "observed_drop_err": drop_err, "reduced_chi2": float(reduced_chi2)}


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
    return set_readout_pulse(prog)


def _add_qubit_gauss(prog, name="qubit"):
    """Gaussian envelope on the QUBIT generator's fabric clock.  Passing gen_ch is not
    optional: without it us2cycles uses the tProc clock and every pi pulse comes out the
    wrong length (and the host-side t_pi = 4*sigma used for coherence bounds is wrong
    too)."""
    cfg = prog.cfg
    qch = cfg["qubit_ch"]
    return add_qubit_gaussian(prog, name=name)


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


def qubit_gain_sweep_supported(soccfg, gen_ch):
    """True only for known full-speed generators with a standalone gain register.

    Interpolated generators such as ``axis_sg_int4_v1`` pack gain into the address
    register; incrementing ``sreg(..., 'gain')`` then compiles but does not change the
    physical amplitude.  A flat rough-Rabi caused by that silent mismatch must never be
    diagnosed as a device failure.
    """
    try:
        gtype = str(soccfg["gens"][int(gen_ch)].get("type", "")).lower()
    except Exception:
        return None
    if not gtype:
        return None
    return bool(gtype.startswith("axis_signal_gen_v"))


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
    d = np.array([Ie - Ig, Qe - Qg], dtype=float)
    a = np.array([Im - Ig, Qm - Qg], dtype=float)
    denom = float(np.dot(d, d))
    sep = float(np.sqrt(max(denom, 0.0)))
    pop = float(iq_to_pop(Im, Qm, (Ig, Qg), (Ie, Qe)))
    if not np.isfinite(denom) or denom <= 0 or not np.isfinite(pop):
        return pop, sep, np.inf
    # First-order propagation through p=((m-g).(e-g))/|e-g|^2.  The old expression
    # included only target-shot noise and treated the immediately adjacent |g>/<e>
    # references as exact.  At low contrast that can understate a T1 point's uncertainty
    # by a large factor and let reference drift masquerade as a precise decay.
    grad_m = d / denom
    grad_e = a / denom - 2.0 * pop * d / denom
    grad_g = -grad_m - grad_e
    sig_m = np.array([sIm, sQm], dtype=float)
    sig_e = np.array([sIe, sQe], dtype=float)
    sig_g = np.array([sIg, sQg], dtype=float)
    variance = float(np.sum((grad_m * sig_m) ** 2)
                     + np.sum((grad_e * sig_e) ** 2)
                     + np.sum((grad_g * sig_g) ** 2))
    sem = float(np.sqrt(max(variance, 0.0))) if np.isfinite(variance) else np.inf
    return pop, sep, sem



DEFAULTS = {
    "max_rounds": 8,
    "resonator": {"span_mhz": 4.0, "points": 81, "max_span_mhz": 60.0, "shots": 400,
                  "relax_delay_us": 50.0, "expected_fwhm_mhz": 0.3,
                  "asym_warn_deg": 10.0},
    "spec": {"span_mhz": 20.0, "points": 121, "max_span_mhz": 150.0, "shots": 500,
             "gain": None, "len_us": None, "relax_delay_us": 500.0,
             "confirm_min_snr": 5.0, "confirm_steps": 3, "confirm_repeat_sigma": 4.0,
             "confirm_min_lever": 0.5, "confirm_min_points": 4,
             "confirm_max_shift_frac": 1.0, "confirm_shift_sigma": 3.0,
             "max_prior_shift_mhz": None, "allow_target_reacquisition": False},
    "rough_pi": {"gain_max": 30000, "points": 61, "shots": 500, "relax_delay_us": None},
    "chi": {"span_mhz": 4.0, "points": 81, "shots": 500, "relax_delay_us": None},
    "readout_power": {"ratios": (0.25, 0.4, 0.6, 0.85, 1.2, 1.7, 2.4, 3.4),
                      "shots": 1500, "coarse_shots": 400,
                      "freq_span_mhz": 2.0, "freq_points": 11,
                      "gain_min": 200, "gain_max": 16000, "gain_points": 9,
                      # Absolute safety ceiling.  None means the *current merged*
                      # gain_max, so a user override of gain_max remains a hard bound.
                      # Set this separately only when edge expansion above the initial
                      # grid is intentionally authorized.
                      "hard_gain_max": None,
                      "minimum_gain_ceiling": 10000, "refine_points": 5,
                      "refine_cells": 3, "shortlist": 6, "confirm_blocks": 4,
                      "decision_blocks": 3, "familywise_alpha": 0.05,
                      "max_block_spread": 0.06,
                      "confidence_sigma": 1.96, "min_improvement": 0.01,
                      "outlier_max": 0.25, "max_extensions": 2,
                      "relax_delay_us": None},
    "t1": {"points": 12, "shots": 600, "t_max_us": None, "relax_delay_us": None,
           "max_frac_err": 0.35, "max_upper_ci_window_ratio": 2.0,
           # Deliberately loose: average unexplained residuals above five reported
           # standard errors indicate drift/model failure, not a trustworthy T1.
           "max_reduced_chi2": 25.0},
    "readout_len": {"lengths_us": (1.0, 2.0, 4.0, 8.0, 14.0, 20.0, 30.0, 45.0),
                    "shots": 1500, "coarse_shots": 400, "shortlist": 3,
                    "confirm_blocks": 3, "decision_blocks": 3,
                    "familywise_alpha": 0.05, "confidence_sigma": 1.96,
                    "min_improvement": 0.005, "max_block_spread": 0.06,
                    "outlier_max": 0.25,
                    "relax_delay_us": None, "max_extensions": 4,
                    "extend_factor": 1.5},
    "single_shot": {"shots": 4000, "min_fidelity_lcb": 0.80,
                    "confidence_sigma": 1.96, "verify_tol_abs": 0.03,
                    "measurement_blocks": 3, "verify_blocks": 4,
                    "max_block_spread": 0.06,
                    "min_sep_sigma": 2.0, "target_sep_sigma": 4.0,
                    "relax_delay_us": None, "verify_tol_frac": 0.15},
    # Independent one-pulse objective map.  This is a branch-safe local challenger to
    # the coherent calibration, not a replacement for it: any adopted challenger must
    # subsequently pass signed frequency/amplitude refinement and held-out audits.
    "pi_fidelity": {"gain_span_frac": 0.30, "gain_points": 9,
                    "freq_span_mhz": 1.2, "freq_points": 9,
                    "coarse_shots": 400, "shots": 1500, "refine_points": 5,
                    "refine_cells": 3, "shortlist": 6, "confirm_blocks": 4,
                    "decision_blocks": 3, "familywise_alpha": 0.05,
                    "max_block_spread": 0.06,
                    "confidence_sigma": 1.96, "min_improvement": 0.015,
                    "outlier_max": 0.25, "relax_delay_us": None},
    # Fine frequency uses driven pseudo-identity pairs Xpi/X-pi.  Amplitude error
    # cancels in a pair while detuning produces a signed Y rotation; an approximate
    # Y90 analysis pulse maps that rotation onto population.  This remains usable on
    # the short-T2* device where Ramsey repeatedly failed.
    "fine_pi_freq": {"pair_list": (1, 3), "span_mhz": (1.6, 0.40),
                     "points": (11, 9), "shots": 600, "min_slope_snr": 3.0,
                     "tol_mhz": 0.06, "agreement_sigma": 3.0,
                     "agreement_floor_mhz": 0.04, "validation_pairs": 2,
                     "validation_span_mhz": 0.24, "relax_delay_us": None},
    # Odd-depth sparse phase estimation is first-order at pi and cancels SPAM offset
    # and contrast.  M_list is kept as the public key for backwards-compatible runner
    # overrides, but all depths are made odd before use and a broad M=1 branch sentinel
    # is prepended automatically.
    "fine_pi_amp": {"M_list": (3, 7, 15), "shots": 800, "blocks": 4,
                    "tol_frac": 0.004, "confidence_sigma": 1.96,
                    "min_phase_snr": 5.0, "min_ref_snr": 5.0,
                    "min_depths": 2, "max_correction_frac": 0.16,
                    "max_initial_correction_frac": 0.50,
                    "max_cumulative_correction_frac": 0.16,
                    "contraction_factor": 0.9, "max_rebound_frac": 0.006,
                    "capture_95_frac": 0.45, "agreement_sigma": 3.0,
                    "agreement_floor_frac": 0.002,
                    "max_axis_rotation_deg": 15.0, "max_ref_change_frac": 0.25,
                    "max_local_ground_step_frac": 0.25,
                    "ground_motion_sigma": 4.0,
                    "max_order_sigma": 4.0, "anchor_floor_frac": 0.02,
                    "validation_M": 16, "validation_peak_M": 13,
                    "validation_peak_M_list": (11, 13),
                    "validation_points": 7,
                    "validation_rounds": 2, "gap_check_factor": 2.0,
                    "validation_max_shot_multiplier": 4,
                    "validation_retry_bound_factor": 2.0,
                    "relax_delay_us": None},
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


def _balanced_block_count(value):
    """Complete forward/reverse x 0/180-degree phase-cycle quartets."""
    n = max(4, int(value))
    return 4 * int(np.ceil(n / 4.0))


GRAPH = [
    ("resonator",     [],                              "_cal_resonator"),
    ("spec",          ["resonator"],                   "_cal_spec"),
    ("rough_pi",      ["spec"],                        "_cal_rough_pi"),
    ("t1",            ["rough_pi", "single_shot"],     "_cal_t1"),
    ("chi",           ["resonator", "rough_pi", "fine_pi_amp"],   "_cal_chi"),
    # Frequency/gain and integration length are coupled.  The backward edge is an
    # intentional fixed-point loop: after length moves, the direct 2-D map is repeated
    # with that exact ADC window rather than assuming its old optimum still applies.
    ("readout_power", ["chi", "rough_pi", "fine_pi_amp", "readout_len"],
                                                               "_cal_readout_power"),
    ("readout_len",   ["readout_power", "t1"],         "_cal_readout_len"),
    ("single_shot",   ["readout_len"],                 "_cal_single_shot"),
    # Frequency and amplitude form an intentional fixed-point pair.  The signed
    # pseudo-identity is first-order insensitive to amplitude, but real pulse distortion
    # and drive-induced shifts are not; a material fine-amplitude move therefore forces
    # frequency to be checked again on the pulse that will actually be committed.
    ("pi_fidelity",   ["single_shot", "rough_pi", "fine_pi_freq", "fine_pi_amp"],
                                                               "_cal_pi_fidelity"),
    ("fine_pi_freq",  ["single_shot", "rough_pi", "pi_fidelity", "fine_pi_amp"],
                                                               "_cal_fine_pi_freq"),
    ("fine_pi_amp",   ["fine_pi_freq", "single_shot"], "_cal_fine_pi_amp"),
]

RECOVERABLE = ("spec", "t1", "chi", "readout_power", "readout_len", "single_shot",
               "fine_pi_freq", "fine_pi_amp")


class AutoTuner(ExperimentClass):
    """Run-once automatic tuner.  acquire() maintains the calibration graph to a fixed
    point and returns {'config': cfg, 'data': self.data}; data['tuned'] holds the values
    measured for diagnostics, while data['eligible_tuned'] is the evidence-gated subset
    the runner may write."""

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data',
                 suffix='Auto_Tune', cfg=None, meta_dict=None, params=None, **kw):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, suffix=suffix, cfg=cfg, meta_dict=meta_dict, **kw)
        self.element = str(path)
        self.P = merge_params(params)
        self.report_lines = []
        self.stale = {name: True for name, _, _ in GRAPH}
        self.node_data = {}
        self.drifted = []

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
        c["adc_trig_offset"] = float(self.cfg.get("adc_trig_offset", 0.5))
        # BaseConfig is the one source of truth used by both tuner and consumers.  A
        # private P_TUNER-only guard would certify a pulse duration that is not replayed
        # after the runner writes the other readout keys.
        c["readout_guard_us"] = float(self.cfg.get("readout_guard_us", 1.0))
        # Preserve a deliberately longer operator-supplied pulse, but never allow it to
        # end before the delayed ADC window.  This is a generator duration, not the ADC
        # integration length optimized by ``readout_len``.
        if "read_pulse_length" in self.cfg:
            c["read_pulse_length"] = float(self.cfg["read_pulse_length"])
        return c

    def _current_pulse_fingerprint(self):
        """Exact saved identity for the waveform that the current working state emits."""
        c = self._cfg_for("pi_fidelity") if hasattr(self, "w") else dict(self.cfg)
        c["pulse_implementation"] = "tls_canonical_gaussian_v1"
        c["switch_triggered"] = False
        # ``length`` is a QM legacy key with different semantics.  Pin the fingerprint
        # to the duration the TLS canonical helper will actually emit so a leftover QM
        # field cannot make the saved identity lie about the hardware waveform.
        c["read_pulse_length"] = readout_drive_length_us(c)
        if hasattr(self, "w"):
            c["qubit_pi_freq"] = float(self.w["drive_freq"])
            c["qubit_pi_gain"] = int(self.w["pi_gain"])
        return pulse_fingerprint(c)

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
        cpx = fit_notch_complex(fs, z, f0_guess=fit["f0"], kappa_guess=fit["fwhm"])
        if cpx["ok"]:
            shift = abs(cpx["f0"] - fit["f0"])
            self.node_data["resonator"]["fit"] = cpx["yfit"]
            self.node_data["resonator"]["asym_deg"] = cpx["asym_deg"]
            self._say("resonator", "OK",
                      "dip at %.4f +/- %.4f MHz, kappa/2pi = %.3f MHz (snr %.0f, complex "
                      "notch fit)" % (cpx["f0"], cpx["f0_err"], cpx["fwhm"], cpx["snr"]))
            if abs(cpx["asym_deg"]) > float(P["asym_warn_deg"]):
                self._say("resonator", "WARN",
                          "the lineshape is ASYMMETRIC by %.0f deg (feedline mismatch), so "
                          "a symmetric Lorentzian is the wrong model here: it puts the dip "
                          "at %.4f and kappa at %.3f, which is %.0f kHz (%.2f kappa) from "
                          "the complex-fit answer. The complex fit is the one being used."
                          % (cpx["asym_deg"], fit["f0"], fit["fwhm"], 1000 * shift,
                             shift / max(cpx["fwhm"], 1e-9)))
            fit_f0, fit_k, fit_err = cpx["f0"], cpx["fwhm"], cpx["f0_err"]
            self.w["res_asym_deg"] = float(cpx["asym_deg"])
        else:
            self._say("resonator", "WARN",
                      "the complex notch fit did not converge -- falling back to the "
                      "symmetric magnitude fit, which BIASES f0 if the dip is asymmetric")
            self._say("resonator", "OK",
                      "%s at %.4f +/- %.4f MHz, kappa/2pi = %.3f MHz (snr %.0f)"
                      % (fit["polarity"], fit["f0"], fit["f0_err"], fit["fwhm"], fit["snr"]))
            fit_f0, fit_k, fit_err = fit["f0"], fit["fwhm"], fit["f0_err"]
        self.w["resonator_f0"] = float(fit_f0)
        self.w["kappa_mhz"] = float(fit_k)
        self.w["read_pulse_freq"] = round(float(fit_f0), 4)
        self.w["updated"].add("read_pulse_freq")
        return {"f0": fit_f0}, {"f0": max(0.2 * fit_k, 3 * fit_err)}

    def _cal_spec(self):
        P = self.P["spec"]
        target_prior = float(self.w["qubit_freq"])
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
            base = np.median(z.real) + 1j * np.median(z.imag)
            return fs, np.abs(z - base)

        span, npts, gain = float(P["span_mhz"]), int(P["points"]), gain0
        best = None
        while True:
            fs, sig = scan(self.w["qubit_freq"], span, npts, gain, P["shots"])
            fit = fit_resonance(fs, sig, polarity="peak", expected_fwhm=max(2.0, span / 40))
            if _better_fit(fit, best[0] if best else None):
                best = (fit, fs, sig, span, gain)
            if fit["ok"]:
                break
            failed_span, failed_gain = span, gain
            if span < float(P["max_span_mhz"]):
                span, npts = min(span * 4.0, float(P["max_span_mhz"])), min(npts * 3, 601)
            elif gain < 30000:
                gain = min(gain * 3, 30000)
            else:
                break
            self._say("spec", "WARN", "nothing in +/-%.0f MHz of %.3f at gain %d (snr %.1f)"
                                      " -- retrying at +/-%.0f MHz, gain %d"
                      % (failed_span / 2, self.w["qubit_freq"], failed_gain, fit["snr"],
                         span / 2, gain))
        fit, fs, sig, span_used, gain_used = best
        if not fit["ok"]:
            raise TunerError("spec: no qubit line within +/-%.0f MHz of %.3f (best snr "
                             "%.1f)." % (span_used / 2, self.w["qubit_freq"], fit["snr"]))
        self._say("spec", "OK", "candidate line at %.4f MHz (span %.0f MHz, gain %d, "
                                "snr %.1f, fwhm %.3f) -- confirming against power"
                  % (fit["f0"], span_used, gain_used, fit["snr"], fit["fwhm"]))
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
        narrow = max(6.0 * fit["fwhm"], 1.5)
        npts_n = max(41, npts // 3)
        fs2, sig2 = scan(fit["f0"], narrow, npts_n, gain_used, P["shots"])
        rep = fit_resonance(fs2, sig2, polarity="peak", expected_fwhm=fit["fwhm"])
        zrep = peak_significance(fs2, sig2, fit["f0"], fit["fwhm"])
        if zrep < float(P["confirm_repeat_sigma"]):
            raise TunerError(
                "spec: the candidate at %.4f MHz did not reproduce on a REPEAT scan at the "
                "same drive power (only %.1f sigma of signal at that frequency, %.1f "
                "required) -- it was a noise excursion, not a line."
                % (fit["f0"], zrep, P["confirm_repeat_sigma"]))
        if rep["ok"] and abs(rep["f0"] - fit["f0"]) <= max(fit["fwhm"], 1.0):
            centre0, snr_full = float(rep["f0"]), max(float(rep["snr"]), 1e-6)
        else:
            centre0, snr_full = float(fit["f0"]), max(zrep, 1e-6)
            self._say("spec", "OK", "the repeat scan confirms %.1f sigma at %.4f MHz but "
                                    "will not support a narrow refit -- keeping the "
                                    "wide-scan centre" % (zrep, fit["f0"]))
        self.node_data["spec"] = {"freqs": fs2, "sig": sig2, "fit": rep["yfit"]}
        centres, powers = [centre0], [float(gain_used) ** 2]
        r_floor = float(np.sqrt(float(P["confirm_min_snr"]) / snr_full))
        if r_floor >= 0.85:
            self._say("spec", "WARN",
                      "the line is only snr %.1f at full drive, and the signal falls as "
                      "gain^2, so ANY reduced power would put it under the noise -- the "
                      "AC-Stark extrapolation is skipped rather than failed. The Rabi in "
                      "the next step is the real confirmation: a spurious feature cannot "
                      "produce a coherent oscillation that returns to zero at 2 pi."
                      % snr_full)
        else:
            for ratio in np.geomspace(0.75, max(r_floor, 0.2), int(P["confirm_steps"])):
                g = max(int(gain_used * ratio), 40)
                fs3, sig3 = scan(fit["f0"], narrow, npts_n, g, P["shots"])
                f3 = fit_resonance(fs3, sig3, polarity="peak", expected_fwhm=fit["fwhm"])
                if not f3["ok"] or abs(f3["f0"] - fit["f0"]) > max(2.0 * fit["fwhm"], 2.0):
                    self._say("spec", "OK", "power step gain %d: line no longer resolvable "
                                            "-- stopping the ladder here" % g)
                    break
                centres.append(f3["f0"])
                powers.append(float(g) ** 2)
        f_q, lever = float(centres[0]), min(powers) / max(powers)
        n_need = int(P["confirm_min_points"])
        if len(centres) >= n_need and lever <= float(P["confirm_min_lever"]):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                c, cov = np.polyfit(np.array(powers), np.array(centres), 1, cov=True)
            f_ex = float(c[-1])
            f_ex_err = float(np.sqrt(abs(cov[-1, -1])))
            shift = abs(f_ex - centres[0])
            cap = float(P["confirm_max_shift_frac"]) * fit["fwhm"]
            nsig = float(P["confirm_shift_sigma"])
            why = None
            if not np.isfinite(f_ex_err) or f_ex_err > 0.5 * fit["fwhm"]:
                why = ("the intercept is only determined to +/-%.3f MHz, half a linewidth"
                       % f_ex_err)
            elif shift < nsig * f_ex_err:
                why = ("the %.3f MHz correction is under %.0f sigma of its own %.3f MHz "
                       "uncertainty, so it is scatter and not a measured shift"
                       % (shift, nsig, f_ex_err))
            elif shift > cap:
                why = ("it would move the line %.3f MHz, more than the %.3f MHz runaway "
                       "guard (%.1f linewidths)"
                       % (shift, cap, float(P["confirm_max_shift_frac"])))
            if why is None:
                f_q = f_ex
                self._say("spec", "OK", "qubit line %.4f MHz +/- %.4f (zero-power "
                                        "extrapolation over %d powers; highest-power "
                                        "centre %.4f)"
                          % (f_q, f_ex_err, len(centres), centres[0]))
            else:
                self._say("spec", "WARN",
                          "the zero-power extrapolation is REJECTED (%s) -- over this short "
                          "a power lever arm that is amplified fit noise, not a Stark "
                          "shift, so the full-drive centre %.4f is kept. A wrong centre "
                          "here detunes the Rabi and wrecks everything downstream."
                          % (why, centres[0]))
        elif len(centres) >= 2:
            self._say("spec", "OK",
                      "qubit line %.4f MHz (reproduced at %d powers, but %s -- not enough "
                      "to extrapolate to zero power, so this is the full-drive centre)"
                      % (f_q, len(centres),
                         "the weakest was still %.0f%% of the strongest" % (100 * lever)
                         if lever > float(P["confirm_min_lever"])
                         else "%d points is under the %d needed for a trustworthy intercept"
                              % (len(centres), n_need)))
        else:
            self._say("spec", "OK",
                      "qubit line %.4f MHz (reproduced at full drive; only one power was "
                      "usable, so this is the AC-Stark-SHIFTED centre and not extrapolated "
                      "to zero power -- fine_pi_freq re-measures it with a pi train anyway)"
                      % f_q)
        target_radius = P.get("max_prior_shift_mhz")
        if target_radius is None:
            target_radius = 0.5 * float(P["span_mhz"])
        target_shift = abs(float(f_q) - target_prior)
        self.node_data["spec"]["target_prior"] = target_prior
        self.node_data["spec"]["target_shift_mhz"] = target_shift
        if (target_shift > float(target_radius)
                and not bool(P.get("allow_target_reacquisition", False))):
            raise TunerError(
                "spec: reproducible transition %.4f MHz is %.3f MHz from the trusted "
                "target %.4f, outside the %.3f MHz identity radius. A coherent Rabi "
                "would prove this is A transition, not that it is the intended one; "
                "refusing to jump targets. Update the target prior deliberately or set "
                "params['spec']['allow_target_reacquisition']=True after identifying it."
                % (f_q, target_shift, target_prior, target_radius))
        if target_shift > float(target_radius):
            self._say("spec", "WARN",
                      "TARGET REACQUISITION was explicitly enabled: %.4f -> %.4f MHz "
                      "(%.3f MHz). Verify this is the intended transition, not a nearby "
                      "TLS/qubit, before applying the result."
                      % (target_prior, f_q, target_shift))
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

        def swept(gain_max):
            """Opposed hardware sweeps cancel first-order time drift pointwise."""
            step = max(int(round(int(gain_max) / (npts - 1))), 1)
            traces = []
            for start, inc in ((0, step), (step * (npts - 1), -step)):
                c = dict(cfg)
                c["start"], c["step"], c["expts"] = int(start), int(inc), npts
                with suppress_stdout():
                    prog = RabiProgram(self.soccfg, c)
                    xret, avgi, avgq = prog.acquire(
                        self.soc, load_pulses=True, progress=False)
                x = np.asarray(xret, dtype=float).reshape(-1)
                I = np.asarray(avgi[0][0], dtype=float).reshape(-1)
                Q = np.asarray(avgq[0][0], dtype=float).reshape(-1)
                if x.size != I.size:
                    x = start + inc * np.arange(I.size, dtype=float)
                order = np.argsort(x)
                traces.append((x[order], I[order] + 1j * Q[order]))
            gf, zf = traces[0]
            gr, zr = traces[1]
            if gf.size != gr.size or not np.allclose(gf, gr, atol=0.51):
                raise TunerError("rough_pi: forward/reverse QICK gain grids disagree.")
            z = 0.5 * (zf + zr)
            dr = 0.5 * np.abs(zf - zr)
            di, dq = z.real - z.real.mean(), z.imag - z.imag.mean()
            cov = np.array([[di @ di, di @ dq], [di @ dq, dq @ dq]])
            wv, vv = np.linalg.eigh(cov)
            u = vv[:, int(np.argmax(wv))]
            sig = di * u[0] + dq * u[1]
            if sig[nan_argmax(np.abs(sig))] < 0:
                u, sig = -u, -sig
            sf = ((zf.real - zf.real.mean()) * u[0]
                  + (zf.imag - zf.imag.mean()) * u[1])
            sr = ((zr.real - zr.real.mean()) * u[0]
                  + (zr.imag - zr.imag.mean()) * u[1])
            return gf, sig, dr, fit_rabi(gf, sig), fit_rabi(gf, sf), fit_rabi(gf, sr)

        gains, sig, drift, fit, fit_fwd, fit_rev = swept(int(P["gain_max"]))
        if fit["ok"] and np.isfinite(fit["period"]) and fit["period"] < 0.25 * gains.max():
            new_max = int(np.clip(2.5 * fit["period"], 200, 32000))
            self._say("rough_pi", "OK", "period %.0f DAC is small next to the %d sweep -- "
                      "re-sweeping 0-%d so it is properly sampled"
                      % (fit["period"], int(gains.max()), new_max))
            gains, sig, drift, fit, fit_fwd, fit_rev = swept(new_max)
        self.node_data["rough_pi"] = {"gains": gains, "sig": sig, "fit": fit["yfit"],
                                      "forward_reverse_halfdiff": drift}
        if not fit["ok"]:
            raise TunerError("rough_pi: no clean Rabi (r2 %.2f). Check drive freq/power "
                             "or readout." % fit["r2"])
        pi0 = int(round(min(fit["pi_gain"], 32000)))
        pi0 = self._harmonic_check(pi0, cfg, int(P["shots"]))
        pass_spread = 0.0
        if fit_fwd["ok"] and fit_rev["ok"]:
            pass_spread = 0.5 * abs(fit_fwd["pi_gain"] - fit_rev["pi_gain"])
        anchor_floor = float(self.P["fine_pi_amp"]["anchor_floor_frac"]) * pi0
        anchor_err = max(float(fit.get("pi_err", np.inf)) if np.isfinite(fit.get("pi_err", np.inf))
                         else 0.0, pass_spread, anchor_floor, 2.0)
        self.w["pi_gain"] = pi0
        self.w["pi_gain_anchor_err"] = float(anchor_err)
        self.w["updated"].add("qubit_pi_gain")
        self._say("rough_pi", "OK", "pi gain %d +/- %.0f DAC (opposed sweeps, period "
                  "%.0f, r2 %.2f)" % (pi0, anchor_err, fit["period"], fit["r2"]))
        return {"g": pi0}, {"g": max(3.0 * anchor_err, 0.01 * pi0)}

    def _harmonic_check(self, pi0, cfg, shots):
        """Confirm the Rabi fit picked the right harmonic, WITH a significance test.
        Repeating each point and requiring the winner to beat 1x by >3 sigma stops a
        noisy readout from silently halving the pi gain."""
        mults = [0.0, 0.5, 1.0, 1.5, 2.0]
        vals = {m: [] for m in mults}
        # Every multiplier is measured at the same mean acquisition time.
        for m in mults + mults[::-1]:
            g = int(round(min(pi0 * m, 32000)))
            seq = [("pulse", g, 0.0)] if g > 0 else []
            I, Q, sI, sQ = _run_seq(self, cfg, seq, self.w["drive_freq"], shots)
            vals[m].append((I, Q, np.hypot(sI, sQ)))
        means, errs = [], []
        for m in mults:
            means.append((float(np.mean([v[0] for v in vals[m]])),
                          float(np.mean([v[1] for v in vals[m]]))))
            errs.append(float(np.sqrt(np.sum([v[2] ** 2 for v in vals[m]]))) / len(vals[m]))
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
            d_opt = optimal_readout_detuning(chi, kappa)
            cands = [f_mid - d_opt, f_mid + d_opt]
            f_analytic = min(cands, key=lambda x: abs(x - f_dmax))
            self.w["chi_mhz"], self.w["kappa_mhz"] = float(chi), float(kappa)
            def _dsep(c, k):
                d = np.linspace(-3 * max(abs(c), k), 3 * max(abs(c), k), 2001)
                ag, ae = 1.0 / ((d - c) + 0.5j * k), 1.0 / ((d + c) + 0.5j * k)
                return float(np.max(np.abs(ag - ae)) / np.max(np.abs(ag)))
            d_now = _dsep(chi, kappa)
            d_opt = _dsep(0.5 * kappa, kappa)
            self.w["chi_kappa_penalty"] = float(d_opt / max(d_now, 1e-9))
            self._say("chi", "OK",
                      "linear-cavity separation-per-photon diagnostic %.2f vs %.2f at "
                      "2|chi|=kappa (model ratio %.1fx). This is a SEED only: Kerr shift, "
                      "compression and state-dependent noise make the real optimum "
                      "power-dependent, so the joint held-out grid decides the readout"
                      % (d_now, d_opt, d_opt / max(d_now, 1e-9)))
            self._say("chi", "OK", "chi/2pi = %+.4f MHz, kappa/2pi = %.4f MHz, 2|chi|/kappa "
                                   "= %.2f -> %s" % (chi, kappa, abs(2 * chi) / max(kappa, 1e-9),
                      "drive the midpoint" if abs(2 * chi) <= kappa else "drive a dressed peak"))
            if abs(f_dmax - f_analytic) < max(kappa, 0.2):
                f_use = f_dmax
                note = "measured D-max (agrees with the analytic optimum to %.3f MHz)" % abs(f_dmax - f_analytic)
            else:
                f_use = f_analytic
                note = ("analytic linear-cavity seed; measured averaged-IQ D-max at %.4f "
                        "differs by %.3f MHz (the direct 2-D fidelity grid will arbitrate)"
                        % (f_dmax, abs(f_dmax - f_analytic)))
        else:
            f_use, note = f_dmax, "measured D-max (chi fit failed, no analytic cross-check)"
        self.w["read_pulse_freq"] = round(float(f_use), 4)
        self.w["updated"].add("read_pulse_freq")
        self._say("chi", "OK", "readout frequency -> %.4f MHz [%s]" % (f_use, note))
        return {"f": f_use}, {"f": max(0.1 * self.w.get("kappa_mhz", 0.3), 0.01)}

    def _balanced_single_shot(self, cfg, drive_freq, pi_gain, shots, strict=True):
        """Acquire drift-balanced ground/excited microblocks and analyze them.

        Strict measurements pool a randomly selected balanced schedule and its exact
        complement.  Consequently every label samples every acquisition slot once: an
        8-call-synchronous baseline artifact cancels deterministically, not merely in
        expectation.  The coarse maps use the same strict primitive: a safe final gate
        is not enough if drift can keep the real 90% basin out of the shortlist entirely.
        """
        seqs = {"g": [], "e": [("pulse", int(pi_gain), 0.0)]}
        got = {"g": [[], []], "e": [[], []]}
        # Every schedule has four labels per state and equal mean acquisition time, so
        # affine drift cancels.  Randomly choosing among all eight such schedules avoids
        # locking the excited label to a repeatable 8-call periodic instrument artifact;
        # independent confirmation blocks choose again.
        e_schedules = ((0, 1, 6, 7), (0, 2, 5, 7), (0, 3, 4, 7),
                       (0, 3, 5, 6), (1, 2, 4, 7), (1, 2, 5, 6),
                       (1, 3, 4, 6), (2, 3, 4, 5))
        e_slots = set(e_schedules[int(np.random.randint(len(e_schedules)))])
        first = ["e" if j in e_slots else "g" for j in range(8)]
        labels = first + (["g" if label == "e" else "e" for label in first]
                          if strict else [])
        per_state_blocks = 8 if strict else 4
        each = max(10, int(np.ceil(float(shots) / float(per_state_blocks))))
        for label in labels:
            i, q = _shots(self, cfg, seqs[label], float(drive_freq), each)
            got[label][0].append(np.asarray(i, dtype=float))
            got[label][1].append(np.asarray(q, dtype=float))
        ig, qg = np.concatenate(got["g"][0]), np.concatenate(got["g"][1])
        ie, qe = np.concatenate(got["e"][0]), np.concatenate(got["e"][1])
        return single_shot_analysis(ig, qg, ie, qe)

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
                ss = self._balanced_single_shot(
                    cfg, self.w["drive_freq"], self.w["pi_gain"], int(shots),
                    strict=True)
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

    def _single_shot_point(self, node, read_freq, read_gain, drive_freq, pi_gain, shots,
                           strict=True):
        """One directly measured setting with drift-balanced g/e microblocks.

        Merely randomizing one full ground batch and one full excited batch aliases IQ
        drift into apparent state contrast.  Eight balanced microblocks give both labels
        the same mean acquisition time (cancelling affine drift), while a randomly chosen
        balanced schedule prevents acquisition-periodic artifacts from staying attached
        to one label across independent blocks.  Total shots per state remain
        approximately ``shots``.
        """
        cfg = self._cfg_for(node)
        cfg["read_pulse_freq"] = float(read_freq)
        cfg["read_pulse_gain"] = int(read_gain)
        ss = self._balanced_single_shot(cfg, drive_freq, pi_gain, shots, strict=strict)
        return {"freq": float(read_freq), "gain": int(read_gain),
                "fid": float(ss["fidelity"]),
                "fid_se": float(ss.get("fidelity_se", np.inf)),
                "sep": float(ss["sep_sigma"]), "outlier": float(ss["outlier_frac"]),
                "verified": bool(ss.get("ok", True)), "ss": ss}

    def _single_shot_length_point(self, length_us, shots):
        """Direct fidelity point for one ADC integration/generator duration pair."""
        cfg = self._cfg_for("readout_len")
        cfg["read_length"] = float(length_us)
        cfg["read_pulse_length"] = readout_drive_length_us(cfg)
        ss = self._balanced_single_shot(
            cfg, self.w["drive_freq"], self.w["pi_gain"], shots)
        # Generic coordinates let the shared confirmation machinery operate unchanged.
        return {"freq": float(length_us), "gain": 0,
                "fid": float(ss["fidelity"]),
                "fid_se": float(ss.get("fidelity_se", np.inf)),
                "sep": float(ss["sep_sigma"]), "outlier": float(ss["outlier_frac"]),
                "verified": bool(ss.get("ok", True)), "ss": ss}

    @staticmethod
    def _aggregate_ss_blocks(rows, max_disagreement=0.10):
        """Combine independent confirmations without hiding block-to-block drift."""
        good = [r for r in rows if np.isfinite(r.get("fid", np.nan))
                and np.isfinite(r.get("fid_se", np.nan))]
        if not good:
            return None
        f = np.asarray([r["fid"] for r in good], dtype=float)
        se = np.asarray([r["fid_se"] for r in good], dtype=float)
        within = float(np.mean(se ** 2) / len(good))
        between = float(np.var(f, ddof=1) / len(good)) if len(good) > 1 else 0.0
        total_se = float(np.sqrt(max(within + between, 0.0)))
        spread = float(np.ptp(f)) if f.size > 1 else 0.0
        out = {"freq": float(good[0]["freq"]), "gain": int(good[0]["gain"]),
               "fid": float(np.mean(f)), "fid_se": total_se,
               "sep": float(np.mean([r["sep"] for r in good])),
               "outlier": float(np.max([r["outlier"] for r in good])),
               "block_spread": spread, "blocks": good,
               "verified": bool(len(good) == len(rows)
                                and spread <= float(max_disagreement))}
        return out

    def _confirm_candidate_blocks(self, candidates, measure, nblocks,
                                  max_disagreement=0.06):
        """Randomized independent blocks for a candidate list.

        ``measure(f, g)`` must return the generic frequency/gain row schema.  Keeping
        this orchestration shared makes the readout and pi maps use identical drift and
        reproducibility rules.
        """
        candidates = list(candidates)
        blocks = {key: [] for key in candidates}
        for _ in range(max(int(nblocks), 2)):
            for idx in np.random.permutation(len(candidates)):
                f, g = candidates[int(idx)]
                blocks[(f, g)].append(measure(float(f), int(g)))
        confirmed = []
        for vals in blocks.values():
            agg = self._aggregate_ss_blocks(vals, max_disagreement=max_disagreement)
            if agg is not None:
                confirmed.append(agg)
        return confirmed

    @staticmethod
    def _ss_from_aggregate(agg):
        """Convert a confirmed generic row back to the single-shot result schema."""
        if agg is None or not agg.get("blocks"):
            return None
        parts = [r.get("ss") for r in agg["blocks"] if isinstance(r.get("ss"), dict)]
        if not parts:
            return None
        ss = dict(parts[-1])
        ss.update({"ok": bool(agg.get("verified", False)),
                   "fidelity": float(agg["fid"]),
                   "fidelity_se": float(agg["fid_se"]),
                   "sep_sigma": float(agg["sep"]),
                   "outlier_frac": float(agg["outlier"])})
        for key in ("p_e_given_g", "p_g_given_e"):
            vals = [float(p[key]) for p in parts if np.isfinite(p.get(key, np.nan))]
            if vals:
                ss[key] = float(np.mean(vals))
        for key in ("xg", "xe"):
            arrays = [np.asarray(p[key]) for p in parts if key in p]
            if arrays:
                ss[key] = np.concatenate(arrays)
        return ss

    @staticmethod
    def _refinement_seeds(rows, count, confidence_sigma=1.96):
        """Top spatially distinct coarse cells, avoiding one-basin over-refinement."""
        ranked = sorted(rows, key=lambda r: fidelity_lower_bound(
            r.get("fid", np.nan), r.get("fid_se", np.inf), confidence_sigma),
                        reverse=True)
        seeds = []
        for row in ranked:
            if not np.isfinite(row.get("fid", np.nan)):
                continue
            # Suppress the 3x3 neighborhood around an already selected cell from the
            # same extension; a separate basin still gets its own local refinement.
            near = any(row.get("extension") == old.get("extension")
                       and abs(int(row.get("freq_index", 0))
                               - int(old.get("freq_index", 0))) <= 1
                       and abs(int(row.get("gain_index", 0))
                               - int(old.get("gain_index", 0))) <= 1
                       for old in seeds)
            if not near:
                seeds.append(row)
            if len(seeds) >= max(int(count), 1):
                break
        return seeds

    def _cal_readout_power(self):
        """Direct joint readout-frequency x gain optimization on held-out fidelity.

        The legacy path chose a frequency from an averaged-IQ/linear-cavity model and
        then varied gain only at that frozen frequency.  Frequency and power are coupled
        by Kerr shift, compression and state-dependent noise; that coordinate search can
        report 60% while a nearby directly measured point is 90%.  This routine maps the
        actual two-dimensional objective with the exact production pulse program,
        refines the best cell, and independently re-measures a shortlist plus the
        incumbent in randomized blocks before changing either setting.
        """
        P = self.P["readout_power"]
        f_inc = float(self.w["read_pulse_freq"])
        g_inc = int(self.w["read_pulse_gain"])
        span = max(float(P["freq_span_mhz"]),
                   6.0 * float(self.w.get("kappa_mhz", 0.0)))
        centre = f_inc
        g_lo = max(30, int(P["gain_min"]))
        configured_hard = P.get("hard_gain_max")
        hard_gain_max = int(P["gain_max"] if configured_hard is None
                            else configured_hard)
        hard_gain_max = min(hard_gain_max, 32000)
        if hard_gain_max < 30:
            raise TunerError("readout_power: hard_gain_max=%d is below the usable DAC "
                             "range" % hard_gain_max)
        if g_inc > hard_gain_max:
            raise TunerError("readout_power: incumbent gain %d exceeds the authorized "
                             "hard_gain_max=%d; lower the incumbent first or explicitly "
                             "raise the safety ceiling" % (g_inc, hard_gain_max))
        if g_lo > hard_gain_max:
            raise TunerError("readout_power: gain_min=%d exceeds hard_gain_max=%d"
                             % (g_lo, hard_gain_max))
        if int(P["minimum_gain_ceiling"]) > hard_gain_max:
            raise TunerError("readout_power: minimum_gain_ceiling=%d exceeds the "
                             "authorized hard_gain_max=%d"
                             % (int(P["minimum_gain_ceiling"]), hard_gain_max))
        g_hi = min(hard_gain_max, max(int(P["minimum_gain_ceiling"]),
                                      int(P["gain_max"]),
                                      int(round(g_inc * max(P.get("ratios", (1.0,)))))))
        coarse_rows, scans = [], []
        coarse_shots = int(P["coarse_shots"])
        nf, ng = int(P["freq_points"]), int(P["gain_points"])

        for extension in range(int(P.get("max_extensions", 2)) + 1):
            freqs = np.linspace(centre - span / 2.0, centre + span / 2.0, nf)
            gains = np.unique(np.round(np.linspace(g_lo, g_hi, ng)).astype(int))
            grid_df = float(abs(freqs[1] - freqs[0])) if len(freqs) > 1 else span
            grid_dg = float(abs(gains[1] - gains[0])) if len(gains) > 1 else max(g_hi-g_lo, 20)
            settings = [(float(f), int(g), fi, gi) for gi, g in enumerate(gains)
                        for fi, f in enumerate(freqs)]
            order = np.random.permutation(len(settings))
            this_rows = []
            for idx in order:
                f, g, fi, gi = settings[int(idx)]
                r = self._single_shot_point("readout_power", f, g,
                                            self.w["drive_freq"], self.w["pi_gain"],
                                            coarse_shots, strict=True)
                r.update({"freq_index": fi, "gain_index": gi,
                          "extension": extension, "freq_step": grid_df,
                          "gain_step": grid_dg})
                this_rows.append(r)
            coarse_rows.extend(this_rows)
            raw = max(this_rows, key=lambda r: r["fid"])
            scans.append({"freqs": freqs, "gains": gains, "best": dict(raw)})
            f_edge = raw["freq_index"] in (0, len(freqs) - 1)
            g_edge = raw["gain_index"] in (0, len(gains) - 1)
            can_lower_gain = raw["gain_index"] == 0 and g_lo > 30
            can_raise_gain = (raw["gain_index"] == len(gains) - 1
                              and g_hi < hard_gain_max)
            if (not (f_edge or can_lower_gain or can_raise_gain)
                    or extension >= int(P.get("max_extensions", 2))):
                if (g_edge and not (can_lower_gain or can_raise_gain)
                        and raw["gain_index"] == len(gains) - 1):
                    self._say("readout_power", "WARN",
                              "the coarse winner is on the authorized hard gain ceiling "
                              "(%d DAC); no pulse above that ceiling will be requested"
                              % hard_gain_max)
                break
            if f_edge:
                centre, span = float(raw["freq"]), 1.5 * span
            if can_lower_gain:
                g_lo = max(30, int(g_lo / 2))
            if can_raise_gain:
                g_hi = min(hard_gain_max, int(round(1.5 * g_hi)))
            self._say("readout_power", "WARN",
                      "coarse 2-D winner is on a grid edge at %.4f MHz / %d DAC; "
                      "expanding the directly measured search" % (raw["freq"], raw["gain"]))

        nr = max(int(P.get("refine_points", 5)), 3)
        seeds = self._refinement_seeds(
            coarse_rows, P.get("refine_cells", 3), P.get("confidence_sigma", 1.96))
        refine_settings, refine_seen = [], set()
        for seed in seeds:
            sdf, sdg = float(seed["freq_step"]), float(seed["gain_step"])
            rf = np.linspace(seed["freq"] - sdf, seed["freq"] + sdf, nr)
            rg = np.unique(np.clip(np.round(np.linspace(seed["gain"] - sdg,
                                                        seed["gain"] + sdg, nr)),
                                   30, hard_gain_max).astype(int))
            for g in rg:
                for f in rf:
                    key = (round(float(f), 9), int(g))
                    if key not in refine_seen:
                        refine_settings.append((float(f), int(g)))
                        refine_seen.add(key)
        refine_rows = []
        for idx in np.random.permutation(len(refine_settings)):
            f, g = refine_settings[int(idx)]
            refine_rows.append(self._single_shot_point(
                "readout_power", f, g, self.w["drive_freq"], self.w["pi_gain"],
                coarse_shots, strict=True))

        df = min((float(s["freq_step"]) for s in seeds), default=max(span / nf, 0.01))
        dg = min((float(s["gain_step"]) for s in seeds), default=max((g_hi-g_lo)/ng, 20.0))
        z = float(P["confidence_sigma"])
        ranked = sorted(coarse_rows + refine_rows,
                        key=lambda r: r["fid"] - z * r["fid_se"], reverse=True)
        candidates, seen = [], set()
        for r in ranked:
            key = (round(float(r["freq"]), 9), int(r["gain"]))
            if key not in seen:
                candidates.append((float(r["freq"]), int(r["gain"])))
                seen.add(key)
            if len(candidates) >= int(P["shortlist"]):
                break
        inc_key = (round(f_inc, 9), g_inc)
        if inc_key not in seen:
            candidates.append((f_inc, g_inc))

        measure = lambda f, g: self._single_shot_point(
            "readout_power", f, g, self.w["drive_freq"], self.w["pi_gain"],
            int(P["shots"]))
        screen_confirmed = self._confirm_candidate_blocks(
            candidates, measure, P.get("confirm_blocks", 4),
            P.get("max_block_spread", 0.06))
        incumbent = next((r for r in screen_confirmed
                          if abs(r["freq"] - f_inc) < 1e-8 and r["gain"] == g_inc), None)
        screen_z = simultaneous_confidence_sigma(
            max(len(screen_confirmed) - 1, 1), P.get("familywise_alpha", 0.05), z)
        screen_best = select_verified_2d_candidate(
            screen_confirmed, incumbent=incumbent, confidence_sigma=screen_z,
            min_improvement=float(P["min_improvement"]),
            max_outlier=float(P["outlier_max"]))
        if screen_best is None:
            raise TunerError("readout_power: no joint frequency/gain candidate reproduced "
                             "in independent confirmation blocks")

        # The screen is independent of the coarse map but still selects among several
        # candidates.  If it nominates a challenger, make the actual write decision on
        # a second, fresh challenger-vs-incumbent data set.
        decision_candidates = [(float(screen_best["freq"]), int(screen_best["gain"]))]
        if incumbent is not None:
            inc_coord = (f_inc, g_inc)
            if inc_coord not in decision_candidates:
                decision_candidates.append(inc_coord)
        decision_confirmed = self._confirm_candidate_blocks(
            decision_candidates, measure, P.get("decision_blocks", 3),
            P.get("max_block_spread", 0.06))
        decision_incumbent = next((r for r in decision_confirmed
                                   if abs(r["freq"] - f_inc) < 1e-8
                                   and r["gain"] == g_inc), None)
        best = select_verified_2d_candidate(
            decision_confirmed, incumbent=decision_incumbent, confidence_sigma=z,
            min_improvement=float(P["min_improvement"]),
            max_outlier=float(P["outlier_max"]))
        if best is None:
            raise TunerError("readout_power: fresh winner/incumbent decision did not "
                             "reproduce")
        chosen = (best if decision_incumbent is None
                  or best["improvement_significant"] else decision_incumbent)
        moved = (abs(float(chosen["freq"]) - f_inc) > 1e-9
                 or int(chosen["gain"]) != g_inc)
        self.node_data["readout_power"] = {
            "coarse": coarse_rows, "refine": refine_rows,
            "screen_confirmed": screen_confirmed,
            "confirmed": decision_confirmed,
            "scans": scans, "selected": dict(chosen), "challenger": dict(best),
            "screen_confidence_sigma": screen_z,
            "hard_gain_max": hard_gain_max,
        }
        self._say("readout_power", "OK",
                  "joint 2-D incumbent %.4f MHz/%d DAC F=%s; verified winner %.4f/%d "
                  "F=%.3f +/- %.3f (%.2f sigma, outliers %.1f%%)%s"
                  % (f_inc, g_inc,
                     "unavailable" if decision_incumbent is None else "%.3f +/- %.3f" %
                     (decision_incumbent["fid"], decision_incumbent["fid_se"]),
                     best["freq"], best["gain"], best["fid"], best["fid_se"],
                     best["sep"], 100 * best["outlier"],
                     " -- significant improvement, adopting both coordinates"
                     if chosen is best else " -- not significantly better, keeping incumbent"))
        self.w["read_pulse_freq"] = round(float(chosen["freq"]), 4)
        self.w["read_pulse_gain"] = int(chosen["gain"])
        self.w["updated"].add("read_pulse_freq")
        self.w["updated"].add("read_pulse_gain")
        if best["outlier"] > 0.08:
            self._say("readout_power", "WARN",
                      "the winning point has %.1f%% robust tail shots. It is retained "
                      "because this heuristic is not a QND/ionization test; the fresh "
                      "fidelity verification, not an isotropic blob model, decides the "
                      "winner" % (100 * best["outlier"]))
        return {"f": float(chosen["freq"]), "g": float(chosen["gain"])}, \
            ({"f": 0.0, "g": 0.0} if moved else
             {"f": max(abs(df) / max(nr - 1, 1), 0.002),
              "g": max(abs(dg) / max(nr - 1, 1), 5.0)})

    def _cal_t1(self):
        """T1 -- required, not optional: it bounds the useful readout length, sets
        relax_delay, caps the pi-train length, and is the dominant contribution to the
        |e>-prep readout error that would otherwise be misread as pi infidelity."""
        P = self.P["t1"]
        cfg = self._cfg_for("t1")
        if int(getattr(self, "_t1_relax_retry_depth", 0)) > 0:
            # A node-specific override that caused the unsafe first pass must not defeat
            # the retry selected from that pass.
            cfg["relax_delay"] = float(self.w["relax_delay"])
        acquisition_relax = float(cfg["relax_delay"])
        shots = int(P["shots"])
        tmax = P["t_max_us"]
        if tmax is None:
            tmax = 60.0
            for probe in (10.0, 30.0, 90.0, 250.0):
                pop, sep, _ = _pop_with_local_refs(
                    self, cfg, [("pulse", int(self.w["pi_gain"]), 0.0), ("delay", probe)],
                    self.w["drive_freq"], self.w["pi_gain"], max(shots // 3, 150))
                if np.isfinite(pop) and pop < 0.4:
                    tmax = float(min(3.0 * probe, 400.0))
                    break
                tmax = float(min(3.0 * probe, 400.0))
        ts = np.linspace(0.05, float(tmax), int(P["points"]))
        order = np.random.permutation(ts.size)
        pops = np.full(ts.size, np.nan)
        errs = np.full(ts.size, np.nan)
        for idx in order:
            t = float(ts[idx])
            pop, sep, sem = _pop_with_local_refs(
                self, cfg, [("pulse", int(self.w["pi_gain"]), 0.0), ("delay", t)],
                self.w["drive_freq"], self.w["pi_gain"], shots)
            pops[idx], errs[idx] = pop, sem
        fit = fit_exp_decay(ts, pops, errs)
        window = float(np.ptp(ts))
        self.node_data["t1"] = {"t": ts, "pop": pops, "fit": fit["yfit"],
                                "window_us": window}
        if not fit["ok"] or not np.isfinite(fit["tau"]):
            # A guessed lifetime is not calibration evidence.  The old 30-us fallback
            # could make the graph look converged while silently choosing unsafe
            # readout-length and pi-train bounds.  Keep any earlier measured value only
            # for diagnostics; the graph's recovery path marks the state mixed-vintage
            # and the write gate requires this bit to be true.
            self.w["t1_verified"] = False
            raise TunerError(
                "t1: exponential fit did not produce a finite lifetime; refusing to "
                "substitute a guessed T1 because it controls the readout-length, "
                "relax-delay, and pi-train safety bounds")
        tau = float(fit["tau"])
        tau_err = float(fit["tau_err"]) if np.isfinite(fit.get("tau_err", np.nan)) else np.inf
        reduced_chi2 = float(fit.get("reduced_chi2", 1.0))
        frac_err = tau_err / max(tau, 1e-9)
        upper_ci = tau + 2.0 * tau_err
        max_upper = float(P.get("max_upper_ci_window_ratio", 2.0)) * window
        self.node_data["t1"].update({"tau_us": tau, "tau_err_us": tau_err,
                                     "upper_95_us": upper_ci,
                                     "maximum_identifiable_upper_us": max_upper,
                                     "reduced_chi2": reduced_chi2})
        # A smooth near-linear drift can fit an exponential with an impressive residual
        # and an amplitude far larger than the *observed* decay, while placing T1 orders
        # of magnitude outside the acquisition window.  That is extrapolation, not a
        # lifetime measurement.  Likewise an infinite/large confidence interval cannot
        # safely set readout or reset bounds.
        identifiable = bool(
            np.isfinite(tau_err)
            and frac_err <= float(P["max_frac_err"])
            and np.isfinite(upper_ci)
            and upper_ci <= max_upper
            and np.isfinite(reduced_chi2)
            and reduced_chi2 <= float(P.get("max_reduced_chi2", 25.0)))
        if not identifiable:
            self.w["t1_verified"] = False
            raise TunerError(
                "t1: lifetime is not identifiable in the measured window "
                "(fit %.1f +/- %.1f us, fractional error %.0f%%, 95%% upper %.1f us; "
                "reduced chi-square %.1f; requirements are <=%.0f%% error, upper "
                "<=%.1f us, and reduced chi-square <=%.1f). Refusing to "
                "extrapolate a safety bound; increase t_max_us/shots or improve the "
                "prepared-state contrast"
                % (tau, tau_err, 100.0 * frac_err,
                   upper_ci, reduced_chi2, 100.0 * float(P["max_frac_err"]),
                   max_upper, float(P.get("max_reduced_chi2", 25.0))))
        if np.isfinite(tau_err):
            t1_lo = max(tau - 2.0 * tau_err, 0.25 * tau, 2.0)
            t1_hi = min(tau + 2.0 * tau_err, 4.0 * tau)
        else:
            t1_lo, t1_hi = max(0.25 * tau, 2.0), 4.0 * tau
        self.w["t1_us"] = tau
        self.w["t1_lo_us"], self.w["t1_hi_us"] = float(t1_lo), float(t1_hi)
        readout_cap = max(0.5 * float(t1_lo), 2.0)
        self.w["t1_readout_cap_us"] = readout_cap
        old_relax = float(self.w["relax_delay"])
        # Relaxation safety is two-sided: shorten a needlessly long delay for runtime,
        # but also LENGTHEN an insufficient one.  The previous one-sided clip could
        # certify a long T1 while continuing to prepare thermally correlated shots.
        required_relax = float(max(5.0 * t1_hi, 20.0))
        if acquisition_relax + 1e-9 < required_relax:
            # This fit was acquired before we knew the configured reset was too short.
            # It is useful only to choose a safe retry delay, not as evidence.  Repeat
            # the entire T1 measurement with 10% headroom; cap retries so a drifting or
            # pathological device fails closed instead of recursing forever.
            depth = int(getattr(self, "_t1_relax_retry_depth", 0))
            if depth >= 2:
                self.w["t1_verified"] = False
                raise TunerError(
                    "t1: the required relax_delay kept increasing across two fresh "
                    "measurements; refusing mixed/reset-correlated lifetime evidence")
            retry_relax = float(max(1.10 * required_relax, required_relax + 1.0))
            self.w["relax_delay"] = retry_relax
            self.w["updated"].add("relax_delay")
            self.w["t1_verified"] = False
            # rough_pi was also acquired before the reset requirement was known.  Make
            # it graph work again; the recursive T1 below supplies immediate safe
            # lifetime evidence, and the next graph round replays the Rabi at the same
            # reset condition before anything can be committed.
            self.stale["rough_pi"] = True
            self._say("t1", "WARN",
                      "configured relax_delay %.0f us is below the measured requirement "
                      "%.0f us; retrying the ENTIRE T1 acquisition at %.0f us before "
                      "treating the lifetime as verified"
                      % (acquisition_relax, required_relax, retry_relax))
            self._t1_relax_retry_depth = depth + 1
            try:
                return self._cal_t1()
            finally:
                self._t1_relax_retry_depth = depth

        new_relax = required_relax
        self.w["relax_delay"] = new_relax
        if abs(new_relax - float(self.cfg.get("relax_delay", old_relax))) > 1e-9:
            self.w["updated"].add("relax_delay")
        self.w["t1_verified"] = True
        if abs(new_relax - old_relax) > max(0.05 * old_relax, 1.0):
            direction = "less idle time" if new_relax < old_relax else "longer safe reset"
            self._say("t1", "OK", "relax_delay %.0f -> %.0f us (5 x the UPPER T1 bound "
                                  "%.1f us; %s downstream)"
                      % (old_relax, new_relax, t1_hi, direction))
        if float(self.w.get("read_length", 0.0)) > readout_cap + 1e-9:
            self.stale["readout_len"] = True
            self._say("t1", "WARN",
                      "the current %.1f-us readout exceeds the new T1-safe cap %.1f us; "
                      "readout_len is stale and must be re-optimized"
                      % (self.w["read_length"], readout_cap))
        self._say("t1", "OK", "T1 = %.1f +/- %.1f us" % (tau, fit["tau_err"]))
        # The cap is a dependency-domain boundary, not a noisy optimization coordinate.
        # Even when tau itself moves within uncertainty, a material cap change must
        # rerun readout_len.  Its explicit final invariant is the last line of defense.
        return {"t1": tau, "cap": readout_cap}, \
            {"t1": max(3.0 * tau_err, 0.01 * tau),
             "cap": max(0.02 * readout_cap, 0.10)}

    def _cal_readout_len(self):
        """Integration length: SNR grows as sqrt(T) but the |e> state decays as T/T1, so
        there is a genuine optimum.  Candidates are capped at T1/2 -- beyond that the
        measurement is mostly watching the qubit decay."""
        P = self.P["readout_len"]
        old_length = float(self.w["read_length"])
        t1 = float(self.w.get("t1_lo_us", self.w.get("t1_us", 30.0)))
        cap = max(0.5 * t1, 2.0)
        cands = [L for L in P["lengths_us"] if L <= cap]
        if not cands:
            cands = [min(P["lengths_us"])]
        def _apply(cfg, L):
            cfg["read_length"] = float(L)

        rows = []

        def _measure(lengths):
            sep, fid, out, _spread = self._sweep_readout("readout_len", lengths, _apply,
                                                         P.get("coarse_shots", P["shots"]))
            for j, L in enumerate(lengths):
                rows.append({"len": float(L), "sep": float(sep[j]), "fid": float(fid[j]),
                             "outlier": float(out[j])})
                self._say("readout_len", "OK", "%5.1f us -> %.2f sigma, F=%.3f"
                          % (L, sep[j], fid[j]))

        _measure(cands)
        for _ in range(int(P.get("max_extensions", 4))):
            ok = [r for r in rows if np.isfinite(r["fid"])]
            if not ok:
                break
            best = max(ok, key=lambda r: r["fid"])
            top = max(r["len"] for r in ok)
            if best["len"] < top - 1e-9 or top >= cap - 1e-9:
                break
            nxt = round(min(top * float(P.get("extend_factor", 1.5)), cap), 1)
            if nxt <= top + 0.5:
                break
            self._say("readout_len", "OK",
                      "F is still rising at the top of the ladder (%.1f us) and T1/2 = "
                      "%.1f us allows more -- extending to %.1f us rather than stopping "
                      "at the range limit" % (top, cap, nxt))
            _measure([nxt])
        ok_rows = [r for r in rows if np.isfinite(r["fid"])]
        if not ok_rows:
            raise TunerError("readout_len: no usable length.")
        coarse_best = max(ok_rows, key=lambda r: r["fid"])
        ranked = sorted(ok_rows, key=lambda r: r["fid"], reverse=True)
        candidates = [(float(r["len"]), 0)
                      for r in ranked[:max(int(P.get("shortlist", 3)), 1)]]
        if old_length <= cap + 1e-9 and (old_length, 0) not in candidates:
            candidates.append((old_length, 0))

        measure = lambda length, _zero: self._single_shot_length_point(
            length, int(P["shots"]))
        screen_confirmed = self._confirm_candidate_blocks(
            candidates, measure, P.get("confirm_blocks", 3),
            P.get("max_block_spread", 0.06))
        incumbent = next((r for r in screen_confirmed
                          if abs(r["freq"] - old_length) < 1e-9), None)
        z = float(P.get("confidence_sigma", 1.96))
        screen_z = simultaneous_confidence_sigma(
            max(len(screen_confirmed) - 1, 1), P.get("familywise_alpha", 0.05), z)
        screen_best = select_verified_2d_candidate(
            screen_confirmed, incumbent=incumbent, confidence_sigma=screen_z,
            min_improvement=float(P.get("min_improvement", 0.005)),
            max_outlier=float(P.get("outlier_max", 0.25)))
        if screen_best is None:
            raise TunerError("readout_len: no integration length reproduced in "
                             "independent confirmation blocks")
        decision_candidates = [(float(screen_best["freq"]), 0)]
        if incumbent is not None and (old_length, 0) not in decision_candidates:
            decision_candidates.append((old_length, 0))
        decision_confirmed = self._confirm_candidate_blocks(
            decision_candidates, measure, P.get("decision_blocks", 3),
            P.get("max_block_spread", 0.06))
        decision_incumbent = next((r for r in decision_confirmed
                                   if abs(r["freq"] - old_length) < 1e-9), None)
        decision_best = select_verified_2d_candidate(
            decision_confirmed, incumbent=decision_incumbent, confidence_sigma=z,
            min_improvement=float(P.get("min_improvement", 0.005)),
            max_outlier=float(P.get("outlier_max", 0.25)))
        if decision_best is None:
            raise TunerError("readout_len: fresh winner/incumbent decision failed")
        selected = (decision_best if decision_incumbent is None
                    or decision_best["improvement_significant"] else decision_incumbent)
        best = {"len": float(selected["freq"]), "fid": float(selected["fid"]),
                "sep": float(selected["sep"]), "outlier": float(selected["outlier"]),
                "fid_se": float(selected["fid_se"])}
        self.node_data["readout_len"] = {
            "coarse": rows, "screen_confirmed": screen_confirmed,
            "confirmed": decision_confirmed, "selected": dict(best),
            "screen_confidence_sigma": screen_z,
        }
        lo = min(r["len"] for r in ok_rows)
        hi = max(r["len"] for r in ok_rows)
        if len(ok_rows) > 1 and best["len"] >= hi - 1e-9 and hi >= cap - 1e-9:
            self._say("readout_len", "WARN",
                      "the best length %.1f us is the T1/2 cap (%.1f us) -- the LIMIT is "
                      "the qubit lifetime, not the ladder; a longer readout would keep "
                      "helping if T1 were longer" % (best["len"], cap))
        elif len(ok_rows) > 1 and best["len"] <= lo + 1e-9:
            self._say("readout_len", "WARN",
                      "the best length %.1f us is the SHORTEST tested (%.1f-%.1f us) -- "
                      "shorten params['readout_len']['lengths_us'] to find the real optimum"
                      % (best["len"], lo, hi))
        self.w["read_length"] = float(best["len"])
        self.w["updated"].add("read_length")
        self._say("readout_len", "OK", "confirmed length %.1f us (F=%.3f +/- %.3f, "
                                       "%.2f robust sigma; coarse winner %.1f us; "
                                       "capped at T1/2 = %.1f us)"
                  % (best["len"], best["fid"], best["fid_se"], best["sep"],
                     coarse_best["len"], 0.5 * t1))
        # Frequency/gain were measured with the old ADC window.  Any selected duration
        # change therefore invalidates that 2-D map; this is a pulse-timing identity,
        # not a 40%-heuristic movement test.
        return {"L": best["len"]}, \
            {"L": 0.0 if abs(float(best["len"]) - old_length) > 1e-12 else 0.05}

    def _cal_single_shot(self):
        P = self.P["single_shot"]
        cfg = self._cfg_for("single_shot")
        shots = int(P["shots"])
        coord = (float(self.w["read_pulse_freq"]), int(self.w["read_pulse_gain"]))
        confirmed = self._confirm_candidate_blocks(
            [coord],
            lambda f, g: self._single_shot_point(
                "single_shot", f, g, self.w["drive_freq"], self.w["pi_gain"], shots),
            P.get("measurement_blocks", 3), P.get("max_block_spread", 0.06))
        ss = self._ss_from_aggregate(confirmed[0] if confirmed else None)
        if ss is None or not ss.get("ok", False):
            raise TunerError("single_shot: the final readout setting did not reproduce "
                             "across drift-balanced blocks")
        self.node_data["single_shot"] = ss
        self.w["ss_fidelity"] = float(ss["fidelity"])
        self.w["ss_fidelity_se"] = float(ss.get("fidelity_se", np.inf))
        self.w["ss_fidelity_lcb"] = fidelity_lower_bound(
            ss["fidelity"], ss.get("fidelity_se", np.inf),
            P.get("confidence_sigma", 1.96))
        self.w["ss_sep_sigma"] = float(ss["sep_sigma"])
        self._say("single_shot", "OK", "F=%.3f +/- %.3f (LCB %.3f) | "
                                       "P(e|g)=%.3f P(g|e)=%.3f | %.2f robust sigma | "
                                       "outliers %.3f | angle %.1f deg"
                  % (ss["fidelity"], ss.get("fidelity_se", np.inf),
                     self.w["ss_fidelity_lcb"], ss["p_e_given_g"], ss["p_g_given_e"],
                     ss["sep_sigma"],
                     ss["outlier_frac"], np.rad2deg(ss["theta"])))
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
        theta_deg = float(np.rad2deg(ss["theta"]))
        if abs(((theta_deg + 180.0) % 360.0) - 180.0) > 2.0:
            cur = float(self.w.get("res_phase", 0.0))
            applied = False
            for sgn in (-1.0, +1.0):
                trial = float((cur + sgn * theta_deg) % 360.0)
                c2 = dict(cfg)
                c2["res_phase"] = trial
                n2 = max(shots // 3, 400)
                t2 = self._balanced_single_shot(
                    c2, self.w["drive_freq"], self.w["pi_gain"], n2)
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
            f_ideal = 1.0 - 2.0 * q_ideal
            at_limit = (f_ideal - ss["fidelity"]) < 0.03
            self._say("single_shot", "WARN",
                      "the robust two-Gaussian diagnostic is %.2f sigma < %.1f. "
                      "Measured held-out F=%.3f vs the idealized Gaussian value %.3f; "
                      "this diagnostic does NOT gate eligibility -> %s"
                      % (ss["sep_sigma"], P["min_sep_sigma"], ss["fidelity"], f_ideal,
                         "ALREADY AT THE LIMIT, so no discriminator or weighting change "
                         "can help -- only more SIGNAL (amplifier chain, chi/kappa, power)"
                         if at_limit else
                         "BELOW the limit, so there is headroom in the discrimination "
                         "itself (rotation angle, threshold, integration weights)"))
        return {"F": ss["fidelity"]}, {"F": 0.02}

    def _cal_pi_fidelity(self):
        """Independent local drive-frequency x gain challenge to the coherent pi.

        A clean Rabi fringe or repeated-pulse root can be internally self-consistent yet
        sit on a detuned, low-inversion solution.  The manual QM workflow exposed exactly
        that class of miss by directly plotting one-pulse visibility.  We therefore map
        the same physical objective around the branch-safe rough-Rabi anchor.  A
        statistically superior point is only a *provisional seed*: signed fine-frequency,
        signed odd-depth amplitude, and held-out audits must all rerun before it can be
        committed, which prevents a raw visibility map from confusing pi and 3pi.
        """
        P = self.P["pi_fidelity"]
        f0, g0 = float(self.w["drive_freq"]), int(self.w["pi_gain"])
        z = float(P["confidence_sigma"])
        all_rows, scans = [], []

        for extension in range(2):
            factor = 1.0 if extension == 0 else 1.5
            frac = min(float(P["gain_span_frac"]) * factor, 0.45)
            fspan = float(P["freq_span_mhz"]) * factor
            freqs = np.linspace(f0 - fspan / 2.0, f0 + fspan / 2.0,
                                int(P["freq_points"]))
            gains = np.unique(np.clip(np.round(np.linspace(
                g0 * (1.0 - frac), g0 * (1.0 + frac), int(P["gain_points"]))),
                30, 32000).astype(int))
            grid_df = float(abs(freqs[1] - freqs[0])) if len(freqs) > 1 else fspan
            grid_dg = float(abs(gains[1] - gains[0])) if len(gains) > 1 else max(frac*g0, 20)
            settings = [(float(f), int(g), fi, gi) for gi, g in enumerate(gains)
                        for fi, f in enumerate(freqs)]
            rows = []
            for idx in np.random.permutation(len(settings)):
                f, g, fi, gi = settings[int(idx)]
                r = self._single_shot_point("pi_fidelity", self.w["read_pulse_freq"],
                                            self.w["read_pulse_gain"], f, g,
                                            int(P["coarse_shots"]), strict=True)
                # ``select_verified_2d_candidate`` uses generic freq/gain names; here
                # they deliberately denote the *drive* coordinates.
                r.update({"read_freq": r["freq"], "read_gain": r["gain"],
                          "freq": f, "gain": g, "freq_index": fi,
                          "gain_index": gi, "extension": extension,
                          "freq_step": grid_df, "gain_step": grid_dg})
                rows.append(r)
            all_rows.extend(rows)
            raw = max(rows, key=lambda r: r["fid"])
            scans.append({"freqs": freqs, "gains": gains, "best": dict(raw)})
            edge = (raw["freq_index"] in (0, len(freqs) - 1)
                    or raw["gain_index"] in (0, len(gains) - 1))
            if not edge:
                break
            if extension == 0:
                self._say("pi_fidelity", "WARN",
                          "one-pulse 2-D winner lies on the local grid edge; expanding "
                          "once while remaining inside the rough-Rabi pi branch")

        nr = max(int(P["refine_points"]), 3)
        seeds = self._refinement_seeds(
            all_rows, P.get("refine_cells", 3), P.get("confidence_sigma", 1.96))
        refine_rows = []
        settings, refine_seen = [], set()
        for seed in seeds:
            sdf, sdg = float(seed["freq_step"]), float(seed["gain_step"])
            rf = np.linspace(seed["freq"] - sdf, seed["freq"] + sdf, nr)
            rg = np.unique(np.clip(np.round(np.linspace(seed["gain"] - sdg,
                                                        seed["gain"] + sdg, nr)),
                                   max(30, int(round(0.55 * g0))),
                                   min(32000, int(round(1.45 * g0)))).astype(int))
            for g in rg:
                for f in rf:
                    key = (round(float(f), 9), int(g))
                    if key not in refine_seen:
                        settings.append((float(f), int(g)))
                        refine_seen.add(key)
        for idx in np.random.permutation(len(settings)):
            f, g = settings[int(idx)]
            r = self._single_shot_point("pi_fidelity", self.w["read_pulse_freq"],
                                        self.w["read_pulse_gain"], f, g,
                                        int(P["coarse_shots"]), strict=True)
            r.update({"read_freq": r["freq"], "read_gain": r["gain"],
                      "freq": f, "gain": g})
            refine_rows.append(r)

        df = min((float(s["freq_step"]) for s in seeds), default=0.02)
        dg = min((float(s["gain_step"]) for s in seeds), default=20.0)

        ranked = sorted(all_rows + refine_rows,
                        key=lambda r: r["fid"] - z * r["fid_se"], reverse=True)
        candidates, seen = [], set()
        for r in ranked:
            key = (round(float(r["freq"]), 9), int(r["gain"]))
            if key not in seen:
                candidates.append((float(r["freq"]), int(r["gain"])))
                seen.add(key)
            if len(candidates) >= int(P["shortlist"]):
                break
        if (round(f0, 9), g0) not in seen:
            candidates.append((f0, g0))

        def measure(f, g):
            r = self._single_shot_point(
                "pi_fidelity", self.w["read_pulse_freq"],
                self.w["read_pulse_gain"], f, g, int(P["shots"]))
            r.update({"read_freq": r["freq"], "read_gain": r["gain"],
                      "freq": f, "gain": g})
            return r

        screen_confirmed = self._confirm_candidate_blocks(
            candidates, measure, P.get("confirm_blocks", 4),
            P.get("max_block_spread", 0.06))
        incumbent = next((r for r in screen_confirmed
                          if abs(r["freq"] - f0) < 1e-8 and r["gain"] == g0), None)
        screen_z = simultaneous_confidence_sigma(
            max(len(screen_confirmed) - 1, 1), P.get("familywise_alpha", 0.05), z)
        screen_best = select_verified_2d_candidate(
            screen_confirmed, incumbent=incumbent, confidence_sigma=screen_z,
            min_improvement=float(P["min_improvement"]),
            max_outlier=float(P["outlier_max"]))
        if screen_best is None or incumbent is None:
            raise TunerError("pi_fidelity: the local 2-D winner/incumbent did not "
                             "reproduce in independent blocks")

        decision_candidates = [(float(screen_best["freq"]), int(screen_best["gain"]))]
        if (f0, g0) not in decision_candidates:
            decision_candidates.append((f0, g0))
        decision_confirmed = self._confirm_candidate_blocks(
            decision_candidates, measure, P.get("decision_blocks", 3),
            P.get("max_block_spread", 0.06))
        decision_incumbent = next((r for r in decision_confirmed
                                   if abs(r["freq"] - f0) < 1e-8
                                   and r["gain"] == g0), None)
        best = select_verified_2d_candidate(
            decision_confirmed, incumbent=decision_incumbent,
            confidence_sigma=z, min_improvement=float(P["min_improvement"]),
            max_outlier=float(P["outlier_max"]))
        if best is None or decision_incumbent is None:
            raise TunerError("pi_fidelity: fresh challenger/incumbent decision did not "
                             "reproduce")
        improve = bool(best["improvement_significant"])
        self.node_data["pi_fidelity"] = {
            "coarse": all_rows, "refine": refine_rows,
            "screen_confirmed": screen_confirmed,
            "confirmed": decision_confirmed, "scans": scans,
            "incumbent": dict(decision_incumbent), "challenger": dict(best),
            "screen_confidence_sigma": screen_z,
        }
        self._say("pi_fidelity", "WARN" if improve else "OK",
                  "one-pulse incumbent %.4f MHz/%d DAC F=%.3f +/- %.3f; best verified "
                  "challenger %.4f/%d F=%.3f +/- %.3f%s"
                  % (f0, g0, decision_incumbent["fid"], decision_incumbent["fid_se"],
                     best["freq"], best["gain"], best["fid"], best["fid_se"],
                     " -- adopting as a PROVISIONAL seed; coherent stages must rerun"
                     if improve else " -- no significant missed optimum"))
        if improve:
            self.w["drive_freq"] = round(float(best["freq"]), 4)
            self.w["pi_gain"] = int(best["gain"])
            self.w["pi_gain_anchor_err"] = max(abs(dg) / 2.0, 0.02 * best["gain"], 20.0)
            self.w["pi_converged"] = False
            self.w["fine_freq_converged"] = False
            self.w["pi_verified"] = False
            self.w["freq_verified"] = False
            self.w["pi_fidelity_verified"] = False
            self.w.pop("pi_fidelity_binding", None)
            self.w["updated"].update(("qubit_pi_freq", "qubit_pi_gain"))
            chosen = best
        else:
            self.w["pi_fidelity_verified"] = True
            self.w["pi_fidelity_binding"] = {
                "drive_freq": f0, "pi_gain": g0,
                "read_pulse_freq": float(self.w["read_pulse_freq"]),
                "read_pulse_gain": int(self.w["read_pulse_gain"]),
                "read_length": float(self.w["read_length"]),
                "pulse_fingerprint": self._current_pulse_fingerprint(),
                "freq_radius": max(abs(df) / max(nr - 1, 1), 0.02),
                "gain_radius": max(abs(dg) / max(nr - 1, 1), 20.0),
            }
            chosen = decision_incumbent
        return {"f": float(chosen["freq"]), "g": float(chosen["gain"])}, \
            ({"f": 0.0, "g": 0.0} if improve else
             {"f": max(abs(df) / max(nr - 1, 1), 0.02),
              "g": max(abs(dg) / max(nr - 1, 1), 20.0)})

    @staticmethod
    def _principal_iq_axis(z, center=True):
        z = np.asarray(z, dtype=complex).reshape(-1)
        x = np.column_stack([z.real, z.imag])
        if center:
            x = x - np.mean(x, axis=0)
        cov = x.T @ x
        val, vec = np.linalg.eigh(cov)
        return vec[:, int(np.argmax(val))]

    def _frequency_pair_point(self, cfg, freq, pairs, shots):
        """Signed detuning syndrome from [Xpi, X-pi]^K followed by +/-Y90.

        Xpi/X-pi exactly cancels a common amplitude error on resonance.  Detuning
        instead produces a Y rotation which the two opposite analysis pulses map to
        opposite populations.  The +,-,-,+ order cancels affine IQ drift.
        """
        pi = int(self.w["pi_gain"])
        pi2 = max(1, int(round(pi / 2.0)))
        core = []
        for _ in range(int(pairs)):
            core.extend([("pulse", pi, 0.0), ("pulse", pi, 180.0)])
        seq = {1: core + [("pulse", pi2, 90.0)],
               -1: core + [("pulse", pi2, -90.0)]}
        each = max(20, int(np.ceil(float(shots) / 2.0)))
        obs = {1: [], -1: []}
        for sign in (1, -1, -1, 1):
            I, Q, sI, sQ = _run_seq(self, cfg, seq[sign], freq, each)
            obs[sign].append((complex(I, Q), float(sI), float(sQ)))

        def mean(sign):
            a = obs[sign]
            z = sum(v[0] for v in a) / len(a)
            si = np.sqrt(sum(v[1] ** 2 for v in a)) / len(a)
            sq = np.sqrt(sum(v[2] ** 2 for v in a)) / len(a)
            return z, float(si), float(sq)

        zp, sip, sqp = mean(1)
        zm, sim, sqm = mean(-1)
        return zp - zm, float(np.hypot(sip, sim)), float(np.hypot(sqp, sqm))

    def _frequency_scan(self, cfg, center, span, points, pairs, shots):
        fs = float(center) + np.linspace(-float(span) / 2.0, float(span) / 2.0,
                                         int(points))
        z = np.empty(fs.size, dtype=complex)
        sei, seq = np.empty(fs.size), np.empty(fs.size)
        mid = (fs.size - 1) / 2.0
        # Centre-out sampling sees both sides of the zero before slow device drift can
        # turn a frequency ordering into a false slope.
        order = sorted(range(fs.size), key=lambda j: (abs(j - mid), j > mid))
        for j in order:
            z[j], sei[j], seq[j] = self._frequency_pair_point(
                cfg, float(fs[j]), int(pairs), int(shots))
        u = self._principal_iq_axis(z, center=False)
        sig = z.real * u[0] + z.imag * u[1]
        err = np.sqrt((sei * u[0]) ** 2 + (seq * u[1]) ** 2)
        err = np.maximum(err, np.nanmedian(err[np.isfinite(err)]) * 0.1 + 1e-15)
        fit = fit_zero_crossing(fs, sig, err, center,
                                min_slope_snr=self.P["fine_pi_freq"]["min_slope_snr"])
        response_snr = float(np.nanmax(np.abs(sig) / np.maximum(err, 1e-15)))
        fit["ok"] = bool(fit["ok"] and response_snr >= 4.0
                         and abs(fit["root"] - center) < 0.48 * float(span))
        return {"freqs": fs, "signal": sig, "err": err, "fit": fit,
                "response_snr": response_snr, "pairs": int(pairs)}

    def _cal_fine_pi_freq(self):
        """Driven, signed frequency calibration independent of amplitude error."""
        P = self.P["fine_pi_freq"]
        cfg = self._cfg_for("fine_pi_freq")
        pairs = tuple(int(v) for v in P.get("pair_list", (1, 3)))
        spans = P["span_mhz"] if isinstance(P["span_mhz"], (tuple, list)) else (P["span_mhz"],)
        points = P["points"] if isinstance(P["points"], (tuple, list)) else (P["points"],)
        roots, center = [], float(self.w["drive_freq"])
        self.node_data["fine_pi_freq"] = {}
        for j, k in enumerate(pairs):
            span = float(spans[min(j, len(spans) - 1)])
            npts = int(points[min(j, len(points) - 1)])
            rd = self._frequency_scan(cfg, center, span, npts, k, int(P["shots"]))
            self.node_data["fine_pi_freq"]["K%d" % k] = rd
            f = rd["fit"]
            if not f["ok"]:
                self._say("fine_pi_freq", "WARN",
                          "K=%d pseudo-identity scan has no unique significant central "
                          "zero (response %.1f sigma); keeping %.4f MHz"
                          % (k, rd["response_snr"], center))
                continue
            roots.append({"K": k, "f": f["root"], "err": f["root_err"]})
            center = round(float(f["root"]), 4)
            self._say("fine_pi_freq", "OK",
                      "K=%d signed detuning zero %.4f +/- %.4f MHz (slope %.1f sigma)"
                      % (k, f["root"], f["root_err"], f["slope_snr"]))
        if not roots:
            self.w["fine_freq_converged"] = False
            return {"f": self.w["drive_freq"]}, {"f": 1e9}
        agree = True
        if len(roots) >= 2:
            a, b = roots[-2], roots[-1]
            tol = (float(P["agreement_sigma"]) * np.hypot(a["err"], b["err"])
                   + float(P["agreement_floor_mhz"]))
            agree = abs(a["f"] - b["f"]) <= tol
            self._say("fine_pi_freq", "OK" if agree else "WARN",
                      "independent K=%d/%d roots differ by %.4f MHz (limit %.4f) -> %s"
                      % (a["K"], b["K"], abs(a["f"] - b["f"]), tol,
                         "consistent" if agree else "INCONSISTENT"))
        last = roots[-1]
        precise = float(P["agreement_sigma"]) * last["err"] <= float(P["tol_mhz"])
        self.w["drive_freq"] = round(float(last["f"]), 4)
        self.w["drive_freq_err"] = float(last["err"])
        self.w["fine_freq_converged"] = bool(len(roots) >= min(2, len(pairs)) and agree and precise)
        self.w["updated"].add("qubit_pi_freq")
        return {"f": last["f"]}, {"f": max(3.0 * last["err"], 0.01)}

    def _measure_pi_spe(self, cfg, center_gain, depth, shots, blocks, gap_us=None):
        """Odd-train sparse phase estimate from drift/reference/phase-cycled blocks."""
        P = self.P["fine_pi_amp"]
        n = int(depth)
        if n < 1 or n % 2 == 0:
            raise ValueError("sparse pi depth must be positive and odd")
        g0 = int(round(center_gain))
        dg = max(1, int(round(g0 / (2.0 * n))))
        gains = np.array([g0 - dg, g0, g0 + dg], dtype=int)
        if gains[0] <= 0 or gains[-1] > 32000:
            return {"ok": False, "reason": "gain_limit", "M": n}
        c = dict(cfg)
        if gap_us is not None:
            c["seq_gap_us"] = float(gap_us)
        nblocks = _balanced_block_count(blocks)
        each = max(20, int(np.ceil(float(shots) / nblocks)))
        labels = ("minus", "zero", "plus")
        gmap = dict(zip(labels, gains))
        combos = ((1, 0.0), (-1, 0.0), (1, 180.0), (-1, 180.0))
        orders = [None] * nblocks
        for q in range(0, nblocks, 4):
            phase0 = np.random.permutation(labels).tolist()
            phase180 = np.random.permutation(labels).tolist()
            orders[q:q + 4] = [phase0, phase0[::-1], phase180, phase180[::-1]]
        recs = []
        for b in range(nblocks):
            direction, phase = combos[b % len(combos)]
            order = orders[b]
            block = {"direction": direction, "phase_cycle": phase,
                     "acquisition_order": tuple(order), "ground_steps": [],
                     "ground_step_errors": []}
            for label in order:
                ga = _run_seq(self, c, [], self.w["drive_freq"], each)
                seq = n * [("pulse", int(gmap[label]), phase)]
                rd = _run_seq(self, c, seq, self.w["drive_freq"], each)
                gb = _run_seq(self, c, [], self.w["drive_freq"], each)
                zbase = 0.5 * (complex(ga[0], ga[1]) + complex(gb[0], gb[1]))
                z = complex(rd[0], rd[1]) - zbase
                si = np.sqrt(rd[2] ** 2 + 0.25 * (ga[2] ** 2 + gb[2] ** 2))
                sq = np.sqrt(rd[3] ** 2 + 0.25 * (ga[3] ** 2 + gb[3] ** 2))
                block[label] = (z, float(si), float(sq))
                block["ground_steps"].append(complex(gb[0] - ga[0], gb[1] - ga[1]))
                block["ground_step_errors"].append(
                    (float(np.hypot(ga[2], gb[2])), float(np.hypot(ga[3], gb[3]))))
            recs.append(block)

        ref = np.array([-r["zero"][0] for r in recs], dtype=complex)
        ref_mean = complex(np.mean(ref))
        if abs(ref_mean) <= 0:
            return {"ok": False, "reason": "dead_reference", "M": n}
        u = np.array([ref_mean.real, ref_mean.imag]) / abs(ref_mean)

        def projected(r, label):
            z, si, sq = r[label]
            return (float(z.real * u[0] + z.imag * u[1]),
                    float(np.sqrt((si * u[0]) ** 2 + (sq * u[1]) ** 2)))

        block_values, block_fits = [], []
        for r in recs:
            ve = [projected(r, label) for label in labels]
            block_values.append(ve)
            block_fits.append(sparse_phase_estimate(
                ve[0][0], ve[1][0], ve[2][0], ve[0][1], ve[1][1], ve[2][1],
                n * np.pi, beta=n * np.pi * dg / float(g0)))
        values = np.array([[v[0] for v in row] for row in block_values], dtype=float)
        errors = np.array([[v[1] for v in row] for row in block_values], dtype=float)
        ym = np.mean(values, axis=0)
        ye = np.sqrt(np.sum(errors ** 2, axis=0)) / nblocks
        pooled = sparse_phase_estimate(ym[0], ym[1], ym[2], ye[0], ye[1], ye[2],
                                       n * np.pi, beta=n * np.pi * dg / float(g0))
        deltas = np.array([(f["phase"] - n * np.pi) / n for f in block_fits if f["ok"]])
        stat = pooled["phase_err"] / n if pooled["ok"] else np.inf
        scatter = (float(np.std(deltas, ddof=1) / np.sqrt(deltas.size))
                   if deltas.size >= 2 else np.inf)

        def group_delta(key, value):
            d = [((f["phase"] - n * np.pi) / n) for f, r in zip(block_fits, recs)
                 if f["ok"] and r[key] == value]
            return float(np.mean(d)) if d else np.nan

        d_f, d_r = group_delta("direction", 1), group_delta("direction", -1)
        d_0, d_180 = group_delta("phase_cycle", 0.0), group_delta("phase_cycle", 180.0)
        order_sys = 0.5 * abs(d_f - d_r) if np.isfinite(d_f) and np.isfinite(d_r) else np.inf
        phase_sys = (0.5 * abs(d_0 - d_180)
                     if np.isfinite(d_0) and np.isfinite(d_180) else np.inf)
        delta_err = float(np.sqrt(max(stat, scatter) ** 2 + order_sys ** 2 + phase_sys ** 2))

        ref_se = np.array([projected(r, "zero")[1] for r in recs])
        ref_snr = abs(ref_mean) / max(float(np.sqrt(np.sum(ref_se ** 2)) / nblocks), 1e-15)
        ref_mag = np.abs(ref)
        ref_change = float(np.ptp(ref_mag) / max(np.mean(ref_mag), 1e-15))
        angles = np.rad2deg(np.angle(ref * np.conj(ref_mean)))
        axis_rotation = float(np.max(np.abs(angles)))
        ground_steps = np.asarray([z for r in recs for z in r["ground_steps"]],
                                  dtype=complex)
        ground_errors = np.asarray(
            [e for r in recs for e in r["ground_step_errors"]], dtype=float)
        raw_ground_step_frac = float(
            np.max(np.abs(ground_steps)) / max(abs(ref_mean), 1e-15))
        motion_sigma = float(P.get("ground_motion_sigma", 4.0))
        excess_i = np.maximum(np.abs(ground_steps.real)
                              - motion_sigma * ground_errors[:, 0], 0.0)
        excess_q = np.maximum(np.abs(ground_steps.imag)
                              - motion_sigma * ground_errors[:, 1], 0.0)
        ground_step_frac = float(
            np.max(np.hypot(excess_i, excess_q)) / max(abs(ref_mean), 1e-15))
        noise_delta = max(stat, 1e-15) * np.sqrt(2.0)
        order_sigma = max(order_sys, phase_sys) / noise_delta
        delta = (pooled["phase"] - n * np.pi) / n if pooled["ok"] else np.nan
        denom = np.pi + delta
        root = g0 * np.pi / denom if np.isfinite(denom) and denom > 0 else np.nan
        root_err = (g0 * np.pi * delta_err / (denom ** 2)
                    if np.isfinite(root) else np.inf)
        ok = bool(pooled["ok"] and deltas.size >= 2
                  and pooled["phase_snr"] >= float(P["min_phase_snr"])
                  and ref_snr >= float(P["min_ref_snr"])
                  and ref_change <= float(P["max_ref_change_frac"])
                  and ground_step_frac <= float(P["max_local_ground_step_frac"])
                  and axis_rotation <= float(P["max_axis_rotation_deg"])
                  and order_sigma <= float(P["max_order_sigma"])
                  and np.isfinite(root_err))
        return {"ok": ok, "M": n, "gains": gains, "res": ym, "err": ye,
                "center": g0, "gain": float(root), "gain_err": float(root_err),
                "delta": float(delta), "delta_err": float(delta_err),
                "phase_snr": float(pooled["phase_snr"]), "ref_snr": float(ref_snr),
                "ref_change": ref_change, "axis_rotation_deg": axis_rotation,
                "max_local_ground_step_frac": ground_step_frac,
                "raw_max_local_ground_step_frac": raw_ground_step_frac,
                "order_sigma": float(order_sigma), "block_deltas": deltas,
                "beta": float(n * np.pi * dg / float(g0)), "gap_us": c.get("seq_gap_us", 0.01)}

    def _equator_point(self, cfg, gain, depth, shots):
        """Independent signed audit: +/-X90 preparation followed by an even pi train."""
        pi2 = max(1, int(round(self.w["pi_gain"] / 2.0)))
        core = int(depth) * [("pulse", int(gain), 0.0)]
        seq = {1: [("pulse", pi2, 0.0)] + core,
               -1: [("pulse", pi2, 180.0)] + core}
        each = max(20, int(np.ceil(float(shots) / 2.0)))
        obs = {1: [], -1: []}
        for sign in (1, -1, -1, 1):
            I, Q, sI, sQ = _run_seq(self, cfg, seq[sign], self.w["drive_freq"], each)
            obs[sign].append((complex(I, Q), sI, sQ))

        def mean(sign):
            a = obs[sign]
            return (sum(v[0] for v in a) / len(a),
                    np.sqrt(sum(v[1] ** 2 for v in a)) / len(a),
                    np.sqrt(sum(v[2] ** 2 for v in a)) / len(a))

        zp, sip, sqp = mean(1)
        zm, sim, sqm = mean(-1)
        return zp - zm, float(np.hypot(sip, sim)), float(np.hypot(sqp, sqm))

    def _measure_equator_root(self, cfg, center_gain, depth, shots, points=5, gap_us=None):
        n = int(depth)
        if n < 2 or n % 2:
            raise ValueError("equator audit depth must be positive and even")
        c = dict(cfg)
        if gap_us is not None:
            c["seq_gap_us"] = float(gap_us)
        points = max(int(points), 5) | 1
        dg = max(1, int(round(float(center_gain) / (4.0 * n))))
        offs = np.arange(-(points // 2), points // 2 + 1)
        gains = np.unique(np.round(float(center_gain) + offs * dg).astype(int))
        gains = gains[(gains > 0) & (gains <= 32000)]
        z, sei, seq = np.empty(gains.size, complex), np.empty(gains.size), np.empty(gains.size)
        mid = float(center_gain)
        for j in sorted(range(gains.size), key=lambda k: abs(gains[k] - mid)):
            z[j], sei[j], seq[j] = self._equator_point(c, int(gains[j]), n, int(shots))
        u = self._principal_iq_axis(z, center=False)
        sig = z.real * u[0] + z.imag * u[1]
        err = np.sqrt((sei * u[0]) ** 2 + (seq * u[1]) ** 2)
        err = np.maximum(err, np.nanmedian(err[np.isfinite(err)]) * 0.1 + 1e-15)
        fit = fit_symmetric_zero(gains, sig, err, center_gain, min_side_snr=5.0,
                                 wavenumber=n * np.pi / max(float(center_gain), 1.0))
        response_snr = float(np.nanmax(np.abs(sig) / np.maximum(err, 1e-15)))
        fit["ok"] = bool(fit["ok"] and response_snr >= 5.0)
        return {"ok": fit["ok"], "M": n, "gains": gains, "res": sig, "err": err,
                "gain": fit["root"], "gain_err": fit["root_err"],
                "slope_snr": fit["slope_snr"], "response_snr": response_snr,
                "gap_us": c.get("seq_gap_us", 0.01)}

    def _measure_peak_root(self, cfg, center_gain, depth, shots, points=7, gap_us=None):
        """Fresh held-out odd-train maximum, with local drift brackets.

        The signed equator audit below is wonderfully sensitive while driven coherence
        survives, but on this device a long +/-X90 sequence can lose all contrast even
        though population-based pi trains remain excellent.  This second verifier uses
        a depth omitted from the optimizer and locates the *maximum* of an odd train.
        It is deliberately not allowed to choose a distant branch: the signed hierarchy
        has already done that, and this scan only judges the central local maximum.
        """
        n = int(depth)
        if n < 1:
            raise ValueError("peak audit depth must be positive")
        if n % 2 == 0:
            n += 1
        c = dict(cfg)
        if gap_us is not None:
            c["seq_gap_us"] = float(gap_us)
        points = max(int(points), 7) | 1
        half_frac = 0.70 / n
        gains = np.unique(np.round(float(center_gain) *
                                   (1.0 + np.linspace(-half_frac, half_frac, points))).astype(int))
        gains = gains[(gains > 0) & (gains <= 32000)]
        if gains.size < 7:
            return {"ok": False, "reason": "gain_limit", "M": n}
        nblocks = _balanced_block_count(self.P["fine_pi_amp"].get("blocks", 4))
        each = max(20, int(np.ceil(float(shots) / nblocks)))
        raw = np.empty((nblocks, gains.size), dtype=complex)
        sei = np.empty((nblocks, gains.size), dtype=float)
        seq = np.empty((nblocks, gains.size), dtype=float)
        refs = np.empty(nblocks, dtype=complex)
        directions = np.empty(nblocks, dtype=int)
        ground_steps = np.empty((nblocks, gains.size), dtype=complex)
        ground_step_si = np.empty((nblocks, gains.size), dtype=float)
        ground_step_sq = np.empty((nblocks, gains.size), dtype=float)
        orders = []
        for _ in range(nblocks // 2):
            perm = np.random.permutation(gains.size).astype(int).tolist()
            orders.extend((perm, perm[::-1]))
        for b in range(nblocks):
            direction = 1 if b % 2 == 0 else -1
            directions[b] = direction
            order = orders[b]
            for j in order:
                # A single bracket around the whole sweep removes affine drift but lets
                # even-in-time curvature synthesize a perfectly symmetric fake peak.
                # Independent local brackets make linear drift cancel point-by-point;
                # quadratic curvature contributes the same offset at every gain and
                # therefore cannot imitate a Rabi fringe.
                ga = _run_seq(self, c, [], self.w["drive_freq"], each)
                rd = _run_seq(self, c, n * [("pulse", int(gains[j]), 0.0)],
                              self.w["drive_freq"], each)
                gb = _run_seq(self, c, [], self.w["drive_freq"], each)
                base = 0.5 * (complex(ga[0], ga[1]) + complex(gb[0], gb[1]))
                raw[b, j] = complex(rd[0], rd[1]) - base
                sei[b, j] = np.sqrt(rd[2] ** 2 + 0.25 * (ga[2] ** 2 + gb[2] ** 2))
                seq[b, j] = np.sqrt(rd[3] ** 2 + 0.25 * (ga[3] ** 2 + gb[3] ** 2))
                ground_steps[b, j] = complex(gb[0] - ga[0], gb[1] - ga[1])
                ground_step_si[b, j] = np.hypot(ga[2], gb[2])
                ground_step_sq[b, j] = np.hypot(ga[3], gb[3])
            refs[b] = raw[b, int(np.argmin(abs(gains - float(center_gain))))]

        ref_mean = complex(np.mean(refs))
        if abs(ref_mean) <= 0:
            return {"ok": False, "reason": "dead_reference", "M": n}
        u = np.array([ref_mean.real, ref_mean.imag]) / abs(ref_mean)
        values = raw.real * u[0] + raw.imag * u[1]
        errors = np.sqrt((sei * u[0]) ** 2 + (seq * u[1]) ** 2)
        pooled_y = np.mean(values, axis=0)
        pooled_e = np.sqrt(np.sum(errors ** 2, axis=0)) / nblocks
        k_guess = n * np.pi / max(float(center_gain), 1.0)
        pooled = fit_cosine_peak(gains, pooled_y, pooled_e, center_gain, k_guess)
        pooled_shape = (pooled.get("wavenumber", np.nan),
                        pooled.get("quadratic_phase", np.nan))
        block = [fit_cosine_peak(gains, values[b], errors[b], center_gain, k_guess,
                                 fixed_shape=pooled_shape)
                 for b in range(nblocks)]
        roots = np.array([r["root"] for r in block
                          if r.get("ok") and np.isfinite(r["root_err"])], dtype=float)
        stat = float(pooled["root_err"])
        scatter = (float(np.std(roots, ddof=1) / np.sqrt(roots.size))
                   if roots.size >= 2 else np.inf)
        fwd = [r["root"] for r, d in zip(block, directions)
               if d > 0 and r.get("ok") and np.isfinite(r["root_err"])]
        rev = [r["root"] for r, d in zip(block, directions)
               if d < 0 and r.get("ok") and np.isfinite(r["root_err"])]
        order_sys = (0.5 * abs(np.mean(fwd) - np.mean(rev)) if fwd and rev else np.inf)
        root_err = float(np.sqrt(max(stat, scatter) ** 2 + order_sys ** 2))
        k0 = int(np.argmin(abs(gains - float(center_gain))))
        edge = 0.5 * (pooled_y[0] + pooled_y[-1])
        edge_err = np.sqrt(pooled_e[k0] ** 2
                           + 0.25 * (pooled_e[0] ** 2 + pooled_e[-1] ** 2))
        curve_snr = float((pooled_y[k0] - edge) / max(edge_err, 1e-15))
        ref_snr = float(abs(ref_mean) /
                        max(np.sqrt(np.sum(errors[:, k0] ** 2)) / nblocks, 1e-15))
        ref_change = float(np.ptp(np.abs(refs)) / max(np.mean(np.abs(refs)), 1e-15))
        angles = np.rad2deg(np.angle(refs * np.conj(ref_mean)))
        axis_rotation = float(np.max(np.abs(angles)))
        raw_ground_step_frac = float(
            np.max(np.abs(ground_steps)) / max(abs(ref_mean), 1e-15))
        motion_sigma = float(self.P["fine_pi_amp"].get("ground_motion_sigma", 4.0))
        excess_i = np.maximum(np.abs(ground_steps.real) - motion_sigma * ground_step_si, 0.0)
        excess_q = np.maximum(np.abs(ground_steps.imag) - motion_sigma * ground_step_sq, 0.0)
        ground_step_frac = float(
            np.max(np.hypot(excess_i, excess_q)) / max(abs(ref_mean), 1e-15))
        root = float(pooled["root"])
        central = abs(root - float(center_gain)) <= 0.55 * half_frac * float(center_gain)
        gates = {
            "pooled_fit": bool(pooled["ok"]),
            "independent_blocks": bool(roots.size >= 2 and np.isfinite(root_err)),
            "curve_contrast": bool(curve_snr >= 5.0),
            "reference_contrast": bool(ref_snr >= 5.0),
            "reference_stability": bool(
                ref_change <= float(self.P["fine_pi_amp"]["max_ref_change_frac"])),
            "local_ground_motion": bool(
                ground_step_frac <= float(
                    self.P["fine_pi_amp"]["max_local_ground_step_frac"])),
            "axis_stability": bool(
                axis_rotation <= float(self.P["fine_pi_amp"]["max_axis_rotation_deg"])),
            "central_root": bool(central),
        }
        failed_gates = [name for name, passed in gates.items() if not passed]
        ok = not failed_gates
        block_diagnostics = [{
            "direction": int(directions[j]), "ok": bool(rd.get("ok")),
            "root": float(rd.get("root", np.nan)),
            "root_err": float(rd.get("root_err", np.inf)),
            "amplitude_snr": float(rd.get("amplitude_snr", 0.0)),
            "red_chi2": float(rd.get("red_chi2", np.inf)),
            "wavenumber": float(rd.get("wavenumber", np.nan)),
            "interior": bool(rd.get("interior", False)),
        } for j, rd in enumerate(block)]
        return {"ok": ok, "failed_gates": failed_gates, "M": n,
                "gains": gains, "res": pooled_y,
                "err": pooled_e, "gain": root, "gain_err": root_err,
                "curve_snr": curve_snr, "ref_snr": ref_snr,
                "ref_change": ref_change,
                "fit_ok": bool(pooled.get("ok")),
                "fit_amplitude_snr": pooled.get("amplitude_snr", 0.0),
                "fit_interior": bool(pooled.get("interior", False)),
                "fit_red_chi2": pooled.get("red_chi2", np.inf),
                "fit_wavenumber": pooled.get("wavenumber", np.nan),
                "axis_rotation_deg": axis_rotation, "order_sys": float(order_sys),
                "central": bool(central),
                "block_roots": roots, "block_diagnostics": block_diagnostics,
                "max_local_ground_step_frac": ground_step_frac,
                "raw_max_local_ground_step_frac": raw_ground_step_frac,
                "acquisition_orders": orders,
                "gap_us": c.get("seq_gap_us", 0.01)}

    def _amplitude_audit(self, cfg, center_gain, gap_us=None, shots=None):
        """Authoritative held-out peak audit plus an optional coherent cross-check."""
        P = self.P["fine_pi_amp"]
        audit_shots = max(20, int(P["shots"] if shots is None else shots))
        gap = float(cfg.get("seq_gap_us", 0.01) if gap_us is None else gap_us)
        t_pi = 4.0 * float(self.cfg["sigma"])
        t1 = float(self.w.get("t1_lo_us", self.w.get("t1_us", np.inf)))
        if np.isfinite(t1) and t1 > 0:
            max_depth = max(1, int(np.floor(0.5 * t1 / max(t_pi + gap, 1e-12))))
        else:
            peak_cfg = P.get("validation_peak_M_list", (P["validation_peak_M"],))
            max_depth = max([int(P["validation_M"])] + [int(v) for v in peak_cfg])
        requested = P.get("validation_peak_M_list", (P["validation_peak_M"],))
        if not isinstance(requested, (tuple, list)):
            requested = (requested,)
        optimizer_depths = {1} | {int(v) if int(v) % 2 else int(v) + 1 for v in P["M_list"]}
        available = list(range(1, max_depth + 1, 2))
        independent = [d for d in available if d not in optimizer_depths]
        peak_depths = []
        for raw in requested:
            target = min(max(1, int(raw) | 1), max_depth)
            candidates = [d for d in independent if d not in peak_depths]
            if not candidates:
                break
            depth = min(candidates, key=lambda d: (abs(d - target), -d))
            peak_depths.append(depth)
        peaks = [self._measure_peak_root(
            cfg, center_gain, depth, audit_shots, int(P["validation_points"]),
            gap_us=gap_us) for depth in peak_depths]
        confidence = float(P["confidence_sigma"])
        for peak in peaks:
            peak_bound = np.inf
            if peak.get("ok"):
                peak_bound = (abs(peak["gain"] - center_gain)
                              + confidence * peak["gain_err"]) \
                    / max(float(center_gain), 1.0)
            peak["bound_frac"] = float(peak_bound)
        required_peaks = min(2, len(requested))
        peak_ok = bool(len(peaks) >= required_peaks and required_peaks > 0
                       and all(rd.get("ok") and rd["bound_frac"] <= float(P["tol_frac"])
                               for rd in peaks))
        good_peaks = [rd for rd in peaks if rd.get("ok")]
        if good_peaks:
            peak_gain = float(np.median([rd["gain"] for rd in good_peaks]))
            peak_spread = 0.5 * float(np.ptp([rd["gain"] for rd in good_peaks]))
            peak_err = max([float(rd["gain_err"]) for rd in good_peaks] + [peak_spread])
            peak_bound = max(float(rd["bound_frac"]) for rd in good_peaks)
            peak = min(good_peaks, key=lambda rd: rd["bound_frac"])
        else:
            peak_gain, peak_err, peak_bound = np.nan, np.inf, np.inf
            peak = peaks[0] if peaks else {"ok": False, "reason": "no_peak_depth"}

        # Coherent contrast can collapse at a long depth.  Descend through powers of
        # two and retain the most constraining valid result.  The cross-check can either
        # corroborate, contradict, or be statistically inconclusive; an inconclusive
        # low-contrast experiment must not veto the high-contrast population audit.
        equator_trials = []
        if max_depth < 2:
            equator_trials.append({"ok": False, "M": 0, "bound_frac": np.inf,
                                    "reason": "T1_limit"})
        else:
            n = min(int(P["validation_M"]), max_depth)
            if n % 2:
                n -= 1
            n = max(2, n)
            while n >= 2:
                equator = self._measure_equator_root(
                    cfg, center_gain, n, audit_shots, int(P["validation_points"]),
                    gap_us=gap_us)
                bound = np.inf
                if equator.get("ok"):
                    delta = abs(equator["gain"] - center_gain)
                    bound = (delta + confidence * equator["gain_err"]) \
                        / max(float(center_gain), 1.0)
                    lower = max(0.0, delta - confidence * equator["gain_err"]) \
                        / max(float(center_gain), 1.0)
                    equator["lower_bound_frac"] = float(lower)
                equator["bound_frac"] = float(bound)
                equator_trials.append(equator)
                if (len(equator_trials) >= 2
                        and any(rd.get("ok") and rd["bound_frac"] <= float(P["tol_frac"])
                                for rd in equator_trials)):
                    break
                if n == 2:
                    break
                n = max(2, 2 * (n // 4))
        usable = [rd for rd in equator_trials if rd.get("ok")]
        equator = min(usable, key=lambda rd: rd["bound_frac"]) if usable else equator_trials[0]
        equator_bound = float(equator.get("bound_frac", np.inf))

        corroborates = any(rd.get("ok") and rd["bound_frac"] <= float(P["tol_frac"])
                           for rd in equator_trials)
        contradicts = any(rd.get("ok")
                          and rd.get("lower_bound_frac", 0.0) > float(P["tol_frac"])
                          for rd in equator_trials)
        coherent_status = ("contradicts" if contradicts else
                           "corroborates" if corroborates else "inconclusive")
        coherent_ok = not contradicts
        ok = bool(peak_ok and coherent_ok)
        return {"ok": ok, "gain": peak_gain, "gain_err": peak_err,
                "bound_frac": float(peak_bound), "peak": peak, "peaks": peaks,
                "equator": equator,
                "equator_trials": equator_trials,
                "coherent_status": coherent_status,
                "coherent_checked": bool(equator.get("ok")), "gap_us": gap_us,
                "shots": audit_shots}

    def _cal_fine_pi_amp(self):
        """Signed odd-train calibration with independent population/axis audits."""
        P = self.P["fine_pi_amp"]
        requested_blocks = int(P["blocks"])
        balanced_blocks = _balanced_block_count(requested_blocks)
        if balanced_blocks != requested_blocks:
            self._say("fine_pi_amp", "WARN", "blocks=%d expanded to %d so every "
                      "forward/reverse and 0/180-degree phase cycle is complete"
                      % (requested_blocks, balanced_blocks))
        cfg = self._cfg_for("fine_pi_amp")
        anchor = float(self.w["pi_gain"])
        est = anchor
        anchor_err = max(float(self.w.get("pi_gain_anchor_err", np.inf)),
                         float(P["anchor_floor_frac"]) * anchor)
        est_err = anchor_err
        t1 = float(self.w.get("t1_lo_us", self.w.get("t1_us", 30.0)))
        t_pi = 4.0 * float(self.cfg["sigma"])
        gap = float(cfg.get("seq_gap_us", 0.01))
        depths = [1]
        for raw in P["M_list"]:
            n = int(raw)
            if n % 2 == 0:
                n += 1
                self._say("fine_pi_amp", "WARN",
                          "legacy even M=%d converted to odd M=%d for signed phase "
                          "estimation" % (raw, n))
            if n > 0 and n not in depths:
                depths.append(n)
        depths.sort()
        accepted = []
        branch_anchor = None
        self.node_data["fine_pi_amp"] = {}
        for n in depths:
            # SeqProgram inserts the configured gap after every pulse, including the
            # final pulse before measurement, so include all n gaps in the bound.
            train_time = n * (t_pi + gap)
            if train_time > 0.5 * t1:
                self._say("fine_pi_amp", "WARN", "skipping M=%d (%.2f us train exceeds "
                          "the conservative T1/2 limit %.2f us)" % (n, train_time, 0.5 * t1))
                break
            capture = n * 1.96 * est_err / max(est, 1.0)
            if capture > float(P["capture_95_frac"]):
                self._say("fine_pi_amp", "WARN", "skipping M=%d: the prior 95%% interval "
                          "occupies %.2f of a phase branch (limit %.2f); use a shorter "
                          "train before error amplification"
                          % (n, capture, P["capture_95_frac"]))
                break
            rd = self._measure_pi_spe(cfg, est, n, int(P["shots"]), balanced_blocks)
            self.node_data["fine_pi_amp"]["M%d" % n] = rd
            if not rd["ok"]:
                self._say("fine_pi_amp", "WARN", "M=%d rejected: phase %.1f sigma, local "
                          "reference %.1f sigma, axis drift %.1f deg, order/phase-cycle "
                          "disagreement %.1f sigma, local ground motion %.1f%% of contrast"
                          % (n, rd.get("phase_snr", 0.0), rd.get("ref_snr", 0.0),
                             rd.get("axis_rotation_deg", np.inf), rd.get("order_sigma", np.inf),
                             100 * rd.get("max_local_ground_step_frac", np.inf)))
                self._say("fine_pi_amp", "WARN", "the signed depth hierarchy stops here; "
                          "a longer train has a narrower phase branch and cannot safely "
                          "rescue a failed shorter train")
                break
            correction = abs(rd["gain"] - est) / max(est, 1.0)
            limit = (float(P["max_initial_correction_frac"]) if n == 1 else
                     float(P["max_correction_frac"]))
            if correction > limit:
                self._say("fine_pi_amp", "WARN", "M=%d requests a %.1f%% move, beyond its "
                          "unambiguous %.1f%% capture guard -- rejected as an alias"
                          % (n, 100 * correction, 100 * limit))
                self._say("fine_pi_amp", "WARN", "the signed depth hierarchy stops here; "
                          "longer depths are more aliased, not less")
                break
            if n > 1 and branch_anchor is not None:
                cumulative = abs(rd["gain"] - branch_anchor) / max(branch_anchor, 1.0)
                if cumulative > float(P["max_cumulative_correction_frac"]):
                    self._say("fine_pi_amp", "WARN", "M=%d would move %.1f%% outside the "
                              "broad M=1 branch anchor (limit %.1f%%) -- rejecting a "
                              "multi-step alias walk"
                              % (n, 100 * cumulative,
                                 100 * P["max_cumulative_correction_frac"]))
                    break
            rd["correction_frac"] = float(correction)
            accepted.append(rd)
            est, est_err = float(rd["gain"]), float(rd["gain_err"])
            if n == 1:
                branch_anchor = est
            self.w["pi_gain"] = int(round(est))
            self._say("fine_pi_amp", "OK", "M=%2d signed phase -> pi %.0f +/- %.0f DAC "
                      "(phase %.1f sigma, reference %.1f sigma)"
                      % (n, est, est_err, rd["phase_snr"], rd["ref_snr"]))

        floor = float(P["agreement_floor_frac"])
        consistent = []
        if accepted:
            consistent = [accepted[-1]]
            for rd in accepted[-2::-1]:
                tol = (float(P["agreement_sigma"]) * np.hypot(rd["gain_err"],
                                                               consistent[0]["gain_err"])
                       + floor * est)
                if abs(rd["gain"] - consistent[0]["gain"]) <= tol:
                    consistent.insert(0, rd)
        corrections = [float(rd["correction_frac"]) for rd in accepted]
        hierarchy_stable = all(
            cur <= max(float(P["contraction_factor"]) * prev,
                       float(P["max_rebound_frac"]))
            for prev, cur in zip(corrections, corrections[1:]))
        depth_ok = len(accepted) >= int(P["min_depths"]) and hierarchy_stable
        if accepted:
            spread = (max(r["gain"] for r in consistent) - min(r["gain"] for r in consistent)
                      if len(consistent) >= 2 else np.inf)
            self._say("fine_pi_amp", "OK" if depth_ok else "WARN",
                      "signed depth hierarchy: %d valid depths (%d trailing estimates "
                      "statistically agree; updates %s)%s"
                      % (len(accepted), len(consistent),
                         "contract" if hierarchy_stable else "DO NOT CONTRACT",
                         "" if depth_ok else
                         " -- at least %d valid, stable depths required" % P["min_depths"]))
        else:
            spread = np.inf

        # Two held-out odd depths are the authoritative population audit.  They judge
        # the signed estimate; they never relocate it.  Relocating from a periodic audit
        # without rerunning SPE can silently jump branches, so every requested repeat is
        # acquired at the unchanged candidate and must pass independently.
        audit = None
        audit_history = []
        audit_attempts = []
        required_rounds = max(1, int(P["validation_rounds"]))
        base_audit_shots = max(20, int(P["shots"]))
        audit_shots = base_audit_shots
        max_audit_shots = base_audit_shots * max(
            1, int(P.get("validation_max_shot_multiplier", 1)))
        if accepted:
            while True:
                attempt = []
                for _ in range(required_rounds):
                    self.w["pi_gain"] = int(round(est))
                    audit = self._amplitude_audit(cfg, est, shots=audit_shots)
                    attempt.append(audit)
                audit_attempts.append(attempt)
                audit_history = attempt
                if all(rd.get("ok") for rd in attempt):
                    break
                retry_limit = (float(P.get("validation_retry_bound_factor", 2.0))
                               * float(P["tol_frac"]))
                retryable = bool(
                    all(rd.get("coherent_status") != "contradicts"
                        and rd.get("peaks")
                        and all(pk.get("ok") and np.isfinite(pk.get("bound_frac", np.inf))
                                and pk.get("bound_frac", np.inf) <= retry_limit
                                for pk in rd["peaks"])
                        for rd in attempt))
                if not retryable or audit_shots >= max_audit_shots:
                    break
                next_shots = min(max_audit_shots, 2 * audit_shots)
                self._say("fine_pi_amp", "WARN", "held-out roots are physical but "
                          "precision-limited at %d shots; repeating both independent "
                          "audits at %d shots without moving the candidate"
                          % (audit_shots, next_shots))
                audit_shots = next_shots
        self.node_data["fine_pi_amp"]["audit"] = audit_history
        self.node_data["fine_pi_amp"]["audit_attempts"] = audit_attempts
        audit_ok = bool(len(audit_history) == required_rounds
                        and all(rd.get("ok") for rd in audit_history))
        audit_bound = (max(float(rd.get("bound_frac", np.inf)) for rd in audit_history)
                       if audit_history else np.inf)
        if audit:
            coherent = audit["equator"]
            peak_text = ", ".join(
                ("M=%d %.0f+/-%.0f (%.3f%%)" %
                  (rd.get("M", -1), rd.get("gain", np.nan), rd.get("gain_err", np.inf),
                  100 * rd.get("bound_frac", np.inf))) if rd.get("ok") else
                "M=%d FAILED:%s" % (rd.get("M", -1),
                                    ",".join(rd.get("failed_gates", [rd.get("reason", "unknown")])))
                for rd in audit.get("peaks", []))
            self._say("fine_pi_amp", "OK" if audit_ok else "WARN",
                      "held-out peak audits [%s] vs unchanged %.0f DAC at %d shots; %d/%d repeats "
                      "passed, worst 95%% bound %s (target %.3f%%)%s"
                      % (peak_text, est, audit_shots,
                         sum(bool(rd.get("ok")) for rd in audit_history),
                         required_rounds,
                         ("%.3f%%" % (100 * audit_bound)) if np.isfinite(audit_bound) else "FAILED",
                         100 * P["tol_frac"],
                         (("; coherent +/-X90 cross-check %s (95%% upper %.3f%%)" %
                           (audit["coherent_status"], 100 * coherent["bound_frac"]))
                          if coherent.get("ok") else
                          "; coherent +/-X90 cross-check had insufficient contrast")))

        gap_ok = True
        gap_audit = None
        if audit_ok and float(P.get("gap_check_factor", 0.0)) > 1.0:
            gap2 = max(gap, 1e-6) * float(P["gap_check_factor"])
            gap_audit = self._amplitude_audit(cfg, est, gap_us=gap2,
                                              shots=audit_shots)
            if gap_audit["ok"]:
                tol = (float(P["agreement_sigma"]) * np.hypot(audit["gain_err"],
                                                                gap_audit["gain_err"])
                       + floor * est)
                gap_ok = abs(gap_audit["gain"] - audit["gain"]) <= tol
            else:
                gap_ok = False
            self.node_data["fine_pi_amp"]["gap_audit"] = gap_audit
            self._say("fine_pi_amp", "OK" if gap_ok else "WARN",
                      "pulse-gap audit at %.3f us %s the production-gap result%s"
                      % (gap2, "agrees with" if gap_ok else "DISAGREES with",
                         "" if gap_ok else " -- pulse-history distortion or detuning remains"))

        if accepted:
            finite_err = [r["gain_err"] for r in consistent if np.isfinite(r["gain_err"])]
            audit_err = [rd["gain_err"] for rd in audit_history
                         if rd.get("ok") and np.isfinite(rd.get("gain_err", np.inf))]
            pieces = finite_err + audit_err
            if np.isfinite(spread):
                pieces.append(0.5 * spread)
            candidate_err = max(pieces) if pieces else np.inf
            candidate_gain = int(round(est))
        else:
            candidate_gain, candidate_err = int(round(anchor)), float(anchor_err)
        converged = bool(depth_ok and audit_ok and gap_ok
                         and self.w.get("fine_freq_converged", False))
        # A failed candidate is diagnostic only.  Never promote it to the next graph
        # round's anchor: repeated failed rounds could otherwise ratchet through periodic
        # aliases until one happened to pass.
        if converged:
            applied_gain, applied_err = candidate_gain, float(candidate_err)
        else:
            applied_gain, applied_err = int(round(anchor)), float(anchor_err)
        self.w["pi_gain"] = applied_gain
        self.w["pi_gain_err"] = applied_err
        self.w["pi_gain_anchor_err"] = applied_err
        self.w["pi_candidate_gain"] = candidate_gain
        self.w["pi_candidate_err"] = float(candidate_err)
        self.w["pi_n_agree"] = len(consistent)
        self.w["pi_n_valid"] = len(accepted)
        self.w["pi_audit_bound_frac"] = float(audit_bound)
        self.w["pi_validation_shots"] = int(audit_shots)
        self.w["pi_converged"] = converged
        self.w["updated"].add("qubit_pi_gain")
        reasons = []
        if not depth_ok:
            reasons.append("signed depth hierarchy was too short or did not contract")
        if not self.w.get("fine_freq_converged", False):
            reasons.append("signed frequency calibration did not converge")
        if not audit_ok:
            reasons.append("held-out amplitude audit failed")
        if not gap_ok:
            reasons.append("pulse-gap audit disagreed")
        self._say("fine_pi_amp", "OK" if self.w["pi_converged"] else "WARN",
                  "FINAL pi candidate %d +/- %.0f DAC -> %s"
                  % (candidate_gain, candidate_err,
                     "CONVERGED with independent verification" if self.w["pi_converged"]
                     else "REJECTED; kept anchor %d (%s)" %
                     (applied_gain, "; ".join(reasons))))
        return {"g": float(self.w["pi_gain"])}, \
            {"g": max(3.0 * applied_err,
                      float(P["tol_frac"]) * max(float(self.w["pi_gain"]), 1.0))}

    def _score(self):
        """Best-so-far score: safe pi state, then fidelity; bounded diagnostics last.

        The previous nominally "weak" ``0.01*sep`` term was not weak when the simulator
        produced 100--300 sigma: it could make a 60% state outrank a 90% state.  Scaling
        fidelity by 1000 and capping diagnostics makes that ordering impossible.
        """
        sep = float(self.w.get("ss_sep_sigma", 0.0))
        fid = float(self.w.get("ss_fidelity", 0.0))
        fid_se = float(self.w.get("ss_fidelity_se", np.inf))
        fid_lcb = -1.0 if not np.isfinite(fid_se) else fid - 1.96 * fid_se
        pig = float(self.w.get("pi_gain", 1))
        pie = float(self.w.get("pi_gain_err", np.inf))
        prec = 0.0 if not np.isfinite(pie) else max(0.0, 1.0 - (pie / max(pig, 1)) / 0.02)
        pi_safe = bool(self.w.get("pi_converged", False)
                       and self.w.get("fine_freq_converged", False)
                       and t1_timing_domain_valid(self.w)
                       and self.w.get("pi_fidelity_verified", False)
                       and self._pi_fidelity_binding_valid())
        return ((1.0e6 if pi_safe else -1.0e6) + 1000.0 * fid_lcb
                + 1e-3 * np.clip(sep, 0.0, 10.0) + 1e-4 * prec)

    def _pi_fidelity_binding_valid(self):
        """Whether the no-better-neighbor map still covers the committed pulse."""
        b = self.w.get("pi_fidelity_binding")
        if not isinstance(b, dict):
            return False
        static_identity_ok = True
        if "pulse_fingerprint" in b:
            expected = copy.deepcopy(b["pulse_fingerprint"])
            current = self._current_pulse_fingerprint()
            # The directly measured map intentionally certifies a finite drive
            # frequency/gain cell; those two coordinates are checked below against its
            # radii.  Every other waveform/path/timing field must match exactly.
            for key in ("qubit_freq_mhz", "qubit_gain_dac"):
                current[key] = expected.get(key)
            static_identity_ok = current == expected
        return bool(
            static_identity_ok
            and
            abs(float(self.w["drive_freq"]) - float(b["drive_freq"]))
            <= float(b.get("freq_radius", 0.0))
            and abs(float(self.w["pi_gain"]) - float(b["pi_gain"]))
            <= float(b.get("gain_radius", 0.0))
            and abs(float(self.w["read_pulse_freq"])
                    - float(b["read_pulse_freq"])) <= 1e-4
            and int(self.w["read_pulse_gain"]) == int(b["read_pulse_gain"])
            and abs(float(self.w["read_length"]) - float(b["read_length"])) <= 1e-9)

    def _invalidate_pi_fidelity_if_unbound(self):
        """Turn an out-of-cell pi-map certificate back into graph work.

        Fine frequency/amplitude stages have uncertainty-based movement tolerances,
        while the independently measured fidelity map has its own (sometimes tighter)
        spatial cell.  A movement can therefore be statistically small yet leave the
        measured map.  Merely noticing that at the final write gate is safe, but it
        produces a baffling non-convergence.  Re-staling the map here makes the graph
        actually remeasure the final pulse/readout coordinates.
        """
        if (not self.w.get("pi_fidelity_verified", False)
                or self._pi_fidelity_binding_valid()):
            return False
        self.w["pi_fidelity_verified"] = False
        self.w.pop("pi_fidelity_binding", None)
        self.stale["pi_fidelity"] = True
        self._say("graph", "WARN",
                  "the final coherent update left the independently verified pi-map "
                  "cell -- pi_fidelity is stale and will be re-measured at the exact "
                  "final drive/readout coordinates")
        return True

    def _snapshot(self):
        return {"w": copy.deepcopy(self.w), "node_data": copy.deepcopy(self.node_data),
                "stale": copy.deepcopy(self.stale), "drifted": list(self.drifted)}

    def _restore_snapshot(self, snap):
        self.w = copy.deepcopy(snap["w"])
        self.node_data = copy.deepcopy(snap["node_data"])
        self.stale = copy.deepcopy(snap["stale"])
        self.drifted = list(snap["drifted"])

    def maintain(self):
        """Sweep the graph until nothing is stale.  Recalibrating a node whose value MOVED
        by more than its own uncertainty marks its declared dependents stale.  The
        saturation spec and broad Rabi remain deliberate one-time anchors; signed fine
        frequency/amplitude and the readout/T1 chain form the iterative fixed point."""
        values = {
            "resonator":     {"f0": float(self.w["read_pulse_freq"])},
            "spec":          {"f": float(self.w["qubit_freq"])},
            "rough_pi":      {"g": float(self.w["pi_gain"])},
            "t1":            {"t1": float(self.w.get("t1_us", np.nan)),
                              "cap": float(self.w.get("t1_readout_cap_us", np.nan))},
            "chi":           {"f": float(self.w["read_pulse_freq"])},
            "readout_power": {"f": float(self.w["read_pulse_freq"]),
                              "g": float(self.w["read_pulse_gain"])},
            "readout_len":   {"L": float(self.w["read_length"])},
            "single_shot":   {"F": float(self.w.get("ss_fidelity", np.nan))},
            "pi_fidelity":   {"f": float(self.w["drive_freq"]),
                              "g": float(self.w["pi_gain"])},
            "fine_pi_freq":  {"f": float(self.w["drive_freq"])},
            "fine_pi_amp":   {"g": float(self.w["pi_gain"])},
        }
        best_score, best_state = -np.inf, None
        for rnd in range(1, int(self.P["max_rounds"]) + 1):
            self._invalidate_pi_fidelity_if_unbound()
            todo = [n for n, _, _ in GRAPH if self.stale[n]]
            if not todo:
                self._say("graph", "OK", "round %d: nothing stale -- FIXED POINT reached" % rnd)
                s = self._score()
                if s > best_score:
                    best_score, best_state = s, self._snapshot()
                break
            print("-" * 78)
            self._say("graph", "OK", "round %d: recalibrating %s" % (rnd, ", ".join(todo)))
            for name, deps, meth in GRAPH:
                if not self.stale[name]:
                    continue
                try:
                    new, tol = getattr(self, meth)()
                except TunerError as exc:
                    if rnd == 1 or name not in RECOVERABLE or name not in values:
                        raise
                    self.stale[name] = False
                    self._say("graph", "WARN",
                              "%s failed on re-measurement (%s) -- KEEPING the round-1 "
                              "value %s and carrying on; the device has moved since it was "
                              "measured, so treat the committed config as provisional"
                              % (name, str(exc).split(".")[0].strip(),
                                 ", ".join("%s=%.4g" % kv for kv in values[name].items())))
                    self.drifted.append(name)
                    continue
                self.stale[name] = False
                if name == "readout_power":
                    self.w["pi_at_readout"] = float(self.w["pi_gain"])
                old = values.get(name)
                if name == "fine_pi_amp" and np.isfinite(self.w.get("pi_at_readout", np.nan)):
                    old = {"g": float(self.w["pi_at_readout"])}
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
            # In particular, catch a fine-pulse move that was under that node's broad
            # statistical tolerance but outside the tighter measured fidelity-map cell.
            self._invalidate_pi_fidelity_if_unbound()
            s = self._score()
            pending = [n for n, _, _ in GRAPH if self.stale[n]]
            self._say("graph", "OK", "round %d score %.3f (separation %.2f sigma, pi %s)"
                      % (rnd, s, self.w.get("ss_sep_sigma", float('nan')),
                         ("+/- %.0f DAC" % self.w["pi_gain_err"])
                         if np.isfinite(self.w.get("pi_gain_err", np.inf)) else "unmeasured"))
            if pending:
                self._say("graph", "WARN", "round %d ended with stale evidence (%s); it is "
                          "diagnostic only and cannot become the committed best state"
                          % (rnd, ", ".join(pending)))
            elif s > best_score:
                best_score, best_state = s, self._snapshot()
            elif best_state is not None:
                self._say("graph", "WARN", "round %d did not improve on %.3f -- keeping the "
                          "best-so-far state (a worse round is never committed)" % (rnd, best_score))
        if best_state is not None and (any(self.stale.values()) or self._score() < best_score):
            self._restore_snapshot(best_state)
            self._say("graph", "OK", "restored best-so-far state (score %.3f)" % best_score)
        fixed = not any(self.stale.values())
        self.w["fixed_point"] = bool(fixed)
        qubit_nodes = ("spec", "rough_pi", "single_shot", "pi_fidelity",
                       "fine_pi_freq", "fine_pi_amp")
        self.w["qubit_fixed_point"] = not any(self.stale[n] for n in qubit_nodes)
        if not fixed:
            self._say("graph", "WARN", "max_rounds exhausted with stale nodes %s -- this is "
                      "NOT a fixed point and no affected calibration may be written"
                      % ", ".join(n for n, _, _ in GRAPH if self.stale[n]))
        self._verify_final()
        return best_score

    def _verify_final(self):
        """Re-measure readout, pi amplitude *and* drive frequency after state restore.

        The old final check only measured the separation produced by the candidate pi;
        it could not distinguish a bad pi from weak readout, and its ``verified`` flag was
        ignored by the write gate.  These fresh amplitude/frequency sentinels use held-out
        sequence depths and are required by ``qubit_ok``.
        """
        if not hasattr(self, "node_data"):
            self.node_data = {}
        was_sep = float(self.w.get("ss_sep_sigma", np.nan))
        was_fid = float(self.w.get("ss_fidelity", np.nan))
        was_fid_se = float(self.w.get("ss_fidelity_se", np.inf))
        readout_verified = False
        ss = None
        try:
            shots = int(self.P["single_shot"]["shots"])
            coord = (float(self.w["read_pulse_freq"]), int(self.w["read_pulse_gain"]))
            confirmed = self._confirm_candidate_blocks(
                [coord],
                lambda f, g: self._single_shot_point(
                    "single_shot", f, g, self.w["drive_freq"],
                    self.w["pi_gain"], shots),
                self.P["single_shot"].get("verify_blocks", 4),
                self.P["single_shot"].get("max_block_spread", 0.06))
            ss = self._ss_from_aggregate(confirmed[0] if confirmed else None)
        except Exception as exc:
            self._say("verify", "WARN", "the final re-measurement failed (%s) -- the "
                      "readout state is UNVERIFIED" % exc)
        if ss is not None and ss.get("ok", True):
            now_sep, now_fid = float(ss["sep_sigma"]), float(ss["fidelity"])
            now_fid_se = float(ss.get("fidelity_se", np.inf))
            z = float(self.P["single_shot"].get("confidence_sigma", 1.96))
            now_lcb = fidelity_lower_bound(now_fid, now_fid_se, z)
            min_lcb = float(self.P["single_shot"].get("min_fidelity_lcb", 0.80))
            combined = float(np.hypot(now_fid_se, was_fid_se))
            allowed_drop = (float(self.P["single_shot"].get("verify_tol_abs", 0.03))
                            + z * combined)
            fid_drop = (0.0 if not np.isfinite(was_fid) else was_fid - now_fid)
            fidelity_reproduced = bool(fid_drop <= allowed_drop)
            fidelity_usable = bool(now_lcb >= min_lcb)
            self.w["ss_verify_sigma"], self.w["ss_verify_fidelity"] = now_sep, now_fid
            self.w["ss_sep_sigma"], self.w["ss_fidelity"] = now_sep, now_fid
            self.w["ss_fidelity_se"], self.w["ss_fidelity_lcb"] = now_fid_se, now_lcb
            tol = float(self.P["single_shot"]["verify_tol_frac"])
            sep_drift = (0.0 if not np.isfinite(was_sep) or was_sep <= 0
                         else abs(now_sep - was_sep) / was_sep)
            readout_verified = bool(fidelity_usable and fidelity_reproduced)
            self._say("verify", "OK" if readout_verified else "WARN",
                      "readout re-measured: F=%.3f +/- %.3f (95%% LCB %.3f) now vs "
                      "F=%.3f +/- %.3f when chosen; separation %.2f vs %.2f sigma "
                      "(%.0f%% diagnostic drift)%s"
                      % (now_fid, now_fid_se, now_lcb, was_fid, was_fid_se,
                         now_sep, was_sep, 100 * sep_drift,
                         "" if readout_verified else
                         " -- fidelity is below the absolute floor or no longer "
                         "reproduces; readout keys are blocked"))
            ss["verification"] = {
                "reference_fidelity": was_fid, "reference_fidelity_se": was_fid_se,
                "fidelity_lcb": now_lcb, "minimum_lcb": min_lcb,
                "drop": fid_drop, "allowed_drop": allowed_drop,
                "fidelity_usable": fidelity_usable,
                "fidelity_reproduced": fidelity_reproduced,
                "separation_drift_fraction": sep_drift,
                "separation_within_legacy_tolerance": bool(sep_drift <= tol),
            }

        pi_verified, amp_verify = False, None
        try:
            Pa = self.P["fine_pi_amp"]
            ca = self._cfg_for("fine_pi_amp")
            amp_verify = self._amplitude_audit(
                ca, self.w["pi_gain"],
                shots=int(self.w.get("pi_validation_shots",
                                     self.P["fine_pi_amp"]["shots"])))
            pi_verified = bool(amp_verify["ok"])
            self._say("verify", "OK" if pi_verified else "WARN",
                      "fresh held-out pi audit %s"
                      % (("root %.0f +/- %.0f DAC; 95%% bound %.3f%%"
                          % (amp_verify["gain"], amp_verify["gain_err"],
                             100 * amp_verify.get("bound_frac", np.inf)))
                         if amp_verify and amp_verify["peak"].get("ok") else "FAILED"))
        except Exception as exc:
            self._say("verify", "WARN", "fresh pi audit failed (%s)" % exc)

        freq_verified, freq_verify = False, None
        try:
            Pf = self.P["fine_pi_freq"]
            cf = self._cfg_for("fine_pi_freq")
            freq_verify = self._frequency_scan(
                cf, self.w["drive_freq"], float(Pf["validation_span_mhz"]), 7,
                int(Pf["validation_pairs"]), int(Pf["shots"]))
            ff = freq_verify["fit"]
            if ff["ok"]:
                bound = (abs(ff["root"] - self.w["drive_freq"])
                         + 1.96 * ff["root_err"])
                freq_verify["bound_mhz"] = float(bound)
                freq_verified = bound <= float(Pf["tol_mhz"])
            self._say("verify", "OK" if freq_verified else "WARN",
                      "fresh driven-frequency audit %s"
                      % (("root %.4f +/- %.4f MHz; 95%% bound %.4f MHz"
                          % (ff["root"], ff["root_err"],
                             freq_verify.get("bound_mhz", np.inf)))
                         if ff.get("ok") else "FAILED"))
        except Exception as exc:
            self._say("verify", "WARN", "fresh frequency audit failed (%s)" % exc)

        fixed = bool(self.w.get("fixed_point", False))
        mixed = bool(self.drifted)
        self.w["readout_verified"] = bool(readout_verified)
        self.w["pi_verified"] = bool(pi_verified)
        self.w["freq_verified"] = bool(freq_verified)
        self.w["verified"] = bool(readout_verified and pi_verified and freq_verified
                                   and fixed and not mixed)
        self.node_data["final_verify"] = {"single_shot": ss, "amplitude": amp_verify,
                                          "frequency": freq_verify}
        if self.drifted:
            self._say("verify", "WARN",
                      "%s could not be re-measured this run and kept an earlier value -- "
                      "the state mixes evidence from different times and affected keys "
                      "are blocked"
                      % ", ".join(sorted(set(self.drifted))))

    def acquire(self, progress=False, plotDisp=False):
        cfg = self.cfg
        self.data = {}
        q_style = str(cfg.get("qubit_pulse_style", "arb")).lower()
        plateau_fields = explicit_flat_top_fields(cfg)
        if q_style == "arb" and plateau_fields:
            raise TunerError(
                "qubit_pulse_style='arb' conflicts with populated flat-top field(s) %s. "
                "QM-Team pulse programs may use those fields to emit a flat-top anyway, "
                "so the physical waveform is ambiguous. Set both flat_top_length and "
                "flattop_length to None for the supported 4-sigma Gaussian, or use a "
                "dedicated flat-top tuner." % plateau_fields)
        if q_style != "arb":
            raise TunerError(
                "this tuner calibrates a 4-sigma Gaussian ('arb') pi pulse, but "
                "qubit_pulse_style=%r. Const/flat-top gains are different physical "
                "pulses; refusing to measure one waveform and write it as another."
                % cfg.get("qubit_pulse_style"))
        r_style = str(cfg.get("read_pulse_style", "const")).lower()
        if r_style != "const":
            raise TunerError(
                "this tuner currently supports a constant readout tone, but "
                "read_pulse_style=%r. The requested style needs its own waveform and "
                "duration semantics; refusing a pulse-path mismatch."
                % cfg.get("read_pulse_style"))
        if bool(cfg.get("use_switch", False)):
            raise TunerError(
                "use_switch=True, but the autotuner sequence does not emit the external "
                "switch trigger. Refusing to calibrate through a different microwave "
                "path than the production pulse.")
        if int(cfg.get("ff_hold_gain", 0)) != 0:
            raise TunerError(
                "ff_hold_gain=%s, but this tuner does not yet reproduce the fast-flux "
                "hold waveform. Refusing to write a pi pulse measured at the wrong flux."
                % cfg.get("ff_hold_gain"))
        for qid, ff_cfg in (cfg.get("FF_Qubits", {}) or {}).items():
            if not hasattr(ff_cfg, "get"):
                continue
            active = {name: ff_cfg.get(name) for name in
                      ("Gain_Readout", "Gain_Expt", "Gain_Pulse")
                      if int(ff_cfg.get(name, 0) or 0) != 0}
            if active:
                raise TunerError(
                    "FF_Qubits[%s] requests active fast-flux gains %s, but the "
                    "autotuner's pulse programs do not emit that waveform. Refusing a "
                    "false calibration at zero flux." % (qid, active))
        if int(cfg["res_ch"]) == int(cfg["qubit_ch"]):
            raise TunerError("res_ch and qubit_ch are both %d; QICK pulse registers would "
                             "overwrite each other, so automatic calibration is unsafe."
                             % int(cfg["res_ch"]))
        if self.soccfg is not None:
            gain_safe = qubit_gain_sweep_supported(self.soccfg, cfg["qubit_ch"])
            if gain_safe is False:
                try:
                    gtype = self.soccfg["gens"][int(cfg["qubit_ch"])].get("type")
                except Exception:
                    gtype = "unknown"
                raise TunerError(
                    "qubit generator %r does not expose the standalone full-speed gain "
                    "register used by RabiProgram; a compiled gain sweep could leave "
                    "the physical amplitude fixed. Use an axis_signal_gen_v4/v5/v6 "
                    "channel or implement its packed gain/address update explicitly."
                    % gtype)
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
            "fine_freq_converged": False,
            "pi_verified": False,
            "freq_verified": False,
            "pi_fidelity_verified": False,
            "t1_verified": False,
            "readout_verified": False,
            "fixed_point": False,
            "updated": set(),
        }
        self.w["pulse_fingerprint"] = self._current_pulse_fingerprint()
        self.node_data["pulse_identity"] = {
            "initial": copy.deepcopy(self.w["pulse_fingerprint"])}
        orig = {k: cfg.get(k) for k in
                ("read_pulse_freq", "read_pulse_gain", "read_length", "res_phase",
                 "relax_delay",
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
            ss_lcb = fidelity_lower_bound(
                self.w.get("ss_fidelity", np.nan),
                self.w.get("ss_fidelity_se", np.inf),
                self.P["single_shot"].get("confidence_sigma", 1.96))
            self.w["ss_fidelity_lcb"] = float(ss_lcb)
            ss_ok = ss_lcb >= float(self.P["single_shot"].get(
                "min_fidelity_lcb", 0.80))
            t1_lo = float(self.w.get("t1_lo_us", np.nan))
            t1_hi = float(self.w.get("t1_hi_us", np.nan))
            t1_cap = max(0.5 * t1_lo, 2.0) if np.isfinite(t1_lo) else np.nan
            t1_domain_ok = t1_timing_domain_valid(self.w)
            self.w["t1_domain_ok"] = t1_domain_ok
            if self.w.get("t1_verified", False) and not t1_domain_ok:
                self._say("verdict", "WARN",
                          "the final timing violates the measured T1 domain "
                          "(read %.1f us <= cap %.1f us and relax %.1f us >= %.1f us "
                          "are required); writes are blocked"
                          % (self.w.get("read_length", np.nan), t1_cap,
                             self.w.get("relax_delay", np.nan), 5.0 * t1_hi))
            qubit_drift = any(n in set(self.drifted) for n in
                              ("spec", "rough_pi", "single_shot", "pi_fidelity",
                               "fine_pi_freq", "fine_pi_amp"))
            state_ok = bool(self.w.get("qubit_fixed_point", False) and not qubit_drift)
            pi_map_bound = self._pi_fidelity_binding_valid()
            if self.w.get("pi_fidelity_verified", False) and not pi_map_bound:
                self._say("verdict", "WARN",
                          "the no-better-neighbor pi map is not bound to the final "
                          "drive/readout coordinates; qubit and readout writes are blocked")
            pi_ok = bool(self.w.get("pi_converged", False)
                         and self.w.get("pi_verified", False)
                         and self.w.get("freq_verified", False)
                         and t1_domain_ok
                         and self.w.get("pi_fidelity_verified", False)
                         and pi_map_bound and state_ok)
            ro_ok = bool(ss_ok and self.w.get("readout_verified", False)
                         and pi_ok and self.w.get("fixed_point", False)
                         and not self.drifted)
            self.w["qubit_ok"], self.w["readout_ok"] = pi_ok, ro_ok
            success = bool(pi_ok and ro_ok)
            if pi_ok and not ro_ok:
                self._say("verdict", "OK",
                          "QUBIT calibration converged (pi %d +/- %.0f DAC) and IS "
                          "trustworthy: the signed depth hierarchy passed and a fresh "
                          "held-out population audit reproduced it (with a coherent "
                          "+/-X90 cross-check whenever that sequence retained contrast). "
                          "This uses averaged IQ and does not require single-shot "
                          "discrimination."
                          % (self.w["pi_gain"], self.w.get("pi_gain_err", float('nan'))))
                if not ss_ok:
                    rp = self.node_data.get("readout_power", {})
                    confirmed = rp.get("confirmed", []) if isinstance(rp, dict) else []
                    grid_best = max((r.get("fid", -np.inf) for r in confirmed),
                                    default=np.nan)
                    extra = (" The direct frequency x gain grid's best independently "
                             "confirmed held-out F was %.3f; no linear chi/kappa model is "
                             "being used to call this a chip limit." % grid_best
                             if np.isfinite(grid_best) else
                             " The joint readout grid did not produce a verified ceiling, "
                             "so no hardware/chip-limit diagnosis is made.")
                    reason = ("held-out fidelity LCB %.3f is below the %.3f floor "
                              "(F=%.3f +/- %.3f; separation %.2f sigma is diagnostic "
                              "only).%s"
                              % (ss_lcb,
                                 self.P["single_shot"].get("min_fidelity_lcb", 0.80),
                                 self.w.get("ss_fidelity", float('nan')),
                                 self.w.get("ss_fidelity_se", float('nan')),
                                 self.w.get("ss_sep_sigma", float('nan')), extra))
                elif not self.w.get("readout_verified", False):
                    reason = "the final readout re-measurement did not reproduce the chosen state."
                elif not self.w.get("fixed_point", False):
                    reason = ("the calibration graph did not reach a readout fixed point; "
                              "stale nodes are %s."
                              % ", ".join(n for n, _, _ in GRAPH if self.stale.get(n, False)))
                else:
                    reason = "the readout evidence mixes measurements from different times."
                self._say("verdict", "WARN", "READOUT keys are diagnostic only and will "
                          "not be written because %s" % reason)
        except TunerError as err:
            failure = str(err)
            self._say("verdict", "FAIL", failure)
        except KeyboardInterrupt:
            failure = "interrupted by user"
            self._say("verdict", "WARN", "interrupted -- partial data is still saved")

        # Saved artifacts carry the exact final waveform identity.  This gives a manual
        # QM run an objective A/B key instead of relying on similarly named gain fields.
        self.w["pulse_fingerprint"] = self._current_pulse_fingerprint()
        self.node_data.setdefault("pulse_identity", {})["final"] = copy.deepcopy(
            self.w["pulse_fingerprint"])

        tuned = {}
        keymap = [("read_pulse_freq", "read_pulse_freq"), ("read_pulse_gain", "read_pulse_gain"),
                  ("read_length", "read_length"), ("res_phase", "res_phase"),
                  ("relax_delay", "relax_delay"),
                  ("qubit_freq", "qubit_freq"), ("qubit_pi_freq", "drive_freq"),
                  ("qubit_pi_gain", "pi_gain")]
        for cfg_key, w_key in keymap:
            if cfg_key in self.w["updated"]:
                v = self.w[w_key]
                tuned[cfg_key] = int(v) if cfg_key in ("read_pulse_gain", "qubit_pi_gain") else float(v)
        readout_keys = {"read_pulse_freq", "read_pulse_gain", "read_length", "res_phase"}
        qubit_keys = {"qubit_freq", "qubit_pi_freq", "qubit_pi_gain"}
        shared_timing_keys = {"relax_delay"}
        eligible_tuned = {k: v for k, v in tuned.items()
                          if ((k in qubit_keys and self.w.get("qubit_ok", False))
                              or (k in readout_keys and self.w.get("readout_ok", False))
                              or (k in shared_timing_keys
                                  and (self.w.get("qubit_ok", False)
                                       or self.w.get("readout_ok", False))))}
        print("-" * 78)
        for line in self.report_lines:
            print("  " + line)
        print("-" * 78)
        result_label = ("SUCCESS" if success else
                        "FAILED (%s)" % failure if failure else
                        "QUBIT CONVERGED / READOUT BLOCKED"
                        if self.w.get("qubit_ok", False) else "NOT CONVERGED")
        print("RESULT: %s" % result_label)
        for k in sorted(tuned):
            was = orig.get(k)
            tag = "" if k in eligible_tuned else "  [diagnostic only]"
            print("   %-18s %-14s (was %s)%s" % (k, tuned[k], was, tag))
        for k, label in (("t1_us", "T1"), ("chi_mhz", "chi/2pi"), ("kappa_mhz", "kappa/2pi"),
                         ("ss_fidelity", "SS fidelity"), ("ss_sep_sigma", "SS separation")):
            if k in self.w and np.isfinite(self.w[k]):
                print("   %-18s %.4g%s" % (label, self.w[k],
                                           " us" if k == "t1_us" else
                                           (" MHz" if "mhz" in k else
                                            (" sigma" if "sep" in k else ""))))
        if not success:
            if eligible_tuned:
                print("   (only the evidence-eligible key group above may be written)")
            else:
                print("   (no config key is eligible to be written)")
        print("=" * 78)

        self.data.update({
            "success": success, "failure": failure, "tuned": tuned,
            "eligible_tuned": eligible_tuned,
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

    @staticmethod
    def _pair(ax, x, y, *a, **kw):
        x, y = np.asarray(x), np.asarray(y)
        if x.ndim == 1 and y.ndim == 1 and x.size == y.size and x.size:
            ax.plot(x, y, *a, **kw)

    def _plot(self, success):
        d = self.node_data
        fig, axs = plt.subplots(4, 3, figsize=(16, 14))
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
            rows = ((r.get("coarse", []) + r.get("refine", []))
                    if isinstance(r, dict) else r)
            if rows:
                sc = ax.scatter([x.get("freq", np.nan) for x in rows],
                                [x["gain"] for x in rows],
                                c=[x["fid"] for x in rows], s=18,
                                vmin=0.0, vmax=1.0)
                fig.colorbar(sc, ax=ax, label="held-out F")
                sel = r.get("selected") if isinstance(r, dict) else None
                if sel:
                    ax.plot(sel["freq"], sel["gain"], "r*", ms=10)
        ax.set_title("joint readout frequency x gain"); ax.set_xlabel("MHz")
        ax.set_ylabel("gain")
        ax = axs[1, 2]
        if "readout_len" in d:
            r = d["readout_len"]
            rows = r.get("coarse", []) if isinstance(r, dict) else r
            self._pair(ax, [x["len"] for x in rows], [x["fid"] for x in rows], "o-", ms=3)
            if isinstance(r, dict) and r.get("selected"):
                ax.plot(r["selected"]["len"], r["selected"]["fid"], "r*", ms=10)
        ax.set_title("readout length (T1=%.0f us)" % self.w.get("t1_us", np.nan))
        ax.set_xlabel("us")
        ax = axs[2, 0]
        if "t1" in d:
            self._pair(ax, d["t1"]["t"], d["t1"]["pop"], ".", ms=4)
            self._pair(ax, d["t1"]["t"], d["t1"]["fit"], "-", lw=1)
        ax.set_title("T1 = %.1f us" % self.w.get("t1_us", np.nan)); ax.set_xlabel("us")
        ax = axs[2, 1]
        ss = d.get("final_verify", {}).get("single_shot") or d.get("single_shot")
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
            rows = [(name, rd) for name, rd in d["fine_pi_amp"].items()
                    if name.startswith("M") and isinstance(rd, dict)
                    and "gains" in rd and "res" in rd]
            for name, rd in sorted(rows, key=lambda kv: int(kv[0][1:])):
                self._pair(ax, rd["gains"], rd["res"], ".-", ms=3, lw=0.8,
                           label=name)
            audits = d["fine_pi_amp"].get("audit", [])
            for j, rd in enumerate(audits):
                peaks = rd.get("peaks", []) if isinstance(rd, dict) else []
                for k, peak in enumerate(peaks):
                    if "gains" in peak:
                        self._pair(ax, peak["gains"], peak["res"], "x--", ms=3, lw=0.7,
                                   label="audit" if j == 0 and k == 0 else None)
            ax.legend(fontsize=7)
        ax.axvline(self.w.get("pi_gain", np.nan), color="r", ls="--", lw=0.8)
        ax.set_title("fine pi (signed SPE + held-out audits)"); ax.set_xlabel("gain")

        ax = axs[3, 0]
        if "pi_fidelity" in d:
            r = d["pi_fidelity"]
            rows = r.get("coarse", []) + r.get("refine", [])
            if rows:
                sc = ax.scatter([x["freq"] for x in rows], [x["gain"] for x in rows],
                                c=[x["fid"] for x in rows], s=18,
                                vmin=0.0, vmax=1.0)
                fig.colorbar(sc, ax=ax, label="held-out F")
                inc, chal = r.get("incumbent"), r.get("challenger")
                if inc:
                    ax.plot(inc["freq"], inc["gain"], "wo", mec="k", ms=7,
                            label="incumbent")
                if chal:
                    ax.plot(chal["freq"], chal["gain"], "r*", ms=10,
                            label="challenger")
                ax.legend(fontsize=7)
        ax.set_title("one-pulse qubit frequency x gain"); ax.set_xlabel("MHz")
        ax.set_ylabel("gain")

        ax = axs[3, 1]
        final_ss = d.get("final_verify", {}).get("single_shot")
        if final_ss and len(final_ss.get("xg", [])):
            bins = np.linspace(min(final_ss["xg"].min(), final_ss["xe"].min()),
                               max(final_ss["xg"].max(), final_ss["xe"].max()), 70)
            ax.hist(final_ss["xg"], bins=bins, alpha=0.6, label="|g>")
            ax.hist(final_ss["xe"], bins=bins, alpha=0.6, label="|e>")
            ax.legend(fontsize=7)
            ax.set_title("fresh final F=%.3f +/- %.3f" %
                         (final_ss["fidelity"], final_ss.get("fidelity_se", np.nan)))
        axs[3, 2].axis("off")
        axs[3, 2].text(0.0, 1.0,
                       "fidelity LCB: %.3f\npi-map bound: %s\nfixed point: %s"
                       % (self.w.get("ss_fidelity_lcb", np.nan),
                          self._pi_fidelity_binding_valid(),
                          self.w.get("fixed_point", False)),
                       va="top", family="monospace")
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
                    elif isinstance(v, list) and v and isinstance(v[0], dict):
                        # Persist scalar columns from coarse/refined/confirmed 2-D maps
                        # in HDF5 as well as in the lossless pickle.  Nested raw-shot
                        # dictionaries stay pickle-only to avoid object arrays.
                        scalar_keys = set.intersection(*[
                            {kk for kk, vv in row.items()
                             if np.isscalar(vv) and not isinstance(vv, (str, bytes))}
                            for row in v])
                        for k2 in sorted(scalar_keys):
                            try:
                                arr = np.asarray([row[k2] for row in v])
                                if arr.dtype != object:
                                    flat["%s_%s_%s" % (node, k, k2)] = arr
                            except Exception:
                                pass
            elif isinstance(nd, list) and nd and isinstance(nd[0], dict):
                for key in nd[0]:
                    try:
                        flat["%s_%s" % (node, key)] = np.array([r[key] for r in nd], dtype=float)
                    except Exception:
                        pass
        if hasattr(self, "data"):
            flat["run_metadata"] = {
                "success": self.data.get("success"),
                "failure": self.data.get("failure"),
                "qubit_ok": self.data.get("qubit_ok"),
                "readout_ok": self.data.get("readout_ok"),
                "eligible_tuned": self.data.get("eligible_tuned", {}),
                "fixed_point": self.w.get("fixed_point") if hasattr(self, "w") else None,
                "pi_converged": self.w.get("pi_converged") if hasattr(self, "w") else None,
                "pi_verified": self.w.get("pi_verified") if hasattr(self, "w") else None,
                "freq_verified": self.w.get("freq_verified") if hasattr(self, "w") else None,
                "readout_verified": self.w.get("readout_verified") if hasattr(self, "w") else None,
                "pi_audit_bound_frac": self.w.get("pi_audit_bound_frac")
                if hasattr(self, "w") else None,
                "report": self.data.get("report", []),
            }
        super().save_data(data=flat)
        # The HDF5 contains plottable arrays plus compact verdict metadata; the pickle is
        # the authoritative lossless record of nested blocks, every audit, and eligibility.
        self.pickle_data(self.data if data is None else data)
