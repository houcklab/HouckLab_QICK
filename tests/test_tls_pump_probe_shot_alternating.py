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


def test_program_counts_four_records_before_one_stream_boundary(monkeypatch):
    module = experiment()
    program = object.__new__(module.ShotAlternatingResidentProgram)
    program.cfg = {"qubit_ch": 1}
    program.condition_cfgs = [{"condition": x} for x in range(4)]
    program.reps, program.record_base, program.done_addr = 3, 32, 1
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
