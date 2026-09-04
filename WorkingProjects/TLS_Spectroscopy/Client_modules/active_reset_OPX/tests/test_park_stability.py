import pytest

from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.park_stability import (
    build_park_probe_config,
    build_frequency_axis_mhz,
    fit_local_frequency_slope,
    fit_sweet_spot_frequency_curve,
    frequency_trace_to_step_response,
    frequency_trace_to_step_response_from_sweet_spot,
    scale_park_compensation,
    summarize_park_trace,
    summarize_target_trace,
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


def test_local_frequency_slope_recovers_linear_tuning_curve():
    result = fit_local_frequency_slope(
        gains=[-25890, -25790, -25690],
        frequencies_mhz=[4371.25, 4367.25, 4363.25],
        min_abs_slope_mhz_per_dac=0.005,
        min_r_squared=0.99,
    )

    assert result["slope_mhz_per_dac"] == pytest.approx(-0.04)
    assert result["r_squared"] == pytest.approx(1.0)
    assert result["center_frequency_mhz"] == pytest.approx(4367.25)


def test_local_frequency_slope_rejects_nonlinear_calibration():
    with pytest.raises(ValueError, match="linear enough"):
        fit_local_frequency_slope(
            gains=[-25890, -25790, -25690],
            frequencies_mhz=[4367.0, 4370.0, 4367.0],
            min_abs_slope_mhz_per_dac=0.005,
            min_r_squared=0.99,
        )


def test_frequency_trace_converts_drift_to_effective_gain_response():
    result = frequency_trace_to_step_response(
        delay_us=[1.0, 10.0, 50.0, 100.0],
        frequency_mhz=[5000.0, 5000.0, 4999.5, 4999.0],
        park_gain=-25000,
        slope_mhz_per_dac=-0.05,
        reference_window_us=10.0,
    )

    assert result["reference_frequency_mhz"] == pytest.approx(5000.0)
    assert result["effective_gain_dac"] == pytest.approx([-25000, -25000, -24990, -24980])
    assert result["step_response"] == pytest.approx([1.0, 1.0, 0.9996, 0.9992])


def test_frequency_trace_rejects_a_nearly_flat_gain_slope():
    with pytest.raises(ValueError, match="slope"):
        frequency_trace_to_step_response(
            delay_us=[1.0, 10.0, 50.0],
            frequency_mhz=[5000.0, 5000.0, 4999.5],
            park_gain=-25000,
            slope_mhz_per_dac=0.0,
            reference_window_us=10.0,
        )


def test_scale_park_compensation_scales_about_unity():
    result = scale_park_compensation(
        {"segment_edges_ns": [0.0, 40000.0], "multipliers": [1.0, 1.1]},
        scale=0.5,
        park_gain=-25000,
        max_abs_gain=32767,
    )

    assert result["segment_edges_ns"] == pytest.approx([0.0, 40000.0])
    assert result["multipliers"] == pytest.approx([1.0, 1.05])
    assert result["commanded_gains_dac"] == [-25000, -26250]


def test_scale_park_compensation_rejects_a_command_beyond_dac_headroom():
    with pytest.raises(ValueError, match="headroom"):
        scale_park_compensation(
            {"segment_edges_ns": [0.0, 40000.0], "multipliers": [1.0, 1.4]},
            scale=1.0,
            park_gain=-25790,
            max_abs_gain=32767,
        )


def test_target_trace_includes_absolute_park_frequency_error():
    result = summarize_target_trace(
        delay_us=[0.5, 20.0, 60.0, 120.0, 160.0],
        frequency_mhz=[4367.5, 4367.4, 4367.0, 4366.8, 4360.0],
        supported=[True] * 5,
        target_frequency_mhz=4367.25,
        reference_window_us=20.0,
        active_reset_window_us=120.0,
        max_allowed_error_mhz=0.5,
    )

    assert result["status"] == "pass"
    assert result["early_frequency_mhz"] == pytest.approx(4367.45)
    assert result["early_target_error_mhz"] == pytest.approx(0.2)
    assert result["max_abs_target_error_mhz"] == pytest.approx(0.45)


def test_target_trace_fails_when_stable_trace_is_at_wrong_frequency():
    result = summarize_target_trace(
        delay_us=[0.5, 20.0, 60.0, 120.0],
        frequency_mhz=[4368.0, 4368.0, 4368.0, 4368.0],
        supported=[True] * 4,
        target_frequency_mhz=4367.25,
        reference_window_us=20.0,
        active_reset_window_us=120.0,
        max_allowed_error_mhz=0.5,
    )

    assert result["status"] == "fail"
    assert result["max_abs_target_error_mhz"] == pytest.approx(0.75)


def test_sweet_spot_curve_recovers_one_sided_quadratic_tuning():
    result = fit_sweet_spot_frequency_curve(
        gains=[-25790, -25540, -25290, -25090],
        frequencies_mhz=[4367.25, 4364.75, 4357.25, 4347.65],
        park_gain=-25790,
        min_frequency_excursion_mhz=2.0,
        min_r_squared=0.98,
    )

    assert result["direction_toward_zero"] == 1
    assert result["curvature_mhz_per_dac_squared"] == pytest.approx(-0.00004)
    assert result["frequency_at_park_mhz"] == pytest.approx(4367.25)
    assert result["r_squared"] == pytest.approx(1.0)


def test_sweet_spot_curve_rejects_points_on_both_sides_of_park():
    with pytest.raises(ValueError, match="toward zero"):
        fit_sweet_spot_frequency_curve(
            gains=[-26040, -25790, -25540, -25290],
            frequencies_mhz=[4364.75, 4367.25, 4364.75, 4357.25],
            park_gain=-25790,
            min_frequency_excursion_mhz=2.0,
            min_r_squared=0.98,
        )


def test_sweet_spot_curve_rejects_insufficient_frequency_excursion():
    with pytest.raises(ValueError, match="excursion"):
        fit_sweet_spot_frequency_curve(
            gains=[-25790, -25540, -25290, -25090],
            frequencies_mhz=[4367.25, 4367.20, 4367.10, 4367.00],
            park_gain=-25790,
            min_frequency_excursion_mhz=2.0,
            min_r_squared=0.0,
        )


def test_frequency_trace_uses_sweet_spot_curvature_to_recover_effective_gain():
    result = frequency_trace_to_step_response_from_sweet_spot(
        delay_us=[1.0, 10.0, 50.0, 100.0],
        frequency_mhz=[4367.25, 4367.25, 4366.85, 4365.65],
        park_gain=-25790,
        frequency_curve={
            "direction_toward_zero": 1,
            "curvature_mhz_per_dac_squared": -0.00004,
            "frequency_at_park_mhz": 4367.25,
        },
        reference_window_us=10.0,
    )

    assert result["directed_offset_dac"] == pytest.approx([0.0, 0.0, 100.0, 200.0])
    assert result["effective_gain_dac"] == pytest.approx([-25790, -25790, -25690, -25590])
    assert result["step_response"] == pytest.approx([
        1.0,
        1.0,
        25690 / 25790,
        25590 / 25790,
    ])
