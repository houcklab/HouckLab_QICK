"""Offline analysis of raw, host-timestamped q3 millisecond sentinel streams.

The analysis respects stream-bank gaps and labels pulse-tube effects only
when an independent compressor frequency is supplied. A screen candidate is
not proof that a microscopic TLS moved; qubit flux noise remains a confound.
"""

import argparse
import json
import math
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp


MIN_SLOPE_PER_MHZ = .02


def position_signals(values, baseline, signed_line_shift_slopes):
    """Use signed slopes: both flank-normalized shifts have the same sign."""
    slopes = {name: float(signed_line_shift_slopes[name])
              for name in ("A_minus", "A_plus", "B")}
    if any(not math.isfinite(value) or abs(value) < MIN_SLOPE_PER_MHZ
           for value in slopes.values()):
        raise ValueError("dither slope is too small for a line-position estimate")
    deltas = {name: np.asarray(values[name], dtype=float) -
              np.asarray(baseline[name], dtype=float)
              for name in slopes}
    a_minus = deltas["A_minus"]/slopes["A_minus"]
    a_plus = deltas["A_plus"]/slopes["A_plus"]
    return {"X_A_mhz": .5*(a_minus+a_plus),
            "X_B_mhz": deltas["B"]/slopes["B"],
            "Y_A": .5*(deltas["A_minus"]+deltas["A_plus"]),
            "A_minus_residual": deltas["A_minus"],
            "A_plus_residual": deltas["A_plus"]}


def timing_quality(observed_utc_ns, *, valid=None):
    stamps = np.asarray(observed_utc_ns, dtype=np.int64)
    if stamps.ndim != 1 or stamps.size < 3:
        raise ValueError("at least three shot timestamps are required")
    if valid is None:
        valid = np.ones(stamps.size, dtype=bool)
    valid = np.asarray(valid, dtype=bool)
    if valid.shape != stamps.shape:
        raise ValueError("timing validity length differs from shots")
    delta = np.diff(stamps)*1e-9
    # Invalidated pairs include callbacks bunched inside one host poll.
    positive = delta[(delta > 0) & valid[:-1] & valid[1:]]
    if not positive.size:
        raise ValueError("unresolved host shot times")
    period = float(np.median(np.sort(positive)[:max(1, int(.75*len(positive)))]))
    regular = positive[positive <= 2*period]
    jitter_mad = (float(np.median(np.abs(regular-np.median(regular))))
                  if regular.size >= 3 else 0.0)
    jitter_limit = (.3/(2*math.pi*jitter_mad)
                    if jitter_mad > 0 else math.inf)
    return {"median_period_s": period,
            "max_science_hz": min(200.0, .4/period, jitter_limit),
            "poll_jitter_mad_s": jitter_mad,
            "gap_count": int(np.count_nonzero(delta > 2*period)),
            "valid_fraction": float(np.mean(valid)),
            "timing_limit": "host polling and resident-stream bank handshakes"}


def motion_candidate(*, excess_sigma_first, excess_sigma_second,
                     flank_cross_sigma_first, flank_cross_sigma_second,
                     nuisance_coherence, controls_valid):
    passed = bool(float(excess_sigma_first) >= 5 and
                  float(excess_sigma_second) >= 5 and
                  float(flank_cross_sigma_first) >= 3 and
                  float(flank_cross_sigma_second) >= 3 and
                  float(nuisance_coherence) < .5 and controls_valid)
    return {"candidate": passed,
            "reason": "requires noise-subtracted excess and significant negative flank cross spectrum in both halves, low control coherence, and valid closing controls"}


def binomial_position_white_floor(probabilities, slopes, period_s):
    """Expected one-sided PSD from two Bernoulli reads at each A flank."""
    variance = .125*sum(float(probabilities[site]) *
                        (1-float(probabilities[site])) /
                        float(slopes[site])**2
                        for site in ("A_minus", "A_plus"))
    return 2*float(period_s)*variance


def bin_irregular(time_s, values, *, width_s):
    time_s = np.asarray(time_s, dtype=float)
    values = np.asarray(values, dtype=float)
    width_s = float(width_s)
    if (time_s.ndim != 1 or values.shape != time_s.shape or
            time_s.size == 0 or width_s <= 0 or
            not np.all(np.diff(time_s) >= 0)):
        raise ValueError("binned stream needs ordered times and positive width")
    index = np.floor((time_s-time_s[0])/width_s + 1e-9).astype(int)
    count = np.bincount(index, minlength=int(index[-1])+1)
    sums = np.bincount(index, weights=values, minlength=len(count))
    mean = np.divide(sums, count, out=np.full(len(count), np.nan), where=count > 0)
    centers = time_s[0] + (np.arange(len(count))+.5)*width_s
    return centers, mean, count


