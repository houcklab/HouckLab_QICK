"""Pure numerical helpers for robust qubit step-response trace extraction.

The image tracker in this module deliberately has no controller dependencies.
The identical implementation is used by the QUA and QICK experiments so that
ridge extraction cannot become another controller-dependent difference.
"""

import numpy as np
from scipy import ndimage, signal


def _robust_scale(values, axis=None, keepdims=False):
    """Return a finite MAD scale, falling back to a standard deviation."""
    values = np.asarray(values, dtype=float)
    center = np.nanmedian(values, axis=axis, keepdims=True)
    scale = 1.4826 * np.nanmedian(np.abs(values - center), axis=axis, keepdims=True)
    fallback = np.nanstd(values, axis=axis, keepdims=True)
    scale = np.where(np.isfinite(scale) & (scale > 1e-12), scale, fallback)
    scale = np.where(np.isfinite(scale) & (scale > 1e-12), scale, 1.0)
    if not keepdims and axis is not None:
        scale = np.squeeze(scale, axis=axis)
    return scale


def _fill_spectral_nans(image):
    """Interpolate isolated missing spectral pixels independently per frame."""
    image = np.asarray(image, dtype=float)
    filled = image.copy()
    rows = np.arange(image.shape[0])
    valid_columns = np.zeros(image.shape[1], dtype=bool)
    for column in range(image.shape[1]):
        finite = np.isfinite(image[:, column])
        if np.count_nonzero(finite) < 3:
            filled[:, column] = 0.0
            continue
        valid_columns[column] = True
        filled[:, column] = np.interp(rows, rows[finite], image[finite, column])
    return filled, valid_columns


def _observed_local_support(finite_pixels, path_rows, half_width_rows=2):
    """Require measured pixels around each selected ridge, not interpolated fill."""
    finite_pixels = np.asarray(finite_pixels, dtype=bool)
    path_rows = np.asarray(path_rows, dtype=int)
    observed = np.zeros(path_rows.size, dtype=bool)
    for column, row in enumerate(path_rows):
        lower = max(0, int(row) - int(half_width_rows))
        upper = min(finite_pixels.shape[0], int(row) + int(half_width_rows) + 1)
        observed[column] = bool(np.all(finite_pixels[lower:upper, column]))
    return observed


def _smooth_supported_path(values, supported, window_points=7, polyorder=2):
    """Return a continuous ridge trajectory without moving its time origin."""
    values = np.asarray(values, dtype=float)
    supported = np.asarray(supported, dtype=bool)
    if int(window_points) <= 1:
        return values.copy()
    valid = supported & np.isfinite(values)
    if np.count_nonzero(valid) < 5:
        return values.copy()
    columns = np.arange(values.size, dtype=float)
    filled = values.copy()
    filled[~valid] = np.interp(columns[~valid], columns[valid], values[valid])
    polyorder = max(0, int(polyorder))
    window = min(
        max(polyorder + 3, int(window_points)),
        filled.size if filled.size % 2 else filled.size - 1,
    )
    if window % 2 == 0:
        window -= 1
    if window <= polyorder:
        return filled
    return signal.savgol_filter(
        filled,
        window,
        min(polyorder, window - 1),
        mode="interp",
    )


def _parabolic_peak(axis, values, row):
    """Refine a discrete local maximum without assuming a line shape."""
    if row <= 0 or row >= len(axis) - 1:
        return float(axis[row])
    left, center, right = values[row - 1 : row + 2]
    denominator = left - 2.0 * center + right
    if not np.isfinite(denominator) or abs(denominator) < 1e-15:
        return float(axis[row])
    offset = float(np.clip(0.5 * (left - right) / denominator, -1.0, 1.0))
    return float(axis[row] + offset * (axis[row + 1] - axis[row]))


