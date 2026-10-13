"""Hardware-free capture core for the config regression harness.

Everything here is layout-agnostic: the driver hands in the ExperimentClass base,
the modules that bind ``makeProxy`` and the ``pyvisa`` modules to patch, so the
same core runs unchanged against the legacy and the refactored code.

What gets recorded per run (see ``begin_run`` / ``end_run``):
  * every ExperimentClass instantiation: class, path, outerFolder, full cfg
    (taken right after ``ExperimentClass.__init__``), and the wrapped methods
    called on it, in order, with their non-data kwargs;
  * a digest of every command the experiment sent to the (fake) QICK board
    while its ``acquire`` ran: compiled tProc binaries, pulse envelopes, gen /
    readout / buffer configuration and readout requests;
  * every yoko ``write``/``query``/``close``.

``acquire`` is NOT stubbed: it runs for real against ``FakeSoc``, which answers
readout requests with seeded synthetic data of exactly the shape QICK would
return. ``display`` is a no-op; ``save_data``/``save_config`` run for real into
the per-run temp dir (downstream analysis reads those files back).
"""

import datetime as _dt
import functools
import hashlib
import importlib
import logging
import os
import random
import re
import sys
import time
import types
import zlib

import numpy as np
from qick import QickConfig, get_version

BUDGET = 12  # experiment instantiations per run before StopCapture
WRAPPED = ("acquire", "display", "save_data", "save_config", "analyze")
NOOP = frozenset({"display"})
CAPTURE = []  # every experiment record of the session, each tagged with its run


class StopCapture(BaseException):
    """Raised on the (BUDGET+1)-th instantiation. BaseException so that the
    code under test cannot swallow it with ``except Exception``."""


# --------------------------------------------------------------------------
# Synthetic board. Clocks mirror what the lab's RFSoC reports (tProc and gen
# fabric 430.08 MHz -- the 0.00232515 us/cycle constant in the runs -- readout
# output 307.2 MHz, avg_maxlen 16384); gens are mixer-less axis_signal_gen_v6,
# readouts axis_readout_v2. The rest is invented: determinism is what matters.
# --------------------------------------------------------------------------
def _gen(i):
    return {
        "type": "axis_signal_gen_v6",
        "fullpath": f"axis_signal_gen_v6_{i}",
        "switch_ch": i,
        "tproc_ch": i + 1,
        "dac": f"{i}_230",
        "fs": 6881.28,
        "fs_mult": 14,
        "fs_div": 1,
        "f_fabric": 430.08,
        "interpolation": 1,
        "f_dds": 6881.28,
        "fdds_div": 1,
        "has_mixer": False,
        "maxlen": 65536,
        "b_dds": 32,
        "b_phase": 32,
        "samps_per_clk": 16,
        "maxv": 32766,
        "maxv_scale": 1.0,
    }


def _readout(i):
    return {
        "ro_type": "axis_readout_v2",
        "avgbuf_type": "axis_avg_buffer",
        "ro_fullpath": f"axis_readout_v2_{i}",
        "fullpath": f"axis_avg_buffer_{i}",
        "adc": f"{i}_226",
        "fs": 4915.2,
        "fs_mult": 10,
        "fs_div": 1,
        "decimation": 2,
        "f_dds": 2457.6,
        "fdds_div": 2,
        "f_output": 307.2,
        "b_dds": 32,
        "b_phase": 32,
        "iq_offset": 0.0,
        "has_outsel": True,
        "avg_maxlen": 16384,
        "buf_maxlen": 1024,
        "has_edge_counter": False,
        "trigger_type": "tproc",
        "trigger_port": 0,
        "trigger_bit": 14 + i,
        "tproc_ch": i,
    }


SYNTHETIC_SOCCFG = {
    "board": "synthetic",
    "sw_version": get_version(),
    "refclk_freq": 491.52,
    "gens": [_gen(i) for i in range(7)],
    "readouts": [_readout(i) for i in range(2)],
    "iqs": [],
    "tprocs": [
        {
            "type": "axis_tproc64x32_x8",
            "fullpath": "axis_tproc64x32_x8_0",
            "f_time": 430.08,
            "pmem_size": 65536,
            "dmem_size": 4096,
            "output_pins": [("output", 0, b, f"PMOD0_{b}") for b in range(8)],
            "start_pin": None,
        }
    ],
}


