# IQ conventions

Each readout returns a complex number I + iQ per shot (or per average). The qubit state moves that
point along some direction in the IQ plane, set by cable delay, `res_phase` and the resonator
response. Different steps turn the complex data into a real signal in different ways; this page
lists them so you know what a plotted "amplitude" or "fidelity" is.

All averaged I/Q values in plots are accumulated sums divided by the window length in readout
cycles ("normalised units"). Single-shot thresholds, separators and `readout_threshold` are in
these units.

## 1. Cable winding (not used at present)

    sig -> sig * exp(1j * (2*pi * cavity_winding_freq * pulse_freq + cavity_winding_offset))

`pulse_freq` is in MHz, so `cavity_winding_freq` is effectively an electrical delay in us and
`cavity_winding_offset` a phase in rad. It corrects the frequency-dependent phase of the cables.
It is **not** a quadrature alignment.

- Applied in `QubitSpecSliceFF`, `AmplitudeRabiFF`, `AmplitudeRabiFF_N`, `T1FF`,
  `ChargeDispersionQuasiCW`. Not applied in `CavitySpecFF`, `ChiShift`, `T2EMUX`, `T2R`, `T1_SS`,
  `ChargeDispersion` or the single-shot family.
- In those five experiments `pulse_freq` is a single number, so the correction is a constant
  rotation, never a frequency-dependent one.
- Both values are 0 in `BASE_CONFIG`, so the correction is the identity.
- Historical calibration, kept for reference only (device and date unknown):
  `cavity_winding_freq` 0.45917414 (earlier 1.0903695), `cavity_winding_offset`
  -32.10723885 + pi (earlier -15.77597).

## 2. Spectroscopy: principal-axis projection, not |I + iQ|

Two-tone spectroscopy often puts almost the whole qubit response into one quadrature, on top of a
large constant offset in the other. `|I + iQ|` (or its square) is then dominated by the big,
noisy background quadrature: peak finding and Lorentzian fits lock onto noise spikes, and
charge-sweep heatmaps wash out. qicklab projects instead (`qicklab.analysis.iq`,
`project_iq_signal`):

1. subtract the median of I and of Q;
2. find the principal axis, `theta = 0.5 * angle(sum(dev**2))`, and project onto it;
3. take the baseline from the outer `edge_frac` = 15% of points on each side (the span is
   centred on the expected line, so the edges are the most likely off-resonant points);
4. orient by total excursion mass (more area above than below), not by the single most extreme
   point.

Result: a real trace with a ~0 baseline and the qubit as a positive peak. Used by `two_tone_spec`
(`qubitFreq` = argmax of the projection), the two-tone peak finder, `charge_sweep` heatmaps and
the zero-span parity-frequency search.

Evidence:

- Q6 two-tone spec, 2026-06-02 (device not recorded): the real feature, in I at about 3054 MHz,
  was missed in favour of Q-noise spikes at 3038 and 3069 MHz when the magnitude was used.
- CSTQ03 Q2 two-tone spec, 2026-09-02 12:03: with a whole-trace-median baseline and "flip if
  |min| > |max|", a broad response at about 3753 MHz was inverted into a dip and both "peaks" were
  put on edge noise at 3764 MHz, although I and Q both showed the bump. This led to steps 3 and 4.

## 3. Rotations used by individual experiments

| Experiment | Method | What it does |
|---|---|---|
| `AmplitudeRabiFF` | principal axis, `0.5*angle(sum(dev**2))` of ADC 0's mean-subtracted trace | rotates both ADCs by -angle so the g->e (maximum-variance) axis lies on I, signed so I increases toward the pi pulse (mean of the first 3 points, gain ~ 0, below the trace mean; valid up to about (N-1)/4 periods); stored as `iq_rotation_rad`, with the major/minor variance ratio as `iq_axis_contrast_ratio` (near 1 = no contrast, angle arbitrary); layered on top of cable winding; shares `principal_axis_angle` with section 2 |
| `AmplitudeRabiFF_N` | same signed principal axis, in display | same rotation; `rotation_phase` = -angle (multiplier phase), not saved |
| `T1FF`, `T2EMUX` | principal axis of the mean-subtracted trace (`decay_axis_phase`) | multiplies by `exp(1j*p)`, p = -(axis angle), so the decay lies in I, signed so the first (shortest-wait, most excited) point is at or above the trace mean; p in [0, 2*pi), 0 for a constant trace; saved as `t1_fit_rotation_rad` / `t2e_fit_rotation_rad`. A fixed cfg `rotation_angle` replaces it, and `min_max` normalisation is applied only with that fixed angle |
| `T2R` | principal axis, `0.5*angle(sum(dev**2))` on the mean-subtracted trace | projects onto the g-e oscillation axis (fringe in I around 0, sign so the t = 0 point is positive); stored as `osc_fit['iq_axis_rad']`; shares `principal_axis_angle` with section 2 |
| single shot (`hist_process`) | line through the g and e medians | see section 4 |

