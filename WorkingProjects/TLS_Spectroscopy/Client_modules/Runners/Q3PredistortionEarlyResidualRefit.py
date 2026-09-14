"""Compose the final q3 correction from the dense early-time validation map."""

import os
from pathlib import Path

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.Q3PredistortionResidualRefit import (
    refit_and_compose,
)


SOURCE_PICKLE = Path(
    os.environ.get(
        "Q3_PREDISTORTION_EARLY_SOURCE_PICKLE",
        "Z:/FluxTeam/Data/q3/2026_09_13/predistortion_validation/early_dense/"
        "q3/q3_2026_09_13/q3_21_06_10_Qubit_Flux_Step_Response.pkl",
    )
)
PREVIOUS_JSON = Path(
    os.environ.get(
        "Q3_PREDISTORTION_EARLY_PREVIOUS_JSON",
        "Z:/FluxTeam/Data/q3/2026_09_13/predistortion_validation/high_snr_3b/"
        "q3/q3_2026_09_13/q3_20_03_47_Qubit_Flux_Step_Response_"
        "upper_phase_residual_composed_dc_compensation.json",
    )
)
OUTPUT_JSON = Path(
    os.environ.get(
        "Q3_PREDISTORTION_EARLY_RESIDUAL_JSON",
        str(
            SOURCE_PICKLE.with_name(
                SOURCE_PICKLE.stem
                + "_upper_phase_early_residual_composed_dc_compensation.json"
            )
        ),
    )
)
COMPOSITION_DAMPING = 0.75


def make_final_residual():
    """Fit the fused upper shoulder and compose a bounded residual correction."""
    return refit_and_compose(
        source_pickle=SOURCE_PICKLE,
        previous_json=PREVIOUS_JSON,
        output_json=OUTPUT_JSON,
        damping=COMPOSITION_DAMPING,
    )


def main():
    print(f"[early residual] source={SOURCE_PICKLE}")
    print(f"[early residual] previous={PREVIOUS_JSON}")
    print(
        "[early residual] tracker=magnitude/dark/upper corroborated by phase; "
        f"composition damping={COMPOSITION_DAMPING}"
    )
    result = make_final_residual()
    composed = result["composed_correction"]
    print(
        "[early residual] support="
        f"{100.0 * result['support_fraction']:.1f}%; "
        f"first={result['first_supported_time_ns'] / 1e3:.1f} us; "
        f"corroboration={result['corroboration']}"
    )
    print(
        "[early residual] composed multiplier range="
        f"{min(composed['multipliers']):.6f}.."
        f"{max(composed['multipliers']):.6f}; "
        f"clipped={bool(composed['multiplier_clipped'])}"
    )
    print(f"[early residual] saved={result['output_json']}")


if __name__ == "__main__":
    main()
