# Zero-Span Parity Validation Harness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the 9-stage contrast/SNR validation harness for the zero-span charge-parity measurement, on top of the existing `mZeroSpanParity.py` + `analyze_ZeroSpanParity.py`, so a telegraph signal can be proven parity-dependent, time-resolved, and not an artifact.

**Architecture:** Strobe-only. Five new pure analysis primitives + a backward-compatible dwell-debounce extension go in `analyze_ZeroSpanParity.py`. One acquisition helper (`modulated_strobe_acquire`) + a `ZeroSpanParity.set_qubit_gain` rebuild method enable software square-wave modulation. A new `validate_ZeroSpanParity.py` harness composes acquisition + analysis into per-stage `run_*` functions, a `CrossRunComparison` helper, self-describing sidecars, and a collate-only evidence report. `CSTQ03_BFC.py` gets thin `Validate_*` flags + param dicts that call the harness. Loopback checks extend `_loopback_check_ZeroSpanParity.py`.

**Tech Stack:** Python, numpy, scipy (`signal`, `optimize`), scikit-learn (`GaussianMixture`, `KMeans`), h5py, matplotlib, QICK. No pytest — tests live in `if __name__ == "__main__":` blocks with plain `assert` + `print("... OK")`, reproducible noise via `np.random.default_rng(0)`.

**Reference spec:** `docs/superpowers/specs/2026-06-01-bfc-parity-validation-harness-design.md` (addendum to the canonical `2026-05-16-bfc-charge-parity-zero-span-design.md`).

**Edit scope:** `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/` only.

