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

## Recovery results and probe-hold scan

Session `q3_pump_probe_recovery_check_20260926T214935Z_f3398562` completed all
864 blocks (345,600 shots) at commit `935b77c`, from 21:49:48 to 22:00:50 UTC.
CSV counts/populations match the manifest and every block reports 400 records.
Median absolute before/after sham change is 0.0225, with median separation
1.42 seconds. The same local time interpolation and repeat-paired contrasts
were used; intervals below are unadjusted 95% t intervals across eight repeats.

Mean +8-MHz pump minus its local sham, ground preparation:

| Additional post-reset wait | 2-us probe hold | 10-us probe hold |
| ---: | ---: | ---: |
| 0 us | +0.0412 | +0.0375 |
| 100 us | +0.0312 | +0.0036 |
| 500 us | −0.0013 | −0.0079 |

At 500 us both ground-probe contrasts are consistent with zero. For the 10-us
probe at zero added wait, the +8-minus-null contrast is +0.0383 with interval
[+0.0086, +0.0679], and +8-minus-20 is +0.0374 with interval [+0.0035, +0.0713].
The latter contrast changes by −0.0440 between 0 and 500 us, interval
[−0.0829, −0.0051]. This is evidence consistent with a transient pump-dependent
response, with multiplicity and the changing shot period still relevant.

The explicit null matters: ground/2-us at zero added wait has a positive null
contrast +0.0183 in all eight repeats (interval [+0.0107, +0.0259]). The
corresponding +8-minus-null result is only +0.0229, interval [+0.0003, +0.0455].
For that probe, the 500-minus-0-us change after null subtraction includes zero,
[−0.0472, +0.0134]. Local shams therefore do not remove every systematic or
history effect, and the ground/2-us curve alone does not establish a decay.

Ground-state reference populations also fall with added wait: the local shams
for +8-MHz ground/2-us change from about 0.135 at zero wait to 0.078 at 500 us.
These are classified signals, not calibrated thermal populations. The wait
changes preparation history as well as elapsed time, while the reset latency
remains unmeasured. No TLS lifetime is fitted, and no TLS suppression or
persistent frequency displacement is established. Excited-prepared probes do
not show a consistent selective survival improvement.

A raw-data check reclassified 120 blocks: all three zero-wait ground/2-us test
conditions and their references, plus the +8 ground/10-us triplets at 0 and
500 us. All counts match. The ground/2-us null offset remains in the final
350 shots as well as the first 50; it is not explained by simply discarding
the first 50 shots. Unthresholded IQ gives the same broad pattern of smaller
ground-probe response at 500 us.

Next, separate an early probe offset from changes with target hold time:

```powershell
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbePilot --run --probe-time-check
```

At 4.110 GHz, keep pump gain 3000 and duration 15 us, +8/−20-MHz controls,
and the zero-gain null. Randomize ground/excited preparation and programmed
probe holds 0.1, 2, 10, and 30 us, with no additional recovery wait. Every test
retains its own matching sham-before/test/sham-after triplet. Twelve repeats
of 400 shots produce 864 blocks (192 driven, 672 zero), 345,600 shots. Output
prefix is `q3/q3_pump_probe_probe_time_check_<UTC>_<id>/`.

The 0.1-us point still has a 0.5-us arrival and 40-us return; it is not zero
interaction time or a readout immediately after reset. The pinned native
correction generates finite positive-duration segments for all four requested
holds: target windows 0.6/2.5/10.5/30.5 us followed by the same 40-us complete
return. This was checked without hardware. No pulse backend changes are made.
An offset at the earliest point versus growth during the hold will guide a
subsequent location/reset control; neither outcome alone identifies a TLS.

## Probe-hold results and probe-location control

Session `q3_pump_probe_probe_time_check_20260926T220924Z_3cad5178` completed
864 blocks (345,600 shots) at commit `29ad774`, from 22:09:38 to 22:18:19 UTC.
CSV counts/populations match the manifest; all blocks report 400 records.
Median absolute before/after sham change is 0.03625, with median separation
1.18 seconds. Contrasts use the same local interpolation and repeat pairing.

| Programmed probe hold | +8-MHz ground-prepared test minus local sham | +8-MHz excited-prepared test minus local sham |
| ---: | ---: | ---: |
| 0.1 us | +0.0490 | +0.0173 |
| 2 us | +0.0401 | +0.0165 |
| 10 us | +0.0142 | +0.0200 |
| 30 us | +0.0210 | +0.0334 |

The extra ground signal is already present at the earliest programmed hold.
That point still includes the 0.5-us arrival and 40-us return, so this does not
locate the effect before the entire probe excursion. At 0.1 us the local
contrast has an unadjusted repeat-based 95% t interval [+0.0115, +0.0865], but
subtracting the null gives +0.0451 with interval [−0.0253, +0.1154], and
subtracting the −20-MHz control gives +0.0292 with interval [−0.0137, +0.0721].
Null fluctuations include one +0.241 contrast; they materially limit inference.

None of the ground-prepared pump-control changes between 0.1 us and the later
holds excludes zero with these repeat-based intervals. Excited/10-us +8-minus-20
is +0.0310, interval [+0.0048, +0.0572], but its increase relative to 0.1 us
includes zero, [−0.0342, +0.0524]. Thus the data do not establish an extra
excitation rate during the hold or selective relaxation suppression. These
are unadjusted intervals over twelve repeats, not multiplicity-corrected claims.
A check of 72 raw blocks (ground/0.1-us +8 and null triplets) reproduced all
saved classified counts. Unthresholded IQ also has a positive early +8 offset.

Next, test whether the probe excursion to 4.110 GHz is required:

```powershell
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbePilot --run --location-check
```

Pump at the same 4.110-GHz flux target in every block, with +8/−20-MHz tones
at gain 3000 for 15 us, plus the zero-gain null. Randomize probe location
(`target` or `park`), ground/excited preparation, and 0.1/10-us hold. Twelve
repeats of 400 shots give 864 blocks (192 driven, 672 zero), 345,600 shots.
Every test has its own matched-location, matched-hold sham-before/test/sham-after
triplet. Additional recovery stays zero; reset and final idle settings are fixed.

The park probe remains at DAC −25146 (configured park frequency about 4.367 GHz)
while the target probe visits DAC −16151 (model frequency 4.110021 GHz). Both
use the same native compensated segment durations, generator pulse lengths,
and synchronization barriers. For park, every segment's displacement from park
is zero; compensation and stepping stay enabled to preserve timing. The pump's
configured target is restored after emitting the probe. Park mode rejects
unsupported non-native/ramp/overlapping-return settings rather than silently
using a differently timed path. Preparation pulses and readout remain at park.

The real flux-command emission path was checked with both synthetic and this
run's saved native correction: for 0.1/10-us holds, target/park instruction
sequences match apart from flux gain, and every park gain equals −25146.
This is software verification, not a measurement of physical flux settling.

Outputs use `q3/q3_pump_probe_location_check_<UTC>_<id>/`. `probe_location` and
`probe_dc_gain` identify the probe; the existing `target_frequency_ghz`,
`realized_frequency_ghz`, and `dc_gain` continue to identify the pump target.
Compare pump-control contrasts within each location, then their difference.
A response that also appears at park would implicate effects not requiring the
probe's loss-region excursion. A difference between locations would still not
by itself identify a microscopic TLS, because relaxation and flux histories
differ between the two locations.

## Location-stage calibration rejection and timing diagnostic

Session `q3_pump_probe_location_check_20260926T222531Z_cbda4df8` failed during
`prepare_reset_session` at commit `7414ec3`. All 864 measurement points remain
pending; no park/target probe comparison was acquired. The `pynq` import notice
was not the stopping error: the PC successfully connected to the remote QICK.

The three saved attempts under `q3_2026_09_26/q3_18_25_39_...` show:

| Attempt | Payload peak fit score | Loop peak fit score | Loop held-out ground acceptance |
| ---: | ---: | ---: | ---: |
| 1 | 0.7225 | 0.6755 | 0.0010 |
| 2 | 0.7345 | 0.6980 | 0.0000 |
| 3 | 0.7215 | 0.6795 | 0.0000 |

`qua_thresholds` searches for a training threshold with score greater than 0.7.
When none exists, its fallback selects the first positive-score threshold near
the minimum projection. That accepts essentially no ground shots. The separate
20% confident-assignment guard then correctly rejects the calibration. These
peak values are training fit scores, not measured reset fidelity. The prior
successful loop calibration at 18:09:34 had peak score 0.7010 and ground
acceptance 0.684: the fit was already close to the policy boundary. Payload IQ
centers/separation remain broadly comparable, and all arrays contain 2000 records.

All three failed attempts and the preceding success share config SHA256
`df81b794e6baecad99e998f6515891d773be1158f9b6f6033476e4c3e9877588`.
No changed calibration settings or executed location-probe code explain this
failure. The overlapping loop reference distributions fail the current fitting
criterion; why they became insufficiently separated is not yet established.

Code inspection found a pre-existing timing mismatch: production calibration
uses `build_calibration_config(tls.BaseConfig, ...)`, leaving the reference
program's default legacy accumulator timing and 2-us read delay. The pump-probe
runner applies `official_wait_all`, pre-measure synchronization, flush off, and
10-us read delay only after calibration. Calibration also deliberately uses
ramped per-shot park references, unlike persistent-park active acquisition.
These differences justify a diagnostic, but do not prove the cause of this
particular failure. Do not weaken thresholds or reuse a stale calibration.

Run the new calibration-only diagnostic:

```powershell
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeResetCheck --run
```

It acquires profiles in forward/reverse order:
legacy, official, official_guard20, official_guard20, official, legacy.
Each profile collects 2000 ground and 2000 pi-prepared records in each of
payload and loop contexts: 48,000 reference shots total. The legacy profile
preserves the current production calibration config. Official changes only the
four feedback timing fields used by the pump-probe runner. Official_guard20
additionally increases loop recovery from 10 to 20 us. Drive frequencies,
amplitudes, reference flux protocol and the 0.7/0.2 policy values stay fixed.

Every profile saves `config.json`, `calibration.json`, and `calibration_raw.npz`
in a distinct subfolder, including rejected fits. The manifest records the
baseline config hash, profile results, acceptance/rejection reason and commit.
Expected quality rejections do not stop this diagnostic; transport or unexpected
acquisition failures do. No active feedback loop, TLS pump, or location scan is
run, and no fitted calibration is installed automatically. Output prefix:
`q3/q3_pump_probe_reset_check_<UTC>_<id>/`.

Compare repeated profiles, raw distributions, and both contexts before choosing
a repair. Even improved scores under official timing would not alone establish
root cause or validate equivalence to the full active acquisition sequence.

## Reset timing diagnostic result and location retry

Session `q3_pump_probe_reset_check_20260926T223505Z_7adae581`, commit
`0b27e6d`, completed all six profiles between 22:35:05 and 22:35:28 UTC.
All 48,000 reference shots were saved. Offline refitting of both contexts in
every profile exactly reproduces the saved classifiers and manifest metrics;
all six bundles pass the unchanged 20% confident-assignment guard. Saved config
digests also reproduce exactly, including the unchanged legacy baseline hash.

| Profile, acquisition order | Payload peak fit score | Loop peak fit score | Loop held-out ground acceptance |
| --- | ---: | ---: | ---: |
| Legacy, first | 0.7375 | 0.7545 | 0.528 |
| Official, first | 0.7765 | 0.7470 | 0.549 |
| Official + 20-us recovery, first | 0.7625 | 0.7740 | 0.515 |
| Official + 20-us recovery, second | 0.7695 | 0.7925 | 0.505 |
| Official, second | 0.7545 | 0.7480 | 0.571 |
| Legacy, second | 0.7450 | 0.7570 | 0.556 |

The original calibration settings now pass at both ends of the comparison.
Official timing alone does not improve the loop peak score in these repeats.
The 20-us profiles have higher peak scores, but two adjacent repetitions do not
establish a robust improvement, explain the prior rejection, or measure active
reset fidelity. The earlier failure was not reproduced; its physical cause
remains unresolved. Do not describe this as a confirmed timing repair.

Next step: retry the existing location check without changing calibration or
acquisition settings. It acquires and validates a fresh production calibration;
none of the diagnostic fits is reused. This preserves comparability with prior
pump-probe stages and retains the existing rejection guard.

```powershell
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbePilot --run --location-check
```

The planned run remains 864 measurement blocks, comparing target and park
probes after identical target pumping. If fresh calibration fails again,
inspect that failure rather than weakening the acceptance policy or repeatedly
retrying until a marginal calibration passes.

## Completed location comparison

Session `q3_pump_probe_location_check_20260926T224556Z_2aba0564`, commit
`ed0ba6a`, completed all 864 blocks / 345,600 shots from 22:46:01 to
22:55:17 UTC. Payload and loop peak calibration fitting scores were 0.7110
and 0.7290; loop held-out ground acceptance was 0.559. These scores do not
measure reset fidelity. The payload classifier's held-out false-positive
fraction was 0.192, so classified excited fractions are not corrected physical
populations.

For each triplet, subtract a time-interpolated before/after sham. The following
are ground-prepared +8-MHz responses, in percentage points; intervals are
unadjusted 95% Student-t intervals across twelve repeats:

| Hold | Target response | Park response | Target minus park |
| --- | --- | --- | --- |
| 0.1 us | +0.97 [-3.22, +5.15] | +2.12 [-3.31, +7.56] | -1.16 [-8.12, +5.81] |
| 10 us | +3.01 [-0.67, +6.70] | +3.81 [-0.27, +7.89] | -0.80 [-7.60, +6.00] |

All location interactions after additionally subtracting the null or -20-MHz
control include zero, for both preparations and both holds. No target-specific
response or equivalence between locations is established. At park, the g/10-us
+8-minus-null contrast is +5.72 points [0.14, 11.30]; the g/0.1-us
+8-minus-minus20 contrast is +8.44 [2.45, 14.42]. These are exploratory,
unadjusted comparisons among multiple endpoints. The latter includes a negative
-20-MHz response, not a resolved positive +8-MHz response alone. Neither
establishes TLS excitation, cooling, or improved lifetime.

Median absolute before/after sham change is 3.375 points (maximum 24 points),
over a median 1.244-second triplet span. Repeat scatter substantially limits
precision. All 864 manifest/summary rows, shot counts, probe DAC labels and
effective pump gains agree. Raw IQ reclassification reproduces 144 blocks
(57,600 shots): g/10-us, both locations, +8 and null triplets. Discarding the
first 50 or 200 shots retains a similar park contrast but widens its interval
to include zero; this sensitivity check is not a replacement primary analysis.

Next: one independent repeat of the unchanged `--location-check` experiment,
with a new production calibration and the same quality guards. Retain this
first run regardless of the repeat outcome. Assess repeatability of the
predefined location contrasts and null controls across both sessions; do not
select whichever hold, control, or session happens to look significant. If
large fluctuations persist without a reproducible contrast, prioritize
readout/reset stability diagnostics over further pump-parameter scans.

## Independent location repeat and reference-stability next step

Session `q3_pump_probe_location_check_20260926T230016Z_fa6209b8`, commit
`e5ccf98`, completed 864 blocks / 345,600 shots from 23:00:21 to 23:09:52 UTC.
Payload/loop peak calibration fit scores were 0.7250/0.7245, and loop held-out
ground acceptance was 0.646. All manifest/summary counts and probe DAC/pump-gain
labels agree. Raw IQ independently reproduces the g/10-us +8/null triplets at
both locations (144 blocks / 57,600 shots).

The short-hold park +8/null triplets were also checked directly from raw IQ
in both sessions: 72 blocks / 28,800 shots per session. Reclassification exactly
reproduces their counts and the +4.79/+5.02-point null-corrected contrasts.

The planned repeat retains an interesting park response but does not establish
TLS-specific probe dynamics. Ground-prepared short-hold park contrasts were:

| Contrast, percentage points | First location run | Repeat |
| --- | ---: | ---: |
| +8 MHz minus its local sham | +2.12 | +4.94 |
| Above contrast minus null contrast | +4.79 | +5.02 |
| Above contrast minus -20-MHz contrast | +8.44 | +4.31 |

Equal-session averages give short-hold park +8-minus-null +4.90 points
[+0.33, +9.47] and +8-minus-minus20 +6.37 [+2.88, +9.87]. These are exploratory,
unadjusted 95% intervals using within-session repeat variances and a
Welch-Satterthwaite degrees-of-freedom approximation. They are conditional on
these two sessions; two sessions do not provide a reliable estimate of
between-session reproducibility. The two runs use the same randomized schedule.

All target-minus-park interactions after null or -20-MHz subtraction still
include zero, for both preparations and holds. A few unadjusted contrasts with
local sham alone exclude zero (including excited-prepared location differences),
but these are not robust across the additional control corrections. The first
run's g/10-us park +8-minus-null contrast was +5.72 points; the repeat is -0.12.
Thus no clear target-specific effect or lifetime improvement is established,
and the earlier 10-us park endpoint did not reproduce. Do not interpret an
unresolved difference as proof that locations are equivalent.

Median absolute local sham change remains 3.5 points (maximum 26), over median
1.354-second triplets. Follow the prior decision to investigate reference
stability before further pump-parameter scans. Extend the existing calibration
diagnostic with `--stability-check`: twelve identical legacy profiles with
scheduled starts 30 seconds apart, each containing 2000 shots for ground/pi in
payload/loop contexts (96,000 total). Starts are monotonic deadlines and actual
acquisition start times are recorded separately from scheduling waits; late
slots are acquired without dropping data. The last scheduled start is at
330 seconds, so normal runtime is about six minutes.

Keep drive, readout, timing, reference flux protocol, and 0.7/0.2 policies fixed.
Save rejected fits and all raw references; install none. Offline analysis will
compare IQ centers/separation, original versus freshly fitted classifiers, and
quality metrics over time. This is an unpumped reference test with per-shot
park ramps and sequential ground/pi acquisitions, not a direct measurement of
active-reset fidelity or a full reproduction of the pump sequence. A stable
result would not rule out pump-induced or feedback-specific effects.

```powershell
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeResetCheck --run --stability-check
```

Output prefix: `q3/q3_pump_probe_reference_stability_<UTC>_<id>/`.

## Reference-stability result: failure reproduced without pumping

Session `q3_pump_probe_reference_stability_20260926T231759Z_361196be`,
commit `7f2fcd9`, completed all twelve references / 96,000 shots. Actual starts
were within 0.047 seconds of scheduled offsets 0 through 330 seconds. All
twelve config hashes equal the original legacy baseline. All 24 independently
refitted classifiers exactly reproduce the saved classifiers and manifest
metrics; every raw array has 2000 finite records.

Only five bundles passed: indices 0 and 8–11. Indices 1–7 failed because the
loop training peak did not exceed 0.7. Loop peak scores in time order were
0.7010, 0.6935, 0.6750, 0.6835, 0.7000, 0.6985, 0.6890, 0.6975, 0.7065,
0.7130, 0.7310, 0.7390. The exactly 0.7000 score also fails the strict `>`
criterion. One payload fit (index 7, peak 0.6905) likewise fell below the
fitting criterion. Rejected loop ground acceptance was 0–0.004 because of the
existing fallback threshold, not a measured disappearance of ground population.

Offline application of the *first* classifier to odd-index held-out shots in
each later reference provides a comparison unaffected by threshold refitting:

| Metric range across twelve references | Payload | Loop |
| --- | ---: | ---: |
| Fresh fit held-out balanced score | 0.6970–0.7365 | 0.6645–0.7280 |
| First classifier held-out balanced score | 0.6965–0.7385 | 0.6645–0.7280 |
| First ground-threshold acceptance | 0.703–0.765 | 0.665–0.786 |
| First excited-threshold false-positive fraction | 0.108–0.158 | 0.214–0.335 |

The abrupt near-zero acceptance is a fitting-policy discontinuity. Holding
thresholds fixed removes that discontinuity but does not recover high
classification quality; refitting provides no consistent benefit on held-out
shots. These ranges are descriptive, not simultaneous confidence intervals.
They do not establish a specific hardware fault, isolate readout from state
preparation, or measure active-reset fidelity. The pump is not necessary to
produce the calibration rejection. This also does not prove that prior pump
contrasts were entirely caused by calibration variation. No stale fit is
installed and no threshold is weakened.

Next, compare all three already-tested timing profiles repeatedly within the
same run, while this marginal regime is relevant. Add `--compare-timing` to
`--stability-check`: each of twelve 30-second slots contains legacy, official,
and official_guard20 references. All six profile orders occur twice, balancing
each profile's position within the group; `comparison_round` identifies matched
groups. There are 36 fits / 288,000 reference shots. All drive/readout settings
and fitting/acceptance criteria stay fixed; only the documented timing-profile
fields differ. This remains an unpumped, non-feedback reference diagnostic.

Compare within-round held-out separation, error/acceptance rates, and quality
rejection rates, keeping both contexts and all rounds. An alternative passing
more frequently is useful evidence but is not itself validation of the full
active acquisition. Groups are sequential, with actual timestamps retained;
counterbalancing reduces rather than eliminates history and drift confounding.

```powershell
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeResetCheck --run --stability-check --compare-timing
```

Normal runtime is about six minutes; output prefix is
`q3/q3_pump_probe_timing_stability_<UTC>_<id>/`.

## Repeated timing comparison result and operational reset check

Session `q3_pump_probe_timing_stability_20260926T233203Z_7a30eeb3`, commit
`eb352720`, completed all 36 calibrations / 288,000 reference shots. All 72
classifiers refit exactly from raw arrays; all profile configs, hashes,
acceptance decisions and manifest metrics agree. Final acquisition began at
337.25 seconds. Each profile was measured once in every round.

