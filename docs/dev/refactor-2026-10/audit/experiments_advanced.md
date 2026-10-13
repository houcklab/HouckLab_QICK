# Audit: experiments_advanced

Root: `WorkingProjects/QM_Team/qubit_measurements/Client_modules/` (abbrev. `CM/`). Client qick in `.venv` = **0.2.334**.
Line counts are `Get-Content().Count`.

## Cross-file map

| File | Lines | Imports (project) | Imported by |
|---|---|---|---|
| Experiments/mModifiedRamsey.py | 1037 | `from qick import *`; CoreLib.Experiment.ExperimentClass | Runners/runs/charge_parity.py (ModifiedRamsey, build_control_variants); Experiments/test_ModifiedRamseyParity_offline.py (MR_CONTROL_TYPE_CODES, build_control_variants, plan_parity_mapping, ModifiedRamseyProgram); Experiments/verify_ModifiedRamsey_timing.py (ModifiedRamseyProgram) |
| Experiments/mUndrivenSingleShot.py | 1219 | `from qick import *`; CoreLib.Experiment; Experiments.utils.ramp_to; Helpers.shot_buffers.raw_shot_buffers | Runners/runs/singleshot.py (UndrivenSingleShot) |
| Experiments/mOptimizeReadoutandPulse_FF.py | 1730 | `from qick import *`; `Helpers.MixedShots_analysis import *`; `Helpers.hist_analysis_opt import *`; mSingleShotProgramFFMUX.SingleShotProgram; CoreLib.Experiment | Runners/runs/singleshot.py (ReadOpt_wSingleShotFF, QubitPulseOpt_wSingleShotFF) |
| Experiments/mAutoCoherence.py | 1796 | mSpecSliceFF.QubitSpecSliceFF, mAmplitudeRabiFF.AmplitudeRabiFF, mSingleShotProgramFFMUX.SingleShotProgramFFMUX, mT1FF.T1FF, mT2R.T2R, mT2EFF.T2EMUX | Runners/runs/coherence.py (run_auto_coherence, AUTO_COHERENCE_PARAMS[unused there], find_sweet_spot[unused there]); Runners/runs/charge_parity.py (find_sweet_spot) |
| Experiments/mZeroSpanParity.py | 737 | `from qick import AveragerProgram`; CoreLib.Experiment | Runners/runs/zero_span.py (ZeroSpanParity); Experiments/utils.py:1282 (lazy, self-test of save_data); utils.chunked_acquire/modulated_strobe_acquire + validate_ZeroSpanParity.py call `set_qubit_gain` duck-typed |
| Experiments/mActiveResetVerify.py | 448 | `from qick import *`; CoreLib.Experiment | Runners/runs/singleshot.py (ActiveResetVerify) |

**None of the six import each other.** ActiveResetVerify *copies* MR's reset logic (and has diverged). Undriven saves under MR key names for `analyze_ModifiedRamseyParity`.

### Cross-file duplication (consolidate in refactor)
- Readout-tone cross-clock coverage block: MR 407-452, Undriven 44-74, ARV 115-152 (identical math) -> `qicklab/core/readout.py::readout_tone_cycles(prog, cfg)`.
- `active_reset_to_g`: MR 637-701 vs ARV 232-278 (DIVERGED: ARV lacks tproc_ch resolution and the ro_norm-sized cmp_offset; ARV adds `reset_force_pi`). -> `qicklab/core/active_reset.py` mixin with `force_pi` option.
- `scheduled_rep_period_cycles/_us`: MR 829-856 vs Undriven 110-134 (MR adds `wait_cycles` for `sync`; Undriven raises on `sync`). -> `qicklab/core/schedule.py`.
- `_ramp_to` (mAutoCoherence 200-209) == `utils.ramp_to` (utils.py:333). -> `qicklab/hardware/yoko.py`.
- `_find_two_tone_peaks` (mAutoCoherence 212-270) == `utils.find_two_tone_peaks` (utils.py:398). -> `qicklab/analysis/spectroscopy.py`.
- Undriven `rate_vs_bin_size(v, dt_us, ...)` vs `analyze_ModifiedRamseyParity.rate_vs_bin_size(v, dt_s, ...)` (1283): SAME NAME, different units and span formula (`n_bins*b*dt` vs `(nb-1)*b*dt`). Undriven `autocorrelation_rate(v, dt_us)` ~= `autocorrelation_rate_estimate(v, dt_s)` (1104). -> one `qicklab/analysis/telegraph.py`, SI units.
- `_T2E_CLOCK_STEP_US = 0.00232515` (= 1 tProc cycle @ ~430.08 MHz) also hard-coded in runs/coherence.py:66,73,136,144,212,213,221 and mSingleShotProgramFFMUX.py:868,883. -> derive `soccfg.cycles2us(1)`.
- `while plt.fignum_exists(figNum): figNum += 1` in every display.
- Raw per-shot buffer access inconsistent: Undriven uses `Helpers.shot_buffers.raw_shot_buffers`; MR/ARV/ZSP read `prog.di_buf[0]` directly. In qick 0.2.334 `di_buf` IS the raw `get_raw()`/`acc_buf` stream (averager_program.py:110-112), so both work locally; shot_buffers docstring says di_buf becomes rep-averaged in later qick (BFG board 0.2.367). Unify on one helper.

---

## 1. Experiments/mModifiedRamsey.py (1037 lines)

**Purpose:** fixed-tau Ramsey for charge-parity switching time series, optional per-shot hardware active reset; hardware-free feasibility planner + validation-control cfg builder.

### Public symbols
- `MR_CONTROL_TYPE_CODES` (9-16): str->int code for control type saved in h5 (`parity`0, `flip_final_pi2`1, `echo_null`2, `tau_offset`3, `drive_detuned`4, `drive_off`5).
- `plan_parity_mapping(df_mhz, sigma_us, use_pi_pulse=False, symmetric_ramsey=False, flip_final_pi2=False, max_bandwidth_ratio=1.0, tau_us=None, drive_freq_offset_mhz=None)` (19-117): hardware-free timing/bandwidth feasibility; returns dict (feasible, errors, warnings, tau_us, pulse_us, n_gaps, gap_us, df_max_mhz, rabi_pi2_mhz, branch_detuning_mhz, bandwidth_ratio, recommend_symmetric, drive_freq_offset_mhz, final_pi2_phase_deg).
- `build_control_variants(base_cfg, include=(...6 names), tau_offset_frac=0.25, detuning_mhz=None)` (120-210): pure; returns list of {label, control_type, cfg|None, skip_reason, expected, plan}.
- `ModifiedRamseyProgram(AveragerProgram)` (213-856): `initialize`, `active_reset_to_g`, `body`, `acquire(soc, threshold, angle, load_pulses, readouts_per_experiment, save_experiments, start_src, progress)` -> `collect_shots()`, `collect_shots` (final read per rep, /norm), `collect_reset_shots` (shape (reset_cycles, reps)), `scheduled_rep_period_cycles`, `scheduled_rep_period_us`.
- `ModifiedRamsey(ExperimentClass)` (859-1037): `__init__` (passthrough), `acquire(progress, debug)`, `display`, `save_data`.

