# qubit_optimize: single-shot qubit gain × frequency map (QubitPulseOpt_wSingleShotFF)

## What it measures

A 2-D grid over qubit drive gain and qubit drive frequency. At every point the step
takes an e single-shot block, pairs it with a |g> reference block, and records the
histogram "fidelity" (a contrast) and the double-Gaussian overlap error, as in
[readout_optimize](readout_optimize.md). The |g> reference plays no qubit pulse, so it
does not depend on the grid point: it is taken once per gain-row boundary, not at
every point (see [Analysis](#analysis)). Use it to fine-tune the pi pulse, or the
pi/2 pulse (see below), against the real single-shot figure of merit rather than an
averaged Rabi. Code: see `qicklab.experiments.readout_optimize`.

## Pulse sequence

`SingleShotProgram` runs with `number_of_pulses` qubit pulses (e) or none (g). The
structure is in [single_shot](single_shot.md#pulse-sequence) (trigger pin 0 before
each pulse, 0.05 µs between pulses, single-shot readout window). One g block opens
the map, one follows every gain row, and every grid point is one e block:
`qubit_gain_Points + 1` g programs plus `qubit_gain_Points × QubitNumPoints` e
programs (before 2026-10: one g and one e program per point, twice the e count).

```
G[0] = [ readout ]×shots                                                       # g block 0
for r, g in enumerate(linspace(qubit_gain_Start, qubit_gain_Stop, qubit_gain_Points)):  # outer
    for f in linspace(qubit_freq_start, qubit_freq_stop, QubitNumPoints):       # inner
        [ (pulse g @ f) × number_of_pulses ─ readout ]×shots                     # e block
    G[r+1] = [ readout ]×shots                                                  # g block r+1
```

Row `r` is bracketed by `G[r]` and `G[r+1]`. At the 21 × 21 default this is 463
programs instead of 882, about 48 % less fridge time.

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
  (DAC), and the g-reference record:
  - `g_ref_index` (gain × freq): which g block `G[b]` each point was analysed against
    (`r` or `r + 1` for row `r`).
  - `g_block_time` (`qubit_gain_Points + 1`): when each g block finished, in seconds
    since the start of `acquire()`.
  - `g_drift_frac` (`qubit_gain_Points`): per row, the shift of the g cloud from
    `G[r]` to `G[r+1]` along the g→e axis, as a fraction of the g–e separation
    (positive = toward e). NaN if the row has no finite fidelity.
  - `g_drift_sigma` (`qubit_gain_Points`): the same shift in units of the g cloud's
    width along that axis (1.4826 × MAD of `G[r]`).
- **png:** written inside `acquire()`. `display()` is a no-op.
- **json:** the cfg. It holds the last grid point's `qubit_gain` and `f_ge`, and
  `Pulse = True`.
- No optimum is computed or written back.

## Analysis

Same metrics as [readout_optimize](readout_optimize.md#analysis): per-class
normalised CDF-gap contrast, and `MixedShots` overlap error (lower is better). With
the regime-B `arb` drive, the overlap is computed on the concatenated g+e shots. A
good point maximises contrast and minimises overlap. The two need not coincide when
the readout itself limits the separation. `hist_process` runs once per point.

**Shared g reference.** Each point's e block is paired with the bracketing g block
nearer to it in time: the first `ceil(QubitNumPoints / 2)` columns of row `r` use
`G[r]`, the rest use `G[r+1]` (and are analysed once `G[r+1]` is in). So every point
in a half-row shares the same g shots. Consequences:

- Point-to-point noise within a half-row is smaller than before, because the g half of
  the contrast is common; a g-block fluctuation shifts the whole half-row together.
- With an `arb`/`flat_top` drive the overlap metric pools g and e shots, so the
  overlap values of a half-row also share the same g shots.
- Each g block is at most `ceil(QubitNumPoints / 2)` e programs away from the points
  that use it (about 1 min at 1000 shots and 6 ms relax delay), compared with zero
  before.

**Drift check.** After each row the step compares `G[r]` with `G[r+1]` (`g_reference_drift`
in `qicklab.experiments.readout_optimize`): the median shift of the g cloud along the
axis from the `G[r]` median to the median of the row's best-contrast e block, divided by
that g–e separation (`g_drift_frac`) and by the g cloud's robust width (`g_drift_sigma`).
If `|g_drift_frac| > 0.05` (`G_DRIFT_WARN_FRAC`) and the shift is also more than three
standard errors of a median difference (`G_DRIFT_WARN_NSE`: `|g_drift_sigma| >
3 × 1.2533 × sqrt(1/n_start + 1/n_end)`, about 0.17 at 1000 shots per block) it prints

```
WARNING: |g> reference drifted +0.083 of the g-e separation (+1.40 sigma) across gain row 7 (gain 4310); that row of the map may be biased
```

and the row should be treated with suspicion (re-run it, or check the readout for
drift). The check uses medians of two independent blocks, so with 1000 shots per block
the statistical scatter of `g_drift_sigma` is about 0.06, and that of `g_drift_frac` is
0.06 divided by the g–e separation in units of the g width (about 0.02 at 3 σ). With a
small separation (a weakly driven row) `g_drift_frac` alone would exceed 0.05 on noise;
the standard-error condition keeps such rows quiet, so a printed warning means the shift
is both real (about 0.3 % of rows warn on noise alone) and large compared with the
g–e separation. Both numbers are saved for every row whether or not it warned.

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
- The drift check only warns. Nothing is re-measured or corrected, and a drift faster
  than one row is seen only as its net change between the two bracketing blocks.
- The drift reference e block is the row's best-contrast point. In a row where the
  drive barely excites the qubit, the g–e separation is small and `g_drift_frac` is
  inflated (the warning is gated on `g_drift_sigma` as well, so it is not printed for
  noise alone, but the saved `g_drift_frac` of such a row is not meaningful).
