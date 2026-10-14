"""Hardware-free tests for the Ramsey (T2R) analysis: principal-axis projection, sampling-derived
fit bounds, and a display that never raises on a failed fit (docs/experiments/t2_ramsey.md).

    python -m pytest tests/test_ramsey_fit.py
"""

import os

import matplotlib

matplotlib.use("Agg")

import numpy as np
import pytest

from qicklab.analysis.iq import principal_axis_angle
from qicklab.analysis.ramsey import fit_ramsey_auto, project_ramsey_iq, ramsey_fit_limits
from qicklab.experiments.t2_ramsey import T2R

T = np.arange(201) * 0.1  # 201 x 0.1 us, Nyquist 5 MHz


def _ramsey_iq(g, e, f=0.4, T2=8.0, noise=0.01, seed=0, t=T):
    """IQ trace moving between the |g> and |e> points with P_e = 1/2 (1 + exp(-t/T2) cos 2 pi f t)."""
    rng = np.random.default_rng(seed)
    pe = 0.5 + 0.5 * np.exp(-t / T2) * np.cos(2 * np.pi * f * t)
    sig = g + (e - g) * pe + noise * (rng.normal(size=t.size) + 1j * rng.normal(size=t.size))
    return sig.real, sig.imag


GEOMETRIES = {
    "g_e_on_one_ray": (0.2 + 0.1j, 1.0 + 0.5j),
    "equal_magnitude_different_phase": (np.exp(-1j * np.pi / 6), np.exp(1j * np.pi / 6)),
    "small_contrast_offset": (0.3 + 1.0j, 0.8 + 1.1j),
    # e - g has a negative real part: the principal-axis angle (in (-pi/2, pi/2]) points from e
    # to g, so project_ramsey_iq has to flip the sign to put t = 0 (about |e>) positive
    "small_contrast_offset_swapped": (0.8 + 1.1j, 0.3 + 1.0j),
}


@pytest.mark.parametrize("geometry", sorted(GEOMETRIES))
def test_t2star_recovered_for_every_readout_geometry(geometry):
    # The old centroid-onto-+I rotation put the fringe into Q for the |g| ~ |e| geometry and
    # returned T2* = 1e5 us (the bound). For small_contrast_offset the old T2* (8.13 us) is still
    # within 5%, but only ~63% of the contrast reached I (old A = 0.161 vs |e - g| / 2 = 0.255):
    # the amplitude and peak-to-peak checks below are what catch it there. g_e_on_one_ray is the
    # control case on which the old rotation was already correct.
    g, e = GEOMETRIES[geometry]
    res = fit_ramsey_auto(T, *_ramsey_iq(g, e))
    assert res["mode"] == "1f"
    A, T2, f, _, _ = res["popt"]
    assert T2 == pytest.approx(8.0, rel=0.05)
    assert f == pytest.approx(0.4, abs=0.005)
    assert abs(A) == pytest.approx(abs(e - g) / 2, rel=0.05)
    # the projection carries all of the g-e contrast (P_e swing 1 at t=0 -> |e - g| peak to peak)
    y = np.real(res["sig_rot"])
    assert np.ptp(y) > 0.9 * abs(e - g)
    assert y[0] > 0  # t = 0 (about |e>) is positive
    # iq_axis_rad is the g-e direction (mod pi)
    d = np.angle((e - g) * np.exp(-1j * res["iq_axis_rad"]))
    assert min(abs(d), abs(abs(d) - np.pi)) < 0.05


def test_projection_helper_matches_principal_axis():
    dev = (np.linspace(-1, 1, 50) + 0.01j) * np.exp(1j * 0.7)
    assert principal_axis_angle(dev) == pytest.approx(0.7)
    sig_rot, ang = project_ramsey_iq(dev.real + 3.0, dev.imag - 2.0)
    assert np.allclose(np.mean(sig_rot), 0)
    assert np.max(np.abs(sig_rot.imag)) < 0.02
    assert sig_rot.real[0] > 0 and -np.pi < ang <= np.pi


def test_bounds_follow_the_sampling():
    assert ramsey_fit_limits(T) == pytest.approx((5.0, 0.05))
    assert ramsey_fit_limits(np.arange(100) * 0.02) == pytest.approx((25.0, 0.01))
    assert ramsey_fit_limits([0.0]) == (2.0, 1.0)


@pytest.mark.parametrize("swapped", [False, True], ids=["no_flip", "flip"])
@pytest.mark.parametrize("n_pts", [100, 201])  # 100 = the session default T2_expts
@pytest.mark.parametrize("f_true", [2.5, 2.6, 2.8, 3.0, 3.2, 4.5])
def test_fringe_above_old_2mhz_cap_fits(f_true, n_pts, swapped):
    # Previously: FFT seed > 2 MHz -> ValueError 'Initial guess is outside of provided bounds'.
    # 2.5-3.3 MHz at dt = 0.1 us is where a sign rule on the mean of the first 3 points picks the
    # wrong sign (mean ~ cos x (2 cos x + 1), x = 2 pi f dt); with phi seeded at 0 and A >= 0 the
    # 100-point fit then collapsed (A -> 0, wrong f) on 7-40% of noise seeds. Several seeds each.
    # With the old rule the f / T2* checks fail at 100 points for 2.6-3.2 MHz (seeds 1-3, 6, 7);
    # at 201 points trf recovers, and only the sign check catches it.
    # swapped: g and e exchanged, so the raw principal axis gives y[0] < 0 and the sign flip in
    # project_ramsey_iq runs end to end. Without the flip the 100-point f / T2* checks fail on
    # 1-4 of the 8 seeds for 2.5-3.2 MHz; at 201 points only the sign check catches it.
    g, e = (0.8 + 1.1j, 0.3 + 1.0j) if swapped else (0.3 + 1.0j, 0.8 + 1.1j)
    t = np.arange(n_pts) * 0.1
    for seed in range(8):
        i, q = _ramsey_iq(g, e, f=f_true, seed=seed, t=t)
        sig = i + 1j * q
        raw = (sig - sig.mean()) * np.exp(-1j * principal_axis_angle(sig - sig.mean()))
        assert (np.real(raw[0]) < 0) == swapped, seed  # the flip branch runs iff swapped
        res = fit_ramsey_auto(t, i, q)
        assert np.real(res["sig_rot"][0]) > 0, seed
        assert res["mode"] == "1f", seed
        assert res["popt"][2] == pytest.approx(f_true, abs=0.005), seed
        assert res["popt"][1] == pytest.approx(8.0, rel=0.25), seed


