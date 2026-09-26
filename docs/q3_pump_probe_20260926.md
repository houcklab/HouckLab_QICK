# q3 pump–probe notebook: 26 September 2026

Measurement-PC workflow: pull `tls-spectroscopy`, run the named Python module,
then inspect NAS results before selecting another experiment. No hardware is
accessed by `--plan`. Do not run another acquisition concurrently.

NAS root: `Z:/FluxTeam/Data/FTT02_AlOxJJ_2026_08_28/RFSOC`
(Mac mount: `/Volumes/ourphoton/FluxTeam/Data/FTT02_AlOxJJ_2026_08_28/RFSOC`).

## Baseline findings

The full-band localizer found strong loss near 4.098 GHz. The subsequent
eight-delay measurement put the feature nearer 4.106 GHz, but changed both the
delay protocol and program chunking. Those measurements alone did not establish
TLS motion.

The unchunked A–B–A comparison used a shared calibration, 2-us reference holds,
40-us returns, and A=[25,60,100] versus B=[4,8,25] us survival increments.
Session `q3/q3_pump_probe_protocol_check_20260926T200743Z_138f511c`
completed at commit `3d4fc6b`. In the common 25-us observable, B was displaced
by about +2.1 MHz relative to the average A curve; IQ centroids showed the same
effect. This implicated protocol dependence without identifying a mechanism.

The follow-up session
`q3/q3_pump_probe_history_check_20260926T201656Z_1ae78613` completed all eight
arms at commit `8852cad`:
A10, B10, A500, B500, B500, A500, B10, A10. The numbers are park idle in us
after readout and feedback reset. Each arm acquired 91 frequencies from
4.080–4.125 GHz and 500 shots per condition, with one shared calibration.

Descriptive translations of B against A, using the shared normalized 25-us
population and linear interpolation over 4092–4114 MHz:

| Comparison | 10-us idle | 500-us idle |
| --- | ---: | ---: |
| First adjacent A/B pair | +2.360 MHz | −0.240 MHz |
| Final adjacent A/B pair | +1.714 MHz | +0.718 MHz |
| Repeat-averaged curves | +1.862 MHz | +0.242 MHz |
| Repeat-averaged IQ projections | +1.778 MHz | +0.249 MHz |

These are shape-alignment estimates, not independently calibrated TLS
frequencies or confidence intervals. A500 also drifted about −1.28 MHz between
its two scans. Median classified P0 was 0.276–0.338 at 10-us idle and
0.116–0.140 at 500-us idle; median P1−P0 improved from 0.316–0.356 to
0.414–0.456. These reference signals include assignment/preparation effects and
must not be interpreted directly as thermal populations.

The longer pause substantially reduces the protocol mismatch. It does not
distinguish flux memory, bath dynamics, reset effects, or other causes, and does
not remove all drift. The next experiment therefore sweeps a small region and
uses nearby-in-time controls instead of assuming one fixed TLS frequency.

## First direct-microwave pilot

```powershell
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbePilot --run
```

Seven target frequencies: 4.094, 4.098, 4.100, 4.102, 4.104, 4.106, 4.110 GHz.
At each target, pump and probe use the same flux excursion. The microwave tone
is 15 us at gain 3000, with controls: zero-gain sham, nominal resonance from the
frozen flux model, and ±20 MHz detunings. Each condition has ground/excited
preparation and 2/10-us probe holds (an 8-us increment). The ground preparation
plays a zero-gain pi-length waveform to preserve timing.

There are three randomized repeats of 200 shots: 336 blocks, 67,200 recorded
probe shots. The four microwave controls for a given frequency/state/hold are
adjacent. Native reset runs before the pump and again after it. All conditions
retain the pinned native correction, 0.5-us arrival, 40-us complete pre-readout
return, and 500-us idle after the probe readout. Unlike the preceding scan,
the next pre-pump reset follows that idle. One calibration is shared.

