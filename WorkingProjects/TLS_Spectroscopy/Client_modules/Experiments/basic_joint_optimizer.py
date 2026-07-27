
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Mapping, Sequence

import numpy as np
from scipy.special import ndtr


PHYSICAL_KEYS = (
    "read_pulse_freq", "read_pulse_gain", "read_length",
    "qubit_freq", "qubit_pi_freq", "qubit_pi_gain", "sigma",
    "qubit_drag_beta",
)


def _finite_float(value, default=float("nan")):
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return float(default)
    return value if np.isfinite(value) else float(default)


@dataclass(frozen=True)
class PulseCandidate:

    read_pulse_freq: float
    read_pulse_gain: int
    read_length: float
    qubit_freq: float
    qubit_pi_freq: float
    qubit_pi_gain: int
    sigma: float
    qubit_drag_beta: float = 0.0

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "PulseCandidate":
        qubit_pi_freq = float(value["qubit_pi_freq"])
        return cls(
            read_pulse_freq=float(value["read_pulse_freq"]),
            read_pulse_gain=int(round(float(value["read_pulse_gain"]))),
            read_length=float(value["read_length"]),
            qubit_freq=float(value.get("qubit_freq", qubit_pi_freq)),
            qubit_pi_freq=qubit_pi_freq,
            qubit_pi_gain=int(round(float(value["qubit_pi_gain"]))),
            sigma=float(value["sigma"]),
            qubit_drag_beta=float(value.get("qubit_drag_beta", 0.0) or 0.0),
        )

    def __post_init__(self):
        numeric = (
            self.read_pulse_freq, self.read_length, self.qubit_freq,
            self.qubit_pi_freq, self.sigma, self.qubit_drag_beta,
        )
        if not all(np.isfinite(value) for value in numeric):
            raise ValueError("candidate fields must be finite")
        if self.read_length <= 0.0 or self.sigma <= 0.0:
            raise ValueError("read_length and sigma must be positive")
        if not 0 <= self.read_pulse_gain <= 32767:
            raise ValueError("read_pulse_gain is outside the DAC range")
        if not 0 < self.qubit_pi_gain <= 32767:
            raise ValueError("qubit_pi_gain is outside the DAC range")

    def as_dict(self) -> dict:
        return {key: getattr(self, key) for key in PHYSICAL_KEYS}

    def key(self) -> tuple:
        return (
            round(self.read_pulse_freq, 9), self.read_pulse_gain,
            round(self.read_length, 9), round(self.qubit_pi_freq, 9),
            self.qubit_pi_gain, round(self.sigma, 9),
            round(self.qubit_drag_beta, 9),
        )

    def duration_key(self) -> tuple:
        return (round(self.read_length, 9), round(self.sigma, 9))

    def chain_latency_us(self) -> float:
        return float(self.read_length + 4.0 * self.sigma)

    def changed(self, **changes) -> "PulseCandidate":
        values = self.as_dict()
        values.update(changes)
        if "qubit_pi_freq" in changes and "qubit_freq" not in changes:
            values["qubit_freq"] = changes["qubit_pi_freq"]
        if "qubit_freq" in changes and "qubit_pi_freq" not in changes:
            values["qubit_pi_freq"] = changes["qubit_freq"]
        return PulseCandidate.from_mapping(values)


class CandidateArchive:

    def __init__(self, sink=None):
        self.rows = sink if sink is not None else []

    def append(self, row: Mapping[str, object], *, stage: str,
               fidelity_level: str, epoch: int) -> dict:
        candidate = PulseCandidate.from_mapping(row)
        saved = dict(row)
        saved.update({
            "candidate_key": candidate.key(),
            "duration_key": candidate.duration_key(),
            "chain_latency_us": candidate.chain_latency_us(),
            "search_stage": str(stage),
            "fidelity_level": str(fidelity_level),
            "drift_epoch": int(epoch),
            "archive_serial": len(self.rows),
        })
        self.rows.append(saved)
        return saved

    def candidates(self, *, stage=None, epoch=None) -> list[dict]:
        rows = list(self.rows)
        if stage is not None:
            rows = [row for row in rows if row.get("search_stage") == stage]
        if epoch is not None:
            rows = [row for row in rows if int(row.get(
                "drift_epoch", -1)) == int(epoch)]
        return rows


