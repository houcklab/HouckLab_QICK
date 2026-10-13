"""
Hardware-free tests for the acquisition and parity helpers split out of the legacy utils.py.

Ported from the legacy inline self-test (Experiments/utils.py ``if __name__ == "__main__":``
block, L1108-1345) with the same assertions: project_iq_onto_separator,
pick_parity_drive_freq, chunked_acquire (stitching, metadata propagation, and the
ZeroSpanParity.save_data round-trip), and modulated_strobe_acquire.
"""
import os
import tempfile

import h5py
import numpy as np
import pytest

from qicklab.analysis.iq import project_iq_onto_separator
from qicklab.analysis.spectroscopy import pick_parity_drive_freq
from qicklab.core.acquisition import chunked_acquire, modulated_strobe_acquire
from qicklab.experiments.zero_span_parity import ZeroSpanParity


class _FakeExp:
    def __init__(self, n_per_chunk, sample_period_us=20.0):
        self.n = int(n_per_chunk)
        self.sp = float(sample_period_us)
        self.cfg = {"sample_period_us": self.sp}
        self.calls = 0

    def acquire(self, progress=False):
        self.calls += 1
        # Each chunk produces IQ ramps offset by the call index for traceability.
        I = np.arange(self.n, dtype=float) + 1000.0 * self.calls
        Q = np.arange(self.n, dtype=float) + 2000.0 * self.calls
        t = np.arange(self.n, dtype=float) * self.sp
        return {"I": I, "Q": Q, "t_us": t,
                "wall_clock_start": f"2026-01-01T00:00:{self.calls:02d}"}


class _MetaFakeExp:
    def __init__(self, n_per_chunk, sp_us=20.0):
        self.n = int(n_per_chunk)
        self.sp = float(sp_us)
        self.calls = 0

    def acquire(self, progress=False):
        self.calls += 1
        return {
            "I": np.arange(self.n, dtype=float),
            "Q": np.arange(self.n, dtype=float),
            "t_us": np.arange(self.n, dtype=float) * self.sp,
            "wall_clock_start": f"2026-05-16T12:00:{self.calls:02d}",
            "sample_period_us": self.sp,
            "read_length_us": 5.0,
            "adc_trig_offset_us": 0.488,
            "ro_norm_cycles": 1920.0,
            "mode": "strobe",
        }


class _ModFakeExp:
    def __init__(self, n_per_block, sample_period_us):
        self.cfg = {"qubit_gain": 0, "reps_per_chunk": n_per_block,
                    "reps": n_per_block, "sample_period_us": sample_period_us}
        self._n = n_per_block
        self._sp = sample_period_us

    def set_qubit_gain(self, gain):
        self.cfg["qubit_gain"] = gain
        self.cfg["reps_per_chunk"] = self._n
        self.cfg["reps"] = self._n

    def acquire(self, progress=False):
        g = self.cfg["qubit_gain"]
        I = np.full(self._n, 5.0 if g > 0 else 0.0)
        Q = np.zeros(self._n)
        t = np.arange(self._n) * self._sp
        return {"I": I, "Q": Q, "t_us": t, "mode": "strobe",
                "sample_period_us": self._sp, "read_length_us": 5.0,
                "wall_clock_start": "2026-01-01T00:00:00"}


