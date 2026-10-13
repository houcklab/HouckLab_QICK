# Audit: charge_parity_runs

File: `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Runners/runs/charge_parity.py`
Lines: **1976** (task said ~1800; actual 1976). Comment-only lines: 172. Docstring lines: ~30.
Last touched by commits: 42ffde5 (extracted from monolith), 68edf75, 8939fe7, aecc868, bb8f965 (added `run_charge_transmission_sweep`).

## 1. Purpose
Session-level "run" routines for charge-parity / charge-dispersion work on CSTQ03: two-tone doublet search + quasi-CW telegraph, Modified Ramsey parity record (+ HMM analysis + interleaved controls), sweet-spot Modified Ramsey control, single-tone quasi-CW, charge-dispersion Ramsey, and two charge-bias sweeps (qubit spec, cavity transmission). Plus the `modified_ramsey_timing` analytic model of the ModifiedRamseyProgram schedule.

## 2. Public symbols

| Symbol | Lines | Description |
|---|---|---|
| `modified_ramsey_timing(soccfg, cfg)` | 34-209 | Pure function: reproduces ModifiedRamseyProgram per-rep schedule (tone/ADC quantization, tau gap, reset block) -> dict of 27 timing fields. No hardware. |
| `run_two_tone_charge_dispersion_quasicw(ctx, TwoToneChargeDispersion_params, Spec_relevant_params, ChargeDispersion_params)` | 212-569 | Yoko-walk doublet search with QubitSpecSliceFF, then ChargeDispersionQuasiCW record + KMeans telegraph per cycle. |
| `run_modified_ramsey(ctx, ModifiedRamsey_params)` | 572-1037 | Fixed-tau Modified Ramsey records at configured f_ge/df, SS separator calibration, optional active reset, HMM/ACF/PSD analysis, interleaved validation controls, legacy threshold plots. |
| `run_modified_ramsey_control(ctx, ModifiedRamsey_Control_params)` | 1040-1419 | Per cycle: `find_sweet_spot` (moves yoko) -> Modified Ramsey at sweet spot -> KMeans + blob-SNR gate + moving-average/hysteresis jump detection. |
| `run_charge_dispersion_quasicw(ctx, ChargeDispersion_params, Spec_relevant_params)` | 1422-1619 | One ChargeDispersionQuasiCW record at fixed probe_freq, KMeans split, 4 plots, npz/json. |
| `run_charge_dispersion_ramsey(ctx, T1T2_params, ChargeDispersion_params)` | 1622-1649 | Loop of ChargeDispersion (Ramsey-type) experiments. |
| `run_charge_sweep(ctx, Spec_relevant_params)` | 1652-1775 | Qubit spec (QubitSpecSliceFF) at each yoko voltage -> live heatmap, npz. |
| `_charge_sweep_voltages(cfg, params)` | 1778-1807 | Private: resolve/validate voltage_start/end/step (params else cfg), returns np.arange. Used only by `run_charge_transmission_sweep`. |
| `run_charge_transmission_sweep(ctx, params=None)` | 1810-1976 | CavitySpecFF at each yoko voltage -> live dB heatmap + tracked extremum; restores yoko in `finally`. |

No QICK Program classes in this file. Experiment classes instantiated: `QubitSpecSliceFF`, `ChargeDispersionQuasiCW`, `ModifiedRamsey`, `ChargeDispersion`, `CavitySpecFF` (+ indirectly `SingleShotProgramFFMUX` via calibration.py and `find_sweet_spot`).

## 3. Control-flow summaries

### 3.1 `modified_ramsey_timing(soccfg, cfg)` (34-209)
1. Validate: ro_chs non-empty; df, sigma, readout_length > 0; adc_trig_offset, mr_relax_delay (+ reset_readout_relax_delay, post_reset_wait when use_active_reset) >= 0 -> `ValueError`.
2. Clock constants from soccfg: `tprocs[0].f_time`, `gens[res_ch].f_fabric`, `gens[qubit_ch].f_fabric`, `readouts[ch].f_output`.
3. Readout slot: requested tone cycles = us2cycles(cfg["length"], gen_ch=res_ch); ADC end per ch = adc offset + window; tone extended to cover ADC end; slot = int(max(tone_end, adc_end)).
4. Qubit pulse = us2cycles(4*sigma, gen_ch=qubit_ch); pulses = 3 if use_pi_pulse else 2; waits = 2 or 1.
5. tau = cfg.get("ramsey_tau_us", 1/(2 df)); gap = tau/waits - pulse_us; gap<=0 -> ValueError; effective_tau from quantized gap.
6. final padding 0.05 us; mr_relax; reset block = reset_cycles*(slot + reset_delay + pi) + post_reset_wait (only if use_active_reset).
7. Return dict (scheduled_rep_period_us/cycles, ramsey_sequence_us, reset_block_us, readout_slot_us/cycles, resonator_tone_us, requested_resonator_tone_us, tone_quantization_extension_cycles, adc_offset_us, max_readout_window_us, tone_coverage_margin_us, qubit_pulse_us, ramsey_qubit_pulse_count, ramsey_wait_us, requested_tau_us, effective_tau_us, ramsey_gap_per_wait_us, final_padding_us, mr_relax_delay_us, reset_cycles, reset_readout_relax_delay_us, post_reset_wait_us, f_time_mhz, res_f_fabric_mhz, qubit_f_fabric_mhz, ro_f_output_mhz).

