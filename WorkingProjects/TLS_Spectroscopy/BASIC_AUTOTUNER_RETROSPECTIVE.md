# Basic auto-tuner retrospective and technical handoff

This document is the detailed handoff for the basic single-qubit auto-tuner in
`Client_modules/Experiments/mBasicAutoTuner.py` and its production runner in
`Client_modules/Runners/BasicAutoTune.py`. It records what the tuner is supposed to
do, why its current design looks the way it does, the hardware failures and software
mistakes encountered during development, the meaning of its output, and the
invariants that must not be casually removed.

Status when this document was written:

- Branch: `tls-spectroscopy`
- Implementation revision: `run-health-v13`
- Last committed optimizer foundation: `68f29ce` (`Add deterministic gain zoom and
  pulse-family screening to the basic autotuner`); v12 adds the local runner mode flag
- Production mode: report-only; top-level runner flag selects either the 1--20 us
  portfolio or the exact current `initialize.py` readout length
- Configuration writes: deliberately disabled in `BasicAutoTune.py`
- Primary test suites:
  `Client_modules/Tests/test_basic_auto_tuner.py` and
  `Client_modules/Tests/test_basic_joint_optimizer.py`

This is not a claim that the tuner is finished or that synthetic tests prove hardware
performance. It is an attempt to ensure that the next agent starts from the actual
evidence instead of repeating the same design mistakes.

---

## 1. Read this first

The essential facts are:

1. The user can manually obtain approximately 90--94% TLS step-5 single-shot
   fidelity on q4. A tuner result near 50--80% is therefore not evidence of a device
   ceiling. It is evidence that the tuner has selected the wrong full tuple, used a
   mismatched pulse/reset path, lost a previously measured good candidate, or measured
   during a bad drift epoch.
2. The optimization target is the exact paired ground/excited single-shot experiment
   used by step 5 of `TLSSpectroscopy.py`, not averaged spectroscopy contrast, a Rabi
   fit score, or an analytic readout model.
3. A high binary single-shot fidelity is not, by itself, a high-fidelity X180 gate.
   It conflates state preparation and readout, and leakage can be counted as
   “excited” by a binary discriminator. Coherent-control and third-population evidence
   must be reported separately.
4. A visible third IQ cloud is not automatically a calibrated `P(f)`. The default
   operational screen reports a resolved third-population statistic. Direct qutrit
   leakage requires a separately calibrated e-f transition and response inversion;
   that strict path exists but is disabled by default because an incorrect e-f
   calibration is worse than an honestly labelled proxy.
5. The current runner does not choose one pulse and does not update
   `initialize.py`. With `RUN_1_TO_20_US_MODE=True`, it reports the best fidelity tuple
   at every integer readout length from 1 through 20 us. With the flag false, every
   readout-length search axis is fixed to the exact `BaseConfig["read_length"]` loaded
   from `initialize.py`. Either mode may report a second lower-stress X180 alternative.
6. `Fmax` and `bal` have different meanings. `Fmax` is selected only by held-out
   fidelity. `bal` is an optional statistically noninferior, preferably longer and
   lower-drive control with better safety evidence. Leakage is not allowed to silently
   replace the fidelity winner.
7. The resonator and qubit input frequencies are priors, not answers. By default each
   true frequency must lie within +/-100 MHz of its corresponding value in
   `initialize.py`. The tuner must search that full authorized interval and must not
   hardcode q4's known 7249/2534 MHz values.
8. Readout gain, readout length, X180 gain, and Gaussian duration are not expected to
   start close. They are search variables. The static fast-flux operating point is
   context, not a search variable.
9. Active reset is an acceleration only. It is never allowed to become part of the
   objective unless the exact full tuple reproduces against passive preparation. If
   that A/B test fails, the run must fall back to passive relaxation without aborting
   or discarding good passive measurements.
10. Never diagnose “device drift” merely because two sequential optimizer stages
    disagree. First inspect the exact pulse signature, reset mode, raw IQ, candidate
    survival, discriminator drift, and whether the comparisons were acquired in a
    shared interleaved cohort.

---

## 2. What the basic tuner is and is not

### 2.1 Intended job

The tuner automates the hand-tuning workflow that has worked in this repository:

```text
resonator discovery
  -> qubit spectroscopy over the authorized prior
  -> coherent averaged-IQ Rabi basins
  -> broad single-shot readout bootstrap
  -> direct single-shot chevrons
  -> repeated-pulse transition qualification / AAE
  -> coupled readout and control search
  -> held-out full-tuple replay
  -> requested fixed-readout-duration portfolio (1--20 us or one initialized length)
  -> independent control and third-population reporting
```

The manual inspiration includes the QICK QM-Team `SingleShot_FF.py` workflow and the
QUA `gate_calibration_flux_tunable` workflow, but the implementation is not a literal
copy. The useful principles were retained: find the physical resonator and transition,
use Rabi/chevron measurements to establish coherent control, optimize with the actual
single-shot objective, and amplify small coherent errors with repeated pulses.

### 2.2 Non-goals

The current production runner is not:

- a randomized-benchmarking optimizer;
- a proof of average gate fidelity;
- a general arbitrary-waveform or closed-loop optimal-control package;
- a flux optimizer;
- a dynamic fast-flux excursion calibrator;
- a guaranteed direct leakage measurement;
- an automatic writer of `initialize.py`;
- allowed to infer that the strongest spectral line is the intended qubit without a
  coherent witness;
- allowed to infer that the shortest pulse is preferable merely because it is fast.

The name “basic” refers to the operator-facing workflow, not to the size of the code.
The implementation became large because it has to preserve evidence across failures,
control drift, manage active-reset state, save raw diagnostics, and prevent partial
measurements from authorizing destructive configuration writes.

---

## 3. The physical tuple and objective

### 3.1 Complete candidate tuple

A candidate is not “a pi gain” or “a readout frequency.” It is the complete physical
tuple:

- `read_pulse_freq` in MHz;
- `read_pulse_gain` in DAC units;
- `read_length` in us;
- `qubit_freq` in MHz;
- `qubit_pi_freq` in MHz;
- `qubit_pi_gain` in DAC units;
- `sigma` in us;
- `qubit_drag_beta`.

The canonical Gaussian pulse is four sigma long. Thus `sigma = 0.25 us` means a
1000 ns X180 envelope and `sigma = 0.10 us` means a 400 ns envelope. Reports print
the physical `4*sigma` length.

Every certificate, repeated-pulse witness, leakage/safety result, and held-out fidelity
must be bound to this exact tuple. Evidence from one frequency/gain/duration/DRAG
combination must never authorize another combination.

### 3.2 Exact step-5 objective

The direct objective uses `mSingleShot1Q.SingleShotProgram` and the same threshold and
IQ-rotation helpers as TLS spectroscopy step 5. It prepares nominal ground and excited
ensembles, rotates the IQ plane, chooses a binary threshold, and reports assignment
fidelity plus uncertainty and cloud-separation information.

Consequences:

- Spectroscopy and averaged Rabi are basin generators, not the final objective.
- Readout and control cannot be optimized independently forever. A weak X180 corrupts
  the apparent readout optimum; a weak readout corrupts the apparent X180 optimum.
- A one-shot maximum can be a statistical outlier. Final decisions require independent
  blocks and fresh replay.
- Binary fidelity can reward leakage if leaked shots land on the excited side of the
  threshold. This is why fidelity and leakage/safety are reported independently.
- A step-5 fidelity is a calibration-system metric, not an RB-derived gate fidelity.

### 3.3 Pulse-path fidelity matters

An important historical bug was omitting the runtime `qubit_gain` register field while
setting `qubit_pi_gain`. The manual step-5 program and the tuner could then compile
different physical amplitudes despite printing the same nominal tuple. `_cfg_for()`
now explicitly sets:

```python
cfg["qubit_gain"] = int(round(candidate["qubit_pi_gain"]))
```

