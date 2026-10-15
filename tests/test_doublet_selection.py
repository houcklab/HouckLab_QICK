"""Parity-doublet selection (F04): QubitSpecSliceFF.display -> pick_parity_drive_freq.

Synthetic two-tone traces on the zero-span parity spectroscopy grid (3000 +- 1 MHz,
201 points), Lorentzian lines (HWHM 40 or 100 kHz) plus Gaussian noise at SNR ~20, run
through the real display with the ZSP step's values (min_sep 0.2, fit_window 0.5,
prominent_ratio 0.1). A single line or a doublet split below min_sep must not come back
as a doublet (pick_parity_drive_freq raises); resolvable doublets must give both centres
within 10 kHz (25 kHz for the blended 0.3 MHz / 100 kHz case). A single line must be
reported at the line, also on the coarse Run2ToneSpec (0.0995 MHz step) and
charge-dispersion (0.0198 MHz step) grids. Each display gate (window clip, full-window
fallback, edge, sub-grid width, seed distance, duplicate with tallest seed first) is pinned
by a test with the Lorentzian fit stubbed; the sub-grid width gate is also run through the
real fit on the coarse grid (a one-bin spike is dropped; a typical sub-step line at SNR 50
is kept, which holds only most of the time, see the test).
SNR 20 is deliberate: there is no significance gate, and below SNR ~15 a noise maximum is
often accepted as the second line (documented in docs/experiments/two_tone_spec.md step 4;
not asserted here). The two-highest-bin-peaks branch (no Lorentzian centre, bin peaks 0.199
MHz apart), the run's min_sep_MHz hand-off to pick_parity_drive_freq and the selection
provenance (parity_freq_source, parity_peak_sep_MHz) in the saved ZSP cfg are pinned
directly.
"""

import os

os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from qicklab.analysis.spectroscopy import (  # noqa: E402
    choose_two_tone_freqs_from_lorentz_or_peaks,
    pick_parity_drive_freq,
)
from qicklab.experiments.qubit_spec import QubitSpecSliceFF  # noqa: E402

F0 = 3000.0
MIN_SEP = 0.2
FIT_WINDOW = 0.5
PROMINENT_RATIO = 0.1
SNR = 20.0


def _grid():
    span, n = 1.0, 201
    step = 2 * span / n
    return F0 - span + step * np.arange(n)


def _spec_data(lines, hwhm, seed, x=None, snr=SNR):
    x = _grid() if x is None else x
    y = np.zeros_like(x)
    for f in lines:
        y += hwhm**2 / ((x - f) ** 2 + hwhm**2)
    rng = np.random.default_rng(seed)
    sigma = 1.0 / snr
    avgi = 0.3 + y + rng.normal(0, sigma, x.size)
    avgq = -0.2 + rng.normal(0, sigma, x.size)
    stack = lambda a: np.stack([a, a])[:, None, :]  # (ADC, read, freq)  # noqa: E731
    return {"config": {}, "data": {"x_pts": x, "avgi": stack(avgi), "avgq": stack(avgq)}}


def _display(data, tmp_path):
    exp = object.__new__(QubitSpecSliceFF)
    exp.cfg = {"qubit_gain": 500, "Gauss": True, "sigma": 2}
    exp.titlename = "Qubit Spec"
    exp.iname = str(tmp_path / "spec.png")
    exp.display(
        data,
        plotDisp=False,
        figNum=2,
        min_sep=MIN_SEP,
        fit_window_mhz=FIT_WINDOW,
        prominent_ratio=PROMINENT_RATIO,
    )
    return data


SEEDS = range(5)


@pytest.mark.parametrize("hwhm", [0.04, 0.1])
@pytest.mark.parametrize("seed", SEEDS)
def test_single_line_is_not_a_doublet(tmp_path, hwhm, seed):
    data = _display(_spec_data([F0 + 0.0123], hwhm, seed), tmp_path)
    choice = choose_two_tone_freqs_from_lorentz_or_peaks(data, min_sep_mhz=MIN_SEP)
    assert choice["source"] == "single_line_unresolved", choice
    assert choice["peak_sep"] is None
    assert choice["freqs"].size == 1
    with pytest.raises(RuntimeError, match="no resolved parity doublet"):
        pick_parity_drive_freq(data, which="lower", min_sep_mhz=MIN_SEP)


