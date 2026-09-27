"""The pump target must be localized immediately before the drive comparison."""

import importlib
import csv

import numpy as np
import pytest


MODULE = (
    "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners."
    "TLSPumpProbeAdaptiveParkPump"
)


def synthetic_scout(center=4.140, depth=0.18):
    rows = []
    for f in np.arange(4.090, 4.1701, 0.001):
        dip = depth * np.exp(-0.5 * ((f - center) / 0.002) ** 2)
        row = {"target_frequency_ghz": float(f), "P0": 0.10,
               "P1": 0.40, "Ps_25us": 0.33 - dip,
               "P0_scan_up": 0.10, "P1_scan_up": 0.40,
               "Ps_25us_scan_up": 0.33 - dip,
               "P0_scan_down": 0.10, "P1_scan_down": 0.40,
               "Ps_25us_scan_down": 0.33 - dip}
        rows.append(row)
    return rows


def test_selector_finds_local_loss_with_both_direction_checks():
    runner = importlib.import_module(MODULE)
    result = runner.select_loss_feature(synthetic_scout())
    assert result["center_ghz"] == pytest.approx(4.140)
    assert result["depth"] > 0.3
    assert result["depth_scan_up"] > 0.3
    assert result["depth_scan_down"] > 0.3


def test_selector_rejects_flat_or_one_direction_only_loss():
    runner = importlib.import_module(MODULE)
    with pytest.raises(ValueError, match="no sufficiently localized loss"):
        runner.select_loss_feature(synthetic_scout(depth=0))
    one_direction = synthetic_scout()
    for row in one_direction:
        row["Ps_25us_scan_down"] = 0.33
    with pytest.raises(ValueError, match="no sufficiently localized loss"):
        runner.select_loss_feature(one_direction)


def test_adaptive_run_pumps_selected_current_center_then_checks_drift(
        monkeypatch, tmp_path):
    runner = importlib.import_module(MODULE)
    calls = []
    monkeypatch.setattr(runner.localizer, "run", lambda **kw: (
        calls.append(("scout", kw)), tmp_path / "scout.csv")[1])
    monkeypatch.setattr(runner.park_pump, "run", lambda **kw: calls.append(("pump", kw)))
    monkeypatch.setattr(runner, "read_scout", lambda _path: synthetic_scout())
    runner.run(data_root=tmp_path)
    assert [kind for kind, _ in calls] == ["scout", "pump", "scout"]
    assert calls[1][1]["center_ghz"] == pytest.approx(4.140)
    assert calls[0][1]["parameter_overrides"]["output_suffix"] != (
        calls[2][1]["parameter_overrides"]["output_suffix"])


def test_drift_control_uses_seven_equal_duration_zero_gain_arms(monkeypatch, tmp_path):
    runner = importlib.import_module(MODULE)
    calls = []
    monkeypatch.setattr(runner.localizer, "run", lambda **kw: (
        calls.append(kw), tmp_path / "scout.csv")[1])
    monkeypatch.setattr(runner, "read_scout", lambda _path: synthetic_scout())
    result = runner.run(data_root=tmp_path, drift_control=True)
    assert len(calls) == 9
    arms = [call["parameter_overrides"] for call in calls[1:-1]]
    assert all(arm["park_pump_gain"] == 0 for arm in arms)
    assert all(arm["park_pump_us"] == 15.0 for arm in arms)
    assert all(arm["park_pump_frequency_mhz"] == 4140.0 for arm in arms)
    assert len({arm["output_suffix"] for arm in arms}) == 7
    assert all("Drift_Control" in arm["output_suffix"] for arm in arms)
    assert "Drift_Control" in calls[0]["parameter_overrides"]["output_suffix"]
    assert "Drift_Control" in calls[-1]["parameter_overrides"]["output_suffix"]
    assert len(result["pump_arms"]) == 7


def test_scout_reader_rejects_duplicate_rows_disguised_as_full_pass(tmp_path):
    runner = importlib.import_module(MODULE)
    path = tmp_path / "scout.csv"
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["wall_clock_run_index", "target_frequency_ghz"])
        writer.writeheader()
        writer.writerows({"wall_clock_run_index": 0, "target_frequency_ghz": 4.140}
                         for _ in range(81))
    with pytest.raises(RuntimeError, match="complete 81-frequency pass"):
        runner.read_scout(path)
