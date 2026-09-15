import numpy as np
import pytest

from fluxpred.core import Command, Filter, render
from fluxpred.fit import Trace, fit_inverse, fit_plant, highpass_features, plant_response
from fluxpred import offline

TAUS_NS = np.array([8_000.0, 24_000.0, 64_000.0, 192_000.0])
TRUE_PLANT = np.array([0.06, -0.04, 0.03, -0.02])
HOLD_NS = 200_000.0
RECOVERY_NS = 600_000.0
HORIZON_NS = HOLD_NS + RECOVERY_NS


def step_command(amplitude=1.0, horizon_ns=HORIZON_NS):
    return Command([0.0, horizon_ns], [amplitude])


def round_trip_command(amplitude=1.0, hold_ns=HOLD_NS, recovery_ns=RECOVERY_NS):
    return Command([0.0, hold_ns, hold_ns + recovery_ns], [amplitude, 0.0])


def synthetic_trace(*, plant=TRUE_PLANT, amplitude=1.0, noise=0.0, seed=0, probe_ns=400.0,
                    samples=600, command=None, offset=0.0):
    command = round_trip_command(amplitude) if command is None else command
    horizon = float(command.edges_ns[-1])
    time_ns = np.linspace(0.0, horizon - probe_ns, samples)
    response = plant_response(command, time_ns, TAUS_NS, plant, probe_ns=probe_ns) + offset
    if noise:
        response = response + np.random.default_rng(seed).normal(0.0, noise, response.shape)
    return Trace(time_ns, response, command, np.ones(samples, dtype=bool), probe_ns)


def test_plant_fit_recovers_known_coefficients_without_noise():
    fit = fit_plant([synthetic_trace()], TAUS_NS, regularization=1e-12)
    assert fit["coefficients"] == pytest.approx(TRUE_PLANT, abs=1e-6)
    assert fit["rms"] < 1e-9


def test_plant_fit_recovers_known_coefficients_from_noisy_data():
    traces = [synthetic_trace(noise=2e-4, seed=seed) for seed in range(3)]
    fit = fit_plant(traces, TAUS_NS, regularization=1e-6)
    assert fit["coefficients"] == pytest.approx(TRUE_PLANT, abs=6e-3)


def test_static_offset_is_absorbed_and_reported_not_treated_as_gain():
    fit = fit_plant([synthetic_trace(offset=0.01)], TAUS_NS, regularization=1e-12)
    assert fit["coefficients"] == pytest.approx(TRUE_PLANT, abs=1e-6)
    assert fit["offsets"][0] == pytest.approx(0.01, abs=1e-6)


def test_masked_low_contrast_samples_do_not_contaminate_the_fit():
    trace = synthetic_trace()
    corrupted = np.array(trace.response, dtype=float)
    support = np.array(trace.support)
    corrupted[50:90] = 12.0
    support[50:90] = False
    fit = fit_plant([Trace(trace.time_ns, corrupted, trace.command, support, trace.probe_ns)],
                    TAUS_NS, regularization=1e-12)
    assert fit["coefficients"] == pytest.approx(TRUE_PLANT, abs=1e-6)


def test_unmasked_low_contrast_samples_fail_closed_instead_of_biasing_the_model():
    trace = synthetic_trace()
    corrupted = np.array(trace.response, dtype=float)
    corrupted[50:90] = 12.0
    with pytest.raises(ValueError, match="L1"):
        fit_plant([Trace(trace.time_ns, corrupted, trace.command, trace.support, trace.probe_ns)],
                  TAUS_NS, regularization=1e-12)


def test_plant_fit_rejects_an_over_l1_model():
    huge = np.array([0.2, 0.2, 0.2, 0.2])
    with pytest.raises(ValueError, match="L1"):
        fit_plant([synthetic_trace(plant=huge)], TAUS_NS, regularization=1e-12)


def test_plant_fit_rejects_negative_time_constants():
    with pytest.raises(ValueError):
        fit_plant([synthetic_trace()], np.array([-8_000.0, 24_000.0]))


def test_plant_fit_requires_enough_supported_samples():
    trace = synthetic_trace(samples=400)
    support = np.zeros(400, dtype=bool)
    support[:4] = True
    with pytest.raises(ValueError, match="insufficient"):
        fit_plant([Trace(trace.time_ns, trace.response, trace.command, support, trace.probe_ns)],
                  TAUS_NS)


