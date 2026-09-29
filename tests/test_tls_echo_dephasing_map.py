"""Regression tests for the bounded q3 target-resident echo map."""

import importlib
import math

import pytest


echo = importlib.import_module(
    "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSEchoDephasingMap"
)


def test_target_resident_echo_pulses_are_phase_cycled_and_timing_matched():
    events = []

    class Parent:
        cfg = {"sigma": .2, "echo_delay_us": 1.8,
               "ff_park_gain": -25146, "ff_gain": -25146,
               "opx_resident_freq_mhz": 4367.292,
               "qubit_ch": 1, "echo_pi2_gain": 13500,
               "echo_pi_gain": 27000, "echo_phase_deg": 270}
        def us2cycles(self, value): return value
        def sync_all(self, value): events.append(("sync", value))
        def freq2reg(self, value, gen_ch): return value
        def deg2reg(self, value, gen_ch): return value
        def set_pulse_registers(self, **kw): events.append(("register", kw))
        def pulse(self, ch): events.append(("pulse", ch))

    program = echo.make_program_class(Parent)()
    program._resident_excursion()
    registers = [e[1] for e in events if e[0] == "register"]
    assert [e["gain"] for e in registers] == [13500, 27000, 13500]
    assert [e["phase"] for e in registers] == [0, 0, 270]
    assert [e[1] for e in events if e[0] == "sync" and e[1] == .9] == [.9, .9]


def test_target_echo_keeps_qubit_at_target_until_final_pulse_then_returns(monkeypatch):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
    events = []

    class Parent:
        cfg = {"echo_delay_us": 1.8, "ff_park_gain": -25146,
               "ff_gain": -18000, "opx_resident_freq_mhz": 4106.,
               "qubit_ch": 1, "echo_pi2_gain": 13500,
               "echo_pi_gain": 27000, "echo_phase_deg": 90}
        _t1_ff_compensation = {"test": True}
        _t1_ff_settle_us = .5
        _t1_ff_predistortion_recovery_us = 40.
        def us2cycles(self, value): return value
        def sync_all(self, value): events.append(("sync", value))
        def freq2reg(self, value, gen_ch): return value
        def deg2reg(self, value, gen_ch): return value
        def set_pulse_registers(self, **kw): events.append(("register", kw))
        def pulse(self, ch): events.append(("pulse", ch))

    def segments(_, hold_us, recovery_us):
        assert hold_us == pytest.approx(33.63)
        assert recovery_us == 40
        return [(1., hold_us)], [(0., 40.)]

    monkeypatch.setattr(ff_pulse, "compensation_round_trip_segments", segments)
    monkeypatch.setattr(ff_pulse, "play_relative_compensation_segments",
                        lambda *args: events.append(("flux", args[-1])))
    monkeypatch.setattr(ff_pulse, "play_hard_step",
                        lambda *args: events.append(("park", args[-1])))
    echo.make_program_class(Parent)()._resident_excursion()
    first_pulse = next(i for i, event in enumerate(events) if event[0] == "pulse")
    last_pulse = max(i for i, event in enumerate(events) if event[0] == "pulse")
    flux_indices = [i for i, event in enumerate(events) if event[0] == "flux"]
    assert flux_indices[0] < first_pulse
    assert flux_indices[-1] > last_pulse
    assert events[-1] == ("sync", 0)
    assert ("park", -25146) in events


def test_phase_cycle_recovers_visibility_independent_of_echo_phase():
    report = echo.phase_cycle_visibility({
        0: .5, 90: .8, 180: .5, 270: .2,
    })
    assert report["visibility"] == pytest.approx(.6)
    assert report["x"] == pytest.approx(0)
    assert report["y"] == pytest.approx(.6)


def test_short_and_long_echo_contrast_yield_apparent_decay_rate():
    report = echo.echo_rate(.6, .3, short_us=.3, long_us=1.8)
    assert report["rate_per_us"] == pytest.approx(math.log(2) / 1.5)
    assert report["t2_echo_us"] == pytest.approx(1.5 / math.log(2))
    assert echo.echo_rate(.08, .03, short_us=.3, long_us=1.8)[
        "status"] == "unresolved_short_contrast"


def test_full_band_schedule_phase_cycles_both_delays_per_frequency():
    schedule = echo.science_schedule(shots=200)
    assert len(schedule) == 251
    assert schedule[0]["frequency_ghz"] == pytest.approx(4.3)
    assert schedule[-1]["frequency_ghz"] == pytest.approx(3.8)
    for row in schedule:
        arms = row["arms"]
        assert len(arms) == 8
        assert {(arm["delay_us"], arm["phase_deg"]) for arm in arms} == {
            (delay, phase) for delay in (.3, 1.8)
            for phase in (0, 90, 180, 270)}
        assert {arm["shots"] for arm in arms} == {200}
    assert schedule[0]["arms"][0]["phase_deg"] != schedule[1]["arms"][0]["phase_deg"]


