"""Checks for the bounded target-resident short-pulse pilot."""

import importlib
import math

import pytest


pilot = importlib.import_module(
    "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSEchoFastSquarePilot")


def test_duration_fit_resolves_first_turnover_and_pi_over_two():
    rows = [{"duration_us": time,
             "response": math.sin(math.pi * time / (2 * .28)) ** 2}
            for time in pilot.DURATIONS_US]
    fit = pilot.fit_duration_rabi(rows)
    assert fit["valid"]
    assert fit["pi_us"] == pytest.approx(.28, abs=.04)
    assert fit["pi2_us"] == pytest.approx(.14, abs=.03)


def test_duration_fit_rejects_monotonic_response():
    rows = [{"duration_us": time, "response": time}
            for time in pilot.DURATIONS_US]
    assert not pilot.fit_duration_rabi(rows)["valid"]


def test_source_is_pinned_to_target_phase_run():
    source = {"schema": "q3.target-pi2-validation.v1",
              "status": "complete_controls_unstable",
              "correction_sha256": pilot.localizer.CORRECTION_SHA256,
              "target_frequency_ghz": 4.288,
              "target_gain": -20130,
              "drive_frequency_mhz": 4290.5}
    assert pilot.validate_source(source) == (4.288, -20130, 4290.5)
    with pytest.raises(ValueError):
        pilot.validate_source({**source, "status": "running"})


def test_interleaved_zero_control_removes_linear_drift():
    anchors = [(0, 100 + 20j), (5, 200 + 40j), (10, 300 + 60j)]
    assert pilot.interpolated_zero(anchors, 3) == pytest.approx(160 + 32j)
    with pytest.raises(ValueError):
        pilot.interpolated_zero(anchors, 11)


def test_bracketed_phase_response_removes_linear_iq_drift():
    report = pilot.score_reference_bracket(
        0j, 1000 + 0j, 200 + 100j, 1200 + 100j)
    assert report["valid"]
    assert pilot.bracketed_response(
        600 + 50j, 0j, 1000 + 0j, 200 + 100j, 1200 + 100j,
        fraction=.5) == pytest.approx(.5)
    assert not pilot.score_reference_bracket(
        0j, 1000 + 0j, 0j, 300 + 0j)["valid"]


def test_square_pulses_play_inside_corrected_target_hold(monkeypatch):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse

    events = []

    class Parent:
        cfg = {"ff_park_gain": -25146, "ff_gain": -20130,
               "opx_resident_pre_us": 30., "opx_resident_post_us": .1,
               "fast_pulse_us": .14, "fast_second_phase_deg": 180,
               "qubit_ch": 1, "opx_resident_freq_mhz": 4290.5,
               "opx_resident_gain": 30000}
        _t1_ff_compensation = {"test": True}
        _t1_ff_settle_us = .5
        _t1_ff_predistortion_recovery_us = 40.

        def us2cycles(self, value, gen_ch=None): return value
        def sync_all(self, value): events.append(("sync", value))
        def freq2reg(self, value, gen_ch): return value
        def deg2reg(self, value, gen_ch): return value
        def set_pulse_registers(self, **kw): events.append(("register", kw))
        def pulse(self, ch): events.append(("pulse", ch))

    monkeypatch.setattr(ff_pulse, "compensation_round_trip_segments",
                        lambda _, hold_us, recovery_us:
                        ([(1., hold_us)], [(0., recovery_us)]))
    monkeypatch.setattr(ff_pulse, "play_relative_compensation_segments",
                        lambda *args: events.append(("flux", args[-1])))
    monkeypatch.setattr(ff_pulse, "play_hard_step",
                        lambda *args: events.append(("park", args[-1])))
    pilot.make_program(Parent)()._resident_excursion()
    regs = [value for kind, value in events if kind == "register"]
    assert len(regs) == 2
    assert [reg["phase"] for reg in regs] == [0, 180]
    assert all(reg["length"] == pytest.approx(.14) for reg in regs)
    assert events.index(("park", -25146)) > max(
        i for i, item in enumerate(events) if item[0] == "pulse")


def test_plan_has_no_wide_scout_or_echo_map():
    p = pilot.plan()
    assert p["gain_dac"] == 30000
    assert not p["fresh_t1_scan"]
    assert not p["wide_echo_map"]
