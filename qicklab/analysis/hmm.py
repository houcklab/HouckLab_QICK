"""Two-state continuous-emission HMM for parity-switching records."""

import math

import numpy as np
from scipy import optimize

from qicklab.analysis.rates import simulate_telegraph_trace, transition_matrix_2state


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
    return -0.5 * ((np.asarray(v) - mu) / sigma) ** 2 - math.log(sigma * math.sqrt(2 * math.pi))


def _log_emissions_from_spec(v, spec):
    """Parity likelihoods for direct Gaussians or imperfect g/e mapping."""
    if spec.get("model", "gaussian") == "gaussian":
        return _log_emissions(v, spec["mu0"], spec["mu1"], spec["sigma0"], spec["sigma1"])
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
            var = (1 - p) * (vg + (mg - mean) ** 2) + p * (ve + (me - mean) ** 2)
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


def _forward_loglik(
    v, dt_steps, gamma01, gamma10, mu0, mu1, sigma0, sigma1, pi0=None, emission_spec=None
):
    """
    Likelihood-only log-space forward pass. Hot path of the rate fit: runs a
    scalar Python loop over pre-listed emission logs (much faster than
    per-step numpy indexing) with a fast path for uniform dt.
    """
    v = np.ravel(np.asarray(v, dtype=float))
    n = v.size
    dt_steps = np.ravel(np.asarray(dt_steps, dtype=float))
    le = (
        _log_emissions_from_spec(v, emission_spec)
        if emission_spec is not None
        else _log_emissions(v, mu0, mu1, sigma0, sigma1)
    )
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
            t00, t01, t10, t11 = (
                float(lp[0, 0]),
                float(lp[0, 1]),
                float(lp[1, 0]),
                float(lp[1, 1]),
            )
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


def hmm_forward_backward(
    v, dt_steps, gamma01, gamma10, mu0, mu1, sigma0, sigma1, pi0=None, emission_spec=None
):
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
        raise ValueError(f"dt_steps must have length N-1={n - 1}, got {dt_steps.size}")

    le = (
        _log_emissions_from_spec(v, emission_spec)
        if emission_spec is not None
        else _log_emissions(v, mu0, mu1, sigma0, sigma1)
    )
    lt = _step_log_transitions(gamma01, gamma10, dt_steps) if n > 1 else np.zeros((0, 2, 2))

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


def hmm_viterbi(
    v, dt_steps, gamma01, gamma10, mu0, mu1, sigma0, sigma1, pi0=None, emission_spec=None
):
    """Most likely state path (int array, values 0/1), log-space Viterbi."""
    v = np.ravel(np.asarray(v, dtype=float))
    n = v.size
    dt_steps = np.ravel(np.asarray(dt_steps, dtype=float))
    le = (
        _log_emissions_from_spec(v, emission_spec)
        if emission_spec is not None
        else _log_emissions(v, mu0, mu1, sigma0, sigma1)
    )
    lt = _step_log_transitions(gamma01, gamma10, dt_steps) if n > 1 else np.zeros((0, 2, 2))
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


def _hmm_nll(log_rates, v, dt_steps, mu0, mu1, sigma0, sigma1, symmetric, emission_spec=None):
    if symmetric:
        g01 = g10 = math.exp(log_rates[0])
    else:
        g01 = math.exp(log_rates[0])
        g10 = math.exp(log_rates[1])
    return -_forward_loglik(
        v, dt_steps, g01, g10, mu0, mu1, sigma0, sigma1, emission_spec=emission_spec
    )


def _single_gaussian_loglik(v):
    """Log likelihood of the best single-Gaussian (no-switching) model."""
    v = np.asarray(v, dtype=float)
    sig = max(float(v.std()), 1e-300)
    return float(
        np.sum(-0.5 * ((v - v.mean()) / sig) ** 2 - math.log(sig * math.sqrt(2 * math.pi)))
    )


