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


def test_within_shot_time_map_interleaves_feature_and_control():
    module = experiment()
    specs = module.within_shot_time_map_specs(4.103, 4.089)
    assert len(specs) == 10
    assert [x["hold_us"] for x in specs] == [
        3.0, 3.0, 6.0, 6.0, 10.0, 10.0, 16.0, 16.0, 25.0, 25.0]
    assert all(x["shots"] == 600 for x in specs)
    first = specs[0]["conditions"]
    assert len(first) == 8
    assert [x["name"] for x in first] == [
        "feature_early_g", "feature_early_e", "feature_late_g",
        "feature_late_e", "control_early_g", "control_early_e",
        "control_late_g", "control_late_e"]
    assert [x["flux_ghz"] for x in first] == [4.103] * 4 + [4.089] * 4
    assert [x["name"] for x in specs[1]["conditions"]] == [
        x["name"] for x in reversed(first)]


def test_within_shot_time_map_split_and_score():
    module = experiment()
    specs = module.within_shot_time_map_specs(4.103, 4.089)
    order = specs[0]["order"]
    split = module.split_eight_records(list(range(16)), order, shots=2)
    assert split["feature_early_g"] == [0, 8]
    assert split["control_late_e"] == [7, 15]
    with pytest.raises(ValueError, match="incomplete"):
        module.split_eight_records(list(range(15)), order, shots=2)
    fractions = {name: 0.1 for name in order}
    for site in ("feature", "control"):
        fractions[f"{site}_early_e"] = 0.7
        fractions[f"{site}_late_e"] = 0.4 if site == "feature" else 0.6
    report = module.score_eight_condition_program(fractions)
    assert report["feature"]["drop"] == pytest.approx(0.3)
    assert report["control"]["drop"] == pytest.approx(0.1)
    assert report["excess_drop"] == pytest.approx(0.2)
    fractions["feature_late_g"] = 0.2
    assert module.score_eight_condition_program(fractions)["usable"] is True


def test_eight_site_program_accepts_two_flux_gains(monkeypatch):
    module = experiment()
    specs = module.within_shot_time_map_specs(4.103, 4.089)
    configs = []
    for cond in specs[0]["conditions"]:
        configs.append({"ff_gain": -17000 if cond["site"] == "feature" else -16000,
                        "ff_park_gain": -25146, "shots": 600, "reps": 600,
                        "opx_swap_hold_us": cond["hold_us"],
                        "opx_resident_preparation_state": cond["state"]})
    seen = []
    monkeypatch.setattr(module.resident.ResidentDriveProgram, "__init__",
                        lambda self, soccfg, cfg, payload, loop:
                        seen.append(dict(cfg)))
    program = module.EightSiteSwapHoldProgram(None, configs, None, None)
    assert program.logical_shots == 600
    assert program.conditions_per_shot == 8
    assert seen[0]["reps"] == 4800
    bad = [dict(c) for c in configs]
    bad[-1]["ff_gain"] = -15000
    with pytest.raises(ValueError, match="two sites"):
        module.EightSiteSwapHoldProgram(None, bad, None, None)


def test_within_shot_time_map_plan_is_bounded():
    plan = experiment().plan(within_shot_time_map=True)
    assert plan["conditions_per_shot"] == 8
    assert plan["programs"] == 10
    assert plan["later_holds_us"] == [3.0, 6.0, 10.0, 16.0, 25.0]


def test_loss_dynamics_repeats_feature_control_in_reversed_shot_order(capsys):
    import json
    module = experiment()
    specs = module.loss_dynamics_specs(4.106, 4.092)
    assert len(specs) == 60
    assert all(x["shots"] == 250 and len(x["conditions"]) == 8 for x in specs)
    assert [x["cycle"] for x in specs] == list(range(60))
    assert {c["hold_us"] for c in specs[0]["conditions"]} == {1.5, 25.0}
    assert specs[1]["order"] == list(reversed(specs[0]["order"]))
    assert {c["flux_ghz"] for c in specs[0]["conditions"]} == {4.106, 4.092}
    assert module.main(["--plan", "--loss-dynamics"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["programs"] == 60 and plan["conditions_per_shot"] == 8
    assert plan["shots_per_program"] == 250


def test_loss_dynamics_scores_late_loss_without_rejecting_feature_floor():
    module = experiment()
    fractions = {"feature_early_g": .08, "feature_early_e": .20,
                 "feature_late_g": .08, "feature_late_e": .09,
                 "control_early_g": .08, "control_early_e": .55,
                 "control_late_g": .09, "control_late_e": .35}
    score = module.score_loss_dynamics(fractions)
    assert score["feature"]["early_contrast"] == pytest.approx(.12)
    assert score["excess_drop"] == pytest.approx(-.10)
    assert score["usable"]
    fractions["control_late_g"] = .20
    assert not module.score_loss_dynamics(fractions)["usable"]
