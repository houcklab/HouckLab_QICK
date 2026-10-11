"""SQLite index of saved measurement files + the declarative filter table.

Pure logic: stdlib + numpy + h5py + ``triangle_lattice_quench.Experiment``. No Qt,
no qick, no hardware -- so the scan/query/filter rules are testable headless (see
``test_viewer.py``) and the viewer runs on a laptop with neither.

Layout on disk, which is what makes indexing cheap::

    <root>/<Experiment>/<Experiment>_YYYY_MM_DD/<Experiment>_YYYY_MM_DD_HH_MM_SS_<prefix>.h5

Experiment name, date and time come from the PATH with zero file opens, and the
day-folder NAME carries the date -- so the newest runs can be found by sorting
directory names, without walking 39k files.

Three tiers, measured on the real share:

  TIER 0  map_day_folders   list experiment folders + day-folder names   ~4.3 s cold
  TIER 1  fill_view         descend newest-first until the view is full  ~2.0 s cold
  TIER 2  index_all         full or experiment-scoped walk, ON DEMAND    ~86 s

  refresh()                 warm reopen: 139 stats + re-list the last
                            RECENCY_DAYS of day folders                  ~0.07 s

The DB is pure cache. Deleting it loses nothing: the next open rebuilds it cold.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np

from triangle_lattice_quench.Experiment import (ExperimentClass, FileBeingSaved,
                                                open_for_reading)

# Files in day-folders dated before this predate ExperimentClass.save_metadata and
# carry no searchable attrs. They are NEVER opened during indexing, and legacy rows
# are not backlabelled.
METADATA_CUTOVER = "2026-10-01"

# A day folder's own mtime changes when files land in it, so only folders dated
# within this window can still be growing -- those are the only ones a warm reopen
# re-lists (~16 folders, 0.06 s today).
RECENCY_DAYS = 14

# Rows tier 1 aims to have cached: the table cap (500) plus margin.
VIEW_ROWS = 600

DATA_ROOT = Path(r"Z:\QSimMeasurements\Measurements")
_PKG_DIR = Path(__file__).resolve().parent
DEVICE_JSON_DIR = _PKG_DIR.parent.parent / "Device_Calibration" / "Device_calib" / "Device_jsons"
DEFAULT_DB_PATH = _PKG_DIR / "data_index.sqlite"

# Top-level folders starting with these are NOT experiments -- the user's convention
# (e.g. _PNAX holds the PNAX scans, _IIR_PulseCompensations holds CSVs). Applied at the
# single place the device root is listed (list_experiment_dirs), so they never reach
# the cache and any rows left from before are pruned on the next listing.
IGNORED_PREFIXES = ("_",)

# Lazy qubit lookup for files that predate save_metadata: at most this many unknown
# candidates are opened per pass (~55 ms each on the share, so 300 is ~16 s).
PASS_BUDGET = 300
# A pass also stops once the table would be full (same cap as the table).
ROW_CAP = 500
# Commit and report progress this often during a lazy pass.
LAZY_COMMIT_EVERY = 25
# qubit_source of a legacy file whose config holds no readout list: never re-read.
SOURCE_UNAVAILABLE = "unavailable"

# Shown when the share cannot be listed; the cache is then left exactly as it was.
UNREACHABLE_MESSAGE = "share not reachable - showing cached results"

# Shown wherever a file is refused because an experiment is writing it.
BUSY_MESSAGE = "this file is being saved right now - try again in a moment"

# Sentinel for "this combo filter is not set".
ANY = "(any)"

FILE_COLUMNS = ("path", "device", "day_path", "experiment", "experiment_class",
                "timestamp", "mtime", "qubit_readout", "qubits", "qubit_source",
                "group_name", "name", "n_readout", "has_meta")

# Bump when the schema or what gets stored in it changes. The DB is pure cache, so a
# mismatch simply drops the tables and the next open rebuilds them cold.
SCHEMA_VERSION = 3

# Experiment names contain underscores (CurrentCalibration_1D_Shots), so both
# patterns anchor on the date groups rather than splitting on '_'.
_DAY_RE = re.compile(r"_(\d{4})_(\d{2})_(\d{2})$")
_STAMP_RE = re.compile(r"_(\d{4})_(\d{2})_(\d{2})_(\d{2})_(\d{2})_(\d{2})(?:_|$)")
_LABEL_RE = re.compile(r"^Q?(\d+)$")


def qubit_label(value: Any) -> Optional[int]:
    """Normalize a qubit label to its int chip number: 'Q3', '3', 3, np.int64(3) -> 3.

    One shared normalizer so the indexer and the lattice selector always agree;
    save_metadata writes whatever build_config held, which may be str or int.
    """
    if isinstance(value, (bytes, np.bytes_)):
        value = value.decode("utf-8", "replace")
    if isinstance(value, (int, np.integer)) and not isinstance(value, bool):
        return int(value)
    m = _LABEL_RE.match(str(value).strip())
    return int(m.group(1)) if m else None


def _jsonable(value: Any) -> Any:
    """ndarray -> list, numpy scalar -> python scalar, bytes -> str."""
    if isinstance(value, np.ndarray):
        return [_jsonable(v) for v in value.tolist()]
    if isinstance(value, (bytes, np.bytes_)):
        return value.decode("utf-8", "replace")
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def day_date(folder_name: str) -> Optional[str]:
    """'T1MUX_2026_10_01' -> '2026-10-01'; None when the name is not a day folder."""
    m = _DAY_RE.search(folder_name)
    return "-".join(m.groups()) if m else None


def parse_path(root: str | os.PathLike, path: str) -> Optional[dict]:
    """Derive experiment / timestamp / day_date from the path alone, no file open."""
    # Lexical relative_to, never resolve(): on Windows resolve() calls
    # _getfinalpathname, which opens a handle per file -- a network round trip each,
    # measured at 2.6 ms/file. Every path here is built by joining onto str(root),
    # so the lexical form is exact.
    try:
        rel = Path(path).relative_to(Path(root))
    except ValueError:
        return None
    parts = rel.parts
    if len(parts) < 2:
        return None
    date = day_date(Path(parts[-2]).name)
    stamps = _STAMP_RE.findall(Path(parts[-1]).stem)
    if stamps:
        y, mo, d, h, mi, s = stamps[-1]
        timestamp = f"{y}-{mo}-{d}T{h}:{mi}:{s}"
    else:
        timestamp = f"{date}T00:00:00" if date else None
    return {"experiment": parts[0], "timestamp": timestamp, "day_date": date}


# --------------------------------------------------------------------------- #
# database
# --------------------------------------------------------------------------- #

def connect(db_path: str | os.PathLike | None = None) -> sqlite3.Connection:
    """Open (creating if needed) the index DB. One connection per thread.

    Only the DEFAULT location gets its parent directory created. A caller-supplied
    path whose directory does not exist is an error, so a mistyped path cannot silently
    build a directory tree and an empty database somewhere unexpected."""
    if db_path is None:
        db_path = Path(DEFAULT_DB_PATH)
        db_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        db_path = Path(db_path)
        if not db_path.parent.is_dir():
            raise FileNotFoundError(
                f"index database directory does not exist: {db_path.parent} "
                f"(refusing to create it for {db_path.name})")
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")      # GUI-thread query() during a scan
    conn.execute("PRAGMA synchronous=NORMAL")
    if conn.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
        conn.executescript("DROP TABLE IF EXISTS files;"
                           "DROP TABLE IF EXISTS day_folders;"
                           "DROP TABLE IF EXISTS expt_folders;")
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.execute("""CREATE TABLE IF NOT EXISTS files (
        path TEXT PRIMARY KEY, device TEXT, day_path TEXT, experiment TEXT,
        experiment_class TEXT, timestamp TEXT, mtime REAL, qubit_readout TEXT,
        qubits TEXT, qubit_source TEXT, group_name TEXT, name TEXT,
        n_readout INTEGER, has_meta INTEGER)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS day_folders (
        path TEXT PRIMARY KEY, device TEXT, experiment TEXT, date TEXT, mtime REAL,
        recursive INTEGER DEFAULT 1, indexed INTEGER DEFAULT 0, n_files INTEGER DEFAULT 0)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS expt_folders (
        path TEXT PRIMARY KEY, device TEXT, experiment TEXT, mtime REAL)""")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_dev_ts ON files(device, timestamp DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_dev_exp ON files(device, experiment)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_file_day ON files(day_path)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_day_dev ON day_folders(device, date DESC)")
    # The only EXPENSIVE thing in the cache: qubit lists read from legacy files' config
    # attr (~55 ms each). Outside the SCHEMA_VERSION drop above and never cleared by
    # reset_cache(), so a rebuild reuses them with zero file opens while mtimes match.
    conn.execute("""CREATE TABLE IF NOT EXISTS qubit_memo (
        path TEXT PRIMARY KEY, mtime REAL, qubit_readout TEXT, qubits TEXT,
        n_readout INTEGER, qubit_source TEXT)""")
    conn.commit()
    return conn


def reset_cache(conn) -> None:
    """Forget the whole index (all devices) but KEEP qubit_memo: the next open rebuilds
    cheaply and re-reads no legacy qubit info whose file is unchanged."""
    for table in ("files", "day_folders", "expt_folders"):
        conn.execute(f"DELETE FROM {table}")
    conn.commit()


def has_cache(device: str, conn) -> bool:
    """True when this device already has day folders mapped (-> warm path)."""
    return conn.execute("SELECT 1 FROM day_folders WHERE device=? LIMIT 1",
                        (device,)).fetchone() is not None


# Where a row's qubit list came from, best first. (a)/(b) are free from the attrs
# already being read; (c)/(d) cost nothing extra either -- they are read in the SAME
# open, and only for files the cutover rule already allows opening.
QUBIT_SOURCES = {
    "qubits": "attr 'qubits'",
    "Qubit_Readout": "attr 'Qubit_Readout'",
    "dataset": "/data/Qubit_Readout_List dataset (fallback)",
    "dataset_root": "root Qubit_Readout_List dataset (old flat layout, fallback)",
}


def read_metadata(path: str) -> dict:
    """Root attrs, plus the small Qubit_Readout_List dataset when the attrs carry no
    qubit list (fallback chain c/d).

    One open, ~0.3 ms. Deliberately a superset of ExperimentClass.load_metadata, so a
    run that saved its readout list only as a dataset is still filterable. Injectable
    so tests can count opens.
    """
    import h5py
    # Saving takes precedence over viewing: open_for_reading holds no HDF5 lock (so a
    # concurrent experiment save is never blocked) and raises FileBeingSaved while a
    # save is in progress. Known limits: (1) the refusal relies on Windows enforcing
    # byte-range locks -- a non-Windows reader degrades to "reads whatever is on disk";
    # (2) an open landing in the millisecond gap between an experiment's successive
    # opens (save_data -> save_metadata -> save_config) can index the file before its
    # metadata attrs exist. That self-heals: the later writes change the file's mtime,
    # so the next refresh re-indexes it (pinned by a test).
    with open_for_reading(path) as f:
        meta = {key: f.attrs[key] for key in f.attrs if key != "config"}
        if not any(isinstance(meta.get(k), np.ndarray) or meta.get(k) is not None
                   for k in ("qubits", "Qubit_Readout")):
            for group, source in ((f.get("data"), "dataset"), (f, "dataset_root")):
                obj = group.get("Qubit_Readout_List") if isinstance(group, h5py.Group) else None
                if isinstance(obj, h5py.Dataset):
                    meta["_qubit_fallback"] = obj[()]
                    meta["_qubit_fallback_source"] = source
                    break
    return meta


def _list_dir(path) -> Optional[list]:
    """Directory entries, or None when the listing FAILED.

    The distinction is load-bearing: an unreachable share must not look like an empty
    one, or the pruning below would wipe the cache every time the drive is offline."""
    try:
        return list(os.scandir(str(path)))
    except OSError:
        return None


def is_ignored(name: str) -> bool:
    return name.startswith(IGNORED_PREFIXES)


def list_experiment_dirs(root) -> tuple[Optional[list], int]:
    """THE place the device root is listed: (experiment dir entries, raw dir count).

    Entries is None when the listing failed. IGNORED_PREFIXES are dropped here and only
    here; the raw count (ignored folders included) tells pruning the listing was real."""
    entries = _list_dir(root)
    if entries is None:
        return None, 0
    dirs = []
    for entry in entries:
        try:
            if entry.is_dir(follow_symlinks=False):
                dirs.append(entry)
        except OSError:
            continue
    return [d for d in dirs if not is_ignored(d.name)], len(dirs)


def iter_h5(root, should_abort=lambda: False, recursive=True, errors=None):
    """Yield (path, mtime) for .h5 files under root.

    scandir hands back mtime from the directory listing itself, so there is no extra
    stat round-trip per file -- which matters at ~40k files over SMB. Directories that
    fail to list are appended to ``errors`` (when given) rather than looking empty.
    """
    stack = [str(root)]
    while stack:
        if should_abort():
            return
        current = stack.pop()
        entries = _list_dir(current)
        if entries is None:
            if errors is not None:
                errors.append(current)
            continue
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    if recursive:
                        stack.append(entry.path)
                elif entry.name.lower().endswith(".h5"):
                    yield entry.path, entry.stat().st_mtime
            except OSError:
                continue


# --------------------------------------------------------------------------- #
# TIER 0 -- map the day folders (names only: no file opens, no per-file stat)
# --------------------------------------------------------------------------- #

# `indexed` is deliberately NOT reset from the stored mtime: on Windows a directory's
# mtime as reported by scandir of its PARENT is stale (NTFS updates the parent's index
# entry lazily), so it cannot be trusted. Freshness comes from the recency pass in
# refresh() and from the per-file (path, mtime) check in index_day(), which uses FILE
# mtimes -- those scandir does report correctly.
_UPSERT_DAY = """INSERT INTO day_folders(path, device, experiment, date, mtime, recursive,
                                         indexed, n_files) VALUES(?,?,?,?,?,?,0,0)
    ON CONFLICT(path) DO UPDATE SET
        date = excluded.date, recursive = excluded.recursive, mtime = excluded.mtime"""


def map_day_folders(root, device, conn, full: bool = True, force_paths=(),
                    progress_cb=None, should_abort=None) -> dict:
    """List experiment folders and their day-folder NAMES into the cache.

    ``full=False`` is the warm path: re-list only the experiment folders whose mtime
    changed -- a directory's mtime moves when a child is created or removed, so that is
    exactly "a new day folder appeared". It does NOT catch files landing inside an
    existing day folder; ``refresh`` handles those with the recency window.

    The mtimes come from a real ``os.stat`` per experiment folder (~139 calls, 0.01 s),
    NOT from the scandir entry: on Windows ``os.scandir(parent)`` hands back the
    PARENT's directory-index copy of a subdirectory's timestamp, which NTFS never
    refreshes -- verified locally to still report the old value long after a mkdir,
    which would make new day folders invisible forever.

    Even a real stat is only eventually consistent: measured here, creating a child
    directory leaves the parent's mtime unchanged in 192/200 trials when no time
    passes. ``force_paths`` therefore re-lists chosen experiment folders regardless of
    mtime; ``refresh`` passes the recently-active ones so a day folder created moments
    ago is found deterministically rather than by timestamp luck.
    """
    progress_cb = progress_cb or (lambda *_: None)
    should_abort = should_abort or (lambda: False)
    stats = {"expt_folders": 0, "relisted": 0, "day_folders": 0, "aborted": False,
             "unreachable": False, "relist_failed": 0, "pruned_experiments": 0,
             "pruned_days": 0}
    expt_dirs, raw_dirs = list_experiment_dirs(root)
    if expt_dirs is None:
        stats["unreachable"] = True             # cache untouched: instant warm open stays
        return stats
    stats["expt_folders"] = len(expt_dirs)
    if raw_dirs:                                # a real listing, not a blank/odd mount
        stats["pruned_experiments"] = _prune_experiments(
            conn, device, {e.name for e in expt_dirs})
    cached = {r["path"]: r["mtime"] for r in
              conn.execute("SELECT path, mtime FROM expt_folders WHERE device=?", (device,))}
    for i, expt in enumerate(expt_dirs, 1):
        if should_abort():
            stats["aborted"] = True
            break
        try:
            mtime = os.stat(expt.path).st_mtime   # real stat; see the docstring
        except OSError:
            continue
        if not full and expt.path not in force_paths and cached.get(expt.path) == mtime:
            continue                            # nothing created or removed in here
        children = _list_dir(expt.path)
        if children is None:
            # Relist failed: leave this experiment's rows (and its stored mtime) alone,
            # so it is simply retried next time.
            stats["relist_failed"] += 1
            continue
        stats["relisted"] += 1
        rows, has_loose = [], False
        for child in children:
            try:
                if child.is_dir(follow_symlinks=False):
                    rows.append((child.path, device, expt.name,
                                 day_date(child.name), child.stat().st_mtime, 1))
                elif child.name.lower().endswith(".h5"):
                    has_loose = True
            except OSError:
                continue
        if has_loose:
            # Files sitting directly in the experiment folder (not in any day folder):
            # a synthetic, undated, NON-recursive row so tier 2 still finds them and
            # they never double-count against the real day folders.
            rows.append((expt.path, device, expt.name, None, mtime, 0))
        stats["pruned_days"] += _prune_days(conn, device, expt.name, {r[0] for r in rows})
        conn.executemany(_UPSERT_DAY, rows)
        conn.execute("INSERT OR REPLACE INTO expt_folders(path, device, experiment, mtime)"
                     " VALUES(?,?,?,?)", (expt.path, device, expt.name, mtime))
        conn.commit()
        stats["day_folders"] += len(rows)
        progress_cb(i, len(expt_dirs), f"listing day folders... {i}/{len(expt_dirs)} experiments")
    return stats


def _prune_experiments(conn, device: str, keep: set) -> int:
    """Delete every cached experiment of ``device`` not in ``keep`` (folder names) --
    gone from the share, moved, or now ignored. Returns how many were dropped."""
    stale = [r["experiment"] for r in conn.execute(
        "SELECT DISTINCT experiment FROM expt_folders WHERE device=? UNION "
        "SELECT DISTINCT experiment FROM day_folders WHERE device=?", (device, device))
        if r["experiment"] not in keep]
    for name in stale:
        for table in ("files", "day_folders", "expt_folders"):
            conn.execute(f"DELETE FROM {table} WHERE device=? AND experiment=?", (device, name))
    conn.commit()
    return len(stale)


def _prune_days(conn, device: str, experiment: str, fresh: set) -> int:
    """After a SUCCESSFUL relist of one experiment folder, drop its day folders (and their
    files) that are no longer there."""
    stale = [r["path"] for r in conn.execute(
        "SELECT path FROM day_folders WHERE device=? AND experiment=?", (device, experiment))
        if r["path"] not in fresh]
    for path in stale:
        conn.execute("DELETE FROM files WHERE day_path=?", (path,))
        conn.execute("DELETE FROM day_folders WHERE path=?", (path,))
    return len(stale)


# --------------------------------------------------------------------------- #
# indexing one day folder
# --------------------------------------------------------------------------- #

def index_day(day_row, device, conn, open_file=read_metadata,
              should_abort=None, stats=None) -> int:
    """Index every .h5 in one day folder. Returns the file count.

    Files whose (path, mtime) are unchanged are skipped without opening anything;
    files that vanished are pruned, so a day folder's rows always match the disk.
    A file that is merely BUSY (being saved) still appears in the listing, so it is
    never pruned. If the listing itself FAILS, nothing is pruned or marked indexed.
    """
    should_abort = should_abort or (lambda: False)
    stats = stats if stats is not None else {}
    stats.setdefault("indexed", 0)
    stats.setdefault("skipped", 0)
    stats.setdefault("opened", 0)
    stats.setdefault("failed", 0)
    day_path = day_row["path"]
    root = str(Path(day_path).parent.parent) if day_row["recursive"] else str(Path(day_path).parent)
    errors: list = []
    found = dict(iter_h5(day_path, should_abort, recursive=bool(day_row["recursive"]),
                         errors=errors))
    if errors:                                  # unreachable: keep the cache as it is
        stats["relist_failed"] = stats.get("relist_failed", 0) + 1
        return day_row["n_files"] or 0
    known = {r["path"]: r["mtime"] for r in
             conn.execute("SELECT path, mtime FROM files WHERE day_path=?", (day_path,))}
    stats.setdefault("busy", 0)
    stats.setdefault("memo_hits", 0)
    memo = {r["path"]: r for r in conn.execute(
        "SELECT * FROM qubit_memo WHERE substr(path, 1, ?) = ?", (len(day_path), day_path))}
    batch, busy = [], 0
    for path, mtime in found.items():
        if known.get(path) == mtime:
            stats["skipped"] += 1
            continue
        row = _build_row(root, device, day_path, path, mtime, day_row["date"],
                         open_file, stats)
        if row is None:                         # being saved: no row, no failure mark
            busy += 1
            continue
        hit = memo.get(path)
        if row[_COL["qubits"]] is None and hit is not None and mtime is not None \
                and hit["mtime"] == mtime:      # unchanged file: reuse, zero opens
            row = _with_qubits(row, hit)
            stats["memo_hits"] += 1
        batch.append(row)
        stats["indexed"] += 1
    stats["busy"] += busy
    gone = set(known) - set(found)
    if gone:
        conn.executemany("DELETE FROM files WHERE path=?", [(p,) for p in gone])
    if batch:
        conn.executemany(
            f"INSERT OR REPLACE INTO files ({','.join(FILE_COLUMNS)}) "
            f"VALUES ({','.join('?' * len(FILE_COLUMNS))})", batch)
    # A folder with a busy file stays unindexed, so EVERY later pass (refresh,
    # fill_view, Index all) retries it whatever its age or mtime.
    conn.execute("UPDATE day_folders SET indexed=?, n_files=? WHERE path=?",
                 (0 if busy else 1, len(found), day_path))
    conn.commit()                               # per day folder: Stop leaves it consistent
    return len(found)


def _build_row(root, device, day_path, path, mtime, date, open_file,
               stats) -> Optional[tuple]:
    """One index row, or None when the file is being saved right now (caller skips it)."""
    parsed = parse_path(root, path) or {}
    date = parsed.get("day_date") or date
    meta: dict = {}
    failed = False
    # The one gate that keeps indexing affordable: pre-cutover day-folders are never
    # opened, so those rows stay has_meta=0 with null metadata columns.
    if date is not None and date >= METADATA_CUTOVER:
        stats["opened"] = stats.get("opened", 0) + 1
        try:
            meta = {k: _jsonable(v) for k, v in open_file(path).items()}
        except FileBeingSaved:
            return None
        except Exception:
            failed = True                       # locked / half-written: index it bare
            stats["failed"] = stats.get("failed", 0) + 1
    # Two DIFFERENT strings, kept in two columns rather than merged into one bucket:
    #   experiment       = the top-level FOLDER name (ExperimentClass's self.path, e.g.
    #                      'T2R'). Always present, covers the whole legacy archive, and
    #                      is what the combo filters on so legacy and new runs of the
    #                      same experiment sit together.
    #   experiment_class = the 'Experiment' attr (type(self).__name__, e.g. 'T2RMUX'),
    #                      only on post-cutover files. Shown as its own column.
    klass = meta.get("Experiment")
    as_list = lambda v: list(v) if isinstance(v, list) and v else None
    readout = as_list(meta.get("Qubit_Readout"))
    # Fallback chain, best first; `qubit_source` records which rung was used so the UI
    # can distinguish a real match from a guess.
    chain = [("qubits", as_list(meta.get("qubits"))),
             ("Qubit_Readout", readout),
             (meta.get("_qubit_fallback_source"), as_list(meta.get("_qubit_fallback")))]
    source, qubits = next(((s, v) for s, v in chain if s and v), (None, None))
    return (
        path, device, day_path, parsed.get("experiment"),
        str(klass) if klass else None, parsed.get("timestamp"),
        None if failed else mtime,              # NULL mtime -> retried on the next pass
        json.dumps(readout) if readout is not None else None,
        json.dumps(qubits) if qubits is not None else None,
        source,
        meta.get("group_name"), meta.get("name"),
        len(qubits) if qubits is not None else None,
        1 if any(not k.startswith("_") for k in meta) else 0,   # '_' keys are fallbacks
    )


_COL = {name: i for i, name in enumerate(FILE_COLUMNS)}
_QUBIT_FIELDS = ("qubit_readout", "qubits", "n_readout", "qubit_source")


def _with_qubits(row: tuple, info) -> tuple:
    """``row`` with its qubit columns taken from a memo row / dict."""
    row = list(row)
    for field in _QUBIT_FIELDS:
        row[_COL[field]] = info[field]
    return tuple(row)


def _index_days(day_rows, device, conn, open_file, progress_cb, should_abort, stats) -> None:
    total = len(day_rows)
    for i, row in enumerate(day_rows, 1):
        if should_abort():
            stats["aborted"] = True
            return
        index_day(row, device, conn, open_file, should_abort, stats)
        progress_cb(i, total, f"indexing {Path(row['path']).name}  ({i}/{total})")


# --------------------------------------------------------------------------- #
# TIER 1 / refresh / TIER 2
# --------------------------------------------------------------------------- #

def _new_stats() -> dict:
    return {"indexed": 0, "skipped": 0, "opened": 0, "failed": 0, "busy": 0,
            "aborted": False, "days_indexed": 0, "unreachable": False,
            "relist_failed": 0, "pruned_experiments": 0, "pruned_days": 0}


def _merge_listing(stats: dict, listed: dict) -> dict:
    """Fold map_day_folders' outcome into a pass's stats."""
    stats["aborted"] |= listed["aborted"]
    stats["unreachable"] |= listed["unreachable"]
    for key in ("relist_failed", "pruned_experiments", "pruned_days"):
        stats[key] += listed[key]
    return stats


def _today() -> datetime.date:
    """The recency window's 'today'. A seam so tests can pin the date."""
    return datetime.date.today()


