"""Hardware-free capture core for the config regression harness.

Everything here is layout-agnostic: the driver hands in the ExperimentClass base,
the modules that bind ``makeProxy`` and the ``pyvisa`` modules to patch, so the
same core runs unchanged against the legacy and the refactored code.

What gets recorded per run (see ``begin_run`` / ``end_run``):
  * every ExperimentClass instantiation (the first ``PER_KIND`` of each
    ``(class, path)`` pair): class, path, outerFolder, full cfg (taken right
    after ``ExperimentClass.__init__``), and the wrapped methods called on it,
    in order, with their non-data kwargs, the public attributes each call set,
    and digests of the ``save_data`` payload / the cfg at ``save_config``;
  * a digest of every command the experiment sent to the (fake) QICK board
    while its ``acquire`` ran: compiled tProc binaries, pulse envelopes, gen /
    readout / buffer configuration and readout requests;
  * every yoko ``write``/``query``/``close``;
  * which cfg keys each experiment class read and wrote (``cfg_access``);
  * how many instantiations were skipped per ``(class, path)`` pair.

``acquire`` and ``display`` are NOT stubbed: ``acquire`` runs for real against
``FakeSoc``, which answers readout requests with seeded synthetic data of
exactly the shape QICK would return; ``display`` runs under Agg (show / pause /
savefig are no-ops) and an exception it raises on synthetic data is recorded
and swallowed. ``save_data``/``save_config`` run for real into the per-run temp
dir (downstream analysis reads those files back).
"""

import copy
import datetime as _dt
import functools
import hashlib
import importlib
import json
import logging
import os
import random
import re
import sys
import time
import types
import zlib

import numpy as np
from qick import get_version

# the fakes live in qicklab.core.fakes (shared with dry_run); re-exported under their old names
from qicklab.core.fakes import (  # noqa: F401
    _SKIPPED,
    BOARDS,
    STATE,
    SYNTHETIC_SOCCFG,
    VARIANTS,
    FakeResourceManager,
    FakeSoc,
    FakeSocCfg,
    FakeYoko,
    _fingerprint,
    _numeric,
    _State,
    current_board,
    fake_make_proxy,
    set_board,
)

PER_KIND = 4  # instantiations captured per (class name, path) pair
MAX_TOTAL = 60  # instantiations (captured + skipped) per run before StopCapture
MAX_SKIPS = 200  # skips of one (class, path) pair before StopCapture (runaway loop)
MAX_IDLE = 8  # consecutive skipped instantiations (nothing new captured) before StopCapture
WRAPPED = ("acquire", "display", "save_data", "save_config", "analyze")
SWALLOW = frozenset({"display"})  # exceptions recorded, not propagated
SETS_SKIP = frozenset({"cfg", "soc", "soccfg", "data", "prog"})
CAPTURE = []  # every experiment record of the session, each tagged with its run


class StopCapture(BaseException):
    """Raised when a run exceeds its budget. BaseException so that the code
    under test cannot swallow it with ``except Exception``."""


class FakeDateTime(_dt.datetime):
    """Virtual clock: each now() is one second after the previous one.

    With time.sleep disabled, back-to-back experiments would otherwise share a
    timestamped filename and collide in the h5 file. Restarts every run.
    """

    @classmethod
    def now(cls, tz=None):
        STATE.clock += 1
        return _dt.datetime(2026, 1, 1, tzinfo=tz) + _dt.timedelta(seconds=STATE.clock)

    @classmethod
    def today(cls):
        return cls.now()


FAKE_DATETIME_MODULE = types.ModuleType("datetime")
FAKE_DATETIME_MODULE.__dict__.update(vars(_dt))
FAKE_DATETIME_MODULE.datetime = FakeDateTime


