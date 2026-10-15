# Hardware-free regression harness

A golden-master snapshot of what the CSTQ03 runner sends to the hardware, what
its experiments compute and what they save. It exists so the coming refactor
can be checked against the pre-refactor code without a fridge, a board or a
yoko.

```
python -m pytest tests/regression                                   # compare against the golden (~13 min)
REGRESSION_LABELS=RunT1,RunT2 python -m pytest tests/regression     # just some runs
REGRESSION_VARIANTS=A python -m pytest tests/regression             # just one board variant
REGRESSION_UPDATE=1 python -m pytest tests/regression               # rewrite the golden from current code
python -m tests.regression.driver_legacy                            # same as UPDATE, without pytest
python -m tests.regression.driver_legacy RunT1                      # dry run (both variants), golden untouched
python -m pytest tests/test_program_timing.py                       # pinned schedule/readout numbers (~3 s)
```

Run from the repo root (`pyproject.toml` / `tests/conftest.py` put it on
`sys.path`). `pyproject.toml` already sets `addopts = "-q"`; adding `-q` on
the command line makes it `-qq`, which hides the per-test lines.
`REGRESSION_LABELS` and `REGRESSION_VARIANTS` combine with
`REGRESSION_UPDATE=1`: only the named entries are rewritten, the rest of the
golden is kept.

## Files

| File | Role |
|---|---|
| `capture.py` | Layout-agnostic core: fakes, synthetic boards, instrumentation, digests, normalisation. Reused unchanged after the refactor. |
| `driver_legacy.py` | Replays every dispatch of the frozen runner, plus variant and multi-flag labels. |
| `fixtures/cstq03_legacy_runner.py.txt` | Verbatim copy of `Runners/CSTQ03_BFC.py` at commit `0f0a51f`. **Never edit** (see `fixtures/README.md`). |
| `golden_cstq03.json` | The snapshot: `{"__meta__": {"qick", "variants"}, "A": {label: ...}, "B": {label: ...}}`. |
| `test_golden.py` | Re-captures in memory under both board variants and diffs per (variant, label). `DRIVER` at the top selects the driver. |
| `../test_program_timing.py` | Unit tests pinning tProc schedule and readout-window integers of the legacy programs under both boards. |

## What changed in v2

1. **`display()` runs for real** (Agg backend; `show`/`pause`/`savefig` are
   no-ops). After every wrapped call the public, plain-data attributes it
   added or changed are recorded as `"sets"`: fit results (`fit_i`, `fit_q`,
   `osc_fit`, `env_fit`), `peakFreq_*`, `qubitFreq`, `fid`/`threshold`/`angle`
   and so on. A `display` that raises on synthetic data is recorded as
   `"raised": <type>` and the run continues (currently none; the 5 `T2R.display`
   `ValueError`s per variant were fixed 2026-10-13). `acquire`/`save_*` exceptions still propagate.
   All figures are closed after each `display`: with `show` stubbed, a display
   that relies on the user closing its window would otherwise leak every
   figure (the Undriven display alone grew the process past 5 GB).
2. **Saved payloads are digested.** Every `save_data` entry carries
   `"data_digest"`: per key (nested dicts flattened with `/`) its shape, dtype,
   first three values and a sha1 over the values. Floats are hashed after
   rounding the binary mantissa to 30 bits (about 9 significant digits;
   `np.frexp` is exact, so this is deterministic). Every `save_config` entry
   carries `"cfg_digest"` (sha1 of the whole cfg) and `"cfg_delta"` (keys added,
   changed or removed since `__init__`, with their values). Arrays anywhere in
   the capture (cfg, kwargs, `sets`) also carry a `sha1`.
