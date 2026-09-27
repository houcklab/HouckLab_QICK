"""Validated spectroscopy maps used by offline and instrument-side analysis."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
import hashlib
from pathlib import Path
from typing import Any

import numpy as np

from .tracker import track_image_ridge


@dataclass(frozen=True)
class StepMap:
    frequency_ghz: np.ndarray
    delay_us: np.ndarray
    magnitude_dbm: np.ndarray
    phase_rad: np.ndarray | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        frequency = np.asarray(self.frequency_ghz, dtype=float)
        delay = np.asarray(self.delay_us, dtype=float)
        magnitude = np.asarray(self.magnitude_dbm, dtype=float)
        phase = None if self.phase_rad is None else np.asarray(self.phase_rad, dtype=float)
        if frequency.ndim != 1 or delay.ndim != 1 or min(frequency.size, delay.size) < 2:
            raise ValueError("frequency and delay axes need at least two points each")
        if not np.all(np.isfinite(frequency)) or not np.all(np.diff(frequency) > 0):
            raise ValueError("frequency axis must be finite and strictly increasing")
        if not np.all(np.isfinite(delay)) or not np.all(np.diff(delay) > 0):
            raise ValueError("delay axis must be finite and strictly increasing")
        expected = (frequency.size, delay.size)
        if magnitude.shape != expected or (phase is not None and phase.shape != expected):
            raise ValueError(f"spectroscopy map shape must be {expected}")
        object.__setattr__(self, "frequency_ghz", frequency)
        object.__setattr__(self, "delay_us", delay)
        object.__setattr__(self, "magnitude_dbm", magnitude)
        object.__setattr__(self, "phase_rad", phase)


@dataclass(frozen=True)
class TraceConfig:
    branch_preference: str = "auto"
    polarity: str = "auto"
    max_jump_mhz: float = 8.0
    min_support_fraction: float = 0.80
    min_edge_margin_mhz: float = 2.0
    ambiguity_ratio: float = 0.95


@dataclass(frozen=True)
class TraceResult:
    frequency_ghz: np.ndarray
    supported: np.ndarray
    lower_ghz: np.ndarray
    upper_ghz: np.ndarray
    score: np.ndarray
    ambiguity: np.ndarray
    signal_source: str
    branch: str
    method: str
    candidates: tuple[dict, ...]
    target_ghz: float


@dataclass(frozen=True)
class QualityReport:
    accepted: bool
    reasons: tuple[str, ...]
    coverage: float
    max_unsupported_gap_us: float
    edge_margin_mhz: float


def _candidate(scan: StepMap, image: np.ndarray, *, source: str,
               polarity: str, background: str, shoulder: str,
               config: TraceConfig) -> dict:
    result = track_image_ridge(
        scan.frequency_ghz, image, polarity=polarity,
        temporal_background=background, shoulder=shoulder,
        max_jump_mhz=config.max_jump_mhz,
        ambiguity_ratio=config.ambiguity_ratio,
        smoothing_window_points=1,
        # Auto follows the dominant single ridge; explicit branch requests
        # are required to resolve a doublet. Their fallback is quality-gated.
        shoulder_min_persistence=(1.1 if shoulder == "auto" else 0.55),
    )
    supported = np.asarray(result["supported"], dtype=bool)
    # A ridge in the negative space between two bright peaks is not a dark
    # spectral line. Require the measured pixels to have the requested sign
    # relative to the column's robust background before ranking hypotheses.
    centers = np.asarray(result["local_frequency_ghz"], dtype=float)
    rows = np.clip(np.searchsorted(scan.frequency_ghz, centers), 0,
                   scan.frequency_ghz.size - 1)
    columns = np.arange(scan.delay_us.size)
    baseline = np.full(image.shape[1], np.nan)
    valid_columns = np.any(np.isfinite(image), axis=0)
    baseline[valid_columns] = np.nanmedian(image[:, valid_columns], axis=0)
    measured = image[rows, columns] - baseline
    signed = measured if polarity == "bright" else -measured
    supported &= np.isfinite(signed) & (signed > 0)
    result["supported"] = supported
    score = np.asarray(result["trace_score"], dtype=float)
    merit = float(np.nanmedian(score[supported])) if np.any(supported) else -np.inf
    result["candidate_merit"] = merit + 20.0 * float(np.mean(supported))
    result["signal_source"] = source
    result["background"] = background
    return result


def extract_step_trace(scan: StepMap, *, baseline_ghz: float,
                       target_ghz: float, config: TraceConfig) -> TraceResult:
    """Select a measured spectral branch and expose alternatives/uncertainty.

    Shape is never flattened or used as an acceptance reward. The expected
    endpoints are recorded for diagnostics but do not force a path.
    """
    if config.branch_preference not in {"auto", "lower", "upper", "midpoint"}:
        raise ValueError("branch_preference must be auto, lower, upper, or midpoint")
    if config.polarity not in {"auto", "bright", "dark"}:
        raise ValueError("polarity must be auto, bright, or dark")
    if not np.isfinite(baseline_ghz) or not np.isfinite(target_ghz):
        raise ValueError("expected endpoint frequencies must be finite")
    images = [("magnitude", scan.magnitude_dbm)]
    if scan.phase_rad is not None and np.nanstd(scan.phase_rad) > 0.05:
        images.append(("phase", np.unwrap(scan.phase_rad, axis=0)))
    candidates = []
    for source, image in images:
        for polarity in (("bright", "dark") if config.polarity == "auto" else (config.polarity,)):
            for background in ("none", "median"):
                try:
                    candidate = _candidate(
                        scan, image, source=source, polarity=polarity,
                        background=background, shoulder=config.branch_preference,
                        config=config,
                    )
                except (ValueError, IndexError, FloatingPointError):
                    continue
                candidates.append(candidate)
    if not candidates:
        raise ValueError("no measured ridge hypothesis could be extracted")
    # Persistent and transient hypotheses compete on direct measured evidence.
    # A phase candidate requires a stronger score than the best magnitude path
    # because an unrelated phase wrap can look like a spectral line.
    def rank(candidate: dict) -> float:
        return candidate["candidate_merit"] - (1.5 if candidate["signal_source"] == "phase" else 0.0)
    selected = max(candidates, key=rank)
    supported = np.asarray(selected["supported"], dtype=bool)
    frequency = np.where(supported, selected["selected_frequency_ghz"], np.nan)
    lower = np.asarray(selected.get("lower_shoulder_frequency_ghz"), dtype=float)
    upper = np.asarray(selected.get("upper_shoulder_frequency_ghz"), dtype=float)
    shoulder = str(selected.get("shoulder_mode", "single"))
    branch = shoulder.split("_")[-1] if shoulder.startswith("paired_") else "single"
    ambiguity = np.asarray(selected["ambiguity_ratio"], dtype=float) >= config.ambiguity_ratio
    # A pair of equally strong, separated measured ridges makes the physical
    # branch unidentified even when the path decoder picks one consistently.
    from scipy.signal import find_peaks
    signed_image = scan.magnitude_dbm if selected["polarity"] == "bright" else -scan.magnitude_dbm
    for column in range(scan.delay_us.size):
        profile = signed_image[:, column]
        if not np.all(np.isfinite(profile)) or not supported[column]:
            continue
        peaks, _ = find_peaks(profile, prominence=0.5)
        if peaks.size < 2:
            continue
        primary = int(np.argmin(np.abs(scan.frequency_ghz[peaks] - frequency[column])))
        primary_row = peaks[primary]
        rivals = peaks[np.abs(scan.frequency_ghz[peaks] - scan.frequency_ghz[primary_row]) >= 0.003]
        noise_floor = float(np.nanmedian(profile))
        primary_height = float(profile[primary_row] - noise_floor)
        if rivals.size and primary_height > 0 and np.max(profile[rivals] - noise_floor) >= 0.9 * primary_height:
            ambiguity[column] = True
    summary = tuple({
        "signal_source": item["signal_source"],
        "polarity": item["polarity"],
        "background": item["background"],
        "branch": item.get("shoulder_mode"),
        "merit": float(item["candidate_merit"]),
        "support_fraction": float(np.mean(item["supported"])),
    } for item in sorted(candidates, key=rank, reverse=True))
    return TraceResult(
        frequency_ghz=frequency, supported=supported,
        lower_ghz=lower, upper_ghz=upper,
        score=np.asarray(selected["trace_score"], dtype=float),
        ambiguity=ambiguity, signal_source=(
            f"{selected['signal_source']}_{selected['polarity']}_{selected['background']}"
        ), branch=branch, method="consensus_v1", candidates=summary,
        target_ghz=float(target_ghz),
    )


def evaluate_trace_quality(result: TraceResult, scan: StepMap,
                           solve_window_us: tuple[float, float],
                           config: TraceConfig | None = None) -> QualityReport:
    config = TraceConfig() if config is None else config
    first, last = map(float, solve_window_us)
    mask = (scan.delay_us >= first) & (scan.delay_us <= last)
    if not first < last or not np.any(mask):
        raise ValueError("solve interval must include measured delays")
    support = np.asarray(result.supported, dtype=bool)[mask]
    coverage = float(np.mean(support))
    delay = scan.delay_us[mask]
    max_gap = 0.0
    missing = np.flatnonzero(~support)
    for group in np.split(missing, np.flatnonzero(np.diff(missing) > 1) + 1):
        if group.size:
            max_gap = max(max_gap, float(delay[group[-1]] - delay[group[0]] + np.median(np.diff(scan.delay_us))))
    frequency = np.asarray(result.frequency_ghz)[mask & result.supported]
    edge = float(np.min(np.minimum(frequency - scan.frequency_ghz[0],
                                   scan.frequency_ghz[-1] - frequency)) * 1000.0) if frequency.size else -np.inf
    reasons = []
    if coverage < config.min_support_fraction:
        reasons.append(f"measured coverage {coverage:.1%} < {config.min_support_fraction:.0%}")
    if config.branch_preference in {"lower", "upper", "midpoint"} and result.branch != config.branch_preference:
        reasons.append(f"requested {config.branch_preference} branch was not resolved")
    allowed_gap = max(10.0, 2.0 * float(np.median(np.diff(scan.delay_us))))
    if max_gap > allowed_gap:
        reasons.append(f"unsupported gap {max_gap:g} us > {allowed_gap:g} us")
    if edge < config.min_edge_margin_mhz:
        reasons.append(f"edge margin {edge:g} MHz < {config.min_edge_margin_mhz:g} MHz")
    expected_edge = min(result.target_ghz - scan.frequency_ghz[0],
                        scan.frequency_ghz[-1] - result.target_ghz) * 1000.0
    if expected_edge < config.min_edge_margin_mhz:
        reasons.append(f"target edge margin {expected_edge:g} MHz < {config.min_edge_margin_mhz:g} MHz")
    ambiguity_fraction = float(np.mean(np.asarray(result.ambiguity, dtype=bool)[mask] & support))
    if ambiguity_fraction >= 0.10:
        reasons.append(f"unresolved spectral branch ambiguity in {ambiguity_fraction:.1%} of solve window")
    return QualityReport(not reasons, tuple(reasons), coverage, max_gap, edge)


def load_raw_map(path: Path, *, controller: str, dc_unit: str | None = None) -> StepMap:
    """Load a saved full grid without averaging duplicates or inventing cells.

    Historical QICK files sometimes label DAC coordinates ``dc_offset_V``;
    callers must explicitly declare their actual units.
    """
    path = Path(path)
    controller = str(controller).lower()
    if controller not in {"qua", "qick"}:
        raise ValueError("controller must be 'qua' or 'qick'")
    if dc_unit is None:
        if controller == "qick":
            raise ValueError("qick dc_unit must be declared explicitly (V or DAC)")
        dc_unit = "V"
    if dc_unit not in {"V", "DAC"}:
        raise ValueError("dc_unit must be V or DAC")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        fields = set(reader.fieldnames or [])
        required = {"delay_time_us", "qubit_frequency_GHz", "magnitude_dBm"}
        if required - fields:
            raise ValueError(f"raw map lacks columns {sorted(required - fields)}")
        rows = list(reader)
    if not rows:
        raise ValueError("raw map is empty")
    cells: dict[tuple[float, float], dict] = {}
    dc_values: set[float] = set()
    for row in rows:
        time = float(row["delay_time_us"])
        frequency = float(row["qubit_frequency_GHz"])
        if not np.isfinite(time) or not np.isfinite(frequency):
            raise ValueError("raw map contains nonfinite coordinates")
        cell = (frequency, time)
        if cell in cells:
            raise ValueError(f"duplicate (frequency_GHz, delay_us) cell {cell}")
        cells[cell] = row
        if "dc_offset_V" in row and row["dc_offset_V"]:
            dc_values.add(float(row["dc_offset_V"]))
    frequency = np.asarray(sorted({key[0] for key in cells}), dtype=float)
    delay = np.asarray(sorted({key[1] for key in cells}), dtype=float)
    missing = [(float(f), float(t)) for f in frequency for t in delay if (f, t) not in cells]
    if missing:
        raise ValueError(f"missing (frequency_GHz, delay_us) cell {missing[0]}")
    magnitude = np.asarray(
        [[float(cells[(float(f), float(t))]["magnitude_dBm"]) for t in delay] for f in frequency],
        dtype=float,
    )
    phase = None
    if "phase_rad" in fields:
        phase = np.asarray(
            [[float(cells[(float(f), float(t))]["phase_rad"]) for t in delay] for f in frequency],
            dtype=float,
        )
    if len(dc_values) > 1:
        raise ValueError(f"raw map has multiple dc_offset_V values: {sorted(dc_values)}")
    metadata = {
        "controller": controller,
        "dc_unit": dc_unit,
        "dc_offset": next(iter(dc_values)) if dc_values else None,
        "source_path": str(path),
        "source_sha256": digest,
    }
    return StepMap(frequency, delay, magnitude, phase, metadata)