def fidelity_evidence(row: Mapping[str, object]) -> tuple[float, float, float]:
    mean = _finite_float(row.get("crossfit_fidelity"))
    se = _finite_float(row.get("crossfit_fidelity_se"), float("inf"))
    lcb = _finite_float(row.get("crossfit_fidelity_lcb_95"))
    if not np.isfinite(mean) or not np.isfinite(se):
        mean = _finite_float(row.get("fidelity"), -float("inf"))
        se = _finite_float(row.get("fidelity_se"), float("inf"))
        lcb = _finite_float(row.get("fidelity_lcb_95"))
    if not np.isfinite(lcb) and np.isfinite(mean) and np.isfinite(se):
        lcb = float(mean - 1.96 * se)
    return float(mean), float(se), float(lcb)


def _row_rank(row: Mapping[str, object]) -> tuple:
    mean, se, lcb = fidelity_evidence(row)
    try:
        latency = PulseCandidate.from_mapping(row).chain_latency_us()
    except Exception:
        latency = float("inf")
    return (lcb, mean, -se, -latency)


def unique_candidate_rows(rows: Iterable[Mapping[str, object]]) -> list[dict]:
    best = {}
    order = []
    for source in rows:
        row = dict(source)
        try:
            key = PulseCandidate.from_mapping(row).key()
        except Exception:
            continue
        if key not in best:
            best[key] = row
            order.append(key)
        elif _row_rank(row) > _row_rank(best[key]):
            best[key] = row
    return [best[key] for key in order]


def duration_stratified_shortlist(
        rows: Sequence[Mapping[str, object]], *, per_stratum: int = 1,
        global_count: int = 24, maximum: int | None = None) -> list[dict]:
    rows = unique_candidate_rows(rows)
    grouped = {}
    for row in rows:
        candidate = PulseCandidate.from_mapping(row)
        grouped.setdefault(candidate.duration_key(), []).append(row)
    selected = []
    per_stratum = max(int(per_stratum), 0)
    if per_stratum:
        for key in sorted(grouped):
            selected.extend(sorted(grouped[key], key=_row_rank, reverse=True)[
                :per_stratum])
    selected.extend(sorted(rows, key=_row_rank, reverse=True)[
                    :max(int(global_count), 0)])
    selected = unique_candidate_rows(selected)
    if maximum is not None and len(selected) > int(maximum):
        mandatory_keys = ({
            PulseCandidate.from_mapping(sorted(
                grouped[key], key=_row_rank, reverse=True)[0]).key()
            for key in grouped
        } if per_stratum else set())
        mandatory = [row for row in selected
                     if PulseCandidate.from_mapping(row).key() in mandatory_keys]
        optional = [row for row in selected
                    if PulseCandidate.from_mapping(row).key() not in mandatory_keys]
        room = max(int(maximum) - len(mandatory), 0)
        selected = mandatory + sorted(optional, key=_row_rank, reverse=True)[:room]
    return selected


def latency_pareto_frontier(rows: Sequence[Mapping[str, object]]) -> list[dict]:
    unique = unique_candidate_rows(rows)
    ordered = sorted(unique, key=lambda row: (
        PulseCandidate.from_mapping(row).chain_latency_us(),
        -fidelity_evidence(row)[0]))
    frontier = []
    best_fidelity = -float("inf")
    for row in ordered:
        mean = fidelity_evidence(row)[0]
        if mean > best_fidelity + 1e-12:
            frontier.append(row)
            best_fidelity = mean
    return frontier


