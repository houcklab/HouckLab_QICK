# Zero-Span Parity — Contrast / SNR Validation Harness

**Spec date:** 2026-06-01
**Author:** brainstormed with Claude Code
**Status:** design approved by user; awaiting implementation plan
**Builds on:** `docs/superpowers/specs/2026-05-16-bfc-charge-parity-zero-span-design.md` (canonical acquisition/analysis spec). This document is an **addendum** — it adds a validation harness on top of the already-implemented `mZeroSpanParity.py` + `analyze_ZeroSpanParity.py`. Where the two conflict, the canonical spec governs acquisition internals; this spec governs the validation layer.
**Target device:** CSTQ03 (production target; physics stages blocked on cooldown).
**Edit scope:** `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/` only (incl. `utils.py`, `analyze_ZeroSpanParity.py`, and the orchestrator `CSTQ03_BFC.py`).

## Problem statement

The acquisition (`mZeroSpanParity.py`) and offline analysis (`analyze_ZeroSpanParity.py`) for zero-span charge-parity detection already exist. Before trusting a natural-parity telegraph signal, we must prove the signal is **parity-dependent**, **time-resolved**, and **not drift / noise / drive artifacts**. This spec defines a staged validation harness that builds the contrast/SNR evidence chain end-to-end, reusing the existing acquisition and analysis as primitives.

The validation follows a 9-stage evidence chain:

1. **Static contrast** — drive parked at one parity branch f₊; measure resonator S21 with qubit drive OFF vs ON; sweep resonator probe freq; find max `|S21_on − S21_off|`. (Long-average, not time-resolved.)
2. **Contrast follows qubit freq** — sweep qubit drive freq while monitoring the zero-span resonator response; see two parity peaks f₊/f₋; confirm signal largest on a branch.
3. **Artificial on/off modulation** — square-wave the qubit drive on/off (~25 Hz default); recovered IQ trace must show the same modulation. Validates timing, demod, and projection axis before trusting natural switching.
4. **Two-level telegraph** — continuous acquisition; project `V(t) = I·cosθ + Q·sinθ`; look for bimodal jumps; histogram should have two peaks.
5. **Bin-size dependence** — reprocess the same raw IQ at `t_bin ∈ {0.1, 0.2, 0.5, 1.0} ms`; levels should separate better until `t_bin` approaches the parity lifetime (~2–3 ms).
6. **Dwell times** — threshold the trace, extract dwell distributions, expect exponential `P(τ) ∝ exp(−τ/T_parity)`, mean near expected, stable vs threshold choice.
7. **Switching rate responds to environment** — rate changes with power / detuning / drive-off (and, manually logged, temperature / shielding).
8. **Instrument-artifact controls** — A: drive off; B: drive far detuned; C: resonator probe off-resonance; D: swap drive to other parity branch. Contrast should change/vanish appropriately.
9. **Evidence chain** — collate stages 1–8 into a single report.

## Decisions locked during brainstorming

| Decision | Choice | Rationale |
|---|---|---|
| Build scope | All 9 stages | User: "plan then build", full harness. |
| Acquisition mode | **Strobe only** | `sample_period_us` is set directly, so absolute ms-scale timing (stages 3/5/6) is trustworthy now. Decimated time axis is flagged unverified (`soccfg f_output` ≠ true rate until loopback cal) — deferred. |
| Stage-3 modulation mechanism | **Software block alternation** | Toggle `qubit_gain` per block of reps and stitch via the existing `chunked_acquire` pattern. No new on-board tProc logic; ~25 Hz is trivially fast relative to per-block run time. |
| Stage-3 default | **~25 Hz, several periods** | 40 ms period (≈1000 reps on / 1000 off at 20 µs/sample), ≈8–10 periods (~0.4 s). Comfortably resolved, well above parity switching. Override per-run. |
| Stage-9 report | **Collate evidence, no auto pass/fail** | Expected T_parity / SNR are unmeasured on CSTQ03; hard thresholds would be premature. Report assembles numbers + plots for human judgment. |
| Architecture | **New `validate_ZeroSpanParity.py` harness** composing existing acquisition + analysis | Keeps validation reusable on the next device, keeps `CSTQ03_BFC.py` readable, each unit independently testable on synthetic data. |

