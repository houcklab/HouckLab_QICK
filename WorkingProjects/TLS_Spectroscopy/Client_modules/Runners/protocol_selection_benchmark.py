"""Canonical, hardware-free plan for the QICK protocol-selection benchmark."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import csv
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping, Sequence

import numpy as np


_SCHEMA = "houcklab.protocol-selection-benchmark.v1"
_MANIFEST_SCHEMA = "houcklab.protocol-selection-benchmark.manifest.v1"
_PROTOCOL_DELAYS_US = {
    "3pt_ts50": (50.0,),
    "3pt_ts100": (100.0,),
    "5pt": (40.0, 80.0, 200.0),
    "7pt": (40.0, 80.0, 120.0, 160.0, 200.0),
}
_LOW_COST_OVERLAY_CONDITIONS = {
    ("3pt_ts100", 300, 3),
    ("5pt", 180, 5),
    ("7pt", 128, 7),
}

PASS_ROW_COLUMNS = (
    "pass_index", "pass_id", "protocol", "predistortion",
    "shots_per_condition", "condition_count", "target_frequency_ghz",
    "realized_frequency_ghz", "flux_coordinate", "gamma1_per_us",
    "gamma1_err_per_us", "t1_us", "t1_err_us", "valid",
    "reference_contrast", "fit_success", "fit_deviance",
    "scan_direction_delta", "requested_flux_coordinate",
    "realized_flux_coordinate", "delays_us", "pass_started_at",
    "pass_ended_at", "normalization_denominator", "residual_deviance",
    "non_exponential_diagnostic",
)
SUMMARY_COLUMNS = (
    "pass_index", "pass_id", "protocol", "predistortion",
    "shots_per_condition", "condition_count", "valid_fraction",
    "longest_invalid_run", "median_reference_contrast",
    "uncertainty_available_fraction", "median_gamma1_err_per_us",
    "p90_gamma1_err_per_us",
    "median_abs_direction_delta", "median_fit_deviance",
    "median_local_roughness", "duration_s",
)


@dataclass(frozen=True)
class BenchmarkPass:
    index: int
    protocol: str
    delays_us: tuple[float, ...]
    shots_per_condition: int
    condition_count: int
    predistortion: str
    role: str = "primary"

    @property
    def pass_id(self) -> str:
        base = (
            f"p{self.index:02d}_{self.protocol}_"
            f"{self.shots_per_condition}_{self.predistortion}"
        )
        return base + ("_sentinel" if self.role == "drift_sentinel" else "")


@dataclass(frozen=True)
class BenchmarkPlan:
    schema: str
    frequency_start_ghz: float
    frequency_stop_ghz: float
    frequency_step_mhz: float
    frequency_count: int
    reset_mode: str
    readout_location: str
    calibration_policy: str
    passes: tuple[BenchmarkPass, ...]
    mode: str = "full"


def _pass(
    index: int,
    protocol: str,
    shots_per_condition: int,
    predistortion: str,
    role: str = "primary",
) -> BenchmarkPass:
    delays_us = _PROTOCOL_DELAYS_US[protocol]
    return BenchmarkPass(
        index=index,
        protocol=protocol,
        delays_us=delays_us,
        shots_per_condition=shots_per_condition,
        condition_count=2 + len(delays_us),
        predistortion=predistortion,
        role=role,
    )


def full_plan() -> BenchmarkPlan:
    """Return the approved, ordered 17-pass hardware-independent plan."""
    return BenchmarkPlan(
        schema=_SCHEMA,
        frequency_start_ghz=4.3,
        frequency_stop_ghz=3.9,
        frequency_step_mhz=0.5,
        frequency_count=801,
        reset_mode="active",
        readout_location="park",
        calibration_policy="once",
        passes=(
            _pass(0, "3pt_ts100", 300, "off", "primary_and_anchor"),
            _pass(1, "3pt_ts100", 300, "on"),
            _pass(2, "3pt_ts100", 500, "on"),
            _pass(3, "3pt_ts100", 500, "off"),
            _pass(4, "3pt_ts50", 300, "off"),
            _pass(5, "3pt_ts50", 300, "on"),
            _pass(6, "3pt_ts50", 500, "on"),
            _pass(7, "3pt_ts50", 500, "off"),
            _pass(8, "5pt", 180, "off"),
            _pass(9, "5pt", 180, "on"),
            _pass(10, "5pt", 300, "on"),
            _pass(11, "5pt", 300, "off"),
            _pass(12, "7pt", 128, "off"),
            _pass(13, "7pt", 128, "on"),
            _pass(14, "7pt", 214, "on"),
            _pass(15, "7pt", 214, "off"),
            _pass(16, "3pt_ts100", 300, "off", "drift_sentinel"),
        ),
    )


def smoke_plan() -> BenchmarkPlan:
    """Return a short, distinct plan covering every protocol and mode."""
    return BenchmarkPlan(
        schema=_SCHEMA,
        frequency_start_ghz=4.3,
        frequency_stop_ghz=4.295,
        frequency_step_mhz=0.5,
        frequency_count=11,
        reset_mode="active",
        readout_location="park",
        calibration_policy="once",
        passes=(
            _pass(0, "3pt_ts100", 4, "off"),
            _pass(1, "3pt_ts100", 4, "on"),
            _pass(2, "5pt", 4, "off"),
            _pass(3, "5pt", 4, "on"),
            _pass(4, "7pt", 4, "off"),
            _pass(5, "7pt", 4, "on"),
        ),
        mode="smoke",
    )


def five_point_ab_plan() -> BenchmarkPlan:
    """Return the focused, counterbalanced 5-point ON/OFF comparison."""
    return BenchmarkPlan(
        schema=_SCHEMA,
        frequency_start_ghz=4.3,
        frequency_stop_ghz=3.9,
        frequency_step_mhz=0.5,
        frequency_count=801,
        reset_mode="active",
        readout_location="park",
        calibration_policy="once",
        passes=(
            _pass(0, "5pt", 180, "off"),
            _pass(1, "5pt", 180, "on"),
            _pass(2, "5pt", 300, "on"),
            _pass(3, "5pt", 300, "off"),
        ),
        mode="five_point_ab",
    )


def _decimal(value: float) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("frequency fields must be finite decimal values") from exc


def _require_finite_number(value: object, field: str) -> None:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be finite")
    try:
        if not math.isfinite(value):
            raise ValueError(f"{field} must be finite")
    except TypeError as exc:
        raise ValueError(f"{field} must be finite") from exc


def _require_nonnegative_integer(value: object, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")


def _require_positive_integer(value: object, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")


def _validate_plan(plan: BenchmarkPlan) -> None:
    if plan.schema != _SCHEMA:
        raise ValueError(f"unsupported benchmark schema: {plan.schema!r}")
    if plan.reset_mode != "active":
        raise ValueError("benchmark reset mode must be active")
    if plan.readout_location != "park":
        raise ValueError("benchmark readout location must be park")
    if plan.calibration_policy != "once":
        raise ValueError("benchmark calibration policy must be once")

    _require_finite_number(plan.frequency_start_ghz, "frequency start")
    _require_finite_number(plan.frequency_stop_ghz, "frequency stop")
    _require_finite_number(plan.frequency_step_mhz, "frequency step")
    _require_positive_integer(plan.frequency_count, "frequency count")
    start = _decimal(plan.frequency_start_ghz)
    stop = _decimal(plan.frequency_stop_ghz)
    step_mhz = _decimal(plan.frequency_step_mhz)
    if start <= stop or step_mhz <= 0:
        raise ValueError("frequency grid must descend with a positive step")
    step_ghz = step_mhz / Decimal("1000")
    intervals = (start - stop) / step_ghz
    if intervals != intervals.to_integral_value():
        raise ValueError("frequency endpoints must align exactly with the step")
    if plan.frequency_count != int(intervals) + 1:
        raise ValueError("frequency count does not match the exact grid arithmetic")

    for expected_index, benchmark_pass in enumerate(plan.passes):
        _require_nonnegative_integer(benchmark_pass.index, "benchmark pass index")
        if benchmark_pass.index != expected_index:
            raise ValueError("benchmark pass indices must be sequential")
        _require_positive_integer(
            benchmark_pass.shots_per_condition, "shots per condition"
        )
        _require_positive_integer(benchmark_pass.condition_count, "condition count")
        try:
            delays_us = tuple(benchmark_pass.delays_us)
        except TypeError as exc:
            raise ValueError("benchmark delays must be finite") from exc
        if not delays_us:
            raise ValueError("benchmark delays must be positive and increasing")
        for delay in delays_us:
            _require_finite_number(delay, "benchmark delays")
        expected_delays = _PROTOCOL_DELAYS_US.get(benchmark_pass.protocol)
        if expected_delays is None:
            raise ValueError(f"unknown benchmark protocol: {benchmark_pass.protocol!r}")
        if delays_us != expected_delays:
            raise ValueError("benchmark protocol delays do not match its canonical definition")
        if (
            any(delay <= 0 for delay in delays_us)
            or any(
                following <= preceding
                for preceding, following in zip(delays_us, delays_us[1:])
            )
        ):
            raise ValueError("benchmark delays must be positive and increasing")
        if benchmark_pass.predistortion not in {"on", "off"}:
            raise ValueError("predistortion must be 'on' or 'off'")
        if benchmark_pass.condition_count != 2 + len(delays_us):
            raise ValueError("condition count must include P0/P1 references")


def canonical_document(plan: BenchmarkPlan) -> dict[str, object]:
    """Return the portable document whose compact JSON is fingerprinted."""
    _validate_plan(plan)
    return {
        "schema": plan.schema,
        "frequency_grid_ghz": {
            "start": plan.frequency_start_ghz,
            "stop": plan.frequency_stop_ghz,
            "step_mhz": plan.frequency_step_mhz,
            "count": plan.frequency_count,
            "order": "descending",
        },
        "reset_mode": plan.reset_mode,
        "readout_location": plan.readout_location,
        "calibration_policy": plan.calibration_policy,
        "passes": [
            {
                "index": benchmark_pass.index,
                "protocol": benchmark_pass.protocol,
                "delays_us": list(benchmark_pass.delays_us),
                "shots_per_condition": benchmark_pass.shots_per_condition,
                "condition_count": benchmark_pass.condition_count,
                "predistortion": benchmark_pass.predistortion,
                "role": benchmark_pass.role,
            }
            for benchmark_pass in plan.passes
        ],
    }


def canonical_json(plan: BenchmarkPlan) -> str:
    """Serialize a validated benchmark plan in its canonical compact form."""
    return json.dumps(
        canonical_document(plan), sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def plan_fingerprint(plan: BenchmarkPlan) -> str:
    """Return the SHA-256 fingerprint of the canonical plan JSON."""
    return hashlib.sha256(canonical_json(plan).encode("utf-8")).hexdigest()


def frequency_grid_ghz(plan: BenchmarkPlan) -> np.ndarray:
    """Return the validated descending frequency grid in GHz."""
    _validate_plan(plan)
    return np.linspace(
        plan.frequency_start_ghz,
        plan.frequency_stop_ghz,
        num=plan.frequency_count,
        dtype=float,
    )


def session_stem(
    device: str, plan: BenchmarkPlan, started_at: datetime | str | None = None
) -> str:
    """Return a readable session stem without introducing hardware dependencies."""
    _validate_plan(plan)
    if started_at is None:
        timestamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    elif isinstance(started_at, datetime):
        timestamp = started_at.strftime("%Y%m%dT%H%M%S%z")
    else:
        timestamp = "".join(character for character in str(started_at) if character.isalnum())
    safe_device = "".join(character for character in str(device) if character.isalnum() or character in "-_")
    if not safe_device or not timestamp:
        raise ValueError("device and started_at must produce non-empty artifact names")
    return f"{safe_device}_protocol_selection_{plan.mode}_{timestamp}"


def artifact_paths(
    output_dir: str | Path, stem: str, item: BenchmarkPass
) -> tuple[Path, Path]:
    """Return the deterministic raw-data and metadata paths for one pass."""
    base = Path(output_dir) / f"{stem}_{item.pass_id}"
    return (
        base.with_name(base.name + "_raw.csv"),
        base.with_name(base.name + "_metadata.json"),
    )


def sha256_file(path: str | Path) -> str:
    """Return the SHA-256 digest of an artifact without loading it into memory."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: str | Path, document: Mapping[str, Any]) -> Path:
    """Atomically replace a JSON document after syncing its complete contents."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent,
            prefix=f".{destination.name}.", suffix=".tmp", delete=False,
        ) as stream:
            temporary_name = stream.name
            json.dump(document, stream, sort_keys=True, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, destination)
    finally:
        if temporary_name is not None and os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return destination


def _new_pass_entry(item: BenchmarkPass) -> dict[str, Any]:
    return {
        "index": item.index,
        "pass_id": item.pass_id,
        "status": "pending",
        "artifacts": {},
    }


def new_manifest(
    plan: BenchmarkPlan, *, device: str, controller: str, code_commit: str,
    model_provenance: Mapping[str, Any], calibration_id: str,
) -> dict[str, Any]:
    """Create the canonical checkpoint manifest for a benchmark session."""
    _validate_plan(plan)
    model = dict(model_provenance)
    if not model.get("sha256"):
        raise ValueError("model provenance must include a sha256")
    if not all(isinstance(value, str) and value for value in (device, controller, calibration_id)):
        raise ValueError("device, controller, and calibration_id must be non-empty strings")
    return {
        "schema": _MANIFEST_SCHEMA,
        "plan": canonical_document(plan),
        "plan_fingerprint": plan_fingerprint(plan),
        "device": device,
        "controller": controller,
        "code_commit": code_commit,
        "model_provenance": model,
        "calibration_id": calibration_id,
        "status": "running",
        "passes": [_new_pass_entry(item) for item in plan.passes],
    }


def _read_manifest(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as stream:
        manifest = json.load(stream)
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be a JSON object")
    return manifest


def _pass_entry(manifest: dict[str, Any], pass_index: int) -> dict[str, Any]:
    entries = manifest.get("passes")
    if not isinstance(entries, list):
        raise ValueError("manifest passes must be a list")
    for entry in entries:
        if isinstance(entry, dict) and entry.get("index") == pass_index:
            return entry
    raise ValueError(f"manifest has no pass {pass_index}")


def _write_manifest(path: str | Path, manifest: dict[str, Any]) -> dict[str, Any]:
    atomic_write_json(path, manifest)
    return manifest


def record_pass_started(
    manifest_path: str | Path, pass_index: int, *, started_at: str
) -> dict[str, Any]:
    """Mark a canonical pass as running before the hardware acquisition starts."""
    manifest = _read_manifest(manifest_path)
    entry = _pass_entry(manifest, pass_index)
    entry.update({"status": "running", "started_at": started_at})
    entry.pop("error", None)
    return _write_manifest(manifest_path, manifest)


def _artifact_record(path: str | Path) -> dict[str, str]:
    artifact_path = Path(path)
    if not artifact_path.is_file():
        raise FileNotFoundError("both pass artifacts must exist before completion")
    return {"path": str(artifact_path.resolve()), "sha256": sha256_file(artifact_path)}


def record_pass_complete(
    manifest_path: str | Path, pass_index: int, *, raw_path: str | Path,
    metadata_path: str | Path, ended_at: str, duration_s: float,
) -> dict[str, Any]:
    """Checkpoint a completed pass only after both output artifacts are durable."""
    if not math.isfinite(duration_s) or duration_s < 0:
        raise ValueError("duration_s must be finite and non-negative")
    artifacts = {
        "raw_csv": _artifact_record(raw_path),
        "metadata_json": _artifact_record(metadata_path),
    }
    manifest = _read_manifest(manifest_path)
    entry = _pass_entry(manifest, pass_index)
    entry.update({
        "status": "complete",
        "ended_at": ended_at,
        "duration_s": float(duration_s),
        "artifacts": artifacts,
    })
    entry.pop("error", None)
    return _write_manifest(manifest_path, manifest)


def record_pass_failed(
    manifest_path: str | Path, pass_index: int, *, error_type: str,
    error_message: str, traceback_text: str, failed_at: str,
) -> dict[str, Any]:
    """Record a failed attempt without falsely treating its pass as complete."""
    manifest = _read_manifest(manifest_path)
    entry = _pass_entry(manifest, pass_index)
    entry.update({
        "status": "failed",
        "failed_at": failed_at,
        "error": {
            "type": error_type,
            "message": error_message,
            "traceback": traceback_text,
        },
    })
    return _write_manifest(manifest_path, manifest)


def _require_manifest_match(manifest: Mapping[str, Any], field: str, expected: Any) -> None:
    if manifest.get(field) != expected:
        raise ValueError(f"resume {field.replace('_', ' ')} mismatch")


def _verify_completed_artifacts(manifest: Mapping[str, Any]) -> None:
    entries = manifest.get("passes")
    if not isinstance(entries, list):
        raise ValueError("manifest passes must be a list")
    for entry in entries:
        if not isinstance(entry, Mapping) or entry.get("status") != "complete":
            continue
        artifacts = entry.get("artifacts")
        if not isinstance(artifacts, Mapping):
            raise ValueError("completed pass artifacts are missing")
        for artifact_name in ("raw_csv", "metadata_json"):
            artifact = artifacts.get(artifact_name)
            if not isinstance(artifact, Mapping):
                raise ValueError("completed pass artifacts are missing")
            path = artifact.get("path")
            checksum = artifact.get("sha256")
            if not isinstance(path, str) or not isinstance(checksum, str):
                raise ValueError("completed pass artifacts are malformed")
            try:
                actual_checksum = sha256_file(path)
            except OSError as exc:
                raise ValueError("completed pass artifact is missing") from exc
            if actual_checksum != checksum:
                raise ValueError("completed pass artifact checksum mismatch")


def _validate_manifest_plan(manifest: Mapping[str, Any], plan: BenchmarkPlan) -> None:
    """Validate that a checkpoint's canonical pass contract belongs to ``plan``."""
    _validate_plan(plan)
    _require_manifest_match(manifest, "schema", _MANIFEST_SCHEMA)
    _require_manifest_match(manifest, "plan", canonical_document(plan))
    _require_manifest_match(manifest, "plan_fingerprint", plan_fingerprint(plan))
    entries = manifest.get("passes")
    if not isinstance(entries, list) or len(entries) != len(plan.passes):
        raise ValueError("resume pass list mismatch")
    for item, entry in zip(plan.passes, entries):
        if not isinstance(entry, Mapping) or entry.get("index") != item.index or entry.get("pass_id") != item.pass_id:
            raise ValueError("resume pass list mismatch")
        if entry.get("status") not in {"pending", "running", "complete", "failed"}:
            raise ValueError("resume pass status mismatch")


