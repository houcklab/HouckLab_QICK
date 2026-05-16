# Zero-Span Charge-Parity Measurement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the zero-span two-tone charge-parity-switching measurement designed in `docs/superpowers/specs/2026-05-16-bfc-charge-parity-zero-span-design.md`, covering v1 strobe acquisition, v2 decimated acquisition, the offline-analysis module, the per-device orchestrator skeleton for test_BTQ_BFC, and the loopback smoke test (spec §6.2). Physics validation (§6.3) is blocked on test_BTQ_BFC cooldown and is **not** part of this plan.

**Architecture:** Three device-agnostic files plus one device-specific orchestrator skeleton, all inside `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/`. New helpers added to existing `utils.py`. The acquisition file (`mZeroSpanParity.py`) dispatches between a strobe `AveragerProgram` (per-rep IQ via `prog.di_buf`/`prog.dq_buf`) and a decimated `AveragerProgram` (raw ADC waveform via `prog.acquire_decimated()`). The analysis file (`analyze_ZeroSpanParity.py`) is five pure functions plus a top-level `analyze_parity_run` driver, all testable on synthetic data via an `if __name__ == "__main__":` block (matches existing project test pattern — no `tests/` directory).

**Tech Stack:** Python 3, numpy, scipy, matplotlib, h5py, sklearn (KMeans), `qick` package (`AveragerProgram`, `acquire_decimated`), existing project helpers in `utils.py` and `CoreLib/Experiment.py`.

**Edit-scope rule:** Stay inside `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/`. The plan only touches files in that directory. If any task seems to require editing upward (MasterProject, CoreLib, shared helpers), stop and ask.

**Test commands used in this plan:**
- `python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity`
- `python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils`

Run from repo root (`C:\Users\ece-houck-j409\PycharmProjects\HouckLab_QICK`). The project does not use pytest; tests are plain `assert` statements inside `if __name__ == "__main__":` blocks.

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/utils.py` | MODIFY | Add `project_iq_onto_separator`, `pick_parity_drive_freq`, `chunked_acquire`, plus `__main__` test block. |
| `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/analyze_ZeroSpanParity.py` | CREATE | Offline analysis: classify, sliding-window rate, burst detection, dwell statistics, top-level driver, tests. |
| `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/mZeroSpanParity.py` | CREATE | QICK acquisition: strobe + decimated programs, ExperimentClass dispatcher, `_validate_cfg`. |
| `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/test_BTQ_BFC.py` | CREATE | Per-device orchestrator skeleton with parity block. Qubit_Parameters values are placeholders to be filled during device characterization. |

Existing files referenced (read-only):
- `WorkingProjects/QM_Team/qubit_measurements/Client_modules/CoreLib/Experiment.py` (`ExperimentClass`)
- `WorkingProjects/QM_Team/qubit_measurements/Client_modules/CoreLib/socProxy.py` (`makeProxy`)
- `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/mChargeDispersionQuasiCW.py` (closest existing experiment — reference, do not modify)
- `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/CSTQ02_BFC.py` (orchestrator pattern — reference, do not modify)
- `.venv/Lib/site-packages/qick/qick_asm.py` (`AveragerProgram`, `acquire_decimated`)

---

## Task 1: Add `project_iq_onto_separator` primitive to `utils.py`

**Why first:** The analysis module's apriori classifier needs to project (I, Q) onto the e-g axis defined by a single-shot calibration. The existing `classify_and_average_iq` does this internally; we extract the projection step into a reusable primitive without modifying the existing function. New code only — no risk to existing callers.

**Files:**
- Modify: `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/utils.py` (add new function, add `__main__` block)

- [ ] **Step 1: Add the function definition at the end of `utils.py`** (before the file ends, after `fit_rabi_cosine`).

```python


def project_iq_onto_separator(I, Q, separator):
    """
    Project (I, Q) sample arrays onto the ground -> excited axis defined by a
    single-shot calibration separator dict.

    Parameters
    ----------
    I, Q : array_like
        Sample arrays (1-D or any shape that ravels to 1-D). Must be same length.
    separator : dict
        Must contain keys "g_center" and "e_center", each a length-2 array-like
        (I, Q) coordinate. Keys "normal" and "midpoint" if present are recomputed
        for consistency.

    Returns
    -------
    scores : np.ndarray, shape (N,)
        Signed projection of each sample onto (e_center - g_center). Positive
        scores are closer to the excited centroid.
    binary_states : np.ndarray, shape (N,), dtype int
        1 where score > 0 (excited side), 0 otherwise.
    """
    g = np.asarray(separator["g_center"], dtype=float)
    e = np.asarray(separator["e_center"], dtype=float)
    if g.shape != (2,) or e.shape != (2,):
        raise ValueError(
            f"separator g_center and e_center must each be length-2, "
            f"got shapes {g.shape} and {e.shape}"
        )
    normal = e - g
    midpoint = 0.5 * (g + e)
    iq = np.column_stack([np.ravel(np.asarray(I, dtype=float)),
                          np.ravel(np.asarray(Q, dtype=float))])
    if iq.shape[0] == 0:
        return np.zeros(0, dtype=float), np.zeros(0, dtype=int)
    scores = (iq - midpoint) @ normal
    binary_states = (scores > 0).astype(int)
    return scores, binary_states
```

- [ ] **Step 2: Add a `__main__` test block at the very end of `utils.py`** (or extend it if one exists; the current file has none).

```python


if __name__ == "__main__":
    # Unit tests for the helpers added by the zero-span-parity plan.
    rng = np.random.default_rng(0)

    # --- project_iq_onto_separator ----------------------------------------
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
    assert bits.dtype == np.int64 or bits.dtype == np.int32

    # Empty input edge case
    scores0, bits0 = project_iq_onto_separator([], [], sep)
    assert scores0.shape == (0,)
    assert bits0.shape == (0,)

    # Bad separator shape raises
    try:
        project_iq_onto_separator([1.0], [1.0], {"g_center": [0, 0, 0], "e_center": [1, 1]})
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError on bad separator shape")

    print("utils.py project_iq_onto_separator: OK")
```

- [ ] **Step 3: Run the test**

```powershell
python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils
```

Expected output: `utils.py project_iq_onto_separator: OK` and exit code 0.

- [ ] **Step 4: Commit**

```powershell
git add WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/utils.py
git commit -m "Add project_iq_onto_separator helper to utils.py for parity classification"
```

---

## Task 2: Add `classify_parity_trace` to `analyze_ZeroSpanParity.py` (apriori path, TDD)

**Files:**
- Create: `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/analyze_ZeroSpanParity.py`

- [ ] **Step 1: Write the failing test by creating the file with only the test block**

```python
"""
Offline analysis for the zero-span charge-parity measurement.

See docs/superpowers/specs/2026-05-16-bfc-charge-parity-zero-span-design.md for the
canonical reference. Five pure functions plus a top-level driver:

  classify_parity_trace      Project (I,Q) -> parity bits via separator or KMeans
  sliding_window_switch_rate Switch rate vs time
  detect_bursts              Find anomalous high-rate intervals
  dwell_time_statistics      Per-state run-length statistics + exponential fits
  analyze_parity_run         Load saved .h5, run all of the above, save plots/sidecars

Tests live under the `if __name__ == "__main__":` block at the end of this file
and are run with:
    python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity
"""

import numpy as np


if __name__ == "__main__":
    rng = np.random.default_rng(1)

    # --- classify_parity_trace apriori path -----------------------------------
    g_center = np.array([0.0, 0.0])
    e_center = np.array([10.0, 0.0])
    sep = {"g_center": g_center, "e_center": e_center}
    I_g = rng.normal(g_center[0], 0.5, 1000); Q_g = rng.normal(g_center[1], 0.5, 1000)
    I_e = rng.normal(e_center[0], 0.5, 1000); Q_e = rng.normal(e_center[1], 0.5, 1000)
    I = np.concatenate([I_g, I_e]); Q = np.concatenate([Q_g, Q_e])
    labels_true = np.concatenate([np.zeros(1000, int), np.ones(1000, int)])

    out = classify_parity_trace(I, Q, separator=sep, method="apriori")
    assert "binary_states" in out and "scores" in out
    assert "method" in out and out["method"] == "apriori"
    assert "separator_used" in out
    accuracy = np.mean(out["binary_states"] == labels_true)
    assert accuracy > 0.99, f"apriori accuracy too low: {accuracy}"

    print("classify_parity_trace apriori: OK")
```

- [ ] **Step 2: Run the test to confirm it fails with NameError**

```powershell
python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity
```

Expected: `NameError: name 'classify_parity_trace' is not defined`.

- [ ] **Step 3: Implement `classify_parity_trace`** — insert just after the imports, before the `__main__` block.

```python
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils import (
    project_iq_onto_separator,
)


def classify_parity_trace(I, Q, separator=None, method="apriori"):
    """
    Project (I, Q) samples onto a 2-state axis and return binary parity labels.

    Parameters
    ----------
    I, Q : array_like
        1-D arrays of equal length, the raw in-phase and quadrature samples.
    separator : dict or None
        For method="apriori": must contain "g_center" and "e_center", each
        a length-2 array-like (I, Q) coordinate from a prior single-shot
        calibration. Ignored if method="kmeans".
    method : {"apriori", "kmeans"}
        "apriori": project onto (e_center - g_center), threshold at 0.
        "kmeans": fit KMeans(n_clusters=2) on (I, Q); label 0 = cluster with
        lower projection on the inter-cluster axis (deterministic remap).

    Returns
    -------
    dict with keys:
      binary_states  : int array (N,), values 0 or 1
      scores         : float array (N,), signed projection along separator axis
      separator_used : dict, the separator actually used (synthesized for kmeans)
      method         : "apriori" or "kmeans_fallback"
    """
    if method == "apriori":
        if separator is None:
            raise ValueError("method='apriori' requires a separator dict")
        scores, bits = project_iq_onto_separator(I, Q, separator)
        return {
            "binary_states": bits,
            "scores": scores,
            "separator_used": {
                "g_center": np.asarray(separator["g_center"], dtype=float),
                "e_center": np.asarray(separator["e_center"], dtype=float),
            },
            "method": "apriori",
        }
    elif method == "kmeans":
        # Implemented in Task 3
        raise NotImplementedError("kmeans method added in next task")
    else:
        raise ValueError(f"Unknown method: {method!r}")
```

- [ ] **Step 4: Run the test to verify it passes**

```powershell
python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity
```

Expected: `classify_parity_trace apriori: OK`.

- [ ] **Step 5: Commit**

```powershell
git add WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/analyze_ZeroSpanParity.py
git commit -m "Add analyze_ZeroSpanParity.classify_parity_trace apriori path"
```

---

## Task 3: Add kmeans fallback to `classify_parity_trace`

**Files:**
- Modify: `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/analyze_ZeroSpanParity.py`

- [ ] **Step 1: Append the kmeans test to the `__main__` block** (after the apriori test, before `print`).

```python
    # --- classify_parity_trace kmeans fallback --------------------------------
    out_km = classify_parity_trace(I, Q, separator=None, method="kmeans")
    assert out_km["method"] == "kmeans_fallback"
    assert "separator_used" in out_km
    accuracy_km = np.mean(out_km["binary_states"] == labels_true)
    assert accuracy_km > 0.99, f"kmeans accuracy too low: {accuracy_km}"

    # Deterministic remap: label 0 should be the lower-I cluster.
    label0_mean_I = np.mean(np.asarray(I)[out_km["binary_states"] == 0])
    label1_mean_I = np.mean(np.asarray(I)[out_km["binary_states"] == 1])
    assert label0_mean_I < label1_mean_I, "kmeans label remap not deterministic"

    print("classify_parity_trace kmeans: OK")