def test_t2star_below_1us_is_not_pinned():
    t = np.arange(101) * 0.02
    res = fit_ramsey_auto(t, *_ramsey_iq(0.2 + 0.1j, 1.0 + 0.5j, f=1.0, T2=0.4, t=t))
    T2 = res["popt"][1] if res["mode"] == "1f" else res["popt"][2]
    assert T2 == pytest.approx(0.4, rel=0.1)


def _t2r(tmp_path):
    return T2R(path="T2R", outerFolder=str(tmp_path) + os.sep, cfg={"reps": 1})


def _data(i, q, t=T):
    return {"data": {"x_pts": t, "avgi": [[i]], "avgq": [[q]]}}


def test_display_reports_the_fitted_frequency(tmp_path):
    inst = _t2r(tmp_path)
    inst.display(data=_data(*_ramsey_iq(0.3 + 1.0j, 0.8 + 1.1j, f=0.437)))
    fit = inst.osc_fit
    assert fit["ok"] and inst.env_fit["ok"]
    # the FFT bin (0.0498 MHz wide) is ~11 kHz off; the fit is not
    assert fit["f_report"] == fit["popt"][2]
    assert fit["f_report"] == pytest.approx(0.437, abs=0.002)
    assert abs(fit["dominant_fft_freq"] - 0.437) > 0.005
    assert fit["fft_fit_mismatch"] is False
    assert os.path.exists(inst.iname[:-4] + "RotatedI_Fit.png")


def test_display_handles_fringe_above_2mhz(tmp_path):
    inst = _t2r(tmp_path)
    inst.display(data=_data(*_ramsey_iq(np.exp(-1j * np.pi / 6), np.exp(1j * np.pi / 6), f=3.0)))
    assert inst.osc_fit["ok"]
    assert inst.osc_fit["f_report"] == pytest.approx(3.0, abs=0.005)


@pytest.mark.parametrize("seed", [0, 1, 2, 4])
def test_display_on_noise_returns(tmp_path, seed):
    # On these noise traces the old code raised 'Initial guess is outside of provided bounds'
    # (FFT seed above the 2 MHz cap) out of T2R.display, as in the golden's 5 raised entries.
    rng = np.random.default_rng(seed)
    inst = _t2r(tmp_path)
    inst.display(data=_data(rng.normal(size=T.size), rng.normal(size=T.size)))
    fit = inst.osc_fit
    assert np.isfinite(fit["iq_axis_rad"]) and len(fit["sig_rot"]) == T.size
    assert isinstance(fit["ok"], bool) and isinstance(inst.env_fit["ok"], bool)
    if fit["ok"]:
        # the fit stays inside the sampling-derived bounds (fft_fit_mismatch is not asserted: it
        # is not a noise detector, False on about half of noise traces)
        assert 0.0 <= fit["f_report"] <= 5.0
        assert 0.05 <= fit["popt"][1] <= 1e5
        assert isinstance(fit["fft_fit_mismatch"], bool)
    else:
        assert fit["f_report"] is None
    assert os.path.exists(inst.iname[:-4] + "RotatedI_Fit.png")
    assert os.path.exists(inst.iname[:-4] + "FFT.png")


def test_display_failed_fit_does_not_raise(tmp_path):
    # A flat trace has zero contrast: curve_fit refuses the degenerate bounds and raises.
    inst = _t2r(tmp_path)
    flat = np.full(T.size, 0.5)
    inst.display(data=_data(flat, flat))
    assert inst.osc_fit["ok"] is False and "Error" in inst.osc_fit["error"]
    assert inst.osc_fit["f_report"] is None
    # the projected data and the FFT are still plotted
    assert os.path.exists(inst.iname[:-4] + "RotatedI_Fit.png")
    assert os.path.exists(inst.iname[:-4] + "FFT.png")


def test_display_survives_any_fit_exception(tmp_path, monkeypatch):
    import qicklab.experiments.t2_ramsey as mod

    def boom(*args, **kwargs):
        raise RuntimeError("Optimal parameters not found")

    monkeypatch.setattr(mod, "fit_ramsey_auto", boom)
    monkeypatch.setattr(mod, "fit_magnitude_envelope", boom)
    inst = _t2r(tmp_path)
    inst.display(data=_data(*_ramsey_iq(0.2 + 0.1j, 1.0 + 0.5j)))
    assert inst.osc_fit["ok"] is False and "RuntimeError" in inst.osc_fit["error"]
    assert inst.env_fit == {"ok": False, "error": "RuntimeError('Optimal parameters not found')"}
    assert np.ptp(np.real(inst.osc_fit["sig_rot"])) > 0.5
