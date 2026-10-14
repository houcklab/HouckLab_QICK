"""Hardware-free tests for qicklab.core.experiment.finish (display never loses the record).

A display that raises (fit on noise) or is interrupted must still leave the h5 + json on disk,
repetition loops must continue, and AutoCoherence must write its summary on every exit.
See docs/architecture.md#display-never-loses-the-record.

    python -m pytest tests/test_finish.py
"""

import json
import os

import h5py
import numpy as np
import pytest

from qicklab.core.experiment import ExperimentClass, finish


class _Expt(ExperimentClass):
    """Records the call order; display raises whatever `boom` holds."""

    boom = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls = []

    def display(self, data=None, **kwargs):
        self.calls.append(("display", kwargs))
        data["data"]["fit_partial"] = [1.0]  # displays may write fit fields into data
        if self.boom is not None:
            raise self.boom

    def save_data(self, data=None):
        self.calls.append(("save_data", None))
        # like T1FF / T2EMUX: rename fname, so save_config must run after save_data
        self.fname = self.fname[:-3] + "_Q1.h5"
        with self.datafile() as f:
            for k, d in data["data"].items():
                f.add(k, np.array(d))

    def save_config(self):
        self.calls.append(("save_config", None))
        super().save_config()


def _make(tmp_path, boom=None):
    inst = _Expt(path="Fin", outerFolder=str(tmp_path) + "/", cfg={"reps": 3})
    inst.boom = boom
    return inst, {"data": {"x_pts": [0.0, 1.0, 2.0]}}


def _assert_saved(inst):
    assert os.path.exists(inst.fname) and inst.fname.endswith("_Q1.h5")
    assert os.path.exists(inst.cname)
    with open(inst.cname) as fh:
        assert json.load(fh) == {"reps": 3}
    with h5py.File(inst.fname, "r") as f:
        assert list(f["x_pts"][()]) == [0.0, 1.0, 2.0]
        assert json.loads(f.attrs["config"]) == {"reps": 3}


def test_display_ok_order_and_kwargs(tmp_path):
    inst, data = _make(tmp_path)
    assert finish(_Expt, inst, data, plotDisp=False, figNum=7) is None
    assert inst.calls == [
        ("display", {"plotDisp": False, "figNum": 7}),
        ("save_data", None),
        ("save_config", None),
    ]
    assert not hasattr(inst, "display_error")
    _assert_saved(inst)
    with h5py.File(inst.fname, "r") as f:
        assert "fit_partial" in f  # fields display writes into data are saved


def test_display_raises_record_still_saved(tmp_path, capsys):
    inst, data = _make(tmp_path, ValueError("Initial guess is outside of provided bounds"))
    err = finish(_Expt, inst, data, plotDisp=False)  # loop default: no re-raise
    assert isinstance(err, ValueError)
    assert inst.display_error == repr(err)
    assert [c[0] for c in inst.calls] == ["display", "save_data", "save_config"]
    _assert_saved(inst)
    assert "Initial guess is outside" in capsys.readouterr().err  # traceback printed


def test_reraise_after_saving(tmp_path):
    inst, data = _make(tmp_path, RuntimeError("fit failed"))
    with pytest.raises(RuntimeError, match="fit failed"):
        finish(_Expt, inst, data, reraise=True)
    assert inst.display_error == "RuntimeError('fit failed')"
    _assert_saved(inst)


