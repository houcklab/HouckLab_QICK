"""Hardware-free contracts for the independent q3 return/readout audit."""

import importlib
import json

import pytest


MODULE = (
    "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners."
    "ReturnReadoutLandingAudit"
)


def audit():
    return importlib.import_module(MODULE)


def test_landing_matrix_brackets_each_repeat_without_a_sync_session():
    arms = audit().landing_arms()
    names = [arm.name for arm in arms]
    assert names[0] == "landing_control_start"
    assert names[-1] == "landing_control_end"
    assert len(names) == len(set(names))
    for repeat in (1, 2, 3):
        for stem in ("recovery_1us", "recovery_5us", "recovery_40us",
                     "continuous_stateful_1us", "continuous_stateful_5us",
                     "continuous_stateful_25us"):
            assert f"{stem}_l{repeat}" in names
        assert any(name.startswith(f"landing_control_l{repeat}_") for name in names)
    assert all(arm.reset_mode == "active" for arm in arms)


def test_q3_timing_arm_config_separates_truncated_from_continuous_return():
    module = audit()
    baseline = {"readout_thermalization_us": 10.0}
    short = module.arm_config(baseline, module.AuditArm("short", 1, 1, False))
    full = module.arm_config(baseline, module.AuditArm("full", 40, 1, True))
    assert short["flux_predistortion_recovery_us"] == 1
    assert short["flux_predistortion_return_prefix_us"] == 1
    assert short["flux_predistortion_overlap_payload_readout"] is False
    assert full["flux_predistortion_recovery_us"] == 40
    assert full["flux_predistortion_return_prefix_us"] == 1
    assert full["flux_predistortion_overlap_payload_readout"] is True
    assert full["diagnostic_iq_summary"] is True


def test_invalid_timing_arm_rejected_before_hardware_access():
    module = audit()
    with pytest.raises(ValueError, match="prefix"):
        module.validate_arm(module.AuditArm("bad", 5, 10, True))


def test_contrast_wait_matrix_stops_each_return_before_readout():
    arms = audit().contrast_wait_arms()
    waits = (2.5, 5.0, 10.0, 20.0, 40.0)
    assert arms[0].name == "contrast_control_start"
    assert arms[-1].name == "contrast_control_end"
    for repeat in (1, 2, 3):
        batch = [arm for arm in arms if arm.name.endswith(f"_r{repeat}")]
        assert tuple(arm.recovery_us for arm in batch) == (
            waits if repeat != 2 else tuple(reversed(waits))
        )
        assert all(arm.prefix_us == arm.recovery_us for arm in batch)
        assert all(arm.overlap_readout is False for arm in batch)
        assert all(arm.reset_mode == "active" for arm in batch)


def test_contrast_csv_summary_uses_recorded_p0_and_p1(tmp_path):
    path = tmp_path / "arm.csv"
    path.write_text(
        "P0,P1,ref_contrast_5pt,T1_5pt_valid_mask,T1_5pt_fit_success\n"
        "0.10,0.70,0.60,1.0,1.0\n"
        "0.20,0.60,0.40,1.0,1.0\n"
        "0.30,0.50,0.20,0.0,0.0\n",
        encoding="utf-8",
    )
    summary = audit().summarize_contrast_csv(path)
    assert summary["frequency_count"] == 3
    assert summary["median_p0"] == pytest.approx(0.20)
    assert summary["median_p1"] == pytest.approx(0.60)
    assert summary["median_p1_minus_p0"] == pytest.approx(0.40)
    assert summary["valid_fit_fraction"] == pytest.approx(2 / 3)


def test_contrast_wait_plan_lists_only_nonoverlap_arms(capsys):
    assert audit().main(["--plan", "--contrast-wait"]) == 0
    plan = json.loads(capsys.readouterr().out)
    arms = plan["arms"]
    assert plan["hardware_access"] is False
    assert len(arms) == 19
    assert all(not arm["overlap_readout"] for arm in arms)
    assert any(arm["recovery_us"] == 2.5 for arm in arms)
    assert any(arm["recovery_us"] == 20.0 for arm in arms)


