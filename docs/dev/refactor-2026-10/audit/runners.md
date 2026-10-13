# Audit: runners group (orchestration layer)

Root: `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Runners/`.
Read-only audit; nothing modified. `runs/charge_parity.py` (1976 lines) is NOT in this group but is wired by
`CSTQ03_BFC.py` and imported by `runs/__init__.py`; it is referenced below only where needed to classify runner params.

Abbreviations: `EXP` = `...Client_modules.Experiments`, `ctx` = `runs.context.Context`.
"4-call pattern" = `X.acquire(i)`, `X.display(i, d, ...)`, `X.save_data(i, d)`, `X.save_config(i)` (class-method call style).

---

## 0. Cross-cutting: the two config regimes (task item c)

### Regime A — `build_context()` (context.py:121-227)
`config = BaseConfig | (trans_config | qubit_config | expt_cfg | tl | ts | charge_params)`, then
`config["FF_Qubits"] = FF_Qubits`, `config["cavity_min"] = cavity_min`.

| source | keys (value) |
|---|---|
| BaseConfig (Calib/initialize4Q.py:17-39) | `res_ch`=0, `qubit_ch`=1, `mixer_freq`=0.0, `ro_chs`=[0], `reps`=1000, `nqz`=2, `qubit_nqz`=1, `relax_delay`=3000, `res_phase`=0, `pulse_style`="const", `length`=30, `pulse_gain`=30000, `adc_trig_offset`=1, `cavity_LO`=0, `cavity_winding_freq`=0, `cavity_winding_offset`=0, `trig_buffer_start`=0.02, `trig_buffer_end`=0.02, `trig_delay`=0.082 |
| trans_config (L179-195) | `reps`=1000, `pulse_style`="const", `length`=adc_trig_offset_us+readout_length_us, `readout_length`=readout_length_us, `adc_trig_offset`=adc_trig_offset_us, `pulse_gain`=Readout.Gain, `pulse_freq`=Readout.Frequency, `TransSpan`=Transmission_params['span'], `TransNumPoints`=Transmission_params['num_points'], `cav_relax_delay`=30 |
| qubit_config (L196-204) | `qubit_pulse_style`="const", `qubit_gain`=Spec_relevant_params['qubit_gain'] (SPEC drive gain, not pi gain), `qubit_freq`=Qubit.Frequency, `qubit_length`=Spec['qubit_length'], `SpecSpan`, `SpecNumPoints`, `current_voltage`=start_voltage |
| expt_cfg (L205-209) | `step`=2*SpecSpan/SpecNumPoints, `start`=qubit_freq-SpecSpan, `expts`=SpecNumPoints |
| tl | `tone_length` (read by mConstantTwoTone) |
| ts | `start_ts_gain`, `end_ts_gain`, `ts_step` -> **read nowhere (dead keys)** |
| charge_params | `voltage_start`, `voltage_end`, `voltage_step` (read by charge_parity.run_charge_sweep and `_charge_sweep_voltages` fallback) |
| post | `FF_Qubits` (shared ref to module dict), `cavity_min` (only read by `sanity_dump`; runs use `ctx.cavity_min`) |

NOT set in A: `sigma`, `f_ge`, `flattop_length`, `pi_gain`, `pi2_gain`, `shots`, `qubit_gains`, `f_ges`, `Read_Indeces`, `pi2_SS`, `read_pulse_style`, `Gauss`. Each run_* adds what it needs.
Also validates readout_length_us>0, adc_trig_offset_us>=0 (None -> BaseConfig 1 us) — AFTER opening the yoko and ramping.
Side effects: `makeProxy()`, opens yoko `GPIB1::9::INSTR`, `:SOUR:FUNC VOLT`, `:OUTP ON`, `ramp_to(start_voltage)`, `print(config)`.

### Regime B — `rebuild_singleshot_config(ctx, SS_params)` (context.py:74-118)
`ctx.config = BaseConfig | UpdateConfig`, then `FF_Qubits`, `Read_Indeces`=ctx.Qubit_Readout. Built from **BaseConfig, not from ctx.config**.

UpdateConfig: `read_pulse_style`="const", `length`=SS.ADC_Offset+SS.Readout_Time, `readout_length`=SS.Readout_Time, `adc_trig_offset`=SS.ADC_Offset, `pi2_SS`=SS.pi2_SS, `pulse_gain`=ctx.cavity_gain, `pulse_freq`=ctx.resonator_frequency_center, `qubit_pulse_style`="arb", `sigma`=ctx.qubit_sigma, `qubit_gain`=ctx.qubit_gain (**pi gain**), `f_ge`=ctx.qubit_frequency_center, `qubit_gains`=[Qubit.Gain for q in SS.Qubit_Pulse], `f_ges`=[Qubit.Frequency ...], `shots`=SS.Shots, `relax_delay`=SS.relax_delay, `flattop_length`=ctx.qubit_flattop.

Differences A -> B (important for preservation):
- Dropped: `TransSpan`, `TransNumPoints`, `cav_relax_delay`, `qubit_freq`, `qubit_length`, `SpecSpan`, `SpecNumPoints`, `current_voltage`, `step`, `start`, `expts`, `tone_length`, ts keys, `voltage_*`, `cavity_min`.
- **Carry-overs discarded**: fitted `pulse_freq` (from run_transmission_fit/run_transmission_sweep) reset to Qubit_Parameters value; calibrated `res_phase` (from calibrate_active_reset_readout) reset to 0.
- `qubit_gain` changes meaning: A = spectroscopy gain (Spec_relevant_params['qubit_gain']=1000); B = pi-pulse gain from Qubit_Parameters. Refactor should split into `spec_gain` / `pi_gain`.
- `reps` stays BaseConfig 1000 in B (programs set reps=shots).
- ctx scalars (cavity_gain etc.) are unchanged by the rebuild.

Persistent `ctx.config` mutations in this group (carry-overs): `pulse_freq` (basic.py:86, :159/:161), `res_phase` (calibration.py:135, :154). `interleave` temporarily swaps `ctx.config` and restores in `finally`.

---

## 1. `Runners/CSTQ03_BFC.py` — 814 lines
Purpose: session script; module-level params + RunX flags; builds ctx and dispatches run_* in a fixed order. Executes on import (no `__main__` guard).
Imports: `from ...Runners.runs import *` (star; pulls ~110 names incl. np, plt, os, time, datetime, all experiment classes). Imported by: nobody.

### (a) Module-level name inventory
Class: D = DEVICE (per chip), R = EXPERIMENT RECIPE (device-independent default), S = SESSION knob, U = UNUSED.

