"""Calibrate qubit-mediated feature loading without using active reset."""

import importlib


MODULE = (
    "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners."
    "TLSPumpProbeOnTargetTiming"
)


def test_run_relocalizes_and_repeats_early_interaction_map(monkeypatch, tmp_path):
    runner = importlib.import_module(MODULE)
    calls = []
    monkeypatch.setattr(runner.localizer, "run", lambda **kw: (
        calls.append(kw), tmp_path / f"scan{len(calls)}.csv")[1])
    monkeypatch.setattr(runner.adaptive, "read_scout", lambda _path: [])
    monkeypatch.setattr(runner.adaptive, "select_loss_feature", lambda _rows: {
        "center_ghz": 4.134, "depth": 0.4,
        "depth_scan_up": 0.3, "depth_scan_down": 0.3,
    })

    result = runner.run(data_root=tmp_path)

    assert len(calls) == 6
    panels = [call["parameter_overrides"] for call in calls[1:5]]
    assert [p["decay_delays_us"] for p in panels] == [
        [0.25, 0.5, 1.0], [1.5, 2.5, 4.0],
        [6.0, 10.0, 20.0], [0.25, 0.5, 1.0],
    ]
    assert all(p["reset_mode"] == "passive" for p in panels)
    assert all(p["freq_min_ghz"] == 4.122 for p in panels)
    assert all(p["freq_max_ghz"] == 4.146 for p in panels)
    assert all(p["freq_step_mhz"] == 1.0 for p in panels)
    assert all(p["shots_per_condition"] == 400 for p in panels)
    assert all(not any("pump" in key for key in p) for p in panels)
    assert len({p["output_suffix"] for p in panels}) == 4
    assert result["selected"]["center_ghz"] == 4.134
    assert len(result["panels"]) == 4


def test_plan_explains_this_is_pump_loading_calibration():
    runner = importlib.import_module(MODULE)
    p = runner.plan()
    assert p["pump_mechanism"] == "qubit excitation plus target flux excursion"
    assert p["microwave_tone_enabled"] is False
    assert p["actual_target_holds_us"][0] == [0.35, 0.6, 1.1]
