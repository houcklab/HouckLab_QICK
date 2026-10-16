"""Two-tone spectroscopy peak finding, plotting and parity drive-frequency selection."""

import os
from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import curve_fit
from scipy.signal import find_peaks, savgol_filter

from qicklab.analysis.fitting import estimate_noise_floor, fit_lorentzian_feature, lorentzian_peak
from qicklab.analysis.iq import project_iq_signal

# Partner significance gate of choose_two_tone_freqs_from_lorentz_or_peaks: the weaker of two
# selected lines must stand at least this many per-point noise sigmas above the off-resonant
# edge baseline (spectrum_noise_floor). Operating curve: docs/experiments/two_tone_spec.md step 4.
MIN_PARTNER_SNR = 5.0


def spectrum_noise_floor(y, edge_frac=0.15):
    """(baseline, sigma) of a projected two-tone trace for the partner significance gate.

    baseline: the median of the outer ``edge_frac`` of each side, the off-resonant baseline
    project_iq_signal subtracts (so about 0 on its output); the whole-trace median when the
    trace is too short for that (same rule as project_iq_signal). The whole-trace median
    (estimate_noise_floor) is not used: the Lorentzian wings lift it in proportion to the
    line width and height (on the 2 MHz ZSP span a 200 kHz HWHM doublet at SNR 10 read
    about 5 sigma and was rejected half the time). sigma: the per-point noise,
    estimate_noise_floor's MAD sigma of the first differences divided by sqrt(2). The MAD
    of the trace itself is not used for sigma: the wings of the lines fill most bins and
    inflate it in proportion to the line height (a 100 kHz HWHM doublet split by 0.6 MHz
    reads about 4 sigma whatever its true SNR); differencing removes the smooth line shape.
    Slow baseline drift is removed too, so sigma is the point-to-point noise, not the drift.
    """
    y = np.asarray(y, dtype=float)
    n = y.size
    k = int(round(edge_frac * n))
    if k >= 3 and 2 * k < n:
        baseline = float(np.median(np.concatenate([y[:k], y[-k:]])))
    else:
        baseline = float(np.median(y))
    _, sigma_diff = estimate_noise_floor(np.diff(y))
    return baseline, sigma_diff / np.sqrt(2.0)


def spec_lorentzian(x, y0, A, x0, gamma):
    """Peak Lorentzian (HWHM gamma) as QubitSpecSliceFF evaluates it. Algebraically equal to
    fitting.lorentzian_peak but rounds differently, so the two are kept apart."""
    return y0 + A * (gamma**2 / ((x - x0) ** 2 + gamma**2))


