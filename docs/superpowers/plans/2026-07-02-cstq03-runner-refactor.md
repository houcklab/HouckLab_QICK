# CSTQ03_BFC Runner Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move `CSTQ03_BFC.py` out of `Experiments/` into a new `Runners/` folder and extract its 28 inline measurement blocks into a `runs/` package, leaving a thin ~550-line runner — with identical measurement behavior except the intended fix of the accidental cross-block `config` leak.

**Architecture:** A `Context` dataclass carries the shared runtime state (`soc`, `soccfg`, `yoko`, `config`, `outerFolder`, derived scalars). Each `if RunX:` block becomes `run_x(ctx, params)` in a family-grouped module. Transient scan knobs live on a per-call local working-config; only measured carry-overs `pulse_freq` and `res_phase` write back to `ctx.config`.

**Tech Stack:** Python 3, QICK, numpy/scipy/matplotlib, Pyro4 (hardware proxy). No unit-test suite and no hardware in this environment — verification is byte-compile + AST import-trace + call-fidelity checks + a dynamic-workflow adversarial review.

## Global Constraints

- Purely structural. No physics/measurement-logic changes; same programs, same acquire/display/save calls, in the same order.
- Do NOT modify any `Experiments/m*.py` file.
- The runner must remain runnable top-to-bottom (edit params → toggle flags → run).
- Leak fix allow-list: the ONLY keys a routine may write back to `ctx.config` are `pulse_freq` (fitted/found cavity freq) and `res_phase` (calibrated readout phase). All other `config[...]` writes go on a local working-config copy.
- All `runs/` modules import utils via the absolute path `from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils import *` (never bare `from utils import *`).
- Source of truth for every extracted body: the current file, committed at `10faf0f`, path `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/CSTQ03_BFC.py`. Reference it as SRC below.

---

## File structure

```
Client_modules/Runners/
├── CSTQ03_BFC.py            # thin runner (Task 8)
└── runs/
    ├── __init__.py          # re-exports (Task 1)
    ├── context.py           # Context, build_context, sanity_dump (Task 1)
    ├── calibration.py       # 4 helpers (Task 2)
    ├── basic.py             # transmission/spec/chi/rabi/trans_qubit_spec (Task 3)
    ├── coherence.py         # T1/T2/T2E/combos/T1SS/auto (Task 4)
    ├── charge_parity.py     # charge-dispersion/ModifiedRamsey±Control/charge sweep (Task 5)
    ├── singleshot.py        # single-shot/readout+qubit optimize/active-reset verify (Task 6)
    └── zero_span.py         # zero-span parity + validation dispatch (Task 7)
```

Source-block line ranges in SRC (for reference during extraction):

| Flag | SRC lines | Target |
|------|-----------|--------|
| Constant2Tone | 797–807 | basic.run_constant_two_tone |
| ConstantTone | 808–815 | basic.run_constant_tone |
| RunTransmissionSweep | 816–928 | basic.run_transmission_fit |
| RunTransmissionSweeps | 929–946 | basic.run_transmission_sweep |
| Run2ToneSpec | 947–982 | basic.run_two_tone_spec |
| RunSpecGainLengthSweep | 983–1023 | basic.run_spec_gain_length_sweep |
| RunChiShift | 1024–1037 | basic.run_chi_shift |
| Run2ToneChargeDispersionQuasiCW | 1038–1395 | charge_parity.run_two_tone_charge_dispersion_quasicw |
| RunModifiedRamsey | 1396–1838 | charge_parity.run_modified_ramsey |
| RunModifiedRamsey_Control | 1839–2168 | charge_parity.run_modified_ramsey_control |
| RunChargeDispersionQuasiCW | 2169–2362 | charge_parity.run_charge_dispersion_quasicw |
| RunChargeDispersionRamsey | 2363–2393 | charge_parity.run_charge_dispersion_ramsey |
| RunAmplitudeRabi | 2394–2430 | basic.run_amplitude_rabi |
| RunT1 | 2431–2453 | coherence.run_t1 |
| RunT1T2E | 2454–2521 | coherence.run_t1_t2e |
| RunT1T2RT2E | 2522–2601 | coherence.run_t1_t2r_t2e |
| RunT2 | 2602–2620 | coherence.run_t2 |
| RunT2E | 2621–2671 | coherence.run_t2e |
| RunTrans_QubitSpec | 2684–2708 | basic.run_trans_qubit_spec |
| RunChargeSweep | 2709–2842 | charge_parity.run_charge_sweep |
| RunActiveResetVerify | 2843–3018 | singleshot.run_active_reset_verify |
| SingleShot | 3019–3032 | singleshot.run_single_shot |
| RunT1SS | 3033–3064 | coherence.run_t1_ss |
| SingleShot_ReadoutOptimize | 3065–3091 | singleshot.run_readout_optimize |
| SingleShot_QubitOptimize | 3092–3127 | singleshot.run_qubit_optimize |
| RunAutoCoherence | 3128–3148 | coherence.run_auto_coherence |
| RunZeroSpanParity (+ nested Validate_*/Build_EvidenceReport 3298–3346) | 3149–3346 | zero_span.run_zero_span_parity |

