# OPX-Style Active Reset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an isolated, q3-runnable QICK/tProc-v1 active reset whose runtime control flow matches the QUA reset and whose telemetry proves what happened on every shot.

**Architecture:** Pure-Python modules define and test the classifier, bounded state machine, data-memory schema, and analysis. A QICK 0.2.133 program emits the same state machine as tProc-v1 branches and stores fixed-size per-shot records in data memory, allowing data-dependent readout counts without the fixed-shape averager acquisition path. A standalone q3 runner performs calibration and interleaved benchmark stages without importing the new package into production experiments.

**Tech Stack:** Python 3, NumPy, SciPy, Matplotlib, pytest, QICK 0.2.133/tProc v1

**Spec:** `docs/superpowers/specs/2026-09-04-opx-active-reset-design.md`

## Global Constraints

- Initial hardware target is q3 using the board-served QICK 0.2.133 tProc-v1 API.
- New code lives only under `WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/`.
- Existing production reset and experiment modules are not modified or made to import the new package.
- Decision zero is the payload measurement; up to eight corrective attempts may follow.
- Every corrective decision runs on the tProc; Python only starts blocks and reads completed telemetry.
- Hardware failures abort explicitly and never fall back to passive reset.
- Commits use `Rumman <rumman@princeton.edu>` and contain no co-author tags.

---

### Task 1: Configuration, classifier, and record schema

**Files:**
- Create: `WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/__init__.py`
- Create: `WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/config.py`
- Create: `WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/classifier.py`
- Create: `WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/records.py`
- Test: `WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/tests/test_config_classifier_records.py`

**Interfaces:**
- Produces: `ClassifierCalibration`, `fit_classifier(...)`, `classify(...)`, `OPXResetConfig.from_mapping(...)`, `ShotRecord`, `decode_records(...)`, and `max_records(...)`.

- [ ] **Step 1: Write failing tests** for classifier orientation, three-zone boundaries, held-out fitting, eight-attempt validation, signed word decoding, and capacity arithmetic.
- [ ] **Step 2: Run the test file and verify failures are missing-module or missing-interface failures.**
- [ ] **Step 3: Implement immutable calibration/config records and a versioned eight-word telemetry record.**
- [ ] **Step 4: Implement a train/holdout rotated classifier whose excited centroid is always above ground and whose two thresholds enforce false-ground and false-pi limits.**
- [ ] **Step 5: Run the test file and verify it passes.**

### Task 2: Executable state-machine model and tProc emitter

**Files:**
- Create: `WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/control_flow.py`
- Test: `WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/tests/test_control_flow.py`

**Interfaces:**
- Consumes: `ClassifierCalibration`.
- Produces: `simulate_reset(decisions, ...) -> ResetOutcome` and `emit_reset_state_machine(prog, ...) -> None`.

- [ ] **Step 1: Write failing state-machine tests** proving immediate-ground exits without a reset measurement, ambiguous shots remeasure without pi, excited shots receive pi, the eighth remeasurement is evaluated, and no ninth correction is possible.
- [ ] **Step 2: Run the tests and verify the intended failures.**
- [ ] **Step 3: Implement the pure state-machine model with literal terminal statuses.**
- [ ] **Step 4: Add a recording fake tProc and interpreter, then write failing emitter tests for the same branch traces.**
- [ ] **Step 5: Implement generated tProc-v1 `condj` blocks with a common early-exit label and separate initial/loop thresholds.**
- [ ] **Step 6: Run the control-flow tests and verify model/emitter parity.**

### Task 3: Direct data-memory acquisition

**Files:**
- Create: `WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/acquisition.py`
- Test: `WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/tests/test_acquisition.py`

**Interfaces:**
- Consumes: a compiled QICK program exposing `config_all`, `config_bufs`, `record_base`, `record_words`, and `reps`.
- Produces: `run_dmem_block(soc, program, timeout_s) -> list[ShotRecord]` and `chunk_sizes(total_shots, capacity) -> list[int]`.

