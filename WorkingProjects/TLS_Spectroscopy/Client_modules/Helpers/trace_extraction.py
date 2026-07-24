
import numpy as np
from scipy import signal, optimize

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import fit_functions as ff


def _odd_savgol_window(requested, n):
    w = min(int(requested), n if n % 2 else n - 1)
    if w % 2 == 0:
        w -= 1
    return max(w, 3)


def _quadratic_refine_x(x, y, idx):
    if idx <= 0 or idx >= len(x) - 1:
        return float(x[idx])
    y0, y1, y2 = y[idx - 1], y[idx], y[idx + 1]
    denom = y0 - 2.0 * y1 + y2
    if not np.isfinite(denom) or abs(denom) < 1e-18:
        return float(x[idx])
    delta = float(np.clip(0.5 * (y0 - y2) / denom, -1.0, 1.0))
    return float(x[idx] + delta * (x[idx + 1] - x[idx]))


def _odd_window_from_mhz(frequency_axis_ghz, width_mhz, polyorder=2):
    frequency_axis_ghz = np.asarray(frequency_axis_ghz, dtype=float)
    if frequency_axis_ghz.size < polyorder + 3:
        return None
    step_mhz = abs(float(np.nanmedian(np.diff(frequency_axis_ghz))) * 1e3)
    if not np.isfinite(step_mhz) or step_mhz <= 0:
        return None
    window = int(round(float(width_mhz) / step_mhz))
    window = max(polyorder + 3, window)
    if window % 2 == 0:
        window += 1
    max_window = frequency_axis_ghz.size if frequency_axis_ghz.size % 2 else frequency_axis_ghz.size - 1
    window = min(window, max_window)
    return window if window > polyorder else None


def make_trace_feature_score(frequency_axis_ghz, iq_magnitude_dbm, expected_window_mask,
                             polarity, trace_baseline_window_mhz=25.0):
    frequency_axis_ghz = np.asarray(frequency_axis_ghz, dtype=float)
    magnitude = np.asarray(iq_magnitude_dbm, dtype=float)
    score = np.full_like(magnitude, np.nan, dtype=float)
    span_mhz = float((np.nanmax(frequency_axis_ghz) - np.nanmin(frequency_axis_ghz)) * 1e3)
    effective_baseline_mhz = max(float(trace_baseline_window_mhz), 0.5 * span_mhz)
    window = _odd_window_from_mhz(frequency_axis_ghz, effective_baseline_mhz, polyorder=2)

    for time_index in range(magnitude.shape[1]):
        mag_slice = np.asarray(magnitude[:, time_index], dtype=float)
        finite = np.isfinite(mag_slice)
        if np.count_nonzero(finite) < 7:
            continue
        filled = mag_slice.copy()
        filled[~finite] = np.nanmedian(mag_slice[finite])
        if window is not None and window < filled.size:
            baseline = signal.savgol_filter(filled, window, 2, mode="interp")
        else:
            baseline = np.full_like(filled, np.nanmedian(filled))
        residual = filled - baseline
        if str(polarity).lower().startswith("dark"):
            residual = -residual
        residual = residual - np.nanmedian(residual)
        scale = np.nanpercentile(residual, 98) - np.nanpercentile(residual, 50)
        if not np.isfinite(scale) or scale <= 1e-12:
            scale = np.nanstd(residual)
        if not np.isfinite(scale) or scale <= 1e-12:
            continue
        score[:, time_index] = residual / scale

    score[~expected_window_mask, :] = -np.inf
    return np.where(np.isfinite(score), score, -np.inf)