@pytest.mark.parametrize("hwhm", [0.04, 0.1])
@pytest.mark.parametrize("seed", SEEDS)
def test_sub_min_sep_doublet_is_unresolved(tmp_path, hwhm, seed):
    data = _display(_spec_data([F0 - 0.075, F0 + 0.075], hwhm, seed), tmp_path)
    with pytest.raises(RuntimeError, match="no resolved parity doublet"):
        pick_parity_drive_freq(data, which="lower", min_sep_mhz=MIN_SEP)


@pytest.mark.parametrize(
    "split,hwhm,tol",
    [(0.3, 0.04, 0.010), (0.3, 0.1, 0.025), (0.6, 0.04, 0.010), (0.6, 0.1, 0.010)],
    ids=["0.3/40k", "0.3/100k", "0.6/40k", "0.6/100k"],
)
@pytest.mark.parametrize("seed", SEEDS)
def test_resolved_doublet_centres(tmp_path, split, hwhm, tol, seed):
    # 0.3/100k is the blended-centre case the window clip fixes: with the full 0.5 MHz window
    # each fit holds both wide lines and lands near the midpoint (~0.15 MHz off).
    lo, hi = F0 - split / 2 + 0.0037, F0 + split / 2 + 0.0037
    data = _display(_spec_data([lo, hi], hwhm, seed), tmp_path)
    low = pick_parity_drive_freq(data, which="lower", min_sep_mhz=MIN_SEP)
    high = pick_parity_drive_freq(data, which="higher", min_sep_mhz=MIN_SEP)
    assert abs(low["lower"] - lo) < tol, low
    assert abs(low["higher"] - hi) < tol, low
    assert low["picked"] == low["lower"] and high["picked"] == high["higher"]
    assert low["peak_sep_MHz"] >= MIN_SEP


def _with_centres(centres, peaks_data):
    data = {"data": dict(peaks_data["data"])}
    data["data"]["lorentz_centers"] = np.asarray(centres, dtype=float)
    return data


def test_close_lorentzian_centres_are_merged(tmp_path):
    # two window fits that converged on one line, 3 kHz apart: one line, not a doublet
    base = _spec_data([F0], 0.04, 0)
    choice = choose_two_tone_freqs_from_lorentz_or_peaks(
        _with_centres([F0 - 0.0015, F0 + 0.0015], base), min_sep_mhz=MIN_SEP
    )
    assert choice["source"] == "single_line_unresolved"
    assert choice["freqs"].size == 1 and abs(choice["freqs"][0] - F0) < 1e-9


def test_one_centre_never_paired_with_its_own_neighbour_bin():
    # the removed fallback paired the Lorentzian centre with the same line one bin over
    base = _spec_data([F0], 0.04, 1)
    with pytest.raises(RuntimeError, match="no resolved parity doublet"):
        pick_parity_drive_freq(_with_centres([F0 + 0.001], base), min_sep_mhz=MIN_SEP)


def test_min_sep_is_honoured():
    # 0.15 MHz apart passes the old default min_sep 0.1 but not the configured 0.2
    base = _spec_data([F0 - 0.075, F0 + 0.075], 0.04, 2)
    data = _with_centres([F0 - 0.075, F0 + 0.075], base)
    assert pick_parity_drive_freq(data, min_sep_mhz=0.1)["peak_sep_MHz"] == pytest.approx(0.15)
    with pytest.raises(RuntimeError):
        pick_parity_drive_freq(data, min_sep_mhz=MIN_SEP)


