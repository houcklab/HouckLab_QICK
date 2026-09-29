"""Behavioral checks for the q3 AC-flux transfer pilot."""

import importlib

import numpy as np
import pytest


MODULE = "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSFluxModulationCalibration"


def experiment():
    return importlib.import_module(MODULE)


def test_waveform_contains_dc_bias_and_thirty_complete_cycles():
    module = experiment()
    waveform, report = module.modulation_waveform(
        sample_rate_mhz=6880.0, fabric_rate_mhz=430.0,
        cycles=430, baseline_gain=-16400, amplitude_gain=1200,
        modulation_mhz=30.0, max_gain=32767)
    assert waveform.shape == (6880,)
    assert waveform.dtype == np.int16
    assert waveform[0] == -16400
    assert abs(int(waveform[-1]) + 16400) <= 35
    assert waveform.min() >= -17601 and waveform.max() <= -15199
    assert np.argmax(np.abs(np.fft.rfft(waveform.astype(float) + 16400))[1:]) + 1 == 30
    assert report["actual_modulation_mhz"] == pytest.approx(30.0)
    assert report["cycles_per_waveform"] == 30


def test_waveform_rejects_clipping_or_nonintegral_generator_ratio():
    module = experiment()
    with pytest.raises(ValueError, match="DAC range"):
        module.modulation_waveform(
            sample_rate_mhz=6880, fabric_rate_mhz=430, cycles=430,
            baseline_gain=-32000, amplitude_gain=1200,
            modulation_mhz=30, max_gain=32767)
    with pytest.raises(ValueError, match="samples per clock"):
        module.modulation_waveform(
            sample_rate_mhz=6880, fabric_rate_mhz=429, cycles=430,
            baseline_gain=0, amplitude_gain=100,
            modulation_mhz=30, max_gain=32767)


def test_modulation_played_during_qubit_probe_before_corrected_return(monkeypatch):
    module = experiment()
    program = object.__new__(module.ModulatedResidentProgram)
    program.cfg = {"ff_ch": 3, "qubit_ch": 1, "ff_park_gain": -25146,
                   "ff_gain": -16613, "opx_resident_pre_us": 20.0,
                   "opx_resident_post_us": 0.1, "sigma": 0.2,
                   "opx_resident_freq_mhz": 4127.0, "opx_resident_gain": 6000}
    program._t1_ff_compensation = object()
    program.soccfg = {"gens": [{}, {}, {}, {"maxv": 32767}]}
    program._t1_ff_settle_us = 0.5
    program._t1_ff_predistortion_recovery_us = 40.0
    program.modulation_waveform_report = {"duration_us": 0.8}
    events = []
    program.set_pulse_registers = lambda **kw: events.append(("regs", kw["ch"], kw["gain"]))
    program.freq2reg = lambda value, **kw: value
    program.deg2reg = lambda value, **kw: value
    program.pulse = lambda **kw: events.append(("pulse", kw["ch"]))
    program.sync_all = lambda *_: events.append("sync")
    program.us2cycles = lambda value, **kw: value
    monkeypatch.setattr(module.resident, "resident_segments",
                        lambda *_a, **_kw: ([(1.0, 20.5)], [(1.0, 0.1)],
                                             [(0.0, 40.0)]))
    monkeypatch.setattr(module.ff_pulse, "play_relative_compensation_segments",
                        lambda _p, _park, _target, segs:
                        events.append(("flux_segment", segs[0][1])))
    monkeypatch.setattr(module.ff_pulse, "play_hard_step",
                        lambda _p, gain: events.append(("park", gain)))

    program._resident_excursion()

    assert events.index(("flux_segment", 20.5)) < events.index(("pulse", 3))
    assert events.index(("pulse", 3)) < events.index(("pulse", 1))
    assert events.index(("pulse", 1)) < events.index(("flux_segment", 0.1))
    assert events[-2:] == [("park", -25146), "sync"]


def test_sideband_probe_grid_brackets_carrier_and_both_first_sidebands():
    module = experiment()
    points = module.sideband_grid(4132.0, modulation_mhz=30.0)
    assert 4132.0 in points
    assert 4102.0 in points and 4162.0 in points
    assert min(points) == 4098.0 and max(points) == 4166.0
    assert len(points) == 15


