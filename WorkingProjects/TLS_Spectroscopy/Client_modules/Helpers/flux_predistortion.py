"""
Flux-line predistortion library for the TLS_Spectroscopy port.

The first section of this file is the VERBATIM QUA LabCode/Helpers/flux_predistortion.py
(exponential/FIR/IIR machinery, default_dc_tail_segment_edges,
calculate_piecewise_dc_correction, save/load_predistortion_json), followed by the
rise_decay_bump model + its 600-seed BIC-selected fit lifted verbatim from
m_qubit_step_response.py, and finally the QICK-specific extensions (JSON
discovery/validation wrappers, gain rescale, fast-flux staircase baker).
"""

import json
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy import optimize, signal


def expdecay(time_ns, amplitude, tau_ns):
    """Normalized single-exponential step response: 1 + A exp(-t / tau)."""
    time_ns = np.asarray(time_ns, dtype=float)
    return 1.0 + amplitude * np.exp(-time_ns / tau_ns)


def multi_expdecay(time_ns, *params):
    """
    Normalized multi-exponential step response.

    Parameters are interleaved as ``A1, tau1, A2, tau2, ...`` with time in ns.
    """
    if len(params) % 2:
        raise ValueError("multi_expdecay expects interleaved (amplitude, tau_ns) pairs.")
    time_ns = np.asarray(time_ns, dtype=float)
    response = np.ones_like(time_ns, dtype=float)
    for amp, tau_ns in zip(params[0::2], params[1::2]):
        response += float(amp) * np.exp(-time_ns / float(tau_ns))
    return response


def multi_expdecay_with_asymptote(time_ns, *params):
    """
    Multi-exponential step response with a fitted flat level.

    Parameters are ``y_inf, A1, tau1, A2, tau2, ...`` with time in ns.
    """
    if len(params) < 3 or (len(params) - 1) % 2:
        raise ValueError("multi_expdecay_with_asymptote expects y_inf plus interleaved (amplitude, tau_ns) pairs.")
    time_ns = np.asarray(time_ns, dtype=float)
    response = np.full_like(time_ns, float(params[0]), dtype=float)
    for amp, tau_ns in zip(params[1::2], params[2::2]):
        response += float(amp) * np.exp(-time_ns / float(tau_ns))
    return response


def normalize_step_response(step_response, tail_fraction=0.25):
    """Normalize a measured step response by the mean of its final tail."""
    response = np.asarray(step_response, dtype=float)
    finite = response[np.isfinite(response)]
    if finite.size == 0:
        raise ValueError("Cannot normalize an empty/non-finite step response.")
    tail_count = max(3, int(np.ceil(finite.size * float(tail_fraction))))
    tail_count = min(tail_count, finite.size)
    tail = finite[-tail_count:]
    tail_mean = float(np.nanmean(tail))
    if not np.isfinite(tail_mean) or abs(tail_mean) < 1e-15:
        raise ValueError("Cannot normalize step response: final tail is zero or non-finite.")
    return response / tail_mean, tail_mean