def fill_view(device, conn, needed: int = VIEW_ROWS, open_file=read_metadata,
              progress_cb=None, should_abort=None, stats=None, done=frozenset()) -> dict:
    """TIER 1: descend into dated day folders newest-first until the view is full.

    Stops on a DATE boundary, not a row count: several experiments share each date, so
    stopping mid-date could hide files newer than ones already shown. ``done`` holds day
    folders already handled in this pass (refresh's recency set): counted, not re-read,
    so a folder left unindexed by a busy file is not opened twice in one pass.
    """
    progress_cb = progress_cb or (lambda *_: None)
    should_abort = should_abort or (lambda: False)
    stats = stats if stats is not None else _new_stats()
    rows = conn.execute(
        "SELECT * FROM day_folders WHERE device=? AND date IS NOT NULL"
        " ORDER BY date DESC, path DESC", (device,)).fetchall()
    have, last_date = 0, None
    for i, row in enumerate(rows, 1):
        if should_abort():
            stats["aborted"] = True
            break
        if have >= needed and row["date"] != last_date:
            break
        if row["indexed"] or row["path"] in done:
            have += row["n_files"] or 0
        else:
            have += index_day(row, device, conn, open_file, should_abort, stats)
            stats["days_indexed"] += 1
            progress_cb(i, len(rows), f"indexing {Path(row['path']).name}  ({have} files)")
        last_date = row["date"]
    return stats


