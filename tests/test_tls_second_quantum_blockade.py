"""Physics and timing contracts for the two-excitation q3 blockade test."""

import importlib

import pytest


MODULE = "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSecondQuantumBlockade"


def experiment():
    return importlib.import_module(MODULE)


def test_middle_pulse_crosses_all_visit_pairs_preparations_and_gains():
    module = experiment()
    specs = module.program_specs(4.106, 4.092)
    assert [entry["gap_us"] for entry in specs] == [2.0, 10.0, 10.0, 2.0]
    assert all(len(entry["conditions"]) == 16 for entry in specs)
    assert {tuple(c[key] for key in ("load_site", "probe_site", "state", "middle_pi"))
            for c in specs[0]["conditions"]} == {
        (first, second, state, middle)
        for first in "fc" for second in "fc" for state in "ge"
        for middle in (False, True)}
    assert specs[2]["order"] == list(reversed(specs[1]["order"]))
    split = module.split_records(list(range(32)), specs[0]["order"], shots=2)
    assert split[specs[0]["order"][0]] == [0, 16]
    with pytest.raises(ValueError, match="incomplete"):
        module.split_records(list(range(31)), specs[0]["order"], shots=2)


def test_middle_pi_is_scheduled_inside_continuously_compensated_park_gap(monkeypatch):
    module = experiment()
    compensation = {"segment_edges_ns": [0.0, 1_000.0],
                    "multipliers": [1.2, 1.0]}
    specs = module.program_specs(4.106, 4.092)
    lookup = {4.106: -16099, 4.092: -15861}
    condition = next(c for c in specs[0]["conditions"] if c["name"] == "ff_e_pi")
    cfg = module.arm_config({"sigma": .2, "ff_park_gain": -25146,
                             "qubit_ch": 2},
                            condition, lookup, shots=2)
    program = object.__new__(module.BlockadeProgram)
    program.cfg = cfg
    program._t1_ff_compensation = compensation
    program._t1_ff_predistortion_recovery_us = 40.0
    events = []
    monkeypatch.setattr(module.ff_pulse, "play_relative_compensation_segments",
                        lambda _program, _park, _target, segments:
                        events.append(("flux", list(segments))))
    monkeypatch.setattr(module.ff_pulse, "play_hard_step",
                        lambda _program, _gain: events.append(("park",)))
    monkeypatch.setattr(program, "sync_all", lambda _cycles: events.append(("sync",)),
                        raising=False)
    monkeypatch.setattr(program, "us2cycles", lambda us: round(us * 1000),
                        raising=False)
    monkeypatch.setattr(program, "_set_payload_pulse",
                        lambda *, gain=None: events.append(("gain", gain)),
                        raising=False)
    monkeypatch.setattr(program, "pulse", lambda *, ch, t:
                        events.append(("middle", ch, t)), raising=False)
    module.BlockadeProgram._resident_excursion(program)
    flux = [event[1] for event in events if event[0] == "flux"]
    assert len(flux) == 2
    assert sum(duration for _, duration in flux[0]) == pytest.approx(3.5)
    assert sum(duration for _, duration in flux[1]) == pytest.approx(41.5)
    assert events.index(("middle", cfg["qubit_ch"], 2000)) < events.index(("flux", flux[0]))
    assert events.index(("middle", cfg["qubit_ch"], 2000)) < events.index(("flux", flux[1]))
    assert ("gain", None) in events


def test_memoryless_transition_channels_factor_and_blockade_changes_only_pi_score():
    module = experiment()
    fractions = {
        "ff_e_pi": .2525, "ff_g_pi": .4775,
        "fc_e_pi": .3875, "fc_g_pi": .7625,
        "cf_e_pi": .1175, "cf_g_pi": .4775,
        "cc_e_pi": .1625, "cc_g_pi": .7625,
        "ff_e_sham": .2975, "ff_g_sham": .0725,
        "fc_e_sham": .4625, "fc_g_sham": .0875,
        "cf_e_sham": .4325, "cf_g_sham": .0725,
        "cc_e_sham": .6875, "cc_g_sham": .0875,
    }
    null = module.score(fractions)
    assert null["usable"]
    assert null["pi_blockade_excess"] == pytest.approx(0.0)
    assert null["pi_minus_sham_blockade_excess"] == pytest.approx(0.0)
    fractions["ff_e_pi"] += .06
    loaded = module.score(fractions)
    assert loaded["pi_blockade_excess"] == pytest.approx(.06)
    assert loaded["pi_minus_sham_blockade_excess"] == pytest.approx(.06)
    fractions["ff_e_pi"] += .24
    assert module.score(fractions)["pi_blockade_excess"] == pytest.approx(.30)
    assert module.score(fractions)["usable"]
    fractions["cc_g_pi"] = .1
    assert not module.score(fractions)["usable"]


def test_plan_exposes_one_measurement_only_and_no_intermediate_readout(capsys):
    import json
    module = experiment()
    assert module.main(["--plan"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["middle_pulse"] == "park pi or matched zero-gain sham"
    assert plan["load_us"] == 1.5
    assert plan["probe_us"] == 1.5
    assert plan["gaps_us"] == [2.0, 10.0]
    assert plan["intermediate_readouts"] == 0
    assert plan["conditions_per_shot"] == 16
