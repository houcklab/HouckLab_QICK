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


def diagnose_t1_flux_lifecycle(*, short_passed, reset_passed, combined_passed):
    short_passed = bool(short_passed)
    reset_passed = bool(reset_passed)
    combined_passed = bool(combined_passed)
    if short_passed and reset_passed and combined_passed:
        return "equivalent"
    if short_passed and reset_passed:
        return "short_inter_shot_active_reset_interaction"
    if not short_passed and reset_passed:
        return "short_inter_shot_lifecycle"
    if short_passed and not reset_passed:
        return "active_reset_lifecycle"
    return "short_inter_shot_and_active_reset"


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


def resolve_t1_delays(*, explicit_delays_us, minimum_us, maximum_us, points):
    if explicit_delays_us is None:
        minimum = float(minimum_us)
        maximum = float(maximum_us)
        count = int(points)
        if not np.isfinite(minimum) or not np.isfinite(maximum):
            raise ValueError("T1 delay limits must be finite")
        if minimum <= 0 or maximum <= minimum or count < 4:
            raise ValueError("T1 logspace needs 0 < minimum < maximum and at least 4 points")
        return np.logspace(np.log10(minimum), np.log10(maximum), count)
    delays = np.asarray(explicit_delays_us, dtype=float).ravel()
    if delays.size < 4 or not np.all(np.isfinite(delays)) or np.any(delays <= 0):
        raise ValueError("explicit T1 delays need at least 4 finite positive values")
    if np.any(np.diff(delays) <= 0):
        raise ValueError("explicit T1 delays must be strictly increasing")
    return delays


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


def fit_t1_rounds(round_rows, *, methods):
    fits = {}
    errors = {}
    for round_index, rows in sorted(dict(round_rows).items()):
        key = str(round_index)
        fits[key] = {}
        errors[key] = {}
        for method in tuple(str(value) for value in methods):
            selected = [row for row in rows if str(row["method"]) == method]
            try:
                fits[key][method] = fit_t1_decay(
                    [row["delay_us"] for row in selected],
                    [row["excited_fraction"] for row in selected],
                    shots=[row["shots"] for row in selected],
                )
            except Exception as exc:
                errors[key][method] = f"{type(exc).__name__}: {exc}"
    return fits, errors


def evaluate_t1_equivalence(
    passive,
    active,
    *,
    max_relative_tau_difference,
    max_abs_p0_difference,
    max_abs_p1_difference,
):
    tolerances = np.asarray([
        max_relative_tau_difference,
        max_abs_p0_difference,
        max_abs_p1_difference,
    ], dtype=float)
    if not np.all(np.isfinite(tolerances)) or np.any(tolerances < 0):
        raise ValueError("T1 equivalence tolerances must be finite and nonnegative")
    passive_tau = float(passive["tau_us"])
    active_tau = float(active["tau_us"])
    values = np.asarray([
        passive_tau,
        active_tau,
        passive["P0"],
        active["P0"],
        passive["P1"],
        active["P1"],
    ], dtype=float)
    if not np.all(np.isfinite(values)) or passive_tau <= 0 or active_tau <= 0:
        raise ValueError("T1 equivalence fits must contain finite positive lifetimes")
    tau_difference = active_tau - passive_tau
    relative_tau_difference = tau_difference / passive_tau
    p0_difference = float(active["P0"] - passive["P0"])
    p1_difference = float(active["P1"] - passive["P1"])
    decaying_passed = bool(passive.get("decaying", False) and active.get("decaying", False))
    tau_passed = abs(relative_tau_difference) <= float(max_relative_tau_difference)
    p0_passed = abs(p0_difference) <= float(max_abs_p0_difference)
    p1_passed = abs(p1_difference) <= float(max_abs_p1_difference)
    checks = {
        "decaying": decaying_passed,
        "tau": bool(tau_passed),
        "P0": bool(p0_passed),
        "P1": bool(p1_passed),
    }
    return {
        "status": "pass" if all(checks.values()) else "fail",
        "passive_tau_us": passive_tau,
        "active_tau_us": active_tau,
        "difference_us": tau_difference,
        "relative_difference": relative_tau_difference,
        "relative_tolerance": float(max_relative_tau_difference),
        "passive_P0": float(passive["P0"]),
        "active_P0": float(active["P0"]),
        "P0_difference": p0_difference,
        "P0_tolerance": float(max_abs_p0_difference),
        "passive_P1": float(passive["P1"]),
        "active_P1": float(active["P1"]),
        "P1_difference": p1_difference,
        "P1_tolerance": float(max_abs_p1_difference),
        "decaying_passed": decaying_passed,
        "tau_passed": bool(tau_passed),
        "P0_passed": bool(p0_passed),
        "P1_passed": bool(p1_passed),
        "failed_checks": [name for name, passed in checks.items() if not passed],
    }