# --------------------------------------------------------------------------
# Recording cfg
# --------------------------------------------------------------------------
class RecordingDict(dict):
    """A dict that logs which (string) keys are read and written.

    ``ExperimentClass.__init__`` stores ``RecordingDict(cfg)`` as ``self.cfg``.
    It is a real ``dict`` (``isinstance`` checks, ``json.dump``, ``dict(...)``,
    ``**cfg`` all work on its own storage, unrecorded). Explicit lookups
    (``[]``, ``get``, ``in``, ``setdefault``) are answered from the ORIGINAL dict
    and every mutation is applied to both, so the aliasing the code under test
    relies on (the caller's dict and ``self.cfg`` being one object) is
    preserved for everything except iteration after a caller-side mutation.
    Copies (``dict(cfg)``, ``cfg.copy()``, ``copy.copy``/``deepcopy``) are plain
    dicts and are not recorded.
    """

    __slots__ = ("_origin", "_access")

    def __init__(self, origin=None, access=None):
        origin = {} if origin is None else origin
        if isinstance(origin, RecordingDict):
            origin = origin._origin
        dict.__init__(self, origin)
        self._origin = origin
        self._access = access if access is not None else {"read": set(), "written": set()}

    def _mark(self, kind, key):
        if isinstance(key, str):
            self._access[kind].add(key)

    def __getitem__(self, key):
        self._mark("read", key)
        return self._origin[key]

    def get(self, key, default=None):
        self._mark("read", key)
        return self._origin.get(key, default)

    def __contains__(self, key):
        self._mark("read", key)
        return key in self._origin

    def setdefault(self, key, default=None):
        self._mark("read", key)
        if key not in self._origin:
            self._mark("written", key)
        value = self._origin.setdefault(key, default)
        dict.__setitem__(self, key, value)
        return value

    def __setitem__(self, key, value):
        self._mark("written", key)
        self._origin[key] = value
        dict.__setitem__(self, key, value)

    def __delitem__(self, key):
        self._mark("written", key)
        del self._origin[key]
        dict.pop(self, key, None)

    def pop(self, key, *default):
        self._mark("written", key)
        dict.pop(self, key, None)
        return self._origin.pop(key, *default)

    def popitem(self):
        key, value = self._origin.popitem()
        self._mark("written", key)
        dict.pop(self, key, None)
        return key, value

    def clear(self):
        for key in self._origin:
            self._mark("written", key)
        self._origin.clear()
        dict.clear(self)

    def update(self, *args, **kwargs):
        new = dict(*args, **kwargs)
        for key in new:
            self._mark("written", key)
        self._origin.update(new)
        dict.update(self, new)

    def __ior__(self, other):
        self.update(other)
        return self

    def __or__(self, other):
        if not isinstance(other, dict):
            return NotImplemented
        return {**self._origin, **other}

    def __ror__(self, other):
        if not isinstance(other, dict):
            return NotImplemented
        return {**other, **self._origin}

    def copy(self):
        return dict(self._origin)

    def __copy__(self):
        return dict(self._origin)

    def __deepcopy__(self, memo):
        return copy.deepcopy(dict(self._origin), memo)

    def __reduce_ex__(self, protocol):
        return (dict, (dict(self._origin),))


def begin_run(label, data_root):
    """Reset per-run state; seeds every RNG from the label (order-independent)."""
    seed = zlib.crc32(label.encode())
    STATE.__init__()
    STATE.run, STATE.data_root, STATE.rng = label, data_root, np.random.default_rng(seed)
    np.random.seed(seed)
    random.seed(seed)


def end_run():
    """Finalise and return {experiments, yoko, hw_outside_experiments, skipped, cfg_access}."""
    for rec in STATE.records:
        rec["hw"] = _hw_summary(STATE.hashers.get(id(rec)))
    out = {
        "experiments": STATE.records,
        "yoko": [normalize(s) for s in STATE.yoko],
        "hw_outside_experiments": _hw_summary(STATE.hashers.get(None)),
        "skipped": dict(sorted(STATE.skipped.items())),
        "cfg_access": {
            cls: {"read": sorted(acc["read"]), "written": sorted(acc["written"])}
            for cls, acc in sorted(STATE.cfg_access.items())
        },
    }
    STATE.run = None
    return out


def _hw_summary(entry):
    if entry is None:
        return None
    hasher, counts = entry
    programs = counts.pop("_programs", [])
    return {
        "calls": dict(sorted(counts.items())),
        "n_programs": len(programs),
        "n_unique_programs": len(set(programs)),
        "first_program": programs[0] if programs else None,
        "digest": hasher.hexdigest()[:32],
    }


