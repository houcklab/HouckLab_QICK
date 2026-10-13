"""Undriven single-shot analysis: IQ-cloud blob detection and telegraph time-series statistics."""

import math

import numpy as np

from qicklab.analysis.rates import autocorrelation_rate_us, rate_vs_bin_size_us


def analyze_undriven_cloud(i_shots, q_shots, min_separation_sigma=2.0,
                           random_state=0):
    """Cloud stats + 1- vs 2-Gaussian BIC test on the principal-axis projection.

    n_blobs is 2 only if BIC prefers it AND separation >= min_separation_sigma;
    0 if the fit failed.
    """
    iq = np.column_stack([np.asarray(i_shots, dtype=float).ravel(),
                          np.asarray(q_shots, dtype=float).ravel()])
    n_shots = len(iq)

    out = {
        "n_shots": n_shots,
        "center": np.array([np.nan, np.nan]),
        "cov": np.full((2, 2), np.nan),
        "axis": np.array([np.nan, np.nan]),
        "axis_angle": np.nan,
        "projection": np.full(n_shots, np.nan),
        "n_blobs": 0,
        "blob_weights": np.array([np.nan, np.nan]),
        "blob_means_proj": np.array([np.nan, np.nan]),
        "blob_sigmas_proj": np.array([np.nan, np.nan]),
        "blob_centers_iq": np.full((2, 2), np.nan),
        "separation_sigma": np.nan,
        "secondary_population": np.nan,
        "bic_1": np.nan,
        "bic_2": np.nan,
        "labels": np.zeros(n_shots, dtype=int),
        "rms_radius": np.nan,
        "sigma_along_axis": np.nan,
        "sigma_across_axis": np.nan,
    }
    if n_shots < 2:
        return out

    center = np.median(iq, axis=0)
    cov = np.cov(iq, rowvar=False)
    out["center"] = center
    out["cov"] = cov

    eigvals, eigvecs = np.linalg.eigh(cov)
    order = np.argsort(eigvals)[::-1]
    eigvals = eigvals[order]
    axis = eigvecs[:, order][:, 0]
    if axis[0] < 0:  # fix the sign so repeated runs project the same way
        axis = -axis

    diff = iq - center
    proj = diff @ axis
    out["axis"] = axis
    out["axis_angle"] = float(np.arctan2(axis[1], axis[0]))
    out["projection"] = proj
    out["rms_radius"] = float(np.sqrt(np.mean(np.sum(diff ** 2, axis=1))))
    out["sigma_along_axis"] = float(np.sqrt(max(eigvals[0], 0.0)))
    out["sigma_across_axis"] = float(np.sqrt(max(eigvals[1], 0.0)))

    if np.std(proj) <= 0:
        # sklearn's reg_covar would floor the variance and return a
        # plausible-looking fit on a dead readout, so bail out first.
        print("[UndrivenSingleShot] zero spread in the IQ cloud - check that the "
              "readout tone is actually reaching the ADC.")
        out["n_blobs"] = 1
        out["blob_weights"] = np.array([1.0, 0.0])
        out["blob_means_proj"] = np.array([0.0, np.nan])
        out["blob_sigmas_proj"] = np.array([0.0, np.nan])
        out["blob_centers_iq"] = np.array([center, [np.nan, np.nan]])
        out["secondary_population"] = 0.0
        out["separation_sigma"] = 0.0
        return out

    try:
        from sklearn.mixture import GaussianMixture

        x = proj.reshape(-1, 1)
        gm1 = GaussianMixture(n_components=1, random_state=random_state).fit(x)
        gm2 = GaussianMixture(n_components=2, random_state=random_state,
                              n_init=5).fit(x)
        bic1 = float(gm1.bic(x))
        bic2 = float(gm2.bic(x))
        out["bic_1"] = bic1
        out["bic_2"] = bic2

        means2 = gm2.means_.ravel()
        sigmas2 = np.sqrt(gm2.covariances_.ravel())
        weights2 = gm2.weights_.ravel()
        # order by projection so component 0 is always the same side
        order2 = np.argsort(means2)
        means2, sigmas2, weights2 = means2[order2], sigmas2[order2], weights2[order2]

        mean_sigma = float(np.mean(sigmas2))
        separation = float(abs(means2[1] - means2[0]))
        separation_sigma = separation / mean_sigma if mean_sigma > 0 else np.inf
        out["separation_sigma"] = separation_sigma

        two_blobs = (bic2 < bic1) and (separation_sigma >= min_separation_sigma)

        if two_blobs:
            labels2 = gm2.predict(x)
            # remap predict()'s component ids onto the sorted ordering
            remap = np.empty(2, dtype=int)
            remap[order2] = np.arange(2)
            labels = remap[labels2]
            minor = int(np.argmin(weights2))  # minority component = "secondary"
            out["n_blobs"] = 2
            out["blob_weights"] = weights2
            out["blob_means_proj"] = means2
            out["blob_sigmas_proj"] = sigmas2
            out["blob_centers_iq"] = np.array([center + m * axis for m in means2])
            out["secondary_population"] = float(weights2[minor])
            out["labels"] = labels
        else:
            mean1 = float(gm1.means_.ravel()[0])
            sigma1 = float(np.sqrt(gm1.covariances_.ravel()[0]))
            out["n_blobs"] = 1
            out["blob_weights"] = np.array([1.0, 0.0])
            out["blob_means_proj"] = np.array([mean1, np.nan])
            out["blob_sigmas_proj"] = np.array([sigma1, np.nan])
            out["blob_centers_iq"] = np.array([center + mean1 * axis,
                                               [np.nan, np.nan]])
            out["secondary_population"] = 0.0
            out["labels"] = np.zeros(n_shots, dtype=int)

    except Exception as err:
        print(f"[UndrivenSingleShot] blob fit failed ({err}); "
              f"reporting cloud statistics only.")

    return out