def _image_ridge_evidence(
    frequency_axis_ghz,
    image,
    expected_window_mask,
    polarity,
    scale_widths_mhz,
):
    """Build v26-style multiscale ridge evidence from a raw spectroscopy map."""
    step_mhz = abs(float(np.nanmedian(np.diff(frequency_axis_ghz)))) * 1e3
    oriented = image if polarity == "bright" else -image

    # A grey opening estimates the slowly varying lower spectral envelope.  It
    # is intentionally resolution-aware and capped by the measured band; a
    # fixed 120 MHz opening (appropriate for the large TLS maps) cannot be used
    # on a 50 MHz step-response map.
    widest_mhz = max(float(width) for width in scale_widths_mhz)
    floor_rows = int(np.ceil(max(3.0 * widest_mhz, 0.45 * step_mhz) / step_mhz))
    floor_rows = max(5, min(floor_rows, max(5, image.shape[0] - 2)))
    if floor_rows % 2 == 0:
        floor_rows += 1
    if floor_rows >= image.shape[0]:
        floor_rows = image.shape[0] if image.shape[0] % 2 else image.shape[0] - 1
    floor = ndimage.grey_opening(oriented, size=(max(floor_rows, 3), 1), mode="nearest")
    foreground = oriented - floor

    # Removing a per-frame common mode rejects bright/dark vertical acquisition
    # stripes.  MAD normalization makes a noisy frame less attractive without
    # erasing a stationary ridge.
    foreground -= np.nanmedian(foreground, axis=0, keepdims=True)
    foreground /= _robust_scale(foreground, axis=0, keepdims=True)

    scale_maps = []
    for fwhm_mhz in scale_widths_mhz:
        sigma_rows = max(0.55, float(fwhm_mhz) / (2.354820045 * step_mhz))
        inner = ndimage.gaussian_filter1d(foreground, sigma_rows, axis=0, mode="nearest")
        outer = ndimage.gaussian_filter1d(foreground, 2.5 * sigma_rows, axis=0, mode="nearest")
        response = inner - outer
        response -= np.nanmedian(response, axis=0, keepdims=True)
        response /= _robust_scale(response, axis=0, keepdims=True)
        # Combine instantaneous evidence with a short coherent view.  This is
        # path evidence, not post-hoc smoothing of the reported frequency.
        coherent = ndimage.gaussian_filter1d(response, 1.0, axis=1, mode="nearest")
        scale_maps.append(0.45 * response + 0.55 * coherent)

    scale_evidence = np.asarray(scale_maps, dtype=float)
    evidence = np.nanmax(scale_evidence, axis=0)
    evidence[~expected_window_mask, :] = -np.inf
    return foreground, evidence, scale_evidence


def _candidate_rows(center_column, evidence_column, allowed, max_candidates=16):
    finite = np.isfinite(center_column) & np.isfinite(evidence_column) & allowed
    if not np.any(finite):
        return np.empty(0, dtype=int)
    work = np.where(finite, center_column, -np.inf)
    peaks, _ = signal.find_peaks(work)
    if peaks.size == 0:
        peaks = np.asarray([int(np.nanargmax(work))], dtype=int)
    # Candidate centers come from the lightly smoothed raw image, while their
    # ranking uses the multiscale evidence.  This prevents a wide filter from
    # inventing a center between two resolved shoulders.
    order = np.argsort(evidence_column[peaks])[::-1]
    return np.asarray(peaks[order[: int(max_candidates)]], dtype=int)


def _decode_ridge_path(
    frequency_axis_ghz,
    evidence,
    center_map,
    expected_window_mask,
    max_jump_mhz,
    jump_penalty,
):
    """Select one continuous sequence of image maxima with Viterbi decoding."""
    candidates = [
        _candidate_rows(center_map[:, column], evidence[:, column], expected_window_mask)
        for column in range(evidence.shape[1])
    ]
    if any(rows.size == 0 for rows in candidates):
        raise ValueError("At least one time frame has no image-ridge candidate.")

    costs = [np.full(rows.size, np.inf, dtype=float) for rows in candidates]
    back = [np.full(rows.size, -1, dtype=int) for rows in candidates]
    costs[0] = -evidence[candidates[0], 0]
    max_jump_mhz = float(max_jump_mhz)
    if not np.isfinite(max_jump_mhz) or max_jump_mhz <= 0.0:
        raise ValueError("max_jump_mhz must be finite and positive.")

    for column in range(1, evidence.shape[1]):
        previous_rows = candidates[column - 1]
        current_rows = candidates[column]
        for current_index, current_row in enumerate(current_rows):
            jump_mhz = np.abs(
                frequency_axis_ghz[previous_rows] - frequency_axis_ghz[current_row]
            ) * 1e3
            allowed = jump_mhz <= max_jump_mhz + 1e-12
            if not np.any(allowed):
                continue
            transition = costs[column - 1] + float(jump_penalty) * (jump_mhz / max_jump_mhz) ** 2
            transition[~allowed] = np.inf
            previous_index = int(np.argmin(transition))
            if not np.isfinite(transition[previous_index]):
                continue
            costs[column][current_index] = (
                transition[previous_index] - evidence[current_row, column]
            )
            back[column][current_index] = previous_index

        # A single unusually large real jump should not destroy the whole path.
        # Re-seeding is expensive, but preferable to silently falling back to a
        # non-peak pixel or smoothing across the event.
        if not np.any(np.isfinite(costs[column])):
            best = int(np.nanargmax(evidence[current_rows, column]))
            costs[column][best] = (
                float(np.nanmin(costs[column - 1]))
                - evidence[current_rows[best], column]
                + 2.0
            )

    final_index = int(np.nanargmin(costs[-1]))
    path = np.full(evidence.shape[1], -1, dtype=int)
    path[-1] = candidates[-1][final_index]
    for column in range(evidence.shape[1] - 1, 0, -1):
        final_index = int(back[column][final_index])
        if final_index < 0:
            # This is the explicit re-seed case above.  Continue backward from
            # the best path that reached the preceding frame.
            final_index = int(np.nanargmin(costs[column - 1]))
        path[column - 1] = candidates[column - 1][final_index]
    return path, candidates


