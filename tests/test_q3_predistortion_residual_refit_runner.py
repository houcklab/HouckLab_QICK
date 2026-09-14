import importlib
import pickle

import pytest

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_predistortion


def _runner():
    return importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners."
        "Q3PredistortionResidualRefit"
    )


def test_residual_refit_corroborates_with_phase_and_saves_composed_candidate(
    tmp_path, monkeypatch
):
    runner = _runner()
    previous_path = tmp_path / "q3_previous_dc_compensation.json"
    flux_predistortion.save_predistortion_json(
        previous_path,
        {
            "success": True,
            "error": None,
            "method": "rise_decay_bump_set_dc_offset_correction",
            "rms": 0.001,
            "multiplier_clipped": False,
            "segment_edges_ns": [0.0, 4_000.0, 8_000.0],
            "multipliers": [1.02, 1.01, 1.0],
            "undamped_multipliers": [1.02, 1.01, 1.0],
        },
        metadata={
            "qubit": "q3",
            "flux_channel": 3,
            "dc_offset": -14_750.0,
            "baseline_dc_offset": -25_146.0,
            "fit_ff_ramp_length_us": 3.5,
            "fit_dt_pulseplay_us": 0.25,
            "fit_dt_pulsedef_us": 0.004,
        },
    )
    applied = flux_predistortion.load_compensation_json(previous_path)
    source = tmp_path / "q3_corrected_response.pkl"
    source.write_bytes(
        pickle.dumps(
            {
                "qubit": "q3",
                "dc_offset": -14_750.0,
                "baseline_dc_offset": -25_146.0,
                "meta_dict": {"flux_channel": 3, "flux_name": "ff_ch3"},
                "applied_flux_tail_compensation": applied,
            }
        )
    )
    output = tmp_path / "q3_residual_composed_dc_compensation.json"
    adjustment = {
        "success": True,
        "error": None,
        "method": "rise_decay_bump_set_dc_offset_correction",
        "rms": 0.0002,
        "multiplier_clipped": False,
        "segment_edges_ns": [0.0, 4_000.0, 8_000.0],
        "multipliers": [1.01, 1.005, 1.0],
        "undamped_multipliers": [1.01, 1.005, 1.0],
    }
    captured = {}

    def fake_refit(_data, **kwargs):
        captured.update(kwargs)
        return {
            "correction": adjustment,
            "model": {"method": "late_exponential_plus_rise_decay_bump"},
            "support_fraction": 1.0,
            "first_supported_time_ns": 1_000.0,
            "corroboration": {
                "source": "phase",
                "secondary_only_points": 5,
                "identity_swaps_resolved": 3,
                "rejected_disagreements": 0,
            },
            "trace": {
                "shoulder_mode": "paired_upper",
                "shoulder_separation_mhz": 4.75,
            },
        }

    monkeypatch.setattr(runner, "refit_saved_step_response", fake_refit)

    result = runner.refit_and_compose(
        source_pickle=source,
        previous_json=previous_path,
        output_json=output,
        damping=0.5,
    )
    saved = flux_predistortion.load_predistortion_json(output)

    assert captured["signal_source"] == "magnitude"
    assert captured["corroborating_signal_source"] == "phase"
    assert captured["shoulder"] == "upper"
    assert saved["composed_with_applied_flux_tail_compensation"] is True
    assert saved["composition_damping"] == 0.5
    assert saved["source_compensation"] == str(previous_path)
    assert saved["metadata"]["source_pickle"] == str(source)
    assert saved["metadata"]["corroboration"]["identity_swaps_resolved"] == 3
    assert saved["metadata"]["fit_ff_ramp_length_us"] == 3.5
    assert saved["metadata"]["fit_dt_pulseplay_us"] == 0.25
    assert saved["metadata"]["fit_dt_pulsedef_us"] == 0.004
    assert result["output_json"] == str(output)


def test_residual_refit_rejects_previous_filter_not_applied_to_source_map(
    tmp_path, monkeypatch
):
    runner = _runner()
    previous_path = tmp_path / "q3_previous_dc_compensation.json"
    metadata = {
        "qubit": "q3",
        "flux_channel": 3,
        "dc_offset": -14_750.0,
        "baseline_dc_offset": -25_146.0,
        "fit_ff_ramp_length_us": 4.0,
        "fit_dt_pulseplay_us": 0.5,
        "fit_dt_pulsedef_us": 0.002,
    }
    flux_predistortion.save_predistortion_json(
        previous_path,
        {
            "success": True,
            "error": None,
            "method": "rise_decay_bump_set_dc_offset_correction",
            "rms": 0.001,
            "multiplier_clipped": False,
            "segment_edges_ns": [0.0, 4_000.0, 8_000.0],
            "multipliers": [1.02, 1.01, 1.0],
            "undamped_multipliers": [1.02, 1.01, 1.0],
        },
        metadata=metadata,
    )
    applied = flux_predistortion.load_compensation_json(previous_path)
    applied["multipliers"] = [1.03, 1.01, 1.0]
    source = tmp_path / "q3_corrected_response.pkl"
    source.write_bytes(
        pickle.dumps(
            {
                "qubit": "q3",
                "dc_offset": -14_750.0,
                "baseline_dc_offset": -25_146.0,
                "meta_dict": {"flux_channel": 3, "flux_name": "ff_ch3"},
                "applied_flux_tail_compensation": applied,
            }
        )
    )
    monkeypatch.setattr(
        runner,
        "refit_saved_step_response",
        lambda *_args, **_kwargs: pytest.fail(
            "trace refit must not run after provenance validation fails"
        ),
    )

    with pytest.raises(ValueError, match="multipliers"):
        runner.refit_and_compose(
            source_pickle=source,
            previous_json=previous_path,
            output_json=tmp_path / "unsafe.json",
        )


def test_final_validation_points_to_residual_composed_candidate():
    runner = _runner()
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
        Q3PredistortionValidation as validation,
    )

    assert validation.CORRECTION_JSON == runner.OUTPUT_JSON
