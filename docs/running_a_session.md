# Running a session

A measurement session is one short Python file, `runners/<device>_session.py`. It names the
device, picks the qubit, sets a few shared knobs and lists the steps to run, in order. All
physics lives in `qicklab`; all chip numbers live in `devices/<device>.py`
([adding_a_device.md](adding_a_device.md)). You should never need to edit either to take data.

> Status (2026-10-13): this is the phase-5 session API from the refactor design. Until it
> lands, `Runners/CSTQ03_BFC.py` on this branch is the working runner. Recipe keyword names
> shown here are illustrative; the authoritative list will be generated into
> `docs/parameters.md` (phase 6, not yet present) and each [experiments/](experiments/README.md) page.

## The session file

```python
"""CSTQ03, 2026-10-01 cooldown."""
from devices.CSTQ03 import DEVICE
from qicklab.core.session import Session, run
from qicklab.runs import recipes as R

SESSION = Session(
    DEVICE,
    qubit_readout=5,          # whose resonator is read out; also selects the data folder
    qubit_pulse=5,            # whose drive parameters are used
    bias_v=0.0,               # charge-line yoko voltage [V], ramped to at connect
    yoko_fixed=False,         # True: charge "sweeps" hold the bias (repeat over time instead)
    interactive_plots=False,  # False: plots are saved, never block (see below)
    # shared recipe groups: every step that needs one reads the same object
    spec=R.spec(),
    coherence=R.coherence(relax_delay=3000),
    echo=R.echo(),
    single_shot=R.single_shot(),
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

### Session fields

| field | units | meaning |
|---|---|---|
| `device` | | the `Device` object from `devices/<NAME>.py` |
| `qubit_readout` | index | qubit whose readout (freq, gain, window) is used; data goes under its folder `Q<qubit_readout>` |
| `qubit_pulse` | index | qubit whose drive (freq, pi gain, pi/2 gain, sigma, flat-top) is used |
| `bias_v` | V | charge-line yoko setpoint, ramped to once at connect |
| `yoko_fixed` | bool | charge sweeps hold the bias instead of stepping it: a cheap way to repeat two-tone spec over time |
| `interactive_plots` | bool | `False` (default): Agg backend, `plt.show()` is a no-op and every figure is only saved as png (planned; see [Plots](#plots)) |
| `transmission`, `spec`, `charge`, `tones`, `coherence`, `echo`, `single_shot` | | shared recipe groups (next section) |

`qubit_readout` and `qubit_pulse` are usually the same. They differ only for cross-qubit
experiments; the legacy code is not consistent about which one a step uses for `Qubit_number`
(Rabi uses the pulse qubit, T1 and single shot the readout qubit).

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
| `single_shot` | `SS_params` | the regime-B config builder (shots, relax delay, pi/2 flag), `single_shot`, `t1_ss`, `qubit_optimize`, `interleaved_coherence` |

### Precedence

```
library recipe default  <  session group  <  per-step override (kwargs on R.<step>(...))
```

Example: the library default T1 relax delay is replaced by `coherence=R.coherence(relax_delay=3000)`
for every coherence step; `R.t1(relax_delay=5000)` uses 5000 for that one step only.
Device-dependent defaults (`None` in the recipe) resolve from the selected qubit at run time;
for example Modified Ramsey's upper-branch frequency comes from
`device.qubits[q].parity.f_upper_mhz`, and `symmetric_ramsey=True` with no `f_upper_mhz`
raises instead of falling back to the centre frequency.

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

`run()` rebuilds the config whenever the regime changes between consecutive steps. A rebuild
starts from the board defaults, so it drops the two in-session carry-overs: the cavity
frequency written by `transmission_fit`/`transmission_sweep` (`pulse_freq`; written only when
the trace passes the [carry-over gate](experiments/transmission_fit.md#carry-over-gate),
otherwise the previous value stays) and the readout
phase written by the active-reset calibration (`res_phase`). If a regime-B step needs a new
cavity frequency, put it in the device file (the calibration line printed by
`transmission_fit` is paste-ready). See [concepts/config_regimes.md](concepts/config_regimes.md)
and, for the window each regime uses, [concepts/readout_window.md](concepts/readout_window.md).

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
| `modified_ramsey_control` | ModifiedRamsey, QubitSpecSliceFF (sweet-spot search) | `ModifiedRamsey_Control`, `auto-Spec` | A | |
| `active_reset_verify` | ActiveResetVerify, SingleShotProgramFFMUX | `ActiveResetVerify`, `SingleShot_MRCalib` | A | |
| `interleaved_coherence` | UndrivenSingleShot, T1FF, T2R, T2EMUX | each step's own | A (swaps to B per step) | coherence, echo, single_shot |
| `single_shot` | SingleShotProgramFFMUX | `SingleShot` | B | single_shot |
| `undriven_single_shot` | UndrivenSingleShot | `UndrivenSingleShot` | B | single_shot |
| `t1_ss` | T1_SS, SingleShotProgramFFMUX | `T1SS`, `SingleShot` | B | single_shot |
| `readout_optimize` | ReadOpt_wSingleShotFF | `SingleShot_OptReadout` | B | |
| `qubit_optimize` | QubitPulseOpt_wSingleShotFF | `SingleShot_OptQubit` | B | single_shot |
| `auto_coherence` | (orchestrator) | `AutoCoherence/run_<timestamp>/auto-*` | B | |
| `zero_span_parity` | ZeroSpanParity, QubitSpecSliceFF, SingleShotProgramFFMUX | `ZeroSpanParity`, `ZeroSpanParity/ZeroSpanParity_Spec` | B | |

The legacy runner always ran regime A steps first, then switched once to regime B. A PLAN
written in that order gives exactly the legacy behaviour; this is how the regression golden is
replayed.

## Running

```python
run(SESSION, PLAN)                 # connect, run every step, close the yoko in `finally`
run(SESSION, PLAN, dry_run=True)   # no hardware: fake board, compiles every program, prints the plan
```

`run()` connects (Pyro4 to the RFSoC, opens the charge-line yoko, sets voltage mode, output on,
ramps to `bias_v`), then for each step: rebuilds the config if the regime changed, resolves the
step's parameters, logs them, and calls the step. The yoko is closed in `finally`, so an
exception or Ctrl-C does not leave the session holding it. Closing does not ramp the bias down;
the voltage stays wherever the last step left it.

`dry_run=True` uses the fakes in `qicklab.core.fakes` (the same ones the regression harness
uses): every tProc program compiles against a realistic `QickConfig`, so cfg typos, missing
keys, timing violations (for example a Modified Ramsey tau shorter than its pi/2 envelopes) and
buffer limits fail before you are on the fridge. It says nothing about physics.

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
  after defaults, group and override. Copy this into your notebook; it is the complete
  description of what ran.
- Calibrating steps (`transmission_fit`, `amplitude_rabi`, `readout_optimize`,
  `qubit_optimize`, `auto_coherence`, zero-span recalibration) append to
  `<data_root>/Q<q>/calibrations.jsonl` and print a paste-ready `Qubit(...)` line. Nothing edits
  the device file for you. See [adding_a_device.md](adding_a_device.md#calibration-write-back).
- Every experiment writes its full `cfg` to a `.json` next to its data and into the h5
  `config` attribute. The saved cfg is the ground truth, not the log.

## Where data lands

```
<data_root>/Q<q>//<path>/<path>_<YYYY_MM_DD>/<path>_<YYYY_MM_DD_HH_MM_SS>_data.h5
                                             <path>_<YYYY_MM_DD_HH_MM_SS>_data.png
                                             <path>_<YYYY_MM_DD_HH_MM_SS>_data.json
