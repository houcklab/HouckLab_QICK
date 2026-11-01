"""Saving runs, while they run.

Files go where ExperimentClass (triangle_lattice_quench/Experiment.py) puts them:

    <folder>/<name>/<name>_<date>/<name>_<timestamp>_data.h5
                                  <name>_<timestamp>_data.png          (the plot)
                                  <name>_<timestamp>_bob_snapshot.json
                                  <name>_<timestamp>_bob_sequence.json
                                  <name>_<timestamp>_soccfg.json       (the board's own config)

The board's config (QickConfig.dump_cfg(), read when Bob connects) is saved with every real
run, and compared with ``soccfg.json`` in the station folder when one is there; the result
is in the .h5's ``board_config_check`` attribute. Simulated runs have no board config and go
to ``<folder>/_simulated/`` instead.

``<folder>`` is, first match wins: ``--out`` / an explicit argument, the sequence's own
save folder (Experiment tab), the station's ``outer_folder``.

The folder and file names follow the lab layout; the .h5 contents do not (Bob stores the
sequence instead of the lab's flat cfg). Whether the lab's viewer GUI or Desq can open these
files has not been checked.

RunWriter creates the .h5 before the first point and writes points as they are measured (in
batches at most a second apart), so a crash or Stop keeps everything measured up to then.
Unmeasured points are NaN; the file's ``status`` attribute says how the run ended (running,
complete, stopped …, failed …) and ``points_done`` how far it got.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import time
from pathlib import Path
from typing import Optional

import numpy as np

from ..config.snapshot import save_snapshot

FLUSH_EVERY_S = 1.0          # write to disk at most this often, and always at the end


def run_folder(outer_folder, name: str) -> Path:
    """``<outer_folder>/<name>/<name>_<date>``, created if needed (the ExperimentClass layout)."""
    problem = folder_problem(str(outer_folder))
    if problem:
        raise OSError(problem)
    today = datetime.date.today().strftime("%Y_%m_%d")
    folder = Path(outer_folder) / name / f"{name}_{today}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def data_folder(seq, station, override: Optional[str] = None) -> str:
    """Where a run of ``seq`` is saved: ``override``, else the sequence's save folder, else the station's."""
    return str(override or seq.settings.save_folder or station.data.get("outer_folder", "") or ".")


def run_folder_for(seq, station, override: Optional[str] = None, simulated: bool = False) -> str:
    """data_folder, with simulated runs kept apart in its _simulated subfolder."""
    folder = data_folder(seq, station, override)
    if simulated:
        from .simulate import SIMULATED_SUBFOLDER
        folder = str(Path(folder) / SIMULATED_SUBFOLDER)
    return folder


def file_name(seq) -> str:
    """The sequence name as a folder/file name that works on Windows, macOS and Linux."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", (seq.name or "").strip().replace(" ", "_"))
    return name.strip(" .") or "bob_run"


def folder_problem(folder: str, system: Optional[str] = None) -> Optional[str]:
    """Why ``folder`` can't be used on this computer, or None. Catches a Windows drive path
    (Z:\\...) on macOS/Linux and a Mac/Linux path (/Volumes/...) on Windows."""
    system = system or os.name               # "nt" on Windows, "posix" on macOS and Linux
    f = str(folder or "").strip()
    if not f:
        return "no save folder is set"
    if system != "nt" and re.match(r"^[A-Za-z]:[\\/]", f):
        return (f"{f} is a Windows drive path, which this computer can't use. Set a save folder in the "
                "Experiment tab (or --out), e.g. where the lab drive is mounted")
    if system == "nt" and re.match(r"^/(Volumes|Users|home|mnt|tmp)(/|$)", f):
        return f"{f} is a macOS/Linux path, which this computer can't use. Set a save folder in the Experiment tab"
    return None