| name | line | type | consumer | class |
|---|---|---|---|---|
| temp_dir_Q4 | 15 | str | none | U |
| _QubitFolderRoot | 18 | str | QubitFolders | S (data root) |
| QubitFolders | 19 | dict[str,str] Q1-6 | outerfoldername in both param dicts | S |
| Qubit_Parameters_v2b | 22-52 | dict | none | U (D data for "CSTQ03 v2b nu cell"; archive into devices/) |
| Qubit_Parameters | 56-86 | dict '1'..'6' -> {Readout{Frequency,Gain}, Qubit{Frequency,Gain,pi2_Gain,sigma,flattop_length}, outerfoldername} | build_context; ctx.Qubit_Parameters in rebuild_singleshot_config, run_qubit_optimize, run_auto_coherence; Amplitude_Rabi_params | D |
| start_voltage | 88 | float 0.0 | build_context (ramp, current_voltage, ctx.start_voltage -> zero_span) | S |
| Qubit_Readout | 90 | int 5 | build_context | S |
| Qubit_Pulse | 91 | int 5 | build_context, Amplitude_Rabi_params, SS_params | S |
| yoko_fixed | 92 | bool | ctx.yoko_fixed -> charge_parity run_charge_sweep / run_charge_transmission_sweep | S |
| cavity_min | 93 | bool | ctx.cavity_min (run_transmission_sweep, charge transmission), config key (dead) | D (resonator dip vs peak) |
| Readout_Time | 106 | float 15 | build_context readout_length_us | D (per qubit; SS_params comment: Q1 15 us, Q5 5 us) |
| ADC_Offset | 107 | float 0.3 | build_context adc_trig_offset_us | D |
| Constant2Tone | 114 | flag | run_constant_two_tone | S |
| tl | 115 | dict {tone_length:151} | merged into config (build_context) | R |
| ConstantTone | 116 | flag | run_constant_tone | S |
| RunTransmissionSweep | 118 | flag | **run_transmission_fit** | S |
| Transmission_params | 119 | dict reps,rounds,num_points,span | build_context(span,num_points); run_transmission_fit(reps,rounds); passed to run_transmission_sweep but ignored | R |
| RunTransmissionSweeps | 121 | flag | **run_transmission_sweep** (name swapped vs above) | S |
| ts | 122 | dict | merged into config; keys read nowhere | U |
| Run2ToneSpec | 124 | flag | run_two_tone_spec | S |
| RunSpecGainLengthSweep | 125 | flag | run_spec_gain_length_sweep | S |
| RunTrans_QubitSpec | 126 | flag | run_trans_qubit_spec | S |
| RunChargeSweep | 127 | flag | run_charge_sweep (charge_parity) | S |
| charge_params | 128 | dict voltage_start/end/step | build_context -> config | S |
| RunChargeTransmissionSweep | 142 | flag | run_charge_transmission_sweep | S |
| ChargeTransmission_params | 143-147 | dict reps,rounds,span,num_points,fit,settle_s,voltage_* | run_charge_transmission_sweep (all keys) | R (+voltage_* S) |
| Spec_relevant_params | 148-158 | dict qubit_gain,SpecSpan,SpecNumPoints,qubit_length,reps,rounds,Gauss,sigma,gain,relax_delay,display,min_sep_MHz,fit_window_mhz,prominent_ratio,sweep_lengths,sweep_gains | build_context; run_two_tone_spec; run_spec_gain_length_sweep; run_trans_qubit_spec; run_charge_sweep; run_two_tone_charge_dispersion_quasicw; run_charge_dispersion_quasicw | R (qubit_gain/gain arguably D) |
| StabilizeTwoTone | 160 | flag | none | U |
| RunChargeDispersionQuasiCW | 162 | flag | run_charge_dispersion_quasicw | S |
| RunChargeDispersionRamsey | 163 | flag | run_charge_dispersion_ramsey | S |
| ChargeDispersion_params | 166-172 | dict upper_freq,lower_freq,probe_freq,relax_delay,repetitions | probe_freq,relax_delay,repetitions used; **upper_freq/lower_freq unused; `df` required by run_charge_dispersion_ramsey but missing** | D (freqs) + R |
| Run2ToneChargeDispersionQuasiCW | 174 | flag | run_two_tone_charge_dispersion_quasicw | S |
| RunModifiedRamsey | 182 | flag | run_modified_ramsey | S |
| TwoToneChargeDispersion_params | 184-208 | dict (19 keys) | run_two_tone_charge_dispersion_quasicw (all keys used) | R (voltage window D) |
| ModifiedRamsey_params | 210-391 | dict (37 keys) | run_modified_ramsey (all keys read) | R + D (`df`, `f_ge`, mapping probs, reset_readout_relax_delay are device) |
| RunActiveResetVerify | 404 | flag | run_active_reset_verify | S |
| ActiveResetVerify_params | 405-418 | dict n_verify_reads,verify_relax_delay,reps,reset_cycles,reset_readout_relax_delay,post_reset_wait,relax_delay,plotDisp | run_active_reset_verify (all) | R (relax/reset delays D-dependent) |
| RunModifiedRamsey_Control | 420 | flag | run_modified_ramsey_control | S |
| ModifiedRamsey_Control_params | 422-460 | dict | run_modified_ramsey_control; `Gauss` unused; `setdefault` adds hysteresis_low/high, window_ms (mutates this dict) | R + D (cd_max_mhz, cd_period_mv) |
| RunChiShift | 462 | flag | run_chi_shift | S |
| ChiShift_params | 463-468 | dict reps,rounds,TransSpan,TransNumPoints,cavity_shift,relax_delay | merged whole into cfg | R |
| RunAmplitudeRabi | 470 | flag | run_amplitude_rabi | S |
| Amplitude_Rabi_params | 471-475 | dict qubit_freq,max_gain,number_of_steps,reps,rounds,relax_delay,fit | run_amplitude_rabi (all); qubit_freq derived from Qubit_Parameters[Qubit_Pulse] at import time (duplicate of ctx.qubit_frequency_center) | R (qubit_freq D) |
| RunT1 / RunT2 | 477/478 | flags | run_t1 / run_t2 | S |
| T1T2_params | 479-482 | dict T1_step,T1_expts,T1_reps,T1_rounds,T2_step,T2_expts,T2_reps,T2_rounds,freq_shift,relax_delay,repetitions | run_t1,run_t2,run_t1_t2e,run_t1_t2r_t2e,run_charge_dispersion_ramsey(repetitions),run_trans_qubit_spec(repetitions),interleave | R |
| RunT1T2E / RunT1T2RT2E / RunT2E | 484/486/488 | flags | run_t1_t2e / run_t1_t2r_t2e / run_t2e | S |
| T2E_params | 489-493 | dict T2_max_us,T2_expts,T2_reps,T2_rounds,freq_shift,relax_delay,num_pi_pulses,rotation_angle,min_max,repetitions | coherence T2E funcs, interleave | R |
| SingleShot | 495 | flag | run_single_shot | S |
| SS_params | 496-497 | dict Shots,Readout_Time,ADC_Offset,Qubit_Pulse,number_of_pulses,relax_delay,pi2_SS | rebuild_singleshot_config, run_single_shot, run_t1_ss, run_qubit_optimize, interleave | R + D (Readout_Time/ADC_Offset) + S (Qubit_Pulse) |
| RunUndrivenSingleShot | 512 | flag (**True**) | run_undriven_single_shot | S |
| US_params | 513-536 | dict Shots,relax_delay,min_separation_sigma,average_shots,bin_sizes,charge_sweep,voltage_start,voltage_end,voltage_step,charge_settle_s,Repeat,plotDisp | run_undriven_single_shot (all), interleave | R (+voltage/Repeat S) |
| RunInterleavedCoherence | 548 | flag | run_interleaved_coherence | S |
| Interleave_params | 549-555 | dict cycles,UndrivenSingleShot,T1,T2R,T2E | run_interleaved_coherence | S |
| RunT1SS | 557 | flag | run_t1_ss | S |
| T1SS_params | 558-563 | dict T1_step,T1_expts,reps,angle,threshold,relax_delay,calibrate_SS,repetitions | run_t1_ss (all) | R |
| SingleShot_ReadoutOptimize | 565 | flag | run_readout_optimize | S |
| SS_R_params | 566 | dict gain_start,gain_stop,gain_pts,span,trans_pts | run_readout_optimize | R (gain range D) |
| SingleShot_QubitOptimize | 568 | flag | run_qubit_optimize | S |
| SS_Q_params | 569-570 | dict q_gain_span,q_gain_pts,q_freq_span,q_freq_pts,number_of_pulses | run_qubit_optimize | R |
| RunAutoCoherence | 575 | flag | run_auto_coherence | S |
| SkipSweetSpotSearch | 581 | bool | AutoCoherence_override_params | S |
| CalibrateQubitFreq | 585 | bool | AutoCoherence_override_params | S |
| AutoCoherence_override_params | 587-631 | dict skip_sweet_spot_search,calibrate_qubit_freq,ss_gain_span_frac,ss_gain_pts,auto_readout_opt,T1_step,T1_repetitions,T2_step,T2_expts,T2_repetitions,T2E_max_us,T2E_repetitions (all valid keys of mAutoCoherence.AUTO_COHERENCE_PARAMS) | run_auto_coherence | R |
| RunZeroSpanParity | 648 | flag | run_zero_span_parity | S |
| ZSP_RunMode / ZSP_StartSrc | 651/652 | str | zero_span | S |
| ZSP_RecalibrateParityFreqs / ZSP_RecalibrateSeparator | 655/656 | bool | zero_span | S |
| ZSP_ParityFreqs_Cached | 659-663 | dict (mutated in place by run) | zero_span | D (cache) |
| ZSP_Separator_Cached | 664-666 | dict (mutated in place) | zero_span | D (cache) |
| ZSP_ParitySpec_params | 670-675 | dict (12 keys, all used) | zero_span | R |
| ZSP_StrobeParams | 680-686 | dict sample_period_us,reps_per_chunk,n_chunks,read_length,adc_trig_offset | zero_span | R |
| ZSP_DecimatedParams | 693-700 | dict capture_length_us,soft_avgs,n_captures,read_length,adc_trig_offset,allow_soft_avgs | zero_span | R |
| ZSP_DriveParams | 704-708 | dict qubit_gain,pulse_gain,res_phase | zero_span | S/D |
| ZSP_AnalysisParams | 711-719 | dict classifier_method,window_us,k_sigma,step_us,min_burst_duration_us,analysis_bin_us,save_plots | zero_span | R |
| Validate_StaticContrast ... Build_EvidenceReport | 725-730 | 6 flags | zero_span | S |
| StaticContrast_params, ContrastVsQubit_params, Modulation_params, Control_params, Environment_params | 732-736 | dicts | zero_span | R |
| ctx | 741 | Context | everything | — |

