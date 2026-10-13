# Refactor handoff — read this first

Branch: `qicklab_refactor` (from `bfc_code` @ 0f0a51f). Last updated 2026-10-13 (end of session 1, machine switch).
Claude Code session that produced this: https://claude.ai/code/session_01LV3mPq1wVnxztiZabqm3RY

## Goal (user's words, condensed)
Complete refactor of the QM_Team code base: dense and hard to follow; runner only works for one qubit
parameter set (new device = new parameter file, same experiment code); far too many comments; bookkeeping
scattered. Be terse, keep only what is needed, add a parameters/reference docs page with pedagogy in mind,
preserve existing functionality, atomic commits, old code recoverable from `bfc_code`, follow best practices.
Orchestrate with dynamic workflows dispatching Opus 5.5 agents; the orchestrator checks itself.

## Decisions already taken with the user (do not re-ask)
- Flatten to a top-level package `qicklab/` (hardware/core/experiments/analysis/runs/twpa) + `devices/` + `runners/` + `tests/` + `docs/`.
- Device files are Python dataclasses (`devices/CSTQ03.py`), not TOML.
- Lab-note comments move to `docs/` (device files may keep short dated inline history).
- ruff + pytest installed; `pyproject.toml` committed. Push target: `origin` (houcklab/HouckLab_QICK).

## Where things are
| What | Path |
|---|---|
| Design spec v3 (layout, migration map, Device/Session/PLAN API, invariants, verification ladder, commit plan) | `docs/dev/refactor-2026-10/design.md` |
| Phase-3a execution brief (the next step) | `docs/dev/refactor-2026-10/brief_3a.md` |
| Per-subsystem audits (symbols, cfg keys, dead code, lab notes, bugs) | `docs/dev/refactor-2026-10/audit/` |
| Design critiques that shaped v3 | `docs/dev/refactor-2026-10/critique_{user,eng}.md` |
| Open lab questions raised by the docs writers (for the user) | `docs/dev/refactor-2026-10/docs_open_questions.json` and `docs/devices/CSTQ03.md` "Open items" |
| Environment lock of the machine the golden was generated on | `docs/dev/refactor-2026-10/requirements-lock.txt` |
| Regression harness (acceptance test for every commit) | `tests/regression/` (README explains) |
| Symbol map + AST/binding equivalence checker for phase 3a | `tests/refactor/` (README explains) |
| Docs tree (written ahead of the code, describes the target API) | `docs/` |

## Commit log so far (all on `qicklab_refactor`)
1. `077e9c2` test(regression): harness v1 + golden
2. `e42007d` chore: pyproject
3. `e67c24d` docs: documentation tree (42 pages)
4. test(regression): harness v2 — display runs for real, save_data/save_config digests, synthetic boards A and B, per-(cls,path) budget, variant + multi-flag labels, frozen legacy runner fixture, qick version pin, recording cfg; golden regenerated ON THE LEGACY CODE
5. test(refactor): symbol map (593 entries, 52 files) + equivalence checker (AST modulo renames + free-name binding check + ledger)
6. docs(dev): this handoff + planning artifacts + CLAUDE.md pointer

Nothing under `WorkingProjects/` has been modified yet. The code refactor proper has NOT started.

## NEXT STEP: phase 3a-i
Follow `brief_3a.md` section "3a-i" exactly: `git mv` every legacy file to the path in `tests/refactor/symbol_map.py`
(kind=moved/renamed, phase=3a-i), rewrite imports to explicit ones, keep the listed aliases, no body edits,
write `tests/regression/driver_qicklab.py`, then verify:
```
python -m compileall -q qicklab devices runners tests
ruff check --select F qicklab runners tests
python -m tests.refactor.equivalence --phase 3a-i     # must report 0 failures
python -m pytest tests                                # golden A and B must match WITHOUT regeneration (~15 min)
```
Then 3a-ii (splits), 3a-iii (format), 3b (per-area cleanup with adversarial review), 5a/5b (Device/Session/
recipes/PLAN, delete legacy runner), 6 (parameter registry → generated parameters.md; reconcile docs), rewrite
CLAUDE.md/AGENTS.md/README, then the approved bug-fix commits. Full list and order: design.md "Commit plan".

