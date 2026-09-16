import hashlib
import json
import math
from pathlib import Path

import numpy as np

from .core import ALGORITHM, Filter

MODEL_SCHEMA = "houcklab.fluxpred.model.v1"
MEASUREMENT_SCHEMA = "houcklab.fluxpred.measurement.v1"
MODEL_TYPE = "parallel_highpass_inverse"
CALIBRATION_METHOD = "ramsey_cryoscope_xy"

DEVICES = {"q3": ("QICK", "DAC_gain"), "q5": ("QUA", "V")}
GATES = ("software", "scientific", "hardware")

MODEL_KEYS = {"schema", "device", "controller", "coordinate", "model", "calibration", "acceptance"}
COORDINATE_KEYS = {"unit", "park", "scale"}
MODEL_BODY_KEYS = {"type", "taus_us", "coefficients", "dc_gain"}
MODEL_BODY_OPTIONAL = {"amplitudes", "resolution_us", "max_l1"}
CALIBRATION_KEYS = {"method", "source_files", "source_sha256", "static_flux_model",
                    "fit_settings", "cross_validation"}

MEASUREMENT_KEYS = {"schema", "device", "controller", "coordinate", "sequence", "observable",
                    "analysis", "provenance", "files"}
SEQUENCE_KEYS = {"park_coordinate", "target_coordinate", "normalized_amplitude", "delays_ns",
                 "probe_windows_ns", "shots_per_point", "rounds", "recovery_ns", "emitted_plan_sha256"}
OBSERVABLE_KEYS = {"quadratures", "contrast", "contrast_threshold", "supported_fraction"}
ANALYSIS_KEYS = {"nominal_phase_model", "unwrap", "differentiator", "detuning_uncertainty_mhz"}
PROVENANCE_KEYS = {"timestamp", "controller_commit", "code_commit", "operator_note"}


class SchemaError(ValueError):
    pass


def basename(value):
    return str(value).replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]


def resolve_against(value, root):
    return Path(value) if root is None else Path(root)/basename(value)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(value):
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _reject_nonfinite(value):
    raise SchemaError(f"nonfinite JSON literal {value!r} is not allowed in a fluxpred document")


def read_json(path):
    text = Path(path).read_text()
    return json.loads(text, parse_constant=_reject_nonfinite)


def _require(condition, message):
    if not condition:
        raise SchemaError(message)


def _exact_keys(document, keys, label, optional=frozenset()):
    _require(isinstance(document, dict), f"{label} must be a JSON object")
    present = set(document)
    missing = keys - present
    extra = present - keys - set(optional)
    _require(not missing, f"{label} is missing required field(s): {sorted(missing)}")
    _require(not extra, f"{label} has unsupported field(s): {sorted(extra)}")


def _finite_vector(value, label):
    array = np.asarray(value, dtype=float)
    _require(array.ndim == 1 and array.size > 0, f"{label} must be a nonempty one-dimensional list")
    _require(bool(np.all(np.isfinite(array))), f"{label} must contain only finite numbers")
    return array


def _finite_scalar(value, label):
    _require(isinstance(value, (int, float)) and not isinstance(value, bool),
             f"{label} must be a JSON number")
    _require(math.isfinite(float(value)), f"{label} must be finite")
    return float(value)


