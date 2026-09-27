"""Hardware-free contract for the passive q3 4.140-GHz pump check."""

import importlib


MODULE = (
    "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners."
    "TLSPumpProbePassiveParkPump"
)


def test_park_pump_plan_brackets_resonant_and_detuned_tones():
    runner = importlib.import_module(MODULE)
    p = runner.parameters()
    arms = runner.arms()
    assert (p["freq_min_ghz"], p["freq_max_ghz"], p["freq_step_mhz"]) == (
        4.138, 4.142, 2.0)
    assert p["reset_mode"] == "passive"
    assert p["calibrate_passive_readout"] is True
    assert p["max_runs"] == p["max_consecutive_failures"] == 1
    assert p["shots_per_condition"] == 500
    assert p["decay_delays_us"] == [2.0, 10.0, 25.0]
    assert [arm["label"] for arm in arms] == [
        "sham", "resonant", "minus20", "sham", "plus20", "resonant", "sham"
    ]
    assert [arm["gain"] for arm in arms] == [0, 3000, 3000, 0, 3000, 3000, 0]
    assert [arm["frequency_mhz"] for arm in arms] == [
        4140.0, 4140.0, 4120.0, 4140.0, 4160.0, 4140.0, 4140.0]
    assert runner.plan()["microwave_pump_enabled"] is True


def test_park_pump_run_passes_one_isolated_scan_per_arm(monkeypatch, tmp_path):
    runner = importlib.import_module(MODULE)
    calls = []
    monkeypatch.setattr(runner.localizer, "run", lambda **kwargs: calls.append(kwargs))
    runner.run(data_root=tmp_path)
    assert len(calls) == 7
    assert all(call["data_root"] == tmp_path for call in calls)
    assert all(call["parameter_overrides"]["park_pump_us"] == 15.0
               for call in calls)
    assert [call["parameter_overrides"]["park_pump_gain"] for call in calls] == [
        0, 3000, 3000, 0, 3000, 3000, 0]
    assert len({call["parameter_overrides"]["output_suffix"] for call in calls}) == 7


def test_park_pump_can_follow_a_newly_localized_center():
    runner = importlib.import_module(MODULE)
    p = runner.parameters(center_ghz=4.126)
    assert (p["freq_min_ghz"], p["freq_max_ghz"]) == (4.124, 4.128)
    assert [a["frequency_mhz"] for a in runner.arms(center_ghz=4.126)] == [
        4126.0, 4126.0, 4106.0, 4126.0, 4146.0, 4126.0, 4126.0]
