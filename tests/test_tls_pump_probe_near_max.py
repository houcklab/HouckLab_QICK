"""The near-max park-tone experiment must retain frequency and sham controls."""

import csv
import importlib

import pytest


MODULE = (
    "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners."
    "TLSPumpProbeNearMax"
)


def test_plan_and_arm_sequence():
    runner = importlib.import_module(MODULE)
    p = runner.plan()
    assert p["maximum_gain"] == 30000
    assert p["screen_gain"] == 12000
    assert p["pump_us"] == 15.0
    assert p["reset_mode"] == "passive"
    assert p["probe_delays_us"] == [2.0, 25.0]
    assert [(a["gain"], a["detuning_mhz"], a["state"])
            for a in runner.ARMS] == [
        (0, 0, "g"), (0, 0, "e"),
        (12000, 0, "g"), (12000, 0, "e"),
        (0, 0, "g"), (0, 0, "e"),
        (30000, -40, "g"), (30000, -40, "e"),
        (30000, 0, "g"), (30000, 0, "e"),
        (30000, 40, "g"), (30000, 40, "e"),
        (30000, 0, "g"), (30000, 0, "e"),
        (0, 0, "g"), (0, 0, "e"),
    ]


def test_run_follows_selected_coordinate_and_keeps_pump_settings_local(
        monkeypatch, tmp_path):
    runner = importlib.import_module(MODULE)
    calls = []
    monkeypatch.setattr(runner.localizer, "run", lambda **kw: (
        calls.append(kw), tmp_path / f"scan{len(calls)}.csv")[1])
    monkeypatch.setattr(runner.adaptive, "read_scout", lambda _path: [])
    monkeypatch.setattr(runner.adaptive, "select_loss_feature", lambda _rows: {
        "center_ghz": 4.140, "depth": 0.4,
        "depth_scan_up": 0.3, "depth_scan_down": 0.3,
    })
    monkeypatch.setattr(runner, "quality_guard", lambda _path: None)

    result = runner.run(data_root=tmp_path)

    assert len(calls) == 18
    arms = [call["parameter_overrides"] for call in calls[1:17]]
    assert [(p["park_pump_gain"], p["park_pump_frequency_mhz"],
             p["survival_probe_state"]) for p in arms] == [
        (a["gain"], 4140.0 + a["detuning_mhz"], a["state"])
        for a in runner.ARMS
    ]
    assert all(p["decay_delays_us"] == [2.0, 25.0] for p in arms)
    assert all(p["freq_min_ghz"] == 4.12 for p in arms)
    assert all(p["freq_max_ghz"] == 4.16 for p in arms)
    assert all(p["shots_per_condition"] == 350 for p in arms)
    assert len({p["output_suffix"] for p in arms}) == 16
    assert len(result["arms"]) == 16


def test_guard_stops_reference_collapse_and_broad_excitation(tmp_path):
    runner = importlib.import_module(MODULE)
    path = tmp_path / "arm.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["P0", "P1"])
        writer.writeheader()
        writer.writerows([{"P0": 0.05, "P1": 0.30}] * 21)
    runner.quality_guard(path)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["P0", "P1"])
        writer.writeheader()
        writer.writerows([{"P0": 0.25, "P1": 0.45}] * 21)
    with pytest.raises(RuntimeError, match="broad excitation"):
        runner.quality_guard(path)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["P0", "P1"])
        writer.writeheader()
        writer.writerows([{"P0": 0.05, "P1": 0.13}] * 21)
    with pytest.raises(RuntimeError, match="reference contrast"):
        runner.quality_guard(path)
