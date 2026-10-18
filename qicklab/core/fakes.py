"""Hardware fakes: a synthetic QICK board, a Pyro-less QickSoc stand-in and a GS200 yoko.

The regression harness (tests/regression/capture.py) and `run(session, PLAN, dry_run=True)`
(qicklab.core.session) share them. `FakeSocCfg` is a real QickConfig over a synthetic board, so
every program compiles through the genuine QICK code path; `FakeSoc` answers readout requests
with seeded synthetic IQ data and folds every call into `STATE` (the harness's hardware digest).
"""

import copy
import functools
import hashlib
import re

import numpy as np
from qick import QickConfig, get_version

# --------------------------------------------------------------------------
# Synthetic boards. Variant A mirrors what the lab's RFSoC reports (tProc and
# gen fabric 430.08 MHz -- the 0.00232515 us/cycle constant in the runs --
# readout output 307.2 MHz, avg_maxlen 16384); gens are mixer-less
# axis_signal_gen_v6, readouts axis_readout_v2 whose tProc input channel equals
# their index. Variant B breaks the coincidences A hides: gen fabric clock
# 614.4 MHz (DAC 9830.4 MS/s) != tProc 430.08 MHz, and readout i is wired to
# tProc input i + 2. The rest is invented: determinism is what matters.
# --------------------------------------------------------------------------
_GEN_CLOCKS = {
    "A": {"fs": 6881.28, "fs_mult": 14, "f_fabric": 430.08},
    "B": {"fs": 9830.4, "fs_mult": 20, "f_fabric": 614.4},
}
_RO_TPROC_OFFSET = {"A": 0, "B": 2}


def _gen(i, variant):
    clk = _GEN_CLOCKS[variant]
    return {
        "type": "axis_signal_gen_v6",
        "fullpath": f"axis_signal_gen_v6_{i}",
        "switch_ch": i,
        "tproc_ch": i + 1,
        "dac": f"{i}_230",
        "fs": clk["fs"],
        "fs_mult": clk["fs_mult"],
        "fs_div": 1,
        "f_fabric": clk["f_fabric"],
        "interpolation": 1,
        "f_dds": clk["fs"],
        "fdds_div": 1,
        "has_mixer": False,
        "maxlen": 65536,
        "b_dds": 32,
        "b_phase": 32,
        "samps_per_clk": 16,
        "maxv": 32766,
        "maxv_scale": 1.0,
    }


def _readout(i, variant):
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
        "tproc_ch": i + _RO_TPROC_OFFSET[variant],
    }


def _board(variant):
    return {
        "board": f"synthetic-{variant}",
        "sw_version": get_version(),
        "refclk_freq": 491.52,
        "gens": [_gen(i, variant) for i in range(7)],
        "readouts": [_readout(i, variant) for i in range(2)],
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


BOARDS = {v: _board(v) for v in ("A", "B")}
VARIANTS = tuple(BOARDS)
SYNTHETIC_SOCCFG = BOARDS["A"]  # v1 name, kept for callers
_BOARD = {"name": "A"}


def set_board(variant):
    """Select the synthetic board every later ``FakeSocCfg()`` is built from."""
    if variant not in BOARDS:
        raise ValueError(f"unknown board variant {variant!r}; choose from {VARIANTS}")
    _BOARD["name"] = variant


def current_board():
    return _BOARD["name"]


class FakeSocCfg(QickConfig):
    """Real QickConfig over a synthetic board (the selected one by default), so
    every conversion and every program compile is the genuine QICK code path."""

    def __init__(self, variant=None):
        super().__init__(copy.deepcopy(BOARDS[variant or _BOARD["name"]]))


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
    """GS200 voltage source, output OFF on open: tracks level/output so ramp_to() terminates."""

    def __init__(self, address):
        self.address = address
        self.level = 0.0
        self.output = "0"

    def write(self, cmd):
        STATE.yoko.append(f"W {cmd}")
        match = re.fullmatch(r":SOUR:LEV\s+(\S+)", cmd.strip())
        if match:
            self.level = float(match.group(1))
        match = re.fullmatch(r":OUTP\s+(ON|OFF)", cmd.strip())
        if match:
            self.output = "1" if match.group(1) == "ON" else "0"

    def query(self, cmd):
        STATE.yoko.append(f"Q {cmd}")
        answers = {":OUTP?": self.output, ":SOUR:FUNC?": "VOLT", ":SOUR:RANG?": "1E+01"}
        return repr(self.level) if cmd.strip() == ":SOUR:LEV?" else answers.get(cmd.strip(), "0")

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


# --------------------------------------------------------------------------
# Run state
# --------------------------------------------------------------------------
_SKIPPED = {"skipped": True}  # stack sentinel: board traffic of skipped experiments


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
        self.total = 0
        self.kinds = {}
        self.skipped = {}
        self.idle = 0
        self.cfg_access = {}

    def hw_event(self, name, args, kwargs):
        if self.stack and self.stack[-1] is _SKIPPED:
            return
        key = id(self.stack[-1]) if self.stack else None
        hasher, counts = self.hashers.setdefault(key, (hashlib.sha256(), {}))
        hasher.update(name.encode())
        hasher.update(_fingerprint((args, kwargs)))
        counts[name] = counts.get(name, 0) + 1
        if name == "load_bin_program":
            counts.setdefault("_programs", []).append(_fingerprint(args[0]).hex()[:16])


STATE = _State()


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