3. **Two synthetic boards.** `A` is the v1 board. `B` breaks the coincidences
   `A` hides: gen fabric clock 614.4 MHz (DAC 9830.4 MS/s, `fs_mult` 20) instead
   of the tProc's 430.08 MHz, and readout *i* wired to tProc input *i + 2*. Both
   keep tProc 430.08 MHz, readout output 307.2 MHz, `avg_maxlen` 16384,
   `buf_maxlen` 1024. Select with `capture.set_board("A"|"B")`; the golden holds
   both and every experiment's board digest differs between them (so a
   gen-clock/tProc-clock or readout/tProc-input mix-up cannot pass).
4. **Budget per (class, path).** The first `PER_KIND` = 4 instantiations of each
   `(class name, path)` pair are captured; later ones still run, but are not
   recorded (their board traffic is discarded too) and are counted in
   `"skipped": {"cls/path": n}`. A run stops (`StopCapture`, outcome
   `stopped_at_budget`) at the first of: more than `MAX_TOTAL` = 60
   instantiations, one pair skipped more than `MAX_SKIPS` = 200 times, or
   **more than `MAX_IDLE` = 8 consecutive skipped instantiations**. The last rule
   was added for runtime: without it, loop-only runs execute 60 real
   acquisitions each (RunUndrivenSingleShot alone took over 9 min per
   variant). It only ends runs that have stopped producing anything new.
5. **Variant and multi-flag labels** (table below).
6. **Frozen runner.** The driver reads `fixtures/cstq03_legacy_runner.py.txt`,
   drops its single `from ... import *` line (replaced by a blank line, so line
   numbers hold) and seeds the exec namespace with exactly the names that
   star-import binds from `RUNS_PACKAGE`. A post-refactor driver changes that
   constant and the patch targets, nothing else.
7. **`cfg_access`.** `ExperimentClass.__init__` stores
   `self.cfg = capture.RecordingDict(cfg)`. Explicit lookups (`[]`, `get`, `in`,
   `setdefault`) and mutations (`[]=`, `del`, `pop`, `popitem`, `clear`,
   `update`, `|=`) are logged per experiment class (string keys only); the run
   records `"cfg_access": {cls: {"read": [...], "written": [...]}}`, unioned
   over all its experiments, skipped ones included. It is a real `dict`, so
   `isinstance`, `json.dump`, h5 attrs, `dict(cfg)` and `**cfg` all work. Lookups
   are answered from the original dict and writes go to both, so the aliasing
   the code relies on is kept. Copies (`dict(cfg)`, `cfg.copy()`,
   `copy.copy/deepcopy`, pickling) are plain dicts and are not recorded.
   Iteration-based reads (`items()`, `**cfg`, `json.dump`) are deliberately not
   recorded either. A full capture with `REGRESSION_RECORD_CFG=0` (no wrapper)
   is identical to the golden apart from `cfg_access`, so the wrapper does not
   change behaviour.
8. **QICK version.** `__meta__.qick` holds `qick.get_version()` at capture
   time; any other installed version fails every golden test with a message
   saying so.
9. **Determinism.** BLAS/OpenMP thread pools are pinned to one thread
   (`threadpoolctl`). With several threads, sklearn's `KMeans` (inside
   `MixedShots`) is not bit-reproducible and `curve_fit` amplified the jitter
   to about 1e-8 relative in `overlap_mat`, which changed its digest from run
   to run.

## What one capture contains

The driver executes the fixture's sections 1-2 (parameters, flags, param dicts)
verbatim, then parses section 3 (EXECUTE). For a set of flags it runs section
3's statements in source order: every unconditional statement
(`build_context`, `rebuild_singleshot_config`, `ctx.yoko.close()`) and the
bodies of the selected `if <Flag>:` blocks only, i.e. exactly what the runner
does with only those flags set, whatever their values in the file. Every flag
gets a run of its own.

Per (variant, run label) the golden holds:

* `outcome`: `completed`, `stopped_at_budget`, or `raised` (type, message, traceback tail).
* `yoko_writes`: every `OPEN`/`W`/`Q`/`CLOSE` on the voltage source, in order.
* `experiments`: every captured `ExperimentClass` instantiation, in order, with
  * `cls`, `path`, `outerFolder`, `fname` (data root and timestamps masked);
  * `cfg`: the full config dict right after `ExperimentClass.__init__`;
  * `methods`: `acquire`/`display`/`save_data`/`save_config`/`analyze` calls with
    their non-data kwargs, `sets`, `raised`, `data_digest`, `cfg_digest`,
    `cfg_delta` (identical consecutive calls run-length encoded as `count`);
  * `hw`: what that experiment sent to the board while its `acquire` ran: call
    counts, number of (unique) tProc programs, and a sha256 over the ordered
    stream of compiled binaries, pulse envelopes, nyquist/readout/buffer
    configuration and readout requests.
* `hw_outside_experiments`: board calls made outside any `acquire` (e.g. `reset_gens`).
* `skipped`: instantiations run but not captured, per `cls/path`.
* `cfg_access`: cfg keys read and written, per experiment class.

## How the hardware is faked

| Real | Fake |
|---|---|
| `makeProxy()` (Pyro4) | `(FakeSoc(), FakeSocCfg())`, patched in `socProxy` and every module that star-imported it. |
| `QickConfig` | A genuine `QickConfig` over `capture.BOARDS[variant]`: tProc v1 at 430.08 MHz, 7 mixer-less `axis_signal_gen_v6` gens, 2 `axis_readout_v2` readouts at 307.2 MHz. Gen fabric 430.08 MHz (A) or 614.4 MHz (B); readout *i* on tProc input *i* (A) or *i + 2* (B). Every program compiles through real QICK code. |
| `QickSoc` | `FakeSoc`: records every call; answers readout requests with seeded two-blob IQ data of exactly the shape QICK returns. |
| `pyvisa.ResourceManager` | `FakeYoko` that tracks its level and output state (OFF on open, voltage mode, 10 V range), so `open_charge_yoko` takes the output-off path and `ramp_to` terminates and reads back. |
| `time.sleep`, `plt.show`, `plt.pause`, `Figure.savefig` | No-ops. |
| `datetime` in project modules | Virtual clock, +1 s per `now()`, reset each run (otherwise back-to-back experiments with sleeps disabled would share an h5 filename). |

Experiments run their real `acquire()` and `display()` against `FakeSoc`, so the
synthetic data always has the shape the code expects and every program the code
builds is compiled. `save_data` and `save_config` run for real into a throw-away
temp dir, because downstream analysis (`analyze_parity_run`) reads the saved file
back. `StopCapture` is a `BaseException`, so the code under test cannot swallow
it. RNGs are seeded from the run label, so runs are independent of order.

## What a passing test proves

For the CSTQ03 parameters in the frozen runner, for each label, on both boards:

* the same experiment classes are created in the same order, with the same
  `path`/`outerFolder` and an identical `cfg` (every key; `int` vs `float`
  compared strictly, floats to a relative 1e-9);
* the same experiment methods are called with the same arguments, set the same
  attributes to the same values (fits included), and save the same payloads
  (digest-exact at ~9 significant digits) and the same final cfg;
* the board receives byte-identical tProc binaries, envelopes and channel
  configuration, in the same order;
* the yoko receives the same command sequence;
* the same cfg keys are read and written by each experiment class.

`tests/test_program_timing.py` additionally pins, on both boards:
`ModifiedRamseyProgram.scheduled_rep_period_cycles()` without reset and with
1 and 2 reset cycles; `UndrivenSingleShotProgram.scheduled_rep_period_cycles()`
and its refusal of a register-based `sync`; `readout_window_cycles`,
`readout_tone_cycles`, `readout_tone_extension_cycles`, `adc_trig_offset_cycles`
of SingleShot/ModifiedRamsey/ActiveResetVerify/UndrivenSingleShot (and that B
gives a different `readout_tone_cycles` than A); compiled program length of
T1 and ModifiedRamsey; the tProc input of the active-reset `read` (both MR and
ARV resolve `tproc_ch` through the shared `ActiveResetMixin`; ARV used to pass
the readout index, fixed 2026-10-13) and both `cmp_offset`s (`ro_norm << 15`);
ARV's sign-safe threshold immediate, its `reset_force_pi` (no `condj`), the
`safe_regwi` split of a threshold immediate above 2^30, and the read-latency stall
before each reset `read` (MR and ARV: `waiti` to window end + 0.5 us before the
`synci`, floor clamped, `ValueError` unless `reset_readout_relax_delay` exceeds it by
>= 0.2 us in tProc cycles;
fixed 2026-10-13, the pre-fix `waiti` stopped at the window end).

