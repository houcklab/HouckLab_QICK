"""Hardware-free tests of the charge-sweep doublet splitting fit and grid-sampling check (F40).

run_charge_sweep extracts the parity doublet of every slice, saves sep(V) / f_mean(V) in the
heatmap npz and fits sep(V) = cd_max |cos(pi (V - V0) / T_S)|, T_S = cd_period_mv / 2 (the
modified_ramsey_control model repeats every T/2). A grid coarser than T_S / 4 must be refused
(the runner's 5 mV step against a 4.37 mV period aliases); a fine grid must recover the model.
The splitting of each slice comes from a joint two-Lorentzian refit (refit_doublet_jointly):
the display's separate window fits read a resolved doublet low (0.8 x at 2 HWHM), which biased
cd_max low by 6 to 18 of its own sigmas end to end. A slice showing one line is censored below
the extent of the smoothed trace above a quarter of its peak (single_line_splitting_bound), which
must bound the true splitting at SNR 8 and for parity lines of unequal height; the display's
clipped Lorentzian widths do not, nor does the contiguous half-maximum width (it biased cd_max
-1.5 sigma at SNR 8 and -1.4 sigma at 60/40 heights). Both are checked through the real
QubitSpecSliceFF.display, and the whole chain through run_charge_sweep with the real display.
See docs/experiments/charge_sweep.md#doublet-splitting-fit.

    python -m pytest tests/test_charge_dispersion_fit.py
"""

import matplotlib

matplotlib.use("Agg")

import numpy as np
import pytest

import qicklab.runs.charge_sweep as cs
from qicklab.analysis.iq import project_iq_signal
from qicklab.analysis.spectroscopy import (
    fit_charge_dispersion_splitting,
    fit_doublet_mean,
    refit_doublet_jointly,
    single_line_splitting_bound,
    spectrum_noise_floor,
)
from qicklab.experiments.qubit_spec import QubitSpecSliceFF
from tests.test_doublet_selection import F0, _display, _grid, _spec_data
from tests.test_run_charge_sweep import SPEC_PARAMS, _Ctx, _fake_experiment

CD_MAX, T_MV, V0_MV, MIN_SEP = 0.682, 4.37, 1.0, 0.2


def _sep(v, rng, noise=0.01):
    s = CD_MAX * np.abs(np.cos(2 * np.pi * (1e3 * v - V0_MV) / T_MV)) + rng.normal(0, noise, v.size)
    return np.where(s < MIN_SEP, np.nan, s)  # unresolved below the resolution: censored


@pytest.mark.parametrize("prior", [None, T_MV])
def test_fine_grid_recovers_model(prior):
    rng = np.random.default_rng(1)
    v = np.arange(0.0, 10e-3, 0.2e-3)
    r = fit_charge_dispersion_splitting(v, _sep(v, rng), MIN_SEP, cd_period_mv=prior)
    assert r["status"] == "ok"
    assert r["n_censored"] > 0  # the zeros are censored, not fitted as sep = 0
    assert abs(r["cd_max_mhz"] - CD_MAX) < 4 * r["cd_max_err_mhz"]
    assert abs(r["cd_period_mv"] - T_MV) < 4 * r["cd_period_err_mv"]
    assert r["s_period_mv"] == pytest.approx(r["cd_period_mv"] / 2)
    # V0 is a maximum of S inside [V_min, V_min + T_S)
    assert abs(r["v0_mv"] - V0_MV) < 4 * r["v0_err_mv"]
    assert 0 < r["cd_max_err_mhz"] < 0.02 and 0 < r["cd_period_err_mv"] < 0.05


def test_runner_grid_with_known_period_is_refused():
    rng = np.random.default_rng(2)
    v = np.arange(0.0, 0.05, 0.005)  # the runner's charge_params grid
    r = fit_charge_dispersion_splitting(v, _sep(v, rng, 0.0), MIN_SEP, cd_period_mv=T_MV)
    assert r["status"] == "undersampled"
    assert np.isnan(r["cd_max_mhz"]) and np.isnan(r["cd_period_mv"])  # no alias period