def refresh(root, device, conn, open_file=read_metadata, progress_cb=None,
            should_abort=None, needed: int = VIEW_ROWS) -> dict:
    """Warm reopen (~0.07 s): no full tier 0.

    1. 139 experiment-folder stats -> re-list only those where a day folder appeared
       or disappeared.
    2. Re-list day folders dated within RECENCY_DAYS -- a day folder's own mtime moves
       when files land in it, and only recent ones can still be growing. Without this,
       today's new runs would never show up.
    3. Top the view back up to ``needed`` rows.
    """
    progress_cb = progress_cb or (lambda *_: None)
    should_abort = should_abort or (lambda: False)
    stats = _new_stats()
    cutoff = (_today() - datetime.timedelta(days=RECENCY_DAYS)).isoformat()
    # Experiment folders that were active recently get re-listed unconditionally (a
    # handful of scandirs); everything else rides on the mtime check.
    active = {str(Path(r["path"]).parent) for r in conn.execute(
        "SELECT path FROM day_folders WHERE device=? AND date >= ?", (device, cutoff))}
    # Propagate a Stop pressed during the listing phase, so a half-done pass is never
    # reported as a clean finish; an unreachable root ends the pass with the cache as is.
    _merge_listing(stats, map_day_folders(root, device, conn, full=False,
                                          force_paths=active, progress_cb=progress_cb,
                                          should_abort=should_abort))
    if stats["aborted"] or stats["unreachable"]:
        return stats
    recent = conn.execute(          # re-queried: may now include a brand-new day folder
        "SELECT * FROM day_folders WHERE device=? AND date >= ? ORDER BY date DESC",
        (device, cutoff)).fetchall()
    progress_cb(0, len(recent), f"refreshing the last {RECENCY_DAYS} days ({len(recent)} folders)")
    _index_days(recent, device, conn, open_file, progress_cb, should_abort, stats)
    stats["days_indexed"] += len(recent)
    if not stats["aborted"]:
        fill_view(device, conn, needed, open_file, progress_cb, should_abort, stats,
                  done={r["path"] for r in recent})
    return stats