def test_blocked_cross_validation_prefers_the_generating_bank():
    traces = [synthetic_trace(noise=1e-4, seed=seed) for seed in range(2)]
    matched = offline.blocked_plant_score(traces, TAUS_NS, regularization=1e-6)
    shifted = offline.blocked_plant_score(
        traces, np.array([12_000.0, 40_000.0, 120_000.0, 360_000.0]), regularization=1e-6)
    slow_pair = offline.blocked_plant_score(traces, TAUS_NS[2:], regularization=1e-6)
    assert matched < shifted
    assert matched < slow_pair
    assert matched == pytest.approx(1e-4, rel=0.5)


def test_an_outbound_only_trace_cannot_discriminate_pole_banks():
    outbound = [synthetic_trace(noise=1e-4, seed=seed, command=step_command())
                for seed in range(2)]
    matched = offline.blocked_plant_score(outbound, TAUS_NS, regularization=1e-6)
    slow_pair = offline.blocked_plant_score(outbound, TAUS_NS[2:], regularization=1e-6)
    assert slow_pair < 2.0 * matched


def test_bank_selection_returns_a_finite_choice_with_an_audit_table():
    traces = [synthetic_trace(noise=1e-4, seed=seed) for seed in range(2)]
    banks = [np.asarray(bank) * 1000.0 for bank in offline.CANDIDATE_BANKS_US]
    chosen = offline.select_plant_bank(traces, banks, regularizations=(1e-6, 1e-4), folds=4)
    assert np.isfinite(chosen["held_out_rms"])
    assert chosen["taus_ns"].size == 4
    assert len(chosen["table"]) == 4
    assert all("held_out_rms" in row for row in chosen["table"])


def test_bank_selection_prefers_the_simpler_bank_when_both_are_adequate():
    two_pole = np.array([0.06, -0.04, 0.0, 0.0])
    traces = [synthetic_trace(plant=two_pole, noise=1e-4, seed=seed) for seed in range(2)]
    chosen = offline.select_plant_bank(
        traces, [TAUS_NS, TAUS_NS[:2]], regularizations=(1e-6,), folds=5, simpler_within=0.05)
    assert chosen["taus_ns"].size == 2


def test_bank_selection_records_a_rejected_candidate_instead_of_using_it():
    traces = [synthetic_trace(noise=1e-4, seed=seed) for seed in range(2)]
    unstable = np.array([-8_000.0, 24_000.0, 64_000.0, 192_000.0])
    chosen = offline.select_plant_bank(
        traces, [TAUS_NS, unstable], regularizations=(1e-6,), folds=5)
    rejected = [row for row in chosen["table"] if row["rejected"] is not None]
    assert len(rejected) == 1
    assert rejected[0]["taus_ns"] == unstable.tolist()
    assert not np.isfinite(rejected[0]["held_out_rms"])
    assert chosen["taus_ns"].tolist() == TAUS_NS.tolist()


def test_bank_selection_fails_when_every_candidate_is_rejected():
    traces = [synthetic_trace(noise=1e-4, seed=0)]
    with pytest.raises(ValueError, match="no candidate pole bank"):
        offline.select_plant_bank(
            traces, [np.array([-8_000.0, 24_000.0])], regularizations=(1e-6,), folds=5)


def test_bank_selection_rejects_an_all_singular_candidate_set():
    traces = [synthetic_trace()]
    with pytest.raises(ValueError, match="at least one candidate"):
        offline.select_plant_bank(traces, [], regularizations=(1e-6,))


def test_inverse_cancels_the_identified_plant_on_held_out_time_blocks():
    inverse = fit_inverse([TRUE_PLANT], TAUS_NS, regularization=1e-9,
                          horizon_ns=HORIZON_NS, sample_ns=2000.0)
    model = inverse["model"]
    result = offline.inverse_cancellation(
        model, TRUE_PLANT, amplitude=1.0, horizon_ns=HORIZON_NS, sample_ns=2000.0, probe_ns=400.0)
    assert result["corrected_rms"] < 0.1 * result["uncorrected_rms"]
    assert result["corrected_late_mean"] == pytest.approx(1.0, abs=2e-3)