### Dispatch order (L741-814)
build_context -> Regime A: constant_two_tone, constant_tone, transmission_fit, transmission_sweep, two_tone_spec, spec_gain_length_sweep, chi_shift, two_tone_charge_dispersion_quasicw, modified_ramsey, modified_ramsey_control, charge_dispersion_quasicw, charge_dispersion_ramsey, amplitude_rabi, t1, t1_t2e, t1_t2r_t2e, t2, t2e, trans_qubit_spec, charge_sweep, charge_transmission_sweep, active_reset_verify -> interleaved_coherence -> `rebuild_singleshot_config` (unconditional) -> Regime B: single_shot, undriven_single_shot, t1_ss, readout_optimize, qubit_optimize, auto_coherence, zero_span_parity -> `ctx.yoko.close()` (not in try/finally).
Note the dispatch order is not the declaration order (e.g. T1 before T2 is preserved, but ARV is declared before ChiShift yet runs after everything in A). Order is load-bearing because of carry-overs.

### Lab notes to migrate (CSTQ03_BFC.py)
| lines | condensed fact | docs page |
|---|---|---|
| 23,28,33,38,43,48 / 57,62,67,72,77,82 | Per-slot "currently working on N" (v2b: Q1->3, Q2->6, Q3->4, Q4->?, Q5->5, Q6->2; CSTQ03: Q1->2, Q2->4, Q3->3, Q4->5, Q5->"6?", Q6->?). Meaning ambiguous (likely physical qubit label / line mapping) — confirm with user before keeping. | device:CSTQ03 |
| 24 | v2b Q1 readout gain: 500 okay, 520/530/700 too much. | device:CSTQ03 (v2b) |
| 29-30 | v2b Q2 readout coarsely tuned to 4000, behavior at 4500; qubit and T1 found. | device:CSTQ03 (v2b) |
| 34-35 | v2b Q3 readout gain 600 too much; qubit found at 1719.8273 MHz. | device:CSTQ03 (v2b) |
| 39-40 (dup 73-74) | Q4 readout history: 7288.48 MHz, gain 1180; 400 good, 420/600 too much; with directional coupler 1400 good, 1500 maybe too much. Pi pulse history: 7468 at sigma 0.15, 5396 at 0.225, 6435; 2603.33 used for Ramsey; pi2 7009//2. | device:CSTQ03 |
| 44-46 | v2b Q5 readout: 4500 with directional coupler, 1500 good without; alt qubit freq 2756.685; qubit and T1 found. | device:CSTQ03 (v2b) |
| 50 | v2b Q6 qubit "can't find". | device:CSTQ03 (v2b) |
| 63-64 | CSTQ03 Q2 readout coarsely tuned to 4000, behavior at 4500; readout length 5 us; qubit and T1 found. | device:CSTQ03 |
| 68 | Q3 readout gain 1200 before (now 1000). | device:CSTQ03 |
| 79 | Q5 alt qubit freq 2756.685. | device:CSTQ03 |
| 83-84 | Q6 readout gain prev 1400; prev qubit freqs 3056, 3238.7, 2965, 3921.5, 2963.5. | device:CSTQ03 |
| 88 | start_voltage 0.0059 V worked for good T2R. | device:CSTQ03 |
| 92-93 | yoko_fixed: hold bias during a "charge sweep" (lazy way to repeat two-tone over time). cavity_min: look for dip not peak. | parameters |
| 95-108 | Non-SS readout window: applies to transmission, two-tone, chi, Rabi, T1/T2/T2E, charge dispersion, MR, ARV. Tone length = ADC_Offset + Readout_Time (auto). Longer window = better SNR until it exceeds ~T1. SS family has own window (SS_params); ZSP overrides via read_length. ADC_Offset None keeps BaseConfig. | parameters + architecture |
| 128 | charge_params: "0.0001 has two periods in it" (unclear; keep verbatim, ask). | device:CSTQ03 |
| 130-141 | ChargeTransmission: per-slice saved under ChargeTransmissionFF/, map as _ChargeTransmissionHeatmap.png/.npz; None inherits charge_params/Transmission_params. reps = hardware averages in one tProc program, rounds = reruns averaged in software; reps=400/rounds=1 ≡ reps=20/rounds=20 in shots but latter starts 20x more programs, each risking the stale-shot-counter race ("could not broadcast input array from shape (26,2) into shape (20,2)"). Prefer reps; raise rounds only if accumulation buffer overflows. | parameters (reps vs rounds) + experiment:charge_transmission_sweep |
| 148-149,154 | Spec: qubit_gain 750 works for Q5; qubit_length 9.5 worked; "500 used for charge sweeps" (relax_delay or gain — ambiguous). | device:CSTQ03 |
| 163 | ChargeDispersionRamsey needs tuned pi and pi/2; choose frequency at a charge-dispersion extremum. | experiment:charge_dispersion_ramsey |
| 165-168 | Charge-dispersion doublet: middle 2306.310396 MHz, upper 2306.567327, lower 2306.032673 (split 0.5347 MHz). Device/date unknown (not a CSTQ03 freq in current table). | device:CSTQ03 (verify) |
| 176-181 | MR: tau = 1/(2 df); f_ge = higher peak; MR relax_delay only for search; fixed-tau Ramsey uses mr_relax_delay; enable active reset for deterministic |g>. | experiment:modified_ramsey |
| 211-223 | Doublet search + yoko walk REMOVED from run_modified_ramsey (never worked reliably). df and f_ge configured; tau correct only if df is the true branch splitting; routine never moves yoko. MEASURED 2026-08-04 (Q2): branches 4186.7 / 4184.0 MHz, df=2.7 MHz, midpoint 4185.35; 4x cd_max_mhz=0.682 — reconcile / confirm doublet is parity before trusting expected_parity_dwell_ms. | device:CSTQ03 + experiment:modified_ramsey |
| 225-237 | tau = k/(2 df), odd k. (at df=2.7) k=1 -> tau 0.185 us infeasible at sigma 0.1 us (pi/2 envelopes span 4σ=0.4 us; program raises). k=3 -> 0.5556 us, gap 0.156 us, phase 3.0008π, contrast 1.000. Prefer smallest feasible odd k (T2* worst at max charge sensitivity). Echo_null needs 3 pulses/2 gaps -> tau > 8σ = 0.80 us; at k=3 echo_null skipped (forces all_expected=False). k=5: tau 0.9259 us, echo gap 0.063 us, phase 4.997π — keeps measurement and its null. | experiment:modified_ramsey |
| 239-250 | f_ge = UPPER parity branch, not centre; lower = f_ge - df; symmetric drive at f_ge - df/2. With symmetric_ramsey=True f_ge MUST be set; fallback is doublet centre -> drive lands on lower branch with 90° closing phase (looks like contrast failure). upper = centre + df/2. | experiment:modified_ramsey |
| 251-254 | ModifiedRamsey requires df < 1/(8σ) (no pi) or 1/(16σ) (echo), raises otherwise. σ=0.1 us -> 1.25 MHz; σ=0.22 us -> 0.57 MHz. | experiment:modified_ramsey |
| 261-292 | ROOT CAUSE of spurious kHz parity rate, CSTQ03 Q2 2026-08-04, 4-arm diagnostic (analog SNR 0.91): parity relax0 r(1)=+0.289 r(10)=+0.099 ACF 0.004582; drive_off relax0 +0.469/+0.301/0.011050; parity relax200 +0.072/+0.010/0.002301; drive_off relax200 +0.115/+0.032/0.000575. drive_off (no pi/2) shows 2.4x more ACF -> correlation is artifact and dominates. 200 us relax collapses it 4x (parity), 19x (drive_off) => incomplete inter-shot reset. T1≈50 us: carryover relax0 exp(-11.75/50)=79%; relax200 exp(-211.75/50)=1.4%; residual r(1)~0.07-0.12 is readout drift (ACF tau ~122 ms). 250 us = 5xT1 -> 0.5% carryover. Cost: rep ~262 us, 2.5 ms dwell sampled 9.6x vs 213x; per-dwell SNR 8.8 -> 2.3; compensate with many dwells. | experiment:modified_ramsey + device:CSTQ03 |
| 293 | mr_relax_delay value 500 with comment "5x T1=50us" (inconsistent: 5x50=250). | device:CSTQ03 |
| 294-301 | Rate precision set by number of dwells. At 250 us relax, rep ~262 us, 2.5 ms dwell ~9.6 shots: 100k shots ≈ 26 s ≈ 10500 dwells; 400k ≈ 105 s ≈ 42000 dwells; old 4.7 s relax-0 record had 1880 dwells. Streamer chunks transparently. | experiment:modified_ramsey |
| 303-307 | average_n_shots: legacy hard-threshold plot only; keep << one dwell: 25 shots ≈ 294 us ≈ 1/8.5 dwell; old 400 spanned ~2 dwells (featureless plot). | experiment:modified_ramsey |
| 308-312 | Primary analysis = continuous IQ + exact two-state HMM; each parity state a calibrated g/e mixture; replace mapping_p_e_state0/1 with measured values when available. | experiment:modified_ramsey |
| 321-339 | hmm_min_emission_snr gate tests analog_snr*|p1-p0| with ASSUMED mapping probs; measured analog SNR ~0.77 -> 0.62 < 0.7 default -> HMM withholds (bookkeeping, not physics; per-dwell sep ~8.8 at ~213 samples/dwell). DO NOT lower: 2026-08-04 Q2 at 0.3 HMM gave 4921±68 Hz vs ACF 9606 Hz vs PSD 15056 Hz (>3x, auto-flagged); echo_null showed 44% of parity ACF amplitude -> fit locked onto ~50-200 us correlation, not parity. None keeps 0.7. | experiment:modified_ramsey |
| 343-345 | Controls: flip_final_pi2 must preserve telegraph and invert occupancy; echo must suppress it. | experiment:modified_ramsey |
| 349-358 | flip_final_pi2 adds 180° to closing pi/2. Symmetric drive halves branch detuning (0.50 -> 0.25 of pi/2 Rabi rate at σ=0.1 us, df=0.5 MHz), improving |p1-p0|; closing phase 180 -> 90° automatically; requires true upper-branch f_ge. | experiment:modified_ramsey |
| 359-371 | UNRESOLVED at df=2.7 MHz, σ=0.1 us: 4σ gaussian pi/2 peak Rabi 0.0997/σ = 0.997 MHz; symmetric detuning df/2 = 1.35 MHz -> ratio 1.354 (standard 2.708) > 1 -> degraded contrast independent of tau. ratio ≤1 needs σ ≤ 0.0739 us (sym) / 0.0369 us (std). pi/2 at 3.7% DAC FS; halving σ -> gain ~2400 (7.3% FS). max_drive_bandwidth_ratio=1.4 runs "under protest"; return to 1.0 once σ allows. | experiment:modified_ramsey + device:CSTQ03 |
| 372-383 | use_active_reset: runs calibrate_active_reset_readout first (rotates res_phase so g/e separate along I, threshold from rotated SS blobs, needs use_apriori_separator=True); threshold re-derived on each SS recal; validate with ARV. readout_threshold None = auto (recommended). | experiment:modified_ramsey / active_reset |
| 384-389 | reset_readout_relax_delay ≥ ~6/kappa so pi fires on photon-free qubit. 5 us = 6/kappa for TATQ01/BFE Q2 resonator (kappa/2π = 190 kHz, measured 2026-06-06); verify kappa for CSTQ03. | parameters + device:CSTQ03 |
| 393-403 | ARV procedure: calibrate, then prep g/e × reset off/on + 2 force-pi diagnostics, n_verify_reads per shot. Working QND reset: prep|e>+ON P(g) ≈ prep|g>+ON ≈ ground fidelity, >> prep|e>+OFF, flat across reads. Runs under the SAME config as MR (regime A) so verdict transfers 1:1. | experiment:active_reset_verify |
| 410-416 | ARV: keep reset_readout_relax_delay equal to MR's; relax_delay 3500 ≥ 3xT1 (3-5xT1 convention). | experiment:active_reset_verify |
| 443-459 | MRC: S(V) ≈ cd_max_mhz·|cos(2π(V-V0)/T)|, T = cd_period_mv; cd_max 0.682 MHz, period 4.37 mV (independent calibration; date/device unstated). Sweet-spot verified if separation < sweet_spot_max_df_mhz or single peak; Ramsey runs either way; tau from S1 (separation at V1) not S_sweet; f_ge from two-tone at V_sweet. | experiment:modified_ramsey_control + device:CSTQ03 |
| 475 | Rabi: raise max_gain if no oscillation seen; compare with transmission data. | experiment:amplitude_rabi |
| 479,481 | Previous T1 settings 80/100/30/30; relax 5000. | device:CSTQ03 (history; optional) |
| 490 | T2E num_pi_pulses must be odd. | experiment:t2e |
| 496-497 | SS readout time: Q1 15 us, Q5 5 us; keep at 15. | device:CSTQ03 |
| 499-511 | UndrivenSingleShot: no qubit pulse, no fidelity; reports cloud centre/width and 2nd-blob population; shots form a time series at rep cadence (~relax_delay + readout); dwell/rate + ACF analysis like MR. Parity dwells are a few ms, so relax 3000 us barely Nyquist — rates are lower bounds. | experiment:undriven_single_shot |
| 512-536 | Flag not named UndrivenSingleShot (class name clash). Averaging n consecutive shots lowers noise 1/√n but hides switching faster than n·rep; pick plateau from rate-vs-averaging panel. Charge sweep range lives in US_params because rebuild_singleshot_config drops charge_params; voltage_end exclusive. Repeat: each pass own h5/png/json, only last displayed. | experiment:undriven_single_shot |
| 538-547 | Interleave: cycle = US -> T1 -> T2R -> T2E; Repeat/repetitions forced 1, plotDisp off; US uses SS window, T1/T2 use regime-A window (loop swaps configs). | experiment:interleave |
| 570 | Pi/2 optimisation: set gain to half and optimise with number_of_pulses=2. | experiment:qubit_optimize |
| 577-585 | AutoCoherence: SkipSweetSpotSearch True -> use Qubit_Parameters freq and hold voltage; CalibrateQubitFreq = one two-tone re-centre at current voltage (Stage 1.5). | experiment:auto_coherence |
| 633-647 | ZSP hard constraints (spec §5.3): sample_period_us ≥ adc_trig_offset + read_length + 1.0; us2cycles(sample_period_us or capture_length_us) ≤ 65535; reps_per_chunk ≤ soccfg readouts[ro_ch].avg_maxlen; decimated read_length samples ≤ buf_maxlen. | experiment:zero_span_parity |
| 651,677-692 | Modes: strobe = Path A (v1), decimated = Path B (v2). Strobe record s = reps_per_chunk·n_chunks·sample_period_us·1e-6 (~12 s defaults). Decimated: capture_length must cover adc_trig_offset+read_length and stay under 16-bit cycle cap; soft_avgs must be 1 unless allow_soft_avgs (>1 destroys trajectories); n_captures>1 concatenated, boundaries in gap_indices. | experiment:zero_span_parity |
| 717 | analysis_bin_us < read_length for decimated apriori. | experiment:zero_span_parity |
| 721-724 | Validation harness (spec 2026-06-01), strobe-only; order stage1 -> stage2 -> stage1 refine -> stage3 (gate) -> stage4 -> 5/6 -> 8 -> 7 -> 9. ModulationCheck is the pipeline-sanity gate, run first. | experiment:zero_span_parity |

