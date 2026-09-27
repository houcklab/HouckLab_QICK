"""Higher-gain pump test must measure both energy-transfer directions."""

import importlib

import pytest


MODULE = (
    "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners."
    "TLSPumpProbeHighGainBidirectional"
)


def test_plan_caps_gain_and_reports_both_probe_states():
    runner = importlib.import_module(MODULE)
    p = runner.plan()
    assert p["pump_gain"] == 6000
    assert p["comparison_gain"] == 3000
    assert p["pump_us"] == 15.0
    assert p["probe_states"] == ["g", "e"]
    assert p["reset_mode"] == "passive"
    with pytest.raises(ValueError, match="pump gain"):
        runner.plan(pump_gain=9000)


def test_run_relocalizes_then_brackets_both_ground_and_excited_probes(
        monkeypatch, tmp_path):
    runner = importlib.import_module(MODULE)
    calls = []
    monkeypatch.setattr(runner.localizer, "run", lambda **kw: (
        calls.append(kw), tmp_path / f"scan{len(calls)}.csv")[1])
    monkeypatch.setattr(runner.adaptive, "read_scout", lambda _path: [])
    monkeypatch.setattr(runner.adaptive, "select_loss_feature", lambda _rows: {
        "center_ghz": 4.138, "depth": 0.4,
        "depth_scan_up": 0.3, "depth_scan_down": 0.3,
    })
    result = runner.run(data_root=tmp_path)
    assert len(calls) == 10
    arms = [call["parameter_overrides"] for call in calls[1:9]]
    assert [(a["park_pump_gain"], a["survival_probe_state"]) for a in arms] == [
        (0, "g"), (0, "e"), (3000, "g"), (3000, "e"),
        (6000, "g"), (6000, "e"), (0, "g"), (0, "e")]
    assert all(a["park_pump_frequency_mhz"] == 4138.0 for a in arms)
    assert all(a["park_pump_us"] == 15.0 for a in arms)
    assert all(a["decay_delays_us"] == [25.0] for a in arms)
    assert all(a["freq_min_ghz"] == 4.118 for a in arms)
    assert all(a["freq_max_ghz"] == 4.158 for a in arms)
    assert all(a["freq_step_mhz"] == 2.0 for a in arms)
    assert len({a["output_suffix"] for a in arms}) == 8
    assert result["selected"]["center_ghz"] == 4.138
    assert len(result["arms"]) == 8
