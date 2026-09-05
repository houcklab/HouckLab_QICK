from collections import defaultdict

import numpy as np

from .analysis import fit_t1_decay


def normalize_classifier(calibration):
    scale_factor = float(calibration.get("scale_factor", 1.0))
    if scale_factor not in (-1.0, 1.0):
        raise ValueError("scale_factor must be -1 or 1")
    threshold = float(calibration["threshold"])
    ground_threshold = float(calibration["ground_threshold"])
    if not np.all(np.isfinite([threshold, ground_threshold])):
        raise ValueError("classifier thresholds must be finite")
    if scale_factor < 0:
        ground_threshold = -ground_threshold
    return {
        "scale_factor": scale_factor,
        "threshold": threshold,
        "ground_threshold": ground_threshold,
    }


def build_interleaved_schedule(rounds, methods, delay_count, seed):
    rounds = int(rounds)
    methods = tuple(str(value) for value in methods)
    delay_count = int(delay_count)
    if rounds <= 0 or delay_count <= 0:
        raise ValueError("rounds and delay_count must be positive")
    if not methods or len(set(methods)) != len(methods):
        raise ValueError("methods must be nonempty and unique")
    rng = np.random.default_rng(int(seed))
    schedule = []
    for round_index in range(rounds):
        for delay_index in rng.permutation(delay_count):
            for method_index in rng.permutation(len(methods)):
                schedule.append((round_index, int(method_index), int(delay_index)))
    return schedule


def _normalized_records(records, methods, delays_us):
    methods = tuple(str(value) for value in methods)
    delays_us = np.asarray(delays_us, dtype=float).ravel()
    if not methods or len(set(methods)) != len(methods):
        raise ValueError("methods must be nonempty and unique")
    if delays_us.size == 0 or not np.all(np.isfinite(delays_us)) or np.any(delays_us <= 0):
        raise ValueError("delays_us must be finite and positive")
    required = {
        "round",
        "method_code",
        "delay_index",
        "shot_index",
        "state",
        "reset_attempts",
        "timestamp_ns",
    }
    normalized = []
    for record in records:
        missing = required.difference(record)
        if missing:
            raise ValueError(f"shot record is missing {sorted(missing)}")
        row = {
            "round": int(record["round"]),
            "method_code": int(record["method_code"]),
            "delay_index": int(record["delay_index"]),
            "shot_index": int(record["shot_index"]),
            "state": int(record["state"]),
            "reset_attempts": int(record["reset_attempts"]),
            "timestamp_ns": int(record["timestamp_ns"]),
        }
        if row["round"] < 0 or row["shot_index"] < 0:
            raise ValueError("round and shot_index must be nonnegative")
        if row["method_code"] < 0 or row["method_code"] >= len(methods):
            raise ValueError("method_code is out of range")
        if row["delay_index"] < 0 or row["delay_index"] >= delays_us.size:
            raise ValueError("delay_index is out of range")
        if row["state"] not in (0, 1) or row["reset_attempts"] < 0:
            raise ValueError("state must be binary and reset_attempts nonnegative")
        normalized.append(row)
    if not normalized:
        raise ValueError("records must not be empty")
    return normalized, methods, delays_us


def _duration_ns(rows):
    timestamps = np.sort(np.asarray([row["timestamp_ns"] for row in rows], dtype=np.int64))
    if timestamps.size < 2:
        return 0
    differences = np.diff(timestamps)
    positive = differences[differences > 0]
    cadence = int(np.median(positive)) if positive.size else 0
    return int(timestamps[-1] - timestamps[0] + cadence)


def _reduce_group(rows, methods, delays_us, include_round=False, include_shot=False):
    first = rows[0]
    states = np.asarray([row["state"] for row in rows], dtype=int)
    attempts = np.asarray([row["reset_attempts"] for row in rows], dtype=int)
    output = {
        "method": methods[first["method_code"]],
        "method_code": first["method_code"],
        "delay_index": first["delay_index"],
        "delay_us": float(delays_us[first["delay_index"]]),
        "shots": int(states.size),
        "excited_count": int(np.sum(states)),
        "excited_fraction": float(np.mean(states)),
        "reset_attempt_mean": float(np.mean(attempts)),
        "reset_attempt_p95": float(np.percentile(attempts, 95)),
        "reset_attempt_max": int(np.max(attempts)),
        "elapsed_ns": _duration_ns(rows),
    }
    if include_round:
        output["round"] = first["round"]
    if include_shot:
        output["shot_index"] = first["shot_index"]
    return output


