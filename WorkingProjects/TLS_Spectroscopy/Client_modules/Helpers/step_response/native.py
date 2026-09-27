"""Small controller-neutral bridge for saved and live 3A/3B maps."""

from __future__ import annotations

import numpy as np

from . import __version__
from .core import StepMap, TraceConfig, evaluate_trace_quality, extract_step_trace


def validate_applied_correction(prior, *, baseline_dc, target_dc, flux_channel):
    """Reject a 3B residual fit unless the exact applied step is identified."""
    if not isinstance(prior, dict) or prior.get("multiplier_clipped", False):
        raise ValueError("prior correction is missing or clipped")
    metadata = prior.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("prior correction has no step/channel metadata")
    try:
        baseline = float(metadata["baseline_dc_offset"])
        target = float(metadata["dc_offset"])
        channel = int(metadata["flux_channel"])
        edges = np.asarray(prior["segment_edges_ns"], dtype=float)
        levels = np.asarray(prior["multipliers"], dtype=float)
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError(f"prior correction metadata is incomplete: {exc}") from exc
    if (not np.isclose(baseline, baseline_dc, rtol=0, atol=1e-6) or
            not np.isclose(target, target_dc, rtol=0, atol=1e-6) or
            channel != int(flux_channel)):
        raise ValueError("prior correction does not match the measured step/channel")
    if (edges.size == 0 or edges.size != levels.size or edges[0] != 0 or
            not np.all(np.isfinite(edges)) or not np.all(np.isfinite(levels)) or
            np.any(np.diff(edges) <= 0)):
        raise ValueError("prior correction has an invalid piecewise waveform")


def analyze_native_map(frequency_ghz, time_ns, magnitude_dbm, phase_rad,
                       baseline_ghz, target_ghz, *, solve_window_us=None,
                       branch_preference="auto", polarity="auto",
                       max_jump_mhz=8.0, min_support_fraction=0.80):
    """Return only measured trace points and an explicit candidate-JSON gate.

    Native QUA and QICK delay vectors are in ns. No pulse or acquisition
    settings enter this function, and the raw map is never modified.
    """
    time_us = np.asarray(time_ns, dtype=float) / 1000.0
    scan = StepMap(np.asarray(frequency_ghz, dtype=float), time_us,
                   np.asarray(magnitude_dbm, dtype=float),
                   None if phase_rad is None else np.asarray(phase_rad, dtype=float))
    config = TraceConfig(branch_preference=branch_preference,
                         polarity=polarity, max_jump_mhz=max_jump_mhz,
                         min_support_fraction=min_support_fraction)
    trace = extract_step_trace(scan, baseline_ghz=float(baseline_ghz),
                               target_ghz=float(target_ghz), config=config)
    window = (float(time_us[0]), float(time_us[-1])) if solve_window_us is None else solve_window_us
    quality = evaluate_trace_quality(trace, scan, window, config=config)
    return {
        "trace_algorithm_version": __version__,
        "trace_tracking_mode": "consensus_v1",
        "trace_effective_polarity": config.polarity,
        "trace_effective_max_jump_mhz": config.max_jump_mhz,
        "trace_effective_min_support_fraction": config.min_support_fraction,
        "trace_signal_source": trace.signal_source,
        "trace_branch": trace.branch,
        "trace_candidates": trace.candidates,
        "trace_supported": trace.supported,
        "trace_ambiguity": trace.ambiguity,
        "trace_score": trace.score,
        "trace_lower_ghz": trace.lower_ghz,
        "trace_upper_ghz": trace.upper_ghz,
        "trace_quality_accepted": quality.accepted,
        "trace_quality_reasons": quality.reasons,
        "trace_quality_coverage": quality.coverage,
        "trace_quality_max_gap_us": quality.max_unsupported_gap_us,
        "trace_quality_edge_margin_mhz": quality.edge_margin_mhz,
        "extracted_qubit_frequency_ghz": trace.frequency_ghz,
    }