## What it cannot prove

* **Data-dependent control flow is only tested on synthetic data.** Everything
  downstream of an acquisition (peak finding, fits, sweet-spot searches, which
  voltage a search walks to, how many cycles a loop runs before a criterion is
  met) follows the seeded noise, not physics. Branches that this data never
  takes are not covered.
* **tProc programs are compiled and fingerprinted but never executed.** Whether
  a program is *correct* (timing, conditional reset, loop counts) still rests
  on code review, on the pinned numbers in `test_program_timing.py`, and on
  `verify_ModifiedRamsey_timing.py` against the board.
* **The boards are synthetic.** Clocks and buffer sizes are realistic; channel
  count, refclk and DDS widths are invented. **No gen has a digital mixer**:
  with `has_mixer=True` on gen 0 (the resonator) every program that declares it
  without `mixer_freq` (Rabi, T1, T2, T2E, SingleShot, ARV, MR, Undriven,
  readout optimisation, ...) raises `RuntimeError` in `declare_gen`, so that
  board would have tested nothing; only Transmission/SingleTone/ChiShift/ZSP
  pass `mixer_freq`. The mixer branches of QICK are therefore not exercised.
* **Only the first 4 instantiations of each (class, path) pair are captured.**
  Later loop iterations are assumed to repeat the pattern. In particular a
  periodic variant inside a loop (e.g. the every-10-cycles readout
  re-calibration) is not captured if it shares class and path with an
  already-saturated kind. The ModifiedRamsey validation controls have a path of
  their own (`ModifiedRamsey_Controls`), so the cycle-0 and cycle-10
  `flip_final_pi2` controls are captured; `echo_null` is infeasible with the
  file's parameters, so the run lists it among its skipped controls and never
  instantiates it. Runs end after 8 consecutive skips.
* **Some stages are still not reached** with the file's parameters:
  `RunModifiedRamsey_Control` spends its budget in the sweet-spot search (use
  `[verified]`), `RunAutoCoherence` in the readout-gain optimisation (use
  `[fast]`), and `RunChargeDispersionRamsey` raises before any experiment (a
  real legacy bug, below).
* **Float digests are exact at ~9 significant digits.** A refactor that changes
  arithmetic order can, very rarely, move a value across a rounding boundary
  and flip a digest even though the value moved by one ulp; the `head` values
  (compared at 1e-9) show whether that is what happened.
* **`display` exceptions are swallowed** (recorded as `raised`), unlike on
  hardware; with real data these displays would normally not raise.
* **Only the CSTQ03 parameter set** in the frozen runner is exercised.
* `traceback` entries are diagnostic only and excluded from the comparison
  (their line numbers move with any edit).

## Run labels (golden at commit time)

40 labels per board variant: 30 runner flags, 6 override variants
(`Flag[name]`, including the v1 `[validate]` variant), and 4 multi-flag labels
(`FlagA+FlagB`, flags run in runner order). Labels stay the legacy flag names.

