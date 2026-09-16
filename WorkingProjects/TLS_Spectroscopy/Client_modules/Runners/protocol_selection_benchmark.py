"""Canonical, hardware-free plan for the QICK protocol-selection benchmark."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json

import numpy as np


_SCHEMA = "houcklab.protocol-selection-benchmark.v1"
_PROTOCOL_DELAYS_US = {
    "3pt_ts50": (50.0,),
    "3pt_ts100": (100.0,),
    "5pt": (40.0, 80.0, 200.0),
    "7pt": (40.0, 80.0, 120.0, 160.0, 200.0),
}


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


def _decimal(value: float) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("frequency fields must be finite decimal values") from exc


def _validate_plan(plan: BenchmarkPlan) -> None:
    if plan.schema != _SCHEMA:
        raise ValueError(f"unsupported benchmark schema: {plan.schema!r}")
    if plan.reset_mode != "active":
        raise ValueError("benchmark reset mode must be active")
    if plan.readout_location != "park":
        raise ValueError("benchmark readout location must be park")
    if plan.calibration_policy != "once":
        raise ValueError("benchmark calibration policy must be once")

    start = _decimal(plan.frequency_start_ghz)
    stop = _decimal(plan.frequency_stop_ghz)
    step_mhz = _decimal(plan.frequency_step_mhz)
    if not start.is_finite() or not stop.is_finite() or not step_mhz.is_finite():
        raise ValueError("frequency fields must be finite")
    if start <= stop or step_mhz <= 0:
        raise ValueError("frequency grid must descend with a positive step")
    step_ghz = step_mhz / Decimal("1000")
    intervals = (start - stop) / step_ghz
    if intervals != intervals.to_integral_value():
        raise ValueError("frequency endpoints must align exactly with the step")
    if plan.frequency_count != int(intervals) + 1:
        raise ValueError("frequency count does not match the exact grid arithmetic")

    for expected_index, benchmark_pass in enumerate(plan.passes):
        if benchmark_pass.index != expected_index:
            raise ValueError("benchmark pass indices must be sequential")
        expected_delays = _PROTOCOL_DELAYS_US.get(benchmark_pass.protocol)
        if expected_delays is None:
            raise ValueError(f"unknown benchmark protocol: {benchmark_pass.protocol!r}")
        if tuple(benchmark_pass.delays_us) != expected_delays:
            raise ValueError("benchmark protocol delays do not match its canonical definition")
        if (
            not benchmark_pass.delays_us
            or any(delay <= 0 for delay in benchmark_pass.delays_us)
            or any(
                following <= preceding
                for preceding, following in zip(
                    benchmark_pass.delays_us, benchmark_pass.delays_us[1:]
                )
            )
        ):
            raise ValueError("benchmark delays must be positive and increasing")
        if benchmark_pass.predistortion not in {"on", "off"}:
            raise ValueError("predistortion must be 'on' or 'off'")
        if benchmark_pass.shots_per_condition <= 0:
            raise ValueError("shots per condition must be positive")
        if benchmark_pass.condition_count != 2 + len(benchmark_pass.delays_us):
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
