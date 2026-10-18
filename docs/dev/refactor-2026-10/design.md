# qicklab refactor — design spec v2 (post-audit)

Branch `qicklab_refactor` (from `bfc_code` 0f0a51f). Old tree stays in history; nothing on `bfc_code` changes.
Audit reports: scratchpad/audit/{runners,charge_parity_runs,experiments_basic,experiments_advanced,infra}.md + analysis_and_utils.json.

## Goals (user)
1. One device = one file. Switching chips never touches experiment or runner code.
2. Flat, navigable package; explicit imports; no `import *`; modules ≲ 600 lines; snake_case modules.
3. Terse code. Lab knowledge moves to `docs/`; comments that restate code are deleted.
4. Bookkeeping in one place: parameter registry → generated `docs/parameters.md`, enforced by a test.
5. Behaviour preserved: identical cfg dicts + identical compiled tProc programs reach the hardware (regression golden). Bug fixes are SEPARATE commits with explicit golden updates.

## Invariants (every agent must respect)
- Experiment CLASS NAMES are unchanged (CavitySpecFF, QubitSpecSliceFF, AmplitudeRabiFF, AmplitudeRabiFF_N, ChiShift, ConstantTwoTone, SingleTone, T1FF, T2EMUX, T2R, T1_SS, ChargeDispersion, ChargeDispersionQuasiCW, SingleShotProgramFFMUX, SingleShotProgram, UndrivenSingleShot, ModifiedRamsey, ModifiedRamseyProgram, ActiveResetVerify, ReadOpt_wSingleShotFF, QubitPulseOpt_wSingleShotFF, ZeroSpanParity). Program classes that collide across modules (two `AmplitudeRabiFFProg`, two `T1Program`) get distinct names (`AmplitudeRabiPointProg`, `T1SingleShotProgram`).
- `ExperimentClass` pathing is byte-identical (`outerFolder + path` concatenation, `os.path.join`, `%Y_%m_%d_%H_%M_%S`). `path="..."` strings passed by runs are unchanged (data lands in the same folders).
- cfg KEY NAMES are unchanged (incl. `Read_Indeces`, `qubit_gain` double meaning) in this refactor. Renames are a later, separate decision.
- tProc program bodies (`initialize/body/update`) move verbatim except: comment removal, dedup into `core/readout.py` / `core/active_reset.py` / `core/schedule.py` ONLY where the audit verified the math is identical (golden program hash must not change).
- Dead cfg keys may be dropped only if provably unread (`ts` keys, `pulse_style`); list them in tests/regression/README "allowed cfg diffs".
- No hardware access at import time anywhere. The import-time `matplotlib.use("Agg")` (B1) stays through 3a/3b (today it silently makes every `plt.show(block=True)` a no-op); it is removed in its own fix commit together with `Session(interactive_plots=False)` which sets the backend in the runner, so the default behaviour (non-blocking) is unchanged.
- Star-import leakage fixed with explicit imports (`os`, `time`, `datetime`, `curve_fit`, `np`, `plt`).

