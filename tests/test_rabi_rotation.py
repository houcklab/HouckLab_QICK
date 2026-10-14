"""Hardware-free tests for the amplitude-Rabi IQ rotation (docs/experiments/amplitude_rabi.md,
docs/concepts/iq_conventions.md section 3): the principal axis is estimated from the analysed read
(ADC 0) only, its sign puts I increasing toward the pi pulse, and the eigenvalue ratio is saved as
a contrast diagnostic.

    python -m pytest tests/test_rabi_rotation.py
"""

import os
import warnings

import matplotlib

matplotlib.use("Agg")

import numpy as np
import pytest

import qicklab.experiments.rabi as rabi
from qicklab.experiments.rabi import (
    AmplitudeRabiFF,
    AmplitudeRabiFF_N,
    iq_axis_contrast_ratio,
    iq_rotation_angle,
)

X = np.arange(101) * 99.0  # run_amplitude_rabi's default grid
PI_GAIN = 4000.0
AXIS = np.deg2rad(120.0)  # direction of the g -> e excursion in IQ


def _pe(x=X, pi_gain=PI_GAIN):
    return (1 - np.cos(np.pi * x / pi_gain)) / 2


def _two_adc(seed=0, noise=0.02):
    """ADC 0: background 30+40j plus a 5 a.u. g->e excursion along 120 deg; ADC 1: idle noise
    around 0 (the readout ADC that sees no qubit). Shape (2, 1, N) like RAveragerProgram.acquire."""
    rng = np.random.default_rng(seed)
    n = X.size
    adc0 = 30 + 40j + 5 * _pe() * np.exp(1j * AXIS)
    adc0 = adc0 + noise * (rng.normal(size=n) + 1j * rng.normal(size=n))
    adc1 = noise * (rng.normal(size=n) + 1j * rng.normal(size=n))
    sig = np.stack([adc0, adc1])[:, None, :]
    return sig.real, sig.imag


def _ang_err_deg(a, b):
    return abs(np.rad2deg(np.angle(np.exp(1j * (a - b)))))


def _acquire(monkeypatch, tmp_path, avgi, avgq):
    class FakeProg:
        def __init__(self, soccfg, cfg):
            pass

        def acquire(self, soc, **kwargs):
            return X.copy(), avgi, avgq

    monkeypatch.setattr(rabi, "AmplitudeRabiFFProg", FakeProg)
    cfg = {"cavity_winding_freq": 0.0, "pulse_freq": 6000.0, "cavity_winding_offset": 0.0}
    inst = AmplitudeRabiFF(path="AmplitudeRabi", outerFolder=str(tmp_path) + os.sep, cfg=cfg)
    return inst.acquire()


def test_acquire_rotation_puts_adc0_contrast_in_i(monkeypatch, tmp_path):
    # Before the fix the axis came from np.ravel over both ADCs: the 50 a.u. ADC0-ADC1 background
    # offset set the axis (55.4 deg here), leaving ~2.2 of the 5 a.u. contrast in I.
    avgi, avgq = _two_adc()
    both = np.ravel(avgi + 1j * avgq)
    i, q = both.real - both.real.mean(), both.imag - both.imag.mean()
    old_angle = 0.5 * np.arctan2(2 * np.mean(i * q), np.mean(i * i) - np.mean(q * q))
    assert _ang_err_deg(old_angle, AXIS) > 30

    d = _acquire(monkeypatch, tmp_path, avgi, avgq)["data"]
    assert np.shape(d["avgi"]) == (2, 1, X.size)
    assert _ang_err_deg(d["iq_rotation_rad"], AXIS) < 1.0
    i0, q0 = d["avgi"][0][0], d["avgq"][0][0]
    assert np.ptp(i0) == pytest.approx(5.0, abs=0.15)
    assert np.ptp(q0) < 0.2
    # Sign: I increases from gain 0 (|g>) to the pi pulse.
    k = np.argmin(np.abs(X - PI_GAIN))
    assert i0[k] - i0[0] == pytest.approx(5.0, abs=0.15)
    assert d["iq_axis_contrast_ratio"] > 1000
    # The same rotation is applied to ADC 1 (shape and data path unchanged).
    raw1 = avgi[1][0] + 1j * avgq[1][0]
    rot1 = d["avgi"][1][0] + 1j * d["avgq"][1][0]
    assert np.allclose(rot1, raw1 * np.exp(-1j * d["iq_rotation_rad"]))


@pytest.mark.parametrize("axis_deg", [-170.0, -60.0, 0.0, 45.0, 120.0, 179.0])
@pytest.mark.parametrize("pi_gain", [3000.0, PI_GAIN, 4950.0, 7425.0])
def test_sign_convention_i_increases_toward_pi(axis_deg, pi_gain):
    # 0.67 to 1.65 periods in the sweep, including exactly 1 period (pi gain 4950), where the end
    # of the sweep is back at |g>: the sign is referenced to the start of the sweep, not its end.
    axis = np.deg2rad(axis_deg)
    rng = np.random.default_rng(1)
    trace = 1 - 2j + 3 * _pe(pi_gain=pi_gain) * np.exp(1j * axis)
    trace = trace + 0.03 * (rng.normal(size=X.size) + 1j * rng.normal(size=X.size))
    ang = iq_rotation_angle(trace)
    assert -np.pi < ang <= np.pi
    assert _ang_err_deg(ang, axis) < 1.0
    i = (trace * np.exp(-1j * ang)).real
    k = np.argmin(np.abs(X - min(pi_gain, X[-1])))
    assert i[k] > i[0]


