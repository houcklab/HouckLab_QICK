from dataclasses import replace
from pathlib import Path
import sys

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