The preflight also requires the canonical `arb` Gaussian control path, the constant
readout path, no conflicting flat-top fields, and the same switch-off behavior as TLS
step 5. If a manual experiment and the tuner disagree, compare the compiled pulse
signature and runtime reset metadata before comparing printed numbers.

---

## 4. Empirical benchmark and the failures that motivated this design

### 4.1 Manual benchmark that invalidated the early conclusions

The user ran TLS spectroscopy step 5 with approximately:

```text
readout: 7249.1 MHz / 5000 DAC / 30 us
X180:    2534.7 MHz / 5790 DAC / 1000 ns
result:  F = 0.9165
```

The confusion matrix was approximately:

```text
[[0.965, 0.132],
 [0.035, 0.868]]
```

Immediately afterward an early autotuner replay of what appeared to be the same tuple
reported only about `F = 0.747`. The correct conclusion was not that the user's manual
number was wrong or that the hardware had necessarily drifted. The nominal tuple was
not sufficient to prove identical execution. Pulse-register propagation and reset
behavior differed. This incident is the reason the current code treats exact pulse
signatures, reset mode, and full raw diagnostics as first-class evidence.

### 4.2 Important observed q4 landmarks

These values are useful sanity checks, not hardcoded device truths:

- Resonator repeatedly observed near 7248.96--7249.10 MHz.
- Coherent qubit transition repeatedly observed near 2534.3--2534.7 MHz in the later
  runs discussed here.
- Manual and tuner single-shot measurements have reached roughly 0.90--0.94 under
  workable conditions.

A new run can legitimately differ with flux, cooldown, power, or device state. These
numbers must never replace a configured search prior or a fresh measurement.

### 4.3 Development timeline and what each failure taught us

#### A. The first “advanced” tuner aborted instead of tuning

The original advanced tuner treated a spectral candidate outside a narrow identity
radius as a fatal error and later treated failure of a local 2-D winner to reproduce as
a fatal verdict. It produced useful partial measurements but wrote nothing and often
stopped before exploring recoverable alternatives.

Lesson: weak initial parameters must not be a baseline acceptance test. A tuner should
search, retain its best measured candidate, and distinguish “best found” from
“certified for write.” Failure to certify is not permission to erase the empirical
result.

#### B. Baseline-only validation blocked the search

An early protected-control version replayed the input tuple, obtained about 0.747, and
stopped because the lower confidence bound was below 0.85. This contradicted the basic
purpose of an autotuner: the input is allowed to be bad.

Current rule: baseline fidelity is diagnostic only. It never gates resonator,
spectroscopy, Rabi, or parameter search.

#### C. A sequential manual-workflow version improved to about 0.895 but was fragile

One run starting around 0.780 found the correct frequency neighborhood and improved to
about 0.895, but later waveform/safety stages failed and the result was not stable
enough to write. The stages moved readout and control one after another, so a later
coordinate update could invalidate an earlier optimum.

Lesson: readout length/gain and X180 length/gain are coupled. Greedy coordinate descent
is useful for bootstrapping but is not a reliable final optimizer.

#### D. Bad starting values exposed local-search anchoring

With intentionally bad starting frequencies, early versions “found” resonators near
6994 or 7108 MHz and qubit features around the wrong prior. One especially revealing
case started the readout near 7200 MHz, where the known 7249 MHz resonator was inside
the promised +/-100 MHz region, yet the tuner selected a false feature around 7108 MHz
and proceeded.

Fixes:

- Search the complete configured +/-100 MHz prior, not a small local window followed
  by wishful extrapolation.
- Preserve several resonator candidates.
- Independently confirm line width, contrast, shift, and edge behavior.
- Run spectroscopy/Rabi on multiple resonator branches.
- Backtrack when a strong resonator feature has no coherent qubit branch.
- Reject monotonic transmission and featureless spectroscopy instead of promoting the
  input prior or noise.

The current tuner is expected to recover 7249 MHz from a 7200 MHz prior. It is not
expected to recover it from 7429 MHz under the default +/-100 MHz contract because the
true line is about 180 MHz away. Expanding the contract is an explicit policy change,
not an undocumented fallback.

#### E. The tuner over-optimized latency and selected a visibly problematic 8 us row

A corrected discovery run found about 7248.958/2534.281 MHz and reported an 8 us
readout with roughly 0.884 fidelity. A subsequent single-shot plot showed a large third
IQ population. The binary objective had not adequately penalized or even reliably
reported that structure.

Lesson: “shortest high-fidelity chain” is not a scalar objective unless leakage and
uncertainty are explicitly constrained. A fidelity/time ratio is particularly bad: it
can prefer a very fast but unusable low-fidelity or high-leakage point.

The operator then requested a clearer contract: report one optimized tuple at every
integer readout duration from 1 to 20 us, report fidelity and leakage separately, and
let the operator choose. That is the current production mode.

#### F. Leakage-aware selection obscured the fidelity maximum

An intermediate portfolio attempted to optimize a weighted combination of fidelity and
leakage. This made it difficult to answer the simple question “what is the maximum
fidelity actually measured at this readout length?” and could choose a lower-fidelity
row based on a noisy or unavailable safety proxy.

Current rule: `Fmax` is selected by held-out fidelity only. Leakage and control checks
annotate that exact row. A second `bal` row may be reported, but never replaces `Fmax`.

#### G. Overly strict transition qualification stopped before the 20-row table

One run found the known workable frequencies and measured about 0.943 at a 10 us
readout, yet an early repeated-pulse/locking condition failed and the portfolio never
ran. The frequency evidence was credible; the rough amplitude witness was being asked
to satisfy a final control-quality standard before amplitude and duration optimization.

Fix: separate transition qualification from final pulse certification. Coherent Rabi
can establish a controllable transition basin even if a rough repeated-pulse pulse is
not yet excellent. The final exact waveform still needs its own control audit, but a
rough pulse-quality failure no longer automatically prevents optimization around a
known coherent frequency.

#### H. A previously observed 93% row later collapsed toward 50%

Sequential portfolio measurements produced cases where a duration previously measured
near 93% later appeared close to a coin flip. This cannot be explained by one coarse
gain number alone. Diagnostics exposed two structural risks:

1. A feedback-reset profile could pass a narrow reset probe yet destroy the actual
   end-to-end step-5 prepared-state comparison.
2. A good passive bootstrap/control tuple could be displaced from the shortlist by
   later shared-ground, feedback-contaminated, or noisy rows.

Fixes:

- Feedback reset now receives an exact passive-versus-feedback A/B qualification on
  the complete tuple.
- A statistically resolved catastrophic loss disables feedback for the rest of the
  run.
- Readout-coordinate maps deliberately use passive preparation where a changing
  integration coordinate invalidates one frozen threshold.
- The known passive bootstrap tuple is protected and crossed into later duration
  searches.
- Candidate archives are append-only; late failures cannot erase earlier direct
  measurements.
- Final exact candidates for all readout durations are replayed in one randomized,
  interleaved cohort so time drift is not aliased into duration dependence.

The answer is not “always use passive reset.” A correctly qualified active reset saves
substantial time. The answer is that active reset must prove it reproduces the exact
objective and must fail safe to passive preparation.

#### I. Suspiciously round gains exposed insufficient local convergence

The broad search intentionally uses a regular DAC backbone. That makes values such as
5000, 6000, or 9000 common coarse winners, but those values are not evidence of a
locally optimized gain. A stochastic trust-region proposal also does not prove that a
gain axis was adequately challenged.

The gain-convergence machinery introduced in v11 and retained in the current
`selectable-readout-mode-v12` implementation adds:

- a deterministic five-point readout-gain axis around each provisional winner;
- a deterministic five-point X180-gain axis;
- minimum 100-DAC spacing so low-gain axes do not collapse;
- a full 3x3 readout-gain/X180-gain interaction zoom;
- up to three recentered zoom rounds when the winner remains on an edge;
- fresh held-out exact replay after refinement;
- tests that require non-round neighbors to be proposed.

