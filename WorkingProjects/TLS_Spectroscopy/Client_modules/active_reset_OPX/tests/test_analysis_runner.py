import csv
from dataclasses import replace
import ast
import math
from pathlib import Path

import numpy as np
import pytest

from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.analysis import (
    ReferenceAxis,
    append_records_csv,
    build_interleaved_schedule,
    summarize_post_readout_pi,
    summarize_records,
    wilson_interval,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.calibration import (
    CalibrationBundle,
    load_calibration,
    save_calibration,
    validate_confident_calibration,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.classifier import (
    ClassifierCalibration,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.records import (
    ShotRecord,
    TerminalStatus,
)


CAL = ClassifierCalibration(
    schema_version=1,
    context="payload",
    theta_rad=0.0,
    shift=0,
    c_int=1,
    s_int=0,
    ground_threshold=-10,
    excited_threshold=10,
    max_abs_raw=100,
    holdout={"ground_median": -100, "excited_median": 100},
)


def test_reference_axis_recovers_mixture_population_from_mean_iq():
    axis = ReferenceAxis.from_centers(10, -5, 110, 45)
    i = np.asarray([10, 110, 110, 10], dtype=float)
    q = np.asarray([-5, 45, 45, -5], dtype=float)

    assert axis.population(i, q) == pytest.approx([0, 1, 1, 0])
    assert axis.mean_population(i, q) == pytest.approx(0.5)


def test_wilson_interval_contains_observed_fraction_and_handles_zero_shots():
    low, high = wilson_interval(10, 100)
    assert low < 0.1 < high
    assert all(math.isnan(value) for value in wilson_interval(0, 0))


def test_summary_includes_timeouts_in_unconditional_residual():
    axis = ReferenceAxis.from_centers(0, 0, 100, 0)
    records = [
        ShotRecord(1, 100, 1, 1, TerminalStatus.CONFIRMED_GROUND, 0, 0, -100),
        ShotRecord(1, 100, 8, 8, TerminalStatus.MAX_ITERATIONS_REACHED, 100, 0, 100),
    ]

    summary = summarize_records(records, axis, CAL)

    assert summary["shots"] == 2
    assert summary["timeout_fraction"] == 0.5
    assert summary["verification_excited_fraction"] == 0.5
    assert summary["verification_population"] == pytest.approx(0.5)


def test_calibration_bundle_round_trips_through_json(tmp_path):
    bundle = CalibrationBundle(
        schema_version=1,
        payload=CAL,
        loop=CAL,
        reference_axis=ReferenceAxis.from_centers(0, 1, 10, 11),
        metadata={"qick_version": "0.2.133", "qubit": "q3"},
    )
    path = tmp_path / "calibration.json"

    save_calibration(path, bundle)

    assert load_calibration(path) == bundle


def test_loading_missing_calibration_fails_closed(tmp_path):
    with pytest.raises(FileNotFoundError, match="calibration"):
        load_calibration(tmp_path / "missing.json")


def test_calibration_rejects_a_loop_classifier_with_no_confident_states():
    payload = replace(CAL, holdout={"ground_accept": 0.4, "excited_fire": 0.5})
    loop = replace(
        CAL,
        context="loop",
        holdout={"ground_accept": 0.07, "excited_fire": 0.03},
    )
    bundle = CalibrationBundle(
        schema_version=1,
        payload=payload,
        loop=loop,
        reference_axis=ReferenceAxis.from_centers(0, 0, 100, 0),
        metadata={},
    )

    with pytest.raises(ValueError, match="confident.*loop"):
        validate_confident_calibration(bundle, min_confident_fraction=0.2)


def test_incremental_csv_has_one_row_per_shot_and_preserves_method(tmp_path):
    axis = ReferenceAxis.from_centers(0, 0, 100, 0)
    records = [
        ShotRecord(0, -100, 0, 0, TerminalStatus.CONFIRMED_GROUND, 0, 0, -100),
        ShotRecord(0, -100, 1, 0, TerminalStatus.CONFIRMED_GROUND, 0, 0, -100),
    ]
    path = tmp_path / "shots.csv"

    append_records_csv(path, records, axis=axis, assignment=CAL, method="opx", block=3)
    append_records_csv(path, records[:1], axis=axis, assignment=CAL, method="none", block=4)

    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 3
    assert [row["method"] for row in rows] == ["opx", "opx", "none"]
    assert [int(row["block"]) for row in rows] == [3, 3, 4]


def test_interleaved_schedule_contains_every_condition_once_per_block():
    schedule = build_interleaved_schedule(
        methods=("none", "opx", "current"), blocks=3, seed=7
    )

    assert len(schedule) == 18
    for block in range(3):
        conditions = {(method, preparation) for b, method, preparation in schedule if b == block}
        assert conditions == {
            (method, preparation)
            for method in ("none", "opx", "current")
            for preparation in (0, 1)
        }


def test_post_readout_pi_summary_selects_the_earliest_working_delay():
    summary = summarize_post_readout_pi(
        pre_pi_delay_us=[2.0, 4.0, 10.0],
        read_delay_us=2.0,
        first_ground_population=[0.02, 0.01, 0.00],
        first_pi_population=[0.03, 0.02, 0.01],
        second_ground_population=[0.05, 0.04, 0.03],
        second_pi_population=[0.20, 0.72, 0.90],
        min_transfer_contrast=0.5,
        max_first_preparation_delta=0.2,
        min_second_pi_population=0.5,
        max_abs_second_ground_population=0.3,
    )

    assert summary["selected_pre_pi_delay_us"] == pytest.approx(4.0)
    assert [row["pre_pi_delay_us"] for row in summary["rows"]] == [2.0, 4.0, 10.0]
    assert [row["passed"] for row in summary["rows"]] == [False, True, True]


def test_post_readout_pi_summary_rejects_delay_shorter_than_read_wait():
    with pytest.raises(ValueError, match="at least the read delay"):
        summarize_post_readout_pi(
            pre_pi_delay_us=[1.0, 2.0],
            read_delay_us=2.0,
            first_ground_population=[0.0, 0.0],
            first_pi_population=[0.0, 0.0],
            second_ground_population=[0.0, 0.0],
            second_pi_population=[0.0, 1.0],
            min_transfer_contrast=0.5,
            max_first_preparation_delta=0.2,
            min_second_pi_population=0.5,
            max_abs_second_ground_population=0.3,
        )


def test_q3_benchmark_uses_measured_post_readout_pi_plateau():
    runner = Path(__file__).parents[1] / "benchmark_q3.py"
    tree = ast.parse(runner.read_text())
    assignments = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "OPX_OVERRIDES"
    }

    assert assignments["OPX_OVERRIDES"]["opx_feedback_syncdelay_us"] == 8.0
