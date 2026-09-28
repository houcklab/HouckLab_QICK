"""Contracts for the anchored q3 Floquet calibration stage."""

import importlib

import numpy as np
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


def test_periodic_only_plan_uses_stronger_probe_without_bessel_fit():
    description = experiment().plan(periodic_check_only=True)
    assert description["probe_gain_dac"] == 6000
    assert description["amplitudes_dac"] == [0, 1400]
    assert description["stage"] == "periodic_hardware_check"


def test_periodic_carrier_accepts_localized_peak_from_measured_run():
    module = experiment()
    fractions = [.116, .078, .104, .120, .148, .136, .154,
                 .196, .230, .186, .126, .096, .126, .112,
                 .096, .098, .070]
    assert module.periodic_carrier_valid(fractions, ground_fraction=.11,
                                         shots=500)
    assert not module.periodic_carrier_valid([.11] * 17,
                                             ground_fraction=.11, shots=500)
    assert not module.periodic_carrier_valid([.23] + [.11] * 16,
                                             ground_fraction=.11, shots=500)


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


def test_spectrum_summary_works_with_numpy_one_api(monkeypatch):
    module = experiment()
    arms = []
    for amplitude in module.AMPLITUDES_DAC:
        beta = 2.405 * amplitude / 1400
        for order in module.ORDERS:
            for offset in module.WINDOW_OFFSETS_MHZ:
                arms.append({"modulation_amplitude_dac": amplitude,
                             "order": order, "offset_mhz": offset,
                             "drive_mhz": 4010 + order * 30 + offset,
                             "excited_fraction_pre_axis": .1 +
                             .12 * jv(abs(order), beta)**2 *
                             np.exp(-.5 * (offset / 3)**2)})
    monkeypatch.delattr(module.np, "trapezoid", raising=False)
    fits = module.summarize_spectra(arms, ground_fraction=.1)
    assert fits["1400"]["beta"] == pytest.approx(2.405, abs=.02)


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


def test_periodic_check_selects_only_a_real_first_sideband():
    module = experiment()
    arms = module.periodic_scan_arms(4.006, 4010.0)
    assert len(arms) == 28
    assert all(arm["gain"] == 6000 for arm in arms)
    for arm in arms:
        arm["excited_fraction_pre_axis"] = .1
        if (arm["order"] == 1 and arm["offset_mhz"] == -2 and
                arm["modulation_amplitude_dac"] == 1400):
            arm["excited_fraction_pre_axis"] = .19
    chosen = module.select_periodic_sideband(arms)
    assert chosen == {"order": 1, "frequency_mhz": 4038.0,
                      "on_off_excess": pytest.approx(.09)}
    for arm in arms:
        arm["excited_fraction_pre_axis"] = .1
    with pytest.raises(ValueError, match="first sideband"):
        module.select_periodic_sideband(arms)


def test_periodic_pilot_resolves_small_sideband_with_enough_shots():
    module = experiment()
    arms = module.periodic_scan_arms(4.006, 4011.0)
    assert all(arm["shots"] == 4000 for arm in arms)
    for arm in arms:
        arm["excited_fraction_pre_axis"] = .10
        if (arm["order"] == 1 and arm["offset_mhz"] == -2 and
                arm["modulation_amplitude_dac"] == 1400):
            arm["excited_fraction_pre_axis"] = .133
    chosen = module.select_periodic_sideband(arms)
    assert chosen["frequency_mhz"] == pytest.approx(4039.0)
    assert chosen["on_off_excess"] == pytest.approx(.033)
    for arm in arms:
        arm["shots"] = 1000
    with pytest.raises(ValueError, match="first sideband"):
        module.select_periodic_sideband(arms)


def test_periodic_check_requires_late_sideband_not_just_early_response():
    module = experiment()
    assert module.periodic_response_valid(
        {"off": .10, "oneshot": .18, "early": .17, "late": .16})
    assert not module.periodic_response_valid(
        {"off": .10, "oneshot": .18, "early": .17, "late": .11})
    assert module.periodic_response_valid(
        {"off": .10, "oneshot": .132, "early": .131, "late": .130},
        shots=6000)
    assert not module.periodic_response_valid(
        {"off": .10, "oneshot": .132, "early": .131, "late": .130},
        shots=2000)


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