Zero **additional** recovery does not mean zero pump-to-probe time: the
40-us return, readout, variable feedback reset, and probe preparation intervene.
After each reset, a 20-us reference-time guard from the final readout endpoint
includes the 10-us feedback wait and 10-us instruction headroom. This is needed
because QICK `wait_all` does not advance its pulse reference time
([QICK timing documentation](https://docs.qick.dev/latest/_autosummary/qick.asm_v1.html#qick.asm_v1.QickProgram.sync_all)).
The actual guard is recorded in per-block telemetry; total reset latency is not.
This pilot is not sensitive to every
possible short-lived TLS response and does not test persistent displacement.

Outputs are under `q3/q3_pump_probe_pilot_<UTC>_<id>/`: `manifest.json`,
`config.json`, `summary.csv`, and raw IQ `point_*.npz`. Completed blocks are
checkpointed and acquisition stops on error. Do not resume a partial session
by mixing a new calibration into it.

The first pilot session, `q3_pump_probe_pilot_20260926T203812Z_94120f74`,
stopped before block 8 after a Windows `WinError 5` during manifest replacement.
Blocks 0–7 have intact 200-shot raw IQ files and CSV rows. The subsequent error
checkpoint succeeded, indicating the denial was intermittent. Checkpoint
replacement now retries access conflicts up to eight attempts over 3.55 seconds;
it does not repeat acquisition or fall back to truncating the manifest. A
persistent denial still stops the run and retains `.pending` for recovery.
Restart this short partial pilot as a fresh session and calibration.

Evaluate excited survival together with ground-probe excitation, reference
contrast, both detuned controls, repeat consistency, and raw IQ changes. Any
effect remains a pump-dependent response until follow-up controls establish its
origin. A persistent-spectrum test needs a separate pump-once/observe protocol.

## Completed pilot and pump-frequency follow-up

Session `q3_pump_probe_pilot_20260926T204545Z_4de3530d` completed all 336
blocks at commit `6731141`, from 20:45:50 to 20:48:00 UTC. The summary has
67,200 probe shots and every manifest block reports 200 records, a 40-us complete
return, and a 20-us reset reference guard. Each condition pools three independent
acquisition blocks of 200 shots.

The strongest 10-us loss lies at model coordinates 4.104 and 4.106 GHz. There
is no convincing selective survival improvement from the nominally resonant
pump at this dose:

| Target (GHz) | Excited-prepared P10: sham | near | −20 MHz | +20 MHz |
| --- | ---: | ---: | ---: | ---: |
| 4.100 | .4333 | .5117 | .4983 | .5183 |
| 4.104 | .3650 | .3933 | .3800 | .3567 |
| 4.106 | .2917 | .3250 | .3283 | .3467 |

At 4.104/4.106 GHz the near-minus-sham differences are +.0283 ± .0280 and
+.0333 ± .0266 (one binomial standard error). At 4.100 GHz, the apparent
improvement also occurs with detuned pumps, so it is not selective evidence.

At 4.098 GHz, ground-prepared P10 is .2483 near versus .1817 sham: +.0667
± .0236, with repeat differences +.035, +.075, +.090. The six raw IQ blocks
were reclassified using the saved payload calibration and exactly reproduce
the stored counts. This is a candidate extra-excitation signal, not a confirmed
upward-transition rate: short-reference P_g also differs, several conditions
were inspected, and drift is not included in these errors. Across frequencies,
the mean near-minus-sham ground P10 difference grows from −.0071 to +.0043 to
+.0707 over the three repeats. Reference signals also drift, so pooling shots
alone overstates precision for physical conclusions.

The follow-up keeps gain 3000 and 15-us duration and maps pump frequency:

```powershell
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbePilot --run --frequency-check
```

Probe targets are 4.098 (candidate extra excitation), 4.104/4.106 (strong loss),
and 4.110 GHz (flank). For every target/state/hold, a sham precedes and follows
a randomized sweep of pump detunings −20, −10, −8, −6, −4, −2, 0, +2, +4,
+6, +8, +10, +20 MHz. The two shams provide a check on drift during the sweep.
There are four repeats of 400 shots per block, 960 blocks total. Preparation,
holds, return timing, resets and idle timing remain those of the pilot.
Outputs use `q3/q3_pump_probe_frequency_check_<UTC>_<id>/`; `control_position`
identifies the bracketing references in the CSV and manifest. Check these
references and repeat consistency before interpreting any narrow response.

## Frequency-check results and locally bracketed confirmation

Session `q3_pump_probe_frequency_check_20260926T205654Z_d0b21866` completed
all 960 blocks (384,000 shots) at commit `267986e`, from 20:56:58 to 21:06:44
UTC. CSV populations/counts match the manifest; every block reports 400 records.
The pulse/reset telemetry retains the 40-us return and 20-us reset guard.

For each target/repeat/preparation/hold, interpolate the two sham populations
linearly in acquisition start time and subtract that estimate from each pump
population. This removes an assumed linear trend, not arbitrary fluctuations
or pump carryover. The 64 sweeps span a median 8.52 seconds between their sham
starts (maximum 10.83 seconds). The median absolute before/after sham change is
0.045; the maximum is 0.220. Consequently binomial shot errors alone substantially
understate uncertainty in a repeatable physical effect. All detunings within a
sweep share the same references and their errors are correlated.

Selected exploratory contrasts (classified population, not calibrated thermal
population):

| Probe target | Pump detuning | Preparation / hold | Mean pump minus interpolated sham | Individual repeats |
| --- | ---: | --- | ---: | --- |
| 4.098 GHz | +8 MHz | g / 10 us | +0.0764 | +0.0206, +0.1167, +0.1596, +0.0086 |
| 4.098 GHz | +8 MHz | g / 2 us | +0.0445 | −0.0223, +0.0936, +0.0423, +0.0643 |
| 4.110 GHz | +8 MHz | g / 2 us | +0.0564 | +0.0489, +0.0210, +0.0092, +0.1466 |
| 4.110 GHz | +8 MHz | e / 2 us | −0.0646 | −0.0367, −0.0113, −0.0689, −0.1416 |

For the first row the binomial standard error of the mean is 0.0135, while the
standard error estimated from four repeat contrasts is 0.0368. These exploratory
comparisons were selected after examining many conditions; they are not a
confirmatory significance test. At 4.098 GHz the near-pump ground/10-us contrast
is only +0.0129, with repeat standard error 0.0418, so the earlier near-pump
candidate did not reproduce as a stable effect. There is still no clear,
repeatable selective improvement of excited survival at 4.104/4.106 GHz.

All twelve raw IQ files for the 4.098-GHz ground/10-us +8-MHz pump and its
bracketing shams were reclassified with this run's saved payload classifier;
they reproduce the CSV counts exactly. Unthresholded IQ projections also show
large repeat variation. At 4.110 GHz, the +8-MHz short-reference contrast change
warns against interpreting the signal as relaxation alone. No TLS suppression,
frequency displacement, or upward-transition rate is established.

The next stage concentrates on these candidates and measures a zero-drive null:

```powershell
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbePilot --run --confirmation-check
```

At each of 4.098 and 4.110 GHz, collect ground/excited preparations and 2/10-us
holds. Randomize four tests: pump at 0, +8, or −20 MHz detuning, and a zero-gain
null at +8 MHz. **Every individual test** gets its own three-block sequence:
sham-before, test, sham-after. All three use the same programmed tone frequency,
flux, preparation, and hold. The null test and both surrounding shams all take
the existing `no_pump` path. `test_condition` identifies the candidate/null and
`comparison_id` identifies its triplet in both CSV and manifest.

Eight repeats of 400 shots produce 768 blocks: 192 driven, 576 zero-gain,
307,200 total probe shots. Gain 3000, 15-us pump duration, idle, reset and pulse
timing remain unchanged. This reduces the separation of each test from its
references and exposes false contrasts from drift/noise; it does not eliminate
rapid fluctuations or distinguish persistent carryover by itself. Outputs use
`q3/q3_pump_probe_confirmation_check_<UTC>_<id>/`. Evaluate each candidate against
its local references, the null distribution, repeat consistency, and the short
reference/IQ changes before deciding on a dose or delay scan.

## Confirmation results and amplitude dependence

Session `q3_pump_probe_confirmation_check_20260926T211749Z_abb5ca0f` completed
all 768 blocks (307,200 shots) at commit `c794ee5`, from 21:17:56 to 21:25:19
UTC. CSV counts/populations match the manifest and all blocks report 400 records.
The median before/after sham separation fell to 1.12 seconds (maximum 2.39),
but the median absolute sham change is still 0.0325 and the maximum is 0.2275.

Use each triplet's acquisition start times to interpolate its local sham, then
form one test-minus-sham contrast per repeat. Report repeat scatter, not merely
pooled binomial error. For comparison with the zero-drive null or detuned pump,
subtract the corresponding contrast within the same repeat, target, preparation,
and hold. Those triplets are nearby but not simultaneous. The intervals below
are unadjusted 95% Student-t intervals across eight repeat contrasts; they assume
independent repeats and do not account for the full set of inspected comparisons.

The clearest candidate is **4.110 GHz, +8 MHz pump, ground preparation, 2-us
hold**. Its local contrasts are +0.0688, +0.0601, +0.0428, +0.0405, +0.0803,
+0.0639, +0.0329, +0.0141: all eight positive, mean +0.0504. Relative to the
−20-MHz control's local contrasts, the difference is +0.0634 with interval
[+0.0404, +0.0864]. Relative to the noisier zero-drive null, it is +0.0326
with interval [−0.0232, +0.0885]. Thus it is a repeatable candidate relative to
its local references and detuned control, with uncertainty remaining in the
explicit null comparison. All 24 raw IQ files for these eight triplets reproduce
the saved classified counts. The unthresholded IQ-axis contrast has the same
positive mean sign.

The earlier 4.098-GHz ground/10-us +8-MHz candidate is +0.0348 relative to
its local shams, while its null is +0.0337. Their difference is +0.0011 with
interval [−0.0734, +0.0757]; it does not separate from this null check. At
4.110 GHz, +8 MHz no longer gives a consistent excited-prepared short-reference
decrease. There is no established relaxation improvement or TLS suppression.
The positive ground/short-hold signal may involve excitation, preparation/reset,
or another pump-dependent mechanism. Classified populations are not calibrated
thermal populations, and the intervening feedback-reset latency is not recorded.

The next stage tests amplitude dependence at fixed 15-us duration:

```powershell
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbePilot --run --dose-check
```

Probe only 4.110 GHz. For each ground/excited preparation and 2/10-us hold,
randomize five tests: +8 and −20 MHz each at programmed gains 1500 and 3000,
and the zero-gain null at +8 MHz. Every test retains its own matching-frequency
sham-before/test/sham-after triplet. Gain is saved per manifest point and the
effective waveform gain is recorded as `effective_pump_gain` in the CSV.
`test_condition` includes gain for nonzero tests, and `comparison_id` pairs the
three blocks. Gains are DAC settings, not a calibrated microwave power scale.

Twelve repeats of 400 shots yield 720 blocks (192 driven, 528 zero-gain),
288,000 recorded probe shots. All prior reset, flux, return, idle, and pulse
settings remain fixed, and no pump gain exceeds the already tested 3000.
Outputs use `q3/q3_pump_probe_dose_check_<UTC>_<id>/`. Look for repeatable
amplitude dependence at +8 MHz relative to both null and −20 MHz, and inspect
short-reference and hold-dependent changes before assigning a relaxation model.

## Amplitude results and added park-wait scan

Session `q3_pump_probe_dose_check_20260926T213400Z_b5d62447` completed all
720 blocks (288,000 shots) at commit `3811248`, from 21:34:10 to 21:40:56 UTC.
CSV counts/populations match the manifest; all blocks report 400 records.
Effective gain counts are 528 zero, 96 at 1500, and 96 at 3000. Median sham
separation is 1.14 seconds and median absolute before/after change is 0.035.
The same start-time interpolation and repeat-paired analysis as above was used.

At 4.110 GHz, ground preparation and 2-us hold:

| Test | Mean test minus local sham |
| --- | ---: |
| +8 MHz, gain 1500 | +0.0190 |
| +8 MHz, gain 3000 | +0.0510 |
| −20 MHz, gain 1500 | −0.0163 |
| −20 MHz, gain 3000 | −0.0182 |
| Zero-gain null | +0.0192 |

The +8-MHz gain-3000 contrast repeats the preceding run's +0.0504 average,
although only 10/12 local contrasts are positive in this run. Relative to the
same-gain −20-MHz control it is +0.0692, with unadjusted repeat-based 95% t
interval [+0.0271, +0.1112]. Relative to the null it is +0.0317 with interval
[−0.0148, +0.0782]. The gain-3000 minus gain-1500 contrast at +8 MHz is
+0.0320 with interval [−0.0143, +0.0783]. Thus the higher mean at larger gain
is suggestive but does not establish amplitude dependence. The corresponding
frequency-by-amplitude interaction also includes zero: +0.0339, interval
[−0.0223, +0.0900]. These intervals assume independent repeat contrasts and
are not adjusted for multiple comparisons.

All 36 raw IQ files for the +8-MHz gain-3000 ground/2-us triplets reproduce the
saved counts. Their mean unthresholded IQ-axis contrast is also positive.
Excited-prepared 10-us changes are similar for +8 and −20 MHz; there is still
no selective relaxation improvement established. Neither this experiment nor
the preceding ones establish TLS suppression or a calibrated excitation rate.

The next stage asks whether the pump-dependent contrast changes with an added
wait at park, using the existing backend's recovery interval:

```powershell
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbePilot --run --recovery-check
```

At 4.110 GHz, use +8 and −20 MHz at gain 3000, plus the zero-gain null.
Randomize ground/excited preparation, 2/10-us hold, and additional park waits
of 0, 100, or 500 us within each repeat. Each test retains its own matched
sham-before/test/sham-after triplet, including the same additional wait. Eight
repeats of 400 shots produce 864 blocks (192 driven, 672 zero), 345,600 shots.
The 15-us pump, native flux correction/return, reset settings and final 500-us
idle remain fixed. `additional_recovery_us` is saved per point and in the CSV;
the acquisition API receives it as `recovery_us`. Outputs use
`q3/q3_pump_probe_recovery_check_<UTC>_<id>/`.

The additional wait occurs **after the post-pump reset and its reference-time
guard, before probe preparation**. Zero remains a nonzero total pump-to-probe
latency because the return, readout and variable reset intervene. Longer waits
also permit qubit-state evolution at park and lengthen the shot period; no
extra reset follows this added interval. Accordingly this is a controlled
sequence-memory test, not a direct TLS lifetime measurement. Compare pump,
detuned and null contrasts separately at each wait and inspect both short
references and hold dependence before fitting any decay model.
