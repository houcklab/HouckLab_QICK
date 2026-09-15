import numpy as np
import pytest

from fluxpred import cryoscope


def transmon(coordinate, f_max=5.2, ec=0.22, period=1.0, offset=0.0, d=0.1):
    x = np.asarray(coordinate, dtype=float)
    ej_max = (f_max + ec) ** 2 / (8.0 * ec)
    phase = np.pi * (x - offset) / period
    ej = ej_max * np.sqrt(np.cos(phase) ** 2 + d ** 2 * np.sin(phase) ** 2)
    return np.sqrt(8.0 * ej * ec) - ec


def test_bloch_components_invert_the_assignment_reference():
    x, y = cryoscope.bloch_components([0.75], [0.25], p_ground=0.05, p_excited=0.95)
    assert x == pytest.approx([2.0 * (0.75 - 0.05) / 0.9 - 1.0])
    assert y == pytest.approx([2.0 * (0.25 - 0.05) / 0.9 - 1.0])


def test_bloch_components_reject_a_collapsed_reference():
    with pytest.raises(ValueError, match="contrast"):
        cryoscope.bloch_components([0.5], [0.5], p_ground=0.48, p_excited=0.50)


def test_support_mask_drops_low_contrast_points():
    x = np.array([1.0, 0.05, 0.8])
    y = np.array([0.0, 0.02, 0.6])
    mask = cryoscope.support_mask(x, y, threshold=0.25)
    assert mask.tolist() == [True, False, True]


def test_unwrap_is_applied_only_to_supported_samples():
    phase = np.array([3.0, 0.0, -3.0, -2.9])
    mask = np.array([True, False, True, True])
    unwrapped = cryoscope.unwrap_masked(phase, mask)
    assert np.isnan(unwrapped[1])
    assert unwrapped[2] == pytest.approx(-3.0 + 2.0 * np.pi)
    assert abs(unwrapped[2] - unwrapped[0]) < np.pi


def test_unwrap_needs_two_supported_samples():
    with pytest.raises(ValueError, match="two supported"):
        cryoscope.unwrap_masked(np.array([0.1, 0.2]), np.array([True, False]))


def test_fixed_window_detuning_is_the_phase_over_the_window():
    detuning = cryoscope.detuning_from_window(np.array([np.pi]), 500.0)
    assert detuning == pytest.approx([1.0])


def test_window_unambiguous_range():
    assert cryoscope.window_unambiguous_range_mhz(500.0) == pytest.approx(1.0)
    assert cryoscope.window_unambiguous_range_mhz(50.0) == pytest.approx(10.0)


def test_multiwindow_branch_resolution_recovers_a_wrapped_detuning():
    truth_mhz = np.array([6.0, 4.0, 2.5, 1.0, 0.2])
    coarse_ns, fine_ns = 40.0, 400.0
    coarse = np.angle(np.exp(1j * 2 * np.pi * truth_mhz * coarse_ns / 1000.0))
    fine = np.angle(np.exp(1j * 2 * np.pi * truth_mhz * fine_ns / 1000.0))
    resolved = cryoscope.resolve_branch(fine, fine_ns, coarse, coarse_ns)
    assert resolved["detuning_mhz"] == pytest.approx(truth_mhz, abs=1e-9)
    assert resolved["ambiguous_count"] == 0


def test_branch_resolution_flags_an_inconsistent_pair():
    coarse = np.array([0.0])
    fine = np.array([0.0])
    resolved = cryoscope.resolve_branch(fine, 400.0, coarse + np.pi / 2, 40.0)
    assert resolved["ambiguous_count"] == 1


def test_branch_resolution_requires_a_longer_fine_window():
    with pytest.raises(ValueError, match="longer"):
        cryoscope.resolve_branch(np.array([0.0]), 40.0, np.array([0.0]), 400.0)


def test_smooth_derivative_recovers_a_linear_phase_ramp():
    time_ns = np.arange(0.0, 2000.0, 20.0)
    slope_mhz = 0.75
    phase = 2 * np.pi * slope_mhz * time_ns / 1000.0
    detuning = cryoscope.smooth_derivative(time_ns, phase, window=9)
    assert detuning == pytest.approx(np.full_like(time_ns, slope_mhz), abs=1e-8)


def test_smooth_derivative_requires_a_uniform_grid():
    time_ns = np.array([0.0, 10.0, 30.0, 60.0, 100.0, 150.0, 210.0])
    with pytest.raises(ValueError, match="uniform"):
        cryoscope.smooth_derivative(time_ns, np.zeros_like(time_ns), window=5)


