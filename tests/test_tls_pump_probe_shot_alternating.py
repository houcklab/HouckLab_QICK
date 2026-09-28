"""Contracts for the target-resident, shot-alternating pilot."""

import importlib

import pytest


MODULE = "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeShotAlternating"


def experiment():
    return importlib.import_module(MODULE)


def test_four_conditions_reverse_order_without_changing_pulses():
    module = experiment()
    forward = module.conditions(4.129, reverse=False)
    reverse = module.conditions(4.129, reverse=True)
    assert [x["name"] for x in forward] == ["sham_g", "sham_e", "on_g", "on_e"]
    assert [x["name"] for x in reverse] == list(reversed([x["name"] for x in forward]))
    assert {x["name"]: (x["preparation_state"], x["gain"], x["drive_mhz"])
            for x in forward} == {x["name"]: (x["preparation_state"], x["gain"], x["drive_mhz"])
                                 for x in reverse}
    assert all(x["drive_mhz"] == pytest.approx(4134.0) for x in forward)


def test_flat_stream_records_split_by_hardware_shot_order():
    module = experiment()
    order = ("sham_g", "sham_e", "on_g", "on_e")
    records = [module.resident.SingleIQ(i, -i) for i in range(12)]
    split = module.split_records(records, order, shots=3)
    assert [r.i for r in split["sham_g"]] == [0, 4, 8]
    assert [r.i for r in split["on_e"]] == [3, 7, 11]
    with pytest.raises(ValueError, match="expected 12"):
        module.split_records(records[:-1], order, shots=3)


def test_stream_boundary_counts_logical_shots_not_individual_records():
    module = experiment()
    assert module.stream_dimensions(200) == {
        "total_shots": 200, "records_per_shot": 4,
        "total_units": 200, "records_per_unit": 4}


def test_constructor_exposes_record_count_to_stream_reader(monkeypatch):
    module = experiment()
    captured = {}
    def fake_base_init(self, _soccfg, cfg, _payload, _loop):
        captured.update(cfg)
    monkeypatch.setattr(module.resident.ResidentDriveProgram, "__init__", fake_base_init)
    cfgs = [{"ff_gain": -17000, "ff_park_gain": -25146,
             "opx_resident_pre_us": 20.0, "opx_resident_post_us": 0.1,
             "opx_resident_freq_mhz": 4134.0, "shots": 200, "reps": 200,
             "opx_resident_gain": gain,
             "opx_resident_preparation_state": state}
            for gain, state in ((0, "g"), (0, "e"), (6000, "g"), (6000, "e"))]
    program = module.ShotAlternatingResidentProgram(None, cfgs, None, None)
    assert program.logical_shots == 200
    assert captured["shots"] == 200
    assert captured["reps"] == 800


def test_program_counts_four_records_before_one_stream_boundary(monkeypatch):
    module = experiment()
    program = object.__new__(module.ShotAlternatingResidentProgram)
    program.cfg = {"qubit_ch": 1}
    program.condition_cfgs = [{"condition": x} for x in range(4)]
    program.reps, program.logical_shots = 12, 3
    program.record_base, program.done_addr = 32, 1
    program.ch_page = lambda *_: 0
    program._declare_experiment = lambda: None
    program._initialize_stream = lambda _controls, **kw: events.append(("stream", kw))
    program._begin_park_lifecycle = lambda: None
    program._end_park_lifecycle = lambda: None
    program._emit_body = lambda: events.append(("emit", program.cfg["condition"]))
    program._stream_after_shot = lambda: events.append("boundary")
    program._finish_stream = lambda: None
    program.regwi = program.memwi = program.label = program.loopnz = program.end = lambda *_: None
    program.mathi = lambda _page, _dst, _src, _op, value: events.append(("done", value))
    events = []
    monkeypatch.setattr(module, "_declare_common", lambda _p: None)
    monkeypatch.setattr(module, "allocate_registers", lambda *_: {"address": 1})
    monkeypatch.setattr(module, "_reserved_registers", lambda *_: set())
    monkeypatch.setattr(module, "resident_control_names", lambda _cfg, names: names)
    monkeypatch.setattr(module, "allocate_named_registers",
                        lambda *_a, **_kw: {"shot_loop": 2, "done": 3})
    program.make_program()
    assert [event for event in events if event[0] == "emit"] == [
        ("emit", 0), ("emit", 1), ("emit", 2), ("emit", 3)]
    assert ("done", 4) in events
    assert events.count("boundary") == 1
    assert next(event[1] for event in events if event[0] == "stream")[
        "records_per_unit"] == 4


def test_pilot_plan_is_bounded_and_uses_full_return():
    module = experiment()
    plan = module.plan()
    assert plan["programs"] == 2
    assert plan["conditions_per_shot"] == 4
    assert plan["shots_per_program"] == 200
    assert plan["full_return_before_each_readout_us"] == 40.0
    assert plan["fresh_drive_check_arms"] == 4