def test_runner_grid_without_period_reports_no_alias_period():
    rng = np.random.default_rng(2)
    v = np.arange(0.0, 0.05, 0.005)
    r = fit_charge_dispersion_splitting(v, _sep(v, rng, 0.0), MIN_SEP)
    assert r["status"] != "ok" and np.isnan(r["cd_period_mv"])


def test_per_slice_censoring_level_removes_cd_max_bias():
    """A resolution coarser than min_sep (broad lines) needs per-slice censoring levels:
    censoring at min_sep alone biases cd_max low (-4 sigma at a 0.5 MHz true resolution)."""
    v = np.arange(0.0, 20e-3, 0.2e-3)
    pulls = {"per_slice": [], "min_sep_only": []}
    for seed in range(10):
        rng = np.random.default_rng(seed)
        s = CD_MAX * np.abs(np.cos(2 * np.pi * (1e3 * v - V0_MV) / T_MV))
        s = s + rng.normal(0, 0.02, v.size)
        s = np.where(s < 0.5, np.nan, s)  # true resolution 0.5 MHz (a 0.5 MHz HWHM line)
        for key, level in (("per_slice", np.full(v.size, 0.5)), ("min_sep_only", MIN_SEP)):
            r = fit_charge_dispersion_splitting(v, s, level, cd_period_mv=T_MV)
            assert r["status"] == "ok"
            pulls[key].append((r["cd_max_mhz"] - CD_MAX) / r["cd_max_err_mhz"])
    assert abs(np.mean(pulls["per_slice"])) < 1.0
    assert np.mean(pulls["min_sep_only"]) < -2.0


def test_censored_slice_without_bound_is_dropped():
    v = np.arange(0.0, 10e-3, 0.2e-3)
    s = _sep(v, np.random.default_rng(4))
    level = np.full(v.size, MIN_SEP)
    unbounded = np.flatnonzero(np.isnan(s))[:3]
    level[unbounded] = np.nan
    r = fit_charge_dispersion_splitting(v, s, level, cd_period_mv=T_MV)
    assert r["n_censored"] == int(np.isnan(s).sum()) - 3
    assert r["status"] == "ok"


def _spec_heights(lines, heights, hwhm, seed, snr=20.0):
    """_spec_data with one height per line (the parity populations need not be equal)."""
    x = _grid()
    y = sum(h * hwhm**2 / ((x - f) ** 2 + hwhm**2) for f, h in zip(lines, heights))
    rng = np.random.default_rng(seed)
    avgi = 0.3 + y + rng.normal(0, 1.0 / snr, x.size)
    avgq = -0.2 + rng.normal(0, 1.0 / snr, x.size)
    stack = lambda a: np.stack([a, a])[:, None, :]  # (ADC, read, freq)  # noqa: E731
    return {"config": {}, "data": {"x_pts": x, "avgi": stack(avgi), "avgq": stack(avgq)}}


def _contiguous_half_max_width(data):
    """The previous bound: the half-maximum run of bins around the tallest one."""
    x = data["data"]["x_pts"]
    y = project_iq_signal(data["data"]["avgi"][0][0], data["data"]["avgq"][0][0])
    base, _ = spectrum_noise_floor(y)
    i = int(np.argmax(y))
    above = y >= base + 0.5 * (y[i] - base)
    lo = hi = i
    while lo > 0 and above[lo - 1]:
        lo -= 1
    while hi < y.size - 1 and above[hi + 1]:
        hi += 1
    return x[hi] - x[lo]


@pytest.fixture
def fast_plots(monkeypatch):
    """The display's figures are not under test: skip the slow layout and file writes."""
    monkeypatch.setattr(cs.plt, "savefig", lambda *a, **k: None)
    monkeypatch.setattr(cs.plt, "tight_layout", lambda *a, **k: None)


