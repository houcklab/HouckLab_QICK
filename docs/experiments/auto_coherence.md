# auto_coherence

Run function `run_auto_coherence` in `qicklab.runs.auto_coherence` (sweet-spot search in
`qicklab.runs.sweet_spot`). Uses `QubitSpecSliceFF`, `AmplitudeRabiFF`,
`SingleShotProgramFFMUX`, `T1FF`, `T2R`, `T2EMUX`. Regime **B**.

## What it measures

An unattended calibrate-then-measure pipeline for one qubit: optional sweet-spot search
on the charge bias, f_ge re-centring, pi gain from an amplitude Rabi, readout-window
optimisation, pi-gain refinement by single-shot readout contrast, then T1, T2R and T2E
with the calibrated values. It writes everything (every intermediate experiment plus a
summary) into one run folder. It does not change the device file or the session config.

## Pulse sequence

The pipeline chains standard experiments; each stage's sequence is the one on the linked
page, with the stage's own parameters.

```
Stage 1    sweet-spot search      QubitSpecSliceFF (Gauss drive) at each yoko voltage   [skip: skip_sweet_spot_search]
Stage 1.5  f_ge calibration       QubitSpecSliceFF at the current voltage, gain auto-raised  [skip: calibrate_qubit_freq=False]
Stage 2    pi gain                AmplitudeRabiFF register sweep, sigma auto-reduced
Stage 2.5  readout window         SingleShotProgramFFMUX on a readout_length x adc_offset grid  [skip: auto_readout_opt=False]
Stage 3    pi (and pi/2) gain     SingleShotProgramFFMUX gain scan, or error-amplified N-pulse scans
Stage 4    T1                     T1FF            x T1_repetitions
Stage 5    T2 Ramsey              T2R             x T2_repetitions
Stage 6    T2 echo                T2EMUX          x T2E_repetitions
           summary                auto_coherence_summary_<ts>.txt / .json
```