## Layout
```
HouckLab_QICK/
├── pyproject.toml, README.md, CLAUDE.md, AGENTS.md
├── devices/              __init__.py (load_device), _template.py, CSTQ03.py
├── runners/              <device>_session.py (the one per-session script; CSTQ03_session.py)
├── qicklab/
│   ├── __init__.py       EMPTY (users import qicklab.core.session; STEPS is qicklab.runs.STEPS) — amended 2026-10-17 in 5a
│   ├── hardware/         rfsoc.py board.py yoko.py attenuator.py sc5510a.py pnax.py synthhd.py
│   ├── core/             experiment.py device.py context.py config.py session.py params.py
│   │                     acquisition.py readout.py active_reset.py schedule.py io.py
│   ├── experiments/      transmission.py cw_tones.py qubit_spec.py rabi.py chi_shift.py
│   │                     t1.py t2_ramsey.py t2_echo.py t1_single_shot.py single_shot.py
│   │                     undriven_single_shot.py charge_dispersion.py modified_ramsey.py
│   │                     active_reset_verify.py readout_optimize.py zero_span_parity.py
│   ├── analysis/         iq.py fitting.py spectroscopy.py ramsey.py readout.py plotting.py
│   │                     hmm.py (emissions, forward-backward, viterbi, fit_two_state_hmm)
│   │                     rates.py (ACF, PSD, rate_vs_bin_size*, simulate_telegraph_trace, drift)
│   │                     dwell.py (debounce, dwell_time_statistics, exp dwell fit)
│   │                     undriven.py (cloud/timeseries analysis from mUndrivenSingleShot)
│   │                     modified_ramsey.py (controls, gates, assess, analyze_modified_ramsey_record, plots)
│   │                     zero_span.py (classify, sliding rate, bursts, analyze_parity_run) zero_span_checks.py (verify_modulation, contrast, snr, sweeps)
│   ├── runs/             __init__.py recipes.py resonator.py spectroscopy.py rabi.py coherence.py
│   │                     single_shot.py active_reset.py modified_ramsey.py charge_dispersion.py
│   │                     charge_sweep.py interleave.py auto_coherence.py sweet_spot.py
│   │                     zero_span.py zero_span_validation.py
│   └── twpa/             common.py set_bias.py set_pump.py flux_sweep.py pump_sweep.py gain_compare.py
├── tests/                regression/ (phase 1) + ported offline tests + registry/device/path tests
│   └── hardware/         verify_modified_ramsey_timing.py (HIL, not collected)
├── scripts/              gen_docs.py (params registry → docs/parameters.md)
└── docs/                 README.md architecture.md parameters.md running_a_session.md adding_a_device.md
                          hardware.md experiments/<step>.md devices/CSTQ03.md
```