def load_resume_manifest(
    manifest_path: str | Path, plan: BenchmarkPlan, *, device: str, controller: str,
    model_sha256: str, calibration_id: str,
) -> dict[str, Any]:
    """Load a resumable manifest after strict provenance and artifact validation."""
    _validate_plan(plan)
    manifest = _read_manifest(manifest_path)
    _validate_manifest_plan(manifest, plan)
    _require_manifest_match(manifest, "device", device)
    _require_manifest_match(manifest, "controller", controller)
    model = manifest.get("model_provenance")
    if not isinstance(model, Mapping) or model.get("sha256") != model_sha256:
        raise ValueError("resume model mismatch")
    _require_manifest_match(manifest, "calibration_id", calibration_id)
    _verify_completed_artifacts(manifest)
    return manifest


def pending_passes(manifest: Mapping[str, Any], plan: BenchmarkPlan) -> tuple[BenchmarkPass, ...]:
    """Return canonical passes not backed by verified completion records."""
    _validate_manifest_plan(manifest, plan)
    entries = manifest.get("passes")
    assert isinstance(entries, list)
    _verify_completed_artifacts(manifest)
    statuses = {entry.get("index"): entry.get("status") for entry in entries if isinstance(entry, Mapping)}
    return tuple(item for item in plan.passes if statuses.get(item.index) != "complete")


