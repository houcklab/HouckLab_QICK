from dataclasses import replace
import csv
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    protocol_selection_benchmark as benchmark,
)


def test_full_plan_is_the_approved_17_pass_matrix():
    plan = benchmark.full_plan()
    assert len(plan.passes) == 17
    assert [item.pass_id for item in plan.passes] == [
        "p00_3pt_ts100_300_off",
        "p01_3pt_ts100_300_on",
        "p02_3pt_ts100_500_on",
        "p03_3pt_ts100_500_off",
        "p04_3pt_ts50_300_off",
        "p05_3pt_ts50_300_on",
        "p06_3pt_ts50_500_on",
        "p07_3pt_ts50_500_off",
        "p08_5pt_180_off",
        "p09_5pt_180_on",
        "p10_5pt_300_on",
        "p11_5pt_300_off",
        "p12_7pt_128_off",
        "p13_7pt_128_on",
        "p14_7pt_214_on",
        "p15_7pt_214_off",
        "p16_3pt_ts100_300_off_sentinel",
    ]
    assert plan.passes[0].role == "primary_and_anchor"
    assert plan.passes[-1].role == "drift_sentinel"


def test_equal_budget_pairs_are_encoded_exactly():
    plan = benchmark.full_plan()
    totals = [p.condition_count * p.shots_per_condition for p in plan.passes[:16]]
    assert totals == [
        900,
        900,
        1500,
        1500,
        900,
        900,
        1500,
        1500,
        900,
        900,
        1500,
        1500,
        896,
        896,
        1498,
        1498,
    ]


def test_full_plan_grid_and_fingerprint_are_fixed():
    plan = benchmark.full_plan()
    grid = benchmark.frequency_grid_ghz(plan)
    assert grid.shape == (801,)
    assert grid[0] == 4.3
    assert grid[-1] == 3.9
    assert benchmark.plan_fingerprint(plan) == (
        "9102ce376f93ef790f43fbafb7e7c9ae25ea8cdb56e7785424b53267e10746bb"
    )


def test_plan_has_no_synchronization_fields():
    encoded = benchmark.canonical_json(benchmark.full_plan())
    assert "sync" not in encoded.lower()
    assert "handshake" not in encoded.lower()


def test_smoke_plan_exercises_every_protocol_and_mode_without_matching_full_hash():
    smoke = benchmark.smoke_plan()
    assert [(p.protocol, p.predistortion) for p in smoke.passes] == [
        ("3pt_ts100", "off"),
        ("3pt_ts100", "on"),
        ("5pt", "off"),
        ("5pt", "on"),
        ("7pt", "off"),
        ("7pt", "on"),
    ]
    assert smoke.frequency_count == 11
    assert all(p.shots_per_condition == 4 for p in smoke.passes)
    assert benchmark.plan_fingerprint(smoke) != benchmark.plan_fingerprint(
        benchmark.full_plan()
    )


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        (
            {"protocol": "unknown"},
            "unknown benchmark protocol",
        ),
        (
            {"delays_us": (100.0, 50.0), "condition_count": 4},
            "canonical definition",
        ),
        (
            {"index": 2},
            "indices must be sequential",
        ),
        (
            {"predistortion": "invalid"},
            "predistortion",
        ),
        (
            {"condition_count": 99},
            "condition count",
        ),
    ],
)
def test_canonical_document_rejects_invalid_pass_contract(replacement, message):
    valid = benchmark.full_plan()
    original = valid.passes[1]
    invalid_pass = benchmark.BenchmarkPass(
        index=replacement.get("index", original.index),
        protocol=replacement.get("protocol", original.protocol),
        delays_us=replacement.get("delays_us", original.delays_us),
        shots_per_condition=replacement.get(
            "shots_per_condition", original.shots_per_condition
        ),
        condition_count=replacement.get("condition_count", original.condition_count),
        predistortion=replacement.get("predistortion", original.predistortion),
        role=original.role,
    )
    invalid_plan = benchmark.BenchmarkPlan(
        **{**valid.__dict__, "passes": (valid.passes[0], invalid_pass, *valid.passes[2:])}
    )

    with pytest.raises(ValueError, match=message):
        benchmark.canonical_document(invalid_plan)


