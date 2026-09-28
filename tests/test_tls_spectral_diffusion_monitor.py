"""Bounded passive scans measure q3 loss-frequency motion over time."""

import importlib


def monitor():
    return importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners."
        "TLSSpectralDiffusionMonitor")


def test_monitor_is_finite_passive_and_covers_recent_dip_motion():
    params = monitor().parameters()
    assert params["freq_min_ghz"] == 4.060
    assert params["freq_max_ghz"] == 4.170
    assert params["freq_step_mhz"] == 1.0
    assert params["max_runs"] == 10
    assert params["wall_clock_duration_min"] == 25.0
    assert params["max_consecutive_failures"] == 1
    assert params["reset_mode"] == "passive"
    assert params["apply_flux_tail_compensation"] is True
    assert params["shots_per_condition"] == 350
    assert "park_pump_gain" not in params


def test_monitor_plan_counts_complete_scans_without_hardware_access():
    plan = monitor().plan()
    assert plan["hardware_access"] is False
    assert plan["frequency_count"] == 111
    assert plan["planned_passes"] == 10
    assert plan["condition_count"] == 5