```

(Also update the existing `print("classify_parity_trace apriori: OK")` so both tests print before reaching a single summary line — or just leave both prints, they're fine.)

- [ ] **Step 2: Run the test to confirm it fails with `NotImplementedError`**

```powershell
python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity
```

Expected: `NotImplementedError: kmeans method added in next task`.

- [ ] **Step 3: Replace the kmeans branch in `classify_parity_trace`** — find the line `raise NotImplementedError("kmeans method added in next task")` and replace the entire `elif method == "kmeans":` block with:

```python
    elif method == "kmeans":
        from sklearn.cluster import KMeans
        I = np.ravel(np.asarray(I, dtype=float))
        Q = np.ravel(np.asarray(Q, dtype=float))
        if I.size == 0:
            return {
                "binary_states": np.zeros(0, dtype=int),
                "scores": np.zeros(0, dtype=float),
                "separator_used": {
                    "g_center": np.array([0.0, 0.0]),
                    "e_center": np.array([0.0, 0.0]),
                },
                "method": "kmeans_fallback",
            }
        iq = np.column_stack([I, Q])
        km = KMeans(n_clusters=2, n_init=10, random_state=0).fit(iq)
        centers = km.cluster_centers_  # shape (2, 2)

        # Define a separator dict consistent with apriori path:
        # label 0 = cluster with lower projection on (centers[1] - centers[0]) axis
        # before remap, then remap so label 0 has lower I-coordinate centroid.
        axis = centers[1] - centers[0]
        # Project both centers onto axis to confirm sign convention
        proj = centers @ axis
        # We want cluster with smaller I to be "0"; pick g/e accordingly.
        if centers[0, 0] <= centers[1, 0]:
            g_idx, e_idx = 0, 1
        else:
            g_idx, e_idx = 1, 0
        g_center = centers[g_idx]
        e_center = centers[e_idx]
        synth_sep = {"g_center": g_center, "e_center": e_center}
        scores, bits = project_iq_onto_separator(I, Q, synth_sep)
        return {
            "binary_states": bits,
            "scores": scores,
            "separator_used": synth_sep,
            "method": "kmeans_fallback",
        }
```

- [ ] **Step 4: Run the test to verify it passes**

```powershell
python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity
```

Expected: both `classify_parity_trace apriori: OK` and `classify_parity_trace kmeans: OK`.

- [ ] **Step 5: Commit**

```powershell
git add WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/analyze_ZeroSpanParity.py
git commit -m "Add kmeans fallback to classify_parity_trace"
```

---

## Task 4: Add `sliding_window_switch_rate`

**Files:**
- Modify: `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/analyze_ZeroSpanParity.py`

- [ ] **Step 1: Add the test at the end of `__main__`** (before any existing final `print` summary).

```python
    # --- sliding_window_switch_rate -------------------------------------------
    # Build a 100 000-sample trace at 20 us/sample (record length 2 s).
    # Inject a known switch probability per sample so we can check recovered rate.
    n_samp = 100_000
    sample_period_us = 20.0
    t_us = np.arange(n_samp) * sample_period_us
    p_switch = 0.001  # 0.1% per sample = 50 Hz at 20 us cadence
    flips = rng.random(n_samp) < p_switch
    bits = np.cumsum(flips) % 2

    out_rate = sliding_window_switch_rate(bits, t_us, window_us=100_000, step_us=100_000)
    # Non-overlapping 100 ms windows; expected rate ~ p_switch / (sample_period_us * 1e-6)
    expected_rate_Hz = p_switch / (sample_period_us * 1e-6)
    mean_rate = float(np.mean(out_rate["rate_Hz"]))
    rel_err = abs(mean_rate - expected_rate_Hz) / expected_rate_Hz
    assert rel_err < 0.1, f"sliding rate off: expected {expected_rate_Hz:.1f}, got {mean_rate:.1f}"

    # Gap indices should zero diffs across the gap.
    bits2 = np.array([0, 0, 1, 1, 0, 0])
    t2 = np.array([0.0, 10.0, 20.0, 30.0, 40.0, 50.0])
    out_gap = sliding_window_switch_rate(bits2, t2, window_us=60.0, step_us=60.0,
                                          gap_indices=[3])
    # Diff array would be [0, 1, 0, -1, 0]; with gap at index 3, position 2 -> 3
    # transition is zeroed. So switches in [0..50) = |0|+|1|+0+|−1 zeroed|+|0| = 1.
    assert out_gap["switches_per_window"][0] == 1, (
        f"expected 1 switch with gap, got {out_gap['switches_per_window']}"
    )

    print("sliding_window_switch_rate: OK")
```

- [ ] **Step 2: Run the test to confirm it fails with NameError**

```powershell
python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity
```

Expected: `NameError: name 'sliding_window_switch_rate' is not defined`.

- [ ] **Step 3: Implement the function** — append after `classify_parity_trace`.

```python
def sliding_window_switch_rate(binary_states, t_us, window_us, step_us=None,
                                gap_indices=None):
    """
    Sliding-window switch rate in Hz from a binary parity trace.

    Parameters
    ----------
    binary_states : array_like of int (0 or 1), shape (N,)
    t_us          : array_like of float, shape (N,), monotonically increasing
    window_us     : float, window duration
    step_us       : float or None, window stride; default = window_us // 2 (50% overlap)
    gap_indices   : list[int] or None, indices i where bits[i] is the first sample
                    after an acquisition-gap boundary; the diff bits[i] - bits[i-1]
                    is set to 0 so no spurious switch is counted across a gap.

    Returns
    -------
    dict with keys:
      window_t_us         : array (M,), center time of each window
      rate_Hz             : array (M,), switch rate per window
      switches_per_window : array (M,) of int
      window_us, step_us  : echoed scalars
    """
    bits = np.asarray(binary_states, dtype=int)
    t = np.asarray(t_us, dtype=float)
    if bits.shape != t.shape:
        raise ValueError(f"binary_states shape {bits.shape} != t_us shape {t.shape}")

    if step_us is None:
        step_us = window_us / 2.0

    if bits.size < 2:
        return {
            "window_t_us": np.zeros(0),
            "rate_Hz": np.zeros(0),
            "switches_per_window": np.zeros(0, dtype=int),
            "window_us": float(window_us),
            "step_us": float(step_us),
        }

    diffs = np.abs(np.diff(bits))  # length N-1, value 0 or 1
    if gap_indices:
        for gi in gap_indices:
            if 1 <= gi < bits.size:
                diffs[gi - 1] = 0

    # diffs[i] corresponds to a transition that occurred between t[i] and t[i+1];
    # assign that switch event the timestamp t[i+1].
    t_event = t[1:]

    # Build windows
    t_start = t[0]
    t_end = t[-1]
    if t_end - t_start < window_us:
        # Single window covering the whole trace
        starts = np.array([t_start])
    else:
        starts = np.arange(t_start, t_end - window_us + step_us, step_us)
    centers = starts + window_us / 2.0
    counts = np.zeros(starts.size, dtype=int)
    for i, s in enumerate(starts):
        mask = (t_event >= s) & (t_event < s + window_us)
        counts[i] = int(diffs[mask].sum())
    rate_Hz = counts / (window_us * 1e-6)

    return {
        "window_t_us": centers,
        "rate_Hz": rate_Hz,
        "switches_per_window": counts,
        "window_us": float(window_us),
        "step_us": float(step_us),
    }
```

- [ ] **Step 4: Run the test to verify it passes**

```powershell
python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity
```

Expected: all prior `OK` lines plus `sliding_window_switch_rate: OK`.

- [ ] **Step 5: Commit**

```powershell
git add WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/analyze_ZeroSpanParity.py
git commit -m "Add sliding_window_switch_rate to analyze_ZeroSpanParity"
```

---

## Task 5: Add `detect_bursts`

**Files:**
- Modify: `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/analyze_ZeroSpanParity.py`

- [ ] **Step 1: Add the test at the end of `__main__`.**

```python
    # --- detect_bursts --------------------------------------------------------
    # Baseline rate ~50 Hz over 100 windows; inject one window with 10 kHz.
    rate = np.full(100, 50.0)
    rate[50] = 10_000.0
    centers = np.arange(100) * 100_000.0  # 100 ms per window in us

    bursts = detect_bursts(rate, centers, baseline_rate=None, k_sigma=5,
                           min_duration_us=None)
    assert len(bursts) == 1, f"expected 1 burst, got {len(bursts)}"
    b = bursts[0]
    assert b["t_start_us"] <= centers[50] <= b["t_end_us"], (
        f"burst window does not contain injection: {b}"
    )
    assert b["peak_rate_Hz"] == 10_000.0
    assert b["baseline_rate_Hz"] == 50.0  # median is robust to one outlier

    # No bursts when everything is at baseline
    bursts0 = detect_bursts(np.full(100, 50.0), centers, k_sigma=5)
    assert bursts0 == [], f"expected no bursts, got {bursts0}"

    print("detect_bursts: OK")
```

- [ ] **Step 2: Run the test to confirm it fails with NameError**

```powershell
python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity
```

Expected: `NameError: name 'detect_bursts' is not defined`.

- [ ] **Step 3: Implement the function** — append after `sliding_window_switch_rate`.

```python
def detect_bursts(rate_Hz, window_t_us, baseline_rate=None, k_sigma=5,
                  min_duration_us=None):
    """
    Identify contiguous high-rate windows as bursts above a robust baseline.

    Parameters
    ----------
    rate_Hz       : array (M,) of switch rates per window (output of
                    sliding_window_switch_rate)
    window_t_us   : array (M,) of window center times
    baseline_rate : float or None; defaults to median(rate_Hz) (robust)
    k_sigma       : float; threshold = baseline + k_sigma * (1.4826 * MAD)
    min_duration_us : float or None; filter bursts shorter than this

    Returns
    -------
    list of dicts, one per burst, with keys:
      t_start_us, t_end_us, duration_us,
      peak_rate_Hz, mean_rate_Hz, integrated_excess_switches,
      baseline_rate_Hz, threshold_Hz
    """
    rate = np.asarray(rate_Hz, dtype=float)
    centers = np.asarray(window_t_us, dtype=float)
    if rate.shape != centers.shape:
        raise ValueError(f"rate {rate.shape} and centers {centers.shape} differ")
    if rate.size == 0:
        return []

    if baseline_rate is None:
        baseline_rate = float(np.median(rate))
    mad = float(np.median(np.abs(rate - baseline_rate)))
    sigma = 1.4826 * mad
    threshold = baseline_rate + k_sigma * sigma

    above = rate > threshold
    if not np.any(above):
        return []

    # Find contiguous runs of True
    edges = np.diff(above.astype(int))
    starts = list(np.where(edges == 1)[0] + 1)
    ends = list(np.where(edges == -1)[0] + 1)
    if above[0]:
        starts = [0] + starts
    if above[-1]:
        ends = ends + [above.size]

    # Window stride for duration calculation
    if centers.size >= 2:
        stride = float(np.median(np.diff(centers)))
    else:
        stride = 0.0

    bursts = []
    for s, e in zip(starts, ends):
        t_start = float(centers[s] - stride / 2.0)
        t_end = float(centers[e - 1] + stride / 2.0)
        duration = t_end - t_start
        if min_duration_us is not None and duration < min_duration_us:
            continue
        seg = rate[s:e]
        bursts.append({
            "t_start_us": t_start,
            "t_end_us": t_end,
            "duration_us": duration,
            "peak_rate_Hz": float(np.max(seg)),
            "mean_rate_Hz": float(np.mean(seg)),
            "integrated_excess_switches": float(
                np.sum((seg - baseline_rate)) * (stride * 1e-6)
            ),
            "baseline_rate_Hz": baseline_rate,
            "threshold_Hz": threshold,
        })
    return bursts
