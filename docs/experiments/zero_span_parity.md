# zero_span_parity: zero-span two-tone parity switching (ZeroSpanParity)

## What it measures

The readout tone is parked at the cavity frequency and a continuous qubit drive is
parked on **one** parity branch of f01. When the charge parity flips, the qubit moves
on or off resonance with the drive, its steady state changes, the dispersive shift
changes, and the cavity IQ jumps. The step records that IQ trace with no gaps inside a
chunk, classifies it into parity bits, and reports the switching rate vs time,
switching bursts and dwell-time distributions. Its purpose is quasiparticle-tunnelling
rates at baseline and during high-energy impact events, with much better time
resolution than PNA-X zero-span (~ms). Code: see `qicklab.experiments.zero_span_parity`
(programs, `validate_cfg`), `qicklab.analysis.zero_span` and
`qicklab.analysis.zero_span_checks`, and `qicklab.runs.zero_span` /
`qicklab.runs.zero_span_validation`.

## Pulse sequence

Both modes run the same body. Only the const-pulse length differs.

```
strobe (one rep = one sample, reps back-to-back, syncdelay = 0):
qubit_ch  [ const @ parity_drive_freq, qubit_gain : sample_period_us ][ … ][ … ]
res_ch    [ const @ read_pulse_freq,  pulse_gain : sample_period_us ][ … ][ … ]
ADC          ^adc_trig_offset [ read_length ]    [ read_length ]   …

decimated (one capture, raw decimated ADC samples):
qubit_ch  [ const : capture_length_us ]
res_ch    [ const : capture_length_us ]
ADC          ^adc_trig_offset [ ~~~~~~~~ read_length of decimated samples ~~~~~~~~ ]
```

- Channels: `qubit_ch` (no mixer), `res_ch` (with `mixer_freq`), `ro_chs[0]`. No
  trigger pin.
- `start_src` is `"internal"` (free-running) or `"external"` (triggered).
- **Strobe** (v1, "Path A"). Each rep contributes one integrated IQ point. Reps run
  back-to-back with `syncdelay = 0`, so from the qubit's point of view the drive is
  effectively CW, apart from a small inter-rep tProc gap. One sample every ~10–30 µs;
  the record length is unbounded, via chunks.
- **Decimated** (v2, "Path B"). `acquire_decimated()` returns the raw decimated
  waveform of one readout window, for sub-µs resolution inside a burst. `reps = 1`.
  The tones are held for the whole capture.
- `initialize()` ends with `synci(200)` (raw tProc cycles).

## The cfg contract

The cfg is built from scratch by the run. It does not inherit the session config
except for channel routing. Note the key names, which differ from the rest of
qicklab: `read_length` (not `readout_length`) and `read_pulse_freq` (not
`pulse_freq`).

| Key | Mode | Units | Meaning |
|---|---|---|---|
| `mode` | all | – | `"strobe"` or `"decimated"`. |
| `start_src` | all | – | `"internal"` or `"external"`. |
| `res_ch`, `qubit_ch`, `ro_chs`, `nqz`, `qubit_nqz`, `mixer_freq` | all | – | Routing, from the session config. |
| `read_pulse_freq` | all | MHz | Readout tone (device readout frequency). |
| `parity_drive_freq` | all | MHz | Qubit tone: one parity branch. |
| `qubit_gain` | all | DAC | Parity-drive gain. Default = device qubit gain. |
| `pulse_gain` | all | DAC | Readout gain. Default = device readout gain. |
| `res_phase` | all | register | Readout phase (0 by default; ignores any calibrated rotation). |
| `adc_trig_offset` | all | µs | Tone start → ADC trigger. |
| `read_length` | all | µs | ADC window. |
| `sample_period_us` | strobe | µs | Sample cadence = const-pulse length. |
| `reps_per_chunk` | strobe | count | Samples per `acquire()`. Copied into `reps`. |
| `capture_length_us` | decimated | µs | Const-pulse length; must cover the window. |
| `soft_avgs` | decimated | count | Must be 1 unless `allow_soft_avgs`. |
| `n_captures` | decimated, optional | count | Back-to-back captures to stitch (default 1). |
| `allow_soft_avgs` | decimated, optional | bool | Opt-in to averaged (non-time-resolved) captures. |

### The nine validation rules

The rules come from a design spec that has since been deleted from the repository
(recoverable from commit 0f0a51f^). They are restated here. Rules 1–5, 8 and 9 are
checked when `ZeroSpanParity` is constructed. Rules 6 and 7 check orchestrator state
and are enforced by the run before the cfg is built. Errors name the rule, the value
and the bound.

1. Strobe: `sample_period_us ≥ adc_trig_offset + read_length + 1.0 µs`. Otherwise
   reads overlap.
2. Strobe: `us2cycles(sample_period_us)` on both `qubit_ch` and `res_ch` ≤ 65535
   (16-bit const-pulse length).
3. Decimated: the same 65535-cycle cap for `capture_length_us`.
4. Strobe: `reps_per_chunk ≤ soccfg["readouts"][ro_ch]["avg_maxlen"]` (16384 on the
   current board).
5. Decimated: `round(read_length · f_output) ≤ buf_maxlen` (1024 on the current
   board). The original spec wrote this in terms of `capture_length_us`; the code
   checks `read_length`, because the decimated buffer is sized by the declared readout
   length, `us2cycles(read_length, ro_ch)`, the number qick checks against the buffer
   (3.2 µs = 983 samples passes, 3.4 µs = 1044 fails).
