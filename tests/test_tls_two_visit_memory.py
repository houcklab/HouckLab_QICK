"""Contracts for the direct two-visit q3 loss-feature memory experiment."""

import importlib
import math

import pytest


MODULE = "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSTwoVisitMemory"


def experiment():
    return importlib.import_module(MODULE)


def test_two_visit_waveform_has_load_store_probe_and_complete_return():
    module = experiment()
    compensation = {"segment_edges_ns": [0.0, 1_000.0],
                    "multipliers": [1.0, 1.0]}
    segments = module.two_visit_segments(
        compensation, load_us=2.0, store_us=1.0,
        probe_us=3.0, second_amplitude=0.5, recovery_us=40.0)
    assert segments == [(1.0, 2.0), (0.0, 1.0),
                        (0.5, 3.0), (0.0, 40.0)]


def test_two_visit_waveform_superposes_short_step_tail():
    module = experiment()
    compensation = {"segment_edges_ns": [0.0, 1_000.0],
                    "multipliers": [1.2, 1.0]}
    segments = module.two_visit_segments(
        compensation, load_us=2.0, store_us=1.0,
        probe_us=2.0, second_amplitude=1.0, recovery_us=40.0)
    def level_at(t):
        edge = 0.0
        for level, duration in segments:
            edge += duration
            if t < edge - 1e-9:
                return level
        raise AssertionError("time exceeds waveform")
    assert level_at(.5) == pytest.approx(1.2)
    assert level_at(1.5) == pytest.approx(1.0)
    assert level_at(2.5) == pytest.approx(-.2)
    assert level_at(3.5) == pytest.approx(1.2)
    assert level_at(5.5) == pytest.approx(-.2)
    assert level_at(6.5) == pytest.approx(0.0)
    assert sum(duration for _, duration in segments) == pytest.approx(45.0)


def test_two_visit_specs_interleave_all_site_pairs_and_reversed_order():
    module = experiment()
    specs = module.program_specs(4.107, 4.093)
    assert len(specs) == 8
    assert [x["store_us"] for x in specs] == [
        .5, 2.0, 10.0, 40.0, 40.0, 10.0, 2.0, .5]
    assert all(x["shots"] == 800 and len(x["conditions"]) == 8 for x in specs)
    assert [x["name"] for x in specs[0]["conditions"]] == [
        "ff_g", "ff_e", "fc_g", "fc_e", "cf_g", "cf_e", "cc_g", "cc_e"]
    assert specs[-1]["order"] == list(reversed(specs[0]["order"]))
    split = module.split_records(list(range(16)), specs[0]["order"], shots=2)
    assert split["ff_g"] == [0, 8]
    assert split["cc_e"] == [7, 15]
    with pytest.raises(ValueError, match="incomplete"):
        module.split_records(list(range(15)), specs[0]["order"], shots=2)


def test_memory_score_removes_independent_multiplicative_loss():
    module = experiment()
    fractions = {"ff_g": .05, "ff_e": .45,
                 "fc_g": .05, "fc_e": .65,
                 "cf_g": .05, "cf_e": .55,
                 "cc_g": .05, "cc_e": .80}
    scored = module.score(fractions)
    assert scored["log_interaction"] == pytest.approx(0.0)
    assert scored["usable"]
    fractions["ff_e"] = .53
    assert module.score(fractions)["log_interaction"] == pytest.approx(math.log(1.2))
    fractions["ff_e"] = .12
    assert not module.score(fractions)["usable"]


def test_two_visit_program_accepts_four_site_pairs_and_both_preparations(monkeypatch):
    module = experiment()
    specs = module.program_specs(4.107, 4.093)
    lookup = {4.107: -16099, 4.093: -15861}
    configs = [module.arm_config({"sigma": .1, "ff_park_gain": -25146},
                                 cond, lookup, shots=800)
               for cond in specs[0]["conditions"]]
    seen = []
    monkeypatch.setattr(module.resident.ResidentDriveProgram, "__init__",
                        lambda self, _soccfg, cfg, _payload, _loop:
                        seen.append(dict(cfg)))
    program = module.TwoVisitProgram(None, configs, None, None)
    assert program.logical_shots == 800
    assert program.conditions_per_shot == 8
    assert seen[0]["reps"] == 6400
    assert [cfg["opx_probe_ff_gain"] for cfg in configs[:2]] == [-16099, -16099]
    bad = [dict(c) for c in configs]
    bad[-1]["opx_probe_ff_gain"] = -16099
    with pytest.raises(ValueError, match="four visit pairs"):
        module.TwoVisitProgram(None, bad, None, None)


