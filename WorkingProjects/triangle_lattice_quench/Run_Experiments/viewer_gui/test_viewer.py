"""Pytests for the viewer: index tiers, filters, lattice geometry, replot safety, and
independence from qick / calibration_gui.

Everything runs against a temp tree and a temp SQLite file: no network share is
touched and nothing is ever written next to real data. Qt is imported (offscreen) but
the window-building checks run in subprocesses so no QThread outlives a test.
"""
from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

from triangle_lattice_quench.Experiment import ExperimentClass
from triangle_lattice_quench.Run_Experiments.viewer_gui import data_index as dx

WORKING_PROJECTS = Path(__file__).resolve().parents[3]


# --------------------------------------------------------------------------- #
# fixtures: a fake tree mimicking <Expt>/<Expt>_Y_M_D/<Expt>_Y_M_D_H_M_S_*.h5
# --------------------------------------------------------------------------- #

class T1(ExperimentClass):
    """Named so save_metadata writes Experiment='T1' (what the real class writes)."""


def _write_run(root: Path, experiment: str, day: str, time: str,
               qubit_readout, group_name="", name="", cls=T1) -> Path:
    """Write one run the way ExperimentClass really does, via save_data/save_metadata."""
    folder = root / experiment / f"{experiment}_{day}"
    folder.mkdir(parents=True, exist_ok=True)
    fname = folder / f"{experiment}_{day}_{time}_data.h5"
    expt = cls.__new__(cls)
    expt.fname = str(fname)
    expt.cname = str(fname)[:-3] + ".json"
    expt.iname = str(fname)[:-3] + ".png"
    expt.start_time = f"{day.replace('_', '-')}T{time.replace('_', ':')}"
    expt.day_folder = folder.name
    expt.day = folder.name[-10:]
    expt.cfg = {"Qubit_Readout_List": list(qubit_readout),
                "qubit_freqs": [4000.0] * max(1, len(qubit_readout)),
                "meta": {"group_name": group_name, "name": name}}
    expt.data = {"config": expt.cfg,
                 "data": {"Qubit_Readout_List": list(qubit_readout),
                          "x_pts": [0.0, 1.0, 2.0, 3.0],
                          "avgi": [1.0, 0.7, 0.5, 0.3],
                          "avgq": [0.1, 0.1, 0.1, 0.1]}}
    expt.save_data(expt.data)
    return fname


@pytest.fixture
def tree(tmp_path):
    """Pre- and post-cutover runs, an underscored experiment name, an old folder and a
    stray h5 sitting directly in an experiment folder."""
    root = tmp_path / "FakeDevice"
    legacy = _write_run(root, "T1", "2026_09_30", "10_00_00", [3], "legacygrp", "old")
    old = _write_run(root, "T1", "2025_01_05", "08_00_00", [4], "ancient", "old2")
    new_1q = _write_run(root, "T1", "2026_10_01", "11_00_00", [3], "calib", "t1")
    new_2q = _write_run(root, "CurrentCalibration_1D_Shots", "2026_10_02", "09_30_00",
                        [3, 5], "dynamics", "sweep")
    stray = root / "Weird" / "not_a_dated_file.h5"
    stray.parent.mkdir(parents=True, exist_ok=True)
    import h5py
    with h5py.File(stray, "w") as f:
        f.create_dataset("x", data=[1, 2, 3])
    return {"root": root, "legacy": legacy, "old": old, "new_1q": new_1q,
            "new_2q": new_2q, "stray": stray, "db": tmp_path / "idx.sqlite"}


def _counting(opened):
    def counting_open(path):
        opened.append(os.path.normcase(path))
        return dx.read_metadata(path)
    return counting_open


def _rows(conn):
    return {r["path"]: dict(r) for r in conn.execute("SELECT * FROM files")}


# --------------------------------------------------------------------------- #
# path parsing
# --------------------------------------------------------------------------- #

def test_parse_path_survives_underscored_experiment_names(tmp_path):
    p = (tmp_path / "CurrentCalibration_1D_Shots" / "CurrentCalibration_1D_Shots_2026_10_02"
         / "CurrentCalibration_1D_Shots_2026_10_02_09_30_00_population_shots.h5")
    p.parent.mkdir(parents=True)
    p.touch()
    parsed = dx.parse_path(tmp_path, str(p))
    assert parsed["experiment"] == "CurrentCalibration_1D_Shots"
    assert parsed["day_date"] == "2026-10-02"
    assert parsed["timestamp"] == "2026-10-02T09:30:00"
    assert dx.day_date("T1_2026_10_01") == "2026-10-01"
    assert dx.day_date("not_a_day_folder") is None


def test_qubit_label_normalizes_every_spelling():
    import numpy as np
    assert [dx.qubit_label(v) for v in ("Q3", "3", 3, np.int64(3), b"Q3")] == [3] * 5
    assert dx.qubit_label("readout_3800") is None


# --------------------------------------------------------------------------- #
# TIER 2 (full walk) -- path-derived always, file opened only on/after the cutover
# --------------------------------------------------------------------------- #

def test_full_scan_derives_from_path_and_never_opens_pre_cutover_files(tree):
    opened = []
    stats = dx.scan(str(tree["root"]), "FakeDevice", db_path=tree["db"],
                    open_file=_counting(opened))
    assert stats["indexed"] == 5 and stats["failed"] == 0

    conn = dx.connect(tree["db"])
    rows = _rows(conn)
    by = lambda key: rows[str(tree[key])]

    # path-derived fields: right for every file, opened or not
    assert by("legacy")["experiment"] == "T1"
    assert by("legacy")["timestamp"] == "2026-09-30T10:00:00"
    assert by("new_2q")["experiment"] == "CurrentCalibration_1D_Shots"
    assert by("new_2q")["timestamp"] == "2026-10-02T09:30:00"
    assert by("stray")["experiment"] == "Weird" and by("stray")["timestamp"] is None

    # The pre-cutover files HAVE real attrs on disk, so "no metadata captured" can only
    # mean they were never opened -- and the open counter confirms it directly.
    assert dx.read_metadata(str(tree["legacy"]))["Qubit_Readout"].tolist() == [3]
    for key in ("legacy", "old", "stray"):
        assert by(key)["has_meta"] == 0
        assert by(key)["qubit_readout"] is None and by(key)["group_name"] is None
        assert os.path.normcase(str(tree[key])) not in opened
    assert len(opened) == 2                                   # only the two post-cutover

    assert by("new_1q")["has_meta"] == 1
    assert by("new_1q")["qubit_readout"] == "[3]"
    assert by("new_1q")["group_name"] == "calib" and by("new_1q")["name"] == "t1"
    assert by("new_2q")["qubit_readout"] == "[3, 5]" and by("new_2q")["n_readout"] == 2
    conn.close()


def test_rescan_with_unchanged_mtimes_opens_nothing(tree):
    dx.scan(str(tree["root"]), "FakeDevice", db_path=tree["db"])
    opened = []
    stats = dx.scan(str(tree["root"]), "FakeDevice", db_path=tree["db"],
                    open_file=_counting(opened))
    assert stats["skipped"] == 5 and stats["indexed"] == 0 and opened == []


def _qfilter(qubits, mode=dx.DEFAULT_QUBIT_MODE):
    return {"qubits": {"mode": mode, "qubits": list(qubits)}}


def test_string_qubit_labels_round_trip(tmp_path):
    """save_metadata writes qubit labels through h5py's vlen-string path, so GUI runs
    (which carry '3' / 'Q5' rather than ints) are filterable too."""
    root = tmp_path / "D"
    path = _write_run(root, "T1", "2026_10_01", "12_00_00", ["3", "Q5"])
    meta = dx.read_metadata(str(path))
    assert [str(v) for v in meta["Qubit_Readout"]] == ["3", "Q5"]
    db = tmp_path / "s.sqlite"
    dx.scan(str(root), "D", db_path=db)
    conn = dx.connect(db)
    assert dx.query(_qfilter([3, 5]), "D", conn=conn)[1] == 1
    assert dx.query(_qfilter([7]), "D", conn=conn)[1] == 0
    conn.close()


# --------------------------------------------------------------------------- #
# TIER 0 / TIER 1 / refresh
# --------------------------------------------------------------------------- #

def test_tier1_indexes_newest_first_and_stops_on_a_date_boundary(tree):
    conn = dx.connect(tree["db"])
    dx.map_day_folders(str(tree["root"]), "FakeDevice", conn, full=True)
    days = conn.execute("SELECT path, date, recursive FROM day_folders").fetchall()
    # 4 dated day folders + 1 synthetic undated row for the loose file in Weird/
    assert sum(1 for d in days if d["date"]) == 4
    assert sum(1 for d in days if d["date"] is None and d["recursive"] == 0) == 1

    dx.fill_view("FakeDevice", conn, needed=1)
    rows = _rows(conn)
    assert list(rows) == [str(tree["new_2q"])]            # only the newest date
    hz = dx.horizon("FakeDevice", {}, conn=conn)
    assert not hz["complete"] and hz["newest_unindexed"] == "2026-10-01"
    assert hz["undated_unindexed"] == 1                    # the stray file's folder

    dx.fill_view("FakeDevice", conn, needed=99)            # all DATED folders
    assert len(_rows(conn)) == 4
    assert dx.horizon("FakeDevice", {}, conn=conn)["undated_unindexed"] == 1

    dx.index_all(str(tree["root"]), "FakeDevice", conn)    # tier 2 adds the stray
    assert len(_rows(conn)) == 5
    assert dx.horizon("FakeDevice", {}, conn=conn)["complete"]
    conn.close()


def test_refresh_finds_a_file_added_to_an_existing_day_folder(tree):
    """A day folder's parent keeps its mtime when a FILE lands inside it, so tier 0 +
    tier 1 alone would never show today's new run. The recency window is what does."""
    conn = dx.connect(tree["db"])
    dx.open_device(str(tree["root"]), "FakeDevice", conn)
    assert len(_rows(conn)) == 4

    extra = _write_run(tree["root"], "T1", "2026_10_01", "23_59_00", [6], "late", "x")

    dx.map_day_folders(str(tree["root"]), "FakeDevice", conn, full=False)
    dx.fill_view("FakeDevice", conn, needed=dx.VIEW_ROWS)
    assert str(extra) not in _rows(conn), "tier 0 + tier 1 alone cannot see it"

    dx.refresh(str(tree["root"]), "FakeDevice", conn)
    assert str(extra) in _rows(conn)
    conn.close()


def test_refresh_sees_a_brand_new_day_folder(tree):
    """Regression guard for the Windows directory-mtime trap: this fails if
    map_day_folders goes back to reading the scandir entry's cached stat instead of
    calling os.stat on each experiment folder."""
    conn = dx.connect(tree["db"])
    dx.open_device(str(tree["root"]), "FakeDevice", conn)
    extra = _write_run(tree["root"], "T1", "2026_10_03", "08_00_00", [7], "new", "y")
    dx.refresh(str(tree["root"]), "FakeDevice", conn)      # expt-folder mtime changed
    assert str(extra) in _rows(conn)
    conn.close()


def test_failed_open_is_retried_on_the_next_pass(tree):
    conn = dx.connect(tree["db"])
    calls = {"n": 0}

    def flaky(path):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("file locked by the writer")
        return dx.read_metadata(path)

    dx.open_device(str(tree["root"]), "FakeDevice", conn, open_file=flaky)
    assert any(r["mtime"] is None for r in _rows(conn).values())   # NULL -> retry
    dx.refresh(str(tree["root"]), "FakeDevice", conn, open_file=flaky)
    assert all(r["mtime"] is not None for r in _rows(conn).values())
    conn.close()


def test_pruning_removes_rows_for_deleted_files(tree):
    conn = dx.connect(tree["db"])
    dx.index_all(str(tree["root"]), "FakeDevice", conn)
    assert len(_rows(conn)) == 5
    os.remove(tree["new_1q"])
    dx.refresh(str(tree["root"]), "FakeDevice", conn)
    assert str(tree["new_1q"]) not in _rows(conn)
    conn.close()


# --------------------------------------------------------------------------- #
# filters: unset filters must never exclude a metadata-free row
# --------------------------------------------------------------------------- #

def test_unset_filters_pass_every_row_including_legacy(tree):
    dx.scan(str(tree["root"]), "FakeDevice", db_path=tree["db"])
    conn = dx.connect(tree["db"])
    for values in ({}, {s.key: None for s in dx.FILTERS},
                   {"experiment": dx.ANY, "experiment_class": "",
                    "qubits": {"mode": "=", "qubits": []},
                    "nq": dx.ANY, "group_name": "", "name": "   ",
                    "date": (None, None)}):
        rows, total = dx.query(values, "FakeDevice", conn=conn)
        assert total == 5, values
        assert any(r["has_meta"] == 0 for r in rows)
    conn.close()


def test_set_filters_exclude_legacy_and_keep_matching_new_rows(tree):
    dx.scan(str(tree["root"]), "FakeDevice", db_path=tree["db"])
    conn = dx.connect(tree["db"])
    q = lambda v: dx.query(v, "FakeDevice", conn=conn)

    # Default qubit rule is EXACT; legacy rows have no qubit info -> excluded.
    rows, total = q(_qfilter([3]))
    assert total == 1 and all(r["has_meta"] == 1 for r in rows)
    assert q(_qfilter([3, 5]))[1] == 1                    # exactly the 2Q run
    assert q(_qfilter([8]))[1] == 0

    assert q({"nq": "1Q"})[1] == 1 and q({"nq": "2Q"})[1] == 1 and q({"nq": "MQ"})[1] == 0
    assert q({"group_name": "cal"})[1] == 1               # substring, legacy excluded
    assert q({"name": "sweep"})[1] == 1
    # The Experiment filter matches the FOLDER name, which every file has -- so legacy
    # and post-cutover runs of the same experiment land in one bucket.
    assert q({"experiment": "T1"})[1] == 3
    # The class name (the 'Experiment' attr) is a separate, post-cutover-only column.
    assert q({"experiment_class": "T1"})[1] == 2   # both post-cutover runs
    assert q({"date": ("2026-10-01", None)})[1] == 2
    assert q({"date": (None, "2026-09-30")})[1] == 2      # 2025-01-05 and 2026-09-30
    conn.close()


