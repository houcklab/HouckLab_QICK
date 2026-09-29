"""Contracts for the weak-site, within-shot afterglow screen."""

import importlib
import pytest


MODULE = "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSWeakAfterglowScreen"


def experiment():
    return importlib.import_module(MODULE)


def scout_rows():
    rows = []
    for index in range(251):
        frequency = round(3.8 + .002 * index, 3)
        row = {"target_frequency_ghz": str(frequency)}
        for suffix in ("", "_scan_up", "_scan_down"):
            row.update({f"P0{suffix}": "0.1", f"P1{suffix}": "0.9",
                        f"Ps_10us{suffix}": "0.82",
                        f"Ps_25us{suffix}": "0.82"})
        rows.append(row)
    indexed = {float(row["target_frequency_ghz"]): row for row in rows}
    for center, depth in ((3.950, .14), (4.066, .08), (4.140, .42)):
        for offset, factor in ((-.002, .48), (0, 1), (.002, .48)):
            row = indexed[round(center + offset, 3)]
            for suffix in ("", "_scan_up", "_scan_down"):
                row[f"Ps_25us{suffix}"] = str(.82 - .8 * depth * factor)
                row[f"Ps_10us{suffix}"] = str(.82 - .8 * depth * factor)
    return rows


def fine_rows(seed=3.954, true_center=3.950):
    rows = []
    for index in range(45):
        frequency = round(seed - .022 + .001 * index, 3)
        offset = abs(frequency - true_center)
        survival = .84 - (.25 if offset < .0001 else
                          .15 if offset < .0011 else 0)
        row = {"target_frequency_ghz": str(frequency)}
        for suffix in ("", "_scan_up", "_scan_down"):
            row.update({f"P0{suffix}": ".1", f"P1{suffix}": ".9",
                        f"Ps_10us{suffix}": str(.1 + .8 * survival),
                        f"Ps_25us{suffix}": str(.1 + .8 * survival)})
        rows.append(row)
    return rows


def test_scout_selects_separated_weak_sites_and_excludes_old_strong_band():
    module = experiment()
    sites = module.select_weak_sites(scout_rows(), max_sites=3)
    assert [site["center_ghz"] for site in sites] == [3.950, 4.066]
    assert all(site["control_ghz"] != site["center_ghz"] for site in sites)
    assert all(site["depth_scan_up"] > 0 and site["depth_scan_down"] > 0
               for site in sites)


def test_incomplete_scout_fails_before_science():
    module = experiment()
    with pytest.raises(ValueError, match="complete 251-point"):
        module.select_weak_sites(scout_rows()[:-1])


def test_one_mhz_rescan_moves_edge_seed_to_actual_local_minimum():
    module = experiment()
    refined = module.refine_site(fine_rows(), seed_ghz=3.954)
    assert refined["center_ghz"] == 3.950
    assert .014 <= abs(refined["control_ghz"] - 3.950) <= .020
    assert refined["depth_scan_up"] > .08
    with pytest.raises(ValueError, match="complete 45-point"):
        module.refine_site(fine_rows()[:-1], seed_ghz=3.954)


def test_refined_sites_do_not_use_another_selected_site_as_control():
    module = experiment()
    sites = module.filter_refined_sites([
        {"center_ghz": 3.950, "control_ghz": 3.966},
        {"center_ghz": 3.974, "control_ghz": 3.950},
        {"center_ghz": 4.066, "control_ghz": 4.050},
    ])
    assert [site["center_ghz"] for site in sites] == [3.950, 4.066]


def test_programs_interleave_three_controls_and_reverse_order():
    module = experiment()
    sites = [{"center_ghz": 3.950, "control_ghz": 3.966}]
    specs = module.program_specs(sites)
    assert len(specs) == 6
    assert [(s["wait_us"], s["cycle"]) for s in specs] == [
        (100.0, 0), (300.0, 0), (1000.0, 0),
        (1000.0, 1), (300.0, 1), (100.0, 1)]
    assert specs[0]["order"] == ["cold_on", "hot_on", "hot_off"]
    assert specs[-1]["order"] == ["hot_off", "hot_on", "cold_on"]
    arms = {arm["name"]: arm for arm in specs[0]["conditions"]}
    assert arms["hot_on"]["pump_state"] == arms["hot_off"]["pump_state"] == "e"
    assert arms["hot_on"]["pump_ghz"] == arms["cold_on"]["pump_ghz"] == 3.950
    assert arms["hot_off"]["pump_ghz"] == 3.966
    assert {arm["probe_ghz"] for arm in arms.values()} == {3.950}


def test_flat_paired_records_split_within_each_logical_shot():
    module = experiment()
    records = list(range(9))
    split = module.split_records(records, ["cold_on", "hot_on", "hot_off"], shots=3)
    assert split == {"cold_on": [0, 3, 6], "hot_on": [1, 4, 7],
                     "hot_off": [2, 5, 8]}
    with pytest.raises(ValueError, match="incomplete"):
        module.split_records(records[:-1], ["cold_on", "hot_on", "hot_off"], shots=3)


def _scored_program(cycle, hot_on, hot_off, cold_on, *, raw_hot=None):
    values = {"hot_on": hot_on, "hot_off": hot_off, "cold_on": cold_on}
    projected = {"hot_on": hot_on if raw_hot is None else raw_hot,
                 "hot_off": hot_off, "cold_on": cold_on}
    return {"site_index": 0, "wait_us": 300.0, "cycle": cycle,
            "status": "complete", "conditions": [
                {"name": name, "summary": {
                    "herald_ground_shots": 200,
                    "final_excited_given_ground": value,
                    "projected_final_given_ground": projected[name]}}
                for name, value in values.items()]}