def select_shortest_noninferior(
        rows: Sequence[Mapping[str, object]], reference: Mapping[str, object],
        *, max_loss: float = 0.005, confidence_z: float = 1.96,
        minimum_mean: float = 0.85, minimum_lcb: float = 0.82) -> tuple[dict, list]:
    ref_mean, ref_se, _ = fidelity_evidence(reference)
    diagnostics = []
    eligible = []
    for row in unique_candidate_rows(rows):
        mean, se, lcb = fidelity_evidence(row)
        loss = ref_mean - mean
        loss_se = math.hypot(ref_se, se)
        loss_ucb = float(loss + float(confidence_z) * loss_se)
        accepted = bool(
            np.all(np.isfinite([mean, se, lcb, loss_ucb]))
            and mean >= float(minimum_mean)
            and lcb >= float(minimum_lcb)
            and loss_ucb <= float(max_loss))
        diagnostic = {
            "candidate_key": PulseCandidate.from_mapping(row).key(),
            "latency_us": PulseCandidate.from_mapping(row).chain_latency_us(),
            "fidelity": mean, "fidelity_lcb": lcb,
            "loss": float(loss), "loss_ucb": loss_ucb,
            "accepted": accepted,
        }
        diagnostics.append(diagnostic)
        if accepted:
            eligible.append(row)
    if not eligible:
        return dict(reference), diagnostics
    chosen = min(eligible, key=lambda row: (
        PulseCandidate.from_mapping(row).chain_latency_us(),
        -fidelity_evidence(row)[2], -fidelity_evidence(row)[0]))
    return dict(chosen), diagnostics


def _feature_bounds(rows, proposal_limits):
    names = (
        "read_pulse_freq", "read_pulse_gain", "read_length",
        "qubit_pi_freq", "qubit_pi_gain", "sigma",
    )
    lows, highs = [], []
    for name in names:
        if name in proposal_limits:
            low, high = proposal_limits[name]
        else:
            values = np.asarray([float(row[name]) for row in rows], dtype=float)
            low, high = float(np.min(values)), float(np.max(values))
        if not np.isfinite(low) or not np.isfinite(high):
            raise ValueError("non-finite surrogate feature bounds")
        if high <= low:
            pad = max(abs(low) * 1e-6, 1e-6)
            low, high = low - pad, high + pad
        lows.append(float(low))
        highs.append(float(high))
    return names, np.asarray(lows), np.asarray(highs)


def _features(rows, names, lows, highs):
    values = np.asarray([[float(row[name]) for name in names]
                         for row in rows], dtype=float)
    for index, name in enumerate(names):
        if name in ("read_pulse_gain", "read_length", "qubit_pi_gain", "sigma"):
            values[:, index] = np.log(np.maximum(values[:, index], 1e-12))
            lows[index] = math.log(max(lows[index], 1e-12))
            highs[index] = math.log(max(highs[index], 1e-12))
    return np.clip((values - lows) / (highs - lows), 0.0, 1.0)


def _matern52(left, right, length_scale=0.22):
    delta = left[:, None, :] - right[None, :, :]
    radius = np.sqrt(np.sum(delta * delta, axis=2)) / max(float(length_scale), 1e-9)
    root5 = math.sqrt(5.0)
    return (1.0 + root5 * radius + (5.0 / 3.0) * radius ** 2) * np.exp(
        -root5 * radius)