def _decode_shoulder_pair(
    frequency_axis_ghz,
    evidence,
    center_map,
    expected_window_mask,
    primary_rows,
    max_jump_mhz,
    min_prominence_z,
    shoulder,
    separation_bounds_mhz=(2.0, 8.0),
    separation_tolerance_mhz=1.25,
    center_tolerance_mhz=5.0,
):
    """Track an ordered lower/upper shoulder pair without identity swaps.

    The pair midpoint is constrained to remain near the unconstrained primary
    ridge.  This prevents unrelated noise peaks elsewhere in a wide sweep from
    masquerading as a shoulder pair.  Missing pairs are bridged only for path
    continuity and are returned as unsupported.
    """
    candidates = [
        _candidate_rows(center_map[:, column], evidence[:, column], expected_window_mask)
        for column in range(evidence.shape[1])
    ]
    primary_frequency = frequency_axis_ghz[np.asarray(primary_rows, dtype=int)]
    lower_bound, upper_bound = map(float, separation_bounds_mhz)

    separations = []
    separation_weights = []
    for column, rows in enumerate(candidates):
        profile = evidence[:, column]
        floor = float(np.nanmedian(profile[np.isfinite(profile)]))
        for first in range(rows.size):
            for second in range(first + 1, rows.size):
                lower_row, upper_row = sorted((int(rows[first]), int(rows[second])))
                separation = float(
                    (frequency_axis_ghz[upper_row] - frequency_axis_ghz[lower_row]) * 1e3
                )
                midpoint = 0.5 * (
                    frequency_axis_ghz[upper_row] + frequency_axis_ghz[lower_row]
                )
                center_distance = abs(midpoint - primary_frequency[column]) * 1e3
                lower_height = float(profile[lower_row] - floor)
                upper_height = float(profile[upper_row] - floor)
                if (
                    lower_bound <= separation <= upper_bound
                    and center_distance <= float(center_tolerance_mhz)
                    and min(lower_height, upper_height) >= float(min_prominence_z)
                ):
                    separations.append(separation)
                    separation_weights.append(
                        min(lower_height, upper_height)
                        * np.exp(-0.5 * (center_distance / 3.0) ** 2)
                    )

    if not separations:
        return None
    separation_grid = np.arange(lower_bound, upper_bound + 0.125, 0.25)
    separation_score = np.asarray(
        [
            np.sum(
                np.asarray(separation_weights)
                * np.exp(-0.5 * ((np.asarray(separations) - value) / 0.5) ** 2)
            )
            for value in separation_grid
        ]
    )
    typical_separation = float(separation_grid[int(np.nanargmax(separation_score))])

    states = []
    emissions = []
    real_pair = []
    strong_column_count = 0
    step_mhz = abs(float(np.nanmedian(np.diff(frequency_axis_ghz)))) * 1e3
    for column, rows in enumerate(candidates):
        profile = evidence[:, column]
        floor = float(np.nanmedian(profile[np.isfinite(profile)]))
        column_states = []
        column_emissions = []
        column_real = []
        column_has_strong_pair = False
        for first in range(rows.size):
            for second in range(first + 1, rows.size):
                lower_row, upper_row = sorted((int(rows[first]), int(rows[second])))
                separation = float(
                    (frequency_axis_ghz[upper_row] - frequency_axis_ghz[lower_row]) * 1e3
                )
                midpoint = 0.5 * (
                    frequency_axis_ghz[upper_row] + frequency_axis_ghz[lower_row]
                )
                center_distance = abs(midpoint - primary_frequency[column]) * 1e3
                if (
                    not lower_bound <= separation <= upper_bound
                    or abs(separation - typical_separation) > float(separation_tolerance_mhz)
                    or center_distance > float(center_tolerance_mhz)
                ):
                    continue
                lower_height = float(profile[lower_row] - floor)
                upper_height = float(profile[upper_row] - floor)
                strong_pair = min(lower_height, upper_height) >= float(min_prominence_z)
                column_has_strong_pair |= strong_pair
                column_states.append((lower_row, upper_row))
                column_emissions.append(
                    0.5 * (lower_height + upper_height)
                    - 0.35
                    * ((separation - typical_separation) / separation_tolerance_mhz) ** 2
                    - 0.4 * (center_distance / center_tolerance_mhz) ** 2
                )
                # Pair persistence is established using both shoulders, but
                # once that identity is established a frame only needs to
                # resolve the shoulder we actually report.  This retains the
                # useful onset when the partner temporarily broadens/merges.
                if shoulder == "midpoint":
                    column_real.append(strong_pair)
                else:
                    column_real.append(
                        (lower_height if shoulder == "lower" else upper_height)
                        >= float(min_prominence_z)
                    )

        if column_has_strong_pair:
            strong_column_count += 1
        if not column_states:
            # A virtual partner bridges a missing/merged-shoulder frame.  It is
            # never reported as measured support.
            primary_row = int(primary_rows[column])
            offset_rows = max(1, int(round(typical_separation / step_mhz)))
            lower_row = max(0, primary_row - offset_rows)
            upper_row = primary_row
            if lower_row == primary_row:
                upper_row = min(frequency_axis_ghz.size - 1, primary_row + offset_rows)
            column_states = [(lower_row, upper_row)]
            column_emissions = [-5.0]
            column_real = [False]
        states.append(np.asarray(column_states, dtype=int))
        emissions.append(np.asarray(column_emissions, dtype=float))
        real_pair.append(np.asarray(column_real, dtype=bool))

    pair_persistence = float(strong_column_count / evidence.shape[1])
    costs = [np.full(len(column), np.inf, dtype=float) for column in states]
    back = [np.full(len(column), -1, dtype=int) for column in states]
    costs[0] = -emissions[0]
    for column in range(1, len(states)):
        previous = states[column - 1]
        for current_index, (lower_row, upper_row) in enumerate(states[column]):
            lower_jump = np.abs(
                frequency_axis_ghz[previous[:, 0]] - frequency_axis_ghz[lower_row]
            ) * 1e3
            upper_jump = np.abs(
                frequency_axis_ghz[previous[:, 1]] - frequency_axis_ghz[upper_row]
            ) * 1e3
            allowed = (lower_jump <= max_jump_mhz) & (upper_jump <= max_jump_mhz)
            transition = costs[column - 1] + 48.0 * (
                (lower_jump / max_jump_mhz) ** 2 + (upper_jump / max_jump_mhz) ** 2
            )
            transition[~allowed] = np.inf
            previous_index = int(np.argmin(transition))
            if np.isfinite(transition[previous_index]):
                costs[column][current_index] = (
                    transition[previous_index] - emissions[column][current_index]
                )
                back[column][current_index] = previous_index
        if not np.any(np.isfinite(costs[column])):
            best = int(np.nanargmax(emissions[column]))
            costs[column][best] = (
                float(np.nanmin(costs[column - 1])) - emissions[column][best] + 4.0
            )

    selected_state = int(np.nanargmin(costs[-1]))
    pair_rows = np.full((evidence.shape[1], 2), -1, dtype=int)
    measured_pair = np.zeros(evidence.shape[1], dtype=bool)
    for column in range(evidence.shape[1] - 1, -1, -1):
        pair_rows[column] = states[column][selected_state]
        measured_pair[column] = real_pair[column][selected_state]
        if column:
            selected_state = int(back[column][selected_state])
            if selected_state < 0:
                selected_state = int(np.nanargmin(costs[column - 1]))
    return pair_rows, measured_pair, typical_separation, pair_persistence, candidates


