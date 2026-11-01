"""Exported Python scripts, checked without an RFSoC.

Level 1: every template exports to a script that runs and compiles every sweep point.
Level 2: the script builds exactly the program Bob builds from the full calibration file.
Level 4: the whole run loop (populations, saving) with a stand-in for the board.
"""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from Bob.compiler.tlq_backend import compile_sequence
from Bob.config.station import Station
from Bob.core.sequence import Sequence
from Bob.library import build_library
from Bob.runner.experiment import BobExperiment
from Bob.runner.export import ExportError, export_python, frozen_calibration, py_literal
from Bob.runner.save import save_run
from Bob.runner.script import hardware_ready
from Bob.tests.reference import legacy

TEMPLATES = sorted((build_library.HERE / "templates").glob("*.json"))
BOB_PARENT = Path(__file__).resolve().parents[2]


def _load_script(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def exported(tmp_path, station, calib):
    def make(template_path, name=None):
        seq = Sequence.load(template_path)
        out = export_python(seq, station, calib, tmp_path / (name or f"{template_path.stem}.py"),
                            source=template_path.name)
        return seq, out
    return make


# ================================================================== level 1 and 2
@pytest.mark.parametrize("path", TEMPLATES, ids=[p.stem for p in TEMPLATES])
def test_script_rebuilds_the_same_program(path, exported, station, calib):
    seq, script = exported(path)
    mod = _load_script(script)
    s_seq, s_station, s_calib = mod.build()
    n = seq.settings.n_points()
    for k in sorted({0, n // 2, n - 1}):
        pt = seq.settings.point(k)
        a, _, _ = compile_sequence(seq, station, calib, pt)
        b, _, _ = compile_sequence(s_seq, s_station, s_calib, pt)
        assert np.array_equal(a.ff, b.ff), f"{path.stem} point {k}: flux differs"
        assert [(d.qubit, d.t_us, d.freq_mhz, d.gain, d.phase_deg) for d in a.drives] == \
               [(d.qubit, d.t_us, d.freq_mhz, d.gain, d.phase_deg) for d in b.drives]
        assert a.qick_cfg["res_freqs"] == b.qick_cfg["res_freqs"]


def test_script_runs_from_the_command_line(exported):
    _, script = exported(build_library.HERE / "templates" / "mott_quench.json")
    env = dict(os.environ, BOB_PATH=str(BOB_PARENT))
    done = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, env=env, timeout=120)
    assert done.returncode == 0, done.stderr
    assert "401 of 401 sweep points compile" in done.stdout


def test_run_refuses_until_the_station_is_verified(exported):
    _, script = exported(build_library.HERE / "templates" / "t1.json")
    env = dict(os.environ, BOB_PATH=str(BOB_PARENT))
    done = subprocess.run([sys.executable, str(script), "--run"], capture_output=True, text=True, env=env,
                          timeout=120)
    assert done.returncode != 0
    assert "Refusing to run on hardware" in done.stderr and "hardware_verified" in done.stderr


def test_header_says_how_to_run(exported):
    _, script = exported(build_library.HERE / "templates" / "mott_quench.json", "my_quench.py")
    head = script.read_text(encoding="utf-8").split('"""')[1]
    for part in ("HOW TO RUN", "python my_quench.py", "python my_quench.py --plot 0", "python my_quench.py --run",
                 "bob_qsim", "STATUS", "Prepared state 00111+11", "401 sweep points", "frozen from"):
        assert part in head, part


def test_settings_at_the_top_are_editable(exported):
    _, script = exported(build_library.HERE / "templates" / "t1.json")
    text = script.read_text(encoding="utf-8").replace("REPS = 1000", "REPS = 7", 1)
    script.write_text(text, encoding="utf-8")
    seq, _, _ = _load_script(script).build()
    assert seq.settings.reps == 7


def test_frozen_calibration_holds_only_what_is_used(exported, calib):
    _, script = exported(build_library.HERE / "templates" / "rabi.json")
    frozen = _load_script(script).CALIBRATION
    assert set(frozen) == {"drive_groups"} and set(frozen["drive_groups"]) == {"readout_3800"}
    assert len(json.dumps(frozen)) < len(json.dumps(calib.data)) / 5


def test_export_refuses_a_sequence_with_errors(tmp_path, station, calib, basic_seq):
    from Bob.core.params import Value
    basic_seq.pulses[0].set_field("freq", Value(9999.0))
    with pytest.raises(ExportError, match="mixer band"):
        export_python(basic_seq, station, calib, tmp_path / "x.py")
    assert not (tmp_path / "x.py").exists()


def test_plot_draws_the_compiled_point(exported):
    pytest.importorskip("matplotlib")
    from Bob.runner import script as script_mod
    _, script = exported(build_library.HERE / "templates" / "mott_quench.json")
    seq, st, cal = _load_script(script).build()
    fig = script_mod.plot(seq, st, cal, 200, show=False)
    assert "t_dyn" in fig._suptitle.get_text() and len(fig.axes[0].lines) >= 8
    with pytest.raises(ValueError, match="out of range"):
        script_mod.plot(seq, st, cal, 401, show=False)


def test_helpers():
    assert frozen_calibration({"a/b": 1, "a/c/d": [2]}) == {"a": {"b": 1, "c": {"d": [2]}}}
    assert eval(py_literal({"x": [1, 2, {"y": "z" * 120}]})) == {"x": [1, 2, {"y": "z" * 120}]}


def test_hardware_ready(fresh_station, tmp_path):
    assert len(hardware_ready(fresh_station)) == 2
    iir = tmp_path / "iir"
    iir.mkdir()
    np.savetxt(iir / "x.csv", np.vstack([np.r_[1.0, 0, 0] + 0j, np.r_[1.0, 0, 0] + 0j]))
    fresh_station.folder = tmp_path
    fresh_station.data["compensation"] = {"iir_dir": "iir", "files": {str(q): ["x.csv"] for q in range(1, 9)}}
    fresh_station.data["hardware_verified"] = True
    assert hardware_ready(fresh_station) == []


def test_station_starts_unverified():
    assert Station.load("8QV1").data["hardware_verified"] is False


# ================================================================== level 4: a stand-in for the board
class FakeProgram:
    """Stands in for BobProgram: returns known single shots instead of talking to an RFSoC."""
    excited = 0.25                               # fraction of shots placed above threshold

    def __init__(self, soccfg, reps, final_delay, cfg):
        self.cfg, self.reps = cfg, reps

    def acquire_shots(self, soc, rounds=1, progress=False):
        shots_i, shots_q = [], []
        for k in range(len(self.cfg["ro_chs"])):
            a, thr = self.cfg["angle"][k], self.cfg["threshold"][k]
            m = int(self.excited * self.reps)
            i_rot = np.r_[np.full(m, thr + 1.0), np.full(self.reps - m, thr - 1.0)]
            q_rot = np.zeros(self.reps)
            # undo the rotation the analysis will apply
            shots_i.append(i_rot * np.cos(-a) - q_rot * np.sin(-a))
            shots_q.append(i_rot * np.sin(-a) + q_rot * np.cos(-a))
        return shots_i, shots_q

    def acquire(self, soc, rounds=1, progress=False):
        return [np.array([[0.1 * k, -0.1 * k]]) for k in range(len(self.cfg["ro_chs"]))]


def test_run_loop_with_populations(station, calib, tmp_path):
    h5py = pytest.importorskip("h5py")
    seq = Sequence.load(build_library.HERE / "templates" / "t1.json")
    exp = BobExperiment(seq, station, calib, soc=object(), soccfg=object(), program_class=FakeProgram)
    seen = []
    exp.on_point(lambda k, pt, data: seen.append(k))
    data = exp.run()
    n = seq.settings.n_points()
    assert seen == list(range(n))
    assert data["population"].shape == (1, n) and np.allclose(data["population"], 0.25)
    conf = np.array(calib.readout_config("readout_3800", [3], 0.0)["confusion_matrix"][0])
    assert np.allclose(data["population_corrected"], legacy.correct_occ(np.array([0.25]), conf)[0])
    assert np.allclose(data["t_wait"], seq.settings.sweeps[0].values())
    path = save_run(tmp_path, "t1", {k: v for k, v in data.items() if k != "snapshot"}, data["snapshot"],
                    seq.to_dict())
    with h5py.File(path, "r") as f:
        assert f["population_corrected"].shape == (1, n)


def test_run_loop_with_iq(station, calib):
    seq = Sequence.load(build_library.HERE / "templates" / "rabi.json")
    exp = BobExperiment(seq, station, calib, soc=object(), soccfg=object(), program_class=FakeProgram)
    data = exp.run()
    assert "population" not in data and data["I"].shape == (1, seq.settings.n_points())