def _as_vector(data: Mapping[str, Any], key: str, count: int, default: Any) -> np.ndarray:
    if key not in data:
        return np.full(count, default)
    vector = np.asarray(data[key])
    if vector.ndim != 1 or len(vector) != count:
        raise ValueError(f"{key} must be a one-dimensional array with {count} values")
    return vector


def _optional_vector(value: Any, count: int, field: str) -> np.ndarray:
    """Return an explicitly supplied scalar/vector, preserving absent values as NaN."""
    if value is None:
        return np.full(count, np.nan)
    vector = np.asarray(value)
    if vector.ndim == 0:
        return np.full(count, vector.item())
    if vector.ndim != 1 or len(vector) != count:
        raise ValueError(f"{field} must be a scalar or one-dimensional array with {count} values")
    return vector


def _scalar(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    return value


def _metric_prefix(item: BenchmarkPass) -> str:
    return "T1_3pt" if item.protocol.startswith("3pt") else f"T1_{item.condition_count}pt"


def normalize_experiment_data(
    item: BenchmarkPass, data: Mapping[str, Any], *, target_frequency_ghz: Sequence[float],
    realized_frequency_ghz: Sequence[float], flux_coordinate: Sequence[float] | None = None,
    requested_flux_coordinate: Sequence[float] | None = None,
    realized_flux_coordinate: Sequence[float] | None = None,
    delays_us: Sequence[float] | None = None, pass_started_at: str | None = None,
    pass_ended_at: str | None = None, normalization_denominator: Any = None,
    residual_deviance: Any = None, non_exponential_diagnostic: Any = None,
) -> list[dict[str, Any]]:
    """Convert existing 3-point or n-point fit outputs to portable row records."""
    count = len(target_frequency_ghz)
    target = _as_vector({"target": target_frequency_ghz}, "target", count, np.nan).astype(float)
    realized = _as_vector({"realized": realized_frequency_ghz}, "realized", count, np.nan).astype(float)
    flux = _optional_vector(flux_coordinate, count, "flux_coordinate")
    requested_flux = _optional_vector(
        requested_flux_coordinate if requested_flux_coordinate is not None else data.get("requested_flux_coordinate"),
        count, "requested_flux_coordinate",
    )
    realized_flux = _optional_vector(
        realized_flux_coordinate if realized_flux_coordinate is not None else data.get("realized_flux_coordinate"),
        count, "realized_flux_coordinate",
    )
    prefix = _metric_prefix(item)
    gamma = _as_vector(data, f"inv_{prefix}_per_us", count, np.nan).astype(float)
    gamma_error = _as_vector(data, f"inv_{prefix}_err_per_us", count, np.nan).astype(float)
    t1 = _as_vector(data, f"{prefix}_us", count, np.nan).astype(float)
    t1_error = _as_vector(data, f"{prefix}_err_us", count, np.nan).astype(float)
    valid_source = _as_vector(data, f"{prefix}_valid_mask", count, True).astype(bool)
    fit_success = _as_vector(data, f"{prefix}_fit_success", count, valid_source).astype(bool)
    fit_deviance = _as_vector(data, f"{prefix}_fit_deviance", count, np.nan).astype(float)
    direction_delta = _as_vector(
        data, f"inv_{prefix}_per_us_scan_direction_delta", count, np.nan
    ).astype(float)
    denominator = _optional_vector(
        normalization_denominator if normalization_denominator is not None else data.get("normalization_denominator"),
        count, "normalization_denominator",
    )
    residual = _optional_vector(
        residual_deviance if residual_deviance is not None else data.get(f"{prefix}_residual_deviance"),
        count, "residual_deviance",
    )
    non_exponential = _optional_vector(
        non_exponential_diagnostic if non_exponential_diagnostic is not None else data.get(f"{prefix}_non_exponential_diagnostic"),
        count, "non_exponential_diagnostic",
    )
    p0 = _as_vector(data, "P0", count, np.nan).astype(float)
    p1 = _as_vector(data, "P1", count, np.nan).astype(float)
    contrast = _as_vector(data, f"ref_contrast_{prefix.removeprefix('T1_')}", count, np.nan).astype(float)
    missing_contrast = ~np.isfinite(contrast)
    contrast[missing_contrast] = np.abs(p1[missing_contrast] - p0[missing_contrast])
    valid = valid_source & np.isfinite(gamma)
    raw_keys = []
    for key, value in data.items():
        array = np.asarray(value)
        if array.ndim == 1 and len(array) == count and (
            key.startswith(("P0", "P1", "Ps")) or "_scan_" in key
        ):
            raw_keys.append(key)
    raw_keys.sort(key=lambda key: (not key.startswith("P"), key))
    raw_vectors = {key: _as_vector(data, key, count, np.nan) for key in raw_keys}
    actual_delays = list(item.delays_us if delays_us is None else delays_us)
    if not actual_delays or not all(math.isfinite(delay) for delay in actual_delays):
        raise ValueError("delays_us must contain finite values")
    started_at = pass_started_at if pass_started_at is not None else data.get("pass_started_at")
    ended_at = pass_ended_at if pass_ended_at is not None else data.get("pass_ended_at")
    rows: list[dict[str, Any]] = []
    for index in range(count):
        row = {
            "pass_index": item.index,
            "pass_id": item.pass_id,
            "protocol": item.protocol,
            "predistortion": item.predistortion,
            "shots_per_condition": item.shots_per_condition,
            "condition_count": item.condition_count,
            "target_frequency_ghz": float(target[index]),
            "realized_frequency_ghz": float(realized[index]),
            "flux_coordinate": _scalar(flux[index]),
            "gamma1_per_us": float(gamma[index]),
            "gamma1_err_per_us": float(gamma_error[index]),
            "t1_us": float(t1[index]),
            "t1_err_us": float(t1_error[index]),
            "valid": bool(valid[index]),
            "reference_contrast": float(contrast[index]),
            "fit_success": bool(fit_success[index]),
            "fit_deviance": float(fit_deviance[index]),
            "scan_direction_delta": float(direction_delta[index]),
            "requested_flux_coordinate": _scalar(requested_flux[index]),
            "realized_flux_coordinate": _scalar(realized_flux[index]),
            "delays_us": actual_delays,
            "pass_started_at": started_at,
            "pass_ended_at": ended_at,
            "normalization_denominator": _scalar(denominator[index]),
            "residual_deviance": _scalar(residual[index]),
            "non_exponential_diagnostic": _scalar(non_exponential[index]),
        }
        row.update({key: _scalar(vector[index]) for key, vector in raw_vectors.items()})
        rows.append(row)
    return rows


def _finite_values(rows: Sequence[Mapping[str, Any]], key: str) -> np.ndarray:
    values = np.asarray([row.get(key, np.nan) for row in rows], dtype=float)
    return values[np.isfinite(values)]


def _nanmedian(values: np.ndarray) -> float:
    return float(np.median(values)) if len(values) else float("nan")


def _longest_invalid_run(valid: np.ndarray) -> int:
    longest = current = 0
    for value in valid:
        if value:
            current = 0
        else:
            current += 1
            longest = max(longest, current)
    return longest


def summarize_pass(rows: Sequence[Mapping[str, Any]], *, duration_s: float | None = None) -> dict[str, Any]:
    """Compute robust protocol-comparison metrics from normalized pass rows."""
    if not rows:
        raise ValueError("cannot summarize an empty pass")
    gamma = np.asarray([row.get("gamma1_per_us", np.nan) for row in rows], dtype=float)
    gamma_error = np.asarray([row.get("gamma1_err_per_us", np.nan) for row in rows], dtype=float)
    declared_valid = np.asarray([bool(row.get("valid", False)) for row in rows])
    valid = declared_valid & np.isfinite(gamma)
    p0 = np.asarray([row.get("P0", np.nan) for row in rows], dtype=float)
    p1 = np.asarray([row.get("P1", np.nan) for row in rows], dtype=float)
    roughness = np.abs(np.diff(gamma, n=2))
    first = rows[0]
    summary = {key: first.get(key) for key in SUMMARY_COLUMNS[:6]}
    summary.update({
        "valid_fraction": float(np.count_nonzero(valid) / len(rows)),
        "longest_invalid_run": _longest_invalid_run(valid),
        "median_reference_contrast": _nanmedian(np.abs(p1 - p0)[np.isfinite(p0) & np.isfinite(p1)]),
        "uncertainty_available_fraction": float(np.count_nonzero(valid & np.isfinite(gamma_error) & (gamma_error > 0)) / len(rows)),
        "median_gamma1_err_per_us": _nanmedian(_finite_values(rows, "gamma1_err_per_us")),
        "p90_gamma1_err_per_us": float(np.percentile(_finite_values(rows, "gamma1_err_per_us"), 90)) if len(_finite_values(rows, "gamma1_err_per_us")) else float("nan"),
        "median_abs_direction_delta": _nanmedian(np.abs(_finite_values(rows, "scan_direction_delta"))),
        "median_fit_deviance": _nanmedian(_finite_values(rows, "fit_deviance")),
        "median_local_roughness": _nanmedian(roughness[np.isfinite(roughness)]),
        "duration_s": float(duration_s) if duration_s is not None else float("nan"),
    })
    return summary


def compare_sentinels(
    opening_rows: Sequence[Mapping[str, Any]], closing_rows: Sequence[Mapping[str, Any]]
) -> dict[str, float | int]:
    """Measure opening-to-closing Gamma1 drift in absolute and sigma units."""
    if len(opening_rows) != len(closing_rows):
        raise ValueError("sentinel frequency coordinate lengths do not align")
    count = len(opening_rows)
    for coordinate in ("target_frequency_ghz", "realized_frequency_ghz"):
        opening_coordinate = np.asarray(
            [row.get(coordinate, np.nan) for row in opening_rows], dtype=float
        )
        closing_coordinate = np.asarray(
            [row.get(coordinate, np.nan) for row in closing_rows], dtype=float
        )
        if not np.array_equal(opening_coordinate, closing_coordinate):
            raise ValueError(
                f"sentinel {coordinate.replace('_ghz', '').replace('_', ' ')} coordinates do not align"
            )
    opening = np.asarray([row.get("gamma1_per_us", np.nan) for row in opening_rows[:count]], dtype=float)
    closing = np.asarray([row.get("gamma1_per_us", np.nan) for row in closing_rows[:count]], dtype=float)
    opening_error = np.asarray([row.get("gamma1_err_per_us", np.nan) for row in opening_rows[:count]], dtype=float)
    closing_error = np.asarray([row.get("gamma1_err_per_us", np.nan) for row in closing_rows[:count]], dtype=float)
    opening_valid = np.asarray([bool(row.get("valid", False)) for row in opening_rows[:count]])
    closing_valid = np.asarray([bool(row.get("valid", False)) for row in closing_rows[:count]])
    delta = closing - opening
    valid_delta = opening_valid & closing_valid & np.isfinite(delta)
    finite_delta = np.abs(delta[valid_delta])
    sigma = np.sqrt(opening_error**2 + closing_error**2)
    valid_sigma = valid_delta & np.isfinite(opening_error) & np.isfinite(closing_error) & (opening_error > 0) & (closing_error > 0)
    sigma_units = np.abs(delta[valid_sigma]) / sigma[valid_sigma]
    return {
        "median_abs_delta_per_us": _nanmedian(finite_delta),
        "median_abs_delta_sigma": _nanmedian(sigma_units[np.isfinite(sigma_units)]),
        "finite_count": int(len(finite_delta)),
        "sigma_finite_count": int(np.count_nonzero(np.isfinite(sigma_units))),
    }


def _column_order(rows: Sequence[Mapping[str, Any]], preferred: Sequence[str]) -> list[str]:
    all_columns = {key for row in rows for key in row}
    extras = sorted(all_columns.difference(preferred))
    return [key for key in preferred if key in all_columns] + extras


def _csv_value(value: Any) -> Any:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return ""
    return _scalar(value)


def _write_csv(path: str | Path, rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in columns})
    return destination