def dynamic_program_trace_ridge(frequency_axis_ghz, score, trace_max_jump_mhz=4.0,
                                trace_smoothness_penalty=0.15):
    frequency_axis_ghz = np.asarray(frequency_axis_ghz, dtype=float)
    score = np.asarray(score, dtype=float)
    n_freq, n_time = score.shape
    step_mhz = abs(float(np.nanmedian(np.diff(frequency_axis_ghz))) * 1e3)
    if not np.isfinite(step_mhz) or step_mhz <= 0:
        raise ValueError("Cannot track ridge because the frequency axis is not monotonic.")
    max_jump_rows = max(1, int(np.ceil(trace_max_jump_mhz / step_mhz)))

    cost = np.full((n_freq, n_time), np.inf)
    back = np.full((n_freq, n_time), -1, dtype=int)
    finite_first = np.isfinite(score[:, 0])
    if not np.any(finite_first):
        raise ValueError("Cannot track ridge because the first delay slice has no finite score.")
    cost[finite_first, 0] = -score[finite_first, 0]

    row_index = np.arange(n_freq)
    for time_index in range(1, n_time):
        for freq_index in range(n_freq):
            if not np.isfinite(score[freq_index, time_index]):
                continue
            lo = max(0, freq_index - max_jump_rows)
            hi = min(n_freq, freq_index + max_jump_rows + 1)
            previous_rows = row_index[lo:hi]
            jump_mhz = (frequency_axis_ghz[previous_rows] - frequency_axis_ghz[freq_index]) * 1e3
            candidate = (cost[lo:hi, time_index - 1]
                         + trace_smoothness_penalty * (jump_mhz / trace_max_jump_mhz) ** 2)
            finite_candidate = np.isfinite(candidate)
            if not np.any(finite_candidate):
                continue
            local_candidates = np.where(finite_candidate)[0]
            best_local = int(local_candidates[np.argmin(candidate[finite_candidate])])
            cost[freq_index, time_index] = candidate[best_local] - score[freq_index, time_index]
            back[freq_index, time_index] = lo + best_local

    finite_final = np.isfinite(cost[:, -1])
    if not np.any(finite_final):
        raise ValueError("Cannot track ridge because no finite path reached the final delay slice.")

    ridge_rows = np.full(n_time, -1, dtype=int)
    ridge_rows[-1] = int(np.where(finite_final)[0][np.argmin(cost[finite_final, -1])])
    for time_index in range(n_time - 1, 0, -1):
        previous = back[ridge_rows[time_index], time_index]
        if previous < 0:
            raise ValueError("Trace ridge backtracking failed.")
        ridge_rows[time_index - 1] = previous
    return ridge_rows, frequency_axis_ghz[ridge_rows]


def lorentzian_with_slope(frequency_ghz, offset, slope, amplitude, center_ghz, fwhm_ghz):
    detuning = (frequency_ghz - center_ghz) / fwhm_ghz
    return offset + slope * (frequency_ghz - center_ghz) + amplitude / (1.0 + 4.0 * detuning ** 2)


def refine_trace_lorentzian(frequency_axis_ghz, iq_magnitude_dbm, seed_frequency_ghz,
                            polarity, trace_local_fit_half_window_mhz=8.0):
    frequency_axis_ghz = np.asarray(frequency_axis_ghz, dtype=float)
    magnitude = np.asarray(iq_magnitude_dbm, dtype=float)
    seed_frequency_ghz = np.asarray(seed_frequency_ghz, dtype=float)
    centers_ghz = np.full_like(seed_frequency_ghz, np.nan, dtype=float)
    fwhm_hz = np.full_like(seed_frequency_ghz, np.nan, dtype=float)
    fit_ok = np.zeros_like(seed_frequency_ghz, dtype=bool)
    half_width_ghz = trace_local_fit_half_window_mhz / 1e3

    for time_index, seed in enumerate(seed_frequency_ghz):
        fitted = False
        for window_scale in (1.0, 3.0):
            half_ghz = half_width_ghz * window_scale
            mask = (np.isfinite(frequency_axis_ghz)
                    & np.isfinite(magnitude[:, time_index])
                    & (np.abs(frequency_axis_ghz - seed) <= half_ghz))
            if np.count_nonzero(mask) < 8:
                continue
            x = frequency_axis_ghz[mask]
            y = magnitude[mask, time_index]
            y_median = float(np.nanmedian(y))
            y_span = max(float(np.nanmax(y) - np.nanmin(y)), 1e-3)
            amplitude0 = y_span if str(polarity).lower().startswith("bright") else -y_span
            lower_amp, upper_amp = (0.0, 10.0 * y_span) if amplitude0 > 0 else (-10.0 * y_span, 0.0)
            fwhm_upper_ghz = max(0.0300, 1.5 * half_ghz)
            p0 = [y_median, 0.0, amplitude0, float(seed), 0.004]
            bounds = ([y_median - 3.0 * y_span, -500.0, lower_amp, seed - half_ghz, 0.0004],
                      [y_median + 3.0 * y_span, 500.0, upper_amp, seed + half_ghz, fwhm_upper_ghz])
            try:
                result, _ = optimize.curve_fit(lorentzian_with_slope, x, y, p0=p0,
                                               bounds=bounds, maxfev=20_000)
            except Exception:
                continue
            centers_ghz[time_index] = float(result[3])
            fwhm_hz[time_index] = abs(float(result[4])) * 1e9
            fit_ok[time_index] = True
            fitted = True
            if abs(float(result[4])) <= 0.6 * (2.0 * half_ghz):
                break
        if not fitted:
            centers_ghz[time_index] = seed

    centers_ghz = np.where(np.isfinite(centers_ghz), centers_ghz, seed_frequency_ghz)
    return centers_ghz, fwhm_hz, fit_ok