---

## §1 — File layout

All inside `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/`.

```
utils.py                       # EXTEND: + modulated_strobe_acquire(...)
analyze_ZeroSpanParity.py      # EXTEND: + 5 pure analysis primitives (§3)
validate_ZeroSpanParity.py     # NEW: device-agnostic validation harness (§4)
CSTQ03_BFC.py                  # EXTEND: thin Validate_* flags + param dicts + calls (§5)
```

No new acquisition program is needed: the existing `ZeroSpanParityProgStrobe` already drives the qubit const tone and the resonator const tone simultaneously, so stages 1, 2, 3, 8 are **outer loops / gain schedules around the existing `ZeroSpanParity` strobe acquisition**, not new firmware.

### Out of scope (this spec)

- Decimated-mode validation (deferred until loopback time-axis calibration; canonical spec §7.3).
- Automated pass/fail verdicts (stage 9 collates only).
- Programmatic temperature control (no interface; logged manually into the report).
- Live/online plotting during acquisition.
- A new QICK program for modulation (software block alternation instead).

---

## §2 — Acquisition addition (`utils.py`)

### `modulated_strobe_acquire(experiment, cfg, gain_schedule, reps_per_block, soc, soccfg, progress=False)`

Runs the strobe acquisition in blocks, setting `cfg["qubit_gain"]` per block according to `gain_schedule`, and stitches the per-block IQ into one contiguous trace. Built on the same back-to-back `acquire()` + stitch pattern as the existing `chunked_acquire`.

- `gain_schedule`: list of `(gain_value, n_blocks)` or a flat list of per-block gains. For a 25 Hz square wave with `reps_per_block` chosen so one block = one half-period, the schedule alternates `[G_on, 0, G_on, 0, ...]`.
- `reps_per_block`: reps per block; must satisfy canonical §5.3 rule 4 (`≤ avg_maxlen`).

