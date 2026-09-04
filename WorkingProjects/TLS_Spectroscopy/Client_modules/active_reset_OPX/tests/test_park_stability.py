import pytest

from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.park_stability import (
    build_park_probe_config,
    build_frequency_axis_mhz,
    summarize_park_trace,
)


def test_frequency_axis_is_centered_and_includes_both_requested_edges():
    axis = build_frequency_axis_mhz(center_mhz=4367.25, half_span_mhz=25.0, step_mhz=0.5)

    assert len(axis) == 101
    assert axis[0] == pytest.approx(4342.25)
    assert axis[-1] == pytest.approx(4392.25)
    assert axis[50] == pytest.approx(4367.25)


@pytest.mark.parametrize(
    "half_span_mhz,step_mhz",
    [(0.0, 0.5), (25.0, 0.0), (25.0, -0.5)],
)
def test_frequency_axis_rejects_nonpositive_span_or_step(half_span_mhz, step_mhz):
    with pytest.raises(ValueError, match="positive"):
        build_frequency_axis_mhz(4367.25, half_span_mhz, step_mhz)


def test_probe_config_uses_zero_baseline_and_measures_while_park_is_held():
    cfg = build_park_probe_config(
        {
            "ff_park_gain": -25790,
            "qubit_pulse_style": "arb",
            "qubit_gain": 11100,
            "qubit_length": 0.25,
            "relax_delay": 1000.0,
            "flux_tail_compensation": {"stale": True},
        },
        park_gain=-25790,
        frequency_axis_mhz=[4342.25, 4342.75, 4343.25],
        shots=100,
        spectroscopy_gain=15000,
        spectroscopy_length_us=0.5,
        passive_reset_us=400.0,
    )

    assert cfg["ff_gain"] == -25790
    assert cfg["ff_park_gain"] == 0
    assert cfg["readout_after_park"] is False
    assert cfg["relax_delay"] == pytest.approx(400.0)
    assert cfg["baseline_rearm_us"] == pytest.approx(0.05)
    assert cfg["qubit_pulse_style"] == "const"
    assert cfg["qubit_gain"] == 15000
    assert cfg["qubit_length"] == pytest.approx(0.5)
    assert cfg["start"] == pytest.approx(4342.25)
    assert cfg["step"] == pytest.approx(0.5)
    assert cfg["expts"] == 3
    assert cfg["reps"] == 100
    assert "flux_tail_compensation" not in cfg


@pytest.mark.parametrize("park_gain", [0, -32768, 32768])
def test_probe_config_rejects_zero_or_out_of_range_park_gain(park_gain):
    with pytest.raises(ValueError, match="park_gain"):
        build_park_probe_config(
            {},
            park_gain=park_gain,
            frequency_axis_mhz=[4342.25, 4342.75, 4343.25],
            shots=100,
            spectroscopy_gain=15000,
            spectroscopy_length_us=0.5,
            passive_reset_us=400.0,
        )


def test_park_trace_passes_when_reset_window_stays_within_drift_limit():
    summary = summarize_park_trace(
        delay_us=[0.5, 10.0, 40.0, 80.0, 120.0, 160.0],
        frequency_mhz=[4367.25, 4367.20, 4367.10, 4366.95, 4366.85, 4350.0],
        supported=[True] * 6,
        sweep_min_mhz=4342.25,
        sweep_max_mhz=4392.25,
        active_reset_window_us=120.0,
        max_allowed_drift_mhz=0.5,
        edge_guard_mhz=1.0,
    )

    assert summary["status"] == "pass"
    assert summary["points_in_reset_window"] == 5
    assert summary["reference_frequency_mhz"] == pytest.approx(4367.25)
    assert summary["max_abs_drift_mhz"] == pytest.approx(0.4)
    assert summary["peak_to_peak_mhz"] == pytest.approx(0.4)
    assert summary["outside_window_points"] == 1


def test_park_trace_fails_when_reset_window_exceeds_drift_limit():
    summary = summarize_park_trace(
        delay_us=[0.5, 20.0, 60.0, 120.0],
        frequency_mhz=[4367.25, 4366.9, 4366.3, 4365.8],
        supported=[True] * 4,
        sweep_min_mhz=4342.25,
        sweep_max_mhz=4392.25,
        active_reset_window_us=120.0,
        max_allowed_drift_mhz=0.5,
        edge_guard_mhz=1.0,
    )

    assert summary["status"] == "fail"
    assert summary["max_abs_drift_mhz"] == pytest.approx(1.45)


def test_park_trace_is_inconclusive_when_resonance_reaches_sweep_edge():
    summary = summarize_park_trace(
        delay_us=[0.5, 40.0, 120.0],
        frequency_mhz=[4367.25, 4350.0, 4342.75],
        supported=[True] * 3,
        sweep_min_mhz=4342.25,
        sweep_max_mhz=4392.25,
        active_reset_window_us=120.0,
        max_allowed_drift_mhz=0.5,
        edge_guard_mhz=1.0,
    )

    assert summary["status"] == "inconclusive_sweep_edge"
    assert summary["edge_limited"] is True


def test_park_trace_is_inconclusive_with_fewer_than_three_supported_window_points():
    summary = summarize_park_trace(
        delay_us=[0.5, 40.0, 120.0],
        frequency_mhz=[4367.25, float("nan"), 4367.1],
        supported=[True, False, True],
        sweep_min_mhz=4342.25,
        sweep_max_mhz=4392.25,
        active_reset_window_us=120.0,
        max_allowed_drift_mhz=0.5,
        edge_guard_mhz=1.0,
    )

    assert summary["status"] == "inconclusive_insufficient_trace"
    assert summary["points_in_reset_window"] == 2


def test_park_trace_rejects_mismatched_vectors():
    with pytest.raises(ValueError, match="matching lengths"):
        summarize_park_trace(
            delay_us=[0.5, 10.0],
            frequency_mhz=[4367.25],
            supported=[True, True],
            sweep_min_mhz=4342.25,
            sweep_max_mhz=4392.25,
            active_reset_window_us=120.0,
            max_allowed_drift_mhz=0.5,
        )