Sequences: spec as [two_tone_spec](two_tone_spec.md#pulse-sequence) (Gaussian drive);
Rabi as [amplitude_rabi](amplitude_rabi.md#pulse-sequence) (`AmplitudeRabiFF`); single
shot as [single_shot](single_shot.md); T1/T2R/T2E as [t1](t1.md), [t2_ramsey](t2_ramsey.md),
[t2_echo](t2_echo.md). All stages read out with the regime-B (single-shot) window, or the
Stage 2.5 winner once it has run.

## How to run

```python
PLAN = [R.auto_coherence()]                               # regime B
PLAN = [R.auto_coherence(skip_sweet_spot_search=True,     # CSTQ03 session settings
                         calibrate_qubit_freq=False,
                         ss_gain_span_frac=0.6, ss_gain_pts=100,
                         auto_readout_opt=True,
                         T1_step=5, T1_repetitions=3,
                         T2_step=0.1, T2_expts=401, T2_repetitions=3,
                         T2E_max_us=500, T2E_repetitions=3)]
```

Any key of the parameter table can be overridden; unspecified keys keep their defaults.
The qubit is `qubit_readout` (see Known issues).

## Parameters

`AUTO_COHERENCE_PARAMS` (library defaults). Keys keep their legacy spelling.

Spectroscopy (Stages 1 and 1.5)

| Key | Default | Units | Meaning |
|---|---|---|---|
| `spec_span` | 1.0 | MHz | +- span around the centre frequency |
| `spec_num_pts` | 101 | - | Points per spectrum |
| `spec_reps` | 10 | shots | Hardware averages |
| `spec_rounds` | 10 | - | Software repeats |
| `spec_relax_delay` | 1500 | us | Wait between shots |
| `spec_sigma` | 2.0 | us | Gaussian drive sigma (`Gauss=True` is hard-coded); a larger sigma gives sharper peaks |
| `spec_gain` | 700 | DAC | Drive gain |
| `spec_qubit_length` | 2.0 | us | Const-drive length; unused because the drive is always Gaussian |

Sweet-spot search (Stage 1)

| Key | Default | Units | Meaning |
|---|---|---|---|
| `skip_sweet_spot_search` | False | bool | True: take f_ge from the device, hold the yoko where it is |
| `ss_search_df_trigger` | 0.50 | MHz | Peak separation that triggers the Strategy-A half-period jump |
| `ss_accept_sep` | 0.08 | MHz | Separation small enough to accept the sweet spot |
| `ss_dV` | 5e-4 | V | Voltage step of the Strategy-B walk |
| `ss_voltage_min` | 0.000 | V | Lower voltage bound |
| `ss_voltage_max` | 0.010 | V | Upper voltage bound |
| `ss_max_tries` | 200 | - | Maximum walk steps |
| `cd_period_mv` | None | mV | Charge-dispersion period; enables Strategy A |

f_ge calibration (Stage 1.5)

| Key | Default | Units | Meaning |
|---|---|---|---|
| `calibrate_qubit_freq` | True | bool | Run Stage 1.5 (no yoko move) |
| `freqcal_auto_gain` | True | bool | Raise the spec gain while the peak is weak |
| `freqcal_min_snr` | 4.0 | - | Peak SNR (median baseline, 1.4826 x MAD noise) below which the gain is raised |
| `freqcal_gain_growth` | 1.8 | - | Gain multiplier per retry |
| `freqcal_max_gain` | 30000 | DAC | Gain cap (under the 32767 ceiling) |
| `freqcal_max_gain_retries` | 5 | - | Maximum retries |

Amplitude Rabi (Stage 2)

| Key | Default | Units | Meaning |
|---|---|---|---|
| `rabi_max_gain` | 12000 | DAC | Top of the gain sweep |
| `rabi_num_steps` | 201 | - | Gain points (step = round(max_gain / (num_steps - 1)) = 60) |
| `rabi_reps` | 15 | shots | Hardware averages |
| `rabi_rounds` | 15 | - | Software repeats |
| `rabi_relax_delay` | 3500 | us | Wait between shots |
| `rabi_sigma` | None | us | Pulse sigma; None = device sigma |
| `rabi_sigma_min` | 0.01 | us | Floor for the automatic sigma reduction |
| `rabi_max_osc_peaks` | 3 | - | More peaks than this: sigma x 0.70 and repeat |
| `rabi_max_sigma_retries` | 10 | - | Maximum sigma reductions |

Single shot (Stage 3)

| Key | Default | Units | Meaning |
|---|---|---|---|
| `ss_shots` | 1000 | shots | Per scan point (Stages 2.5 and 3) |
| `ss_full_shots` | 2000 | shots | Final measurement at the chosen gain |
| `ss_relax_delay` | 3500 | us | Wait between shots |
| `ss_readout_time` | 15 | us | Readout window (replaced by the Stage 2.5 winner) |
| `ss_adc_offset` | 1 | us | ADC trigger offset (replaced by the Stage 2.5 winner) |
| `ss_target_fidelity` | 0.70 | - | Warning threshold only; compared with histogram contrast (see Findings) |
| `ss_gain_pts` | 21 | - | Gain points in the scan |
| `ss_max_scan_expansions` | 2 | - | Re-centre and widen if the best point is on the scan edge |
| `ss_gain_span_growth` | 1.8 | - | Span multiplier per expansion |
| `ss_gain_span_frac` | 0.20 | - | Scan +- this fraction of the Rabi pi gain |

Readout optimisation (Stage 2.5)

| Key | Default | Units | Meaning |
|---|---|---|---|
| `auto_readout_opt` | True | bool | Run Stage 2.5 |
| `readout_length_start` | 5.0 | us | Shortest window |
| `readout_length_stop` | 30.0 | us | Longest window |
| `readout_length_pts` | 6 | - | Window values (5, 10, 15, 20, 25, 30 us) |
| `adc_offset_start` | 0.2 | us | Shortest ADC offset |
| `adc_offset_stop` | 3.0 | us | Longest ADC offset |
| `adc_offset_pts` | 5 | - | Offset values (0.2, 0.9, 1.6, 2.3, 3.0 us) |

Extended pi / pi/2 optimisation (error amplification, Stage 3 alternative)

| Key | Default | Units | Meaning |
|---|---|---|---|
| `extended_pi_pi2_opt` | False | bool | Use error amplification instead of the simple scan |
| `pi_nsteps_list` | [1, 3, 5, 7, 11] | pulses | Odd N pi pulses -> |e> |
| `pi2_nsteps_list` | [2, 6, 10, 14, 22] | pulses | N = 2(2k+1) pi/2 pulses -> |e> |
| `ext_gain_pts` | 51 | - | Gains per N step |
| `ext_pi_gain_span_init` | 0.20 | - | Initial +- span (fraction of the pi gain) |
| `ext_pi2_gain_span_init` | 0.20 | - | Initial +- span for pi/2 |
| `ext_gain_span_shrink` | 0.40 | - | Span multiplier after each N step |

T1 / T2 / T2E (Stages 4-6)

| Key | Default | Units | Meaning |
|---|---|---|---|
| `T1_step` | 40 | us | Wait step |
| `T1_expts` | 60 | - | Points (0 ... 2360 us) |
| `T1_reps`, `T1_rounds` | 20, 20 | - | Averaging |
| `T1_relax_delay` | 3500 | us | |
| `T1_repetitions` | 1 | - | Consecutive T1 records |
| `T2_step` | 0.1 | us | Ramsey wait step |
| `T2_expts` | 201 | - | Points (0 ... 20 us) |
| `T2_reps`, `T2_rounds` | 20, 20 | - | Averaging |
| `T2_relax_delay` | 3500 | us | |
| `T2_repetitions` | 1 | - | |
| `T2_freq_shift` | 0.0 | MHz | Artificial detuning from f_ge |
| `T2E_max_us` | 200 | us | Target maximum echo time (quantised: 198.1 us with n = 1) |
| `T2E_expts` | 201 | - | Points |
| `T2E_reps`, `T2E_rounds` | 25, 25 | - | Averaging |
| `T2E_relax_delay` | 3500 | us | |
| `T2E_num_pi_pulses` | 1 | - | Must be odd and >= 1 (`ValueError` when the Stage 6 T2E program is built; see [t2_echo](t2_echo.md#refocusing-condition)) |
| `T2E_repetitions` | 1 | - | |

## Stages in detail

**Stage 1 - sweet-spot search** (skipped when `skip_sweet_spot_search=True`: f_ge from the
device, voltage held and recorded). One spectrum at the current voltage. Peaks are found on
`|I + iQ|^2` after Savitzky-Golay smoothing (window 5, order 2), prominence >= 0.25 x
(max - min) (`prominence_fraction` 0.25, which works for typical two-tone SNR), minimum distance `round(0.10 MHz / df)` points; up to two peaks. f_ge = the
midpoint of two peaks, or the single peak. Accept immediately if there is one peak or the
separation is below `ss_accept_sep`; without a yoko, use the midpoint. Otherwise:

- *Strategy A* (only if `cd_period_mv` is set and the separation is >= `ss_search_df_trigger`):
  ramp once by +`cd_period_mv`/2 (clipped to the voltage bounds), re-measure, accept if the
  peaks merged. It typically converges in 1-2 spectra.
- *Strategy B* (fallback): walk in steps of `ss_dV`, reversing at the bounds, up to
  `ss_max_tries` spectra, tracking the voltage with the smallest separation; stop on
  acceptance, else return to the best voltage.

The yoko is left at the chosen voltage. The same search is available on its own as
`find_sweet_spot` (used by [modified_ramsey_control](modified_ramsey_control.md)).

**Stage 1.5 - f_ge calibration.** One spectrum at the current voltage (no yoko move).
Peak SNR = (peak - median) / (1.4826 x MAD). If SNR < 4.0 and `freqcal_auto_gain`,
the spec gain is multiplied by 1.8 (capped at 30000) up to 5 times; a warning is logged if
the peak stays weak. f_ge = midpoint of two peaks or the single peak.

**Stage 2 - Rabi pi gain.** `AmplitudeRabiFF`, gain 0 ... 12000 in 201 steps (step 60),
15 x 15 averages, relax 3500 us, no cosine fit. The pi gain is taken from the trace:
project IQ on its principal axis (SVD), normalise to [0, 1], flip so |g> -> 0 (median of
the first max(1, min(5, N // 20)) points decides), smooth (Savitzky-Golay, window <= 11,
order 2), find peaks with prominence 0.20 and height 0.35; pi gain = the **first** peak
(fallback: global maximum). If more than `rabi_max_osc_peaks` (3) peaks are seen, sigma is
multiplied by 0.70 (floor 0.01 us) and the Rabi repeated, up to 10 times; the last attempt
is accepted regardless.

**Stage 2.5 - readout window.** At the Rabi pi gain, one single-shot run (1000 shots) per
(readout_length, adc_offset) pair: 6 x 5 = 30 runs with the defaults. The pair with the
highest contrast replaces `ss_readout_time`/`ss_adc_offset` for Stage 3 and
`readout_length`/`adc_trig_offset`/`length` for Stages 4-6. The resonator tone length is
`max(length, adc_offset + readout_length)`. T1/T2R/T2E integrate the same physical window as
the single-shot runs that chose it (before 2026-10-15 they integrated 1.4x `readout_length`, so
the winner did not transfer: [readout window](../concepts/readout_window.md#history)).

**Stage 3 - pi gain by single shot (default).** Gains `linspace(pi (1 - 0.20), pi (1 + 0.20), 21)`
(unique integers), 1000 shots each; pick the highest contrast. If the best gain is on an
edge, re-centre on it and widen the span x1.8, up to 2 times. Warn if the best contrast is
below 0.70. Final run at the best gain with 2000 shots (contrast, threshold, angle go to
the summary). `pi2_gain = pi_gain // 2`.

**Stage 3 - error-amplified pi / pi/2 (`extended_pi_pi2_opt=True`).** For each N in
`pi_nsteps_list` (odd N: N pi pulses end in |e>), scan 51 gains around the current centre
with `number_of_pulses = N`; the best gain becomes the next centre and the span shrinks
x0.40 (initial +-20 %). Then the same for pi/2 starting at `pi_gain // 2` with
`pi2_nsteps_list` (N = 2(2k+1) pi/2 pulses also end in |e>). Final N = 1 single-shot
verification at the pi gain with 2000 shots.

**Stages 4-6.** T1, T2R and T2E with the calibrated f_ge, pi/pi2 gains and sigma, each
followed by a 5 s pause and `soc.reset_gens()`. The T2E step is quantised as on
[t2_echo](t2_echo.md#step-quantisation) (0.00232515 us x (n + 1) x int_steps); if
`int_steps` is 0 it is forced to 1. T2E uses f_ge without detuning.

## Outputs

```
<data_root>/Q{qubit_readout}/AutoCoherence/run_<YYYYMMDD_HHMMSS>/
    auto-Spec/            Stage 1 and 1.5 spectra (raw h5 + json; no peak keys, no PNG)
    auto-AmplitudeRabi/   Stage 2 Rabi records (one per sigma attempt; PNG without fit)
    auto-ReadoutOpt/      Stage 2.5 single-shot records
    auto-SingleShot/      Stage 3 scan + final records
    auto-PiOpt/           extended mode only
    auto-Pi2Opt/          extended mode only
    auto-T1/  auto-T2/  auto-T2E/
    auto_coherence_summary_<YYYYMMDD_HHMMSS>.txt
    auto_coherence_summary_<YYYYMMDD_HHMMSS>.json
```

Inside each `auto-*` folder the usual `<path>_<YYYY_MM_DD>/<path>_<timestamp>_data.*`
layout applies. The summary holds the calibrated values (`qubit_frequency`, `pi_gain`,
`pi2_gain`, `rabi_sigma`, `flattop_length`, `fidelity`, `ss_threshold`, `ss_angle`,
`sweet_spot_voltage`), every parameter used, and the full stage log. The step returns the
same values plus `auto_folder` and `summary_file`.

The summary is written after the calibration block, after each of T1, T2 and T2E, and once
more on every exit, including a failure or Ctrl-C, so a crash never loses the calibration.
`stage_reached` (json key; `Stage reached:` line in the txt) names the last completed stage
(`start`, `sweet_spot_search`, `calibrate_qubit_freq`, `amplitude_rabi`,
`optimize_readout`, `singleshot_optimize`, `T1`, `T2`, `T2E`, `complete`) and `error` holds
the `repr` of the exception that aborted the run (else `null`). Before Stage 3 finishes,
`calibration` holds only what is known so far (`pi_gain` is then the Rabi estimate). The
readout window chosen by Stage 2.5 is in the parameters section (`ss_readout_time`,
`ss_adc_offset`). A display (fit/plot) failure inside a stage does not stop the run: the
record is saved and a `display failed (record saved)` line is added to the log.

T1/T2/T2E fit values are **not** in the summary. The `auto-T1` and `auto-T2E` h5 records hold
their fits (`t1_fit_*`, `t2e_fit_*`, see [t1](t1.md#outputs)); refit the `auto-T2` records. Calibrated values are not written into the
device file; copy them by hand (`Qubit(freq=..., gain=..., pi2_gain=..., sigma=...)`).

## Analysis

Stage logic is described above. Each stage's records can be re-analysed with the
standalone page's analysis. The "fidelity" used throughout is the value returned by the
single-shot histogram analysis (see Findings).

## Findings & notes

- Contract: the caller's config and device parameters are never mutated (all stage configs
  are copies), and the experiment classes are used unmodified.
- The legacy module docstring described "300 shots during scan, 500 final", an
  `AutoCoherence_<timestamp>` folder and "sigma is halved". Current behaviour, documented
  above: 1000 / 2000 shots, `AutoCoherence/run_<timestamp>/`, sigma x 0.70.
- `ExperimentClass` concatenates `outerFolder + path` with no separator, so the run folder
  must end with "/"; the step appends it.
- The "fidelity" from the single-shot histogram is the readout **contrast**
  C = max|CDF_g - CDF_e| = P(g|g) + P(e|e) - 1, not the assignment fidelity
  (1 + C)/2. `ss_target_fidelity = 0.70` is therefore a contrast threshold. See
  [single_shot](single_shot.md) and
  [concepts/iq_conventions.md](../concepts/iq_conventions.md).
- CSTQ03 session settings (legacy runner, 2026-10-01 cooldown): `skip_sweet_spot_search`
  True (use the device f_ge, hold the current voltage), `calibrate_qubit_freq` False,
  `ss_gain_span_frac` 0.6, `ss_gain_pts` 100, `auto_readout_opt` True, `T1_step` 5,
  `T1_repetitions` 3, `T2_step` 0.1, `T2_expts` 401, `T2_repetitions` 3, `T2E_max_us` 500,
  `T2E_repetitions` 3.
- The CSTQ03 runner's commented example sets `cd_period_mv = 4.37` mV, the same period
  quoted there for modified_ramsey_control (S(V) period 4.37 mV, cd_max 0.682 MHz, from an
  independent calibration; device, qubit and date not recorded). Strategy A needs it.

## Known issues

- The qubit is `qubit_readout` for everything: drive frequency, gain, sigma and flat-top
  are read from the device entry of `qubit_readout`; `qubit_pulse` is ignored.
- Stages 1/1.5 find peaks on `|I + iQ|^2`, the method that
  [two_tone_spec](two_tone_spec.md#findings--notes) replaced with the IQ projection
  because it misses features lying in one quadrature.
- `ss_accept_sep` (0.08 MHz) is below the peak finder's minimum separation (~0.10 MHz), so
  a two-peak spectrum can never be accepted; acceptance happens only when a single peak is
  found.
- The spectrum grid is asymmetric by one step (last point `centre + span - step`).
- Strategy A drops the starting voltage from the best-voltage tracking: if the half-period
  jump makes things worse, the search cannot return to the start.
- Stage 2 always uses the register-swept `AmplitudeRabiFF`, even when the qubit has a
  `flattop_length` (the flat part then does not follow the gain; see
  [amplitude_rabi](amplitude_rabi.md#findings--notes)).
- Reducing sigma at a fixed `rabi_max_gain` can push the pi gain past the sweep; this is
  not checked (fallback: global maximum).
- In extended mode the returned gain is the one with the highest contrast over all N steps,
  not the one from the largest N.
- `T2E_num_pi_pulses` must be odd and >= 1, but this is checked only when Stage 6 builds
  its first `T2EProgram` (`ValueError`; see [t2_echo](t2_echo.md#refocusing-condition)).
  With an even value the run therefore aborts late: the whole calibration and the T1 and
  T2R stages have already run and saved, the summary is written with
  `stage_reached = "T2"` and `error = ValueError(...)`, and an empty dated `auto-T2E` folder
  is left behind. The one exception is `-1`, which fails slightly earlier, at the start of
  Stage 6, with a `ZeroDivisionError` from the step computation (`num_pi_pulses + 1 = 0`);
  every other value < 1 reaches the `ValueError`.
- The yoko is left at the Stage 1 voltage.
- The summary timestamp format (`%Y%m%d_%H%M%S`) differs from the experiment files
  (`%Y_%m_%d_%H_%M_%S`).