### 3.2 `run_two_tone_charge_dispersion_quasicw` (212-569)
1. `cfg = ctx.working_config()` ONCE (reused/mutated across all cycles). save_dir = outerFolder/TwoToneChargeDispersion.
2. Read yoko voltage (`:SOUR:LEV?`), direction=+1.
3. `for cycle_idx in range(num_cycles)`:
   - `for attempt_idx in range(max_voltage_tries)`:
     a. cfg overrides from TwoTone params: current_voltage, reps, rounds, Gauss, relax_delay, [sigma, qubit_gain if Gauss], qubit_length, SpecSpan, SpecNumPoints, step=2*SpecSpan/SpecNumPoints, start=qubit_frequency_center-SpecSpan, expts.
     b. `QubitSpecSliceFF(path="TwoToneChargeDispersion")` -> acquire -> display(plotDisp=False, figNum=2, min_sep, fit_window_mhz, prominent_ratio from Spec_relevant_params) -> save_data -> save_config.
     c. `project_iq_signal`, `choose_two_tone_freqs_from_lorentz_or_peaks(min_sep_mhz)`; `save_two_tone_plot`; write `<base>_summary.txt`.
     d. Branch 1 (data-dependent): strongest peak within `center_peak_tol_mhz` (default 0.05) of `ctx.qubit_frequency_center` -> probe = that peak, sep = peak_sep or 0.0, success, break.
     e. Branch 2: peak_sep >= df -> probe = max/min peak per `use_upper_peak`, success, break.
     f. Else `choose_next_voltage` (bounce between voltage_min (clamped >=0) and voltage_max); if step stalled (<1e-15) break (failure); `ramp_to(yoko, next)` (ignores ctx.yoko_fixed).
   - If not success: append failure summary; continue.
   - **Mutates caller dict** `ChargeDispersion_params["probe_freq"] = probe`.
   - QCW cfg overrides: current_voltage, reps=qcw_repetitions, rounds=1, Gauss/sigma/qubit_gain from **Spec_relevant_params** (not TwoTone params), relax_delay=qcw_relax_delay, SpecNumPoints=1, SpecSpan=0, step=0, start=probe, expts=1.
   - `ChargeDispersionQuasiCW(path="TwoToneChargeDispersion").acquire(load_pulses=True, print_time=True)` (no save_data/save_config).
   - KMeans(2) split, majority relabel; approx time axis `rep = 1.0+0.5+readout_length+10+relax_delay` us.
   - 4 PNGs (_iq_separator, _iq_labeled, _amplitude_vs_time, _binary), npz, _config.json; append success summary. Voltage/direction carried to next cycle.
4. Write CycleSummary_<ts>.json. Yoko NOT restored.

### 3.3 `run_modified_ramsey` (572-1037)
1. save_dir = outerFolder/ModifiedRamsey/<YYYY_MM_DD>. df = params["df"] (>0 else ValueError); f_ge = params.get("f_ge", ctx.qubit_frequency_center); voltage read once (provenance only, never moves yoko).
2. If use_active_reset: require use_apriori_separator (else RuntimeError); `calibrate_active_reset_readout(ctx)` -> **rotates ctx.config["res_phase"] in place** (persistent).
3. If use_apriori_separator: `get_apriori_separator_from_singleshot(ctx, ss_calib_shots)` (SingleShotProgramFFMUX run).
4. `cfg = ctx.working_config()` (after the res_phase rotation).
5. `for cycle_idx in range(num_cycles)`:
   a. If use_apriori_separator and (sep None or cycle_idx % ss_recalib_every_n_cycles == 0) -> recalibrate separator (fires at cycle 0 too: duplicate calibration, see bugs).
   b. tau_harmonic_k must be positive odd else ValueError; tau = k/(2 df).
   c. Build `mr_cfg` (keys in sec. 4); threshold: params readout_threshold if set, elif use_active_reset -> `wire_reset_into_mr_cfg(mr_cfg, sep)`.
   d. `config_mr = cfg | mr_cfg`; `config_mr["modified_ramsey_timing"] = modified_ramsey_timing(...)`.
   e. `ModifiedRamsey(path="ModifiedRamsey")` acquire -> display(figNum=10) -> save_data -> save_config.
   f. If sep None -> RuntimeError (after acquisition).
   g. analog calibration from SS g/e shots (`calibrate_readout_from_labeled_shots`); mapping probs; hmm_kwargs (+ min_emission_snr override).
   h. If parity_analysis_enabled (default True; runner sets False): `analyze_modified_ramsey_record(...)`; print verdict. If validation_controls and cycle_idx % every_n == 0: for each `build_control_variants(config_mr, include, tau_offset_frac, detuning_mhz)` -> skipped if cfg None, else timing, `ModifiedRamsey(path="ModifiedRamsey_Controls")` acquire/save_data/save_config (no display), analyze with same kwargs; `compare_parity_controls` -> `<base>_control_comparison.json`.
   i. Legacy diagnostics: `classify_and_average_iq` with SS g/e centres; time axis from **model** `timing_mr["scheduled_rep_period_us"]` (analysis used the emitted-schedule `data["scheduled_rep_period_us"]`); 3 PNGs (_iq_labeled_apriori, _single_shot_binary, _averaged_population), npz, _config.json; append cycle summary (incl. gamma01/10, identifiable, warnings).
