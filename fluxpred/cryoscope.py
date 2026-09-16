import numpy as np

QUADRATURES = ("x", "y")
DEFAULT_CONTRAST_THRESHOLD = 0.25


def _vector(value, name):
    array = np.asarray(value, dtype=float)
    if array.ndim != 1 or array.size == 0:
        raise ValueError(f"{name} must be a nonempty one-dimensional array")
    return array


def bloch_components(p_x, p_y, *, p_ground, p_excited, min_reference_contrast=0.05):
    p_x = _vector(p_x, "p_x")
    p_y = _vector(p_y, "p_y")
    if p_x.shape != p_y.shape:
        raise ValueError("p_x and p_y must have the same shape")
    reference = float(p_excited) - float(p_ground)
    if not np.isfinite(reference) or reference < float(min_reference_contrast):
        raise ValueError(
            f"assignment reference contrast {reference!r} is below the required "
            f"{float(min_reference_contrast)!r}; the readout cannot resolve the Bloch vector")
    x = 2.0 * (p_x - float(p_ground)) / reference - 1.0
    y = 2.0 * (p_y - float(p_ground)) / reference - 1.0
    return x, y


def contrast(x, y):
    return np.hypot(_vector(x, "x"), _vector(y, "y"))


def support_mask(x, y, *, threshold=DEFAULT_CONTRAST_THRESHOLD):
    magnitude = contrast(x, y)
    finite = np.isfinite(magnitude) & np.isfinite(x) & np.isfinite(y)
    return finite & (magnitude >= float(threshold))


def wrapped_phase(x, y):
    return np.arctan2(_vector(y, "y"), _vector(x, "x"))


def phase_uncertainty(x, y, sigma_x, sigma_y):
    x = _vector(x, "x")
    y = _vector(y, "y")
    sigma_x = _vector(sigma_x, "sigma_x")
    sigma_y = _vector(sigma_y, "sigma_y")
    squared = x ** 2 + y ** 2
    with np.errstate(divide="ignore", invalid="ignore"):
        sigma = np.sqrt((x * sigma_y) ** 2 + (y * sigma_x) ** 2) / squared
    return np.where(squared > 0, sigma, np.inf)


def shot_noise_sigma(population, shots):
    population = np.clip(_vector(population, "population"), 0.0, 1.0)
    shots = float(shots)
    if not np.isfinite(shots) or shots <= 0:
        raise ValueError("shots must be a positive number")
    return np.sqrt(population * (1.0 - population) / shots)


def unwrap_masked(phase, mask):
    phase = _vector(phase, "phase")
    mask = np.asarray(mask, dtype=bool)
    if mask.shape != phase.shape:
        raise ValueError("mask must have the same shape as phase")
    if np.count_nonzero(mask) < 2:
        raise ValueError("phase unwrapping needs at least two supported samples")
    out = np.full(phase.shape, np.nan)
    out[mask] = np.unwrap(phase[mask])
    return out


def detuning_from_window(phase_rad, window_ns):
    phase_rad = _vector(phase_rad, "phase_rad")
    window_ns = float(window_ns)
    if not np.isfinite(window_ns) or window_ns <= 0:
        raise ValueError("window_ns must be positive and finite")
    return phase_rad * 1000.0 / (2.0 * np.pi * window_ns)


def window_unambiguous_range_mhz(window_ns):
    window_ns = float(window_ns)
    if not np.isfinite(window_ns) or window_ns <= 0:
        raise ValueError("window_ns must be positive and finite")
    return 500.0 / window_ns


