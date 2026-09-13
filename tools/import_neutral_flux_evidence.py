"""Read trusted local measurement pickles into an immutable, finite JSON snapshot.

This program does not import any lab hardware modules. Sources are opened only
for reading. Pickle inputs must be trusted; the default roots are the lab's
specified September 13 predistortion validation records.
"""

import argparse
import csv
import hashlib
import io
import json
import os
import pickle
import tempfile
from pathlib import Path

import numpy as np
from scipy.signal import savgol_filter


DEFAULT_DATA_ROOT = Path("/Volumes/ourphoton/FluxTeam/Data")
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "reports/neutral_flux/input_traces.json"


def calibration_frequency_mhz(control, params):
    """Evaluate the saved asymmetric-transmon-plus-linear-tilt calibration."""
    control = np.asarray(control, dtype=float)
    phase = np.pi * (control - float(params["phase_offset_volts"])) / float(params["period_volts"])
    ej = float(params["EJmax"]) * np.sqrt(np.cos(phase)**2 + float(params["d"])**2 * np.sin(phase)**2)
    return 1000 * (np.sqrt(8 * ej * float(params["Ec"])) - float(params["Ec"])
                   + float(params.get("tilt_slope", 0)) * control)


def invert_calibration(frequency_mhz, params, branch):
    """Invert a verified monotonic branch; out-of-branch values become NaN."""
    lower, upper = map(float, branch)
    if not np.isfinite(lower + upper) or not lower < upper:
        raise ValueError("inversion branch must be finite and increasing")
    control = np.linspace(lower, upper, 100_001)
    frequency = calibration_frequency_mhz(control, params)
    if not np.all(np.isfinite(frequency)):
        raise ValueError("calibration is not finite on the inversion branch")
    derivative = np.diff(frequency)
    if np.all(derivative < 0):
        frequency, control = frequency[::-1], control[::-1]
    elif not np.all(derivative > 0):
        raise ValueError("calibration branch must be strictly monotonic")
    return np.interp(np.asarray(frequency_mhz, dtype=float), frequency, control,
                     left=np.nan, right=np.nan)


def inversion_branch(params, park, target):
    """Choose and record a monotonic branch including park and nearby overshoot.

    Try symmetric extensions of the park-to-target interval, longest first.
    Unlike the legacy endpoint clamp, unsupported frequencies remain missing.
    This numerical extension is not an additional calibration measurement.
    """
    low, high = sorted((float(park), float(target)))
    span = high - low
    if span <= 0:
        raise ValueError("park and target must differ")
    for fraction in (0.5, 0.25, 0.1, 0.0):
        branch = (low - fraction * span, high + fraction * span)
        try:
            invert_calibration([], params, branch)
        except ValueError:
            continue
        return branch
    raise ValueError("no monotonic branch spans the requested excursion")


def feature_score(axis_mhz, magnitude, window_mask, *, polarity="bright", baseline_window_mhz=25):
    """Numerical copy of the QUA saved-map feature-score algorithm (baseline422b6c9)."""
    axis = np.asarray(axis_mhz, dtype=float)
    magnitude = np.asarray(magnitude, dtype=float)
    if magnitude.ndim != 2 or magnitude.shape[0] != axis.size:
        raise ValueError("magnitude must have shape (frequency, time)")
    span = float(np.nanmax(axis) - np.nanmin(axis))
    width = max(float(baseline_window_mhz), 0.5 * span)
    spacing = abs(float(np.nanmedian(np.diff(axis))))
    window = max(5, int(round(width / spacing)))
    window += window % 2 == 0
    window = min(window, axis.size if axis.size % 2 else axis.size - 1)
    scores = np.full_like(magnitude, -np.inf)
    for column in range(magnitude.shape[1]):
        values = magnitude[:, column]
        finite = np.isfinite(values)
        if finite.sum() < 7:
            continue
        filled = np.where(finite, values, np.nanmedian(values[finite]))
        baseline = (savgol_filter(filled, window, 2, mode="interp")
                    if 2 < window < filled.size else np.full_like(filled, np.nanmedian(filled)))
        residual = filled - baseline
        if str(polarity).lower().startswith("dark"):
            residual = -residual
        residual -= np.nanmedian(residual)
        scale = np.nanpercentile(residual, 98) - np.nanpercentile(residual, 50)
        if not np.isfinite(scale) or scale <= 1e-12:
            scale = np.nanstd(residual)
        if np.isfinite(scale) and scale > 1e-12:
            scores[:, column] = residual / scale
    scores[~np.asarray(window_mask, dtype=bool), :] = -np.inf
    return np.where(np.isfinite(scores), scores, -np.inf)