6. CycleSummary json.

### 3.4 `run_modified_ramsey_control` (1040-1419)
1. save_dir = outerFolder/ModifiedRamsey_Control. Reads sweet_spot_max_df_mhz, cd_max_mhz, cd_period_mv (KeyError if missing), num_cycles. **setdefault mutates caller dict**: hysteresis_low 0.4, hysteresis_high 0.6, window_ms 0.1.
2. Voltage read; `cfg = ctx.working_config()`; build `sweet_params` (spec_* + ss_* keys + cd_period_mv) for `find_sweet_spot`.
3. `for cycle_idx in range(num_cycles)`:
   a. `find_sweet_spot(...)` (moves yoko; Strategy A half-period jump if cd_period_mv, else B incremental walk). Update voltage if returned. Print log.
   b. S_sweet = peak_sep or 0; verified = peak_sep is None or S < sweet_spot_max_df_mhz.
   c. tau = 1/(2 cd_max_mhz) (printed/saved only; NOT passed as ramsey_tau_us — program derives tau from df=cd_max_mhz, same value for k=1).
   d. If verified: build mr_cfg_mrc (f_ge from search, df=cd_max_mhz, ...; no tau_harmonic_k, no max_drive_bandwidth_ratio, no readout_threshold); timing; `ModifiedRamsey(path="ModifiedRamsey_Control")` acquire/display(figNum=11)/save_data/save_config; KMeans(2) split; blob SNR = |c1-c0| / pooled within-cluster RMS; if < 2.0 all shots -> 0, else majority relabel; IQ + binary plots; moving average (window_n = round(window_ms/dt)) + hysteresis state machine -> switches; 3 more plots; npz, _config.json; summary.
   e. Else: print skip; failure summary (stage_failed="sweet_spot_not_verified").
4. CycleSummary json. Yoko left at last sweet spot; ctx.yoko_fixed ignored.

### 3.5 `run_charge_dispersion_quasicw` (1422-1619)
1. cfg = working_config; reps=repetitions, rounds=1, Gauss/sigma/qubit_gain from Spec_relevant_params, relax_delay; one-frequency mode (SpecNumPoints=1, SpecSpan=0, step=0, start=probe_freq, expts=1).
2. `ChargeDispersionQuasiCW(path="ChargeDispersion").acquire(load_pulses=True, print_time=True)`.
3. KMeans(2), majority relabel; amps; approx rep period (same magic formula).
4. Plot 1 (IQ + separator) `plt.show()` only, never saved; Plot 2 saved + show; Plot 3 score histogram saved + show; Plot 4 binary trace saved. npz + _config.json under outerFolder/ChargeDispersion.

### 3.6 `run_charge_dispersion_ramsey` (1622-1649)
`for i in range(T1T2_params["repetitions"])`: cd_cfg {df=ChargeDispersion_params["df"], reps=1, rounds=1, pi2_gain, sigma, flattop_length, f_ge=qubit_frequency_center, relax_delay, Qubit_number}; `ChargeDispersion(path="ChargeDispersion")` acquire/display(plotDisp=True, figNum=5)/save_data/save_config.

### 3.7 `run_charge_sweep` (1652-1775)
1. cfg = working_config; sanity_dump; reps, rounds, Gauss, [sigma, qubit_gain]. Voltages = np.arange(cfg voltage_start/end/step) directly (not `_charge_sweep_voltages`).
2. For each V: if V>10 print+break; if not yoko_fixed ramp_to; current_voltage; `QubitSpecSliceFF(path="QubitSpecFF")` acquire/display/save_data/save_config; project_iq_signal; find_peaks two tallest (print only); lazy-init live imshow; update row; plt.pause(0.1).
3. Save heatmap PNG next to last slice (`iname[:-4]`), npz (`fname[:-3]`). Yoko NOT restored.

### 3.8 `run_charge_transmission_sweep` (1810-1976)
1. params default {}; cfg = working_config; sanity_dump; optional reps/rounds/TransSpan/TransNumPoints overrides; fit, settle_s; voltages via `_charge_sweep_voltages`.
2. center_freq = cfg["pulse_freq"]; lo_mhz = cfg.get("cavity_LO",0)/1e6. v_return = yoko voltage.
3. try: for each V: ramp (unless yoko_fixed) + optional sleep; cfg current_voltage, pulse_freq reset to centre; `CavitySpecFF(path="ChargeTransmissionFF")` acquire/display(fit=do_fit, figNum=20)/save_data/save_config; dB; raw extremum (argmin if ctx.cavity_min); fit extremum if `hanger_fit_min_freq_mhz`; lazy live heatmap (GHz axis); shape-mismatch RuntimeError. finally: ramp back to v_return (unless yoko_fixed).
4. Overlay tracked extremum, save PNG/npz beside last slice, print span in kHz.

## 4. cfg keys

