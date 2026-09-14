"""Compose a damped q3 residual correction from the corrected validation map."""

import os
import pickle
from pathlib import Path

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import (
    flux_predistortion,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.saved_step_response_refit import (
    compose_verified_saved_response_residual,
    refit_saved_step_response,
    verify_applied_compensation,
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

    previous, verified_timing = verify_applied_compensation(data, previous_json)
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
    composed = compose_verified_saved_response_residual(
        previous,
        result["correction"],
        damping=float(damping),
        min_multiplier=0.5,
        max_multiplier=1.5,
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