Round values can still genuinely win. They are no longer accepted merely because the
coarse lattice used round values.

#### J. Short high-gain pulses were being preferred without a lower-stress comparison

For an ideal two-level Gaussian X180, pulse area scales roughly with `gain*sigma`.
Shortening sigma therefore tends to require higher gain and can increase spectral
broadening, mixer/nonlinearity sensitivity, and leakage risk. Blindly minimizing X180
length is not a state-of-the-art objective.

The current portfolio now generates exact constant-area partners at half and double
sigma, seeds gain inversely, and then measures a local gain axis because inverse scaling
is only a prediction. Partners such as 0.075 or 0.30 us are allowed even though they
are absent from the original coarse sigma list. Amplified-amplitude-error refinement is
run across the pulse family once before the per-readout portfolio. The final table can
show a lower-stress `bal` row when its paired fidelity loss is bounded by 1 percentage
point.

---

## 5. Current production workflow in detail

### 5.1 Preflight and fixed experimental context

Preflight validates the hardware/pulse contract:

- canonical arbitrary Gaussian qubit pulse;
- no mixed flat-top fields;
- constant readout pulse;
- switch-off step-5 path;
- valid distinct fast-flux channel when a static park is requested;
- positive readout length and sigma;
- supported gain-sweep behavior or a slower point-by-point compiled fallback.

The tuner holds the configured `ff_park_gain` on `ff_ch` throughout every acquisition.
That value is neither tuned nor written. The user may calibrate at any static flux
operating point by changing the configured park value before the run.

Important limitation: dynamic `ff_hold_gain` excursions and legacy dynamic
`FF_Qubits` gain sequences are rejected. Supporting “tune while an arbitrary flux
waveform is played” would require a new timing contract and matching tests; it must not
be silently mixed with the static-park implementation.

### 5.2 Baseline

The exact input tuple is measured for reference. Low fidelity does not abort or narrow
the search. The baseline answers only:

- what did the starting configuration actually do in this run?;
- is there an already-good tuple worth protecting?;
- how large was the eventual improvement?;

### 5.3 Resonator discovery

Default relative policy:

- center: input `read_pulse_freq`;
- authorized radius: +/-100 MHz;
- expansion radii: 5, 25, then 100 MHz;
- broad step: 0.20 MHz;
- up to eight candidate notches;
- 4 MHz independent confirmation around each candidate;
- safe discovery readout: 5000 DAC / 10 us, independent of a bad input gain/length.

Padding lets a fit see a feature exactly at the prior edge but does not expand the
accepted policy. Candidate selection checks contrast, width, edge location,
reproducibility, and confirmation shift. Multiple real modes are retained for qubit
branch testing.

Never simplify this to “take the deepest dip.” A package mode can be deeper than the
useful readout resonator.

### 5.4 Qubit spectroscopy

Default relative policy:

- center: input `qubit_freq`/`qubit_pi_freq` prior;
- authorized radius: +/-100 MHz;
- broad step: 2 MHz;
- local and wide scans;
- up to eight ordinary/shoulder candidates;
- fresh opposed confirmation scans;
- 20 MHz local confirmation window to accommodate broad driven lines.

The full prior is searched even after finding an early feature. This is essential when
a nearby TLS is stronger than the qubit. Shoulder proposals exist because overlapping
lines need not produce separate local maxima.

Spectroscopy is not allowed to promote featureless noise or the starting prior. A
provisional correlated complex response may seed Rabi when a one-line fit is
inadequate, but it does not become a final transition by itself.

### 5.5 Averaged-IQ Rabi and branch resolution

Every retained spectral basin receives a frequency/gain Rabi challenge. The analysis
looks for coherent oscillation, adequate contrast/SNR, and a credible return toward
the 2-pi state. Multiple resonator/spectral branches can survive into this stage.

A weaker coherent branch must not be erased by a stronger noncoherent line. Conversely,
a saturation feature with no oscillatory witness must not become a control basin.

### 5.6 Bootstrap single-shot readout

The first broad direct single-shot readout map breaks the control/readout
chicken-and-egg problem. It uses a provisional coherent pulse to find a usable
discriminator. This map is not final write evidence.

The exact passive bootstrap tuple is protected. It is later crossed into every
readout-duration search so that a failed active-reset profile or noisy shared-ground
map cannot remove the last known working path.

### 5.7 Active reset qualification

The active-reset system:

- calibrates a raw threshold for the ADC integration length/readout frequency;
- freezes the reset drive gain/control pulse;
- restores the candidate's scoring readout and X180 after reset operations;
- clears measurement photons for 25 us before the next calibrated control pulse;
- validates residual behavior;
- most importantly, runs an exact end-to-end passive-versus-feedback A/B comparison.

Default exact A/B requirements include minimum feedback fidelity, maximum mean/block
loss, and a separation-ratio floor. A large resolved collapse disables feedback for
the remainder of the run.

`relax_delay = 3000 us` is the passive fallback inherited from `BaseConfig`. It is not
a searched pulse parameter and is not written by this runner. It is intentionally slow
and safe. If active reset is unavailable, a 20-duration high-shot portfolio can take a
long time because every passive shot pays that delay.

### 5.8 Direct single-shot chevrons and repeated-pulse qualification

Each coherent frequency basin receives a small single-shot frequency/gain chevron.
Repeated odd/even pulse counts then test whether the candidate acts like coherent
X180 control rather than a one-pulse saturation maximum.

This stage qualifies the transition basin. It must not demand that the rough pulse
already meet the final exact-waveform control certificate. Gain, duration, and AAE are
still to be optimized.

### 5.9 Pre-expensive frequency gate

The expensive joint optimizer starts only after the resonator and qubit transition are
credibly located. This gate exists because spending tens of minutes optimizing gains
around a noise feature is worse than stopping with clear diagnostics.

The gate should fail closed when:

- no resonator candidate confirms;
- no reproducible spectral feature exists in the authorized prior;
- no spectral basin has a coherent Rabi witness;
- resonator/qubit branch association is unresolved in a way that makes the chosen
  physical target ambiguous.

It should not fail merely because a rough amplitude is imperfect or an optional
repeated-pulse refinement throws an exception.

### 5.10 Structured coupled joint search

The joint search covers:

- readout lengths: every integer 1--20 us in broad mode, or only the exact initialized
  readout length in fixed mode;
- Gaussian sigmas: 0.05, 0.10, 0.15, 0.25, 0.35, and 0.50 us;
- readout gains: 1000--10000 DAC broad backbone plus current in-range gain;
- X180 gains: from ground reference through a duration-scaled upper range, capped by
  the hardware limit;
- local readout and qubit frequency neighborhoods.

The schedule is duration-stratified. Under a runtime limit, every readout-length/sigma
pair gets mandatory central/interior gain coverage before any pair receives repeated
luxury measurements. This prevents an interrupted run from becoming a de facto
short-duration-only search because short cells happened to run first.

Coarse measurements generate candidates. Medium independent blocks and a local Matern
trust-region surrogate refine several basins. The surrogate may propose coordinates,
but it may never invent or select an unmeasured candidate. The archive remains
append-only and labels drift epochs.

The joint-search runtime budget is soft, currently 30 minutes with reserved time for
medium/control/final work. Upload time, retries, passive reset, and the later portfolio
can add substantial wall-clock time. Any runtime estimate must distinguish repetition
delay from compilation/network overhead.

### 5.11 Multi-candidate AAE and closure

Amplified amplitude error (AAE) applies repeated pulses at multiple depths to amplify
small coherent over/under-rotation. It refines frequency/gain around several promising
control basins, not just the current single winner. Boundary expansions are allowed;
a flat/noisy amplified map cannot authorize a movement.

AAE is not ALE and does not directly measure leakage. It is a coherent amplitude-error
calibration.

After AAE, coupled closure rechecks readout/control coordinates. This avoids the old
one-way chain in which changing one coordinate invalidated everything optimized before
it.

### 5.12 Ordinary final replay

