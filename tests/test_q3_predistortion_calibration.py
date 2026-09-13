import ast
from pathlib import Path


RUNNER = (
    Path(__file__).parents[1]
    / "WorkingProjects"
    / "TLS_Spectroscopy"
    / "Client_modules"
    / "Runners"
    / "Q3PredistortionCalibration.py"
)


def _step_response_overrides():
    tree = ast.parse(RUNNER.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "update" or not node.args or not isinstance(node.args[0], ast.Dict):
            continue
        return {
            ast.literal_eval(key): ast.literal_eval(value)
            for key, value in zip(node.args[0].keys, node.args[0].values)
        }
    raise AssertionError("P3_STEP_RESPONSE.update({...}) was not found")


def test_high_snr_q3_calibration_window_and_sampling():
    settings = _step_response_overrides()

    assert settings["shots"] == 1000
    assert settings["freq_step"] == 0.5
    assert settings["auto_freq_absolute_min_mhz"] == 4000.0
    assert settings["auto_freq_absolute_max_mhz"] == 4080.0
    assert settings["t_min_us"] == 1.0
    assert settings["t_max_us"] == 200.0
    assert settings["t_step_us"] == 4.0


def test_q3_calibration_uses_image_tracker_and_no_existing_correction():
    settings = _step_response_overrides()

    assert settings["run_fit"] is True
    assert settings["run_correct"] is False
    assert settings["readout_after_park"] is True
    assert settings["trace_tracking_mode"] == "image_v26"
    assert settings["trace_shoulder"] == "auto"
    assert settings["live_plot"] is True