```

- [ ] **Step 4: Run the test**

```powershell
python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity
```

Expected: prior `OK` lines plus `detect_bursts: OK`.

- [ ] **Step 5: Commit**

```powershell
git add WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/analyze_ZeroSpanParity.py
git commit -m "Add detect_bursts to analyze_ZeroSpanParity"
```

---

## Task 6: Add `dwell_time_statistics`

**Files:**
- Modify: `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/analyze_ZeroSpanParity.py`

- [ ] **Step 1: Add the test at the end of `__main__`.**

```python
    # --- dwell_time_statistics ------------------------------------------------
    # Generate a Markov-style binary trace with known mean dwell times
    # tau_0 = 200 samples, tau_1 = 400 samples, at 20 us/sample.
    n = 200_000
    p01 = 1.0 / 200.0   # prob 0 -> 1 per sample
    p10 = 1.0 / 400.0   # prob 1 -> 0 per sample
    bits_mc = np.zeros(n, dtype=int)
    state = 0
    for i in range(n):
        bits_mc[i] = state
        if state == 0:
            if rng.random() < p01:
                state = 1
        else:
            if rng.random() < p10:
                state = 0
    t_mc = np.arange(n) * 20.0  # us
    stats = dwell_time_statistics(bits_mc, t_mc)
    # Expected mean dwell times in microseconds:
    expected_tau_0_us = 200 * 20.0
    expected_tau_1_us = 400 * 20.0
    assert abs(stats["mean_0"] - expected_tau_0_us) / expected_tau_0_us < 0.15, (
        f"mean_0 off: got {stats['mean_0']:.1f}, expected ~{expected_tau_0_us}"
    )
    assert abs(stats["mean_1"] - expected_tau_1_us) / expected_tau_1_us < 0.15, (
        f"mean_1 off: got {stats['mean_1']:.1f}, expected ~{expected_tau_1_us}"
    )
    assert stats["n_runs_0"] > 0 and stats["n_runs_1"] > 0

    # gap_indices splits runs across acquisition boundaries
    bits_short = np.array([0, 0, 0, 0, 0, 0])
    t_short = np.arange(6, dtype=float) * 10.0
    stats_gap = dwell_time_statistics(bits_short, t_short, gap_indices=[3])
    # Without gap: one run of length 6 in state 0; with gap: two runs of length 3
    assert stats_gap["n_runs_0"] == 2

    print("dwell_time_statistics: OK")
