# Research-effectiveness review (2026-10-13)

Seven Opus domain reviewers read the post-3b tree; every tier-A/B finding was then given to an independent
refuter agent that tried to disprove it (3 were refuted). `findings.json` holds the 85 surviving findings
with evidence, proposed change, expected golden impact and the refuter's notes; `tier_c_and_gaps.json` holds
the 9 methodology proposals that need the fridge and each domain's 'gaps' paragraph (what the code cannot
establish today). Findings are applied one commit each (see HANDOFF.md); this table is the index.

| id | tier | sev | domain | file | symbol | claim |
|---|---|---|---|---|---|---|
| F00 | A | high | readout-singleshot | `active_reset.py` | ActiveResetMixin.active_reset_to_g (and ActiveRese | The tProc `read` runs as soon as `measure(wait=True)` stalls to the nominal end of the ADC window, before the accumulated word of the current readout reaches th |
| F01 | A | high | coherence | `iq.py` | rotate_iq (used by fit_ramsey_auto, T2R.display) | The Ramsey projection rotates the IQ centroid onto +I instead of projecting onto the g-e oscillation axis. With the usual dispersive readout geometry (/g/ about |
| F02 | A | high | coherence | `auto_coherence.py` | _stage_run_t1/_stage_run_t2/_stage_run_t2e, _run_a | Every coherence path calls display() (which fits) before save_data() and save_config(). A fit exception therefore throws away the acquired record. In auto_coher |
| F03 | A | high | spectroscopy-transmission | `resonator.py` | run_transmission_fit (second hanger fit, startpoin | The step's own hanger fit, whose f0 becomes ctx.config['pulse_freq'] for every later regime-A step, starts from asym=1e3. That value is about 1e6 times too larg |
| F04 | A | high | spectroscopy-transmission | `spectroscopy.py` | choose_two_tone_freqs_from_lorentz_or_peaks / pick | The parity-doublet selection reports a doublet for a single line, and collapses a real doublet split less than about 2x fit_window to two copies of the blended  |
| F05 | A | high | spectroscopy-transmission | `spectroscopy.py` | fit_lorentzian_near_peak / find_two_tone_peaks / Q | Peak finding is done by three different algorithms: the argmax in acquire, the local-max/ratio pick in display, and the savgol/prominence find_two_tone_peaks. A |
| F06 | A | high | charge-parity-mr | `hmm.py` | fit_two_state_hmm (identifiability gates: min_logl | A record with no temporal correlation is reported as an identifiable parity telegraph at 7-90 kHz. This happens because the null model is a single Gaussian, not |
| F07 | A | high | zero-span-undriven | `zero_span.py` | classify_parity_trace (method='apriori') via qickl | The default 'apriori' classifier puts the parity threshold at the g/e midpoint of a SingleShot separator. A continuously driven two-level qubit has p_e <= 0.5,  |
| F08 | A | high | acquisition-timing-infra | `auto_coherence.py:1306-1310)` | run-function sequence acquire -> display -> save_d | Every run function calls display() before save_data()/save_config(), so if the analysis raises (or a blocking plot window stays open), data already acquired fro |
| F09 | A | medium | readout-singleshot | `active_reset_verify.py` | ActiveResetVerifyProgram.initialize / active_reset | Confirmed known bug: ARV still uses `cmp_offset = 1<<24` and `read(ro_ch, ...)` with the readout index instead of the tProc input channel. It therefore does not |
| F10 | A | medium | readout-singleshot | `readout.py` | classify_thermal_tail | The thermal-mode 'population' is not an estimator of the excited population. It reports about 1% when the true population is 0, and it underestimates real popul |
| F11 | A | medium | readout-singleshot | `single_shot.py` | run_t1_ss | The T1-SS threshold/angle calibration copies `SS_params['number_of_pulses']` but not the matching gain. If the single-shot group is set up for the pi/2 check (p |
| F12 | A | medium | coherence | `ramsey.py` | fit_ramsey_auto (bounds), fit_magnitude_envelope | The Ramsey fit bounds are fixed numbers, not derived from the sampling. f in [0, 2] MHz although the Nyquist limit at T2_step=0.1 us is 5 MHz. T2* >= 1 us regar |
| F13 | A | medium | spectroscopy-transmission | `fitting.py` | fit_rabi_cosine (used by AmplitudeRabiFF/_N); fit_ | Extends the known single-start issue. fit_rabi_cosine already fails at about 1.5 periods in the sweep, sometimes with a plausible but wrong in-range pi gain. Th |
| F14 | A | medium | spectroscopy-transmission | `transmission.py` | CavitySpecFFProg / QubitSpecSliceFFProg / ChiProgr | These programs do not use the shared cover_readout_window helper. On the lab board the ADC window is 1.4x readout_length (known, readout_window.md), so about 6  |
| F15 | A | medium | charge-parity-mr | `modified_ramsey.py` | run_modified_ramsey (control acquisition nested in | The interleaved validation controls are acquired only when online analysis is enabled. With the runner's parity_analysis_enabled=False, the configured validatio |
| F16 | A | medium | charge-parity-mr | `modified_ramsey.py` | compare_parity_controls | The two decisive checks give wrong verdicts on easy cases. An ideal symmetric echo null (i.i.d. P(e)=0.5) is marked FAILED, and a 'flip' record whose mapping di |
| F17 | A | medium | zero-span-undriven | `zero_span.py` | detect_bursts / analyze_parity_run baseline_rate_H | The headline baseline_rate_Hz is the median of integer per-window switch counts. In the expected operating regime (under about 0.7 switches per window) it is ex |
| F18 | A | medium | zero-span-undriven | `acquisition.py` | modulated_strobe_acquire (and runs/zero_span_valid | The reps_per_block argument never reaches the program: set_qubit_gain rebuilds it with cfg['reps_per_chunk']. Each modulation half-period therefore holds reps_p |
| F19 | A | medium | zero-span-undriven | `zero_span_validation.py` | run_control_suite variant D (branch_sign_flip) | The stage-8 'assignment reverses' statistic cannot be True even after the known missing-rebuild bug is fixed. Driving either parity branch moves the time-averag |
| F20 | A | medium | acquisition-timing-infra | `{transmission,qubit_spec,rabi,chi_shift,t1,t2_ramsey,t2_echo,charge_dispersion,t1_single_shot}.py` | declare_readout(length=self.us2cycles(cfg['readout | Confirms and quantifies the documented regime-A window bug (docs/concepts/readout_window.md known issues; not in design.md's list). The ADC window is declared i |
| F21 | A | medium | orchestration-params | `set_bias.py` | main / qicklab/twpa/flux_sweep.py main (OUTP ON be | Both scripts turn the GS200 output on before ramping. If the output was off with a non-zero stored current setpoint, the TWPA sees an unramped step to that setp |
| F22 | A | low | readout-singleshot | `active_reset.py` | calibrate_active_reset_readout | Known unwrapped `res_phase` arithmetic, extended: res_phase stays correct mod 2^32 up to 2^33, but the third calibration in one regime-A session pushes it past  |
| F23 | A | low | coherence | `t2_echo.py` | T2EProgram.body / update (equal waits) | Confirms and explains the known 'num_pi_pulses must be odd' rule. The program uses n+1 equal waits (τ, π, τ, ..., τ) instead of CPMG spacing (τ/2, π, τ, ..., π, |
| F24 | A | low | coherence | `t1.py` | T1Program/T2RProgram/T2EProgram/T1SingleShotProgra | Extends the known readout-clock issue. The ADC window is declared in tProc cycles, so it is 1.4x readout_length on the lab board. auto_coherence Stage 2.5 optim |
| F25 | A | low | spectroscopy-transmission | `transmission.py` | CavitySpecFF.display kappa_mhz; runs/resonator.py  | Confirms the known kappa bug. (f0/Qext)/1e6 is 1e6 too small (golden value 1.9e-09 MHz) and is the external rate, not the total linewidth. |
| F26 | A | low | spectroscopy-transmission | `rabi.py` | AmplitudeRabiFF.acquire iq_rotation_angle(np.ravel | Confirms the known issue with numbers. Estimating the principal axis over ADC0 and ADC1 together aligns the background offset between the two ADCs with I, not t |
| F27 | A | low | zero-span-undriven | `zero_span_parity.py` | _validate_cfg rule 1 / ZeroSpanParity._acquire_str | Because the readout window is 1.4x read_length (known bug), any sample_period_us between the rule-1 floor and adc_trig_offset + 1.4*read_length compiles to a lo |
| F28 | A | low | orchestration-params | `charge_sweep.py` | run_charge_sweep / run_charge_transmission_sweep ( | With yoko_fixed=True the bias is never moved, yet every saved slice records cfg['current_voltage'] = the swept value, and the heatmap and npz label the rows as  |
| F29 | B | high | coherence | `auto_coherence.py` | AUTO_COHERENCE_PARAMS['T2_freq_shift'], _stage_run | Ramsey runs on resonance by default: freq_shift 0.0 and phase_step = deg2reg(0). The fringe frequency is then the unknown residual detuning, which is often near |
| F30 | B | high | charge-parity-mr | `modified_ramsey.py` | analyze_modified_ramsey_record (mapping_probabilit | With fixed assumed mapping probabilities, the rate is strongly biased whenever the real Ramsey contrast differs. The per-sample emission-SNR gate (computed from |
| F31 | B | high | charge-parity-mr | `modified_ramsey.py` | build_control_variants (echo_null) / plan_parity_m | The Hahn-echo control is not a parity null at the bandwidth-limited operating point. Its detuned pi pulse is itself parity-dependent, so echo_null can keep most |
| F32 | B | high | zero-span-undriven | `zero_span.py` | analyze_parity_run / sliding_window_switch_rate /  | Every switch rate and dwell time in ZSP, and the undriven gamma01/gamma10, comes from counting threshold crossings with no readout-error model. Each misassigned |
| F33 | B | medium | readout-singleshot | `readout_optimize.py` | QubitPulseOpt_wSingleShotFF.acquire / _acquireSing | The qubit-pulse map re-acquires the /g> reference at every (qubit gain, qubit frequency) point, but the /g> program never plays a qubit pulse, so half of the fr |
| F34 | B | medium | coherence | `t1.py` | T1FF.display / T2R.display / T2EMUX.display / auto | Fit results and their uncertainties are never saved: not in the h5, not in the json, not in the auto summary. Only the plot title carries them. Repeated records |
| F35 | B | medium | coherence | `auto_coherence.py` | _stage_sweet_spot_search (Strategy B walk), find_s | The walk has no 'range covered' stopping rule: it bounces between the bounds and re-measures the same voltages, up to 200 spectra. It also accepts a single 'pea |
| F36 | B | medium | spectroscopy-transmission | `fitting.py` | fit_hanger_transmission / CavitySpecFF.display (pu | The magnitude-only hanger fit cannot tell Qext from Qtot/(2-Qtot/Qext) (under- vs over-coupled), and abs() in Qint hides the unphysical branch. There is also no |
| F37 | B | medium | spectroscopy-transmission | `chi_shift.py` | ChiShift.display (argmin of /S21/ per state) | Taking chi from the argmin of the pi-pulsed trace is biased toward zero whenever the excited-state population at readout is below 1 (thermal population of a 2.6 |
| F38 | B | medium | charge-parity-mr | `readout.py` | calibrate_readout_from_labeled_shots (moment-match | The emission model and analog SNR come from the mean and std of the 'e'-labelled shots. Those shots are prepared by a pi pulse at the doublet centre, which is d |
| F39 | B | medium | charge-parity-mr | `modified_ramsey.py` | build_control_variants (drive_detuned default det= | The default drive_detuned control (drive offset +df) does not degrade the mapping as documented. It shifts both branch phases by k*pi and so gives an inverted m |
| F40 | B | medium | charge-parity-mr | `charge_sweep.py` | run_charge_sweep / charge_sweep_voltages / run_cha | The sweep grid is never checked against the charge-dispersion period, and no code extracts the doublet splitting vs bias or fits cd_max/period. With the runner' |
| F41 | B | medium | charge-parity-mr | `modified_ramsey.py` | run_modified_ramsey_control (KMeans + moving-avera | Beyond the known 'not the same sequence' issue, the sweet-spot null is also analysed with a different estimator (KMeans g/e + hysteresis switch count) that has  |
| F42 | B | medium | charge-parity-mr | `modified_ramsey.py` | run_modified_ramsey (f_ge, df vs ctx.qubit_frequen | Nothing checks that the configured upper branch f_ge lies near the qubit whose pi/2 and pi gains and SingleShot calibration are used. A value hundreds of MHz of |
| F43 | B | medium | zero-span-undriven | `acquisition.py` | chunked_acquire / experiments/zero_span_parity.py  | Rule 4 (reps_per_chunk <= avg_maxlen = 16384) is not a qick limit. In 0.2.334 the accumulated buffer is a ring buffer streamed during acquire(). The 60-chunk de |
| F44 | B | medium | zero-span-undriven | `zero_span.py` | run_zero_span_parity (stage ordering / feedback) | The main parity record is taken and analysed before any validation stage. The stage-1 optimal probe frequency and the stage-2 branch positions, which are measur |
| F45 | B | medium | zero-span-undriven | `zero_span_validation.py` | run_static_contrast / _mean_complex_response / con | Stage-1 'contrast_snr' is the peak contrast divided by the MAD of the contrast curve itself, which is a shape ratio, not a signal-to-noise ratio. The per-point  |
| F46 | B | medium | acquisition-timing-infra | `experiment.py` | ExperimentClass.save_config / data_paths (provenan | Saved files cannot reproduce or attribute a measurement. Nothing records the qick client or board version, the board config, the git commit, the device or coold |
| F47 | B | medium | acquisition-timing-infra | `context.py` | ramp_to; build_context | The charge-bias source lacks basic safety checks. ramp_to only rejects > +10 V and never verifies that it landed. build_context switches the output on before ra |
| F48 | B | medium | acquisition-timing-infra | `t1_single_shot.py (T1_SS.acquire)` | multi-program acquisitions held in memory until th | Long multi-program acquisitions save nothing until every point is done. An exception at point k (for example the stale-shot-counter race, which is retried only  |
| F49 | B | medium | acquisition-timing-infra | `context.py (no validation layer exists)` | frequency vs DAC Nyquist zone | Nothing checks frequencies against the DAC sampling rate. freq2reg silently wraps, and 5 of 6 CSTQ03 readout tones lie above fs = 6881.28 MS/s, i.e. they are th |
| F50 | B | medium | orchestration-params | `board.py` | BASE_CONFIG['qubit_nqz'] / build_context (no Nyqui | qubit_nqz=1 is applied to every qubit, but Q2 (3754.5 MHz) and Q4 (4117 MHz) sit above fs/2. For those qubits the DAC's strongest output is the first-zone image |
| F51 | B | medium | orchestration-params | `rabi.py` | session-wide gain validation (run_amplitude_rabi m | qick 0.2.334 compiles DAC gains above 32767 without complaint; the 16-bit register then wraps to a negative gain. No run_* checks its resolved gains, apart from |
| F52 | B | medium | orchestration-params | `resonator.py` | run_transmission_fit / run_transmission_sweep (pul | The fitted or argmin resonator frequency is written into ctx.config['pulse_freq'] with no quality gate. A fit to noise, or to the wrong feature, silently moves  |
| F53 | B | medium | orchestration-params | `context.py` | build_context yoko setup / qicklab/hardware/yoko.p | Charge-yoko setup has three gaps. It writes ':SOUR:FUNC VOLT' and ':OUTP ON' before ramping, so the output steps to whatever level is stored. It never checks th |
| F54 | B | medium | orchestration-params | `gain_compare.py` | bring-up sequence + TWPA state provenance (gain_co | The documented TWPA bring-up order ends with the pump off, and with the bias at 0 if flux_sweep runs after set_bias. Nothing records or checks the TWPA state, a |
| F55 | B | medium | orchestration-params | `pump_sweep.py` | main (no unpumped reference; full-array incrementa | pump_sweep ranks operating points by absolute band-mean /S21/ over a roughly 10 h sweep, with no pump-off reference. Drift is confounded with gain, and the docs |
| F56 | B | medium | orchestration-params | `CSTQ03_BFC.py` | cross-dict agreement checks (ModifiedRamsey_params | Several values must agree across separate dicts but are kept consistent only by comments. In the committed runner state, two of them already disagree. |
| F57 | B | medium | orchestration-params | `design.md` | Device/Session layer (phase 5): regime-switch sema | The phase-5 spec contradicts itself and defines validation that would either reject CSTQ03 or miss its real problems. |
| F58 | B | medium | orchestration-params | `design.md` | Device/Session layer (phase 5): missing capabiliti | The planned API does not cover in-session application of calibrations, hardware-state provenance, bias precedence, runtime estimates or a graceful stop. Each of |
| F59 | B | low | readout-singleshot | `readout.py` | MixedShots (used for overlap_mat in readout_optimi | At the readout SNR CSTQ03 actually runs (analog SNR about 0.8-1.5), the overlap-error map is mostly NaN, biased and not reproducible. It also discards the g/e l |
| F60 | B | low | readout-singleshot | `readout_optimize.py` | ReadOpt_wSingleShotFF.acquire / QubitPulseOpt_wSin | Both optimisation maps save point estimates with no uncertainty and no optimum. At the default 1000 shots per class the per-point noise (sigma_C of about 0.015- |
| F61 | B | low | readout-singleshot | `single_shot.py` | SingleShotProgramFFMUX.acquire / display | The single-shot step does not save its own figure of merit: no contrast, assignment fidelity, per-class errors or SNR. Readout quality and drift therefore canno |
| F62 | B | low | readout-singleshot | `readout.py` | hist_process | Confirmed known off-by-one threshold (left bin edge), which costs less than 0.1% contrast out of sample. Also, the 'pooled' and 'per_class' normalisations give  |
| F63 | B | low | readout-singleshot | `single_shot.py` | SingleShotProgram.initialize (also ActiveResetVeri | The cross-clock readout-window and tone-extension arithmetic is copied in full into SingleShotProgram and ActiveResetVerifyProgram rather than calling `core.rea |
| F64 | B | low | coherence | `auto_coherence.py` | _stage_singleshot_optimize / _stage_optimize_reado | The pi gain (and the readout window) is picked as the argmax of noisy single-shot contrasts from 1000 shots each. The result scatters by about 4% rms in gain, w |
| F65 | B | low | coherence | `auto_coherence.py` | AUTO_COHERENCE_PARAMS relax delays / T1 window; _s | Neither the relax delays nor the sweep windows are checked against the T1 that the pipeline itself measures. On CSTQ03 (T1 about 50 us) every stage waits 3500 u |
| F66 | B | low | coherence | `t1_single_shot.py` | T1_SS.acquire/display | T1_SS produces neither a T1 nor calibrated populations. It plots the raw thresholded excited fraction with no fit and no readout-error correction, although the  |
| F67 | B | low | coherence | `t2_ramsey.py` | T2R.display f_report / use_fft_freq | When one FFT peak dominates, the legend reports the FFT bin frequency as 'USED' instead of the fitted frequency. Its resolution is 1/(N dt) = 50 kHz for 201 x 0 |
| F68 | B | low | coherence | `iq.py` | min_q_range_phase (T1FF, T2EMUX) | The min-Q-peak-to-peak grid estimator is adequate for T1 and T2E: the fitted T scatter is identical. Its angle error, however, is 2.5-3x that of a principal-axi |
| F69 | B | low | spectroscopy-transmission | `cw_tones.py` | ConstantTwoTone / SingleTone / runs.resonator.run_ | The 'CW' tones are made by reprogramming the board up to 1e6 times, or by 100 x 1e5 x 1000-rep acquires (about 42 h) with gaps between pulses. QICK 0.2.334 supp |
| F70 | B | low | spectroscopy-transmission | `qubit_spec.py` | saved payloads: lorentz_* (QubitSpecSliceFF), fit_ | No calibrated quantity in this domain is saved with an uncertainty. pcov is computed and dropped (Lorentz centres, Qint, pi gain), or never computed (chi), and  |
| F71 | B | low | spectroscopy-transmission | `spectroscopy.py` | run_spec_gain_length_sweep | The gain x length grid exists to choose a spectroscopy power, but it produces no summary: no linewidth or height vs gain, and no zero-power extrapolation. The u |
| F72 | B | low | charge-parity-mr | `charge_dispersion.py` | run_charge_dispersion_quasicw / run_two_tone_charg | The quasi-CW 'telegraph' is a per-shot g/e classification, not a parity trace. Under a saturating drive the resonant parity gives P(e) <= 0.5, and at the config |
| F73 | B | low | zero-span-undriven | `dwell.py` | _fit_exp_dwell / dwell_time_statistics | The tau from a log-linear fit to a histogram is biased high by about 15 % at the dwell counts typical of a stage-7 or threshold-stability record (100-300 dwells |
| F74 | B | low | zero-span-undriven | `undriven_single_shot.py` | UndrivenSingleShot._acquire_at_bias / save_data | Each 1e6-shot pass saves 16 full-length float64 arrays (128 MB), and at most 2 of them are primary data. With the documented Repeat = 10000, that is about 1.3 T |
| F75 | B | low | zero-span-undriven | `zero_span.py` | sliding_window_switch_rate | The per-window Python loop with a full-length boolean mask is O(M*N). At the default 12 s record it takes tens of seconds per call and minutes for longer record |
| F76 | B | low | zero-span-undriven | `rates.py` | rate_vs_bin_size vs rate_vs_bin_size_us; autocorre | Two duplicated pairs have diverged, so MR and Undriven compute 'the same' bin-size rate with different denominators. |
| F77 | B | low | acquisition-timing-infra | `experiment.py` | H5File.add / NumpyJSONEncoder / data_paths | Extends the known add()/float64 bug. A failing write leaves a zero-filled dataset and aborts the remaining keys, so the h5 looks valid but holds zeros. The JSON |
| F78 | B | low | acquisition-timing-infra | `coherence.py` | update(): mathi(..., us2cycles(cfg['step'])) vs x_ | The time axis of register-swept waits assumes the unquantised step while the register advances by round(step*f_time) cycles. The resulting relative error biases |
| F79 | B | low | acquisition-timing-infra | `iq.py` | min_q_range_phase | The rotation used for T1, T2E and Rabi is chosen by minimising the peak-to-peak of Q on a 200-point grid. Peak-to-peak is set by the largest noise outliers, so  |
| F80 | B | low | acquisition-timing-infra | `rfsoc.py` | make_proxy | The Pyro4 proxy has no communication timeout (COMMTIMEOUT 0, i.e. infinite), and qick polls with timeout=None. A board that reboots or loses its network mid-run |
| F81 | B | low | acquisition-timing-infra | `attenuator.py` | setatten / module import | Confirms the known attenuator bugs (NameError on a negative readback, fixed range(5), silent no-op when the serial is missing). In addition, the module still ca |
| F82 | B | low | orchestration-params | `auto_coherence.py` | run_auto_coherence / _run_auto_coherence (qubit_pa | AutoCoherence takes the qubit frequency, pi gain, sigma and flat-top from the readout qubit's entry and ignores Qubit_Pulse. In a cross-qubit session it calibra |
| F83 | B | low | orchestration-params | `coherence.py` | T2E_CLOCK_STEP_US / auto_coherence._T2E_CLOCK_STEP | The tProc cycle is hard-coded twice as 0.00232515 us (1/430.08 MHz) instead of being read from soccfg. On a board with another tProc clock, T2E steps are no lon |
| F84 | B | low | orchestration-params | `spectroscopy.py` | silently ignored parameters (run_two_tone_spec, ru | Several run_* functions accept a parameter dict and then ignore or override keys the user sets, so edits have no effect. |

## Tier C (needs hardware validation; proposals only)

- **single_shot.py: SingleShotProgramFFMUX.acquire (and readout_optimi** — The g and e clouds come from two separate, back-to-back programs (about 6 s each in regime B). Readout drift between the two blocks therefore enters the angle, threshold and contrast directly, and every calibration pays 
- **auto_coherence.py: _stage_sweet_spot_search criterion; docs/glossary.** — The 'sweet spot' the search converges to (minimum parity-branch separation, where the branches cross) is the point of maximum first-order offset-charge sensitivity of each branch, not a charge-insensitive point. T2*/T2E 
- **fitting.py: fit_exp_decay as used by T2EMUX.display (and T2R e** — T2E is fitted as a pure exponential. For 1/f-type dephasing the echo envelope is exp(-t/2T1)·exp(-(t/Tφ)^2), so the reported 'T2E' depends on the sweep window by about 25%, while the quoted error bar is about 2%.
- **fitting.py: hanger_model_db (dB-magnitude fit)** — Fitting 20log10|S21| unweighted throws away the phase (which resolves the coupling degeneracy and the impedance-mismatch asymmetry) and gives the noisy dip bottom too much weight. A complex circle fit (Probst et al. 2015
- **modified_ramsey.py: ModifiedRamseyProgram.body / run_modified_ramsey c** — The controls are separate records taken minutes after the parity record, so drift, rate changes and ng drift confound every comparison. A phase-alternating interleave inside one record would test the mapping directly.
- **zero_span_validation.py: run_modulation_check (stage 3) design** — Stage 3 builds the square wave from separate acquire() calls, one block per program run, so the recovered modulation only proves static drive-on/off contrast. It cannot check time resolution, gap-free continuity, or the 
- **zero_span.py: run_zero_span_parity drive/readout operating point** — The CW parity drive defaults to the device pi-pulse gain and the CW readout to the single-shot readout gain. No stage picks gains that maximise branch selectivity (on-branch contrast vs off-branch leakage under power bro
- **readout.py: adc_trig_offset (no time-of-flight calibration)** — The ADC trigger offsets in use (0.3 us regime A/B, 0.488 us zero span, 1 us BASE_CONFIG and AutoCoherence) are not derived from a measured DAC-to-ADC time of flight, and the code has no step to measure one. The integrati
- **{t1,t2_ramsey,t2_echo,rabi,single_shot,modified_ramsey,...}.py: add_gauss(sigma=us2cycles(sigma, gen_ch), length=u** — sigma and the envelope length are rounded to fabric cycles independently, so the documented '4 sigma' envelope is violated, and the realised sigma differs from cfg['sigma']. The timing and drive-bandwidth models use cfg[

## Gaps per domain

### readout-singleshot

What the domain cannot establish today. It reports one number, the contrast C = P(g|g)+P(e|e)-1, and that number mixes three different errors: separation-limited readout error, state-preparation error (thermal population plus pi infidelity) and T1 decay during the readout window. Nothing separates them. There is no heralding/pre-selection readout, the per-class errors are not saved, and the thermal-population estimator is biased (finding above), so the code cannot tell a bad readout from a hot qubit or a bad pi pulse. There is no repeated-readout (QND/measurement-induced transition) test as a function of readout gain. readout_optimize can therefore pick a gain that maximises C while it drives transitions that hurt active reset and parity tracking; ARV only measures this indirectly, at one gain. The readout window length and adc_trig_offset are never optimised in this domain (only auto_coherence scans them). adc_trig_offset (0.3 us) has no recorded time-of-flight calibration (no decimated trace of the readout pulse). Integration uses a boxcar only, with no matched-filter weights. No step reports statistical uncertainties (sigma on C, a confidence interval on the threshold, ARV P(g) error bars). Readout drift is visible in the notes but is never monitored automatically, for example by periodic g/e checkpoints with a tolerance gate. For active reset, the threshold is the midpoint of the cloud means rather than the error-optimal or prior-weighted point; there is no gate that refuses to arm the reset when the analog SNR is too low for the decision to beat random; and κ (and so the 6/κ wait) is unmeasured for CSTQ03. The core decision path has not been validated on hardware since the read-latency fix and the sign-offset change. ARV, as it stands, cannot validate it either, because it runs a different copy of the reset and discards the reset reads. Rotation conventions are consistent: rotate_data, hist_process, MixedShots and classify_thermal_tail all use I' = I cos(theta) - Q sin(theta), and res_phase is in register units everywhere. Readout-clock handling is consistent among SingleShotProgram, ActiveResetVerify and ModifiedRamsey (the T1_SS mismatch belongs to another domain). The active-reset units (normalised threshold times ro_norm) and the ro_norm<<15 offset in the mixin are correct for signed and unsigned comparison.

### coherence

The code takes data well enough, but on its own it cannot establish most of the numbers a coherence benchmark needs.

1. **Fits are not saved.** Fit parameters, uncertainties and the rotation angle are never saved. T1/T2*/T2E repeated over hours (repetitions 1000/3000, interleaved cycles) therefore cannot become a time series, a mean ± spread, or a fluctuation (TLS/telegraph) analysis without refitting every file.

2. **No honest error bars.** QICK averages the rounds internally and returns no per-point uncertainty, so every fit is unweighted. The error bars are curve_fit's residual-scaled values: no chi-square, no residual or goodness-of-fit flag, and no model comparison. For T2E this hides a ~25% window-dependent bias behind ~2% errors.

3. **No adequacy checks.** Nothing checks that:
   - the sweep window is 3-10 T,
   - relax_delay >= 5 T1,
   - the Ramsey fringe is below Nyquist and above the FFT resolution,
   - the pi pulse is good (contrast against the SS calibration).

   Time axes are nominal (start + i·step in us) rather than the realised cycles. The error is negligible for the current steps (0.02% at 0.1 us), but would reach ~7% at a 0.01 us step. start is loaded as raw cycles (known). Echo x_pts exclude the pulse durations (known).

4. **No absolute populations.** min_max is manual, and T1_SS has neither a confusion-matrix correction nor a fit. The code therefore cannot state the residual excited (thermal) population or the π-pulse error.

5. **f_ge is never fed back.** Ramsey at zero detuning gives neither the sign nor a precise value of the detuning, and nothing feeds it back into f_ge, in auto_coherence or across interleaved cycles.

6. **Paired T1/T2 are never combined.** The combos measure T1 and T2E back to back, but never compute pure dephasing Tφ. CPMG-N is available, but the uniform spacing (non-CPMG for n ≥ 2) prevents standard noise-spectroscopy use.

7. **Charge-parity bias point is not tracked.** The sweet-spot search drives to the branch-degenerate point, which is maximally charge-noise sensitive, and calls it charge-insensitive. Nothing measures coherence at the true charge-insensitive point (maximum splitting), and nothing re-checks the offset charge after the long T1/T2/T2E stages. The coherence records therefore do not say which charge condition they were taken at.

8. **Readout window and failure handling.** T1/T2R/T2E integrate 1.4x the configured readout window (known), so window optimisation does not transfer to them. A single fit failure loses the record and, in auto_coherence, the whole calibration summary.

### spectroscopy-transmission

The domain code does run each measurement, but it cannot yet back its own numbers. (1) No fit in this domain is gated by significance or goodness of fit before its result is carried over or used. pulse_freq is overwritten from a hanger fit to pure noise (golden: Qtot 2.5e5 +- 1.7e6 accepted). Parity doublets are 'found' in a single line. The Rabi pi gain is reported from fits that locked onto the wrong period. (2) No uncertainty is saved for f0, Qi/Qc, the spec line centres, the parity splitting, chi or the pi gain, so drift between runs cannot be told from noise. (3) Calibration steps that are missing: readout power and photon-number calibration (power-dependent transmission or punch-out, and the AC-Stark / measurement-induced shift giving n-bar per pulse_gain); qubit thermal population (it sets the bias in chi and the contrast in spec); a check that the readout frequency is placed for g/e discrimination (the carry-over is the |g> dip, and chi is measured but never used to set pulse_freq); a Rabi chevron or detuning check and decay in the Rabi model; a spectroscopy-linewidth vs power extrapolation (T2* bound, saturation). (4) For charge-sensitive qubits, nothing checks that the spec or Rabi pulse bandwidth is much smaller than the parity split, or calibrates per parity branch. The Gaussian spec/Rabi pulses (sigma 0.08 us, about 2 MHz bandwidth) drive both branches at once. analyze_charge_dispersion (same module) fits one Lorentzian per gate row, so on a split row it returns the blended centre, not the two parity branches. (5) What checks out: the sweep axes match what the programs step. Transmission/chi frequency points are within 4 Hz of the freq2reg-rounded tone. The register-swept spec axis accumulates at most 27 Hz on board A and 157 Hz on board B over 401 points. The register gain sweep is exact; AmplitudeRabiFF_N differs by less than 1 DAC unit (known). The P/2 rule is the right physics (theta proportional to gain, ground state at gain 0); the problem is only fit convergence and the grid-search extremum rule. Scratch evidence scripts: /tmp/qlreview/{hanger,hanger_mc,hanger_qint,doublet,dbl,rabi,rot,chi,board,freqgrid}.py.

### charge-parity-mr

The parity-mapping sequence is implemented as documented: centre-to-centre tau = k/(2df), closing phases 180/90 deg plus the flip, and correct 4-sigma and 8-sigma feasibility. One caveat: in the symmetric scheme the parity-to-state sign flips with k mod 4 (k=1,5 map upper to e; k=3,7 map upper to g), which the docs table does not say.

The HMM algebra is sound: exact expm(Q dt), log-space forward/backward and Viterbi, pairwise xi, and rate conventions consistent with the ACF and PSD (gamma = 1/(2 tau_corr) = pi f_c, gamma_eff = (g01+g10)/2). On correctly specified synthetic data the HMM, ACF and PSD agree within about 10% at 2*gamma*dt = 0.1-0.5. The sample period, including active-reset overhead, is handled correctly via the emitted schedule, and there is no dead-time bias because the HMM treats the record as a sampled continuous-time chain.

What the code cannot currently establish:
- **Mapping calibration.** It cannot measure the parity-to-state mapping. The p's are assumed, and a mis-specified value biases the rate by 10x while passing every gate.
- **Clean readout clouds.** The e cloud is moment-matched from a pi pulse that is itself parity- and bandwidth-limited.
- **Temporal correlation.** It does not test that a fitted telegraph is temporally correlated at all: the null is a single Gaussian rather than an i.i.d. mixture, and nothing checks that the rate is resolved at the cadence.
- **df and offset charge.** It has no step that verifies df or f_upper at the operating bias: no tau or detuning fringe, no df tracking across cycles while the offset charge drifts, and no record of the bias at which df was measured.
- **Inter-shot correlation.** Nothing checks for inter-shot carryover automatically. drive_off, the control that caught it, is informational, and the configured controls are never acquired when online analysis is off.
- **Uncertainty.** No error budget combines calibration, mapping and drift uncertainty: the bootstrap is parametric under the fitted model only.

On the charge-dispersion side:
- There is no extraction or fit of the doublet splitting vs bias, so cd_max and the period, and with them the MRC tau and the sweet-spot step, rest on an untraceable external fit (already 4x inconsistent with the measured df).
- Grid density is not checked against that period.
- The Ramsey dispersion step has zero contrast by construction.
- The quasi-CW step reports projection noise as a telegraph.

Yoko handling is unchanged from the known list: no restore in the spec charge sweep, the two-tone search or MRC, yoko_fixed is ignored in the searches, and ramp_to checks +10 V only. In addition, no settle time is applied after a ramp in the spec sweep or the searches. All synthetic evidence can be rerun from /tmp/qlreview/*.py (sim_hmm_null, sim_hmm_rates(2), sim_fitp, sim_controls, sim_lr, sim_emis(2), bloch, bloch2-4).

### zero-span-undriven

I would not yet trust the zero-span parity code to measure a parity-switching rate. With the default 'apriori' classifier, the per-sample bits track the driven qubit's state rather than the parity. The headline baseline rate reads 0 Hz in the expected regime. Every reported rate is a threshold-crossing count, so it is inflated by roughly 2*eps/sample_period. None of those rates or dwell times comes with an uncertainty, and the record saves no estimate of eps (separation or overlap of the two parity levels). Nothing checks that the record is bimodal before it reports rates: KMeans will 'find' switching in a single blob, such as the drive-off control.

Calibration steps that should come before the main record are missing:
- The parity branches are not located under the CW readout actually used (Stark shift and measurement broadening against the 0.2-2.7 MHz splitting).
- The drive gain is not optimised for selectivity.
- The stage-1 probe and stage-2 branch results are not fed back.
- No closed-loop test injects a known telegraph to calibrate the rate estimator against real noise.

Stages 4-6 (bimodality, bin-size dependence, threshold stability) exist only as unused functions, and stage 8 variant D tests a statistic that cannot flip.

Time-base problems:
- The strobe period is exact in the default regime (synci = us2cycles(sample_period)). It silently stretches whenever the 1.4x readout-window bug pushes the window past the sample period.
- Chunk dead times are neither modelled nor fully recorded (start times only), so bursts cannot be placed on a wall-clock axis precisely enough to correlate with external impact detectors.
- The 16384-rep chunk cap that creates these gaps is not a qick limit.

The decimated path cannot observe parity switching: about 3.3 us captures (1024 samples at 307.2 MHz) separated by milliseconds of Python dead time, against 2-3 ms dwells and at very low per-sample SNR. Its 'unverified 430 MHz' rate is explained by the declare_readout bug: the sample rate f_output is correct, and the buffer held 1.4x more samples than planned.

For undriven single shot:
- The analysis is functionally correct and fast at 1e6 shots: about 5 s with FFT ACF and GMM.
- Its rates are the qubit's g<->e jump rates, again biased by readout error. The HMM that would fix this exists but is not called.
- The bin-size 'plateau' rule cannot tell readout noise from real switching faster than the sampling period: iid fake data gives 1384 -> 0 Hz with a 'noise' warning.
- The principal-axis projection assumes the noise is isotropic.
- Storage is about 8x larger than needed.

Neither experiment logs temperature or other environment metadata alongside the record.

### acquisition-timing-infra

The infrastructure runs programs and writes files. It cannot yet establish five things.

(1) Whether the readout it uses is the one it thinks it uses. No step measures the DAC-to-ADC time of flight. The regime-A window is 1.4x longer than the tone. Nothing checks Nyquist zones or images: 5 of 6 CSTQ03 readouts are 3rd-zone images. The 'Device.validate()', 'Session/run()' and 'connect() finally' safety layer described in docs/hardware.md, config_regimes.md and adding_a_device.md does not exist in the tree yet (core has no device.py or session.py). Today build_context performs no validation beyond the readout-window sign checks.

(2) Under what conditions a file was taken. There is no qick or board version, board config, git commit, device or cooldown, drive-qubit identity, measured yoko level, end time or program hash. The yoko level in the cfg is the session value even after steps moved it. That is why the device page carries many 'qubit/date not recorded' entries.

(3) Measurement health. There are no per-run checks of readout saturation or accumulator overflow, no ADC-level or IQ-offset monitoring, and no record of retries or failed attempts. The stale-shot-counter retry covers only CavitySpecFF.

(4) Uncertainty at the bookkeeping level. Display-time fit results such as rotation angles, fit parameters and covariances mostly live only in PNG titles and printouts, not in the h5. Calibrations are not appended to a calibrations log (the documented calibrations.jsonl is not written by current code).

(5) Robust completion. Analysis runs before saving, long sweeps save only at the end, the RFSoC connection has no timeout, and the bias source has no read-back check. A failed fit, a hung board or a refused setpoint can therefore lose data or leave the measurement at an unknown bias without the user knowing.

### orchestration-params

The orchestration layer can run every step, but it cannot establish several things a careful session needs.

**Hardware it cannot see**
- It never checks which tone actually reaches the device. There is no Nyquist or image check, and on the implied 6881.28 MS/s DAC, Q2 and Q4 are driven from the second zone with an NRZ image 1.6-6 dB stronger.
- It never measures the readout time of flight. ADC_Offset is 0.3 us in one place and 0.488 us in another, and both are uncalibrated.
- It has no readout photon-number calibration (AC-Stark or measurement-induced dephasing), so readout gain is set by notes like "too much".
- It does not measure the qubit's thermal or residual excited population, which every parity-rate estimate depends on.

**State it does not record**
- The bias actually applied: most records carry the session value, and with yoko_fixed the values are invented.
- The TWPA state. Nothing records the bias or pump, or even whether the pump is on. The documented bring-up order leaves it off, and the SynthHD cannot be queried without switching it off.
- The real board's soccfg, so dry-run validation is only as good as a synthetic board.

**Statistics it does not propagate**
- Calibrations are written back or printed with no uncertainty and no quality gate. Noise fits become readout frequencies.
- Nothing re-centres f_ge or f_res during multi-day loops (interleaved coherence, Repeat=10000, num_cycles=1000).
- T2R runs at freq_shift 0 with no artificial detuning, so the sign of the detuning cannot be recovered.

**TWPA calibration**
- It measures PNA-X gain only, with no noise-temperature or SNR-improvement measurement through the actual RFSoC readout (single-shot separation/σ with pump on vs off).
- It has no compression check (gain vs probe power).
- pump_sweep ranks points on raw transmission without a pump-off reference.

**Session-level checks**
- Nothing preflights gain overflow, which wraps silently in qick 0.2.334.
- Nothing preflights cross-dict consistency: MR f_ge against the selected qubit, ARV against MR reset timing, pi2/pi ratio, the ZSP window against the separator window, or relax_delay against a known T1, even though the runner's own MR notes trace a spurious kHz parity rate to insufficient relax.
- There are no runtime or disk estimates.
- There is no session log tying steps, carry-overs and hardware state together.

Phase 5 as designed fixes the shared-dict and typo problems: keyword-only recipes, per-qubit ParityParams, and a finally around the yoko close. It does not fix the provenance, image, gain-range, carry-over-quality or TWPA-state gaps unless the additions above are made. The design and the docs also currently disagree on whether A carry-overs survive a single-shot (B) excursion.

Scratch demonstrations are in /tmp/qlreview/ (nqz.py, gain.py, hanger.py, noisefit.py).