Helper functions in SRC: `_extract_iq_from_singleshot_data` (48–80), `get_apriori_separator_from_singleshot` (81–142), `calibrate_active_reset_readout` (145–225), `wire_reset_into_mr_cfg` (228–241) → `calibration.py`. `sanity_dump` (2672–2683) → `context.py`.

---

## Extraction rules (apply to every block in Tasks 2–7)

1. Signature: `def run_x(ctx, params):` (helpers keep their data args + take `ctx`).
2. Rewrite shared globals to `ctx.<field>`: `soc`→`ctx.soc`, `soccfg`→`ctx.soccfg`, `yoko`→`ctx.yoko`, `outerFolder`→`ctx.outerFolder`, `Qubit_Readout`→`ctx.Qubit_Readout`, `Qubit_Pulse`→`ctx.Qubit_Pulse`, `Qubit_Parameters`→`ctx.Qubit_Parameters`, `start_voltage`→`ctx.start_voltage`, `yoko_fixed`→`ctx.yoko_fixed`, `cavity_min`→`ctx.cavity_min`, `cavity_gain`→`ctx.cavity_gain`, `resonator_frequency_center`→`ctx.resonator_frequency_center`, `qubit_gain`→`ctx.qubit_gain`, `pi2_gain`→`ctx.pi2_gain`, `qubit_frequency_center`→`ctx.qubit_frequency_center`, `qubit_sigma`→`ctx.qubit_sigma`, `qubit_flattop`→`ctx.qubit_flattop`.
3. The block's own `*_params` global → the `params` argument.
4. Config: replace the block's first use of `config` with `cfg = ctx.working_config()`; keep all transient `config[...] = ...` writes as `cfg[...] = ...`; keep `config[...]` reads as `cfg[...]`. EXCEPTION — the allow-list writes stay on `ctx.config`: `config["pulse_freq"] = ...` → `ctx.config["pulse_freq"] = ...`; `config["res_phase"] = ...` → `ctx.config["res_phase"] = ...` (and pass `ctx.config` — not `cfg` — into helpers/programs that must see the persisted phase, matching SRC which shared one dict).
5. Any `config = config | X` rebind (SRC 1030, 2406, 2415, 2444, 2611, 3054, 3081, 3112) becomes `cfg = ctx.working_config(X)` (local; no write-back) — this IS the leak fix.
6. Nothing else changes: same imports available, same call order, same numeric literals.

---

### Task 1: Package scaffold — `context.py` + `__init__.py`

**Files:**
- Create: `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Runners/runs/__init__.py`
- Create: `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Runners/runs/context.py`

**Interfaces:**
- Produces: `Context` (dataclass, fields per spec §4), `build_context(Qubit_Parameters, Qubit_Readout, Qubit_Pulse, start_voltage) -> Context`, `Context.working_config(*updates) -> dict`, `sanity_dump(cfg, tag="")`.

