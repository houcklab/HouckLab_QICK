import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_predistortion
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import saved_step_response_refit


_METADATA = {
    "qubit": "q3",
    "flux_channel": 3,
    "dc_offset": -14750.0,
    "baseline_dc_offset": -25146.0,
    "fit_ff_ramp_length_us": 3.5,
    "fit_dt_pulseplay_us": 0.25,
    "fit_dt_pulsedef_us": 0.004,
}


def _write_compensation(path, *, method="rise_decay_bump_set_dc_offset_correction", metadata=None):
    flux_predistortion.save_predistortion_json(
        path,
        {
            "success": True,
            "error": None,
            "method": method,
            "multiplier_clipped": False,
            "segment_edges_ns": [0.0, 4_000.0, 8_000.0],
            "multipliers": [1.02, 1.01, 1.0],
            "undamped_multipliers": [1.02, 1.01, 1.0],
        },
        metadata=_METADATA if metadata is None else metadata,
    )


def test_discovery_accepts_supported_generic_filename_but_rejects_bad_method_and_provenance(tmp_path):
    """Would fail if discovery trusts a filename or skips metadata matching."""
    qubit_dir = tmp_path / "q3" / "nested"
    qubit_dir.mkdir(parents=True)
    _write_compensation(qubit_dir / "q3_old_dc_compensation.json")
    _write_compensation(
        qubit_dir / "q3_unsupported_dc_compensation.json", method="exponential"
    )
    _write_compensation(
        qubit_dir / "q3_wrong_provenance_dc_compensation.json",
        metadata={**_METADATA, "dc_offset": -12000.0},
    )

    found = flux_predistortion.find_latest_compensation_json(
        tmp_path,
        "q3",
        dc_offset=-14750.0,
        baseline_dc_offset=-25146.0,
    )

    assert found == str(qubit_dir / "q3_old_dc_compensation.json")


def test_discovery_reuses_the_supported_method_set_for_loading_and_matching(
    tmp_path, monkeypatch
):
    """Would fail if discovery and loading keep separate supported-method lists."""
    alternate_method = "future_set_dc_offset_correction"
    monkeypatch.setattr(
        flux_predistortion,
        "SUPPORTED_COMPENSATION_METHODS",
        {
            "rise_decay_bump_set_dc_offset_correction",
            alternate_method,
        },
        raising=False,
    )
    candidate = tmp_path / "q3" / "q3_future_dc_compensation.json"
    _write_compensation(candidate, method=alternate_method)

    assert flux_predistortion.load_compensation_json(candidate)["method"] == alternate_method
    assert flux_predistortion.find_latest_compensation_json(
        tmp_path,
        "q3",
        dc_offset=-14750.0,
        baseline_dc_offset=-25146.0,
    ) == str(candidate)


def test_discovery_skips_candidates_with_malformed_metadata(tmp_path):
    """Would fail if malformed candidate metadata aborts discovery instead of being rejected."""
    qubit_dir = tmp_path / "q3"
    valid = qubit_dir / "q3_valid_dc_compensation.json"
    _write_compensation(valid)
    _write_compensation(
        qubit_dir / "q3_list_metadata_dc_compensation.json",
        metadata=["not", "a", "mapping"],
    )
    _write_compensation(
        qubit_dir / "q3_non_numeric_metadata_dc_compensation.json",
        metadata={
            **_METADATA,
            "dc_offset": "not-a-number",
            "baseline_dc_offset": "also-not-a-number",
        },
    )

    assert flux_predistortion.find_latest_compensation_json(
        tmp_path,
        "q3",
        dc_offset=-14750.0,
        baseline_dc_offset=-25146.0,
    ) == str(valid)


def test_saved_response_composition_requires_the_recorded_applied_correction(tmp_path):
    """Would fail if composition accepts a different previous filter than acquisition used."""
    previous_path = tmp_path / "q3_previous_dc_compensation.json"
    _write_compensation(previous_path)
    applied = flux_predistortion.load_compensation_json(previous_path)
    data = {
        "qubit": "q3",
        "dc_offset": -14750.0,
        "baseline_dc_offset": -25146.0,
        "meta_dict": {"flux_channel": 3},
        "applied_flux_tail_compensation": applied,
    }
    adjustment = {
        "success": True,
        "method": "rise_decay_bump_set_dc_offset_correction",
        "multiplier_clipped": False,
        "segment_edges_ns": [0.0, 4_000.0, 8_000.0],
        "multipliers": [1.01, 1.005, 1.0],
    }

    composed, timing = saved_step_response_refit.compose_saved_response_residual(
        data, previous_path, adjustment, damping=0.25
    )

    assert composed["composed_with_applied_flux_tail_compensation"] is True
    assert composed["composition_damping"] == 0.25
    assert composed["source_compensation"] == str(previous_path)
    assert timing == {
        "fit_ff_ramp_length_us": 3.5,
        "fit_dt_pulseplay_us": 0.25,
        "fit_dt_pulsedef_us": 0.004,
    }

    data["applied_flux_tail_compensation"]["multipliers"] = [1.03, 1.01, 1.0]
    with pytest.raises(ValueError, match="multipliers"):
        saved_step_response_refit.compose_saved_response_residual(
            data, previous_path, adjustment
        )


def _stub_module(monkeypatch, name, **attributes):
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)