@pytest.mark.parametrize("hwhm", [0.1, 0.2, 0.3])
def test_joint_refit_removes_selection_bias(hwhm, tmp_path, fast_plots):
    """Real display + selection: the selected separation reads low for a doublet a few HWHM
    apart; the joint refit's separation is within 1 % of the truth (8 seeds, SNR 20)."""
    for d in (0.5, 0.682):
        sel, joint = [], []
        for seed in range(8):
            data = _display(_spec_data([F0 - d / 2, F0 + d / 2], hwhm, seed), tmp_path)
            choice, refit, censor = cs._slice_doublet(data, MIN_SEP, SPEC_PARAMS["fit_window_mhz"])
            if choice["peak_sep"] is None:
                continue
            assert refit is not None and np.isnan(censor)
            sel.append(choice["peak_sep"] / d)
            joint.append((refit["centers"][1] - refit["centers"][0]) / d)
            assert abs(0.5 * refit["centers"].sum() - F0) < 0.01
            np.testing.assert_allclose(refit["hwhm"], hwhm, rtol=0.15)
        assert len(joint) >= 4
        assert abs(np.mean(joint) - 1) < 0.01
        if d / hwhm < 4:  # the bias the refit removes: 0.79-0.95 x here
            assert np.mean(sel) < 0.96


@pytest.mark.parametrize(
    "snr, ratio, min_old_violations",
    [(20.0, 1.0, 0), (8.0, 1.0, 1), (20.0, 0.6, 1), (8.0, 0.5, 1)],
)
def test_single_line_bound_holds_through_real_display(
    snr, ratio, min_old_violations, tmp_path, fast_plots
):
    """Every slice the selection calls single_line_unresolved is censored at a level at or
    above its true splitting, also at SNR 8 and when the weaker parity line is 0.5-0.6 as high.
    Neither the display's widest Lorentzian HWHM nor the contiguous half-maximum width (the
    two previous levels) is: the clipped window gives a fit narrower than d, and a noisy flank
    bin, a noise-raised peak or the dip before the weaker line ends the run inside the doublet."""
    n_unresolved, hwhm_violations, old_violations = 0, 0, 0
    for hwhm in (0.04, 0.1, 0.2, 0.3):
        for d in np.arange(0.0, 1.21, 0.04):
            for seed in range(2):
                spec = _spec_heights([F0 - d / 2, F0 + d / 2], [1.0, ratio], hwhm, seed, snr)
                data = _display(spec, tmp_path)
                choice, refit, censor = cs._slice_doublet(data, MIN_SEP, 0.5)
                if choice["source"] != "single_line_unresolved":
                    continue
                n_unresolved += 1
                assert refit is None
                if np.isnan(censor):  # too faint to bound: dropped, never a wrong ceiling
                    continue
                assert censor >= max(MIN_SEP, d), (hwhm, d, seed, censor)
                gammas = data["data"]["lorentz_gamma"]
                if gammas.size and d > max(MIN_SEP, gammas.max()):
                    hwhm_violations += 1
                if d > max(MIN_SEP, _contiguous_half_max_width(data)):
                    old_violations += 1
    assert n_unresolved >= 50
    assert hwhm_violations > 0  # the display's widths are not a bound
    assert old_violations >= min_old_violations  # nor is the contiguous half-maximum width


@pytest.mark.parametrize("snr", [20.0, 8.0])
def test_single_line_bound_holds_just_above_min_sep(snr, tmp_path, fast_plots):
    """Narrow lines split by just above min_sep (fine d steps): the band where the contiguous
    half-maximum width fell up to 15 kHz short of d."""
    n_unresolved = 0
    for hwhm in (0.04, 0.055, 0.07):
        for d in np.arange(0.18, 0.301, 0.005):
            for seed in range(2):
                spec = _spec_heights([F0 - d / 2, F0 + d / 2], [1.0, 1.0], hwhm, seed, snr)
                choice, _, censor = cs._slice_doublet(_display(spec, tmp_path), MIN_SEP, 0.5)
                if choice["source"] != "single_line_unresolved" or np.isnan(censor):
                    continue
                n_unresolved += 1
                assert censor >= d, (hwhm, d, seed, censor)
    assert n_unresolved >= 20