def test_plan_describes_direct_memory_not_spectroscopy(capsys):
    import json
    module = experiment()
    assert module.main(["--plan"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["load_us"] == 10.0
    assert plan["store_us"] == [0.5, 2.0, 10.0, 40.0]
    assert plan["probe_us"] == 6.0
    assert plan["conditions_per_shot"] == 8
    assert plan["programs"] == 8
    assert plan["intermediate_readouts"] == 0


def test_confirmation_interleaves_ten_and_forty_microseconds_within_shot():
    module = experiment()
    specs = module.confirmation_specs(4.102, 4.088)
    assert len(specs) == 4
    assert all(len(x["conditions"]) == 16 and x["shots"] == 1200
               for x in specs)
    assert {x["store_us"] for x in specs[0]["conditions"]} == {10.0, 40.0}
    assert specs[1]["order"] == list(reversed(specs[0]["order"]))
    assert specs[2]["order"][0].startswith("t40_")
    assert specs[3]["order"] == list(reversed(specs[2]["order"]))
    split = module.split_records(list(range(32)), specs[0]["order"], shots=2)
    assert split[specs[0]["order"][0]] == [0, 16]


def test_confirmation_program_validates_all_site_gap_state_cells(monkeypatch):
    module = experiment()
    specs = module.confirmation_specs(4.102, 4.088)
    lookup = {4.102: -16099, 4.088: -15861}
    configs = [module.arm_config({"sigma": .1, "ff_park_gain": -25146},
                                 cond, lookup, shots=1200)
               for cond in specs[0]["conditions"]]
    seen = []
    monkeypatch.setattr(module.resident.ResidentDriveProgram, "__init__",
                        lambda self, _soccfg, cfg, _payload, _loop:
                        seen.append(dict(cfg)))
    program = module.TwoVisitProgram(None, configs, None, None)
    assert program.conditions_per_shot == 16
    assert seen[0]["reps"] == 19200
    bad = [dict(c) for c in configs]
    bad[-1]["opx_store_us"] = 10.0
    with pytest.raises(ValueError, match="visit pairs"):
        module.TwoVisitProgram(None, bad, None, None)


def test_confirmation_plan_is_focused_and_has_no_intermediate_readout(capsys):
    import json
    module = experiment()
    assert module.main(["--plan", "--confirm"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["store_us"] == [10.0, 40.0]
    assert plan["conditions_per_shot"] == 16
    assert plan["shots_per_program"] == 1200
    assert plan["intermediate_readouts"] == 0


def test_confirmation_scores_each_gap_and_pairs_within_block():
    module = experiment()
    entry = module.confirmation_specs(4.102, 4.088)[0]
    values = {"ff_g": .05, "ff_e": .45, "fc_g": .05, "fc_e": .65,
              "cf_g": .05, "cf_e": .55, "cc_g": .05, "cc_e": .80}
    for cond in entry["conditions"]:
        key = cond["name"].split("_", 1)[1]
        cond["excited_fraction_pre_axis"] = values[key]
        if cond["store_us"] == 10.0 and key == "ff_e":
            cond["excited_fraction_pre_axis"] = .53
    scored = module.score_entry(entry, confirm=True)
    assert scored["10.0"]["log_interaction"] == pytest.approx(math.log(1.2))
    assert scored["40.0"]["log_interaction"] == pytest.approx(0.0)
    report = module._confirmation_report([entry], {entry["name"]: scored})
    assert report["mean_paired_difference"] == pytest.approx(math.log(1.2))