### Noise comments (delete)
1-7 (replace with short docstring), 12-14, 17, 21, 55, 111-113, 155, 194, 205, 211, 261-264 (restates; also contradicts 293), 393, 402-403 (fold into docs), 431, 442, 447, 453, 459, 464 (stale), 465, 538, 572-574, 590-591, 606, 614, 623, 721, 738-740, 750, 774, 779 (stale "old line 2990"), 782. Commented-out dict entries 592-600, 608-611, 617-619, 621, 625-629 are dead code.

### Dead code
- U names: temp_dir_Q4 (15), Qubit_Parameters_v2b (22-52), StabilizeTwoTone (160), ts (122; keys unread).
- Unused dict keys: ChargeDispersion_params upper_freq/lower_freq (167-168); ModifiedRamsey_Control_params Gauss (437); Transmission_params reps/rounds ignored by run_transmission_sweep.
- Comments in dict 592-629 (commented-out overrides).
- `ZSP_*` packing at 790-812 rebuilds a dict of globals by hand — replace with a single ZSP params dict.

### Bugs / suspicious
- CSTQ03_BFC.py:250 `ModifiedRamsey_params["f_ge"]=3754.5` = Qubit_Parameters['2'] centre freq, but session Qubit_Pulse=5 (2651 MHz) and comment says "measured TOP branch (bottom=4184.0)" — stale; with symmetric_ramsey=True a centre value puts the drive on the lower branch (exactly what L243-248 warns). Device param living in a recipe dict.
- CSTQ03_BFC.py:166-172 + charge_parity.py:1627: run_charge_dispersion_ramsey reads `ChargeDispersion_params["df"]`, absent -> KeyError when RunChargeDispersionRamsey=True.
- CSTQ03_BFC.py:118/121 + 753-754: RunTransmissionSweep -> run_transmission_fit, RunTransmissionSweeps -> run_transmission_sweep (swapped-looking names; the latter ignores Transmission_params).
- CSTQ03_BFC.py:293 vs 287/299: comment says 250 us / 100k shots recommended; values are 500 / 50000.
- CSTQ03_BFC.py:224/238: df=1, k=1 contradict the analysis text (written for df=2.7, recommending k=5).
- CSTQ03_BFC.py:471: Amplitude_Rabi qubit_freq frozen at import from Qubit_Pulse; diverges from ctx if Qubit_Pulse changes elsewhere.
- CSTQ03_BFC.py:814: yoko.close() not reached on exception; yoko output left ON.
- Runner has no `__main__` guard; importing it connects to hardware.

