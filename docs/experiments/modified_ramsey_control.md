# modified_ramsey_control: Modified Ramsey at the charge sweet spot (ModifiedRamsey)

Recipe: `R.modified_ramsey_control(...)` (`qicklab.runs.recipes`; every keyword with its default and unit is in the docstring, `help(R.modified_ramsey_control)`). Session groups: [step table](../running_a_session.md#steps). Generated parameter tables come in phase 6.

## What it measures

This step is a sweet-spot null control for charge-parity detection. At a
charge-insensitive bias point (the "sweet spot") the two parity branches are
degenerate, so a Modified Ramsey record taken there should show **no** parity
telegraph. Each cycle:

1. searches for the sweet spot by two-tone spectroscopy and moves the yoko there;
2. takes a SingleShot calibration at V_sweet (first Ramsey, after a bias move, and on
   the `ss_recalib_every_n_cycles` cadence);
3. runs a `ModifiedRamsey` record with **the modified_ramsey sequence**: the cfg is
   built by the same function (`build_modified_ramsey_cfg`) from the session's
   `ModifiedRamsey_params`;
4. analyses it with **the modified_ramsey analysis** (same mapping seed, emission model
   and gates, see [modified_ramsey](modified_ramsey.md#analysis)) and reports
   `gamma01_hz`, `identifiable`, the lag-1 autocorrelation r(1) and the
   separation-normalised lag-covariance sum next to the newest analysed
   modified_ramsey record.

A valid null is `identifiable = False` (or a rate consistent with zero), r(1) near 0,
and a lag-covariance ratio to the MR record near 0 (95 % upper bound well below 1). Its
`acf_amplitude` is NaN: the ACF exponential fit needs at least 5 positive lags and an
uncorrelated record does not have them, so the amplitude is not used to judge the null.
The KMeans split and the moving-average / hysteresis trace are kept as **diagnostic
plots only**.

This needs `ModifiedRamsey_params` (the runner passes it). Without it the step falls back
to the old sequence (see Known issues) and warns. Code: `qicklab.runs.modified_ramsey`
and `qicklab.runs.sweet_spot`.

## Charge-dispersion model

The device's branch separation vs yoko voltage is modelled as

```
S(V) = cd_max · |cos(2π (V − V0) / T)|,     T = cd_period_mv
```

with `cd_max_mhz` and `cd_period_mv` taken from an independent calibration. The
model sets the search step (Strategy A below). The Ramsey tau is the modified_ramsey
one, `tau = tau_harmonic_k/(2 · df)` with the MR `df`; only the fallback without
`ModifiedRamsey_params` uses `df = cd_max_mhz` (tau = 1/(2 · cd_max_mhz)).

## Pulse sequence

1. **Sweet-spot search** (`find_sweet_spot`, moves the yoko).
   - Each spectroscopy point is a `QubitSpecSliceFF` acquisition over ±`SpecSpan`
     around the qubit centre.
   - **Strategy A** (when `cd_period_mv` is known): if the first spectrum shows two
     peaks separated by ≥ `df`, jump **half a period** from the current V, then take
     one more spectrum. Typically 1–2 acquisitions.
   - **Strategy B** (fallback): walk in `dV` steps between `voltage_min` and
     `voltage_max`, measuring each voltage once (one pass of the range; at most
     `max_voltage_tries` steps), tracking the minimum separation. Return to the best
     voltage found and take one new spectrum there.
   - Every spectrum must clear the peak-SNR gate (`freqcal_min_snr` = 4.0 of
     [auto_coherence](auto_coherence.md#stages-in-detail)); the first one gets the
     auto_coherence gain raise (spec `gain` x 1.8, up to 5 times); the walk keeps the
     raised gain only if it showed a line there, else it uses `gain`. A spectrum below
     the gate is never accepted.
   - Accept when a single peak is found, or when sep < `sweet_spot_max_df_mhz`.
   - Qubit frequency = midpoint of the two peaks, or the single peak.
   - If no spectrum of the search clears the gate, or the one re-taken at the best
     voltage does not, the yoko returns to the start voltage and the cycle is **not
     verified** (no Ramsey).
2. **SingleShot calibration** (`SingleShot_MRCalib`, `ss_calib_shots` shots, pi pulse at
   the qubit centre as in modified_ramsey) at V_sweet, before the first Ramsey, whenever
   V_sweet moves by more than 0.1 mV, and every `ss_recalib_every_n_cycles` cycles.
   With `use_active_reset` the readout phase is rotated once before the first cycle
   (`calibrate_active_reset_readout`) and the reset threshold comes from this
   calibration, as in modified_ramsey.
3. **Ramsey** at V_sweet, only if the sweet spot was verified. The sequence is the
   [modified_ramsey](modified_ramsey.md#pulse-sequence) program with every key from
   `ModifiedRamsey_params` (`df`, `tau_harmonic_k`, `mr_reps`, `mr_relax_delay`,
   `max_drive_bandwidth_ratio`, `symmetric_ramsey`, `use_pi_pulse`, reset keys) except
   `f_ge` = the frequency found and `current_voltage` = V_sweet; `rounds = 1`:

```
qubit_ch  ─[pi/2]── tau − 4σ ──[pi/2, φ_close]─ 0.05 µs ─┐
res_ch                                                    [ readout ]── mr_relax_delay ──▶
```

Channels `qubit_ch`, `res_ch`, `ro_chs[0]`; no trigger pin; regime-A readout window.

## How to run

Runs in **regime A**. It moves the yoko and leaves it at the last sweet spot.

```python
run_modified_ramsey_control(ctx, ModifiedRamsey_Control_params, ModifiedRamsey_params)
```

The Ramsey settings and the analysis keys (`hmm_*`, `mapping_*`, `drift_window_ms`,
`expected_parity_dwell_ms`, `ss_calib_shots`, `ss_recalib_every_n_cycles`) come from
`ModifiedRamsey_params`; a sequence key (`mr_reps`, `mr_relax_delay`, pulse,
active-reset and `readout_threshold` keys; `MRC_SEQUENCE_KEYS`) set differently in
`ModifiedRamsey_Control_params` is ignored with a printed note. `cd_max_mhz` and
`cd_period_mv` resolve from the device (`Qubit.parity`).

**Fridge time.** With the CSTQ03 MR values (50000 shots, 500 µs relax, rep ≈ 512 µs) a
Ramsey record takes about 26 s (≈ 10 000 dwells of 2.5 ms), plus one or more search
spectra (101 points × 10 reps × 10 rounds × 1.5 ms ≈ 15 s each). The runner's
`num_cycles = 1000` is therefore many hours. The old 500-shot record (0.13 s at
262 µs, ≈ 50 dwells) was too short for the HMM to identify anything.

## Parameters

Legacy `ModifiedRamsey_Control_params` keys. Defaults are the CSTQ03 runner values.

| Key | Default | Units | Meaning |
|---|---|---|---|
| `cd_max_mhz` | 0.682 | MHz | Peak charge dispersion of the model (the sweet-spot search). Sets tau and the Ramsey `df` only on the fallback path without `ModifiedRamsey_params`; with them (the runner path) both come from the MR dict. Required. |
| `cd_period_mv` | 4.37 | mV | Model period T. Enables Strategy A. Required (read with `[]`). |
| `sweet_spot_max_df_mhz` | 0.1 | MHz | Accept the sweet spot if the separation is below this (or a single peak). |
| `df` | 0.5 | MHz | Separation that triggers the Strategy-A half-period jump. |
| `dV` | 0.0005 | V | Strategy-B step. |
| `voltage_min` / `voltage_max` | 0.000 / 0.010 | V | Search bounds. |
| `max_voltage_tries` | 1000 | count | Strategy-B hard step limit (one pass of the range, 21 steps with these bounds, ends the walk first). |
| `num_cycles` | 1000 | count | Search + Ramsey cycles. |
| `SpecSpan` | 1.0 | MHz | ± spectroscopy span. |
| `SpecNumPoints` | 101 | count | Spectroscopy points. |
| `reps` / `rounds` | 10 / 10 | count | Spectroscopy averaging. |
| `relax_delay` | 1500 | µs | Spectroscopy relax (not used by the Ramsey). |
| `sigma` / `gain` / `qubit_length` | 2 / 700 / 2 | µs / DAC / µs | Spectroscopy drive. `Gauss` is in the dict but unread. |
| `mr_relax_delay` | 0.0 | µs | Fallback only (no `ModifiedRamsey_params`): Ramsey relax. 0 leaves residual excitation (inter-shot carryover, r(1) ≈ +0.3 on CSTQ03). Otherwise the MR value is used. |
| `mr_reps` | 500 | shots | Fallback only: Ramsey shots per cycle. Otherwise the MR value is used. |
| `hysteresis_low` / `hysteresis_high` | 0.4 / 0.6 | fraction | Hysteresis thresholds of the diagnostic moving-average plot. Set by default if absent. |
| `window_ms` | 0.1 | ms | Moving-average window of the diagnostic plot. Set by default if absent. At a relax of ≥ 100 µs it is one shot, i.e. the raw flip count. |
| `use_pi_pulse`, `flip_final_pi2`, `symmetric_ramsey`, `use_active_reset`, `reset_*`, `post_reset_wait`, `tau_harmonic_k`, `max_drive_bandwidth_ratio` | False, …, 1, 1.0 | — | Fallback only; otherwise taken from `ModifiedRamsey_params`. `reset_read_latency_us` is forwarded only when set ([active_reset](active_reset.md#read-latency)). |

The Ramsey cfg always has `pi_gain = qubit_gain` (with `pi2_gain`), `ramsey_tau_us`,
`mr_tau_harmonic_k` and `max_drive_bandwidth_ratio`, exactly as a modified_ramsey record.

## Outputs

- **Spectra** from the search: `QubitSpecSliceFF` records with path `auto-Spec`,
  under `<outer>/ModifiedRamsey_Control/`.
- **SingleShot calibrations:** `SingleShot_MRCalib` records (as modified_ramsey); their
  cfg `current_voltage` is V_sweet, the bias they were taken at.
- **Ramsey record:** `ModifiedRamsey_Control/…_data.h5`, png and json. Same h5
  schema as [modified_ramsey](modified_ramsey.md#outputs). The cfg json includes
  `modified_ramsey_timing`.
- **Parity analysis** with base `…/ModifiedRamsey_Control/Cycle_<n>_MRC_<ts>_continuous`:
  the `_analysis.json` / `_analysis.h5` sidecars and plots of
  [modified_ramsey](modified_ramsey.md#outputs).
- **Analysis files** with base `…/ModifiedRamsey_Control/<…>`:
  - diagnostic plots `_iq_labeled.png`, `_binary.png`, `_state_moving_avg.png`,
    `_state_hysteresis.png`, `_state_hysteresis_jumps.png`;
  - `.npz`, `_config.json`, `_provenance.json`
    ([provenance](../architecture.md#provenance)). The result keys are `parity_identifiable`, `gamma01_hz`,
    `gamma10_hz`, `gamma01_err_hz`, `acf_amplitude` (NaN for an uncorrelated record,
    see Analysis), `acf_r1` (lag-1 autocorrelation) and `acf_r1_mr` (the MR record's),
    `lag_covariance_norm` and `lag_covariance_norm_mr` (drift-corrected lag-covariance
    sum over lags 1..K, K = one expected dwell, divided by the true-state readout
    separation squared), `lag_covariance_ratio_to_mr` and `lag_covariance_ratio_upper95`,
    `lag_covariance_ratio_reason` (why the ratio is NaN, else empty),
    `lag_covariance_ratio_prep_corrected` and `lag_covariance_ratio_upper95_prep_corrected`
    and `lag_covariance_ratio_warning` (the prep-bias flag and correction, see Analysis
    step 2), `blob_snr` (the
    KMeans gate value, so "no switching" can be told from "could not resolve") and
    `mr_reference` (the MR record compared with: file, identifiable, gamma01_hz,
    gamma01_err_hz, acf_amplitude, acf_r1, readout_separation,
    readout_separation_source, readout_prep_e_predicted; None if none).
    `diagnostic_only` lists the KMeans / hysteresis keys (`binary_states`,
    `state_avg`, `state_hysteresis`, `hysteresis_switches`, ...), kept for the plots;
  - one `CycleSummary_<ts>.json` per run, with the same result keys,
    `parity_analysis_warnings`, `mr_reference` and `diagnostic_only` per verified cycle.
  - A cycle whose sweet spot is not verified (separation too large, or no spectrum
    cleared the SNR gate) is recorded with
    `stage_failed = "sweet_spot_not_verified"` and **no Ramsey is run**.
- The rate result is the HMM / ACF of the parity analysis. The hysteresis switch
  count is not a result: in uncorrelated shots it counts thousands of "jumps".
- **MR reference.** The newest `*_continuous_analysis.json` under
  `<outer>/ModifiedRamsey/<date>/`, looked up once at the start. Records taken with
  `parity_analysis_enabled = False` have no sidecar, so the CSTQ03 runner's MR records
  are not found and the step prints "no analysed ModifiedRamsey record". Sidecars
  written before 2026-10 have no `r1` / `lag_covariance_sum` / `readout_separation`;
  against those the ratio is NaN with a reason.
- Not to be confused with the interleaved `validation_controls` of
  [modified_ramsey](modified_ramsey.md#validation-controls) (path
  `ModifiedRamsey_Controls`, plural). Those are acquired on their cadence whether or not
  the parity analysis is enabled; this step has no such switch.

## Analysis

1. **Parity analysis (the result).** `analyze_modified_ramsey_record` on the
   unthresholded shots, with the SingleShot calibration taken at V_sweet and the
   modified_ramsey settings: the mapping fit seeded at the predicted mapping of the
   sequence, `hmm_min_emission_snr`, the i.i.d. likelihood-ratio and resolved-rate
   gates, `drift_window_ms` and `expected_parity_dwell_ms`
   ([modified_ramsey](modified_ramsey.md#analysis)). At a true sweet spot the two
   branches are degenerate, so the record should be `identifiable = False`.
2. **Comparison with the MR record.** r(1), and the statistic of
   [compare_parity_controls](modified_ramsey.md#validation-controls): the
   drift-corrected lag-covariance sum over lags 1..K (K = one expected dwell, the same
   for both records because MRC inherits the MR relax and `expected_parity_dwell_ms`).
   The MR record is at another bias, so its readout scale differs: each sum is divided
   by its record's **true-state** readout separation squared
   (`true_state_separation`: |mu_e − mu_g|² of the SingleShot calibration's clean
   clouds when the joint mixture fit is resolved, `clean_cloud_source = "mixture"`;
   otherwise the raw separation, see "Raw separation" below). The raw labelled-set
   separation is not used when the mixture resolves: the SingleShot pi pulse plays at the
   qubit centre, df/2 from each parity
   branch at the MR bias but on the degenerate line at V_sweet, so the π-prepared set
   is a g/e mixture at the MR bias and its mean is pulled toward g by the e-cloud
   purity. Dividing by that would inflate the MR sum by 1/purity² and bias the ratio
   low (≈ purity², 0.48 at purity 0.7 in the synthetic test, instead of 0.96). White
   readout noise does not enter lags ≥ 1, so the quotient is the lagged covariance of
   the excited-state indicator, the same units for both records. (The clean e cloud
   also removes decay during readout, which the trace shares; that factor is common to
   both biases to the extent T1 is.)
   **Raw separation (the usual case at low readout SNR).** The mixture fit resolves only
   when it raises the likelihood by 2ΔlnL ≥ 9. At the CSTQ03 analog SNR (0.77 on
   2026-08-04) it does not, even at a purity of 0.7 (1000 shots per set: "moments" in
   20 of 20 seeds; at SNR 1.5 in about 14 of 20; at SNR 3 it always resolves). The
   separation is then the raw one, still shrunk by the purity p, which these shots cannot
   measure. On the MR side that biases the ratio **low by ≈ p², toward passing the
   null**; on the MRC side high (conservative). So each analysed record also stores the
   predicted purity `readout_prep_e_predicted` (`predicted_singleshot_prep`: the
   SingleShot pi, `ctx.qubit_sigma` at `ctx.qubit_frequency_center`, applied to the
   branches f_ge and f_ge − df with `predict_pi_transfer`, ideal two-level, averaged;
   None for a flat-top pulse). When the MR reference's source is not "mixture" and its
   predicted purity is unknown (pre-2026-10 sidecar, flat-top pulse) or below
   `SS_PREP_NEAR_ONE` = 0.95, `lag_covariance_ratio_warning` is set and printed as
   `[MRC]   WARNING: …`. `lag_covariance_ratio_prep_corrected` (and its upper bound)
   multiplies the ratio by (s_MRC / s_MR)², s = 1 for a "mixture" source, else the
   predicted purity. It is NaN when the MR purity is unknown or below
   `SS_PREP_CORRECTABLE` = 0.5; an unknown or uncorrectable MRC purity counts as 1, the
   larger ratio. The prediction leaves out decay during readout and thermal g, so it is
   an upper bound on p: the correction removes the detuning part of the bias only.
   For scale, at df = 1 MHz with the pi on the branch midpoint the model gives 0.98 at
   sigma = 0.05 µs, 0.91 at 0.1 µs, 0.70 at 0.2 µs and 0.07 at 0.5 µs; below 0.5 read
   the ratio as a lower bound.
   The ratio MRC/MR and its one-sided 95 % bootstrap bound use `_lag_cov_ratio`, as for
   the validation controls. It is NaN with a reason when the MR record's own sum is not
   significantly > 0, the two K differ (fallback path), or either record lacks the
   statistic. A valid null reads ratio ≈ 0, upper bound well below 1; a telegraph as
   strong as the MR one reads ≈ 1. The ACF exponential-fit amplitude is printed and
   saved but is NaN for an uncorrelated record (fewer than 5 positive lags), so it is
   not the comparison. The per-cycle printout gives identifiable, gamma01, r(1), the
   normalised lag sum and the ACF amplitude, then the MR reference values and the ratio.

Diagnostics (plots and the `diagnostic_only` npz keys; no null distribution):

3. **KMeans(2)** on the IQ shots, scored against the perpendicular bisector of the
   two centroids.
4. **Blob-SNR gate.** KMeans always returns two centroids. With majority relabelling
   it manufactures a ~50/50 split from a single blob. The gate is centroid distance /
   pooled within-cluster RMS:
   - resolved blobs give ≳ 2, one blob ≲ 1;
   - **below 2.0, all shots are set to state 0** in the diagnostic trace; `blob_snr`
     is saved.
5. Otherwise the majority cluster is relabelled state 0.
6. Moving average over `round(window_ms / dt)` shots, then a hysteresis state machine
   (rise above `hysteresis_high`, fall below `hysteresis_low`; `hysteresis_parity_trace`).

## Findings & notes

- Charge-dispersion model parameters `cd_max_mhz = 0.682 MHz`, `cd_period_mv =
  4.37 mV`. They come from an independent calibration; the device and date are not
  recorded in the code. [charge_sweep](charge_sweep.md#doublet-splitting-fit) now fits
  both from the doublet splitting vs bias, in this T convention (it reports T_S = T/2 as
  well). It needs a grid finer than the runner's 5 mV, and its values are not written
  back.
- CSTQ03 Q2, 2026-08-04: the measured doublet splitting df = 2.7 MHz is 4× this
  `cd_max_mhz`. Either the fit is stale, or that doublet is not charge parity (see
  [modified_ramsey](modified_ramsey.md#findings--notes)).
- Runner note, undated: `start_voltage = 0.0059 V` "worked for good T2R", i.e. a
  charge-insensitive point. Under the model, the maxima sit a quarter period
  (~1.09 mV) away from a sweet spot.
- History: older runner comments said "tau is computed from S1 (the separation at
  V1)", "f_ge from two-tone at V_sweet" and "either way the Ramsey still runs". The
  code took tau = 1/(2·`cd_max_mhz`) (since F41 only on the fallback path without
  `ModifiedRamsey_params`; otherwise tau = k/(2 df) from the MR dict), f_ge from
  `find_sweet_spot`, and **skips** the Ramsey when the sweet spot is not verified.
- Before 2026-10 (F41) the Ramsey was not the modified_ramsey sequence (`df =
  cd_max_mhz`, no `tau_harmonic_k` / `ramsey_tau_us`, bandwidth ratio 1.0 instead of
  the MR 1.4, `mr_relax_delay` 0, 500 shots) and the output was the hysteresis switch
  count. Records from then are not comparable with an MR rate.
- Synthetic check (tests/test_mrc_parity_analysis.py): uncorrelated shots at the MR
  cadence give `identifiable = False` and |r(1)| < 0.03 while the hysteresis counts
  thousands of jumps; relax-0 carryover (c = 0.4) gives r(1) > 0.2 with no telegraph;
  an injected 200 Hz telegraph is identified within 25 %. Against a 200 Hz telegraph MR
  record read back from its sidecar, an i.i.d. null at twice the readout scale has a NaN
  ACF amplitude and a lag-covariance ratio of −0.01 (95 % upper 0.01); the same
  telegraph at that scale reads 0.96. With the MR SingleShot at e-cloud purity 0.7
  and V_sweet at purity 1, the same telegraph at both reads 0.96 (95 % upper 1.04) on
  the true-state separation, and would read 0.48 on the raw one. With an MR reference
  whose separation is raw (source "moments", purity 0.7) the ratio reads 0.49, is
  flagged, and the prep-corrected ratio reads 1.0; a 1000-shot SingleShot at SNR 0.77
  and purity 0.7 resolves to "moments" with the separation shrunk to ≈ 0.7 of the true
  one.

## Known issues

- **Without `ModifiedRamsey_params` it is not the same sequence as modified_ramsey**
  (the frozen regression runner calls it that way): `df = cd_max_mhz` (0.682) instead
  of the MR `df`, `tau_harmonic_k` 1, `max_drive_bandwidth_ratio` 1.0, and this dict's
  `mr_reps` / `mr_relax_delay` (500 / 0 in the CSTQ03 file). A null then is not
  comparable to a modified_ramsey record; the step warns.
- The SingleShot calibration's pi pulse is at the qubit centre
  (`ctx.qubit_frequency_center`), as in modified_ramsey, not at the line found at
  V_sweet. The MRC/MR comparison is normalised by the true-state (mixture-fit)
  separation, so it does not depend on that pulse's prep fidelity only when the
  mixture fit resolves (`clean_cloud_source = "mixture"`). At low readout SNR it
  usually does not: the source is `"moments"` (silent in the calibration) or
  `"moments_fallback"` (which warns), the separation is the raw one, and a poor MR prep
  biases the ratio low, **toward passing the null**. The comparison flags this
  (`lag_covariance_ratio_warning`) and gives a prep-corrected ratio from the predicted
  pi-pulse purity, which is model-based (ideal two-level, an upper bound on the purity)
  and NaN below a predicted purity of 0.5. The fix is a resolved mixture (more
  SingleShot shots or a better readout) or a SingleShot pi on the branches.
- The MR reference is the newest analysed record on disk, whatever its bias or
  settings; it is printed and saved, not checked.
- A single line (`peak_sep` None) that clears the SNR gate is a verified sweet spot
  whatever `sweet_spot_max_df_mhz` says. (Before 2026-10 (F35) a noise-only spectrum,
  which the peak finder reports as one peak, was too.)
- The SNR-gate keys (`freqcal_*`) are not forwarded from `ModifiedRamsey_Control_params`;
  the auto_coherence defaults apply.
- **Acceptance threshold vs peak finder.** The peak finder never returns two peaks
  closer than its 0.10 MHz minimum separation, so `sep < 0.1 MHz` is effectively
  unreachable for a two-peak spectrum. Acceptance in practice comes only from a
  single peak.
- **Half-period jump vs the model.** As written, S(V) = cd_max·|cos(2π(V−V0)/T)|
  repeats every T/2, so a jump of T/2 lands where S is unchanged. Zeros are a
  quarter period from maxima. If Strategy A never converges, this is the likely
  reason. Which of the model or the jump is intended is not documented.
- Strategy A drops the pre-jump voltage from best-tracking. If the jump makes things
  worse, the search cannot return to the starting voltage.
- The step mutates the caller's parameter dict (`setdefault` of the hysteresis keys).
  The yoko is not restored, and `yoko_fixed` is ignored.
- If `window_n` exceeds the number of shots, the moving-average trace is longer than
  the time axis and the plot raises.
- f_ge from the search is the peak midpoint, but the program treats `f_ge` as the
  upper branch. At a true sweet spot the branches are degenerate, so this only matters
  if the spot is not reached.
