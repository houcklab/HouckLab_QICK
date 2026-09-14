import pickle

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_predistortion
from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    Q3PredistortionRefit as runner,
)


def test_refit_pickle_writes_a_loadable_production_correction(tmp_path, monkeypatch):
    source = tmp_path / "q3_source.pkl"
    output = tmp_path / "q3_upper_refit_dc_compensation.json"
    source.write_bytes(pickle.dumps({"qubit": "q3"}))
    correction = {
        "success": True,
        "error": None,
        "method": "rise_decay_bump_set_dc_offset_correction",
        "normalization": 1.0,
        "rms": 0.001,
        "multiplier_clipped": False,
        "segment_edges_ns": [0.0, 4_000.0, 8_000.0],
        "multipliers": [1.01, 1.005, 1.0],
        "undamped_multipliers": [1.01, 1.005, 1.0],
        "rise_decay_bump_model": {},
        "model_note": "test causal model",
    }
    monkeypatch.setattr(
        runner,
        "refit_saved_step_response",
        lambda _data, **_kwargs: {
            "correction": correction,
            "model": {"method": "late_exponential_plus_rise_decay_bump"},
            "support_fraction": 0.92,
            "first_supported_time_ns": 1_000.0,
            "trace": {
                "shoulder_mode": "paired_upper",
                "shoulder_separation_mhz": 4.75,
            },
        },
    )

    result = runner.refit_pickle(source, output)
    saved = flux_predistortion.load_predistortion_json(output)

    assert result["support_fraction"] == 0.92
    assert saved["method"] == "rise_decay_bump_set_dc_offset_correction"
    assert saved["success"] is True
    assert saved["metadata"]["source_pickle"] == str(source)
    assert saved["metadata"]["trace_signal_source"] == "magnitude"
    assert saved["metadata"]["trace_shoulder"] == "upper"
    assert saved["metadata"]["response_time_origin_us"] == 0.0
    assert saved["metadata"]["fit_ff_ramp_length_us"] == 4.0
    assert saved["metadata"]["fit_dt_pulseplay_us"] == 0.5


def test_q3_validation_no_longer_points_to_the_first_offline_refit_candidate():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
        Q3PredistortionValidation as validation,
    )

    assert validation.CORRECTION_JSON.name.endswith(
        "_upper_phase_residual_composed_dc_compensation.json"
    )
