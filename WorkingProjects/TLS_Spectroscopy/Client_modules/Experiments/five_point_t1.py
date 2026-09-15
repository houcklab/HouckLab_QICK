"""Shared analysis primitives for matched-reference five-point T1 scans."""

import json

import numpy as np


def five_point_output_metadata(data, condition_names):
    """String-valued acquisition and correction provenance for CSV rows."""
    correction = data.get("flux_tail_compensation")
    return {
        "acquisition_order": data.get("acquisition_order", ""),
        "acquisition_loop_order": "shot,frequency,condition",
        "condition_order": ",".join(condition_names),
        "condition_order_json": json.dumps(list(condition_names)),
        "survival_order_alternates": bool(
            data.get("survival_order_alternates", False)
        ),
        "survival_order_forward_json": json.dumps(list(condition_names[2:])),
        "survival_order_reverse_json": json.dumps(
            list(reversed(condition_names[2:]))
            if data.get("survival_order_alternates", False)
            else list(condition_names[2:])
        ),
        "dc_scan_order": "alternating_bidirectional",
        "dc_scan_axis_convention": "up=forward input dc_vec; down=reverse input dc_vec",
        "dc_scan_first_direction": "forward",
        "dc_scan_up_shots": data.get("dc_scan_up_shots"),
        "dc_scan_down_shots": data.get("dc_scan_down_shots"),
        "p0_mode": "matched_frequency_resolved",
        "reference_mode": "matched_frequency_resolved",
        "correction_mode": data.get("correction_mode", "distortion-corrected" if correction else "uncorrected"),
        "correction_source": (correction or {}).get("source", ""),
        "correction_method": (correction or {}).get("method", ""),
        "correction_gain": (float(correction["correction_gain"] if correction.get("correction_gain") is not None else 1.0) if correction else 0.0),
        "correction_provenance_json": json.dumps(correction, sort_keys=True, default=lambda x: np.asarray(x).tolist()),
    }


def validate_five_point_delays(delays_us):
    return validate_matched_t1_delays(delays_us, expected_count=3)


def validate_matched_t1_delays(delays_us, expected_count=None):
    """Validate an ordered matched-reference survival-delay axis."""
    delays = np.asarray(delays_us, dtype=float).reshape(-1)
    if expected_count is not None and delays.size != int(expected_count):
        raise ValueError(
            f"matched-reference T1 requires exactly {int(expected_count)} "
            "decay delays"
        )
    if delays.size < 1:
        raise ValueError("matched-reference T1 requires at least one decay delay")
    if not np.all(np.isfinite(delays)) or np.any(delays <= 0.0):
        raise ValueError("matched-reference decay delays must be finite and positive")
    if np.any(np.diff(delays) <= 0.0):
        raise ValueError("matched-reference decay delays must be strictly increasing")
    return delays


def _logit(value):
    value = float(np.clip(value, 1e-9, 1.0 - 1e-9))
    return np.log(value / (1.0 - value))


def _prediction_and_jacobian(parameters, delays_us):
    """Return five probabilities and d(probability)/d(a, b, log(T1))."""

    a, b, log_t1 = np.asarray(parameters, dtype=float)
    p0 = 1.0 / (1.0 + np.exp(-a))
    excited_fraction = 1.0 / (1.0 + np.exp(-b))
    p1 = p0 + (1.0 - p0) * excited_fraction
    t1_us = float(np.exp(log_t1))
    decay = np.exp(-delays_us / t1_us)
    predicted = np.r_[p0, p1, p0 + (p1 - p0) * decay]

    dp0_da = p0 * (1.0 - p0)
    dp1_da = dp0_da * (1.0 - excited_fraction)
    dp1_db = (1.0 - p0) * excited_fraction * (1.0 - excited_fraction)
    jacobian = np.zeros((2 + delays_us.size, 3), dtype=float)
    jacobian[0] = (dp0_da, 0.0, 0.0)
    jacobian[1] = (dp1_da, dp1_db, 0.0)
    jacobian[2:, 0] = (1.0 - decay) * dp0_da + decay * dp1_da
    jacobian[2:, 1] = decay * dp1_db
    jacobian[2:, 2] = (
        (p1 - p0) * decay * delays_us / t1_us
    )
    return p0, p1, t1_us, predicted, jacobian


