import numpy as np
import pytest

from fluxpred.core import Command, Filter, compare_commands, render, tail_bound


def single_pole(tau_ns, coefficient, resolution_ns=1000.0):
    return Filter([tau_ns], [1.0], [[coefficient]], resolution_ns=resolution_ns)


def test_single_pole_step_matches_closed_form():
    tau, c = 40_000.0, 0.1
    model = single_pole(tau, c)
    duration = 10_000.0
    command, state = render(model, [(1.0, duration)], sample_ns=duration)
    expected_state = c * (1.0 - np.exp(-duration / tau))
    assert state == pytest.approx([expected_state], rel=0, abs=1e-14)
    expected_mean = 1.0 + c * tau / duration * (1.0 - np.exp(-duration / tau))
    assert command.values[0] == pytest.approx(expected_mean, rel=1e-13)


def test_finer_sampling_reaches_the_same_state():
    model = single_pole(40_000.0, 0.1)
    _, coarse = render(model, [(1.0, 20_000.0)], sample_ns=20_000.0)
    _, fine = render(model, [(1.0, 20_000.0)], sample_ns=250.0)
    assert coarse == pytest.approx(fine, abs=1e-12)


def test_state_is_continuous_through_target_and_return_edges():
    model = single_pole(40_000.0, 0.1)
    hold, recovery = 30_000.0, 120_000.0
    _, split = render(model, [(1.0, hold)], sample_ns=1000.0)
    _, continued = render(model, [(0.0, recovery)], initial_state=split, sample_ns=1000.0)
    _, whole = render(model, [(1.0, hold), (0.0, recovery)], sample_ns=1000.0)
    assert continued == pytest.approx(whole, abs=1e-12)


def test_return_command_depends_on_the_hold_duration():
    model = single_pole(40_000.0, 0.1)
    short, _ = render(model, [(1.0, 5_000.0), (0.0, 50_000.0)], sample_ns=1000.0)
    long, _ = render(model, [(1.0, 200_000.0), (0.0, 50_000.0)], sample_ns=1000.0)
    short_return = short.values[short.edges_ns[:-1] >= 5_000.0][0]
    long_return = long.values[long.edges_ns[:-1] >= 200_000.0][0]
    assert short_return != pytest.approx(long_return, abs=1e-9)


def test_filter_state_is_not_reset_at_the_return_edge():
    model = single_pole(40_000.0, 0.1)
    command, _ = render(model, [(1.0, 30_000.0), (0.0, 30_000.0)], sample_ns=30_000.0)
    reset_value = 0.0 + np.sum((model.potential(0.0) - np.zeros(1)) * model.taus_ns / 30_000.0
                               * -np.expm1(-30_000.0 / model.taus_ns))
    assert command.values[1] != pytest.approx(reset_value, abs=1e-9)
    assert command.values[1] < 0.0


def test_dc_gain_is_exactly_one_for_a_settled_hold():
    model = Filter([20_000.0, 80_000.0], [1.0], [[0.1, -0.05]], resolution_ns=1000.0)
    command, state = render(model, [(0.7, 4_000_000.0)], sample_ns=20_000.0)
    assert command.values[-1] == pytest.approx(0.7, abs=1e-12)
    assert state == pytest.approx(model.potential(0.7), abs=1e-12)
    assert tail_bound(state) == pytest.approx(0.7 * 0.15, abs=1e-12)


def test_zero_desired_amplitude_has_zero_potential():
    model = Filter([20_000.0, 80_000.0], [0.5, 1.0], [[0.05, -0.02], [0.08, -0.03]],
                   resolution_ns=1000.0)
    assert model.potential(0.0) == pytest.approx([0.0, 0.0])


@pytest.mark.parametrize("taus", [[-1000.0], [0.0], [80_000.0, 20_000.0], [20_000.0, 20_000.0]])
def test_invalid_time_constants_are_rejected(taus):
    with pytest.raises(ValueError):
        Filter(taus, [1.0], [[0.0] * len(taus)], resolution_ns=1000.0)


def test_coefficient_l1_overflow_is_rejected():
    with pytest.raises(ValueError, match="L1"):
        Filter([20_000.0, 80_000.0], [1.0], [[0.2, 0.2]], resolution_ns=1000.0)


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_nonfinite_coefficients_are_rejected(bad):
    with pytest.raises(ValueError):
        Filter([20_000.0], [1.0], [[bad]], resolution_ns=1000.0)


@pytest.mark.parametrize("bad", [np.nan, np.inf])
def test_nonfinite_command_values_are_rejected(bad):
    with pytest.raises(ValueError):
        Command([0.0, 10.0], [bad])


def test_amplitude_outside_the_calibrated_range_is_rejected():
    model = single_pole(20_000.0, 0.05)
    with pytest.raises(ValueError, match="calibrated"):
        model.potential(1.5)
    with pytest.raises(ValueError, match="calibrated"):
        model.potential(-0.1)


def test_tail_bound_is_the_state_l1_norm():
    assert tail_bound([0.03, -0.04]) == pytest.approx(0.07)


def test_filter_json_round_trip_preserves_every_field():
    model = Filter([20_000.0, 80_000.0], [0.5, 1.0], [[0.05, -0.02], [0.08, -0.03]],
                   resolution_ns=1000.0, max_l1=0.3)
    restored = Filter.from_dict(model.to_dict())
    assert restored.taus_ns == pytest.approx(model.taus_ns)
    assert restored.amplitudes == pytest.approx(model.amplitudes)
    assert restored.coefficients == pytest.approx(model.coefficients)
    assert restored.resolution_ns == model.resolution_ns
    assert restored.max_l1 == model.max_l1


def test_filter_from_dict_rejects_a_foreign_algorithm():
    model = Filter([20_000.0], [1.0], [[0.05]], resolution_ns=1000.0)
    document = model.to_dict()
    document["algorithm"] = "some_other_inverse"
    with pytest.raises(ValueError, match="algorithm"):
        Filter.from_dict(document)


def test_filter_from_dict_rejects_a_future_schema_version():
    model = Filter([20_000.0], [1.0], [[0.05]], resolution_ns=1000.0)
    document = model.to_dict()
    document["schema_version"] = 2
    with pytest.raises(ValueError, match="schema"):
        Filter.from_dict(document)


def test_compare_commands_reports_an_exactly_displaced_edge():
    a = Command([0.0, 100.0, 200.0], [1.0, 0.0])
    b = Command([0.0, 104.0, 200.0], [1.0, 0.0])
    difference = compare_commands(a, b)
    assert difference["max_abs"] == pytest.approx(1.0)
    assert difference["integrated_abs_ns"] == pytest.approx(4.0)
    assert difference["rms"] == pytest.approx(np.sqrt(4.0 / 200.0))


def test_compare_commands_rejects_different_horizons():
    with pytest.raises(ValueError, match="horizons"):
        compare_commands(Command([0.0, 100.0], [1.0]), Command([0.0, 200.0], [1.0]))


def test_segment_budget_is_enforced():
    model = single_pole(20_000.0, 0.05)
    with pytest.raises(ValueError, match="budget"):
        render(model, [(1.0, 1_000_000.0)], sample_ns=1.0, max_segments=100)


def test_requested_hold_is_never_extended_to_the_sample_grid():
    model = single_pole(20_000.0, 0.05)
    command, _ = render(model, [(1.0, 2_500.0), (0.0, 2_500.0)], sample_ns=1_000.0)
    assert command.edges_ns[-1] == pytest.approx(5_000.0)
    assert np.any(np.isclose(command.edges_ns, 2_500.0))