def test_fitted_inverse_obeys_the_l1_and_stability_bounds():
    inverse = fit_inverse([TRUE_PLANT], TAUS_NS, regularization=1e-9,
                          horizon_ns=HORIZON_NS, sample_ns=2000.0)
    model = inverse["model"]
    assert np.sum(np.abs(model.coefficients)) <= model.max_l1 + 1e-12
    assert np.all(model.taus_ns > 0)
    assert Filter.from_dict(model.to_dict()).coefficients == pytest.approx(model.coefficients)


def test_round_trip_simulation_settles_at_park_with_continuous_state():
    inverse = fit_inverse([TRUE_PLANT], TAUS_NS, regularization=1e-9,
                          horizon_ns=HORIZON_NS, sample_ns=2000.0)
    result = offline.simulate_round_trip(
        inverse["model"], TRUE_PLANT, amplitude=1.0, hold_ns=200_000.0,
        recovery_ns=1_600_000.0, sample_ns=2000.0, probe_ns=400.0)
    assert result["park_error_rms"] < 0.02
    assert result["tail_bound"] < 1e-3
    assert np.abs(result["response"][-1]) < 5e-3


def test_round_trip_return_differs_when_the_hold_changes():
    inverse = fit_inverse([TRUE_PLANT], TAUS_NS, regularization=1e-9,
                          horizon_ns=HORIZON_NS, sample_ns=2000.0)
    model = inverse["model"]
    short = offline.simulate_round_trip(model, TRUE_PLANT, amplitude=1.0, hold_ns=40_000.0,
                                        recovery_ns=400_000.0, sample_ns=2000.0)
    long = offline.simulate_round_trip(model, TRUE_PLANT, amplitude=1.0, hold_ns=200_000.0,
                                       recovery_ns=400_000.0, sample_ns=2000.0)
    short_return = short["command"].values[short["command"].edges_ns[:-1] >= 40_000.0][0]
    long_return = long["command"].values[long["command"].edges_ns[:-1] >= 200_000.0][0]
    assert short_return != pytest.approx(long_return, abs=1e-9)


def test_repeated_traces_expose_drift_instead_of_silently_averaging():
    base = synthetic_trace()
    drifted = Trace(base.time_ns, base.response + 0.01, base.command, base.support, base.probe_ns)
    fit = fit_plant([base, drifted], TAUS_NS, regularization=1e-12)
    assert fit["offsets"] == pytest.approx([0.0, 0.01], abs=1e-6)
    assert abs(fit["offsets"][1] - fit["offsets"][0]) == pytest.approx(0.01, abs=1e-6)


def test_forecast_retains_the_measured_residual():
    inverse = fit_inverse([TRUE_PLANT], TAUS_NS, regularization=1e-9,
                          horizon_ns=HORIZON_NS, sample_ns=2000.0)
    trace = synthetic_trace()
    residual = 0.005
    noisy = Trace(trace.time_ns, trace.response + residual, trace.command, trace.support,
                  trace.probe_ns)
    forecast = offline.forecast(inverse["model"], 1.0, TRUE_PLANT, noisy, sample_ns=2000.0)
    assert np.mean(forecast - noisy.response) != pytest.approx(0.0, abs=1e-9)
    assert np.all(np.isfinite(forecast))


def test_highpass_features_frozen_probe_latches_the_pre_probe_level():
    command = Command([0.0, 1000.0, 2000.0], [1.0, 0.0])
    u, _ = highpass_features(command, np.array([999.0]), TAUS_NS, probe_ns=100.0)
    assert u == pytest.approx([1.0])


def test_highpass_features_reject_a_probe_past_the_horizon():
    command = Command([0.0, 1000.0], [1.0])
    with pytest.raises(ValueError, match="extends beyond command horizon"):
        highpass_features(command, np.array([950.0]), TAUS_NS, probe_ns=100.0, freeze_probe=False)


def test_render_and_plant_response_agree_on_an_uncorrected_step():
    zero = Filter(TAUS_NS, [1.0], [np.zeros(4)], resolution_ns=2000.0)
    command, _ = render(zero, [(1.0, HORIZON_NS)], sample_ns=2000.0)
    time_ns = np.linspace(0.0, HORIZON_NS - 400.0, 200)
    rendered = plant_response(command, time_ns, TAUS_NS, TRUE_PLANT, probe_ns=400.0)
    direct = plant_response(step_command(), time_ns, TAUS_NS, TRUE_PLANT, probe_ns=400.0)
    assert rendered == pytest.approx(direct, abs=1e-9)
