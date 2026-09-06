import numpy as np
import pytest

from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.sscal_failure_diagnostic_q3 import (
    build_gain_axis,
    classify_result,
    pair_metrics,
    select_grid_best,
    should_run_optimizer,
)


def test_gain_axis_includes_candidate_and_stays_in_dac_range():
    gains = build_gain_axis(12000, points=13)

    assert gains.size == 13
    assert 12000 in gains
    assert np.all(np.diff(gains) > 0)
    assert gains[0] >= 1
    assert gains[-1] <= 32767


def test_pair_metrics_reports_separated_clouds_and_ordered_centers():
    ground_i = np.asarray([-1.1, -1.0, -0.9, -1.0])
    ground_q = np.asarray([0.1, -0.1, 0.0, 0.05])
    excited_i = np.asarray([0.9, 1.0, 1.1, 1.0])
    excited_q = np.asarray([0.0, 0.1, -0.1, 0.05])

    metrics = pair_metrics(ground_i, ground_q, excited_i, excited_q)

    assert metrics["fidelity"] > 0.99
    assert metrics["center_distance"] == pytest.approx(2.0, rel=0.05)
    assert metrics["separation_sigma"] > 10.0


def test_select_grid_best_uses_gain_frequency_coordinates():
    frequencies = np.asarray([4300.0, 4300.5, 4301.0])
    gains = np.asarray([8000, 10000])
    fidelity = np.asarray([[0.55, 0.72, 0.60], [0.61, 0.91, 0.70]])

    selected = select_grid_best(frequencies, gains, fidelity)

    assert selected == {
        "frequency_mhz": 4300.5,
        "gain_dac": 10000,
        "fidelity": pytest.approx(0.91),
    }


def test_optimizer_only_runs_when_exact_chevron_does_not_validate_cleanly():
    assert should_run_optimizer(chevron_exact_fidelity=0.91, ground_drift_fidelity=0.51) is False
    assert should_run_optimizer(chevron_exact_fidelity=0.70, ground_drift_fidelity=0.51) is True
    assert should_run_optimizer(chevron_exact_fidelity=0.91, ground_drift_fidelity=0.66) is True


@pytest.mark.parametrize(
    "inputs, expected",
    [
        (
            {
                "ground_drift_fidelity": 0.68,
                "current_fidelity": 0.52,
                "chevron_sigma_fidelity": 0.53,
                "qubit_grid_fidelity": 0.55,
                "readout_grid_fidelity": 0.57,
                "final_ge_fidelity": 0.56,
                "final_eg_fidelity": 0.54,
            },
            "state_order_or_slow_drift",
        ),
        (
            {
                "ground_drift_fidelity": 0.51,
                "current_fidelity": 0.53,
                "chevron_sigma_fidelity": 0.86,
                "qubit_grid_fidelity": 0.88,
                "readout_grid_fidelity": 0.89,
                "final_ge_fidelity": 0.90,
                "final_eg_fidelity": 0.89,
            },
            "pulse_sigma_mismatch",
        ),
        (
            {
                "ground_drift_fidelity": 0.51,
                "current_fidelity": 0.54,
                "chevron_sigma_fidelity": 0.56,
                "qubit_grid_fidelity": 0.87,
                "readout_grid_fidelity": 0.88,
                "final_ge_fidelity": 0.89,
                "final_eg_fidelity": 0.88,
            },
            "qubit_frequency_or_gain_mismatch",
        ),
        (
            {
                "ground_drift_fidelity": 0.50,
                "current_fidelity": 0.54,
                "chevron_sigma_fidelity": 0.55,
                "qubit_grid_fidelity": 0.61,
                "readout_grid_fidelity": 0.87,
                "final_ge_fidelity": 0.88,
                "final_eg_fidelity": 0.86,
            },
            "readout_frequency_or_gain_mismatch",
        ),
        (
            {
                "ground_drift_fidelity": 0.51,
                "current_fidelity": 0.54,
                "chevron_sigma_fidelity": 0.55,
                "qubit_grid_fidelity": 0.59,
                "readout_grid_fidelity": 0.61,
                "final_ge_fidelity": 0.60,
                "final_eg_fidelity": 0.58,
            },
            "no_resolved_qubit_state_separation",
        ),
    ],
)
def test_classify_result_separates_failure_modes(inputs, expected):
    assert classify_result(**inputs) == expected