def _binomial_deviance(observed, predicted, shots):
    eps = 1e-12
    observed = np.clip(np.asarray(observed, dtype=float), 0.0, 1.0)
    predicted = np.clip(np.asarray(predicted, dtype=float), eps, 1.0 - eps)
    shots = np.asarray(shots, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        first = np.where(
            observed > 0.0,
            observed * np.log(observed / predicted),
            0.0,
        )
        second = np.where(
            observed < 1.0,
            (1.0 - observed) * np.log((1.0 - observed) / (1.0 - predicted)),
            0.0,
        )
    return max(0.0, float(2.0 * np.sum(shots * (first + second))))


def _fit_one_five_point(observed, delays_us, shots, *, min_t1_us, max_t1_us):
    from scipy.optimize import minimize

    observed = np.asarray(observed, dtype=float)
    contrast_seed = max(float(observed[1] - observed[0]), 1e-3)
    p0_seed = float(np.clip(observed[0], 1e-4, 1.0 - 1e-4))
    p1_seed = float(
        np.clip(max(observed[1], p0_seed + 1e-3), p0_seed + 1e-3, 1.0 - 1e-4)
    )
    fraction_seed = (p1_seed - p0_seed) / (1.0 - p0_seed)
    ratios = (observed[2:] - p0_seed) / contrast_seed
    informative = (ratios > 0.0) & (ratios < 1.0)
    candidate = -delays_us[informative] / np.log(ratios[informative])
    candidate = candidate[np.isfinite(candidate) & (candidate > 0.0)]
    t1_seed = (
        float(np.median(candidate))
        if candidate.size
        else float(np.median(delays_us))
    )
    t1_seed = float(np.clip(t1_seed, min_t1_us, max_t1_us))
    initial = np.array(
        [_logit(p0_seed), _logit(fraction_seed), np.log(t1_seed)]
    )

    def objective(parameters):
        _, _, _, predicted, jacobian = _prediction_and_jacobian(
            parameters, delays_us
        )
        predicted = np.clip(predicted, 1e-12, 1.0 - 1e-12)
        value = float(
            -np.sum(
                shots
                * (
                    observed * np.log(predicted)
                    + (1.0 - observed) * np.log1p(-predicted)
                )
            )
        )
        score = shots * (predicted - observed) / (
            predicted * (1.0 - predicted)
        )
        gradient = jacobian.T @ score
        return value, gradient

    fit = minimize(
        objective,
        initial,
        method="L-BFGS-B",
        jac=True,
        bounds=(
            (-12.0, 12.0),
            (-12.0, 12.0),
            (np.log(min_t1_us), np.log(max_t1_us)),
        ),
        options={"maxiter": 500, "ftol": 1e-12},
    )
    p0, p1, t1_us, predicted, _ = _prediction_and_jacobian(
        fit.x, delays_us
    )
    decay = np.exp(-delays_us / t1_us)

    fisher = np.zeros((3, 3), dtype=float)
    gradients = [
        np.array([1.0, 0.0, 0.0]),
        np.array([0.0, 1.0, 0.0]),
    ]
    gradients.extend(
        np.array([1.0 - q, q, (p1 - p0) * q * delay / t1_us])
        for delay, q in zip(delays_us, decay)
    )
    for n_shots, probability, gradient in zip(shots, predicted, gradients):
        variance = max(float(probability * (1.0 - probability)), 1e-12)
        fisher += float(n_shots) * np.outer(gradient, gradient) / variance
    try:
        covariance = np.linalg.inv(fisher)
        t1_error_us = float(t1_us * np.sqrt(max(covariance[2, 2], 0.0)))
    except np.linalg.LinAlgError:
        t1_error_us = float("nan")
    return {
        "success": bool(fit.success),
        "P0_fit": p0,
        "P1_fit": p1,
        "T1_us": t1_us,
        "T1_err_us": t1_error_us,
        "deviance": _binomial_deviance(observed, predicted, shots),
    }


def estimate_matched_t1(
    P0,
    P1,
    survival_probabilities,
    delays_us,
    *,
    shots_per_condition,
    min_ref_contrast=0.05,
    max_relative_error=1.0,
    min_t1_us=0.25,
    max_t1_us=3000.0,
):
    """Jointly fit P0, P1, and T1 with matched binomial populations."""

    delays = validate_matched_t1_delays(delays_us)
    p0 = np.asarray(P0, dtype=float).reshape(-1)
    p1 = np.asarray(P1, dtype=float).reshape(-1)
    survival = np.asarray(survival_probabilities, dtype=float)
    if survival.ndim == 1:
        survival = survival.reshape(1, -1)
    survival_count = int(delays.size)
    condition_count = 2 + survival_count
    if survival.shape != (p0.size, survival_count) or p1.shape != p0.shape:
        raise ValueError(
            "P0/P1 must be 1D and survival probabilities must have shape "
            f"(n, {survival_count})"
        )
    if np.isscalar(shots_per_condition):
        shots = np.full(condition_count, float(shots_per_condition), dtype=float)
    else:
        shots = np.asarray(shots_per_condition, dtype=float).reshape(-1)
    if (
        shots.size != condition_count
        or not np.all(np.isfinite(shots))
        or np.any(shots <= 0.0)
        or np.any(shots != np.floor(shots))
    ):
        raise ValueError(
            "shots_per_condition must be a positive integer or one positive "
            "integer per condition"
        )
    min_t1_us = float(min_t1_us)
    max_t1_us = float(max_t1_us)
    if not (0.0 < min_t1_us < max_t1_us):
        raise ValueError("T1 fit bounds must satisfy 0 < min_t1_us < max_t1_us")

    raw_t1 = np.full(p0.shape, np.nan)
    error = np.full(p0.shape, np.nan)
    p0_fit = np.full(p0.shape, np.nan)
    p1_fit = np.full(p0.shape, np.nan)
    deviance = np.full(p0.shape, np.nan)
    fit_success = np.zeros(p0.shape, dtype=np.int8)
    valid = np.zeros(p0.shape, dtype=np.int8)
    contrast = p1 - p0

    for index in range(p0.size):
        observed = np.r_[p0[index], p1[index], survival[index]]
        if not np.all(np.isfinite(observed)):
            continue
        if np.any(observed < 0.0) or np.any(observed > 1.0):
            continue
        if contrast[index] < float(min_ref_contrast):
            continue
        fitted = _fit_one_five_point(
            observed,
            delays,
            shots,
            min_t1_us=min_t1_us,
            max_t1_us=max_t1_us,
        )
        raw_t1[index] = fitted["T1_us"]
        error[index] = fitted["T1_err_us"]
        p0_fit[index] = fitted["P0_fit"]
        p1_fit[index] = fitted["P1_fit"]
        deviance[index] = fitted["deviance"]
        fit_success[index] = int(fitted["success"])
        relative_error = error[index] / raw_t1[index]
        valid[index] = int(
            fitted["success"]
            and np.isfinite(relative_error)
            and relative_error <= float(max_relative_error)
            and fitted["P1_fit"] - fitted["P0_fit"] >= float(min_ref_contrast)
            and raw_t1[index] > min_t1_us
            and raw_t1[index] < max_t1_us
        )

    return {
        "T1_us_raw": raw_t1,
        "T1_us": np.where(valid.astype(bool), raw_t1, np.nan),
        "T1_err_us": np.where(valid.astype(bool), error, np.nan),
        "valid_mask": valid,
        "fit_success": fit_success,
        "P0_fit": p0_fit,
        "P1_fit": p1_fit,
        "ref_contrast": contrast,
        "fit_deviance": deviance,
        "decay_delays_us": delays,
        "shots_per_condition": shots,
    }


def estimate_five_point_t1(*args, **kwargs):
    """Backward-compatible five-condition estimator."""
    delays = validate_five_point_delays(args[3] if len(args) > 3 else kwargs["delays_us"])
    if len(args) > 3:
        args = (*args[:3], delays, *args[4:])
    else:
        kwargs = {**kwargs, "delays_us": delays}
    result = estimate_matched_t1(*args, **kwargs)
    return {
        **result,
        "T1_5pt_us_raw": result["T1_us_raw"],
        "T1_5pt_us": result["T1_us"],
        "T1_5pt_err_us": result["T1_err_us"],
        "T1_5pt_valid_mask": result["valid_mask"],
        "ref_contrast_5pt": result["ref_contrast"],
    }


def reduce_bidirectional_condition_states(
    states, condition_names, *, canonical_dc_axis=False
):
    """Canonicalize alternating scan direction and average each condition."""

    values = np.asarray(states, dtype=float)
    names = tuple(str(name) for name in condition_names)
    if values.ndim != 3 or values.shape[0] != len(names):
        raise ValueError("states must have shape (condition, dc, shot)")
    shots = int(values.shape[2])
    if shots < 2:
        raise ValueError("bidirectional acquisition requires at least two shots")
    if len(set(names)) != len(names):
        raise ValueError("condition names must be unique")
    canonical = values.copy()
    if not canonical_dc_axis:
        canonical[:, :, 1::2] = values[:, ::-1, 1::2]
    up_mask = np.arange(shots) % 2 == 0
    down_mask = ~up_mask
    up_shots = int(np.count_nonzero(up_mask))
    down_shots = int(np.count_nonzero(down_mask))
    result = {
        "dc_scan_up_shots": up_shots,
        "dc_scan_down_shots": down_shots,
    }
    for index, name in enumerate(names):
        up = np.mean(canonical[index][:, up_mask], axis=1)
        down = np.mean(canonical[index][:, down_mask], axis=1)
        result[name] = (up_shots * up + down_shots * down) / shots
        result[f"{name}_scan_up"] = up
        result[f"{name}_scan_down"] = down
    return result
