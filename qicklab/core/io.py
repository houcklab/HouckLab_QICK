"""Run-level file output: timestamped names, npz + config-json records, cycle summaries,
and the provenance record attached to saved files (docs/architecture.md#provenance)."""

import dataclasses
import hashlib
import importlib.metadata
import json
import os
import platform
import socket
import subprocess
import sys
import time
from datetime import datetime

import numpy as np

from qicklab.core.device import ParityParams, Qubit, source
from qicklab.hardware.yoko import last_levels


def timestamp():
    """Wall-clock stamp used in run-level file names (%Y_%m_%d_%H_%M_%S)."""
    return datetime.now().strftime("%Y_%m_%d_%H_%M_%S")


def save_record(base, cfg, exp=None, /, **arrays):
    """Write `<base>.npz` (arrays, keys in call order), `<base>_config.json` (cfg) and
    `<base>_provenance.json` (write_provenance; never raises).

    `exp`, the experiment that acquired the record, adds its class, h5 name, start time and,
    when it keeps `self.prog`, the program hash to the provenance (experiment_fields).
    """
    np.savez(base + ".npz", **arrays)
    with open(base + "_config.json", "w") as f:
        json.dump(cfg, f, indent=2, default=float)
    write_provenance(base, **(_safe(lambda: experiment_fields(exp)) or {}))


def save_cycle_summary(save_dir, rows):
    """Write the per-cycle summary rows to `<save_dir>/CycleSummary_<timestamp>.json`."""
    summary_path = os.path.join(save_dir, f"CycleSummary_{timestamp()}.json")
    with open(summary_path, "w") as f:
        json.dump(rows, f, indent=2, default=float)


# --------------------------------------------------------------------------------------------
# Provenance (docs/architecture.md#provenance). Never stored in a cfg or a save_data payload.
# Times come from time.time(), never datetime.now(): recording them must not move a
# timestamped file name.
# --------------------------------------------------------------------------------------------
PROVENANCE_VERSION = 1
PROVENANCE_SUFFIX = "_provenance.json"
GIT_TIMEOUT_S = 5.0

_SESSION = {}  # set by start_session (build_context); JSON-ready values only
_SESSION_SOCCFG = [None]  # the session's QickConfig, summarised lazily
_STATIC = {}  # per-process facts (versions, host, script, git), computed once
_SOCCFG_CACHE = [None, None]  # [soccfg object, its summary]: dump_cfg hashed once per board


def iso_time(t):
    """Local ISO-8601 time with UTC offset (second precision) of a time.time() value."""
    lt = time.localtime(t)
    off = lt.tm_gmtoff or 0
    sign = "+" if off >= 0 else "-"
    off = abs(off)
    return (
        time.strftime("%Y-%m-%dT%H:%M:%S", lt) + f"{sign}{off // 3600:02d}:{off % 3600 // 60:02d}"
    )


def start_session(soccfg=None, **fields):
    """Replace the session record that provenance() attaches to every later save.

    build_context calls it once per connect (device, data_root, qubit_readout, qubit_pulse,
    RFSoC endpoint, yoko address, start voltage, ...). `soccfg` is kept by reference and
    summarised (board, sw_version, fw_timestamp, sha1) at the first save.
    """
    _SESSION.clear()
    _SESSION.update(fields)
    _SESSION["session_start_time"] = iso_time(time.time())
    _SESSION_SOCCFG[0] = soccfg


def session():
    """A copy of the current session record (empty before build_context)."""
    return dict(_SESSION)


def _clear_provenance_cache():
    """Forget the per-process facts and the board summary (tests)."""
    _STATIC.clear()
    _SOCCFG_CACHE[0] = _SOCCFG_CACHE[1] = None


def _safe(fn):
    try:
        return fn()
    except Exception:
        return None


def _repo_dir():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _git(*args):
    """stdout of `git <args>` run in the repo; raises if git is missing, fails or times out."""
    kwargs = {}
    if os.name == "nt":  # no console window flashing up from a GUI session
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    out = subprocess.run(
        ["git", "-C", _repo_dir(), *args],
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_S,
        check=True,
        **kwargs,
    )
    return out.stdout.strip()


def _qick_version():
    """The qick client version, without importing qick (analysis runs without it)."""
    qick = sys.modules.get("qick")
    if qick is not None and hasattr(qick, "get_version"):
        return qick.get_version()
    return importlib.metadata.version("qick")


def _script():
    """The running script's absolute path; None in a REPL or under `python -c`."""
    arg = sys.argv[0] if sys.argv else ""
    return os.path.abspath(arg) if arg and arg != "-c" else None


def _static():
    """qick/python versions, host, script and git commit + dirty flag; computed once."""
    if not _STATIC:
        commit = _safe(lambda: _git("rev-parse", "HEAD") or None)
        dirty = None
        if commit is not None:
            dirty = _safe(lambda: bool(_git("status", "--porcelain", "--untracked-files=no")))
        _STATIC.update(
            qick_version=_safe(_qick_version),
            python_version=_safe(platform.python_version),
            hostname=_safe(socket.gethostname),
            script=_safe(_script),
            git_commit=commit,
            git_dirty=dirty,
        )
    return dict(_STATIC)


