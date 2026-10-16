# Troubleshooting

Symptom -> cause -> what to do. Search this page for the exact error text. Entries marked
**(legacy bug)** are known defects that the refactor preserves on purpose; they are fixed only in
separate, reviewed commits.

## Connecting and instruments

| Symptom | Cause | Fix |
|---|---|---|
| `locateNS` fails / `NamingError` on connect | not on the lab network, or the board's Pyro4 nameserver is down | check that `192.168.0.103:8888` answers; old docs naming `192.168.1.7` are stale ([hardware](hardware.md#rfsoc)) |
| `RuntimeError` / version mismatch in the regression tests | client qick is not 0.2.334 | reinstall from `pyproject.toml` |
| `KeyError: 'gens'` from `"gens" in soccfg` | `QickConfig` has `__getitem__` but no `__contains__` | use `try: soccfg["gens"] except KeyError` |
| Bias is not where the session says | an earlier step (sweet-spot search, `charge_sweep`, two-tone charge dispersion, Modified Ramsey control) moved the yoko and did not return it | read `:SOUR:LEV?`; re-ramp; see [hardware](hardware.md#charge-bias-yoko) |
| `ValueError` "exceeds the 10 V charge-line limit" | `ramp_to` rejects \|target\| > 10 V on both signs | check the sign and value of the bias |
| `RuntimeError` "yoko level reads ... after ramping" | the read-back level differs from the target by more than 1e-4 V: either the active GS200 range clipped it (target above 1.2x the range), or the range is too coarse to resolve it (the 30 V range resolves 1 mV) | clipped: set a larger range (output off); off by under 1 mV on the 30 V range: set the 10 V range (output off) |
| `connect()` refuses the yoko ("TWPA bias source", "sourcing current with its output ON", "exceeds the active ... V range", "active voltage range is 30 V") | `yoko_addr` is the TWPA source (any spelling of GPIB board 1, address 12), or the source is biasing something in current mode, or `bias_v` is above the active range, or the source is on the 30 V range | check `yoko_addr`; set the 10 V range (or smaller) with the output off; see [hardware](hardware.md#charge-bias-yoko) |
| Yoko output still on after a crash | closing VISA does not switch the output off; the legacy connect also turned it on before validating the readout window | intended (bias holds); ramp to 0 by hand if you want it off |
| Attenuator does nothing / `OSError` loading `VNX_atten64.dll` | DLL directory not registered (Python >= 3.8 ignores `PATH`), DLL not present, wrong serial | pass `dll_dir=`; the DLL is not in the repo; default serial 27786 |
| `NameError: result` from the legacy attenuator driver in verbose mode | typo in a print when the readback is negative **(legacy bug)** | use `qicklab.hardware.attenuator` |
| SC5510A connects to the wrong host | `SC5510A_SERVER_HOST` is read at import | set the variable before importing |

## Acquisition errors

| Symptom | Cause | Fix |
|---|---|---|
| `ValueError: could not broadcast input array from shape (26,2) into shape (20,2)` (numbers vary; second = reps) or "got too much data" | stale tProc shot counter when programs run back to back ([averaging](concepts/averaging.md#the-stale-shot-counter-race)) | re-run; use fewer `rounds` and more `reps`. `transmission_fit` / `transmission_sweep`, `t1_single_shot` and `undriven_single_shot` retry automatically (3 tries, `soc.stop_tproc()`, fresh program) |
| `Overflowed the averages buffer` | tProc outruns the readout | lengthen `relax_delay`; do not retry unchanged |
| `ValueError: cannot reshape array of size 1 into shape (1,1000)` | qick >= ~0.2.29x averages `di_buf`; code expects the raw per-shot stream | keep client qick 0.2.334, or read `prog.acc_buf` via `raw_shot_buffers` |
| `AxisSignalGen: buffer length must be 65536 samples or less` | envelope memory full (long sigma; separate pi and pi/2 envelopes) | share one envelope; shorter sigma ([timing](concepts/timing_and_units.md#pulse-envelopes)) |
| qick warning "possibility that the sum buffer will overflow" | declared readout window above 2^16 samples | shorten the window |
| `RuntimeError: requested frequency ... is outside of [-range/2, range/2]` | frequency outside the DDS band of the generator | check the value and the generator's `f_dds` |
| Only the last round's shots in a single-shot record; fewer shots than expected | `rounds > 1` in a single-shot style program (raw buffer keeps the last round) | `rounds = 1`; raise `reps` / `shots` |
| `TypeError` about `debug=` from an old single-shot class | dead legacy classes called qick `acquire(debug=...)` | deleted in the refactor; use `SingleShotProgramFFMUX` |

## Config errors (KeyError, ValueError at build)

| Symptom | Cause | Fix |
|---|---|---|
| `KeyError: 'pi2_SS'` in `qubit_optimize` | step called under regime A | it is a regime-B step; let `run()` switch ([config regimes](concepts/config_regimes.md)) |
| `KeyError: 'df'` with `charge_dispersion_ramsey` | the step reads `df` from a parameter dict that never had it **(legacy bug)** | pass `df` explicitly |
| `KeyError: 'voltage_start'` (or the sweep uses the wrong range) in `undriven_single_shot` after a switch | regime B drops `voltage_start/end/step` | pass the range in the step's own parameters |
| `ValueError: cfg['length'] must cover cfg['adc_trig_offset'] + cfg['readout_length']` | `length` set by hand shorter than offset + window | do not set `length`; the builders derive it ([readout window](concepts/readout_window.md)) |
| `ValueError` on `readout_length_us` / `adc_trig_offset_us` at connect | window <= 0 or offset < 0 in the device file | fix the device `ReadoutWindow` |
| `ModifiedRamsey` raises in `initialize` (wait <= 0, df too large, bandwidth ratio, `flattop_length` set, `rounds != 1`, `cmp_offset >= 2^30`) | the requested timing or reset is infeasible; the message says which | see the [Modified Ramsey page](experiments/modified_ramsey.md); typically raise the tau harmonic k or lower sigma |
| `symmetric_ramsey=True` raises about `f_upper_mhz` | the upper parity branch is not set for the qubit | measure the doublet and set `parity.f_upper_mhz` in the device file; there is no silent fallback to the centre frequency any more |
| `ZeroSpanParity` raises `RuntimeError` at construction | a zero-span hard constraint failed (sample period, 16-bit cycle cap, `avg_maxlen`, `buf_maxlen`, DDS band, missing key) | the message names the rule; see the [zero-span page](experiments/zero_span_parity.md) |
| `ZeroSpanParity` refuses `soft_avgs > 1` | averaging captures destroys trajectories | keep 1, or set `allow_soft_avgs=True` deliberately |
| `RuntimeError` from `set_qubit_gain` in zero span | validation stages need strobe mode | use `mode="strobe"` for the validation harness |
| Modified Ramsey control with `use_active_reset` raises about `readout_threshold` | the control step never calibrates the reset threshold **(legacy bug)** | run it without active reset |
| Modified Ramsey with `use_apriori_separator=False` aborts after the first record | the check runs after acquiring and saving cycle 0 **(legacy bug)** | keep `use_apriori_separator=True` |
| T2E prints "Step size is 0!" and stops (after T1 already ran in the combined steps) | `T2_max_us` too short for `T2_expts x (num_pi_pulses+1)` tProc cycles | raise `T2_max_us` or lower `T2_expts` ([timing](concepts/timing_and_units.md#t2e-step-quantisation)) |
| `TypeError` with `rotation_angle=None` in `t1` | `T1FF` multiplies by `exp(1j*None)` **(legacy bug)** | omit the key or give a number |
| `KeyError: 'min_max'` in `t2_echo` | `rotation_angle` given without `min_max` **(legacy bug)** | give both or neither |
| `ValueError` "not a finite number" or "thermal mode" in `t1_ss` | `calibrate_SS=False` with `threshold`/`angle` None or NaN, or the calibration single_shot failed (NaN threshold) or ran in thermal mode | calibrate first or pass `threshold` and `angle`; check the `SingleShot/` record ([t1_single_shot](experiments/t1_single_shot.md#how-to-run)) |
| `AttributeError` / `NameError` at the end of `charge_sweep` | empty voltage list or first voltage above 10 V ends the loop before anything is created **(legacy bug)** | check the voltage range |
| `TypeError` from `save_data()` with no argument | every `save_data(data=None)` override indexes `None` **(legacy bug)** | pass the data dict |
| `ValueError` when saving a key twice, or saving complex/string data | the base h5 writer always creates float64 datasets and cannot overwrite | save once; convert complex to real/imag |

## Plots and files

| Symptom | Cause | Fix |
|---|---|---|
| No plot window appears; `plotDisp=True` does not block | importing the analysis package switches matplotlib to Agg | PNGs are still saved; interactive plots return with `Session(interactive_plots=...)` (planned) |
| `UnicodeEncodeError` writing `EVIDENCE.md` (zero-span validation) | file opened with the Windows default code page (cp1252) **(legacy bug)** | none yet; run with `PYTHONUTF8=1` |
| Saved `.json` shows `pulse_freq` at the edge of the sweep | `CavitySpecFF` sweeps `pulse_freq` in place; with `fit=False` or a failed fit it stays at the last point | expected; use the fit result or the step's printed value |
| Paths with mixed `/`, `//`, `\` | `outerFolder + path` concatenation | expected; do not normalise ([hardware](hardware.md#data-paths)) |
| T2 (Ramsey) / chi values missing from the h5 | these fits are drawn in the PNG title but not saved (T1 and T2E fits are saved as `t1_fit_*` / `t2e_fit_*`, see [t1](experiments/t1.md#outputs)) | refit from `x_pts`, `avgi`, `avgq` |
| Rabi pi marker missing, x axis autoscaled to ~1e9 | the cosine fit failed (no visible oscillation) and returned a runaway period | raise `max_gain`; compare with transmission data |

## Results look wrong

| Symptom | Cause | Fix |
|---|---|---|
| Spectroscopy peak on a noise spike, or a broad line shown as a dip | analysing `\|I + iQ\|` instead of the projection | use the principal-axis projection ([IQ conventions](concepts/iq_conventions.md#2-spectroscopy-principal-axis-projection-not-i--iq)) |
| Single-shot "Fidelity = 45%" looks low | the number is the contrast C, not the assignment fidelity | F_assign = (1 + C)/2 = 72.5% for C = 0.45; since 2026-10 the png says "Contrast C" and the h5 saves `contrast_hist<r>` and `assignment_fidelity<r>` |
| `WARNING: no resonator dip passes the carry-over gate`; later steps still read at the old `pulse_freq` | the transmission trace failed the depth, linewidth or edge check (no resonator in the window, too little averaging, dip at the sweep edge, a dip wider than about (span - 10 steps)/6 so fewer than 10 baseline points remain (~1.6 MHz on +-5 MHz), a single bad point, a resonance narrower than 2 frequency steps (kappa below 0.1 MHz on the default +-5 MHz / 201-point grid, step 0.05 MHz; printed as `frequency steps (< 2)` or `a single-point dip`), or a hanger fit pulled off the dip by a tilted background) | read the printed reasons and metrics. Too shallow: raise `reps`. At the edge: re-centre. Too wide (fewer than 10 baseline points): widen `span`. Too narrow for the grid (`frequency steps (< 2)`, `single-point dip` on a dip you can see): raise `num_points` or narrow `span` so the step is at most kappa/2; widening `span` makes it worse ([carry-over gate](experiments/transmission_fit.md#carry-over-gate)) |
| Fitted resonator frequency not used by `single_shot` | carry-overs are discarded when switching to regime B | put the value in the device file ([config regimes](concepts/config_regimes.md#what-changes-at-the-switch-a---b)) |
| `single_shot` after `active_reset_verify` has a rotated blob again | `res_phase` reset to 0 by the switch to regime B | expected |
| `t1_ss` populations off (data from before 2026-10-15) | until 2026-10-15 `T1_SS` played `qubit_gain` (the pi gain only in regime B; now `pi_gain`) and its IQ scale differed from the single-shot calibration by 1.4x ([readout window](concepts/readout_window.md#history)) | re-take `t1_ss` data from before 2026-10-15 |
| Rabi sweep ends below `max_gain` | `step = int(max_gain/number_of_steps)` truncates (10000/101 -> 99, end 9900) **(legacy bug)** | choose `number_of_steps` dividing `max_gain` |
| Kappa from the hanger fit looks wrong | the printout and the saved `hanger_fit_kappa_tot_mhz` / `hanger_fit_kappa_ext_mhz` are kappa/2pi in MHz (before 2026-10 the single `hanger_fit_kappa_mhz` was 1e6 too small and was the external rate) | for 6/kappa use the angular value: 6/(2 pi x kappa_tot/2pi) |
| Rabi rotation looks off with two ADCs (data taken before 2026-10-14) | `AmplitudeRabiFF` estimated its rotation over both ADC channels, so the ADC 0 - ADC 1 offset set the angle and contrast leaked into Q; now ADC 0 only, with a fixed sign ([IQ conventions](concepts/iq_conventions.md#3-rotations-used-by-individual-experiments)) | for older data re-rotate the I/Q traces of ADC 0 directly; check `iq_axis_contrast_ratio` on new data |
| Averaged IQ amplitudes differ from records taken before 2026-10-15 | regime-A programs declared the window in tProc cycles (1.4x `readout_length` on the lab board, ~6 us after the tone) until the fix | compare fitted quantities, not raw IQ amplitudes, across the date ([readout window](concepts/readout_window.md#history)) |
| Active reset fires the pi on ground-state shots, more for long windows | comparison wraps: tProc compares unsigned; offset too small | `ModifiedRamsey` and `active_reset_verify` use `int(ro_norm) << 15` (ARV used `1 << 24` before 2026-10-13: re-take older ARV data) ([IQ conventions](concepts/iq_conventions.md#6-active-reset-thresholds)) |
| Symmetric Modified Ramsey shows almost no contrast (90 deg closing phase "failing") | `f_ge` set to the doublet centre, so the drive sits on the lower branch | set the **upper** branch frequency (`parity.f_upper_mhz`) |
| Spurious kHz parity rate in Modified Ramsey; the `drive_off` control shows even more correlation | incomplete inter-shot reset: with no relax delay most of the previous shot's excitation carries over (CSTQ03 Q2, 2026-08-04) | `mr_relax_delay` >= 5 x T1 (250 us for T1 = 50 us) |
| HMM withholds the rate ("emission SNR" gate) | per-sample readout separation x \|p1 - p0\| below `hmm_min_emission_snr` = 0.7 | improve readout SNR or measure the mapping probabilities. **Do not lower the gate**: at 0.3 on CSTQ03 Q2 (2026-08-04) the HMM gave 4921 +- 68 Hz vs ACF 9606 Hz vs PSD 15056 Hz and locked onto a 50-200 us correlation, not parity. An older code comment advised lowering it; that advice is wrong |
| `KeyError: 'mu0'` in the Modified Ramsey HMM plot | old bug with g/e-mixture emissions | fixed (a test guards it); update |
| Undriven single-shot rate looks too low | shortest dwell under ~5 samples: the rate is a lower bound | shorten `relax_delay`; parity dwells are a few ms, so 3000 us is barely Nyquist |
| Undriven rate falls with averaging and never plateaus | noise crossings, no resolvable telegraph | raise readout SNR; set `average_shots` only on a plateau |
| Two "blobs" from KMeans on a single cloud | KMeans always returns two centroids | trust only splits passing the distance/RMS gate of 2.0 |
| Thermal-mode tail fraction is NaN with a NaN threshold, all scatter labels ground | the tail classifier failed (e.g. sklearn missing) and fell back silently; `thermal_population` is a separate fit | install scikit-learn; check the log |
| Thermal population is NaN | no pi reference (`thermal_pi_calibration` False and no `thermal_e_center`), g-e separation < 1 sigma, or the pi pulse did not move this read (other MUX qubit, off-resonant pi, p ~ 0.5); the WARNING names the cause | rerun with the pi reference on this read's qubit (`qubit_ch`, `f_ge`, `qubit_gain`) |
| Thermal population is finite on a MUX read whose qubit was not on `qubit_ch` | the guard saw that read's cloud move between the undriven and pi runs (readout drift, cross-Kerr/ZZ to the driven qubit) and took the moved cloud as \|e>; the number is meaningless | use only the read of the qubit on `qubit_ch`; rerun with each qubit on `qubit_ch` in turn |
| Moving-average trace longer than the time axis (Modified Ramsey plot error) | averaging window longer than the record **(legacy bug)** | shorter `average_n_shots` |
| Zero-span control D: `both_branches_respond` False, or A/B `null_ok` False | a branch did not raise the level beyond `t_crit` (the Student-t value with the tail of a normal 3 sigma) above drive-off, or a null control moved it; a record too short for batch means gives None with `insufficient_batches`, not False | check `delta_*_z` against `t_crit` / `t_crit_*` and `n_batches`; for longer records pass a larger `min_record_us` to `run_control_suite` (default 200 ms, stitched from `reps_per_chunk` acquisitions; stage 1 overwrites `reps_per_chunk`, so raising it does nothing); see [stage 8](experiments/zero_span_parity.md#stage-8-instrument-controls) |
| Zero-span environment sweep writes negative `pulse_gain` | "power_dB" values written as DAC gain **(legacy bug)** | do not use until fixed |
| Zero-span analysis crashes with `window_us` < 2 us | default `step_us = window_us // 2` is 0 | pass `step_us` |
| A long interleaved loop stopped early | an acquire/hardware error or Ctrl-C in any step aborts the whole loop (a display/fit error does not: it is printed and the loop goes on) | restart; check the last files |

## TWPA scripts

| Symptom | Cause | Fix |
|---|---|---|
| Setting pump channel 1 turned channel 0 off | SynthHD disables RF on both channels on connect | set all channels in one call |
| `twpa set_pump` only turns the pump off | committed with `DISABLE_PUMP = True` | set it to False |
| VISA timeout in the flux sweep | fixed timeout too short for low IF bandwidth / many averages | raise the timeout or IF bandwidth |
| Flat band-mean \|S21\| vs bias, spread < 0.5 dB | DC bias path open or not flux-responsive | check wiring |
| Band-mean gain < 1 dB with pump on | pump off-optimum, under-powered or not reaching the TWPA | re-run the pump sweep |
| Target above 25 uA refused | hard safety limit | intended |
