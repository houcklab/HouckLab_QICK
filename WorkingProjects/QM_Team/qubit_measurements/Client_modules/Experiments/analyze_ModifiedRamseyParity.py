"""
Offline analysis for Modified-Ramsey charge-parity switching records.

Companion to mModifiedRamsey.py (acquisition). This module is pure offline
analysis: NumPy/SciPy/Matplotlib only, no hardware, no QICK imports. The
zero-span acquisition files are NOT touched or required.

Pipeline (orchestrated end-to-end by analyze_modified_ramsey_record):

  calibrate_readout_from_labeled_shots
        Labeled g/e single-shot IQ -> cloud centers, covariances, projection
        axis, projected separation, analog SNR, optimal threshold, confusion
        matrix, readout contrast, and average assignment fidelity.
        NOTE ON "FIDELITY": the legacy hist-analysis number (e.g. the
        "Fidelity = 44.90%" printed by Helpers/hist_analysis.py) is
        max|CDF_g - CDF_e|, which is the readout CONTRAST
        C = P(correct|g) + P(correct|e) - 1, NOT the assignment fidelity.
        For equal priors and the matching optimized threshold,
        F_assignment = (1 + C) / 2. Both numbers are reported here under
        unambiguous names.

  project_iq_trace          (I, Q) record -> scalar analog trace v(t) along the
                            calibrated axis (raw units preserved; NO thresholding)
  remove_slow_drift         Conservative slow-drift estimate/subtraction;
                            original trace is always preserved
  fit_two_state_hmm         Continuous-emission 2-state HMM: log-space
                            forward/backward, smoothed posteriors, Viterbi,
                            expm(Q*dt) transitions, likelihood rate fit,
                            Hessian errors + optional parametric bootstrap,
                            explicit "unidentifiable" verdict
  autocorrelation_rate_estimate / psd_rate_estimate
                            HMM-independent switching-rate estimates from the
                            analog trace
  rate_vs_bin_size          Stability of a simple threshold-rate estimate
                            against the visualization bin size
  reset_success_vs_cycle    Pre-correction populations; final reset requires a verification readout
  compare_parity_controls   flip_final_pi2 / echo-null / detuning control checks
  assess_parity_record      Aggregated quality gates -> warnings, not verdicts

State labels are NEUTRAL ("state0"/"state1"). Mapping states to even/odd
charge parity requires physics input this module does not have.

Rate conventions (SYMMETRIC switching, rate gamma per state, verified by the
deterministic synthetic tests in test_ModifiedRamseyParity_offline.py):

    mean dwell time         tau_dwell = 1 / gamma
    autocorrelation         <v(0)v(t)> ~ exp(-2*gamma*t)  =>  tau_corr = 1/(2*gamma)
    Lorentzian PSD corner   f_corner = gamma / pi         (2*pi*f_c = 2*gamma)

Tests:
    python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.test_ModifiedRamseyParity_offline
"""

import json
import math
import os

import numpy as np
from scipy import optimize, signal
from scipy.ndimage import uniform_filter1d

import matplotlib
matplotlib.use("Agg")  # headless-safe, matches analyze_ZeroSpanParity
import matplotlib.pyplot as plt


# =========================================================================
# 1. Readout calibration from labeled g/e shots
# =========================================================================

def calibrate_readout_from_labeled_shots(I_g, Q_g, I_e, Q_e, use_lda=True):
    """
    Calibrate the IQ projection and discrimination stats from LABELED shots.

    Parameters
    ----------
    I_g, Q_g : array_like
        Single-shot I/Q with the qubit prepared in |g> (no pi pulse).
    I_e, Q_e : array_like
        Single-shot I/Q with the qubit prepared in |e> (pi pulse).
    use_lda : bool
        If True (default) the projection axis is the Fisher/LDA direction
        Sigma_pooled^-1 (mu_e - mu_g), which is optimal for Gaussian clouds
        with shared covariance. If False, the plain mean-difference axis
        (mu_e - mu_g) is used (identical when the noise is isotropic).

    Returns
    -------
    dict with keys:
      g_center, e_center     : (2,) cloud means in (I, Q)
      cov_g, cov_e           : (2, 2) cloud covariances
      axis                   : (2,) UNIT projection vector (points g -> e)
      midpoint               : (2,) projection origin (midpoint of centers)
      proj_g_mean, proj_e_mean, proj_g_sigma, proj_e_sigma : floats,
                               moments of the projected clouds (raw units)
      separation             : |proj_e_mean - proj_g_mean|
      snr_analog             : separation / sqrt(0.5*(sg^2 + se^2))
      threshold              : equal-priors optimal projected threshold
                               (maximizes empirical assignment accuracy)
      confusion_matrix       : (2, 2) rows = prepared (g, e), cols = assigned
                               (g, e); P(assign col | prepared row)
      contrast               : P(g|g) + P(e|e) - 1 == max|CDF_g - CDF_e|
                               (this is what legacy code prints as "Fidelity")
      assignment_fidelity    : (1 + contrast) / 2, equal priors
      max_cdf_gap            : identical to contrast, kept under the explicit
                               name so the legacy number is traceable
      e_above_threshold      : bool, True if the |e> cloud projects ABOVE the
                               threshold (orientation of the mapping)
      n_g, n_e               : shot counts used
      warnings               : list of str
    """
    I_g = np.ravel(np.asarray(I_g, dtype=float))
    Q_g = np.ravel(np.asarray(Q_g, dtype=float))
    I_e = np.ravel(np.asarray(I_e, dtype=float))
    Q_e = np.ravel(np.asarray(Q_e, dtype=float))
    if I_g.size != Q_g.size or I_e.size != Q_e.size:
        raise ValueError("I/Q length mismatch in labeled shots")
    if I_g.size < 10 or I_e.size < 10:
        raise ValueError(
            f"need >= 10 shots per state to calibrate, got n_g={I_g.size}, "
            f"n_e={I_e.size}"
        )
    warnings = []

    g_pts = np.column_stack([I_g, Q_g])
    e_pts = np.column_stack([I_e, Q_e])
    g_center = g_pts.mean(axis=0)
    e_center = e_pts.mean(axis=0)
    cov_g = np.cov(g_pts, rowvar=False)
    cov_e = np.cov(e_pts, rowvar=False)

    diff = e_center - g_center
    if not np.any(np.abs(diff) > 0):
        raise ValueError("g and e cloud centers coincide; cannot define an axis")

    if use_lda:
        pooled = 0.5 * (cov_g + cov_e)
        # Regularize so a rank-deficient pooled covariance (e.g. synthetic
        # noise-free data) cannot blow up the solve.
        eps = 1e-12 * max(np.trace(pooled), 1e-300)
        axis = np.linalg.solve(pooled + eps * np.eye(2), diff)
    else:
        axis = diff.copy()
    axis = axis / np.linalg.norm(axis)
    # Canonical orientation: axis points from g toward e.
    if float(axis @ diff) < 0:
        axis = -axis
    midpoint = 0.5 * (g_center + e_center)

    vg = (g_pts - midpoint) @ axis
    ve = (e_pts - midpoint) @ axis
    proj_g_mean = float(vg.mean())
    proj_e_mean = float(ve.mean())
    proj_g_sigma = float(vg.std(ddof=1))
    proj_e_sigma = float(ve.std(ddof=1))
    separation = float(abs(proj_e_mean - proj_g_mean))
    pooled_sigma = math.sqrt(0.5 * (proj_g_sigma ** 2 + proj_e_sigma ** 2))
    snr_analog = separation / pooled_sigma if pooled_sigma > 0 else np.inf

    # Equal-priors optimal threshold: maximize |CDF_g(t) - CDF_e(t)| over the
    # pooled empirical sample. This IS the threshold the legacy hist analysis
    # optimizes; the number it prints is the max gap itself (the contrast).
    both = np.sort(np.concatenate([vg, ve]))
    cdf_g = np.searchsorted(np.sort(vg), both, side="right") / vg.size
    cdf_e = np.searchsorted(np.sort(ve), both, side="right") / ve.size
    gap = np.abs(cdf_g - cdf_e)
    k = int(np.argmax(gap))
    contrast = float(gap[k])
    threshold = float(both[k])

    e_above = proj_e_mean > proj_g_mean  # True by axis construction
    # Confusion matrix at the optimized threshold, equal priors.
    if e_above:
        p_gg = float(np.mean(vg <= threshold))
        p_ee = float(np.mean(ve > threshold))
    else:  # pragma: no cover - axis is canonically oriented g -> e
        p_gg = float(np.mean(vg > threshold))
        p_ee = float(np.mean(ve <= threshold))
    confusion = np.array([[p_gg, 1.0 - p_gg],
                          [1.0 - p_ee, p_ee]])
    assignment_fidelity = 0.5 * (1.0 + contrast)

    if snr_analog < 1.0:
        warnings.append(
            f"analog SNR {snr_analog:.2f} < 1: clouds barely separated; "
            "single-shot parity mapping will be dominated by readout noise"
        )
    if contrast < 0.3:
        warnings.append(
            f"readout contrast {contrast:.3f} < 0.3: parity trace will be "
            "heavily mixed; treat rate estimates with caution"
        )
    n_min = min(I_g.size, I_e.size)
    if n_min < 500:
        warnings.append(
            f"only {n_min} labeled shots in the smaller class; threshold and "
            "confusion-matrix estimates are coarse"
        )

    return {
        "g_center": g_center,
        "e_center": e_center,
        "cov_g": cov_g,
        "cov_e": cov_e,
        "axis": axis,
        "midpoint": midpoint,
        "proj_g_mean": proj_g_mean,
        "proj_e_mean": proj_e_mean,
        "proj_g_sigma": proj_g_sigma,
        "proj_e_sigma": proj_e_sigma,
        "separation": separation,
        "snr_analog": float(snr_analog),
        "threshold": threshold,
        "confusion_matrix": confusion,
        "contrast": contrast,
        "max_cdf_gap": contrast,
        "assignment_fidelity": float(assignment_fidelity),
        "e_above_threshold": bool(e_above),
        "n_g": int(I_g.size),
        "n_e": int(I_e.size),
        "use_lda": bool(use_lda),
        "warnings": warnings,
    }


def project_iq_trace(I, Q, calibration):
    """
    Project an (I, Q) record onto the calibrated axis. Returns the analog
    trace v (same length, raw units, midpoint-referenced). No thresholding.
    """
    I = np.ravel(np.asarray(I, dtype=float))
    Q = np.ravel(np.asarray(Q, dtype=float))
    if I.size != Q.size:
        raise ValueError("I and Q must have the same length")
    axis = np.asarray(calibration["axis"], dtype=float)
    midpoint = np.asarray(calibration["midpoint"], dtype=float)
    return (np.column_stack([I, Q]) - midpoint) @ axis


