"""Runs without an RFSoC: saving as points are measured, the save folder, and the general plots.

The board is a stand-in (FakeProgram, from test_export) that returns known single shots.
"""
import json
import os
import subprocess
import sys

import numpy as np
import pytest

from Bob.config.settings import ExperimentSettings, SweepAxis
from Bob.core.params import Sweep, Value
from Bob.core.sequence import Sequence
from Bob.library import build_library
from Bob.runner import live_plot, save, script
from Bob.runner.export import export_python
from Bob.tests.reference import legacy
from Bob.tests.test_export import BOB_PARENT, FakeProgram, _load_script

TEMPLATES = build_library.HERE / "templates"
NO_BOARD = (lambda station: (object(), object()))


class Oscillating(FakeProgram):
    """Excited fraction depends on the flux waveform length, so each sweep point differs."""

    def __init__(self, soccfg, reps, final_delay, cfg):
        super().__init__(soccfg, reps, final_delay, cfg)
        n = len(cfg["bob"]["ff_waveforms"][0])
        self.excited = round(0.5 + 0.4 * np.cos(n / 900.0), 3)


def _mott(points=11, reps=100):
    seq = Sequence.load(TEMPLATES / "mott_quench.json")
    seq.settings.sweeps = [SweepAxis("t_dyn", 0.0, 2.3251, points, "µs")]
    seq.settings.reps = reps
    return seq


def _run(seq, station, calib, tmp_path, **kw):
    kw.setdefault("out_folder", str(tmp_path))
    return script.run(seq, station, calib, override=True, show_plot=False, connect=kw.pop("connect", NO_BOARD),
                      program_class=kw.pop("program_class", Oscillating), out=lambda *a: None, **kw)


# ================================================================== saving while it runs
def test_writer_saves_each_point_as_it_is_measured(tmp_path, monkeypatch):
    import h5py
    monkeypatch.setattr(save, "FLUSH_EVERY_S", 0.0)
    seq = _mott(points=5)
    w = save.RunWriter(tmp_path, seq)
    for k in range(3):
        w.write_point(k, {"t_dyn": 0.0}, {"population": [0.1 * k] * 6})
    with h5py.File(w.path, "r") as f:                          # readable while the run is still going
        pop = f["population"][()]
        assert f.attrs["status"] == "running" and f.attrs["points_done"] == 3
    assert np.allclose(pop[:, :3], [[0.0, 0.1, 0.2]] * 6) and np.isnan(pop[:, 3:]).all()
    w.close("stopped after 3 of 5 points")
    run = save.load_run(w.path)
    assert run["status"] == "stopped after 3 of 5 points" and run["points_done"] == 3
    assert Sequence.from_dict(run["sequence"]).name == seq.name
    assert list(run["data"]["readout_list"]) == [3, 4, 5, 6, 7, 8]


def test_run_saves_data_plot_and_files(station, calib, tmp_path):
    seq = _mott()
    path = _run(seq, station, calib, tmp_path)
    assert path.parent == tmp_path / "Mott_quench" / f"Mott_quench_{path.name[12:22]}"
    stem = str(path)[:-len("_data.h5")]
    for suffix in ("_data.png", "_bob_sequence.json", "_bob_snapshot.json"):
        assert os.path.exists(stem + suffix), suffix
    run = save.load_run(path)
    assert run["status"] == "complete" and run["points_done"] == 11
    pop = run["data"]["population_corrected"]
    assert pop.shape == (6, 11) and np.isfinite(pop).all()
    assert np.allclose(run["data"]["t_dyn"], seq.settings.sweeps[0].values())


class _StopsAtPoint4(Oscillating):
    calls = 0

    def acquire_shots(self, soc, rounds=1, progress=False):
        _StopsAtPoint4.calls += 1
        if _StopsAtPoint4.calls == 5:
            raise KeyboardInterrupt
        return super().acquire_shots(soc, rounds, progress)


def test_ctrl_c_keeps_what_was_measured(station, calib, tmp_path):
    _StopsAtPoint4.calls = 0
    path = _run(_mott(), station, calib, tmp_path, program_class=_StopsAtPoint4)
    run = save.load_run(path)
    assert run["status"] == "stopped by Ctrl+C after 4 of 11 points"
    pop = run["data"]["population_corrected"]
    assert np.isfinite(pop[:, :4]).all() and np.isnan(pop[:, 4:]).all()
    assert path.with_suffix(".png").exists()


