"""Contracts for switching q3 loss within one target visit."""

import importlib
import json

import numpy as np
import pytest


MODULE = "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSFloquetSwitch"


def experiment():
    return importlib.import_module(MODULE)


def _synthetic_wide_rows(*, dips):
    rows = []
    for index in range(251):
        frequency = round(3.8 + .002 * index, 3)
        survival = .75
        for center, depth in dips:
            if abs(frequency - center) <= .002001:
                survival -= depth
        rows.append({"target_frequency_ghz": frequency,
                     "survival": survival})
    return rows


def test_switch_selector_prefers_old_feature_when_it_is_still_qualified(monkeypatch):
    module = experiment()
    monkeypatch.setattr(module.adaptive, "_survival",
                        lambda row, _direction="": row["survival"])
    rows = _synthetic_wide_rows(dips=((3.992, .3), (4.106, .5)))
    selected = module.select_switch_candidate(rows, preferred_center=3.992)
    assert abs(selected["center_ghz"] - 3.992) <= .004


def test_switch_selector_follows_strong_fresh_4p1_feature(monkeypatch):
    module = experiment()
    monkeypatch.setattr(module.adaptive, "_survival",
                        lambda row, _direction="": row["survival"])
    rows = _synthetic_wide_rows(dips=((4.106, .5), (3.942, .2)))
    selected = module.select_switch_candidate(rows, preferred_center=3.992)
    assert selected["center_ghz"] == pytest.approx(4.106)
    assert selected["depth"] > .4
    with pytest.raises(ValueError, match="no qualified loss"):
        module.select_switch_candidate(_synthetic_wide_rows(dips=()),
                                       preferred_center=3.992)


def test_switch_waveforms_share_dc_and_equal_on_time_without_clipping():
    module = experiment()
    args = dict(segments=[(1.0, 1.8), (1.01, 1.8)],
                park_gain=-25146, target_gain=-15000,
                amplitude_dac=1000, modulation_mhz=30.0,
                sample_rate_mhz=6881.28, fabric_rate_mhz=430.08,
                cycles=1548, max_gain=32767)
    waves = {name: module.switch_waveform(pattern=name, **args)[0]
             for name in module.PATTERNS}
    assert {len(wave) for wave in waves.values()} == {24768}
    assert waves["off"][0] == waves["on"][0]
    assert np.array_equal(waves["early"][:12384], waves["on"][:12384])
    assert np.array_equal(waves["early"][12384:], waves["off"][12384:])
    assert np.array_equal(waves["late"][:12384], waves["off"][:12384])
    assert np.array_equal(waves["late"][12384:], waves["on"][12384:])
    assert all(wave.min() >= -26146 and wave.max() <= -13000
               for wave in waves.values())
    assert sum(waves["early"] != waves["off"]) == \
        sum(waves["late"] != waves["off"])


