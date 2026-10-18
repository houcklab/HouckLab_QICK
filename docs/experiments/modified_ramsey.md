# modified_ramsey: fixed-tau Ramsey charge-parity record (ModifiedRamsey)

Recipe: `R.modified_ramsey(...)` (`qicklab.runs.recipes`; every keyword with its default and unit is in the docstring, `help(R.modified_ramsey)`). Session groups: [step table](../running_a_session.md#steps). Generated parameter tables come in phase 6.

## What it measures

A charge-sensitive transmon (or offset-charge-sensitive qubit) has two transition
frequencies, one for each charge parity: the **parity branches**, split by `df`. A
Ramsey sequence with a fixed free-evolution time `tau = 1/(2·df)` makes the two
branches accumulate a relative phase of π. The closing pi/2 then maps one parity
to |g> and the other to |e>. Repeating that single-shot sequence thousands of times
gives a time series whose telegraph switching is the parity switching. The rate is
inferred from the unthresholded IQ trace with a two-state HMM, cross-checked against
autocorrelation (ACF) and power-spectrum (PSD) estimates, and validated with
interleaved control sequences. Code: see `qicklab.experiments.modified_ramsey`
(program, timing model, feasibility planner, control builder),
`qicklab.analysis.modified_ramsey`, `qicklab.analysis.hmm` (HMM) and
`qicklab.analysis.rates` (ACF, PSD, rate vs bin size, drift), and
`qicklab.runs.modified_ramsey`.

## Physics and conventions

### Branches: `f_ge` is the UPPER branch

| Quantity | Value |
|---|---|
| Upper parity branch | `f_ge` (cfg) = doublet centre + df/2 |
| Lower parity branch | `f_ge − df` |
| Symmetric drive frequency | `f_ge − df/2` (doublet centre) |

`f_ge` here is **not** the doublet centre. The legacy run fell back to the qubit
centre frequency when `f_ge` was unset. In the symmetric scheme that puts the drive
at centre − df/2, i.e. on the lower branch with a 90° closing phase, and the result
looks like a contrast failure rather than a misconfiguration. In qicklab,
`symmetric_ramsey=True` with no `parity.f_upper_mhz` on the device raises instead.

### f_ge must sit on the pulsed qubit

The pi/2 and pi gains and the SingleShot separator all come from `Qubit_Pulse`, at
`Qubit_Parameters[Qubit_Pulse]["Qubit"]["Frequency"]`. Nothing else ties `f_ge` to that
qubit, so an `f_ge` hundreds of MHz away would run a full record with no drive on the
qubit. Before any acquisition, `run_modified_ramsey` compares the doublet centre
`f_ge − df/2` with that frequency (`check_f_ge_near_qubit`). The tolerance is
max(5·df, 2 MHz, 1/(4σ)), where 1/(4σ) is roughly the bandwidth of the 4σ Gaussian
(3.1 MHz at σ = 0.08 µs). Outside it the run prints a `WARNING` with f_ge, df, the
centre, the qubit frequency, `Qubit_Pulse` and the offset. It raises ValueError instead
when `require_f_ge_near_qubit=True`.

The check only warns by default because the CSTQ03 runner trips it (see
[known issues](#known-issues)). `qubit_frequency_center` is never updated by a
calibration step, so a stale `Qubit_Parameters` entry also trips it. That is correct:
the separator is then calibrated off-resonance too.

If `f_ge_measured_at_V` is set (the bias at which df and f_ge were measured), the run
saves it in the record config and warns when the yoko readback differs from it by more
than 0.1 mV. It never moves the yoko.

### Standard vs symmetric scheme

| | Standard (`symmetric_ramsey=False`) | Symmetric (`symmetric_ramsey=True`) |
|---|---|---|
| Drive frequency | `f_ge` (on the upper branch) | `f_ge − df/2` (midpoint) |
| Branch detunings | 0 and df | ±df/2 |
| Phase accrued in tau | upper 0, lower π | ±π/2 |
| Closing pi/2 phase | 180° | 90° |
| Mapping | upper → \|g>, lower → \|e> | upper → \|e>, lower → \|g> |
| `flip_final_pi2=True` | 0°, mapping swapped | 270°, mapping swapped |

- The phase and mapping rows are for k = 1 (tau = 1/(2·df)). For odd k the standard
  scheme is unchanged (the lower branch accrues kπ ≡ π). In the symmetric scheme the
  branches accrue ±kπ/2: ±π/2 for k ≡ 1 mod 4 (k = 1, 5, …), but ∓π/2 for k ≡ 3 mod 4
  (k = 3, 7, …), where the mapping is swapped (upper → |g>, lower → |e>; flip swaps it
  back). The contrast is the same.
- The closing phase is `(base + 180·flip) mod 360`.
- The generator DDS is free-running and phase-coherent across the wait. Phase 0 on
  the first pulse and 180° on the last are therefore exact inverses, independent of
  tau; no `2π·f·tau` correction is needed.
- The symmetric scheme halves the worst branch detuning. Example: at σ = 0.1 µs and
  df = 0.5 MHz the ratio drops from 0.50 to 0.25 of the pi/2 Rabi rate. The
  off-resonant branch is then much less under-rotated, which improves the mapping
  contrast |p1 − p0|.

### Choosing tau: `tau = k/(2·df)` with odd k

- The parity condition is "relative phase = π mod 2π". Any **odd** k satisfies it with
  identical mapping contrast (in the symmetric scheme the orientation alternates with
  k mod 4, see above).
- k = 1 is shortest (least T2 decay, and T2* is worst at maximum charge sensitivity),
  but it requires the pulses to fit inside tau.
- Raising k to the next odd value relaxes the timing without changing σ or df.
- Even k puts the branches back in phase and gives zero contrast. The run rejects even
  or non-positive k.
- `ramsey_tau_us` is the programmed delay. `cfg["df"]` always stays the physical
  branch splitting in the saved record.

### tau is centre-to-centre: the 4σ / 8σ feasibility

tau is the **pulse-centre-to-pulse-centre** precession time. QICK schedules waits
between pulse **edges**: `sync_all()` moves the reference to the end of the envelope.
So the programmed gap is:

- no pi: `gap = tau − 4σ` (centres are gap + 4σ apart);
- echo: `gap = (tau − 8σ)/2` per gap.

In general, centre-to-centre = n_gaps · (gap + 4σ).

If `gap ≤ 0` the program raises. The largest usable splitting is therefore
`df_max = 1/(2 · n_gaps · 4σ)`:

- no pi: **df_max = 1/(8σ)**, e.g. 1.25 MHz at σ = 0.1 µs, 0.57 MHz at σ = 0.22 µs;
- echo: **df_max = 1/(16σ)**.

The realised centre-to-centre time after tProc-cycle quantisation is saved as
`effective_tau_us`, next to the requested `tau_us`.

History: until 2026-07-28 the program wrote tau itself as the edge gap. The realised
interval was then tau + 4σ (+8σ with echo): 1.4π instead of π at σ = 0.1 µs,
df = 0.5 MHz (contrast 0.66), and 1.8π at df = 1.0 (contrast 0.095). The error was
worst exactly when the doublet was best resolved.

### Drive bandwidth: `0.0997/σ`

- A 4σ gaussian pi/2 pulse has a peak Rabi frequency of Ω0/2π ≈ **0.0997/σ MHz**
  (σ in µs). This is the constant the code uses; it is the area of an
  *untruncated* Gaussian (1/(4·√(2π)) ≈ 0.0997). QICK's envelope is cut at ±2σ and
  not offset-subtracted, which leaves 95.4 % of that area, so the exact value is
  ≈ 0.1045/σ MHz. The code therefore overstates the bandwidth ratio by ~5 %
  (conservative); the CSTQ03 numbers below use the code constant.
- Bandwidth ratio = (largest branch detuning) / (pi/2 Rabi rate). The largest branch
  detuning is df in the standard scheme and df/2 in the symmetric scheme.
- Ratio > `max_drive_bandwidth_ratio` (default 1.0): the program raises, because the
  off-resonant branch is barely rotated and the mapping cannot be realised.
- Ratio between 0.2 and the limit: the program warns.
- The saved `drive_bandwidth_ratio` tells you how degraded a record is.
- Raise the limit only deliberately, and treat such a record as degraded.

### Echo is a null only for short pulses

`use_pi_pulse=True` inserts a Hahn echo, which refocuses the static detuning df, i.e.
exactly the parity phase. Use it only as a negative control (`echo_null`). Its parity
contrast is zero only for pulses short against 1/df: with finite pulses the branch
detuning also acts during the pulses, and the echo pi, detuned from at least one branch,
rotates the two branches differently. It is then itself parity-dependent, and the echo
can keep most of the contrast, or more than the measurement has.

`predict_parity_mapping` (in `qicklab.experiments.modified_ramsey`) gives the predicted
P(e|upper), P(e|lower) and contrast |P(e|upper) − P(e|lower)| of the programmed sequence
for an ideal two-level qubit:

- nominal 4σ truncated Gaussians, each with its on-resonance area calibrated to π/2 (the
  echo pi: π, phase 0, the same envelope);
- the branch detuning f_branch − f_drive acting during the pulses and the gaps;
- pulses centre-to-centre at tau, with the pi at tau/2;
- the closing phase from the same rule as the program (90° / 180°, + 180° with flip).

It is a piecewise-constant 2×2 propagator, 200 steps per pulse; it agrees with an
independent `solve_ivp` integration to < 10⁻³ (`tests/test_mr_echo_null_prediction.py`).
It has no T2, no readout or thermal error, and no cycle quantisation, so it overstates
|P(e|upper) − P(e|lower)|. The absolute branch labels assume the phase convention of the
table above, including its k mod 4 rule for the symmetric scheme (at k = 3 the predicted
upper branch maps to |g>); the contrast does not depend on it.

At df = 2.7 MHz (CSTQ03 Q2), symmetric scheme:

| σ (µs) | k | main contrast | echo contrast | (echo / main)² |
|---|---|---|---|---|
| 0.1 | 5 | 0.732 | 0.641 | 0.77 |
| 0.0739 | 5 | 0.859 | 0.450 | 0.27 |
| 0.05 | 5 | 0.938 | 0.217 | 0.054 |
| 0.04 | 3 | 0.960 | 0.063 | 0.004 |

In the standard scheme at σ = 0.1 µs, k = 5 the echo keeps 0.884 against a main contrast
of 0.127: it is more parity-sensitive than the measurement.

`build_control_variants` stores the prediction for every control (in its cfg, so in its
h5 `config` and json): `mr_predicted_p_e_upper`, `mr_predicted_p_e_lower`,
`mr_predicted_contrast` (`drive_off`: 0). For `echo_null` it also stores
`mr_predicted_residual_ratio` (echo contrast / the parity run's predicted contrast) and
`mr_null_control_valid`. When the ratio exceeds `ECHO_NULL_MAX_PREDICTED_RESIDUAL_RATIO`
= 0.2, the echo is **"not a null at these settings"**: it is still acquired, but
`compare_parity_controls` excludes it from the decisive checks, with the reason. The limit
is deliberately strict. The lag-covariance statistic scales as contrast², so a ratio of
0.2 lets a genuine parity telegraph leave ≈ 0.04 in the echo, a sixth of the 0.25
decision threshold; the margin covers what the model leaves out (an echo dephases less
than the Ramsey, so the real ratio can be larger than predicted). The cost: σ = 0.05 µs,
k = 5 (ratio 0.23) is also excluded. Beyond the controls, the prediction of the parity
sequence only seeds the HMM's mapping fit (`predicted_mapping_seed`, see
[Analysis](#analysis)); the fitted mapping, not the prediction, enters the emission gate.

## Pulse sequence

Per rep (`reps = mr_reps`, `rounds = 1`):

```
            [active reset × reset_cycles]   (optional, see active_reset.md)
qubit_ch    ─[pi/2, φ=0]─── gap ───[pi/2, φ_close]─ 0.05 µs ─┐
                  │<─────── tau (centre-to-centre) ──────>│     │
res_ch                                                          [ readout tone ]── mr_relax_delay ──▶ next rep
ADC                                                               [ window ]

echo control (use_pi_pulse):
qubit_ch    ─[pi/2]─ gap ─[pi, φ=0]─ gap ─[pi/2, φ_close]─ …      gap = (tau − 8σ)/2
```

- Channels: `qubit_ch` (all pulses share one 4σ gaussian envelope; gains `pi2_gain`,
  `pi_gain`), `res_ch`, `ro_chs[0]`.
- No trigger pin.
- All qubit pulses, including the reset pi, play at the **drive** frequency.
- Readout window: regime-A window (CSTQ03: `readout_length` 15 µs, `adc_trig_offset`
  0.3 µs), with the cross-clock tone extension of
  [single_shot](single_shot.md#pulse-sequence). There is no MR-specific window knob.
- `mr_relax_delay` follows the final readout. It is deliberately separate from
  `relax_delay`, which other steps sharing the config use, so a long spectroscopy
  `relax_delay` cannot silently slow this loop.
- Reads per rep = `reset_cycles + 1`. The final read is the Ramsey readout; earlier
  reads are reset readouts, saved separately.

## How to run

Runs in **regime A**. `df`, `f_upper_mhz` and the mapping probabilities come from the
device file (`Qubit.parity`).

```python
# devices/CSTQ03.py  (example values: CSTQ03 Q2 doublet measured 2026-08-04)
Qubit(..., parity=ParityParams(df_mhz=2.7, f_upper_mhz=4186.7, cd_max_mhz=0.682,
                               cd_period_mv=4.37))
# runners/session.py
PLAN = [
    R.active_reset_verify(),                     # validate the reset first
    R.modified_ramsey(tau_harmonic_k=5, symmetric_ramsey=True,
                      mr_relax_delay=250.0, mr_reps=100_000,
                      validation_controls=("flip_final_pi2", "echo_null")),
]
```

Hardware-free feasibility check before a cooldown: `plan_parity_mapping(df_mhz,
sigma_us, use_pi_pulse=..., symmetric_ramsey=..., tau_us=...)` returns `feasible`,
`errors`, `tau_us`, `gap_us`, `df_max_mhz`, `rabi_pi2_mhz`, `bandwidth_ratio`,
`final_pi2_phase_deg`, `predicted_mapping` (see
[the echo null](#echo-is-a-null-only-for-short-pulses); None without a gap), …. It uses
**nominal** 4σ envelopes; the program reports the quantised values.

What one run does:

1. If `use_active_reset`: calibrate the reset readout (rotates `res_phase`).
2. Run the SingleShot g/e calibration (`ss_calib_shots`).
3. Repeat for `num_cycles` cycles. Each cycle:
   - recalibrates the separator every `ss_recalib_every_n_cycles` cycles;
   - acquires the record;
   - runs the continuous analysis (if `parity_analysis_enabled`);
   - every `validation_controls_every_n_cycles` cycles, acquires and saves each
     control, and analyses it if `parity_analysis_enabled` (see
     [validation controls](#validation-controls));
   - writes the legacy threshold diagnostics.
4. The run **never moves the yoko**. The voltage is read once, for provenance only.

## Parameters

Legacy `ModifiedRamsey_params` keys. Defaults are the CSTQ03 runner values for the
2026-10-01 cooldown; code fallbacks are noted where they differ. Device-dependent
keys (`df`, `f_ge`, mapping probabilities) resolve from the device in qicklab.

| Key | Default | Units | Meaning |
|---|---|---|---|
| `df` | 1 | MHz | Physical parity-branch splitting. Must be measured independently. Sets tau. |
| `f_ge` | 3754.5 | MHz | **Upper** parity branch. Required with `symmetric_ramsey`. |
| `require_f_ge_near_qubit` | False (code fallback) | bool | Raise, instead of warning, when `f_ge − df/2` is off the `Qubit_Pulse` frequency (see [f_ge must sit on the pulsed qubit](#f_ge-must-sit-on-the-pulsed-qubit)). |
| `f_ge_measured_at_V` | None (code fallback) | V | Bias at which df and f_ge were measured. Saved in the record config when set; a different current bias only warns. |
| `tau_harmonic_k` | 1 | odd int | tau = k/(2·df). Use the smallest feasible odd k (see feasibility). |
| `symmetric_ramsey` | True | bool | Drive at the midpoint, closing phase 90°. Code fallback False. |
| `flip_final_pi2` | False | bool | +180° on the closing pi/2 (swaps the mapping). |
| `use_pi_pulse` | False | bool | Hahn echo: null control only. |
| `max_drive_bandwidth_ratio` | 1.4 | ratio | Ceiling on detuning / pi/2 Rabi. Code fallback 1.0. |
| `mr_relax_delay` | 500.0 | µs | Wait after the final readout. ≥ 5·T1 (see findings). Code fallback 0. |
| `mr_reps` → `reps` | 50000 | shots | Shots per record (one cycle). |
| `num_cycles` | 1000 | count | Records per run. |
| `use_apriori_separator` | True | bool | Calibrate g/e with SingleShot. Effectively required. |
| `ss_calib_shots` | 1000 | shots | Shots per separator calibration. |
| `ss_recalib_every_n_cycles` | 10 | cycles | Separator recalibration cadence. |
| `use_active_reset` | True | bool | Per-shot hardware reset; see [active_reset](active_reset.md). Code fallback False. |
| `readout_threshold` | None | normalised I | Manual reset threshold. None = derived from the current separator. |
| `reset_cycles` | 1 | count | Reset rounds per shot. |
| `reset_ground_below_threshold` | True | bool | Overwritten by the derived threshold. |
| `reset_readout_relax_delay` | 5.0 | µs | ≥ ~6/κ. Code fallback 1.0. |
| `reset_read_latency_us` | 0.5 (code fallback) | µs | Stall before the reset `read`; floor 0.5, `reset_readout_relax_delay` must exceed it by ≥ 0.2. Forwarded only when set. See [active_reset](active_reset.md#read-latency). |
| `post_reset_wait` | 0.0 | µs | Settle time after reset. |
| `parity_analysis_enabled` | False | bool | Run the HMM/ACF/PSD analysis per cycle (record and controls). Controls are acquired either way. Code fallback True. |
| `expected_parity_dwell_ms` | 2.5 | ms | HMM initial rate (1/dwell). Also sets the drift-window safety check. |
| `drift_window_ms` | 200.0 | ms | Rolling-mean drift window (≥ 20× dwell). |
| `hmm_symmetric` | True | bool | Fit one symmetric rate. |
| `hmm_bootstrap_samples` | 0 | count | Parametric bootstrap for rate CIs. |
| `hmm_fit_mapping` | True (code fallback) | bool | Fit P(e) of each parity state jointly with the rate (record and controls). False: fixed at `mapping_p_e_state0/1`. `hmm_kwargs["fit_mapping"]`, if set, overrides it. |
| `mapping_p_e_state0` / `mapping_p_e_state1` | 0.1 / 0.9 | prob. | Fixed P(e) for each parity state with `hmm_fit_mapping=False`; otherwise the seed when the mapping is calibrated, or the fallback seed when the predicted one is unavailable. |
| `mapping_probabilities_calibrated` | False | bool | True: the values above are a calibration (they seed the fit instead of the prediction). False with `hmm_fit_mapping=False` adds an explicit warning. |
| `hmm_min_emission_snr` | None (→ 0.7) | ratio | Per-sample emission gate, at the fitted mapping. **Do not lower** (see findings). |
| `hmm_kwargs` | None | dict | Other `fit_two_state_hmm` kwargs (e.g. `min_transitions`, `max_mixing`). |
| `validation_controls` | ["flip_final_pi2", "echo_null"] | list | Controls to interleave. Acquired whether or not `parity_analysis_enabled`. |
| `validation_controls_every_n_cycles` | 10 | cycles | Control cadence. |
| `control_tau_offset_frac` | None (→ predicted null) | fraction | `tau_offset` control: None sets the predicted null next to the programmed k/(2·df): the even harmonic (k+1)/(2·df) in the standard scheme, the solved zero a few % below it in the symmetric one (see [controls](#analysis)); a fraction f sets the programmed tau × (1 + f). Code fallback None. |
| `control_detuning_mhz` | None (→ +df) | MHz | `drive_detuned` control (+df: an inverted mapping; with active reset decisive only when the reset pi still works at the detuned drive, see [controls](#analysis)). |
| `average_n_shots` | 50 | shots | Legacy hard-threshold plot only. Code fallback 25. |

The program also reads `sigma`, `pi2_gain`, `pi_gain`, `flattop_length` (must be
None), `readout_length`, `adc_trig_offset`, `res_phase`, `pulse_freq`, `pulse_gain`,
`rounds` (must be 1), and the optional `ramsey_drive_freq_mhz`.

## Outputs

Per cycle:

- **`ModifiedRamsey/ModifiedRamsey_<date>/…_data.h5`**, from `ExperimentClass`:
  - per-shot record and time base: `shots_i`, `shots_q` (unthresholded, normalised),
    `shot_index`, `shot_time_us`, `scheduled_rep_period_us`, `gap_indices` (empty);
  - tau and pulse: `tau_us`, `effective_tau_us`, `wait_us`, `qubit_pulse_us`,
    `sigma_us`, `drive_bandwidth_ratio`;
  - branches and drive: `f_ge`, `f_branch_upper`, `f_branch_lower`, `df`,
    `drive_freq`, `pi2_gain`, `pi_gain`, `first_pi2_phase_deg`,
    `final_pi2_phase_deg`, `use_pi_pulse`, `flip_final_pi2`, `symmetric_ramsey`,
    `mr_control_type_code`;
  - readout: `read_pulse_freq`, `read_pulse_gain`, `res_phase`,
    `readout_length_us`, `readout_window_us`, `adc_trig_offset_us`,
    `mr_relax_delay_us`;
  - reset: `use_active_reset`, `reset_cycles`, `reset_shots_i/q`,
    `readout_threshold`, `reset_ground_below_threshold`,
    `reset_readout_relax_delay_us`, `post_reset_wait_us`;
  - throughput diagnostics: `streamer_elapsed_s`, `streamer_average_rep_period_us`.
- **png** `…_IQ.png` and **json** (the cfg, including `modified_ramsey_timing` and,
  for controls, the string `mr_control_type`, plus `mr_parent_record` (the parent
  record's h5 path) and `mr_parent_cycle_idx`).
- **Analysis files** in `<outer>/ModifiedRamsey/<YYYY_MM_DD>/` with base
  `Cycle_<nnn>_MR_<ts>`:
  - `_continuous_analysis.json` (summary, plus `acf` with the fit values, `r1` and
    `lag_covariance_sum` with its bootstrap, `readout_separation` (the true-state
    separation of the clean clouds when the mixture fit is resolved, else the raw
    labelled-set separation, still shrunk by the SingleShot e purity),
    `readout_separation_source` (`clean_cloud_source`) and `readout_prep_e_predicted`
    (the SingleShot pi's predicted e purity at this record's branches,
    `predicted_singleshot_prep`; None for a flat-top pulse), `psd`,
    `rate_vs_bin`, ...; modified_ramsey_control compares its null with the newest of
    these) and `_continuous_analysis.h5` (`v_projected`, `v_corrected`, `drift`, `t_s`,
    `posterior_state1`, `viterbi_path`, summary attrs);
  - plots `_continuous_{calibration,projected_trace,hmm,acf_psd,rate_vs_bin,dwells,reset_success}.png`;
  - per control, the same files with `_<control>`; plus `_control_comparison.json`
    (analysis on) or `_controls_index.json` (analysis off: `cycle_idx`,
    `parent_record`, `controls` = control type → h5 path, `skipped` with reasons);
  - legacy diagnostics: `_iq_labeled_apriori.png`, `_single_shot_binary.png`,
    `_averaged_population.png`, `.npz`, `_config.json`, `_provenance.json`
    ([provenance](../architecture.md#provenance); the `_analysis.json` sidecars carry a
    `provenance` key for the analysis run);
  - one `CycleSummary_<ts>.json` per run.
- Control records go to `ModifiedRamsey_Controls/` (h5, `_IQ.png`, json).
- **The fitted rates are saved only in the analysis sidecars and the cycle summary.**
  They are not in the raw h5.

The h5 stores the control type as a numeric code: `parity` 0, `flip_final_pi2` 1,
`echo_null` 2, `tau_offset` 3, `drive_detuned` 4, `drive_off` 5.

## Analysis

Primary inference uses **every unthresholded IQ sample**. The threshold plots are
diagnostics only.

1. **Readout calibration** from the labelled SingleShot g/e shots:
   - LDA axis, CDF-gap threshold, confusion matrix;
   - contrast C and `assignment_fidelity = (1+C)/2`, analog SNR.
   - Warnings: analog SNR < 1, contrast < 0.3, < 500 labelled shots per class.
   - **Clean clouds.** The pi pulse of the SingleShot calibration plays at the
     doublet centre, df/2 from both parity branches, so at a bandwidth-limited σ
     part of the "e" shots stay in g (Bloch estimate: P(e) ≈ 0.51 at σ = 0.1 µs,
     ≈ 0.90 at σ = 0.04 µs for df = 2.7 MHz). Their moments put `proj_e_mean`
     toward g, inflate `proj_e_sigma` and understate `snr_analog` (true SNR 2 with
     half the e shots in g reads ≈ 0.8). A joint two-Gaussian mixture fit of both
     projected labelled sets (shared component means and sigmas, σ_e/σ_g in
     [0.8, 1.25], one e weight per set) gives `proj_{g,e}_{mean,sigma}_clean`,
     `snr_analog_clean`, the e-cloud purity `prep_fidelity_e` and the g set's e
     weight `prep_excited_g`. The purity counts pi-pulse error **and** decay during
     readout (the MR readout has the same tail), not prep error alone. The mixture
     is used only when it raises the joint log-likelihood by 2ΔlnL ≥ 9
     (`mixture_2dlnl`) over the pure fit, which uses each set's own raw moments with
     no bound on σ_e/σ_g (so a pure but wider or narrower e cloud is not mistaken
     for a mixture, and `mixture_2dlnl` can be negative); otherwise the clean clouds
     are the moments (`clean_cloud_source` = `moments`). An e weight < 0.2 or a clean SNR < 1 falls
     back to the moments with a warning (`moments_fallback`). A purity < 0.9 warns.
     The raw keys (`proj_*`, `snr_analog`, contrast, threshold, confusion matrix)
     keep their meaning; the reset threshold and `rate_vs_bin_size` do not use the
     clean clouds.
2. **Projection** onto the calibrated axis, giving an analog trace v(t). The time
   base is the emitted-schedule rep period.
3. **Drift removal.** A centred rolling **mean** over `drift_window_ms`. A rolling
   median would track the majority state and eat the telegraph. The default 0.2 s is
   80× a 2.5 ms dwell; a window < 20× dwell is flagged unsafe.
4. **Two-state HMM.** Log-space forward-backward with exact `expm(Q·dt)` transitions.
   - Each parity state emits a calibrated g/e **mixture** with weights
     `p_e_state0/1`.
   - The weights `p_e_state0/1` are **fitted** with the rate (`hmm_fit_mapping`,
     default True; `fit_two_state_hmm(fit_mapping=True)`), as logits bounded to ±8,
     with the readout clouds (`mu_g`, `mu_e`, `sigma_g`, `sigma_e`) fixed at the
     SingleShot calibration. A fixed wrong mapping biases the rate: a record with
     real contrast 0.5 analysed with (0.1, 0.9) reads several times fast with a
     small error bar, or is withheld as unresolved (`tests/test_hmm_fit_mapping.py`).
     The rate error comes from the Hessian over the rate and the mapping logits, so
     it carries the mapping uncertainty (a logit at its bound, P(e) within 3·10⁻⁴ of
     0 or 1, is held fixed). The summary, `_analysis.json` and `_analysis.h5`
     attributes report the fitted `mapping_p_e_state0_fit/1_fit`, their errors, the
     `emission_snr` the gate saw (`emission_snr_seed` at the seed), the free-P(e)
     i.i.d. null's `iid_p_e`, and `mapping_seed_source` (`predicted`,
     `fallback: <why>`, `calibrated`, or `assumed` for a fixed mapping);
     `mapping_p_e_state0/1` are the seed. The fit costs about 3× a rate-only fit
     (≈ 3 s at 5·10⁴ shots); with `hmm_bootstrap_samples` every resample refits the
     mapping too.
   - Seed: the predicted mapping of the parity sequence (`predicted_mapping_seed`,
     from `plan_parity_mapping`), in ascending order, so `state1` is the state with
     the larger P(e), as in the (0.1, 0.9) default. It falls back to
     `mapping_p_e_state0/1` when the plan is infeasible or the predicted contrast is
     below `MAPPING_SEED_MIN_PREDICTED_CONTRAST` = 0.1; a calibrated mapping
     (`mapping_probabilities_calibrated=True`) is the seed instead. The controls of a
     cycle reuse the parity record's seed and fit their own mapping; since the seed
     order fixes the labels (a fit that converges swapped is relabelled), `state1` is
     the larger-P(e) state in every record, which the `flip_final_pi2` occupancy
     inversion relies on.
   - With `hmm_fit_mapping=False` (or `hmm_kwargs={"fit_mapping": False}`, which
     takes precedence in the run as in the analysis) the weights are fixed at
     `mapping_p_e_state0/1` (default 0.1/0.9), never at the prediction. Unless `mapping_probabilities_calibrated`, every rate is then
     conditional on an assumption, and a warning says so; g/e readout fidelity alone
     does not calibrate them.
   - State labels are neutral (`state0`/`state1`): mapping them to even/odd charge
     parity needs physics input the analysis does not have.
   - The readout clouds are fixed during the fit (refitting them would absorb drift).
     They are the **clean** clouds of step 1 when the mapping is fitted or
     calibrated, the raw moments when it is a fixed assumption
     (`analyze_modified_ramsey_record(clean_readout_clouds=None)`; True or False
     forces it, and clean clouds with an assumed fixed mapping warn, since they
     raise the emission SNR the gate sees while the assumed p's carry the same
     bandwidth loss). The summary and `_analysis.json` record `readout_clouds`
     (`clean`/`raw`), `snr_analog_clean`, `prep_fidelity_e`, `prep_excited_g` and
     `clean_cloud_source`; `snr_analog` stays the raw number.
   - Symmetric rate by default: charge parity has no preferred branch.
   - The initial rate is 1/`expected_parity_dwell_ms`. The documented BFC operating
     point is a 2–3 ms dwell; 2.5 ms corresponds to γ = 200 Hz.
   - **Identifiability gates.** All must pass, otherwise rates are NaN with reasons:
     - per-sample emission SNR ≥ `min_emission_snr` (0.7), at the fitted mapping
       (`emission_snr`; at the seed `emission_snr_seed`). It is checked after the fit,
       and the other gates are still evaluated and reported. A record whose fitted
       contrast is too low for the readout SNR is withheld here even though the seed
       would pass;
     - expected transitions ≥ 10;
     - log-likelihood gain over a single Gaussian ≥ 10 (`delta_loglik`). This only
       shows the readout is bimodal: uncorrelated g/e shots pass it by thousands;
     - log-likelihood gain over the **i.i.d. mixture** with the same emissions ≥ 10
       (`delta_loglik_iid`, `loglik_iid`). The null draws every shot independently
       from state 0 or 1 with the best-fit weight `iid_weight_state1`, so it has
       the same readout but no temporal correlation. The weight is free even for
       a symmetric fit: P(e) ≠ 1/2 (T1 decay during τ, a mapping offset) would
       otherwise let the symmetric HMM beat a 1/2 null without any switching.
       With `fit_emissions=True` the null refits its own means and sigmas too; with
       the mapping fitted, the null is the g/e mixture with its own free P(e)
       (`iid_p_e`), the i.i.d. limit over every mapping.
       This is the evidence for switching: uncorrelated shots, an ideal
       `echo_null`, or a dephased record (T2 ≪ τ, unresolved df) give ≈ 0–1 or
       less (the gain is negative when a symmetric HMM is misspecified), a
       resolved telegraph gives tens to thousands;
     - switching resolved at the cadence: `(γ01 + γ10)·median(dt)` ≤ `max_mixing`
       (1.0; reported as `mixing_per_step`). Above it the state decorrelates
       between samples and the rate is indistinguishable from uncorrelated shots;
     - fitted rate not pinned at the fit bounds (1e-2 to 1e6 Hz).
   - Posterior ambiguity > 0.25 warns: do not trust individual Viterbi samples. That
     does not mean the rate is wrong.
   - A clean-looking Viterbi trace is **not** evidence of switching. The gates are.
5. **HMM-independent estimates.**
   - ACF: an exponential fit with lag 0 excluded (lag 0 holds readout-noise
     variance).
   - Welch PSD: a Lorentzian corner.
   - Warnings: ACF noise variance > 4× telegraph amplitude; PSD plateau < 3× white
     floor.
6. **Rate conventions** (symmetric rate γ per state):
   - τ_dwell = 1/γ;
   - ACF ∝ e^(−2γt), so τ_corr = 1/(2γ);
   - PSD corner f_c = γ/π.
   - With asymmetric rates, the ACF and PSD see γ_eff = (γ01 + γ10)/2.
   - If the HMM and the ACF or PSD disagree by > 3×, the record is flagged: at least
     one estimator is not measuring parity.
7. **Rate vs bin size.** A falling rate means noise crossings; a plateau means real
   switching. The rate is n_switches / ((n_bins − 1)·b·dt), the same estimator the
   Undriven bin sweep uses.
8. **Reset readouts.** Pre-correction ground fraction per reset row (see
   [active_reset](active_reset.md#reset-readout-k-is-taken-before-flip-k)).
9. **Controls** (`build_control_variants` + `compare_parity_controls`). Controls
   share the voltage, calibration, time base and emission model with the parity
   record, and must use the **same HMM gate**; otherwise they are not controls.

| Control | Change | Expected signature | Decision |
|---|---|---|---|
| `flip_final_pi2` | +180° closing phase | Telegraph amplitude and rates unchanged; occupancy inverted | Fails unless ACF amplitude ratio > 0.25 **and** the effective HMM rate (γ01 + γ10)/2 agrees with the parity record's (a rate fails only if it differs by more than 3 combined 1σ errors **and** by more than a factor 2, so ordinary drift between the two records is tolerated; when the HMM reports no finite rate errors, the factor-2 rule decides alone). Then, if \|occ1_main − 0.5\| > 0.15: passes when \|occ1_flip − (1 − occ1_main)\| < 0.15, else fails; if \|occ1_main − 0.5\| ≤ 0.15: "inversion uninformative" (not decisive) |
| `echo_null` | `use_pi_pulse=True` | Contrast suppressed (echo refocuses df), only for short pulses | Passes if the control HMM is unidentifiable by its i.i.d. gate, **or** the lag-covariance ratio's 95% upper bound < 0.25. Fails regardless when the ratio's 5% lower bound is ≥ 0.25 (the telegraph survived). When its control dict carries `null_control_valid=False` (predicted to keep > 0.2× the parity contrast, see [the echo null](#echo-is-a-null-only-for-short-pulses)): "not a null at these settings" (not decisive) |
| `tau_offset` | default: the predicted null next to the programmed k/(2·df), i.e. the even harmonic (k+1)/(2·df) (standard scheme) or the solved zero of the predicted contrast a few % below it (symmetric scheme); or programmed tau × (1 + `control_tau_offset_frac`) | Both branches end in the same state, contrast suppressed (a null) | When its control dict carries `null_control_valid=True` (predicted to keep ≤ 0.2× the parity contrast): judged as `echo_null` (i.i.d. HMM gate or lag-covariance ratio 95% upper bound < 0.25; fails when the 5% lower bound is ≥ 0.25). Otherwise informational |
| `drive_detuned` | drive + detuning (default +df), bandwidth limit lifted | +df adds a common phase 2π·df·tau = kπ (k odd): mapping **inverted** at about full contrast, a second flip control, not a null | When its control dict carries `inverted_mapping_expected=True` (predicted contrast ≤ −0.8× the parity run's and, with `use_active_reset`, the reset pi at the detuned drive predicted to flip each branch with ≥ 0.95): judged as `flip_final_pi2` (survival, rate, occupancy inversion). Otherwise informational |
| `drive_off` | `pi2_gain = 0` | Readout/thermal baseline, no parity information | Passes if the lag-covariance ratio's 95% upper bound < 0.1; fails if its 5% lower bound is ≥ 0.1 (inter-shot carryover / readout correlation contaminates the parity record); when the interval straddles 0.1, "inconclusive" (not decisive: acquire more shots), whichever side the point estimate is on. When both records carry the lag statistic but no ratio can be formed (the parity record's own lag sum is not significantly > 0: weak contrast or short record), also "inconclusive". Only when the lag statistic is absent does the ACF amplitude ratio decide, by its point value: < 0.1 passes, ≥ 0.1 fails (no CI, so a noisy record can fail by chance); with neither available, "inconclusive" (not decisive) |

The **lag-covariance ratio** is model-free. For each record, `analyze_modified_ramsey_record`
stores `acf["lag_covariance_sum"]`: the autocovariance of the drift-corrected trace summed
over lags 1..K, with K = ceil(`expected_parity_dwell_ms` / dt). Lag 0, the readout-noise
variance, is excluded, so uncorrelated shots of any P(e) give ≈ 0. It is computed on the
interior of the trace, half a drift window (`edge_trim_samples` = W/2) away from either
end: the rolling-mean drift estimate repeats the end samples there, and that common ramp
biased the full-trace sum upward (a clean drive_off whose first and last shots read
2.5σ above the e mean reached 0.7× a weak parity record's sum). The full trace is used
only when the interior is too short. Subtracting the rolling mean also puts a flat
offset of −P/W·(1 + k/W) on every lag k < W/2 (P: the record's autocovariance summed over
all lags, the trace variance for i.i.d. shots), about −var·K/W on the lag sum (−0.013 of
the variance at K = 10, W = 763). That is not small against a weak parity record: at the
CSTQ03 2026-08-04 contrast (normalised ACF amplitude 0.0046) the parity lag sum itself is
only ≈ 0.017 of the variance, and left in, the offset pulls every control's ratio down (a
drive_off at true ratio 0.2 next to an A = 0.02 parity record measured ≈ −0.1 on 10⁵
shots, so it could pass). The offset
is therefore measured in a baseline band of lags 4K..min(8K, W/2 − 1), where a telegraph
of the expected dwell has decayed to < 10⁻³ of its lag-0 value, and removed: K·(1 + (K+1)/(2W)) times the band
mean over (1 + (L1+L2)/(2W)). `value` is the corrected sum, `uncorrected_value` the raw
one, `baseline_lags` the band (None when W is too short for a band of ≥ K lags). Its CI is
a block bootstrap of the baseline-corrected lagged products (so the baseline noise, about
+10 % on the CI width, is included): 1000 resamples of non-overlapping blocks of
max(10K, 2·L2, N/2000) samples, capped at N/20 and at least 2K. The ratio is control / parity, and its
one-sided 95% upper bound comes from the two independent bootstraps. It needs uniform
timing and a parity record whose own lag sum is significantly > 0. At the CSTQ03
2026-08-04 contrast that takes a few 10⁵ shots; resolving the thresholds takes far more.
The bootstrap SD of the corrected sum is ≈ 0.011·var·√(10⁵/N) at K = 10, so a clean
echo_null can pass (95 % upper bound < 0.25) only from about 2·10⁶ shots (≈ 8 min at
262 µs) and a clean drive_off (< 0.1) only from about 10⁷ (≈ 45 min); below that the
drive_off is "inconclusive" and the echo rests on the HMM's i.i.d. gate. An ACF fit failure
alone is never counted as null evidence: the ACF is also skipped for non-uniform timing.
Nor is the HMM's resolved-rate gate ("(γ01 + γ10)·dt > 1"), nor its emission gate: with a
fixed mapping (`hmm_fit_mapping=False`) a partially refocused echo (mapping 0.29/0.71
against 0.1/0.9, lag ratio ≈ 0.3) is mis-modelled, locks onto a fast rate and trips the
resolved-rate gate although the telegraph survived; with the fitted mapping its reduced
contrast trips the emission gate instead. Only the i.i.d. gate counts, and it fires
for every ideal echo null tested (P(e) = 0, 0.03, 0.1, 0.2, 0.5).
Each control entry in `_control_comparison.json` reports `amplitude_ratio`,
`lag_cov_ratio`, `lag_cov_ratio_upper95`, `lag_cov_ratio_lower05`, `checked` (True / False / None = not
decisive), `verdict` and a `note`. The comparison also reports `null_control_valid` (False
when the echo_null was excluded as not a null, True when it was judged, None without
one), `decisive_controls` (the labels that decided) and `notes`: when the echo is
excluded, a note names the decisive checks that remain (possibly none).

`all_expected` is True only if all of the following hold:

- the parity record is identifiable and has a finite ACF amplitude;
- at least one decisive check ran, and none failed;
- no requested control was skipped as infeasible.

For a balanced parity record (the symmetric case), the flip control (and a
`drive_detuned` judged like it) is not decisive, so `echo_null`, `drive_off` and a
predicted-null `tau_offset` carry the verdict. An echo excluded as not a null does not
count: with only flip and echo on a balanced record, no decisive check is left and
`all_expected` is False; on an imbalanced record the flip alone can make it True, and
`null_control_valid = False` says the null did not take part. A run whose only control is `flip_final_pi2`
therefore gets `all_expected = False` on a balanced record.

`tau_offset` and `drive_detuned` are decisive only through their predicted mapping
(`predict_parity_mapping`, see [the echo null](#echo-is-a-null-only-for-short-pulses)),
which `build_control_variants` stores in their cfg:

- `tau_offset` gets `mr_predicted_residual_ratio` and `mr_null_control_valid`, with the
  same 0.2× limit as the echo. In the standard scheme (drive on the upper branch) the
  default tau is the even harmonic (k+1)/(2·df): there both branches end in the same
  state to second order, independent of the pulse model (residual 0.01–0.04× at
  df = 2.7 MHz, σ = 0.04 µs and df = 0.5 MHz, σ = 0.1 µs). In the symmetric scheme the
  finite pulses lengthen the effective phase time, so the even harmonic keeps 0.1–0.45×
  (0.26× at df = 2.7 MHz, σ = 0.04 µs, k = 3; 0.44× at σ = 0.1 µs, k = 5: no null on
  CSTQ03). There the default is the zero of the predicted P(e|upper) − P(e|lower) closest
  to the even harmonic, solved with the propagator: 1–4.4 % below it (0.7109 µs instead of
  0.7407 µs at df = 2.7 MHz, σ = 0.04 µs, k = 3; 1.0623 µs instead of 1.1111 µs at
  σ = 0.1 µs, k = 5), predicted residual < 0.001×. Both are linear zeros in the symmetric
  scheme, so the solved tau is no less robust: a 1 % df error leaves 0.03–0.10× (the
  standard even harmonic: 0.03–0.07×). An explicit `control_tau_offset_frac` applies to
  the programmed tau (not solved for), so it respects k; a 25 % offset at k = 1 keeps
  about 0.7–0.9× of the contrast and is no null.
- `drive_detuned` gets `mr_predicted_contrast_ratio` (signed: control / parity run) and
  `mr_inverted_mapping_expected`, True when the ratio is ≤
  −`DRIVE_DETUNED_MIN_INVERTED_CONTRAST_RATIO` = −0.8 (the ACF amplitude then keeps
  ≥ 0.64×, clear of the 0.25 survival threshold). At +df it is ≈ −0.97 for
  df = 1 MHz, σ = 0.04 µs and df = 0.5 MHz, σ = 0.1 µs. Only bandwidth-starved settings
  break it: at σ = 0.1 µs, df = 2.7 MHz, k = 5, symmetric, the detuned branches cannot be
  rotated and the ratio is +0.05, so it is informational. A custom `control_detuning_mhz`
  adds a common phase 2π·det·tau: odd multiples of π invert, even ones keep the
  mapping, others lose contrast.
  With `use_active_reset` the corrective reset pi also plays at the detuned drive, df and
  2·df from the branches (standard) or 0.5·df and 1.5·df (symmetric), so it can fail and
  leave inter-shot carryover that changes the rate or occupancy for reasons unrelated to
  parity. `build_control_variants` then stores `mr_predicted_reset_pi_transfer`
  (`predict_pi_transfer`: the predicted |e⟩ → |g⟩ probability of the worse branch) and
  keeps the control decisive only when it is ≥ `DRIVE_DETUNED_MIN_RESET_PI_TRANSFER` =
  0.95. At +df that needs short pulses: 0.795 (standard) and 0.880 (symmetric) at
  df = 1 MHz, σ = 0.04 µs, 0.696 at df = 0.5 MHz, σ = 0.1 µs (informational), 0.969 at
  df = 0.5 MHz, σ = 0.04 µs, symmetric (decisive). The informational verdict carries the
  reason (`inverted_mapping_reason`) in its note.

Records without these flags (older or hand-built control dicts) are informational for both. The default `validation_controls` list
does not include `drive_off` yet; add it when the inter-shot reset has to be checked.

The `drive_off` threshold of 0.1 is a contamination budget: at most a tenth of the
parity record's short-lag correlation may come from sources that carry no parity.
Slow readout drift counts as such a source, and it can exceed the budget even with a
complete inter-shot reset. Simulated with the default 200 ms `drift_window_ms` (dt 262 µs,
K = 10, the same τ ≈ 122 ms readout drift in the parity record and the drive_off
record: the CSTQ03 2026-08-04 residual), the baseline-corrected lag-covariance ratio
(`drift_corrected_lag_sum`) comes out at about 0.8–1.2× the ACF amplitude ratio: ≈ 1×
at the CSTQ03 contrast (normalised amplitude 0.0046), ≈ 0.8× against an A = 0.02 parity
record. (The uncorrected sum read about 1.5×; the baseline band takes out roughly half
of the drift residual.) The 200 µs-relax arms of that diagnostic (ACF amplitude ratio
0.25) would therefore sit near 0.2–0.25, about twice the budget, and so would the
250 µs acceptance run if its r(1) ratio of about 0.27 carries over to the lag sum.
Whether that reads "failed" or "inconclusive" depends on the record length: the 5%
lower bound clears 0.1 only once the ratio's bootstrap SD is ≲ 0.06–0.09, about 0.5–1·10⁷ shots
at that contrast. This is a real contamination of the parity record, not a false
alarm, but more relax time will not fix it. Shortening `drift_window_ms` helps less
than the uncorrected sum suggests: at the 50 ms floor (20× a 2.5 ms dwell) the
corrected ratio fell only 1.4–1.8× in the same simulations (the uncorrected residual
fell ≈ 4×, but at short windows the high-passed drift still bends across the 4K..8K
baseline band, so less of it is removed), leaving ≈ 0.12–0.18, still at or above the
budget. The remedy is to remove the drift source.

### Validation controls

On every cycle with `cycle_idx % validation_controls_every_n_cycles == 0` the run
acquires each control in `validation_controls` right after the parity record, with the
same cfg except the control's change. **Acquisition does not depend on
`parity_analysis_enabled`**: that flag only decides whether the record and the
controls are analysed online. A control that `plan_parity_mapping` rejects is skipped
and listed with its reason; a notice is printed when every control was skipped.

- Analysis on: each control is analysed with the parity record's gate and the result
  goes to `_control_comparison.json`.
- Analysis off (the CSTQ03 runner): a notice is printed and `_controls_index.json`
  pairs the controls with the parent record, for offline analysis. Each control's cfg
  also carries `mr_parent_record` and `mr_parent_cycle_idx`.

A non-positive `validation_controls_every_n_cycles` raises ValueError in either case.

### Dwell-count statistics

Rate precision is set by the **number of dwells observed**, not by per-shot fidelity.
At 250 µs relax the rep period is ~262 µs, so a 2.5 ms dwell spans about 9.6 shots:

| Shots | Record | Dwells |
|---|---|---|
| 100,000 | ≈ 26 s | ≈ 10,500 |
| 400,000 | ≈ 105 s | ≈ 42,000 |

For comparison, the old 4.7 s relax-0 record held only 1880 dwells. The streamer
chunks long records transparently.

### Timing ledger

- `modified_ramsey_timing(soccfg, cfg)` is a pure model of the per-rep schedule. It
  includes:
  - tone and ADC quantisation on each clock, and the readout slot =
    max(tone end, ADC end);
  - the 4σ pulse on the generator clock and the tau gap;
  - 0.05 µs final padding and `mr_relax_delay`;
  - the reset block `reset_cycles × (slot + reset_readout_relax_delay + pi) +
    post_reset_wait`.

  It excludes `initialize()`, tProc instruction latency, data transfer and Python
  overhead. The model is saved in the cfg json as `modified_ramsey_timing`.
- The program's `scheduled_rep_period_us()` walks the compiled instruction list
  (each `synci`, plus the wait register per `sync`) and is the time base of
  `shot_time_us` and the analysis.
- Streamer wall-clock stats include polling/transfer latency. They are kept only as
  diagnostics.
- `tests/hardware/verify_modified_ramsey_timing.py` cross-checks model, emitted
  schedule and realised centre-to-centre tau (within 2 tProc cycles).

## Findings & notes

**Timing (2026-07-28, warm RFSoC 192.168.0.103).**

- Board constants: tProc f_time = gen f_fabric = 430.08 MHz; readout f_output =
  307.2 MHz; avg_maxlen 16384; buf_maxlen 1024.
- The centre-to-centre fix was verified 40/40. A/B against the old gap on real
  clocks: parity phase 1.400π → 1.000π at σ = 0.1 µs, df = 0.5 MHz (contrast
  0.655 → 1.000), and 1.879π → 1.000π at σ = 0.22 µs.
- The emitted `synci` ledger matches the model exactly: 7506 cycles bare, 16710 with
  reset ×1, 25914 with reset ×2.
- A live 40,000-rep zero-DAC-gain run (electrically inert) measured a rep period of
  17.4665 µs against 17.4526 µs scheduled (+0.08 %).
- Usable df at σ = 0.1 µs: < 1.2502 MHz (no pi), < 0.6251 MHz (echo).

**CSTQ03 Q2, 2026-08-04: staged hardware validation.**

- Offline suite and timing phase 1 passed (42/42).
- Zero-gain cadence was within 1.2 % of the ledger.
- Analog readout SNR 0.77–1.05. At first the HMM correctly withheld rates ("emission
  separation SNR 0.60 < 0.7").

**CSTQ03 Q2, 2026-08-04: root cause of the spurious kHz "parity" rate.** A 4-arm
diagnostic (analog SNR 0.91) found incomplete inter-shot reset:

| Arm | relax | r(1) | r(10) | ACF amplitude |
|---|---|---|---|---|
| parity | 0 µs | +0.289 | +0.099 | 0.004582 |
| drive_off (pi2_gain = 0) | 0 µs | +0.469 | +0.301 | 0.011050 |
| parity | 200 µs | +0.072 | +0.010 | 0.002301 |
| drive_off | 200 µs | +0.115 | +0.032 | 0.000575 |

- `drive_off` plays no pi/2 pulses and cannot carry parity, yet it showed 2.4× the
  parity ACF amplitude. The correlation is an artifact, and it dominates rather than
  merely contaminates.
- 200 µs of relax collapses it 4× (parity) and 19× (drive_off).
- With `mr_relax_delay = 0` and no active reset, the readout collapses the qubit but
  never returns it to |g>. With T1 ≈ 50 µs, the carryover is exp(−11.75/50) = 79 %
  at relax 0, exp(−211.75/50) = 1.4 % at relax 200 µs, and 0.5 % at 250 µs = 5·T1.
- The residual r(1) ≈ 0.07–0.12 in the 200 µs arms is slow readout drift (ACF
  τ ≈ 122 ms), not T1.
- Cost of the long relax: the rep becomes ~262 µs, so a 2.5 ms dwell is sampled ~9.6×
  instead of ~213×, and the per-dwell SNR drops from ~8.8 to ~2.3. Compensate with
  many dwells (more shots), **not** with a lower HMM gate.
- Lab record, not in code: the acceptance run at 250 µs relax gave r(1) +0.289 →
  +0.011 (parity) and +0.469 → +0.003 (drive_off).

**`hmm_min_emission_snr`: DO NOT lower (CSTQ03 Q2, 2026-08-04).**

- History (2026-08-04): the mapping was then fixed at the **assumed** (0.1, 0.9), and
  the gate, the per-sample separation of the two states' g/e mixtures (≈
  `analog_snr × |p1 − p0|`), came out at ≈ 0.60–0.62 < 0.7 at the measured analog
  SNR ≈ 0.77, so the HMM withheld rates. That SNR came from the raw moments of the
  doublet-centre pi pulse at σ = 0.1 µs, df = 2.7 MHz, where about half the "e" shots
  are predicted to stay in g; a true SNR of 2 then reads ≈ 0.8, so the low readout SNR
  may be a calibration artifact. The emissions now use the clean clouds (step 1 of the
  analysis); re-analysing the saved `SingleShot_MRCalib` h5 files of 2026-08 for
  `prep_fidelity_e` and `snr_analog_clean` would confirm or rule this out (not yet
  done).
- Now: the mapping is fitted (`hmm_fit_mapping`, default True) and the gate uses
  the **fitted** probabilities; the threshold stays 0.7. That is at least as strict
  as the old gate whenever the **fitted** contrast |p1 − p0| is below 0.8, and more
  lenient above it: at analog SNR 0.77 a record passes only with a fitted contrast
  above ≈ 0.92 (symmetric mapping).
- With the gate lowered to 0.3, the HMM returned a confident-looking 4921 ± 68 Hz,
  while ACF gave 9606 Hz and PSD 15056 Hz (> 3×, auto-flagged). The `echo_null`
  control retained 44 % of the parity ACF amplitude. (This was read at the time as
  proof that the correlation is not parity, because the echo "cannot contain parity
  contrast". That premise is wrong at σ = 0.1 µs, df = 2.7 MHz: the finite-pulse echo
  is predicted to keep 0.77 of the parity ACF amplitude in the symmetric scheme, see
  [the echo null](#echo-is-a-null-only-for-short-pulses). The echo does not decide
  the question at these settings; the HMM / ACF / PSD disagreement and the drive_off
  diagnostic do.)
- So the fit had locked onto a ~50–200 µs shot-to-shot correlation that is not
  charge parity. 0.7 correctly withheld the number.
- History: an older code comment advised lowering the gate for oversampled
  telegraphs (~213 samples/dwell at an 11.75 µs rep). That advice is contradicted by
  this measurement and no longer applies.

**df, bandwidth and the unresolved σ/df limit (CSTQ03 Q2, 2026-08-04).**

- **Measured branches:** 4186.7 MHz (top) and 4184.0 MHz (bottom), so df = 2.7 MHz
  and the midpoint is 4185.35 MHz. This is 4× the `cd_max_mhz = 0.682` of the
  device's charge-dispersion fit (see [modified_ramsey_control](modified_ramsey_control.md)).
  Either that fit is stale, or this doublet is not charge parity. Confirm it before
  trusting `expected_parity_dwell_ms`.
- **Timing at df = 2.7, σ = 0.1 µs** (solved with odd k):
  - k = 1: tau = 0.185 µs, infeasible (the two pi/2 envelopes span 4σ = 0.4 µs; the
    program raises).
  - k = 3: tau = 0.5556 µs, gap 0.156 µs, realised phase 3.0008π, mapping contrast
    1.000. But echo_null needs tau > 8σ = 0.80 µs, so it is skipped, and that forces
    `all_expected = False`.
  - k = 5: tau = 0.9259 µs, echo gap 0.063 µs, phase 4.997π. The echo is feasible,
    but at σ = 0.1 µs it is not a null: it keeps 0.641 contrast against the main 0.732
    (symmetric), so `build_control_variants` marks it "not a null at these settings".
    The echo becomes a usable null only at shorter σ (σ = 0.04 µs, k = 3: 0.063
    against 0.960; see [the echo null](#echo-is-a-null-only-for-short-pulses)).
- **Bandwidth (UNRESOLVED):**
  - The pi/2 Rabi rate is 0.0997/0.1 = 0.997 MHz. The symmetric detuning df/2 =
    1.35 MHz gives a ratio of 1.354 (standard: 2.708). The mapping contrast is
    degraded **independent of tau**; no choice of k fixes it.
  - A ratio ≤ 1 needs σ ≤ 0.0739 µs (symmetric) or 0.0369 µs (standard).
  - The pi/2 pulse sits at 3.7 % of DAC full scale. Halving σ (gain ∝ 1/σ, about
    2400, 7.3 % FS) has headroom.
  - `max_drive_bandwidth_ratio = 1.4` lets the run proceed under protest. Return it
    to 1.0 once σ allows.
- Lab record, not in code: a randomised tau sweep (0.42–4.75 µs, 62 points, 10,000
  shots each, interleaved drive_off baselines) found no parity contrast at any tau
  and any df up to 6 MHz. The parity r(1) excess was +0.0069 ± 0.0052 (t = 1.33). This
  is consistent with the bandwidth limit.
- Lab record, not in code: the first, monotonic tau sweep produced a spurious
  "df = 0.80 MHz" because tau was collinear with time and the readout drifted.
  Always randomise sweep order.

**Other notes.**

- The doublet search that used to set df and f_ge by walking the yoko was removed
  from this step. It never worked reliably and was not used. df and f_ge are
  configured. Set df from an independent doublet measurement: the realised tau is
  only correct if df is the true splitting.
- `average_n_shots` affects only the legacy averaged plot. Keep it well below one
  dwell. At an 11.75 µs rep, 25 shots ≈ 294 µs ≈ 1/8.5 dwell; the old value 400
  spanned ~2 dwells and gave a featureless plot. At a ~262 µs rep, even 10 shots span
  about one dwell.
- `rounds > 1` is refused: the shot buffer keeps only the last round. Scale `reps`
  instead.
- A set `flattop_length` is refused: flat-top-calibrated gains do not transfer to the
  gaussian envelope.
- One shared envelope serves pi and pi/2. Envelope memory is 65536 samples per
  generator; at σ = 2 µs one copy is ~55056 samples, so two copies would not fit.

## Known issues

- `mr_relax_delay = 500` in the CSTQ03 runner carries the comment "5x T1 = 50 µs", but
  5 × 50 µs = 250 µs, and the 2026-08-04 acceptance settings were 250 µs and
  100,000 shots. The runner currently has 500 µs and 50,000 shots. Check which one you
  intend.
- The runner's `f_ge = 3754.5` (the Q2 table centre frequency) sits next to a comment
  "measured TOP branch (bottom = 4184.0)". The two are inconsistent, and `df = 1`,
  k = 1 contradict the df = 2.7 analysis. Values are per-cooldown; set them in the
  device file. The runner pulses `Qubit_Pulse = 5` (2651 MHz), so the doublet centre
  3754.0 MHz is 1103 MHz off the pulsed qubit and every run prints the
  [f_ge check](#f_ge-must-sit-on-the-pulsed-qubit) warning. The check is warn-only by
  default for this reason; set `require_f_ge_near_qubit=True` once f_ge is corrected.
- The SingleShot separator is calibrated twice at the start (before the loop and
  again at cycle 0).
- `use_apriori_separator=False` aborts with RuntimeError **after** cycle 0's
  acquisition and save.
- The legacy plots and npz use the *model* rep period; the HMM uses the *emitted*
  schedule. The two should agree, but this is not checked at runtime.
- The out-of-range error message suggests capping via
  `ModifiedRamsey_params['max_sep_MHz']`, a key of the removed doublet search. It has
  no effect.
- The run passes the device `flattop_length`. On a device with a flat-top pi pulse,
  the program refuses to run.
- In the symmetric scheme the reset pi plays at the midpoint, off-resonant from both
  branches (see [active_reset](active_reset.md#known-issues)).
- `save_data()` with no argument raises.
- `parity_analysis_enabled = False` in the CSTQ03 runner: no rates are computed
  online, only the raw records, the control records and legacy plots.
- Before 2026-10, the controls were acquired only when `parity_analysis_enabled` was
  True, so CSTQ03 runs with the analysis off have **no control records**.