class FakeSocCfg(QickConfig):
    """Real QickConfig over SYNTHETIC_SOCCFG, so every conversion and every
    program compile is the genuine QICK code path."""

    def __init__(self):
        super().__init__(SYNTHETIC_SOCCFG)


class FakeSoc:
    """Stands in for the Pyro QickSoc proxy.

    Every call is folded into the active experiment's hardware digest. Readout
    requests are answered with seeded two-blob IQ data (normalised blob centres
    at +-5, sigma 2, 30 % in the second blob) scaled by the configured window.
    """

    def __init__(self):
        self._ro_len = {}
        self._pending = None

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return functools.partial(self._record, name)

    def _record(self, name, *args, **kwargs):
        STATE.hw_event(name, args, kwargs)

    def config_avg(self, ch, address=0, length=1, **kwargs):
        self._ro_len[ch] = int(length)
        self._record("config_avg", ch, address=address, length=length, **kwargs)

    def start_readout(self, total_count, counter_addr, ch_list, reads_per_shot, **kwargs):
        self._pending = (int(total_count), list(ch_list), list(reads_per_shot))
        self._record(
            "start_readout",
            total_count,
            counter_addr=counter_addr,
            ch_list=ch_list,
            reads_per_shot=reads_per_shot,
            **kwargs,
        )

    def poll_data(self, *args, **kwargs):
        if self._pending is None:
            return []
        total, chs, reads = self._pending
        self._pending = None
        data = [
            _iq_blobs(total * n, self._ro_len.get(ch, 1)) for ch, n in zip(chs, reads, strict=True)
        ]
        return [(total, (data, (total * 1e-5, total, 0, 0)))]

    def get_accumulated(self, ch, address=0, length=1):
        return _iq_blobs(int(length), self._ro_len.get(ch, 1))

    def get_decimated(self, ch, address=0, length=1):
        return STATE.rng.normal(0.0, 2.0, size=(int(length), 2))

    def get_tproc_counter(self, *args, **kwargs):
        return 2**31


def _iq_blobs(n, window):
    rng = STATE.rng
    sign = np.where(rng.random(n) < 0.3, -1.0, 1.0)
    iq = np.stack([5.0 * sign, 2.5 * sign], axis=1) + rng.normal(0.0, 2.0, size=(n, 2))
    return np.round(iq * window).astype(np.int64)


class FakeYoko:
    """GS200 voltage source: tracks the level so ramp_to() terminates."""

    def __init__(self, address):
        self.address = address
        self.level = 0.0

    def write(self, cmd):
        STATE.yoko.append(f"W {cmd}")
        match = re.fullmatch(r":SOUR:LEV\s+(\S+)", cmd.strip())
        if match:
            self.level = float(match.group(1))

    def query(self, cmd):
        STATE.yoko.append(f"Q {cmd}")
        return repr(self.level) if cmd.strip() == ":SOUR:LEV?" else "0"

    def close(self):
        STATE.yoko.append("CLOSE")


class FakeResourceManager:
    def __init__(self, *args, **kwargs):
        pass

    def open_resource(self, address, *args, **kwargs):
        STATE.yoko.append(f"OPEN {address}")
        return FakeYoko(address)

    def list_resources(self, *args, **kwargs):
        return ()


def fake_make_proxy(*args, **kwargs):
    return FakeSoc(), FakeSocCfg()


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
# Run state
# --------------------------------------------------------------------------
class _State:
    def __init__(self):
        self.run = None
        self.data_root = None
        self.records = []
        self.stack = []
        self.yoko = []
        self.hashers = {}
        self.clock = 0
        self.rng = np.random.default_rng(0)

    def hw_event(self, name, args, kwargs):
        key = id(self.stack[-1]) if self.stack else None
        hasher, counts = self.hashers.setdefault(key, (hashlib.sha256(), {}))
        hasher.update(name.encode())
        hasher.update(_fingerprint((args, kwargs)))
        counts[name] = counts.get(name, 0) + 1
        if name == "load_bin_program":
            counts.setdefault("_programs", []).append(_fingerprint(args[0]).hex()[:16])


STATE = _State()


def begin_run(label, data_root):
    """Reset per-run state; seeds every RNG from the label (order-independent)."""
    seed = zlib.crc32(label.encode())
    STATE.__init__()
    STATE.run, STATE.data_root, STATE.rng = label, data_root, np.random.default_rng(seed)
    np.random.seed(seed)
    random.seed(seed)


