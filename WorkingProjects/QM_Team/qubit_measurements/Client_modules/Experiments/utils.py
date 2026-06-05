import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
from scipy.signal import find_peaks, savgol_filter
import time
import datetime
from datetime import datetime
import os
import json

def project_iq_signal(avgi, avgq):
    """Project complex IQ data onto its signal-bearing axis for peak finding.

    Two-tone spec frequently lands almost the entire qubit response in one
    quadrature, sitting on top of a large constant offset in the other. Taking
    |I + iQ| (or its square) then buries the feature: the magnitude is dominated
    by the big, noisy background quadrature, so peak-finding and Lorentzian fits
    lock onto background noise spikes instead of the qubit (see e.g. the
    2026-06-02 Q6 QubitSpecFF traces, where the real feature in I at ~3054 MHz
    was missed in favour of Q-noise spikes at 3038/3069 MHz).

    This removes the off-resonant background and rotates the deviation onto its
    principal axis, returning a real-valued trace in which the qubit feature
    appears as a positive peak rising from a ~0 baseline.

    Parameters
    ----------
    avgi, avgq : array_like
        Real and imaginary readout quadratures (1-D, same length).

    Returns
    -------
    np.ndarray
        Real-valued, background-subtracted, principal-axis-projected trace,
        oriented so the dominant excursion is positive.
    """
    avgi = np.asarray(avgi, dtype=float)
    avgq = np.asarray(avgq, dtype=float)
    sig = avgi + 1j * avgq

    # Off-resonant background: most points are off-resonance, so the per-quadrature
    # median is a robust estimate of the constant complex offset.
    bg = np.median(sig.real) + 1j * np.median(sig.imag)
    dev = sig - bg

    # Principal axis of the deviation. sum(dev**2) has argument 2*theta, where
    # theta is the axis the signal varies along; half its angle recovers theta
    # (and resolves the 180-degree fold). Projecting onto exp(-i*theta) puts the
    # variation into the real part.
    if np.allclose(dev, 0):
        return np.zeros_like(avgi)
    ang = 0.5 * np.angle(np.sum(dev ** 2))
    proj = (dev * np.exp(-1j * ang)).real

    # Orient so the dominant excursion is a positive peak (peak-finding/Lorentzian
    # fitting expect maxima rising from the baseline).
    if abs(proj.min()) > abs(proj.max()):
        proj = -proj
    return proj


def choose_two_tone_freqs_from_lorentz_or_peaks(data_spec, min_sep_mhz=0.1):
    x_pts = np.asarray(data_spec["data"]["x_pts"], dtype=float)
    avgi = np.asarray(data_spec["data"]["avgi"][0][0], dtype=float)
    avgq = np.asarray(data_spec["data"]["avgq"][0][0], dtype=float)
    # Rotate onto the signal-bearing axis instead of taking the raw magnitude,
    # so the fallback peak search sees the qubit rather than background noise.
    avgamp0 = project_iq_signal(avgi, avgq)

    peak_info = find_two_tone_peaks(x_pts, avgamp0, min_sep_mhz=min_sep_mhz)
    peak_freqs = np.array(peak_info["peak_freqs"], dtype=float) if peak_info["peak_freqs"] is not None else np.array([])

    lorentz_centers = np.array(
        data_spec["data"].get("lorentz_centers", []),
        dtype=float
    )
    lorentz_centers = lorentz_centers[np.isfinite(lorentz_centers)]

    if len(lorentz_centers) >= 2:
        chosen_freqs = np.sort(lorentz_centers[:2])
        source = "two_lorentzian_centers"

    elif len(lorentz_centers) == 1 and len(peak_freqs) >= 1:
        lc = float(lorentz_centers[0])
        other_peaks = [p for p in peak_freqs if abs(p - lc) >= min_sep_mhz]

        if len(other_peaks) == 0:
            other_peaks = [p for p in peak_freqs if abs(p - lc) > 1e-9]

        if len(other_peaks) >= 1:
            chosen_freqs = np.sort([lc, float(other_peaks[0])])
            source = "one_lorentzian_center_plus_peak"
        else:
            chosen_freqs = np.array([lc])
            source = "one_lorentzian_only"

    else:
        chosen_freqs = np.sort(peak_freqs[:2])
        source = "two_highest_peaks"

    if len(chosen_freqs) >= 2:
        peak_sep = float(abs(chosen_freqs[-1] - chosen_freqs[0]))
    else:
        peak_sep = None

    return {
        "freqs": chosen_freqs,
        "peak_sep": peak_sep,
        "source": source,
        "peak_info_raw": peak_info,
    }

def classify_and_average_iq(raw_i, raw_q, g_center, e_center, average_n_shots=25):
    """
    Projects IQ shots onto the calibrated ground/excited axis.

    Returns:
      binary_states: 0 or 1 per shot
      excited_avg: averaged excited population in groups of average_n_shots
      elapsed_idx_avg: group index for plotting
      scores: raw projection scores
      threshold_score: decision threshold
    """

    iq = np.column_stack([raw_i, raw_q])

    g_center = np.asarray(g_center, dtype=float)
    e_center = np.asarray(e_center, dtype=float)

    normal = e_center - g_center
    midpoint = 0.5 * (g_center + e_center)

    # Projection coordinate along g -> e axis
    scores = (iq - midpoint) @ normal

    # By construction, scores > 0 is closer to excited center
    binary_states = (scores > 0).astype(int)

    average_n_shots = max(1, int(average_n_shots))

    n_full = len(binary_states) // average_n_shots
    if n_full > 0:
        trimmed = binary_states[:n_full * average_n_shots]
        excited_avg = trimmed.reshape(n_full, average_n_shots).mean(axis=1)
        elapsed_idx_avg = np.arange(n_full)
    else:
        excited_avg = np.array([np.mean(binary_states)])
        elapsed_idx_avg = np.array([0])

    return {
        "binary_states": binary_states,
        "excited_avg": excited_avg,
        "elapsed_idx_avg": elapsed_idx_avg,
        "scores": scores,
        "normal": normal,
        "midpoint": midpoint,
    }

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