```

- [ ] **Step 2: Run the test to confirm it fails**

```powershell
python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity
```

Expected: `NameError: name 'dwell_time_statistics' is not defined`.

- [ ] **Step 3: Implement** — append after `detect_bursts`.

```python
def dwell_time_statistics(binary_states, t_us, gap_indices=None):
    """
    Lengths of contiguous runs in state 0 and state 1, in microseconds.

    Runs spanning a `gap_indices` boundary are split (not joined across it).

    Returns
    -------
    dict with keys:
      dwell_0_us, dwell_1_us : array of dwell durations (us)
      mean_0, mean_1         : float, mean dwell time per state (nan if no runs)
      n_runs_0, n_runs_1     : int, run counts
      exp_fit_0, exp_fit_1   : dict {"tau_us": float, "A": float}; nans if fit fails
    """
    bits = np.asarray(binary_states, dtype=int)
    t = np.asarray(t_us, dtype=float)
    n = bits.size
    if n == 0:
        return {
            "dwell_0_us": np.zeros(0), "dwell_1_us": np.zeros(0),
            "mean_0": float("nan"), "mean_1": float("nan"),
            "n_runs_0": 0, "n_runs_1": 0,
            "exp_fit_0": {"tau_us": float("nan"), "A": float("nan")},
            "exp_fit_1": {"tau_us": float("nan"), "A": float("nan")},
        }

    # Break trace into segments at gap_indices, run-length encode each segment.
    breakpoints = sorted(set([0, n] + list(gap_indices or [])))
    dwells_0, dwells_1 = [], []
    for a, b in zip(breakpoints[:-1], breakpoints[1:]):
        if b <= a:
            continue
        seg = bits[a:b]
        seg_t = t[a:b]
        # Run-length encode
        change_idx = np.where(np.diff(seg) != 0)[0] + 1
        run_starts = np.concatenate(([0], change_idx))
        run_ends = np.concatenate((change_idx, [seg.size]))
        for rs, re in zip(run_starts, run_ends):
            state = int(seg[rs])
            # Duration: time from first sample in run to first sample after run
            if re < seg.size:
                duration = float(seg_t[re] - seg_t[rs])
            else:
                # Last run in segment: extrapolate using sample period
                if seg.size >= 2:
                    sp = float(seg_t[1] - seg_t[0])
                else:
                    sp = 0.0
                duration = float(seg_t[re - 1] - seg_t[rs]) + sp
            if state == 0:
                dwells_0.append(duration)
            else:
                dwells_1.append(duration)

    dwells_0 = np.asarray(dwells_0, dtype=float)
    dwells_1 = np.asarray(dwells_1, dtype=float)

    def _fit_exp(dwells):
        if dwells.size < 5:
            return {"tau_us": float("nan"), "A": float("nan")}
        try:
            hist, edges = np.histogram(dwells, bins=min(30, max(5, dwells.size // 10)))
            centers_h = 0.5 * (edges[:-1] + edges[1:])
            mask = hist > 0
            if mask.sum() < 3:
                return {"tau_us": float("nan"), "A": float("nan")}
            x = centers_h[mask]
            y = np.log(hist[mask])
            slope, intercept = np.polyfit(x, y, 1)
            if slope >= 0:
                return {"tau_us": float("nan"), "A": float("nan")}
            tau = -1.0 / slope
            A = float(np.exp(intercept))
            return {"tau_us": float(tau), "A": A}
        except Exception:
            return {"tau_us": float("nan"), "A": float("nan")}

    return {
        "dwell_0_us": dwells_0,
        "dwell_1_us": dwells_1,
        "mean_0": float(np.mean(dwells_0)) if dwells_0.size else float("nan"),
        "mean_1": float(np.mean(dwells_1)) if dwells_1.size else float("nan"),
        "n_runs_0": int(dwells_0.size),
        "n_runs_1": int(dwells_1.size),
        "exp_fit_0": _fit_exp(dwells_0),
        "exp_fit_1": _fit_exp(dwells_1),
    }
```

- [ ] **Step 4: Run the test**

```powershell
python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity
```

Expected: prior `OK` lines plus `dwell_time_statistics: OK`.

- [ ] **Step 5: Commit**

```powershell
git add WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/analyze_ZeroSpanParity.py
git commit -m "Add dwell_time_statistics to analyze_ZeroSpanParity"
```

---

## Task 7: Add `analyze_parity_run` top-level driver and plotting

**Files:**
- Modify: `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/analyze_ZeroSpanParity.py`

This task wires the four primitives into a load-h5 → analyze → save-plots-and-sidecar driver. The test creates a synthetic `.h5`, runs the driver, and asserts plots + sidecar JSON exist.

- [ ] **Step 1: Add the test at the end of `__main__`.**

```python
    # --- analyze_parity_run end-to-end ----------------------------------------
    import os, tempfile, h5py, json

    with tempfile.TemporaryDirectory() as tmpdir:
        # Build a synthetic raw .h5 mimicking what ZeroSpanParity.save_data writes.
        n_syn = 50_000
        sample_period_us_syn = 20.0
        rng_syn = np.random.default_rng(7)
        # Two IQ clouds, parity-modulated
        labels_syn = (np.cumsum(rng_syn.random(n_syn) < 0.005) % 2).astype(int)
        I_syn = np.where(labels_syn == 1,
                         rng_syn.normal(10.0, 0.5, n_syn),
                         rng_syn.normal(0.0, 0.5, n_syn))
        Q_syn = rng_syn.normal(0.0, 0.5, n_syn)
        t_syn = np.arange(n_syn) * sample_period_us_syn

        h5_path = os.path.join(tmpdir, "ZeroSpanParity_synthetic.h5")
        with h5py.File(h5_path, "w") as f:
            f.create_dataset("I", data=I_syn)
            f.create_dataset("Q", data=Q_syn)
            f.create_dataset("t_us", data=t_syn)
            f.create_dataset("gap_indices", data=np.array([], dtype=int))
            f.attrs["sample_period_us"] = sample_period_us_syn
            f.attrs["mode"] = "strobe"

        sep_syn = {"g_center": np.array([0.0, 0.0]),
                   "e_center": np.array([10.0, 0.0])}
        results = analyze_parity_run(
            h5_path=h5_path,
            separator=sep_syn,
            window_us=100_000.0,
            k_sigma=5.0,
            save_plots=True,
            out_dir=tmpdir,
        )
        assert "n_bursts" in results
        assert "baseline_rate_Hz" in results
        assert "mean_dwell_0_us" in results and "mean_dwell_1_us" in results

        base = os.path.splitext(os.path.basename(h5_path))[0]
        for suffix in ["_iq_scatter.png", "_parity_vs_time.png",
                       "_switch_rate_vs_time.png", "_dwell_histograms.png"]:
            png = os.path.join(tmpdir, base + suffix)
            assert os.path.exists(png), f"missing plot: {png}"

        sidecar_json = os.path.join(tmpdir, base + "_analysis.json")
        sidecar_h5   = os.path.join(tmpdir, base + "_analysis.h5")
        assert os.path.exists(sidecar_json)
        assert os.path.exists(sidecar_h5)
        with open(sidecar_json) as f:
            sj = json.load(f)
        assert "baseline_rate_Hz" in sj

    print("analyze_parity_run: OK")
```

- [ ] **Step 2: Run the test to confirm it fails**

```powershell
python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity
```

Expected: `NameError: name 'analyze_parity_run' is not defined`.

- [ ] **Step 3: Implement the driver** — append after `dwell_time_statistics`. Also add `matplotlib`, `h5py`, `os`, `json` to the imports at the top of the file.

Update the top imports block (replace `import numpy as np` line) with:

```python
import os
import json
import numpy as np
import h5py
import matplotlib
matplotlib.use("Agg")  # non-interactive backend safe in headless runs
import matplotlib.pyplot as plt

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils import (
    project_iq_onto_separator,
)
```

Then append the driver:

```python
def _plot_iq_scatter(I, Q, bits, separator, out_path):
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(np.asarray(I)[bits == 0], np.asarray(Q)[bits == 0],
               s=1, alpha=0.3, label="state 0")
    ax.scatter(np.asarray(I)[bits == 1], np.asarray(Q)[bits == 1],
               s=1, alpha=0.3, label="state 1")
    g = np.asarray(separator["g_center"], dtype=float)
    e = np.asarray(separator["e_center"], dtype=float)
    ax.plot([g[0], e[0]], [g[1], e[1]], "k--", lw=1)
    ax.scatter([g[0], e[0]], [g[1], e[1]], c="k", marker="x", s=60, label="separator")
    ax.set_xlabel("I"); ax.set_ylabel("Q"); ax.legend(loc="best", markerscale=4)
    ax.set_title("Parity IQ scatter")
    fig.tight_layout(); fig.savefig(out_path, dpi=150); plt.close(fig)


def _plot_parity_vs_time(bits, t_us, out_path, max_pts=100_000):
    fig, ax = plt.subplots(figsize=(10, 3))
    n = bits.size
    if n > max_pts:
        # Downsample by histogram2d for speed
        time_bins = np.linspace(t_us[0], t_us[-1], max_pts)
        idx = np.clip(np.searchsorted(time_bins, t_us) - 1, 0, time_bins.size - 1)
        avg_state = np.bincount(idx, weights=bits.astype(float), minlength=time_bins.size)
        cnt = np.bincount(idx, minlength=time_bins.size).astype(float)
        avg_state[cnt > 0] /= cnt[cnt > 0]
        ax.plot(time_bins / 1e6, avg_state, lw=0.5)
        ax.set_ylabel("mean state (downsampled)")
    else:
        ax.step(t_us / 1e6, bits, where="post", lw=0.5)
        ax.set_ylabel("parity state")
    ax.set_xlabel("time (s)")
    ax.set_title("Parity vs time")
    fig.tight_layout(); fig.savefig(out_path, dpi=150); plt.close(fig)


def _plot_switch_rate(rate_out, bursts, out_path):
    fig, ax = plt.subplots(figsize=(10, 3))
    ax.plot(rate_out["window_t_us"] / 1e6, rate_out["rate_Hz"], lw=0.8)
    if bursts:
        baseline = bursts[0]["baseline_rate_Hz"]
        threshold = bursts[0]["threshold_Hz"]
        ax.axhline(baseline, color="gray", ls=":", label=f"baseline {baseline:.1f} Hz")
        ax.axhline(threshold, color="red", ls="--", label=f"threshold {threshold:.1f} Hz")
        for b in bursts:
            ax.axvspan(b["t_start_us"] / 1e6, b["t_end_us"] / 1e6,
                       color="red", alpha=0.15)
    ax.set_xlabel("time (s)"); ax.set_ylabel("switch rate (Hz)")
    ax.set_title("Sliding-window switch rate")
    ax.legend(loc="best")
    fig.tight_layout(); fig.savefig(out_path, dpi=150); plt.close(fig)


def _plot_dwell_histograms(stats, out_path):
    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(10, 4))
    for ax, dwells, fit, title in [
        (ax0, stats["dwell_0_us"], stats["exp_fit_0"], "state 0 dwells"),
        (ax1, stats["dwell_1_us"], stats["exp_fit_1"], "state 1 dwells"),
    ]:
        if dwells.size > 0:
            ax.hist(dwells, bins=30, log=True, alpha=0.7)
            if np.isfinite(fit["tau_us"]):
                xs = np.linspace(dwells.min(), dwells.max(), 200)
                ax.plot(xs, fit["A"] * np.exp(-xs / fit["tau_us"]), "r-",
                        label=f"tau={fit['tau_us']:.1f} us")
                ax.legend()
        ax.set_xlabel("dwell (us)")
        ax.set_title(title)
    fig.tight_layout(); fig.savefig(out_path, dpi=150); plt.close(fig)


def analyze_parity_run(h5_path, separator=None, window_us=1000.0, k_sigma=5.0,
                       classifier_method="apriori", step_us=None,
                       min_burst_duration_us=None, save_plots=True, out_dir=None):
    """
    Load a ZeroSpanParity raw .h5, classify into parity bits, compute switch rate,
    detect bursts, compute dwell statistics, save plots and a sidecar.

    Parameters
    ----------
    h5_path           : str, path to raw .h5 written by ZeroSpanParity.save_data
    separator         : dict or None; required for classifier_method="apriori"
    window_us         : float, sliding-window size
    k_sigma           : float, burst threshold
    classifier_method : "apriori" | "kmeans"
    step_us           : float or None, window stride
    min_burst_duration_us : float or None
    save_plots        : bool
    out_dir           : str or None; defaults to directory of h5_path

    Returns
    -------
    dict with scalar summary fields (matches sidecar JSON).
    """
    if out_dir is None:
        out_dir = os.path.dirname(h5_path) or "."
    base = os.path.splitext(os.path.basename(h5_path))[0]

    with h5py.File(h5_path, "r") as f:
        I = np.array(f["I"])
        Q = np.array(f["Q"])
        t_us = np.array(f["t_us"])
        gap_indices = list(np.array(f["gap_indices"])) if "gap_indices" in f else []
        sample_period_us = float(f.attrs.get("sample_period_us",
                                              (t_us[1] - t_us[0]) if t_us.size > 1 else 0.0))

    cls = classify_parity_trace(I, Q, separator=separator, method=classifier_method)
    bits = cls["binary_states"]
    sep_used = cls["separator_used"]

    rate_out = sliding_window_switch_rate(bits, t_us, window_us=window_us,
                                          step_us=step_us, gap_indices=gap_indices)
    bursts = detect_bursts(rate_out["rate_Hz"], rate_out["window_t_us"],
                           baseline_rate=None, k_sigma=k_sigma,
                           min_duration_us=min_burst_duration_us)
    stats = dwell_time_statistics(bits, t_us, gap_indices=gap_indices)

    if save_plots:
        _plot_iq_scatter(I, Q, bits, sep_used,
                          os.path.join(out_dir, base + "_iq_scatter.png"))
        _plot_parity_vs_time(bits, t_us,
                              os.path.join(out_dir, base + "_parity_vs_time.png"))
        _plot_switch_rate(rate_out, bursts,
                           os.path.join(out_dir, base + "_switch_rate_vs_time.png"))
        _plot_dwell_histograms(stats,
                                os.path.join(out_dir, base + "_dwell_histograms.png"))

    baseline_rate = (bursts[0]["baseline_rate_Hz"] if bursts
                     else float(np.median(rate_out["rate_Hz"])
                                if rate_out["rate_Hz"].size else 0.0))
    summary = {
        "h5_path": h5_path,
        "sample_period_us": sample_period_us,
        "n_samples": int(bits.size),
        "n_bursts": len(bursts),
        "baseline_rate_Hz": baseline_rate,
        "mean_dwell_0_us": stats["mean_0"],
        "mean_dwell_1_us": stats["mean_1"],
        "n_runs_0": stats["n_runs_0"],
        "n_runs_1": stats["n_runs_1"],
        "exp_fit_tau_0_us": stats["exp_fit_0"]["tau_us"],
        "exp_fit_tau_1_us": stats["exp_fit_1"]["tau_us"],
        "classifier_method": cls["method"],
    }

    # Write sidecars
    with open(os.path.join(out_dir, base + "_analysis.json"), "w") as f:
        json.dump({**summary,
                   "bursts": bursts,
                   "window_us": rate_out["window_us"],
                   "step_us": rate_out["step_us"]},
                  f, indent=2, default=lambda x: x.tolist()
                  if isinstance(x, np.ndarray) else float(x))
    with h5py.File(os.path.join(out_dir, base + "_analysis.h5"), "w") as f:
        f.create_dataset("binary_states", data=bits)
        f.create_dataset("scores", data=cls["scores"])
        f.create_dataset("window_t_us", data=rate_out["window_t_us"])
        f.create_dataset("rate_Hz", data=rate_out["rate_Hz"])
        f.create_dataset("dwell_0_us", data=stats["dwell_0_us"])
        f.create_dataset("dwell_1_us", data=stats["dwell_1_us"])
        for k, v in summary.items():
            try:
                f.attrs[k] = v
            except TypeError:
                f.attrs[k] = str(v)
    return summary
```

- [ ] **Step 4: Run the full test suite**

```powershell
python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity
```

Expected: all six `OK` lines (`classify_parity_trace apriori`, `classify_parity_trace kmeans`, `sliding_window_switch_rate`, `detect_bursts`, `dwell_time_statistics`, `analyze_parity_run`).

- [ ] **Step 5: Commit**

```powershell
git add WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/analyze_ZeroSpanParity.py
git commit -m "Add analyze_parity_run end-to-end driver with plotting and sidecars"
```

---

## Task 8: Add `pick_parity_drive_freq` to `utils.py`

**Files:**
- Modify: `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/utils.py`

- [ ] **Step 1: Add the test in the `__main__` block** (after the project_iq_onto_separator test).

```python
    # --- pick_parity_drive_freq ----------------------------------------------
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
    try:
        pick_parity_drive_freq(spec_data, which="middle")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for which='middle'")

    print("utils.py pick_parity_drive_freq: OK")
```

- [ ] **Step 2: Run the test to confirm it fails**

```powershell
python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils
```

Expected: `NameError: name 'pick_parity_drive_freq' is not defined`.

- [ ] **Step 3: Add the function in `utils.py`** — insert just after `project_iq_onto_separator`.

```python
def pick_parity_drive_freq(spec_data, which="lower"):
    """
    Pick one of the two parity-doublet peaks from a QubitSpecSliceFF-style
    spec_data dict, using the existing choose_two_tone_freqs_from_lorentz_or_peaks
    helper as the underlying peak-finder.

    Parameters
    ----------
    spec_data : dict (output of QubitSpecSliceFF.acquire or compatible)
    which     : "lower" or "higher" — which doublet peak to park at

    Returns
    -------
    dict:
      picked  : float, the chosen frequency (MHz)
      lower   : float, the lower-frequency doublet peak (MHz)
      higher  : float, the higher-frequency doublet peak (MHz)
      peak_sep_MHz : float or None, peak separation
      source  : str, provenance from choose_two_tone_freqs_from_lorentz_or_peaks
    """
    if which not in ("lower", "higher"):
        raise ValueError(f"which must be 'lower' or 'higher', got {which!r}")
    result = choose_two_tone_freqs_from_lorentz_or_peaks(spec_data)
    freqs = np.asarray(result["freqs"], dtype=float)
    if freqs.size < 2:
        raise RuntimeError(
            f"pick_parity_drive_freq: only {freqs.size} peak(s) found; "
            f"need 2 for parity doublet. Source={result['source']}"
        )
    lower = float(np.min(freqs[:2]))
    higher = float(np.max(freqs[:2]))
    picked = lower if which == "lower" else higher
    return {
        "picked": picked,
        "lower": lower,
        "higher": higher,
        "peak_sep_MHz": result.get("peak_sep"),
        "source": result.get("source"),
    }
```

- [ ] **Step 4: Run the test**

```powershell
python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils
```

Expected: prior `OK` line plus `utils.py pick_parity_drive_freq: OK`.

- [ ] **Step 5: Commit**

```powershell
git add WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/utils.py
git commit -m "Add pick_parity_drive_freq helper to utils.py"
```

---

## Task 9: Add `chunked_acquire` to `utils.py`

**Files:**
- Modify: `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/utils.py`

`chunked_acquire` runs `experiment.acquire()` N times back-to-back and stitches the per-chunk IQ/time arrays into one contiguous dataset, recording the chunk-boundary indices in `gap_indices` so analysis can avoid counting switches across them.

- [ ] **Step 1: Add the test in `__main__`.**

```python
    # --- chunked_acquire ------------------------------------------------------
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

    print("utils.py chunked_acquire: OK")
```

- [ ] **Step 2: Run the test to confirm it fails**

```powershell
python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils
```

Expected: `NameError: name 'chunked_acquire' is not defined`.

- [ ] **Step 3: Implement** — append after `pick_parity_drive_freq` in `utils.py`.

```python
def chunked_acquire(experiment, n_chunks, progress=False):
    """
    Run experiment.acquire() n_chunks times back-to-back and stitch results.

    Each acquire() must return a dict with keys "I", "Q", "t_us" (1-D arrays of
    equal length per chunk) and optionally "wall_clock_start" (str).

    The stitched time axis is monotonic: each subsequent chunk's t_us is shifted
    by (previous_chunk_t_us[-1] + sample_period). Inter-chunk Python+tProc gaps
    are NOT modeled in the stitched t_us; gap_indices marks where boundaries
    occur so the analysis module can avoid counting switches across them.

    Parameters
    ----------
    experiment : object with .acquire(progress=False) -> dict {I, Q, t_us, ...}
    n_chunks   : int >= 1
    progress   : bool

    Returns
    -------
    dict:
      I, Q, t_us               : concatenated arrays
      gap_indices              : list of ints, first index of each chunk after the
                                  first (length n_chunks - 1)
      chunk_wall_clock_starts  : list of str (or None) per chunk
      n_chunks                 : echoed int
    """
    if n_chunks < 1:
        raise ValueError(f"n_chunks must be >= 1, got {n_chunks}")
    I_parts, Q_parts, t_parts = [], [], []
    wall_clocks = []
    gap_indices = []
    cum_offset_us = 0.0
    cum_idx = 0
    iterator = range(n_chunks)
    if progress:
        try:
            from tqdm import tqdm
            iterator = tqdm(iterator, desc="chunked_acquire")
        except ImportError:
            pass
    for ci in iterator:
        out = experiment.acquire(progress=False)
        I_c = np.asarray(out["I"], dtype=float).ravel()
        Q_c = np.asarray(out["Q"], dtype=float).ravel()
        t_c = np.asarray(out["t_us"], dtype=float).ravel()
        if not (I_c.shape == Q_c.shape == t_c.shape):
            raise RuntimeError(
                f"chunk {ci} returned mismatched shapes: I={I_c.shape}, "
                f"Q={Q_c.shape}, t_us={t_c.shape}"
            )
        if ci > 0:
            # Stitch time: previous chunk's last + estimated sample period
            if t_parts and t_parts[-1].size >= 2:
                sp = float(t_parts[-1][1] - t_parts[-1][0])
            else:
                sp = 0.0
            cum_offset_us = t_parts[-1][-1] + sp
            gap_indices.append(cum_idx)
        t_shifted = t_c + cum_offset_us
        I_parts.append(I_c); Q_parts.append(Q_c); t_parts.append(t_shifted)
        wall_clocks.append(out.get("wall_clock_start", None))
        cum_idx += I_c.size

    return {
        "I": np.concatenate(I_parts),
        "Q": np.concatenate(Q_parts),
        "t_us": np.concatenate(t_parts),
        "gap_indices": gap_indices,
        "chunk_wall_clock_starts": wall_clocks,
        "n_chunks": int(n_chunks),
    }
```

- [ ] **Step 4: Run the test**

```powershell
python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils
```

Expected: all three `OK` lines, including `utils.py chunked_acquire: OK`.

- [ ] **Step 5: Commit**

```powershell
git add WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/utils.py
git commit -m "Add chunked_acquire helper to utils.py for long-record stitching"
```

---

## Task 10: Skeleton `mZeroSpanParity.py` with imports, `_validate_cfg`, and shared helper

**Files:**
- Create: `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/mZeroSpanParity.py`

This task is mostly scaffolding plus the validation function (spec §5.3). No QICK code yet — that comes in Tasks 11–13. The `_validate_cfg` function has its own tests against synthetic cfg dicts.

- [ ] **Step 1: Create the file with imports, module docstring, and the validation function.**

```python
"""
Zero-span two-tone parity-switching acquisition (QICK / RFSoC).

Canonical reference:
    docs/superpowers/specs/2026-05-16-bfc-charge-parity-zero-span-design.md

This module contains the device-agnostic acquisition code:
    ZeroSpanParityProgStrobe       (Path A, v1) per-rep IQ via di_buf/dq_buf
    ZeroSpanParityProgDecimated    (Path B, v2) raw decimated ADC waveform
    ZeroSpanParity                 ExperimentClass dispatching on cfg["mode"]
    _validate_cfg                  fail-fast configuration validation (spec §5.3)

cfg keys consumed by ZeroSpanParity (see spec §5.2 for the full contract):

  === required (all modes) ===
  mode               "strobe" | "decimated"
  start_src          "internal" | "external"
  res_ch, qubit_ch, ro_chs, nqz, qubit_nqz, mixer_freq
  read_pulse_freq    MHz, parking freq for readout tone
  parity_drive_freq  MHz, parking freq for qubit tone (one parity peak)
  qubit_gain, pulse_gain, res_phase
  adc_trig_offset    us
  read_length        us

  === required if mode=="strobe" ===
  sample_period_us   us, sample cadence
  reps_per_chunk     int, samples per acquire() call (chunking via chunked_acquire)

  === required if mode=="decimated" ===
  capture_length_us  us, length of one decimated capture
  soft_avgs          int, software-averaged rounds (1 = single-shot)

Validation errors include the spec rule number, the offending value, and the
violated bound.
"""

import numpy as np
from qick import AveragerProgram, RAveragerProgram

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import (
    ExperimentClass,
)


_STROBE_REQUIRED = (
    "sample_period_us", "reps_per_chunk",
)
_DECIMATED_REQUIRED = (
    "capture_length_us", "soft_avgs",
)
_SHARED_REQUIRED = (
    "mode", "start_src", "res_ch", "qubit_ch", "ro_chs", "nqz", "qubit_nqz",
    "mixer_freq", "read_pulse_freq", "parity_drive_freq",
    "qubit_gain", "pulse_gain", "res_phase",
    "adc_trig_offset", "read_length",
)


def _validate_cfg(cfg, soccfg):
    """
    Fail-fast validation of a ZeroSpanParity cfg dict (spec §5.3 rules 1-8).

    Raises RuntimeError on the first violation found. Each error message names
    the rule number, the offending value, and the violated bound.
    """
    # Presence checks first — easier to debug than indexing errors below.
    missing = [k for k in _SHARED_REQUIRED if k not in cfg]
    if missing:
        raise RuntimeError(
            f"[ZeroSpanParity cfg] missing required keys: {missing}"
        )
    mode = cfg["mode"]
    if mode not in ("strobe", "decimated"):
        raise RuntimeError(
            f"[ZeroSpanParity cfg] cfg['mode']={mode!r} must be 'strobe' or 'decimated'"
        )
    extra = _STROBE_REQUIRED if mode == "strobe" else _DECIMATED_REQUIRED
    missing_extra = [k for k in extra if k not in cfg]
    if missing_extra:
        raise RuntimeError(
            f"[ZeroSpanParity cfg] missing keys for mode={mode!r}: {missing_extra}"
        )

    # Rule 1: sample_period floor
    if mode == "strobe":
        sp = float(cfg["sample_period_us"])
        floor = float(cfg["adc_trig_offset"]) + float(cfg["read_length"]) + 1.0
        if sp < floor:
            raise RuntimeError(
                f"[ZeroSpanParity §5.3 rule 1] sample_period_us={sp} us is below "
                f"floor (adc_trig_offset + read_length + 1.0 = {floor:.3f} us). "
                f"Increase sample_period_us or shorten read_length."
            )

    # Rules 2 & 3: const-pulse 16-bit cycle cap
    # us2cycles depends on the channel; soccfg exposes us2cycles via soccfg.us2cycles
    if mode == "strobe":
        cyc_q = soccfg.us2cycles(cfg["sample_period_us"], gen_ch=cfg["qubit_ch"])
        cyc_r = soccfg.us2cycles(cfg["sample_period_us"], gen_ch=cfg["res_ch"])
        for label, cyc in [("qubit_ch", cyc_q), ("res_ch", cyc_r)]:
            if cyc > 65535:
                raise RuntimeError(
                    f"[ZeroSpanParity §5.3 rule 2] sample_period_us yields "
                    f"{cyc} cycles on {label} > 65535 cap. "
                    f"Reduce sample_period_us."
                )
    else:
        cyc_q = soccfg.us2cycles(cfg["capture_length_us"], gen_ch=cfg["qubit_ch"])
        cyc_r = soccfg.us2cycles(cfg["capture_length_us"], gen_ch=cfg["res_ch"])
        for label, cyc in [("qubit_ch", cyc_q), ("res_ch", cyc_r)]:
            if cyc > 65535:
                raise RuntimeError(
                    f"[ZeroSpanParity §5.3 rule 3] capture_length_us yields "
                    f"{cyc} cycles on {label} > 65535 cap. "
                    f"Reduce capture_length_us."
                )

    # Rules 4 & 5: avg_maxlen / buf_maxlen
    ro_ch = cfg["ro_chs"][0]
    ro_info = soccfg["readouts"][ro_ch]
    if mode == "strobe":
        avg_maxlen = int(ro_info["avg_maxlen"])
        reps = int(cfg["reps_per_chunk"])
        if reps > avg_maxlen:
            raise RuntimeError(
                f"[ZeroSpanParity §5.3 rule 4] reps_per_chunk={reps} > "
                f"avg_maxlen={avg_maxlen} for readout ch {ro_ch}. "
                f"Reduce reps_per_chunk (and increase n_chunks if longer record "
                f"is needed)."
            )
    else:
        buf_maxlen = int(ro_info["buf_maxlen"])
        decimated_fs_MHz = float(ro_info["f_output"])
        n_samples = int(round(float(cfg["capture_length_us"]) * decimated_fs_MHz))
        if n_samples > buf_maxlen:
            raise RuntimeError(
                f"[ZeroSpanParity §5.3 rule 5] capture_length_us={cfg['capture_length_us']} "
                f"us => {n_samples} decimated samples > buf_maxlen={buf_maxlen} "
                f"for readout ch {ro_ch} at {decimated_fs_MHz} MHz. "
                f"Reduce capture_length_us."
            )

    # Rule 8: parity_drive_freq within DAC range
    qch = cfg["qubit_ch"]
    gen_info = soccfg["gens"][qch] if "gens" in soccfg else None
    if gen_info is not None and "f_dds" in gen_info:
        f_max = float(gen_info["f_dds"])
        f_drive = float(cfg["parity_drive_freq"])
        if not (0.0 <= f_drive <= f_max):
            raise RuntimeError(
                f"[ZeroSpanParity §5.3 rule 8] parity_drive_freq={f_drive} MHz "
                f"outside qubit channel {qch} DDS range [0, {f_max}] MHz."
            )

    # Rules 6 & 7 are caller-level constraints (Recalibrate flags vs cached values).
    # The orchestrator enforces them before constructing cfg, so they are not
    # re-checked here.


if __name__ == "__main__":
    # Synthetic soccfg-like object for unit testing _validate_cfg without QICK hardware.
    class _FakeSocCfg:
        def __init__(self):
            self._d = {
                "readouts": {0: {"avg_maxlen": 16384, "buf_maxlen": 8192,
                                 "f_output": 1.0}},
                "gens": {0: {"f_dds": 6144.0}, 1: {"f_dds": 6144.0}},
            }
        def us2cycles(self, us, gen_ch=None):
            # Pretend 384 MHz clock on every channel.
            return int(round(us * 384.0))
        def __getitem__(self, k): return self._d[k]
        def __contains__(self, k): return k in self._d

    sc = _FakeSocCfg()
    base = {
        "mode": "strobe", "start_src": "internal",
        "res_ch": 0, "qubit_ch": 1, "ro_chs": [0],
        "nqz": 2, "qubit_nqz": 2, "mixer_freq": 0.0,
        "read_pulse_freq": 7000.0, "parity_drive_freq": 3050.0,
        "qubit_gain": 5000, "pulse_gain": 1000, "res_phase": 0,
        "adc_trig_offset": 0.5, "read_length": 5.0,
        "sample_period_us": 20.0, "reps_per_chunk": 1000,
    }

    # Valid cfg passes.
    _validate_cfg(base, sc)
    print("_validate_cfg valid strobe: OK")

    # Rule 1: sample_period too small
    bad = dict(base); bad["sample_period_us"] = 1.0
    try: _validate_cfg(bad, sc)
    except RuntimeError as ex: assert "rule 1" in str(ex), ex
    else: raise AssertionError("expected rule 1 to fire")

    # Rule 2: sample_period too long => cycles > 65535
    bad = dict(base); bad["sample_period_us"] = 500.0
    try: _validate_cfg(bad, sc)
    except RuntimeError as ex: assert "rule 2" in str(ex), ex
    else: raise AssertionError("expected rule 2 to fire")

    # Rule 4: reps_per_chunk too large
    bad = dict(base); bad["reps_per_chunk"] = 10**6
    try: _validate_cfg(bad, sc)
    except RuntimeError as ex: assert "rule 4" in str(ex), ex
    else: raise AssertionError("expected rule 4 to fire")

    # Rule 5: capture_length_us too long (decimated mode)
    dec_base = dict(base)
    dec_base.update({"mode": "decimated", "capture_length_us": 100.0,
                     "soft_avgs": 1})
    del dec_base["sample_period_us"]
    del dec_base["reps_per_chunk"]
    _validate_cfg(dec_base, sc)  # 100 us * 1 MHz = 100 samples < 8192
    bad = dict(dec_base); bad["capture_length_us"] = 20000.0  # 20000 samples > 8192
    try: _validate_cfg(bad, sc)
    except RuntimeError as ex: assert "rule 5" in str(ex), ex
    else: raise AssertionError("expected rule 5 to fire")

    # Rule 8: parity_drive_freq out of range
    bad = dict(base); bad["parity_drive_freq"] = 9000.0
    try: _validate_cfg(bad, sc)
    except RuntimeError as ex: assert "rule 8" in str(ex), ex
    else: raise AssertionError("expected rule 8 to fire")

    # Missing key
    bad = dict(base); del bad["qubit_gain"]
    try: _validate_cfg(bad, sc)
    except RuntimeError as ex: assert "missing required keys" in str(ex)
    else: raise AssertionError("expected missing-key error")

    print("_validate_cfg all rules: OK")
```

- [ ] **Step 2: Run the validation tests.**

```powershell
python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mZeroSpanParity
```

Expected: `_validate_cfg valid strobe: OK` and `_validate_cfg all rules: OK`.

- [ ] **Step 3: Commit**

```powershell
git add WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/mZeroSpanParity.py
git commit -m "Scaffold mZeroSpanParity with imports, docstring contract, and _validate_cfg"
```

---

## Task 11: Add `ZeroSpanParityProgStrobe` (Path A QICK program)

**Files:**
- Modify: `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/mZeroSpanParity.py`

QICK programs run on the RFSoC and cannot be unit-tested without hardware. We add the class with a clear docstring, and verify via the loopback smoke test in Task 14 (§6.2).

- [ ] **Step 1: Append the strobe program after `_validate_cfg` (and before the `__main__` block).**

```python
class ZeroSpanParityProgStrobe(AveragerProgram):
    """
    Path A: stroboscopic per-rep IQ acquisition for zero-span parity measurement.

    Both tones are held on for the full duration of each rep; reps run back-to-
    back with syncdelay=0 so the qubit drive is effectively CW from the qubit's
    perspective (apart from a small inter-rep tProc-overhead gap).

    Each rep contributes one integrated IQ point to prog.di_buf[ro_ch] /
    prog.dq_buf[ro_ch]. The ExperimentClass wrapper reshapes those into a time-
    resolved 1-D IQ trace with sample period = cfg["sample_period_us"].

    Required cfg keys: see module docstring.
    """

    def _setup_two_tones(self):
        cfg = self.cfg
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                          mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        for ch in cfg["ro_chs"]:
            self.declare_readout(
                ch=ch,
                length=self.us2cycles(cfg["read_length"]),
                freq=cfg["read_pulse_freq"],
                gen_ch=cfg["res_ch"],
            )
        f_res = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"],
                              ro_ch=cfg["ro_chs"][0])
        f_qub = self.freq2reg(cfg["parity_drive_freq"], gen_ch=cfg["qubit_ch"])
        return f_res, f_qub

    def initialize(self):
        cfg = self.cfg
        f_res, f_qub = self._setup_two_tones()
        period_cyc_q = self.us2cycles(cfg["sample_period_us"], gen_ch=cfg["qubit_ch"])
        period_cyc_r = self.us2cycles(cfg["sample_period_us"], gen_ch=cfg["res_ch"])

        self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=f_qub,
                                  phase=0, gain=cfg["qubit_gain"],
                                  length=period_cyc_q)
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res,
                                  phase=cfg["res_phase"], gain=cfg["pulse_gain"],
                                  length=period_cyc_r)
        self.synci(200)

    def body(self):
        self.pulse(ch=self.cfg["qubit_ch"], t=0)
        self.measure(
            pulse_ch=self.cfg["res_ch"],
            adcs=self.cfg["ro_chs"],
            adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
            wait=True,
            syncdelay=0,
        )