# --------------------------------------------------------------------------
# Normalisation to deterministic JSON
# --------------------------------------------------------------------------
_TIMESTAMP_PATTERNS = (
    (re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?"), "<ISO>"),
    (re.compile(r"\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2}"), "<TS>"),
    (re.compile(r"\d{4}_\d{2}_\d{2}"), "<DATE>"),
)


def normalize(text):
    """Strip the temp data root, unify slashes, mask timestamps."""
    if STATE.data_root:
        root = os.path.abspath(STATE.data_root)
        for variant in {root, root.replace("\\", "/"), STATE.data_root}:
            text = text.replace(variant, "<DATA>")
    text = text.replace("\\", "/")
    for pattern, token in _TIMESTAMP_PATTERNS:
        text = pattern.sub(token, text)
    return text


def jsonable(obj):
    """Deep-convert to JSON types; arrays become shape/dtype/head/sha1 summaries."""
    if obj is None or isinstance(obj, (bool, int)):
        return obj
    if isinstance(obj, str):
        return normalize(obj)
    if isinstance(obj, float):
        return obj
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, complex | np.complexfloating):
        return [float(obj.real), float(obj.imag)]
    if isinstance(obj, np.ndarray):
        flat = obj.ravel()
        summary = {
            "shape": list(obj.shape),
            "dtype": str(obj.dtype),
            "head": [jsonable(x) for x in flat[:3].tolist()],
        }
        if obj.dtype.kind in "biufc":
            summary["sha1"] = digest_value(obj)["sha1"]
        return {"__ndarray__": summary}
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [jsonable(x) for x in obj]
    if isinstance(obj, set | frozenset):
        return sorted((jsonable(x) for x in obj), key=repr)
    return f"<{type(obj).__name__}>"


MANTISSA_BITS = 30  # ~9 significant decimal digits (2**-30 = 9.3e-10 relative)


def digest_value(value):
    """{shape, dtype, sha1[:16], head} of one payload value.

    Floats are hashed after rounding to MANTISSA_BITS bits of binary mantissa
    (np.frexp is exact, so this is deterministic and independent of decimal
    formatting); ints and bools by value as int64; strings after normalize().
    """
    h = hashlib.sha1()
    if isinstance(value, str):
        text = normalize(value)
        h.update(text.encode())
        return {"shape": [], "dtype": "str", "sha1": h.hexdigest()[:16], "head": [text[:40]]}
    try:
        arr = np.asarray(value)
    except Exception:  # ragged nesting
        arr = np.asarray(value, dtype=object)
    kind = arr.dtype.kind
    if kind == "c":
        arr_f = np.stack([arr.real, arr.imag], axis=-1).astype(np.float64)
    else:
        arr_f = arr
    if kind in "fc":
        x = np.ascontiguousarray(arr_f, dtype=np.float64)
        finite = np.isfinite(x)
        mant, expo = np.frexp(np.where(finite, x, 0.0))
        h.update(np.round(mant * 2.0**MANTISSA_BITS).astype(np.int64).tobytes())
        h.update(expo.astype(np.int32).tobytes())
        h.update(np.packbits(finite).tobytes())
        h.update(repr(x[~finite].tolist()).encode())
    elif kind in "biu":
        h.update(np.ascontiguousarray(arr, dtype=np.int64).tobytes())
    elif kind in "US":
        for s in arr.ravel().tolist():
            h.update(normalize(str(s)).encode() + b"\0")
    else:
        h.update(json.dumps(jsonable(value), sort_keys=True, allow_nan=True).encode())
    h.update(repr(arr.shape).encode())
    head = arr.ravel()[:3].tolist() if arr.dtype.kind != "O" else []
    return {
        "shape": list(arr.shape),
        "dtype": str(arr.dtype) if kind not in "US" else "str",
        "sha1": h.hexdigest()[:16],
        "head": [jsonable(x) for x in head],
    }


def digest_payload(payload, prefix=""):
    """Flatten nested dicts with '/' and digest every leaf."""
    if not isinstance(payload, dict):
        return {prefix or "<value>": digest_value(payload)}
    out = {}
    for key, value in payload.items():
        name = f"{prefix}/{key}" if prefix else str(key)
        if isinstance(value, dict):
            out.update(digest_payload(value, name))
        else:
            out[name] = digest_value(value)
    return dict(sorted(out.items()))