def _soccfg_summary(soccfg):
    """{soccfg_board, soccfg_sw_version, soccfg_fw_timestamp, soccfg_sha1}; cached per object."""
    if soccfg is None:
        return {}
    if _SOCCFG_CACHE[0] is soccfg:
        return dict(_SOCCFG_CACHE[1])
    cfg = _safe(soccfg.get_cfg) or {}
    summary = {
        "soccfg_board": _safe(lambda: cfg.get("board")),
        "soccfg_sw_version": _safe(lambda: cfg.get("sw_version")),
        "soccfg_fw_timestamp": _safe(lambda: cfg.get("fw_timestamp")),
        "soccfg_sha1": _safe(lambda: hashlib.sha1(soccfg.dump_cfg().encode()).hexdigest()),
    }
    _SOCCFG_CACHE[0], _SOCCFG_CACHE[1] = soccfg, summary
    return dict(summary)


def _bias_levels():
    return {
        name: {**rec, "time": iso_time(rec["time"]) if rec.get("time") else None}
        for name, rec in last_levels().items()
    }


def experiment_fields(exp):
    """The provenance() kwargs that describe experiment `exp` ({} for None).

    Reads only soccfg, prog (when the class keeps its program), fname, outerFolder and the
    construction time `_provenance_t0`; never the cfg.
    """
    if exp is None:
        return {}
    return {
        "soccfg": getattr(exp, "soccfg", None),
        "prog": getattr(exp, "prog", None),
        "t_start": getattr(exp, "_provenance_t0", None),
        "experiment_class": type(exp).__name__,
        "outer_folder": getattr(exp, "outerFolder", None),
        "data_file": getattr(exp, "fname", None),
    }


def provenance(soccfg=None, prog=None, t_start=None, **extra):
    """Who/what/when of a save, as a JSON-ready dict; never raises.

    Keys: provenance_version; qick_version, python_version, hostname, script, git_commit,
    git_dirty (None when git is unavailable); soccfg_board, soccfg_sw_version,
    soccfg_fw_timestamp, soccfg_sha1 (of `soccfg`, else the session's board); the session
    record (device, data_root, qubit_readout, qubit_pulse, rfsoc_*, yoko_addr, start_voltage,
    yoko_fixed, session_start_time); `bias` (per source, the last level a ramp landed on and
    its :SOUR:LEV? read-back, recorded by the ramp: no new GPIB query); program_class and
    program_asm_sha1 when `prog` is given; start_time (`t_start`, a time.time() value) and
    end_time (now); then `extra`. A piece that cannot be determined is None.
    """
    try:
        record = {"provenance_version": PROVENANCE_VERSION}
        record.update(_static())
        record.update(_soccfg_summary(soccfg if soccfg is not None else _SESSION_SOCCFG[0]))
        record.update(_SESSION)
        record["bias"] = _safe(_bias_levels)
        if prog is not None:
            record["program_class"] = type(prog).__name__
            record["program_asm_sha1"] = _safe(
                lambda: hashlib.sha1(prog.asm().encode()).hexdigest()
            )
        record["start_time"] = _safe(lambda: iso_time(t_start)) if t_start is not None else None
        record["end_time"] = iso_time(time.time())
        record.update(extra)
        return record
    except Exception as exc:  # never block a save
        return {"provenance_version": PROVENANCE_VERSION, "provenance_error": repr(exc)}


def provenance_json(**kwargs):
    """provenance(**kwargs) as a JSON string (other values via str), or None on failure."""
    try:
        return json.dumps(provenance(**kwargs), indent=2, default=str)
    except Exception:
        return None


def write_provenance(stem, **kwargs):
    """Write provenance(**kwargs) to `<stem>_provenance.json`; return the path, or None.

    Never raises: a failure is printed and the caller's save goes on.
    """
    text = provenance_json(**kwargs)
    return None if text is None else write_provenance_text(stem, text)


def write_provenance_text(stem, text):
    """Write the provenance JSON `text` to `<stem>_provenance.json`; return the path, or None.

    A plain write (no tmp + replace: the cfg json keeps its replace/retry budget to itself).
    Never raises: a failure is printed and the caller's save goes on.
    """
    path = stem + PROVENANCE_SUFFIX
    try:
        with open(path, "w") as f:
            f.write(text)
        return path
    except Exception as exc:
        print(f"[provenance] could not write {path}: {exc!r}")
        return None


# --------------------------------------------------------------------------------------------
# Calibration write-back and the zero-span cache (docs/adding_a_device.md#calibration-write-back).
# Both live in the qubit's data folder; neither ever edits devices/<NAME>.py.
# --------------------------------------------------------------------------------------------
CALIBRATIONS_FILE = "calibrations.jsonl"
ZSP_CACHE_FILE = "zsp_cache.json"
ZSP_CACHE_VERSION = 1
ZSP_CACHED = ("ZSP_ParityFreqs_Cached", "ZSP_Separator_Cached")  # the run's in-place caches