The four principal-axis rows use the same axis (`principal_axis_angle`, so the decay and Rabi axes agree to float
precision on the same trace); they differ only in the sign rule and in whether the angle or its
negative is stored. Until 2026-10 `T1FF` and `T2EMUX` (and, before that, `AmplitudeRabiFF_N` with
500 points) used `min_q_range_phase`: the phase on a 200-point grid over [0, pi] that minimised
the peak-to-peak of Q, with no sign rule. Peak-to-peak is set by the two most extreme points, so
it follows the noise. On 300 synthetic T1 traces (100 waits over 6 T1, unit contrast at a random
IQ angle, Gaussian noise sigma per quadrature) the median angle error (95th percentile) was
2.3 deg (6.6) for min-Q-range against 0.8 deg (2.3) for the principal axis at sigma = 0.05, and
5.4 (14.3) against 1.9 (5.4) at sigma = 0.10; the sign rule was right on all 600 traces and the
fitted-T scatter was the same within 1%.
`min_q_range_phase` is kept as an alias of `decay_axis_phase` (its `n` is ignored).

## 4. Single-shot readout: angle, threshold, "fidelity"

`hist_process` (`qicklab.analysis.readout`) takes the g-prepared and e-prepared shots:

1. medians of each cloud; rotate all shots by `theta = -arctan2(Qe - Qg, Ie - Ig)` so the g->e line
   lies along I;
2. histogram the rotated I of each class in 200 bins;
3. contrast curve `|cumsum(n_g) - cumsum(n_e)| / (0.5*N_g + 0.5*N_e)`; its maximum gives the
   threshold (a bin edge) and the printed "fidelity".

The printed "Fidelity" is the **readout contrast**
C = max |CDF_g - CDF_e| = P(g|g) + P(e|e) - 1, not the assignment fidelity. With equal priors and
the optimal threshold, F_assign = (1 + C)/2. Example: a legacy "Fidelity = 44.90%" is C = 0.449,
F_assign = 72.45%. The display clips the value to at most 1.0.

`single_shot` prints `angle` (theta) and `threshold`; `t1_ss` reuses them to classify its shots.

Two variants exist and give different numbers: the QM-team version (pooled normalisation as
above) and the version relocated from the Inductive_Coupler project, used by `readout_optimize`
and `qubit_optimize` (per-class signed normalisation, `print_fidelities=`). The refactor keeps
both as one function, `hist_process(..., normalize="pooled" | "per_class", print_fidelities=False)`;
`single_shot` uses the default `"pooled"`, `readout_optimize` passes `"per_class"`.

Readout quality gates used by the parity analysis: analog SNR < 1 warns; contrast < 0.3 warns;
fewer than 500 labelled shots per class warns.

## 5. Separator and bisector classification

The apriori separator (measured by a single-shot calibration with a pi pulse inside
`modified_ramsey`, `active_reset_verify` and `zero_span_parity`):

    g_center = mean(I_g, Q_g),  e_center = mean(I_e, Q_e)
    normal   = e_center - g_center,  midpoint = (g_center + e_center) / 2
    score    = (iq - midpoint) . normal        # score > 0  ->  e

This is classification by the perpendicular bisector of the two means; `ActiveResetVerify`
classifies the same way. The centres are means of all prepared shots (thermal and decay tails
included), not fitted blob centres. The separator lives in the normalised units of
`collect_shots`, which hard-codes `ro_ch=0`; zero-span strobe data are normalised the same way
(`us2cycles(read_length, ro_ch=0)`) so a single-shot separator applies to them.

KMeans with two clusters always returns two centroids; with majority forcing it manufactures a
~50/50 split from a single blob. The charge-parity code gates it: centroid distance / pooled
within-cluster RMS, resolved blobs give more than about 2, one blob less than about 1; the
threshold used is 2.0.

## 6. Active-reset thresholds

The tProc compares the **raw accumulated I** of a readout against a threshold register. Q is not
used. Consequences:

- g and e must separate along I. The active-reset calibration rotates `res_phase` (a register
  value) so the g->e axis lies on +I: it measures the axis angle phi, tries `-phi` then `+phi`
  (deg2reg's sign convention is never trusted), keeps the one with the smallest |Q separation|,
  then re-measures and reads the threshold off the rotated blobs:
  `readout_threshold = (g_I + e_I)/2`, `reset_ground_below_threshold = g_I < e_I`. It warns if
  the residual Q separation exceeds 10% of the I separation.
- Threshold precedence: a manual `readout_threshold` wins; otherwise it is derived from the
  current apriori separator, re-derived at every single-shot recalibration (idempotent, tracks
  drift). Leave it `None` (auto) unless you have a reason.
- Units: `readout_threshold` is normalised (I / window cycles), the tProc sees raw I, so the
  program multiplies the threshold by the window length (`ro_norm`) before loading it.
- The deployed tProc compares as unsigned. Data on TATQ01/BFE, 2026-06-05/06: the corrective pi
  fired on every shot with negative accumulated I; ground-state damage tracked the below-zero
  fraction of the g blob, and a sweep with g_I near 0 lost exactly half its ground shots. Fix: add
  the same large positive offset to both operands.
- Offset size: the accumulator sums `ro_norm` samples of at most 15 bits (12-bit ADC + 3 bits
  decimation gain), so |raw I| <= `ro_norm * 2^15`. `ModifiedRamsey` uses
  `cmp_offset = int(ro_norm) << 15` and requires it below 2^30 (operands must fit 32-bit signed;
  `safe_regwi`). History: the first fix used a fixed `1 << 24`, on the assumption that |raw I| is
  about 1e4-1e5. That assumption is superseded: beyond 512 readout cycles (about 1.7 us at
  307.2 MHz) the sum can exceed 2^24 and wrap, firing the pi on the wrong branch with no error (2^24 is about 9x too small for
  long windows, 2026-07-28). A threshold sanity check cannot catch this, because the threshold
  itself sits between the blobs.

## 7. Thermal population (single shot without a pi pulse)

With `number_of_pulses` = 0 `single_shot` acquires undriven shots and, right after them in the
same call, a labelled reference of shots after one pi pulse (`thermal_pi_calibration`, default
True). The excited (thermal) population is the maximum-likelihood mixture weight
(`qicklab.analysis.readout.fit_thermal_population`):

1. model: both sets are (1 - q) N(g, Sigma) + q N(e, Sigma) with one shared covariance; q = p for
   the undriven shots, q = w for the pi shots;
2. EM fits g, e, Sigma, p and w jointly, started both from p = 0.05, w = 0.9 and from a KMeans
   2-cluster split of the pooled shots (e = the cluster enriched in the pi shots); the start with
   the higher likelihood wins, and |e> is by definition the state the pi pulse populates
   (w > p). The undriven shots pin g, the
   pi shots pin e, and each set's own weight absorbs its contamination (thermal population in the
   g set, pi infidelity and T1 decay in the e set), so neither set is used as a histogram
   template;
3. with the components fixed, p is solved exactly on [0, 1] (the log likelihood is concave in p);
   its standard error comes from the outer-product-of-scores information over all fitted
   parameters, so it includes the uncertainty of the centres;
4. without the pi run, `thermal_e_center` (an (I, Q) pair, or one pair per read) is held fixed and
   g, Sigma and p are fitted from the undriven shots. A stale `thermal_e_center` does not follow
   readout drift. With neither, p is NaN and a warning is printed;
5. p, its SE, w (`thermal_pi_population`), the width ratio and the fitted centres and covariance
   are all saved as NaN (g and e may even be mirrored), with a warning that prints the unguarded p
   and w, when the fitted g-e separation is below 1 sigma, or when the pi contrast w - p is below
   4 times its standard error: the pi pulse did not measurably move this read's populations, so
   which cloud is |e> is undetermined. This normally happens for every read of a multiplexed run
   except that of the qubit the pi pulse drives (`qubit_ch`), for an off-resonant pi pulse, and
   near p = 0.5, where the pi pulse swaps nearly equal populations (w = F(1 - p) + (1 - F)p ~ p).
   The guard sees any change between the two sets, not the pi pulse: if a non-driven read's
   cloud moved between the runs (readout drift, cross-Kerr/ZZ to the driven qubit), the fit can
   take the moved cloud as |e> and return a finite, meaningless p without a per-read warning
   (synthetic d = 3 sigma, p = 3 %: finite in 0/20 seeds unshifted, 1-4/20 at a 0.3-0.5 sigma
   shift, 14-16/20 at 1 sigma). Only the read of the qubit on `qubit_ch` is a population, even if
   another read returns a number; with several reads a warning says so.