def evaluate_t1_flux_lifecycle(
    fits,
    *,
    max_relative_tau_difference,
    max_abs_p0_difference,
    max_abs_p1_difference,
):
    required = ("passive_1000", "passive_400", "active_1000", "active_400")
    missing = [name for name in required if name not in fits]
    if missing:
        return {
            "status": "fail",
            "diagnosis": "fit_failed",
            "missing_fits": missing,
            "comparisons": {},
        }
    baseline = fits["passive_1000"]
    options = {
        "short_interval": fits["passive_400"],
        "active_reset": fits["active_1000"],
        "combined": fits["active_400"],
    }
    comparisons = {
        name: evaluate_t1_equivalence(
            baseline,
            fit,
            max_relative_tau_difference=max_relative_tau_difference,
            max_abs_p0_difference=max_abs_p0_difference,
            max_abs_p1_difference=max_abs_p1_difference,
        )
        for name, fit in options.items()
    }
    passed = {
        name: result["status"] == "pass" for name, result in comparisons.items()
    }
    diagnosis = diagnose_t1_flux_lifecycle(
        short_passed=passed["short_interval"],
        reset_passed=passed["active_reset"],
        combined_passed=passed["combined"],
    )
    return {
        "status": "pass" if all(passed.values()) else "fail",
        "diagnosis": diagnosis,
        "missing_fits": [],
        "comparisons": comparisons,
    }


def evaluate_t1_recovery_sweep(
    fits,
    round_fits,
    *,
    candidate_delays_us,
    baseline_method,
    max_relative_tau_difference,
    max_abs_p0_difference,
    max_abs_p1_difference,
):
    fits = dict(fits)
    round_fits = {str(key): dict(value) for key, value in dict(round_fits).items()}
    candidate_delays = {
        str(method): float(delay)
        for method, delay in dict(candidate_delays_us).items()
    }
    baseline_method = str(baseline_method)
    if not candidate_delays:
        raise ValueError("at least one active recovery candidate is required")
    delays = np.asarray(list(candidate_delays.values()), dtype=float)
    if not np.all(np.isfinite(delays)) or np.any(delays < 0):
        raise ValueError("active recovery delays must be finite and nonnegative")
    if np.unique(delays).size != delays.size:
        raise ValueError("active recovery delays must be unique")
    rows = []
    for method, delay in sorted(candidate_delays.items(), key=lambda item: item[1]):
        aggregate_complete = baseline_method in fits and method in fits
        aggregate = (
            evaluate_t1_equivalence(
                fits[baseline_method],
                fits[method],
                max_relative_tau_difference=max_relative_tau_difference,
                max_abs_p0_difference=max_abs_p0_difference,
                max_abs_p1_difference=max_abs_p1_difference,
            )
            if aggregate_complete
            else {"status": "fail", "reason": "missing aggregate fit"}
        )
        comparisons = {}
        failed_rounds = []
        for round_index, values in sorted(round_fits.items()):
            if baseline_method not in values or method not in values:
                comparison = {"status": "fail", "reason": "missing round fit"}
            else:
                comparison = evaluate_t1_equivalence(
                    values[baseline_method],
                    values[method],
                    max_relative_tau_difference=max_relative_tau_difference,
                    max_abs_p0_difference=max_abs_p0_difference,
                    max_abs_p1_difference=max_abs_p1_difference,
                )
            comparisons[round_index] = comparison
            if comparison["status"] != "pass":
                failed_rounds.append(round_index)
        complete = bool(aggregate_complete and round_fits and not any(
            comparison.get("reason") == "missing round fit"
            for comparison in comparisons.values()
        ))
        passed = bool(
            complete
            and aggregate["status"] == "pass"
            and not failed_rounds
        )
        rows.append({
            "method": method,
            "active_relax_us": delay,
            "complete": complete,
            "passed": passed,
            "aggregate": aggregate,
            "rounds": comparisons,
            "failed_rounds": failed_rounds,
        })
    selected = next((row for row in rows if row["passed"]), None)
    return {
        "status": "pass" if selected is not None else "fail",
        "baseline_method": baseline_method,
        "selected_method": selected["method"] if selected is not None else None,
        "selected_active_relax_us": (
            selected["active_relax_us"] if selected is not None else None
        ),
        "rows": rows,
    }