## Migration map (old → new). "verbatim" = move + import rewrite only in phase 3a.
| old (Client_modules/…) | new | phase-3b cleanup notes |
|---|---|---|
| CoreLib/socProxy.py | hardware/rfsoc.py `make_proxy(host="192.168.0.103", port=8888, name="myqick", verbose=False)` | drop 4 duplicate makeProxy_* ; keep `makeProxy = make_proxy` alias until runs stop using it |
| Calib/initialize4Q.py | hardware/board.py `BASE_CONFIG`, `base_config()`, `FF_QUBITS` (+ `BaseConfig`, `FF_Qubits` aliases) | drop unused imports; drop `pulse_style` key (allowed cfg diff) |
| PythonDrivers/YOKOGS200.py (unused) | hardware/yoko.py: `ramp_to` (from utils, byte-identical SCPI sequence), `open_yoko(addr)`, `read_voltage`, `restore_bias()` ctx mgr, `pick_current_range`, `ramp_current` (from twpa_set_bias) | delete YOKOGS200 class |
| PythonDrivers/control_atten.py | hardware/attenuator.py `set_attenuation(db, serial, dll_dir, verbose)` | fix NameError L71; drop distutils |
| PythonDrivers/sc5510a_client.py | hardware/sc5510a.py | verbatim |
| CoreLib/Experiment.py | core/experiment.py `ExperimentClass`, `H5File`(=MakeFile), `NumpyJSONEncoder`(=NpEncoder), pure `data_paths()` | delete go/load_data/commented blocks; keep MakeFile/NpEncoder aliases |
| Runners/runs/context.py | core/context.py `Context` (same field names), `connect(session)`; core/config.py `measurement_config(...)`, `singleshot_config(...)`, `sanity_dump` | keep `build_context`/`rebuild_singleshot_config` as thin wrappers during 3a |
| Experiments/utils.py | core/acquisition.py (acquire_with_retry, chunked_acquire, modulated_strobe_acquire, _META_KEYS, markers); analysis/iq.py (project_iq_signal, project_iq_onto_separator, classify_and_average_iq); analysis/fitting.py (hanger_model_db, fit_hanger_transmission, lorentzian_*, fit_lorentzian_feature, estimate_noise_floor, cos_func→`cos_func`, fit_rabi_cosine→`fit_rabi_cosine_gridsearch`); analysis/spectroscopy.py (find_two_tone_peaks, choose_two_tone_freqs_from_lorentz_or_peaks, pick_parity_drive_freq, save_two_tone_plot, _refine_peak_lorentzian, analyze_charge_dispersion); hardware/yoko.py (ramp_to); runs/charge_sweep.py (choose_next_voltage); __main__ → tests/test_acquisition.py | split happens in 3a (pure moves of whole functions) |
| Helpers/shot_buffers.py | core/acquisition.py `raw_shot_buffers` | |
| Helpers/hist_analysis.py, hist_analysis_opt.py | analysis/readout.py `hist_process(..., normalize="pooled"|"per_class", print_fidelities)` — both numerics preserved | |
| Helpers/MixedShots_analysis.py | analysis/readout.py `MixedShots` | drop unused plot methods |
| Helpers/rotate_SS_data.py | analysis/iq.py `rotate_data`, `count_percentage` | drop average_data |
| Experiments/analyze_ModifiedRamseyParity.py | analysis/telegraph.py (HMM/ACF/PSD/drift/simulate/rate_vs_bin_size), analysis/readout.py (calibrate_readout_from_labeled_shots, project_iq_trace), analysis/modified_ramsey.py (reset_success_vs_cycle, compare_parity_controls, assess_parity_record, analyze_modified_ramsey_record, _plot_*) | remove `matplotlib.use` |
| Experiments/analyze_ZeroSpanParity.py | analysis/zero_span.py; dwell_time_statistics/_fit_exp_dwell/_debounce_* → analysis/telegraph.py; __main__ → tests/test_zero_span_analysis.py (mark slow) | remove `matplotlib.use` |
| Experiments/validate_ZeroSpanParity.py | runs/zero_span_validation.py; __main__ → tests/test_zero_span_validation.py | B2 encoding fix (separate commit) |
| Experiments/test_ModifiedRamseyParity_offline.py | tests/test_modified_ramsey_offline.py (pytest-ified; keep all 131 checks) | |
| Experiments/verify_ModifiedRamsey_timing.py | tests/hardware/verify_modified_ramsey_timing.py (imports modified_ramsey_timing from experiments) | |
| Runners/runs/charge_parity.py `modified_ramsey_timing` | experiments/modified_ramsey.py | |
| Experiments/mTransmissionFF.py | experiments/transmission.py | hanger report block → analysis/fitting.py |
| mSpecSliceFF.py | experiments/qubit_spec.py | lorentz helpers → analysis/spectroscopy.py; drop get_amplitude_slice |
| mAmplitudeRabiFF.py + mAmplitudeRabiFF_noUpdate.py | experiments/rabi.py (AmplitudeRabiFFProg, AmplitudeRabiPointProg, AmplitudeRabiFF, AmplitudeRabiFF_N) | local simple cosine fit → analysis/fitting.py `fit_rabi_cosine` (P/2 semantics, the one actually used); Amplitude_IQ(500) → analysis/iq.py `min_q_range_phase(n=500)` |
| mChiShift.py | experiments/chi_shift.py | |
| mConstantTwoTone.py + mSingleTone.py | experiments/cw_tones.py | drop debug prints ("oh yeah") |
| mT1FF.py | experiments/t1.py | Amplitude_IQ(200) → analysis/iq.py; exp fit → analysis/fitting.py `fit_exp_decay` |
| mT2EFF.py | experiments/t2_echo.py | same helpers; remove `if True:` hacks |
| mT2R.py | experiments/t2_ramsey.py; fit fns → analysis/ramsey.py | delete dead ramsey_func/guess_ramsey_params/fit_ramsey |
| mT1_SS.py | experiments/t1_single_shot.py (`T1SingleShotProgram`) | |
| mChargeDispersion.py + mChargeDispersionQuasiCW.py | experiments/charge_dispersion.py | drop dead rotate_iq |
| mSingleShotProgramFFMUX.py | experiments/single_shot.py (SingleShotProgram, SingleShotProgramFFMUX) | DELETE WITHUPDATE, Loopback, AWG compensation, acquireUPDATE (~550 lines); thermal classifier → analysis/readout.py `classify_thermal_tail` |
| mUndrivenSingleShot.py | experiments/undriven_single_shot.py; analysis fns → analysis/telegraph.py (`rate_vs_bin_size_us`, `autocorrelation_rate_us`, analyze_undriven_cloud, analyze_undriven_timeseries, block_average_shots, two_gaussian_threshold, project_onto_axis) | |
| mModifiedRamsey.py | experiments/modified_ramsey.py | reset block → core/active_reset.py mixin (MR version); tone coverage → core/readout.py; schedule ledger → core/schedule.py |
| mActiveResetVerify.py | experiments/active_reset_verify.py | 3b: keep its own (buggy) reset copy; SEPARATE fix commit switches it to the shared mixin + golden update |
| mOptimizeReadoutandPulse_FF.py | experiments/readout_optimize.py | DELETE 3 broken *_Higher* classes + 577 commented lines; keep the two live classes |
| mAutoCoherence.py | runs/auto_coherence.py (+ runs/sweet_spot.py: find_sweet_spot, _stage_sweet_spot_search, _choose_next_voltage) | _ramp_to → hardware.yoko.ramp_to; _find_two_tone_peaks → analysis.spectroscopy |
| mZeroSpanParity.py | experiments/zero_span_parity.py; __main__ → tests/test_zero_span_parity.py | |
| twpa_*.py | twpa/{set_bias,set_pump,flux_sweep,pump_sweep,gain_compare}.py; shared → twpa/common.py, hardware/pnax.py, hardware/synthhd.py | |
| Runners/runs/basic.py | runs/resonator.py (constant tones, transmission_fit/sweep, chi_shift), runs/spectroscopy.py (two_tone_spec, spec_gain_length_sweep, trans_qubit_spec, `spec_cfg()`), runs/rabi.py | |
| Runners/runs/calibration.py | runs/active_reset.py (calibrate_active_reset_readout, wire_reset_into_mr_cfg); runs/single_shot.py (get_apriori_separator_from_singleshot, _extract_iq_from_singleshot_data) | |
| Runners/runs/coherence.py | runs/coherence.py (run_t1/t2/t2e/combos, cfg builders, `t2e_step()`); run_t1_ss → runs/single_shot.py; run_auto_coherence → runs/auto_coherence.py | |
| Runners/runs/singleshot.py | runs/single_shot.py (single_shot, undriven, readout/qubit optimize); run_active_reset_verify → runs/active_reset.py | |
| Runners/runs/charge_parity.py | runs/modified_ramsey.py (run_modified_ramsey, run_modified_ramsey_control), runs/charge_dispersion.py (3 fns), runs/charge_sweep.py (run_charge_sweep, run_charge_transmission_sweep, charge_sweep_voltages) | 3b: dedupe KMeans/plot/save blocks into analysis/iq.py, analysis/plotting.py, core/io.py |
| Runners/runs/zero_span.py, interleave.py | runs/zero_span.py, runs/interleave.py | |
| Runners/runs/__init__.py | runs/__init__.py explicit re-exports + `__all__`; STEPS registry added in phase 5 | |
| Runners/CSTQ03_BFC.py | runners/CSTQ03_BFC.py during 3a–3b (import line only); phase 5 replaces it with devices/CSTQ03.py + runners/<device>_session.py (CSTQ03_session.py) and deletes it | |

