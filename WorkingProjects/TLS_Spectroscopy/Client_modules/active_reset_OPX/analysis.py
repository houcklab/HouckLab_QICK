import csv
from dataclasses import asdict, dataclass
import math
from pathlib import Path

import numpy as np

from .records import TerminalStatus


def json_safe(value):
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def diagnose_rabi_lifecycle(
    *, baseline_rmse, short_interval_rmse, active_short_rmse, max_rmse
):
    values = np.asarray(
        [baseline_rmse, short_interval_rmse, active_short_rmse, max_rmse],
        dtype=float,
    )
    if not np.all(np.isfinite(values)):
        raise ValueError("Rabi lifecycle metrics must be finite")
    if np.any(values[:3] < 0) or values[3] <= 0:
        raise ValueError("Rabi lifecycle RMSE values must be nonnegative")
    baseline_bad, short_bad, active_bad = values[:3] > values[3]
    if baseline_bad:
        return "compact_payload_path"
    if short_bad and active_bad:
        return "short_inter_shot_and_active_reset"
    if short_bad:
        return "short_inter_shot_lifecycle"
    if active_bad:
        return "active_reset_state_machine"
    return "equivalent"


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


def fit_t1_decay(times_us, populations, shots=None):
    from scipy.optimize import curve_fit

    times = np.asarray(times_us, dtype=float).ravel()
    values = np.asarray(populations, dtype=float).ravel()
    if times.size != values.size or times.size < 4:
        raise ValueError("T1 fit needs at least four matching time and population values")
    finite = np.isfinite(times) & np.isfinite(values) & (times >= 0)
    if shots is not None:
        counts = np.asarray(shots, dtype=float).ravel()
        if counts.size != times.size:
            raise ValueError("shots must match the T1 vectors")
        finite &= np.isfinite(counts) & (counts > 0)
    else:
        counts = None
    times = times[finite]
    values = values[finite]
    if counts is not None:
        counts = counts[finite]
    if times.size < 4 or np.unique(times).size < 4:
        raise ValueError("T1 fit needs at least four finite distinct delay values")
    order = np.argsort(times)
    times = times[order]
    values = values[order]
    if counts is not None:
        counts = counts[order]
    contrast = float(np.max(values) - np.min(values))
    if contrast < 1e-6:
        raise ValueError("T1 population contrast is too small to fit")
    p0_seed = float(np.mean(values[-max(2, values.size // 5):]))
    p1_seed = float(values[0])
    amplitude = p1_seed - p0_seed
    target = p0_seed + amplitude / math.e
    tau_seed = max(0.01, float(times[np.argmin(np.abs(values - target))]))
    lower_population = min(-0.5, float(np.min(values)) - 0.25)
    upper_population = max(1.5, float(np.max(values)) + 0.25)
    upper_tau = max(1e6, float(np.max(times)) * 1000.0)
    sigma = None
    if counts is not None:
        clipped = np.clip(values, 0.5 / counts, 1.0 - 0.5 / counts)
        sigma = np.sqrt(clipped * (1.0 - clipped) / counts)
    model = lambda t, p0, p1, tau: p0 + (p1 - p0) * np.exp(-t / tau)
    fitted, covariance = curve_fit(
        model,
        times,
        values,
        p0=[p0_seed, p1_seed, tau_seed],
        sigma=sigma,
        absolute_sigma=sigma is not None,
        bounds=(
            [lower_population, lower_population, 0.01],
            [upper_population, upper_population, upper_tau],
        ),
        maxfev=50000,
    )
    errors = np.sqrt(np.diag(covariance))
    predicted = model(times, *fitted)
    return {
        "P0": float(fitted[0]),
        "P1": float(fitted[1]),
        "tau_us": float(fitted[2]),
        "P0_err": float(errors[0]),
        "P1_err": float(errors[1]),
        "tau_err_us": float(errors[2]),
        "decaying": bool(fitted[1] > fitted[0]),
        "rmse": float(np.sqrt(np.mean((values - predicted) ** 2))),
    }


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
            "max_reset_attempts": float("nan"),
            "p99_reset_attempts": float("nan"),
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
        "p99_reset_attempts": float(np.percentile(attempts, 99)),
        "max_reset_attempts": int(np.max(attempts)),
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


def evaluate_feedback_delay_sweep(
    rows,
    *,
    max_timeout_fraction,
    max_verification_excited_fraction,
):
    timeout_limit = float(max_timeout_fraction)
    residual_limit = float(max_verification_excited_fraction)
    if not 0.0 <= timeout_limit <= 1.0:
        raise ValueError("max_timeout_fraction must be in [0, 1]")
    if not 0.0 <= residual_limit <= 1.0:
        raise ValueError("max_verification_excited_fraction must be in [0, 1]")
    grouped = {}
    for raw in rows:
        row = dict(raw)
        delay = float(row["feedback_syncdelay_us"])
        preparation = int(row["preparation"])
        timeout = float(row["timeout_fraction"])
        residual = float(row["verification_excited_fraction"])
        if not math.isfinite(delay) or delay < 0:
            raise ValueError("feedback_syncdelay_us must be finite and nonnegative")
        if preparation not in (0, 1):
            raise ValueError("preparation must be zero or one")
        if not math.isfinite(timeout) or not 0.0 <= timeout <= 1.0:
            raise ValueError("timeout_fraction must be finite and in [0, 1]")
        if not math.isfinite(residual) or not 0.0 <= residual <= 1.0:
            raise ValueError(
                "verification_excited_fraction must be finite and in [0, 1]"
            )
        if preparation in grouped.setdefault(delay, {}):
            raise ValueError(
                f"duplicate feedback delay/preparation row: {delay}, {preparation}"
            )
        grouped[delay][preparation] = row
    delays = []
    for delay in sorted(grouped):
        preparations = grouped[delay]
        complete = set(preparations) == {0, 1}
        worst_timeout = max(
            (float(row["timeout_fraction"]) for row in preparations.values()),
            default=float("nan"),
        )
        worst_residual = max(
            (
                float(row["verification_excited_fraction"])
                for row in preparations.values()
            ),
            default=float("nan"),
        )
        passed = bool(
            complete
            and worst_timeout <= timeout_limit
            and worst_residual <= residual_limit
        )
        delays.append({
            "feedback_syncdelay_us": delay,
            "complete": complete,
            "worst_timeout_fraction": worst_timeout,
            "worst_verification_excited_fraction": worst_residual,
            "passed": passed,
        })
    selected = next((row for row in delays if row["passed"]), None)
    return {
        "status": "pass" if selected is not None else "fail",
        "selected_feedback_syncdelay_us": (
            selected["feedback_syncdelay_us"] if selected is not None else None
        ),
        "max_timeout_fraction": timeout_limit,
        "max_verification_excited_fraction": residual_limit,
        "delays": delays,
    }


def evaluate_attempt_limit_sweep(
    rows,
    *,
    max_timeout_fraction,
    max_verification_excited_fraction,
):
    timeout_limit = float(max_timeout_fraction)
    residual_limit = float(max_verification_excited_fraction)
    if not 0.0 <= timeout_limit <= 1.0:
        raise ValueError("max_timeout_fraction must be in [0, 1]")
    if not 0.0 <= residual_limit <= 1.0:
        raise ValueError("max_verification_excited_fraction must be in [0, 1]")
    grouped = {}
    for raw in rows:
        row = dict(raw)
        attempts = int(row["max_reset_attempts"])
        preparation = int(row["preparation"])
        timeout = float(row["timeout_fraction"])
        residual = float(row["verification_excited_fraction"])
        if attempts <= 0:
            raise ValueError("max_reset_attempts must be positive")
        if preparation not in (0, 1):
            raise ValueError("preparation must be zero or one")
        if not math.isfinite(timeout) or not 0.0 <= timeout <= 1.0:
            raise ValueError("timeout_fraction must be finite and in [0, 1]")
        if not math.isfinite(residual) or not 0.0 <= residual <= 1.0:
            raise ValueError(
                "verification_excited_fraction must be finite and in [0, 1]"
            )
        if preparation in grouped.setdefault(attempts, {}):
            raise ValueError(
                f"duplicate attempt limit/preparation row: {attempts}, {preparation}"
            )
        grouped[attempts][preparation] = row
    attempt_limits = []
    for attempts in sorted(grouped):
        preparations = grouped[attempts]
        complete = set(preparations) == {0, 1}
        worst_timeout = max(
            (float(row["timeout_fraction"]) for row in preparations.values()),
            default=float("nan"),
        )
        worst_residual = max(
            (
                float(row["verification_excited_fraction"])
                for row in preparations.values()
            ),
            default=float("nan"),
        )
        passed = bool(
            complete
            and worst_timeout <= timeout_limit
            and worst_residual <= residual_limit
        )
        attempt_limits.append({
            "max_reset_attempts": attempts,
            "complete": complete,
            "worst_timeout_fraction": worst_timeout,
            "worst_verification_excited_fraction": worst_residual,
            "passed": passed,
        })
    selected = next((row for row in attempt_limits if row["passed"]), None)
    return {
        "status": "pass" if selected is not None else "fail",
        "selected_max_reset_attempts": (
            selected["max_reset_attempts"] if selected is not None else None
        ),
        "max_timeout_fraction": timeout_limit,
        "max_verification_excited_fraction": residual_limit,
        "attempt_limits": attempt_limits,
    }