def _refine_peak_lorentzian(x_pts, y, idx, fit_window_mhz):
    """Lorentzian-refine a single peak near sample ``idx``.

    Fits a positive Lorentzian to the data within +/- fit_window_mhz of the bin
    peak (widened to >= 5 samples if the window is too narrow). Returns a dict
    with the sub-bin centre ``freq``, ``fwhm``, and the fitted curve
    (``x_fit`` / ``y_fit``) for plotting, or None if the fit fails or runs away
    outside the fit window.
    """
    x_pts = np.asarray(x_pts, dtype=float)
    y = np.asarray(y, dtype=float)
    n = x_pts.size
    f_peak = float(x_pts[idx])

    mask = np.abs(x_pts - f_peak) <= fit_window_mhz
    if np.count_nonzero(mask) < 5:
        lo = max(0, idx - 3)
        hi = min(n, idx + 4)
        mask = np.zeros(n, dtype=bool)
        mask[lo:hi] = True

    xx = x_pts[mask]
    yy = y[mask]
    if xx.size < 4:
        return None

    try:
        res = fit_lorentzian_feature(xx, yy, fit_dip=False)
        f0 = float(res["popt"][2])
        gamma = float(res["popt"][3])
        if not (xx.min() <= f0 <= xx.max()):
            return None
        x_fit = np.linspace(float(xx.min()), float(xx.max()), 200)
        y_fit = lorentzian_peak(x_fit, *res["popt"])
        return {
            "freq": f0,
            "fwhm": 2.0 * abs(gamma),
            "x_fit": x_fit,
            "y_fit": y_fit,
        }
    except Exception:
        return None


def find_parity_doublet(
    x_pts,
    avgamp0,
    center_freq,
    min_sep_mhz=0.02,
    max_sep_mhz=None,
    prominence_snr=5.0,
    smooth_window=5,
    symmetry_tol_mhz=None,
    min_height_balance=0.3,
    fit_window_mhz=0.1,
    refine=True,
):
    """Locate a charge-parity doublet in a (rotated) two-tone spectrum.

    Designed for the Modified-Ramsey voltage search, where the qubit appears as
    TWO peaks (one per charge parity) sitting roughly symmetrically about the
    spec centre ``center_freq``. The algorithm:

      1. Savitzky-Golay smooth to suppress single-sample noise.
      2. Estimate the noise floor robustly (median + MAD, see
         :func:`estimate_noise_floor`) and set the peak-prominence bar at
         ``prominence_snr * sigma`` -- an ABSOLUTE, noise-referenced threshold,
         so a lone tall feature or a noise spike no longer raises the bar and
         suppresses the real second peak (the failure mode of the old
         fraction-of-dynamic-range threshold).
      3. Detect all peaks clearing that bar.
      4. Among every candidate pair, keep those that (a) are separated by
         ``[min_sep_mhz, max_sep_mhz]``, (b) have midpoint within
         ``symmetry_tol_mhz`` of ``center_freq``, and (c) are balanced in height
         (weaker >= ``min_height_balance`` * stronger). Score the survivors by
         ``combined_prominence * balance / (1 + (sym_err / symmetry_tol)^2)`` so
         the strongest, most balanced, most symmetric pair wins.
      5. If no pair qualifies, fall back to the single most-prominent peak
         (``mode="single"``) -- used by the caller's centred-calibration path.
      6. Optionally Lorentzian-refine each chosen peak for sub-bin frequencies.

    Parameters
    ----------
    x_pts : array
        Qubit frequency axis [MHz].
    avgamp0 : array
        Signal-bearing, background-subtracted trace (see project_iq_signal),
        oriented so the qubit feature is a positive peak.
    center_freq : float
        Expected centre of the doublet [MHz] (e.g. qubit_frequency_center).
    min_sep_mhz, max_sep_mhz : float
        Allowed peak separation window [MHz]. This is the RESOLUTION limit, NOT
        the parity threshold ``df`` -- keep it small; the caller compares the
        returned ``peak_sep`` against its own df requirement. ``max_sep_mhz``
        defaults to the full swept span.
    prominence_snr : float
        Peak prominence threshold in units of the noise sigma.
    smooth_window : int
        Savitzky-Golay window length in samples (odd; <3 disables smoothing).
    symmetry_tol_mhz : float or None
        Max allowed |doublet midpoint - center_freq| [MHz]. None -> half the
        swept span (lenient; tighten to enforce the symmetric-pair assumption).
    min_height_balance : float
        Minimum (weaker / stronger) peak-height ratio for an accepted pair.
    fit_window_mhz : float
        Half-width of the Lorentzian refinement window around each peak [MHz].
    refine : bool
        If True, Lorentzian-refine peak centres for sub-bin accuracy.

    Returns
    -------
    dict with keys:
        mode        : "doublet" | "single" | "none"
        lower, upper: chosen peak frequencies [MHz] (equal in single mode)
        center      : doublet midpoint, or the single peak frequency [MHz]
        peak_sep    : |upper - lower| [MHz], or None in single/none mode
        peak_inds   : nearest-bin indices of the chosen peak(s) (for plotting)
        peak_freqs  : chosen peak frequencies (refined if refine=True)
        peak_vals   : trace value at the chosen peak bins
        fit         : list of per-peak Lorentzian fit dicts (or None)
        noise_sigma : estimated noise sigma
        candidates  : list of (freq, height, prominence) for all detected peaks
    """
    x_pts = np.asarray(x_pts, dtype=float)
    y = np.asarray(avgamp0, dtype=float)
    n = y.size

    out = {
        "mode": "none",
        "lower": None,
        "upper": None,
        "center": None,
        "peak_sep": None,
        "peak_inds": [],
        "peak_freqs": np.array([]),
        "peak_vals": np.array([]),
        "fit": None,
        "noise_sigma": None,
        "candidates": [],
    }

    def _finish_single(idx):
        out["mode"] = "single"
        out["peak_inds"] = [int(idx)]
        out["peak_vals"] = y[[idx]]
        f = float(x_pts[idx])
        fit = _refine_peak_lorentzian(x_pts, y, idx, fit_window_mhz) if refine else None
        if fit is not None:
            f = fit["freq"]
            out["fit"] = [fit]
        out["lower"] = out["upper"] = out["center"] = f
        out["peak_freqs"] = np.array([f])
        return out

    if n < 3:
        if n:
            return _finish_single(int(np.argmax(y)))
        return out

    # 1. smooth
    sw = max(3, int(smooth_window) | 1)
    sw = min(sw, n if n % 2 == 1 else n - 1)
    sig = savgol_filter(y, window_length=sw, polyorder=2) if sw >= 3 else y.copy()

    # 2. noise-referenced prominence threshold
    _, sigma = estimate_noise_floor(sig)
    out["noise_sigma"] = sigma
    prom_thresh = prominence_snr * sigma

    dx = abs(float(x_pts[1] - x_pts[0]))
    span = float(x_pts.max() - x_pts.min())
    if max_sep_mhz is None:
        max_sep_mhz = span
    if symmetry_tol_mhz is None:
        symmetry_tol_mhz = 0.5 * span
    min_dist = max(1, int(round(min_sep_mhz / dx))) if dx > 0 else 1

    # 3. detect candidate peaks above the noise bar
    inds, props = find_peaks(sig, prominence=prom_thresh, distance=min_dist)
    if inds.size == 0:
        return _finish_single(int(np.argmax(sig)))

    proms = np.asarray(props["prominences"], dtype=float)
    cand = [
        (int(idx), float(x_pts[idx]), float(sig[idx]), float(pr))
        for idx, pr in zip(inds, proms)
    ]
    cand.sort(key=lambda c: c[3], reverse=True)  # most prominent first
    out["candidates"] = [(c[1], c[2], c[3]) for c in cand]

    # 4. best symmetric, balanced, prominent pair
    sym_norm = max(symmetry_tol_mhz, dx)
    best = None  # (score, lo_cand, hi_cand)
    for a in range(len(cand)):
        for b in range(a + 1, len(cand)):
            ca, cb = cand[a], cand[b]
            lo, hi = (ca, cb) if ca[1] < cb[1] else (cb, ca)
            sep = hi[1] - lo[1]
            if sep < min_sep_mhz or sep > max_sep_mhz:
                continue
            midpoint = 0.5 * (lo[1] + hi[1])
            sym_err = abs(midpoint - center_freq)
            if sym_err > symmetry_tol_mhz:
                continue
            h_lo, h_hi = lo[2], hi[2]
            denom = max(abs(h_lo), abs(h_hi))
            balance = (min(h_lo, h_hi) / denom) if denom > 0 else 0.0
            if balance < min_height_balance:
                continue
            combined_prom = lo[3] + hi[3]
            score = combined_prom * balance / (1.0 + (sym_err / sym_norm) ** 2)
            if best is None or score > best[0]:
                best = (score, lo, hi)

    if best is None:
        # No qualifying pair -> single most-prominent peak.
        return _finish_single(cand[0][0])

    _, lo, hi = best
    i_lo, i_hi = lo[0], hi[0]
    f_lo, f_hi = lo[1], hi[1]
    fits = []
    if refine:
        for idx in (i_lo, i_hi):
            fits.append(_refine_peak_lorentzian(x_pts, y, idx, fit_window_mhz))
        if fits[0] is not None:
            f_lo = fits[0]["freq"]
        if fits[1] is not None:
            f_hi = fits[1]["freq"]
        # Refinement can re-order the pair; keep lower < upper.
        if f_lo > f_hi:
            f_lo, f_hi = f_hi, f_lo
            i_lo, i_hi = i_hi, i_lo
            fits = [fits[1], fits[0]]
        out["fit"] = [f for f in fits if f is not None] or None

    out["mode"] = "doublet"
    out["peak_inds"] = [int(i_lo), int(i_hi)]
    out["peak_vals"] = np.array([y[i_lo], y[i_hi]])
    out["peak_freqs"] = np.array([f_lo, f_hi])
    out["lower"] = float(f_lo)
    out["upper"] = float(f_hi)
    out["center"] = 0.5 * (float(f_lo) + float(f_hi))
    out["peak_sep"] = abs(float(f_hi) - float(f_lo))
    return out


