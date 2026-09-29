"""Contracts for the bounded q3 J0-minimum loss pilot."""

import importlib

import numpy as np
import pytest


def experiment():
    return importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSFloquetJ0Pilot")


def test_plan_uses_two_integer_cycle_frequencies_and_bracketed_static_profiles():
    p = experiment().plan()
    assert p["modulation_frequencies_mhz"] == [5.0, 10.0]
    assert p["beta_targets"] == [1.8, pytest.approx(2.4048255577), 3.0]
    assert p["holds_us"] == [1.6, 5.6]
    assert p["static_offsets_mhz"] == [-2.0, 0.0, 2.0]
    assert p["static_profiles_per_block"] == 2
    assert p["reset_mode"] == "passive"


def test_amplitude_schedule_uses_local_static_slope_but_labels_it_estimated():
    module = experiment()
    settings = module.amplitude_settings(0.070)
    assert len(settings) == 6
    assert [(x["modulation_mhz"], x["beta_target"])
            for x in settings] == [
                (5.0, 1.8), (5.0, module.J0_ZERO), (5.0, 3.0),
                (10.0, 1.8), (10.0, module.J0_ZERO), (10.0, 3.0)]
    assert [x["amplitude_dac"] for x in settings] == [
        129, 172, 214, 257, 344, 429]
    assert all(x["beta_estimate_source"] == "static_flux_slope_unverified_ac_transfer"
               for x in settings)
    assert all(x["amplitude_dac"] < 1000 for x in settings)


@pytest.mark.parametrize("slope", [0, float("nan"), 0.001])
def test_amplitude_schedule_rejects_unusable_local_slope(slope):
    with pytest.raises(ValueError, match="slope|range"):
        experiment().amplitude_settings(slope)


def test_program_schedule_reverses_amplitude_order_and_brackets_each_block():
    module = experiment()
    specs = module.program_specs(4.106, module.amplitude_settings(0.070),
                                 shots=100)
    assert len(specs) == 16
    assert [x["kind"] for x in specs] == (
        ["static"] + ["ac"] * 6 + ["static"] +
        ["static"] + ["ac"] * 6 + ["static"])
    assert [x["amplitude_dac"] for x in specs[1:7]] == [
        129, 172, 214, 257, 344, 429]
    assert [x["amplitude_dac"] for x in specs[9:15]] == [
        429, 344, 257, 214, 172, 129]
    assert all(len(x["conditions"]) == 8 for x in specs if x["kind"] == "ac")
    assert all(len(x["conditions"]) == 12 for x in specs if x["kind"] == "static")
    module.recenter_repeat(specs, center=4.108, repeat=1)
    assert all(x["center_ghz"] == 4.108 for x in specs if x["repeat"] == 1)
    assert all(x["center_ghz"] == 4.106 for x in specs if x["repeat"] == 0)
    assert {c["flux_ghz"] for x in specs if x["repeat"] == 1
            and x["kind"] == "static" for c in x["conditions"]} == {
                4.106, 4.108, 4.110}


def test_static_profile_stream_is_complete_and_rejects_missing_records():
    module = experiment()
    spec = module.program_specs(4.106, module.amplitude_settings(0.070),
                                shots=2)[0]
    records = list(range(24))
    split = module.split_records(records, spec["order"], shots=2)
    assert all(len(value) == 2 for value in split.values())
    with pytest.raises(ValueError, match="incomplete"):
        module.split_records(records[:-1], spec["order"], shots=2)


def test_local_slope_uses_symmetric_static_flux_fit():
    module = experiment()
    def linear(_fit, gains):
        return 4.0 + np.asarray(gains) * 0.000070
    assert module.local_static_slope_mhz_per_dac(
        object(), -15000, estimator=linear) == pytest.approx(.070)


def test_compiled_ac_pair_has_whole_cycles_and_fits_q3_envelope_budget(monkeypatch):
    module = experiment()
    modulated = module.modulated
    monkeypatch.setattr(
        modulated.alternating.ShotAlternatingResidentProgram,
        "_declare_experiment", lambda self: None)
    monkeypatch.setattr(modulated, "_target_segments",
                        lambda _correction, *, pre_us, hold_us, recovery_us:
                        ([(1.0, pre_us)], [(1.0, hold_us + .01)],
                         [(1.0, recovery_us)]))
    monkeypatch.setattr(modulated, "ff_maxv", lambda *_args, **_kw: 32767)
    monkeypatch.setattr(modulated, "ff_envelope_samples", lambda *_args: 65536)
    for frequency, expected in ((5.0, [8, 28]), (10.0, [16, 56])):
        program = object.__new__(modulated.ModulatedT1Program)
        program.cfg = {"ff_ch": 0, "ff_gain": -14299,
                       "ff_park_gain": -25146}
        program.soccfg = {"gens": [{"fs": 6881.28, "f_fabric": 430.08}]}
        program.holds_us = (1.6, 5.6)
        program.pre_us = .05
        program.ac_amplitude_dac = 429
        program.modulation_mhz = frequency
        program._t1_ff_compensation = object()
        program._t1_ff_settle_us = .5
        program._t1_ff_predistortion_recovery_us = 40.
        program._ff_ramp_cache = {}
        program.us2cycles = lambda hold, **_kw: round(hold * 430.08)
        program.add_pulse = lambda **_kw: None
        program._declare_experiment()
        assert [program.ac_reports[str(hold)]["cycles_per_waveform"]
                for hold in (1.6, 5.6)] == expected
        assert program.ff_envelope_report["total_samples"] < 65536


def test_static_profile_plays_changing_early_correction_without_target_pulse(monkeypatch):
    module = experiment()
    calls = []
    before = [(1.025, .2), (1.02, .35)]
    during = [(1.02, .8), (1.00, .8)]
    recovery = [(0.8, 40.0)]
    monkeypatch.setattr(module.modulated, "_target_segments",
                        lambda *args, **kwargs: (before, during, recovery))
    monkeypatch.setattr(module.ff_pulse, "play_relative_compensation_segments",
                        lambda _p, _park, _target, segments:
                        calls.append(segments))
    monkeypatch.setattr(module.ff_pulse, "play_hard_step",
                        lambda _p, park: calls.append(("park", park)))
    program = object.__new__(module.StaticProfileProgram)
    program.cfg = {"ff_park_gain": -25146, "ff_gain": -14299,
                   "opx_resident_pre_us": .05,
                   "opx_resident_post_us": 1.6}
    program._t1_ff_compensation = object()
    program._t1_ff_settle_us = .5
    program._t1_ff_predistortion_recovery_us = 40.
    program.sync_all = lambda *args: None
    program._resident_excursion()
    assert calls == [before, during, recovery, ("park", -25146)]