def open_device(root, device, conn, open_file=read_metadata, progress_cb=None,
                should_abort=None, needed: int = VIEW_ROWS) -> dict:
    """What runs on open / device select: warm refresh if the cache knows this device,
    otherwise a cold tier 0 + tier 1. Never a full walk."""
    if has_cache(device, conn):
        return refresh(root, device, conn, open_file, progress_cb, should_abort, needed)
    listed = map_day_folders(root, device, conn, full=True,
                             progress_cb=progress_cb, should_abort=should_abort)
    if listed["unreachable"]:
        return _merge_listing(_new_stats(), listed)
    stats = fill_view(device, conn, needed, open_file, progress_cb, should_abort)
    return _merge_listing(stats, listed)


def index_all(root, device, conn, scope: dict | None = None, open_file=read_metadata,
              progress_cb=None, should_abort=None) -> dict:
    """TIER 2: walk every day folder in ``scope`` (all of them when scope is empty).

    ON DEMAND ONLY. With an experiment scope this touches one of ~139 folders, which
    is the common case and ~100x cheaper than the full walk.
    """
    progress_cb = progress_cb or (lambda *_: None)
    should_abort = should_abort or (lambda: False)
    stats = _merge_listing(_new_stats(), map_day_folders(
        root, device, conn, full=True, progress_cb=progress_cb, should_abort=should_abort))
    if stats["aborted"] or stats["unreachable"]:
        return stats
    where, params = _scope_sql(device, scope)
    rows = conn.execute(f"SELECT * FROM day_folders WHERE {where}"
                        " ORDER BY (date IS NULL), date DESC", params).fetchall()
    progress_cb(0, len(rows), f"indexing {len(rows):,} day folders")
    _index_days(rows, device, conn, open_file, progress_cb, should_abort, stats)
    stats["days_indexed"] = len(rows)
    return stats