def refine_centroid(axis_mhz, scores, seeds_mhz, *, half_window_mhz,
                    source_axis_ghz=None, source_seeds_ghz=None):
    """Positive-score centroid, matching the QUA local estimator in MHz."""
    axis, scores, seeds = (np.asarray(value, dtype=float) for value in (axis_mhz, scores, seeds_mhz))
    if scores.shape != (axis.size, seeds.size) or not np.isfinite(half_window_mhz) or half_window_mhz <= 0:
        raise ValueError("invalid centroid shapes or half-window")
    output_scale = 1.0
    if source_axis_ghz is not None or source_seeds_ghz is not None:
        if source_axis_ghz is None or source_seeds_ghz is None:
            raise ValueError("both original GHz coordinate arrays are required")
        axis = np.asarray(source_axis_ghz, dtype=float)
        seeds = np.asarray(source_seeds_ghz, dtype=float)
        if scores.shape != (axis.size, seeds.size):
            raise ValueError("original GHz coordinate shapes do not match scores")
        half_window_mhz = float(half_window_mhz) / 1000
        output_scale = 1000.0
    centers = np.full(seeds.shape, np.nan)
    for index, seed in enumerate(seeds):
        active = np.isfinite(axis) & np.isfinite(scores[:, index]) & (np.abs(axis - seed) <= half_window_mhz)
        if active.sum() < 3:
            continue
        local = scores[active, index]
        weights = np.maximum(local - np.nanpercentile(local, 20), 0)**2
        total = np.sum(weights)
        if np.isfinite(total) and total > 0:
            centers[index] = output_scale * np.sum(weights * axis[active]) / total
    return centers


def _rms(values):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    return float(np.sqrt(np.mean(values**2))) if values.size else np.nan


def centroid_window_sensitivity(axis_mhz, scores, seeds_mhz, support,
                                source_axis_ghz=None, source_seeds_ghz=None):
    """Change in center when only the centroid half-window changes (not noise CI)."""
    centers = {str(window): refine_centroid(axis_mhz, scores, seeds_mhz, half_window_mhz=window,
                                            source_axis_ghz=source_axis_ghz,
                                            source_seeds_ghz=source_seeds_ghz)
               for window in (6, 8, 10)}
    output = {}
    for window, value in centers.items():
        active = np.asarray(support, dtype=bool) & np.isfinite(value) & np.isfinite(centers["8"])
        delta = value[active] - centers["8"][active]
        output[window] = {"supported_count": int(active.sum()), "rms_shift_vs_8mhz": _rms(delta),
                          "max_abs_shift_vs_8mhz": float(np.max(np.abs(delta))) if delta.size else np.nan}
    return output


def json_safe(value):
    """Preserve booleans and replace every nonfinite numeric value by JSON null."""
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, Path):
        return str(value)
    return value


def compact_json(value, indent=0):
    """Pretty objects with numeric arrays kept on one readable line."""
    value = json_safe(value)
    padding = " " * indent
    if isinstance(value, dict) and value:
        return "{\n" + ",\n".join(
            " " * (indent + 2) + json.dumps(key) + ": " + compact_json(item, indent + 2)
            for key, item in value.items()) + "\n" + padding + "}"
    if isinstance(value, list) and any(isinstance(item, (dict, list)) for item in value):
        return "[\n" + ",\n".join(" " * (indent + 2) + compact_json(item, indent + 2)
                                    for item in value) + "\n" + padding + "]"
    return json.dumps(value, allow_nan=False)


def _read_snapshot(path):
    before = path.stat()
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    second_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    after = path.stat()
    if (before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns
            or digest != second_digest):
        raise RuntimeError(f"source changed during snapshot: {path}")
    return raw, digest


def _masked(values, support):
    values = np.asarray(values, dtype=float)
    if values.shape != support.shape:
        raise ValueError("trace numerical array and support shapes differ")
    return np.where(support, values, np.nan)


def validate_csv_snapshot(raw, *, expected_rows):
    """Reject stable-but-incomplete CSV exports paired with a finished pickle."""
    rows = csv.reader(io.StringIO(raw.decode("utf-8-sig")))
    header = next(rows, None)
    if not header:
        raise ValueError("paired CSV is incomplete: missing header")
    count = 0
    for row in rows:
        if len(row) != len(header):
            raise ValueError("paired CSV is incomplete: inconsistent columns")
        count += 1
    if count != expected_rows:
        raise ValueError(f"paired CSV has {count} rows, expected {expected_rows}")


