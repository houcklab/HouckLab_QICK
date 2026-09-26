import importlib
import json
import subprocess
import sys
from collections import Counter
from types import SimpleNamespace

import pytest

PREFIX = "WorkingProjects.TLS_Spectroscopy.Client_modules"
MODULE = f"{PREFIX}.Runners.TLSPumpProbePilot"


def pilot():
    assert importlib.util.find_spec(MODULE) is not None, "pilot runner missing"
    return importlib.import_module(MODULE)


def test_plan_has_complete_matched_controls_without_hardware():
    module = pilot()
    result = subprocess.run([sys.executable, "-m", MODULE, "--plan"],
                            text=True, capture_output=True, check=True)
    plan = json.loads(result.stdout)
    assert plan["hardware_access"] is False
    schedule = module.schedule(module.parameters())
    assert len(schedule) == 336
    assert len({a["name"] for a in schedule}) == 336
    counts = Counter((a["target_index"], a["pump_mode"], a["probe_state"],
                      a["probe_us"]) for a in schedule)
    assert set(counts.values()) == {3}
    assert len(counts) == 7 * 4 * 2 * 2
    assert {a["probe_state"] for a in schedule} == {"g", "e"}
    assert {a["probe_us"] for a in schedule} == {2.0, 10.0}
    assert {a["pump_detuning_mhz"] for a in schedule} == {-20.0, 0.0, 20.0}
    assert schedule == module.schedule(module.parameters())


def test_pilot_checkpoints_results_and_stops_after_failure(tmp_path):
    module = pilot()
    manifest = {"status": "running", "points": [dict(name=str(i), status="pending") for i in range(3)]}
    path = tmp_path / "manifest.json"
    calls = []
    def acquire(entry):
        calls.append(entry["name"])
        if len(calls) == 2:
            assert json.loads(path.read_text())["points"][0]["result"]["raw_npz"] == "0.npz"
            raise RuntimeError("transport failed")
        return {"raw_npz": "0.npz", "P_excited": 0.2}
    with pytest.raises(RuntimeError, match="transport failed"):
        module.collect_points(manifest, path, acquire)
    saved = json.loads(path.read_text())
    assert calls == ["0", "1"]
    assert saved["status"] == "failed"
    assert [e["status"] for e in saved["points"]] == ["complete", "failed", "pending"]


def test_frequency_check_brackets_every_pump_sweep_with_sham_measurements():
    module = pilot()
    p = module.parameters(frequency_check=True)
    points = module.schedule(p)
    assert len(points) == 960
    assert p["pump_gain"] == 3000 and p["pump_us"] == 15.0
    assert p["target_frequency_ghz"] == [4.098, 4.104, 4.106, 4.110]
    # Each contiguous 15-point group holds frequency, preparation and hold fixed.
    for start in range(0, len(points), 15):
        block = points[start:start + 15]
        assert len({(e["repeat"], e["target_index"], e["probe_state"], e["probe_us"])
                    for e in block}) == 1
        assert block[0]["pump_mode"] == block[-1]["pump_mode"] == "sham"
        assert block[0]["control_position"] == "before"
        assert block[-1]["control_position"] == "after"
        assert all(e["pump_mode"] != "sham" for e in block[1:-1])
        assert sorted(e["pump_detuning_mhz"] for e in block[1:-1]) == [
            -20, -10, -8, -6, -4, -2, 0, 2, 4, 6, 8, 10, 20]
    assert len({e["name"] for e in points}) == 960