def resolve_branch(phase_fine, window_fine_ns, phase_coarse, window_coarse_ns, *, mask=None):
    phase_fine = _vector(phase_fine, "phase_fine")
    phase_coarse = _vector(phase_coarse, "phase_coarse")
    if phase_fine.shape != phase_coarse.shape:
        raise ValueError("fine and coarse phase arrays must have the same shape")
    window_fine_ns = float(window_fine_ns)
    window_coarse_ns = float(window_coarse_ns)
    if not np.isfinite(window_fine_ns) or not np.isfinite(window_coarse_ns):
        raise ValueError("probe windows must be finite")
    if window_fine_ns <= window_coarse_ns:
        raise ValueError("the fine window must be longer than the coarse window")
    coarse_mhz = detuning_from_window(phase_coarse, window_coarse_ns)
    branch = np.rint((coarse_mhz * 2.0 * np.pi * window_fine_ns / 1000.0 - phase_fine) / (2.0 * np.pi))
    resolved = phase_fine + 2.0 * np.pi * branch
    fine_mhz = detuning_from_window(resolved, window_fine_ns)
    slip = np.abs(fine_mhz - coarse_mhz)
    tolerance = 0.5 * window_unambiguous_range_mhz(window_fine_ns)
    ambiguous = ~np.isfinite(slip) | (slip > tolerance)
    if mask is not None:
        ambiguous &= np.asarray(mask, dtype=bool)
    return {"detuning_mhz": fine_mhz, "resolved_phase_rad": resolved, "branch": branch,
            "coarse_detuning_mhz": coarse_mhz, "branch_slip_mhz": slip,
            "branch_tolerance_mhz": tolerance, "ambiguous": ambiguous,
            "ambiguous_count": int(np.count_nonzero(ambiguous))}


def smooth_derivative(time_ns, phase_rad, *, window, polyorder=2):
    from scipy.signal import savgol_filter

    time_ns = _vector(time_ns, "time_ns")
    phase_rad = _vector(phase_rad, "phase_rad")
    if time_ns.shape != phase_rad.shape:
        raise ValueError("time and phase arrays must have the same shape")
    if np.any(np.diff(time_ns) <= 0):
        raise ValueError("time_ns must be strictly increasing")
    spacing = np.diff(time_ns)
    if not np.allclose(spacing, spacing[0], rtol=1e-9, atol=1e-9):
        raise ValueError("the smooth differentiator requires a uniform delay grid")
    window = int(window)
    if window < 5 or window % 2 == 0 or window > phase_rad.size:
        raise ValueError("differentiator window must be odd, at least 5, and fit the trace")
    if not 1 <= int(polyorder) < window:
        raise ValueError("differentiator polyorder must be at least 1 and below the window")
    derivative = savgol_filter(phase_rad, window, int(polyorder), deriv=1, delta=float(spacing[0]))
    return derivative * 1000.0 / (2.0 * np.pi)


def local_monotonic_branch(frequency_of_coordinate, *, park, target, margin=0.25, points=200001):
    park = float(park)
    target = float(target)
    if not np.isfinite(park) or not np.isfinite(target):
        raise ValueError("park and target coordinates must be finite")
    if park == target:
        raise ValueError("park and target coordinates must differ")
    points = int(points)
    if points < 3:
        raise ValueError("the inversion grid needs at least three points")
    margin = float(margin)
    if not np.isfinite(margin) or margin < 0:
        raise ValueError("margin must be a nonnegative finite fraction of the park-target span")
    inside = np.linspace(park, target, points)
    step = inside[1] - inside[0]
    extra = int(round(margin * (points - 1)))
    below = park - step * np.arange(extra, 0, -1)
    above = target + step * np.arange(1, extra + 1)
    grid = np.concatenate([below, inside, above])
    values = np.asarray(frequency_of_coordinate(grid), dtype=float)
    if values.shape != grid.shape or not np.all(np.isfinite(values)):
        raise ValueError("frequency_of_coordinate must return a finite value for every coordinate")
    difference = np.diff(values)
    interior = difference[extra:extra + points - 1]
    if not (np.all(interior > 0) or np.all(interior < 0)):
        raise ValueError(
            "the static flux model is not monotonic between park and target; the measured "
            "frequency cannot be assigned to a unique flux coordinate on this branch")
    sign = 1.0 if interior[0] > 0 else -1.0
    lower = extra
    while lower > 0 and sign * difference[lower - 1] > 0:
        lower -= 1
    upper = extra + points - 1
    while upper < difference.size and sign * difference[upper] > 0:
        upper += 1
    grid = grid[lower:upper + 1]
    values = values[lower:upper + 1]
    if sign < 0:
        grid = grid[::-1]
        values = values[::-1]
    return grid, values