def import_trace(path, data_root):
    raw_pickle, pickle_sha = _read_snapshot(path)
    data = pickle.loads(raw_pickle)  # Only the explicitly trusted local input tree.
    if "t_vec" not in data or "extracted_qubit_frequency_ghz" not in data:
        return None
    time = np.asarray(data["t_vec"], dtype=float)
    support = np.asarray(data["trace_supported"], dtype=bool)
    if time.shape != support.shape or np.any(~np.isfinite(time)):
        raise ValueError(f"invalid time/support arrays: {path}")
    raw_frequency = _masked(1000 * np.asarray(data["local_lorentzian_qubit_frequency_ghz"]), support)
    smooth_frequency = _masked(1000 * np.asarray(data["extracted_qubit_frequency_ghz"]), support)
    ridge = _masked(1000 * np.asarray(data["ridge_qubit_frequency_ghz"]), support)
    park, target = float(data["baseline_dc_offset"]), float(data["dc_offset"])
    params = data["flux_fit_params"]
    branch = inversion_branch(params, park, target)
    response_raw = (invert_calibration(raw_frequency, params, branch) - park) / (target - park)
    response_smooth = _masked(data["measured_voltage_step_response"], support)
    grid = 1000 * np.asarray(data["fit_frequency_axis_ghz"], dtype=float)
    widths = _masked(np.asarray(data["extracted_fwhm_hz"]) / 1e6, support)
    valid_widths = widths[np.isfinite(widths)]
    finite_raw, finite_smooth = raw_frequency[np.isfinite(raw_frequency)], smooth_frequency[np.isfinite(smooth_frequency)]
    sensitivity = {
        "raw_smooth_rms_mhz": _rms(raw_frequency - smooth_frequency),
        "ridge_local_rms_mhz": _rms(ridge - raw_frequency),
        "spectral_grid_step_mhz": float(np.median(np.abs(np.diff(grid)))),
        "raw_peak_to_peak_mhz": float(np.ptp(finite_raw)) if finite_raw.size else np.nan,
        "smooth_peak_to_peak_mhz": float(np.ptp(finite_smooth)) if finite_smooth.size else np.nan,
        "width_median_mhz": float(np.median(valid_widths)) if valid_widths.size else np.nan,
        "width_p90_mhz": float(np.percentile(valid_widths, 90)) if valid_widths.size else np.nan,
        "width_max_mhz": float(np.max(valid_widths)) if valid_widths.size else np.nan,
        "width_note": "spectral feature widths, not noise or centroid confidence intervals",
        "raw_inversion_out_of_branch_count": int(np.sum(np.isfinite(raw_frequency) & ~np.isfinite(response_raw))),
    }
    early, late = support & (time <= 21_000), support & (time >= 300_000)
    sensitivity["raw_early_minus_late_mhz"] = (float(np.nanmean(raw_frequency[early]) - np.nanmean(raw_frequency[late]))
                                               if early.any() and late.any() else np.nan)
    if data.get("trace_refinement") == "centroid":
        score = feature_score(grid, data["IQ_mag"], data["fit_frequency_window_mask"],
                              polarity=data.get("trace_selected_polarity", "bright"),
                              baseline_window_mhz=data.get("trace_baseline_window_mhz", 25))
        seeds = 1000 * np.asarray(data["ridge_qubit_frequency_ghz"])
        original_coordinates = {"source_axis_ghz": data["fit_frequency_axis_ghz"],
                                "source_seeds_ghz": data["ridge_qubit_frequency_ghz"]}
        sensitivity["centroid_half_window_mhz"] = centroid_window_sensitivity(
            grid, score, seeds, support, **original_coordinates)
        centers_8 = refine_centroid(grid, score, seeds, half_window_mhz=8, **original_coordinates)
        sensitivity["reextracted_8mhz_vs_saved_local_rms_mhz"] = _rms(_masked(centers_8, support) - raw_frequency)
        sensitivity["centroid_window_boundary_convention"] = "original saved GHz floats retained to reproduce inclusive-window comparisons"

    applied = data.get("applied_flux_tail_compensation") or {}
    edges = np.asarray(applied.get("segment_edges_ns", [0]), dtype=float)
    levels = np.asarray(applied.get("multipliers", [1]), dtype=float)
    if not applied:
        edges, levels = np.asarray([0.0]), np.asarray([1.0])
    if (edges.size != levels.size or edges.size == 0 or edges[0] != 0
            or np.any(np.diff(edges) <= 0) or edges[-1] >= 600_000
            or not np.all(np.isfinite(edges)) or not np.all(np.isfinite(levels))):
        raise ValueError(f"malformed applied correction: {path}")
    paired = {"frequency_drift_csv": path.with_name(path.stem + "_frequency_drift.csv"),
              "raw_sweep_csv": path.with_name(path.stem + "_raw_sweep.csv")}
    hashes, files = {"pkl": pickle_sha}, {"pkl": str(path.relative_to(data_root))}
    for name, csv_path in paired.items():
        if csv_path.is_file():
            csv_bytes, hashes[name] = _read_snapshot(csv_path)
            validate_csv_snapshot(csv_bytes, expected_rows=time.size if name == "frequency_drift_csv"
                                  else time.size * grid.size)
            files[name] = str(csv_path.relative_to(data_root))
        else:
            raise ValueError(f"incomplete measurement: paired CSV is missing: {csv_path}")
    estimator = {key: value for key, value in data.items()
                 if key.startswith("trace_") and not isinstance(value, (list, tuple, dict, np.ndarray))}
    estimator.update({"methods": sorted(set(data.get("trace_extraction_method", []))),
                      "local_saved_field": "local_lorentzian_qubit_frequency_ghz",
                      "local_field_is_centroid": data.get("trace_refinement") == "centroid",
                      "baseline_rearm_time_ns": data.get("baseline_rearm_time_ns"),
                      "acquisition_order": data.get("acquisition_order", "shot_frequency_time"),
                      "shots": data.get("shots"), "read_len_ns": data.get("meta_dict", {}).get("read_len")})
    qubit = str(data["qubit"])
    return dict(
        id=path.stem, qubit=qubit, source=files["pkl"], source_files=files, source_sha256=hashes,
        time_ns=time, raw_frequency_mhz=raw_frequency, smooth_frequency_mhz=smooth_frequency,
        ridge_frequency_mhz=ridge, support=support, response_raw=response_raw,
        response_smooth=response_smooth, park=park, target=target,
        native_control_unit="V" if qubit == "q5" else "QICK DAC gain",
        probe_ns=data.get("meta_dict", {}).get("cw_len"),
        applied_command={"edges_ns": np.r_[edges, 600_000.0], "values": levels},
        applied_correction_source=applied.get("source"),
        flux_fit_params=params, inversion_branch=branch,
        inversion_note="monotonic numerical extension; no endpoint clamping or extra calibration evidence",
        estimator=estimator, grid_mhz=grid, widths_mhz=widths, sensitivity=sensitivity,
    )


