# Architecture

How qicklab is put together, why it is layered the way it is, and the QICK/tProc facts the
code depends on. Read [running_a_session.md](running_a_session.md) first if you only want to
take data; this page is for people who change the code.

> Status (2026-10-13): the `qicklab_refactor` branch is mid-migration. This page describes the
> target layout from the refactor design. Module names under `qicklab.` are final; function
> signatures of the session layer may still move until phase 5 lands.

## Package layout and layering

```
devices/        one file per chip+cooldown (Device dataclass); archive/ for old cooldowns
runners/        <device>_session.py: the per-session script a researcher edits
qicklab/
  hardware/     rfsoc, board (BASE_CONFIG), yoko, attenuator, sc5510a, pnax, synthhd
  core/         experiment (ExperimentClass), device, context, config, session, params,
                acquisition, readout, active_reset, schedule, io, fakes
  analysis/     iq, fitting, spectroscopy, ramsey, readout, plotting, hmm, rates, dwell,
                undriven, modified_ramsey, zero_span, zero_span_checks
  experiments/  one module per experiment family (QICK program + ExperimentClass subclass)
  runs/         run functions (one per step), recipes.py, the STEPS registry
  twpa/         standalone TWPA bias/pump/sweep scripts
tests/          regression golden, offline tests; tests/hardware/ (not collected)
scripts/        gen_docs.py (parameter registry -> docs/parameters.md)
```

Import direction is one way:

```
hardware  <  core  <  analysis  <  experiments  <  runs  <  twpa
```

Rules (enforced by `tests/test_layering.py`):

- `analysis` never imports `experiments`, `runs` or `qick`. Analysis must run offline on saved
  h5 files, on a laptop without the board.
- `core` never imports `runs`.
- No function-local project imports. They hide cycles and the regression harness patches only
  modules already in `sys.modules`.
- `qicklab/__init__.py` is empty. Import what you need explicitly
  (`from qicklab.core.session import Session, run`). Importing a leaf module must not drag in
  qick, sklearn, pyvisa and matplotlib.
- No hardware access at import time anywhere.

Why: the legacy tree star-imported everything (`from runs import *` pulled ~110 names,
including `np`, `plt`, every experiment class and helper functions whose names collided with
run functions). Star-import shadowing silently changed which `fit_rabi_cosine` or `datetime`
a module used. Explicit imports plus layering make every binding visible.

## The two-class experiment pattern

Every experiment is two cooperating classes in one module under `qicklab.experiments`:

1. A QICK program (`AveragerProgram`, `RAveragerProgram` or `NDAveragerProgram` subclass).
   `initialize()` declares generators, readouts, envelopes and registers; `body()` plays the
   sequence. This code is compiled to tProc assembly and runs on the RFSoC.
2. An `ExperimentClass` subclass (from `qicklab.core.experiment`) that wraps the program:
   builds it from `cfg`, calls `acquire()`, `display()` (plots + fits), `save_data()` and
   `save_config()`.

Experiment class names are unchanged by the refactor (`T1FF`, `T2EMUX`, `T2R`,
`ModifiedRamsey`, `SingleShotProgramFFMUX`, ...). Where two legacy modules both defined a
program class with the same name, one was renamed (`AmplitudeRabiPointProg`,
`T1SingleShotProgram`).

### File naming (must stay byte-identical)

`ExperimentClass.__init__(path, outerFolder, prefix="data", ...)` takes one timestamp and
derives three file names:

```
dir   = os.path.join(outerFolder + path, path + "_" + "%Y_%m_%d")
fname = os.path.join(dir, path + "_" + "%Y_%m_%d_%H_%M_%S" + "_" + prefix + ".h5")
iname = same stem + ".png"
cname = same stem + ".json"
```

