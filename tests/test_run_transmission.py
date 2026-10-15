"""Hardware-free tests for the transmission carry-over (F03, F52).

run_transmission_fit / run_transmission_sweep must carry display()'s hanger-fit minimum
(``hanger_fit_min_freq_mhz``) into ctx.config['pulse_freq'], fall back to the raw argmin with a
printed warning when that fit failed, and (sweep, cavity_min=False) keep the raw argmax; and
(F52) only when the trace passes the resonator gate: on a noise-only trace pulse_freq is left
as it was. See docs/architecture.md#carry-overs and docs/experiments/transmission_fit.md.

    python -m pytest tests/test_run_transmission.py
"""

import matplotlib

matplotlib.use("Agg")

import numpy as np
import pytest

import qicklab.runs.resonator as res_runs
from qicklab.analysis.fitting import hanger_model_db
from qicklab.core.context import Context
from qicklab.experiments.transmission import CavitySpecFF

CENTER = 7095.0
FIT_MIN = 7095.3989
RAW_MIN = 7095.35
RAW_MAX = 7091.0
FAKE_F0, FAKE_KAPPA = 7095.3, 0.4  # the fake trace's dip (MHz) and its |f0|/Qtot linewidth
FAKE_POPT = [FAKE_F0, FAKE_F0 / FAKE_KAPPA, FAKE_F0 / FAKE_KAPPA / 0.8, 0.0, -35.0]


def _fake_trace(kind, seed=0):
    """``results`` (1, 1, 2, N) and fpts over CENTER +- 5 MHz: a 14 dB hanger dip at FAKE_F0,
    a 6 dB peak at RAW_MAX, or 0.3 dB noise on a flat -35 dB line; Q = 0."""
    fpts = np.linspace(CENTER - 5, CENTER + 5, 201)
    rng = np.random.default_rng(seed)
    if kind == "dip":
        y = hanger_model_db(fpts, *FAKE_POPT) + 0.05 * rng.standard_normal(fpts.size)
    elif kind == "peak":
        y = -35 + 6 / (1 + ((fpts - RAW_MAX) / 0.15) ** 2) + 0.05 * rng.standard_normal(fpts.size)
    else:
        y = -35 + 0.3 * rng.standard_normal(fpts.size)
    results = np.zeros((1, 1, 2, fpts.size))
    results[0, 0, 0] = 10 ** (y / 20)
    return fpts, results


class _FakeTrans:
    """Stands in for CavitySpecFF: acquire sets peakFreq_min/max, display optionally 'fits'."""

    instances = []
    fit_ok = True
    kind = "dip"

    def __init__(self, path=None, cfg=None, soc=None, soccfg=None, outerFolder=None):
        self.cfg = cfg
        type(self).instances.append(self)

    def acquire(self):
        self.peakFreq_min, self.peakFreq_max = RAW_MIN, RAW_MAX
        fpts, results = _fake_trace(type(self).kind)
        return {"config": self.cfg, "data": {"fpts": fpts, "results": results}}

    def display(self, data=None, **kw):
        if type(self).fit_ok:
            self.peakFreq_min = FIT_MIN
            data["data"]["hanger_fit_min_freq_mhz"] = np.asarray(FIT_MIN)
            data["data"]["hanger_fit_f0_mhz"] = np.asarray(FIT_MIN - 0.2)  # f0 != curve minimum
            data["data"]["hanger_fit_popt"] = np.asarray(FAKE_POPT)
        else:
            print("Hanger fit failed: synthetic")

    def save_data(self, data=None):
        pass

    def save_config(self):
        pass


class _Ctx:
    working_config = Context.working_config

    def __init__(self, cavity_min=True):
        self.config = {"pulse_freq": CENTER, "reps": 10}
        self.cavity_min = cavity_min
        self.resonator_frequency_center = CENTER
        self.outerFolder = "unused/"
        self.soc = self.soccfg = None


@pytest.fixture
def fake(monkeypatch):
    _FakeTrans.instances, _FakeTrans.fit_ok, _FakeTrans.kind = [], True, "dip"
    monkeypatch.setattr(res_runs, "CavitySpecFF", _FakeTrans)
    return _FakeTrans


PARAMS = {"reps": 20, "rounds": 1}


@pytest.mark.parametrize("run", ["fit", "sweep"])
def test_carries_display_fit_minimum(fake, run, capsys):
    ctx = _Ctx()
    getattr(res_runs, f"run_transmission_{run}")(ctx, PARAMS)
    assert ctx.config["pulse_freq"] == FIT_MIN
    assert "WARNING" not in capsys.readouterr().out


@pytest.mark.parametrize("run", ["fit", "sweep"])
def test_failed_fit_falls_back_to_raw_argmin_with_warning(fake, run, capsys):
    fake.fit_ok = False
    ctx = _Ctx()
    getattr(res_runs, f"run_transmission_{run}")(ctx, PARAMS)
    assert ctx.config["pulse_freq"] == RAW_MIN
    out = capsys.readouterr().out
    assert "WARNING" in out and "RAW" in out


def test_sweep_peak_mode_keeps_raw_argmax(fake):
    fake.kind = "peak"
    ctx = _Ctx(cavity_min=False)
    res_runs.run_transmission_sweep(ctx, PARAMS)
    assert ctx.config["pulse_freq"] == RAW_MAX


def test_fit_step_does_not_refit(fake, monkeypatch):
    """The step must not run its own hanger fit (old start asym=1e3 was ~1e6 too large in MHz)."""

    def _boom(*a, **k):
        raise AssertionError("run_transmission_fit refit the trace")

    monkeypatch.setattr(res_runs, "fit_hanger_transmission", _boom, raising=False)
    res_runs.run_transmission_fit(_Ctx(), PARAMS)


