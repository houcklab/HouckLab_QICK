# modified_ramsey: fixed-tau Ramsey charge-parity record (ModifiedRamsey)

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

### Standard vs symmetric scheme

| | Standard (`symmetric_ramsey=False`) | Symmetric (`symmetric_ramsey=True`) |
|---|---|---|
| Drive frequency | `f_ge` (on the upper branch) | `f_ge − df/2` (midpoint) |
| Branch detunings | 0 and df | ±df/2 |
| Phase accrued in tau | upper 0, lower π | ±π/2 |
| Closing pi/2 phase | 180° | 90° |
| Mapping | upper → \|g>, lower → \|e> | upper → \|e>, lower → \|g> |
| `flip_final_pi2=True` | 0°, mapping swapped | 270°, mapping swapped |

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
  identical mapping contrast.
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

### Echo is a null, not a measurement

`use_pi_pulse=True` inserts a Hahn echo, which refocuses the static detuning df, i.e.
exactly the parity phase. The echo sequence has zero parity contrast by construction.
Use it only as a negative control (`echo_null`).

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
`final_pi2_phase_deg`, …. It uses **nominal** 4σ envelopes; the program reports the
quantised values.

What one run does:

1. If `use_active_reset`: calibrate the reset readout (rotates `res_phase`).
2. Run the SingleShot g/e calibration (`ss_calib_shots`).
3. Repeat for `num_cycles` cycles. Each cycle:
   - recalibrates the separator every `ss_recalib_every_n_cycles` cycles;
   - acquires the record;
   - runs the continuous analysis (if `parity_analysis_enabled`);
   - every `validation_controls_every_n_cycles` cycles, acquires and analyses each
     control;
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
| `post_reset_wait` | 0.0 | µs | Settle time after reset. |
| `parity_analysis_enabled` | False | bool | Run the HMM/ACF/PSD analysis per cycle. Code fallback True. |
| `expected_parity_dwell_ms` | 2.5 | ms | HMM initial rate (1/dwell). Also sets the drift-window safety check. |
| `drift_window_ms` | 200.0 | ms | Rolling-mean drift window (≥ 20× dwell). |
| `hmm_symmetric` | True | bool | Fit one symmetric rate. |
| `hmm_bootstrap_samples` | 0 | count | Parametric bootstrap for rate CIs. |
| `mapping_p_e_state0` / `mapping_p_e_state1` | 0.1 / 0.9 | prob. | Assumed P(e) for each parity state. |
| `mapping_probabilities_calibrated` | False | bool | False adds an explicit warning. |
| `hmm_min_emission_snr` | None (→ 0.7) | ratio | Per-sample emission gate. **Do not lower** (see findings). |
| `hmm_kwargs` | None | dict | Other `fit_two_state_hmm` kwargs (e.g. `min_transitions`). |
| `validation_controls` | ["flip_final_pi2", "echo_null"] | list | Controls to interleave. |
| `validation_controls_every_n_cycles` | 10 | cycles | Control cadence. |
| `control_tau_offset_frac` | 0.25 | fraction | `tau_offset` control. |
| `control_detuning_mhz` | None (→ +df) | MHz | `drive_detuned` control. |
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
  for controls, the string `mr_control_type`).
- **Analysis files** in `<outer>/ModifiedRamsey/<YYYY_MM_DD>/` with base
  `Cycle_<nnn>_MR_<ts>`:
  - `_continuous_analysis.json` and `_continuous_analysis.h5` (`v_projected`,
    `v_corrected`, `drift`, `t_s`, `posterior_state1`, `viterbi_path`, summary
    attrs);
  - plots `_continuous_{calibration,projected_trace,hmm,acf_psd,rate_vs_bin,dwells,reset_success}.png`;
  - per control, the same files with `_<control>`; plus `_control_comparison.json`;
  - legacy diagnostics: `_iq_labeled_apriori.png`, `_single_shot_binary.png`,
    `_averaged_population.png`, `.npz`, `_config.json`;
  - one `CycleSummary_<ts>.json` per run.