def test_query_cap_reports_true_total(tree):
    dx.scan(str(tree["root"]), "FakeDevice", db_path=tree["db"])
    conn = dx.connect(tree["db"])
    rows, total = dx.query({}, "FakeDevice", conn=conn, limit=2)
    assert len(rows) == 2 and total == 5
    assert [r["timestamp"] for r in rows] == sorted(
        [r["timestamp"] for r in rows], reverse=True)          # newest first
    conn.close()


def test_metadata_filters_scope_the_horizon_to_post_cutover_days(tree):
    """A class/group/name filter can only ever match post-cutover files, so the view is
    complete as soon as those day folders are indexed -- no 86 s walk offered. The qubit
    filters are NOT scoped this way: old runs match through the lazy config lookup, so
    they need the whole history (otherwise the status claimed "nothing indexed yet"
    while showing matches)."""
    conn = dx.connect(tree["db"])
    dx.map_day_folders(str(tree["root"]), "FakeDevice", conn, full=True)
    dx.fill_view("FakeDevice", conn, needed=1)             # only 2026-10-02

    group = {"group_name": "cal"}
    hz_all = dx.horizon("FakeDevice", {}, conn=conn)
    hz_meta = dx.horizon("FakeDevice", group, conn=conn)
    hz_qubit = dx.horizon("FakeDevice", _qfilter([3]), conn=conn)
    # unscoped: 2025-01-05 + 2026-09-30 + 2026-10-01 + the undated stray folder.
    assert hz_all["unindexed_days"] == 4 and hz_all["newest_unindexed"] == "2026-10-01"
    # metadata-scoped: pre-cutover days cannot match, so only 2026-10-01 + undated.
    assert hz_meta["unindexed_days"] == 2 and hz_meta["newest_unindexed"] == "2026-10-01"
    # qubit filter: old runs can match too, so it sees exactly what an unfiltered view does.
    assert hz_qubit["unindexed_days"] == hz_all["unindexed_days"]
    assert hz_qubit["newest_unindexed"] == hz_all["newest_unindexed"]

    dx.fill_view("FakeDevice", conn, needed=99)            # all dated folders
    hz_meta = dx.horizon("FakeDevice", group, conn=conn)
    # Nothing DATED is left for a metadata filter; only loose undated files remain,
    # and those are reported separately rather than as a date horizon.
    assert hz_meta["newest_unindexed"] is None and hz_meta["undated_unindexed"] == 1
    assert dx.day_scope(_qfilter([3])) == {}               # could match any day folder
    assert dx.day_scope(group) == {"date_lo": dx.METADATA_CUTOVER}
    assert dx.day_scope({"experiment": "T1"}) == {"experiment": "T1"}
    conn.close()


def test_qubit_match_modes(tmp_path):
    """= exact / contains (selection superset) / within (selection subset)."""
    root = tmp_path / "M"
    _write_run(root, "T1", "2026_10_01", "10_00_00", [3])          # 1Q on Q3
    _write_run(root, "T1", "2026_10_01", "10_01_00", [5])          # 1Q on Q5
    _write_run(root, "T1", "2026_10_01", "10_02_00", [3, 4])       # Q3+Q4
    _write_run(root, "T1", "2026_10_01", "10_03_00", [3, 5])       # Q3+Q5
    _write_run(root, "T1", "2026_10_01", "10_04_00", [3, 4, 5])    # Q3+Q4+Q5
    db = tmp_path / "m.sqlite"
    dx.scan(str(root), "M", db_path=db)
    conn = dx.connect(db)
    sets = lambda mode: sorted(
        sorted(json.loads(r["qubits"])) for r in
        dx.query(_qfilter([3, 5], mode), "M", conn=conn)[0])

    # exact: ONLY {3,5} -- not Q3 alone, not Q3+Q4, not Q3+Q4+Q5 (the user's words).
    assert sets("=") == [[3, 5]]
    # contains: every run whose qubits fit inside the selection.
    assert sets("⊇") == [[3], [3, 5], [5]]
    # within: every run that includes the selection, others allowed.
    assert sets("⊆") == [[3, 4, 5], [3, 5]]
    conn.close()


def test_qubit_fallback_chain_recovers_a_dataset_only_file(tmp_path):
    """A post-cutover file whose only qubit info is /data/Qubit_Readout_List is still
    filterable, and the index records that the value came from the dataset."""
    import h5py
    root = tmp_path / "F"
    path = _write_run(root, "T1", "2026_10_01", "13_00_00", [3, 6])
    with h5py.File(path, "a") as f:                  # strip the attrs: dataset only
        for key in ("qubits", "Qubit_Readout"):
            f.attrs.pop(key, None)
    meta = dx.read_metadata(str(path))
    assert "Qubit_Readout" not in meta and meta["_qubit_fallback_source"] == "dataset"

    db = tmp_path / "f.sqlite"
    dx.scan(str(root), "F", db_path=db)
    conn = dx.connect(db)
    rows, total = dx.query(_qfilter([3, 6]), "F", conn=conn)
    assert total == 1 and rows[0]["qubit_source"] == "dataset"
    assert json.loads(rows[0]["qubits"]) == [3, 6]
    conn.close()


def test_qubit_source_prefers_attrs_over_the_dataset(tmp_path):
    root = tmp_path / "P"
    _write_run(root, "T1", "2026_10_01", "14_00_00", [2])
    db = tmp_path / "p.sqlite"
    dx.scan(str(root), "P", db_path=db)
    conn = dx.connect(db)
    rows, _ = dx.query({}, "P", conn=conn)
    assert rows[0]["qubit_source"] == "qubits"      # attr 'qubits', top of the chain
    conn.close()


# --------------------------------------------------------------------------- #
# lattice geometry
# --------------------------------------------------------------------------- #

def test_triangle_lattice_geometry_and_hit_test():
    from triangle_lattice_quench.Run_Experiments.viewer_gui import lattice as lt
    topo = lt.device_topology("8QV1_Triangle_Lattice")
    assert len(topo["qubits"]) == 8 and len(topo["couplers"]) == 6
    assert topo["edges"], "device json should give qubit-qubit couplings"

    for name, (x, y) in topo["qubits"].items():
        assert lt.hit_test(topo, x, y) == ("qubit", name)
    # C1 sits at the midpoint of Q1-Q3 and stands for that pair.
    cx, cy = topo["couplers"]["C1"]
    assert lt.hit_test(topo, cx, cy) == ("pair", ("Q1", "Q3"))
    # A plain rung edge: the midpoint of Q2-Q3 selects that pair.
    (x2, y2), (x3, y3) = topo["qubits"]["Q2"], topo["qubits"]["Q3"]
    assert set(lt.hit_test(topo, (x2 + x3) / 2, (y2 + y3) / 2)[1]) == {"Q2", "Q3"}
    assert lt.hit_test(topo, 99.0, 99.0) is None


def test_rungs_come_from_topology_not_parity():
    from triangle_lattice_quench.Run_Experiments.viewer_gui import lattice as lt
    topo = lt.device_topology("8QV1_Triangle_Lattice")
    # Edges with a coupler at the midpoint (Qk-Qk+2) are NOT rungs; the zig-zag is.
    assert sorted(topo["rungs"]) == [(f"Q{k}", f"Q{k + 1}") for k in range(1, 8)]
    for (a, b), (mx, my) in topo["rungs"].items():
        assert lt.hit_test(topo, mx, my) == ("pair", (a, b))
        # a click near (not on) the square still lands within its pick radius
        assert lt.hit_test(topo, mx + 0.02, my - 0.02) == ("pair", (a, b))


# --------------------------------------------------------------------------- #
# Qt widgets in-process (no QThread is ever started by these)
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isolated_settings_and_date(monkeypatch):
    """Tests never touch the user's real QSettings (zoom, last device), and the 14-day
    recency window is pinned to the fixture dates rather than the machine clock."""
    import datetime
    from PyQt5.QtCore import QSettings
    from triangle_lattice_quench.Run_Experiments.viewer_gui import browser as br
    from triangle_lattice_quench.Run_Experiments.viewer_gui import main_window as mw
    monkeypatch.setattr(br, "SETTINGS_APP", "TriangleLatticeDataViewer_PYTEST")
    monkeypatch.setattr(mw, "SETTINGS_APP", "TriangleLatticeDataViewer_PYTEST")
    monkeypatch.setattr(dx, "_today", lambda: datetime.date(2026, 10, 1))
    from PyQt5.QtWidgets import QApplication
    from triangle_lattice_quench.Run_Experiments.viewer_gui import style as st
    QSettings(br.SETTINGS_ORG, "TriangleLatticeDataViewer_PYTEST").clear()
    yield
    QSettings(br.SETTINGS_ORG, "TriangleLatticeDataViewer_PYTEST").clear()
    app = QApplication.instance()
    if app is not None:
        _destroy_all_widgets(app)                 # no zombie widget outlives its test
        st.apply_style(app, st.ZOOM_DEFAULT)      # no zoom leaks


def _destroy_all_widgets(app):
    """Stop workers, close and DELETE every top-level widget, flush deferred deletes.

    Without this, widgets a test merely closed stay alive in C++; a later
    app.setStyleSheet() restyles every live widget, and restyling one whose Python side
    has been collected was an intermittent access violation (seen at different tests on
    different runs, always inside apply_style -> setStyleSheet)."""
    import gc
    from PyQt5.QtCore import QCoreApplication, QEvent
    from triangle_lattice_quench.Run_Experiments.viewer_gui.browser import BrowserWidget
    for widget in app.allWidgets():
        if isinstance(widget, BrowserWidget):
            widget._stop_worker()
            widget._queued = None
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()
    gc.collect()


def _lattice(qapp, width, device="8QV1_Triangle_Lattice"):
    """A shown LatticeSelector of the given width; its height follows the width."""
    from triangle_lattice_quench.Run_Experiments.viewer_gui.lattice import LatticeSelector
    sel = LatticeSelector()
    sel.resize(width, 300)
    sel.show()
    qapp.processEvents()
    sel.set_device(device)
    for _ in range(4):                            # deferred height sync + canvas resize
        qapp.processEvents()
    sel.redraw()
    sel.canvas.draw()
    return sel


def _drawn(sel):
    """{kind: [(position, window bbox)]} for every visible marker artist.

    Classified by POSITION, not marker shape: couplers and rungs are both squares now,
    told apart by colour on screen and here by which topology table holds the point."""
    r = sel.canvas.get_renderer()
    rungs = set(sel.topo["rungs"].values())
    couplers = set(sel.topo["couplers"].values())
    qubits = set(sel.topo["qubits"].values())
    out = {}
    for art in sel.canvas.ax.lines:
        if not (art.get_visible() and len(art.get_xdata()) == 1 and art.get_mfc() != "none"):
            continue                                  # edges, the hover ring
        pos = (art.get_xdata()[0], art.get_ydata()[0])
        kind = ("qubit" if pos in qubits else "rung" if pos in rungs
                else "coupler" if pos in couplers else None)
        if kind:
            out.setdefault(kind, []).append((pos, art.get_window_extent(r)))
    return out


def test_couplers_and_rungs_are_both_squares_told_apart_by_colour(qapp):
    from matplotlib.colors import to_rgb
    from triangle_lattice_quench.Run_Experiments.viewer_gui import style as st
    sel = _lattice(qapp, 522)
    rungs, couplers = set(sel.topo["rungs"].values()), set(sel.topo["couplers"].values())
    seen = {"rung": set(), "coupler": set()}
    for art in sel.canvas.ax.lines:
        if len(art.get_xdata()) == 1 and art.get_mfc() != "none":
            pos = (art.get_xdata()[0], art.get_ydata()[0])
            for kind, where in (("rung", rungs), ("coupler", couplers)):
                if pos in where:
                    assert art.get_marker() == "s"
                    seen[kind].add(to_rgb(art.get_mec()))
    assert seen["rung"] == {to_rgb(st.RUNG["edge"])}
    assert seen["coupler"] == {to_rgb(st.COUPLER["edge"])}
    assert seen["rung"] != seen["coupler"]
    sel.close()


@pytest.mark.parametrize("width", [440, 522, 800])
def test_squares_keep_their_gap_from_neighbouring_qubits(qapp, width):
    """The size cap: every square, at its widest (selected) edge, stays GAP_PT clear of
    every qubit circle -- the rung squares between columns are where it binds."""
    from triangle_lattice_quench.Run_Experiments.viewer_gui import lattice as lt
    sel = _lattice(qapp, width)
    sel.set_selected(set(sel.topo["qubits"]))     # widest edges everywhere
    sel.canvas.draw()
    drawn = _drawn(sel)
    ppt = sel.canvas.fig.dpi / 72
    gap_px = lt.GAP_PT * ppt
    worst = float("inf")
    for (qpos, qbb) in drawn["qubit"]:
        qx, qy, qr = (qbb.x0 + qbb.x1) / 2, (qbb.y0 + qbb.y1) / 2, qbb.width / 2
        for kind in ("rung", "coupler"):
            for (_, sbb) in drawn[kind]:
                # distance from circle centre to the axis-aligned square, minus radius
                dx_ = max(sbb.x0 - qx, 0, qx - sbb.x1)
                dy_ = max(sbb.y0 - qy, 0, qy - sbb.y1)
                worst = min(worst, (dx_ ** 2 + dy_ ** 2) ** 0.5 - qr)
    assert worst >= gap_px - 1.0, (width, worst, gap_px)   # 1 px antialias tolerance
    sel.close()


