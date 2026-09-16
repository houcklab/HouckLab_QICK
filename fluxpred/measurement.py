import csv
import json
from pathlib import Path

import numpy as np

from . import cryoscope, schema
from .core import Command
from .fit import Trace

ARM_LABELS = ("g", "e")


def quadrature_labels(window_count):
    return tuple(f"{arm}{index}" for index in range(int(window_count)) for arm in ("i", "q"))


def raw_columns(window_count):
    labels = ARM_LABELS+quadrature_labels(window_count)
    return ("delay_ns",)+tuple(f"p_{name}" for name in labels)+tuple(
        f"keep_{name}" for name in labels)


def analyze(*, delays_ns, p_ground, p_excited, quadratures, windows_ns, probe_frequency_ghz,
            frequency_of_coordinate, park, target, shots, ideal_amplitude=None,
            contrast_threshold=None, min_reference_contrast=0.05, branch_safety=0.5):
    delays_ns = np.asarray(delays_ns, dtype=float)
    windows_ns = [float(value) for value in windows_ns]
    if len(quadratures) != len(windows_ns):
        raise ValueError("one (i, q) population pair is required per probe window")
    threshold = (cryoscope.DEFAULT_CONTRAST_THRESHOLD if contrast_threshold is None
                 else float(contrast_threshold))
    reference_ground = float(np.mean(p_ground))
    reference_excited = float(np.mean(p_excited))
    components, phases, mask = [], [], None
    for p_i, p_q in quadratures:
        x, y = cryoscope.bloch_components(
            p_i, p_q, p_ground=reference_ground, p_excited=reference_excited,
            min_reference_contrast=min_reference_contrast)
        components.append((x, y))
        phases.append(cryoscope.wrapped_phase(x, y))
        rung_mask = cryoscope.support_mask(x, y, threshold=threshold)
        mask = rung_mask if mask is None else (mask & rung_mask)
    resolved = cryoscope.resolve_ladder(phases, windows_ns, mask=mask, safety=branch_safety)
    mask = mask & ~resolved["ambiguous"]
    finest = int(np.argmax(windows_ns))
    x_fine, y_fine = components[finest]
    sigma_phase = cryoscope.phase_uncertainty(
        x_fine, y_fine,
        cryoscope.shot_noise_sigma(quadratures[finest][0], shots),
        cryoscope.shot_noise_sigma(quadratures[finest][1], shots))
    trace = cryoscope.trace_from_measurement(
        delays_ns=delays_ns, phase_rad=resolved["resolved_phase_rad"], mask=mask,
        probe_window_ns=resolved["finest_window_ns"], probe_frequency_ghz=probe_frequency_ghz,
        frequency_of_coordinate=frequency_of_coordinate, park=park, target=target,
        ideal_amplitude=ideal_amplitude, sigma_phase_rad=sigma_phase)
    trace.update({
        "components": components, "phases_rad": phases,
        "contrast": [cryoscope.contrast(x, y) for x, y in components],
        "contrast_fine": cryoscope.contrast(x_fine, y_fine),
        "resolved": resolved, "contrast_threshold": threshold,
        "windows_ns": tuple(windows_ns), "window_fine_ns": resolved["finest_window_ns"],
        "sigma_phase_rad": sigma_phase,
        "reference_ground": reference_ground, "reference_excited": reference_excited,
    })
    return trace


