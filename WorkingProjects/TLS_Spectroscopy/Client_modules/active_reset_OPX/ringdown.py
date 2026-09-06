import math

import numpy as np


def delay_cycle_axis(minimum_us, step_us, points, descending, us2cycles):
    minimum_us = float(minimum_us)
    step_us = float(step_us)
    points = int(points)
    if not math.isfinite(minimum_us) or minimum_us < 0:
        raise ValueError("minimum delay must be finite and non-negative")
    if not math.isfinite(step_us) or step_us <= 0:
        raise ValueError("delay step must be positive and finite")
    if points < 2:
        raise ValueError("delay axis needs at least two points")
    minimum_cycles = int(us2cycles(minimum_us))
    step_cycles = int(us2cycles(step_us))
    if step_cycles <= 0:
        raise ValueError("delay step rounds to zero tProc cycles")
    cycles = minimum_cycles + np.arange(points, dtype=np.int64) * step_cycles
    if bool(descending):
        cycles = cycles[::-1].copy()
    return cycles


def combine_ringdown_sweeps(sweeps):
    sweeps = list(sweeps)
    if not sweeps:
        raise ValueError("at least one ring-down sweep is required")
    fields = ("baseline_i", "baseline_q", "residual_i", "residual_q")
    expected_delays = None
    ordered = {field: [] for field in fields}
    for sweep in sweeps:
        delays = np.asarray(sweep["delays_us"], dtype=float).reshape(-1)
        if delays.size < 2 or not np.all(np.isfinite(delays)):
            raise ValueError("ring-down sweep delays must be finite")
        order = np.argsort(delays)
        delays = delays[order]
        if np.any(np.diff(delays) <= 0):
            raise ValueError("ring-down sweep delays must be distinct")
        if expected_delays is None:
            expected_delays = delays
        elif not np.allclose(delays, expected_delays, rtol=0.0, atol=1e-9):
            raise ValueError("ring-down sweeps must use the same delay axis")
        for field in fields:
            values = np.asarray(sweep[field], dtype=float)
            if values.ndim != 2 or values.shape[0] != delays.size:
                raise ValueError(f"{field} must have one row per delay")
            ordered[field].append(values[order])
    result = {"delays_us": expected_delays}
    result.update({field: np.concatenate(ordered[field], axis=1) for field in fields})
    return result


def _ringdown_vectors(delays_us, amplitudes, sem):
    delays = np.asarray(delays_us, dtype=float).reshape(-1)
    values = np.asarray(amplitudes, dtype=float).reshape(-1)
    errors = np.asarray(sem, dtype=float).reshape(-1)
    if delays.size < 5 or values.size != delays.size or errors.size != delays.size:
        raise ValueError("ring-down vectors need at least five matching values")
    if not np.all(np.isfinite(delays)) or not np.all(np.isfinite(values)):
        raise ValueError("ring-down delays and amplitudes must be finite")
    if not np.all(np.isfinite(errors)) or np.any(errors < 0):
        raise ValueError("ring-down uncertainties must be finite and non-negative")
    if np.any(delays < 0) or np.any(np.diff(delays) <= 0):
        raise ValueError("ring-down delays must be non-negative and strictly increasing")
    return delays, values, errors


def select_noise_floor_delay(delays_us, amplitudes, sem, sigma=3.0, consecutive=5):
    delays, values, errors = _ringdown_vectors(delays_us, amplitudes, sem)
    sigma = float(sigma)
    consecutive = int(consecutive)
    if not math.isfinite(sigma) or sigma <= 0:
        raise ValueError("sigma must be positive and finite")
    if consecutive <= 0 or consecutive > delays.size:
        raise ValueError("consecutive must fit within the delay vector")
    below = values <= sigma * errors
    for index in range(delays.size - consecutive + 1):
        if np.all(below[index:index + consecutive]):
            return float(delays[index])
    return None


def fit_field_decay(delays_us, amplitudes, sem):
    delays, values, errors = _ringdown_vectors(delays_us, amplitudes, sem)
    positive_errors = errors[errors > 0]
    error_floor = float(np.median(positive_errors)) if positive_errors.size else 1.0
    effective_errors = np.maximum(errors, error_floor * 1e-6)
    fit_mask = (values > 0) & (values > 5.0 * effective_errors)
    if np.count_nonzero(fit_mask) < 5:
        raise ValueError("ring-down amplitude has too few high-SNR points")
    fit_delays = delays[fit_mask]
    fit_values = values[fit_mask]
    fit_errors = effective_errors[fit_mask]
    coefficients, covariance = np.polyfit(
        fit_delays,
        np.log(fit_values),
        deg=1,
        w=fit_values / fit_errors,
        cov=True,
    )
    slope = float(coefficients[0])
    intercept = float(coefficients[1])
    if not math.isfinite(slope) or slope >= 0:
        raise ValueError("ring-down amplitude does not have a decaying high-SNR fit")
    amplitude = math.exp(intercept)
    tau = -1.0 / slope
    slope_err = math.sqrt(max(float(covariance[0, 0]), 0.0))
    intercept_err = math.sqrt(max(float(covariance[1, 1]), 0.0))
    tau_err = slope_err / (slope * slope)
    predicted = amplitude * np.exp(-delays / tau)
    return {
        "field_amplitude": float(amplitude),
        "field_tau_us": float(tau),
        "field_floor": 0.0,
        "field_amplitude_err": float(amplitude * intercept_err),
        "field_tau_err_us": float(tau_err),
        "field_floor_err": 0.0,
        "field_fit_points": int(np.count_nonzero(fit_mask)),
        "rmse": float(np.sqrt(np.mean((values - predicted) ** 2))),
        "predicted_amplitude": predicted,
    }


