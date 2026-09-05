import csv
from dataclasses import asdict, dataclass
import math
from pathlib import Path

import numpy as np

from .records import TerminalStatus


@dataclass(frozen=True)
class ReferenceAxis:
    ground_i: float
    ground_q: float
    delta_i: float
    delta_q: float
    denominator: float

    @classmethod
    def from_centers(cls, ground_i, ground_q, excited_i, excited_q):
        di = float(excited_i) - float(ground_i)
        dq = float(excited_q) - float(ground_q)
        denominator = di * di + dq * dq
        if not math.isfinite(denominator) or denominator <= 0:
            raise ValueError("ground and excited reference centers coincide")
        return cls(float(ground_i), float(ground_q), di, dq, denominator)

    def population(self, i_values, q_values):
        i_values = np.asarray(i_values, dtype=float)
        q_values = np.asarray(q_values, dtype=float)
        return (
            (i_values - self.ground_i) * self.delta_i
            + (q_values - self.ground_q) * self.delta_q
        ) / self.denominator

    def mean_population(self, i_values, q_values):
        values = self.population(i_values, q_values)
        return float(np.mean(values)) if values.size else float("nan")

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, values):
        return cls(**dict(values))


def wilson_interval(successes, trials, z=1.959963984540054):
    successes, trials = int(successes), int(trials)
    if trials <= 0:
        return float("nan"), float("nan")
    if successes < 0 or successes > trials:
        raise ValueError("successes must lie between zero and trials")
    proportion = successes / trials
    denominator = 1.0 + z * z / trials
    center = (proportion + z * z / (2.0 * trials)) / denominator
    half = z * math.sqrt(
        proportion * (1.0 - proportion) / trials + z * z / (4.0 * trials * trials)
    ) / denominator
    return float(center - half), float(center + half)


def assignment_threshold(calibration):
    metrics = calibration.holdout or {}
    if "ground_median" in metrics and "excited_median" in metrics:
        return 0.5 * (float(metrics["ground_median"]) + float(metrics["excited_median"]))
    return 0.5 * (
        float(calibration.ground_threshold) + float(calibration.excited_threshold)
    )


def verification_excited(records, assignment):
    if not records:
        return np.asarray([], dtype=bool)
    i_values = np.asarray([record.final_i for record in records], dtype=np.int64)
    q_values = np.asarray([record.final_q for record in records], dtype=np.int64)
    projected = assignment.project(i_values, q_values)
    return projected > assignment_threshold(assignment)


def summarize_records(records, axis, assignment):
    records = list(records)
    if not records:
        return {
            "shots": 0,
            "timeout_fraction": float("nan"),
            "verification_excited_fraction": float("nan"),
            "verification_excited_ci95": (float("nan"), float("nan")),
            "verification_population": float("nan"),
        }
    excited = verification_excited(records, assignment)
    timeouts = np.asarray([
        record.terminal_status is TerminalStatus.MAX_ITERATIONS_REACHED
        for record in records
    ])
    attempts = np.asarray([record.reset_attempts for record in records], dtype=float)
    pi_pulses = np.asarray([record.pi_pulses for record in records], dtype=float)
    i_values = np.asarray([record.final_i for record in records], dtype=float)
    q_values = np.asarray([record.final_q for record in records], dtype=float)
    confirmed = ~timeouts
    n_excited = int(np.count_nonzero(excited))
    conditional = excited[confirmed]
    return {
        "shots": len(records),
        "timeouts": int(np.count_nonzero(timeouts)),
        "timeout_fraction": float(np.mean(timeouts)),
        "verification_excited": n_excited,
        "verification_excited_fraction": float(np.mean(excited)),
        "verification_excited_ci95": wilson_interval(n_excited, len(records)),
        "verification_excited_confirmed_fraction": (
            float(np.mean(conditional)) if conditional.size else float("nan")
        ),
        "verification_population": axis.mean_population(i_values, q_values),
        "mean_reset_attempts": float(np.mean(attempts)),
        "p95_reset_attempts": float(np.percentile(attempts, 95)),
        "mean_pi_pulses": (
            float(np.mean(pi_pulses[pi_pulses >= 0]))
            if np.any(pi_pulses >= 0) else float("nan")
        ),
    }