**Build order rationale:** Stage 3 (modulation sanity gate) is the user's top priority, so its chain (debounce → `verify_modulation` → `modulated_strobe_acquire` → `run_modulation_check`) is front-loaded (Tasks 1–4). Pure analysis primitives are TDD'd offline; hardware-coupled harness functions are plumbing-tested with a fake experiment object (the `_FakeExp` pattern already used by `chunked_acquire`'s tests) and finally exercised in loopback (Task 15).

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `analyze_ZeroSpanParity.py` | Modify | + `verify_modulation`, `projected_histogram_snr`, `bin_size_sweep`, `threshold_stability`, `contrast_from_sweeps`, `_debounce_bits`/`_debounce_bits_segmented`, debounce params on `dwell_time_statistics`, plot helpers, `__main__` tests |
| `utils.py` | Modify | + `modulated_strobe_acquire` (+ `__main__` test) |
| `mZeroSpanParity.py` | Modify | + `ZeroSpanParity.set_qubit_gain` rebuild method (+ `__main__` test) |
| `validate_ZeroSpanParity.py` | Create | Harness: `run_static_contrast`, `run_contrast_vs_qubit_freq`, `run_modulation_check`, `run_control_suite`, `run_environment_sweep`, `CrossRunComparison`, `_stage_sidecar`, `build_evidence_report`, plot helpers, `__main__` plumbing tests |
| `CSTQ03_BFC.py` | Modify | Thin `Validate_*` flags + param dicts + linear calls into the harness |
| `_loopback_check_ZeroSpanParity.py` | Modify | + checks for `modulated_strobe_acquire` and `run_static_contrast` plumbing |

All new pure functions follow the existing module convention: arrays in → dict out, no file I/O (only `_stage_sidecar`/`build_evidence_report`/`analyze_parity_run` touch disk), `gap_indices` respected everywhere, empty/degenerate inputs return sensible structures without raising.

---

## Task 1: Dwell-time debounce extension (spec §3.6)

Adds opt-in flicker filtering to the existing `dwell_time_statistics` so marginal-SNR threshold flickers don't bias τ low. Backward-compatible (defaults off). Foundation for Tasks 9 & 10.

**Files:**
- Modify: `Experiments/analyze_ZeroSpanParity.py` (add helpers above `dwell_time_statistics`; add 2 params to its signature; extend `__main__`)

- [ ] **Step 1: Write the failing test** — append inside the `__main__` block (after the existing `dwell_time_statistics` test), then add a top-level print marker:

```python
    # --- Task 1: dwell debounce ---
    rng = np.random.default_rng(0)
    # Clean telegraph: 50 us sample period, runs of ~40 samples (2 ms) per state
    sp_us = 50.0
    runs = []
    state = 0
    for _ in range(400):
        L = max(2, int(rng.exponential(40)))
        runs.append(np.full(L, state))
        state ^= 1
    clean = np.concatenate(runs).astype(int)
    t = np.arange(clean.size) * sp_us
    # Inject single-sample flickers (flip 3% of samples) -> fake fast switches
    noisy = clean.copy()
    flip = rng.random(noisy.size) < 0.03
    noisy[flip] ^= 1

    stats_clean = dwell_time_statistics(clean, t)
    stats_nodb = dwell_time_statistics(noisy, t)
    stats_db = dwell_time_statistics(noisy, t, merge_short_segments=True, min_dwell_bins=2)

    mean_clean = 0.5 * (stats_clean["mean_0"] + stats_clean["mean_1"])
    mean_nodb = 0.5 * (stats_nodb["mean_0"] + stats_nodb["mean_1"])
    mean_db = 0.5 * (stats_db["mean_0"] + stats_db["mean_1"])
    assert mean_nodb < 0.5 * mean_clean, f"expected flickers to bias mean low, got {mean_nodb} vs {mean_clean}"
    assert abs(mean_db - mean_clean) / mean_clean < 0.30, f"debounced mean {mean_db} far from clean {mean_clean}"
    # Debounce must respect gaps: a gap index must never merge across the boundary
    g = [clean.size // 2]
    _ = dwell_time_statistics(noisy, t, gap_indices=g, merge_short_segments=True, min_dwell_bins=2)
    print("dwell_time_statistics debounce: OK")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity`
Expected: FAIL — `dwell_time_statistics() got an unexpected keyword argument 'merge_short_segments'`

- [ ] **Step 3: Add the debounce helpers** — insert above `dwell_time_statistics`:

```python
def _debounce_bits(bits, min_len):
    """Merge runs shorter than min_len into the neighbouring run (single segment)."""
    bits = np.asarray(bits).astype(int).copy()
    if bits.size == 0 or min_len <= 1:
        return bits
    changed = True
    while changed:
        changed = False
        edges = np.flatnonzero(np.diff(bits)) + 1
        starts = np.concatenate(([0], edges))
        ends = np.concatenate((edges, [bits.size]))
        lengths = ends - starts
        for i in range(starts.size):
            if lengths[i] < min_len:
                if i > 0:
                    bits[starts[i]:ends[i]] = bits[starts[i - 1]]
                elif i + 1 < starts.size:
                    bits[starts[i]:ends[i]] = bits[starts[i + 1]]
                changed = True
                break
    return bits


def _debounce_bits_segmented(bits, gap_indices, min_dwell_bins):
    """Apply _debounce_bits within each gap-delimited segment (never across a gap)."""
    bits = np.asarray(bits).astype(int)
    n = bits.size
    if min_dwell_bins <= 1 or n == 0:
        return bits.copy()
    valid = sorted({int(g) for g in (gap_indices or []) if 0 < int(g) < n})
    edges = [0] + valid + [n]
    out = bits.copy()
    for a, b in zip(edges[:-1], edges[1:]):
        out[a:b] = _debounce_bits(bits[a:b], min_dwell_bins)
    return out
```

- [ ] **Step 4: Wire the params into `dwell_time_statistics`** — change its signature and add a debounce line as the first statement of the body:

```python
def dwell_time_statistics(binary_states, t_us, gap_indices=None,
                          merge_short_segments=False, min_dwell_bins=1):
    binary_states = np.asarray(binary_states).astype(int)
    if merge_short_segments and min_dwell_bins > 1:
        binary_states = _debounce_bits_segmented(binary_states, gap_indices, min_dwell_bins)
    # ... existing body unchanged from here ...
```

(Keep the rest of the existing function exactly as-is; only the signature and the two new leading lines change.)

- [ ] **Step 5: Run to verify it passes**

Run: `python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity`
Expected: PASS — prints `dwell_time_statistics debounce: OK`, all prior "OK" lines still print.

- [ ] **Step 6: Commit**

```bash
git add WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/analyze_ZeroSpanParity.py
git commit -m "feat(parity): add opt-in dwell-time debounce (spec 3.6)"
```

---

## Task 2: `verify_modulation` (stage 3 analysis, spec §3.1)

**Files:**
- Modify: `Experiments/analyze_ZeroSpanParity.py` (add function + `__main__` tests)

- [ ] **Step 1: Write the failing tests** — append in `__main__`:

```python
    # --- Task 2: verify_modulation ---
    rng = np.random.default_rng(0)
    nblk, reps = 10, 500
    sp_us = 20.0
    ref = np.tile(np.concatenate([np.ones(reps), np.zeros(reps)]), nblk)
    t = np.arange(ref.size) * sp_us
    scores = np.where(ref > 0.5, 5.0, 0.0) + rng.normal(0, 1.0, ref.size)
    vm = verify_modulation(scores, t, ref)
    assert vm["correlation"] > 0.9, f"correlation too low: {vm['correlation']}"
    assert vm["modulation_depth"] > 3.0, f"depth too low: {vm['modulation_depth']}"
    assert abs(vm["lag_samples"]) <= 1, f"unexpected lag: {vm['lag_samples']}"
    # Null case: no modulation -> no false positive
    flat = rng.normal(0, 1.0, ref.size)
    vm0 = verify_modulation(flat, t, ref)
    assert abs(vm0["correlation"]) < 0.2, f"false positive correlation: {vm0['correlation']}"
    assert vm0["modulation_depth"] < 0.5, f"false positive depth: {vm0['modulation_depth']}"
    print("verify_modulation: OK")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity`
Expected: FAIL — `name 'verify_modulation' is not defined`

- [ ] **Step 3: Implement** — add to the module (near the other primitives):

```python
def verify_modulation(scores, t_us, modulation_reference, gap_indices=None):
    """Confirm a recovered projected trace carries an injected on/off square wave.

    Primary metrics: level_on/off, modulation_depth, snr, correlation, lag_samples.
    Secondary (diagnostic only): recovered_freq_hz vs injected_freq_hz.
    """
    scores = np.asarray(scores, dtype=float).ravel()
    ref = np.asarray(modulation_reference, dtype=float).ravel()
    t_us = np.asarray(t_us, dtype=float).ravel()
    out = {"level_on": np.nan, "level_off": np.nan, "modulation_depth": np.nan,
           "snr": np.nan, "correlation": np.nan, "lag_samples": 0,
           "recovered_freq_hz": np.nan, "injected_freq_hz": np.nan}
    n = min(scores.size, ref.size, t_us.size)
    if n < 2:
        return out
    scores, ref, t_us = scores[:n], ref[:n], t_us[:n]
    on = ref > 0.5
    off = ~on
    if on.sum() == 0 or off.sum() == 0:
        return out
    level_on = float(np.mean(scores[on]))
    level_off = float(np.mean(scores[off]))
    pooled = float(np.sqrt(0.5 * (np.var(scores[on]) + np.var(scores[off]))))
    out["level_on"] = level_on
    out["level_off"] = level_off
    out["modulation_depth"] = abs(level_on - level_off)
    out["snr"] = abs(level_on - level_off) / pooled if pooled > 0 else np.inf
    # Normalised cross-correlation (primary)
    s = scores - scores.mean()
    r = ref - ref.mean()
    denom = float(np.sqrt(np.sum(s * s) * np.sum(r * r)))
    if denom > 0:
        full = np.correlate(s, r, mode="full") / denom
        k = int(np.argmax(np.abs(full)))
        out["correlation"] = float(full[k])
        out["lag_samples"] = int(k - (n - 1))
    # Injected freq from reference transitions (count half-periods)
    dt_us = float(np.median(np.diff(t_us))) if n > 1 else 0.0
    duration_s = (t_us[-1] - t_us[0]) * 1e-6
    transitions = int(np.count_nonzero(np.diff((ref > 0.5).astype(int))))
    if duration_s > 0 and transitions > 0:
        out["injected_freq_hz"] = (transitions / 2.0) / duration_s
    # Recovered freq from dominant FFT bin (diagnostic only)
    if dt_us > 0 and n > 4:
        freqs = np.fft.rfftfreq(n, d=dt_us * 1e-6)
        spec = np.abs(np.fft.rfft(scores - scores.mean()))
        if spec.size > 1:
            out["recovered_freq_hz"] = float(freqs[1:][int(np.argmax(spec[1:]))])
    return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity`
Expected: PASS — prints `verify_modulation: OK`

- [ ] **Step 5: Commit**

```bash
git add WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/analyze_ZeroSpanParity.py
git commit -m "feat(parity): add verify_modulation (stage 3 analysis)"
```

---

## Task 3: `modulated_strobe_acquire` + `ZeroSpanParity.set_qubit_gain` (stage 3 acquisition, spec §2)

**Files:**
- Modify: `Experiments/mZeroSpanParity.py` (add `set_qubit_gain` to `ZeroSpanParity`)
- Modify: `Experiments/utils.py` (add `modulated_strobe_acquire` + `__main__` test)

- [ ] **Step 1: Add `set_qubit_gain` to `ZeroSpanParity`** — in `mZeroSpanParity.py`, add a method to the `ZeroSpanParity` class (so the qubit gain can change between blocks and the strobe program is rebuilt):

```python
    def set_qubit_gain(self, gain):
        """Update qubit drive gain and rebuild the strobe program in place.

        Used by modulated_strobe_acquire to square-wave the drive across blocks.
        Strobe mode only.
        """
        if self.cfg.get("mode", "strobe") != "strobe":
            raise RuntimeError("set_qubit_gain is strobe-mode only")
        self.cfg["qubit_gain"] = gain
        self.prog = ZeroSpanParityProgStrobe(self.soccfg, self.cfg)
```

- [ ] **Step 2: Write the failing test** — in `utils.py` `__main__`, add a fake experiment whose `acquire()` returns IQ whose level tracks the current `qubit_gain`, so we can verify the modulation reference aligns with the actually-applied gains:

```python
    # --- Task 3: modulated_strobe_acquire ---
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
    print("utils.py modulated_strobe_acquire: OK")
```

- [ ] **Step 3: Run to verify it fails**

Run: `python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils`
Expected: FAIL — `name 'modulated_strobe_acquire' is not defined`

- [ ] **Step 4: Implement `modulated_strobe_acquire`** — add to `utils.py` (mirrors `chunked_acquire` stitching, adds gain scheduling + reference):

```python
def modulated_strobe_acquire(experiment, gain_schedule, reps_per_block, progress=False):
    """Run strobe acquisition in blocks, setting qubit_gain per block, and stitch.

    gain_schedule : list of gain values, one per block (e.g. [G_on, 0, G_on, 0, ...]).
    reps_per_block : reps (= time samples) per block; must satisfy avg_maxlen (rule 4).

    Returns the chunked_acquire contract plus:
      modulation_reference : per-sample 1.0 where the block gain > 0 else 0.0
      block_labels         : the gains actually applied, per block
      reps_per_block, sample_period_us, modulation_freq_hz
    """
    I_parts, Q_parts, t_parts = [], [], []
    ref_parts, gaps, wall_starts = [], [], []
    cum_idx = 0
    cum_offset_us = 0.0
    sample_period = float(experiment.cfg.get("sample_period_us", 0.0))
    first_meta = {}
    for bi, gain in enumerate(gain_schedule):
        experiment.set_qubit_gain(gain)
        data = experiment.acquire(progress=False)
        I_c = np.asarray(data["I"]).ravel()
        Q_c = np.asarray(data["Q"]).ravel()
        t_c = np.asarray(data["t_us"], dtype=float).ravel()
        if bi == 0:
            for k in _META_KEYS:
                if k in data:
                    first_meta[k] = data[k]
            sample_period = float(data.get("sample_period_us", sample_period) or sample_period)
        if bi > 0:
            gaps.append(cum_idx)
        t_parts.append(t_c + cum_offset_us)
        if t_c.size >= 2:
            cum_offset_us = t_parts[-1][-1] + (t_c[1] - t_c[0])
        else:
            cum_offset_us = t_parts[-1][-1] + sample_period
        I_parts.append(I_c)
        Q_parts.append(Q_c)
        ref_parts.append(np.full(I_c.size, 1.0 if gain > 0 else 0.0))
        wall_starts.append(data.get("wall_clock_start"))
        cum_idx += I_c.size
    stitched = {
        "I": np.concatenate(I_parts),
        "Q": np.concatenate(Q_parts),
        "t_us": np.concatenate(t_parts),
        "modulation_reference": np.concatenate(ref_parts),
        "gap_indices": gaps,
        "block_labels": list(gain_schedule),
        "chunk_wall_clock_starts": wall_starts,
        "n_chunks": len(gain_schedule),
        "reps_per_block": int(reps_per_block),
        "sample_period_us": sample_period,
        "modulation_freq_hz": (1.0 / (2.0 * reps_per_block * sample_period * 1e-6))
                              if reps_per_block > 0 and sample_period > 0 else float("nan"),
    }
    stitched.update(first_meta)
    return stitched
```

(If `_META_KEYS` is not already module-level visible at this point in `utils.py`, this function is defined after it — `chunked_acquire` and `_META_KEYS` already exist above.)

- [ ] **Step 5: Run to verify it passes**

Run: `python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils`
Expected: PASS — prints `utils.py modulated_strobe_acquire: OK`

- [ ] **Step 6: Run the acquisition module's tests too (set_qubit_gain must not break existing validation)**

Run: `python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mZeroSpanParity`
Expected: PASS — existing `_validate_cfg` tests still print OK.

- [ ] **Step 7: Commit**

```bash
git add WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/utils.py WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/mZeroSpanParity.py
git commit -m "feat(parity): add modulated_strobe_acquire + set_qubit_gain (stage 3 acquisition)"
```

---

## Task 4: Harness scaffold + `run_modulation_check` (stage 3 end-to-end, spec §4.3/§4.7)

Creates `validate_ZeroSpanParity.py` with the sidecar helper, a modulation plot, and the first `run_*`. After this task, **stage 3 is complete end-to-end** (offline-plumbing-tested; real-qubit run is §6.3).

**Files:**
- Create: `Experiments/validate_ZeroSpanParity.py`

- [ ] **Step 1: Write the failing test** — create the file with imports, a `__main__` test using a fake experiment, and run it before implementing:

```python
"""Zero-span parity validation harness (spec 2026-06-01).

Composes ZeroSpanParity acquisition + analyze_ZeroSpanParity primitives into the
9-stage contrast/SNR validation chain. Strobe-only. Collate-only report.
"""
import os
import json
import datetime

import numpy as np
import h5py

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils import (
    modulated_strobe_acquire,
)
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity import (
    classify_parity_trace,
    verify_modulation,
    projected_histogram_snr,
    bin_size_sweep,
    threshold_stability,
    contrast_from_sweeps,
    dwell_time_statistics,
    sliding_window_switch_rate,
)
```

then at the bottom:

```python
if __name__ == "__main__":
    import tempfile

    class _StrobeFakeExp:
        """Fake ZeroSpanParity: acquire() returns bimodal IQ when driven, unimodal off."""
        def __init__(self, n, sp_us, out_dir):
            self.cfg = {"qubit_gain": 200, "reps_per_chunk": n, "reps": n,
                        "sample_period_us": sp_us, "read_pulse_freq": 100.0,
                        "parity_drive_freq": 4000.0, "device": "TEST", "mode": "strobe",
                        "pulse_gain": 300}
            self._n = n
            self._sp = sp_us
            self._rng = np.random.default_rng(0)
            self.fname = os.path.join(out_dir, "fake.h5")
        def set_qubit_gain(self, gain):
            self.cfg["qubit_gain"] = gain
        def acquire(self, progress=False):
            g = self.cfg["qubit_gain"]
            level = 5.0 if g > 0 else 0.0
            I = level + self._rng.normal(0, 0.8, self._n)
            Q = self._rng.normal(0, 0.8, self._n)
            t = np.arange(self._n) * self._sp
            return {"I": I, "Q": Q, "t_us": t, "mode": "strobe",
                    "sample_period_us": self._sp, "read_length_us": 5.0,
                    "wall_clock_start": "2026-01-01T00:00:00"}

    sep = {"g_center": np.array([0.0, 0.0]), "e_center": np.array([5.0, 0.0])}
    with tempfile.TemporaryDirectory() as d:
        exp = _StrobeFakeExp(500, 20.0, d)
        res = run_modulation_check(exp, separator=sep, modulation_freq_hz=50.0, n_periods=4, out_dir=d)
        assert res["correlation"] > 0.8, res["correlation"]
        assert res["modulation_depth"] > 2.0, res["modulation_depth"]
        # sidecar written
        sidecars = [f for f in os.listdir(d) if f.startswith("3_modulation_check") and f.endswith(".json")]
        assert sidecars, "no modulation sidecar json written"
        with open(os.path.join(d, sidecars[0])) as fh:
            meta = json.load(fh)
        assert meta["stage"] == "3_modulation_check"
        assert meta["mode"] == "strobe"
    print("validate_ZeroSpanParity run_modulation_check: OK")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.validate_ZeroSpanParity`
Expected: FAIL — `name 'run_modulation_check' is not defined`

- [ ] **Step 3: Implement the sidecar helper** — add after the imports:

```python
def _timestamp():
    return datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")


ANALYSIS_VERSION = "1.0"


def _stage_sidecar(experiment, stage, scalars, arrays=None, extra_meta=None, out_dir=None):
    """Write a self-describing JSON (metadata + scalars) and an .h5 (raw arrays).

    Returns (json_path, h5_path). Arrays make every stage reprocessable offline.
    """
    cfg = getattr(experiment, "cfg", {})
    base_dir = out_dir or os.path.dirname(getattr(experiment, "fname", "") or ".") or "."
    base = os.path.join(base_dir, f"{stage}_{_timestamp()}")
    meta = {
        "stage": stage,
        "timestamp": datetime.datetime.now().isoformat(),
        "device": cfg.get("device"),
        "mode": cfg.get("mode", "strobe"),
        "sample_period_us": cfg.get("sample_period_us"),
        "reps": cfg.get("reps_per_chunk", cfg.get("reps")),
        "read_pulse_freq": cfg.get("read_pulse_freq"),
        "parity_drive_freq": cfg.get("parity_drive_freq"),
        "qubit_gain": cfg.get("qubit_gain"),
        "read_pulse_gain": cfg.get("pulse_gain"),
        "bin_us": (extra_meta or {}).get("bin_us"),
        "threshold": (extra_meta or {}).get("threshold"),
        "gap_indices_present": bool((arrays or {}).get("gap_indices")),
        "analysis_version": ANALYSIS_VERSION,
    }
    meta.update(extra_meta or {})
    meta["scalars"] = {k: (None if v is None else (float(v) if np.isscalar(v) and not isinstance(v, str) else v))
                       for k, v in scalars.items()}
    json_path = base + ".json"
    with open(json_path, "w") as fh:
        json.dump(meta, fh, indent=2, default=str)
    h5_path = base + ".h5"
    if arrays:
        with h5py.File(h5_path, "w") as f:
            for k, v in arrays.items():
                if v is None:
                    continue
                if k == "gap_indices":
                    f.create_dataset(k, data=np.asarray(list(v), dtype=int))
                else:
                    f.create_dataset(k, data=np.asarray(v))
            for mk, mv in meta.items():
                if mk == "scalars":
                    continue
                f.attrs[mk] = "" if mv is None else mv
    return json_path, h5_path
```

- [ ] **Step 4: Implement the modulation plot + `run_modulation_check`**:

```python
def _plot_modulation(scores, t_us, reference, vm, out_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(t_us / 1e6, scores, lw=0.5, label="V(t) recovered")
    span = np.nanmax(scores) - np.nanmin(scores) if scores.size else 1.0
    ax.plot(t_us / 1e6, np.nanmin(scores) + reference * span, "r-", alpha=0.5,
            label="injected on/off")
    ax.set_xlabel("time (s)")
    ax.set_ylabel("projected V")
    ax.set_title(f"Modulation check  corr={vm['correlation']:.2f}  depth={vm['modulation_depth']:.2f}  snr={vm['snr']:.2f}")
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def run_modulation_check(experiment, separator, modulation_freq_hz=25.0, n_periods=10,
                         progress=False, out_dir=None):
    """Stage 3: artificial square-wave modulation sanity gate.

    One block = one half-period (explicit factor of 2). Builds an alternating
    [G_on, 0] schedule, acquires, projects, and verifies recovery.
    """
    sp_us = float(experiment.cfg["sample_period_us"])
    g_on = experiment.cfg["qubit_gain"]
    reps_per_block = int(round(1.0 / (2.0 * modulation_freq_hz * sp_us * 1e-6)))
    reps_per_block = max(1, reps_per_block)
    actual_freq = 1.0 / (2.0 * reps_per_block * sp_us * 1e-6)
    schedule = [g_on, 0] * int(n_periods)
    acq = modulated_strobe_acquire(experiment, schedule, reps_per_block, progress=progress)
    cls = classify_parity_trace(acq["I"], acq["Q"], separator=separator, method="apriori")
    vm = verify_modulation(cls["scores"], acq["t_us"], acq["modulation_reference"],
                           gap_indices=acq["gap_indices"])
    vm["injected_freq_hz"] = actual_freq
    arrays = {"I": acq["I"], "Q": acq["Q"], "t_us": acq["t_us"],
              "scores": cls["scores"], "modulation_reference": acq["modulation_reference"],
              "gap_indices": acq["gap_indices"]}
    json_path, _ = _stage_sidecar(experiment, "3_modulation_check", scalars=vm, arrays=arrays,
                                  extra_meta={"reps_per_block": reps_per_block,
                                              "n_periods": n_periods,
                                              "modulation_freq_hz": actual_freq}, out_dir=out_dir)
    _plot_modulation(cls["scores"], acq["t_us"], acq["modulation_reference"], vm,
                     json_path.replace(".json", ".png"))
    return {**vm, "acq": acq, "classification": cls, "sidecar": json_path}
```

- [ ] **Step 5: Run to verify it passes**

Run: `python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.validate_ZeroSpanParity`
Expected: PASS — prints `validate_ZeroSpanParity run_modulation_check: OK`

- [ ] **Step 6: Commit**

```bash
git add WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/validate_ZeroSpanParity.py
git commit -m "feat(parity): harness scaffold + run_modulation_check (stage 3 complete)"
```

---

## Task 5: `contrast_from_sweeps` (stage 1 analysis, spec §3.5)

**Files:**
- Modify: `Experiments/analyze_ZeroSpanParity.py`

- [ ] **Step 1: Write the failing test** — in `__main__`:

```python
    # --- Task 5: contrast_from_sweeps ---
    f = np.linspace(99.0, 101.0, 201)
    # Two slightly shifted Lorentzian complex responses
    def _lor(f0):
        return 1.0 / (1 + 1j * (f - f0) / 0.05)
    Z_off = _lor(100.0)
    Z_on = _lor(100.05)
    c = contrast_from_sweeps(f, Z_on, Z_off)
    assert np.isfinite(c["best_freq"]), c
    assert 99.5 < c["best_freq"] < 100.5, c["best_freq"]
    assert c["max_contrast"] > 0, c["max_contrast"]
    assert c["contrast_snr"] > 3.0, c["contrast_snr"]
    # empty input
    ce = contrast_from_sweeps(np.array([]), np.array([]), np.array([]))
    assert not np.isfinite(ce["best_freq"]), ce
    print("contrast_from_sweeps: OK")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity`
Expected: FAIL — `name 'contrast_from_sweeps' is not defined`

- [ ] **Step 3: Implement**:

```python
def contrast_from_sweeps(freqs, Z_on, Z_off):
    """Stage 1: |Z_on - Z_off|(f), best probe freq, robust contrast SNR.

    Z_on/Z_off are complex demodulated responses (proportional to S21, NOT
    calibrated S21).
    """
    freqs = np.asarray(freqs, dtype=float).ravel()
    Z_on = np.asarray(Z_on).ravel()
    Z_off = np.asarray(Z_off).ravel()
    out = {"freqs": freqs, "contrast": np.zeros(0), "best_freq": np.nan,
           "max_contrast": np.nan, "contrast_snr": np.nan,
           "Z_on": Z_on, "Z_off": Z_off}
    n = min(freqs.size, Z_on.size, Z_off.size)
    if n == 0:
        return out
    freqs, Z_on, Z_off = freqs[:n], Z_on[:n], Z_off[:n]
    contrast = np.abs(Z_on - Z_off)
    idx = int(np.argmax(contrast))
    med = float(np.median(contrast))
    mad = float(np.median(np.abs(contrast - med)))
    noise_floor = 1.4826 * mad if mad > 0 else (med if med > 0 else 1.0)
    out.update({"freqs": freqs, "contrast": contrast,
                "best_freq": float(freqs[idx]), "max_contrast": float(contrast[idx]),
                "contrast_snr": float(contrast[idx] / noise_floor) if noise_floor > 0 else np.inf,
                "Z_on": Z_on, "Z_off": Z_off})
    return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity`
Expected: PASS — prints `contrast_from_sweeps: OK`

- [ ] **Step 5: Commit**

```bash
git add WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/analyze_ZeroSpanParity.py
git commit -m "feat(parity): add contrast_from_sweeps (stage 1 analysis)"
```

---

## Task 6: `run_static_contrast` (stage 1, spec §4.1)

**Files:**
- Modify: `Experiments/validate_ZeroSpanParity.py`

- [ ] **Step 1: Write the failing test** — in `__main__` (reuse `_StrobeFakeExp` from Task 4; its `acquire()` returns a level that depends on `qubit_gain`, so on/off differ):

```python
    with tempfile.TemporaryDirectory() as d:
        exp = _StrobeFakeExp(200, 20.0, d)
        freq_list = np.linspace(95.0, 105.0, 11)
        res = run_static_contrast(exp, freq_list, qubit_gain_on=200, out_dir=d)
        assert res["contrast"].shape == (freq_list.size,), res["contrast"].shape
        assert np.all(np.isfinite(res["Z_on"])) and np.all(np.isfinite(res["Z_off"]))
        files = [f for f in os.listdir(d) if f.startswith("1_static_contrast")]
        assert any(f.endswith(".png") for f in files), "no contrast plot"
        assert any(f.endswith(".json") for f in files), "no contrast sidecar"
    print("validate_ZeroSpanParity run_static_contrast: OK")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.validate_ZeroSpanParity`
Expected: FAIL — `name 'run_static_contrast' is not defined`

- [ ] **Step 3: Implement** — add to `validate_ZeroSpanParity.py`:

```python
def _mean_complex_response(experiment, progress=False):
    data = experiment.acquire(progress=progress)
    return complex(np.mean(data["I"]) + 1j * np.mean(data["Q"]))


def _plot_contrast(c, out_path, xlabel="read_pulse_freq (MHz)"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(c["freqs"], np.abs(c["Z_on"]), label="|Z_on|")
    ax.plot(c["freqs"], np.abs(c["Z_off"]), label="|Z_off|")
    ax.plot(c["freqs"], c["contrast"], "k-", label="|Z_on - Z_off|")
    if np.isfinite(c["best_freq"]):
        ax.axvline(c["best_freq"], color="r", ls="--", label=f"best={c['best_freq']:.3f}")
    ax.set_xlabel(xlabel)
    ax.set_ylabel("response")
    ax.set_title(f"Static contrast  snr={c['contrast_snr']:.2f}")
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def run_static_contrast(experiment, freq_list, qubit_gain_on, progress=False, out_dir=None):
    """Stage 1: sweep read_pulse_freq, drive ON vs OFF, max |Z_on - Z_off|.

    Z = <I + iQ> averaged per point. NOT calibrated S21.
    Returns contrast_from_sweeps result; best_freq is the recommended read_pulse_freq.
    """
    freq_list = np.asarray(freq_list, dtype=float).ravel()
    Z_on = np.empty(freq_list.size, dtype=complex)
    Z_off = np.empty(freq_list.size, dtype=complex)
    base_gain = experiment.cfg["qubit_gain"]
    base_freq = experiment.cfg.get("read_pulse_freq")
    for i, fr in enumerate(freq_list):
        experiment.cfg["read_pulse_freq"] = float(fr)
        experiment.set_qubit_gain(qubit_gain_on)
        Z_on[i] = _mean_complex_response(experiment, progress=progress)
        experiment.set_qubit_gain(0)
        Z_off[i] = _mean_complex_response(experiment, progress=progress)
    experiment.cfg["read_pulse_freq"] = base_freq
    experiment.set_qubit_gain(base_gain)
    c = contrast_from_sweeps(freq_list, Z_on, Z_off)
    arrays = {"freqs": c["freqs"], "Z_on_real": c["Z_on"].real, "Z_on_imag": c["Z_on"].imag,
              "Z_off_real": c["Z_off"].real, "Z_off_imag": c["Z_off"].imag, "contrast": c["contrast"]}
    scalars = {"best_freq": c["best_freq"], "max_contrast": c["max_contrast"],
               "contrast_snr": c["contrast_snr"]}
    json_path, _ = _stage_sidecar(experiment, "1_static_contrast", scalars=scalars, arrays=arrays,
                                  out_dir=out_dir)
    _plot_contrast(c, json_path.replace(".json", ".png"))
    return {**c, "sidecar": json_path}
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.validate_ZeroSpanParity`
Expected: PASS — prints `validate_ZeroSpanParity run_static_contrast: OK`

- [ ] **Step 5: Commit**

```bash
git add WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/validate_ZeroSpanParity.py
git commit -m "feat(parity): add run_static_contrast (stage 1)"
```

---

## Task 7: `run_contrast_vs_qubit_freq` (stage 2, spec §4.2)

**Files:**
- Modify: `Experiments/validate_ZeroSpanParity.py`

- [ ] **Step 1: Write the failing test** — in `__main__`. Make the fake return a drive-frequency-dependent response by extending the fake with a `parity_drive_freq`-sensitive level via a small subclass:

```python
    class _SpecFakeExp(_StrobeFakeExp):
        def acquire(self, progress=False):
            g = self.cfg["qubit_gain"]
            fq = self.cfg["parity_drive_freq"]
            # two "branches" at 3998 and 4002 -> larger response near them when driven
            resp = 0.0
            if g > 0:
                resp = 5.0 * (np.exp(-((fq - 3998.0) ** 2) / 0.5) + np.exp(-((fq - 4002.0) ** 2) / 0.5))
            I = resp + self._rng.normal(0, 0.5, self._n)
            Q = self._rng.normal(0, 0.5, self._n)
            t = np.arange(self._n) * self._sp
            return {"I": I, "Q": Q, "t_us": t, "mode": "strobe",
                    "sample_period_us": self._sp, "read_length_us": 5.0,
                    "wall_clock_start": "2026-01-01T00:00:00"}

    with tempfile.TemporaryDirectory() as d:
        exp = _SpecFakeExp(200, 20.0, d)
        qf = np.linspace(3995.0, 4005.0, 51)
        res = run_contrast_vs_qubit_freq(exp, qf, out_dir=d)
        assert res["contrast"].shape == (qf.size,), res["contrast"].shape
        # the two branches should be the two strongest contrast points
        top2 = qf[np.argsort(res["contrast"])[-2:]]
        assert min(abs(top2 - 3998.0).min(), abs(top2 - 4002.0).min()) < 0.5, top2
    print("validate_ZeroSpanParity run_contrast_vs_qubit_freq: OK")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.validate_ZeroSpanParity`
Expected: FAIL — `name 'run_contrast_vs_qubit_freq' is not defined`

- [ ] **Step 3: Implement**:

```python
def run_contrast_vs_qubit_freq(experiment, qfreq_list, progress=False, out_dir=None):
    """Stage 2: contrast(f_q) = |<Z>_drive_on - <Z>_drive_off| vs qubit drive freq.

    No telegraph exists at each driven steady state, so DO NOT use histogram
    bimodality here -- use complex-response difference against a drive-off baseline.
    Run this at the resonator probe point already optimized by stage 1.
    """
    from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity import (
        find_two_tone_peaks,
    )
    qfreq_list = np.asarray(qfreq_list, dtype=float).ravel()
    base_gain = experiment.cfg["qubit_gain"]
    base_qfreq = experiment.cfg.get("parity_drive_freq")
    # drive-off baseline at current probe point
    experiment.set_qubit_gain(0)
    z_off = _mean_complex_response(experiment, progress=progress)
    contrast = np.empty(qfreq_list.size, dtype=float)
    z_on = np.empty(qfreq_list.size, dtype=complex)
    for i, fq in enumerate(qfreq_list):
        experiment.cfg["parity_drive_freq"] = float(fq)
        experiment.set_qubit_gain(base_gain)
        z_on[i] = _mean_complex_response(experiment, progress=progress)
        contrast[i] = abs(z_on[i] - z_off)
    experiment.cfg["parity_drive_freq"] = base_qfreq
    experiment.set_qubit_gain(base_gain)
    peaks = find_two_tone_peaks(qfreq_list, contrast)
    arrays = {"qfreqs": qfreq_list, "contrast": contrast,
              "z_on_real": z_on.real, "z_on_imag": z_on.imag}
    scalars = {"z_off_real": z_off.real, "z_off_imag": z_off.imag,
               "peak_sep": peaks.get("peak_sep")}
    json_path, _ = _stage_sidecar(experiment, "2_contrast_vs_qubit_freq", scalars=scalars,
                                  arrays=arrays, out_dir=out_dir)
    _plot_contrast({"freqs": qfreq_list, "Z_on": z_on, "Z_off": np.full(qfreq_list.size, z_off),
                    "contrast": contrast,
                    "best_freq": float(qfreq_list[int(np.argmax(contrast))]) if contrast.size else np.nan,
                    "contrast_snr": np.nan},
                   json_path.replace(".json", ".png"), xlabel="parity_drive_freq (MHz)")
    return {"qfreqs": qfreq_list, "contrast": contrast, "z_on": z_on, "z_off": z_off,
            "peaks": peaks, "sidecar": json_path}
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.validate_ZeroSpanParity`
Expected: PASS — prints `validate_ZeroSpanParity run_contrast_vs_qubit_freq: OK`

- [ ] **Step 5: Commit**

```bash
git add WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/validate_ZeroSpanParity.py
git commit -m "feat(parity): add run_contrast_vs_qubit_freq (stage 2)"
```

---

## Task 8: `projected_histogram_snr` (stage 4 quantitative, spec §3.2)

**Files:**
- Modify: `Experiments/analyze_ZeroSpanParity.py`

- [ ] **Step 1: Write the failing tests** — in `__main__`:

```python
    # --- Task 8: projected_histogram_snr ---
    rng = np.random.default_rng(0)
    bim = np.concatenate([rng.normal(-3, 1, 5000), rng.normal(3, 1, 5000)])
    h = projected_histogram_snr(bim)
    assert h["is_bimodal"], h
    assert h["delta_bic"] > 0, h["delta_bic"]
    assert h["separation_snr"] > 2.0, h["separation_snr"]
    uni = rng.normal(0, 1, 10000)
    hu = projected_histogram_snr(uni)
    assert not hu["is_bimodal"], hu
    assert hu["delta_bic"] <= 0, hu["delta_bic"]
    print("projected_histogram_snr: OK")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity`
Expected: FAIL — `name 'projected_histogram_snr' is not defined`

- [ ] **Step 3: Implement**:

```python
def projected_histogram_snr(scores, bins="auto"):
    """Stage 4: two-Gaussian fit of V(t) with conservative, BIC-based bimodality.

    A 2-component GMM almost always 'finds' two peaks, so is_bimodal requires
    delta_bic>0 AND separation_snr>1.5 AND both weights in (0.1, 0.9).
    """
    scores = np.asarray(scores, dtype=float).ravel()
    out = {"centers": np.array([np.nan, np.nan]), "sigmas": np.array([np.nan, np.nan]),
           "weights": np.array([np.nan, np.nan]), "separation_snr": 0.0, "overlap": np.nan,
           "is_bimodal": False, "bic_1": np.nan, "bic_2": np.nan, "delta_bic": np.nan,
           "hist": np.zeros(0), "bin_edges": np.zeros(0)}
    if scores.size < 10:
        return out
    from sklearn.mixture import GaussianMixture
    x = scores.reshape(-1, 1)
    g1 = GaussianMixture(n_components=1, random_state=0).fit(x)
    g2 = GaussianMixture(n_components=2, random_state=0).fit(x)
    bic_1 = float(g1.bic(x))
    bic_2 = float(g2.bic(x))
    means = g2.means_.ravel()
    sigmas = np.sqrt(g2.covariances_.ravel())
    weights = g2.weights_.ravel()
    order = np.argsort(means)
    centers, sig, w = means[order], sigmas[order], weights[order]
    denom = np.sqrt(0.5 * (sig[0] ** 2 + sig[1] ** 2))
    sep = float(abs(centers[1] - centers[0]) / denom) if denom > 0 else 0.0
    # Bhattacharyya coefficient (two gaussians) as overlap
    s2 = sig[0] ** 2 + sig[1] ** 2
    bc = float(np.sqrt(2 * sig[0] * sig[1] / s2) * np.exp(-0.25 * (centers[0] - centers[1]) ** 2 / s2)) if s2 > 0 else 1.0
    hist, edges = np.histogram(scores, bins=bins)
    is_bimodal = (bic_1 - bic_2 > 0) and (sep > 1.5) and (0.1 < w[0] < 0.9) and (0.1 < w[1] < 0.9)
    out.update({"centers": centers, "sigmas": sig, "weights": w, "separation_snr": sep,
                "overlap": bc, "is_bimodal": bool(is_bimodal), "bic_1": bic_1, "bic_2": bic_2,
                "delta_bic": bic_1 - bic_2, "hist": hist, "bin_edges": edges})
    return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity`
Expected: PASS — prints `projected_histogram_snr: OK`

- [ ] **Step 5: Commit**

```bash
git add WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/analyze_ZeroSpanParity.py
git commit -m "feat(parity): add projected_histogram_snr with BIC bimodality (stage 4)"
```

---

## Task 9: `bin_size_sweep` (stage 5, spec §3.3)

**Files:**
- Modify: `Experiments/analyze_ZeroSpanParity.py`

- [ ] **Step 1: Write the failing test** — in `__main__`:

```python
    # --- Task 9: bin_size_sweep ---
    rng = np.random.default_rng(1)
    # Markov telegraph at 10 us raw sample period, mean dwell ~2 ms, heavy per-sample noise
    sp_raw = 10.0
    n = 200_000
    p = sp_raw / 2000.0  # switch prob per sample for ~2 ms dwell
    state = 0
    bits = np.empty(n, dtype=int)
    for i in range(n):
        if rng.random() < p:
            state ^= 1
        bits[i] = state
    centers = np.array([[0.0, 0.0], [4.0, 0.0]])
    I = centers[bits, 0] + rng.normal(0, 3.0, n)   # noisy: small bins won't separate
    Q = centers[bits, 1] + rng.normal(0, 3.0, n)
    t = np.arange(n) * sp_raw
    sep = {"g_center": np.array([0.0, 0.0]), "e_center": np.array([4.0, 0.0])}
    res = bin_size_sweep(I, Q, t, sep, bin_list_us=[100, 200, 500, 1000])
    assert np.isfinite(res["best_bin_us"]), res
    snr = np.array(res["separation_snr_per_bin"], dtype=float)
    assert snr[-1] >= snr[0], f"separation should not be worse at large bins: {snr}"
    print("bin_size_sweep: OK")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity`
Expected: FAIL — `name 'bin_size_sweep' is not defined`

- [ ] **Step 3: Implement** (uses `_bin_iq_time`, `classify_parity_trace`, `projected_histogram_snr`, debounced `dwell_time_statistics` — all already defined):

```python
def bin_size_sweep(I, Q, t_us, separator, bin_list_us, gap_indices=None, method="apriori"):
    """Stage 5: reprocess the same raw IQ at several bin sizes.

    Returns per-bin separation SNR and dwell tau. best_bin_us maximizes separation
    SNR. NO monotonic-then-degrade assertion: the optimum can occur before T_parity.
    """
    sep_snr, mean_dwell, exp_tau = [], [], []
    for b in bin_list_us:
        Ib, Qb, tb, gb, _ = _bin_iq_time(I, Q, t_us, float(b), gap_indices)
        cls = classify_parity_trace(Ib, Qb, separator=separator, method=method)
        h = projected_histogram_snr(cls["scores"])
        dw = dwell_time_statistics(cls["binary_states"], tb, gap_indices=gb,
                                   merge_short_segments=True, min_dwell_bins=2)
        sep_snr.append(h["separation_snr"])
        mean_dwell.append(0.5 * (dw["mean_0"] + dw["mean_1"]))
        taus = [dw["exp_fit_0"]["tau_us"], dw["exp_fit_1"]["tau_us"]]
        taus = [tt for tt in taus if np.isfinite(tt)]
        exp_tau.append(float(np.mean(taus)) if taus else np.nan)
    snr_arr = np.array(sep_snr, dtype=float)
    best_bin = float(bin_list_us[int(np.nanargmax(snr_arr))]) if np.any(np.isfinite(snr_arr)) else np.nan
    return {"bin_list_us": list(bin_list_us), "separation_snr_per_bin": sep_snr,
            "mean_dwell_per_bin": mean_dwell, "exp_tau_per_bin": exp_tau, "best_bin_us": best_bin}
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity`
Expected: PASS — prints `bin_size_sweep: OK`

- [ ] **Step 5: Commit**

```bash
git add WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/analyze_ZeroSpanParity.py
git commit -m "feat(parity): add bin_size_sweep (stage 5)"
```

---

## Task 10: `threshold_stability` (stage 6, spec §3.4)

**Files:**
- Modify: `Experiments/analyze_ZeroSpanParity.py`

- [ ] **Step 1: Write the failing test** — in `__main__`:

```python
    # --- Task 10: threshold_stability ---
    rng = np.random.default_rng(2)
    sp = 50.0
    n = 100_000
    p = sp / 2000.0
    state = 0
    bits = np.empty(n, dtype=int)
    for i in range(n):
        if rng.random() < p:
            state ^= 1
        bits[i] = state
    t = np.arange(n) * sp
    clean_scores = np.where(bits == 1, 4.0, -4.0) + rng.normal(0, 1.0, n)  # well separated
    noise_scores = rng.normal(0, 1.0, n)  # pure noise
    ts_clean = threshold_stability(clean_scores, t)
    ts_noise = threshold_stability(noise_scores, t)
    assert ts_clean["tau_cv"] < ts_noise["tau_cv"], (ts_clean["tau_cv"], ts_noise["tau_cv"])
    print("threshold_stability: OK")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity`
Expected: FAIL — `name 'threshold_stability' is not defined`

- [ ] **Step 3: Implement**:

```python
def threshold_stability(scores, t_us, threshold_list=None, gap_indices=None, min_dwell_bins=2):
    """Stage 6: vary the classification threshold; report dwell tau stability.

    Low tau_cv (coefficient of variation across thresholds) = robust telegraph;
    high tau_cv = noise crossings.
    """
    scores = np.asarray(scores, dtype=float).ravel()
    if threshold_list is None:
        threshold_list = list(np.percentile(scores, [30, 40, 50, 60, 70])) if scores.size else [0.0]
    tau0, tau1 = [], []
    for th in threshold_list:
        bits = (scores > th).astype(int)
        dw = dwell_time_statistics(bits, t_us, gap_indices=gap_indices,
                                   merge_short_segments=True, min_dwell_bins=min_dwell_bins)
        tau0.append(dw["exp_fit_0"]["tau_us"])
        tau1.append(dw["exp_fit_1"]["tau_us"])
    allt = np.array([x for x in (tau0 + tau1) if np.isfinite(x)], dtype=float)
    tau_cv = float(np.std(allt) / np.mean(allt)) if allt.size >= 2 and np.mean(allt) > 0 else np.inf
    return {"threshold_list": list(threshold_list), "tau0_per_threshold": tau0,
            "tau1_per_threshold": tau1, "tau_cv": tau_cv}
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity`
Expected: PASS — prints `threshold_stability: OK`

- [ ] **Step 5: Commit**

```bash
git add WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/analyze_ZeroSpanParity.py
git commit -m "feat(parity): add threshold_stability (stage 6)"
```

---

## Task 11: `CrossRunComparison` + `run_environment_sweep` (stage 7, spec §4.5)

**Files:**
- Modify: `Experiments/validate_ZeroSpanParity.py`

- [ ] **Step 1: Write the failing test** — in `__main__`:

```python
    # --- Task 11: CrossRunComparison ---
    cmp = CrossRunComparison(param_name="power_dB")
    cmp.add(-10, {"switch_rate": 100.0, "separation_snr": 5.0, "mean_dwell": 2000.0, "mean_signal_level": 4.0})
    cmp.add(-5, {"switch_rate": 200.0, "separation_snr": 4.0, "mean_dwell": 1000.0, "mean_signal_level": 4.1})
    tbl = cmp.table()
    assert tbl["power_dB"] == [-10, -5], tbl
    assert tbl["switch_rate"] == [100.0, 200.0], tbl
    with tempfile.TemporaryDirectory() as d:
        p = cmp.plot(os.path.join(d, "env.png"))
        assert os.path.exists(p)
    print("validate_ZeroSpanParity CrossRunComparison: OK")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.validate_ZeroSpanParity`
Expected: FAIL — `name 'CrossRunComparison' is not defined`

- [ ] **Step 3: Implement** — add to `validate_ZeroSpanParity.py`:

```python
class CrossRunComparison:
    """Collect (swept_param, {metric: value}) across runs; emit table + plot.

    Shared by stages 5/7/8. Stage 7 records multiple metrics per setting because
    readout power changes both measurement SNR and real parity dynamics.
    """
    METRICS = ("switch_rate", "separation_snr", "mean_dwell", "mean_signal_level")

    def __init__(self, param_name):
        self.param_name = param_name
        self._rows = []

    def add(self, param_value, metrics):
        self._rows.append((param_value, dict(metrics)))

    def table(self):
        self._rows.sort(key=lambda r: r[0])
        out = {self.param_name: [r[0] for r in self._rows]}
        keys = set()
        for _, m in self._rows:
            keys.update(m.keys())
        for k in keys:
            out[k] = [r[1].get(k) for r in self._rows]
        return out

    def plot(self, out_path):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        tbl = self.table()
        metrics = [k for k in self.METRICS if k in tbl]
        fig, axes = plt.subplots(len(metrics), 1, figsize=(8, 2.4 * max(1, len(metrics))), sharex=True)
        if len(metrics) == 1:
            axes = [axes]
        x = tbl[self.param_name]
        for ax, k in zip(axes, metrics):
            ax.plot(x, tbl[k], "o-")
            ax.set_ylabel(k)
        axes[-1].set_xlabel(self.param_name)
        axes[0].set_title("Cross-run comparison")
        fig.tight_layout()
        fig.savefig(out_path, dpi=200)
        plt.close(fig)
        return out_path


def _trace_metrics(experiment, separator, window_us=1000.0, progress=False):
    """Acquire one strobe trace, classify, return the 4 stage-7 metrics."""
    data = experiment.acquire(progress=progress)
    cls = classify_parity_trace(data["I"], data["Q"], separator=separator, method="apriori")
    rate = sliding_window_switch_rate(cls["binary_states"], data["t_us"], window_us)
    dw = dwell_time_statistics(cls["binary_states"], data["t_us"],
                              merge_short_segments=True, min_dwell_bins=2)
    h = projected_histogram_snr(cls["scores"])
    return {"switch_rate": float(np.mean(rate["rate_Hz"])) if rate["rate_Hz"].size else 0.0,
            "separation_snr": h["separation_snr"],
            "mean_dwell": 0.5 * (dw["mean_0"] + dw["mean_1"]),
            "mean_signal_level": float(np.mean(np.abs(data["I"] + 1j * data["Q"])))}


def run_environment_sweep(experiment, separator, param_name, param_values, set_param,
                          window_us=1000.0, progress=False, out_dir=None):
    """Stage 7: vary an environment knob (power/detuning/drive-off), record 4 metrics each.

    set_param(experiment, value) applies the swept parameter (caller-provided so this
    stays decoupled from YOKO/attenuator/cfg specifics). Temperature is logged manually.
    """
    cmp = CrossRunComparison(param_name)
    for v in param_values:
        set_param(experiment, v)
        cmp.add(v, _trace_metrics(experiment, separator, window_us=window_us, progress=progress))
    tbl = cmp.table()
    json_path, _ = _stage_sidecar(experiment, f"7_environment_{param_name}",
                                  scalars={"n_points": len(param_values)},
                                  arrays=None, extra_meta={"table": tbl}, out_dir=out_dir)
    cmp.plot(json_path.replace(".json", ".png"))
    return {"table": tbl, "comparison": cmp, "sidecar": json_path}
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.validate_ZeroSpanParity`
Expected: PASS — prints `validate_ZeroSpanParity CrossRunComparison: OK`

- [ ] **Step 5: Commit**

```bash
git add WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/validate_ZeroSpanParity.py
git commit -m "feat(parity): add CrossRunComparison + run_environment_sweep (stage 7)"
```

---

## Task 12: `run_control_suite` (stage 8, spec §4.4)

**Files:**
- Modify: `Experiments/validate_ZeroSpanParity.py`

- [ ] **Step 1: Write the failing test** — in `__main__` (reuse `_StrobeFakeExp`; control A=drive off should kill contrast, D auto-runs both branches and records sign flip):

```python
    with tempfile.TemporaryDirectory() as d:
        exp = _StrobeFakeExp(2000, 20.0, d)
        sep = {"g_center": np.array([0.0, 0.0]), "e_center": np.array([5.0, 0.0])}
        res = run_control_suite(exp, separator=sep,
                                variants=("A", "D"), detune_mhz=50.0,
                                parity_freqs={"lower": 3998.0, "higher": 4002.0},
                                out_dir=d)
        assert "A" in res["variants"] and "D" in res["variants"], res["variants"]
        # control A (drive off) separation should be lower than driven baseline
        assert res["variants"]["A"]["separation_snr"] <= res["variants"]["D"]["separation_snr_lower"] + 1e-6
        assert "branch_sign_flip" in res["variants"]["D"], res["variants"]["D"]
    print("validate_ZeroSpanParity run_control_suite: OK")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.validate_ZeroSpanParity`
Expected: FAIL — `name 'run_control_suite' is not defined`

- [ ] **Step 3: Implement**:

```python
def _signed_level(experiment, separator, progress=False):
    """Mean projected V relative to the separator midpoint, plus separation SNR."""
    data = experiment.acquire(progress=progress)
    cls = classify_parity_trace(data["I"], data["Q"], separator=separator, method="apriori")
    h = projected_histogram_snr(cls["scores"])
    return float(np.mean(cls["scores"])), h["separation_snr"]


def run_control_suite(experiment, separator, variants=("A", "B", "C", "D"), detune_mhz=50.0,
                      parity_freqs=None, progress=False, out_dir=None):
    """Stage 8: A=drive off, B=detuned, C=probe off-res, D=swap branch (auto both).

    Contrast should vanish for A/B/C; assignment should reverse for D
    (branch_sign_flip True is the strong evidence).
    """
    cfg = experiment.cfg
    base = {"qubit_gain": cfg["qubit_gain"], "parity_drive_freq": cfg.get("parity_drive_freq"),
            "read_pulse_freq": cfg.get("read_pulse_freq")}
    results = {}

    # drive-off reference for sign baseline
    experiment.set_qubit_gain(0)
    off_level, _ = _signed_level(experiment, separator, progress=progress)
    experiment.set_qubit_gain(base["qubit_gain"])

    if "A" in variants:
        experiment.set_qubit_gain(0)
        lvl, snr = _signed_level(experiment, separator, progress=progress)
        results["A"] = {"label": "drive_off", "mean_level": lvl, "separation_snr": snr}
        experiment.set_qubit_gain(base["qubit_gain"])
    if "B" in variants:
        experiment.cfg["parity_drive_freq"] = (base["parity_drive_freq"] or 0.0) + detune_mhz
        experiment.set_qubit_gain(base["qubit_gain"])
        lvl, snr = _signed_level(experiment, separator, progress=progress)
        results["B"] = {"label": "drive_detuned", "mean_level": lvl, "separation_snr": snr}
        experiment.cfg["parity_drive_freq"] = base["parity_drive_freq"]
    if "C" in variants:
        experiment.cfg["read_pulse_freq"] = (base["read_pulse_freq"] or 0.0) + detune_mhz
        lvl, snr = _signed_level(experiment, separator, progress=progress)
        results["C"] = {"label": "probe_off_resonance", "mean_level": lvl, "separation_snr": snr}
        experiment.cfg["read_pulse_freq"] = base["read_pulse_freq"]
    if "D" in variants:
        pf = parity_freqs or {"lower": base["parity_drive_freq"], "higher": base["parity_drive_freq"]}
        experiment.cfg["parity_drive_freq"] = float(pf["lower"])
        experiment.set_qubit_gain(base["qubit_gain"])
        lvl_lo, snr_lo = _signed_level(experiment, separator, progress=progress)
        experiment.cfg["parity_drive_freq"] = float(pf["higher"])
        lvl_hi, snr_hi = _signed_level(experiment, separator, progress=progress)
        sgn_lo = int(np.sign(lvl_lo - off_level))
        sgn_hi = int(np.sign(lvl_hi - off_level))
        results["D"] = {"label": "swap_branch", "mean_level_lower": lvl_lo, "mean_level_higher": lvl_hi,
                        "separation_snr_lower": snr_lo, "separation_snr_higher": snr_hi,
                        "sign_lower": sgn_lo, "sign_higher": sgn_hi,
                        "branch_sign_flip": bool(sgn_lo != sgn_hi)}
        experiment.cfg["parity_drive_freq"] = base["parity_drive_freq"]
    experiment.set_qubit_gain(base["qubit_gain"])

    json_path, _ = _stage_sidecar(experiment, "8_control_suite",
                                  scalars={"off_level": off_level},
                                  arrays=None, extra_meta={"variants": results}, out_dir=out_dir)
    return {"variants": results, "off_level": off_level, "sidecar": json_path}
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.validate_ZeroSpanParity`
Expected: PASS — prints `validate_ZeroSpanParity run_control_suite: OK`

- [ ] **Step 5: Commit**

```bash
git add WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/validate_ZeroSpanParity.py
git commit -m "feat(parity): add run_control_suite with branch sign flip (stage 8)"
```

---

## Task 13: `build_evidence_report` (stage 9, spec §4.6)

**Files:**
- Modify: `Experiments/validate_ZeroSpanParity.py`

- [ ] **Step 1: Write the failing test** — in `__main__` (write a couple of fake sidecars, then build the report):

```python
    with tempfile.TemporaryDirectory() as d:
        for stage, sc in [("1_static_contrast", {"best_freq": 100.05, "contrast_snr": 8.0}),
                          ("3_modulation_check", {"correlation": 0.95, "modulation_depth": 4.0})]:
            with open(os.path.join(d, f"{stage}_2026_01_01_00_00_00.json"), "w") as fh:
                json.dump({"stage": stage, "timestamp": "t", "mode": "strobe",
                           "analysis_version": ANALYSIS_VERSION, "scalars": sc}, fh)
        report = build_evidence_report(d, os.path.join(d, "EVIDENCE.md"))
        assert os.path.exists(report)
        text = open(report).read()
        assert "1_static_contrast" in text and "3_modulation_check" in text
        assert "correlation" in text
    print("validate_ZeroSpanParity build_evidence_report: OK")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.validate_ZeroSpanParity`
Expected: FAIL — `name 'build_evidence_report' is not defined`

- [ ] **Step 3: Implement**:

```python
_STAGE_ORDER = ["1_static_contrast", "2_contrast_vs_qubit_freq", "3_modulation_check",
                "4_telegraph", "5_bin_size_sweep", "6_threshold_stability",
                "7_environment", "8_control_suite"]


def build_evidence_report(run_dir, out_path):
    """Stage 9: collate per-stage sidecars into one markdown report. NO pass/fail.

    Scans run_dir for *.json sidecars, groups by stage prefix, embeds figures and
    scalar tables in canonical order. Flags stale analysis_version.
    """
    sidecars = []
    for fn in sorted(os.listdir(run_dir)):
        if fn.endswith(".json"):
            try:
                with open(os.path.join(run_dir, fn)) as fh:
                    meta = json.load(fh)
            except (ValueError, OSError):
                continue
            if "stage" in meta:
                meta["_file"] = fn
                sidecars.append(meta)

    def _order_key(m):
        for i, pref in enumerate(_STAGE_ORDER):
            if m["stage"].startswith(pref):
                return (i, m.get("timestamp", ""))
        return (len(_STAGE_ORDER), m.get("timestamp", ""))

    sidecars.sort(key=_order_key)
    lines = ["# Zero-Span Parity — Evidence Chain", "",
             f"_Collated from `{run_dir}` — no automated pass/fail; human judgment required._", ""]
    for m in sidecars:
        lines.append(f"## {m['stage']}")
        lines.append("")
        if m.get("analysis_version") != ANALYSIS_VERSION:
            lines.append(f"> ⚠ stale analysis_version {m.get('analysis_version')} "
                         f"(current {ANALYSIS_VERSION}) — consider re-analysis.")
            lines.append("")
        sc = m.get("scalars", {})
        if sc:
            lines.append("| metric | value |")
            lines.append("|---|---|")
            for k, v in sc.items():
                lines.append(f"| {k} | {v} |")
            lines.append("")
        png = os.path.join(run_dir, m["_file"].replace(".json", ".png"))
        if os.path.exists(png):
            lines.append(f"![{m['stage']}]({os.path.basename(png)})")
            lines.append("")
    with open(out_path, "w") as fh:
        fh.write("\n".join(lines))
    return out_path
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.validate_ZeroSpanParity`
Expected: PASS — prints `validate_ZeroSpanParity build_evidence_report: OK`

- [ ] **Step 5: Commit**

```bash
git add WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/validate_ZeroSpanParity.py
git commit -m "feat(parity): add build_evidence_report (stage 9, collate-only)"
```

---

## Task 14: Orchestrator wiring in `CSTQ03_BFC.py` (spec §5)

Add thin `Validate_*` flags + param dicts + linear calls into the harness, mirroring the existing `ZSP_*` block style. No stage logic here.

**Files:**
- Modify: `Experiments/CSTQ03_BFC.py`

- [ ] **Step 1: Locate the existing parity block** — find the `RunZeroSpanParity` / `ZSP_*` block and the `get_apriori_separator_from_singleshot` usage.

Run: `python - <<"PY"` is not needed; use grep:
`grep -n "ZSP_\|RunZeroSpanParity\|get_apriori_separator_from_singleshot\|analyze_parity_run" WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/CSTQ03_BFC.py`
Expected: prints the line numbers of the parity block (≈ lines 2700–2810 per extraction).

- [ ] **Step 2: Add the harness import** near the other parity imports at the top of `CSTQ03_BFC.py`:

```python
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.validate_ZeroSpanParity import (
    run_static_contrast, run_contrast_vs_qubit_freq, run_modulation_check,
    run_control_suite, run_environment_sweep, build_evidence_report,
)
```

- [ ] **Step 3: Add the flags + param dicts** immediately after the existing `ZSP_*` param block:

```python
# ============================ VALIDATION HARNESS (spec 2026-06-01) ============================
# Strobe-only. Each block reuses ZSP_Separator_Cached / ZSP_ParityFreqs_Cached and the
# zsp_cfg already built for ZeroSpanParity. Run order: stage1 -> stage2 -> stage1 refine ->
# stage3 (gate) -> stage4 -> 5/6 -> 8 -> 7 -> 9.  See spec 6.3.
Validate_StaticContrast      = False
Validate_ContrastVsQubitFreq = False
Validate_ModulationCheck     = True     # pipeline-sanity gate -- run first
Validate_ControlSuite        = False
Validate_EnvironmentSweep    = False
Build_EvidenceReport         = False

StaticContrast_params = {"freq_span_mhz": 2.0, "n_points": 41, "reps_per_point": 2000}
ContrastVsQubit_params = {"qfreq_span_mhz": 10.0, "n_points": 81}
Modulation_params = {"modulation_freq_hz": 25, "n_periods": 10}
Control_params = {"variants": ["A", "B", "C", "D"], "detune_mhz": 50.0}
Environment_params = {"param_name": "power_dB", "values": [-10, -8, -6, -4]}
```

- [ ] **Step 4: Add the execution block** after the existing `analyze_parity_run(...)` call (so `zsp` = the constructed `ZeroSpanParity`, `zsp_separator`, and `zsp_cfg` are already in scope):

```python
# --- Validation harness execution ---
_val_out_dir = zsp.outerFolder if hasattr(zsp, "outerFolder") else os.path.dirname(zsp.fname)

if Validate_StaticContrast:
    if ZSP_Separator_Cached.get("g_center") is None:
        raise RuntimeError("Validate_StaticContrast needs a calibrated separator (set RecalibrateSeparator)")
    _f0 = zsp_cfg["read_pulse_freq"]
    _span = StaticContrast_params["freq_span_mhz"]
    _flist = np.linspace(_f0 - _span / 2, _f0 + _span / 2, StaticContrast_params["n_points"])
    zsp.cfg["reps_per_chunk"] = StaticContrast_params["reps_per_point"]
    _sc = run_static_contrast(zsp, _flist, qubit_gain_on=zsp_cfg["qubit_gain"], out_dir=_val_out_dir)
    print(f"[stage 1] best read_pulse_freq = {_sc['best_freq']:.4f} MHz  (contrast SNR {_sc['contrast_snr']:.1f})")

if Validate_ContrastVsQubitFreq:
    _q0 = zsp_cfg["parity_drive_freq"]
    _qspan = ContrastVsQubit_params["qfreq_span_mhz"]
    _qlist = np.linspace(_q0 - _qspan / 2, _q0 + _qspan / 2, ContrastVsQubit_params["n_points"])
    _s2 = run_contrast_vs_qubit_freq(zsp, _qlist, out_dir=_val_out_dir)
    print(f"[stage 2] parity peak sep = {_s2['peaks'].get('peak_sep')}")

if Validate_ModulationCheck:
    _m = run_modulation_check(zsp, separator=zsp_separator,
                              modulation_freq_hz=Modulation_params["modulation_freq_hz"],
                              n_periods=Modulation_params["n_periods"], out_dir=_val_out_dir)
    print(f"[stage 3] modulation corr={_m['correlation']:.2f} depth={_m['modulation_depth']:.2f} "
          f"snr={_m['snr']:.2f}  (gate: proceed only if recovered)")

if Validate_ControlSuite:
    _pf = {"lower": ZSP_ParityFreqs_Cached.get("lower_peak_MHz"),
           "higher": ZSP_ParityFreqs_Cached.get("higher_peak_MHz")}
    _c = run_control_suite(zsp, separator=zsp_separator, variants=tuple(Control_params["variants"]),
                           detune_mhz=Control_params["detune_mhz"], parity_freqs=_pf, out_dir=_val_out_dir)
    print(f"[stage 8] controls: {[(k, v.get('separation_snr', v.get('separation_snr_lower'))) for k, v in _c['variants'].items()]}")

if Validate_EnvironmentSweep:
    def _set_power(_exp, _val):
        _exp.cfg["pulse_gain"] = _val  # NOTE: replace with attenuator/YOKO call for real power sweep
        _exp.prog = type(_exp.prog)(_exp.soccfg, _exp.cfg)
    _e = run_environment_sweep(zsp, separator=zsp_separator,
                               param_name=Environment_params["param_name"],
                               param_values=Environment_params["values"],
                               set_param=_set_power, out_dir=_val_out_dir)
    print(f"[stage 7] swept {Environment_params['param_name']}: {_e['table']}")

if Build_EvidenceReport:
    _rep = build_evidence_report(_val_out_dir, os.path.join(_val_out_dir, "EVIDENCE.md"))
    print(f"[stage 9] evidence report written: {_rep}")
```

- [ ] **Step 5: Smoke-import the orchestrator** (no hardware: importing must not raise; it will stop at `makeProxy()` if run fully, so only check the harness import + syntax):

Run: `python -c "import ast; ast.parse(open(r'WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/CSTQ03_BFC.py').read())"`
Expected: no output (syntax OK).

- [ ] **Step 6: Commit**

```bash
git add WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/CSTQ03_BFC.py
git commit -m "feat(parity): wire validation harness flags into CSTQ03_BFC orchestrator"
```

---

## Task 15: Loopback checks (spec §6.2)

Extend the loopback smoke test so `modulated_strobe_acquire` and `run_static_contrast` are exercised on real RFSoC plumbing (DAC→ADC cable, tiny gains, no qubit).

**Files:**
- Modify: `Experiments/_loopback_check_ZeroSpanParity.py`

- [ ] **Step 1: Add the modulated-acquire loopback check** — append to the loopback script's check sequence (after the existing strobe/chunked checks), following its existing pattern of constructing a `ZeroSpanParity` with a real `soc, soccfg` and a placeholder `parity_drive_freq` + tiny `pulse_gain`:

```python
    # --- Loopback: modulated_strobe_acquire ---
    from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils import modulated_strobe_acquire
    zsp_mod = ZeroSpanParity(soc=soc, soccfg=soccfg, cfg=dict(loopback_cfg), outerFolder=tmp_dir, prefix="loopback_mod")
    schedule = [loopback_cfg["qubit_gain"], 0] * 2   # 2 periods
    acq = modulated_strobe_acquire(zsp_mod, schedule, reps_per_block=1000)
    assert acq["I"].shape == (4000,), acq["I"].shape
    assert acq["gap_indices"] == [1000, 2000, 3000], acq["gap_indices"]
    assert np.array_equal((acq["modulation_reference"] > 0.5),
                          np.tile(np.concatenate([np.ones(1000), np.zeros(1000)]), 2).astype(bool)), "ref misaligned"
    assert acq["block_labels"] == schedule, acq["block_labels"]
    print("loopback modulated_strobe_acquire: OK")
```

- [ ] **Step 2: Add the `run_static_contrast` plumbing check** — append:

```python
    # --- Loopback: run_static_contrast plumbing ---
    from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.validate_ZeroSpanParity import run_static_contrast
    zsp_sc = ZeroSpanParity(soc=soc, soccfg=soccfg, cfg=dict(loopback_cfg), outerFolder=tmp_dir, prefix="loopback_sc")
    f0 = loopback_cfg["read_pulse_freq"]
    flist = np.linspace(f0 - 0.5, f0 + 0.5, 5)
    sc = run_static_contrast(zsp_sc, flist, qubit_gain_on=loopback_cfg["qubit_gain"], out_dir=tmp_dir)
    assert sc["contrast"].shape == (5,), sc["contrast"].shape
    assert np.all(np.isfinite(sc["Z_on"])) and np.all(np.isfinite(sc["Z_off"]))
    print("loopback run_static_contrast: OK")
```

- [ ] **Step 3: Run the loopback suite on hardware** (requires the RFSoC reachable at `192.168.1.7` + loopback cable)

Run: `python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments._loopback_check_ZeroSpanParity`
Expected: PASS — prints `loopback modulated_strobe_acquire: OK` and `loopback run_static_contrast: OK` along with the existing loopback "OK" lines.

> If hardware is unavailable when executing this plan, mark Task 15 blocked and proceed; it is the only hardware-gated task. All Tasks 1–14 are fully verified offline.

- [ ] **Step 4: Commit**

```bash
git add WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/_loopback_check_ZeroSpanParity.py
git commit -m "test(parity): loopback checks for modulated acquire + static contrast"
```

---

## Final verification

- [ ] **Run all offline test suites** and confirm every "OK" line prints:

```bash
python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity
python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils
python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mZeroSpanParity
python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.validate_ZeroSpanParity
```

Expected: each exits 0; new markers present — `dwell_time_statistics debounce`, `verify_modulation`, `contrast_from_sweeps`, `projected_histogram_snr`, `bin_size_sweep`, `threshold_stability`, `modulated_strobe_acquire`, and the four `validate_ZeroSpanParity ...` lines, plus all pre-existing OK lines.

- [ ] **Syntax-check the orchestrator:** `python -c "import ast; ast.parse(open(r'WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/CSTQ03_BFC.py').read())"`

---

## Spec coverage check (self-review)

| Spec section | Task |
|---|---|
| §2 `modulated_strobe_acquire` | Task 3 |
| §3.1 `verify_modulation` | Task 2 |
| §3.2 `projected_histogram_snr` (Δ-BIC) | Task 8 |
| §3.3 `bin_size_sweep` (no monotonic assert) | Task 9 |
| §3.4 `threshold_stability` | Task 10 |
| §3.5 `contrast_from_sweeps` (Z naming) | Task 5 |
| §3.6 dwell debounce | Task 1 |
| §4.1 `run_static_contrast` | Task 6 |
| §4.2 `run_contrast_vs_qubit_freq` (\|<Z>on−<Z>off\|) | Task 7 |
| §4.3 `run_modulation_check` (factor-of-2) | Task 4 |
| §4.4 `run_control_suite` (auto both branches + sign flip) | Task 12 |
| §4.5 `CrossRunComparison` + multi-metric stage 7 | Task 11 |
| §4.6 `build_evidence_report` (collate-only) | Task 13 |
| §4.7 sidecar contract (metadata + raw arrays) | Task 4 (`_stage_sidecar`), used by all |
| §5 orchestrator wiring | Task 14 |
| §6.1 offline tests | Tasks 1–13 (`__main__`) |
| §6.2 loopback | Task 15 |
| §6.3 live run order | documented; executed on hardware (out of plan scope) |

All spec requirements map to a task. Type/name consistency verified: `_stage_sidecar`, `classify_parity_trace`, `dwell_time_statistics(..., merge_short_segments, min_dwell_bins)`, `modulated_strobe_acquire`, and `set_qubit_gain` are used with identical signatures across tasks.