def scan(root, device, db_path=None, progress_cb=None, should_abort=None,
         open_file=read_metadata, conn=None) -> dict:
    """Unscoped TIER 2 convenience wrapper (used by 'Index all history' and tests)."""
    own = conn is None
    conn = conn or connect(db_path)
    try:
        return index_all(root, device, conn, None, open_file, progress_cb, should_abort)
    finally:
        if own:
            conn.close()


# --------------------------------------------------------------------------- #
# declarative filters -- ADD A FILTER BY ADDING ONE FilterSpec TO FILTERS
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class FilterSpec:
    """One user-facing filter.

    ``kind`` tells the UI which widget to build ('combo' | 'text' | 'daterange' |
    'lattice'); ``predicate(row, value)`` is the authority on whether a row passes.
    ``sql`` is an optional pre-filter -- an optimization, never the whole rule.
    ``day_scope(value)`` narrows which DAY FOLDERS could still hold matches, which is
    what makes the completeness label and the scoped tier-2 walk one-entry too.
    ``choices_column`` populates a 'combo' from the index; ``choices`` is a fixed list.
    """
    key: str
    label: str
    kind: str
    predicate: Callable[[dict, Any], bool]
    sql: Optional[Callable[[Any], tuple[str, list]]] = None
    day_scope: Optional[Callable[[Any], dict]] = None
    choices_column: Optional[str] = None
    choices: tuple[str, ...] = ()
    # combo only: type-ahead with suggestions (QCompleter, contains-match). The filter
    # applies only on a case-insensitive exact match, a picked suggestion, or Enter.
    editable: bool = False
    # Override when "the user set this" is not simply "the value is non-empty"
    # (the qubit filter always carries a match mode, so only its list counts).
    active: Optional[Callable[[Any], bool]] = None
    # True for filters that read a row's qubit set: they are what triggers the lazy
    # qubit lookup and the "no qubit info" note.
    qubit_based: bool = False