Several candidate tuples receive fresh, repeated held-out step-5 measurements. The
best empirical full tuple is retained as `best_fidelity_replay` before any safety or
latency reasoning. Optional later failure must not erase it.

### 5.13 Constant-area pulse-family AAE

Before building the duration portfolio, the current revision constructs physical
control partners:

- `sigma * 0.5`, with approximately doubled gain;
- `sigma * 2.0`, with approximately halved gain;
- sigma constrained to 0.05--0.50 us;
- each predicted gain receives its own local measured axis;
- AAE refines these physical pulse families once because the X180 does not depend on
  the later readout integration length.

Area conservation is only a seed. Real hardware has transfer-function distortion,
AC-Stark shifts, nonlinearity, bandwidth limits, and multilevel dynamics. The measured
local optimum, not the inverse scaling formula, is authoritative.

### 5.14 Per-duration gain convergence

For each fixed readout duration:

1. Cross native same-duration readout basins with protected control basins.
2. Add local stochastic proposals around multiple basins.
3. Measure all candidates with equal refinement opportunity.
4. Challenge the provisional winner along an independent five-point readout-gain
   axis and independent five-point X180-gain axis.
5. Measure constant-area half/double-sigma partners with their own X180-gain axes.
6. Run a full 3x3 readout-gain/X180-gain interaction zoom.
7. If the winner lies at a gain edge, recenter and repeat, up to three rounds.
8. Protect historical same-duration and pulse-family champions in the exact replay
   shortlist.

The deterministic axes use fractional spans and a minimum 100-DAC step. This is why
future final gains should not be suspiciously tied to the original 1000-DAC backbone.

### 5.15 Interleaved exact requested-duration replay

In 1--20 us mode, the tuner does not finalize 1 us, then 2 us, then 3 us in twenty
isolated epochs. Exact finalists from all requested durations are combined into one
randomized round-robin held-out acquisition. Shared block/cohort identifiers make
paired comparisons possible and reduce the chance that slow device or discriminator
drift is mistaken for a readout-length effect. In fixed mode the same held-out path is
used for the single initialized duration; no other readout length is proposed.

This design is critical. Reverting to sequential per-duration finalization would make
the table visually complete but statistically misleading.

### 5.16 `Fmax` and `bal`

For every duration:

- `Fmax` is the exact candidate with the best common held-out fidelity rank. Leakage
  and control status do not rerank it.
- Several exact pulse-family finalists receive operational third-population screening
  and exact control audits.
- `bal` is considered only among candidates whose paired fidelity loss relative to
  `Fmax` is bounded by the configured 1 percentage-point margin at 95% confidence.
- Within that noninferior set, the ranking prefers better verified safety evidence,
  lower third-population risk, longer sigma, and lower X180 gain.
- If no distinct alternative qualifies, `bal` equals `Fmax` internally and no second
  table row is printed.

The operator should normally inspect both rows. A slightly lower mean fidelity does not
make `bal` worse when the difference is unresolved and it substantially reduces drive
stress. Conversely, `bal` is not allowed to hide a statistically meaningful fidelity
loss.

---

## 6. Leakage, third populations, AAE, ALE, and DRAG

These terms were repeatedly conflated during development. They are not interchangeable.

### 6.1 AAE

AAE means amplified amplitude error. Repeated coherent pulses turn a small angle error
into a larger population error. It is primarily a calibration of over/under-rotation
and can refine amplitude/frequency. It does not determine `P(f)`.

### 6.2 Operational third-population screen

The default basic tuner keeps the waveform family simple and evaluates whether the IQ
data support a third resolved population. It compares two- versus three-component 2-D
Gaussian-mixture descriptions, checks BIC improvement and cluster separation, and
reports conservative 95% upper bounds for:

- total third-cluster fraction;
- largest single-preparation third-cluster fraction;
- a legacy tail-excess statistic.

Default limits are approximately 5% total and 8% for one prepared state. Drifted
before/after discriminators trigger retries rather than automatically condemning the
pulse.

This catches patterns that a binary fidelity can miss, including a common-mode third
cloud in both nominal preparations. It is still an operational proxy. Possible causes
include real `|f>` population, thermal/mixed preparation, readout nonlinearity, reset
failure, switching artifacts, or unresolved drift.

The output deliberately says “not a direct P(f) measurement.” Do not remove that
qualification.

### 6.3 Strict direct qutrit leakage

The code contains an opt-in strict leakage path that:

- searches/confirms the e-f transition;
- calibrates independent long/narrow reference pulses;
- builds ground/e/f response references;
- uses shelving response inversion;
- measures one-pulse and amplified `P(f)` bounds;
- can search both DRAG signs;
- treats leakage constraints as hard feasibility conditions.

Default hard bounds are 2% for one-pulse `P(f)` and 3% for amplified `P(f)`.

This path is disabled by default because it is only trustworthy when the e-f line and
response matrix are independently identifiable. Defining the e reference with the
candidate pulse itself can absorb the candidate's leakage and make `P(f)` circularly
small. An old anharmonicity prior is not adequate evidence of a current e-f
calibration.

### 6.4 ALE and DRAG

The QUA amplitude-leakage-error style experiment is conceptually useful, but a robust
implementation needs trustworthy qutrit state discrimination or a carefully validated
return protocol. Repeated binary return error alone can also arise from detuning,
dephasing, amplitude error, reset error, or discriminator drift, so it must not be
labelled `P(f)`.

The current default operational path does not broadly optimize arbitrary waveforms and
does not tune DRAG (`operational_tune_drag=False`). `qubit_drag_beta` remains part of
the exact tuple and the strict direct mode can tune it. If a future agent enables DRAG
in production, it must:

- preserve both signs because mixer conventions change the physical sign;
- compare exact uploaded waveforms, not nominal beta alone;
- retain a pure-fidelity answer separately;
- prove that the leakage estimator is valid for that run;
- add hardware-path tests for waveform memory, reset coexistence, and final exact
  fingerprint matching.

---

## 7. Reset behavior and why it caused inconsistent results

### 7.1 Why active reset was attractive

The configured passive fallback can be 3000 us. At hundreds of thousands of shots,
that alone can contribute tens of minutes. Feedback reset can dramatically reduce the
idle cost.

### 7.2 Why active reset can corrupt an optimizer

A reset profile is bound to measurement coordinates. If the tuner changes readout
frequency or integration length while retaining an old raw threshold, the feedback
decision no longer has the same meaning. Additional failure modes include:

- reset gain accidentally following the scoring gain;
- the final scoring pulse not being restored after the reset pulse;
- insufficient photon clearing before the qubit pulse;
- incorrect `readouts_per_experiment` buffer accounting;
- using the last dmem word instead of the full shot distribution;
- a reset probe that passes while the actual ground/excited step-5 comparison collapses.

Several of these are covered by explicit regression tests because they occurred or
were credible on the actual QICK path.

### 7.3 Current fail-safe policy

- Cache a profile per readout frequency/integration signature, not per scoring gain.
- Freeze the reset waveform and restore the scoring waveform.
- Clear photons for 25 us.
- Qualify the complete tuple against passive preparation.
- Disable feedback after a catastrophic resolved loss.
- Use passive preparation for readout-coordinate maps where the feedback discriminator
  would move with the optimized coordinate.
- Preserve passive candidates in every later search.
- Treat passive fallback as slow but valid, not as a tuner failure.

Do not globally disable active reset unless hardware evidence shows the exact A/B guard
itself is insufficient. Doing so would make the portfolio much slower and reduce its
ability to average down uncertainty. Do not globally force active reset either.

---

## 8. Frequency priors and fast flux

### 8.1 Relative prior contract

The current default contract is symmetric and device-independent:

- resonator within +/-100 MHz of the initialized resonator frequency;
- qubit transition within +/-100 MHz of the initialized qubit frequency.

Optional absolute `search_min_mhz`/`search_max_mhz` values can override that contract
for a characterized study. There are no q4-specific absolute constants in the runner.

Examples:

