"""Contracts for a short-time q3 loss-feature exchange probe."""

import importlib

import pytest


MODULE = "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSwapHoldPilot"


def experiment():
    return importlib.import_module(MODULE)


def scout_rows(*, high_control=0.8, upper_feature=True,
               low_control=0.8):
    rows = []
    for index in range(81):
        frequency = round(4.090 + index * 0.001, 3)
        survival = 0.8
        if frequency in (4.128, 4.130):
            survival = 0.35
        if frequency == 4.129:
            survival = 0.25
        if upper_feature and frequency in (4.143, 4.145):
            survival = 0.48
        if upper_feature and frequency == 4.144:
            survival = 0.4
        if frequency in (4.157, 4.158, 4.159):
            survival = high_control
        if frequency in (4.114, 4.115, 4.116):
            survival = low_control
        row = {"target_frequency_ghz": f"{frequency:.3f}"}
        for suffix in ("", "_scan_up", "_scan_down"):
            row["P0" + suffix] = "0.1"
            row["P1" + suffix] = "0.9"
            row["Ps_25us" + suffix] = str(0.1 + 0.8 * survival)
        rows.append(row)
    return rows


def test_anchor_keeps_upper_feature_when_lower_feature_is_deeper():
    selected = experiment().select_anchored_feature(scout_rows())
    assert selected["center_ghz"] == 4.144
    assert selected["control_ghz"] == 4.158
    assert selected["depth"] > 0.15


def test_anchor_rejects_control_that_is_itself_lossy():
    with pytest.raises(ValueError, match="control"):
        experiment().select_anchored_feature(scout_rows(high_control=0.44))


def test_falls_back_to_lower_feature_when_upper_dip_disappears():
    selected = experiment().select_anchored_feature(
        scout_rows(upper_feature=False))
    assert selected["center_ghz"] == 4.129
    assert selected["control_ghz"] == 4.115
    assert selected["anchor_ghz"] == 4.127


def test_post_scout_keeps_lower_family_if_upper_dip_reappears():
    selected = experiment().select_anchored_feature(
        scout_rows(), preferred_center=4.127)
    assert selected["center_ghz"] == 4.129
    assert selected["control_ghz"] == 4.115


def test_fallback_rejects_lossy_lower_control():
    with pytest.raises(ValueError, match="control"):
        experiment().select_anchored_feature(
            scout_rows(upper_feature=False, low_control=0.3))


def test_specs_bracket_each_dwell_with_ground_excited_and_reverse_order():
    specs = experiment().program_specs(4.144, 4.158)
    assert len(specs) == 88
    assert [(x["site"], x["hold_us"], x["state"]) for x in specs[:4]] == [
        ("feature", 0.1, "g"), ("feature", 0.1, "e"),
        ("control", 0.1, "g"), ("control", 0.1, "e")]
    assert [(x["site"], x["hold_us"], x["state"]) for x in specs[-4:]] == [
        ("control", 0.1, "e"), ("control", 0.1, "g"),
        ("feature", 0.1, "e"), ("feature", 0.1, "g")]
    assert all(x["shots"] == 600 for x in specs)


def test_short_hold_uses_full_corrected_return_without_microwave_window():
    module = experiment()
    correction = {"segment_edges_ns": [0.0, 500.0, 40_000.0],
                  "multipliers": [1.02, 1.01, 1.0]}
    target, recovery = module.swap_segments(correction, hold_us=0.1)
    assert sum(duration for _, duration in target) == pytest.approx(0.1)
    assert sum(duration for _, duration in recovery) == pytest.approx(40.0)


def test_post_scout_tracks_same_upper_feature_not_whichever_dip_is_deepest():
    module = experiment()
    pre = module.select_anchored_feature(scout_rows())
    post = module.select_anchored_feature(scout_rows())
    assert module.feature_stable(pre, post)


