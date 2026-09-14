"""Compose a damped q3 residual correction from the corrected validation map."""

import os
import pickle
from pathlib import Path

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import (
    flux_predistortion,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.saved_step_response_refit import (
    refit_saved_step_response,
)


SOURCE_PICKLE = Path(
    os.environ.get(
        "Q3_PREDISTORTION_RESIDUAL_SOURCE_PICKLE",
        "Z:/FluxTeam/Data/q3/2026_09_13/predistortion_validation/high_snr_3b/"
        "q3/q3_2026_09_13/q3_20_03_47_Qubit_Flux_Step_Response.pkl",
    )
)
PREVIOUS_JSON = Path(
    os.environ.get(
        "Q3_PREDISTORTION_PREVIOUS_JSON",
        "Z:/FluxTeam/Data/q3/2026_09_13/predistortion_validation/high_snr_3a/"
        "q3/q3_2026_09_13/q3_17_28_26_Qubit_Flux_Step_Response_"
        "upper_refit_dc_compensation.json",
    )
)
OUTPUT_JSON = Path(
    os.environ.get(
        "Q3_PREDISTORTION_RESIDUAL_JSON",
        str(
            SOURCE_PICKLE.with_name(
                SOURCE_PICKLE.stem
                + "_upper_phase_residual_composed_dc_compensation.json"
            )
        ),
    )
)
COMPOSITION_DAMPING = 0.5
_TIMING_KEYS = (
    "fit_ff_ramp_length_us",
    "fit_dt_pulseplay_us",
    "fit_dt_pulsedef_us",
)


def _portable_name(path):
    return str(path).replace("\\", "/").rsplit("/", 1)[-1]


def _verified_previous_compensation(data, previous_json):
    """Return the exact gain-scaled correction recorded by the acquisition."""
    previous_json = Path(previous_json)
    previous = flux_predistortion.load_compensation_json(previous_json)
    applied = data.get("applied_flux_tail_compensation")
    if not isinstance(applied, dict) or not applied.get("enabled", False):
        raise ValueError(
            "The saved response does not record an applied flux-tail compensation."
        )
    if applied.get("method") != previous.get("method"):
        raise ValueError("Applied and requested compensation methods do not match.")
    if _portable_name(applied.get("source", "")) != previous_json.name:
        raise ValueError(
            "The requested previous JSON is not the compensation source recorded "
            "by the saved response."
        )

    for key in ("segment_edges_ns", "multipliers"):
        recorded = np.asarray(applied.get(key, []), dtype=float)
        requested = np.asarray(previous.get(key, []), dtype=float)
        if (
            recorded.ndim != 1
            or requested.ndim != 1
            or recorded.size == 0
            or recorded.shape != requested.shape
            or not np.all(np.isfinite(recorded))
            or not np.all(np.isfinite(requested))
            or not np.allclose(recorded, requested, rtol=1e-12, atol=1e-12)
        ):
            raise ValueError(
                f"The {key} in the requested previous JSON do not match the "
                "gain-scaled correction actually applied to the saved response."
            )

    recorded_gain_value = applied.get("correction_gain", 1.0)
    requested_gain_value = previous.get("correction_gain", 1.0)
    recorded_gain = float(
        1.0 if recorded_gain_value is None else recorded_gain_value
    )
    requested_gain = float(
        1.0 if requested_gain_value is None else requested_gain_value
    )
    if not np.isclose(recorded_gain, requested_gain, rtol=1e-12, atol=1e-12):
        raise ValueError(
            "The requested previous correction gain does not match the gain "
            "actually applied to the saved response."
        )

    recorded_metadata = applied.get("metadata", {}) or {}
    requested_metadata = previous.get("metadata", {}) or {}
    data_metadata = data.get("meta_dict", {}) or {}
    expected_values = {
        "qubit": data.get("qubit"),
        "flux_channel": data_metadata.get("flux_channel"),
        "dc_offset": data.get("dc_offset"),
        "baseline_dc_offset": data.get("baseline_dc_offset"),
    }
    for key, expected in expected_values.items():
        recorded = recorded_metadata.get(key)
        requested = requested_metadata.get(key)
        if expected is None or recorded is None or requested is None:
            raise ValueError(
                f"Cannot verify previous compensation metadata field {key!r}."
            )
        if key == "qubit":
            matches = str(recorded) == str(expected) == str(requested)
        else:
            matches = bool(
                np.isclose(float(recorded), float(expected), rtol=1e-12, atol=1e-12)
                and np.isclose(
                    float(requested), float(expected), rtol=1e-12, atol=1e-12
                )
            )
        if not matches:
            raise ValueError(
                f"Previous compensation metadata {key!r} does not match the "
                "saved response."
            )

    verified_timing = {}
    for key in _TIMING_KEYS:
        recorded = recorded_metadata.get(key)
        requested = requested_metadata.get(key)
        if recorded is None or requested is None or not np.isclose(
            float(recorded), float(requested), rtol=1e-12, atol=1e-12
        ):
            raise ValueError(
                f"Cannot verify waveform timing {key!r} between the applied "
                "correction and requested previous JSON."
            )
        verified_timing[key] = float(recorded)

    # Compose from the exact gain-scaled levels stored with the acquisition,
    # while retaining the verified source path and metadata.
    verified_previous = dict(applied)
    verified_previous["source"] = str(previous_json)
    return verified_previous, verified_timing


def _metadata(
    data, result, source_pickle, previous_json, damping, verified_timing
):
    meta_dict = data.get("meta_dict", {}) or {}
    trace = result["trace"]
    return {
        "qubit": data.get("qubit", "q3"),
        "flux_channel": meta_dict.get("flux_channel", 3),
        "flux_name": meta_dict.get("flux_name", "ff_ch3"),
        "dc_offset": data.get("dc_offset"),
        "baseline_dc_offset": data.get("baseline_dc_offset"),
        "source": "Q3PredistortionResidualRefit",
        "source_pickle": str(source_pickle),
        "source_png": data.get("summary_image"),
        "previous_compensation_json": str(previous_json),
        "intended_use": "rise_decay_bump_set_dc_offset_tail_compensation",
        **verified_timing,
        "rise_decay_bump_response_domain": "voltage",
        "rise_decay_bump_response_model": "rise_decay_bump",
        "rise_decay_bump_desired_response": "median",
        "response_fit_method": result["model"]["method"],
        "response_time_origin_us": 0.0,
        "response_extrapolated_to_origin": True,
        "trace_signal_source": "magnitude",
        "trace_corroborating_signal_source": "phase",
        "trace_polarity": "dark",
        "trace_shoulder": "upper",
        "trace_shoulder_mode": trace.get("shoulder_mode"),
        "trace_shoulder_separation_mhz": trace.get(
            "shoulder_separation_mhz"
        ),
        "trace_supported_fraction": result["support_fraction"],
        "trace_first_supported_time_us": (
            result["first_supported_time_ns"] / 1e3
        ),
        "corroboration": result["corroboration"],
        "composition_damping": float(damping),
        "model_note": (
            "magnitude upper shoulder corroborated by phase, then composed "
            "as a damped residual correction"
        ),
    }


def refit_and_compose(
    source_pickle=SOURCE_PICKLE,
    previous_json=PREVIOUS_JSON,
    output_json=OUTPUT_JSON,
    damping=COMPOSITION_DAMPING,
):
    source_pickle = Path(source_pickle)
    previous_json = Path(previous_json)
    output_json = Path(output_json)
    if not source_pickle.is_file():
        raise FileNotFoundError(
            f"Saved corrected q3 step-response map not found: {source_pickle}"
        )
    if not previous_json.is_file():
        raise FileNotFoundError(
            f"Previous q3 compensation JSON not found: {previous_json}"
        )
    with source_pickle.open("rb") as stream:
        data = pickle.load(stream)

    previous, verified_timing = _verified_previous_compensation(
        data, previous_json
    )

    result = refit_saved_step_response(
        data,
        signal_source="magnitude",
        corroborating_signal_source="phase",
        max_signal_disagreement_mhz=2.0,
        polarity="dark",
        shoulder="upper",
        time_origin_ns=0.0,
        max_first_supported_ns=5_000.0,
        min_supported_fraction=0.8,
        max_jump_mhz=8.0,
    )
    composed = flux_predistortion.compose_piecewise_dc_compensations(
        previous,
        result["correction"],
        damping=float(damping),
        min_multiplier=0.5,
        max_multiplier=1.5,
    )
    if not composed.get("success", False) or composed.get(
        "multiplier_clipped", False
    ):
        raise RuntimeError(
            "Residual composition did not produce an unclipped successful correction."
        )
    flux_predistortion.save_predistortion_json(
        output_json,
        composed,
        metadata=_metadata(
            data,
            result,
            source_pickle,
            previous_json,
            float(damping),
            verified_timing,
        ),
    )
    result["composed_correction"] = composed
    result["output_json"] = str(output_json)
    return result


def main():
    print(f"[residual] source={SOURCE_PICKLE}")
    print(f"[residual] previous={PREVIOUS_JSON}")
    print(
        "[residual] tracker=magnitude/dark/upper corroborated by phase; "
        f"composition damping={COMPOSITION_DAMPING}"
    )
    result = refit_and_compose()
    composed = result["composed_correction"]
    print(
        "[residual] support="
        f"{100.0 * result['support_fraction']:.1f}%; "
        f"first={result['first_supported_time_ns'] / 1e3:.1f} us; "
        f"corroboration={result['corroboration']}"
    )
    print(
        "[residual] composed multiplier range="
        f"{min(composed['multipliers']):.6f}.."
        f"{max(composed['multipliers']):.6f}; "
        f"clipped={bool(composed['multiplier_clipped'])}"
    )
    print(f"[residual] saved={result['output_json']}")


if __name__ == "__main__":
    main()