CSV_FIELDS = (
    "block",
    "method",
    "preparation",
    "initial_z",
    "reset_attempts",
    "pi_pulses",
    "terminal_status",
    "final_i",
    "final_q",
    "last_z",
    "verification_excited",
    "verification_population",
)


def append_records_csv(path, records, *, axis, assignment, method, block):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    records = list(records)
    excited = verification_excited(records, assignment)
    populations = axis.population(
        [record.final_i for record in records], [record.final_q for record in records]
    )
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        if not exists:
            writer.writeheader()
        for record, is_excited, population in zip(records, excited, populations):
            writer.writerow({
                "block": int(block),
                "method": str(method),
                "preparation": int(record.preparation),
                "initial_z": int(record.initial_z),
                "reset_attempts": int(record.reset_attempts),
                "pi_pulses": int(record.pi_pulses),
                "terminal_status": record.terminal_status.name,
                "final_i": int(record.final_i),
                "final_q": int(record.final_q),
                "last_z": int(record.last_z),
                "verification_excited": int(bool(is_excited)),
                "verification_population": float(population),
            })


def build_interleaved_schedule(*, methods, blocks, seed=None):
    methods = tuple(str(method) for method in methods)
    if not methods:
        raise ValueError("at least one benchmark method is required")
    if int(blocks) <= 0:
        raise ValueError("blocks must be positive")
    rng = np.random.default_rng(seed)
    schedule = []
    conditions = [(method, prep) for method in methods for prep in (0, 1)]
    for block in range(int(blocks)):
        for index in rng.permutation(len(conditions)):
            method, prep = conditions[int(index)]
            schedule.append((block, method, prep))
    return schedule


def summarize_post_readout_pi(
    *,
    pre_pi_delay_us,
    read_delay_us,
    first_ground_population,
    first_pi_population,
    second_ground_population,
    second_pi_population,
    min_transfer_contrast,
    max_first_preparation_delta,
    min_second_pi_population,
    max_abs_second_ground_population,
):
    vectors = [
        np.asarray(values, dtype=float).ravel()
        for values in (
            pre_pi_delay_us,
            first_ground_population,
            first_pi_population,
            second_ground_population,
            second_pi_population,
        )
    ]
    lengths = {values.size for values in vectors}
    if len(lengths) != 1 or not lengths or next(iter(lengths)) == 0:
        raise ValueError("post-readout pi vectors must have one matching nonzero length")
    if not all(np.all(np.isfinite(values)) for values in vectors):
        raise ValueError("post-readout pi vectors must be finite")
    delay, first_ground, first_pi, second_ground, second_pi = vectors
    read_delay = float(read_delay_us)
    if not np.isfinite(read_delay) or read_delay < 0:
        raise ValueError("read delay must be finite and nonnegative")
    if np.any(delay < read_delay):
        raise ValueError("pre-pi delay must be at least the read delay")
    rows = []
    for index in range(delay.size):
        first_delta = float(first_pi[index] - first_ground[index])
        contrast = float(second_pi[index] - second_ground[index])
        passed = bool(
            contrast >= float(min_transfer_contrast)
            and abs(first_delta) <= float(max_first_preparation_delta)
            and second_pi[index] >= float(min_second_pi_population)
            and abs(second_ground[index]) <= float(max_abs_second_ground_population)
        )
        rows.append({
            "pre_pi_delay_us": float(delay[index]),
            "first_ground_population": float(first_ground[index]),
            "first_pi_population": float(first_pi[index]),
            "first_preparation_delta": first_delta,
            "second_ground_population": float(second_ground[index]),
            "second_pi_population": float(second_pi[index]),
            "transfer_contrast": contrast,
            "passed": passed,
        })
    selected = next((row for row in rows if row["passed"]), None)
    return {
        "status": "pass" if selected is not None else "fail",
        "selected_pre_pi_delay_us": (
            selected["pre_pi_delay_us"] if selected is not None else None
        ),
        "rows": rows,
    }
