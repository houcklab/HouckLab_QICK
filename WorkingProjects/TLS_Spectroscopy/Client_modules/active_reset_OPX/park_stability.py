"""Hardware-independent analysis helpers for the q3 park-stability probe."""

import math

import numpy as np


def build_frequency_axis_mhz(center_mhz, half_span_mhz, step_mhz):
    """Return a symmetric, endpoint-inclusive spectroscopy axis."""

    center_mhz = float(center_mhz)
    half_span_mhz = float(half_span_mhz)
    step_mhz = float(step_mhz)
    if not all(math.isfinite(value) for value in (center_mhz, half_span_mhz, step_mhz)):
        raise ValueError("center, half-span, and step must be finite")
    if half_span_mhz <= 0 or step_mhz <= 0:
        raise ValueError("frequency half-span and step must be positive")

    intervals = int(math.ceil((2.0 * half_span_mhz) / step_mhz))
    intervals = max(intervals, 2)
    if intervals % 2:
        intervals += 1
    return np.linspace(
        center_mhz - half_span_mhz,
        center_mhz + half_span_mhz,
        intervals + 1,
        dtype=float,
    )


def build_park_probe_config(
    base_config,
    *,
    park_gain,
    frequency_axis_mhz,
    shots,
    spectroscopy_gain,
    spectroscopy_length_us,
    passive_reset_us,
):
    """Build the safe per-shot park probe config from the live machine config."""

    park_gain = int(park_gain)
    if park_gain == 0 or not -32767 <= park_gain <= 32767:
        raise ValueError("park_gain must be a nonzero signed 16-bit DAC value")
    frequency_axis = np.asarray(frequency_axis_mhz, dtype=float).reshape(-1)
    if frequency_axis.size < 3 or not np.all(np.isfinite(frequency_axis)):
        raise ValueError("frequency_axis_mhz must contain at least three finite points")
    steps = np.diff(frequency_axis)
    if np.any(steps <= 0) or not np.allclose(steps, steps[0], rtol=1e-9, atol=1e-9):
        raise ValueError("frequency_axis_mhz must be increasing and uniformly spaced")
    shots = int(shots)
    if shots <= 0:
        raise ValueError("shots must be positive")
    spectroscopy_gain = int(spectroscopy_gain)
    if spectroscopy_gain <= 0 or spectroscopy_gain > 32767:
        raise ValueError("spectroscopy_gain must be in the range 1..32767")
    spectroscopy_length_us = float(spectroscopy_length_us)
    passive_reset_us = float(passive_reset_us)
    if spectroscopy_length_us <= 0 or passive_reset_us < 0:
        raise ValueError("spectroscopy length must be positive and passive reset non-negative")

    cfg = dict(base_config)
    cfg.pop("flux_tail_compensation", None)
    cfg.update({
        "ff_gain": park_gain,
        "ff_park_gain": 0,
        "readout_after_park": False,
        "baseline_rearm_us": 0.05,
        "relax_delay": passive_reset_us,
        "qubit_pulse_style": "const",
        "qubit_gain": spectroscopy_gain,
        "qubit_length": spectroscopy_length_us,
        "start": float(frequency_axis[0]),
        "step": float(steps[0]),
        "expts": int(frequency_axis.size),
        "reps": shots,
    })
    return cfg


def summarize_park_trace(
    *,
    delay_us,
    frequency_mhz,
    supported,
    sweep_min_mhz,
    sweep_max_mhz,
    active_reset_window_us,
    max_allowed_drift_mhz,
    edge_guard_mhz=1.0,
):
    """Summarize whether a measured park stays stable over the reset window.

    A trace that touches a spectroscopy boundary is inconclusive even when its
    apparent drift is small: the actual resonance may already have left the map.
    """

    delay = np.asarray(delay_us, dtype=float).reshape(-1)
    frequency = np.asarray(frequency_mhz, dtype=float).reshape(-1)
    support = np.asarray(supported, dtype=bool).reshape(-1)
    if not (delay.size == frequency.size == support.size):
        raise ValueError("delay, frequency, and supported vectors must have matching lengths")
    if delay.size == 0:
        raise ValueError("park trace must contain at least one point")

    sweep_min_mhz = float(sweep_min_mhz)
    sweep_max_mhz = float(sweep_max_mhz)
    active_reset_window_us = float(active_reset_window_us)
    max_allowed_drift_mhz = float(max_allowed_drift_mhz)
    edge_guard_mhz = float(edge_guard_mhz)
    finite_settings = (
        sweep_min_mhz,
        sweep_max_mhz,
        active_reset_window_us,
        max_allowed_drift_mhz,
        edge_guard_mhz,
    )
    if not all(math.isfinite(value) for value in finite_settings):
        raise ValueError("park-trace settings must be finite")
    if sweep_max_mhz <= sweep_min_mhz:
        raise ValueError("sweep_max_mhz must be greater than sweep_min_mhz")
    if active_reset_window_us <= 0 or max_allowed_drift_mhz < 0 or edge_guard_mhz < 0:
        raise ValueError("window must be positive and drift/edge limits non-negative")

    usable = support & np.isfinite(delay) & np.isfinite(frequency)
    in_window = usable & (delay <= active_reset_window_us)
    outside_window = usable & (delay > active_reset_window_us)
    indices = np.flatnonzero(in_window)
    indices = indices[np.argsort(delay[indices])]

    summary = {
        "status": "inconclusive_insufficient_trace",
        "park_stable": False,
        "active_reset_window_us": active_reset_window_us,
        "max_allowed_drift_mhz": max_allowed_drift_mhz,
        "edge_guard_mhz": edge_guard_mhz,
        "points_in_reset_window": int(indices.size),
        "outside_window_points": int(np.count_nonzero(outside_window)),
        "supported_points": int(np.count_nonzero(usable)),
        "total_points": int(delay.size),
        "edge_limited": False,
        "reference_delay_us": None,
        "reference_frequency_mhz": None,
        "max_abs_drift_mhz": None,
        "peak_to_peak_mhz": None,
        "frequency_slope_khz_per_us": None,
    }
    if indices.size < 3:
        return summary

    window_delay = delay[indices]
    window_frequency = frequency[indices]
    reference_frequency = float(window_frequency[0])
    drift = window_frequency - reference_frequency
    edge_distance = np.minimum(
        window_frequency - sweep_min_mhz,
        sweep_max_mhz - window_frequency,
    )
    edge_limited = bool(np.any(edge_distance <= edge_guard_mhz))
    slope_mhz_per_us = float(np.polyfit(window_delay, window_frequency, 1)[0])
    max_abs_drift = float(np.max(np.abs(drift)))

    if edge_limited:
        status = "inconclusive_sweep_edge"
    elif max_abs_drift <= max_allowed_drift_mhz:
        status = "pass"
    else:
        status = "fail"

    summary.update({
        "status": status,
        "park_stable": status == "pass",
        "edge_limited": edge_limited,
        "reference_delay_us": float(window_delay[0]),
        "reference_frequency_mhz": reference_frequency,
        "max_abs_drift_mhz": max_abs_drift,
        "peak_to_peak_mhz": float(np.ptp(window_frequency)),
        "frequency_slope_khz_per_us": 1e3 * slope_mhz_per_us,
        "minimum_sweep_edge_distance_mhz": float(np.min(edge_distance)),
    })
    return summary