### Read from cfg
- `modified_ramsey_timing`: res_ch, qubit_ch, ro_chs, df, sigma, readout_length, length, adc_trig_offset, mr_relax_delay, use_active_reset, reset_readout_relax_delay, post_reset_wait, use_pi_pulse, ramsey_tau_us, reset_cycles. soccfg: tprocs[0].f_time, gens[ch].f_fabric, readouts[ch].f_output.
- two-tone QCW: SpecSpan, SpecNumPoints, Gauss, readout_length, relax_delay (after writing).
- QCW: Gauss, readout_length, relax_delay.
- run_charge_sweep: voltage_start, voltage_end, voltage_step (from runner `charge_params` via build_context; Regime A only).
- transmission sweep: pulse_freq, cavity_LO, voltage_start/end/step (fallback).

### Written to working cfg (transient)
- two-tone: current_voltage, reps, rounds, Gauss, relax_delay, sigma, qubit_gain, qubit_length, SpecSpan, SpecNumPoints, step, start, expts.
- MR (`mr_cfg` merged into config_mr): f_ge, df, ramsey_tau_us, mr_tau_harmonic_k, pi2_gain, pi_gain, use_pi_pulse, flip_final_pi2, symmetric_ramsey, max_drive_bandwidth_ratio, use_active_reset, reset_cycles, reset_ground_below_threshold, reset_readout_relax_delay, post_reset_wait, mr_relax_delay, sigma, flattop_length, reps, rounds, current_voltage, Qubit_number, readout_threshold (conditional; wire_reset also overwrites reset_ground_below_threshold), modified_ramsey_timing.
- MRC (`mr_cfg_mrc`): f_ge, df, pi2_gain, pi_gain, use_pi_pulse, flip_final_pi2, symmetric_ramsey, use_active_reset, reset_cycles, reset_ground_below_threshold, reset_readout_relax_delay, post_reset_wait, sigma, flattop_length, mr_relax_delay, reps, rounds, current_voltage, Qubit_number, modified_ramsey_timing.
- QCW: reps, rounds, Gauss, relax_delay, sigma, qubit_gain, SpecNumPoints, SpecSpan, step, start, expts.
- CD Ramsey: df, reps, rounds, pi2_gain, sigma, flattop_length, f_ge, relax_delay, Qubit_number.
- charge sweep: reps, rounds, Gauss, sigma, qubit_gain, current_voltage.
- transmission sweep: reps, rounds, TransSpan, TransNumPoints, current_voltage, pulse_freq.

### Persistent state mutated
- `ctx.config["res_phase"]` (via `calibrate_active_reset_readout`, run_modified_ramsey:610).
- Caller param dicts: `ChargeDispersion_params["probe_freq"]` (401); `ModifiedRamsey_Control_params` hysteresis_low/high, window_ms (1049-1051).
- Yoko bias left moved by two-tone search, MRC, charge sweep (only transmission sweep restores).

### Param-dict keys consumed (for devices/ + runner schema)
- TwoToneChargeDispersion_params: df, dV, voltage_min, voltage_max, max_voltage_tries, num_cycles, reps, rounds, Gauss, relax_delay, sigma, gain, qubit_length, SpecSpan, SpecNumPoints, center_peak_tol_mhz(.get 0.05), use_upper_peak, qcw_repetitions, qcw_relax_delay.
- Spec_relevant_params: min_sep_MHz, fit_window_mhz, prominent_ratio, Gauss, sigma, gain, reps, rounds.
- ChargeDispersion_params: probe_freq, repetitions, relax_delay, df (missing in runner!). Runner keys upper_freq/lower_freq are read nowhere.
- ModifiedRamsey_params: df, f_ge, num_cycles, use_active_reset, use_apriori_separator, ss_calib_shots, ss_recalib_every_n_cycles, tau_harmonic_k, use_pi_pulse, flip_final_pi2, symmetric_ramsey, max_drive_bandwidth_ratio, reset_cycles, reset_ground_below_threshold, reset_readout_relax_delay, post_reset_wait, mr_relax_delay, mr_reps, readout_threshold, mapping_p_e_state0, mapping_p_e_state1, hmm_kwargs, hmm_min_emission_snr, parity_analysis_enabled, drift_window_ms, expected_parity_dwell_ms, hmm_symmetric, hmm_bootstrap_samples, mapping_probabilities_calibrated, validation_controls, validation_controls_every_n_cycles, control_tau_offset_frac, control_detuning_mhz, average_n_shots.
- ModifiedRamsey_Control_params: sweet_spot_max_df_mhz, cd_max_mhz, cd_period_mv, num_cycles, hysteresis_low, hysteresis_high, window_ms, SpecSpan, SpecNumPoints, reps, rounds, relax_delay, sigma, gain, qubit_length, df, dV, voltage_min, voltage_max, max_voltage_tries, use_pi_pulse, flip_final_pi2, symmetric_ramsey, use_active_reset, reset_cycles, reset_ground_below_threshold, reset_readout_relax_delay, post_reset_wait, mr_relax_delay, mr_reps. (Runner key "Gauss" is unread.)
- T1T2_params: repetitions (CD Ramsey loop count).
- ChargeTransmission_params: reps, rounds, span, num_points, fit, settle_s, voltage_start/end/step.
- ctx fields: soc, soccfg, yoko, outerFolder, qubit_frequency_center, pi2_gain, qubit_gain, qubit_sigma, qubit_flattop, Qubit_Readout, yoko_fixed, cavity_min.

## 5. Imports

