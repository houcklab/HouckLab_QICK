import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
from scipy.signal import find_peaks, savgol_filter
import time
import datetime
from datetime import datetime
import os
import json

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
        offset_guess = np.median(ydata[:max(10, len(ydata)//10)])
        startpoint = [f0_guess, 4.1e4, 4.3e4, 1e3, offset_guess]

    if bounds is None:
        f_span = np.max(freq) - np.min(freq)
        bounds = (
            [np.min(freq), 1e2, 1e2, -1e7, -200],
            [np.max(freq), 1e9, 1e9,  1e7,  200]
        )

    popt, pcov = curve_fit(
        hanger_model_db,
        freq,
        ydata,
        p0=startpoint,
        bounds=bounds,
        maxfev=200000
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

def ramp_to(yoko, target, step=0.001, delay=0.01):
    if target > 10:
        raise ValueError("Voltage too high")
    current = float(yoko.query(":SOUR:LEV?"))
    values = np.arange(current, target, step if target > current else -step)
    for v in values:
        yoko.write(f":SOUR:LEV {v}")
        time.sleep(delay)
    yoko.write(f":SOUR:LEV {target}")  # land exactly on target

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

    bounds = (
        [-np.inf, 0.0, np.min(x), 1e-12],
        [ np.inf, np.inf, np.max(x), x_span]
    )

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

def find_two_tone_peaks(x_pts, avgamp0, min_sep_mhz=0.1,
                        prominence_fraction=0.25, smooth_window=5):
    """
    Locate up to two prominent peaks in a two-tone spectrum.

    The algorithm:
      1. Savitzky-Golay smooth to suppress single-sample noise spikes.
      2. Find peaks whose *prominence* exceeds prominence_fraction * (max-min).
         Prominence measures how much a peak rises above its surrounding
         landscape, so noise bumps riding on top of a single broad peak are
         rejected while genuine second resonances (which rise from the baseline)
         are kept.
      3. Keep the two tallest qualifying peaks, sorted by frequency.
      4. Fall back to the global maximum if no peak clears the prominence bar.

    Parameters
    ----------
    min_sep_mhz : float
        Minimum allowed separation between two returned peaks [MHz].
    prominence_fraction : float
        Prominence threshold as a fraction of the spectrum's dynamic range.
        0.25 works well for typical two-tone SNR.
    smooth_window : int
        Savitzky-Golay window length in samples (must be odd; set to 1 to skip).
    """
    x_pts   = np.asarray(x_pts,   dtype=float)
    avgamp0 = np.asarray(avgamp0, dtype=float)
    n = len(avgamp0)

    # --- trivial case -------------------------------------------------------
    if n <= 2:
        best = int(np.argmax(avgamp0))
        return {"peak_inds": [best], "peak_freqs": x_pts[[best]],
                "peak_vals": avgamp0[[best]], "peak_sep": None}

    # --- 1. Smooth ----------------------------------------------------------
    sw = max(3, int(smooth_window) | 1)          # must be odd, at least 3
    sw = min(sw, n if n % 2 == 1 else n - 1)     # cannot exceed array length
    sig = savgol_filter(avgamp0, window_length=sw, polyorder=2) if sw >= 3 else avgamp0.copy()

    # --- 2. Prominence threshold --------------------------------------------
    amp_range = sig.max() - sig.min()
    if amp_range < 1e-12:
        best = int(np.argmax(sig))
        return {"peak_inds": [best], "peak_freqs": x_pts[[best]],
                "peak_vals": avgamp0[[best]], "peak_sep": None}
    prom_thresh = prominence_fraction * amp_range

    # --- 3. Minimum distance in samples -------------------------------------
    dx = abs(float(x_pts[1] - x_pts[0])) if n > 1 else 1.0
    min_dist = max(1, int(round(min_sep_mhz / dx)))

    # --- 4. Find prominent peaks --------------------------------------------
    peak_inds, _ = find_peaks(sig, prominence=prom_thresh, distance=min_dist)

    if len(peak_inds) == 0:
        # Nothing cleared the prominence bar — return the global maximum only
        best = int(np.argmax(sig))
        return {"peak_inds": [best], "peak_freqs": x_pts[[best]],
                "peak_vals": avgamp0[[best]], "peak_sep": None}

    # --- 5. Keep the two tallest, sorted by frequency -----------------------
    if len(peak_inds) > 2:
        order = np.argsort(sig[peak_inds])[::-1]
        peak_inds = np.sort(peak_inds[order[:2]])

    if len(peak_inds) == 2:
        i0, i1 = int(peak_inds[0]), int(peak_inds[1])
        return {
            "peak_inds": [i0, i1],
            "peak_freqs": np.array([x_pts[i0], x_pts[i1]]),
            "peak_vals":  np.array([avgamp0[i0], avgamp0[i1]]),
            "peak_sep":   abs(float(x_pts[i1]) - float(x_pts[i0])),
        }
    else:
        i0 = int(peak_inds[0])
        return {
            "peak_inds": [i0],
            "peak_freqs": np.array([x_pts[i0]]),
            "peak_vals":  np.array([avgamp0[i0]]),
            "peak_sep":   None,
        }


def save_two_tone_plot(x_pts, avgi, avgq, avgamp0, peak_info, attempt_idx, save_dir, current_voltage=0):
    timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    base = os.path.join(save_dir, f"TwoTone_{attempt_idx:03d}_{timestamp}")

    plt.figure(figsize=(8, 5))
    plt.plot(x_pts, avgi, '.-', label="I")
    plt.plot(x_pts, avgq, '.-', label="Q")
    for k, idx in enumerate(peak_info["peak_inds"]):
        plt.axvline(x_pts[idx], linestyle='--', label=f"Peak {k+1}: {x_pts[idx]:.6f} MHz")
    plt.xlabel("Qubit Frequency (MHz)")
    plt.ylabel("a.u.")
    plt.title(f"Two-tone IQ, V={current_voltage:.6f} V")
    plt.legend()
    plt.tight_layout()
    plt.savefig(base + "_IQ.png", dpi=300, bbox_inches="tight")
    plt.close()

    plt.figure(figsize=(8, 5))
    plt.plot(x_pts, avgamp0, '.-', label="|I+iQ|^2")
    for k, idx in enumerate(peak_info["peak_inds"]):
        plt.axvline(x_pts[idx], linestyle='--', label=f"Peak {k+1}: {x_pts[idx]:.6f} MHz")
        plt.plot(x_pts[idx], avgamp0[idx], 'o')
    plt.xlabel("Qubit Frequency (MHz)")
    plt.ylabel("a.u.")
    sep_txt = "None" if peak_info["peak_sep"] is None else f"{peak_info['peak_sep']:.6f} MHz"
    plt.title(f"Two-tone amplitude, V={current_voltage:.6f} V, sep={sep_txt}")
    plt.legend()
    plt.tight_layout()
    plt.savefig(base + "_amp.png", dpi=300, bbox_inches="tight")
    plt.close()

    return base


def choose_next_voltage(current_v, dv, vmin, vmax, direction):
    proposed = current_v + direction * dv

    if proposed > vmax:
        direction = -1
        proposed = current_v + direction * dv

    if proposed < vmin:
        direction = +1
        proposed = current_v + direction * dv

    proposed = min(max(proposed, vmin), vmax)
    return proposed, direction

