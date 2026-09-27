"""Band scans must cover the moving loss feature in every pump arm."""

import importlib

import pytest


MODULE = (
    "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners."
    "TLSPumpProbeBandComparison"
)


def test_band_parameters_follow_scout_center_and_cover_both_flanks():
    runner = importlib.import_module(MODULE)
    p = runner.band_parameters(center_ghz=4.137)
    assert p["freq_min_ghz"] == pytest.approx(4.117)
    assert p["freq_max_ghz"] == pytest.approx(4.157)
    assert p["freq_step_mhz"] == 1.0
    assert p["shots_per_condition"] == 350


def test_run_uses_three_band_arms_with_matched_pump_timing(monkeypatch, tmp_path):
    runner = importlib.import_module(MODULE)
    calls = []
    monkeypatch.setattr(runner.localizer, "run", lambda **kw: (
        calls.append(kw), tmp_path / f"scan{len(calls)}.csv")[1])
    monkeypatch.setattr(runner.adaptive, "read_scout", lambda _path: [])
    monkeypatch.setattr(runner.adaptive, "select_loss_feature", lambda _rows: {
        "center_ghz": 4.137, "depth": 0.4,
        "depth_scan_up": 0.3, "depth_scan_down": 0.3,
    })
    result = runner.run(data_root=tmp_path)
    assert len(calls) == 5
    assert calls[0]["parameter_overrides"]["output_suffix"] == (
        "TLS_PumpProbe_Band_Scout_pre")
    assert calls[-1]["parameter_overrides"]["output_suffix"] == (
        "TLS_PumpProbe_Band_Scout_post")
    arms = [call["parameter_overrides"] for call in calls[1:4]]
    assert [arm["park_pump_gain"] for arm in arms] == [0, 3000, 0]
    assert all(arm["park_pump_frequency_mhz"] == 4137.0 for arm in arms)
    assert all(arm["park_pump_us"] == 15.0 for arm in arms)
    assert all(arm["freq_min_ghz"] == 4.117 for arm in arms)
    assert all(arm["freq_max_ghz"] == 4.157 for arm in arms)
    assert len({arm["output_suffix"] for arm in arms}) == 3
    assert result["selected"]["center_ghz"] == 4.137
    assert len(result["arms"]) == 3


def test_plan_is_read_only_and_reports_the_band_protocol():
    runner = importlib.import_module(MODULE)
    p = runner.plan()
    assert p["hardware_access"] is False
    assert p["arm_gains"] == [0, 3000, 0]
    assert p["band_half_width_mhz"] == 20.0
    assert p["band_frequencies"] == 41