def _path_diagnostics(
    frequency_axis_ghz,
    foreground,
    evidence,
    center_map,
    path_rows,
    candidates,
    valid_columns,
    ambiguity_ratio,
    min_prominence_z,
):
    n_time = evidence.shape[1]
    centers = np.full(n_time, np.nan, dtype=float)
    widths_hz = np.full(n_time, np.nan, dtype=float)
    supported = np.zeros(n_time, dtype=bool)
    trace_score = np.full(n_time, np.nan, dtype=float)
    ambiguity = np.full(n_time, np.nan, dtype=float)
    chosen_height = np.full(n_time, np.nan, dtype=float)
    alternative_offset_mhz = np.full(n_time, np.nan, dtype=float)
    step_hz = abs(float(np.nanmedian(np.diff(frequency_axis_ghz)))) * 1e9

    for column, row in enumerate(path_rows):
        profile = evidence[:, column]
        centers[column] = _parabolic_peak(
            frequency_axis_ghz,
            center_map[:, column],
            int(row),
        )
        trace_score[column] = float(profile[row])

        center_profile = center_map[:, column]
        finite_profile = np.where(
            np.isfinite(center_profile),
            center_profile,
            np.nanmin(center_profile[np.isfinite(center_profile)]),
        )
        if (
            0 < int(row) < finite_profile.size - 1
            and finite_profile[int(row)] >= finite_profile[int(row) - 1]
            and finite_profile[int(row)] >= finite_profile[int(row) + 1]
        ):
            try:
                widths_hz[column] = float(
                    signal.peak_widths(finite_profile, [int(row)], rel_height=0.5)[0][0]
                ) * step_hz
            except Exception:
                pass

        alternatives = candidates[column][candidates[column] != row]
        if alternatives.size:
            separated = (
                np.abs(frequency_axis_ghz[alternatives] - frequency_axis_ghz[row]) * 1e3
                >= 4.0
            )
            alternatives = alternatives[separated]
        if alternatives.size:
            best_alternative = int(alternatives[np.nanargmax(profile[alternatives])])
            alternative_score = float(profile[best_alternative])
            alternative_offset_mhz[column] = float(
                (frequency_axis_ghz[best_alternative] - frequency_axis_ghz[row]) * 1e3
            )
        else:
            alternative_score = -np.inf
        # Scores are z-like and may be negative, so compare prominence above the
        # column floor rather than taking a raw ratio.
        column_floor = float(np.nanmedian(profile[np.isfinite(profile)]))
        chosen_height[column] = max(float(profile[row]) - column_floor, 0.0)
        alternative_height = max(alternative_score - column_floor, 0.0)
        ambiguity[column] = (
            alternative_height / chosen_height[column]
            if chosen_height[column] > 1e-12
            else np.inf
        )

    strong = valid_columns & (chosen_height >= float(min_prominence_z))
    competitive = ambiguity >= float(ambiguity_ratio)
    coherent_parallel_shoulder = np.zeros(n_time, dtype=bool)
    minimum_persistence = max(5, int(np.ceil(0.25 * np.count_nonzero(valid_columns))))
    for sign in (-1.0, 1.0):
        same_side = competitive & (np.sign(alternative_offset_mhz) == sign)
        offsets = alternative_offset_mhz[same_side]
        if offsets.size < minimum_persistence:
            continue
        offset_mad = 1.4826 * float(np.nanmedian(np.abs(offsets - np.nanmedian(offsets))))
        if np.isfinite(offset_mad) and offset_mad <= 1.5:
            coherent_parallel_shoulder |= same_side
    supported = strong & (~competitive | coherent_parallel_shoulder)

    return centers, widths_hz, supported, trace_score, ambiguity


