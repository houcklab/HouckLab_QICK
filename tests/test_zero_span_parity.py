"""
Hardware-free tests for qicklab.experiments.zero_span_parity.

Ported from the legacy inline self-test (mZeroSpanParity.py ``if __name__ == "__main__":``
block, L581-737) with the same assertions: _validate_cfg rules against a fake soccfg, the
decimated soft_avgs opt-in gate, and the strobe I/Q normalisation to single-shot units.
"""

import datetime
import time

import numpy as np
import pytest

from qicklab.experiments.zero_span_parity import ZeroSpanParity, _validate_cfg


def _ticking_now():
    """Return now() as an ISO string with a clock tick on either side.

    The fake acquire calls this, so a wall clock taken before the call is strictly earlier
    than the returned time and one taken after it is strictly later.
    """
    time.sleep(0.002)
    t = datetime.datetime.now().isoformat()
    time.sleep(0.002)
    return t


def _ts(iso):
    return datetime.datetime.fromisoformat(iso)


class _FakeSocCfg:
    """Synthetic soccfg-like object for unit testing _validate_cfg without QICK hardware."""

    def __init__(self):
        self._d = {
            "readouts": {0: {"avg_maxlen": 16384, "buf_maxlen": 8192, "f_output": 100.0}},
            "gens": {0: {"f_dds": 6144.0}, 1: {"f_dds": 6144.0}},
        }

    def us2cycles(self, us, gen_ch=None, ro_ch=None):
        # Pretend 384 MHz clock on every channel.
        return int(round(us * 384.0))

    def __getitem__(self, k):
        return self._d[k]

    def __contains__(self, k):
        return k in self._d


@pytest.fixture
def sc():
    return _FakeSocCfg()


@pytest.fixture
def base():
    return {
        "mode": "strobe",
        "start_src": "internal",
        "res_ch": 0,
        "qubit_ch": 1,
        "ro_chs": [0],
        "nqz": 2,
        "qubit_nqz": 2,
        "mixer_freq": 0.0,
        "read_pulse_freq": 7000.0,
        "parity_drive_freq": 3050.0,
        "qubit_gain": 5000,
        "pulse_gain": 1000,
        "res_phase": 0,
        "adc_trig_offset": 0.5,
        "read_length": 5.0,
        "sample_period_us": 20.0,
        "reps_per_chunk": 1000,
    }


@pytest.fixture
def dec_base(base):
    dec = dict(base)
    dec.update({"mode": "decimated", "capture_length_us": 50.0, "soft_avgs": 1})
    del dec["sample_period_us"]
    del dec["reps_per_chunk"]
    return dec


def _expect_rule(cfg, sc, fragment):
    with pytest.raises(RuntimeError) as exc:
        _validate_cfg(cfg, sc)
    assert fragment in str(exc.value), exc.value


def test_validate_cfg_valid_strobe(base, sc):
    _validate_cfg(base, sc)


def test_rule1_sample_period_too_small(base, sc):
    bad = dict(base)
    bad["sample_period_us"] = 1.0
    _expect_rule(bad, sc, "rule 1")


def test_rule2_sample_period_too_long(base, sc):
    # sample_period too long => cycles > 65535
    bad = dict(base)
    bad["sample_period_us"] = 500.0
    _expect_rule(bad, sc, "rule 2")


def test_rule4_reps_per_chunk_not_capped_at_avg_maxlen(base, sc, capsys):
    # F43: the averages buffer is a streamed ring buffer, so one 12 s chunk (600000 samples
    # at 20 us, > avg_maxlen 16384) is valid and, with 295 ms of headroom, prints no warning.
    ok = dict(base)
    ok["reps_per_chunk"] = 600000
    _validate_cfg(ok, sc)
    assert "rule 4 warning" not in capsys.readouterr().out


