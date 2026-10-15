"""Hardware-free tests for the T1 / T2E IQ rotation (docs/concepts/iq_conventions.md section 3):
the closed-form principal-axis phase replaces the min-Q-peak-to-peak grid search, its sign puts
the first (most excited) point above the trace mean, it shares its axis with the Rabi rotation,
and fixed min_max levels are applied only with a fixed rotation_angle.

    python -m pytest tests/test_decay_axis_phase.py
"""

import os

import matplotlib

matplotlib.use("Agg")

import h5py
import numpy as np
import pytest

from qicklab.analysis.iq import decay_axis_phase, min_q_range_phase
from qicklab.core.experiment import finish
from qicklab.experiments.rabi import iq_rotation_angle
from qicklab.experiments.t1 import T1FF
from qicklab.experiments.t2_echo import T2EMUX

X = np.arange(100) * 5.0  # 0 ... 495 us, the T1 defaults
T = 80.0
OFFSET = 0.4 - 0.7j  # readout background: the rotation must not depend on it


def _trace(axis, noise=0.0, seed=0, contrast=1.0):
    """Decay of `contrast` along the IQ direction `axis` (|e> at axis, decaying to |g>)."""
    rng = np.random.default_rng(seed)
    z = contrast * np.exp(-X / T) * np.exp(1j * axis) + OFFSET
    z = z + noise * (rng.normal(size=X.size) + 1j * rng.normal(size=X.size))
    return z.real, z.imag


def _legacy_min_q_range(i, q, n=200):
    """The pre-2026-10 estimator: grid phase in [0, pi] minimising the peak-to-peak of Q."""
    z = i + 1j * q
    phases = np.linspace(0, np.pi, n)
    return phases[np.argmin([np.ptp((z * np.exp(1j * p)).imag) for p in phases])]


def _axis_error_deg(phase, axis):
    d = (phase + axis) % np.pi  # the multiplier phase is -axis modulo pi
    return np.degrees(min(d, np.pi - d))


@pytest.mark.parametrize("axis_deg", [0.0, 37.0, 90.0, 151.0, 200.0, 271.0, 330.0])
def test_noiseless_decay_is_put_in_i_with_the_excited_end_up(axis_deg):
    axis = np.deg2rad(axis_deg)
    i, q = _trace(axis)
    p = decay_axis_phase(i, q)
    assert 0.0 <= p < 2 * np.pi
    # exact: the first point lies on +I relative to the mean, all of the decay in I
    assert np.angle(np.exp(1j * (p + axis))) == pytest.approx(0.0, abs=1e-9)
    rot = (i + 1j * q) * np.exp(1j * p)
    assert np.ptp(rot.imag) == pytest.approx(0.0, abs=1e-9)
    assert rot.real[0] > rot.real.mean()


def test_constant_or_empty_trace_gives_zero():
    assert decay_axis_phase(np.full(10, 0.3), np.full(10, -0.2)) == 0.0
    assert decay_axis_phase(np.array([]), np.array([])) == 0.0


def test_old_name_is_an_alias():
    i, q = _trace(1.1, noise=0.05, seed=4)
    assert min_q_range_phase(i, q, 200) == decay_axis_phase(i, q)
    assert min_q_range_phase(i, q, 500) == decay_axis_phase(i, q)


def test_same_axis_as_the_rabi_rotation():
    """Rabi multiplies by exp(-1j*a), the decay by exp(+1j*p): the axes agree, p = -a mod pi."""
    for seed in range(20):
        axis = np.random.default_rng(100 + seed).uniform(0, 2 * np.pi)
        i, q = _trace(axis, noise=0.1, seed=seed)
        p = decay_axis_phase(i, q)
        a = iq_rotation_angle(i + 1j * q)
        d = (p + a) % np.pi
        assert min(d, np.pi - d) < 1e-12


@pytest.mark.parametrize("noise", [0.05, 0.10])
def test_more_accurate_than_the_min_q_range_grid(noise):
    rng = np.random.default_rng(7)
    old, new, signs = [], [], 0
    for seed in range(200):
        axis = rng.uniform(0, 2 * np.pi)
        i, q = _trace(axis, noise=noise, seed=seed)
        p = decay_axis_phase(i, q)
        old.append(_axis_error_deg(_legacy_min_q_range(i, q), axis))
        new.append(_axis_error_deg(p, axis))
        signs += abs(np.angle(np.exp(1j * (p + axis)))) < np.pi / 2
    assert np.median(new) < 0.5 * np.median(old)
    assert np.percentile(new, 95) < 0.5 * np.percentile(old, 95)
    assert signs == 200  # the first point is the most excited one on every trace


# ---------------------------------------------------------------- displays


def _run(tmp_path, cls, cfg, min_max=None, axis=np.deg2rad(140.0)):
    i, q = _trace(axis, noise=0.01, seed=1, contrast=1.0)
    data = {
        "data": {
            "x_pts": X,
            "avgi": i[None, None, :],
            "avgq": q[None, None, :],
            "qfreq": 4000.0,
        }
    }
    if min_max is not None:
        data["min_max"] = min_max
    inst = cls(path=cls.__name__, outerFolder=str(tmp_path) + os.sep, cfg=dict(cfg))
    assert finish(cls, inst, data, plotDisp=False) is None
    with h5py.File(inst.fname, "r") as f:
        saved = {k: f[k][()] for k in f}
    return inst, saved, axis


CASES = {
    "T1FF": (T1FF, "t1", {"Qubit_number": 1}),
    "T2EMUX": (T2EMUX, "t2e", {"num_pi_pulses": 1, "rotation_angle": None}),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_display_saves_the_automatic_rotation(tmp_path, name):
    cls, prefix, cfg = CASES[name]
    inst, saved, axis = _run(tmp_path, cls, cfg)
    p = saved[f"{prefix}_fit_rotation_rad"]
    assert abs(np.angle(np.exp(1j * (p + axis)))) < np.deg2rad(1.0)
    assert inst.fit["ok"] and inst.fit["a"] == pytest.approx(1.0, rel=0.05)  # all contrast in I


@pytest.mark.parametrize("name", sorted(CASES))
def test_min_max_without_a_fixed_rotation_stays_in_au(tmp_path, name):
    cls, prefix, cfg = CASES[name]
    # levels that would scale the amplitude by 1 / 0.1 = 10 if they were applied
    inst, saved, _ = _run(tmp_path, cls, cfg, min_max=[0.0, 0.1])
    assert inst.fit["a"] == pytest.approx(1.0, rel=0.05)


@pytest.mark.parametrize("name", sorted(CASES))
def test_min_max_with_a_fixed_rotation_normalises(tmp_path, name):
    cls, prefix, cfg = CASES[name]
    axis = np.deg2rad(140.0)
    fixed = dict(cfg, rotation_angle=float(-axis % (2 * np.pi)))
    inst, saved, _ = _run(tmp_path, cls, fixed, min_max=[0.0, 0.1], axis=axis)
    assert saved[f"{prefix}_fit_rotation_rad"] == pytest.approx(fixed["rotation_angle"])
    assert inst.fit["a"] == pytest.approx(10.0, rel=0.05)