def invert_static_model(frequency_ghz, frequency_of_coordinate, *, park, target,
                        margin=0.25, points=200001):
    grid, values = local_monotonic_branch(
        frequency_of_coordinate, park=park, target=target, margin=margin, points=points)
    frequency = np.asarray(frequency_ghz, dtype=float)
    coordinate = np.interp(frequency, values, grid, left=np.nan, right=np.nan)
    outside = ~np.isfinite(coordinate) & np.isfinite(frequency)
    return coordinate, outside


def normalized_amplitude(frequency_ghz, frequency_of_coordinate, *, park, target, margin=0.25):
    coordinate, outside = invert_static_model(
        frequency_ghz, frequency_of_coordinate, park=park, target=target, margin=margin)
    return (coordinate - float(park)) / (float(target) - float(park)), outside


def nominal_detuning_mhz(ideal_amplitude, frequency_of_coordinate, *, park, target,
                         probe_frequency_ghz):
    ideal = np.asarray(ideal_amplitude, dtype=float)
    probe = np.asarray(probe_frequency_ghz, dtype=float)
    if probe.ndim not in (0, 1) or (probe.ndim == 1 and probe.shape != ideal.shape):
        raise ValueError("probe_frequency_ghz must be a scalar or match the delay grid")
    if not np.all(np.isfinite(probe)):
        raise ValueError("probe_frequency_ghz must be finite")
    coordinate = float(park) + ideal * (float(target) - float(park))
    frequency = np.asarray(frequency_of_coordinate(coordinate), dtype=float)
    if frequency.shape != ideal.shape or not np.all(np.isfinite(frequency)):
        raise ValueError("the static flux model must give a finite nominal frequency at every sample")
    return (frequency - probe) * 1000.0


def probe_frequencies(ideal_amplitude, frequency_of_coordinate, *, park, target):
    ideal = np.asarray(ideal_amplitude, dtype=float)
    coordinate = float(park) + ideal * (float(target) - float(park))
    frequency = np.asarray(frequency_of_coordinate(coordinate), dtype=float)
    if frequency.shape != ideal.shape or not np.all(np.isfinite(frequency)):
        raise ValueError("the static flux model must give a finite probe frequency at every delay")
    return frequency


def trace_from_measurement(*, delays_ns, phase_rad, mask, probe_window_ns, probe_frequency_ghz,
                           frequency_of_coordinate, park, target, ideal_amplitude=None,
                           sigma_phase_rad=None):
    delays_ns = _vector(delays_ns, "delays_ns")
    phase_rad = _vector(phase_rad, "phase_rad")
    mask = np.asarray(mask, dtype=bool)
    if delays_ns.shape != phase_rad.shape or mask.shape != delays_ns.shape:
        raise ValueError("delays, phase and mask must have the same shape")
    if np.any(np.diff(delays_ns) <= 0):
        raise ValueError("delays_ns must be strictly increasing")
    residual_mhz = detuning_from_window(phase_rad, probe_window_ns)
    if ideal_amplitude is None:
        ideal = np.ones_like(delays_ns)
    else:
        ideal = np.asarray(ideal_amplitude, dtype=float)
        if ideal.shape != delays_ns.shape:
            raise ValueError("ideal_amplitude must match the delay grid")
    nominal_mhz = nominal_detuning_mhz(
        ideal, frequency_of_coordinate, park=park, target=target,
        probe_frequency_ghz=probe_frequency_ghz)
    measured_mhz = nominal_mhz + residual_mhz
    frequency_ghz = np.asarray(probe_frequency_ghz, dtype=float) + measured_mhz / 1000.0
    amplitude, outside = normalized_amplitude(
        frequency_ghz, frequency_of_coordinate, park=park, target=target)
    support = mask & np.isfinite(amplitude) & ~outside
    result = {"delays_ns": delays_ns, "residual_detuning_mhz": residual_mhz,
              "nominal_detuning_mhz": nominal_mhz, "measured_detuning_mhz": measured_mhz,
              "frequency_ghz": frequency_ghz, "normalized_amplitude": amplitude,
              "outside_static_model": outside, "support": support,
              "probe_window_ns": float(probe_window_ns),
              "probe_frequency_ghz": np.asarray(probe_frequency_ghz, dtype=float),
              "supported_fraction": float(np.mean(support))}
    if sigma_phase_rad is not None:
        sigma_phase_rad = _vector(sigma_phase_rad, "sigma_phase_rad")
        result["sigma_detuning_mhz"] = np.abs(detuning_from_window(sigma_phase_rad, probe_window_ns))
    return result