@pytest.mark.parametrize(
    "lines, hwhm, expected",
    [
        ([F0], 0.04, MIN_SEP),  # narrow line: its full width at quarter maximum (0.139) < min_sep
        ([F0], 0.1, 0.33),  # 2 sqrt(3) HWHM = 0.346, a bin or two less after smoothing
        # a broad line: below 2 sqrt(3) HWHM (0.693) because its wings lift the edge baseline
        # on this 2 MHz span; the blend's extent still exceeds its 0.3 MHz splitting
        ([F0], 0.2, 0.63),
        ([F0 - 0.15, F0 + 0.15], 0.2, 0.89),
        ([F0 - 0.15, F0 + 0.15], 0.04, 0.45),  # two lines, a gap between them: still one extent
        ([], 0.1, np.nan),  # noise only: no line, no bound (dropped, not censored)
    ],
)
def test_single_line_bound_cases(lines, hwhm, expected):
    data = _spec_data(lines, hwhm, 0, snr=200.0)
    got = single_line_splitting_bound(data, MIN_SEP)
    if np.isnan(expected):
        assert np.isnan(got)
    else:
        assert got == pytest.approx(expected, abs=0.02)  # a 9.95 kHz bin each side
    if len(lines) == 2:
        assert got > lines[1] - lines[0]


def test_joint_refit_needs_two_frequencies():
    data = _spec_data([F0 - 0.3, F0 + 0.3], 0.1, 0)
    assert refit_doublet_jointly(data, [F0], 0.5, MIN_SEP) is None
    r = refit_doublet_jointly(data, [F0 + 0.29, F0 - 0.31], 0.5, MIN_SEP)  # any order
    assert r["centers"][0] < r["centers"][1]
    np.testing.assert_allclose(r["centers"], [F0 - 0.3, F0 + 0.3], atol=0.01)


def test_too_few_resolved_points():
    v = np.arange(0.0, 3e-3, 0.5e-3)
    sep = np.array([0.5, np.nan, 0.4, np.nan, 0.6, np.nan])
    assert fit_charge_dispersion_splitting(v, sep, MIN_SEP)["status"] == "too_few_points"


def test_doublet_mean_line():
    v = np.arange(0.0, 5e-3, 0.5e-3)
    f = 3000.0 + 0.01 * (1e3 * v - 2.25)
    f[[1, 4]] = np.nan
    r = fit_doublet_mean(v, f)
    assert r["slope_mhz_per_mv"] == pytest.approx(0.01, abs=1e-9)
    assert r["f0_mhz"] == pytest.approx(3000.0 + 0.01 * (r["v_center_mv"] - 2.25), abs=1e-9)
    assert np.isnan(fit_doublet_mean(v[:2], f[:2])["f0_mhz"])


@pytest.mark.parametrize(
    "step_v, prior, warned",
    [(0.005, T_MV, True), (0.2e-3, T_MV, False), (0.005, None, False)],
)
def test_grid_sampling_report(step_v, prior, warned, capsys):
    pts = cs.report_grid_sampling(np.arange(0.0, 0.05, step_v), prior)
    out = capsys.readouterr().out
    assert "points per mV" in out
    assert ("WARNING" in out) is warned
    if prior is None:
        assert np.isnan(pts) and "period unknown" in out
    else:
        assert pts == pytest.approx(T_MV / 2 / (1e3 * step_v))


def _doublet_spectrum(volts, rng):
    """Projected-trace stand-in: two Lorentzians split by S(V), one per call (slice order)."""
    it = iter(volts)

    def data():
        v = next(it)
        x = np.linspace(-1.5, 1.5, 301)
        s = CD_MAX * abs(np.cos(2 * np.pi * (1e3 * v - V0_MV) / T_MV))
        g = 0.03
        amp = sum(1 / (1 + ((x - c) / g) ** 2) for c in (-s / 2, s / 2))
        amp = amp + rng.normal(0, 0.01, x.size)
        return {"x_pts": x, "avgi": [[amp]], "avgq": [[0.0 * amp]]}

    return data


def _real_display_spectrum(volts, hwhm, snr=20.0, ratio=1.0):
    """_spec_heights (2 MHz span) with the doublet split by S(V), one per call; the upper
    line is ``ratio`` as high as the lower."""
    it = iter(enumerate(volts))

    def data():
        i, v = next(it)
        s = CD_MAX * abs(np.cos(2 * np.pi * (1e3 * v - V0_MV) / T_MV))
        return _spec_heights([F0 - s / 2, F0 + s / 2], [1.0, ratio], hwhm, i, snr)["data"]

    return data