def test_project_iq_onto_separator():
    rng = np.random.default_rng(0)
    g_center = np.array([0.0, 0.0])
    e_center = np.array([10.0, 0.0])
    sep = {"g_center": g_center, "e_center": e_center}

    # Two clouds of 1000 samples each at the centers, plus tight Gaussian noise.
    I_g = rng.normal(g_center[0], 0.5, 1000); Q_g = rng.normal(g_center[1], 0.5, 1000)
    I_e = rng.normal(e_center[0], 0.5, 1000); Q_e = rng.normal(e_center[1], 0.5, 1000)
    I = np.concatenate([I_g, I_e]); Q = np.concatenate([Q_g, Q_e])
    labels_true = np.concatenate([np.zeros(1000, int), np.ones(1000, int)])

    scores, bits = project_iq_onto_separator(I, Q, sep)
    accuracy = np.mean(bits == labels_true)
    assert accuracy > 0.99, f"project_iq_onto_separator accuracy too low: {accuracy}"
    assert scores.shape == (2000,)
    assert bits.shape == (2000,)
    assert np.issubdtype(bits.dtype, np.integer)
    # Sign convention: ground cluster (first 1000 samples) projects negative,
    # excited cluster (last 1000) projects positive.
    assert scores[0] < 0, f"expected ground sample to project negative, got {scores[0]}"
    assert scores[1500] > 0, f"expected excited sample to project positive, got {scores[1500]}"

    # Empty input edge case
    scores0, bits0 = project_iq_onto_separator([], [], sep)
    assert scores0.shape == (0,)
    assert bits0.shape == (0,)

    # Bad separator shape raises
    with pytest.raises(ValueError):
        project_iq_onto_separator([1.0], [1.0], {"g_center": [0, 0, 0], "e_center": [1, 1]})

    # Mismatched I/Q lengths raise with a clear message
    with pytest.raises(ValueError) as ex:
        project_iq_onto_separator([1.0, 2.0], [1.0], sep)
    assert "same length" in str(ex.value), f"unexpected error message: {ex.value}"


def test_pick_parity_drive_freq():
    # Build a fake QubitSpecSliceFF-style spec_data with two peaks at 3050 and 3052 MHz
    x_pts = np.linspace(3045.0, 3055.0, 401)

    def _lorentz(x, x0, A, g):
        return A / (1.0 + ((x - x0) / g) ** 2)
    amp = _lorentz(x_pts, 3050.0, 1.0, 0.15) + _lorentz(x_pts, 3052.0, 1.0, 0.15)
    avgi = np.sqrt(amp)  # arbitrary, only avgamp0 = i^2 + q^2 is fit-relevant
    avgq = np.zeros_like(avgi)
    spec_data = {"data": {
        "x_pts": x_pts.tolist(),
        "avgi": [[avgi.tolist()]],
        "avgq": [[avgq.tolist()]],
        "lorentz_centers": [3050.0, 3052.0],
    }}

    picked_low = pick_parity_drive_freq(spec_data, which="lower")
    assert abs(picked_low["picked"] - 3050.0) < 0.1, picked_low
    assert abs(picked_low["lower"]  - 3050.0) < 0.1
    assert abs(picked_low["higher"] - 3052.0) < 0.1

    picked_high = pick_parity_drive_freq(spec_data, which="higher")
    assert abs(picked_high["picked"] - 3052.0) < 0.1, picked_high

    # Bad "which" raises
    with pytest.raises(ValueError):
        pick_parity_drive_freq(spec_data, which="middle")


def test_chunked_acquire():
    exp = _FakeExp(n_per_chunk=1000)
    stitched = chunked_acquire(exp, n_chunks=5)
    assert stitched["I"].shape == (5000,)
    assert stitched["Q"].shape == (5000,)
    assert stitched["t_us"].shape == (5000,)
    # gap_indices marks first sample of each chunk after the first
    assert list(stitched["gap_indices"]) == [1000, 2000, 3000, 4000]
    # Time axis is monotonic
    assert np.all(np.diff(stitched["t_us"]) > 0)
    # Per-chunk wall clock timestamps are recorded
    assert len(stitched["chunk_wall_clock_starts"]) == 5
    # n_chunks == 1 case: gap_indices empty
    one = chunked_acquire(_FakeExp(n_per_chunk=100), n_chunks=1)
    assert list(one["gap_indices"]) == []

    # Degenerate single-sample chunks: t_us must stay strictly increasing (no
    # duplicate timestamp at chunk boundaries). The fallback derives the sample
    # period from experiment.cfg when the intra-chunk diff is unavailable.
    deg = chunked_acquire(_FakeExp(n_per_chunk=1, sample_period_us=20.0), n_chunks=3)
    assert deg["t_us"].shape == (3,)
    assert np.all(np.diff(deg["t_us"]) > 0), deg["t_us"]
    assert list(deg["gap_indices"]) == [1, 2]

    # chunked_acquire wires the stitched record into experiment.data so a bare
    # save_data() persists the full trace, not just the final chunk that the
    # inner acquire() calls leave behind.
    wired = _FakeExp(n_per_chunk=50)
    wired.data = {"data": None}  # would otherwise hold only the last chunk
    ws = chunked_acquire(wired, n_chunks=4)
    assert isinstance(wired.data, dict) and "data" in wired.data
    assert wired.data["data"] is ws
    assert wired.data["data"]["I"].shape == (200,)