# =========================================================================
# 2. Slow-drift removal
# =========================================================================

def remove_slow_drift(v, dt_s, drift_timescale_s, expected_dwell_s=None,
                      min_timescale_ratio=20.0):
    """
    Conservative slow-drift estimate and subtraction.

    The drift estimate is a centered rolling MEAN with window
    ``drift_timescale_s``. Over a window much longer than the parity dwell
    time, the telegraph averages to (p0*mu0 + p1*mu1) = const (stationary
    occupancy), so subtracting the rolling mean removes readout drift plus a
    constant offset without distorting the telegraph itself. A rolling median
    is deliberately NOT used: over long windows the median tracks the
    majority STATE, which would eat the telegraph.

    Parameters
    ----------
    v : array_like            analog trace
    dt_s : float              sample period (s)
    drift_timescale_s : float rolling-window duration (s); must be MUCH longer
                              than the expected dwell time (2-3 ms on BFC
                              devices -> use >= ~100 ms)
    expected_dwell_s : float or None
                              if given, used to check the timescale ratio
    min_timescale_ratio : float
                              warn (and mark unsafe) when
                              drift_timescale < ratio * expected_dwell

    Returns
    -------
    dict:
      v_original    : the input trace, untouched
      v_corrected   : v_original - drift + mean(drift)  (same DC level)
      drift         : the rolling-mean drift estimate
      window_samples: int
      safe          : bool, False when the window is too short vs the dwell
      warnings      : list of str
    """
    v = np.ravel(np.asarray(v, dtype=float))
    warnings = []
    if dt_s <= 0 or drift_timescale_s <= 0:
        raise ValueError("dt_s and drift_timescale_s must be positive")
    window = max(1, int(round(drift_timescale_s / dt_s)))
    safe = True
    if expected_dwell_s is not None and expected_dwell_s > 0:
        ratio = drift_timescale_s / expected_dwell_s
        if ratio < min_timescale_ratio:
            safe = False
            warnings.append(
                f"drift window {drift_timescale_s*1e3:.1f} ms is only "
                f"{ratio:.1f}x the expected dwell "
                f"{expected_dwell_s*1e3:.1f} ms (< {min_timescale_ratio:g}x): "
                "drift removal will bleed into the telegraph; increase the "
                "window or skip drift removal"
            )
    if window >= v.size:
        warnings.append(
            "drift window >= record length; drift estimate degenerates to the "
            "global mean (no time-dependent correction applied)"
        )
        drift = np.full_like(v, v.mean())
    else:
        drift = uniform_filter1d(v, size=window, mode="nearest")
    v_corr = v - drift + float(drift.mean())
    drift_span = float(drift.max() - drift.min())
    return {
        "v_original": v,
        "v_corrected": v_corr,
        "drift": drift,
        "window_samples": int(window),
        "drift_span": drift_span,
        "safe": bool(safe),
        "warnings": warnings,
    }


# =========================================================================
# 3. Two-state continuous-emission HMM
# =========================================================================

def transition_matrix_2state(gamma01, gamma10, dt_s):
    """
    Exact expm(Q*dt) for the 2-state generator
        Q = [[-g01, g01], [g10, -g10]]   (rates in Hz, dt in s).

    The closed form (verified against scipy.linalg.expm in the test suite):
        P = Pi + exp(-(g01+g10)*dt) * (I - Pi),
        Pi = [[g10, g01], [g10, g01]] / (g01 + g10)
    """
    g01 = float(gamma01)
    g10 = float(gamma10)
    if g01 < 0 or g10 < 0:
        raise ValueError("rates must be non-negative")
    s = g01 + g10
    if s == 0:
        return np.eye(2)
    pi0 = g10 / s
    pi1 = g01 / s
    decay = math.exp(-s * dt_s)
    return np.array([
        [pi0 + pi1 * decay, pi1 - pi1 * decay],
        [pi0 - pi0 * decay, pi1 + pi0 * decay],
    ])


def _log_emissions(v, mu0, mu1, sigma0, sigma1):
    """(N, 2) log Gaussian emission densities."""
    v = np.asarray(v, dtype=float)
    if sigma0 <= 0 or sigma1 <= 0:
        raise ValueError("emission sigmas must be positive")
    le0 = -0.5 * ((v - mu0) / sigma0) ** 2 - math.log(sigma0 * math.sqrt(2 * math.pi))
    le1 = -0.5 * ((v - mu1) / sigma1) ** 2 - math.log(sigma1 * math.sqrt(2 * math.pi))
    return np.column_stack([le0, le1])

def _log_gaussian_1d(v, mu, sigma):
    if sigma <= 0:
        raise ValueError("emission sigma must be positive")
    return (-0.5 * ((np.asarray(v) - mu) / sigma) ** 2
            - math.log(sigma * math.sqrt(2 * math.pi)))


def _log_emissions_from_spec(v, spec):
    """Parity likelihoods for direct Gaussians or imperfect g/e mapping."""
    if spec.get("model", "gaussian") == "gaussian":
        return _log_emissions(
            v, spec["mu0"], spec["mu1"], spec["sigma0"], spec["sigma1"])
    if spec.get("model") != "ge_mixture":
        raise ValueError(f"unknown emission model {spec.get('model')!r}")
    lg = _log_gaussian_1d(v, spec["mu_g"], spec["sigma_g"])
    le = _log_gaussian_1d(v, spec["mu_e"], spec["sigma_e"])
    out = []
    for key in ("p_e_state0", "p_e_state1"):
        p = float(spec[key])
        if not 0 <= p <= 1:
            raise ValueError(f"{key} must be in [0, 1]")
        log_pg = math.log1p(-p) if p < 1 else -np.inf
        log_pe = math.log(p) if p > 0 else -np.inf
        out.append(np.logaddexp(log_pg + lg, log_pe + le))
    return np.column_stack(out)


def _emission_snr(spec):
    if spec.get("model", "gaussian") == "gaussian":
        means = (spec["mu0"], spec["mu1"])
        variances = (spec["sigma0"] ** 2, spec["sigma1"] ** 2)
    else:
        mg, me = spec["mu_g"], spec["mu_e"]
        vg, ve = spec["sigma_g"] ** 2, spec["sigma_e"] ** 2
        moments = []
        for p in (spec["p_e_state0"], spec["p_e_state1"]):
            mean = (1 - p) * mg + p * me
            var = ((1 - p) * (vg + (mg - mean) ** 2)
                   + p * (ve + (me - mean) ** 2))
            moments.append((mean, var))
        means = (moments[0][0], moments[1][0])
        variances = (moments[0][1], moments[1][1])
    pooled = math.sqrt(0.5 * sum(variances))
    return abs(means[1] - means[0]) / pooled if pooled > 0 else np.inf


def _step_log_transitions(gamma01, gamma10, dt_steps):
    """
    log transition matrices for each inter-sample interval.

    dt_steps : (N-1,) array of per-step intervals in seconds. Non-uniform
    values (record gaps, missing samples) are handled exactly, since the
    continuous-time generator gives expm(Q*dt) for any dt.
    Returns (N-1, 2, 2) array of log probabilities.
    """
    dt_steps = np.asarray(dt_steps, dtype=float)
    uniq, inv = np.unique(dt_steps, return_inverse=True)
    mats = np.empty((uniq.size, 2, 2))
    for i, dt in enumerate(uniq):
        mats[i] = transition_matrix_2state(gamma01, gamma10, dt)
    with np.errstate(divide="ignore"):
        return np.log(mats)[inv]


def _logaddexp2(a, b):
    """Scalar log(exp(a) + exp(b)), stable."""
    if a == -np.inf:
        return b
    if b == -np.inf:
        return a
    m = a if a > b else b
    return m + math.log1p(math.exp(-abs(a - b)))


def _forward_loglik(v, dt_steps, gamma01, gamma10, mu0, mu1, sigma0, sigma1,
                    pi0=None, emission_spec=None):
    """
    Likelihood-only log-space forward pass. Hot path of the rate fit: runs a
    scalar Python loop over pre-listed emission logs (much faster than
    per-step numpy indexing) with a fast path for uniform dt.
    """
    v = np.ravel(np.asarray(v, dtype=float))
    n = v.size
    dt_steps = np.ravel(np.asarray(dt_steps, dtype=float))
    le = (_log_emissions_from_spec(v, emission_spec)
          if emission_spec is not None
          else _log_emissions(v, mu0, mu1, sigma0, sigma1))
    le0 = le[:, 0].tolist()
    le1 = le[:, 1].tolist()

    s = gamma01 + gamma10
    if pi0 is None:
        pi0 = gamma10 / s if s > 0 else 0.5
    pi0 = min(max(float(pi0), 1e-15), 1.0 - 1e-15)
    a0 = math.log(pi0) + le0[0]
    a1 = math.log1p(-pi0) + le1[0]

    log = math.log
    log1p = math.log1p
    exp = math.exp

    def ladd(x, y):
        m = x if x > y else y
        return m + log1p(exp(-abs(x - y))) if m != -np.inf else -np.inf

    uniform = n <= 1 or bool(np.all(dt_steps == dt_steps[0]))
    if uniform:
        if n > 1:
            P = transition_matrix_2state(gamma01, gamma10, float(dt_steps[0]))
            with np.errstate(divide="ignore"):
                lp = np.log(P)
            t00, t01, t10, t11 = (float(lp[0, 0]), float(lp[0, 1]),
                                  float(lp[1, 0]), float(lp[1, 1]))
            for i in range(1, n):
                b0 = ladd(a0 + t00, a1 + t10) + le0[i]
                b1 = ladd(a0 + t01, a1 + t11) + le1[i]
                a0, a1 = b0, b1
    else:
        lt = _step_log_transitions(gamma01, gamma10, dt_steps)
        for i in range(1, n):
            t = lt[i - 1]
            b0 = ladd(a0 + t[0, 0], a1 + t[1, 0]) + le0[i]
            b1 = ladd(a0 + t[0, 1], a1 + t[1, 1]) + le1[i]
            a0, a1 = b0, b1
    return ladd(a0, a1)


