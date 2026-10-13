# t1_single_shot: single-shot T1 (T1_SS)

## What it measures

T1 measured from thresholded single shots instead of averaged IQ. At each wait time
the step prepares |e> with one pi pulse, waits, reads out `reps` single shots,
rotates them by the [single_shot](single_shot.md) angle, and counts the fraction
above the single-shot threshold (the "excited population"). The result is the
excited fraction vs wait time. **No T1 fit is performed.** Code: see
`qicklab.experiments.t1_single_shot` (program class `T1SingleShotProgram`;
experiment class `T1_SS`).

## Pulse sequence

One `AveragerProgram` per wait point (a Python loop over `expts` points), each with
`reps` shots and `rounds = 1`.

```
qubit_ch  ── 0.05 µs ─[ gauss 4σ @ f_ge, gain qubit_gain, phase 0 ]─┐
                                                                     ├── variable_wait ──┐
res_ch    ───────────────────────────────────────────────────────────────────────────────[ readout tone: length ]── relax_delay
ADC       ─────────────────────────────────────────────────────────────────────────────────────[ window ]
                                                                                     ^ adc_trig_offset
```

- Channels: `qubit_ch`, `res_ch`, `ro_chs` (only `ro_chs[0]` is used).
- No trigger pin. Plain gaussian only: `flattop_length` is ignored.
- `variable_wait = start + k·step` (µs).
- No cross-clock tone extension. The tone length is `us2cycles(length)` (tProc clock)
  and the readout window is declared with `us2cycles(readout_length)`, also the tProc
  clock (see Known issues).

## How to run

Runs in **regime B**. The program plays `cfg["qubit_gain"]`, which is the pi gain
only in regime B.

```python
PLAN = [R.t1_single_shot()]                                  # calibrates SS first
PLAN = [R.t1_single_shot(calibrate_ss=False, angle=0.12, threshold=1.3)]
```

With `calibrate_SS = True`, each repetition first runs a [single_shot](single_shot.md)
(saved under `SingleShot/`, honouring the single_shot group's `number_of_pulses`) and
uses its read-0 `angle` and `threshold`. After every repetition the run sleeps 10 s
and calls `soc.reset_gens()`.

## Parameters

Legacy `T1SS_params` keys. Defaults are the CSTQ03 runner values.

| Key | Default | Units | Meaning |
|---|---|---|---|
| `T1_step` → `step` | 80 | µs | Wait-time step (`start` is fixed at 0). |
| `T1_expts` → `expts` | 100 | count | Number of wait points; one program each. |
| `reps` | 2000 | count | Single shots per wait point. |
| `relax_delay` | 8000 | µs | Wait after each readout. |
| `calibrate_SS` | True | bool | Run single_shot before each repetition to get angle and threshold. |
| `angle` | 0 | rad | Rotation used when `calibrate_SS = False`. Same convention as single_shot. |
| `threshold` | 0 | normalised I | Threshold used when `calibrate_SS = False`. |
| `repetitions` | 3000 | count | Back-to-back T1_SS runs. |

`pi_gain` is written into the cfg by the run but **not read** by the program.

## Outputs

Path `T1SS/`.

- **h5:**
  - `Exp_values`: excited fraction per wait point, shape `(expts,)`.
  - `RotatedIQ`: rotated I/Q per point.
  - `threshold` and `angle` as used.
  - `wait_times`: µs.
- **png:** excited fraction vs wait time (µs).
- **json:** the cfg, including `variable_wait` (last point) and `Excited_PulseT1`,
  which nothing reads.
- **No fit.** T1 is not extracted or saved. Fit `Exp_values` vs `wait_times` offline.

## Analysis

Each shot is rotated: `I' = I cosθ − Q sinθ`. A shot counts as excited if `I' >
threshold`. The single_shot rotation puts |e> at larger I', so the fraction is
P(e) without readout-error correction. The excited fraction plateaus at the readout
error floor, not at 0, and starts below 1 by the pi infidelity plus the readout error.

## Findings & notes

None recorded for this step in the legacy code.

## Known issues

- **Window mismatch with the calibration.** The readout window is declared with a
  tProc-clock cycle count, but shots are normalised with the readout-clock count
  (`us2cycles(readout_length, ro_ch=0)`).
  - On the current board (f_time 430.08 MHz, f_output 307.2 MHz) the integrated
    window is therefore about 1.4x longer than `readout_length`.
  - The normalisation does not match the [single_shot](single_shot.md) program that
    produced the threshold. The threshold is applied on a different scale.
  - The audit rates this plausible: it depends on the clocks of the board.
- The program plays `qubit_gain`, not `pi_gain`. Before the regime-B config rebuild,
  `qubit_gain` is the spectroscopy gain.
- `flattop_length` is ignored. Devices with a flat-top pi pulse get a mis-rotation.
- `threshold = None` raises in the counting step.
- One program per wait point, plus a 10 s sleep per repetition: long runs are slow.