def _surrogate_training_subset(rows, rng, maximum=420):
    rows = unique_candidate_rows(rows)
    if len(rows) <= int(maximum):
        return rows
    ranked = sorted(rows, key=_row_rank, reverse=True)
    elite_count = min(max(int(maximum) // 2, 1), len(ranked))
    elite = ranked[:elite_count]
    remainder = ranked[elite_count:]
    random_count = max(int(maximum) - len(elite), 0)
    indices = rng.choice(len(remainder), size=random_count, replace=False)
    return elite + [remainder[int(index)] for index in indices]


def propose_trust_region_candidates(
        rows: Sequence[Mapping[str, object]], *, rng: np.random.Generator,
        count: int, proposal_limits: Mapping[str, tuple],
        read_frequency_radius_mhz: float = 0.40,
        qubit_frequency_radius_mhz: float = 0.70,
        read_gain_fraction: float = 0.30,
        qubit_gain_fraction: float = 0.30,
        trust_regions: int = 6, pool_size: int = 3000,
        length_scale: float = 0.22) -> list[dict]:
    usable = [dict(row) for row in rows if np.isfinite(fidelity_evidence(row)[0])]
    if not usable or int(count) <= 0:
        return []
    training = _surrogate_training_subset(usable, rng)
    names, lows, highs = _feature_bounds(training, proposal_limits)
    feature_lows, feature_highs = lows.copy(), highs.copy()
    x = _features(training, names, feature_lows, feature_highs)
    y = np.asarray([fidelity_evidence(row)[0] for row in training], dtype=float)
    noise = np.asarray([max(fidelity_evidence(row)[1], 0.002) ** 2
                        for row in training], dtype=float)
    mean_y = float(np.mean(y))
    scale_y = max(float(np.std(y)), 0.01)
    target = (y - mean_y) / scale_y
    kernel = _matern52(x, x, length_scale=length_scale)
    kernel.flat[::kernel.shape[0] + 1] += noise / (scale_y ** 2) + 1e-7
    try:
        chol = np.linalg.cholesky(kernel)
        alpha = np.linalg.solve(chol.T, np.linalg.solve(chol, target))
    except np.linalg.LinAlgError:
        return []

    centres = duration_stratified_shortlist(
        usable, per_stratum=0, global_count=max(int(trust_regions), 1),
        maximum=max(int(trust_regions), 1))
    if not centres:
        centres = sorted(usable, key=_row_rank, reverse=True)[:1]
    pool = []
    each = max(int(math.ceil(float(pool_size) / len(centres))), 1)
    for center_row in centres:
        center = PulseCandidate.from_mapping(center_row)
        for _ in range(each):
            read_freq = float(np.clip(
                center.read_pulse_freq + rng.uniform(
                    -read_frequency_radius_mhz, read_frequency_radius_mhz),
                *proposal_limits["read_pulse_freq"]))
            qubit_freq = float(np.clip(
                center.qubit_pi_freq + rng.uniform(
                    -qubit_frequency_radius_mhz, qubit_frequency_radius_mhz),
                *proposal_limits["qubit_pi_freq"]))
            read_gain = int(np.clip(round(
                center.read_pulse_gain * math.exp(rng.uniform(
                    -read_gain_fraction, read_gain_fraction))),
                *proposal_limits["read_pulse_gain"]))
            qubit_gain = int(np.clip(round(
                center.qubit_pi_gain * math.exp(rng.uniform(
                    -qubit_gain_fraction, qubit_gain_fraction))),
                *proposal_limits["qubit_pi_gain"]))
            pool.append(center.changed(
                read_pulse_freq=read_freq,
                read_pulse_gain=read_gain,
                qubit_pi_freq=qubit_freq,
                qubit_pi_gain=qubit_gain).as_dict())
    pool = unique_candidate_rows(pool)
    if not pool:
        return []
    pool_x = _features(pool, names, lows.copy(), highs.copy())
    cross = _matern52(pool_x, x, length_scale=length_scale)
    predicted = mean_y + scale_y * (cross @ alpha)
    solved = np.linalg.solve(chol, cross.T)
    variance = np.maximum(1.0 - np.sum(solved * solved, axis=0), 1e-10)
    sigma = scale_y * np.sqrt(variance)
    best = max(fidelity_evidence(row)[0] for row in usable)
    improvement = predicted - best
    z = improvement / np.maximum(sigma, 1e-12)
    expected_improvement = (improvement * ndtr(z)
                            + sigma * np.exp(-0.5 * z * z)
                            / math.sqrt(2.0 * math.pi))

    selected = []
    available = np.ones(len(pool), dtype=bool)
    existing_keys = {PulseCandidate.from_mapping(row).key() for row in usable}
    for _ in range(min(int(count), len(pool))):
        score = np.where(available, expected_improvement, -np.inf)
        if selected:
            chosen_x = pool_x[np.asarray(selected)]
            distance = np.min(np.sqrt(np.sum(
                (pool_x[:, None, :] - chosen_x[None, :, :]) ** 2, axis=2)), axis=1)
            score *= np.clip(distance / 0.12, 0.05, 1.0)
        index = int(np.argmax(score))
        if not np.isfinite(score[index]):
            break
        key = PulseCandidate.from_mapping(pool[index]).key()
        available[index] = False
        if key in existing_keys:
            continue
        existing_keys.add(key)
        selected.append(index)
    return [pool[index] for index in selected]


def validate_structured_coverage(rows, read_lengths, sigmas) -> dict:
    measured = {
        PulseCandidate.from_mapping(row).duration_key() for row in rows
        if all(key in row for key in PHYSICAL_KEYS)
    }
    expected = {
        (round(float(read_length), 9), round(float(sigma), 9))
        for read_length in read_lengths for sigma in sigmas
    }
    missing = sorted(expected - measured)
    return {
        "complete": not missing,
        "expected_strata": len(expected),
        "measured_strata": len(expected & measured),
        "missing_strata": missing,
    }