Imports (lines 1-31):
- `Experiments.utils import *` (STAR) -> uses ramp_to, project_iq_signal, choose_two_tone_freqs_from_lorentz_or_peaks, save_two_tone_plot, choose_next_voltage, classify_and_average_iq.
- Experiments: mChargeDispersionQuasiCW.ChargeDispersionQuasiCW, mChargeDispersion.ChargeDispersion, mModifiedRamsey.{ModifiedRamsey, build_control_variants}, analyze_ModifiedRamseyParity.{analyze_modified_ramsey_record, calibrate_readout_from_labeled_shots, compare_parity_controls}, mSpecSliceFF.QubitSpecSliceFF, mTransmissionFF.CavitySpecFF, mSingleShotProgramFFMUX.SingleShotProgramFFMUX (**unused**), mAutoCoherence.find_sweet_spot.
- `.context`: Context (**unused**), sanity_dump. `.calibration`: get_apriori_separator_from_singleshot, calibrate_active_reset_readout, wire_reset_into_mr_cfg, _extract_iq_from_singleshot_data (private name imported across modules).
- third-party: numpy, matplotlib.pyplot, os, json, time, datetime, sklearn KMeans, scipy.signal.find_peaks.

Imported by:
- `Runners/runs/__init__.py:11` `from .charge_parity import *` (no `__all__` -> re-exports everything incl. np/plt/KMeans/utils star names) -> `Runners/CSTQ03_BFC.py:9` `from ...Runners.runs import *`.
- `Experiments/verify_ModifiedRamsey_timing.py:36-37` imports `modified_ramsey_timing` (experiment layer depending on Runners package: layering inversion; pulls pyvisa/initialize4Q via context.py).
- `mModifiedRamsey.py:837` mentions `modified_ramsey_timing()` in docstring only.

External usage of run_* (CSTQ03_BFC.py 758-771), all gated by flags that are **ALL False today**:
- Run2ToneChargeDispersionQuasiCW=False (174), RunModifiedRamsey=False (182), RunModifiedRamsey_Control=False (420), RunChargeDispersionQuasiCW=False (162), RunChargeDispersionRamsey=False (163), RunChargeSweep=False (127), RunChargeTransmissionSweep=False (142).
- All seven are called in "Regime A" (before `rebuild_singleshot_config`).

Unused externally: `_charge_sweep_voltages` (internal only). Dead: none at module level; unused imports `SingleShotProgramFFMUX`, `Context`.

## 6. Dead code
- No commented-out code blocks.
- Unused imports: line 15 `SingleShotProgramFFMUX`, line 25 `Context`.
- Unused variables: `labels` (434; 1463/1484 relabelled but never used after), `cbar` (1671/1745, 1918), `x_pts` in QCW only saved, `half_period_v_mrc` (1046; saved only), `peak_freqs`/`peak_vals` in run_charge_sweep (1715-1724; print only), loop var `i` in run_charge_dispersion_ramsey (1625), `tau_mrc` (1108; plot/save only, not sent to program).
- Duplicated computations: QCW I/Q pad computed twice (1508-1510 vs 1533-1536).
- Effectively unreachable: 1942-1943 `if db_map is None: return` (`_charge_sweep_voltages` forbids empty sweeps; an exception propagates past it). `if len(binary_states_mrc) >= 1` (1284) always true in practice.
- `run_charge_dispersion_ramsey` is effectively dead: KeyError on `ChargeDispersion_params["df"]` with the current runner dict.
- `modified_ramsey_timing` duplicates `ModifiedRamseyProgram.scheduled_rep_period_cycles()` (mModifiedRamsey.py:830-856); the model is now only needed for (a) `modified_ramsey_timing` field in saved cfg, (b) plot time axis, (c) verify script cross-check.

### Duplicated blocks -> shared helpers
| Block | Locations | Proposed helper |
|---|---|---|
| KMeans(2) split + perpendicular-bisector scores + majority relabel | 433-451, 1169-1206 (with blob-SNR gate), 1462-1488; similar in Experiments/analyze_ZeroSpanParity.py:98 | `analysis/iq_classify.py: kmeans_split(iq, min_blob_snr=None) -> (states, c0, c1, midpoint, normal, scores, blob_snr)` |
| IQ pad + separator line + vertical-line special case + scatter | 459-507, 912-949, 1219-1254, 1508-1566 | `analysis/plotting.py: plot_iq_separator(ax, i, q, states, c0, c1, midpoint, normal, title)` |
| Binary step trace plot | 520-530, 951-965, 1256-1269, 1587-1601 | `plot_binary_trace(ax, t, states, ...)` |
| npz + `_config.json` + timestamped base name | 456-457/532-550, 725-727/981-1007, 1214-1217/1354-1385, 1502-1503/1603-1619 | `core/io.py: timestamp()`, `save_record(base, cfg, **arrays)` |
| CycleSummary_<ts>.json | 564-569, 1032-1037, 1414-1419 | `save_cycle_summary(save_dir, rows)` |
| Two-tone spec cfg setup (reps/rounds/Gauss/sigma/gain/span/step/start/expts) | 245-260, 1655-1661, basic.py:167-183 | `spec_cfg(cfg, params, center)` |
| Quasi-CW one-frequency cfg | 403-417 == 1424-1438 | `quasicw_cfg(cfg, probe, reps, relax, spec_params)` |
| QubitSpecSliceFF acquire/display/save 4-liner | 262-280, 1679-1697, basic.py:187-198 | generic `core.run_experiment(cls, ctx, path, cfg, **display_kw)` |
| ModifiedRamsey acquire/display/save | 706-716, 813-822, 1149-1156 | same generic helper |
| mr_cfg construction | 658-693 vs 1122-1144 (near-identical key list; MRC missing tau/k/bw-ratio/threshold) | `build_mr_cfg(ctx, params, f_ge, df, voltage)` used by both |
| analyze_modified_ramsey_record kwargs | 756-777 vs 824-852 (identical except data/base_name) | `_analyze(data, base_name)` closure/partial |
| Live imshow heatmap init/update | 1726-1764 vs 1896-1937 | `analysis/plotting.py: LiveHeatmap(x, y, label)` |
| Voltage grid | 1663-1665 vs `_charge_sweep_voltages` | use `_charge_sweep_voltages` in both |
| Approx QCW rep period `1.0+0.5+readout_length+10+relax_delay` | 453, 1494 | one named function (or real program timing) |
| Yoko readback `float(ctx.yoko.query(":SOUR:LEV?"))` | 225, 593, 1053, 1856 | `hardware/yoko.py: get_voltage(yoko)`; plus a `restore_bias(yoko)` context manager (pattern at 1856-1940) |