| Profile | Bundles passing guard | Mean payload held-out balanced score | Mean loop held-out balanced score |
| --- | ---: | ---: | ---: |
| Legacy | 10/12 | 0.7197 | 0.7106 |
| Official | 11/12 | 0.7408 | 0.7448 |
| Official + 20-us loop recovery | 12/12 | 0.7418 | 0.7498 |

Within-round candidate-minus-legacy held-out score differences are +2.21
percentage points [1.19, 3.23] for payload and +3.93 [2.95, 4.90] for loop.
Intervals are unadjusted 95% t intervals across twelve paired rounds. Official
alone improves loop score by +3.42 [2.18, 4.66]. The additional 20-us profile
versus official alone gives +0.50 [-0.75, 1.75] on held-out loop score: its
incremental improvement is unresolved. Candidate loop training peaks range
0.7245–0.7780; ground acceptance is 0.453–0.611, with excited references
falsely accepted as ground at 0.113–0.188. Thus passing the guard is not evidence
of high reset fidelity, and 12/12 success does not establish a long-term failure
rate. Still, the repeated reference results support testing candidate timing
in an actual feedback sequence before using it for more pump-probe data.

`TLSPumpProbeResetValidation` performs that bounded operational check. It
acquires and saves one fresh candidate calibration, applies the unchanged
quality guard, and stops before feedback if rejected. It then holds that
classifier fixed for twelve rounds of four conditions: native unbounded reset
or no feedback, each with nominal no-pi or pi preparation. Each block has 400
shots, for 19,200 benchmark shots; pre/post reference sets add 16,000 shots.
Each condition occupies each ordinal position three times. Round starts are
scheduled at 30-second offsets through 330 seconds, with actual times saved.

The existing `OPXResetBenchmarkProgram` stays at persistent park with hard-step
initialization; it has no TLS pump or target excursion. After the initial
decision measurement and optional feedback reset, an additional verification
readout follows a 20-us synchronization delay. Inter-shot idle is 500 us.
Candidate timing is applied after production session overrides, retaining the
20-us loop recovery. Per-shot NPZs retain all eight record fields: preparation,
initial decision projection, reset attempts, pi count, terminal status,
verification I/Q, and final decision projection. The last projection is a reset
decision, not the verification readout. Both payload- and loop-classifier
verification fractions are reported as uncorrected observables.

No-feedback and feedback arms have different elapsed times and readout counts;
the no-feedback arm is not a duration-matched causal control. Nominal ground
preparation means no pi pulse, not a certified ground state. This tests
operational behavior and separate verification readouts, not absolute reset
fidelity or equivalence to the full pump sequence. No calibration or timing
default is changed globally. End references are saved and evaluated without
updating the classifier; a rejected end reference is reported for analysis.

An incomplete returned block is saved before rejection. A streaming timeout
saves recovered shot records and completed/recovered counts before re-raising
the original timeout; it never silently retries the acquisition. Mocked tests
cover the full 48-block run and final references, rejected initial calibration
preventing feedback, and saved partial records on watchdog failure.

```powershell
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeResetValidation --run
```

Normal duration is about six minutes. Output prefix:
`q3/q3_pump_probe_reset_validation_<UTC>_<id>/`.

## Operational reset result: termination does not erase preparation dependence

Session `q3_pump_probe_reset_validation_20260926T234722Z_791c9c1e`, commit
`af5cc460`, completed 48 benchmark blocks and both reference sets. All 19,200
benchmark shots and 16,000 reference shots were independently checked. Saved
verification fractions, attempt/pi counts, preparation and terminal labels
agree with raw records; all four reference classifiers refit exactly. The
runtime classifier equals the initial saved bundle and stays fixed throughout.

Both reference bundles passed. Initial payload/loop training peak scores were
0.7515/0.7195; final scores were 0.7425/0.7065. Using the original loop classifier
on held-out initial/final reference shots gives balanced scores 0.7090/0.7165,
ground false-positive fractions 0.329/0.310, and pi-positive fractions
0.747/0.743. There is no large endpoint degradation in these metrics; they do
not exclude intervening drift or a calibration-versus-benchmark context mismatch.

Mean verification fractions labeled excited by the fixed loop classifier:

| Nominal preparation | Active feedback | No feedback |
| --- | ---: | ---: |
| No pi (g label) | 0.2346 | 0.2898 |
| Pi (e label) | 0.3054 | 0.4458 |

Paired active-minus-no-feedback differences are -5.52 percentage points
[-8.40, -2.64] for g and -14.04 [-18.16, -9.92] for e. Within the active arm,
e-minus-g remains +7.08 points [2.75, 11.42]. The payload classifier gives the
same qualitative result (+6.73 [2.45, 11.01]). These are unadjusted 95% t
intervals across twelve rounds. Active/control durations differ, so the lower
active signal is not a clean causal estimate of feedback benefit. Fractions
are not corrected excited populations or reset fidelities; do not invert the
reference confusion matrix across these different sequence contexts.

All 9600 active shots report `CONFIRMED_GROUND`, with no watchdog failures.
Mean reset attempts are 1.024 (g) and 2.734 (e); pooled 99th percentiles are
14 and 18, and maxima 37 and 38. Mean pi counts are 0.732 and 2.338. Zero
feedback attempts occur in 68.7% of g and 17.7% of e shots. These conditional
fractions select different shot populations and should not be used to infer
which pathway causes the residual signal. Operationally, a terminal ground
decision has not removed dependence on nominal initial preparation in the
separate verification observable. This supports continuing pump-off checks.

Next: `--delay-check` repeats this same benchmark with verification delays of
20, 100, and 500 us. Keep reset-loop recovery at 20 us, the reference profile,
drive/readout settings, and fit/acceptance policies unchanged. Only the wait
before the additional verification readout changes. Twelve rounds contain all
twelve reset/preparation/delay combinations; each occupies each ordinal
position once. There are 144 blocks / 57,600 benchmark shots plus 16,000
pre/post reference shots. Earliest round starts remain 30 seconds apart; actual
starts are saved and the typical run remains about six minutes.

Primary comparison: e-minus-g verification contrast within the active arm at
each delay, and its paired change from 20 us; retain the no-feedback comparisons,
both classifiers, null result possibilities, and pre/post references. This
tests whether longer waits reduce the preparation dependence. It does not
identify its microscopic source, establish absolute reset fidelity, or justify
a lifetime fit. Longer waits may also erase a desired pump-induced response;
do not promote them into pump-probe defaults without inspecting the result.

```powershell
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeResetValidation --run --delay-check
```

Output prefix: `q3/q3_pump_probe_reset_delay_check_<UTC>_<id>/`.

## Verification-delay result and first-readout drive control

Session `q3_pump_probe_reset_delay_check_20260927T002012Z_b7a77792`, commit
`bb47105e`, completed all 144 benchmark blocks and both reference sets. All
57,600 benchmark shots and 16,000 reference shots were checked against the
manifest; all four reference fits reproduce exactly. All 28,800 active shots
have confirmed-ground terminal status, and all no-feedback records have
no-reset status. No runtime classifier update occurred.

Using the fixed loop classifier, the nominal pi-minus-no-pi verification
contrast in the active arm is:

| Verification delay | Contrast, percentage points | Unadjusted 95% paired t interval |
| --- | ---: | --- |
| 20 us | +5.48 | [2.29, 8.67] |
| 100 us | +3.35 | [0.89, 5.82] |
| 500 us | +1.125 | [-0.027, 2.277] |

The paired change at 500 versus 20 us is -4.35 points [-7.86, -0.85]; the
100-versus-20 change remains unresolved. Payload-classifier analysis agrees
qualitatively. At 500 us, an unresolved difference is not proof of equivalence
or perfect initialization: a residual difference of about two points is still
compatible with these data. The no-feedback contrast also drops, from +18.29
points at 20 us to +1.44 [0.16, 2.72] at 500 us. Active/no-feedback differences
at 500 us include zero for both preparations.

The nominal ground verification fraction itself falls substantially: active
0.2465 to 0.1135 and no-feedback 0.2442 to 0.1063 from 20 to 500 us. Both
reference bundles pass; original-classifier held-out loop balanced score is
0.7165 initially and 0.7020 finally (ground false-positive 0.289 to 0.311).
These observations support a transient preparation/readout-related background,
without distinguishing qubit relaxation, measurement effects, or readout-chain
memory. They do not establish a microscopic cause or a TLS lifetime. A 500-us
wait may also suppress the pump-associated transient of interest, so it is not
automatically promoted into the pump-probe sequence.

Next: `--readout-memory-check` directly varies the preceding readout drive.
Feedback is disabled in every arm. Compare the initial readout pulse at its
normal amplitude versus zero amplitude, retain its ADC trigger/integration and
digital timing, and use the normal amplitude for the final verification pulse.
Use both nominal preparations and all three delays (20/100/500 us), twelve
balanced rounds, 400 shots per block: 57,600 benchmark shots plus 16,000 fresh
pre/post reference shots. Initial and final physical gain values are saved in
each manifest entry. The zero-amplitude initial projection is not a calibrated
state measurement; it is retained for auditing and never drives feedback.

The dedicated `OPXReadoutMemoryBenchmarkProgram` subclasses the existing
benchmark, rejects feedback and periodic readout, and permits only zero or
normal initial drive gain. It emits the same pulse-register setup calls for both
arms, measures/projects the first capture, and restores normal readout registers
before verification on every shot. Base benchmark behavior and production
defaults are unchanged. Tests compare the actual readout-register helper's
emitted settings, require gain restoration, and exercise all 144 mocked blocks.

Primary comparison: normal-minus-zero initial drive within each preparation
and delay, and its change with delay, retaining both classifier analyses and
pre/post raw-reference checks. This tests whether the applied first readout
drive changes the later observable; it cannot by itself distinguish qubit
excitation from resonator/readout memory. The zero-drive arm still runs readout
electronics and ADC capture. Sequential blocks and cyclic order balance
ordinal position but do not eliminate predecessor effects or rapid drift.

```powershell
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeResetValidation --run --readout-memory-check
```

Typical duration is six minutes. Output prefix:
`q3/q3_pump_probe_readout_memory_check_<UTC>_<id>/`.

## First-readout drive result and reduced-amplitude screen

Session `q3_pump_probe_readout_memory_check_20260927T003357Z_70ec1322`, commit
`dfe9f566`, completed all 144 benchmark blocks and both reference sets. All
57,600 benchmark shots and 16,000 reference shots were checked. All four fits
refit exactly; raw verification fractions match the manifest; every block has
zero reset attempts/pi feedback pulses and no-reset terminal status. Manifest
gains are first 0 or 1880, final 1880. Both reference bundles passed, although
classification improved during the run: initial-classifier held-out loop
balanced score was 0.7125 initially and 0.7605 finally. Local round pairing
reduces sensitivity to slow drift but does not eliminate all history effects.

With a 20-us verification delay, the fixed loop-classifier observable is:

| Nominal preparation | Zero-amplitude first pulse | Normal first pulse |
| --- | ---: | ---: |
| No pi | 0.0919 | 0.2242 |
| Pi | 0.6194 | 0.4015 |

Normal-minus-zero paired differences are +13.23 percentage points [9.10, 17.36]
for no-pi and -21.79 [-23.83, -19.75] for pi preparation. At 100 us they are
+13.60 [10.04, 17.17] and -9.31 [-12.93, -5.70]. At 500 us the no-pi effect
remains +3.17 [2.13, 4.21], while the pi difference is unresolved at -0.56
[-2.48, 1.36]. Intervals are unadjusted 95% t intervals across twelve paired
rounds. The payload-classifier analysis agrees closely. The first readout
drive therefore changes the later observable substantially under this control,
with opposite signs for the two nominal preparations. This exceeds the scale
of earlier few-point pump contrasts but does not prove those contrasts were
entirely artifacts or identify qubit-state transitions versus readout-system
memory. These are uncorrected readout fractions, not physical populations.

Next screen reduced first-readout amplitude while preserving normal final
readout. `--readout-gain-check` uses amplitude fractions 0, 0.25, 0.5, 0.75, 1
(DAC gains 0, 470, 940, 1410, 1880 with current configuration), both nominal
preparations, and a fixed 20-us verification delay. Feedback and pump remain
off. Ten rounds cycle ten conditions so each occupies each ordinal position
once; 400 shots per block give 40,000 benchmark shots plus 16,000 pre/post
references. Earliest round starts are 30 seconds apart through 270 seconds,
so typical duration is about five minutes. No gain exceeds the normal setting.

Primary assessment: gain dependence of the later verification shift relative
to zero drive, alongside first-capture separation along the saved fixed payload
axis. `initial_z` is the hardware assembly projection: account for
`payload.assembly_plan()['excited_above']` when converting to the Python
classifier's projection convention. A held-out one-dimensional threshold
comparison can screen separation, but only projected initial data are saved;
this cannot optimize IQ angle separately at each gain. Do not interpret the
normal-gain classifier's raw first-readout excited fraction at reduced gain as
a population, or install a reduced-gain threshold without a fresh calibration.

The existing dedicated no-feedback program now permits integer first gains
between zero and the normal gain, rejecting negative, fractional, and larger
values. It preserves the normal final pulse, timing, ADC acquisition, and
raw-record layout. Existing modes retain their schedules and physical settings.
Tests exercise all five register settings and a full mocked 100-block run,
including actual gain metadata and fixed final gain. Production defaults stay
unchanged pending a usable discrimination/disturbance tradeoff and validation.

```powershell
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeResetValidation --run --readout-gain-check
```

Output prefix: `q3/q3_pump_probe_readout_gain_check_<UTC>_<id>/`.

## Amplitude screen result and half-gain feedback validation

Session `q3_pump_probe_readout_gain_check_20260927T024044Z_5e264892`, commit
`ccad8c4c`, completed all 100 blocks and both references. All 40,000 benchmark
shots and 16,000 reference shots were verified against the saved manifest;
all four calibration fits refit exactly. Feedback was off throughout and the
verification gain stayed 1880. Initial/final references both passed. The fixed
initial classifier's held-out loop balanced score changed from 0.7510 to
0.7775 (payload 0.7365 to 0.7715), so the session was not perfectly stationary.

| First amplitude / normal | Final no-pi excited fraction | Final pi excited fraction | Initial held-out balanced score |
| --- | ---: | ---: | ---: |
| 0 | 0.0765 | 0.6090 | 0.5105 |
| 0.25 | 0.0718 | 0.6138 | 0.6298 |
| 0.50 | 0.0820 | 0.6040 | 0.7343 |
| 0.75 | 0.0715 | 0.3370 | 0.7410 |
| 1 | 0.1345 | 0.3818 | 0.8165 |

Final fractions use the fixed loop classifier. Initial scores use the fixed
payload projection axis, converting assembly sign to Python convention
(`excited_above=False`, sign -1), fitting a one-dimensional threshold on even
shots and evaluating odd shots separately in each round. They measure
separation of nominal preparations, not physical readout or reset fidelity.
Half-amplitude initial score has unadjusted 95% t interval [0.7210, 0.7475];
normal [0.8030, 0.8300]. This analysis does not optimize the IQ angle at each
amplitude or demonstrate stability of one installed threshold.

At half amplitude, paired verification shifts relative to zero are +0.55
percentage points [-1.55, 2.65] for no-pi and -0.50 [-2.59, 1.59] for pi.
Neither is resolved; this does not establish zero disturbance. At 0.75
amplitude the pi shift is -27.20 [-29.11, -25.29] points. At normal amplitude
no-pi is +5.80 [1.95, 9.65] and pi -22.73 [-26.73, -18.72] points. Intervals
are unadjusted 95% t intervals across ten paired rounds; the payload analysis
agrees. The amplitude response is not monotonic. Half amplitude is a candidate
for lower disturbance with usable separation; the underlying mechanism and
any genuine TLS pump response remain unresolved.

The next `--half-gain-reset-check` uses the existing operational benchmark,
with fresh payload/loop calibrations at gain 940 and a separate fresh normal
1880 bundle for classifying final verification IQ. Both starting bundles must
pass the unchanged quality guard, with no retry or stale calibration fallback.
All first and feedback-loop readouts use gain 940. Only the independent final
readout uses 1880, after the same 20-us verification delay; a dedicated
benchmark subclass restores gain 940 before the next shot. Global defaults
and other stages are unchanged. The normal verification reference remains an
uncorrected observable; its calibration context is not identical to every
possible feedback history.

Twelve rounds compare native unbounded feedback and no feedback from no-pi
and pi preparation, 400 shots each: 48 blocks / 19,200 benchmark shots.
Both reference bundles are repeated at the end without replacing either
initial classifier, adding 32,000 reference shots total. Actual gains and
classifier source paths are recorded. Both final reference entries must be
saved before collection is complete, and the terminal report reflects their
combined acceptance. Quality rejection stops before benchmarking and retains
raw references; acquisition timeouts retain recovered partial shot records.
The run takes about six minutes. The primary assessment is residual dependence
on starting preparation after feedback, alongside no-feedback controls,
reference drift, and reset latency/attempt telemetry. Active and no-feedback
arms are not elapsed-time matched, and this test does not validate the full
pump sequence or install production settings.

```bash
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeResetValidation --run --half-gain-reset-check
```

Output prefix: `q3/q3_pump_probe_half_gain_reset_check_<UTC>_<id>/`.

## Half-gain reset result and required-loop control

Session `q3_pump_probe_half_gain_reset_check_20260927T030145Z_21b4ba3e`, commit
`807fca95`, completed all 48 blocks and four reference sets. All 19,200 benchmark
shots and 32,000 reference shots were verified, including all eight exact
calibration refits, gain metadata, classifier provenance, raw fractions,
preparation labels, counters, and terminal statuses. All 9,600 active shots
returned CONFIRMED_GROUND, a controller status rather than proof of physical
state. Both starting and both ending reference bundles passed.

The half-gain payload training peak was marginal at 0.7070 and its initial
held-out balanced score was 0.6940 (fixed initial classifier on ending data:
0.7235). Half-gain loop held-out score was 0.7755 initially / 0.7600 finally.
For normal-gain verification, fixed payload score was 0.7465 / 0.7520, but
fixed loop score drifted 0.7935 / 0.7455; loop reference ground false-positive
fraction rose 0.176 to 0.231. Thus the main comparisons use interleaved local
rounds and both verification axes; absolute fractions remain uncorrected.

| Nominal preparation | No feedback, loop verification | Half-gain reset, loop verification |
| --- | ---: | ---: |
| No pi | 0.1131 | 0.1148 |
| Pi | 0.6454 | 0.1833 |

Paired active-minus-none is +0.17 percentage points [-1.59, 1.92] for no-pi
and -46.21 [-49.40, -43.02] for pi. Residual pi-minus-no-pi after reset is
+6.85 [4.63, 9.08] points; the independent payload-axis analysis agrees at
+6.60 [4.95, 8.25]. All intervals are unadjusted 95% t intervals across twelve
rounds. There is a large operational reduction of preparation dependence,
but it is still resolved after feedback. Active and no-feedback durations
are unequal; do not attribute the entire reduction solely to corrective pi
pulses or infer a physical reset fidelity.

Mean attempts were 1.0767 (no-pi) and 2.1104 (pi), p99 8 and 10, maximum 16
for both. Initial ground acceptance produced zero feedback attempts on
63.42% of no-pi and 15.06% of pi shots. Every zero-attempt flag matches the
saved initial payload projection's ground decision exactly. Within pi shots,
zero-attempt verification was 0.4993 (723 shots), compared with 0.1273 among
those entering the loop (4,077 shots). For no-pi these conditional fractions
were 0.0917 (3,044) and 0.1549 (1,756). These subsets are selected by a noisy
measurement, not randomized causal comparisons. They motivate testing the
initial acceptance rule rather than assuming its contribution has been proven.

`--half-gain-confirm-check` interleaves three policies at the same half decision
gain and full verification gain: ordinary unbounded reset, unbounded reset
requiring at least one loop readout, and no feedback; each starts from no-pi
or pi. Twelve rounds cycle six conditions so every condition occupies every
ordinal position twice. 72 blocks x 400 = 28,800 benchmark shots, with the
same 32,000 starting/ending reference shots. Round start offsets run from
0 to 330 seconds; typical duration remains about six minutes.

The intervention suppresses only the first ground-exit branch. An initially
ground or ambiguous result waits through the existing ringdown and is
remeasured without a pi pulse; an initially excited result follows its usual
pi/remeasurement path. The existing loop classifier and ground stopping rule
then apply. This does not require two consecutive ground classifications.
Extra elapsed time and measurement are part of the intervention, so the
comparison assesses operational performance rather than isolating those
mechanisms. Thresholds, quality guards, readout amplitudes, verification delay,
and pi settings are fixed within the session. Production defaults remain off
for this diagnostic flag. Required-loop blocks must have at least one attempt
per shot; violations fail only after raw records have been saved.

Tests execute the emitted branch graph for both projection signs, including
threshold boundaries and initial ground/ambiguous/excited paths, and check
runner propagation, balancing, normal verification, and unchanged prior modes.
No measurement hardware is invoked locally.

```bash
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeResetValidation --run --half-gain-confirm-check
```

Output prefix: `q3/q3_pump_probe_half_gain_confirm_check_<UTC>_<id>/`.

## Repeated half-gain run exposed signed-multiplier overflow