- [ ] **Step 1: Write `context.py`.** Define the `Context` dataclass with exactly the fields in spec §4. Add method `working_config(self, *updates)` returning `dict(self.config)` updated with each dict in `updates`. Move `sanity_dump` verbatim from SRC 2672–2683 (module-level function). Write `build_context`: it performs SRC lines 249 (`makeProxy()`), 296–303 (yoko open/`ramp_to(start_voltage)`), the derived-scalar block SRC 747–754, config assembly SRC 756–792 (`trans_config`/`qubit_config`/`expt_cfg`/`UpdateConfig`/`config = BaseConfig | UpdateConfig`, `config["FF_Qubits"]`, `config["cavity_min"]`) — reading device values from `Qubit_Parameters[str(...)]`. Import `BaseConfig`, `FF_Qubits`, `makeProxy`, `ramp_to`, `pyvisa` via the same absolute paths SRC uses (initialize4Q, socProxy, Experiments.utils). Return the populated `Context`.

- [ ] **Step 2: Write `__init__.py`** re-exporting names: `from .context import Context, build_context, sanity_dump`. (Family modules appended in later tasks.)

- [ ] **Step 3: Byte-compile.** Run: `python -m py_compile <runs>/context.py <runs>/__init__.py` — Expected: no output (success).

- [ ] **Step 4: Commit.** `git add` the two files; `git commit -m "refactor(CSTQ03): add runs/ package scaffold (Context, build_context)"`.

---

### Task 2: `calibration.py` — active-reset / single-shot helpers

**Files:**
- Create: `.../Runners/runs/calibration.py`
- Modify: `.../Runners/runs/__init__.py` (add re-export)

**Interfaces:**
- Consumes: `Context` (Task 1).
- Produces: `get_apriori_separator_from_singleshot(ctx)`, `calibrate_active_reset_readout(ctx, max_align_iter=2, align_tol_frac=0.1)`, `wire_reset_into_mr_cfg(mr_cfg, apriori_sep)`, `_extract_iq_from_singleshot_data(data_ss, state="g")`.

- [ ] **Step 1: Extract the 4 helpers** from SRC 48–241 into `calibration.py`, applying the extraction rules. `get_apriori_separator_from_singleshot` currently reads globals `ModifiedRamsey_params`, `qubit_gain`, `qubit_frequency_center`, `qubit_sigma`, `qubit_flattop`, `Qubit_Readout` and takes `(config, soc, soccfg, outerFolder)` — change its signature to `(ctx)` and read all of those from `ctx` (build its SingleShot cfg from `ctx.working_config(...)`; the `ss_calib_shots` value comes from `ctx`-carried ModifiedRamsey params — pass it as an arg `ss_shots` instead, defaulting to 1000, since ModifiedRamsey_params is a client param dict). `calibrate_active_reset_readout` mutates `ctx.config["res_phase"]` (allowed carry-over). Import `SingleShotProgramFFMUX`, numpy via absolute paths.
- [ ] **Step 2:** Add `from .calibration import *` (or explicit names) to `__init__.py`.
- [ ] **Step 3: Byte-compile** `calibration.py` + `__init__.py`. Expected: success.
- [ ] **Step 4: Fidelity check.** Run: `grep -oE "SingleShotProgramFFMUX|deg2reg|arctan2|readout_threshold|res_phase" calibration.py | sort | uniq -c` and confirm the same symbols appear as in SRC 48–241. Expected: matching set.
- [ ] **Step 5: Commit.** `git commit -m "refactor(CSTQ03): extract active-reset calibration helpers"`.

---

### Task 3: `basic.py` — transmission, spec, chi-shift, Rabi

**Files:**
- Create: `.../Runners/runs/basic.py`
- Modify: `.../Runners/runs/__init__.py`