def test_rule4_reps_per_chunk_memory_cap(base, sc):
    from qicklab.experiments.zero_span_parity import _MAX_REPS_PER_CHUNK

    assert _MAX_REPS_PER_CHUNK == 20_000_000
    at_cap = dict(base)
    at_cap["reps_per_chunk"] = _MAX_REPS_PER_CHUNK
    _validate_cfg(at_cap, sc)
    bad = dict(base)
    bad["reps_per_chunk"] = _MAX_REPS_PER_CHUNK + 1
    _expect_rule(bad, sc, "rule 4")


def test_rule4_streaming_headroom_warning(base, sc, capsys):
    # headroom per stride = (16384 - 1638) * 3 us = 44 ms < 100 ms: warn, do not raise
    fast = dict(base)
    fast.update({"read_length": 1.0, "sample_period_us": 3.0, "reps_per_chunk": 16384})
    _validate_cfg(fast, sc)
    out = capsys.readouterr().out
    assert "rule 4 warning" in out and "44.2 ms" in out, out
    # a chunk that fits the buffer never wraps the ring: no warning at the same cadence
    fast["reps_per_chunk"] = 16383
    _validate_cfg(fast, sc)
    assert "rule 4 warning" not in capsys.readouterr().out


def test_rule5_read_length_too_long_decimated(dec_base, sc):
    # Buffer cap is sized by the declared readout window, not by the const-pulse length.
    _validate_cfg(dec_base, sc)  # read_length=5 us * 100 MHz = 500 samples < 8192
    bad = dict(dec_base)
    bad["read_length"] = 90.0  # 9000 samples > 8192
    bad["capture_length_us"] = 100.0  # keep capture >= read+offset
    _expect_rule(bad, sc, "rule 5]")


def test_rule9_pulse_shorter_than_readout_window(dec_base, sc):
    bad = dict(dec_base)
    bad["capture_length_us"] = 3.0  # < adc_trig_offset + read_length = 5.5
    _expect_rule(bad, sc, "rule 9")


def test_rule8_parity_drive_freq_above_fdds(base, sc):
    bad = dict(base)
    bad["parity_drive_freq"] = 9000.0
    _expect_rule(bad, sc, "rule 8")


def test_rule8_parity_drive_freq_above_half_fdds(base, sc):
    # f_dds=6144 for the fake gens, so 5000 MHz passes the old [0, f_dds] bound but is
    # outside QICK's true [-3072, 3072] DDS band. Regression guard for the
    # half-bandwidth fix.
    bad = dict(base)
    bad["parity_drive_freq"] = 5000.0
    _expect_rule(bad, sc, "rule 8")


def test_missing_required_key(base, sc):
    bad = dict(base)
    del bad["qubit_gain"]
    _expect_rule(bad, sc, "missing required keys")


def test_soft_avgs_gate_requires_opt_in(base, sc):
    # soft_avgs > 1 averages across independent parity captures and destroys the
    # time-resolved trajectory. _acquire_decimated must reject it unless the user
    # explicitly opts in.
    class _StubExp:
        """Minimal ZeroSpanParity stand-in to exercise _acquire_decimated's
        soft_avgs gate without instantiating QICK programs."""

        _acquire_decimated = ZeroSpanParity._acquire_decimated

        def __init__(self, cfg, soccfg):
            self.cfg = cfg
            self.soccfg = soccfg
            self.soc = None
            self.prog = None

    cfg_soft = dict(base)
    cfg_soft.update(
        {
            "mode": "decimated",
            "capture_length_us": 50.0,
            "soft_avgs": 4,
            "read_length": 5.0,
            "adc_trig_offset": 0.5,
        }
    )
    del cfg_soft["sample_period_us"]
    del cfg_soft["reps_per_chunk"]
    with pytest.raises(RuntimeError) as exc:
        _StubExp(cfg_soft, sc)._acquire_decimated(progress=False)
    assert "soft_avgs" in str(exc.value), exc.value


