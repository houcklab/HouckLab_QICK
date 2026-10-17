"""Hardware-free tests for the interleaved validation controls of run_modified_ramsey (F15).

The controls in ``validation_controls`` must be acquired and saved on their cadence whether
or not ``parity_analysis_enabled`` is set; the flag only gates their online analysis. With
the analysis off, ``<base>_controls_index.json`` pairs them with the parent record. See
docs/experiments/modified_ramsey.md#validation-controls.

    python -m pytest tests/test_run_modified_ramsey_controls.py
"""

import json
import os
import types

import numpy as np
import pytest

import qicklab.runs.modified_ramsey as mr_runs
from qicklab.core.context import Context

N_SHOTS = 64


class _FakeMR:
    """Stands in for ModifiedRamsey: records path/cfg and which finish() steps ran."""

    instances = []

    def __init__(self, path=None, cfg=None, soc=None, soccfg=None, outerFolder=None):
        self.path, self.cfg = path, cfg
        n = len(type(self).instances)
        self.fname = os.path.join(outerFolder, path, f"{path}_{n:02d}_data.h5")
        self.calls = []
        type(self).instances.append(self)

    def acquire(self):
        self.calls.append("acquire")
        rng = np.random.default_rng(len(type(self).instances))
        return {
            "config": self.cfg,
            "data": {
                "shots_i": rng.normal(size=N_SHOTS),
                "shots_q": rng.normal(size=N_SHOTS),
                "scheduled_rep_period_us": 20.0,
            },
        }

    def display(self, data, **kwargs):
        self.calls.append("display")

    def save_data(self, data):
        self.calls.append("save_data")

    def save_config(self):
        self.calls.append("save_config")


class _Ctx:
    """Minimal Context: just the attributes run_modified_ramsey uses."""

    working_config = Context.working_config

    def __init__(self, outer, sigma):
        self.config = {"reps": 10}
        self.outerFolder = outer
        self.qubit_frequency_center = 4186.7
        self.yoko = types.SimpleNamespace(query=lambda cmd: "0.125")
        self.pi2_gain = 2000
        self.qubit_gain = 4000
        self.qubit_sigma = sigma
        self.qubit_flattop = None
        self.Qubit_Readout = [2]
        self.Qubit_Pulse = 2
        self.soc = None
        self.soccfg = None


def _analysis_result():
    return {
        "summary": {
            "identifiable": False,
            "gamma01_hz": float("nan"),
            "gamma10_hz": float("nan"),
            "warnings": [],
            "occupancy_state1": 0.5,
        },
        "hmm": {},
        "acf": {},
    }


@pytest.fixture
def fakes(monkeypatch):
    _FakeMR.instances = []
    calls = {"analyze": [], "analyze_kwargs": [], "compare": [], "compare_controls": []}

    def analyze(*args, **kwargs):
        calls["analyze"].append(kwargs["base_name"])
        calls["analyze_kwargs"].append(kwargs)
        return _analysis_result()

    def compare(parity, controls):
        calls["compare"].append([c["control_type"] for c in controls])
        calls["compare_controls"].append([dict(c) for c in controls])
        return {"all_expected": True}

    sep = {"data_ss": None, "g_center": np.array([-1.0, 0.0]), "e_center": np.array([1.0, 0.0])}
    monkeypatch.setattr(mr_runs, "ModifiedRamsey", _FakeMR)
    monkeypatch.setattr(
        mr_runs, "modified_ramsey_timing", lambda soccfg, cfg: {"scheduled_rep_period_us": 20.0}
    )
    monkeypatch.setattr(mr_runs, "get_apriori_separator_from_singleshot", lambda ctx, **k: sep)
    monkeypatch.setattr(
        mr_runs, "_extract_iq_from_singleshot_data", lambda d, s: (np.zeros(4), np.zeros(4))
    )
    monkeypatch.setattr(mr_runs, "calibrate_readout_from_labeled_shots", lambda *a: object())
    monkeypatch.setattr(mr_runs, "analyze_modified_ramsey_record", analyze)
    monkeypatch.setattr(mr_runs, "compare_parity_controls", compare)
    monkeypatch.setattr(mr_runs.plt, "savefig", lambda *a, **k: None)
    monkeypatch.setattr(mr_runs, "save_record", lambda *a, **k: None)
    monkeypatch.setattr(mr_runs, "save_cycle_summary", lambda *a, **k: None)
    return calls


def _params(**overrides):
    params = {
        "df": 2.7,
        "f_ge": 4186.7,
        "tau_harmonic_k": 1,
        "symmetric_ramsey": True,
        "max_drive_bandwidth_ratio": 1.4,
        "mr_reps": N_SHOTS,
        "num_cycles": 1,
        "use_apriori_separator": True,
        "average_n_shots": 8,
        "parity_analysis_enabled": False,
        "validation_controls": ["flip_final_pi2", "echo_null"],
        "validation_controls_every_n_cycles": 10,
    }
    params.update(overrides)
    return params


