# zero_span_parity: zero-span two-tone parity switching (ZeroSpanParity)

Recipe: `R.zero_span_parity(...)` (`qicklab.runs.recipes`; every keyword with its default and unit is in the docstring, `help(R.zero_span_parity)`). Session groups: [step table](../running_a_session.md#steps). Generated parameter tables come in phase 6.

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
4. Strobe: `reps_per_chunk ≤ 2·10⁷` (`_MAX_REPS_PER_CHUNK`, a client-memory cap: qick
   keeps ~16 B per sample in its raw buffer and the record is copied several times as
   floats). Until 2026-10 this rule was `reps_per_chunk ≤ avg_maxlen` (16384), which
   is not a qick limit: in qick 0.2.334 the averages buffer is a ring buffer that the
   board-side streamer drains during `acquire()`, one stride (10 % of `avg_maxlen`,
   1638 samples) at a time. The real limit is qick's own "Overflowed the averages
   buffer" `RuntimeError` (the streamer fell more than one buffer behind), which
   `acquire_with_retry` deliberately does not retry. When `reps_per_chunk ≥
   avg_maxlen` the record wraps the ring, and the check prints a warning (no error) if
   the headroom per stride, `(avg_maxlen − stride) · sample_period_us`, is below
   100 ms (`_STREAM_HEADROOM_WARN_MS`); at 20 µs it is 295 ms. The runner defaults
   (10000 × 60 chunks) are unchanged; one 600000-sample chunk would record the same
   12 s without the 59 dead gaps (`UndrivenSingleShot` already takes 10⁶ shots in one
   `acquire()`), pending a board loopback check at the 20 µs cadence.
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
PLAN = [R.zero_span_parity(run_mode="strobe",
                           strobe={"sample_period_us": 20.0, "reps_per_chunk": 10_000,
                                   "n_chunks": 60, "read_length": 5.0,
                                   "adc_trig_offset": 0.488})]
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
   Otherwise validate the cache (rule 7). Under a session both caches live on disk as
   `<data_root>/Q{q}/zsp_cache.json` (pulse qubit): read before the step for entries still
   `None` (step value > `Qubit.parity` > file), rewritten after a successful run
   ([adding_a_device](../adding_a_device.md#calibration-write-back)).
3. Build the cfg. With any of stages 1-3 enabled (strobe only), run them now, on their
   own `ZeroSpanParity` instance, and feed their results into the cfg (see
   [Run order and feedback](#run-order-and-feedback)): stage 1 sets `read_pulse_freq`
   (re-deriving the separator at that probe, or keeping the resonator centre with a
   cached separator), stage 2 refines `parity_drive_freq`, stage 3 is the gate.
4. Build a **fresh** `ZeroSpanParity` from the final cfg and **acquire** the main record:
   - **Strobe, `n_chunks > 1`:** `chunked_acquire` stitches the `acquire()` calls,
     makes `t_us` monotonic and marks chunk boundaries in `gap_indices`. Gaps between
     chunks are not modelled in `t_us`; analysis never counts a switch across a gap.
     Each inner `acquire()` leaves only its own chunk in `experiment.data`, so
     `chunked_acquire` replaces `experiment.data` with the stitched record. A plain
     `save_data()` afterwards therefore saves the whole record.
   - **Decimated:** `n_captures` captures are stitched with `gap_indices`.
5. **Analysis.** `analyze_parity_run` writes its sidecars into the same run folder as
   the raw h5.
6. **Validation stages 8, 7 and 9**, on the main record's instance (see below).

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
| Strobe `reps_per_chunk` | 10000 | count | Samples per program; ≤ 2·10⁷ (rule 4), not bounded by avg_maxlen. |
| Strobe `n_chunks` | 60 | count | Chunks to stitch; each boundary is a dead gap (`gap_indices`). |
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
| `ContrastVsQubit.qfreq_span_mhz` / `n_points` | 10.0 / 81 | Stage 2 drive-frequency sweep. Refining `parity_drive_freq` needs ≥ 6 points within the capture range (step ≤ capture / 3): the default 0.125 MHz step refines only for a doublet splitting ≥ ~0.75 MHz; use more points (e.g. 161) for a narrower doublet. |
| `ContrastVsQubit.min_peak_snr` (optional) | 5 (`MIN_PARTNER_SNR`) | Contrast SNR a stage-2 peak needs to refine `parity_drive_freq`. |
| `ContrastVsQubit.doublet_sep_tol_MHz` (optional) | max(25 % of the splitting, 2 grid steps) | How far the stage-2 pair separation may differ from the cached splitting and still assign the parked branch by line order. |
| `Modulation.modulation_freq_hz` / `n_periods` | 25 / 10 | Stage 3 square wave (40 ms period). |
| `Modulation.min_block_t` / `min_abs_correlation` / `min_snr` (optional) | unset (flag at \|block_t\| < 5) | Stage-3 gate; the ones set replace the default and make a failure raise before the main record. |
| `Control.variants` / `detune_mhz` | A, B, C, D / 50.0 | Stage 8. |
| `Environment.param_name` / `values` | "power_dB" / [−10, −8, −6, −4] | Stage 7 (see Known issues). |

## Outputs

- **Raw**, path `ZeroSpanParity/` (under `<outer>/ZeroSpanParity/`). The h5 is opened
  in append mode, so the config attribute survives, and datasets are deleted and
  recreated, so re-saving is idempotent.
  - Datasets: `I`, `Q`, `t_us`, `gap_indices`; plus `capture_sizes`,
    `chunk_wall_clock_starts` and `chunk_wall_clock_ends` when present (chunked strobe
    records and decimated captures). Each start is taken just before and each end just
    after the chunk's `acquire()` call, so the bracket also holds that chunk's program
    load, buffer configuration and final transfer. The times therefore bound the dead
    time rather than measure it. With T the sampling time of one chunk
    (`reps_per_chunk × sample_period_us`; for a decimated capture, its sample count ×
    `sample_period_us`), the gap between chunk i's last sample and chunk i+1's first
    sample satisfies `starts[i+1] − ends[i] ≤ gap ≤ ends[i+1] − starts[i] − 2T`, and
    `(ends[i] − starts[i]) − T` is chunk i's load/configure/transfer overhead. Both
    assume `sample_period_us` is the true rep period, which is not checked against the
    board.
  - Attributes: `wall_clock_start`, `wall_clock_end`, `sample_period_us`, `mode`, `decimated_fs_MHz`,
    `decimated_fs_source` (`"soccfg.f_output_unverified"`), `read_length_us`,
    `capture_length_us`, `adc_trig_offset_us`, `ro_norm_cycles`,
    `samples_per_capture` (actual first-capture length, not total/n_captures),
    `n_chunks`, `n_captures`, `soft_avgs`.
  - json: the cfg. No png from the experiment itself.
- **Analysis**, in the same run folder:
  - `<base>_analysis.json`: summary, bursts, window, step, and `provenance` (of the analysis
    run; [provenance](../architecture.md#provenance)).
  - `<base>_analysis.h5`: `binary_states`, `scores`, `window_t_us`, `rate_Hz`,
    `dwell_0_us`, `dwell_1_us`, summary attrs.
  - `<base>_iq_scatter.png`, `_parity_vs_time.png`, `_switch_rate_vs_time.png`,
    `_dwell_histograms.png`.
  - Summary fields: `baseline_rate_Hz`, `baseline_rate_err_Hz`, `n_switches_baseline`,
    `T_baseline_s`, `median_window_rate_Hz`, `n_bursts`, `mean_dwell_0/1_us`,
    `n_runs_0/1`, `tau_mle_0/1_us`, `tau_err_0/1_us`, `n_exits_0/1`, `n_interior_0/1`,
    `exp_fit_tau_0/1_us` (legacy histogram fit, biased high), `raw_sample_period_us`,
    `n_raw/binned_samples`, `analysis_bin_us`, `mode`, `classifier_method`,
    `classifier_threshold` (score units), `bits_withheld`, `classifier_warning`, and the
    `apriori_gmm` score-histogram fit: `classifier_separation_snr`, `classifier_delta_bic`,
    `classifier_centers`, `classifier_sigmas`, `classifier_weights` (lower component first,
    score units; NaN for `apriori_midpoint` and `kmeans`). The fit is reported even when
    it fails the gate and the bits are withheld.
  - Readout-error model and threshold-free rates ([Analysis](#analysis) step 7):
    `readout_eps_0/1`, `readout_eps`, `threshold_spurious_rate_Hz_est`,
    `threshold_switch_rate_Hz`, `acf_tau_corr_us`, `acf_gamma_Hz`, `acf_fit_ok`,
    `psd_f_corner_Hz`, `psd_gamma_Hz`, `psd_fit_ok`, `hmm_identifiable`,
    `hmm_gamma01/10_Hz`, `hmm_gamma01/10_err_Hz`, `hmm_switch_rate_Hz`,
    `hmm_emission_snr`, `hmm_n_samples`, `hmm_unidentifiable_reasons`,
    `rate_switch_threshold/acf/psd/hmm_Hz`, `rate_agreement_max_ratio`,
    `rates_disagree`, `rate_agreement` (one printed line) and `rate_warnings`.
  - When the bits are withheld (`bits_withheld` True, see [Analysis](#analysis) step 2),
    every rate, burst and dwell field is NaN, `binary_states` is empty, and only
    `_iq_scatter.png` (uncoloured) is drawn.
- **Validation:** per-stage JSON sidecars plus raw arrays (stitched IQ, references,
  `freqs`, `Z_on`/`Z_off` and their standard errors), each tagged with an
  `analysis_version`, and `EVIDENCE.md` from stage 9. The stage-1/2 error fields are
  listed under [Stage-1/2 contrast SNR](#stage-12-contrast-snr).

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
   No switch is counted across a `gap_indices` boundary. Each window's rate is its
   switch count over the time it covers, `covered_us` = min(`window_us`, t_end − start
   + sample period): only a last window that runs past the record end (or a record
   shorter than one window) is shorter than `window_us`, and it is kept, not dropped.
   A window that would start after the last sample (only when `step_us` > `window_us`)
   holds no data and is not returned.
4. **Bursts.**
   - threshold = baseline + `k_sigma`·σ, baseline = event-based switch rate (see
     [Baseline switch rate](#baseline-switch-rate)).
   - σ = max(1.4826·MAD about the median, Poisson floor). The Poisson floor is
     q·√max(baseline_counts, 1), with q = 1/(window_us·1e-6), the rate of one switch
     per window.
   - The floor exists because more than 50 % of windows hold zero switches, so the MAD
     is 0.
   - A partial last window (`covered_us` = c < `window_us`) is held to its own
     threshold: σ_c = max(1.4826·MAD·√(window_us/c), q_c·√max(baseline/q_c, 1)) with
     q_c = 1/(c·1e-6), the same significance as a full window. With `k_sigma` ≥ 1 a
     single switch in a short tail therefore never reads as a burst; a real one is
     still flagged and excluded from the baseline. The reported `threshold_Hz` is the
     full-window one.
5. **Dwell times.**
   - Run lengths per state, in µs and in samples, split at gaps. The last run of each
     segment is extrapolated by one sample period. The first and last run of each
     segment are **censored** (cut by the segment edge); `mean_dwell_0/1_us` still
     averages all runs.
   - **Dwell time τ (`tau_mle_0/1_us`)**: maximum-likelihood estimate of τ_s = 1/γ_s
     for a continuous-time two-state telegraph (rates γ_0 out of 0, γ_1 out of 1)
     sampled every sp, with the censored runs included. Sampled, the telegraph is a
     two-state Markov chain: every step from a sample in state s to the next sample of
     the same segment is a trial that leaves s with probability
     P_s = (γ_s/Γ)·(1 − exp(−Γ·sp)), Γ = γ_0 + γ_1 (a switch inside the step can be
     undone by a second one, so P_s depends on both rates). Its MLE is
     P_s = N_exits / exposure (`p_exit_0/1` in the dwell dict), where N_exits
     (`n_exits_0/1`) counts the switches out of s and the exposure counts the samples in
     s that have a next sample in the same segment: a run of n samples adds n trials,
     or n − 1 if it is the segment's last run, which has no exit. Inverting,
     λ = 1 − P_0 − P_1, Γ = −ln(λ)/sp and τ_s = (P_0 + P_1)/(P_s·Γ). The single-state
     form −sp/ln(1 − P_s) would read high by about sp/(2·τ_other) (+9.5 % for
     τ_0 = 60 µs, τ_1 = 120 µs at sp = 20 µs). `tau_err_0/1_us` is the delta-method error
     through both P_0 and P_1 (binomial variances), ≈ τ/√N_exits. sp is the median
     within-segment sample spacing. τ is NaN with fewer than 5 exits from s, or when
     λ ≤ 0 (P_0 + P_1 ≥ 1, e.g. every run one sample long: switching not resolved at
     this sp). `n_interior_0/1` is the number of uncensored runs, for information.
   - Bias, on event-driven continuous-time telegraphs (exponential dwells, random
     sampling phase, sp = 20 µs, τ = 60 µs to 2 ms, 200 replicates): within ±1.3 % at
     100 dwells and ±1.1 % at 300, consistent with zero at that replicate count, with
     `tau_err` matching the replicate scatter; the histogram fit reads +15 % to +30 %
     there. Asymmetric telegraphs ((τ_0, τ_1, sp) = (60, 120, 20), (200, 400, 20),
     (2000, 4000, 100) µs) are recovered to under 0.5 %. For segments as short as 5 τ
     (τ = 2 ms, 40 replicates) the bias stays under 0.5 %. The mean of the interior runs
     alone is biased low by about τ/T_segment, because long dwells are the ones a
     segment cuts off: −23 % at 5 τ, −10 % at 10 τ, −3 % at 20 τ, under 1 % at 100 τ.
     That is why the censored runs are kept.
   - The exponential fit to the histogram (log-linear regression weighted by √count,
     `exp_fit_tau_0/1_us`) is kept for the histogram overlay binning and as a legacy
     field. At 100–300 dwells it reads τ about 15 % high (+5 % at 1000), so it meets the
     ±5 % acceptance criterion only for N ≳ 1000. The `_dwell_histograms.png` overlay is
     the MLE run-length law, N·(bin width/sp)·P_s·(1 − P_s)^((x − sp)/sp).
   - Optional debouncing (`min_dwell_bins` = m) for the bin-size and threshold-stability
     checks. Debouncing removes runs shorter than m and lengthens their neighbours, so
     there the first m − 1 steps of every run whose start is observed are not counted
     as trials (for the interior runs, P = 1/(mean(n) − (m − 1))), then τ is inverted as
     above. This is an approximation, not exact: the debounced trace is not a sampled
     telegraph, because debouncing also merges the real dwells shorter than m. At m = 2
     on continuous-time telegraphs, with or without 1 % one-sample readout flips, τ is
     recovered within about 1 % at τ = 100 sp but reads high by about 7 % at τ = 20 sp
     and 11 % at τ = 10 sp.
6. **Bimodality** (`projected_histogram_snr`): bimodal requires ΔBIC > 0 **and**
   separation SNR > 1.5 **and** both weights in (0.1, 0.9).
7. **Readout-error model and threshold-free rates** (`_noise_robust_rates`). Every
   threshold-counted rate and dwell above assumes perfect assignment, but each
   misassigned sample adds two spurious switches. The summary therefore carries, for
   every classifier method (the score fit is the `apriori_gmm` one, or the same
   `projected_histogram_snr` fit run on the scores for the other methods):
   - **eps.** `readout_eps_0` = P(score > threshold | lower Gaussian), `readout_eps_1`
     = P(score ≤ threshold | upper Gaussian), `readout_eps` = w_0·eps_0 + w_1·eps_1,
     and `threshold_spurious_rate_Hz_est` = 2·eps·(1 − eps)/`sample_period_us` (the
     post-binning period: binning lowers eps, which is the existing remedy).
   - **ACF** on the scores (`autocorrelation_rate_us`, lag 0 excluded): lag products
     are summed only inside the gap-free segments and normalised per lag by their pair
     count (the segment-length-weighted mean ACF), then fitted once. For unequal rates
     `acf_gamma_Hz` = 1/(2 τ_corr) is (γ_01 + γ_10)/2.
   - **PSD** on the scores (`psd_rate_estimate`, Welch + Lorentzian, `psd_gamma_Hz` =
     π f_c = (γ_01 + γ_10)/2). Welch windows run across acquisition gaps, so when the
     record has gaps the PSD rate is still reported but warned and left out of the
     agreement below (`rate_switch_psd_Hz` = NaN): on many short captures it reads
     about as high as a gap-blind count.
   - **HMM** (`fit_two_state_hmm`, fixed Gaussian emissions from the score fit, default
     gates including `min_emission_snr` = 0.7, which must not be lowered) on at most
     `hmm_max_samples` (default 100 000) leading samples. That usually takes 3-8 s, but
     up to about a minute when the L-BFGS-B fit fails and the HMM's Powell fallback runs
     (`rate_warnings` then says "retried with Powell"): the regression harness's gapped
     record with no time correlation (6e5 samples, 60 captures) takes 55 s, and the HMM
     withholds it anyway. Lower `hmm_max_samples` to bound it. The per-step dt is
     diff(`t_us`), except that every step across a `gap_indices` boundary is set to
     `HMM_GAP_DT_S` = 1000 s: saved `t_us` is contiguous across the dead time (see
     above), so without this the HMM would read a parity change across a boundary as a
     transition. With it each gap-free segment is an independent restart, as for the
     other estimators. On 120 captures of 400 µs (true 752 Hz) a gap-blind HMM gives
     1844 Hz and this one 731 Hz. Its start rate is the midpoint-crossing count over the
     gap-free steps. Its rates are NaN unless `hmm_identifiable`;
     `hmm_unidentifiable_reasons` says why.
   - eps, the HMM and the occupancy scale below need a usable score fit: ΔBIC > 0 and
     separation SNR > 1.5 (the step-6 gate without the weight condition, so a lopsided
     parity occupancy still qualifies). A fit failing that is no emission model: on a
     1σ split it would put the HMM at about 3× the true rate.
   - **Agreement.** All four estimators are expressed as a switch rate (switches per
     second, what threshold counting measures): `rate_switch_threshold_Hz` = all
     switches / all observed time (`event_switch_rate`, bursts included; NaN when the
     bits are withheld), HMM 2·γ_01·γ_10/(γ_01 + γ_10), ACF and PSD (γ_01 + γ_10)/2 ×
     4·w_0·w_1 (the fit weights), the PSD only for a gap-free record. `rates_disagree`
     is True when the largest finite one exceeds the smallest by more than
     `RATE_AGREEMENT_MAX_RATIO` = 2. The
     `rate_agreement` line is printed. On a 3.5σ split (eps ≈ 4 %, sp = 20 µs, true
     520 Hz) threshold counting gives 4307 Hz (spurious estimate 3796 Hz), the ACF
     544 Hz, the PSD 524 Hz and the HMM 528 Hz.
   - The existing threshold fields (`baseline_rate_Hz`, dwells, bursts) are unchanged;
     these are reported beside them. Every block is guarded: a failure leaves its
     fields NaN with a note in `rate_warnings`.

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
is strobe-only (decimated timing is unverified) and collates evidence. Apart from the
stage-1/2 feedback and the stage-3 gate ([below](#run-order-and-feedback)), it gives **no
automatic pass/fail**.

| Stage | Name | What | Status |
|---|---|---|---|
| 1 | Static contrast | Drive parked on one branch; sweep the probe frequency; maximise \|Z_on − Z_off\|; contrast SNR from per-point batch-means errors, max SNR tested against a 5 % threshold ([below](#stage-12-contrast-snr)) | `run_static_contrast` |
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
  before sweeping the qubit frequency: a bad probe point can miss the branches. The
  run implements 1 → 2 → 3 → main record → 8 → 7 → 9 (no second stage-1 pass; stages
  4-6 are not implemented).
- Stage 1 does not use the g/e separator. It compares averaged complex responses
  with the drive on and off. For stage 1 only, the run sets both `reps_per_chunk` and
  `reps` to `reps_per_point` (the strobe program is rebuilt from `cfg["reps"]`), and
  restores both afterwards, so stages 2-3, the main record and stages 8/7 use the
  run's `reps_per_chunk`.
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
  across thresholds indicates a robust telegraph only when every threshold sits in the
  gap between the two score clouds. The default `threshold_list` (30th-70th percentiles
  of the scores) does not: for a balanced, well-separated telegraph those percentiles
  fall inside a cloud, about 0.25 sigma from its centre, so each threshold reads that
  cloud's noise as switches. At the defaults a clean telegraph and pure noise give
  similar `tau_cv` (about 0.6 each in the unit-test traces), and the clean one can come
  out higher. Pass thresholds that lie between the cloud centres (e.g. from the
  `apriori_gmm` fit) until the defaults are moved. `bin_size_sweep` (`exp_tau_per_bin`)
  and `threshold_stability` (`tau0/1_per_threshold`, `tau_cv`) use the dwell-time MLE
  (Analysis step 5), not the histogram fit.
- `reps_per_block` must be ≤ avg_maxlen (16384), so each modulation block fits the
  averages buffer without streaming. This is a choice of `modulated_strobe_acquire`,
  not a qick limit (rule 4 above); it bounds the slowest square wave to
  1 / (2 · 16384 · `sample_period_us`), 1.5 Hz at 20 µs.

### Run order and feedback

The parked drive frequency comes from a pulsed spectroscopy (readout off during the
drive), so it misses the AC-Stark shift of the CW readout the record uses (about
2χn̄, comparable to the 0.2-2.7 MHz parity splitting) and the measurement broadening.
Stages 1-3 measure under that CW readout, so they run first and feed the main record:

- **Instances.** Stages 1-3 run on their own `ZeroSpanParity` instance, built from a
  copy of the cfg. The main record is a fresh instance built from the final cfg, so its
  program depends only on the chosen values, not on what the stages left in the cfg.
  Stages 8 and 7 run on the main instance after the record. Every sidecar and
  `EVIDENCE.md` go to the same run folder.
- **Stage 1 → `read_pulse_freq`.** When `best_freq` is finite and its own
  `contrast_snr` (the SNR at `best_freq`, not `contrast_snr_max`) exceeds
  `contrast_snr_threshold`, the cfg's `read_pulse_freq` becomes `best_freq`; otherwise it
  stays at the resonator centre (a printed FLAG). Stage 2, stage 3 and the main record
  use it.
- **Separator at the new probe.** The g → e axis that every separator classifier
  projects on (`classifier_method` `apriori_gmm` / `apriori_midpoint`: the main
  analysis, stage 3, stages 8 and 7) is only valid at the probe it was calibrated at:
  the I/Q frame and the g − e difference vector rotate with probe detuning, so the
  projected contrast falls as cos θ. When `best_freq` differs from the resonator centre
  and the classifier uses the separator, the run re-derives it with a SingleShot g/e
  calibration at `best_freq` (`get_apriori_separator_from_singleshot(ctx,
  pulse_freq=best_freq)`, a second `SingleShot_MRCalib` file) when
  `RecalibrateSeparator` is True. With a cached separator it does not move the probe
  (a printed FLAG, `read_pulse_freq_source = resonator_center_cached_separator`).
  `kmeans` needs no separator, so it adopts `best_freq` without one; but stages 3, 8
  and 7 score the record on the separator projection, so `kmeans` with
  `Validate_ModulationCheck`, `Validate_ControlSuite` or `Validate_EnvironmentSweep`
  raises RuntimeError at the start of the run, before any acquisition (before 2026-10 it
  crashed after the main record, in the first of those stages). `kmeans` runs with
  stages 1-2 only.
- **Stage 2 → `parity_drive_freq`** (`nearest_contrast_peak`). The capture range is
  half the doublet splitting `parity_peak_sep_MHz` when both lines are known, else the
  spec `min_sep_MHz`. Branch assignment: when both cached lines are known and stage 2
  (`find_two_tone_peaks`, grid points) finds exactly two lines whose separation matches
  the cached splitting within `doublet_sep_tol_MHz` (default max(25 % of the splitting,
  2 grid steps)), the parked line is the lower or higher of the two, by
  `which_to_park` (`parity_stage2_doublet = matched`). The CW-readout shift is common to
  both lines, so this assignment is right for any common shift inside the stage-2 span,
  including one larger than half the splitting, where the line nearest the parked
  frequency is the partner (printed). Otherwise the stage-2 line nearest the parked
  frequency is used, and only within the capture range. That line is the parked one, not
  its partner, only for a common shift below half the splitting, so when the cached
  splitting is known but stage 2 does not show a matching doublet (one line found, or a
  pair at a different separation) the run prints a FLAG
  (`parity_stage2_doublet = mismatch`; `unknown` when the partner is not cached). In
  that case a common shift between half and 1.5 times the splitting would put the
  parked frequency on the partner branch: re-run the spectroscopy under the CW
  readout. The assigned grid peak must have `contrast_snr_per_point` ≥ `min_peak_snr`
  (default 5). Its centre is then refined below the grid step by a Lorentzian fit
  (`fit_lorentzian_near_peak`, the two-tone acceptance gates: ≥ 6 points, R², width) to
  the stage-2 contrast within the capture range of that grid peak. The fitted centre
  replaces the parked line when it differs from the parked line by more than 2 fit
  standard errors (and, for a nearest-line assignment, lies within the capture range);
  a shift consistent with zero leaves it in place. Otherwise (no peak, low SNR, fit
  failed — e.g. fewer than 6 grid points in the capture range — centre outside the
  capture range, or consistent with no shift) the line is not refined (a printed FLAG
  with the reason). The line is never snapped to a raw grid point. The single-line fit
  is biased by a neighbouring line's tail (a few kHz for a 0.6 MHz doublet of 0.1 MHz
  HWHM lines). Stage 3 and the main record use the refined line; the main cfg records
  `parity_stage2_doublet` and the stage-2 pair separation `parity_stage2_peak_sep_MHz`.
- **Stage 3 gate.** The default statistic is the block-means t, `block_t`
  (`modulation_block_t`): the record is cut at `gap_indices` into its on/off blocks
  (one half-period, `reps_per_block` samples each), each block's mean score is one
  sample, and `block_t` is the Welch t of mean(on) − mean(off) (signed, positive toward
  e). A block is much longer than the parity correlation time, so the block means are
  close to independent and the null is about Student t with 2·`n_periods` − 2 dof;
  the default threshold \|`block_t`\| ≥ 5 (`MODULATION_MIN_BLOCK_T`) is a false-alarm
  probability of about 1e-4 at `n_periods` = 10. Without recipe values a failure only
  prints a FLAG. The recipe keys `min_block_t` (on \|`block_t`\|), `min_abs_correlation`
  and `min_snr` replace the default: exactly the ones set are tested, and a failure
  raises RuntimeError before the main record. NaN fails. The per-sample `snr`
  (\|level_on − level_off\| / pooled per-sample σ) and `correlation` (about
  snr/√(snr² + 4)) scale with the single-shot separation and not with the record
  length: a parked drive that excites one parity to p_e ≈ 0.5 shifts the level by about
  0.25·\|e − g\|, so at a single-shot separation SNR of 2 the per-sample snr is about 0.5
  and the correlation about 0.24 although the telegraph is easily resolved. They are
  heuristics, used only when the recipe sets them.
- **Provenance**, in the main record's cfg (json and h5 `config`), only for the stages
  that ran: `read_pulse_freq_nominal` (the resonator centre) and `read_pulse_freq_source`
  (`stage1_static_contrast` or `resonator_center`); `parity_drive_freq_unrefined`,
  `parity_drive_freq_refined` (bool) and `parity_drive_freq_stage2_snr` (the nearest
  peak's SNR, None without a peak); `parity_drive_freq_stage2_fit_center` and
  `parity_drive_freq_stage2_fit_se` (only when the Lorentzian fit ran and passed); `separator_probe_freq` (only when the separator was
  re-derived at `best_freq`); `modulation_correlation`, `modulation_snr`,
  `modulation_block_t`, `modulation_gate_passed`. The `read_pulse_freq_source` values
  are `stage1_static_contrast`, `resonator_center` (not significant) and
  `resonator_center_cached_separator` (significant, but the cached separator blocks the
  move).
- **Stage 8 control D** drives the cached spectroscopy lines. When stage 2 refined the
  parked line, both cached lines are shifted by the same refinement
  (`parity_drive_freq` − `parity_drive_freq_unrefined`) for control D, so D drives the
  record's lines under the CW readout (the Stark shift 2χn̄ is common to both parity
  lines). The on-disk cache keeps the spectroscopy values.
- **Before 2026-10 (F44)** the main record was taken and analysed first, at the
  resonator centre and the spectroscopy line; the stage-1 `best_freq` and the stage-2
  peaks were only printed and the stage-3 gate was not applied. Stages 2, 3, 8 and 7
  reused the record's instance with stage 1's `reps_per_point` left in `reps_per_chunk`
  (2000 instead of 10000 when stage 1 ran).

### Stage-1/2 contrast SNR

- **Per-point errors.** Each acquisition (one record of `reps_per_point` time-ordered
  strobe samples in stage 1, `reps_per_chunk` in stage 2) gives the mean Z = ⟨I⟩ + i⟨Q⟩
  and batch-means standard errors of ⟨I⟩ and ⟨Q⟩ plus their covariance (`complex_response_stats`): the record is cut into
  `n_blocks` = 20 contiguous blocks, se = std(block means)/√n_b with n_b − 1 dof (fewer
  blocks, each ≥ 2 samples, below 40 reps; NaN below 2 blocks). The samples are
  correlated by the parity telegraph and drift, so std/√N would be too small. The
  number of acquisitions is unchanged (one per point and drive setting).
- **SNR.** For D = Z_on − Z_off, σ² = uᵀ(C_on + C_off)u with u = D/\|D\| and C the 2×2
  covariance of the mean (I, Q); the covariance term matters when the telegraph runs
  along a diagonal of the IQ plane. `contrast_snr` = \|D\|/σ at `best_freq`;
  `contrast_snr_max` is the largest over the sweep. `contrast_significant` is True when
  `contrast_snr_max` exceeds `contrast_snr_threshold`, the value the largest of N
  pure-noise SNRs exceeds with probability `alpha` = 0.05: under no signal \|D\|/σ is
  Rayleigh (exact σ) or √(2 F(2, ν)) (σ from ν = n_b − 1 dof, the smallest over the
  points), and the points are treated as independent. For N = 41, ν = 19 the threshold
  is 4.40 (3.66 with exact σ); the largest of 41 pure-noise SNRs is typically ~3.
- **Fields.** Stage-1 scalars: `contrast_snr`, `contrast_snr_method`
  (`standard_error`), `contrast_snr_max`, `contrast_snr_threshold`,
  `contrast_significant` (stored as 1.0/0.0), `alpha`, `contrast_peak_to_mad`,
  `n_blocks`, `n_batches_min`; arrays `Z_on_se_real/imag`, `Z_off_se_real/imag`
  (se of ⟨I⟩ / ⟨Q⟩), `Z_on_cov_IQ`, `Z_off_cov_IQ`, `contrast_se` (σ) and
  `contrast_snr_per_point`. Stage 2: arrays `z_on_se_real/imag`, `z_on_cov_IQ`,
  `contrast_se`, `contrast_snr_per_point`; scalars `z_off_se_real/imag`,
  `z_off_cov_IQ`, `n_blocks`, `n_batches_min`. Stage 2's single drive-off baseline
  error is shared by all its points: a correlated offset, not independent noise, so
  its per-point SNRs are not independent and no significance flag is given. The
  contrast plots draw ±σ error bars.
- **Block length vs T_parity.** At the stage-1 defaults (2000 reps × 20 µs = 40 ms) a
  block is 2 ms, comparable to T_parity (~2–3 ms). On a drive-on record dominated by the
  telegraph the batch-means se is then low by up to ~40 % (exponential correlation,
  block = dwell) and the SNR up to ~1.6× too high. Stage 2 runs at the run's
  `reps_per_chunk` (10000 × 20 µs = 200 ms, 10 ms blocks), where the bias is smaller.
  Pass a smaller `n_blocks` to `run_static_contrast` / `run_contrast_vs_qubit_freq`, or a
  larger `reps_per_point` (stage 1) / `reps_per_chunk` (stage 2), when the telegraph
  dominates the noise.
- **Before 2026-10 (F45)** `contrast_snr` was the peak contrast over the MAD of the
  contrast curve itself (`estimate_noise_floor`): a shape ratio that scores a noiseless
  Lorentzian above 3, not a signal-to-noise ratio, and no stage stored an error. That
  value is kept as `contrast_peak_to_mad`. `contrast_from_sweeps` called without
  standard errors still returns it as `contrast_snr`, with `contrast_snr_method` =
  `peak_to_mad`.

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
  uneven. `chunk_wall_clock_starts` and `chunk_wall_clock_ends` bracket each block's
  `acquire()` call, so they bound the dead time between blocks (see Outputs) rather than
  measure it.

### Stage-8 instrument controls

`run_control_suite` takes one record per setting and projects it on the separator
(score > 0 = bright, e). Every variant rebuilds the program (`set_qubit_gain`) after
its cfg change, and the base point is rebuilt at the end, also when an acquisition
raises. A drive-off record is the reference. The per-variant results are in the
sidecar's `variants`; EVIDENCE.md renders them as a `variant | metric | value` table.

- **Record length.** One acquisition holds `reps_per_chunk` samples, the run's value
  (stage 1 restores it), e.g. 10000 × 20 µs = 200 ms.
  Each control record therefore stitches ⌈`min_record_us` / (`reps_per_chunk` ×
  `sample_period_us`)⌉ acquisitions of the same program, with `min_record_us` = 200 ms
  by default. The stitched time omits the dead time between acquisitions. The sidecar
  holds `blocks_per_record` and `record_us`. To lengthen the records, pass a larger
  `min_record_us` or a larger ZSP `reps_per_chunk`. Before 2026-10 (F44) stage 1 left
  its `reps_per_point` (2000, 40 ms) in `reps_per_chunk`, so with stage 1 enabled each
  record stitched 5 acquisitions instead of 1.
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
  midpoint (from `parity_freqs`, the cached peaks, both shifted by the stage-2
  refinement when it fired: [Run order and feedback](#run-order-and-feedback)). Driving a peak excites only the
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
    attenuator/YOKO sweep, and it bypasses the [gain guard](../concepts/timing_and_units.md#gains)
    (it rebuilds the program directly).
  - `build_evidence_report` writes a non-ASCII warning sign with the default encoding.
    On this Windows machine (cp1252) a sidecar with a stale `analysis_version` raises
    UnicodeEncodeError.
  - `modulated_strobe_acquire` does not set `experiment.data`, so a following
    `save_data()` stores only the last block.
- `step_us` defaults to `window_us // 2`, which is 0 for windows under 2 µs (e.g.
  decimated). The window grid then raises.