def block_average_shots(i_shots, q_shots, n_avg):
    """Mean of non-overlapping blocks of n_avg consecutive shots (noise ~1/sqrt(n)).

    Trailing partial block is dropped. Returns (i_avg, q_avg, index_center,
    n_dropped); index_center is on the RAW shot index axis.
    """
    i = np.asarray(i_shots, dtype=float).ravel()
    q = np.asarray(q_shots, dtype=float).ravel()
    if i.size != q.size:
        raise ValueError("i_shots and q_shots must have the same length")
    n_avg = int(n_avg)
    if n_avg < 1:
        raise ValueError(f"shot_average must be >= 1, got {n_avg}")

    n_blocks = i.size // n_avg
    if n_blocks < 2:
        raise ValueError(
            f"shot_average={n_avg} leaves only {n_blocks} averaged point(s) "
            f"from {i.size} shots; lower shot_average or raise cfg['shots']"
        )
    keep = n_blocks * n_avg
    i_avg = i[:keep].reshape(n_blocks, n_avg).mean(axis=1)
    q_avg = q[:keep].reshape(n_blocks, n_avg).mean(axis=1)
    index_center = np.arange(n_blocks) * n_avg + (n_avg - 1) / 2.0
    return i_avg, q_avg, index_center, int(i.size - keep)


def project_onto_axis(i_shots, q_shots, center, axis):
    iq = np.column_stack([np.asarray(i_shots, dtype=float).ravel(),
                          np.asarray(q_shots, dtype=float).ravel()])
    return (iq - np.asarray(center, dtype=float)) @ np.asarray(axis, dtype=float)