```

- [ ] **Step 2: Run the existing validation tests (still no QICK invocation, but the file must still load).**

```powershell
python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mZeroSpanParity
```

Expected: same `OK` output as Task 10 (the new class is defined but not exercised).

- [ ] **Step 3: Commit**

```powershell
git add WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/mZeroSpanParity.py
git commit -m "Add ZeroSpanParityProgStrobe (Path A) QICK program"
```

---

## Task 12: Add `ZeroSpanParityProgDecimated` (Path B QICK program)

**Files:**
- Modify: `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/mZeroSpanParity.py`

- [ ] **Step 1: Append after `ZeroSpanParityProgStrobe`.**

```python
class ZeroSpanParityProgDecimated(AveragerProgram):
    """
    Path B: decimated raw-ADC waveform acquisition for zero-span parity.

    Both tones held on for the full capture window; ADC streams decimated samples
    for the entire window. ExperimentClass wrapper calls prog.acquire_decimated()
    instead of prog.acquire() to extract the (length, 2) IQ array.

    Sample period = 1 / soccfg['readouts'][ro_ch]['f_output'] (us).
    Total length = capture_length_us * f_output_MHz samples, capped by buf_maxlen.
    """

    def _setup_two_tones(self):
        # Identical to strobe — could be hoisted to a mixin, but the spec calls
        # for both classes to be self-contained for clarity. Duplication is
        # bounded (~12 lines) and changes to one usually require revisiting both.
        cfg = self.cfg
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                          mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        for ch in cfg["ro_chs"]:
            self.declare_readout(
                ch=ch,
                length=self.us2cycles(cfg["read_length"]),
                freq=cfg["read_pulse_freq"],
                gen_ch=cfg["res_ch"],
            )
        f_res = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"],
                              ro_ch=cfg["ro_chs"][0])
        f_qub = self.freq2reg(cfg["parity_drive_freq"], gen_ch=cfg["qubit_ch"])
        return f_res, f_qub

    def initialize(self):
        cfg = self.cfg
        f_res, f_qub = self._setup_two_tones()
        capture_cyc_q = self.us2cycles(cfg["capture_length_us"], gen_ch=cfg["qubit_ch"])
        capture_cyc_r = self.us2cycles(cfg["capture_length_us"], gen_ch=cfg["res_ch"])

        self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=f_qub,
                                  phase=0, gain=cfg["qubit_gain"],
                                  length=capture_cyc_q)
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res,
                                  phase=cfg["res_phase"], gain=cfg["pulse_gain"],
                                  length=capture_cyc_r)
        self.synci(200)

    def body(self):
        self.pulse(ch=self.cfg["qubit_ch"], t=0)
        self.measure(
            pulse_ch=self.cfg["res_ch"],
            adcs=self.cfg["ro_chs"],
            adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
            wait=True,
            syncdelay=0,
        )