def write_raw_csv(path, *, delays_ns, populations, keep_fractions, window_count):
    path = Path(path)
    labels = ARM_LABELS+quadrature_labels(window_count)
    with open(path, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(raw_columns(window_count))
        for index, delay in enumerate(np.asarray(delays_ns, dtype=float)):
            row = [float(delay)]
            row.extend(float(populations[name][index]) for name in labels)
            row.extend(float(keep_fractions[name][index]) for name in labels)
            writer.writerow(row)
    return path


def read_raw_csv(path):
    table = np.genfromtxt(path, delimiter=",", names=True)
    if table.ndim == 0:
        table = table.reshape(1)
    return {name: np.asarray(table[name], dtype=float) for name in table.dtype.names}


def quadratures_from_raw(raw, window_count):
    pairs = []
    for index in range(int(window_count)):
        pairs.append((raw[f"p_i{index}"], raw[f"p_q{index}"]))
    return pairs


def build_summary(*, device, park, scale, park_coordinate, target_coordinate,
                  normalized_amplitude, delays_ns, windows_ns, shots, rounds, recovery_ns,
                  command, trace, static_flux_model, differentiator, timestamp,
                  controller_commit, code_commit, operator_note, files):
    controller, unit = schema.DEVICES[device]
    document = {
        "schema": schema.MEASUREMENT_SCHEMA,
        "device": device, "controller": controller,
        "coordinate": {"unit": unit, "park": float(park), "scale": float(scale)},
        "sequence": {
            "park_coordinate": float(park_coordinate),
            "target_coordinate": float(target_coordinate),
            "normalized_amplitude": float(normalized_amplitude),
            "delays_ns": [float(value) for value in delays_ns],
            "probe_windows_ns": [float(value) for value in windows_ns],
            "shots_per_point": int(shots), "rounds": int(rounds),
            "recovery_ns": float(recovery_ns),
            "emitted_plan_sha256": schema.sha256_json(command.to_dict()),
        },
        "observable": {
            "quadratures": ["x", "y"],
            "contrast": [float(value) for value in trace["contrast_fine"]],
            "contrast_threshold": float(trace["contrast_threshold"]),
            "supported_fraction": float(trace["supported_fraction"]),
        },
        "analysis": {
            "nominal_phase_model": dict(static_flux_model),
            "unwrap": {"method": "window_ladder",
                       "windows_ns": [float(value) for value in trace["windows_ns"]],
                       "window_fine_ns": float(trace["window_fine_ns"]),
                       "ambiguous_count": int(trace["resolved"]["ambiguous_count"]),
                       "branch_tolerance_mhz": float(trace["resolved"]["branch_tolerance_mhz"])},
            "differentiator": dict(differentiator),
            "detuning_uncertainty_mhz": [float(value) if np.isfinite(value) else None
                                         for value in trace.get("sigma_detuning_mhz", [])],
        },
        "provenance": {"timestamp": str(timestamp), "controller_commit": str(controller_commit),
                       "code_commit": str(code_commit), "operator_note": str(operator_note)},
        "files": {key: {"path": str(value["path"]), "sha256": str(value["sha256"]),
                        "bytes": int(value["bytes"])} for key, value in files.items()},
    }
    schema.validate_measurement_document(document, device=device)
    return document


def describe_file(path):
    path = Path(path)
    return {"path": str(path), "sha256": schema.sha256_file(path), "bytes": path.stat().st_size}


def write_summary(path, document):
    path = Path(path)
    path.write_text(json.dumps(document, indent=2, allow_nan=False)+"\n")
    return path


def read_summary(path, *, device=None, verify_hashes=False, hash_root=None):
    document = schema.read_json(path)
    schema.validate_measurement_document(document, device=device)
    if verify_hashes:
        for key, entry in document["files"].items():
            candidate = Path(entry["path"])
            if hash_root is not None:
                candidate = Path(hash_root)/candidate.name
            if not candidate.exists():
                raise schema.SchemaError(
                    f"measurement file {key!r} is not readable at {str(candidate)!r}")
            actual = schema.sha256_file(candidate)
            if actual != entry["sha256"]:
                raise schema.SchemaError(
                    f"measurement file {key!r} has SHA-256 {actual}, but the summary recorded "
                    f"{entry['sha256']}; the raw measurement changed")
    return document


def trace_from_summary(document, raw, *, frequency_of_coordinate, probe_frequency_ghz,
                       ideal_amplitude=None):
    sequence = document["sequence"]
    windows = sequence["probe_windows_ns"]
    return analyze(
        delays_ns=raw["delay_ns"], p_ground=raw["p_g"], p_excited=raw["p_e"],
        quadratures=quadratures_from_raw(raw, len(windows)), windows_ns=windows,
        probe_frequency_ghz=probe_frequency_ghz,
        frequency_of_coordinate=frequency_of_coordinate,
        park=sequence["park_coordinate"], target=sequence["target_coordinate"],
        shots=sequence["shots_per_point"], ideal_amplitude=ideal_amplitude,
        contrast_threshold=document["observable"]["contrast_threshold"])


def identification_trace(document, trace, command):
    delays = np.asarray(trace["delays_ns"], dtype=float)
    window = float(max(document["sequence"]["probe_windows_ns"]))
    amplitude = float(document["sequence"]["normalized_amplitude"])
    if not np.isfinite(amplitude) or amplitude <= 0:
        raise ValueError("the measurement's normalized amplitude must be positive")
    unit_command = Command(command.edges_ns, np.asarray(command.values, dtype=float)/amplitude)
    response = np.asarray(trace["normalized_amplitude"], dtype=float)/amplitude
    return Trace(delays, response, unit_command, np.asarray(trace["support"], dtype=bool), window)


def write_command_json(path, command):
    path = Path(path)
    path.write_text(json.dumps(command.to_dict(), indent=2, allow_nan=False)+"\n")
    return path


def read_command_json(path):
    document = schema.read_json(path)
    if not isinstance(document, dict) or set(document) != {"edges_ns", "values"}:
        raise schema.SchemaError("a normalized command file needs exactly edges_ns and values")
    return Command(document["edges_ns"], document["values"])


def command_from_summary(document, *, root=None):
    entry = document["files"].get("command_json")
    if entry is None:
        raise schema.SchemaError(
            "the measurement summary does not reference the emitted normalized command; "
            "identification cannot proceed without the exact commanded waveform")
    path = Path(entry["path"])
    if root is not None:
        path = Path(root)/path.name
    command = read_command_json(path)
    recorded = document["sequence"]["emitted_plan_sha256"]
    actual = schema.sha256_json(command.to_dict())
    if actual != recorded:
        raise schema.SchemaError(
            f"the normalized command at {str(path)!r} hashes to {actual}, but the summary "
            f"recorded {recorded}")
    return command