def _index_files(outer):
    root = os.path.join(outer, "ModifiedRamsey")
    return sorted(
        os.path.join(d, f) for d, _, fs in os.walk(root) for f in fs if f.endswith("_index.json")
    )


def _comparison_files(outer):
    root = os.path.join(outer, "ModifiedRamsey")
    return [f for _, _, fs in os.walk(root) for f in fs if f.endswith("_control_comparison.json")]


def test_controls_acquired_with_analysis_off(fakes, tmp_path, capsys):
    outer = str(tmp_path) + "/"
    mr_runs.run_modified_ramsey(_Ctx(outer, sigma=0.01), _params())

    parent, *controls = _FakeMR.instances
    assert parent.path == "ModifiedRamsey"
    assert [c.path for c in controls] == ["ModifiedRamsey_Controls"] * 2
    assert [c.cfg["mr_control_type"] for c in controls] == ["flip_final_pi2", "echo_null"]
    for c in controls:
        # acquired and saved through finish(): display, then h5 + json
        assert c.calls == ["acquire", "display", "save_data", "save_config"]
        assert c.cfg["mr_parent_record"] == parent.fname
        assert c.cfg["mr_parent_cycle_idx"] == 0
    assert controls[0].cfg["flip_final_pi2"] is True
    assert controls[1].cfg["use_pi_pulse"] is True
    # nothing analysed, no comparison
    assert fakes["analyze"] == [] and fakes["compare"] == []
    assert _comparison_files(outer) == []

    (index_path,) = _index_files(outer)
    assert os.path.basename(index_path).startswith("Cycle_000_MR_")
    with open(index_path) as f:
        index = json.load(f)
    assert index == {
        "cycle_idx": 0,
        "parent_record": parent.fname,
        "controls": {"flip_final_pi2": controls[0].fname, "echo_null": controls[1].fname},
        "skipped": [],
    }
    assert "parity_analysis_enabled=False" in capsys.readouterr().out


def test_controls_analysed_with_analysis_on(fakes, tmp_path):
    outer = str(tmp_path) + "/"
    mr_runs.run_modified_ramsey(_Ctx(outer, sigma=0.01), _params(parity_analysis_enabled=True))
    parent, *controls = _FakeMR.instances
    assert [c.cfg["mr_control_type"] for c in controls] == ["flip_final_pi2", "echo_null"]
    assert [b.rsplit("_", 1)[-1] for b in fakes["analyze"]] == [
        "continuous",
        "pi2",  # ..._flip_final_pi2
        "null",  # ..._echo_null
    ]
    assert fakes["compare"] == [["flip_final_pi2", "echo_null"]]
    assert len(_comparison_files(outer)) == 1
    assert _index_files(outer) == []


def test_cadence_independent_of_analysis(fakes, tmp_path):
    outer = str(tmp_path) + "/"
    mr_runs.run_modified_ramsey(
        _Ctx(outer, sigma=0.01),
        _params(num_cycles=3, validation_controls_every_n_cycles=2),
    )
    controls = [c for c in _FakeMR.instances if c.path == "ModifiedRamsey_Controls"]
    assert [c.cfg["mr_parent_cycle_idx"] for c in controls] == [0, 0, 2, 2]
    assert [os.path.basename(p)[:9] for p in _index_files(outer)] == ["Cycle_000", "Cycle_002"]


@pytest.mark.parametrize("analysis", [False, True])
def test_nonpositive_cadence_raises(fakes, tmp_path, analysis):
    with pytest.raises(ValueError, match="validation_controls_every_n_cycles"):
        mr_runs.run_modified_ramsey(
            _Ctx(str(tmp_path) + "/", sigma=0.01),
            _params(parity_analysis_enabled=analysis, validation_controls_every_n_cycles=0),
        )


def test_infeasible_control_skipped_and_recorded(fakes, tmp_path, capsys):
    # sigma = 30 ns at df = 2.7 MHz, k = 1: the echo pulses do not fit in tau
    outer = str(tmp_path) + "/"
    mr_runs.run_modified_ramsey(_Ctx(outer, sigma=0.03), _params(validation_controls=["echo_null"]))
    assert [c.path for c in _FakeMR.instances] == ["ModifiedRamsey"]
    (index_path,) = _index_files(outer)
    with open(index_path) as f:
        index = json.load(f)
    assert index["controls"] == {}
    assert [s["control_type"] for s in index["skipped"]] == ["echo_null"]
    assert "need df <" in index["skipped"][0]["reason"]
    assert "every validation control was skipped" in capsys.readouterr().out