## Device / session layer (phase 5) — v3 after critique
Legacy param dicts are SHARED (Spec_relevant_params feeds 6 runs + the regime-A base cfg; T1T2_params 6; SS_params 5 + the regime-B switch). The model must keep that.

```python
# qicklab/core/device.py  (frozen dataclasses; devices/*.py may carry short dated inline history — exempt from the comment policy)
ReadoutWindow(length_us, adc_offset_us)
Readout(freq, gain, window: ReadoutWindow|None=None, ss_window: ReadoutWindow|None=None, kappa_mhz=None)
ParityParams(df_mhz, f_upper_mhz, cd_max_mhz=None, cd_period_mv=None, p_e_state0=0.1, p_e_state1=0.9, calibrated=False)
Qubit(freq, gain, sigma, readout: Readout, pi2_gain=None -> gain//2, flattop_length=None, spec_gain=None, bias_v=None, t1_us=None, parity: ParityParams|None=None, notes="")
Setup(rfsoc_host="192.168.0.103", rfsoc_port=8888, rfsoc_name="myqick", yoko_addr="GPIB1::9::INSTR", board_overrides: dict={} (merged over BASE_CONFIG: nqz, qubit_nqz, cavity_winding_*, trig_*), ff_qubits: dict|None, twpa: TwpaSetup|None (yoko_addr, synth_port, pnax_addr, pump=(ghz, dbm, ch), bias_ua))
Device(name, cooldown, data_root, qubits: dict[int, Qubit], setup: Setup, cavity_min=True, readout_window=ReadoutWindow(15, 0.3), ss_window=ReadoutWindow(15, 0.3))
    .folder(q) -> f"{data_root}/Q{q}//"            # byte-identical to QubitFolders
    .legacy_parameters() -> old Qubit_Parameters shape (str keys) for Context.Qubit_Parameters / AutoCoherence
    .with_qubit(q, **changes) -> new Device (session-local trial without editing the tracked file)
    .validate()  (keys 1..N, gains in 0..32767, pi2 ≤ gain, freqs vs nqz band)
```
Previous cooldowns: `devices/archive/<name>_<cooldown>.py` (v2b table goes there), never deleted.

