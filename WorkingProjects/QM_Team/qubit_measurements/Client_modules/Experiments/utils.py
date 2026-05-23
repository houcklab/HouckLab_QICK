import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
from scipy.signal import find_peaks, savgol_filter
import time
import datetime
from datetime import datetime
import os
import json

def choose_two_tone_freqs_from_lorentz_or_peaks(data_spec, min_sep_mhz=0.1):
    x_pts = np.asarray(data_spec["data"]["x_pts"], dtype=float)
    avgi = np.asarray(data_spec["data"]["avgi"][0][0], dtype=float)
    avgq = np.asarray(data_spec["data"]["avgq"][0][0], dtype=float)
    avgamp0 = np.abs(avgi + 1j * avgq) ** 2

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
    """
    if n_chunks < 1:
        raise ValueError(f"n_chunks must be >= 1, got {n_chunks}")
    I_parts, Q_parts, t_parts = [], [], []
    wall_clocks = []
    gap_indices = []
    cum_offset_us = 0.0
    cum_idx = 0
    first_meta = {}
    # Keys that describe the acquisition mode/units, propagated from the first
    # chunk to the stitched output so save_data persists them verbatim.
    _META_KEYS = (
        "mode", "sample_period_us",
        "read_length_us", "adc_trig_offset_us", "ro_norm_cycles",
        "decimated_fs_MHz", "decimated_fs_source",
        "capture_length_us", "samples_per_capture",
        "soft_avgs", "n_captures",
    )
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
            # Stitch time: previous chunk's last + estimated sample period
            if t_parts and t_parts[-1].size >= 2:
                sp = float(t_parts[-1][1] - t_parts[-1][0])
            else:
                sp = 0.0
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