def test_bin_peak_inside_the_fitted_line_is_not_its_partner():
    # one Lorentzian centre plus a bin peak 0.21 MHz away (> min_sep): a partner for a narrow
    # fitted line, but inside a 0.3 MHz HWHM line it is that line (or an unresolved blend)
    base = _spec_data([F0 - 0.105, F0 + 0.105], 0.04, 0)
    data = _with_centres([F0 - 0.105], base)
    peaks = choose_two_tone_freqs_from_lorentz_or_peaks(data, min_sep_mhz=MIN_SEP)
    assert peaks["source"] == "one_lorentzian_center_plus_peak", peaks
    data["data"]["lorentz_gamma"] = np.array([0.3])
    one = choose_two_tone_freqs_from_lorentz_or_peaks(data, min_sep_mhz=MIN_SEP)
    assert one["source"] == "single_line_unresolved"
    assert one["freqs"] == pytest.approx([F0 - 0.105])


def test_close_bin_peaks_without_lorentzian_keep_the_taller():
    # find_peaks' distance is round(min_sep/dx) bins = 20 x 0.00995 = 0.199 MHz on the ZSP grid,
    # just under min_sep: with no Lorentzian centre, two bin peaks that close are one
    # unresolved line, reported at the taller peak (here the higher-frequency one)
    x = _grid()
    lo, hi = x[100], x[120]
    assert MIN_SEP - 0.01 < hi - lo < MIN_SEP
    w = 0.01
    y = 0.3 + 0.6 * w**2 / ((x - lo) ** 2 + w**2) + 1.0 * w**2 / ((x - hi) ** 2 + w**2)
    stack = lambda a: np.stack([a, a])[:, None, :]  # noqa: E731
    data = {
        "data": {
            "x_pts": x,
            "avgi": stack(y),
            "avgq": stack(np.full_like(x, -0.2)),
            "lorentz_centers": np.array([]),
        }
    }
    choice = choose_two_tone_freqs_from_lorentz_or_peaks(data, min_sep_mhz=MIN_SEP)
    assert choice["peak_info_raw"]["peak_freqs"] == pytest.approx([lo, hi])  # both bins found
    assert choice["source"] == "single_line_unresolved", choice
    assert choice["peak_sep"] is None
    assert choice["freqs"] == pytest.approx([hi])
    with pytest.raises(RuntimeError, match="no resolved parity doublet"):
        pick_parity_drive_freq(data, min_sep_mhz=MIN_SEP)


class _RunCtx:
    soc = soccfg = None
    qubit_frequency_center = F0
    resonator_frequency_center = 7000.0
    start_voltage = 0.0

    def __init__(self, tmp_path):
        self.outerFolder = str(tmp_path) + "/"

    def working_config(self):
        return {
            "res_ch": 0,
            "qubit_ch": 1,
            "ro_chs": [0],
            "nqz": 2,
            "qubit_nqz": 1,
            "mixer_freq": 0.0,
        }


def _run_params(recalibrate=True, lower=None, higher=None):
    return {
        "ZSP_RecalibrateParityFreqs": recalibrate,
        "ZSP_ParitySpec_params": {
            "reps": 1,
            "rounds": 1,
            "relax_delay": 1,
            "Gauss": False,
            "sigma": 0.05,
            "gain": 1000,
            "qubit_length": 1,
            "SpecSpan": 1.0,
            "SpecNumPoints": 201,
            "min_sep_MHz": MIN_SEP,
            "fit_window_mhz": FIT_WINDOW,
            "prominent_ratio": PROMINENT_RATIO,
        },
        "ZSP_ParityFreqs_Cached": {
            "which_to_park": "lower",
            "lower_peak_MHz": lower,
            "higher_peak_MHz": higher,
        },
        "ZSP_RecalibrateSeparator": False,
        "ZSP_AnalysisParams": {"classifier_method": "kmeans"},
        "ZSP_RunMode": "strobe",
        "ZSP_StrobeParams": {},
        "ZSP_DriveParams": {"qubit_gain": 100, "pulse_gain": 100, "res_phase": 0},
        "ZSP_StartSrc": "internal",
    }


