"""Conservative, controller-neutral candidate solves from measured traces.

This module never installs a candidate. A failed gate returns no payload.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
from scipy.optimize import lsq_linear

from .core import QualityReport, StepMap, TraceResult, evaluate_trace_quality


@dataclass(frozen=True)
class FluxBranch:
    dc: np.ndarray
    frequency_ghz: np.ndarray

    def __post_init__(self):
        dc = np.asarray(self.dc, dtype=float)
        frequency = np.asarray(self.frequency_ghz, dtype=float)
        if dc.ndim != 1 or frequency.shape != dc.shape or dc.size < 3:
            raise ValueError("flux branch needs matching one-dimensional grids")
        if not np.all(np.isfinite(dc)) or not np.all(np.isfinite(frequency)):
            raise ValueError("flux branch contains nonfinite values")
        if not (np.all(np.diff(dc) > 0) and
                (np.all(np.diff(frequency) > 0) or np.all(np.diff(frequency) < 0))):
            raise ValueError("flux branch must be strictly monotonic")
        object.__setattr__(self, "dc", dc)
        object.__setattr__(self, "frequency_ghz", frequency)

    def invert(self, frequency_ghz):
        values = np.asarray(frequency_ghz, dtype=float)
        frequency = self.frequency_ghz
        dc = self.dc
        if frequency[0] > frequency[-1]:
            frequency, dc = frequency[::-1], dc[::-1]
        if np.any(values[np.isfinite(values)] < frequency[0]) or np.any(values[np.isfinite(values)] > frequency[-1]):
            raise ValueError("measured frequency lies outside monotonic flux branch")
        return np.interp(values, frequency, dc)


def build_flux_branch(params, baseline_dc: float, target_dc: float) -> FluxBranch:
    """Construct the native-unit local transmon branch; no silent extrapolation."""
    if isinstance(params, dict):
        values = [params[key] for key in ("EJmax", "Ec", "period_volts", "phase_offset_volts", "d")]
        values.append(params.get("tilt_slope", 0.0))
    else:
        values = list(params)
        if len(values) == 5:
            values.append(0.0)
    if len(values) != 6 or not np.all(np.isfinite(values)):
        raise ValueError("flux-fit parameters need five values plus optional tilt")
    ejmax, ec, period, phase_offset, asymmetry, tilt = map(float, values)
    if period == 0 or ec <= 0 or ejmax <= 0:
        raise ValueError("invalid flux-fit energy or period")
    extended = float(target_dc + 0.25 * (target_dc - baseline_dc))
    dc = np.linspace(min(baseline_dc, extended), max(baseline_dc, extended), 12501)
    phase = np.pi * (dc - phase_offset) / period
    ej = ejmax * np.sqrt(np.cos(phase) ** 2 + asymmetry**2 * np.sin(phase) ** 2)
    frequency = np.sqrt(8 * ej * ec) - ec + tilt * dc
    return FluxBranch(dc, frequency)


@dataclass(frozen=True)
class CandidateResult:
    quality: QualityReport
    payload: dict | None
    diagnostics: dict


def _reject(quality, reason, diagnostics=None):
    return CandidateResult(replace(quality, accepted=False,
                                   reasons=quality.reasons + (reason,)), None,
                           {} if diagnostics is None else diagnostics)


def _sample_levels(edges, levels, times):
    positions = np.searchsorted(edges, times, side="right") - 1
    out = np.zeros_like(times, dtype=float)
    active = positions >= 0
    out[active] = levels[positions[active]]
    return out


def _compose_prior(prior, edges, levels, damping):
    previous_edges = np.asarray(prior["segment_edges_ns"], dtype=float)
    previous_levels = np.asarray(prior["multipliers"], dtype=float)
    if (previous_edges.ndim != 1 or previous_levels.ndim != 1 or
            previous_edges.size != previous_levels.size or previous_edges.size == 0):
        raise ValueError("prior has inconsistent segment edges and multipliers")
    if (not np.all(np.isfinite(previous_edges)) or
            not np.all(np.isfinite(previous_levels)) or
            previous_edges[0] != 0 or np.any(np.diff(previous_edges) <= 0)):
        raise ValueError("prior segment edges must start at zero and increase")
    output_edges = np.unique(np.r_[previous_edges, edges])
    previous_on_output = _sample_levels(previous_edges, previous_levels, output_edges)
    adjustment_on_output = _sample_levels(edges, levels, output_edges)
    jumps = np.diff(np.r_[0.0, adjustment_on_output])
    fully = np.zeros_like(output_edges)
    for index, time in enumerate(output_edges):
        lag = time - output_edges[:index + 1]
        fully[index] = np.sum(jumps[:index + 1] *
                              _sample_levels(previous_edges, previous_levels, lag))
    return output_edges, previous_on_output + damping * (fully - previous_on_output)


def solve_candidate(trace: TraceResult, scan: StepMap, *, solve_window_us,
                    baseline_dc: float, target_dc: float, flux_branch: FluxBranch,
                    prior_json: dict | None, damping: float, hardware_limits,
                    flux_channel: int | None = None) -> CandidateResult:
    """Fit a measured plant response, returning a candidate only if all gates pass."""
    quality = evaluate_trace_quality(trace, scan, solve_window_us)
    if not quality.accepted:
        return CandidateResult(quality, None, {})
    span = float(target_dc - baseline_dc)
    if not np.isfinite(span) or abs(span) < 1e-12:
        return _reject(quality, "zero or invalid DC step")
    if not 0 <= damping <= 1:
        return _reject(quality, "damping must be in [0, 1]")
    if prior_json is not None:
        metadata = prior_json.get("metadata", {})
        if not prior_json.get("success", False) or prior_json.get("multiplier_clipped", False):
            return _reject(quality, "prior correction is unsuccessful or clipped")
        try:
            prior_baseline = float(metadata["baseline_dc_offset"])
            prior_target = float(metadata["dc_offset"])
            prior_channel = int(metadata["flux_channel"])
        except (KeyError, TypeError, ValueError):
            return _reject(quality, "prior correction lacks exact step/channel metadata")
        tolerance = max(1e-6, 1e-7 * abs(span))
        if (abs(prior_baseline - baseline_dc) > tolerance or
                abs(prior_target - target_dc) > tolerance or
                (flux_channel is not None and prior_channel != int(flux_channel))):
            return _reject(quality, "prior correction does not match applied step/channel")
    mask = ((scan.delay_us >= solve_window_us[0]) &
            (scan.delay_us <= solve_window_us[1]) & trace.supported)
    time_us = scan.delay_us[mask]
    try:
        effective_dc = flux_branch.invert(trace.frequency_ghz[mask])
    except ValueError as exc:
        return _reject(quality, f"invalid flux inversion: {exc}")
    response = (effective_dc - baseline_dc) / span
    if np.any(~np.isfinite(response)) or np.any(response <= 0):
        return _reject(quality, "nonfinite or nonpositive measured step response")
    # Use only directly supported samples. Short gaps allowed by the quality
    # gate may be interpolated inside the plant model, never relabeled measured.
    time_zeroed = time_us - time_us[0]
    spacing_us = max(2.0, 2.0 * float(np.median(np.diff(time_us))))
    edges_ns = np.arange(0.0, time_zeroed[-1] * 1000 + 1e-9,
                         spacing_us * 1000)
    if edges_ns.size < 2:
        return _reject(quality, "not enough time span for a piecewise solve")
    plant = np.zeros((time_us.size, edges_ns.size))
    for column, edge in enumerate(edges_ns):
        lag_us = time_zeroed - edge / 1000
        active = lag_us >= 0
        plant[active, column] = np.interp(lag_us[active], time_zeroed, response)
    difference = np.eye(edges_ns.size)
    difference[1:, :-1] -= np.eye(edges_ns.size - 1)
    model = plant @ difference
    regularization = 0.003
    augmented = np.vstack([model, np.sqrt(regularization) * np.eye(edges_ns.size)])
    target = np.r_[np.ones(time_us.size), np.sqrt(regularization) * np.ones(edges_ns.size)]
    solved = lsq_linear(augmented, target, bounds=(0.5, 1.5), max_iter=2000)
    levels = np.asarray(solved.x, dtype=float)
    if not solved.success or np.any(np.isclose(levels, 0.5, atol=1e-5)) or np.any(np.isclose(levels, 1.5, atol=1e-5)):
        return _reject(quality, "piecewise multiplier solve failed or clipped")
    if prior_json is not None:
        try:
            edges_ns, levels = _compose_prior(prior_json, edges_ns, levels, damping)
        except (KeyError, ValueError, TypeError) as exc:
            return _reject(quality, f"prior composition failed: {exc}")
    limits = tuple(map(float, hardware_limits))
    command = baseline_dc + span * levels
    if not np.all(np.isfinite(levels)) or not np.all(np.isfinite(command)):
        return _reject(quality, "candidate has nonfinite multiplier or DC command")
    if not limits[0] < limits[1] or np.any(command < limits[0]) or np.any(command > limits[1]):
        return _reject(quality, "candidate exceeds hardware DC command limits")
    if np.any(levels < 0.5) or np.any(levels > 1.5):
        return _reject(quality, "composed multiplier clipped")
    method = ("measured_trace_residual_composed_set_dc_offset_correction"
              if prior_json is not None else
              "measured_trace_piecewise_set_dc_offset_correction")
    payload = {
        "enabled": True, "success": True, "error": None, "method": method,
        "feedforward": [], "feedback": [], "components": [],
        "normalization": 1.0, "multiplier_clipped": False,
        "segment_edges_ns": [float(value) for value in edges_ns],
        "multipliers": [float(value) for value in levels],
        "composed_with_applied_flux_tail_compensation": prior_json is not None,
        "source_compensation": (prior_json.get("source") if prior_json else None),
        "metadata": {
            "baseline_dc_offset": float(baseline_dc),
            "dc_offset": float(target_dc),
            "flux_channel": flux_channel,
            "trace_method": trace.method,
            "trace_source": trace.signal_source,
            "trace_branch": trace.branch,
            "trace_supported_fraction": quality.coverage,
        },
    }
    if prior_json is not None:
        payload["composition_damping"] = float(damping)
    diagnostics = {"rms": float(np.sqrt(np.mean((model @ solved.x - 1.0) ** 2))),
                   "measured_points": int(time_us.size),
                   "first_measured_us": float(time_us[0]),
                   "last_measured_us": float(time_us[-1])}
    return CandidateResult(quality, payload, diagnostics)