def track_image_ridge(
    frequency_axis_ghz,
    image,
    expected_window_mask=None,
    polarity="auto",
    scale_widths_mhz=(0.75, 1.5, 3.0, 6.0, 12.0),
    max_jump_mhz=8.0,
    jump_penalty=128.0,
    min_prominence_z=0.6,
    ambiguity_ratio=0.95,
    shoulder="auto",
    shoulder_min_persistence=0.6,
    temporal_background="none",
    smoothing_window_points=1,
    smoothing_polyorder=2,
):
    """Track one spectroscopy ridge using raw-image evidence and path context.

    A single-ridge or explicit-shoulder trace is the sub-bin location of an
    actual image maximum.  ``shoulder='midpoint'`` first tracks an ordered
    lower/upper pair and returns their centerline.  No post-hoc temporal
    smoothing is applied.  ``temporal_background='median'`` removes each
    frequency row's time median before forming ridge evidence.  That option is
    useful for a short-lived step-response trajectory which would otherwise be
    outscored by a persistent spectral line at the final target frequency.
    """
    frequency = np.asarray(frequency_axis_ghz, dtype=float)
    raw = np.asarray(image, dtype=float)
    if frequency.ndim != 1 or frequency.size < 7:
        raise ValueError("frequency_axis_ghz must be a one-dimensional axis with at least 7 points.")
    if raw.ndim != 2 or raw.shape[0] != frequency.size:
        raise ValueError("image must have shape (frequency, time).")
    if not np.all(np.isfinite(frequency)) or np.any(np.diff(frequency) == 0.0):
        raise ValueError("frequency_axis_ghz must be finite and strictly monotonic.")
    polarity = str(polarity).strip().lower()
    if polarity not in {"bright", "dark", "auto"}:
        raise ValueError("polarity must be 'bright', 'dark', or 'auto'.")
    shoulder = str(shoulder).strip().lower()
    if shoulder not in {"auto", "lower", "upper", "midpoint"}:
        raise ValueError("shoulder must be 'auto', 'lower', 'upper', or 'midpoint'.")
    temporal_background = str(temporal_background).strip().lower()
    if temporal_background not in {"none", "median"}:
        raise ValueError("temporal_background must be 'none' or 'median'.")

    window = (
        np.ones(frequency.size, dtype=bool)
        if expected_window_mask is None
        else np.asarray(expected_window_mask, dtype=bool)
    )
    if window.shape != frequency.shape or np.count_nonzero(window) < 7:
        raise ValueError("expected_window_mask must select at least 7 frequency points.")

    # Internally use increasing frequency; returned frequencies remain physical
    # values, so no caller-visible index convention leaks out.
    if frequency[0] > frequency[-1]:
        frequency = frequency[::-1]
        raw = raw[::-1, :]
        window = window[::-1]
    finite_pixels = np.isfinite(raw)
    if temporal_background == "median":
        raw = raw - np.nanmedian(raw, axis=1, keepdims=True)
    filled, valid_columns = _fill_spectral_nans(raw)

    choices = []
    for selected_polarity in (["bright", "dark"] if polarity == "auto" else [polarity]):
        foreground, evidence, scale_evidence = _image_ridge_evidence(
            frequency,
            filled,
            window,
            selected_polarity,
            tuple(scale_widths_mhz),
        )
        center_sigma_rows = max(
            0.65,
            0.75 / (abs(float(np.nanmedian(np.diff(frequency)))) * 1e3),
        )
        center_map = ndimage.gaussian_filter1d(
            foreground,
            center_sigma_rows,
            axis=0,
            mode="nearest",
        )
        path_rows, candidates = _decode_ridge_path(
            frequency,
            evidence,
            center_map,
            window,
            max_jump_mhz,
            jump_penalty,
        )
        shoulder_mode = "single"
        shoulder_separation_mhz = np.nan
        paired_support_fraction = 0.0
        measured_pair = np.ones(evidence.shape[1], dtype=bool)
        pair_rows = None
        pair_shoulder = "midpoint" if shoulder == "auto" else shoulder
        if shoulder in {"auto", "lower", "upper", "midpoint"}:
            paired = _decode_shoulder_pair(
                frequency,
                evidence,
                center_map,
                window,
                path_rows,
                float(max_jump_mhz),
                float(min_prominence_z),
                pair_shoulder,
            )
            if paired is not None:
                (
                    pair_rows,
                    measured_pair,
                    shoulder_separation_mhz,
                    paired_support_fraction,
                    candidates,
                ) = paired
                if paired_support_fraction >= float(shoulder_min_persistence):
                    if shoulder == "auto":
                        columns = np.arange(evidence.shape[1])
                        lower_strength = float(np.nanmedian(
                            evidence[pair_rows[:, 0], columns][measured_pair]
                        ))
                        upper_strength = float(np.nanmedian(
                            evidence[pair_rows[:, 1], columns][measured_pair]
                        ))
                        pair_index = 0 if lower_strength >= upper_strength else 1
                        pair_label = "lower" if pair_index == 0 else "upper"
                        path_rows = pair_rows[:, pair_index]
                        shoulder_mode = f"paired_auto_{pair_label}"
                    else:
                        path_rows = pair_rows[
                            :, 0 if pair_shoulder in {"lower", "midpoint"} else 1
                        ]
                        shoulder_mode = f"paired_{pair_shoulder}"
                else:
                    measured_pair = np.ones(evidence.shape[1], dtype=bool)
                    shoulder_mode = (
                        "single" if shoulder == "auto" else "single_fallback"
                    )
            else:
                shoulder_mode = "single" if shoulder == "auto" else "single_fallback"
        centers, widths_hz, supported, trace_score, ambiguity = _path_diagnostics(
            frequency,
            foreground,
            evidence,
            center_map,
            path_rows,
            candidates,
            valid_columns,
            ambiguity_ratio,
            min_prominence_z,
        )
        supported &= _observed_local_support(finite_pixels, path_rows)
        if shoulder_mode.startswith("paired_"):
            supported &= measured_pair
        lower_centers = np.full(evidence.shape[1], np.nan, dtype=float)
        upper_centers = np.full(evidence.shape[1], np.nan, dtype=float)
        if shoulder_mode.startswith("paired_"):
            lower_centers = np.asarray(
                [
                    _parabolic_peak(frequency, center_map[:, column], int(row))
                    for column, row in enumerate(pair_rows[:, 0])
                ]
            )
            upper_centers = np.asarray(
                [
                    _parabolic_peak(frequency, center_map[:, column], int(row))
                    for column, row in enumerate(pair_rows[:, 1])
                ]
            )
            if shoulder_mode.startswith("paired_auto_"):
                # The sibling is an expected member of the decoded pair, not
                # an alternative identity.  Once the ordered pair has met the
                # persistence gate, support is determined by direct evidence
                # for that pair and measured pixels around the fixed label.
                supported = measured_pair & _observed_local_support(
                    finite_pixels,
                    path_rows,
                )
                ambiguity = np.zeros(evidence.shape[1], dtype=float)
            if shoulder_mode == "paired_midpoint":
                supported &= _observed_local_support(finite_pixels, pair_rows[:, 0])
                supported &= _observed_local_support(finite_pixels, pair_rows[:, 1])
                centers = 0.5 * (lower_centers + upper_centers)
                widths_hz = np.abs(upper_centers - lower_centers) * 1e9
                trace_score = 0.5 * (
                    evidence[pair_rows[:, 0], np.arange(evidence.shape[1])]
                    + evidence[pair_rows[:, 1], np.arange(evidence.shape[1])]
                )
                ambiguity = np.zeros(evidence.shape[1], dtype=float)
        quality = float(np.nanmedian(trace_score)) + 0.5 * float(np.mean(supported))
        choices.append(
            (
                quality,
                selected_polarity,
                foreground,
                evidence,
                center_map,
                scale_evidence,
                path_rows,
                centers,
                widths_hz,
                supported,
                trace_score,
                ambiguity,
                shoulder_mode,
                shoulder_separation_mhz,
                paired_support_fraction,
                lower_centers,
                upper_centers,
            )
        )

    (
        _,
        selected_polarity,
        foreground,
        evidence,
        center_map,
        scale_evidence,
        path_rows,
        centers,
        widths_hz,
        supported,
        trace_score,
        ambiguity,
        shoulder_mode,
        shoulder_separation_mhz,
        paired_support_fraction,
        lower_centers,
        upper_centers,
    ) = max(choices, key=lambda item: item[0])
    smoothed = _smooth_supported_path(
        centers,
        supported,
        window_points=smoothing_window_points,
        polyorder=smoothing_polyorder,
    )
    selected = np.where(supported, smoothed, np.nan)
    return {
        "selected_frequency_ghz": selected,
        "ridge_frequency_ghz": frequency[path_rows],
        "local_frequency_ghz": centers,
        "smoothed_frequency_ghz": smoothed,
        "extracted_if_frequency_hz": selected * 1e9,
        "extracted_fwhm_hz": widths_hz,
        "supported": supported,
        "method": [
            f"image_v26_{selected_polarity}" if ok else "image_v26_ambiguous"
            for ok in supported
        ],
        "polarity": selected_polarity,
        "score": evidence,
        "trace_score": trace_score,
        "ambiguity_ratio": ambiguity,
        "shoulder_mode": shoulder_mode,
        "shoulder_separation_mhz": shoulder_separation_mhz,
        "paired_support_fraction": paired_support_fraction,
        "lower_shoulder_frequency_ghz": lower_centers,
        "upper_shoulder_frequency_ghz": upper_centers,
        "foreground_z": foreground,
        "raw_center_evidence": center_map,
        "multiscale_evidence": scale_evidence,
        "temporal_background": temporal_background,
    }


