"""Curve-fit models and fitters: hanger transmission, Lorentzian features, Rabi cosine."""

import numpy as np
from scipy.optimize import curve_fit


def hanger_model_db(f, f0, Qtot, Qext, asym, offset):
    """Hanger |S21| in dB (MATLAB-style model): f, f0 in the same units; Qtot, Qext; asymmetry
    ``asym``; vertical ``offset`` in dB."""
    numerator = (Qtot / Qext) - 2j * Qtot * asym / (f0 * 2 * np.pi)
    denominator = 1 + 2j * Qtot * (f - f0) / f0
    s21 = 1 - numerator / denominator
    return 20 * np.log10(np.abs(s21)) + offset


def fit_hanger_transmission(freq, amp_linear=None, amp_db=None, startpoint=None, bounds=None):
    """Fit hanger_model_db to ``amp_linear`` (converted to dB) or ``amp_db``.
    Returns dict: popt, perr, pcov, model, Qint (= |1/(1/Qtot - 1/Qext)|)."""
    freq = np.asarray(freq)

    if amp_db is None:
        if amp_linear is None:
            raise ValueError("Provide either amp_linear or amp_db.")
        ydata = 20 * np.log10(np.asarray(amp_linear))
    else:
        ydata = np.asarray(amp_db)

    idx_min = np.argmin(ydata)
    f0_guess = freq[idx_min]

    if startpoint is None:
        offset_guess = np.median(ydata[: max(10, len(ydata) // 10)])
        startpoint = [f0_guess, 4.1e4, 4.3e4, 1e3, offset_guess]

    if bounds is None:
        bounds = ([np.min(freq), 1e2, 1e2, -1e7, -200], [np.max(freq), 1e9, 1e9, 1e7, 200])

    popt, pcov = curve_fit(
        hanger_model_db, freq, ydata, p0=startpoint, bounds=bounds, maxfev=200000
    )

    perr = np.sqrt(np.diag(pcov))

    f0_fit, Qtot_fit, Qext_fit, asym_fit, offset_fit = popt

    denom = (1.0 / Qtot_fit) - (1.0 / Qext_fit)
    Qint_fit = np.abs(1.0 / denom) if denom != 0 else np.inf

    return {
        "popt": popt,
        "perr": perr,
        "pcov": pcov,
        "model": hanger_model_db,
        "Qint": Qint_fit,
    }


def lorentzian_dip(f, y0, A, f0, gamma):
    return y0 - A / (1.0 + ((f - f0) / gamma) ** 2)


def lorentzian_peak(f, y0, A, f0, gamma):
    return y0 + A / (1.0 + ((f - f0) / gamma) ** 2)


def fit_lorentzian_feature(x, y, fit_dip=True):
    """Fit lorentzian_dip / lorentzian_peak over the whole trace; returns popt, pcov, perr,
    yfit, rss, model. Raises if curve_fit fails."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    y_max = np.max(y)
    y_min = np.min(y)
    x_span = np.max(x) - np.min(x)

    if fit_dip:
        idx0 = np.argmin(y)
        y0_guess = np.median(y)
        A_guess = max(y0_guess - y_min, 1e-12)
    else:
        idx0 = np.argmax(y)
        y0_guess = np.median(y)
        A_guess = max(y_max - y0_guess, 1e-12)

    f0_guess = x[idx0]
    gamma_guess = max(x_span / 20.0, 1e-6)

    model = lorentzian_dip if fit_dip else lorentzian_peak
    p0 = [y0_guess, A_guess, f0_guess, gamma_guess]

    bounds = ([-np.inf, 0.0, np.min(x), 1e-12], [np.inf, np.inf, np.max(x), x_span])

    popt, pcov = curve_fit(model, x, y, p0=p0, bounds=bounds, maxfev=50000)
    perr = np.sqrt(np.diag(pcov))
    yfit = model(x, *popt)

    residuals = y - yfit
    rss = np.sum(residuals**2)

    return {
        "popt": popt,
        "pcov": pcov,
        "perr": perr,
        "yfit": yfit,
        "rss": rss,
        "model": model,
    }


def estimate_noise_floor(y):
    """Robust baseline and noise sigma of a 1-D trace.

    Uses the median as the baseline and the median-absolute-deviation (MAD)
    scaled to a Gaussian sigma. Unlike (max - min), this is insensitive to a
    handful of tall qubit peaks or single-sample spikes, so it gives a stable
    noise estimate to threshold against.

    Returns
    -------
    (baseline, sigma) : tuple of float
    """
    y = np.asarray(y, dtype=float)
    baseline = float(np.median(y))
    mad = float(np.median(np.abs(y - baseline)))
    sigma = 1.4826 * mad  # MAD -> Gaussian-equivalent std
    if not np.isfinite(sigma) or sigma <= 0:
        sigma = float(np.std(y))
        if not np.isfinite(sigma) or sigma <= 0:
            sigma = 1e-12
    return baseline, sigma


def cos_func(x, y0, A, P, phi):
    return y0 + A * np.cos(2 * np.pi * x / P + phi)


RABI_FLAG_PHASE = 1  # |phi mod pi| > 0.3 rad: the trace does not start at an extremum
RABI_FLAG_PI_OUT_OF_RANGE = 2  # P/2 outside the swept gain range
RABI_FLAG_UNDERSAMPLED = 4  # fewer than 0.75 periods in the sweep


def _rabi_period_seed_fft(x, y, pad=16):
    """Period at the peak of the zero-padded rFFT of ``y - mean`` (DC bin zeroed); None if
    undefined. A non-uniform grid is resampled onto a uniform one of the same length."""
    n = x.size
    dx = (x[-1] - x[0]) / (n - 1)
    xu = x[0] + dx * np.arange(n)
    yu = np.interp(xu, x, y) - np.mean(y)
    n_fft = int(2 ** np.ceil(np.log2(pad * n)))
    spec = np.abs(np.fft.rfft(yu, n_fft))
    spec[0] = 0.0
    k = int(np.argmax(spec))
    if k == 0 or spec[k] == 0:
        return None
    return 1.0 / np.fft.rfftfreq(n_fft, d=dx)[k]


def fit_rabi_cosine(x, y):
    """Cosine fit ``y0 + A cos(2 pi x / P + phi)`` for amplitude Rabi; ``pi_gain = P / 2``,
    ``dpi_gain = dP / 2``. Two period seeds (zero-padded FFT peak, and the gain span) times
    two signs of A, phi = 0; the lowest-residual fit wins. P is bounded below by 2 median
    grid steps (Nyquist), so an aliased short period cannot win on residual. Raises
    RuntimeError on flat or too-short data; the quality checks never raise: ``flags`` (list
    of str) and ``flag_code`` (bitmask of the RABI_FLAG_* constants) report them. See
    docs/experiments/amplitude_rabi.md."""
    x_in = np.asarray(x, dtype=float).ravel()
    y = np.asarray(y, dtype=float).ravel()
    good = np.isfinite(x_in) & np.isfinite(y)
    order = np.argsort(x_in[good])
    x, y = x_in[good][order], y[good][order]
    if x.size < 5 or x[-1] <= x[0]:
        raise RuntimeError("Rabi fit needs at least 5 distinct gain points.")
    x_min, x_max = float(x[0]), float(x[-1])
    x_span = x_max - x_min
    y0_guess = float(np.mean(y))
    A_guess = 0.5 * float(np.max(y) - np.min(y))
    if A_guess == 0:
        raise RuntimeError("Flat Rabi data.")

    # Nyquist floor on P: a period shorter than 2 grid steps is an alias of a longer one with
    # the same residual (the -A start can land on it), so it is excluded from the fit.
    P_min = 2.0 * float(np.median(np.diff(np.unique(x))))
    seeds = [max(x_span, 1.0)]
    p_fft = _rabi_period_seed_fft(x, y)
    if p_fft is not None:
        seeds.append(p_fft)
    seeds = [max(P_guess, 1.01 * P_min) for P_guess in seeds]

    bounds = ([-np.inf, -np.inf, P_min, -4 * np.pi], [np.inf, np.inf, np.inf, 4 * np.pi])
    best = None
    for P_guess in seeds:
        for A_sign in (1.0, -1.0):
            p0 = [y0_guess, A_sign * A_guess, P_guess, 0.0]
            try:
                popt, pcov = curve_fit(cos_func, x, y, p0=p0, bounds=bounds, maxfev=50000)
            except (RuntimeError, ValueError):
                continue
            sse = float(np.sum((y - cos_func(x, *popt)) ** 2))
            if best is None or sse < best[0]:
                best = (sse, popt, pcov)
    if best is None:
        raise RuntimeError("All Rabi cosine fits failed.")
    _, popt, pcov = best
    perr = np.sqrt(np.diag(pcov))

    y0_fit, A_fit, P_fit, phi_fit = popt
    dy0_fit, dA_fit, dP_fit, dphi_fit = perr
    pi_gain = P_fit / 2.0
    n_periods = x_span / P_fit

    flags, flag_code = [], 0
    phi_mod = (phi_fit + np.pi / 2) % np.pi - np.pi / 2  # phi wrapped modulo pi
    if abs(phi_mod) > 0.3:
        flag_code |= RABI_FLAG_PHASE
        flags.append(f"phase {phi_fit:.2f} rad is {phi_mod:+.2f} rad from 0 or pi")
    if not x_min <= pi_gain <= x_max:
        flag_code |= RABI_FLAG_PI_OUT_OF_RANGE
        flags.append(f"pi gain {pi_gain:.4g} outside the sweep [{x_min:.4g}, {x_max:.4g}]")
    if n_periods < 0.75:
        flag_code |= RABI_FLAG_UNDERSAMPLED
        flags.append(f"only {n_periods:.2f} periods in the sweep (< 0.75)")

    return {
        "popt": popt,
        "perr": perr,
        "yfit": cos_func(x_in, *popt),
        "y0": y0_fit,
        "A": A_fit,
        "P": P_fit,
        "phi": phi_fit,
        "dy0": dy0_fit,
        "dA": dA_fit,
        "dP": dP_fit,
        "dphi": dphi_fit,
        "pi_gain": pi_gain,
        "dpi_gain": dP_fit / 2.0,
        "n_periods": n_periods,
        "flags": flags,
        "flag_code": flag_code,
    }


def exp_decay(x, a, T1, c):
    return a * np.exp(-1 * x / T1) + c


def fit_exp_decay(x_pts, y):
    """Single-exponential fit for T1 / T2E; returns (curve at x_pts, |T|, sigma_T).
    T start value: x where y is closest to a/2.6 + c (docs/experiments/t1.md)."""
    a_guess = y[0] - y[-1]
    b_guess = y[-1]
    approx_t1_val = a_guess / 2.6 + b_guess
    index_t1_guess = np.argmin(np.abs(y - approx_t1_val))
    t1_guess = x_pts[index_t1_guess]
    guess = [a_guess, t1_guess, b_guess]
    pOpt, pCov = curve_fit(exp_decay, x_pts, y, p0=guess)
    perr = np.sqrt(np.diag(pCov))

    T1_fit = exp_decay(x_pts, *pOpt)

    T1_est = np.abs(pOpt[1])
    T1_err = perr[1]
    return T1_fit, T1_est, T1_err