def wide_scout_rows(*, other_feature=True, poor_control=False):
    rows = []
    for index in range(251):
        frequency = round(3.800 + .002 * index, 3)
        survival = .8
        if frequency in (4.100, 4.102, 4.104):
            survival = .2  # The already tested feature is excluded.
        if other_feature and frequency in (4.046, 4.050):
            survival = .5
        if other_feature and frequency == 4.048:
            survival = .2
        if poor_control and frequency in (4.060, 4.062, 4.064):
            survival = .38
        row = {"target_frequency_ghz": f"{frequency:.3f}"}
        for suffix in ("", "_scan_up", "_scan_down"):
            row["P0" + suffix] = ".1"
            row["P1" + suffix] = ".9"
            row["Ps_25us" + suffix] = str(.1 + .8 * survival)
        rows.append(row)
    return rows


def test_wide_selector_finds_new_isolated_candidate_with_clean_control():
    selected = experiment().select_wide_candidate(wide_scout_rows())
    assert selected["center_ghz"] == 4.048
    assert selected["control_ghz"] == 4.062
    assert selected["depth"] >= .15


def test_wide_selector_rejects_known_band_and_missing_candidate():
    with pytest.raises(ValueError, match="outside"):
        experiment().select_wide_candidate(wide_scout_rows(other_feature=False))


def test_wide_selector_tracks_same_candidate_in_post_scout():
    module = experiment()
    selected = module.select_wide_candidate(wide_scout_rows())
    post = module.select_wide_candidate(wide_scout_rows(),
                                        preferred_center=selected["center_ghz"])
    assert module.feature_stable(selected, post)


def test_wide_post_selector_accepts_same_dip_split_across_adjacent_bins():
    module = experiment()
    pre = module.select_wide_candidate(wide_scout_rows())
    rows = wide_scout_rows()
    for row in rows:
        f = float(row["target_frequency_ghz"])
        if f == 4.046:
            survival = .2
        elif f == 4.048:
            survival = .2
        elif f == 4.050:
            survival = .5
        else:
            continue
        for suffix in ("", "_scan_up", "_scan_down"):
            row["Ps_25us" + suffix] = str(.1 + .8 * survival)
    post = module.select_wide_candidate(rows,
                                        preferred_center=pre["center_ghz"])
    assert abs(post["center_ghz"] - pre["center_ghz"]) <= .002
    assert module.feature_stable(pre, post)


def test_wide_post_selector_does_not_switch_to_other_control():
    module = experiment()
    pre = module.select_wide_candidate(wide_scout_rows())
    assert pre["control_offset_ghz"] == .014
    with pytest.raises(ValueError, match="qualified"):
        module.select_wide_candidate(
            wide_scout_rows(poor_control=True),
            preferred_center=pre["center_ghz"],
            preferred_control_offset=pre["control_offset_ghz"])


def test_wide_selector_rejects_incomplete_frequency_pass():
    with pytest.raises(ValueError, match="complete"):
        experiment().select_wide_candidate(wide_scout_rows()[:-1])


def test_wide_selector_prefers_sharp_candidate_over_broad_loss_band():
    rows = wide_scout_rows()
    for row in rows:
        f = float(row["target_frequency_ghz"])
        if f in (4.000, 4.002, 4.004, 4.006, 4.008):
            survival = .25
        elif f in (4.046, 4.050):
            survival = .55
        elif f == 4.048:
            survival = .20
        else:
            continue
        for suffix in ("", "_scan_up", "_scan_down"):
            row["Ps_25us" + suffix] = str(.1 + .8 * survival)
    selected = experiment().select_wide_candidate(rows)
    assert selected["center_ghz"] == 4.048


def test_wide_candidate_plan_runs_direct_exchange_trace(capsys):
    import json
    assert experiment().main(["--plan", "--wide-candidate"]) == 0
    description = json.loads(capsys.readouterr().out)
    assert description["wide_candidate"] is True
    assert description["pre_and_post_scout_frequencies"] == 251
    assert description["programs"] == 88
    assert description["reset_mode"] == "passive"