**Interfaces:**
- Consumes: `Context`.
- Produces: `run_constant_two_tone(ctx, params=None)`, `run_constant_tone(ctx, params=None)`, `run_transmission_fit(ctx, params)`, `run_transmission_sweep(ctx, params)`, `run_two_tone_spec(ctx, params)`, `run_spec_gain_length_sweep(ctx, params)`, `run_chi_shift(ctx, params)`, `run_amplitude_rabi(ctx, params)`, `run_trans_qubit_spec(ctx, params)`. (`params` = the block's original `*_params` dict; for the two Constant* blocks and Trans blocks pass the relevant params dict, e.g. `Transmission_params`/`Spec_relevant_params`, per SRC usage.)

- [ ] **Step 1:** Extract SRC blocks 797–815, 816–946, 947–1023, 1024–1037, 2394–2430, 2684–2708 into `basic.py` per the extraction rules. `run_transmission_fit` / `run_transmission_sweep` write `ctx.config["pulse_freq"]` (allow-listed); `run_chi_shift` and `run_amplitude_rabi` use `cfg = ctx.working_config(...)` for their param merges (leak fix). `run_trans_qubit_spec` calls `sanity_dump(cfg)` (imported from context). Import `CavitySpecFF`, `SingleTone`, `ConstantTwoTone`, `QubitSpecSliceFF`, `ChiShift`, `AmplitudeRabiFF`, `fit_hanger_transmission` (from utils), numpy/plt via absolute paths.
- [ ] **Step 2:** Add re-export to `__init__.py`.
- [ ] **Step 3: Byte-compile.** Expected: success.
- [ ] **Step 4: Fidelity check.** For each function, `grep` its program class name and confirm it matches the SRC block (e.g. `run_two_tone_spec` contains `QubitSpecSliceFF` acquire/display/save_data/save_config in that order).
- [ ] **Step 5: Commit.** `git commit -m "refactor(CSTQ03): extract basic experiments (transmission/spec/chi/rabi)"`.

---

### Task 4: `coherence.py` — T1/T2/T2E/combos/T1SS/auto

**Files:**
- Create: `.../Runners/runs/coherence.py`
- Modify: `.../Runners/runs/__init__.py`

**Interfaces:**
- Consumes: `Context`.
- Produces: `run_t1(ctx, params)`, `run_t2(ctx, params)`, `run_t2e(ctx, params)`, `run_t1_t2e(ctx, params)`, `run_t1_t2r_t2e(ctx, params)`, `run_t1_ss(ctx, params)`, `run_auto_coherence(ctx, params, override_params)`.

- [ ] **Step 1:** Extract SRC blocks 2431–2453, 2602–2620, 2621–2671, 2454–2521, 2522–2601, 3033–3064, 3128–3148. `run_t1`/`run_t2`/`run_t1_ss` rebind config in SRC → use `cfg = ctx.working_config(...)` (leak fix); `expt_cfg` rebinds become local vars. `run_auto_coherence` wraps `run_auto_coherence`/`AUTO_COHERENCE_PARAMS`/`find_sweet_spot` from `mAutoCoherence` — rename the wrapper to avoid shadowing the import (e.g. keep import as `from ...mAutoCoherence import run_auto_coherence as _run_auto_coherence` and name the wrapper `run_auto_coherence`). Import `T1FF`, `T2R`, `T2EMUX`, `T1_SS`, numpy via absolute paths.
- [ ] **Step 2:** Re-export in `__init__.py`.
- [ ] **Step 3: Byte-compile.** Expected: success.
- [ ] **Step 4: Fidelity check.** Confirm program classes per block (`T1FF`, `T2R`, `T2EMUX`, `T1_SS`) and call order match SRC.
- [ ] **Step 5: Commit.** `git commit -m "refactor(CSTQ03): extract coherence experiments (T1/T2/T2E/T1SS/auto)"`.

---

### Task 5: `charge_parity.py` — charge dispersion, ModifiedRamsey(±Control), charge sweep

**Files:**
- Create: `.../Runners/runs/charge_parity.py`
- Modify: `.../Runners/runs/__init__.py`

**Interfaces:**
- Consumes: `Context`, and from `calibration`: `get_apriori_separator_from_singleshot`, `calibrate_active_reset_readout`, `wire_reset_into_mr_cfg`.
- Produces: `run_two_tone_charge_dispersion_quasicw(ctx, params)`, `run_charge_dispersion_quasicw(ctx, params)`, `run_charge_dispersion_ramsey(ctx, params)`, `run_charge_sweep(ctx, params)`, `run_modified_ramsey(ctx, params)`, `run_modified_ramsey_control(ctx, params)`.

- [ ] **Step 1:** Extract SRC blocks 1038–1395, 2169–2362, 2363–2393, 2709–2842, 1396–1838, 1839–2168. These are the largest blocks and the ones using the calibration helpers and `ctx.yoko` voltage sweeps. Preserve every `yoko.query/write`, `ramp_to`, peak-finder (`find_parity_doublet`), and Ramsey loop verbatim; only apply the rewrites. `run_charge_sweep` calls `sanity_dump(cfg)`. `run_modified_ramsey`/`run_modified_ramsey_control` call the calibration helpers with `ctx` and use `ctx.config` where the persisted `res_phase`/threshold must be visible. Import charge/ramsey program classes (`ChargeDispersionQuasiCW`, `ChargeDispersion`, `ModifiedRamsey`, `QubitSpecSliceFF`, `SingleShotProgramFFMUX`), utils peak-finder functions, numpy/plt via absolute paths.
- [ ] **Step 2:** Re-export in `__init__.py`.
- [ ] **Step 3: Byte-compile.** Expected: success.
- [ ] **Step 4: Fidelity check.** Confirm `find_parity_doublet`, `ModifiedRamsey`, voltage-search loop bounds, and `tau = 1/(2*df)` computation are present and match SRC line-for-line (diff the extracted body against `sed -n '1396,1838p' SRC` modulo the mechanical rewrites).
- [ ] **Step 5: Commit.** `git commit -m "refactor(CSTQ03): extract charge-parity + modified-Ramsey experiments"`.

---

### Task 6: `singleshot.py` — single-shot, readout/qubit optimize, active-reset verify

**Files:**
- Create: `.../Runners/runs/singleshot.py`
- Modify: `.../Runners/runs/__init__.py`

**Interfaces:**
- Consumes: `Context`, and from `calibration`: `calibrate_active_reset_readout`, `wire_reset_into_mr_cfg`.
- Produces: `run_single_shot(ctx, params)`, `run_readout_optimize(ctx, params)`, `run_qubit_optimize(ctx, params)`, `run_active_reset_verify(ctx, params)`.

- [ ] **Step 1:** Extract SRC blocks 3019–3032, 3065–3091, 3092–3127, 2843–3018. `run_active_reset_verify` contains a second config rebuild (SRC ~3015 sets `config["FF_Qubits"]`) — reproduce it on a local `cfg = ctx.working_config(...)` and set `cfg["FF_Qubits"] = ctx.config["FF_Qubits"]`. The optimize blocks' `config = ...` rebinds → local `cfg` (leak fix). Import `SingleShotProgramFFMUX`, `ReadOpt_wSingleShotFF`, `QubitPulseOpt_wSingleShotFF`, `ActiveResetVerify`, numpy via absolute paths.
- [ ] **Step 2:** Re-export in `__init__.py`.
- [ ] **Step 3: Byte-compile.** Expected: success.
- [ ] **Step 4: Fidelity check.** Confirm `ActiveResetVerify`, `ReadOpt_wSingleShotFF`, `QubitPulseOpt_wSingleShotFF` classes and their call order match SRC.
- [ ] **Step 5: Commit.** `git commit -m "refactor(CSTQ03): extract single-shot + optimize + active-reset-verify"`.

---

### Task 7: `zero_span.py` — zero-span parity + validation dispatch

**Files:**
- Create: `.../Runners/runs/zero_span.py`
- Modify: `.../Runners/runs/__init__.py`

**Interfaces:**
- Consumes: `Context`, and from `calibration`: `get_apriori_separator_from_singleshot`.
- Produces: `run_zero_span_parity(ctx, zsp_params)` where `zsp_params` is a dict bundling the client's `ZSP_*` config (`RunMode`, `StartSrc`, recalibrate flags, cached dicts, `ParitySpec_params`, `StrobeParams`, `DecimatedParams`, `DriveParams`, `AnalysisParams`, and the `Validate_*`/`Build_EvidenceReport` flags + their `*_params`).

- [ ] **Step 1:** Extract SRC block 3149–3346 (including the nested `Validate_*`/`Build_EvidenceReport` sub-blocks 3298–3346) into a single `run_zero_span_parity`. Apply the rewrites; the nested `if Validate_X:` stay as nested `if zsp_params["Validate_X"]:`. Import `ZeroSpanParity`, `analyze_parity_run`, the `validate_ZeroSpanParity` functions, `QubitSpecSliceFF`, numpy via absolute paths; `pick_parity_drive_freq`/`chunked_acquire` from utils.
- [ ] **Step 2:** Re-export in `__init__.py`.
- [ ] **Step 3: Byte-compile.** Expected: success.
- [ ] **Step 4: Fidelity check.** Confirm `ZeroSpanParity`, `analyze_parity_run`, and the 6 validation functions all appear and match SRC call order.
- [ ] **Step 5: Commit.** `git commit -m "refactor(CSTQ03): extract zero-span parity + validation dispatch"`.

---

### Task 8: Thin runner + retire the old file

**Files:**
- Create: `.../Runners/CSTQ03_BFC.py`
- Delete: `.../Experiments/CSTQ03_BFC.py`

**Interfaces:**
- Consumes: everything re-exported from `runs`.

- [ ] **Step 1: Write the thin runner** with the three bannered sections from spec §7. Section 1: `Qubit_Parameters` (verbatim from SRC 258–293), `Qubit_Readout`/`Qubit_Pulse`, `start_voltage`, `temp_dir_Q4`, `QubitFolders`. Section 2: all 36 flags + all 23 `*_params` dicts verbatim from SRC. Section 3: `ctx = build_context(...)` then one `if Flag: run_x(ctx, params)` per row in the block map (matching SRC's original top-to-bottom order). Zero-span passes a single `zsp_params` dict assembled from the `ZSP_*` globals.
- [ ] **Step 2: Delete** the old `Experiments/CSTQ03_BFC.py` (`git rm`).
- [ ] **Step 3: Byte-compile** the new runner and the whole `runs/` package. Run: `git ls-files 'Client_modules/Runners/*.py' | xargs python -m py_compile`. Expected: success.
- [ ] **Step 4: AST import-trace** from the new runner (reuse the scratch `trace_imports.py`, re-rooted at the new path). Expected: closure resolves; no reference to the deleted `Experiments/CSTQ03_BFC.py`; no dangling repo-internal imports.
- [ ] **Step 5: Flag/dispatch coverage check.** Run a script asserting: (a) every `Run*/Single*/Constant*/Validate*/Build*` flag defined in section 2 has exactly one dispatch in section 3 (or is a nested ZSP flag), and (b) every `run_*` exported by `runs` is dispatched. Expected: no missing/extra.
- [ ] **Step 6: Commit.** `git commit -m "refactor(CSTQ03): thin runner in Runners/; retire monolithic Experiments/CSTQ03_BFC.py"`.

---

### Task 9: Adversarial code review (dynamic workflow)

**Files:** none (review only).

- [ ] **Step 1:** Run a dynamic Workflow that, per extracted module, has an agent diff the extracted `run_*` bodies against their SRC blocks (SRC available at git `10faf0f`) and report any behavior-affecting discrepancy: missed global→ctx rewrite (latent `NameError`), dropped/reordered program call, transient write wrongly persisted to `ctx.config`, allow-listed carry-over (`pulse_freq`/`res_phase`) wrongly localized, mis-threaded `params`, changed numeric literal.
- [ ] **Step 2:** Each finding is verified by an independent skeptic agent (refute-by-default) before it is accepted as real.
- [ ] **Step 3:** Fix confirmed findings; re-run byte-compile + trace; commit fixes.

## Self-review (author checklist — completed)

- **Spec coverage:** every spec section maps to a task — layout/move (Task 8), Context (Task 1), leak fix allow-list (rules + Tasks 3/5/6), all 27 rows + helpers (Tasks 2–7), import fix (rules + each task), verification + adversarial review (Tasks 8–9). No gaps.
- **Placeholder scan:** no TBD/TODO; where full code is impractical to inline (2,550 lines of verbatim extraction), tasks cite exact SRC line ranges + mechanical rewrite rules — the extraction is copy-with-rename, not new authorship.
- **Type/name consistency:** `Context`, `build_context`, `working_config`, `sanity_dump`, and every `run_*` name are used identically across the interfaces blocks and the Task 8 dispatch/block-map.
```