def save_two_tone_plot(x_pts, avgi, avgq, avgamp0, peak_info, attempt_idx, save_dir, current_voltage=0,
                       qubit_gain=None, qubit_length=None, center_freq=None, fit=None,
                       live_display=False, live_fignum=77, live_pause=0.05):
    """Save the two-tone IQ and amplitude plots; optionally live-refresh the latter.

    When ``live_display`` is True, the amplitude figure (with peak markers, the
    expected-centre line, and the Lorentzian fits) is drawn into a single
    persistent window (figure number ``live_fignum``) that is cleared and
    redrawn in place on every call and shown NON-BLOCKING via ``plt.pause``. The
    PNG is still written either way. Live display requires an interactive
    matplotlib backend (e.g. TkAgg/QtAgg); under a non-interactive backend
    (Agg) it is a harmless no-op beyond saving the file.
    """
    timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    base = os.path.join(save_dir, f"TwoTone_{attempt_idx:03d}_{timestamp}")

    # Common label identifying bias voltage and (optionally) the drive gain/length.
    label_bits = [f"V={current_voltage:.6f} V"]
    if qubit_gain is not None:
        label_bits.append(f"gain={qubit_gain}")
    if qubit_length is not None:
        label_bits.append(f"len={qubit_length} us")
    label_suffix = ", ".join(label_bits)

    plt.figure(figsize=(8, 5))
    plt.plot(x_pts, avgi, '.-', label="I")
    plt.plot(x_pts, avgq, '.-', label="Q")
    for k, idx in enumerate(peak_info["peak_inds"]):
        plt.axvline(x_pts[idx], linestyle='--', label=f"Peak {k+1}: {x_pts[idx]:.6f} MHz")
    plt.xlabel("Qubit Frequency (MHz)")
    plt.ylabel("a.u.")
    plt.title(f"Two-tone IQ, {label_suffix}")
    plt.legend()
    plt.tight_layout()
    plt.savefig(base + "_IQ.png", dpi=300, bbox_inches="tight")
    plt.close()

    # Amplitude figure (authoritative). For live display, reuse a single
    # persistent window (constant figure number) cleared and redrawn per call;
    # otherwise use a throwaway figure that is closed after saving.
    if live_display:
        # Reuse the persistent window: only pass figsize when first creating it,
        # otherwise matplotlib warns that the size argument is ignored.
        if plt.fignum_exists(live_fignum):
            fig_amp = plt.figure(num=live_fignum)
        else:
            fig_amp = plt.figure(num=live_fignum, figsize=(8, 5))
        fig_amp.clf()
    else:
        fig_amp = plt.figure(figsize=(8, 5))
    ax = fig_amp.gca()
    ax.plot(x_pts, avgamp0, '.-', label="rotated IQ projection")
    for k, idx in enumerate(peak_info["peak_inds"]):
        ax.axvline(x_pts[idx], linestyle='--', label=f"Peak {k+1}: {x_pts[idx]:.6f} MHz")
        ax.plot(x_pts[idx], avgamp0[idx], 'o')
    # Optional overlays: expected doublet centre and sub-bin Lorentzian fits.
    if center_freq is not None:
        ax.axvline(center_freq, color="k", linestyle=":", alpha=0.7,
                   label=f"center {center_freq:.6f} MHz")
    if fit:
        for fpk in fit:
            if fpk is None:
                continue
            ax.plot(fpk["x_fit"], fpk["y_fit"], '-', color="red", alpha=0.8)
            ax.axvline(fpk["freq"], color="red", linestyle="-", alpha=0.5,
                       label=f"fit {fpk['freq']:.6f} MHz")
    ax.set_xlabel("Qubit Frequency (MHz)")
    ax.set_ylabel("a.u.")
    sep_txt = "None" if peak_info["peak_sep"] is None else f"{peak_info['peak_sep']:.6f} MHz"
    ax.set_title(f"Two-tone amplitude, {label_suffix}, sep={sep_txt}")
    ax.legend()
    fig_amp.tight_layout()
    fig_amp.savefig(base + "_amp.png", dpi=300, bbox_inches="tight")
    if live_display:
        # Non-blocking refresh: process GUI events and return immediately.
        fig_amp.canvas.draw_idle()
        plt.pause(live_pause)
    else:
        plt.close(fig_amp)

    return base