def hmm_forward_backward(v, dt_steps, gamma01, gamma10, mu0, mu1,
                         sigma0, sigma1, pi0=None, emission_spec=None):
    """
    Log-space forward/backward for the 2-state continuous-emission HMM.

    Parameters
    ----------
    v         : (N,) analog trace
    dt_steps  : (N-1,) per-step intervals in seconds
    gamma01, gamma10 : switching rates (Hz), state0 -> state1 and back
    mu0, mu1, sigma0, sigma1 : Gaussian emission parameters
    pi0       : initial P(state0); default stationary g10/(g01+g10)

    Returns
    -------
    dict:
      loglik     : total log likelihood
      log_alpha  : (N, 2) forward log messages
      log_beta   : (N, 2) backward log messages
      posteriors : (N, 2) smoothed P(state_t | all data)
    """
    v = np.ravel(np.asarray(v, dtype=float))
    n = v.size
    if n == 0:
        raise ValueError("empty trace")
    dt_steps = np.ravel(np.asarray(dt_steps, dtype=float))
    if dt_steps.size != n - 1:
        raise ValueError(f"dt_steps must have length N-1={n-1}, got {dt_steps.size}")

    le = (_log_emissions_from_spec(v, emission_spec)
          if emission_spec is not None
          else _log_emissions(v, mu0, mu1, sigma0, sigma1))
    lt = _step_log_transitions(gamma01, gamma10, dt_steps) if n > 1 else \
        np.zeros((0, 2, 2))

    s = gamma01 + gamma10
    if pi0 is None:
        pi0 = gamma10 / s if s > 0 else 0.5
    pi0 = min(max(float(pi0), 1e-15), 1.0 - 1e-15)
    lpi = (math.log(pi0), math.log1p(-pi0))

    la = np.empty((n, 2))
    la[0, 0] = lpi[0] + le[0, 0]
    la[0, 1] = lpi[1] + le[0, 1]
    for i in range(1, n):
        t = lt[i - 1]
        a0, a1 = la[i - 1, 0], la[i - 1, 1]
        la[i, 0] = _logaddexp2(a0 + t[0, 0], a1 + t[1, 0]) + le[i, 0]
        la[i, 1] = _logaddexp2(a0 + t[0, 1], a1 + t[1, 1]) + le[i, 1]

    lb = np.empty((n, 2))
    lb[n - 1] = 0.0
    for i in range(n - 2, -1, -1):
        t = lt[i]
        b0 = lb[i + 1, 0] + le[i + 1, 0]
        b1 = lb[i + 1, 1] + le[i + 1, 1]
        lb[i, 0] = _logaddexp2(t[0, 0] + b0, t[0, 1] + b1)
        lb[i, 1] = _logaddexp2(t[1, 0] + b0, t[1, 1] + b1)

    loglik = _logaddexp2(la[n - 1, 0], la[n - 1, 1])
    lg = la + lb - loglik
    posteriors = np.exp(lg)
    # Normalize away round-off
    posteriors /= posteriors.sum(axis=1, keepdims=True)
    return {
        "loglik": float(loglik),
        "log_alpha": la,
        "log_beta": lb,
        "posteriors": posteriors,
    }


def hmm_viterbi(v, dt_steps, gamma01, gamma10, mu0, mu1, sigma0, sigma1,
                pi0=None, emission_spec=None):
    """Most likely state path (int array, values 0/1), log-space Viterbi."""
    v = np.ravel(np.asarray(v, dtype=float))
    n = v.size
    dt_steps = np.ravel(np.asarray(dt_steps, dtype=float))
    le = (_log_emissions_from_spec(v, emission_spec)
          if emission_spec is not None
          else _log_emissions(v, mu0, mu1, sigma0, sigma1))
    lt = _step_log_transitions(gamma01, gamma10, dt_steps) if n > 1 else \
        np.zeros((0, 2, 2))
    s = gamma01 + gamma10
    if pi0 is None:
        pi0 = gamma10 / s if s > 0 else 0.5
    pi0 = min(max(float(pi0), 1e-15), 1.0 - 1e-15)

    delta = np.empty((n, 2))
    back = np.zeros((n, 2), dtype=np.int8)
    delta[0, 0] = math.log(pi0) + le[0, 0]
    delta[0, 1] = math.log1p(-pi0) + le[0, 1]
    for i in range(1, n):
        t = lt[i - 1]
        for k in (0, 1):
            c0 = delta[i - 1, 0] + t[0, k]
            c1 = delta[i - 1, 1] + t[1, k]
            if c0 >= c1:
                delta[i, k] = c0 + le[i, k]
                back[i, k] = 0
            else:
                delta[i, k] = c1 + le[i, k]
                back[i, k] = 1
    path = np.empty(n, dtype=int)
    path[n - 1] = int(np.argmax(delta[n - 1]))
    for i in range(n - 2, -1, -1):
        path[i] = back[i + 1, path[i + 1]]
    return path


def _hmm_nll(log_rates, v, dt_steps, mu0, mu1, sigma0, sigma1, symmetric,
             emission_spec=None):
    if symmetric:
        g01 = g10 = math.exp(log_rates[0])
    else:
        g01 = math.exp(log_rates[0])
        g10 = math.exp(log_rates[1])
    return -_forward_loglik(
        v, dt_steps, g01, g10, mu0, mu1, sigma0, sigma1,
        emission_spec=emission_spec)


def _single_gaussian_loglik(v):
    """Log likelihood of the best single-Gaussian (no-switching) model."""
    v = np.asarray(v, dtype=float)
    sig = max(float(v.std()), 1e-300)
    return float(np.sum(-0.5 * ((v - v.mean()) / sig) ** 2
                        - math.log(sig * math.sqrt(2 * math.pi))))