def select_step_response_trace(
    candidates,
    *,
    target_frequency_ghz,
    baseline_frequency_ghz,
    transient_min_supported_fraction=0.30,
    transient_min_path_score=3.0,
    transient_min_excursion_mhz=10.0,
    transient_max_late_target_error_mhz=20.0,
    transient_merge_tolerance_mhz=5.0,
):
    """Choose a physical step trajectory over a persistent spectral distractor.

    A step-response map may contain both a long-lived feature near the target
    and a shorter causal trajectory.  Raw-image Viterbi scoring naturally
    favors the former because it accrues evidence for more frames.  A
    temporal-median hypothesis is accepted only when it has measured support,
    moves from the target in the direction of the baseline endpoint, and then
    returns close to the target.  Otherwise the ordinary persistent hypothesis
    remains the conservative fallback.
    """
    candidates = list(candidates)
    if not candidates:
        raise ValueError("At least one step-response trace candidate is required.")
    target = float(target_frequency_ghz)
    baseline = float(baseline_frequency_ghz)
    direction = float(np.sign(baseline - target))
    if not np.isfinite(direction) or direction == 0.0:
        direction = 1.0

    persistent_by_source = {
        candidate.get("signal_source"): candidate
        for candidate in candidates
        if candidate.get("temporal_background", "none") == "none"
    }
    diagnostics = []
    for candidate in candidates:
        local = np.asarray(candidate["local_frequency_ghz"], dtype=float)
        supported = np.asarray(candidate["supported"], dtype=bool)
        score = np.asarray(candidate["trace_score"], dtype=float)
        n_time = local.size
        early_stop = max(1, int(np.ceil(0.6 * n_time)))
        directed = direction * (local - target) * 1e3
        directed_excursion = float(np.nanmax(directed[:early_stop]))
        is_transient = candidate.get("temporal_background", "none") == "median"
        persistent = persistent_by_source.get(candidate.get("signal_source"))
        merge_index = None
        persistent_late_target_error = np.inf
        transient_late_target_error = np.inf
        recovered_excursion_mhz = -np.inf
        if is_transient and persistent is not None:
            persistent_local = np.asarray(
                persistent["local_frequency_ghz"], dtype=float
            )
            persistent_supported = np.asarray(persistent["supported"], dtype=bool)
            late_start = min(n_time - 1, int(np.floor(0.75 * n_time)))
            persistent_late_target_error = float(np.nanmedian(
                np.abs(persistent_local[late_start:] - target) * 1e3
            ))
            transient_late_target_error = float(np.nanmedian(
                np.abs(local[late_start:] - target) * 1e3
            ))
            recovered_excursion_mhz = float(
                directed_excursion
                - np.nanmedian(np.maximum(directed[late_start:], 0.0))
            )
            peak_index = int(np.nanargmax(directed[:early_stop]))
            separation_mhz = np.abs(local - persistent_local) * 1e3
            merge_candidates = np.flatnonzero(
                (np.arange(n_time) >= peak_index)
                & (separation_mhz <= float(transient_merge_tolerance_mhz))
                & supported
                & persistent_supported
            )
            if merge_candidates.size:
                merge_index = int(merge_candidates[0])
        evaluation_stop = n_time if merge_index is None else merge_index + 1
        evaluation_supported = supported[:evaluation_stop]
        support_fraction = float(np.mean(evaluation_supported))
        supported_scores = score[:evaluation_stop][evaluation_supported]
        path_score = float(
            np.nanmedian(supported_scores)
            if supported_scores.size
            else np.nanmedian(score[:evaluation_stop])
        )
        settled_or_recovering = bool(
            persistent_late_target_error
            <= float(transient_max_late_target_error_mhz)
            or (
                recovered_excursion_mhz
                >= max(10.0, 0.25 * max(directed_excursion, 0.0))
                and transient_late_target_error < directed_excursion
            )
        )
        physical_transient = bool(
            is_transient
            and persistent is not None
            and merge_index is not None
            and support_fraction >= float(transient_min_supported_fraction)
            and path_score >= float(transient_min_path_score)
            and directed_excursion >= float(transient_min_excursion_mhz)
            and settled_or_recovering
        )
        diagnostics.append({
            "signal_source": candidate.get("signal_source"),
            "temporal_background": candidate.get("temporal_background", "none"),
            "support_fraction": support_fraction,
            "path_score": path_score,
            "directed_excursion_mhz": directed_excursion,
            "persistent_late_target_error_mhz": persistent_late_target_error,
            "transient_late_target_error_mhz": transient_late_target_error,
            "recovered_excursion_mhz": recovered_excursion_mhz,
            "settled_or_recovering": settled_or_recovering,
            "merge_index": merge_index,
            "physical_transient": physical_transient,
        })

    physical = [
        (candidate, diagnostic)
        for candidate, diagnostic in zip(candidates, diagnostics)
        if diagnostic["physical_transient"]
    ]
    if physical:
        transient, selected_diagnostic = max(
            physical,
            key=lambda item: (
                item[1]["path_score"],
                item[1]["support_fraction"],
            ),
        )
        persistent = persistent_by_source[transient.get("signal_source")]
        merge_index = int(selected_diagnostic["merge_index"])
        selected = dict(persistent)
        n_time = np.asarray(transient["local_frequency_ghz"]).size
        for key, persistent_value in persistent.items():
            if key not in transient:
                continue
            persistent_array = np.asarray(persistent_value)
            transient_array = np.asarray(transient[key])
            if persistent_array.ndim == 0 or transient_array.shape != persistent_array.shape:
                continue
            if persistent_array.shape[-1] == n_time:
                combined = persistent_array.copy()
                combined[..., : merge_index + 1] = transient_array[..., : merge_index + 1]
                selected[key] = combined
        selected["temporal_background"] = "hybrid_median_to_persistent"
        selected["hybrid_merge_index"] = merge_index
        reason = "physical_transient"
    else:
        persistent = [
            (candidate, diagnostic)
            for candidate, diagnostic in zip(candidates, diagnostics)
            if diagnostic["temporal_background"] == "none"
        ]
        pool = persistent if persistent else list(zip(candidates, diagnostics))
        selected, selected_diagnostic = max(
            pool,
            key=lambda item: (
                item[1]["path_score"],
                item[1]["support_fraction"],
            ),
        )
        reason = "persistent_fallback"

    return selected, {
        "selection_reason": reason,
        "selected_signal_source": selected.get("signal_source"),
        "selected_temporal_background": selected.get(
            "temporal_background", "none"
        ),
        "selected_candidate": selected_diagnostic,
        "candidates": diagnostics,
    }
