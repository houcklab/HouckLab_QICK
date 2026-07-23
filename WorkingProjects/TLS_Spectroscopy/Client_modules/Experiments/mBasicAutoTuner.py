"""A deliberately simple, measurement-first single-qubit auto tuner.

This module automates the tune-up that has worked manually in this repository:

    resonator -> wide qubit spectrum -> provisional IQ Rabi
    -> bootstrap readout grid -> canonical single-shot control selection
    -> error-amplified SS control -> joint readout/control/duration refinement

The implementation is intentionally independent of :mod:`mAutoTuner`.  Early
averaged-IQ experiments are *seeds*, never verdicts.  The optimization objective is
the exact paired ground/excited ``SingleShotProgram`` used by
``TLSSpectroscopy.py`` step 5, constrained by a calibrated e-f shelving measurement
of population outside the computational subspace.  A weak starting point never
prevents the search, and an optional-stage failure never erases the best directly
measured candidate.

The tuner uses bounded coordinate descent rather than one enormous simultaneous
search.  A full Cartesian search over readout frequency/gain/length and qubit
frequency/gain/length would require millions of long-relax single-shot acquisitions.
Cheap spectroscopy and Rabi maps locate the basin; small direct-SS grids then optimize
the actual quantity of interest and independently remeasure their winners.
"""

from __future__ import annotations

import copy
import datetime
import io
import json
import math
import os
import pickle
import warnings
from contextlib import redirect_stdout
from statistics import NormalDist

import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import OptimizeWarning, curve_fit
from scipy.signal import find_peaks, savgol_filter
from qick import AveragerProgram, RAveragerProgram

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import (
    ExperimentClass, NpEncoder,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mRabiChevronSS import (
    RabiSSProgram,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import (
    SingleShotProgram,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset, ff_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import (
    add_qubit_gaussian, explicit_flat_top_fields, set_readout_pulse,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.ss_helpers import (
    find_blob_median, find_threshold,
)


BASIC_AUTOTUNER_REVISION = "manual-workflow-v7"


BASIC_DEFAULTS = {
    "random_seed": 271828,
    "max_consecutive_point_failures": 5,
    # ``concise`` keeps the operator informed at human-scale stage boundaries while
    # retaining every technical message in data['report'].  Set to ``detailed`` only
    # when debugging an acquisition problem.
    "console": {"verbosity": "concise"},
    "calibration_drift": {
        "max_angle_degrees": 25.0,
        "max_independent_fidelity_change": 0.08,
        "max_fixed_discriminator_fidelity_loss": 0.08,
        "max_midpoint_shift_fraction": 0.25,
    },
    "reset": {
        # Direct-control stages use fresh tProc feedback once a usable readout/pi tuple
        # exists.  Readout-coordinate maps deliberately revert to passive reset because
        # their changing integration length/frequency/gain invalidates one raw feedback
        # threshold; the winner is re-probed immediately afterward.
        "enabled": True, "probe_shots": 2000, "max_iters": 3,
        "min_activation_fidelity": 0.75,
        "min_raw_assignment_fidelity": 0.80,
        # Clear residual measurement photons before every calibrated control pulse.
        # Kept explicit in the saved reset record even though the shared primitive
        # also fails safe to this value for non-tuner callers.
        "thermalization_us": 25.0,
        "post_measure_delay_us": 0.05,
    },
    "baseline": {"shots": 800, "blocks": 2},
    "resonator": {
        "enabled": True, "span_mhz": 4.0, "points": 61, "shots": 120,
        "polarity": "dip", "wide_span_mhz": 12.0, "wide_points": 101,
        "min_contrast_snr": 3.0, "always_wide": True,
        # Averaged discovery must not inherit a deliberately bad/zero input readout.
        # The input gain is also tried; whichever gives the clearest local response is
        # used only as a bootstrap and never written without direct SS optimization.
        "discovery_gain": 5000, "discovery_length_us": 10.0,
    },
    "spectroscopy": {
        "enabled": True, "local_span_mhz": 20.0, "local_points": 81,
        "wide_span_mhz": 80.0, "wide_points": 121, "gain": 7000,
        "pulse_length_us": 2.0, "shots": 80, "max_candidates": 3,
        "min_feature_snr": 3.0, "always_wide": True,
    },
    "iq_rabi": {
        "enabled": True, "local_span_mhz": 4.0,
        "freq_points_per_candidate": 5, "gain_min": 0, "gain_max": 30000,
        "gain_points": 31, "shots": 60, "min_r2": 0.55,
        "fine_gain_points": 41, "shortlist": 4,
    },
    "rough_single_shot": {
        # A small direct-SS chevron is run independently in every retained spectral
        # basin before any basin is discarded.  This is the automated counterpart of
        # the manual SS Rabi-chevron step and protects a weak true qubit from a strong
        # but irrelevant TLS ridge or a poor averaged-IQ fit.
        "coarse_shots": 140, "freq_span_mhz": 2.0, "freq_points": 3,
        "gain_fraction": 0.35, "gain_points": 5,
        "shots": 700, "blocks": 2,
    },
    "parity_chevron": {
        "enabled": True, "freq_span_mhz": 1.5, "freq_points": 9,
        "gain_fraction": 0.22, "gain_points": 9, "pulse_counts": [3, 4, 5],
        "shots": 100, "confirm_shots": 600, "confirm_blocks": 2,
        "min_contrast_sigma": 5.0, "min_depth_correctness": 0.55,
        "min_consistent_depth_fraction": 0.67,
    },
    "fine_frequency": {
        # Repeated (+Xpi,-Xpi) pseudoidentity pairs amplify coherent detuning without
        # assuming that half of the X180 DAC code is a calibrated X90.
        "enabled": True, "span_mhz": 1.0, "points": 17, "pairs": 5,
        "shots": 220, "calibration_shots": 500,
        "confirm_shots": 700, "confirm_blocks": 2,
        "min_contrast_sigma": 5.0,
    },
    "amplified_error": {
        # The QUA ``ALE_tune_1Q.py`` file actually runs amplified AMPLITUDE error
        # (AAE), not leakage.  This is its X180 analogue: multi-depth odd/even parity
        # jointly refines frequency and gain.  Several depths suppress the aliases
        # that make a single repeated-pulse count unsafe.
        "enabled": True, "freq_span_mhz": 0.5, "freq_points": 3,
        "gain_fraction": 0.08, "gain_points": 11,
        "pulse_counts": [5, 6, 7, 9, 10, 11, 13, 14, 15],
        "shots": 80, "calibration_shots": 500,
        "confirm_shots": 700, "confirm_blocks": 2,
        "min_contrast_sigma": 5.0, "min_depth_correctness": 0.55,
        "min_consistent_depth_fraction": 0.67,
    },
    "leakage": {
        # The basic workflow defaults to a practical operational screen: compare
        # Gaussian duration/gain/DRAG candidates, reject third-cloud growth and poor
        # normalized odd/even repeated-pulse returns, then independently replay the
        # winner.  This is deliberately *not* called P(f).  Set ``enabled`` to True
        # (or explicitly to ``auto``) only when strict identity+shelving qutrit
        # response inversion is desired as an additional hard gate.
        "enabled": False, "operational_enabled": True,
        "required_for_write": True,
        "operational_depths": [1, 2, 3, 4, 6, 8],
        "operational_shots": 220, "operational_reference_shots": 350,
        "operational_verify_shots": 650, "operational_verify_blocks": 3,
        "operational_max_even_return_error": 0.12,
        "operational_max_odd_inversion_error": 0.12,
        "operational_min_binary_contrast": 0.45,
        "operational_beta_span": 0.08, "operational_beta_points": 7,
        "operational_max_beta_span": 0.16,
        "operational_max_extensions": 2,
        "operational_max_candidate_waveforms": 4,
        "operational_selection_shots": 900,
        "operational_selection_blocks": 3,
        "operational_selection_shortlist": 5,
        # Candidates inside this joint uncertainty/margin band are treated as tied;
        # the longer, lower-power Gaussian wins that tie.
        "operational_fidelity_tie_margin": 0.003,
        "operational_max_tie_fidelity_loss": 0.010,
        "anharmonicity_prior_mhz": None,
        "ef_span_mhz": 100.0, "ef_points": 101,
        "ef_narrow_span_mhz": 6.0, "ef_narrow_points": 61,
        "ef_spec_gain": 7000, "ef_spec_shots": 300,
        "ef_min_feature_snr": 4.0, "ef_max_repeat_error_mhz": 1.5,
        # Keep several peaks from each opposed scan and associate the same physical
        # feature across the two passes.  Comparing only each pass's strongest peak
        # falsely rejects a real e-f line whenever a different weak feature swaps rank.
        "ef_feature_candidates": 8,
        # A separately calibrated long/narrow-bandwidth Gaussian prepares the qutrit
        # response references.  Using the candidate pulse to define "pure e" would
        # absorb its own leakage into the response matrix and make one-pulse P(f)
        # circularly zero by construction.
        "reference_sigma_us": 0.50,
        "reference_gain_max": 30000, "reference_gain_points": 41,
        "reference_rabi_shots": 300, "reference_min_rabi_r2": 0.55,
        "reference_min_contrast": 0.20,
        "reference_max_return_fraction": 0.35,
        "ef_gain_max": 30000, "ef_gain_points": 41,
        "ef_rabi_shots": 300, "ef_min_rabi_r2": 0.55,
        "ef_min_rabi_contrast": 0.15, "ef_max_return_fraction": 0.40,
        # beta is peak derivative-Q / peak Gaussian-I.  Both signs must be searched
        # because the physical sign depends on the mixer/cabling convention.
        "beta_span": 0.08, "beta_points": 7,
        "max_beta_span": 0.20, "max_extensions": 2,
        # Include a direct one-pulse witness and repeated-pulse leakage amplifiers.
        "depths": [1, 2, 4, 8], "gap_phases": [0.0, 0.5],
        "shots": 250, "reference_shots": 400,
        # Leakage maps screen feasibility; a separate round-robin held-out replay
        # selects fidelity so the largest of many noisy beta estimates cannot win.
        "selection_fidelity_shots": 900,
        "selection_fidelity_blocks": 3, "selection_shortlist": 5,
        "verify_shots": 800, "verify_blocks": 3,
        "familywise_alpha": 0.05, "confidence_sigma": 1.96,
        "max_response_condition": 40.0,
        "min_identity_selectivity": 0.45,
        "min_shelving_selectivity": 0.45,
        # Hard constraints.  Fidelity is maximized only inside this feasible set.
        "max_single_p2": 0.02, "max_amplified_p2": 0.03,
        "max_third_blob_excess": 0.05,
        "max_candidate_waveforms": 3,
    },
    "readout": {
        "enabled": True, "freq_span_mhz": 2.0, "freq_points": 11,
        "gain_min": 1000, "gain_max": 10000, "gain_points": 11,
        "shots": 140, "shortlist": 3, "confirm_shots": 600,
        "confirm_blocks": 2,
        "max_tie_fidelity_loss": 0.010,
        "local_freq_span_mhz": 0.8, "local_freq_points": 5,
        "local_gain_fraction": 0.25, "local_gain_points": 5,
    },
    "readout_length": {
        "enabled": True, "values_us": [4.0, 8.0, 14.0, 20.0, 30.0, 45.0],
        "min_us": 1.0, "max_us": 100.0,
        "freq_span_mhz": 0.8, "freq_points": 3,
        # A separate broad power axis is measured at every length.  Reusing one
        # +/-25% neighborhood biases the comparison because short integrations can
        # need several times the drive of long integrations.
        "gain_min": 1000, "gain_max": 10000, "gain_points": 7,
        "shots": 160, "shortlist": 3, "confirm_shots": 700,
        "confirm_blocks": 2,
    },
    "qubit": {
        "enabled": True, "freq_span_mhz": 3.0, "freq_points": 11,
        "gain_fraction": 0.50, "gain_points": 11, "shots": 140,
        "shortlist": 3, "confirm_shots": 700, "confirm_blocks": 2,
        "local_freq_span_mhz": 0.8, "local_freq_points": 7,
        "local_gain_fraction": 0.22, "local_gain_points": 7,
    },
    "pulse_duration": {
        # The physical Gaussian gate length is 4*sigma.  Every sigma gets its own
        # local frequency/gain retune; comparing sigma at one fixed gain is invalid.
        "enabled": True,
        "sigma_values_us": [0.05, 0.10, 0.15, 0.25, 0.35, 0.50],
        "freq_span_mhz": 1.0, "freq_points": 3,
        "gain_fraction": 0.28, "gain_points": 5, "shots": 160,
        "shortlist": 3, "confirm_shots": 700, "confirm_blocks": 2,
    },
    "coordinate_descent_repeat": True,
    "final": {
        "top_candidates": 3, "shots": 1200, "blocks": 3,
        "confidence_sigma": 1.96, "max_block_spread": 0.08,
        # Exact tuples whose confirmation batch was incomplete are audited regardless
        # of raw-score rank, so later coarse outliers cannot erase a real Rabi basin.
        "max_unconfirmed_contenders": 16,
    },
}


TUNED_KEYS = (
    "read_pulse_freq", "read_pulse_gain", "read_length",
    "qubit_freq", "qubit_pi_freq", "qubit_pi_gain", "sigma",
    "qubit_drag_beta",
)


# Human-scale console milestones.  Internal calibration-graph nodes which merely
# re-probe a threshold or repeat a refinement stay in the saved report without
# flooding the terminal.
_CONCISE_STAGE_START = {
    "baseline": "Checking the starting calibration...",
    "resonator": "Finding the resonator...",
    "spectroscopy": "Finding the qubit transition...",
    "iq_rabi": "Finding a rough pi pulse...",
    "readout_grid": "Optimizing the initial readout...",
    "reset_after_bootstrap": "Setting up active reset...",
    "rough_ss": "Refining the pi pulse with single-shot measurements...",
    "parity_chevron": "Checking repeated-pulse errors...",
    "readout_after_control": "Refining readout frequency and power...",
    "readout_length": "Optimizing readout length...",
    "qubit_grid": "Optimizing qubit frequency and amplitude...",
    "pulse_duration": "Optimizing pi-pulse duration...",
    "readout_repeat": "Cross-checking the readout...",
    "qubit_repeat": "Cross-checking the pi pulse...",
    "amplified_error": "Reducing amplified amplitude error...",
    "final": "Comparing the best measured calibrations...",
    "operational_leakage": "Screening pulse duration, power, and DRAG...",
    "operational_leakage_verify": "Verifying the leakage-sensitive checks...",
    "leakage": "Optimizing under the leakage constraint...",
    "qubit_post_leakage": "Rechecking the pi pulse after leakage optimization...",
    "readout_post_leakage": "Rechecking the readout after leakage optimization...",
    "leakage_verify": "Verifying leakage independently...",
    "final_safe": "Running the final screened validation...",
    "final_feedback": "Running the final active-reset validation...",
}


def _qubit_gain_sweep_supported(soccfg, gen_ch):
    """Whether ``sreg(ch, 'gain')`` is a real standalone amplitude register.

    Interpolated generators pack amplitude into another register.  Incrementing the
    nominal gain register can then compile while leaving the physical pulse amplitude
    fixed, so unknown/packed generators use slower point-by-point compiled pulses.
    """
    try:
        generator = soccfg["gens"][int(gen_ch)]
        gtype = str(generator.get("type", "")).lower()
    except Exception:
        return None
    if not gtype:
        return None
    return bool(gtype.startswith("axis_signal_gen_v"))


def _deep_merge(base, update):
    out = copy.deepcopy(base)
    for key, value in (update or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _robust_scale(x):
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if not x.size:
        return np.nan
    return float(1.4826 * np.median(np.abs(x - np.median(x))))


def _binomial_variance_jeffreys(k, n):
    """Posterior variance that remains finite after observing zero events."""
    n = max(int(n), 1)
    a, b = float(k) + 0.5, float(n - k) + 0.5
    return float(a * b / ((a + b) ** 2 * (a + b + 1.0)))


def _simultaneous_z(comparisons, alpha=0.05, floor=1.96):
    """Two-sided Bonferroni confidence multiplier for a screened family."""
    count = max(int(comparisons), 1)
    alpha = float(np.clip(alpha, 1e-9, 0.5))
    return float(max(float(floor), NormalDist().inv_cdf(
        1.0 - alpha / (2.0 * count))))


def _third_blob_diagnostics(c0, c1, theta, scale_factor, sigma_cut=4.0):
    """Find population far from both robust g/e blobs without calling it leakage.

    This catches a separated third cloud even when it lies on the ``excited`` side of
    the binary threshold and therefore leaves step-5 fidelity deceptively high.  The
    excess excited-preparation tail is the useful control diagnostic; common tails in
    both preparations are more likely readout/amplifier pathology.  This remains an
    operational anomaly metric, not P(f); strict mode can measure P(f) separately by
    shelving response inversion.
    """
    rotation = np.exp(-1j * float(theta))
    g = rotation * np.asarray(c0, dtype=complex)
    e = rotation * np.asarray(c1, dtype=complex)
    # Apply the discriminator sign only to x.  Euclidean distances are sign invariant,
    # but keeping the same orientation makes saved centres directly interpretable.
    xg, xe = float(scale_factor) * g.real, float(scale_factor) * e.real
    yg, ye = g.imag, e.imag
    cg = np.array([np.median(xg), np.median(yg)], dtype=float)
    ce = np.array([np.median(xe), np.median(ye)], dtype=float)
    separation = float(np.linalg.norm(ce - cg))

    def radius(x, y):
        # A small separation-relative floor prevents a mathematically zero orthogonal
        # MAD from classifying harmless ADC quantization as a third state.
        return max(0.5 * (_robust_scale(x) + _robust_scale(y)),
                   0.01 * separation, 1e-12)

    sg, se = radius(xg, yg), radius(xe, ye)

    def flags(x, y):
        points = np.column_stack([x, y])
        d2 = np.minimum(
            np.sum((points - cg) ** 2, axis=1) / (sg * sg),
            np.sum((points - ce) ** 2, axis=1) / (se * se),
        )
        return d2 > float(sigma_cut) ** 2

    fg, fe = flags(xg, yg), flags(xe, ye)
    kg, ke = int(np.count_nonzero(fg)), int(np.count_nonzero(fe))
    ng, ne = max(int(fg.size), 1), max(int(fe.size), 1)
    pg, pe = float(kg / ng), float(ke / ne)
    excess = max(0.0, pe - pg)
    excess_se = math.sqrt(
        _binomial_variance_jeffreys(ke, ne)
        + _binomial_variance_jeffreys(kg, ng))
    return {
        "outlier_frac": float((kg + ke) / (ng + ne)),
        "ground_outlier_frac": pg,
        "excited_outlier_frac": pe,
        "third_blob_excess": excess,
        "third_blob_excess_se": float(excess_se),
        "third_blob_excess_ucb_95": float(excess + 1.96 * excess_se),
        "outlier_sigma_cut": float(sigma_cut),
    }


def ground_fraction_with_discriminator(i, q, metrics):
    """Ground-labelled fraction and Jeffreys uncertainty for a fixed g/e axis."""
    labels = discriminate_with_metrics(i, q, metrics)
    n = int(labels.size)
    if n < 10:
        return np.nan, np.inf
    k = int(np.count_nonzero(labels == 0))
    return float(k / n), float(math.sqrt(_binomial_variance_jeffreys(k, n)))


def solve_shelved_qutrit_population(calibration, target_identity, target_shelved,
                                    max_condition=40.0):
    """Estimate P(g/e/f) from calibrated identity and f-selective shelving.

    Each calibration column is ``(p_g identity, se, p_g shelved, se)``.  The
    shelving sequence e-f pi followed by g-e pi maps f to g while mapping g/e away
    from g.  Together with ordinary binary readout and normalization this gives a
    measured 3x3 response matrix.  Ill-conditioned and nonphysical inversions fail
    closed instead of fabricating a small leakage value.
    """
    try:
        columns = [calibration[name] for name in ("g", "e", "f")]
        matrix = np.array([
            [float(column[0]) for column in columns],
            [float(column[2]) for column in columns],
            [1.0, 1.0, 1.0],
        ], dtype=float)
        matrix_se = np.array([
            [float(column[1]) for column in columns],
            [float(column[3]) for column in columns],
            [0.0, 0.0, 0.0],
        ], dtype=float)
        observed = np.array([
            float(target_identity[0]), float(target_shelved[0]), 1.0],
            dtype=float)
        observed_se = np.array([
            float(target_identity[1]), float(target_shelved[1]), 0.0],
            dtype=float)
        condition = float(np.linalg.cond(matrix))
        inverse = np.linalg.inv(matrix)
        raw = inverse @ observed
    except Exception:
        return {"ok": False, "population": np.full(3, np.nan),
                "population_se": np.full(3, np.inf), "condition": np.inf,
                "p2": np.nan, "p2_se": np.inf}
    covariance = inverse @ np.diag(observed_se ** 2) @ inverse.T
    # d(A^-1 b)/dA_rc = -A^-1[:, r] p[c].
    for row in range(2):
        for column in range(3):
            gradient = -inverse[:, row] * raw[column]
            covariance += np.outer(gradient, gradient) * matrix_se[row, column] ** 2
    population_se = np.sqrt(np.maximum(np.diag(covariance), 0.0))
    physical = np.clip(raw, 0.0, None)
    if float(np.sum(physical)) > 0:
        physical /= float(np.sum(physical))
    matrix_ok = bool(np.isfinite(condition) and condition <= float(max_condition))
    physical_ok = bool(
        np.all(raw >= -3.0 * population_se)
        and np.all(raw <= 1.0 + 3.0 * population_se))
    return {
        "ok": bool(matrix_ok and physical_ok
                   and np.all(np.isfinite(population_se))),
        "population": physical, "population_raw": raw,
        "population_se": population_se,
        "p2": float(physical[2]), "p2_raw": float(raw[2]),
        "p2_se": float(population_se[2]), "condition": condition,
        "response_matrix": matrix, "response_matrix_se": matrix_se,
        "matrix_ok": matrix_ok, "physical_ok": physical_ok,
    }


def _candidate_key(candidate):
    return (
        round(float(candidate["read_pulse_freq"]), 9),
        int(round(candidate["read_pulse_gain"])),
        round(float(candidate["read_length"]), 9),
        round(float(candidate["qubit_pi_freq"]), 9),
        int(round(candidate["qubit_pi_gain"])),
        round(float(candidate["sigma"]), 9),
        round(float(candidate.get("qubit_drag_beta", 0.0)), 9),
    )


def _candidate_from_cfg(cfg):
    # Do not use ``dict.get(key, cfg[other])`` here: Python evaluates the default
    # expression eagerly, so a perfectly valid config containing only
    # ``qubit_pi_freq`` would still raise KeyError while constructing its fallback.
    qf = float(cfg["qubit_pi_freq"] if "qubit_pi_freq" in cfg
               else cfg["qubit_freq"])
    return {
        "read_pulse_freq": float(cfg["read_pulse_freq"]),
        "read_pulse_gain": int(round(cfg["read_pulse_gain"])),
        "read_length": float(cfg["read_length"]),
        "qubit_freq": qf,
        "qubit_pi_freq": qf,
        "qubit_pi_gain": int(round(cfg["qubit_pi_gain"])),
        "sigma": float(cfg["sigma"]),
        # Starts as part of physical identity; the direct leakage stage may optimize it.
        "qubit_drag_beta": float(cfg.get("qubit_drag_beta", 0.0) or 0.0),
    }


def _with_candidate(candidate, **changes):
    out = dict(candidate)
    out.update(changes)
    if "qubit_pi_freq" in changes and "qubit_freq" not in changes:
        out["qubit_freq"] = float(changes["qubit_pi_freq"])
    if "qubit_freq" in changes and "qubit_pi_freq" not in changes:
        out["qubit_pi_freq"] = float(changes["qubit_freq"])
    out["read_pulse_gain"] = int(round(out["read_pulse_gain"]))
    out["qubit_pi_gain"] = int(round(out["qubit_pi_gain"]))
    return out


def _unique_candidates(candidates):
    out, seen = [], set()
    for candidate in candidates:
        key = _candidate_key(candidate)
        if key not in seen:
            seen.add(key)
            out.append(dict(candidate))
    return out


def step5_metrics(ig, qg, ie, qe):
    """Reproduce TLS step-5 fidelity and return its operational discriminator.

    This intentionally uses ``find_blob_median`` and the same 100-threshold
    ``find_threshold`` sweep as :class:`SingleShot1Q`.  Consequently a manual step-5
    result such as 0.9165 is reported on the same scale here (balanced assignment
    fidelity), rather than the older visibility convention ``2*F-1``.
    """
    ig, qg = np.asarray(ig, dtype=float), np.asarray(qg, dtype=float)
    ie, qe = np.asarray(ie, dtype=float), np.asarray(qe, dtype=float)
    n = min(ig.size, qg.size, ie.size, qe.size)
    if n < 20:
        raise ValueError("at least 20 paired ground/excited shots are required")
    ig, qg, ie, qe = ig[:n], qg[:n], ie[:n], qe[:n]
    good = np.isfinite(ig) & np.isfinite(qg) & np.isfinite(ie) & np.isfinite(qe)
    ig, qg, ie, qe = ig[good], qg[good], ie[good], qe[good]
    n = ig.size
    if n < 20:
        raise ValueError("too few finite paired ground/excited shots")

    c0, c1 = ig + 1j * qg, ie + 1j * qe
    center_g = complex(find_blob_median(c0))
    center_e = complex(find_blob_median(c1))
    theta = float(np.angle(center_e - center_g))
    xg = np.real(np.exp(-1j * theta) * c0)
    xe = np.real(np.exp(-1j * theta) * c1)
    thresholds, fidelities = find_threshold(xg.astype(complex), xe.astype(complex))
    k = int(np.nanargmax(fidelities))
    threshold = float(thresholds[k])
    fidelity = float(fidelities[k])

    factor = 1.0
    if float(np.mean(xg)) > threshold:
        factor = -1.0
        xg, xe, threshold = -xg, -xe, -threshold
    p_e_given_g = float(np.mean(xg > threshold))
    p_g_given_e = float(np.mean(xe < threshold))
    confusion = np.array([
        [1.0 - p_e_given_g, p_g_given_e],
        [p_e_given_g, 1.0 - p_g_given_e],
    ])
    # The exact helper's finite threshold grid defines fidelity.  The confusion matrix
    # is retained for directional errors and uncertainty and should agree to O(1/n).
    var = (p_e_given_g * (1.0 - p_e_given_g)
           + p_g_given_e * (1.0 - p_g_given_e)) / (4.0 * n)
    # Jeffreys-scale floor avoids claiming zero uncertainty after observing zero errors.
    fidelity_se = float(math.sqrt(max(var, 0.25 / (n + 1.0) ** 2)))
    sg = max(_robust_scale(xg), 1e-12)
    se = max(_robust_scale(xe), 1e-12)
    sep_sigma = float(abs(np.median(xe) - np.median(xg)) / (0.5 * (sg + se)))
    anomaly = _third_blob_diagnostics(c0, c1, theta, factor)
    return {
        "fidelity": fidelity,
        "fidelity_se": fidelity_se,
        "fidelity_lcb_95": float(fidelity - 1.96 * fidelity_se),
        "visibility": float(2.0 * fidelity - 1.0),
        "p_e_given_g": p_e_given_g,
        "p_g_given_e": p_g_given_e,
        "confusion": confusion,
        "read_theta": theta,
        "scale_factor": factor,
        "threshold": threshold,
        "sep_sigma": sep_sigma,
        "shots_per_state": int(n),
        "ground_center_i": float(center_g.real),
        "ground_center_q": float(center_g.imag),
        "excited_center_i": float(center_e.real),
        "excited_center_q": float(center_e.imag),
        "projected_ground_center": float(
            factor * np.real(np.exp(-1j * theta) * center_g)),
        "projected_excited_center": float(
            factor * np.real(np.exp(-1j * theta) * center_e)),
        **anomaly,
    }


def discriminate_with_metrics(i, q, metrics):
    c = np.asarray(i, dtype=float) + 1j * np.asarray(q, dtype=float)
    x = float(metrics["scale_factor"]) * np.real(
        np.exp(-1j * float(metrics["read_theta"])) * c)
    return (x > float(metrics["threshold"])).astype(np.int8)


def fit_anchored_rabi(gains, signal):
    """Fit a damped Rabi cosine whose phase is anchored by the zero-gain point."""
    x, y = np.asarray(gains, dtype=float), np.asarray(signal, dtype=float)
    good = np.isfinite(x) & np.isfinite(y)
    x, y = x[good], y[good]
    if x.size < 9 or np.ptp(x) <= 0:
        return {"ok": False, "pi_gain": np.nan, "r2": -np.inf,
                "contrast": 0.0, "yfit": np.full_like(y, np.nan)}
    order = np.argsort(x)
    x, y = x[order], y[order]
    x = x - x[0]
    span = float(np.ptp(x))
    step = float(np.median(np.diff(np.unique(x))))

    def model(g, offset, amp, pi_gain, decay):
        return offset + amp * np.exp(-g / decay) * np.cos(np.pi * g / pi_gain)

    # FFT plus geometric seeds make the first physical period identifiable even when
    # the high-gain oscillations are strongly damped.
    centred = y - np.mean(y)
    fft = np.fft.rfft(centred * np.hanning(x.size))
    ff = np.fft.rfftfreq(x.size, d=max(step, 1e-9))
    if ff.size > 1:
        fft_pi = 0.5 / max(float(ff[1 + np.argmax(np.abs(fft[1:]))]), 1e-12)
    else:
        fft_pi = span / 3.0
    seeds = [fft_pi, span / 8.0, span / 6.0, span / 4.0,
             span / 3.0, span / 2.0, 0.75 * span]
    best = None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", OptimizeWarning)
        for p0 in seeds:
            if not np.isfinite(p0):
                continue
            try:
                popt, pcov = curve_fit(
                    model, x, y,
                    p0=[float(np.mean(y)), float(y[0] - np.mean(y)),
                        float(np.clip(p0, 0.6 * step, span)), 3.0 * span],
                    # pi_gain below one gain step is a discrete-time alias of a much
                    # slower Rabi oscillation, not a resolvable first inversion.
                    bounds=([-np.inf, -np.inf, 1.05 * step, 0.20 * span],
                            [np.inf, np.inf, 1.25 * span, 1e5 * span]),
                    maxfev=30000,
                )
                yf = model(x, *popt)
                sse = float(np.sum((y - yf) ** 2))
                if best is None or sse < best[0]:
                    best = (sse, popt, pcov, yf)
            except Exception:
                pass
    if best is None:
        return {"ok": False, "pi_gain": np.nan, "r2": -np.inf,
                "contrast": float(np.ptp(y)), "yfit": np.full_like(y, np.nan)}
    sse, popt, pcov, yf = best
    total = float(np.sum((y - np.mean(y)) ** 2)) + 1e-15
    r2 = float(1.0 - sse / total)
    offset, amp, pi_gain, decay = [float(v) for v in popt]
    try:
        pi_err = float(math.sqrt(max(float(pcov[2, 2]), 0.0)))
    except Exception:
        pi_err = np.inf
    ok = bool(np.isfinite(pi_gain) and 1.05 * step <= pi_gain <= span
              and r2 > 0.45 and abs(amp) > 0)
    return {
        "ok": ok, "pi_gain": pi_gain, "pi_gain_err": pi_err,
        "period": 2.0 * pi_gain, "r2": r2,
        "contrast": float(2.0 * abs(amp)), "decay_gain": decay,
        "offset": offset, "amplitude": amp, "x": x, "y": y, "yfit": yf,
    }


def analyze_iq_chevron(freqs, gains, i_map, q_map, min_r2=0.55):
    """Find a coherent Rabi ridge after removing each row's common IQ offset.

    This is the key correction to the existing TLS/QM chevrons: absolute ``I**2+Q**2``
    is dominated by the readout baseline and has no reason to identify a pi pulse.
    """
    freqs, gains = np.asarray(freqs, float), np.asarray(gains, float)
    z = np.asarray(i_map, float) + 1j * np.asarray(q_map, float)
    if z.shape != (freqs.size, gains.size):
        raise ValueError("IQ chevron shape does not match its axes")
    rows = []
    for row, freq in zip(z, freqs):
        d = row - row[0]
        xy = np.column_stack([d.real, d.imag])
        xy -= np.nanmean(xy, axis=0)
        try:
            _, _, vh = np.linalg.svd(np.nan_to_num(xy), full_matrices=False)
            axis = vh[0]
        except Exception:
            axis = np.array([1.0, 0.0])
        projection = d.real * axis[0] + d.imag * axis[1]
        fit = fit_anchored_rabi(gains, projection)
        residual = projection - np.asarray(fit.get("yfit", projection))
        noise = max(_robust_scale(residual), 1e-12)
        snr = float(np.ptp(projection) / noise)
        score = float(max(fit.get("r2", -1.0), -1.0) * math.log1p(max(snr, 0.0)))
        rows.append({"frequency": float(freq), "projection": projection,
                     "fit": fit, "snr": snr, "raw_score": score,
                     "contrast_observed": float(np.ptp(projection))})
    max_contrast = max(max(row["contrast_observed"] for row in rows), 1e-15)
    for row in rows:
        # A vanishing but perfectly sinusoidal numerical/noise trace can have an
        # excellent scale-free r2.  The physical ridge must also carry a substantial
        # fraction of the largest drive-induced displacement in the map.
        relative = float(row["contrast_observed"] / max_contrast)
        row["relative_contrast"] = relative
        row["score"] = float(row["raw_score"] * relative)
    valid = [row for row in rows
             if row["fit"].get("ok") and row["fit"].get("r2", -1) >= min_r2]
    pool = valid if valid else rows
    best = max(pool, key=lambda row: row["score"])
    return {"ok": bool(valid), "best": best, "rows": rows}


def _declare_common(program, include_qubit=True):
    cfg = program.cfg
    program.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                        mixer_freq=cfg.get("mixer_freq", 0),
                        ro_ch=cfg["ro_chs"][0])
    if include_qubit:
        program.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
    # ``ff_park_gain`` is an environmental operating point, never an optimization
    # coordinate.  Declare its generator even when the configured value is zero so
    # every uploaded program can clear a stale nonzero latched FF output.
    ff_pulse.declare_static_park(program)
    for ro_ch in cfg["ro_chs"]:
        program.declare_readout(
            ch=ro_ch, freq=cfg["read_pulse_freq"],
            length=program.us2cycles(cfg["read_length"], ro_ch=cfg["ro_chs"][0]),
            gen_ch=cfg["res_ch"],
        )
    set_readout_pulse(program)


def _replay_static_flux(program):
    """Hold the input configuration's FF park value for this complete repetition."""
    ff_pulse.play_static_park(
        program, settle_us=program.cfg.get("ff_park_settle_us", 0.05))


class BasicTransmissionProgram(AveragerProgram):
    """Static-operating-point readout using the canonical step-5 pulse."""

    def initialize(self):
        self.cfg.setdefault("reps", int(self.cfg.get("shots", 300)))
        _declare_common(self, include_qubit=False)
        self.synci(200)

    def body(self):
        cfg = self.cfg
        _replay_static_flux(self)
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(cfg["relax_delay"]))


class BasicSpecProgram(RAveragerProgram):
    """Hardware frequency sweep of a constant saturation-spectroscopy pulse."""

    def initialize(self):
        cfg = self.cfg
        self.q_rp = self.ch_page(cfg["qubit_ch"])
        self.r_freq = self.sreg(cfg["qubit_ch"], "freq")
        _declare_common(self, include_qubit=True)
        self.f_start = self.freq2reg(cfg["start"], gen_ch=cfg["qubit_ch"])
        self.f_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])
        self.set_pulse_registers(
            ch=cfg["qubit_ch"], style="const", freq=self.f_start, phase=0,
            gain=int(cfg["spec_gain"]),
            length=self.us2cycles(cfg["spec_len_us"], gen_ch=cfg["qubit_ch"]),
        )
        self.synci(200)

    def body(self):
        cfg = self.cfg
        _replay_static_flux(self)
        self.pulse(ch=cfg["qubit_ch"])
        self.sync_all(self.us2cycles(0.02))
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_freq, self.r_freq, "+", self.f_step)


