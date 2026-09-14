import importlib


def _runner():
    return importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners."
        "Q3PredistortionEarlyValidation"
    )


def test_early_validation_is_dense_narrow_and_measurement_only():
    runner = _runner()
    settings = runner.step_response_settings()
    grid = runner.frequency_grid_mhz()

    assert len(grid) == 71
    assert grid[0] == 4025.0
    assert grid[-1] == 4060.0
    assert settings["shots"] == 200
    assert settings["freq_step"] == 0.5
    assert settings["t_min_us"] == 1.0
    assert settings["t_max_us"] == 41.0
    assert settings["t_step_us"] == 1.0
    assert settings["run_fit"] is False
    assert settings["run_correct"] is True
    assert settings["trace_tracking_mode"] == "image_v26"
    assert settings["trace_polarity"] == "dark"
    assert settings["trace_shoulder"] == "upper"


def test_early_validation_uses_current_composed_correction():
    runner = _runner()
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
        Q3PredistortionEarlyResidualRefit as residual,
    )

    assert runner.CORRECTION_JSON == residual.OUTPUT_JSON