# record_calibration keyword -> (part of the Qubit, field): Qubit fields as they are, the
# readout's and the parity calibration's with a readout_ / parity_ prefix
_QUBIT_PART = {
    f.name: ("qubit", f.name)
    for f in dataclasses.fields(Qubit)
    if f.name not in ("readout", "parity", "notes")
}
_QUBIT_PART.update(
    {f"readout_{n}": ("readout", n) for n in ("freq", "gain", "kappa_mhz")},
)
_QUBIT_PART.update(
    {f"parity_{f.name}": ("parity", f.name) for f in dataclasses.fields(ParityParams)}
)


def qubit_file(device, q, name):
    """`<data_root>/Q{q}/<name>`: a per-qubit file beside the qubit's data folders."""
    return f"{device.data_root}/Q{q}/{name}"


def _plain(value):
    """JSON-ready copy: numpy scalars -> numbers, arrays -> lists, tuples -> lists."""
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def record_calibration(device, q, *, step=None, **values):
    """Append `values` measured on qubit q to calibrations.jsonl; print a paste-ready Qubit line.

    Keywords: a Qubit field (freq, gain, pi2_gain, sigma, ...), readout_freq / readout_gain /
    readout_kappa_mhz, or parity_<ParityParams field>; anything else raises TypeError before a
    write. Returns the updated Qubit (`device.with_qubit` for a trial). A failed write is
    printed, never raised: the measurement is already saved.
    """
    if q not in device.qubits:
        raise KeyError(f"{device.name} has no qubit {q!r}; qubits are {sorted(device.qubits)}")
    unknown = sorted(set(values) - set(_QUBIT_PART))
    if unknown:
        raise TypeError(f"record_calibration: unknown keys {unknown}; known: {sorted(_QUBIT_PART)}")
    if not values:
        raise ValueError("record_calibration: no values given")
    values = {k: _plain(v) for k, v in values.items()}
    parts = {"qubit": {}, "readout": {}, "parity": {}}
    for key, value in values.items():
        part, name = _QUBIT_PART[key]
        parts[part][name] = value
    qb = device.qubits[q]
    changes = dict(parts["qubit"])
    if parts["readout"]:
        changes["readout"] = dataclasses.replace(qb.readout, **parts["readout"])
    note = ""
    if parts["parity"]:
        if qb.parity is not None:
            changes["parity"] = dataclasses.replace(qb.parity, **parts["parity"])
        elif {"df_mhz", "f_upper_mhz"} <= set(parts["parity"]):
            changes["parity"] = ParityParams(**parts["parity"])
        else:
            note = " (parity values not in the line: the qubit has no ParityParams yet)"
    new = dataclasses.replace(qb, **changes)

    path = qubit_file(device, q, CALIBRATIONS_FILE)
    record = {
        "time": iso_time(time.time()),
        "device": device.name,
        "cooldown": device.cooldown,
        "qubit": q,
        "step": step,
        "values": values,
    }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(record, default=str) + "\n")
        where = path
    except Exception as exc:
        where = f"NOT written ({exc!r})"
    shown = ", ".join(f"{k}={v!r}" for k, v in values.items())
    print(f"[calibration] {device.name} Q{q} ({step or 'manual'}): {shown} -> {where}{note}")
    print(f"    {q}: {source(new)},")
    return new


def zsp_cache_path(device, q):
    """`<data_root>/Q{q}/zsp_cache.json`."""
    return qubit_file(device, q, ZSP_CACHE_FILE)


def read_zsp_cache(device, q):
    """The zero-span cache record of qubit q ({ZSP_ParityFreqs_Cached, ZSP_Separator_Cached,
    qubit_readout, qubit_pulse, time, ...}), separator values as arrays; None if absent or unreadable.
    """
    path = zsp_cache_path(device, q)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            record = json.load(f)
        sep = record["ZSP_Separator_Cached"]
        record["ZSP_Separator_Cached"] = {
            k: None if v is None else np.asarray(v, dtype=float) for k, v in sep.items()
        }
        if not isinstance(record.get("ZSP_ParityFreqs_Cached"), dict):
            raise ValueError("no ZSP_ParityFreqs_Cached dict")
        return record
    except Exception as exc:
        print(f"[zsp cache] ignoring unreadable {path}: {exc!r}")
        return None


def write_zsp_cache(device, q, parity_freqs, separator, **meta):
    """Write the run's two caches (and `meta`, e.g. qubit_readout) to zsp_cache.json.

    Replaces the file atomically; returns the path, or None after printing a failed write.
    """
    path = zsp_cache_path(device, q)
    record = {
        "version": ZSP_CACHE_VERSION,
        "time": iso_time(time.time()),
        "device": device.name,
        "cooldown": device.cooldown,
        "qubit": q,
        **_plain(meta),
        "ZSP_ParityFreqs_Cached": _plain(dict(parity_freqs)),
        "ZSP_Separator_Cached": _plain(dict(separator)),
    }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(record, f, indent=2, default=str)
        os.replace(tmp, path)
        return path
    except Exception as exc:
        print(f"[zsp cache] could not write {path}: {exc!r}")
        return None