def build_snapshot(data_root):
    traces, skipped = [], []
    # Pin the inventory once before reading; do not silently add newly arrived scans.
    inventory = [path for qubit in ("q5", "q3")
                 for path in sorted((data_root / qubit / "2026_09_13/predistortion_validation").rglob("*.pkl"))]
    for path in inventory:
        trace = import_trace(path, data_root)
        if trace is None:
            skipped.append(str(path.relative_to(data_root)))
        else:
            traces.append(trace)
    return json_safe({
        "schema_version": 1, "data_root": str(data_root),
        "source_inventory_pkl": [str(path.relative_to(data_root)) for path in inventory],
        "generator": {"path": "tools/import_neutral_flux_evidence.py",
                      "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        "snapshot_note": "pinned file inventory; two source-byte reads must match SHA256 and stat metadata; paired CSV row/column counts checked; unsupported/nonfinite numerical samples are null; original support is retained",
        "applied_command_note": "outbound normalized step schedule only, ending at600000ns for numerical modeling; not a measured reset/return command",
        "traces": traces, "skipped_nontrace_sources": skipped,
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(Path("/Volumes")) or output.is_relative_to(args.data_root.resolve()):
        raise ValueError("output must be local and outside the measurement source tree")
    snapshot = build_snapshot(args.data_root.resolve())
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=output.parent, prefix=".input_traces-",
                                         suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(compact_json(snapshot) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print(json.dumps({"output": str(output), "trace_count": len(snapshot["traces"]),
                      "qubit_counts": {qubit: sum(trace["qubit"] == qubit for trace in snapshot["traces"])
                                       for qubit in ("q5", "q3")}}))
    for trace in snapshot["traces"]:
        print(json.dumps({"id": trace["id"], "qubit": trace["qubit"],
                          "supported": sum(trace["support"]), "sensitivity": trace["sensitivity"]}))


if __name__ == "__main__":
    main()
