# Predistortion Production Cleanup Implementation Plan

> **For Codex:** Execute this plan task-by-task, running each verification before advancing.

**Goal:** Relocate and verify the temporary q3/q5 data, consolidate predistortion and five-point T1 work into generic production code, remove qubit-specific temporary files, and push the QICK and QUA production branches.

**Architecture:** The standard TLS spectroscopy runners own orchestration and configuration. Generic helpers own image tracking, saved-response refitting, correction composition, and multi-amplitude consensus fitting. Controller-specific experiment modules only compile and execute their native pulse programs. Data relocation is driven by a checksum manifest and refuses collisions or unknown layouts.

**Tech Stack:** Python, NumPy/SciPy, pytest, QICK tProc/DMem integration, QUA/QOP, Git, SMB-mounted NAS.

---

### Task 1: Relocate and verify measurement artifacts

**Files:**
- Create: `/Volumes/ourphoton/FluxTeam/Data/migration_manifests/2026-09-13_q3_q5_temp_roots_relocation.json`
- Remove after verification: `/Volumes/ourphoton/FluxTeam/Data/q3`
- Remove after verification: `/Volumes/ourphoton/FluxTeam/Data/q5`

1. Re-run the dry-run mapper and require 287 moves, 19 temporary/cache deletions, and zero collisions.
2. Hash every source and write the planned mapping to the audit manifest.
3. Move each artifact to the standard device/controller/date tree.
4. Hash every destination and require an exact match.
5. Delete only the explicitly classified temporary/cache files and remove empty temporary directories.
6. Verify both top-level temporary roots are absent and re-read the manifest successfully.

### Task 2: Productionize QICK correction discovery and residual composition

**Files:**
- Modify: `WorkingProjects/TLS_Spectroscopy/Client_modules/Helpers/flux_predistortion.py`
- Modify: `WorkingProjects/TLS_Spectroscopy/Client_modules/Helpers/saved_step_response_refit.py`
- Modify: `WorkingProjects/TLS_Spectroscopy/Client_modules/Runners/TLSSpectroscopy.py`
- Modify/Create: generic tests under `tests/`

1. Add failing tests for discovering any supported compensation filename while rejecting unsupported methods and mismatched provenance.
2. Add failing tests for regular step 3b residual composition controls and composed-output selection.
3. Move reusable saved-response verification/composition logic out of q3 runners into the helper.
4. Generalize recursive discovery without weakening metadata validation.
5. Wire the regular pipeline to optional damped residual composition.
6. Run the targeted tests.

### Task 3: Productionize QUA multi-amplitude fitting and discovery

**Files:**
- Create: `LabCode/Helpers/multi_amplitude_predistortion.py`
- Modify: `LabCode/Control/Flux_Tunable/flux_predistortion.py`
- Modify: `LabCode/Control/Flux_Tunable/TLSSpectroscopy.py`
- Create/Modify: generic tests under `tests/`

1. Add failing controller-neutral tests for trace normalization, consensus, segment edges, bounded adjustment fitting, and residual metrics.
2. Extract the reusable algorithm from the q5 runner and parameterize all device values.
3. Generalize correction discovery to supported compensation methods and preserve strict match checks.
4. Confirm regular step 3a/3b uses the shared image tracker and residual composition controls.
5. Run the targeted tests.

### Task 4: Integrate the matched five-point protocol on QICK

**Files:**
- Create: `WorkingProjects/TLS_Spectroscopy/Client_modules/Experiments/five_point_t1.py`
- Create: `WorkingProjects/TLS_Spectroscopy/Client_modules/Runners/FivePointApplesToApples.py`
- Modify: `WorkingProjects/TLS_Spectroscopy/Client_modules/Experiments/mT1VsFlux.py`
- Modify: `WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/integration.py`
- Modify: `WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/programs.py`
- Create: generic five-point tests under `tests/`

1. Add failing tests for `[10, 50, 200]` microsecond delays, 180 shots, active reset, condition order, DMem sizing, bidirectional frequency mapping, and uncertainty output.
2. Transfer the existing local five-point implementation into the current deploy worktree.
3. Replace obsolete `[30, 100, 300]` defaults and remove device-specific assumptions.
4. Run the targeted tests.

### Task 5: Integrate the matched five-point protocol on QUA

**Files:**
- Create: `LabCode/Experiments/Flux_Sweeps/five_point_t1.py`
- Create: `LabCode/Control/Flux_Tunable/FivePointApplesToApples.py`
- Modify: `LabCode/Experiments/Flux_Sweeps/m_swap_spec_vs_flux.py`
- Create: generic five-point tests under `tests/`

1. Add failing tests for the matched delays, shot budget, active reset, condition order, bidirectional mapping, precompiled execution, and failure-resilient saving.
2. Transfer the existing local implementation into the current deploy worktree.
3. Replace obsolete defaults and align output fields with QICK.
4. Run the targeted tests.

### Task 6: Remove temporary code and preserve generic coverage

**Files:**
- Delete: tracked `Q3Predistortion*.py` and `Q5Predistortion*.py`
- Delete/replace: qubit-specific predistortion tests
- Delete locally: untracked q5 diagnostic scripts listed in the approved inventory

1. Confirm every reusable function has a generic production home and generic test.
2. Remove tracked qubit-specific runners and tests.
3. Remove only the listed untracked q5 diagnostic scripts from the local checkout.
4. Search both repositories and the relocated data for stale executable copies or production imports.

### Task 7: Full verification and code review

**Files:** all changed production and test files.

1. Run full pytest suites appropriate to both repositories.
2. Run targeted `compileall` checks.
3. Inspect git diffs and confirm unrelated local files are untouched.
4. Request independent code review for QICK and QUA diffs.
5. Address review findings and rerun affected tests.

### Task 8: Commit, push, and hand off measurement-PC commands

1. Commit the QICK production cleanup and push it to `origin/tls-spectroscopy`.
2. Commit the QUA production cleanup and push it to `origin/marty-branch`.
3. Verify both remote branch SHAs.
4. Provide exact Git Bash commands for each measurement PC to remove untracked temporary files, fast-forward, verify imports/defaults, and show remaining unrelated status.