class _BreaksAtPoint3(Oscillating):
    calls = 0

    def acquire_shots(self, soc, rounds=1, progress=False):
        _BreaksAtPoint3.calls += 1
        if _BreaksAtPoint3.calls == 4:
            raise RuntimeError("board went away")
        return super().acquire_shots(soc, rounds, progress)


def test_a_failed_run_keeps_its_data(station, calib, tmp_path):
    _BreaksAtPoint3.calls = 0
    with pytest.raises(RuntimeError, match="board went away"):
        _run(_mott(), station, calib, tmp_path, program_class=_BreaksAtPoint3)
    (path,) = tmp_path.rglob("*_data.h5")
    run = save.load_run(path)
    assert run["status"] == "failed after 3 of 11 points: board went away" and run["points_done"] == 3


# ================================================================== save folder
def test_save_folder_order(station, calib, tmp_path):
    seq = _mott(points=3)
    assert save.data_folder(seq, station) == station["outer_folder"]
    seq.settings.save_folder = str(tmp_path / "mine")
    assert save.data_folder(seq, station) == str(tmp_path / "mine")
    assert save.data_folder(seq, station, override=str(tmp_path / "cli")) == str(tmp_path / "cli")
    path = _run(seq, station, calib, tmp_path, out_folder=None)
    assert str(path).startswith(str(tmp_path / "mine"))


def test_save_folder_is_saved_with_the_sequence():
    s = ExperimentSettings(save_folder="D:/data")
    assert ExperimentSettings.from_dict(s.to_dict()).save_folder == "D:/data"
    assert "save_folder" not in ExperimentSettings().to_dict()          # old files stay unchanged


def test_exported_script_carries_the_save_folder(station, calib, tmp_path):
    seq = _mott(points=3)
    seq.settings.save_folder = "D:/runs"
    script_path = export_python(seq, station, calib, tmp_path / "mq.py")
    text = script_path.read_text(encoding="utf-8")
    assert "SAVE_FOLDER = 'D:/runs'" in text and "--show-data" in text
    s_seq, _, _ = _load_script(script_path).build()
    assert s_seq.settings.save_folder == "D:/runs"


def test_exported_script_shows_saved_data(station, calib, tmp_path):
    path = _run(_mott(), station, calib, tmp_path)
    script_path = export_python(_mott(), station, calib, tmp_path / "mq.py")
    env = dict(os.environ, BOB_PATH=str(BOB_PARENT), MPLBACKEND="Agg")
    done = subprocess.run([sys.executable, str(script_path), "--show-data", str(path)], capture_output=True,
                          text=True, env=env, timeout=120)
    assert done.returncode == 0, done.stderr


# ================================================================== plot layout
def _seq_with(axes, mode="populations_corrected"):
    seq = _mott()
    seq.settings.sweeps = axes
    seq.measure.set_field("mode", Value(mode))
    return seq


def test_layout_follows_the_sweep_and_the_measure_block():
    a, b, c = SweepAxis("t", 0, 1, 4, "µs"), SweepAxis("phi", 0, 90, 3, "deg"), SweepAxis("g", 0, 1, 2)
    assert live_plot.plot_layout(_seq_with([])).kind == "points"
    one = live_plot.plot_layout(_seq_with([a]))
    assert (one.kind, one.x.label, one.quantity, one.qubits) == ("lines", "t (µs)", "population_corrected",
                                                                  [3, 4, 5, 6, 7, 8])
    two = live_plot.plot_layout(_seq_with([b, a], "populations"))
    assert (two.kind, two.x.name, two.y.name, two.quantity) == ("maps", "t", "phi", "population")
    three = live_plot.plot_layout(_seq_with([c, b, a], "iq"))
    assert three.kind == "maps" and [x.name for x in three.outer] == ["g"] and three.quantity == "contrast"
    assert three.outer_index(3 * 4 + 5) == (1,) and three.outer_text((1,)) == "g = 1"


