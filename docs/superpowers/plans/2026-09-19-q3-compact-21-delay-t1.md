# Q3 Compact 21-Delay T1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in QICK program that acquires P0, P1, and a 21-delay T1 axis inside one shot × frequency block without exceeding the 16,384-word tProc instruction limit.

**Architecture:** The legacy `OPXResetT1NPointProgram` unrolls every active-reset/flux condition and reaches 59,726 words for 21 delays.  The compact program will retain one active-reset payload body and choose a runtime hold duration with a tProc register loop.  The existing 3-delay chunked acquisition remains intact and is selected by default; `opx_t1_compact_delay_loop=True` explicitly selects the compact program and reports its different order.

**Tech Stack:** Python, QICK tProc assembly primitives (`loopnz`, `condj`, `sync`), DMem resident streaming, pytest.

**Spec:** User-approved design in this task: preserve the chunked fallback; do not silently substitute it; provide a small hardware validation before the full 801-frequency measurement.

## Global Constraints

- Preserve active reset, target-to-park lifecycle, full 40 us return recovery, P0/P1 references, and condition-tag decoding.
- Compact mode must produce `shot, frequency, condition` order with P0/P1 followed by all survival delays, like QUA.
- Compact mode must be opt-in.  If its program cannot fit/load, error with instructions to choose the established chunked fallback.
- Do not modify scientific default production runners while validating the new program.

## Review Focus

- `opx_t1_compact_delay_loop=False` continues to use the chunked implementation and preserves its telemetry.
- 21 delays use one program and one P0/P1 pair per shot/frequency, rather than repeated references per chunk.
- Reverse-frequency shots still restore named delay columns and condition tags correctly.
- The full-return recovery barrier remains before any payload readout.
- A compact program reports a clear limit failure instead of silently executing the chunked order.

---

### Task 1: Compact-mode selection contract

**Files:**
- Modify: `WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/integration.py`
- Test: `tests/test_five_point_protocol.py`

**Interfaces:**
- Consumes: `acquire_t1_5pt_iq(..., _allow_chunking=True)`.
- Produces: `opx_t1_compact_delay_loop` in the run configuration and telemetry mode identifier.

- [ ] **Step 1: Write the failing test**

```python
def test_qick_compact_delay_mode_uses_one_program_for_twenty_one_delays(monkeypatch):
    # Patch the compact program and stream runner; assert one construction,
    # 23 records per DC, and compact order telemetry.
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_five_point_protocol.py::test_qick_compact_delay_mode_uses_one_program_for_twenty_one_delays -q`

Expected: FAIL because compact selection does not exist.

- [ ] **Step 3: Write minimal implementation**

Pass `opx_t1_compact_delay_loop` through `acquire_t1_5pt_iq`; select a dedicated compact program only when the flag is true.  Leave the current automatic three-delay chunking path unchanged when it is false.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_five_point_protocol.py::test_qick_compact_delay_mode_uses_one_program_for_twenty_one_delays -q`

Expected: PASS.

### Task 2: Runtime-delay program

**Files:**
- Modify: `WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/programs.py`
- Test: `tests/test_five_point_protocol.py`

**Interfaces:**
- Consumes: compact run configuration from Task 1.
- Produces: `OPXResetT1CompactNPointProgram`, a condition order matching the decoded 23-column output.

- [ ] **Step 1: Write the failing tests**

```python
def test_qick_compact_program_runtime_selector_has_one_payload_body():
    # Capture assembly calls and verify a 21-delay selector plus one runtime
    # payload path, rather than 21 unrolled payload paths.
    ...

def test_qick_compact_program_preserves_p0_p1_and_all_survival_tags():
    # Assert tags [0, 1, 2, ..., 22] in each forward block.
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_five_point_protocol.py -k 'compact_program' -q`

Expected: FAIL because the compact program does not exist.

- [ ] **Step 3: Write minimal implementation**

Use one loop counter and a static selector that loads the selected delay duration into a register.  Emit the common active-reset/flux/readout body once, using dynamic `sync(page, register)` to end the target hold.  Keep the full stateful return sequence and park-readout barrier.  Stream and tag each record, then `loopnz` over the survival axis.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_five_point_protocol.py -k 'compact_program' -q`

Expected: PASS.

### Task 3: Runner switch and safe hardware validation

**Files:**
- Modify: `WorkingProjects/TLS_Spectroscopy/Client_modules/Runners/Test.py`
- Test: `tests/test_five_point_protocol.py`

**Interfaces:**
- Consumes: `Q3_CAUSALITY_COMPACT=on` in the temporary causality runner.
- Produces: a small 11-frequency, 21-delay, 20-shot compact hardware test command; the full test requires an explicit environment setting.

- [ ] **Step 1: Write the failing test**

```python
def test_qick_causality_compact_mode_is_opt_in_and_marks_telemetry():
    plan = diagnostic().predistortion_causality_plan({"Q3_CAUSALITY_COMPACT": "on"})
    assert plan["compact_delay_loop"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_five_point_protocol.py::test_qick_causality_compact_mode_is_opt_in_and_marks_telemetry -q`

Expected: FAIL because the runner has no compact mode.

- [ ] **Step 3: Write minimal implementation**

Add only an explicit environment switch, console banner, telemetry, and program-size/load guard.  Do not change the existing `Q3_T1_SEQUENCE_AUDIT` default.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_five_point_protocol.py::test_qick_causality_compact_mode_is_opt_in_and_marks_telemetry -q`

Expected: PASS.

### Task 4: Full verification and measurement handoff

**Files:**
- Test: `tests/test_five_point_protocol.py`

- [ ] **Step 1: Run full suite**

Run: `python3 -m pytest tests/test_five_point_protocol.py -q`

Expected: PASS.

- [ ] **Step 2: Compile-check changed modules**

Run: `python3 -m py_compile WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/programs.py WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/integration.py WorkingProjects/TLS_Spectroscopy/Client_modules/Runners/Test.py`

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/programs.py \
  WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/integration.py \
  WorkingProjects/TLS_Spectroscopy/Client_modules/Runners/Test.py \
  tests/test_five_point_protocol.py docs/superpowers/plans/2026-09-19-q3-compact-21-delay-t1.md
git commit -m "Add compact q3 21-delay T1 program"
```