def evaluate_paired_t1_recovery_sweep(
    fits,
    round_fits,
    *,
    candidate_delays_us,
    baseline_method,
    control_method,
    max_relative_tau_difference,
    max_abs_p0_difference,
    max_abs_p1_difference,
    max_heterogeneity_i2=0.5,
):
    candidate_delays = {
        str(method): float(delay)
        for method, delay in dict(candidate_delays_us).items()
    }
    if not candidate_delays:
        raise ValueError("at least one active recovery candidate is required")
    delays = np.asarray(list(candidate_delays.values()), dtype=float)
    if not np.all(np.isfinite(delays)) or np.any(delays < 0):
        raise ValueError("active recovery delays must be finite and nonnegative")
    if np.unique(delays).size != delays.size:
        raise ValueError("active recovery delays must be unique")
    control_method = str(control_method)
    if control_method not in candidate_delays:
        raise ValueError("control method must be an active recovery candidate")
    staged_methods = {
        method: f"active_recovery_{delay:g}us"
        for method, delay in candidate_delays.items()
        if method != control_method
    }
    attribution = evaluate_t1_load_attribution(
        fits,
        round_fits,
        baseline_method=baseline_method,
        active_method=control_method,
        staged_methods=staged_methods,
        max_relative_tau_difference=max_relative_tau_difference,
        max_abs_p0_difference=max_abs_p0_difference,
        max_abs_p1_difference=max_abs_p1_difference,
        max_heterogeneity_i2=max_heterogeneity_i2,
    )
    rows = []
    for method, delay in sorted(candidate_delays.items(), key=lambda item: item[1]):
        comparison = attribution["comparisons"][method]
        aggregate = comparison["aggregate"]
        meta = comparison["meta"]
        ratio = float(meta.get("ratio", float("nan")))
        i2 = float(meta.get("I2", float("nan")))
        ratio_passed = bool(
            np.isfinite(ratio)
            and 1.0 - float(max_relative_tau_difference)
            <= ratio
            <= 1.0 + float(max_relative_tau_difference)
        )
        heterogeneity_passed = bool(
            np.isfinite(i2) and i2 <= float(max_heterogeneity_i2)
        )
        complete = bool(
            aggregate.get("status") in {"pass", "fail"}
            and "reason" not in aggregate
            and meta.get("complete", False)
        )
        passed = bool(
            complete
            and aggregate["status"] == "pass"
            and ratio_passed
            and heterogeneity_passed
        )
        rows.append({
            "method": method,
            "active_relax_us": delay,
            "complete": complete,
            "passed": passed,
            "aggregate": aggregate,
            "meta": meta,
            "ratio_passed": ratio_passed,
            "heterogeneity_passed": heterogeneity_passed,
            "rounds": comparison["rounds"],
            "failed_rounds": [
                round_index
                for round_index, values in comparison["rounds"].items()
                if values.get("status") != "pass"
            ],
        })
    by_method = {row["method"]: row for row in rows}
    control_passed = bool(by_method[control_method]["passed"])
    selected = next((row for row in rows if row["passed"]), None)
    status = "pass" if control_passed and selected is not None else "fail"
    return {
        "status": status,
        "baseline_method": str(baseline_method),
        "control_method": control_method,
        "control_passed": control_passed,
        "selected_method": selected["method"] if selected is not None else None,
        "selected_active_relax_us": (
            selected["active_relax_us"] if selected is not None else None
        ),
        "max_heterogeneity_i2": float(max_heterogeneity_i2),
        "rows": rows,
    }