| Variant label | Override applied after sections 1-2 | Why |
|---|---|---|
| `RunZeroSpanParity[validate]` | every `Validate_*` / `Build_*` flag = True | validation harness |
| `RunModifiedRamsey[no_reset]` | `ModifiedRamsey_params["use_active_reset"] = False` | no-reset MR program path |
| `RunModifiedRamsey_Control[verified]` | `ModifiedRamsey_Control_params["sweet_spot_max_df_mhz"] = 1e9` | search accepts at once, so the MRC Ramsey stage runs |
| `RunAutoCoherence[fast]` | `AutoCoherence_override_params` += `auto_readout_opt=False, ss_gain_pts=3, T1_expts=5, T2_expts=5, T2E_expts=5` | reaches T1, T2R and T2E stages |
| `RunT2E[rotation]` | `T2E_params` += `rotation_angle=0.3, min_max=[0.0, 1.0]` | rotation branch of T2E |
| `RunChargeSweep[yoko_fixed]` | session flag `yoko_fixed = True` | held-bias repeat: one `:SOUR:LEV?` read-back, held `current_voltage` + `nominal_voltage`/`repeat_index`/`acq_time` per slice |
| `RunTransmissionSweep+RunAmplitudeRabi` | none | `pulse_freq` carried from the transmission fit into Rabi |
| `Run2ToneChargeDispersionQuasiCW+RunChargeDispersionQuasiCW` | `TwoToneChargeDispersion_params["num_cycles"] = 1` | `probe_freq` leak; one cycle so the second dispatch is reached at all |
| `RunActiveResetVerify+SingleShot` | none | `res_phase` set by ARV calibration, discarded by the rebuild |
| `RunTransmissionSweep+Run2ToneSpec` | none | transmission result carried into spectroscopy |

Outcomes are identical on both boards (every experiment's `hw` digest differs
between them). Full capture: ~13 min for both boards in one process (pytest,
24-core Windows box, BLAS pinned to one thread), dominated by
`RunUndrivenSingleShot` (~2 min per board: the real 1e6-shot analysis),
`RunInterleavedCoherence` (~75 s), `SingleShot_QubitOptimize` (~26 s),
`RunZeroSpanParity[validate]` (~30 s).

