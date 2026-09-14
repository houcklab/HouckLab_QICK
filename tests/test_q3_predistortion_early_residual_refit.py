import importlib
from pathlib import Path


def _runner():
    return importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners."
        "Q3PredistortionEarlyResidualRefit"
    )


def test_early_residual_refit_uses_dense_map_and_damped_composition(monkeypatch):
    runner = _runner()
    captured = {}

    def fake_refit_and_compose(**kwargs):
        captured.update(kwargs)
        return {
            "support_fraction": 0.95,
            "first_supported_time_ns": 2_000.0,
            "corroboration": {"identity_swaps_resolved": 4},
            "composed_correction": {
                "multipliers": [1.0, 1.08, 1.0],
                "multiplier_clipped": False,
            },
            "output_json": str(runner.OUTPUT_JSON),
        }

    monkeypatch.setattr(runner, "refit_and_compose", fake_refit_and_compose)
    result = runner.make_final_residual()

    assert runner.SOURCE_PICKLE.name == (
        "q3_21_06_10_Qubit_Flux_Step_Response.pkl"
    )
    assert runner.PREVIOUS_JSON.name.endswith(
        "upper_phase_residual_composed_dc_compensation.json"
    )
    assert runner.COMPOSITION_DAMPING == 0.75
    assert captured == {
        "source_pickle": runner.SOURCE_PICKLE,
        "previous_json": runner.PREVIOUS_JSON,
        "output_json": runner.OUTPUT_JSON,
        "damping": 0.75,
    }
    assert result["support_fraction"] == 0.95


def test_final_dense_validation_points_to_early_residual_candidate():
    runner = _runner()
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
        Q3PredistortionEarlyValidation as validation,
    )

    assert validation.CORRECTION_JSON == runner.OUTPUT_JSON
    assert Path(runner.OUTPUT_JSON).name.endswith(
        "upper_phase_early_residual_composed_dc_compensation.json"
    )