def analyze_ringdown(
    delays_us,
    baseline_i,
    baseline_q,
    residual_i,
    residual_q,
    sigma=3.0,
    consecutive=5,
    timing_resolution_us=0.1,
    observation_offset_us=0.0,
    probe_length_us=0.0,
):
    delays = np.asarray(delays_us, dtype=float).reshape(-1)
    arrays = [
        np.asarray(value, dtype=float)
        for value in (baseline_i, baseline_q, residual_i, residual_q)
    ]
    if any(value.ndim != 2 for value in arrays):
        raise ValueError("ring-down IQ arrays must be two-dimensional")
    if any(value.shape != arrays[0].shape for value in arrays):
        raise ValueError("ring-down IQ arrays must have matching shapes")
    if arrays[0].shape[0] != delays.size or arrays[0].shape[1] < 2:
        raise ValueError("ring-down IQ rows must match delays and contain at least two shots")
    if any(not np.all(np.isfinite(value)) for value in arrays):
        raise ValueError("ring-down IQ arrays must be finite")
    delta = (arrays[2] - arrays[0]) + 1j * (arrays[3] - arrays[1])
    coherent = np.mean(delta, axis=1)
    amplitude = np.abs(coherent)
    centered = delta - coherent[:, None]
    sem = np.sqrt(
        (np.var(centered.real, axis=1, ddof=1) + np.var(centered.imag, axis=1, ddof=1))
        / delta.shape[1]
    )
    coherent_crossing = select_noise_floor_delay(
        delays,
        amplitude,
        sem,
        sigma=sigma,
        consecutive=consecutive,
    )
    baseline_complex = arrays[0] + 1j * arrays[1]
    residual_complex = arrays[2] + 1j * arrays[3]
    baseline_center = np.mean(baseline_complex)
    excess_samples = (
        np.abs(residual_complex - baseline_center) ** 2
        - np.abs(baseline_complex - baseline_center) ** 2
    )
    energy_excess = np.mean(excess_samples, axis=1)
    energy_sem = np.std(excess_samples, axis=1, ddof=1) / math.sqrt(delta.shape[1])
    energy_crossing = select_noise_floor_delay(
        delays,
        np.abs(energy_excess),
        energy_sem,
        sigma=sigma,
        consecutive=consecutive,
    )
    crossing = None
    if coherent_crossing is not None and energy_crossing is not None:
        crossing = max(coherent_crossing, energy_crossing)
    fit = None
    try:
        fit = fit_field_decay(delays, amplitude, sem)
    except (RuntimeError, ValueError):
        pass
    timing_resolution_us = float(timing_resolution_us)
    if not math.isfinite(timing_resolution_us) or timing_resolution_us <= 0:
        raise ValueError("timing resolution must be positive and finite")
    observation_offset_us = float(observation_offset_us)
    probe_length_us = float(probe_length_us)
    if not math.isfinite(observation_offset_us) or observation_offset_us < 0:
        raise ValueError("observation offset must be finite and non-negative")
    if not math.isfinite(probe_length_us) or probe_length_us < 0:
        raise ValueError("probe length must be finite and non-negative")
    observed_crossing = None
    recommended = None
    if crossing is not None:
        observed_crossing = crossing + observation_offset_us + probe_length_us
        recommended = round(
            math.ceil((observed_crossing - 1e-12) / timing_resolution_us)
            * timing_resolution_us,
            12,
        )
    result = {
        "status": "complete" if crossing is not None else "scan_too_short",
        "noise_sigma": float(sigma),
        "required_consecutive_points": int(consecutive),
        "coherent_noise_floor_delay_us": coherent_crossing,
        "energy_noise_floor_delay_us": energy_crossing,
        "programmed_noise_floor_delay_us": crossing,
        "noise_floor_delay_us": observed_crossing,
        "recommended_thermalization_us": recommended,
        "observation_offset_us": observation_offset_us,
        "probe_length_us": probe_length_us,
        "coherent_i": coherent.real,
        "coherent_q": coherent.imag,
        "coherent_amplitude": amplitude,
        "coherent_sem": sem,
        "energy_excess": energy_excess,
        "energy_sem": energy_sem,
        "shots_per_delay": int(delta.shape[1]),
    }
    if fit is not None:
        result.update(fit)
        result["photon_tau_us"] = float(fit["field_tau_us"] / 2.0)
        result["photon_tau_err_us"] = float(fit["field_tau_err_us"] / 2.0)
    else:
        result.update({
            "field_tau_us": None,
            "field_tau_err_us": None,
            "photon_tau_us": None,
            "photon_tau_err_us": None,
            "predicted_amplitude": np.full(delays.size, np.nan),
        })
    return result
