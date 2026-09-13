import numpy as np
import pytest

from fluxpred.core import Command, Filter
from fluxpred.offline import forecast, blocked_plant_score, common_horizon
from fluxpred.fit import Trace, plant_response


def test_forecast_transports_heldout_residual_without_refitting_it():
    t = np.arange(1000, 498000, 4000)
    tau, plant = [8000, 32000, 128000], [-.01, -.02, .005]
    old = Command([0, 600000], [1])
    measured = plant_response(old, t, tau, plant, probe_ns=500)
    model = Filter(tau, [1], [[.01, .02, -.005]])
    first = forecast(model, 1, plant, Trace(t, measured, old, np.ones(len(t), bool), 500))
    noise = np.sin(np.arange(len(t)))*.001
    second = forecast(model, 1, plant, Trace(t, measured+noise, old, np.ones(len(t), bool), 500))
    assert np.allclose(second-first, noise)


def test_blocked_cv_only_uses_training_responses():
    t = np.arange(1000, 498000, 4000)
    tau, plant = [8000, 32000, 128000], [-.01, -.02, .005]
    cmd = Command([0, 600000], [1])
    y = plant_response(cmd, t, tau, plant)
    tr = Trace(t, y, cmd, np.ones(len(t), bool))
    # The first held-out block leaves exp(-100us/8us) to identify the fast
    # pole; allow floating point amplification far below the 1e-4 target.
    assert blocked_plant_score([tr], tau, regularization=0) < 1e-10


def test_alignment_only_extends_explicit_zero_park():
    a = Command([0, 100, 200], [1, 0])
    b = Command([0, 100, 202], [1, 0])
    aa, bb = common_horizon(a, b)
    assert aa.edges_ns[-1] == bb.edges_ns[-1] == 202
    with pytest.raises(ValueError):
        common_horizon(Command([0, 200], [1]), b)