def test_chunked_acquire_propagates_metadata():
    # Regression guard for Codex round-2 finding: the real chunked path must
    # carry sample_period_us, mode, read_length_us, adc_trig_offset_us, and
    # ro_norm_cycles into the stitched output so save_data sees them.
    meta_exp = _MetaFakeExp(n_per_chunk=500)
    meta_stitched = chunked_acquire(meta_exp, n_chunks=3)
    for k, v in [("mode", "strobe"), ("sample_period_us", 20.0),
                 ("read_length_us", 5.0), ("adc_trig_offset_us", 0.488),
                 ("ro_norm_cycles", 1920.0), ("n_chunks", 3)]:
        assert meta_stitched.get(k) == v, (
            f"chunked_acquire did not propagate {k}: got {meta_stitched.get(k)}, expected {v}"
        )
    assert meta_stitched["wall_clock_start"] == "2026-05-16T12:00:01"


def test_save_data_persists_chunked_acquire_metadata():
    # Stronger regression guard: drive the actual chunked_acquire helper with
    # a fake that returns realistic per-chunk metadata, then hand the stitched
    # dict to ZeroSpanParity.save_data and reload.
    real_stitched = chunked_acquire(_MetaFakeExp(n_per_chunk=10), n_chunks=3)
    # Sanity: the helper returns the metadata we expect to save.
    assert real_stitched["mode"] == "strobe"
    assert real_stitched["sample_period_us"] == 20.0
    assert real_stitched["read_length_us"] == 5.0

    class _SavingDouble:
        """Mimics enough of ZeroSpanParity to exercise save_data() in-isolation."""
        save_data = ZeroSpanParity.save_data

        def __init__(self, fname, data):
            self.fname = fname
            self.data = {"data": data}

    with tempfile.TemporaryDirectory() as tmpdir:
        fname = os.path.join(tmpdir, "stitched_test.h5")
        _SavingDouble(fname, real_stitched).save_data()
        with h5py.File(fname, "r") as f:
            assert list(np.array(f["gap_indices"])) == [10, 20]
            wcs = [s.decode("utf-8") if isinstance(s, bytes) else str(s)
                   for s in np.array(f["chunk_wall_clock_starts"])]
            assert len(wcs) == 3 and all(w.startswith("2026-05-16T") for w in wcs), wcs
            assert int(f.attrs["n_chunks"]) == 3
            assert float(f.attrs["sample_period_us"]) == 20.0
            assert str(f.attrs["mode"]) == "strobe"
            assert float(f.attrs["read_length_us"]) == 5.0
            assert float(f.attrs["adc_trig_offset_us"]) == 0.488
            assert float(f.attrs["ro_norm_cycles"]) == 1920.0


def test_modulated_strobe_acquire():
    n_per, sp = 500, 20.0
    exp = _ModFakeExp(n_per, sp)
    schedule = [100, 0] * 4   # 4 periods, on=100/off=0
    acq = modulated_strobe_acquire(exp, schedule, n_per)
    assert acq["I"].shape == (n_per * len(schedule),), acq["I"].shape
    assert acq["modulation_reference"].shape == acq["I"].shape
    # reference must be 1 exactly where the on-blocks are (I==5.0)
    assert np.array_equal((acq["modulation_reference"] > 0.5), (acq["I"] > 2.5)), "ref/gain misaligned"
    assert acq["gap_indices"] == [n_per * k for k in range(1, len(schedule))], acq["gap_indices"]
    assert np.all(np.diff(acq["t_us"]) > 0), "t_us not monotonic"
    assert acq["block_labels"] == schedule, acq["block_labels"]
    # 500 reps/half-period at 20 us -> half=10 ms -> period 20 ms -> 50 Hz
    assert abs(acq["modulation_freq_hz"] - 50.0) < 1.0, acq["modulation_freq_hz"]
