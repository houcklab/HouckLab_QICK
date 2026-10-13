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
   length. It is a nominal estimate that may be off by O(1) sample where the tProc and
   readout clocks differ.
6. If `RecalibrateParityFreqs = False`, the cached frequency selected by
   `which_to_park` must be set. The spec required a finite float; the code checks
   only that it is not None.
7. If `RecalibrateSeparator = False` and `classifier_method = "apriori"`, all four
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
   lower and higher peaks and park on `which_to_park`. Otherwise use the cache (rule 6).
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
| `classifier_method` | "apriori" | – | `"apriori"` (separator) or `"kmeans"`. |
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
  - Summary fields: `baseline_rate_Hz`, `n_bursts`, `mean_dwell_0/1_us`,
    `n_runs_0/1`, `exp_fit_tau_0/1_us`, `raw_sample_period_us`,
    `n_raw/binned_samples`, `analysis_bin_us`, `mode`, `classifier_method`.
- **Validation:** per-stage JSON sidecars plus raw arrays (stitched IQ, references,
  `freqs`, `Z_on`/`Z_off`), each tagged with an `analysis_version`, and `EVIDENCE.md`
  from stage 9.

## Analysis

1. **Normalisation units (strobe).** I and Q are divided by
   `us2cycles(read_length, ro_ch=0)` to match the SingleShot separator. The SingleShot
   `collect_shots` normalisation is the reference, so `ro_ch=0` is used deliberately,
   not `ro_chs[0]`. `di_buf`/`dq_buf` are indexed by readout **declaration order**
   (position 0), while `soccfg["readouts"][ch]` is keyed by absolute channel.
2. **Classify** (`classify_parity_trace`):
   - `apriori`: project onto the SingleShot separator.
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
   - threshold = baseline + `k_sigma`·σ, baseline = median rate.
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
| 8 | Instrument controls | A drive off; B drive far detuned; C probe off-resonance → contrast vanishes; D drive on the other branch → assignment reverses (`branch_sign_flip` is strong evidence) | `run_control_suite` |
| 9 | Evidence report | Collate stages 1–8 into EVIDENCE.md | `build_evidence_report` |

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
  every setting.
- Z_on and Z_off are proportional to S21; they are not calibrated.
- Stage-5 interpretation: the best bin may come before T_parity. A low `tau_cv`
  across thresholds indicates a robust telegraph.
- `reps_per_block` must satisfy avg_maxlen (16384).

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
  `decimated_fs_source` are saved for post-hoc reconstruction. The likely cause is the
  `declare_readout` bug below.
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

- **`declare_readout` omits `ro_ch`.** The readout length is given in tProc cycles,
  but qick 0.2.334 interprets it as decimated samples. The integration window and the
  decimated record are therefore f_time/f_output (about 1.4×) longer than
  `read_length`. This also means:
  - the strobe normalisation (which divides by the readout-clock count) is off by the
    same factor relative to the SingleShot separator;
  - the rule-5 estimate counts the wrong number of samples.

  [modified_ramsey](modified_ramsey.md), [active_reset_verify](active_reset_verify.md)
  and [undriven_single_shot](undriven_single_shot.md) all pass `ro_ch`.
- The decimated defaults (`read_length = 80 µs`) give ≈ 24576 samples at 307.2 MHz,
  far above buf_maxlen = 1024. Rule 5 rejects them on the current board.
- A `rounds` key in the cfg would override `soft_avgs` inside AveragerProgram,
  bypassing the soft-average gate (decimated) and keeping only the last round
  (strobe). The run does not set `rounds` today.
- Strobe `t_us = index · sample_period_us` ignores the per-rep tProc overhead.
  Modified Ramsey and Undriven derive the period from the compiled schedule instead.
- `res_phase` defaults to 0 and ignores any calibrated rotation.
- `current_voltage` is taken from the session start voltage and may be stale.
- Validation harness:
  - The stage-3 modulation check never restores `qubit_gain`. It ends at the last
    schedule entry (0), with the program rebuilt at gain 0. Because stage 3 runs
    before stages 8 and 7, **every control variant and the environment sweep then run
    with the drive OFF**.
  - Control C changes `read_pulse_freq` and control D changes `parity_drive_freq`
    without rebuilding the program. Both are therefore measured at the original
    frequencies, and `branch_sign_flip` can never genuinely be True.
  - The stage-7 environment sweep writes the "power_dB" values (−10 … −4) directly as
    `pulse_gain` DAC units, i.e. negative gains. It is a placeholder for an
    attenuator/YOKO sweep.
  - The cfg-preservation helper writes None into keys that were absent at entry. With
    unset frequencies, controls drive at `0 + 50 MHz`. Control D raises TypeError when
    the cached parity frequencies are None.
  - `build_evidence_report` writes a non-ASCII warning sign with the default encoding.
    On this Windows machine (cp1252) a sidecar with a stale `analysis_version` raises
    UnicodeEncodeError.
  - `modulated_strobe_acquire` does not set `experiment.data`, so a following
    `save_data()` stores only the last block.
- `step_us` defaults to `window_us // 2`, which is 0 for windows under 2 µs (e.g.
  decimated). The window grid then raises.