## 7. Lab notes to migrate

| Lines | Condensed note | Docs page |
|---|---|---|
| 35-40 | modified_ramsey_timing mirrors program clock conversions + timestamp barriers; excludes initialize(), tProc instruction latency, data transfer, Python overhead. | experiment:modified_ramsey |
| 64-66 | QICK tracks gen/readout timestamps as native cycles converted to tProc cycles; sync_all() truncates the largest to an integer tProc cycle. | architecture |
| 103-105 | tau = pulse-CENTRE-to-centre precession time; QICK schedules waits between pulse EDGES, so programmed gap = tau/n_gaps - 4*sigma. | experiment:modified_ramsey |
| 148-150 | Conditional corrective pi: compile-time timestamp tracking sees the pulse before the shared sync_all(), so synci reserves its full duration on both branches. | experiment:modified_ramsey (active reset) |
| 285-287, 1701-1705 | Use background-subtracted IQ projection (project_iq_signal), not |I+iQ|^2: magnitude is dominated by the large noisy background quadrature, buries qubit peak and washes out the charge-sweep heatmap; projection gives ~0 baseline with qubit as positive bump. | architecture (analysis conventions) |
| 577-582, 592 | df is CONFIGURED. Two-tone doublet search + yoko walk was removed from run_modified_ramsey: never worked reliably, unused. Set df from an independent doublet measurement; realized tau is conditional on it. Routine never moves the yoko. | experiment:modified_ramsey |
| 586-587 | f_ge = upper parity branch; defaults to qubit centre (see bug: centre != upper branch). | experiment:modified_ramsey |
| 599-603 | Active-reset calibration rotates config["res_phase"] in place so g/e separate along I (tProc feedback thresholds on raw I only); must run BEFORE the apriori separator so classification uses the rotated frame. | experiment:modified_ramsey (active reset) |
| 641-648 | Parity condition: relative phase = pi mod 2pi, so tau = k/(2 df) for any ODD k with identical mapping contrast. k=1 shortest (least T2 decay) but needs 4*sigma < tau; raise k to relieve timing without changing sigma or df. Even k returns branches to phase -> zero contrast. | experiment:modified_ramsey |
| 661-662 | ramsey_tau_us is the programmed delay; cfg["df"] stays the physical branch separation in saved records. | experiment:modified_ramsey |
| 672-676 | max_drive_bandwidth_ratio = ceiling on branch_detuning / pi2 Rabi; above 1.0 off-resonant branch barely rotated, mapping degrades; program raises past it. Raise only deliberately; read saved drive_bandwidth_ratio. | parameters + experiment:modified_ramsey |
| 679-680 | Active reset requires readout_threshold + I-axis g/e separation. | experiment:modified_ramsey |
| 694-697 | Threshold precedence: manual readout_threshold > derived from current apriori separator (rotated frame; tracks each SS recalibration). | parameters |
| 738-749 | HMM min_emission_snr gates per-SAMPLE separation (default 0.7 in fit_two_state_hmm). At rep ~11.75 us and 2.5 ms dwell, ~213 samples/dwell -> per-dwell info ~ per_sample_snr*sqrt(213) ~ 15x. Ref test_hmm_moderate_contrast in test_ModifiedRamseyParity_offline.py. Posterior-ambiguity warning means "don't trust individual Viterbi samples", not "rate wrong". **Advice here ("lower it deliberately") is CONTRADICTED by the 2026-08-04 CSTQ03 Q2 measurement in CSTQ03_BFC.py:332-339 ("DO NOT lower"; at 0.3 HMM gave 4921+/-68 Hz vs ACF 9606 Hz vs PSD 15056 Hz; echo_null showed 44% of parity ACF amplitude).** Keep only the runner's conclusion. | experiment:modified_ramsey + device:CSTQ03 |
| 783-785 | Validation controls share voltage, calibration, time base, emission model with the parity record; use a cadence to bound run time. | experiment:modified_ramsey |
| 848-850 | Controls must use the SAME HMM gate as the parity record or they are not controls. | experiment:modified_ramsey |
| 877-878 | Hard-threshold plots are diagnostics only; rate inference uses all unthresholded IQ samples. | experiment:modified_ramsey |
| 904-905 | Averaged trace labels each N-shot bin at its centre (+0.5). | (keep as 1-line code comment) |
| 1083-1086 | find_sweet_spot: Strategy A (cd_period_mv known): one spec + half-period jump, usually 1-2 acquisitions; Strategy B: incremental walk tracking min separation. | experiment:modified_ramsey_control |
| 1104-1107 | MRC tau = 1/(2*cd_max_mhz) (max dispersion from independent calibration), not a measured S1. | experiment:modified_ramsey_control |
| 1118-1121 | Control must run the SAME sequence as the measurement or a null is uninterpretable; pi_gain required when use_pi_pulse or use_active_reset. (Not actually satisfied — see bugs.) | experiment:modified_ramsey_control |
| 1163-1168, 1180-1181 | KMeans(2) always returns two centroids; with majority forcing it manufactures a ~50/50 split from a single blob. Gate: centroid distance / pooled within-cluster RMS; resolved blobs >~2, one blob <~1; threshold 2.0. | architecture (analysis conventions) |
| 1779-1784 | Charge sweep voltages: params override cfg (charge_params); half-open like np.arange. | parameters |
| 1805 | ramp_to only rejects target > 10 V, so a negative typo slips past; sweep validates |V| <= 10. | architecture (hardware: yoko) |
| 1811-1827 | Charge transmission sweep: does NOT write cavity freq back to ctx.config (undefined across a charge sweep); yoko returns to start bias on error/Ctrl-C; per-slice saves + map beside last slice. | experiment:charge_transmission_sweep |
| 1841-1843 | CavitySpecFF.acquire() sweeps cfg["pulse_freq"] in place and display(fit=True) rewrites it with the fitted minimum -> reset to centre for every slice. | architecture (experiment side effects) |
| 1857-1858 | An abort must not park the bias at an arbitrary point; every later measurement would silently run at that charge offset. | architecture (hardware: yoko) |