def analyze_charge_dispersion(avgamp_map, x_pts, voltage_pts,
                              save_base=None, plotDisp=False):
    """
    Build a charge-dispersion curve from a two-tone charge-sweep heatmap.

    For each gate-voltage row of ``avgamp_map`` (expected to already be projected
    onto the signal-bearing IQ axis via :func:`project_iq_signal`, so the qubit
    feature is a positive peak on a ~0 baseline), locate the qubit frequency and
    return it as a function of voltage. A Lorentzian peak fit
    (:func:`fit_lorentzian_feature`) gives sub-bin centres; the per-row argmax is
    the fallback when the fit fails or lands outside the swept window.

    Parameters
    ----------
    avgamp_map : array (n_voltage, n_freq)
        Projected two-tone amplitude, one row per gate voltage.
    x_pts : array (n_freq,)
        Qubit frequency axis [MHz].
    voltage_pts : array (n_voltage,)
        Gate voltages [V].
    save_base : str or None
        Path stem. If given, writes ``save_base + 'ChargeDispersionCurve.png'``
        and ``... .npz``.
    plotDisp : bool
        Show the figure interactively (always saved when ``save_base`` is given).

    Returns
    -------
    dict with keys: voltage_V, f_argmax, f_lorentz, fwhm_MHz, f_mean,
    dispersion_pp_MHz (peak-to-peak of the fitted curve).
    """
    avgamp_map = np.asarray(avgamp_map, dtype=float)
    x_pts = np.asarray(x_pts, dtype=float).ravel()
    voltage_pts = np.asarray(voltage_pts, dtype=float).ravel()
    nv = avgamp_map.shape[0]

    f_argmax = np.full(nv, np.nan)
    f_lorentz = np.full(nv, np.nan)
    fwhm = np.full(nv, np.nan)

    for i in range(nv):
        y = avgamp_map[i]
        if not np.any(np.isfinite(y)):
            continue  # row never populated (sweep cut short)
        fa = x_pts[int(np.nanargmax(y))]
        f_argmax[i] = fa
        ff, fw = fa, np.nan
        try:
            res = fit_lorentzian_feature(x_pts, y, fit_dip=False)
            cand = float(res["popt"][2])          # f0
            if x_pts.min() <= cand <= x_pts.max():  # reject runaway fits
                ff = cand
                fw = 2.0 * abs(float(res["popt"][3]))  # FWHM = 2*gamma
        except Exception:
            pass
        f_lorentz[i] = ff
        fwhm[i] = fw

    f_mean = float(np.nanmean(f_lorentz))
    disp_pp = float(np.nanmax(f_lorentz) - np.nanmin(f_lorentz))

    # ---- two-panel figure: heatmap + overlay, and extracted curve ----
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 5))
    xs = (x_pts[1] - x_pts[0]) if x_pts.size > 1 else 1.0
    ys = (voltage_pts[1] - voltage_pts[0]) if voltage_pts.size > 1 else 1.0
    im = a1.imshow(avgamp_map, aspect="auto", origin="lower", interpolation="none",
                   extent=[x_pts[0] - xs / 2, x_pts[-1] + xs / 2,
                           (voltage_pts[0] - ys / 2) * 1e3,
                           (voltage_pts[-1] + ys / 2) * 1e3])
    a1.plot(f_lorentz, voltage_pts * 1e3, color="w", marker="o", ls="-",
            ms=5, lw=1.2, label="fitted peak")
    a1.set_xlabel("Qubit frequency (MHz)")
    a1.set_ylabel("Gate voltage (mV)")
    a1.set_title("Charge sweep (rotated IQ projection)")
    a1.legend(loc="upper right")
    fig.colorbar(im, ax=a1, label="projection (a.u.)")

    a2.plot(voltage_pts * 1e3, f_lorentz, "o-", label="Lorentzian fit")
    a2.plot(voltage_pts * 1e3, f_argmax, "s--", alpha=0.5, label="argmax")
    a2.axhline(f_mean, color="gray", ls=":", label=f"mean {f_mean:.4f} MHz")
    a2.set_xlabel("Gate voltage (mV)")
    a2.set_ylabel("Qubit frequency (MHz)")
    a2.set_title(f"Charge dispersion curve (p-p = {disp_pp*1e3:.1f} kHz)")
    a2.legend()
    fig.tight_layout()

    if save_base is not None:
        fig.savefig(save_base + "ChargeDispersionCurve.png", dpi=200, bbox_inches="tight")
        np.savez(save_base + "ChargeDispersionCurve.npz",
                 voltage_V=voltage_pts, f_argmax=f_argmax,
                 f_lorentz=f_lorentz, fwhm_MHz=fwhm)
        print(f"[analyze_charge_dispersion] saved {save_base}ChargeDispersionCurve.png/.npz")

    if plotDisp:
        plt.show(block=False)
        plt.pause(0.1)
    else:
        plt.close(fig)

    print(f"[analyze_charge_dispersion] mean f = {f_mean:.5f} MHz, "
          f"peak-to-peak dispersion (fit) = {disp_pp*1e3:.2f} kHz, "
          f"median FWHM = {np.nanmedian(fwhm)*1e3:.1f} kHz")

    return {
        "voltage_V": voltage_pts,
        "f_argmax": f_argmax,
        "f_lorentz": f_lorentz,
        "fwhm_MHz": fwhm,
        "f_mean": f_mean,
        "dispersion_pp_MHz": disp_pp,
    }


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