def fit_lorentzian_near_peak(x, y, peak_x, fit_window_mhz):
    """Fit spec_lorentzian within +/- fit_window_mhz of peak_x; None unless the fit passes the
    acceptance gates (docs/experiments/two_tone_spec.md: R^2, gamma, centre, >= 6 points)."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    mask = np.abs(x - peak_x) <= fit_window_mhz
    if np.sum(mask) < 6:
        return None

    xf = x[mask]
    yf = y[mask]

    y0_guess = np.median(yf)
    A_guess = np.max(yf) - y0_guess
    gamma_guess = max((np.max(xf) - np.min(xf)) / 8, 1e-6)

    p0 = [y0_guess, A_guess, peak_x, gamma_guess]

    bounds = (
        [-np.inf, 0, np.min(xf), 1e-9],
        [np.inf, np.inf, np.max(xf), np.max(xf) - np.min(xf)],
    )

    try:
        popt, pcov = curve_fit(spec_lorentzian, xf, yf, p0=p0, bounds=bounds, maxfev=50000)

        yfit = spec_lorentzian(xf, *popt)
        ss_res = np.sum((yf - yfit) ** 2)
        ss_tot = np.sum((yf - np.mean(yf)) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan

        y0, A, x0, gamma = popt

        if not np.isfinite(r2) or r2 < 0.60:
            return None
        if gamma <= 0 or gamma >= (np.max(xf) - np.min(xf)):
            return None
        if x0 < np.min(xf) or x0 > np.max(xf):
            return None

        return {
            "popt": popt,
            "pcov": pcov,
            "x_fit": xf,
            "y_fit": yfit,
            "r2": r2,
            "center": x0,
            "gamma": gamma,
            "fwhm": 2 * gamma,
            "amplitude": A,
            "offset": y0,
        }

    except Exception:
        return None


def _merge_close_centers(centers, min_sep_mhz):
    """Sort the centres and replace every run of neighbours closer than min_sep_mhz by its
    mean: two window fits that converged on the same line count as one line."""
    centers = np.sort(np.asarray(centers, dtype=float))
    if centers.size == 0:
        return centers
    groups = [[centers[0]]]
    for c in centers[1:]:
        if c - groups[-1][-1] < min_sep_mhz:
            groups[-1].append(c)
        else:
            groups.append([c])
    return np.array([np.mean(g) for g in groups], dtype=float)


def choose_two_tone_freqs_from_lorentz_or_peaks(
    data_spec, min_sep_mhz=0.1, min_partner_snr=MIN_PARTNER_SNR
):
    """Pick the two parity-doublet frequencies from a QubitSpecSliceFF display result.

    Preference: two Lorentzian centres, else one Lorentzian centre plus a bin peak at least
    max(min_sep_mhz, fitted HWHM) away (a bin peak inside the fitted line is that line, or an
    unresolved blend, not its partner), else the two highest find_two_tone_peaks peaks.
    Lorentzian centres closer than min_sep_mhz are merged (mean) first. Two frequencies are returned only when
    they are at least min_sep_mhz apart; otherwise the result is one frequency, peak_sep
    None and source 'single_line_unresolved' (a single line, or a doublet split below
    min_sep_mhz, which this selection cannot resolve by design).

    Significance: each of two such frequencies is given the height of the projected trace at
    its nearest bin above the off-resonant edge baseline, in units of the per-point noise
    sigma (spectrum_noise_floor). If the weaker one is below min_partner_snr (None or 0 disables
    the gate) it is taken to be a noise maximum: the result is the stronger frequency alone,
    peak_sep None, source 'partner_not_significant'. ``partner_snr`` is that weaker
    height / sigma whenever two frequencies reached the gate (also when they failed it),
    else None.
    """
    x_pts = np.asarray(data_spec["data"]["x_pts"], dtype=float)
    avgi = np.asarray(data_spec["data"]["avgi"][0][0], dtype=float)
    avgq = np.asarray(data_spec["data"]["avgq"][0][0], dtype=float)
    # Projection, not |I + iQ| (docs/concepts/iq_conventions.md section 2).
    avgamp0 = project_iq_signal(avgi, avgq)

    peak_info = find_two_tone_peaks(x_pts, avgamp0, min_sep_mhz=min_sep_mhz)
    peak_freqs = (
        np.array(peak_info["peak_freqs"], dtype=float)
        if peak_info["peak_freqs"] is not None
        else np.array([])
    )
    peak_vals = np.asarray(peak_info.get("peak_vals", []), dtype=float)

    lorentz_centers = np.array(data_spec["data"].get("lorentz_centers", []), dtype=float)
    lorentz_centers = lorentz_centers[np.isfinite(lorentz_centers)]
    lorentz_centers = _merge_close_centers(lorentz_centers, min_sep_mhz)

    if len(lorentz_centers) >= 2:
        chosen_freqs = np.sort(lorentz_centers[:2])
        source = "two_lorentzian_centers"

    elif len(lorentz_centers) == 1 and len(peak_freqs) >= 1:
        lc = float(lorentz_centers[0])
        # every accepted fit belongs to this one (merged) line: its widest fitted HWHM
        gammas = np.asarray(data_spec["data"].get("lorentz_gamma", []), dtype=float)
        gammas = gammas[np.isfinite(gammas)]
        line_hwhm = float(np.max(gammas)) if gammas.size else 0.0
        other_peaks = [p for p in peak_freqs if abs(p - lc) >= max(min_sep_mhz, line_hwhm)]

        if len(other_peaks) >= 1:
            chosen_freqs = np.sort([lc, float(other_peaks[0])])
            source = "one_lorentzian_center_plus_peak"
        else:
            chosen_freqs = np.array([lc])
            source = "single_line_unresolved"

    else:
        chosen_freqs = np.sort(peak_freqs[:2])
        source = "two_highest_peaks"
        if len(chosen_freqs) >= 2 and abs(chosen_freqs[-1] - chosen_freqs[0]) < min_sep_mhz:
            # keep the taller bin peak
            chosen_freqs = peak_freqs[[int(np.argmax(peak_vals))]]

    partner_snr = None
    if len(chosen_freqs) >= 2 and abs(chosen_freqs[-1] - chosen_freqs[0]) >= min_sep_mhz:
        peak_sep = float(abs(chosen_freqs[-1] - chosen_freqs[0]))
        # partner significance: height of each line at its nearest bin over the noise floor
        baseline, sigma = spectrum_noise_floor(avgamp0)
        snrs = np.array(
            [(avgamp0[int(np.argmin(np.abs(x_pts - f)))] - baseline) / sigma for f in chosen_freqs]
        )
        partner_snr = float(np.min(snrs))
        if min_partner_snr and partner_snr < min_partner_snr:
            chosen_freqs = np.asarray(chosen_freqs[[int(np.argmax(snrs))]], dtype=float)
            peak_sep = None
            source = "partner_not_significant"
    else:
        chosen_freqs = np.asarray(chosen_freqs[:1], dtype=float)
        peak_sep = None
        source = "single_line_unresolved"

    return {
        "freqs": chosen_freqs,
        "peak_sep": peak_sep,
        "source": source,
        "partner_snr": partner_snr,
        "peak_info_raw": peak_info,
    }


def find_two_tone_peaks(x_pts, avgamp0, min_sep_mhz=0.1, prominence_fraction=0.25, smooth_window=5):
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
    x_pts = np.asarray(x_pts, dtype=float)
    avgamp0 = np.asarray(avgamp0, dtype=float)
    n = len(avgamp0)

    if n <= 2:
        best = int(np.argmax(avgamp0))
        return {
            "peak_inds": [best],
            "peak_freqs": x_pts[[best]],
            "peak_vals": avgamp0[[best]],
            "peak_sep": None,
        }

    sw = max(3, int(smooth_window) | 1)  # must be odd, at least 3
    sw = min(sw, n if n % 2 == 1 else n - 1)  # cannot exceed array length
    sig = savgol_filter(avgamp0, window_length=sw, polyorder=2) if sw >= 3 else avgamp0.copy()

    amp_range = sig.max() - sig.min()
    if amp_range < 1e-12:
        best = int(np.argmax(sig))
        return {
            "peak_inds": [best],
            "peak_freqs": x_pts[[best]],
            "peak_vals": avgamp0[[best]],
            "peak_sep": None,
        }
    prom_thresh = prominence_fraction * amp_range

    dx = abs(float(x_pts[1] - x_pts[0])) if n > 1 else 1.0
    min_dist = max(1, int(round(min_sep_mhz / dx)))

    peak_inds, _ = find_peaks(sig, prominence=prom_thresh, distance=min_dist)

    if len(peak_inds) == 0:
        best = int(np.argmax(sig))
        return {
            "peak_inds": [best],
            "peak_freqs": x_pts[[best]],
            "peak_vals": avgamp0[[best]],
            "peak_sep": None,
        }

    if len(peak_inds) > 2:
        order = np.argsort(sig[peak_inds])[::-1]
        peak_inds = np.sort(peak_inds[order[:2]])

    if len(peak_inds) == 2:
        i0, i1 = int(peak_inds[0]), int(peak_inds[1])
        return {
            "peak_inds": [i0, i1],
            "peak_freqs": np.array([x_pts[i0], x_pts[i1]]),
            "peak_vals": np.array([avgamp0[i0], avgamp0[i1]]),
            "peak_sep": abs(float(x_pts[i1]) - float(x_pts[i0])),
        }
    else:
        i0 = int(peak_inds[0])
        return {
            "peak_inds": [i0],
            "peak_freqs": np.array([x_pts[i0]]),
            "peak_vals": np.array([avgamp0[i0]]),
            "peak_sep": None,
        }


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


def save_two_tone_plot(
    x_pts,
    avgi,
    avgq,
    avgamp0,
    peak_info,
    attempt_idx,
    save_dir,
    current_voltage=0,
    qubit_gain=None,
    qubit_length=None,
    center_freq=None,
    fit=None,
    live_display=False,
    live_fignum=77,
    live_pause=0.05,
):
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

    label_bits = [f"V={current_voltage:.6f} V"]
    if qubit_gain is not None:
        label_bits.append(f"gain={qubit_gain}")
    if qubit_length is not None:
        label_bits.append(f"len={qubit_length} us")
    label_suffix = ", ".join(label_bits)

    plt.figure(figsize=(8, 5))
    plt.plot(x_pts, avgi, ".-", label="I")
    plt.plot(x_pts, avgq, ".-", label="Q")
    for k, idx in enumerate(peak_info["peak_inds"]):
        plt.axvline(x_pts[idx], linestyle="--", label=f"Peak {k + 1}: {x_pts[idx]:.6f} MHz")
    plt.xlabel("Qubit Frequency (MHz)")
    plt.ylabel("a.u.")
    plt.title(f"Two-tone IQ, {label_suffix}")
    plt.legend()
    plt.tight_layout()
    plt.savefig(base + "_IQ.png", dpi=300, bbox_inches="tight")
    plt.close()

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
    ax.plot(x_pts, avgamp0, ".-", label="rotated IQ projection")
    for k, idx in enumerate(peak_info["peak_inds"]):
        ax.axvline(x_pts[idx], linestyle="--", label=f"Peak {k + 1}: {x_pts[idx]:.6f} MHz")
        ax.plot(x_pts[idx], avgamp0[idx], "o")
    if center_freq is not None:
        ax.axvline(
            center_freq, color="k", linestyle=":", alpha=0.7, label=f"center {center_freq:.6f} MHz"
        )
    if fit:
        for fpk in fit:
            if fpk is None:
                continue
            ax.plot(fpk["x_fit"], fpk["y_fit"], "-", color="red", alpha=0.8)
            ax.axvline(
                fpk["freq"],
                color="red",
                linestyle="-",
                alpha=0.5,
                label=f"fit {fpk['freq']:.6f} MHz",
            )
    ax.set_xlabel("Qubit Frequency (MHz)")
    ax.set_ylabel("a.u.")
    sep_txt = "None" if peak_info["peak_sep"] is None else f"{peak_info['peak_sep']:.6f} MHz"
    ax.set_title(f"Two-tone amplitude, {label_suffix}, sep={sep_txt}")
    ax.legend()
    fig_amp.tight_layout()
    fig_amp.savefig(base + "_amp.png", dpi=300, bbox_inches="tight")
    if live_display:
        fig_amp.canvas.draw_idle()
        plt.pause(live_pause)
    else:
        plt.close(fig_amp)

    return base


def analyze_charge_dispersion(avgamp_map, x_pts, voltage_pts, save_base=None, plotDisp=False):
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
            cand = float(res["popt"][2])  # f0
            if x_pts.min() <= cand <= x_pts.max():  # reject runaway fits
                ff = cand
                fw = 2.0 * abs(float(res["popt"][3]))  # FWHM = 2*gamma
        except Exception:
            pass
        f_lorentz[i] = ff
        fwhm[i] = fw

    f_mean = float(np.nanmean(f_lorentz))
    disp_pp = float(np.nanmax(f_lorentz) - np.nanmin(f_lorentz))

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 5))
    xs = (x_pts[1] - x_pts[0]) if x_pts.size > 1 else 1.0
    ys = (voltage_pts[1] - voltage_pts[0]) if voltage_pts.size > 1 else 1.0
    im = a1.imshow(
        avgamp_map,
        aspect="auto",
        origin="lower",
        interpolation="none",
        extent=[
            x_pts[0] - xs / 2,
            x_pts[-1] + xs / 2,
            (voltage_pts[0] - ys / 2) * 1e3,
            (voltage_pts[-1] + ys / 2) * 1e3,
        ],
    )
    a1.plot(
        f_lorentz,
        voltage_pts * 1e3,
        color="w",
        marker="o",
        ls="-",
        ms=5,
        lw=1.2,
        label="fitted peak",
    )
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
    a2.set_title(f"Charge dispersion curve (p-p = {disp_pp * 1e3:.1f} kHz)")
    a2.legend()
    fig.tight_layout()

    if save_base is not None:
        fig.savefig(save_base + "ChargeDispersionCurve.png", dpi=200, bbox_inches="tight")
        np.savez(
            save_base + "ChargeDispersionCurve.npz",
            voltage_V=voltage_pts,
            f_argmax=f_argmax,
            f_lorentz=f_lorentz,
            fwhm_MHz=fwhm,
        )
        print(f"[analyze_charge_dispersion] saved {save_base}ChargeDispersionCurve.png/.npz")

    if plotDisp:
        plt.show(block=False)
        plt.pause(0.1)
    else:
        plt.close(fig)

    print(
        f"[analyze_charge_dispersion] mean f = {f_mean:.5f} MHz, "
        f"peak-to-peak dispersion (fit) = {disp_pp * 1e3:.2f} kHz, "
        f"median FWHM = {np.nanmedian(fwhm) * 1e3:.1f} kHz"
    )

    return {
        "voltage_V": voltage_pts,
        "f_argmax": f_argmax,
        "f_lorentz": f_lorentz,
        "fwhm_MHz": fwhm,
        "f_mean": f_mean,
        "dispersion_pp_MHz": disp_pp,
    }


def pick_parity_drive_freq(
    spec_data, which="lower", min_sep_mhz=0.1, min_partner_snr=MIN_PARTNER_SNR
):
    """
    Pick one of the two parity-doublet peaks from a QubitSpecSliceFF-style
    spec_data dict, using the existing choose_two_tone_freqs_from_lorentz_or_peaks
    helper as the underlying peak-finder.

    Parameters
    ----------
    spec_data   : dict (output of QubitSpecSliceFF.acquire or compatible)
    which       : "lower" or "higher" — which doublet peak to park at
    min_sep_mhz : float, smallest doublet splitting accepted as two lines (MHz); pass the
                  min_sep the spectroscopy display used
    min_partner_snr : float, the weaker line's height over the per-point noise must reach
                  this (None or 0: no significance gate)

    Returns
    -------
    dict:
      picked  : float, the chosen frequency (MHz)
      lower   : float, the lower-frequency doublet peak (MHz)
      higher  : float, the higher-frequency doublet peak (MHz)
      peak_sep_MHz : float, peak separation (>= min_sep_mhz)
      source  : str, provenance from choose_two_tone_freqs_from_lorentz_or_peaks
      partner_snr : float, the weaker line's height over the per-point noise sigma

    Raises RuntimeError when the selection does not return two frequencies at least
    min_sep_mhz apart (a single line, or a doublet split below min_sep_mhz: source
    "single_line_unresolved") or when the weaker of the two is below min_partner_snr
    (source "partner_not_significant": a noise maximum, typically paired with a single
    line, a blended sub-min_sep doublet or, on a noise-only trace, another noise maximum).
    Parking on a blended centre or a noise maximum would put the drive off the parity
    lines. Operating curve of the gate: docs/experiments/two_tone_spec.md, step 4.
    """
    if which not in ("lower", "higher"):
        raise ValueError(f"which must be 'lower' or 'higher', got {which!r}")
    result = choose_two_tone_freqs_from_lorentz_or_peaks(
        spec_data, min_sep_mhz=min_sep_mhz, min_partner_snr=min_partner_snr
    )
    freqs = np.asarray(result["freqs"], dtype=float)
    if freqs.size < 2:
        found = ", ".join(f"{f:.6f}" for f in freqs) or "none"
        if result["source"] == "partner_not_significant":
            why = (
                f"the second line is only {result['partner_snr']:.1f} x the per-point noise "
                f"above the baseline (min_partner_snr={min_partner_snr}), so it is taken to be "
                f"a noise maximum. Average more (reps/rounds) or raise the spec gain so both "
                f"parity lines stand clear of the noise, widen the span if the second line "
                f"may lie outside it"
            )
        else:
            why = (
                f"need two lines at least min_sep_mhz={min_sep_mhz} MHz apart; a single "
                f"line or a doublet split below min_sep cannot be parked on"
            )
        raise RuntimeError(
            f"pick_parity_drive_freq: no resolved parity doublet (source="
            f"{result['source']}, line(s) at {found} MHz): {why}. Check the spectroscopy "
            f"PNG, or set the cached parity frequencies and disable recalibration."
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
        "partner_snr": result.get("partner_snr"),
    }


# Summary of run_spec_gain_length_sweep (docs/experiments/spec_gain_length_sweep.md#analysis).
GAIN_SWEEP_MAX_LINES = 2  # columns per grid point: display selects at most two peaks
GAIN_SWEEP_MIN_SNR = 5.0  # peak height over the per-point noise for a line to be used
GAIN_SWEEP_WINDOW_FWHM = 3.0  # summary refit: window half-width target, in FWHM
GAIN_SWEEP_MIN_WINDOW_FWHM = 2.0  # refit window capped below this many FWHM: width censored
GAIN_SWEEP_BROADENING = 1.2  # recommendation: FWHM <= this x the zero-power FWHM
GAIN_SWEEP_MIN_FIT_POINTS = 3
GAIN_SWEEP_RESOLUTION_STEPS = 3.0  # FWHM_0 below this many grid steps: resolution-limited
GAIN_SWEEP_VALLEY_SIGMA = 4.0  # two peaks are two lines only if the trace dips this far between
GAIN_SWEEP_BLEND_SPLITTING = 1.0  # single line >= this x the group's doublet splitting: a blend

_POINT_SCALARS = (
    "q_length",
    "q_gain",
    "step_mhz",
    "noise_sigma",
    "lorentz_num_fits",
    "fwhm_line",
    "fwhm_line_err",
    "snr_line",
    "center_line",
    "splitting_mhz",
)
_POINT_COLUMNS = (
    "peak_freqs",
    "peak_amps",
    "snr",
    "lorentz_centers",
    "lorentz_fwhm",
    "lorentz_amplitudes",
    "lorentz_r2",
    "refit_centers",
    "refit_fwhm",
    "refit_fwhm_err",
    "refit_window_mhz",
    "refit_censored",
)
_GROUP_KEYS = (
    "length",
    "status",
    "n_points",
    "n_blended",
    "a",
    "c",
    "fwhm0",
    "fwhm0_err",
    "t2star_lower_us",
    "fourier_fwhm_mhz",
    "recommended_gain",
    "highest_unbroadened_gain",
    "splitting_min_mhz",
    "splitting_max_mhz",
)


def _padded(values, n=GAIN_SWEEP_MAX_LINES):
    out = np.full(n, np.nan)
    v = np.asarray(values if values is not None else [], dtype=float).ravel()[:n]
    out[: v.size] = v
    return out


def _diag_err(pcov, i):
    try:
        var = float(np.asarray(pcov, dtype=float)[i, i])
    except (IndexError, TypeError, ValueError):
        return np.nan
    return float(np.sqrt(var)) if np.isfinite(var) and var >= 0 else np.nan


def _adaptive_lorentz(x, y, seed, w0, cap, min_sep_mhz):
    """fit_lorentzian_near_peak with the window half-width grown to GAIN_SWEEP_WINDOW_FWHM x
    the fitted FWHM (doubled after a failed fit), never beyond ``cap``. A fit whose centre
    left the seed by more than half of max(min_sep, HWHM) is rejected (display's seed gate).
    Returns (fit, window) of the last accepted fit, or (None, nan)."""
    w = min(w0, cap)
    best = (None, np.nan)
    for _ in range(8):
        fit = fit_lorentzian_near_peak(x, y, seed, w)
        if fit is not None and abs(fit["center"] - seed) > 0.5 * max(min_sep_mhz, fit["gamma"]):
            fit = None
        if fit is not None:
            fit["fwhm_err"] = 2.0 * _diag_err(fit["pcov"], 3)
            best = (fit, w)
            target = min(GAIN_SWEEP_WINDOW_FWHM * fit["fwhm"], cap)
            if w >= target:
                break
            w = target
        else:
            if w >= cap:
                break
            w = min(2.0 * w, cap)
    return best


def _two_lorentzians(x, y0, a1, x1, g1, a2, x2, g2):
    return y0 + a1 * g1**2 / ((x - x1) ** 2 + g1**2) + a2 * g2**2 / ((x - x2) ** 2 + g2**2)


def _fit_doublet(x, y, seeds, heights, w0, cap, min_sep_mhz):
    """Joint two-Lorentzian fit of a resolved doublet (seeds ascending) on the window
    |x - midpoint| <= half-separation + w, w grown to GAIN_SWEEP_WINDOW_FWHM x the wider
    FWHM, never beyond ``cap``. None when curve_fit fails, R^2 < 0.6, or a centre leaves its
    seed by more than half of max(min_sep, HWHM). Else ([fit_lo, fit_hi], w), each fit a
    dict like fit_lorentzian_near_peak's (center, gamma, fwhm, fwhm_err, x_fit)."""
    lo, hi = float(seeds[0]), float(seeds[1])
    half, mid = 0.5 * (hi - lo), 0.5 * (lo + hi)
    g0 = max(min(0.5 * w0, 0.5 * half), 1e-6)
    gam = [g0, g0]
    w = min(w0, cap)
    best = None
    for _ in range(6):
        mask = np.abs(x - mid) <= half + w
        if np.sum(mask) < 8:
            break
        xf, yf = x[mask], y[mask]
        gmax = float(np.ptp(xf))
        p0 = [0.0, heights[0], lo, min(gam[0], gmax), heights[1], hi, min(gam[1], gmax)]
        lb = [-np.inf, 0.0, lo - half, 1e-9, 0.0, mid, 1e-9]
        ub = [np.inf, np.inf, mid, gmax, np.inf, hi + half, gmax]
        try:
            popt, pcov = curve_fit(_two_lorentzians, xf, yf, p0=p0, bounds=(lb, ub), maxfev=20000)
        except Exception:
            break
        ss_tot = np.sum((yf - np.mean(yf)) ** 2)
        r2 = 1 - np.sum((yf - _two_lorentzians(xf, *popt)) ** 2) / ss_tot if ss_tot > 0 else np.nan
        centres, gam = (popt[2], popt[5]), (popt[3], popt[6])
        if not np.isfinite(r2) or r2 < 0.60:
            break
        if any(abs(c - s) > 0.5 * max(min_sep_mhz, g) for c, s, g in zip(centres, (lo, hi), gam)):
            break
        fits = [
            {
                "center": float(popt[k]),
                "gamma": float(popt[k + 1]),
                "fwhm": 2.0 * float(popt[k + 1]),
                "fwhm_err": 2.0 * _diag_err(pcov, k + 1),
                "x_fit": xf,
            }
            for k in (2, 5)
        ]
        best = (fits, w)
        target = min(GAIN_SWEEP_WINDOW_FWHM * 2.0 * max(gam), cap)
        if w >= target:
            break
        w = target
    return best


def gain_sweep_point(data, q_length, q_gain, *, fit_window_mhz, span_mhz, min_sep_mhz):
    """One row of the gain x length summary from a displayed QubitSpecSliceFF record.

    Copies display's peaks and Lorentzians (two columns, NaN-padded), adds each peak's SNR
    (height over the edge baseline in units of the per-point noise, spectrum_noise_floor)
    and refits every peak with SNR >= GAIN_SWEEP_MIN_SNR with an adaptive window
    (_adaptive_lorentz, window capped at the half-span). Two such peaks count as a doublet
    only when the trace between them dips GAIN_SWEEP_VALLEY_SIGMA noise sigmas below the
    lower one (then both are refitted jointly, _fit_doublet); otherwise the second is a
    noise maximum on the flank of one broad line and only the taller is refitted. display's
    own window (fit_window_mhz) biases lines wider than about 2 fit_window_mhz and rejects
    wider ones, so its lorentz_fwhm is not used for the saturation fit. A refit width is
    censored when the fitted data reach less than GAIN_SWEEP_MIN_WINDOW_FWHM x FWHM beyond
    the centre (on the outer side of a doublet). ``fwhm_line`` is the narrower uncensored
    branch (``snr_line`` its SNR, ``center_line`` its refit centre), ``splitting_mhz`` the
    refit centre separation of a doublet. Reads ``data`` only. Never raises: a record without usable data gives a NaN
    row."""
    row = {k: np.nan for k in _POINT_SCALARS}
    row.update({k: np.full(GAIN_SWEEP_MAX_LINES, np.nan) for k in _POINT_COLUMNS})
    row["q_length"] = float(q_length)
    row["q_gain"] = float(q_gain)
    try:
        d = data["data"]
        x = np.asarray(d["x_pts"], dtype=float)
        y = project_iq_signal(
            np.asarray(d["avgi"][0][0], dtype=float), np.asarray(d["avgq"][0][0], dtype=float)
        )
        baseline, sigma = spectrum_noise_floor(y)
        row["step_mhz"] = float(np.median(np.abs(np.diff(x)))) if x.size > 1 else np.nan
        row["noise_sigma"] = sigma
        for key in ("lorentz_centers", "lorentz_fwhm", "lorentz_amplitudes", "lorentz_r2"):
            row[key] = _padded(d.get(key))
        row["lorentz_num_fits"] = float(d.get("lorentz_num_fits", 0))
        freqs = np.asarray(d.get("two_tone_peak_freqs", []), dtype=float).ravel()
        amps = np.asarray(d.get("two_tone_peak_amps", []), dtype=float).ravel()
        order = np.argsort(freqs)[:GAIN_SWEEP_MAX_LINES]
        freqs, amps = freqs[order], amps[order]
        snr = (amps - baseline) / sigma
        row["peak_freqs"] = _padded(freqs)
        row["peak_amps"] = _padded(amps)
        row["snr"] = _padded(snr)

        strong = [i for i in range(freqs.size) if snr[i] >= GAIN_SWEEP_MIN_SNR]
        cap = float(span_mhz) if span_mhz else 0.5 * float(np.ptp(x))
        if len(strong) == 2:
            i0, i1 = np.searchsorted(x, freqs[strong[0]]), np.searchsorted(x, freqs[strong[1]])
            valley = float(np.min(y[i0 : i1 + 1]))
            if valley >= np.min(amps[strong]) - GAIN_SWEEP_VALLEY_SIGMA * sigma:
                # a noise maximum on the flank of one broad line: refit the taller only
                strong = [strong[int(np.argmax(amps[strong]))]]
        for i in strong:
            row["refit_censored"][i] = 1.0
        if len(strong) == 2:
            res = _fit_doublet(x, y, freqs[strong], amps[strong], fit_window_mhz, cap, min_sep_mhz)
            fits = [] if res is None else list(zip(strong, res[0], [res[1]] * 2))
        else:
            fits = []
            for i in strong:
                fit, w = _adaptive_lorentz(x, y, freqs[i], fit_window_mhz, cap, min_sep_mhz)
                if fit is not None:
                    fits.append((i, fit, w))
        for i, fit, w in fits:
            xf = np.asarray(fit["x_fit"], dtype=float)
            margin = min(fit["center"] - np.min(xf), np.max(xf) - fit["center"])
            if len(fits) == 2:  # the inner flank is modelled by the joint fit
                margin = (
                    fit["center"] - np.min(xf) if i == strong[0] else np.max(xf) - fit["center"]
                )
            row["refit_centers"][i] = fit["center"]
            row["refit_fwhm"][i] = fit["fwhm"]
            row["refit_fwhm_err"][i] = fit["fwhm_err"]
            row["refit_window_mhz"][i] = w
            row["refit_censored"][i] = float(margin < GAIN_SWEEP_MIN_WINDOW_FWHM * fit["fwhm"])
        ok = [i for i in strong if row["refit_censored"][i] == 0.0]
        if ok:
            i = min(ok, key=lambda j: row["refit_fwhm"][j])
            row["fwhm_line"] = row["refit_fwhm"][i]
            row["fwhm_line_err"] = row["refit_fwhm_err"][i]
            row["snr_line"] = row["snr"][i]
            row["center_line"] = row["refit_centers"][i]
        if np.all(np.isfinite(row["refit_centers"])):
            row["splitting_mhz"] = float(abs(row["refit_centers"][1] - row["refit_centers"][0]))
    except Exception as exc:  # the summary never stops the sweep
        print(f"[gain_sweep_point] length={q_length} gain={q_gain}: no summary row ({exc!r})")
    return row


def fit_power_broadening(gains, fwhm, fwhm_err=None):
    """Saturation fit FWHM^2 = a + c gain^2 (a, c >= 0) on the finite, positive points.

    Weighted by the FWHM^2 errors 2 FWHM fwhm_err when every one is finite and positive,
    unweighted otherwise. Returns {status, n_points, a, c, fwhm0, fwhm0_err} with status
    "insufficient" (fewer than GAIN_SWEEP_MIN_FIT_POINTS points; NaN fields), "failed"
    (curve_fit raised) or "fit". fwhm0 = sqrt(a), fwhm0_err from pcov (NaN at a = 0)."""
    g = np.asarray(gains, dtype=float).ravel()
    f = np.asarray(fwhm, dtype=float).ravel()
    e = None if fwhm_err is None else np.asarray(fwhm_err, dtype=float).ravel()
    keep = np.isfinite(g) & np.isfinite(f) & (f > 0)
    out = {"status": "insufficient", "n_points": int(keep.sum()), "a": np.nan, "c": np.nan}
    out.update({"fwhm0": np.nan, "fwhm0_err": np.nan})
    if keep.sum() < GAIN_SWEEP_MIN_FIT_POINTS:
        return out
    g, f = g[keep], f[keep]
    sig = None
    if e is not None:
        e = e[keep]
        if np.all(np.isfinite(e) & (e > 0)):
            sig = 2.0 * f * e
    gmax = float(np.max(np.abs(g))) or 1.0
    u = (g / gmax) ** 2
    y = f**2
    slope0 = max(float(np.polyfit(u, y, 1)[0]), 0.0) if np.ptp(u) > 0 else 0.0
    a0 = max(float(np.min(y)) - slope0 * float(np.min(u)), 0.0)
    try:
        popt, pcov = curve_fit(
            lambda uu, a, c: a + c * uu,
            u,
            y,
            p0=[a0, slope0],
            bounds=([0.0, 0.0], [np.inf, np.inf]),
            sigma=sig,
            maxfev=20000,
        )
    except Exception:
        out["status"] = "failed"
        return out
    a, c_scaled = float(popt[0]), float(popt[1])
    fwhm0 = float(np.sqrt(a))
    out.update(
        status="fit",
        a=a,
        c=c_scaled / gmax**2,
        fwhm0=fwhm0,
        fwhm0_err=_diag_err(pcov, 0) / (2.0 * fwhm0) if fwhm0 > 0 else np.nan,
    )
    return out


def summarize_gain_length_sweep(rows, *, gauss=False, sigma_us=None):
    """Per-length saturation summary of gain_sweep_point rows.

    Groups by qubit_length (one group, length NaN, when ``gauss``: the length does not
    change a Gaussian drive). Per group: fit_power_broadening on the rows with an
    uncensored ``fwhm_line`` (SNR >= GAIN_SWEEP_MIN_SNR by construction) that is not a
    blend. A blend (point ``blended`` = 1) is a single-line row of a group with a resolved
    doublet somewhere, whose width is at least GAIN_SWEEP_BLEND_SPLITTING x the group's
    smallest splitting: at that width the doublet is no longer resolved, and one Lorentzian
    over the merged pair is about splitting + branch FWHM wide, not a branch width. Status "ok" when
    FWHM_0 exceeds GAIN_SWEEP_RESOLUTION_STEPS grid steps and the Fourier width 1/T of the
    drive (T = qubit_length, or 4 sigma for a Gaussian); then t2star_lower_us =
    1/(pi FWHM_0) (MHz -> us), a lower bound on T2*. "resolution-limited" otherwise (no T2*
    bound), "insufficient" / "failed" from the fit. Recommendation (printed and saved, never
    written back): the smallest gain whose line has SNR >= GAIN_SWEEP_MIN_SNR and FWHM <=
    GAIN_SWEEP_BROADENING x the reference width (FWHM_0 when "ok"; when
    "resolution-limited", the larger of FWHM_0 and the narrowest measured line), and the
    highest such gain (most signal without measurable broadening). Returns
    {"points": {key: array}, "groups": {key: array}, "gauss": bool}."""
    pts = {k: np.array([r[k] for r in rows], dtype=float) for k in _POINT_SCALARS}
    pts.update(
        {
            k: np.array([r[k] for r in rows], dtype=float).reshape(-1, GAIN_SWEEP_MAX_LINES)
            for k in _POINT_COLUMNS
        }
    )
    lengths = [np.nan] if gauss else sorted({float(v) for v in pts["q_length"]})
    groups = {k: [] for k in _GROUP_KEYS}
    has_line = np.isfinite(pts["fwhm_line"])
    pts["blended"] = np.where(has_line, 0.0, np.nan)
    for L in lengths:
        sel = np.ones(len(rows), bool) if gauss else pts["q_length"] == L
        split = pts["splitting_mhz"][sel]
        split = split[np.isfinite(split)]
        if split.size:
            single = sel & has_line & ~np.isfinite(pts["splitting_mhz"])
            blend = single & (pts["fwhm_line"] >= GAIN_SWEEP_BLEND_SPLITTING * float(split.min()))
            pts["blended"][blend] = 1.0
        use = sel & has_line & (pts["blended"] == 0.0)
        fit = fit_power_broadening(
            pts["q_gain"][use], pts["fwhm_line"][use], pts["fwhm_line_err"][use]
        )
        steps = pts["step_mhz"][sel]
        step = float(np.nanmedian(steps)) if np.any(np.isfinite(steps)) else np.nan
        if gauss:
            T = 4.0 * float(sigma_us) if sigma_us else np.nan
        else:
            T = L
        fourier = 1.0 / T if np.isfinite(T) and T > 0 else np.nan
        status, t2, ref = fit["status"], np.nan, np.nan
        if status == "fit":
            f0 = fit["fwhm0"]
            resolved = f0 > GAIN_SWEEP_RESOLUTION_STEPS * step and not f0 <= fourier
            if resolved:
                status, t2, ref = "ok", 1.0 / (np.pi * f0), f0
            else:
                status = "resolution-limited"
                ref = max(f0, float(np.min(pts["fwhm_line"][use])))
        rec = hi = np.nan
        if np.isfinite(ref):
            good = use & (pts["fwhm_line"] <= GAIN_SWEEP_BROADENING * ref)
            if np.any(good):
                rec = float(np.min(pts["q_gain"][good]))
                hi = float(np.max(pts["q_gain"][good]))
        values = {
            "length": L,
            "status": status,
            "n_points": fit["n_points"],
            "n_blended": float(np.sum(sel & (pts["blended"] == 1.0))),
            "a": fit["a"],
            "c": fit["c"],
            "fwhm0": fit["fwhm0"],
            "fwhm0_err": fit["fwhm0_err"],
            "t2star_lower_us": t2,
            "fourier_fwhm_mhz": fourier,
            "recommended_gain": rec,
            "highest_unbroadened_gain": hi,
            "splitting_min_mhz": float(split.min()) if split.size else np.nan,
            "splitting_max_mhz": float(split.max()) if split.size else np.nan,
        }
        for k in _GROUP_KEYS:
            groups[k].append(values[k])
    groups = {k: np.array(v, dtype=str if k == "status" else float) for k, v in groups.items()}
    return {"points": pts, "groups": groups, "gauss": bool(gauss)}


def print_gain_length_summary(summary):
    """One console line per length group of summarize_gain_length_sweep."""
    g = summary["groups"]
    if summary["gauss"]:
        print("GainLengthSweep summary: Gauss=True, all lengths pooled (the length loop repeats)")
    for i in range(len(g["status"])):
        name = "all lengths" if summary["gauss"] else f"length {g['length'][i]:g} us"
        line = f"GainLengthSweep {name}: {g['status'][i]} ({int(g['n_points'][i])} lines used"
        if g["n_blended"][i]:
            line += f", {int(g['n_blended'][i])} merged-doublet blends left out"
        line += ")"
        if np.isfinite(g["fwhm0"][i]):
            line += f", FWHM_0 = {g['fwhm0'][i]:.4f} +/- {g['fwhm0_err'][i]:.4f} MHz"
        if np.isfinite(g["t2star_lower_us"][i]):
            line += f", T2* >= {g['t2star_lower_us'][i]:.3f} us"
        if np.isfinite(g["recommended_gain"][i]):
            line += (
                f"; recommended gain {g['recommended_gain'][i]:g} (highest within "
                f"{GAIN_SWEEP_BROADENING} x FWHM_0: {g['highest_unbroadened_gain'][i]:g})"
            )
        if np.isfinite(g["splitting_min_mhz"][i]):
            line += (
                f"; doublet splitting {g['splitting_min_mhz'][i]:.4f} to "
                f"{g['splitting_max_mhz'][i]:.4f} MHz"
            )
        print(line)


def save_gain_length_summary(summary, folder, plotDisp=False):
    """Write GainLengthSweep_summary_<timestamp>.npz (point_* and group_* arrays, no pickled
    objects) and .png (FWHM and SNR vs gain per length, with the saturation fits) into
    ``folder``. Returns the npz path."""
    stem = os.path.join(
        folder, "GainLengthSweep_summary_" + datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    )
    arrays = {"point_" + k: v for k, v in summary["points"].items()}
    arrays.update({"group_" + k: v for k, v in summary["groups"].items()})
    arrays["gauss"] = np.array(summary["gauss"])
    np.savez(stem + ".npz", **arrays)

    p, g = summary["points"], summary["groups"]
    fig, (ax_w, ax_s) = plt.subplots(1, 2, figsize=(11, 4.5))
    for i in range(len(g["status"])):
        sel = np.ones(p["q_gain"].size, bool)
        label = "all lengths"
        if not summary["gauss"]:
            sel = p["q_length"] == g["length"][i]
            label = f"{g['length'][i]:g} us"
        blend = sel & (p["blended"] == 1.0)
        (h,) = ax_w.plot(p["q_gain"][sel & ~blend], p["fwhm_line"][sel & ~blend], "o", label=label)
        if np.any(blend):
            ax_w.plot(p["q_gain"][blend], p["fwhm_line"][blend], "x", color=h.get_color())
        if np.isfinite(g["a"][i]) and np.any(sel):
            gg = np.linspace(0, np.nanmax(p["q_gain"][sel]), 200)
            ax_w.plot(gg, np.sqrt(g["a"][i] + g["c"][i] * gg**2), "-", color=h.get_color())
        ax_s.plot(p["q_gain"][sel], p["snr_line"][sel], "o", color=h.get_color(), label=label)
    ax_s.axhline(GAIN_SWEEP_MIN_SNR, linestyle="--", color="gray")
    ax_w.set_xlabel("qubit_gain (DAC)")
    ax_w.set_ylabel("FWHM (MHz)")
    ax_w.set_title("FWHM^2 = FWHM_0^2 + c gain^2")
    ax_s.set_xlabel("qubit_gain (DAC)")
    ax_s.set_ylabel("SNR (peak / per-point noise)")
    ax_w.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(stem + ".png")
    if plotDisp:
        plt.show()
    plt.close(fig)
    print(f"GainLengthSweep summary saved: {stem}.npz")
    return stem + ".npz"