def is_set(value: Any) -> bool:
    """True when the user actually constrained this filter.

    Legacy-file behaviour hangs entirely off this: query() SKIPS unset filters, so a
    row with null qubit/group/name columns passes every filter the user has not set
    and is only ever excluded by one that IS set.
    """
    if value is None or value is ANY:
        return False
    if isinstance(value, str):
        return value.strip() != "" and value != ANY
    if isinstance(value, (list, tuple, set)):
        return any(is_set(v) for v in value)
    return True


def _row_qubits(row: dict) -> Optional[set]:
    """Chip numbers this run touched, as resolved by the fallback chain at index time
    ('qubits' holds the winner, 'qubit_readout' is kept raw). None when the file
    carries no qubit information at all."""
    for col in ("qubits", "qubit_readout"):
        raw = row.get(col)
        if raw:
            labels = {qubit_label(v) for v in json.loads(raw)}
            labels.discard(None)
            if labels:
                return labels
    return None


# Match modes, phrased relative to the LATTICE SELECTION so the filter reads
# left-to-right as "[Q3, Q5] = qubits". DEFAULT is exact.
QUBIT_MODES: dict[str, tuple[str, str, Callable[[set, set], bool]]] = {
    "=": ("exact", "runs on exactly these qubits",
          lambda selection, have: selection == have),
    "⊇": ("contains", "runs on any of these qubits, and no others",
               lambda selection, have: have <= selection),
    "⊆": ("within", "runs that include these qubits, possibly with others",
               lambda selection, have: selection <= have),
}
DEFAULT_QUBIT_MODE = "="


def _p_qubits(row, value) -> bool:
    # ``value`` is {'mode': <symbol>, 'qubits': [chip numbers]}. Rows with no qubit
    # information give have=None and fail -- but only because this filter is set;
    # unset filters never reach a predicate (see active_filters).
    have = _row_qubits(row)
    if have is None:
        return False
    test = QUBIT_MODES.get(value.get("mode") or DEFAULT_QUBIT_MODE, QUBIT_MODES["="])[2]
    return test(set(value["qubits"]), have)


def _p_nq(row, value) -> bool:
    n = row.get("n_readout")
    return n is not None and {"1Q": n == 1, "2Q": n == 2, "MQ": n >= 3}.get(value, True)


def _p_text(col: str):
    return lambda row, value: bool(row.get(col)) and value.lower() in str(row[col]).lower()


def _p_daterange(row, value) -> bool:
    lo, hi = value
    day = (row.get("timestamp") or "")[:10]
    return bool(day) and (not lo or day >= lo) and (not hi or day <= hi)


def _sql_daterange(value):
    lo, hi = value
    clauses, params = [], []
    if lo:
        clauses.append("substr(timestamp,1,10) >= ?")
        params.append(lo)
    if hi:
        clauses.append("substr(timestamp,1,10) <= ?")
        params.append(hi)
    return " AND ".join(clauses), params


# Filters on columns that only post-cutover files carry (class, group, name) can only ever
# match those, so pre-cutover day folders need not be indexed for the answer to be complete.
# The qubit-based filters are deliberately NOT scoped this way: old runs can match too, via
# the lazy lookup of their `config` attr, so their completeness needs the whole history.
_META_SCOPE = lambda _v: {"date_lo": METADATA_CUTOVER}

FILTERS: list[FilterSpec] = [
    FilterSpec("experiment", "Experiment (folder)", "combo",
               predicate=lambda row, v: row.get("experiment") == v,
               sql=lambda v: ("experiment = ?", [v]),
               day_scope=lambda v: {"experiment": v},
               choices_column="experiment", editable=True),
    FilterSpec("experiment_class", "Class name", "text",
               predicate=_p_text("experiment_class"), day_scope=_META_SCOPE),
    FilterSpec("qubits", "Qubits", "lattice", predicate=_p_qubits, qubit_based=True,
               active=lambda v: bool((v or {}).get("qubits"))),
    FilterSpec("nq", "1Q / 2Q / MQ", "combo", predicate=_p_nq, qubit_based=True,
               choices=("1Q", "2Q", "MQ")),
    FilterSpec("group_name", "Group name", "text",
               predicate=_p_text("group_name"), day_scope=_META_SCOPE),
    FilterSpec("name", "Name", "text",
               predicate=_p_text("name"), day_scope=_META_SCOPE),
    FilterSpec("date", "Date range", "daterange", predicate=_p_daterange,
               sql=_sql_daterange,
               day_scope=lambda v: {"date_lo": v[0], "date_hi": v[1]}),
]


