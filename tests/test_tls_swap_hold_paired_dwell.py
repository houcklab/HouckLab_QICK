"""Within-shot dwell pairs track the loss feature's time dependence."""

import pytest

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSSwapHoldConfirm as confirm,
)


def test_paired_dwell_specs_reverse_time_site_and_subshot_order():
    specs = confirm.paired_dwell_specs(4.110, 4.096)
    assert len(specs) == 40
    assert [item["name"] for item in specs[:2]] == [
        "r0_t0p2_feature", "r0_t0p2_control"]
    assert [item["name"] for item in specs[20:22]] == [
        "r1_t6_control", "r1_t6_feature"]
    assert all(item["shots"] == 800 for item in specs)
    assert [(c["hold_us"], c["state"]) for c in specs[0]["conditions"]] == [
        (0.1, "g"), (0.1, "e"), (0.2, "g"), (0.2, "e")]
    assert [(c["hold_us"], c["state"]) for c in specs[20]["conditions"]] == [
        (6.0, "e"), (6.0, "g"), (0.1, "e"), (0.1, "g")]
    assert specs[0]["conditions"][0] is not specs[2]["conditions"][0]


def test_paired_dwell_report_subtracts_control_loss_at_each_time():
    specs = confirm.paired_dwell_specs(4.110, 4.096)
    scores = {item["name"]: {"drop": 0.02, "usable": True,
                             "early_contrast": 0.6,
                             "late_contrast": 0.58} for item in specs}
    scores["r0_t6_feature"]["drop"] = 0.18
    scores["r0_t6_control"]["drop"] = 0.03
    report = confirm.paired_dwell_report(specs, scores)
    assert report["r0"][-1]["hold_us"] == 6.0
    assert report["r0"][-1]["excess_drop"] == pytest.approx(0.15)
    assert report["r1"][0]["hold_us"] == 0.2


def test_paired_preflight_covers_short_and_long_holds_both_orders():
    specs = confirm.paired_dwell_specs(4.110, 4.096)
    sampled = confirm.preflight_entries(specs, paired_dwell_scan=True)
    assert [item["name"] for item in sampled] == [
        "r0_t0p2_feature", "r0_t0p2_control",
        "r0_t6_feature", "r0_t6_control",
        "r1_t6_control", "r1_t6_feature",
        "r1_t0p2_control", "r1_t0p2_feature"]


def test_paired_dwell_plan_is_passive_and_uses_fresh_moving_selector():
    plan = confirm.plan(paired_dwell_scan=True)
    assert plan["feature_search_ghz"] == [4.105, 4.134]
    assert plan["reference_hold_us"] == 0.1
    assert plan["programs"] == 40
    assert plan["shots_per_program"] == 800