def _sweep(tmp_path, monkeypatch, grid, prior, real_display=None):
    monkeypatch.setattr(cs, "ramp_to", lambda yoko, v: None)
    monkeypatch.setattr(cs.plt, "pause", lambda *a, **k: None)
    monkeypatch.setattr(cs.plt, "show", lambda *a, **k: None)
    ctx = _Ctx(False)
    ctx.config.update(grid)
    volts = np.arange(grid["voltage_start"], grid["voltage_end"], grid["voltage_step"])
    if real_display is None:
        fake = _fake_experiment(tmp_path, _doublet_spectrum(volts, np.random.default_rng(3)))
    else:  # the real QubitSpecSliceFF.display (Lorentzian fits, clipped windows)
        spectra = _real_display_spectrum(volts, **real_display)

        class fake(_fake_experiment(tmp_path, spectra)):
            titlename = "Qubit Spec"
            display = QubitSpecSliceFF.display

    monkeypatch.setattr(cs, "QubitSpecSliceFF", fake)

    cs.run_charge_sweep(ctx, SPEC_PARAMS, cd_period_mv=prior)
    n = len(volts)
    return volts, np.load(tmp_path / f"slice{n - 1}_ChargeSweepHeatmap.npz")


def test_run_charge_sweep_saves_doublet_and_fit(tmp_path, monkeypatch, capsys):
    grid = {"voltage_start": 0.0, "voltage_end": 9e-3, "voltage_step": 0.2e-3}
    volts, npz = _sweep(tmp_path, monkeypatch, grid, T_MV)
    out = capsys.readouterr().out
    assert "WARNING" not in out and "points per S period" in out

    nv = len(volts)
    assert npz["doublet_freqs_mhz"].shape == (nv, 2) and npz["doublet_amp"].shape == (nv, 2)
    assert npz["lorentz_centers_mhz"].shape == (nv, 2)  # NaN-padded (fake display fits none)
    assert npz["doublet_refit_mhz"].shape == npz["doublet_refit_hwhm_mhz"].shape == (nv, 2)
    sep, src = npz["sep_mhz"], npz["doublet_source"]
    true_sep = CD_MAX * np.abs(np.cos(2 * np.pi * (1e3 * volts - V0_MV) / T_MV))
    resolved = np.isfinite(sep)
    assert resolved.any() and (~resolved).any()
    assert set(src[~resolved]) <= {"single_line_unresolved", "partner_not_significant"}
    # sep is the joint refit's: sub-bin, not the bin peaks'
    np.testing.assert_allclose(sep[resolved], true_sep[resolved], atol=0.005)
    np.testing.assert_allclose(npz["f_mean_mhz"][resolved], 0.0, atol=0.005)
    np.testing.assert_allclose(npz["doublet_refit_hwhm_mhz"][resolved], 0.03, rtol=0.2)
    # a single line is censored below its quarter-maximum extent, which bounds the splitting
    censored = src == "single_line_unresolved"
    assert np.all(np.isfinite(npz["censor_limit_mhz"][censored]))
    assert np.all(npz["censor_limit_mhz"][censored] >= true_sep[censored])
    assert np.all(np.isnan(npz["censor_limit_mhz"][resolved]))
    assert np.all(np.isnan(npz["f_mean_mhz"][~resolved]))

    assert str(npz["fit_status"]) == "ok"
    assert float(npz["prior_cd_period_mv"]) == T_MV
    assert float(npz["fit_cd_max_mhz"]) == pytest.approx(CD_MAX, abs=0.02)
    assert float(npz["fit_cd_period_mv"]) == pytest.approx(T_MV, rel=0.01)
    assert float(npz["fit_s_period_mv"]) == pytest.approx(T_MV / 2, rel=0.01)
    assert float(npz["fit_cd_max_err_mhz"]) > 0
    assert abs(float(npz["fit_f_slope_mhz_per_mv"])) < 0.01