def test_static_model_inversion_round_trips():
    park, target = 0.0, 0.35
    coordinates = np.linspace(park, target, 11)
    frequency = transmon(coordinates)
    recovered, outside = cryoscope.invert_static_model(frequency, transmon, park=park, target=target)
    assert recovered == pytest.approx(coordinates, abs=2e-6)
    assert not outside.any()


def test_static_model_inversion_flags_out_of_branch_frequencies():
    park, target = 0.0, 0.35
    _, outside = cryoscope.invert_static_model(np.array([99.0]), transmon, park=park, target=target)
    assert outside.tolist() == [True]


def test_static_model_inversion_rejects_a_non_monotonic_branch():
    park, target = -0.4, 0.4
    with pytest.raises(ValueError, match="monotonic"):
        cryoscope.invert_static_model(np.array([5.0]), transmon, park=park, target=target)


def test_branch_extension_stops_at_the_sweet_spot():
    grid, values = cryoscope.local_monotonic_branch(transmon, park=0.0, target=0.35)
    assert grid.min() == pytest.approx(0.0, abs=1e-9)
    assert grid.max() > 0.35
    assert np.all(np.diff(values) > 0)


def test_normalized_amplitude_is_zero_at_park_and_one_at_target():
    park, target = 0.0, 0.35
    amplitude, _ = cryoscope.normalized_amplitude(
        transmon(np.array([park, target])), transmon, park=park, target=target)
    assert amplitude == pytest.approx([0.0, 1.0], abs=1e-5)


def test_nominal_detuning_matches_the_ideal_command():
    park, target = 0.0, 0.35
    probe = float(transmon(target))
    nominal = cryoscope.nominal_detuning_mhz(
        np.array([0.0, 1.0]), transmon, park=park, target=target, probe_frequency_ghz=probe)
    assert nominal[1] == pytest.approx(0.0, abs=1e-9)
    assert nominal[0] == pytest.approx((transmon(park) - probe) * 1000.0)


def test_trace_from_measurement_recovers_a_known_normalized_amplitude():
    park, target = 0.0, 0.35
    probe = float(transmon(target))
    delays = np.arange(1, 21, dtype=float) * 1000.0
    truth = 1.0 - 0.04 * np.exp(-delays / 8000.0)
    residual_mhz = (transmon(park + truth * (target - park)) - probe) * 1000.0
    window = 400.0
    phase = 2 * np.pi * residual_mhz * window / 1000.0
    trace = cryoscope.trace_from_measurement(
        delays_ns=delays, phase_rad=phase, mask=np.ones_like(delays, dtype=bool),
        probe_window_ns=window, probe_frequency_ghz=probe, frequency_of_coordinate=transmon,
        park=park, target=target)
    assert trace["normalized_amplitude"] == pytest.approx(truth, abs=2e-5)
    assert trace["support"].all()
    assert trace["supported_fraction"] == pytest.approx(1.0)


def test_trace_marks_samples_outside_the_static_model_as_unsupported():
    park, target = 0.0, 0.35
    probe = float(transmon(target))
    delays = np.array([1000.0, 2000.0])
    phase = np.array([0.0, 2.0 * np.pi * 8000.0 * 400.0 / 1000.0])
    trace = cryoscope.trace_from_measurement(
        delays_ns=delays, phase_rad=phase, mask=np.ones(2, dtype=bool),
        probe_window_ns=400.0, probe_frequency_ghz=probe, frequency_of_coordinate=transmon,
        park=park, target=target)
    assert trace["support"][0]
    assert not trace["support"][1]


def test_phase_uncertainty_propagates_shot_noise():
    sigma = cryoscope.phase_uncertainty(np.array([1.0]), np.array([0.0]),
                                        np.array([0.1]), np.array([0.2]))
    assert sigma == pytest.approx([0.2])


def test_phase_uncertainty_is_infinite_at_the_origin():
    sigma = cryoscope.phase_uncertainty(np.array([0.0]), np.array([0.0]),
                                        np.array([0.1]), np.array([0.1]))
    assert np.isinf(sigma[0])


def test_shot_noise_sigma_matches_the_binomial_form():
    assert cryoscope.shot_noise_sigma([0.5], 100) == pytest.approx([0.05])


def test_drift_report_separates_between_and_within_repeat_spread():
    base = np.array([1.0, 1.0, 1.0, 1.0])
    repeats = np.vstack([base, base + 0.02, base - 0.02])
    report = cryoscope.drift_report(repeats)
    assert report["between_repeat_range"] == pytest.approx(0.04)
    assert report["supported_samples"] == 4


def test_drift_report_needs_two_repeats():
    with pytest.raises(ValueError, match="at least two"):
        cryoscope.drift_report(np.ones((1, 4)))