class BasicRabiProgram(RAveragerProgram):
    """Hardware gain sweep of the canonical 4-sigma Gaussian pulse."""

    def initialize(self):
        cfg = self.cfg
        self.q_rp = self.ch_page(cfg["qubit_ch"])
        self.r_gain = self.sreg(cfg["qubit_ch"], "gain")
        _declare_common(self, include_qubit=True)
        add_qubit_gaussian(self)
        if str(cfg.get("reset_mode", "passive")).strip().lower() == "feedback":
            add_qubit_gaussian(
                self, name="qubit_reset",
                sigma_us=float(cfg.get("reset_pi_sigma", cfg["sigma"])),
                drag_beta=float(cfg.get(
                    "reset_pi_drag_beta", cfg.get("qubit_drag_beta", 0.0))))
        self.set_pulse_registers(
            ch=cfg["qubit_ch"], style="arb",
            freq=self.freq2reg(float(cfg["drive_freq"]), gen_ch=cfg["qubit_ch"]),
            phase=self.deg2reg(0, gen_ch=cfg["qubit_ch"]),
            gain=int(cfg["start"]), waveform="qubit",
        )
        self.synci(200)

    def body(self):
        cfg = self.cfg
        _replay_static_flux(self)
        self.pulse(ch=cfg["qubit_ch"])
        self.sync_all(self.us2cycles(0.01))
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_gain, self.r_gain, "+", int(self.cfg["step"]))


class BasicSequenceProgram(AveragerProgram):
    """Generic canonical Gaussian sequence followed by one per-shot readout.

    Legacy callers supply ``sequence_phases_deg`` and one gain/frequency.  Leakage
    calibration supplies ``sequence_ops`` containing ``('pulse', gain, phase)`` for
    the candidate g-e DRAG waveform and ``('pulse_at', gain, phase, frequency,
    'reference')`` for independently calibrated long g-e/e-f reference pulses.
    """

    def initialize(self):
        cfg = self.cfg
        cfg["reps"] = int(cfg.get("shots", cfg.get("reps", 200)))
        _declare_common(self, include_qubit=True)
        add_qubit_gaussian(self)
        if any(op[0] == "pulse_at" and len(op) > 4
               and str(op[4]) == "gaussian"
               for op in cfg.get("sequence_ops", [])):
            # Shelving uses the same duration/clock but no DRAG quadrature; its gain is
            # calibrated independently for every candidate duration.
            add_qubit_gaussian(self, name="qubit_ef", drag_beta=0.0)
        if any(op[0] == "pulse_at" and len(op) > 4
               and str(op[4]) == "reference"
               for op in cfg.get("sequence_ops", [])):
            add_qubit_gaussian(
                self, name="qubit_ref",
                sigma_us=float(cfg["leakage_reference_sigma_us"]),
                drag_beta=0.0)
        self.synci(200)

    def body(self):
        cfg = self.cfg
        _replay_static_flux(self)
        qch = cfg["qubit_ch"]
        feedback = str(cfg.get("reset_mode", "passive")).strip().lower() == "feedback"
        if feedback:
            # This program may later switch among candidate g-e and reference e-f
            # waveforms.  Install the candidate X180 explicitly for reset first; every
            # sequence operation below then installs its own complete pulse registers.
            self.set_pulse_registers(
                ch=qch, style="arb",
                freq=self.freq2reg(float(cfg.get(
                    "reset_pi_freq", cfg["drive_freq"])), gen_ch=qch),
                phase=self.deg2reg(0, gen_ch=qch),
                gain=int(cfg.get("reset_pi_gain", cfg["qubit_pi_gain"])),
                waveform="qubit_reset")
            active_reset.active_reset_block(
                self, ro_ch=cfg["ro_chs"][0],
                threshold_raw=cfg["reset_threshold_raw"],
                oper=cfg.get("reset_oper", "lower"),
                ground_below=cfg.get("reset_ground_below", True),
                max_iters=int(cfg.get("reset_max_iters", 3)),
                reg_val=25, reg_thr=26)
        gap = self.us2cycles(float(cfg.get("seq_gap_us", 0.01)))
        if "sequence_ops" in cfg:
            operations = list(cfg["sequence_ops"])
        else:
            operations = [
                ("pulse", int(cfg["sequence_gain"]), float(phase))
                for phase in cfg["sequence_phases_deg"]
            ]
        last_registers = None
        for operation in operations:
            if operation[0] == "pulse":
                gain, phase = int(operation[1]), float(operation[2])
                frequency = float(cfg["drive_freq"])
                waveform = "qubit"
            elif operation[0] == "pulse_at":
                gain, phase = int(operation[1]), float(operation[2])
                frequency = float(operation[3])
                family = str(operation[4]) if len(operation) > 4 else "qubit"
                if family not in ("qubit", "gaussian", "reference"):
                    raise ValueError("unknown pulse_at waveform %r" % family)
                waveform = ({"gaussian": "qubit_ef", "reference": "qubit_ref"}
                            .get(family, "qubit"))
            elif operation[0] == "delay":
                self.sync_all(self.us2cycles(float(operation[1])))
                continue
            else:
                raise ValueError("unknown sequence operation %r" % (operation,))
            registers = (gain, phase, frequency, waveform)
            if registers != last_registers:
                self.set_pulse_registers(
                    ch=qch, style="arb",
                    freq=self.freq2reg(frequency, gen_ch=qch),
                    phase=self.deg2reg(phase, gen_ch=qch),
                    gain=gain, waveform=waveform)
                last_registers = registers
            self.pulse(ch=qch)
            if gap > 0:
                self.sync_all(gap)
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(
                         cfg.get("active_reset_post_measure_delay_us", 0.05)
                         if feedback else cfg["relax_delay"]))

    def acquire(self, soc, load_pulses=True, progress=False, **kw):
        n_reset = active_reset.active_reset_readouts(self.cfg)
        return super().acquire(
            soc, load_pulses=load_pulses,
            readouts_per_experiment=1 + n_reset, progress=progress, **kw)


def _curve_from_qick(value, n):
    arr = np.asarray(value, dtype=float).squeeze()
    if arr.ndim == 0:
        arr = np.repeat(float(arr), int(n))
    arr = arr.reshape(-1)
    if arr.size < n:
        raise RuntimeError("QICK returned %d points, expected %d" % (arr.size, n))
    return arr[:n]


def _mean_from_qick(value):
    arr = np.asarray(value, dtype=float)
    if not arr.size:
        raise RuntimeError("QICK returned an empty acquisition")
    return float(np.mean(arr))


def _shots_from_program(program, cfg):
    length = program.us2cycles(cfg["read_length"], ro_ch=cfg["ro_chs"][0])
    n = int(cfg["reps"])
    n_reset = active_reset.active_reset_readouts(cfg)
    reads = 1 + n_reset
    di, dq = getattr(program, "di_buf", None), getattr(program, "dq_buf", None)
    if di is not None and dq is not None:
        shot_i = np.asarray(di, dtype=float)[0].reshape((n, reads))[:, n_reset]
        shot_q = np.asarray(dq, dtype=float)[0].reshape((n, reads))[:, n_reset]
        return shot_i / length, shot_q / length
    get_raw = getattr(program, "get_raw", None)
    if callable(get_raw):
        raw = np.asarray(get_raw(), dtype=float).reshape(-1, 2)
        raw = raw.reshape((n, reads, 2))[:, n_reset, :]
        return raw[:, 0] / length, raw[:, 1] / length
    raise RuntimeError("QICK exposes neither di_buf/dq_buf nor get_raw per-shot data")