def summarize_shots(records, methods, delays_us):
    records, methods, delays_us = _normalized_records(records, methods, delays_us)
    overall_groups = defaultdict(list)
    round_groups = defaultdict(list)
    shot_groups = defaultdict(list)
    for row in records:
        pair = (row["method_code"], row["delay_index"])
        overall_groups[pair].append(row)
        round_groups[(row["round"], *pair)].append(row)
        shot_groups[(*pair, row["shot_index"])].append(row)
    overall = [
        _reduce_group(overall_groups[key], methods, delays_us)
        for key in sorted(overall_groups)
    ]
    rounds = [
        _reduce_group(round_groups[key], methods, delays_us, include_round=True)
        for key in sorted(round_groups)
    ]
    shot_order = [
        _reduce_group(shot_groups[key], methods, delays_us, include_shot=True)
        for key in sorted(shot_groups)
    ]
    return {"overall": overall, "rounds": rounds, "shot_order": shot_order}


def fit_method_decays(summary_rows, methods):
    methods = tuple(str(value) for value in methods)
    fits = {}
    errors = {}
    for method in methods:
        selected = sorted(
            (row for row in summary_rows if str(row["method"]) == method),
            key=lambda row: int(row["delay_index"]),
        )
        try:
            fits[method] = fit_t1_decay(
                [row["delay_us"] for row in selected],
                [row["excited_fraction"] for row in selected],
                shots=[row["shots"] for row in selected],
            )
        except Exception as exc:
            errors[method] = f"{type(exc).__name__}: {exc}"
    return {"fits": fits, "errors": errors}


def make_comparison(fits, passive_method):
    passive_method = str(passive_method)
    if passive_method not in fits:
        raise ValueError("passive fit is missing")
    passive = fits[passive_method]
    passive_tau = float(passive["tau_us"])
    if not np.isfinite(passive_tau) or passive_tau <= 0:
        raise ValueError("passive T1 must be finite and positive")
    output = []
    for method, fit in fits.items():
        output.append(
            {
                "method": str(method),
                "tau_us": float(fit["tau_us"]),
                "tau_err_us": float(fit["tau_err_us"]),
                "tau_ratio_to_passive": float(fit["tau_us"]) / passive_tau,
                "P0": float(fit["P0"]),
                "P1": float(fit["P1"]),
                "P0_difference_from_passive": float(fit["P0"] - passive["P0"]),
                "P1_difference_from_passive": float(fit["P1"] - passive["P1"]),
                "rmse": float(fit["rmse"]),
            }
        )
    return output


def summarize_block_timings(records, methods, passive_method):
    methods = tuple(str(value) for value in methods)
    passive_method = str(passive_method)
    if passive_method not in methods:
        raise ValueError("passive method is missing")
    blocks = defaultdict(list)
    for record in records:
        required = {"block_index", "method_code", "shot_index", "timestamp_ns"}
        missing = required.difference(record)
        if missing:
            raise ValueError(f"timing record is missing {sorted(missing)}")
        method_code = int(record["method_code"])
        if method_code < 0 or method_code >= len(methods):
            raise ValueError("method_code is out of range")
        blocks[int(record["block_index"])].append(
            {
                "method_code": method_code,
                "shot_index": int(record["shot_index"]),
                "timestamp_ns": int(record["timestamp_ns"]),
            }
        )
    ordered = []
    for block_index in sorted(blocks):
        rows = blocks[block_index]
        method_codes = {row["method_code"] for row in rows}
        if len(method_codes) != 1:
            raise ValueError("each block must contain one method")
        ordered.append(
            {
                "block_index": block_index,
                "method_code": next(iter(method_codes)),
                "shots": len(rows),
                "start_ns": min(row["timestamp_ns"] for row in rows),
            }
        )
    per_method = defaultdict(list)
    for current, following in zip(ordered[:-1], ordered[1:]):
        elapsed = following["start_ns"] - current["start_ns"]
        if elapsed > 0 and current["shots"] > 0:
            per_method[current["method_code"]].append(elapsed / current["shots"])
    passive_code = methods.index(passive_method)
    if not per_method[passive_code]:
        raise ValueError("passive timing has no complete blocks")
    passive_median = float(np.median(per_method[passive_code]))
    output = []
    for method_code, method in enumerate(methods):
        values = np.asarray(per_method.get(method_code, ()), dtype=float)
        if values.size == 0:
            continue
        median = float(np.median(values))
        output.append(
            {
                "method": method,
                "complete_blocks": int(values.size),
                "median_ns_per_shot": median,
                "mean_ns_per_shot": float(np.mean(values)),
                "speedup_to_passive": passive_median / median,
            }
        )
    return output