- Control records go to `ModifiedRamsey_Controls/` (h5 + json, no png).
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
2. **Projection** onto the calibrated axis, giving an analog trace v(t). The time
   base is the emitted-schedule rep period.
3. **Drift removal.** A centred rolling **mean** over `drift_window_ms`. A rolling
   median would track the majority state and eat the telegraph. The default 0.2 s is
   80× a 2.5 ms dwell; a window < 20× dwell is flagged unsafe.
4. **Two-state HMM.** Log-space forward-backward with exact `expm(Q·dt)` transitions.
   - Each parity state emits a calibrated g/e **mixture** with weights
     `p_e_state0/1`.
   - The weights `p_e_state0/1` (default 0.1/0.9) are **assumed**. Replace them
     with values from a device-specific mapping calibration once one exists; g/e
     readout fidelity alone is not enough. Until then, every rate is conditional on
     the assumption, and a warning says so.
   - State labels are neutral (`state0`/`state1`): mapping them to even/odd charge
     parity needs physics input the analysis does not have.
   - Emissions are fixed during the rate fit (refitting would absorb drift).
   - Symmetric rate by default: charge parity has no preferred branch.
   - The initial rate is 1/`expected_parity_dwell_ms`. The documented BFC operating
     point is a 2–3 ms dwell; 2.5 ms corresponds to γ = 200 Hz.
   - **Identifiability gates.** All must pass, otherwise rates are NaN with reasons:
     - per-sample emission SNR ≥ `min_emission_snr` (0.7);
     - expected transitions ≥ 10;
     - log-likelihood gain over a single Gaussian ≥ 10;
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
   switching.
8. **Reset readouts.** Pre-correction ground fraction per reset row (see
   [active_reset](active_reset.md#reset-readout-k-is-taken-before-flip-k)).
9. **Controls** (`build_control_variants` + `compare_parity_controls`). Controls
   share the voltage, calibration, time base and emission model with the parity
   record, and must use the **same HMM gate**; otherwise they are not controls.

| Control | Change | Expected signature | Decision |
|---|---|---|---|
| `flip_final_pi2` | +180° closing phase | Telegraph amplitude and rates unchanged; occupancy inverted | ACF amplitude ratio > 0.25 **and** \|occ1_flip − (1 − occ1_main)\| < 0.15 |
| `echo_null` | `use_pi_pulse=True` | Contrast suppressed (echo refocuses df) | Ratio < 0.25, or HMM unidentifiable |
| `tau_offset` | programmed tau × (1 + frac) | Off the π condition: contrast reduced or rotated | Informational |
| `drive_detuned` | drive + detuning (default +df), bandwidth limit lifted | Both branches off-resonant, mapping degraded | Informational |
| `drive_off` | `pi2_gain = 0` | Readout/thermal baseline, no parity information | Informational |

`all_expected` is True only if all of the following hold:

- the parity record is identifiable and has a finite ACF amplitude;
- at least one decisive check ran and passed;
- no requested control was skipped as infeasible.

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

- The gate tests `analog_snr × |p1 − p0|` using the **assumed** mapping
  probabilities. Improving the real mapping (for example with the symmetric scheme)
  does not move this number until the probabilities are updated from a measurement.
- At analog SNR ≈ 0.77 the product is ≈ 0.62 < 0.7, so the HMM withholds rates.
- With the gate lowered to 0.3, the HMM returned a confident-looking 4921 ± 68 Hz,
  while ACF gave 9606 Hz and PSD 15056 Hz (> 3×, auto-flagged). The `echo_null`
  control, which cannot contain parity contrast, retained 44 % of the parity ACF
  amplitude.
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
  - k = 5: tau = 0.9259 µs, echo gap 0.063 µs, phase 4.997π. This keeps the
    measurement **and** its decisive null; prefer it.
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
  device file.
- The `tau_offset` control sets tau = 1/(2·df)·(1 + frac). It ignores
  `tau_harmonic_k`, so with k > 1 it is not "the measured tau + 25 %".
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
  online, only the raw records and legacy plots.
