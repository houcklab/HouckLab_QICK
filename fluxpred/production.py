import os
import copy
from pathlib import Path

import numpy as np

from . import report, schema
from .core import Command, geometric_schedule, render_on_schedule, tail_bound
from .validation import shot_schedule

MODES = ("off", "neutral")
ENV_PREFIX = {"q3": "Q3_FLUXPRED", "q5": "Q5_FLUXPRED"}


def timing_matched_unity(compensation):
    """Remove correction amplitude while preserving every lifecycle edge."""
    result = copy.deepcopy(compensation)
    result["multipliers"] = [1.0] * len(result.get("multipliers", ()))
    for condition in result.get("lifecycle_conditions", ()):
        hold_ns = float(condition["hold_ns"])
        edges = [float(value) for value in condition["edges_ns"]]
        condition["values"] = [
            1.0 if start < hold_ns - 1e-9 else 0.0
            for start in edges[:-1]
        ]
        condition["terminal_tail_bound"] = 0.0
    return result


def scale_lifecycle_recovery(compensation, scale):
    """Scale only the post-return portion of exact lifecycle commands."""
    scale = float(scale)
    if not np.isfinite(scale) or not 0.0 <= scale <= 1.0:
        raise ValueError("recovery scale must be finite and between zero and one")
    result = copy.deepcopy(compensation)
    conditions = result.get("lifecycle_conditions")
    if not conditions:
        raise ValueError("recovery scaling requires exact lifecycle conditions")
    for condition in conditions:
        hold_ns = float(condition["hold_ns"])
        edges = [float(value) for value in condition["edges_ns"]]
        if not any(abs(edge - hold_ns) <= 1e-9 for edge in edges):
            raise ValueError("lifecycle condition does not contain its return edge")
        condition["values"] = [
            float(value) if start < hold_ns - 1e-9 else scale * float(value)
            for start, value in zip(edges[:-1], condition["values"])
        ]
        condition["terminal_tail_bound"] = (
            scale * float(condition.get("terminal_tail_bound", 0.0))
        )
        condition["recovery_scale"] = scale
    result["recovery_scale"] = scale
    return result


def _env(device, name, environ):
    return str(environ.get(f"{ENV_PREFIX[device]}_{name}", "")).strip()


def _flag(value):
    return value.lower() in {"1", "true", "yes", "on"}


def resolve_mode(device, environ=None):
    environ = os.environ if environ is None else environ
    mode = _env(device, "MODE", environ).lower() or "off"
    if mode not in MODES:
        raise ValueError(
            f"{ENV_PREFIX[device]}_MODE must be one of {MODES}, got {mode!r}; the long scan "
            f"defaults to 'off' when nothing is set")
    return mode


def selection(device, *, park, scale, environ=None, amplitude_range=None):
    environ = os.environ if environ is None else environ
    mode = resolve_mode(device, environ)
    if mode == "off":
        return {"device": device, "mode": "off", "model": None, "document": None,
                "model_path": None, "model_sha256": None, "diagnostic_override": False,
                "reason": "no correction requested"}
    path = _env(device, "MODEL_JSON", environ)
    if not path:
        raise ValueError(
            f"{ENV_PREFIX[device]}_MODE=neutral requires {ENV_PREFIX[device]}_MODEL_JSON; "
            f"selecting the latest JSON automatically is not permitted")
    override = _flag(_env(device, "DIAGNOSTIC_OVERRIDE", environ))
    model, document = schema.load_model(
        path, device=device, park=park, scale=scale, require_scientific=True,
        diagnostic_override=override, verify_hashes=False, amplitude_range=amplitude_range)
    return {"device": device, "mode": "neutral", "model": model, "document": document,
            "model_path": str(Path(path)), "model_sha256": schema.sha256_file(path),
            "diagnostic_override": override,
            "reason": "explicit diagnostic override" if override else "accepted candidate"}


