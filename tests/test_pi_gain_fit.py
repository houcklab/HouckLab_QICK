"""Hardware-free tests of the AutoCoherence single-shot gain choice (F64).

Stage 3 takes the pi gain from a cosine fit C(g) = B - A cos(pi N g / P) to the scanned
single-shot contrasts (fit_pi_gain_contrast), falling back to the scan argmax with fewer than
5 points, a failed fit, A <= 0, or P off the window / outside the scan; Stage 2.5 takes the
shortest readout window within one standard error of the best contrast. See
docs/experiments/auto_coherence.md#stages-in-detail.

    python -m pytest tests/test_pi_gain_fit.py
"""

import numpy as np
import pytest

import qicklab.analysis.fitting as fitting
import qicklab.runs.auto_coherence as ac
from qicklab.analysis.fitting import fit_pi_gain_contrast

G_PI = 6000.0
C_READ = 0.8
SHOTS = 1000


def _contrast(gains, g_pi=G_PI, rotations=1.0, rng=None, shots=SHOTS):
    """|P(e|e-prep) - P(e|g-prep)| with symmetric readout error (1 - C_READ) / 2, binomial noise."""
    g = np.asarray(gains, dtype=float)
    eps = (1.0 - C_READ) / 2.0
    p_exc = np.sin(np.pi * rotations * g / (2.0 * g_pi)) ** 2
    p_e = p_exc * (1.0 - eps) + (1.0 - p_exc) * eps
    if rng is None:
        return p_e - eps
    return np.abs(rng.binomial(shots, p_e) / shots - rng.binomial(shots, eps, g.size) / shots)


def _grid(centre, frac, pts):
    return np.unique(np.linspace(centre * (1 - frac), centre * (1 + frac), pts).astype(int))


@pytest.mark.parametrize("frac, pts", [(0.2, 21), (0.6, 100)])
def test_fit_beats_argmax(frac, pts):
    rng = np.random.default_rng(64)
    err_fit, err_arg = [], []
    for _ in range(150):
        g_pi = G_PI * (1 + rng.uniform(-0.05, 0.05))  # Rabi estimate within 5 %
        gains = _grid(G_PI, frac, pts)
        c = _contrast(gains, g_pi, rng=rng)
        fit = fit_pi_gain_contrast(gains, c, G_PI)
        assert fit["ok"], fit["reason"]
        assert fit["A"] > 0 and fit["dP"] > 0 and fit["n"] == gains.size
        err_fit.append(fit["P"] / g_pi - 1)
        err_arg.append(gains[np.argmax(c)] / g_pi - 1)
    rms_fit, rms_arg = np.sqrt(np.mean(np.square(err_fit))), np.sqrt(np.mean(np.square(err_arg)))
    assert rms_fit < 0.01
    assert rms_arg > 0.025
    assert rms_fit < rms_arg / 3


def test_fit_exact_noiseless():
    gains = _grid(G_PI, 0.2, 21)
    fit = fit_pi_gain_contrast(gains, _contrast(gains, 5800.0), G_PI)
    assert fit["ok"]
    assert fit["P"] == pytest.approx(5800.0, rel=1e-6)
    assert fit["A"] == pytest.approx(C_READ / 2, rel=1e-6)
    assert fit["B"] == pytest.approx(C_READ / 2, rel=1e-6)


def test_points_far_from_centre_are_not_fitted():
    gains = _grid(G_PI, 0.9, 40)
    fit = fit_pi_gain_contrast(gains, _contrast(gains), G_PI)
    assert fit["ok"]
    assert fit["n"] == int(np.sum(np.abs(gains / G_PI - 1) <= fitting.PI_GAIN_FIT_MAX_REL_DEV))
    assert fit["n"] < gains.size


def test_fallback_too_few_points():
    gains = _grid(G_PI, 0.2, 4)
    fit = fit_pi_gain_contrast(gains, _contrast(gains), G_PI)
    assert not fit["ok"] and "points" in fit["reason"]
    # duplicated gains do not count as distinct points
    fit = fit_pi_gain_contrast(np.repeat(gains, 2), _contrast(np.repeat(gains, 2)), G_PI)
    assert not fit["ok"]


def test_fallback_negative_amplitude():
    # a contrast minimum at the centre: the best cosine has A < 0
    gains = _grid(G_PI, 0.2, 21)
    c = 0.5 + 0.3 * np.cos(np.pi * gains / G_PI)
    fit = fit_pi_gain_contrast(gains, c, G_PI)
    assert not fit["ok"]
    assert "A =" in fit["reason"] and fit["A"] == pytest.approx(-0.3, rel=1e-6)