def smooth_trace_frequency(frequency_ghz, time_ns, trace_smoothing_window_points=17,
                           trace_smoothing_polyorder=2):
    frequency_ghz = np.asarray(frequency_ghz, dtype=float)
    valid = np.isfinite(frequency_ghz)
    if np.count_nonzero(valid) < 5:
        return frequency_ghz.copy()
    time_ns = np.asarray(time_ns, dtype=float)
    filled = frequency_ghz.copy()
    filled[~valid] = np.interp(time_ns[~valid], time_ns[valid], frequency_ghz[valid])
    polyorder = max(0, int(trace_smoothing_polyorder))
    window = min(int(trace_smoothing_window_points),
                 filled.size if filled.size % 2 else filled.size - 1)
    window = max(polyorder + 3, window)
    if window % 2 == 0:
        window += 1
    if window >= filled.size:
        window = filled.size if filled.size % 2 else filled.size - 1
    if window <= polyorder:
        return filled
    return signal.savgol_filter(filled, window, min(polyorder, window - 1), mode="interp")


def extract_trace_independent_slices(iq_magnitude_dbm, frequency_axis_ghz, time_ns,
                                     expected_window_mask):
    n_time = len(time_ns)
    f_hz_axis = np.asarray(frequency_axis_ghz, dtype=float) * 1e9
    extracted_qubit_frequency_ghz = np.full(n_time, np.nan)
    extracted_if_frequency_hz = np.full(n_time, np.nan)
    extracted_fwhm_hz = np.full(n_time, np.nan)
    extracted_supported = np.zeros(n_time, dtype=bool)
    extraction_method = []

    for time_index in range(n_time):
        magnitude_slice = np.asarray(iq_magnitude_dbm[:, time_index], dtype=float)
        finite_mask = np.isfinite(magnitude_slice) & np.isfinite(f_hz_axis) & expected_window_mask
        if np.count_nonzero(finite_mask) < 7:
            extraction_method.append("failed")
            continue
        f_slice = f_hz_axis[finite_mask]
        mag_slice = magnitude_slice[finite_mask]
        if len(f_slice) >= 7:
            smooth_window = _odd_savgol_window(9, len(f_slice))
            mag_for_min = signal.savgol_filter(mag_slice, smooth_window,
                                               min(2, smooth_window - 1), mode="interp")
        else:
            mag_for_min = mag_slice
        rough_idx = int(np.nanargmin(mag_for_min))
        rough_fr_hz = _quadratic_refine_x(f_slice, mag_for_min, rough_idx)
        local_half_width_hz = max(12e6, 0.20 * float(np.nanmax(f_slice) - np.nanmin(f_slice)))
        local_mask = np.abs(f_slice - rough_fr_hz) <= local_half_width_hz
        try:
            if np.count_nonzero(local_mask) < 7:
                raise ValueError("Not enough local points around the dip for a Lorentzian fit.")
            params, _ = ff.fit_resonator_dip(f_slice[local_mask] / 1e6, mag_slice[local_mask])
            fr_hz = float(params["fr"]) * 1e6
            fwhm_hz = abs(float(params["fwhm"])) * 1e6
            local_min = float(np.nanmin(f_slice[local_mask]))
            local_max = float(np.nanmax(f_slice[local_mask]))
            if not (local_min <= fr_hz <= local_max):
                raise ValueError("Dip fit center escaped the local search window.")
            method = "local_dip_lorentzian"
        except Exception:
            fr_hz = rough_fr_hz
            fwhm_hz = np.nan
            method = "local_smoothed_minimum"
        extracted_if_frequency_hz[time_index] = fr_hz
        extracted_fwhm_hz[time_index] = fwhm_hz
        extracted_qubit_frequency_ghz[time_index] = fr_hz / 1e9
        extracted_supported[time_index] = True
        extraction_method.append(method)

    return {"selected_frequency_ghz": extracted_qubit_frequency_ghz,
            "ridge_frequency_ghz": np.full(n_time, np.nan),
            "local_frequency_ghz": extracted_qubit_frequency_ghz,
            "smoothed_frequency_ghz": extracted_qubit_frequency_ghz,
            "extracted_if_frequency_hz": extracted_if_frequency_hz,
            "extracted_fwhm_hz": extracted_fwhm_hz,
            "supported": extracted_supported,
            "method": extraction_method,
            "polarity": "dark"}