def test_frequency_plan_is_available_without_hardware_or_nas():
    result = subprocess.run([sys.executable, "-m", MODULE, "--plan", "--frequency-check"],
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["hardware_access"] is False
    assert plan["acquisition_blocks"] == 960
    assert plan["parameters"]["shots"] == 400
    assert plan["parameters"]["repeats"] == 4


@pytest.mark.parametrize("state,gain", [("g", 0), ("e", 13500)])
def test_native_probe_preparation_matches_timing_with_zero_gain_for_ground(state, gain):
    module = importlib.import_module(f"{PREFIX}.active_reset_OPX.programs")
    prog = object.__new__(module.OPXResetTLSSaturationProgram)
    prog.cfg = {"qubit_ch": 1, "qubit_pi_freq": 4367.292, "qubit_pi_gain": 13500,
                "opx_saturation_probe_state": state}
    events = []
    prog.freq2reg = lambda f, **_: f
    prog.deg2reg = lambda f, **_: f
    prog.us2cycles = lambda t, **_: t
    prog.set_pulse_registers = lambda **kw: events.append(kw)
    prog.pulse = lambda **kw: events.append(("pulse", kw))
    prog.sync_all = lambda t: events.append(("sync", t))
    prog._prepare_saturation_probe()
    assert events == [dict(ch=1, style="arb", freq=4367.292, phase=0.0,
                           gain=gain, waveform="qubit"),
                      ("pulse", {"ch": 1}), ("sync", 0.01)]


def test_hard_step_pump_tone_does_not_include_legacy_ramp_time():
    module = importlib.import_module(f"{PREFIX}.active_reset_OPX.programs")
    prog = object.__new__(module.OPXResetTLSSaturationProgram)
    prog.cfg = {"qubit_ch": 1, "opx_saturation_arm": "pump",
                "opx_saturation_pump_gain": 3000, "opx_saturation_pump_freq_mhz": 4102,
                "opx_saturation_pump_us": 15, "ff_ramp_length": 4}
    prog.reset_config = SimpleNamespace(hard_flux_steps=True)
    prog._t1_ff_settle_us = 0.5
    prog.freq2reg = lambda f, **_: f
    prog.deg2reg = lambda f, **_: f
    prog.us2cycles = lambda t, **_: t
    pulses = []
    prog.set_pulse_registers = lambda **kw: pulses.append(kw)
    prog._set_saturation_pump()
    assert pulses[-1]["length"] == 15.5
    prog.cfg["opx_saturation_arm"] = "no_pump"
    prog._set_saturation_pump()
    assert pulses[-1]["gain"] == 0
    assert pulses[-1]["length"] == 15.5
    prog.reset_config = SimpleNamespace(hard_flux_steps=False)
    prog._set_saturation_pump()
    assert pulses[-1]["length"] == 19.5


def test_native_pilot_resets_on_both_sides_of_pump_before_recording_probe(monkeypatch):
    module = importlib.import_module(f"{PREFIX}.active_reset_OPX.programs")
    prog = object.__new__(module.OPXResetTLSSaturationProgram)
    prog.cfg = {"qubit_ch": 1, "opx_saturation_reset_before_pump": True}
    prog.reset_page, prog.reset_regs = 0, {"i": 1, "q": 2, "address": 3}
    prog.payload_calibration, prog.loop_calibration = "payload_cal", "loop_cal"
    prog.reset_config = SimpleNamespace(inter_shot_delay_us=500, read_delay_us=10,
                                        loop_recovery_us=10, feedback_syncdelay_us=8)
    prog._saturation_recovery_us, prog._saturation_probe_us = 0, 10
    events = []
    prog._shot_park_callbacks = lambda: (lambda: events.append("park_up"), lambda: events.append("park_down"))
    prog._emit_saturation_pump = lambda: events.append("pump")
    prog._set_reset_pulse = lambda: events.append("reset_pulse_setup")
    prog._measure_project = lambda cal, context: events.append(("measure", cal, context))
    prog._wait_reset_ringdown = lambda: None
    prog.pulse = lambda **kw: None
    monkeypatch.setattr(module, "emit_unbounded_reset_state_machine",
                        lambda *_a, **kw: events.append(("reset", kw["label_prefix"])))
    prog._prepare_saturation_probe = lambda: events.append("probe_prepare")
    prog._prepare_excited = lambda: events.append("legacy_excited_only")
    prog._wait_t1_payload = lambda t: events.append(("probe", t))
    prog.us2cycles = lambda t: t
    prog.sync_all = lambda t: events.append(("wait", t))
    prog.memw = lambda *_: events.append("record")
    prog.mathi = lambda *_: None
    prog._emit_body()
    assert events == ["park_up", "reset_pulse_setup", ("measure", "payload_cal", "payload"),
                      ("reset", "OPX_TLS_SATURATION_PRE_RESET"), ("wait", 20), "pump", "reset_pulse_setup",
                      ("measure", "payload_cal", "payload"), ("reset", "OPX_TLS_SATURATION_RESET"),
                      ("wait", 20), ("wait", 0), "probe_prepare", ("probe", 10),
                      ("measure", "payload_cal", "payload"), "record", "record", "park_down", ("wait", 500)]


@pytest.mark.parametrize("remeasurements", [0, 2])
def test_reset_rebases_pump_after_cpu_feedback_wait_on_ground_and_loop_paths(monkeypatch, remeasurements):
    """Model QICK wait_all vs sync_all separately, with 0.25-us branch cost.

    This checks the caller's reset boundary, not the reset branch interpreter.
    A missing barrier OR sync_all(0) leaves the pulse in the processor's past.
    """
    module = importlib.import_module(f"{PREFIX}.active_reset_OPX.programs")
    prog = object.__new__(module.OPXResetTLSSaturationProgram)
    prog.cfg = {"qubit_ch": 1, "opx_saturation_arm": "pump",
                "opx_saturation_pump_gain": 3000, "opx_saturation_pump_freq_mhz": 4102,
                "opx_saturation_pump_us": 15}
    prog.reset_page, prog.reset_regs = 0, {}
    prog.payload_calibration, prog.loop_calibration = object(), object()
    prog.reset_config = SimpleNamespace(read_delay_us=10, feedback_syncdelay_us=8,
                                        loop_recovery_us=10, hard_flux_steps=True)
    prog._t1_ff_settle_us, prog._saturation_pump_us = 0.5, 15
    clock = dict(reference=0.0, endpoint=0.0, cpu=0.0)
    def sync(extra):
        clock["reference"] += clock["endpoint"] + extra
        clock["endpoint"] = 0.0
    def measure(*_):
        sync(0)
        clock["endpoint"] = 3.5
        clock["cpu"] = clock["reference"] + 3.5 + 10 + 0.25
    def reset_flow(*_, **kwargs):
        for _ in range(remeasurements):
            sync(20)  # stand in for a completed corrective-iteration boundary
            kwargs["measure_next"]()
    monkeypatch.setattr(module, "emit_unbounded_reset_state_machine", reset_flow)
    prog._measure_project = measure
    prog._set_reset_pulse = prog._wait_reset_ringdown = lambda: None
    prog.sync_all = sync
    prog.us2cycles = lambda t, **_: t
    prog.freq2reg = prog.deg2reg = lambda t, **_: t
    prog.set_pulse_registers = lambda **_: None
    starts = []
    prog.pulse = lambda **_: starts.append(clock["reference"])
    prog._wait_t1_payload = lambda _: starts.append(clock["reference"])
    prog._reset_saturation_qubit("TEST_RESET")
    prog._emit_saturation_pump()
    assert len(starts) == 2
    assert starts[0] == starts[1]  # pump and flux share the rebased origin
    assert min(starts) >= clock["cpu"] + 1.0


def test_confirmation_brackets_each_tone_and_null_with_matching_zero_gain_controls():
    module = pilot()
    points = module.schedule(module.parameters(confirmation_check=True))
    assert len(points) == 768
    from collections import Counter
    centers = []
    for start in range(0, len(points), 3):
        before, test, after = points[start:start + 3]
        assert [p['control_position'] for p in (before, test, after)] == ['before', 'test', 'after']
        assert before['pump_mode'] == after['pump_mode'] == 'sham'
        assert len({(p['repeat'], p['target_index'], p['probe_state'], p['probe_us'],
                     p['pump_detuning_mhz'], p['comparison_id'], p['test_condition'])
                    for p in (before, test, after)}) == 1
        if test['test_condition'] == 'null':
            assert test['pump_mode'] == 'sham'
            assert test['pump_detuning_mhz'] == 8
        else:
            assert test['pump_mode'] == test['test_condition']
            assert test['pump_detuning_mhz'] == {'near': 0, 'plus8': 8, 'minus20': -20}[test['pump_mode']]
        centers.append(test)
    assert Counter(p['test_condition'] for p in centers) == {'near': 64, 'plus8': 64, 'minus20': 64, 'null': 64}
    assert len({p['comparison_id'] for p in centers}) == 256
    assert len({p['name'] for p in points}) == 768
    assert len({(p['repeat'], p['target_index'], p['probe_state'], p['probe_us'], p['test_condition'])
                for p in centers}) == 256


def test_confirmation_plan_and_exclusive_stage_selection():
    result = subprocess.run([sys.executable, '-m', MODULE, '--plan', '--confirmation-check'],
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan['hardware_access'] is False
    assert plan['acquisition_blocks'] == 768
    assert plan['parameters']['target_frequency_ghz'] == [4.098, 4.110]
    assert plan['parameters']['shots'] == 400
    assert plan['parameters']['repeats'] == 8
    result = subprocess.run([sys.executable, '-m', MODULE, '--plan', '--confirmation-check', '--frequency-check'],
                            text=True, capture_output=True)
    assert result.returncode != 0
    with pytest.raises(ValueError):
        pilot().parameters(frequency_check=True, confirmation_check=True)