def write_pass_csv(path: str | Path, rows: Sequence[Mapping[str, Any]]) -> Path:
    """Write normalized pass rows with stable common columns and retained raw data."""
    return _write_csv(path, rows, _column_order(rows, PASS_ROW_COLUMNS))


def write_summary_csv(path: str | Path, summaries: Sequence[Mapping[str, Any]]) -> Path:
    """Write one stable metrics row for each benchmark pass."""
    return _write_csv(path, summaries, _column_order(summaries, SUMMARY_COLUMNS))


def _session_rows(session: Any) -> dict[int, Sequence[Mapping[str, Any]]]:
    if isinstance(session, Mapping):
        passes = session.get("passes", session)
    else:
        passes = session
    if isinstance(passes, Mapping):
        return {int(index): rows for index, rows in passes.items() if isinstance(rows, Sequence)}
    result: dict[int, Sequence[Mapping[str, Any]]] = {}
    for entry in passes:
        if not isinstance(entry, Mapping) or "rows" not in entry:
            continue
        index = entry.get("index", entry.get("pass_index"))
        if index is not None:
            result[int(index)] = entry["rows"]
    return result


def _condition_label(index: int, rows: Sequence[Mapping[str, Any]]) -> str:
    first = rows[0]
    protocol = str(first.get("protocol", "unknown protocol"))
    shots = first.get("shots_per_condition", "?")
    conditions = first.get("condition_count", "?")
    try:
        total_budget = int(shots) * int(conditions)
        budget = f"{total_budget} shots"
    except (TypeError, ValueError):
        budget = "unknown budget"
    mode = str(first.get("predistortion", "unknown")).upper()
    return (
        f"pass {index:02d} — {protocol} | {shots} shots/condition × "
        f"{conditions} = {budget} | {mode}"
    )


