"""Physics and timing contracts for the two-excitation q3 blockade test."""

import importlib
import math

import pytest


MODULE = "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSecondQuantumBlockade"


def experiment():
    return importlib.import_module(MODULE)


def test_middle_pulse_crosses_all_visit_pairs_preparations_and_gains():
    module = experiment()
    specs = module.program_specs(4.106, 4.092)
    assert [entry["gap_us"] for entry in specs] == [
        2.0] * 4 + [10.0] * 8 + [2.0] * 4
    assert [entry["middle_phase_deg"] for entry in specs] == [
        0.0, 90.0, 180.0, 270.0] * 2 + [270.0, 180.0, 90.0, 0.0] * 2
    assert all(len(entry["conditions"]) == 16 for entry in specs)
    assert {tuple(c[key] for key in ("load_site", "probe_site", "state", "middle_pi"))
            for c in specs[0]["conditions"]} == {
        (first, second, state, middle)
        for first in "fc" for second in "fc" for state in "ge"
        for middle in (False, True)}
    assert specs[8]["order"] == list(reversed(specs[4]["order"]))
    split = module.split_records(list(range(32)), specs[0]["order"], shots=2)
    assert split[specs[0]["order"][0]] == [0, 16]
    with pytest.raises(ValueError, match="incomplete"):
        module.split_records(list(range(31)), specs[0]["order"], shots=2)


