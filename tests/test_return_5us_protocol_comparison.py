"""Hardware-free checks for the q3 5-us, 3pt-vs-5pt comparison."""

import csv
import importlib
import json

import numpy as np
import pytest


MODULE = (
    "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners."
    "ReturnFiveUsProtocolComparison"
)


def comparison():
    return importlib.import_module(MODULE)


def test_plan_uses_separate_matched_reference_acquisitions(capsys):
    assert comparison().main(["--plan"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["hardware_access"] is False
    assert [arm["name"] for arm in plan["arms"]] == ["three_point_100us", "five_point_25_60_100us"]
    assert [arm["delays_us"] for arm in plan["arms"]] == [[100.0], [25.0, 60.0, 100.0]]
    assert all(arm["reference_hold_us"] == 2.0 for arm in plan["arms"])
    assert plan["return_to_readout_us"] == 5.0
    assert plan["shots_per_condition"] == 300


def test_only_survival_conditions_differ_between_protocols():
    module = comparison()
    base = {"readout_thermalization_us": 10.0, "reset_mode": "active"}
    three, five = module.protocol_arms()
    assert module.arm_config(base, three) == module.arm_config(base, five)
    config = module.arm_config(base, three)
    assert config["flux_predistortion_recovery_us"] == 5.0
    assert config["flux_predistortion_return_prefix_us"] == 5.0
    assert config["flux_predistortion_overlap_payload_readout"] is False
    assert config["flux_predistortion_round_trip_mode"] == "stateful"
    assert config["qua_shot_order"] is True


def test_one_delay_matched_reference_estimator_is_valid():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.five_point_t1 import (
        estimate_matched_t1,
    )

    p0, p1, t1_us = 0.05, 0.70, 80.0
    ps_100 = p0 + (p1 - p0) * np.exp(-100.0 / t1_us)
    result = estimate_matched_t1(
        [p0], [p1], [[ps_100]], [100.0],
        shots_per_condition=300, max_relative_error=0.5,
    )
    assert result["valid_mask"][0] == 1
    assert result["T1_us"][0] == pytest.approx(t1_us, rel=0.02)


def test_hardware_run_requires_stopped_scan_confirmation():
    with pytest.raises(RuntimeError, match="current QICK scan has stopped"):
        comparison().run(correction_json="not-a-real-file.json")


def test_curve_is_gated_by_success_and_validity_and_saved_incrementally(tmp_path):
    module = comparison()
    path = tmp_path / "three.csv"
    module.write_arm_curve(
        path,
        frequencies_ghz=np.array([3.9, 3.901, 3.902]),
        data={
            "P0": np.array([0.1, 0.1, 0.1]),
            "P1": np.array([0.7, 0.7, 0.7]),
            "inv_T1_3pt_per_us": np.array([0.01, 0.02, 0.03]),
            "T1_3pt_valid_mask": np.array([1, 0, 1]),
            "T1_3pt_fit_success": np.array([1, 1, 0]),
        },
        point_count=3,
    )
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 3
    assert float(rows[0]["gamma_per_us"]) == pytest.approx(0.01)
    assert rows[1]["gamma_per_us"] == ""
    assert rows[2]["gamma_per_us"] == ""
    assert float(rows[0]["contrast"]) == pytest.approx(0.6)


def test_comparison_plot_uses_saved_curves(tmp_path):
    module = comparison()
    arms = module.protocol_arms()
    manifest = {"arms": []}
    for arm, scale in zip(arms, (1.0, 1.2)):
        path = tmp_path / f"{arm.name}.csv"
        module.write_arm_curve(
            path,
            frequencies_ghz=np.array([3.9, 3.901]),
            data={
                "P0": np.array([0.1, 0.1]),
                "P1": np.array([0.7, 0.7]),
                f"inv_T1_{arm.point_count}pt_per_us": np.array([0.01, 0.02]) * scale,
                f"T1_{arm.point_count}pt_valid_mask": np.array([1, 1]),
                f"T1_{arm.point_count}pt_fit_success": np.array([1, 1]),
            },
            point_count=arm.point_count,
        )
        manifest["arms"].append({"name": arm.name, "status": "complete", "curve_csv": str(path)})
    png = module.plot_completed_curves(tmp_path, manifest)
    assert png.is_file() and png.stat().st_size > 0
