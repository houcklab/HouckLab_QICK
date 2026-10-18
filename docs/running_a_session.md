# Running a session

A measurement session is one short Python file, `runners/<device>_session.py`. It names the
device, picks the qubit, sets a few shared knobs and lists the steps to run, in order. All
physics lives in `qicklab`; all chip numbers live in `devices/<device>.py`
([adding_a_device.md](adding_a_device.md)). You should never need to edit either to take data.

> Status (2026-10-17): `Session`, `run`, `connect`, `run_step` and the dry run are in
> `qicklab/core/session.py`; the CSTQ03 session runner is `runners/CSTQ03_session.py`
> ([below](#the-cstq03-session-runner)); the legacy flag runner `runners/CSTQ03_BFC.py` was
> deleted in phase 5b. Every recipe keyword is in its function's docstring (`help(R.t1)`); the generated
> tables (`docs/parameters.md`, each [experiments/](experiments/README.md) page) come in phase 6.

## The session file

```python
"""CSTQ03, 2026-10-01 cooldown."""
from devices.CSTQ03 import DEVICE
from qicklab.core.session import Session, run
from qicklab.runs import groups as G
from qicklab.runs import recipes as R

SESSION = Session(
    DEVICE,
    qubit_readout=5,          # whose resonator is read out; also selects the data folder
    qubit_pulse=5,            # whose drive parameters are used
    bias_v=0.0,               # charge-line yoko voltage [V], ramped to at connect
    yoko_fixed=False,         # True: charge "sweeps" hold the bias (repeat over time instead)
    interactive_plots=False,  # False: plots are saved, never block (see below)
    # shared recipe groups: every step that needs one reads the same object
    spec=G.spec(),
    coherence=G.coherence(relax_delay=3000),
    echo=G.echo(),
    single_shot=G.single_shot(),
)

PLAN = [
    R.transmission_fit(reps=20),
    R.two_tone_spec(),
    R.amplitude_rabi(max_gain=10_000),
    R.t1(),
    R.single_shot(),
    R.t1(relax_delay=5000),   # same step again, one knob changed
]

if __name__ == "__main__":
    run(SESSION, PLAN)
```

Nothing touches hardware until `run()` is called. Importing the file is safe.

### The CSTQ03 session runner

`runners/CSTQ03_session.py` is the session file for CSTQ03. It replaced the legacy flag runner
`runners/CSTQ03_BFC.py` (deleted in phase 5b; frozen in
`tests/regression/fixtures/cstq03_legacy_runner.py.txt`). It has three blocks:

1. `SESSION`: qubits, bias, `yoko_fixed`, and the shared groups. Only the legacy runner's
   repetition counts differ from the library groups (`G.coherence(repetitions=1000)`,
   `G.echo(repetitions=3000)`).
2. `STEP`: one Step per canonical name, with the legacy runner's values where they differ from
   the library defaults (for example `R.t1_single_shot(repetitions=3000)`,
   `R.modified_ramsey(df=1, f_ge=3754.5, ...)`).
3. `PLAN`: the steps to run, e.g. `PLAN = [STEP["transmission_fit"], STEP["t1"]]`. Any step
   can be written out instead with its own overrides (`R.t1(relax_delay=5000)`).

```
python -m runners.CSTQ03_session              # on the fridge
python -m runners.CSTQ03_session --dry-run    # fake board, nothing kept
```

Run it from the repo root (or PyCharm with the repo root as sources root). The legacy
repetition counts make some `STEP` entries long even in a dry run: `t1`, `t2_echo` and
`modified_ramsey` stop at the dry-run guard (`INCOMPLETE`), and the default
`STEP["undriven_single_shot"]` (10^6 shots, `repeat=10000`) analyses 41 records of a million shots
before it stops (tens of minutes). To check a plan offline, dry-run it with shorter steps,
e.g. `R.undriven_single_shot(shots=10_000)`. The effective
parameters printed for each step are equivalent to those the legacy runner passed for the same
flag, not a copy of its dicts: every key the run reads has the runner's value, the run's own
defaults are written out, and the runner's dead keys (keys the run never reads, such as
`lower_freq`/`upper_freq` of `ChargeDispersion_params` and `Gauss` of
`ModifiedRamsey_Control_params`) are dropped. `tests/test_session_runner.py` checks this, step
by step, against the frozen copy of the legacy runner plus the value changes it received after
the freeze (`POST_FREEZE` there); the dropped keys are a pinned list there, so a runner
key with no recipe keyword fails the test rather than silently not reaching the run. A
legacy flag maps to its step like this:

| legacy flag | step | legacy flag | step |
|---|---|---|---|
| `ConstantTone` | `constant_tone` | `RunT1` | `t1` |
| `Constant2Tone` | `constant_two_tone` | `RunT2` | `t2_ramsey` |
| `RunTransmissionSweep` | `transmission_fit` | `RunT2E` | `t2_echo` |
| `RunTransmissionSweeps` | `transmission_sweep` | `RunT1T2E` | `t1_t2e` |
| `Run2ToneSpec` | `two_tone_spec` | `RunT1T2RT2E` | `t1_t2r_t2e` |
| `RunSpecGainLengthSweep` | `spec_gain_length_sweep` | `RunInterleavedCoherence` | `interleaved_coherence` |
| `RunTrans_QubitSpec` | `trans_qubit_spec` | `RunAutoCoherence` | `auto_coherence` |
| `RunChiShift` | `chi_shift` | `SingleShot` | `single_shot` |
| `RunAmplitudeRabi` | `amplitude_rabi` | `RunUndrivenSingleShot` | `undriven_single_shot` |
| `RunChargeSweep` | `charge_sweep` | `RunT1SS` | `t1_single_shot` |
| `RunChargeTransmissionSweep` | `charge_transmission_sweep` | `SingleShot_ReadoutOptimize` | `readout_optimize` |
| `Run2ToneChargeDispersionQuasiCW` | `two_tone_charge_dispersion_quasicw` | `SingleShot_QubitOptimize` | `qubit_optimize` |
| `RunChargeDispersionQuasiCW` | `charge_dispersion_quasicw` | `RunActiveResetVerify` | `active_reset_verify` |
| `RunChargeDispersionRamsey` | `charge_dispersion_ramsey` | `RunModifiedRamsey` | `modified_ramsey` |
| `RunZeroSpanParity` | `zero_span_parity` | `RunModifiedRamsey_Control` | `modified_ramsey_control` |

The legacy runner ran its flags in a fixed order (every regime-A flag, then the switch, then the
regime-B flags). `STEP` is written in that order: to get the legacy behaviour from several
flags, list their steps in PLAN in the order they appear in `STEP`. The `ZSP_*`, `Validate_*` and `Build_EvidenceReport` settings are
keywords of `R.zero_span_parity` (`run_mode=`, `validate_static_contrast=`, `parity_spec={...}`,
...). For an offline dry run of `zero_span_parity`, `modified_ramsey*` and the charge-dispersion
steps, see [Dry run](#dry-run).

### Session fields

| field | units | meaning |
|---|---|---|
| `device` | | the `Device` object from `devices/<NAME>.py` |
| `qubit_readout` | index | qubit whose readout (freq, gain, window) is used; data goes under its folder `Q<qubit_readout>` |
| `qubit_pulse` | index | qubit whose drive (freq, pi gain, pi/2 gain, sigma, flat-top) is used |
| `bias_v` | V | charge-line yoko setpoint, ramped to once at connect |
| `yoko_fixed` | bool | charge sweeps hold the bias instead of stepping it: a cheap way to repeat two-tone spec over time |
| `interactive_plots` | bool | `False` (default): Agg backend, `plt.show()` is a no-op and every figure is only saved as png (planned; see [Plots](#plots)) |
| `transmission`, `spec`, `charge`, `tones`, `coherence`, `echo`, `single_shot` | | shared recipe groups (next section); left out = the library group `G.<group>()`, a given dict is copied |

`qubit_readout` and `qubit_pulse` are usually the same. They differ only for cross-qubit
experiments; the legacy code is not consistent about which one a step uses for `Qubit_number`
(Rabi uses the pulse qubit, T1 and single shot the readout qubit). File names depend on it, so it
stays; every saved file records both qubits explicitly in its provenance
([architecture](architecture.md#provenance)).

### Shared groups

Some parameter sets are read by several steps and by the config builders themselves, so they
live on the session, not on one step. This reproduces the legacy runner, where editing
`T1T2_params` changed `t1`, `t1_t2e` and the interleaved loop together.

| group | legacy dict | read by |
|---|---|---|
| `transmission` | `Transmission_params` (`span`, `num_points`, `reps`, `rounds`) | regime-A base config (`TransSpan`, `TransNumPoints`), `transmission_fit`, `charge_transmission_sweep` |
| `spec` | `Spec_relevant_params` | regime-A base config (`qubit_gain`, `qubit_length`, `SpecSpan`, `SpecNumPoints`), `two_tone_spec`, `spec_gain_length_sweep`, `trans_qubit_spec`, `charge_sweep`, the charge-dispersion steps |
| `charge` | `charge_params` (`voltage_start/end/step`) | regime-A base config, `charge_sweep`, `charge_transmission_sweep` |
| `tones` | `tl` (`tone_length`) | regime-A base config, `constant_two_tone` |
| `coherence` | `T1T2_params` | `t1`, `t2_ramsey`, `t1_t2e`, `t1_t2r_t2e`, `trans_qubit_spec` (its `repetitions`), `charge_dispersion_ramsey`, `interleaved_coherence` |
| `echo` | `T2E_params` | `t2_echo`, `t1_t2e`, `t1_t2r_t2e`, `interleaved_coherence` |
| `single_shot` | `SS_params` | the regime-B config builder (shots, relax delay, pi/2 flag), `single_shot`, `t1_single_shot`, `qubit_optimize`, `interleaved_coherence` |

### Precedence

```
library recipe default  <  session group  <  per-step override (kwargs on R.<step>(...))
```

Example: the library default T1 relax delay is replaced by `coherence=G.coherence(relax_delay=3000)`
for every coherence step; `R.t1(relax_delay=5000)` uses 5000 for that one step only.
Device-dependent defaults (`None` in the recipe) resolve from the selected qubit at run time;
for example Modified Ramsey's upper-branch frequency comes from
`device.qubits[q].parity.f_upper_mhz`, and `symmetric_ramsey=True` with no `f_upper_mhz`
raises instead of falling back to the centre frequency. Groups resolve the same way: the
`spec` group's `gain` left at `None` is `Qubit.spec_gain`, else 800. Every Step does this
itself when its arguments are built (`Step.fill_groups`, which is `G.resolve`), so a library
`G.spec()` never hands `None` to a run.

### Values the device does not carry

The design lists the voltage window and the spectroscopy gain as device-dependent values.
Two kinds still have concrete library defaults (equal to the CSTQ03 runner's values), listed
in `qicklab.runs.recipes.LIBRARY_DEVICE_VALUES`:

| Step | Keywords | Library value | Why it is not `None` |
|---|---|---|---|
| `modified_ramsey_control` | `voltage_min`, `voltage_max`; `gain` | 0 to 0.010 V; 700 | no voltage-window field on the device; search gain |
| `two_tone_charge_dispersion_quasicw` | `voltage_min`, `voltage_max`; `gain` | 0 to 0.010 V; 500 | same |
| `auto_coherence` | `ss_voltage_min`, `ss_voltage_max`; `spec_gain` | 0 to 0.01 V; 700 | same |
| `zero_span_parity` | `parity_spec={"gain": ...}` | 500 | search gain |

- **Voltage window.** The device model (`Qubit`, `ParityParams`) has no voltage-window field,
  so there is nothing to resolve these from.
- **Search gains.** The runner drives these search spectroscopies at gains (700, 500) that
  differ from the `spec` group's 800. A single `Qubit.spec_gain` cannot hold all of them, so
  only the `spec` group's `gain` resolves from it.

Pass these per step (`R.modified_ramsey_control(voltage_max=0.02)`). This is an open design
decision awaiting sign-off: either the device model gets a field for each of these, or the
design accepts them as library values.

Recipes are keyword-only functions: a misspelled keyword raises `TypeError` instead of being
ignored. PyCharm's quick-doc (Ctrl+Q) on `R.t1` shows every parameter with its default and
units.

## The PLAN

`PLAN` is an ordered list. Steps run in the order written, repeats are allowed, and the same
step can appear with different overrides. Each step belongs to a regime:

- Regime A: the measurement config (readout window = `Device.readout_window`, `qubit_gain` =
  spec drive gain).
- Regime B: the single-shot config (readout window = `Device.ss_window`, `qubit_gain` = pi
  gain).

`run()` switches the config whenever the regime changes between consecutive steps. A switch
A -> B builds the single-shot config afresh from the board defaults, so the regime-B steps do
not see the two in-session carry-overs: the cavity frequency written by
`transmission_fit`/`transmission_sweep` (`pulse_freq`; written only when the trace passes the
[carry-over gate](experiments/transmission_fit.md#carry-over-gate), otherwise the previous value
stays) and the readout phase written by the active-reset calibration (`res_phase`). A switch
B -> A puts back the regime-A config held at the A -> B switch, carry-overs included, as
`interleaved_coherence` does. If a regime-B step needs a new cavity frequency, put it in the
device file (under a session a transmission step whose gate passed prints a paste-ready
`Qubit(...)` line, see [What gets logged](#what-gets-logged)). See
[concepts/config_regimes.md](concepts/config_regimes.md#how-run-switches) and, for the window
each regime uses, [concepts/readout_window.md](concepts/readout_window.md).

### Steps

Data path = the `path` string the experiment saves under (unchanged from the legacy code). Each
step has a page under [experiments/](experiments/README.md) with its pulse sequence and
parameters.

| step | experiment class(es) | path | regime | groups |
|---|---|---|---|---|
| `constant_tone` | SingleTone | `TransmissionFF` | A | |
| `constant_two_tone` | ConstantTwoTone | `ConstantTwoTone` | A | tones |

The two CW steps hold their tones until you press Enter (or for `hold_s` seconds when the step is
given `hold_s`; with no interactive stdin and no `hold_s` the tones stop at once) and always call
`soc.reset_gens()` before returning. After a hard kill, run `soc.reset_gens()` yourself: a periodic
tone keeps playing otherwise ([cw_tones](experiments/cw_tones.md#stray-tone-hazard)).
| `transmission_fit` | CavitySpecFF | `TransmissionFF` | A | transmission |
| `transmission_sweep` | CavitySpecFF | `TransmissionFF` | A | transmission |
| `two_tone_spec` | QubitSpecSliceFF | `QubitSpecFF` | A | spec |
| `spec_gain_length_sweep` | QubitSpecSliceFF | `QubitSpecFF` | A | spec |
| `trans_qubit_spec` | QubitSpecSliceFF | `QubitSpecFF` | A | spec, coherence |
| `chi_shift` | ChiShift | `ChiShift` | A | |
| `amplitude_rabi` | AmplitudeRabiFF, AmplitudeRabiFF_N (flat-top) | `AmplitudeRabi` | A | |
| `t1` | T1FF | `T1` | A | coherence |
| `t2_ramsey` | T2R | `T2R` | A | coherence |
| `t2_echo` | T2EMUX | `T2E` | A | echo |
| `t1_t2e`, `t1_t2r_t2e` | T1FF, T2EMUX (, T2R) | `T1`, `T2E` (, `T2R`) | A | coherence, echo |
| `charge_sweep` | QubitSpecSliceFF | `QubitSpecFF` | A | spec, charge |
| `charge_transmission_sweep` | CavitySpecFF | `ChargeTransmissionFF` | A | transmission, charge |
| `two_tone_charge_dispersion_quasicw` | QubitSpecSliceFF, ChargeDispersionQuasiCW | `TwoToneChargeDispersion` | A | spec |
| `charge_dispersion_quasicw` | ChargeDispersionQuasiCW | `ChargeDispersion` | A | spec |
| `charge_dispersion_ramsey` | ChargeDispersion | `ChargeDispersion` | A | coherence |
| `modified_ramsey` | ModifiedRamsey, SingleShotProgramFFMUX (calibration) | `ModifiedRamsey`, `ModifiedRamsey_Controls`, `SingleShot_MRCalib` | A | |
| `modified_ramsey_control` | ModifiedRamsey, QubitSpecSliceFF (sweet-spot search), SingleShotProgramFFMUX (calibration) | `ModifiedRamsey_Control`, `auto-Spec`, `SingleShot_MRCalib` | A | |
| `active_reset_verify` | ActiveResetVerify, SingleShotProgramFFMUX | `ActiveResetVerify`, `SingleShot_MRCalib` | A | |
| `interleaved_coherence` | UndrivenSingleShot, T1FF, T2R, T2EMUX | each step's own | A (swaps to B per step) | coherence, echo, single_shot |
| `single_shot` | SingleShotProgramFFMUX | `SingleShot` | B | single_shot |
| `undriven_single_shot` | UndrivenSingleShot | `UndrivenSingleShot` | B | single_shot |
| `t1_single_shot` | T1_SS, SingleShotProgramFFMUX | `T1SS`, `SingleShot` | B | single_shot |
| `readout_optimize` | ReadOpt_wSingleShotFF | `SingleShot_OptReadout` | B | |
| `qubit_optimize` | QubitPulseOpt_wSingleShotFF | `SingleShot_OptQubit` | B | single_shot |
| `auto_coherence` | (orchestrator) | `AutoCoherence/run_<timestamp>/auto-*` | B | |
| `zero_span_parity` | ZeroSpanParity, QubitSpecSliceFF, SingleShotProgramFFMUX | `ZeroSpanParity`, `ZeroSpanParity/ZeroSpanParity_Spec` | B | |

The legacy runner always ran regime A steps first, then switched once to regime B. A PLAN
written in that order gives exactly the legacy behaviour. The regression harness checks this:
`tests/regression/driver_plan.py` replays every golden label as `Session` + PLAN and reproduces
the golden leaf for leaf ([tests/regression/README.md](../tests/regression/README.md#driver_plan-the-session-api-replay)).

## Running

```python
run(SESSION, PLAN)                 # connect, run every step, close the yoko in `finally`
run(SESSION, PLAN, dry_run=True)   # no hardware: fake board, compiles every program, prints the plan
```

`run()` connects (Pyro4 to the RFSoC, opens the charge-line yoko, sets voltage mode, output on,
ramps to `bias_v`; this is the legacy `build_context` call fed from the device and the groups),
checks the device against the board (`Device.validate(soccfg)`: errors raise, soft problems
warn), then for each step: switches the regime if it changed, resolves the step's parameters,
logs them, and calls the step. It returns the steps' return values. The yoko is closed in
`finally`, so an exception or Ctrl-C does not leave the session holding it. Closing does not
ramp the bias down; the voltage stays wherever the last step left it.

The regime-B config is built from the session's `single_shot` group (its window `None` = the
readout qubit's `Device.window(q, single_shot=True)`, its `qubit_pulse` `None` = the session's
pulse qubit). A step's own override of that group reaches only that step. The one override
that touches a config key is `R.single_shot(pi2_ss=...)`. While that step runs, the config's
`pi2_SS` holds the step's value, so the saved cfg records the pulse that played; afterwards it
is put back (the log says so). The legacy runner fed one `SS_params` to both, so the two never
disagreed there.

A device whose `Setup` sets `board_overrides` or `ff_qubits` is refused at connect
(`NotImplementedError`): `build_context` does not apply them yet.

### Dry run

`dry_run=True` uses the fakes in `qicklab.core.fakes` (the same ones the regression harness
uses): every tProc program compiles against a realistic `QickConfig`, so cfg typos, missing
keys, timing violations (for example a Modified Ramsey tau shorter than its pi/2 envelopes) and
buffer limits fail before you are on the fridge. It says nothing about physics.

- Data goes to a temp data root that is deleted afterwards; your `zsp_cache.json` files are
  copied in (read, never written). The provenance session record is restored afterwards.
- `plt.show`, `plt.pause`, `time.sleep` and `input()` do not block; the CW-tone steps stop at once.
- Every experiment a step builds runs, so the stages after a calibration loop compile too
  (`auto_coherence` with library defaults: about 90 experiments, under a minute). The report lists, per
  step, every experiment (class, path) built and how often.
- Two guards stop a step: more than `DRY_RUN_MAX_REPEATS` (40) builds in a row of experiments the
  step already built (a long repetition loop or grid), or `DRY_RUN_MAX_EXPERIMENTS` (200) builds
  in all. The report then marks the step `INCOMPLETE`: the programs after the stop were not
  compiled. Among the canonical steps with library defaults only `spec_gain_length_sweep` (its
  10 x 49 grid; the saturation summary after the grid is not reached) gets there; shorten
  `sweep_lengths` / `sweep_gains` (or `repetitions` elsewhere) to check the rest. An
  `INCOMPLETE` step does not fail the dry run.
- A step that raises is printed with its traceback and the dry run goes on; at the end a report
  lists every step (experiments built, programs loaded, status) and `RuntimeError` names the
  failed steps. Without failures `run` returns the report.
- `zero_span_parity` with the default `recalibrate_parity_freqs=True` always fails a dry run:
  the fake board's synthetic spectroscopy never resolves a parity doublet, so the step raises
  (`pick_parity_drive_freq: no resolved parity doublet`) before its record programs compile.
  To check the rest of the step offline, give the doublet and skip the search:
  `R.zero_span_parity(recalibrate_parity_freqs=False, parity_freqs_cached={"lower_peak_MHz":
  ..., "higher_peak_MHz": ...})`. With `recalibrate_parity_freqs=False`, a `Qubit.parity` or a
  `zsp_cache.json` entry can supply the doublet instead.

### From a console (REPL)

```python
from qicklab.core.session import connect, run_step
from qicklab.runs import recipes as R
from runners.CSTQ03_session import SESSION

ctx = connect(SESSION)                  # one Pyro connection and one yoko ramp
run_step(ctx, R.t1(relax_delay=5000))
run_step(ctx, R.single_shot())
ctx.yoko.close()                        # run() does this for you; connect() does not
```

`ctx` keeps `soc`, `soccfg`, `yoko`, the current `config` and the per-qubit scalars, so repeated
steps do not reconnect.

### Plots

Today, importing the analysis package switches matplotlib to the Agg backend, so
`plt.show(block=True)` is silently a no-op in every session: nothing opens on screen, nothing
blocks, figures are only written to the step's png. A planned fix commit moves that choice to
`Session(interactive_plots=False)`, which keeps the same non-blocking default. With `True`, a
step whose display is on will open a window and wait for you to close it; do not combine that
with long unattended loops (`undriven_single_shot` with many repeats, `interleaved_coherence`).
Whatever the display does (a fit raises, or you Ctrl-C a blocking window), the step's h5 and
json are still written. A display error inside a repetition loop is printed and the loop goes
on; a single run re-raises it after saving. A Ctrl-C is never swallowed: after the save it
stops the step, and the loop with it
([architecture](architecture.md#display-never-loses-the-record)).

## What gets logged

- At connect: the readout window, e.g.
  `[readout window] integration 15 us, adc_trig_offset 0.3 us, resonator tone 15.3 us`.
- Before each step: the step name, its regime, any regime switch, and the effective parameters
  after defaults, group and override. An A -> B switch also prints the session `single_shot`
  group the regime-B config was built from (shots, relax delay, window, `pi2_SS`), which every
  later regime-B step reads through the config, also the steps without a `single_shot` slot
  (`readout_optimize`, `auto_coherence`, ...). Copy this into your notebook; with the switch
  lines it is the complete description of what ran.
- Calibration write-back: `qicklab.core.io.record_calibration` appends to
  `<data_root>/Q<q>/calibrations.jsonl` and prints a paste-ready `Qubit(...)` line. The session
  calls it after a `transmission_fit` / `transmission_sweep` whose carry-over gate wrote a new
  `pulse_freq` (`readout_freq` of the readout qubit; not when `cavity_LO` != 0, where
  `pulse_freq` is an IF) and after a zero-span parity recalibration. For the other calibrating
  steps (`amplitude_rabi`, `readout_optimize`, `qubit_optimize`, `auto_coherence`) call it
  yourself for now: their run functions return nothing the session could record. Nothing edits
  the device file for you. See [adding_a_device.md](adding_a_device.md#calibration-write-back).
- Every experiment writes its full `cfg` to a `.json` next to its data and into the h5
  `config` attribute. The saved cfg is the ground truth, not the log.
- Every saved file also gets a provenance record (`<stem>_provenance.json` and the h5
  attribute `provenance`): qick and board versions, board-config hash, git commit and dirty
  flag, host, device, data root, readout and pulse qubit, the last landed yoko level and the
  start and end time ([architecture](architecture.md#provenance)).

## Where data lands

```
<data_root>/Q<q>//<path>/<path>_<YYYY_MM_DD>/<path>_<YYYY_MM_DD_HH_MM_SS>_data.h5
                                             <path>_<YYYY_MM_DD_HH_MM_SS>_data.png
                                             <path>_<YYYY_MM_DD_HH_MM_SS>_data.json
                                             <path>_<YYYY_MM_DD_HH_MM_SS>_data_provenance.json
```

`<q>` is `qubit_readout`. `<data_root>` comes from the device file. If two experiments with
the same `path` start in the same second, the second gets `_1` (then `_2`, ...) on all three
names (`..._data_1.h5`, `..._data_1.png`, `..._data_1.json`) instead of overwriting the
first. A real CSTQ03 file:

```
V:/t1Team/Data/2026-10-01_BFC_cooldown/CSTQ03/RFSOC/Q1//TransmissionFF\TransmissionFF_2026_10_13\TransmissionFF_2026_10_13_14_03_22_data.h5
```

The mix of `/`, `//` and `\` is intentional legacy behaviour (string concatenation plus
`os.path.join` on Windows); Windows resolves it fine. Details in
[architecture.md](architecture.md#file-naming-must-stay-byte-identical).

Exceptions to the pattern:

| step | extra or different output |
|---|---|
| `t1` | h5 renamed in `save_data` to `..._data_Q<n>.h5`; the json keeps the plain stem |
| `t2_echo` | h5 renamed to `..._data_n<num_pi_pulses>.h5`; two pngs, `..._dataI_Data.png` and `..._dataQ_Data.png` |
| `charge_transmission_sweep` | one file set per bias slice under `ChargeTransmissionFF/`; the map lands beside the last slice as `_ChargeTransmissionHeatmap.png/.npz` |
| `active_reset_verify` | per-condition files, plus an overlay png and npz in `<folder>/ActiveResetVerify/` |
| `zero_span_parity` | data under `<folder>/ZeroSpanParity/`; analysis plots and sidecars in the same run directory; `EVIDENCE.md` when the evidence report is built |
| `undriven_single_shot` | one file set per repeat |
| `interleaved_coherence` | every sub-step writes its own files; cfg carries `interleave_run_id`, `interleave_cycle`, `interleave_cycles_total`, `interleave_step` |
| `auto_coherence` | see tree below |

AutoCoherence output tree:

```
<data_root>/Q<q>//AutoCoherence/
    run_<timestamp>/
        auto-Spec/  auto-AmplitudeRabi/  auto-ReadoutOpt/  auto-SingleShot/
        auto-PiOpt/  auto-Pi2Opt/  auto-T1/  auto-T2/  auto-T2E/
        auto_coherence_summary_<timestamp>.txt
        auto_coherence_summary_<timestamp>.json
```

Each `auto-*` folder follows the normal `<path>_<date>/<path>_<timestamp>_data.*` pattern. The
summary json holds the calibrated values (qubit frequency, pi and pi/2 gains, sigma, flat-top,
fidelity, single-shot threshold and angle, sweet-spot voltage) and the parameters used.

Two experiments constructed in the same wall-clock second get the same file name; the second
`save_data` then fails on the existing dataset. Normal steps never do this (acquisition takes
longer than a second), but keep it in mind when scripting loops of very short runs.

## Reading data offline

```python
import glob, json
import h5py

folder = "V:/t1Team/Data/2026-10-01_BFC_cooldown/CSTQ03/RFSOC/Q5//T1"
fname = sorted(glob.glob(folder + "/T1_*/T1_*_data*.h5"))[-1]   # newest

with h5py.File(fname, "r") as f:
    cfg = json.loads(f.attrs["config"])        # the exact cfg the experiment ran with
    prov = json.loads(f.attrs.get("provenance", "{}"))  # code, board, qubits, bias (2026-10-17 on)
    data = {k: f[k][()] for k in f.keys()}     # every dataset (float64 for most steps)

print(cfg["relax_delay"], cfg["f_ge"], sorted(data))
```

- Numeric and bool data are stored as float64 by the base writer; complex data is
  complex128 and string data an h5py UTF-8 string dataset, which `f[k][()]` returns as
  bytes (use `f[k].asstr()[()]` for `str`). Every current step saves numeric data only.
  Zero-span parity writes its own file (int arrays, string attributes). Undriven
  single-shot is the other exception: it stores raw traces as float32, 0/1 labels as uint8
  and duplicate keys as h5py SoftLinks, which the loop above follows transparently; its dropped index/time axes are
  rebuilt from saved scalars ([undriven_single_shot](experiments/undriven_single_shot.md#outputs)).
- The `.json` next to the h5 holds the same cfg; it is the quick way to grep settings across a
  folder. Skip `*_provenance.json` when globbing `*.json`: those hold the provenance record.
- `t1` and `t2_echo` save their exponential fit in the h5 (`t1_fit_*`, `t2e_fit_*`, see
  [t1](experiments/t1.md#outputs)); `*_fit_ok` is a quality flag, not an unbiased selector for a
  T(t) series ([t1](experiments/t1.md#analysis)). `chi_shift` saves its joint fit (`chi_fit`,
  `chi_err`, `chi_fit_ok`, populations, kappa, fr; see [chi_shift](experiments/chi_shift.md#outputs)).
  Fit results of `t2_ramsey` are not saved; they appear only in the png and the console. Refit
  from the saved data.
- Interleaved records group by cycle via the cfg:
  `cfg["interleave_run_id"], cfg["interleave_cycle"], cfg["interleave_step"]`. `run_id` is the
  wall-clock start of the loop, so separate invocations on the same day stay distinct.
- The analysis functions in `qicklab.analysis` import without qick or a board, so analysis
  notebooks can run anywhere the data drive is mounted.

## Known issues

Error messages and their fixes are collected in [troubleshooting.md](troubleshooting.md).

- Regime switches drop `pulse_freq` and `res_phase` (above). A PLAN that runs
  `active_reset_verify` and then `single_shot` sees `res_phase` reset to 0.
- Some steps move the bias and do not restore it (AutoCoherence sweet-spot walk, some charge
  sweeps). Later steps then run at a different voltage while the cfg's `current_voltage` still
  shows the session value; the provenance `bias.charge_yoko` holds the level the last ramp
  actually landed on.
- Two steps mutate their caller's parameter dicts. `two_tone_charge_dispersion_quasicw` writes
  the chosen `probe_freq` into the dict given as `charge_dispersion=`; the CSTQ03 runner passes
  `STEP["charge_dispersion_quasicw"]`'s own dict there, as the legacy runner shared
  `ChargeDispersion_params`, so a later `charge_dispersion_quasicw` probes that frequency.
  Modified Ramsey control adds hysteresis/window keys. Order of such steps changes their
  parameters.
- `charge_dispersion_ramsey` raises `KeyError: 'df'` with the CSTQ03 parameter set.
- `qubit_optimize` raises `KeyError: 'pi2_SS'` if run in regime A.