```python
# qicklab/core/session.py
Session(device, qubit_readout, qubit_pulse, bias_v=0.0, yoko_fixed=False, interactive_plots=False,
        # shared recipe GROUPS consumed by the config builders and by every step that needs them
        transmission=R.transmission(), spec=R.spec(), charge=R.charge_range(), tones=R.tones(),
        coherence=R.coherence(), echo=R.echo(), single_shot=R.single_shot())
Step(name, fn, regime in {"A","B"}, needs=("spec","coherence"), params: dict)   # produced by R.<step>(...)
PLAN = [R.transmission_fit(reps=20), R.t1(), R.single_shot(), R.t1(relax_delay=5000)]   # ORDERED, repeats allowed
run(session, PLAN, dry_run=False)   # connect(); for each step: rebuild cfg iff regime changed vs previous step; step.fn(ctx, *groups, **params); finally close yoko
ctx = connect(session); run_step(ctx, R.t1())      # REPL use
```
Precedence: library recipe default < session group < per-step override (explicit kwargs on `R.<step>(...)`). A single-flag legacy run == PLAN of one step, so the golden is reproducible through this API. `run()` logs the effective params of every step. Regimes switch automatically between consecutive steps: A→B builds the single-shot config from BASE_CONFIG exactly as the legacy `rebuild_singleshot_config` (carry-overs dropped — golden-preserving); B→A restores the cached regime-A config object (what `interleave` already does), so A carry-overs survive a B excursion.

Namespaces (resolved 2026-10-13): session GROUP recipes live in `qicklab.runs.groups as G` (`G.transmission()`, `G.spec()`, `G.charge_range()`, `G.tones()`, `G.coherence()`, `G.echo()`, `G.single_shot()`); STEP recipes in `qicklab.runs.recipes as R` (`R.single_shot()`, `R.t1()`, …) — no name collisions. Runner file: `runners/<device>_session.py` (e.g. `runners/CSTQ03_session.py`). Canonical step names = docs/experiments page names: transmission_fit, transmission_sweep, constant_tone, constant_two_tone, two_tone_spec, spec_gain_length_sweep, trans_qubit_spec, chi_shift, amplitude_rabi, t1, t2_ramsey, t2_echo, t1_t2e, t1_t2r_t2e, interleaved_coherence, auto_coherence, single_shot, undriven_single_shot, t1_single_shot, readout_optimize, qubit_optimize, active_reset_verify, modified_ramsey, modified_ramsey_control, charge_dispersion_ramsey, charge_dispersion_quasicw, two_tone_charge_dispersion_quasicw, charge_sweep, charge_transmission_sweep, zero_span_parity. `dry_run` writes nothing (temp dir removed).

Recipes (`qicklab/runs/recipes.py`): keyword-only functions with explicit parameters, defaults and one-line docs (typos → TypeError; PyCharm quick-doc). Parameter names are snake_case; the function returns the legacy-keyed dict the run_* consumes (`def undriven_single_shot(*, shots=10_000, relax_delay=300, repeat=1, ...) -> {"Shots": shots, "Repeat": repeat, ...}`). Device-dependent values (f_upper, df, cd_*, mapping probs, probe freqs, voltage window, spec gain) default to `None` and resolve from `session.qubit(q)` at run time; `symmetric_ramsey=True` with no `parity.f_upper_mhz` RAISES (no silent centre-frequency fallback). Library defaults are documented sane values; the frozen legacy values live only in `tests/regression/fixtures/cstq03_legacy_params.py` and are passed explicitly by the golden driver.