def test_three_axes_show_the_current_outer_point():
    L = live_plot.plot_layout(_seq_with([SweepAxis("g", 0, 1, 2), SweepAxis("phi", 0, 90, 3),
                                         SweepAxis("t", 0, 1, 4)]))
    data = {"population_corrected": np.arange(6 * 24, dtype=float).reshape(6, 24)}
    shown = live_plot.values(L, data, (1,))
    assert shown.shape == (6, 3, 4) and shown[0, 0, 0] == 12


def test_iq_contrast_matches_the_lab_helper():
    rng = np.random.default_rng(1)
    t = np.linspace(0, 1, 40)
    i, q = 0.3 + np.cos(6 * t) * 0.8 + rng.normal(0, 0.02, 40), -0.1 + np.cos(6 * t) * 0.5
    assert np.allclose(live_plot.iq_contrast(i, q), legacy.IQ_contrast(i, q))
    part = live_plot.iq_contrast(np.r_[i[:25], [np.nan] * 15], np.r_[q[:25], [np.nan] * 15])
    assert np.allclose(part[:25], legacy.IQ_contrast(i[:25], q[:25])) and np.isnan(part[25:]).all()


# ================================================================== the figure
def test_live_figure_shows_the_saved_numbers(station, calib, tmp_path):
    path = _run(_mott(), station, calib, tmp_path)
    plot = live_plot.show_saved(path, show=False)
    saved = save.load_run(path)["data"]["population_corrected"]
    for r, line in enumerate(plot.axes[0].lines):
        assert np.allclose(line.get_ydata(), saved[r])
    assert line.get_label() == "Read: Q8" and plot.axes[0].get_xlabel() == "t_dyn (µs)"
    assert "11 of 11 points" in plot.fig._suptitle.get_text()


def test_maps_for_two_axes(station, calib, tmp_path):
    seq = _mott(points=5)
    seq.settings.sweeps.insert(0, SweepAxis("phi", 0, 90, 3, "deg"))
    seq.pulses[-1].set_field("phase", Sweep("phi"))
    path = _run(seq, station, calib, tmp_path)
    plot = live_plot.show_saved(path, show=False)
    saved = save.load_run(path)["data"]["population_corrected"]
    assert len(plot._artists) == 6 and np.allclose(plot._artists[2].get_array(), saved[2])
    assert plot.axes[0].get_ylabel() == "phi (deg)" and plot.axes[0].get_title() == "Q3"


def test_a_stopped_run_says_so_on_the_plot(station, calib, tmp_path):
    _StopsAtPoint4.calls = 0
    path = _run(_mott(), station, calib, tmp_path, program_class=_StopsAtPoint4)
    plot = live_plot.show_saved(path, show=False)
    assert "4 of 11 points" in plot.fig._suptitle.get_text() and "stopped" in plot.fig._suptitle.get_text()


# ================================================================== the simulated board
from Bob.runner import simulate  # noqa: E402


def test_simulated_shots_give_the_intended_populations(station, calib):
    seq = _mott(points=11)
    from Bob.compiler.tlq_backend import compile_sequence
    compiled, _, _ = compile_sequence(seq, station, calib, seq.settings.point(4))
    cfg = dict(compiled.qick_cfg, bob_point={"index": 4, "shape": [11]})
    prog = simulate.SimulatedProgram(None, 40000, 0, cfg, seed=3)
    shots_i, shots_q = prog.acquire_shots(None)
    assert len(shots_i) == 6 and all(len(s) == 40000 for s in shots_i)
    from Bob.runner.populations import populations
    pops = populations(shots_i, shots_q, cfg)
    for r in range(6):
        p = simulate.excited_probability(r, cfg["bob_point"])
        ng, ne = cfg["confusion_matrix"][r][1][0], cfg["confusion_matrix"][r][0][1]
        assert abs(pops["population"][r] - (p * (1 - ne) + (1 - p) * ng)) < 0.01      # readout error applied
        assert abs(pops["population_corrected"][r] - p) < 0.015                        # and removed again
    iq = prog.acquire(None)
    assert len(iq) == 6 and np.asarray(iq[0]).shape == (1, 2)


