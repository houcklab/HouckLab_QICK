# OPX Reset Reference Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a portable OPX T1 benchmark that measures passive-reset versus true-unbounded active-reset behavior with the same post-reset delays and raw shot-order diagnostics used by the QICK tests.

**Architecture:** Keep QUA and OPX imports inside a hardware runner so the host-side schedule, reduction, fitting, and cross-method metrics remain testable without OPX dependencies. Store flat raw shot records, grouped summaries, fit results, reset-attempt telemetry, and acquisition timing in open formats. Run fixed-park T1 by default and make a flux excursion an explicit command-line option.

**Tech Stack:** Python 3.10, NumPy, SciPy, matplotlib, pytest, QUA, qualang-tools, existing Houck-Lab-Qua calibration/configuration modules.

**Spec:** Current user request and the QICK paired-recovery schema in `WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/t1_flux_ramp_park_refresh_paired_q3.py`.

## Global Constraints

- New Python files contain no comments or docstrings.
- Active reset uses a true QUA `while_` loop with no iteration cap.
- Passive and active methods are interleaved within every round.
- Active post-reset delays are 25, 100, 400, and 1000 microseconds; passive reset is 1000 microseconds.
- Absolute T1 values are not compared across chips; active/passive ratios and endpoint shifts are compared within each platform.
- The separate Houck-Lab-Qua checkout is not modified because it has no tracked history.

---

### Task 1: Host-side OPX reference analysis

**Files:**
- Create: `WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/opx_reference_analysis.py`
- Test: `WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/tests/test_opx_reference_analysis.py`

**Interfaces:**
- Consumes: method names, T1 delay vector, random seed, and flat per-shot records.
- Produces: `build_interleaved_schedule(rounds, methods, delay_count, seed)`, `summarize_shots(records, methods, delays_us)`, `fit_method_decays(summary_rows, methods)`, and `make_comparison(fits, passive_method)`.

- [x] **Step 1: Write failing tests for deterministic balanced scheduling, grouped raw-shot reduction, and within-chip active/passive fit ratios.**
- [x] **Step 2: Run `pytest WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/tests/test_opx_reference_analysis.py -q` and verify imports fail because the analysis module does not exist.**
- [x] **Step 3: Implement the four pure host-side functions with validation for malformed or incomplete inputs.**
- [x] **Step 4: Run the focused tests and verify they pass.**
- [x] **Step 5: Run the full active-reset test suite and verify no regression.**

### Task 2: Portable QUA benchmark runner

**Files:**
- Create: `WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/opx_reference_t1.py`
- Modify: `WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/tests/test_opx_reference_analysis.py`

**Interfaces:**
- Consumes: `--qua-repo`, `--chip`, `--qubit`, optional `--dc-target-voltage`, optional `--park-voltage`, optional T1 delays, rounds, and shots per block.
- Produces: `raw_shots.csv`, `summary.csv`, `fits.json`, `metadata.json`, and `comparison.png` in a timestamped OPX data folder.

- [x] **Step 1: Add a failing source-contract test requiring lazy QUA imports, an unbounded `while_`, timestamp and reset-attempt streams, five reset methods, and no comments or docstrings.**
- [x] **Step 2: Run the focused test and verify it fails because the runner does not exist.**
- [x] **Step 3: Implement one interleaved QUA program that performs X180 T1 payloads, optional OPX DC-offset excursions, payload readout, passive or unbounded active reset, and explicit post-reset waits.**
- [x] **Step 4: Implement result fetching, record validation, CSV/JSON output, within-chip fitting, timing metrics, and plotting.**
- [x] **Step 5: Run focused and full active-reset tests, compile the Python sources, and inspect the final diff.**
- [x] **Step 6: Commit and push to `origin/tls-spectroscopy` with Rumman as the sole author.**