- Initial readout 7200 MHz, actual 7249 MHz: inside policy and should be recovered.
- Initial readout 7429 MHz, actual 7249 MHz: outside policy and should not be promised.
- Bad starting gains or durations: allowed; discovery uses safe independent bootstrap
  settings and the joint optimizer spans gains/durations broadly.

The runner flag is intentionally applied to all four readout-length consumers:
`joint_search.read_lengths_us`, `duration_portfolio.read_lengths_us`,
`readout_length.values_us`, and the latency maximum. Disabling only the final table
would allow an earlier stage to keep optimizing other readout lengths and would violate
the operator's fixed-length request.

### 8.2 Flux is environmental context

The tuner should find the best pulse at the static flux point currently configured. It
does not need to know whether that point is called “park,” “baseline,” or a special
experiment bias. It does need to replay the same physical flux on every acquisition.

`ff_park_gain` and its channel are included in checkpoint/context validation so data
from one flux point cannot resume into another. Flux is never added to `TUNED_KEYS`.

---

## 9. Evidence hierarchy and failure semantics

### 9.1 Evidence hierarchy

From weakest to strongest:

1. input prior;
2. coarse averaged transmission/spectroscopy feature;
3. independently confirmed feature;
4. coherent Rabi basin;
5. direct single-shot candidate measurement;
6. repeated multi-block held-out candidate measurement;
7. exact interleaved final replay;
8. exact repeated-pulse/control audit;
9. exact operational or direct leakage/safety evidence;
10. atomic write certificate bound to the same full tuple and source config.

A lower tier may propose a candidate but must not veto stronger direct evidence without
a physically justified safety reason. A higher score from a lower tier must not evict a
qualified higher-tier basin.

### 9.2 Best found is not certified for write

The tuner deliberately distinguishes:

- `best_found`: strongest empirical tuple retained even in a partial run;
- `best_fidelity_replay`: best stable unconstrained fidelity replay;
- portfolio `selected`/`Fmax`: best fidelity row at a fixed readout duration;
- portfolio `balanced`: optional lower-stress noninferior alternative;
- `eligible_tuned`: only values satisfying the complete atomic write contract.

Warnings such as “safety not verified” or “control audit failed” do not mean the
reported fidelity was fabricated. They mean the evidence is incomplete for a stronger
claim.

### 9.3 Exit codes

The runner generally returns success when it has a useful measured candidate, even if
the portfolio is partial or not write-eligible. A nonzero code is reserved for cases
such as no measured candidate or failed critical transition qualification. Always read
the outcome and table; do not treat exit code zero as certification.

### 9.4 Optional-stage failure

An exception in a later refinement should:

- be recorded with stage/error details;
- retain every completed direct measurement;
- continue when the remaining work is meaningful;
- never promote partial evidence to write eligibility;
- never erase a previously stable replay.

This resilience is intentional. Earlier implementations aborted too aggressively and
made the tuner useless even when it had already measured a good pulse.

---

## 10. Configuration-write policy

`Client_modules/Runners/BasicAutoTune.py` currently sets:

```python
APPLY_CONFIG = False
```

The duration portfolio also declares manual-selection-only mode and disallows automatic
writes. The runner appends history and saves artifacts but leaves `BaseConfig`
untouched.

This overrides an earlier user request to update `initialize.py` automatically. The
later, more specific workflow request was to display twenty fidelity/leakage choices so
the operator could make a manual decision. The current report-only policy follows that
later request.

If automatic writing is requested again, do not merely flip the flag. First decide how
one portfolio row is selected and restore an atomic certificate for exactly these
fields:

- readout frequency, gain, and length;
- qubit and pi frequency;
- pi gain;
- sigma;
- DRAG beta.

The source-config hash and compare-and-swap guard must remain. Channel mappings, ADC
timing, switch state, fast-flux context, and other untuned physical settings must not
change between measurement and write. Never write a hybrid assembled from separately
best coordinates.

---

## 11. Output and how to read the 20-row table

The runner prints, for every readout length:

```text
len/type fidelity (95% LCB) leakage 95% UCB/status control readout ... X180 ...
```

Interpretation:

- `Fmax`: maximum common-cohort held-out binary assignment fidelity at that fixed
  readout length.
- `bal`: optional lower-stress pulse that passed paired noninferiority relative to the
  corresponding `Fmax`.
- fidelity: mean step-5 assignment fidelity.
- `95% LCB`: conservative fidelity lower bound.
- leakage UCB: usually operational third-population upper bound, not direct `P(f)`.
- leakage status `SAFE`: measured operational bound passed configured limits.
- `INCONCLUSIVE`: unavailable, drifted, or statistically insufficient screen; not the
  same as unsafe.
- `UNSAFE`: measured screen exceeded its bound.
- control `VERIFIED`: exact repeated-pulse/coherent audit passed for that tuple.
- control `FAILED`/`NOT_RUN`: fidelity remains reportable but the X180 interpretation
  is not certified.

Suggested manual choice procedure:

1. Reject or investigate rows with obvious third-cloud structure or `UNSAFE` status.
2. Prefer control-verified rows.
3. Compare fidelity confidence intervals, not only the fourth decimal place.
4. When `bal` exists with similar fidelity, prefer it if its longer/lower-drive X180
   materially reduces stress or third-population risk.
5. Choose the shortest readout only after it stays within the fidelity loss the
   experiment can tolerate.
6. Replay the selected exact tuple in TLS step 5 before committing it to a long
   experiment.
7. Preserve the diagnostic bundle and the selected row's full tuple.

The 20 rows describe a measured tradeoff surface. They do not establish a universal
readout ceiling: drift, different flux, hardware state, broader waveform families, or
better qutrit-aware control can improve the frontier.

---

## 12. Diagnostic artifacts

Every production run attempts to save:

- the compact experiment HDF5 (`*_Basic_Auto_Tune.h5`);
- a summary PNG;
- an atomic pickle checkpoint;
- a self-contained diagnostic HDF5
  (`*_Basic_Auto_Tune_diagnostics.h5`).

The diagnostic HDF5 is the most useful file to send to another agent. It includes:

- streamed per-shot raw IQ arrays;
- exact candidate coordinates;
- pulse fingerprints;
- compiled reset runtime metadata;
- acquisition timestamps;
- stage metadata;
- full final Python run-data pickle;
- JSON summary, parameters, input config, and SoC config representation;
- implementation revision and source SHA-256.

Load it with:

```python
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mBasicAutoTuner import (
    load_basic_autotuner_diagnostic,
)

bundle = load_basic_autotuner_diagnostic(path, load_raw=False)
data = bundle["run_data"]
manifest = bundle["raw_records"]
```

Use `load_raw=True` only when the IQ arrays are needed; the bundle can be large.

### 12.1 Minimum evidence to request after a bad run

Ask for:

1. the diagnostic HDF5, not only the console text;
2. the matching console log;
3. the summary PNG;
4. any manual TLS step-5 plot used as a benchmark;
5. the exact initialized tuple and static fast-flux point;
6. whether the run was interrupted;
7. revision/source hash from the bundle.

### 12.2 First diagnostic questions

For a missing prior best:

- Was the old tuple actually proposed and measured at that duration?
- Was it present in the exact replay shortlist?
- Did its pulse fingerprint match the manual program?
- Was reset passive or feedback for each measurement?
- Did exact feedback A/B pass?
- Were candidate and reference blocks interleaved?
- Did the IQ angle/midpoint drift?
- Was the apparent fidelity based on shared-ground proposal evidence or independent
  ground/excited blocks?
- Did a screen measure the selected exact tuple or a neighboring waveform?

For a third cloud:

- Is it present in ground, excited, or both preparations?
- Does the 3-component model beat the 2-component model by the configured BIC margin?
- Are clusters separated by the configured sigma threshold?
- Does the structure reproduce in held-out blocks?
- Does it move with readout gain/length, suggesting readout nonlinearity?
- Does it move with X180 gain/sigma, suggesting control-induced population?
- Does passive versus feedback reset change it?
- Is direct qutrit calibration available before calling it `P(f)`?

