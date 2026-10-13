# readout_optimize: single-shot readout gain × frequency map (ReadOpt_wSingleShotFF)

## What it measures

A 2-D grid over readout (cavity) DAC gain and readout frequency. At every grid point
the step takes a full g/e single-shot pair with the [single_shot](single_shot.md)
program and records two figures of merit: the histogram "fidelity" (actually a
contrast, see below) and the **overlap error** of a double-Gaussian fit. Use it to
choose `pulse_gain` / `pulse_freq` for the single-shot readout. The companion step
[qubit_optimize](qubit_optimize.md) does the same over qubit gain × qubit frequency.
Code: see `qicklab.experiments.readout_optimize`.

## Pulse sequence

Per grid point: two `SingleShotProgram` runs (Pulse off, Pulse on), with
`number_of_pulses = 1`. The sequence is the one on [single_shot](single_shot.md#pulse-sequence)
(trigger pin 0 per qubit pulse, readout window with cross-clock extension), with
`pulse_gain` and `pulse_freq` replaced by the grid values.

```
for gain in linspace(cav_gain_Start, cav_gain_Stop, cav_gain_Points):       # outer
    for f in linspace(trans_freq_start, trans_freq_stop, TransNumPoints):   # inner
        [no pulse ─ readout]×shots   then   [pi ─ readout]×shots
```

## How to run

Runs in **regime B**, with the single-shot window and `qubit_pulse_style = "arb"`.

```python
PLAN = [R.readout_optimize(gain_start=3000, gain_stop=3600, gain_pts=7,
                           span=0.1, trans_pts=21)]
```

The frequency axis is centred on the current `pulse_freq`: `pulse_freq ± span/2`.

## Parameters

Legacy `SS_R_params` keys. Defaults are the CSTQ03 runner values. The cfg keys
written are shown after the arrow.

| Key | Default | Units | Meaning |
|---|---|---|---|
| `gain_start` → `cav_gain_Start` | 3000 | DAC | First readout gain. |
| `gain_stop` → `cav_gain_Stop` | 3600 | DAC | Last readout gain (inclusive). |
| `gain_pts` → `cav_gain_Points` | 7 | count | Gain points. Must be ≥ 2. |
| `span` | 0.1 | MHz | Full frequency span around `pulse_freq`. |
| `trans_pts` → `TransNumPoints` | 21 | count | Frequency points. Must be ≥ 2. |
| `shots`, `relax_delay`, window | single_shot group | — | Inherited from regime B (`SS_params`). |

## Outputs

Path `SingleShot_OptReadout/`.

- **h5:** `fid_mat` (gain × freq), `overlap_mat` (gain × freq), `trans_fpts` (MHz),
  `gain_pts` (DAC).
- **png:** two heatmaps, fidelity (%) and overlap error. They are written at the end
  of `acquire()`; `display()` does nothing.
- **json:** the cfg. It holds the **last** grid point's `pulse_gain` and `pulse_freq`,
  not the optimum.
- **No optimum is computed or written back.** Read the heatmaps and set the readout
  gain/frequency in the device file.

## Analysis

- **"Fidelity".** This step uses the per-class-normalised variant of `hist_process`:
  `max[ cumsum(n_g)/N_g − cumsum(n_e)/N_e ]`. It is a readout **contrast**, and it is
  numerically different from the [single_shot](single_shot.md#analysis) number,
  which uses pooled normalisation. Both variants are kept on purpose (the
  per-class one came from the Inductive_Coupler code). `F_assign = (1+C)/2` applies.
- **Overlap metric** (`MixedShots`):
  1. KMeans splits the shots into two clusters.
  2. The data are rotated onto the inter-centroid axis and the rotated I is
     histogrammed (200 bins).
  3. A double Gaussian is fitted, seeded from the cluster stats.
  4. `OverlapErr = max(A_overlap/A_1, A_overlap/A_2)`, where `A_overlap` is the area
     under min(G1, G2). **Lower is better.** It is NaN if either ratio exceeds 0.9.
- **Which shots go into the overlap.**
  - With an `arb` or `flat_top` qubit drive (the regime-B default), the g and e shots
    are concatenated.
  - With a `const` drive, only the e shots are used.

## Findings & notes

None recorded with dates. Readout-gain history per qubit lives on
[devices/CSTQ03](../devices/CSTQ03.md).

## Known issues

- Axis labels: the frequency axis is labelled GHz but the values are MHz. The second
  panel's y label reads "Cavity Atten (dB" but it is DAC gain.
- A sweep axis with a single point raises IndexError (the step size is
  `X[1] − X[0]`).
- `hist_process` is computed twice per point. That is wasted time, but the result is
  the same.
- If the double-Gaussian fit fails, it prints "curve_fit failed" and the parameters
  fall back to all ones. `OverlapErr` for that point is then computed from the dummy
  fit and means nothing.
- MixedShots uses `arctan`, not `arctan2`. If the two cluster centres share the same
  I, the rotation divides by zero.
- `pulse_gains = [gain/32000]` is written into the cfg each point (legacy
  normalisation). It appears unused by the program.
- Calling `save_data()` without an argument raises.
