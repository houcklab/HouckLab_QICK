"""Gain x length spectroscopy summary (F71): run_spec_gain_length_sweep's saturation fit.

Synthetic two-tone traces on the Run2ToneSpec grid (3000 +- 10 MHz, 201 points, step
0.0995 MHz) with a power-broadened Lorentzian, FWHM^2 = FWHM_0^2 + c gain^2 (FWHM_0 =
0.4 MHz, c = 6e-7 MHz^2 / DAC^2) and a saturating height, plus Gaussian noise, run through
the real QubitSpecSliceFF.display (min_sep 0.2, fit_window 0.5, prominent_ratio 0.1) and
gain_sweep_point. The summary must recover FWHM_0 (and the T2* bound 1/(pi FWHM_0)) and the
recommended gain (smallest gain with SNR >= 5 and FWHM <= 1.2 FWHM_0), also where display's
0.5 MHz window cannot fit the broad high-gain lines. Fewer than 3 usable lines give
"insufficient"; empty or missing fits give NaN rows; a FWHM_0 under 3 grid steps is
"resolution-limited"; Gauss=True pools the lengths; a resolved doublet reports its
splitting, and its merged high-gain blends stay out of the fit; the run writes
GainLengthSweep_summary_<timestamp>.npz into the QubitSpecFF folder.
"""

import os

os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

import qicklab.runs.spectroscopy as spec_runs  # noqa: E402
from qicklab.analysis.spectroscopy import (  # noqa: E402
    fit_power_broadening,
    gain_sweep_point,
    summarize_gain_length_sweep,
)
from qicklab.experiments.qubit_spec import QubitSpecSliceFF  # noqa: E402

F0 = 3000.0
SPAN = 10.0
FWHM0 = 0.4
C = 6e-7
NOISE = 0.02
GAINS = list(range(100, 2001, 100))
KW = dict(fit_window_mhz=0.5, span_mhz=SPAN, min_sep_mhz=0.2)


def _grid(span=SPAN, n=201):
    step = 2 * span / n
    return F0 - span + step * np.arange(n)


def _fwhm(g):
    return np.sqrt(FWHM0**2 + C * g**2)


def _height(g):
    return min(1.0, (g / 400.0) ** 2)


def _spec(lines, seed, x=None):
    """lines: [(centre, fwhm, height)]; the data dict of QubitSpecSliceFF.acquire."""
    x = _grid() if x is None else x
    y = np.zeros_like(x)
    for f, w, h in lines:
        hw = 0.5 * w
        y += h * hw**2 / ((x - f) ** 2 + hw**2)
    rng = np.random.default_rng(seed)
    avgi = 0.3 + y + rng.normal(0, NOISE, x.size)
    avgq = -0.2 + rng.normal(0, NOISE, x.size)
    stack = lambda a: np.stack([a, a])[:, None, :]  # (ADC, read, freq)  # noqa: E731
    return {"config": {}, "data": {"x_pts": x, "avgi": stack(avgi), "avgq": stack(avgq)}}


def _display(data, tmp_path):
    exp = object.__new__(QubitSpecSliceFF)
    exp.cfg = {"qubit_gain": 500, "Gauss": False, "qubit_length": 10}
    exp.titlename = "Qubit Spec"
    exp.iname = str(tmp_path / "spec.png")
    exp.display(
        data, plotDisp=False, figNum=2, min_sep=0.2, fit_window_mhz=0.5, prominent_ratio=0.1
    )
    return data


def _row(lines, gain, seed, tmp_path, length=10.0):
    data = _display(_spec(lines, seed), tmp_path)
    return gain_sweep_point(data, length, gain, **KW)


def test_synthetic_grid_recovers_fwhm0_t2star_and_recommended_gain(tmp_path):
    rows = [_row([(F0 + 0.03, _fwhm(g), _height(g))], g, k, tmp_path) for k, g in enumerate(GAINS)]
    s = summarize_gain_length_sweep(rows)
    g = s["groups"]
    assert list(g["length"]) == [10.0]
    assert g["status"][0] == "ok"
    assert g["fwhm0"][0] == pytest.approx(FWHM0, rel=0.1)
    assert np.isfinite(g["fwhm0_err"][0]) and g["fwhm0_err"][0] < 0.05
    assert g["c"][0] == pytest.approx(C, rel=0.2)
    assert g["t2star_lower_us"][0] == pytest.approx(1 / (np.pi * g["fwhm0"][0]))
    # gain 100: SNR ~3 (not used); gain 200: SNR ~12 and FWHM 0.43 <= 1.2 FWHM_0
    assert s["points"]["snr_line"][0] != s["points"]["snr_line"][0]  # NaN at gain 100
    assert g["recommended_gain"][0] == 200
    assert g["highest_unbroadened_gain"][0] in (300, 400)
    assert g["n_points"][0] == len(GAINS) - 1


