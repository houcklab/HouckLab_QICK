import ast
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


SOURCE = (Path(__file__).parents[1] /
          "WorkingProjects/TLS_Spectroscopy/Client_modules/Experiments/mQubitFluxStepResponse.py")


def _method(name):
    module = ast.parse(SOURCE.read_text())
    cls = next(node for node in module.body if isinstance(node, ast.ClassDef) and
               node.name == "QubitFluxStepResponse")
    function = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == name)
    function.decorator_list = []
    namespace = {"np": np, "fpd": SimpleNamespace(
        mask_unsupported_trace=lambda values, supported: np.where(supported, values, np.nan))}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace[name]


def _top_level_function(name):
    module = ast.parse(SOURCE.read_text())
    function = next(node for node in module.body if isinstance(node, ast.FunctionDef)
                    and node.name == name)
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace[name]


def _fake_experiment():
    frequency = np.arange(4.04, 4.201, 0.001)
    time_us = np.arange(0.0, 80.0)
    truth = 4.08 + 0.08 * np.exp(-time_us / 30.0)
    image = np.full((frequency.size, time_us.size), -75.0)
    for j, center in enumerate(truth):
        image[:, j] += 5 * np.exp(-0.5 * ((frequency - center) / 0.0014) ** 2)
    fake = SimpleNamespace(
        trace_tracking_mode="consensus_v1", trace_shoulder="auto",
        trace_polarity="bright", trace_max_jump_mhz=8.0,
        trace_min_supported_fraction=0.0,
        meta_dict={"q_LO": {"LO_freq": 4e9}},
        f_vec=frequency * 1e9 - 4e9, t_vec=time_us * 1000,
        data={}, dc_offset=20000, baseline_dc_offset=10000,
        _compute_expected_frequencies=lambda: (4.20, 4.08, 0.10),
        _frequency_to_local_flux_branch=lambda x: 10000 + (4.2 - x) / 1.2 * 10000,
    )
    return fake, image, truth


def test_qick_consensus_native_map_agrees_with_saved_map_core():
    fake, image, truth = _fake_experiment()
    _method("_extract_trace_from_map")(fake, image)
    observed = fake.data["extracted_qubit_frequency_ghz"]
    supported = np.asarray(fake.data["trace_supported"], dtype=bool)
    assert fake.data["trace_algorithm_version"] == "step-trace-v1"
    assert fake.data["trace_quality_accepted"]
    assert np.nanmedian(np.abs(observed[supported] - truth[supported])) < 0.002


def test_qick_consensus_respects_expected_frequency_window():
    fake, image, truth = _fake_experiment()
    fake._compute_expected_frequencies = lambda: (4.08, 4.08, 0.02)
    frequency = (fake.meta_dict["q_LO"]["LO_freq"] + fake.f_vec) / 1e9
    image += 10 * np.exp(-0.5 * ((frequency[:, None] - 4.19) / 0.001) ** 2)
    _method("_extract_trace_from_map")(fake, image)
    observed = fake.data["extracted_qubit_frequency_ghz"]
    assert np.nanmax(observed) <= 4.10
    assert np.nanmedian(np.abs(observed[60:] - truth[60:])) < 0.002


def test_qick_consensus_rejection_blocks_correction_fit():
    fake, _, _ = _fake_experiment()
    fake.fit_rise_decay_bump_dc_correction = True
    fake.data["trace_quality_accepted"] = False
    fake.data["trace_quality_reasons"] = ("edge clipped",)
    with pytest.raises(RuntimeError, match="edge clipped"):
        _method("_fit_rise_decay_bump_dc_correction_from_step_response")(fake)


def test_qick_consensus_rejects_mismatched_applied_prior():
    fake, _, _ = _fake_experiment()
    fake.fit_rise_decay_bump_dc_correction = True
    fake.data["trace_quality_accepted"] = True
    fake.compose_with_applied_flux_tail_compensation = True
    fake.meta_dict["flux_channel"] = 1
    fake.flux_tail_compensation = {
        "segment_edges_ns": [0, 2000], "multipliers": [1, 1.01],
        "metadata": {"baseline_dc_offset": 10000, "dc_offset": 21000,
                     "flux_channel": 1},
    }
    with pytest.raises(ValueError, match="prior"):
        _method("_fit_rise_decay_bump_dc_correction_from_step_response")(fake)


def test_qick_consensus_persists_raw_data_when_fit_is_rejected():
    helper = _top_level_function("_finalize_consensus_analysis")
    events = []
    data = {"raw_sweep_csv": "already-saved.csv"}
    def fail():
        raise RuntimeError("quality gate rejected")
    helper(fail, lambda: events.append("figures"),
           lambda: events.append("pickle"), data)
    assert events == ["figures", "pickle"]
    assert data["raw_sweep_csv"] == "already-saved.csv"
    assert "quality gate rejected" in data["correction_fit_error"]