def extract_trace_ridge(iq_magnitude_dbm, frequency_axis_ghz, time_ns,
                        expected_window_mask, trace_polarity="auto",
                        trace_baseline_window_mhz=25.0, trace_max_jump_mhz=4.0,
                        trace_smoothness_penalty=0.15,
                        trace_local_fit_half_window_mhz=8.0,
                        trace_smoothing_window_points=17,
                        trace_smoothing_polyorder=2,
                        trace_use_smoothed_frequency=True):
    polarities = ["bright", "dark"] if trace_polarity == "auto" else [trace_polarity]
    candidates = []
    for polarity in polarities:
        score = make_trace_feature_score(frequency_axis_ghz, iq_magnitude_dbm,
                                         expected_window_mask, polarity,
                                         trace_baseline_window_mhz)
        ridge_rows, ridge_frequency_ghz = dynamic_program_trace_ridge(
            frequency_axis_ghz, score, trace_max_jump_mhz, trace_smoothness_penalty)
        path_score = float(np.nanmean(score[ridge_rows, np.arange(score.shape[1])]))
        candidates.append((path_score, polarity, score, ridge_frequency_ghz))
    _, polarity, score, ridge_frequency_ghz = max(candidates, key=lambda item: item[0])

    local_frequency_ghz, fwhm_hz, fit_ok = refine_trace_lorentzian(
        frequency_axis_ghz, iq_magnitude_dbm, ridge_frequency_ghz, polarity,
        trace_local_fit_half_window_mhz)
    smoothed_frequency_ghz = smooth_trace_frequency(local_frequency_ghz, time_ns,
                                                    trace_smoothing_window_points,
                                                    trace_smoothing_polyorder)
    selected_frequency_ghz = (smoothed_frequency_ghz if trace_use_smoothed_frequency
                              else local_frequency_ghz)
    extracted_if_frequency_hz = selected_frequency_ghz * 1e9
    extraction_method = [f"ridge_{polarity}_local_lorentzian" if ok else f"ridge_{polarity}"
                         for ok in fit_ok]
    return {"selected_frequency_ghz": selected_frequency_ghz,
            "ridge_frequency_ghz": ridge_frequency_ghz,
            "local_frequency_ghz": local_frequency_ghz,
            "smoothed_frequency_ghz": smoothed_frequency_ghz,
            "extracted_if_frequency_hz": extracted_if_frequency_hz,
            "extracted_fwhm_hz": fwhm_hz,
            "supported": np.isfinite(selected_frequency_ghz),
            "method": extraction_method,
            "polarity": polarity,
            "score": score}


def extract_trace_from_map(iq_magnitude_dbm, frequency_axis_ghz, time_ns,
                           baseline_frequency_ghz, target_frequency_ghz,
                           frequency_margin_ghz, trace_tracking_mode="ridge",
                           **trace_knobs):
    expected_min_ghz = min(baseline_frequency_ghz, target_frequency_ghz) - frequency_margin_ghz
    expected_max_ghz = max(baseline_frequency_ghz, target_frequency_ghz) + frequency_margin_ghz
    frequency_axis_ghz = np.asarray(frequency_axis_ghz, dtype=float)
    expected_window_mask = ((frequency_axis_ghz >= expected_min_ghz)
                            & (frequency_axis_ghz <= expected_max_ghz))
    if not np.any(expected_window_mask):
        raise ValueError(
            "Expected trace frequency window does not overlap the spectroscopy sweep. "
            f"expected=[{expected_min_ghz:.6f}, {expected_max_ghz:.6f}] GHz, "
            f"sweep=[{float(np.nanmin(frequency_axis_ghz)):.6f}, "
            f"{float(np.nanmax(frequency_axis_ghz)):.6f}] GHz")

    if trace_tracking_mode == "ridge":
        try:
            trace_result = extract_trace_ridge(iq_magnitude_dbm, frequency_axis_ghz,
                                               time_ns, expected_window_mask, **trace_knobs)
        except Exception as exc:
            print(f"Ridge trace extraction failed; falling back to independent slices: {exc}")
            trace_result = extract_trace_independent_slices(
                iq_magnitude_dbm, frequency_axis_ghz, time_ns, expected_window_mask)
    else:
        trace_result = extract_trace_independent_slices(
            iq_magnitude_dbm, frequency_axis_ghz, time_ns, expected_window_mask)
    trace_result["expected_window_mask"] = expected_window_mask
    trace_result["expected_window_ghz"] = (expected_min_ghz, expected_max_ghz)
    return trace_result