def fit_two_state_hmm(v, dt_s, emissions, symmetric=False,
                      fit_emissions=False, rate_bounds_hz=(1e-2, 1e6),
                      gamma_init_hz=None, n_boot=0, seed=0,
                      min_emission_snr=0.7, min_transitions=10,
                      min_loglik_gain=10.0, compute_viterbi=True):
    """
    Likelihood-based switching-rate fit of a 2-state continuous-emission HMM.

    Parameters
    ----------
    v : (N,) analog trace (projected IQ; NOT thresholded).
    dt_s : float or (N-1,) array
        Sample interval(s) in SECONDS. Pass the per-step array when the record
        has gaps or missing samples; expm(Q*dt) handles them exactly.
    emissions : dict
        Either Gaussian state emissions (model="gaussian" with mu0/mu1 and
        sigma0/sigma1), or imperfect Ramsey mapping (model="ge_mixture" with
        calibrated mu_g/mu_e, sigma_g/sigma_e, and p_e_state0/p_e_state1).
        Emissions are fixed during the rate fit by default; refitting them on
        the parity record risks absorbing drift into the means.
    symmetric : bool
        True fits a single rate gamma (gamma01 = gamma10); False fits both.
    fit_emissions : bool
        Opt-in joint fit of (mu0, mu1, log sigma0, log sigma1) with the rates.
    rate_bounds_hz : (lo, hi) bounds on each rate.
    gamma_init_hz : float or None; initial rate guess (default: from a simple
        threshold-crossing count, clipped into bounds).
    n_boot : int
        Parametric-bootstrap resamples for rate CIs (0 = Hessian errors only).
    seed : int, bootstrap RNG seed (deterministic).
    min_emission_snr, min_transitions, min_loglik_gain :
        identifiability gates (see "identifiable"/"unidentifiable_reasons").

    Returns
    -------
    dict:
      identifiable            : bool. When False, rate fields are nan and
                                unidentifiable_reasons says why. A clean
                                Viterbi trace alone is NOT evidence of parity
                                switching -- these gates are the evidence.
      unidentifiable_reasons  : list of str
      gamma01_hz, gamma10_hz  : fitted rates (nan if unidentifiable)
      gamma01_err_hz, gamma10_err_hz : 1-sigma from the NLL Hessian (log space,
                                propagated), nan when unavailable
      gamma_boot_ci           : dict of 16/50/84 percentiles per rate
                                (only when n_boot > 0)
      loglik, loglik_single_gaussian, delta_loglik
      posteriors              : (N, 2) smoothed posteriors (from the fit point)
      posterior_ambiguity     : mean(1 - max posterior); ~0 = confident,
                                ~0.5 = coin toss
      viterbi_path            : (N,) int array (neutral labels 0/1)
      n_viterbi_transitions   : int
      expected_transitions    : float, posterior-weighted transition count
      occupancy               : (2,) posterior mean occupancy
      dwell_mean_s            : dict per state, from the Viterbi path
      emissions_used          : emission dict actually used
      rate_at_bound           : bool
      warnings                : list of str
    """
    v = np.ravel(np.asarray(v, dtype=float))
    n = v.size
    if n < 10:
        raise ValueError("trace too short for HMM analysis")
    if not np.all(np.isfinite(v)):
        bad = int(np.count_nonzero(~np.isfinite(v)))
        raise ValueError(
            f"trace contains {bad} non-finite samples; filter I/Q jointly and "
            "carry skipped time into dt_s before fitting")
    if np.isscalar(dt_s):
        if dt_s <= 0:
            raise ValueError("dt_s must be positive")
        dt_steps = np.full(n - 1, float(dt_s))
    else:
        dt_steps = np.ravel(np.asarray(dt_s, dtype=float))
        if dt_steps.size != n - 1:
            raise ValueError("dt_s array must have length N-1")
        if np.any(~np.isfinite(dt_steps)) or np.any(dt_steps <= 0):
            raise ValueError("all dt steps must be positive")

    emission_model = emissions.get("model", "gaussian")
    if emission_model == "gaussian":
        emission_spec = {
            "model": "gaussian",
            "mu0": float(emissions["mu0"]),
            "mu1": float(emissions["mu1"]),
            "sigma0": float(emissions["sigma0"]),
            "sigma1": float(emissions["sigma1"]),
        }
        mu0, mu1 = emission_spec["mu0"], emission_spec["mu1"]
        sigma0, sigma1 = emission_spec["sigma0"], emission_spec["sigma1"]
    elif emission_model == "ge_mixture":
        if fit_emissions:
            raise ValueError("fit_emissions is invalid for ge_mixture")
        emission_spec = {
            "model": "ge_mixture",
            "mu_g": float(emissions["mu_g"]),
            "mu_e": float(emissions["mu_e"]),
            "sigma_g": float(emissions["sigma_g"]),
            "sigma_e": float(emissions["sigma_e"]),
            "p_e_state0": float(emissions["p_e_state0"]),
            "p_e_state1": float(emissions["p_e_state1"]),
        }
        mu0, mu1 = emission_spec["mu_g"], emission_spec["mu_e"]
        sigma0, sigma1 = emission_spec["sigma_g"], emission_spec["sigma_e"]
        p0 = emission_spec["p_e_state0"]
        p1 = emission_spec["p_e_state1"]
        if not (0.0 <= p0 <= 1.0 and 0.0 <= p1 <= 1.0):
            raise ValueError("mixture probabilities must lie in [0, 1]")
        if p0 == p1:
            raise ValueError(
                "p_e_state0 and p_e_state1 must differ; identical mixtures "
                "carry no state information")
    else:
        raise ValueError(f"unknown emission model {emission_model!r}")
    warnings = []
    reasons = []

    pooled = math.sqrt(0.5 * (sigma0 ** 2 + sigma1 ** 2))
    emission_snr = _emission_snr(emission_spec)
    if emission_snr < min_emission_snr:
        reasons.append(
            f"emission separation SNR {emission_snr:.2f} < {min_emission_snr}: "
            "the two states are not distinguishable in the analog trace"
        )

    result = {
        "identifiable": False,
        "unidentifiable_reasons": reasons,
        "gamma01_hz": float("nan"),
        "gamma10_hz": float("nan"),
        "gamma01_err_hz": float("nan"),
        "gamma10_err_hz": float("nan"),
        "gamma_boot_ci": None,
        "loglik": float("nan"),
        "loglik_single_gaussian": _single_gaussian_loglik(v),
        "delta_loglik": float("nan"),
        "posteriors": None,
        "posterior_ambiguity": float("nan"),
        "viterbi_path": None,
        "n_viterbi_transitions": 0,
        "expected_transitions": float("nan"),
        "occupancy": np.array([np.nan, np.nan]),
        "dwell_mean_s": {"state0": float("nan"), "state1": float("nan")},
        "emissions_used": dict(emission_spec),
        "emission_snr": float(emission_snr),
        "symmetric": bool(symmetric),
        "rate_at_bound": False,
        "warnings": warnings,
    }
    if reasons:
        # Emissions unusable: rate fit would chase noise. Bail out explicitly.
        return result

    lo, hi = float(rate_bounds_hz[0]), float(rate_bounds_hz[1])
    if gamma_init_hz is None:
        # Crude threshold-crossing rate as a starting point.
        thr = 0.5 * (mu0 + mu1)
        bits = (v > thr).astype(int)
        crossings = int(np.count_nonzero(np.diff(bits)))
        total_t = float(dt_steps.sum())
        gamma_init_hz = max(crossings, 1) / max(total_t, 1e-12) / 2.0
    g0 = float(np.clip(gamma_init_hz, lo * 1.01, hi * 0.99))

    if fit_emissions:
        x0 = [math.log(g0)] if symmetric else [math.log(g0), math.log(g0)]
        x0 += [mu0, mu1, math.log(sigma0), math.log(sigma1)]
        n_rates = 1 if symmetric else 2

        def nll(x):
            g01 = math.exp(x[0])
            g10 = g01 if symmetric else math.exp(x[1])
            m0, m1 = x[n_rates], x[n_rates + 1]
            s0, s1 = math.exp(x[n_rates + 2]), math.exp(x[n_rates + 3])
            return -_forward_loglik(v, dt_steps, g01, g10, m0, m1, s0, s1)

        bounds = [(math.log(lo), math.log(hi))] * n_rates
        span = abs(mu1 - mu0) + 4 * pooled
        bounds += [(min(mu0, mu1) - span, max(mu0, mu1) + span)] * 2
        bounds += [(math.log(pooled * 1e-3), math.log(pooled * 1e3))] * 2
        opt = optimize.minimize(nll, x0, method="L-BFGS-B", bounds=bounds)
        log_rates = opt.x[:n_rates]
        mu0, mu1 = float(opt.x[n_rates]), float(opt.x[n_rates + 1])
        sigma0 = float(math.exp(opt.x[n_rates + 2]))
        sigma1 = float(math.exp(opt.x[n_rates + 3]))
        emission_spec = {"model": "gaussian", "mu0": mu0, "mu1": mu1,
                         "sigma0": sigma0, "sigma1": sigma1}
        result["emissions_used"] = dict(emission_spec)
        warnings.append(
            "emissions were REFIT on the parity record (fit_emissions=True); "
            "drift can be absorbed into the means"
        )
    else:
        x0 = [math.log(g0)] if symmetric else [math.log(g0), math.log(g0)]
        bounds = [(math.log(lo), math.log(hi))] * len(x0)
        nll_args = (v, dt_steps, mu0, mu1, sigma0, sigma1, symmetric,
                    emission_spec)
        if symmetric:
            opt = optimize.minimize_scalar(
                lambda lr: _hmm_nll(np.asarray([lr]), *nll_args),
                bounds=bounds[0], method="bounded",
                options={"xatol": 1e-8},
            )
            opt.x = np.asarray([opt.x])
        else:
            opt = optimize.minimize(
                _hmm_nll, x0, args=nll_args,
                method="L-BFGS-B", bounds=bounds,
            )
            if not (opt.success and np.all(np.isfinite(opt.x))
                    and math.isfinite(float(opt.fun))):
                warnings.append(
                    "L-BFGS-B rate fit did not converge; retried with Powell")
                opt = optimize.minimize(
                    _hmm_nll, x0, args=nll_args,
                    method="Powell", bounds=bounds,
                    options={"xtol": 1e-7, "ftol": 1e-9},
                )
        log_rates = np.asarray(opt.x)[:len(x0)]

    optimizer_ok = bool(opt.success and np.all(np.isfinite(opt.x))
                        and math.isfinite(float(opt.fun)))
    if not optimizer_ok:
        reasons.append(
            f"HMM optimizer failed: {getattr(opt, 'message', 'non-finite result')}")
        result["unidentifiable_reasons"] = reasons
        result["warnings"].append("HMM optimization did not converge")
        return result

    if symmetric:
        g01 = g10 = math.exp(log_rates[0])
    else:
        g01, g10 = math.exp(log_rates[0]), math.exp(log_rates[1])
    loglik = -float(opt.fun)

    fb = hmm_forward_backward(
        v, dt_steps, g01, g10, mu0, mu1, sigma0, sigma1,
        emission_spec=emission_spec)
    post = fb["posteriors"]
    ambiguity = float(np.mean(1.0 - post.max(axis=1)))
    occupancy = post.mean(axis=0)

    viterbi = hmm_viterbi(
        v, dt_steps, g01, g10, mu0, mu1, sigma0, sigma1,
        emission_spec=emission_spec) \
        if compute_viterbi else None
    n_trans = int(np.count_nonzero(np.diff(viterbi))) if viterbi is not None else 0

    # Pairwise posterior xi_t(i,j), not a product of adjacent marginals.
    # Adjacent hidden states are correlated through the transition matrix.
    le = _log_emissions_from_spec(v, emission_spec)
    lt = _step_log_transitions(g01, g10, dt_steps)
    exp_trans = 0.0
    for k_step in range(n - 1):
        log_xi = (
            fb["log_alpha"][k_step, :, None] + lt[k_step]
            + le[k_step + 1, None, :]
            + fb["log_beta"][k_step + 1, None, :]
        )
        xi = np.exp(log_xi - np.logaddexp.reduce(log_xi.ravel()))
        exp_trans += float(xi[0, 1] + xi[1, 0])

    delta_ll = loglik - result["loglik_single_gaussian"]
    if delta_ll < min_loglik_gain:
        reasons.append(
            f"2-state HMM improves on a single Gaussian by only "
            f"{delta_ll:.1f} log-likelihood (< {min_loglik_gain:g}): no "
            "statistical evidence for two states"
        )
    if exp_trans < min_transitions:
        reasons.append(
            f"expected transitions {exp_trans:.1f} < {min_transitions}: too "
            "few switches in the record to constrain a rate"
        )
    log_lo, log_hi = math.log(lo), math.log(hi)
    at_bound = any(
        lr <= log_lo + 1e-3 or lr >= log_hi - 1e-3 for lr in log_rates
    )
    if at_bound:
        reasons.append(
            "fitted rate pinned to a fit bound; the likelihood does not "
            "constrain the rate inside the allowed range"
        )
    result["rate_at_bound"] = bool(at_bound)

    # Hessian errors in log-rate space via central finite differences.
    def nll_rates(lr):
        return _hmm_nll(
            lr, v, dt_steps, mu0, mu1, sigma0, sigma1, symmetric,
            emission_spec)

    errs = [float("nan")] * len(log_rates)
    if not at_bound:
        try:
            h = 1e-3
            k = len(log_rates)
            H = np.zeros((k, k))
            f0 = nll_rates(log_rates)
            for i in range(k):
                ei = np.zeros(k); ei[i] = h
                for j in range(i, k):
                    ej = np.zeros(k); ej[j] = h
                    if i == j:
                        H[i, i] = (nll_rates(log_rates + ei)
                                   - 2 * f0 + nll_rates(log_rates - ei)) / h ** 2
                    else:
                        H[i, j] = H[j, i] = (
                            nll_rates(log_rates + ei + ej)
                            - nll_rates(log_rates + ei - ej)
                            - nll_rates(log_rates - ei + ej)
                            + nll_rates(log_rates - ei - ej)
                        ) / (4 * h ** 2)
            cov = np.linalg.inv(H)
            diag = np.diag(cov)
            if np.all(diag > 0):
                errs = list(np.sqrt(diag))  # sigma of log(rate)
        except (np.linalg.LinAlgError, ValueError):
            warnings.append("Hessian error estimate failed (singular curvature)")

    # sigma(log g) -> absolute error via g * sigma_log
    if symmetric:
        e = errs[0]
        result["gamma01_err_hz"] = result["gamma10_err_hz"] = (
            g01 * e if math.isfinite(e) else float("nan"))
    else:
        result["gamma01_err_hz"] = g01 * errs[0] if math.isfinite(errs[0]) else float("nan")
        result["gamma10_err_hz"] = g10 * errs[1] if math.isfinite(errs[1]) else float("nan")

    # Optional parametric bootstrap (deterministic via seed).
    if n_boot and not reasons:
        rng = np.random.default_rng(seed)
        boots = []
        for _ in range(int(n_boot)):
            sim = simulate_telegraph_trace(
                n=n, dt_s=dt_steps, gamma01_hz=g01, gamma10_hz=g10,
                mu0=0.0, mu1=1.0, sigma0=1e-9, sigma1=1e-9,
                seed=int(rng.integers(0, 2 ** 31 - 1)),
            )
            if emission_spec["model"] == "ge_mixture":
                hidden = sim["states"]
                p_e = np.where(
                    hidden == 0, emission_spec["p_e_state0"],
                    emission_spec["p_e_state1"])
                prepared_e = rng.random(n) < p_e
                sim_v = rng.normal(
                    np.where(prepared_e, emission_spec["mu_e"],
                             emission_spec["mu_g"]),
                    np.where(prepared_e, emission_spec["sigma_e"],
                             emission_spec["sigma_g"]),
                )
            else:
                hidden = sim["states"]
                sim_v = rng.normal(
                    np.where(hidden == 0, emission_spec["mu0"],
                             emission_spec["mu1"]),
                    np.where(hidden == 0, emission_spec["sigma0"],
                             emission_spec["sigma1"]),
                )
            x0b = [math.log(g01)] if symmetric else [math.log(g01), math.log(g10)]
            boot_args = (sim_v, dt_steps, mu0, mu1, sigma0, sigma1,
                         symmetric, emission_spec)
            boot_bounds = [(math.log(lo), math.log(hi))] * len(x0b)
            if symmetric:
                ob = optimize.minimize_scalar(
                    lambda lr: _hmm_nll(np.asarray([lr]), *boot_args),
                    bounds=boot_bounds[0], method="bounded",
                    options={"xatol": 1e-8},
                )
                ob.x = np.asarray([ob.x])
            else:
                ob = optimize.minimize(
                    _hmm_nll, x0b, args=boot_args, method="L-BFGS-B",
                    bounds=boot_bounds,
                )
                if not (ob.success and np.all(np.isfinite(ob.x))):
                    ob = optimize.minimize(
                        _hmm_nll, x0b, args=boot_args, method="Powell",
                        bounds=boot_bounds,
                    )
            if ob.success and np.all(np.isfinite(ob.x)):
                if symmetric:
                    boots.append((math.exp(ob.x[0]), math.exp(ob.x[0])))
                else:
                    boots.append((math.exp(ob.x[0]), math.exp(ob.x[1])))
        if boots:
            boots = np.asarray(boots)
            result["gamma_boot_ci"] = {
                "gamma01_hz": dict(zip(("p16", "p50", "p84"),
                                       np.percentile(boots[:, 0], [16, 50, 84]))),
                "gamma10_hz": dict(zip(("p16", "p50", "p84"),
                                       np.percentile(boots[:, 1], [16, 50, 84]))),
                "n_boot": int(boots.shape[0]),
            }
        else:
            warnings.append("all parametric-bootstrap optimizations failed")

    # Mean dwell from the Viterbi path (empirical), per state.
    dwell_mean = {"state0": float("nan"), "state1": float("nan")}
    if viterbi is not None and n_trans >= 1:
        t_axis = np.concatenate([[0.0], np.cumsum(dt_steps)])
        edges = np.flatnonzero(np.diff(viterbi)) + 1
        starts = np.concatenate([[0], edges])
        ends = np.concatenate([edges, [n]])
        d0, d1 = [], []
        for a, b in zip(starts, ends):
            dur = t_axis[b - 1] - t_axis[a] + float(np.median(dt_steps))
            (d0 if viterbi[a] == 0 else d1).append(dur)
        if d0:
            dwell_mean["state0"] = float(np.mean(d0))
        if d1:
            dwell_mean["state1"] = float(np.mean(d1))

    identifiable = not reasons
    if identifiable:
        result["gamma01_hz"] = float(g01)
        result["gamma10_hz"] = float(g10)
    else:
        warnings.append(
            "record judged UNIDENTIFIABLE: rate estimates withheld (nan). "
            "Do not read a switching rate off the Viterbi trace."
        )
    result.update({
        "identifiable": bool(identifiable),
        "loglik": float(loglik),
        "delta_loglik": float(delta_ll),
        "posteriors": post,
        "posterior_ambiguity": ambiguity,
        "viterbi_path": viterbi,
        "n_viterbi_transitions": n_trans,
        "expected_transitions": exp_trans,
        "occupancy": occupancy,
        "dwell_mean_s": dwell_mean,
    })
    if ambiguity > 0.25:
        warnings.append(
            f"posterior ambiguity {ambiguity:.2f} > 0.25: state assignments "
            "are individually unreliable even if rates are constrained"
        )
    return result