@pytest.mark.parametrize("snr, ratio", [(20.0, 1.0), (8.0, 1.0), (20.0, 0.6)])
def test_run_charge_sweep_real_display_recovers_cd_max(
    snr, ratio, tmp_path, monkeypatch, capsys, fast_plots
):
    """End to end through the real display and selection at HWHM 0.2 MHz (cd_max = 3.4 HWHM).
    The display's separate window fits read these doublets 0.79-0.95 x low and gave cd_max
    13 sigma low; the joint refit must bring it within 4 of its own sigmas. At SNR 8, and with
    parity lines 60/40 high, the contiguous half-maximum width censored 2-3 HWHM blends below
    their splitting (cd_max -1.5 sigma over 12 seeds); every bound must hold here."""
    grid = {"voltage_start": 0.0, "voltage_end": 10e-3, "voltage_step": 0.2e-3}
    real_display = {"hwhm": 0.2, "snr": snr, "ratio": ratio}
    volts, npz = _sweep(tmp_path, monkeypatch, grid, T_MV, real_display=real_display)
    capsys.readouterr()
    src = npz["doublet_source"]
    true_sep = CD_MAX * np.abs(np.cos(2 * np.pi * (1e3 * volts - V0_MV) / T_MV))
    pair = np.isfinite(npz["doublet_freqs_mhz"][:, 1])
    resolved = np.isfinite(npz["sep_mhz"])
    assert pair.sum() >= 20 and resolved.sum() >= pair.sum() - 1
    selected = np.diff(npz["doublet_freqs_mhz"], axis=1).ravel()
    assert np.mean(selected[resolved] / true_sep[resolved]) < 0.96  # what the refit removes
    assert abs(np.mean(npz["sep_mhz"][resolved] / true_sep[resolved]) - 1) < 0.01
    censored = src == "single_line_unresolved"
    limit, true_censored = npz["censor_limit_mhz"][censored], true_sep[censored]
    bounded = np.isfinite(limit)  # NaN: too faint to bound, dropped
    assert censored.sum() >= 10 and bounded.sum() >= censored.sum() - 2
    assert np.all(limit[bounded] >= true_censored[bounded])

    assert str(npz["fit_status"]) == "ok"
    cd, err = float(npz["fit_cd_max_mhz"]), float(npz["fit_cd_max_err_mhz"])
    assert abs(cd - CD_MAX) < 4 * err + 0.002, (cd, err)
    t, t_err = float(npz["fit_cd_period_mv"]), float(npz["fit_cd_period_err_mv"])
    assert abs(t - T_MV) < 4 * t_err + 0.01, (t, t_err)


def test_run_charge_sweep_coarse_grid_warns_and_refuses_fit(tmp_path, monkeypatch, capsys):
    grid = {"voltage_start": 0.0, "voltage_end": 0.05, "voltage_step": 0.005}  # runner grid
    volts, npz = _sweep(tmp_path, monkeypatch, grid, T_MV)
    out = capsys.readouterr().out
    assert "WARNING: [ChargeSweep] step 5 mV" in out  # warns, never raises
    assert len(npz["voltage_pts"]) == len(volts) == 10
    assert str(npz["fit_status"]) == "undersampled"
    assert np.isnan(float(npz["fit_cd_period_mv"]))


@pytest.mark.parametrize(
    "grid",
    [
        {"voltage_start": 0.0, "voltage_end": 0.05, "voltage_step": -0.005},  # empty
        {"voltage_start": -11.0, "voltage_end": -10.5, "voltage_step": 0.1},  # |V| > 10
    ],
)
def test_run_charge_sweep_rejects_bad_grid_before_acquiring(grid, tmp_path, monkeypatch):
    ramps = []
    monkeypatch.setattr(cs, "ramp_to", lambda yoko, v: ramps.append(v))
    ctx = _Ctx(False)
    ctx.config.update(grid)
    fake = _fake_experiment(tmp_path, lambda: None)
    monkeypatch.setattr(cs, "QubitSpecSliceFF", fake)
    with pytest.raises(ValueError):
        cs.run_charge_sweep(ctx, SPEC_PARAMS)
    assert ramps == [] and fake.slices == []