```

- [ ] **Step 2: Run the file to make sure it still loads and the validation tests still pass.**

```powershell
python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mZeroSpanParity
```

Expected: same `OK` output.

- [ ] **Step 3: Commit**

```powershell
git add WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/mZeroSpanParity.py
git commit -m "Add ZeroSpanParityProgDecimated (Path B) QICK program"
```

---

## Task 13: Add `ZeroSpanParity` ExperimentClass dispatcher

**Files:**
- Modify: `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/mZeroSpanParity.py`

- [ ] **Step 1: Append after `ZeroSpanParityProgDecimated`.**

```python
class ZeroSpanParity(ExperimentClass):
    """
    Dispatcher ExperimentClass for the zero-span parity measurement.

    cfg["mode"] selects between strobe (Path A) and decimated (Path B). See
    module docstring + spec §5 for the full configuration contract.

    Saves data via the standard ExperimentClass HDF5 + JSON pattern:
      .h5  : datasets I, Q, t_us, gap_indices; attrs sample_period_us, mode, etc.
      .json: cfg dict (via save_config)
      .png : optional, written by display() if called
    """

    def __init__(self, soc=None, soccfg=None, path="", outerFolder="",
                 prefix="data", cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, cfg=cfg, config_file=config_file,
                         progress=progress)
        _validate_cfg(self.cfg, self.soccfg)
        mode = self.cfg["mode"]
        # AveragerProgram.__init__ reads cfg["reps"] during make_program() —
        # we must set it BEFORE constructing the program. For strobe mode,
        # reps_per_chunk drives the loop; for decimated mode, reps=1 and the
        # whole capture is one shot (averaged in software via soft_avgs).
        if mode == "strobe":
            self.cfg["reps"] = int(self.cfg["reps_per_chunk"])
            self.prog = ZeroSpanParityProgStrobe(self.soccfg, self.cfg)
        elif mode == "decimated":
            self.cfg["reps"] = 1
            self.prog = ZeroSpanParityProgDecimated(self.soccfg, self.cfg)
        else:
            # _validate_cfg already raised, but keep defensive check.
            raise ValueError(f"Unknown mode: {mode!r}")

    def acquire(self, progress=False, **kwargs):
        mode = self.cfg["mode"]
        if mode == "strobe":
            return self._acquire_strobe(progress=progress)
        if mode == "decimated":
            return self._acquire_decimated(progress=progress)
        raise ValueError(f"Unknown mode: {mode!r}")

    def _acquire_strobe(self, progress=False):
        import datetime
        cfg = self.cfg
        wall_clock_start = datetime.datetime.now().isoformat()
        # cfg["reps"] was already set to reps_per_chunk in __init__ before
        # AveragerProgram.make_program() ran. No further mutation needed here.
        prog = self.prog
        # AveragerProgram.acquire returns (avg_di, avg_dq) along with filling
        # prog.di_buf/prog.dq_buf with the raw per-rep stream.
        prog.acquire(
            self.soc,
            load_pulses=True,
            start_src=cfg["start_src"],
            progress=progress,
            readouts_per_experiment=1,
            save_experiments=None,
        )
        ro_ch = cfg["ro_chs"][0]
        I = np.asarray(prog.di_buf[ro_ch], dtype=float).ravel()
        Q = np.asarray(prog.dq_buf[ro_ch], dtype=float).ravel()
        sp = float(cfg["sample_period_us"])
        t_us = np.arange(I.size, dtype=float) * sp
        data = {
            "I": I, "Q": Q, "t_us": t_us,
            "gap_indices": np.array([], dtype=int),
            "wall_clock_start": wall_clock_start,
            "sample_period_us": sp,
            "mode": "strobe",
        }
        self.data = {"data": data}
        return data

    def _acquire_decimated(self, progress=False):
        import datetime
        cfg = self.cfg
        wall_clock_start = datetime.datetime.now().isoformat()
        # cfg["reps"] was already set to 1 in __init__ for decimated mode.
        prog = self.prog
        dec = prog.acquire_decimated(
            self.soc,
            soft_avgs=int(cfg.get("soft_avgs", 1)),
            load_pulses=True,
            start_src=cfg["start_src"],
            progress=progress,
        )
        # acquire_decimated returns a list with one (length, 2) array per ro_ch.
        arr = np.asarray(dec[0])
        if arr.ndim == 2 and arr.shape[1] == 2:
            I = arr[:, 0]; Q = arr[:, 1]
        elif arr.ndim == 3:
            # multi-rep/multi-read shape (n_reps, length, 2) — flatten to length
            I = arr.reshape(-1, 2)[:, 0]
            Q = arr.reshape(-1, 2)[:, 1]
        else:
            raise RuntimeError(f"unexpected acquire_decimated shape: {arr.shape}")
        ro_ch = cfg["ro_chs"][0]
        decimated_fs_MHz = float(self.soccfg["readouts"][ro_ch]["f_output"])
        sp = 1.0 / decimated_fs_MHz  # us per decimated sample
        t_us = np.arange(I.size, dtype=float) * sp
        data = {
            "I": I, "Q": Q, "t_us": t_us,
            "gap_indices": np.array([], dtype=int),
            "wall_clock_start": wall_clock_start,
            "sample_period_us": sp,
            "decimated_fs_MHz": decimated_fs_MHz,
            "mode": "decimated",
        }
        self.data = {"data": data}
        return data

    def save_data(self, data=None):
        """Write IQ trace + metadata to self.fname (.h5)."""
        import h5py
        if data is None:
            data = self.data["data"] if isinstance(self.data, dict) and "data" in self.data else self.data
        with h5py.File(self.fname, "w") as f:
            f.create_dataset("I", data=np.asarray(data["I"]))
            f.create_dataset("Q", data=np.asarray(data["Q"]))
            f.create_dataset("t_us", data=np.asarray(data["t_us"]))
            f.create_dataset("gap_indices",
                             data=np.asarray(data.get("gap_indices", []), dtype=int))
            for k in ("wall_clock_start", "sample_period_us", "mode",
                      "decimated_fs_MHz"):
                if k in data:
                    try:
                        f.attrs[k] = data[k]
                    except TypeError:
                        f.attrs[k] = str(data[k])

    def display(self, data=None, plotDisp=False, **kwargs):
        """No-op for live display; analysis module generates plots from the .h5."""
        return None