### Destination
Split into: `devices/cstq03.py` (Qubit_Parameters per qubit incl. readout window, cavity_min, charge-dispersion freqs, cd_max/cd_period, MR df/f_ge, ZSP caches, data root), `devices/cstq03_v2b.py` or docs archive (v2b table), `runners/cstq03_session.py` (qubit selection, voltage, flags; ~50 lines), recipe defaults -> `qicklab/runs/<module>.py` `DEFAULTS` dicts merged with session overrides. Lab notes -> docs pages above.

### Style
Star import; module-level side effects; CamelCase/snake mixed globals (Qubit_Readout, US_params, SS_R_params); string-keyed qubit dicts ('1'..'6') requiring str() everywhere; flag+params pairs that should be one structure (e.g. `{"t1": {...}}` + `enabled`).

---

## 2. `Runners/runs/__init__.py` — 14 lines
Purpose: package facade re-exporting everything.
Imports: `.context` (Context, build_context, rebuild_singleshot_config, sanity_dump), star from `.calibration`, `.basic`, `.coherence`, `.charge_parity`, `.singleshot`, `.zero_span`; `.interleave.run_interleaved_coherence`.
Imported by: CSTQ03_BFC.py:9 (star). Resulting namespace has 110 names incl. np, plt, os, time, json, datetime, KMeans, curve_fit, every experiment class, and validate_ZeroSpanParity's `run_static_contrast`, `run_contrast_vs_qubit_freq`, `run_modulation_check`, `run_control_suite`, `run_environment_sweep` (look like runner run_* but are not) — collision hazard.
No __all__ in any submodule. Lab notes: none. Noise: 1-5 docstring (stale "extracted from monolithic").
Destination: `qicklab/runs/__init__.py` with explicit imports + `__all__`.

---

## 3. `Runners/runs/context.py` — 227 lines
Purpose: session state + the two config builders + hardware connect.
Imports: `pyvisa`; star from `Calib.initialize4Q` (BaseConfig, FF_Qubits, also re-exports socProxy *), star from `CoreLib.socProxy` (makeProxy), star from `Experiments.utils` (ramp_to). Imported by: `runs/__init__`, basic (Context, sanity_dump), calibration, coherence, singleshot, zero_span (Context — unused in all), charge_parity (Context, sanity_dump), interleave (rebuild_singleshot_config).

Symbols:
- `Context` (dataclass L24-58): soc, soccfg, yoko, config, outerFolder, Qubit_Readout, Qubit_Pulse, Qubit_Parameters, start_voltage, yoko_fixed, cavity_min, cavity_gain, resonator_frequency_center, qubit_gain, pi2_gain, qubit_frequency_center, qubit_sigma, qubit_flattop. `Context` type itself unused externally except as import.
  - `working_config(*updates)`: shallow `dict(self.config)` + updates (nested `ro_chs` list / `FF_Qubits` dict shared — in-place mutation of those would leak).
- `sanity_dump(cfg, tag="")` L61-71: prints selected keys. Used by basic.run_trans_qubit_spec, charge_parity.run_charge_sweep/run_charge_transmission_sweep. Debug helper.
- `rebuild_singleshot_config(ctx, SS_params)` L74-118: regime B (see §0). Writes ctx.config.
- `build_context(...)` L121-227: regime A + hardware connect; returns Context. Derived scalars: cavity_gain=Readout.Gain[Q_R], resonator_frequency_center=Readout.Frequency[Q_R], qubit_gain=Qubit.Gain[Q_P], pi2_gain=Qubit.pi2_Gain[Q_P], qubit_frequency_center=Qubit.Frequency[Q_P], qubit_sigma=Qubit.sigma[Q_P], qubit_flattop=Qubit.flattop_length[Q_P]; outerFolder = outerfoldername[Q_R].

cfg keys read: BaseConfig["adc_trig_offset"]; SS_params Shots, Readout_Time, ADC_Offset, Qubit_Pulse, relax_delay, pi2_SS; Transmission_params span, num_points; Spec_relevant_params qubit_gain, qubit_length, SpecSpan, SpecNumPoints.
cfg keys written: see §0 lists.

Lab notes: L7-12 config model (persistent config, only pulse_freq/res_phase carry-overs; transient knobs via working_config) -> architecture. L91-94 / L182-184 tone length = adc_trig_offset + readout window (tone starts t=0, ADC starts offset later) -> parameters. L200 "qubit_length 10 was best for Q4" (device unknown) -> device:CSTQ03 (verify). L133-140 docstring -> architecture.
Noise: 26, 30, 32, 35, 38, 41, 68, 76-83 (stale old-line refs), 89-90 & 98-99 (commented-out code = dead), 102, 104 ("20ns sigma" stale), 109, 146, 153, 180 (stale "used for all experiments below"), 187-188, 192-193 (stale "0.75 MHz"), 212.
Dead: commented code 90, 99. `rm` never closed. `print(config)` L213.
Bugs/suspicious:
- context.py:115 rebuild builds from BaseConfig, silently discarding `pulse_freq` / `res_phase` carry-overs (see §0).
- context.py:147-151 yoko opened, output ON and ramped before readout-window validation (L162-175); ValueError leaves yoko open/on.
- context.py:216 `FF_Qubits` stored by reference in every config (shared mutable).
- Regime A `qubit_gain` = spec gain while regime B `qubit_gain` = pi gain.
Destination: `qicklab/core/context.py` (Context/Session), `qicklab/core/config.py` (`base_config(device, qubit, readout_window)`, `singleshot_config(...)`, `sanity_dump`), `qicklab/hardware/yoko.py` (open/ramp/close as context manager), connection in `qicklab/hardware/rfsoc.py`.
Style: 3 star imports; typed `object` fields; CamelCase dataclass fields; `UpdateConfig` local CamelCase.

---

## 4. `Runners/runs/basic.py` — 324 lines
Purpose: transmission, constant tones, two-tone spec, chi shift, Rabi.
Imports: star `EXP.utils` (fit_hanger_transmission); `EXP.mTransmissionFF.CavitySpecFF`, `EXP.mSingleTone.SingleTone`, `EXP.mConstantTwoTone.ConstantTwoTone`, `EXP.mSpecSliceFF.QubitSpecSliceFF`, `EXP.mChiShift.ChiShift`, `EXP.mAmplitudeRabiFF.AmplitudeRabiFF`, `EXP.mAmplitudeRabiFF_noUpdate.AmplitudeRabiFF_N`; np, plt; `.context` Context (unused), sanity_dump.
Imported by: runs/__init__ (star) -> CSTQ03.