def _patch_spec(monkeypatch, spec):
    import qicklab.runs.zero_span as zs

    class FakeSpec:
        def __init__(self, **kwargs):
            pass

        def acquire(self):
            return spec

    monkeypatch.setattr(zs, "QubitSpecSliceFF", FakeSpec)
    monkeypatch.setattr(zs, "finish", lambda *a, **k: None)
    return zs


def test_run_zero_span_parity_passes_the_configured_min_sep(monkeypatch, tmp_path):
    # the run must hand ZSP_ParitySpec_params['min_sep_MHz'] to pick_parity_drive_freq: a
    # 0.15 MHz "doublet" passes the 0.1 MHz default but must stop the run at 0.2 MHz
    from qicklab.analysis.spectroscopy import pick_parity_drive_freq as real_pick

    base = _spec_data([F0 - 0.075, F0 + 0.075], 0.04, 2)
    zs = _patch_spec(monkeypatch, _with_centres([F0 - 0.075, F0 + 0.075], base))

    picks = []

    def recording_pick(spec_data, **kwargs):
        picks.append(kwargs)
        chosen = real_pick(spec_data, **kwargs)
        raise AssertionError(f"run accepted a sub-min_sep doublet: {chosen}, kwargs {kwargs}")

    monkeypatch.setattr(zs, "pick_parity_drive_freq", recording_pick)

    with pytest.raises(RuntimeError, match="no resolved parity doublet"):
        zs.run_zero_span_parity(_RunCtx(tmp_path), _run_params())
    assert len(picks) == 1 and picks[0].get("min_sep_mhz") == MIN_SEP, picks


class _StopAtZsp(Exception):
    pass


def _capture_zsp_cfg(monkeypatch, zs):
    seen = {}

    def fake_zsp(**kwargs):
        seen["cfg"] = kwargs["cfg"]
        raise _StopAtZsp

    monkeypatch.setattr(zs, "ZeroSpanParity", fake_zsp)
    return seen


def test_run_zero_span_parity_records_selection_provenance(monkeypatch, tmp_path):
    # the saved ZSP cfg must say which selection path produced the parked line
    lines = [F0 - 0.3, F0 + 0.3]
    zs = _patch_spec(monkeypatch, _with_centres(lines, _spec_data(lines, 0.04, 3)))
    seen = _capture_zsp_cfg(monkeypatch, zs)
    with pytest.raises(_StopAtZsp):
        zs.run_zero_span_parity(_RunCtx(tmp_path), _run_params())
    cfg = seen["cfg"]
    assert cfg["parity_drive_freq"] == pytest.approx(F0 - 0.3)
    assert cfg["parity_freq_source"] == "two_lorentzian_centers"
    assert cfg["parity_peak_sep_MHz"] == pytest.approx(0.6)


@pytest.mark.parametrize("lower, higher, sep", [(F0 - 0.3, F0 + 0.3, 0.6), (F0 - 0.3, None, None)])
def test_run_zero_span_parity_records_cached_provenance(monkeypatch, tmp_path, lower, higher, sep):
    import qicklab.runs.zero_span as zs

    seen = _capture_zsp_cfg(monkeypatch, zs)
    with pytest.raises(_StopAtZsp):
        zs.run_zero_span_parity(
            _RunCtx(tmp_path), _run_params(recalibrate=False, lower=lower, higher=higher)
        )
    cfg = seen["cfg"]
    assert cfg["parity_drive_freq"] == lower
    assert cfg["parity_freq_source"] == "cached"
    if sep is None:
        assert cfg["parity_peak_sep_MHz"] is None
    else:
        assert cfg["parity_peak_sep_MHz"] == pytest.approx(sep)


# --- display gates, with the Lorentzian fit stubbed so each gate is exercised directly ---