def end_run():
    """Finalise and return {experiments, yoko, hw_outside_experiments}."""
    for rec in STATE.records:
        rec["hw"] = _hw_summary(STATE.hashers.get(id(rec)))
    out = {
        "experiments": STATE.records,
        "yoko": [normalize(s) for s in STATE.yoko],
        "hw_outside_experiments": _hw_summary(STATE.hashers.get(None)),
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


def _fingerprint(obj):
    """Stable bytes for anything sent to the board (arrays hashed by content)."""
    h = hashlib.sha1()

    def feed(o):
        if isinstance(o, np.ndarray):
            h.update(f"nd{o.shape}{o.dtype}".encode())
            h.update(np.ascontiguousarray(o).tobytes())
        elif isinstance(o, dict):
            h.update(b"{")
            for k in sorted(o, key=str):
                feed(str(k))
                feed(o[k])
            h.update(b"}")
        elif isinstance(o, list | tuple) and len(o) > 16 and _numeric(o):
            feed(np.asarray(o))
        elif isinstance(o, list | tuple):
            h.update(b"[")
            for x in o:
                feed(x)
            h.update(b"]")
        else:
            h.update(repr(o).encode())

    feed(obj)
    return h.digest()


def _numeric(seq):
    return all(isinstance(x, int | float | np.number) for x in seq)


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
    """Deep-convert to JSON types; arrays become shape/dtype/head summaries."""
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
        return {
            "__ndarray__": {
                "shape": list(obj.shape),
                "dtype": str(obj.dtype),
                "head": [jsonable(x) for x in flat[:3].tolist()],
            }
        }
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [jsonable(x) for x in obj]
    if isinstance(obj, set | frozenset):
        return sorted((jsonable(x) for x in obj), key=repr)
    return f"<{type(obj).__name__}>"


def _kwargs_summary(kwargs):
    return {k: jsonable(v) for k, v in kwargs.items() if k != "data"}


def _log_call(log, entry):
    """Append, run-length encoding identical consecutive calls as "count"."""
    last = log[-1] if log else None
    if last and last["name"] == entry["name"] and last["kwargs"] == entry["kwargs"]:
        last["count"] = last.get("count", 1) + 1
    else:
        log.append(entry)


# --------------------------------------------------------------------------
# Experiment instrumentation
# --------------------------------------------------------------------------
def _wrap_method(name, fn):
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        depth = self.__dict__.setdefault("_capture_depth", {})
        if depth.get(name):  # super() chain: log the outermost call only
            return None if name in NOOP else fn(self, *args, **kwargs)
        rec = self.__dict__.get("_capture_record")
        if rec is not None:
            _log_call(rec["methods"], {"name": name, "kwargs": _kwargs_summary(kwargs)})
        if name in NOOP:
            return None
        depth[name] = 1
        if rec is not None and name == "acquire":
            STATE.stack.append(rec)
        try:
            return fn(self, *args, **kwargs)
        finally:
            depth[name] = 0
            if rec is not None and name == "acquire":
                STATE.stack.pop()

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


def _patch_experiment_base(base):
    original = base.__dict__["__init__"]

    @functools.wraps(original)
    def __init__(self, *args, **kwargs):
        if STATE.run is not None and len(STATE.records) >= BUDGET:
            raise StopCapture(f"budget of {BUDGET} experiments reached")
        original(self, *args, **kwargs)
        _instrument(type(self), base)
        if STATE.run is None:
            return
        rec = {
            "run": STATE.run,
            "index": len(STATE.records),
            "cls": type(self).__name__,
            "path": jsonable(getattr(self, "path", None)),
            "outerFolder": jsonable(getattr(self, "outerFolder", None)),
            "fname": jsonable(getattr(self, "fname", None)),
            "cfg": jsonable(getattr(self, "cfg", None)),
            "methods": [],
        }
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

    mocks.set(time, "sleep", lambda *a, **k: None)
    for name in ("show", "pause"):
        mocks.set(plt, name, lambda *a, **k: None)
    mocks.set(matplotlib.figure.Figure, "savefig", lambda *a, **k: None)

    _patch_experiment_base(experiment_base_cls)
    for cls in (experiment_base_cls, *_subclasses(experiment_base_cls)):
        _instrument(cls, experiment_base_cls)
    return mocks