Stale lab notes in the runner that describe this file's code wrongly (fix while migrating):
- CSTQ03_BFC.py:176-181: "two-tone search -> fixed-tau Ramsey; tau = 1/(2*df) where df is the measured peak separation; f_ge set to the higher-frequency peak" — search was removed; df/f_ge configured.
- CSTQ03_BFC.py:448-450 "Either way the Ramsey still runs" — code skips Ramsey when not verified (1399-1412).
- CSTQ03_BFC.py:454-456 "tau is computed from S1 ... f_ge from two-tone at V_sweet" — tau uses cd_max_mhz; f_ge from find_sweet_spot.
- CSTQ03_BFC.py:250 comment "measured TOP branch (bottom = 4184.0)" next to f_ge=3754.5 (inconsistent with 4186.7 note at 219).

## 8. Noise comments (delete)
193, 224, 237, 244, 372, 388, 400, 560-561, 563, 635-636, 640, 718, 922, 951, 967, 1058-1060, 1082, 1116, 1158, 1231, 1256, 1271, 1433, 1452, 1456, 1459-1461, 1469, 1473, 1476, 1479, 1490, 1493, 1505-1507, 1516-1518, 1546-1548, 1569-1571, 1584-1586, 1588-1592 (historical NameError fix narrative), 1666, 1707, 1714, 1717 (inline), 1725, 1753, 1755, 1757, 1895, 1945. (~67 lines)

