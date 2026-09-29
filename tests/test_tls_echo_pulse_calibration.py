"""Target-resident pi/2 calibration gates before another echo map."""

import importlib
import math

import pytest


cal = importlib.import_module(
    "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSEchoPulseCalibration")


def test_detuning_selector_uses_repeatable_single_pulse_excitation():
    rows = []
    for offset, peak in [(-5., .16), (0., .18), (5., .34)]:
        for gain, fraction in zip((4000, 8000, 12000, 16000),
                                  (.12, peak - .02, peak, .13)):
            rows.append({"offset_mhz": offset, "gain": gain,
                         "excited_fraction": fraction})
    chosen = cal.choose_detuning(rows, ground_fraction=.10)
    assert chosen["offset_mhz"] == 5.
    assert chosen["response"] > .20


def test_rabi_fit_finds_first_pi_and_pi_over_two_gains():
    gains = range(0, 30001, 1500)
    rows = [{"gain": gain,
             "excited_fraction": .1 + .35 * math.sin(
                 math.pi * gain / (2 * 12000)) ** 2}
            for gain in gains]
    fit = cal.fit_rabi(rows)
    assert fit["valid"]
    assert fit["pi_gain"] == pytest.approx(12000, abs=1500)
    assert fit["pi2_gain"] == pytest.approx(6000, abs=1500)


def test_rabi_fit_rejects_monotonic_response_without_pi_turnover():
    rows = [{"gain": gain, "excited_fraction": .1 + .00001 * gain}
            for gain in range(0, 30001, 1500)]
    assert not cal.fit_rabi(rows)["valid"]


def test_two_pulse_gate_requires_inversion_and_cancellation_in_both_orders():
    first = {0: .44, 90: .28, 180: .12, 270: .27}
    second = {270: .29, 180: .13, 90: .30, 0: .43}
    assert cal.two_pulse_gate(first, second, ground=.10, pi=.45)["valid"]
    weak = {0: .30, 90: .27, 180: .24, 270: .28}
    assert not cal.two_pulse_gate(first, weak, ground=.10, pi=.45)["valid"]


def test_validate_source_rejects_an_unrelated_run():
    source = {"schema": "q3.echo-dephasing-map.v1",
              "status": "stopped_quiet_pilot",
              "quiet_anchor": {"frequency_ghz": 4.288}}
    assert cal.validate_source(source) == 4.288
    with pytest.raises(ValueError):
        cal.validate_source({**source, "schema": "other"})


def test_plan_only_calibrates_one_target_pi_over_two_pulse():
    plan = cal.plan()
    assert plan["hardware_access"] is False
    assert plan["rabi_gain_sweep"]
    assert plan["two_pulse_phase_check"]
    assert plan["wide_echo_map"] is False


def test_double_pulse_program_applies_two_target_pi2_pulses_before_return(monkeypatch):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
    events = []

    class Parent:
        cfg = {"sigma": .2, "ff_park_gain": -25146, "ff_gain": -18000,
               "opx_resident_freq_mhz": 4293., "opx_resident_gain": 6500,
               "qubit_ch": 1, "rabi_second_phase_deg": 180}
        _t1_ff_compensation = {"test": True}
        _t1_ff_settle_us = .5
        _t1_ff_predistortion_recovery_us = 40.
        def us2cycles(self, value): return value
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
    cal.make_double_pulse_program(Parent)()._resident_excursion()
    registers = [item[1] for item in events if item[0] == "register"]
    assert [item["phase"] for item in registers] == [0, 180]
    assert all(item["gain"] == 6500 for item in registers)
    assert all(item["freq"] == 4293. for item in registers)
    assert events.index(("park", -25146)) > max(
        i for i, item in enumerate(events) if item[0] == "pulse")