6. If `RecalibrateParityFreqs = False`, the cached frequency selected by
   `which_to_park` must be set. The spec required a finite float; the code checks
   only that it is not None.
7. If `RecalibrateSeparator = False` and `classifier_method` uses the separator
   (`"apriori_gmm"`, `"apriori_midpoint"` or the legacy `"apriori"`), all four
   cached separator fields (`g_center`, `e_center`, `normal`, `midpoint`) must be
   arrays of shape (2,). Lists are coerced.
8. `parity_drive_freq` must lie in the qubit generator's DDS band `[−f_dds/2,
   +f_dds/2]`, which is QICK's `freq2reg` valid range, **not** `[0, f_dds]`. The rule
   is skipped if the soccfg has no `f_dds`.
9. Decimated: `capture_length_us ≥ adc_trig_offset + read_length`. Otherwise the pulse
   ends before the readout window closes.

The decimated acquisition additionally requires `n_captures ≥ 1`, and `soft_avgs > 1`
only with `allow_soft_avgs = True`: averaging independent captures destroys the parity
trajectories. `set_qubit_gain` (used by the validation harness) is strobe-only.

## How to run

Runs after the regime-B switch. The g/e separator calibration uses the single-shot
window.

```python
PLAN = [R.zero_span_parity(mode="strobe", sample_period_us=20.0,
                           reps_per_chunk=10_000, n_chunks=60,
                           read_length=5.0, adc_trig_offset=0.488)]
