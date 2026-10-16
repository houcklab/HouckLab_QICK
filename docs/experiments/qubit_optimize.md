# qubit_optimize: single-shot qubit gain × frequency map (QubitPulseOpt_wSingleShotFF)

## What it measures

A 2-D grid over qubit drive gain and qubit drive frequency. At every point the step
takes an e single-shot block, pairs it with a |g> reference block, and records the
single-shot "fidelity" (a contrast) and the labelled double-Gaussian overlap error, as in
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

- **h5:** `fid_mat` (gain × freq), `overlap_mat`, `snr_mat` (since 2026-10; analog SNR,
  as on [readout_optimize](readout_optimize.md#outputs)), `qubit_fpts` (MHz), `gain_pts`
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
  - since 2026-10, the per-point statistics and the recommended point, with the same
    names and meaning as on [readout_optimize](readout_optimize.md#outputs):
    `fid_err_mat`, `Pgg_mat`, `Pee_mat`, `threshold_mat`, `angle_mat`,
    `fid_smooth_mat`, `tied_mask`, `best_gain`, `best_freq`, `best_fid`,
    `best_fid_err`, `best_fid_smooth`, `median_fid_err`.
- **png:** written inside `acquire()`. `display()` is a no-op. The fidelity colorbar
  title gives the median per-point standard error.
- **json:** the cfg. It holds the last grid point's `qubit_gain` and `f_ge`, and
  `Pulse = True`.
- The recommended point (argmax of the 3×3-smoothed contrast) is printed and saved,
  but not written back.

## Analysis

Same metrics as [readout_optimize](readout_optimize.md#analysis): per-class
normalised CDF-gap contrast, and the labelled overlap error `2 Φ(−d/2)` (lower is
better; `labelled_overlap_error`, computed from the point's g reference and e shots for
an `arb`, `flat_top` or `const` drive; before 2026-10 it was the KMeans-based `MixedShots`
on the concatenated g+e shots). The overlap excludes state-preparation error that its
likelihood test can resolve, so on this map it measures the **readout** separation of the g
and excited clouds, not the quality of the pulse. Once a resolvable fraction of the e shots
is excited, the fit finds that minority and the overlap sits near the readout-limited value
whatever the excitation: with 1000+1000 synthetic shots it is within ≈0.01 of `2 Φ(−d/2)`
from about 30% excitation up to 100% at d = 4 (from about 50% at d = 2–3). It reads
clearly high only where little is excited (below ≈20% at d = 4, ≈30% at d = 2–3: far off
resonance, very low gain) and approaches 1 only below ≈5–10%. **Choose the pulse from
`fid_mat` (contrast), not from the overlap**; the overlap tells you how well the readout can resolve the state you reached.
Without the likelihood test about 1 in 13 points with no separation at all read below 0.8
and looked like good points; with it about 1 in 2000 still does (reading 0.41–0.48), and
about 0.3–1% of weakly separated points (d ≈ 0.25–0.5) still read 0.2–0.55 too low (details in
[readout_optimize](readout_optimize.md#analysis)). `hist_process` runs once per point.
The per-point standard error `fid_err_mat`, the smoothed map, the recommended point and
`tied_mask` are computed as on [readout_optimize](readout_optimize.md#analysis), including
the printed warning when the recommendation is on the map border (on a 21×21 map that is
flat within noise this happens about 63% of the time against 18% of the points, so a border
recommendation is usually noise unless the contrast clearly rises toward that edge). Points
in the same half-row share their g shots (below), so `fid_err` is the right error of
one point but overstates the noise of the difference between two points of a half-row.
Off-resonant columns have near-zero true contrast, where the threshold-selection bias that
`fid_err` leaves out is about +0.04 (2 standard errors) at 1000 shots, so they read
C ≈ 0.04 ± 0.02 rather than 0 (see the per-point uncertainty bullet on
[readout_optimize](readout_optimize.md#analysis)).

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