def _mark_invalid_points(
    axis: Any, frequency: np.ndarray, values: np.ndarray, valid: np.ndarray
) -> int:
    invalid_count = int(np.count_nonzero(~valid))
    if invalid_count:
        finite_values = values[valid]
        marker_y = float(np.min(finite_values)) if len(finite_values) else 0.0
        axis.scatter(
            frequency[~valid], np.full(invalid_count, marker_y), marker="x",
            color="crimson", s=16, label="_nolegend_",
        )
    return invalid_count


def _realized_frequency(rows: Sequence[Mapping[str, Any]]) -> np.ndarray:
    return np.asarray(
        [row.get("realized_frequency_ghz", row.get("target_frequency_ghz", np.nan)) for row in rows],
        dtype=float,
    )


def _plot_linecut(axis: Any, rows: Sequence[Mapping[str, Any]], title: str) -> None:
    frequency = _realized_frequency(rows)
    gamma = np.asarray([row.get("gamma1_per_us", np.nan) for row in rows], dtype=float)
    valid = np.asarray([bool(row.get("valid", False)) for row in rows]) & np.isfinite(gamma)
    axis.plot(frequency[valid], gamma[valid], color="C0", linewidth=1.0)
    invalid_count = _mark_invalid_points(axis, frequency, gamma, valid)
    axis.set_title(f"{title}\ninvalid {invalid_count}/{len(rows)}", fontsize=8)
    axis.set_xlabel("realized frequency (GHz)", fontsize=7)
    axis.set_ylabel("Gamma1 (1/us)", fontsize=7)
    axis.tick_params(labelsize=7)


