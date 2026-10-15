# Refactor handoff — read this first

Branch: `qicklab_refactor` (from `bfc_code` @ 0f0a51f). Last updated 2026-10-14 (END of session 2 on macOS: 18 research-review findings landed; eight more are
parked, unlanded, on branch `qicklab_refactor_wip`; see TRANSFER STATE below).
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

35. `2859f222` fix(readout): F10 — thermal-mode population by a two-cloud EM fit (golden: 0 leaves)
36. `8fdde7ca` fix(runs): F03 — transmission_fit carries the display fit's minimum (golden: 24 leaves, the
    two transmission carry-over labels' downstream pulse_freq/program/config digests)

37. `4ecf0ba1` fix(rabi): F26 — rotation from the analysed read, fixed sign, contrast diagnostic (golden: 88
    data_digest leaves in the four Rabi labels)

Session 3 (Windows PC, 2026-10-14; https://claude.ai/code/session_013hKCT9KZpyGQ3BqMAGCkXk):
38. `4716ed29` test(regression): golden regenerated on Windows (i7-11700F, scipy-openblas 0.3.30, numpy 2.4.1):
    1064 leaves, sets 716 + data_digest 348 in 16 labels per board, nothing else; two further captures
    byte-identical (sha1 ea536087…)
39. `20c0c602` fix(yoko): F21+F53 — open_charge_yoko / enable_current_output_safely / two-sided ramp_to guard
    with readback (golden: 838 leaves, all yoko_writes, every label on both boards)
40. `12ff8a8c` fix(spectroscopy): F04 — doublet selection (min_sep in every branch, window clip, seed/edge/
    duplicate/quarter-step gates, min_sep hand-off + provenance keys in ZSP cfg) (golden: 304 leaves = lorentz_*
    data_digest in 6 labels + 2 ZSP cfg keys and cfg_digest in RunZeroSpanParity[*]); four Opus review rounds here
    (one reject: the first sub-grid gate at 0.5 step dropped real lines; now 0.25). DEFERRED: partner significance
    gate (F04 (c) second half): below SNR ~15 on the ZSP grid a single line is often paired with a noise maximum
    (source one_lorentzian_center_plus_peak) and the run parks between the parity lines without error; needs a
    partner-height-over-noise threshold (design decision + golden change).
41. `f7f590b0` fix(coherence): F02+F34 — bounded, guarded fit_exp_decay (dict result, ok criteria incl.
    |a| >= 3 a_err) saved as t1_fit_* / t2e_fit_* in the h5 (golden: 684 leaves = new display `sets` + new fit
    datasets in the 7 T1/T2E labels; nothing else). Not done: T2R fit saving, T1/T2E in the AutoCoherence summary.
42. `56765a26` fix(zero_span): F19 — stage-8 controls: gain restore, rebuilds (base rebuild in a finally),
    stitched 200 ms records, batch-means se + Welch/Student-t thresholds, both_branches_respond / branch_ratio /
    complementarity / midpoint null, variants table in EVIDENCE.md (golden: 24 hw/count leaves, ZSP[validate] only);
    three Opus rounds. FOLLOW-UPS: stages 1-2 set_qubit_gain(base) sits after the _preserve_cfg block, not in a
    finally; se_batch_us (10 ms) is not tied to the measured dwell (se ~2x too small at a 30 ms dwell);
    min_record_us / se_batch_us / k_sigma are not exposed in Control_params; control C has no decision statistic.
43. `ab896b28` fix(transmission): F25 — hanger_fit_kappa_tot_mhz / _ext_mhz = |f0|/Q in MHz replace the 1e6-too-small
    external-only key; four stale docs pages fixed (golden: 24 data_digest leaves, the 4 RunTransmissionSweep* labels).
    Follow-ups: docs/adding_a_device.md:100 "6/kappa" should name the angular kappa; the Q lower bound 1e2 caps
    kappa at |f0|/100 on a small IF axis (pre-existing).
44. `ea8999b0` fix(modified_ramsey): F16 — model-free lag-covariance statistic (interior-trimmed, baseline-band
    corrected, block bootstrap) drives echo_null / flip_final_pi2 / drive_off verdicts; drive_off decisive with a
    symmetric 0.1 rule (golden byte-identical: no label runs the analysis). Four Opus rounds here, three rejects
    (NaN-error flip rule, drift-filter edge bias, interior bias at CSTQ03 contrast). TIER C left: add drive_off to
    the default validation_controls and confirm the 0.1 budget on the fridge; the per-record lag sum is not in
    _analysis.json; K is per record (a control with a slightly different rep period can lose the comparison).
45. `b0430ae6` fix(single_shot): F48 — T1_SS and the Undriven charge sweep save the completed points on abort
    (sweep_completed / points_completed + cfg aborted) and retry the shot-counter race (golden byte-identical).
46. `206734b4` fix(readout_optimize): F33 — qubit-pulse map brackets each gain row with shared |g> blocks (463
    programs instead of 882), g_ref_index / g_block_time / g_drift_* saved, gated drift warning (golden: 48 leaves,
    SingleShot_QubitOptimize hw counts + fid/overlap digests + the four new keys).
47. `914e45f9` fix(spectroscopy): F05 part 1 — partner significance gate (MIN_PARTNER_SNR 5, edge baseline,
    parity_partner_snr provenance, min_partner_snr overrides), estimate_noise_floor dedupe; three gate-off harness
    labels keep the ZSP pipeline and the two-tone quasi-CW record under the golden (43 labels per board) (golden:
    114 leaves in the plain ZSP / two-tone labels, which now raise / step to budget on the noise-only harness
    spectra). Not done: F05 part 2 (joint 1-vs-2 line fit, tier B) and AutoCoherence |I+iQ|^2 -> project_iq_signal.
ALL EIGHT PARKED ITEMS ARE LANDED (39-46). `qicklab_refactor_wip` is deleted; the per-item table in TRANSFER STATE is
historical. Pushed to origin after 46.

## TRANSFER STATE (2026-10-14, end of macOS session 2) — READ THIS BEFORE ANYTHING ELSE
The macOS machine is being left; the next machine is a Windows PC that is NOT the final lab PC (the lab PC
is where the code runs in the end; see "End state"). Everything needed is in git, nothing on the Mac.

**Branches (both pushed to `origin`):**
- `qicklab_refactor` — 44 verified commits since `eecd7f98` (every one passed the full ladder; golden
  byte-identical except the per-commit allowlists written in each commit message). Head = this HANDOFF commit.
- `qicklab_refactor_wip` = `qicklab_refactor` + two UNVERIFIED commits holding the working tree of the
  eight in-flight findings when the session was cut:
  1. "wip: reviewed, unlanded fixes F04 F21+F53 F16 F02+F34 F19 F25" — agent-complete edits (plus their new
     tests and docs). Quick ladder on this tree passed (compileall, `ruff --select F`, `ruff format --check`,
     and all tests except the golden suite); the GOLDEN SUITE WAS NOT RUN on it and the golden is unchanged, so
     `pytest tests/test_golden.py` is expected to fail there until each item is landed with its golden regen.
  2. "wip: interrupted implementers F33 F48 (partial, unreviewed)" — the implementer agents were stopped
     mid-work. Treat as a starting point only: either finish+review them or `git revert` that commit and
     relaunch the two items from `review/findings_with_refuter_notes.json`.
  Never merge `qicklab_refactor_wip` as-is. Land items one at a time onto `qicklab_refactor` (procedure
  below), then delete the wip branch.

**Per-item status** (agent reports and the last reviewer verdict for each are in
`review/inflight/<ID>.json`: `status`, `last_report`, `last_review.findings`):
| ID | Files (from `git diff qicklab_refactor qicklab_refactor_wip`) | State at cut | Expected golden impact |
|---|---|---|---|
| F04 doublet selection | analysis/spectroscopy.py, experiments/qubit_spec.py, runs/zero_span.py (one `min_sep_mhz=` line), tests/test_doublet_selection.py, docs two_tone_spec.md | refix done, re-review round 2 interrupted; 2 open should-fix (tests for the two_highest_peaks min_sep rule and for the zero_span `min_sep_mhz` plumbing) | only RunSpecGainLengthSweep (`experiments[1]` lorentz_* 0→1 length); ZSP labels unchanged |
| F21+F53 yoko safety | hardware/yoko.py, twpa/set_bias.py, twpa/flux_sweep.py, core/context.py, tests/regression/capture.py (FakeYoko), tests/test_yoko_safety.py, docs hardware.md/twpa.md/architecture.md/troubleshooting.md/charge_sweep.md/undriven_single_shot.md/charge_transmission_sweep.md, tests/regression/README.md, comment line in experiments/undriven_single_shot.py | three review rounds, all approve; 2 should-fix left (report hygiene; "all 40 labels change in yoko_writes" which IS the intended impact) | `yoko_writes` on every label (new state queries, LEV 0 before OUTP ON, LEV? readback per ramp_to); nothing in cfg/hw/data. `TWPA_YOKO_ADDRESS` moved into hardware.yoko: add a `final_module` row in tests/refactor/symbol_map.py or a re-export, or test_equivalence fails |
| F16 parity-control verdicts | analysis/modified_ramsey.py (compare_parity_controls), tests/test_modified_ramsey_offline.py, docs modified_ramsey.md (+ new docs/experiments/modified_ramsey_control.md if present) | fix round 1 done, unreviewed; 3 should-fix from review 1 (echo_null resolved-rate gate precedence, Hessian-only errors in the flip-rate agreement test, drive_off threshold vs CSTQ03 numbers) | none expected (offline analysis) — verify with diff_labels on RunModifiedRamsey[*] |
| F02+F34 T1/T2E fit guard | analysis/fitting.py (fit_exp_decay), experiments/t1.py, t2_echo.py, tests/test_exp_decay_fit.py, docs t1.md/t2_echo.md/auto_coherence.md/coherence_combos.md/interleaved_coherence.md/running_a_session.md | implementer done, review 1 interrupted → run the rereview workflow | T1/T2E labels: fit outputs (`sets`/data_digest) and possibly new saved keys; see last_report |
| F19 ZSP validation stage 8 + B2-B4 | runs/zero_span_validation.py, analysis/zero_span_checks.py, tests/test_zero_span_validation.py, docs zero_span_parity.md (validation sections only) | implementer done, review 1 interrupted → rereview | ZSP[validate] label only, per last_report |
| F25 kappa units | experiments/transmission.py, runs/resonator.py print, tests/test_transmission_kappa.py, docs transmission_fit.md/transmission_sweep.md | review 1 rejected (1 must-fix: four docs pages incl. docs/devices/CSTQ03.md still say the kappa printout is 1e6 too small); fix round interrupted → finish the docs fix, then rereview | none in data; print text only (methods/cfg unaffected) — verify |
| F33 g-reference bracketing | experiments/readout_optimize.py (+ docs qubit_optimize.md) | implementer interrupted (partial) | SingleShot_QubitOptimize only: n_programs 882→483, hw digest, fid_mat/overlap_mat |
| F48 partial save on abort | experiments/undriven_single_shot.py, t1_single_shot.py, tests/test_partial_save.py, docs averaging.md/t1_single_shot.md/undriven_single_shot.md | implementer interrupted (partial; the test file exists) | none on the success path |

Shared files touched by more than one item: experiments/undriven_single_shot.py (F21 one comment line +
F48), docs/experiments/undriven_single_shot.md (F21 + F48), docs/architecture.md, docs/troubleshooting.md
(F21 + others). Use `tools/hunk_filter.py [--invert] <regex> <files>` to split them at landing time.

**Landing procedure on the next machine (per item, one commit each):**
1. Environment: Python 3.13 (`py -3.13 -m venv .venv`, `.venv\Scripts\activate`), `pip install -r
   docs/dev/refactor-2026-10/requirements-test.txt` (exact pins; on macOS the same pins installed cleanly with
   Python 3.13.2 — see requirements-macos.txt). Then on a CLEAN `qicklab_refactor` checkout run
   `python -m pytest tests` (~11 min on the Mac). The golden (`tests/regression/golden_cstq03.json`) was
   regenerated on macOS (commit 9b8540ba): a Windows BLAS can flip float roundings, so if the first run fails
   ONLY in `data_digest`/`sets` leaves, regenerate ONCE at the branch head (`REGRESSION_UPDATE=1 python -m
   pytest tests`, confirm two further captures byte-identical, classify with `tools/classify_golden.py`,
   commit as "test(regression): regenerate golden on Windows (<CPU/BLAS>, numpy x.y)" listing the leaf
   classes). Any diff in `cfg`/`hw`/`methods`/`yoko_writes` on the clean head = wrong environment (check
   `qick==0.2.334`, numpy/scipy pins): fix the environment, never the golden. Do not land anything until the
   suite is green and stable.
2. Bring one item's files over: `git checkout qicklab_refactor_wip -- <its files>` (or `git diff
   qicklab_refactor qicklab_refactor_wip -- <files> | git apply`; hunk-filter the shared files). New files:
   same command. Check `git diff --stat` shows only that item.
3. If its `review/inflight/<ID>.json` status is not "approved, no open findings": run the rereview workflow
   (`tools/workflow_rereview.js`, args `{id, item (the finding JSON from review/findings_with_refuter_notes.json),
   files, context}`) or the apply-findings fix loop, then address what it returns. Claude Code's Workflow tool
   accepts `scriptPath` for files inside the repo; the scripts' RULES text still names the Mac repo path and
   `source .venv/bin/activate` — edit those two strings for Windows before use.
4. Fast ladder: `python -m compileall -q qicklab devices runners tests`; `ruff check --select F qicklab
   runners tests devices`; `ruff format --check qicklab devices runners tests`; the item's tests;
   `python docs/dev/refactor-2026-10/tools/diff_labels.py <labels> --variants A` (every differing leaf must be
   explained by the item).
5. Full suite with golden regen: `REGRESSION_UPDATE=1 python -m pytest tests -p no:cacheprovider`
   (`tools/land_fix.sh <tag> [paths]` does 2+4+5 in a scratch worktree under Git Bash; set `QICKLAB_SCRATCH`;
   on plain PowerShell run the steps by hand). CHECK THE EXIT CODE before committing. Classify:
   `python tools/classify_golden.py <(git show HEAD:tests/regression/golden_cstq03.json)
   tests/regression/golden_cstq03.json` and write every leaf class per label into the commit message.
6. Prune `[tool.ruff.lint.per-file-ignores]` with `tools/prune_ignores.py` if the item removed a trigger.
   Commit (`fix(<area>): <ID> ...`, with the Claude-Session trailer of the session doing the work), then append
   the commit to the log below and refresh "NEXT STEP".

**After the eight parked items:** remaining tier A: F05 (unify peak finding), F07 (ZSP apriori classifier;
needs F04 landed), F14+F20+F24+F27 (regime-A readout window → `cover_readout_window` in all programs); then
tier B (F29–F84, group tiny ones thematically; F46 provenance touches many files — do it when nothing else is
in flight); the dead-cfg-key commit (`pulse_style`, `ts`, ConstantTwoTone debug prints; allowlist + golden
regen); then phases 5a (Device/Session/recipes/PLAN + devices/CSTQ03.py + runners/CSTQ03_session.py; inputs:
design.md phase-5 section and findings F57/F58/F46/F49/F50/F51/F56), 5b (delete runners/CSTQ03_BFC.py and
driver_legacy), 6 (parameter registry + generated docs/parameters.md, reconcile docs with the real API), the
CLAUDE.md/AGENTS.md/README rewrite, then "End state" below. Tier C (needs the fridge) stays documented only
(`review/tier_c_and_gaps.json`).

**Tools now live in the repo** (`docs/dev/refactor-2026-10/tools/`): `diff_labels.py`, `classify_golden.py`,
`hunk_filter.py`, `prune_ignores.py`, `land_fix.sh`, and the three workflow scripts
(`workflow_apply_findings.js`: implementer → adversarial reviewer → fix, args `{"items":[finding,...]}` with an
optional `extra_instructions` string per finding; `workflow_rereview.js`; `workflow_3b_area.js`, historical).
`review/findings_with_refuter_notes.json` is `findings.json` plus each item's refuter notes/reasoning — use it
as the Workflow args source. The regression README lists the 40 labels.

The repo IS the qicklab package: `qicklab/`, `devices/` (empty init), `runners/CSTQ03_BFC.py` (legacy runner,
star-imports `qicklab.runs`, deleted in 5b), `tests/`, `docs/`. The lab code runs on the original Windows PC
in the end (user, 2026-10-13): keep Windows-only lines (DLL directory, `.env`, `Z:\` roots) and the TWPA
modules (`qicklab/twpa/*`, needed; `pywindfreak` is an optional extra, not a reason to drop them).

## NEXT STEP: remaining tier-A findings, then tier B, dead-cfg-key commit, 5a, 5b, 6, docs rewrite, merge back
The eight parked items are landed (session 3, this Windows PC). Procedure per item is unchanged (apply-findings or
rereview workflow with Opus agents, fast ladder, ONE full-suite golden regeneration at a time, classify, commit with
every leaf class in the message, handoff line). Order: F05 (what is left of its part (1): the partner significance
gate deferred from F04, estimate_noise_floor dedupe in auto_coherence/_spec_peak_snr and zero_span_checks; the
tier-B joint two-Lorentzian fit is a later item), F07 (GMM-threshold ZSP classifier as the new default; F04 landed),
F14+F20+F24+F27 (cover_readout_window in every regime-A program + ro_ch in ZSP; large golden change: hw digests of
every regime-A label and ZSP; do it when nothing else is in flight), then tier B (F29-F84, group tiny ones; F46
provenance touches many files), the dead-cfg-key commit, 5a, 5b, 6, docs rewrite, merge back (End state).
Open follow-ups recorded in items 40, 42, 43, 44 above (F04 significance gate = F05; F19 stages 1-2 finally /
se_batch_us; F25 adding_a_device.md; F16 tier C).

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
python -m pytest tests                    # ~11-15 min; expect: all pass (platform note below)
```
Python 3.13.5 was used; 3.11+ is required. Windows PC (session 3): the `py` launcher only had 3.8/3.9, so
`winget install --id Python.Python.3.13 --scope user` was used (3.13.15); the pins installed cleanly. That PC has
16 GB RAM: run ONE golden capture at a time (three concurrent captures were all killed for low memory); a full
`pytest tests` takes ~14 min there, `pytest tests/regression` ~10 min. Set `PYTHONUTF8=1` (cp1252 console). `requirements-lock.txt` is the full Windows `pip freeze`, kept for
reference only — do not install it on macOS. The `.venv` is not in git. The committed `.env` holds a Windows
PYTHONPATH; pytest does not need it (`pyproject.toml` sets `pythonpath = ["."]`), and `python -m <module>`
from the repo root works everywhere. PyCharm users: mark the repo root as sources root.
The lab's RFSoC/yoko are never needed for the tests.

**Platform note on the golden.** The golden was captured on Windows originally and regenerated on macOS in
9b8540ba (the original Windows capture is `git show ed66820e:tests/regression/golden_cstq03.json`). The tProc program hashes, cfg dicts and
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
full ladder), then fast-forward. Show the user the commit list and the final test summary before merging. On the final (lab) Windows PC, before
regenerating anything, run the suite once against the ORIGINAL Windows golden (`git show ed66820e:...`) and
classify the diff: everything outside the per-commit allowlists must be explainable, or it is a platform/env
problem to fix first.

## Resuming with Claude Code
Open the repo on the new machine, start Claude Code, and say: "Continue the qicklab refactor — read
docs/dev/refactor-2026-10/HANDOFF.md (TRANSFER STATE first), then design.md; get the suite green on the
clean qicklab_refactor head, then land the parked items from qicklab_refactor_wip one commit at a time per the
landing procedure, using dynamic workflows with Opus agents. Do not re-ask decisions recorded there." The CLAUDE.md banner also points here. Memory from the previous machine is not required;
everything needed is in this directory.