```

- [ ] **Step 2: Run the validation tests one more time.**

```powershell
python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mZeroSpanParity
```

Expected: same `OK` output as Task 10.

- [ ] **Step 3: Commit**

```powershell
git add WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/mZeroSpanParity.py
git commit -m "Add ZeroSpanParity ExperimentClass dispatcher"
```

---

## Task 14: Create `test_BTQ_BFC.py` orchestrator skeleton

**Files:**
- Create: `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/test_BTQ_BFC.py`

This is the per-device orchestrator skeleton. It mirrors the structural patterns of `CSTQ02_BFC.py` (imports, makeProxy, yoko, Qubit_Parameters, flag-driven main block) plus the new zero-span parity block. Qubit_Parameters values are placeholders to be filled in once test_BTQ_BFC is characterized. The script does **not** auto-run on import; the user toggles flags and runs explicitly. Module docstring carries the §5.5 condensed configuration contract.

- [ ] **Step 1: Create the file with the full skeleton.**

```python
"""
test_BTQ_BFC.py — Per-device orchestrator for the test_BTQ_BFC device.

Patterned after CSTQ02_BFC.py. Built once the test_BTQ_BFC chip is mounted;
Qubit_Parameters values are placeholders until device characterization fills
them in.

Workflow (set the boolean flags below and run this file):
  1. Optional transmission / spec calibration         (RunTransmissionSweep, Run2ToneSpec)
  2. **Coherence-benchmark block** (T1, T2R, T2E)     (RunT1, RunT2R, RunT2E)
       Standard step on every new device; see memory feedback_coherence_benchmark.md
  3. Optional single-shot readout calibration         (RunSingleShot)
  4. Zero-span parity measurement                     (RunZeroSpanParity)

────────────────────────────────────────────────────────────────────────────────
ZERO-SPAN PARITY — PER-RUN PARAMETERS
────────────────────────────────────────────────────────────────────────────────
Always required:
  Qubit_Target              int 1-N       row of Qubit_Parameters
  RunMode                   "strobe"|"decimated"   Path A (v1) | Path B (v2)
  StartSrc                  "internal"|"external"  spontaneous | triggered
  RecalibrateParityFreqs    bool           run narrow QubitSpecSliceFF first
  RecalibrateSeparator      bool           run single-shot pi-pulse calib
  ParityFreqs_Cached["which_to_park"]      "lower"|"higher"

Required if RecalibrateParityFreqs=False:
  ParityFreqs_Cached["lower_peak_MHz" | "higher_peak_MHz"]

Required if RecalibrateSeparator=False:
  Separator_Cached["g_center","e_center","normal","midpoint"]  np.ndarray(2,)

Strobe-mode (Path A):  sample_period_us, reps_per_chunk, n_chunks,
                       read_length, adc_trig_offset
Decimated-mode (Path B): capture_length_us, soft_avgs, n_captures,
                       read_length, adc_trig_offset

Drive: qubit_gain, pulse_gain, res_phase
Analysis: classifier_method, window_us, k_sigma,
          min_burst_duration_us, save_plots

Hard constraints (validated at start — fail-fast):
  sample_period_us >= adc_trig_offset + read_length + 1.0
  us2cycles(sample_period_us or capture_length_us) <= 65535
  reps_per_chunk   <= soccfg['readouts'][ro_ch]['avg_maxlen']
  capture samples  <= soccfg['readouts'][ro_ch]['buf_maxlen']
  Cached fields must be non-None when their Recalibrate flag is False.

Canonical full reference:
  docs/superpowers/specs/2026-05-16-bfc-charge-parity-zero-span-design.md §5
"""

import os
import numpy as np
import pyvisa

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.socProxy import makeProxy
# Calibration / yoko helpers
# from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Calib.initialize4Q import *
# (uncomment once initialize4Q.py is configured for the test_BTQ_BFC setup)

# Existing experiments — copy in additional imports as device characterization progresses.
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mTransmissionFF import CavitySpecFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSpecSliceFF import QubitSpecSliceFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT1FF import T1FF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT2R import T2R
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT2EFF import T2EMUX
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSingleShotProgramFFMUX import SingleShotProgramFFMUX

# New zero-span parity modules
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mZeroSpanParity import ZeroSpanParity
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity import analyze_parity_run
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils import (
    pick_parity_drive_freq, chunked_acquire, ramp_to,
)


# ============================================================================
# Hardware setup
# ============================================================================
soc, soccfg = makeProxy()

# yoko (mirrors CSTQ02_BFC.py)
start_voltage = 0.000
rm = pyvisa.ResourceManager()
yoko = rm.open_resource('GPIB1::9::INSTR')
yoko.write(":SOUR:FUNC VOLT")
yoko.write(":OUTP ON")
ramp_to(yoko, start_voltage)


# ============================================================================
# Qubit_Parameters — TODO: fill in values once test_BTQ_BFC is characterized
# ============================================================================
Qubit_Parameters = {
    '1': {
        'Readout': {'Frequency': None, 'Gain': None},
        'Qubit':   {'Frequency': None, 'Gain': None, 'pi2_Gain': None,
                    'sigma': None, 'flattop_length': None},
        'outerfoldername': "V:/t1Team/Data/TBD_test_BTQ_BFC_cooldown/test_BTQ_BFC/RFSOC/Q1//",
    },
    # add rows '2', '3', ... as the device has more qubits
}


# ============================================================================
# Run flags — toggle these between runs
# ============================================================================
Qubit_Target = '1'

RunTransmissionSweep   = False    # cavity spec
Run2ToneSpec           = False    # qubit spec
RunT1                  = False    # coherence benchmark
RunT2R                 = False    # coherence benchmark
RunT2E                 = False    # coherence benchmark
RunSingleShot          = False    # readout calibration
RunZeroSpanParity      = False    # this spec


# ============================================================================
# Zero-span parity block — see module docstring for parameter meanings
# ============================================================================

# --- Calibration cache (filled by recalibration or set manually) -------------
ParityFreqs_Cached = {
    "lower_peak_MHz":  None,
    "higher_peak_MHz": None,
    "which_to_park":   "lower",
}
Separator_Cached = {
    "g_center": None, "e_center": None, "normal": None, "midpoint": None,
}

# --- Recalibration toggles ---------------------------------------------------
RecalibrateParityFreqs = True
RecalibrateSeparator   = True

# --- Acquisition mode --------------------------------------------------------
RunMode  = "strobe"          # "strobe" | "decimated"
StartSrc = "internal"        # "internal" | "external"

# --- Strobe-mode params (Path A) ---------------------------------------------
# sample_period_us : temporal resolution; floor = adc_trig_offset + read_length + 1.0 us
# reps_per_chunk   : capped at runtime by soccfg['readouts'][ro_ch]['avg_maxlen']
# n_chunks         : total record (s) = reps_per_chunk*n_chunks*sample_period_us*1e-6
StrobeParams = {
    "sample_period_us": 20.0,
    "reps_per_chunk":   50000,
    "n_chunks":         12,
    "read_length":      5.0,
    "adc_trig_offset":  0.488,
}

# --- Decimated-mode params (Path B) ------------------------------------------
# capture_length_us : capped at runtime by buf_maxlen / decimated_fs
# soft_avgs         : 1 = burst-resolved single shot; >1 = software-averaged
# n_captures        : outer loop, useful for triggered campaigns
DecimatedParams = {
    "capture_length_us": 1000.0,
    "soft_avgs":         1,
    "n_captures":        1,
    "read_length":       1000.0,
    "adc_trig_offset":   0.488,
}

# --- Drive parameters --------------------------------------------------------
def _drive_params_for(qt):
    return {
        "qubit_gain": Qubit_Parameters[qt]["Qubit"]["Gain"],
        "pulse_gain": Qubit_Parameters[qt]["Readout"]["Gain"],
        "res_phase":  0,
    }

# --- Analysis params ---------------------------------------------------------
AnalysisParams = {
    "classifier_method":       "apriori",
    "window_us":               1000.0,
    "k_sigma":                 5.0,
    "min_burst_duration_us":   None,
    "save_plots":              True,
}


# ============================================================================
# Execution
# ============================================================================
if RunZeroSpanParity:
    outerFolder = Qubit_Parameters[Qubit_Target]['outerfoldername'] + "ZeroSpanParity/"
    os.makedirs(outerFolder, exist_ok=True)

    # ---- Step 1: optional parity-freq pre-calibration -----------------------
    if RecalibrateParityFreqs:
        # TODO: build spec_cfg from BaseConfig + Qubit_Parameters[Qubit_Target]
        # once initialize4Q.py is configured for test_BTQ_BFC. The block below
        # is the canonical pattern — fill in the cfg dict.
        spec_cfg = {}  # FILL IN — see QubitSpecSliceFF expected keys
        raise NotImplementedError(
            "Implement spec_cfg construction once test_BTQ_BFC is characterized "
            "(see CSTQ02_BFC.py Run2ToneSpec block for the pattern)."
        )
        spec_exp  = QubitSpecSliceFF(soc=soc, soccfg=soccfg,
                                      path="ParityRecal_Spec",
                                      outerFolder=outerFolder, cfg=spec_cfg)
        spec_data = spec_exp.acquire(progress=True)
        spec_exp.display(spec_data, plotDisp=False)
        spec_exp.save_data(spec_data); spec_exp.save_config()
        chosen = pick_parity_drive_freq(spec_data,
                                         which=ParityFreqs_Cached["which_to_park"])
        ParityFreqs_Cached["lower_peak_MHz"]  = chosen["lower"]
        ParityFreqs_Cached["higher_peak_MHz"] = chosen["higher"]
        parity_drive_freq_MHz = chosen["picked"]
    else:
        which = ParityFreqs_Cached["which_to_park"]
        parity_drive_freq_MHz = (ParityFreqs_Cached["lower_peak_MHz"]
                                 if which == "lower"
                                 else ParityFreqs_Cached["higher_peak_MHz"])
        if parity_drive_freq_MHz is None:
            raise RuntimeError(
                "No cached parity freq and RecalibrateParityFreqs=False. "
                "Either set ParityFreqs_Cached or set RecalibrateParityFreqs=True."
            )

    # ---- Step 2: optional g/e separator pre-calibration ---------------------
    if RecalibrateSeparator:
        # TODO: implement single-shot calibration call once SingleShotProgramFFMUX
        # cfg is set for test_BTQ_BFC. See CSTQ02_BFC.py
        # get_apriori_separator_from_singleshot for the canonical pattern.
        raise NotImplementedError(
            "Implement single-shot separator calibration once test_BTQ_BFC is "
            "characterized (see CSTQ02_BFC.py get_apriori_separator_from_singleshot)."
        )
    else:
        if AnalysisParams["classifier_method"] == "apriori":
            for k in ("g_center", "e_center", "normal", "midpoint"):
                if Separator_Cached[k] is None:
                    raise RuntimeError(
                        f"Separator_Cached['{k}'] is None and classifier_method "
                        f"is 'apriori'. Either populate Separator_Cached or set "
                        f"RecalibrateSeparator=True or classifier_method='kmeans'."
                    )

    # ---- Step 3: build the ZeroSpanParity cfg -------------------------------
    drive = _drive_params_for(Qubit_Target)
    mode_params = StrobeParams if RunMode == "strobe" else DecimatedParams
    zsp_cfg = {
        # Channel routing (TODO: source from BaseConfig once initialize4Q is set up)
        "res_ch":     0,
        "qubit_ch":   1,
        "ro_chs":     [0],
        "nqz":        2,
        "qubit_nqz":  2,
        "mixer_freq": 0.0,
        # Frequencies
        "read_pulse_freq":   Qubit_Parameters[Qubit_Target]["Readout"]["Frequency"],
        "parity_drive_freq": parity_drive_freq_MHz,
        # Drive
        **drive,
        # Mode + start
        "mode":      RunMode,
        "start_src": StartSrc,
        # Mode-specific
        **mode_params,
    }

    # ---- Step 4: run acquisition --------------------------------------------
    exp = ZeroSpanParity(soc=soc, soccfg=soccfg,
                         path="ZeroSpanParity",
                         outerFolder=outerFolder, cfg=zsp_cfg)
    if RunMode == "strobe" and StrobeParams["n_chunks"] > 1:
        data = chunked_acquire(exp, n_chunks=StrobeParams["n_chunks"], progress=True)
        # When stitched, replace exp.data so save_data writes the stitched arrays.
        exp.data = {"data": data}
    else:
        data = exp.acquire(progress=True)

    exp.save_data(); exp.save_config()

    # ---- Step 5: offline analysis -------------------------------------------
    separator = (Separator_Cached
                 if AnalysisParams["classifier_method"] == "apriori" else None)
    analyze_parity_run(
        h5_path=exp.fname,
        separator=separator,
        window_us=AnalysisParams["window_us"],
        k_sigma=AnalysisParams["k_sigma"],
        classifier_method=AnalysisParams["classifier_method"],
        min_burst_duration_us=AnalysisParams["min_burst_duration_us"],
        save_plots=AnalysisParams["save_plots"],
        out_dir=os.path.dirname(exp.fname),
    )

    print(f"ZeroSpanParity complete. Data: {exp.fname}")
