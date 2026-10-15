# Bring-up workflow: characterising a new chip

The order in which a fresh device is characterised, from an amplifier that works to the
specialised charge-parity measurements. Each stage lists the step(s) to run, the knobs that
matter, what a good result looks like (with CSTQ03 numbers as examples) and what to write back
into the device file. Session mechanics are in [running_a_session.md](running_a_session.md);
device fields in [adding_a_device.md](adding_a_device.md).

```
0 device file + dry run
1 TWPA bias, then pump
2 transmission          -> Readout.freq, Readout.gain, cavity_min
3 two-tone spec         -> Qubit.freq (Qubit.spec_gain)
4 amplitude Rabi        -> Qubit.gain (pi), Qubit.sigma
5 single shot + optimise-> Readout.gain/freq, Qubit.pi2_gain, readout windows
6 coherence benchmark   -> Qubit.t1_us; T1, T2R, T2E recorded for the device
7 specialised           -> ParityParams, bias point; charge dispersion, Modified Ramsey,
                           zero span, undriven single shot
```

Stage 6 is not optional: T1, T2R and T2E are measured on every new device as the standard
benchmark before any specialised measurement.

## 0. Device file and dry run

Create `devices/<NAME>.py` with design values (resonator and qubit frequencies from design or a
VNA scan, placeholder gains). Run `DEVICE.validate()` and a dry run of the first plan. Fix
anything that fails before cooling down.

## 1. TWPA

Bias first, pump second. Scripts in `qicklab.twpa` are standalone and ask you to type `yes`
before touching an instrument.

| order | script | knobs | good |
|---|---|---|---|
| 1 | `python -m qicklab.twpa.set_bias` | target current; ramp at most 300 nA/s from 0, pump OFF | reaches target without trapping flux |
| 2 | `python -m qicklab.twpa.flux_sweep` (calibration, once per cooldown) | +/-25 uA, pump off | transmission enhancement near about 11 uA, strong suppression near about 25 uA. A spread under 0.5 dB means the DC path is open |
| 3 | `python -m qicklab.twpa.set_pump` | `(freq_GHz, power_dBm, channel)` from `setup.twpa` | pump on, script leaves the port open on purpose (closing would switch RF off) |
| 4 | `python -m qicklab.twpa.pump_sweep` (if no operating point yet) | pump freq x power grid | best band-mean \|S21\|; subtract an unpumped reference offline for gain |
| 5 | `python -m qicklab.twpa.gain_compare` | pump off/on interleaved | broadband positive gain, often about 15-20 dB with modest ripple. Band-mean gain under 1 dB: pump off-optimum, under-powered or not reaching the TWPA |

Keep the PNA-X at -25 dBm so the probe does not saturate the TWPA. Datasheet limits: nominal
bias about 11 uA; do not sweep well above that in normal operation (flux trapping, reduced
performance); 25 uA is for one-off calibration.