def _load_step3_runner(monkeypatch):
    class ResetSession:
        @classmethod
        def passive(cls):
            return cls()

        def apply(self, config):
            return dict(config)

    class StepResponse:
        calls = []

        def __init__(self, **kwargs):
            type(self).calls.append(kwargs)
            self.data = {
                "rise_decay_bump_dc_compensation_json": "/tmp/composed.json"
            }

        @staticmethod
        def load_piecewise_dc_compensation_json(_path):
            return {
                "enabled": True,
                "method": "rise_decay_bump_set_dc_offset_correction",
                "source": "/tmp/base.json",
                "segment_edges_ns": [0.0, 4_000.0],
                "multipliers": [1.02, 1.0],
                "undamped_multipliers": [1.02, 1.0],
                "metadata": _METADATA,
            }

        def acquire(self, **_kwargs):
            return self.data

        def save_data(self):
            pass

        def save_config(self):
            pass

    _stub_module(monkeypatch, "qick", QickConfig=object)
    _stub_module(
        monkeypatch,
        "WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy",
        makeProxy=lambda: (None, None),
    )
    _stub_module(
        monkeypatch,
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize",
        BaseConfig={}, outerFolder="/tmp",
    )
    _stub_module(
        monkeypatch,
        "WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.local_settings",
        apply_local_overrides=lambda *_args: None,
    )
    for name, attribute in (
        ("mTransmissionVsFFGain", "TransmissionVsFFGain"),
        ("mQubitLongTimeSpecVsFlux", "QubitLongTimeSpecVsFlux"),
        ("mSingleShot1Q", "SingleShot1Q"),
    ):
        _stub_module(
            monkeypatch,
            f"WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.{name}",
            **{attribute: object},
        )
    _stub_module(
        monkeypatch,
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mQubitFluxStepResponse",
        QubitFluxStepResponse=StepResponse,
    )
    _stub_module(
        monkeypatch,
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mT1VsFlux",
        T1FullCurveVsFlux=object,
        T1FullCurveVsFluxFromFit=object,
        T13PointVsFlux=object,
        build_wall_clock_repeat_metadata=lambda *_args, **_kwargs: {},
        get_wall_clock_repeat_spec=lambda *_args, **_kwargs: {},
        get_wall_clock_repeat_full_spec=lambda *_args, **_kwargs: {},
        save_wall_clock_repeat_full_outputs=lambda *_args, **_kwargs: None,
        _csv_base_from_pickle=lambda path: path,
    )
    _stub_module(
        monkeypatch,
        "WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production",
        AUTOMATIC_RECALIBRATION_MIN=1,
        PASSIVE_T1_RESET_US=1,
        ProductionResetSession=ResetSession,
        normalize_reset_mode=lambda value: value,
        prepare_reset_session=lambda *_args, **_kwargs: None,
    )
    path = Path(__file__).parents[1] / "WorkingProjects/TLS_Spectroscopy/Client_modules/Runners/TLSSpectroscopy.py"
    spec = importlib.util.spec_from_file_location("test_tls_step3_runner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, StepResponse


def test_step3b_composes_residual_when_enabled_and_returns_composed_json(monkeypatch):
    """Would fail if regular step 3b validates only or returns the base JSON."""
    runner, response = _load_step3_runner(monkeypatch)
    runner.P3_STEP_RESPONSE = {
        **runner.P3_STEP_RESPONSE,
        "fit_residual_composition": True,
        "residual_composition_damping": 0.25,
        "live_plot": False,
    }
    runner.STEP3B_GAIN_SWEEP = None
    monkeypatch.setattr(runner.fpd, "load_compensation_json", lambda _path: {})

    result = runner.run_step3b_step_response_correct("/tmp", None, None, "/tmp/base.json")

    assert result == "/tmp/composed.json"
    assert response.calls[-1]["fit_rise_decay_bump_dc_correction"] is True
    assert response.calls[-1]["compose_with_applied_flux_tail_compensation"] is True
    assert response.calls[-1]["composition_damping"] == 0.25


def test_step3b_gain_sweep_returns_the_last_composed_json_when_enabled(monkeypatch):
    """Would fail if the gain-sweep branch discards its composed correction."""
    runner, _response = _load_step3_runner(monkeypatch)
    runner.P3_STEP_RESPONSE = {
        **runner.P3_STEP_RESPONSE,
        "fit_residual_composition": True,
        "live_plot": False,
    }
    runner.STEP3B_GAIN_SWEEP = [0.5]
    monkeypatch.setattr(runner, "_gain_sweep_row", lambda *_args: {})
    monkeypatch.setattr(runner, "_write_gain_sweep_summary_csv", lambda *_args: None)
    monkeypatch.setattr(runner.fpd, "load_compensation_json", lambda _path: {})

    result = runner.run_step3b_step_response_correct("/tmp", None, None, "/tmp/base.json")

    assert result == "/tmp/composed.json"


def test_step3a_ignores_the_step3b_residual_composition_control(monkeypatch):
    """Would fail if enabling 3b composition tries to compose without a base filter in 3a."""
    runner, response = _load_step3_runner(monkeypatch)
    runner.P3_STEP_RESPONSE = {
        **runner.P3_STEP_RESPONSE,
        "fit_residual_composition": True,
        "residual_composition_damping": 0.25,
        "live_plot": False,
    }

    result = runner.run_step3a_step_response_fit("/tmp", None, None)

    assert result == "/tmp/composed.json"
    assert response.calls[-1]["compose_with_applied_flux_tail_compensation"] is False