```

The run, in order:

1. **Parity frequencies.** With `RecalibrateParityFreqs`, take a narrow
   `QubitSpecSliceFF` around the qubit centre (path `ZeroSpanParity_Spec`). Pick the
   lower and higher peaks with `pick_parity_drive_freq` (selection rules:
   [two_tone_spec](two_tone_spec.md#analysis), step 4, with the spec `min_sep_MHz`) and
   park on `which_to_park`. If the selection does not return two frequencies at least
   `min_sep_MHz` apart (a single line, or a doublet split below `min_sep_MHz`: outcome
   `single_line_unresolved`), or if the weaker of the two lines is less than
   `min_partner_snr` (default 5, `MIN_PARTNER_SNR`) times the per-point noise above the
   off-resonant (span-edge) baseline (outcome `partner_not_significant`: the partner is
   taken to be a noise maximum), the run raises RuntimeError before the separator
   calibration rather than park on a blended centre or on noise. The message says which:
   for `partner_not_significant`, average more (`reps`/`rounds`) or raise the spec gain,
   widen `SpecSpan` if the second line may lie outside it, or use cached frequencies.
   The significance gate closes the low-SNR hole of the separation test: on the ZSP grid
   a single line (HWHM 40-200 kHz) and a doublet split below `min_sep_MHz` (before the
   gate a doublet in 70.5-99 % of trials at SNR 6 and up to 54.5 % at SNR 10) and a
   noise-only trace (before: a doublet in 98.5-100 % of trials) were stopped in all but 5
   of 6000 trials (SNR 6-20, 200 per case; the 5 were 200 kHz HWHM single lines at SNR
   6-8, paired with a noise maximum on the line's own shoulder), while equal-height
   doublets split 0.3-0.6 MHz are accepted in 99-100 % of trials at SNR 10 and above
   (98-99.5 % at SNR 8 for 40 kHz HWHM lines, 89.5-100 % for 100 kHz, 94.5 % for 200 kHz;
   about 53-73 % at SNR 6). A doublet whose weaker line has an SNR below about 8, or whose
   lines are so broad that their wings fill the span edges (a 300 kHz HWHM doublet split
   by 1.0 MHz on the 2 MHz span: 64.5 % at SNR 10, 100 % at 15), therefore often stops
   the run. Operating curve: [two_tone_spec](two_tone_spec.md#analysis) step 4.
   Setting `ZSP_ParitySpec_params["min_partner_snr"] = 0` switches the gate off
   (separation test only). The selection path, splitting and significance are saved in
   the ZSP cfg (json and h5 `config`) as `parity_freq_source` (the step-4 source, or
   `cached`), `parity_peak_sep_MHz` (`None` for a cache missing either peak) and
   `parity_partner_snr` (the weaker line's height over the per-point noise; `None` on
   the cached path). Otherwise use the cache (rule 6).
2. **Separator.** With `RecalibrateSeparator`, run a SingleShot g/e calibration.
   Otherwise validate the cache (rule 7). Both caches live on disk as
   `<data_root>/Q{q}/zsp_cache.json`.
3. Build the cfg and **acquire**:
   - **Strobe, `n_chunks > 1`:** `chunked_acquire` stitches the `acquire()` calls,
     makes `t_us` monotonic and marks chunk boundaries in `gap_indices`. Gaps between
     chunks are not modelled in `t_us`; analysis never counts a switch across a gap.
     Each inner `acquire()` leaves only its own chunk in `experiment.data`, so
     `chunked_acquire` replaces `experiment.data` with the stitched record. A plain
     `save_data()` afterwards therefore saves the whole record.
   - **Decimated:** `n_captures` captures are stitched with `gap_indices`.
4. **Analysis.** `analyze_parity_run` writes its sidecars into the same run folder as
   the raw h5.
5. **Validation stages**, strobe only (see below).

**Record length (strobe)** = `reps_per_chunk · n_chunks · sample_period_us`. With the
defaults that is 10000 × 60 × 20 µs ≈ 12 s.

## Parameters

CSTQ03 runner values (legacy `ZSP_*` dicts).

| Key | Default | Units | Meaning |
|---|---|---|---|
| `ZSP_RunMode` → `mode` | "strobe" | – | Acquisition path. |
| `ZSP_StartSrc` → `start_src` | "internal" | – | Trigger source. |
| `ZSP_RecalibrateParityFreqs` | True | bool | Run the narrow spectroscopy first. |
| `ZSP_RecalibrateSeparator` | True | bool | Run the SingleShot calibration first. |
| `which_to_park` | "lower" | – | Parity branch to drive. |
| Strobe `sample_period_us` | 20.0 | µs | Sample period. Floor = offset + window + 1 µs. |
| Strobe `reps_per_chunk` | 10000 | count | ≤ avg_maxlen. |
| Strobe `n_chunks` | 60 | count | Chunks to stitch. |
| Strobe `read_length` | 5.0 | µs | ADC window. |
| Strobe `adc_trig_offset` | 0.488 | µs | ADC offset. |
| Decimated `capture_length_us` | 100.0 | µs | Tone length per capture. |
| Decimated `soft_avgs` | 1 | count | Must stay 1. |
| Decimated `n_captures` | 1 | count | Captures to stitch. |
| Decimated `read_length` | 80.0 | µs | ADC window. Fails rule 5 on the current board (see Known issues). |
| Decimated `adc_trig_offset` | 0.488 | µs | ADC offset. |
| Decimated `allow_soft_avgs` | False | bool | Opt-in to averaging. |
| `qubit_gain` / `pulse_gain` | None (→ device gains) | DAC | Drive gains. |
| `res_phase` | 0 | register | Readout phase. |
| Spec `SpecSpan` / `SpecNumPoints` | 1.0 / 201 | MHz / count | Narrow parity spectroscopy. |
| Spec `reps` / `rounds` / `relax_delay` | 10 / 10 / 3500 | count / count / µs | Its averaging. |
| Spec `Gauss` / `sigma` / `gain` / `qubit_length` | True / 2 / 500 / 2 | – / µs / DAC / µs | Its drive. |
| Spec `min_sep_MHz` / `fit_window_mhz` / `prominent_ratio` | 0.2 / 0.5 / 0.1 | MHz / MHz / – | Peak picking. |
| Spec `min_partner_snr` (optional) | 5 (`MIN_PARTNER_SNR`) | noise sigma | Significance the weaker parity line needs (step 1); 0 switches the gate off. |
| `classifier_method` | "apriori_gmm" | – | `"apriori_gmm"` (separator axis, threshold from the data), `"apriori_midpoint"` (separator axis, threshold at the g/e midpoint; not for driven data) or `"kmeans"`. The legacy `"apriori"` means `"apriori_gmm"`. See [Analysis](#analysis) step 2. |
| `window_us` | 1000.0 | µs | Sliding window for the switch rate. |
| `k_sigma` | 5.0 | σ | Burst threshold. |
| `step_us` | None (→ window_us // 2) | µs | Window stride. |
| `min_burst_duration_us` | None | µs | Drop shorter bursts. |
| `analysis_bin_us` | None | µs | Mean-bin before classifying. Set it < `read_length` for decimated + apriori. |
| `save_plots` | True | bool | Write the analysis PNGs. |

Validation-stage parameters:

| Key | Default | Meaning |
|---|---|---|
| `StaticContrast.freq_span_mhz` / `n_points` / `reps_per_point` | 2.0 / 41 / 2000 | Stage 1 probe-frequency sweep. |
| `ContrastVsQubit.qfreq_span_mhz` / `n_points` | 10.0 / 81 | Stage 2 drive-frequency sweep. |
| `Modulation.modulation_freq_hz` / `n_periods` | 25 / 10 | Stage 3 square wave (40 ms period). |
| `Control.variants` / `detune_mhz` | A, B, C, D / 50.0 | Stage 8. |
| `Environment.param_name` / `values` | "power_dB" / [−10, −8, −6, −4] | Stage 7 (see Known issues). |

## Outputs

- **Raw**, path `ZeroSpanParity/` (under `<outer>/ZeroSpanParity/`). The h5 is opened
  in append mode, so the config attribute survives, and datasets are deleted and
  recreated, so re-saving is idempotent.
  - Datasets: `I`, `Q`, `t_us`, `gap_indices`; plus `capture_sizes` and
    `chunk_wall_clock_starts` when present.
  - Attributes: `wall_clock_start`, `sample_period_us`, `mode`, `decimated_fs_MHz`,
    `decimated_fs_source` (`"soccfg.f_output_unverified"`), `read_length_us`,
    `capture_length_us`, `adc_trig_offset_us`, `ro_norm_cycles`,
    `samples_per_capture` (actual first-capture length, not total/n_captures),
    `n_chunks`, `n_captures`, `soft_avgs`.
  - json: the cfg. No png from the experiment itself.
- **Analysis**, in the same run folder:
  - `<base>_analysis.json`: summary, bursts, window, step.
  - `<base>_analysis.h5`: `binary_states`, `scores`, `window_t_us`, `rate_Hz`,
    `dwell_0_us`, `dwell_1_us`, summary attrs.
  - `<base>_iq_scatter.png`, `_parity_vs_time.png`, `_switch_rate_vs_time.png`,
    `_dwell_histograms.png`.
  - Summary fields: `baseline_rate_Hz`, `baseline_rate_err_Hz`, `n_switches_baseline`,
    `T_baseline_s`, `median_window_rate_Hz`, `n_bursts`, `mean_dwell_0/1_us`,
    `n_runs_0/1`, `exp_fit_tau_0/1_us`, `raw_sample_period_us`,
    `n_raw/binned_samples`, `analysis_bin_us`, `mode`, `classifier_method`,
    `classifier_threshold` (score units), `bits_withheld`, `classifier_warning`, and the
    `apriori_gmm` score-histogram fit: `classifier_separation_snr`, `classifier_delta_bic`,
    `classifier_centers`, `classifier_sigmas`, `classifier_weights` (lower component first,
    score units; NaN for `apriori_midpoint` and `kmeans`). The fit is reported even when
    it fails the gate and the bits are withheld.
  - When the bits are withheld (`bits_withheld` True, see [Analysis](#analysis) step 2),
    every rate, burst and dwell field is NaN, `binary_states` is empty, and only
    `_iq_scatter.png` (uncoloured) is drawn.
- **Validation:** per-stage JSON sidecars plus raw arrays (stitched IQ, references,
  `freqs`, `Z_on`/`Z_off`), each tagged with an `analysis_version`, and `EVIDENCE.md`
  from stage 9.

## Analysis

1. **Normalisation units (strobe).** I and Q are divided by
   `us2cycles(read_length, ro_ch=0)` to match the SingleShot separator. The SingleShot
   `collect_shots` normalisation is the reference, so `ro_ch=0` is used deliberately,
   not `ro_chs[0]`. `di_buf`/`dq_buf` are indexed by readout **declaration order**
   (position 0), while `soccfg["readouts"][ch]` is keyed by absolute channel.
2. **Classify** (`classify_parity_trace`). The separator methods project each sample
   onto the SingleShot g → e axis about the g/e midpoint, score = (iq − (g + e)/2)·(e − g)
   (g at −|e−g|²/2, e at +|e−g|²/2); they differ only in where they put the threshold.
   - `apriori_gmm` (default; the legacy name `apriori` means this): the separator is
     only the projection axis. A two-component Gaussian mixture is fitted to the scores
     (`projected_histogram_snr`) and the threshold is the maximum-likelihood boundary of
     the two components (`two_gaussian_threshold`, weights and widths included,
     `classifier_threshold` in the summary). If the score histogram fails the bimodality
     gate of step 6, the bits are **withheld**: rates, bursts and dwells are NaN and
     `classifier_warning` says why. Nothing is thresholded at a guessed level.
   - Why not the midpoint: under the CW parity drive the off-resonant parity sits at
     ≈ g and the driven one at g + p_e·(e − g), with p_e ≤ 1/2 for a driven two-level
     qubit (less with readout dephasing). The driven level is therefore at or below
     the g/e midpoint, and a midpoint threshold follows the qubit's noise, not the
     parity. On a synthetic telegraph (500 Hz per state, 20 µs samples, |e−g| = 1,
     σ = 0.1) the midpoint classifies 75 % of samples correctly at p_e = 0.5 with a
     ~25× too high switch rate, and 53 % (chance) at p_e = 0.35; the GMM threshold
     classifies 99.4 % and 96 % (the latter SNR-limited, as KMeans). The separator also
     comes from a pulsed SingleShot window, not the CW steady state. Until 2026-10 the
     midpoint was the default (`apriori`); it remains as `apriori_midpoint` and is used
     only where nothing is thresholded (stage-3 and stage-8 levels).
   - The threshold is now in the right place, but the switch rate is still inflated by
     noise crossings: every sample that noise pushes across the threshold counts as two
     switches, and no threshold avoids that. On the same synthetic telegraph the
     unbinned sliding-window rate is ~2.2× the true rate at p_e = 0.5 (the parity
     levels 5 σ apart) and ~8.5× at p_e = 0.35 (3.5 σ apart). Trust the rates only when
     the levels are well separated (`classifier_separation_snr` in the summary ≳ 5 per
     sample, i.e. per-sample errors ≲ 1 %). Otherwise mean-bin with `analysis_bin_us` to a bin still well below
     the dwell time: binning the p_e = 0.35 trace to 80 µs (4 samples, 7 σ) brings the
     rate to within 5 % of the truth.
   - This is still a two-level threshold on the averaged level, and the bimodality gate
     does not catch every failure. If the qubit jumps are resolved within a sample
     (the driven branch sits at g or at e from sample to sample, not at the average
     g + p_e·(e − g)), the score histogram has two clean lobes **at the SingleShot g and
     e**. It passes the gate, and the bits follow the qubit jumps: the F07 failure
     again. Synthetic check: driven samples at e with probability 0.4 give GMM centers at
     exactly g and e, 70 % accuracy and a ~24× too high switch rate, with no warning.
     The signature is the upper GMM center at or above the g/e midpoint
     (`classifier_centers[1]` ≥ 0 in the summary, the e score being +|e−g|²/2; the
     threshold lies below the upper center, so `classifier_threshold` ≥ 0 is a stronger,
     sufficient form), or the state-1 cloud on the separator's e marker in
     `_iq_scatter.png`. An averaged driven level with p_e ≤ 1/2 cannot be there. Treat
     it as a diagnostic, not a test: the separator is pulsed SingleShot data (and in
     records before 2026-10-15 the `declare_readout` normalisation mismatch also
     rescaled it relative to the zero-span I/Q by about 1.4), so the absolute g/e
     positions are only approximate. No single
     threshold separates the parities in this regime (a hidden-Markov model would; not
     implemented). A three-lobe or skewed histogram (partly resolved jumps) is the same
     regime.
   - `kmeans`: two clusters. Label 0 is the lower projection on the inter-centroid
     axis, with the sign canonicalised to the dominant positive component.
   - Optionally mean-bin first (`analysis_bin_us`). Never auto-bin by `read_length`:
     a decimated capture covers exactly one `read_length`, so that would collapse it
     to one point. Pass a fraction of it.
   - Per-sample SNR in decimated mode is much lower than in strobe mode.
3. **Sliding-window rate.** Switches are counted in windows of `window_us` with stride
   `step_us` (default 50 % overlap). Windows are half-open; the last one is closed.
   No switch is counted across a `gap_indices` boundary.
4. **Bursts.**
   - threshold = baseline + `k_sigma`·σ, baseline = event-based switch rate (see
     [Baseline switch rate](#baseline-switch-rate)).
   - σ = max(1.4826·MAD about the median, Poisson floor). The Poisson floor is
     q·√max(baseline_counts, 1), with q = 1/(window_us·1e-6), the rate of one switch
     per window.
   - The floor exists because more than 50 % of windows hold zero switches, so the MAD
     is 0.
5. **Dwell times.**
   - Run lengths per state, split at gaps. The last run of each segment is
     extrapolated by one sample period.
   - Exponential fit to the histogram by log-linear regression **weighted by
     √count**. Unweighted OLS overweights sparse tail bins and biases τ about 10 %
     high, which failed the ±5 % acceptance criterion.
   - Optional debouncing (`min_dwell_bins`) for the threshold-stability check.
6. **Bimodality** (`projected_histogram_snr`): bimodal requires ΔBIC > 0 **and**
   separation SNR > 1.5 **and** both weights in (0.1, 0.9).

### Baseline switch rate

`baseline_rate_Hz` is the quiet-time parity switching rate, computed from the switch
events themselves (`baseline_rate_and_bursts`, `event_switch_rate`), not from the
sliding windows:

- **Events and exposure.** n is the number of 0↔1 transitions between consecutive
  (post-binning) samples; T is the sum of the sample intervals, with every interval
  that spans a `gap_indices` boundary dropped from both. No uniform spacing is
  assumed across gaps. The rate is n / T.
- **Burst exclusion, iterated.** A provisional rate (all switches / all of T) sets
  the burst threshold. The intervals inside each flagged burst are then removed from
  both n and T, the rate is recomputed, and the bursts are re-detected against it;
  because the lower rate lets more bursts cross the threshold, the exclusion is
  repeated until no new span is flagged (at most `MAX_BURST_PASSES` = 5 passes), so
  every reported burst is excluded from the baseline. If the bursts cover the whole
  record, the provisional rate is kept. The excluded
  span is the full extent of the flagged windows, `[t_start_us − pad, t_end_us +
  pad]` with pad = (`window_us` − stride)/2 (250 µs at the default 1000 µs window
  and 50 % overlap): the reported `[t_start_us, t_end_us]` is only stride/2 wide at
  each end, so masking just that would let a burst's edge switches leak into the
  baseline and bias it upward when bursts are frequent. Over-masking is unbiased,
  since quiet switches and quiet time are removed together. Bursts too dim to cross
  the threshold are not excluded and count toward the baseline.
- **Uncertainty.** `baseline_rate_err_Hz` = √n / T, the Gaussian (large-n)
  approximation to the Poisson standard error. It is good for n ≳ 10 switches but
  is not a valid interval for n of order 0–10: it reads 0 at n = 0, where the
  one-sided 68 % upper limit is −ln(0.32) / T ≈ 1.14 / T. For sparse records, build
  an exact Poisson interval from `n_switches_baseline` and `T_baseline_s` (n and T).
  With fewer than two samples, T = 0 and the rate and its error are NaN.
- **Why not the median window rate.** Each window holds an integer number of
  switches, so its median is 0 Hz below about 0.7 switches per window (≈ 700 Hz at
  `window_us` = 1000; ln 2 for Poisson counts) and a multiple of 1/`window_us` above
  it, with no error bar. With the expected 2–3 ms dwells (~400 Hz) it read 0 Hz. The
  median is still reported as `median_window_rate_Hz`, and it remains the
  centre of the MAD and the default of `detect_bursts` when no baseline is passed.
- **Burst threshold.** The Poisson floor q·√max(baseline_counts, 1) takes the
  non-integer baseline_counts = baseline / q as is: below one switch per window
  the floor stays at q.

### The 9-stage validation chain

Before trusting a natural parity telegraph, the signal must be shown to be
parity-dependent, time-resolved, and not drift, noise or drive artifact. The harness
is strobe-only (decimated timing is unverified) and collates evidence; it gives **no
automatic pass/fail**.

| Stage | Name | What | Status |
|---|---|---|---|
| 1 | Static contrast | Drive parked on one branch; sweep the probe frequency; maximise \|Z_on − Z_off\| | `run_static_contrast` |
| 2 | Contrast vs qubit frequency | Sweep the drive frequency at the stage-1 probe; see the two branches | `run_contrast_vs_qubit_freq` |
| 3 | Artificial modulation | Square-wave the drive gain (~25 Hz) by software block alternation; recover it from the IQ trace. **Pipeline-sanity gate**: do not proceed if not recovered | `run_modulation_check` |
| 4 | Two-level telegraph | Continuous record, projected histogram should be bimodal | **not implemented** (`projected_histogram_snr` exists) |
| 5 | Bin-size dependence | Reprocess at t_bin ∈ {0.1, 0.2, 0.5, 1.0} ms; levels separate better until t_bin approaches T_parity (~2–3 ms) | **not implemented** (`bin_size_sweep` exists, unused) |
| 6 | Dwell times | Exponential dwell distributions, stable vs threshold | **not implemented** (`threshold_stability` exists, unused) |
| 7 | Environment | Rate vs power, detuning, drive-off; temperature logged by hand | `run_environment_sweep` |
| 8 | Instrument controls | A drive off, B drive far detuned → level stays at the drive-off reference (`null_ok`); C probe off-resonance → contrast vanishes; D drive each branch in turn → both raise the level (`both_branches_respond`), branch ratio, complementarity, midpoint null; nulls and responses tested with batch-means errors against a Student-t critical value ([below](#stage-8-instrument-controls)) | `run_control_suite` |
| 9 | Evidence report | Collate stages 1–8 into EVIDENCE.md (scalar tables; stage 8 also a variant/metric table) | `build_evidence_report` |

- **Run order:** stage 1 → stage 2 → stage 1 again (refine) → stage 3 (gate) →
  stage 4 → stages 5/6 → stage 8 → stage 7 → stage 9. Optimise the probe (stage 1)
  before sweeping the qubit frequency: a bad probe point can miss the branches.
- Stage 1 does not use the g/e separator. It compares averaged complex responses
  with the drive on and off. Before calling stage 1, the run sets both
  `reps_per_chunk` and `reps` to `reps_per_point`, because the strobe program is
  rebuilt from `cfg["reps"]`.
- Stage 2 has no telegraph at a driven steady state. It uses the complex-response
  difference against the drive-off baseline, `|⟨Z⟩_on − ⟨Z⟩_off|`, not histogram
  bimodality.
- Readout power changes both the SNR and the real parity dynamics. Stage 7 therefore
  records `switch_rate`, `separation_snr`, `mean_dwell` and `mean_signal_level` for
  every setting. The bits behind `switch_rate` and `mean_dwell` come from the
  `apriori_gmm` threshold; at a setting whose score histogram is not bimodal (e.g.
  drive off) both are NaN. Before 2026-10 they used the g/e midpoint and read the
  qubit noise of the driven branch as switches. Where `separation_snr` is below ~5,
  `switch_rate` is still inflated by noise crossings (Analysis step 2).
- Z_on and Z_off are proportional to S21; they are not calibrated.
- Stage-5 interpretation: the best bin may come before T_parity. A low `tau_cv`
  across thresholds indicates a robust telegraph.
- `reps_per_block` must satisfy avg_maxlen (16384).

### Stage-3 modulation timing

- **Block length.** `run_modulation_check` sets `reps_per_block` = round(1 / (2 ·
  `modulation_freq_hz` · `sample_period_us`)), at least 1. `modulated_strobe_acquire`
  compiles every block program with that many reps (it sets `reps_per_chunk` and `reps`
  for the blocks), then restores the previous `reps_per_chunk`/`reps` and rebuilds
  the program at the last gain of the schedule (0). Before this fix the blocks were
  compiled with `reps_per_chunk` (2000 after stage 1, 10000 without it). Each
  half-period then held 2–10× the requested samples, and the true square wave ran at
  12.5 or 2.5 Hz where 25 Hz was reported.
- **Gain restore.** `run_modulation_check` then restores the drive gain and rebuilds
  the program (also on an exception). Before 2026-10 it did not, so stages 8 and 7,
  which run after stage 3, ran with the drive off.
- **Frequencies saved.** The sidecar scalars hold both values:
  - `nominal_modulation_freq_hz`: the requested frequency after rounding to whole reps
    (also `modulation_freq_hz` in the sidecar metadata);
  - `injected_freq_hz`: the value measured from the on/off reference.
    `verify_modulation` counts transitions + 1 half-periods over the n samples
    (n · dt), so it equals the nominal value when every block holds `reps_per_block`
    samples. A mismatch means the blocks had a different length.
- **Dead time.** Both values are in stitched sample time. The stitched `t_us` leaves
  out the dead time between block programs (Python rebuild, load and start of every
  block). In wall-clock time the square wave is therefore slower and
  uneven. `chunk_wall_clock_starts` holds the block start times.

### Stage-8 instrument controls

`run_control_suite` takes one record per setting and projects it on the separator
(score > 0 = bright, e). Every variant rebuilds the program (`set_qubit_gain`) after
its cfg change, and the base point is rebuilt at the end, also when an acquisition
raises. A drive-off record is the reference. The per-variant results are in the
sidecar's `variants`; EVIDENCE.md renders them as a `variant | metric | value` table.

- **Record length.** One acquisition holds `reps_per_chunk` samples (at most
  `avg_maxlen`). After stage 1 that is `reps_per_point`, e.g. 2000 × 20 µs = 40 ms.
  Each control record therefore stitches ⌈`min_record_us` / (`reps_per_chunk` ×
  `sample_period_us`)⌉ acquisitions of the same program, with `min_record_us` = 200 ms
  by default. The stitched time omits the dead time between acquisitions. The sidecar
  holds `blocks_per_record` and `record_us`. To lengthen the records, pass a larger
  `min_record_us`; changing the ZSP `reps_per_chunk` has no effect, because stage 1
  overwrites it.
- **Error bars.** A parity telegraph is correlated over its dwell (~2–3 ms), so
  std/√N of the samples is far too small. Every mean has a batch-means standard
  error: consecutive batches of `se_batch_us` = 10 ms, se = std(batch means)/√n_b,
  with n_b − 1 degrees of freedom. A shift from the reference is delta = level −
  off_level, se = √(se² + se_off²), z = delta/se. The two records are independent, so
  z has a Student-t distribution with the Welch–Satterthwaite dof (`delta_*_dof`). It is
  compared with `t_crit`, the t value that has the same tail probability as a normal
  `k_sigma` = 3. With 4 batches per record (dof 3–6), comparing z with 3 would give a
  null false-alarm rate of ~2 % instead of 0.27 %. At 200 ms (20 batches, dof ≈ 38),
  t_crit ≈ 3.2.
- **Undetermined.** If a record holds fewer than `min_batches` = 4 batches, the se is
  NaN. `null_ok` / `both_branches_respond` are then **None** (not False) and
  `insufficient_batches` is True, so a short record is not read as a null violation.
- **A (drive off), B (drive detuned by `detune_mhz`).** Nulls: `delta`, `delta_se`,
  `delta_z`, `delta_dof`, `t_crit`, `null_ok` = |z| < t_crit.
- **C (probe off-resonance).** `mean_level` and `separation_snr` only: moving the probe
  moves both clouds, so the drive-off reference at the probe point does not apply.
- **D (both branches).** The drive goes to the lower peak, the higher peak and their
  midpoint (from `parity_freqs`, the cached peaks). Driving a peak excites only the
  samples in the parity whose transition that peak is. Which parity has the lower
  peak depends on the offset charge (the branches cross at n_g = 0.25 mod 0.5), so
  write P_lower for the occupation of the lower-peak parity. **Both** shifts are
  positive (toward e): delta_lower = P_lower·p_e,lower·|e−g| and delta_higher =
  P_higher·p_e,higher·|e−g| (projected). Reported:
  - `both_branches_respond`: z_lower > t_crit_lower and z_higher > t_crit_higher
    (one-sided);
  - `branch_ratio` = delta_lower/delta_higher ± `branch_ratio_se` (the shared
    reference is included), expected P_lower·p_e,lower / (P_higher·p_e,higher);
  - `complementarity` = (delta_lower + delta_higher)/(`pe_drive`·|e−g|) ±
    `complementarity_se`, with `complementarity_z` = (complementarity − 1)/se. Here
    |e−g| is the projected separator distance (`e_minus_g` in the sidecar, i.e.
    |e_center − g_center|²). P_lower + P_higher = 1, so the value is ~1 when both
    branches are driven to the same excited population `pe_drive` (0.5 assumed) and
    the separator is exact. This is a secondary, model-dependent check: it depends on
    the assumed `pe_drive` and on the separator scale, and says nothing about P_lower,
    which is near 0.5 for a symmetric telegraph. Biases:
    - **below 1:** a weaker (unsaturated) drive. Thermal excited population p_th is
      present with the drive off too, so each shift is P_branch·(p_e − p_th)·|e−g| and
      the value is ≈ 1 − p_th/`pe_drive`. e decay during the ZSP readout lowers it
      further only beyond the decay already in the calibration (next point);
    - **above 1:** `e_minus_g` comes from the SingleShot π-pulse calibration
      (`get_apriori_separator_from_singleshot`), whose centres are plain means.
      e_center is pulled toward g by π infidelity and by T1 decay during the readout,
      g_center toward e by thermal population, so |e−g| is too small and the value
      too large by ≈ 1/(1 − ε_π − ε_T1 − p_th). Any scale mismatch between the ZSP
      readout and the SingleShot separator enters as the same factor (before 2026-10-15
      the `declare_readout` bug made it about 1.4, see
      [readout window](../concepts/readout_window.md#history));
    - a value clearly above 1 therefore points to a separator or `pe_drive`
      miscalibration, not to the parity physics.

    It uses mean levels, which stay linear in p_e when a sample is a time average over
    the near-CW drive rather than a projective outcome; a thresholded bright fraction
    would not;
  - the midpoint null `delta_midpoint`, `delta_midpoint_z`, `t_crit_midpoint`,
    `midpoint_null_ok`. It fails when the doublet splitting is not large compared with
    the (power-broadened) drive linewidth, i.e. the two branches are not resolved at
    this gain.
- **Skips.** A variant whose frequencies are unset (None) is recorded as
  `{"skipped": reason}` instead of driving at 0 + `detune_mhz` or raising.
- **History (before 2026-10).** Variant D was `swap_branch`, with
  `sign_lower`/`sign_higher` and `branch_sign_flip` = sign(lvl_lower − off) ≠
  sign(lvl_higher − off). By the argument above it is False for a genuine parity
  signal, so it was not evidence. It was dropped and the outputs renamed. Other
  problems fixed at the same time:
  - variants C and D changed `read_pulse_freq` / `parity_drive_freq` without
    rebuilding, so C ran with B's detuned program and D measured the lower branch
    twice;
  - each control was a single 40 ms acquisition with no error bar;
  - the cfg helper wrote None into absent keys, and None parity frequencies raised
    TypeError.

  An 8_control_suite sidecar with a `swap_branch` variant predates these fixes.

## Findings & notes

- Loopback on the RFSoC, 2026-05-16, all four checks passed. Bugs found then:
  - `"gens" in soccfg` raised, because `QickConfig` has `__getitem__` but no
    `__contains__`;
  - `soft_avgs` was passed twice to `acquire_decimated`. AveragerProgram already
    injects it; do not pass it.
- Spec audit, 2026-05-29: the rule-8 band was `[0, f_dds]` and should have been
  `[−f_dds/2, +f_dds/2]`; strobe `di_buf` was indexed by absolute channel instead of
  declaration order; `chunked_acquire` produced a non-monotonic `t_us` for 1-sample
  chunks; the KMeans label remap used I instead of the e−g projection. All fixed.
- **Decimated time axis is unverified.** `soccfg["readouts"][ro]["f_output"]` is
  307.2 MHz on this firmware. The loopback observed samples coming back at about the
  tProc clock (~430 MHz) instead. `t_us` uses the nominal rate, so
  `read_length_us`, `capture_length_us`, `samples_per_capture` and
  `decimated_fs_source` are saved for post-hoc reconstruction. The likely cause was the
  `declare_readout` bug fixed on 2026-10-15: the window was declared as a tProc-cycle
  count, which qick reads as readout samples, so the buffer held about 1.4x more samples
  than planned at the correct 307.2 MHz. `decimated_fs_source` stays
  `"soccfg.f_output_unverified"` until a loopback confirms `samples_per_capture` =
  `read_length` x 307.2.
- The decimated buffer is small: buf_maxlen = 1024 samples, so about 2.4 µs per capture
  at 430 MHz (3.3 µs at 307.2 MHz). Path B is much more constrained than the original
  ms-record assumption.
- `acquire_decimated` returns `(2, length)` per channel for reps = 1 (I/Q axis
  leading), `(reps, 2, length)` for reps > 1, and `(length, 2)` on some paths. All
  three are handled.
- `set_qubit_gain` re-syncs `reps` from `reps_per_chunk` before rebuilding the
  program. AveragerProgram reads `cfg["reps"]` at construction, so a post-construction
  change to `reps_per_chunk` would otherwise be ignored.
- No physics validation on a cold device (CSTQ03) is recorded in the code or the
  audit. The original plan was to run stages 1–4 first after characterisation.

## Known issues

- **Records before 2026-10-15** were taken with `declare_readout` given a tProc-cycle
  count (no `ro_ch`), which qick 0.2.334 reads as decimated samples: the window and the
  decimated record were f_time/f_output (about 1.4×) longer than `read_length`, the
  strobe I/Q were 1.4× too large relative to the SingleShot separator, and rule 5
  counted the wrong number of samples
  ([readout window](../concepts/readout_window.md#history)).
- The decimated defaults (`read_length = 80 µs`) give ≈ 24576 samples at 307.2 MHz,
  far above buf_maxlen = 1024. Rule 5 rejects them on the current board.
- A `rounds` key in the cfg would override `soft_avgs` inside AveragerProgram,
  bypassing the soft-average gate (decimated) and keeping only the last round
  (strobe). The run does not set `rounds` today.
- The strobe rep period is max(`us2cycles(sample_period_us)`, ADC trigger offset +
  readout window), so with rule 1 satisfied the tones set it and `t_us = index ·
  sample_period_us` is exact for the default cfg (to under one tProc cycle where the
  generator and tProc clocks differ). The rule-1 +1.0 µs margin is purely conservative.
  Before 2026-10-15 the 1.4× window could set the period instead (10 µs window, 11.5 µs
  period: 14.50 µs per rep, +26 % on every rate and dwell). The program now raises at
  construction if the compiled period differs from `us2cycles(sample_period_us)` by more
  than one tProc cycle.
- `res_phase` defaults to 0 and ignores any calibrated rotation.
- `current_voltage` is taken from the session start voltage and may be stale.
- Validation harness (the stage-3 gain restore, the C/D rebuilds, the cfg helper and
  the None parity frequencies are fixed: [stage 8](#stage-8-instrument-controls)):
  - The stage-7 environment sweep writes the "power_dB" values (−10 … −4) directly as
    `pulse_gain` DAC units, i.e. negative gains. It is a placeholder for an
    attenuator/YOKO sweep.
  - `build_evidence_report` writes a non-ASCII warning sign with the default encoding.
    On this Windows machine (cp1252) a sidecar with a stale `analysis_version` raises
    UnicodeEncodeError.
  - `modulated_strobe_acquire` does not set `experiment.data`, so a following
    `save_data()` stores only the last block.
- `step_us` defaults to `window_us // 2`, which is 0 for windows under 2 µs (e.g.
  decimated). The window grid then raises.
