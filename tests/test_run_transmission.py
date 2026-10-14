"""Hardware-free tests for the transmission carry-over (F03).

run_transmission_fit / run_transmission_sweep must carry display()'s hanger-fit minimum
(``hanger_fit_min_freq_mhz``) into ctx.config['pulse_freq'], fall back to the raw argmin with a
printed warning when that fit failed, and (sweep, cavity_min=False) keep the raw argmax. See
docs/architecture.md#carry-overs and docs/experiments/transmission_fit.md.

    python -m pytest tests/test_run_transmission.py
"""

import matplotlib

matplotlib.use("Agg")

import numpy as np
import pytest

import qicklab.runs.resonator as res_runs
from qicklab.core.context import Context
from qicklab.experiments.transmission import CavitySpecFF

CENTER = 7095.0
FIT_MIN = 7095.3989
RAW_MIN = 7095.35
RAW_MAX = 7091.0


class _FakeTrans:
    """Stands in for CavitySpecFF: acquire sets peakFreq_min/max, display optionally 'fits'."""

    instances = []
    fit_ok = True

    def __init__(self, path=None, cfg=None, soc=None, soccfg=None, outerFolder=None):
        self.cfg = cfg
        type(self).instances.append(self)

    def acquire(self):
        self.peakFreq_min, self.peakFreq_max = RAW_MIN, RAW_MAX
        return {"config": self.cfg, "data": {"fpts": np.zeros(3), "results": np.zeros(3)}}

    def display(self, data=None, **kw):
        if type(self).fit_ok:
            self.peakFreq_min = FIT_MIN
            data["data"]["hanger_fit_min_freq_mhz"] = np.asarray(FIT_MIN)
            data["data"]["hanger_fit_f0_mhz"] = np.asarray(FIT_MIN - 0.2)  # f0 != curve minimum
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
    _FakeTrans.instances, _FakeTrans.fit_ok = [], True
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
