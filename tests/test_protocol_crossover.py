import importlib
import sys
import types

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.protocol_crossover import (
    apply_phase,
    annotate_metadata,
)


BASE_3PT = {
    "shots": 300,
    "Ts_us": 100.0,
    "freq_min_ghz": 3.8,
    "freq_max_ghz": 4.3,
    "wall_clock_duration_min": 10080,
    "sync_session": "production-3pt",
}

BASE_5PT = {
    "shots_per_condition": 180,
    "decay_delays_us": [40.0, 80.0, 200.0],
    "freq_min_ghz": 3.9,
    "freq_max_ghz": 4.3,
    "wall_clock_duration_min": 10080,
    "sync_session": "production-5pt",
}


def test_q3_crossover_legacy_arm_is_a_30_min_common_band_3pt_off_scan():
    plan = apply_phase(
        BASE_3PT,
        expected="legacy_off",
        environ={"Q3_PROTOCOL_CROSSOVER_PHASE": "legacy_off"},
    )

    assert plan["wall_clock_duration_min"] == 30.0
    assert plan["freq_min_ghz"] == 3.9
    assert plan["freq_max_ghz"] == 4.3
    assert plan["dc_min"] == -20550
    assert plan["dc_max"] == -11800
    assert plan["shots"] == 300
    assert plan["Ts_us"] == 100.0
    assert plan["apply_flux_tail_compensation"] is False
    assert plan["protocol_crossover_phase"] == "legacy_off"
    assert plan["protocol_crossover_calibration"] == "current_5pt_frozen"
    assert plan["output_suffix"] == "TLS_Protocol_Crossover_3pt_OFF"
    assert plan["sync_session"] == "q3_q5_protocol_crossover_20260916_3pt_off"


def test_q3_crossover_current_arm_is_a_30_min_common_band_5pt_on_scan():
    plan = apply_phase(
        BASE_5PT,
        expected="current_on",
        environ={"Q3_PROTOCOL_CROSSOVER_PHASE": "current_on"},
    )

    assert plan["wall_clock_duration_min"] == 30.0
    assert plan["freq_min_ghz"] == 3.9
    assert plan["freq_max_ghz"] == 4.3
    assert plan["shots_per_condition"] == 180
    assert plan["decay_delays_us"] == [40.0, 80.0, 200.0]
    assert plan["apply_flux_tail_compensation"] is True
    assert plan["protocol_crossover_phase"] == "current_on"
    assert plan["output_suffix"] == "TLS_Protocol_Crossover_5pt_ON"
    assert plan["sync_session"] == "q3_q5_protocol_crossover_20260916_5pt_on"


def test_q3_crossover_arms_have_equal_measurement_budget_per_frequency():
    legacy = apply_phase(
        BASE_3PT,
        expected="legacy_off",
        environ={"Q3_PROTOCOL_CROSSOVER_PHASE": "legacy_off"},
    )
    current = apply_phase(
        BASE_5PT,
        expected="current_on",
        environ={"Q3_PROTOCOL_CROSSOVER_PHASE": "current_on"},
    )

    assert 3 * legacy["shots"] == 5 * current["shots_per_condition"] == 900


def test_q3_crossover_does_not_change_normal_production_parameters():
    plan = apply_phase(BASE_5PT, expected="current_on", environ={})

    assert plan == BASE_5PT
    assert plan is not BASE_5PT


def test_q3_crossover_tags_saved_run_metadata_without_mutating_input():
    metadata = {"run_index": 4}
    params = apply_phase(
        BASE_3PT,
        expected="legacy_off",
        environ={"Q3_PROTOCOL_CROSSOVER_PHASE": "legacy_off"},
    )

    tagged = annotate_metadata(metadata, params)

    assert tagged == {
        "run_index": 4,
        "protocol_crossover_phase": "legacy_off",
        "protocol_crossover_calibration": "current_5pt_frozen",
    }
    assert metadata == {"run_index": 4}


def _runner(name):
    sys.modules.setdefault("qick", types.SimpleNamespace(AveragerProgram=object))
    sys.modules.setdefault(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q",
        types.SimpleNamespace(discriminate_shots=lambda i, q, cal: i),
    )
    return importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners." + name
    )


def test_q3_legacy_runner_exposes_the_crossover_runtime_parameters():
    runner = _runner("ThreePointApplesToApples")

    plan = runner.runtime_parameters(
        {"Q3_PROTOCOL_CROSSOVER_PHASE": "legacy_off"}
    )

    assert plan["wall_clock_duration_min"] == 30.0
    assert plan["output_suffix"] == "TLS_Protocol_Crossover_3pt_OFF"


def test_q3_current_runner_exposes_the_crossover_runtime_parameters():
    runner = _runner("FivePointApplesToApples")

    plan = runner.runtime_parameters(
        {"Q3_PROTOCOL_CROSSOVER_PHASE": "current_on"}
    )

    assert plan["wall_clock_duration_min"] == 30.0
    assert plan["output_suffix"] == "TLS_Protocol_Crossover_5pt_ON"


def test_q3_shared_integer_grid_uses_the_callers_calibrated_tls_module(monkeypatch):
    """The 5-point caller must not depend on ThreePoint.main initializing tls."""
    runner = _runner("ThreePointApplesToApples")

    class FakeTLS:
        FLUX_FIT_PARAMS = ["current-calibration"]

    def estimate(params, dc_values):
        assert params == ["current-calibration"]
        return 3.9 + 0.1 * np.asarray(dc_values, dtype=float)

    monkeypatch.setattr(runner.fx, "estimate_fit_frequency_ghz_array", estimate)
    params = {
        "dc_min": 0,
        "dc_max": 4,
        "freq_step_mhz": 100.0,
    }
    target = np.array([4.3, 4.2, 4.1])

    dc_vec, realized = runner._integer_dc_grid(params, target, FakeTLS)

    np.testing.assert_array_equal(dc_vec, [4, 3, 2])
    np.testing.assert_allclose(realized, target, atol=1e-12)