def test_quiet_anchor_requires_measured_two_us_and_twenty_five_us_survival():
    rows = []
    for mhz in range(3800, 4301, 2):
        p2, p25 = (.85, .75)
        if mhz == 4298:
            p2, p25 = (.5, .3)
        rows.append({"target_frequency_ghz": str(mhz / 1000),
                     "P0": ".1", "P1": ".9",
                     "Ps_2us": str(.1 + .8 * p2),
                     "Ps_25us": str(.1 + .8 * p25)})
    anchor = echo.select_quiet_anchor(rows)
    assert 4.25 <= anchor["frequency_ghz"] <= 4.3
    assert anchor["frequency_ghz"] != 4.298
    assert anchor["survival_2us"] >= .75
    assert anchor["survival_25us"] >= .65


def test_quiet_anchor_prefers_valid_decay_over_noisy_above_one_survival():
    rows = [
        {"target_frequency_ghz": "4.260", "P0": ".1", "P1": ".5",
         "Ps_2us": ".49", "Ps_25us": ".52", "T1_5pt_valid_mask": "0.0"},
        {"target_frequency_ghz": "4.296", "P0": ".1", "P1": ".5",
         "Ps_2us": ".45", "Ps_25us": ".43", "T1_5pt_valid_mask": "1.0"},
    ]
    assert echo.select_quiet_anchor(rows)["frequency_ghz"] == 4.296


def test_quiet_anchor_can_fall_back_outside_high_band():
    rows = [
        {"target_frequency_ghz": "4.280", "P0": ".1", "P1": ".5",
         "Ps_2us": ".22", "Ps_25us": ".14"},
        {"target_frequency_ghz": "4.120", "P0": ".1", "P1": ".5",
         "Ps_2us": ".46", "Ps_25us": ".40"},
    ]
    assert echo.select_quiet_anchor(rows)["frequency_ghz"] == 4.120


def test_plan_declares_phase_gate_and_T1_comparison_without_hardware(capsys):
    assert echo.main(["--plan"]) == 0
    out = capsys.readouterr().out
    assert '"hardware_access": false' in out
    assert '"phase_axis_preflight": true' in out
    assert '"frequency_count": 251' in out
    assert '"target_resident_echo": true' in out


def test_arm_config_places_three_echo_pulses_at_target_after_settle():
    base = {"ff_park_gain": -25146, "qubit_pi_gain": 13500,
            "qubit_pi2_gain": 6750, "sigma": .2}
    cfg = echo.arm_config(base, target_gain=-18000,
                          frequency_ghz=4.106, delay_us=1.8,
                          phase_deg=270, shots=200)
    assert cfg["ff_gain"] == -18000
    assert cfg["opx_resident_pre_us"] == 30
    assert cfg["opx_resident_freq_mhz"] == 4106
    assert cfg["echo_phase_deg"] == 270
    assert cfg["echo_delay_us"] == pytest.approx(1.8)
    assert cfg["echo_pi_gain"] == 27000
    assert cfg["shots"] == cfg["reps"] == 200


def test_phase_gate_requires_a_replicated_park_fringe():
    strong = {0: .8, 90: .5, 180: .2, 270: .5}
    weak = {0: .55, 90: .5, 180: .45, 270: .5}
    assert echo.phase_gate(strong, strong, reference_contrast=.7)["valid"]
    assert not echo.phase_gate(strong, weak, reference_contrast=.7)["valid"]
    assert not echo.phase_gate(strong, strong, reference_contrast=.1)["valid"]


def test_point_report_separates_echo_visibility_from_t1_limited_decay():
    short = {0: .8, 90: .5, 180: .2, 270: .5}
    long = {0: .65, 90: .5, 180: .35, 270: .5}
    scout = {"P0": ".1", "P1": ".9", "Ps_2us": ".74",
             "Ps_25us": ".7"}
    report = echo.point_report({.3: short, 1.8: long}, scout)
    assert report["status"] == "resolved"
    assert report["echo_rate_per_us"] == pytest.approx(math.log(2) / 1.5)
    assert report["t1_rate_per_us"] == pytest.approx(-math.log(.8) / 2)
    assert report["excess_dephasing_rate_per_us"] == pytest.approx(
        math.log(2) / 1.5 + math.log(.8) / 4)


def test_point_report_marks_lost_short_echo_contrast_unresolved():
    weak = {0: .53, 90: .5, 180: .47, 270: .5}
    report = echo.point_report({.3: weak, 1.8: weak},
                               {"P0": ".1", "P1": ".9", "Ps_2us": ".8"})
    assert report["status"] == "unresolved_short_contrast"
    assert "excess_dephasing_rate_per_us" not in report


def test_point_report_prefers_valid_multidelay_t1_fit():
    short = {0: .8, 90: .5, 180: .2, 270: .5}
    long = {0: .65, 90: .5, 180: .35, 270: .5}
    scout = {"P0": ".1", "P1": ".9", "Ps_2us": ".74",
             "T1_5pt_valid_mask": "1.0", "inv_T1_5pt_per_us": ".125"}
    report = echo.point_report({.3: short, 1.8: long}, scout)
    assert report["t1_rate_per_us"] == pytest.approx(.125)
    assert report["t1_rate_source"] == "five_point_fit"