def test_five_repeat_contrast_plan_has_no_25us_return_controls(capsys):
    assert audit().main([
        "--plan", "--contrast-wait", "--contrast-repeats", "5",
        "--no-contrast-controls",
    ]) == 0
    plan = json.loads(capsys.readouterr().out)
    arms = plan["arms"]
    assert len(arms) == 25
    assert [arm["recovery_us"] for arm in arms] == [
        2.5, 5.0, 10.0, 20.0, 40.0,
        40.0, 20.0, 10.0, 5.0, 2.5,
        2.5, 5.0, 10.0, 20.0, 40.0,
        40.0, 20.0, 10.0, 5.0, 2.5,
        2.5, 5.0, 10.0, 20.0, 40.0,
    ]
    assert all(arm["prefix_us"] == arm["recovery_us"] for arm in arms)
    assert all(not arm["overlap_readout"] for arm in arms)
    assert not any(arm["recovery_us"] == 25.0 for arm in arms)


def test_averaged_outputs_use_run_medians_and_valid_gamma_cells(tmp_path):
    columns = (
        "target_frequency_ghz,P0,P1,T1_5pt_valid_mask,"
        "T1_5pt_fit_success,inv_T1_5pt_per_us\n"
    )
    first = tmp_path / "r1.csv"
    first.write_text(columns +
                     "4.0,0.1,0.7,1,1,0.01\n"
                     "4.1,0.1,0.5,0,0,0.99\n", encoding="utf-8")
    second = tmp_path / "r2.csv"
    second.write_text(columns +
                      "4.0,0.1,0.5,1,1,0.03\n"
                      "4.1,0.1,0.7,1,1,0.04\n", encoding="utf-8")
    manifest = {"arms": [
        {"name": "contrast_stop_5us_r1", "recovery_us": 5.0,
         "status": "complete", "full_csv": str(first),
         "contrast_summary": {"median_p1_minus_p0": 0.5}},
        {"name": "contrast_stop_5us_r2", "recovery_us": 5.0,
         "status": "complete", "full_csv": str(second),
         "contrast_summary": {"median_p1_minus_p0": 0.5}},
    ]}
    outputs = audit().write_averaged_outputs(tmp_path, manifest)
    assert all(path.is_file() for path in outputs.values())
    import csv
    with outputs["contrast_csv"].open(newline="", encoding="utf-8") as stream:
        contrast = list(csv.DictReader(stream))
    with outputs["gamma_csv"].open(newline="", encoding="utf-8") as stream:
        gamma = list(csv.DictReader(stream))
    assert len(contrast) == 1
    assert float(contrast[0]["mean_median_p1_minus_p0"]) == pytest.approx(0.5)
    assert int(contrast[0]["repeat_count"]) == 2
    assert [(float(row["frequency_ghz"]), int(row["repeat_count"]))
            for row in gamma] == [(4.0, 2), (4.1, 1)]
    assert [float(row["mean_gamma_per_us"]) for row in gamma] == pytest.approx(
        [0.02, 0.04]
    )


def test_contrast_outputs_checkpoint_summary_and_png(tmp_path):
    path = tmp_path / "arm.csv"
    path.write_text(
        "P0,P1,ref_contrast_5pt,T1_5pt_valid_mask,T1_5pt_fit_success\n"
        "0.10,0.70,0.60,1.0,1.0\n"
        "0.20,0.60,0.40,1.0,1.0\n",
        encoding="utf-8",
    )
    manifest = {
        "arms": [
            {"name": "contrast_stop_5us_r1", "recovery_us": 5.0,
             "status": "complete", "full_csv": str(path)},
            {"name": "contrast_stop_10us_r1", "recovery_us": 10.0,
             "status": "pending"},
        ]
    }
    csv_path, png_path = audit().write_contrast_outputs(tmp_path, manifest)
    assert png_path.is_file()
    lines = csv_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert "contrast_stop_5us_r1" in lines[1]
    assert "contrast_stop_10us_r1" not in lines[1]
    manifest["arms"][1].update(status="complete", full_csv=str(path))
    next_csv, next_png = audit().write_contrast_outputs(tmp_path, manifest)
    assert next_csv != csv_path
    assert next_png != png_path
    assert csv_path.is_file() and png_path.is_file()
    assert len(next_csv.read_text(encoding="utf-8").splitlines()) == 3
