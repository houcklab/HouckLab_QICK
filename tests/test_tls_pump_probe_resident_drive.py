"""Behavioral contracts for the target-resident q3 drive calibration."""

import importlib
from types import SimpleNamespace

import numpy as np
import pytest


MODULE = "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeResidentDrive"


def experiment():
    return importlib.import_module(MODULE)


def test_single_readout_decoder_preserves_signed_iq_and_rejects_missing_word():
    module = experiment()
    assert module.decode_single_iq([0xFFFFFFFF, 0xFFFFFFFE], 1) == [
        module.SingleIQ(-1, -2)]
    with pytest.raises(ValueError, match="two words"):
        module.decode_single_iq([1], 1)


def test_resident_drive_is_scheduled_between_target_segments_before_return(monkeypatch):
    module = experiment()
    program = object.__new__(module.ResidentDriveProgram)
    program.cfg = {"ff_park_gain": -25000, "ff_gain": -17000,
                   "qubit_ch": 1, "sigma": 0.02,
                   "opx_resident_pre_us": 1.0,
                   "opx_resident_post_us": 0.1,
                   "opx_resident_freq_mhz": 4132.0,
                   "opx_resident_gain": 6000}
    program._t1_ff_compensation = object()
    program._t1_ff_settle_us = 0.5
    program._t1_ff_predistortion_recovery_us = 40.0
    events = []
    program.set_pulse_registers = lambda **kw: events.append(("drive_regs", kw["gain"], kw["freq"]))
    program.freq2reg = lambda freq, **kw: freq
    program.deg2reg = lambda deg, **kw: deg
    program.pulse = lambda **kw: events.append("drive")
    program.us2cycles = lambda us, **kw: us
    program.sync_all = lambda us: events.append(("sync", us))
    monkeypatch.setattr(module.ff_pulse, "compensation_round_trip_segments",
                        lambda *_args, **_kw: ([(1.0, 1.5), (1.0, 0.09), (1.0, 0.1)],
                                               [(0.1, 40.0)]))
    monkeypatch.setattr(module.ff_pulse, "play_relative_compensation_segments",
                        lambda _p, _park, _target, segs: events.append(("flux", list(segs))))
    monkeypatch.setattr(module.ff_pulse, "play_hard_step",
                        lambda _p, gain: events.append(("park", gain)))

    program._resident_excursion()

    assert events.index("drive") < events.index(("flux", [(1.0, 0.1)]))
    assert events.index(("flux", [(1.0, 1.5)])) < events.index("drive")
    assert events.index(("flux", [(0.1, 40.0)])) > events.index("drive")
    assert events[-2:] == [("park", -25000), ("sync", 0)]


def test_reference_pi_occurs_after_return_but_science_has_no_park_pi_after_return():
    module = experiment()
    program = object.__new__(module.ResidentDriveProgram)
    program.cfg = {"qubit_ch": 1, "opx_resident_reference_state": "e",
                   "opx_resident_gain": 0}
    program.reset_config = SimpleNamespace(inter_shot_delay_us=500.0)
    program.reset_page, program.reset_regs = 0, {"i": 1, "q": 2, "address": 3}
    events = []
    program._shot_park_callbacks = lambda: (lambda: events.append("up"),
                                            lambda: events.append("down"))
    program._set_payload_pulse = lambda **kw: events.append(("park_pi_gain", kw.get("gain")))
    program.pulse = lambda **kw: events.append("park_pi")
    program._resident_excursion = lambda: events.append("excursion")
    program._measure_raw = lambda: events.append("readout")
    program.memw = program.mathi = lambda *_: None
    program.us2cycles = lambda us, **_: us
    program.sync_all = lambda *_: None
    program._emit_body()
    assert events == ["up", ("park_pi_gain", 0), "park_pi", "excursion",
                      ("park_pi_gain", None), "park_pi", "readout", "down"]
    events.clear()
    program.cfg["opx_resident_reference_state"] = None
    program._emit_body()
    assert events == ["up", ("park_pi_gain", 0), "park_pi", "excursion",
                      "readout", "down"]
    events.clear()
    program.cfg["opx_resident_preparation_state"] = "e"
    program._emit_body()
    assert events == ["up", ("park_pi_gain", None), "park_pi", "excursion",
                      "readout", "down"]


def test_calibration_design_brackets_each_detuning_with_zero_drive():
    module = experiment()
    arms = module.calibration_arms(4.132, 4.118)
    for site in ("feature", "flank"):
        for detuning in module.DETUNINGS_MHZ:
            group = [a for a in arms if a["site"] == site and a["detuning_mhz"] == detuning]
            assert group[0]["gain"] == group[-1]["gain"] == 0
            assert {a["gain"] for a in group[1:-1]} == set(module.DRIVEN_GAINS)
            assert len(group) == len(module.DRIVEN_GAINS) + 2
    assert all(-32768 <= arm["gain"] <= 32767 for arm in arms)


def test_frozen_readout_axis_detects_post_reference_collapse():
    module = experiment()
    axis = module.fit_axis(np.full(200, -3.0), np.full(200, 3.0))
    assert axis["fidelity"] == 1.0
    assert module.score_axis(axis, np.full(200, -3.0), np.full(200, 3.0))["valid"]
    assert not module.score_axis(axis, np.full(200, -3.0), np.full(200, -3.0))["valid"]


def test_drive_window_rejects_changing_flux_correction(monkeypatch):
    module = experiment()
    monkeypatch.setattr(module.ff_pulse, "compensation_round_trip_segments",
                        lambda *_a, **_k: ([(1.0, 1.5), (1.02, 0.4), (1.03, 0.5)],
                                           [(0.1, 40.0)]))
    with pytest.raises(ValueError, match="not flat"):
        module.resident_segments(object(), pre_us=1.5, pulse_us=0.8,
                                 post_us=0.1, recovery_us=40.0)


def test_feature_shift_and_transfer_contrast_gate_interpretation():
    module = experiment()
    assert module.feature_stable({"center_ghz": 4.132, "depth": 0.3},
                                 {"center_ghz": 4.134, "depth": 0.25})
    assert not module.feature_stable({"center_ghz": 4.132, "depth": 0.3},
                                     {"center_ghz": 4.136, "depth": 0.25})
    assert module.transfer_usable(0.1, 0.4)
    assert not module.transfer_usable(0.1, 0.2)
