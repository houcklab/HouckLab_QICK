"""Curve-fit models and fitters: hanger transmission, Lorentzian features, Rabi cosine."""

import numpy as np
from scipy.optimize import curve_fit


def hanger_model_db(f, f0, Qtot, Qext, asym, offset):
    """
    MATLAB-style hanger fit model:

    20*log10(abs(1 - (Qtot/Qext - 2j*Qtot*asym/(f0*2*pi))
                    / (1 + 2j*Qtot*(f - f0)/f0))) + offset

    Parameters
    ----------
    f : array
        Frequency axis
    f0 : float
        Resonance frequency
    Qtot : float
        Total Q
    Qext : float
        External Q
    asym : float
        Asymmetry parameter
    offset : float
        Vertical offset in dB
    """
    numerator = (Qtot / Qext) - 2j * Qtot * asym / (f0 * 2 * np.pi)
    denominator = 1 + 2j * Qtot * (f - f0) / f0
    s21 = 1 - numerator / denominator
    return 20 * np.log10(np.abs(s21)) + offset


def fit_hanger_transmission(freq, amp_linear=None, amp_db=None, startpoint=None, bounds=None):
    """
    Fit a resonator transmission dip with a MATLAB-like hanger model.

    Provide either:
      - amp_linear : linear magnitude data, or
      - amp_db     : data already in dB

    Returns
    -------
    dict with keys:
        popt, perr, pcov, model, Qint
    """
    freq = np.asarray(freq)

    if amp_db is None:
        if amp_linear is None:
            raise ValueError("Provide either amp_linear or amp_db.")
        ydata = 20 * np.log10(np.asarray(amp_linear))
    else:
        ydata = np.asarray(amp_db)

    # Initial guess from minimum point, like MATLAB
    idx_min = np.argmin(ydata)
    f0_guess = freq[idx_min]

    if startpoint is None:
        # Similar spirit to MATLAB:
        # [center 4.1e4 4.3e4 1e3 0]
        offset_guess = np.median(ydata[: max(10, len(ydata) // 10)])
        startpoint = [f0_guess, 4.1e4, 4.3e4, 1e3, offset_guess]

    if bounds is None:
        f_span = np.max(freq) - np.min(freq)
        bounds = ([np.min(freq), 1e2, 1e2, -1e7, -200], [np.max(freq), 1e9, 1e9, 1e7, 200])

    popt, pcov = curve_fit(
        hanger_model_db, freq, ydata, p0=startpoint, bounds=bounds, maxfev=200000
    )

    perr = np.sqrt(np.diag(pcov))

    f0_fit, Qtot_fit, Qext_fit, asym_fit, offset_fit = popt

    # Match MATLAB expression:
    # abs(1/(1/Qtot - 1/Qext))
    denom = (1.0 / Qtot_fit) - (1.0 / Qext_fit)
    Qint_fit = np.abs(1.0 / denom) if denom != 0 else np.inf

    return {
        "popt": popt,
        "perr": perr,
        "pcov": pcov,
        "model": hanger_model_db,
        "Qint": Qint_fit,
    }


# -------------------- local fit helpers --------------------
def lorentzian_dip(f, y0, A, f0, gamma):
    # dip: baseline - lorentzian
    return y0 - A / (1.0 + ((f - f0) / gamma) ** 2)


def lorentzian_peak(f, y0, A, f0, gamma):
    # peak: baseline + lorentzian
    return y0 + A / (1.0 + ((f - f0) / gamma) ** 2)


def fit_lorentzian_feature(x, y, fit_dip=True):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    # initial guesses
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

    # goodness-of-fit / uncertainty propagation
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
