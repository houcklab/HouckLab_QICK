"""Refit the saved q3 high-SNR map with a fixed upper-shoulder trace."""

import os
import pickle
from pathlib import Path

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import (
    flux_predistortion,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.saved_step_response_refit import (
    refit_saved_step_response,
)


SOURCE_PICKLE = Path(
    os.environ.get(
        "Q3_PREDISTORTION_SOURCE_PICKLE",
        "Z:/FluxTeam/Data/q3/2026_09_13/predistortion_validation/high_snr_3a/"
        "q3/q3_2026_09_13/q3_17_28_26_Qubit_Flux_Step_Response.pkl",
    )
)
OUTPUT_JSON = Path(
    os.environ.get(
        "Q3_PREDISTORTION_REFIT_JSON",
        str(SOURCE_PICKLE.with_name(
            SOURCE_PICKLE.stem + "_upper_refit_dc_compensation.json"
        )),
    )
)


def _metadata(data, result, source_pickle):
    meta_dict = data.get("meta_dict", {}) or {}
    trace = result["trace"]
    return {
        "qubit": data.get("qubit", "q3"),
        "flux_channel": meta_dict.get("flux_channel", 3),
        "flux_name": meta_dict.get("flux_name", "ff_ch3"),
        "dc_offset": data.get("dc_offset"),
        "baseline_dc_offset": data.get("baseline_dc_offset"),
        "source": "Q3PredistortionRefit",
        "source_pickle": str(source_pickle),
        "source_png": data.get("summary_image"),
        "intended_use": "rise_decay_bump_set_dc_offset_tail_compensation",
        "fit_ff_ramp_length_us": 4.0,
        "fit_dt_pulseplay_us": 0.5,
        "fit_dt_pulsedef_us": 0.002,
        "rise_decay_bump_response_domain": "voltage",
        "rise_decay_bump_response_model": "rise_decay_bump",
        "rise_decay_bump_desired_response": "median",
        "response_fit_method": result["model"]["method"],
        "response_time_origin_us": 0.0,
        "response_extrapolated_to_origin": True,
        "trace_signal_source": "magnitude",
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
        "model_note": result["correction"]["model_note"],
    }


def refit_pickle(source_pickle=SOURCE_PICKLE, output_json=OUTPUT_JSON):
    source_pickle = Path(source_pickle)
    output_json = Path(output_json)
    if not source_pickle.is_file():
        raise FileNotFoundError(f"Saved q3 step-response map not found: {source_pickle}")
    with source_pickle.open("rb") as stream:
        data = pickle.load(stream)

    result = refit_saved_step_response(
        data,
        signal_source="magnitude",
        polarity="dark",
        shoulder="upper",
        time_origin_ns=0.0,
        max_first_supported_ns=5_000.0,
        min_supported_fraction=0.8,
        max_jump_mhz=8.0,
    )
    flux_predistortion.save_predistortion_json(
        output_json,
        result["correction"],
        metadata=_metadata(data, result, source_pickle),
    )
    result["output_json"] = str(output_json)
    return result


def main():
    print(f"[refit] source={SOURCE_PICKLE}")
    print("[refit] tracker=magnitude/dark/upper; physical time origin=0 us")
    result = refit_pickle()
    trace = result["trace"]
    correction = result["correction"]
    print(
        "[refit] support="
        f"{100.0 * result['support_fraction']:.1f}%; "
        f"first={result['first_supported_time_ns'] / 1e3:.1f} us; "
        f"shoulder separation={trace.get('shoulder_separation_mhz')} MHz"
    )
    print(
        "[refit] predicted correction RMS="
        f"{float(correction['rms']):.6g}; "
        f"clipped={bool(correction['multiplier_clipped'])}"
    )
    print(f"[refit] saved={result['output_json']}")


if __name__ == "__main__":
    main()