def fit_exponential_step_response(
    time_ns,
    step_response,
    n_exp=1,
    normalize=True,
    tail_fraction=0.25,
    initial_taus_ns=None,
    max_abs_amplitude=10.0,
    fit_asymptote=False,
):
    """
    Fit a normalized step response to one or more exponential components.

    Returns a dictionary with component tuples ``[(A1, tau1_ns), ...]``. These
    component amplitudes are in the same convention used by the QUA examples:
    ``step(t) = 1 + sum(A_i exp(-t / tau_i))``.
    """
    time_ns = np.asarray(time_ns, dtype=float)
    response = np.asarray(step_response, dtype=float)
    if time_ns.shape != response.shape:
        raise ValueError("time_ns and step_response must have the same shape.")
    if n_exp < 1:
        raise ValueError("n_exp must be >= 1.")

    valid = np.isfinite(time_ns) & np.isfinite(response)
    time_ns = time_ns[valid]
    response = response[valid]
    if time_ns.size < max(5, 2 * n_exp + 2):
        raise ValueError("Not enough finite points to fit exponential step response.")

    order = np.argsort(time_ns)
    time_ns = time_ns[order]
    response = response[order]
    time_zeroed = time_ns - time_ns[0]

    if normalize:
        fit_response, input_normalization = normalize_step_response(response, tail_fraction=tail_fraction)
    else:
        fit_response = response
        input_normalization = 1.0

    using_default_taus = initial_taus_ns is None
    if initial_taus_ns is None:
        span_ns = max(float(time_zeroed[-1] - time_zeroed[0]), 1.0)
        if n_exp == 1:
            initial_taus_ns = [max(span_ns / 5.0, 1.0)]
        else:
            initial_taus_ns = np.geomspace(max(span_ns / 20.0, 1.0), max(span_ns, 2.0), n_exp)
    if len(initial_taus_ns) != n_exp:
        raise ValueError("initial_taus_ns must have one value per exponential component.")

    fit_asymptote = bool(fit_asymptote)
    tail_count = max(3, int(np.ceil(fit_response.size * float(tail_fraction))))
    tail_count = min(tail_count, fit_response.size)
    asymptote_guess = float(np.nanmean(fit_response[-tail_count:]))
    response_min = float(np.nanmin(fit_response))
    response_max = float(np.nanmax(fit_response))
    response_span = max(response_max - response_min, 1e-9)
    asymptote_lower = response_min - 2.0 * response_span
    asymptote_upper = response_max + 2.0 * response_span

    reference_flat_level = asymptote_guess if fit_asymptote else 1.0
    first_error = float(fit_response[0] - reference_flat_level)
    amp_guess = first_error / n_exp
    lower = []
    upper = []
    if fit_asymptote:
        lower.append(asymptote_lower)
        upper.append(asymptote_upper)
    for _ in initial_taus_ns:
        lower.extend([-max_abs_amplitude, 0.1])
        upper.extend([max_abs_amplitude, np.inf])

    model_func = multi_expdecay_with_asymptote if fit_asymptote else multi_expdecay
    tau_guesses = [np.asarray(initial_taus_ns, dtype=float)]
    if using_default_taus:
        span_ns = max(float(time_zeroed[-1] - time_zeroed[0]), 1.0)
        if n_exp == 1:
            for scale in (1 / 50, 1 / 20, 1 / 10, 1 / 5, 1 / 2, 1, 2, 5, 10):
                tau_guesses.append(np.asarray([max(span_ns * scale, 0.1)], dtype=float))
        else:
            for low_scale, high_scale in (
                (1 / 100, 1 / 2),
                (1 / 50, 1),
                (1 / 20, 2),
                (1 / 10, 5),
                (1 / 5, 10),
            ):
                tau_guesses.append(
                    np.geomspace(
                        max(span_ns * low_scale, 0.1),
                        max(span_ns * high_scale, 0.2),
                        n_exp,
                    )
                )

    best = None
    errors = []
    for tau_guess in tau_guesses:
        p0 = []
        if fit_asymptote:
            p0.append(asymptote_guess)
        for tau_ns in tau_guess:
            p0.extend([amp_guess, max(float(tau_ns), 0.1)])
        try:
            popt_candidate, pcov_candidate = optimize.curve_fit(
                model_func,
                time_zeroed,
                fit_response,
                p0=p0,
                bounds=(lower, upper),
                maxfev=100_000,
            )
            fitted_candidate = model_func(time_zeroed, *popt_candidate)
            residual_candidate = fit_response - fitted_candidate
            rms_candidate = float(np.sqrt(np.nanmean(residual_candidate**2)))
            if best is None or rms_candidate < best["rms"]:
                best = {
                    "popt": popt_candidate,
                    "pcov": pcov_candidate,
                    "fitted": fitted_candidate,
                    "residual": residual_candidate,
                    "rms": rms_candidate,
                }
        except Exception as exc:
            errors.append(str(exc))

    if best is not None:
        popt = best["popt"]
        pcov = best["pcov"]
        fitted = best["fitted"]
        residual = best["residual"]
        rms = best["rms"]
        components = [(float(amp), float(tau_ns)) for amp, tau_ns in zip(popt[0::2], popt[1::2])]
        success = True
        error = None
    else:
        p0 = []
        if fit_asymptote:
            p0.append(asymptote_guess)
        for tau_ns in initial_taus_ns:
            p0.extend([amp_guess, max(float(tau_ns), 0.1)])
        popt = np.asarray(p0, dtype=float)
        pcov = np.full((len(p0), len(p0)), np.nan)
        fitted = model_func(time_zeroed, *popt)
        residual = fit_response - fitted
        rms = float(np.sqrt(np.nanmean(residual**2)))
        success = False
        error = "; ".join(errors) if errors else "Exponential fit failed."

    if fit_asymptote:
        fitted_asymptote = float(popt[0])
        if not np.isfinite(fitted_asymptote) or abs(fitted_asymptote) < 1e-15:
            raise ValueError("Fitted exponential asymptote is zero or non-finite.")
        raw_components = [(float(amp), float(tau_ns)) for amp, tau_ns in zip(popt[1::2], popt[2::2])]
        components = [(float(amp / fitted_asymptote), float(tau_ns)) for amp, tau_ns in raw_components]
        total_normalization = float(input_normalization * fitted_asymptote)
        return_fit_response = fitted * input_normalization
        return_residual = response - return_fit_response
        return_rms = float(np.sqrt(np.nanmean(return_residual**2)))
        normalized_response = response / total_normalization
        normalized_fit_response = return_fit_response / total_normalization
    else:
        fitted_asymptote = 1.0
        raw_components = [(float(amp), float(tau_ns)) for amp, tau_ns in zip(popt[0::2], popt[1::2])]
        components = raw_components
        total_normalization = float(input_normalization)
        return_fit_response = fitted
        return_residual = residual
        return_rms = rms
        normalized_response = fit_response
        normalized_fit_response = fitted

    return {
        "success": success,
        "error": error,
        "time_ns": time_ns,
        "time_zeroed_ns": time_zeroed,
        "response": response,
        "normalized_response": normalized_response,
        "normalization": total_normalization,
        "fit_asymptote": fit_asymptote,
        "asymptote": float(fitted_asymptote * input_normalization),
        "components": components,
        "raw_components": raw_components,
        "fit_response": return_fit_response,
        "normalized_fit_response": normalized_fit_response,
        "residual": return_residual,
        "rms": return_rms,
        "covariance": pcov,
    }


def exponential_correction(amplitude, tau_ns, sample_period_s=1e-9):
    """
    Calculate the OPX feedforward/feedback taps for one exponential component.

    This follows the formula used in the QUA cryoscope examples.
    """
    tau_s = float(tau_ns) * 1e-9
    ts = float(sample_period_s)
    k1 = ts + 2.0 * tau_s * (float(amplitude) + 1.0)
    k2 = ts - 2.0 * tau_s * (float(amplitude) + 1.0)
    c1 = ts + 2.0 * tau_s
    c2 = ts - 2.0 * tau_s
    feedback_tap = -k2 / k1
    feedforward_taps = np.array([c1, c2], dtype=float) / k1
    return feedforward_taps, float(feedback_tap)


def filter_calc(exponential_components, sample_period_s=1e-9, max_feedforward_tap=2.0 - 2.0**-16):
    """
    Derive OPX FIR/IIR taps from exponential response components.

    ``exponential_components`` should be ``[(A1, tau1_ns), (A2, tau2_ns), ...]``.
    """
    components = [(float(a), float(t)) for a, t in exponential_components]
    if not components:
        return [], [], False

    feedforward_taps = np.asarray([1.0], dtype=float)
    feedback_taps = []
    for amplitude, tau_ns in components:
        if tau_ns <= 0:
            raise ValueError("All exponential tau values must be positive.")
        ff, fb = exponential_correction(amplitude, tau_ns, sample_period_s=sample_period_s)
        feedforward_taps = np.convolve(feedforward_taps, ff)
        feedback_taps.append(float(fb))
    feedback_taps = np.asarray(feedback_taps, dtype=float)

    max_abs = float(np.nanmax(np.abs(feedforward_taps)))
    clipped = False
    if max_abs >= max_feedforward_tap:
        feedforward_taps = feedforward_taps * (max_feedforward_tap / max_abs)
        clipped = True

    max_feedback_tap = 1.0 - 2.0**-20
    if feedback_taps.size and float(np.nanmax(np.abs(feedback_taps))) >= max_feedback_tap:
        feedback_taps = np.clip(feedback_taps, -max_feedback_tap, max_feedback_tap)
        clipped = True

    max_feedforward_len = 44 - 7 * len(feedback_taps)
    if len(feedforward_taps) > max_feedforward_len:
        removed = feedforward_taps[max_feedforward_len:]
        feedforward_taps = feedforward_taps[:max_feedforward_len]
        if np.nanmax(np.abs(removed)) > 1e-9:
            clipped = True

    return [float(x) for x in feedforward_taps], [float(x) for x in feedback_taps], clipped