def test_fresh_drive_check_tracks_new_feature_without_old_frequency_bracket():
    module = experiment()
    arms = module.fresh_drive_arms(4.144)
    assert [a["tone"] for a in arms] == [
        "sham_a", "on_6000", "detuned_6000", "sham_b"]
    assert [a["gain"] for a in arms] == [0, 6000, 6000, 0]
    assert [a["drive_mhz"] for a in arms] == [4149.0, 4149.0, 4134.0, 4149.0]
    assert all(a["flux_ghz"] == 4.144 and a["shots"] == 200 for a in arms)


def test_scoring_retains_hot_preparation_contrast_as_control():
    module = experiment()
    score = module.score_conditions({"sham_g": 0.08, "sham_e": 0.31,
                                      "on_g": 0.29, "on_e": 0.25})
    assert score["cold_drive_contrast"] == pytest.approx(0.21)
    assert score["hot_preparation_contrast"] == pytest.approx(0.23)


def test_loading_check_pairs_four_preholds_in_both_shot_orders():
    module = experiment()
    specs = module.loading_program_specs(4.129)
    assert len(specs) == 8
    assert [(x["pre_drive_us"], x["direction"]) for x in specs] == [
        (4.0, "forward"), (8.0, "forward"),
        (12.0, "forward"), (20.0, "forward"),
        (20.0, "reverse"), (12.0, "reverse"),
        (8.0, "reverse"), (4.0, "reverse")]
    assert all(x["post_drive_us"] == 0.1 for x in specs)
    assert all({c["name"] for c in x["conditions"]} ==
               {"sham_g", "sham_e", "on_g", "on_e"} for x in specs)
    assert specs[0]["order"] == ["sham_g", "sham_e", "on_g", "on_e"]
    assert specs[-1]["order"] == ["on_e", "on_g", "sham_e", "sham_g"]


def test_loading_check_requires_repeatable_hot_and_drive_contrast():
    module = experiment()
    scores = {
        "load4_forward": {"hot_preparation_contrast": 0.25,
                          "cold_drive_contrast": 0.20,
                          "hot_minus_cold_drive_change": 0.02},
        "load4_reverse": {"hot_preparation_contrast": 0.24,
                          "cold_drive_contrast": 0.18,
                          "hot_minus_cold_drive_change": 0.01},
        "load8_forward": {"hot_preparation_contrast": 0.16,
                          "cold_drive_contrast": 0.19,
                          "hot_minus_cold_drive_change": 0.05},
        "load8_reverse": {"hot_preparation_contrast": 0.08,
                          "cold_drive_contrast": 0.17,
                          "hot_minus_cold_drive_change": 0.04},
        "load12_forward": {"hot_preparation_contrast": 0.09,
                           "cold_drive_contrast": 0.17,
                           "hot_minus_cold_drive_change": 0.04},
        "load12_reverse": {"hot_preparation_contrast": 0.12,
                           "cold_drive_contrast": 0.17,
                           "hot_minus_cold_drive_change": 0.04},
        "load20_forward": {"hot_preparation_contrast": 0.19,
                           "cold_drive_contrast": 0.17,
                           "hot_minus_cold_drive_change": 0.04},
        "load20_reverse": {"hot_preparation_contrast": 0.09,
                           "cold_drive_contrast": 0.17,
                           "hot_minus_cold_drive_change": 0.04},
    }
    assert module.usable_loading_times(scores) == [4.0]


def test_weak_short_drive_check_is_diagnostic_only_for_loading_scan():
    module = experiment()
    weak = {"sham_a": 0.065, "on_6000": 0.135,
            "detuned_6000": 0.105, "sham_b": 0.080,
            "on_excess": 0.0625, "detuned_excess": 0.0325,
            "bracket_drift": 0.015, "usable": False}
    assert module.drive_check_gate(weak, loading_check=True) == "diagnostic_only"
    with pytest.raises(RuntimeError, match="fresh feature drive check failed"):
        module.drive_check_gate(weak, loading_check=False)


def test_loss_check_crosses_feature_flank_holds_tones_and_orders():
    module = experiment()
    specs = module.loss_program_specs(4.129)
    assert len(specs) == 16
    assert {(x["site"], x["post_drive_us"], x["tone"], x["direction"])
            for x in specs} == {
                (site, hold, tone, direction)
                for site in ("feature", "flank")
                for hold in (0.1, 2.0)
                for tone in ("on", "detuned")
                for direction in ("forward", "reverse")}
    assert all(x["pre_drive_us"] == 20.0 and x["shots"] == 400
               for x in specs)
    feature_on = next(x for x in specs if x["site"] == "feature" and
                      x["tone"] == "on")
    flank_detuned = next(x for x in specs if x["site"] == "flank" and
                         x["tone"] == "detuned")
    assert {c["drive_mhz"] for c in feature_on["conditions"]} == {4134.0}
    assert {c["drive_mhz"] for c in flank_detuned["conditions"]} == {4105.0}
    assert {x["flux_ghz"] for x in specs if x["site"] == "flank"} == {4.115}
    assert specs[0]["direction"] == "forward"
    assert specs[-1]["direction"] == "reverse"


