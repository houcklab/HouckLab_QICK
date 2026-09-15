import json
from pathlib import Path

import numpy as np
from scipy.signal import savgol_filter

from .core import Command, Filter, geometric_schedule, render, render_on_schedule, tail_bound


def flatness(time_ns, frequency_mhz, support, *, smooth_window=17):
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


PREFERRED_SMOOTH_RMS_MHZ = 0.25
PREFERRED_EARLY_MINUS_LATE_MHZ = 0.5
INITIAL_SMOOTH_RMS_MHZ = 0.5
INITIAL_EARLY_MINUS_LATE_MHZ = 1.0
REQUIRED_SUPPORTED_FRACTION = 0.95


def _finite_number(value):
    return value is not None and np.isscalar(value) and np.isfinite(value)


def _threshold_pass(metrics, *, smooth_rms_mhz, early_minus_late_mhz, supported_fraction,
                    required_conditions):
    if len(metrics) != required_conditions:
        return False
    return all(
        _finite_number(m.get('smooth_rms_mhz')) and abs(m['smooth_rms_mhz']) < smooth_rms_mhz
        and _finite_number(m.get('early_minus_late_mhz'))
        and abs(m['early_minus_late_mhz']) < early_minus_late_mhz
        and m.get('supported_fraction', 0.0) >= supported_fraction
        for m in metrics
    )


def acceptance(metrics, *, held_out_supported, required_conditions=3,
               measurement_uncertainty_mhz=None):
    preferred = _threshold_pass(
        metrics, smooth_rms_mhz=PREFERRED_SMOOTH_RMS_MHZ,
        early_minus_late_mhz=PREFERRED_EARLY_MINUS_LATE_MHZ,
        supported_fraction=REQUIRED_SUPPORTED_FRACTION,
        required_conditions=required_conditions)
    initial = _threshold_pass(
        metrics, smooth_rms_mhz=INITIAL_SMOOTH_RMS_MHZ,
        early_minus_late_mhz=INITIAL_EARLY_MINUS_LATE_MHZ,
        supported_fraction=REQUIRED_SUPPORTED_FRACTION,
        required_conditions=required_conditions)
    claimable = None
    if measurement_uncertainty_mhz is not None:
        uncertainty = float(measurement_uncertainty_mhz)
        if not np.isfinite(uncertainty) or uncertainty < 0:
            raise ValueError("measurement_uncertainty_mhz must be a nonnegative finite number")
        claimable = {
            "measurement_uncertainty_mhz": uncertainty,
            "preferred_threshold_resolvable": bool(uncertainty < PREFERRED_SMOOTH_RMS_MHZ),
            "initial_threshold_resolvable": bool(uncertainty < INITIAL_SMOOTH_RMS_MHZ),
        }
    return {"numerical_targets_pass": bool(preferred),
            "preferred_targets_pass": bool(preferred),
            "initial_targets_pass": bool(initial),
            "scientific_gate_pass": bool(initial and held_out_supported),
            "preferred_scientific_gate_pass": bool(preferred and held_out_supported),
            "thresholds": {"preferred_smooth_rms_mhz": PREFERRED_SMOOTH_RMS_MHZ,
                           "preferred_early_minus_late_mhz": PREFERRED_EARLY_MINUS_LATE_MHZ,
                           "initial_smooth_rms_mhz": INITIAL_SMOOTH_RMS_MHZ,
                           "initial_early_minus_late_mhz": INITIAL_EARLY_MINUS_LATE_MHZ,
                           "required_supported_fraction": REQUIRED_SUPPORTED_FRACTION,
                           "required_conditions": int(required_conditions)},
            "uncertainty": claimable,
            "hardware_ready": False,
            "hardware_gate_reason": "Actual controller compilation, dispatch timing and plant validation required"}


def build_shot(model, *, amplitude, hold_ns, recovery_ns, initial_state=None,
               tail_tolerance=1e-5, terminal_park_ns=4000, sample_ns=None, schedule=None):
    if not np.isfinite(tail_tolerance) or tail_tolerance <= 0 or not np.isfinite(terminal_park_ns) or terminal_park_ns <= 0:
        raise ValueError("positive finite tolerance and terminal duration required")
    if schedule is None:
        command, state = render(model, [(amplitude, hold_ns), (0, recovery_ns)],
                                initial_state=initial_state, sample_ns=sample_ns)
    else:
        if sample_ns is not None:
            raise ValueError("pass either a uniform sample_ns or an explicit emission schedule")
        command, state = render_on_schedule(model, schedule, initial_state=initial_state)
        requested = sum(duration for _, duration in schedule)
        if abs(requested - (float(hold_ns)+float(recovery_ns))) > 1e-6:
            raise ValueError("emission schedule duration does not match hold plus recovery")
    bound = tail_bound(state)
    if bound > tail_tolerance:
        raise ValueError(f"return tail {bound:.6g} exceeds tolerance {tail_tolerance:.6g}; extend recovery or carry history")
    terminal = Command(np.r_[command.edges_ns, command.edges_ns[-1]+terminal_park_ns], np.r_[command.values, 0])
    return {"command": terminal, "target_end_ns": float(hold_ns), "terminal_tail_bound": bound,
            "state_at_truncation": state, "tail_tolerance": float(tail_tolerance),
            "terminal_park_ns": float(terminal_park_ns), "hardware_ready": False}


def shot_schedule(*, amplitude, hold_ns, recovery_ns, first_ns, growth=1.35, max_ns=None,
                  quantum_ns=None):
    hold = geometric_schedule(amplitude, hold_ns, first_ns=first_ns, growth=growth,
                              max_ns=max_ns, quantum_ns=quantum_ns)
    recovery = geometric_schedule(0.0, recovery_ns, first_ns=first_ns, growth=growth,
                                  max_ns=max_ns, quantum_ns=quantum_ns)
    return hold + recovery


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