def _stub_fits(monkeypatch, offset_for, gamma=0.04):
    """Replace the display's fit with one centred at seed + offset_for(seed, window) (None = fit
    failed, "edge" = on the window's outermost grid point away from the scan centre), x_fit the
    grid points in the window as in the real fit; record (seed, window) per call."""
    import qicklab.experiments.qubit_spec as qs

    calls = []

    def fake_fit(x, y, peak_x, fit_window_mhz):
        calls.append((float(peak_x), float(fit_window_mhz)))
        off = offset_for(float(peak_x), float(fit_window_mhz))
        if off is None:
            return None
        xf = np.asarray(x)[np.abs(np.asarray(x) - peak_x) <= fit_window_mhz]
        if isinstance(off, str):
            c = float(xf.min() if peak_x < F0 else xf.max())
        else:
            c = float(peak_x) + off
        return {
            "center": c,
            "fwhm": 2 * gamma,
            "gamma": gamma,
            "amplitude": 1.0,
            "offset": 0.0,
            "r2": 0.9,
            "x_fit": xf,
            "y_fit": np.zeros_like(xf),
        }

    monkeypatch.setattr(qs, "fit_lorentzian_near_peak", fake_fit)
    return calls


def _doublet(tmp_path, lines=(F0 - 0.15, F0 + 0.15), seed=0):
    """Selected bin peaks (low, high) and the taller one, from an unstubbed display."""
    data = _display(_spec_data(list(lines), 0.04, seed), tmp_path)
    peaks = data["data"]["two_tone_peak_freqs"]
    amps = data["data"]["two_tone_peak_amps"]
    assert peaks.size == 2
    return peaks, float(peaks[int(np.argmax(amps))])


def _stubbed_display(
    monkeypatch, tmp_path, offset_for, lines=(F0 - 0.15, F0 + 0.15), seed=0, gamma=0.04
):
    calls = _stub_fits(monkeypatch, offset_for, gamma)
    data = _display(_spec_data(list(lines), 0.04, seed), tmp_path)
    return data, calls


def test_two_peak_fit_window_is_clipped_to_half_separation(monkeypatch, tmp_path):
    peaks, _ = _doublet(tmp_path)
    data, calls = _stubbed_display(monkeypatch, tmp_path, lambda p, w: 0.0)
    half_sep = 0.5 * (peaks[1] - peaks[0])
    assert half_sep < FIT_WINDOW
    assert [w for _, w in calls] == pytest.approx([half_sep, half_sep])
    assert data["data"]["lorentz_num_fits"] == 2


def test_fit_far_from_its_seed_bin_is_dropped(monkeypatch, tmp_path):
    # the low seed's fit wanders 0.12 MHz (> min_sep/2 = 0.1, > HWHM/2) away from the other
    # line in both windows, so only the seed gate can drop it; the high seed's stays within 0.09
    peaks, _ = _doublet(tmp_path)
    data, _ = _stubbed_display(
        monkeypatch, tmp_path, lambda p, w: -0.12 if p == peaks[0] else -0.09
    )
    assert data["data"]["lorentz_num_fits"] == 1
    assert data["data"]["lorentz_centers"] == pytest.approx([peaks[1] - 0.09])


def test_seed_gate_scales_with_the_fitted_width(monkeypatch, tmp_path):
    # a broad line's flat top jitters its seed bin: 0.12 MHz off is kept for a fitted HWHM of
    # 0.3 (tolerance HWHM/2 = 0.15), dropped for HWHM 0.04 (tolerance min_sep/2 = 0.1)
    lines = (F0 - 0.3, F0 + 0.3)
    peaks, _ = _doublet(tmp_path, lines=lines)

    def shift(p, w):
        return -0.12 if p == peaks[0] else 0.12

    data, _ = _stubbed_display(monkeypatch, tmp_path, shift, lines=lines, gamma=0.3)
    assert data["data"]["lorentz_centers"] == pytest.approx([peaks[0] - 0.12, peaks[1] + 0.12])
    data, _ = _stubbed_display(monkeypatch, tmp_path, shift, lines=lines, gamma=0.04)
    assert data["data"]["lorentz_num_fits"] == 0