Returns (superset of `chunked_acquire`'s contract):
```
{
  "I", "Q", "t_us",          # stitched strobe trace (per-cycle-normalized, canonical §7.1)
  "gap_indices",             # block boundaries (avoid counting switches across them)
  "modulation_reference",    # sample-aligned injected on/off square wave (1 = drive on, 0 = off)
  "block_labels",            # per-block gain actually applied
  "reps_per_block", "sample_period_us",
  "modulation_freq_hz",      # derived from reps_per_block * sample_period_us
}
```

**Why software, not firmware:** at ~25 Hz one half-period is ~1000 reps; the only cost is the small inter-block Python/tProc gap already absorbed by `gap_indices`. No 16-bit pulse-length concern, no new register logic to validate in loopback.

---

## §3 — Analysis primitives (`analyze_ZeroSpanParity.py`)

Five new **pure functions** (arrays in → dict out, no file I/O), consistent with the existing module's style (canonical §3 functions are pure; only `analyze_parity_run` touches disk). Each is independently unit-testable on synthetic data.

### 3.1 `verify_modulation(scores, t_us, modulation_reference, gap_indices=None)` — Stage 3

Confirms the recovered projected trace carries the injected square wave.
- Mean projected level during drive-ON blocks vs drive-OFF blocks → `level_on`, `level_off`, `modulation_depth`.
- Normalized cross-correlation of `scores` vs `modulation_reference`; peak value and lag (sample offset) → `correlation`, `lag_samples`.
- Recovered modulation frequency (from the dominant FFT bin of `scores`) vs injected → `recovered_freq_hz`, `injected_freq_hz`.
- `snr = |level_on − level_off| / pooled_std`.
Returns `{level_on, level_off, modulation_depth, snr, correlation, lag_samples, recovered_freq_hz, injected_freq_hz}`.

### 3.2 `projected_histogram_snr(scores, bins="auto")` — Stage 4 (quantitative)

Two-Gaussian mixture fit of `V(t)` histogram.
- Fit 2-component GMM (or two-peak fit) → `centers (2,)`, `sigmas (2,)`, `weights (2,)`.
- `separation_snr = |c0 − c1| / sqrt(0.5·(σ0² + σ1²))`.
- `overlap` (classification error / Bhattacharyya) as a bimodality measure.
- `is_bimodal` heuristic flag (e.g. separation_snr above a small floor AND both weights non-negligible).
Returns `{centers, sigmas, weights, separation_snr, overlap, is_bimodal, hist, bin_edges}`.

### 3.3 `bin_size_sweep(I, Q, t_us, separator, bin_list_us, gap_indices=None, method="apriori")` — Stage 5

For each `t_bin` in `bin_list_us` (default `[100, 200, 500, 1000]` µs): mean-bin via existing `_bin_iq_time`, classify via `classify_parity_trace`, compute `projected_histogram_snr.separation_snr` and `dwell_time_statistics` τ.
Returns `{bin_list_us, separation_snr_per_bin, mean_dwell_per_bin, exp_tau_per_bin, best_bin_us}` plus a single comparison figure (caller saves). `best_bin_us` = bin maximizing separation SNR (expected to peak below T_parity then degrade — the convergence signature).

### 3.4 `threshold_stability(scores, t_us, threshold_list=None, gap_indices=None)` — Stage 6

Default `threshold_list` = percentiles around the midpoint (e.g. 30–70th of `scores`). For each threshold, binarize, run `dwell_time_statistics`, record τ₀, τ₁.
Returns `{threshold_list, tau0_per_threshold, tau1_per_threshold, tau_cv}` where `tau_cv` (coefficient of variation of τ across thresholds) quantifies stability — low CV = robust telegraph, high CV = noise crossings.

### 3.5 `contrast_from_sweeps(freqs, S21_on, S21_off)` — Stage 1

Both `S21_*` are complex arrays vs `freqs`.
- `contrast = |S21_on − S21_off|` (complex difference magnitude).
- `best_freq = freqs[argmax(contrast)]`, `max_contrast`.
- `contrast_snr = max_contrast / noise_floor` (noise from off-feature baseline of the contrast curve).
Returns `{freqs, contrast, best_freq, max_contrast, contrast_snr, S21_on, S21_off}`.

### Guards (inherit canonical §3 conventions)

- Empty / degenerate inputs return sensible structures (nan fits, zero SNR) without exceptions.
- All `gap_indices` respected so chunk/block boundaries never masquerade as transitions or dwell joins.
- Fits that fail to converge return `nan` fields rather than raising.

---

## §4 — Validation harness (`validate_ZeroSpanParity.py`)

Device-agnostic. Composes the existing `ZeroSpanParity` acquisition + the §3 primitives. Each `run_*` returns a result dict and writes a tagged sidecar (JSON + PNGs) using the existing `ExperimentClass` save machinery, so stage 9 can collate by scanning the run folder.

### 4.1 `run_static_contrast(cfg, freq_list, qubit_gain_on, soc, soccfg, ...)` — Stage 1
Loop `read_pulse_freq` over `freq_list`. Two passes: `qubit_gain = qubit_gain_on` → `S21_on(f)`; `qubit_gain = 0` → `S21_off(f)`. Each point is a short strobe acquisition averaged to one complex S21. Call `contrast_from_sweeps`. Plot `|S21_on|`, `|S21_off|`, and contrast vs freq with `best_freq` marked. The returned `best_freq` is the recommended `read_pulse_freq` for the live measurement.

### 4.2 `run_contrast_vs_qubit_freq(cfg, qfreq_list, soc, soccfg, ...)` — Stage 2
Loop `parity_drive_freq` over `qfreq_list`; short zero-span strobe trace each; contrast metric per point (e.g. projected-V spread / `separation_snr` from `projected_histogram_snr`, plus mean |S21|). Plot contrast vs qubit freq; mark the two parity peaks via the existing `find_two_tone_peaks`. Confirms the zero-span signal tracks f₊/f₋.

### 4.3 `run_modulation_check(cfg, modulation_freq_hz=25, n_periods=10, soc, soccfg, ...)` — Stage 3
Compute `reps_per_block` from `modulation_freq_hz` and `sample_period_us` (one block = one half-period). Build alternating `[G_on, 0]` schedule for `n_periods`. Call `modulated_strobe_acquire`, then `classify_parity_trace` → `verify_modulation`. Plot recovered `V(t)` overlaid with `modulation_reference`. Pass evidence: high `correlation`, `modulation_depth`, and `recovered_freq_hz ≈ injected_freq_hz`. **This is the pipeline-sanity gate** — run before trusting natural switching.

### 4.4 `run_control_suite(cfg, variants=("A","B","C","D"), detune_mhz, soc, soccfg, ...)` — Stage 8
Enumerate control variants, run `ZeroSpanParity` + `analyze_parity_run` per variant, tag each sidecar with its control label:
- **A** drive off: `qubit_gain = 0`.
- **B** drive far detuned: `parity_drive_freq += detune_mhz` (≫ linewidth).
- **C** probe off-resonance: `read_pulse_freq` shifted off the contrast slope.
- **D** swap branch: `which_to_park` flipped via `pick_parity_drive_freq` (optionally auto-run both branches).
Produce a control-vs-signal comparison plot (telegraph contrast / `separation_snr` per variant). Expectation: contrast vanishes for A/B/C, sign/assignment changes for D.

### 4.5 `CrossRunComparison` — Stages 5/7/8 glue
Small helper: collect `(swept_param_value, metric_value)` across runs and emit a correlation table + plot. Used by stage 7 (rate vs power/detuning/drive-off) and shared by stages 5/8 comparisons. Stage 7 outer sweeps reuse the existing `YOKOGS200` / attenuator (`control_atten.dll`) loop patterns already in `CSTQ03_BFC.py`. Temperature is logged manually into the comparison (no programmatic interface).

### 4.6 `build_evidence_report(run_dir, out_path)` — Stage 9
Scan `run_dir` for the tagged per-stage JSON sidecars + PNGs, assemble a single markdown report (embedding figures) that walks the 9-item evidence chain with the measured numbers for each. **No pass/fail** — presents:
two spec peaks (f₊/f₋), static on/off contrast + best probe freq, modulation-recovery correlation, bimodal IQ + histogram separation SNR, bin-size convergence, exponential dwell τ + threshold stability, control-suite comparison. Human reads and judges.

---

## §5 — Orchestrator wiring (`CSTQ03_BFC.py`)

Thin layer mirroring the existing `ZSP_*` block style: top-level boolean flags + per-stage param dicts + linear calls into the harness. No stage logic lives here.

```python
# --- Validation harness flags (this run) ---
Validate_StaticContrast      = False
Validate_ContrastVsQubitFreq = False
Validate_ModulationCheck     = True     # pipeline-sanity gate — run first
Validate_Telegraph           = False    # continuous run + projected_histogram_snr
Validate_BinSizeSweep        = False
Validate_ThresholdStability  = False
Validate_EnvironmentSweep    = False
Validate_ControlSuite        = False
Build_EvidenceReport         = False

# --- Per-stage params (defaults; override per run) ---
StaticContrast_params   = {"freq_span_mhz": ..., "n_points": ..., "reps_per_point": ...}
ContrastVsQubit_params  = {"qfreq_span_mhz": ..., "n_points": ...}
Modulation_params       = {"modulation_freq_hz": 25, "n_periods": 10}
BinSize_params          = {"bin_list_us": [100, 200, 500, 1000]}
Threshold_params        = {"threshold_percentiles": [30, 40, 50, 60, 70]}
Environment_params      = {"sweep": "power", "values": [...]}   # power|detuning|drive_off
Control_params          = {"variants": ["A","B","C","D"], "detune_mhz": ...}
```

Each block raises immediately if it needs cached calibration (parked freqs / separator from the canonical-spec `ZSP_*_Cached`) that is `None` — no silent fall-through (matches canonical §4.3).

---

## §6 — Validation & test plan

### §6.1 Offline unit tests (no hardware) — extend `analyze_ZeroSpanParity.py`'s `__main__`

| Test | Synthetic input | Assertion |
|---|---|---|
| `verify_modulation` | Projected trace = injected square wave + Gaussian noise | `correlation > 0.9`, `recovered_freq_hz` within ±5% of injected, `lag` ≈ 0 |
| `projected_histogram_snr` | Two Gaussians, known centers/σ | `centers`, `sigmas` within ±5%; `separation_snr` matches analytic; `is_bimodal` True |
| `projected_histogram_snr` unimodal | Single Gaussian | `is_bimodal` False, `separation_snr` ≈ 0 |
| `bin_size_sweep` | Markov telegraph, known τ, sub-bin noise | `separation_snr_per_bin` increases then degrades; `best_bin_us` below τ |
| `threshold_stability` | Clean telegraph vs pure noise | clean → low `tau_cv`; noise → high `tau_cv` |
| `contrast_from_sweeps` | Two Lorentzian S21 with known on/off shift | `best_freq` at max-slope point; `contrast_snr` high |

Run time < 5 s. Pass before hardware.

### §6.2 Loopback smoke test (RFSoC, no qubit) — extend `_loopback_check_ZeroSpanParity.py`

| Check | How | Pass criterion |
|---|---|---|
| `modulated_strobe_acquire` shape | 4 blocks, `reps_per_block=1000` | `I.shape == (4000,)`; `gap_indices == [1000,2000,3000]`; `modulation_reference` alternates per block |
| Modulation reference alignment | inspect `block_labels` vs schedule | matches requested `[G_on,0,G_on,0]` |
| `run_static_contrast` plumbing | tiny `freq_list`, tiny gain | returns finite `contrast` array of len(freq_list); two PNGs written |

Run time < 30 s. Pass before real qubit.

### §6.3 Physics validation (CSTQ03 — blocked on cooldown)

Run order on a live qubit (after coherence benchmark per `feedback_coherence_benchmark.md`):
1. Stage 2 (`run_contrast_vs_qubit_freq`) → confirm f₊/f₋, pick branch.
2. Stage 1 (`run_static_contrast`) → confirm on/off contrast, pick `read_pulse_freq`.
3. **Stage 3 (`run_modulation_check`) → pipeline-sanity gate. Do not proceed if modulation isn't recovered.**
4. Stage 4 telegraph + `projected_histogram_snr`.
5. Stage 5 bin-size sweep; Stage 6 dwell + threshold stability.
6. Stage 8 control suite (A/B/C/D).
7. Stage 7 environment sweeps (power/detuning/drive-off; temperature manual).
8. Stage 9 `build_evidence_report`.

### §6.4 Acceptance criteria

- All §6.1 offline tests pass.
- All §6.2 loopback tests pass.
- Stage-3 modulation recovered in loopback-plumbing form (real recovery on qubit deferred to §6.3).
- §5 flags/params present in `CSTQ03_BFC.py`; harness importable; `build_evidence_report` produces a report from synthetic per-stage sidecars.

---

## §7 — Open items carried forward

- **Expected T_parity** (~2–3 ms) is unmeasured on CSTQ03; bin-size ranges and dwell sanity are parameterized, not hard-coded. Set from the device's measured T1/T2 benchmark when available.
- **Decimated timing** stays deferred until loopback rate calibration (canonical §7.3); all validation here is strobe.
- **Readout geometry** (transmission vs reflection) only affects the stage-1 contrast metric labeling; `contrast_from_sweeps` uses the complex difference magnitude either way.

## Related files

- Canonical spec: `docs/superpowers/specs/2026-05-16-bfc-charge-parity-zero-span-design.md`
- Acquisition: `Experiments/mZeroSpanParity.py` (`ZeroSpanParityProgStrobe`, `ZeroSpanParity`)
- Analysis: `Experiments/analyze_ZeroSpanParity.py`
- Helpers: `Experiments/utils.py` (`chunked_acquire`, `pick_parity_drive_freq`, `project_iq_onto_separator`, `find_two_tone_peaks`)
- Orchestrator: `Experiments/CSTQ03_BFC.py` (`ZSP_*` blocks, `get_apriori_separator_from_singleshot`)
- Loopback: `Experiments/_loopback_check_ZeroSpanParity.py`
