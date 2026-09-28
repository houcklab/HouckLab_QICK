"""Contracts for the anchored q3 Floquet calibration stage."""

import importlib

import pytest
from scipy.special import jv


def experiment():
    return importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSFloquetStageA")


def test_plan_targets_stable_line_and_never_claims_science_result():
    plan = experiment().plan()
    assert plan["anchor_ghz"] == 3.992
    assert plan["modulation_mhz"] == pytest.approx(30.0056, rel=1e-3)
    assert plan["probe_gain_dac"] == 3000
    assert plan["stage"] == "calibration_only"
    assert plan["periodic_check"] == "early-versus-late first-sideband response"


def test_joint_sideband_weights_recover_bessel_index():
    module = experiment()
    beta = 2.405
    areas = {n: 1.7 * jv(abs(n), beta) ** 2
             for n in (-2, -1, 0, 1)}
    fit = module.fit_modulation_index(areas)
    assert fit["beta"] == pytest.approx(beta, abs=.015)
    assert fit["relative_residual"] < .01


def test_zero_estimate_requires_measured_bracket():
    module = experiment()
    with pytest.raises(ValueError, match="bracket"):
        module.estimate_zero_dac({0: 0.0, 800: 1.1, 1200: 1.8})
    estimate = module.estimate_zero_dac(
        {0: 0.0, 800: 1.2, 1200: 1.9, 1600: 2.8})
    assert 1200 < estimate < 1600


def test_mean_shift_uses_resolved_sidebands_when_carrier_is_dark():
    module = experiment()
    peaks = {
        "-2": {"frequency_mhz": 3949.0, "excess": .08, "interior": True},
        "-1": {"frequency_mhz": 3979.0, "excess": .12, "interior": True},
        "0": {"frequency_mhz": 4013.0, "excess": .01, "interior": True},
        "1": {"frequency_mhz": 4039.0, "excess": .12, "interior": True},
    }
    assert module.estimate_mean_shift_mhz(peaks, carrier_mhz=4011.0) == pytest.approx(-2.0)


def test_periodic_probe_requires_quiet_compensation_tail():
    module = experiment()
    with pytest.raises(ValueError, match="DC correction spread"):
        module.validate_periodic_baseline(
            [(1.0, 1.6), (1.01, 1.6)], park_gain=-25146,
            target_gain=-16000, max_spread_dac=20)
    assert module.validate_periodic_baseline(
        [(1.0, 1.6), (1.001, 1.6)], park_gain=-25146,
        target_gain=-16000, max_spread_dac=20) == pytest.approx(-16000)


def test_periodic_block_must_match_verified_24_cycle_waveform():
    module = experiment()
    with pytest.raises(ValueError, match="24-cycle"):
        module.validate_block_report({"duration_us": 1.0,
                                      "cycles_per_waveform": 30,
                                      "actual_modulation_mhz": 30.0})
    module.validate_block_report({"duration_us": .79985,
                                  "cycles_per_waveform": 24,
                                  "actual_modulation_mhz": 30.0056})


def test_periodic_probe_uses_repeating_arb_and_explicit_dc_recovery(monkeypatch):
    module = experiment()
    program = object.__new__(module.FloquetProbeProgram)
    program.cfg = {"ff_ch": 3, "qubit_ch": 1,
                   "ff_park_gain": -25146, "ff_gain": -16000,
                   "opx_resident_pre_us": 20.0,
                   "opx_resident_post_us": .1,
                   "opx_resident_freq_mhz": 4011.0,
                   "opx_resident_gain": 3000,
                   "opx_floquet_periodic_position": "late"}
    program._t1_ff_compensation = object()
    program._t1_ff_settle_us = .5
    program._t1_ff_predistortion_recovery_us = 40.0
    program.modulation_waveform_report = {"duration_us": .8,
                                          "baseline_gain": -16000}
    program.soccfg = {"gens": [{}, {}, {}, {"maxv": 32767}]}
    events = []
    program.set_pulse_registers = lambda **kw: events.append(("regs", kw))
    program.pulse = lambda **kw: events.append(("pulse", kw["ch"]))
    program.sync_all = lambda *args: events.append(("sync", args))
    program.us2cycles = lambda value, **kw: value
    program.freq2reg = lambda value, **kw: value
    program.deg2reg = lambda value, **kw: value
    monkeypatch.setattr(module, "ff_maxv", lambda *_a: 32767)
    monkeypatch.setattr(module.ff_pulse, "compensation_round_trip_segments",
                        lambda *_a, **_kw: ([(1.0, 20.5),
                                                (1.0, 3.2), (1.0, .1)],
                                               [(0.0, 40.0)]))
    monkeypatch.setattr(module.ff_pulse, "split_compensation_segments",
                        lambda segments, duration: (
                            [(1.0, duration)],
                            [(1.0, sum(x[1] for x in segments)-duration)]))
    monkeypatch.setattr(module.ff_pulse, "play_relative_compensation_segments",
                        lambda *_a: events.append("dc_segment"))
    monkeypatch.setattr(module.ff_pulse, "play_hard_step",
                        lambda *_a: events.append("park"))

    program._resident_excursion()

    ff = next(event[1] for event in events if isinstance(event, tuple)
              and event[0] == "regs" and event[1]["ch"] == 3
              and event[1].get("style") == "arb")
    assert ff["mode"] == "periodic"
    assert events.index(("pulse", 3)) < events.index(("pulse", 1))
    assert events.index(("pulse", 1)) < events.index("park")
    assert events[-1][0] == "sync"
