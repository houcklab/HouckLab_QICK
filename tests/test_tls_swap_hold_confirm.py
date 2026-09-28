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


def test_loss_line_dynamics_interleaves_three_feature_frequencies_and_control(capsys):
    import json
    module = experiment()
    specs = module.loss_line_dynamics_specs(4.104, 4.090)
    assert len(specs) == 40
    assert all(x["shots"] == 200 and len(x["conditions"]) == 16 for x in specs)
    assert {c["flux_ghz"] for c in specs[0]["conditions"]} == {
        4.101, 4.104, 4.107, 4.090}
    assert specs[1]["order"] == list(reversed(specs[0]["order"]))
    order = specs[0]["order"]
    records = list(range(32))
    split = module.split_line_records(records, order, shots=2)
    assert split["left_early_g"] == [0, 16]
    assert split["control_late_e"] == [15, 31]
    assert module.main(["--plan", "--loss-line-dynamics"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["programs"] == 40 and plan["conditions_per_shot"] == 16
    assert plan["feature_offsets_mhz"] == [-3, 0, 3]


def test_loss_line_program_and_score_use_four_flux_points(monkeypatch):
    module = experiment()
    entry = module.loss_line_dynamics_specs(4.104, 4.090)[0]
    cfgs = module._condition_configs({"sigma": .1, "ff_park_gain": -25146}, entry,
                                     {4.101: -1, 4.104: -2,
                                      4.107: -3, 4.090: -4})
    seen = []
    monkeypatch.setattr(module.resident.ResidentDriveProgram, "__init__",
                        lambda self, _soccfg, cfg, _payload, _loop:
                        seen.append(dict(cfg)))
    program = module.MultiSiteSwapHoldProgram(None, cfgs, None, None)
    assert program.conditions_per_shot == 16
    assert program.logical_shots == 200
    assert seen[0]["reps"] == 3200
    fractions = {}
    for site, early, late in (("left", .4, .2), ("center", .5, .1),
                              ("right", .6, .05), ("control", .6, .5)):
        fractions.update({f"{site}_early_g": .1,
                          f"{site}_early_e": early + .1,
                          f"{site}_late_g": .1,
                          f"{site}_late_e": late + .1})
    score = module.score_loss_line(fractions)
    assert score["extra_loss"]["left"] == pytest.approx(.1)
    assert score["extra_loss"]["center"] == pytest.approx(.3)
    assert score["extra_loss"]["right"] == pytest.approx(.45)
    assert score["right_minus_left_extra_loss"] == pytest.approx(.35)
    assert score["usable"]


def test_dense_profile_interleaves_seven_offsets_and_control(capsys):
    import json
    module = experiment()
    specs = module.dense_profile_specs(4.106, 4.092)
    assert len(specs) == 40
    assert all(x["shots"] == 200 and len(x["conditions"]) == 16 for x in specs)
    assert [c["flux_ghz"] for c in specs[0]["conditions"][::2]] == [
        4.100, 4.102, 4.104, 4.106, 4.108, 4.110, 4.112, 4.092]
    assert {c["hold_us"] for c in specs[0]["conditions"]} == {25.0}
    assert specs[1]["order"] == list(reversed(specs[0]["order"]))
    split = module.split_dense_records(list(range(32)), specs[0]["order"], shots=2)
    assert split["m6_g"] == [0, 16]
    assert split["control_e"] == [15, 31]
    with pytest.raises(ValueError, match="incomplete"):
        module.split_dense_records(list(range(31)), specs[0]["order"], shots=2)
    assert module.main(["--plan", "--dense-profile"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["feature_offsets_mhz"] == [-6, -4, -2, 0, 2, 4, 6]
    assert plan["conditions_per_shot"] == 16


def test_dense_profile_program_and_score_separate_shape_from_control(monkeypatch):
    module = experiment()
    entry = module.dense_profile_specs(4.106, 4.092)[0]
    gains = {4.100: -1, 4.102: -2, 4.104: -3, 4.106: -4,
             4.108: -5, 4.110: -6, 4.112: -7, 4.092: -8}
    cfgs = module._condition_configs({"sigma": .1, "ff_park_gain": -25146},
                                     entry, gains)
    seen = []
    monkeypatch.setattr(module.resident.ResidentDriveProgram, "__init__",
                        lambda self, _soccfg, cfg, _payload, _loop:
                        seen.append(dict(cfg)))
    program = module.DenseProfileProgram(None, cfgs, None, None)
    assert program.conditions_per_shot == 16
    assert program.logical_shots == 200
    assert seen[0]["reps"] == 3200
    fractions = {f"{site}_g": .1 for site in module.DENSE_SITES}
    fractions.update({f"{site}_e": .6 for site in module.DENSE_SITES})
    fractions["c_e"] = .25
    fractions["p2_e"] = .35
    score = module.score_dense_profile(fractions)
    assert score["extra_loss"]["c"] == pytest.approx(.35)
    assert score["extra_loss"]["p2"] == pytest.approx(.25)
    assert score["usable"]
    fractions["control_e"] = .15
    assert not module.score_dense_profile(fractions)["usable"]


def test_dense_profile_long_monitor_preserves_same_shots_and_has_bounded_length(capsys):
    import json
    module = experiment()
    specs = module.dense_profile_specs(4.105, 4.091, cycles=180)
    assert len(specs) == 180
    assert [x["cycle"] for x in specs] == list(range(180))
    assert specs[0]["order"] == specs[-2]["order"]
    assert specs[1]["order"] == specs[-1]["order"]
    assert all(x["shots"] == 200 for x in specs)
    assert module.main(["--plan", "--dense-profile",
                        "--dense-profile-cycles", "180"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["programs"] == 180
    assert plan["cycles"] == 180
    with pytest.raises(ValueError, match="40..180"):
        module.dense_profile_specs(4.105, 4.091, cycles=181)