def two_gaussian_threshold(means, sigmas, weights):
    """ML decision boundary between two 1-D Gaussians: the root of
    w0*N(x;m0,s0) == w1*N(x;m1,s1) lying between the means; nan if unusable.
    """
    means = np.asarray(means, dtype=float)
    sigmas = np.asarray(sigmas, dtype=float)
    weights = np.asarray(weights, dtype=float)
    if means.size < 2 or not np.all(np.isfinite(means[:2])):
        return float("nan")
    if not np.all(np.isfinite(sigmas[:2])) or np.any(sigmas[:2] <= 0):
        return float("nan")
    if not np.all(np.isfinite(weights[:2])) or np.any(weights[:2] <= 0):
        return float("nan")

    m0, m1 = float(means[0]), float(means[1])
    s0, s1 = float(sigmas[0]), float(sigmas[1])
    w0, w1 = float(weights[0]), float(weights[1])
    lo, hi = (m0, m1) if m0 <= m1 else (m1, m0)

    # (x-m1)^2/(2 s1^2) - (x-m0)^2/(2 s0^2) + log(w0/s0) - log(w1/s1) = 0
    a = 1.0 / (2 * s1 ** 2) - 1.0 / (2 * s0 ** 2)
    b = -m1 / s1 ** 2 + m0 / s0 ** 2
    c = (m1 ** 2 / (2 * s1 ** 2) - m0 ** 2 / (2 * s0 ** 2)
         + math.log(w0 / s0) - math.log(w1 / s1))

    if abs(s0 - s1) <= 1e-9 * (s0 + s1):
        # equal widths: a == 0, so the quadratic branch would divide by ~0
        if abs(b) < 1e-300:
            return float("nan")
        # Returned even when it falls outside [m0, m1], which is where the ML
        # boundary genuinely sits once one weight dominates (w0/w1 > e^(sep^2/2)).
        # Clamping to the midpoint there mislabels the majority blob's tail and
        # inflates the switching rate several-fold.
        return float(-c / b)

    disc = b ** 2 - 4 * a * c
    if disc < 0:
        return float(0.5 * (m0 + m1))
    sq = math.sqrt(disc)
    roots = [(-b + sq) / (2 * a), (-b - sq) / (2 * a)]
    inside = [r for r in roots if lo <= r <= hi]
    if inside:
        return float(inside[0])
    # both roots in the tails (very unequal widths): the nearer one still
    # separates the blobs, the midpoint does not
    return float(min(roots, key=lambda r: min(abs(r - lo), abs(r - hi))))