def validate_model_document(document, *, device=None, unit=None, park=None, scale=None,
                            coordinate_tolerance=1e-9):
    _exact_keys(document, MODEL_KEYS, "model document")
    _require(document["schema"] == MODEL_SCHEMA,
             f"unsupported model schema {document['schema']!r}; expected {MODEL_SCHEMA!r}")
    named = document["device"]
    _require(named in DEVICES, f"unknown device {named!r}; expected one of {sorted(DEVICES)}")
    expected_controller, expected_unit = DEVICES[named]
    _require(document["controller"] == expected_controller,
             f"device {named} is a {expected_controller} device, not {document['controller']!r}")
    if device is not None:
        _require(named == device, f"model is for device {named!r}, but {device!r} was requested")

    coordinate = document["coordinate"]
    _exact_keys(coordinate, COORDINATE_KEYS, "model coordinate")
    _require(coordinate["unit"] == expected_unit,
             f"device {named} uses coordinate unit {expected_unit!r}, not {coordinate['unit']!r}")
    if unit is not None:
        _require(coordinate["unit"] == unit,
                 f"model coordinate unit {coordinate['unit']!r} does not match requested {unit!r}")
    model_park = _finite_scalar(coordinate["park"], "coordinate.park")
    model_scale = _finite_scalar(coordinate["scale"], "coordinate.scale")
    _require(model_scale != 0.0, "coordinate.scale must be nonzero")
    if park is not None:
        _require(abs(model_park - float(park)) <= coordinate_tolerance,
                 f"model park {model_park!r} does not match the calibrated park {float(park)!r}")
    if scale is not None:
        _require(abs(model_scale - float(scale)) <= coordinate_tolerance,
                 f"model scale {model_scale!r} does not match the calibrated scale {float(scale)!r}")

    body = document["model"]
    _exact_keys(body, MODEL_BODY_KEYS, "model body", optional=MODEL_BODY_OPTIONAL)
    _require(body["type"] == MODEL_TYPE,
             f"unsupported model type {body['type']!r}; expected {MODEL_TYPE!r}")
    _require(_finite_scalar(body["dc_gain"], "model.dc_gain") == 1.0,
             "model.dc_gain must be exactly 1.0; this inverse class has unity DC gain by construction")
    taus_us = _finite_vector(body["taus_us"], "model.taus_us")
    _require(bool(np.all(taus_us > 0)), "model.taus_us must all be strictly positive")
    _require(bool(np.all(np.diff(taus_us) > 0)), "model.taus_us must be strictly increasing")

    coefficients = np.asarray(body["coefficients"], dtype=float)
    _require(bool(np.all(np.isfinite(coefficients))), "model.coefficients must be finite")
    if coefficients.ndim == 1:
        _require("amplitudes" not in body,
                 "one-dimensional model.coefficients describes an LTI model and must omit amplitudes")
        amplitudes = np.array([1.0])
        coefficients = coefficients[None, :]
    else:
        _require(coefficients.ndim == 2, "model.coefficients must be one- or two-dimensional")
        _require("amplitudes" in body,
                 "two-dimensional model.coefficients requires a matching model.amplitudes list")
        amplitudes = _finite_vector(body["amplitudes"], "model.amplitudes")
    _require(coefficients.shape == (amplitudes.size, taus_us.size),
             f"model.coefficients shape {coefficients.shape} does not match "
             f"({amplitudes.size} amplitudes, {taus_us.size} taus)")

    max_l1 = _finite_scalar(body.get("max_l1", 0.25), "model.max_l1")
    resolution_us = _finite_scalar(body.get("resolution_us", 4.0), "model.resolution_us")
    try:
        model = Filter(taus_us * 1000.0, amplitudes, coefficients,
                       resolution_ns=resolution_us * 1000.0, max_l1=max_l1)
    except ValueError as error:
        raise SchemaError(f"model rejected by the shared inverse core: {error}") from error

    calibration = document["calibration"]
    _exact_keys(calibration, CALIBRATION_KEYS, "model calibration")
    _require(calibration["method"] == CALIBRATION_METHOD,
             f"calibration.method must be {CALIBRATION_METHOD!r}; ridge-derived models are not accepted "
             f"by this loader")
    files = calibration["source_files"]
    hashes = calibration["source_sha256"]
    _require(isinstance(files, list) and isinstance(hashes, list),
             "calibration.source_files and calibration.source_sha256 must be lists")
    _require(len(files) > 0, "calibration.source_files must name at least one immutable raw measurement")
    _require(len(files) == len(hashes),
             f"calibration provenance mismatch: {len(files)} source files but {len(hashes)} hashes")
    for entry in hashes:
        _require(isinstance(entry, str) and len(entry) == 64 and all(c in "0123456789abcdef" for c in entry),
                 f"calibration.source_sha256 entry {entry!r} is not a lowercase hex SHA-256 digest")

    acceptance = document["acceptance"]
    _exact_keys(acceptance, set(GATES), "model acceptance")
    for gate in GATES:
        _require(isinstance(acceptance[gate], bool),
                 f"acceptance.{gate} must be a JSON boolean, not {acceptance[gate]!r}")
    return model


def verify_source_hashes(document, *, root=None, missing_ok=False):
    calibration = document["calibration"]
    report = []
    for name, expected in zip(calibration["source_files"], calibration["source_sha256"]):
        path = resolve_against(name, root)
        if not path.exists():
            _require(missing_ok, f"calibration source file {str(path)!r} is not readable for hash verification")
            report.append({"path": str(path), "status": "missing", "expected_sha256": expected})
            continue
        actual = sha256_file(path)
        _require(actual == expected,
                 f"calibration source file {str(path)!r} has SHA-256 {actual}, but the model "
                 f"recorded {expected}; the raw measurement changed or the wrong file is present")
        report.append({"path": str(path), "status": "verified", "expected_sha256": expected,
                       "bytes": path.stat().st_size})
    return report


def load_model(path, *, device, park, scale, require_scientific=True, require_hardware=False,
               diagnostic_override=False, verify_hashes=False, hash_root=None,
               amplitude_range=None):
    document = read_json(path)
    unit = DEVICES[device][1] if device in DEVICES else None
    model = validate_model_document(document, device=device, unit=unit, park=park, scale=scale)
    acceptance = document["acceptance"]
    if amplitude_range is not None:
        low, high = (float(value) for value in amplitude_range)
        _require(low >= 0.0, "requested amplitude range must start at or above zero")
        _require(high <= float(model.amplitudes[-1]) + 1e-12,
                 f"requested normalized amplitude {high!r} is outside the calibrated model range "
                 f"[0, {float(model.amplitudes[-1])!r}]; extrapolation is refused")
    if not diagnostic_override:
        if require_scientific:
            _require(acceptance["scientific"],
                     f"model {str(path)!r} has acceptance.scientific=false; pass an explicit diagnostic "
                     f"override to use an unvalidated candidate")
        if require_hardware:
            _require(acceptance["hardware"],
                     f"model {str(path)!r} has acceptance.hardware=false; pass an explicit diagnostic "
                     f"override to use an unvalidated candidate")
    if verify_hashes:
        document = dict(document)
        document["_hash_report"] = verify_source_hashes(document, root=hash_root)
    return model, document