`outerFolder + path` is plain string concatenation with no separator, so `outerFolder` must
end in `/`. That is why `Device.folder(q)` returns `f"{data_root}/Q{q}//"` and why
AutoCoherence builds its run folder with a trailing `"/"`. The mixed `/`, `//`, `\` in the
resulting paths is what is on disk today; do not "fix" it with `pathlib`, because the strings
are saved and printed and some code compares them. `path` is both the sub-folder name and the
file stem. `os.makedirs` runs in `__init__`, so constructing an experiment creates its folder.

### h5 and json writing

- `save_data(data)` writes one dataset per key, always as float64 with resizable shape.
  Complex, string and object arrays cannot go through the base class; experiments that need
  them (ZeroSpanParity) override `save_data`, open the file in `"a"` mode so the `config`
  attribute is not truncated, and delete-then-recreate datasets so a re-save is idempotent.
- Re-saving an existing key through the base class raises `ValueError` (h5py 3 behaviour; the
  legacy `except RuntimeError` overwrite branch never fires).
- `save_config()` writes the full `cfg` to the `.json` and to the h5 attribute `config`
  (JSON string). That attribute is how you recover the exact settings of any file.
- Scripts are intentionally not embedded in the h5. An automatic save-script feature existed
  and was removed: "caused more trouble than convenience" (Ge Yang, legacy CoreLib comment).

### Display never loses the record

Run functions do not call `display`, `save_data` and `save_config` one after another; they
call `finish(Cls, inst, data, reraise=..., **display_kw)` from `qicklab.core.experiment`
right after `acquire`. It runs `Cls.display(inst, data, **display_kw)` and then, in a
`finally`, `Cls.save_data(inst, data)` and `Cls.save_config(inst)`. The order is unchanged
(some displays write fit fields into `data`, and T1/T2E `save_data` renames `fname`, so
`save_config` must come last), but a display that raises (a fit on noise-only data) or is
interrupted (Ctrl-C on a blocking plot window) no longer throws away the h5 and json: the
traceback is printed and `repr(exc)` is stored on `inst.display_error`. Inside repetition
loops (`t1`, `t2r`, `t2e` and their combinations, sweeps, charge/MR cycles, AutoCoherence
stages) the error is not re-raised, so the loop continues. Single runs (`transmission_*`,
`two_tone_spec`, `amplitude_rabi`, `chi_shift`, `single_shot`, the optimisers, the
zero-span recalibration spec) pass `reraise=True`: the error still stops the step, after the
files are on disk. A Ctrl-C is never swallowed. `finish` takes the class explicitly, so a
call site that names a parent class keeps calling that class's methods.

## How configuration flows

```
hardware/board.py BASE_CONFIG      channel wiring, nqz, trig_*, cavity_winding_*, defaults
        |  merged with Device.setup.board_overrides
        v
devices/<NAME>.py  Device          per-qubit freq/gain/sigma, readout freq/gain/window, parity
        |  selected by Session(qubit_readout, qubit_pulse)
        v
qicklab/runs/recipes.py  R.<x>()   library defaults (documented sane values)
        |  < session group (Session(spec=R.spec(...), ...))  < per-step kwargs (R.t1(relax_delay=...))
        v
core/config.py  measurement_config() (regime A) / singleshot_config() (regime B)
        |
        v
core/context.py  Context           soc, soccfg, yoko, config, derived scalars
        |  step.fn(ctx, *groups, **params) -> ctx.working_config(...) -> experiment cfg
        v