def test_canonical_document_rejects_frequency_count_that_does_not_match_grid():
    valid = benchmark.full_plan()
    invalid_plan = benchmark.BenchmarkPlan(
        **{**valid.__dict__, "frequency_count": 800}
    )

    with pytest.raises(ValueError, match="frequency count"):
        benchmark.canonical_document(invalid_plan)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("index", 1.5, "integer"),
        ("index", True, "integer"),
        ("shots_per_condition", 1.5, "integer"),
        ("shots_per_condition", float("nan"), "integer"),
        ("shots_per_condition", True, "integer"),
        ("condition_count", 3.0, "integer"),
        ("condition_count", True, "integer"),
        ("delays_us", (float("nan"),), "finite"),
    ],
)
def test_canonical_document_rejects_invalid_pass_numbers(field, value, message):
    plan = benchmark.full_plan()
    invalid_pass = replace(plan.passes[1], **{field: value})
    invalid_plan = replace(
        plan, passes=(plan.passes[0], invalid_pass, *plan.passes[2:])
    )

    with pytest.raises(ValueError, match=message):
        benchmark.canonical_document(invalid_plan)


@pytest.mark.parametrize("value", [801.0, True])
def test_canonical_document_rejects_non_integer_frequency_count(value):
    invalid_plan = replace(benchmark.full_plan(), frequency_count=value)

    with pytest.raises(ValueError, match="frequency count must be a positive integer"):
        benchmark.canonical_document(invalid_plan)


def fake_five_point_data(points):
    frequency_index = np.arange(points, dtype=float)
    p0 = 0.10 + frequency_index * 0.0001
    p1 = 0.90 - frequency_index * 0.0001
    gamma = 0.010 + frequency_index * 0.00001
    return {
        "P0": p0,
        "P1": p1,
        "Ps_40us": 0.70 - frequency_index * 0.0001,
        "Ps_80us": 0.50 - frequency_index * 0.0001,
        "Ps_200us": 0.25 - frequency_index * 0.0001,
        "P0_scan_up": p0 + 0.001,
        "P0_scan_down": p0 - 0.001,
        "inv_T1_5pt_per_us": gamma,
        "inv_T1_5pt_err_per_us": np.full(points, 0.0002),
        "T1_5pt_us": 1.0 / gamma,
        "T1_5pt_err_us": np.full(points, 2.0),
        "ref_contrast_5pt": p1 - p0,
        "T1_5pt_valid_mask": np.ones(points, dtype=bool),
        "T1_5pt_fit_success": np.ones(points, dtype=bool),
        "T1_5pt_fit_deviance": np.full(points, 0.01),
        "inv_T1_5pt_per_us_scan_up": gamma + 0.0005,
        "inv_T1_5pt_per_us_scan_down": gamma - 0.0005,
        "inv_T1_5pt_per_us_scan_direction_delta": np.full(points, 0.001),
    }


def synthetic_rows(
    *, valid_fraction=1.0, direction_offset=0.0, gamma_offset=0.0,
    gamma_error=0.001,
):
    rows = []
    for index in range(20):
        valid = index < int(20 * valid_fraction)
        rows.append({
            "pass_index": 0,
            "pass_id": "p00_3pt_ts100_300_off",
            "protocol": "3pt_ts100",
            "predistortion": "off",
            "shots_per_condition": 300,
            "condition_count": 3,
            "target_frequency_ghz": 4.3 - index * 0.0005,
            "realized_frequency_ghz": 4.3 - index * 0.0005,
            "flux_coordinate": index,
            "gamma1_per_us": 0.010 + gamma_offset if valid else np.nan,
            "gamma1_err_per_us": gamma_error,
            "t1_us": 100.0,
            "t1_err_us": 1.0,
            "valid": valid,
            "reference_contrast": 0.8,
            "fit_success": valid,
            "fit_deviance": 0.01,
            "scan_direction_delta": direction_offset,
            "P0": 0.1,
            "P1": 0.9,
            "Ps": 0.5,
        })
    return rows