def test_decimated_records_per_capture_end_times(dec_base, sc):
    # F43: _acquire_decimated takes a start time before and an end time after every
    # acquire_decimated() call, so chunk_wall_clock_ends has one entry per capture and each
    # capture's start < (time inside its acquire) < its end, strictly; wall_clock_end is the
    # last capture's end.
    n_len = 8

    class _FakeDecProg:
        def __init__(self):
            self.calls = []
            self.inside = []

        def acquire_decimated(self, soc, load_pulses=True, start_src="internal", progress=False):
            self.calls.append(load_pulses)
            self.inside.append(_ticking_now())
            i = np.arange(n_len, dtype=float) + 10.0 * len(self.calls)
            return [np.stack([i, -i])]  # (2, length): the reps=1 shape

    class _DecStub:
        _acquire_decimated = ZeroSpanParity._acquire_decimated

        def __init__(self, cfg, soccfg, prog):
            self.cfg = cfg
            self.soccfg = soccfg
            self.soc = None
            self.prog = prog

    cfg = dict(dec_base)
    cfg["n_captures"] = 3
    prog = _FakeDecProg()
    out = _DecStub(cfg, sc, prog)._acquire_decimated(progress=False)

    assert prog.calls == [True, False, False]  # pulses loaded on the first capture only
    starts = out["chunk_wall_clock_starts"]
    ends = out["chunk_wall_clock_ends"]
    assert len(starts) == len(ends) == 3
    for s, t, e in zip(starts, prog.inside, ends):
        assert _ts(s) < _ts(t) < _ts(e), (s, t, e)
    for e, t_next in zip(ends[:-1], prog.inside[1:]):
        assert _ts(e) < _ts(t_next), (e, t_next)
    assert out["wall_clock_end"] == ends[-1]
    assert out["wall_clock_start"] <= starts[0]
    assert out["I"].size == 3 * n_len
    assert list(out["gap_indices"]) == [n_len, 2 * n_len]


def test_strobe_iq_normalised_to_single_shot_units(base, sc):
    # Strobe raw di_buf values are integrated over the readout window
    # (~us2cycles(read_length, ro_ch) summands), but the apriori separator from
    # single_shot.collect_shots is in per-cycle units (di_buf / us2cycles(readout_length,
    # ro_ch=0)). _acquire_strobe divides I/Q by the same divisor.
    class _FakeProg:
        def __init__(self, di_val, dq_val, n):
            self.di_buf = {0: np.full(n, di_val, dtype=float)}
            self.dq_buf = {0: np.full(n, dq_val, dtype=float)}

            self.inside = None

        def acquire(self, *_a, **_k):
            self.inside = _ticking_now()
            return None

    class _StrobeStub:
        _acquire_strobe = ZeroSpanParity._acquire_strobe

        def __init__(self, cfg, soccfg, prog):
            self.cfg = cfg
            self.soccfg = soccfg
            self.soc = None
            self.prog = prog

    # With _FakeSocCfg, us2cycles(5, ro_ch=0) returns 5 * 384 = 1920 (the fake hardcodes
    # 384 MHz regardless of channel). The check is I_normalized = di_val / 1920.
    cfg_strobe = dict(base)
    n_reps = 1000
    cfg_strobe["reps_per_chunk"] = n_reps
    fake = _FakeProg(di_val=192000.0, dq_val=0.0, n=n_reps)
    stub = _StrobeStub(cfg_strobe, sc, fake)
    out = stub._acquire_strobe(progress=False)
    # Expected I per sample = 192000 / us2cycles(5, ro_ch=0) = 192000/1920 = 100.0
    assert abs(float(out["I"][0]) - 100.0) < 1e-6, (
        f"strobe normalization wrong: got {out['I'][0]}, expected 100.0"
    )
    assert out["ro_norm_cycles"] == 1920.0, out["ro_norm_cycles"]
    assert out["read_length_us"] == 5.0
    assert out["mode"] == "strobe"
    # F43: the start time is taken before and the end time after prog.acquire, so the
    # chunk's acquire() call is bracketed (strictly, because the fake acquire ticks the clock)
    assert _ts(out["wall_clock_start"]) < _ts(fake.inside) < _ts(out["wall_clock_end"]), (
        out["wall_clock_start"],
        fake.inside,
        out["wall_clock_end"],
    )
