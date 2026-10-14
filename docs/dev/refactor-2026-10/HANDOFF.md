# Refactor handoff — read this first

Branch: `qicklab_refactor` (from `bfc_code` @ 0f0a51f). Last updated 2026-10-14 (session 2, applying research-review findings; F09, F00, F08, F01, F06, F11, F22, F13, F28, F23, F15, F18, F17 landed).
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
7. `650b0250` docs(dev): macOS test environment — exact pins install on Homebrew Python 3.13.2 arm64
   (`requirements-macos.txt`); the only mismatch was `python3` = miniforge 3.9
8. `9b8540ba` test(regression): golden regenerated on macOS on the untouched legacy tree (platform note
   applied: 804 fit-output diffs in 15 labels, incl. the `pulse_freq` carry-over in the two transmission
   multi-flag labels; three captures byte-identical; 106 passed). Session 2:
   https://claude.ai/code/session_01Si1tqwikwVWbWUzWwbxDCY

9. `5dc9e120` refactor: 3a-i — every whole-file row git-mv'd into `qicklab/`, explicit imports, renames +
   aliases, `driver_qicklab` is the DRIVER, `tests/test_imports.py`; equivalence `--phase 3a-i` PASS
   (341 AST / 341 bindings), pytest 147 passed, golden byte-identical. Harness fixes in the same commit:
   the golden fixture undoes the capture patches at module teardown (they leaked `savefig` no-ops into
   later test modules), `CURRENT_PHASE` in `tests/refactor/test_equivalence.py`, checker self-test runs on
   a copy of the legacy worktree, transitional ruff per-file ignores in `pyproject.toml` (3b removes them).

10. `b87f4dd0` refactor: 3a-ii — the twelve remaining files split into 32 destination modules per the map,
    `WorkingProjects/` deleted, consumers retargeted, driver clock loop removed, `CURRENT_PHASE = "3a-ii"`;
    equivalence strict + phase-less PASS (505 AST / 505 bindings), pytest 170 passed, golden byte-identical.
11. `bd2d85ec` style: 3a-iii — `ruff format` + isort only (listed in `.git-blame-ignore-revs`); equivalence
    PASS, pytest 170 passed, golden byte-identical.

12. `a3924c28` refactor(hardware) — area 1 (+ the equivalence gate enters 3b: structural only, pending deletions allowed)
13. `62e3a660` refactor(core) — area 2 (pure `data_paths()`, dead go/load_data, comments)
14. `3b405ba4` test(refactor): 3b gate follows `final_module`; synthhd import allowlist
15. `98f70b8c` refactor(analysis) — area 3 (min_q_range_phase, fit_exp_decay, fit_rabi_cosine, spec Lorentzians,
    hist_process(normalize=...) merge, classify_thermal_tail, dead code, verified identical-result improvements)
16. `791d395c` refactor(twpa) — area 7 (hardware/pnax.py, hardware/synthhd.py, yoko ramp_current, twpa/common.py;
    all five scripts kept)
17. `07f9900d` refactor(experiments) — area 4, basic experiments (rotate_iq deleted, `if True:` flattened, comments,
    verified identical-result improvements)
18. `742d357e` refactor(experiments) — area 5, advanced (single_shot ~550 dead lines + readout_optimize *_Higher*
    classes deleted; ModifiedRamsey's readout window / active reset / schedule ledger are core/readout.py,
    core/active_reset.py (ActiveResetMixin), core/schedule.py; ARV/SingleShot/Undriven keep their own copies)
19. `818a782a` refactor(runs) — area 6 (analysis.iq.kmeans_split, analysis/plotting.py, core/io.py,
    auto_coherence merges into yoko.ramp_to / spectroscopy.find_two_tone_peaks)