def board_config_text(soccfg) -> Optional[str]:
    """The board's own description (QickConfig.dump_cfg()), or None when there is no real board."""
    if soccfg is None:
        return None
    dump = getattr(soccfg, "dump_cfg", None)
    try:
        return dump() if callable(dump) else None
    except Exception:
        return None


def check_board_config(station, text: Optional[str]) -> str:
    """Compare the live board config with the one saved in the station folder (soccfg.json)."""
    if text is None:
        return "no board config (no real board)"
    ref = Path(getattr(station, "folder", ".")) / "soccfg.json"
    if not ref.exists():
        return f"not compared: no saved board config at {ref}"
    try:
        same = json.loads(ref.read_text(encoding="utf-8")) == json.loads(text)
    except Exception as exc:
        return f"not compared: {exc}"
    return "matches the station's saved board config" if same else \
        f"DIFFERS from the station's saved board config ({ref}): the firmware or qick version may have changed"


def measured_qubits(seq) -> list:
    m = seq.measure
    if m is None:
        return []
    src = m.fields.get("qubits")
    return [int(q) for q in (getattr(src, "value", None) or [])]


def _plain(v):
    """JSON-ready: numpy arrays and scalars become lists and numbers."""
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    if isinstance(v, np.ndarray):
        return v.tolist()
    if isinstance(v, np.generic):
        return v.item()
    return v


def flatten_resolution(res) -> dict:
    """Every resolved number of one sweep point, as {"<block> [id] › <field>": value}."""
    out = {}
    blocks = list(res.segments) + list(res.pulses) + ([res.measure] if res.measure else [])
    for x in blocks:
        name = f"{x.block.name} [{x.block.id}]"
        for k, v in (x.params or {}).items():
            out[f"{name} › {k}"] = _plain(v)
    if res.measure is not None and res.measure.readout:
        for k, v in res.measure.readout.items():
            out[f"readout › {k}"] = _plain(v)
    return out


def git_commit() -> str:
    """The commit Bob's code is at (and "+ changes" when it has uncommitted edits), or ""."""
    import subprocess
    here = Path(__file__).resolve().parents[1]
    try:
        head = subprocess.run(["git", "-C", str(here), "rev-parse", "HEAD"], capture_output=True, text=True,
                              timeout=5).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(here), "status", "--porcelain", "--", "."], capture_output=True,
                               text=True, timeout=5).stdout.strip()
        return head + (" + uncommitted changes" if dirty else "") if head else ""
    except Exception:
        return ""