---

## 13. Testing

Run from `WorkingProjects/TLS_Spectroscopy`:

```bash
MPLCONFIGDIR=/tmp/mpl-basic-autotuner \
python3 Client_modules/Tests/test_basic_auto_tuner.py

python3 Client_modules/Tests/test_basic_joint_optimizer.py

python3 -m py_compile \
  Client_modules/Experiments/mBasicAutoTuner.py \
  Client_modules/Experiments/basic_joint_optimizer.py \
  Client_modules/Runners/BasicAutoTune.py \
  Client_modules/Tests/test_basic_auto_tuner.py \
  Client_modules/Tests/test_basic_joint_optimizer.py

git diff --check
```

At the time of the current revision, the full basic-autotuner suite and all seven
joint-optimizer tests passed.

### 13.1 Important regression categories

The tests cover, among other things:

- exact step-5 metric compatibility;
- common-mode and preparation-specific third-cloud detection;
- no false third cloud from splitting an ordinary tail;
- 1--20 us portfolio coverage and exact initialized-length fixed mode;
- fidelity-only `Fmax` ranking;
- safe/unsafe/inconclusive reporting;
- preservation of known historical winners;
- non-round deterministic gain challenges;
- half/double constant-area partners;
- paired noninferiority for balanced pulses;
- interleaved exact replay across readout lengths;
- strict shelving response inversion and independent qutrit references;
- AAE boundary expansion and flat-map rejection;
- active-reset buffer accounting, threshold calculation, waveform restoration, cavity
  clearing, profile binding, and exact A/B collapse detection;
- static fast-flux replay and rejection of dynamic excursions;
- +/-100 MHz relative-prior recovery;
- multiple resonator branches and stronger wrong-resonator backtracking;
- noise/monotonic transmission rejection;
- opposed spectroscopy confirmation and stronger-neighbor survival;
- coherent branch qualification;
- structured duration coverage under runtime limits;
- interrupt/partial-run preservation;
- exact waveform control certificates;
- atomic config writes and source-hash compare-and-swap.

### 13.2 What the tests do not prove

Most tests use a virtual device or injected acquisition backend. They prove logic,
candidate accounting, statistical policy, and failure handling. They do not prove:

- that a physical qubit is stationary during a long run;
- that the chosen IQ model matches every hardware artifact;
- that active reset works on every QICK firmware version;
- that an operational third cluster is actual `|f>`;
- that 30 minutes of configured acquisition fits into 30 minutes wall-clock;
- that synthetic spectral lines reproduce the exact asymmetry/noise of the device;
- that binary SS fidelity predicts RB fidelity.

Every substantial algorithmic change still needs a dry hardware run with diagnostics.

---

## 14. Known limitations and open problems

### 14.1 Hardware validation of revision v12 is still required

The selectable fixed-length mode, deterministic gain zoom, constant-area family,
global pulse-family AAE, balanced row, and interleaved 20-duration exact replay passed
regression tests but need hardware validation. The key empirical questions are:

- Do final gains move off the coarse round backbone when the hardware optimum is
  between points?
- Does the known approximately 90--94% basin remain represented at longer readout
  lengths?
- Do paired blocks prevent the same duration from swinging between 93% and 50% without
  an explicit drift warning?
- Does a longer/lower-drive `bal` row reduce the visible third population?
- Is runtime acceptable with passive fallback?

### 14.2 Operational leakage remains a proxy

The default table cannot answer “what is `P(f)`?” It answers whether the IQ data support
a resolved third population under a controlled statistical model. A high-quality
direct qutrit calibration remains future work if the device and readout support it.

### 14.3 Binary fidelity can remain misleading

A two-cloud classifier can assign leaked or thermally excited shots to the excited
side. Even a control-verified `Fmax` is not a complete gate-quality measure. RB,
interleaved RB, cycle benchmarking, or gate-set-aware methods would be needed for a
different claim. The user explicitly did not require RB for the basic tuner.

### 14.4 Runtime remains substantial

Twenty durations, multiple pulse families, deterministic gain axes, zooms, exact
replays, safety screens, and control audits are expensive. The current design chooses
reliability and inspectable coverage over a deceptively quick answer. Future runtime
work should use adaptive allocation only if it preserves:

- coverage of every requested duration;
- protected known basins;
- shared interleaved final evidence;
- uncertainty estimates;
- exact-tuple safety/control association.

Do not cut runtime by dropping long readouts first, using one gain for every duration,
or skipping held-out replay.

### 14.5 The default pulse family is limited

The search uses a canonical four-sigma Gaussian plus optional DRAG metadata. It does
not optimize arbitrary waveform samples, derivative order, Wah-Wah pulses, cosine
edges, or optimal-control shapes. More waveform freedom may reduce leakage but greatly
increases calibration dimensionality and waveform-path failure modes.

### 14.6 Dynamic fast-flux calibration is unsupported

Only a static configured park is replayed. If the desired pulse occurs during a
time-dependent flux excursion, the tuner needs a new program and a definition of where
in that waveform spectroscopy/readout/control happen.

### 14.7 Frequency identity is physical, not semantic

Coherent Rabi proves a controllable transition. It does not, by itself, name that
transition q4 rather than a nearby coherent TLS. The +/-100 MHz prior and branch
association are practical constraints, not absolute semantic identity. If multiple
coherent branches exist, the operator may still need flux dependence or other device
knowledge.

### 14.8 Long-run nonstationarity cannot be eliminated in software

Interleaving and paired comparisons reduce drift bias but do not make a changing device
stationary. The correct response to clear nonstationarity is to report it and preserve
the time-resolved evidence, not average incompatible epochs into a falsely precise
number.

---

## 14A. What `run-health-v13` changed and why

v12 and earlier were epistemically careful and operationally blind. Three measured
facts motivated this revision.

### 14A.1 The workload estimate was wrong in both directions

`_estimate_default_measurement_repetitions` never counted the structured joint search
— by far the largest single cost — while it did count `_stage_readout_length`,
`_stage_qubit_grid`, `_stage_pulse_duration` and the `coordinate_descent_repeat`
closure. Those four stages are not reachable from `acquire()`; the joint search
replaced them. The two errors partially cancelled, which is why the number looked
plausible. The estimate was also printed only in `detailed` console mode, so a
production operator never saw it at all.

Corrected figures for the shipped defaults, at the configured 3000 us passive
relaxation delay and counting repetition delay only (no compile/upload overhead):

```text
RUN_1_TO_20_US_MODE = True   ~4.4M repetitions   ~3.6 h of pure idle
RUN_1_TO_20_US_MODE = False  ~1.4M repetitions   ~1.2 h of pure idle
```

The resonator term also undercounted: every coarse notch is confirmed on every trial
readout, so the multiplicity is candidates x trials, not trials alone.

The estimate is now computed unconditionally, stored as `planned_repetitions` and
`planned_passive_idle_hours`, and printed in concise mode before the first
acquisition. An operator should be able to decline a four-hour run before it starts.

### 14A.2 The mandatory coverage pass silently starved the refinement tail

`joint_search` reserves `reserve_medium_minutes` (6) and
`reserve_control_refinement_minutes` (7) out of a 30-minute soft budget so the
held-out medium replay and the trust-region refinement always run. Separately,
`minimum_duration_coverage_passes` (3) made the first three readout-power passes
mandatory and exempt from the budget check.

With 20 readout lengths and 6 sigmas there are 120 strata per pass. One coarse cell is
15 gain points x 56 shots = 840 repetitions, about 2.5 s of idle. Three mandatory
passes are therefore roughly 15 minutes of idle plus 360 program uploads — which
exhausts the 18-minute threshold that gates the medium stage. The exempt mandatory
block consumed the budget that had been explicitly reserved for the stages that
produce tier-2/3 evidence, so `medium_rows` and `trust_rows` came back empty and the
portfolio was seeded from tier-0 shared-ground coarse rows.