def calculate_predistortion_filter(
    time_ns,
    step_response,
    n_exp=1,
    sample_period_s=1e-9,
    max_feedforward_tap=1.999,
    **fit_kwargs,
):
    """Fit a step response and calculate OPX filter taps in one call."""
    fit = fit_exponential_step_response(time_ns, step_response, n_exp=n_exp, **fit_kwargs)
    feedforward, feedback, clipped = filter_calc(
        fit["components"],
        sample_period_s=sample_period_s,
        max_feedforward_tap=max_feedforward_tap,
    )
    fit.update(
        {
            "feedforward": feedforward,
            "feedback": feedback,
            "feedforward_clipped": bool(clipped),
        }
    )
    return fit


def _delayed_step_matrix(step_response, n_taps):
    step_response = np.asarray(step_response, dtype=float)
    matrix = np.zeros((len(step_response), int(n_taps)), dtype=float)
    for tap_index in range(int(n_taps)):
        matrix[tap_index:, tap_index] = step_response[: len(step_response) - tap_index]
    return matrix


def calculate_fir_predistortion_filter(
    time_ns,
    step_response,
    n_taps=24,
    regularization=0.05,
    dc_weight=100.0,
    normalize=True,
    tail_fraction=0.25,
    max_feedforward_tap=1.999,
):
    """
    Calculate a regularized feedforward-only inverse from a measured step response.

    This is a non-parametric alternative to fitting exponentials. It solves for FIR
    taps ``f`` such that a linear combination of delayed measured step responses
    approximates an ideal unit step:

        sum_k f[k] * measured_step[n-k] ~= 1

    The regularizer keeps the solution close to ``[1, 0, 0, ...]`` and a separate
    DC-gain constraint keeps ``sum(f)`` close to one.
    """
    time_ns = np.asarray(time_ns, dtype=float)
    response = np.asarray(step_response, dtype=float)
    if time_ns.shape != response.shape:
        raise ValueError("time_ns and step_response must have the same shape.")

    valid = np.isfinite(time_ns) & np.isfinite(response)
    time_ns = time_ns[valid]
    response = response[valid]
    if response.size < max(8, int(n_taps) + 2):
        raise ValueError("Not enough finite points to calculate FIR predistortion.")

    order = np.argsort(time_ns)
    time_ns = time_ns[order]
    response = response[order]
    time_zeroed = time_ns - time_ns[0]

    if normalize:
        normalized_response, normalization = normalize_step_response(response, tail_fraction=tail_fraction)
    else:
        normalized_response = response
        normalization = 1.0

    n_taps = int(n_taps)
    step_matrix = _delayed_step_matrix(normalized_response, n_taps)
    desired = np.ones(len(normalized_response), dtype=float)

    reference_taps = np.zeros(n_taps, dtype=float)
    reference_taps[0] = 1.0
    sqrt_reg = np.sqrt(float(regularization))
    sqrt_dc = np.sqrt(float(dc_weight))
    augmented_matrix = np.vstack(
        [
            step_matrix,
            sqrt_reg * np.eye(n_taps),
            sqrt_dc * np.ones((1, n_taps)),
        ]
    )
    augmented_target = np.concatenate(
        [
            desired,
            sqrt_reg * reference_taps,
            np.asarray([sqrt_dc], dtype=float),
        ]
    )

    taps, *_ = np.linalg.lstsq(augmented_matrix, augmented_target, rcond=None)
    corrected_response = step_matrix @ taps
    residual = desired - corrected_response
    rms = float(np.sqrt(np.nanmean(residual**2)))
    max_abs = float(np.nanmax(np.abs(taps)))
    clipped = False
    if max_abs >= float(max_feedforward_tap):
        clipped = True

    return {
        "success": True,
        "error": None,
        "method": "regularized_fir_deconvolution",
        "time_ns": time_ns,
        "time_zeroed_ns": time_zeroed,
        "response": response,
        "normalized_response": normalized_response,
        "normalization": float(normalization),
        "feedforward": [float(x) for x in taps],
        "feedback": [],
        "components": [],
        "fit_response": corrected_response,
        "corrected_response": corrected_response,
        "residual": residual,
        "rms": rms,
        "feedforward_clipped": bool(clipped),
        "regularization": float(regularization),
        "dc_weight": float(dc_weight),
        "n_taps": n_taps,
        "tap_sum": float(np.sum(taps)),
        "max_abs_tap": max_abs,
    }