@pytest.mark.parametrize("program_index, condition_name, expected_gain, expected_phase", [
    (0, "ff_e_pi", 13500, 0.0),
    (1, "ff_e_pi", 13500, 90.0),
    (2, "ff_e_pi", 13500, 180.0),
    (3, "ff_e_sham", 0, 270.0),
])
def test_middle_pi_is_scheduled_inside_continuously_compensated_park_gap(
        monkeypatch, program_index, condition_name, expected_gain, expected_phase):
    module = experiment()
    compensation = {"segment_edges_ns": [0.0, 1_000.0],
                    "multipliers": [1.2, 1.0]}
    specs = module.program_specs(4.106, 4.092)
    lookup = {4.106: -16099, 4.092: -15861}
    condition = next(c for c in specs[program_index]["conditions"]
                     if c["name"] == condition_name)
    cfg = module.arm_config({"sigma": .2, "ff_park_gain": -25146,
                             "qubit_ch": 2, "qubit_pi_gain": 13500,
                             "qubit_pi_freq": 4367.292,
                             "qubit_freq": 4367.292},
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
    monkeypatch.setattr(program, "freq2reg", lambda frequency, *, gen_ch: frequency,
                        raising=False)
    monkeypatch.setattr(program, "deg2reg", lambda degrees, *, gen_ch: degrees,
                        raising=False)
    monkeypatch.setattr(program, "set_pulse_registers", lambda **kwargs:
                        events.append(("registers", kwargs)), raising=False)
    monkeypatch.setattr(program, "pulse", lambda *, ch, t:
                        events.append(("middle", ch, t)), raising=False)
    module.BlockadeProgram._resident_excursion(program)
    flux = [event[1] for event in events if event[0] == "flux"]
    assert len(flux) == 2
    assert sum(duration for _, duration in flux[0]) == pytest.approx(3.5)
    assert sum(duration for _, duration in flux[1]) == pytest.approx(41.5)
    assert events.index(("middle", cfg["qubit_ch"], 2000)) < events.index(("flux", flux[0]))
    assert events.index(("middle", cfg["qubit_ch"], 2000)) < events.index(("flux", flux[1]))
    registers = next(item[1] for item in events if item[0] == "registers")
    assert registers["gain"] == expected_gain
    assert registers["phase"] == expected_phase


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


def test_phase_averaged_primary_score_rejects_memoryless_coherent_rotations():
    module = experiment()
    specs = module.program_specs(4.106, 4.092)
    # Coherent X rotations violate population factorization in each arm.
    # Averaging pi phases 0/90 removes the first visit's qubit coherence.
    angles = {"f": .5, "c": .1}
    for entry in specs:
        phase = entry["middle_phase_deg"]
        for cond in entry["conditions"]:
            a, b = angles[cond["load_site"]], angles[cond["probe_site"]]
            if cond["middle_pi"]:
                contrast = (-math.cos(a + b) if phase in (0.0, 180.0)
                            else -math.cos(a - b))
            else:
                contrast = math.cos(a + b)
            cond["excited_fraction_pre_axis"] = (
                (1.0 + contrast) / 2.0 if cond["state"] == "e"
                else (1.0 - contrast) / 2.0)
    result = module.report(specs)
    assert result["usable"]
    for gap in ("2.0", "10.0"):
        assert len(result[gap]["cycle_scores"]) == 2
        assert all(abs(item["pi_blockade_excess"]) < 1e-12
                   for item in result[gap]["cycle_scores"])


@pytest.mark.parametrize("rotation_deg", [120.0, 155.0])
def test_imperfect_middle_pi_cannot_pass_quiet_inversion_check(rotation_deg):
    module = experiment()
    specs = module.program_specs(4.106, 4.092)
    angles = {"f": 1.0, "c": 0.0}
    theta = math.radians(rotation_deg)
    for entry in specs:
        for cond in entry["conditions"]:
            a, b = angles[cond["load_site"]], angles[cond["probe_site"]]
            if not cond["middle_pi"]:
                contrast = math.cos(a + b)
            elif entry["middle_phase_deg"] == 0.0:
                contrast = math.cos(a + b + theta)
            elif entry["middle_phase_deg"] == 180.0:
                contrast = math.cos(a + b - theta)
            else:
                contrast = (-math.sin(a) * math.sin(b) +
                            math.cos(theta) * math.cos(a) * math.cos(b))
            cond["excited_fraction_pre_axis"] = (
                (1.0 + contrast) / 2.0 if cond["state"] == "e"
                else (1.0 - contrast) / 2.0)
    report = module.report(specs)
    assert not report["usable"]


def test_park_middle_calibration_rejects_underrotation_before_science():
    module = experiment()
    specs = module.calibration_specs()
    assert len(specs) == 2
    assert all(len(entry["conditions"]) == 16 for entry in specs)
    assert {c["phase_deg"] for c in specs[0]["conditions"]} == {
        0.0, 90.0, 180.0, 270.0}
    for condition in specs[0]["conditions"]:
        condition["excited_fraction_pre_axis"] = (
            .85 if condition["state"] == "e" and not condition["middle_pi"] else
            .15 if condition["state"] == "g" and not condition["middle_pi"] else
            .15 if condition["state"] == "e" else .85)
    assert module.calibration_score(specs[0])["usable"]
    assert module.calibration_score(specs[0])["tight_inversion"]
    for condition in specs[0]["conditions"]:
        if condition["middle_pi"]:
            condition["excited_fraction_pre_axis"] = (
                .183 if condition["state"] == "e" else .817)
    near = module.calibration_score(specs[0])
    assert near["usable"]
    assert not near["tight_inversion"]
    for condition in specs[0]["conditions"]:
        if condition["middle_pi"]:
            condition["excited_fraction_pre_axis"] = (
                .325 if condition["state"] == "e" else .675)
    assert not module.calibration_score(specs[0])["usable"]
    assert not module.calibration_score(specs[0])["tight_inversion"]


def test_park_calibration_pulse_timing_and_phase(monkeypatch):
    module = experiment()
    condition = next(c for c in module.calibration_specs()[0]["conditions"]
                     if c["name"] == "phase270_e_pi")
    cfg = module.calibration_config(
        {"sigma": .2, "ff_park_gain": -25146, "qubit_ch": 2,
         "qubit_pi_gain": 13500, "qubit_pi_freq": 4367.292},
        condition, 4.092, {4.092: -15861}, shots=3)
    assert cfg["ff_gain"] == -25146
    program = object.__new__(module.ParkMiddleCalibrationProgram)
    program.cfg = cfg
    events = []
    monkeypatch.setattr(program, "us2cycles", lambda us: round(us * 1000),
                        raising=False)
    monkeypatch.setattr(program, "sync_all", lambda cycles:
                        events.append(("sync", cycles)), raising=False)
    monkeypatch.setattr(program, "freq2reg", lambda mhz, *, gen_ch: mhz,
                        raising=False)
    monkeypatch.setattr(program, "deg2reg", lambda deg, *, gen_ch: deg,
                        raising=False)
    monkeypatch.setattr(program, "set_pulse_registers", lambda **kwargs:
                        events.append(("registers", kwargs)), raising=False)
    monkeypatch.setattr(program, "pulse", lambda *, ch, t:
                        events.append(("pulse", ch, t)), raising=False)
    module.ParkMiddleCalibrationProgram._resident_excursion(program)
    assert events[0] == ("sync", 0)
    registers = events[1][1]
    assert registers["gain"] == 13500
    assert registers["phase"] == 270.0
    assert events[2] == ("pulse", 2, 2000)
    assert events[-1] == ("sync", 2200)


def test_failed_pre_transfer_control_aborts_before_science():
    module = experiment()
    with pytest.raises(RuntimeError, match="pre-run transfer"):
        module.validate_pre_transfer({"ground": .40, "excited": .48})
    module.validate_pre_transfer({"ground": .12, "excited": .62})


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
    assert plan["programs"] == 16
    assert plan["park_middle_calibration_programs"] == 2