| function | experiments + calls | cfg keys set | ctx.config mutation |
|---|---|---|---|
| run_constant_two_tone(ctx, params=None) L14 | 1,000,000 x `ConstantTwoTone(path="ConstantTwoTone").acquire()` only (no display/save) | none (uses tone_length from config) | — |
| run_constant_tone(ctx, params=None) L26 | `SingleTone(path="TransmissionFF")` acquire only | none | — |
| run_transmission_fit(ctx, params) L32 | CavitySpecFF(path "TransmissionFF") 4-call (display plotDisp=True, figNum=1); `fit_hanger_transmission`; extra matplotlib fig (not saved), `plt.show()` | reps, rounds (params) | `pulse_freq` = f0_fit |
| run_transmission_sweep(ctx, params) L146 | CavitySpecFF 4-call (figNum 1) | reps=20, rounds=20 hardcoded (params ignored) | `pulse_freq` = peakFreq_min if ctx.cavity_min else peakFreq_max |
| run_two_tone_spec(ctx, params) L166 | QubitSpecSliceFF(path "QubitSpecFF") 4-call (plotDisp=params.display, figNum 2, min_sep, fit_window 0.5, prominent 0.1 hardcoded) | reps, rounds, Gauss, sigma (if Gauss), qubit_gain=gain, qubit_length, SpecSpan, SpecNumPoints, step, start=qubit_frequency_center-SpecSpan, expts, relax_delay | — |
| run_spec_gain_length_sweep(ctx, params) L204 | for length in sweep_lengths, gain in sweep_gains: QubitSpecSliceFF 4-call | same as above, qubit_gain=q_gain, qubit_length=q_length | — |
| run_chi_shift(ctx, params) L247 | ChiShift(path "ChiShift") 4-call (plotDisp True, figNum 1) | params merged whole (reps, rounds, TransSpan, TransNumPoints, cavity_shift, relax_delay) + pi_gain, sigma, f_ge, flattop_length | — |
| run_amplitude_rabi(ctx, params) L262 | flattop != None: AmplitudeRabiFF_N; else AmplitudeRabiFF; path "AmplitudeRabi"; 4-call (plotDisp True, figNum 2, fit) | start 0, step=int(max_gain/number_of_steps), expts, reps, rounds, sigma, f_ge=params.qubit_freq, relax_delay, flattop_length, Qubit_number=Qubit_Pulse; flattop branch adds gain_start 0, gain_end, gainNumPoints, relax_delay=8000 | — |
| run_trans_qubit_spec(ctx, params, T1T2_params) L300 | sanity_dump; T1T2_params.repetitions x QubitSpecSliceFF 4-call (plotDisp False) using base config SpecSpan/start | reps, rounds, Gauss, sigma+qubit_gain (if Gauss) | — |

Lab notes: L64-70 hanger fit start guesses Qtot 4.1e4, Qext 4.3e4, asym 1e3 (resonator-specific) -> experiment:transmission. L201-203 -> experiment:spec_gain_length_sweep.
Noise: 36, 85, 105, 145, 148-149 (wrong: reps/rounds are not "points"), 157, 165, 196 trailing, 284 (stale), 305.
Dead: `data_trans` L23, L29 unused; `params` unused L14, L26, L146; `fit_min_val` L111 unused; L173 redundant (overwritten by L175); `Context` import.
Duplication: spec cfg block (reps/rounds/Gauss/sigma/gain/span/step/start/expts) repeated in run_two_tone_spec, run_spec_gain_length_sweep, run_trans_qubit_spec, charge_parity, zero_span -> one `spec_cfg(params, center)` helper.
Bugs:
- basic.py:89 `kappa_mhz = (f0_fit / Qext_fit) / 1e6`: f0 is MHz so result is 1e6 too small, and f0/Qext is kappa_ext not total linewidth (f0/Qtot).
- basic.py:265 step=int(max_gain/number_of_steps): 10000/101 -> 99, sweep ends at 9900 not max_gain.
- basic.py:282 flattop Rabi hardcodes relax_delay 8000, ignoring params.
- basic.py:148-149 run_transmission_sweep ignores the Transmission_params passed by the runner.
- basic.py:175/196 two-tone always uses `gain` (800) and ignores params fit_window_mhz/prominent_ratio; run_trans_qubit_spec uses config qubit_gain (Spec 'qubit_gain'=1000) when Gauss False — two gain keys for one thing.
- basic.py:271 Qubit_number=Qubit_Pulse whereas T1/SS use Qubit_Readout.
- basic.py:303 run_trans_qubit_spec loops `T1T2_params['repetitions']` (1000) — cross-coupled to the coherence recipe.
- basic.py:15 run_constant_two_tone loop of 1e6 with no exit/save.
- basic.py:27 SingleTone saved under path "TransmissionFF".
Destination: `qicklab/runs/transmission.py` (constant tone, transmission fit/sweep, chi shift), `qicklab/runs/spectroscopy.py` (two-tone, gain/length sweep, trans_qubit_spec, constant two-tone), `qicklab/runs/rabi.py`. Hanger-fit report/plot block L52-142 -> `qicklab/analysis/resonator.py` (`fit_and_report_hanger`).
Style: class-method calls `CavitySpecFF.acquire(inst)`; `!= None` (L276); CamelCase locals; local var `display` shadows IPython display.

---

## 5. `Runners/runs/calibration.py` — 194 lines
Purpose: single-shot g/e separator and active-reset readout calibration helpers.
Imports: star `EXP.utils`; `EXP.mSingleShotProgramFFMUX.SingleShotProgramFFMUX`; np; `.context.Context` (unused).
Imported by: runs/__init__ (star, `_extract...` excluded), singleshot.py (all four, only calibrate_active_reset_readout used), zero_span.py (get_apriori...), charge_parity.py (all four).

Symbols:
- `_extract_iq_from_singleshot_data(data_ss, state="g")` L7-39: tries key pairs (i_g0,q_g0)/(i_g,q_g)/(Ig,Qg), e, thermal. Used only by charge_parity.py:728-730.
- `get_apriori_separator_from_singleshot(ctx, ss_shots=1000)` L40-99: SingleShotProgramFFMUX(path "SingleShot_MRCalib") 4-call (display plotDisp False); returns g_center, e_center, normal, midpoint, data_ss. cfg set: number_of_pulses=1, shots, reps, qubit_gain=ctx.qubit_gain, f_ge, sigma, flattop_length, Qubit_number=Qubit_Readout, Read_Indeces=Qubit_Readout. Used by calibrate (here), zero_span, charge_parity.
- `calibrate_active_reset_readout(ctx, max_align_iter=2, align_tol_frac=0.1)` L102-178: 1 + up to 2 separator runs; writes `ctx.config["res_phase"]` (L135 per trial, L154 final). Returns res_phase, readout_threshold, reset_ground_below_threshold, g_center, e_center. Used by singleshot.run_active_reset_verify, charge_parity.run_modified_ramsey.
- `wire_reset_into_mr_cfg(mr_cfg, apriori_sep)` L181-194: writes mr_cfg readout_threshold, reset_ground_below_threshold. Used only by charge_parity.py:701.
Lab notes: L108-113 (tProc feedback thresholds on RAW I only, so g/e must separate along I; threshold measured on rotated blobs so deg2reg sign convention never trusted) -> experiment:active_reset. L131-132 (try -phi then +phi, keep smallest |Q sep|) -> same. L186-189 idempotent; re-call on SS recal to track drifting threshold -> same.
Noise: 68, 14-23 docstring fine; minimal.
Dead: param `max_align_iter` unused (L103; loop hard-coded to 2 signs); `Context` import.
Duplication: L73-78 hardcodes i_g0/q_g0/i_e0/q_e0 instead of `_extract_iq_from_singleshot_data`; threshold math duplicated L163-164 and L193-194.
Bugs/suspicious:
- calibration.py:135-136 `base_phase + deg2reg(sign*phi)` can be negative / exceed register range; no wrap modulo full phase.
- calibration.py:121 first calibration run is used only for the axis angle; total 2-3 SingleShot acquisitions each saved under SingleShot_MRCalib.
- calibrate uses default ss_shots=1000, ignoring MR's ss_calib_shots.
Destination: `qicklab/analysis/singleshot.py` (`extract_iq`, `separator_from_blobs`, `threshold_from_blobs`); `qicklab/runs/active_reset.py` (calibrate_active_reset_readout, wire_reset_into_mr_cfg -> rename `apply_reset_threshold`); `get_apriori_separator_from_singleshot` -> `qicklab/runs/singleshot.py::measure_ge_separator`.
Style: missing blank lines L39-40; long docstrings partly restating code.

---

## 6. `Runners/runs/coherence.py` — 297 lines
Purpose: T1 / T2R / T2E / T1SS loops and AutoCoherence wrapper.
Imports: star `EXP.utils` (time); `EXP.mT1FF.T1FF`, `EXP.mT2R.T2R`, `EXP.mT2EFF.T2EMUX`, `EXP.mT1_SS.T1_SS`, `EXP.mSingleShotProgramFFMUX.SingleShotProgramFFMUX`, `EXP.mAutoCoherence` (run_auto_coherence as _run_auto_coherence, AUTO_COHERENCE_PARAMS (unused), find_sweet_spot (unused)); np, plt (unused); Context (unused).
Imported by: runs/__init__ (star), interleave (run_t1, run_t2, run_t2e).