def evaluate_t1_load_attribution(
    fits,
    round_fits,
    *,
    baseline_method,
    active_method,
    staged_methods,
    max_relative_tau_difference,
    max_abs_p0_difference,
    max_abs_p1_difference,
    max_heterogeneity_i2=0.5,
):
    fits = dict(fits)
    round_fits = {str(key): dict(value) for key, value in dict(round_fits).items()}
    baseline_method = str(baseline_method)
    active_method = str(active_method)
    staged_methods = {
        str(method): str(diagnosis)
        for method, diagnosis in dict(staged_methods).items()
    }
    methods = tuple(staged_methods) + (active_method,)
    max_heterogeneity_i2 = float(max_heterogeneity_i2)
    if not np.isfinite(max_heterogeneity_i2) or not 0 <= max_heterogeneity_i2 <= 1:
        raise ValueError("max_heterogeneity_i2 must be finite and in [0, 1]")
    comparisons = {}
    for method in methods:
        if baseline_method in fits and method in fits:
            aggregate = evaluate_t1_equivalence(
                fits[baseline_method],
                fits[method],
                max_relative_tau_difference=max_relative_tau_difference,
                max_abs_p0_difference=max_abs_p0_difference,
                max_abs_p1_difference=max_abs_p1_difference,
            )
        else:
            aggregate = {"status": "fail", "reason": "missing aggregate fit"}
        rounds = {}
        for round_index, values in sorted(round_fits.items()):
            if baseline_method in values and method in values:
                rounds[round_index] = evaluate_t1_equivalence(
                    values[baseline_method],
                    values[method],
                    max_relative_tau_difference=max_relative_tau_difference,
                    max_abs_p0_difference=max_abs_p0_difference,
                    max_abs_p1_difference=max_abs_p1_difference,
                )
            else:
                rounds[round_index] = {
                    "status": "fail",
                    "reason": "missing round fit",
                }
        log_ratios = []
        variances = []
        for values in round_fits.values():
            if baseline_method not in values or method not in values:
                continue
            baseline = values[baseline_method]
            candidate = values[method]
            try:
                baseline_tau = float(baseline["tau_us"])
                candidate_tau = float(candidate["tau_us"])
                baseline_error = float(baseline["tau_err_us"])
                candidate_error = float(candidate["tau_err_us"])
            except (KeyError, TypeError, ValueError):
                continue
            raw = np.asarray(
                [baseline_tau, candidate_tau, baseline_error, candidate_error],
                dtype=float,
            )
            if not np.all(np.isfinite(raw)) or np.any(raw <= 0):
                continue
            log_ratios.append(math.log(candidate_tau / baseline_tau))
            variances.append(
                (candidate_error / candidate_tau) ** 2
                + (baseline_error / baseline_tau) ** 2
            )
        if len(log_ratios) >= 2:
            log_ratios = np.asarray(log_ratios, dtype=float)
            variances = np.asarray(variances, dtype=float)
            weights = 1.0 / variances
            mean = float(np.sum(weights * log_ratios) / np.sum(weights))
            error = float(np.sqrt(1.0 / np.sum(weights)))
            q_value = float(np.sum(weights * (log_ratios - mean) ** 2))
            degrees = len(log_ratios) - 1
            i2 = max(0.0, (q_value - degrees) / q_value) if q_value > 0 else 0.0
            meta = {
                "complete": True,
                "rounds": len(log_ratios),
                "ratio": math.exp(mean),
                "ratio_ci95_low": math.exp(mean - 1.96 * error),
                "ratio_ci95_high": math.exp(mean + 1.96 * error),
                "Q": q_value,
                "I2": i2,
            }
        else:
            meta = {"complete": False, "rounds": len(log_ratios)}
        comparisons[method] = {
            "aggregate": aggregate,
            "rounds": rounds,
            "meta": meta,
        }

    complete = baseline_method in fits and all(method in fits for method in methods)
    active_comparison = comparisons[active_method]["aggregate"]

    def shortened(comparison):
        return bool(
            "relative_difference" in comparison
            and comparison["relative_difference"]
            < -float(max_relative_tau_difference)
        )

    for method, values in comparisons.items():
        values["shortened"] = shortened(values["aggregate"])
        values["shortened_rounds"] = [
            round_index
            for round_index, comparison in values["rounds"].items()
            if shortened(comparison)
        ]
        meta = values["meta"]
        values["robust_shortened"] = bool(
            values["shortened"]
            and meta.get("complete", False)
            and meta["ratio_ci95_high"] < 1.0
            and meta["I2"] <= max_heterogeneity_i2
        )

    if not complete:
        diagnosis = "fit_failed"
    elif not shortened(active_comparison):
        diagnosis = "no_active_effect"
    elif not comparisons[active_method]["robust_shortened"]:
        diagnosis = "time_dependent_or_inconclusive"
    else:
        diagnosis = "feedback_dependent_reset"
        for method, candidate in staged_methods.items():
            if comparisons[method]["robust_shortened"]:
                diagnosis = candidate
                break
    return {
        "status": "complete" if complete else "fail",
        "diagnosis": diagnosis,
        "baseline_method": baseline_method,
        "active_method": active_method,
        "max_heterogeneity_i2": max_heterogeneity_i2,
        "comparisons": comparisons,
    }


