"""A moving lower-band dip can be retargeted without chasing noise."""

import pytest

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSSwapHoldConfirm as confirm,
)


def scout_with_lower_dip(center=None):
    rows = []
    for index in range(81):
        frequency = round(4.090 + index * 0.001, 3)
        survival = 0.8
        if center is not None and abs(frequency - center) <= 0.00101:
            survival = 0.32
        row = {"target_frequency_ghz": str(frequency)}
        for suffix in ("", "_scan_up", "_scan_down"):
            row["P0" + suffix] = "0.10"
            row["P1" + suffix] = "0.70"
            row["Ps_25us" + suffix] = str(0.10 + 0.60 * survival)
        rows.append(row)
    return rows


def test_wide_lower_selector_follows_a_shifted_dip_and_clean_control():
    selected = confirm.select_moving_lower_dip(scout_with_lower_dip(4.120))
    assert selected["center_ghz"] == 4.120
    assert selected["control_ghz"] == 4.106
    assert selected["depth"] >= 0.15
    assert min(selected["control_survival_advantage"].values()) >= 0.15


def test_wide_lower_selector_refuses_a_flat_scan():
    with pytest.raises(ValueError, match="no qualified moving lower-band dip"):
        confirm.select_moving_lower_dip(scout_with_lower_dip())


def test_follow_moving_plan_preserves_original_four_program_comparison():
    plan = confirm.plan(follow_moving_dip=True)
    assert plan["feature_search_ghz"] == [4.116, 4.134]
    assert plan["dwells_us"] == [1.5, 6.0]
    assert plan["programs"] == 4
    assert plan["shots_per_program"] == 3000