def cos_func(x, y0, A, P, phi):
    return y0 + A * np.cos(2 * np.pi * x / P + phi)


def fit_rabi_cosine(x, y):
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
                            [ np.inf,  np.inf, 8 * x_span,  8 * np.pi],
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


def project_iq_onto_separator(I, Q, separator):
    """
    Project (I, Q) sample arrays onto the ground -> excited axis defined by a
    single-shot calibration separator dict.

    Parameters
    ----------
    I, Q : array_like
        Sample arrays (1-D or any shape that ravels to 1-D). Must be same length.
    separator : dict
        Must contain keys "g_center" and "e_center", each a length-2 array-like
        (I, Q) coordinate. Keys "normal" and "midpoint" if present are ignored;
        they are recomputed from g_center and e_center.

    Returns
    -------
    scores : np.ndarray, shape (N,)
        Signed projection of each sample onto (e_center - g_center). Positive
        scores are closer to the excited centroid.
    binary_states : np.ndarray, shape (N,), dtype int
        1 where score > 0 (excited side), 0 otherwise.
    """
    g = np.asarray(separator["g_center"], dtype=float)
    e = np.asarray(separator["e_center"], dtype=float)
    if g.shape != (2,) or e.shape != (2,):
        raise ValueError(
            f"separator g_center and e_center must each be length-2, "
            f"got shapes {g.shape} and {e.shape}"
        )
    normal = e - g
    midpoint = 0.5 * (g + e)
    I_arr = np.ravel(np.asarray(I, dtype=float))
    Q_arr = np.ravel(np.asarray(Q, dtype=float))
    if I_arr.size != Q_arr.size:
        raise ValueError(
            f"I and Q must have the same length, got I.size={I_arr.size}, "
            f"Q.size={Q_arr.size}"
        )
    if I_arr.size == 0:
        return np.zeros(0, dtype=float), np.zeros(0, dtype=int)
    iq = np.column_stack([I_arr, Q_arr])
    scores = (iq - midpoint) @ normal
    binary_states = (scores > 0).astype(int)
    return scores, binary_states


def pick_parity_drive_freq(spec_data, which="lower"):
    """
    Pick one of the two parity-doublet peaks from a QubitSpecSliceFF-style
    spec_data dict, using the existing choose_two_tone_freqs_from_lorentz_or_peaks
    helper as the underlying peak-finder.

    Parameters
    ----------
    spec_data : dict (output of QubitSpecSliceFF.acquire or compatible)
    which     : "lower" or "higher" — which doublet peak to park at

    Returns
    -------
    dict:
      picked  : float, the chosen frequency (MHz)
      lower   : float, the lower-frequency doublet peak (MHz)
      higher  : float, the higher-frequency doublet peak (MHz)
      peak_sep_MHz : float or None, peak separation
      source  : str, provenance from choose_two_tone_freqs_from_lorentz_or_peaks
    """
    if which not in ("lower", "higher"):
        raise ValueError(f"which must be 'lower' or 'higher', got {which!r}")
    result = choose_two_tone_freqs_from_lorentz_or_peaks(spec_data)
    freqs = np.asarray(result["freqs"], dtype=float)
    if freqs.size < 2:
        raise RuntimeError(
            f"pick_parity_drive_freq: only {freqs.size} peak(s) found; "
            f"need 2 for parity doublet. Source={result['source']}"
        )
    lower = float(np.min(freqs[:2]))
    higher = float(np.max(freqs[:2]))
    picked = lower if which == "lower" else higher
    return {
        "picked": picked,
        "lower": lower,
        "higher": higher,
        "peak_sep_MHz": result.get("peak_sep"),
        "source": result.get("source"),
    }


# Keys that describe the acquisition mode/units, propagated from the first chunk
# to the stitched output so save_data persists them verbatim. Module-level so both
# chunked_acquire and modulated_strobe_acquire share the same set.
_META_KEYS = (
    "mode", "sample_period_us",
    "read_length_us", "adc_trig_offset_us", "ro_norm_cycles",
    "decimated_fs_MHz", "decimated_fs_source",
    "capture_length_us", "samples_per_capture",
    "soft_avgs", "n_captures",
)