@pytest.mark.parametrize("width", [300, 380, 440, 522, 600, 800])
def test_lattice_markers_never_leave_the_figure(qapp, width):
    sel = _lattice(qapp, width)
    sel.set_selected({"Q1", "Q8", "Q4", "Q5"})   # selected = thicker edge, worst case
    sel._set_hover(("qubit", "Q8"))               # hover ring = the outermost artist
    canvas = sel.canvas
    canvas.draw()
    renderer = canvas.get_renderer()
    fig_box, ax_box = canvas.fig.bbox, canvas.ax.get_window_extent(renderer)
    assert abs(fig_box.width - width) <= 2
    arts = [a for a in canvas.ax.lines if a.get_visible() and len(a.get_xdata())
            and a.get_marker() not in (None, "None", "")] + canvas.ax.texts
    assert len(arts) == 8 + 6 + 7 + 8 + 1         # qubits, couplers, rungs, labels, ring
    for box in (fig_box, ax_box):
        for art in arts:
            bb = art.get_window_extent(renderer)
            assert (bb.x0 >= box.x0 - 0.5 and bb.y0 >= box.y0 - 0.5
                    and bb.x1 <= box.x1 + 0.5 and bb.y1 <= box.y1 + 0.5), (width, bb)
    assert not any(a.get_clip_on() for a in canvas.ax.lines + canvas.ax.texts)
    # height follows width: no empty bands
    assert sel.height() == sel.heightForWidth(sel.width())
    sel.close()


def test_lattice_sizes_at_the_default_column_width(qapp):
    """522 px is the measured lattice width in the 1500x850 window (windows platform)."""
    sel = _lattice(qapp, 522)
    drawn = _drawn(sel)
    side = lambda kind: min(min(bb.width, bb.height) for _, bb in drawn[kind])
    assert side("qubit") >= 34 and side("rung") >= 20 and side("coupler") >= 22
    assert 2 * sel.sizes["marker_hit_px"] >= 30   # pair markers clickable over >= 30 px
    assert sel.sizes["lw"] >= 2.5 and sel.sizes["font"] >= 9
    sel.close()


def test_markers_scale_with_width(qapp):
    narrow, wide = _lattice(qapp, 440), _lattice(qapp, 800)
    assert wide.sizes["qubit_ms"] > narrow.sizes["qubit_ms"]
    assert wide.sizes["qubit_hit_px"] > narrow.sizes["qubit_hit_px"]
    narrow.close(), wide.close()


@pytest.mark.parametrize("width", [440, 522, 800])
def test_clicks_land_on_what_is_drawn(qapp, width):
    """Centres of all three kinds, 3 px outside a qubit's edge, and the drawn area of
    every rung square (they sit between qubit columns) all resolve to their own target."""
    sel = _lattice(qapp, width)
    to_data = sel.canvas.ax.transData.inverted().transform
    to_px = sel.canvas.ax.transData.transform
    pick_px = lambda px, py: sel.pick(*to_data((px, py)))
    drawn = _drawn(sel)
    names = {v: k for k, v in sel.topo["qubits"].items()}
    rungs = {v: k for k, v in sel.topo["rungs"].items()}
    k_of = {v: (f"Q{int(k[1:])}", f"Q{int(k[1:]) + 2}") for k, v in sel.topo["couplers"].items()}

    for (pos, bb) in drawn["qubit"]:
        cx, cy = to_px(pos)
        r = bb.width / 2
        assert pick_px(cx, cy) == ("qubit", names[pos])
        for dx_, dy_ in ((1, 0), (-1, 0), (0, 1), (0, -1)):     # 3 px outside the edge
            assert pick_px(cx + dx_ * (r + 3), cy + dy_ * (r + 3)) == ("qubit", names[pos])
    for (pos, bb) in drawn["rung"]:
        cx, cy = to_px(pos)
        h = 0.8 * bb.width / 2                     # inside the drawn square, all corners
        for px, py in ((cx, cy), (cx + h, cy + h), (cx - h, cy + h),
                       (cx + h, cy - h), (cx - h, cy - h)):
            assert pick_px(px, py) == ("pair", rungs[pos]), (width, px - cx, py - cy)
    for (pos, bb) in drawn["coupler"]:
        cx, cy = to_px(pos)
        assert pick_px(cx, cy) == ("pair", k_of[pos])
    sel.close()


def test_clicking_a_rung_square_selects_its_pair(qapp):
    from types import SimpleNamespace
    sel = _lattice(qapp, 522)
    mx, my = sel.topo["rungs"][("Q4", "Q5")]
    sel._on_click(SimpleNamespace(xdata=mx, ydata=my))
    assert sel.selected() == [4, 5]
    sel._on_click(SimpleNamespace(xdata=mx, ydata=my))      # second click toggles off
    assert sel.selected() == []
    sel.close()


def test_hover_highlights_exactly_what_a_click_would_select(qapp):
    from types import SimpleNamespace
    from PyQt5.QtCore import Qt
    sel = _lattice(qapp, 522)
    for target in (("qubit", "Q3"), ("pair", ("Q4", "Q5")), ("pair", ("Q1", "Q3"))):
        if target[0] == "qubit":
            x, y = sel.topo["qubits"][target[1]]
        else:
            (x1, y1), (x2, y2) = (sel.topo["qubits"][q] for q in target[1])
            x, y = (x1 + x2) / 2, (y1 + y2) / 2
        sel._on_motion(SimpleNamespace(xdata=x, ydata=y))
        assert sel._hover == sel.pick(x, y) == target
        assert sel._ring.get_visible() and tuple(sel._ring.get_xydata()[0]) == (x, y)
        assert sel.canvas.cursor().shape() == Qt.PointingHandCursor
    sel._on_motion(SimpleNamespace(xdata=99.0, ydata=99.0))
    assert sel._hover is None and not sel._ring.get_visible()
    assert sel.canvas.cursor().shape() != Qt.PointingHandCursor
    sel.close()


def test_friendly_timestamp():
    from triangle_lattice_quench.Run_Experiments.viewer_gui.browser import friendly_timestamp
    cases = {
        "2026-10-01T14:10:00": "10/1/26 2:10pm",
        "2026-10-01T00:05:00": "10/1/26 12:05am",
        "2026-10-01T12:30:00": "10/1/26 12:30pm",
        "2026-03-04T09:07:59": "3/4/26 9:07am",
        "2026-12-31T23:59:00": "12/31/26 11:59pm",
        "2099-12-31T23:59:00": "12/31/99 11:59pm",
        "2100-01-01T00:00:00": "1/1/00 12:00am",       # %y-style rollover
        "2009-07-04T11:00:00": "7/4/09 11:00am",       # 2-digit year keeps its zero
    }
    for iso, want in cases.items():
        assert friendly_timestamp(iso) == want, (iso, friendly_timestamp(iso))
    assert friendly_timestamp("") == "" and friendly_timestamp("garbage") == "garbage"


def test_format_path_list_is_valid_python():
    import ast
    from triangle_lattice_quench.Run_Experiments.viewer_gui.browser import format_path_list
    paths = [r"Z:\QSimMeasurements\Measurements\D\T1\T1_2026_10_01\T1_2026_10_01_1_data.h5",
             'C:\\odd "quoted" name.h5', "C:\\ends\\in\\slash\\"]   # last two use repr()
    text = format_path_list(paths)
    assert text.startswith("[\n") and text.endswith(",\n]")
    assert text.splitlines()[1] == f'    r"{paths[0]}",'
    assert ast.literal_eval(text) == paths
    assert ast.literal_eval(format_path_list([])) == []


def _make_browser(qapp, tmp_path, runs):
    """BrowserWidget over ``runs`` = [(experiment, time, group_name)]; never indexes."""
    from triangle_lattice_quench.Run_Experiments.viewer_gui.browser import BrowserWidget
    dev = "8QV1_Triangle_Lattice"
    root = tmp_path / dev
    for experiment, time, group in runs:
        _write_run(root, experiment, "2026_10_01", time, [3], group)
    db = tmp_path / "b.sqlite"
    dx.scan(str(root), dev, db_path=db)
    b = BrowserWidget(db_path=db, auto_index=False)
    b.device_combo.blockSignals(True)            # no _request -> no network
    b.device_combo.setCurrentText(dev)
    b.device_combo.blockSignals(False)
    b._on_device_changed(dev, index=False)
    b.resize(1400, 800)
    b.show()
    qapp.processEvents()
    return b


@pytest.fixture
def browser(qapp, tmp_path):
    """35 T1 runs, newest first 10:00:34 .. 10:00:00, groups alternating g0/g1."""
    b = _make_browser(qapp, tmp_path, [("T1", f"10_00_{i:02d}", f"g{i % 2}")
                                       for i in range(35)])
    yield b
    b.close()
    b.conn.close()


def _path(b, r):
    from PyQt5.QtCore import Qt
    return b.table.item(r, 0).data(Qt.UserRole)


def _bold_paths(b):
    """Paths of rows whose EVERY cell is bold (and assert no row is partially bold)."""
    out = set()
    for r in range(b.table.rowCount()):
        flags = {b.table.item(r, c).font().bold() for c in range(b.table.columnCount())}
        assert len(flags) == 1, f"row {r} partially bold"
        if flags == {True}:
            out.add(_path(b, r))
    return out


def test_timestamp_is_friendly_by_default_and_toggles(browser):
    from triangle_lattice_quench.Run_Experiments.viewer_gui.browser import ISO_ROLE
    item = browser.table.item(0, 0)
    iso, path = item.data(ISO_ROLE), _path(browser, 0)
    assert iso == "2026-10-01T10:00:34"
    assert item.text() == "10/1/26 10:00am"                  # natural form by default
    assert "friendly" in browser.table.horizontalHeaderItem(0).toolTip()
    browser._on_header_clicked(0)
    assert item.text() == iso and item.data(ISO_ROLE) == iso
    assert _path(browser, 0) == path                         # row lookup unaffected
    assert "ISO" in browser.table.horizontalHeaderItem(0).toolTip()
    browser.refresh_table()                                  # repopulate keeps the format
    assert browser.table.item(0, 0).text() == iso
    browser._on_header_clicked(0)
    assert browser.table.item(0, 0).text() == "10/1/26 10:00am"


def test_right_click_toggles_and_bolds(browser, qapp):
    import ast
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    t = browser.table
    assert t.rowCount() == 35
    t.selectRow(4)
    selected_before = [i.row() for i in t.selectionModel().selectedRows()]

    def right_click(row):
        QTest.mouseClick(t.viewport(), Qt.RightButton, Qt.NoModifier,
                         t.visualItemRect(t.item(row, 1)).center())

    p0, p1, p2 = (_path(browser, r) for r in (0, 1, 2))
    right_click(2)
    right_click(0)
    right_click(1)
    assert browser.file_list == [p2, p0, p1] and _bold_paths(browser) == {p0, p1, p2}
    right_click(0)                                           # toggle OFF, others keep order
    assert browser.file_list == [p2, p1] and _bold_paths(browser) == {p1, p2}
    right_click(0)                                           # re-add appends at the end
    assert browser.file_list == [p2, p1, p0]
    assert [i.row() for i in t.selectionModel().selectedRows()] == selected_before
    assert ast.literal_eval(browser.list_text.toPlainText()) == browser.file_list

    # bold follows the PATH through a filter change and a timestamp-format toggle
    browser.filter_widgets["group_name"].setText("g1")
    browser.refresh_table()
    visible = {_path(browser, r) for r in range(t.rowCount())}
    assert t.rowCount() == 17 and _bold_paths(browser) == visible & {p0, p1, p2}
    browser._on_header_clicked(0)
    assert _bold_paths(browser) == visible & {p0, p1, p2}
    browser.filter_widgets["group_name"].setText("")
    browser.refresh_table()
    assert _bold_paths(browser) == {p0, p1, p2}


def test_add_all_bolds_exactly_the_added_rows_and_clear_unbolds(browser):
    import ast
    from PyQt5.QtWidgets import QApplication
    browser.toggle_in_list(_path(browser, 2))
    browser.toggle_in_list(_path(browser, 31))               # outside the top 30
    added = browser.add_all_to_list()                        # adds only; never toggles off
    top30 = [_path(browser, r) for r in range(30)]
    assert added == 29 and len(browser.file_list) == 31
    assert browser.file_list[:2] == [_path(browser, 2), _path(browser, 31)]
    assert _bold_paths(browser) == set(top30) | {_path(browser, 31)}
    assert _path(browser, 30) not in browser.file_list

    copy = [w for w in browser.lower.findChildren(type(browser.refresh_btn))
            if w.text() == "Copy"][0]
    copy.click()
    assert ast.literal_eval(QApplication.clipboard().text()) == browser.file_list

    browser.clear_list()
    assert browser.file_list == [] and _bold_paths(browser) == set()
    assert ast.literal_eval(browser.list_text.toPlainText()) == []
    assert browser.add_all_to_list() == 30                   # from empty: exactly 30
    assert _bold_paths(browser) == set(top30)
    assert browser.lower.tabText(0) == "File list" and browser.lower.count() == 1


def test_experiment_type_ahead(qapp, tmp_path):
    runs = [(e, f"10_00_{i:02d}", "") for i, e in enumerate(
        ["T1", "T1", "T1vsFF", "T1vsFF", "T2R", "T2R", "SpecVsFF"])]
    b = _make_browser(qapp, tmp_path, runs)
    try:
        combo = b.filter_widgets["experiment"]
        assert combo.isEditable()
        completer = combo.completer()
        completer.setCompletionPrefix("t1")                  # case-insensitive, contains
        model = completer.completionModel()
        suggestions = {model.index(i, 0).data() for i in range(model.rowCount())}
        assert {"T1", "T1vsFF"} <= suggestions and "T2R" not in suggestions
        completer.setCompletionPrefix("ff")
        model = completer.completionModel()
        assert {"T1vsFF", "SpecVsFF"} <= {model.index(i, 0).data()
                                         for i in range(model.rowCount())}

        def shown():
            b.refresh_table()
            return {b.table.item(r, 1).text() for r in range(b.table.rowCount())}

        combo.setCurrentText("t1")                           # exact, any case -> applies
        assert b._debounce.isActive()                        # typing is debounced
        assert b.current_filters()["experiment"] == "T1" and shown() == {"T1"}
        combo.setCurrentText("T1v")                          # partial -> NO filter
        assert b.current_filters()["experiment"] == dx.ANY
        assert shown() == {"T1", "T1vsFF", "T2R", "SpecVsFF"}
        combo.setCurrentText("vsf")                          # Enter takes a suggestion
        b._accept_completion(combo)
        assert combo.currentText() in {"T1vsFF", "SpecVsFF"}
        assert shown() == {combo.currentText()}
        combo.setCurrentText("")                             # cleared -> (any)
        assert b.current_filters()["experiment"] == dx.ANY and len(shown()) == 4
        combo.setCurrentText(dx.ANY)
        assert b.current_filters()["experiment"] == dx.ANY
    finally:
        b.close()
        b.conn.close()


