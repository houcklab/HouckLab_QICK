# undriven_single_shot: readout-only blob test and telegraph series (UndrivenSingleShot)

## What it measures

This step takes single-shot readouts of a qubit that is **never driven** and
characterises the IQ cloud: centre, width, and whether a second blob is resolvable
and how populated it is. There is no |e> reference, so no fidelity is reported.
Shots arrive in acquisition order at a fixed scheduled cadence, so the record is
also a uniformly sampled **time series**. The step projects it onto the blob axis
and measures how it hops between blobs (dwell times, rates, autocorrelation), the
same way [modified_ramsey](modified_ramsey.md) treats parity. Optionally it repeats
all of this at each point of a yoko charge-bias sweep. Code: see
`qicklab.experiments.undriven_single_shot` and `qicklab.analysis.undriven`.

## Pulse sequence

One program, `reps = shots`, `rounds = 1`. The qubit channel is never declared.

```
res_ch  ── sync_all ─[ readout tone: length (extended to cover the window) ]── relax_delay ──▶ next shot
ADC     ──────────────────[ window: readout_length ]
                    ^ adc_trig_offset
```

- Channels: `res_ch`, `ro_chs`. No qubit pulse, no trigger pin.
- The readout window, tone length and cross-clock extension are identical to
  [single_shot](single_shot.md#pulse-sequence), so blob positions are directly
  comparable with a g/e calibration.
- **Time axis.** The shot period comes from the *emitted* tProc schedule: the
  `synci` immediates between `LOOP_J` and `loopnz`. It does not come from a wall
  clock. Only `synci` advances tProc time; the `waiti` emitted by
  `measure(wait=True)` does not. A register-based `sync` in the loop would make the
  period non-constant, and the program raises in that case.
- The rep period is roughly `relax_delay + adc_trig_offset + readout_length` plus
  small fixed overheads. It is saved as `scheduled_rep_period_us`.

## How to run

Runs in **regime B**, under the same readout window as [single_shot](single_shot.md).

```python
PLAN = [R.undriven_single_shot(shots=1_000_000, relax_delay=300, average_shots=1,
                               repeat=10)]
# charge sweep: the range must be given here, not in the session charge group
PLAN = [R.undriven_single_shot(charge_sweep=True, voltage_start=0.0,
                               voltage_end=0.05, voltage_step=0.005,
                               charge_settle_s=1.0)]
```

- **Repeat.** `Repeat` (`repeat`) runs the whole acquisition that many times back to
  back.
  - Each pass is an independent experiment with its own timestamped h5/png/json, so
    nothing is overwritten and passes can be concatenated offline.
  - Each pass gets a fresh copy of the config, because the program mutates `reps`,
    `rounds` and `length` in place.
  - Only the **last** pass is shown on screen (`plotDisp` blocks until the window is
    closed). The png is written for every pass.
  - The run returns the list of per-pass data dicts, so every pass's float64 payload
    (~72 MB per read per bias per 1e6 shots) stays in RAM until the run ends: memory
    grows linearly with `Repeat` (see the Parameters table).
- **Charge sweep.** Ramps the yoko through `np.arange(voltage_start, voltage_end,
  voltage_step)`, so the range is half-open and `voltage_end` is not measured. It
  waits `charge_settle_s` after each ramp and acquires at each bias, then **returns
  to the starting voltage** in a `finally` block (also on error or Ctrl-C).
  - An error or Ctrl-C after at least one bias first saves the completed biases (h5 +
    json, no png), then re-raises. The file is marked with `sweep_completed` (number of
    biases kept) and the cfg also gets `aborted` (the error's repr). See Outputs.
  - It needs a yoko.
  - It rejects a zero step, an empty range and any |V| > 10 V before moving the bias
    (`ramp_to` itself rejects |target| > 10 V only when it reaches that point).
  - The range must come from the step's own parameters. The regime-B config is
    rebuilt from scratch and does not carry the session's charge range (see
    [config regimes](../concepts/config_regimes.md#what-changes-at-the-switch-a---b)).

## Parameters

Legacy `US_params` keys (renamed in cfg as shown). Defaults are the CSTQ03 runner
values.

| Key | Default | Units | Meaning |
|---|---|---|---|
| `Shots` → `shots` | 1,000,000 | count | Shots per pass. More than single_shot, because a small secondary blob needs statistics. Required (KeyError if absent). |
| `relax_delay` | 300 | µs | Wait after each readout. Sets the sampling period. Omit it to inherit the single-shot `relax_delay`. |
| `min_separation_sigma` → `blob_min_separation_sigma` | 2.0 | combined σ | Two blobs are only called two if they are this far apart *and* BIC prefers two Gaussians. |
| `average_shots` → `shot_average` | 1 | count | Consecutive shots averaged into one time-series point. 1 = off. Raising it trades time resolution for the sqrt(n) noise reduction that makes a marginal blob split resolvable; the rate-vs-averaging panel of the output plot shows where the useful plateau is. |
| `bin_sizes` → `ts_bin_sizes` | (1, 2, 4, 8, 16, 32, 64) | shots | Averaging levels for the rate-vs-averaging sweep. |
| `charge_sweep` | False | bool | Sweep the yoko charge bias. |
| `voltage_start` / `voltage_end` / `voltage_step` | 0.0 / 0.05 / 0.005 | V | Sweep range, half-open. |
| `charge_settle_s` | 1.0 | s | Extra wait after each ramp (for filtered lines). |
| `Repeat` | 1 | count | Back-to-back passes. Runner-only key. The CSTQ03 runner file still carries the legacy value 10000: at 1e6 shots and a ~300 µs rep period one pass takes ~5 min and writes ~26 MB per read, so 10000 passes is ~35 days and ~0.26 TB. RAM is the tighter limit: the run keeps every pass's float64 data dict in memory until it returns (~72 MB per read per bias per 1e6 shots), so memory grows linearly with `Repeat`. On a 16 GB PC keep `Repeat` × reads × biases × (shots / 1e6) below ~50 (~3.6 GB), e.g. `Repeat` 10-30 with one read at 1e6 shots; run several sessions for a longer record. |
| `plotDisp` | True | bool | Show the last pass on screen. Runner-only key. |

## Outputs

Path `UndrivenSingleShot/`. One h5/png/json per pass.

The h5 is slimmed on write (about 26 MB per 1e6-shot read instead of 128 MB). The
in-memory `data` dict that `display()` reads keeps every key below in float64.

- **Per read tag r:**
  - `i<r>`, `q<r>`, `projection<r>`: the points the blob fit saw. These are raw shots
    when `shot_average = 1`, and averaged points otherwise. With `shot_average = 1`
    they are h5py SoftLinks to `i_raw<r>`, `q_raw<r>`, `projection_raw<r>` (h5py
    follows a SoftLink transparently on read); otherwise float32 datasets.
  - `i_raw<r>`, `q_raw<r>`, `projection_raw<r>`: float32 (about 6e-8 relative
    precision, far below readout noise).
  - Cloud results: `labels`, `projection`, `center`, `cov`, `axis`, `axis_angle`,
    `n_blobs`, `blob_weights`, `blob_means_proj`, `blob_sigmas_proj`,
    `blob_centers_iq`, `separation_sigma`, `secondary_population`, `bic_1`, `bic_2`,
    `rms_radius`, `sigma_along_axis`, `sigma_across_axis` (each suffixed `<r>`), plus
    `*_raw<r>` copies of the main cloud scalars. `labels<r>` is uint8 (0/1).
  - `n_dropped<r>`. The per-read time axes are **not** written to the h5; they
    regenerate from the saved scalars, with N = length of `i_raw<r>`, n = `shot_average`
    and T = `scheduled_rep_period_us`: `shot_index<r>` = arange(N),
    `shot_time_us<r>` = arange(N)·T, `ts_index<r>` = arange(N // n)·n + (n − 1)/2 (block
    centres on the raw shot axis), `ts_time_us<r>` = `ts_index<r>`·T.
  - Time-series results `ts_<key><r>`: threshold, states, transitions, occupancy,
    dwell means, γ01, γ10, mean γ, τ_dwell, samples per dwell, ACF fit, and the
    bin-sweep arrays, and the HMM rates (`ts_hmm_*`, see Analysis step 3). Also
    `ts_acf_fit_ok<r>` and `ts_hmm_identifiable<r>`. `ts_states<r>` is uint8 (0/1).
- **Global:** `read_indices`, `scheduled_rep_period_us`, `shot_average`,
  `timeseries_dt_us`, `gap_indices` (empty).
- **Modified Ramsey aliases** for the first read: `shots_i`, `shots_q` (SoftLinks to
  `i_raw<first>`, `q_raw<first>`), and `shot_index` (uint32), `shot_time_us` (float64),
  the one real copy of the time axis. The record can be fed directly to the
  Modified Ramsey analysis (`fit_two_state_hmm`, `psd_rate_estimate`).
- **Charge sweep:** every per-point key is prefixed `V<k>_`, with the same on-disk
  types and links within each bias. The file adds `sweep_voltages`, summary arrays
  `sweep_<scalar><r>` (n_blobs, separation_sigma, secondary_population,
  sigma_along_axis, gamma_mean_hz, acf_gamma_hz), and the aliases pointing at `V0`
  (`shots_i`, `shots_q`, `shot_index`, `shot_time_us` as SoftLinks).
- **Aborted charge sweep:** the same layout for the first `sweep_completed` biases
  only (`sweep_voltages` has that length), plus a `sweep_completed` dataset; the json
  cfg carries `sweep_completed` and `aborted`. A complete sweep has neither key, so
  check for `sweep_completed` before treating a file as the full range.
- Every program start (single pass and each sweep bias) goes through `acquire_with_retry`
  (3 tries on the [stale-shot-counter race](../concepts/averaging.md#the-stale-shot-counter-race)).
- **png:** the IQ cloud with blob fit, the time series between blobs, and the
  rate-vs-averaging panel; for a sweep, summary scalars vs voltage.
- All fit results are saved to the h5. Nothing lives only in the plot.

## Analysis

1. **Cloud.**
   - Centre = median.
   - Axis = the major principal axis, with its sign fixed so repeated runs project the
     same way.
   - Fit 1- and 2-component Gaussian mixtures to the projection.
   - `n_blobs = 2` only if BIC(2) < BIC(1) **and** the separation ≥
     `blob_min_separation_sigma` (in units of the mean component σ). The secondary
     population is the weight of the minority component.
   - A dead readout (zero spread) is caught before the fit, because sklearn's
     `reg_covar` would otherwise return a plausible-looking fit.
2. **Threshold.** The maximum-likelihood boundary between the two Gaussians. Even
   with equal widths, the ML boundary can lie outside [m0, m1] once the weight ratio
   w0/w1 > e^(sep²/2) (sep in σ).
   Clamping it to the midpoint mislabels the majority tail and inflates the switching
   rate several-fold.
3. **Rates.**
   - Continuous-time Markov ML: γ_ij = (transitions out of i) / (time in i).
   - HMM (`ts_hmm_*`, beside the Markov ML): a two-state HMM (`fit_two_state_hmm`,
     default gates) on the analysed (block-averaged) trace with the two blob Gaussians
     as fixed emissions, fitted on at most 100 000 leading samples (usually 3-8 s; up
     to about a minute if its L-BFGS-B fit fails and the Powell fallback runs).
     Threshold crossings count every misassigned sample as two switches; the HMM does
     not. On blobs 1.0 apart at σ = 0.22 (true 500 Hz each way) the Markov ML reads
     1466/1605 Hz and the HMM 470/516 Hz. Saved: `ts_hmm_gamma01_hz`, `ts_hmm_gamma10_hz`,
     `ts_hmm_gamma01_err_hz`, `ts_hmm_gamma10_err_hz`, `ts_hmm_gamma_mean_hz`,
     `ts_hmm_emission_snr`, `ts_hmm_n_samples`, `ts_hmm_identifiable` (0/1). NaN (and 0)
     unless the cloud has two blobs and the HMM gates pass.
   - Mean dwell: computed from interior runs only, because the first and last runs
     are truncated by the record.
   - ACF: fit `C(t) = A·e^(−t/τc)` with τc = 1/(2γ) and τ_dwell = 1/γ. Lag 0 is
     excluded; it carries the readout-noise variance (`acf_noise_variance`). The ACF
     and the bin sweep run on the un-averaged trace.
4. **Rate-vs-bin-size plateau rule.** Re-threshold the trace after averaging 1, 2, 4,
   … shots.
   - The rate at block size b is n_switches / ((n_bins − 1)·b·dt): n_bins = N//b blocks
     give n_bins − 1 intervals in which a switch can be seen. This is the same estimator
     (`analysis.rates`) that Modified Ramsey uses. Sizes with fewer than 4 blocks give NaN.
   - A rate that **falls** with bin size means the small-bin crossings are readout
     noise.
   - A **plateau** is a real telegraph rate. Set `average_shots` on the plateau.
   - If the curve never flattens, the record has no resolvable telegraph.
   - The run warns when the rate drops by more than 2x across the sweep.
5. Switching statistics are withheld (NaN) unless the cloud resolved two blobs. The
   analog trace and its ACF are always shown.
6. Warnings:
   - fewer than 10 transitions: the rate is unconstrained;
   - shortest dwell < 5 samples: the rate is a **lower bound** (shorten
     `relax_delay`).

Averaging trade-off: averaging n consecutive shots lowers noise by 1/√n, so a
marginal blob split can become resolvable, but it hides switching faster than n
times the rep period.

## Findings & notes

- **Sampling / Nyquist caveat.** Parity dwells are a few ms (expected 2–3 ms on BFC
  devices). At `relax_delay = 3000 µs` the series barely meets Nyquist, so expect rates
  to read as lower bounds. This is why the CSTQ03 default is 300 µs. Check
  `ts_samples_per_dwell` against the 5-sample warning.
- 2026-09-03: the first real charge-sweep run would have failed with `KeyError:
  'voltage_start'`, because the regime-B config does not carry the session charge
  range. The range now has to come through this step's parameters.
- The undriven cloud gives no fidelity. To label blobs as g/e, compare with a
  [single_shot](single_shot.md) calibration taken in the same regime.

## Known issues

- When the two-Gaussian discriminant is negative, `two_gaussian_threshold` falls back
  to the midpoint. That is the fallback its own rationale warns against: it can
  mislabel the majority tail.
- Any exception in the blob fit, including a missing sklearn, is caught. The run then
  reports cloud statistics only and prints one line.
- `shots` has no default. The program raises KeyError if it is missing.
- Requires `rounds = 1` (enforced). Raw shots come from `acc_buf` through the
  raw-buffer helper, because newer qick versions rep-average `di_buf`.
- With `Repeat = 10000` and 10^6 shots per pass, a session spends a very long time in
  this step. Each pass is saved before the next starts.