def test_pass_is_complete_only_after_both_artifacts_and_checksums_exist(tmp_path):
    plan = benchmark.smoke_plan()
    manifest_path = tmp_path / "q3_smoke_manifest.json"
    manifest = benchmark.new_manifest(
        plan, device="q3", controller="qick", code_commit="abc123",
        model_provenance={"sha256": "1" * 64}, calibration_id="cal-1",
    )
    benchmark.atomic_write_json(manifest_path, manifest)
    raw_path, metadata_path = benchmark.artifact_paths(
        tmp_path, "q3_smoke", plan.passes[0]
    )
    with pytest.raises(FileNotFoundError, match="artifacts"):
        benchmark.record_pass_complete(
            manifest_path, 0, raw_path=raw_path, metadata_path=metadata_path,
            ended_at="2026-09-16T12:00:00-04:00", duration_s=1.2,
        )
    raw_path.write_text("frequency_ghz,gamma1_per_us\n4.05,0.01\n")
    metadata_path.write_text("{}")
    completed = benchmark.record_pass_complete(
        manifest_path, 0, raw_path=raw_path, metadata_path=metadata_path,
        ended_at="2026-09-16T12:00:00-04:00", duration_s=1.2,
    )
    assert completed["passes"][0]["status"] == "complete"
    assert completed["passes"][0]["artifacts"]["raw_csv"]["sha256"]
    assert benchmark.pending_passes(completed, plan) == plan.passes[1:]


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"plan": benchmark.full_plan()}, "plan"),
        ({"device": "q5"}, "device"),
        ({"controller": "qua"}, "controller"),
        ({"model_sha256": "2" * 64}, "model"),
        ({"calibration_id": "cal-2"}, "calibration"),
    ],
)
def test_resume_refuses_provenance_mismatches(tmp_path, override, message):
    plan = benchmark.smoke_plan()
    path = tmp_path / "manifest.json"
    benchmark.atomic_write_json(path, benchmark.new_manifest(
        plan, device="q3", controller="qick", code_commit="abc123",
        model_provenance={"sha256": "1" * 64}, calibration_id="cal-1",
    ))
    arguments = {
        "plan": plan,
        "device": "q3",
        "controller": "qick",
        "model_sha256": "1" * 64,
        "calibration_id": "cal-1",
    }
    arguments.update(override)
    with pytest.raises(ValueError, match=message):
        benchmark.load_resume_manifest(path, **arguments)


def test_resume_rechecks_both_completed_artifact_checksums(tmp_path):
    plan = benchmark.smoke_plan()
    path = tmp_path / "manifest.json"
    benchmark.atomic_write_json(path, benchmark.new_manifest(
        plan, device="q3", controller="qick", code_commit="abc",
        model_provenance={"sha256": "1" * 64}, calibration_id="cal-1",
    ))
    raw_path, metadata_path = benchmark.artifact_paths(tmp_path, "q3", plan.passes[0])
    raw_path.write_text("raw version one")
    metadata_path.write_text('{"metadata": 1}')
    benchmark.record_pass_complete(
        path, 0, raw_path=raw_path, metadata_path=metadata_path,
        ended_at="2026-09-16T12:00:00-04:00", duration_s=1.2,
    )
    metadata_path.write_text('{"metadata": 2}')
    with pytest.raises(ValueError, match="checksum"):
        benchmark.load_resume_manifest(
            path, plan, device="q3", controller="qick",
            model_sha256="1" * 64, calibration_id="cal-1",
        )