class RunWriter:
    """One run's files. Use ``write_point`` as an ``on_point`` listener, then ``close``.

    Everything needed to run the same experiment again goes into the .h5's attributes before
    the first point: the sequence, the station, the whole calibration file (or the frozen
    subset an exported script carries), the IIR coefficient files, the board's config and
    Bob's version. ``write_resolved`` adds every resolved number: values that are the same at
    every point once, values that change as one dataset per value under ``resolved/``.

    Points are written in small batches (at most every FLUSH_EVERY_S, and at the end); the file
    is opened only for each batch, as ExperimentClass does, so it is a complete, readable .h5
    between batches and others can open it while the run goes on."""

    def __init__(self, folder, seq, snapshot: Optional[dict] = None, board_config: Optional[str] = None,
                 board_check: str = "", simulated: bool = False, station=None, calib=None):
        import h5py
        from .. import __version__
        name = file_name(seq)
        self.folder = run_folder(folder, name)
        stamp = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        self.base = self.folder / f"{name}_{stamp}"
        self.path = Path(str(self.base) + "_data.h5")
        settings = seq.settings
        self.shape = tuple(max(1, a.points) for a in settings.sweeps) or (1,)
        self.n_points = settings.n_points()
        self.points_done = 0
        self._pending: list = []
        self._pending_resolved: list = []
        self._constant: Optional[dict] = None       # resolved values at the first point
        self._varying: dict = {}                    # key -> True once it differs from the first point
        self._seen: list = []                       # sweep points resolved so far
        self._closed = False
        calib_text, calib_kind = _calibration_text(calib)
        with h5py.File(str(self.path), "w") as f:
            for a in settings.sweeps:
                f.create_dataset(a.name, data=a.values())
            f.create_dataset("readout_list", data=np.asarray(measured_qubits(seq), int))
            f.attrs["bob_version"] = __version__
            f.attrs["bob_git_commit"] = git_commit()
            f.attrs["bob_sequence"] = json.dumps(seq.to_dict())
            f.attrs["status"] = "running"
            f.attrs["points_done"] = 0
            f.attrs["n_points"] = self.n_points
            f.attrs["started"] = datetime.datetime.now().isoformat(timespec="seconds")
            f.attrs["simulated"] = bool(simulated)
            f.attrs["board_config"] = board_config or ""
            f.attrs["board_config_check"] = board_check
            if station is not None:
                f.attrs["station"] = json.dumps(station.to_dict())
                f.attrs["station_name"] = station.name
                _save_iir(f, station)
            if calib is not None:
                f.attrs["calibration"] = calib_text
                f.attrs["calibration_kind"] = calib_kind
                f.attrs["calibration_path"] = calib.path or ""
                f.attrs["calibration_sha256"] = calib.sha256 or ""
            f.attrs["how_to_rerun"] = ("python -m Bob.runner.rerun <this file>: checks that the saved inputs "
                                       "rebuild the same experiment; --run (or --run --simulate) runs it again")
        self._last_flush = time.monotonic()
        Path(str(self.base) + "_bob_sequence.json").write_text(json.dumps(seq.to_dict(), indent=2),
                                                                encoding="utf-8")
        if snapshot is not None:
            save_snapshot(snapshot, str(self.base) + "_bob_snapshot.json")
        if board_config:
            Path(str(self.base) + "_soccfg.json").write_text(board_config, encoding="utf-8")
        if calib is not None:
            Path(str(self.base) + "_qubit_parameters.json").write_text(calib_text, encoding="utf-8")

    def write_resolved(self, k: int, res) -> None:
        """Record the resolved numbers of sweep point ``k`` (a BobExperiment ``on_resolved`` listener)."""
        flat = flatten_resolution(res)
        if self._constant is None:
            self._constant = flat
        self._pending_resolved.append((int(k), flat))

    def write_point(self, k: int, point: Optional[dict] = None, data: Optional[dict] = None) -> None:
        """Store sweep point ``k``. Accepts ``(k, pt, data)`` as BobExperiment's listeners get it."""
        values = data if data is not None else point
        self._pending.append((int(k), {key: np.asarray(v, float) for key, v in values.items()}))
        self.points_done = max(self.points_done, int(k) + 1)
        if time.monotonic() - self._last_flush >= FLUSH_EVERY_S:
            self.flush()

    def flush(self, status: Optional[str] = None) -> None:
        import h5py
        with h5py.File(str(self.path), "a") as f:
            for k, values in self._pending:
                idx = np.unravel_index(k, self.shape)
                for key, vals in values.items():
                    if key not in f:
                        f.create_dataset(key, data=np.full((len(vals), *self.shape), np.nan))
                    f[key][(slice(None), *idx)] = vals
            self._flush_resolved(f)
            f.attrs["points_done"] = self.points_done
            if status is not None:
                f.attrs["status"] = status
                f.attrs["finished"] = datetime.datetime.now().isoformat(timespec="seconds")
        self._pending = []
        self._last_flush = time.monotonic()

    def _flush_resolved(self, f) -> None:
        if self._constant is None:
            return
        grp = f.require_group("resolved")
        for k, flat in self._pending_resolved:
            idx = np.unravel_index(k, self.shape)
            for key, value in flat.items():
                if key not in self._varying and value == self._constant.get(key):
                    continue
                name = key.replace("/", "∕")
                if key not in self._varying:
                    self._varying[key] = True
                    base = self._constant.get(key)
                    width = () if np.ndim(base) == 0 else (len(base),)
                    ds = grp.create_dataset(name, data=np.full((*self.shape, *width), np.nan))
                    ds.attrs["value"] = key
                    for j in self._seen:                  # earlier points had the first point's value
                        ds[np.unravel_index(j, self.shape)] = _numeric(base)
                grp[name][idx] = _numeric(value)
            self._seen.append(k)
        grp.attrs["constant"] = json.dumps({k: v for k, v in self._constant.items() if k not in self._varying})
        grp.attrs["varying"] = json.dumps(sorted(self._varying))
        self._pending_resolved = []

    def close(self, status: str = "complete") -> Path:
        if not self._closed:
            self.flush(status)
            self._closed = True
        return self.path