def calculate_iir_predistortion_filter(
    time_ns,
    step_response,
    n_feedforward=40,
    n_feedback=1,
    regularization=0.05,
    dc_weight=100.0,
    normalize=True,
    tail_fraction=0.25,
    max_feedforward_tap=1.999,
    max_feedback_tap=0.98,
):
    """
    Calculate a regularized FIR+IIR inverse directly from a measured step response.

    This does not fit exponentials. It finds OPX output-filter taps ``b`` and
    ``a`` such that ``lfilter(b, [1] + a, measured_step)`` is close to a unit
    step. Use one feedback tap unless you have a very good reason to allow more;
    one bounded pole is much easier to keep stable.
    """
    time_ns = np.asarray(time_ns, dtype=float)
    response = np.asarray(step_response, dtype=float)
    if time_ns.shape != response.shape:
        raise ValueError("time_ns and step_response must have the same shape.")

    valid = np.isfinite(time_ns) & np.isfinite(response)
    time_ns = time_ns[valid]
    response = response[valid]
    n_feedforward = int(n_feedforward)
    n_feedback = int(n_feedback)
    if n_feedforward < 1:
        raise ValueError("n_feedforward must be >= 1.")
    if n_feedback < 0:
        raise ValueError("n_feedback must be >= 0.")
    if response.size < max(8, n_feedforward + n_feedback + 2):
        raise ValueError("Not enough finite points to calculate IIR predistortion.")

    order = np.argsort(time_ns)
    time_ns = time_ns[order]
    response = response[order]
    time_zeroed = time_ns - time_ns[0]

    if normalize:
        normalized_response, normalization = normalize_step_response(response, tail_fraction=tail_fraction)
    else:
        normalized_response = response
        normalization = 1.0

    desired = np.ones(len(normalized_response), dtype=float)
    reference = np.zeros(n_feedforward + n_feedback, dtype=float)
    reference[0] = 1.0
    sqrt_reg = np.sqrt(float(regularization))
    sqrt_dc = np.sqrt(float(dc_weight))

    def residual(params):
        feedforward = params[:n_feedforward]
        feedback = params[n_feedforward:]
        corrected = signal.lfilter(feedforward, [1.0] + list(feedback), normalized_response)
        denom_dc = 1.0 + float(np.sum(feedback))
        if abs(denom_dc) < 1e-9:
            dc_residual = 1e3
        else:
            dc_residual = float(np.sum(feedforward) / denom_dc - 1.0)
        return np.concatenate(
            [
                corrected - desired,
                sqrt_reg * (params - reference),
                np.asarray([sqrt_dc * dc_residual], dtype=float),
            ]
        )

    initial = reference.copy()
    lower = np.concatenate(
        [
            -float(max_feedforward_tap) * np.ones(n_feedforward, dtype=float),
            -float(max_feedback_tap) * np.ones(n_feedback, dtype=float),
        ]
    )
    upper = np.concatenate(
        [
            float(max_feedforward_tap) * np.ones(n_feedforward, dtype=float),
            float(max_feedback_tap) * np.ones(n_feedback, dtype=float),
        ]
    )
    result = optimize.least_squares(
        residual,
        initial,
        bounds=(lower, upper),
        max_nfev=100_000,
        xtol=1e-12,
        ftol=1e-12,
        gtol=1e-12,
    )

    taps = result.x
    feedforward = taps[:n_feedforward]
    feedback = taps[n_feedforward:]
    corrected_response = signal.lfilter(feedforward, [1.0] + list(feedback), normalized_response)
    model_residual = desired - corrected_response
    rms = float(np.sqrt(np.nanmean(model_residual**2)))
    max_abs_ff = float(np.nanmax(np.abs(feedforward)))
    max_abs_fb = float(np.nanmax(np.abs(feedback))) if n_feedback else 0.0
    feedforward_clipped = bool(max_abs_ff >= float(max_feedforward_tap) * 0.999)
    feedback_clipped = bool(n_feedback and max_abs_fb >= float(max_feedback_tap) * 0.999)

    stable = True
    max_pole_radius = 0.0
    if n_feedback:
        poles = np.roots([1.0] + [float(x) for x in feedback])
        max_pole_radius = float(np.max(np.abs(poles))) if poles.size else 0.0
        stable = bool(max_pole_radius < 1.0)

    return {
        "success": bool(result.success and stable),
        "error": None if result.success and stable else result.message,
        "method": "regularized_iir_deconvolution",
        "time_ns": time_ns,
        "time_zeroed_ns": time_zeroed,
        "response": response,
        "normalized_response": normalized_response,
        "normalization": float(normalization),
        "feedforward": [float(x) for x in feedforward],
        "feedback": [float(x) for x in feedback],
        "components": [],
        "fit_response": corrected_response,
        "corrected_response": corrected_response,
        "residual": model_residual,
        "rms": rms,
        "feedforward_clipped": feedforward_clipped,
        "feedback_clipped": feedback_clipped,
        "regularization": float(regularization),
        "dc_weight": float(dc_weight),
        "n_feedforward": n_feedforward,
        "n_feedback": n_feedback,
        "tap_sum": float(np.sum(feedforward)),
        "feedback_sum": float(np.sum(feedback)),
        "dc_gain": float(np.sum(feedforward) / (1.0 + np.sum(feedback))),
        "max_abs_tap": max_abs_ff,
        "max_abs_feedback_tap": max_abs_fb,
        "max_pole_radius": max_pole_radius,
    }


def default_dc_tail_segment_edges(max_time_ns):
    max_time_ns = float(max_time_ns)
    if not np.isfinite(max_time_ns):
        raise ValueError("max_time_ns must be finite.")
    max_time_ns = max(max_time_ns, 0.0)

    edges = [0.0]
    edge_ns = 0.0
    while edge_ns < max_time_ns:
        if edge_ns < 1_000.0:
            step_ns = 500.0
        elif edge_ns < 4_000.0:
            step_ns = 1_000.0
        elif edge_ns < 8_000.0:
            step_ns = 2_000.0
        elif edge_ns < 16_000.0:
            step_ns = 4_000.0
        elif edge_ns < 32_000.0:
            step_ns = 8_000.0
        else:
            step_ns = 10_000.0

        next_edge_ns = edge_ns + step_ns
        if next_edge_ns <= max_time_ns + 1e-9:
            edges.append(next_edge_ns)
            edge_ns = next_edge_ns
            continue

        remaining_ns = max_time_ns - edge_ns
        if remaining_ns >= max(500.0, 0.25 * step_ns):
            edges.append(max_time_ns)
        break

    return np.asarray(edges, dtype=float)