# --------------------------------------------------------------------------- #
# style: one tunable file, zoom
# --------------------------------------------------------------------------- #

_STYLE_PROBE = """
import json, sys
from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtGui import QFontInfo
from PyQt5.QtWidgets import QApplication, QComboBox, QDateEdit, QLineEdit, QPushButton
from triangle_lattice_quench.Run_Experiments.viewer_gui import browser as br, main_window as mw
from triangle_lattice_quench.Run_Experiments.viewer_gui import style as st
br.SETTINGS_APP = mw.SETTINGS_APP = "TriangleLatticeDataViewer_PYTEST_PROBE"
QSettings(br.SETTINGS_ORG, br.SETTINGS_APP).setValue(st.SETTING_ZOOM, float(sys.argv[1]))
app = QApplication([])
win = mw.ViewerWindow(db_path=sys.argv[2], auto_index=False)
win.setAttribute(Qt.WA_DontShowOnScreen, True)          # measured, never displayed
win.resize(1500, 850)
win.show()
for _ in range(5):
    app.processEvents()
b = win.browser
heights = {}
for cls in (QPushButton, QComboBox, QLineEdit, QDateEdit):
    ws = [w for w in b.findChildren(cls) if w.isVisible()
          and not isinstance(w.parent(), (QComboBox, QDateEdit))]
    heights[cls.__name__] = min(w.height() for w in ws)
print(json.dumps({
    "platform": app.platformName(), "families": st.resolved_families(),
    "heights": heights, "row": b.table.verticalHeader().defaultSectionSize(),
    "table_pt": b.table.font().pointSizeF(),
    "header_pt": b.table.horizontalHeader().font().pointSizeF(),
    "mono": {n: [getattr(b, n).font().family(), QFontInfo(getattr(b, n).font()).fixedPitch()]
             for n in ("list_text", "config_text", "data_text")}}))
QSettings(br.SETTINGS_ORG, br.SETTINGS_APP).clear()
"""