def test_phase_scramble_preserves_cycle_amplitude_and_changes_order():
    module = experiment()
    args = dict(segments=[(1.0, 1.8), (1.01, 1.8)],
                park_gain=-25146, target_gain=-15000,
                amplitude_dac=1000, modulation_mhz=30.0,
                sample_rate_mhz=6881.28, fabric_rate_mhz=430.08,
                cycles=1548, max_gain=32767)
    off, _ = module.switch_waveform(pattern="off", **args)
    on, _ = module.switch_waveform(pattern="on", **args)
    scrambled, report = module.switch_waveform(
        pattern="phase_scrambled", **args)
    signs = report["phase_signs"]
    assert len(signs) == report["cycles_per_waveform"] == 108
    assert signs.count(1) == signs.count(-1) == 54
    assert np.array_equal(scrambled - off, (on - off) *
                          np.asarray(signs)[np.arange(len(on)) * 108 // len(on)])
    assert not np.array_equal(scrambled, on)
    assert np.max(np.abs(scrambled)) <= 32767
    assert abs(np.mean(scrambled - off) - np.mean(on - off)) < 1
    assert abs(np.std(scrambled - off) - np.std(on - off)) < 1
    assert np.array_equal(np.sort(scrambled - off), np.sort(on - off))


def test_switch_specs_pair_patterns_and_reverse_order_after_fresh_scout():
    module = experiment()
    specs = module.program_specs(3.992, shots=8000)
    assert [(s["repeat"], s["pair"]) for s in specs] == [
        (0, "reference"), (0, "switch"),
        (1, "switch"), (1, "reference")]
    assert [s["order"] for s in specs] == [
        ["off_g", "off_e", "on_g", "on_e"],
        ["early_g", "early_e", "late_g", "late_e"],
        ["late_e", "late_g", "early_e", "early_g"],
        ["on_e", "on_g", "off_e", "off_g"]]
    module.recenter_repeat(specs, center=3.994, repeat=1)
    assert [s["flux_ghz"] for s in specs] == [3.992, 3.992, 3.994, 3.994]
    assert all(c["post_drive_us"] == module.HOLD_US
               for spec in specs for c in spec["conditions"])


def test_phase_order_specs_and_score():
    module = experiment()
    specs = module.program_specs(4.106, shots=8000, phase_order=True)
    assert [(s["repeat"], s["pair"], s["patterns"]) for s in specs] == [
        (0, "reference", ["off", "on"]),
        (0, "phase", ["on", "phase_scrambled"]),
        (1, "phase", ["on", "phase_scrambled"]),
        (1, "reference", ["off", "on"])]
    values = {"off_g": .1, "off_e": .5,
              "on_g": .1, "on_e": .56,
              "phase_scrambled_g": .1, "phase_scrambled_e": .53}
    score = module.score_phase_patterns(values)
    assert score["on_minus_off_contrast"] == pytest.approx(.06)
    assert score["scrambled_minus_on_contrast"] == pytest.approx(-.03)
    assert score["usable"] is True
    phase_values = {"on_g": .1, "on_e": .50,
                    "phase_scrambled_g": .1,
                    "phase_scrambled_e": .53}
    paired = module.score_phase_patterns(values, phase_values)
    assert paired["on_minus_off_contrast"] == pytest.approx(.06)
    assert paired["scrambled_minus_on_contrast"] == pytest.approx(.03)


def test_switch_score_uses_hot_minus_cold_and_rejects_heating():
    module = experiment()
    values = {"off_g": .1, "off_e": .3,
              "on_g": .11, "on_e": .43,
              "early_g": .1, "early_e": .35,
              "late_g": .1, "late_e": .38}
    score = module.score_patterns(values)
    assert score["on_minus_off_contrast"] == pytest.approx(.12)
    assert score["late_minus_early_contrast"] == pytest.approx(.03)
    assert score["ground_spread"] == pytest.approx(.01)
    assert score["usable"] is True
    values["late_g"] = .25
    assert module.score_patterns(values)["usable"] is False


def test_switch_plan_and_memory_fit_q3_generator(capsys):
    module = experiment()
    p = module.plan()
    assert p["patterns"] == ["off", "on", "early", "late"]
    assert p["modulation_frequency_mhz"] == 30.0
    assert p["amplitude_dac"] == 1000
    assert p["hold_us"] == 3.6
    assert p["switch_us"] == 1.8
    assert p["programs"] == 4
    assert p["conditions_per_shot"] == 4
    assert (2 * p["park_ramp_us"] + 2 * p["hold_us"]) * 6881.28 < 65536
    assert module.main(["--plan"]) == 0
    assert json.loads(capsys.readouterr().out)["hardware_access"] is False
    assert module.main(["--plan", "--phase-order"]) == 0
    phase_plan = json.loads(capsys.readouterr().out)
    assert phase_plan["patterns"] == ["off", "on", "phase_scrambled"]
    assert phase_plan["phase_scramble_seed"] == 260929


@pytest.mark.parametrize("patterns", [("early", "late"),
                                      ("on", "phase_scrambled")])
def test_switch_program_compiles_only_two_patterns_with_memory_guard(
        monkeypatch, patterns):
    module = experiment()
    monkeypatch.setattr(
        module.alternating.ShotAlternatingResidentProgram,
        "_declare_experiment", lambda self: None)
    monkeypatch.setattr(module.modulated, "_target_segments",
                        lambda _correction, *, pre_us, hold_us, recovery_us:
                        ([(1.0, pre_us)], [(1.0, hold_us + .01)],
                         [(1.0, recovery_us)]))
    monkeypatch.setattr(module, "ff_maxv", lambda *_args, **_kw: 32767)
    monkeypatch.setattr(module, "ff_envelope_samples", lambda *_args: 65536)
    program = object.__new__(module.SwitchProgram)
    program.cfg = {"ff_ch": 0, "ff_gain": -15000,
                   "ff_park_gain": -25146}
    program.soccfg = {"gens": [{"fs": 6881.28, "f_fabric": 430.08}]}
    program.patterns = patterns
    program._t1_ff_compensation = object()
    program._t1_ff_settle_us = .5
    program._t1_ff_predistortion_recovery_us = 40.
    program._ff_ramp_cache = {(0, "up", 0, 6880),
                              (0, "down", 0, 6880)}
    program.us2cycles = lambda hold, **_kw: round(hold * 430.08)
    added = []
    program.add_pulse = lambda **kw: added.append(kw)
    program._declare_experiment()
    assert {row["name"] for row in added} == {
        f"q3_switch_{pattern}" for pattern in patterns}
    assert program.ff_envelope_report["total_samples"] == 2*24768 + 2*6880
    assert program.ff_envelope_report["total_samples"] < 65536
    assert all(row["idata"].dtype == np.int16 for row in added)


def test_switch_program_plays_selected_waveform_then_full_return(monkeypatch):
    module = experiment()
    monkeypatch.setattr(module.modulated, "_target_segments",
                        lambda _correction, *, pre_us, hold_us, recovery_us:
                        ([(1.0, pre_us)], [(1.0, hold_us)],
                         [(1.0, recovery_us)]))
    events = []
    monkeypatch.setattr(module.ff_pulse, "play_relative_compensation_segments",
                        lambda _program, _park, _target, segments:
                        events.append(("segments", segments)))
    monkeypatch.setattr(module.ff_pulse, "play_hard_step",
                        lambda _program, gain: events.append(("park", gain)))
    monkeypatch.setattr(module, "ff_maxv", lambda *_args, **_kw: 32767)
    program = object.__new__(module.SwitchProgram)
    program.cfg = {"ff_ch": 0, "ff_park_gain": -25146,
                   "ff_gain": -15000, "opx_resident_pre_us": .05,
                   "opx_switch_pattern": "late"}
    program._t1_ff_compensation = object()
    program._t1_ff_settle_us = .5
    program._t1_ff_predistortion_recovery_us = 40.
    program.set_pulse_registers = lambda **kw: events.append(("registers", kw))
    program.pulse = lambda **kw: events.append(("pulse", kw))
    program.sync_all = lambda *_args: None
    program._resident_excursion()
    assert events[1][1]["waveform"] == "q3_switch_late"
    assert events[-2] == ("segments", [(1.0, 40.)])
    assert events[-1] == ("park", -25146.)