def pulse_tube_screen(frequency_hz, power, *, pt_frequency_hz):
    if pt_frequency_hz is None:
        return {"attribution": "unavailable_without_independent_frequency"}
    frequency = np.asarray(frequency_hz, dtype=float)
    power = np.asarray(power, dtype=float)
    matches = np.flatnonzero(np.abs(frequency-float(pt_frequency_hz)) <= .02)
    if matches.size == 0:
        return {"attribution": "frequency_outside_resolved_grid"}
    index = int(matches[np.argmax(power[matches])])
    background = float(np.median(power[np.isfinite(power)]))
    return {"attribution": "independent_frequency_test",
            "frequency_hz": float(frequency[index]),
            "power_to_median": None if background <= 0 else
            float(power[index]/background),
            "passes_snr_5": bool(background > 0 and power[index]/background > 5)}


def irregular_spectrum(time_s, channels, frequency_hz):
    """Windowed nonuniform Fourier spectra; gaps are never interpolated."""
    time_s = np.asarray(time_s, dtype=float)
    frequency_hz = np.asarray(frequency_hz, dtype=float)
    if (time_s.ndim != 1 or time_s.size < 16 or
            np.any(np.diff(time_s) <= 0) or
            np.any(frequency_hz <= 0)):
        raise ValueError("irregular spectrum needs ordered resolved shot times")
    window = np.hanning(time_s.size)
    kernel = np.exp(-2j*np.pi*frequency_hz[:, None]*(time_s-time_s[0])[None, :])
    scale = 2.0*float(np.median(np.diff(time_s)))/float(np.sum(window**2))
    fourier = {}
    power = {}
    for name, values in channels.items():
        x = np.asarray(values, dtype=float)
        if x.shape != time_s.shape or not np.all(np.isfinite(x)):
            raise ValueError(f"{name}: invalid spectrum samples")
        coefficients = kernel @ (window*(x-np.mean(x)))
        fourier[name] = coefficients
        power[name] = scale*np.abs(coefficients)**2
    return {"frequency_hz": frequency_hz, "fourier": fourier,
            "power": power, "scale": scale}


def allan_deviation(time_s, values, tau_values_s):
    result = []
    for tau in tau_values_s:
        centers, means, counts = bin_irregular(time_s, values, width_s=tau)
        paired = np.isfinite(means[:-1]) & np.isfinite(means[1:])
        differences = np.diff(means)[paired]
        allan = (float(np.sqrt(.5*np.mean(differences**2)))
                 if differences.size >= 3 else None)
        result.append({"tau_s": float(tau), "allan": allan,
                       "adjacent_pairs": int(differences.size)})
    return result


def _hmm_log_likelihood(data, means, sigma, stay):
    states = len(means)
    off = (1-stay)/(states-1)
    transition = np.full((states, states), off)
    np.fill_diagonal(transition, stay)
    log_transition = np.log(transition)
    normalization = -.5*math.log(2*math.pi) - math.log(sigma)
    alpha = np.full(states, -math.log(states))
    for observation in data:
        emission = normalization - .5*((observation-means)/sigma)**2
        alpha = emission + logsumexp(alpha[:, None]+log_transition, axis=0)
    return float(logsumexp(alpha))