def test_failed_pass_is_recorded_but_remains_pending(tmp_path):
    plan = benchmark.smoke_plan()
    path = tmp_path / "manifest.json"
    benchmark.atomic_write_json(path, benchmark.new_manifest(
        plan, device="q3", controller="qick", code_commit="abc",
        model_provenance={"sha256": "1" * 64}, calibration_id="cal-1",
    ))
    failed = benchmark.record_pass_failed(
        path, 0, error_type="RuntimeError", error_message="hardware stopped",
        traceback_text="trace", failed_at="2026-09-16T12:00:00-04:00",
    )
    assert failed["passes"][0]["status"] == "failed"
    assert benchmark.pending_passes(failed, plan)[0].index == 0


def test_normalization_preserves_raw_populations_and_directional_diagnostics():
    spec = benchmark.full_plan().passes[8]
    data = fake_five_point_data(points=801)
    rows = benchmark.normalize_experiment_data(
        spec,
        data,
        target_frequency_ghz=np.linspace(4.3, 3.9, 801),
        realized_frequency_ghz=np.linspace(4.3, 3.9, 801),
        flux_coordinate=np.arange(801),
    )
    assert len(rows) == 801
    assert {"P0", "P1", "Ps_40us", "Ps_80us", "Ps_200us", "P0_scan_up"} <= rows[0].keys()
    assert {"gamma1_per_us", "gamma1_err_per_us", "valid", "fit_deviance", "scan_direction_delta"} <= rows[0].keys()
    assert rows[0]["gamma1_per_us"] == pytest.approx(0.01)
    assert rows[0]["scan_direction_delta"] == pytest.approx(0.001)


def test_summary_flags_nan_region_direction_shift_and_linewidth_shift():
    clean = synthetic_rows(valid_fraction=1.0, direction_offset=0.0)
    corrupt = synthetic_rows(valid_fraction=0.95, direction_offset=0.02)
    clean_metrics = benchmark.summarize_pass(clean)
    corrupt_metrics = benchmark.summarize_pass(corrupt)
    assert clean_metrics["valid_fraction"] == pytest.approx(1.0)
    assert corrupt_metrics["valid_fraction"] < 0.99
    assert corrupt_metrics["median_abs_direction_delta"] > clean_metrics[
        "median_abs_direction_delta"
    ]
    assert corrupt_metrics["longest_invalid_run"] == 1


def test_opening_and_closing_sentinels_report_drift_in_sigma_units():
    opening = synthetic_rows(gamma_offset=0.0, gamma_error=0.001)
    closing = synthetic_rows(gamma_offset=0.004, gamma_error=0.001)
    result = benchmark.compare_sentinels(opening, closing)
    assert result["median_abs_delta_per_us"] == pytest.approx(0.004)
    assert result["median_abs_delta_sigma"] > 2.0


def test_csv_summary_and_linecut_figure_artifacts_are_written(tmp_path):
    rows = synthetic_rows()
    raw_path = tmp_path / "pass_raw.csv"
    summary_path = tmp_path / "summary.csv"
    figure_path = tmp_path / "comparison.png"
    assert benchmark.write_pass_csv(raw_path, rows) == raw_path
    assert benchmark.write_summary_csv(summary_path, [benchmark.summarize_pass(rows)]) == summary_path
    with raw_path.open(newline="") as stream:
        written = list(csv.DictReader(stream))
    assert written[0]["gamma1_per_us"] == "0.01"
    assert "median_local_roughness" in summary_path.read_text()

    primary = {index: [dict(row, pass_index=index, pass_id=f"p{index:02d}") for row in rows] for index in range(16)}
    session = {"passes": [{"index": index, "rows": pass_rows} for index, pass_rows in primary.items()]}
    session["passes"].append({"index": 16, "rows": synthetic_rows(gamma_offset=0.002)})
    metadata = benchmark.render_comparison_figure(session, figure_path)
    assert figure_path.exists() and figure_path.stat().st_size > 2_000
    assert metadata["primary_map_panels"] == 16
    assert metadata["sentinel_panels"] >= 1