def test_loss_controls_reject_detuned_drive_and_sham_baseline_motion():
    module = experiment()
    scores = {}
    for repeat in (0, 1):
        for site in ("feature", "flank"):
            scores[f"r{repeat}_{site}_hold0p1_on"] = {
                "cold_drive_contrast": 0.20,
                "hot_preparation_contrast": 0.25}
            scores[f"r{repeat}_{site}_hold0p1_detuned"] = {
                "cold_drive_contrast": 0.02,
                "hot_preparation_contrast": 0.24}
            scores[f"r{repeat}_{site}_hold2_on"] = {
                "cold_drive_contrast": 0.07,
                "hot_preparation_contrast": 0.12}
            scores[f"r{repeat}_{site}_hold2_detuned"] = {
                "cold_drive_contrast": 0.02,
                "hot_preparation_contrast": 0.11}
    assert module.loss_control_report(scores)["usable"]
    scores["r0_feature_hold0p1_detuned"]["cold_drive_contrast"] = 0.17
    assert not module.loss_control_report(scores)["usable"]
    scores["r0_feature_hold0p1_detuned"]["cold_drive_contrast"] = 0.02
    scores["r1_flank_hold0p1_detuned"]["hot_preparation_contrast"] = 0.01
    assert not module.loss_control_report(scores)["usable"]


def test_loss_controls_reject_a_long_hold_floor_or_detuned_response():
    module = experiment()
    scores = {}
    for repeat in (0, 1):
        for site in ("feature", "flank"):
            for hold in ("0p1", "2"):
                scores[f"r{repeat}_{site}_hold{hold}_on"] = {
                    "cold_drive_contrast": 0.20,
                    "hot_preparation_contrast": 0.25}
                scores[f"r{repeat}_{site}_hold{hold}_detuned"] = {
                    "cold_drive_contrast": 0.02,
                    "hot_preparation_contrast": 0.24}
    assert module.loss_control_report(scores)["usable"]
    scores["r1_feature_hold2_on"]["hot_preparation_contrast"] = 0.0
    assert not module.loss_control_report(scores)["usable"]
    scores["r1_feature_hold2_on"]["hot_preparation_contrast"] = 0.12
    scores["r0_flank_hold2_detuned"]["cold_drive_contrast"] = 0.15
    assert not module.loss_control_report(scores)["usable"]


def test_loss_plan_uses_longer_streams_and_matched_controls():
    module = experiment()
    plan = module.plan(loss_check=True)
    assert plan["programs"] == 16
    assert plan["shots_per_program"] == 400
    assert plan["post_drive_holds_us"] == [0.1, 2.0]
    assert plan["sites"] == ["feature", "14-MHz lower flank"]
    assert plan["tones_mhz"] == [5.0, -10.0]


def test_loss_statistic_subtracts_hold_detuning_and_flank_in_each_order():
    module = experiment()
    scores = {x["name"]: {"hot_minus_cold_drive_change": 0.0}
              for x in module.loss_program_specs(4.129)}
    scores["r0_feature_hold0p1_on"]["hot_minus_cold_drive_change"] = 0.4
    scores["r0_feature_hold2_on"]["hot_minus_cold_drive_change"] = 0.1
    scores["r0_flank_hold0p1_on"]["hot_minus_cold_drive_change"] = 0.2
    scores["r0_flank_hold2_on"]["hot_minus_cold_drive_change"] = 0.1
    report = module.loss_effect_report(scores)
    assert report["r0"]["feature_on_incremental_loss"] == pytest.approx(0.3)
    assert report["r0"]["flank_on_incremental_loss"] == pytest.approx(0.1)
    assert report["r0"]["feature_specific_tone_selective_incremental_loss"] == pytest.approx(0.2)
    assert report["r1"]["feature_specific_tone_selective_incremental_loss"] == 0.0


def test_loss_program_configs_use_the_flank_dc_and_full_shot_count():
    module = experiment()
    entry = next(x for x in module.loss_program_specs(4.129)
                 if x["site"] == "flank" and x["tone"] == "detuned" and
                 x["post_drive_us"] == 2.0)
    cfgs = module.condition_configs({"sigma": 0.1}, entry,
                                    {4.129: -100, 4.115: -123}, 4.129)
    assert len(cfgs) == 4
    assert {cfg["ff_gain"] for cfg in cfgs} == {-123}
    assert {cfg["opx_resident_freq_mhz"] for cfg in cfgs} == {4105.0}
    assert {cfg["opx_resident_post_us"] for cfg in cfgs} == {2.0}
    assert {cfg["shots"] for cfg in cfgs} == {400}
    assert {cfg["opx_resident_gain"] for cfg in cfgs} == {0, 6000}