@pytest.mark.parametrize("periods", [3.0, 5.0, 6.0, 8.0, 10.0, 15.0, 20.0])
def test_sign_convention_holds_for_many_periods(periods):
    # The sign reference is a fixed few points at the start of the sweep (gain ~ 0, |g>). A window
    # of 10% of the sweep (the first version) spans 0.6 period at 6 periods and its mean then lies
    # above the trace mean: I came out decreasing toward the pi pulse in every seed at 6 and 8
    # periods. The fixed 3-point window holds up to about (N - 1) / 4 = 25 periods here.
    axis = 0.7
    pi_gain = X[-1] / (2 * periods)
    k_pi = np.argmin(np.abs(X - pi_gain))
    rng = np.random.default_rng(int(periods * 10))
    n_bad = n_bad_old = 0
    for _ in range(50):
        trace = 3 * _pe(pi_gain=pi_gain) * np.exp(1j * axis)
        trace = trace + 0.1 * (rng.normal(size=X.size) + 1j * rng.normal(size=X.size))
        ang = iq_rotation_angle(trace)
        assert _ang_err_deg(ang, axis) < 3.0
        i = (trace * np.exp(-1j * ang)).real
        n_bad += not i[k_pi] > i[0]
        # the 10%-window rule, for contrast
        dev = trace - trace.mean()
        a0 = 0.5 * np.angle(np.sum(dev**2))
        proj = (dev * np.exp(-1j * a0)).real
        if np.mean(proj[:10]) > 0:
            a0 += np.pi
        i_old = (trace * np.exp(-1j * a0)).real
        n_bad_old += not i_old[k_pi] > i_old[0]
    assert n_bad == 0
    if periods in (6.0, 8.0):
        assert n_bad_old == 50  # the failure the fixed window removes


def test_contrast_ratio_diagnostic():
    rng = np.random.default_rng(2)
    noise = rng.normal(size=X.size) + 1j * rng.normal(size=X.size)
    assert 1.0 <= iq_axis_contrast_ratio(noise) < 3.0  # no preferred axis
    line = 2 + 1j + _pe() * np.exp(1j * AXIS)
    assert iq_axis_contrast_ratio(line) == np.inf
    assert np.isnan(iq_axis_contrast_ratio(np.full(X.size, 1 + 1j)))
    # Equals the eigenvalue ratio of the 2x2 IQ covariance.
    trace = line + 0.05 * noise
    w = np.linalg.eigvalsh(np.cov(np.vstack([trace.real, trace.imag])))
    assert iq_axis_contrast_ratio(trace) == pytest.approx(w[1] / w[0], rel=1e-9)


def test_ff_n_display_uses_the_same_signed_principal_axis(tmp_path):
    rng = np.random.default_rng(3)
    trace = 30 + 40j + 5 * _pe() * np.exp(1j * AXIS)
    trace = trace + 0.02 * (rng.normal(size=X.size) + 1j * rng.normal(size=X.size))
    data = {"data": {"x_pts": X, "avgi": [[trace.real]], "avgq": [[trace.imag]]}}
    inst = AmplitudeRabiFF_N(path="AmplitudeRabi", outerFolder=str(tmp_path) + os.sep, cfg={})
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        inst.display(data=data, fit=True, rotate=True)
    # rotation_phase is the multiplier phase: rotated = raw * exp(1j * rotation_phase)
    assert _ang_err_deg(-inst.rotation_phase, AXIS) < 1.0
    assert inst.iq_axis_contrast_ratio > 1000
    assert inst.fit_i["pi_gain"] == pytest.approx(PI_GAIN, rel=0.03)
    assert abs(inst.fit_i["popt"][1]) == pytest.approx(2.5, rel=0.05)


def test_identical_adcs_give_the_old_axis_modulo_pi(monkeypatch, tmp_path):
    # With ADC 1 an exact copy of ADC 0 the concatenated estimate was already right: the axis is
    # unchanged, only its sign is now fixed.
    avgi, avgq = _two_adc()
    avgi, avgq = np.stack([avgi[0], avgi[0]]), np.stack([avgq[0], avgq[0]])
    both = np.ravel(avgi + 1j * avgq)
    i, q = both.real - both.real.mean(), both.imag - both.imag.mean()
    old_angle = 0.5 * np.arctan2(2 * np.mean(i * q), np.mean(i * i) - np.mean(q * q))
    d = _acquire(monkeypatch, tmp_path, avgi, avgq)["data"]
    diff = np.rad2deg(d["iq_rotation_rad"] - old_angle) % 180.0
    assert min(diff, 180.0 - diff) < 1e-6