On synthetic data with equal g and e widths (sigma = 1, 2000 + 2000 shots, pi fidelity 0.9, g-e
distance d = 2-5 sigma, p = 0-10 %, and p = 0.45 with a 95 % pi pulse) p is unbiased within its
SE. Two departures from the model bias it:

- **Unequal widths.** The shared covariance assumes the e cloud is as wide as the g cloud. A
  wider e cloud (measurement-induced transitions, long windows) biases p **low**, a narrower one
  **high**, most at small d: sigma_e = 1.2 sigma_g turns p = 3 % into 1.9/2.6/3.1 % at
  d = 2/3/5 sigma, 1.5 sigma_g into 1.2/1.8/2.7 %, and 0.8 sigma_g turns p = 0 into
  3.2/0.6/0.0 %. The diagnostic `thermal_fit_e_width_ratio` = (det Sigma_e / det Sigma_g)^(1/4)
  of the responsibility-weighted component covariances at the fit is 0.99 +- 0.013 for equal
  widths and reads closer to 1 than the truth (1.2 reads 1.10-1.17, 0.8 reads 0.80-0.86); a
  warning is printed when it is off 1 by more than 5 % and by more than 4 standard errors.
- **T1 decay** during the readout window smears excited shots toward g and biases p **low**: if
  a fraction P_dec of excited shots decays within the window, p is low by about 0.5-0.9 x P_dec
  in relative terms (P_dec = 0.2: -11 to -17 %, up to -27 % at d = 2 sigma). The pi-run weight w
  (`thermal_pi_population`) is low by a similar amount. The smear barely moves the width ratio
  (1.00-1.05 for P_dec <= 0.3), so the width warning does not flag it.

The scatter labels still come from the tail classifier (`classify_thermal_tail`):

1. robust centre and covariance of the main blob with MinCovDet (support fraction 0.75,
   `random_state` 0);
2. Mahalanobis d^2 above `thermal_tail_md2_threshold` marks a tail point (the 95% chi-square value
   for 2D is about 5.99; use 6-9 depending on overlap; default 6.0);
3. protrusion axis = mean of the farthest max(10, 5%) points minus the centre; width along it =
   1.4826 x MAD;
4. a shot is excited if its projection exceeds median + k x width, k = `thermal_tail_sigma_threshold`
   (2.0-3.0 by aggressiveness, default 2.5).

The fraction of shots it labels excited is saved as `thermal_tail_fraction` and is **not** a
population estimate, and it is not conservative: at k = 2.5 and N = 2000 it reads about 1 % at
zero population (the axis is chosen from the farthest 5 % of points, so the floor exceeds
Q(2.5) = 0.62 %), and below d of about 4 sigma most excited shots fall under the threshold, so it
reads low (true 0/1/3/10 % gives about 1.0/1.2/1.5/2.7 % at d = 2 sigma, 1.1/1.6/2.9/6.9 % at
d = 3 sigma, 1.1/1.8/3.8/10.9 % at d = 5 sigma). If the classifier fails (including sklearn
missing) it silently returns all labels 0 and a NaN threshold.

## Known issues

- Before 2026-10 `AmplitudeRabiFF` estimated its rotation over both ADC channels concatenated
  (its data have shape (2, 1, N)), so the ADC 0 - ADC 1 background offset, not the Rabi axis, set
  the angle and most of the contrast could end up in Q; its sign was arbitrary. It now uses ADC 0
  only, with a fixed sign (section 3).
- `hist_process` returns the **left** edge of the bin where the contrast peaks; the optimum lies
  up to one bin higher. When `ran` is given the histogram range is centred on the g cloud only and
  the e cloud can fall outside it.
- `hist_process` in the readout-optimise variant prints misassignment fractions labelled
  "ne contrast" / "ng contrast", twice.
- Before 2026-10-13 `ActiveResetVerify` used the fixed `1 << 24` offset and the readout index
  instead of the tProc input channel, so for windows longer than about 1.7 us (512 readout
  cycles) its verdicts from then do not test the mechanism `ModifiedRamsey` uses. It now shares
  `ActiveResetMixin` with `ModifiedRamsey`.
- The calibration's first single-shot run is used only for the axis angle; each calibration makes
  2-3 single-shot acquisitions, all saved under `SingleShot_MRCalib`, with 1000 shots regardless of
  the step's own calibration-shot setting.