def calculate_piecewise_dc_correction(
    time_ns,
    step_response,
    segment_edges_ns=None,
    regularization=0.02,
    final_weight=0.0,
    normalize=False,
    tail_fraction=0.25,
    min_multiplier=-1.5,
    max_multiplier=3.0,
    desired_response="unity",
    correction_gain=1.0,
):
    """
    Calculate a slow, piecewise-constant DC precompensation waveform.

    This is meant for experiments that use ``set_dc_offset`` for us-scale flux
    holds, where the OPX output filter may not be in the path. The measured
    ``step_response`` is the normalized plant response to a unit command step,
    in the same absolute convention as the target experiment. For TLS/T1 maps
    the most important target is often flatness: a constant frequency offset can
    be retuned, while a drifting offset cannot. ``desired_response`` can be:
    ``"unity"`` for exactly 1.0, ``"initial"`` for the mean of the first few
    points, ``"median"``/``"mean"``, or a numeric target level.
    The returned ``multipliers`` are applied to the requested step amplitude:

        commanded_dc(t) = park + multiplier[k] * (target - park)

    for the time segment starting at ``segment_edges_ns[k]``.
    """
    time_ns = np.asarray(time_ns, dtype=float)
    response = np.asarray(step_response, dtype=float)
    if time_ns.shape != response.shape:
        raise ValueError("time_ns and step_response must have the same shape.")

    valid = np.isfinite(time_ns) & np.isfinite(response)
    time_ns = time_ns[valid]
    response = response[valid]
    if response.size < 8:
        raise ValueError("Not enough finite points to calculate piecewise DC correction.")

    order = np.argsort(time_ns)
    time_ns = time_ns[order]
    response = response[order]
    time_zeroed = time_ns - time_ns[0]

    if normalize:
        normalized_response, normalization = normalize_step_response(response, tail_fraction=tail_fraction)
    else:
        normalized_response = response
        normalization = 1.0

    if segment_edges_ns is None:
        max_time_ns = max(float(time_zeroed[-1]), 4.0)
        segment_edges_ns = list(default_dc_tail_segment_edges(max_time_ns))
        if not segment_edges_ns or segment_edges_ns[0] != 0.0:
            segment_edges_ns.insert(0, 0.0)
    segment_edges_ns = np.asarray(segment_edges_ns, dtype=float)
    segment_edges_ns = np.unique(segment_edges_ns[np.isfinite(segment_edges_ns)])
    if segment_edges_ns.size == 0 or segment_edges_ns[0] > 0:
        segment_edges_ns = np.concatenate([[0.0], segment_edges_ns])
    if np.any(segment_edges_ns < 0):
        raise ValueError("segment_edges_ns must be non-negative.")
    if segment_edges_ns.size < 1:
        raise ValueError("At least one segment edge is required.")

    def plant_response(delay_ns):
        delay_ns = np.asarray(delay_ns, dtype=float)
        return np.interp(
            delay_ns,
            time_zeroed,
            normalized_response,
            left=float(normalized_response[0]),
            right=float(normalized_response[-1]),
        )

    step_matrix = np.zeros((len(time_zeroed), len(segment_edges_ns)), dtype=float)
    for edge_index, edge_ns in enumerate(segment_edges_ns):
        delay_ns = time_zeroed - float(edge_ns)
        active = delay_ns >= 0
        step_matrix[active, edge_index] = plant_response(delay_ns[active])

    if isinstance(desired_response, str):
        desired_mode = desired_response.strip().lower()
        if desired_mode in {"unity", "one", "target"}:
            desired_level = 1.0
        elif desired_mode in {"initial", "first"}:
            head_count = max(3, min(len(normalized_response), int(np.ceil(0.10 * len(normalized_response)))))
            desired_level = float(np.nanmean(normalized_response[:head_count]))
        elif desired_mode == "median":
            desired_level = float(np.nanmedian(normalized_response))
        elif desired_mode == "mean":
            desired_level = float(np.nanmean(normalized_response))
        else:
            desired_level = float(desired_response)
            desired_mode = "numeric"
    else:
        desired_level = float(desired_response)
        desired_mode = "numeric"
    if not np.isfinite(desired_level):
        raise ValueError("desired_response produced a non-finite target level.")

    desired = desired_level * np.ones(len(time_zeroed), dtype=float)
    lower = float(min_multiplier) * np.ones(len(segment_edges_ns), dtype=float)
    upper = float(max_multiplier) * np.ones(len(segment_edges_ns), dtype=float)
    if np.any(lower >= upper):
        raise ValueError("min_multiplier must be smaller than max_multiplier.")
    initial = np.ones(len(segment_edges_ns), dtype=float)
    initial = np.clip(initial, lower + 1e-9, upper - 1e-9)
    sqrt_reg = np.sqrt(float(regularization))
    sqrt_final = np.sqrt(max(float(final_weight), 0.0))

    def levels_to_response(levels):
        previous = np.concatenate([[0.0], levels[:-1]])
        jumps = levels - previous
        return step_matrix @ jumps

    def residual(levels):
        predicted = levels_to_response(levels)
        return np.concatenate(
            [
                predicted - desired,
                sqrt_reg * (levels - 1.0),
                np.asarray([sqrt_final * (levels[-1] - 1.0)], dtype=float),
            ]
        )

    correction_gain = float(correction_gain)
    if not np.isfinite(correction_gain) or correction_gain < 0.0:
        raise ValueError("correction_gain must be finite and non-negative.")

    result = optimize.least_squares(
        residual,
        initial,
        bounds=(lower, upper),
        max_nfev=100_000,
        xtol=1e-12,
        ftol=1e-12,
        gtol=1e-12,
    )
    undamped_multipliers = np.asarray(result.x, dtype=float)
    multipliers = 1.0 + correction_gain * (undamped_multipliers - 1.0)
    multipliers = np.clip(multipliers, lower, upper)
    undamped_corrected_response = levels_to_response(undamped_multipliers)
    corrected_response = levels_to_response(multipliers)
    model_residual = desired - corrected_response
    undamped_model_residual = desired - undamped_corrected_response
    rms = float(np.sqrt(np.nanmean(model_residual**2)))
    undamped_rms = float(np.sqrt(np.nanmean(undamped_model_residual**2)))
    clipped = bool(
        np.any(np.isclose(multipliers, lower, rtol=0.0, atol=1e-6))
        or np.any(np.isclose(multipliers, upper, rtol=0.0, atol=1e-6))
    )
    undamped_clipped = bool(
        np.any(np.isclose(undamped_multipliers, lower, rtol=0.0, atol=1e-6))
        or np.any(np.isclose(undamped_multipliers, upper, rtol=0.0, atol=1e-6))
    )

    return {
        "success": bool(result.success and not clipped),
        "error": None if result.success and not clipped else result.message,
        "method": "piecewise_set_dc_offset_deconvolution",
        "time_ns": time_ns,
        "time_zeroed_ns": time_zeroed,
        "response": response,
        "normalized_response": normalized_response,
        "normalization": float(normalization),
        "desired_response": desired_mode,
        "desired_level": float(desired_level),
        "desired_response_level": float(desired_level),
        "segment_edges_ns": [float(x) for x in segment_edges_ns],
        "multipliers": [float(x) for x in multipliers],
        "undamped_multipliers": [float(x) for x in undamped_multipliers],
        "corrected_response": corrected_response,
        "undamped_corrected_response": undamped_corrected_response,
        "fit_response": corrected_response,
        "residual": model_residual,
        "rms": rms,
        "undamped_rms": undamped_rms,
        "regularization": float(regularization),
        "final_weight": float(final_weight),
        "min_multiplier": float(min_multiplier),
        "max_multiplier": float(max_multiplier),
        "correction_gain": correction_gain,
        "multiplier_clipped": clipped,
        "undamped_multiplier_clipped": undamped_clipped,
        "max_abs_multiplier": float(np.nanmax(np.abs(multipliers))),
        "max_abs_undamped_multiplier": float(np.nanmax(np.abs(undamped_multipliers))),
    }