def evaluate_inter_shot_recovery_sweep(
    passive_excited_fraction,
    rows,
    *,
    max_abs_population_difference,
    max_abs_shot_drift,
):
    passive = float(passive_excited_fraction)
    population_limit = float(max_abs_population_difference)
    drift_limit = float(max_abs_shot_drift)
    if not math.isfinite(passive) or not 0.0 <= passive <= 1.0:
        raise ValueError("passive_excited_fraction must be finite and in [0, 1]")
    limits = np.asarray([population_limit, drift_limit], dtype=float)
    if not np.all(np.isfinite(limits)) or np.any(limits < 0) or np.any(limits > 1):
        raise ValueError("recovery sweep tolerances must be finite and in [0, 1]")
    evaluated = []
    seen = set()
    for raw in rows:
        row = dict(raw)
        delay = float(row["active_relax_us"])
        population = float(row["excited_fraction"])
        drift = float(row["shot_drift"])
        values = np.asarray([delay, population, drift], dtype=float)
        if not np.all(np.isfinite(values)) or delay < 0:
            raise ValueError("recovery sweep rows must contain finite nonnegative delays")
        if not 0.0 <= population <= 1.0 or not -1.0 <= drift <= 1.0:
            raise ValueError("recovery sweep populations and drifts must be in range")
        if delay in seen:
            raise ValueError(f"duplicate active recovery delay: {delay}")
        seen.add(delay)
        population_difference = population - passive
        round_differences = np.asarray(
            row.get("round_population_differences", []), dtype=float
        ).ravel()
        if not np.all(np.isfinite(round_differences)) or np.any(
            np.abs(round_differences) > 1.0
        ):
            raise ValueError("round population differences must be finite and in range")
        worst_population_difference = max(
            [abs(population_difference)] + np.abs(round_differences).tolist()
        )
        row.update({
            "active_relax_us": delay,
            "excited_fraction": population,
            "shot_drift": drift,
            "population_difference": population_difference,
            "round_population_differences": round_differences.tolist(),
            "worst_abs_population_difference": worst_population_difference,
            "population_passed": worst_population_difference <= population_limit,
            "drift_passed": abs(drift) <= drift_limit,
        })
        row["passed"] = bool(row["population_passed"] and row["drift_passed"])
        evaluated.append(row)
    evaluated.sort(key=lambda row: row["active_relax_us"])
    selected = next((row for row in evaluated if row["passed"]), None)
    return {
        "status": "pass" if selected is not None else "fail",
        "passive_excited_fraction": passive,
        "selected_active_relax_us": (
            selected["active_relax_us"] if selected is not None else None
        ),
        "max_abs_population_difference": population_limit,
        "max_abs_shot_drift": drift_limit,
        "rows": evaluated,
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
