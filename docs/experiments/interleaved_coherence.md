# interleaved_coherence

Run function in `qicklab.runs.interleave`; experiments `UndrivenSingleShot`, `T1FF`, `T2R`,
`T2EMUX`. Regime **A** on entry and exit; the step builds the regime-B config for its
undriven sub-step and swaps configs per sub-step.

## What it measures

A long unattended loop that alternates parity/blob records with coherence numbers measured
under the same conditions. One cycle runs, in this fixed order:

```
UndrivenSingleShot  ->  T1  ->  T2R  ->  T2E
```

Each sub-step can be switched off; the cycle repeats `cycles` times. Every sub-step is
exactly the standalone measurement ([undriven_single_shot](undriven_single_shot.md),
[t1](t1.md), [t2_ramsey](t2_ramsey.md), [t2_echo](t2_echo.md)) with its own
repetition counter forced to 1 and plotting off.

## Pulse sequence

```
cycle k (k = 0 .. cycles-1):
  [US]  regime-B cfg  : no qubit pulse; readout only, Shots shots at relax_delay cadence
  [T1]  regime-A cfg  : pi - wait - readout                   (+10 s pause, reset_gens)
  [T2R] regime-A cfg  : pi/2 - wait - pi/2 - readout          (+10 s pause, reset_gens)
  [T2E] regime-A cfg  : pi/2 - (w - pi) x n - w - pi/2 - readout (+10 s pause, reset_gens)
```

Readout windows differ by sub-step: the undriven sub-step uses the single-shot window
(`single_shot` group / device `ss_window`), T1/T2R/T2E use the regime-A device window.
The loop swaps the two configs for you. Channels and triggers as on the individual pages.

## How to run

```python
PLAN = [R.interleaved_coherence(cycles=500, t2e=True)]
PLAN = [R.interleaved_coherence(), R.single_shot()]      # regime switches to B after the loop as usual
```

Sub-step parameters come from the shared groups (`coherence`, `echo`, `single_shot`) and
the undriven-single-shot recipe.

## Parameters

| Name (legacy key) | Legacy default | Units | Meaning |
|---|---|---|---|
| `cycles` | 10000 | - | Number of cycles (minimum 1) |
| `UndrivenSingleShot` | True | bool | Run the undriven sub-step |
| `T1` | True | bool | Run the T1 sub-step |
| `T2R` | True | bool | Run the Ramsey sub-step |
| `T2E` | False | bool | Run the echo sub-step |

Forced inside the loop: undriven `Repeat = 1`, `plotDisp = False`; T1/T2R/T2E
`repetitions = 1`, `plotDisp = False`. All other values come unchanged from the
`undriven_single_shot` recipe (legacy `US_params`), `coherence` (`T1T2_params`), `echo`
(`T2E_params`) and `single_shot` (`SS_params`, which defines the undriven readout window).

## Outputs

Every sub-step writes its own timestamped record exactly as the standalone step does
(folders `UndrivenSingleShot`, `T1`, `T2R`, `T2E` under `<outerFolder>`). Nothing is
displayed mid-loop.

Each record is tagged with four config keys, saved in both the `.json` and the h5
`attrs["config"]`:

| Key | Value |
|---|---|
| `interleave_run_id` | wall-clock start of the loop, `%Y_%m_%d_%H_%M_%S`; distinguishes separate invocations on the same day |
| `interleave_cycle` | cycle index, **0-based** |
| `interleave_cycles_total` | `cycles` |
| `interleave_step` | `"UndrivenSingleShot"`, `"T1"`, `"T2R"` or `"T2E"` |

Group the records of one cycle offline:

```python
import glob, json
from collections import defaultdict
import h5py

cycles = defaultdict(dict)                        # (run_id, cycle) -> {step: h5 path}
for fn in glob.glob(f"{outer_folder}/**/*.h5", recursive=True):
    with h5py.File(fn, "r") as f:
        if "config" not in f.attrs:
            continue
        c = json.loads(f.attrs["config"])
    if "interleave_run_id" in c:
        cycles[(c["interleave_run_id"], c["interleave_cycle"])][c["interleave_step"]] = fn
```

## Analysis

None beyond each sub-step's own display/fit. The T1 and T2E fits are saved in their h5
(`t1_fit_*`, `t2e_fit_*`, with `*_fit_ok`; see [t1](t1.md#outputs)), so a per-cycle time series
needs no refit; the T2R fit is not saved (refit from the arrays). `*_fit_ok` is a quality flag,
not an unbiased selection: when the sweep is short for the current T (for example after a TLS
drift raises T1) it preferentially drops the fits that came out high, so filtering a series
on it biases T low ([t1](t1.md#analysis)). Not-ok records keep their fitted values; count and
inspect them rather than discarding them silently.

## Findings & notes

- Cycle = UndrivenSingleShot -> T1 -> T2R -> T2E; `Repeat` / `repetitions` are forced to 1
  per cycle and `plotDisp` off so nothing blocks the loop on a plot window. An explicit
  `plotDisp` always wins over the "show if only one repetition" default in t1 and
  t2_echo; that is what keeps this loop non-blocking.
- The undriven sub-step uses the single-shot window, T1/T2 use the regime-A window; the
  loop swaps configs.
- The regime-B config of the undriven sub-step is rebuilt from `BASE_CONFIG`, so it does
  not see a `pulse_freq` carried over from an earlier transmission step (the T1/T2 sub-steps
  do).

## Known issues

- A display or fit error inside a sub-step (T1, T2R, T2E, undriven single shot) does not
  abort: that record is saved, the traceback printed and the loop goes on
  ([architecture](../architecture.md#display-never-loses-the-record)). Any other exception (acquire, hardware) or a Ctrl-C still
  aborts the whole loop (no per-step retry). The session config is restored on the way out.
- T1, T2R and T2E each sleep 10 s after their record, so a cycle has at least 30 s of idle
  time (10 s per enabled coherence sub-step).
- The legacy undriven defaults are `Shots = 1,000,000` at `relax_delay = 300` us, i.e.
  roughly 5 min of acquisition per cycle for that sub-step alone.