def analyze_undriven_timeseries(cloud, dt_us, raw_projection=None,
                                raw_dt_us=None,
                                bin_sizes=(1, 2, 4, 8, 16, 32, 64),
                                min_samples_per_dwell=5.0,
                                min_transitions=10):
    """Telegraph statistics for cloud['projection'] at sample period dt_us
    (= rep_period * shot_average).

    raw_projection/raw_dt_us: the same axis and center un-averaged, used for the
    ACF and the bin sweep. Every rate field is nan unless the cloud resolved
    two blobs.
    """
    warnings = []
    proj = np.asarray(cloud.get("projection"), dtype=float).ravel()
    n = proj.size
    n_blobs = int(cloud.get("n_blobs", 0))
    dt_us = float(dt_us)

    out = {
        "dt_us": dt_us,
        "n_samples": n,
        "threshold": float("nan"),
        "states": np.zeros(n, dtype=int),
        "n_transitions": 0,
        "n_01": 0,
        "n_10": 0,
        "occupancy": np.array([np.nan, np.nan]),
        "time_in_state_us": np.array([np.nan, np.nan]),
        "dwell_mean_us": np.array([np.nan, np.nan]),
        "dwell_counted": np.array([0, 0]),
        "gamma01_hz": float("nan"),
        "gamma10_hz": float("nan"),
        "gamma_mean_hz": float("nan"),
        "tau_dwell_us": np.array([np.nan, np.nan]),
        "samples_per_dwell": float("nan"),
        "acf_tau_corr_us": float("nan"),
        "acf_gamma_hz": float("nan"),
        "acf_amplitude": float("nan"),
        "acf_noise_variance": float("nan"),
        "acf_fit_ok": False,
        "acf_lags_us": np.zeros(0),
        "acf": np.zeros(0),
        "bin_sizes": np.zeros(0, dtype=int),
        "bin_dt_us": np.zeros(0),
        "bin_rate_hz": np.zeros(0),
        "bin_n_switches": np.zeros(0, dtype=int),
        "warnings": warnings,
    }
    if n == 0:
        return out

    if raw_projection is not None and raw_dt_us:
        acf_trace, acf_dt = np.ravel(np.asarray(raw_projection, float)), float(raw_dt_us)
    else:
        acf_trace, acf_dt = proj, dt_us
    acf = autocorrelation_rate_us(acf_trace, acf_dt)
    warnings.extend(acf["warnings"])
    out.update({
        "acf_tau_corr_us": acf["tau_corr_us"],
        "acf_gamma_hz": acf["gamma_hz"],
        "acf_amplitude": acf["amplitude"],
        "acf_noise_variance": acf["noise_variance"],
        "acf_fit_ok": bool(acf["fit_ok"]),
        "acf_lags_us": acf["lags_us"],
        "acf": acf["acf"],
    })

    if n_blobs != 2:
        warnings.append(
            "the cloud did not resolve two blobs, so there is no state to "
            "assign: switching statistics are withheld (nan). The analog trace "
            "and its autocorrelation are still shown."
        )
        return out

    threshold = two_gaussian_threshold(cloud["blob_means_proj"],
                                       cloud["blob_sigmas_proj"],
                                       cloud["blob_weights"])
    out["threshold"] = threshold
    if not np.isfinite(threshold):
        warnings.append("could not place a decision threshold between the blobs")
        return out

    sweep = rate_vs_bin_size_us(acf_trace, acf_dt, threshold, bin_sizes=bin_sizes)
    out.update({
        "bin_sizes": sweep["bin_sizes"],
        "bin_dt_us": sweep["bin_dt_us"],
        "bin_rate_hz": sweep["rate_hz"],
        "bin_n_switches": sweep["n_switches"],
    })

    states = (proj > threshold).astype(int)
    out["states"] = states
    n0 = int(np.count_nonzero(states == 0))
    n1 = n - n0
    t0_us, t1_us = n0 * dt_us, n1 * dt_us
    out["time_in_state_us"] = np.array([t0_us, t1_us])
    out["occupancy"] = np.array([n0 / n, n1 / n])

    steps = np.diff(states)
    n_01 = int(np.count_nonzero(steps == 1))
    n_10 = int(np.count_nonzero(steps == -1))
    out["n_01"], out["n_10"] = n_01, n_10
    out["n_transitions"] = n_01 + n_10

    # Continuous-time Markov ML rates: gamma_ij = (transitions out of i) / (time in i)
    g01 = n_01 / (t0_us * 1e-6) if t0_us > 0 else float("nan")
    g10 = n_10 / (t1_us * 1e-6) if t1_us > 0 else float("nan")
    out["gamma01_hz"], out["gamma10_hz"] = g01, g10
    with np.errstate(divide="ignore", invalid="ignore"):
        out["tau_dwell_us"] = np.array([
            1e6 / g01 if np.isfinite(g01) and g01 > 0 else np.nan,
            1e6 / g10 if np.isfinite(g10) and g10 > 0 else np.nan,
        ])
    if np.isfinite(g01) and np.isfinite(g10):
        out["gamma_mean_hz"] = float(0.5 * (g01 + g10))

    # Empirical mean dwell from interior runs only (the first and last run are
    # cut off by the record boundaries and would drag the mean down).
    edges = np.flatnonzero(steps) + 1
    starts = np.concatenate([[0], edges])
    ends = np.concatenate([edges, [n]])
    runs = list(zip(starts, ends))
    interior = runs[1:-1] if len(runs) >= 3 else []
    dwells = {0: [], 1: []}
    for a, b in interior:
        dwells[int(states[a])].append((b - a) * dt_us)
    out["dwell_mean_us"] = np.array([
        float(np.mean(dwells[0])) if dwells[0] else np.nan,
        float(np.mean(dwells[1])) if dwells[1] else np.nan,
    ])
    out["dwell_counted"] = np.array([len(dwells[0]), len(dwells[1])])

    finite_tau = out["tau_dwell_us"][np.isfinite(out["tau_dwell_us"])]
    if finite_tau.size:
        out["samples_per_dwell"] = float(finite_tau.min() / dt_us)

    if out["n_transitions"] < min_transitions:
        warnings.append(
            f"only {out['n_transitions']} threshold transitions in the record "
            f"(< {min_transitions}): the rate is not constrained"
        )
    if np.isfinite(out["samples_per_dwell"]) and \
            out["samples_per_dwell"] < min_samples_per_dwell:
        warnings.append(
            f"shortest dwell is only {out['samples_per_dwell']:.1f} samples "
            f"(< {min_samples_per_dwell:g}): switching is close to the sampling "
            "period, so transitions are being missed and the rate is a LOWER "
            "bound. Shorten relax_delay to sample faster."
        )
    if sweep["rate_hz"].size >= 2:
        finite = np.isfinite(sweep["rate_hz"])
        if finite.sum() >= 2:
            r = sweep["rate_hz"][finite]
            if r[0] > 0 and r[-1] < 0.5 * r[0]:
                warnings.append(
                    f"switch rate falls from {r[0]:.1f} Hz to {r[-1]:.1f} Hz "
                    "across the bin-size sweep: crossings at small bin sizes "
                    "are dominated by readout noise. Read the rate off a "
                    "plateau at larger averaging and set shot_average there; "
                    "if the sweep never flattens, the record has no resolvable "
                    "telegraph"
                )
    return out