Session `q3_pump_probe_half_gain_reset_check_20260927T032506Z_63856a40`, commit
`ba720e95`, ran the ordinary `--half-gain-reset-check` again, not the requested
confirmation stage: its manifest has `half_gain_reset_check=true`,
`half_gain_confirm_check=false`, and zero required-loop blocks. It completed
all 48 blocks and four reference sets. All 19,200 benchmark shots and 32,000
reference shots were checked; original fits refit exactly under the pre-fix
code and normal-gain verification fractions agree with raw IQ. This repeat is
useful but does not test the confirmation intervention.

The result deteriorated dramatically despite accepted reference reports:

| Preparation | No-feedback loop verification | Ordinary reset loop verification |
| --- | ---: | ---: |
| No pi | 0.1196 | 0.2077 |
| Pi | 0.6481 | 0.6502 |

Paired active-minus-none was +8.81 percentage points [6.71, 10.91] for no-pi
and +0.21 [-2.33, 2.75] for pi. Residual active pi-minus-no-pi was +44.25
[41.76, 46.74] points. Intervals are unadjusted 95% t intervals over twelve
rounds; payload-axis analysis agrees. Mean attempts increased to 3.5596
(no-pi) and 13.2881 (pi), maxima 143/162. All active records still reported
CONFIRMED_GROUND. This controller label cannot validate physical preparation.
The ordinary runtime configuration matches the preceding half-gain run apart
from freshly fitted calibrations; the new confirmation flag was false.

The initial loop fit had `c_int=-32768`, `s_int=-61`. Our assembly emitted
absolute coefficients, including **+32768**, into `mathi('*')`. Upstream
tProc-v1 uses a 32-bit ALU, but its multiplier takes each operand's signed
**lower 16 bits**. Thus the emitted +32768 becomes -32768. The original
coefficient selection constrained 32-bit product overflow but missed this
operand-width constraint. This is a deterministic arithmetic error, not a
statistical quality rejection, and the existing Python fit scores could not
catch it because Python used full-width multiplication.