def telegraph_fit(values, *, max_states=3):
    """Small symmetric-transition Gaussian HMM screen; report BIC, not certainty."""
    data = np.asarray(values, dtype=float)
    if data.ndim != 1 or data.size < 40 or not np.all(np.isfinite(data)):
        raise ValueError("HMM screen needs at least forty finite binned points")
    n = data.size
    sigma0 = max(float(np.std(data)), 1e-4)
    single_ll = float(np.sum(-.5*np.log(2*np.pi*sigma0**2) -
                             .5*((data-np.mean(data))/sigma0)**2))
    models = {"1": {"bic": float(2*math.log(n)-2*single_ll),
                     "log_likelihood": single_ll,
                     "mean": float(np.mean(data)), "sigma": sigma0}}
    for states in range(2, min(int(max_states), 3)+1):
        means0 = np.quantile(data, np.linspace(.1, .9, states))
        lower, upper = float(np.min(data)), float(np.max(data))
        bounds = [(lower-sigma0, upper+sigma0)]*states + [
            (math.log(max(sigma0/100, 1e-5)), math.log(max(sigma0*2, 1e-4))),
            (.501, .9995)]

        def objective(params):
            return -_hmm_log_likelihood(data, params[:states],
                                        math.exp(params[states]), params[-1])

        estimate = minimize(
            objective, np.r_[means0, math.log(max(sigma0/3, 1e-4)), .98],
            bounds=bounds, method="L-BFGS-B", options={"maxiter": 90})
        means = sorted(float(x) for x in estimate.x[:states])
        ll = -float(estimate.fun)
        k = states+2
        models[str(states)] = {
            "bic": float(k*math.log(n)-2*ll), "log_likelihood": ll,
            "means": means, "step_size": float(max(means)-min(means)),
            "sigma": float(math.exp(estimate.x[states])),
            "stay_probability_per_bin": float(estimate.x[-1]),
            "fit_converged": bool(estimate.success)}
    return {"models": models,
            "best_state_count": int(min(models, key=lambda key: models[key]["bic"])),
            "warning": "symmetric-transition Gaussian HMM is a screening model"}


def gaussian_block_change_points(values, *, noise_sigma=None,
                                 min_segment=5):
    """Penalized Gaussian block fit, a change-point cross-check to the HMM."""
    x = np.asarray(values, dtype=float)
    if x.ndim != 1 or x.size < 2*min_segment or x.size > 1000 or \
            not np.all(np.isfinite(x)):
        raise ValueError("Gaussian blocks need 10..1000 finite samples")
    if noise_sigma is None:
        noise_sigma = float(np.median(np.abs(np.diff(x))))/.954
    sigma = max(float(noise_sigma), 1e-6)
    length = x.size
    total = np.r_[0., np.cumsum(x)]
    square = np.r_[0., np.cumsum(x*x)]
    penalty = 2*math.log(length)
    cost = np.full(length+1, np.inf)
    parent = np.full(length+1, -1, dtype=int)
    cost[0] = -penalty
    for end in range(min_segment, length+1):
        starts = np.arange(0, end-min_segment+1)
        valid = np.isfinite(cost[starts])
        starts = starts[valid]
        if starts.size == 0:
            continue
        count = end-starts
        sums = total[end]-total[starts]
        sse = square[end]-square[starts]-sums*sums/count
        candidates = cost[starts]+np.maximum(sse, 0)/(2*sigma*sigma)+penalty
        best = int(np.argmin(candidates))
        cost[end] = candidates[best]
        parent[end] = starts[best]
    cuts = []
    cursor = length
    while parent[cursor] > 0:
        cuts.append(int(parent[cursor]))
        cursor = int(parent[cursor])
    cuts.sort()
    return {"change_indices": cuts, "noise_sigma": sigma,
            "penalty": penalty,
            "method": "penalized Gaussian blocks; not an independent TLS classifier"}


def lag_statistics(paired_subshots):
    paired = np.asarray(paired_subshots, dtype=float)
    if paired.ndim != 2 or paired.shape[1] != 2 or paired.shape[0] < 3:
        raise ValueError("lag statistics need early/late subshots across shots")
    def corr(x, y):
        if np.std(x) == 0 or np.std(y) == 0:
            return None
        return float(np.corrcoef(x, y)[0, 1])
    shot_mean = np.mean(paired, axis=1)
    return {"early_late": corr(paired[:, 0], paired[:, 1]),
            "consecutive_shots": corr(shot_mean[:-1], shot_mean[1:])}


def _project_iq(iq, axis):
    complex_iq = (np.asarray(iq[..., 0], dtype=float) +
                  1j*np.asarray(iq[..., 1], dtype=float))
    return np.real(complex_iq*np.exp(-1j*float(axis["theta_rad"])))


def pooled_calibration(calibration_paths, axis):
    """Pool dither means across interleaved blocks before slope division."""
    binary, continuous = [], []
    for path in calibration_paths:
        with np.load(path, allow_pickle=False) as payload:
            iq = np.asarray(payload["iq"])
        projection = _project_iq(iq, axis)
        ground = float(np.median(projection[:, 6]))
        span = float(np.median(projection[:, 7]))-ground
        if span <= 0:
            raise ValueError("collapsed pooled calibration readout span")
        binary.append(np.mean(projection > float(axis["threshold"]), axis=0))
        continuous.append(np.mean((projection-ground)/span, axis=0))
    if not binary:
        raise ValueError("no calibration records to pool")
    return {"binary": np.mean(binary, axis=0),
            "continuous": np.mean(continuous, axis=0)}


