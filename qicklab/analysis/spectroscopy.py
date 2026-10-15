"""Two-tone spectroscopy peak finding, plotting and parity drive-frequency selection."""

import os
from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import curve_fit
from scipy.signal import find_peaks, savgol_filter

from qicklab.analysis.fitting import fit_lorentzian_feature, lorentzian_peak
from qicklab.analysis.iq import project_iq_signal


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


def choose_two_tone_freqs_from_lorentz_or_peaks(data_spec, min_sep_mhz=0.1):
    """Pick the two parity-doublet frequencies from a QubitSpecSliceFF display result.

    Preference: two Lorentzian centres, else one Lorentzian centre plus a bin peak at least
    max(min_sep_mhz, fitted HWHM) away (a bin peak inside the fitted line is that line, or an
    unresolved blend, not its partner), else the two highest find_two_tone_peaks peaks.
    Lorentzian centres closer than min_sep_mhz are merged (mean) first. Two frequencies are returned only when
    they are at least min_sep_mhz apart; otherwise the result is one frequency, peak_sep
    None and source 'single_line_unresolved' (a single line, or a doublet split below
    min_sep_mhz, which this selection cannot resolve by design).
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

    if len(chosen_freqs) >= 2 and abs(chosen_freqs[-1] - chosen_freqs[0]) >= min_sep_mhz:
        peak_sep = float(abs(chosen_freqs[-1] - chosen_freqs[0]))
    else:
        chosen_freqs = np.asarray(chosen_freqs[:1], dtype=float)
        peak_sep = None
        source = "single_line_unresolved"

    return {
        "freqs": chosen_freqs,
        "peak_sep": peak_sep,
        "source": source,
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


def pick_parity_drive_freq(spec_data, which="lower", min_sep_mhz=0.1):
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

    Returns
    -------
    dict:
      picked  : float, the chosen frequency (MHz)
      lower   : float, the lower-frequency doublet peak (MHz)
      higher  : float, the higher-frequency doublet peak (MHz)
      peak_sep_MHz : float, peak separation (>= min_sep_mhz)
      source  : str, provenance from choose_two_tone_freqs_from_lorentz_or_peaks

    Raises RuntimeError when the selection does not return two frequencies at least
    min_sep_mhz apart (a single line, or a doublet split below min_sep_mhz): parking on a
    blended or duplicated centre would put the drive between the parity lines. Only the
    separation is checked, not significance, so the raise is reliable only at high SNR
    (line height / per-point noise >= ~15 on the ZSP grid). At lower SNR a noise maximum
    at least min_sep_mhz from the line is taken as the partner: a single line, or a
    sub-min_sep doublet fitted as one Lorentzian at its midpoint, then passes as a doublet
    (source "one_lorentzian_center_plus_peak", e.g. a 0.15 MHz doublet at HWHM 40 kHz
    raises in only ~27 % of trials at SNR 8), and on a noise-only trace two noise maxima
    pass (source "two_highest_peaks"). See docs/experiments/two_tone_spec.md, step 4.
    """
    if which not in ("lower", "higher"):
        raise ValueError(f"which must be 'lower' or 'higher', got {which!r}")
    result = choose_two_tone_freqs_from_lorentz_or_peaks(spec_data, min_sep_mhz=min_sep_mhz)
    freqs = np.asarray(result["freqs"], dtype=float)
    if freqs.size < 2:
        found = ", ".join(f"{f:.6f}" for f in freqs) or "none"
        raise RuntimeError(
            f"pick_parity_drive_freq: no resolved parity doublet (source="
            f"{result['source']}, line(s) at {found} MHz). Need two lines at least "
            f"min_sep_mhz={min_sep_mhz} MHz apart; a single line or a doublet split "
            f"below min_sep cannot be parked on. Check the spectroscopy PNG, or set the "
            f"cached parity frequencies and disable recalibration."
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