This is a second, still-live mechanism behind failure H in section 4.3. It was
invisible because both effects are silent: the budget check simply returns false and
`_run_stage` records nothing.

The loop now times each completed coverage pass and, at a pass boundary, refuses to
start another mandatory pass whose measured cost would eat the reserved tail. At
least one complete pass always runs, so every duration stratum is still measured. The
reduction is recorded as `mandatory_duration_passes_requested` versus
`mandatory_duration_passes`, plus `mandatory_coverage_reduced_for_budget` and the
per-pass timings in `coarse_pass_minutes`. Nothing is capped silently.

### 14A.3 A degraded run looked exactly like a good one

`_run_stage` downgrades every non-`KeyboardInterrupt` exception to a warning row, the
budget checks skip stages without comment, and each portfolio row already recorded
whether it came from a complete interleaved replay — but none of that reached the
operator. A run could lose spectroscopy confirmation, fall back to passive reset, skip
the medium replay, seed five lengths from coarse proposals, and end the gain zoom on
an axis edge, and still print a clean twenty-row table and exit zero.

`data["run_health"]` now records, and `BasicAutoTune.py` now prints, a `RUN HEALTH`
block: warned stages, the reset mode actually used, joint coverage and mandatory-pass
accounting, medium/trust row counts, per-length selection basis, lengths seeded
without any held-out readout basin, and lengths whose gain zoom never converged.
`degraded` is true whenever any of those concerns fired. Read this block before the
table.

`_portfolio_candidates_for_length` additionally reports `source_max_evidence_tier`,
`source_held_out_row_count` and `readout_seeded_from_proposals_only` so the degraded
seeding in 14A.2 is attributable per readout length rather than inferred.

### 14A.4 Readout-phase alignment before the feedback threshold probe

The tProc feedback decision is a one-dimensional `condj` comparison against a single
32-bit half of the readout accumulator (`oper='lower'` or `'upper'`). When the g/e
separation straddles both quadratures that comparison is weak regardless of readout
SNR, and `probe_reset_params` rejects the profile on either of its two gates:

```python
purity_ok = max(lower, upper) >= 3 * max(1, min(lower, upper))
raw_fidelity >= min_raw_fidelity            # 0.80 for this tuner
```

The tuner previously inherited `BaseConfig["res_phase"]` without ever calibrating it,
so a misaligned angle silently forced every acquisition onto the 3000 us passive
fallback — the difference between minutes and hours of idle.

`_calibrate_reset_phase` now runs the existing `Helpers/reset_phase.calibrate_res_phase`
sweep once, from `_try_activate_feedback`, immediately before the first threshold
probe. It is called with `apply_config=False`: the aligned angle is applied to
`input_cfg` for the run only and never written to `initialize.py`, because this runner
is report-only.

Binary step-5 fidelity is invariant under a global IQ rotation — `step5_metrics` fits
`theta = angle(center_e - center_g)` from the data and projects along it — so the
alignment cannot move the optimizer's objective. That invariance is what makes this
safe to add inside a fidelity search.

Alignment is deliberately run-scoped rather than per reset profile, even though the
resonator phase response across its linewidth means a wide readout-frequency search
can de-align it:

- per-profile alignment costs roughly 19k repetitions per profile, comparable to the
  entire duration portfolio;
- a mid-run `res_phase` change rotates `read_theta` and would trip the
  `calibration_drift.max_angle_degrees` (25) guard, manufacturing spurious
  discriminator-drift failures in the control-verify, parity and leakage stages;
- one run-scoped value keeps both arms of the exact passive/feedback A/B on an
  identical compiled program, which is the property that guard exists to protect.

A profile that still fails purity falls back to passive exactly as before, and the
RUN HEALTH block reports it. Note that the aligned angle changes the compiled pulse
fingerprint relative to a manual step-5 run using the `initialize.py` value; the
calibration record stores `aligned_pulse_signature` so the section 16 fingerprint
comparison stays traceable.

### 14A.5 Unreachable stages that still look live

`readout_length`, `pulse_duration`, `qubit` and `readout.local_*`, plus
`coordinate_descent_repeat`, configure stages `acquire()` never calls. They were left
in place because `configure_readout_length_mode` and the runner's write contract still
read some of them, but they configure nothing that runs. Do not tune them expecting an
effect, and do not reintroduce them into the cost model.

---

## 15. Rules for future changes

Treat these as invariants unless new hardware evidence and tests justify changing them.

1. Never gate the search on input fidelity.
2. Never hardcode q4's current resonator or qubit frequency in the generic tuner.
3. Never accept a frequency outside the configured prior padding as though it were
   inside policy.
4. Never select the deepest resonator dip without qubit-branch confirmation.
5. Never call a spectral feature a qubit solely because it is strong.
6. Never let a weak preliminary test veto a stronger downstream coherent witness.
7. Never let a rough pulse-quality audit substitute for final exact-waveform control
   certification.
8. Never optimize final readout and X180 coordinates only one at a time.
9. Never accept coarse round gains without a deterministic local axis challenge.
10. Never assume inverse gain-duration scaling is exact; measure around it.
11. Never call AAE a leakage measurement.
12. Never call an IQ third cluster `P(f)` without response calibration.
13. Never let leakage silently rerank or hide the pure-fidelity `Fmax` result.
14. Never prefer a faster pulse unless fidelity loss is explicitly bounded.
15. Never compare twenty sequential final epochs as if they were simultaneous; retain
    interleaved block evidence.
16. Never allow active reset to affect scores without exact passive/feedback A/B
    qualification.
17. Never erase a completed direct candidate because a later optional stage failed.
18. Never transfer a control/leakage certificate between nonidentical tuples.
19. Never write a partial or hybrid configuration.
20. Never treat exit code zero as proof of certification.
21. Never diagnose hardware drift before excluding software path, reset, candidate
    accounting, and discriminator drift.
22. Never make diagnostic I/O authoritative; a disk failure should be recorded but
    should not change the physical optimizer result.
23. Never resume a checkpoint across revision, input-tuple, or fast-flux-context
    mismatch.
24. Never remove the user-readable 20-row table in favor of one opaque scalar score.

---

## 16. Troubleshooting decision tree

### Symptom: resonator is obviously wrong

1. Check whether the known line is inside the configured +/-100 MHz prior.
2. Inspect the broad transmission trace, not only the selected candidate.
3. Check the safe discovery gain/length were actually compiled.
4. Confirm the line is not at the forbidden padded edge.
5. Inspect all confirmed resonator candidates and their widths/contrasts.
6. Determine whether the selected resonator had a coherent qubit branch.
7. Verify the backtracking stage did not fail or time out.
8. Do not proceed to an expensive joint run around an unqualified branch.

### Symptom: qubit frequency is wrong

1. Check whether the actual line lies inside the qubit prior.
2. Inspect both opposed spectroscopy passes.
3. Check for a stronger nearby TLS hiding a shoulder.
4. Inspect every retained spectral basin's Rabi map.
5. Reject a strong nonoscillatory line.
6. Verify the coherent basin was not evicted by a later rough SS tie.
7. If multiple coherent branches remain, do not pretend software can name them without
   additional physical evidence.

### Symptom: manual step 5 is 90% but tuner replay is much worse

1. Compare exact full tuple, including sigma and DRAG.
2. Confirm `qubit_gain` and `qubit_pi_gain` compiled identically.
3. Compare pulse fingerprints.
4. Compare passive versus feedback reset mode.
5. Inspect exact reset A/B validation and photon-clear delay.
6. Compare shot counts and whether the tuner result was one block or held-out replay.
7. Check IQ angle/midpoint drift and fixed-discriminator loss.
8. Inspect raw clouds in the diagnostic bundle.
9. Replay the exact tuner tuple in TLS step 5 and the exact manual tuple through the
   tuner backend in an interleaved A/B experiment.
10. Do not invoke a device ceiling until the program paths match.

### Symptom: gains are round