def build_model_document(*, device, park, scale, taus_us, coefficients, amplitudes=None,
                         source_files=(), source_sha256=(), static_flux_model=None,
                         fit_settings=None, cross_validation=None, acceptance=None,
                         resolution_us=None, max_l1=None):
    controller, unit = DEVICES[device]
    body = {"type": MODEL_TYPE,
            "taus_us": [float(value) for value in taus_us],
            "coefficients": np.asarray(coefficients, dtype=float).tolist(),
            "dc_gain": 1.0}
    if amplitudes is not None:
        body["amplitudes"] = [float(value) for value in amplitudes]
    if resolution_us is not None:
        body["resolution_us"] = float(resolution_us)
    if max_l1 is not None:
        body["max_l1"] = float(max_l1)
    gates = {gate: False for gate in GATES}
    gates.update(acceptance or {})
    document = {
        "schema": MODEL_SCHEMA,
        "device": device,
        "controller": controller,
        "coordinate": {"unit": unit, "park": float(park), "scale": float(scale)},
        "model": body,
        "calibration": {
            "method": CALIBRATION_METHOD,
            "source_files": [str(value) for value in source_files],
            "source_sha256": [str(value) for value in source_sha256],
            "static_flux_model": dict(static_flux_model or {}),
            "fit_settings": dict(fit_settings or {}),
            "cross_validation": dict(cross_validation or {}),
        },
        "acceptance": {gate: bool(gates[gate]) for gate in GATES},
    }
    validate_model_document(document)
    return document


def validate_measurement_document(document, *, device=None):
    _exact_keys(document, MEASUREMENT_KEYS, "measurement document")
    _require(document["schema"] == MEASUREMENT_SCHEMA,
             f"unsupported measurement schema {document['schema']!r}; expected {MEASUREMENT_SCHEMA!r}")
    named = document["device"]
    _require(named in DEVICES, f"unknown device {named!r}")
    expected_controller, expected_unit = DEVICES[named]
    _require(document["controller"] == expected_controller,
             f"device {named} is a {expected_controller} device, not {document['controller']!r}")
    if device is not None:
        _require(named == device, f"measurement is for device {named!r}, but {device!r} was requested")
    coordinate = document["coordinate"]
    _exact_keys(coordinate, COORDINATE_KEYS, "measurement coordinate")
    _require(coordinate["unit"] == expected_unit,
             f"device {named} uses coordinate unit {expected_unit!r}, not {coordinate['unit']!r}")
    _finite_scalar(coordinate["park"], "coordinate.park")
    _require(_finite_scalar(coordinate["scale"], "coordinate.scale") != 0.0,
             "coordinate.scale must be nonzero")

    sequence = document["sequence"]
    _exact_keys(sequence, SEQUENCE_KEYS, "measurement sequence")
    delays = _finite_vector(sequence["delays_ns"], "sequence.delays_ns")
    _require(bool(np.all(delays >= 0)), "sequence.delays_ns must be nonnegative")
    _require(bool(np.all(np.diff(delays) > 0)), "sequence.delays_ns must be strictly increasing")
    windows = _finite_vector(sequence["probe_windows_ns"], "sequence.probe_windows_ns")
    _require(bool(np.all(windows > 0)), "sequence.probe_windows_ns must be strictly positive")
    amplitude = _finite_scalar(sequence["normalized_amplitude"], "sequence.normalized_amplitude")
    _require(0.0 < amplitude <= 1.0, "sequence.normalized_amplitude must be in (0, 1]")
    _finite_scalar(sequence["park_coordinate"], "sequence.park_coordinate")
    _finite_scalar(sequence["target_coordinate"], "sequence.target_coordinate")
    _finite_scalar(sequence["recovery_ns"], "sequence.recovery_ns")
    shots = sequence["shots_per_point"]
    _require(isinstance(shots, int) and not isinstance(shots, bool) and shots > 0,
             "sequence.shots_per_point must be a positive integer")

    observable = document["observable"]
    _exact_keys(observable, OBSERVABLE_KEYS, "measurement observable")
    _require(observable["quadratures"] == ["x", "y"],
             "measurement observable.quadratures must be exactly ['x', 'y']")
    analysis = document["analysis"]
    _exact_keys(analysis, ANALYSIS_KEYS, "measurement analysis")
    provenance = document["provenance"]
    _exact_keys(provenance, PROVENANCE_KEYS, "measurement provenance")
    files = document["files"]
    _require(isinstance(files, dict) and files, "measurement files must be a nonempty object")
    for key, entry in files.items():
        _exact_keys(entry, {"path", "sha256", "bytes"}, f"measurement files[{key!r}]")
    return document