@pytest.mark.parametrize(
    "sigma, k, echo_valid",
    [
        # df 2.7 MHz, symmetric: the finite-pulse echo keeps 0.641 against 0.732 -> not a null
        (0.1, 5, False),
        # short pulses: echo 0.063 against 0.960 -> a valid null
        (0.04, 3, True),
    ],
)
def test_echo_null_validity_reaches_comparison(fakes, tmp_path, sigma, k, echo_valid):
    # F31: the run must hand build_control_variants' null_control_valid / null_invalid_reason
    # to compare_parity_controls, or a non-null echo would be judged as a null.
    outer = str(tmp_path) + "/"
    mr_runs.run_modified_ramsey(
        _Ctx(outer, sigma=sigma), _params(parity_analysis_enabled=True, tau_harmonic_k=k)
    )
    ((flip, echo),) = fakes["compare_controls"]
    assert flip["control_type"] == "flip_final_pi2"
    assert flip["null_control_valid"] is None and flip["null_invalid_reason"] == ""
    assert echo["control_type"] == "echo_null"
    assert echo["null_control_valid"] is echo_valid
    if echo_valid:
        assert echo["null_invalid_reason"] == ""
    else:
        assert echo["null_invalid_reason"].startswith("not a null at these settings")
    # the same verdict travels in the saved control cfg
    echo_cfg = [c for c in _FakeMR.instances if c.path == "ModifiedRamsey_Controls"][1].cfg
    assert echo_cfg["mr_null_control_valid"] is echo_valid


def test_tau_offset_and_drive_detuned_predictions_reach_comparison(fakes, tmp_path):
    # F39: with no control_tau_offset_frac the run builds the even-harmonic tau null from the
    # programmed k, and hands null_control_valid / inverted_mapping_expected to the comparison.
    outer = str(tmp_path) + "/"
    params = _params(
        parity_analysis_enabled=True,
        tau_harmonic_k=3,
        symmetric_ramsey=False,
        validation_controls=["tau_offset", "drive_detuned"],
    )
    mr_runs.run_modified_ramsey(_Ctx(outer, sigma=0.04), params)
    ((tau, det),) = fakes["compare_controls"]
    assert tau["control_type"] == "tau_offset" and tau["null_control_valid"] is True
    assert tau["inverted_mapping_expected"] is None
    assert det["control_type"] == "drive_detuned" and det["inverted_mapping_expected"] is True
    assert det["inverted_mapping_reason"] == ""  # no active reset: no reset-pi gate
    assert det["null_control_valid"] is None
    tau_cfg = [c for c in _FakeMR.instances if c.path == "ModifiedRamsey_Controls"][0].cfg
    assert abs(tau_cfg["ramsey_tau_us"] - 4 / (2 * 2.7)) < 1e-12


@pytest.mark.parametrize(
    "overrides, fitted, seeded, source",
    [
        # default: fit the mapping, seeded from the prediction
        ({}, True, True, "predicted"),
        # fixed at mapping_p_e_state0/1
        ({"hmm_fit_mapping": False}, False, False, "assumed"),
        # the hmm_kwargs escape hatch turns the fit off the same way: the idealised
        # prediction must never become the FIXED mapping the emission gate trusts
        ({"hmm_kwargs": {"fit_mapping": False}}, False, False, "assumed"),
        # and turns it on even with hmm_fit_mapping=False
        ({"hmm_fit_mapping": False, "hmm_kwargs": {"fit_mapping": True}}, True, True, "predicted"),
        # seeded at the calibration
        ({"mapping_probabilities_calibrated": True}, True, False, "calibrated"),
    ],
)
def test_mapping_fit_seed_reaches_analysis(fakes, tmp_path, overrides, fitted, seeded, source):
    # F30: the parity record and its controls are analysed with fit_mapping and one seed, the
    # predicted mapping of the parity sequence (ascending: state1 = the larger P(e)).
    from qicklab.experiments.modified_ramsey import predicted_mapping_seed

    outer = str(tmp_path) + "/"
    params = _params(
        parity_analysis_enabled=True,
        tau_harmonic_k=3,
        symmetric_ramsey=False,
        mapping_p_e_state0=0.2,
        mapping_p_e_state1=0.7,
        **overrides,
    )
    mr_runs.run_modified_ramsey(_Ctx(outer, sigma=0.04), params)
    parent = _FakeMR.instances[0]
    p0, p1, src = predicted_mapping_seed(parent.cfg, fallback=(0.2, 0.7))
    assert src == "predicted" and p0 < p1
    expected = (p0, p1) if seeded else (0.2, 0.7)
    assert len(fakes["analyze_kwargs"]) == 3  # parity + flip + echo
    for kw in fakes["analyze_kwargs"]:
        assert kw["fit_mapping"] is fitted
        assert tuple(kw["mapping_probabilities"]) == pytest.approx(expected)
        assert kw["mapping_seed_source"] == source