def test_duplicate_conflict_keeps_the_tallest_seeds_fit(monkeypatch, tmp_path):
    # both fits stay within min_sep/2 of their seeds but end up < min_sep apart: the taller
    # seed's fit is kept whichever side of the doublet it is on (frequency order must not decide)
    for lines, seed in (((F0 - 0.15, F0 + 0.15), 0), ((F0 - 0.15, F0 + 0.15), 1)):
        peaks, tall = _doublet(tmp_path, lines, seed)
        short = float(peaks[0] if tall == peaks[1] else peaks[1])
        toward = np.sign(short - tall)
        data, _ = _stubbed_display(
            monkeypatch,
            tmp_path,
            lambda p, w: 0.05 * toward if p == tall else -0.09 * toward,
            lines,
            seed,
        )
        assert abs((tall + 0.05 * toward) - (short - 0.09 * toward)) < MIN_SEP
        assert data["data"]["lorentz_num_fits"] == 1
        assert data["data"]["lorentz_centers"] == pytest.approx([tall + 0.05 * toward])


def test_taller_seed_is_fitted_first(monkeypatch, tmp_path):
    for seed in (0, 1, 2):
        _, tall = _doublet(tmp_path, seed=seed)
        _, calls = _stubbed_display(monkeypatch, tmp_path, lambda p, w: 0.0, seed=seed)
        assert calls[0][0] == pytest.approx(tall)


def test_edge_pinned_or_failed_clipped_fit_falls_back_to_full_window(monkeypatch, tmp_path):
    # clipped fit: low seed pinned to its window edge, high seed fails; full-window fits good
    peaks, _ = _doublet(tmp_path)

    def offset_for(p, w):
        if w < FIT_WINDOW:
            return w if p == peaks[0] else None
        return 0.003

    data, calls = _stubbed_display(monkeypatch, tmp_path, offset_for)
    assert sorted(w for _, w in calls).count(FIT_WINDOW) == 2
    assert data["data"]["lorentz_centers"] == pytest.approx(peaks + 0.003)


def test_edge_pinned_fit_is_dropped(monkeypatch, tmp_path):
    # the low seed's fits sit on their window's outer grid point in both windows; a broad
    # fitted HWHM (0.4) lets them through the seed gate, so only the edge gate can drop them
    peaks, _ = _doublet(tmp_path)
    data, calls = _stubbed_display(
        monkeypatch, tmp_path, lambda p, w: 0.0 if p == peaks[1] else "edge", gamma=0.4
    )
    assert data["data"]["lorentz_centers"] == pytest.approx([peaks[1]])
    half_sep = 0.5 * (peaks[1] - peaks[0])
    assert [w for p, w in calls if p == peaks[0]] == pytest.approx([half_sep, FIT_WINDOW])


# --- the selected single line must be the real line, on fine and coarse grids ---


def _display_on(x, lines, hwhm, seed, tmp_path, snr=SNR):
    return _display(_spec_data(lines, hwhm, seed, x=x, snr=snr), tmp_path)


def _coarse_grid(span, n):
    step = 2 * span / n
    return F0 - span + step * np.arange(n)


@pytest.mark.parametrize("hwhm", [0.1, 0.15])
@pytest.mark.parametrize("seed", [2, 6, 15, 17, 19])
def test_single_line_reported_at_the_line_zsp_grid(tmp_path, hwhm, seed):
    # a flank/noise maximum selected as the second peak must not displace the line's own fit
    line = F0 + 0.0123
    data = _display(_spec_data([line], hwhm, seed), tmp_path)
    choice = choose_two_tone_freqs_from_lorentz_or_peaks(data, min_sep_mhz=MIN_SEP)
    assert choice["source"] == "single_line_unresolved"
    assert abs(choice["freqs"][0] - line) < 0.03, choice["freqs"] - line
    assert np.any(np.abs(data["data"]["lorentz_centers"] - line) < 0.03)