Source inspected at upstream QICK commit
`4da51a5154e448fa3613257a967bfa6a58959a8b`:
- [tProc width B=32](https://github.com/openquantumhardware/qick/blob/4da51a5154e448fa3613257a967bfa6a58959a8b/firmware/ip/axis_tproc64x32_x8_v1/src/tproc64x32_x8.v)
- [ALU width propagation](https://github.com/openquantumhardware/qick/blob/4da51a5154e448fa3613257a967bfa6a58959a8b/firmware/ip/axis_tproc64x32_x8_v1/src/alu/alu.v)
- [Signed low-half multiplier](https://github.com/openquantumhardware/qick/blob/4da51a5154e448fa3613257a967bfa6a58959a8b/firmware/ip/axis_tproc64x32_x8_v1/src/alu/math.vhd)

Emulating this arithmetic on the saved initial loop references changes
nominal-ground acceptance from the intended 51.65% to 0.10%, and labels 98.35%
of those nominal-ground references excited. This predicts unnecessary pi
pulses and long loops, consistent with the observed failure. The actual
installed FPGA image was not read out in this analysis; hardware verification
of the correction remains the next step. Final loop calibration also had
`c_int=-32768` and `s_int=93`, but was never installed during the run. Among
148 fits in the local pump-probe diagnostic archives checked, these were the
only two with unsafe multiplier coefficients or raw magnitude metadata.
Previously successful half-gain and amplitude-screen fits passed this audit.

The fix reduces the fixed-point shift until **both absolute coefficients are
at most 32767**, retaining the existing product-headroom calculation. It refits
all thresholds in that new scale, without changing the 70% threshold-selection
policy or confident-state quality requirements. `assembly_plan()` now rejects
unsafe legacy coefficients and calibration raw-IQ magnitude metadata above
32767, and the existing calibration guard checks that plan. The raw-IQ check
is conservative at magnitude 32768 because stored metadata does not distinguish
valid -32768 from invalid +32768. Historical calibrations remain loadable and
projectable offline; they cannot silently be emitted for feedback. Reference
artifacts are saved before the guard rejects them. This check covers observed
reference range, not unforeseen runtime IQ excursions.

Refitting the archived data changes initial loop coefficients to -16384/-30
and final loop to -16384/47. The other six fits retain their coefficients.
All 32,000 reference shots then have exact Python/emulated-tProc projection
parity, and all four refitted bundles pass the unchanged statistical guards.
Regression tests cover the original wrap, all projection quadrants, independent
I/Q endpoint combinations, small-signal coefficient scaling, historical unsafe
fit rejection, and the production quality guard. Offline replay establishes
the arithmetic correction, not restored hardware reset performance.

Next repeat the ordinary half-gain reset check with fresh corrected fits.
Defer the required-loop policy experiment until this baseline is trustworthy:

```bash
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeResetValidation --run --half-gain-reset-check
```

## Half-gain reset after signed-multiplier correction

Session `q3_pump_probe_half_gain_reset_check_20260927T034723Z_ca6f9958`, commit
`3ef8e587`, completed 48 benchmark blocks and all four reference sets. All
19,200 raw benchmark shots and 32,000 reference shots were checked, with all
eight fits reproducing the saved calibrations. Decision gain was 940, separate
verification gain 1880, all active terminal statuses CONFIRMED_GROUND, and
zero-attempt records exactly matched initial payload ground classifications.
Every saved coefficient and raw-reference magnitude is within the new signed
16-bit guard. Both initial and final reference bundles passed. The fixed
full-gain loop classifier's held-out balanced score changed 0.7240 to 0.7470,
so absolute fractions still have some calibration drift.

| Nominal preparation | No-feedback loop verification | Active half-gain reset loop verification |
| --- | ---: | ---: |
| No pi | 0.1567 | 0.1406 |
| Pi | 0.6433 | 0.2219 |

Across twelve paired rounds, active-minus-none is -1.60 percentage points
[-3.22, +0.01] for no-pi and -42.15 [-44.45, -39.85] for pi. Residual active
pi-minus-no-pi is +8.13 [6.23, 10.02] points. Intervals are unadjusted 95% t
intervals; independent payload-axis verification gives +8.17 [6.20, 10.13].
This recovers the useful operational response seen in the first half-gain run
(+6.85-point residual), after the intervening unsafe-coefficient run produced
+44.25 points and long feedback loops. The run supports the arithmetic fix in
hardware but does not establish physical ground-state fidelity or the exact
installed FPGA provenance.

Mean feedback attempts are 1.034 no-pi and 2.258 pi, p99 9 and 10, maxima 18
and 22. The pi zero-attempt fraction is 18.02% (865/4800); these selected
shots have 55.14% later excited classification, versus 14.94% among the 3935
shots that entered feedback. For no-pi the corresponding fractions are 12.91%
and 16.51%. This reproduces the association between initial acceptance and
residual preparation dependence, but the subsets are selected by a noisy
measurement. The already pushed `--half-gain-confirm-check` is the direct
interleaved comparison of ordinary reset with an arm requiring one loop readout.

## Required-loop half-gain reset, first interleaved run

Session `q3_pump_probe_half_gain_confirm_check_20260927T040710Z_2289752d`, commit
`54d60bf1`, completed all 72 benchmark blocks and four reference sets. All
28,800 benchmark shots and 32,000 reference shots were checked, including
exact refits of all eight classifiers, raw verification fractions, decision and
verification gains 940/1880, terminal statuses, and shot counters. All starting
and ending reference bundles passed. No required-loop shot had zero attempts;
ordinary reset zero-attempt decisions exactly matched the saved initial payload
projection. The fixed initial full-gain loop classifier's held-out balanced
score stayed near 0.7200 at the start and 0.7225 at the end, though both are
modest. Original statistical guard thresholds were unchanged.

| Nominal preparation | No feedback | Ordinary reset | Require one loop readout |
| --- | ---: | ---: | ---: |
| No pi | 0.1242 | 0.1094 | 0.1231 |
| Pi | 0.5935 | 0.1783 | 0.1327 |
| Pi minus no-pi | 0.4694 | 0.0690 | 0.0096 |

These are uncorrected final fractions labeled excited by one fixed normal-gain
loop classifier at 20-us verification delay. Across twelve paired rounds,
required-minus-ordinary is +1.38 percentage points [-0.59, 3.34] for no-pi
and -4.56 [-6.21, -2.91] for pi. The remaining preparation gap after the
required-loop policy is +0.96 [-0.82, 2.74] points, unresolved from zero in
this session. The change in that gap versus ordinary reset is -5.94
[-8.35, -3.53] points. Independent payload-axis classification agrees: the
required-loop gap is +0.88 [-0.49, 2.24] points and the gap change is -5.81
[-7.85, -3.78]. All intervals are unadjusted 95% t intervals. The large
no-feedback pi-minus-no-pi gap confirms the reference contrast remained
observable; the active and no-feedback arms have different time histories.

Ordinary reset used mean attempts 1.212/2.508 and mean pi pulses 0.758/1.700
for no-pi/pi. Required-loop reset used mean attempts 2.853/2.959 and pi pulses
1.240/1.883. Both required-loop maxima were 18; ordinary maxima were 27/21.
Ordinary zero-attempt fractions were 64.48% no-pi and 15.96% pi. In the pi
zero-attempt subset, the later excited fraction was 0.4739 (766 shots), versus
0.1222 among shots entering feedback (4034 shots). These are selected subsets,
not randomized proof of the mechanism. The required-loop arm adds measurement
and elapsed time along with eliminating the initial stopping branch; it
establishes an operational improvement in this session, not ground-state
fidelity or a TLS pump response. Repeat it under a fresh calibration before
using it as the basis for a new pump-probe sequence or any production policy.

## Required-loop half-gain reset, independent repeat and pump-probe pivot

Session `q3_pump_probe_half_gain_confirm_check_20260927T043053Z_89ce25d4`,
commit `1457ce64`, completed all 72 benchmark blocks and both ending reference
sets. All 28,800 benchmark shots had 400-record raw blocks; the four reference
sets and all required-loop attempt counters were present. Starting and ending
calibrations passed the established quality guard. These are fixed initial
normal-gain loop-classifier fractions, not physical reset fidelities:

| Nominal preparation | No feedback | Ordinary half-gain reset | Required-loop half-gain reset |
| --- | ---: | ---: | ---: |
| No pi | 0.0704 | 0.0823 | 0.0842 |
| Pi | 0.4825 | 0.0988 | 0.0921 |
| Pi minus no-pi | 0.4121 | 0.0165 | 0.0079 |

Across twelve paired rounds, required-minus-ordinary was +0.19 percentage
points [-1.06, +1.43] for no-pi and -0.67 [-1.76, +0.43] for pi (unadjusted
95% t intervals). This repeat does not resolve an advantage between the two
active policies. The initial half-gain payload calibration accepted only 0.1%
of known ground shots, versus 77.2% in the ending half-gain reference; the
quality guard still passed because its payload requirement is confident
excited firing, while loop decisions require confident ground acceptance.
The ordinary arm had only 4/9600 zero-attempt shots (0.04%), so it almost
always entered the feedback loop, making its path closer to the required-loop
arm in this run. The ending probe
reference also passed, but this reference change limits absolute comparisons.

The next stage returns to a matched pump--probe measurement using the
experiment-only `TLSPumpProbeConfirmed` runner. It uses fresh half-gain
decision and normal-gain probe calibrations with the same official/20-us
feedback timing, then requires a loop decision in resets both before and after
the pump. At the 4.110-GHz target, eight randomized rounds of 400 shots compare
+8 and -20 MHz pumps with adjacent same-frequency zero-drive shams and a
zero-drive null. Ground probes hold 0.1 us at either target or park, yielding
144 pump--probe blocks (57,600 shots); initial and ending references add 32,000
shots. Final probe IQ is classified with the initial normal-gain bundle, and
both classifier axes and all raw IQ are saved. Ending reference failure marks
the run failed while retaining data. The new runner and program leave the
production TLS spectroscopy path and defaults unchanged.

On the measurement PC after stopping other acquisitions:

```bash
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeConfirmed --run
```

## Confirmed-reset short-hold pump--probe result and transfer follow-up

Session `q3_pump_probe_confirmed_20260927T045322Z_509b23af`, commit
`ee7a1445`, completed 144 pump--probe blocks (57,600 shots) and all four
reference sets. Starting and ending half-gain decision and normal-gain probe
references passed. Independent replay of all 144 raw IQ files reproduces both
saved classifier fractions exactly; every file has 400 shots and the recorded
read length. All 48 adjacent sham--test--sham triplets have matching detuning,
probe location, and preparation. The full-gain payload reference's held-out
peak score changed from 0.745 to 0.707, and ground acceptance from 0.650 to
0.817; the acquisition uses the frozen starting classifier throughout.

Each value below is a test block minus the mean of its immediately adjacent
shams, in percentage points of the frozen payload classifier's excited label.
Intervals are unadjusted 95% Student-t intervals across eight repeats:

| Probe at 4.110 GHz, ground preparation, 0.1-us hold | Park | Target |
| --- | ---: | ---: |
| +8-MHz pump | +0.03 [-1.60, +1.66] | +0.34 [-1.22, +1.91] |
| -20-MHz pump | +0.69 [-0.73, +2.10] | -0.27 [-2.32, +1.79] |
| Zero-drive null | -0.25 [-2.59, +2.09] | -0.64 [-2.50, +1.22] |

The independent loop classifier and reclassification with the ending probe
bundle likewise show no statistically resolved change in the classified
population. An
unthresholded Q shift for the target +8-MHz pump is -0.107 in normalized IQ
units, but the target zero-drive null is also -0.079; their within-round
difference is -0.028 [-0.136, +0.080]. None of these data establishes a
target-specific microwave effect or TLS transfer at this short hold. The
earlier strongest candidate was a **2-us target probe**, so this short-hold
result does not directly repeat it.

The `--transfer-check` follow-up keeps the same fresh dual calibrations,
required-loop half-gain resets, normal-gain final readout, +8/-20-MHz pumps,
adjacent shams and zero-drive null. It uses a **2-us hold with both ground and
excited probes at target and park**. Eight rounds of 400 shots give 288 blocks
(115,200 probe shots), plus 32,000 reference shots. The predeclared priority is
whether the earlier +8-MHz target ground-probe signal repeats against both its
shams and null, with an excited-probe response and a target-versus-park
contrast. The -20-MHz arm monitors detuning specificity. A positive response
would still require current loss-feature localization and persistence tests
before assigning a TLS mechanism.

On the measurement PC after stopping other acquisitions:

```bash
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeConfirmed --run --transfer-check
```

## Two-microsecond transfer check: candidate did not reproduce

Session `q3_pump_probe_transfer_check_20260927T050733Z_4c90b982`, commit
`57b0e009`, completed all 288 blocks (115,200 probe shots) and all four
reference sets. The starting and ending decision and probe calibrations passed.
Independent replay of every 400-shot raw IQ file reproduces the saved frozen
full-gain payload and loop fractions; all 96 sham--test--sham trios have
matching preparation, hold, detuning and location. Reclassifying with the
ending probe bundle gives the same qualitative conclusion.

The predeclared +8-MHz target comparison at a 2-us probe hold was:

| Preparation | Driven test minus adjacent shams | Zero-drive null minus adjacent shams | Driven minus null |
| --- | ---: | ---: | ---: |
| Ground | -0.52 [-3.08, +2.05] | +1.13 [-0.58, +2.83] | -1.64 [-4.99, +1.71] |
| Excited | +1.77 [-1.93, +5.46] | +0.63 [-3.66, +4.91] | +1.14 [-5.69, +7.97] |

Values are percentage-point changes in the frozen full-gain payload
classifier's excited label, with unadjusted 95% Student-t intervals across
eight paired rounds. The +8-MHz park response is +0.00 [-1.89, +1.89] points
for ground preparation and -1.30 [-4.33, +1.73] for excited preparation,
also unresolved. A park/excited zero-drive null produces -2.81 [-5.13, -0.50]
points versus its own shams; this exploratory nonzero null cautions against
assigning small contrasts to the pump. The earlier +8-MHz ground/2-us target
candidate does **not** repeat under this newly calibrated reset/readout
protocol. This does not distinguish a past transient feature from earlier
readout/reset or selection effects. It supplies no evidence for TLS population
transfer, suppression, or persistent frequency control at 4.110 GHz.

Stop tuning the pump around this unconfirmed target. The next experiment-only
stage is `--relocalize`: a **microwave-pump-off** screening scan over
3.900–4.300 GHz in 2-MHz steps using the same half-gain required-loop reset,
normal-gain probe readout, pinned flux compensation and complete return.
At each of 201 model-frequency targets, acquire nearby-in-time excited 2-us,
excited 10-us and ground 10-us probes. One forward and one reverse pass,
250 shots per block, give 1206 blocks (301,500 probe shots) plus 32,000
reference shots. Compare the local excited 2-to-10-us loss against neighboring
frequencies and the reverse pass before selecting any new pump coordinate.
This is a coarse screen: narrow features can fall between 2-MHz samples, and
the model coordinate is not an independently measured TLS frequency. The
no-drive pre-probe flux excursion remains part of the pump--probe sequence so
the eventual target is localized under the same history.

On the measurement PC after stopping other acquisitions:

```bash
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeConfirmed --run --relocalize
```

## Broadband pump-off screen finds a new repeatable loss candidate

Session `q3_pump_probe_relocalize_20260927T052905Z_ad01fe40`, commit
`2f262b45`, completed all 1206 blocks (301,500 probe shots) and all four
reference sets. The 201 model-frequency targets span 3.900–4.300 GHz in
2-MHz steps; the second pass reversed order. All references passed. Initial
and ending full-gain payload/loop held-out peak scores were 0.7495/0.7675
and 0.7505/0.7745, respectively. The manifest and summary agree on all
blocks; 102 selected raw files (25,500 shots) around the leading and
secondary candidate windows reproject exactly to both saved classifier
fractions and IQ means.

The clearest localized feature is at model coordinates **4.044–4.046 GHz**.
The adjacent excited 2-us and excited 10-us blocks give a larger loss
increment there than on the nearby flanks. In the forward pass,
`P_e(2 us)-P_e(10 us)` averages 0.190 across the two center bins, versus
0.046 across 4.036/4.038/4.040 and 4.050/4.052/4.054 GHz. In the reverse
pass the corresponding values are 0.242 versus 0.035. The center was visited
about 8.5 minutes apart. Center ground/10-us fractions remain low in both
passes. These differences were selected after inspecting the 201-point
screen; they are descriptive evidence for a current loss feature, not a
predeclared significance test or microscopic TLS identification. Structure
around 4.114–4.118 GHz is a secondary, less isolated candidate. The earlier
4.110-GHz pump target need not have coincided with the strongest current loss.

The next stage is an **independent fine localization** of the 4.045-GHz
candidate before any new pumping. `--fine-localize` screens 4.036–4.054 GHz
at 0.5-MHz spacing (37 targets), with four alternating forward/reverse passes.
At every target it locally shuffles the same pump-off excited 2-us,
excited 10-us and ground 10-us probes, now with 400 shots each. That is 444
blocks (177,600 probe shots), plus 32,000 reference shots. A candidate for
later pump tests must recur in these new passes with identifiable low-loss
flanks; the scan does not yet supply a full decay curve or an independently
calibrated TLS resonance frequency. The production TLS pipeline is unchanged.

On the measurement PC after stopping other acquisitions:

```bash
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeConfirmed --run --fine-localize
```

## Fine scan weakens the first candidate; check the second broadband feature

Session `q3_pump_probe_fine_localize_20260927T060406Z_39e09da8`, commit
`82374867`, completed all 444 pump-off blocks (177,600 probe shots) and its
final references. It revisited the same integer DC coordinates used in the
broadband screen. The 4.044–4.046-GHz, 2-to-10-us loss contrast fell from
0.190/0.242 in the two broadband passes to 0.044/0.058/0.051/0.048 in the
four fine-scan passes (five 0.5-MHz bins). The fine-scan 4.050–4.054-GHz
upper flank averaged 0.053/0.078/0.046/0.067, so the earlier sharp feature
did not recur as an isolated peak. Both payload and loop classifiers agree;
reprojecting 96 selected raw fine-scan blocks (38,400 shots) reproduces all
saved counts and IQ means. Cross-projecting the earlier and later raw blocks
with each other's payload classifiers changes the relevant contrasts by
about 0.01 or less, far too little to explain the lost peak. All starting and ending
references passed, although this does not by itself establish whether the
change was microscopic TLS motion or another time-varying device effect.

The broadband screen had a second candidate at 4.114–4.118 GHz. Across
those three 2-MHz bins, the 2-to-10-us contrast averaged 0.132 in the
forward pass and 0.173 in reverse; the adjacent 4.112- and 4.120-GHz bins
were near zero or negative. This was selected after looking at the screen
and remains a candidate rather than an identified TLS. `--secondary-localize`
checks it independently, pump-off, from 4.108 to 4.122 GHz in 0.5-MHz steps:
29 integer-DAC targets, four alternating passes, 400 shots each for excited
2-us, excited 10-us, and ground 10-us probes. The production TLS pipeline is
unchanged. A pump coordinate is deferred until a localized loss feature
recurs with low-loss flanks.

On the measurement PC after stopping other acquisitions:

```bash
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeConfirmed --run --secondary-localize
```

## Secondary scan finds a strong lower-frequency loss region

Session `q3_pump_probe_secondary_localize_20260927T062230Z_77f08842`, commit
`b5af3897`, completed all 348 pump-off blocks (139,200 probe shots) and its
final references. All four initial/final references passed. The manifest and
CSV agree on every block, and 108 selected raw blocks (43,200 shots) reproduce
their saved payload/loop excited counts and IQ means. Reprojecting selected
raw blocks through the broadband and secondary classifiers leaves the main
frequency contrast largely unchanged.

The strongest current loss is **4.109–4.111 GHz**, lower than the broadband
4.114–4.118-GHz candidate. Mean excited 2-to-10-us loss contrast across the
five 0.5-MHz center bins is 0.275/0.292/0.290/0.266 in the four passes,
versus 0.031/0.050/0.035/0.027 over the 4.1145–4.1175-GHz upper low-loss
window. The center excited 2-us population remains near the upper window;
the center excited 10-us population is lower, consistent with stronger
decay. Ground 10-us controls remain comparable across these windows. The
center was revisited in both scan directions over about three minutes. Loss
is already substantial at the 4.108-GHz lower boundary, so this scan does
not locate the lower flank. These are model frequency coordinates; neither
the same microscopic TLS nor its resonance motion has been established.

`--drift-track` is a passive time baseline before assigning any microwave
response: 4.094–4.122 GHz at 1-MHz spacing, 29 distinct integer-DAC targets,
12 alternating forward/reverse passes. Each local triplet has 250-shot
excited 2-us, excited 10-us, and ground 10-us blocks. This is 1044 blocks
(261,000 probe shots) plus 32,000 calibration shots. It covers both flanks
and tests whether the loss maximum jumps or moves during a single session.
The production TLS pipeline is unchanged.

On the measurement PC after stopping other acquisitions:

```bash
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeConfirmed --run --drift-track
```

## Park reference rejected twice before drift tracking could begin

Drift-track sessions `q3_pump_probe_drift_track_20260927T171242Z_bf54c07c`
and `q3_pump_probe_drift_track_20260927T172545Z_1d55fc4e` stopped during
initial calibration; all 1044 scan blocks remained pending in each session.
The first half-gain decision reference passed with loop peak fidelity 0.7335,
but its separate normal-gain probe reference had loop peak fidelity 0.681 and
`loop.ground_accept=0`. The second attempt failed earlier: its half-gain
decision loop peak fidelity was 0.610, again with zero confident ground
assignments. Both were properly rejected by the unchanged 0.20 acceptance
guard. The same calibration config hashes and pinned correction were used in
the successful secondary scan and both failures. The later opt-in step-response
commit does not change this reference configuration.

Ground-state IQ medians and spread remained roughly stable, while the
prepared-excited cluster approached ground across the successful scan and two
failures. At half readout gain, the median I separation fell from about 3200
to 2660 to 1130 raw counts. This supports loss of excited-state preparation
contrast, but does not distinguish a detuned park pi pulse from faster decay or
another device change. Repeating the drift tracker again without diagnosing
the park reference would be uninformative.

`TLSPumpProbeParkPiSweep` is a calibration-only diagnostic. It uses the
same half-gain park reference and `official_guard20` timing, varying only the
park pi frequency around its configured 4367.292 MHz. It measures 0,
then alternating ±2, ±4, …, ±20 MHz, and finally 0 again, with 500 shots
per ground/excited state and payload/loop context at each of 22 points
(44,000 total reference shots). Every raw IQ set and fit is saved, including
rejected fits. It installs no calibration and leaves the production settings
and quality guard unchanged. A recovered contrast away from zero would point
toward frequency detuning; persistently poor contrast would require a different
preparation/readout investigation.

On the measurement PC after stopping other acquisitions:

```bash
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeParkPiSweep --run
```

## Park pi sweep result and time stability follow-up

The 22-point park pi sweep `q3_pump_probe_park_pi_sweep_20260927T173742Z_53bfbd34`
completed without a TLS pump or drift scan. Its first 4367.292 MHz reference
failed the normal guard (loop peak fidelity 0.604; loop IQ centroid separation
about 1,000 raw counts). The intervening ±2 through ±20 MHz references all
failed and had still smaller loop separation. The final repeat at 4367.292 MHz,
roughly 25 seconds after the first, passed (loop peak fidelity 0.752; loop
centroid separation about 3,043 counts). Ground IQ medians stayed near the
same location; the prepared-excited loop median moved much farther from ground
at the final point. Frequency and time changed together, so these data do not
establish a frequency optimum or explain why the nominal-frequency contrast
changed. Payload-context median separation at the two center points was
roughly 1,800 counts both times; the larger change was in the loop context,
which measures after an initial readout and recovery. The final passing
half-gain reference does not establish that the
normal-gain probe reference would pass too.

The follow-up `--stability-check` holds 4367.292 MHz fixed. At each of twelve
20-second slots it captures the exact half-gain decision and normal-gain probe
reference configurations used by the drift tracker, saving raw IQ before any
fit and continuing past rejected references. It installs no calibration and
does not run a TLS pump or flux scan. This tests whether both tracker references
remain usable long enough to justify resuming drift tracking.

On the measurement PC after stopping other acquisitions:

```bash
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeParkPiSweep --run --stability-check
```

## Fixed-frequency reference instability and guarded pump-off scout

The 24-point stability run
`q3_pump_probe_park_reference_stability_20260927T174709Z_f89dd2fb`
completed at a fixed 4367.292 MHz park pi frequency, with paired half-gain
decision and normal-gain probe references every 20 seconds. The half-gain
reference passed in 5/12 slots; the normal-gain reference passed in 7/12.
Both passed in slots 2 and 8–11; both failed in slots 1, 3–5, and 7. The final
four pairs passed over a 60-second span. Prepared-excited IQ moved relative to
ground while the frequency remained fixed. Thus the gate failures are not
simply a wrong choice of readout gain, and one late passing reference is not
enough to certify the planned 1,044-block drift tracker. The record does not
identify whether the underlying cause is qubit-frequency motion, changing
excitation/decay, or readout-history dependence.

`TLSPumpProbeConfirmed --guarded-scout` returns to the pump-off loss question
over 4.094–4.122 GHz at 1-MHz spacing. It makes two alternating-direction
passes (174 data blocks, 250 shots each), with the original initial and final
reference pairs. It adds paired decision/probe references after each ten target
trios and at the end of the first pass. Each failed reference stops the scan,
leaving all preceding raw IQ and CSV rows for analysis. Classifiers stay frozen
within a run and the same quality guard remains active; checkpoint references
validate their continued usability and are saved for drift comparison.

On the measurement PC after stopping other acquisitions:

```bash
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeConfirmed --run --guarded-scout
```

## Return to the direct on-target pump question

The earlier clean pump tests at 4.110 GHz used +8 and -20 MHz drive detunings,
and did not resolve a response. They preceded the later pump-off localization
that found the strongest current loss around 4.109–4.111 GHz. Thus they do not
answer whether an on-target microwave pump changes that newly localized loss.
The guarded pump-off scout remains available, but the next run should test the
mechanism directly rather than keep mapping passive drift.

`TLSPumpProbeConfirmed --direct-pump` uses the model's 4.110-GHz target and
zero pump detuning, with a 15-us, gain-3000 pump. Four randomized rounds compare
each driven block with same-tone zero-drive blocks immediately before and after
it. Excited and ground probes at 2 and 10 us distinguish a change in excited
survival from direct ground excitation. A zero-drive null at +8 MHz checks for
drift or selection effects. This is 96 data blocks (38,400 probe shots), with
decision/probe reference pairs at the beginning, midpoint, and end. A rejected
reference stops the run and preserves the preceding data. The drive coordinate
is the flux-model qubit frequency, not an independently measured TLS transition.

On the measurement PC after stopping other acquisitions, **run this direct
pump test instead of the guarded scout above**:

```bash
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeConfirmed --run --direct-pump
```

## Direct pump attempt stopped before the first driven block

Session `q3_pump_probe_direct_pump_20260927T180212Z_4f14540c`, commit
`a64a62f2`, rejected its initial half-gain decision reference with
`loop.ground_accept=0.002` (required minimum 0.20), loop peak fidelity 0.613,
and payload peak fidelity 0.601. All 96 pump/sham data blocks remained pending.
This is a reference failure, not a negative TLS result.

The direct-pump runner now waits for up to twelve fresh decision/probe
reference attempts, starting them at 20-second intervals. It saves each
attempt and starts the **same** on-target pump/sham comparison only after both
references pass the unchanged guard. If no pair passes, it stops without a
pump block. Checkpoint and ending reference failures still stop a running scan
and retain its completed raw data. No rejected classifier is used for feedback
or probe analysis.

On the measurement PC after stopping other acquisitions:

```bash
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeConfirmed --run --direct-pump
```

## Wide passive-reset loss scan before choosing another pump target

The next stage is a single, pump-off survey from **4.300 down to 3.800 GHz**
at 2-MHz model-frequency spacing (251 points). It uses the existing q3
five-condition TLS scan with passive reset, so the intermittently rejected
active-reset classifier is not a prerequisite. Each frequency receives 250
shots for a ground reference, excited reference, and excited survival after
2, 10, and 25 us additional target hold beyond a 0.1-us reference hold
(313,750 measurements). The same pinned native flux-tail correction and
40-us completed return are retained. The established DAC inversion is
monotonic across the requested range: local validation gives -20522 through
-11830 DAC and at most 0.042 MHz nearest-DAC model error.

This scan locates a current loss feature for a later pump/sham comparison;
its flux-model coordinate is not by itself a TLS transition frequency.
Passive and active-reset results should not be combined without a fresh
protocol comparison. The runner uses one isolated pass and a distinct output
suffix, without changing production scan defaults.

The first wide-passive launch on September 27 failed before acquiring any
frequency point: the shared five-point runner passed `calib_params=None` to a
passive T1 experiment, which requires a preceding `SingleShot1Q` readout
calibration. Its finite-run cap counted only successful passes, so the same
setup error repeated until interrupted after more than 600 attempts. The
wide-scan runner now opts into the existing step-5 single-shot calibration
(1000 shots, minimum fidelity 0.60) and passes its discrimination parameters
to the five-point experiment. It also stops after the first failed pass and
reports the original exception. Both options are enabled only by this wide
scan; the production five-point defaults remain unchanged.

On the measurement PC after stopping other acquisitions:

```bash
git pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeWidePassiveScan --run
```

## September 27 wide passive scan and first pump coordinate

The repaired wide scan completed one 251-frequency pass from 4.300 to 3.800
GHz in 144.5 s. The preceding single-shot calibration had fidelity 0.862.
The output is
`q3/q3_2026_09_27/q3_14_16_35_TLS_PumpProbe_Wide_Passive_3p8_4p3_T1_5pt_vs_wall_clock_full.csv`
under the established RFSOC data root. Its most useful interior loss feature
is centered around 4.140 GHz: fitted T1 is 9.8, 12.9, and 11.1 us at
4.138, 4.140, and 4.142 GHz. At these three points, the mean 25-us survival
population is 0.151, versus mean P0=0.111 and P1=0.361. The corresponding
normalized 25-us survival is about 0.16, compared with about 0.77 at the
4.122–4.128-GHz lower flank and 0.85 at the 4.158–4.164-GHz upper flank.
Both scan directions show the dip. The previously followed 4.110-GHz region
is weaker in this pass (roughly 39-us fitted T1 over 4.106–4.114 GHz).
Another strong loss feature reaches the 3.800-GHz scan boundary, so its
center cannot yet be assigned. These data identify loss at a *model qubit
frequency*, not independently the microscopic TLS resonance.

The first pump check therefore uses 4.140 GHz. It applies a 15-us microwave
tone at the q3 park bias, where the calibrated qubit frequency is about
4.367 GHz, before preparing the probe state and making the same compensated
flux excursion used in the passive scan. A zero-gain arm plays the same
15-us pulse length; +/−20-MHz pump detunings test frequency selectivity.
Seven short scans are ordered sham/on/−20/sham/+20/on/sham, each with
500 shots per condition at 4.142, 4.140, and 4.138 GHz. Each arm has its
own single-shot readout calibration and fails after one acquisition error.
Compare the raw P0, P1, and survival populations after the run; a pump
response alone will not establish TLS identity. This opt-in pulse is inserted
only when the experimental runner supplies park-pump settings, and requires
passive reset. Production five-point defaults remain pump-free.

On the measurement PC after stopping other acquisitions:

```bash
git pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbePassiveParkPump --run
```

## First passive park-pump result and immediate localization follow-up

The seven-arm park-pump test completed September 27 at 14:31–14:32. Each
arm saved all three 4.138/4.140/4.142-GHz rows with 500 shots per condition.
The seven single-shot calibrations passed, with fidelity 0.749–0.814, below
the 0.862 calibration of the 14:16 wide scan. By the pump run, the 4.140-GHz
sham T1 estimates were 69.3, 30.7, and 60.8 us, much longer and less stable
than the 12.9-us wide-scan estimate. At 4.140 GHz, raw P0/P1-normalized
25-us survival was 0.732/0.429/0.712 across shams, 0.560/0.689 across
resonant-pump arms, and 0.554/0.514 across the −20/+20-MHz arms. The
variation among the shams exceeds the apparent pump contrast, and no
repeatable frequency-selective saturation is established. A 4.142-GHz sham
fit was invalid; comparisons should use the raw populations there.

The next experimental runner performs a passive 4.090–4.170-GHz pre-scout at
1-MHz spacing and 350 shots per condition, chooses a three-point loss dip
only when both flanks and scan directions show adequate contrast, then
runs the same seven-arm park-pump comparison at that selected coordinate.
A matching post-scout checks whether the dip moved or disappeared. The
pre-scout and pump are in one PC command, avoiding the 15-minute gap that
separated the first wide scan and pump test. If no localized dip passes the
checks, it stops before pumping and retains the pre-scout CSV. The seven
arm measurements and post-scout are also retained if a later stage fails.

On the measurement PC after stopping other acquisitions:

```bash
git pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeAdaptiveParkPump --run
```

## Adaptive park-pump result and matched drift control

The September 27 adaptive sequence completed. The pre-scout at 14:38:58
selected a localized loss feature at 4.131 GHz (25-us survival depth 0.366;
both scan directions passed). At that coordinate the pre-scout fitted
T1=16.9 us. Seven pump/sham arms ran from 14:40:07 to 14:40:49, followed by
a post-scout at 14:40:56. The post-scout selected 4.138 GHz and found
T1=6.6 us there: the strongest loss moved by about 7 MHz over the sequence.
The readout contrast also changed. At 4.131 GHz, normalized 25-us survival
was 0.154, 0.305, 0.500 in the three shams and 0.398, 0.489 in the two
nominally resonant pump arms. The rising final sham and migrating loss feature
prevent a pump-specific saturation claim. The drive is applied at the parked
qubit bias, so this null/ambiguous result cannot establish whether a TLS would
respond to an on-target pump.

The next control repeats the same pre-scout, seven short arms, and post-scout,
but sets every park-pump gain to zero. This measures spontaneous feature
motion over the same timing and recalibration cadence before attributing the
shift to microwave drive. All files have a distinct `Drift_Control` suffix;
the existing driven command and production TLS defaults are unchanged.

On the measurement PC after stopping other acquisitions:

```bash
git pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeAdaptiveParkPump --run --drift-control
```

The matched pump-off control completed at 16:51–16:54. Its 81-point pre-scout
selected 4.137 GHz with depth 0.479, and the post-scout selected 4.140 GHz
with depth 0.466. This 3-MHz shift in the *selected loss coordinate* happened
with every pump gain set to zero; the broad dip does not establish that one
microscopic TLS physically moved by exactly 3 MHz. At 4.137 GHz the seven
sham arms had normalized 25-us survival
0.363/0.265/0.322/0.531/0.323/0.275/0.440, a 0.266 span without microwave
drive. P1 stayed roughly 0.63–0.70 in those arms, so the variation is not
explained solely by a collapsing excited reference. The earlier driven-run
resonant survival values (0.398 and 0.489 at 4.131 GHz) fall within this
control's sham spread, though these are different runs at different selected
coordinates. No selective pump saturation has been demonstrated.

The next comparison measures the whole loss band in each arm instead of only
three fixed probe coordinates. A fresh 81-point passive scout chooses a center,
then 41-point scans cover center ±20 MHz with equal-duration sham/pump/sham
arms (gain 0/3000/0, 15-us tone at park). A post-scout checks where the loss
lies afterward. This 1-MHz band scan permits comparison of the loss profile
and integrated dip even if the selected center shifts by a few MHz. It keeps
the established correction and passive reset; a positive result would still
require a frequency-selectivity check before calling it TLS saturation.

On the measurement PC after stopping other acquisitions:

```bash
git pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeBandComparison --run
```

The band comparison completed at 17:01–17:06. Both 81-point scouts selected
4.138 GHz (pre depth 0.366, post depth 0.447). All three 41-point arms
completed over 4.118–4.158 GHz with 350 shots per condition. Define normalized
25-us survival at each frequency as `(Ps_25us-P0)/(P1-P0)`. With the outer
4.118–4.125 and 4.151–4.158 GHz points as flanks and 4.133–4.143 GHz as the
central loss region, the mean flank-minus-center dip depths were **0.4250,
0.4248, 0.4294** for sham/pump/sham. Thus the 15-us, gain-3000 park-bias
pump at 4.138 GHz did not measurably suppress the loss feature. The center
coordinate was unchanged to the 1-MHz scout grid before and after the block.
The pumped arm raised raw P0 and P1 somewhat over both shams across the band,
so a single-frequency raw-population difference would be misleading. This is
a null for this pump placement, duration, gain, and current device state; it
does not rule out a qubit-mediated on-target pump or identify the loss as a TLS.
Do not repeat the same park-pump protocol without a new physical control or
changed preparation mechanism.

## Higher-gain bidirectional park-pump screen

The gain-3000 band comparison measured only excited-qubit loss. That observable
alone cannot test whether a pumped TLS changes the balance of downward and
upward transfer: equal changes in opposite directions can leave the normalized
decay rate unchanged. The next bounded screen doubles the park-tone DAC gain
to 6000 for the same 15-us pulse, and measures both probe preparations. It
uses the pinned compensated flux excursion and passive reset; no active-reset
classifier is involved. The experimental runner caps gain at 6000.

An 81-point pump-off pre-scout selects the current localized loss. Eight 21-point
scans over center ±20 MHz then run in the order sham-g/e, gain-3000-g/e,
gain-6000-g/e, sham-g/e. This compares the new higher gain with the old gain
in the same device state. Each frequency uses 350 shots for P0, P1, and a 25-us survival
condition beyond the 0.1-us matched reference hold. The ground survival shot
omits the park pi pulse; its `Ps_25us-P0` is saved as ground excitation and no
T1 is fitted for it. The excited scan retains the original pi preparation and
the same raw P0/P1/Ps measurements. A post-scout checks feature position.
Pump-specific changes must be localized in frequency and exceed both bracket
shams. Analyze the ground probe as `G=Ps_25us-P0` and the excited probe as
`L=P1-Ps_25us`; subtract the mean flank value of each before comparing gains.
A putative populated TLS would give more target-localized upward transfer `G`
and less downward transfer `L` as gain rises. A suggestive result then needs a
matched off-resonant pump control.

On the measurement PC after stopping other acquisitions:

```bash
git pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeHighGainBidirectional --run
```

The higher-gain bidirectional run completed at 17:31–17:35 on September 27.
Both 81-point scouts selected 4.140 GHz (pre/post dip depths 0.378/0.406).
All eight 21-point arms completed. For each arm, the target region is
4.136–4.144 GHz and the flanks are 4.120–4.128 plus 4.152–4.160 GHz. Define
the target-localized raw ground excitation as center-minus-flank of
`Ps_25us-P0`; its values for sham, gain 3000, gain 6000, final sham were
**0.0037, 0.0040, 0.0000, 0.0077**. There is no gain-dependent upward
transfer. The corresponding localized excited-qubit loss
`P1-Ps_25us` was **0.0997, 0.0491, 0.0500, 0.0480**. The first sham was the
outlier; gain 3000, gain 6000, and final sham agree. At the target center,
the first-sham excited P1 was 0.319 versus 0.267/0.271/0.263 later, while
the long-hold Ps stayed around 0.16–0.17. The apparent decrease in loss is
thus driven substantially by a changing reference, not a reversible
gain-dependent pump effect. The final ground-sham P1 also transiently rose
to 0.504, then returned to 0.263 in the next excited-sham arm. These
reference variations preclude a subtle saturation claim. The gain-6000
park-tone test is negative at its present sensitivity; the loss feature
itself remains reproducible.

## Near-maximum park-tone frequency-control screen

At the user's request, the next bounded screen tests a much stronger tone,
up to DAC gain **30000** (below the program's 32767 limit). The selected
loss coordinate comes from a fresh 81-point passive scout; the qubit remains
parked near 4.367 GHz during each 15-us tone. The screen first measures
zero-gain shams, then gain 12000 at the selected frequency, then another
sham. It next uses equal gain 30000 at −40, 0, +40, and 0 MHz detuning, and
ends with a sham and post-scout. Every arm contains ground and excited probe
preparations on the same 21-point target-flux grid, with 2- and 25-us
additional holds and 350 shots per condition. An arm stops the sequence if
the frequency-median P0 exceeds 0.20 or P1−P0 falls below 0.15. This is a
reference and gross-excitation guard, not a calibrated microwave power or
component-temperature limit.

The controls are essential because the earlier excited-loss change persisted
in the final sham, and the first sham's reference was anomalous. A narrow,
repeatable response at zero detuning that is absent at ±40 MHz and in shams
would warrant a focused follow-up. Broad response, reference collapse, or a
null at gain 30000 would argue against further escalation of this *park-tone*
mechanism. This still does not drive the qubit at the loss flux coordinate;
a negative result does not rule out qubit-mediated TLS pumping.

On the measurement PC after stopping other acquisitions:

```bash
git pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeNearMax --run
```

The near-maximum screen completed all 16 arms at 18:32–18:39. The guard
passed throughout: frequency-median P0 stayed 0.063–0.109, and median
P1−P0 stayed 0.360–0.437. The pre/post scouts selected 4.136/4.134 GHz,
with localized dip depths 0.502/0.454. The strong loss remained visible,
but moved about 2 MHz during the block. An analysis that only watches the
original 4.136-GHz bin therefore overstates loss suppression.

For a shift-tolerant comparison, take the mean normalized 25-us loss
`(P1-Ps_25us)/(P1-P0)` over 4.128–4.138 GHz and subtract the mean over
4.116–4.124 plus 4.148–4.156 GHz. The gain-30000 sequence gave **0.421**
at −40 MHz, **0.437** on-frequency (first), **0.351** at +40 MHz, and
**0.378** on-frequency (second); the final sham gave **0.387**. On-frequency
pumping did not consistently suppress the dip relative to equal-gain
off-frequency controls. The analogous target-localized normalized 2-us
ground-excitation contrasts were **+0.019, −0.015, −0.010, +0.023** in the
same order. They change sign between the two on-frequency runs. This is
not a reproducible reciprocal pump response. Both scan directions also
show substantial within-arm variation at the high gain. The conclusion is
specific to a tone delivered while q3 is parked roughly 227 MHz from the
loss coordinate; it does not rule out an on-target, qubit-mediated pump.

The next experiment stays on the pump-probe path: determine a *loading time*
for moving a prepared qubit excitation into the feature. A fresh 81-point
scout selects the current coordinate. Four 25-point passive maps span that
center ±12 MHz at 1-MHz spacing with 400 shots per condition. They use
additional target holds of 0.25/0.5/1, 1.5/2.5/4, and 6/10/20 us beyond
the 0.1-us matched reference; the earliest panel is repeated at the end,
followed by a post-scout. The existing pi pulse, corrected flux excursion,
and readout are unchanged. Analyze raw P0/P1/Ps and both scan directions for
a reproducible nonmonotonic swap minimum or, if loss is monotonic, a useful
transfer time. That time will set the subsequent hot/cold, on/off-target
loading and signed return probes; a time-domain dip alone is not TLS proof.

On the measurement PC after stopping other acquisitions:

```bash
git pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeOnTargetTiming --run
```

The September 27 timing run completed its pre/post scouts and all four
panels. The scouts selected 4.134 and 4.135 GHz, respectively. Averaging
normalized survival `(Ps-P0)/(P1-P0)` over 4.132–4.136 GHz gives 0.762,
0.696, and 0.442 at additional holds of 6, 10, and 20 us. The nearby
4.120–4.124-GHz flank gives 0.895, 0.928, and 0.825. The early and repeated
early panels show no stable oscillatory minimum at 0.25–1 us. A 20-us target
visit is consequently a useful **incoherent loading pilot**, not an observed
coherent swap time or evidence that a TLS has been excited.

The follow-up uses the prepared qubit as its pump. After the 20-us target
visit and complete 40-us corrected return, it reads out the qubit once,
waits for the readout accumulator, prepares a ground or excited probe, visits
the target for 2 us, and reads out again. Raw IQ for both readouts is saved
shot by shot. Offline analysis selects first-readout ground shots, then
compares hot/on-target loading with cold/on-target and hot/off-target
controls. The first and second readouts each have paired ground/excited
references before and after the science arms; the second-readout excited
reference is itself selected on first-readout ground. This sequence does not
use the unreliable active-reset feedback decision. A null is limited by the
roughly 40-us return plus first-readout time before the return probe. A post
loss-feature scout records drift; shifts greater than 1 MHz mark the pilot
frequency-unstable rather than treating a null as evidence against return.

The first heralded attempt on September 27 stopped during its third reference,
before any science arm. Its fresh scout selected 4.124 GHz (the feature had
moved since the earlier timing map). The ordinary single-shot calibration just
before the scout had ground/excited fidelity `(0.943+0.896)/2 = 0.9195`.
However, the pilot's first-readout reference prepared an excited qubit *before*
the target excursion and 40-us return. That state can relax before it is read;
the resulting prepared-excited IQ distribution yielded apparent fidelity
0.711 and only 7.7% prepared-ground acceptance at a 2% lower-tail cutoff.
No pump/probe result can be inferred from this stopped run.

The reference arms now perform their calibrated pi (or zero-gain matched
pulse) **after** the complete flux return, immediately before the respective
readout. They therefore calibrate the state present at readout. Science arms
still prepare before their target visit, so the loading and return test is
unchanged. Raw paired IQ and the strict reference-quality guard remain in
place; a failing readout reference still stops the run before science data.

The retry's scout selected 4.123 GHz with depth 0.397 and SS-calibration
fidelity 0.911. Its post-return first-readout reference improved to fidelity
0.880, but the fixed 2% false-ground cutoff accepted only 15.5% of the
prepared-ground shots, below the pilot's 20% minimum. Again it stopped before
all science arms. Replaying the saved paired IQ with a **5% empirical
false-ground cap** accepts 52.5% of ground-reference shots for the first
readout (fidelity 0.880) and yields a second-readout reference with fidelity
0.819, ground acceptance 50.0%, and false-ground rate 4.7%. The revised cutoff
uses a discrete order statistic rather than an interpolated percentile, so it
never exceeds its 5% cap on the finite reference sample. It retains the
original readout and science pulse sequence; this is an exploratory pilot,
with the full raw IQ preserved for alternate threshold analysis. The 5% is an
in-sample cap, not a guarantee for future shots. Odd/even reference holdouts
must independently show at most 10% false-ground labeling before science
starts. On the saved retry IQ, the two held-out rates were 3.5% and 7.0%.
Post-run references are scored against the *frozen pre-run axes* without
refitting; an unstable post readout marks the completed science block as
readout-unstable. The manifest also records a one-sided 95% upper bound on
the measured false-ground rate to make finite-sample uncertainty visible.

The next retry's scout selected 4.129 GHz with depth 0.245, but an independent
200-shot excited reference scored 12% below the candidate herald cutoff, so
the run again stopped before its first science arm. The full 400-shot paired
reference still had first-readout fidelity 0.849, and the two disjoint
holdouts scored 2% and 12% false-ground. Quarter-by-quarter IQ means did not
show a clear time trend; the extreme-tail cutoff is unstable at this sample
size. After three reference-only aborts, the hard herald gate is no longer a
sound acquisition policy. The runner now records all hot/cold, on/off-target
science arms and paired raw IQ even if offline classification is uncertain.
It suppresses unvalidated online conditional claims and marks the completed
dataset readout-unstable unless pre and post references pass. This changes
data retention and interpretation policy, not the science pulse sequence.
Per-arm conditional probabilities remain provisional until the post readout
and feature scouts finish; they are nulled in the final manifest if either
control is unstable. The paired IQ files remain available for offline work.

On the measurement PC after stopping other acquisitions:

```bash
git pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeHeralded --run
```

The September 27 retry completed all 18 arms and saved 400 paired-IQ shots per
arm in `q3_pump_probe_heralded_20260928T035041Z_782f2184`. The independent
pre-run readout checks and frozen-axis post-run checks passed. The pre/post
scouts selected 4.132/4.130 GHz, so the runner conservatively marked the
feature unstable under its 1-MHz center-shift rule. The loss itself did not
disappear: at the fixed 4.132-GHz coordinate, normalized 25-us survival was
0.298 before and 0.402 after, versus 0.771 and 0.826 at the 4.118-GHz flank.
The 2-MHz change in selected minimum should not be interpreted as loss of the
feature or a measured TLS frequency jump.

For an offline descriptive estimate, project all paired IQ onto the *frozen*
pre-run axes, retain first-readout IQ below the confident-ground limit, and
classify final-readout IQ using the pre-run threshold. In the pooled two
repetitions, final excited counts after first-readout ground selection were:

| Probe preparation | Hot/on target | Cold/on target | Hot/off target | Hot-minus-cold |
| --- | ---: | ---: | ---: | ---: |
| Ground | 29/244 = 0.119 | 40/353 = 0.113 | 15/159 = 0.094 | +0.006 |
| Excited | 214/330 = 0.648 | 242/376 = 0.644 | 104/154 = 0.675 | +0.005 |

The naive shot-binomial 95% intervals for hot-minus-cold are approximately
[-0.047, +0.058] for the ground probe and [-0.066, +0.076] for the excited
probe. These are *not* uncertainty bounds for device drift or correlated
shots. The matched differences are also small within each repetition: ground
+0.017 and +0.001; excited +0.002 and +0.007. This is a null for a population
effect that survives the compensated return, first readout, and next probe.
It does not exclude shorter-lived TLS excitation or establish that the loss
feature is a TLS.

One repeated hot/on-target ground-probe arm had only 77/400 confident-ground
first readouts, versus 167/400 in its earlier nominally identical arm and
167/400 in the immediately preceding hot/on-target excited-probe repetition.
The settings match; the raw first-IQ distribution changed. This isolated
nonstationarity precludes a stronger pooled claim, but does not by itself
establish telegraph noise or identify its cause. A follow-up should interleave
hot/cold controls on a shorter timescale and move the second probe ahead of
the 40-us return/readout latency.

## Target-resident pulse calibration

The heralded sequence cannot test population lost during its approximately
40-us corrected return and first readout. Before a shorter-gap hot/cold
sequence, first verify that a microwave pulse can re-excite q3 **at the loss
flux coordinate**. The experiment-only `TLSPumpProbeResidentDrive` runner
finds the current feature with the same 81-point passive scout, then tests
Gaussian pulses 20 us into a single compensated target visit. It also tests
the 14-MHz lower flux flank. The pinned correction is checked to be flat
through the Gaussian drive window. The pulse occupies the middle of the visit;
the 40-us return occurs only after the pulse and a 0.1-us target dwell.
There is one park readout per shot, with no feedback reset or intermediate
readout. Ground/excited readout references are prepared immediately before
readout, both before and after the scan. Separate short-return controls
prepare the qubit excited **before** a 4-us target visit and verify that an
excitation remains distinguishable through the same return and readout.

At each site, seven drive detunings from -20 to +20 MHz use gains 1000, 3000,
6000, 12000, 20000, and 30000 DAC, bracketed by zero-gain waveforms of the
same duration. Each arm has 200 raw-IQ shots, saved separately under a
manifest. Representative reference and high-gain frequency-edge programs
are constructed before any acquisition. The post scout, frozen pre-run readout
axis, and short-return
controls check whether the result can be interpreted. A post-scout center
shift above 2 MHz or a loss depth below 0.15 marks the controls unstable;
the transfer control must retain at least 0.15 readout contrast before and
after the sweep. This is a drive calibration, **not** a TLS
saturation claim. Select a usable target pulse only after inspecting its
contrast, frequency dependence, zero-drive brackets, flank response, and
pre/post feature position. A drive null can still mean rapid relaxation from
the target after the pulse; the short-return control only bounds this ambiguity.
A later runner will interleave hot/cold loading
and probe within one target visit, removing the first readout and return
from the pump-to-probe gap.

On the measurement PC after stopping other acquisitions:

```bash
git pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeResidentDrive --run
```

The September 28 calibration completed all 120 arms in
`q3_pump_probe_resident_drive_20260928T041637Z_8faee4a6`. Both scouts
selected 4.133 GHz, with dip depths 0.381/0.420. The frozen readout axis
scored fidelity 0.885 before and 0.913 after. Short-return ground/excited
controls gave 0.115/0.495 before and 0.095/0.475 after, so a prepared
excitation remained visible through their target visit and return.

The drive response is narrow and tracks the flux-model qubit frequency:
the clearest response is **model frequency +5 MHz** at both the loss
coordinate and 14-MHz lower flank. With gain 6000, final classified excited
fractions at the feature were 0.285 versus bracketing zero-gain 0.095/0.090;
at the flank they were 0.265 versus 0.100/0.105. The unthresholded IQ
projection changes in the excited direction too. At gain 30000, the same
feature arm reached 0.390 versus 0.095/0.090, while the flank reached 0.270
versus 0.100/0.105. Gain 20000 was much less effective, consistent with a
nonmonotonic drive response; the high-gain contrast must not be interpreted
as saturation. Most other detunings have only small, fluctuating contrasts.
This establishes a usable **post-return qubit-drive signal** for the next
probe, not a TLS-specific pump effect. Use gain 6000 as the lower-power
primary probe, include gain 30000 as a sensitivity check, and retain
zero-gain and detuned controls. The short-return control cannot prove that
excitation created at target survives in exactly the same way; the science
run must compare its own short- and longer-hold arms.

## Target-resident hot/cold probe

The follow-up reuses the calibrated `ResidentDriveProgram` pulse sequence,
with a fresh 81-point feature scout. A park pi prepares the hot arm (a
zero-gain waveform prepares the cold arm). The qubit stays at the selected
flux for 20 us, receives a Gaussian pulse there, then remains there for
0.1, 2, or 6 us. It returns with the complete pinned 40-us correction and
is read out once. Thus the probe hold starts immediately after the target
microwave pulse, without the intervening first readout and return that
limited the heralded pilot.

For each hold, site, and two reversed repeats, hot/cold arms are adjacent.
The tone block is bracketed by two gain-zero shams, with an on-frequency
gain-6000 primary probe, a -10-MHz detuned gain-6000 control, and an
on-frequency gain-30000 sensitivity arm. The same sequence runs at the
14-MHz lower flux flank, with its microwave frequency tracking that
coordinate. There are 120 science arms of 400 shots each, plus pre/post
readout and short-return controls. Raw IQ is retained for every arm.
The runner checks the completed resident-drive calibration, constructs
representative QICK programs before acquiring, checks the flat corrected
drive window and full return, and makes a post scout. A >2-MHz selected
feature shift, weak feature, readout failure, or failed short-return
contrast marks the finished data controls-unstable. If the fresh pre-scout
feature is more than 5 MHz from the calibrated 4.133-GHz coordinate, the
runner stops before science acquisition and requests a new drive calibration.

Analyze each arm's full readout distribution and hot/cold changes in the
**incremental** 0.1-to-2 and 0.1-to-6-us loss, not just its final excited
fraction: hot loading can leave residual qubit excitation that the target
microwave pulse partly inverts. Require a response in both repeats that
survives zero-drive bracket drift, differs from the detuned tone, and is
stronger at the feature than the flank before calling it a candidate
pump-dependent loss change. A null here is substantially more informative
about short-lived memory than the heralded result, but still does not
exclude every possible TLS or prove the loss dip's microscopic origin.
The primary planned contrast is the hot-minus-cold difference in loss from
0.1 to 2 us at gain 6000, corrected by the mean local zero-drive sham and
then by the same quantity on the flank. A negative result would have the
sign expected if hot loading reduces subsequent target loss. The 6-us and
gain-30000 arms are sensitivity checks, and the detuned drive must not
produce the same selective effect. Inspect the two repeats separately
before pooling them.

On the measurement PC after stopping other acquisitions:

```bash
git pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeResidentProbe --run
```

The first short-gap run completed 128/128 arms in
`q3_pump_probe_resident_probe_20260928T043204Z_c978173b`. The pre/post
scouts selected 4.128/4.129 GHz with depths 0.318/0.335, so the feature
persisted through the experiment. Frozen-axis reference fidelities were
0.854 before and 0.905 after; the short-return ground/excited controls
were 0.113/0.595 before and 0.070/0.633 after. All recorded NPZ shots
are present, and the saved classifications match recalculation from raw IQ.

For the planned 0.1-to-2-us hot-minus-cold loss contrast, after subtracting
the mean of the two zero-drive shams and then the flank, gain 6000 at +5 MHz
gave **+0.314 and +0.195** in the two repeats. This is repeatable but has
the **opposite sign** from the simple saturation hypothesis, in which hot
loading would reduce subsequent loss. The -10-MHz gain-6000 control also
gave +0.159 and +0.105; gain 30000 gave +0.166 and -0.013. Raw-IQ
projections confirm the gain-6000 short-gap change in both repeats, so it
is not created by the classifier threshold. However, the zero-drive short
hold still retains appreciable hot-minus-cold qubit excitation (roughly
0.12-0.17 at the feature and 0.50-0.57 at the flank). The resident drive
can rotate that residual population. These data establish a candidate
pump-dependent response, **not** TLS saturation or single-TLS memory.

## Loading-time check for the residual-qubit confound

The next bounded run repeats the target-resident sequence after either a
20- or 80-us visit before the microwave pulse. It keeps matched hot/cold
preparation, 0.1/2-us post-drive holds, gain-zero brackets, the +5-MHz
gain-6000 drive, the -10-MHz gain-6000 control, and the 14-MHz lower flank.
Both sites and both loading times run twice in reversed order: 128 science
arms at 400 raw-IQ shots each, plus the same pre/post references and feature
scouts. The drive window is checked against the pinned flux correction at
both loading times before acquisition. The nominal 80-us correction is flat
through the drive window and retains the complete 40-us return.

First compare the *zero-drive* short-hold hot-minus-cold population at 20
and 80 us. If it has not appreciably converged at 80 us, this check cannot
separate residual qubit excitation from bath memory. If it converges, ask
whether the on-tone incremental-loss contrast remains while the detuned and
flank controls do not; inspect both repeats and unthresholded IQ. Even a
selective effect would remain evidence for a pump-dependent loss mechanism,
not proof of a microscopic TLS.

On the measurement PC after stopping other acquisitions:

```bash
git pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeResidentProbe --run --loading-time-check
```

The loading-time run acquired all 136 arms in
`q3_pump_probe_loading_time_20260928T044344Z_e4999f87`. Its frozen readout
fidelity was 0.904 before and 0.891 after; short-return ground/excited
controls were 0.135/0.608 before and 0.075/0.568 after. Every NPZ has the
expected 400 shots, and raw-IQ classifications reproduce the manifest.
The loss feature remained visible, but its selected center changed from
4.128 to 4.125 GHz during the run, exceeding the 2-MHz stability gate.

More seriously, the zero-drive hot control at the feature fluctuated
between short adjacent arms: at 20-us loading in the first repeat it fell
from 0.585 to 0.238 excited fraction between the two sham brackets, roughly
two seconds apart. At 80-us loading, the first repeat's sham hot fractions
were 0.040/0.118, whereas the second repeat's were 0.398/0.430. Each 400-shot
arm is internally much steadier in 40-shot bins than these differences
between arms, and the cold controls and readout references did not show a
comparable collapse. Consequently the 20-to-80-us result is not a reliable
TLS-memory test: neither an apparent convergence nor a pooled on-tone
contrast survives the rapidly changing loss baseline.

## Pump carryover check

The next test asks a narrower question suggested by the inconsistent sham
brackets: does a driven block reproducibly change the *following* zero-drive
hot survival at the same flux, or do similar changes occur after an undriven
block? The experimental `--carryover-check` mode performs six short cycles
of feature/flank groups. Each group measures zero-drive ground and excited
baselines, then 100 hot pump shots, then zero-drive excited and ground
baselines. Pump groups rotate among gain-zero sham, +5-MHz gain-6000, and
-10-MHz gain-6000; all six tone permutations occur once and site order
alternates. A five-second park recovery separates groups, and its actual
duration is logged. The measured pre-baselines of the three tone groups at
each site/cycle must agree within 0.20 excited-fraction units for the data
to pass the stability gate; a fixed wait alone does not prove recovery.
Each arm also records the start and end of the actual QICK acquisition so
the pump-to-post interval can be reconstructed separately from file writes
and program construction.
All arms use the same 20-us target visit, 0.1-us post-pulse hold, full
corrected return, and one readout per shot. There are 180 science arms at
100 shots each, plus 400-shot pre/post readout and transfer controls. Eight
fresh 200-shot ground-drive checks at the actual feature and flank bracket
the on-tone and detuned pulses with gain-zero shams. Science acquisition
starts only if on-tone gain 6000 produces at least 0.10 excess excitation,
the detuned pulse stays within 0.10 of sham, and the sham bracket stays
within 0.10 at both sites; these checks are washed out before science. The
frozen IQ axis, raw shots, pre/post feature scouts, and exact arm order are
saved. The feature must fall within the interval in which the prior
calibration actually demonstrated gain-6000 drive contrast (4.119-4.133
GHz). The flank can fall outside that interval, which is why its fresh
drive check is mandatory.

For each group, compare the post-minus-pre change in hot-minus-cold sham
survival. A pump-induced effect requires a repeatable change after on-tone
blocks beyond the sham and detuned blocks, with an appropriate flank
control and stable readout. Even then, seconds-scale carryover alone would
not establish a microscopic TLS. A null would identify the prior bracket
divergence as a baseline nonstationarity to handle by faster interleaving
or feature tracking, rather than justify pooling the earlier pump-probe
arms.

On the measurement PC after stopping other acquisitions:

```bash
git pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeResidentProbe --run --carryover-check
```

The carryover run acquired all 196 arms in
`q3_pump_probe_carryover_20260928T045929Z_00d31985`. Both scouts selected
4.129 GHz with dip depths 0.294/0.302. Pre/post readout fidelities were
0.895/0.880, and short-return controls retained excited-minus-ground
contrast of 0.465/0.475. Fresh gain-6000 drive checks passed at both actual
sites: on-minus-sham was +0.173 at the feature and +0.185 at the flank,
while the detuned excess was +0.013/0.000. All raw IQ files contain the
requested shots and reproduce the manifest classifications. The QICK
pump-to-post acquisition gap was 0.060-0.135 seconds; the logged inter-group
recovery was at least 5.0 seconds.

The feature's pre-pump hot-minus-cold baseline remained within the 0.20
spread gate in cycles 0-2 but failed in cycles 3-5 (within-cycle spreads
0.35, 0.37, and 0.42). Sham groups themselves sometimes changed markedly
from pre to post. In the three stable cycles, the mean on-tone post-minus-pre
change relative to the mean sham/detuned change was +0.055 at the feature
and +0.045 at the flank. This tiny feature-minus-flank difference (+0.010)
does not support a selective, seconds-scale on-tone carryover. The full
six-cycle result is controls-unstable and cannot be used to claim a null or
positive microscopic TLS result. The rapid baseline changes remain the
dominant obstacle to interpreting separate-arm pump-probe comparisons.

## Shot-alternating sequencing pilot

The next step puts the four primary conditions inside one QICK program:
ground/sham, excited/sham, ground/+5-MHz gain-6000, and excited/+5-MHz
gain-6000. Each logical hardware shot executes all four complete resident
visits, corrected 40-us returns, and individual readouts, separated by the
same 500-us inter-shot delay. Two 200-shot programs use forward and reverse
condition order. The 4-IQ-per-shot stream is split by the recorded order,
with raw IQ saved per condition. Fresh scouts and pre/post readout and
short-return references bound drift. The program is constructed for both
orders before the first readout. This small pilot validates the QICK stream,
drive contrast, and order dependence. Success also requires at least 0.10
hot-minus-cold contrast in each 20-us sham condition. It is not yet a loss-vs-hold scan or
a TLS saturation result. If it works, extend the same shot-level alternation
to short/long holds, detuned control, and the flank.

On the measurement PC after stopping other acquisitions:

```bash
git pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeShotAlternating --run
```

The first pilot attempt made only its passive scout. It selected a clear
new loss feature at 4.144 GHz (depth 0.306); the previous 4.129-GHz feature
was no longer prominent. The pilot stopped before any resident-drive
acquisition because 4.144 GHz lay outside the old drive calibration's
4.119-4.133-GHz interval. This is an expected safety stop, not a failed
QICK stream. The pilot now keeps the old calibration's verified pulse and
correction settings but performs four fresh 200-shot ground-drive checks
at the newly selected feature: sham, +5-MHz gain-6000, -10-MHz gain-6000,
and sham. It starts shot-alternating acquisition only if the on-tone
response exceeds the local sham by at least 0.10, the detuned response
remains within 0.10, and the sham bracket stays within 0.10. Raw check IQ
is saved; a five-second washout separates the check from the pilot.

The subsequent pilot at `q3_pump_probe_shot_alternating_20260928T052601Z_c3f80105`
completed both QICK stream orders and saved all 1,600 interleaved IQ records.
The fresh feature was 4.129 GHz; pre/post dip depths were 0.360/0.293.
The local gain-6000 drive check passed: gain-6000 excess +0.175, detuned
excess +0.040, and sham-bracket drift 0.020. The pre/post readout references
and short-return transfer controls also passed. In the forward order,
sham ground/excited fractions were 0.080/0.270 and driven ground/excited
fractions were 0.280/0.320. In reverse order, those fractions were
0.115/0.205 and 0.265/0.305. Thus cold-drive contrast persisted in both
orders (+0.200/+0.150), while the 20-us sham hot-minus-cold contrast was
0.190 forward and 0.090 reverse. The latter misses the prespecified 0.10
gate, so the pilot status is `complete_controls_unstable`. The QICK stream
works; this still cannot be interpreted as TLS saturation.

The next check holds everything else fixed but compares 4, 8, 12, and 20-us
target visits before the resident drive. Each visit gets forward and reverse
200-shot four-condition programs, with the same raw IQ, local drive check,
readout references, corrected 40-us return, and pre/post loss scouts.
Shorter visits should preserve more of the prepared hot state. A usable
loading time needs at least 0.10 hot-minus-cold sham contrast and 0.10
ground-state drive contrast in both orders, with no large order disagreement.
This check selects timing for a subsequent short/long-hold, detuned and flank
comparison; it is not itself a TLS-memory test.

On the measurement PC after stopping other acquisitions:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeShotAlternating --run --loading-check
```

The first loading-time attempt, `q3_pump_probe_shot_alternating_loading_20260928T053650Z_8db3dbff`,
stopped after the four preliminary drive checks and before any of the eight
shot-alternating programs. It selected a 4.131-GHz loss feature (depth 0.431)
and had a valid pre-run readout axis (fidelity 0.903). The 8-us gain-6000
check produced excited fractions 0.065/0.135/0.105/0.080 for sham/on/detuned/sham,
so on-tone excess was only 0.063 against the required 0.10. The 8-us drive
check alone cannot answer which loading time supports both hot preparation
and resident drive. For this timing diagnostic only, a weak preliminary
check is now recorded but does not abort the scan. Each of the eight programs
directly measures its own ground-state drive and sham hot-minus-cold contrast;
the final usable-time gate still requires both to pass in both shot orders.
The original two-program pilot retains its strict preliminary drive gate.

On the measurement PC:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeShotAlternating --run --loading-check
```

The completed loading-time run is
`q3_pump_probe_shot_alternating_loading_20260928T054034Z_4b1e77d5`.
Both scouts found the same loss feature within 1 MHz (4.131/4.130 GHz),
with depths 0.472/0.389. Pre/post readout fidelities were 0.898/0.875;
short-return hot-minus-cold controls were 0.443/0.420. All 6,400 program
IQ records are present and reproduce the saved classifications. The local
8-us preliminary drive check was weak (on-tone excess 0.015), and the
eight-program scan explains why: at 4 and 8 us, sham hot-minus-cold
contrasts remained 0.35-0.41 and 0.31-0.38, but cold-drive contrasts were
between -0.03 and +0.07. At 12 us the drive contrast was also inconsistent.
At 20 us, both orders passed the prespecified gates: sham hot-minus-cold
0.195/0.125, cold-drive contrast 0.190/0.105, and hot-minus-cold drive
change -0.140/-0.030. These are timing-control results, not evidence of
TLS saturation. The need for a longer wait may reflect the target flux
or qubit frequency settling; this scan alone cannot distinguish that from
other drive-calibration changes.

The next run uses the 20-us visit and 400 logical shots per program. Sixteen
shot-alternating programs cross feature/flank, 0.1/2-us post-drive holds,
+5-MHz gain-6000/-10-MHz gain-6000 tones, and forward/reverse order. Each
program measures sham and driven hot/cold shots in one QICK stream; all raw
IQ is saved. Eight fresh drive checks at the actual feature and flank are
recorded, but program-level controls determine usability so one noisy
preliminary check cannot terminate the comparison. The prespecified effect
is the driven-minus-sham hot/cold loss between 0.1 and 2 us, subtracting
the detuned and flank responses separately in each order. Readout,
short-return, feature-stability, on-tone response, detuned response, and
sham-baseline agreement gates remain explicit in the manifest at both holds.
The 2-us sham hot contrast must remain at least 0.05 to avoid a floor, but
the driven 2-us contrast may decay. A selective effect would be a candidate
bath response, not proof of one TLS.

On the measurement PC after stopping other acquisitions:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeShotAlternating --run --loss-check
```

The loss comparison completed all 16 programs in
`q3_pump_probe_shot_alternating_loss_20260928T055734Z_99fd68d3`.
The feature persisted at 4.130/4.129 GHz, with dip depths 0.301/0.335;
pre/post readout fidelities were 0.900/0.910. Both actual-site preliminary
gain-6000 drive checks passed (on-tone excess +0.120 feature, +0.148 flank),
and the transfer controls passed. All 25,600 science IQ records are present
and reproduce the saved classifications. The prespecified feature-specific,
tone-selective short-minus-long loss contrast was +0.195 forward and +0.110
reverse. Within-program 20-shot block resampling gave approximate 95% ranges
of [-0.040,+0.428] and [-0.115,+0.333] for the classified outcomes, before
allowing for drift between programs. Unthresholded-IQ versions were +0.223
and +0.059, also with ranges covering zero. The run's status is
`complete_controls_unstable`: the reverse feature short-hold on-tone
ground-drive contrast was +0.080, below the 0.10 gate.

More importantly, the feature sham hot-minus-cold baseline in the forward
on-tone programs rose from 0.150 at the 0.1-us hold to 0.368 at the 2-us
hold. Physical relaxation alone cannot produce that rise. Those holds were
separate QICK programs about a second apart, so fast baseline motion can
contaminate their difference. The repeated positive sign is interesting but
does not establish a pump-induced loss change or TLS saturation.

The next sequence puts both holds in each logical QICK shot. Each program
has eight complete resident visits and readouts: four sham/driven x hot/cold
subshots at 0.1 us and four at 2 us. A reverse program flips both hold and
condition order. Feature/flank and on-tone/detuned still require separate
programs, giving eight 400-shot programs total, with the same raw-IQ,
readout, transfer, scout, and control checks. This shortens the hold-pair
comparison from seconds to milliseconds and directly tests whether the
previous contrast survives better alternation. It remains a candidate bath
response measurement, not a single-TLS identification.

On the measurement PC after stopping other acquisitions:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeShotAlternating --run --hold-alternating
```

The completed hold-alternating run is
`q3_pump_probe_hold_alternating_loss_20260928T061232Z_b39cdba0`. The loss
feature remained strong: the pre/post scouts selected 4.136/4.137 GHz with
depths 0.301/0.440. Readout fidelity was 0.904/0.903, both fresh site-drive
checks passed, and the transfer references remained usable. The predeclared
feature-specific, tone-selective short-minus-long contrast was **-0.118**
forward and **+0.005** reverse, rather than the earlier separate-program
+0.195/+0.110. The forward feature 0.1-us on-tone cold-drive contrast was
+0.0775, below its 0.10 gate; the run status is
`complete_controls_unstable`. A shot-paired bootstrap of the two-order mean
gave approximately [-0.21,+0.10] for the classified outcome. The earlier
positive hint did not reproduce with stronger hold alternation. These runs
were at selected features 4.130 and 4.136 GHz, so the comparison does not
prove why the effect changed or settle the microscopic TLS identity.

The next stage tests fast-flux delivery before trying modulation-assisted T1.
`TLSFluxModulationCalibration` first scouts the current loss feature, then
performs sideband spectroscopy at its 14-MHz lower flank. A 0.8-us arbitrary
fast-flux waveform containing 24 cycles near 30 MHz is synchronized with the
existing gain-6000 Gaussian qubit probe. The waveform has the corrected DC
target bias plus 0, 800, or 1600 DAC of AC amplitude. A 17-point unmodulated
carrier scan locates the actual qubit resonance; then fifteen frequencies
cover carrier and ±30-MHz first-sideband windows for each amplitude. Adjacent
amplitude arms reverse order between frequency points. The full corrected
40-us return precedes every park readout. Pre/post ground/excited references,
a repeated carrier, and pre/post loss scouts check drift; raw IQ and compiled
waveform samples are saved in a manifest. The script rejects DAC clipping,
waveform-memory overflow, a correction window that is not flat, and a weak
or edge-selected carrier. It does not claim a TLS response or a T1 benefit.
The sidebands will determine whether the line delivers a useful AC swing and
which amplitude to try in a later modulated-T1 comparison.

On the measurement PC after stopping other acquisitions:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSFluxModulationCalibration --run
```

The calibration completed at
`q3_flux_modulation_calibration_20260928T063011Z_63ebbcfd` with status
`complete`. The loss feature remained at 4.136/4.135 GHz (pre/post depths
0.405/0.510). The corrected flank was 4.122 GHz. The pre/post park-readout
fidelities were 0.915/0.884, and the unmodulated carrier was 4.126 GHz,
with initial/repeated excess excitation 0.304/0.248. The compiled flux
waveform had 5,504 samples, 24 complete cycles in 0.79985 us at 30.0056 MHz,
and a safe -17,742..-14,542 DAC range for the 1,600-DAC flank arm.

The calibration spectra show a substantial AC response. At the carrier,
classified excited fraction was 0.397 (AC off), 0.222 (800 DAC), and 0.135
(1,600 DAC). At 4.094 GHz, the corresponding fractions were
0.105/0.212/0.183, and at 4.154 GHz they were 0.092/0.180/0.150. The
projected raw-IQ means change in the same directions. These are nearly
symmetric first-sideband responses about the carrier, though the maxima
shift by about 2 MHz from nominal ±30-MHz positions; the 1,600-DAC peak may
lie partly outside the five-point sideband window. The strong carrier
suppression does not by itself give an exact in situ modulation amplitude or
prove that the target loss feature will be suppressed.

The next bounded test interleaves AC off/on within each logical QICK shot.
Each of eight 4,000-shot programs has short/6-us target holds crossed with
off/on modulation and park-prepared ground/excited states, in forward and
reverse orders at the fresh feature and its 14-MHz lower flank. The on arms
use 800 or 1,600 DAC AC waveforms whose slowly varying DC baseline follows
the pinned correction; off arms play that correction without the sinusoid.
Every subshot receives a complete corrected 40-us return before readout.
The runner sets the compiled park-ramp envelope to 1 us so two ramp
envelopes plus both AC holds fit q3's 65,536-sample generator memory. The
resident sequence uses hard flux steps and does not play those park ramps;
the AC on/off arms share the same actual park and target timing. A preflight
records the full envelope-memory accounting before any acquisition.
The predeclared effect is the modulation-induced change in hot-minus-cold
survival from 0.1 to 6 us, then feature-minus-flank. Ground response,
preparation contrast, readout, transfer, and feature-stability controls
remain explicit. A selective response is only a candidate bath effect, not
proof of one TLS or a microscopic saturation mechanism.

On the measurement PC after stopping other acquisitions:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSFluxModulatedT1 --run
```

The first modulated-T1 comparison completed at
`q3_flux_modulated_t1_20260928T064334Z_87403532`. All eight 4,000-shot
programs and raw IQ files are present. The pre/post scouts found a strong
loss feature at 4.131/4.127 GHz (depths 0.290/0.335), a 4-MHz shift that
fails the prespecified 2-MHz stability gate. Readout fidelity was 0.895
before and 0.879 after; transfer and all eight within-program hot/cold,
ground-response controls passed. The final status is
`complete_controls_unstable` because of the feature shift.

The classified feature-minus-flank, AC-induced change in hot-minus-cold
survival from 0.1 to 6 us was +0.044/-0.0495 in forward/reverse order at
800 DAC and +0.0598/+0.0200 at 1,600 DAC. Shot-paired 95% bootstrap
intervals for the latter were approximately [+0.011,+0.107] and
[-0.025,+0.067]. After normalizing continuous IQ by the pre-run ground/e
reference separation, the 1,600-DAC feature-specific values were
+0.0625/+0.0032. Thus 800 DAC reverses sign and the 1,600-DAC response
weakens substantially in the reverse repeat. This is an interesting
calibrated-AC delivery experiment, but not a reproducible suppression of
TLS-mediated loss.

The next focused repeat keeps only 1,600 DAC and uses 8,000 logical shots
per program. After the forward feature/flank pair it performs a fresh
81-point loss scout and retargets the reverse flank/feature pair to the
newly selected frequency. A final scout gives a stability check for each
pair separately. The original off/on, short/long, ground/excited conditions
remain interleaved within each hardware shot, and the corrected 40-us
return still precedes readout. This tests whether the small first-pass
1,600-DAC effect reproduces at a tracked feature; it does not infer TLS
identity from modulation alone.

On the measurement PC after stopping other acquisitions:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSFluxModulatedT1 --run --focused
```

The focused run completed at
`q3_flux_modulated_t1_20260928T065416Z_8526a431`. All four 8,000-shot
programs and raw IQ files are present; readout fidelity was 0.896/0.878,
and all four within-program preparation/ground-response controls passed.
The pre/mid/post global selectors returned 4.144/4.129/4.126 GHz, so both
selector-stability gates failed. Inspection of the full scout curves shows
two coexisting features: the upper 4.143–4.145-GHz dip persists in all three
scans, while a lower 4.126–4.131-GHz dip also persists and becomes deeper.
The 15-MHz selection jump therefore cannot be called a physical shift of
one TLS. The first pair's nominal 4.130-GHz lower control fell into the
second loss feature, invalidating it as a clean flank.

The within-feature 1,600-DAC modulation-induced change in hot-minus-cold
survival from 0.1 to 6 us was only +0.0069 at 4.144 GHz and +0.0085 at
4.129 GHz (shot-paired standard errors about 0.013 each). The normalized
continuous-IQ versions were +0.0035 and +0.0132. The second pair's
feature-minus-control +0.0496 was driven mostly by a -0.0411 response at
the 4.115-GHz control, not a feature-local suppression. Thus this 30-MHz,
1,600-DAC, park-prepared modulation protocol did not reproducibly suppress
the measured loss. The earlier marginal 1,600-DAC hint is not confirmed.

The next experiment sets aside the saturation protocol and probes direct
time-domain exchange. A fresh passive scout identifies the persistent
upper loss feature within 4.142–4.146 GHz and checks that the +14-MHz
upper control is clean. A park pi prepares excited versus matched ground
shots; the qubit visits the candidate or control flux for eleven dwell times
from 0.1 to 6 us, returns with the full 40-us correction, and is read out
once. Forward and reversed dwell/site/state order, pre/post readout and
transfer references, early contrast gating, and a post-scout anchored to
the *same* upper feature protect against the selector switching between
the two dips. All 88 arms use 600 raw-IQ shots. A reproducible nonmonotonic
time trace localized to the feature would motivate a denser swap chevron;
the shortest points include flux settling and are not by themselves proof
of coherent exchange. This follows the standard qubit–defect swap protocol
used, for example, in
https://pubmed.ncbi.nlm.nih.gov/25652611/ .

On the measurement PC after stopping other acquisitions:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSwapHoldPilot --run
```

The first swap-hold attempt stopped after its pre-scout
`q3_03_06_27_TLS_SwapHold_Pilot_Scout_pre_T1_5pt_vs_wall_clock_full.csv`;
it made no science manifest and applied no swap-hold pulses. The anchored
4.144-GHz feature was no longer sufficiently deep, while the lower loss
feature near 4.127–4.129 GHz remained strong. The revised selector first
tests the upper family, then falls back to the lower family with a control
14 MHz below it; the post-scout must track whichever family was selected
pre-run, even if the other dip reappears. On the failed attempt's actual
scout it selects 4.128 GHz (depth 0.253 in both scan directions) and a
clean 4.114-GHz control (survival advantage 0.516). If neither feature or
its corresponding control passes, the runner still stops before science.

On the measurement PC after stopping other acquisitions:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSwapHoldPilot --run
```

The retargeted swap-hold run completed at
`q3_tls_swap_hold_20260928T071255Z_3f183279` with all 88 arms and raw IQ
present. Its anchored lower feature was 4.127 GHz before and 4.126 GHz
after, with depths 0.448/0.300; the clean lower control was 4.113 GHz.
Readout fidelity was 0.856 before and 0.908 after. Pre/post transfer
controls and both early hot-minus-cold contrasts passed. The 0.1–6-us
trace did **not** show a convincing coherent swap oscillation. It did show
larger late-time loss at the feature than at the control in both forward
and reverse orders. For the *post hoc* 1.5-to-6-us difference of
hot-minus-cold contrasts, feature minus control was +0.150/+0.118 by
classified outcome, and +0.197/+0.232 using continuous IQ normalized by
the pre-run reference separation. Contiguous 20-shot block bootstraps gave
classified 95% intervals of roughly [+0.060,+0.235] and
[+0.027,+0.210]; continuous-IQ intervals were [+0.059,+0.331] and
[+0.093,+0.364]. These intervals describe shot uncertainty conditional
on the selected dwell pair; the pair was noticed after examining the trace,
so they do not establish a discovery-level effect. The forward control
trace also varied with dwell time.

The next run makes 1.5 versus 6 us the *predeclared* comparison. Each
logical QICK shot contains four complete visits and readouts at one site:
ground/excited at 1.5 us and ground/excited at 6 us. Four 3,000-shot
programs cover lower feature/control in forward and reversed order. The
fresh pre-scout must find the lower 4.127-GHz family with a clean 14-MHz
lower control, and the post-scout must track that same family. Readout,
transfer, ground-drift, and preparation-contrast gates remain explicit.
The primary statistic is the extra 1.5-to-6-us hot-minus-cold loss at the
feature after subtracting the same loss at the control. Reproduction would
confirm a time-localized excess-loss feature, not microscopic TLS identity.

On the measurement PC after stopping other acquisitions:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSwapHoldConfirm --run
```

The confirmation run `q3_tls_swap_hold_confirm_20260928T072204Z_bcf25403`
completed all four 3,000-shot, four-condition programs. The predeclared
feature-minus-control extra 1.5-to-6-us loss was +0.1017 and +0.0643 in
the forward/reverse orders, pooled +0.0830. Continuous IQ projected onto
the pre-run ground/excited reference axis gave +0.1167/+0.0908, pooled
+0.1038 reference separations. Independently resampling 20-logical-shot
blocks within each program gave pooled 95% intervals of about
[+0.053,+0.114] classified and [+0.066,+0.141] continuous-IQ units.
These intervals reflect shot noise within the acquired programs; they
do not cover the observed frequency drift.
The 400-shot readout references had fidelity 0.9075/0.9113 pre/post;
transfer controls and all four preparation/ground-drift checks passed.
The anchored lower feature remained visible but its selected center moved
from 4.125 to 4.128 GHz, beyond the predeclared 2-MHz stability gate,
so the manifest is `complete_controls_unstable`. The data support a
repeatable frequency-local excess late loss at the measured point, but
the shift prevents claiming a stationary resonant microscopic TLS.

The next measurement maps the same predeclared 1.5-to-6-us contrast over
17 frequencies spaced 1 MHz apart and centered on the new fresh lower
feature. An ascending and descending sweep each have a clean control
before and after them (38 programs total, 1,000 logical shots per
program, four subshots per logical shot). The post-scout tracks movement
again. A narrow extra-loss peak that follows the loss feature in both
directions would strengthen the resonant-interaction interpretation;
a broad or order-dependent signal would argue for ordinary drift or
flux-dependent qubit relaxation.

On the measurement PC after stopping other acquisitions:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSwapHoldConfirm --run --flux-map
```

The bidirectional flux map completed at
`q3_tls_swap_hold_flux_map_20260928T073005Z_ade6d323`: 38/38 programs,
all program preparation and ground-drift checks usable, and 0.910/0.884
pre/post readout fidelity. In the ascending sweep, the control-subtracted
extra 1.5-to-6-us loss was largest at 4.126 GHz (+0.171 classified);
the descending sweep had +0.130 at 4.126 GHz and +0.151 at 4.124 GHz.
The broad 4.124–4.130-GHz band was higher than the ten outer map points
in both directions (+0.120/+0.058 classified and +0.140/+0.067
continuous-IQ reference separations). This band and contrast were chosen
after seeing the map, so those numbers describe a pattern rather than an
independent significance test. The old narrow post-scout selector found
no anchored feature, but direct inspection showed a substantial lower
loss trough that had moved down and broadened. A qualified wider selector
locates 4.126 GHz in the pre-scout and 4.120 GHz in the post-scout, with
clean 14-MHz-lower controls in both scan directions. Thus the data do
not yet distinguish a moving resonance from two nearby loss processes.

The next one-cycle follow-up uses the same four-program, 3,000-shot
short/long-hold comparison but relocates the deepest qualified dip over
4.116–4.134 GHz before the experiment. It rejects flat/noisy scans,
records pre/post movement, and measures a clean control 14 MHz below
the new dip. Seeing the extra late loss at a newly shifted dip would
test whether the effect follows the loss feature.

On the measurement PC after stopping other acquisitions:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSwapHoldConfirm --run --follow-moving-dip
```

The retargeted confirmation
`q3_tls_swap_hold_moving_dip_20260928T074757Z_0996a6c1` found strong
loss near 4.115–4.116 GHz. The run selected 4.116 GHz with a 4.102-GHz
control; readout fidelity was 0.901/0.911 pre/post, both transfer
controls passed, and all four science-program contrast and ground-drift
checks passed. The predeclared extra 1.5-to-6-us loss at feature minus
control was +0.1087/+0.1870 in the two orders, pooled +0.1478
classified. Continuous-IQ normalization gave +0.1223/+0.2307, pooled
+0.1765 reference separations. Twenty-logical-shot block bootstrap
intervals for the pooled effects were [+0.118,+0.178] classified and
[+0.137,+0.217] continuous-IQ units. These intervals capture within-run
shot variation, not uncertainty about whether this and the earlier
4.127-GHz trough are the same microscopic object. Widening the selector's
lower edge from 4.116 to 4.110 GHz finds a three-point center at 4.116
before and 4.115 GHz after this run; the old selection was clipped at
the lower search boundary. Both scouts show a pronounced local minimum
at 4.115 GHz, and the 1-MHz three-point shift is within the stability
gate. Thus excitation-dependent excess loss reappeared at a substantially
lower-frequency loss feature with stable readout and control behavior.

The next measurement uses the already checked 88-arm passive swap-hold
time-trace protocol at the freshly selected lower-band dip: eleven dwell
times from 0.1 to 6 us, ground/excited preparation, feature/control, and
forward/reverse orders, with 600 shots per arm and pre/post scouts. This
tests whether the shifted feature supports reproducible exchange structure
or a simple extra decay envelope.

On the measurement PC after stopping other acquisitions:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSwapHoldPilot --run --follow-moving-dip
```

After an hours-long gap, the moving-dip swap-hold trace completed at
`q3_tls_swap_hold_moving_trace_20260928T140534Z_ed9a97a9`. Its fresh
pre/post scouts both found a deep loss region near 4.109–4.110 GHz;
the original wider selector's 4.110-GHz lower search bound returned
4.110 GHz with a 4.096-GHz control. Extending the qualified search to
4.105 GHz selects a three-point center of 4.109 GHz and a 4.095-GHz
control in both saved scouts. The dip had therefore moved several MHz
since the 4.115-GHz run, but it was stable during this trace. Readout
fidelity was 0.915/0.906 and pre/post park-to-target transfer controls
passed; all 88 arms and raw IQ were present.

The separately acquired 0.1–6-us feature and control curves show no
reproducible coherent exchange oscillation. At 1.5 versus 6 us, the
feature-minus-control extra loss is approximately -0.024 in the forward
order and +0.098 in reverse by classified readout, so this run does not
resolve whether the previously confirmed extra late loss still follows
the now-lower dip. Control-arm time dependence and acquisition-order
variation matter here. The next run uses the existing within-shot
four-condition confirmation at a fresh qualified dip (now searching
4.105–4.134 GHz), with a clean control 14 MHz below and reversed order.
If its pre-scout cannot find a qualified dip, the experiment stops rather
than measuring at an assumed old frequency.

On the measurement PC after stopping other acquisitions:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSwapHoldConfirm --run --follow-moving-dip
```

The within-shot confirmation completed at
`q3_tls_swap_hold_moving_dip_20260928T141757Z_e302ed09`. Fresh scouts
selected 4.110 GHz pre and 4.111 GHz post, with a 4.096-GHz lower
control during science acquisition. Readout fidelity was 0.895/0.903,
both transfer controls passed, and every program's early/late
preparation and ground-drift gate passed. The predeclared extra
1.5-to-6-us feature-minus-control loss was +0.0997 and +0.0493 in
forward/reverse order, pooled +0.0745 classified. Continuous IQ gave
+0.1679/+0.0303, pooled +0.0991 reference separations. Twenty-shot
block bootstrap intervals for the pooled effects were [+0.045,+0.104]
classified and [+0.061,+0.137] continuous-IQ units. The apparent
late-time loss therefore persists at the now-lower feature, while the
separately acquired 11-time-point pilot is too order-sensitive to resolve
its detailed time course.

The next measurement pairs each of ten later holds (0.2, 0.35, 0.5,
0.75, 1, 1.5, 2, 3, 4, 6 us) with a 0.1-us reference inside each
logical shot. It repeats feature/control in ascending and descending
hold order: 40 four-condition programs, 800 logical shots each, fresh
pre/post scouts, passive reset, and the same pinned flux correction.
The 0.1-us reference includes flux settling, so the long-time curve
and any oscillatory structure should be interpreted with that limitation.
This addresses the separate-arm order noise before attempting a model
fit or a stronger claim about coherent exchange.

On the measurement PC after stopping other acquisitions:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSwapHoldConfirm --run --paired-dwell-scan
```

The paired-dwell scan
`q3_tls_swap_hold_paired_dwell_20260928T143254Z_20d8a8e3` completed
40/40 four-condition programs. Readout fidelity was 0.899/0.908,
pre/post transfer controls passed, and all 40 individual preparation
and ground-drift checks passed. However, the strong T1 loss trough was
centered near 4.113 GHz before and 4.107 GHz after the run: a 6-MHz
shift, well outside the 2-MHz stability gate. The fixed 4.113-GHz
science point became nearly loss-free in the post-scout, while the
4.099-GHz control remained away from the trough. The feature-minus-
control 0.1-to-6-us excess loss was -0.061/-0.036 classified and
-0.044/-0.028 continuous-IQ units in ascending/descending order.
These are measurements at a drifting fixed frequency, not evidence that
the feature itself became nonsaturable or lost its extra late-time decay.
The separately acquired time trace and this paired curve cannot resolve
coherent exchange under such movement.

The next measurement quantifies the baseline spectral diffusion: ten
finite corrected passive five-point T1-versus-flux passes across
4.060–4.170 GHz at 1-MHz spacing, 350 shots per condition and five
conditions, stopping after ten passes or 25 minutes between passes.
Each pass checkpoints the usual one-stop CSV. A time series of trough
center, depth, width, and scan-direction disagreement will tell us how
quickly a future pump/swap experiment must relocate the feature and
whether the apparent movement looks continuous or jump-like. No pump is
applied during this baseline monitor.

On the measurement PC after stopping other acquisitions:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSpectralDiffusionMonitor --run
```

The finite baseline monitor completed ten 111-frequency passes between
11:04:42 and 11:18:06 local time on September 28. A three-point 25-us
survival dip was present in both scan directions on every pass. Its strongest
center moved from 4.106 GHz on the first pass to 4.101 GHz around passes
five and six, then 4.103 GHz on the last pass. Combined local depth varied
roughly 0.41–0.60 in normalized survival. A weaker, persistent trough near
4.146–4.148 GHz also appeared in every pass; the scan alone does not show
whether either trough is one microscopic TLS. The median P1-minus-P0
reference contrast stayed 0.49–0.53 across the ten passes. Thus the main
obstacle for a long fixed-frequency swap or pump run is movement of the loss
coordinate, not an obvious collapse of the passive preparation/readout
references. The old moving-lower-dip selector started at 4.105 GHz, so its
failure on some of these passes is a range artifact; the raw loss remained.

To test whether imperfect initial ground preparation still dilutes the
short/long-hold signal, an experiment-only pre-herald mode reuses the proven
two-readout QICK program. A first readout follows an identical 0.1-us ground
visit at the lower control; after the readout guard, a freshly prepared g/e
qubit visits the feature or 14-MHz-lower control for 1.5 or 6 us and gets a
final readout. No readout intervenes between that science visit and its final
readout. Both raw IQ records are saved. Six reference arms calibrate and
validate a frozen first-readout ground cutoff and a final-readout axis, but
invalid references do not discard the raw science. Sixteen science arms cover
all site/dwell/preparation combinations in forward and reverse order, with
800 shots per arm. The same saved shots produce all-shot and ground-heralded
excess-loss estimates; no conditioning uses the final outcome. Broad 4.060–
4.170-GHz scouts before and after locate the loss and flag more than 2-MHz
movement, and the 14-MHz-lower control must be separated from the loss in
both scan directions. The first measurement itself could alter the device,
so this is a test of heralded preparation, not a correction to the prior
unheralded swap-hold measurements.

On the measurement PC after stopping other acquisitions:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeHeralded --plan --prep-postselect
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeHeralded --run --prep-postselect
```

The pre-heralded preparation comparison completed in
`q3_preparation_postselection_20260928T153131Z_e43defe2`. The loss center
was 4.102 GHz in both the broad pre and post scouts, with normalized local
depths 0.584 and 0.551; the 4.088-GHz control remained clean. The first
readout held a 0.64–0.71 confident-ground acceptance across science arms.
The pre reference passed its independent herald checks, but the frozen final
readout axis failed the post reference: final-state fidelity fell from about
0.818 to 0.770, and excited-reference false-ground rate reached 0.106,
slightly above the preset 0.10 limit. The manifest therefore correctly
withheld a validated conditional result. Descriptively, projecting the raw
IQ on the frozen pre axes gives feature-minus-control 1.5-to-6-us excess
loss of +0.157 in the forward order and -0.034 in reverse after ground
heralding. All-shot estimates are +0.069 and 0.000. The order disagreement
persists after postselection, so this run does not show that imperfect
initial ground preparation was the principal obstacle. It also does not
refute the loss feature, which remained strong and fixed during the run.

The next bounded measurement returns to qubit-mediated pump/probe and asks
whether loading at this loss feature leaves a time-dependent excitation
memory. A park pi (or zero-gain cold control) precedes a 20-us target visit;
an excited pump at the 14-MHz-lower control checks off-target loading.
After the compensated return and first readout, a ground-prepared qubit
visits the loss feature for either 2 or 10 us. An additional 0 or 50 us
between readouts varies the post-loading wait. Each hot-on, cold-on, and
hot-off triad is repeated in reverse order: 24 science arms at 400 shots,
plus pre/mid/post references and broad pre/post loss scouts. Paired raw IQ is
saved even if the final reference gate fails. The descriptive report keeps
hot-on-minus-cold-on and hot-on-minus-hot-off separately; neither is
interpreted as a confirmed TLS signal unless the readout and feature
controls pass. This is a feature-local memory check inspired by the
time-dependent energy return in Guimarães et al. (arXiv:2609.31280), not a
replication of their broadband excitation spectroscopy. Its approximately
40-us first return plus readout still limits sensitivity to very fast memory.

On the measurement PC after stopping other acquisitions:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeHeralded --plan --afterglow
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeHeralded --run --afterglow
```

The feature-local afterglow run
`q3_pump_probe_afterglow_20260928T154340Z_b90f1e08` completed all 24 science
arms. The pre/post loss centers were 4.103/4.102 GHz, and pre/mid/post
readout references all passed. At the first readout, the qubit was classified
excited in 36.6% of hot/on-target shots versus 53.6% of hot/off-target shots:
the on-target flux visit caused pronounced extra qubit loss. But after
confident-ground heralding, pooled final excited probabilities were
91/965 = 0.094 for hot/on-target, 58/716 = 0.081 for hot/off-target, and
107/1489 = 0.072 for cold/on-target. Hot-on minus hot-off was +0.013, with
an approximate independent-shot 95% interval [-0.014,+0.041]; this interval
does not cover temporal correlations. In the two acquisition orders that
difference was approximately +0.030 and -0.002, and neither probe dwell nor
the extra 50-us wait showed a consistent feature-selective return pattern.
The larger all-shot hot/cold differences largely track residual qubit
excitation left after pumping; ground heralding greatly reduces them. This
clean run supports strong on-feature energy loss but does not establish
energy returning to q3 after the corrected pump return and readout. It does
not exclude faster memory before that roughly 40-us-plus-readout gap or a
loss process that dissipates without returning energy to the qubit.

The next bounded check resolves transfer *within one target visit*, before
the return/readout gap. A broad fresh passive scout locates the strongest
qualified dip and 14-MHz-lower control. Ten eight-condition programs compare
1.5 us with 3, 6, 10, 16, or 25 us. Each logical shot contains feature and
control visits, ground/excited preparations, and both dwells; the condition
order is reversed in the paired program at each dwell. Six hundred logical
shots per program save all raw IQ. Pre/post scouts and state-transfer/readout
references gate interpretation. The observable is the feature-minus-control
incremental loss relative to 1.5 us. The feature's late contrast may go near
zero from real loss, so the quality gate checks early contrast and the late
control contrast rather than demanding a large late feature contrast. It
also records feature ground-state excitation rather than rejecting it as
drift; only the control ground-state change enters the drift gate.
An unusual time course can motivate a microscopic model but is not by itself
proof of a single TLS.

On the measurement PC after stopping other acquisitions:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSwapHoldConfirm --plan --within-shot-time-map
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSwapHoldConfirm --run --within-shot-time-map
```

The within-shot time map completed in
`q3_tls_swap_hold_within_shot_time_map_20260928T155435Z_046eec13`.
All ten eight-condition programs completed, and the readout and transfer
controls passed. The loss feature was at 4.102 GHz in the pre-scout and
4.104 GHz in the post-scout; the 4.088-GHz fixed control remained separated
from the loss. The feature-minus-control extra loss relative to 1.5 us was
-0.058/-0.055 at 3 us, +0.083/+0.102 at 6 us, +0.100/+0.122 at 10 us,
+0.170/+0.172 at 16 us, and +0.307/+0.393 at 25 us, in the two
reversed condition orders. Block resampling 20 logical shots at a time
gives pooled classified 95% intervals of [-0.121,+0.009] at 3 us,
[+0.031,+0.154] at 6 us, and [+0.288,+0.413] at 25 us. The continuous
IQ projections agree in sign and magnitude at 6–25 us. These intervals
cover within-program shot variation, not uncertainty from the 2-MHz
feature motion. The 3-us negative point is inconclusive. The result is
a time-resolved, frequency-local loss signal; it does not identify a
single microscopic TLS or demonstrate saturation.

The next experiment directly tests loading-dependent loss before any
intermediate return or readout. A fresh 4.060–4.170-GHz scout selects the
strongest qualified loss feature and a clean 14-MHz-lower control. In each
science subshot, q3 starts in g or e, visits the target for 20 us, receives
a gain-6000 on-tone or detuned pulse while still at the target, remains
there for 1.5 or 16 us, and is read out once after the full corrected
return. Eight 1,500-logical-shot programs cross feature/control, on/detuned
tone, and reversed condition order; each logical shot alternates the two
probe holds, sham/driven pulse, and g/e loading. All single-shot IQ is
saved. Fresh resident-drive checks, readout/transfer references, and a
post-scout gate interpretation. The prespecified statistic compares
ground-referenced 16-to-1.5-us survival ratios after loaded and cold
preparations, then subtracts the corresponding off-feature difference.
Normalizing each preparation to its own short-time signal prevents unequal
post-pulse qubit populations from mimicking saturation. Detuned-tone arms
gate drive specificity. A positive result would be candidate saturation,
conditional on those controls, not proof
of a single TLS. A null result would leave faster TLS relaxation or weak
target drive unresolved.

On the measurement PC after stopping other acquisitions:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeShotAlternating --plan --short-gap-saturation
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeShotAlternating --run --short-gap-saturation
```

The first short-gap saturation run completed at
`q3_pump_probe_short_gap_saturation_20260928T171947Z_7a4dd52e`.
Pre/post scouts both selected 4.102 GHz with a clean 4.088-GHz flank;
readout, transfer, fresh drive, and all per-program controls passed.
The prespecified normalized, flank-subtracted loaded-survival advantage
was -0.017/-0.044 in the two reversed orders. Twenty-logical-shot block
resampling gives pooled classified -0.031 with approximate 95% interval
[-0.201,+0.164]; continuous IQ gives -0.055 with [-0.229,+0.122].
Thus this run does not resolve loading-induced saturation, but its
uncertainty still allows a smaller positive effect. The gain-6000 pulse
produced only about 0.15–0.18 short-hold cold-arm excitation contrast.
These intervals measure within-program shot variation and do not include
systematic uncertainty from the pulse model.

The next bounded follow-up keeps the same normalized statistic and controls
but shortens the target loading visit from 20 to 12 us and uses gain 30000
for the target-resident pulse. The previous drive calibration included this
gain, and fresh on/detuned/sham drive checks at both actual flux points
will again be measured before science. This tests whether weak re-excitation
or loss of defect memory during the 20-us preload concealed a short-gap
effect. Changing both settings together means any positive result will
require a later dose/timing dissection. A weak preliminary drive check
will not discard raw science; the within-program drive controls determine
whether a saturation claim is allowed.

On the measurement PC after stopping other acquisitions:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeShotAlternating --plan --strong-short-gap
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeShotAlternating --run --strong-short-gap
```

The gain-30000, 12-us-load run
`q3_pump_probe_strong_short_gap_20260928T173324Z_a4a397da`
completed all science programs, but its status is
`complete_controls_unstable`. The pre/post loss centers were 4.104/4.102
GHz with deep, well-separated troughs; readout and transfer controls
passed. The target-resident gain-30000 pulse produced almost no cold-arm
excitation at either flux point. Fresh-drive on-minus-sham fractions were
+0.003 at the feature and -0.018 at the flank; the within-program 1.5-us
cold-arm contrasts were only +0.012–0.025. Continuous IQ projections
agree that the response was near zero. The normalized saturation statistic
is undefined because its cold-arm denominator is too small. This run is
not evidence for or against TLS saturation. Earlier loading-time tests
found the resident pulse response at 4, 8, and 12 us weak, while 20 us
worked; changing loading time and gain together in this run left the cause
of drive failure ambiguous.

The next measurement keeps gain 30000 but restores the previously usable
20-us target-loading/settling time. It otherwise reuses the same
1.5/16-us, hot/cold, sham/on, feature/flank, detuned, and reversed-order
science protocol. The fresh high-gain drive check and each science program
measure whether the cold probe pulse actually excites q3. If they fail,
the raw data are retained but no saturation statistic is interpreted.
If they pass, this isolates the effect of higher drive gain relative to
the completed gain-6000, 20-us-load experiment.

On the measurement PC after stopping other acquisitions:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeShotAlternating --plan --strong-long-load
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeShotAlternating --run --strong-long-load
```

The 20-us-load, gain-30000 follow-up completed at
`q3_pump_probe_strong_long_load_20260928T174229Z_c7a2b280` with status
`complete_controls_unstable`. The loss center was 4.105/4.104 GHz pre/post,
the flank stayed separated, and readout/transfer controls passed. Restoring
20 us improved the fresh high-gain on-minus-sham response to +0.108 at the
feature, but only +0.073 at the flank. Within science, the 1.5-us cold-arm
drive response was +0.077–0.096 at the feature and +0.040–0.079 at the
flank, below the predeclared 0.10 gate in every program. The reverse-order
flank normalization denominator was below its 0.05 minimum. Continuous
IQ gives similarly small responses. Thus the gain-30000 saturation
comparison remains inconclusive; its apparently positive forward-order
ratio is not a validated physical effect. The earlier gain-6000, 20-us
run had stronger probe preparation, so simply increasing the DAC gain
was counterproductive at the current feature.

Rather than guess another gain, the next bounded measurement maps the
target-resident qubit pulse at the *current* loss feature. It uses the
proven 20-us target settling, scans gains 1000–30000 and detunings
-20 to +20 MHz with zero-drive brackets at the feature and qualified
14-MHz-lower control, and saves raw IQ. A fresh 4.060–4.170-GHz scout
locates the moving feature before the map and checks it afterward. The
purpose is to select a locally effective qubit re-excitation pulse for
one more short-gap pump–probe test; the map itself is not a TLS
saturation measurement.

On the measurement PC after stopping other acquisitions:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeResidentDrive --run --fresh-map
```

The fresh resident-drive map completed at
`q3_pump_probe_resident_drive_fresh_map_20260928T175415Z_eae54320`.
Both scouts found a 4.104-GHz loss center (depth 0.484/0.509), with a
qualified 4.090-GHz lower-flank control. Readout fidelity was 0.91 before
and 0.90 afterward; pre/post park-preparation transfer contrasts were
0.380/0.390. With 20-us target settling, a +5-MHz resident qubit pulse at
gain 20000 raised the excited fraction above adjacent zero-drive brackets
by +0.1425 at the feature and +0.1325 at the flank (200 shots per arm).
Shot-bootstrap 95% intervals were [0.075, 0.210] and [0.065, 0.200]. At
+20 MHz, the same gain gave +0.010 and +0.0225, respectively, with intervals
spanning zero. Continuous IQ projections agree in sign and size. Gain
30000 was weaker than 20000, as expected from the earlier failure. This is
a usable *qubit drive calibration*, not evidence of TLS saturation.

The next run uses the measured gain-20000, +5-MHz pulse for the actual
short-gap hot/cold pump–probe. It repeats the earlier 20-us load and
1.5/16-us probe holds, with sham, +20-MHz off-tone, lower-flank, and
reversed-order controls. The feature is located afresh; the map's controls
are validated before hardware access, and the current feature and flank
each receive new on/off/sham drive checks. The final report requires
within-program cold-drive response and stable readout, transfer, and
feature controls before interpreting a loaded-versus-cold survival effect.
The drive and target hold are within one flux visit, with no intermediate
readout. This changes only the experimental runner.

On the measurement PC after stopping other acquisitions:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeShotAlternating --run --mapped-short-gap
```

The mapped-pulse short-gap run completed at
`q3_pump_probe_mapped_short_gap_20260928T180222Z_f158ca27`, with status
`complete_controls_unstable`. All eight science programs and raw IQ files
were saved. The pre/post scouts both found 4.106 GHz (depth 0.485/0.519),
and the 4.092-GHz flank, readout, and park-transfer controls passed. The
fresh gain-20000 pulse produced +0.075 excited-fraction contrast at the
feature and +0.120 at the flank; the first feature check was below the
0.10 gate. Within-program 1.5-us cold-drive contrast was +0.090 at the
first feature pass and +0.124 at the reverse pass; both flank passes were
about +0.14. The +20-MHz off-tone stayed near zero.

The feature-specific loaded-minus-cold survival statistic changed sign:
-0.385 in the first order and +0.241 in the reverse order. Fifty-shot-block
bootstrap 95% intervals were [-0.828, +0.037] and [-0.063, +0.616],
respectively; the pooled interval [-0.338, +0.198] includes zero. The
feature's sham hot-preparation contrast rose from +0.132 to +0.264 over
the 50-second science sequence; the off-tone program showed the same
change (+0.122 to +0.240), and continuous IQ confirms it. The flank did
not show a comparable change. Thus neither sign can be interpreted as a
repeatable TLS saturation effect. Stable pre/post scout centers do not
guarantee that the short-time loss baseline stayed fixed in between.

The next measurement pairs +5-MHz on-tone and +20-MHz off-tone conditions
with both 1.5/16-us holds, hot/cold preparation, and sham/drive within
each 16-condition hardware shot. It repeats 500 shots at the feature and
flank in eight short cycles, reversing site and condition order every
cycle. Each program has 8000 IQ records, fewer than the 12000-record
programs that just ran. The result preserves cycle-by-cycle loss baseline
and pump response, so a changing feature can be separated from a
reproducible pump effect. The pulse is still checked at the current flux
before science, and the feature is scouted before and afterward. This is
an actual repeated pump–probe experiment, not another pulse map. The
predeclared quality rule requires at least six complete feature/flank
cycle pairs, including at least two of each condition order; the
cycle-level effect and sham hot-preparation contrast remain available
even if this gate fails.

On the measurement PC after stopping other acquisitions:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeShotAlternating --run --paired-tone-dynamics
```

The paired-tone dynamics run completed at
`q3_pump_probe_paired_tone_dynamics_20260928T181326Z_e820cfd9`.
All sixteen 16-condition programs completed, and pre/post scouts both
located the main loss center at 4.106 GHz. The loss depth changed from
0.427 to 0.590; readout and transfer controls passed. The fresh gain-20000
drive had excited-fraction response +0.0875 at the feature (below the
0.10 threshold) and +0.1125 at the flank. Within-program feature cold-drive
responses were +0.090–0.134 at 1.5 us; off-tone responses stayed near
zero. Only one of eight feature/flank cycle pairs passed every prespecified
drive and preparation gate. The feature-specific normalized pump statistic
by cycle was -0.330, +0.361, -0.113, +0.146, +0.140, -0.377, +0.311,
and +0.049: no reproducible sign. Continuous-IQ estimates also change
sign. A non-normalized, tone- and flank-subtracted four-way contrast
averaged -0.035 classified and -0.032 in reference-normalized IQ units;
neither establishes the sought positive saturation effect.

The short-time loss baseline itself varied locally: the feature's 1.5-us
sham hot-minus-ground contrast ranged from +0.130 to +0.282, while the
flank's corresponding on-tone contrast stayed around +0.41–0.46. The
feature variation appears in both +5-MHz and +20-MHz tone groups and in
continuous IQ, so it is not simply a pump-tone response. This run is a
decision point: stop this qubit-mediated pump/probe saturation protocol.
It neither proves nor excludes a microscopic TLS. The feature's switching
or spectral diffusion is now the more informative target.

The next experiment omits the pump and measures the local loss dynamics
directly. A broad scout finds the feature and a clean 14-MHz-lower
control. Sixty short programs each collect 250 logical shots containing
feature/control, g/e preparation, and 1.5/25-us holds in the *same*
hardware shot. The eight-condition order reverses each cycle. Raw IQ and
UTC timestamps preserve a roughly seconds-resolution trace of early
survival, late survival, and feature-minus-control incremental loss.
Pre/post readout and flux scouts remain controls; a shifted post-scout
center is recorded as part of the physics rather than discarding the
time trace. This tests whether the loss changes on a seconds timescale,
and does not by itself identify one defect or the mechanism of switching.

On the measurement PC after stopping other acquisitions:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSwapHoldConfirm --run --loss-dynamics
```

The pump-free loss-dynamics trace completed at
`q3_tls_loss_dynamics_20260928T182534Z_defa0535`: 60/60 cycles passed
the within-shot control gate. Readout fidelity was 0.920/0.884 pre/post;
both transfer controls passed. The main loss center was 4.102 GHz in the
pre-scout and 4.104 GHz afterward, still with a deep loss trough. Each
cycle lasted about 1.2 seconds. At the fixed 4.102-GHz science point,
feature-minus-control extra 1.5-to-25-us loss averaged +0.250 in the
first 20 cycles and +0.154 in the last 20. The difference +0.096 has a
four-cycle block-bootstrap 95% interval [+0.062,+0.131]. Continuous IQ
agrees in direction: +0.286 early versus +0.198 late in units of the
pre-run reference separation. Reversing the eight-condition order each
cycle produced only +0.021 mean difference between even and odd cycles.
Thus the measured loss at a fixed flux point changed during roughly
82 seconds, even though the clean control remained usable. The 2-MHz
pre/post center motion means this trace cannot distinguish a resonance
moving away from 4.102 GHz from a change in its depth. It is evidence
for time-varying local loss, not proof of telegraph switching or a single
microscopic TLS.

The next pump-free experiment samples a *local loss profile* fast enough
to separate those possibilities. Each 16-condition hardware shot visits
the freshly located center and ±3-MHz offsets, plus the qualified
14-MHz-lower control. At each point it measures ground/excited contrasts
after 1.5 and 25 us. Forty 200-shot cycles alternate condition order;
raw IQ and UTC timing are saved. The three simultaneous extra-loss
values and their right-minus-left asymmetry reveal whether the loss
peak shifts within the local band or instead changes approximately
uniformly in strength. A pre/post broad scout still checks the wider
frequency context. This is a spectral-diffusion measurement, not
another attempt at saturation.

On the measurement PC after stopping other acquisitions:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSwapHoldConfirm --run --loss-line-dynamics
```

The three-frequency trace completed at
`q3_tls_loss_line_dynamics_20260928T183725Z_1a549b0e`: all 40 cycles
acquired, 39 passed the within-shot control gate, and pre/post readout and
transfer controls passed. The broad scouts found a deep feature at 4.106
and then 4.105 GHz. At the fixed 4.103, 4.106, and 4.109-GHz science
points, mean feature-minus-control extra loss in the first ten cycles was
+0.241, +0.204, and +0.024; in the last ten it was +0.229, +0.312, and
+0.128. Two-cycle block-bootstrap intervals for the last-minus-first
changes were [−0.102,+0.075], [+0.068,+0.153], and [+0.038,+0.176].
The right-minus-left change was +0.117 with interval [+0.029,+0.199].
Reversing condition order between cycles gave much smaller even/odd
differences. Continuous-IQ projections agree that the center and right
side gained loss, though the left-side change depends on the estimator.
These are exploratory first/last comparisons; three points do not establish
a rigid line shift, a width change, or one microscopic fluctuator. The
broad-scout minimum moved *down* by 1 MHz while the fixed-point asymmetry
moved toward the high-frequency side, so a single rigid shift is already
an inadequate description of both observations.

The next run resolves the local shape with seven 2-MHz-spaced offsets
(−6 to +6 MHz) and one clean control inside each 16-condition shot. At
each flux point it measures g/e contrast after the same 25-us hold. Forty
200-shot cycles alternate the subshot order; raw IQ, cycle times, and
pre/post broad scouts are saved. Since this uses the same QICK stream size
as the completed three-point trace, it trades the short-dwell reference
for four more simultaneous frequencies. It tests whether the entire loss
profile translates, changes width/depth, or develops multiple components.
The data remain qubit-loss spectroscopy, not a definitive identification
of a single TLS.

On the measurement PC after stopping other acquisitions:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSwapHoldConfirm --run --dense-profile
```

The seven-point trace completed at
`q3_tls_dense_loss_profile_20260928T184741Z_a3a36000`. All 40 cycles,
all control gates, both transfer controls, and both readout references passed
(fidelity 0.919 pre and 0.914 post). The broad scouts both selected 4.105
GHz, but the *within-shot* profile switched character during the 89-second
science interval. In cycles 0–9, control-referenced extra loss at 4.099 and
4.105 GHz averaged +0.167 and +0.136. In cycles 10–39, those values were
+0.038 and +0.288. Thus the 4.105-minus-4.099 relative loss changed from
−0.031 to +0.250; from cycle 10 onward, all 30 individual cycles had the
4.105-GHz point more lossy. The clean-control g/e contrast changed only
from +0.357 to +0.385. Raw, unthresholded IQ projections independently
show the same profile change. Reversing the shot order between even and odd
cycles does not account for it.

The pre-scout already had a deep trough at 4.105 GHz, so the early
low-frequency profile appears temporary; it is not adequately explained by
the pre/post fitted center alone. Neither a single resonance jumping nor
two nearby fluctuators changing weight is established yet. The first-ten
versus later comparison was chosen after viewing the trace, so it is
descriptive rather than a predeclared significance test. A longer monitor
with the identical 16-condition shot can test whether low-frequency
episodes recur, how long each profile state persists, and whether changes
are abrupt. A 180-cycle run should take several minutes and preserves the
same flux and readout controls. If no second transition occurs, the earlier
event remains a transient rather than an estimated switching process.

On the measurement PC after stopping other acquisitions:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSwapHoldConfirm --run --dense-profile --dense-profile-cycles 180
```

The extended trace completed at
`q3_tls_dense_loss_profile_20260928T185929Z_91db64ce`: 180/180 cycles
passed the control gate, readout fidelity was 0.900/0.901 pre/post, and
both transfer controls passed. The broad scout selected the main trough
at 4.105 GHz before and 4.107 GHz afterward. During the roughly
seven-minute science interval, its local profile repeatedly shifted in
relative weight. Define asymmetry as extra loss at center+2 MHz minus
extra loss at center−2 MHz. Ten-cycle means were −0.075 and −0.103 for
cycles 0–19, +0.214 to +0.236 for cycles 30–59, −0.071 and −0.073 for
cycles 130–149, then +0.198 for cycles 170–179. Unthresholded IQ gives
the same sequence and correlates with the classified per-cycle asymmetry
at 0.964. Even/odd cycle mean asymmetries were +0.085/+0.099. The
asymmetry–clean-control contrast correlation was only −0.145.

This establishes recurring, minutes-scale changes in the *relative
frequency profile* of the qubit loss, not just a one-time warmup drift.
The trajectory is not cleanly binary, so a two-state fluctuator and its
switching rate should not be inferred from these data alone. A global
flux drift could still move all loss features together. The next run
tests that possibility by measuring the main trough and the separate
4.15-GHz trough in the same hardware shot. A pre-scout independently
qualifies the upper trough and its own lower control; three frequencies
at ±2 MHz and center around each trough, plus both controls, comprise
the same proven 16-subshot format. The 180-cycle trace saves raw IQ and
timestamps. Independent line motion would weigh against a common global
flux/readout drift, though it would still not identify a microscopic TLS.

On the measurement PC after stopping other acquisitions:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSwapHoldConfirm --run --dual-line-dynamics
```

The simultaneous two-line run completed at
`q3_tls_dual_line_dynamics_20260928T191619Z_7e340715`: 180/180
cycles passed both control gates, pre/post readout fidelities were
0.906/0.918, and both transfer controls passed. The main broad-scout
center remained 4.107 GHz; the separate upper feature was selected at
4.147 before and 4.148 GHz afterward. In the 3-point within-shot
profiles, the main asymmetry (loss at center+2 MHz minus loss at
center−2 MHz) moved from −0.053 in cycles 0–19 to −0.231 in cycles
160–179. The upper asymmetry changed from +0.107 to +0.116. Their
change difference was −0.188; an exploratory four-cycle block-bootstrap
interval was [−0.249,−0.130]. The cycle-by-cycle correlation between
the two line asymmetries was only +0.114, compared with +0.414 between
their control contrasts. Continuous IQ independently reproduces both
line asymmetries (correlations 0.914 and 0.905 with classified values)
and the weak between-line correlation (+0.113).

The distinct responses argue against a *simple common readout drift*.
They do not yet exclude global flux drift because the two lines may
have different sensitivity to a shared flux offset. Also, the upper
feature is weaker, and the post-run park-to-readout transfer contrast
fell while remaining above its acceptance threshold. The next run
calibrates the common-flux response directly: in alternating four-cycle
ABBA blocks, it adds −20 or +20 DAC counts to **every** science flux
point (both lines and both controls). Each sign appears in both shot
orders, and the pairwise difference is measured over nearby cycles.
The offset is about 1 MHz on the local frequency grid, small compared
with the 2-MHz sample spacing. This gives an empirical fingerprint of
how a global flux shift changes each line's asymmetry. The dither could
itself perturb a defect, so the interpretation will use repeatability
and raw IQ rather than assuming a passive calibration.

On the measurement PC after stopping other acquisitions:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSwapHoldConfirm --run --dual-line-dither
```

## Direct two-visit memory test (current next experiment)

The flux-dither proposal above was **not run**. The user wants to act on a
loss feature rather than measure its spectral diffusion or common-mode flux
motion. Earlier afterglow attempts inserted a full corrected return and an
intermediate readout between loading and probing. A negative result there
does not test whether excitation can be recovered sooner.

`TLSTwoVisitMemory` freshly locates a qualified loss feature and a clean
14-MHz-lower control. In each hardware shot it interleaves eight subshots:
first/second visits at feature/feature, feature/control, control/feature,
or control/control, each with park-ground or park-excited preparation.
The first visit lasts 10 µs. After a 0.5, 2, 10, or 40 µs storage interval
at park, the second visit lasts 6 µs. Flux-tail compensation superposes
the four step responses, with no measurement or full 40 µs recovery between
visits. A 40 µs corrected return precedes the **only** readout. Each gap
is repeated with the eight subshot orders reversed; gaps are visited in
ascending then descending order, 800 logical shots per program. Raw IQ,
readout and park-transfer references, and pre/post broad
scouts are saved.

The preregistered interaction score is
`log[(C_ff × C_cc)/(C_fc × C_cf)]`, where `C_ab` is the final excited-minus-
ground readout contrast after first site `a` and second site `b`.
Independent multiplicative loss from the two visits gives zero. A
reproducible short-gap interaction that disappears by 40 µs would be
evidence of memory across visits. It would not by itself identify a single
TLS or prove coherent exchange; flux-history and other non-Markovian
mechanisms would remain alternatives. Both order repeats and the scout /
readout controls must pass before interpretation.

On the measurement PC after stopping other acquisitions:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSTwoVisitMemory --run
```

The run completed at `q3_tls_two_visit_memory_20260928T202625Z_0092391e`.
Its 4.102-GHz loss feature shifted by only +1 MHz after the science
sequence; readout fidelity was 0.899/0.928 pre/post, and both park
transfer controls passed. No positive excitation-retrieval interaction
appeared. Classified-shot mean log interactions for storage times
0.5, 2, 10, and 40 µs were +0.040, −0.116, −0.254, and +0.035.
The 10-µs minus 40-µs difference was −0.290 with an exploratory
shot-bootstrap 95% interval of [−0.583, −0.004]; this is borderline
after inspecting four gaps. The unthresholded IQ agrees with the
negative 10-µs interaction in one order but is near zero in the other.
This is an extra-loss hint, not evidence of returned excitation or a
confirmed TLS memory effect.

The focused `--confirm` run measures 10- and 40-µs storage gaps in
*the same* 16-subshot hardware shot: four first/second visit pairs,
both preparations, and both gaps. Four blocks reverse the subshot
order and which gap comes first, with 1200 logical shots per block.
This directly tests the tentative 10-vs-40-µs difference under close
temporal matching and saves raw IQ for every condition. The same
fresh scout, feature/control qualification, readout and transfer
references, and post scout remain in force. If the paired difference
does not reproduce across blocks and in continuous IQ, abandon the
memory claim rather than broadening the drift study.

On the measurement PC:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSTwoVisitMemory --run --confirm
```

The within-shot confirmation completed at
`q3_tls_two_visit_memory_confirm_20260928T204426Z_33753877`.
All four 1200-shot blocks, 16 conditions per block, completed; pre/post
readout fidelities were 0.909/0.898 and transfer controls passed.
The loss center moved from 4.102 to 4.105 GHz, beyond the preregistered
2-MHz stability gate. The blockwise classified 10-minus-40-µs log
interactions were −0.146, −0.201, +0.325, and −0.064, averaging −0.022.
A paired shot bootstrap gave an exploratory 95% interval of
[−0.188, +0.148]. The unthresholded-IQ mean was −0.030 with interval
[−0.206, +0.153]. There is no replicated memory or energy-return
effect in this protocol; the earlier 10-µs hint should be dropped.

Further repetitions of pump–probe on this 4.10-GHz loss feature are not
justified by these data: it is a robust loss channel but has shown no
repeatable saturation, coherent swap, or loaded-state memory. The next
direct TLS-control attempt moves to a **different** candidate rather
than tracking this feature's drift. `TLSSwapHoldPilot --wide-candidate`
first acquires one 3.8–4.3-GHz passive scout, then selects an isolated,
sharp dip outside 4.080–4.190 GHz with a clean ±14-MHz control in both
scan directions. In the September 27 wide data this rule would select
the separate 4.048-GHz dip, but the run uses the freshly measured
location. It immediately performs the existing 0.1–6-µs g/e swap-hold
trace at that candidate and control, with forward and reverse order,
raw IQ, readout/transfer references, and a post wide scout. A feature-
local, reproducible **nonmonotonic** trace would motivate a swap
chevron; monotonic loss alone will not be called a controlled TLS.

On the measurement PC:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSwapHoldPilot --run --wide-candidate
```

The wide-candidate run completed at
`q3_tls_swap_hold_wide_candidate_20260928T210034Z_1d9b202a`.
It selected a strong separate dip at 3.992 GHz with a 4.006-GHz control;
all 88 swap arms completed. Readout fidelity was 0.926/0.903, and the
park-transfer controls passed. The manifest marked the feature unstable
because the post-scout selector demanded a single-bin minimum. Direct
inspection shows that the same 3.990–3.992-GHz dip persisted: applying
the same three-point depth and bidirectional control criteria around
the pre-run anchor gives a 3.992-GHz post center, depth 0.509 versus
0.499 pre, and the same clean control. The selector now allows a
two-bin minimum on the anchored post pass, while retaining a sharp-
minimum requirement for choosing a new pre-run candidate.

The sequential 0.1–6-µs trace is not convincing coherent exchange.
The feature-minus-control g/e contrast curve has forward/reverse
correlation −0.29; the large 0.1- and 0.75-µs excursions change sign
between orders. Continuous IQ shows the same disagreements. There is
more feature-local late loss, but that alone is ordinary relaxation.

The next direct test keeps this *new* candidate family and interleaves
feature/control, ground/excited, and 0.1-µs/longer visits inside every
hardware shot. Ten later holds from 0.2 to 6 µs are measured in
ascending and descending order, 800 logical shots per program. A fresh
wide scout selects the current coordinate automatically; readout,
transfer, and post-scout controls remain. The question is whether a
nonmonotonic swap-time feature replicates when temporal changes are
suppressed by within-shot pairing. If not, stop treating this loss dip
as a coherent TLS candidate.

On the measurement PC:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSwapHoldConfirm --run --wide-within-shot
```