Calibration write-back: steps that measure a device value (transmission_fit → f_res, Rabi → pi gain, readout/qubit optimize, AutoCoherence, ZSP recal) call `core.io.record_calibration(device, q, **values)`: appends to `<data_root>/Q{q}/calibrations.jsonl` and prints a paste-ready `Qubit(...)` line. ZSP caches are read/written as `<data_root>/Q{q}/zsp_cache.json`.

Dry-run: `run(session, PLAN, dry_run=True)` uses `qicklab/core/fakes.py` (FakeSoc/FakeSocCfg/FakeYoko — the same fakes the regression harness uses; harness imports them from here after 3a) to compile every program and print the plan without hardware.

## Parameter registry (phase 6) — v3
`PARAMS` keyed by `(key, scope)`, scope ∈ {device, session, recipe:<step>, cfg}; fields units (required), meaning, layer, read_by, notes; double-meaning keys (`qubit_gain` spec vs pi; `relax_delay` vs `mr_relax_delay`; `reps`=shots in SS programs) get one entry per scope. Generated docs: (a) `docs/parameters.md` opens with a ~20-row "knobs you change every session" table, then per-layer sections; (b) each `docs/experiments/<step>.md` gets its recipe table (name, default, units, meaning) injected; (c) cfg-internal keys in a developer appendix. Enforcement is RUNTIME: the regression harness wraps each experiment's cfg in a recording dict (logs `__getitem__/get/__contains__/setdefault/__setitem__` per class) and `tests/test_params_registry.py` asserts recorded keys ⊆ PARAMS and `read_by` matches. The AST scan is only a lint for literal `cfg["..."]`/`self.cfg["..."]` subscripts under qicklab/experiments.

## Comment policy
Keep: ≤3-line docstrings on public symbols; one-line "why" at enforced constraints with a `docs/...#anchor` pointer; recipe parameter docs (that is where the user looks). Hazards next to knobs become either runtime checks (odd `num_pi_pulses`; `symmetric_ramsey` needs f_upper; warn `hmm_min_emission_snr < 0.7`) — each in its own fix commit — or a recipe-parameter doc line. Move to docs: measured values, root causes, physics bounds, tuning advice (audit "lab notes" tables are the source; keep dates/numbers). `devices/*.py` keep short dated inline history per qubit. Delete: restated code, commented-out code, banners, stale TODOs, debug prints.

## Package layering (enforced by tests/test_layering.py)
hardware < core < analysis < experiments < runs < twpa. analysis never imports experiments/runs/qick; core never imports runs; no function-local project imports (grep test). `qicklab/__init__.py` is EMPTY (users import `qicklab.core.session`); the regression driver imports every qicklab module before installing mocks.

## Harness v2 (before phase 3a; regenerate golden on legacy code)
1. `display()` runs for real under Agg (savefig/show/pause mocked); attributes it sets (fit_i, fit_q, rotation angles, osc_fit, env_fit, peakFreq_*, qubitFreq, fid/threshold/angle) captured via jsonable().
2. `save_data` payload digested: per key shape, dtype, rounded (1e-9 rel) hash + first 3 values. `save_config` cfg digested too.
3. Second synthetic soccfg VARIANT: gen f_fabric 614.4 MHz ≠ f_time 430.08, readout tproc_ch = index+2, one gen has_mixer=True, avg_maxlen/buf_maxlen as real (16384/1024). Golden keyed by variant; both must pass.
4. Budget per (cls, path) (first N=4 of each kind), not per run; variant labels: `RunModifiedRamsey[no_reset]`, `RunModifiedRamsey_Control[skip_sweet_spot]`, `RunAutoCoherence[skip_search,no_readout_opt]`, `RunT2E[...]`; multi-flag labels for carry-overs: `RunTransmissionSweep+RunAmplitudeRabi` (pulse_freq), `Run2ToneChargeDispersionQuasiCW+RunChargeDispersionQuasiCW` (probe_freq leak), `RunActiveResetVerify+SingleShot` (res_phase discarded by rebuild).
5. Freeze runner sections 1–2 verbatim as `tests/regression/fixtures/cstq03_legacy_params.py` (driver execs the fixture, not the runner).
6. Record `qick.__version__` in the golden; fail loudly on mismatch. Pin `qick==0.2.334` in pyproject.
7. Recording-dict cfg wrapper (for the params registry test) — recorded key sets stored in the golden per class.
8. Unit tests pinning `scheduled_rep_period_cycles` (MR with/without reset, with register sync → raise in Undriven) and the readout-window attributes (readout_window_cycles, readout_tone_cycles, extension) under both variants.

