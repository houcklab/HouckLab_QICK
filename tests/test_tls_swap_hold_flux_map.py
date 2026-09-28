"""The swap-hold flux map brackets both sweep directions with controls."""

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSSwapHoldConfirm as confirm,
)
import pytest


def test_map_grid_covers_drifting_feature_in_both_directions():
    specs = confirm.flux_map_specs(4.125, 4.111)
    assert len(specs) == 38
    assert [x["name"] for x in specs[:2]] == ["r0_control_pre", "r0_f00"]
    assert [x["name"] for x in specs[-2:]] == ["r1_f00", "r1_control_post"]
    assert [x["flux_ghz"] for x in specs[1:18]] == [
        round(4.117 + 0.001 * i, 3) for i in range(17)]
    assert [x["flux_ghz"] for x in specs[20:37]] == [
        round(4.133 - 0.001 * i, 3) for i in range(17)]
    assert all(x["shots"] == 1000 for x in specs)
    assert specs[0]["order"] == ["early_g", "early_e", "late_g", "late_e"]
    assert specs[-1]["order"] == ["late_e", "late_g", "early_e", "early_g"]
    assert specs[0]["conditions"][0] is not specs[1]["conditions"][0]


def test_map_report_subtracts_each_sweeps_bracketing_controls():
    specs = confirm.flux_map_specs(4.125, 4.111)
    scores = {item["name"]: {"drop": 0.02, "usable": True}
              for item in specs}
    scores["r0_control_pre"]["drop"] = 0.01
    scores["r0_control_post"]["drop"] = 0.03
    scores["r1_control_pre"]["drop"] = -0.01
    scores["r1_control_post"]["drop"] = 0.01
    scores["r0_f00"]["drop"] = 0.12
    scores["r1_f00"]["drop"] = 0.12
    report = confirm.flux_map_report(specs, scores)
    assert report["r0"][0]["excess_drop"] == pytest.approx(0.10)
    assert report["r1"][0]["excess_drop"] == pytest.approx(0.12)
    assert report["r0"][0]["flux_ghz"] == 4.117
    assert report["r1"][0]["flux_ghz"] == 4.117
