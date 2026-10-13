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


def fit_rabi_cosine(x, y):
    """Single-start cosine fit used by the amplitude-Rabi experiments; ``pi_gain = P / 2``.
    See docs/experiments/amplitude_rabi.md for the start values."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    y0_guess = np.mean(y)
    A_guess = 0.5 * (np.max(y) - np.min(y))

    x_span = np.max(x) - np.min(x)
    P_guess = max(x_span, 1.0)

    phi_guess = 0.0

    p0 = [y0_guess, A_guess, P_guess, phi_guess]

    bounds = ([-np.inf, -np.inf, 1e-9, -4 * np.pi], [np.inf, np.inf, np.inf, 4 * np.pi])

    popt, pcov = curve_fit(cos_func, x, y, p0=p0, bounds=bounds, maxfev=50000)
    perr = np.sqrt(np.diag(pcov))

    yfit = cos_func(x, *popt)

    y0_fit, A_fit, P_fit, phi_fit = popt
    dy0_fit, dA_fit, dP_fit, dphi_fit = perr

    pi_gain = P_fit / 2.0

    return {
        "popt": popt,
        "perr": perr,
        "yfit": yfit,
        "y0": y0_fit,
        "A": A_fit,
        "P": P_fit,
        "phi": phi_fit,
        "dy0": dy0_fit,
        "dA": dA_fit,
        "dP": dP_fit,
        "dphi": dphi_fit,
        "pi_gain": pi_gain,
    }


def fit_rabi_cosine_gridsearch(x, y):
    x = np.asarray(x, dtype=float).ravel()
    y = np.asarray(y, dtype=float).ravel()

    order = np.argsort(x)
    x = x[order]
    y = y[order]

    x_span = np.max(x) - np.min(x)
    dx = np.median(np.diff(x))
    y0_guess = np.mean(y)
    A_guess = 0.5 * (np.max(y) - np.min(y))

    if A_guess == 0 or x_span <= 0:
        raise RuntimeError("Flat or invalid Rabi data.")

    # Try many initial period guesses; this is much more robust than one FFT guess.
    period_guesses = np.linspace(max(4 * dx, x_span / 8), 4 * x_span, 40)

    best = None
    for P_guess in period_guesses:
        for phi_guess in np.linspace(-np.pi, np.pi, 9):
            for A_sign in [1, -1]:
                p0 = [y0_guess, A_sign * A_guess, P_guess, phi_guess]

                try:
                    popt, pcov = curve_fit(
                        cos_func,
                        x,
                        y,
                        p0=p0,
                        bounds=(
                            [-np.inf, -np.inf, 2 * dx, -8 * np.pi],
                            [np.inf, np.inf, 8 * x_span, 8 * np.pi],
                        ),
                        maxfev=20000,
                    )

                    yfit = cos_func(x, *popt)
                    err = np.mean((y - yfit) ** 2)

                    if best is None or err < best["err"]:
                        best = {
                            "popt": popt,
                            "pcov": pcov,
                            "err": err,
                            "yfit": yfit,
                        }
                except Exception:
                    pass

    if best is None:
        raise RuntimeError("All Rabi cosine fits failed.")

    popt = best["popt"]
    pcov = best["pcov"]
    perr = np.sqrt(np.diag(pcov))

    y0_fit, A_fit, P_fit, phi_fit = popt

    x_dense = np.linspace(np.min(x), np.max(x), 5000)
    y_dense = cos_func(x_dense, *popt)

    # Pi gain = first opposite extremum relative to starting point.
    if y_dense[0] > y0_fit:
        pi_gain = x_dense[np.argmin(y_dense)]
    else:
        pi_gain = x_dense[np.argmax(y_dense)]

    return {
        "popt": popt,
        "perr": perr,
        "yfit": best["yfit"],
        "x_fit_dense": x_dense,
        "y_fit_dense": y_dense,
        "y0": y0_fit,
        "A": A_fit,
        "P": P_fit,
        "phi": phi_fit,
        "dy0": perr[0],
        "dA": perr[1],
        "dP": perr[2],
        "dphi": perr[3],
        "pi_gain": pi_gain,
        "fit_error": best["err"],
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