20. 3b-done: `CURRENT_PHASE = "3b-done"` — the structural gate is strict again (every 3b deletion/merge done)
Each 3b area commit: full pytest 170 passed on an isolated snapshot worktree, golden byte-identical,
adversarial old-vs-new review (reject → fix → approve where needed). Workflow script per area:
`~/.claude/projects/.../workflows/scripts/qicklab-3b-area-*.js` (cleanup agent, reviewer, fix loop, args =
area brief). User decisions 2026-10-13: functionality-preserving improvements are applied inside 3b
commits with a proof of identical results (reviewer re-verifies); behaviour-changing improvements and the
known bugs become a separate phase of individual commits after 3b (user: "make these improvements as you
see fit"), preceded by a research-effectiveness review workflow (one Opus agent per measurement domain).

21. `0cf3b82c` docs(dev): research-effectiveness review (85 verified findings; `docs/dev/refactor-2026-10/review/`)
22. `2a21c17f` fix(active_reset_verify): F09 — ARV runs the shared reset block (golden: 16 hw leaves, ARV reset-ON)
23. `578518d2` fix(active_reset): F00 — stall for the read latency before the reset read (golden: 32 hw + 50
    cfg_access leaves, reset-ON MR/ARV programs; needs the documented hardware validation)
24. `70aebbec` fix(runs): F08 — finish() helper saves the record even when display() raises (golden: 0 leaves)
25. `5ba679cb` fix(ramsey): F01 (+F12, T2R guard, F67) — principal-axis projection, sampling bounds, guarded
    display (golden: 660 leaves, all T2R display `sets` in 4 labels; the 5 per-board raised displays now fit)

26. `aefb2214` fix(hmm): F06 — i.i.d.-null likelihood-ratio gate and resolved-rate gate (golden: 0 leaves)

27. `8436b708` fix(runs): F11 — T1-SS calibration in its own cfg (golden: 56 RunT1SS leaves, dead keys gone)
28. `c65810e8` fix(active_reset): F22 — res_phase wrapped mod 2^b_phase (golden: 0 leaves)
29. `36344a3c` fix(fitting): F13 — one FFT-seeded Nyquist-bounded Rabi fit (golden: 0 leaves)

30. `c46424ce` fix(runs): F28 — yoko_fixed charge sweeps record the held bias + repeat axis (golden: new label
    RunChargeSweep[yoko_fixed], 0 leaves elsewhere)
31. `8164e138` fix(t2_echo): F23 — even/zero num_pi_pulses rejected (golden: 0 leaves)

32. `0d9f4437` fix(runs): F15 — MR validation controls acquired regardless of the analysis flag (golden: 394
    leaves, the new control experiments in RunModifiedRamsey[*])
33. `94f6a24e` fix(acquisition): F18 — strobe blocks compile reps_per_block (golden: 4 hw leaves, ZSP[validate])
34. `736c8fac` fix(zero_span): F17 — event-based baseline rate, iterated burst exclusion (golden: 0 leaves)

## STATE OF THE WORKING TREE (session 2 continues, 2026-10-14)
Commits above are verified. The WORKING TREE holds UNCOMMITTED, in-progress edits from parallel fix agents
(each on disjoint files); none of it is verified by the full suite until landed:
- In flight (agents running or awaiting landing): F10 (analysis/readout.py classify_thermal_tail +
  experiments/single_shot.py thermal branch; re-review running), F04 (analysis/spectroscopy.py + experiments/qubit_spec.py +
  one line in runs/zero_span.py), F13 (analysis/fitting.py Rabi fit + experiments/rabi.py + runs/__init__.py
  alias), F11 (runs/single_shot.py run_t1_ss), F15 (runs/modified_ramsey.py controls always acquired),
  F17 (analysis/zero_span.py baseline rate), F03 (runs/resonator.py carry-over from the display fit),
  F21+F53 (hardware/yoko.py safety helpers, twpa/set_bias.py, twpa/flux_sweep.py, core/context.py,
  capture.py FakeYoko), F23 (experiments/t2_echo.py even-n ValueError), F22 (runs/active_reset.py res_phase
  wrap), F28 (runs/charge_sweep.py yoko_fixed metadata + RunChargeSweep[yoko_fixed] label), F18
  (core/acquisition.py modulated_strobe_acquire reps_per_block + runs/zero_span_validation.py).
  Their agent reports are in the workflow journals under `~/.claude/projects/.../subagents/workflows/`.
  To resume: for each, inspect `git diff HEAD -- <its files>`, re-run an adversarial review (the
  `qicklab-rereview` workflow script) if its journal shows no final approve, then land one at a time with
  path/hunk-filtered snapshots (see the pipeline notes above; `hunk_filter.py --invert` separates shared
  files such as runs/zero_span.py). If the tree is too tangled, `git stash` everything and re-apply the
  findings one by one from `review/findings.json`.
- After these: the remaining findings (F02 parts 2/4, F05, F07, F14+F20+F24+F27 readout window,
  F16, F18, F19, F22, F25, F26, F28, then tier B), the dead-cfg-key commit, then phases 5a, 5b, 6, the
  CLAUDE.md/AGENTS.md/README rewrite, and the merge back into `bfc_code` (+ the Windows golden check).

Fix pipeline: `~/.cache/qicklab-refactor/apply_findings` workflow script (implementer → adversarial reviewer →
fix, 3 review rounds), `diff_labels.py` (capture labels, classify leaf diffs vs the golden), `land_fix.sh` /
hunk-filtered snapshots into `~/.cache/qicklab-refactor/wt_<id>` + `REGRESSION_UPDATE=1` full suite +
`classify_golden.py`, then commit from the worktree and `git reset --soft` the branch. In flight at last
update: F01 (Ramsey projection/bounds), F06 (HMM i.i.d. null gate), F10 (thermal population estimator),
F04 (parity-doublet selection), F13 (Rabi fit). Remaining items: `review/findings.json` (by id).

The repo now IS the qicklab package: `qicklab/`, `devices/` (empty init), `runners/CSTQ03_BFC.py` (legacy
runner, star-imports `qicklab.runs`, deleted in 5b), `tests/`, `docs/`. The lab code runs on the original
Windows PC in the end (user, 2026-10-13): keep Windows-only lines (DLL directory, `.env`, `Z:\` roots) and
the TWPA modules (`qicklab/twpa/*`, needed; `pywindfreak` is an optional extra, not a reason to drop them).

## NEXT STEP: research-effectiveness review → individual bug/improvement commits, then phase 5a
Phase 3b is complete (areas 1-7). Running/next: the read-only research review workflow (seven domain
reviewers + a refuter per tier-A/B finding; script `qicklab-research-review-*.js`), then one commit per
accepted finding (bug fixes incl. design.md "Known bugs", low-risk effectiveness improvements; each with
the golden regenerated and the diff classified per label in the commit message; tier C = methodology
changes needing the fridge go to docs as proposals), the dead-cfg-key commit (`pulse_style`, `ts` keys,
ConstantTwoTone debug prints) with its allowlist, then 5a (Device/Session/recipes/PLAN + devices/CSTQ03.py +
runners/CSTQ03_session.py), 5b, 6, docs rewrite, merge back.

## Phase 3b plan as executed (one commit per area, adversarial old-vs-new review each)
Areas in order (shared helpers first): 1 hardware, 2 core, 3 analysis helpers (+ switch callers), 4 experiments
basic, 5 experiments advanced (single_shot / readout_optimize deletions, MR dedupe into core/readout,
core/active_reset, core/schedule only where the audit proved identical math), 6 runs (dedupe KMeans/plot/save
into analysis.iq / analysis.plotting / core.io), 7 twpa (common.py, hardware/pnax.py, hardware/synthhd.py;
all five TWPA scripts stay). Sources: design.md migration-map "phase-3b cleanup notes" + comment policy,
the 3b rows of the symbol map (deleted with audit citation / merged with proof), the audits' "Lab notes to
migrate" tables (the docs tree already holds most notes: verify on the named page, add if missing, delete
the comment). Decision 2026-10-13: dead cfg keys (`pulse_style`, `ts`) are NOT dropped in 3b — that is a
later dedicated commit with an allowlist + golden regeneration — so every 3b commit keeps the golden
byte-identical. Ladder per area: compileall, ruff --select F (shrink the transitional per-file ignores in
`pyproject.toml` as the legacy bodies go), equivalence `--phase 3b` (structural: deleted symbols gone,
merge targets present), full pytest with the golden unchanged.
Then 3a-iii is done; 3a-iii (format), 3b (per-area cleanup with adversarial review), 5a/5b (Device/Session/
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

## Environment mismatch policy (added 2026-10-13, session 2 start on macOS)
If the exact pins in `requirements-test.txt` cannot be installed (no wheel for the Mac's Python/arch), do NOT
fight it: install the nearest available versions, but keep `qick==0.2.334` if at all possible (it is pure
Python; install from PyPI or `pip install qick==0.2.334 --no-deps` then the deps separately). Record the
actual versions in `docs/dev/refactor-2026-10/requirements-macos.txt`. Then run the suite on the UNTOUCHED
legacy tree: diffs only in `data_digest`/`sets` → regenerate the golden on the legacy tree (platform note
above) and commit it; diffs in `cfg`/`hw`/`methods` with a different qick version → the harness `__meta__`
check will fail by design; if qick 0.2.334 truly cannot be installed, regenerate the golden on the legacy
tree with the new qick version, commit it with the version in the message, and note that program hashes are
now relative to that version. Either way the golden must be stable (two identical captures) BEFORE phase 3a-i.

## End state: merge back into `bfc_code` (user decision 2026-10-13)
When the whole plan is done and the verification ladder is green, unify the code base: `bfc_code` has not
moved since 0f0a51f, so `git checkout bfc_code && git merge --ff-only qicklab_refactor` keeps history linear
with every atomic commit individually revertable (`git revert <sha>`), then `git push origin bfc_code`. If
`bfc_code` HAS moved in the meantime, rebase `qicklab_refactor` onto it first (resolve conflicts, rerun the
full ladder), then fast-forward. Show the user the commit list and the final test summary before merging.

## Resuming with Claude Code
Open the repo on the new machine, start Claude Code, and say: "Continue the qicklab refactor — read
docs/dev/refactor-2026-10/HANDOFF.md and proceed with phase 3a-i per brief_3a.md, using dynamic workflows
with Opus agents." The CLAUDE.md banner also points here. Memory from the previous machine is not required;
everything needed is in this directory.
