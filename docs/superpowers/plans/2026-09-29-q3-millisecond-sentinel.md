# q3 Millisecond Sentinel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Acquire and analyze time-resolved, raw-IQ loss-flank streams at two q3 loss lines and a quiet control during this cooldown.

**Architecture:** A new experiment-only runner reuses the pinned passive wide scout, corrected swap-hold pulse, resident data-memory stream, and frozen readout-axis code. It saves per-logical-shot host timestamps from the stream progress callback because bank handshakes interrupt the tProc; a standalone analyzer uses actual timestamps and treats bank crossings as discontinuities. No production TLS scan defaults change.

**Tech Stack:** Python 3.10, QICK tProc v1 resident stream, NumPy/SciPy, pytest, NAS manifest/NPZ artifacts.

**Spec:** User-pasted “Millisecond sentinel — time-resolved motion of a single q3 loss line (1 ms – 60 s),” September 29, 2026; summarized in `docs/q3_pump_probe_20260926.md`.

## Global Constraints

- Fresh 3.8–4.3 GHz passive wide scout; qualify A, B at least 20 MHz apart, and a clean C at least 10 MHz from qualified loss.
- Pinned q3 flux-tail correction, full 40 µs corrected return, frozen readout axis, raw IQ, and no production defaults changed.
- Start with passive 500 µs recovery; `dump` is a separately requested optional pass and must validate against references.
- Eight 25 µs, excited-prepared subshots per logical shot in palindromic order: A−, A+, B, C, C, B, A+, A−.
- Twelve approximately 5 s science chunks, three null chunks, per-chunk dither controls, pre/post profiles and scouts, checkpointed manifest.
- Report time resolution actually supported by measured shot intervals; never claim a 1 ms position measurement or a 60 s switching-rate fit from one short run.

## Review Focus

- Streaming handshakes may delay shots. Assert actual progress timestamps are retained, monotonic, and analysis never assumes one global fixed period.
- A line may move, vanish, or overlap a control. Assert the gate stops science while retaining scout/profile artifacts.
- A flank slope may approach zero or reverse. Assert the analyzer marks that chunk invalid instead of dividing by noise.
- A readout axis may drift. Assert the post and interleaved references gate scientific claims, not just acquisition completion.
- Host polling may bunch callbacks. Assert repeated timestamps are treated as unresolved timing and excluded from high-frequency estimates.

---

### Task 1: Site qualification and flank calibration

**Files:** Create `WorkingProjects/TLS_Spectroscopy/Client_modules/Runners/TLSMillisecondSentinel.py`; test `tests/test_tls_millisecond_sentinel.py`.

**Interfaces:** `select_sites(rows) -> dict`, `fit_static_profile(frequency_mhz, survival) -> dict`, `make_flanks(profile, flux_model) -> dict`, `profile_gate(profile) -> dict`.

- [ ] Write failing tests for two qualified distinct sites, a control clean in both directions, a missing-B stop, Lorentzian center/HWHM recovery, signed flank gradients, and weak-profile gate.
- [ ] Run targeted pytest and inspect expected failure.
- [ ] Implement selector and fit/calibration helpers using raw scout survival and integer DAC offsets.
- [ ] Rerun targeted tests and commit.

### Task 2: Eight-condition passive/dump QICK sequence and timing

**Files:** Modify runner; test `tests/test_tls_millisecond_sentinel.py`.

**Interfaces:** `sentinel_conditions(targets, reset_mode) -> list`, `SentinelProgram`, `capture_timestamps(...) -> tuple`, `validate_timestamps(...)`.

- [ ] Write failing tests for palindrome, 8 records/shot, dynamic target DACs, matched 25 µs holds, passive recovery, optional 60 µs dump, progress timestamps, and invalid duplicates.
- [ ] Run targeted pytest and inspect expected failure.
- [ ] Implement sequence by reusing corrected `SwapHoldProgram._resident_excursion` and resident stream; emit a dump visit only after readout in dump mode.
- [ ] Rerun targeted tests and commit.

### Task 3: Checkpointed acquisition protocol

**Files:** Modify runner; test `tests/test_tls_millisecond_sentinel.py`.

**Interfaces:** `run(..., reset_mode='passive') -> Path`, `plan(...) -> dict`, `main(argv=None) -> int`.

- [ ] Write failing tests for hardware-free plan, failed site gate, full manifest schedule, chunk timing/raw-IQ shapes, null reassignment, and safe resume/failed checkpoint semantics.
- [ ] Run targeted pytest and inspect expected failure.
- [ ] Implement wide scout, static profiles, readout references, science/calibration/null chunks, post checks, and manifest status gates.
- [ ] Rerun targeted tests and commit.

### Task 4: Standalone offline analysis and documentation

**Files:** Create `WorkingProjects/TLS_Spectroscopy/Client_modules/Runners/TLSMillisecondSentinelAnalyze.py`; test `tests/test_tls_millisecond_sentinel_analysis.py`; modify `docs/q3_pump_probe_20260926.md`.

**Interfaces:** `analyze_session(manifest_path) -> dict`, `main(argv=None) -> int`.

- [ ] Write failing synthetic tests for signed-slope line-position recovery, null/common-mode rejection, irregular sampling and bank gaps, telegraph versus stationary control, and zero-slope refusal.
- [ ] Run targeted pytest and inspect expected failure.
- [ ] Implement raw-IQ projections, dither slopes, irregular-time spectra/Allan/lag statistics, cautious telegraph and pulse-tube screens, report artifacts, and commands.
- [ ] Run targeted and maintained suites, static compile, dry-run plan, inspect diff, commit and push `tls-spectroscopy` per the established measurement-PC workflow.