Known gotchas for 3a (from the symbol-map agent): `runs/singleshot` needs `from datetime import datetime`
(the class) and `import os`; `runs/coherence` needs `import time`; `mSpecSliceFF` needs `curve_fit`;
`verify_ModifiedRamsey_timing._REPO_ROOT` uses `Path(__file__).parents[N]` and breaks after moving to
`tests/hardware/`. Three symbol placements deliberately differ from design.md (recorded in
`tests/refactor/README.md`): `transition_matrix_2state` → `analysis.rates`; `_stage_sweet_spot_search` and
`_choose_next_voltage` stay in `runs.auto_coherence`; `analysis/telegraph` is split into `hmm/rates/dwell/undriven`.

## Rules (non-negotiable)
- The golden (`tests/regression/golden_cstq03.json`) is regenerated ONLY with a written, per-label justification;
  refactor commits never change it (allowed: the documented dead-key allowlist in tests/regression/README.md).
- Bug fixes are separate commits, one per bug, after the user approves the list in design.md "Known bugs".
- Experiment class names, cfg key names, data paths (`outerFolder + path`, timestamp formats) are unchanged.
- No hardware access at import time; never regenerate the golden on a machine with a different qick version
  (the golden stores `qick.get_version()`; pin is `qick==0.2.334`).

## Setting up on a new machine (macOS / Linux / Windows)
```
git clone https://github.com/houcklab/HouckLab_QICK.git && cd HouckLab_QICK
git checkout qicklab_refactor
python3 -m venv .venv
source .venv/bin/activate                 # macOS/Linux        (Windows: .venv\Scripts\activate)
pip install -r docs/dev/refactor-2026-10/requirements-test.txt   # pinned, cross-platform, ~15 packages
python -m pytest tests                    # ~15 min; expect: all pass, 1 skipped (qicklab/ not yet present)
```
Python 3.13.5 was used; 3.11+ is required. `requirements-lock.txt` is the full Windows `pip freeze`, kept for
reference only — do not install it on macOS. The `.venv` is not in git. The committed `.env` holds a Windows
PYTHONPATH; pytest does not need it (`pyproject.toml` sets `pythonpath = ["."]`), and `python -m <module>`
from the repo root works everywhere. PyCharm users: mark the repo root as sources root.
The lab's RFSoC/yoko are never needed for the tests.

**Platform note on the golden.** The golden was captured on Windows. The tProc program hashes, cfg dicts and
yoko sequences are platform-independent, but the `data_digest` / `sets` fields hash floats rounded to 9
significant digits, so a different BLAS (Apple Accelerate vs MKL/OpenBLAS) can in rare cases flip a rounding
boundary. If the very first `pytest tests` on the new machine fails ONLY in `data_digest`/`sets` entries
(nothing in `cfg`, `hw`, `methods`, `yoko_writes`), that is a platform artifact, not a code change: BEFORE
moving any code, run `REGRESSION_UPDATE=1 python -m pytest tests/regression` on the untouched legacy tree,
commit the regenerated golden with the message "test(regression): regenerate golden on macOS (BLAS rounding)",
and run the suite twice more to confirm it is stable on that machine. Any diff in `cfg`, `hw` or `methods`
on an untouched tree means the environment is wrong (check `qick==0.2.334`, numpy/scipy versions).

## Resuming with Claude Code
Open the repo on the new machine, start Claude Code, and say: "Continue the qicklab refactor — read
docs/dev/refactor-2026-10/HANDOFF.md and proceed with phase 3a-i per brief_3a.md, using dynamic workflows
with Opus agents." The CLAUDE.md banner also points here. Memory from the previous machine is not required;
everything needed is in this directory.
