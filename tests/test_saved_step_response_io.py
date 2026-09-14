import pickle

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_predistortion
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import saved_step_response_refit as runner


def test_refit_pickle_writes_a_loadable_production_correction(tmp_path, monkeypatch):
    source = tmp_path / "q8_source.pkl"
    output = tmp_path / "q8_upper_refit_dc_compensation.json"
    source.write_bytes(pickle.dumps({"qubit": "q8"}))
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

    assert hasattr(runner, "refit_pickle"), "generic saved-map writer missing"
    result = runner.refit_pickle(source, output, timing={
        "fit_ff_ramp_length_us": 4.0,
        "fit_dt_pulseplay_us": 0.5,
        "fit_dt_pulsedef_us": 0.002,
    })
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


import pytest


def test_corrected_map_requires_previous_filter_before_fitting_or_saving(tmp_path, monkeypatch):
    source = tmp_path / "corrected_response.pkl"
    output = tmp_path / "unsafe_dc_compensation.json"
    source.write_bytes(pickle.dumps({
        "applied_flux_tail_compensation": {"enabled": True},
    }))

    def unexpected_fit(*args, **kwargs):
        pytest.fail("corrected map was fitted without its previous correction")

    def unexpected_save(*args, **kwargs):
        pytest.fail("corrected map was saved without its previous correction")

    monkeypatch.setattr(runner, "refit_saved_step_response", unexpected_fit)
    monkeypatch.setattr(flux_predistortion, "save_predistortion_json", unexpected_save)
    with pytest.raises(ValueError, match="previous_json"):
        runner.refit_pickle(source, output, timing={
            "fit_ff_ramp_length_us": 4.0,
            "fit_dt_pulseplay_us": 0.5,
            "fit_dt_pulsedef_us": 0.002,
        })
    assert not output.exists()


def test_residual_refit_corroborates_with_phase_and_saves_composed_candidate(
    tmp_path, monkeypatch
):
    assert hasattr(runner, 'refit_pickle'), 'generic saved-map writer missing'
    previous_path = tmp_path / "q8_previous_dc_compensation.json"
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
            "qubit": "q8",
            "flux_channel": 3,
            "dc_offset": -14_750.0,
            "baseline_dc_offset": -25_146.0,
            "fit_ff_ramp_length_us": 3.5,
            "fit_dt_pulseplay_us": 0.25,
            "fit_dt_pulsedef_us": 0.004,
        },
    )
    applied = flux_predistortion.load_compensation_json(previous_path)
    source = tmp_path / "q8_corrected_response.pkl"
    source.write_bytes(
        pickle.dumps(
            {
                "qubit": "q8",
                "dc_offset": -14_750.0,
                "baseline_dc_offset": -25_146.0,
                "meta_dict": {"flux_channel": 3, "flux_name": "ff_ch3"},
                "applied_flux_tail_compensation": applied,
            }
        )
    )
    output = tmp_path / "q8_residual_composed_dc_compensation.json"
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

    result = runner.refit_pickle(
        source_pickle=source,
        previous_json=previous_path,
        output_json=output,
        damping=0.5,
        refit_options={"corroborating_signal_source": "phase"},
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
    assert hasattr(runner, 'refit_pickle'), 'generic saved-map writer missing'
    previous_path = tmp_path / "q8_previous_dc_compensation.json"
    metadata = {
        "qubit": "q8",
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
    source = tmp_path / "q8_corrected_response.pkl"
    source.write_bytes(
        pickle.dumps(
            {
                "qubit": "q8",
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
        runner.refit_pickle(
            source_pickle=source,
            previous_json=previous_path,
            output_json=tmp_path / "unsafe.json",
        )