### cfg keys
READ (program): `df, sigma, readout_length, adc_trig_offset, mr_relax_delay, rounds, flattop_length, qubit_ch, res_ch, ro_chs, nqz, qubit_nqz, use_active_reset, reset_cycles, reset_readout_relax_delay, post_reset_wait, reset_ground_below_threshold, ramsey_tau_us, use_pi_pulse, symmetric_ramsey, f_ge, ramsey_drive_freq_mhz, flip_final_pi2, length, pulse_freq, max_drive_bandwidth_ratio, res_phase, pulse_gain, readout_threshold, pi_gain, pi2_gain, reps`.
READ (ExperimentClass extra): `mr_control_type`.
READ (build_control_variants): `flip_final_pi2, df, f_ge, symmetric_ramsey, sigma, use_pi_pulse, ramsey_tau_us, ramsey_drive_freq_mhz, max_drive_bandwidth_ratio`.
WRITTEN: `cfg.setdefault("length", adc_trig_offset+readout_length)` (411; mutates the caller's dict — ExperimentClass does not copy cfg, CoreLib/Experiment.py:72). build_control_variants writes into `dict(base_cfg)` copies: `mr_control_type, flip_final_pi2, use_pi_pulse, ramsey_tau_us, mr_control_tau_offset_frac, ramsey_drive_freq_mhz, max_drive_bandwidth_ratio (1e12), mr_control_detuning_mhz, pi2_gain (0)`.
Upstream writers (runs/calibration.py:181-194 `wire_reset_into_mr_cfg`): `readout_threshold = mean(g_I, e_I)`, `reset_ground_below_threshold = g_I < e_I`; `calibrate_active_reset_readout` rotates `config["res_phase"]` in place.

### Timing contract (group-specific)
- tau = `ramsey_tau_us` if set else `1/(2*df)` (df MHz -> us); **pulse-CENTRE-to-CENTRE** interval of the outer pi/2s.
- Envelope = one shared gaussian "qubit", length `us2cycles(4*sigma, gen_ch=qubit_ch)`; `pulse_us` = quantized duration.
- n_gaps = 2 if `use_pi_pulse` else 1; gap per wait `wait_us = (tau - n_gaps*pulse_us)/n_gaps` (no pi: tau-4σ; echo: (tau-8σ)/2). Written to r_wait (reg 3) as `us2cycles(wait_us)` tProc cycles.
- `effective_tau_us = n_gaps*(cycles2us(wait_cycles)+pulse_us)` saved beside `tau_us`, `wait_us`.
- Final pi/2 phase = (90 if symmetric else 180) + (180 if flip_final_pi2) mod 360. Drive freq = `ramsey_drive_freq_mhz` or f_ge (standard) / f_ge - df/2 (symmetric).
- Bandwidth: rabi_pi2 = 0.0997/sigma MHz; branch detuning = max(|drive-f_ge|, |drive-(f_ge-df)|); ratio > `max_drive_bandwidth_ratio` (default 1.0) raises; > 0.2 warns.
- **Raises** (initialize): df<=0, sigma<=0, readout_length<=0, adc_trig_offset/mr_relax_delay<0, rounds!=1, flattop_length not None, reset_cycles<0, reset delays<0, length < offset+window, empty ro_chs, wait_us<=0 (with df_max message), bandwidth ratio over limit, missing readout_threshold/pi_gain with reset (KeyError), cmp_offset >= 2^30, |raw_threshold| >= cmp_offset. `active_reset_to_g`: RuntimeError if `readouts[ro_ch].tproc_ch` missing/<0. `acquire`: readouts_per_experiment != reset_cycles+1.
- Shot time axis: `scheduled_rep_period_us()` walks compiled prog_list LOOP_J..loopnz summing `synci` args + `wait_cycles` per `sync`; `shot_time_us = index*period` (includes reset overhead). Streamer wall-clock stats saved only as diagnostics.

### Active-reset wiring (group-specific)
- Regs on qubit page: r_wait=3, r_read=4, r_thresh=5.
- `raw_threshold = round(readout_threshold * ro_norm)`, `ro_norm = readout_window_cycles[ro_chs[0]]` (same norm as collect_shots).
- `cmp_offset = int(ro_norm) << 15` (fixed 2026-07-28 per memory); r_thresh = raw_threshold + cmp_offset; after `read(tproc_in_ch, q_rp, "lower", r_read)` do `mathi r_read += cmp_offset`; `condj(r_read, "<" if reset_ground_below_threshold else ">", r_thresh, RESET_DONE_i)` skips the corrective pi (pi_gain, phase 0, f_drive) when already |g>. Label before `sync_all()`; after cycles `sync_all(us2cycles(post_reset_wait))`. Each reset readout uses `syncdelay=reset_readout_relax_delay` (default 1.0 us). Reset pi plays at the Ramsey **drive** freq (f_avg in symmetric mode), not f_ge.
- reads_per_rep = reset_cycles + 1; final read = index reads_per_rep-1.

### Dead / unused
- `ModifiedRamsey.acquire(debug=...)` unused; `display(**kwargs)` unused; `readout_tone_extension_cycles` (450) set, never read; `ModifiedRamsey.__init__` is a pure passthrough (deletable).
- No commented-out code blocks.

### Lab notes to migrate
| Lines | Condensed | Page |
|---|---|---|
| 7-16 | h5 stores numeric control code; string in cfg["mr_control_type"] via save_config. Code table + meaning: flip_final_pi2 = mapping inversion (signal must reverse); echo_null = Hahn null (contrast must vanish); tau_offset = wrong tau (reduced contrast); drive_detuned = off both branches; drive_off = pi/2 disabled (readout-only). | experiment:modified_ramsey |
| 23-37 | Planner mirrors initialize() with NOMINAL 4σ (unquantized); realized values from program `effective_tau_us`; verify_ModifiedRamsey_timing.py checks agreement; conventions tested in test_ModifiedRamseyParity_offline.py. | experiment:modified_ramsey |
| 134-150 | Expected control signatures: flip -> mapping inverts, telegraph amplitude & rates unchanged; echo_null -> contrast suppressed; tau_offset -> programmed tau x(1+frac), physical df unchanged, contrast reduced/rotated; drive_detuned default +df (one branch spacing), both branches off-resonant; drive_off -> pi2_gain=0, readout/thermal baseline. | experiment:modified_ramsey |
| 223-267 | Sequences (no-pi / echo). Standard scheme: drive on UPPER branch (cfg f_ge), closing phase 180: upper->|g>, lower->|e>. Symmetric: drive at f_ge-df/2, branches ±df/2, ±90° in tau, closing phase 90: upper->|e>, lower->|g>. flip adds 180 in either scheme (180<->0, 90<->270). | experiment:modified_ramsey |
| 240-244, 374-378 | Echo (use_pi_pulse) refocuses static detuning df -> zero parity contrast by construction; negative control only. | experiment:modified_ramsey |
| 263-267 | mr_relax_delay (default 0) deliberately separate from relax_delay (used by runner's two-tone search). | parameters |
| 273-287 | readout_threshold in normalized units (accum I / window cycles) = IQ-plot units; tProc thresholds raw I only -> res_phase must be rotated so g/e separate along I. reset_cycles more rounds = better ground fidelity, more readouts. | parameters + experiment:modified_ramsey |
| 310-312 | rounds>1 unsupported: di_buf keeps only last round -> earlier rounds silently dropped; scale reps. | architecture |
| 320-322 | flat_top-calibrated pi/pi2 gains do not transfer to a gaussian envelope -> refuse. | architecture |
| 335-339 | Pulse regs allocated top-down per page (asm_v1.py:610-625: regs 22-31 on 1-manager page, 12-31 on 2-manager page); AveragerProgram rjj=14, rcount=15, trigger word 16 on page 0; regs 3/4/5 free on any page. | architecture |
| 354-362 | ARV data TATQ01/BFE 2026-06-05/06: corrective pi fired on every shot with NEGATIVE accumulated I (deployed tProc compares as unsigned). Fix: add same large positive offset to both operands. | architecture (active reset) |
| 482-496 | QICK waits are between pulse EDGES (sync_all advances to end of envelope; asm_v1.py:895-904, 938-960). Parity phase accrues centre-to-centre; using raw tau as gap overshoots by 4σ (8σ echo), worst when doublet best resolved (large df -> small tau). | experiment:modified_ramsey |
| 500-513 | df_max = 1/(2·n_gaps·4σ) (= 1/(8σ) no-pi); cap via ModifiedRamsey_params['max_sep_MHz']. | parameters |
| 523-539 | 4σ gaussian pi/2 peak Rabi Ω0/2π ≈ 0.0997/σ MHz; standard detunes one branch by df, symmetric both by df/2; ratio>limit (default 1.0) -> fail; 0.2..limit -> warn; overridable. | experiment:modified_ramsey + parameters |
| 562-570 | Envelope memory 65536 samples/gen; σ=2 us -> ~55056 samples per copy; two copies ~110112 -> "AxisSignalGen: buffer length must be 65536 samples or less". Share one envelope for pi and pi/2. | architecture |
| 598-601 | collect_shots divides accum I by window cycles; tProc compares raw -> multiply threshold by window. | architecture |
| 605-617 | Accumulator sums ro_norm samples of ≤15 bits (12-bit ADC + 3 bits decimation gain; qick_asm.declare_readout overflow note) -> |raw I| ≤ ro_norm·2^15. Fixed 2^24 too small beyond ~0.5 us window: wraps -> wrong-branch pi, no error. Threshold check alone can't catch (threshold sits between blobs). Operands must fit 32-bit signed; immediate < 2^30 (safe_regwi). | architecture (active reset) |
| 647-651 | tProc `read` takes tProc INPUT channel, not readout index; coincide on current firmware (readouts[0]['tproc_ch']==0); resolve explicitly. | architecture |
| 710-713 | DDS free-running & phase-coherent across wait -> phase 0 / 180 are exact inverses independent of tau. | experiment:modified_ramsey |
| 806-810 | Reset readout k measures state BEFORE corrective flip k; row 0 = pre-reset thermal population. | experiment:modified_ramsey |
| 889-892, 903-905 | Streamer stats include polling/transfer latency; physical time base = emitted tProc schedule incl. reset overhead. | architecture |
| 929-931, 946-947 | gap_indices kept empty for schema parity with stitched records; f_ge is the UPPER branch, lower = f_ge - df. | experiment:modified_ramsey / parameters |

### Noise comments (delete)
481, 706, 728, 742-743 (stale, see bugs), 923, 933, 934, 940, 945, 953, 958, 964, 972, 990 (~15 lines). Docstring 263-296 is a cfg reference: move to docs, keep 1-line refs.

### Bugs / suspicious
- 742-743: comment "180 deg default, 0 deg if flip_final_pi2" stale for symmetric (90/270).
- 1035-1037 `save_data(data=None)` -> `data['data']` TypeError when called without data.
- 142-143 docstring "contrast reduced by ~cos(pi*(1+frac))... i.e." garbled.
- Reset pi plays at drive freq (f_avg in symmetric mode, detuned by df/2 from each branch) — reset flip is off-resonant in symmetric/drive_detuned modes (469 comment says intended; physics risk worth documenting).

### Destination
`qicklab/experiments/modified_ramsey.py` (ModifiedRamseyProgram, ModifiedRamsey, plan_parity_mapping, MR_CONTROL_TYPE_CODES). Move `build_control_variants` -> `qicklab/runs/charge_parity.py` (orchestration) or keep beside planner. Extract reset -> `qicklab/core/active_reset.py`, tone coverage -> `qicklab/core/readout.py`, schedule ledger -> `qicklab/core/schedule.py`.

### Style
`from qick import *`; camelCase params (outerFolder, figNum, plotDisp); `print` warnings (use `warnings`/logging); 70-line class docstring.

---

## 2. Experiments/mUndrivenSingleShot.py (1219 lines)

**Purpose:** readout-only single-shot (qubit never driven): IQ cloud blob test + telegraph time-series statistics; optional yoko charge-bias sweep.

### Public symbols
ACQUISITION
- `UndrivenSingleShotProgram(AveragerProgram)` (22-134): `initialize` (sets reps=shots, rounds=1, validates, tone coverage, declares res gen+readouts only), `body` (sync_all; measure, syncdelay=relax_delay), `acquire(soc, load_pulses, progress)`, `collect_shots` (via raw_shot_buffers; list per ro ch of (1,reps)/norm), `scheduled_rep_period_cycles` (raises on register sync), `scheduled_rep_period_us`.
- `UndrivenSingleShot(ExperimentClass)` (642-1219): `__init__(..., yoko=None)`, `_read_indices`, `_sweep_voltages`, `acquire(progress)`, `_acquire_at_bias`, `_print_read_summary`, `_time_unit` (static), `display(data, plotDisp, figNum, ran, max_trace_points)`, `_display_charge_sweep`, `_plot_timeseries`, `_plot_rate_vs_bin`, `save_data`.
- Module consts `_CLOUD_SCALARS, _CLOUD_KEYS, _TS_KEYS, _SWEEP_TS_SCALARS` (625-639): h5 key schema.
ANALYSIS (pure numpy/scipy/sklearn; move to analysis/)
- `analyze_undriven_cloud(i, q, min_separation_sigma=2.0, random_state=0)` (137-263): median center, PCA axis (sign-fixed), 1- vs 2-GMM BIC on projection; n_blobs 0/1/2.
- `block_average_shots(i, q, n_avg)` (266-290).
- `project_onto_axis(i, q, center, axis)` (293-296).
- `two_gaussian_threshold(means, sigmas, weights)` (299-344): ML boundary.
- `autocorrelation_rate(v, dt_us, min_points=5)` (347-422): FFT ACF, exp fit excluding lag 0.
- `rate_vs_bin_size(v, dt_us, threshold, bin_sizes)` (425-455).
- `analyze_undriven_timeseries(cloud, dt_us, raw_projection, raw_dt_us, bin_sizes, min_samples_per_dwell=5.0, min_transitions=10)` (458-621): states, Markov ML rates, interior-run dwell means, ACF, bin sweep, warnings.
All analysis functions referenced only inside this file (unused externally).

### cfg keys
READ: `shots, readout_length, ro_chs, adc_trig_offset, relax_delay, res_ch, nqz, pulse_freq, length, res_phase, pulse_gain, reps` (program); `Read_Indeces, charge_sweep, voltage_start, voltage_end, voltage_step, charge_settle_s, blob_min_separation_sigma (2.0), shot_average (1), ts_bin_sizes ((1,2,4,8,16,32,64))` (experiment); display reads `readout_length, pulse_freq, pulse_gain, relax_delay, blob_min_separation_sigma`.
WRITTEN: `reps = shots`, `rounds = 1` (27-29), `setdefault("length")` (48), `current_voltage` (715). All on the caller's dict.
Runner mapping (singleshot.py:200-216): US_params Shots->shots, relax_delay, min_separation_sigma->blob_min_separation_sigma, average_shots->shot_average, bin_sizes->ts_bin_sizes, charge_sweep, voltage_*, charge_settle_s; Repeat, plotDisp runner-only.

### Saved data schema
Per read tag `r`: `i r, q r, labels/projection/center/cov/axis/axis_angle/n_blobs/blob_* /separation_sigma/secondary_population/bic_1/bic_2/rms_radius/sigma_along_axis/sigma_across_axis + r`, `{_CLOUD_SCALARS}_raw r`, `i_raw, q_raw, projection_raw, n_dropped, shot_index, shot_time_us, ts_index, ts_time_us`, `ts_{_TS_KEYS} r`, `ts_acf_fit_ok r`; global `read_indices, scheduled_rep_period_us, shot_average, timeseries_dt_us, gap_indices`, MR aliases `shots_i, shots_q, shot_index, shot_time_us` (first read). Sweep: `V<k>_<key>`, `sweep_voltages`, `sweep_<scalar><r>`, aliases -> V0.

### Dead / unused
- `acquire(progress)` param unused (not forwarded); `display(ran=..., **kwargs)` unused.
- No commented-out code.

### Lab notes to migrate
| Lines | Condensed | Page |
|---|---|---|
| 1-6 | No |e> reference -> no fidelity; shots in acquisition order at scheduled cadence => uniformly sampled time series; saved under MR key names so analyze_ModifiedRamseyParity (fit_two_state_hmm, psd_rate_estimate) can consume it. | experiment:undriven_single_shot |
| 28, 100-101 | rounds must be 1: acc_buf overwritten each round. di_buf/dq_buf rep-averaged in qick ≥0.2.29x; acc_buf keeps raw stream (Helpers/shot_buffers). NOTE local client qick 0.2.334 still exposes raw di_buf. | architecture |
| 113-114 | Only `synci` advances tProc time; `waiti` from measure(wait=True) does not. Register `sync` in loop => period not compile-time constant. | architecture |
| 194-195 | sklearn reg_covar floors variance -> plausible fit on dead readout; bail on zero spread. | analysis |
| 324-331 | Equal widths: ML boundary may lie outside [m0,m1] once w0/w1 > e^(sep²/2); clamping to midpoint mislabels majority tail and inflates switching rate several-fold. | analysis (telegraph) |
| 347-353 | ACF model C(t)=A e^{-t/τc}, τc = 1/(2γ), τdwell = 1/γ; lag 0 excluded (readout noise variance -> `noise_variance`). | analysis |
| 425-428, 612-619 | Rate falling with bin size = noise crossings; plateau = real telegraph; set shot_average on plateau; never flattens = no resolvable telegraph. | experiment:undriven_single_shot |
| 563, 575-576 | Markov ML rate γij = transitions out of i / time in i; dwell mean from interior runs only (edges truncated). | analysis |
| 600-607 | Shortest dwell < 5 samples -> rate is LOWER bound; shorten relax_delay. | experiment:undriven_single_shot |
| 679-681 | rebuild_singleshot_config() drops charge_params; voltage_* must come via US_params. | parameters (matches memory note) |
| 694 | ramp_to only rejects target > 10 V; negative typo slips -> check |v|>10 here. | hardware |
| 706-707 | finally: restore bias on abort (every later measurement would use parked bias). | keep as 1-line code comment |

### Noise comments (delete)
624, 632, 752, 760, 796-797, 808-809, 982-985, 1131, 1158-1161, 1204-1205 (plot-framing rationale; keep one line max).

### Bugs / suspicious
- 336: disc<0 returns midpoint, contradicting the rationale at 328-331 (midpoint mislabels) — inconsistent fallback.
- 259: `except Exception` swallows ImportError of sklearn and any bug; returns cloud stats silently (only a print).
- `rate_vs_bin_size` name collision with analyze_ModifiedRamseyParity.rate_vs_bin_size (dt_s, different span formula) — must disambiguate when merging.
- `cfg["shots"]` required with no default -> KeyError if absent (27).

### Destination
- Acquisition: `qicklab/experiments/undriven_single_shot.py` (UndrivenSingleShotProgram, UndrivenSingleShot incl. display + charge sweep; consider moving charge-sweep loop to `qicklab/runs/singleshot.py` or a generic `sweep_bias()` helper).
- Analysis: `qicklab/analysis/telegraph.py` <- analyze_undriven_cloud, block_average_shots, project_onto_axis, two_gaussian_threshold, autocorrelation_rate, rate_vs_bin_size, analyze_undriven_timeseries (merge with analyze_ModifiedRamseyParity equivalents; pick one unit convention).

### Style
`from qick import *`; local var `warnings` shadows stdlib module name (355, 470); `Read_Indeces` misspelling (project-wide key); prints instead of logging; 4 x ~10-line summary prints.

---

## 3. Experiments/mOptimizeReadoutandPulse_FF.py (1730 lines)

**Purpose:** 2-D single-shot fidelity/overlap maps: (cavity gain x readout freq) and (qubit gain x qubit freq). 5 near-identical classes + 577 commented-out lines.

### Public symbols
- `ReadOpt_wSingleShotFF(ExperimentClass)` (18-233): sweep `pulse_gain` x `pulse_freq`; g/e shots via SingleShotProgram (cfg["Pulse"] False/True); hist_process fidelity; MixedShots overlap. LIVE.
- `QubitPulseOpt_wSingleShotFF(ExperimentClass)` (235-442): sweep `qubit_gain` x `f_ge`. LIVE.
- `ReadOpt_wSingleShotFF_Higher` (444-674): sweep `pulse_gains` x `mixer_freq` using undefined `SingleShotProgramFF_2StatesMUX`. BROKEN, unused externally.
- `ReadOpt_wSingleShotFF_HigherMUXOLD` (677-907): duplicate of _Higher (minus one print). BROKEN, unused externally.
- `QubitPulseOpt_wSingleShotFF_HigherMUX` (909-1150): qutrit variant, undefined program. BROKEN, unused externally.
All `display` inherited from ExperimentClass (no-op `pass`, Experiment.py:169) — runner calls it (singleshot.py:263,301) for nothing; the figure is saved inside acquire.

### cfg keys
ReadOpt READ: `cav_gain_Start, cav_gain_Stop, cav_gain_Points, trans_freq_start, trans_freq_stop, TransNumPoints, qubit_pulse_style` (+ everything SingleShotProgram reads). WRITTEN (caller dict): `pulse_gains = [g/32000]`, `pulse_gain = int(g)`, `pulse_freq`, `Pulse`.
QubitPulseOpt READ: `qubit_gain_Start, qubit_gain_Stop, qubit_gain_Points, qubit_freq_start, qubit_freq_stop, QubitNumPoints, qubit_pulse_style`. WRITTEN: `qubit_gain, f_ge, Pulse`.
Higher variants READ: `pulse_freqs, cavity_LO, cav_*, trans_*, qubit_pulse_style, qubit_gain01, qubit_gain12, qubit_freq01, qubit_freq12`; WRITTEN: `pulse_gains, mixer_freq, pulse_expt, qubit_gain, qubit_gain12/01, qubit_freq12/01`.

### Dead code
- 1154-1380 commented-out `ReadOpt_wSingleShotFF_Higher`; 1385-1730 commented-out `QubitPulseOpt_wSingleShotFF_Higher` (incl. `_calibrate`, `_acquireTransData`, `_acquireSpecData` referencing nonexistent SingleToneSpectroscopyProgramFF/QubitSpecSliceFFProg). DELETE (577 lines).
- Classes 444-1150 (3 classes) dead + broken -> DELETE.
- `_acquireSingleShotData` in the 3 Higher classes (625-647, 858-880, 1101-1123): never called.
- Commented code: 80, 86, 94-95, 103-105, 150-152, 294, 300, 306-307, 314-316, 362-364, 502, 508, 514-515, 522-524, 570-572, 735, 741, 747-748, 755-757, 802-804, 968, 975, 989-990, 997-999, 1044-1046; inline `#cfg=config,...` at 652, 885, 1128; `# prog.display` 655, 888, 1131.
- Unused params: `__init__(calibrate, cavityAtten)` all classes; `acquire(progress, plotSave, calibrate, cavityAtten)`; `Qubit_Sweep_Index` (255, 929). Unused import `tqdm` (14). `Z_fid`/`Z_overlap` are the same arrays as data['fid_mat']/['overlap_mat'] -> double writes (107-108 etc.). Debug prints 51-52, 56, 62-63. `self.fid/threshold/angle` set in `_acquireSingleShotData` never read.
- Duplicate docstrings (20-31 copied 5x; also inaccurate: describes calibrate/transmission/spec steps that the code does not do).

### Lab notes to migrate
| Lines | Condensed | Page |
|---|---|---|
| 9-11 | hist_analysis_opt = relocated Inductive_Coupler hist_analysis; its hist_process takes print_fidelities= and uses a different contrast calc than QM_Team Helpers/hist_analysis — kept separate to preserve behavior. | architecture |
| 137-159 | Overlap metric: arb/flat_top qubit drive -> MixedShots on concatenated g+e shots; const drive -> MixedShots on e shots only. | experiment:readout_optimize |
| CSTQ03 runner 569-570 (context) | pi/2 optimization: set gain to half and optimize with number_of_pulses=2. | experiment:readout_optimize |

### Noise comments (delete)
1, 38, 40, 44-47 (inline "actual frequency is this number + cavity_LO" stale — no LO add for ReadOpt), 54, 71, 78, 84, 87, 91, 110, 160, 190 inline, 191 inline, 201, 206, 220, 231; same pattern repeated in every class (~138 comment lines in 1-1153).

### Bugs / suspicious
- 652, 885, 1128: `SingleShotProgramFF_2StatesMUX` is not defined or imported anywhere -> NameError on first point of all three Higher classes.
- 988: prints `cfg["qubit_gain12"]`, `cfg["qubit_freq12"]`, etc. -> KeyError unless all four preset.
- 79, 193, 199 etc.: `datetime.datetime` resolves only through `from ...hist_analysis_opt import *` (which does `import datetime`); np/plt also only via star imports.
- 100 + 221: hist_process computed twice per point (once in `_acquireSingleShotData`, once in loop). 312, 432: QubitPulseOpt omits `print_fidelities=False` -> verbose prints.
- 181: ylabel "Cavity Atten (dB" — it is cavity gain; missing ")". 134, 182, 346, 394: xlabel "(GHz)" but values are MHz. 1027 (HigherMUX) ylabel wrong for qubit sweep.
- 88: `pulse_gains = [gain/32000]` legacy normalization (32000 vs 32767 max) — probably unused by SingleShotProgram; check before deleting.
- Mutates the caller's cfg (no copy in ExperimentClass): leaves `pulse_gain/pulse_freq/f_ge/qubit_gain/Pulse` at last sweep value.
- 57, 59, 272, 274: `X[1]-X[0]` IndexError if a sweep has 1 point.
- 233 etc. `save_data(data=None)` crashes.

### Destination
`qicklab/experiments/readout_optimize.py`: one generic `SingleShotSweep2D(ExperimentClass)` (args: outer key/values, inner key/values, axis labels) + thin `ReadoutOptimize` (pulse_gain x pulse_freq) and `QubitPulseOptimize` (qubit_gain x f_ge). Fidelity/overlap -> reuse `qicklab/analysis/single_shot.py`. Drop all Higher/MUXOLD classes and commented code (git history preserves).

### Style
Star imports x3; class names with underscores/mixed case; `idf_cavgain` / `idx_trans` naming; plotting inside acquire; colorbar remove/recreate each point.

---

## 4. Experiments/mAutoCoherence.py (1796 lines)

**Purpose:** orchestrator: sweet-spot search -> f_ge calibration -> AmplitudeRabi pi gain -> readout window opt -> single-shot gain opt (simple or error-amplified) -> T1/T2/T2E, with txt/json summary. Not an experiment class; it is a run.

### Public symbols
- `AUTO_COHERENCE_PARAMS` (69-193): defaults (table below).
- `find_sweet_spot(soc, soccfg, config, save_folder, qubit_freq_center, qubit_readout, yoko, sweet_params=None)` (1460-1530) -> (qubit_freq, voltage, peak_info, log). Used by runs/charge_parity.py:1087.
- `run_auto_coherence(soc, soccfg, config, outerFolder, qubit_readout, qubit_params, yoko=None, auto_params=None)` (1533-1796) -> results dict. Used by runs/coherence.py:287.
Private (all unused externally): `_ramp_to` (200), `_find_two_tone_peaks` (212), `_choose_next_voltage` (273), `_acquire_spec` (286), `_find_pi_gain_from_rabi` (334), `_sync_cfg_to_selected_qubit` (402), `_readout_tone_length` (427), `_run_single_shot_at_gain` (432), `_stage_sweet_spot_search` (497), `_spec_peak_snr` (644), `_stage_calibrate_qubit_freq` (671), `_stage_amplitude_rabi` (747), `_stage_optimize_readout` (841), `_stage_singleshot_optimize` (916), `_optimize_gain_sequence` (1050), `_stage_extended_pulse_opt` (1132), `_stage_run_t1` (1249), `_stage_run_t2` (1294), `_stage_run_t2e` (1348), `_save_summary` (1411). Constant `_T2E_CLOCK_STEP_US` (64).

### AUTO_COHERENCE_PARAMS (key -> default, meaning)
Spec (Stage 1/1.5):
- `spec_span` 1.0 MHz: ± span around centre. `spec_num_pts` 101. `spec_reps` 10. `spec_rounds` 10. `spec_relax_delay` 1500 us. `spec_sigma` 2.0 us (gaussian drive σ; larger σ -> sharper peaks). `spec_gain` 700 DAC. `spec_qubit_length` 2.0 us (flat length, unused when Gauss=True, which is hard-coded).
Sweet spot (Stage 1):
- `skip_sweet_spot_search` False: skip Stage 1, use qubit_params f, hold yoko.
- `ss_search_df_trigger` 0.50 MHz: peak sep that triggers the half-period jump (Strategy A only).
- `ss_accept_sep` 0.08 MHz: sep small enough to accept sweet spot.
- `ss_dV` 5e-4 V per walk step. `ss_voltage_min` 0.000 V, `ss_voltage_max` 0.010 V. `ss_max_tries` 200. `cd_period_mv` None (mV charge-dispersion period; enables Strategy A half-period step).
Freq cal (Stage 1.5):
- `calibrate_qubit_freq` True. `freqcal_auto_gain` True. `freqcal_min_snr` 4.0 (MAD-based peak SNR). `freqcal_gain_growth` 1.8. `freqcal_max_gain` 30000 (under 32767 ceiling). `freqcal_max_gain_retries` 5.
Rabi (Stage 2):
- `rabi_max_gain` 12000. `rabi_num_steps` 201. `rabi_reps` 15. `rabi_rounds` 15. `rabi_relax_delay` 3500 us. `rabi_sigma` None (-> qubit_params sigma). `rabi_sigma_min` 0.01 us. `rabi_max_osc_peaks` 3 (above -> σ x0.70, comment says "halved" — stale). `rabi_max_sigma_retries` 10.
Single shot (Stage 3):
- `ss_shots` 1000 (per scan point). `ss_full_shots` 2000 (final). `ss_relax_delay` 3500 us. `ss_readout_time` 15 us. `ss_adc_offset` 1 us. `ss_target_fidelity` 0.70 (warn only). `ss_gain_pts` 21. `ss_max_scan_expansions` 2. `ss_gain_span_growth` 1.8. `ss_gain_span_frac` 0.20 (± fraction of pi gain).
Readout opt (Stage 2.5):
- `auto_readout_opt` True. `readout_length_start` 5.0 us, `readout_length_stop` 30.0 us, `readout_length_pts` 6. `adc_offset_start` 0.2 us, `adc_offset_stop` 3.0 us, `adc_offset_pts` 5. (Winners overwrite ss_readout_time/ss_adc_offset and base_cfg readout_length/adc_trig_offset/length.)
Extended (error amplification):
- `extended_pi_pi2_opt` False. `pi_nsteps_list` [1,3,5,7,11] (odd N pi -> |e>). `pi2_nsteps_list` [2,6,10,14,22] (N=2(2k+1) pi/2 -> |e>). `ext_gain_pts` 51. `ext_pi_gain_span_init` 0.20. `ext_pi2_gain_span_init` 0.20. `ext_gain_span_shrink` 0.40 (span x per N step).
T1: `T1_step` 40 us, `T1_expts` 60, `T1_reps` 20, `T1_rounds` 20, `T1_relax_delay` 3500 us, `T1_repetitions` 1.
T2 Ramsey: `T2_step` 0.1 us, `T2_expts` 201, `T2_reps` 20, `T2_rounds` 20, `T2_relax_delay` 3500 us, `T2_repetitions` 1, `T2_freq_shift` 0.0 MHz (artificial detuning).
T2E: `T2E_max_us` 200, `T2E_expts` 201, `T2E_reps` 25, `T2E_rounds` 25, `T2E_relax_delay` 3500 us, `T2E_num_pi_pulses` 1 (must be odd; not enforced), `T2E_repetitions` 1.
CSTQ03 overrides (CSTQ03_BFC.py:587-604): skip_sweet_spot_search=True, calibrate_qubit_freq=False, ss_gain_span_frac=0.6, ss_gain_pts=100, auto_readout_opt=True, ...

### cfg keys
Never mutates caller config (all via `cfg | {...}` copies). READ: `length`, `qubit_ch` (via get). qubit_params read: `[str(q)]["Readout"]["Frequency"|"Gain"]`, `["Qubit"]["Frequency"|"Gain"|"sigma"|"flattop_length"]`.
WRITTEN into copies: sync (413-422): `pulse_freq, pulse_gain, qubit_gain, f_ge, qubit_gains, f_ges, sigma, flattop_length, Read_Indeces (int), Qubit_number`. Spec (298-311): `reps, rounds, Gauss=True, sigma, qubit_gain, qubit_length, SpecSpan, SpecNumPoints, step, start, expts, relax_delay`. SS (451-469): `read_pulse_style, readout_length, adc_trig_offset, length, pi2_SS=False, qubit_pulse_style="arb", sigma, qubit_gain, f_ge, qubit_gains, f_ges, shots, relax_delay, flattop_length, number_of_pulses, Read_Indeces`. Rabi (784-795): `start, step, expts, reps, rounds, sigma, f_ge, relax_delay, flattop_length, Qubit_number`. T1 (1261-1273): `start, step, expts, reps, rounds, pi_gain, relax_delay, sigma, flattop_length, f_ge, Qubit_number`. T2 (1314-1327): `start, step, phase_step, expts, reps, rounds, pi_gain, pi2_gain, relax_delay, f_ge(+shift), sigma, flattop_length`. T2E (1376-1390): + `num_pi_pulses, Qubit_number`. Readout opt -> base_cfg `readout_length, adc_trig_offset, length` (1699-1701).

### Dead / unused
- `rabi_data`, `rabi_inst` (778-779, 824-825) assigned never used.
- `qubit_readout` param unused in `_stage_sweet_spot_search`, `_stage_calibrate_qubit_freq`, `_stage_run_t2`; `_acquire_spec` returns x_pts/avgi/avgq that every caller discards.
- `_stage_run_t2` 1306-1311: `phase_step = deg2reg(0.0)` always 0; try/except dead logic.
- `spec_qubit_length` meaningless with Gauss=True (hard-coded 301).
- runs/coherence.py imports `AUTO_COHERENCE_PARAMS`, `find_sweet_spot` but never uses them.

### Lab notes to migrate
| Lines | Condensed | Page |
|---|---|---|
| 6-19 | Pipeline stages 1, 1.5, 2, 2.5, 3, 4-6 (rewrite; numbers stale — see bugs). | experiment:auto_coherence |
| 37-42 | Contract: caller globals/config/qubit_params never mutated; existing experiment classes unmodified. | experiment:auto_coherence |
| 60-64 | T2E step quantum 0.00232515 us (1 tProc cycle, ~430.08 MHz) x (num_pi+1); must match CSTQ02/coherence.py. | architecture |
| 69-193 | Param meanings (table above). | parameters |
| 86-90, 1470-1477 | Sweet-spot strategy A: step half charge-dispersion period from current V, typically converges in 1-2 spec acquisitions; B: walk tracking minimum sep, return to best V. | experiment:auto_coherence |
| 150-159 | Error amplification: odd N pi; N=2(2k+1) pi/2 -> |e>; best gain becomes centre, span x shrink each step. | experiment:auto_coherence |
| 369-373 | Rabi trace orientation: flip so |g>->0 using first ≤5 pts median. | analysis (rabi) |
| 648-649 | Peak SNR: median baseline, 1.4826·MAD noise. | analysis (spectroscopy) |
| 1486-1488, 1592-1593 | ExperimentClass concatenates outerFolder + path with no separator -> folder must end with "/". | architecture |
| 1583-1591 | Output tree: outerFolder/AutoCoherence/run_<ts>/{auto-Spec, auto-AmplitudeRabi, auto-SingleShot, auto-ReadoutOpt, auto-PiOpt, auto-Pi2Opt, auto-T1, auto-T2, auto-T2E} + auto_coherence_summary_<ts>.txt/.json. | experiment:auto_coherence |

### Noise comments (delete)
60-63/65-68/196-198/493-495/1456-1458 banners; section banners inside dict 70, 80, 99, 115, 126, 138, 150, 168, 176, 185; 228, 513, 528, 534, 547, 557, 584, 626, 1028, 1071, 1119, 1170, 1194, 1219, 1440, 1576, 1579, 1582, 1600, 1619-1621, 1633, 1657, 1673, 1687, 1706, 1738, 1756, 1764, 1772, 1780; 1306-1307 (stale). Long numpydoc blocks 1479-1516, 1539-1575 -> condense.

### Bugs / suspicious
- 14-18 docstring stale: "300 shots during scan, 500 final" vs ss_shots=1000/ss_full_shots=2000; "AutoCoherence_<timestamp>" vs actual AutoCoherence/run_<timestamp>/ (1594-1596). 123: "sigma is halved" vs code x0.70 (832).
- 92 vs 212: `ss_accept_sep`=0.08 MHz < `_find_two_tone_peaks` min_sep_mhz=0.10 -> two peaks are never returned closer than ~0.1 MHz, so `sep < accept` is unreachable for two-peak spectra; acceptance only happens via single peak.
- 307-308: spec grid start=c-span, step=2·span/N -> last point c+span-step (asymmetric by one step).
- 558-583: Strategy A discards the pre-step voltage/sep from best-tracking; if the half-period jump makes it worse, search can't return to the start voltage.
- 821-832: reducing σ with fixed `rabi_max_gain` can push pi gain beyond the sweep (no check); fallback `argmax`.
- 1363: `T2E_num_pi_pulses` "must be odd" not enforced.
- 1306-1311: `except Exception` around deg2reg; phase_step always 0.
- `_run_single_shot_at_gain` 451-469 forces `qubit_pulse_style="arb"` but passes `flattop_length` from qubit_params — if non-None, meaning differs between experiments.
- Calls methods unbound (`QubitSpecSliceFF.acquire(inst)`) — works but non-idiomatic.

### Destination
`qicklab/runs/auto_coherence.py` (run_auto_coherence + stages + AUTO_COHERENCE_PARAMS as a dataclass/defaults). `find_sweet_spot`, `_stage_sweet_spot_search`, `_choose_next_voltage` -> `qicklab/runs/sweet_spot.py` (shared with charge_parity). `_find_two_tone_peaks`, `_spec_peak_snr` -> `qicklab/analysis/spectroscopy.py` (dedupe with utils.find_two_tone_peaks). `_find_pi_gain_from_rabi` -> `qicklab/analysis/rabi.py`. `_ramp_to` -> `qicklab/hardware/yoko.py` (one ramp_to). `_save_summary` -> generic `qicklab/core/summary.py` or keep. `_T2E_CLOCK_STEP_US` -> derive from soccfg.

### Style
Unbound-method calls; 11-arg stage functions (pass a context/dataclass); `except Exception`; `print` + manual log list (use logging); `|` dict merge requires py≥3.9 (fine).

---

## 5. Experiments/mZeroSpanParity.py (737 lines)

**Purpose:** zero-span two-tone (CW readout + CW parity drive) parity-switching acquisition; strobe (per-rep IQ) and decimated (raw ADC trace) paths; fail-fast cfg validation.

### Public symbols
- `_STROBE_REQUIRED`, `_DECIMATED_REQUIRED`, `_SHARED_REQUIRED` (54-68).
- `_validate_cfg(cfg, soccfg)` (71-205): raises RuntimeError on first violation.
- `_ZeroSpanParityProgBase(AveragerProgram)` (208-266): `_const_length_us` (abstract), `_setup_two_tones`, `initialize`, `body` (pulse qubit t=0; measure syncdelay=0). Reads `res_ch, nqz, mixer_freq, ro_chs, qubit_ch, qubit_nqz, read_length, read_pulse_freq, parity_drive_freq, qubit_gain, res_phase, pulse_gain, adc_trig_offset`.
- `ZeroSpanParityProgStrobe` (269-285): length = `sample_period_us`.
- `ZeroSpanParityProgDecimated` (288-305): length = `capture_length_us`.
- `ZeroSpanParity(ExperimentClass)` (308-578): `__init__` (validate, set reps, build prog), `set_qubit_gain` (strobe only; rebuild prog), `acquire`, `_acquire_strobe`, `_acquire_decimated`, `save_data` (h5 append, own schema), `display` (no-op).

### cfg keys
READ: `mode, start_src, res_ch, qubit_ch, ro_chs, nqz, qubit_nqz, mixer_freq, read_pulse_freq, parity_drive_freq, qubit_gain, pulse_gain, res_phase, adc_trig_offset, read_length`; strobe `sample_period_us, reps_per_chunk`; decimated `capture_length_us, soft_avgs, n_captures (1), allow_soft_avgs (False)`; implicit via AveragerProgram: `reps`, `soft_avgs`, **`rounds` (overrides soft_avgs)**.
WRITTEN: `reps = reps_per_chunk` (strobe, 333, 358) or `1` (decimated, 336); `qubit_gain` (350). On caller's dict.
NOTE naming differs from rest of codebase: `read_length` (not `readout_length`), `read_pulse_freq` (not `pulse_freq`).

### Fail-fast validation (group-specific)
- Presence: all `_SHARED_REQUIRED`; mode in {strobe, decimated}; mode extras.
- Rule 1 (strobe): `sample_period_us >= adc_trig_offset + read_length + 1.0 us`.
- Rule 2 (strobe) / 3 (decimated): `us2cycles(sample_period_us | capture_length_us, gen_ch=qubit_ch and res_ch) <= 65535` (16-bit const-pulse length).
- Rule 4 (strobe): `reps_per_chunk <= soccfg.readouts[ro].avg_maxlen`.
- Rule 5 (decimated): `round(read_length * f_output) <= buf_maxlen` (nominal estimate).
- Rule 9 (decimated): `capture_length_us >= adc_trig_offset + read_length`.
- Rule 8: `parity_drive_freq in [-f_dds/2, +f_dds/2]` of qubit gen (skipped if soccfg lacks gens/f_dds).
- Rules 6-7 caller-level (Recalibrate flags vs cached values), enforced in orchestrator, not here.
- In `_acquire_decimated`: `n_captures >= 1`; `soft_avgs > 1` requires `allow_soft_avgs=True`.
- `set_qubit_gain` raises if mode != strobe.

### Dead / unused
- `ro_ch` local in `_acquire_strobe` (386) unused. `display` no-op. `"n_chunks"` scalar key only written by utils.chunked_acquire.
- 581-737 `__main__` self-test (fake soccfg, validation rules, soft_avgs gate, strobe normalization) -> move to `tests/test_zero_span_parity.py`.

### Lab notes to migrate
| Lines | Condensed | Page |
|---|---|---|
| 10-33 | cfg contract (keys, units, mode extras). | experiment:zero_span_parity + parameters |
| 38-43, 429-435 | On some firmware soccfg readouts f_output is empirically NOT the decimated rate returned by acquire_decimated (loopback test); t_us nominal; read_length_us, capture_length_us, samples_per_capture, decimated_fs_source persisted for post-hoc reconstruction. (See bug: likely caused by declare_readout length in tProc cycles.) | experiment:zero_span_parity |
| 60-62 | n_captures>1 stitches back-to-back acquire_decimated with gap_indices (mirrors chunked_acquire for strobe). | experiment:zero_span_parity |
| 141-153 | Decimated buffer sized by declared readout length, not capture length; estimate may differ by O(1) sample where tProc and readout clocks differ; hardware loopback must confirm. | experiment:zero_span_parity |
| 177-183 | QICK DDS band is [-f_dds/2, +f_dds/2] (qick_asm freq2reg range check), not [0, f_dds]; qubit gen declared without mixer. QickConfig has __getitem__ but no __contains__ -> `"gens" in soccfg` raises KeyError; use try/except. | architecture |
| 213-217, 273-279 | Strobe: both tones held one sample_period; reps back-to-back syncdelay=0 => drive effectively CW except small inter-rep tProc gap. Decimated: tones held for capture window. | experiment:zero_span_parity |
| 328-331 | AveragerProgram reads cfg["reps"] in make_program() at construction -> set before building the program. | architecture |
| 351-356 | set_qubit_gain re-syncs reps from reps_per_chunk (validate's run_static_contrast bumps it post-construction; otherwise sidecar reps disagree with run). | experiment:zero_span_parity |
| 387-397 | Strobe I/Q normalized by us2cycles(read_length, ro_ch=0) to match mSingleShotProgramFFMUX.collect_shots, which HARD-CODES ro_ch=0; apriori separator from get_apriori_separator_from_singleshot is in those units. | architecture |
| 401-405 | di_buf/dq_buf indexed by readout DECLARATION order, not absolute channel; soccfg["readouts"][ro_ch] IS keyed by absolute channel. | architecture |
| 445-448 | soft_avgs>1 averages independent captures -> destroys parity trajectories. | experiment:zero_span_parity |
| 465-467 | Do not pass soft_avgs to acquire_decimated (AveragerProgram injects it -> kwarg collision). | architecture |
| 474-480 | acquire_decimated returns per ro_ch: (2, length) for reps=1, (reps, 2, length) for reps>1 (np.moveaxis); some paths (length, 2). | architecture |
| 517-520 | samples_per_capture = actual first-capture length, not total/n_captures. | experiment:zero_span_parity |
| 534-537 | h5 opened "a" so ExperimentClass.save_config attr is not truncated; datasets delete-then-recreate for idempotent resave. | architecture |
| 8, 73, 102... | "spec §5.3 rules 1-9" refers to docs/superpowers/specs/2026-05-16-bfc-charge-parity-zero-span-design.md, deleted in commit 0f0a51f (recover from 0f0a51f^) — rules must be restated in docs. | experiment:zero_span_parity |

### Noise comments (delete)
78, 96, 122, 339, 373-374, 376-377 (partly), 543-560 inline restating, 562-564; module-docstring list 4-8 (restates class names); 672-675, 698-723 test narration (moves with tests).

### Bugs / suspicious
- **234: `declare_readout(length=self.us2cycles(cfg["read_length"]))` omits `ro_ch=ch`**; qick 0.2.334 declare_readout length = number of decimated samples (qick_asm.py:1131). Gives tProc-cycle count, so the integration window/decimated record is `read_length*f_time/f_output` too long/short. Plausible root cause of the "f_output is not the true decimated rate" observation (38-43, 429-435). Also makes the strobe normalization (398, divides by readout-clock count) inconsistent with the actual number of summed samples (scale error f_time/f_output) and makes rule 5 (156) estimate the wrong count. MR/ARV/Undriven all use `ro_ch=ch`.
- 31-34 of qick averager_program: `cfg["rounds"]` overrides `soft_avgs`; ZSP gates only `soft_avgs` (444-455). A `rounds` key in cfg would bypass the gate (decimated) and soft-average strobe rounds (di_buf = last round only). zero_span.py:106 builds a fresh cfg without rounds -> latent.
- 409: strobe `t_us = idx * sample_period_us` ignores per-rep tProc overhead (synci(200) is init-only, but measure/sync per rep adds time); MR/Undriven derive the period from the compiled schedule.
- 41: references `_loopback_check_ZeroSpanParity.py`, deleted in commit 10faf0f.
- 256: `synci(200)` raw cycles (others use `sync_all(us2cycles(0.2))`).

### Destination
`qicklab/experiments/zero_span_parity.py` (keep `_validate_cfg` as `validate_cfg`, programs, experiment). `__main__` -> `qicklab/tests/test_zero_span_parity.py`. h5 writer could use core saver if it supports attrs.

### Style
Local imports inside methods (`datetime` 370/424, `h5py` 531); semicolon statements (483-485, 498, 612-668); capitalized locals `I, Q`; RuntimeError for config errors (ValueError more apt).

---

## 6. Experiments/mActiveResetVerify.py (448 lines)

**Purpose:** differential validation of the MR hardware active reset: [prep pi] -> [reset] -> N verification readouts, P(|g>) per read.

### Public symbols
- `ActiveResetVerifyProgram(AveragerProgram)` (7-339): `initialize`, `active_reset_to_g` ("copy" of MR, diverged), `body`, `acquire(soc, load_pulses, start_src, progress)`, `collect_shots` -> (n_verify_reads, reps) I and Q.
- `ActiveResetVerify(ExperimentClass)` (342-448): `acquire(progress, debug)` classifies against perpendicular bisector of `g_center`/`e_center`; `display`; `save_data`.

### cfg keys
READ: `sigma, readout_length, ro_chs, adc_trig_offset, verify_relax_delay (5.0), relax_delay, reset_readout_relax_delay (1.0), post_reset_wait (0.0), qubit_ch, res_ch, nqz, qubit_nqz, prep_excited (False), use_active_reset (False), reset_cycles (1), reset_ground_below_threshold (True), reset_force_pi (False), n_verify_reads (5), length, pulse_freq, f_ge, res_phase, pulse_gain, pi_gain, readout_threshold, reps; g_center, e_center` (experiment).
WRITTEN: `setdefault("length")` (119).
Runner (singleshot.py:24-71) also passes `flattop_length, rounds=1, Qubit_number` — ignored by the program.

### Dead / unused
- `readout_tone_extension_cycles` (150) unused; `acquire(debug)` unused; `display(**kwargs)`.

### Lab notes to migrate
| Lines | Condensed | Page |
|---|---|---|
| 20-30 | Reset from thermal equilibrium can't distinguish working reset from cold qubit -> 4 conditions: prep g/reset off (thermal baseline), prep e/off (control, stays excited), prep g/on, prep e/on (KEY PROOF). Read N times: QND working reset = flat high P(g). Runner adds forcePI diagnostics (prep e forcePI ≈ prep g baseline if pi good; prep g forcePI ≈ prep e reset-off). Verdict: pg_e_on ≥ 0.9·pg_g_on and recovery ≥ 0.3. | experiment:active_reset_verify |
| 38-42 | Last verification read uses relax_delay (rethermalize before next rep's prep); others verify_relax_delay. | experiment:active_reset_verify |
| 57-60, 94-96 | reset_force_pi: fire corrective pi unconditionally -> bare post-readout pi fidelity decoupled from threshold. | experiment:active_reset_verify |
| 98-106 | TATQ01/BFE 2026-06-05/06: ground-state damage tracked the below-zero fraction of the g blob; the g_I≈0 sweep lost exactly half its ground shots => tProc compares unsigned. Claim "2^24 >> |raw I| (~1e4-1e5)" is SUPERSEDED by MR 605-615 (|raw I| ≤ ro_norm·2^15; 2^24 ~9x too small for long windows per memory 2026-07-28). | architecture (active reset), mark superseded |
| 215-218 | Diagnostic: pi SKIPPED when (r_read reset_skip_op r_thresh); cross-check against g_I/e_I printed by calibrate_active_reset_readout. | experiment:active_reset_verify |

### Noise comments (delete)
84, 115-117 (says "Match ModifiedRamsey exactly" — no longer true), 167, 203-204, 212-213, 254-257, 283, 296, 300-302, 316, 332, 380.

### Bugs / suspicious
- **107: `cmp_offset = 1 << 24` fixed**; MR uses `int(ro_norm) << 15` (mModifiedRamsey.py:615). For ro_norm > 512 cycles (window ≳0.5 us at typical readout clock) shots with raw I < -2^24 wrap -> wrong reset decision; e.g. 15 us window -> ~9x too small (memory note). ARV therefore no longer validates MR's actual mechanism. Also lacks the `cmp_offset < 2^30` guard.
- **252: `self.read(ro_ch, ...)`** passes readout index, not `soccfg["readouts"][ro_ch]["tproc_ch"]` (MR 652-658 resolves it). Silent wrong buffer on firmware where mapping isn't identity.
- No `flattop_length` guard (MR 323-330); runner passes `flattop_length=ctx.qubit_flattop` -> if pi_gain calibrated for flat_top it is replayed on a 4σ gaussian (mis-rotation).
- No `rounds != 1` guard (MR 313-319); collect_shots reads only last round.
- Reset/prep pi at `f_ge` while MR uses drive freq — fine for standard scheme, differs for symmetric.
- 446-448 `save_data(data=None)` crash. 440 `plt.show(block=False)` vs MR `block=True` inconsistency.
- Docstring 15-18 / 234-236 claims "faithful/verbatim copy" — false (see above).

### Destination
`qicklab/experiments/active_reset_verify.py`, using the shared `qicklab/core/active_reset.py` mixin (so ARV tests MR's exact code path, with `force_pi` flag). Bisector classification -> `qicklab/analysis/single_shot.py::classify_bisector`. Verdict logic now in runs/singleshot.py should move with it (or to runs/active_reset.py).

### Style
`from qick import *`; duplicated validation/tone code; print diagnostics.