def test_simulated_run_needs_no_board_and_is_kept_apart(station, calib, tmp_path):
    assert script.hardware_ready(station)                       # the real station is not verified
    path = script.run(_mott(), station, calib, out_folder=str(tmp_path), show_plot=False, simulate=True,
                      out=lambda *a: None)
    assert path.parts[-4] == "_simulated" and str(path).startswith(str(tmp_path))
    run = save.load_run(path)
    assert run["simulated"] and run["status"] == "complete" and run["board_config"] == ""
    pop = run["data"]["population_corrected"]
    assert pop.shape == (6, 11) and np.isfinite(pop).all() and pop.std() > 0.1     # the made-up signal shows
    assert not path.with_name(path.name.replace("_data.h5", "_soccfg.json")).exists()
    assert "(simulated data)" in live_plot.show_saved(path, show=False).fig._suptitle.get_text()


def test_real_run_without_simulate_still_refuses(station, calib, tmp_path):
    with pytest.raises(SystemExit, match="--simulate"):
        script.run(_mott(), station, calib, out_folder=str(tmp_path), show_plot=False, out=lambda *a: None)


def test_exported_script_runs_simulated(station, calib, tmp_path):
    script_path = export_python(_mott(points=5), station, calib, tmp_path / "mq.py")
    env = dict(os.environ, BOB_PATH=str(BOB_PARENT), MPLBACKEND="Agg")
    done = subprocess.run([sys.executable, str(script_path), "--run", "--simulate", "--out", str(tmp_path / "d")],
                          capture_output=True, text=True, env=env, timeout=180)
    assert done.returncode == 0, done.stderr
    (h5,) = (tmp_path / "d" / "_simulated").rglob("*_data.h5")
    assert save.load_run(h5)["simulated"] and h5.with_suffix(".png").exists()


# ================================================================== the board's live config
class _BoardConfig:
    def __init__(self, text):
        self.text = text

    def dump_cfg(self):
        return self.text


def test_every_real_run_saves_the_board_config(fresh_station, calib, tmp_path):
    cfg_text = json.dumps({"gens": [{"maxv": 32766}], "tprocs": [{"f_time": 430.08}]})
    connect = (lambda station: (object(), _BoardConfig(cfg_text)))
    path = _run(_mott(points=3), fresh_station, calib, tmp_path, connect=connect)
    saved = path.with_name(path.name.replace("_data.h5", "_soccfg.json"))
    assert saved.read_text(encoding="utf-8") == cfg_text
    run = save.load_run(path)
    assert run["board_config"] == cfg_text and run["board_config_check"].startswith("not compared")


def test_board_config_is_checked_against_the_station(fresh_station, tmp_path):
    fresh_station.folder = tmp_path
    live = json.dumps({"gens": [{"maxv": 32766}]})
    assert save.check_board_config(fresh_station, live).startswith("not compared: no saved board config")
    (tmp_path / "soccfg.json").write_text(json.dumps({"gens": [{"maxv": 32766}]}), encoding="utf-8")
    assert save.check_board_config(fresh_station, live) == "matches the station's saved board config"
    assert save.check_board_config(fresh_station, json.dumps({"gens": [{"maxv": 8191}]})).startswith("DIFFERS")
    assert save.check_board_config(fresh_station, None) == "no board config (no real board)"


# ================================================================== everything needed to run it again
from Bob.runner import rerun  # noqa: E402


def _two_axis_mott():
    seq = _mott(points=7)
    seq.settings.sweeps.insert(0, SweepAxis("phi", 0, 90, 3, "deg"))
    for p in seq.pulses[-6:]:
        p.set_field("phase", Sweep("phi"))
    return seq


def test_the_h5_holds_every_input(station, calib, tmp_path):
    import h5py
    path = _run(_two_axis_mott(), station, calib, tmp_path)
    with h5py.File(path, "r") as f:
        a = dict(f.attrs)
        assert json.loads(a["station"]) == station.to_dict() and a["station_name"] == "8QV1"
        assert json.loads(a["calibration"]) == calib.data and a["calibration_kind"] == "the whole calibration file"
        assert a["calibration_sha256"] == calib.sha256 and a["bob_version"]
        assert Sequence.from_dict(json.loads(a["bob_sequence"])).to_dict() == _two_axis_mott().to_dict() | {
            "blocks": json.loads(a["bob_sequence"])["blocks"]}
        varying = {ds.attrs["value"] for ds in f["resolved"].values()}
        assert {v.split(" › ")[1] for v in varying} == {"duration_us", "phase"} and len(varying) == 7
        assert f["resolved"]["Quench [{}] › duration_us".format(_two_axis_mott().segments[1].id)].shape == (3, 7)
        assert len(json.loads(f["resolved"].attrs["constant"])) > 50
    side = path.with_name(path.name.replace("_data.h5", "_qubit_parameters.json"))
    assert json.loads(side.read_text(encoding="utf-8")) == calib.data


