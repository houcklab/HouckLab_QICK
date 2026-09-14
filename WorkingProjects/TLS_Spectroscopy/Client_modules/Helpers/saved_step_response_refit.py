"""Refit a saved step-response map without reacquiring controller data."""

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_fit
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_predistortion
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.image_ridge_tracker import (
    track_image_ridge,
)


_SIGNAL_KEYS = {
    "magnitude": "IQ_mag",
    "phase": "IQ_phase",
}


def refit_saved_step_response(
    data,
    *,
    signal_source="magnitude",
    corroborating_signal_source=None,
    max_signal_disagreement_mhz=2.0,
    polarity="dark",
    shoulder="upper",
    time_origin_ns=0.0,
    max_first_supported_ns=5_000.0,
    min_supported_fraction=0.8,
    max_jump_mhz=8.0,
    fit_tail_fraction=0.25,
    regularization=0.02,
    min_multiplier=0.5,
    max_multiplier=1.5,
    desired_response="median",
):
    """Track one fixed ridge identity and refit its causal DC correction."""
    try:
        signal_key = _SIGNAL_KEYS[str(signal_source).strip().lower()]
    except KeyError as exc:
        raise ValueError("signal_source must be 'magnitude' or 'phase'.") from exc

    frequency_axis_ghz = np.asarray(data["fit_frequency_axis_ghz"], dtype=float)
    time_ns = np.asarray(data["t_vec"], dtype=float)
    signal_map = np.asarray(data[signal_key], dtype=float)
    if signal_map.shape != (frequency_axis_ghz.size, time_ns.size):
        raise ValueError(
            "Saved signal map shape must be (frequency points, time points)."
        )

    expected_window_mask = np.asarray(
        data.get(
            "fit_frequency_window_mask",
            np.ones(frequency_axis_ghz.size, dtype=bool),
        ),
        dtype=bool,
    )
    trace = track_image_ridge(
        frequency_axis_ghz,
        signal_map,
        expected_window_mask=expected_window_mask,
        polarity=polarity,
        max_jump_mhz=max_jump_mhz,
        shoulder=shoulder,
    )
    selected_frequency_ghz = np.asarray(
        trace["selected_frequency_ghz"], dtype=float
    )
    supported = np.asarray(trace["supported"], dtype=bool)
    corroboration = {
        "source": None,
        "secondary_only_points": 0,
        "identity_swaps_resolved": 0,
        "rejected_disagreements": 0,
    }
    if corroborating_signal_source is not None:
        corroborating_name = str(corroborating_signal_source).strip().lower()
        try:
            corroborating_key = _SIGNAL_KEYS[corroborating_name]
        except KeyError as exc:
            raise ValueError(
                "corroborating_signal_source must be 'magnitude', 'phase', or None."
            ) from exc
        if corroborating_key == signal_key:
            raise ValueError(
                "corroborating_signal_source must differ from signal_source."
            )
        corroborating_map = np.asarray(data[corroborating_key], dtype=float)
        if corroborating_map.shape != signal_map.shape:
            raise ValueError(
                "Saved corroborating signal map shape must match the primary signal map."
            )
        max_disagreement = float(max_signal_disagreement_mhz)
        if not np.isfinite(max_disagreement) or max_disagreement <= 0.0:
            raise ValueError("max_signal_disagreement_mhz must be finite and positive.")
        corroborating_trace = track_image_ridge(
            frequency_axis_ghz,
            corroborating_map,
            expected_window_mask=expected_window_mask,
            polarity=polarity,
            max_jump_mhz=max_jump_mhz,
            shoulder=shoulder,
        )
        corroborating_frequency = np.asarray(
            corroborating_trace["selected_frequency_ghz"], dtype=float
        )
        corroborating_supported = np.asarray(
            corroborating_trace["supported"], dtype=bool
        ) & np.isfinite(corroborating_frequency)
        primary_supported = supported & np.isfinite(selected_frequency_ghz)
        secondary_only = (~primary_supported) & corroborating_supported
        selected_frequency_ghz = selected_frequency_ghz.copy()
        selected_frequency_ghz[secondary_only] = corroborating_frequency[secondary_only]
        supported = primary_supported | secondary_only

        both = primary_supported & corroborating_supported
        disagreement_mhz = (
            np.abs(selected_frequency_ghz - corroborating_frequency) * 1e3
        )
        conflicts = both & (disagreement_mhz > max_disagreement)
        separation_mhz = float(trace.get("shoulder_separation_mhz", np.nan))
        plausible_limit_mhz = (
            1.75 * separation_mhz
            if np.isfinite(separation_mhz) and separation_mhz > 0.0
            else 4.0 * max_disagreement
        )
        plausible_swaps = conflicts & (disagreement_mhz <= plausible_limit_mhz)
        if shoulder == "upper":
            selected_frequency_ghz[plausible_swaps] = np.maximum(
                selected_frequency_ghz[plausible_swaps],
                corroborating_frequency[plausible_swaps],
            )
        elif shoulder == "lower":
            selected_frequency_ghz[plausible_swaps] = np.minimum(
                selected_frequency_ghz[plausible_swaps],
                corroborating_frequency[plausible_swaps],
            )
        else:
            plausible_swaps[:] = False
        rejected = conflicts & ~plausible_swaps
        supported[rejected] = False
        selected_frequency_ghz[~supported] = np.nan
        trace = dict(trace)
        trace["selected_frequency_ghz"] = selected_frequency_ghz.copy()
        trace["supported"] = supported.copy()
        trace["corroborating_trace"] = corroborating_trace
        trace["corroborating_signal_source"] = corroborating_name
        corroboration = {
            "source": corroborating_name,
            "secondary_only_points": int(np.count_nonzero(secondary_only)),
            "identity_swaps_resolved": int(np.count_nonzero(plausible_swaps)),
            "rejected_disagreements": int(np.count_nonzero(rejected)),
        }
    supported &= np.isfinite(selected_frequency_ghz) & np.isfinite(time_ns)
    if not np.any(supported):
        raise ValueError("The saved map has no supported trace points.")
    first_supported_time_ns = float(np.min(time_ns[supported]))
    if first_supported_time_ns > float(max_first_supported_ns):
        raise ValueError(
            f"The first supported trace point is {first_supported_time_ns / 1e3:.3f} us; "
            f"causal refitting requires support by {float(max_first_supported_ns) / 1e3:.3f} us."
        )
    support_fraction = float(np.mean(supported))
    if support_fraction < float(min_supported_fraction):
        raise ValueError(
            f"Trace support {support_fraction:.3f} is below the required "
            f"{float(min_supported_fraction):.3f}."
        )

    tracked_frequency_ghz = selected_frequency_ghz.copy()
    tracked_frequency_ghz[~supported] = np.nan
    effective_dc = flux_fit.frequency_to_local_flux_branch(
        data["flux_fit_params"],
        tracked_frequency_ghz,
        float(data["baseline_dc_offset"]),
        float(data["dc_offset"]),
    )
    voltage_denominator = float(data["dc_offset"]) - float(
        data["baseline_dc_offset"]
    )
    if abs(voltage_denominator) < 1e-15:
        raise ValueError("dc_offset and baseline_dc_offset must be distinct.")
    voltage_response = (
        effective_dc - float(data["baseline_dc_offset"])
    ) / voltage_denominator
    voltage_response[~supported] = np.nan

    model = flux_predistortion.fit_rise_decay_bump_response_model(
        time_ns,
        voltage_response,
        fit_tail_fraction=fit_tail_fraction,
        time_origin_ns=time_origin_ns,
    )
    segment_edges_ns = flux_predistortion.default_dc_tail_segment_edges(
        float(np.nanmax(model["time_zeroed_ns"]))
    )
    correction = flux_predistortion.calculate_piecewise_dc_correction(
        model["time_ns"],
        model["fit_response"],
        segment_edges_ns=segment_edges_ns,
        regularization=regularization,
        final_weight=0.0,
        normalize=False,
        tail_fraction=fit_tail_fraction,
        min_multiplier=min_multiplier,
        max_multiplier=max_multiplier,
        desired_response=desired_response,
        correction_gain=1.0,
    )
    correction.update(
        {
            "method": "rise_decay_bump_set_dc_offset_correction",
            "model_note": (
                "saved map re-tracked with a fixed ridge identity and fitted "
                "against the physical step origin"
            ),
            "rise_decay_bump_model": model,
        }
    )
    return {
        "trace": trace,
        "corroboration": corroboration,
        "tracked_frequency_ghz": tracked_frequency_ghz,
        "effective_dc_offset": effective_dc,
        "voltage_response": voltage_response,
        "first_supported_time_ns": first_supported_time_ns,
        "support_fraction": support_fraction,
        "model": model,
        "correction": correction,
    }