ExperimentClass(cfg=...)           saved verbatim to .json and h5 attrs["config"]
```

`cfg` key names are unchanged by the refactor, including the misspelled `Read_Indeces` and the
double-meaning `qubit_gain`. Renames are a later, separate decision.

### The two config regimes

User-facing explanations: [concepts/config_regimes.md](concepts/config_regimes.md),
[concepts/readout_window.md](concepts/readout_window.md),
[concepts/timing_and_units.md](concepts/timing_and_units.md).

| | Regime A (`measurement_config`) | Regime B (`singleshot_config`) |
|---|---|---|
| Legacy builder | `build_context` | `rebuild_singleshot_config` |
| Steps | transmission, spectroscopy, chi shift, Rabi, T1/T2R/T2E, charge dispersion, Modified Ramsey, active-reset verify | single shot, undriven single shot, T1 single-shot, readout/qubit optimise, AutoCoherence, zero-span parity |
| Readout window | `Device.readout_window` (or the qubit's `Readout.window`) | `Device.ss_window` (or the qubit's `Readout.ss_window`) |
| `qubit_gain` means | spectroscopy drive gain (the `spec` group) | pi-pulse gain (`Qubit.gain`) |
| Built from | `BASE_CONFIG` + transmission/spec/tones/charge groups | `BASE_CONFIG` + single-shot group (not from the regime-A config) |

Regime B is built from `BASE_CONFIG`, not from the current config, so it discards both
carry-overs (below). `reps` stays at the `BASE_CONFIG` 1000 in regime B; single-shot programs
set their own shot count.

### Readout window

`readout_length` is the ADC integration window; `adc_trig_offset` is the delay from tone start
to ADC trigger; the resonator tone `length` is derived as `adc_trig_offset + readout_length`
(the tone starts at t = 0, the ADC later, so the tone must last through offset + window). Do
not set `length` by hand. A longer window improves SNR per shot until it approaches the
qubit T1; past that the tail of the integration just averages in decayed `|e>` population.
The single-shot family has its own window; zero-span parity overrides it again with its own
`read_length`. If no ADC offset is given the `BASE_CONFIG` value (1 us) is kept. The legacy
builder printed the window at connect:
`[readout window] integration 15 us, adc_trig_offset 0.3 us, resonator tone 15.3 us`.

Single-shot, Modified Ramsey, ActiveResetVerify, T1_SS and the regime-A programs must
integrate the same physical ADC window and play the same tone, because thresholds and windows
calibrated in one are consumed by the others.
Each duration is converted with its owning clock (tProc for the trigger offset, readout clock
for the window, generator clock for the tone) and the tone is extended by the minimum number of
generator cycles needed after cross-clock rounding:
`ceil(adc_end_tproc * f_fabric / f_time - 1e-12)`. The shared function is
`qicklab.core.readout.cover_readout_window` (used by SingleShotProgram, ModifiedRamsey,
ActiveResetVerify, UndrivenSingleShot, T1_SS and every regime-A program).

### Carry-overs

`ctx.config` is the persistent instrument config. Steps take a fresh copy
(`ctx.working_config(...)`) for transient knobs, so reps/spans/gains never leak. Only two
measured values are written back:

| key | written by | lost when |
|---|---|---|
| `pulse_freq` | `transmission_fit` and `transmission_sweep` with `cavity_min`: `hanger_fit_min_freq_mhz`, the minimum of `CavitySpecFF.display()`'s hanger-fit curve (raw argmin, with a printed warning, if that fit failed); `transmission_sweep` without `cavity_min`: raw argmax. Written only if the trace passes the [carry-over gate](experiments/transmission_fit.md#carry-over-gate); otherwise left unchanged | next switch to regime B |
| `res_phase` | active-reset readout calibration (`modified_ramsey` with reset, `active_reset_verify`) | next switch to regime B |

`interleaved_coherence` swaps `ctx.config` between the two regimes per step and restores it in
`finally`. Calibrated values meant to survive a session go through calibration write-back
(`core.io.record_calibration`, see [adding_a_device.md](adding_a_device.md#calibration-write-back)),
not through `ctx.config`.

Side effect to know about: `CavitySpecFF.acquire()` sweeps `cfg["pulse_freq"]` in place and
`display(fit=True)` rewrites it with the fitted minimum. Code that runs several transmission
slices (charge transmission sweep) resets it to the centre for every slice.

## Comment policy

Keep: docstrings of three lines or fewer on public symbols; a one-line "why" at an enforced
constraint with a `docs/...#anchor` pointer; recipe parameter docs (that is where users look).
Move to `docs/`: measured values, root causes, physics bounds, tuning advice (keep dates and
numbers). Delete: comments that restate code, commented-out code, banners, stale TODOs, debug
prints. Exception: `devices/*.py` keep short dated history inline next to each qubit. Hazards
next to a knob become runtime checks (each in its own fix commit) or a recipe-parameter doc
line.

## Regression harness and the bug-fix rule

`tests/regression/` replays every legacy run with the hardware faked (`FakeSoc`, a genuine
`QickConfig` over a synthetic board, a fake yoko, a virtual clock) and compares against a
golden snapshot: the experiment classes created, their full `cfg`, method calls, the SHA-256
of every compiled tProc program/envelope/readout config, and the yoko command stream. A pass
proves the refactored code sends the same things to the hardware for the CSTQ03 parameter
set. It does not prove the programs are physically right; that rests on review and on
`tests/hardware/verify_modified_ramsey_timing.py` against the board. Details and limits:
`tests/regression/README.md`.