def test_fallback_p_on_window_edge():
    # true pi gain 8500 inside a +-60 % scan [2400, 9600] but beyond the P window
    # 6000 x [0.7, 1.3] = [4200, 7800]: P is pinned to the window edge with A > 0 -> fallback
    gains = _grid(G_PI, 0.6, 61)
    fit = fit_pi_gain_contrast(gains, _contrast(gains, 8500.0), G_PI)
    assert not fit["ok"]
    assert fit["reason"].startswith("P = 7800.0 on the edge of the window [4200, 7800]")
    assert fit["A"] > 0 and gains.min() < fit["P"] < gains.max()


def test_window_half_width_shrinks_with_rotations():
    # N = 3: h = min(0.3, 0.5 / 3) = 1/6, window 6000 x [5/6, 7/6] = [5000, 7000]; the true
    # P = 7200 lies inside h = 0.3 but outside this window -> edge fallback naming the window
    gains = _grid(G_PI, 0.25, 51)
    fit = fit_pi_gain_contrast(gains, _contrast(gains, 7200.0, rotations=3), G_PI, rotations=3)
    assert not fit["ok"] and "edge of the window [5000, 7000]" in fit["reason"]
    assert fit["A"] > 0
    # N = 1 on the same data shape: h = 0.3, P = 7200 is fitted
    fit1 = fit_pi_gain_contrast(gains, _contrast(gains, 7200.0), G_PI)
    assert fit1["ok"] and fit1["P"] == pytest.approx(7200.0, rel=1e-6)


@pytest.mark.parametrize("n_pulses, span", [(3, 0.08), (5, 0.032)])
def test_narrow_window_avoids_minimum_alias(n_pulses, span):
    # noisy extended-mode scans (51 pts, the ext_gain_span_init x 0.4^k spans): with the
    # window h = 0.5 / N the fit finds P; with h = 0.3 for every N the grid search lands on
    # the contrast-minimum alias (A < 0) and falls back in ~40 % (N=3) / ~75 % (N=5) of scans
    rng = np.random.default_rng(642)
    good = 0
    for _ in range(100):
        g_pi = G_PI * (1 + rng.uniform(-0.6 * span, 0.6 * span))
        gains = _grid(G_PI, span, 51)
        c = _contrast(gains, g_pi, rotations=n_pulses, rng=rng)
        fit = fit_pi_gain_contrast(gains, c, G_PI, rotations=n_pulses)
        good += fit["ok"] and abs(fit["P"] / g_pi - 1) < 0.01
    assert good >= 95


def test_fallback_p_outside_scan():
    # true pi gain 25 % above the centre, scan +-20 %: the contrast still rises at the edge
    gains = _grid(G_PI, 0.2, 21)
    fit = fit_pi_gain_contrast(gains, _contrast(gains, 1.25 * G_PI), G_PI)
    assert not fit["ok"] and "outside" in fit["reason"]
    assert fit["P"] == pytest.approx(1.25 * G_PI, rel=1e-3)


