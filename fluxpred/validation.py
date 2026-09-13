"""Offline flatness gates and explicit finite-horizon shot preparation."""

import json
from pathlib import Path

import numpy as np
from scipy.signal import savgol_filter

from .core import Command, Filter, render, tail_bound


def flatness(time_ns, frequency_mhz, support, *, smooth_window=17):
    """Smooth RMS about late mean; early <=21us minus late >=300us.

    Smoothing is applied once to raw estimates when requested. A saved smoothed
    trace must use smooth_window=1. Filled gaps serve only the smoothing
    operator and are excluded from all reported metrics. No noise-CI claim.
    """
    t, f, mask = np.asarray(time_ns, float), np.asarray(frequency_mhz, float), np.asarray(support, bool)
    if t.ndim != 1 or t.shape != f.shape or t.shape != mask.shape or np.any(~np.isfinite(t)) or np.any(np.diff(t) <= 0):
        raise ValueError("invalid metric arrays")
    valid = mask & np.isfinite(f)
    early, late = valid & (t <= 21000), valid & (t >= 300000)
    if np.count_nonzero(early) < 3 or np.count_nonzero(late) < 3:
        raise ValueError("insufficient supported early/late samples")
    if type(smooth_window) is not int or smooth_window < 1 or smooth_window % 2 == 0 or smooth_window > len(t):
        raise ValueError("invalid smoothing window")
    filled = np.interp(t, t[valid], f[valid])
    if smooth_window > 1:
        if smooth_window < 5 or not np.allclose(np.diff(t), np.diff(t)[0]):
            raise ValueError("Savitzky-Golay requires a uniform grid and window >=5")
        smooth = savgol_filter(filled, smooth_window, 2)
    else:
        smooth = filled
    reference = float(np.mean(smooth[late]))
    return {"smooth_rms_mhz": float(np.sqrt(np.mean((smooth[valid]-reference)**2))),
            "early_minus_late_mhz": float(np.mean(smooth[early])-reference),
            "raw_rms_mhz": float(np.sqrt(np.mean((f[valid]-np.mean(f[late]))**2))),
            "supported_fraction": float(np.mean(valid)),
            "smooth_window": smooth_window, "early_stop_ns": 21000, "late_start_ns": 300000}


def acceptance(metrics, *, held_out_supported):
    numerical = len(metrics) == 3 and all(np.isfinite(m['smooth_rms_mhz']) and m['smooth_rms_mhz'] < .25
        and np.isfinite(m['early_minus_late_mhz']) and abs(m['early_minus_late_mhz']) < .5
        and m['supported_fraction'] >= .95 for m in metrics)
    return {"numerical_targets_pass": bool(numerical),
            "scientific_gate_pass": bool(numerical and held_out_supported),
            "hardware_ready": False,
            "hardware_gate_reason": "Actual controller compilation, dispatch timing and plant validation required"}


def build_shot(model, *, amplitude, hold_ns, recovery_ns, initial_state=None,
               tail_tolerance=1e-5, terminal_park_ns=4000, sample_ns=None):
    """Target-return command anchored AFTER reset/align at park.

    Finite recovery leaves an explicit bounded INVERSE COMMAND truncation
    error. This is not a physical plant-settling bound. A terminal
    park plateau prevents stdysel/DC latch from retaining a nonzero correction.
    Never use an arbitrary 40-us recovery and then silently discard the tail.
    To model incomplete settling or variable reset dwell, propagate render's
    state during that dwell and supply it here. Hardware reset durations must
    be bounded/padded or handled at runtime; this is a static schedule builder.
    """
    if not np.isfinite(tail_tolerance) or tail_tolerance <= 0 or not np.isfinite(terminal_park_ns) or terminal_park_ns <= 0:
        raise ValueError("positive finite tolerance and terminal duration required")
    command, state = render(model, [(amplitude, hold_ns), (0, recovery_ns)], initial_state=initial_state, sample_ns=sample_ns)
    bound = tail_bound(state)
    if bound > tail_tolerance:
        raise ValueError(f"return tail {bound:.6g} exceeds tolerance {tail_tolerance:.6g}; extend recovery or carry history")
    terminal = Command(np.r_[command.edges_ns, command.edges_ns[-1]+terminal_park_ns], np.r_[command.values, 0])
    return {"command": terminal, "target_end_ns": float(hold_ns), "terminal_tail_bound": bound,
            "state_at_truncation": state, "tail_tolerance": float(tail_tolerance),
            "terminal_park_ns": float(terminal_park_ns), "hardware_ready": False}


def load_candidate(path, *, park, scale, unit, require_scientific_gate=False):
    doc = json.loads(Path(path).read_text(), parse_constant=lambda x: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
    if not isinstance(doc, dict) or set(doc) != {"schema_version", "model", "coordinate", "evidence"} or type(doc["schema_version"]) is not int or doc["schema_version"] != 1:
        raise ValueError("unsupported candidate schema")
    coord = doc['coordinate']
    if not isinstance(coord, dict) or set(coord) != {"park", "scale", "unit"}:
        raise ValueError("invalid coordinate schema")
    for value in (park, scale, coord['park'], coord['scale']):
        if not np.isfinite(value):
            raise ValueError("nonfinite coordinate")
    if scale == 0 or abs(coord['park']-park) > 1e-9 or abs(coord['scale']-scale) > 1e-9 or coord['unit'] != unit:
        raise ValueError("candidate coordinate does not match calibration")
    evidence = doc['evidence']
    if not isinstance(evidence, dict) or type(evidence.get('scientific_gate_pass')) is not bool or type(evidence.get('hardware_ready')) is not bool:
        raise ValueError("candidate evidence schema missing gate booleans")
    if require_scientific_gate and not evidence['scientific_gate_pass']:
        raise ValueError("candidate scientific acceptance gate failed")
    return Filter.from_dict(doc['model']), doc