def test_plan_is_a_calibration_only_with_no_modulated_t1_claim():
    plan = experiment().plan()
    assert plan["hardware_access"] is False
    assert plan["modulation_frequency_mhz"] == 30.0
    assert plan["modulation_amplitudes_dac"] == [0, 800, 1600]
    assert plan["full_return_before_readout_us"] == 40.0
    assert "T1" not in plan["purpose"]


def test_frequency_response_plan_and_schedule_cover_three_drive_rates():
    module = experiment()
    description = module.plan(frequency_response=True)
    assert description["hardware_access"] is False
    assert description["modulation_frequencies_mhz"] == [20.0, 30.0, 40.0]
    assert description["modulation_amplitudes_dac"] == [0, 800]
    assert description["stage"] == "calibration_only"
    arms = module.frequency_response_arms(4.058, 4062.0)
    assert len(arms) == 90
    assert len({arm["name"] for arm in arms}) == len(arms)
    for frequency in (20.0, 30.0, 40.0):
        group = [arm for arm in arms if arm["modulation_mhz"] == frequency]
        assert len(group) == 30
        assert {arm["order"] for arm in group} == {-1, 0, 1}
        assert {arm["modulation_amplitude_dac"] for arm in group} == {0, 800}
        assert {arm["drive_mhz"] for arm in group
                if arm["order"] == 1 and arm["offset_mhz"] == 0} == {
                    4062.0 + frequency}


def test_frequency_response_site_prefers_quiet_flank_sixty_mhz_away():
    module = experiment()
    rows = []
    for i in range(251):
        freq = round(3.8 + .002 * i, 3)
        survival = .75
        if 4.116 <= freq <= 4.120:
            survival = .2
        elif freq == 4.138:
            survival = .3  # spoils the upper +60-MHz calibration flank
        p25 = .1 + .8 * survival
        rows.append({"target_frequency_ghz": str(freq), "P0": ".1",
                     "P1": ".9", "Ps_25us": str(p25),
                     "P0_scan_up": ".1", "P1_scan_up": ".9",
                     "Ps_25us_scan_up": str(p25), "P0_scan_down": ".1",
                     "P1_scan_down": ".9", "Ps_25us_scan_down": str(p25)})
    report = module.select_frequency_response_site(rows, 4.118)
    assert report["site_ghz"] == 4.058
    assert report["min_survival"] >= .6


@pytest.mark.parametrize("frequency, cycles", [(20.0, 16), (40.0, 32)])
def test_program_compiles_the_requested_modulation_frequency(monkeypatch,
                                                              frequency, cycles):
    module = experiment()
    monkeypatch.setattr(module.resident.ResidentDriveProgram,
                        "_declare_experiment", lambda self: None)
    monkeypatch.setattr(module.resident, "resident_segments",
                        lambda *_a, **_kw: ([(1.0, 20.5)],
                                             [(1.0, .1)], [(0.0, 40.0)]))
    monkeypatch.setattr(module, "ff_maxv", lambda *_a, **_kw: 32767)
    monkeypatch.setattr(module, "ff_envelope_samples", lambda *_a: 65536)
    program = object.__new__(module.ModulatedResidentProgram)
    program.cfg = {"ff_ch": 0, "sigma": .2, "ff_gain": -16000,
                   "ff_park_gain": -25146, "opx_resident_pre_us": 20.,
                   "opx_resident_post_us": .1,
                   "opx_modulation_amplitude_dac": 800,
                   "opx_modulation_mhz": frequency}
    program.soccfg = {"gens": [{"fs": 6881.28, "f_fabric": 430.08}]}
    program._t1_ff_compensation = object()
    program._t1_ff_settle_us = .5
    program._t1_ff_predistortion_recovery_us = 40.
    program.us2cycles = lambda us, **_kw: round(us * 430.08)
    program.add_pulse = lambda **_kw: None
    program._declare_experiment()
    assert program.modulation_waveform_report["cycles_per_waveform"] == cycles
    assert program.modulation_waveform_report["requested_modulation_mhz"] == frequency