def active_filters(values: dict) -> list[tuple[FilterSpec, Any]]:
    """The (spec, value) pairs the user actually set; everything else is skipped."""
    return [(s, values.get(s.key)) for s in FILTERS
            if (s.active or is_set)(values.get(s.key))]


def row_passes(row: dict, values: dict) -> bool:
    return all(spec.predicate(row, value) for spec, value in active_filters(values))


def day_scope(values: dict) -> dict:
    """Intersect every active filter's day_scope: which day folders could still match.

    An empty dict means "any day folder", i.e. completeness needs the whole history.
    """
    scope: dict = {}
    for spec, value in active_filters(values):
        if spec.day_scope is None:
            return {}                           # this filter could match anything
        for key, val in spec.day_scope(value).items():
            if val is None:
                continue
            if key == "date_lo":
                scope[key] = max(scope.get(key, ""), val)
            elif key == "date_hi":
                scope[key] = min(scope.get(key, "9999"), val)
            else:
                scope[key] = val
    return scope


def _scope_sql(device: str, scope: dict | None) -> tuple[str, list]:
    where, params = ["device = ?"], [device]
    for key, column, op in (("experiment", "experiment", "="),
                            ("date_lo", "date", ">="), ("date_hi", "date", "<=")):
        val = (scope or {}).get(key)
        if val:
            # date IS NULL folders are undated: they can hold anything, so a date
            # bound never excludes them.
            where.append(f"({column} {op} ?" + (" OR date IS NULL)" if column == "date" else ")"))
            params.append(val)
    return " AND ".join(where), params


def horizon(device: str, values: dict | None = None, conn=None, db_path=None) -> dict:
    """How complete the current view is, for the scope the active filters imply.

    Returns {'complete', 'unindexed_days', 'newest_unindexed', 'undated_unindexed',
             'total_days', 'scope'}.
    """
    own = conn is None
    conn = conn or connect(db_path)
    try:
        scope = day_scope(values or {})
        where, params = _scope_sql(device, scope)
        row = conn.execute(
            f"SELECT COUNT(*) n, MAX(date) newest,"
            f" SUM(CASE WHEN date IS NULL THEN 1 ELSE 0 END) undated"
            f" FROM day_folders WHERE {where} AND indexed=0", params).fetchone()
        total = conn.execute(f"SELECT COUNT(*) FROM day_folders WHERE {where}",
                             params).fetchone()[0]
        return {"complete": (row["n"] or 0) == 0, "unindexed_days": row["n"] or 0,
                "newest_unindexed": row["newest"], "undated_unindexed": row["undated"] or 0,
                "total_days": total, "scope": scope}
    finally:
        if own:
            conn.close()


def query(values: dict | None = None, device: str | None = None, db_path=None,
          conn=None, limit: int = 500) -> tuple[list[dict], int]:
    """Return (rows newest-first capped at ``limit``, total matching IN THE CACHE).

    SQL pre-filters where a spec offers one, then every active predicate runs in
    Python. The cap is applied LAST so "showing 500 of N" reports the true N.
    Pair with ``horizon()`` -- N counts only what has been indexed so far.
    """
    values = values or {}
    own = conn is None
    conn = conn or connect(db_path)
    try:
        where: list[str] = []
        params: list = []
        if device:
            where.append("device = ?")
            params.append(device)
        active = active_filters(values)
        in_sql = 0
        for spec, value in active:
            if spec.sql is None:
                continue
            clause, extra = spec.sql(value)
            if clause:
                where.append(f"({clause})")
                params.extend(extra)
                in_sql += 1
        tail = (" WHERE " + " AND ".join(where)) if where else ""
        # (timestamp IS NULL) first: SQLite sorts NULL smallest, which DESC would
        # otherwise float unparseable-name files to the top.
        order = " ORDER BY (timestamp IS NULL), timestamp DESC, path DESC"
        if in_sql == len(active):
            # SQL already expresses the whole filter, so COUNT + LIMIT is exact and we
            # skip materializing ~40k dicts just to drop all but 500 of them.
            total = conn.execute(f"SELECT COUNT(*) FROM files{tail}", params).fetchone()[0]
            rows = [dict(r) for r in
                    conn.execute(f"SELECT * FROM files{tail}{order} LIMIT ?",
                                 params + [int(limit)])]
            return rows, total
        rows = [dict(r) for r in conn.execute(f"SELECT * FROM files{tail}{order}", params)]
        rows = [r for r in rows if row_passes(r, values)]
        return rows[:limit], len(rows)
    finally:
        if own:
            conn.close()


def distinct(column: str, device: str | None = None, table: str = "files",
             db_path=None, conn=None) -> list[str]:
    """Distinct non-null values of a column, for populating combo filters.

    Experiment names come from ``day_folders`` rather than ``files``: tier 0 knows all
    139 of them after ~4 s, long before their files are indexed.
    """
    own = conn is None
    conn = conn or connect(db_path)
    try:
        sql = f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL"
        params: list = []
        if device:
            sql += " AND device = ?"
            params.append(device)
        return sorted(str(r[0]) for r in conn.execute(sql, params))
    finally:
        if own:
            conn.close()


def available_devices(json_dir=DEVICE_JSON_DIR) -> list[str]:
    """Device names that have a device json (stem == data-root folder name).

    Driven by the LOCAL json directory, not a listing of the network root, so the
    window constructs instantly even when Z: is slow or unmapped; reachability of
    <DATA_ROOT>/<device> is checked on the worker thread.
    """
    try:
        return sorted(p.stem for p in Path(json_dir).glob("*.json"))
    except OSError:
        return []


# --------------------------------------------------------------------------- #
# lazy qubit lookup for files that predate save_metadata
# --------------------------------------------------------------------------- #

def qubit_filter_active(values: dict) -> bool:
    return any(spec.qubit_based for spec, _ in active_filters(values))


def _other_filters(values: dict) -> dict:
    """``values`` with the qubit-based filters unset."""
    return {k: v for k, v in values.items()
            if not any(s.key == k and s.qubit_based for s in FILTERS)}