def test_broad_lines_use_the_adaptive_refit_not_display_window(tmp_path):
    gain = 2000  # FWHM 1.6 MHz: display's +-0.5 MHz window clips or rejects it
    row = _row([(F0, _fwhm(gain), 1.0)], gain, 3, tmp_path)
    assert row["fwhm_line"] == pytest.approx(_fwhm(gain), rel=0.1)
    k = int(np.nanargmax(row["peak_amps"]))  # the line (display may add a flank maximum)
    assert row["refit_censored"][k] == 0.0
    assert row["refit_window_mhz"][k] >= 3 * row["fwhm_line"] * 0.99
    disp = row["lorentz_fwhm"][0]
    assert not np.isfinite(disp) or abs(disp - _fwhm(gain)) > 0.1 * _fwhm(gain)


def test_fewer_than_three_lines_is_insufficient():
    assert fit_power_broadening([200, 400], [0.4, 0.5])["status"] == "insufficient"
    assert fit_power_broadening([200, 400, 600], [0.4, np.nan, 0.5])["status"] == "insufficient"
    fit = fit_power_broadening([200, 400, 600], [0.4, 0.45, 0.55])
    assert fit["status"] == "fit" and fit["n_points"] == 3


def test_empty_fits_give_nan_rows_and_an_insufficient_group(tmp_path):
    noise_only = _row([], 500, 7, tmp_path)
    empty = {"data": {"x_pts": _grid(), "avgi": [[np.zeros(201)]], "avgq": [[np.zeros(201)]]}}
    empty["data"].update(two_tone_peak_freqs=np.array([]), two_tone_peak_amps=np.array([]))
    rows = [
        noise_only,
        gain_sweep_point(empty, 10, 600, **KW),
        gain_sweep_point(None, 10, 700, **KW),
    ]
    for r in rows:
        assert np.isnan(r["fwhm_line"]) and np.isnan(r["snr_line"])
        assert r["refit_fwhm"].shape == (2,) and np.all(np.isnan(r["refit_fwhm"]))
    assert rows[2]["q_gain"] == 700 and np.all(np.isnan(rows[2]["peak_freqs"]))
    s = summarize_gain_length_sweep(rows)
    assert s["points"]["peak_freqs"].shape == (3, 2)
    assert s["groups"]["status"][0] == "insufficient"
    assert np.isnan(s["groups"]["recommended_gain"][0])


def _fake_row(length, gain, fwhm, snr=20.0, step=0.0995, split=np.nan):
    r = gain_sweep_point(None, length, gain, **KW)
    r.update(fwhm_line=fwhm, fwhm_line_err=0.01, snr_line=snr, step_mhz=step, splitting_mhz=split)
    return r


def test_fwhm0_below_three_steps_is_resolution_limited():
    rows = [_fake_row(10, g, np.sqrt(0.2**2 + C * g**2)) for g in (200, 600, 1000, 1400)]
    g = summarize_gain_length_sweep(rows)["groups"]
    assert g["status"][0] == "resolution-limited"  # 0.2 MHz < 3 x 0.0995 MHz
    assert np.isnan(g["t2star_lower_us"][0])
    assert g["recommended_gain"][0] == 200


def test_gauss_pools_lengths_and_uses_the_envelope_fourier_width():
    rows = [_fake_row(L, g, _fwhm(g)) for L in (10, 20) for g in (200, 600, 1000)]
    g = summarize_gain_length_sweep(rows, gauss=True, sigma_us=0.5)["groups"]
    assert g["status"].shape == (1,) and np.isnan(g["length"][0])
    assert g["n_points"][0] == 6
    assert g["fourier_fwhm_mhz"][0] == pytest.approx(0.5)  # 1 / (4 sigma)
    assert g["status"][0] == "resolution-limited"  # FWHM_0 0.4 < 0.5 MHz Fourier width
    per_length = summarize_gain_length_sweep(rows)["groups"]
    assert list(per_length["length"]) == [10.0, 20.0]


def test_resolved_doublet_reports_splitting_and_uses_the_narrower_branch(tmp_path):
    lines = [(F0 - 0.6, 0.3, 1.0), (F0 + 0.6, 0.5, 0.8)]
    row = _row(lines, 800, 11, tmp_path)
    assert row["splitting_mhz"] == pytest.approx(1.2, abs=0.05)
    assert row["fwhm_line"] == pytest.approx(0.3, rel=0.15)
    assert np.all(row["refit_censored"] == 0.0)