```

`<q>` is `qubit_readout`. `<data_root>` comes from the device file. A real CSTQ03 file:

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
    data = {k: f[k][()] for k in f.keys()}     # every dataset (float64 for most steps)

print(cfg["relax_delay"], cfg["f_ge"], sorted(data))
```

- Every dataset is float64 (the base writer forces it). Experiments that save complex or
  string data write their own files (zero-span parity). Undriven single-shot is the other
  exception: it stores raw traces as float32, 0/1 labels as uint8 and duplicate keys as h5py
  SoftLinks, which the loop above follows transparently; its dropped index/time axes are
  rebuilt from saved scalars ([undriven_single_shot](experiments/undriven_single_shot.md#outputs)).
- The `.json` next to the h5 holds the same cfg; it is the quick way to grep settings across a
  folder.
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
  shows the session value.
- Two steps mutate their caller's parameter dicts (`probe_freq` from
  `two_tone_charge_dispersion_quasicw` leaks into `charge_dispersion_quasicw`; Modified Ramsey
  control adds hysteresis/window keys). Order of such steps changes their parameters.
- `charge_dispersion_ramsey` raises `KeyError: 'df'` with the CSTQ03 parameter set.
- `qubit_optimize` raises `KeyError: 'pi2_SS'` if run in regime A.
