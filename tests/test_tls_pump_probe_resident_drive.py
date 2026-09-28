"""Behavioral contracts for the target-resident q3 drive calibration."""

import importlib
import json
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


def test_arm_config_preserves_requested_probe_hold_and_hot_preparation():
    module = experiment()
    cfg = module.arm_config(
        {"sigma": 0.2},
        {"flux_ghz": 4.133, "drive_mhz": 4138.0, "gain": 6000,
         "preparation_state": "e", "post_drive_us": 6.0, "shots": 400},
        {4.133: -17000})
    assert cfg["opx_resident_preparation_state"] == "e"
    assert cfg["opx_resident_post_us"] == 6.0
    assert cfg["ff_hold"] == pytest.approx(26.81)
    assert cfg["shots"] == cfg["reps"] == 400


def test_probe_schedule_pairs_hot_cold_and_brackets_each_tone_block():
    module = importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeResidentProbe")
    arms = module.probe_arms(4.133, 4.119)
    assert len(arms) == 120
    for repeat in (0, 1):
        for site in ("feature", "flank"):
            for hold in (0.1, 2.0, 6.0):
                block = [a for a in arms if a["repeat"] == repeat and
                         a["site"] == site and a["post_drive_us"] == hold]
                expected = (["sham_a", "on_6000", "detuned_6000",
                             "on_30000", "sham_b"] if repeat == 0 else
                            ["sham_b", "on_30000", "detuned_6000",
                             "on_6000", "sham_a"])
                assert [a["tone"] for a in block[::2]] == expected
                assert all({block[i]["preparation_state"],
                            block[i+1]["preparation_state"]} == {"g", "e"}
                           for i in range(0, len(block), 2))
                assert all(a["pre_drive_us"] == 20.0 for a in block)
                assert all(a["drive_mhz"] == pytest.approx(1000 * a["flux_ghz"] +
                             (5 if a["tone"] != "detuned_6000" else -10))
                           for a in block)


def test_loading_time_schedule_balances_loads_and_reverses_order():
    module = importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeResidentProbe")
    arms = module.loading_time_arms(4.128, 4.114)
    assert len(arms) == 128
    assert {a["pre_drive_us"] for a in arms} == {20.0, 80.0}
    assert {a["post_drive_us"] for a in arms} == {0.1, 2.0}
    assert {a["tone"] for a in arms} == {
        "sham_a", "on_6000", "detuned_6000", "sham_b"}
    assert all(a["gain"] in (0, 6000) and a["shots"] == 400 for a in arms)
    for repeat in (0, 1):
        subset = [a for a in arms if a["repeat"] == repeat]
        expected_loads = (20.0, 80.0) if repeat == 0 else (80.0, 20.0)
        assert list(dict.fromkeys(a["pre_drive_us"] for a in subset[:64])) == list(expected_loads)
        for site in ("feature", "flank"):
            for load in expected_loads:
                for hold in (0.1, 2.0):
                    block = [a for a in subset if a["site"] == site and
                             a["pre_drive_us"] == load and a["post_drive_us"] == hold]
                    assert len(block) == 8
                    assert all({block[i]["preparation_state"],
                                block[i + 1]["preparation_state"]} == {"g", "e"}
                               for i in range(0, 8, 2))
                    assert [a["tone"] for a in block[::2]] == (
                        ["sham_a", "on_6000", "detuned_6000", "sham_b"]
                        if repeat == 0 else
                        ["sham_b", "detuned_6000", "on_6000", "sham_a"])
    assert len({a["name"] for a in arms}) == len(arms)


def test_loading_time_plan_describes_actual_schedule():
    module = importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeResidentProbe")
    plan = module.plan(loading_time_check=True)
    assert plan["science_arms"] == 128
    assert plan["pre_drive_holds_us"] == [20.0, 80.0]
    assert plan["probe_holds_us"] == [0.1, 2.0]
    assert plan["probe_dac_gains"] == [0, 6000]


def test_carryover_schedule_has_paired_baselines_around_each_pump_block():
    module = importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeResidentProbe")
    arms = module.carryover_arms(4.125, 4.111)
    assert len(arms) == 240
    assert len({a["name"] for a in arms}) == 240
    assert {a["cycle"] for a in arms} == set(range(8))
    assert {a["site"] for a in arms} == {"feature", "flank"}
    for cycle in range(8):
        for site in ("feature", "flank"):
            for tone in ("sham", "on_6000", "detuned_6000"):
                group = [a for a in arms if a["cycle"] == cycle and
                         a["site"] == site and a["pump_tone"] == tone]
                assert [a["role"] for a in group] == [
                    "pre_g", "pre_e", "pump_e", "post_e", "post_g"]
                assert [a["gain"] for a in group] == [
                    0, 0, {"sham": 0, "on_6000": 6000,
                           "detuned_6000": 6000}[tone], 0, 0]
                assert all(a["pre_drive_us"] == 20.0 and
                           a["post_drive_us"] == 0.1 and a["shots"] == 100
                           for a in group)
    assert [a["site"] for a in arms[:15]] == ["feature"] * 15
    assert [a["site"] for a in arms[15:30]] == ["flank"] * 15
    assert [a["site"] for a in arms[30:45]] == ["flank"] * 15


def test_carryover_plan_and_calibration_frequency_bracket():
    module = importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeResidentProbe")
    plan = module.plan(carryover_check=True)
    assert plan["science_arms"] == 240
    assert plan["shots_per_arm"] == 100
    assert module.calibration_brackets_feature({"center_ghz": 4.133}, 4.125)
    assert not module.calibration_brackets_feature({"center_ghz": 4.133}, 4.115)


def test_probe_rejects_feature_outside_calibrated_frequency_neighborhood():
    module = importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeResidentProbe")
    assert module.calibration_covers_feature(4.133, 4.137)
    assert not module.calibration_covers_feature(4.133, 4.140)


def test_probe_rejects_calibration_with_wrong_flux_correction(tmp_path):
    module = importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeResidentProbe")
    folder = tmp_path / "q3" / module.CALIBRATION_SESSION_ID
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(
        '{"status":"complete","schema":"q3.pump-probe-resident-drive.v1",'
        '"feature_stable":true,"pre_readout_valid":true,'
        '"correction_sha256":"wrong","arms":[]}')
    with pytest.raises(ValueError, match="flux correction"):
        module.checked_calibration(tmp_path)


def test_probe_rejects_calibration_with_different_drive_settings(tmp_path):
    module = importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeResidentProbe")
    folder = tmp_path / "q3" / module.CALIBRATION_SESSION_ID
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps({
        "status": "complete", "schema": "q3.pump-probe-resident-drive.v1",
        "feature_stable": True, "pre_readout_valid": True,
        "correction_sha256": module.localizer.CORRECTION_SHA256,
        "plan": {"pre_drive_us": 1.0, "driven_gains_dac": [6000, 30000]},
        "arms": [],
    }))
    with pytest.raises(ValueError, match="drive settings"):
        module.checked_calibration(tmp_path)