def describe(choice):
    lines = [f"[fluxpred] device={choice['device']} mode={choice['mode']}"]
    if choice["mode"] == "off":
        lines.append("[fluxpred] no software flux correction is applied to this run")
        return lines
    document = choice["document"]
    coordinate = document["coordinate"]
    calibration = document["calibration"]
    body = document["model"]
    lines.append(f"[fluxpred] model      {choice['model_path']}")
    lines.append(f"[fluxpred] sha256     {choice['model_sha256']}")
    lines.append(f"[fluxpred] schema     {document['schema']}")
    lines.append(f"[fluxpred] coordinate unit={coordinate['unit']} park={coordinate['park']!r} "
                 f"scale={coordinate['scale']!r}")
    lines.append(f"[fluxpred] taus_us    {body['taus_us']}")
    lines.append(f"[fluxpred] coeffs     {body['coefficients']}")
    lines.append(f"[fluxpred] method     {calibration['method']}")
    lines.append(f"[fluxpred] sources    {len(calibration['source_files'])} raw file(s), "
                 f"first={calibration['source_files'][0] if calibration['source_files'] else 'none'}")
    lines.append(f"[fluxpred] acceptance {document['acceptance']}")
    if choice["diagnostic_override"]:
        lines.append("[fluxpred] WARNING running an unaccepted candidate under an explicit "
                     "diagnostic override; this is not a production-validated correction")
    return lines


def condition_commands(choice, *, amplitude, holds_ns, recovery_ns, schedule_first_ns,
                       schedule_growth, schedule_max_ns, quantum_ns, tail_tolerance=1e-5,
                       terminal_park_ns=4000.0):
    if choice["mode"] == "off":
        return [{"hold_ns": float(hold), "command": Command(
            [0.0, float(hold), float(hold)+float(recovery_ns)], [float(amplitude), 0.0]),
            "terminal_tail_bound": 0.0, "state_at_truncation": np.zeros(0)}
            for hold in holds_ns]
    return report.condition_bank(
        choice["model"], amplitude=amplitude, holds_ns=holds_ns, recovery_ns=recovery_ns,
        tail_tolerance=tail_tolerance, terminal_park_ns=terminal_park_ns,
        schedule_first_ns=schedule_first_ns, schedule_growth=schedule_growth,
        schedule_max_ns=schedule_max_ns, schedule_quantum_ns=quantum_ns)


def neutral_step_table(choice, *, max_hold_ns, recovery_ns, schedule_first_ns,
                       schedule_growth, schedule_max_ns, quantum_ns):
    """Render one normalized neutral step for the existing stateful scheduler.

    The QICK round-trip implementation already constructs the return command as
    ``m(hold + recovery) - m(recovery)``.  Supplying the unit-step table here
    therefore preserves the same causal superposition used by the controller-
    neutral model instead of baking one particular hold time into the JSON.
    """
    if choice.get("mode") != "neutral" or choice.get("model") is None:
        raise ValueError("neutral_step_table requires a selected neutral model")
    max_hold_ns = float(max_hold_ns)
    recovery_ns = float(recovery_ns)
    if not np.isfinite(max_hold_ns) or max_hold_ns <= 0.0:
        raise ValueError("max_hold_ns must be finite and positive")
    if not np.isfinite(recovery_ns) or recovery_ns <= 0.0:
        raise ValueError("recovery_ns must be finite and positive")
    horizon_ns = max_hold_ns + recovery_ns
    schedule = geometric_schedule(
        1.0, horizon_ns, first_ns=float(schedule_first_ns),
        growth=float(schedule_growth), max_ns=float(schedule_max_ns),
        quantum_ns=float(quantum_ns))
    command, _ = render_on_schedule(choice["model"], schedule)
    return {
        "enabled": True,
        "method": "neutral_parallel_highpass_inverse_v1",
        "source": str(choice["model_path"]),
        "model_sha256": str(choice["model_sha256"]),
        "segment_edges_ns": [*command.edges_ns[:-1].tolist(), command.edges_ns[-1]],
        "multipliers": [*command.values.tolist(), 1.0],
    }


