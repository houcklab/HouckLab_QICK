# qubit_optimize: single-shot qubit gain × frequency map (QubitPulseOpt_wSingleShotFF)

## What it measures

A 2-D grid over qubit drive gain and qubit drive frequency. At every point the step
takes a g/e single-shot pair and records the histogram "fidelity" (a contrast) and
the double-Gaussian overlap error, exactly as in
[readout_optimize](readout_optimize.md). Use it to fine-tune the pi pulse, or the
pi/2 pulse (see below), against the real single-shot figure of merit rather than an
averaged Rabi. Code: see `qicklab.experiments.readout_optimize`.

## Pulse sequence

Per grid point: two `SingleShotProgram` runs, without and with `number_of_pulses`
qubit pulses. The structure is in [single_shot](single_shot.md#pulse-sequence)
(trigger pin 0 before each pulse, 0.05 µs between pulses, single-shot readout
window).

```
for g in linspace(qubit_gain_Start, qubit_gain_Stop, qubit_gain_Points):      # outer
    for f in linspace(qubit_freq_start, qubit_freq_stop, QubitNumPoints):      # inner
        [ readout ]×shots   then   [ (pulse g @ f) × number_of_pulses ─ readout ]×shots
```

## How to run

Runs in **regime B**. The step reads `pi2_SS`, which only the regime-B config has.

```python
PLAN = [R.qubit_optimize(q_gain_span=500, q_gain_pts=21,
                         q_freq_span=2, q_freq_pts=21, number_of_pulses=1)]  # pi pulse
```

**pi/2 optimisation.** Set the gain to the pi/2 value and optimise with
`number_of_pulses = 2`, so that two pi/2 pulses make a pi. In practice:

1. Enable `pi2_SS` in the single_shot group. The gain centre becomes the device pi/2
   gain.
2. Set `number_of_pulses = 2` on this step.

## Parameters

Legacy `SS_Q_params` keys. Defaults are the CSTQ03 runner values.

| Key | Default | Units | Meaning |
|---|---|---|---|
| `q_gain_span` | 500 | DAC | Gain range = centre ± span, clipped to [0, 32767]. Centre = `qubit_gain` (pi gain, or pi/2 gain when `pi2_SS`). |
| `q_gain_pts` → `qubit_gain_Points` | 21 | count | Gain points. Must be ≥ 2. |
| `q_freq_span` | 2 | MHz | Frequency range = centre ± span. |
| `q_freq_pts` → `QubitNumPoints` | 21 | count | Frequency points. Must be ≥ 2. |
| `number_of_pulses` | 1 | count | Pulses in the "e" program. 2 for pi/2 optimisation. |

The frequency centre is the device frequency of the first `Qubit_Pulse` qubit of the
single_shot group. It is not the session's current `f_ge`.

## Outputs

Path `SingleShot_OptQubit/`.

- **h5:** `fid_mat` (gain × freq), `overlap_mat`, `qubit_fpts` (MHz), `gain_pts`
  (DAC).
- **png:** written inside `acquire()`. `display()` is a no-op.
- **json:** the cfg. It holds the last grid point's `qubit_gain` and `f_ge`.
- No optimum is computed or written back.

## Analysis

Same metrics as [readout_optimize](readout_optimize.md#analysis): per-class
normalised CDF-gap contrast, and `MixedShots` overlap error (lower is better). With
the regime-B `arb` drive, the overlap is computed on the concatenated g+e shots. A
good point maximises contrast and minimises overlap. The two need not coincide when
the readout itself limits the separation.

## Findings & notes

- Pi/2 optimisation rule (runner note, undated): set the gain to half and optimise
  with `number_of_pulses = 2`.

## Known issues

- The gain centre comes from the current config and the frequency centre from the
  device table. If they disagree (for example after a recalibration not yet copied
  into the device file), the grid is centred inconsistently.
- `print_fidelities` is not disabled, so every point prints misassignment fractions,
  labelled "ne contrast" / "ng contrast". These are P(e→g) and P(g→e), not contrasts.
- Same axis-label and single-point issues as [readout_optimize](readout_optimize.md#known-issues).