```

- [ ] **Step 2: Import-check the file**

```powershell
python -c "import importlib; importlib.import_module('WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.test_BTQ_BFC')"
```

Expected: the module imports without raising. Because `RunZeroSpanParity = False` by default, no execution path that requires hardware/calibration is triggered. (The `makeProxy()` and pyvisa calls at the top WILL run — if no QICK proxy or GPIB is reachable on the import machine, expect a connection error there; that's a runtime concern, not a syntax error.)

If you only want to check syntax without hitting hardware, use:

```powershell
python -c "import ast; ast.parse(open(r'WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/test_BTQ_BFC.py').read()); print('syntax OK')"
```

Expected: `syntax OK`.

- [ ] **Step 3: Commit**

```powershell
git add WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/test_BTQ_BFC.py
git commit -m "Add test_BTQ_BFC.py orchestrator skeleton with zero-span parity block"
```

---

## Task 15: Loopback smoke test (spec §6.2)

**Files:**
- Use: `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/mZeroSpanParity.py` (already built)
- Use: `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/test_BTQ_BFC.py` (or a one-off script)
- Create (if needed): `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/_loopback_check_ZeroSpanParity.py` — a throwaway runner.

This task requires the RFSoC reachable at the configured Pyro4 endpoint and a DAC→ADC loopback cable installed (same setup used by `Calibrate_loopback.py`). It runs §6.2 of the spec.

⚠️ **Hardware-dependent.** If the RFSoC is not currently available, skip this task and resume when hardware is back. The acceptance criterion for this plan does NOT require Task 15 to pass — Tasks 1–14 give a complete, offline-validated implementation; Task 15 graduates the code to "loopback-validated".

- [ ] **Step 1: Create the runner**

`WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/_loopback_check_ZeroSpanParity.py`:

```python
"""
Loopback smoke test for ZeroSpanParity (spec §6.2).

Requires RFSoC Pyro4 server reachable and a DAC->ADC loopback cable installed.
Run from repo root:
  python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments._loopback_check_ZeroSpanParity

This is a throwaway diagnostic — keep it under version control for repeatability
but do not import from it elsewhere.
"""

import numpy as np

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mZeroSpanParity import ZeroSpanParity
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils import chunked_acquire


def _base_cfg():
    return {
        "res_ch": 0, "qubit_ch": 1, "ro_chs": [0],
        "nqz": 2, "qubit_nqz": 2, "mixer_freq": 0.0,
        "read_pulse_freq": 1000.0,         # any safe in-range freq for loopback
        "parity_drive_freq": 1000.0,       # same — placeholder
        "qubit_gain": 100, "pulse_gain": 100,
        "res_phase": 0,
        "adc_trig_offset": 0.488,
        "read_length": 1.0,
        "start_src": "internal",
    }


def test_strobe_shape(soc, soccfg):
    cfg = _base_cfg()
    cfg.update({"mode": "strobe", "sample_period_us": 5.0, "reps_per_chunk": 1000})
    exp = ZeroSpanParity(soc=soc, soccfg=soccfg, path="Loopback_Strobe",
                         outerFolder="./_loopback_tmp/", cfg=cfg)
    data = exp.acquire(progress=False)
    assert data["I"].shape == (1000,), f"strobe I shape: {data['I'].shape}"
    assert data["Q"].shape == (1000,), f"strobe Q shape: {data['Q'].shape}"
    assert data["t_us"].shape == (1000,)
    dt = np.diff(data["t_us"])
    assert np.all(dt > 0), "t_us not monotonic"
    assert abs(float(np.mean(dt)) - 5.0) < 0.1, f"t step off: {np.mean(dt)}"
    print("loopback strobe shape: OK")


def test_chunked_stitch(soc, soccfg):
    cfg = _base_cfg()
    cfg.update({"mode": "strobe", "sample_period_us": 5.0, "reps_per_chunk": 1000})
    exp = ZeroSpanParity(soc=soc, soccfg=soccfg, path="Loopback_Chunked",
                         outerFolder="./_loopback_tmp/", cfg=cfg)
    stitched = chunked_acquire(exp, n_chunks=5)
    assert stitched["I"].shape == (5000,), stitched["I"].shape
    assert list(stitched["gap_indices"]) == [1000, 2000, 3000, 4000]
    assert np.all(np.diff(stitched["t_us"]) > 0), "stitched t_us not monotonic"
    print("loopback chunked stitch: OK")


def test_decimated_shape(soc, soccfg):
    cfg = _base_cfg()
    cfg.update({"mode": "decimated", "capture_length_us": 500.0,
                "soft_avgs": 1, "read_length": 500.0})
    exp = ZeroSpanParity(soc=soc, soccfg=soccfg, path="Loopback_Decimated",
                         outerFolder="./_loopback_tmp/", cfg=cfg)
    data = exp.acquire(progress=False)
    decimated_fs = float(soccfg["readouts"][cfg["ro_chs"][0]]["f_output"])
    expected = int(round(500.0 * decimated_fs))
    assert abs(data["I"].size - expected) <= 1, (
        f"decimated length: got {data['I'].size}, expected ~{expected}"
    )
    print(f"loopback decimated shape ({data['I'].size} samples @ "
          f"{decimated_fs} MHz): OK")


def test_validation_rules_fire(soc, soccfg):
    from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mZeroSpanParity import _validate_cfg
    bad = _base_cfg()
    bad.update({"mode": "strobe", "sample_period_us": 0.1, "reps_per_chunk": 10})
    try:
        _validate_cfg(bad, soccfg)
    except RuntimeError as ex:
        assert "rule 1" in str(ex), ex
        print("loopback validation rule 1 fires: OK")
    else:
        raise AssertionError("expected rule 1 to fire on loopback soccfg")


if __name__ == "__main__":
    soc, soccfg = makeProxy()
    test_validation_rules_fire(soc, soccfg)
    test_strobe_shape(soc, soccfg)
    test_chunked_stitch(soc, soccfg)
    test_decimated_shape(soc, soccfg)
    print("All loopback checks passed.")
```

- [ ] **Step 2: Run with loopback cable installed**

```powershell
python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments._loopback_check_ZeroSpanParity
```

Expected:
```
loopback validation rule 1 fires: OK
loopback strobe shape: OK
loopback chunked stitch: OK
loopback decimated shape (... samples @ ... MHz): OK
All loopback checks passed.
```

- [ ] **Step 3: If a check fails, debug iteratively. Likely failure modes:**

| Symptom | Likely cause | Fix |
|---|---|---|
| `_acquire_strobe` returns wrong shape | `prog.di_buf` not populated as expected for this QICK firmware version | Inspect `prog.di_buf` / `prog.dq_buf` shape; check `mChargeDispersionQuasiCW.py` for the same reshape pattern |
| `acquire_decimated` returns unexpected ndim | firmware version differs from spec assumption | adapt the shape-handling block in `_acquire_decimated` |
| Validation rules misfire on real soccfg | `soccfg["readouts"][ch]` keys named differently in this firmware | inspect `soccfg.dump_cfg()` and update `_validate_cfg` accordingly |
| `_setup_two_tones` fails on `mixer_freq` | not all setups define mixer_freq on the res_ch | conditionally pass mixer_freq only when channel supports it |

For each fix, write a one-line note in the runner script's docstring noting the firmware-specific quirk and the date observed.

- [ ] **Step 4: Commit (if any fixes were made)**

```powershell
git add WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/_loopback_check_ZeroSpanParity.py WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/mZeroSpanParity.py
git commit -m "Loopback smoke test for ZeroSpanParity; record any firmware quirks"
```

If no fixes were needed, just commit the runner alone:

```powershell
git add WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/_loopback_check_ZeroSpanParity.py
git commit -m "Add loopback smoke test runner for ZeroSpanParity (§6.2)"
```

---

## Task 16: Final integration sweep + plan-level summary commit

**Files:**
- None modified; this task is verification.

- [ ] **Step 1: Run all offline test suites in sequence**

```powershell
python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils
python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity
python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mZeroSpanParity
```

Expected output across all three: every `OK` line from Tasks 1–13 prints, and exit code is 0 for each command.

- [ ] **Step 2: Syntax-check the orchestrator**

```powershell
python -c "import ast; ast.parse(open(r'WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/test_BTQ_BFC.py').read()); print('syntax OK')"
```

Expected: `syntax OK`.

- [ ] **Step 3: Confirm the spec §6.1 coverage**

Check that each row of spec §6.1 (the offline unit-test table) has at least one assertion in `analyze_ZeroSpanParity.py`'s `__main__` block. Open the file, scan for the test name, confirm it exists. No code change.

- [ ] **Step 4: Confirm the spec §5.5 contract documentation**

Open each of these locations and verify the configuration contract is mirrored:
1. `test_BTQ_BFC.py` module docstring — top of file, contains the "ZERO-SPAN PARITY — PER-RUN PARAMETERS" block.
2. Per-section comment headers above each `*Params` dict in `test_BTQ_BFC.py`.
3. `ZeroSpanParity` class docstring in `mZeroSpanParity.py` — module docstring lists every cfg key with mode-specific requirements.
4. Validation errors in `_validate_cfg` — each `RuntimeError` includes the rule number tag.

No code change unless a gap is found; if any of these is missing, add it inline and commit before proceeding.

- [ ] **Step 5: Final commit (only if Step 4 added documentation)**

```powershell
git add -p   # interactively select only the documentation additions
git commit -m "Complete §5.5 configuration contract documentation"
```

- [ ] **Step 6: Tag the plan-complete state for easy reference**

```powershell
git tag bfc-parity-plan-complete-offline-validated
```

This tag marks the state where all offline + syntax-level acceptance is met. Hardware (loopback + physics validation) is gated separately by Task 15 and by spec §6.3.

---

## Plan-level acceptance criteria

- All Task 1–13 unit tests pass via the `python -m ...` invocations from Task 16 Step 1.
- `test_BTQ_BFC.py` passes syntax check (Task 16 Step 2).
- Spec §5.5 contract is mirrored in all four code locations (Task 16 Step 4).
- Task 15 (loopback) is complete if RFSoC was available at implementation time; otherwise documented as deferred.

What this plan does **not** deliver (intentionally per spec §6.6):

- §6.3 physics-level validation on a real qubit — blocked on test_BTQ_BFC cooldown
- `CSTQ03_BFC.py` orchestrator — separate spec/phase when CSTQ03 is ready
- Live plotting during acquisition (out of scope per spec §1)
- Multi-qubit MUX simultaneous parity (out of scope per spec §1)
