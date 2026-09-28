"""Contracts for the within-shot 1.5/6-us q3 swap-loss confirmation."""

import importlib

import pytest


MODULE = "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSwapHoldConfirm"


def experiment():
    return importlib.import_module(MODULE)


def test_each_program_has_both_dwell_times_and_preparations():
    module = experiment()
    specs = module.program_specs(4.127, 4.113)
    assert [item["name"] for item in specs] == [
        "r0_feature", "r0_control", "r1_control", "r1_feature"]
    assert [(c["hold_us"], c["state"]) for c in specs[0]["conditions"]] == [
        (1.5, "g"), (1.5, "e"), (6.0, "g"), (6.0, "e")]
    assert [c["name"] for c in specs[-1]["conditions"]] == [
        "late_e", "late_g", "early_e", "early_g"]
    assert all(item["shots"] == 3000 for item in specs)


def test_primary_effect_is_extra_late_loss_at_feature():
    module = experiment()
    feature = module.score({"early_g": .1, "early_e": .7,
                            "late_g": .1, "late_e": .4})
    control = module.score({"early_g": .1, "early_e": .7,
                            "late_g": .1, "late_e": .6})
    assert feature["drop"] == pytest.approx(.3)
    assert control["drop"] == pytest.approx(.1)
    assert module.effect(feature, control) == pytest.approx(.2)


def test_four_way_stream_split_preserves_same_shot_pairing():
    module = experiment()
    order = ["early_g", "early_e", "late_g", "late_e"]
    assert module.split_records(list(range(12)), order, shots=3) == {
        "early_g": [0, 4, 8], "early_e": [1, 5, 9],
        "late_g": [2, 6, 10], "late_e": [3, 7, 11]}
    with pytest.raises(ValueError, match="incomplete"):
        module.split_records(list(range(11)), order, shots=3)


def test_plan_tracks_only_lower_feature_and_predeclared_dwell_pair():
    plan = experiment().plan()
    assert plan["feature_anchor_ghz"] == 4.127
    assert plan["dwells_us"] == [1.5, 6.0]
    assert plan["conditions_per_shot"] == 4
    assert plan["programs"] == 4
    assert plan["shots_per_program"] == 3000