def test_interrupt_in_display_still_saves_and_propagates(tmp_path):
    # Ctrl-C while a blocking plot window is open: save, then let the interrupt through
    inst, data = _make(tmp_path, KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        finish(_Expt, inst, data)
    assert not hasattr(inst, "display_error")
    _assert_saved(inst)


def test_explicit_class_is_used(tmp_path):
    class Child(_Expt):
        def display(self, data=None, **kwargs):
            raise AssertionError("child display must not run")

    inst = Child(path="Fin", outerFolder=str(tmp_path) + "/", cfg={"reps": 3})
    finish(_Expt, inst, {"data": {"x_pts": [0.0, 1.0, 2.0]}})
    assert [c[0] for c in inst.calls] == ["display", "save_data", "save_config"]


def test_run_t2_loop_continues_after_display_error(tmp_path, monkeypatch):
    """The F02 case: T2R.display raising on noise must not lose the record or stop the loop."""
    import qicklab.runs.coherence as coherence

    made = []

    class FakeT2R(_Expt):
        def __init__(self, *args, **kwargs):
            # the real loop sleeps 10 s between runs; distinct prefixes stand in for that
            super().__init__(*args, prefix=f"data{len(made)}", **kwargs)
            self.boom = ValueError("Initial guess is outside of provided bounds")
            made.append(self)

        def acquire(self):
            return {"data": {"x_pts": [0.0, 1.0, 2.0]}}

    class Ctx:
        outerFolder = str(tmp_path) + "/"
        soc = type("Soc", (), {"reset_gens": lambda self: None})()
        soccfg = type("SocCfg", (), {"deg2reg": lambda self, deg, gen_ch: 0})()
        qubit_gain = pi2_gain = 1000
        qubit_frequency_center = 4000.0
        qubit_sigma = 0.05
        qubit_flattop = None

        def working_config(self, extra):
            return {"reps": 3}

    monkeypatch.setattr(coherence, "T2R", FakeT2R)
    monkeypatch.setattr(coherence.time, "sleep", lambda s: None)
    params = {
        "repetitions": 2,
        "T2_step": 0.1,
        "T2_expts": 3,
        "T2_reps": 1,
        "T2_rounds": 1,
        "relax_delay": 100,
        "freq_shift": 0.0,
    }
    coherence.run_t2(Ctx(), params)
    assert len(made) == 2
    for inst in made:
        assert inst.display_error.startswith("ValueError(")
        assert os.path.exists(inst.fname) and os.path.exists(inst.cname)


def _run_auto(tmp_path, monkeypatch, fail_stage=None):
    import qicklab.runs.auto_coherence as ac

    ran = []

    def stage(name, ret=None):
        def fn(**kwargs):
            ran.append(name)
            if name == fail_stage:
                raise RuntimeError(f"{name} blew up")
            return ret

        return fn

    monkeypatch.setattr(ac, "_stage_amplitude_rabi", stage("rabi", (1200, 0.05)))
    monkeypatch.setattr(ac, "_stage_singleshot_optimize", stage("ss", (1210, 605, 0.91, 12.5, 0.3)))
    monkeypatch.setattr(ac, "_stage_run_t1", stage("T1"))
    monkeypatch.setattr(ac, "_stage_run_t2", stage("T2"))
    monkeypatch.setattr(ac, "_stage_run_t2e", stage("T2E"))
    qubit_params = {
        "1": {
            "Readout": {"Frequency": 7000.0, "Gain": 800},
            "Qubit": {"Frequency": 4000.0, "Gain": 1000, "sigma": 0.05, "flattop_length": None},
        }
    }
    auto_params = {
        "skip_sweet_spot_search": True,
        "calibrate_qubit_freq": False,
        "auto_readout_opt": False,
    }
    call = dict(
        soc=None,
        soccfg=None,
        config={},
        outerFolder=str(tmp_path) + "/",
        qubit_readout=1,
        qubit_params=qubit_params,
        yoko=None,
        auto_params=auto_params,
    )
    return ac, ran, call


def _summary(tmp_path):
    run_dirs = os.listdir(os.path.join(tmp_path, "AutoCoherence"))
    assert len(run_dirs) == 1
    folder = os.path.join(tmp_path, "AutoCoherence", run_dirs[0])
    (js,) = [f for f in os.listdir(folder) if f.endswith(".json")]
    (txt,) = [f for f in os.listdir(folder) if f.endswith(".txt")]
    with open(os.path.join(folder, js)) as fh, open(os.path.join(folder, txt)) as ft:
        return json.load(fh), ft.read()


def test_auto_coherence_summary_survives_stage_failure(tmp_path, monkeypatch):
    ac, ran, call = _run_auto(tmp_path, monkeypatch, fail_stage="T2")
    with pytest.raises(RuntimeError, match="T2 blew up"):
        ac._run_auto_coherence(**call)
    assert ran == ["rabi", "ss", "T1", "T2"]
    summary, text = _summary(tmp_path)
    assert summary["stage_reached"] == "T1"
    assert summary["error"] == "RuntimeError('T2 blew up')"
    cal = summary["calibration"]
    assert (cal["pi_gain"], cal["pi2_gain"], cal["ss_threshold"], cal["ss_angle"]) == (
        1210,
        605,
        12.5,
        0.3,
    )
    assert cal["qubit_frequency"] == 4000.0 and cal["rabi_sigma"] == 0.05
    assert "Run aborted after stage 'T1'" in text


def test_auto_coherence_partial_calibration_saved(tmp_path, monkeypatch):
    ac, ran, call = _run_auto(tmp_path, monkeypatch, fail_stage="ss")
    with pytest.raises(RuntimeError):
        ac._run_auto_coherence(**call)
    summary, _ = _summary(tmp_path)
    assert summary["stage_reached"] == "optimize_readout"
    # the Rabi estimate is kept even though Stage 3 never finished
    assert summary["calibration"]["pi_gain"] == 1200
    assert summary["calibration"]["rabi_sigma"] == 0.05


def test_auto_coherence_complete(tmp_path, monkeypatch):
    ac, ran, call = _run_auto(tmp_path, monkeypatch)
    results = ac._run_auto_coherence(**call)
    assert ran == ["rabi", "ss", "T1", "T2", "T2E"]
    summary, text = _summary(tmp_path)
    assert summary["stage_reached"] == "complete" and summary["error"] is None
    assert list(summary["calibration"]) == [
        "qubit_frequency",
        "pi_gain",
        "pi2_gain",
        "rabi_sigma",
        "flattop_length",
        "fidelity",
        "ss_threshold",
        "ss_angle",
        "sweet_spot_voltage",
    ]
    assert results["summary_file"].endswith(".txt") and "Run completed" in text


_STAGE_CASES = {
    # tag: (stage function, class it instantiates, extra stage kwargs, stage params)
    "T1": ("_stage_run_t1", "T1FF", {}, {"T1_repetitions": 2, "T1_step": 1.0, "T1_expts": 3,
                                         "T1_reps": 1, "T1_rounds": 1, "T1_relax_delay": 100}),
    "T2": ("_stage_run_t2", "T2R", {"pi2_gain": 600},
           {"T2_repetitions": 2, "T2_freq_shift": 0.0, "T2_step": 0.1, "T2_expts": 3,
            "T2_reps": 1, "T2_rounds": 1, "T2_relax_delay": 100}),
    "T2E": ("_stage_run_t2e", "T2EMUX", {"pi2_gain": 600},
            {"T2E_repetitions": 2, "T2E_num_pi_pulses": 1, "T2E_max_us": 30.0, "T2E_expts": 3,
             "T2E_reps": 1, "T2E_rounds": 1, "T2E_relax_delay": 100}),
}  # fmt: skip


@pytest.mark.parametrize("tag", list(_STAGE_CASES))
def test_auto_coherence_stage_loop_continues_after_display_error(tmp_path, monkeypatch, tag):
    """Real AutoCoherence T1/T2/T2E stage loops: a raising display saves the record, logs
    'display failed (record saved)' and the next repetition still runs."""
    import qicklab.runs.auto_coherence as ac

    stage_name, cls_name, extra, params = _STAGE_CASES[tag]
    made = []

    class Fake(_Expt):
        def __init__(self, *args, soc=None, soccfg=None, **kwargs):
            super().__init__(*args, prefix=f"data{len(made)}", **kwargs)
            self.boom = ValueError("Initial guess is outside of provided bounds")
            made.append(self)

        def acquire(self):
            return {"data": {"x_pts": [0.0, 1.0, 2.0]}}

    resets = []
    soc = type("Soc", (), {"reset_gens": lambda self: resets.append(1)})()
    soccfg = type("SocCfg", (), {"deg2reg": lambda self, deg, gen_ch: 0})()
    monkeypatch.setattr(ac, cls_name, Fake)
    monkeypatch.setattr(ac.time, "sleep", lambda s: None)

    log = []
    getattr(ac, stage_name)(
        soc=soc,
        soccfg=soccfg,
        cfg={"reps": 3},
        auto_folder=str(tmp_path) + "/",
        qubit_freq=4000.0,
        pi_gain=1200,
        sigma=0.05,
        flattop_length=None,
        qubit_readout=1,
        params=params,
        log=log,
        **extra,
    )
    assert len(made) == 2 and len(resets) == 2  # loop went on to the second repetition
    for inst in made:
        assert inst.display_error.startswith("ValueError(")
        assert os.path.exists(inst.fname) and os.path.exists(inst.cname)
    assert f"  {tag} run 2/2 saved." in log
    failed = [line for line in log if "display failed (record saved)" in line]
    assert len(failed) == 2 and "Initial guess is outside" in failed[0]


# Run functions that acquire without a display (nothing can fail between acquire and save),
# so they may call save_data/save_config directly. Every other site must go through finish().
_DIRECT_SAVE_ALLOWED = {
    ("auto_coherence.py", "_acquire_spec"),
    ("modified_ramsey.py", "run_modified_ramsey"),
    ("zero_span.py", "run_zero_span_parity"),
}


def test_run_modules_save_through_finish():
    """Guard: no qicklab/runs module calls .display() itself (it would lose the record when the
    fit raises), and direct save_data/save_config calls only appear in the display-less sites."""
    import ast
    import pathlib

    import qicklab.runs

    runs_dir = pathlib.Path(qicklab.runs.__file__).parent
    displays, saves = [], set()
    for path in sorted(runs_dir.glob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(fn):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                    continue
                if node.func.attr == "display":
                    displays.append(f"{path.name}:{node.lineno} in {fn.name}")
                elif node.func.attr in ("save_data", "save_config"):
                    saves.add((path.name, fn.name))
    assert displays == [], f"call finish() instead of .display(): {displays}"
    assert saves <= _DIRECT_SAVE_ALLOWED, f"use finish(): {sorted(saves - _DIRECT_SAVE_ALLOWED)}"