1. Check `autotuner_revision` is `run-health-v13` or later.
2. Inspect deterministic gain-refinement axes in the duration entry.
3. Confirm the final row came from `complete_duration_interleaved_exact_replay`.
4. Check whether zoom rounds ran and whether the winner remained on an edge.
5. A round winner is acceptable only if neighboring non-round gains were measured.

### Symptom: one duration was 93% and later becomes 50%

1. Compare timestamps and block/cohort identifiers.
2. Verify both came from independent exact ground/excited blocks.
3. Inspect reset runtime and exact A/B status.
4. Check whether the older tuple survived into the exact shortlist.
5. Check the passive bootstrap was preserved.
6. Compare IQ centroid motion and discriminator drift.
7. Look for a common-mode third cloud or state-preparation collapse.
8. Require an interleaved replay before declaring one measurement “correct.”

### Symptom: high fidelity but visible third cloud

1. Remember that binary fidelity can count the third cloud as excited.
2. Inspect total and single-preparation third-cluster UCBs.
3. Compare `Fmax` with a longer/lower-gain `bal` row.
4. Sweep X180 duration/gain at roughly constant area.
5. Sweep readout gain/length separately to distinguish measurement-induced structure.
6. Compare passive and feedback reset.
7. If a direct qutrit claim is needed, calibrate e-f and independent response
   references; do not relabel the operational proxy.

### Symptom: run is taking too long

1. Check whether active reset qualified or passive 3000 us fallback is in use.
2. Separate idle-delay estimate from upload/network overhead.
3. Check repeated point failures and retries.
4. Check whether gain zooms repeatedly hit edges.
5. Do not terminate without preserving the diagnostic/checkpoint files.
6. If reducing the budget, preserve mandatory all-duration coverage and final
   interleaving.

### Symptom: no 20-row table

1. Inspect `outcome` and `pre_expensive_gate`.
2. Verify resonator and spectroscopy discovery flags.
3. Check whether at least one coherent transition basin qualified.
4. Distinguish a true frequency-qualification failure from an optional rough-control
   warning.
5. Check for operator interruption or a hard acquisition exception.
6. Use the diagnostic bundle to locate the last completed stage.

---

## 17. Code map

Primary files:

- `Client_modules/Experiments/mBasicAutoTuner.py`
  - hardware programs;
  - default policies;
  - discovery, optimization, reset, AAE, leakage, portfolio, persistence;
  - diagnostic loader.
- `Client_modules/Experiments/basic_joint_optimizer.py`
  - immutable candidate representation;
  - append-only archive;
  - duration-stratified shortlist;
  - trust-region proposals;
  - structured coverage validation;
  - latency/noninferiority helpers.
- `Client_modules/Runners/BasicAutoTune.py`
  - device runner;
  - concise console output;
  - manual 20-row table;
  - history and write-boundary checks;
  - `APPLY_CONFIG=False`.
- `Client_modules/Tests/test_basic_auto_tuner.py`
  - integrated policy, virtual-device, failure, reset, discovery, safety, and runner
    tests.
- `Client_modules/Tests/test_basic_joint_optimizer.py`
  - optimizer data-structure and selection tests.

Important shared dependencies:

- `Client_modules/Experiments/mSingleShot1Q.py`
- `Client_modules/Experiments/mRabiChevronSS.py`
- `Client_modules/Experiments/mRabiChevronIQ.py`
- `Client_modules/Helpers/active_reset.py`
- `Client_modules/Helpers/ff_pulse.py`
- `Client_modules/Helpers/pulse_setup.py`
- `Client_modules/Helpers/ss_helpers.py`
- `Client_modules/Helpers/config_updater.py`
- `Client_modules/Runners/TLSSpectroscopy.py`
- `Client_modules/Calib/initialize.py`

Any local change to these shared pulse/reset helpers can affect the basic tuner even if
`mBasicAutoTuner.py` itself is untouched. Compare pulse fingerprints and rerun the
basic tuner tests after shared-helper changes.

---

## 18. Relevant commit history

The progression is useful when bisecting a regression:

```text
7973bf6 Add a resilient manual-workflow auto tuner
c324bbf Add the active-reset thermalization wait and finish the basic auto tuner
2118bb5 Apply the active-reset cavity wait everywhere
77168ad Streamline leakage screening in the basic auto tuner
2611edd Keep basic tuner fidelity and safety checks separate
f641faa Make the basic tuner recover from bad starting calibrations
263e2b3 Optimize the basic tuner for the shortest high-fidelity pulse chain
d04b979 Search pulse and readout parameters together in the basic tuner
167bd9c Backtrack across resonator candidates before choosing the readout
cfeb797 Report leakage-aware calibrations for every readout length
50644c1 Qualify the qubit transition before the full autotune
16722d5 Let qualified qubit transitions reach the full autotune
15054b8 Make the duration portfolio fidelity first
d7cae4f Save complete autotuner diagnostics
7203fd5 Qualify feedback reset by exact A/B and protect the passive control seeds
68f29ce Add deterministic gain zoom and pulse-family screening to the basic autotuner
```

The commit subjects describe the recurring tension: resilience versus certification,
frequency certainty versus overly strict early gates, pure fidelity versus leakage,
speed versus lower-drive pulses, and active-reset runtime versus path fidelity.

---

## 19. Recommended next hardware validation

The next agent should not begin by adding another optimizer layer. First run the current
revision and answer these falsifiable questions from one complete diagnostic bundle:

1. Does discovery recover the known resonator/qubit basin from deliberately imperfect
   but in-contract frequency priors?
2. Does the exact manual benchmark tuple reproduce through the tuner backend under
   passive reset?
3. If feedback qualifies, does an interleaved passive/feedback A/B show no meaningful
   loss or cloud deformation?
4. In broad mode, does every 1--20 us duration have a reportable exact replay? In
   fixed mode, is the initialized readout length the only duration measured by the
   optimization stages?
5. Does the known long-readout high-fidelity basin survive the shortlist and appear in
   the final cohort?
6. Are final readout/X180 gains locally challenged and not merely inherited from the
   broad lattice?
7. Do constant-area longer pulses achieve statistically similar fidelity at lower
   gain?
8. Does the operational third-population UCB agree qualitatively with the plotted IQ
   clouds?
9. Does a distinct `bal` row appear where appropriate, and is its fidelity comparison
   genuinely paired?
10. Are any remaining failures due to hardware acquisition, program compilation,
    statistical uncertainty, or policy? Label them precisely.

Only after those answers should the design be expanded. If the current implementation
still cannot reproduce the manual benchmark, the highest-value experiment is a minimal
interleaved exact-path A/B between TLS step 5 and the tuner backend, with raw buffers,
compiled configs, pulse fingerprints, and reset disabled. More global optimization is
not a remedy for two programs playing different pulses.

---

## 20. Final perspective

The repeated failures were not caused by a lack of optimization vocabulary. They were
caused by violating measurement discipline:

- trusting nominal parameters instead of compiled physical paths;
- allowing the input baseline to gate a search;
- anchoring discovery too locally;
- selecting the strongest feature without branch physics;
- optimizing coupled coordinates sequentially;
- discarding earlier good measurements after later failures;
- confusing active-reset validation with objective validation;
- optimizing speed before defining an acceptable-fidelity set;
- using binary fidelity as a leakage metric;
- comparing long sequential epochs as if the device had not moved;
- accepting coarse round gains without local convergence evidence.

The current architecture is designed around the opposite principles: broad but bounded
discovery, coherent branch qualification, exact step-5 measurements, append-only
evidence, structured coupled search, deterministic local gain challenges,
constant-area pulse families, AAE, interleaved held-out replay, separate fidelity and
safety reporting, exact reset A/B qualification, and report-only manual selection.

That architecture should be simplified only when a proposed simplification preserves
those protections and is supported by real diagnostic evidence. The goal is not to
make the tuner appear confident. The goal is to make every confidence claim traceable
to the exact pulse that was actually measured.