## Phase-3a equivalence check (replaces the vague "AST equivalence")
- `tests/refactor/symbol_map.py`: per-symbol table (old module.qualname → new module.name, phase, kind ∈ {moved, renamed, deleted(reason), merged(proof)}); a test asserts no two old symbols map to one new name unless kind=merged with an AST-equality proof.
- AST equality modulo the rename table, with import statements stripped, for every moved function/class.
- Binding check: load the old tree from a git worktree at 0f0a51f and the new package; for each moved function, free globals (symtable) must resolve to the same origin (same AST hash for project code; same identity for stdlib/3rd-party) — this catches the star-import shadowing (local fit_rabi_cosine, `datetime` class-vs-module).
- Ledger: every top-level statement of every old module is accounted for (moved / deleted-with-reason / replaced).

## Known bugs — NOT fixed in the refactor (reported to user; candidates for separate commits)
ARV `cmp_offset=1<<24` (fix via shared mixin — planned separate commit); ZSP `declare_readout` missing `ro_ch`; `run_charge_dispersion_ramsey` KeyError `df`; `kappa_mhz` /1e6 (2 places); ChargeDispersion wait 1/df vs 1/(2df); T2R ignores flattop; validate_ZSP B2–B4; hist threshold off-by-one-bin; MRC not same sequence as MR; mutated caller dicts (probe_freq, setdefault); yoko not restored after sweeps; `step=int(max_gain/n)` truncation; `run_interleaved_coherence` returns early when no sub-experiment is enabled without restoring `ctx.config` (regime B left behind; guarded by `core.session.run_step`, found in 5a 2026-10-17).

## Verification ladder (every phase)
1. `ruff check .` + `ruff format --check .` (qicklab, devices, runners, tests, scripts)
2. `python -m compileall -q qicklab devices runners tests`
3. import every module under qicklab/ (no hardware, no Agg side effect)
4. `pytest tests` incl. regression golden (driver_qicklab) — program hashes + cfgs identical except the documented allowlist
5. phase 3a only: AST equivalence old↔new per moved symbol (imports stripped)
6. adversarial reviewer per cleaned module (phase 3b)

## Commit plan (each commit green on the full verification ladder)
1. test(regression): harness v1 + golden (phase-1 agent)
2. test(regression): harness v2 (display/save_data digests, soccfg variant, per-kind budget, variant+multi-flag labels, frozen legacy fixture, qick version, recording cfg) + regenerated golden — still on legacy code
3. chore: pyproject (ruff/pytest config, pinned qick, extras), README stub
4. refactor: 3a-i — 1:1 `git mv` into qicklab/ + import rewrite (explicit imports, no star) + `__init__.py`s + driver_qicklab path switch. No body edits. Equivalence check + golden green.
5. refactor: 3a-ii — multi-way splits (utils, analyze_MRP, analyze_ZSP, charge_parity, mAutoCoherence, basic/calibration/coherence/singleshot runs) as pure function moves with the symbol map; distinct names for colliding symbols. Equivalence + golden green.
6. style: 3a-iii — `ruff format` + isort only; listed in `.git-blame-ignore-revs`.
7..N. refactor(<area>): comments→docs notes file, dead code, dedupe (phase 3b, one commit per area, each with an adversarial old-vs-new review). Golden green (allowlisted dead-key diffs only).
N+1. feat(core): 5a — Device/Session/recipes/Step/PLAN/run + devices/CSTQ03.py + runners/CSTQ03_session.py + driver_plan (legacy labels → PLAN via the frozen fixture); both drivers green.
N+2. refactor: 5b — delete legacy runner + driver_legacy; `devices/archive/CSTQ03_v2b.py`.
N+3. docs: registry + generated parameters.md + concept pages + experiment/device/hardware pages + bring-up workflow + troubleshooting + glossary (phase 6)
N+4. docs: rewrite CLAUDE.md / AGENTS.md / README for this branch (the repo now IS qicklab)
N+5.. fix(...): individual bug fixes, one per commit, each with an explicit golden update (B1 Agg + interactive_plots; ARV → shared reset mixin; validate_ZSP B2–B4; odd num_pi_pulses check; …) — only after the user approves the list.
