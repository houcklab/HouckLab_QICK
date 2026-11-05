"""Hardware-free tests: the UndrivenSingleShot showcase trace (`<data>_trace.png`).

The readout-dropout gate (qicklab.analysis.telegraph_trace) must find a 2 Hz square-wave gain
dropout and keep only full-gain shots, leave a clean record alone, and the sweep display must
pick the bias with the best separation x population balance and write the figure.
See docs/experiments/undriven_single_shot.md#outputs.

    python -m pytest tests/test_undriven_trace.py
"""

import os
import types

import numpy as np
import pytest

import qicklab.experiments.undriven_single_shot as us_mod
import qicklab.hardware.yoko as yoko_mod
from qicklab.analysis.telegraph_trace import (
    pick_trace_window,
    readout_dropout_gate,
    trace_point_quality,
)

DT_US = 25.0
SIGMA = 0.1


def _telegraph(n, sep_sigma=3.0, rate_hz=300.0, p_upper=0.5, dropout=False, seed=1):
    """Two-state telegraph in IQ; with `dropout` a 2 Hz square wave scales the signal by 0.53
    for 40% of each cycle while the noise stays put (the 2026-11-04 fault)."""
    rng = np.random.default_rng(seed)
    t = np.arange(n) * DT_US
    # asymmetric switching gives the requested stationary upper-state population
    p_up = rate_hz * DT_US * 1e-6 * 2 * p_upper
    p_dn = rate_hz * DT_US * 1e-6 * 2 * (1 - p_upper)
    u = rng.random(n)
    s = np.empty(n, np.int8)
    cur = 0
    for j in range(n):
        if cur == 0 and u[j] < p_up:
            cur = 1
        elif cur == 1 and u[j] < p_dn:
            cur = 0
        s[j] = cur
    gain = np.ones(n)
    if dropout:
        gain = np.where((t * 1e-6 * 2.0) % 1.0 < 0.4, 0.53, 1.0)
    i = gain * (1.0 + (s - 0.5) * sep_sigma * SIGMA) + rng.normal(0, SIGMA, n)
    q = gain * 0.5 + rng.normal(0, SIGMA, n)
    return i, q, t, gain


def test_gate_finds_the_dropout_and_keeps_full_gain_shots():
    i, q, t, gain = _telegraph(400_000, dropout=True)
    g = readout_dropout_gate(i, q, t)
    assert g["modulated"]
    assert abs(g["f0_hz"] - 2.0) < 0.02
    assert 0.4 < g["kept_fraction"] < 0.6
    assert np.mean(gain[g["keep"]] < 1) < 0.01  # almost no low-gain shot kept


def test_gate_leaves_a_clean_record_alone():
    i, q, t, _ = _telegraph(400_000)
    g = readout_dropout_gate(i, q, t)
    assert not g["modulated"] and g["keep"].all() and g["kept_fraction"] == 1.0


def test_gated_quality_recovers_the_separation():
    i, q, t, _ = _telegraph(400_000, dropout=True)
    qual = trace_point_quality(i, q, t)
    assert qual["separation_sigma"] == pytest.approx(3.0, abs=0.3)
    assert qual["weights"] == pytest.approx([0.5, 0.5], abs=0.1)
    merged = trace_point_quality(*_telegraph(400_000, sep_sigma=0.5)[:3])
    # a 2-Gaussian fit of one unresolved blob still finds ~1.5 sigma, so the margin is ~1.5
    assert qual["score"] > merged["score"] + 1.0


def test_window_lies_inside_kept_shots():
    i, q, t, _ = _telegraph(400_000, dropout=True)
    qual = trace_point_quality(i, q, t)
    win = pick_trace_window(t, qual["z"], qual["keep"], qual["separation_sigma"])
    s0, n = win["start"], win["n_shots"]
    assert s0 is not None and n == round(20_000 / DT_US)
    assert qual["keep"][s0 : s0 + n].all()
    seg = win["smoothed"][s0 : s0 + n]
    assert seg.min() < 0 < seg.max()  # both states visible


# ---------------------------------------------------------------- through display()
_BIASES = {
    0.0: dict(sep_sigma=0.5),
    0.001: dict(sep_sigma=3.0),
    0.002: dict(sep_sigma=3.0, p_upper=0.1),
}


class _Prog:
    def __init__(self, soccfg, cfg):
        self.cfg = cfg

    def acquire(self, soc, load_pulses=True):
        kw = _BIASES[round(self.cfg.get("current_voltage", 0.0), 6)]
        i, q, _, _ = _telegraph(60_000, seed=3, **kw)
        return [[i]], [[q]]

    def scheduled_rep_period_us(self):
        return DT_US


class _FakeYoko:
    def __init__(self):
        self.level = 0.0

    def query(self, cmd):
        return f"{self.level}"

    def write(self, cmd):
        self.level = float(cmd.split()[1])


@pytest.fixture
def _fakes(monkeypatch):
    monkeypatch.setattr(us_mod, "UndrivenSingleShotProgram", _Prog)
    monkeypatch.setattr(yoko_mod.time, "sleep", lambda s: None)


def test_sweep_display_saves_the_best_bias_trace(tmp_path, _fakes, capsys):
    cfg = {
        "ts_bin_sizes": (1, 2),
        "charge_sweep": True,
        "voltage_start": 0.0,
        "voltage_end": 0.0025,
        "voltage_step": 0.001,
        "readout_length": 3.0,
        "pulse_freq": 6842.9,
        "pulse_gain": 1000,
    }
    exp = us_mod.UndrivenSingleShot(
        path="Undriven",
        outerFolder=str(tmp_path) + "/",
        cfg=cfg,
        soc=types.SimpleNamespace(stop_tproc=lambda: None),
        yoko=_FakeYoko(),
    )
    exp.acquire()
    attrs = set(vars(exp))
    exp.display(plotDisp=False)
    assert set(vars(exp)) == attrs  # the trace sets no attribute (golden records them)
    trace = exp.iname[: -len(".png")] + "_trace.png"
    assert os.path.getsize(trace) > 10_000
    assert "bias 1" in capsys.readouterr().out  # balanced and split beats merged and 90/10


def test_trace_failure_never_raises(tmp_path, capsys):
    exp = us_mod.UndrivenSingleShot(
        path="Undriven",
        outerFolder=str(tmp_path) + "/",
        cfg={},
        soc=types.SimpleNamespace(stop_tproc=lambda: None),
    )
    exp._save_trace_figures({"read_indices": np.array([0])})
    assert "trace figure skipped" in capsys.readouterr().out