class BasicAutoTuner(ExperimentClass):
    """Streamlined autotuner built around direct TLS step-5 fidelity.

    Hardware methods beginning with ``_acquire_`` are deliberately narrow injection
    boundaries.  The test suite replaces them with a virtual device; production uses
    the exact QICK programs in this module and ``mSingleShot1Q``.
    """

    def __init__(self, soc=None, soccfg=None, path="", outerFolder="", prefix="data",
                 suffix="Basic_Auto_Tune", cfg=None, meta_dict=None, params=None, **kw):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, suffix=suffix, cfg=copy.deepcopy(cfg),
                         meta_dict=meta_dict, **kw)
        if cfg is None:
            raise ValueError("BasicAutoTuner requires a configuration dictionary")
        self.input_cfg = copy.deepcopy(cfg)
        self.params = _deep_merge(BASIC_DEFAULTS, params)
        self.rng = np.random.default_rng(int(self.params["random_seed"]))
        self.initial = _candidate_from_cfg(self.input_cfg)
        self.working = dict(self.initial)
        self._archive = []
        self._confirmed = []
        self._unconfirmed_contenders = []
        self._maps = {}
        self._stages = []
        self._report = []
        self._key_evidence = {key: [] for key in TUNED_KEYS}
        self._resonator_seed = float(self.initial["read_pulse_freq"])
        self._discovery_readout = dict(self.initial)
        self._spec_candidates_mhz = [float(self.initial["qubit_pi_freq"])]
        self._rabi_candidates = []
        self._interrupted = False
        self._final_replay_completed = False
        self._final_replay_kind = None
        self._fast_gain_sweep = None
        self._leakage_active = self._leakage_enabled()
        self._operational_leakage_active = bool(
            self.params["leakage"].get("operational_enabled", True))
        self._leakage_selected_candidate = None
        self._leakage_ef_calibration = None
        self._leakage_verified_candidate_key = None
        self._reset_runtime = {"reset_mode": "passive"}
        self._reset_readout_key = None
        self._reset_unavailable = False
        self.data = {
            "revision": BASIC_AUTOTUNER_REVISION,
            "autotuner_revision": BASIC_AUTOTUNER_REVISION,
            "fidelity_definition": "TLS step-5 balanced assignment fidelity",
            "selection_objective": (
                "maximize held-out TLS step-5 fidelity subject to direct shelving "
                "P(f) and third-cloud upper-confidence constraints"
                if self._leakage_active else
                "maximize held-out TLS step-5 fidelity inside a fixed Gaussian pulse "
                "family subject to leakage-sensitive repeated-return and third-cloud "
                "upper-confidence constraints"),
            "initial": dict(self.initial),
            "working": dict(self.working),
            "best_found": None,
            "candidate_archive": self._archive,
            "confirmed_candidates": self._confirmed,
            "unconfirmed_contenders": self._unconfirmed_contenders,
            "maps": self._maps,
            "stages": self._stages,
            "report": self._report,
            "confirmation_failures": [],
            "key_evidence": self._key_evidence,
            "eligible_tuned": {},
            "tuned": {},
            "outcome": "not_started",
            "success": False,
            "leakage": {
                "active": bool(
                    self._leakage_active or self._operational_leakage_active),
                "strict_direct_active": bool(self._leakage_active),
                "operational_active": bool(self._operational_leakage_active),
                "required_for_write": bool(
                    (self._leakage_active or self._operational_leakage_active)
                    and self.params["leakage"].get("required_for_write", True)),
                "measurement": (
                    "identity+shelving qutrit response inversion"
                    if self._leakage_active else
                    "operational repeated-return and third-cloud screen"),
                "direct_p2_measured": False,
                "third_blob_guard": True,
                "optimized": False, "verified": False,
                "failure": None,
            },
            "fast_flux_operating_point": {
                "mode": "static_park",
                "configured": bool(ff_pulse.static_park_configured(self.input_cfg)),
                "ff_ch": self.input_cfg.get("ff_ch"),
                "ff_park_gain": int(self.input_cfg.get("ff_park_gain", 0) or 0),
                "tuned": False,
            },
            "reset": {
                "requested": bool(self.params["reset"].get("enabled", True)),
                "mode": "passive", "fresh": False,
                "readout_key": None, "events": [],
                "fallback_relax_delay_us": float(
                    self.input_cfg.get("relax_delay", np.nan)),
            },
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    # ------------------------------------------------------------------ invariants
    @staticmethod
    def _reset_readout_signature(candidate):
        return (
            round(float(candidate["read_pulse_freq"]), 9),
            int(round(candidate["read_pulse_gain"])),
            round(float(candidate["read_length"]), 9),
        )

    def _deactivate_feedback(self, reason=None):
        was_feedback = self._reset_runtime.get("reset_mode") == "feedback"
        self._reset_runtime = {"reset_mode": "passive"}
        self.data["reset"].update({"mode": "passive", "fresh": False})
        if reason is not None:
            event = {"mode": "passive", "reason": str(reason),
                     "readout_key": list(self._reset_readout_signature(self.working))}
            self.data["reset"]["events"].append(event)
            if was_feedback:
                self._log("reset", "OK", "%s; using passive reset for this map"
                          % reason)

    def _working_confirmation_fidelity(self):
        rows = [row for row in self._confirmed
                if _candidate_key(row) == _candidate_key(self.working)]
        return max((float(row.get("fidelity", -np.inf)) for row in rows),
                   default=-np.inf)

    def _try_activate_feedback(self, reason):
        """Freshly calibrate feedback for the exact current readout/control tuple."""
        settings = self.params["reset"]
        if not bool(settings.get("enabled", True)) or self._reset_unavailable:
            return False
        if self.soccfg is None or not active_reset.active_reset_supported(
                self.soccfg, self.input_cfg["ro_chs"][0]):
            self._reset_unavailable = True
            self.data["reset"]["events"].append({
                "mode": "passive", "reason": "feedback path unavailable"})
            return False
        fidelity = self._working_confirmation_fidelity()
        minimum = float(settings.get("min_activation_fidelity", 0.75))
        if not np.isfinite(fidelity) or fidelity < minimum:
            self._log(
                "reset", "WARN",
                "not probing feedback after %s: current held-out F %.3f is below %.3f; "
                "retaining safe passive relaxation" % (reason, fidelity, minimum))
            return False
        probe_cfg = self._cfg_for(self.working, reset_mode="passive")
        try:
            def run_probe():
                return active_reset.probe_reset_params(
                    self.soc, self.soccfg, probe_cfg, path=self.path,
                    outer_folder=self.outerFolder,
                    shots=int(settings.get("probe_shots", 2000)), validate=True,
                    min_raw_fidelity=float(
                        settings.get("min_raw_assignment_fidelity", 0.80)))

            if self._detailed_console():
                rec = run_probe()
            else:
                # The complete raw-IQ/threshold/residual diagnostics remain in the
                # probe artifact and returned reset record.  They are useful for
                # debugging, but not useful as routine operator console output.
                with redirect_stdout(io.StringIO()):
                    rec = run_probe()
        except Exception as exc:
            rec = None
            self._log("reset", "WARN", "feedback probe failed after %s (%s: %s)"
                      % (reason, type(exc).__name__, exc))
        if rec is None:
            self._deactivate_feedback(
                "fresh feedback validation failed after %s" % reason)
            return False
        self._reset_runtime = {
            "reset_mode": "feedback",
            "reset_threshold_raw": int(rec["threshold_raw"]),
            "reset_oper": str(rec.get("oper", "lower")),
            "reset_ground_below": bool(rec.get("ground_below", True)),
            "reset_max_iters": int(settings.get("max_iters", 3)),
            "reset_thermalization_us": float(
                settings.get("thermalization_us", 25.0)),
            "active_reset_post_measure_delay_us": float(
                settings.get("post_measure_delay_us", 0.05)),
            # Freeze the validated correction pulse while candidate pulse parameters
            # are swept.  Otherwise a deliberately bad candidate would also become
            # its own reset pulse and be unfairly penalized by a different initial
            # state rather than by its gate action.
            "reset_pi_freq": float(self.working["qubit_pi_freq"]),
            "reset_pi_gain": int(self.working["qubit_pi_gain"]),
            "reset_pi_sigma": float(self.working["sigma"]),
            "reset_pi_drag_beta": float(
                self.working.get("qubit_drag_beta", 0.0)),
        }
        self._reset_readout_key = self._reset_readout_signature(self.working)
        event = {
            "mode": "feedback", "reason": str(reason),
            "readout_key": list(self._reset_readout_key),
            "threshold_raw": int(rec["threshold_raw"]),
            "oper": str(rec.get("oper", "lower")),
            "ground_below": bool(rec.get("ground_below", True)),
            "validation": rec.get("validation"),
            "raw_assignment_fidelity": rec.get("raw_assignment_fidelity"),
            "raw_assignment_errors": rec.get("raw_assignment_errors"),
            "thermalization_us": float(settings.get("thermalization_us", 25.0)),
        }
        self.data["reset"]["events"].append(event)
        self.data["reset"].update({
            "mode": "feedback", "fresh": True,
            "readout_key": list(self._reset_readout_key),
            "threshold_raw": int(rec["threshold_raw"]),
            "oper": str(rec.get("oper", "lower")),
            "ground_below": bool(rec.get("ground_below", True)),
            "validation": rec.get("validation"),
            "raw_assignment_fidelity": rec.get("raw_assignment_fidelity"),
            "raw_assignment_errors": rec.get("raw_assignment_errors"),
            "thermalization_us": float(settings.get("thermalization_us", 25.0)),
        })
        self._log(
            "reset", "OK",
            "fresh end-to-end feedback reset enabled after %s (threshold %d, %s, "
            "%d passes)" % (reason, int(rec["threshold_raw"]),
                             rec.get("oper", "lower"),
                             int(settings.get("max_iters", 3))))
        return True

    def _leakage_enabled(self):
        """Whether the device configuration identifies a transmon e-f target."""
        settings = self.params["leakage"]
        mode = settings.get("enabled", "auto")
        if not (isinstance(mode, str) and mode.lower() == "auto"):
            return bool(mode)

        def finite(value):
            try:
                return bool(np.isfinite(float(value)))
            except (TypeError, ValueError, OverflowError):
                return False

        return bool(
            finite(self.input_cfg.get("qubit_ef_freq"))
            or finite(self.input_cfg.get("qubit_anharmonicity_mhz"))
            or finite(settings.get("anharmonicity_prior_mhz")))

    def _preflight(self):
        cfg = self.input_cfg
        required = (
            "res_ch", "qubit_ch", "ro_chs", "nqz", "qubit_nqz",
            "read_pulse_freq", "read_pulse_gain", "read_length",
            "qubit_pi_gain", "sigma", "adc_trig_offset", "relax_delay",
        )
        missing = [key for key in required if key not in cfg]
        if "qubit_pi_freq" not in cfg and "qubit_freq" not in cfg:
            missing.append("qubit_pi_freq (or qubit_freq)")
        if missing:
            raise ValueError("missing BasicAutoTuner config keys: %s" % ", ".join(missing))
        if int(cfg["res_ch"]) == int(cfg["qubit_ch"]):
            raise ValueError(
                "res_ch and qubit_ch are both %d; their pulse registers would collide"
                % int(cfg["res_ch"]))
        if len(cfg["ro_chs"]) != 1:
            raise ValueError(
                "basic tuner v1 requires exactly one readout channel; got %r"
                % (cfg["ro_chs"],))
        if str(cfg.get("qubit_pulse_style", "arb")).lower() != "arb":
            raise ValueError("basic tuner requires the canonical arb Gaussian pulse")
        if explicit_flat_top_fields(cfg):
            raise ValueError("basic tuner does not mix flat-top and 4-sigma Gaussian paths")
        if str(cfg.get("read_pulse_style", "const")).lower() != "const":
            raise ValueError("basic tuner requires the canonical constant readout pulse")
        if bool(cfg.get("use_switch", False)) or bool(
                cfg.get("switch_triggered", False)):
            raise ValueError("basic tuner v1 reproduces the step-5 switch-off pulse path")
        park_gain = int(cfg.get("ff_park_gain", 0) or 0)
        if park_gain != 0 and cfg.get("ff_ch", None) is None:
            raise ValueError(
                "nonzero ff_park_gain requires ff_ch so the operating point can be "
                "replayed on every acquisition")
        if cfg.get("ff_ch", None) is not None:
            ff_ch = int(cfg["ff_ch"])
            if ff_ch in (int(cfg["res_ch"]), int(cfg["qubit_ch"])):
                raise ValueError(
                    "ff_ch must be distinct from res_ch and qubit_ch; got %d" % ff_ch)
            try:
                ff_max = int(self.soccfg["gens"][ff_ch]["maxv"])
            except Exception:
                ff_max = None
            if ff_max is not None and abs(park_gain) > ff_max:
                raise ValueError(
                    "ff_park_gain %d exceeds fast-flux generator range +/- %d"
                    % (park_gain, ff_max))
        # A dynamic park->hold excursion is a different experiment timing path.  The
        # basic tuner supports any *static* park value, but it must not silently mix
        # static stages with a pulsed-flux control stage.
        if int(cfg.get("ff_hold_gain", 0) or 0) != 0:
            raise ValueError(
                "basic tuner calibrates the static ff_park_gain operating point; "
                "ff_hold_gain requests a dynamic flux excursion")
        for row in (cfg.get("FF_Qubits", {}) or {}).values():
            if not hasattr(row, "get"):
                continue
            for key in ("Gain_Readout", "Gain_Expt", "Gain_Pulse"):
                if int(row.get(key, 0) or 0) != 0:
                    raise ValueError(
                        "basic tuner supports static ff_park_gain, not legacy dynamic "
                        "FF_Qubits Gain_Readout/Gain_Expt/Gain_Pulse sequences")
        if float(cfg["sigma"]) <= 0 or float(cfg["read_length"]) <= 0:
            raise ValueError("sigma and read_length must be positive")
        self._fast_gain_sweep = _qubit_gain_sweep_supported(
            self.soccfg, cfg["qubit_ch"])
        if self.soccfg is not None and self._fast_gain_sweep is not True:
            self._log(
                "preflight", "WARN",
                "qubit generator does not advertise a standalone gain register; "
                "using slower point-by-point compiled pulses so amplitude really changes")
        if ff_pulse.static_park_configured(cfg):
            self._log(
                "fast_flux", "OK",
                "holding configured ff_park_gain %d DAC on channel %s throughout; "
                "flux is fixed context, not a searched or writable parameter"
                % (park_gain, cfg.get("ff_ch")))

    def _cfg_for(self, candidate=None, **extra):
        c = self.working if candidate is None else candidate
        cfg = copy.deepcopy(self.input_cfg)
        cfg.update({key: c[key] for key in (
            "read_pulse_freq", "read_pulse_gain", "read_length",
            "qubit_freq", "qubit_pi_freq", "qubit_pi_gain", "sigma",
        )})
        cfg["qubit_drag_beta"] = float(c.get(
            "qubit_drag_beta", self.input_cfg.get("qubit_drag_beta", 0.0)) or 0.0)
        # This key is the RAverager register step used by SingleShotProgram.  Omitting
        # it was the exact kind of pulse-path mismatch that made older automatic runs
        # disagree with a 91.65% manual step-5 run.
        cfg["qubit_gain"] = int(round(c["qubit_pi_gain"]))
        cfg["qubit_pulse_style"] = "arb"
        reset = dict(self._reset_runtime)
        # A raw feedback threshold belongs to one exact readout frequency/gain/length.
        # Any mismatched candidate fails closed to passive even if a caller forgot to
        # suspend feedback around a readout-coordinate map.
        if (reset.get("reset_mode") == "feedback"
                and self._reset_readout_signature(c) != self._reset_readout_key):
            reset = {"reset_mode": "passive"}
        cfg.update(reset)
        # Per-shot buffers and requested shot counts must have one unambiguous meaning;
        # inherited software averaging would otherwise make seeds and direct SS use
        # different effective sample sets.
        cfg["rounds"] = 1
        cfg["soft_avgs"] = 1
        cfg["use_switch"] = False
        cfg["switch_triggered"] = False
        cfg.update(extra)
        return cfg

    def _detailed_console(self):
        console = self.params.get("console", {})
        if not isinstance(console, dict):
            return str(console).strip().lower() in ("detailed", "verbose", "debug")
        return str(console.get("verbosity", "concise")).strip().lower() in (
            "detailed", "verbose", "debug")

    @staticmethod
    def _candidate_console_text(candidate):
        if not isinstance(candidate, dict):
            return None
        try:
            text = ("read %.6f MHz / %d DAC / %.1f us; pi %.6f MHz / %d DAC / "
                    "%.1f ns"
                    % (float(candidate["read_pulse_freq"]),
                       int(round(candidate["read_pulse_gain"])),
                       float(candidate["read_length"]),
                       float(candidate["qubit_pi_freq"]),
                       int(round(candidate["qubit_pi_gain"])),
                       4000.0 * float(candidate["sigma"])))
            if np.isfinite(float(candidate.get("fidelity", np.nan))):
                text += "; F=%.3f" % float(candidate["fidelity"])
            return text
        except (KeyError, TypeError, ValueError):
            return None

    def _concise_stage_done(self, name, result):
        if name == "baseline":
            fidelity = (float(result.get("fidelity", np.nan))
                        if isinstance(result, dict) else np.nan)
            print("  Starting fidelity: %s" % (
                "%.3f" % fidelity if np.isfinite(fidelity) else "measured"))
        elif name == "resonator" and result is not None:
            print("  Resonator found near %.6f MHz." % float(result))
        elif name == "spectroscopy" and result:
            values = ", ".join("%.4f" % float(value) for value in result)
            print("  Qubit candidate%s found near %s MHz."
                  % ("s" if len(result) != 1 else "", values))
        elif name == "iq_rabi":
            print("  Rough pi pulse: %.6f MHz at %d DAC."
                  % (self.working["qubit_pi_freq"],
                     int(round(self.working["qubit_pi_gain"]))))
        elif name == "reset_after_bootstrap":
            if bool(result):
                print("  Active reset is ready.")
            else:
                print("  Active reset was unavailable; using passive relaxation.")
        elif name in ("leakage", "operational_leakage"):
            safe = bool((self.data.get("leakage", {}) or {}).get(
                "selection_safe", False))
            print("  Leakage-screened pulse found." if safe else
                  "  No pulse passed every leakage-sensitive check; automatic writes "
                  "are blocked.")
        elif name == "operational_leakage_verify":
            print("  Leakage-sensitive checks passed." if bool(result) else
                  "  Leakage-sensitive checks failed; automatic writes are blocked.")
        elif name == "leakage_verify":
            print("  Leakage verification passed." if bool(result) else
                  "  Leakage verification failed; automatic writes are blocked.")
        elif name in ("readout_grid", "readout_after_control", "readout_length",
                      "readout_repeat", "readout_post_leakage"):
            print("  Readout selected: %.6f MHz / %d DAC / %.1f us."
                  % (self.working["read_pulse_freq"],
                     int(round(self.working["read_pulse_gain"])),
                     self.working["read_length"]))
        elif name in ("rough_ss", "qubit_grid", "pulse_duration", "qubit_repeat",
                      "qubit_post_leakage"):
            print("  Pi pulse selected: %.6f MHz / %d DAC / %.1f ns."
                  % (self.working["qubit_pi_freq"],
                     int(round(self.working["qubit_pi_gain"])),
                     4000.0 * self.working["sigma"]))
        elif name in ("parity_chevron", "amplified_error"):
            print("  Repeated-pulse refinement complete.")
        elif name in ("final", "final_safe", "final_feedback"):
            text = self._candidate_console_text(result)
            print("  Validation complete%s." % ((": " + text) if text else ""))
        else:
            print("  Done.")

    def _log(self, stage, level, message):
        level = str(level).upper()
        row = {"stage": str(stage), "level": level, "message": str(message),
               "time": datetime.datetime.now().strftime("%H:%M:%S")}
        self._report.append(row)
        if self._detailed_console():
            print("  [%-16s] %-4s %s" % (str(stage)[:16], level, message))

    def _run_stage(self, name, function):
        row = {"name": name, "status": "running", "error": None}
        self._stages.append(row)
        concise_message = None if self._detailed_console() else _CONCISE_STAGE_START.get(name)
        if concise_message:
            print("  " + concise_message)
        try:
            result = function()
            row["status"] = "ok"
            if concise_message:
                self._concise_stage_done(name, result)
            return result
        except KeyboardInterrupt:
            row["status"] = "interrupted"
            self._interrupted = True
            raise
        except Exception as exc:
            row["status"] = "warning"
            row["error"] = "%s: %s" % (type(exc).__name__, exc)
            self._log(name, "WARN", "%s -- continuing with the best measured tuple"
                      % row["error"])
            if not self._detailed_console():
                label = concise_message or (str(name).replace("_", " ").capitalize() + "...")
                print("  Warning: %s could not be completed; continuing with the best "
                      "measurement so far." % label.rstrip("."))
            return None
        finally:
            self.data["working"] = dict(self.working)
            # A long hardware run must survive a client crash or operator interrupt.
            # The pickle is the lossless checkpoint; HDF5/PNG are finalized by runner.
            try:
                self._checkpoint()
            except Exception as exc:
                self._log(name, "WARN", "checkpoint failed: %s" % exc)
                if not self._detailed_console():
                    print("  Warning: the intermediate checkpoint could not be saved.")

    # ---------------------------------------------------------- production backends
    def _acquire_transmission(self, freqs_mhz, candidate, shots):
        freqs = np.asarray(freqs_mhz, dtype=float)
        z = np.full(freqs.size, np.nan + 1j * np.nan)
        order = self.rng.permutation(freqs.size)
        for index in order:
            cfg = self._cfg_for(candidate, read_pulse_freq=float(freqs[index]),
                                shots=int(shots), reps=int(shots))
            program = BasicTransmissionProgram(self.soccfg, cfg)
            avgi, avgq = program.acquire(
                self.soc, load_pulses=True, progress=False)
            z[index] = _mean_from_qick(avgi) + 1j * _mean_from_qick(avgq)
        return z

    def _acquire_spectroscopy(self, freqs_mhz, candidate, shots, gain,
                              pulse_length_us):
        freqs = np.asarray(freqs_mhz, dtype=float)
        if freqs.size < 2:
            raise ValueError("spectroscopy needs at least two frequencies")
        step = float(freqs[1] - freqs[0])
        cfg = self._cfg_for(
            candidate, start=float(freqs[0]), step=step, expts=int(freqs.size),
            reps=int(shots), shots=int(shots), spec_gain=int(round(gain)),
            spec_len_us=float(pulse_length_us),
        )
        program = BasicSpecProgram(self.soccfg, cfg)
        _x, avgi, avgq = program.acquire(
            self.soc, load_pulses=True, progress=False)
        return (_curve_from_qick(avgi, freqs.size)
                + 1j * _curve_from_qick(avgq, freqs.size))

    def _acquire_iq_chevron(self, freqs_mhz, gains, candidate, shots):
        freqs, gains = np.asarray(freqs_mhz, float), np.asarray(gains, int)
        if gains.size < 2:
            raise ValueError("Rabi gain sweep needs at least two gains")
        steps = np.diff(gains)
        if not np.all(steps == steps[0]):
            raise ValueError("hardware Rabi sweep requires equally spaced integer gains")
        i_map = np.full((freqs.size, gains.size), np.nan)
        q_map = np.full_like(i_map, np.nan)
        if self._fast_gain_sweep is True:
            for row, freq in enumerate(freqs):
                cfg = self._cfg_for(
                    candidate, drive_freq=float(freq), start=int(gains[0]),
                    step=int(steps[0]), expts=int(gains.size), reps=int(shots),
                    shots=int(shots),
                )
                program = BasicRabiProgram(self.soccfg, cfg)
                _x, avgi, avgq = program.acquire(
                    self.soc, load_pulses=True, progress=False)
                i_map[row] = _curve_from_qick(avgi, gains.size)
                q_map[row] = _curve_from_qick(avgq, gains.size)
            return i_map, q_map

        # Packed/unknown generator: compile every amplitude into the pulse registers.
        # This costs uploads but cannot silently produce a flat fake gain sweep.
        jobs = [(fi, gi) for fi in range(freqs.size) for gi in range(gains.size)]
        for job_index in self.rng.permutation(len(jobs)):
            fi, gi = jobs[int(job_index)]
            cfg = self._cfg_for(
                candidate, drive_freq=float(freqs[fi]), start=int(gains[gi]),
                step=0, expts=1, reps=int(shots), shots=int(shots),
            )
            program = BasicRabiProgram(self.soccfg, cfg)
            _x, avgi, avgq = program.acquire(
                self.soc, load_pulses=True, progress=False)
            i_map[fi, gi] = _curve_from_qick(avgi, 1)[0]
            q_map[fi, gi] = _curve_from_qick(avgq, 1)[0]
        return i_map, q_map

    def _acquire_ss_pair(self, candidate, shots, state_order="ge"):
        # This is the production TLS step-5 program, not a lookalike sequence program.
        if self._fast_gain_sweep is not True:
            # SingleShotProgram obtains g/e by sweeping the qubit gain register.  On a
            # packed generator, two fixed compiled programs are the only safe physical
            # equivalent.  Return arrays in canonical [ground, excited] order.
            acquired = {}
            states = ("ground", "excited") if state_order == "ge" \
                else ("excited", "ground")
            for state in states:
                cfg = self._cfg_for(
                    candidate, drive_freq=float(candidate["qubit_pi_freq"]),
                    sequence_gain=(0 if state == "ground"
                                   else int(candidate["qubit_pi_gain"])),
                    # Match SingleShotProgram's gain-zero ground arm exactly: it still
                    # emits the zero-amplitude waveform and the same 10 ns post-pulse gap.
                    sequence_phases_deg=[0.0], shots=int(shots), reps=int(shots),
                )
                program = BasicSequenceProgram(self.soccfg, cfg)
                program.acquire(self.soc, load_pulses=True, progress=False)
                acquired[state] = _shots_from_program(program, cfg)
            return (acquired["ground"][0], acquired["ground"][1],
                    acquired["excited"][0], acquired["excited"][1])

        cfg = self._cfg_for(
            candidate, qubit_gain=int(candidate["qubit_pi_gain"]),
            qubit_pi_gain=int(candidate["qubit_pi_gain"]),
            qubit_pi_freq=float(candidate["qubit_pi_freq"]),
            shots=int(shots), repeats=1,
            single_shot_state_order=str(state_order),
        )
        program = SingleShotProgram(self.soccfg, cfg)
        shot_i, shot_q = program.acquire(
            self.soc, load_pulses=True, progress=False)
        shot_i, shot_q = np.asarray(shot_i, float), np.asarray(shot_q, float)
        if shot_i.ndim != 2 or shot_q.ndim != 2 \
                or shot_i.shape[0] < 2 or shot_q.shape[0] < 2:
            raise RuntimeError("SingleShotProgram did not return [ground, excited] shots")
        return shot_i[0], shot_q[0], shot_i[1], shot_q[1]

    def _acquire_sequence(self, candidate, sequence_ops, shots, seq_gap_us=None):
        """Acquire raw shots for an arbitrary g-e/e-f shelving sequence."""
        extra = {
            "drive_freq": float(candidate["qubit_pi_freq"]),
            "sequence_ops": list(sequence_ops),
            "shots": int(shots), "reps": int(shots),
            "leakage_reference_sigma_us": max(
                float(self.params["leakage"]["reference_sigma_us"]),
                float(candidate["sigma"])),
        }
        if seq_gap_us is not None:
            extra["seq_gap_us"] = float(seq_gap_us)
        cfg = self._cfg_for(candidate, **extra)
        program = BasicSequenceProgram(self.soccfg, cfg)
        program.acquire(self.soc, load_pulses=True, progress=False)
        return _shots_from_program(program, cfg)

    def _acquire_parity_chevron(self, freqs_mhz, gains, candidate, shots,
                                pulse_counts, calibration):
        """Return a joint odd/even parity score, using a fixed fresh discriminator."""
        freqs, gains = np.asarray(freqs_mhz, float), np.asarray(gains, int)
        if gains.size < 2 or not np.all(np.diff(gains) == np.diff(gains)[0]):
            raise ValueError("parity chevron requires an equally spaced gain axis")
        populations = np.full((len(pulse_counts), freqs.size, gains.size), np.nan)
        if self._fast_gain_sweep is not True:
            jobs = [(ci, fi, gi) for ci in range(len(pulse_counts))
                    for fi in range(freqs.size) for gi in range(gains.size)]
            for job_index in self.rng.permutation(len(jobs)):
                ci, fi, gi = jobs[int(job_index)]
                cfg = self._cfg_for(
                    candidate, drive_freq=float(freqs[fi]),
                    sequence_gain=int(gains[gi]),
                    sequence_phases_deg=[0.0] * int(pulse_counts[ci]),
                    shots=int(shots), reps=int(shots),
                )
                program = BasicSequenceProgram(self.soccfg, cfg)
                program.acquire(self.soc, load_pulses=True, progress=False)
                shot_i, shot_q = _shots_from_program(program, cfg)
                populations[ci, fi, gi] = float(np.mean(
                    discriminate_with_metrics(shot_i, shot_q, calibration)))
            targets = np.asarray(
                [1.0 if int(n) % 2 else 0.0 for n in pulse_counts])
            correctness = np.where(targets[:, None, None] > 0.5,
                                   populations, 1.0 - populations)
            return np.mean(correctness, axis=0), populations

        jobs = [(count_index, freq_index)
                for count_index in range(len(pulse_counts))
                for freq_index in range(freqs.size)]
        for job_number, job_index in enumerate(self.rng.permutation(len(jobs))):
            count_index, freq_index = jobs[int(job_index)]
            count, freq = pulse_counts[count_index], freqs[freq_index]
            run_gains = gains if job_number % 2 == 0 else gains[::-1]
            cfg = self._cfg_for(
                candidate, rabi_drive_freq=float(freq), n_pulses=int(count),
                amp_start=int(run_gains[0]),
                amp_step=int(np.diff(run_gains)[0]),
                amp_expts=int(gains.size), shots=int(shots), reps=int(shots),
                ff_hold_gain=0,
            )
            program = RabiSSProgram(self.soccfg, cfg)
            shot_i, shot_q = program.acquire(
                self.soc, load_pulses=True, progress=False)
            shot_i, shot_q = np.asarray(shot_i), np.asarray(shot_q)
            row = np.empty(gains.size, dtype=float)
            for gain_index in range(gains.size):
                row[gain_index] = float(
                    np.mean(discriminate_with_metrics(
                        shot_i[gain_index], shot_q[gain_index], calibration)))
            populations[count_index, freq_index] = (
                row if job_number % 2 == 0 else row[::-1])
        targets = np.asarray([1.0 if int(n) % 2 else 0.0 for n in pulse_counts])
        correctness = np.where(targets[:, None, None] > 0.5,
                               populations, 1.0 - populations)
        return np.mean(correctness, axis=0), populations

    def _acquire_inverse_pair_scan(self, freqs_mhz, candidate, shots, pairs,
                                   calibration):
        freqs = np.asarray(freqs_mhz, dtype=float)
        populations = np.full(freqs.size, np.nan)
        phases = [phase for _ in range(int(pairs)) for phase in (0.0, 180.0)]
        for index in self.rng.permutation(freqs.size):
            cfg = self._cfg_for(
                candidate, drive_freq=float(freqs[index]),
                sequence_gain=int(candidate["qubit_pi_gain"]),
                sequence_phases_deg=phases, shots=int(shots), reps=int(shots),
            )
            program = BasicSequenceProgram(self.soccfg, cfg)
            program.acquire(self.soc, load_pulses=True, progress=False)
            shot_i, shot_q = _shots_from_program(program, cfg)
            populations[index] = float(np.mean(
                discriminate_with_metrics(shot_i, shot_q, calibration)))
        return populations

    # ----------------------------------------------------------- direct SS objective
    def _measure_candidate(self, candidate, shots, label, state_order="ge",
                           archive=True, reference_discriminator=None):
        ig, qg, ie, qe = self._acquire_ss_pair(
            dict(candidate), int(shots), state_order=state_order)
        metrics = step5_metrics(ig, qg, ie, qe)
        row = dict(candidate)
        row.update({key: value for key, value in metrics.items()
                    if key != "confusion"})
        row["confusion"] = np.asarray(metrics["confusion"])
        if reference_discriminator is not None:
            ground_state = discriminate_with_metrics(
                ig, qg, reference_discriminator)
            excited_state = discriminate_with_metrics(
                ie, qe, reference_discriminator)
            p_e_given_g = float(np.mean(ground_state > 0))
            p_g_given_e = float(np.mean(excited_state < 1))
            row.update({
                "reference_fidelity": float(
                    1.0 - 0.5 * (p_e_given_g + p_g_given_e)),
                "reference_p_e_given_g": p_e_given_g,
                "reference_p_g_given_e": p_g_given_e,
            })
        row["label"] = str(label)
        row["state_order"] = str(state_order)
        row["measurement_index"] = len(self._archive)
        if archive:
            self._archive.append(row)
        return row

    @staticmethod
    def _aggregate(candidate, measurements, label):
        if not measurements:
            raise ValueError("cannot aggregate zero measurements")
        fids = np.asarray([row["fidelity"] for row in measurements], dtype=float)
        shot_ses = np.asarray([row["fidelity_se"] for row in measurements], dtype=float)
        mean = float(np.mean(fids))
        if fids.size > 1:
            between = float(np.std(fids, ddof=1) / np.sqrt(fids.size))
        else:
            between = 0.0
        within = float(np.sqrt(np.sum(shot_ses ** 2)) / fids.size)
        se = float(max(between, within))
        out = dict(candidate)
        out.update({
            "fidelity": mean, "fidelity_se": se,
            "fidelity_lcb_95": float(mean - 1.96 * se),
            "confirmation_blocks": int(fids.size),
            "block_fidelities": fids,
            "block_spread": float(np.ptp(fids)) if fids.size else np.inf,
            "label": str(label),
            "measurement_indices": [int(row["measurement_index"])
                                    for row in measurements],
            "sep_sigma": float(np.mean([row["sep_sigma"] for row in measurements])),
            # Multiple blocks are a family of fresh anomaly checks.  Preserve the
            # worst upper bound so a transient third cloud cannot be averaged away.
            "third_blob_excess_ucb": float(max(
                row.get("third_blob_excess_ucb_95", np.inf)
                for row in measurements)),
        })
        return out

    def _confirm_candidates(self, candidates, shots, blocks, label,
                            add_to_history=True):
        candidates = _unique_candidates(candidates)
        if not candidates:
            raise ValueError("cannot confirm an empty candidate list")
        requested_blocks = max(int(blocks), 1)
        buckets = [[] for _ in candidates]
        failures = []
        # Round-robin, randomized candidate order prevents one candidate from owning a
        # uniquely favorable drift window.  GE/EG order alternates between blocks.  A
        # transient failure is isolated to that candidate/block: successful contenders
        # remain available to this stage and to the final replay.
        for block in range(requested_blocks):
            for index in self.rng.permutation(len(candidates)):
                try:
                    row = self._measure_candidate(
                        candidates[index], shots,
                        "%s block %d" % (label, block + 1),
                        state_order="ge" if block % 2 == 0 else "eg")
                    buckets[index].append(row)
                except KeyboardInterrupt:
                    raise
                except Exception as exc:
                    failure = {
                        "label": str(label), "candidate_index": int(index),
                        "block": int(block + 1),
                        "error": "%s: %s" % (type(exc).__name__, exc),
                    }
                    failures.append(failure)
                    self.data["confirmation_failures"].append(failure)
        batch_complete = bool(
            not failures and all(len(rows) == requested_blocks for rows in buckets))
        aggregates = []
        for candidate, rows in zip(candidates, buckets):
            key = _candidate_key(candidate)
            existing = next((entry for entry in self._unconfirmed_contenders
                             if _candidate_key(entry["candidate"]) == key), None)
            if not batch_complete:
                entry = {
                    "candidate": {name: candidate[name] for name in self.initial},
                    "missing_blocks": int(requested_blocks - len(rows)),
                    "completed_blocks": int(len(rows)),
                    "scheduled_blocks": int(requested_blocks),
                    "batch_incomplete": True,
                    "label": str(label),
                    "order": int(len(self.data["confirmation_failures"])),
                }
                if existing is None:
                    self._unconfirmed_contenders.append(entry)
                elif entry["missing_blocks"] >= existing["missing_blocks"]:
                    existing.update(entry)
            elif existing is not None:
                self._unconfirmed_contenders.remove(existing)
            if not rows:
                continue
            aggregate = self._aggregate(candidate, rows, label)
            aggregate.update({
                "scheduled_confirmation_blocks": requested_blocks,
                "completed_confirmation_blocks": len(rows),
                "missing_confirmation_blocks": requested_blocks - len(rows),
                "confirmation_complete": bool(len(rows) == requested_blocks),
                "confirmation_batch_complete": batch_complete,
                "confirmation_failure_count": len(failures),
            })
            aggregates.append(aggregate)
        limit = max(int(self.params["final"].get(
            "max_unconfirmed_contenders", 16)), 1)
        # Fully failed tuples sort ahead of partially measured ones.  Preserve earlier
        # discovery order within a priority class so a later storm of backend faults
        # cannot continually evict the first unresolved spectral basins.
        self._unconfirmed_contenders[:] = sorted(
            self._unconfirmed_contenders,
            key=lambda entry: (-int(entry["missing_blocks"]), int(entry["order"])),
        )[:limit]
        if failures:
            self._log(
                "confirmation", "WARN",
                "%s retained %d/%d successful candidate-block measurements; "
                "the batch remains usable for best-effort reporting but is not "
                "calibration evidence"
                % (label, sum(len(rows) for rows in buckets),
                   len(candidates) * requested_blocks))
        if not aggregates:
            raise RuntimeError("%s completed no confirmation measurements" % label)
        if add_to_history:
            self._confirmed.extend(aggregates)
        return aggregates

    @staticmethod
    def _confirmation_batch_complete(aggregates):
        return bool(aggregates and all(
            row.get("confirmation_batch_complete", False) for row in aggregates))

    @staticmethod
    def _best_aggregate(rows):
        if not rows:
            return None
        return max(rows, key=lambda row: (
            float(row.get("fidelity_lcb_95", -np.inf)),
            float(row.get("fidelity", -np.inf)),
            -float(row.get("read_length", np.inf)),
        ))

    @staticmethod
    def _noninferior_seed(aggregates, seed, incumbent, margin=0.005):
        by_key = {_candidate_key(row): row for row in aggregates}
        seed_row = by_key.get(_candidate_key(seed))
        incumbent_row = by_key.get(_candidate_key(incumbent))
        if seed_row is None:
            return BasicAutoTuner._best_aggregate(aggregates)
        if incumbent_row is None:
            return seed_row
        floor = (float(incumbent_row["fidelity"])
                 - 1.96 * float(incumbent_row["fidelity_se"]) - float(margin))
        if float(seed_row["fidelity_lcb_95"]) >= floor:
            return seed_row
        return BasicAutoTuner._best_aggregate(aggregates)

    @staticmethod
    def _prefer_lower_readout_exposure(aggregates, margin=0.003,
                                       max_mean_loss=0.010):
        """Prefer lower readout gain-squared x duration inside a fidelity tie."""
        if not aggregates:
            return None
        best = BasicAutoTuner._best_aggregate(aggregates)
        tied = []
        for row in aggregates:
            uncertainty = 1.96 * math.hypot(
                float(best.get("fidelity_se", np.inf)),
                float(row.get("fidelity_se", np.inf)))
            loss = float(best["fidelity"]) - float(row["fidelity"])
            if (loss <= uncertainty + float(margin)
                    and loss <= float(max_mean_loss)):
                tied.append(row)
        return min(tied or [best], key=lambda row: (
            float(row.get("read_pulse_gain", np.inf)) ** 2
            * float(row.get("read_length", np.inf)),
            float(row.get("read_length", np.inf)),
            -float(row.get("fidelity_lcb_95", -np.inf))))

    @staticmethod
    def _calibration_drift(before, after):
        angle = float(np.angle(np.exp(1j * (
            float(after["read_theta"]) - float(before["read_theta"])))))
        theta = float(before["read_theta"])
        factor = float(before["scale_factor"])

        def project(row, state):
            center = complex(float(row["%s_center_i" % state]),
                             float(row["%s_center_q" % state]))
            return float(factor * np.real(np.exp(-1j * theta) * center))

        pre_g = project(before, "ground")
        pre_e = project(before, "excited")
        post_g = project(after, "ground")
        post_e = project(after, "excited")
        separation = max(abs(pre_e - pre_g), 1e-12)
        midpoint_shift_fraction = abs(
            0.5 * (post_g + post_e) - 0.5 * (pre_g + pre_e)) / separation
        reference_fidelity = float(after.get("reference_fidelity", np.nan))
        return {
            "angle_degrees": float(abs(np.degrees(angle))),
            "fidelity_change": float(after["fidelity"] - before["fidelity"]),
            "fixed_discriminator_fidelity": reference_fidelity,
            "fixed_discriminator_fidelity_loss": float(
                before["fidelity"] - reference_fidelity),
            "midpoint_shift_fraction": float(midpoint_shift_fraction),
            "separation_change_fraction": float(
                ((post_e - post_g) - (pre_e - pre_g)) / separation),
        }

    def _calibration_is_stable(self, drift):
        limits = self.params["calibration_drift"]
        return bool(
            np.isfinite(drift["fixed_discriminator_fidelity"])
            and float(drift["angle_degrees"])
            <= float(limits["max_angle_degrees"])
            and abs(float(drift["fidelity_change"]))
            <= float(limits["max_independent_fidelity_change"])
            and float(drift["fixed_discriminator_fidelity_loss"])
            <= float(limits["max_fixed_discriminator_fidelity_loss"])
            and float(drift["midpoint_shift_fraction"])
            <= float(limits["max_midpoint_shift_fraction"]))

    def _require_stable_calibration(self, drift, stage):
        if not self._calibration_is_stable(drift):
            raise RuntimeError(
                "%s discriminator drifted during its map (angle %.1f deg, "
                "independent dF %+.3f, fixed-discriminator loss %+.3f, "
                "midpoint shift %.2f separation)"
                % (stage, drift["angle_degrees"], drift["fidelity_change"],
                   drift["fixed_discriminator_fidelity_loss"],
                   drift["midpoint_shift_fraction"]))

    def _adopt(self, aggregate, stage):
        if aggregate is None:
            return
        self.working = {key: aggregate[key] for key in self.initial}
        self._log(stage, "OK",
                  "selected read %.6f/%d/%.1fus | pi %.6f @ %d / %.1fns; "
                  "step-5 F=%.4f +/- %.4f"
                  % (self.working["read_pulse_freq"],
                     self.working["read_pulse_gain"], self.working["read_length"],
                     self.working["qubit_pi_freq"], self.working["qubit_pi_gain"],
                     4000.0 * self.working["sigma"], aggregate["fidelity"],
                     aggregate["fidelity_se"]))

    def _record_key_evidence(self, keys, stage, complete):
        for key in keys:
            self._key_evidence[key].append({
                "value": self.working[key], "stage": str(stage),
                "complete": bool(complete),
            })

    def _key_has_evidence(self, key, value):
        for row in reversed(self._key_evidence.get(key, [])):
            measured = row.get("value")
            try:
                matches = (int(measured) == int(value) if key.endswith("gain")
                           else math.isclose(float(measured), float(value),
                                             rel_tol=0.0, abs_tol=1e-9))
            except Exception:
                matches = measured == value
            if matches:
                return bool(row.get("complete", False))
        return False

    @staticmethod
    def _tuned_values_match(key, first, second):
        """Compare two persisted calibration values without gain truncation leaks."""
        try:
            if key.endswith("gain"):
                return int(round(float(first))) == int(round(float(second)))
            return math.isclose(float(first), float(second),
                                rel_tol=0.0, abs_tol=1e-9)
        except (TypeError, ValueError, OverflowError):
            return first == second

    def _input_tuned_value(self, key):
        """Return the value that would remain if the runner did not write ``key``."""
        return self.input_cfg.get(key, self.initial[key])

    # --------------------------------------------------------------- map utilities
    @staticmethod
    def _integer_axis(start, stop, points, lower=0, upper=32767):
        start = int(np.clip(round(start), lower, upper))
        stop = int(np.clip(round(stop), lower, upper))
        if stop < start:
            start, stop = stop, start
        points = max(int(points), 2)
        step = max(int(round((stop - start) / float(points - 1))), 1)
        axis = start + step * np.arange(points, dtype=int)
        axis = axis[(axis <= upper) & (axis <= stop)]
        if axis.size < 2:
            axis = np.array([max(lower, start - 1), min(upper, start + 1)], dtype=int)
        return axis

    @staticmethod
    def _float_axis(center, span, points, include=()):
        axis = np.linspace(float(center) - float(span) / 2.0,
                           float(center) + float(span) / 2.0, int(points))
        for value in include:
            if np.isfinite(value):
                axis[int(np.argmin(np.abs(axis - float(value))))] = float(value)
        return np.sort(np.unique(axis))

    @staticmethod
    def _gain_axis(start, stop, points, include=()):
        axis = np.rint(np.linspace(float(start), float(stop), int(points))).astype(int)
        axis = np.clip(axis, 0, 32767)
        for value in include:
            if np.isfinite(value):
                axis[int(np.argmin(np.abs(axis - int(round(value)))))] = int(
                    np.clip(round(value), 0, 32767))
        return np.sort(np.unique(axis))

    def _direct_grid(self, stage, candidates, shape, axes, shots, shortlist,
                     confirm_shots, confirm_blocks):
        candidates = [dict(candidate) for candidate in candidates]
        if int(np.prod(shape)) != len(candidates):
            raise ValueError("candidate list does not match grid shape")
        score = np.full(len(candidates), np.nan)
        score_se = np.full(len(candidates), np.nan)
        third_blob_ucb = np.full(len(candidates), np.nan)
        order = self.rng.permutation(len(candidates))
        failures = 0
        consecutive_failures = 0
        aborted = False
        cache = {}
        self._log(stage, "OK", "%d-point direct step-5 grid (%d shots/state)"
                  % (len(candidates), int(shots)))
        progress_step = max(len(candidates) // 10, 1)
        for count, index in enumerate(order):
            key = _candidate_key(candidates[index])
            if key in cache:
                score[index], score_se[index], third_blob_ucb[index] = cache[key]
                consecutive_failures = 0
                continue
            try:
                measured = self._measure_candidate(
                    candidates[index], int(shots), "%s coarse" % stage,
                    state_order="ge" if count % 2 == 0 else "eg")
                score[index] = measured["fidelity"]
                score_se[index] = measured["fidelity_se"]
                third_blob_ucb[index] = measured["third_blob_excess_ucb_95"]
                cache[key] = (
                    score[index], score_se[index], third_blob_ucb[index])
                consecutive_failures = 0
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                failures += 1
                consecutive_failures += 1
                self._log(stage, "WARN", "grid point %d/%d failed (%s: %s)"
                          % (count + 1, len(candidates), type(exc).__name__, exc))
                if consecutive_failures >= int(self.params.get(
                        "max_consecutive_point_failures", 5)):
                    self._log(stage, "WARN",
                              "%d consecutive backend failures; stopping this grid"
                              % consecutive_failures)
                    aborted = True
                    break
            if (self._detailed_console()
                    and ((count + 1) % progress_step == 0
                         or count + 1 == len(candidates))):
                print("      %s progress: %d/%d" % (stage, count + 1, len(candidates)))
        if not np.any(np.isfinite(score)):
            raise RuntimeError("every direct single-shot grid point failed")
        coverage = float(np.count_nonzero(np.isfinite(score)) / max(len(score), 1))
        selection_usable = bool(not aborted and coverage >= 0.80)
        # A partially measured map may still nominate useful candidates for fresh
        # confirmation, but it is never complete evidence for an automatic write.
        search_complete = bool(not aborted and coverage >= 1.0 - 1e-12)
        self._maps[stage] = {
            "axes": {key: np.asarray(value) for key, value in axes.items()},
            "fidelity": score.reshape(shape),
            "fidelity_se": score_se.reshape(shape),
            "third_blob_excess_ucb": third_blob_ucb.reshape(shape),
            "failed_points": int(failures),
            "coverage": coverage, "aborted": bool(aborted),
            "selection_coverage_usable": selection_usable,
            "search_complete": search_complete, "selection_confirmed": False,
        }
        if not selection_usable:
            raise RuntimeError(
                "%s grid incomplete (%.1f%% finite coverage); partial points archived"
                % (stage, 100.0 * coverage))
        if not search_complete:
            self._log(
                stage, "WARN",
                "%.1f%% map coverage is enough to confirm/report candidates, but only "
                "100%% coverage counts as independent coordinate-search evidence; "
                "a stable exact final tuple replay can still authorize the winner"
                % (100.0 * coverage))
        finite = np.flatnonzero(np.isfinite(score))
        guarded = finite
        if self._operational_leakage_active or self._leakage_active:
            threshold = float(self.params["leakage"]["max_third_blob_excess"])
            safe = finite[np.isfinite(third_blob_ucb[finite])
                          & (third_blob_ucb[finite] <= threshold)]
            if safe.size:
                guarded = safe
        ranked = guarded[np.argsort(score[guarded])[::-1]]
        selected = [candidates[int(index)]
                    for index in ranked[:max(int(shortlist), 1)]]
        # The current incumbent is freshly remeasured beside the grid winners.  Thus a
        # noisy maximum can never silently replace a genuinely better manual tuple.
        incumbent = dict(self.working)
        selected.append(incumbent)
        confirmed = self._confirm_candidates(
            selected, int(confirm_shots), int(confirm_blocks), "%s confirm" % stage)
        confirmation_complete = self._confirmation_batch_complete(confirmed)
        self._maps[stage]["selection_confirmation_complete"] = bool(
            confirmation_complete)
        if not confirmation_complete:
            self._maps[stage]["search_complete"] = False
        guarded_confirmed = list(confirmed)
        if self._operational_leakage_active or self._leakage_active:
            threshold = float(self.params["leakage"]["max_third_blob_excess"])
            safe_confirmed = [row for row in confirmed
                              if float(row.get(
                                  "third_blob_excess_ucb", np.inf)) <= threshold]
            if safe_confirmed:
                guarded_confirmed = safe_confirmed
        direct_best = self._best_aggregate(guarded_confirmed)
        # When held-out evidence cannot distinguish the incumbent from the apparent
        # winner, keep the incumbent.  This prevents a flat bootstrap map from turning
        # a coherent Rabi/readout seed into an arbitrary noise-selected tuple.
        if str(stage).startswith("readout"):
            best = self._prefer_lower_readout_exposure(
                guarded_confirmed, margin=0.003,
                max_mean_loss=self.params["readout"].get(
                    "max_tie_fidelity_loss", 0.010))
        else:
            best = self._noninferior_seed(
                guarded_confirmed, incumbent, direct_best, margin=0.003)
        self._adopt(best, stage)
        self._maps[stage]["selection_confirmed"] = True
        return best

    @staticmethod
    def _smooth_trace(values):
        values = np.asarray(values, dtype=float)
        n = values.size
        if n < 5:
            return values.copy()
        # Keep the kernel deliberately short.  A 15-point kernel erased a narrow
        # resonator in coarse scans and moved the apparent dip by multiple linewidths.
        window = 5
        return savgol_filter(values, window_length=window, polyorder=2, mode="interp")

    @staticmethod
    def _parabolic_vertex(x, y, index):
        if index <= 0 or index >= len(x) - 1:
            return float(x[index])
        xx = np.asarray(x[index - 1:index + 2], float)
        yy = np.asarray(y[index - 1:index + 2], float)
        try:
            a, b, _ = np.polyfit(xx, yy, 2)
            vertex = -b / (2.0 * a)
            if a != 0 and xx[0] <= vertex <= xx[-1]:
                return float(vertex)
        except Exception:
            pass
        return float(x[index])

    @staticmethod
    def _spectral_features(freqs, response, max_candidates=3):
        freqs = np.asarray(freqs, float)
        z = np.asarray(response, complex)
        n = freqs.size
        if n < 9 or z.size != n:
            raise ValueError("invalid spectroscopy trace")
        # A wide Savitzky-Golay curve models slow gain/phase drift.  Spectral lines are
        # ranked by complex distance from that local baseline, independent of whether
        # they appear as a dip, peak, or phase rotation.
        window = min(n if n % 2 else n - 1, max(11, 2 * (n // 8) + 1))
        if window % 2 == 0:
            window -= 1
        if window < 7:
            baseline = np.linspace(z[0], z[-1], n)
        else:
            baseline = (savgol_filter(z.real, window, 2, mode="interp")
                        + 1j * savgol_filter(z.imag, window, 2, mode="interp"))
        residual = np.abs(z - baseline)
        noise = max(_robust_scale(residual), 1e-15)
        floor = float(np.median(residual))
        snr_trace = (residual - floor) / noise
        distance = max(1, n // 40)
        peaks, properties = find_peaks(snr_trace, distance=distance, prominence=1.0)
        if not peaks.size:
            peaks = np.array([int(np.nanargmax(snr_trace))])
            prominences = snr_trace[peaks]
        else:
            prominences = properties.get("prominences", snr_trace[peaks])
        order = peaks[np.argsort(prominences)[::-1]]
        chosen = [int(index) for index in order[:max(int(max_candidates), 1)]]
        return {
            "candidates_mhz": [float(freqs[index]) for index in chosen],
            "candidate_indices": chosen,
            "best_snr": float(np.nanmax(snr_trace)),
            "residual": residual,
            "snr_trace": snr_trace,
            "baseline": baseline,
        }

    @staticmethod
    def _reproduced_spectral_seed(freqs, combined, individual, max_error_mhz,
                                  min_combined_snr):
        """Associate one significant spectral feature across two opposed passes.

        A scan can contain several real or weak spurious features.  Requiring the
        *strongest* feature in pass one to also be strongest in pass two is not a
        reproducibility test: harmless rank swapping then looks like a disappearing
        line.  Match all retained local peaks, require a close pair and significant
        combined evidence, and choose the pair with the strongest weaker pass.
        """
        freqs = np.asarray(freqs, dtype=float)
        if freqs.size == 0 or len(individual) != 2:
            raise RuntimeError("opposed spectroscopy passes are incomplete")
        maximum_error = float(max_error_mhz)
        minimum_combined = float(min_combined_snr)
        minimum_individual = max(1.5, 0.5 * minimum_combined)
        matches = []
        for left_position, left_frequency in enumerate(
                individual[0].get("candidates_mhz", [])):
            left_indices = individual[0].get("candidate_indices", [])
            if left_position >= len(left_indices):
                continue
            left_index = int(left_indices[left_position])
            left_snr = float(individual[0]["snr_trace"][left_index])
            for right_position, right_frequency in enumerate(
                    individual[1].get("candidates_mhz", [])):
                right_indices = individual[1].get("candidate_indices", [])
                if right_position >= len(right_indices):
                    continue
                separation = abs(float(left_frequency) - float(right_frequency))
                if separation > maximum_error:
                    continue
                right_index = int(right_indices[right_position])
                right_snr = float(individual[1]["snr_trace"][right_index])
                centre = 0.5 * (float(left_frequency) + float(right_frequency))
                combined_index = int(np.argmin(np.abs(freqs - centre)))
                combined_snr = float(combined["snr_trace"][combined_index])
                if (not np.all(np.isfinite(
                        [left_snr, right_snr, combined_snr]))
                        or min(left_snr, right_snr) < minimum_individual
                        or combined_snr < minimum_combined):
                    continue
                matches.append({
                    "frequency_mhz": float(centre),
                    "pass_centres_mhz": (
                        float(left_frequency), float(right_frequency)),
                    "pass_snr": (left_snr, right_snr),
                    "combined_snr": combined_snr,
                    "separation_mhz": float(separation),
                })
        if not matches:
            raise RuntimeError(
                "no significant spectral feature reproduced in opposed passes")
        return max(matches, key=lambda row: (
            min(row["pass_snr"]), row["combined_snr"],
            -row["separation_mhz"]))

    def _inverse_pair_map(self, stage, incumbent, params, center_frequency):
        """Acquire one drift-bracketed inverse-pair frequency map.

        The returned ``data_complete`` flag is deliberately stricter than merely
        finding a finite minimum.  A map with one missing point may still nominate a
        candidate for direct replay, but it cannot provide independent coordinate-
        search evidence.  A later stable exact replay of the complete tuple remains
        sufficient for an atomic update.
        """
        calibration_row = self._measure_candidate(
            incumbent, params["calibration_shots"],
            "%s discriminator" % stage)
        calibration = {key: calibration_row[key] for key in
                       ("read_theta", "scale_factor", "threshold")}
        freqs = self._float_axis(
            center_frequency, params["span_mhz"], params["points"],
            include=[center_frequency, incumbent["qubit_pi_freq"]])
        populations = self._acquire_inverse_pair_scan(
            freqs, incumbent, params["shots"], params["pairs"], calibration)
        post_calibration = self._measure_candidate(
            incumbent, params["calibration_shots"],
            "%s discriminator post" % stage,
            reference_discriminator=calibration)
        drift = self._calibration_drift(calibration_row, post_calibration)
        drift_stable = self._calibration_is_stable(drift)
        finite = np.isfinite(populations)
        coverage = float(np.count_nonzero(finite) / max(populations.size, 1))
        self._maps[stage] = {
            "axes": {"qubit_frequency_mhz": freqs},
            "residual_excited_population": populations,
            "pairs": int(params["pairs"]),
            "calibration_drift": drift,
            "calibration_stable": drift_stable,
            "coverage": coverage,
            "data_complete": bool(np.all(finite)),
            "search_complete": False,
            "selection_confirmed": False,
        }
        self._require_stable_calibration(drift, stage)
        if not np.any(finite):
            raise RuntimeError("inverse-pair frequency scan returned no finite data")
        # Searching many frequencies turns an ordinary largest/smallest binomial
        # fluctuation into an apparently structured range.  A 3-sigma pointwise rule
        # is therefore not a valid post-selection information test.  Use the measured
        # two-point uncertainty with a conservative 5-sigma default before allowing
        # the inverse-pair minimum to move or authorize the drive frequency.
        low_index = int(np.nanargmin(populations))
        high_index = int(np.nanargmax(populations))
        shot_count = max(int(params["shots"]), 1)
        point_variance = populations * (1.0 - populations) / shot_count
        point_variance = np.maximum(
            point_variance, 0.25 / float(shot_count + 1) ** 2)
        contrast = float(populations[high_index] - populations[low_index])
        contrast_se = float(math.hypot(
            math.sqrt(float(point_variance[low_index])),
            math.sqrt(float(point_variance[high_index]))))
        contrast_sigma = contrast / max(contrast_se, 1e-12)
        informative = bool(
            np.all(finite) and np.isfinite(contrast_sigma)
            and contrast_sigma >= float(params.get("min_contrast_sigma", 5.0)))
        self._maps[stage].update({
            "map_contrast": contrast,
            "map_contrast_se": contrast_se,
            "map_contrast_sigma": contrast_sigma,
            "information_complete": informative,
        })
        if not informative:
            self._maps[stage]["search_complete"] = False
            raise RuntimeError(
                "inverse-pair frequency response has insufficient post-selection "
                "information (contrast %.2f sigma, require %.2f)"
                % (contrast_sigma,
                   float(params.get("min_contrast_sigma", 5.0))))
        index = low_index
        frequency = self._parabolic_vertex(freqs, populations, index)
        seed = _with_candidate(incumbent, qubit_pi_freq=float(frequency))
        return {
            "stage": stage, "frequencies": freqs,
            "populations": populations, "index": index, "seed": seed,
            "data_complete": bool(np.all(finite)),
        }

    def _parity_map(self, stage, incumbent, params, center_frequency,
                    center_gain, calibration_shots, discriminator_label):
        """Acquire one drift-bracketed odd/even parity map."""
        calibration_row = self._measure_candidate(
            incumbent, int(calibration_shots),
            "%s discriminator" % discriminator_label)
        calibration = {key: calibration_row[key] for key in
                       ("read_theta", "scale_factor", "threshold")}
        freqs = self._float_axis(
            center_frequency, params["freq_span_mhz"], params["freq_points"],
            include=[center_frequency, incumbent["qubit_pi_freq"]])
        fraction = float(params["gain_fraction"])
        gains = self._integer_axis(
            float(center_gain) * (1.0 - fraction),
            float(center_gain) * (1.0 + fraction), params["gain_points"])
        score, populations = self._acquire_parity_chevron(
            freqs, gains, incumbent, params["shots"], params["pulse_counts"],
            calibration)
        post_calibration = self._measure_candidate(
            incumbent, int(calibration_shots),
            "%s discriminator post" % discriminator_label,
            reference_discriminator=calibration)
        drift = self._calibration_drift(calibration_row, post_calibration)
        drift_stable = self._calibration_is_stable(drift)
        finite = np.isfinite(score)
        coverage = float(np.count_nonzero(finite) / max(score.size, 1))
        self._maps[stage] = {
            "axes": {"qubit_frequency_mhz": freqs,
                     "qubit_gain_dac": gains,
                     "pulse_count": np.asarray(params["pulse_counts"], int)},
            "parity_score": score, "excited_populations": populations,
            "calibration_drift": drift,
            "calibration_stable": drift_stable,
            "coverage": coverage,
            "data_complete": bool(np.all(finite)),
            "search_complete": False,
            "selection_confirmed": False,
        }
        self._require_stable_calibration(drift, discriminator_label)
        if not np.any(finite):
            raise RuntimeError("%s returned no finite parity score" % stage)
        index = np.unravel_index(int(np.nanargmax(score)), score.shape)
        # A flat repeated-pulse surface contains no amplitude/frequency information.
        # Its numerical argmax is merely the largest shot-noise fluctuation, and the
        # direct one-pulse replay is intentionally too insensitive to reject a small
        # coherent miscalibration.  Require both a multiple-comparison-resistant map
        # contrast and agreement across the independently amplified pulse depths before
        # the raw optimum may move the control tuple or become write evidence.
        targets = np.asarray(
            [1.0 if int(count) % 2 else 0.0
             for count in params["pulse_counts"]], dtype=float)
        correctness = np.where(
            targets[:, None, None] > 0.5, populations, 1.0 - populations)
        depth_count = max(correctness.shape[0], 1)
        shot_count = max(int(params["shots"]), 1)
        depth_variance = correctness * (1.0 - correctness) / shot_count
        # Avoid zero nominal uncertainty when finite shots happen to observe no errors.
        depth_variance = np.maximum(
            depth_variance, 0.25 / float(shot_count + 1) ** 2)
        cell_se = np.sqrt(np.nansum(depth_variance, axis=0)) / depth_count
        low_index = np.unravel_index(int(np.nanargmin(score)), score.shape)
        contrast = float(score[index] - score[low_index])
        contrast_se = float(math.hypot(
            float(cell_se[index]), float(cell_se[low_index])))
        contrast_sigma = contrast / max(contrast_se, 1e-12)
        winning_depths = np.asarray(correctness[(slice(None),) + index], float)
        depth_median = float(np.nanmedian(winning_depths))
        depth_consistent_fraction = float(np.mean(winning_depths > 0.5))
        informative = bool(
            np.isfinite(contrast_sigma)
            and contrast_sigma >= float(params.get("min_contrast_sigma", 5.0))
            and depth_median >= float(params.get("min_depth_correctness", 0.55))
            and depth_consistent_fraction >= float(params.get(
                "min_consistent_depth_fraction", 0.67)))
        self._maps[stage].update({
            "map_contrast": contrast,
            "map_contrast_se": contrast_se,
            "map_contrast_sigma": contrast_sigma,
            "winning_depth_correctness": winning_depths,
            "winning_depth_median": depth_median,
            "winning_depth_consistent_fraction": depth_consistent_fraction,
            "information_complete": informative,
        })
        if not informative:
            self._maps[stage]["search_complete"] = False
            raise RuntimeError(
                "%s has insufficient repeated-pulse information "
                "(contrast %.2f sigma, median depth correctness %.3f, "
                "consistent depths %.0f%%)"
                % (stage, contrast_sigma, depth_median,
                   100.0 * depth_consistent_fraction))
        seed = _with_candidate(
            incumbent, qubit_pi_freq=float(freqs[index[0]]),
            qubit_pi_gain=int(gains[index[1]]))
        return {
            "stage": stage, "frequencies": freqs, "gains": gains,
            "score": score, "populations": populations,
            "index": index, "seed": seed,
            "data_complete": bool(np.all(finite)),
        }

    # --------------------------------------------------------------------- stages
    def _stage_baseline(self):
        p = self.params["baseline"]
        rows = self._confirm_candidates(
            [self.initial], p["shots"], p["blocks"], "exact input tuple")
        best = rows[0]
        self._adopt(best, "baseline")
        self._log("baseline", "OK",
                  "exact step-5 replay measured; low fidelity does not gate the search")
        return best

    def _stage_resonator(self):
        p = self.params["resonator"]
        if not p.get("enabled", True):
            self._log("resonator", "SKIP", "disabled")
            return None
        def run(span, points, readout):
            axis = self._float_axis(
                self.initial["read_pulse_freq"], span, points,
                include=[self.initial["read_pulse_freq"]])
            response = self._acquire_transmission(axis, readout, p["shots"])
            amplitude = np.abs(response)
            smooth = self._smooth_trace(amplitude)
            if str(p.get("polarity", "dip")).lower() == "peak":
                idx = int(np.nanargmax(smooth))
                fit = -smooth
            else:
                idx = int(np.nanargmin(smooth))
                fit = smooth
            noise = max(_robust_scale(amplitude - smooth), 1e-15)
            snr = float(np.ptp(smooth) / noise)
            return axis, response, amplitude, smooth, idx, fit, snr

        safe = _with_candidate(
            self.working,
            read_pulse_gain=int(np.clip(round(p.get(
                "discovery_gain", self.working["read_pulse_gain"])), 1, 32767)),
            read_length=max(float(p.get(
                "discovery_length_us", self.working["read_length"])), 0.1),
        )
        # Safe bootstrap wins exact ties; normalized contrast SNR can be identical at
        # two gains even though the near-zero input trace has unusably small absolute IQ.
        trial_candidates = _unique_candidates([safe, self.working])
        trials = []
        for trial in trial_candidates:
            try:
                result = run(p["span_mhz"], p["points"], trial)
                trials.append((float(result[-1]), trial, result))
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                self._log(
                    "resonator", "WARN",
                    "bootstrap readout %d DAC/%.1f us failed (%s: %s)"
                    % (trial["read_pulse_gain"], trial["read_length"],
                       type(exc).__name__, exc))
        if not trials:
            raise RuntimeError("all resonator bootstrap settings failed")
        _, discovery, local_result = max(trials, key=lambda row: row[0])
        freqs, z, mag, smoothed, index, fit_values, snr = local_result
        local_seed = self._parabolic_vertex(freqs, fit_values, index)
        used_wide = bool(p.get("always_wide", True)
                         or index <= 1 or index >= freqs.size - 2
                         or snr < float(p.get("min_contrast_snr", 3.0)))
        if used_wide:
            self._log("resonator",
                      "OK" if p.get("always_wide", True) else "WARN",
                      "checking the full %.1f MHz span with bootstrap readout %d DAC/%.1f us"
                      % (p["wide_span_mhz"], discovery["read_pulse_gain"],
                         discovery["read_length"]))
            wide_result = run(
                p["wide_span_mhz"], p["wide_points"], discovery)
            wide_freqs, wide_z, wide_mag, wide_smoothed, wide_index, \
                wide_fit_values, wide_snr = wide_result
            wide_seed = self._parabolic_vertex(
                wide_freqs, wide_fit_values, wide_index)
            # Prefer the finer local estimate only when the wide scan independently
            # places the same response inside that local basin.
            local_step = abs(float(np.median(np.diff(freqs))))
            if abs(local_seed - wide_seed) <= max(2.0 * local_step, 0.15):
                seed = local_seed
            else:
                seed = wide_seed
                freqs, z, mag, smoothed, index, fit_values, snr = wide_result
        else:
            seed = local_seed
        self._resonator_seed = seed
        self._discovery_readout = _with_candidate(
            discovery, read_pulse_freq=float(seed))
        self._maps["resonator"] = {
            "axes": {"read_frequency_mhz": freqs},
            "magnitude": mag, "smoothed_magnitude": smoothed,
            "complex_response": z, "contrast_snr": snr,
            "used_wide_scan": bool(used_wide),
            "bootstrap_gain_dac": int(discovery["read_pulse_gain"]),
            "bootstrap_length_us": float(discovery["read_length"]),
            "trial_gain_dac": np.asarray(
                [row[1]["read_pulse_gain"] for row in trials], dtype=int),
            "trial_length_us": np.asarray(
                [row[1]["read_length"] for row in trials], dtype=float),
            "trial_contrast_snr": np.asarray(
                [row[0] for row in trials], dtype=float),
        }
        if used_wide:
            self._maps["resonator"].update({
                "wide_frequency_mhz": wide_freqs,
                "wide_magnitude": wide_mag,
                "wide_smoothed_magnitude": wide_smoothed,
                "wide_complex_response": wide_z,
                "wide_contrast_snr": float(wide_snr),
            })
        self._log("resonator", "OK",
                  "response seed %.6f MHz using %d DAC/%.1f us (direct SS still decides)"
                  % (seed, discovery["read_pulse_gain"], discovery["read_length"]))
        return seed

    def _stage_spectroscopy(self):
        p = self.params["spectroscopy"]
        if not p.get("enabled", True):
            self._log("spectroscopy", "SKIP", "disabled")
            return None
        prior = float(self.initial["qubit_pi_freq"])
        # Temporarily read near the resonator response seed to maximize spectroscopy
        # contrast.  This does not adopt the seed as the optimized SS readout.
        seed_candidate = dict(self._discovery_readout)

        def run(span, points):
            freqs = self._float_axis(prior, span, points, include=[prior])
            z = self._acquire_spectroscopy(
                freqs, seed_candidate, p["shots"], p["gain"],
                p["pulse_length_us"])
            features = self._spectral_features(
                freqs, z, max_candidates=p["max_candidates"])
            return freqs, z, features

        local_freqs, local_z, local_features = run(
            p["local_span_mhz"], p["local_points"])
        used_wide = bool(p.get("always_wide", True)
                         or local_features["best_snr"]
                         < float(p["min_feature_snr"]))
        if used_wide:
            reason = ("the starting frequency is deliberately treated as untrusted"
                      if p.get("always_wide", True)
                      else "local feature SNR is %.2f" % local_features["best_snr"])
            self._log(
                "spectroscopy", "OK",
                "%s; also scanning the full %.1f MHz span so a nearby TLS cannot "
                "hide the intended transition" % (reason, p["wide_span_mhz"]))
            wide_freqs, wide_z, wide_features = run(
                p["wide_span_mhz"], p["wide_points"])
        else:
            wide_freqs = wide_z = wide_features = None

        candidate_rows = []
        for source, source_freqs, source_features in (
                ("local", local_freqs, local_features),
                ("wide", wide_freqs, wide_features)):
            if source_features is None:
                continue
            for index in source_features["candidate_indices"]:
                candidate_rows.append({
                    "frequency": float(source_freqs[index]),
                    "score": float(source_features["snr_trace"][index]),
                    "source": source,
                })
        candidate_rows.sort(key=lambda row: row["score"], reverse=True)
        steps = [abs(float(np.median(np.diff(local_freqs))))]
        if wide_freqs is not None:
            steps.append(abs(float(np.median(np.diff(wide_freqs)))))
        # Merge duplicate representations of one line from the fine and wide scans,
        # while keeping genuinely separate nearby basins for coherent-Rabi arbitration.
        tolerance = 0.6 * max(steps)
        unique = [prior]
        retained_rows = []
        for row in candidate_rows:
            if any(abs(row["frequency"] - old) <= tolerance for old in unique):
                continue
            unique.append(row["frequency"])
            retained_rows.append(row)
            if len(unique) >= 1 + int(p["max_candidates"]):
                break
        self._spec_candidates_mhz = [float(value) for value in unique]
        freqs = wide_freqs if wide_freqs is not None else local_freqs
        z = wide_z if wide_z is not None else local_z
        features = wide_features if wide_features is not None else local_features
        self._maps["spectroscopy"] = {
            "axes": {"qubit_frequency_mhz": freqs},
            "complex_response": z, "feature_residual": features["residual"],
            "feature_snr": features["snr_trace"],
            "used_wide_scan": bool(used_wide),
            "candidate_frequencies_mhz": np.asarray(self._spec_candidates_mhz),
            "candidate_scores": np.asarray(
                [row["score"] for row in retained_rows], dtype=float),
            "local_frequency_mhz": local_freqs,
            "local_complex_response": local_z,
            "local_feature_snr": local_features["snr_trace"],
        }
        if wide_freqs is not None:
            self._maps["spectroscopy"].update({
                "wide_frequency_mhz": wide_freqs,
                "wide_complex_response": wide_z,
                "wide_feature_snr": wide_features["snr_trace"],
            })
        self._log("spectroscopy", "OK",
                  "retained spectral seeds %s; coherent Rabi/direct SS choose among them"
                  % ", ".join("%.4f" % f for f in self._spec_candidates_mhz))
        return self._spec_candidates_mhz

    def _stage_iq_rabi(self):
        p = self.params["iq_rabi"]
        if not p.get("enabled", True):
            self._log("iq_rabi", "SKIP", "disabled")
            return None
        # Resonator spectroscopy already established a better readout-frequency seed.
        # Use it for the cheap averaged-IQ maps and carry it into the rough direct-SS
        # candidates; otherwise a bad input readout can erase the Rabi we need in order
        # to escape that same bad starting tuple.
        rabi_base = dict(self._discovery_readout)
        local_freqs = []
        for center in self._spec_candidates_mhz:
            local_freqs.extend(self._float_axis(
                center, p["local_span_mhz"], p["freq_points_per_candidate"],
                include=[center]))
        # Register resolution makes sub-Hz distinctions irrelevant here.
        freqs = np.asarray(sorted(set(round(float(f), 6) for f in local_freqs)))
        gains = self._integer_axis(
            p["gain_min"], p["gain_max"], p["gain_points"])
        i_map, q_map = self._acquire_iq_chevron(
            freqs, gains, rabi_base, p["shots"])
        analysis = analyze_iq_chevron(
            freqs, gains, i_map, q_map, min_r2=p["min_r2"])
        best = analysis["best"]
        rough_freq = float(best["frequency"])
        rough_gain = float(best["fit"].get("pi_gain", np.nan))
        if not np.isfinite(rough_gain):
            # Still return a physical first-response lobe if a heavily damped trace did
            # not satisfy the coherent fit.  Direct SS confirmation remains sovereign.
            projection = np.asarray(best["projection"])
            rough_gain = float(gains[int(np.nanargmax(np.abs(projection - projection[0])))])
        rough_gain = int(np.clip(round(rough_gain), 1, 32767))
        self._maps["iq_rabi"] = {
            "axes": {"qubit_frequency_mhz": freqs, "qubit_gain_dac": gains},
            "I": i_map, "Q": q_map,
            "row_scores": np.asarray([row["score"] for row in analysis["rows"]]),
            "row_r2": np.asarray([row["fit"].get("r2", np.nan)
                                  for row in analysis["rows"]]),
            "row_pi_gain": np.asarray([row["fit"].get("pi_gain", np.nan)
                                       for row in analysis["rows"]]),
        }

        ranked_rows = sorted(analysis["rows"], key=lambda row: row["score"],
                             reverse=True)
        rabi_candidates = []
        selected_rows = []
        # Preserve at least one coherent candidate from every spectral basin.  Without
        # this non-maximum suppression, four adjacent samples around one strong TLS can
        # crowd the configured-prior/qubit basin out of the direct-SS shortlist.
        spectral_centers = np.asarray(self._spec_candidates_mhz, dtype=float)
        for center_index, center in enumerate(spectral_centers):
            # Use disjoint nearest-centre (Voronoi) assignment.  Overlapping +/- local
            # windows must not let several nearby spectral seeds all select the same
            # strong Rabi row and silently erase a weaker basin.
            basin = [
                row for row in ranked_rows
                if int(np.argmin(np.abs(
                    spectral_centers - float(row["frequency"])))) == center_index
            ]
            if basin:
                selected_rows.append(basin[0])
        selected_rows.extend(ranked_rows)
        seen_frequencies = set()
        rabi_capacity = max(
            int(p.get("shortlist", 4)), len(self._spec_candidates_mhz))
        for row in selected_rows:
            fkey = round(float(row["frequency"]), 6)
            if fkey in seen_frequencies:
                continue
            seen_frequencies.add(fkey)
            gain = row["fit"].get("pi_gain", np.nan)
            if not np.isfinite(gain):
                projection = np.asarray(row["projection"])
                gain = gains[int(np.nanargmax(np.abs(projection - projection[0])))]
            rabi_candidates.append(_with_candidate(
                rabi_base, qubit_pi_freq=float(row["frequency"]),
                qubit_pi_gain=int(np.clip(round(gain), 1, 32767))))
            if len(_unique_candidates(rabi_candidates)) >= rabi_capacity:
                break

        fine_stop = min(32767, max(int(round(2.4 * rough_gain)), rough_gain + 4))
        fine_gains = self._integer_axis(0, fine_stop, p["fine_gain_points"])
        fi, fq = self._acquire_iq_chevron(
            np.asarray([rough_freq]), fine_gains, rabi_base, p["shots"])
        fine = analyze_iq_chevron(
            np.asarray([rough_freq]), fine_gains, fi, fq,
            min_r2=max(0.45, 0.8 * float(p["min_r2"])))
        fine_gain = fine["best"]["fit"].get("pi_gain", np.nan)
        if np.isfinite(fine_gain):
            rough_gain = int(np.clip(round(fine_gain), 1, 32767))
        self._maps["rough_amplitude_rabi"] = {
            "axes": {"qubit_frequency_mhz": np.asarray([rough_freq]),
                     "qubit_gain_dac": fine_gains},
            "I": fi, "Q": fq,
            "projection": np.asarray(fine["best"]["projection"])[None, :],
            "fit": np.asarray(fine["best"]["fit"].get("yfit", []))[None, :],
        }
        self.working = _with_candidate(
            rabi_base, qubit_pi_freq=rough_freq, qubit_pi_gain=rough_gain)
        # Refinement replaces the coarse representative of its own basin; it must not
        # consume an extra shortlist slot and evict the weaker fourth basin (which may
        # be the intended qubit behind stronger TLS lines).
        rabi_candidates = _unique_candidates(rabi_candidates)
        if rabi_candidates:
            replace_index = int(np.argmin([
                abs(float(candidate["qubit_pi_freq"]) - rough_freq)
                for candidate in rabi_candidates
            ]))
            rabi_candidates[replace_index] = dict(self.working)
        else:
            rabi_candidates = [dict(self.working)]
        self._rabi_candidates = _unique_candidates(rabi_candidates)[:rabi_capacity]
        self._log("iq_rabi", "OK" if analysis["ok"] else "WARN",
                  "common-mode-subtracted Rabi seed %.6f MHz @ %d DAC (r2 %.3f)"
                  % (rough_freq, rough_gain, best["fit"].get("r2", np.nan)))
        return self.working

    def _stage_rough_single_shot(self):
        p = self.params["rough_single_shot"]
        incumbent = dict(self.working)
        seeds = list(self._rabi_candidates) or [incumbent]
        frequency_offsets = np.linspace(
            -float(p["freq_span_mhz"]) / 2.0,
            float(p["freq_span_mhz"]) / 2.0, int(p["freq_points"]))
        gain_scales = np.linspace(
            1.0 - float(p["gain_fraction"]),
            1.0 + float(p["gain_fraction"]), int(p["gain_points"]))
        actual_gains = np.empty((len(seeds), len(gain_scales)), dtype=int)
        candidates = []
        for basin_index, seed in enumerate(seeds):
            actual_gains[basin_index] = np.clip(
                np.rint(float(seed["qubit_pi_gain"]) * gain_scales),
                1, 32767).astype(int)
            for offset in frequency_offsets:
                for gain in actual_gains[basin_index]:
                    # Candidates discovered before readout optimization are always
                    # grafted onto the current read tuple.
                    candidates.append(_with_candidate(
                        incumbent, sigma=float(seed["sigma"]),
                        qubit_pi_freq=float(seed["qubit_pi_freq"] + offset),
                        qubit_pi_gain=int(gain)))

        shape = (len(seeds), len(frequency_offsets), len(gain_scales))
        score = np.full(int(np.prod(shape)), np.nan)
        score_se = np.full_like(score, np.nan)
        order = self.rng.permutation(len(candidates))
        cache = {}
        failures = 0
        consecutive_failures = 0
        aborted = False
        self._log(
            "rough_ss", "OK",
            "%d-basin direct-SS Rabi chevron (%d points, %d shots/state)"
            % (len(seeds), len(candidates), int(p["coarse_shots"])))
        progress_step = max(len(candidates) // 10, 1)
        for count, index in enumerate(order):
            key = _candidate_key(candidates[index])
            if key in cache:
                score[index], score_se[index] = cache[key]
                consecutive_failures = 0
                continue
            try:
                measured = self._measure_candidate(
                    candidates[index], int(p["coarse_shots"]),
                    "rough_ss chevron coarse",
                    state_order="ge" if count % 2 == 0 else "eg")
                score[index] = measured["fidelity"]
                score_se[index] = measured["fidelity_se"]
                cache[key] = (score[index], score_se[index])
                consecutive_failures = 0
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                failures += 1
                consecutive_failures += 1
                self._log(
                    "rough_ss", "WARN", "chevron point %d/%d failed (%s: %s)"
                    % (count + 1, len(candidates), type(exc).__name__, exc))
                if consecutive_failures >= int(self.params.get(
                        "max_consecutive_point_failures", 5)):
                    aborted = True
                    self._log("rough_ss", "WARN",
                              "backend failure circuit breaker stopped the SS chevron")
                    break
            if (self._detailed_console()
                    and ((count + 1) % progress_step == 0
                         or count + 1 == len(candidates))):
                print("      rough_ss chevron progress: %d/%d"
                      % (count + 1, len(candidates)))

        score_map = score.reshape(shape)
        coverage = float(np.count_nonzero(np.isfinite(score)) / max(score.size, 1))
        self._maps["rough_ss_chevron"] = {
            "axes": {
                "basin_seed_frequency_mhz": np.asarray(
                    [seed["qubit_pi_freq"] for seed in seeds], dtype=float),
                "frequency_offset_mhz": frequency_offsets,
                "gain_scale": gain_scales,
            },
            "actual_gain_dac": actual_gains,
            "fidelity": score_map,
            "fidelity_se": score_se.reshape(shape),
            "coverage": coverage,
            "failed_points": int(failures),
            "aborted": bool(aborted),
            "search_complete": bool(not aborted and coverage >= 1.0 - 1e-12),
            "selection_confirmed": False,
        }
        basin_winners = []
        for basin_index, seed in enumerate(seeds):
            flat = score_map[basin_index].reshape(-1)
            finite = np.flatnonzero(np.isfinite(flat))
            if finite.size:
                local_index = int(finite[np.argmax(flat[finite])])
                global_index = (basin_index * len(frequency_offsets)
                                * len(gain_scales) + local_index)
                basin_winners.append(candidates[global_index])
            else:
                basin_winners.append(_with_candidate(
                    incumbent, sigma=float(seed["sigma"]),
                    qubit_pi_freq=float(seed["qubit_pi_freq"]),
                    qubit_pi_gain=int(seed["qubit_pi_gain"])))
        if not basin_winners:
            raise RuntimeError("no Rabi basin is available for direct SS confirmation")
        confirmed = self._confirm_candidates(
            basin_winners + [incumbent, self.initial],
            p["shots"], p["blocks"],
            "rough pulse exact step-5")
        confirmation_complete = self._confirmation_batch_complete(confirmed)
        self._maps["rough_ss_chevron"]["selection_confirmed"] = True
        self._maps["rough_ss_chevron"]["selection_confirmation_complete"] = bool(
            confirmation_complete)
        if not confirmation_complete:
            self._maps["rough_ss_chevron"]["search_complete"] = False
        direct_best = self._best_aggregate(confirmed)
        best = self._noninferior_seed(
            confirmed, incumbent, direct_best, margin=0.005)
        self._adopt(best, "rough_ss")
        return best

    def _stage_parity_chevron(self):
        p = self.params["parity_chevron"]
        if not p.get("enabled", True):
            self._log("parity_chevron", "SKIP", "disabled")
            return None
        incumbent = dict(self.working)
        calibration_shots = max(int(p["shots"]), 300)
        initial = self._parity_map(
            "parity_chevron", incumbent, p,
            incumbent["qubit_pi_freq"], incumbent["qubit_pi_gain"],
            calibration_shots, "parity chevron")
        index = initial["index"]
        initial_edge = (index[0] in (0, initial["frequencies"].size - 1)
                        or index[1] in (0, initial["gains"].size - 1))
        self._maps["parity_chevron"]["initial_edge_winner"] = bool(initial_edge)
        seeds = [initial["seed"]]
        preferred = initial["seed"]
        maps = [initial]
        final_edge = bool(initial_edge)
        expansion_ok = False
        if initial_edge:
            self._maps["parity_chevron"]["search_complete"] = False
            self._log(
                "parity_chevron", "WARN",
                "raw amplified optimum is on a boundary; running one centered/outward "
                "frequency/gain expansion before deciding")
            try:
                expanded = self._parity_map(
                    "parity_chevron_edge", incumbent, p,
                    initial["seed"]["qubit_pi_freq"],
                    initial["seed"]["qubit_pi_gain"], calibration_shots,
                    "parity chevron expansion")
                expanded_index = expanded["index"]
                final_edge = bool(
                    expanded_index[0] in (0, expanded["frequencies"].size - 1)
                    or expanded_index[1] in (0, expanded["gains"].size - 1))
                self._maps["parity_chevron_edge"]["edge_winner"] = final_edge
                self._maps["parity_chevron_edge"]["search_complete"] = bool(
                    expanded["data_complete"] and not final_edge)
                seeds.insert(0, expanded["seed"])
                preferred = expanded["seed"]
                maps.append(expanded)
                expansion_ok = True
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                final_edge = True
                self._maps["parity_chevron"]["expansion_failure"] = \
                    "%s: %s" % (type(exc).__name__, exc)
                self._log(
                    "parity_chevron", "WARN",
                    "boundary expansion failed (%s: %s); directly confirming the "
                    "best measured edge point and incumbent anyway"
                    % (type(exc).__name__, exc))
        confirmed = self._confirm_candidates(
            seeds + [incumbent], p["confirm_shots"], p["confirm_blocks"],
            "parity winner direct step-5")
        confirmation_complete = self._confirmation_batch_complete(confirmed)
        # One-pulse assignment fidelity is intentionally insensitive to the coherent
        # error amplified by this map.  Keep the map optimum when its direct replay is
        # noninferior, exactly as in the final variable-depth refinement.
        best = self._noninferior_seed(confirmed, preferred, incumbent)
        self._adopt(best, "parity_chevron")
        for mapping in maps:
            self._maps[mapping["stage"]]["selection_confirmed"] = True
            self._maps[mapping["stage"]]["selection_confirmation_complete"] = bool(
                confirmation_complete)
            if not confirmation_complete:
                self._maps[mapping["stage"]]["search_complete"] = False
        complete = bool(
            confirmation_complete and initial["data_complete"]
            and (not initial_edge
                 or (expansion_ok and maps[-1]["data_complete"] and not final_edge)))
        self._maps["parity_chevron"]["expanded"] = bool(initial_edge)
        self._maps["parity_chevron"]["edge_winner"] = bool(
            initial_edge and final_edge)
        self._maps["parity_chevron"]["search_complete"] = complete
        self._record_key_evidence(
            ("qubit_freq", "qubit_pi_freq", "qubit_pi_gain"),
            "parity_chevron", complete)
        if initial_edge and not final_edge and complete:
            self._log("parity_chevron", "OK",
                      "expanded amplified optimum is interior; joint control search "
                      "is complete")
        elif initial_edge:
            self._log("parity_chevron", "WARN",
                      "expanded amplified optimum remains boundary-limited or incomplete; "
                      "best candidate retained for the exact final tuple replay")
        elif not complete:
            self._log("parity_chevron", "WARN",
                      "parity map was incomplete; confirmed candidate retained but "
                      "does not have independent coordinate-search evidence")
        return best

    def _stage_fine_frequency(self, stage="fine_frequency"):
        p = self.params["fine_frequency"]
        if not p.get("enabled", True):
            self._log(stage, "SKIP", "disabled")
            return None
        incumbent = dict(self.working)
        initial = self._inverse_pair_map(
            stage, incumbent, p, incumbent["qubit_pi_freq"])
        initial_edge = initial["index"] in (
            0, initial["frequencies"].size - 1)
        self._maps[stage]["initial_edge_winner"] = bool(initial_edge)
        seeds = [initial["seed"]]
        preferred = initial["seed"]
        maps = [initial]
        final_edge = bool(initial_edge)
        expansion_ok = False
        if initial_edge:
            self._maps[stage]["search_complete"] = False
            self._log(
                stage, "WARN",
                "inverse-pair minimum is on a boundary; running one centered/outward "
                "frequency expansion before deciding")
            try:
                expanded = self._inverse_pair_map(
                    stage + "_edge", incumbent, p,
                    initial["seed"]["qubit_pi_freq"])
                final_edge = expanded["index"] in (
                    0, expanded["frequencies"].size - 1)
                self._maps[expanded["stage"]]["edge_winner"] = bool(final_edge)
                self._maps[expanded["stage"]]["search_complete"] = bool(
                    expanded["data_complete"] and not final_edge)
                seeds.insert(0, expanded["seed"])
                preferred = expanded["seed"]
                maps.append(expanded)
                expansion_ok = True
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                final_edge = True
                self._maps[stage]["expansion_failure"] = \
                    "%s: %s" % (type(exc).__name__, exc)
                self._log(
                    stage, "WARN",
                    "boundary expansion failed (%s: %s); directly confirming the "
                    "best measured edge point and incumbent anyway"
                    % (type(exc).__name__, exc))
        confirmed = self._confirm_candidates(
            seeds + [incumbent], p["confirm_shots"], p["confirm_blocks"],
            "%s direct replay" % stage)
        confirmation_complete = self._confirmation_batch_complete(confirmed)
        chosen = self._noninferior_seed(confirmed, preferred, incumbent)
        self._adopt(chosen, stage)
        for mapping in maps:
            self._maps[mapping["stage"]]["selection_confirmed"] = True
            self._maps[mapping["stage"]]["selection_confirmation_complete"] = bool(
                confirmation_complete)
            if not confirmation_complete:
                self._maps[mapping["stage"]]["search_complete"] = False
        complete = bool(
            confirmation_complete and initial["data_complete"]
            and (not initial_edge
                 or (expansion_ok and maps[-1]["data_complete"] and not final_edge)))
        self._maps[stage]["expanded"] = bool(initial_edge)
        self._maps[stage]["edge_winner"] = bool(initial_edge and final_edge)
        self._maps[stage]["search_complete"] = complete
        self._record_key_evidence(
            ("qubit_freq", "qubit_pi_freq"), stage, complete)
        if initial_edge and not final_edge and complete:
            self._log(stage, "OK",
                      "expanded inverse-pair minimum is interior; frequency search "
                      "is complete")
        elif initial_edge:
            self._log(stage, "WARN",
                      "expanded inverse-pair minimum remains boundary-limited or "
                      "incomplete; best candidate retained for the exact final tuple "
                      "replay")
        elif not complete:
            self._log(stage, "WARN",
                      "inverse-pair map was incomplete; confirmed candidate retained "
                      "without independent coordinate-search evidence")
        return chosen

    def _stage_amplified_error(self):
        p = self.params["amplified_error"]
        if not p.get("enabled", True):
            self._log("amplified_error", "SKIP", "disabled")
            return None
        self._log(
            "amplified_error", "OK",
            "QUA-style amplified amplitude error (AAE) refinement for X180: "
            "joint multi-depth parity across frequency and gain")
        incumbent = dict(self.working)
        initial = self._parity_map(
            "amplified_error", incumbent, p,
            incumbent["qubit_pi_freq"], incumbent["qubit_pi_gain"],
            p["calibration_shots"], "amplified error")
        index = initial["index"]
        initial_edge = (index[0] in (0, initial["frequencies"].size - 1)
                        or index[1] in (0, initial["gains"].size - 1))
        self._maps["amplified_error"]["initial_edge_winner"] = bool(initial_edge)
        self._maps["amplified_error"].update({
            "calibration_kind": "amplified_amplitude_error_x180",
            "qua_analogue": "ALE_tune_1Q.py / m_amplified_amplitude_error.AAE",
            "leakage_measurement": False,
        })
        seeds = [initial["seed"]]
        preferred = initial["seed"]
        maps = [initial]
        final_edge = bool(initial_edge)
        expansion_ok = False
        if initial_edge:
            self._maps["amplified_error"]["search_complete"] = False
            self._log(
                "amplified_error", "WARN",
                "raw variable-depth optimum is on a boundary; running one centered/"
                "outward frequency/gain expansion before deciding")
            try:
                expanded = self._parity_map(
                    "amplified_error_edge", incumbent, p,
                    initial["seed"]["qubit_pi_freq"],
                    initial["seed"]["qubit_pi_gain"],
                    p["calibration_shots"], "amplified error expansion")
                expanded_index = expanded["index"]
                final_edge = bool(
                    expanded_index[0] in (0, expanded["frequencies"].size - 1)
                    or expanded_index[1] in (0, expanded["gains"].size - 1))
                self._maps["amplified_error_edge"]["edge_winner"] = final_edge
                self._maps["amplified_error_edge"].update({
                    "calibration_kind": "amplified_amplitude_error_x180",
                    "qua_analogue": (
                        "ALE_tune_1Q.py / m_amplified_amplitude_error.AAE"),
                    "leakage_measurement": False,
                })
                self._maps["amplified_error_edge"]["search_complete"] = bool(
                    expanded["data_complete"] and not final_edge)
                seeds.insert(0, expanded["seed"])
                preferred = expanded["seed"]
                maps.append(expanded)
                expansion_ok = True
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                final_edge = True
                self._maps["amplified_error"]["expansion_failure"] = \
                    "%s: %s" % (type(exc).__name__, exc)
                self._log(
                    "amplified_error", "WARN",
                    "boundary expansion failed (%s: %s); directly confirming the "
                    "best measured edge point and incumbent anyway"
                    % (type(exc).__name__, exc))
        confirmed = self._confirm_candidates(
            seeds + [incumbent], p["confirm_shots"], p["confirm_blocks"],
            "amplified-error direct replay")
        confirmation_complete = self._confirmation_batch_complete(confirmed)
        chosen = self._noninferior_seed(confirmed, preferred, incumbent)
        self._adopt(chosen, "amplified_error")
        for mapping in maps:
            self._maps[mapping["stage"]]["selection_confirmed"] = True
            self._maps[mapping["stage"]]["selection_confirmation_complete"] = bool(
                confirmation_complete)
            if not confirmation_complete:
                self._maps[mapping["stage"]]["search_complete"] = False
        complete = bool(
            confirmation_complete and initial["data_complete"]
            and (not initial_edge
                 or (expansion_ok and maps[-1]["data_complete"] and not final_edge)))
        self._maps["amplified_error"]["expanded"] = bool(initial_edge)
        self._maps["amplified_error"]["edge_winner"] = bool(
            initial_edge and final_edge)
        self._maps["amplified_error"]["search_complete"] = complete
        self._record_key_evidence(
            ("qubit_freq", "qubit_pi_freq", "qubit_pi_gain"),
            "amplified_error", complete)
        if initial_edge and not final_edge and complete:
            self._log("amplified_error", "OK",
                      "expanded variable-depth optimum is interior; amplified control "
                      "search is complete")
        elif initial_edge:
            self._log("amplified_error", "WARN",
                      "expanded variable-depth optimum remains boundary-limited or "
                      "incomplete; best candidate retained for the exact final tuple "
                      "replay")
        elif not complete:
            self._log("amplified_error", "WARN",
                      "variable-depth map was incomplete; confirmed candidate retained "
                      "without independent coordinate-search evidence")
        return chosen

    def _stage_readout_grid(self, stage="readout_grid", local=False,
                            record_evidence=True, prior_complete=True):
        p = self.params["readout"]
        if not p.get("enabled", True):
            self._log(stage, "SKIP", "disabled")
            return None
        if local:
            center_freq = float(self.working["read_pulse_freq"])
            span = p["local_freq_span_mhz"]
            nfreq = p["local_freq_points"]
            center_gain = int(self.working["read_pulse_gain"])
            fraction = float(p["local_gain_fraction"])
            gains = self._gain_axis(
                center_gain * (1.0 - fraction), center_gain * (1.0 + fraction),
                p["local_gain_points"], include=[center_gain])
        else:
            incumbent = float(self.working["read_pulse_freq"])
            seed = float(self._resonator_seed)
            center_freq = 0.5 * (incumbent + seed)
            span = max(float(p["freq_span_mhz"]),
                       abs(incumbent - seed) + 0.5 * float(p["freq_span_mhz"]))
            nfreq = p["freq_points"]
            gains = self._gain_axis(
                p["gain_min"], p["gain_max"], p["gain_points"],
                include=[self.working["read_pulse_gain"]])
        freqs = self._float_axis(
            center_freq, span, nfreq,
            include=[self.working["read_pulse_freq"], self._resonator_seed])
        candidates = [
            _with_candidate(self.working, read_pulse_freq=float(freq),
                            read_pulse_gain=int(gain))
            for freq in freqs for gain in gains
        ]
        result = self._direct_grid(
            stage, candidates, (freqs.size, gains.size),
            {"read_frequency_mhz": freqs, "read_gain_dac": gains},
            p["shots"], p["shortlist"], p["confirm_shots"],
            p["confirm_blocks"])
        coverage_complete = bool(
            prior_complete and self._maps[stage].get("search_complete", False))
        at_edge = (np.isclose(self.working["read_pulse_freq"], freqs[0])
                   or np.isclose(self.working["read_pulse_freq"], freqs[-1])
                   or int(self.working["read_pulse_gain"]) in
                   (int(gains[0]), int(gains[-1])))
        self._maps[stage]["edge_winner"] = bool(at_edge)
        self._maps[stage]["eligibility_evidence_enabled"] = bool(record_evidence)
        if at_edge:
            self._maps[stage]["search_complete"] = False
            if record_evidence:
                self._record_key_evidence(
                    ("read_pulse_freq", "read_pulse_gain"), stage, False)
        if at_edge and not stage.endswith("_edge"):
            self._log(stage, "WARN",
                      "confirmed winner is on a grid edge; expanding once around it")
            return self._stage_readout_grid(
                stage + "_edge", local=True, record_evidence=record_evidence,
                prior_complete=coverage_complete)
        if at_edge:
            self._log(stage, "WARN",
                      "winner remains on the expanded edge; result retained but this "
                      "readout map is not independent coordinate-search evidence")
        elif record_evidence:
            self._record_key_evidence(
                ("read_pulse_freq", "read_pulse_gain"), stage,
                coverage_complete)
            if not coverage_complete:
                self._log(stage, "WARN",
                          "winner confirmed, but incomplete upstream/map coverage makes "
                          "the exact final tuple replay responsible for write safety")
        return result

    def _stage_readout_length(self):
        p = self.params["readout_length"]
        if not p.get("enabled", True):
            self._log("readout_length", "SKIP", "disabled")
            return None
        values = sorted(set(float(v) for v in p["values_us"]
                            if np.isfinite(v) and float(v) > 0)
                        | {float(self.working["read_length"])})
        center_frequency = float(self.working["read_pulse_freq"])
        frequency_offsets = np.linspace(
            -float(p["freq_span_mhz"]) / 2.0,
            float(p["freq_span_mhz"]) / 2.0, int(p["freq_points"]))
        actual_gains = self._gain_axis(
            p.get("gain_min", self.params["readout"]["gain_min"]),
            p.get("gain_max", self.params["readout"]["gain_max"]),
            p["gain_points"], include=[self.working["read_pulse_gain"]])
        candidates = [
            _with_candidate(
                self.working, read_length=value,
                read_pulse_freq=float(center_frequency + offset),
                read_pulse_gain=int(gain))
            for value in values for offset in frequency_offsets for gain in actual_gains
        ]
        result = self._direct_grid(
            "readout_length", candidates,
            (len(values), len(frequency_offsets), len(actual_gains)),
            {"read_length_us": np.asarray(values),
             "frequency_offset_mhz": frequency_offsets,
             "read_gain_dac": actual_gains}, p["shots"], p["shortlist"],
            p["confirm_shots"], p["confirm_blocks"])
        initial_coverage_complete = bool(
            self._maps["readout_length"].get("search_complete", False))
        self._maps["readout_length"]["actual_gain_dac"] = actual_gains
        selected_length = float(self.working["read_length"])
        length_edge = (np.isclose(selected_length, values[0])
                       or np.isclose(selected_length, values[-1]))
        frequency_edge = (
            np.isclose(self.working["read_pulse_freq"],
                       center_frequency + frequency_offsets[0])
            or np.isclose(self.working["read_pulse_freq"],
                          center_frequency + frequency_offsets[-1]))
        gain_edge = int(self.working["read_pulse_gain"]) in (
            int(actual_gains[0]), int(actual_gains[-1]))
        at_edge = bool(length_edge or frequency_edge or gain_edge)
        self._maps["readout_length"]["edge_winner"] = bool(at_edge)
        self._maps["readout_length"]["edge_dimensions"] = {
            "read_length": bool(length_edge),
            "read_pulse_freq": bool(frequency_edge),
            "read_pulse_gain": bool(gain_edge),
        }
        if at_edge:
            self._maps["readout_length"]["search_complete"] = False
            extension = (max(float(p["min_us"]), 0.5 * selected_length)
                         if np.isclose(selected_length, values[0])
                         else min(float(p["max_us"]), 1.5 * selected_length))
            self._record_key_evidence(
                ("read_pulse_freq", "read_pulse_gain", "read_length"),
                "readout_length", False)
            if length_edge and not np.isclose(extension, selected_length):
                self._log("readout_length", "WARN",
                          "length winner is on an edge; testing %.1f us once" % extension)
                incumbent = dict(self.working)
                edge_lengths = np.asarray([selected_length, extension], dtype=float)
                edge_gains = self._gain_axis(
                    p.get("gain_min", self.params["readout"]["gain_min"]),
                    p.get("gain_max", self.params["readout"]["gain_max"]),
                    p["gain_points"], include=[incumbent["read_pulse_gain"]])
                edge_candidates = [
                    _with_candidate(
                        incumbent, read_length=float(length),
                        read_pulse_freq=float(incumbent["read_pulse_freq"] + offset),
                        read_pulse_gain=int(gain))
                    for length in edge_lengths for offset in frequency_offsets
                    for gain in edge_gains
                ]
                result = self._direct_grid(
                    "readout_length_edge", edge_candidates,
                    (2, len(frequency_offsets), len(edge_gains)),
                    {"read_length_us": edge_lengths,
                     "frequency_offset_mhz": frequency_offsets,
                     "read_gain_dac": edge_gains}, p["shots"], p["shortlist"],
                    p["confirm_shots"], p["confirm_blocks"])
                extension_coverage_complete = bool(
                    self._maps["readout_length_edge"].get(
                        "search_complete", False))
                self._maps["readout_length_edge"]["actual_gain_dac"] = edge_gains
                extension_won = np.isclose(float(self.working["read_length"]), extension)
                edge_frequency_limited = (
                    np.isclose(self.working["read_pulse_freq"],
                               incumbent["read_pulse_freq"] + frequency_offsets[0])
                    or np.isclose(self.working["read_pulse_freq"],
                                  incumbent["read_pulse_freq"] + frequency_offsets[-1]))
                edge_gain_limited = int(self.working["read_pulse_gain"]) in (
                    int(edge_gains[0]), int(edge_gains[-1]))
                unresolved = bool(
                    extension_won or edge_frequency_limited or edge_gain_limited)
                self._maps["readout_length_edge"]["edge_winner"] = unresolved
                self._maps["readout_length_edge"]["edge_dimensions"] = {
                    "read_length": bool(extension_won),
                    "read_pulse_freq": bool(edge_frequency_limited),
                    "read_pulse_gain": bool(edge_gain_limited),
                }
                extension_complete = bool(
                    initial_coverage_complete and extension_coverage_complete
                    and not unresolved)
                self._maps["readout_length_edge"]["search_complete"] = \
                    extension_complete
                self._record_key_evidence(
                    ("read_pulse_freq", "read_pulse_gain", "read_length"),
                    "readout_length_edge", extension_complete)
                if unresolved:
                    self._log("readout_length_edge", "WARN",
                              "expanded joint search remains boundary-limited in %s; "
                              "retained for the exact final tuple replay"
                              % ", ".join(key for key, value in
                                          self._maps["readout_length_edge"]
                                          ["edge_dimensions"].items() if value))
            elif at_edge:
                self._log(
                    "readout_length", "WARN",
                    "joint length search is boundary-limited in %s; retained and a "
                    "local readout refinement will follow, but this length comparison "
                    "is not write evidence"
                    % ", ".join(key for key, value in
                                self._maps["readout_length"]["edge_dimensions"].items()
                                if value))
        else:
            self._record_key_evidence(
                ("read_pulse_freq", "read_pulse_gain", "read_length"),
                "readout_length", initial_coverage_complete)
            if not initial_coverage_complete:
                self._log(
                    "readout_length", "WARN",
                    "winner confirmed, but incomplete map coverage makes the joint "
                    "length result report-only")
        # Every length was compared after its own local f/g retune.  One final fine
        # pass around the winning three-dimensional cell removes coarse-grid error.
        if self.params["readout"].get("enabled", True):
            self._stage_readout_grid("readout_after_length", local=True)
        return result

    def _stage_qubit_grid(self, stage="qubit_grid", local=False,
                          prior_complete=True):
        p = self.params["qubit"]
        if not p.get("enabled", True):
            self._log(stage, "SKIP", "disabled")
            return None
        if local:
            span, nfreq = p["local_freq_span_mhz"], p["local_freq_points"]
            fraction, ngain = p["local_gain_fraction"], p["local_gain_points"]
        else:
            span, nfreq = p["freq_span_mhz"], p["freq_points"]
            fraction, ngain = p["gain_fraction"], p["gain_points"]
        center_freq = float(self.working["qubit_pi_freq"])
        center_gain = int(self.working["qubit_pi_gain"])
        freqs = self._float_axis(center_freq, span, nfreq, include=[center_freq])
        gains = self._gain_axis(
            center_gain * (1.0 - float(fraction)),
            center_gain * (1.0 + float(fraction)), ngain, include=[center_gain])
        candidates = [
            _with_candidate(self.working, qubit_pi_freq=float(freq),
                            qubit_pi_gain=int(gain))
            for freq in freqs for gain in gains
        ]
        result = self._direct_grid(
            stage, candidates, (freqs.size, gains.size),
            {"qubit_frequency_mhz": freqs, "qubit_gain_dac": gains},
            p["shots"], p["shortlist"], p["confirm_shots"],
            p["confirm_blocks"])
        coverage_complete = bool(
            prior_complete and self._maps[stage].get("search_complete", False))
        at_edge = (np.isclose(self.working["qubit_pi_freq"], freqs[0])
                   or np.isclose(self.working["qubit_pi_freq"], freqs[-1])
                   or int(self.working["qubit_pi_gain"]) in
                   (int(gains[0]), int(gains[-1])))
        self._maps[stage]["edge_winner"] = bool(at_edge)
        if at_edge:
            self._maps[stage]["search_complete"] = False
            self._record_key_evidence(
                ("qubit_freq", "qubit_pi_freq", "qubit_pi_gain"), stage, False)
        if at_edge and not stage.endswith("_edge"):
            self._log(stage, "WARN",
                      "confirmed winner is on a grid edge; expanding once around it")
            return self._stage_qubit_grid(
                stage + "_edge", local=True,
                prior_complete=coverage_complete)
        if at_edge:
            self._log(stage, "WARN",
                      "winner remains on the expanded edge; result retained but this "
                      "control map is not independent coordinate-search evidence")
        else:
            self._record_key_evidence(
                ("qubit_freq", "qubit_pi_freq", "qubit_pi_gain"), stage,
                coverage_complete)
            if not coverage_complete:
                self._log(stage, "WARN",
                          "winner confirmed, but incomplete upstream/map coverage makes "
                          "the exact final tuple replay responsible for write safety")
        return result

    def _stage_pulse_duration(self):
        p = self.params["pulse_duration"]
        if not p.get("enabled", True):
            self._log("pulse_duration", "SKIP", "disabled")
            return None
        sigma_values = sorted(set(float(v) for v in p["sigma_values_us"]
                                  if np.isfinite(v) and float(v) > 0)
                              | {float(self.working["sigma"])})
        frequency_offsets = np.linspace(
            -float(p["freq_span_mhz"]) / 2.0,
            float(p["freq_span_mhz"]) / 2.0, int(p["freq_points"]))
        gain_scales = np.linspace(
            1.0 - float(p["gain_fraction"]),
            1.0 + float(p["gain_fraction"]), int(p["gain_points"]))
        old_sigma = float(self.working["sigma"])
        old_gain = float(self.working["qubit_pi_gain"])
        old_frequency = float(self.working["qubit_pi_freq"])
        candidates = []
        actual_gains = np.empty((len(sigma_values), len(gain_scales)), dtype=int)
        for si, sigma in enumerate(sigma_values):
            # Gaussian rotation area is approximately gain*sigma.  The area scaling is
            # only a center; every duration then gets a real local gain/frequency grid.
            predicted_gain = old_gain * old_sigma / sigma
            for gi, scale in enumerate(gain_scales):
                actual_gains[si, gi] = int(np.clip(
                    round(predicted_gain * scale), 1, 32767))
            for offset in frequency_offsets:
                for gain in actual_gains[si]:
                    candidates.append(_with_candidate(
                        self.working, sigma=float(sigma),
                        qubit_pi_freq=float(old_frequency + offset),
                        qubit_pi_gain=int(gain)))
        result = self._direct_grid(
            "pulse_duration", candidates,
            (len(sigma_values), len(frequency_offsets), len(gain_scales)),
            {"sigma_us": np.asarray(sigma_values),
             "frequency_offset_mhz": frequency_offsets,
             "gain_scale": gain_scales},
            p["shots"], p["shortlist"], p["confirm_shots"],
            p["confirm_blocks"])
        initial_coverage_complete = bool(
            self._maps["pulse_duration"].get("search_complete", False))
        self._maps["pulse_duration"]["actual_gain_dac"] = actual_gains
        selected_sigma = float(self.working["sigma"])
        selected_sigma_index = int(np.argmin(
            np.abs(np.asarray(sigma_values, dtype=float) - selected_sigma)))
        sigma_edge = (np.isclose(selected_sigma, sigma_values[0])
                      or np.isclose(selected_sigma, sigma_values[-1]))
        frequency_edge = (
            np.isclose(self.working["qubit_pi_freq"],
                       old_frequency + frequency_offsets[0])
            or np.isclose(self.working["qubit_pi_freq"],
                          old_frequency + frequency_offsets[-1]))
        selected_gain_axis = actual_gains[selected_sigma_index]
        gain_edge = int(self.working["qubit_pi_gain"]) in (
            int(selected_gain_axis[0]), int(selected_gain_axis[-1]))
        at_edge = bool(sigma_edge or frequency_edge or gain_edge)
        self._maps["pulse_duration"]["edge_winner"] = bool(at_edge)
        self._maps["pulse_duration"]["edge_dimensions"] = {
            "sigma": bool(sigma_edge),
            "qubit_pi_freq": bool(frequency_edge),
            "qubit_pi_gain": bool(gain_edge),
        }
        if at_edge:
            self._maps["pulse_duration"]["search_complete"] = False
            self._record_key_evidence(
                ("qubit_freq", "qubit_pi_freq", "qubit_pi_gain", "sigma"),
                "pulse_duration", False)
            if np.isclose(selected_sigma, sigma_values[0]):
                extension = max(0.025, 0.5 * selected_sigma)
            else:
                extension = min(1.0, 1.5 * selected_sigma)
            if sigma_edge and not np.isclose(extension, selected_sigma):
                self._log("pulse_duration", "WARN",
                          "duration winner is on an edge; testing %.1f ns once"
                          % (4000.0 * extension))
                incumbent = dict(self.working)
                extension_sigmas = np.asarray([selected_sigma, extension], dtype=float)
                edge_candidates = []
                edge_gains = np.empty((2, len(gain_scales)), dtype=int)
                for si, sigma in enumerate(extension_sigmas):
                    predicted = (float(incumbent["qubit_pi_gain"])
                                 * selected_sigma / sigma)
                    edge_gains[si] = np.clip(
                        np.rint(predicted * gain_scales), 1, 32767).astype(int)
                    for offset in frequency_offsets:
                        for gain in edge_gains[si]:
                            edge_candidates.append(_with_candidate(
                                incumbent, sigma=float(sigma),
                                qubit_pi_freq=float(
                                    incumbent["qubit_pi_freq"] + offset),
                                qubit_pi_gain=int(gain)))
                edge_result = self._direct_grid(
                    "pulse_duration_edge", edge_candidates,
                    (2, len(frequency_offsets), len(gain_scales)),
                    {"sigma_us": extension_sigmas,
                     "frequency_offset_mhz": frequency_offsets,
                     "gain_scale": gain_scales},
                    p["shots"], p["shortlist"], p["confirm_shots"],
                    p["confirm_blocks"])
                extension_coverage_complete = bool(
                    self._maps["pulse_duration_edge"].get(
                        "search_complete", False))
                self._maps["pulse_duration_edge"]["actual_gain_dac"] = edge_gains
                extension_won = np.isclose(float(self.working["sigma"]), extension)
                selected_edge_sigma = int(np.argmin(np.abs(
                    extension_sigmas - float(self.working["sigma"]))))
                edge_frequency_limited = (
                    np.isclose(self.working["qubit_pi_freq"],
                               incumbent["qubit_pi_freq"] + frequency_offsets[0])
                    or np.isclose(self.working["qubit_pi_freq"],
                                  incumbent["qubit_pi_freq"] + frequency_offsets[-1]))
                edge_gain_limited = int(self.working["qubit_pi_gain"]) in (
                    int(edge_gains[selected_edge_sigma, 0]),
                    int(edge_gains[selected_edge_sigma, -1]))
                unresolved = bool(
                    extension_won or edge_frequency_limited or edge_gain_limited)
                self._maps["pulse_duration_edge"]["edge_winner"] = unresolved
                self._maps["pulse_duration_edge"]["edge_dimensions"] = {
                    "sigma": bool(extension_won),
                    "qubit_pi_freq": bool(edge_frequency_limited),
                    "qubit_pi_gain": bool(edge_gain_limited),
                }
                extension_complete = bool(
                    initial_coverage_complete and extension_coverage_complete
                    and not unresolved)
                self._maps["pulse_duration_edge"]["search_complete"] = \
                    extension_complete
                self._record_key_evidence(
                    ("qubit_freq", "qubit_pi_freq", "qubit_pi_gain", "sigma"),
                    "pulse_duration_edge", extension_complete)
                if unresolved:
                    self._log("pulse_duration_edge", "WARN",
                              "expanded joint duration search remains boundary-limited "
                              "in %s; candidate is retained for exact final tuple replay"
                              % ", ".join(key for key, value in
                                          self._maps["pulse_duration_edge"]
                                          ["edge_dimensions"].items() if value))
                return edge_result
            self._log(
                "pulse_duration", "WARN",
                "joint duration search is boundary-limited in %s; candidate is retained "
                "but this duration comparison is not write evidence"
                % ", ".join(key for key, value in
                            self._maps["pulse_duration"]["edge_dimensions"].items()
                            if value))
        else:
            self._record_key_evidence(
                ("qubit_freq", "qubit_pi_freq", "qubit_pi_gain", "sigma"),
                "pulse_duration", initial_coverage_complete)
            if not initial_coverage_complete:
                self._log(
                    "pulse_duration", "WARN",
                    "winner confirmed, but incomplete map coverage makes the joint "
                    "duration map non-authoritative until exact final tuple replay")
        return result

    # ----------------------------------------------- practical operational leakage screen
    def _acquire_repeated_populations(self, candidate, pulse_counts, shots,
                                      calibration):
        """Measure exact-candidate odd/even repeated-pulse populations."""
        counts = [int(value) for value in pulse_counts]
        populations = np.full(len(counts), np.nan, dtype=float)
        for raw in self.rng.permutation(len(counts)):
            index = int(raw)
            cfg = self._cfg_for(
                candidate, drive_freq=float(candidate["qubit_pi_freq"]),
                sequence_gain=int(candidate["qubit_pi_gain"]),
                sequence_phases_deg=[0.0] * counts[index],
                shots=int(shots), reps=int(shots),
            )
            program = BasicSequenceProgram(self.soccfg, cfg)
            program.acquire(self.soc, load_pulses=True, progress=False)
            shot_i, shot_q = _shots_from_program(program, cfg)
            populations[index] = float(np.mean(
                discriminate_with_metrics(shot_i, shot_q, calibration)))
        return populations

    def _measure_operational_leakage_candidate(self, candidate, shots,
                                               reference_shots, label):
        """Screen one Gaussian using third-cloud and normalized repeat-return tests.

        This does not identify or estimate P(f).  It catches the operational symptoms
        that matter in a basic tune: a new IQ cloud and failure of one calibrated X180
        to alternate reproducibly between the binary g/e manifolds at several depths.
        """
        p = self.params["leakage"]
        candidate = dict(candidate)
        before = self._measure_candidate(
            candidate, int(reference_shots), "%s discriminator" % label)
        calibration = {key: before[key] for key in
                       ("read_theta", "scale_factor", "threshold")}
        depths = [int(value) for value in p["operational_depths"]
                  if int(value) > 0]
        if not depths or not any(value % 2 == 0 for value in depths) \
                or not any(value % 2 == 1 for value in depths):
            raise RuntimeError(
                "operational leakage depths require positive odd and even counts")
        populations = np.asarray(self._acquire_repeated_populations(
            candidate, depths, int(shots), calibration), dtype=float)
        after = self._measure_candidate(
            candidate, int(reference_shots), "%s discriminator post" % label,
            reference_discriminator=calibration)
        drift = self._calibration_drift(before, after)
        drift_stable = self._calibration_is_stable(drift)

        p_e_ground = float(before["p_e_given_g"])
        p_e_excited = float(1.0 - before["p_g_given_e"])
        contrast = float(p_e_excited - p_e_ground)
        finite_contrast = bool(
            np.isfinite(contrast)
            and contrast >= float(p["operational_min_binary_contrast"]))
        if finite_contrast:
            normalized = (populations - p_e_ground) / contrast
            n = max(int(shots), 1)
            sequence_variance = np.asarray([
                _binomial_variance_jeffreys(
                    int(np.clip(round(value * n), 0, n)), n)
                for value in populations
            ], dtype=float)
            reference_n = max(int(before.get("shots_per_state", reference_shots)), 1)
            ground_variance = _binomial_variance_jeffreys(
                int(np.clip(round(p_e_ground * reference_n), 0, reference_n)),
                reference_n)
            excited_variance = _binomial_variance_jeffreys(
                int(np.clip(round(p_e_excited * reference_n), 0, reference_n)),
                reference_n)
            gradient_ground = (normalized - 1.0) / contrast
            gradient_excited = -normalized / contrast
            normalized_se = np.sqrt(np.maximum(
                sequence_variance / contrast ** 2
                + gradient_ground ** 2 * ground_variance
                + gradient_excited ** 2 * excited_variance,
                0.0))
        else:
            normalized = np.full(len(depths), np.nan)
            normalized_se = np.full(len(depths), np.inf)
        targets = np.asarray([value % 2 for value in depths], dtype=float)
        errors = np.abs(normalized - targets)
        z = _simultaneous_z(
            len(depths), p.get("familywise_alpha", 0.05),
            p.get("confidence_sigma", 1.96))
        error_ucb = errors + z * normalized_se
        even = np.asarray([value % 2 == 0 for value in depths], dtype=bool)
        odd = ~even
        even_values = error_ucb[even]
        odd_values = error_ucb[odd]
        worst_even = (float(np.max(even_values[np.isfinite(even_values)]))
                      if np.any(np.isfinite(even_values)) else np.inf)
        worst_odd = (float(np.max(odd_values[np.isfinite(odd_values)]))
                     if np.any(np.isfinite(odd_values)) else np.inf)
        third_blob = float(before["third_blob_excess_ucb_95"])
        valid = bool(
            finite_contrast and drift_stable
            and np.all(np.isfinite(populations))
            and np.all(np.isfinite(error_ucb))
            and np.isfinite(third_blob))
        safe = bool(
            valid
            and worst_even <= float(p["operational_max_even_return_error"])
            and worst_odd <= float(p["operational_max_odd_inversion_error"])
            and third_blob <= float(p["max_third_blob_excess"]))
        row = dict(candidate)
        row.update({
            "fidelity": float(before["fidelity"]),
            "fidelity_se": float(before["fidelity_se"]),
            "fidelity_lcb_95": float(before["fidelity_lcb_95"]),
            "third_blob_excess_ucb": third_blob,
            "depths": np.asarray(depths, dtype=int),
            "observed_excited_fraction": populations,
            "normalized_excited_population": normalized,
            "normalized_population_se": normalized_se,
            "target_population": targets,
            "depth_error": errors, "depth_error_ucb": error_ucb,
            "max_even_return_error_ucb": worst_even,
            "max_odd_inversion_error_ucb": worst_odd,
            "binary_contrast": contrast,
            "calibration_drift": drift,
            "calibration_stable": drift_stable,
            "valid": valid, "operational_safe": safe,
            "leakage_safe": safe,
            "label": str(label),
            "failure": (None if valid else
                        "insufficient binary contrast or discriminator drift"),
        })
        return row

    @staticmethod
    def _prefer_longer_noninferior(aggregates, margin=0.003,
                                   max_mean_loss=0.010):
        """Among statistically tied fidelities, prefer longer/lower-power control."""
        if not aggregates:
            return None
        best = BasicAutoTuner._best_aggregate(aggregates)
        tied = []
        for row in aggregates:
            uncertainty = 1.96 * math.hypot(
                float(best.get("fidelity_se", np.inf)),
                float(row.get("fidelity_se", np.inf)))
            loss = float(best["fidelity"]) - float(row["fidelity"])
            if (loss <= uncertainty + float(margin)
                    and loss <= float(max_mean_loss)):
                tied.append(row)
        return max(tied or [best], key=lambda row: (
            float(row.get("sigma", 0.0)),
            -abs(float(row.get("qubit_pi_gain", np.inf))),
            -float(row.get("max_even_return_error_ucb", np.inf)),
            -float(row.get("max_odd_inversion_error_ucb", np.inf)),
            -float(row.get("third_blob_excess_ucb", np.inf)),
            float(row.get("fidelity_lcb_95", -np.inf))))

    @staticmethod
    def _duration_covered_shortlist(rows, limit):
        """Keep the best safe row per duration before filling by fidelity."""
        ranked = sorted(rows, key=lambda row: (
            float(row.get("fidelity_lcb_95", -np.inf)),
            float(row.get("fidelity", -np.inf))), reverse=True)
        limit = max(int(limit), 1)
        by_duration = {}
        for row in ranked:
            by_duration.setdefault(round(float(row["sigma"]), 9), row)
        shortlist = list(by_duration.values())[:limit]
        for row in ranked:
            if len(shortlist) >= limit:
                break
            if not any(_candidate_key(existing) == _candidate_key(row)
                       for existing in shortlist):
                shortlist.append(row)
        return shortlist

    def _operational_waveform_pool(self):
        return self._leakage_waveform_pool(limit=max(
            int(self.params["leakage"].get(
                "operational_max_candidate_waveforms", 3)), 1))

    def _stage_operational_leakage(self):
        """Optimize Gaussian duration and DRAG inside the operational safe set."""
        if not self._operational_leakage_active:
            return None
        p = self.params["leakage"]
        attempts = []
        safe_rows = []
        for waveform_index, waveform in enumerate(self._operational_waveform_pool()):
            incumbent_beta = float(waveform.get("qubit_drag_beta", 0.0))
            rows = []
            failures = []
            measured = set()
            consecutive_failures = 0
            abort_waveform = False
            for extension in range(max(int(p["operational_max_extensions"]), 1)):
                span = min(
                    float(p["operational_beta_span"]) * (1.7 ** extension),
                    float(p["operational_max_beta_span"]))
                betas = np.unique(np.round(np.r_[
                    np.linspace(
                        incumbent_beta - span, incumbent_beta + span,
                        max(int(p["operational_beta_points"]), 5)),
                    0.0, incumbent_beta,
                ], 8))
                for raw in self.rng.permutation(betas.size):
                    beta = float(betas[int(raw)])
                    if beta in measured:
                        continue
                    measured.add(beta)
                    candidate = _with_candidate(
                        waveform, qubit_drag_beta=beta)
                    try:
                        row = self._measure_operational_leakage_candidate(
                            candidate, int(p["operational_shots"]),
                            int(p["operational_reference_shots"]),
                            "operational waveform %d beta %+.5f"
                            % (waveform_index + 1, beta))
                    except KeyboardInterrupt:
                        raise
                    except Exception as exc:
                        consecutive_failures += 1
                        failures.append({
                            "qubit_drag_beta": beta,
                            "error": "%s: %s" % (type(exc).__name__, exc),
                        })
                        self._log(
                            "operational_leakage", "WARN",
                            "waveform %d beta %+.5f failed (%s: %s)"
                            % (waveform_index + 1, beta,
                               type(exc).__name__, exc))
                        if consecutive_failures >= int(
                                self.params["max_consecutive_point_failures"]):
                            abort_waveform = True
                            break
                        continue
                    consecutive_failures = 0
                    rows.append(row)
                if abort_waveform:
                    break
                safe_now = [row for row in rows if row["operational_safe"]]
                if safe_now:
                    best_safe = max(safe_now, key=lambda row: (
                        float(row["fidelity_lcb_95"]),
                        -float(row["max_even_return_error_ucb"]),
                        -float(row["max_odd_inversion_error_ucb"])))
                    measured_betas = np.asarray([
                        row["qubit_drag_beta"] for row in rows], dtype=float)
                    if (float(best_safe["qubit_drag_beta"])
                            > float(np.min(measured_betas)) + 1e-9
                            and float(best_safe["qubit_drag_beta"])
                            < float(np.max(measured_betas)) - 1e-9):
                        break
            attempts.append({
                "candidate": dict(waveform), "rows": rows,
                "failures": failures, "aborted": bool(abort_waveform),
            })
            safe_rows.extend(row for row in rows if row["operational_safe"])
        if not safe_rows:
            self.data["leakage"].update({
                "attempts": attempts, "optimized": False,
                "selection_safe": False, "verified": False,
                "failure": "no Gaussian candidate passed the operational screen",
            })
            raise RuntimeError(self.data["leakage"]["failure"])

        # Reserve duration coverage before filling by score.  Otherwise several
        # nearby beta values from the short/high-power winner can consume the whole
        # shortlist and prevent the intended longer/lower-power comparison.
        shortlist = self._duration_covered_shortlist(
            safe_rows, p["operational_selection_shortlist"])
        confirmations = self._confirm_candidates(
            shortlist, int(p["operational_selection_shots"]),
            int(p["operational_selection_blocks"]),
            "held-out operationally safe fidelity selection",
            add_to_history=True)
        screened_by_key = {_candidate_key(row): row for row in shortlist}
        for confirmation in confirmations:
            screened_row = screened_by_key.get(_candidate_key(confirmation), {})
            for key in ("max_even_return_error_ucb",
                        "max_odd_inversion_error_ucb",
                        "third_blob_excess_ucb", "operational_safe"):
                if key in screened_row:
                    confirmation[key] = screened_row[key]
        complete = self._confirmation_batch_complete(confirmations)
        selected_confirmation = self._prefer_longer_noninferior(
            confirmations, p["operational_fidelity_tie_margin"],
            p["operational_max_tie_fidelity_loss"])
        if selected_confirmation is None:
            raise RuntimeError("operational safe shortlist produced no confirmation")
        screened = next(
            row for row in shortlist
            if _candidate_key(row) == _candidate_key(selected_confirmation))
        chosen = dict(screened)
        chosen.update({
            "screening_fidelity": float(screened["fidelity"]),
            "screening_fidelity_se": float(screened["fidelity_se"]),
            "fidelity": float(selected_confirmation["fidelity"]),
            "fidelity_se": float(selected_confirmation["fidelity_se"]),
            "fidelity_lcb_95": float(selected_confirmation["fidelity_lcb_95"]),
            "confirmation_blocks": int(
                selected_confirmation["confirmation_blocks"]),
            "block_fidelities": selected_confirmation["block_fidelities"],
            "block_spread": float(selected_confirmation["block_spread"]),
            "selection_confirmation_complete": bool(complete),
        })
        self._leakage_selected_candidate = {
            key: chosen[key] for key in self.initial}
        self._adopt(chosen, "operational_leakage")
        self.data["leakage"].update({
            "attempts": attempts, "chosen": chosen,
            "optimized": True, "selection_safe": True,
            "selection_confirmations": confirmations,
            "selection_confirmation_complete": bool(complete),
            "verified": False, "failure": None,
        })
        return chosen

    def _stage_operational_leakage_verify(self):
        """Independently repeat every operational guard on the exact final tuple."""
        if not self._operational_leakage_active:
            return None
        p = self.params["leakage"]
        self._leakage_verified_candidate_key = None

        def verify(candidate, tag):
            rows, failures = [], []
            requested = max(int(p["operational_verify_blocks"]), 1)
            for block in range(requested):
                try:
                    rows.append(self._measure_operational_leakage_candidate(
                        candidate, int(p["operational_verify_shots"]),
                        int(p["operational_verify_shots"]),
                        "%s block %d" % (tag, block + 1)))
                except KeyboardInterrupt:
                    raise
                except Exception as exc:
                    failures.append({
                        "block": block + 1,
                        "error": "%s: %s" % (type(exc).__name__, exc),
                    })
            passed = bool(
                len(rows) == requested and not failures
                and all(row.get("operational_safe", False) for row in rows))
            return rows, failures, passed

        candidate = dict(self.working)
        rows, failures, passed = verify(candidate, "operational verification")
        used_fallback = False
        if (not passed and self._leakage_selected_candidate is not None
                and _candidate_key(candidate)
                != _candidate_key(self._leakage_selected_candidate)):
            candidate = dict(self._leakage_selected_candidate)
            rows, failures, passed = verify(
                candidate, "operational safe-seed fallback")
            used_fallback = True
            if passed:
                self.working = dict(candidate)
        worst_even = max((float(row.get(
            "max_even_return_error_ucb", np.inf)) for row in rows), default=np.inf)
        worst_odd = max((float(row.get(
            "max_odd_inversion_error_ucb", np.inf)) for row in rows), default=np.inf)
        worst_blob = max((float(row.get(
            "third_blob_excess_ucb", np.inf)) for row in rows), default=np.inf)
        self.data["leakage"].update({
            "verification": rows, "verified": bool(passed),
            "verification_failures": failures,
            "operational_verified": bool(passed),
            "verified_candidate_key": (
                list(_candidate_key(candidate)) if passed else None),
            "used_safe_seed_fallback": bool(used_fallback),
            "worst_even_return_error_ucb": worst_even,
            "worst_odd_inversion_error_ucb": worst_odd,
            "worst_third_blob_excess_ucb": worst_blob,
            "failure": (None if passed else
                        "fresh operational leakage-sensitive checks failed"),
        })
        if passed:
            self._leakage_verified_candidate_key = _candidate_key(candidate)
        return bool(passed)

    # ------------------------------------------------------- direct leakage constraint
    @staticmethod
    def _ef_pulse(gain, frequency, phase=0.0):
        return ("pulse_at", int(round(gain)), float(phase),
                float(frequency), "reference")

    @staticmethod
    def _reference_pulse(gain, frequency, phase=0.0):
        return ("pulse_at", int(round(gain)), float(phase),
                float(frequency), "reference")

    @staticmethod
    def _ge_pulse(candidate, phase=0.0):
        return ("pulse", int(round(candidate["qubit_pi_gain"])), float(phase))

    def _sequence_mean(self, candidate, sequence, shots, seq_gap_us=None):
        i, q = self._acquire_sequence(
            candidate, sequence, int(shots), seq_gap_us=seq_gap_us)
        i, q = np.asarray(i, dtype=float), np.asarray(q, dtype=float)
        n = min(i.size, q.size)
        if n < 10:
            raise RuntimeError("sequence acquisition returned fewer than 10 shots")
        i, q = i[:n], q[:n]
        return {
            "i": float(np.mean(i)), "q": float(np.mean(q)),
            "se_i": float(np.std(i, ddof=1) / math.sqrt(n)),
            "se_q": float(np.std(q, ddof=1) / math.sqrt(n)),
            "shots": int(n),
        }

    def _population_with_local_refs(self, candidate, sequence, shots,
                                    excited_sequence=None):
        """Project one sequence between immediately adjacent g/e IQ references."""
        ground = self._sequence_mean(candidate, [], shots)
        if excited_sequence is None:
            excited_sequence = [self._ge_pulse(candidate)]
        excited = self._sequence_mean(
            candidate, excited_sequence, shots)
        measured = self._sequence_mean(candidate, sequence, shots)
        delta = np.array([
            excited["i"] - ground["i"], excited["q"] - ground["q"]],
            dtype=float)
        target = np.array([
            measured["i"] - ground["i"], measured["q"] - ground["q"]],
            dtype=float)
        denominator = float(np.dot(delta, delta))
        if not np.isfinite(denominator) or denominator <= 0:
            return np.nan, np.inf
        population = float(np.dot(target, delta) / denominator)
        gradient_m = delta / denominator
        gradient_e = target / denominator - 2.0 * population * delta / denominator
        gradient_g = -gradient_m - gradient_e
        sigma_m = np.array([measured["se_i"], measured["se_q"]])
        sigma_e = np.array([excited["se_i"], excited["se_q"]])
        sigma_g = np.array([ground["se_i"], ground["se_q"]])
        variance = float(
            np.sum((gradient_m * sigma_m) ** 2)
            + np.sum((gradient_e * sigma_e) ** 2)
            + np.sum((gradient_g * sigma_g) ** 2))
        return population, float(math.sqrt(max(variance, 0.0)))

    def _interleaved_sequence_fractions(self, candidate, sequences, metrics, shots):
        """Measure every labelled sequence in four randomized drift-balanced blocks."""
        labels = list(sequences)
        each = max(10, int(math.ceil(float(shots) / 4.0)))
        acquired = {label: [[], []] for label in labels}
        schedule = labels * 4
        for raw in self.rng.permutation(len(schedule)):
            label = schedule[int(raw)]
            i, q = self._acquire_sequence(
                candidate, sequences[label], each)
            acquired[label][0].append(np.asarray(i, dtype=float))
            acquired[label][1].append(np.asarray(q, dtype=float))
        return {
            label: ground_fraction_with_discriminator(
                np.concatenate(acquired[label][0]),
                np.concatenate(acquired[label][1]), metrics)
            for label in labels
        }

    def _audit_reference_ge_gain(self, candidate, gain, shots, total_span):
        """Directly verify that one reference pulse inverts and two return."""
        harmonic = []
        for count in (0, 1, 2):
            sequence = ([self._reference_pulse(
                0, candidate["qubit_pi_freq"])] if count == 0 else
                [self._reference_pulse(
                    gain, candidate["qubit_pi_freq"])] * count)
            harmonic.append(self._sequence_mean(
                candidate, sequence, int(shots)))
        z = np.asarray([complex(row["i"], row["q"]) for row in harmonic])
        baseline = 0.5 * (z[0] + z[2])
        contrast = float(abs(z[1] - baseline))
        return_error = float(abs(z[2] - z[0]))
        noise = float(3.0 * math.sqrt(sum(
            row["se_i"] ** 2 + row["se_q"] ** 2 for row in harmonic)))
        p = self.params["leakage"]
        allowance = float(p["reference_max_return_fraction"]) * contrast + noise
        normalized_contrast = contrast / max(float(total_span), 1e-12)
        passed = bool(
            normalized_contrast >= float(p["reference_min_contrast"])
            and return_error <= allowance)
        return {
            "gain": int(round(gain)), "harmonic": harmonic,
            "contrast": contrast, "return_error": return_error,
            "return_allowance": allowance,
            "normalized_contrast": normalized_contrast,
            "passed": passed,
        }

    def _calibrate_reference_ge(self, candidate):
        """Calibrate a long narrow-bandwidth g-e pulse for independent qutrit SPAM."""
        p = self.params["leakage"]
        gains = self._integer_axis(
            0, int(p["reference_gain_max"]), int(p["reference_gain_points"]),
            lower=0, upper=32767)
        response = np.full(gains.size, np.nan + 1j * np.nan, dtype=complex)
        errors = np.full((gains.size, 2), np.inf, dtype=float)
        for raw in self.rng.permutation(gains.size):
            index = int(raw)
            sequence = [self._reference_pulse(
                gains[index], candidate["qubit_pi_freq"])]
            measured = self._sequence_mean(
                candidate, sequence, int(p["reference_rabi_shots"]))
            response[index] = complex(measured["i"], measured["q"])
            errors[index] = measured["se_i"], measured["se_q"]
        displacement = response - response[0]
        xy = np.column_stack([displacement.real, displacement.imag])
        xy -= np.mean(xy, axis=0)
        try:
            _u, _s, vh = np.linalg.svd(xy, full_matrices=False)
            direction = vh[0]
        except Exception:
            direction = np.array([1.0, 0.0])
        projection = displacement.real * direction[0] + displacement.imag * direction[1]
        rabi = fit_anchored_rabi(gains, projection)
        if (not rabi.get("ok")
                or float(rabi.get("r2", -np.inf))
                < float(p["reference_min_rabi_r2"])
                or not np.isfinite(rabi.get("pi_gain", np.nan))):
            raise RuntimeError(
                "long reference g-e pulse did not produce a coherent Rabi")
        gain = int(round(rabi["pi_gain"]))
        if gain <= 0 or gain >= int(p["reference_gain_max"]):
            raise RuntimeError("long reference g-e pi gain is outside its range")
        total_span = max(float(np.ptp(response.real)), float(np.ptp(response.imag)),
                         1e-12)
        audits = [self._audit_reference_ge_gain(
            candidate, gain, int(p["reference_rabi_shots"]), total_span)]
        if not audits[0]["passed"]:
            # A damped multi-period fit can lock to 3pi or another alias even with a
            # good global r2.  The physical requirement is simpler and stronger:
            # one pulse must invert and two identical pulses must return.  On audit
            # failure, directly test a small set of observed response maxima plus a
            # local neighborhood of the fit and select the lowest passing gain.
            displacement_size = np.abs(response - response[0])
            peaks, _properties = find_peaks(displacement_size)
            ranked_peaks = sorted(
                (int(index) for index in peaks if int(gains[index]) > 0),
                key=lambda index: float(displacement_size[index]), reverse=True)[:6]
            local = np.clip(np.rint(float(gain) * np.linspace(0.65, 1.35, 9)),
                            1, int(p["reference_gain_max"]) - 1).astype(int)
            rescue_gains = [int(gains[index]) for index in ranked_peaks]
            rescue_gains.extend(int(value) for value in local)
            rescue_gains = sorted(set(rescue_gains) - {int(gain)})
            for rescue_gain in rescue_gains:
                audits.append(self._audit_reference_ge_gain(
                    candidate, rescue_gain, int(p["reference_rabi_shots"]),
                    total_span))
            passing = [row for row in audits if row["passed"]]
            if passing:
                selected = min(passing, key=lambda row: row["gain"])
                gain = int(selected["gain"])
            else:
                selected = audits[0]
        else:
            selected = audits[0]
        if not selected["passed"]:
            raise RuntimeError(
                "long reference g-e 0/pi/2pi audit failed "
                "(relative contrast %.3f, return %.4g > %.4g)"
                % (selected["normalized_contrast"], selected["return_error"],
                   selected["return_allowance"]))
        return {
            "ge_reference_gain": gain,
            "reference_sigma_us": max(
                float(p["reference_sigma_us"]), float(candidate["sigma"])),
            "gains": gains, "response": response, "response_se": errors,
            "projection": projection, "rabi": rabi,
            "harmonic": selected["harmonic"],
            "harmonic_contrast": selected["contrast"],
            "harmonic_return_error": selected["return_error"],
            "harmonic_audits": audits,
            "harmonic_rescue_used": bool(gain != int(round(rabi["pi_gain"]))),
        }

    def _calibrate_ef_transition(self, candidate):
        """Find and coherently verify e-f with a g-e/e-f/g-e shelving witness."""
        p = self.params["leakage"]
        ge_reference = self._calibrate_reference_ge(candidate)
        ge = self._reference_pulse(
            ge_reference["ge_reference_gain"], candidate["qubit_pi_freq"])
        try:
            configured = float(self.input_cfg.get("qubit_ef_freq", np.nan))
        except (TypeError, ValueError):
            configured = np.nan
        alpha_prior = p.get("anharmonicity_prior_mhz")
        if alpha_prior is None:
            alpha_prior = self.input_cfg.get("qubit_anharmonicity_mhz", np.nan)
        try:
            alpha_prior = float(alpha_prior)
        except (TypeError, ValueError):
            alpha_prior = np.nan
        centre = (configured if np.isfinite(configured)
                  else float(candidate["qubit_pi_freq"]) + alpha_prior)
        if not np.isfinite(centre):
            raise RuntimeError(
                "direct leakage requires qubit_ef_freq or qubit_anharmonicity_mhz")
        def scan(grid):
            grid = np.asarray(grid, dtype=float)
            passes = np.full((2, grid.size), np.nan + 1j * np.nan, dtype=complex)
            orders = (range(grid.size), range(grid.size - 1, -1, -1))
            for pass_index, order in enumerate(orders):
                for index in order:
                    seq = [ge, self._ef_pulse(
                        p["ef_spec_gain"], grid[index]), ge]
                    measured = self._sequence_mean(
                        candidate, seq, int(p["ef_spec_shots"]))
                    passes[pass_index, index] = complex(
                        measured["i"], measured["q"])
            average = np.mean(passes, axis=0)
            retained = max(int(p.get("ef_feature_candidates", 8)), 3)
            combined = self._spectral_features(
                grid, average, max_candidates=retained)
            individual = [self._spectral_features(
                grid, passes[index], max_candidates=retained)
                for index in range(2)]
            return average, passes, combined, individual

        broad_frequencies = self._float_axis(
            centre, p["ef_span_mhz"], p["ef_points"], include=[centre])
        broad, broad_passes, broad_features, broad_individual = scan(
            broad_frequencies)
        if float(broad_features["best_snr"]) < float(p["ef_min_feature_snr"]):
            raise RuntimeError(
                "e-f shelving scan found no %.1f-sigma feature in %.1f +/- %.1f MHz"
                % (p["ef_min_feature_snr"], centre, p["ef_span_mhz"] / 2.0))
        try:
            broad_match = self._reproduced_spectral_seed(
                broad_frequencies, broad_features, broad_individual,
                p["ef_max_repeat_error_mhz"], p["ef_min_feature_snr"])
        except RuntimeError as exc:
            raise RuntimeError(
                "e-f broad-scan feature did not reproduce in opposed passes") from exc
        broad_seed = float(broad_match["frequency_mhz"])

        narrow_frequencies = self._float_axis(
            broad_seed, p["ef_narrow_span_mhz"], p["ef_narrow_points"],
            include=[broad_seed])
        narrow, narrow_passes, narrow_features, narrow_individual = scan(
            narrow_frequencies)
        try:
            narrow_match = self._reproduced_spectral_seed(
                narrow_frequencies, narrow_features, narrow_individual,
                p["ef_max_repeat_error_mhz"], p["ef_min_feature_snr"])
        except RuntimeError as exc:
            raise RuntimeError(
                "e-f shelving feature did not reproduce in the narrow confirmation"
                ) from exc
        ef_frequency = float(narrow_match["frequency_mhz"])
        if abs(ef_frequency - broad_seed) > float(p["ef_max_repeat_error_mhz"]):
            raise RuntimeError(
                "e-f shelving feature did not reproduce in the narrow confirmation")
        alpha = ef_frequency - float(candidate["qubit_pi_freq"])
        if alpha >= -5.0:
            raise RuntimeError(
                "candidate e-f line %.4f MHz gives non-transmon anharmonicity %.3f MHz"
                % (ef_frequency, alpha))

        gains = self._integer_axis(
            0, int(p["ef_gain_max"]), int(p["ef_gain_points"]),
            lower=0, upper=32767)
        populations = np.full(gains.size, np.nan)
        population_se = np.full(gains.size, np.inf)
        for raw in self.rng.permutation(gains.size):
            index = int(raw)
            sequence = [ge, self._ef_pulse(
                gains[index], ef_frequency), ge]
            populations[index], population_se[index] = \
                self._population_with_local_refs(
                    candidate, sequence, int(p["ef_rabi_shots"]),
                    excited_sequence=[ge])
        rabi = fit_anchored_rabi(gains, populations)
        if (not rabi.get("ok")
                or float(rabi.get("r2", -np.inf)) < float(p["ef_min_rabi_r2"])
                or not np.isfinite(rabi.get("pi_gain", np.nan))):
            raise RuntimeError("e-f candidate did not produce a coherent Rabi")
        ef_gain = int(round(rabi["pi_gain"]))
        if ef_gain <= 0 or ef_gain >= int(p["ef_gain_max"]):
            raise RuntimeError("e-f pi gain lies outside the authorized range")

        harmonic = []
        for count in (0, 1, 2):
            ef_sequence = ([self._ef_pulse(0, ef_frequency)] if count == 0
                           else [self._ef_pulse(
                               ef_gain, ef_frequency)] * count)
            sequence = [ge] + ef_sequence + [ge]
            harmonic.append(self._population_with_local_refs(
                candidate, sequence, int(p["ef_rabi_shots"]),
                excited_sequence=[ge]))
        baseline = 0.5 * (harmonic[0][0] + harmonic[2][0])
        contrast = abs(harmonic[1][0] - baseline)
        return_error = abs(harmonic[2][0] - harmonic[0][0])
        return_allowance = (
            float(p["ef_max_return_fraction"]) * contrast
            + 3.0 * math.hypot(harmonic[0][1], harmonic[2][1]))
        if (not np.isfinite(contrast)
                or contrast < float(p["ef_min_rabi_contrast"])
                or return_error > return_allowance):
            raise RuntimeError(
                "e-f 0/pi/2pi audit failed (contrast %.3f, return %.3f > %.3f)"
                % (contrast, return_error, return_allowance))
        calibration = {
            "ef_frequency": ef_frequency, "ef_gain": ef_gain,
            "anharmonicity_mhz": alpha,
            "ge_reference": ge_reference,
            "ge_reference_gain": ge_reference["ge_reference_gain"],
            "reference_sigma_us": ge_reference["reference_sigma_us"],
            "broad_frequencies_mhz": broad_frequencies,
            "broad_response": broad, "broad_passes": broad_passes,
            "broad_features": broad_features, "broad_match": broad_match,
            "narrow_frequencies_mhz": narrow_frequencies,
            "narrow_response": narrow, "narrow_passes": narrow_passes,
            "narrow_features": narrow_features, "narrow_match": narrow_match,
            "rabi_gains": gains, "rabi_population": populations,
            "rabi_population_se": population_se, "rabi": rabi,
            "harmonic": harmonic, "harmonic_contrast": float(contrast),
            "harmonic_return_error": float(return_error),
        }
        self._log(
            "leakage", "OK",
            "shelving-calibrated e-f %.4f MHz (anharmonicity %.3f MHz), "
            "e-f pi %d DAC" % (ef_frequency, alpha, ef_gain))
        return calibration

    def _leakage_response_calibration(self, candidate, ef_calibration, shots):
        """Measure the identity/shelving response matrix for prepared g/e/f."""
        p = self.params["leakage"]
        ig, qg, ie, qe = self._acquire_ss_pair(candidate, int(shots))
        metrics = step5_metrics(ig, qg, ie, qe)
        ge = self._reference_pulse(
            ef_calibration["ge_reference_gain"],
            candidate["qubit_pi_freq"])
        ef = self._ef_pulse(
            ef_calibration["ef_gain"], ef_calibration["ef_frequency"])
        preparation = {"g": [], "e": [ge], "f": [ge, ef]}
        sequences = {}
        for state in ("g", "e", "f"):
            sequences[(state, "identity")] = list(preparation[state])
            sequences[(state, "shelved")] = list(preparation[state]) + [ef, ge]
        fractions = self._interleaved_sequence_fractions(
            candidate, sequences, metrics, int(shots))
        calibration = {
            state: (
                fractions[(state, "identity")][0],
                fractions[(state, "identity")][1],
                fractions[(state, "shelved")][0],
                fractions[(state, "shelved")][1],
            ) for state in ("g", "e", "f")
        }
        condition_probe = solve_shelved_qutrit_population(
            calibration,
            (calibration["g"][0], calibration["g"][1]),
            (calibration["g"][2], calibration["g"][3]),
            p["max_response_condition"])
        identity_selectivity = float(
            calibration["g"][0]
            - max(calibration["e"][0], calibration["f"][0]))
        shelving_selectivity = float(
            calibration["f"][2]
            - max(calibration["g"][2], calibration["e"][2]))
        ok = bool(
            condition_probe.get("matrix_ok", False)
            and identity_selectivity >= float(p["min_identity_selectivity"])
            and shelving_selectivity >= float(p["min_shelving_selectivity"]))
        return {
            "ok": ok, "metrics": metrics, "calibration": calibration,
            "condition": float(condition_probe.get("condition", np.inf)),
            "response_matrix": condition_probe.get("response_matrix"),
            "response_matrix_se": condition_probe.get("response_matrix_se"),
            "identity_selectivity": identity_selectivity,
            "shelving_selectivity": shelving_selectivity,
            "reason": None if ok else "ill-conditioned or nonselective shelving",
        }

    def _leakage_target_population(self, candidate, sequence, response,
                                   ef_calibration, shots, seq_gap_us):
        """Interleave target identity/shelving shots and invert P(g/e/f)."""
        ge = self._reference_pulse(
            ef_calibration["ge_reference_gain"],
            candidate["qubit_pi_freq"])
        ef = self._ef_pulse(
            ef_calibration["ef_gain"], ef_calibration["ef_frequency"])
        sequences = {
            "identity": list(sequence),
            "shelved": list(sequence) + [ef, ge],
        }
        # Preserve the selected gap in both target arms.  The appended shelving pulses
        # use the same short gap, matching the response calibration convention.
        metrics = response["metrics"]
        labels = list(sequences)
        each = max(10, int(math.ceil(float(shots) / 4.0)))
        acquired = {label: [[], []] for label in labels}
        schedule = labels * 4
        for raw in self.rng.permutation(len(schedule)):
            label = schedule[int(raw)]
            i, q = self._acquire_sequence(
                candidate, sequences[label], each, seq_gap_us=seq_gap_us)
            acquired[label][0].append(np.asarray(i, dtype=float))
            acquired[label][1].append(np.asarray(q, dtype=float))
        fractions = {
            label: ground_fraction_with_discriminator(
                np.concatenate(acquired[label][0]),
                np.concatenate(acquired[label][1]), metrics)
            for label in labels
        }
        solved = solve_shelved_qutrit_population(
            response["calibration"], fractions["identity"], fractions["shelved"],
            self.params["leakage"]["max_response_condition"])
        solved["ground_fractions"] = fractions
        return solved

    def _measure_leakage_candidate(self, candidate, ef_calibration, shots,
                                   reference_shots, label):
        """Measure step-5 fidelity, third-cloud excess, and direct/amplified P(f)."""
        p = self.params["leakage"]
        candidate = dict(candidate)
        direct = self._measure_candidate(
            candidate, int(reference_shots), "%s direct step-5" % label)
        response = self._leakage_response_calibration(
            candidate, ef_calibration, int(reference_shots))
        row = dict(candidate)
        row.update({
            "fidelity": float(direct["fidelity"]),
            "fidelity_se": float(direct["fidelity_se"]),
            "fidelity_lcb_95": float(direct["fidelity_lcb_95"]),
            "third_blob_excess": float(direct["third_blob_excess"]),
            "third_blob_excess_se": float(direct["third_blob_excess_se"]),
            "third_blob_excess_ucb": float(direct["third_blob_excess_ucb_95"]),
            "ground_outlier_frac": float(direct["ground_outlier_frac"]),
            "excited_outlier_frac": float(direct["excited_outlier_frac"]),
            "response": response, "witnesses": [], "label": str(label),
        })
        if not response.get("ok", False):
            row.update(valid=False, leakage_safe=False,
                       single_p2_ucb=np.inf, amplified_p2_ucb=np.inf,
                       failure=response.get("reason"))
            return row
        depths = [int(value) for value in p["depths"]]
        phases = [float(value) for value in p["gap_phases"]]
        z = _simultaneous_z(
            len(depths) * len(phases), p.get("familywise_alpha", 0.05),
            p.get("confidence_sigma", 1.96))
        alpha = float(ef_calibration["anharmonicity_mhz"])
        base_gap = float(self.input_cfg.get("seq_gap_us", 0.01))
        period_us = 1.0 / max(abs(alpha), 1e-12)
        for depth in depths:
            for phase in phases:
                gap = base_gap + phase * period_us
                sequence = [self._ge_pulse(candidate)] * depth
                solved = self._leakage_target_population(
                    candidate, sequence, response, ef_calibration,
                    int(shots), gap)
                solved.update({
                    "depth": int(depth), "gap_phase": float(phase),
                    "gap_us": float(gap),
                })
                row["witnesses"].append(solved)
        if not row["witnesses"] or not all(
                witness.get("ok", False) for witness in row["witnesses"]):
            row.update(valid=False, leakage_safe=False,
                       single_p2_ucb=np.inf, amplified_p2_ucb=np.inf,
                       failure="one or more qutrit inversions failed")
            return row
        for witness in row["witnesses"]:
            witness["p2_ucb"] = float(np.clip(
                witness["p2"] + z * witness["p2_se"], 0.0, 1.0))
        direct_witnesses = [w for w in row["witnesses"] if w["depth"] == 1]
        amplified_witnesses = [w for w in row["witnesses"] if w["depth"] > 1]
        single_ucb = max((w["p2_ucb"] for w in direct_witnesses), default=np.inf)
        amplified_ucb = max(
            (w["p2_ucb"] for w in amplified_witnesses), default=single_ucb)
        finite = bool(
            np.isfinite(row["fidelity"]) and np.isfinite(row["fidelity_se"])
            and np.isfinite(single_ucb) and np.isfinite(amplified_ucb))
        safe = bool(
            finite
            and single_ucb <= float(p["max_single_p2"])
            and amplified_ucb <= float(p["max_amplified_p2"])
            and row["third_blob_excess_ucb"]
            <= float(p["max_third_blob_excess"]))
        row.update({
            "valid": finite, "leakage_safe": safe,
            "single_p2_ucb": float(single_ucb),
            "amplified_p2_ucb": float(amplified_ucb),
            "confidence_sigma": float(z), "failure": None,
        })
        return row

    def _leakage_waveform_pool(self, limit=None):
        """High-fidelity distinct control waveforms, including longer fallbacks."""
        if limit is None:
            limit = self.params["leakage"]["max_candidate_waveforms"]
        limit = max(int(limit), 1)

        def physical(row):
            # Compare control waveforms under one fixed readout/reset calibration.
            # Pulling each historical row's old readout tuple would mix raw feedback
            # thresholds and make duration look better or worse because of SPAM drift.
            candidate = dict(self.working)
            for key in ("qubit_freq", "qubit_pi_freq", "qubit_pi_gain", "sigma",
                        "qubit_drag_beta"):
                candidate[key] = row[key]
            return candidate

        def control_key(row):
            return (
                round(float(row["qubit_pi_freq"]), 7),
                int(round(row["qubit_pi_gain"])),
                round(float(row["sigma"]), 9),
            )

        pool = [dict(self.working)]
        seen = {control_key(self.working)}
        rows = list(self.data.get("final_candidates", [])) + list(self._confirmed)
        ranked = sorted(rows, key=lambda row: (
            float(row.get("fidelity_lcb_95", -np.inf)),
            float(row.get("fidelity", -np.inf))), reverse=True)
        # First preserve the best candidate at every longer duration.  Leakage rises
        # rapidly for short/high-amplitude pulses, so a pure global-fidelity shortlist
        # can otherwise omit the most important recovery direction.
        current_sigma = float(self.working["sigma"])
        by_sigma = {}
        for row in ranked:
            if not all(key in row for key in self.initial):
                continue
            sigma = round(float(row["sigma"]), 9)
            by_sigma.setdefault(sigma, row)
        longer = [row for sigma, row in sorted(by_sigma.items())
                  if sigma > current_sigma + 1e-10]
        slots = max(limit - 1, 0)
        if len(longer) > slots > 0:
            indices = np.unique(np.rint(np.linspace(
                0, len(longer) - 1, slots)).astype(int))
            longer = [longer[int(index)] for index in indices]
        for row in longer + ranked:
            if len(pool) >= limit:
                break
            if not all(key in row for key in self.initial):
                continue
            candidate = physical(row)
            key = control_key(candidate)
            if key in seen:
                continue
            seen.add(key)
            pool.append(candidate)
        return pool

    def _stage_leakage(self):
        """Choose the highest-fidelity waveform satisfying direct leakage bounds."""
        if not self._leakage_active:
            self._log("leakage", "SKIP",
                      "no e-f frequency/anharmonicity prior; direct P(f) inactive")
            return None
        p = self.params["leakage"]
        attempts = []
        for waveform_index, waveform in enumerate(self._leakage_waveform_pool()):
            try:
                ef_calibration = self._calibrate_ef_transition(waveform)
            except Exception as exc:
                attempts.append({
                    "candidate": dict(waveform), "ef_calibration": None,
                    "rows": [], "chosen": None,
                    "failure": "%s: %s" % (type(exc).__name__, exc),
                })
                self._log(
                    "leakage", "WARN",
                    "waveform %d e-f calibration failed (%s: %s)"
                    % (waveform_index + 1, type(exc).__name__, exc))
                continue
            incumbent_beta = float(waveform.get("qubit_drag_beta", 0.0))
            rows = []

            def measure(beta, suffix):
                candidate = _with_candidate(
                    waveform, qubit_drag_beta=float(beta))
                row = self._measure_leakage_candidate(
                    candidate, ef_calibration, int(p["shots"]),
                    int(p["reference_shots"]),
                    "leakage waveform %d %s" % (waveform_index + 1, suffix))
                rows.append(row)
                self._log(
                    "leakage", "OK" if row.get("leakage_safe") else "WARN",
                    "waveform %d beta %+.5f -> F %.4f +/- %.4f, "
                    "P(f) UCB one/amplified %s/%s, third-cloud excess UCB %.4f%s"
                    % (waveform_index + 1, beta,
                       row.get("fidelity", np.nan),
                       row.get("fidelity_se", np.inf),
                       ("%.4f" % row["single_p2_ucb"])
                       if np.isfinite(row.get("single_p2_ucb", np.inf)) else "FAILED",
                       ("%.4f" % row["amplified_p2_ucb"])
                       if np.isfinite(row.get("amplified_p2_ucb", np.inf)) else "FAILED",
                       row.get("third_blob_excess_ucb", np.inf),
                       " [SAFE]" if row.get("leakage_safe") else ""))
                return row

            incumbent = measure(incumbent_beta, "incumbent")
            # Safety is a constraint, not the optimization objective.  Even a safe
            # incumbent has not established the best fidelity over beta, so always run
            # the first two-sided DRAG map.  Further span extensions are needed only
            # while no safe point exists or the best safe point remains on a boundary.
            measured = {round(incumbent_beta, 8)}
            for extension in range(max(int(p["max_extensions"]), 1)):
                span = min(float(p["beta_span"]) * (1.7 ** extension),
                           float(p["max_beta_span"]))
                values = list(np.linspace(
                    incumbent_beta - span, incumbent_beta + span,
                    max(int(p["beta_points"]), 5)))
                values.extend((0.0, incumbent_beta))
                values = np.unique(np.round(values, 8))
                for raw in self.rng.permutation(values.size):
                    beta = float(values[int(raw)])
                    if round(beta, 8) in measured:
                        continue
                    measured.add(round(beta, 8))
                    measure(beta, "scan %d" % (extension + 1))
                safe_now = [row for row in rows if row.get("leakage_safe")]
                if safe_now:
                    best_safe = max(safe_now, key=lambda row: (
                        float(row["fidelity_lcb_95"]),
                        -float(row["single_p2_ucb"]),
                        -float(row["amplified_p2_ucb"])))
                    beta_values = np.asarray([row["qubit_drag_beta"]
                                              for row in rows], dtype=float)
                    if (best_safe["qubit_drag_beta"]
                            > np.min(beta_values) + 1e-9
                            and best_safe["qubit_drag_beta"]
                            < np.max(beta_values) - 1e-9):
                        break
            safe_rows = [row for row in rows if row.get("leakage_safe")]
            if safe_rows:
                chosen = max(safe_rows, key=lambda row: (
                    float(row["fidelity_lcb_95"]),
                    -float(row["single_p2_ucb"]),
                    -float(row["amplified_p2_ucb"])))
            else:
                valid_rows = [row for row in rows if row.get("valid")]
                if valid_rows:
                    def violation(row):
                        return max(
                            float(row["single_p2_ucb"]) / float(p["max_single_p2"]),
                            float(row["amplified_p2_ucb"])
                            / float(p["max_amplified_p2"]),
                            float(row["third_blob_excess_ucb"])
                            / float(p["max_third_blob_excess"]),
                        )
                    chosen = min(valid_rows, key=lambda row: (
                        violation(row), -float(row["fidelity_lcb_95"])))
                else:
                    chosen = None
            attempts.append({
                "candidate": dict(waveform),
                "ef_calibration": ef_calibration,
                "rows": rows, "chosen": chosen, "failure": None,
            })
        feasible = [attempt for attempt in attempts
                    if isinstance(attempt.get("chosen"), dict)
                    and attempt["chosen"].get("leakage_safe", False)]
        if feasible:
            selected_attempt = max(feasible, key=lambda attempt: (
                float(attempt["chosen"]["fidelity_lcb_95"]),
                -float(attempt["chosen"]["single_p2_ucb"]),
                -float(attempt["chosen"]["amplified_p2_ucb"])))
        else:
            measured = [attempt for attempt in attempts
                        if attempt.get("chosen") is not None]
            if not measured:
                self.data["leakage"].update({
                    "attempts": attempts, "optimized": False,
                    "verified": False,
                    "failure": "no waveform produced a valid direct leakage estimate",
                })
                raise RuntimeError(self.data["leakage"]["failure"])
            selected_attempt = min(measured, key=lambda attempt: (
                max(
                    float(attempt["chosen"].get("single_p2_ucb", np.inf))
                    / float(p["max_single_p2"]),
                    float(attempt["chosen"].get("amplified_p2_ucb", np.inf))
                    / float(p["max_amplified_p2"]),
                    float(attempt["chosen"].get(
                        "third_blob_excess_ucb", np.inf))
                    / float(p["max_third_blob_excess"])),
                -float(attempt["chosen"].get("fidelity_lcb_95", -np.inf))))
        chosen = selected_attempt["chosen"]

        # Beta/duration screening compares many noisy fidelities.  Replaying the top
        # safe physical tuples in randomized round-robin blocks removes that winner's
        # curse and prevents slow drift from favoring whichever waveform ran first.
        # Direct leakage is independently re-audited after all subsequent refinements.
        safe_pairs = [
            (attempt, row) for attempt in attempts for row in attempt.get("rows", [])
            if row.get("leakage_safe", False)
        ]
        selection_confirmations = []
        selection_complete = False
        if safe_pairs:
            ranked_pairs = sorted(safe_pairs, key=lambda pair: (
                float(pair[1].get("fidelity_lcb_95", -np.inf)),
                float(pair[1].get("fidelity", -np.inf))), reverse=True)
            selected_pairs = ranked_pairs[:max(int(p["selection_shortlist"]), 1)]
            try:
                selection_confirmations = self._confirm_candidates(
                    [row for _attempt, row in selected_pairs],
                    int(p["selection_fidelity_shots"]),
                    int(p["selection_fidelity_blocks"]),
                    "held-out leakage-feasible fidelity selection",
                    add_to_history=True)
                selection_complete = self._confirmation_batch_complete(
                    selection_confirmations)
                confirmed = self._best_aggregate(selection_confirmations)
                if confirmed is not None:
                    key = _candidate_key(confirmed)
                    pair = next((pair for pair in selected_pairs
                                 if _candidate_key(pair[1]) == key), None)
                    if pair is not None:
                        selected_attempt, screened = pair
                        chosen = dict(screened)
                        chosen.update({
                            "screening_fidelity": float(screened["fidelity"]),
                            "screening_fidelity_se": float(screened["fidelity_se"]),
                            "fidelity": float(confirmed["fidelity"]),
                            "fidelity_se": float(confirmed["fidelity_se"]),
                            "fidelity_lcb_95": float(confirmed["fidelity_lcb_95"]),
                            "confirmation_blocks": int(
                                confirmed["confirmation_blocks"]),
                            "block_fidelities": confirmed["block_fidelities"],
                            "block_spread": float(confirmed["block_spread"]),
                            "selection_confirmation_complete": bool(
                                selection_complete),
                        })
                        selected_attempt["chosen"] = chosen
            except Exception as exc:
                self._log(
                    "leakage", "WARN",
                    "held-out feasible-fidelity comparison failed (%s: %s); "
                    "retaining the best screened safe tuple for later final replay"
                    % (type(exc).__name__, exc))
        self._leakage_selected_candidate = {
            key: chosen[key] for key in self.initial}
        self._leakage_ef_calibration = selected_attempt["ef_calibration"]
        self._adopt(chosen, "leakage")
        self.data["leakage"].update({
            "attempts": attempts, "chosen": chosen,
            "ef_calibration": self._leakage_ef_calibration,
            "direct_p2_measured": True,
            "selection_confirmations": selection_confirmations,
            "selection_confirmation_complete": bool(selection_complete),
            "optimized": True, "verified": False,
            "selection_safe": bool(chosen.get("leakage_safe", False)),
            "failure": (None if chosen.get("leakage_safe") else
                        "no measured waveform met every leakage constraint"),
        })
        if chosen.get("leakage_safe"):
            self._log(
                "leakage", "OK",
                "leakage-constrained winner retains F %.4f with one-pulse/amplified "
                "P(f) UCB %.4f/%.4f and third-cloud excess UCB %.4f"
                % (chosen["fidelity"], chosen["single_p2_ucb"],
                   chosen["amplified_p2_ucb"], chosen["third_blob_excess_ucb"]))
        else:
            self._log(
                "leakage", "WARN",
                "no waveform passed every leakage bound; retaining the least-violating "
                "measured candidate for reporting, but automatic writes are blocked")
        return chosen

    def _stage_leakage_verify(self):
        """Fresh independent leakage blocks after all post-DRAG control refinements."""
        if not self._leakage_active or self._leakage_ef_calibration is None:
            return None
        p = self.params["leakage"]
        self._leakage_verified_candidate_key = None

        def verify(candidate, tag):
            rows = []
            for block in range(max(int(p["verify_blocks"]), 1)):
                rows.append(self._measure_leakage_candidate(
                    candidate, self._leakage_ef_calibration,
                    int(p["verify_shots"]), int(p["verify_shots"]),
                    "%s block %d" % (tag, block + 1)))
            passed = bool(
                len(rows) == max(int(p["verify_blocks"]), 1)
                and all(row.get("valid") and row.get("leakage_safe")
                        for row in rows))
            return rows, passed

        candidate = dict(self.working)
        rows, passed = verify(candidate, "leakage verification")
        used_fallback = False
        if (not passed and self._leakage_selected_candidate is not None
                and _candidate_key(candidate)
                != _candidate_key(self._leakage_selected_candidate)):
            self._log(
                "leakage_verify", "WARN",
                "post-leakage coherent refinement violated the leakage constraint; "
                "restoring and independently replaying the measured safe seed")
            candidate = dict(self._leakage_selected_candidate)
            rows, passed = verify(candidate, "leakage safe-seed fallback")
            used_fallback = True
            if passed:
                self.working = dict(candidate)
        worst_single = max(
            (float(row.get("single_p2_ucb", np.inf)) for row in rows),
            default=np.inf)
        worst_amplified = max(
            (float(row.get("amplified_p2_ucb", np.inf)) for row in rows),
            default=np.inf)
        worst_blob = max(
            (float(row.get("third_blob_excess_ucb", np.inf)) for row in rows),
            default=np.inf)
        self.data["leakage"].update({
            "verification": rows, "verified": bool(passed),
            "direct_verified": bool(passed),
            "direct_p2_measured": True,
            "verified_candidate_key": (
                list(_candidate_key(candidate)) if passed else None),
            "used_safe_seed_fallback": bool(used_fallback),
            "worst_single_p2_ucb": worst_single,
            "worst_amplified_p2_ucb": worst_amplified,
            "worst_third_blob_excess_ucb": worst_blob,
            "failure": (None if passed else
                        "fresh leakage verification exceeded a hard constraint"),
        })
        if passed:
            self._leakage_verified_candidate_key = _candidate_key(candidate)
        self._log(
            "leakage_verify", "OK" if passed else "WARN",
            "%d fresh blocks: worst P(f) UCB one/amplified %s/%s, "
            "third-cloud excess UCB %s -- %s"
            % (len(rows),
               "%.4f" % worst_single if np.isfinite(worst_single) else "FAILED",
               "%.4f" % worst_amplified
               if np.isfinite(worst_amplified) else "FAILED",
               "%.4f" % worst_blob if np.isfinite(worst_blob) else "FAILED",
               "PASS" if passed else "WRITE BLOCKED"))
        return bool(passed)

    def _stage_final_constrained(self):
        """Exact step-5 replay of only the leakage-screened physical tuple."""
        return self._stage_final_current_tuple(
            "final exact leakage-screened step-5 replay",
            "leakage_constrained", "final_safe")

    def _stage_final_feedback(self):
        """Exact replay after a fresh active-reset threshold/loop validation."""
        return self._stage_final_current_tuple(
            "final exact feedback-reset step-5 replay",
            "feedback_validated", "final_feedback")

    def _stage_final_current_tuple(self, label, replay_kind, log_stage):
        # Fail closed: an exception in this replay must not leave the completion flag
        # or provenance from the earlier unconstrained final comparison in force.
        self._final_replay_completed = False
        self._final_replay_kind = None
        p = self.params["final"]
        candidate = dict(self.working)
        finals = self._confirm_candidates(
            [candidate], p["shots"], p["blocks"], label,
            add_to_history=True)
        best = self._best_aggregate(finals)
        self._adopt(best, log_stage)
        self.data["final_candidates"] = finals
        self._final_replay_completed = self._confirmation_batch_complete(finals)
        self._final_replay_kind = (
            str(replay_kind) if self._final_replay_completed else None)
        self.data["final_confirmation_complete"] = bool(
            self._final_replay_completed)
        return best

    def _current_best_for_partial_run(self):
        pool = list(self._confirmed)
        if self._archive:
            # Completed individual measurements are real evidence even when an
            # interrupt prevented their surrounding grid/confirmation from finishing.
            # They are explicitly labeled unconfirmed and can never become eligible.
            observed = max(self._archive, key=lambda row: (
                float(row.get("fidelity_lcb_95", -np.inf)),
                float(row.get("fidelity", -np.inf))))
            pool.append(self._aggregate(
                observed, [observed], "partial best direct measurement (unconfirmed)"))
        return self._best_aggregate(pool)

    def _stage_final(self):
        self._final_replay_completed = False
        self._final_replay_kind = None
        p = self.params["final"]
        ranked = sorted(
            self._confirmed,
            key=lambda row: (float(row.get("fidelity_lcb_95", -np.inf)),
                             float(row.get("fidelity", -np.inf))), reverse=True)
        raw_ranked = sorted(
            self._archive,
            key=lambda row: (float(row.get("fidelity_lcb_95", -np.inf)),
                             float(row.get("fidelity", -np.inf))), reverse=True)

        def physical_candidate(row):
            return {key: row[key] for key in self.initial}

        # A contender whose confirmation blocks all suffered transient faults is still
        # present in the raw archive.  Re-introduce the top raw measurements here; a
        # false coarse maximum is harmless because this final replay is fresh and held
        # out, while omitting it could permanently lose the correct Rabi basin.
        candidates = [physical_candidate(row)
                      for row in ranked[:int(p["top_candidates"])]]
        candidates.extend(dict(entry["candidate"])
                          for entry in self._unconfirmed_contenders)
        candidates.extend(physical_candidate(row)
                          for row in raw_ranked[:int(p["top_candidates"])])
        candidates.extend([dict(self.working), dict(self.initial)])
        candidates = _unique_candidates(candidates)
        if not candidates:
            raise RuntimeError("no measured candidate is available for final replay")
        finals = self._confirm_candidates(
            candidates, p["shots"], p["blocks"], "final exact step-5 replay",
            add_to_history=True)
        # All final records have identical shots and block count, so comparing their
        # lower confidence bounds is fair and resistant to a one-block fluctuation.
        # Protect the final fine-frequency/AAE tuple when its one-pulse score is
        # statistically noninferior: a one-pulse histogram is insensitive to the small
        # coherent errors that those amplified sequences were designed to expose.
        selection_finals = list(finals)
        if self._operational_leakage_active or self._leakage_active:
            threshold = float(self.params["leakage"]["max_third_blob_excess"])
            safe_finals = [row for row in finals
                           if float(row.get(
                               "third_blob_excess_ucb", np.inf)) <= threshold]
            if safe_finals:
                selection_finals = safe_finals
        direct_best = self._best_aggregate(selection_finals)
        best = self._noninferior_seed(
            selection_finals, self.working, direct_best, margin=0.003)
        self._adopt(best, "final")
        self.data["final_candidates"] = finals
        self._final_replay_completed = self._confirmation_batch_complete(finals)
        self._final_replay_kind = (
            "unconstrained" if self._final_replay_completed else None)
        self.data["final_confirmation_complete"] = bool(
            self._final_replay_completed)
        return best

    def _estimate_default_measurement_repetitions(self):
        """Conservative workload estimate used only for the upfront operator ETA."""
        p = self.params
        total = 0
        total += 2 * int(p["baseline"]["shots"]) * int(p["baseline"]["blocks"])
        if p["resonator"].get("enabled", True):
            total += int(p["resonator"]["shots"]) * (
                2 * int(p["resonator"]["points"])
                + int(p["resonator"]["wide_points"]))
        if p["spectroscopy"].get("enabled", True):
            total += int(p["spectroscopy"]["shots"]) * (
                int(p["spectroscopy"]["local_points"])
                + int(p["spectroscopy"]["wide_points"]))
        if p["iq_rabi"].get("enabled", True):
            basins = 1 + int(p["spectroscopy"].get("max_candidates", 2))
            total += int(p["iq_rabi"]["shots"]) * (
                basins * int(p["iq_rabi"]["freq_points_per_candidate"])
                * int(p["iq_rabi"]["gain_points"])
                + int(p["iq_rabi"]["fine_gain_points"]))
        r = p["rough_single_shot"]
        rabi_capacity = max(
            int(p["iq_rabi"].get("shortlist", 4)),
            1 + int(p["spectroscopy"].get("max_candidates", 3)))
        total += (2 * rabi_capacity * int(r["freq_points"])
                  * int(r["gain_points"]) * int(r["coarse_shots"]))
        total += (2 * int(r["shots"]) * int(r["blocks"])
                  * (rabi_capacity + 2))
        for _ in range(2):
            f = p["fine_frequency"]
            if f.get("enabled", True):
                total += 2 * int(f["calibration_shots"])
                total += int(f["points"]) * int(f["shots"])
                total += 4 * int(f["confirm_shots"]) * int(f["confirm_blocks"])
        parity = p["parity_chevron"]
        if parity.get("enabled", True):
            total += 2 * max(int(parity["shots"]), 300)
            total += (len(parity["pulse_counts"]) * int(parity["freq_points"])
                      * int(parity["gain_points"]) * int(parity["shots"]))
            total += 4 * int(parity["confirm_shots"]) * int(parity["confirm_blocks"])
        readout = p["readout"]
        if readout.get("enabled", True):
            total += (2 * int(readout["freq_points"]) * int(readout["gain_points"])
                      * int(readout["shots"]))
            total += (2 * (int(readout["shortlist"]) + 1)
                      * int(readout["confirm_shots"]) * int(readout["confirm_blocks"]))
            # Local readout replay after direct/amplified control selection.
            total += (2 * int(readout["local_freq_points"])
                      * int(readout["local_gain_points"]) * int(readout["shots"]))
            total += (2 * (int(readout["shortlist"]) + 1)
                      * int(readout["confirm_shots"]) * int(readout["confirm_blocks"]))
        length = p["readout_length"]
        if length.get("enabled", True):
            total += (2 * (len(length["values_us"]) + 1)
                      * int(length["freq_points"]) * int(length["gain_points"])
                      * int(length["shots"]))
            total += (2 * (int(length["shortlist"]) + 1)
                      * int(length["confirm_shots"]) * int(length["confirm_blocks"]))
            total += (2 * int(readout["local_freq_points"])
                      * int(readout["local_gain_points"]) * int(readout["shots"]))
            total += (2 * (int(readout["shortlist"]) + 1)
                      * int(readout["confirm_shots"]) * int(readout["confirm_blocks"]))
        qubit = p["qubit"]
        if qubit.get("enabled", True):
            total += (2 * int(qubit["freq_points"]) * int(qubit["gain_points"])
                      * int(qubit["shots"]))
            total += (2 * (int(qubit["shortlist"]) + 1)
                      * int(qubit["confirm_shots"]) * int(qubit["confirm_blocks"]))
        duration = p["pulse_duration"]
        if duration.get("enabled", True):
            total += (2 * (len(duration["sigma_values_us"]) + 1)
                      * int(duration["freq_points"]) * int(duration["gain_points"])
                      * int(duration["shots"]))
            total += (2 * (int(duration["shortlist"]) + 1)
                      * int(duration["confirm_shots"]) * int(duration["confirm_blocks"]))
        if p.get("coordinate_descent_repeat", True):
            total += (2 * int(readout["local_freq_points"])
                      * int(readout["local_gain_points"]) * int(readout["shots"]))
            total += (2 * (int(readout["shortlist"]) + 1)
                      * int(readout["confirm_shots"]) * int(readout["confirm_blocks"]))
            total += (2 * int(qubit["local_freq_points"])
                      * int(qubit["local_gain_points"]) * int(qubit["shots"]))
            total += (2 * (int(qubit["shortlist"]) + 1)
                      * int(qubit["confirm_shots"]) * int(qubit["confirm_blocks"]))
        amplified = p["amplified_error"]
        if amplified.get("enabled", True):
            total += 2 * int(amplified["calibration_shots"])
            total += (len(amplified["pulse_counts"])
                      * int(amplified["freq_points"])
                      * int(amplified["gain_points"]) * int(amplified["shots"]))
            total += 4 * int(amplified["confirm_shots"]) * int(amplified["confirm_blocks"])
        if self._leakage_active:
            leak = p["leakage"]
            # Nominal constrained search: independently calibrate g-e/e-f and run a
            # complete initial beta map for every retained duration.  Boundary span
            # extensions and recovery after transient backend faults remain extra.
            waveform_count = max(int(leak["max_candidate_waveforms"]), 1)
            calibration_point = (
                2 * (int(leak["ef_points"]) + int(leak["ef_narrow_points"]))
                * int(leak["ef_spec_shots"])
                + (int(leak["reference_gain_points"]) + 3)
                * int(leak["reference_rabi_shots"])
                + 3 * (int(leak["ef_gain_points"]) + 3)
                * int(leak["ef_rabi_shots"]))
            per_point = (4 * 6 * int(math.ceil(
                float(leak["reference_shots"]) / 4.0))
                         + 2 * int(leak["reference_shots"])
                         + 8 * len(leak["depths"]) * len(leak["gap_phases"])
                         * int(math.ceil(float(leak["shots"]) / 4.0)))
            beta_points = max(int(leak["beta_points"]), 5) + 1
            total += waveform_count * (
                calibration_point + beta_points * per_point)
            total += (2 * int(leak["selection_shortlist"])
                      * int(leak["selection_fidelity_shots"])
                      * int(leak["selection_fidelity_blocks"]))
            verify_point = (4 * 6 * int(math.ceil(
                float(leak["verify_shots"]) / 4.0))
                            + 2 * int(leak["verify_shots"])
                            + 8 * len(leak["depths"]) * len(leak["gap_phases"])
                            * int(math.ceil(float(leak["verify_shots"]) / 4.0)))
            total += int(leak["verify_blocks"]) * verify_point
            # Re-close coordinates after DRAG/duration selection, then replay the
            # exact safe tuple.  These are real planned stages, not optimistic extras.
            total += (2 * int(qubit["local_freq_points"])
                      * int(qubit["local_gain_points"]) * int(qubit["shots"]))
            total += (2 * (int(qubit["shortlist"]) + 1)
                      * int(qubit["confirm_shots"]) * int(qubit["confirm_blocks"]))
            total += 2 * int(f["calibration_shots"])
            total += int(f["points"]) * int(f["shots"])
            total += 4 * int(f["confirm_shots"]) * int(f["confirm_blocks"])
            total += 2 * int(amplified["calibration_shots"])
            total += (len(amplified["pulse_counts"])
                      * int(amplified["freq_points"])
                      * int(amplified["gain_points"])
                      * int(amplified["shots"]))
            total += (4 * int(amplified["confirm_shots"])
                      * int(amplified["confirm_blocks"]))
            total += (2 * int(readout["local_freq_points"])
                      * int(readout["local_gain_points"])
                      * int(readout["shots"]))
            total += (2 * (int(readout["shortlist"]) + 1)
                      * int(readout["confirm_shots"])
                      * int(readout["confirm_blocks"]))
        elif self._operational_leakage_active:
            leak = p["leakage"]
            waveform_count = max(int(
                leak["operational_max_candidate_waveforms"]), 1)
            beta_points = max(int(leak["operational_beta_points"]), 5) + 1
            screen_point = (
                4 * int(leak["operational_reference_shots"])
                + len(leak["operational_depths"])
                * int(leak["operational_shots"]))
            total += waveform_count * beta_points * screen_point
            total += (2 * int(leak["operational_selection_shortlist"])
                      * int(leak["operational_selection_shots"])
                      * int(leak["operational_selection_blocks"]))
            verify_point = (
                4 * int(leak["operational_verify_shots"])
                + len(leak["operational_depths"])
                * int(leak["operational_verify_shots"]))
            total += int(leak["operational_verify_blocks"]) * verify_point
            # Same local closure used by strict mode after duration/DRAG selection.
            total += (2 * int(qubit["local_freq_points"])
                      * int(qubit["local_gain_points"]) * int(qubit["shots"]))
            total += (2 * (int(qubit["shortlist"]) + 1)
                      * int(qubit["confirm_shots"]) * int(qubit["confirm_blocks"]))
            total += 2 * int(f["calibration_shots"])
            total += int(f["points"]) * int(f["shots"])
            total += 4 * int(f["confirm_shots"]) * int(f["confirm_blocks"])
            total += 2 * int(amplified["calibration_shots"])
            total += (len(amplified["pulse_counts"])
                      * int(amplified["freq_points"])
                      * int(amplified["gain_points"])
                      * int(amplified["shots"]))
            total += (4 * int(amplified["confirm_shots"])
                      * int(amplified["confirm_blocks"]))
            total += (2 * int(readout["local_freq_points"])
                      * int(readout["local_gain_points"]) * int(readout["shots"]))
            total += (2 * (int(readout["shortlist"]) + 1)
                      * int(readout["confirm_shots"])
                      * int(readout["confirm_blocks"]))
        final = p["final"]
        # Normal final replay: top confirmed + top raw + working + input.  Explicit
        # recovery-queue candidates are added only after actual confirmation faults.
        total += (2 * (2 * int(final["top_candidates"]) + 2)
                  * int(final["shots"]) * int(final["blocks"]))
        if self._leakage_active or self._operational_leakage_active:
            total += 2 * int(final["shots"]) * int(final["blocks"])
        return int(total)

    # --------------------------------------------------------------- orchestration
    def acquire(self, progress=False, debug=False, plotDisp=False):
        del progress, debug
        self._preflight()
        if self._detailed_console():
            print("=" * 78)
            print("BASIC AUTO TUNER  %s" % self.path)
            print("  revision %s; exact TLS step-5 objective with direct P(f) constraint"
                  % BASIC_AUTOTUNER_REVISION)
            print("  start: read %.6f/%d/%.1fus | pi %.6f @ %d / %.1fns | DRAG %+.5f"
                  % (self.initial["read_pulse_freq"], self.initial["read_pulse_gain"],
                     self.initial["read_length"], self.initial["qubit_pi_freq"],
                     self.initial["qubit_pi_gain"], 4000.0 * self.initial["sigma"],
                     self.initial["qubit_drag_beta"]))
            if self._leakage_active:
                leakage = self.params["leakage"]
                print("  leakage limits: P(f) UCB one/amplified %.3f/%.3f; "
                      "third-cloud excess %.3f"
                      % (leakage["max_single_p2"], leakage["max_amplified_p2"],
                         leakage["max_third_blob_excess"]))
            repetitions = self._estimate_default_measurement_repetitions()
            passive_minutes = (
                repetitions * float(self.input_cfg["relax_delay"]) / 1e6 / 60.0)
            print("  worst-case all-passive delay: %.1f min over about %.0fk repetitions"
                  % (passive_minutes, repetitions / 1000.0))
            print("=" * 78)

        try:
            self._run_stage("baseline", self._stage_baseline)
            self._run_stage("resonator", self._stage_resonator)
            self._run_stage("spectroscopy", self._stage_spectroscopy)
            self._run_stage("iq_rabi", self._stage_iq_rabi)
            # Break the control/readout chicken-and-egg loop: coherent averaged Rabi is
            # a provisional preparation, then a broad direct-SS readout search makes the
            # later exact comparison among all Rabi basins meaningful.  This bootstrap
            # map is deliberately not write evidence; readout is re-optimized after the
            # direct/amplified control choice.
            self._run_stage("readout_grid", lambda: self._stage_readout_grid(
                "readout_grid", local=False, record_evidence=False))
            self._run_stage("reset_after_bootstrap", lambda:
                            self._try_activate_feedback("bootstrap readout"))
            self._run_stage("rough_ss", self._stage_rough_single_shot)
            self._run_stage("fine_frequency", lambda: self._stage_fine_frequency(
                "fine_frequency"))
            self._run_stage("parity_chevron", self._stage_parity_chevron)
            self._deactivate_feedback("readout frequency/power comparison")
            self._run_stage("readout_after_control", lambda: self._stage_readout_grid(
                "readout_after_control", local=True))
            self._run_stage("reset_after_readout", lambda:
                            self._try_activate_feedback("readout frequency/power"))
            self._deactivate_feedback("readout-length comparison")
            self._run_stage("readout_length", self._stage_readout_length)
            self._run_stage("reset_after_length", lambda:
                            self._try_activate_feedback("readout length"))
            self._run_stage("qubit_grid", lambda: self._stage_qubit_grid(
                "qubit_grid", local=False))
            self._run_stage("pulse_duration", self._stage_pulse_duration)
            self._run_stage("reset_after_duration", lambda:
                            self._try_activate_feedback("pulse-duration selection"))
            if bool(self.params.get("coordinate_descent_repeat", True)):
                self._deactivate_feedback("coordinate-descent readout comparison")
                self._run_stage("readout_repeat", lambda: self._stage_readout_grid(
                    "readout_repeat", local=True))
                self._run_stage("reset_after_repeat", lambda:
                                self._try_activate_feedback(
                                    "coordinate-descent readout"))
                self._run_stage("qubit_repeat", lambda: self._stage_qubit_grid(
                    "qubit_repeat", local=True))
            # These amplified control refinements must be last.  A later one-pulse
            # grid could otherwise undo a correction it is not sensitive enough to see.
            self._run_stage("fine_frequency_post_duration",
                            lambda: self._stage_fine_frequency(
                                "fine_frequency_post_duration"))
            self._run_stage("amplified_error", self._stage_amplified_error)
            # The ordinary final map first identifies the best empirical waveforms.
            # The default basic path then compares duration/DRAG candidates using
            # leakage-sensitive repeated returns and third-cloud growth.  Optional
            # strict mode replaces that screen with direct shelving P(f).  Either path
            # re-closes local coordinates and independently verifies the exact tuple
            # before the only replay allowed to authorize a write.
            # Candidate-rich final comparison may contain several readout tuples, so a
            # single raw feedback threshold cannot be applied fairly to all of them.
            # Compare them passively, then freshly validate feedback on only the winner.
            self._deactivate_feedback("multi-readout final comparison")
            final = self._run_stage("final", self._stage_final)
            reset_ready = self._run_stage(
                "reset_before_verification", lambda:
                self._try_activate_feedback("ordinary final winner"))
            if self._leakage_active:
                leakage_result = self._run_stage(
                    "leakage", self._stage_leakage)
                leakage_verified = False
                if leakage_result is None:
                    leakage_stage = self._stages[-1]
                    self.data["leakage"].update({
                        "optimized": False, "verified": False,
                        "failure": (leakage_stage.get("error")
                                    or "direct leakage stage produced no result"),
                    })
                else:
                    self._run_stage(
                        "qubit_post_leakage", lambda: self._stage_qubit_grid(
                            "qubit_post_leakage", local=True))
                    self._run_stage(
                        "frequency_post_leakage", lambda: self._stage_fine_frequency(
                            "frequency_post_leakage"))
                    self._run_stage(
                        "aae_post_leakage", self._stage_amplified_error)
                    self._deactivate_feedback("post-leakage readout comparison")
                    self._run_stage(
                        "readout_post_leakage", lambda: self._stage_readout_grid(
                            "readout_post_leakage", local=True))
                    self._run_stage(
                        "reset_after_post_readout", lambda:
                        self._try_activate_feedback("post-leakage readout"))
                    leakage_verified = bool(self._run_stage(
                        "leakage_verify", self._stage_leakage_verify))
                # A leakage-constrained replay is meaningful only for the exact tuple
                # that passed the independent qutrit audit.  Previously this replay
                # ran even when all e-f calibrations had failed, allowing a late noisy
                # measurement to overwrite a much better validated unconstrained
                # result.  Keep that best real measurement for reporting while still
                # failing closed on every config write.
                if leakage_verified:
                    constrained = self._run_stage(
                        "final_safe", self._stage_final_constrained)
                    if constrained is not None:
                        final = constrained
            elif self._operational_leakage_active:
                operational_result = self._run_stage(
                    "operational_leakage", self._stage_operational_leakage)
                operational_verified = False
                if operational_result is None:
                    operational_stage = self._stages[-1]
                    self.data["leakage"].update({
                        "optimized": False, "verified": False,
                        "failure": (operational_stage.get("error")
                                    or "operational screen produced no result"),
                    })
                else:
                    self._run_stage(
                        "qubit_post_leakage", lambda: self._stage_qubit_grid(
                            "qubit_post_leakage", local=True))
                    self._run_stage(
                        "frequency_post_leakage", lambda: self._stage_fine_frequency(
                            "frequency_post_leakage"))
                    self._run_stage(
                        "aae_post_leakage", self._stage_amplified_error)
                    self._deactivate_feedback("post-screen readout comparison")
                    self._run_stage(
                        "readout_post_leakage", lambda: self._stage_readout_grid(
                            "readout_post_leakage", local=True))
                    self._run_stage(
                        "reset_after_post_readout", lambda:
                        self._try_activate_feedback("post-screen readout"))
                    operational_verified = bool(self._run_stage(
                        "operational_leakage_verify",
                        self._stage_operational_leakage_verify))
                if operational_verified:
                    constrained = self._run_stage(
                        "final_safe", self._stage_final_constrained)
                    if constrained is not None:
                        final = constrained
            elif reset_ready:
                feedback_final = self._run_stage(
                    "final_feedback", self._stage_final_feedback)
                if feedback_final is not None:
                    final = feedback_final
        except KeyboardInterrupt:
            self._interrupted = True
            final = None
            self._log("run", "WARN", "operator interrupted; retaining completed measurements")

        if final is None:
            final = self._current_best_for_partial_run()
        self._finalize(final)
        try:
            self._checkpoint()
        except Exception as exc:
            self._log("save", "WARN", "pickle save failed: %s" % exc)
        try:
            self.save_plot(plotDisp=plotDisp)
        except Exception as exc:
            self._log("plot", "WARN", "summary plot failed: %s" % exc)
        return {"config": copy.deepcopy(self.input_cfg), "data": self.data}

    def _finalize(self, final):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.data["time"] = now
        self.data["working"] = dict(self.working)
        self.data["candidate_count"] = len(self._archive)
        self.data["interrupted"] = bool(self._interrupted)
        if self._archive:
            observed = max(self._archive, key=lambda row: float(
                row.get("fidelity", -np.inf)))
            self.data["best_observed_single_block"] = {
                key: observed[key] for key in (
                    "read_pulse_freq", "read_pulse_gain", "read_length",
                    "qubit_pi_freq", "qubit_pi_gain", "sigma",
                    "qubit_drag_beta", "fidelity",
                    "fidelity_se", "fidelity_lcb_95", "label", "measurement_index")
            }
        if final is None:
            self.data.update({
                "outcome": "no_measurement", "success": False,
                "failure": "no direct single-shot candidate was completed",
                "best_found": None, "tuned": {}, "eligible_tuned": {},
            })
            return
        best = dict(final)
        # Convert arrays to ordinary lists only in the compact top-level result; full
        # numpy evidence remains in confirmed_candidates and the pickle.
        if isinstance(best.get("block_fidelities"), np.ndarray):
            best["block_fidelities"] = best["block_fidelities"].tolist()
        best["gate_length_ns"] = 4000.0 * float(best["sigma"])
        self.data["best_found"] = best
        tuned = {key: best[key] for key in TUNED_KEYS}
        self.data["tuned"] = tuned
        is_final = str(best.get("label", "")).startswith("final exact")
        leakage_required = bool(
            self.data["leakage"].get("active", False)
            and self.data["leakage"].get("required_for_write", True))
        leakage_verified = bool(self.data["leakage"].get("verified", False))
        leakage_tuple_match = bool(
            not leakage_required
            or (leakage_verified
                and self._leakage_verified_candidate_key is not None
                and _candidate_key(best) == self._leakage_verified_candidate_key
                and self._final_replay_kind == "leakage_constrained"))
        self.data["leakage_required_for_write"] = leakage_required
        self.data["leakage_verified"] = leakage_verified
        stable = bool(is_final
                      and self._final_replay_completed
                      and not self._interrupted
                      and int(best.get("confirmation_blocks", 0))
                      >= int(self.params["final"]["blocks"])
                      and float(best.get("block_spread", np.inf))
                      <= float(self.params["final"]["max_block_spread"])
                      and leakage_tuple_match)
        self.data["final_stable"] = stable
        evidence = {
            key: self._key_has_evidence(key, tuned[key]) for key in TUNED_KEYS
        }
        changed = [
            key for key in TUNED_KEYS
            if not self._tuned_values_match(
                key, tuned[key], self._input_tuned_value(key))
        ]
        missing_evidence = [key for key in changed if not evidence[key]]
        eligible = {}
        if stable and changed:
            # The final measurement is itself the strongest relevant write evidence:
            # every changed coordinate below was jointly exercised as one exact
            # physical tuple for all required blocks.  Requiring a second, per-axis
            # provenance record can incorrectly reject a real winner that entered the
            # final pool through basin recovery or a cross-coordinate comparison.  We
            # therefore write the changed members of this jointly replayed tuple as an
            # atomic unit.  Earlier search evidence remains useful diagnostic metadata,
            # but it is not a veto over the later full-tuple experiment.
            eligible = {key: tuned[key] for key in changed}
            if missing_evidence:
                self._log(
                    "eligibility", "OK",
                    "stable exact final replay authorizes the complete measured "
                    "tuple; separate coordinate-search provenance is absent for %s"
                    % ", ".join(missing_evidence))
        self.data["eligibility"] = {
            "stable_final_replay": bool(stable),
            "changed_keys": list(changed),
            "exact_value_evidence": evidence,
            "missing_evidence": list(missing_evidence),
            "search_provenance_complete": bool(not missing_evidence),
            "eligibility_basis": (
                "stable_exact_full_tuple_replay" if stable else None),
            "atomic_tuple_safe": bool(stable),
            "leakage_required": bool(leakage_required),
            "leakage_verified": bool(leakage_verified),
            "leakage_tuple_match": bool(leakage_tuple_match),
            "final_replay_kind": self._final_replay_kind,
            "write_needed": bool(changed),
        }
        self.data["eligible_tuned"] = eligible
        self.data["success"] = True
        warned = [row for row in self._stages if row.get("status") == "warning"]
        report_warnings = [row.get("message") for row in self._report
                           if row.get("level") == "WARN"]
        self.data["warnings"] = ([row.get("error") for row in warned]
                                 + report_warnings)
        if self._interrupted:
            self.data["outcome"] = "interrupted_with_candidate"
        elif is_final:
            self.data["outcome"] = ("completed_with_warnings"
                                    if warned or report_warnings
                                    else "completed")
        else:
            self.data["outcome"] = "partial_with_candidate"
        self.data["failure"] = None
        self._log("result", "OK",
                  "best measured step-5 F=%.4f +/- %.4f%s"
                  % (best["fidelity"], best["fidelity_se"],
                     " (full measured tuple is write-eligible after stable final replay)"
                     if eligible
                     else " (reported, not write-eligible)"))

    # ---------------------------------------------------------------- persistence
    def _checkpoint(self, data=None):
        """Atomically replace the lossless pickle checkpoint on the same volume."""
        payload = self.data if data is None else data
        temporary = self.pname + ".tmp"
        with open(temporary, "wb") as stream:
            pickle.dump(payload, stream, protocol=pickle.HIGHEST_PROTOCOL)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.pname)

    @staticmethod
    def _jsonable_summary(data):
        keys = (
            "revision", "fidelity_definition", "initial", "working", "best_found",
            "selection_objective",
            "tuned", "eligible_tuned", "eligibility", "outcome", "success", "failure",
            "candidate_count", "interrupted", "final_stable", "time", "stages",
            "report", "confirmation_failures", "final_confirmation_complete",
            "unconfirmed_contenders", "leakage_required_for_write",
            "leakage_verified", "reset",
        )
        summary = {key: data.get(key) for key in keys if key in data}
        leakage = data.get("leakage", {})
        if isinstance(leakage, dict):
            scalar_keys = (
                "active", "strict_direct_active", "operational_active",
                "required_for_write", "measurement", "direct_p2_measured",
                "third_blob_guard",
                "optimized", "verified", "selection_safe", "failure",
                "used_safe_seed_fallback", "worst_single_p2_ucb",
                "worst_amplified_p2_ucb", "worst_third_blob_excess_ucb",
                "worst_even_return_error_ucb",
                "worst_odd_inversion_error_ucb",
            )
            summary["leakage"] = {
                key: leakage.get(key) for key in scalar_keys if key in leakage
            }
            chosen = leakage.get("chosen")
            if isinstance(chosen, dict):
                summary["leakage"]["chosen"] = {
                    key: chosen.get(key) for key in (
                        "qubit_pi_freq", "qubit_pi_gain", "sigma",
                        "qubit_drag_beta", "fidelity", "fidelity_se",
                        "single_p2_ucb", "amplified_p2_ucb",
                        "max_even_return_error_ucb",
                        "max_odd_inversion_error_ucb",
                        "third_blob_excess_ucb", "leakage_safe",
                        "operational_safe")
                    if key in chosen
                }
        return summary

    def save_data(self, data=None):
        """Save compact numeric maps to HDF5; the complete nested archive is in pickle."""
        if data is None:
            data = self.data
        print("Saving %s" % self.fname)
        with self.datafile() as h5:
            h5.attrs["summary"] = json.dumps(self._jsonable_summary(data), cls=NpEncoder)
            h5.attrs["params"] = json.dumps(self.params, cls=NpEncoder)
            h5.attrs["input_config"] = json.dumps(self.input_cfg, cls=NpEncoder)
            for stage, mapping in (data.get("maps", {}) or {}).items():
                if not isinstance(mapping, dict):
                    continue
                prefix = "maps/%s" % str(stage).replace("/", "_")
                axes = mapping.get("axes", {})
                if isinstance(axes, dict):
                    for key, value in axes.items():
                        try:
                            arr = np.asarray(value)
                            if np.issubdtype(arr.dtype, np.number):
                                h5.add("%s/axis_%s" % (prefix, key), arr)
                        except Exception:
                            pass
                for key, value in mapping.items():
                    if key == "axes" or isinstance(value, (dict, str, bytes)):
                        continue
                    try:
                        arr = np.asarray(value)
                        if np.issubdtype(arr.dtype, np.complexfloating):
                            h5.add("%s/%s_real" % (prefix, key), arr.real)
                            h5.add("%s/%s_imag" % (prefix, key), arr.imag)
                        elif np.issubdtype(arr.dtype, np.number) or arr.dtype == bool:
                            h5.add("%s/%s" % (prefix, key), arr)
                    except Exception:
                        pass
            # Compact archive columns make the direct measurements inspectable without
            # loading Python pickle objects.
            if self._archive:
                columns = {
                    "fidelity": [row.get("fidelity", np.nan) for row in self._archive],
                    "fidelity_se": [row.get("fidelity_se", np.nan) for row in self._archive],
                    "read_frequency_mhz": [row["read_pulse_freq"] for row in self._archive],
                    "read_gain_dac": [row["read_pulse_gain"] for row in self._archive],
                    "read_length_us": [row["read_length"] for row in self._archive],
                    "qubit_frequency_mhz": [row["qubit_pi_freq"] for row in self._archive],
                    "qubit_gain_dac": [row["qubit_pi_gain"] for row in self._archive],
                    "sigma_us": [row["sigma"] for row in self._archive],
                    "drag_beta": [row.get("qubit_drag_beta", 0.0)
                                  for row in self._archive],
                    "third_blob_excess_ucb": [
                        row.get("third_blob_excess_ucb_95", np.nan)
                        for row in self._archive],
                }
                for key, value in columns.items():
                    h5.add("candidate_archive/%s" % key, np.asarray(value))
            leakage_rows = (data.get("leakage", {}) or {}).get("verification", [])
            if leakage_rows:
                for key in ("single_p2_ucb", "amplified_p2_ucb",
                            "max_even_return_error_ucb",
                            "max_odd_inversion_error_ucb",
                            "third_blob_excess_ucb", "fidelity"):
                    h5.add(
                        "leakage_verification/%s" % key,
                        np.asarray([row.get(key, np.nan) for row in leakage_rows],
                                   dtype=float))
        try:
            self._checkpoint(data)
        except Exception as exc:
            self._log("save", "WARN", "pickle save failed: %s" % exc)

    def save_plot(self, plotDisp=False):
        """Write one compact summary: direct fidelity history and the key search maps."""
        fig, axes = plt.subplots(2, 3, figsize=(15, 8.5), constrained_layout=True)
        axes = axes.ravel()
        if self._archive:
            fids = np.asarray([row.get("fidelity", np.nan) for row in self._archive])
            axes[0].plot(np.arange(fids.size), fids, ".", ms=3, alpha=0.65)
            if self.data.get("best_found"):
                axes[0].axhline(self.data["best_found"]["fidelity"], color="tab:red",
                                lw=1.2, label="selected final")
                axes[0].legend(fontsize=8)
            axes[0].set_ylim(0.45, 1.01)
            axes[0].set_xlabel("direct step-5 measurement")
            axes[0].set_ylabel("balanced assignment fidelity")
            axes[0].set_title("All directly measured candidates")
        else:
            axes[0].text(0.5, 0.5, "no direct SS data", ha="center", va="center")

        preferred = [
            ("iq_rabi", "row_r2"),
            ("parity_chevron", "parity_score"),
            ("readout_grid", "fidelity"),
            ("qubit_grid", "fidelity"),
            ("pulse_duration", "fidelity"),
        ]
        for axis, (stage, field) in zip(axes[1:], preferred):
            mapping = self._maps.get(stage, {})
            value = mapping.get(field)
            if value is None:
                axis.text(0.5, 0.5, "%s not available" % stage,
                          ha="center", va="center")
                axis.set_axis_off()
                continue
            arr = np.asarray(value, dtype=float)
            while arr.ndim > 2:
                arr = np.nanmax(arr, axis=0)
            if arr.ndim == 1:
                axis.plot(arr, "o-")
            else:
                image = axis.imshow(arr, origin="lower", aspect="auto",
                                    interpolation="nearest")
                fig.colorbar(image, ax=axis, shrink=0.8)
            axis.set_title("%s: %s" % (stage.replace("_", " "), field))
        leakage = self.data.get("leakage", {})
        if isinstance(leakage, dict) and leakage.get("active", False):
            axis = axes[-1]
            axis.clear()
            rows = []
            for attempt in leakage.get("attempts", []):
                rows.extend(attempt.get("rows", []))
            rows = [row for row in rows
                    if np.isfinite(row.get("qubit_drag_beta", np.nan))]
            if rows:
                beta = np.asarray([row["qubit_drag_beta"] for row in rows])
                if leakage.get("strict_direct_active", False):
                    one = np.asarray([
                        row.get("single_p2_ucb", np.nan) for row in rows])
                    amplified = np.asarray([
                        row.get("amplified_p2_ucb", np.nan) for row in rows])
                    axis.plot(beta, one, "o", ms=4, label="one-pulse P(f) UCB")
                    axis.plot(beta, amplified, "s", ms=4,
                              label="amplified P(f) UCB")
                    axis.axhline(float(self.params["leakage"]["max_single_p2"]),
                                 color="tab:blue", ls="--", lw=1)
                    axis.axhline(float(
                        self.params["leakage"]["max_amplified_p2"]),
                        color="tab:orange", ls="--", lw=1)
                    axis.set_ylabel("population upper bound")
                    axis.set_title("direct shelving leakage constraint")
                else:
                    even = np.asarray([row.get(
                        "max_even_return_error_ucb", np.nan) for row in rows])
                    odd = np.asarray([row.get(
                        "max_odd_inversion_error_ucb", np.nan) for row in rows])
                    axis.plot(beta, even, "o", ms=4,
                              label="even return-error UCB")
                    axis.plot(beta, odd, "s", ms=4,
                              label="odd inversion-error UCB")
                    axis.axhline(float(self.params["leakage"]
                                       ["operational_max_even_return_error"]),
                                 color="tab:blue", ls="--", lw=1)
                    axis.axhline(float(self.params["leakage"]
                                       ["operational_max_odd_inversion_error"]),
                                 color="tab:orange", ls="--", lw=1)
                    axis.set_ylabel("normalized error upper bound")
                    axis.set_title("operational leakage-sensitive screen")
                axis.set_xlabel("DRAG beta")
                axis.legend(fontsize=7)
            else:
                axis.text(0.5, 0.5, "leakage-screen data unavailable",
                          ha="center", va="center")
        best = self.data.get("best_found")
        if best:
            title = ("Basic auto tune %s | F=%.4f +/- %.4f | read %.6f/%d/%.1fus | "
                     "pi %.6f @ %d, %.1fns, DRAG %+.5f | leakage %s"
                     % (self.path, best["fidelity"], best["fidelity_se"],
                        best["read_pulse_freq"], best["read_pulse_gain"],
                        best["read_length"], best["qubit_pi_freq"],
                        best["qubit_pi_gain"], 4000.0 * best["sigma"],
                        best.get("qubit_drag_beta", 0.0),
                        ("verified" if leakage.get("verified", False)
                         else "not verified")
                        if leakage.get("active", False) else "inactive"))
        else:
            title = "Basic auto tune %s | no completed direct SS candidate" % self.path
        fig.suptitle(title)
        fig.savefig(self.iname, dpi=160)
        if plotDisp:
            plt.show(block=False)
            plt.pause(0.1)
        else:
            plt.close(fig)