# --- end to end with the real CavitySpecFF.display on a synthetic hanger ----------------------
# Over-coupled dip (Qi=3e5, Qc=5e3, f0/Qtot ~ 1.44 MHz) where the removed step fit (start
# asym=1e3) ran to the sweep edge (7100 MHz, 4 linewidths off); the display fit lands on f0.
TRUE_F0, QI, QC, SEED = 7094.2, 3e5, 5e3, 1


class _SyntheticCavitySpec(CavitySpecFF):
    """Real display(); acquire returns a noisy synthetic hanger dip, nothing touches disk."""

    def __init__(self, path=None, cfg=None, soc=None, soccfg=None, outerFolder=None):
        self.cfg = cfg
        self.iname = str(_SyntheticCavitySpec.tmp / "trans.png")

    def acquire(self):
        f0, qi, qc = TRUE_F0, QI, QC
        qtot = 1 / (1 / qi + 1 / qc)
        fpts = np.linspace(CENTER - 5, CENTER + 5, 201)
        s21 = 1 - (qtot / qc) / (1 + 2j * qtot * (fpts - f0) / f0)
        rng = np.random.default_rng(SEED)
        s21 = (
            0.01 * np.exp(0.7j) * (s21 + 0.01 * (rng.normal(size=201) + 1j * rng.normal(size=201)))
        )
        results = np.array([[[s21.real, s21.imag]]])
        self.peakFreq_min = fpts[np.argmin(np.abs(s21))]
        self.peakFreq_max = fpts[np.argmax(np.abs(s21))]
        self.data = {"config": self.cfg, "data": {"results": results, "fpts": fpts}}
        return self.data

    def save_data(self, data=None):
        pass

    def save_config(self):
        pass


def test_real_display_fit_lands_within_a_linewidth(monkeypatch, tmp_path):
    _SyntheticCavitySpec.tmp = tmp_path
    monkeypatch.setattr(res_runs, "CavitySpecFF", _SyntheticCavitySpec)
    ctx = _Ctx()
    ctx.config["cavity_LO"] = 0
    res_runs.run_transmission_fit(ctx, PARAMS)
    linewidth = TRUE_F0 * (1 / QI + 1 / QC)  # f0/Qtot
    assert abs(ctx.config["pulse_freq"] - TRUE_F0) < 0.1 * linewidth


# --- F52: the carry-over gate ----------------------------------------------------------------
PREVIOUS = 7095.25  # an earlier good carry-over that a rejected trace must not overwrite


@pytest.mark.parametrize("run", ["fit", "sweep"])
@pytest.mark.parametrize("fit_ok", [True, False], ids=["display_fit", "raw_argmin"])
def test_noise_trace_leaves_pulse_freq_unchanged(fake, run, fit_ok, capsys):
    fake.kind, fake.fit_ok = "noise", fit_ok
    ctx = _Ctx()
    ctx.config["pulse_freq"] = PREVIOUS
    getattr(res_runs, f"run_transmission_{run}")(ctx, PARAMS)
    assert ctx.config["pulse_freq"] == PREVIOUS
    out = capsys.readouterr().out
    assert "carry-over gate" in out and "depth_sigmas=" in out and "NOT updated" in out


def test_sweep_peak_mode_rejects_noise(fake):
    fake.kind = "noise"
    ctx = _Ctx(cavity_min=False)
    ctx.config["pulse_freq"] = PREVIOUS
    res_runs.run_transmission_sweep(ctx, PARAMS)
    assert ctx.config["pulse_freq"] == PREVIOUS


def test_sweep_peak_mode_does_not_use_the_dip_fit(fake, monkeypatch):
    """The display fit always fits a dip: a peak must be judged without its popt."""

    def _boom(*a, **k):
        raise AssertionError("peak judged by the hanger (dip) fit")

    fake.kind = "peak"
    monkeypatch.setattr(res_runs, "assess_resonator_fit", _boom)
    ctx = _Ctx(cavity_min=False)
    res_runs.run_transmission_sweep(ctx, PARAMS)
    assert ctx.config["pulse_freq"] == RAW_MAX


def test_gate_exception_is_a_failed_gate(fake, monkeypatch, capsys):
    def _raise(*a, **k):
        raise ValueError("synthetic")

    monkeypatch.setattr(res_runs, "assess_resonator_fit", _raise)
    ctx = _Ctx()
    ctx.config["pulse_freq"] = PREVIOUS
    res_runs.run_transmission_fit(ctx, PARAMS)
    assert ctx.config["pulse_freq"] == PREVIOUS
    assert "gate raised ValueError('synthetic')" in capsys.readouterr().out


class _SyntheticNoiseSpec(_SyntheticCavitySpec):
    """Real display() on a resonator-free trace: flat -35 dB plus 0.3 dB noise."""

    def acquire(self):
        fpts, results = _fake_trace("noise", seed=_SyntheticNoiseSpec.seed)
        self.peakFreq_min = fpts[np.argmin(results[0, 0, 0])]
        self.peakFreq_max = fpts[np.argmax(results[0, 0, 0])]
        self.data = {"config": self.cfg, "data": {"results": results, "fpts": fpts}}
        return self.data


@pytest.mark.parametrize("seed", range(6))
def test_real_display_fit_on_noise_is_not_carried(monkeypatch, tmp_path, seed):
    _SyntheticNoiseSpec.tmp, _SyntheticNoiseSpec.seed = tmp_path, seed
    monkeypatch.setattr(res_runs, "CavitySpecFF", _SyntheticNoiseSpec)
    ctx = _Ctx()
    ctx.config["cavity_LO"] = 0
    res_runs.run_transmission_fit(ctx, PARAMS)
    assert ctx.config["pulse_freq"] == CENTER