@pytest.mark.parametrize("hwhm", [0.3, 0.5, 1.0])
@pytest.mark.parametrize("seed", range(6))
def test_single_line_lorentzian_kept_on_run2tonespec_grid(tmp_path, hwhm, seed):
    # 10 MHz half-span, 201 points (0.0995 MHz step): the clipped window often holds < 6
    # points, so the fit must fall back to the full window rather than vanish
    line = F0 + 0.0123
    data = _display_on(_coarse_grid(10.0, 201), [line], hwhm, seed, tmp_path)
    centres = np.asarray(data["data"]["lorentz_centers"])
    assert np.any(np.abs(centres - line) <= hwhm / 2), centres - line


@pytest.mark.parametrize("hwhm", [0.04, 0.1, 0.15])
@pytest.mark.parametrize("seed", range(6))
def test_centred_line_stays_centred_on_charge_dispersion_grid(tmp_path, hwhm, seed):
    # 1 MHz half-span, 101 points, centre_peak_tol 0.05: the run's centred-mode check
    data = _display_on(_coarse_grid(1.0, 101), [F0], hwhm, seed, tmp_path)
    choice = choose_two_tone_freqs_from_lorentz_or_peaks(data, min_sep_mhz=MIN_SEP)
    assert choice["freqs"].size == 1
    assert abs(choice["freqs"][0] - F0) <= 0.05, choice


def test_sub_grid_width_fit_is_dropped(monkeypatch, tmp_path):
    # a fit with HWHM below a quarter grid step (0.00995 MHz on the ZSP grid) is a spike through
    # a single bin, not a resolved line: dropped in the clipped and the full window alike; the
    # same fit at HWHM = a quarter step is kept
    peaks, _ = _doublet(tmp_path)
    step = float(np.median(np.diff(_grid())))
    data, calls = _stubbed_display(monkeypatch, tmp_path, lambda p, w: 0.0, gamma=0.24 * step)
    assert data["data"]["lorentz_num_fits"] == 0
    assert sorted(w for _, w in calls).count(FIT_WINDOW) == 2  # full-window retry ran
    data, _ = _stubbed_display(monkeypatch, tmp_path, lambda p, w: 0.0, gamma=0.25 * step)
    assert data["data"]["lorentz_centers"] == pytest.approx(peaks)


@pytest.mark.parametrize("hwhm", [0.04, 0.05])
@pytest.mark.parametrize("seed", range(6))
def test_sub_step_line_lorentzian_kept_on_run2tonespec_grid(tmp_path, hwhm, seed):
    # typical case, not a guarantee: a line narrower than the 0.0995 MHz step (real fit, SNR
    # 50), 0.37 step from its nearest bin, keeps its fit for these seeds and is centred far
    # better than its bin peak (~37 kHz off). Pins the cut at a quarter step (a half-step cut
    # fails here). A sub-step line's fit can collapse below the cut and be dropped (about 10 %
    # of trials at HWHM 40 kHz, SNR 50, random offset; about 20 % midway between bins), see
    # docs/experiments/two_tone_spec.md step 3.
    line = F0 + 0.0123
    data = _display_on(_coarse_grid(10.0, 201), [line], hwhm, seed, tmp_path, snr=50.0)
    centres = np.asarray(data["data"]["lorentz_centers"])
    assert np.any(np.abs(centres - line) <= hwhm / 2), centres - line


@pytest.mark.parametrize("seed", range(6))
def test_single_bin_spike_is_dropped_on_run2tonespec_grid(tmp_path, seed):
    # real fit: a strong one-bin spike 3 MHz from a line collapses onto its bin and is dropped;
    # the line keeps its fit
    x = _coarse_grid(10.0, 201)
    data = _spec_data([F0], 0.3, seed, x=x)
    k = int(np.argmin(np.abs(x - (F0 + 3.0))))
    data["data"]["avgi"][:, :, k] += 0.8
    data = _display(data, tmp_path)
    assert np.any(np.abs(data["data"]["two_tone_peak_freqs"] - x[k]) < 1e-9)  # spike seeded
    centres = np.asarray(data["data"]["lorentz_centers"])
    assert np.all(np.abs(centres - x[k]) > 0.5), centres
    assert np.any(np.abs(centres - F0) <= 0.15), centres