| function | experiments + calls | cfg keys set |
|---|---|---|
| run_t1(ctx, T1T2_params) L13 | per repetition: T1FF(path "T1") 4-call (plotDisp = params.get('plotDisp', reps<=1), figNum 2); sleep 10; soc.reset_gens() | start 0, step=T1_step, expts=T1_expts, reps=T1_reps, rounds=T1_rounds, Qubit_number=Qubit_Readout, pi_gain, relax_delay, sigma, flattop_length, f_ge |
| run_t1_t2e(ctx, T1T2, T2E) L35 | per T1T2.repetitions: T1FF 4-call, then T2EMUX(path "T2E") 4-call (figNum 3); break if int_steps==0 | T1 as above; T2E: start 0, step=0.00232515*(n_pi+1)*int_steps, expts, reps, rounds, pi_gain, pi2_gain, relax_delay, f_ge+freq_shift, num_pi_pulses, sigma, flattop_length, Qubit_number; rotation_angle/min_max if `.get(...,False) != False` |
| run_t1_t2r_t2e(ctx, T1T2, T2E) L104 | per rep: T1FF -> T2EMUX -> T2R(path "T2R") (order T1, T2E, T2R; name says T2R first) via local `_run_experiment` | T1, T2E (rotation if not None), T2R: start 0, step=T2_step, phase_step=deg2reg(0, gen_ch=2), expts, reps, rounds, pi_gain, pi2_gain, relax_delay, f_ge+freq_shift, sigma, flattop_length (no Qubit_number) |
| run_t2(ctx, T1T2) L184 | per rep: T2R 4-call (plotDisp False, figNum 2) | T2R cfg as above |
| run_t2e(ctx, T2E) L203 | per rep: T2EMUX 4-call (plotDisp param or reps<=1, figNum 2) | T2E cfg (no Qubit_number); rotation_angle/min_max if `!= False` |
| run_t1_ss(ctx, T1SS, SS) L253 | per rep: optional SingleShotProgramFFMUX(path "SingleShot") 4-call -> angle, threshold; T1_SS(path "T1SS") acquire(angle, threshold), display(False, 2), save_data, save_config | number_of_pulses (if calibrate), start 0, step, expts, reps, pi_gain, relax_delay |
| run_auto_coherence(ctx, AutoCoherence_override_params) L286 | `mAutoCoherence.run_auto_coherence(soc, soccfg, config=working_config(), outerFolder, qubit_readout=Qubit_Readout, qubit_params=Qubit_Parameters, yoko, auto_params)` | — |

No ctx.config mutation in this file.
Lab notes: 0.00232515 us (L66, 73, 136, 144, 212, 213, 221) = one tProc clock cycle (1/430.08 MHz); T2E step must be integer multiple of (n_pi+1) cycles so pulses stay on grid -> experiment:t2e (only "hardware quantization" stated in code; confirm the 430.08 MHz interpretation). L15/L205-206: explicit plotDisp wins so interleaved loops don't block -> experiment:interleave.
Noise: 24, 37, 40, 62, 65, 87, 99, 117, 133, 163, 193, 211, 217 (trailing), 234, 241, 275 (trailing).
Dead: imports np, plt, AUTO_COHERENCE_PARAMS, find_sweet_spot, Context; loop var `i` unused in run_t1/run_t1_t2e/run_t2/run_t1_ss.
Duplication: T1 cfg built 3x (L17, L41, L118); T2E cfg 3x (L71, L142, L219) + int_steps calc 3x; T2R cfg 2x (L164, L185); local `_run_experiment` (L105) duplicates the 4-call pattern used everywhere -> one module-level `run_experiment(ctx, cls, path, cfg, fig, plot)` in core.
Bugs/suspicious:
- coherence.py:167,185 `deg2reg(0*360/50, gen_ch=2)` hardcodes gen_ch 2 (qubit_ch is 1); harmless only because value is 0.
- coherence.py:88, 235 `!= False` lets rotation_angle=None through (writes None keys; T2EMUX tolerates); L157 uses `is not None` — inconsistent.
- coherence.py:38 run_t1_t2e ignores params plotDisp (unlike run_t1/run_t2e); run_t2 always plotDisp False.
- coherence.py:69/140 `break` after T1 already ran (T1 saved without its T2E pair); run_t2e L217 break on first rep.
- Qubit_number present for T1 / T2E-in-pair but absent for standalone T2E and T2R.
- time.sleep(10) after every rep including last.
Destination: `qicklab/runs/coherence.py` (keep), with cfg builders `t1_cfg`, `t2r_cfg`, `t2e_cfg(…)` and `t2e_step(t_max, n_expts, n_pi)` -> `qicklab/core/timing.py`. run_t1_ss -> `qicklab/runs/singleshot.py`. run_auto_coherence wrapper -> `qicklab/runs/auto_coherence.py`.
Style: star import; wrapper name equals imported function name (aliased with `_`); `!= False`.

---

## 7. `Runners/runs/singleshot.py` — 305 lines
Purpose: ARV, single-shot, undriven single-shot, readout/qubit optimisation.
Imports: star `EXP.utils` (os, datetime); `EXP.mSingleShotProgramFFMUX.SingleShotProgramFFMUX`, `EXP.mOptimizeReadoutandPulse_FF` (ReadOpt_wSingleShotFF, QubitPulseOpt_wSingleShotFF), `EXP.mActiveResetVerify.ActiveResetVerify`, `EXP.mUndrivenSingleShot.UndrivenSingleShot`; np, plt; `.context.Context` (unused); `.calibration` four names (only calibrate_active_reset_readout used).
Imported by: runs/__init__ (star), interleave (run_undriven_single_shot).

| function | experiments + calls | cfg keys set | ctx.config mutation |
|---|---|---|---|
| run_active_reset_verify(ctx, ARV) L12 | calibrate_active_reset_readout (2-3 SingleShot runs); 6 conditions x ActiveResetVerify(path "ActiveResetVerify") 4-call (display False, figNum 20); overlay PNG + npz in outerFolder/ActiveResetVerify/; verdict print | f_ge, pi_gain, sigma, flattop_length, reps, rounds=1, relax_delay, n_verify_reads, verify_relax_delay, reset_cycles, reset_readout_relax_delay, post_reset_wait, readout_threshold, reset_ground_below_threshold, g_center, e_center, Qubit_number=Qubit_Readout, prep_excited, use_active_reset, reset_force_pi | `res_phase` (via calibrate) |
| run_single_shot(ctx, SS) L160 | SingleShotProgramFFMUX(path "SingleShot") 4-call (display True); prints angle/threshold | number_of_pulses; qubit_gain=pi2_gain if pi2_SS | — |
| run_undriven_single_shot(ctx, US=None) L176 | Repeat x UndrivenSingleShot(path "UndrivenSingleShot", yoko=ctx.yoko) 4-call (display only last pass if plotDisp); returns list of data | shots, relax_delay, blob_min_separation_sigma, shot_average, ts_bin_sizes, charge_sweep, voltage_start/end/step, charge_settle_s (only if present) | — |
| run_readout_optimize(ctx, SS_R) L241 | ReadOpt_wSingleShotFF(path "SingleShot_OptReadout") 4-call (display True) | number_of_pulses=1, cav_gain_Start/Stop/Points, trans_freq_start/stop = pulse_freq ∓ span/2, TransNumPoints | — |
| run_qubit_optimize(ctx, SS_Q, SS) L269 | QubitPulseOpt_wSingleShotFF(path "SingleShot_OptQubit") acquire(Qubit_Sweep_Index=0), display(True), save_data, save_config | number_of_pulses, qubit_gain (pi2 if pi2_SS), qubit_gain_Start=max(0,g-span), qubit_gain_Stop=min(32767,g+span), qubit_gain_Points, qubit_freq_start/stop = f_ges[0] ∓ q_freq_span, QubitNumPoints | — |