def fit_two_state_hmm(
    v,
    dt_s,
    emissions,
    symmetric=False,
    fit_emissions=False,
    rate_bounds_hz=(1e-2, 1e6),
    gamma_init_hz=None,
    n_boot=0,
    seed=0,
    min_emission_snr=0.7,
    min_transitions=10,
    min_loglik_gain=10.0,
    compute_viterbi=True,
):
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
            "carry skipped time into dt_s before fitting"
        )
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
                "carry no state information"
            )
    else:
        raise ValueError(f"unknown emission model {emission_model!r}")
    warnings = []
    reasons = []

    pooled = math.sqrt(0.5 * (sigma0**2 + sigma1**2))
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
        emission_spec = {
            "model": "gaussian",
            "mu0": mu0,
            "mu1": mu1,
            "sigma0": sigma0,
            "sigma1": sigma1,
        }
        result["emissions_used"] = dict(emission_spec)
        warnings.append(
            "emissions were REFIT on the parity record (fit_emissions=True); "
            "drift can be absorbed into the means"
        )
    else:
        x0 = [math.log(g0)] if symmetric else [math.log(g0), math.log(g0)]
        bounds = [(math.log(lo), math.log(hi))] * len(x0)
        nll_args = (v, dt_steps, mu0, mu1, sigma0, sigma1, symmetric, emission_spec)
        if symmetric:
            opt = optimize.minimize_scalar(
                lambda lr: _hmm_nll(np.asarray([lr]), *nll_args),
                bounds=bounds[0],
                method="bounded",
                options={"xatol": 1e-8},
            )
            opt.x = np.asarray([opt.x])
        else:
            opt = optimize.minimize(
                _hmm_nll,
                x0,
                args=nll_args,
                method="L-BFGS-B",
                bounds=bounds,
            )
            if not (opt.success and np.all(np.isfinite(opt.x)) and math.isfinite(float(opt.fun))):
                warnings.append("L-BFGS-B rate fit did not converge; retried with Powell")
                opt = optimize.minimize(
                    _hmm_nll,
                    x0,
                    args=nll_args,
                    method="Powell",
                    bounds=bounds,
                    options={"xtol": 1e-7, "ftol": 1e-9},
                )
        log_rates = np.asarray(opt.x)[: len(x0)]

    optimizer_ok = bool(
        opt.success and np.all(np.isfinite(opt.x)) and math.isfinite(float(opt.fun))
    )
    if not optimizer_ok:
        reasons.append(f"HMM optimizer failed: {getattr(opt, 'message', 'non-finite result')}")
        result["unidentifiable_reasons"] = reasons
        result["warnings"].append("HMM optimization did not converge")
        return result

    if symmetric:
        g01 = g10 = math.exp(log_rates[0])
    else:
        g01, g10 = math.exp(log_rates[0]), math.exp(log_rates[1])
    loglik = -float(opt.fun)

    fb = hmm_forward_backward(
        v, dt_steps, g01, g10, mu0, mu1, sigma0, sigma1, emission_spec=emission_spec
    )
    post = fb["posteriors"]
    ambiguity = float(np.mean(1.0 - post.max(axis=1)))
    occupancy = post.mean(axis=0)

    viterbi = (
        hmm_viterbi(v, dt_steps, g01, g10, mu0, mu1, sigma0, sigma1, emission_spec=emission_spec)
        if compute_viterbi
        else None
    )
    n_trans = int(np.count_nonzero(np.diff(viterbi))) if viterbi is not None else 0

    # Pairwise posterior xi_t(i,j), not a product of adjacent marginals.
    # Adjacent hidden states are correlated through the transition matrix.
    le = _log_emissions_from_spec(v, emission_spec)
    lt = _step_log_transitions(g01, g10, dt_steps)
    exp_trans = 0.0
    for k_step in range(n - 1):
        log_xi = (
            fb["log_alpha"][k_step, :, None]
            + lt[k_step]
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
    at_bound = any(lr <= log_lo + 1e-3 or lr >= log_hi - 1e-3 for lr in log_rates)
    if at_bound:
        reasons.append(
            "fitted rate pinned to a fit bound; the likelihood does not "
            "constrain the rate inside the allowed range"
        )
    result["rate_at_bound"] = bool(at_bound)

    # Hessian errors in log-rate space via central finite differences.
    def nll_rates(lr):
        return _hmm_nll(lr, v, dt_steps, mu0, mu1, sigma0, sigma1, symmetric, emission_spec)

    errs = [float("nan")] * len(log_rates)
    if not at_bound:
        try:
            h = 1e-3
            k = len(log_rates)
            H = np.zeros((k, k))
            f0 = nll_rates(log_rates)
            for i in range(k):
                ei = np.zeros(k)
                ei[i] = h
                for j in range(i, k):
                    ej = np.zeros(k)
                    ej[j] = h
                    if i == j:
                        H[i, i] = (
                            nll_rates(log_rates + ei) - 2 * f0 + nll_rates(log_rates - ei)
                        ) / h**2
                    else:
                        H[i, j] = H[j, i] = (
                            nll_rates(log_rates + ei + ej)
                            - nll_rates(log_rates + ei - ej)
                            - nll_rates(log_rates - ei + ej)
                            + nll_rates(log_rates - ei - ej)
                        ) / (4 * h**2)
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
            g01 * e if math.isfinite(e) else float("nan")
        )
    else:
        result["gamma01_err_hz"] = g01 * errs[0] if math.isfinite(errs[0]) else float("nan")
        result["gamma10_err_hz"] = g10 * errs[1] if math.isfinite(errs[1]) else float("nan")

    # Optional parametric bootstrap (deterministic via seed).
    if n_boot and not reasons:
        rng = np.random.default_rng(seed)
        boots = []
        for _ in range(int(n_boot)):
            sim = simulate_telegraph_trace(
                n=n,
                dt_s=dt_steps,
                gamma01_hz=g01,
                gamma10_hz=g10,
                mu0=0.0,
                mu1=1.0,
                sigma0=1e-9,
                sigma1=1e-9,
                seed=int(rng.integers(0, 2**31 - 1)),
            )
            if emission_spec["model"] == "ge_mixture":
                hidden = sim["states"]
                p_e = np.where(
                    hidden == 0, emission_spec["p_e_state0"], emission_spec["p_e_state1"]
                )
                prepared_e = rng.random(n) < p_e
                sim_v = rng.normal(
                    np.where(prepared_e, emission_spec["mu_e"], emission_spec["mu_g"]),
                    np.where(prepared_e, emission_spec["sigma_e"], emission_spec["sigma_g"]),
                )
            else:
                hidden = sim["states"]
                sim_v = rng.normal(
                    np.where(hidden == 0, emission_spec["mu0"], emission_spec["mu1"]),
                    np.where(hidden == 0, emission_spec["sigma0"], emission_spec["sigma1"]),
                )
            x0b = [math.log(g01)] if symmetric else [math.log(g01), math.log(g10)]
            boot_args = (sim_v, dt_steps, mu0, mu1, sigma0, sigma1, symmetric, emission_spec)
            boot_bounds = [(math.log(lo), math.log(hi))] * len(x0b)
            if symmetric:
                ob = optimize.minimize_scalar(
                    lambda lr: _hmm_nll(np.asarray([lr]), *boot_args),
                    bounds=boot_bounds[0],
                    method="bounded",
                    options={"xatol": 1e-8},
                )
                ob.x = np.asarray([ob.x])
            else:
                ob = optimize.minimize(
                    _hmm_nll,
                    x0b,
                    args=boot_args,
                    method="L-BFGS-B",
                    bounds=boot_bounds,
                )
                if not (ob.success and np.all(np.isfinite(ob.x))):
                    ob = optimize.minimize(
                        _hmm_nll,
                        x0b,
                        args=boot_args,
                        method="Powell",
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
                "gamma01_hz": dict(
                    zip(("p16", "p50", "p84"), np.percentile(boots[:, 0], [16, 50, 84]))
                ),
                "gamma10_hz": dict(
                    zip(("p16", "p50", "p84"), np.percentile(boots[:, 1], [16, 50, 84]))
                ),
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
    result.update(
        {
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
        }
    )
    if ambiguity > 0.25:
        warnings.append(
            f"posterior ambiguity {ambiguity:.2f} > 0.25: state assignments "
            "are individually unreliable even if rates are constrained"
        )
    return result
