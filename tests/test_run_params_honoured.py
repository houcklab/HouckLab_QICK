"""Hardware-free guard (F84): run_* steps hand the experiment the values from their params dict.

Each run is called with a fake ctx and a fake experiment class; the test reads the cfg the
experiment was constructed with and the display kwargs passed to finish(), never the reads on
the params dict (Spec_relevant_params is shared across steps).

    python -m pytest tests/test_run_params_honoured.py
"""

import pytest

import qicklab.runs.rabi as rabi_runs
import qicklab.runs.resonator as res_runs
import qicklab.runs.spectroscopy as spec_runs

# the regime-A keys these runs fall back to: BASE_CONFIG relax_delay, spec-group qubit_gain
BASE = {"relax_delay": 3000, "qubit_gain": 1000, "pulse_freq": 7095.0, "reps": 1000}


class _Ctx:
    soc = soccfg = None
    outerFolder = "unused"
    qubit_frequency_center = 4000.0
    qubit_sigma = 0.05
    qubit_flattop = None
    Qubit_Pulse = 1
    cavity_min = True

    def __init__(self, **kw):
        self.config = dict(BASE)
        self.__dict__.update(kw)

    def working_config(self, *updates):
        cfg = dict(self.config)
        for u in updates:
            if u:
                cfg.update(u)
        return cfg


def _fake_class(name):
    """An experiment stand-in that records a copy of the cfg it was built with."""

    class Fake:
        built = []

        def __init__(self, path=None, cfg=None, soc=None, soccfg=None, outerFolder=None):
            type(self).built.append(dict(cfg))

        def acquire(self):
            return {"data": {}}

    Fake.__name__ = name
    return Fake


@pytest.fixture
def finished(monkeypatch):
    """Replace finish() in every run module; collect the display kwargs it was called with."""
    calls = []

    def fake_finish(cls, inst, data, *, reraise=False, **display_kw):
        calls.append(display_kw)

    for mod in (rabi_runs, res_runs, spec_runs):
        monkeypatch.setattr(mod, "finish", fake_finish)
    return calls


SPEC = {
    "qubit_gain": 1000,
    "SpecSpan": 10,
    "SpecNumPoints": 201,
    "qubit_length": 50,
    "reps": 7,
    "rounds": 3,
    "Gauss": False,
    "sigma": 2,
    "gain": 800,
    "relax_delay": 2500,
    "display": False,
    "min_sep_MHz": 0.2,
    "fit_window_mhz": 0.3,
    "prominent_ratio": 0.25,
    "sweep_lengths": [10],
    "sweep_gains": [200],
}


def test_transmission_sweep_uses_params_reps_rounds(monkeypatch, finished):
    fake = _fake_class("CavitySpecFF")
    monkeypatch.setattr(res_runs, "CavitySpecFF", fake)
    monkeypatch.setattr(res_runs, "_carry_if_resonator", lambda *a, **k: False)
    res_runs.run_transmission_sweep(_Ctx(), {"reps": 400, "rounds": 1, "span": 5})
    assert (fake.built[0]["reps"], fake.built[0]["rounds"]) == (400, 1)


@pytest.mark.parametrize("run", ["two_tone_spec", "spec_gain_length_sweep"])
def test_spec_display_knobs_come_from_params(monkeypatch, finished, run):
    monkeypatch.setattr(spec_runs, "QubitSpecSliceFF", _fake_class("QubitSpecSliceFF"))
    getattr(spec_runs, f"run_{run}")(_Ctx(), SPEC)
    assert finished[0]["fit_window_mhz"] == 0.3
    assert finished[0]["prominent_ratio"] == 0.25
    # absent keys keep the legacy defaults
    finished.clear()
    params = {k: v for k, v in SPEC.items() if k not in ("fit_window_mhz", "prominent_ratio")}
    getattr(spec_runs, f"run_{run}")(_Ctx(), params)
    assert (finished[0]["fit_window_mhz"], finished[0]["prominent_ratio"]) == (0.5, 0.1)


@pytest.mark.parametrize("gauss", [False, True])
def test_trans_qubit_spec_uses_spec_gain_and_relax_delay(monkeypatch, finished, gauss):
    fake = _fake_class("QubitSpecSliceFF")
    monkeypatch.setattr(spec_runs, "QubitSpecSliceFF", fake)
    spec_runs.run_trans_qubit_spec(_Ctx(), SPEC | {"Gauss": gauss}, {"repetitions": 2})
    assert len(fake.built) == 2
    for cfg in fake.built:
        assert cfg["qubit_gain"] == 800  # spec 'gain', not the base-config qubit_gain 1000
        assert cfg["relax_delay"] == 2500  # spec group, not BASE_CONFIG 3000
        assert (cfg["reps"], cfg["rounds"]) == (7, 3)
    assert finished[0]["fit_window_mhz"] == 0.3
    assert finished[0]["prominent_ratio"] == 0.25


RABI = {
    "qubit_freq": 4000.0,
    "max_gain": 10000,
    "number_of_steps": 101,
    "reps": 10,
    "rounds": 10,
    "relax_delay": 3000,
    "fit": False,
}


@pytest.mark.parametrize("extra, expected", [({}, 8000), ({"flattop_relax_delay": 5000}, 5000)])
def test_flattop_rabi_relax_delay(monkeypatch, finished, extra, expected):
    fake = _fake_class("AmplitudeRabiFF_N")
    monkeypatch.setattr(rabi_runs, "AmplitudeRabiFF_N", fake)
    rabi_runs.run_amplitude_rabi(_Ctx(qubit_flattop=1.0), RABI | extra)
    assert fake.built[0]["relax_delay"] == expected
    assert fake.built[0]["flattop_length"] == 1.0


def test_gaussian_rabi_relax_delay(monkeypatch, finished):
    fake = _fake_class("AmplitudeRabiFF")
    monkeypatch.setattr(rabi_runs, "AmplitudeRabiFF", fake)
    rabi_runs.run_amplitude_rabi(_Ctx(), RABI | {"flattop_relax_delay": 5000})
    assert fake.built[0]["relax_delay"] == 3000