def chunked_acquire(experiment, n_chunks, progress=False):
    """
    Run experiment.acquire() n_chunks times back-to-back and stitch results.

    Each acquire() must return a dict with keys "I", "Q", "t_us" (1-D arrays of
    equal length per chunk) and optionally "wall_clock_start" (str).

    The stitched time axis is monotonic: each subsequent chunk's t_us is shifted
    by (previous_chunk_t_us[-1] + sample_period). Inter-chunk Python+tProc gaps
    are NOT modeled in the stitched t_us; gap_indices marks where boundaries
    occur so the analysis module can avoid counting switches across them.

    Parameters
    ----------
    experiment : object with .acquire(progress=False) -> dict {I, Q, t_us, ...}
    n_chunks   : int >= 1
    progress   : bool

    Returns
    -------
    dict:
      I, Q, t_us               : concatenated arrays
      gap_indices              : list of ints, first index of each chunk after the
                                  first (length n_chunks - 1)
      chunk_wall_clock_starts  : list of str (or None) per chunk
      n_chunks                 : echoed int

    Side effect: sets ``experiment.data = {"data": stitched}`` before returning
    so a subsequent ``experiment.save_data()`` persists the full stitched record.
    Without this the inner ``acquire()`` calls leave only the final chunk in
    ``experiment.data``, and a bare ``save_data()`` would silently write just
    that last chunk. Callers may still pass the returned dict explicitly.
    """
    if n_chunks < 1:
        raise ValueError(f"n_chunks must be >= 1, got {n_chunks}")
    I_parts, Q_parts, t_parts = [], [], []
    wall_clocks = []
    gap_indices = []
    cum_offset_us = 0.0
    cum_idx = 0
    first_meta = {}
    iterator = range(n_chunks)
    if progress:
        try:
            from tqdm import tqdm
            iterator = tqdm(iterator, desc="chunked_acquire")
        except ImportError:
            pass
    for ci in iterator:
        out = experiment.acquire(progress=False)
        I_c = np.asarray(out["I"], dtype=float).ravel()
        Q_c = np.asarray(out["Q"], dtype=float).ravel()
        t_c = np.asarray(out["t_us"], dtype=float).ravel()
        if not (I_c.shape == Q_c.shape == t_c.shape):
            raise RuntimeError(
                f"chunk {ci} returned mismatched shapes: I={I_c.shape}, "
                f"Q={Q_c.shape}, t_us={t_c.shape}"
            )
        if ci == 0:
            for k in _META_KEYS:
                if k in out:
                    first_meta[k] = out[k]
        if ci > 0:
            # Stitch time: previous chunk's last + estimated sample period.
            if t_parts and t_parts[-1].size >= 2:
                sp = float(t_parts[-1][1] - t_parts[-1][0])
            else:
                # Degenerate single-sample chunk: the intra-chunk diff is
                # unavailable, so fall back to a real sample period (from chunk
                # metadata or the experiment cfg) instead of 0.0 — otherwise the
                # next chunk's first timestamp would duplicate this one and
                # break the strictly-increasing t_us guarantee (spec §6.2).
                sp = float(first_meta.get("sample_period_us", 0.0)
                           or getattr(experiment, "cfg", {}).get("sample_period_us", 0.0))
            cum_offset_us = t_parts[-1][-1] + sp
            gap_indices.append(cum_idx)
        t_shifted = t_c + cum_offset_us
        I_parts.append(I_c); Q_parts.append(Q_c); t_parts.append(t_shifted)
        wall_clocks.append(out.get("wall_clock_start", None))
        cum_idx += I_c.size

    stitched = {
        "I": np.concatenate(I_parts),
        "Q": np.concatenate(Q_parts),
        "t_us": np.concatenate(t_parts),
        "gap_indices": gap_indices,
        "chunk_wall_clock_starts": wall_clocks,
        "n_chunks": int(n_chunks),
        "wall_clock_start": wall_clocks[0] if wall_clocks else None,
    }
    stitched.update(first_meta)
    # Wire the stitched record into experiment.data so save_data() persists the
    # full trace, not the last chunk the inner acquire() left behind.
    try:
        experiment.data = {"data": stitched}
    except AttributeError:
        pass
    return stitched


def modulated_strobe_acquire(experiment, gain_schedule, reps_per_block, progress=False):
    """Run strobe acquisition in blocks, setting qubit_gain per block, and stitch.

    gain_schedule : list of gain values, one per block (e.g. [G_on, 0, G_on, 0, ...]).
    reps_per_block : reps (= time samples) per block; must satisfy avg_maxlen (rule 4).

    Returns the chunked_acquire contract plus:
      modulation_reference : per-sample 1.0 where the block gain > 0 else 0.0
      block_labels         : the gains actually applied, per block
      reps_per_block, sample_period_us, modulation_freq_hz
    """
    I_parts, Q_parts, t_parts = [], [], []
    ref_parts, gaps, wall_starts = [], [], []
    cum_idx = 0
    cum_offset_us = 0.0
    sample_period = float(experiment.cfg.get("sample_period_us", 0.0))
    first_meta = {}
    for bi, gain in enumerate(gain_schedule):
        experiment.set_qubit_gain(gain)
        data = experiment.acquire(progress=False)
        I_c = np.asarray(data["I"]).ravel()
        Q_c = np.asarray(data["Q"]).ravel()
        t_c = np.asarray(data["t_us"], dtype=float).ravel()
        if bi == 0:
            for k in _META_KEYS:
                if k in data:
                    first_meta[k] = data[k]
            sample_period = float(data.get("sample_period_us", sample_period) or sample_period)
        if bi > 0:
            gaps.append(cum_idx)
        t_parts.append(t_c + cum_offset_us)
        if t_c.size >= 2:
            cum_offset_us = t_parts[-1][-1] + (t_c[1] - t_c[0])
        else:
            cum_offset_us = t_parts[-1][-1] + sample_period
        I_parts.append(I_c)
        Q_parts.append(Q_c)
        ref_parts.append(np.full(I_c.size, 1.0 if gain > 0 else 0.0))
        wall_starts.append(data.get("wall_clock_start"))
        cum_idx += I_c.size
    stitched = {
        "I": np.concatenate(I_parts),
        "Q": np.concatenate(Q_parts),
        "t_us": np.concatenate(t_parts),
        "modulation_reference": np.concatenate(ref_parts),
        "gap_indices": gaps,
        "block_labels": list(gain_schedule),
        "chunk_wall_clock_starts": wall_starts,
        "n_chunks": len(gain_schedule),
        "reps_per_block": int(reps_per_block),
        "sample_period_us": sample_period,
        "modulation_freq_hz": (1.0 / (2.0 * reps_per_block * sample_period * 1e-6))
                              if reps_per_block > 0 and sample_period > 0 else float("nan"),
    }
    stitched.update(first_meta)
    return stitched