@pytest.mark.skipif(sys.platform != "win32", reason="fonts need the real Windows platform")
@pytest.mark.parametrize("zoom", [1.0, 1.5])
def test_control_and_row_sizes_follow_zoom(zoom, tmp_path):
    """Run on the REAL windows platform (offscreen has no font database), hidden."""
    from triangle_lattice_quench.Run_Experiments.viewer_gui import style as st
    env = dict(os.environ, QT_QPA_PLATFORM="windows", MPLBACKEND="Agg",
               PYTHONPATH=str(WORKING_PROJECTS))
    out = subprocess.run([sys.executable, "-c", _STYLE_PROBE, str(zoom),
                          str(tmp_path / "s.sqlite")], cwd=str(WORKING_PROJECTS), env=env,
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    m = json.loads(out.stdout.strip().splitlines()[-1])
    assert m["platform"] == "windows"
    floor = round(st.CONTROL_MIN_H * zoom)
    assert all(h >= floor for h in m["heights"].values()), (zoom, m["heights"])
    assert m["row"] == round(st.ROW_H * zoom)
    assert abs(m["table_pt"] - st.BASE_PT * zoom) < 0.05
    assert abs(m["header_pt"] - st.BASE_PT * zoom) < 0.05
    assert m["families"]["mono"] in st.MONO_FAMILIES
    for name, (family, fixed) in m["mono"].items():
        assert family == m["families"]["mono"] and fixed, name


def test_zoom_clamps_and_is_remembered(qapp, tmp_path):
    from PyQt5.QtCore import QSettings
    from triangle_lattice_quench.Run_Experiments.viewer_gui import browser as br, style as st
    from triangle_lattice_quench.Run_Experiments.viewer_gui.main_window import ViewerWindow
    win = ViewerWindow(db_path=tmp_path / "z.sqlite", auto_index=False)
    assert win.set_zoom(5.0) == 2.0 and win.set_zoom(0.1) == 0.8
    assert win.set_zoom(1.23) == 1.2 and st.current_scale() == 1.2
    for _ in range(10):
        win.set_zoom(st.current_scale() + st.ZOOM_STEP)      # what Ctrl+= does
    assert st.current_scale() == 2.0
    assert QSettings(br.SETTINGS_ORG, br.SETTINGS_APP).value(st.SETTING_ZOOM, type=float) == 2.0
    win.close()
    again = ViewerWindow(db_path=tmp_path / "z.sqlite", auto_index=False)
    assert st.current_scale() == 2.0                         # remembered
    again.set_zoom(st.ZOOM_DEFAULT)                          # Ctrl+0
    assert st.current_scale() == 1.0
    again.close()


# --------------------------------------------------------------------------- #
# saving takes precedence over viewing (real two-process tests, temp dir only)
# --------------------------------------------------------------------------- #

_WRITER = """
import os, sys, time, h5py
f = h5py.File(sys.argv[1], "a")          # what ExperimentClass.datafile() does
print("held", flush=True)
deadline = time.time() + 60
while not os.path.exists(sys.argv[2]) and time.time() < deadline:
    time.sleep(0.05)
f.attrs["written_while_viewer_looked"] = 1
f.close()
print("saved", flush=True)
"""


def _writer_env():
    # The experiment process is a NORMAL h5py user: default HDF5 locking, which the
    # viewer's own HDF5_USE_FILE_LOCKING=FALSE (inherited via os.environ) must not mask.
    env = dict(os.environ)
    env.pop("HDF5_USE_FILE_LOCKING", None)
    return env


def test_a_file_being_saved_is_skipped_everywhere_and_indexed_after(qapp, tmp_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from triangle_lattice_quench.Run_Experiments.viewer_gui.browser import BrowserWidget
    from triangle_lattice_quench.Run_Experiments.viewer_gui import replot

    root = tmp_path / "D"
    path = _write_run(root, "T1", "2026_10_01", "11_00_00", [3, 5], "calib", "t1")
    release = tmp_path / "release"
    proc = subprocess.Popen([sys.executable, "-c", _WRITER, str(path), str(release)],
                            stdout=subprocess.PIPE, text=True, env=_writer_env())
    try:
        assert proc.stdout.readline().strip() == "held"
        db = tmp_path / "busy.sqlite"
        stats = dx.scan(str(root), "D", db_path=db)
        assert stats["busy"] == 1 and stats["indexed"] == 0 and stats["failed"] == 0
        conn = dx.connect(db)
        assert conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0   # NO row
        assert conn.execute("SELECT indexed FROM day_folders WHERE date='2026-10-01'"
                            ).fetchone()[0] == 0                    # folder stays retryable
        conn.close()

        b = BrowserWidget(db_path=tmp_path / "ui.sqlite", auto_index=False)
        b._load_datasets(str(path))
        assert b.data_tree.topLevelItem(0).text(0) == dx.BUSY_MESSAGE
        b._load_config(str(path))
        assert b.config_text.toPlainText() == dx.BUSY_MESSAGE
        b._path, b._datasets = str(path), {"x_pts": {"nbytes": 32}}
        item = type(b.data_tree.topLevelItem(0))(b.data_tree, ["x_pts", "", "", ""])
        b._on_dataset_clicked(item, 0)
        assert b.data_text.toPlainText() == dx.BUSY_MESSAGE
        fig, ax = plt.subplots()
        assert replot.replot_into(str(path), ax) == dx.BUSY_MESSAGE
        plt.close(fig)
        assert b._busy                                       # a re-click will retry
    finally:
        release.touch()
        out, _ = proc.communicate(timeout=60)
    assert proc.returncode == 0 and "saved" in out

    stats = dx.scan(str(root), "D", db_path=db)               # next pass: indexed, w/ meta
    assert stats["busy"] == 0 and stats["indexed"] == 1
    rows, _ = dx.query({}, "D", db_path=db)
    assert rows[0]["has_meta"] == 1 and json.loads(rows[0]["qubits"]) == [3, 5]
    b._load_datasets(str(path))                               # and the panes work now
    assert b.data_tree.topLevelItem(0).text(0) != dx.BUSY_MESSAGE
    b._load_config(str(path))
    assert json.loads(b.config_text.toPlainText())["Qubit_Readout_List"] == [3, 5]
    b.close()
    b.conn.close()


def test_a_viewer_open_never_blocks_a_save(tmp_path):
    from triangle_lattice_quench.Experiment import open_for_reading
    path = _write_run(tmp_path / "D", "T1", "2026_10_01", "12_00_00", [3])
    release = tmp_path / "release"
    release.touch()                                           # writer saves immediately
    with open_for_reading(str(path)) as f:                    # viewer holds it open...
        assert "Experiment" in f.attrs
        out = subprocess.run([sys.executable, "-c", _WRITER, str(path), str(release)],
                             capture_output=True, text=True, env=_writer_env(), timeout=60)
    assert out.returncode == 0 and "saved" in out.stdout, out.stderr   # ...save succeeded
    with open_for_reading(str(path)) as f:
        assert f.attrs["written_while_viewer_looked"] == 1


def test_a_file_indexed_before_its_metadata_heals_on_the_next_pass(tmp_path):
    """The gap between save_data -> save_metadata: index the file attr-less, then let the
    metadata land; the mtime change makes the next pass re-index it."""
    import time
    import h5py
    folder = tmp_path / "D" / "T1" / "T1_2026_10_01"
    folder.mkdir(parents=True)
    path = folder / "T1_2026_10_01_13_00_00_data.h5"
    with h5py.File(path, "w") as f:                           # save_data's part only
        f.create_group("data").create_dataset("x_pts", data=[0.0, 1.0])
    db = tmp_path / "gap.sqlite"
    dx.scan(str(tmp_path / "D"), "D", db_path=db)
    rows, _ = dx.query({}, "D", db_path=db)
    assert rows[0]["has_meta"] == 0 and rows[0]["qubits"] is None

    time.sleep(0.05)
    expt = T1.__new__(T1)                               # ...then save_metadata lands
    expt.fname, expt.start_time, expt.day_folder = str(path), "2026-10-01T13:00:00", folder.name
    expt.day = folder.name[-10:]
    expt.cfg = {"Qubit_Readout_List": [4], "meta": {"group_name": "late"}}
    expt.save_metadata({"data": {"Qubit_Readout_List": [4]}})

    conn = dx.connect(db)
    dx.refresh(str(tmp_path / "D"), "D", conn)                # an ordinary refresh
    conn.close()
    rows, _ = dx.query({}, "D", db_path=db)
    assert rows[0]["has_meta"] == 1 and json.loads(rows[0]["qubits"]) == [4]
    assert rows[0]["group_name"] == "late"


# --------------------------------------------------------------------------- #
# replot safety: the archived png must never be rewritten
# --------------------------------------------------------------------------- #

def test_replot_draws_into_ax_and_leaves_the_archived_png_untouched(tmp_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from triangle_lattice_quench.Run_Experiments.viewer_gui import replot

    h5 = _write_run(tmp_path / "FakeDevice", "T1", "2026_10_01", "11_00_00",
                    [3], "calib", "t1")
    png = Path(str(h5)[:-3] + ".png")
    png.write_bytes(b"ARCHIVED-PNG-SENTINEL")
    before = (png.read_bytes(), png.stat().st_mtime_ns)

    pattern = os.path.join(tempfile.gettempdir(), "viewer_replot_*")
    dirs_before = set(glob.glob(pattern))

    fig, ax = plt.subplots()
    message = replot.replot_into(str(h5), ax)
    plt.close(fig)

    assert message.startswith("replotted T1"), message
    assert ax.lines, "display() must actually have drawn into the viewer axis"
    # The savefig inside display() went to a fresh temp dir, not next to the data.
    new_dirs = set(glob.glob(pattern)) - dirs_before
    assert new_dirs and any(list(Path(d).glob("*.png")) for d in new_dirs)
    assert (png.read_bytes(), png.stat().st_mtime_ns) == before


def test_experiment_folder_and_class_are_kept_separate(tmp_path):
    """Folder 'T2R' (ExperimentClass.path) and class 'T2RMUX' (the attr) are different
    strings; the index records both rather than merging them."""
    class T2RMUX(ExperimentClass):
        pass

    root = tmp_path / "S"
    _write_run(root, "T2R", "2026_10_01", "10_00_00", [3], cls=T2RMUX)     # folder T2R
    _write_run(root, "T2R", "2025_01_01", "10_00_00", [3], cls=T2RMUX)     # pre-cutover
    db = tmp_path / "s.sqlite"
    dx.scan(str(root), "S", db_path=db)
    conn = dx.connect(db)
    rows, total = dx.query({"experiment": "T2R"}, "S", conn=conn)
    assert total == 2                                      # both, via the folder name
    assert sorted((r["experiment"], r["experiment_class"] or "") for r in rows) == [
        ("T2R", ""), ("T2R", "T2RMUX")]
    assert dx.distinct("experiment", "S", conn=conn) == ["T2R"]
    conn.close()


def test_replot_guesses_the_class_from_the_folder_when_the_attr_is_missing(tmp_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import h5py
    from triangle_lattice_quench.Run_Experiments.viewer_gui import replot

    # Folder 'T1' resolves to exactly one ExperimentClass subclass -> offered as a
    # labelled guess.
    h5 = _write_run(tmp_path / "G", "T1", "2026_10_01", "11_00_00", [3])
    with h5py.File(h5, "a") as f:
        del f.attrs["Experiment"]
    fig, ax = plt.subplots()
    message = replot.replot_into(str(h5), ax)
    plt.close(fig)
    assert "GUESS" in message and "inferred from folder 'T1'" in message
    assert message.startswith("replotted T1") and ax.lines

    # A folder matching no class must NOT guess.
    h5b = _write_run(tmp_path / "G", "NoSuchExperiment", "2026_10_01", "11_00_00", [3])
    with h5py.File(h5b, "a") as f:
        del f.attrs["Experiment"]
    fig, ax = plt.subplots()
    message = replot.replot_into(str(h5b), ax)
    plt.close(fig)
    assert "matches 0 experiment classes" in message and not ax.lines


def test_replot_refuses_files_without_an_experiment_attr(tmp_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import h5py
    from triangle_lattice_quench.Run_Experiments.viewer_gui import replot

    path = tmp_path / "bare.h5"
    with h5py.File(path, "w") as f:
        f.create_dataset("x", data=[1, 2, 3])
    fig, ax = plt.subplots()
    assert "no 'Experiment' attr" in replot.replot_into(str(path), ax)
    plt.close(fig)


# --------------------------------------------------------------------------- #
# independence: builds with qick blocked, and never imports it when present
# --------------------------------------------------------------------------- #

def _run_subprocess(script: str, *args) -> subprocess.CompletedProcess:
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", MPLBACKEND="Agg",
               PYTHONPATH=str(WORKING_PROJECTS))
    return subprocess.run([sys.executable, "-c", textwrap.dedent(script), *args],
                          cwd=str(WORKING_PROJECTS), env=env, capture_output=True,
                          text=True, timeout=300)


_NO_QICK = """
    import sys
    class _BlockQick:
        def find_spec(self, name, path=None, target=None):
            if name == "qick" or name.startswith("qick."):
                raise ImportError("qick blocked for this test")
            return None
    sys.meta_path.insert(0, _BlockQick())
    try:
        import qick
        print("FAIL: qick imported despite the block"); raise SystemExit(1)
    except ImportError:
        pass

    from PyQt5.QtWidgets import QApplication
    from triangle_lattice_quench.Run_Experiments.viewer_gui.main_window import ViewerWindow
    from triangle_lattice_quench.Run_Experiments.viewer_gui import replot
    app = QApplication([])
    win = ViewerWindow(db_path=sys.argv[1], auto_index=False)
    print("window built:", win.windowTitle())
    print("devices:", win.browser.device_combo.count())
    print("panes:", [win.browser.right.tabText(i) for i in range(win.browser.right.count())])
    print("lattice qubits:", len(win.browser.lattice.topo["qubits"]))
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    print("replot says:", replot.replot_into(sys.argv[2], ax))
    print("OK")
"""

_NO_HARDWARE_IMPORTS = """
    import sys
    from PyQt5.QtWidgets import QApplication
    from triangle_lattice_quench.Run_Experiments.viewer_gui.main_window import ViewerWindow
    app = QApplication([])
    win = ViewerWindow(db_path=sys.argv[1], auto_index=False)
    leaked = [m for m in sys.modules
              if m == "qick" or m.startswith("qick.")
              or "calibration_gui" in m or m.endswith("MUXInitialize")
              or m.endswith("build_config") or m.endswith("socProxy")]
    print("leaked modules:", leaked)
    assert not leaked, leaked
    print("OK")
"""


def test_builds_with_qick_blocked(tmp_path):
    h5 = _write_run(tmp_path / "FakeDevice", "T1", "2026_10_01", "11_00_00", [3])
    out = _run_subprocess(_NO_QICK, str(tmp_path / "v.sqlite"), str(h5))
    assert out.returncode == 0, out.stdout + out.stderr
    assert "OK" in out.stdout, out.stdout + out.stderr
    assert "qick not installed" in out.stdout, out.stdout


def test_window_never_imports_qick_or_calibration_gui(tmp_path):
    out = _run_subprocess(_NO_HARDWARE_IMPORTS, str(tmp_path / "v.sqlite"))
    assert out.returncode == 0, out.stdout + out.stderr
    assert "leaked modules: []" in out.stdout, out.stdout


# --------------------------------------------------------------------------- #
# the cache follows the share: ignored folders, pruning, and the offline guard
# --------------------------------------------------------------------------- #

def _counts(conn, device):
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t} WHERE device=?", (device,)).fetchone()[0]
            for t in ("expt_folders", "day_folders", "files")}


def _experiments(conn, device):
    return {r[0] for t in ("expt_folders", "day_folders", "files")
            for r in conn.execute(f"SELECT DISTINCT experiment FROM {t} WHERE device=?",
                                  (device,))}


@pytest.fixture
def share(tmp_path):
    """Experiments + two top-level PNAX scan folders (undated subfolders) + an _IIR
    folder of CSVs -- the share as it was before the user moved PNAX under _PNAX."""
    import h5py
    root = tmp_path / "D"
    runs = {
        "t1_new": _write_run(root, "T1", "2026_10_01", "11_00_00", [3]),
        "t1_new2": _write_run(root, "T1", "2026_10_01", "11_05_00", [3]),
        "t1_old": _write_run(root, "T1", "2025_01_05", "08_00_00", [4]),
        "t2r": _write_run(root, "T2R", "2026_09_30", "09_00_00", [5]),
    }
    for pnax in ("pnax061025", "pnax071125"):
        for k in range(2):
            scan = root / pnax / f"InitialCrosstalk8Qubit_Tri_20250610_18{k:02d}"
            scan.mkdir(parents=True)
            with h5py.File(scan / "trace.h5", "w") as f:
                f.create_dataset("s21", data=[1.0, 2.0])
    iir = root / "_IIR_PulseCompensations"
    iir.mkdir()
    (iir / "Q1_iir.csv").write_text("a,b\n1,2\n")
    return {"root": root, "db": tmp_path / "share.sqlite", **runs}


def test_moved_pnax_and_deleted_files_are_pruned(share):
    import shutil
    root, dev = share["root"], "D"
    conn = dx.connect(share["db"])
    dx.open_device(str(root), dev, conn)                       # cold: tier 0 + tier 1
    assert {"pnax061025", "pnax071125"} <= _experiments(conn, dev)
    assert "_IIR_PulseCompensations" not in _experiments(conn, dev)   # ignored from the start
    hz = dx.horizon(dev, {}, conn=conn)
    assert hz["undated_unindexed"] == 4 and not hz["complete"]          # the user's symptom

    # A cache written by the OLD code also listed the _IIR folder as an experiment.
    iir = str(root / "_IIR_PulseCompensations")
    conn.execute("INSERT INTO expt_folders VALUES (?,?,?,?)", (iir, dev, "_IIR_PulseCompensations", 0.0))
    conn.execute("INSERT INTO day_folders(path, device, experiment, date, mtime, recursive, indexed,"
                 " n_files) VALUES (?,?,?,NULL,0,1,0,0)", (iir + "\\x", dev, "_IIR_PulseCompensations"))
    conn.commit()

    # The user's move, plus one file deleted inside a still-existing day folder.
    (root / "_PNAX").mkdir()
    for pnax in ("pnax061025", "pnax071125"):
        shutil.move(str(root / pnax), str(root / "_PNAX" / pnax))
    os.remove(share["t1_new2"])

    stats = dx.refresh(str(root), dev, conn)                   # ordinary warm refresh
    assert not stats["unreachable"] and stats["pruned_experiments"] == 3
    names = _experiments(conn, dev)
    assert names == {"T1", "T2R"}                           # no pnax*, no _PNAX, no _IIR*
    assert not any(n.startswith("_") for n in dx.distinct("experiment", dev, table="day_folders",
                                                           conn=conn))
    paths = {r[0] for r in conn.execute("SELECT path FROM files")}
    assert str(share["t1_new2"]) not in paths and str(share["t1_new"]) in paths
    hz = dx.horizon(dev, {}, conn=conn)
    assert hz["complete"] and hz["undated_unindexed"] == 0

    # Tier 2 ("Index all") honours the same choke point: nothing under _PNAX is indexed.
    dx.index_all(str(root), dev, conn)
    assert not any("_PNAX" in p for p in (r[0] for r in conn.execute("SELECT path FROM files")))
    # (c) an OLD day folder outside the recency window is pruned by the full pass
    os.remove(share["t1_old"])
    dx.index_all(str(root), dev, conn)
    assert str(share["t1_old"]) not in {r[0] for r in conn.execute("SELECT path FROM files")}
    conn.close()


def test_removed_day_folder_is_pruned_when_its_experiment_is_relisted(share):
    import shutil
    root, dev = share["root"], "D"
    conn = dx.connect(share["db"])
    dx.open_device(str(root), dev, conn)
    gone_day = str(root / "T2R" / "T2R_2026_09_30")
    shutil.rmtree(gone_day)
    stats = dx.refresh(str(root), dev, conn)                    # T2R is recently active
    assert stats["pruned_days"] >= 1
    assert conn.execute("SELECT COUNT(*) FROM day_folders WHERE path=?", (gone_day,)).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM files WHERE day_path=?", (gone_day,)).fetchone()[0] == 0
    conn.close()


def test_an_unreachable_root_leaves_the_cache_identical(share, monkeypatch):
    root, dev = share["root"], "D"
    conn = dx.connect(share["db"])
    dx.open_device(str(root), dev, conn)
    before = _counts(conn, dev)
    assert all(before.values())

    missing = str(share["root"].parent / "not_mounted" / "D")   # nonexistent path
    for run in (lambda: dx.refresh(missing, dev, conn), lambda: dx.open_device(missing, dev, conn),
                lambda: dx.index_all(missing, dev, conn)):
        assert run()["unreachable"] is True
        assert _counts(conn, dev) == before

    real_scandir = os.scandir                                  # the share drops mid-session

    def offline(path):
        raise OSError("network name is no longer available")
    monkeypatch.setattr(os, "scandir", offline)
    assert dx.refresh(str(root), dev, conn)["unreachable"] is True
    assert dx.index_all(str(root), dev, conn)["unreachable"] is True
    assert _counts(conn, dev) == before
    monkeypatch.setattr(os, "scandir", real_scandir)
    conn.close()


def test_a_failed_experiment_or_day_listing_prunes_nothing(share, monkeypatch):
    root, dev = share["root"], "D"
    conn = dx.connect(share["db"])
    dx.open_device(str(root), dev, conn)
    before = _counts(conn, dev)
    t1 = str(root / "T1")
    real = dx._list_dir

    # every listing at or below T1 fails; the root and T2R still list fine
    monkeypatch.setattr(dx, "_list_dir",
                        lambda path: None if str(path).startswith(t1) else real(path))
    stats = dx.refresh(str(root), dev, conn)
    assert not stats["unreachable"] and stats["relist_failed"] >= 1
    assert _counts(conn, dev) == before                        # T1 rows all kept
    t1_files = {r[0] for r in conn.execute("SELECT path FROM files WHERE experiment='T1'")}
    stats = dx.index_all(str(root), dev, conn)                  # the day-folder level too
    assert stats["relist_failed"] >= 1
    # tier 2 may ADD rows elsewhere (the undated pnax traces) but deletes nothing of T1
    after = {r[0] for r in conn.execute("SELECT path FROM files WHERE experiment='T1'")}
    assert after == t1_files and len(after) == 3
    conn.close()


def test_status_line_says_the_share_is_unreachable(qapp, tmp_path):
    from triangle_lattice_quench.Run_Experiments.viewer_gui.browser import (
        BrowserWidget, IndexWorker)
    seen = []
    worker = IndexWorker(str(tmp_path / "not_mounted"), "D", db_path=tmp_path / "w.sqlite")
    worker.unavailable.connect(seen.append)
    worker.run()                                               # synchronous: no thread
    assert seen and seen[0].startswith(dx.UNREACHABLE_MESSAGE)
    b = BrowserWidget(db_path=tmp_path / "w.sqlite", auto_index=False)
    b._on_index_done({**dx._new_stats(), "unreachable": True})
    assert b.status_label.text() == dx.UNREACHABLE_MESSAGE
    b._on_index_unavailable(seen[0])
    assert dx.UNREACHABLE_MESSAGE in b.status_label.text()
    b.close()
    b.conn.close()


_WRITER_DIRTY = """
import os, sys, time, h5py
f = h5py.File(sys.argv[1], "a")          # an experiment mid-save: new bytes, still open
f.attrs["mid_save"] = 1
f.flush()
print("held", flush=True)
deadline = time.time() + 60
while not os.path.exists(sys.argv[2]) and time.time() < deadline:
    time.sleep(0.05)
f.close()
print("saved", flush=True)
"""


def test_a_busy_file_survives_a_prune_pass(share):
    root, dev = share["root"], "D"
    conn = dx.connect(share["db"])
    dx.open_device(str(root), dev, conn)
    target = str(share["t1_new"])
    assert conn.execute("SELECT COUNT(*) FROM files WHERE path=?", (target,)).fetchone()[0] == 1
    release = share["root"].parent / "release"
    proc = subprocess.Popen([sys.executable, "-c", _WRITER_DIRTY, target, str(release)],
                            stdout=subprocess.PIPE, text=True, env=_writer_env())
    has_row = lambda: conn.execute("SELECT COUNT(*) FROM files WHERE path=?",
                                   (target,)).fetchone()[0] == 1
    try:
        assert proc.stdout.readline().strip() == "held"
        # (a) While held open, NTFS keeps the OLD mtime in the directory listing (it is
        #     updated on close), so the file reads as unchanged: skipped, row kept.
        stats = dx.refresh(str(root), dev, conn)
        assert stats["busy"] == 0 and has_row()
        # (b) A file due for a retry IS opened, refused as busy -- and still not pruned.
        for run in (lambda: dx.refresh(str(root), dev, conn), lambda: dx.index_all(str(root), dev, conn)):
            conn.execute("UPDATE files SET mtime=NULL WHERE path=?", (target,))
            conn.commit()
            stats = run()
            assert stats["busy"] == 1 and has_row()
    finally:
        release.touch()
        out, _ = proc.communicate(timeout=60)
    assert proc.returncode == 0 and "saved" in out
    stats = dx.refresh(str(root), dev, conn)                    # after the save closes
    assert stats["busy"] == 0 and has_row()
    mtime = conn.execute("SELECT mtime FROM files WHERE path=?", (target,)).fetchone()[0]
    assert mtime == os.stat(target).st_mtime                   # re-indexed at the new mtime
    conn.close()


def test_connect_refuses_a_missing_directory(tmp_path):
    bad = tmp_path / "typo_dir" / "nested" / "index.sqlite"
    with pytest.raises(FileNotFoundError, match="does not exist"):
        dx.connect(bad)
    assert not (tmp_path / "typo_dir").exists()                # nothing was created
    ok = dx.connect(tmp_path / "fine.sqlite")                   # existing dir: fine
    ok.close()


# --------------------------------------------------------------------------- #
# qubit digits sit centred on their circles
# --------------------------------------------------------------------------- #

def _digit_offsets(sel):
    """Mean (dx, dy) px of each digit's ink centroid from its DRAWN circle centre.

    Everything but the circles and digits is hidden on a black figure, so the circle
    centre is the centroid of the binary disk mask (which contains its digit uniformly:
    neither digit shape nor marker pixel-snapping biases it). dy > 0 = digit sits high."""
    import numpy as np
    from matplotlib.colors import to_rgb
    from triangle_lattice_quench.Run_Experiments.viewer_gui import style as st
    c, ax = sel.canvas, sel.canvas.ax
    hidden = [a for a in ax.lines if not (a.get_marker() == "o" and a.get_mfc() != "none")
              and a.get_visible()]
    for a in hidden:
        a.set_visible(False)
    face0 = c.fig.get_facecolor()
    c.fig.set_facecolor("black")
    c.draw()
    buf = np.asarray(c.buffer_rgba())[:, :, :3].astype(float) / 255.0
    c.fig.set_facecolor(face0)
    for a in hidden:
        a.set_visible(True)
    c.draw()
    H, W = buf.shape[:2]
    jj, ii = np.meshgrid(np.arange(W) + 0.5, H - np.arange(H) - 0.5)
    r_px = sel.sizes["qubit_ms"] / 2 * c.fig.dpi / 72
    lit = buf.max(axis=2) > 0.2
    texts = {t.get_text(): t for t in ax.texts}
    dxs, dys = [], []
    for name, pos in sel.topo["qubits"].items():
        mx, my = ax.transData.transform(pos)
        disk = lit & ((jj - mx) ** 2 + (ii - my) ** 2 <= (1.3 * r_px) ** 2)
        cx, cy = jj[disk].mean(), ii[disk].mean()
        face = np.array(to_rgb(st.QUBIT["face_on" if name in sel._selected else "face"]))
        ink = np.array(to_rgb(texts[name[1:]].get_color()))
        d = ink - face
        inside = (jj - cx) ** 2 + (ii - cy) ** 2 <= (0.72 * r_px) ** 2
        w = np.clip(((buf - face) @ d) / (d @ d), 0, 1) * inside
        dxs.append((w * jj).sum() / w.sum() - cx)
        dys.append((w * ii).sum() / w.sum() - cy)
    return float(np.mean(dxs)), float(np.mean(dys))


@pytest.mark.parametrize("zoom", [1.0, 1.5])
@pytest.mark.parametrize("width", [440, 540, 800])
def test_qubit_digits_are_centred(qapp, width, zoom):
    from triangle_lattice_quench.Run_Experiments.viewer_gui import style as st
    st.apply_style(qapp, zoom)                  # reset to 1.0 by the autouse fixture
    sel = _lattice(qapp, width)
    for selected in (set(), set(sel.topo["qubits"])):        # maroon-on-white, white-on-red
        sel.set_selected(selected)
        dx_, dy_ = _digit_offsets(sel)
        assert abs(dy_) <= 0.7 and abs(dx_) < 1.0, (width, zoom, bool(selected), dx_, dy_)
    # the offset moves the digits only: hover ring and click radii still use the centre
    x, y = sel.topo["qubits"]["Q3"]
    assert sel.pick(x, y) == ("qubit", "Q3")
    sel._set_hover(("qubit", "Q3"))
    assert tuple(sel._ring.get_xydata()[0]) == (x, y)
    sel.close()


# --------------------------------------------------------------------------- #
# qubit info for legacy files: the empty-state note and the lazy, budgeted lookup
# --------------------------------------------------------------------------- #

LEGACY_DAY = "2025_06_01"                       # before the cutover: never opened by indexing


def _legacy_tree(tmp_path, spec):
    """spec = [(experiment, qubits), ...] -> legacy runs (config attr holds the list)."""
    root = tmp_path / "L"
    paths = []
    for i, (experiment, qubits) in enumerate(spec):
        paths.append(_write_run(root, experiment, LEGACY_DAY, f"10_{i // 60:02d}_{i % 60:02d}",
                                qubits))
    db = tmp_path / "legacy.sqlite"
    dx.scan(str(root), "L", db_path=db)
    return root, db, paths


@pytest.fixture
def counting_reader(monkeypatch):
    """Count every config read the lazy lookup does (the real reader underneath)."""
    opened = []
    real = dx.read_config_qubits

    def reader(path):
        opened.append(path)
        return real(path)
    monkeypatch.setattr(dx, "read_config_qubits", reader)
    return opened


def _q(qubits, mode="="):
    return {"qubits": {"mode": mode, "qubits": list(qubits)}}


def test_note_counts_only_runs_the_qubit_filter_cannot_judge(tmp_path):
    root, db, _ = _legacy_tree(tmp_path, [("T2R", [3])] * 4 + [("T1", [3])] * 3)
    _write_run(root, "T2R", "2026_10_01", "12_00_00", [3])      # one NEW run with metadata
    dx.scan(str(root), "L", db_path=db)
    conn = dx.connect(db)
    rows = conn.execute("SELECT has_meta, qubits FROM files").fetchall()
    assert sum(r[0] for r in rows) == 1                          # only the new run
    # legacy rows: indexed but never opened, so qubit info is unknown
    assert dx.qubit_unknown_counts(_q([3]), "L", conn) == {"unchecked": 7, "unavailable": 0}
    assert dx.qubit_unknown_counts({**_q([3]), "experiment": "T2R"}, "L", conn)["unchecked"] == 4
    assert dx.query(_q([3]), "L", conn=conn)[1] == 1             # only the new run matches
    assert not dx.qubit_filter_active({})
    conn.close()


def test_lazy_pass_respects_other_filters_budget_and_continuation(tmp_path, counting_reader):
    root, db, paths = _legacy_tree(tmp_path, [("T2R", [3])] * 12 + [("T1", [3])] * 5)
    conn = dx.connect(db)
    values = {**_q([3]), "experiment": "T2R"}
    assert dx.lazy_qubit_pass({"experiment": "T2R"}, "L", conn)["active"] is False
    assert counting_reader == []                                  # no qubit filter: no reads

    s1 = dx.lazy_qubit_pass(values, "L", conn, budget=5)
    assert s1["opened"] == 5 and s1["remaining"] == 7 and not s1["complete"]
    assert all("\\T2R\\" in p for p in counting_reader)          # T1 rows never opened
    newest5 = [r[0] for r in conn.execute(
        "SELECT path FROM files WHERE experiment='T2R' ORDER BY timestamp DESC LIMIT 5")]
    assert counting_reader == newest5                             # newest first
    s2 = dx.lazy_qubit_pass(values, "L", conn, budget=5)          # "Read more"
    assert s2["opened"] == 5 and len(set(counting_reader)) == 10
    s3 = dx.lazy_qubit_pass(values, "L", conn, budget=5)
    assert s3["opened"] == 2 and s3["complete"] and s3["remaining"] == 0
    assert dx.query(values, "L", conn=conn)[1] == 12             # all found via config
    before = len(counting_reader)
    assert dx.lazy_qubit_pass(values, "L", conn, budget=5)["opened"] == 0   # identical query
    assert len(counting_reader) == before
    rows = dx.query(values, "L", conn=conn)[0]
    assert {r["qubit_source"] for r in rows} == {"config"}
    conn.close()


def test_lazy_pass_stops_early_once_the_table_is_full(tmp_path, counting_reader):
    root, db, _ = _legacy_tree(tmp_path, [("T2R", [3])] * 10)
    conn = dx.connect(db)
    stats = dx.lazy_qubit_pass(_q([3]), "L", conn, budget=100, row_cap=3)
    assert stats["opened"] == 3 and stats["matched"] == 3 and stats["table_full"]
    assert not stats["complete"] and stats["remaining"] == 7
    conn.close()


def test_matches_appear_progressively(tmp_path):
    root, db, _ = _legacy_tree(tmp_path, [("T2R", [3])] * 6)
    conn = dx.connect(db)
    other = dx.connect(db)                                        # the GUI's connection
    seen = []
    dx.lazy_qubit_pass(_q([3]), "L", conn, budget=100, commit_every=1,
                       progress_cb=lambda s: seen.append(
                           (s["matched"], dx.query(_q([3]), "L", conn=other)[1])))
    matched = [m for m, _ in seen]
    assert matched == sorted(matched) and matched[-1] == 6
    assert all(m == visible for m, visible in seen)               # visible as soon as found
    conn.close()
    other.close()


def test_sentinels_and_missing_files(tmp_path, counting_reader):
    import h5py
    root, db, paths = _legacy_tree(tmp_path, [("T2R", [3])] * 3)
    with h5py.File(paths[0], "a") as f:                           # config without the key
        f.attrs["config"] = json.dumps({"something_else": 1})
    paths[1].write_bytes(b"this is not an hdf5 file")             # corrupt
    os.utime(paths[1], None)
    conn = dx.connect(db)
    conn.execute("UPDATE files SET mtime=0")                      # keep the index's rows as-is
    conn.commit()
    os.remove(paths[2])                                           # vanished since indexing
    stats = dx.lazy_qubit_pass(_q([3]), "L", conn, budget=100)
    assert stats["opened"] == 3 and stats["unavailable"] == 2 and stats["missing"] == 1
    src = {r[0]: r[1] for r in conn.execute("SELECT path, qubit_source FROM files")}
    assert src[str(paths[0])] == src[str(paths[1])] == dx.SOURCE_UNAVAILABLE
    assert src[str(paths[2])] is None                             # missing: no sentinel
    n = len(counting_reader)
    again = dx.lazy_qubit_pass(_q([3]), "L", conn, budget=100)
    assert len(counting_reader) - n == 1 and again["missing"] == 1   # sentinels never re-read
    counts = dx.qubit_unknown_counts(_q([3]), "L", conn)
    assert counts == {"unchecked": 1, "unavailable": 2}
    conn.close()


@pytest.mark.parametrize("mode,want", [("=", [[3, 5]]), ("⊇", [[3], [3, 5], [5]]),
                                       ("⊆", [[3, 4, 5], [3, 5]])])
def test_match_modes_on_config_sourced_lists(tmp_path, mode, want):
    root, db, _ = _legacy_tree(tmp_path, [("T2R", q) for q in
                                          ([3], [5], [3, 4], [3, 5], [3, 4, 5], ["Q3", "5"])])
    conn = dx.connect(db)
    dx.lazy_qubit_pass(_q([3, 5], mode), "L", conn, budget=100)
    rows = dx.query(_q([3, 5], mode), "L", conn=conn)[0]
    got = sorted(sorted(dx.qubit_label(v) for v in json.loads(r["qubits"])) for r in rows)
    # ["Q3", "5"] normalises to {3, 5}: it joins the [3, 5] bucket
    expect = sorted(want + ([[3, 5]] if [3, 5] in want else []))
    assert got == expect and all(r["qubit_source"] == "config" for r in rows)
    conn.close()


def test_busy_legacy_file_is_skipped_and_retried(tmp_path):
    root, db, paths = _legacy_tree(tmp_path, [("T2R", [6])])
    target, release = str(paths[0]), tmp_path / "release"
    conn = dx.connect(db)
    proc = subprocess.Popen([sys.executable, "-c", _WRITER, target, str(release)],
                            stdout=subprocess.PIPE, text=True, env=_writer_env())
    try:
        assert proc.stdout.readline().strip() == "held"
        stats = dx.lazy_qubit_pass(_q([6]), "L", conn, budget=10)
        assert stats["busy"] == 1 and stats["unavailable"] == 0
        assert conn.execute("SELECT qubit_source FROM files").fetchone()[0] is None
        assert conn.execute("SELECT COUNT(*) FROM qubit_memo").fetchone()[0] == 0
    finally:
        release.touch()
        proc.communicate(timeout=60)
    stats = dx.lazy_qubit_pass(_q([6]), "L", conn, budget=10)     # retried, now readable
    assert stats["found"] == 1 and stats["matched"] == 1
    conn.close()


def test_memo_survives_reset_and_only_changed_files_are_reread(tmp_path, counting_reader):
    import h5py
    import time as _time
    root, db, paths = _legacy_tree(tmp_path, [("T2R", [3])] * 4)
    conn = dx.connect(db)
    dx.lazy_qubit_pass(_q([3]), "L", conn, budget=100)
    assert len(counting_reader) == 4
    assert conn.execute("SELECT COUNT(*) FROM qubit_memo").fetchone()[0] == 4

    dx.reset_cache(conn)                                          # part B's "Yes"
    assert all(conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0
               for t in ("files", "day_folders", "expt_folders"))
    assert conn.execute("SELECT COUNT(*) FROM qubit_memo").fetchone()[0] == 4

    _time.sleep(0.05)
    with h5py.File(paths[0], "a") as f:                           # one file changes
        f.attrs["config"] = json.dumps({"Qubit_Readout_List": [7]})
    stats = dx.index_all(str(root), "L", conn)                    # the rebuild
    assert stats["memo_hits"] == 3                                # labels back, zero opens
    assert len(counting_reader) == 4
    src = {r[0]: r[1] for r in conn.execute("SELECT path, qubit_source FROM files")}
    assert src[str(paths[0])] is None and sum(v == "config" for v in src.values()) == 3
    dx.lazy_qubit_pass(_q([7]), "L", conn, budget=100)            # only the changed one
    assert counting_reader[4:] == [str(paths[0])]
    assert dx.query(_q([7]), "L", conn=conn)[1] == 1
    conn.close()


# ---- GUI: the note, the automatic pass, "Read more", Stop / Reset ----------------------

def _legacy_browser(qapp, tmp_path, spec, monkeypatch, budget=None, sync=True):
    from triangle_lattice_quench.Run_Experiments.viewer_gui.browser import BrowserWidget
    dev = "8QV1_Triangle_Lattice"
    root = tmp_path / dev
    for i, (experiment, qubits) in enumerate(spec):
        _write_run(root, experiment, LEGACY_DAY, f"10_{i // 60:02d}_{i % 60:02d}", qubits)
    db = tmp_path / "gui.sqlite"
    dx.scan(str(root), dev, db_path=db)
    monkeypatch.setattr(dx, "DATA_ROOT", tmp_path)                # workers never see Z:
    if budget is not None:
        monkeypatch.setattr(dx, "PASS_BUDGET", budget)
    b = BrowserWidget(db_path=db, auto_index=False)
    if sync:
        b._start_worker = lambda w: w.run()                       # deterministic, no thread
    b.device_combo.blockSignals(True)
    b.device_combo.setCurrentText(dev)
    b.device_combo.blockSignals(False)
    b._on_device_changed(dev, index=False)
    qapp.processEvents()
    return b


def _settle(qapp, n=6):
    for _ in range(n):
        qapp.processEvents()


def test_gui_note_without_reading_then_lazy_pass(qapp, tmp_path, monkeypatch, counting_reader):
    b = _legacy_browser(qapp, tmp_path, [("T2R", [3])] * 6 + [("T1", [4])] * 4, monkeypatch,
                        budget=4)
    try:
        _settle(qapp)
        assert counting_reader == []                              # construction reads nothing
        assert "qubit info" not in b.count_label.text() and b.read_more_btn.isHidden()

        requests = []
        real_request = b._request
        b._request = lambda mode: requests.append(mode)           # hold the pass back
        b.lattice.set_selected({"Q3"})
        b.refresh_table()
        assert b.table.rowCount() == 0
        assert "10 older runs not yet checked for qubit info" in b.count_label.text()
        b.filter_widgets["experiment"].setCurrentText("T2R")
        b.refresh_table()
        assert "6 older runs not yet checked for qubit info" in b.count_label.text()
        _settle(qapp)
        assert requests and set(requests) == {"lazy"} and counting_reader == []

        b._request = real_request                                 # now let it run
        b._lazy_key = None
        b.refresh_table()
        _settle(qapp)
        assert len(counting_reader) == 4 and all("\\T2R\\" in p for p in counting_reader)
        assert b.table.rowCount() == 4                            # matches shown
        assert "read 4 older runs (4 match); 2 more candidates unread" in b.status_label.text()
        assert not b.read_more_btn.isHidden()
        assert "2 older runs not yet checked" in b.count_label.text()

        b.read_more_btn.click()                                   # continuation
        _settle(qapp)
        assert len(counting_reader) == 6 and b.table.rowCount() == 6
        assert "complete for this filter" in b.status_label.text()
        assert b.read_more_btn.isHidden() and "not yet checked" not in b.count_label.text()

        b.refresh_table()                                         # identical query again
        _settle(qapp)
        assert len(counting_reader) == 6
        b.lattice.preset(0)                                       # qubit filter off
        b.refresh_table()
        _settle(qapp)
        assert len(counting_reader) == 6 and "qubit info" not in b.count_label.text()
    finally:
        b.close()
        b.conn.close()


def test_reset_confirmation_text_and_no_keeps_everything(qapp, tmp_path, monkeypatch):
    from PyQt5.QtWidgets import QMessageBox
    b = _legacy_browser(qapp, tmp_path, [("T2R", [3])] * 3, monkeypatch)
    try:
        box = b._reset_box()                                      # inspected, never exec'd
        assert box.windowTitle() == "Reset cache"
        assert box.text() == ("Clearing the cache can be useful when files are reorganized "
                              "on the disk. Are you sure you want to clear the cache?")
        assert box.defaultButton() is box.button(QMessageBox.No)
        assert b.stop_btn.text() == "Reset cache" and b.stop_btn.isEnabled()

        before = {t: b.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                  for t in ("files", "day_folders", "expt_folders")}
        asked = []
        b.confirm_reset = lambda: asked.append(1) or False        # "No"
        b.on_stop_or_reset()
        assert asked == [1]
        assert before == {t: b.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                          for t in before}
    finally:
        b.close()
        b.conn.close()


def test_reset_yes_clears_keeps_memo_and_rebuilds(qapp, tmp_path, monkeypatch):
    b = _legacy_browser(qapp, tmp_path, [("T2R", [3])] * 3, monkeypatch)
    try:
        dx.lazy_qubit_pass(_q([3]), "8QV1_Triangle_Lattice", b.conn, budget=10)
        memo = b.conn.execute("SELECT COUNT(*) FROM qubit_memo").fetchone()[0]
        assert memo == 3
        requests = []
        b._request = lambda mode: requests.append(mode)
        b.confirm_reset = lambda: True                            # "Yes"
        assert b.reset_cache()
        assert all(b.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0
                   for t in ("files", "day_folders", "expt_folders"))
        assert b.conn.execute("SELECT COUNT(*) FROM qubit_memo").fetchone()[0] == memo
        assert requests == ["open"]
        assert b.status_label.text() == "cache cleared - rebuilding..."
    finally:
        b.close()
        b.conn.close()


def _wait_thread(qapp, worker, timeout_s=30):
    import time as _time
    deadline = _time.time() + timeout_s
    while worker.isRunning() and _time.time() < deadline:
        qapp.processEvents()
        _time.sleep(0.01)
    _settle(qapp)


def test_stop_reset_label_follows_real_workers(qapp, tmp_path, monkeypatch):
    import time as _time
    b = _legacy_browser(qapp, tmp_path, [("T2R", [3])] * 8, monkeypatch, sync=False)
    try:
        assert b.stop_btn.text() == "Reset cache" and b.stop_btn.isEnabled()
        b._request("open")                                        # real thread, temp root
        assert b.stop_btn.text() == "Stop" and b.stop_btn.isEnabled()
        _wait_thread(qapp, b.worker)
        assert b.stop_btn.text() == "Reset cache"

        real = dx.read_config_qubits

        def slow(path):                                           # keeps the lazy pass alive
            _time.sleep(0.15)
            return real(path)
        monkeypatch.setattr(dx, "read_config_qubits", slow)
        asked = []
        b.confirm_reset = lambda: asked.append(1) or True
        b.lattice.set_selected({"Q3"})
        b.refresh_table()                                         # auto-starts a lazy pass
        _settle(qapp, 3)
        assert b._running() and b.worker.kind == "lazy" and b.stop_btn.text() == "Stop"
        assert b.reset_cache() is False                           # no way in during a run
        b.on_stop_or_reset()                                      # the button: Stop only
        assert asked == []
        _wait_thread(qapp, b.worker)
        assert b.stop_btn.text() == "Reset cache" and asked == []
        assert b.conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 8
    finally:
        b._stop_worker()
        b.close()
        b.conn.close()


def test_zoom_after_a_registered_widget_is_destroyed(qapp):
    """apply_style must skip monospace panes / tables deleted with their parent window
    (this was an intermittent access violation inside apply_style)."""
    from PyQt5.QtCore import QCoreApplication, QEvent
    from PyQt5.QtWidgets import QPlainTextEdit, QTableWidget, QVBoxLayout, QWidget
    from triangle_lattice_quench.Run_Experiments.viewer_gui import style as st
    parent = QWidget()
    layout = QVBoxLayout(parent)
    pane = st.make_mono(QPlainTextEdit())
    table = st.style_table(QTableWidget(1, 1))
    layout.addWidget(pane)
    layout.addWidget(table)
    keep = st.make_mono(QPlainTextEdit())            # a survivor, still restyled
    parent.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    qapp.processEvents()
    assert st.apply_style(qapp, 1.5) == 1.5          # no crash, no RuntimeError
    assert abs(keep.font().pointSizeF() - st.MONO_PT * 1.5) < 0.05
    st.apply_style(qapp, 1.0)


# --------------------------------------------------------------------------- #
# Config tab: one-line summaries + a lazy tree instead of 12,900 pretty-printed lines
# --------------------------------------------------------------------------- #

def _real_like_config():
    """~330 KB, shaped like BSClean_BSGain's config (43 keys, two big 2-D arrays)."""
    import random
    rng = random.Random(0)
    cfg = {f"param_{i}": rng.randint(0, 5000) for i in range(20)}
    cfg.update({
        "relax_delay": 200.5, "reps": 300, "qubit_gains": [0.0488, 0.0610, 0.0533, 0.0702],
        "t_offset": [0] * 8, "intermediate_jump_gains": [-3200, 0, 1200, 0, 0, 0, 0, 0],
        "fast_flux_chs": list(range(8)), "Qubit_Readout_List": [3, 4],
        "confusion_matrix": [[[0.97, 0.03], [0.05, 0.95]], [[0.96, 0.04], [0.06, 0.94]]],
        "outerFolder": r"Z:\QSimMeasurements\Measurements\8QV1_Triangle_Lattice" + "\\",
        "notes": "x" * 500,
        "FF_Qubits": {str(q): {"channel": q, "Gain_Readout": 1000 * q, "Gain_Pulse": 0,
                               "Gain_BS": 500, "Additional_Delay_Time": 0.0}
                      for q in range(1, 9)},
        "IDataArray1": [[rng.uniform(-32000, 32000) for _ in range(1250)] for _ in range(8)],
        "IDataArray2": [[rng.uniform(-32000, 32000) for _ in range(1000)] for _ in range(8)],
    })
    return cfg


def test_describe_rules():
    from triangle_lattice_quench.Run_Experiments.viewer_gui import config_tree as ct
    assert ct.describe([0] * 8).summary == "[0, 0, 0, 0, 0, 0, 0, 0]"
    assert ct.describe([0] * 8).children is None                       # inline, no rows
    assert ct.describe([0.0488, 0.061]).summary == "[0.0488, 0.061]"
    assert ct.describe([True, None, "a"]).summary == '[true, null, "a"]'
    assert ct.describe([]).summary == "[]" and ct.describe(3.14159265).summary == "3.14159"

    big = [float(i) for i in range(10000)]
    node = ct.describe(big)
    assert node.summary.startswith("list[10,000] float") and "max 1e+04" in node.summary
    assert callable(node.children) and node.array.shape == (10000,)   # lazy, not a list
    rows = list(node.children())
    assert len(rows) == ct.MAX_CHILDREN + 1 and rows[-1][0] == "\u2026"
    assert ct.describe(rows[-1][1]).summary == f"... {10000 - ct.MAX_CHILDREN:,} more"

    rect = ct.describe([[float(i + j) for i in range(1250)] for j in range(8)])
    assert rect.summary.startswith("array [8 x 1,250] float") and "min 0" in rect.summary
    assert rect.array.shape == (8, 1250)
    first = list(rect.children())[0]
    assert ct.describe(first[1]).summary.startswith("list[1,250] float")

    nested = ct.describe({"a": {"b": {"c": 1}}})
    assert nested.summary == "{1 key}"
    (k, v), = list(nested.children())
    assert k == "a" and ct.describe(v).summary == "{1 key}"

    long = "y" * 1000
    s = ct.describe(long)
    assert len(s.summary) == ct.STR_MAX and s.summary.endswith("\u2026") and s.tooltip == long
    assert ct.describe([{"x": 1}, {"y": 2}]).summary == "[2 dicts]"
    assert ct.describe([[[0.97, 0.03]], [[0.05, 0.95]]]).summary == "[2 lists]"   # 3-level
    mixed = ct.describe([1, [2, 3], {"z": 4}])
    assert mixed.summary == "[3 items]" and len(list(mixed.children())) == 3
    many = ct.describe({f"k{i}": i for i in range(250)})
    kids = list(many.children())
    assert len(kids) == ct.MAX_CHILDREN + 1 and ct.describe(kids[-1][1]).summary == "... 50 more"


def test_find_paths_searches_data_not_long_arrays():
    from triangle_lattice_quench.Run_Experiments.viewer_gui.config_tree import find_paths
    cfg = _real_like_config()
    paths = find_paths(cfg, "GAIN")
    tops = {p[0] for p in paths}
    assert {"qubit_gains", "intermediate_jump_gains", "FF_Qubits"} <= tops
    assert ("FF_Qubits", "3", "Gain_Readout") in paths
    assert not any(p[0].startswith("IDataArray") for p in paths)
    assert find_paths(cfg, "8QV1_Triangle") == [("outerFolder",)]           # value match
    assert find_paths(cfg, "") == [] and find_paths(cfg, "no-such-thing") == []
    assert find_paths({"a": list(range(100000))}, "9999") == []           # never descended


@pytest.fixture
def config_pane(qapp):
    from triangle_lattice_quench.Run_Experiments.viewer_gui.browser import ConfigPane
    pane = ConfigPane()
    pane.resize(700, 600)
    pane.show()
    qapp.processEvents()
    yield pane
    pane.close()


def _top(pane, key):
    return next(pane.tree.topLevelItem(i) for i in range(pane.tree.topLevelItemCount())
                if pane.tree.topLevelItem(i).text(0) == key)


def test_config_tree_builds_lazily_and_fast(config_pane, qapp):
    import time as _time
    from triangle_lattice_quench.Run_Experiments.viewer_gui.config_tree import MAX_CHILDREN
    cfg = _real_like_config()
    assert 300_000 < len(json.dumps(cfg)) < 400_000
    t = _time.perf_counter()
    config_pane.set_config(cfg)
    build = _time.perf_counter() - t
    assert build < 0.5, build
    assert config_pane.tree.topLevelItemCount() == len(cfg)
    assert config_pane.materialised == len(cfg) <= 60           # top level only
    assert _top(config_pane, "t_offset").text(1) == "[0, 0, 0, 0, 0, 0, 0, 0]"   # no expand
    assert _top(config_pane, "IDataArray1").text(1).startswith("array [8 x 1,250] float")
    item = _top(config_pane, "IDataArray1")
    item.setExpanded(True)
    assert item.childCount() == 8 <= MAX_CHILDREN + 1
    row = item.child(0)
    assert row.text(1).startswith("list[1,250] float")
    row.setExpanded(True)
    assert row.childCount() == MAX_CHILDREN + 1
    assert row.child(MAX_CHILDREN).text(1) == f"... {1250 - MAX_CHILDREN:,} more"


def test_config_filter_expands_only_matching_paths(config_pane):
    config_pane.set_config(_real_like_config())
    config_pane.filter_edit.setText("gain")
    config_pane.apply_filter()                                  # the debounce, run now
    visible = {config_pane.tree.topLevelItem(i).text(0)
               for i in range(config_pane.tree.topLevelItemCount())
               if not config_pane.tree.topLevelItem(i).isHidden()}
    assert visible == {"qubit_gains", "intermediate_jump_gains", "FF_Qubits"}
    ff = _top(config_pane, "FF_Qubits")
    assert ff.isExpanded() and all(ff.child(i).isExpanded() for i in range(ff.childCount()))
    assert _top(config_pane, "IDataArray1").isHidden()
    config_pane.filter_edit.setText("no-such-key")
    config_pane.apply_filter()
    assert config_pane.tree.topLevelItemCount() == 1
    assert config_pane.tree.topLevelItem(0).text(0) == "(no match)"
    config_pane.filter_edit.setText("")
    config_pane.apply_filter()                                  # cleared: all back
    assert config_pane.tree.topLevelItemCount() == len(_real_like_config())
    assert not any(config_pane.tree.topLevelItem(i).isHidden()
                   for i in range(config_pane.tree.topLevelItemCount()))


def test_config_plot_follows_selection(config_pane):
    cfg = _real_like_config()
    cfg["long_trace"] = [float(i % 97) for i in range(50000)]
    config_pane.set_config(cfg)
    tree, canvas = config_pane.tree, config_pane.canvas
    arr = _top(config_pane, "IDataArray2")
    tree.setCurrentItem(arr)
    assert canvas.isVisible() and len(canvas.ax.lines) == 8          # rows overlaid
    assert canvas.height() >= canvas.minimumHeight() >= 160          # never a 0-px sliver
    assert canvas.ax.get_legend() is not None
    arr.setExpanded(True)
    tree.setCurrentItem(arr.child(2))                                # one row only
    assert canvas.isVisible() and len(canvas.ax.lines) == 1
    tree.setCurrentItem(_top(config_pane, "long_trace"))             # decimated
    assert "decimated" in canvas.ax.get_title()
    assert len(canvas.ax.lines[0].get_xdata()) <= config_pane.MAX_PLOT_POINTS
    tree.setCurrentItem(_top(config_pane, "reps"))                   # scalar: hidden
    assert not canvas.isVisible()


def test_config_raw_view_copy_and_messages(config_pane, qapp):
    from PyQt5.QtWidgets import QApplication
    cfg = _real_like_config()
    config_pane.set_config(cfg)
    want = json.dumps(cfg, indent=2)
    assert config_pane.stack.currentIndex() == 0                     # tree by default
    config_pane.raw_box.setChecked(True)
    assert config_pane.stack.currentWidget() is config_pane.raw
    assert config_pane.raw.toPlainText() == want
    config_pane.raw_box.setChecked(False)
    config_pane.copy_json()
    assert QApplication.clipboard().text() == want
    config_pane.show_message(dx.BUSY_MESSAGE)                        # busy -> raw view
    assert config_pane.stack.currentWidget() is config_pane.raw
    assert config_pane.raw.toPlainText() == dx.BUSY_MESSAGE
    assert config_pane.tree.topLevelItemCount() == 0
    config_pane.expand_one_level()                                   # inert without cfg
    config_pane.set_config(cfg)
    config_pane.expand_one_level()
    assert _top(config_pane, "FF_Qubits").isExpanded()
    assert not _top(config_pane, "FF_Qubits").child(0).isExpanded()  # one level only


def test_browser_config_tab_uses_the_tree_and_sidecar(qapp, tmp_path):
    import h5py
    from triangle_lattice_quench.Run_Experiments.viewer_gui.browser import BrowserWidget
    path = _write_run(tmp_path / "D", "T1", "2026_10_01", "11_00_00", [3])
    b = BrowserWidget(db_path=tmp_path / "c.sqlite", auto_index=False)
    try:
        b._load_config(str(path))
        assert b.config_pane.stack.currentIndex() == 0
        assert _top(b.config_pane, "Qubit_Readout_List").text(1) == "[3]"
        assert json.loads(b.config_text.toPlainText())["Qubit_Readout_List"] == [3]
        with h5py.File(path, "a") as f:                              # attr gone -> sidecar
            del f.attrs["config"]
        Path(str(path)[:-3] + ".json").write_text(json.dumps({"from_sidecar": True}))
        b._load_config(str(path))
        assert _top(b.config_pane, "from_sidecar").text(1) == "true"
        Path(str(path)[:-3] + ".json").unlink()
        b._load_config(str(path))                                    # neither: a message
        assert "no config attr and no readable sidecar json" in b.config_text.toPlainText()
        assert b.config_pane.stack.currentWidget() is b.config_text
    finally:
        b.close()
        b.conn.close()


# --------------------------------------------------------------------------- #
# Data tab: the clicked dataset as a tree + plot, numpy text abbreviated by default
# --------------------------------------------------------------------------- #

def test_describe_numpy_arrays():
    import numpy as np
    from triangle_lattice_quench.Run_Experiments.viewer_gui import config_tree as ct
    assert ct.describe(np.zeros(8)).summary == "[0, 0, 0, 0, 0, 0, 0, 0]"   # short: inline
    assert ct.describe(np.array(3.5)).summary == "3.5"                     # 0-d: scalar
    one = ct.describe(np.arange(10000.0))
    assert one.summary.startswith("ndarray [10,000] float64") and "max 1e+04" in one.summary
    assert one.array.shape == (10000,) and callable(one.children)
    shots = np.ones((8, 100000), dtype=np.int32)
    two = ct.describe(shots)
    assert two.summary.startswith("ndarray [8 x 100,000] int32   min 1   max 1")
    assert two.array.shape == (8, 100000)
    rows = list(two.children())
    assert len(rows) == 8 and ct.describe(rows[0][1]).array.shape == (100000,)
    cube = ct.describe(np.zeros((2, 3, 4)))
    assert cube.summary.startswith("ndarray [2 x 3 x 4]") and cube.array is None
    assert ct.describe(list(cube.children())[0][1]).array.shape == (3, 4)  # slices plot
    strs = ct.describe(np.array(["a", "b"] * 20))
    assert strs.array is None and strs.summary.startswith("ndarray [40]")


def _data_file(tmp_path, datasets):
    """A saved run plus extra /data datasets {name: array}; returns its path."""
    import h5py
    path = _write_run(tmp_path / "D", "T1", "2026_10_01", "11_00_00", [3])
    with h5py.File(path, "a") as f:
        for name, value in datasets.items():
            f["data"].create_dataset(name, data=value)
    return str(path)


def _click_dataset(b, name):
    item = next(b.data_tree.topLevelItem(i) for i in range(b.data_tree.topLevelItemCount())
                if b.data_tree.topLevelItem(i).text(0) == name)
    b._on_dataset_clicked(item, 0)


@pytest.fixture
def data_browser(qapp, tmp_path):
    import numpy as np
    from triangle_lattice_quench.Run_Experiments.viewer_gui.browser import BrowserWidget
    path = _data_file(tmp_path, {"shots": np.arange(8 * 5000, dtype=float).reshape(8, 5000),
                                 "small": np.arange(12, dtype=float)})
    b = BrowserWidget(db_path=tmp_path / "d.sqlite", auto_index=False)
    b.resize(1400, 900)
    b.show()
    b.right.setCurrentIndex(1)                                       # the Data tab
    b._path = path
    b._load_datasets(path)
    qapp.processEvents()
    yield b
    b.close()
    b.conn.close()


def test_data_tab_shows_tree_and_plot_with_abbreviated_text(data_browser):
    import numpy as np
    b = data_browser
    _click_dataset(b, "shots")
    view = b.data_view
    assert view.tree.topLevelItemCount() == 1
    top = view.tree.topLevelItem(0)
    assert top.text(0) == "shots" and top.text(1).startswith("ndarray [8 x 5,000] float64")
    assert view.canvas.isVisible() and len(view.canvas.ax.lines) == 8    # plotted at once
    top.setExpanded(True)
    view.tree.setCurrentItem(top.child(3))                            # one row
    assert len(view.canvas.ax.lines) == 1
    text = b.data_text.toPlainText()
    assert "..." in text and len(text) < 2000                        # numpy's summary
    assert text == np.array2string(np.arange(40000.0).reshape(8, 5000), threshold=2000)
    assert b.show_raw_btn.isEnabled() and not b.show_raw_btn.isChecked()


def test_show_raw_prints_everything_and_resets_on_selection(data_browser):
    import numpy as np
    b = data_browser
    _click_dataset(b, "shots")
    b.show_raw_btn.setChecked(True)
    full = b.data_text.toPlainText()
    assert "..." not in full
    assert full == np.array2string(np.arange(40000.0).reshape(8, 5000), threshold=40001)
    values = np.array(full.replace("[", " ").replace("]", " ").split(), dtype=float)
    assert values.size == 40000 and values[-1] == 39999.0             # every value shown
    b.show_raw_btn.setChecked(False)                                  # and back
    assert "..." in b.data_text.toPlainText()

    b.show_raw_btn.setChecked(True)
    _click_dataset(b, "small")                                        # new selection
    assert not b.show_raw_btn.isChecked()                             # reset to off
    assert not b.show_raw_btn.isEnabled()                             # nothing to expand
    assert "..." not in b.data_text.toPlainText()
    _click_dataset(b, "shots")                                        # back to the big one
    assert not b.show_raw_btn.isChecked() and "..." in b.data_text.toPlainText()
    b._load_datasets(b._path)                                         # new file: cleared
    assert b.data_view.tree.topLevelItemCount() == 0 and not b.show_raw_btn.isEnabled()


def test_big_dataset_still_asks_before_loading(qapp, tmp_path, monkeypatch):
    import numpy as np
    from triangle_lattice_quench.Run_Experiments.viewer_gui import browser as br
    path = _data_file(tmp_path, {"population_shots": np.zeros((8, 100000))})   # 6.4 MB
    b = br.BrowserWidget(db_path=tmp_path / "big.sqlite", auto_index=False)
    try:
        b._path = path
        b._load_datasets(path)
        assert b._datasets["population_shots"]["nbytes"] > br.CONFIRM_LOAD_BYTES
        asked = []

        def answer(reply):
            return lambda *a, **k: asked.append(a[2]) or reply
        monkeypatch.setattr(br.QMessageBox, "question", answer(br.QMessageBox.No))
        _click_dataset(b, "population_shots")
        assert len(asked) == 1 and "6.1 MB" in asked[0]
        assert b.data_view.tree.topLevelItemCount() == 0             # nothing loaded
        monkeypatch.setattr(br.QMessageBox, "question", answer(br.QMessageBox.Yes))
        _click_dataset(b, "population_shots")
        assert len(asked) == 2
        assert b.data_view.tree.topLevelItem(0).text(1).startswith(
            "ndarray [8 x 100,000] float64")
        assert "..." in b.data_text.toPlainText() and b.show_raw_btn.isEnabled()
    finally:
        b.close()
        b.conn.close()


def test_group_name_edit_fans_out_to_selected_cells_in_the_column(qapp, tmp_path):
    import h5py
    from PyQt5.QtCore import QItemSelectionModel, Qt
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QLineEdit, QApplication
    from PyQt5.QtGui import QKeyEvent
    from PyQt5.QtCore import QEvent
    b = _make_browser(qapp, tmp_path, [("T1", "10_00_00", "g0"), ("T1", "10_00_01", "g1"),
                                       ("T1", "10_00_02", "g2")])
    try:
        t = b.table
        b.show(); qapp.processEvents()
        assert t.item(0, 3).flags() & Qt.ItemIsEditable and not t.item(0, 1).flags() & Qt.ItemIsEditable
        sm = t.selectionModel()
        t.setCurrentCell(0, 3)
        for r in (0, 1):
            sm.select(t.model().index(r, 3), QItemSelectionModel.Select)
        sm.select(t.model().index(1, 1), QItemSelectionModel.Select)   # other column: dropped
        assert {(i.row(), i.column()) for i in sm.selectedIndexes()} == {(0, 3), (1, 3)}
        untouched = t.item(2, 3).text()
        t.setFocus(); t.activateWindow(); qapp.processEvents()
        QTest.keyClicks(t, "n")                                    # typing starts the editor
        qapp.processEvents()
        editor = t.viewport().findChild(QLineEdit)
        assert editor is not None and editor.text() == "n"
        editor.setText("newgrp")
        QTest.keyClick(editor, Qt.Key_Return)                           # commit + cursor moves down
        qapp.processEvents()
        assert [t.item(r, 3).text() for r in range(3)] == ["newgrp", "newgrp", untouched]
        for r, want in ((0, "newgrp"), (1, "newgrp"), (2, untouched)):
            with h5py.File(t.item(r, 0).data(Qt.UserRole), "r") as f:
                assert f.attrs["group_name"] == want
    finally:
        b.close()


def test_mouse_drag_selects_several_cells_in_one_column(qapp, tmp_path):
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    from PyQt5.QtCore import QEvent, QPointF
    from PyQt5.QtGui import QMouseEvent
    from PyQt5.QtWidgets import QApplication
    b = _make_browser(qapp, tmp_path, [("T1", f"10_00_0{i}", f"g{i}") for i in range(4)])
    try:
        t = b.table
        b.show(); t.resize(700, 300); qapp.processEvents()
        pos = lambda r, c: t.visualItemRect(t.item(r, c)).center()
        vp = t.viewport()
        QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, pos(0, 3))
        for p in (pos(2, 3), pos(2, 4)):                                 # drifts into the next column
            QApplication.sendEvent(vp, QMouseEvent(QEvent.MouseMove, QPointF(p), Qt.NoButton,
                                                   Qt.LeftButton, Qt.NoModifier))
        QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, pos(2, 4))
        assert {(i.row(), i.column()) for i in t.selectionModel().selectedIndexes()} == {(0, 3), (1, 3), (2, 3)}
    finally:
        b.close()