def test_hit_requires_both_controls_both_orders_and_raw_iq():
    module = experiment()
    first = _scored_program(0, .19, .10, .11)
    second = _scored_program(1, .18, .09, .10)
    report = module.score_programs([first, second], controls_valid=True)
    assert report["site0_wait300"]["hit"] is True
    assert report["site0_wait300"]["cycles"][0]["hot_on_minus_hot_off"] == pytest.approx(.09)
    bad_raw = _scored_program(1, .18, .09, .10, raw_hot=.08)
    assert module.score_programs([first, bad_raw], controls_valid=True)["site0_wait300"]["hit"] is False
    assert module.score_programs([first, second], controls_valid=False)["site0_wait300"]["hit"] is False


def test_small_or_unreplicated_signal_is_not_a_hit():
    module = experiment()
    first = _scored_program(0, .13, .10, .11)
    second = _scored_program(1, .18, .09, .10)
    assert module.score_programs([first, second], controls_valid=True)["site0_wait300"]["hit"] is False


def test_three_condition_program_reports_all_paired_records(monkeypatch):
    module = experiment()
    captured = {}
    monkeypatch.setattr(module.heralded.HeraldedPumpProbeProgram, "__init__",
                        lambda _self, _soc, cfg, _payload, _loop: captured.update(cfg))
    cfgs = [{"ff_gain": gain, "opx_herald_probe_gain": -17000,
             "ff_park_gain": -25146, "shots": 600, "reps": 600,
             "opx_herald_interstage_extra_us": 300.0,
             "opx_herald_pump_state": state,
             "opx_herald_probe_state": "g"}
            for gain, state in ((-17000, "g"), (-17000, "e"), (-16800, "e"))]
    program = module.InterleavedAfterglowProgram(None, cfgs, None, None)
    assert program.logical_shots == 600
    assert captured["reps"] == 1800


def test_three_subshots_emit_before_one_stream_boundary(monkeypatch):
    module = experiment()
    program = object.__new__(module.InterleavedAfterglowProgram)
    program.cfg = {"qubit_ch": 1}
    program.condition_cfgs = [{"name": name} for name in ("cold_on", "hot_on", "hot_off")]
    program.logical_shots = 2
    program.record_base, program.done_addr = 32, 1
    program.ch_page = lambda *_: 0
    program._declare_experiment = lambda: None
    program._begin_park_lifecycle = program._end_park_lifecycle = lambda: None
    events = []
    program._emit_body = lambda: events.append(("emit", program.cfg["name"]))
    program._initialize_stream = lambda _controls, **kw: events.append(("stream", kw))
    program._stream_after_shot = lambda: events.append("boundary")
    program._finish_stream = lambda: None
    program.us2cycles = lambda us: us
    program.sync_all = lambda cycles: events.append(("recovery", cycles))
    program.regwi = program.memwi = program.label = program.loopnz = program.end = lambda *_: None
    program.mathi = lambda _p, _d, _s, _op, value: events.append(("done", value))
    monkeypatch.setattr(module, "_declare_common", lambda _p: None)
    monkeypatch.setattr(module, "_reserved_registers", lambda *_: set())
    monkeypatch.setattr(module, "resident_control_names", lambda _cfg, names: names)
    monkeypatch.setattr(module, "allocate_named_registers",
                        lambda *_a, **_kw: {"address": 1, "shot_loop": 2, "done": 3})
    program.make_program()
    assert [event for event in events if event[0] == "emit"] == [
        ("emit", "cold_on"), ("emit", "hot_on"), ("emit", "hot_off")]
    assert events.count("boundary") == 1
    assert events.count(("recovery", 1000.0)) == 5
    assert ("done", 3) in events
    assert next(event[1] for event in events if event[0] == "stream")["records_per_unit"] == 3


def test_raw_iq_score_uses_only_ground_heralded_second_readout():
    module = experiment()
    records = [module.heralded.PairedIQ(-2, 0, -2, 0),
               module.heralded.PairedIQ(-2, 0, 2, 0),
               module.heralded.PairedIQ(2, 0, 99, 0)]
    axes = {"herald": {"theta_rad": 0.0, "ground_limit": 0.0},
            "final": {"theta_rad": 0.0, "threshold": 0.0}}
    value = module.projected_final_given_ground(records, axes,
                                                 ground_level=-2.0,
                                                 excited_level=2.0)
    assert value == pytest.approx(.5)


def test_post_scout_rejects_disappeared_weak_site():
    module = experiment()
    pre = module.select_weak_sites(scout_rows(), max_sites=1)[0]
    post = scout_rows()
    indexed = {float(row["target_frequency_ghz"]): row for row in post}
    for frequency in (3.948, 3.950, 3.952):
        for suffix in ("", "_scan_up", "_scan_down"):
            indexed[frequency][f"Ps_25us{suffix}"] = ".82"
            indexed[frequency][f"Ps_10us{suffix}"] = ".82"
    assert module.post_site_stability(post, pre)["stable"] is False


def test_plan_is_hardware_free_and_names_intermediate_readout_limit(capsys):
    module = experiment()
    assert module.main(["--plan"]) == 0
    import json
    plan = json.loads(capsys.readouterr().out)
    assert plan["hardware_access"] is False
    assert plan["maximum_weak_sites"] == 3
    assert plan["conditions_per_shot"] == 3
    assert plan["additional_waits_us"] == [100.0, 300.0, 1000.0]
    assert plan["full_return_before_each_readout_us"] == 40.0
    assert plan["logical_shot_recovery_us"] == 5000.0
    assert "readout" in plan["interpretation_limit"].lower()