def drift_report(repeats, *, mask=None):
    stack = np.asarray(repeats, dtype=float)
    if stack.ndim != 2 or stack.shape[0] < 2:
        raise ValueError("drift needs at least two repeated traces of equal length")
    if mask is None:
        mask = np.isfinite(stack).all(axis=0)
    else:
        mask = np.asarray(mask, dtype=bool) & np.isfinite(stack).all(axis=0)
    if np.count_nonzero(mask) < 2:
        raise ValueError("drift needs at least two jointly supported samples")
    supported = stack[:, mask]
    means = supported.mean(axis=1)
    spread = supported.std(axis=0, ddof=1)
    return {"per_repeat_mean": means.tolist(),
            "between_repeat_range": float(np.max(means) - np.min(means)),
            "within_repeat_rms": float(np.sqrt(np.mean(spread ** 2))),
            "supported_samples": int(np.count_nonzero(mask))}


def effective_window_ns(idle_ns, pulse_ns):
    idle_ns = float(idle_ns)
    pulse_ns = float(pulse_ns)
    if not np.isfinite(idle_ns) or idle_ns <= 0 or not np.isfinite(pulse_ns) or pulse_ns < 0:
        raise ValueError("idle window must be positive and the pulse length nonnegative")
    return idle_ns+pulse_ns


def idle_window_ns(effective_ns, pulse_ns):
    idle = float(effective_ns)-float(pulse_ns)
    if idle <= 0:
        raise ValueError(
            f"an effective window of {float(effective_ns):g} ns is not reachable with "
            f"{float(pulse_ns):g} ns pi/2 pulses; the shortest effective window is the pulse "
            f"length plus one clock")
    return idle


def excursion_mhz(frequency_of_coordinate, *, park, target, amplitude, overshoot):
    park = float(park)
    target = float(target)
    span = target-park
    amplitude = float(amplitude)
    overshoot = abs(float(overshoot))
    grid = np.array([park+amplitude*span, park+amplitude*(1.0+overshoot)*span,
                     park, park+amplitude*overshoot*span])
    values = np.asarray(frequency_of_coordinate(grid), dtype=float)
    return float(max(abs(values[1]-values[0]), abs(values[3]-values[2]))*1000.0)


def solve_identification_amplitude(frequency_of_coordinate, *, park, target, overshoot,
                                   coarsest_window_ns, safety=0.8, max_amplitude=1.0,
                                   points=4001):
    park = float(park)
    target = float(target)
    overshoot = abs(float(overshoot))
    if overshoot <= 0:
        raise ValueError("overshoot must be positive")
    budget = float(safety)*window_unambiguous_range_mhz(coarsest_window_ns)
    amplitudes = np.linspace(0.0, float(max_amplitude), int(points))[1:]
    span = target-park
    nominal = np.asarray(frequency_of_coordinate(park+amplitudes*span), dtype=float)
    overshot = np.asarray(frequency_of_coordinate(park+amplitudes*(1.0+overshoot)*span),
                          dtype=float)
    at_park = float(np.asarray(frequency_of_coordinate(np.array([park])), dtype=float)[0])
    returned = np.asarray(frequency_of_coordinate(park+amplitudes*overshoot*span), dtype=float)
    excursion = np.maximum(np.abs(overshot-nominal), np.abs(returned-at_park))*1000.0
    ok = np.isfinite(excursion) & (excursion <= budget)
    if not ok.any() or not ok[0]:
        raise ValueError(
            f"even the smallest tested amplitude produces a {float(excursion[0]):.3g} MHz "
            f"excursion, above the {budget:.3g} MHz a {float(coarsest_window_ns):g} ns window can "
            f"unwrap; shorten the coarsest window or start from an existing correction")
    first_bad = int(np.argmin(ok)) if not ok.all() else amplitudes.size
    return float(amplitudes[first_bad-1])


