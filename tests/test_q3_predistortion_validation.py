from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    Q3PredistortionValidation as validation,
)


def test_q3_step3b_uses_latest_high_snr_candidate():
    assert validation.CORRECTION_JSON.as_posix().endswith(
        "high_snr_3a/q3/q3_2026_09_13/"
        "q3_17_28_26_Qubit_Flux_Step_Response_"
        "rise_decay_bump_dc_compensation.json"
    )
    assert validation.validation_gain() == 1.0


def test_q3_step3b_matches_calibration_grid_and_uses_upper_shoulder():
    settings = validation.step_response_settings()
    grid = validation.frequency_grid_mhz()

    assert len(grid) == 161
    assert grid[0] == 4000.0
    assert grid[-1] == 4080.0
    assert settings["shots"] == 1000
    assert settings["freq_step"] == 0.5
    assert settings["t_min_us"] == 1.0
    assert settings["t_max_us"] == 200.0
    assert settings["t_step_us"] == 4.0
    assert settings["trace_tracking_mode"] == "image_v26"
    assert settings["trace_polarity"] == "dark"
    assert settings["trace_shoulder"] == "upper"
    assert settings["run_fit"] is False
    assert settings["run_correct"] is True