def test_a_saved_run_rebuilds_exactly(station, calib, tmp_path):
    from Bob.compiler.tlq_backend import compile_sequence
    seq = _two_axis_mott()
    path = _run(seq, station, calib, tmp_path)
    report = rerun.check(path)
    assert report == {"points": 21, "mismatches": []}
    s2, st2, c2 = rerun.inputs(path)
    for k in (0, 10, 20):
        a, _, _ = compile_sequence(seq, station, calib, seq.settings.point(k))
        b, _, _ = compile_sequence(s2, st2, c2, s2.settings.point(k))
        assert np.array_equal(a.ff, b.ff) and a.qick_cfg["res_freqs"] == b.qick_cfg["res_freqs"]
        assert [(d.t_us, d.freq_mhz, d.gain, d.phase_deg) for d in a.drives] == \
               [(d.t_us, d.freq_mhz, d.gain, d.phase_deg) for d in b.drives]


def test_rerun_notices_a_changed_input(station, calib, tmp_path):
    import h5py
    path = _run(_mott(points=4), station, calib, tmp_path)
    with h5py.File(path, "a") as f:
        data = json.loads(f.attrs["calibration"])
        data["drive_groups"]["readout_3800"]["entries"]["3"]["Qubit"]["Frequency"] += 1.0
        f.attrs["calibration"] = json.dumps(data)
    bad = rerun.check(path)["mismatches"]
    assert bad and all("freq" in key or "res_" in key or "Frequency" in key for _, key, _, _ in bad)


def test_iir_files_travel_with_the_run(fresh_station, calib, tmp_path):
    """With compensation on, the coefficient files are saved too, and the rebuilt waveform is identical."""
    from Bob.compiler.tlq_backend import compile_sequence
    folder = tmp_path / "station"
    (folder / "iir").mkdir(parents=True)
    rng = np.random.default_rng(0)
    for files in fresh_station.data["compensation"]["files"].values():
        for name in files:
            q = 0.99 + 0.005 * rng.random()
            np.savetxt(folder / "iir" / name, np.vstack([[1, -q], [1.03 * (1 - q) / (1.03 * (1 - q)), -0.99]]).astype(complex))
    fresh_station.folder = folder
    seq = _mott(points=3)
    path = _run(seq, fresh_station, calib, tmp_path / "data")
    s2, st2, c2 = rerun.inputs(path)
    a, _, _ = compile_sequence(seq, fresh_station, calib, seq.settings.point(2))
    b, _, _ = compile_sequence(s2, st2, c2, s2.settings.point(2))
    assert a.compensated and b.compensated and np.array_equal(a.ff, b.ff)


def test_an_exported_scripts_run_records_its_frozen_calibration(station, calib, tmp_path):
    script_path = export_python(_mott(points=3), station, calib, tmp_path / "mq.py")
    s_seq, s_station, s_calib = _load_script(script_path).build()
    path = _run(s_seq, s_station, s_calib, tmp_path)
    import h5py
    with h5py.File(path, "r") as f:
        assert f.attrs["calibration_kind"].startswith("the calibration values in memory")
        assert json.loads(f.attrs["calibration"]) == s_calib.data
    assert rerun.check(path)["mismatches"] == []


def test_rerun_command_line(station, calib, tmp_path):
    path = _run(_mott(points=3), station, calib, tmp_path)
    env = dict(os.environ, MPLBACKEND="Agg")
    done = subprocess.run([sys.executable, "-m", "Bob.runner.rerun", str(path), "--run", "--simulate",
                           "--out", str(tmp_path / "again"), "--sequence", str(tmp_path / "seq.json")],
                          capture_output=True, text=True, env=env, timeout=180, cwd=str(BOB_PARENT))
    assert done.returncode == 0, done.stderr
    assert "rebuild 3 of 3 measured points exactly" in done.stdout
    assert Sequence.load(tmp_path / "seq.json").name == "Mott quench"
    assert list((tmp_path / "again" / "_simulated").rglob("*_data.h5"))