def _kwargs_summary(kwargs):
    return {k: jsonable(v) for k, v in kwargs.items() if k != "data"}


def _same_call(a, b):
    return {k: v for k, v in a.items() if k != "count"} == {
        k: v for k, v in b.items() if k != "count"
    }


def _finish_call(log, entry):
    """Run-length encode identical consecutive calls as "count" once complete."""
    if len(log) >= 2 and log[-1] is entry and _same_call(log[-2], entry):
        log.pop()
        log[-1]["count"] = log[-1].get("count", 1) + 1


# --------------------------------------------------------------------------
# Attributes set by a method call
# --------------------------------------------------------------------------
_CLEAN_SCALARS = (type(None), bool, int, float, str, np.bool_, np.integer, np.floating)


def _clean(value, depth=0):
    """JSON form of a 'plain data' attribute value, or _MISSING if it is not one."""
    if isinstance(value, _CLEAN_SCALARS):
        return jsonable(value)
    if isinstance(value, complex | np.complexfloating):
        return jsonable(value)
    if isinstance(value, np.ndarray):
        return jsonable(value) if value.dtype.kind in "biufcU" else _MISSING
    if depth > 3:
        return _MISSING
    if isinstance(value, list | tuple):
        if len(value) > 64 and _numeric(value):
            return jsonable(np.asarray(value))
        items = [_clean(x, depth + 1) for x in value]
        return _MISSING if any(x is _MISSING for x in items) else items
    if isinstance(value, dict):
        if type(value) is not dict and not isinstance(value, RecordingDict):
            return _MISSING
        items = {str(k): _clean(v, depth + 1) for k, v in value.items()}
        return _MISSING if any(v is _MISSING for v in items.values()) else items
    return _MISSING


def _public_state(obj):
    """{name: clean JSON value} for the instance's public plain-data attributes."""
    out = {}
    for name, value in list(vars(obj).items()):
        if name.startswith("_") or name in SETS_SKIP:
            continue
        clean = _clean(value)
        if clean is not _MISSING:
            out[name] = clean
    return out


def _canon(value):
    return json.dumps(value, sort_keys=True, allow_nan=True)


def _changed(before, after):
    return {k: v for k, v in after.items() if k not in before or _canon(before[k]) != _canon(v)}


# --------------------------------------------------------------------------
# Experiment instrumentation
# --------------------------------------------------------------------------
def _call_record(self, name, args, kwargs):
    entry = {"name": name, "kwargs": _kwargs_summary(kwargs)}
    if name == "save_data":
        data = kwargs["data"] if "data" in kwargs else (args[0] if args else None)
        if data is None:
            data = self.__dict__.get("data")
        if data is not None:
            entry["data_digest"] = digest_payload(data)
    return entry


def _plain(cfg):
    """The authoritative dict behind a (possibly recording) cfg."""
    return cfg._origin if isinstance(cfg, RecordingDict) else cfg


def _cfg_snapshot(cfg):
    return {str(k): _canon(jsonable(v)) for k, v in dict.items(_plain(cfg))}


def _cfg_delta(self):
    """Keys of self.cfg added/changed/removed since __init__, with new values."""
    cfg = _plain(self.__dict__.get("cfg"))
    start = self.__dict__.get("_capture_cfg0") or {}
    delta = {}
    for key, value in dict.items(cfg):
        value = jsonable(value)
        if start.get(str(key)) != _canon(value):
            delta[str(key)] = value
    present = {str(k) for k in cfg}
    for key in start:
        if key not in present:
            delta[key] = "<removed>"
    return dict(sorted(delta.items()))