def test_fallback_fit_failure(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no convergence")

    monkeypatch.setattr(fitting, "curve_fit", boom)
    gains = _grid(G_PI, 0.2, 21)
    fit = fit_pi_gain_contrast(gains, _contrast(gains), G_PI)
    assert not fit["ok"] and "fit failed" in fit["reason"]


def test_flat_data_falls_back():
    gains = _grid(G_PI, 0.2, 21)
    fit = fit_pi_gain_contrast(gains, np.full(gains.size, 0.7), G_PI)
    assert not fit["ok"]


@pytest.mark.parametrize("n_pulses, span", [(3, 0.08), (5, 0.032), (7, 0.0128)])
def test_extended_period_is_p_over_n(n_pulses, span):
    centre = 6030.0
    gains = _grid(centre, span, 51)
    c = _contrast(gains, G_PI, rotations=n_pulses)
    fit = fit_pi_gain_contrast(gains, c, centre, rotations=n_pulses)
    assert fit["ok"], fit["reason"]
    assert fit["P"] == pytest.approx(G_PI, rel=1e-6)
    assert fit["A"] == pytest.approx(C_READ / 2, rel=1e-4)
    # with one pi rotation the model cannot follow the fringe: the amplitude is wrong
    wrong = fit_pi_gain_contrast(gains, c, centre, rotations=1.0)
    assert not wrong["ok"] or abs(wrong["A"] / (C_READ / 2) - 1) > 0.5


# ---- the AutoCoherence stages with a fake single-shot run


class _FakeSS:
    """Stands in for _run_single_shot_at_gain: contrast from _contrast for each call."""

    def __init__(self, g_pi=G_PI, seed=0, noise=True, pi_rot_per_pulse=1.0, cell_fid=None):
        self.g_pi, self.noise = g_pi, noise
        self.rng = np.random.default_rng(seed)
        self.pi_rot_per_pulse = pi_rot_per_pulse
        self.cell_fid = cell_fid
        self.calls = []

    def __call__(self, soc, soccfg, cfg, outerFolder, **kw):
        gain, shots, n = kw["qubit_gain"], kw["shots"], kw.get("num_pulses", 1)
        rl, ao = kw["readout_time"], kw["adc_offset"]
        self.calls.append(dict(gain=gain, shots=shots, n=n, path=kw.get("path"), rl=rl, ao=ao))
        if self.cell_fid is not None:
            fid = self.cell_fid[(rl, ao)]
        else:
            rng = self.rng if self.noise else None
            fid = float(_contrast([gain], self.g_pi, n * self.pi_rot_per_pulse, rng, shots)[0])
        return fid, 0.1, 0.2, None, None


def _params(**kw):
    return {**ac.AUTO_COHERENCE_PARAMS, **kw}


def _stage3(fake, monkeypatch, **kw):
    monkeypatch.setattr(ac, "_run_single_shot_at_gain", fake)
    log = []
    out = ac._stage_singleshot_optimize(
        None, None, {}, "x/", 4000.0, 0.05, None, kw.pop("estimate", 6000), 0, _params(**kw), log
    )
    return out, log


def test_stage3_uses_fitted_gain_for_final_run(monkeypatch):
    fake = _FakeSS(g_pi=6180.0, seed=3)
    (pi_gain, pi2_gain, *_), log = _stage3(fake, monkeypatch)
    scan = [c for c in fake.calls if c["shots"] == SHOTS]
    final = fake.calls[-1]
    assert len(scan) == 21 and final["shots"] == 2000
    assert final["gain"] == pi_gain and isinstance(pi_gain, int)
    assert pi2_gain == pi_gain // 2
    assert abs(pi_gain / 6180.0 - 1) < 0.01
    assert any("Cosine fit (21 pts" in line for line in log)


def test_stage3_three_points_keeps_argmax(monkeypatch):
    # the regression harness setting: ss_gain_pts=3 -> fallback, the argmax is unchanged
    fake = _FakeSS(g_pi=6100.0, noise=False)
    (pi_gain, pi2_gain, *_), log = _stage3(fake, monkeypatch, ss_gain_pts=3)
    scan = [c["gain"] for c in fake.calls[:3]]
    assert scan == [4800, 6000, 7200]
    assert pi_gain == 6000 and pi2_gain == 3000 and fake.calls[-1]["gain"] == 6000
    assert any("Cosine fit not used (3 points" in line for line in log)


def test_stage3_edge_rescan_then_fit(monkeypatch):
    # pi gain 40 % above the estimate: the first scan's argmax is its top edge -> rescan
    fake = _FakeSS(g_pi=8400.0, noise=False)
    (pi_gain, *_), log = _stage3(fake, monkeypatch)
    assert any("rescanning" in line for line in log)
    assert pi_gain == 8400
    assert fake.calls[-1]["gain"] == 8400


def test_select_readout_window_shortest_within_se():
    se = ac._contrast_se(0.81, SHOTS)
    assert se == pytest.approx(np.sqrt(2 * 0.905 * 0.095 / SHOTS))
    assert se == pytest.approx(0.0131, abs=2e-4)
    cells = [
        (5.0, 0.2, 0.70),
        (5.0, 0.9, 0.80),  # within one SE of the best: chosen (shortest, then smaller offset)
        (5.0, 1.6, 0.805),
        (10.0, 0.2, 0.81),  # best
        (15.0, 0.9, 0.79),
    ]
    rl, ao, fid, best, se_out = ac._select_readout_window(cells, SHOTS)
    assert (rl, ao, fid, best) == (5.0, 0.9, 0.80, 0.81)
    assert se_out == pytest.approx(se)
    # nothing within SE but the best itself
    rl, ao, *_ = ac._select_readout_window([(5.0, 0.2, 0.5), (10.0, 0.2, 0.81)], SHOTS)
    assert (rl, ao) == (10.0, 0.2)
    # order does not depend on the loop order; NaN cells are ignored
    cells2 = [(10.0, 0.2, 0.81), (5.0, 1.6, 0.805), (5.0, 0.9, float("nan"))]
    assert ac._select_readout_window(cells2, SHOTS)[:2] == (5.0, 1.6)
    assert ac._select_readout_window([(5.0, 0.2, float("nan"))], SHOTS) is None


def test_stage_optimize_readout_rule(monkeypatch):
    rls = np.linspace(5.0, 30.0, 6)
    aos = np.linspace(0.2, 3.0, 5)
    cell_fid = {(float(r), float(a)): (0.66 if r == 25.0 else 0.60) for r in rls for a in aos}
    cell_fid[(30.0, 3.0)] = 0.672  # best
    fake = _FakeSS(cell_fid=cell_fid)
    monkeypatch.setattr(ac, "_run_single_shot_at_gain", fake)
    log = []
    rl, ao = ac._stage_optimize_readout(
        None, None, {}, "x/", 4000.0, 6000, 0.05, None, 0, _params(), log
    )
    # SE(0.672) = 0.0166: 0.66 (rl=25) is the shortest within it; the plain max was (30, 3.0)
    assert (rl, ao) == (25.0, 0.2)
    assert len(fake.calls) == 30
    assert any("shortest window within one SE" in line for line in log)


@pytest.mark.parametrize(
    "label, rot_per_pulse, nsteps", [("pi", 1.0, [1, 3, 5]), ("pi/2", 0.5, [2, 6, 10])]
)
def test_optimize_gain_sequence_fits_each_n(monkeypatch, label, rot_per_pulse, nsteps):
    target = G_PI if label == "pi" else G_PI / 2
    # N pulses at gain g rotate by N pi g / G_PI: a pi/2 pulse is the gain G_PI / 2
    fake = _FakeSS(g_pi=G_PI, noise=False)
    monkeypatch.setattr(ac, "_run_single_shot_at_gain", fake)
    log = []
    gain, fid, thr, ang = ac._optimize_gain_sequence(
        None,
        None,
        {},
        "x/",
        4000.0,
        0.05,
        None,
        0,
        gain_estimate=int(target * 1.06),
        nsteps_list=nsteps,
        gain_span_init=0.2,
        gain_span_shrink=0.4,
        gain_pts=51,
        shots=SHOTS,
        relax_delay=3500,
        readout_time=15,
        adc_offset=1,
        pulse_path="p",
        log=log,
        label=label,
        rotations_per_pulse=rot_per_pulse,
    )
    assert abs(gain - target) <= 1
    assert sum("Cosine fit (51 pts" in line for line in log) == len(nsteps)
    # after the first step every scan is centred on the fitted gain, not on a grid point
    for call_n in nsteps[1:]:
        scan = sorted({c["gain"] for c in fake.calls if c["n"] == call_n})
        assert abs((scan[0] + scan[-1]) / 2 - target) <= 2
    assert (thr, ang) == (0.1, 0.2) and 0 < fid <= C_READ + 1e-9


def test_stage_extended_fits_pi2_with_half_rotations(monkeypatch):
    # _stage_extended_pulse_opt must fit the pi/2 sequence with N/2 pi rotations
    # (rotations_per_pulse=0.5); with N rotations every pi/2 step would fall back to the argmax
    g_pi = 6013.0
    fake = _FakeSS(g_pi=g_pi, noise=False)
    monkeypatch.setattr(ac, "_run_single_shot_at_gain", fake)
    log = []
    params = _params(pi_nsteps_list=[1, 3], pi2_nsteps_list=[2, 6])
    pi_gain, pi2_gain, *_ = ac._stage_extended_pulse_opt(
        None, None, {}, "x/", 4000.0, 0.05, None, int(g_pi * 1.06), 0, params, log
    )
    assert abs(pi_gain - g_pi) <= 1
    assert abs(pi2_gain - g_pi / 2) <= 1
    for n, rot in ((2, "1"), (6, "3")):
        assert any(f"[pi/2 N={n}] Cosine fit (51 pts, {rot} pi rotation(s)" in s for s in log)
    assert not any("[pi/2 N=" in s and "Cosine fit not used" in s for s in log)
    assert fake.calls[-1]["gain"] == pi_gain and fake.calls[-1]["n"] == 1