def prune_ladder(windows, *, min_step_ratio=1.5, max_step_ratio=6.0):
    windows = [float(value) for value in sorted(windows)]
    if len(windows) < 3:
        return windows
    kept = [windows[0]]
    for index, value in enumerate(windows[1:], start=1):
        if index == len(windows)-1:
            kept.append(value)
            continue
        following = windows[index+1]
        if value/kept[-1] < min_step_ratio and following/kept[-1] <= max_step_ratio:
            continue
        kept.append(value)
    return kept


def plan_window_ladder(max_detuning_mhz, *, finest_ns, ratio=5.0, max_rungs=6, min_ns=None):
    max_detuning_mhz = float(max_detuning_mhz)
    finest_ns = float(finest_ns)
    ratio = float(ratio)
    if not np.isfinite(max_detuning_mhz) or max_detuning_mhz <= 0:
        raise ValueError("max_detuning_mhz must be positive and finite")
    if not np.isfinite(finest_ns) or finest_ns <= 0:
        raise ValueError("finest_ns must be positive and finite")
    if not np.isfinite(ratio) or ratio <= 1.0:
        raise ValueError("ratio between adjacent probe windows must exceed one")
    floor = 0.0 if min_ns is None else float(min_ns)
    if floor > 0 and finest_ns < floor:
        raise ValueError(
            f"the finest window {finest_ns:g} ns is below the {floor:g} ns the pulses allow")
    windows = [finest_ns]
    for _ in range(int(max_rungs)-1):
        if window_unambiguous_range_mhz(windows[0]) >= max_detuning_mhz:
            break
        candidate = windows[0]/ratio
        if floor > 0 and candidate < floor:
            windows.insert(0, floor)
            break
        windows.insert(0, candidate)
    windows = prune_ladder(sorted(set(windows)))
    if window_unambiguous_range_mhz(windows[0]) < max_detuning_mhz:
        raise ValueError(
            f"a {len(windows)}-rung ladder down to {windows[0]:.3g} ns still only resolves "
            f"+-{window_unambiguous_range_mhz(windows[0]):.3g} MHz, but the expected excursion is "
            f"{max_detuning_mhz:.3g} MHz; reduce the identification amplitude, start from an "
            f"existing correction, or shorten the finest window")
    return tuple(float(value) for value in windows)


def max_identification_amplitude(*, sensitivity_mhz_per_unit, overshoot, coarsest_window_ns,
                                 safety=0.8):
    sensitivity = abs(float(sensitivity_mhz_per_unit))
    overshoot = abs(float(overshoot))
    if sensitivity <= 0 or overshoot <= 0:
        raise ValueError("sensitivity and overshoot must be positive")
    budget = float(safety)*window_unambiguous_range_mhz(coarsest_window_ns)
    return float(budget/(sensitivity*overshoot))


def resolve_ladder(phases_rad, windows_ns, *, mask=None, safety=0.5):
    windows = [float(value) for value in windows_ns]
    if len(windows) < 2:
        raise ValueError("a ladder needs at least two probe windows")
    if any(value <= 0 for value in windows):
        raise ValueError("probe windows must be positive")
    order = np.argsort(windows)
    windows = [windows[index] for index in order]
    stack = [np.asarray(phases_rad, dtype=float)[index] for index in order]
    if any(entry.shape != stack[0].shape for entry in stack):
        raise ValueError("every rung must have the same number of delays")
    estimate = detuning_from_window(stack[0], windows[0])
    rungs = [{"window_ns": windows[0], "detuning_mhz": estimate.copy(),
              "branch": np.zeros_like(estimate), "slip_mhz": np.zeros_like(estimate),
              "ambiguous": np.zeros(estimate.shape, dtype=bool)}]
    ambiguous = np.zeros(estimate.shape, dtype=bool)
    resolved_phase = stack[0]
    for window, phase in zip(windows[1:], stack[1:]):
        branch = np.rint((estimate*2.0*np.pi*window/1000.0-phase)/(2.0*np.pi))
        resolved_phase = phase+2.0*np.pi*branch
        refined = detuning_from_window(resolved_phase, window)
        slip = np.abs(refined-estimate)
        tolerance = float(safety)*window_unambiguous_range_mhz(window)
        step_ambiguous = ~np.isfinite(slip) | (slip > tolerance)
        ambiguous = ambiguous | step_ambiguous
        rungs.append({"window_ns": window, "detuning_mhz": refined.copy(), "branch": branch,
                      "slip_mhz": slip, "ambiguous": step_ambiguous,
                      "tolerance_mhz": tolerance})
        estimate = refined
    if mask is not None:
        ambiguous = ambiguous & np.asarray(mask, dtype=bool)
    return {"detuning_mhz": estimate, "resolved_phase_rad": resolved_phase,
            "windows_ns": tuple(windows), "rungs": rungs, "ambiguous": ambiguous,
            "ambiguous_count": int(np.count_nonzero(ambiguous)),
            "finest_window_ns": windows[-1],
            "branch_tolerance_mhz": float(safety*window_unambiguous_range_mhz(windows[-1]))}