def simulate_telegraph_trace(n, dt_s, gamma01_hz, gamma10_hz, mu0, mu1,
                             sigma0, sigma1, seed=0, drift=None,
                             start_state=None):
    """
    Deterministic (seeded) synthetic telegraph + Gaussian-emission trace.

    dt_s may be a scalar or an (N-1,) per-step array (gaps/missing samples).
    ``drift``: optional (N,) additive drift. Returns dict with keys
    states, v, t_s.
    """
    rng = np.random.default_rng(seed)
    n = int(n)
    if np.isscalar(dt_s):
        dt_steps = np.full(n - 1, float(dt_s))
    else:
        dt_steps = np.ravel(np.asarray(dt_s, dtype=float))
        if dt_steps.size != n - 1:
            raise ValueError("dt_s array must have length N-1")
    s = gamma01_hz + gamma10_hz
    if start_state is None:
        p0 = gamma10_hz / s if s > 0 else 0.5
        state = 0 if rng.random() < p0 else 1
    else:
        state = int(start_state)
    # Precompute stay probabilities per unique dt (fast path: uniform dt).
    uniq, inv = np.unique(dt_steps, return_inverse=True) if n > 1 else \
        (np.zeros(0), np.zeros(0, dtype=int))
    p0_by_dt = []  # (P[0,0], P[1,0]) per unique dt
    for dt in uniq:
        P = transition_matrix_2state(gamma01_hz, gamma10_hz, float(dt))
        p0_by_dt.append((P[0, 0], P[1, 0]))
    u = rng.random(max(n - 1, 0))
    states = np.empty(n, dtype=int)
    states[0] = state
    for i in range(1, n):
        p_to0 = p0_by_dt[inv[i - 1]][state]
        state = 0 if u[i - 1] < p_to0 else 1
        states[i] = state
    mu = np.where(states == 0, mu0, mu1)
    sig = np.where(states == 0, sigma0, sigma1)
    v = mu + sig * rng.standard_normal(n)
    if drift is not None:
        v = v + np.ravel(np.asarray(drift, dtype=float))[:n]
    t_s = np.concatenate([[0.0], np.cumsum(dt_steps)])
    return {"states": states, "v": v, "t_s": t_s}


# =========================================================================
# 4. HMM-independent rate estimators: autocorrelation and Welch PSD
# =========================================================================