def render_comparison_figure(session: Any, output_path: str | Path) -> dict[str, int]:
    """Render primary linecuts, full sentinel context, and matched-budget metrics."""
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    rows_by_index = _session_rows(session)
    durations: dict[int, float] = {}
    plan_hash = None
    model_hash = None
    if isinstance(session, Mapping):
        plan_hash = session.get("plan_fingerprint")
        model = session.get("model_provenance")
        model_hash = model.get("sha256") if isinstance(model, Mapping) else session.get("model_sha256")
        passes = session.get("passes")
        if isinstance(passes, Sequence):
            for entry in passes:
                if isinstance(entry, Mapping) and entry.get("index") is not None:
                    duration = entry.get("duration_s")
                    if isinstance(duration, (int, float)) and math.isfinite(duration):
                        durations[int(entry["index"])] = float(duration)
    figure = plt.figure(figsize=(22, 18), constrained_layout=True)
    figure.suptitle(
        "Protocol-selection benchmark — "
        f"plan: {plan_hash or 'unavailable'} | model: {model_hash or 'unavailable'}",
        fontsize=11,
    )
    grid = figure.add_gridspec(5, 4)
    for index in range(16):
        axis = figure.add_subplot(grid[index // 4, index % 4])
        rows = rows_by_index.get(index, ())
        if rows:
            _plot_linecut(axis, rows, _condition_label(index, rows))
        else:
            axis.text(0.5, 0.5, "missing pass", ha="center", va="center")
            axis.set_title(f"pass {index:02d}\ninvalid 0/0", fontsize=8)
    bottom = grid[4, :].subgridspec(1, 5, width_ratios=(1, 1, 1, 1.8, 1.5))
    opening, closing = rows_by_index.get(0, ()), rows_by_index.get(16, ())
    opening_axis = figure.add_subplot(bottom[0, 0])
    closing_axis = figure.add_subplot(bottom[0, 1])
    sentinel_axis = figure.add_subplot(bottom[0, 2])
    if opening and closing:
        _plot_linecut(opening_axis, opening, "opening sentinel")
        _plot_linecut(closing_axis, closing, "terminal sentinel")
        compare_sentinels(opening, closing)
        frequency = _realized_frequency(opening)
        opening_gamma = np.asarray([row.get("gamma1_per_us", np.nan) for row in opening], dtype=float)
        closing_gamma = np.asarray([row.get("gamma1_per_us", np.nan) for row in closing], dtype=float)
        valid = (
            np.asarray([bool(row.get("valid", False)) for row in opening])
            & np.asarray([bool(row.get("valid", False)) for row in closing])
            & np.isfinite(opening_gamma)
            & np.isfinite(closing_gamma)
        )
        difference = closing_gamma - opening_gamma
        sentinel_axis.plot(frequency[valid], difference[valid], color="C3")
        invalid_count = _mark_invalid_points(sentinel_axis, frequency, difference, valid)
        sentinel_axis.set_title(
            f"opening / closing sentinel difference\ninvalid {invalid_count}/{len(opening)}"
        )
    else:
        opening_axis.text(0.5, 0.5, "opening unavailable", ha="center", va="center")
        closing_axis.text(0.5, 0.5, "terminal unavailable", ha="center", va="center")
        sentinel_axis.text(0.5, 0.5, "sentinel unavailable", ha="center", va="center")
    sentinel_axis.set_xlabel("realized frequency (GHz)")
    sentinel_axis.set_ylabel("delta Gamma1 (1/us)")

    overlay_axis = figure.add_subplot(bottom[0, 3])
    pairs: dict[tuple[Any, ...], dict[str, Sequence[Mapping[str, Any]]]] = {}
    for index, rows in rows_by_index.items():
        if index >= 16 or not rows:
            continue
        first = rows[0]
        key = (first.get("protocol"), first.get("shots_per_condition"), first.get("condition_count"))
        if key not in _LOW_COST_OVERLAY_CONDITIONS:
            continue
        pairs.setdefault(key, {})[str(first.get("predistortion"))] = rows
    uncertainty_band_series = 0
    uncertainty_unavailable_series = 0
    for pair_number, mode_rows in enumerate(pairs.values()):
        for mode, rows in mode_rows.items():
            frequency = _realized_frequency(rows)
            gamma = np.asarray([row.get("gamma1_per_us", np.nan) for row in rows], dtype=float)
            error = np.asarray([row.get("gamma1_err_per_us", np.nan) for row in rows], dtype=float)
            valid = np.asarray([bool(row.get("valid", False)) for row in rows]) & np.isfinite(gamma)
            uncertain = valid & np.isfinite(error) & (error > 0)
            color = f"C{(pair_number * 2 + (mode == 'on')) % 10}"
            invalid_count = _mark_invalid_points(overlay_axis, frequency, gamma, valid)
            label = _condition_label(int(rows[0].get("pass_index", pair_number)), rows)
            label += f" | invalid {invalid_count}/{len(rows)}"
            if not np.any(uncertain):
                label += " (uncertainty unavailable)"
                uncertainty_unavailable_series += 1
            elif not np.all(uncertain[valid]):
                label += " (uncertainty partial)"
            overlay_axis.plot(frequency[valid], gamma[valid], label=label, color=color)
            if np.any(uncertain):
                overlay_axis.fill_between(
                    frequency, gamma - error, gamma + error, where=uncertain,
                    color=color, alpha=0.15,
                )
                uncertainty_band_series += 1
    overlay_axis.set_title("matched-budget Gamma1 comparisons")
    overlay_axis.set_xlabel("realized frequency (GHz)")
    overlay_axis.set_ylabel("Gamma1 (1/us)")
    if pairs:
        overlay_axis.legend(fontsize=6, ncol=2)
    if uncertainty_unavailable_series:
        overlay_axis.text(
            0.01, 0.01,
            f"{uncertainty_unavailable_series} series: uncertainty unavailable",
            transform=overlay_axis.transAxes, fontsize=7, va="bottom",
        )

    table_axis = figure.add_subplot(bottom[0, 4])
    table_axis.axis("off")
    metrics = [
        summarize_pass(rows, duration_s=durations.get(index))
        for index, rows in sorted(rows_by_index.items()) if index < 16 and rows
    ]
    def metric_value(value: Any, formatter: str) -> str:
        return format(value, formatter) if isinstance(value, (int, float)) and math.isfinite(value) else "unavailable"
    table_columns = ["pass", "valid", "uncertainty", "direction", "runtime", "contrast"]
    table_data = [
        [
            str(metric.get("pass_index", "")),
            metric_value(metric["valid_fraction"], ".2f"),
            f"{metric_value(metric['uncertainty_available_fraction'], '.0%')} / {metric_value(metric['median_gamma1_err_per_us'], '.3g')}",
            metric_value(metric["median_abs_direction_delta"], ".3g"),
            metric_value(metric["duration_s"], ".2f"),
            metric_value(metric["median_reference_contrast"], ".3g"),
        ]
        for metric in metrics
    ]
    table_axis.table(cellText=table_data, colLabels=table_columns, loc="center", cellLoc="center")
    table_axis.set_title("pass metrics")
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(destination, dpi=150)
    plt.close(figure)
    return {
        "primary_map_panels": 16,
        "sentinel_panels": 3 if opening and closing else 0,
        "sentinel_linecut_panels": 2 if opening and closing else 0,
        "uncertainty_band_series": uncertainty_band_series,
        "uncertainty_unavailable_series": uncertainty_unavailable_series,
        "metrics_table_columns": table_columns,
        "plan_fingerprint": plan_hash,
        "model_sha256": model_hash,
    }