def _wrap_method(name, fn):
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        depth = self.__dict__.setdefault("_capture_depth", {})
        if depth.get(name):  # super() chain: log the outermost call only
            return fn(self, *args, **kwargs)
        rec = self.__dict__.get("_capture_record")
        skipped = self.__dict__.get("_capture_skipped", False)
        entry = None
        if rec is not None:
            entry = _call_record(self, name, args, kwargs)
            if name == "save_config":
                cfg = self.__dict__.get("cfg")
                if isinstance(cfg, dict):
                    entry["cfg_digest"] = _fingerprint(jsonable(dict(_plain(cfg)))).hex()[:16]
                    entry["cfg_delta"] = _cfg_delta(self)
            rec["methods"].append(entry)
            before = _public_state(self)
        depth[name] = 1
        pushed = name == "acquire" and (rec is not None or skipped)
        if pushed:
            STATE.stack.append(rec if rec is not None else _SKIPPED)
        try:
            result = fn(self, *args, **kwargs)
        except Exception as exc:
            if name not in SWALLOW or STATE.run is None:
                raise
            result = None
            if entry is not None:
                entry["raised"] = type(exc).__name__
        finally:
            depth[name] = 0
            if pushed:
                STATE.stack.pop()
            if name == "display" and STATE.run is not None:
                # plt.show is a no-op here, so a display that relies on the user
                # closing its window would otherwise leak every figure it opens.
                plt = sys.modules.get("matplotlib.pyplot")
                if plt is not None:
                    plt.close("all")
            if entry is not None:
                sets = _changed(before, _public_state(self))
                if sets:
                    entry["sets"] = sets
                _finish_call(rec["methods"], entry)
        return result

    wrapper._capture_wrapped = True
    return wrapper


def _instrument(cls, base):
    """Wrap WRAPPED methods defined anywhere between cls and base (once)."""
    for klass in cls.__mro__:
        if klass.__dict__.get("_capture_instrumented"):
            if klass is base:
                break
            continue
        for name in WRAPPED:
            fn = klass.__dict__.get(name)
            if callable(fn) and not getattr(fn, "_capture_wrapped", False):
                _ACTIVE.set(klass, name, _wrap_method(name, fn))
        _ACTIVE.set(klass, "_capture_instrumented", True)
        if klass is base:
            break


RECORD_CFG = os.environ.get("REGRESSION_RECORD_CFG", "1") != "0"


def _patch_experiment_base(base):
    original = base.__dict__["__init__"]

    @functools.wraps(original)
    def __init__(self, *args, **kwargs):
        if STATE.run is not None and STATE.total >= MAX_TOTAL:
            raise StopCapture(f"budget of {MAX_TOTAL} instantiations reached")
        original(self, *args, **kwargs)
        _instrument(type(self), base)
        if STATE.run is None:
            return
        STATE.total += 1
        cls = type(self).__name__
        cfg = self.__dict__.get("cfg")
        if RECORD_CFG and isinstance(cfg, dict):
            access = STATE.cfg_access.setdefault(cls, {"read": set(), "written": set()})
            self.cfg = RecordingDict(cfg, access)
        path = jsonable(getattr(self, "path", None))
        kind = f"{cls}/{path}"
        if STATE.kinds.get(kind, 0) >= PER_KIND:
            STATE.skipped[kind] = STATE.skipped.get(kind, 0) + 1
            STATE.idle += 1
            self.__dict__["_capture_skipped"] = True
            if STATE.skipped[kind] > MAX_SKIPS:
                raise StopCapture(f"{kind} skipped more than {MAX_SKIPS} times")
            if STATE.idle > MAX_IDLE:
                raise StopCapture(f"{MAX_IDLE} consecutive skips: the run only repeats itself")
            return
        STATE.idle = 0
        STATE.kinds[kind] = STATE.kinds.get(kind, 0) + 1
        rec = {
            "run": STATE.run,
            "index": len(STATE.records),
            "cls": cls,
            "path": path,
            "outerFolder": jsonable(getattr(self, "outerFolder", None)),
            "fname": jsonable(getattr(self, "fname", None)),
            "cfg": jsonable(getattr(self, "cfg", None)),
            "methods": [],
        }
        if isinstance(self.__dict__.get("cfg"), dict):
            self.__dict__["_capture_cfg0"] = _cfg_snapshot(self.cfg)
        self.__dict__["_capture_record"] = rec
        STATE.records.append(rec)
        CAPTURE.append(rec)

    __init__._capture_wrapped = True
    _ACTIVE.set(base, "__init__", __init__)


def _subclasses(cls):
    for sub in cls.__subclasses__():
        yield sub
        yield from _subclasses(sub)