def _unknown_where(values: dict, device: str, unchecked_only: bool):
    """(where, params, python_side) selecting rows with unknown qubit info that pass every
    NON-qubit filter. SQL does those filters where a spec offers it; any spec without
    SQL comes back in ``python_side`` to apply per row."""
    where = ["device = ?", "qubits IS NULL", "qubit_readout IS NULL"]
    params: list = [device]
    if unchecked_only:
        where.append("qubit_source IS NULL")
    else:
        where.append("(qubit_source IS NULL OR qubit_source = ?)")
        params.append(SOURCE_UNAVAILABLE)
    python_side = []
    for spec, value in active_filters(_other_filters(values)):
        clause, extra = spec.sql(value) if spec.sql else ("", [])
        if clause:
            where.append(f"({clause})")
            params.extend(extra)
        else:
            python_side.append((spec, value))
    return " AND ".join(where), params, python_side


def _unknown_rows(values: dict, device: str, conn, unchecked_only: bool):
    """Rows passing every NON-qubit filter whose qubit set is unknown, newest first.
    Rows failing another filter are never yielded -- so never opened."""
    where, params, python_side = _unknown_where(values, device, unchecked_only)
    sql = (f"SELECT * FROM files WHERE {where}"
           " ORDER BY (timestamp IS NULL), timestamp DESC, path DESC")
    for r in conn.execute(sql, params):
        row = dict(r)
        if all(spec.predicate(row, v) for spec, v in python_side):
            yield row


def qubit_unknown_counts(values: dict, device: str, conn) -> dict:
    """{'unchecked': rows not yet read, 'unavailable': rows read and found without qubit
    info} among rows passing every other filter. One SQL COUNT when every other active
    filter has an SQL form (the usual case); a Python pass otherwise."""
    where, params, python_side = _unknown_where(values, device, unchecked_only=False)
    if not python_side:
        r = conn.execute(
            f"SELECT SUM(qubit_source IS NULL), SUM(qubit_source = ?) FROM files WHERE {where}",
            [SOURCE_UNAVAILABLE, *params]).fetchone()
        return {"unchecked": r[0] or 0, "unavailable": r[1] or 0}
    unchecked = unavailable = 0
    for row in _unknown_rows(values, device, conn, unchecked_only=False):
        if row["qubit_source"] == SOURCE_UNAVAILABLE:
            unavailable += 1
        else:
            unchecked += 1
    return {"unchecked": unchecked, "unavailable": unavailable}


def read_config_qubits(path: str):
    """Qubit_Readout_List from a file's ``config`` root attr (the chain's last rung).

    Read-only through open_for_reading, so it never blocks a save and raises
    FileBeingSaved while one is in progress. Returns None when the key is absent."""
    with open_for_reading(path) as f:
        blob = f.attrs.get("config")
    if blob is None:
        return None
    if isinstance(blob, (bytes, np.bytes_)):
        blob = blob.decode("utf-8", "replace")
    value = json.loads(blob).get("Qubit_Readout_List")
    value = _jsonable(value)
    return list(value) if isinstance(value, (list, tuple)) and len(value) else None


def lazy_qubit_pass(values: dict, device: str, conn, budget: Optional[int] = None,
                    row_cap: Optional[int] = None, reader=None, progress_cb=None,
                    should_abort=None, commit_every: Optional[int] = None) -> dict:
    """Read qubit info for unknown candidates, newest first, ONLY under a qubit filter.

    Candidates pass every other active filter (others are never opened). Reads at most
    ``budget`` files and stops early once ``row_cap`` rows match the full filter. Found
    lists become qubit_source='config'; FileBeingSaved leaves the row untouched (retried
    later, no sentinel); a missing key or any other failure stores SOURCE_UNAVAILABLE so
    the file is never re-read. Every outcome but busy is written to qubit_memo.
    """
    budget = PASS_BUDGET if budget is None else budget
    row_cap = ROW_CAP if row_cap is None else row_cap
    reader = reader or read_config_qubits
    commit_every = commit_every or LAZY_COMMIT_EVERY
    progress_cb = progress_cb or (lambda stats: None)
    should_abort = should_abort or (lambda: False)
    stats = {"opened": 0, "found": 0, "unavailable": 0, "busy": 0, "missing": 0,
             "matched": 0, "remaining": 0, "complete": False, "table_full": False,
             "aborted": False, "unreachable": False, "active": True}
    if not qubit_filter_active(values):
        stats["active"] = False                  # nothing is EVER read without one
        return stats
    _, matches = query(values, device, conn=conn, limit=1)
    candidates = list(_unknown_rows(values, device, conn, unchecked_only=True))
    for row in candidates:
        if stats["opened"] >= budget or matches >= row_cap:
            break
        if should_abort():
            stats["aborted"] = True
            break
        stats["opened"] += 1
        try:
            found = reader(row["path"])
        except FileBeingSaved:
            stats["busy"] += 1                   # untouched: a later pass retries it
            continue
        except Exception:
            # Only a file that is THERE but unreadable earns the permanent sentinel. A
            # vanished file (deleted, or the share dropped mid-pass) is skipped; if its
            # folder is gone too the share is down, so stop rather than burn the budget.
            if not os.path.exists(row["path"]):
                stats["missing"] += 1
                if not os.path.isdir(os.path.dirname(row["path"])):
                    stats["unreachable"] = True
                    break
                continue
            found = None
        if found:
            info = {"qubit_readout": json.dumps(found), "qubits": json.dumps(found),
                    "n_readout": len(found), "qubit_source": "config"}
            stats["found"] += 1
        else:
            info = {"qubit_readout": None, "qubits": None, "n_readout": None,
                    "qubit_source": SOURCE_UNAVAILABLE}
            stats["unavailable"] += 1
        conn.execute("UPDATE files SET qubit_readout=?, qubits=?, n_readout=?, "
                     "qubit_source=? WHERE path=?",
                     (*(info[f] for f in _QUBIT_FIELDS), row["path"]))
        conn.execute("INSERT OR REPLACE INTO qubit_memo(path, mtime, qubit_readout, qubits,"
                     " n_readout, qubit_source) VALUES (?,?,?,?,?,?)",
                     (row["path"], row["mtime"], *(info[f] for f in _QUBIT_FIELDS)))
        if found and row_passes({**row, **info}, values):
            matches += 1
            stats["matched"] += 1
        if stats["opened"] % commit_every == 0:
            conn.commit()
            progress_cb(dict(stats))
    conn.commit()
    counts = qubit_unknown_counts(values, device, conn)
    stats["remaining"] = counts["unchecked"]
    stats["complete"] = counts["unchecked"] == 0          # nothing left to read
    stats["table_full"] = matches >= row_cap              # stopped early: view is full
    progress_cb(dict(stats))
    return stats