def test_doublet_merging_at_high_gain_is_left_out_of_the_saturation_fit(tmp_path):
    # Branches at F0 -+ 0.6 MHz, each power-broadened (FWHM^2 = 0.4^2 + c g^2), heights
    # 1 : 0.8. Up to about 1400 the valley test resolves them; above it one Lorentzian over
    # the merged pair is ~2.4 MHz wide (splitting + branch FWHM). Those rows must be marked
    # as blends and kept out of the fit, or FWHM_0 drops and the group turns
    # resolution-limited.
    gains = list(range(200, 2001, 200))
    rows = [
        _row(
            [(F0 - 0.6, _fwhm(g), _height(g)), (F0 + 0.6, _fwhm(g), 0.8 * _height(g))],
            g,
            100 + k,
            tmp_path,
        )
        for k, g in enumerate(gains)
    ]
    s = summarize_gain_length_sweep(rows)
    p, g = s["points"], s["groups"]
    merged = np.isfinite(p["fwhm_line"]) & np.isnan(p["splitting_mhz"])
    assert list(p["q_gain"][merged]) == [1600, 1800, 2000]
    assert np.all(p["fwhm_line"][merged] > 2.0)  # the blend, not a 1.3-1.6 MHz branch
    assert np.all(p["blended"][merged] == 1.0)
    assert np.all(p["blended"][~merged] == 0.0)
    assert g["n_blended"][0] == 3 and g["n_points"][0] == 7
    assert g["status"][0] == "ok"
    assert g["fwhm0"][0] == pytest.approx(FWHM0, rel=0.1)
    assert g["c"][0] == pytest.approx(C, rel=0.2)
    assert g["splitting_min_mhz"][0] == pytest.approx(1.2, abs=0.05)
    assert g["recommended_gain"][0] == 200


def test_blend_censoring_needs_a_resolved_doublet_in_the_group():
    # Same wide single lines with no doublet anywhere in the group: kept (a broad line is
    # just a broad line); with a 1.2 MHz doublet at another gain they are blends.
    wide = [_fake_row(10, g, _fwhm(g)) for g in (200, 1000, 1600, 2000)]
    s = summarize_gain_length_sweep(wide)
    assert np.all(s["points"]["blended"] == 0.0) and s["groups"]["n_points"][0] == 4
    rows = wide + [_fake_row(10, 400, 0.5, split=1.2)]
    s = summarize_gain_length_sweep(rows)
    assert list(s["points"]["blended"]) == [0.0, 0.0, 1.0, 1.0, 0.0]  # 1.30, 1.60 MHz >= 1.2
    assert s["groups"]["n_blended"][0] == 2 and s["groups"]["n_points"][0] == 3


def test_flank_noise_maximum_is_not_a_doublet(tmp_path):
    # a broad line: display's second peak (prominent_ratio 0.1) is a noise maximum on its flank
    for seed in range(4):
        row = _row([(F0, 1.6, 1.0)], 2000, 20 + seed, tmp_path)
        assert np.isnan(row["splitting_mhz"])
        assert row["fwhm_line"] == pytest.approx(1.6, rel=0.1)


def test_run_saves_the_summary_in_the_qubitspec_folder(tmp_path, monkeypatch):
    calls = []

    class _Fake(QubitSpecSliceFF):
        def __init__(self, path="", cfg=None, outerFolder="", **kw):
            self.cfg = dict(cfg)
            folder = os.path.join(outerFolder + path, path + "_today")
            os.makedirs(folder, exist_ok=True)
            self.fname = os.path.join(folder, f"pt{len(calls)}_data.h5")
            self.iname = self.fname[:-3] + ".png"
            self.titlename = path

        def acquire(self):
            g = self.cfg["qubit_gain"]
            calls.append(g)
            return _spec([(F0, _fwhm(g), _height(g))], len(calls))

        def save_data(self, data=None):
            pass

        def save_config(self):
            pass

    class _Ctx:
        soc = soccfg = None
        outerFolder = str(tmp_path) + os.sep
        qubit_frequency_center = F0

        def working_config(self):
            return {}

    monkeypatch.setattr(spec_runs, "QubitSpecSliceFF", _Fake)
    params = dict(sweep_lengths=[10], sweep_gains=[200, 400, 600, 800], display=False)
    params.update(min_sep_MHz=0.2, fit_window_mhz=0.5, prominent_ratio=0.1, reps=1, rounds=1)
    params.update(Gauss=False, SpecSpan=SPAN, SpecNumPoints=201, relax_delay=10)
    spec_runs.run_spec_gain_length_sweep(_Ctx(), params)
    assert calls == [200, 400, 600, 800]
    folder = tmp_path / "QubitSpecFF" / "QubitSpecFF_today"
    npz = list(folder.glob("GainLengthSweep_summary_*.npz"))
    assert len(npz) == 1 and len(list(folder.glob("GainLengthSweep_summary_*.png"))) == 1
    with np.load(npz[0], allow_pickle=False) as z:
        assert z["point_q_gain"].tolist() == [200, 400, 600, 800]
        assert z["point_refit_fwhm"].shape == (4, 2)
        assert z["group_status"].tolist() == ["ok"]
        assert z["group_fwhm0"][0] == pytest.approx(FWHM0, rel=0.2)