- [ ] **Step 1: Write failing tests** for successful completion, chunking, timeout/reset cleanup, partial telemetry, unsigned-to-signed conversion, and both QICK 0.2.133 data-memory read APIs.
- [ ] **Step 2: Run the tests and verify the intended failures.**
- [ ] **Step 3: Implement direct program loading, average-buffer feedback enablement, completion-counter polling, bounded DMem reads, and record decoding.**
- [ ] **Step 4: Implement fail-closed timeout cleanup through tProc reset and generator reset.**
- [ ] **Step 5: Run the acquisition tests and verify they pass.**

### Task 4: QICK calibration and benchmark programs

**Files:**
- Create: `WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/programs.py`
- Test: `WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/tests/test_programs.py`

**Interfaces:**
- Consumes: `OPXResetConfig`, `ClassifierCalibration`, `emit_reset_state_machine`, and existing pulse/park helpers.
- Produces: `TimingMatchedReferenceProgram` and `OPXResetBenchmarkProgram`.

- [ ] **Step 1: Write failing tests with a recording QICK double** for payload-first ordering, latched park lifetime, dynamic DMem writes, verification readout placement, completion-counter writes, and register collision rejection.
- [ ] **Step 2: Run the tests and verify the intended failures.**
- [ ] **Step 3: Implement the fixed-read-count timing-matched reference program for payload and post-measurement contexts.**
- [ ] **Step 4: Implement the custom benchmark program with an outer tProc shot loop, dynamic DMem address, OPX reset emitter, independent verification readout, and normal-path park cleanup.**
- [ ] **Step 5: Compile the program against QICK 0.2.133 or its source distribution using a representative tProc-v1 configuration.**
- [ ] **Step 6: Run the program tests and relevant existing active-reset tests.**

### Task 5: Calibration, analysis, persistence, and q3 runner

**Files:**
- Create: `WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/calibration.py`
- Create: `WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/analysis.py`
- Create: `WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/benchmark_q3.py`
- Test: `WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/tests/test_analysis_runner.py`

**Interfaces:**
- Consumes: reference and benchmark programs, acquisition blocks, classifier fits, and the current q3 `BaseConfig`.
- Produces: calibration JSON, per-shot CSV, summary JSON/text, plots, assembly text, and an explicit stage runner.

- [ ] **Step 1: Write failing tests** for population projection, Wilson intervals, timeout-inclusive residuals, calibration JSON round-trip, incremental CSV output, and fail-closed stage dependency checks.
- [ ] **Step 2: Run the tests and verify the intended failures.**
- [ ] **Step 3: Implement analysis and JSON-safe calibration serialization.**
- [ ] **Step 4: Implement reference acquisition for decision-zero and in-loop timing, using fixed readout counts and held-out fitting.**
- [ ] **Step 5: Implement `benchmark_q3.py` with a top-level editable configuration, `makeProxy()`, staged calibration/benchmark execution, DMem-aware chunking, incremental saves, and clear hardware instructions.**
- [ ] **Step 6: Run dry-run runner tests and verify malformed or missing calibrations abort without passive fallback.**

### Task 6: Documentation and full verification

**Files:**
- Create: `WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/README.md`
- Modify only if tests require collection support: no production module.

**Interfaces:**
- Produces: measurement-PC instructions and an auditable test report.

- [ ] **Step 1: Document configuration, stages, generated artifacts, expected console output, abort behavior, and the exact first q3 smoke-test sequence.**
- [ ] **Step 2: Run all new tests.**
- [ ] **Step 3: Run the complete existing TLS active-reset/reset-dispatch suite.**
- [ ] **Step 4: Run `compileall`, `git diff --check`, and inspect the final diff for production-file changes.**
- [ ] **Step 5: Commit implementation under the configured user identity, with no co-author trailer.**
- [ ] **Step 6: Push `tls-spectroscopy` only after all local verification succeeds.**
