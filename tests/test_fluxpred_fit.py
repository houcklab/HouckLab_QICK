import numpy as np
import pytest
from numpy.testing import assert_allclose

from fluxpred.core import Command, render
from fluxpred.fit import Trace, fit_plant, fit_inverse, plant_response, highpass_features, interpolate_plant


def test_known_command_identification_with_dc_nuisance_and_missing_points():
    tau = np.array([8000., 32000., 128000.])
    truth = np.array([-.012, -.025, .009])
    t = np.arange(1000, 500000, 4000)
    cmd = Command([0, 12000, 80000, 600000], [1.03, 1.01, 1])
    y = plant_response(cmd, t, tau, truth, probe_ns=500)+0.007
    support = np.ones(len(t), bool); support[10:15] = False
    y[~support] = np.nan
    tr = Trace(t, y, cmd, support, probe_ns=500)
    fit = fit_plant([tr], tau, regularization=0)
    assert_allclose(fit['coefficients'], truth, atol=1e-11)
    assert fit['offsets'][0] == pytest.approx(0.007)


def test_probe_freezes_last_command_and_keeps_true_time_origin():
    cmd = Command([0, 2000, 100000], [2, 1])
    u, x = highpass_features(cmd, [1000], [8000], probe_ns=4000)
    assert u[0] == 2
    assert x[0, 0] == pytest.approx(2*np.exp(-1000/8000)*2*(1-np.exp(-0.5)))
    # Full waveform changes at 2 us; frozen measurement intentionally does not.


def test_probe_at_exact_edge_freezes_preceding_interval():
    cmd = Command([0, 1000, 100000], [1.3, 1])
    u, x = highpass_features(cmd, [1000], [8000], probe_ns=500)
    assert u[0] == 1.3
    assert x[0, 0] == pytest.approx(1.3*np.exp(-1000/8000)*16*(1-np.exp(-500/8000)))
    assert highpass_features(cmd, [1000], [8000])[0][0] == 1


def test_continuous_probe_integrates_updates_inside_window():
    cmd = Command([0, 1000, 100000], [1.3, 1])
    u, x = highpass_features(cmd, [500], [8000], probe_ns=1000, freeze_probe=False)
    assert u[0] == pytest.approx(1.15)
    expected = 1.3*8*(np.exp(-500/8000)-np.exp(-1500/8000))-.3*8*(1-np.exp(-500/8000))
    assert x[0, 0] == pytest.approx(expected)


def test_inverse_reports_physical_rms_without_design_weight_scaling():
    tau = [8000, 32000, 128000]
    a = [-.01, -.03, .02]
    result = fit_inverse([a], tau)
    cmd, _ = render(result['model'], [(1, 500000)])
    t = (cmd.edges_ns[:-1]+cmd.edges_ns[1:])/2
    rms = np.sqrt(np.mean((plant_response(cmd, t, tau, a)-1)**2))
    assert result['design_rms'] == pytest.approx(rms)


def test_synthetic_stable_inverse_flattens_plant_and_return():
    tau = np.array([8000., 32000., 128000.])
    a = np.array([-.005, -.03, .008])
    inv = fit_inverse([a], tau, regularization=1e-7)
    model = inv['model']
    cmd, state = render(model, [(1, 160000), (0, 800000)])
    t = np.arange(2000, 958000, 4000)
    predicted = plant_response(cmd, t, tau, a)
    desired = (t < 160000).astype(float)
    assert np.sqrt(np.mean((predicted-desired)**2)) < 0.001
    assert abs(predicted[-1]) < 1e-4
    assert np.max(np.abs(state)) < 1e-4


def test_interpolation_and_leave_one_amplitude_out_have_explicit_hull_flag():
    knots = [0.6, 1.0]
    plants = [[-.01, -.03], [-.02, -.04]]
    middle, outside = interpolate_plant(knots, plants, 0.8)
    assert_allclose(middle, [-.015, -.035]); assert not outside
    endpoint, outside = interpolate_plant(knots, plants, 0.5)
    assert_allclose(endpoint, plants[0]); assert outside


def test_fit_refuses_unidentified_and_nonfinite_parameters():
    t = np.arange(1000, 50000, 4000)
    tr = Trace(t, np.ones(len(t)), Command([0, 60000], [0]), np.ones(len(t), bool))
    with pytest.raises(ValueError, match="rank"):
        fit_plant([tr], [8000, 32000])
    with pytest.raises(ValueError):
        fit_plant([tr], [8000, 32000], regularization=-1)
    with pytest.raises(ValueError):
        fit_inverse([[float('nan')]], [8000])
    with pytest.raises(ValueError):
        Trace(t, np.ones(len(t)), tr.command, np.full(len(t), np.nan))
