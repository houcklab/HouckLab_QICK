import math

import pytest

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSEchoSquareMap as square,
)


def test_blind_grid_covers_whole_band_without_loss_selection():
    assert len(square.FREQUENCIES_GHZ) == 126
    assert square.FREQUENCIES_GHZ[0] == 4.3
    assert square.FREQUENCIES_GHZ[-1] == 3.8
    assert all(round(1000 * (a - b)) == 4 for a, b in zip(
        square.FREQUENCIES_GHZ, square.FREQUENCIES_GHZ[1:]))


def test_echo_duration_counts_three_short_pulses_and_delay():
    assert square.echo_window_us(.3) == pytest.approx(
        2 * .045 + .0907 + 3 * .01 + .3)
    assert square.echo_window_us(1.8) > square.echo_window_us(.3)
    with pytest.raises(ValueError):
        square.echo_window_us(-.1)


def test_target_echo_keeps_flux_hold_through_all_three_pulses(monkeypatch):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse

    events = []

    class Parent:
        cfg = {"echo_delay_us": .9, "ff_park_gain": -25146,
               "ff_gain": -18000, "opx_resident_pre_us": 30.,
               "opx_resident_post_us": .1, "opx_resident_freq_mhz": 4102.5,
               "qubit_ch": 1, "echo_phase_deg": 270}
        _t1_ff_compensation = {"test": True}
        _t1_ff_settle_us = .5
        _t1_ff_predistortion_recovery_us = 40.

        def us2cycles(self, value, gen_ch=None): return value
        def sync_all(self, value): events.append(("sync", value))
        def freq2reg(self, value, gen_ch): return value
        def deg2reg(self, value, gen_ch): return value
        def set_pulse_registers(self, **kwargs): events.append(("register", kwargs))
        def pulse(self, ch): events.append(("pulse", ch))

    def segments(_, hold_us, recovery_us):
        assert hold_us == pytest.approx(30.5 + square.echo_window_us(.9) + .1)
        assert recovery_us == 40.
        return [(1., hold_us)], [(0., 40.)]

    monkeypatch.setattr(ff_pulse, "compensation_round_trip_segments", segments)
    monkeypatch.setattr(ff_pulse, "play_relative_compensation_segments",
                        lambda *args: events.append(("flux", args[-1])))
    monkeypatch.setattr(ff_pulse, "play_hard_step",
                        lambda *args: events.append(("park", args[-1])))
    square.make_echo_program(Parent)()._resident_excursion()
    registers = [event[1] for event in events if event[0] == "register"]
    assert [entry["phase"] for entry in registers] == [0, 0, 270]
    assert [entry["length"] for entry in registers] == [.045, .0907, .045]
    assert all(entry["style"] == "const" for entry in registers)
    assert max(i for i, event in enumerate(events) if event[0] == "pulse") < min(
        i for i, event in enumerate(events) if event[0] == "park")


def test_phase_control_rejects_weak_local_pulse_axis():
    good = {0: .94, 90: .29, 180: .07, 270: .71}
    assert square.control_gate(good)["valid"]
    assert square.control_stability_gate(good, good)["valid"]
    assert not square.control_gate({0: .53, 90: .49, 180: .47, 270: .51})["valid"]
    assert square.control_gate({0: 1.02, 90: .29, 180: -.02, 270: .71})["valid"]
    opposite = {0: .07, 90: .71, 180: .94, 270: .29}
    assert not square.control_stability_gate(good, opposite)["valid"]


def test_schedule_brackets_echo_by_reverse_phase_controls():
    schedule = square.site_schedule(0)
    assert [kind for kind, _, _ in schedule[:4]] == ["control_pre"] * 4
    assert [kind for kind, _, _ in schedule[-4:]] == ["control_post"] * 4
    assert {delay for kind, delay, _ in schedule if kind == "echo"} == {
        .3, .9, 1.8}
    assert [phase for _, _, phase in schedule[:4]] == [0, 90, 180, 270]
    assert [phase for _, _, phase in schedule[-4:]] == [270, 180, 90, 0]


def test_echo_report_uses_phase_visibility_and_does_not_claim_tls_dephasing():
    short = {0: .8, 90: .5, 180: .2, 270: .5}
    middle = {0: .71, 90: .5, 180: .29, 270: .5}
    long = {0: .65, 90: .5, 180: .35, 270: .5}
    report = square.echo_report({.3: short, .9: middle, 1.8: long})
    assert report["status"] == "resolved"
    assert report["echo_rate_per_us"] == pytest.approx(math.log(2) / 1.5)
    assert "tls_dephasing_rate_per_us" not in report
    assert square.echo_report({.3: long, .9: middle, 1.8: short})["status"] == "nondecaying"
    assert square.echo_report({.3: short, .9: long, 1.8: middle})[
        "status"] == "nonmonotonic"