def plan_probe(frequency_of_coordinate, *, park, target, pulse_ns, readout_span_ns,
               min_idle_ns=16.0, finest_effective_ns=2000.0, ratio=4.0, overshoot=0.2,
               safety=0.8, inset_ns=16.0, requested_amplitude=None,
               requested_effective_windows_ns=None, emission_quantum_ns=1000.0,
               requested_first_ns=0.0, max_amplitude=1.0):
    pulse_ns = float(pulse_ns)
    min_idle_ns = float(min_idle_ns)
    floor = pulse_ns+min_idle_ns
    ceiling = solve_identification_amplitude(
        frequency_of_coordinate, park=park, target=target, overshoot=overshoot,
        coarsest_window_ns=floor, safety=safety, max_amplitude=max_amplitude)
    amplitude = ceiling if requested_amplitude is None else float(requested_amplitude)
    if amplitude > ceiling+1e-12:
        raise ValueError(
            f"a normalized amplitude of {amplitude:g} exceeds the {ceiling:.4f} that the "
            f"{floor:g} ns shortest reachable effective window can unwrap for an assumed "
            f"{overshoot:.0%} overshoot; lower the amplitude, shorten the pi/2 pulse, or start "
            f"from an existing correction")
    expected = excursion_mhz(frequency_of_coordinate, park=park, target=target,
                             amplitude=amplitude, overshoot=overshoot)
    if requested_effective_windows_ns:
        windows = tuple(sorted(float(value) for value in requested_effective_windows_ns))
        if windows[0] < floor-1e-9:
            raise ValueError(
                f"the coarsest requested effective window {windows[0]:g} ns is shorter than the "
                f"{floor:g} ns that {pulse_ns:g} ns pi/2 pulses plus a {min_idle_ns:g} ns idle "
                f"allow")
        if window_unambiguous_range_mhz(windows[0]) < expected:
            raise ValueError(
                f"the coarsest requested effective window {windows[0]:g} ns resolves only "
                f"+-{window_unambiguous_range_mhz(windows[0]):.3g} MHz, but the expected excursion "
                f"at amplitude {amplitude:g} is {expected:.3g} MHz")
    else:
        finest = max(float(finest_effective_ns), floor*float(ratio))
        windows = plan_window_ladder(
            expected/max(float(safety), 1e-9), finest_ns=finest, ratio=float(ratio), min_ns=floor)
    idle = tuple(idle_window_ns(value, pulse_ns) for value in windows)
    span = float(inset_ns)+2.0*pulse_ns+max(idle)+float(readout_span_ns)
    quantum = float(emission_quantum_ns)
    first = max(float(requested_first_ns), np.ceil(span/quantum)*quantum)
    return {"effective_windows_ns": windows, "idle_windows_ns": idle, "pulse_ns": pulse_ns,
            "amplitude": amplitude, "amplitude_ceiling": ceiling, "overshoot": float(overshoot),
            "expected_excursion_mhz": expected, "probe_span_ns": span,
            "schedule_first_ns": float(first), "inset_ns": float(inset_ns),
            "readout_span_ns": float(readout_span_ns),
            "coarsest_range_mhz": window_unambiguous_range_mhz(min(windows)),
            "finest_range_mhz": window_unambiguous_range_mhz(max(windows))}