Lab notes: L46-51 force-pi diagnostics meaning (prep|e>_forcePI should match prep|g>_resetOFF if pi good; prep|g>_forcePI should match prep|e>_resetOFF) -> experiment:active_reset_verify. L150 verdict criterion: working if P_g(e,ON) ≥ 0.9·P_g(g,ON) and recovery P_g(e,ON)-P_g(e,OFF) ≥ 0.3 -> experiment:active_reset_verify. L177-197 US docstring (time-series, Repeat semantics, sqrt(n) tradeoff) and L210-211 (range must come via US_params because rebuild drops charge_params), L224 (program mutates reps/rounds/length in place -> fresh cfg per pass), L230-232 (display blocks) -> experiment:undriven_single_shot.
Noise: 16-17, 22-23, 89, 128, 167 (commented print), 250 & 281 ("###### cavity" — 281 wrong), 259, 262, 283-284 trailing commented code, 292 trailing, 295, 300.
Dead: imports get_apriori_separator_from_singleshot, wire_reset_into_mr_cfg, _extract_iq_from_singleshot_data, Context; `g0`, `f0` L293-294; `qubit_gains` partly (only index 0 via g0, dead); commented prints 167, 262, 300; duplicate print L291/L302.
Bugs/suspicious:
- singleshot.py:278 `cfg['pi2_SS']` KeyError if called in regime A (only regime B sets it).
- singleshot.py:286-287 qubit freq centre from SS_params Qubit_Pulse[0] (Qubit_Parameters) not ctx/current f_ge; gain centre from cfg['qubit_gain'] — mixed sources.
- singleshot.py:138-139 force-PI uses only read 0 (`[:1]`) — intentional but undocumented.
- ARV calibrate mutates persistent res_phase; subsequent regime-A runs inherit it, regime B resets it.
Destination: `qicklab/runs/singleshot.py` (single_shot, undriven, readout/qubit optimize, t1_ss), `qicklab/runs/active_reset.py` (ARV + calibration). ARV verdict/overlay plotting -> `qicklab/analysis/active_reset.py`.
Style: class-method calls; CamelCase locals (Instance_SingleShotProgram); `arv_` prefix on every local.

---

## 8. `Runners/runs/interleave.py` — 77 lines
Purpose: loop UndrivenSingleShot -> T1 -> T2R -> T2E with per-step config regime swap.
Imports: datetime; `.context.rebuild_singleshot_config`; `.coherence` run_t1, run_t2, run_t2e; `.singleshot.run_undriven_single_shot`. Imported by: runs/__init__.
`run_interleaved_coherence(ctx, IL_params, US_params, T1T2_params, T2E_params, SS_params)`: coh_cfg = ctx.config; rebuild_singleshot_config -> ss_cfg; steps (US with ss_cfg, US|{Repeat:1, plotDisp:False}; T1/T2R/T2E with coh_cfg, params|{repetitions:1, plotDisp:False}); for each cycle/step sets `ctx.config = cfg | {interleave_run_id, interleave_cycle, interleave_cycles_total, interleave_step}`; finally restores ctx.config = coh_cfg.
Experiments: via run_undriven_single_shot (UndrivenSingleShot), run_t1 (T1FF), run_t2 (T2R), run_t2e (T2EMUX).
cfg keys written: interleave_run_id, interleave_cycle, interleave_cycles_total, interleave_step (tag keys; saved in json + h5 attrs).
Lab notes: docstring L1-30 (regimes, tag keys, offline grouping snippet `json.loads(f.attrs["config"])`, run_id = wall-clock start) -> experiment:interleave + architecture. Concise already.
Noise: 45, 70.
Bugs/suspicious: a T1/T2 failure mid-cycle aborts the whole loop (no per-step try); `run_t2` ignores plotDisp (always False — fine). ss_cfg is built from BaseConfig so loses pulse_freq carry-over (consistent with rebuild).
Destination: `qicklab/runs/interleave.py`.
Style: clean.

---

## 9. `Runners/runs/zero_span.py` — 229 lines
Purpose: ZeroSpanParity acquisition + analysis + validation harness orchestration.
Imports: star `EXP.utils` (pick_parity_drive_freq, chunked_acquire); `EXP.mZeroSpanParity.ZeroSpanParity`; `EXP.analyze_ZeroSpanParity.analyze_parity_run`; `EXP.validate_ZeroSpanParity` (run_static_contrast, run_contrast_vs_qubit_freq, run_modulation_check, run_control_suite, run_environment_sweep, build_evidence_report); `EXP.mSpecSliceFF.QubitSpecSliceFF`; np, plt (unused), os; Context (unused); `.calibration.get_apriori_separator_from_singleshot`.
Imported by: runs/__init__ (star; also leaks the validate_* run_* names).

`run_zero_span_parity(ctx, p)` sequence:
1. If ZSP_RecalibrateParityFreqs: QubitSpecSliceFF(path "ZeroSpanParity_Spec", outerFolder=outerFolder+"ZeroSpanParity/") acquire, display(False, figNum 2, min_sep, fit_window, prominent), save_data, save_config; `pick_parity_drive_freq` -> writes p["ZSP_ParityFreqs_Cached"] lower_peak_MHz/higher_peak_MHz. cfg keys: reps, rounds, relax_delay, Gauss, sigma, qubit_gain=gain, qubit_length, qubit_pulse_style="const", SpecSpan, SpecNumPoints, step, start, expts, setdefault current_voltage=start_voltage. Else read cache (raise if None).
2. If ZSP_RecalibrateSeparator: get_apriori_separator_from_singleshot -> writes p["ZSP_Separator_Cached"] g_center/e_center/normal/midpoint. Elif apriori: validate cache shapes (2,), coerce to ndarray in place.
3. zsp_cfg: res_ch, qubit_ch, ro_chs, nqz, qubit_nqz, mixer_freq (from config), read_pulse_freq=resonator_frequency_center, parity_drive_freq, qubit_gain, pulse_gain, res_phase (ZSP_DriveParams; default 0), mode, start_src, **mode params (strobe: sample_period_us, reps_per_chunk, n_chunks, read_length, adc_trig_offset; decimated: capture_length_us, soft_avgs, n_captures, read_length, adc_trig_offset, allow_soft_avgs). Note: built from scratch, NOT ctx.config.
4. Guard: Validate_* with non-strobe mode raises.
5. ZeroSpanParity(path "ZeroSpanParity") chunked_acquire (strobe & n_chunks>1) or acquire(progress=True); save_data, save_config (no display).
6. analyze_parity_run(h5_path, separator, window_us, k_sigma, classifier_method, step_us, min_burst_duration_us, analysis_bin_us, save_plots, out_dir=run dir).
7. Validation stages (each optional): run_static_contrast (mutates zsp_exp.cfg reps_per_chunk & reps), run_contrast_vs_qubit_freq, run_modulation_check, run_control_suite, run_environment_sweep (local `_set_power` sets cfg pulse_gain and rebuilds prog), build_evidence_report -> EVIDENCE.md.
ctx.config mutation: none. Caller dict mutation: ZSP_ParityFreqs_Cached, ZSP_Separator_Cached (module globals in runner).
Lab notes: L76-79 spec §5.3 rule 7 (cached separator fields must be shape-(2,) arrays when apriori and not recalibrating) -> experiment:zero_span_parity. L128-131 validation harness strobe-only because set_qubit_gain raises in decimated mode -> same. L146-147 chunked_acquire sets exp.data itself. L155-157 one run dir for analysis + sidecars so build_evidence_report collates. L182-184 stage 1 uses no separator. L188-190 set_qubit_gain rebuilds strobe program from cfg["reps"], so update both reps keys. L219 NOTE environment sweep should use attenuator/YOKO for real power sweep.
Noise: 17, 68, 96, 107, 114, 117, 121, 124, 141, 160, 178.
Dead: `zsp_data` (L148/151) unused; plt import; Context import; L19-20 double copy (`working_config()` then `.copy()`); `qubit_pulse_style` L28 unused by QubitSpecSliceFF (it keys on Gauss).
Bugs/suspicious:
- zero_span.py:218-220 + CSTQ03_BFC.py:736: Environment sweep "power_dB" values [-10,-8,-6,-4] written raw as `pulse_gain` DAC units (negative gains).
- zero_span.py:14 `ctx.outerFolder + "ZeroSpanParity/"` relies on trailing slash in outerFolder; use os.path.join.
- zero_span.py:120 res_phase from ZSP_DriveParams (0) ignores any calibrated res_phase.
- zero_span.py:34 current_voltage setdefault start_voltage may be stale (yoko could have moved).
Destination: `qicklab/runs/zero_span.py`; `_set_power` -> `qicklab/experiments/zero_span_validate.py` (or analysis); spec-cfg block -> shared `spec_cfg()` helper.
Style: star import; `_`-prefixed locals at function scope; dict-of-dicts param `p` with 22 keys (better a dataclass / single nested dict).