CSTQ03 (2026-10 cooldown): pump ch1 10.7165 GHz at -5.5 dBm. Bias history and open questions
are in [devices/CSTQ03.md](devices/CSTQ03.md#twpa). Details of the scripts:
[hardware.md](hardware.md).

## 2. Transmission: find the resonator

Pages: [transmission_fit](experiments/transmission_fit.md),
[transmission_sweep](experiments/transmission_sweep.md).
Steps: `transmission_fit` (hanger fit, writes the fitted curve's minimum into the session config) or
`transmission_sweep` (takes the min or max point). `constant_tone` plays a CW readout tone for
looking at the line on a spectrum analyser.

| knob | where | CSTQ03 value | notes |
|---|---|---|---|
| span | `transmission` group `span` | 5 MHz (+/-) | the sweep is `pulse_freq +/- span`; widen for a first search |
| points | `transmission` group `num_points` | 201 | |
| averaging | `reps`, `rounds` | 20 x 20 | see [concepts/averaging.md](concepts/averaging.md); prefer `reps` (hardware averaging in one program) over `rounds` (one program per round, each a chance to hit the stale-shot-counter race). 400 x 1 averages the same shots as 20 x 20 with 20x fewer program starts |
| readout gain | `Readout.gain` | 1000-4500 across Q1-Q6 | |
| dip or peak | `Device.cavity_min` | `True` (dip) | decides which extremum `transmission_sweep` tracks |

Good: a clear dip (for `cavity_min=True`) well inside the span, and a hanger fit that converges
(start values from the trace: f0 at the raw minimum, Qtot from the span, asymmetry 0; Qint =
\|1/(1/Qtot - 1/Qext)\|).

Readout gain: raise it until the response is clear, and stop below where it was judged
"too much". CSTQ03 examples (runner notes, undated): Q4 at 7288.48 MHz, 400 good and 420 too much;
with the directional coupler 1400 good and 1500 maybe too much; Q2 coarsely tuned to 4000 with
"behaviour at 4500". The gain is refined later by `readout_optimize` (stage 5).

Write back: `Readout.freq` from the calibration line `transmission_fit` prints. The in-session
`pulse_freq` carry-over is lost at the next switch to the single-shot regime, so the device file
must hold it. The kappa it prints is kappa_tot/2pi in MHz (total linewidth; kappa_ext/2pi is printed too):
use it for `Readout.kappa_mhz`, and note that `reset_readout_relax_delay` >= 6/kappa needs the angular
kappa, i.e. 6/(2 pi x kappa_tot/2pi) (0.19 MHz -> 5 us).

## 3. Two-tone spectroscopy: find the qubit

Pages: [two_tone_spec](experiments/two_tone_spec.md),
[spec_gain_length_sweep](experiments/spec_gain_length_sweep.md).
Step: `two_tone_spec` (QubitSpecSliceFF). The `spec` group is shared with every other
spectroscopy-type step and with the regime-A base config.

| knob | `spec` group key | CSTQ03 value | notes |
|---|---|---|---|
| span | `SpecSpan` | 10 MHz (+/-) | centred on `Qubit.freq` |
| points | `SpecNumPoints` | 201 | |
| drive gain | `gain` | 800 | the gain `two_tone_spec` actually plays (DAC units) |
| base-config spec gain | `qubit_gain` | 1000 | used by `trans_qubit_spec`; regime-A `qubit_gain` means spec gain, not pi gain |
| drive shape | `Gauss`, `sigma`, `qubit_length` | flat 50 us (`Gauss` False) | long weak drive = narrow line; `qubit_length` ignored when `Gauss` is True |
| averaging | `reps`, `rounds`, `relax_delay` | 20, 10, 2500 us | |
| peak finding | `min_sep_MHz` | 0.2 MHz | minimum separation for two peaks (doublets) |

Good: after projection onto the principal IQ axis, a baseline near 0 and the qubit as a positive
bump. AutoCoherence's acceptance criterion is a useful number: peak SNR >= 4, where noise is
1.4826 x MAD about the median baseline. A charge-sensitive qubit away from its sweet spot shows a
doublet; the CSTQ03 runner carries a maximum splitting `cd_max_mhz` of 0.682 MHz (independent
calibration, qubit and date not recorded; see [devices/CSTQ03.md](devices/CSTQ03.md#doublet-measurements)).

Why projection and not magnitude ([concepts/iq_conventions.md](concepts/iq_conventions.md)):
Q6 2026-06-02 (device not recorded), the real feature sat in I near 3054 MHz
and `|I+iQ|` picked noise spikes at 3038/3069 MHz; CSTQ03 Q2 2026-09-02 12:03, a broad line near
3753 MHz was flipped into a dip by a whole-trace baseline. Centre the span on the expected line
so the outer 15% on each side is baseline.

If nothing is seen:

1. Check transmission first: no readout, no spectroscopy.
2. Widen `SpecSpan`.
3. Run `spec_gain_length_sweep`: every `qubit_length` in `sweep_lengths` (CSTQ03: 10 to 100 us in
   10 us steps) times every gain in `sweep_gains` (200 to 5000 in steps of 100). That is 490
   spectra; trim the lists first.
4. CSTQ03 notes (undated): spec gain 750 works for Q5; flat length 9.5 us worked; "10 was the best
   for Q4".

`trans_qubit_spec` repeats spectroscopy `coherence.repetitions` times (1000 in the CSTQ03
session); set that group value deliberately before running it.

Write back: `Qubit.freq`; optionally `Qubit.spec_gain`.

## 4. Amplitude Rabi: pi gain

Page: [amplitude_rabi](experiments/amplitude_rabi.md).
Step: `amplitude_rabi` (AmplitudeRabiFF; AmplitudeRabiFF_N, a software sweep, when
`flattop_length` is set).

| knob | CSTQ03 value | notes |
|---|---|---|
| `max_gain` | 10000 | sweep runs 0..max_gain. Raise it if no oscillation is visible; also compare with the transmission data |
| `number_of_steps` | 101 | |
| `reps`, `rounds`, `relax_delay` | 10, 10, 3000 us | relax >= 3-5 x T1 once T1 is known |
| `Qubit.sigma` | 0.02-0.6 us across Q1-Q6 | shorter sigma needs more gain |

Good: at least about 0.75-1 period inside the sweep (fewer is flagged, bit 4; see the
Analysis section of [amplitude_rabi](experiments/amplitude_rabi.md#analysis)), with the pi point
well inside. CSTQ03 pi gains are 3800-5000 at sigma 0.02-0.6 us. A failed fit
returns a runaway period (flags 2 and 4) and the pi marker disappears off the plot. AutoCoherence's Rabi stage
uses `rabi_max_gain` 12000, 201 steps, and shrinks sigma by 0.70 when it sees more than 3
oscillation peaks.

Write back: `Qubit.gain`, and `Qubit.sigma` if changed. `pi2_gain` defaults to `gain // 2` until
stage 5.

Known: the gain step is `int(max_gain / number_of_steps)`, so 10000/101 gives step 99 and the sweep
ends at 9900; the flat-top path forces `relax_delay` 8000 us.

## 5. Single shot and optimisation

Steps (regime B, single-shot window): [single_shot](experiments/single_shot.md),
[readout_optimize](experiments/readout_optimize.md),
[qubit_optimize](experiments/qubit_optimize.md).

| step | knobs (CSTQ03 values) | result |
|---|---|---|
| `single_shot` | `single_shot` group: 1000 shots, relax 6000 us, `number_of_pulses` 1; window `Device.ss_window` 15 us / 0.3 us | g and e blobs, threshold, rotation angle, contrast |
| `readout_optimize` | gain 3000..3600 in 7 points; frequency span 0.1 MHz (centred on `Readout.freq`) in 21 points | best readout gain and frequency |
| `qubit_optimize` | pi gain +/-500 in 21 points; frequency +/-2 MHz in 21 points; `number_of_pulses` 1 | best pi gain and drive frequency |

pi/2: set the gain to half the pi gain and optimise with `number_of_pulses=2` (two pi/2 pulses make
a pi). Write the result to `Qubit.pi2_gain`.

Good: the legacy printout called "Fidelity" is the contrast C = P(g|g) + P(e|e) - 1; the
assignment fidelity is (1 + C)/2. Warning thresholds used by the analysis: contrast below 0.3,
analog SNR below 1, fewer than 500 labelled shots per class. AutoCoherence targets 0.70 (warning
only). CSTQ03 Q2 on 2026-08-04 had analog SNR of about 0.77-1.05 across calibrations (0.91 in
the four-arm diagnostic), mostly below 1; that readout SNR is
what limited the parity analysis, so it is worth spending time here before stage 7.

Readout window: integrate longer for SNR until the window approaches T1. AutoCoherence can scan
it (integration 5-30 us in 6 points, ADC offset 0.2-3 us in 5 points) and adopts the winner.
CSTQ03 notes: Q2 readout length 5 us; single-shot Q1 15 us, Q5 5 us. Per-qubit windows go in
`Readout.window` / `Readout.ss_window`.

Known: `qubit_optimize` centres its frequency scan on the device-file value, not on a frequency
measured earlier in the session.

## 6. Coherence benchmark: T1, T2R, T2E

Run on every new device, before specialised work, and record the numbers in the device record.
Pages: [t1](experiments/t1.md), [t2_ramsey](experiments/t2_ramsey.md),
[t2_echo](experiments/t2_echo.md), [auto_coherence](experiments/auto_coherence.md),
[interleaved_coherence](experiments/interleaved_coherence.md).

| step | group | CSTQ03 session values | notes |
|---|---|---|---|
| `t1` | `coherence` | `T1_step` 5 us x 100 points, reps 20 x rounds 20, relax 3000 us | span should cover several T1 |
| `t2_ramsey` | `coherence` | `T2_step` 0.1 us x 100 points, `freq_shift` 0 | detune with `freq_shift` to see fringes |
| `t2_echo` | `echo` | `T2_max_us` 20, 121 points, 25 x 25, relax 500 us, `num_pi_pulses` 1 | `num_pi_pulses` must be odd and >= 1 (`ValueError` otherwise; see [t2_echo](experiments/t2_echo.md#refocusing-condition)) |

`repetitions` in the `coherence` and `echo` groups repeat the whole measurement (1000 and 3000 in
the CSTQ03 session, meant for long unattended runs). Use 1-3 for a benchmark.

Rules of thumb: `relax_delay` >= 3-5 x T1 (CSTQ03 Q2 T1 was about 50 us on 2026-08-04, so 250 us
is 5 x T1); the T1 sweep should reach several T1.

Alternative: `auto_coherence` runs Rabi, readout and single-shot optimisation, then T1, T2 and T2E,
and writes a summary json with every calibrated value. CSTQ03 settings: `skip_sweet_spot_search`
True (use the device frequency and hold the bias), `calibrate_qubit_freq` False, `ss_gain_span_frac`
0.6, `ss_gain_pts` 100, `auto_readout_opt` True, `T1_step` 5 us, `T2_step` 0.1 us, `T2_expts` 401,
`T2E_max_us` 500, 3 repetitions of each.

Outputs: the fitted T1/T2 values are in the png and console only (not in the h5) for `t1`,
`t2_ramsey` and `t2_echo`; the AutoCoherence summary json does hold them. Write `Qubit.t1_us`.

For drift: `interleaved_coherence` cycles undriven single shot -> T1 -> T2R -> T2E under the
same conditions.

## 7. Specialised measurements

Prerequisites for all of them: stages 2-6 done on this qubit, the device file current.

### Charge dispersion and bias point

- [`charge_sweep`](experiments/charge_sweep.md): two-tone spectroscopy at each bias in the `charge` group range
  (`voltage_start`, `voltage_end` exclusive, `voltage_step`, V). Gives the doublet splitting vs
  bias. Fit S(V) = cd_max \|cos(2 pi (V - V0)/T)\| for `ParityParams.cd_max_mhz` and `cd_period_mv`.
  CSTQ03 runner values: 0.682 MHz and 4.37 mV (qubit and date not recorded). Choose the step well below the period: the session default
  0.005 V (5 mV) is longer than one 4.37 mV period and cannot resolve it.
- `charge_transmission_sweep`: resonator transmission at each bias (heatmap plus tracked
  frequency). Returns the bias to the start value on error or Ctrl-C.
- `two_tone_charge_dispersion_quasicw`, `charge_dispersion_quasicw`: quasi-CW telegraph at a
  chosen doublet peak.
- `charge_dispersion_ramsey`: needs tuned pi and pi/2, and a frequency at a charge-dispersion
  extremum. It currently fails with `KeyError: 'df'` on the CSTQ03 parameter set.
- Bias: record the chosen point in `Qubit.bias_v`. CSTQ03 note: 0.0059 V gave good T2R.

### Modified Ramsey (charge-parity rate)

Before the first record ([experiments/modified_ramsey.md](experiments/modified_ramsey.md)):

1. Measure the doublet independently and set `ParityParams.df_mhz` and `f_upper_mhz` (the upper
   branch, not the centre). The step does not search for it and never moves the bias.
2. Check df against sigma: df < 1/(8 sigma) without echo, 1/(16 sigma) with echo (sigma 0.1 us:
   1.25 MHz; 0.22 us: 0.57 MHz). Pick tau = k/(2 df) with the smallest odd k that keeps the
   echo_null control feasible (tau > 8 sigma). See the CSTQ03 df = 2.7 MHz example in
   [devices/CSTQ03.md](devices/CSTQ03.md#modified-ramsey-at-df--27-mhz-timing-choice).
3. Validate active reset with [`active_reset_verify`](experiments/active_reset_verify.md). Working reset: prep `|e>` with reset ON gives
   P(g) >= 0.9 x P(g) of prep `|g>` with reset ON, and recovery P(g | e, ON) - P(g | e, OFF) >= 0.3,
   flat across repeated reads. `reset_readout_relax_delay` >= about 6/kappa with kappa the
   angular linewidth, i.e. 6/(2 pi x kappa_tot/2pi) using the kappa_tot/2pi the transmission fit
   prints (0.19 MHz -> 5 us; 5 us on TATQ01/BFE; CSTQ03 kappa unmeasured).
4. Set `mr_relax_delay` to about 5 x T1 without active reset. The CSTQ03 Q2 2026-08-04 diagnostic
   showed incomplete inter-shot reset faking a kHz parity rate at relax 0.
5. Take many dwells (CSTQ03: 100k shots at 250 us relax, about 10 500 dwells), keep
   `hmm_min_emission_snr` at 0.7, and interleave the `flip_final_pi2` and `echo_null` controls.
   Good: flip preserves the telegraph and inverts occupancy, echo suppresses it, and HMM, ACF and
   PSD rates agree within 3x.

`modified_ramsey_control` repeats the measurement at the charge sweet spot as a null.

### Zero-span parity

`zero_span_parity` ([experiments/zero_span_parity.md](experiments/zero_span_parity.md)): strobe
mode (one sample per rep) or decimated mode (continuous capture). Run the modulation check first:
it is the pipeline-sanity gate. Hard limits are checked at construction (sample period >= ADC
offset + read length + 1 us; at most 65535 cycles per period or capture; reps per chunk <= 16384;
decimated samples <= 1024).

### Undriven single shot

`undriven_single_shot` ([experiments/undriven_single_shot.md](experiments/undriven_single_shot.md)):
no qubit pulse; looks for a second IQ blob and its switching in time. Parity dwells are a few ms,
so `relax_delay` 3000 us barely samples them; CSTQ03 runs 300 us and 1 000 000 shots. Set
`average_shots` on the plateau of the rate-vs-averaging panel.
