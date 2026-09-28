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