def _numeric(v):
    try:
        return np.asarray(v, float)
    except (TypeError, ValueError):
        return np.nan                               # text that changes between points is not expected


def _calibration_text(calib) -> tuple:
    """The calibration this run used, as JSON text, and what it is."""
    if calib is None:
        return "", ""
    if calib.path and Path(calib.path).exists() and calib.sha256:
        import hashlib
        raw = Path(calib.path).read_bytes()
        if hashlib.sha256(raw).hexdigest() == calib.sha256 and json.loads(raw.decode("utf-8")) == calib.data:
            return raw.decode("utf-8"), "the whole calibration file"
    return json.dumps(calib.data, indent=1), ("the calibration values in memory (an exported script's frozen subset, "
                                              "or a file changed on disk since it was loaded)")


def _save_iir(f, station) -> None:
    """The IIR coefficient files the run compensates with, so the waveform can be rebuilt exactly."""
    from ..hardware.compensation import Compensator
    comp = Compensator.from_station(station)
    if not comp.available():
        return
    grp = f.create_group("iir")
    for q in sorted(comp.files):
        for p in comp._paths(q):
            if p.name not in grp:
                grp.create_dataset(p.name, data=np.loadtxt(p, dtype=np.complex128))


def save_run(folder: Path, name: str, data: dict, snapshot: dict, sequence_dict: dict) -> Path:
    """Save a finished run in one go (results already in memory)."""
    import h5py
    stamp = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    base = Path(folder) / f"{name}_{stamp}"
    with h5py.File(str(base) + "_data.h5", "w") as f:
        for k, v in data.items():
            try:
                f.create_dataset(k, data=np.asarray(v))
            except TypeError:                     # not array-like: store as a JSON attribute instead
                f.attrs[k] = json.dumps(v, default=str)
        f.attrs["bob_sequence"] = json.dumps(sequence_dict)
        f.attrs["status"] = "complete"
    save_snapshot(snapshot, str(base) + "_bob_snapshot.json")
    Path(str(base) + "_bob_sequence.json").write_text(json.dumps(sequence_dict, indent=2), encoding="utf-8")
    return Path(str(base) + "_data.h5")


def load_run(path) -> dict:
    """A saved run: {"sequence": dict, "data": {key: array}, "status", "points_done", "n_points", "path"}."""
    import h5py
    with h5py.File(str(path), "r") as f:
        data = {k: np.asarray(f[k][()]) for k in f.keys() if isinstance(f[k], h5py.Dataset)}
        attrs = dict(f.attrs)
    seq = json.loads(attrs.get("bob_sequence", "{}"))
    n = int(attrs.get("n_points", 0)) or None
    return {"sequence": seq, "data": data, "status": str(attrs.get("status", "complete")),
            "points_done": int(attrs.get("points_done", n or 0)), "n_points": n, "path": str(path),
            "simulated": bool(attrs.get("simulated", False)), "board_config": str(attrs.get("board_config", "")),
            "board_config_check": str(attrs.get("board_config_check", ""))}