def derive_chunk(science_path, calibration_path, axis, *, calibration_override=None):
    """Freeze one calibration to eight raw subshots, preserving shot times."""
    with np.load(calibration_path, allow_pickle=False) as payload:
        calibration_iq = np.asarray(payload["iq"])
        calibration_order = [str(name) for name in payload["order"]]
    expected_cal = [f"{site}_{sign}" for site in ("A_minus", "A_plus", "B")
                    for sign in ("m", "p")] + ["ref_g", "ref_e"]
    if calibration_iq.ndim != 3 or calibration_iq.shape[1:] != (8, 2) or \
            calibration_order != expected_cal:
        raise ValueError("calibration IQ/order is not the eight-arm dither protocol")
    cal_projection = _project_iq(calibration_iq, axis)
    ground = float(np.median(cal_projection[:, 6]))
    excited = float(np.median(cal_projection[:, 7]))
    span = excited-ground
    if not math.isfinite(span) or span <= 0:
        raise ValueError("frozen readout-axis reference separation collapsed")
    cal_binary = np.mean(cal_projection > float(axis["threshold"]), axis=0)
    cal_continuous = np.mean((cal_projection-ground)/span, axis=0)
    if calibration_override is not None:
        cal_binary = np.asarray(calibration_override["binary"], dtype=float)
        cal_continuous = np.asarray(calibration_override["continuous"], dtype=float)

    with np.load(science_path, allow_pickle=False) as payload:
        iq = np.asarray(payload["iq"])
        order = [str(name) for name in payload["order"]]
        observed_ns = np.asarray(payload["observed_utc_ns"], dtype=np.int64)
        valid = np.asarray(payload["timing_valid"], dtype=bool)
        gaps = np.asarray(payload["gap_after_previous"], dtype=bool)
    expected_order = [f"{site}_{index}" for index, site in enumerate(
        ("A_minus", "A_plus", "B", "C", "C", "B", "A_plus", "A_minus"))]
    if iq.ndim != 3 or iq.shape[1:] != (8, 2) or order != expected_order:
        raise ValueError("science IQ/order is not the eight-arm palindrome")
    if len(observed_ns) != iq.shape[0] or valid.shape != observed_ns.shape or \
            gaps.shape != observed_ns.shape:
        raise ValueError("science IQ and host timestamp lengths differ")
    timing = timing_quality(observed_ns, valid=valid)
    projected = _project_iq(iq, axis)
    binary = (projected > float(axis["threshold"])).astype(float)
    continuous = (projected-ground)/span
    indices = {"A_minus": (0, 7), "A_plus": (1, 6),
               "B": (2, 5), "C": (3, 4)}
    derived = {}
    slopes_binary = {}
    for label, science, calibration in (("binary", binary, cal_binary),
                                        ("continuous", continuous,
                                         cal_continuous)):
        values = {site: np.mean(science[:, pair], axis=1)
                  for site, pair in indices.items()}
        baseline = {site: .5*(float(calibration[2*index]) +
                                float(calibration[2*index+1]))
                    for index, site in enumerate(("A_minus", "A_plus", "B"))}
        slopes = {site: -float(calibration[2*index+1] - calibration[2*index])
                  for index, site in enumerate(("A_minus", "A_plus", "B"))}
        if label == "binary":
            slopes_binary = slopes
        signals = position_signals(values, baseline, slopes)
        signals["C"] = values["C"]
        signals["A_minus"] = values["A_minus"]
        signals["A_plus"] = values["A_plus"]
        signals["paired"] = {site: science[:, pair]
                              for site, pair in indices.items()}
        derived[label] = signals
    return {**derived, "slopes": slopes_binary,
            "observed_utc_ns": observed_ns, "timing_valid": valid,
            "gap_after_previous": gaps, "timing": timing,
            "calibration_reference_levels": {"ground": ground,
                                             "excited": excited}}