if __name__ == "__main__":
    # Unit tests for the helpers added by the zero-span-parity plan.
    rng = np.random.default_rng(0)

    # --- project_iq_onto_separator ----------------------------------------
    g_center = np.array([0.0, 0.0])
    e_center = np.array([10.0, 0.0])
    sep = {"g_center": g_center, "e_center": e_center}

    # Two clouds of 1000 samples each at the centers, plus tight Gaussian noise.
    I_g = rng.normal(g_center[0], 0.5, 1000); Q_g = rng.normal(g_center[1], 0.5, 1000)
    I_e = rng.normal(e_center[0], 0.5, 1000); Q_e = rng.normal(e_center[1], 0.5, 1000)
    I = np.concatenate([I_g, I_e]); Q = np.concatenate([Q_g, Q_e])
    labels_true = np.concatenate([np.zeros(1000, int), np.ones(1000, int)])

    scores, bits = project_iq_onto_separator(I, Q, sep)
    accuracy = np.mean(bits == labels_true)
    assert accuracy > 0.99, f"project_iq_onto_separator accuracy too low: {accuracy}"
    assert scores.shape == (2000,)
    assert bits.shape == (2000,)
    assert np.issubdtype(bits.dtype, np.integer)
    # Sign convention: ground cluster (first 1000 samples) projects negative,
    # excited cluster (last 1000) projects positive.
    assert scores[0] < 0, f"expected ground sample to project negative, got {scores[0]}"
    assert scores[1500] > 0, f"expected excited sample to project positive, got {scores[1500]}"

    # Empty input edge case
    scores0, bits0 = project_iq_onto_separator([], [], sep)
    assert scores0.shape == (0,)
    assert bits0.shape == (0,)

    # Bad separator shape raises
    try:
        project_iq_onto_separator([1.0], [1.0], {"g_center": [0, 0, 0], "e_center": [1, 1]})
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError on bad separator shape")

    # Mismatched I/Q lengths raise with a clear message
    try:
        project_iq_onto_separator([1.0, 2.0], [1.0], sep)
    except ValueError as ex:
        assert "same length" in str(ex), f"unexpected error message: {ex}"
    else:
        raise AssertionError("expected ValueError on mismatched I/Q lengths")

    print("utils.py project_iq_onto_separator: OK")

    # --- pick_parity_drive_freq ----------------------------------------------
    # Build a fake QubitSpecSliceFF-style spec_data with two peaks at 3050 and 3052 MHz
    x_pts = np.linspace(3045.0, 3055.0, 401)
    def _lorentz(x, x0, A, g):
        return A / (1.0 + ((x - x0) / g) ** 2)
    amp = _lorentz(x_pts, 3050.0, 1.0, 0.15) + _lorentz(x_pts, 3052.0, 1.0, 0.15)
    avgi = np.sqrt(amp)  # arbitrary, only avgamp0 = i^2 + q^2 is fit-relevant
    avgq = np.zeros_like(avgi)
    spec_data = {"data": {
        "x_pts": x_pts.tolist(),
        "avgi": [[avgi.tolist()]],
        "avgq": [[avgq.tolist()]],
        "lorentz_centers": [3050.0, 3052.0],
    }}

    picked_low = pick_parity_drive_freq(spec_data, which="lower")
    assert abs(picked_low["picked"] - 3050.0) < 0.1, picked_low
    assert abs(picked_low["lower"]  - 3050.0) < 0.1
    assert abs(picked_low["higher"] - 3052.0) < 0.1

    picked_high = pick_parity_drive_freq(spec_data, which="higher")
    assert abs(picked_high["picked"] - 3052.0) < 0.1, picked_high

    # Bad "which" raises
    try:
        pick_parity_drive_freq(spec_data, which="middle")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for which='middle'")

    print("utils.py pick_parity_drive_freq: OK")

    # --- chunked_acquire ------------------------------------------------------
    class _FakeExp:
        def __init__(self, n_per_chunk, sample_period_us=20.0):
            self.n = int(n_per_chunk)
            self.sp = float(sample_period_us)
            self.cfg = {"sample_period_us": self.sp}
            self.calls = 0

        def acquire(self, progress=False):
            self.calls += 1
            # Each chunk produces IQ ramps offset by the call index for traceability.
            I = np.arange(self.n, dtype=float) + 1000.0 * self.calls
            Q = np.arange(self.n, dtype=float) + 2000.0 * self.calls
            t = np.arange(self.n, dtype=float) * self.sp
            return {"I": I, "Q": Q, "t_us": t,
                    "wall_clock_start": f"2026-01-01T00:00:{self.calls:02d}"}

    exp = _FakeExp(n_per_chunk=1000)
    stitched = chunked_acquire(exp, n_chunks=5)
    assert stitched["I"].shape == (5000,)
    assert stitched["Q"].shape == (5000,)
    assert stitched["t_us"].shape == (5000,)
    # gap_indices marks first sample of each chunk after the first
    assert list(stitched["gap_indices"]) == [1000, 2000, 3000, 4000]
    # Time axis is monotonic
    assert np.all(np.diff(stitched["t_us"]) > 0)
    # Per-chunk wall clock timestamps are recorded
    assert len(stitched["chunk_wall_clock_starts"]) == 5
    # n_chunks == 1 case: gap_indices empty
    one = chunked_acquire(_FakeExp(n_per_chunk=100), n_chunks=1)
    assert list(one["gap_indices"]) == []

    # Degenerate single-sample chunks: t_us must stay strictly increasing (no
    # duplicate timestamp at chunk boundaries). The fallback derives the sample
    # period from experiment.cfg when the intra-chunk diff is unavailable.
    deg = chunked_acquire(_FakeExp(n_per_chunk=1, sample_period_us=20.0), n_chunks=3)
    assert deg["t_us"].shape == (3,)
    assert np.all(np.diff(deg["t_us"]) > 0), deg["t_us"]
    assert list(deg["gap_indices"]) == [1, 2]

    # chunked_acquire wires the stitched record into experiment.data so a bare
    # save_data() persists the full trace, not just the final chunk that the
    # inner acquire() calls leave behind.
    wired = _FakeExp(n_per_chunk=50)
    wired.data = {"data": None}  # would otherwise hold only the last chunk
    ws = chunked_acquire(wired, n_chunks=4)
    assert isinstance(wired.data, dict) and "data" in wired.data
    assert wired.data["data"] is ws
    assert wired.data["data"]["I"].shape == (200,)

    print("utils.py chunked_acquire: OK")

    # --- chunked_acquire propagates per-chunk metadata to stitched dict ------
    # Regression guard for Codex round-2 finding: the real chunked path must
    # carry sample_period_us, mode, read_length_us, adc_trig_offset_us, and
    # ro_norm_cycles into the stitched output so save_data sees them.
    class _MetaFakeExp:
        def __init__(self, n_per_chunk, sp_us=20.0):
            self.n = int(n_per_chunk)
            self.sp = float(sp_us)
            self.calls = 0
        def acquire(self, progress=False):
            self.calls += 1
            return {
                "I": np.arange(self.n, dtype=float),
                "Q": np.arange(self.n, dtype=float),
                "t_us": np.arange(self.n, dtype=float) * self.sp,
                "wall_clock_start": f"2026-05-16T12:00:{self.calls:02d}",
                "sample_period_us": self.sp,
                "read_length_us": 5.0,
                "adc_trig_offset_us": 0.488,
                "ro_norm_cycles": 1920.0,
                "mode": "strobe",
            }
    meta_exp = _MetaFakeExp(n_per_chunk=500)
    meta_stitched = chunked_acquire(meta_exp, n_chunks=3)
    for k, v in [("mode", "strobe"), ("sample_period_us", 20.0),
                 ("read_length_us", 5.0), ("adc_trig_offset_us", 0.488),
                 ("ro_norm_cycles", 1920.0), ("n_chunks", 3)]:
        assert meta_stitched.get(k) == v, (
            f"chunked_acquire did not propagate {k}: got {meta_stitched.get(k)}, expected {v}"
        )
    assert meta_stitched["wall_clock_start"] == "2026-05-16T12:00:01"
    print("utils.py chunked_acquire propagates per-chunk metadata: OK")

    # --- save_data persists real chunked_acquire output ----------------------
    # Stronger regression guard: drive the actual chunked_acquire helper with
    # a fake that returns realistic per-chunk metadata, then hand the stitched
    # dict to ZeroSpanParity.save_data and reload. Previously this test built
    # the stitched dict by hand, which silently sidestepped the question of
    # whether chunked_acquire itself propagates metadata.
    import tempfile, h5py, os
    from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mZeroSpanParity import ZeroSpanParity

    real_stitched = chunked_acquire(_MetaFakeExp(n_per_chunk=10), n_chunks=3)
    # Sanity: the helper returns the metadata we expect to save.
    assert real_stitched["mode"] == "strobe"
    assert real_stitched["sample_period_us"] == 20.0
    assert real_stitched["read_length_us"] == 5.0

    class _SavingDouble:
        """Mimics enough of ZeroSpanParity to exercise save_data() in-isolation."""
        save_data = ZeroSpanParity.save_data
        def __init__(self, fname, data):
            self.fname = fname
            self.data = {"data": data}

    with tempfile.TemporaryDirectory() as tmpdir:
        fname = os.path.join(tmpdir, "stitched_test.h5")
        _SavingDouble(fname, real_stitched).save_data()
        with h5py.File(fname, "r") as f:
            assert list(np.array(f["gap_indices"])) == [10, 20]
            wcs = [s.decode("utf-8") if isinstance(s, bytes) else str(s)
                   for s in np.array(f["chunk_wall_clock_starts"])]
            assert len(wcs) == 3 and all(w.startswith("2026-05-16T") for w in wcs), wcs
            assert int(f.attrs["n_chunks"]) == 3
            assert float(f.attrs["sample_period_us"]) == 20.0
            assert str(f.attrs["mode"]) == "strobe"
            assert float(f.attrs["read_length_us"]) == 5.0
            assert float(f.attrs["adc_trig_offset_us"]) == 0.488
            assert float(f.attrs["ro_norm_cycles"]) == 1920.0
    print("utils.py save_data persists real chunked_acquire metadata: OK")

    # --- Task 3: modulated_strobe_acquire ---
    class _ModFakeExp:
        def __init__(self, n_per_block, sample_period_us):
            self.cfg = {"qubit_gain": 0, "reps_per_chunk": n_per_block,
                        "reps": n_per_block, "sample_period_us": sample_period_us}
            self._n = n_per_block
            self._sp = sample_period_us
        def set_qubit_gain(self, gain):
            self.cfg["qubit_gain"] = gain
            self.cfg["reps_per_chunk"] = self._n
            self.cfg["reps"] = self._n
        def acquire(self, progress=False):
            g = self.cfg["qubit_gain"]
            I = np.full(self._n, 5.0 if g > 0 else 0.0)
            Q = np.zeros(self._n)
            t = np.arange(self._n) * self._sp
            return {"I": I, "Q": Q, "t_us": t, "mode": "strobe",
                    "sample_period_us": self._sp, "read_length_us": 5.0,
                    "wall_clock_start": "2026-01-01T00:00:00"}

    n_per, sp = 500, 20.0
    exp = _ModFakeExp(n_per, sp)
    schedule = [100, 0] * 4   # 4 periods, on=100/off=0
    acq = modulated_strobe_acquire(exp, schedule, n_per)
    assert acq["I"].shape == (n_per * len(schedule),), acq["I"].shape
    assert acq["modulation_reference"].shape == acq["I"].shape
    # reference must be 1 exactly where the on-blocks are (I==5.0)
    assert np.array_equal((acq["modulation_reference"] > 0.5), (acq["I"] > 2.5)), "ref/gain misaligned"
    assert acq["gap_indices"] == [n_per * k for k in range(1, len(schedule))], acq["gap_indices"]
    assert np.all(np.diff(acq["t_us"]) > 0), "t_us not monotonic"
    assert acq["block_labels"] == schedule, acq["block_labels"]
    # 500 reps/half-period at 20 us -> half=10 ms -> period 20 ms -> 50 Hz
    assert abs(acq["modulation_freq_hz"] - 50.0) < 1.0, acq["modulation_freq_hz"]
    print("utils.py modulated_strobe_acquire: OK")