def neutral_lifecycle_table(choice, *, holds_ns, recovery_ns, schedule_first_ns,
                            schedule_growth, schedule_max_ns, quantum_ns):
    """Render an exact finite-horizon command for every production hold."""
    if choice.get("mode") != "neutral" or choice.get("model") is None:
        raise ValueError("neutral_lifecycle_table requires a selected neutral model")
    holds = tuple(float(value) for value in holds_ns)
    recovery_ns = float(recovery_ns)
    if not holds or any(not np.isfinite(value) or value <= 0.0 for value in holds):
        raise ValueError("holds_ns must contain positive finite durations")
    if not np.isfinite(recovery_ns) or recovery_ns <= 0.0:
        raise ValueError("recovery_ns must be finite and positive")
    fallback = neutral_step_table(
        choice, max_hold_ns=max(holds), recovery_ns=recovery_ns,
        schedule_first_ns=schedule_first_ns, schedule_growth=schedule_growth,
        schedule_max_ns=schedule_max_ns, quantum_ns=quantum_ns)
    conditions = []
    for hold_ns in holds:
        schedule = shot_schedule(
            amplitude=1.0, hold_ns=hold_ns, recovery_ns=recovery_ns,
            first_ns=schedule_first_ns, growth=schedule_growth,
            max_ns=schedule_max_ns, quantum_ns=quantum_ns)
        command, state = render_on_schedule(choice["model"], schedule)
        conditions.append({
            "hold_ns": hold_ns,
            "edges_ns": command.edges_ns.tolist(),
            "values": command.values.tolist(),
            "terminal_tail_bound": tail_bound(state),
        })
    return {
        **fallback,
        "method": "neutral_condition_lifecycle_v1",
        "preserve_timing_segments": True,
        "recovery_ns": recovery_ns,
        "schedule_first_ns": float(schedule_first_ns),
        "lifecycle_conditions": conditions,
    }


def provenance(choice, *, bank=None, backend=None, backend_report=None, code_commit=None):
    record = {"correction_mode": choice["mode"],
              "model_path": choice["model_path"],
              "model_sha256": choice["model_sha256"],
              "diagnostic_override": bool(choice["diagnostic_override"]),
              "controller_code_commit": str(code_commit) if code_commit else "unknown",
              "backend": backend}
    if choice["document"] is not None:
        document = choice["document"]
        record.update({
            "schema": document["schema"],
            "coordinate": dict(document["coordinate"]),
            "taus_us": list(document["model"]["taus_us"]),
            "coefficients": document["model"]["coefficients"],
            "calibration_method": document["calibration"]["method"],
            "calibration_sources": list(document["calibration"]["source_files"]),
            "acceptance": dict(document["acceptance"]),
        })
    if bank is not None:
        record["conditions"] = [
            {"hold_ns": float(entry["hold_ns"]),
             "command_sha256": report.command_hash(entry["command"]),
             "terminal_tail_bound": float(entry["terminal_tail_bound"]),
             "segments": int(len(entry["command"].values)),
             "max_abs_normalized": float(np.max(np.abs(entry["command"].values)))}
            for entry in bank]
        record["plan_sha256"] = schema.sha256_json(
            [condition["command_sha256"] for condition in record["conditions"]])
    if backend_report is not None:
        record["backend_report"] = backend_report
    return record


def production_schedule(*, amplitude, hold_ns, recovery_ns, first_ns, growth, max_ns, quantum_ns):
    return shot_schedule(amplitude=amplitude, hold_ns=hold_ns, recovery_ns=recovery_ns,
                         first_ns=first_ns, growth=growth, max_ns=max_ns, quantum_ns=quantum_ns)
