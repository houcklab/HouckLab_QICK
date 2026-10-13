"""Switching-rate estimators: slow-drift removal, telegraph simulation, ACF/PSD and bin-size rates."""

import math

import numpy as np
from scipy import optimize, signal
from scipy.ndimage import uniform_filter1d


def remove_slow_drift(v, dt_s, drift_timescale_s, expected_dwell_s=None, min_timescale_ratio=20.0):
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
                f"drift window {drift_timescale_s * 1e3:.1f} ms is only "
                f"{ratio:.1f}x the expected dwell "
                f"{expected_dwell_s * 1e3:.1f} ms (< {min_timescale_ratio:g}x): "
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
    return np.array(
        [
            [pi0 + pi1 * decay, pi1 - pi1 * decay],
            [pi0 - pi0 * decay, pi1 + pi0 * decay],
        ]
    )


def simulate_telegraph_trace(
    n, dt_s, gamma01_hz, gamma10_hz, mu0, mu1, sigma0, sigma1, seed=0, drift=None, start_state=None
):
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
    uniq, inv = (
        np.unique(dt_steps, return_inverse=True) if n > 1 else (np.zeros(0), np.zeros(0, dtype=int))
    )
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
    out = {
        "tau_corr_s": float("nan"),
        "gamma_hz": float("nan"),
        "amplitude": float("nan"),
        "noise_variance": float("nan"),
        "acf": np.zeros(0),
        "lags_s": np.zeros(0),
        "fit_ok": False,
        "warnings": warnings,
    }
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
        below = np.flatnonzero(acf[1:] < ref / math.e**2)
        kmax = int(below[0] + 1) if below.size else n // 4
        kmax = int(np.clip(kmax, min_points + 1, n // 4))
    else:
        kmax = int(np.clip(round(max_lag_s / dt_s), min_points + 1, n // 4))

    lags = np.arange(1, kmax + 1) * dt_s
    y = acov[1 : kmax + 1]
    out["acf"] = acf[: kmax + 1]
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
            lags[pos],
            y[pos],
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
            f"fitted tau_corr {tau * 1e6:.1f} us is below the sample period; "
            "the switching is unresolved at this cadence"
        )
    noise_var = float(c0 - A)  # zero-lag excess over the telegraph amplitude
    out.update(
        {
            "tau_corr_s": tau,
            "gamma_hz": 1.0 / (2.0 * tau),
            "amplitude": A,
            "noise_variance": noise_var,
            "fit_ok": True,
        }
    )
    if noise_var > 4 * A:
        warnings.append(
            f"readout-noise variance is {noise_var / A:.1f}x the telegraph "
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
    out = {
        "f_corner_hz": float("nan"),
        "gamma_hz": float("nan"),
        "s0": float("nan"),
        "white_floor": float("nan"),
        "freqs_hz": np.zeros(0),
        "psd": np.zeros(0),
        "fit_ok": False,
        "warnings": warnings,
    }
    n = v.size
    if n < 256:
        warnings.append("trace too short for Welch PSD analysis")
        return out
    fs = 1.0 / float(dt_s)
    if nperseg is None:
        nperseg = int(min(max(256, 2 ** math.floor(math.log2(n / 8))), n))
    freqs, psd = signal.welch(v - v.mean(), fs=fs, nperseg=nperseg, detrend="constant")
    keep = (freqs > 0) & (freqs <= f_max_factor * fs)
    f, p = freqs[keep], psd[keep]
    out["freqs_hz"], out["psd"] = f, p
    if f.size < 8:
        warnings.append("too few PSD points to fit")
        return out

    def model(fx, log_s0, log_fc, log_w):
        return np.exp(log_s0) / (1.0 + (fx / np.exp(log_fc)) ** 2) + np.exp(log_w)

    # Fit in log-power space so the (log-uniform) high-frequency floor does
    # not dominate the least squares.
    def resid(theta):
        return np.log(model(f, *theta)) - np.log(p)

    s0_guess = float(np.median(p[: max(3, f.size // 20)]))
    w_guess = float(np.median(p[-max(3, f.size // 20) :]))
    fc_guess = float(f[min(np.searchsorted(-p, -s0_guess / 2), f.size - 1)])
    fc_guess = float(np.clip(fc_guess, f[0], f[-1]))
    try:
        sol = optimize.least_squares(
            resid,
            x0=[
                math.log(max(s0_guess, 1e-300)),
                math.log(max(fc_guess, f[0])),
                math.log(max(w_guess, 1e-300)),
            ],
            bounds=(
                [-np.inf, math.log(f[0] / 10.0), -np.inf],
                [np.inf, math.log(f[-1] * 10.0), np.inf],
            ),
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
    out.update(
        {
            "f_corner_hz": float(fc),
            "gamma_hz": float(math.pi * fc),
            "s0": float(s0),
            "white_floor": float(white),
            "fit_ok": True,
        }
    )
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
            rates.append(float("nan"))
            counts.append(0)
            bin_us.append(b * dt_s * 1e6)
            continue
        vb = v[: nb * b].reshape(nb, b).mean(axis=1)
        bits = (vb > threshold).astype(int)
        n_sw = int(np.count_nonzero(np.diff(bits)))
        total_t = (nb - 1) * b * dt_s
        rates.append(n_sw / total_t if total_t > 0 else float("nan"))
        counts.append(n_sw)
        bin_us.append(b * dt_s * 1e6)
    return {"bin_sizes": list(bin_sizes), "bin_us": bin_us, "rate_hz": rates, "n_switches": counts}


def autocorrelation_rate_us(v, dt_us, min_points=5):
    """Rate from the ACF decay: C(t)=A*exp(-t/tau_corr), tau_corr=1/(2*gamma),
    tau_dwell=1/gamma.

    Lag 0 is EXCLUDED from the fit: it carries the additive readout-noise
    variance, reported separately as `noise_variance`.
    """
    v = np.ravel(np.asarray(v, dtype=float))
    warnings = []
    out = {
        "tau_corr_us": float("nan"),
        "gamma_hz": float("nan"),
        "amplitude": float("nan"),
        "noise_variance": float("nan"),
        "acf": np.zeros(0),
        "lags_us": np.zeros(0),
        "fit_ok": False,
        "warnings": warnings,
    }
    n = v.size
    if n < 32:
        warnings.append("trace too short for autocorrelation analysis")
        return out
    dt_us = float(dt_us)
    x = v - v.mean()
    nfft = int(2 ** math.ceil(math.log2(2 * n)))
    X = np.fft.rfft(x, nfft)
    acov = np.fft.irfft(X * np.conj(X), nfft)[:n] / n
    c0 = acov[0]
    if c0 <= 0:
        warnings.append("zero-variance trace")
        return out

    acf = acov / c0
    ref = acf[1] if n > 1 else 0.0
    below = np.flatnonzero(acf[1:] < ref / math.e**2)
    kmax = int(below[0] + 1) if below.size else n // 4
    kmax = int(np.clip(kmax, min_points + 1, max(n // 4, min_points + 1)))
    kmax = min(kmax, n - 1)

    lags = np.arange(1, kmax + 1) * dt_us
    y = acov[1 : kmax + 1]
    out["acf"] = acf[: kmax + 1]
    out["lags_us"] = np.arange(kmax + 1) * dt_us
    pos = y > 0
    if pos.sum() < min_points:
        warnings.append(
            "too few positive autocorrelation lags to fit; the "
            "telegraph amplitude may be below the readout noise"
        )
        return out
    try:
        popt, _ = optimize.curve_fit(
            lambda t, A, tau: A * np.exp(-t / tau),
            lags[pos],
            y[pos],
            p0=[max(y[0], 1e-12), max(lags[pos][-1] / 3.0, dt_us)],
            maxfev=10000,
        )
        A, tau_us = float(popt[0]), float(abs(popt[1]))
    except (RuntimeError, ValueError):
        warnings.append("autocorrelation exponential fit failed")
        return out
    if A <= 0 or tau_us <= 0:
        warnings.append("autocorrelation fit returned non-physical parameters")
        return out
    if tau_us < dt_us:
        warnings.append(
            f"fitted tau_corr {tau_us:.1f} us is below the {dt_us:.1f} us shot "
            "period; any switching is unresolved at this cadence"
        )
    noise_var = float(c0 - A)
    out.update(
        {
            "tau_corr_us": tau_us,
            "gamma_hz": 1e6 / (2.0 * tau_us),
            "amplitude": A,
            "noise_variance": noise_var,
            "fit_ok": True,
        }
    )
    if A > 0 and noise_var > 4 * A:
        warnings.append(
            f"readout-noise variance is {noise_var / A:.1f}x the telegraph "
            "amplitude; the autocorrelation rate is noise-dominated"
        )
    return out


def rate_vs_bin_size_us(v, dt_us, threshold, bin_sizes=(1, 2, 4, 8, 16, 32, 64)):
    """Threshold-crossing rate vs block-average size (the shot_average sweep).

    Falling rate = noise crossings averaging out; a plateau = real telegraph.
    """
    v = np.ravel(np.asarray(v, dtype=float))
    dt_us = float(dt_us)
    sizes, dts, rates, counts = [], [], [], []
    for b in bin_sizes:
        b = int(b)
        if b < 1:
            continue
        n_bins = v.size // b
        sizes.append(b)
        dts.append(b * dt_us)
        if n_bins < 4 or not np.isfinite(threshold):
            rates.append(float("nan"))
            counts.append(0)
            continue
        vb = v[: n_bins * b].reshape(n_bins, b).mean(axis=1)
        bits = (vb > threshold).astype(int)
        n_switch = int(np.count_nonzero(np.diff(bits)))
        span_us = n_bins * b * dt_us
        counts.append(n_switch)
        rates.append(n_switch / (span_us * 1e-6) if span_us > 0 else float("nan"))
    return {
        "bin_sizes": np.asarray(sizes, dtype=int),
        "bin_dt_us": np.asarray(dts, dtype=float),
        "rate_hz": np.asarray(rates, dtype=float),
        "n_switches": np.asarray(counts, dtype=int),
    }