## 9. Bugs / suspicious behavior
1. **charge_parity.py:1627** `run_charge_dispersion_ramsey` reads `ChargeDispersion_params["df"]`; runner dict (CSTQ03_BFC.py:166-172) has no `df` -> KeyError on enable. Also uses `T1T2_params["repetitions"]` as its loop count (cross-dict coupling).
2. **401** `run_two_tone_charge_dispersion_quasicw` mutates caller's `ChargeDispersion_params["probe_freq"]`; runner calls `run_charge_dispersion_quasicw` later (line 761) with the leaked value.
3. **337-352** centered-peak branch is checked BEFORE the separation test: any strongest peak within 0.05 MHz of qubit_frequency_center succeeds with sep possibly 0 -> `df` requirement bypassed whenever the qubit sits at its nominal centre.
4. **406-411** QCW uses Gauss/sigma/gain from Spec_relevant_params, while search used TwoTone params; with Spec Gauss=False, `qubit_gain` and `qubit_length` silently carry over from the search (cfg reused across loop, 213).
5. **385** two-tone search ramps yoko even if `ctx.yoko_fixed`; yoko never restored (also MRC via find_sweet_spot, run_charge_sweep).
6. **219** voltage_min silently clamped to >= 0.
7. **316 vs 296** summary writes `peak_vals` from the raw peak finder but `peak_freqs` from the Lorentzian choice (can refer to different peaks).
8. **453, 1494** QCW time axis uses hardcoded `1.0 + 0.5 + readout_length + 10 + relax_delay` us — not derived from the program; elapsed_s is approximate.
9. **612-632** run_modified_ramsey calibrates the SS separator before the loop and again at cycle 0 (`0 % n == 0`) -> duplicate SS calibration at start.
10. **722** `apriori_sep_mr is None` check raises AFTER the hardware acquisition and save; with use_apriori_separator=False every run aborts after cycle 0's data -> option effectively unsupported; validate up front.
11. **588-589** f_ge defaults to ctx.qubit_frequency_center = doublet CENTRE, but program treats f_ge as UPPER branch; with symmetric_ramsey=True this drives the lower branch (runner note 243-248). Default should be removed / required.
12. **898 vs 759** plots/npz time base uses model `timing_mr` while HMM analysis uses emitted `data["scheduled_rep_period_us"]`; two sources of truth (should agree per verify script, but unchecked at runtime).
13. **738-749** comment advises lowering `hmm_min_emission_snr`; contradicted by measured 2026-08-04 finding in runner (332-339).
14. **1122-1144** MRC claims "SAME sequence" but omits tau_harmonic_k / ramsey_tau_us, max_drive_bandwidth_ratio (defaults 1.0 vs MR's 1.4) and uses df=cd_max_mhz (0.682) vs MR df (1 configured; 2.7 measured) -> control not comparable.
15. **1130** MRC forwards `use_active_reset` but never calibrates/wires `readout_threshold` -> ModifiedRamseyProgram raises (mModifiedRamsey.py:588-590) if enabled.
16. **1102** MRC treats "no peaks at all" (peak_sep None) as verified sweet spot.
17. **1046 vs 1076** `cd_period_mv` read with `[]` (KeyError) and `.get` (optional) inconsistently.
18. **1049-1051** `setdefault` mutates caller's ModifiedRamsey_Control_params.
19. **1286** `np.convolve(..., mode="same")` returns length max(N, window_n); if window_n > N the moving-average trace is longer than the time axis -> plot shape error.
20. **1544, 1566, 1581** QCW `plt.show()` calls block in interactive backends; Plot 1 (1519-1544) never saved.
21. **1673-1675, 1766** run_charge_sweep: `break` on first V>10 or empty voltage list -> `fig` None / `Instance_specSlice` undefined -> AttributeError/NameError at save. Only positive >10 checked (negative typo passes). Not using `_charge_sweep_voltages`.
22. **1655-1661** run_charge_sweep ignores Spec_relevant_params relax_delay/SpecSpan/qubit_length (uses values frozen into ctx.config at build_context; relax_delay from BaseConfig).
23. Layering: `Experiments/verify_ModifiedRamsey_timing.py:36` imports from `Runners.runs.charge_parity`.

## 10. Proposed destination
| Symbol(s) | New module |
|---|---|
| `modified_ramsey_timing` | `qicklab/experiments/modified_ramsey.py` (beside ModifiedRamseyProgram; tests/ uses it for the ledger cross-check) |
| `run_modified_ramsey`, `run_modified_ramsey_control`, new `build_mr_cfg`, `_analyze` | `qicklab/runs/modified_ramsey.py` |
| `run_two_tone_charge_dispersion_quasicw`, `run_charge_dispersion_quasicw`, `run_charge_dispersion_ramsey` | `qicklab/runs/charge_dispersion.py` |
| `run_charge_sweep`, `run_charge_transmission_sweep`, `charge_sweep_voltages` (public) | `qicklab/runs/charge_sweep.py` |
| KMeans split + blob SNR gate, hysteresis/moving-average | `qicklab/analysis/iq_classify.py` (`kmeans_split`, `hysteresis_states`) |
| IQ separator / binary trace plots, LiveHeatmap | `qicklab/analysis/plotting.py` |
| timestamped save, npz+json, cycle summary | `qicklab/core/io.py` |
| yoko readback, bias-restore context manager | `qicklab/hardware/yoko.py` |
Candidates to ask the user about dropping: `run_charge_dispersion_ramsey` (broken), `run_two_tone_charge_dispersion_quasicw` (doublet search "never worked reliably" per MR note), `run_modified_ramsey_control` (not same sequence as MR).

## 11. Style
- Star imports (`utils import *`) and star re-export through `runs/__init__.py` without `__all__`.
- Private cross-module import `_extract_iq_from_singleshot_data`.
- CamelCase/Mixed param names (`TwoToneChargeDispersion_params`, `ModifiedRamsey_Control_params`, `Instance_specSlice`, `I_min`, `S_sweet_mrc`), `_mr`/`_mrc` suffix-per-variable naming instead of function scope.
- Unbound-method calls `QubitSpecSliceFF.acquire(Instance)` instead of `inst.acquire()`.
- Mutating caller dicts (401, 1049-1051); `ctx.config` mutated by side-effect call.
- Lambda assignment (162); semicolon statements (1243, 1252, 1262, 1315, 1326, 1332).
- pyplot state machine instead of fig/ax; repeated `dpi=300, bbox_inches="tight"`.
- Magic numbers (0.05 MHz tolerance, 0.05 us padding, 1e-12, 2.0 blob SNR, 0.05 min_spacing, rep-period constants).
- Functions 300-470 lines long (run_modified_ramsey 466, run_modified_ramsey_control 380, two-tone 358).
- `json.dump(..., default=float)` fails on non-numeric objects (e.g. lists of arrays OK, dicts of str fine; object arrays/None-handled) — consider a shared encoder.