def analyze_session(manifest_path, *, pt_frequency_hz=None,
                    compute_telegraph=True):
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "q3.tls-millisecond-sentinel.v1":
        raise ValueError("not a q3 millisecond sentinel manifest")
    if not str(manifest.get("status", "")).startswith("complete"):
        raise ValueError("sentinel acquisition must be complete before analysis")
    if "pre_readout_axis" not in manifest:
        raise ValueError("sentinel manifest lacks a frozen readout axis")
    axis = manifest["pre_readout_axis"]
    science_entries = [entry for entry in manifest["chunks"]
                       if entry["kind"] == "science" and entry["status"] == "complete"]
    null_entries = [entry for entry in manifest["chunks"]
                    if entry["kind"] == "null" and entry["status"] == "complete"]
    if len(science_entries) != 12 or len(null_entries) != 3:
        raise ValueError("complete sentinel needs 12 science and 3 null chunks")
    science = []
    calibration_paths = [entry["calibration"]["raw_npz"]
                         for entry in science_entries
                         if entry.get("calibration_report", {}).get("valid")]
    if not calibration_paths:
        raise ValueError("no usable dither calibration for analysis")
    pooled = pooled_calibration(calibration_paths, axis)
    for entry in science_entries:
        if not entry.get("calibration_report", {}).get("valid"):
            science.append(None)
            continue
        science.append(derive_chunk(entry["raw_npz"],
                                    entry["calibration"]["raw_npz"], axis,
                                    calibration_override=pooled))
    null = [derive_chunk(entry["raw_npz"], calibration_paths[-1], axis,
                         calibration_override=pooled)
            for entry in null_entries]
    valid_science = [item for item in science if item is not None]
    if len(valid_science) < 6:
        raise ValueError("fewer than six science chunks have usable dither slopes")
    bandwidth = min(item["timing"]["max_science_hz"]
                    for item in valid_science + null)
    frequencies = np.arange(.2, bandwidth+.00001, .2)
    if frequencies.size < 5:
        raise ValueError("shot cadence does not resolve the science band")

    def spectrum(item):
        keep = np.asarray(item["timing_valid"], dtype=bool)
        t = np.asarray(item["observed_utc_ns"], dtype=np.int64)[keep]
        relative = (t-t[0])*1e-9
        channels = {name: np.asarray(item["binary"][name])[keep]
                    for name in ("X_A_mhz", "X_B_mhz", "Y_A", "C",
                                 "A_minus_residual", "A_plus_residual")}
        return irregular_spectrum(relative, channels, frequencies)

    def continuous_spectrum(item):
        keep = np.asarray(item["timing_valid"], dtype=bool)
        t = np.asarray(item["observed_utc_ns"], dtype=np.int64)[keep]
        return irregular_spectrum(
            (t-t[0])*1e-9,
            {"X_A_mhz": np.asarray(item["continuous"]["X_A_mhz"])[keep]},
            frequencies)

    science_spectra = [spectrum(item) if item is not None else None
                       for item in science]
    null_spectra = [spectrum(item) for item in null]
    def floor(item):
        probabilities = {site: float(np.mean(item["binary"][site]))
                         for site in ("A_minus", "A_plus")}
        return binomial_position_white_floor(
            probabilities, item["slopes"], item["timing"]["median_period_s"])
    science_floors = [floor(item) if item is not None else None
                      for item in science]
    null_floors = [floor(item) for item in null]
    continuous_spectra = [continuous_spectrum(item)
                          for item in valid_science]
    names = ("X_A_mhz", "X_B_mhz", "Y_A", "C", "A_minus_residual",
             "A_plus_residual")
    average = {name: np.mean([s["power"][name] for s in science_spectra
                              if s is not None], axis=0) for name in names}
    null_average = {name: np.mean([s["power"][name] for s in null_spectra], axis=0)
                    for name in names}
    continuous_power = np.mean([s["power"]["X_A_mhz"]
                                for s in continuous_spectra], axis=0)
    bands = []
    boundaries = ((.2, 2.0), (2.0, 20.0), (20.0, float(bandwidth)))
    for low, high in boundaries:
        if high <= low or low >= bandwidth:
            continue
        mask = (frequencies >= low) & (frequencies < high)
        if not np.any(mask):
            continue
        null_power = np.asarray([
            float(np.mean(s["power"]["X_A_mhz"][mask]))-null_floors[index]
            for index, s in enumerate(null_spectra)])
        null_mean = float(np.mean(null_power))
        half_stats = []
        cross_stats = []
        for start in (0, 6):
            retained = [(s, science_floors[index])
                        for index, s in enumerate(science_spectra)
                        if start <= index < start+6 and s is not None]
            if len(retained) < 3:
                half_stats.append(None)
                cross_stats.append(None)
                continue
            values = np.asarray([
                float(np.mean(s["power"]["X_A_mhz"][mask]))-noise_floor
                for s, noise_floor in retained])
            error = math.sqrt(float(np.var(values, ddof=1))/len(values) +
                              float(np.var(null_power, ddof=1))/len(null_power))
            half_stats.append({"excess_sigma": float((np.mean(values)-null_mean)/error)
                               if error > 0 else 0.0,
                               "power": float(np.mean(values))})
            cross_values = np.asarray([
                float(np.mean(np.real(s["scale"] *
                    s["fourier"]["A_minus_residual"][mask] *
                    np.conj(s["fourier"]["A_plus_residual"][mask]))))
                for s, _ in retained])
            cross_error = float(np.std(cross_values, ddof=1) /
                                math.sqrt(len(cross_values)))
            cross_stats.append({"real": float(np.mean(cross_values)),
                                "negative_sigma": float(
                                    -np.mean(cross_values)/cross_error)
                                if cross_error > 0 else 0.0})
        retained = [s for s in science_spectra if s is not None]
        cross = np.mean([s["scale"] * s["fourier"]["A_minus_residual"] *
                         np.conj(s["fourier"]["A_plus_residual"])
                         for s in retained], axis=0)
        cross_real = float(np.mean(np.real(cross[mask])))
        cross_ac = np.mean([s["scale"] * s["fourier"]["X_A_mhz"] *
                            np.conj(s["fourier"]["C"])
                            for s in retained], axis=0)
        cross_ab = np.mean([s["scale"] * s["fourier"]["X_A_mhz"] *
                            np.conj(s["fourier"]["X_B_mhz"])
                            for s in retained], axis=0)
        def coherence(cross_power, left, right):
            denominator = np.maximum(average[left]*average[right], 1e-18)
            return float(np.mean(np.abs(cross_power[mask])**2/denominator[mask]))
        nuisance = max(coherence(cross_ac, "X_A_mhz", "C"),
                       coherence(cross_ab, "X_A_mhz", "X_B_mhz"))
        verdict = (motion_candidate(
            excess_sigma_first=half_stats[0]["excess_sigma"],
            excess_sigma_second=half_stats[1]["excess_sigma"],
            flank_cross_sigma_first=cross_stats[0]["negative_sigma"],
            flank_cross_sigma_second=cross_stats[1]["negative_sigma"],
            nuisance_coherence=nuisance,
            controls_valid=bool(manifest.get("controls_valid")) and
            not bool(manifest.get("line_moved")))
            if all(half_stats) else {"candidate": False,
                                     "reason": "too few calibrated chunks per half"})
        bands.append({"low_hz": float(low), "high_hz": float(high),
                      "null_power": null_mean, "halves": half_stats,
                      "flank_cross_real": cross_real,
                      "flank_cross_halves": cross_stats,
                      "nuisance_coherence": nuisance, **verdict})

    all_time = np.concatenate([item["observed_utc_ns"] for item in valid_science])
    all_x = np.concatenate([item["binary"]["X_A_mhz"] for item in valid_science])
    all_x_continuous = np.concatenate(
        [item["continuous"]["X_A_mhz"] for item in valid_science])
    all_x_b = np.concatenate([item["binary"]["X_B_mhz"]
                              for item in valid_science])
    all_c = np.concatenate([item["binary"]["C"]
                            for item in valid_science])
    order = np.argsort(all_time)
    all_time = all_time[order]
    all_x = all_x[order]
    all_x_continuous = all_x_continuous[order]
    all_x_b = all_x_b[order]
    all_c = all_c[order]
    relative_time = (all_time-all_time[0])*1e-9
    taus = np.geomspace(max(.005, 2*np.median(np.diff(relative_time))), 30., 20)
    allan = allan_deviation(relative_time, all_x, taus)
    telegraph = {}
    if compute_telegraph:
        for width in (.010, .030, .100):
            telegraph[f"{width:g}"] = []
            for half in (valid_science[:len(valid_science)//2],
                         valid_science[len(valid_science)//2:]):
                t = np.concatenate([x["observed_utc_ns"] for x in half])
                y = np.concatenate([x["binary"]["X_A_mhz"] for x in half])
                _, binned, counts = bin_irregular(
                    (t-t[0])*1e-9, y, width_s=width)
                values = binned[counts > 0]
                if values.size >= 40:
                    fit = telegraph_fit(values)
                    fit["caveat"] = "missing bins omitted; compare with raw gap-aware spectra"
                    telegraph[f"{width:g}"].append(fit)
                else:
                    telegraph[f"{width:g}"].append({"status": "too_few_bins"})
    block_centers, block_means, block_counts = bin_irregular(
        relative_time, all_x, width_s=.100)
    finite_blocks = block_counts > 0
    if 10 <= int(np.sum(finite_blocks)) <= 1000:
        changes = gaussian_block_change_points(block_means[finite_blocks])
        present_centers = block_centers[finite_blocks]
        present_indices = np.flatnonzero(finite_blocks)
        changes["change_times_s"] = [float(present_centers[index])
                                     for index in changes["change_indices"]]
        changes["gap_adjacent"] = [bool(present_indices[index] -
                                       present_indices[index-1] > 1)
                                   for index in changes["change_indices"]]
    else:
        changes = {"status": "too_few_or_too_many_resolved_100ms_bins"}
    pt = ({"attribution": "unavailable_without_independent_frequency"}
          if pt_frequency_hz is None else
          {"attribution": "frequency_outside_resolved_band"})
    if pt_frequency_hz is not None and .2 <= float(pt_frequency_hz) <= bandwidth:
        narrow_frequency = np.arange(
            max(.2, float(pt_frequency_hz)-.10),
            min(float(bandwidth), float(pt_frequency_hz)+.10)+.0001,
            .01)
        narrow = irregular_spectrum(
            relative_time, {"X_A_mhz": all_x, "C": all_c},
            narrow_frequency)
        null_time = np.concatenate([item["observed_utc_ns"][item["timing_valid"]]
                                    for item in null])
        null_x = np.concatenate([
            np.asarray(item["binary"]["X_A_mhz"])[item["timing_valid"]]
            for item in null])
        null_narrow = irregular_spectrum(
            (null_time-null_time[0])*1e-9, {"X_A_mhz": null_x},
            narrow_frequency)
        near = np.flatnonzero(np.abs(narrow_frequency-float(pt_frequency_hz))
                              <= .020001)
        if near.size:
            peak = int(near[np.argmax(narrow["power"]["X_A_mhz"][near])])
            background = np.abs(narrow_frequency-float(pt_frequency_hz)) >= .05
            background_power = float(np.median(
                narrow["power"]["X_A_mhz"][background]))
            local_control = float(np.median(narrow["power"]["C"][background]))
            signal_ratio = (float(narrow["power"]["X_A_mhz"][peak] /
                                  background_power)
                            if background_power > 0 else 0.0)
            control_ratio = (float(narrow["power"]["C"][peak] / local_control)
                             if local_control > 0 else 0.0)
            null_background = float(np.median(
                null_narrow["power"]["X_A_mhz"][background]))
            null_ratio = (float(null_narrow["power"]["X_A_mhz"][peak] /
                                null_background)
                          if null_background > 0 else 0.0)
            pt.update({"narrowband_grid_step_hz": .01,
                       "attribution": "independent_frequency_test",
                       "passes_snr_5": bool(signal_ratio >= 5 and
                                            control_ratio < 5 and
                                            null_ratio < 5),
                       "control_power_to_local_background": control_ratio,
                       "null_power_to_local_background": null_ratio,
                       "physical_resolution_hz": float(1/relative_time[-1]),
                       "narrowband_peak_hz": float(narrow_frequency[peak]),
                       "narrowband_power_to_local_background": (
                           None if background_power <= 0 else signal_ratio),
                       "narrowband_control_power": float(
                           narrow["power"]["C"][peak]),
                       "narrowband_amplitude_proxy_mhz": float(
                           2*np.abs(narrow["fourier"]["X_A_mhz"][peak]) /
                           np.sum(np.hanning(len(all_x)))),
                       "caveat": "full-run irregular Fourier grid; calibration gaps form a spectral window"})
    def lag_summary(items):
        result = {}
        for site in ("A_minus", "A_plus", "B", "C"):
            per_chunk = [lag_statistics(item["binary"]["paired"][site])
                         for item in items]
            result[site] = {
                key: (float(np.mean([x[key] for x in per_chunk
                                     if x[key] is not None]))
                      if any(x[key] is not None for x in per_chunk) else None)
                for key in ("early_late", "consecutive_shots")}
        return result
    lag = {"science": lag_summary(valid_science), "null": lag_summary(null)}
    lag["control_corrected_A_minus"] = (
        None if lag["science"]["A_minus"]["consecutive_shots"] is None or
        lag["science"]["C"]["consecutive_shots"] is None else
        lag["science"]["A_minus"]["consecutive_shots"] -
        lag["science"]["C"]["consecutive_shots"])
    white_floor = [floor(item) for item in valid_science]
    report = {"schema": "q3.tls-millisecond-sentinel-analysis.v1",
              "source_manifest": str(manifest_path),
              "controls_valid": bool(manifest.get("controls_valid")),
              "line_moved": bool(manifest.get("line_moved")),
              "science_chunks": len(valid_science),
              "null_chunks": len(null), "max_science_hz": float(bandwidth),
              "frequency_hz": frequencies.tolist(),
              "mean_power": {name: value.tolist() for name, value in average.items()},
              "continuous_x_a_mean_power": continuous_power.tolist(),
              "null_mean_power": {name: value.tolist()
                                  for name, value in null_average.items()},
              "bands": bands, "allan_deviation": allan,
              "lag1": lag,
              "binomial_white_floor": {"X_A_mhz2_per_hz": float(np.mean(white_floor)),
                                       "model": "two Bernoulli subshots per flank per hardware shot; subtracted per chunk from science and quiet null band powers"},
              "telegraph_screen": telegraph, "pulse_tube": pt,
              "change_point_crosscheck": changes,
              "interpretation": "screen only; common qubit flux motion and host timestamp jitter remain confounds"}
    output = manifest_path.parent / "sentinel_analysis.json"
    output.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    np.savez_compressed(manifest_path.parent / "sentinel_derived_streams.npz",
                        observed_utc_ns=all_time, x_a_mhz=all_x,
                        x_a_continuous_mhz=all_x_continuous,
                        x_b_mhz=all_x_b,
                        frequency_hz=frequencies,
                        x_a_mean_power=average["X_A_mhz"],
                        x_a_continuous_mean_power=continuous_power,
                        x_a_null_power=null_average["X_A_mhz"])
    import matplotlib
    matplotlib.use("Agg", force=True)
    from matplotlib import pyplot as plt
    figure, axes = plt.subplots(2, 2, figsize=(11, 8), constrained_layout=True)
    ax = axes[0, 0]
    ax.plot(relative_time, all_x, ".", markersize=1.3, alpha=.35)
    ax.set(xlabel="Host-observed time (s)", ylabel="A position proxy (MHz)",
           title="Calibrated two-flank stream; host timestamps")
    ax = axes[0, 1]
    ax.loglog(frequencies, average["X_A_mhz"], label="A binary")
    ax.loglog(frequencies, continuous_power, label="A raw IQ")
    ax.loglog(frequencies, null_average["X_A_mhz"], label="quiet null")
    ax.axhline(float(np.mean(white_floor)), linestyle="--", color="gray",
               label="binomial white floor")
    ax.set(xlabel="Frequency (Hz)", ylabel="Relative power (MHz²/Hz)",
           title="Gap-aware nonuniform spectra")
    ax.legend(fontsize=8)
    ax = axes[1, 0]
    resolved = [item for item in allan if item["allan"] is not None]
    if resolved:
        ax.loglog([item["tau_s"] for item in resolved],
                  [max(item["allan"], 1e-12) for item in resolved], "o-")
    ax.set(xlabel="Averaging time (s)", ylabel="Allan deviation (MHz)",
           title="Resolved adjacent-bin Allan deviation")
    ax = axes[1, 1]
    positions = np.arange(len(bands))
    if bands:
        ax.bar(positions-.16,
               [b["halves"][0]["excess_sigma"] if b["halves"][0] else 0
                for b in bands], width=.32, label="first half")
        ax.bar(positions+.16,
               [b["halves"][1]["excess_sigma"] if b["halves"][1] else 0
                for b in bands], width=.32, label="second half")
        ax.set_xticks(positions, [f"{b['low_hz']:g}–{b['high_hz']:g} Hz"
                                  for b in bands])
    ax.axhline(5, linestyle="--", color="gray")
    ax.set(ylabel="Science minus null (σ)",
           title="Screen only; control coherence also required")
    ax.legend(fontsize=8)
    figure.savefig(manifest_path.parent / "sentinel_analysis.png", dpi=160)
    plt.close(figure)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--pt-frequency-hz", type=float,
                        help="independently measured pulse-tube frequency")
    args = parser.parse_args(argv)
    report = analyze_session(args.manifest,
                             pt_frequency_hz=args.pt_frequency_hz)
    print(json.dumps({"report": str(args.manifest.parent / "sentinel_analysis.json"),
                      "science_chunks": report["science_chunks"],
                      "max_science_hz": report["max_science_hz"],
                      "candidate_bands": [b for b in report["bands"]
                                          if b["candidate"]]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