def autocorrelation_rate_estimate(v, dt_s, max_lag_s=None, min_points=5):
    """
    Switching rate from the exponential decay of the analog autocorrelation.

    Convention (symmetric switching, rate gamma per state):
        C(t) = C(0) * exp(-2*gamma*t)   =>   tau_corr = 1/(2*gamma),
        gamma = 1/(2*tau_corr),         tau_dwell = 1/gamma = 2*tau_corr.

    Lag 0 is EXCLUDED from the fit: it carries the additive readout-noise
    variance, which does not decay with the telegraph.

    Requires (approximately) uniform sampling; pass the drift-corrected trace.

    Returns dict:
      tau_corr_s, gamma_hz, amplitude, noise_variance, acf, lags_s,
      fit_ok, warnings
    """
    v = np.ravel(np.asarray(v, dtype=float))
    warnings = []
    out = {"tau_corr_s": float("nan"), "gamma_hz": float("nan"),
           "amplitude": float("nan"), "noise_variance": float("nan"),
           "acf": np.zeros(0), "lags_s": np.zeros(0),
           "fit_ok": False, "warnings": warnings}
    n = v.size
    if n < 32:
        warnings.append("trace too short for autocorrelation analysis")
        return out
    dt_s = float(dt_s)
    x = v - v.mean()
    # FFT-based biased autocovariance.
    nfft = int(2 ** math.ceil(math.log2(2 * n)))
    X = np.fft.rfft(x, nfft)
    acov = np.fft.irfft(X * np.conj(X), nfft)[:n] / n
    c0 = acov[0]
    if c0 <= 0:
        warnings.append("zero variance trace")
        return out
    acf = acov / c0

    if max_lag_s is None:
        # Adaptive: fit out to where the ACF first drops below 1/e^2 of its
        # lag-1 value, capped at n//4 lags.
        ref = acf[1] if n > 1 else 0.0
        below = np.flatnonzero(acf[1:] < ref / math.e ** 2)
        kmax = int(below[0] + 1) if below.size else n // 4
        kmax = int(np.clip(kmax, min_points + 1, n // 4))
    else:
        kmax = int(np.clip(round(max_lag_s / dt_s), min_points + 1, n // 4))

    lags = np.arange(1, kmax + 1) * dt_s
    y = acov[1:kmax + 1]
    out["acf"] = acf[:kmax + 1]
    out["lags_s"] = np.arange(kmax + 1) * dt_s
    pos = y > 0
    if pos.sum() < min_points:
        warnings.append(
            "autocorrelation has too few positive lags to fit; telegraph "
            "amplitude may be below the noise"
        )
        return out
    try:
        popt, _ = optimize.curve_fit(
            lambda t, A, tau: A * np.exp(-t / tau),
            lags[pos], y[pos],
            p0=[max(y[0], 1e-12), max(lags[pos][-1] / 3.0, dt_s)],
            maxfev=10000,
        )
        A, tau = float(popt[0]), float(abs(popt[1]))
    except (RuntimeError, ValueError):
        warnings.append("autocorrelation exponential fit failed")
        return out
    if A <= 0 or tau <= 0:
        warnings.append("autocorrelation fit returned non-physical parameters")
        return out
    if tau < dt_s:
        warnings.append(
            f"fitted tau_corr {tau*1e6:.1f} us is below the sample period; "
            "the switching is unresolved at this cadence"
        )
    noise_var = float(c0 - A)  # zero-lag excess over the telegraph amplitude
    out.update({
        "tau_corr_s": tau,
        "gamma_hz": 1.0 / (2.0 * tau),
        "amplitude": A,
        "noise_variance": noise_var,
        "fit_ok": True,
    })
    if noise_var > 4 * A:
        warnings.append(
            f"readout-noise variance is {noise_var/A:.1f}x the telegraph "
            "amplitude; the autocorrelation estimate is noise-dominated"
        )
    return out


def psd_rate_estimate(v, dt_s, nperseg=None, f_max_factor=0.45):
    """
    Switching rate from a Lorentzian fit to the Welch PSD.

    Convention (symmetric switching, rate gamma per state):
        S(f) = S0 / (1 + (f / f_corner)^2) + white,
        f_corner = gamma / pi        (angular corner = 2*gamma).

    Returns dict:
      f_corner_hz, gamma_hz, s0, white_floor, freqs_hz, psd, fit_ok, warnings
    """
    v = np.ravel(np.asarray(v, dtype=float))
    warnings = []
    out = {"f_corner_hz": float("nan"), "gamma_hz": float("nan"),
           "s0": float("nan"), "white_floor": float("nan"),
           "freqs_hz": np.zeros(0), "psd": np.zeros(0),
           "fit_ok": False, "warnings": warnings}
    n = v.size
    if n < 256:
        warnings.append("trace too short for Welch PSD analysis")
        return out
    fs = 1.0 / float(dt_s)
    if nperseg is None:
        nperseg = int(min(max(256, 2 ** math.floor(math.log2(n / 8))), n))
    freqs, psd = signal.welch(v - v.mean(), fs=fs, nperseg=nperseg,
                              detrend="constant")
    keep = (freqs > 0) & (freqs <= f_max_factor * fs)
    f, p = freqs[keep], psd[keep]
    out["freqs_hz"], out["psd"] = f, p
    if f.size < 8:
        warnings.append("too few PSD points to fit")
        return out

    def model(fx, log_s0, log_fc, log_w):
        return (np.exp(log_s0) / (1.0 + (fx / np.exp(log_fc)) ** 2)
                + np.exp(log_w))

    # Fit in log-power space so the (log-uniform) high-frequency floor does
    # not dominate the least squares.
    def resid(theta):
        return np.log(model(f, *theta)) - np.log(p)

    s0_guess = float(np.median(p[: max(3, f.size // 20)]))
    w_guess = float(np.median(p[-max(3, f.size // 20):]))
    fc_guess = float(f[min(np.searchsorted(-p, -s0_guess / 2), f.size - 1)])
    fc_guess = float(np.clip(fc_guess, f[0], f[-1]))
    try:
        sol = optimize.least_squares(
            resid,
            x0=[math.log(max(s0_guess, 1e-300)),
                math.log(max(fc_guess, f[0])),
                math.log(max(w_guess, 1e-300))],
            bounds=([-np.inf, math.log(f[0] / 10.0), -np.inf],
                    [np.inf, math.log(f[-1] * 10.0), np.inf]),
        )
    except ValueError:
        warnings.append("PSD Lorentzian fit failed")
        return out
    if not sol.success:
        warnings.append("PSD Lorentzian fit did not converge")
        return out
    s0 = math.exp(sol.x[0])
    fc = math.exp(sol.x[1])
    white = math.exp(sol.x[2])
    if fc <= f[0] * 1.05 or fc >= f[-1] * 0.95:
        warnings.append(
            f"PSD corner {fc:.1f} Hz sits at the edge of the analysis band "
            f"[{f[0]:.1f}, {f[-1]:.1f}] Hz; the rate is not resolved"
        )
    if s0 < 3 * white:
        warnings.append(
            "Lorentzian plateau is < 3x the white noise floor; PSD rate "
            "estimate is weakly constrained"
        )
    out.update({
        "f_corner_hz": float(fc),
        "gamma_hz": float(math.pi * fc),
        "s0": float(s0),
        "white_floor": float(white),
        "fit_ok": True,
    })
    return out


def rate_vs_bin_size(v, dt_s, threshold, bin_sizes=(1, 2, 4, 8, 16, 32)):
    """
    Threshold-crossing switch rate as a function of visualization bin size.

    A rate that keeps FALLING as the bin grows means noise crossings dominate
    (each binning step removes noise-induced flips); a rate that is stable
    over a plateau of bin sizes reflects genuine telegraph switching.

    Returns dict: bin_sizes, bin_us, rate_hz, n_switches.
    """
    v = np.ravel(np.asarray(v, dtype=float))
    dt_s = float(dt_s)
    rates, counts, bin_us = [], [], []
    for b in bin_sizes:
        b = int(b)
        nb = v.size // b
        if nb < 4:
            rates.append(float("nan")); counts.append(0)
            bin_us.append(b * dt_s * 1e6)
            continue
        vb = v[: nb * b].reshape(nb, b).mean(axis=1)
        bits = (vb > threshold).astype(int)
        n_sw = int(np.count_nonzero(np.diff(bits)))
        total_t = (nb - 1) * b * dt_s
        rates.append(n_sw / total_t if total_t > 0 else float("nan"))
        counts.append(n_sw)
        bin_us.append(b * dt_s * 1e6)
    return {"bin_sizes": list(bin_sizes), "bin_us": bin_us,
            "rate_hz": rates, "n_switches": counts}


# =========================================================================
# 5. Active-reset validation (offline, from saved reset readouts)
# =========================================================================

def reset_success_vs_cycle(reset_I, reset_Q, calibration,
                           post_reset_I=None, post_reset_Q=None):
    """Report what the saved active-reset readouts actually establish.

    Reset readout k is acquired before corrective flip k. Consequently row 0
    is the pre-reset population and row k validates only the k corrections
    preceding it. The last corrective flip is not observable unless an
    explicit post-reset verification readout is supplied.
    """
    reset_I = np.atleast_2d(np.asarray(reset_I, dtype=float))
    reset_Q = np.atleast_2d(np.asarray(reset_Q, dtype=float))
    if reset_I.shape != reset_Q.shape:
        raise ValueError("reset_I and reset_Q shapes differ")
    threshold = calibration["threshold"]
    e_above = calibration["e_above_threshold"]

    def ground_fraction(i_values, q_values):
        projected = project_iq_trace(i_values, q_values, calibration)
        ground = (projected <= threshold if e_above
                  else projected > threshold)
        return float(np.mean(ground))

    pre_correction = np.asarray([
        ground_fraction(reset_I[k], reset_Q[k])
        for k in range(reset_I.shape[0])
    ])
    warnings = []
    final_fraction = float("nan")
    converged = None
    if post_reset_I is not None and post_reset_Q is not None:
        final_fraction = ground_fraction(post_reset_I, post_reset_Q)
        converged = bool(final_fraction > 0.9)
        if not converged:
            warnings.append(
                f"post-reset ground fraction {final_fraction:.3f} <= 0.9: "
                "active reset did not establish reliable initialization")
    else:
        warnings.append(
            "no post-reset verification readout was saved; the final "
            "corrective flip cannot be validated from ModifiedRamsey reset "
            "buffers. Use mActiveResetVerify before trusting initialization")

    return {
        "g_fraction": pre_correction,
        "pre_correction_g_fraction": pre_correction,
        "validated_after_reset_g_fraction": pre_correction[1:],
        "final_ground_fraction": final_fraction,
        "n_cycles": int(reset_I.shape[0]),
        "n_shots": int(reset_I.shape[1]),
        "n_resets_observed": max(0, int(reset_I.shape[0]) - 1),
        "converged": converged,
        "warnings": warnings,
    }

# =========================================================================
# 6. Control comparisons
# =========================================================================

def compare_parity_controls(main_result, control_results):
    """
    Sanity checks between the parity-sensing run and its controls.

    Parameters
    ----------
    main_result : dict
        {"label", "hmm": fit_two_state_hmm output, "acf": autocorrelation
        output, "occupancy_state1": float} for the parity-sensing run.
    control_results : list of dicts
        Same structure plus "control_type" in
        {"flip_final_pi2", "echo_null", "tau_offset", "drive_detuned",
         "drive_off"}.

    Checks applied (each control gets checked=True/False + note):
      flip_final_pi2 : telegraph must SURVIVE (similar amplitude/rate) with
                       the state-occupancy mapping inverted:
                       occ1_flip ~ 1 - occ1_main.
      echo_null      : telegraph must be SUPPRESSED: ACF amplitude < 25% of
                       the main run's, or the HMM must report unidentifiable.
      tau_offset / drive_detuned / drive_off :
                       reduced contrast expected; reported informationally
                       with amplitude ratios.

    Returns dict: {"controls": [...], "all_expected": bool}
    """
    def amp(res):
        a = res.get("acf", {}).get("amplitude", float("nan"))
        return a if (a is not None and math.isfinite(a) and a > 0) else float("nan")

    main_amp = amp(main_result)
    main_occ1 = float(main_result.get("occupancy_state1", float("nan")))
    main_identifiable = bool(
        main_result.get("hmm", {}).get("identifiable", False))
    main_valid = main_identifiable and math.isfinite(main_amp)
    entries = []
    all_ok = main_valid
    n_decisive_checks = 0
    for ctl in control_results:
        ctype = ctl.get("control_type", "unknown")
        c_amp = amp(ctl)
        ratio = c_amp / main_amp if (math.isfinite(c_amp)
                                     and math.isfinite(main_amp)
                                     and main_amp > 0) else float("nan")
        entry = {"control_type": ctype, "label": ctl.get("label", ctype),
                 "amplitude_ratio": ratio, "checked": None, "note": ""}
        if ctype == "flip_final_pi2":
            occ1 = float(ctl.get("occupancy_state1", float("nan")))
            survives = math.isfinite(ratio) and ratio > 0.25
            inverted = (math.isfinite(occ1) and math.isfinite(main_occ1)
                        and abs(occ1 - (1.0 - main_occ1)) < 0.15)
            ok = main_valid and survives and inverted
            entry["checked"] = bool(ok)
            entry["note"] = (
                f"amplitude ratio {ratio:.2f} (expect ~1), occupancy(state1) "
                f"{occ1:.2f} vs 1-main={1.0 - main_occ1:.2f} (expect equal)"
            )
        elif ctype == "echo_null":
            hmm_ident = bool(ctl.get("hmm", {}).get("identifiable", False))
            suppressed = math.isfinite(ratio) and ratio < 0.25
            null_evidence = suppressed or (not hmm_ident and main_valid)
            ok = main_valid and null_evidence
            entry["checked"] = bool(ok)
            entry["note"] = (
                f"amplitude ratio {ratio if math.isfinite(ratio) else float('nan'):.2f} "
                "(expect << 1: echo refocuses the static parity detuning)"
            )
        else:
            entry["checked"] = None  # informational only
            entry["note"] = f"amplitude ratio {ratio}"
        if entry["checked"] is not None:
            n_decisive_checks += 1
        if entry["checked"] is False:
            all_ok = False
        entries.append(entry)
    return {"controls": entries,
            "all_expected": bool(all_ok and n_decisive_checks > 0)}


# =========================================================================
# 7. Quality gates
# =========================================================================

def assess_parity_record(calibration=None, hmm=None, acf=None, psd=None,
                         drift=None, reset=None,
                         estimator_agreement_factor=3.0):
    """
    Aggregate quality gates into a warnings list. Never upgrades a result --
    only flags reasons NOT to over-interpret it.
    """
    warnings = []
    for src in (calibration, hmm, acf, psd, drift, reset):
        if src:
            warnings.extend(src.get("warnings", []))
    if hmm and hmm.get("identifiable"):
        rates = [hmm.get("gamma01_hz"), hmm.get("gamma10_hz")]
        alt = []
        for est, name in ((acf, "autocorrelation"), (psd, "PSD")):
            if est and est.get("fit_ok") and math.isfinite(est.get("gamma_hz", float("nan"))):
                alt.append((name, est["gamma_hz"]))
        g_eff = 0.0
        if all(r and math.isfinite(r) and r > 0 for r in rates):
            # For asymmetric rates the ACF/PSD see gamma_eff = (g01+g10)/2.
            g_eff = 0.5 * (rates[0] + rates[1])
        for name, g_alt in alt:
            if g_eff > 0 and (g_alt / g_eff > estimator_agreement_factor
                              or g_eff / g_alt > estimator_agreement_factor):
                warnings.append(
                    f"HMM effective rate {g_eff:.1f} Hz and {name} rate "
                    f"{g_alt:.1f} Hz disagree by more than "
                    f"{estimator_agreement_factor:g}x: at least one estimator "
                    "is not measuring parity switching"
                )
    return {"warnings": warnings, "clean": not warnings}


# =========================================================================
# 8. Plots + orchestration
# =========================================================================

def _plot_projected_trace(t_s, v, v_corr, drift, out_path, max_pts=200_000):
    stride = max(1, v.size // max_pts)
    fig, axes = plt.subplots(2, 1, figsize=(11, 5), sharex=True)
    axes[0].plot(t_s[::stride], v[::stride], lw=0.4, label="projected v(t)")
    if drift is not None:
        axes[0].plot(t_s[::stride], drift[::stride], "r-", lw=1.2, label="drift estimate")
    axes[0].set_ylabel("v (raw units)"); axes[0].legend(loc="best")
    axes[1].plot(t_s[::stride], v_corr[::stride], lw=0.4, color="C2")
    axes[1].set_ylabel("v corrected"); axes[1].set_xlabel("time (s)")
    fig.suptitle("Projected analog parity trace")
    fig.tight_layout(); fig.savefig(out_path, dpi=150); plt.close(fig)


def _plot_hmm(t_s, v, hmm, out_path, max_pts=200_000):
    stride = max(1, v.size // max_pts)
    fig, axes = plt.subplots(3, 1, figsize=(11, 7), sharex=True)
    axes[0].plot(t_s[::stride], v[::stride], lw=0.4)
    # Reference levels for the two PARITY states. Two emission models reach
    # here and they do not share key names: the plain Gaussian model carries
    # mu0/mu1 directly, while the ge_mixture model (which is what
    # analyze_modified_ramsey_record always builds) carries the calibrated
    # readout clouds mu_g/mu_e plus per-state excited-state probabilities. For
    # the mixture, the level a parity state actually emits at is the
    # probability-weighted mean of the two clouds, not either cloud itself.
    em = hmm["emissions_used"]
    if em.get("model") == "ge_mixture":
        mu_g, mu_e = em["mu_g"], em["mu_e"]
        state_means = (
            (1.0 - em["p_e_state0"]) * mu_g + em["p_e_state0"] * mu_e,
            (1.0 - em["p_e_state1"]) * mu_g + em["p_e_state1"] * mu_e,
        )
        # the underlying g/e clouds, for context
        for mu, lbl in ((mu_g, "readout |g>"), (mu_e, "readout |e>")):
            axes[0].axhline(mu, color="0.6", ls=":", lw=0.8, label=lbl)
        axes[0].legend(loc="best", fontsize="x-small")
    else:
        state_means = (em["mu0"], em["mu1"])
    for mu, c in zip(state_means, ("C0", "C1")):
        axes[0].axhline(mu, color=c, ls="--", lw=1)
    axes[0].set_ylabel("v")
    if hmm["posteriors"] is not None:
        axes[1].plot(t_s[::stride], hmm["posteriors"][::stride, 1], lw=0.5)
        axes[1].set_ylim(-0.05, 1.05)
    axes[1].set_ylabel("P(state1 | data)")
    if hmm["viterbi_path"] is not None:
        axes[2].step(t_s[::stride], hmm["viterbi_path"][::stride],
                     where="post", lw=0.6)
        axes[2].set_ylim(-0.1, 1.1)
    axes[2].set_ylabel("Viterbi state"); axes[2].set_xlabel("time (s)")
    title = "2-state HMM"
    if hmm["identifiable"]:
        title += (f": g01={hmm['gamma01_hz']:.1f} Hz, "
                  f"g10={hmm['gamma10_hz']:.1f} Hz")
    else:
        title += ": UNIDENTIFIABLE (rates withheld)"
    fig.suptitle(title)
    fig.tight_layout(); fig.savefig(out_path, dpi=150); plt.close(fig)


def _plot_acf_psd(acf_out, psd_out, out_path):
    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(11, 4))
    if acf_out["acf"].size:
        ax0.plot(acf_out["lags_s"] * 1e3, acf_out["acf"], ".-", ms=3)
        if acf_out["fit_ok"]:
            lags = acf_out["lags_s"]
            c0_amp = acf_out["amplitude"] / (
                acf_out["amplitude"] + max(acf_out["noise_variance"], 0.0))
            ax0.plot(lags * 1e3,
                     c0_amp * np.exp(-lags / acf_out["tau_corr_s"]), "r-",
                     label=(f"tau_corr={acf_out['tau_corr_s']*1e3:.2f} ms -> "
                            f"gamma={acf_out['gamma_hz']:.1f} Hz"))
            ax0.legend()
    ax0.set_xlabel("lag (ms)"); ax0.set_ylabel("normalized ACF")
    ax0.set_title("Autocorrelation")
    if psd_out["freqs_hz"].size:
        ax1.loglog(psd_out["freqs_hz"], psd_out["psd"], lw=0.7)
        if psd_out["fit_ok"]:
            f = psd_out["freqs_hz"]
            fit = (psd_out["s0"] / (1 + (f / psd_out["f_corner_hz"]) ** 2)
                   + psd_out["white_floor"])
            ax1.loglog(f, fit, "r-",
                       label=(f"f_c={psd_out['f_corner_hz']:.1f} Hz -> "
                              f"gamma={psd_out['gamma_hz']:.1f} Hz"))
            ax1.legend()
    ax1.set_xlabel("frequency (Hz)"); ax1.set_ylabel("PSD")
    ax1.set_title("Welch PSD")
    fig.tight_layout(); fig.savefig(out_path, dpi=150); plt.close(fig)


def _plot_calibration(calibration, out_path):
    fig, ax = plt.subplots(figsize=(6, 6))
    for c, cov, lbl, col in (
        (calibration["g_center"], calibration["cov_g"], "g", "C0"),
        (calibration["e_center"], calibration["cov_e"], "e", "C1"),
    ):
        ax.plot(*c, "x", color=col, ms=12, mew=3, label=f"|{lbl}> center")
        # 1-sigma covariance ellipse
        w, vecs = np.linalg.eigh(cov)
        th = np.linspace(0, 2 * np.pi, 100)
        ell = (vecs @ (np.sqrt(np.maximum(w, 0))[:, None]
                       * np.vstack([np.cos(th), np.sin(th)])))
        ax.plot(c[0] + ell[0], c[1] + ell[1], color=col, lw=1)
    mid = calibration["midpoint"]; axv = calibration["axis"]
    span = calibration["separation"]
    ax.plot([mid[0] - axv[0] * span, mid[0] + axv[0] * span],
            [mid[1] - axv[1] * span, mid[1] + axv[1] * span],
            "k--", lw=1, label="projection axis")
    ax.set_xlabel("I"); ax.set_ylabel("Q"); ax.axis("equal"); ax.legend()
    ax.set_title(
        f"Readout calibration: SNR={calibration['snr_analog']:.2f}, "
        f"contrast={calibration['contrast']:.3f},\n"
        f"F_assign=(1+C)/2={calibration['assignment_fidelity']:.3f}"
    )
    fig.tight_layout(); fig.savefig(out_path, dpi=150); plt.close(fig)


def _plot_rate_vs_bin(rvb, out_path):
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.semilogx(rvb["bin_us"], rvb["rate_hz"], "o-")
    ax.set_xlabel("bin size (us)"); ax.set_ylabel("threshold switch rate (Hz)")
    ax.set_title("Rate stability vs visualization bin size")
    fig.tight_layout(); fig.savefig(out_path, dpi=150); plt.close(fig)


def _plot_dwells(hmm, out_path):
    if hmm["viterbi_path"] is None:
        return
    # Import here to keep this module importable without the zero-span file
    # in pathological environments; dwell_time_statistics is pure NumPy.
    from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity import (
        dwell_time_statistics,
    )
    path = hmm["viterbi_path"]
    t_us = np.arange(path.size, dtype=float)  # unit spacing; scaled below
    stats = dwell_time_statistics(path, t_us)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, dw, lbl in ((axes[0], stats["dwell_0_us"], "state0"),
                        (axes[1], stats["dwell_1_us"], "state1")):
        if dw.size:
            ax.hist(dw, bins=min(30, max(5, dw.size // 5)), log=True)
        ax.set_xlabel("dwell (samples)"); ax.set_title(f"{lbl} dwells (Viterbi)")
    fig.tight_layout(); fig.savefig(out_path, dpi=150); plt.close(fig)


def _json_default(x):
    if isinstance(x, np.ndarray):
        return x.tolist()
    if isinstance(x, (np.floating, np.integer)):
        return x.item()
    if isinstance(x, (np.bool_,)):
        return bool(x)
    return str(x)


def analyze_modified_ramsey_record(
        I, Q, dt_s, calibration,
        drift_timescale_s=0.2, expected_dwell_s=2.5e-3,
        symmetric_hmm=True, n_boot=0, seed=0,
        mapping_probabilities=(0.1, 0.9),
        mapping_probabilities_calibrated=False,
        reset_I=None, reset_Q=None,
        out_dir=None, base_name="mr_parity", save_plots=True,
        save_sidecars=True, hmm_kwargs=None):
    """
    End-to-end offline analysis of one Modified-Ramsey parity record.

    Parameters
    ----------
    I, Q          : (N,) unthresholded per-shot IQ (final Ramsey readout).
    dt_s          : float or (N-1,) array, ACTUAL per-shot interval(s) in
                    seconds (use the scheduled rep period from the saved
                    timing, and per-step gaps where the record has them).
    calibration   : output of calibrate_readout_from_labeled_shots.
    drift_timescale_s : rolling drift window; default 0.2 s = 80x a 2.5 ms
                    expected dwell.
    expected_dwell_s  : expected parity dwell (2-3 ms on BFC devices).
    symmetric_hmm : fit a single symmetric rate by default (charge parity has
                    no preferred branch); set False for asymmetric rates.
    mapping_probabilities : assumed P(e|state0), P(e|state1) for the Ramsey
                    mapping. These must come from a device-specific mapping
                    calibration; g/e readout fidelity alone is not sufficient.
    mapping_probabilities_calibrated : whether that independent calibration was
                    performed; False adds an explicit quality warning.
    reset_I/Q     : optional (n_cycles, N) reset readouts for initialization
                    validation.
    out_dir/base_name/save_plots/save_sidecars : output control.
    hmm_kwargs    : extra kwargs forwarded to fit_two_state_hmm.

    Returns dict with sub-results: calibration, drift, hmm, acf, psd,
    rate_vs_bin, reset, assessment, plus scalar summary fields.
    """
    I = np.ravel(np.asarray(I, dtype=float))
    Q = np.ravel(np.asarray(Q, dtype=float))
    if I.size != Q.size:
        raise ValueError("I and Q must have the same length")
    original_n = I.size
    finite = np.isfinite(I) & np.isfinite(Q)
    if np.count_nonzero(finite) < 10:
        raise ValueError("fewer than 10 jointly finite IQ samples remain")

    if np.isscalar(dt_s):
        dt_value = float(dt_s)
        if not math.isfinite(dt_value) or dt_value <= 0:
            raise ValueError("dt_s must be finite and positive")
        full_t = np.arange(original_n, dtype=float) * dt_value
    else:
        raw_steps = np.ravel(np.asarray(dt_s, dtype=float))
        if raw_steps.size != original_n - 1:
            raise ValueError("dt_s array must have length original_N-1")
        if np.any(~np.isfinite(raw_steps)) or np.any(raw_steps <= 0):
            raise ValueError("all dt steps must be finite and positive")
        full_t = np.concatenate([[0.0], np.cumsum(raw_steps)])

    I, Q = I[finite], Q[finite]
    t_s = full_t[finite]
    dt_steps = np.diff(t_s)
    dt_nominal = float(np.median(dt_steps))
    removed = int(original_n - I.size)
    v = project_iq_trace(I, Q, calibration)

    uniform_timing = bool(
        np.allclose(dt_steps, dt_nominal, rtol=1e-6,
                    atol=max(1e-15, dt_nominal * 1e-9)))
    if uniform_timing:
        drift = remove_slow_drift(
            v, dt_nominal, drift_timescale_s,
            expected_dwell_s=expected_dwell_s)
    else:
        warning = (
            "nonuniform timing/gaps detected: drift filtering, "
            "autocorrelation, PSD, and bin-size estimates were skipped; "
            "the HMM alone uses exact per-step timing")
        drift = {
            "v_original": v.copy(), "v_corrected": v.copy(),
            "drift": np.zeros_like(v), "window_samples": 0,
            "drift_span": 0.0, "safe": False, "warnings": [warning],
        }
    if removed:
        drift["warnings"].append(
            f"removed {removed} non-finite IQ samples and carried their "
            "elapsed time into HMM dt steps")
    v_corr = drift["v_corrected"]

    p0, p1 = map(float, mapping_probabilities)
    if not (0.0 <= p0 <= 1.0 and 0.0 <= p1 <= 1.0):
        raise ValueError("mapping probabilities must lie in [0, 1]")
    if p0 == p1:
        raise ValueError(
            "mapping probabilities must differ; identical probabilities carry "
            "no parity information")
    if not mapping_probabilities_calibrated:
        drift["warnings"].append(
            "Ramsey mapping probabilities are assumed rather than independently "
            "calibrated; fitted rates are conditional on those assumptions")
    emissions = {
        "model": "ge_mixture",
        "mu_g": calibration["proj_g_mean"],
        "mu_e": calibration["proj_e_mean"],
        "sigma_g": calibration["proj_g_sigma"],
        "sigma_e": calibration["proj_e_sigma"],
        "p_e_state0": p0,
        "p_e_state1": p1,
    }
    fit_options = dict(hmm_kwargs or {})
    if expected_dwell_s and expected_dwell_s > 0:
        fit_options.setdefault("gamma_init_hz", 1.0 / expected_dwell_s)
    hmm = fit_two_state_hmm(
        v_corr, dt_steps, emissions, symmetric=symmetric_hmm,
        n_boot=n_boot, seed=seed, **fit_options)

    if uniform_timing:
        acf = autocorrelation_rate_estimate(v_corr, dt_nominal)
        psd = psd_rate_estimate(v_corr, dt_nominal)
        rvb = rate_vs_bin_size(
            v_corr, dt_nominal, calibration["threshold"])
    else:
        skipped = drift["warnings"][0]
        acf = {
            "tau_corr_s": float("nan"), "gamma_hz": float("nan"),
            "amplitude": float("nan"), "noise_variance": float("nan"),
            "acf": np.zeros(0), "lags_s": np.zeros(0),
            "fit_ok": False, "warnings": [skipped],
        }
        psd = {
            "f_corner_hz": float("nan"), "gamma_hz": float("nan"),
            "s0": float("nan"), "white_floor": float("nan"),
            "freqs_hz": np.zeros(0), "psd": np.zeros(0),
            "fit_ok": False, "warnings": [skipped],
        }
        rvb = {
            "bin_sizes": [], "bin_us": [], "rate_hz": [],
            "n_switches": [], "warnings": [skipped],
        }

    reset = None
    if reset_I is not None and reset_Q is not None and np.size(reset_I):
        reset_i = np.asarray(reset_I)
        reset_q = np.asarray(reset_Q)
        if reset_i.shape[-1] == original_n:
            reset_i, reset_q = reset_i[..., finite], reset_q[..., finite]
        reset = reset_success_vs_cycle(reset_i, reset_q, calibration)
    assessment = assess_parity_record(calibration=calibration, hmm=hmm,
                                      acf=acf, psd=psd, drift=drift,
                                      reset=reset)

    t_s = (np.concatenate([[0.0], np.cumsum(dt_steps)])
           if dt_steps is not None else np.arange(v.size) * dt_nominal)

    summary = {
        "n_samples": int(v.size),
        "n_samples_removed_nonfinite": removed,
        "uniform_timing": uniform_timing,
        "dt_nominal_s": dt_nominal,
        "record_duration_s": float(t_s[-1]) if v.size else 0.0,
        "emission_model": "ge_mixture",
        "mapping_p_e_state0": p0,
        "mapping_p_e_state1": p1,
        "mapping_probabilities_calibrated": bool(
            mapping_probabilities_calibrated),
        "identifiable": hmm["identifiable"],
        "gamma01_hz": hmm["gamma01_hz"],
        "gamma10_hz": hmm["gamma10_hz"],
        "gamma01_err_hz": hmm["gamma01_err_hz"],
        "gamma10_err_hz": hmm["gamma10_err_hz"],
        "acf_gamma_hz": acf["gamma_hz"],
        "psd_gamma_hz": psd["gamma_hz"],
        "posterior_ambiguity": hmm["posterior_ambiguity"],
        "expected_transitions": hmm["expected_transitions"],
        "occupancy_state1": float(hmm["occupancy"][1])
        if np.all(np.isfinite(hmm["occupancy"])) else float("nan"),
        "readout_contrast": calibration["contrast"],
        "assignment_fidelity": calibration["assignment_fidelity"],
        "snr_analog": calibration["snr_analog"],
        "drift_span": drift["drift_span"],
        "drift_safe": drift["safe"],
        "reset_converged": (reset or {}).get("converged"),
        "warnings": assessment["warnings"],
    }

    if out_dir is not None and (save_plots or save_sidecars):
        os.makedirs(out_dir, exist_ok=True)
        base = os.path.join(out_dir, base_name)
        if save_plots:
            _plot_calibration(calibration, base + "_calibration.png")
            _plot_projected_trace(t_s, v, v_corr, drift["drift"],
                                  base + "_projected_trace.png")
            _plot_hmm(t_s, v_corr, hmm, base + "_hmm.png")
            _plot_acf_psd(acf, psd, base + "_acf_psd.png")
            _plot_rate_vs_bin(rvb, base + "_rate_vs_bin.png")
            _plot_dwells(hmm, base + "_dwells.png")
            if reset is not None:
                fig, ax = plt.subplots(figsize=(5, 4))
                ax.plot(
                    np.arange(reset["n_cycles"]),
                    reset["pre_correction_g_fraction"], "o-")
                ax.set_xlabel("pre-correction readout index")
                ax.set_ylabel("ground fraction before correction")
                ax.set_ylim(0, 1.02)
                ax.set_title("Active-reset pre-correction populations")
                fig.tight_layout()
                fig.savefig(base + "_reset_success.png", dpi=150)
                plt.close(fig)
        if save_sidecars:
            with open(base + "_analysis.json", "w") as fh:
                json.dump({**summary,
                           "acf": {k: acf[k] for k in
                                   ("tau_corr_s", "gamma_hz", "amplitude",
                                    "noise_variance", "fit_ok")},
                           "psd": {k: psd[k] for k in
                                   ("f_corner_hz", "gamma_hz", "s0",
                                    "white_floor", "fit_ok")},
                           "rate_vs_bin": rvb,
                           "gamma_boot_ci": hmm["gamma_boot_ci"],
                           "dwell_mean_s": hmm["dwell_mean_s"],
                           "reset_pre_correction_g_fraction":
                               (reset or {}).get("pre_correction_g_fraction"),
                           "reset_validated_after_reset_g_fraction":
                               (reset or {}).get("validated_after_reset_g_fraction"),
                           "reset_final_ground_fraction":
                               (reset or {}).get("final_ground_fraction"),
                           },
                          fh, indent=2, default=_json_default)
            try:
                import h5py
                with h5py.File(base + "_analysis.h5", "w") as fh:
                    fh.create_dataset("v_projected", data=v)
                    fh.create_dataset("v_corrected", data=v_corr)
                    fh.create_dataset("drift", data=drift["drift"])
                    fh.create_dataset("t_s", data=t_s)
                    if hmm["posteriors"] is not None:
                        fh.create_dataset("posterior_state1",
                                          data=hmm["posteriors"][:, 1])
                    if hmm["viterbi_path"] is not None:
                        fh.create_dataset("viterbi_path",
                                          data=hmm["viterbi_path"])
                    for k, val in summary.items():
                        if k == "warnings":
                            fh.attrs[k] = json.dumps(val)
                        elif val is None:
                            fh.attrs[k] = "None"
                        else:
                            fh.attrs[k] = val
            except ImportError:
                pass

    return {"summary": summary, "calibration": calibration, "drift": drift,
            "hmm": hmm, "acf": acf, "psd": psd, "rate_vs_bin": rvb,
            "reset": reset, "assessment": assessment,
            "v_projected": v, "v_corrected": v_corr, "t_s": t_s}