| Run label | Outcome | Captured | Skipped | Classes (count) | tProc programs |
|---|---|---|---|---|---|
| `Constant2Tone` | stopped_at_budget | 4 | 9 | ConstantTwoTone x4 | 4 |
| `ConstantTone` | completed | 1 | 0 | SingleTone x1 | 100 |
| `RunTransmissionSweep` | completed | 1 | 0 | CavitySpecFF x1 | 201 |
| `RunTransmissionSweeps` | completed | 1 | 0 | CavitySpecFF x1 | 201 |
| `Run2ToneSpec` | completed | 1 | 0 | QubitSpecSliceFF x1 | 1 |
| `RunSpecGainLengthSweep` | stopped_at_budget | 4 | 9 | QubitSpecSliceFF x4 | 4 |
| `RunChiShift` | completed | 1 | 0 | ChiShift x1 | 202 |
| `Run2ToneChargeDispersionQuasiCW` | stopped_at_budget | 8 | 13 | QubitSpecSliceFF x4, ChargeDispersionQuasiCW x4 | 8 |
| `RunModifiedRamsey` | stopped_at_budget | 10 | 18 | SingleShotProgramFFMUX x4, ModifiedRamsey x6 (4 records, 2 `ModifiedRamsey_Controls`) | 14 |
| `RunModifiedRamsey[no_reset]` | stopped_at_budget | 9 | 16 | SingleShotProgramFFMUX x3, ModifiedRamsey x6 (4 records, 2 `ModifiedRamsey_Controls`) | 12 |
| `RunModifiedRamsey_Control` | stopped_at_budget | 4 | 9 | QubitSpecSliceFF x4 | 4 |
| `RunModifiedRamsey_Control[verified]` | stopped_at_budget | 8 | 9 | QubitSpecSliceFF x4, ModifiedRamsey x4 | 8 |
| `RunChargeDispersionQuasiCW` | completed | 1 | 0 | ChargeDispersionQuasiCW x1 | 1 |
| `RunChargeDispersionRamsey` | raised (KeyError 'df') | 0 | 0 | - | 0 |
| `RunAmplitudeRabi` | completed | 1 | 0 | AmplitudeRabiFF x1 | 1 |
| `RunT1` | stopped_at_budget | 4 | 9 | T1FF x4 | 4 |
| `RunT1T2E` | stopped_at_budget | 8 | 9 | T1FF x4, T2EMUX x4 | 8 |
| `RunT1T2RT2E` | stopped_at_budget | 12 | 9 | T1FF x4, T2EMUX x4, T2R x4 | 12 |
| `RunT2` | stopped_at_budget | 4 | 9 | T2R x4 | 4 |
| `RunT2E` | stopped_at_budget | 4 | 9 | T2EMUX x4 | 4 |
| `RunT2E[rotation]` | stopped_at_budget | 4 | 9 | T2EMUX x4 | 4 |
| `RunTrans_QubitSpec` | stopped_at_budget | 4 | 9 | QubitSpecSliceFF x4 | 4 |
| `RunChargeSweep` | completed | 4 | 6 | QubitSpecSliceFF x4 | 4 |
| `RunChargeSweep[yoko_fixed]` | completed | 4 | 6 | QubitSpecSliceFF x4 | 4 |
| `RunChargeTransmissionSweep` | completed | 4 | 6 | CavitySpecFF x4 | 804 |
| `RunActiveResetVerify` | completed | 7 | 2 | SingleShotProgramFFMUX x3, ActiveResetVerify x4 | 10 |
| `RunInterleavedCoherence` | stopped_at_budget | 12 | 9 | UndrivenSingleShot x4, T1FF x4, T2R x4 | 12 |
| `SingleShot` | completed | 1 | 0 | SingleShotProgramFFMUX x1 | 2 |
| `RunUndrivenSingleShot` | stopped_at_budget | 4 | 9 | UndrivenSingleShot x4 | 4 |
| `RunT1SS` | stopped_at_budget | 8 | 9 | SingleShotProgramFFMUX x4, T1_SS x4 | 408 |
| `SingleShot_ReadoutOptimize` | completed | 1 | 0 | ReadOpt_wSingleShotFF x1 | 294 |
| `SingleShot_QubitOptimize` | completed | 1 | 0 | QubitPulseOpt_wSingleShotFF x1 | 882 |
| `RunAutoCoherence` | stopped_at_budget | 5 | 9 | AmplitudeRabiFF x1, SingleShotProgramFFMUX x4 | 9 |
| `RunAutoCoherence[fast]` | completed | 14 | 3 | AmplitudeRabiFF x1, SingleShotProgramFFMUX x4, T1FF x3, T2R x3, T2EMUX x3 | 18 |
| `RunZeroSpanParity` | completed | 3 | 0 | QubitSpecSliceFF x1, SingleShotProgramFFMUX x1, ZeroSpanParity x1 | 63 |
| `RunZeroSpanParity[validate]` | completed | 3 | 0 | QubitSpecSliceFF x1, SingleShotProgramFFMUX x1, ZeroSpanParity x1 | 257 |
| `RunTransmissionSweep+RunAmplitudeRabi` | completed | 2 | 0 | CavitySpecFF x1, AmplitudeRabiFF x1 | 202 |
| `Run2ToneChargeDispersionQuasiCW+RunChargeDispersionQuasiCW` | completed | 4 | 0 | QubitSpecSliceFF x2, ChargeDispersionQuasiCW x2 | 4 |
| `RunActiveResetVerify+SingleShot` | completed | 8 | 2 | SingleShotProgramFFMUX x4, ActiveResetVerify x4 | 12 |
| `RunTransmissionSweep+Run2ToneSpec` | completed | 2 | 0 | CavitySpecFF x1, QubitSpecSliceFF x1 | 202 |

The multi-flag labels do see their carry-overs: Rabi after the transmission
fit runs at `pulse_freq` 7099.50 MHz (7095.4 alone), and the quasi-CW after the
two-tone search starts at 2650.99 MHz (2306.57 alone).