# --------------------------------------------------------------------------
# Installation
# --------------------------------------------------------------------------
_MISSING = object()


class Mocks:
    """Undo log for install_mocks(); undo() restores every patched attribute."""

    def __init__(self):
        self._undo = []

    def set(self, owner, attr, value):
        previous = (
            owner.__dict__.get(attr, _MISSING) if isinstance(owner, type) else getattr(owner, attr)
        )
        self._undo.append((owner, attr, previous))
        setattr(owner, attr, value)

    def undo(self):
        while self._undo:
            owner, attr, value = self._undo.pop()
            if value is _MISSING:
                delattr(owner, attr)
            else:
                setattr(owner, attr, value)


_ACTIVE = Mocks()


def _resolve(target):
    """'pkg.mod:attr' or (module, attr) -> (module, attr)."""
    if isinstance(target, str):
        mod, attr = target.split(":")
        return importlib.import_module(mod), attr
    return target


_THREADPOOLS = []


def _single_threaded():
    """Pin BLAS/OpenMP pools to one thread for the whole session.

    Multi-threaded reductions (BLAS; formerly also sklearn KMeans in MixedShots)
    are not bit-reproducible, and curve_fit amplifies the last-ulp jitter to ~1e-8
    relative -- enough to flip the save_data digests between two runs.
    """
    try:
        from threadpoolctl import threadpool_limits
    except ImportError:  # pragma: no cover - sklearn always brings it
        return
    _THREADPOOLS.append(threadpool_limits(limits=1))


def install_mocks(experiment_base_cls, make_proxy_targets, pyvisa_targets):
    """Patch hardware entry points, instrument experiments, silence blocking calls.

    make_proxy_targets: ``"module:attr"`` or ``(module, attr)`` naming the proxy
        factory. The defining module and every already-imported module that
        bound the same object (``from ... import *``) are patched.
    pyvisa_targets: modules (or names) whose ``ResourceManager`` is replaced.
    """
    if getattr(experiment_base_cls.__dict__["__init__"], "_capture_wrapped", False):
        return _ACTIVE  # already installed in this process
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.figure
    import matplotlib.pyplot as plt

    mocks = _ACTIVE
    for target in make_proxy_targets:
        module, attr = _resolve(target)
        original = getattr(module, attr)
        for mod in list(sys.modules.values()):
            if getattr(mod, attr, None) is original:
                mocks.set(mod, attr, fake_make_proxy)
    for target in pyvisa_targets:
        module = importlib.import_module(target) if isinstance(target, str) else target
        mocks.set(module, "ResourceManager", FakeResourceManager)

    # Virtual clock, only inside the project's own package (third-party code
    # keeps the real datetime so its isinstance checks still hold).
    package = experiment_base_cls.__module__.split(".")[0] + "."
    for name, mod in list(sys.modules.items()):
        if not name.startswith(package) or mod is None:
            continue
        for attr, value in list(vars(mod).items()):
            if value is _dt:
                mocks.set(mod, attr, FAKE_DATETIME_MODULE)
            elif value is _dt.datetime:
                mocks.set(mod, attr, FakeDateTime)
    logging.getLogger("qick").setLevel(logging.ERROR)
    _single_threaded()

    mocks.set(time, "sleep", lambda *a, **k: None)
    for name in ("show", "pause"):
        mocks.set(plt, name, lambda *a, **k: None)
    mocks.set(matplotlib.figure.Figure, "savefig", lambda *a, **k: None)

    _patch_experiment_base(experiment_base_cls)
    for cls in (experiment_base_cls, *_subclasses(experiment_base_cls)):
        _instrument(cls, experiment_base_cls)
    return mocks


# --------------------------------------------------------------------------
# Golden assembly over board variants
# --------------------------------------------------------------------------
def capture_variants(capture_all, labels=None, variants=VARIANTS):
    """{"__meta__": {qick, variants}, <variant>: capture_all(labels)} for each variant."""
    out = {"__meta__": {"qick": get_version(), "variants": list(variants)}}
    try:
        for variant in variants:
            set_board(variant)
            print(f"[regression] --- board variant {variant} ---", file=sys.stderr)
            out[variant] = capture_all(labels)
    finally:
        set_board("A")
    return out
