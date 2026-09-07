import sys
import types

import numpy as np
import pytest

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import qubit_spec_trace_fit as qst

qick = sys.modules.get("qick")
if qick is None:
    qick = types.ModuleType("qick")
    qick.AveragerProgram = type("AveragerProgram", (), {})
    qick.RAveragerProgram = type("RAveragerProgram", (), {})
    sys.modules["qick"] = qick

from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mQubitFluxStepResponse import (
    QubitFluxStepResponse,
)


def test_phase_fallback_recovers_dark_qubit_branch_when_magnitude_has_no_trace():
    rng = np.random.default_rng(9127)
    dc_v = np.linspace(-0.8667, -0.6667, 13)
    frequency_ghz = np.linspace(4.20, 4.38, 181)
    expected = qst.flux_tunable_transmon_frequency_with_tilt(
        dc_v, 24.0, 0.09, 0.31, -0.77, 0.98, -0.35
    )
    detuning_mhz = (frequency_ghz[:, None] - expected[None, :]) * 1e3
    phase = -0.22 / (1.0 + 4.0 * (detuning_mhz / 4.0) ** 2)
    phase += 0.01 * rng.standard_normal(phase.shape)
    magnitude = 12.0 + 0.01 * rng.standard_normal(phase.shape)

    result = qst.fit_qubit_spec_map(
        dc_v,
        frequency_ghz,
        magnitude,
        phase_rad=phase,
        trim_low_dc_v=0.0,
    )

    predicted = qst.flux_tunable_transmon_frequency_with_tilt(
        dc_v, *result["params"]
    )
    assert result["trace_source"] == "phase_dark"
    assert result["confident_frac"] >= 0.9
    assert np.sqrt(np.mean((predicted - expected) ** 2)) * 1e3 < 3.0


def test_flux_step_trace_automatically_uses_clear_phase_ridge():
    rng = np.random.default_rng(2271)
    frequency_ghz = np.linspace(4.25, 4.38, 131)
    time_ns = np.arange(20, dtype=float) * 5000.0
    expected = 4.315 - 0.0006 * np.arange(time_ns.size)
    detuning_mhz = (frequency_ghz[:, None] - expected[None, :]) * 1e3
    phase = -0.25 / (1.0 + 4.0 * (detuning_mhz / 4.0) ** 2)
    phase += 0.008 * rng.standard_normal(phase.shape)
    magnitude = 12.0 + 0.03 * rng.standard_normal(phase.shape)
    experiment = QubitFluxStepResponse.__new__(QubitFluxStepResponse)
    experiment.meta_dict = {"q_LO": {"LO_freq": 0.0}}
    experiment.f_vec = frequency_ghz * 1e9
    experiment.t_vec = time_ns
    experiment.trace_tracking_mode = "ridge"
    experiment.trace_polarity = "auto"
    experiment.trace_baseline_window_mhz = 25.0
    experiment.trace_max_jump_mhz = 4.0
    experiment.trace_smoothness_penalty = 0.15
    experiment.trace_local_fit_half_window_mhz = 8.0
    experiment.trace_smoothing_window_points = 9
    experiment.trace_smoothing_polyorder = 2
    experiment.trace_use_smoothed_frequency = True
    experiment.baseline_dc_offset = 0.0
    experiment.dc_offset = 1.0
    experiment.data = {}
    experiment._compute_expected_frequencies = lambda: (4.315, 4.300, 0.040)
    experiment._frequency_to_local_flux_branch = lambda values: np.asarray(values)

    experiment._extract_trace_from_map(magnitude, phase)

    measured = np.asarray(experiment.data["extracted_qubit_frequency_ghz"])
    assert experiment.data["trace_signal_source"] == "phase"
    assert np.sqrt(np.mean((measured - expected) ** 2)) * 1e3 < 2.0


def test_flux_step_inverse_uses_target_side_through_intermediate_turning_point():
    experiment = QubitFluxStepResponse.__new__(QubitFluxStepResponse)
    experiment.baseline_dc_offset = -25790.0
    experiment.dc_offset = -20000.0
    experiment.flux_fit_params = {
        "EJmax": 8.203384791028979,
        "Ec": 0.2902930003646722,
        "period_volts": 8774.00218131707,
        "phase_offset_volts": -23058.31389817458,
        "d": 0.9831224825856887,
        "tilt_slope": -1.2183803188472806e-05,
    }
    expected_dc = np.asarray([-20000.0, -19750.0, -19500.0])
    measured_frequency = experiment._evaluate_flux_model_frequency(expected_dc)

    recovered_dc = experiment._frequency_to_local_flux_branch(measured_frequency)

    assert recovered_dc == pytest.approx(expected_dc, abs=1.0)