def apply_output_filter_to_config(config, flux_channel, feedforward, feedback):
    """Insert OPX+ style output filters into a config dictionary in-place."""
    channel = int(flux_channel)
    analog_outputs = config["controllers"]["con1"]["analog_outputs"]
    if channel not in analog_outputs:
        analog_outputs[channel] = {"offset": 0.0}
    analog_outputs[channel]["filter"] = {
        "feedforward": [float(x) for x in feedforward],
        "feedback": [float(x) for x in feedback],
    }
    return config


def predistortion_dict(feedforward, feedback, components=None, source=None):
    """Return a serializable predistortion metadata dictionary."""
    return {
        "enabled": True,
        "feedforward": [float(x) for x in feedforward],
        "feedback": [float(x) for x in feedback],
        "components": [[float(a), float(t)] for a, t in (components or [])],
        "source": source,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _json_safe(value):
    if isinstance(value, np.ndarray):
        return [_json_safe(item) for item in value.tolist()]
    if isinstance(value, (np.floating, float)):
        return float(value)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def save_predistortion_json(path, fit_result, metadata=None):
    """Save a predistortion fit/filter result to JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "enabled": True,
        "feedforward": [float(x) for x in fit_result.get("feedforward", [])],
        "feedback": [float(x) for x in fit_result.get("feedback", [])],
        "components": [[float(a), float(t)] for a, t in fit_result.get("components", [])],
        "method": fit_result.get("method", "exponential"),
        "normalization": float(fit_result.get("normalization", 1.0)),
        "rms": float(fit_result.get("rms", np.nan)),
        "success": bool(fit_result.get("success", False)),
        "error": fit_result.get("error"),
        "feedforward_clipped": bool(fit_result.get("feedforward_clipped", False)),
        "feedback_clipped": bool(fit_result.get("feedback_clipped", False)),
        "multiplier_clipped": bool(fit_result.get("multiplier_clipped", False)),
        "undamped_multiplier_clipped": bool(fit_result.get("undamped_multiplier_clipped", False)),
        "segment_edges_ns": [float(x) for x in fit_result.get("segment_edges_ns", [])],
        "multipliers": [float(x) for x in fit_result.get("multipliers", [])],
        "undamped_multipliers": [float(x) for x in fit_result.get("undamped_multipliers", [])],
        "previous_multipliers": [float(x) for x in fit_result.get("previous_multipliers", [])],
        "adjustment_multipliers": [float(x) for x in fit_result.get("adjustment_multipliers", [])],
        "damped_adjustment_multipliers": [
            float(x) for x in fit_result.get("damped_adjustment_multipliers", [])
        ],
        "composed_with_applied_flux_tail_compensation": bool(
            fit_result.get("composed_with_applied_flux_tail_compensation", False)
        ),
        "source_compensation": fit_result.get("source_compensation", None),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "metadata": metadata or {},
    }
    if "composition_damping" in fit_result:
        payload["composition_damping"] = float(fit_result["composition_damping"])
    if "correction_gain" in fit_result:
        payload["correction_gain"] = float(fit_result["correction_gain"])
    if "undamped_rms" in fit_result:
        payload["undamped_rms"] = float(fit_result["undamped_rms"])
    if "desired_response" in fit_result:
        payload["desired_response"] = fit_result.get("desired_response", None)
    desired_response_level = fit_result.get(
        "desired_response_level",
        fit_result.get("desired_level", None),
    )
    if desired_response_level is not None and np.isfinite(float(desired_response_level)):
        payload["desired_response_level"] = float(desired_response_level)
    if "model_note" in fit_result:
        payload["model_note"] = fit_result.get("model_note")
    if "staged_model" in fit_result:
        payload["staged_model"] = _json_safe(fit_result["staged_model"])
    if "rise_decay_bump_model" in fit_result:
        payload["rise_decay_bump_model"] = _json_safe(fit_result["rise_decay_bump_model"])
    path.write_text(json.dumps(payload, indent=2))
    return str(path)


def load_predistortion_json(path):
    """Load a predistortion JSON file produced by ``save_predistortion_json``."""
    payload = json.loads(Path(path).read_text())
    payload["feedforward"] = [float(x) for x in payload.get("feedforward", [])]
    payload["feedback"] = [float(x) for x in payload.get("feedback", [])]
    payload["components"] = [
        (float(component[0]), float(component[1])) for component in payload.get("components", [])
    ]
    payload["segment_edges_ns"] = [float(x) for x in payload.get("segment_edges_ns", [])]
    payload["multipliers"] = [float(x) for x in payload.get("multipliers", [])]
    payload["undamped_multipliers"] = [float(x) for x in payload.get("undamped_multipliers", [])]
    payload["previous_multipliers"] = [float(x) for x in payload.get("previous_multipliers", [])]
    payload["adjustment_multipliers"] = [float(x) for x in payload.get("adjustment_multipliers", [])]
    payload["damped_adjustment_multipliers"] = [
        float(x) for x in payload.get("damped_adjustment_multipliers", [])
    ]
    if "desired_response_level" in payload:
        payload["desired_response_level"] = float(payload["desired_response_level"])
    elif "desired_level" in payload:
        payload["desired_response_level"] = float(payload["desired_level"])
    if "correction_gain" in payload:
        payload["correction_gain"] = float(payload["correction_gain"])
    return payload


def simulate_filtered_step(exponential_components, feedforward, feedback, n_samples):
    """Return ideal, unfiltered, and filtered normalized step responses."""
    n_samples = int(n_samples)
    time_ns = np.arange(n_samples, dtype=float)
    ideal = np.ones(n_samples, dtype=float)
    plant = multi_expdecay(time_ns, *np.asarray(exponential_components, dtype=float).ravel())
    dac_output = signal.lfilter(feedforward, [1.0] + [-float(tap) for tap in feedback], ideal)
    return {
        "time_ns": time_ns,
        "ideal": ideal,
        "unfiltered": plant,
        "dac_output": dac_output,
        "filtered": plant * dac_output,
    }


def rise_decay_bump_model(time_zeroed_ns, asymptote, late_amplitude, late_tau_ns, bump_amplitude, rise_tau_ns, bump_tau_ns):
    time_zeroed_ns = np.asarray(time_zeroed_ns, dtype=float)
    time_zeroed_ns = np.maximum(time_zeroed_ns, 0.0)
    late_tau_ns = max(float(late_tau_ns), 0.1)
    rise_tau_ns = max(float(rise_tau_ns), 0.1)
    bump_tau_ns = max(float(bump_tau_ns), 0.1)
    late = float(late_amplitude) * np.exp(np.clip(-time_zeroed_ns / late_tau_ns, -80.0, 80.0))
    bump = (
        float(bump_amplitude)
        * (1.0 - np.exp(np.clip(-time_zeroed_ns / rise_tau_ns, -80.0, 80.0)))
        * np.exp(np.clip(-time_zeroed_ns / bump_tau_ns, -80.0, 80.0))
    )
    return float(asymptote) + late + bump


def fit_rise_decay_bump_response_model(time_ns, response, fit_tail_fraction=0.25):
    time_ns = np.asarray(time_ns, dtype=float)
    response = np.asarray(response, dtype=float)
    valid = np.isfinite(time_ns) & np.isfinite(response)
    time_ns = time_ns[valid]
    response = response[valid]
    if time_ns.size < 12:
        raise ValueError("Not enough finite points to fit rise-decay bump response.")

    order = np.argsort(time_ns)
    time_ns = time_ns[order]
    response = response[order]
    time_zeroed_ns = time_ns - float(time_ns[0])
    n_points = int(time_zeroed_ns.size)
    span_ns = max(float(time_zeroed_ns[-1] - time_zeroed_ns[0]), 1.0)
    response_min = float(np.nanmin(response))
    response_max = float(np.nanmax(response))
    response_span = max(response_max - response_min, 1e-9)
    tail_count = max(3, int(np.ceil(n_points * float(fit_tail_fraction))))
    tail_count = min(tail_count, n_points)
    asymptote_guess = float(np.nanmean(response[-tail_count:]))
    late_amplitude_guess = float(response[0] - asymptote_guess)
    lower = np.asarray(
        [
            response_min - 5.0 * response_span,
            -10.0 * response_span,
            0.1,
            -10.0 * response_span,
            0.1,
            0.1,
        ],
        dtype=float,
    )
    upper = np.asarray(
        [
            response_max + 5.0 * response_span,
            10.0 * response_span,
            max(100.0 * span_ns, 1.0),
            10.0 * response_span,
            max(100.0 * span_ns, 1.0),
            max(100.0 * span_ns, 1.0),
        ],
        dtype=float,
    )

    late_tau_guesses = [max(span_ns * scale, 0.1) for scale in (1 / 5, 1 / 2, 1, 2, 5)]
    rise_tau_guesses = [max(span_ns * scale, 0.1) for scale in (1 / 100, 1 / 50, 1 / 20, 1 / 10)]
    bump_tau_guesses = [max(span_ns * scale, 0.1) for scale in (1 / 50, 1 / 20, 1 / 10, 1 / 5, 1 / 2)]
    bump_amplitude_guesses = [
        -0.50 * response_span,
        -0.25 * response_span,
        -0.10 * response_span,
        0.10 * response_span,
        0.25 * response_span,
        0.50 * response_span,
    ]

    best = None
    errors = []
    for late_tau_guess in late_tau_guesses:
        for rise_tau_guess in rise_tau_guesses:
            for bump_tau_guess in bump_tau_guesses:
                for bump_amplitude_guess in bump_amplitude_guesses:
                    p0 = np.asarray(
                        [
                            asymptote_guess,
                            late_amplitude_guess,
                            late_tau_guess,
                            bump_amplitude_guess,
                            rise_tau_guess,
                            bump_tau_guess,
                        ],
                        dtype=float,
                    )
                    p0 = np.clip(p0, lower + 1e-12, upper - 1e-12)
                    try:
                        result = optimize.least_squares(
                            lambda params: rise_decay_bump_model(time_zeroed_ns, *params) - response,
                            p0,
                            bounds=(lower, upper),
                            max_nfev=100_000,
                            xtol=1e-12,
                            ftol=1e-12,
                            gtol=1e-12,
                        )
                        fit_response = rise_decay_bump_model(time_zeroed_ns, *result.x)
                        residual = response - fit_response
                        rss = float(np.nansum(residual**2))
                        rss = max(rss, 1e-300)
                        rms = float(np.sqrt(np.nanmean(residual**2)))
                        bic = float(n_points * np.log(rss / n_points) + len(result.x) * np.log(n_points))
                        if best is None or bic < best["bic"]:
                            best = {
                                "params": np.asarray(result.x, dtype=float),
                                "fit_response": fit_response,
                                "residual": residual,
                                "rms": rms,
                                "bic": bic,
                                "success": bool(result.success),
                                "error": None if result.success else result.message,
                            }
                    except Exception as exc:
                        errors.append(str(exc))
    if best is None:
        raise RuntimeError("; ".join(errors[-5:]) if errors else "Rise-decay bump fit failed.")

    params = np.asarray(best["params"], dtype=float)
    return {
        "success": bool(best["success"]),
        "error": best["error"],
        "method": "late_exponential_plus_rise_decay_bump",
        "time_ns": time_ns,
        "time_zeroed_ns": time_zeroed_ns,
        "response": response,
        "asymptote": float(params[0]),
        "late_amplitude": float(params[1]),
        "late_tau_ns": float(params[2]),
        "bump_amplitude": float(params[3]),
        "rise_tau_ns": float(params[4]),
        "bump_tau_ns": float(params[5]),
        "fit_response": np.asarray(best["fit_response"], dtype=float),
        "residual": np.asarray(best["residual"], dtype=float),
        "rms": float(best["rms"]),
        "bic": float(best["bic"]),
    }


# =========================================================================== #
#  QICK-specific extensions (TLS_Spectroscopy port) -- everything ABOVE this
#  line is the VERBATIM QUA LabCode/Helpers/flux_predistortion.py, and the two
#  rise_decay_bump functions below it are lifted verbatim from
#  m_qubit_step_response.py (de-methodized).  Below: the fast-flux waveform
#  baker and the JSON discovery/validation wrappers the QICK runner uses.
# =========================================================================== #
import os as _os
import glob as _glob


def load_compensation_json(json_path):
    """VERBATIM QubitFluxStepResponse.load_piecewise_dc_compensation_json."""
    payload = load_predistortion_json(json_path)
    allowed_methods = {
        "rise_decay_bump_set_dc_offset_correction",
    }
    if payload.get("method") not in allowed_methods:
        raise ValueError(
            "flux_tail_compensation_json must contain a supported set_dc_offset "
            f"compensation, got method={payload.get('method')!r}: {json_path}"
        )
    if not payload.get("success", True):
        raise ValueError(f"Refusing to apply unsuccessful flux-tail compensation: {json_path}")
    if payload.get("multiplier_clipped", False):
        raise ValueError(f"Refusing to apply clipped flux-tail compensation: {json_path}")
    return {
        "enabled": True,
        "method": payload.get("method"),
        "source": str(json_path),
        "segment_edges_ns": payload.get("segment_edges_ns", []),
        "multipliers": payload.get("multipliers", []),
        "undamped_multipliers": payload.get("undamped_multipliers", []),
        "correction_gain": payload.get("correction_gain", None),
        "metadata": payload.get("metadata", {}),
    }


def find_latest_compensation_json(
    outer_folder,
    qubit,
    dc_offset=None,
    baseline_dc_offset=None,
    require_success=True,
):
    """VERBATIM QubitFluxStepResponse.find_latest_rise_decay_bump_dc_compensation_json."""
    qubit_dir = Path(outer_folder) / qubit
    pattern = f"{qubit}_*_rise_decay_bump_dc_compensation.json"
    if not qubit_dir.exists():
        return None
    candidates = list(qubit_dir.rglob(pattern))
    if not candidates:
        return None
    matching_candidates = []
    for candidate in candidates:
        try:
            payload = load_predistortion_json(candidate)
        except Exception:
            continue
        if payload.get("method") != "rise_decay_bump_set_dc_offset_correction":
            continue
        if require_success and not payload.get("success", True):
            continue
        if payload.get("multiplier_clipped", False):
            continue
        metadata = payload.get("metadata", {})
        candidate_dc = metadata.get("dc_offset", None)
        candidate_baseline = metadata.get("baseline_dc_offset", None)
        if dc_offset is not None:
            if candidate_dc is None or not np.isclose(float(candidate_dc), float(dc_offset), atol=1e-9):
                continue
        if baseline_dc_offset is not None:
            if candidate_baseline is None or not np.isclose(
                float(candidate_baseline),
                float(baseline_dc_offset),
                atol=1e-9,
            ):
                continue
        matching_candidates.append(candidate)
    if not matching_candidates:
        return None
    latest = max(matching_candidates, key=lambda path: path.stat().st_mtime)
    return str(latest)


def scale_compensation_gain(flux_tail_compensation, gain, min_multiplier=None, max_multiplier=None):
    """VERBATIM QUA Control _scale_flux_tail_compensation_gain."""
    import copy
    if flux_tail_compensation is None:
        raise ValueError("Cannot sweep gain without a loaded flux-tail compensation.")
    gain = float(gain)
    if not np.isfinite(gain) or gain < 0.0:
        raise ValueError("flux_tail_compensation_gain_sweep values must be finite and non-negative.")

    scaled = copy.deepcopy(flux_tail_compensation)
    multipliers = np.asarray(scaled.get("multipliers", []), dtype=float)
    undamped = np.asarray(scaled.get("undamped_multipliers", []), dtype=float)
    if undamped.size != multipliers.size or not np.all(np.isfinite(undamped)):
        source_gain = scaled.get("correction_gain", None)
        try:
            source_gain = float(source_gain)
        except (TypeError, ValueError):
            source_gain = 1.0
        if np.isfinite(source_gain) and abs(source_gain) > 1e-12:
            undamped = 1.0 + (multipliers - 1.0) / source_gain
        else:
            undamped = multipliers.copy()

    new_multipliers = 1.0 + gain * (undamped - 1.0)
    clipped = False
    if min_multiplier is not None and max_multiplier is not None:
        min_multiplier = float(min_multiplier)
        max_multiplier = float(max_multiplier)
        clipped = bool(
            np.any(new_multipliers < min_multiplier)
            or np.any(new_multipliers > max_multiplier)
        )
        new_multipliers = np.clip(new_multipliers, min_multiplier, max_multiplier)

    scaled["multipliers"] = [float(x) for x in new_multipliers]
    scaled["undamped_multipliers"] = [float(x) for x in undamped]
    scaled["correction_gain"] = gain
    scaled["gain_sweep_multiplier_clipped"] = clipped
    return scaled


def build_predistorted_ff_samples(compensation, hold_ns, dt_ns, target_amp, start_amp=0.0):
    """Bake the piecewise multipliers into a sampled fast-flux staircase (the QICK
    stand-in for the QUA real-time set_dc_offset staircase in _hold_flux_step)."""
    edges = np.asarray(compensation["segment_edges_ns"], dtype=float)
    mult = np.asarray(compensation["multipliers"], dtype=float)
    n = max(int(np.ceil(hold_ns / dt_ns)), 1)
    tt = (np.arange(n) + 0.5) * dt_ns
    seg_idx = np.clip(np.searchsorted(edges, tt, side="right") - 1, 0, mult.size - 1)
    levels = mult[seg_idx]
    return start_amp + levels * (target_amp - start_amp)


def build_inclusive_sweep(vmin, vmax, step):
    """np.arange including the upper endpoint when on-grid (QUA build_inclusive_sweep)."""
    step = float(step)
    if step <= 0:
        raise ValueError("step must be > 0")
    return np.arange(float(vmin), float(vmax) + 0.5 * step, step)
