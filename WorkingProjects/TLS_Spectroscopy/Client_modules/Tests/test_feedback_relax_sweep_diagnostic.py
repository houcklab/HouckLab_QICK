import copy

import pytest

from WorkingProjects.TLS_Spectroscopy.Client_modules.Tests import reset_sim

reset_sim.install_stubs()

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    FeedbackRelaxSweepDiagnostic as diagnostic,
)


def test_validate_settings_accepts_positive_increasing_relax_values():
    values = diagnostic.validate_settings(
        [25, 50, 100, 200, 400, 800],
        drift_shots=500,
        probe_shots=1000,
        reset_max_iters=3,
    )

    assert values == [25.0, 50.0, 100.0, 200.0, 400.0, 800.0]


@pytest.mark.parametrize(
    "values",
    ([25, 25], [50, 25], [0, 25], [25, float("nan")]),
)
def test_validate_settings_rejects_ambiguous_or_unsafe_relax_values(values):
    with pytest.raises(ValueError):
        diagnostic.validate_settings(
            values, drift_shots=500, probe_shots=1000, reset_max_iters=3
        )


def test_summarize_point_reports_the_two_directly_measured_probabilities():
    row = diagnostic.summarize_point(
        100.0,
        {
            "reset_pi_offset_mhz": 2.25,
            "post_reset_pi_offset_mhz": 1.50,
            "reset_pi_freq_step_mhz": 0.50,
            "residual": 0.08,
            "contrast": 0.62,
            "passive_contrast": 0.80,
        },
    )

    assert row["feedback_relax_us"] == 100.0
    assert row["P_e_no_pi"] == pytest.approx(0.08)
    assert row["P_e_with_pi"] == pytest.approx(0.70)
    assert row["contrast_fraction_of_passive"] == pytest.approx(0.775)
    assert row["reset_pi_offset_mhz"] == pytest.approx(2.25)
    assert row["post_reset_pi_offset_mhz"] == pytest.approx(1.50)
    assert row["reset_pi_freq_step_mhz"] == pytest.approx(0.50)


def test_run_sweep_uses_an_isolated_reset_record_and_checkpoints_each_point():
    source_record = {"threshold_raw": 123, "rot_reset": {"c_int": 1}}
    checkpoints = []

    def calibrate(relax_us, point_record):
        point_record["drift_pi"] = {"feedback_relax_us": relax_us}
        return {
            "reset_pi_offset_mhz": relax_us / 100.0,
            "post_reset_pi_offset_mhz": 1.0,
            "reset_pi_freq_step_mhz": 0.5,
            "residual": 0.05,
            "contrast": 0.60,
            "passive_contrast": 0.75,
        }

    rows = diagnostic.run_sweep(
        [25.0, 50.0], source_record, calibrate,
        lambda current: checkpoints.append(copy.deepcopy(current)),
    )

    assert [row["feedback_relax_us"] for row in rows] == [25.0, 50.0]
    assert len(checkpoints) == 2
    assert [len(snapshot) for snapshot in checkpoints] == [1, 2]
    assert "drift_pi" not in source_record


def test_run_sweep_checkpoints_the_error_then_stops():
    checkpoints = []

    def calibrate(relax_us, point_record):
        if relax_us == 50.0:
            raise RuntimeError("hardware link lost")
        return {
            "reset_pi_offset_mhz": 1.0,
            "post_reset_pi_offset_mhz": 1.0,
            "reset_pi_freq_step_mhz": 0.0,
            "residual": 0.05,
            "contrast": 0.60,
            "passive_contrast": 0.75,
        }

    with pytest.raises(RuntimeError, match="hardware link lost"):
        diagnostic.run_sweep(
            [25.0, 50.0], {"threshold_raw": 123}, calibrate,
            lambda current: checkpoints.append(copy.deepcopy(current)),
        )

    assert len(checkpoints) == 2
    assert checkpoints[-1][-1]["feedback_relax_us"] == 50.0
    assert checkpoints[-1][-1]["status"] == "error"
    assert checkpoints[-1][-1]["error"] == "RuntimeError: hardware link lost"


def test_choose_shortest_usable_point_requires_reset_floor_and_pi_contrast():
    rows = [
        {"feedback_relax_us": 25.0, "status": "ok", "P_e_no_pi": 0.07,
         "contrast_fraction_of_passive": 0.45},
        {"feedback_relax_us": 50.0, "status": "ok", "P_e_no_pi": 0.18,
         "contrast_fraction_of_passive": 0.85},
        {"feedback_relax_us": 100.0, "status": "ok", "P_e_no_pi": 0.08,
         "contrast_fraction_of_passive": 0.82},
        {"feedback_relax_us": 200.0, "status": "ok", "P_e_no_pi": 0.06,
         "contrast_fraction_of_passive": 0.91},
    ]

    selected = diagnostic.choose_shortest_usable(
        rows, min_contrast_fraction=0.80, max_p_e_no_pi=0.15
    )

    assert selected["feedback_relax_us"] == 100.0