**`RunChargeDispersionRamsey` raises before any capture, and that is a real
legacy bug, not a harness artefact.** `run_charge_dispersion_ramsey` reads
`ChargeDispersion_params["df"]`, but the runner's `ChargeDispersion_params` has
no `"df"` key (`upper_freq`, `lower_freq`, `probe_freq`, `relax_delay`,
`repetitions`). It would raise the same `KeyError` on hardware. The golden
records the raise so the refactor has to decide on it deliberately.

Checked before committing: the golden was generated with
`REGRESSION_UPDATE=1`, and a second full capture in a separate process is
byte-identical to it; `python -m pytest tests` passes against it in a third
process; a capture with `REGRESSION_RECORD_CFG=0` equals it apart from
`cfg_access`.

## Platform of the golden (regenerated 2026-10-13 on macOS)

The golden now in the tree was captured on an Apple Silicon Mac (arm64, Python
3.13.2, qick 0.2.334, numpy 2.4.1 with Apple Accelerate, scipy 1.17.0,
scikit-learn 1.8.0) on the untouched legacy tree. Against the original Windows
golden (same package versions, x86 OpenBLAS/MKL) it differed in 804 leaves over
15 labels per board, identical on A and B. Every primary difference is the
output of an iterative fit on synthetic noise, where ulp-level differences in
numpy's per-architecture SIMD math and scipy's compiled MINPACK move the
optimizer: `lorentz_*` (two-tone Lorentzian fits), `hanger_fit_*` (transmission
hanger fit), `env_fit`/`osc_fit` (T2R display fits), `ts_acf_*` and the
`projection*` columns (undriven time-series fits and threshold), `overlap_mat`
(KMeans in `MixedShots`). The hanger fit is ill-conditioned on this data (its
`Qint` moved from 2.2e8 to 2.7e5), so its `f0` moved too.

The only `cfg`/`hw` differences were the deterministic consequence of that
`f0`: `run_transmission_sweep` stores it as `ctx.config["pulse_freq"]`, so in
the two carry-over labels `RunTransmissionSweep+Run2ToneSpec` and
`RunTransmissionSweep+RunAmplitudeRabi` the second experiment's `cfg.pulse_freq`
(7098.80 -> 7095.55 MHz and 7099.804294 -> 7099.804219 MHz), its compiled
program (`hw.digest`, `hw.first_program`) and its `save_config` digest changed.
No other cfg key, program hash, method sequence, `yoko_writes` or `cfg_access`
entry differed. Bit-exact agreement with the Windows capture is not reachable
by an environment change (the arithmetic is not in BLAS), so the golden was
regenerated here, two further captures in separate processes were confirmed
byte-identical, and all later phases are measured against this capture. A
golden captured on a different architecture will show the same 15 labels.

## After the refactor

`driver_qicklab.py` (now the `DRIVER` in `test_golden.py`) is `driver_legacy.py`
with only the package constants switched (`RUNS_PACKAGE = "qicklab.runs"`, the
`ExperimentClass` from `qicklab.core.experiment`, `make_proxy` and its alias
`makeProxy` in `qicklab.hardware.rfsoc`), reading the same frozen fixture with the
same legacy run labels; until phase 3a-ii it also installs the virtual clock in the
modules still under `WorkingProjects.`.
Differences that are intentional must be justified one by one before the
golden is regenerated.

## Existing offline scripts

Run with the venv Python from the repo root on 2026-10-13:

| Script | Result | Needs hardware? |
|---|---|---|
| `Experiments/test_ModifiedRamseyParity_offline.py` | 131 passed, 0 failed (exit 0, ~45 s) | No |
| `Experiments/verify_ModifiedRamsey_timing.py` | 42 passed, 0 failed (exit 0, ~4 s) | **Yes.** It connects over Pyro4 to `myqick` at `192.168.0.103:8888` and checks programs against the board's real `QickConfig`. Run without `--acquire`, it only reads the config and compiles; nothing plays. Off the lab network it fails at `locateNS`. |