Rule: behaviour-preserving refactors and bug fixes are separate commits. A refactor commit
must leave the golden green (only documented dead-key diffs are allowlisted). A fix commit
changes behaviour on purpose and updates the golden explicitly, with the diff justified in the
commit. The list of known, unfixed legacy bugs is in the refactor design; each experiment page
has a "Known issues" section.

## Adding an experiment, a step, a recipe

1. Experiment: add `qicklab/experiments/<family>.py` with the program class and the
   `ExperimentClass` subclass. Read every cfg value with `cfg["key"]` (no silent defaults for
   physics values). Use `freq2reg`, `us2cycles`, `deg2reg`; never compute register values by
   hand. Gaussian envelopes are `4*sigma` long.
2. Run function: add `fn(ctx, *groups, **params)` in the matching `qicklab/runs/<area>.py`.
   Build the experiment cfg from `ctx.working_config(...)`; do not mutate the caller's dicts.
   Call `acquire`, then `finish(Cls, inst, data, ...)` for display + save
   ([display never loses the record](#display-never-loses-the-record)).
3. Recipe: add a keyword-only function to `qicklab/runs/recipes.py` with explicit parameters,
   snake_case names, defaults and a one-line doc each. It returns the legacy-keyed dict the run
   function consumes and a `Step(name, fn, regime, needs, params)`. Device-dependent values
   default to `None` and resolve from `session.qubit(q)` at run time. Unknown keywords must
   raise `TypeError`.
4. Register the step in the `STEPS` registry (`qicklab/runs/__init__.py`), with its regime
   (`"A"` or `"B"`) and the session groups it needs.
5. Parameter registry: add every new key to `PARAMS` in `qicklab/core/params.py`, keyed by
   `(key, scope)` with units. `tests/test_params_registry.py` records the keys each experiment
   actually reads at runtime and fails if one is missing.
6. Docs: add `docs/experiments/<step>.md` (template: What it measures, Pulse sequence, How to
   run, Parameters, Outputs, Analysis, Findings & notes, Known issues) and regenerate tables
   with `python scripts/gen_docs.py`.
7. Regression: add a run label to the driver so the new step is fingerprinted.

## Testing

From the repo root with the venv active:

```
ruff check .
ruff format --check .
python -m compileall -q qicklab devices runners tests
python -m pytest tests                         # everything collected, incl. the golden (~5 min)
python -m pytest tests -m "not slow"           # skip the long offline analysis tests
python -m pytest tests/regression -q           # golden only
REGRESSION_LABELS=RunT1,RunT2 python -m pytest tests/regression -q
REGRESSION_UPDATE=1 python -m pytest tests/regression -q   # rewrite golden: fix commits only
python scripts/gen_docs.py                     # regenerate docs/parameters.md
```

`tests/hardware/verify_modified_ramsey_timing.py` is hardware-in-the-loop and not collected by
pytest. Run it by hand on the lab network; without `--acquire` it only reads the board's
`QickConfig` and compiles (nothing plays); with `--acquire` it drives the tProc at zero gain.
Off the lab network it fails at `locateNS`. Last recorded results before the move (October
2026 audit, legacy tree, each run as a module with `python -m` from the repo root with
`PYTHONPATH` = repo root):

- offline Modified Ramsey suite: 131 passed / 0 failed, 42 s, no board needed (qick must be
  importable);
- timing verify phase 1 (read-only `soc.get_cfg()` + compile against `192.168.0.103:8888`,
  `myqick`): 42 passed / 0 failed, 5 s; phase 2 (`--acquire`, zero gain) was not run in the
  audit; `--help` works offline;
- inline self-tests: acquisition/IQ/fit helpers 6 blocks, 2 s; zero-span analysis 17 blocks,
  180 s (pure-Python Markov loops, hence the `slow` marker); zero-span validation 6 blocks,
  40 s.

Recorded client environment: Python 3.13, qick 0.2.334, numpy 2.4.1, scipy 1.17.0,
matplotlib 3.10.8, scikit-learn 1.8.0.

## QICK and tProc facts the code relies on

Measured on the lab board (read from its `QickConfig` during the October 2026 audit): tProc
`f_time` 430.08 MHz (one cycle = 2.32515 ns = 0.00232515 us); gen0/gen1 `f_fabric`
430.08 MHz; readout ro0 `f_output` 307.2 MHz; `avg_maxlen` 16384; `buf_maxlen` 1024. Client
qick is pinned at 0.2.334; the board runs qick 0.2.367 (per the shot-buffer helper's notes).

### Timing

- Waits are between pulse edges. `sync_all()` advances to the end of the last envelope. QICK
  tracks generator/readout timestamps in native cycles converted to tProc cycles; `sync_all()`
  truncates the largest to an integer tProc cycle.
- Only `synci` advances tProc time. The `waiti` that `measure(wait=True)` emits does not. A
  register-valued `sync` inside a loop makes the rep period not a compile-time constant (the
  undriven single-shot schedule raises in that case).
- Echo-type sweeps quantise their step: T2E uses `step = c * (n_pi + 1) * k`, with the tProc
  cycle `c = soccfg.cycles2us(1)` read from the board (`core.schedule.tproc_cycle_us`), so each
  of the `n_pi + 1` segments is an integer number of tProc cycles. The coherence run functions
  and AutoCoherence share one function (`experiments.t2_echo.quantised_t2e_step`).
- Streamer statistics include polling and transfer latency. The physical time base of a
  shot record is the emitted tProc schedule (including active-reset overhead), not wall-clock.
- `AveragerProgram` reads `cfg["reps"]` in `make_program()` at construction; set `reps` before
  building the program.

### Readout buffers

- `rounds > 1` is unsupported for single-shot programs: `acc_buf` (and the per-shot `di_buf`)
  keep only the last round, so earlier rounds are silently dropped. Scale `reps` instead.
- qick up to about 0.2.28x exposed `di_buf/dq_buf` as the flat raw accumulated stream
  (`reps * reads_per_shot`, times `expts` for RAverager). From about 0.2.29x `_average_buf`
  averages and normalises, so `di_buf` holds one point per read and old reshapes fail
  (`cannot reshape array of size 1 into shape (1,1000)`); the raw stream is in `prog.acc_buf`,
  shaped `(*loop_dims, reads_per_shot, 2)` in raw units. The local client qick 0.2.334 still
  exposes raw `di_buf`. Only UndrivenSingleShot uses the version-robust
  `qicklab.core.acquisition.raw_shot_buffers`; SingleShotProgramFFMUX, ActiveResetVerify,
  ModifiedRamsey, ZeroSpanParity, T1_SS and ChargeDispersionQuasiCW read `di_buf` directly.
- `di_buf/dq_buf` are indexed by readout declaration order, not by absolute channel;
  `soccfg["readouts"][ro_ch]` is keyed by absolute channel.
- Single-shot `collect_shots` divides accumulated I/Q by the window length in readout cycles and
  hard-codes `ro_ch=0`. Zero-span strobe data are normalised the same way
  (`us2cycles(read_length, ro_ch=0)`), so a separator calibrated by single shot is in the same
  units.
- `acquire_decimated` returns per readout channel `(2, length)` for `reps=1` and
  `(reps, 2, length)` for `reps>1`; some code paths give `(length, 2)`. Do not pass `soft_avgs`
  to it (AveragerProgram injects it; keyword collision). On some firmware the nominal decimated
  rate in `soccfg` differs from the true rate (`soccfg.f_output_unverified`); zero-span sidecars
  keep `raw_sample_period_us`, `n_raw_samples`, `n_binned_samples`, `analysis_bin_us` and `mode`
  for post-hoc reconstruction.
- A chunked acquisition's inner `acquire()` leaves only the last chunk in `experiment.data`;
  the chunking helper assembles the full record itself.

### Generators and registers

- Envelope memory is 65536 samples per generator. A sigma = 2 us Gaussian is about 55056
  samples; two copies (about 110112) fail with
  `AxisSignalGen: buffer length must be 65536 samples or less`. Share one envelope between pi
  and pi/2.
- The DDS band is `[-f_dds/2, +f_dds/2]` (`freq2reg` range check), not `[0, f_dds]`. The qubit
  generator is declared without a mixer.
- `QickConfig` has `__getitem__` but no `__contains__`: `"gens" in soccfg` raises `KeyError`;
  use try/except.
- Pulse registers are allocated top-down per page (qick `asm_v1.py`: registers 22-31 on a
  one-manager page, 12-31 on a two-manager page). AveragerProgram uses `rjj`=14, `rcount`=15 and
  the trigger word 16 on page 0; framework-reserved registers on page 0 are 13-21. Registers
  3/4/5 are free on any page.
- tProc `read` takes the tProc input channel, not the readout index. They coincide on the
  current firmware (`readouts[0]['tproc_ch'] == 0`); resolve it explicitly anyway.
- Flat-top-calibrated pi/pi2 gains do not transfer to a Gaussian envelope; code that needs a
  Gaussian refuses flat-top gains rather than reusing them.
- The flat segment of a flat-top pulse does not follow a register-swept gain (only the ramp
  `gain` register is updated). A register-swept Rabi is therefore invalid with flat-top; the
  software-swept `AmplitudeRabiFF_N` is used when `flattop_length` is set.
- Fast-flux AWG compensation (deleted dead code, recorded in case it is revived): it used an
  envelope sample step of `0.00232515/16` us (one tProc cycle / 16 fabric samples), clipped
  the analytic compensation at -0.8 (-0.7 for long times) and limited `v_awg <= 1.5`.

### Trigger pin 0

Rabi, T1, T2E and single shot raise tProc trigger pin 0 around the qubit pulse
(`trig_buffer_start` 0.02 us before, `trig_buffer_end` 0.02 us after, `trig_delay` 0.082 us
cable/latency offset; trigger length = start + end + 4 sigma). Spectroscopy, chi shift, T2R,
T1 single-shot and charge dispersion do not. What pin 0 drives in the current fridge wiring is
not documented in the code.

### Active-reset comparison

The tProc compares as unsigned. ActiveResetVerify data on TATQ01/BFE (2026-06-05/06) showed the
corrective pi firing on every shot with negative accumulated I: ground-state damage tracked the
below-zero fraction of the g blob, and a sweep with g_I near 0 lost exactly half its ground
shots. The fix adds the same large positive offset to both operands. The offset must exceed
the largest raw |I|: the accumulator sums `ro_norm` samples of up to 15 bits (12-bit ADC plus
3 bits decimation gain), so |raw I| <= `ro_norm * 2^15`, and the offset is
`int(ro_norm) << 15`, which must stay below 2^30 (`safe_regwi`; operands must fit 32-bit
signed). History: the original fixed offset `1 << 24` assumed |raw I| of about 1e4-1e5; that
claim is superseded, `2^24` is about 9x too small for a 15 us window (2026-07-28) and can wrap
once the window exceeds 2^24 / 2^15 = 512 readout cycles (about 1.7 us at `f_output` 307.2 MHz;
the legacy code comment says "~0.5 us", which does not follow from its own bound), firing the
wrong branch with no error. A threshold check alone cannot
catch it, because the threshold sits between the blobs. ModifiedRamsey uses the corrected
offset, shared through `qicklab.core.active_reset.ActiveResetMixin`; ActiveResetVerify
carried its own copy with `1 << 24` (and the readout index as the `read` input) until
2026-10-13 and now uses the mixin too. The threshold immediate `raw_threshold + cmp_offset`
is loaded with `safe_regwi`, since it can reach 2^30 for windows above 2^14 readout cycles.
`collect_shots` thresholds are in normalised units (accumulated I / window cycles); the tProc
compares raw I, so the threshold is multiplied by the window length before loading.

### Back-to-back programs (stale shot counter)

Starting programs back to back can hit a race: the streamer zeroes the shot counter and starts
the next program while the previous one is still retiring reps, so the counter reports more
shots than ran. `acquire` then dies with
`ValueError: could not broadcast input array from shape (26,2) into shape (20,2)` (second
number = reps, first = reps + leftovers). It is intermittent and likelier the more programs a
step starts (one transmission slice starts `TransNumPoints x rounds` programs). `soc.stop_tproc()`
(tProc v1 reset and reload, tens of ms) clears it; `acquire_with_retry` retries with a fresh
program object rather than losing a long sweep. Prefer hardware `reps` over software `rounds`
for this reason. `Overflowed the averages buffer` is a different error: the tProc outran the
readout. Lengthen `relax_delay`; never retry it blindly.

## Analysis conventions

- Spectroscopy projects IQ onto its principal axis after background subtraction
  (`project_iq_signal`), never `|I + iQ|`. The magnitude is dominated by the large, noisy
  background quadrature, buries a qubit response that lies in one quadrature and washes out
  charge-sweep heatmaps; the projection gives a baseline near 0 with the qubit as a positive
  bump.
- Rotating IQ by `-angle` to put the g-e (maximum-variance) axis on I is a data-driven
  quadrature alignment. `cavity_winding_freq/offset` is something else: a
  frequency-dependent cable-delay phase correction.
- KMeans(2) always returns two centroids; with majority forcing it manufactures a ~50/50 split
  from a single blob. Gate on centroid distance / pooled within-cluster RMS: resolved blobs
  give more than about 2, a single blob less than about 1; the threshold used is 2.0.
- Readout "fidelity" printed by the legacy histogram analysis is the contrast
  C = P(g|g) + P(e|e) - 1, not assignment fidelity; with equal priors and the optimal
  threshold F_assign = (1 + C)/2.
- The two legacy histogram analyses (QM_Team pooled normalisation; Inductive_Coupler per-class
  normalisation with `print_fidelities=`) are one function, `hist_process(normalize=...)`. Since
  2026-10 it computes the contrast and threshold from the exact empirical CDFs, so both
  `normalize` strings give identical numbers ([IQ conventions section 4](concepts/iq_conventions.md)).

## Hardware notes

### Endpoints

| Instrument | Address | Notes |
|---|---|---|
| RFSoC (QICK) | Pyro4 nameserver `192.168.0.103:8888`, server `myqick` | Active board. Legacy helpers also pointed at `192.168.1.10`, `.11`, `.12`, `.119` (unused). Older docs saying `192.168.1.7` are stale. |
| Charge-line yoko (GS200) | `GPIB1::9::INSTR` | Voltage mode. Opened by `connect()`. |
| TWPA bias yoko (GS200) | `GPIB1::12::INSTR` | Current mode, dedicated. |
| TWPA pump (Windfreak SynthHD) | `COM5` | |
| PNA-X | `GPIB0::16::INSTR` | TWPA calibration only. |
| SignalCore SC5510A | Pyro5 nameserver `192.168.0.102:9090`, prefix `SC5510A#` (env `SC5510A_SERVER_HOST`) | Unused by current runs. Server code: `https://github.com/NPdL-SQTeam/sc5510a-py`; the server PC must run `start_nameserver.py` and `start_instrument_server.py`. Example id `10002D35`. |
| Vaunix LDA attenuator | DLL `VNX_atten64.dll`, serial 27786 | Unused by current runs. |

Device-specific addresses live in `Device.setup`; see [devices/CSTQ03.md](devices/CSTQ03.md).

### Yoko safety

- Ramp in software. The legacy GS200 driver used 1e-4 V steps every 0.01 s and noted the
  interval must not go below 0.001 s or the fridge heats up.
- `ramp_to` rejects |target| > 10 V (both signs) and reads the level back after landing; sweep
  helpers also validate |V| <= 10 for the whole grid before moving. `connect()` opens the yoko
  with `open_charge_yoko` (level 0 before the output goes on; refuses the TWPA address in any
  GPIB spelling, a source found in current mode with its output on, and the 30 V range):
  [hardware](hardware.md#charge-bias-yoko).
- An abort must not leave the bias parked at an arbitrary point: every later measurement would
  silently run at that charge offset. Sweeps return to the start bias on error or Ctrl-C (charge
  transmission sweep does; not every sweep does yet, see the known-bug list). `run()` closes the
  yoko in `finally`.

### Attenuator DLL

Python 3.8+ does not search `PATH` for DLLs. The attenuator driver must be given the directory
holding `VNX_atten64.dll` explicitly (`set_attenuation(db, serial, dll_dir=...)`, which calls
`os.add_dll_directory`). The DLL is not in the repository. High-resolution attenuation unit is
0.05 dB.

### TWPA instruments

- `SynthHD.__init__` disables RF on both channels and locks to the external 10 MHz reference;
  `SynthHD.close()` also disables RF on both. The set-pump script therefore deliberately does
  not close the port, to leave the pump on. Connecting to set one channel switches the other
  off.
- PNA-X sweep time is about `n_points / IF_BW` per sweep times `n_avg`. A fixed 30 s VISA
  timeout was exceeded at low IF bandwidth with many averages; the pump sweep sizes its timeout
  as 3 x estimate + 5 s with the configured timeout as a floor. The flux sweep still uses a
  fixed timeout.
