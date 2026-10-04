# q3 afterglow spectrum versus wall-clock time — 2026-10-04

## Purpose and first run

Repeat a fixed-grid, same-frequency loading/probing spectrum to look for
loading-dependent energy return that persists or appears intermittently.
This is a blind afterglow screen: it does not select a T1 loss line or require
two qualified sites. Earlier limited nulls at selected sites motivate mapping
more frequencies; they do not establish that no long-lived storage exists.

Stop any q4 acquisition using the same RFSoC before running this command on
the measurement PC:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSAfterglowTimeMap --run
```

Default: **one pass, 4.000–4.050 GHz inclusive, 2 MHz spacing, 400 shots per
condition**. There are 26 frequencies and six conditions per frequency:
62,400 paired science records, each containing two IQ readouts. Initial and
final references add 7,200 paired records. Science recovery time alone is
5.2 minutes; references add at least 0.6 minutes. Allow roughly **8–12 minutes**
including compilation, transport and saving, pending measurement of actual
throughput. The science progress bar reports elapsed time and ETA; initial
preflight and reference acquisition happen before the bar starts.

Inspect this pass and its independent references before starting continuous
acquisition. The eventual repeating command is:

```bash
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSAfterglowTimeMap --run --continuous
```

`--plan` prints the request without connecting to hardware. Band, spacing,
shots and finite pass count are adjustable with `--freq-start`, `--freq-stop`,
`--step-mhz`, `--shots`, and `--passes`. Requests exceeding 30 minutes of
minimum science recovery time per pass are rejected before connection, so
references cannot silently become separated by hours. This is a workload
bound, not a guarantee that total elapsed time is under 30 minutes.

## Pulse sequence and interpretation

Reuse the measured `TLSAfterglowDiagonal.DiagonalProgram` hardware sequence:

1. Prepare hot/cold at park using a calibrated pi pulse or a matched zero-gain
   pulse; visit the scanned frequency for 10 us.
2. Complete the compensated 40-us return to park. Read out and retain IQ as
   the ground herald.
3. Make the matched ground-probe excursion to the same frequency, dwell for
   0.1, 10 or 40 us, return and perform the final readout.
4. Use the inherited 5-ms recovery between conditions.

The hardware collects all shots. Ground heralding is performed offline on
the first readout; there is no new feedback reset. Consequently this is an
adaptation of the afterglow idea, **not the paper's feed-forward protocol**.
The gap from loading to probing includes the 40-us return, herald readout,
guard and next preparation/arrival. This screen cannot exclude memory that
decays during that gap. The cold arm is a matched ground-prepared loading
visit, rather than the absence of an excursion.

At each probe delay save the hot-minus-cold conditional excited fraction.
Also save growth relative to the 0.1-us probe:

```text
growth(t) = [hot(t) - cold(t)] - [hot(0.1 us) - cold(0.1 us)]
```

Growth is the main control against a positive offset from qubit carryover.
Continuous-IQ contrasts, all-shot fractions, herald acceptance and statistical
errors are retained alongside it. A positive conditional fraction alone is
not evidence of deposited energy returning. These classified fractions are
not absolute SPAM-corrected populations, and no lifetime is fitted. A
reproducible growth signal would justify controls for broad heating, readout
effects, selection bias and qubit carryover before attributing it to an
individual TLS. At 400 shots this pilot is a throughput/reference check and
a screen for sizeable signals; a null is not a high-precision exclusion.

## References, ordering and files

Initial references calibrate separate herald and final-readout axes using
three paired reference arms, 1,200 shots each. Axes remain frozen throughout
the session. Independent references at each pass boundary validate those
axes. Initial failure stops before science; post-reference failure preserves
the acquired pass, marks its controls invalid and stops repetition. References
are not repeatedly retried until a preferred answer appears.

Frequency order and the six-condition order reverse on alternate passes.
The fixed frequency grid is preserved even when no loss line is visible.
CSV is updated after every completed frequency; plots update at pass
boundaries and finalization. Requested and realized frequencies, flux gains,
per-cell start/end times and science-pass intervals are saved.

Each session lives under the usual NAS q3 folder with prefix
`q3_afterglow_time_map_`. Outputs include:

- `afterglow_vs_wall_clock.csv`: contrasts, uncertainties, accepted counts,
  reference quality and actual timestamps.
- `afterglow_vs_wall_clock.png`: three excess-return panels.
- `afterglow_growth_vs_wall_clock.png`: growth panels for 10 and 40 us.
- `afterglow_latest_spectrum.png`: latest-pass contrasts with error bars.
- Raw paired IQ `.npz` files, per-program metadata, `manifest.json`,
  `summary.json`, source snapshots, config and board configuration.

Map strips span each sequential science pass; frequencies were not measured
simultaneously. Timestamps in the CSV enable more detailed temporal analysis.
Plots use a fixed signed color scale of +/-0.15 with saturation indicators.
Missing frequencies and invalid-reference passes remain blank; pending
references are explicitly provisional. No missing cells are interpolated.

Ctrl+C aborts hardware before finalizing outputs. Completed cells are retained;
already transferred banks from the interrupted program are saved to
`.partial.npz`, trimmed to complete logical shots. Untransferred board data
cannot be recovered. There is no automatic restart or reacquisition. File
publication retries Windows access conflicts quietly, without retrying
measurements. The terminal uses SS calibration messages, the progress bar
and final status/path; checkpoint/compile details go to session log files.

## Scope and verification

Only a new runner, tests and documentation are added. The runner enters the
existing temporary q3 configuration context and restores it afterward.
Production TLS spectroscopy, shared active reset, initialize.py and the q4
runner are unchanged. The host-only subclass retains transferred IQ banks;
it does not override hardware sequence generation.

Offline verification used pinned QICK 0.2.133 and the saved q3 board/config
snapshot. All **58** default science/reference programs compiled, and their
binaries matched the original diagonal program exactly. Maximum instruction
count was **4,211 / 8,192**; waveform memory also fit. The local NumPy 2 audit
required an audit-only integer-cast compatibility proxy for the older
assembler; no such patch was made to acquisition code.

Synthetic transport tests covered two successful passes, interruption with
transferred-bank recovery, failed post references and failed initial
references. They verified saved raw data, classifications, quality masks,
abort behavior, fixed-grid plots and restoration of the configuration
context. Synthetic plots were visually inspected. These checks establish
software behavior, not a measured afterglow signal or successful hardware run.

The final maintained `tests/` suite passed: **1,395 tests in 35.73 seconds**.
Bare repository-wide pytest also encounters six unrelated collection errors:

- Archive/q4diamond and WorkingProjects/Inductive_Coupler `Timing_test.py`:
  QICK is absent from the local default Python environment.
- Tantalum_fluxonium_escher `Calib_escher/Experiment_test.py`: unavailable
  local proxy/name-server object.
- Tantalum_fluxonium_escher `mFFDelayedTransSlice_test.py` and
  `mFFSpecSlice_test.py`: PyQt5 is absent.
- Tantalum_fluxonium_marvin `mTransmission_GUI_test.py`: duplicate test-module
  import name conflicts with the escher module.

An independent code review checked interruption recovery, finalization and
hardware-sequence inheritance; its blocking findings were resolved before
the final checks. Local audit outputs are under
`/tmp/q3_afterglow_time_map_check/` and maintained-suite output is
`/tmp/q3_afterglow_time_map_maintained_tests_final.log`.

## First measured pass: 20261004T193258Z_8af4b9b7

The finite pass completed on commit `fbc8334b`: all 26 frequencies, 62,400
science records and 7,200 reference records, in **376.94 seconds** overall.
Science acquisition took 330.67 seconds. Both boundaries passed. Herald
reference fidelity was 91.17% initially and 91.71% on the frozen axis at the
end; conditioned final-readout fidelity was 78.36% and 78.35%. These are the
paired sequence's reference scores, not a separate standard SS-cal result.
All 78 frequency/delay cells met the accepted-shot threshold. Counts ranged
from 86 to 330 of 400 (median 247.5); hot arms often have substantially fewer
accepted shots than cold arms because the qubit retains excitation.

All saved summaries, both reference reports, source hashes and final summary
rows reproduce from the saved raw IQ. Independently reconstructed paired
influence variances reproduce every growth error.

There is **no confirmed afterglow signal**. The strongest growth is at
4.034 GHz, 40 us: **+17.29 +/- 6.33 percentage points** (one SE), with direct
hot-minus-cold excess **+11.11 +/- 4.80 points**. It is 2.73 SE in growth;
an approximate one-sided normal Bonferroni correction over the 26 x 2
frequency/delay search gives p=0.164. This is exploratory triage, not a
calibrated discovery test. The continuous-IQ growth has the same sign
(0.309 +/- 0.094 of the reference separation), but is computed from the
same shots and is not independent confirmation. All-shot growth is smaller.

As a descriptive selection-sensitivity check at 4.034 GHz, lowering the
excited-reference tail admitted by the herald from 5% to 2.5% changes growth
to +11.60 +/- 7.58 points; at 1% it is +12.49 +/- 12.16 points. Positive
direction survives, but the accepted sample shrinks. This neither proves nor
excludes selection bias. The second classified-growth hint, 4.042 GHz at
10 us (+15.58 +/- 5.89 points), has a weak IQ counterpart and is less persuasive.

Next take **three finite passes on the unchanged grid at 400 shots**, roughly
18--20 minutes at the measured throughput. Alternating frequency and arm
order will test reproducibility and provide multiple wall-clock map rows.
Treat 4.034 GHz/40 us as the prespecified primary repeat target, while
retaining the blind grid if the spectrum shifts. Do not expand into a
two-frequency experiment or infer a lifetime from this pass.

```bash
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSAfterglowTimeMap --run --passes 3
```

Audit script, raw snapshot, numerical report and inspected spectrum/map plots
are saved under
`~/.codex/visualizations/2026/10/04/q3_afterglow_time_map_193258Z/`.

## Three-pass repeat: 20261004T202506Z_c3e9f87d

Completed **78 frequency/pass cells**, 187,200 science records and 14,400
reference records in **1,111.46 seconds (18m31s)** on commit `725e8fc5`.
All four reference boundaries passed, including the independent frozen-axis
checks after each pass. Every frequency/delay contrast met the acceptance
threshold; accepted counts ranged from 95 to 362 of 400, median 280.5.
All source hashes, 78 raw cell summaries, four reference reports and final
summary rows reproduce. Independent reconstruction of paired influence
variances reproduces every growth error. A higher final-reference fidelity
than in the first session does not establish identical population calibration
between sessions; these remain classified fractions.

The prespecified **4.034 GHz, 40-us hint did not reproduce**. Growth in the
ascending/descending/ascending passes was **+3.62, -9.25, -5.69 points**.
The three-pass mean is **-3.78 +/- 3.84 points**, with the error taken as the
larger of paired-shot SE and between-pass disagreement SE. Direct excess
averages -0.06 +/- 2.39 points. Continuous-IQ growth also averages negative.
Do not pool the initial exploratory peak into the independent repeat and
claim confirmation, or interpret this as a proof that the site cannot have
intermittent memory.

No pooled point establishes afterglow across the blind 52-comparison search.
The largest pooled positive growth is **4.046 GHz, 10 us**, at
**+7.60 +/- 3.05 points** (2.49 SE; approximate normal one-sided Bonferroni
p=0.329 over 52 comparisons). Its three growth values are **+3.63, +10.07,
+9.11 points**; direct excess averages **+6.74 +/- 2.57 points** and IQ
growth **0.128 +/- 0.048 of reference separation**. The IQ check shares the
same shots. Nearby-frequency direct-excess localization is not consistent
in every pass, so neither this candidate nor its apparent persistence should
be called a localized TLS signal.

The time map now contains three sequential science strips, separated by
reference measurements. Each strip is a frequency sweep lasting about
5.5 minutes, not a simultaneous spectrum. The apparent vertical continuity
within one strip is a plotting convention; point timestamps remain in CSV.
The combined-spectrum errors include a pass-disagreement floor and are
descriptive, not calibrated discovery intervals.

Next use one bounded independent confirmation of the remaining candidate:
**4.040--4.050 GHz, 2 MHz spacing, 2,000 shots/condition, two passes**.
Keep the 4.046 GHz/10-us growth as the primary endpoint selected before this
new run; neighboring points are drift/localization controls. The sequence
and analysis stay unchanged. Require positive direct excess, growth and IQ
growth in both scan orders, and pooled primary growth exceeding three times
the larger of paired-shot SE and pass-disagreement SE, before extending to
off-target loading controls. This is a screening decision rather than a
discovery claim. Comparing
to both neighboring frequencies is needed before claiming localization;
even a repeat would not by itself identify an individual TLS. If the
independent repeat is null or contradictory, close this candidate rather
than promoting another fluctuation from the same screen.

At observed throughput the two-pass confirmation should take **13--15
minutes**: 144,000 science records with 12 minutes minimum recovery time,
plus 10,800 reference records. All 21 science/reference programs were
compiled offline on the newly saved board snapshot before the command was
issued, with binary identity against the existing diagonal sequence and
maximum 4,211 of 8,192 instructions.

```bash
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSAfterglowTimeMap --run --freq-start 4.040 --freq-stop 4.050 --step-mhz 2 --shots 2000 --passes 2
```

Raw snapshot, numerical audit, independent analysis and inspected plots:
`~/.codex/visualizations/2026/10/04/q3_afterglow_time_map_202506Z/`.

## Revised priority: broadband search

The user correctly prioritized coverage over following another weak peak.
The proposed six-frequency 4.046-GHz confirmation is superseded as the next
measurement. The paper reports long-lived TLSs spread across 3--4.5 GHz;
it supplies motivation for a blind broad search, not a physical reason to
privilege 4.046 GHz. Its density and signal visibility cannot be transferred
to q3. Reference: https://arxiv.org/html/2609.31280v1, Fig. 3 and associated
discussion. Our 50-MHz screen covered only one tenth of the usual accessible
band, and the corrected-return/herald gap still limits sensitivity to
shorter-lived energy storage.

Next take one pass of each **3.800--4.050 GHz** and **4.050--4.300 GHz**,
2 MHz spacing, 400 shots/condition. The shared 4.050-GHz point provides an
overlap between sessions. Each half has 126 frequencies and 302,400 science
records (25.2 minutes minimum recovery time), below the 30-minute per-pass
workload limit. Each half has independent initial and final references.
Allow roughly **55 minutes total** at measured throughput. Keep 0.1/10/40-us
probes, raw-IQ saving and the current matched hot/cold controls unchanged.
This is a coarse screen; 2-MHz spacing and limited shots can miss narrow or
weak signals. Repetition and finer sampling follow candidates from the full
band. Do not interpret a broad null as excluding TLSs whose memory decays
during the return and first readout.

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy &&
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSAfterglowTimeMap --run --freq-start 3.800 --freq-stop 4.050 --step-mhz 2 --shots 400 --passes 1 &&
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSAfterglowTimeMap --run --freq-start 4.050 --freq-stop 4.300 --step-mhz 2 --shots 400 --passes 1
```

The command chain starts the second half only after successful completion of
the first. Reference rejection or acquisition failure stops the chain and
retains the existing raw data. No new acquisition code is needed.

## First full-band result: 212318Z_601077f7 / 215155Z_e5a7c5d6

Both halves completed on 2026-10-04, with all four reference boundaries
valid. The combined sweep lasted **3,428.65 seconds (57m09s)** from first
initialization to final completion. It contains **252 science cells, 251
unique frequencies, 604,800 paired science records and 14,400 reference
records**. The duplicated point is 4.050 GHz. All 252 raw summaries, four
reference reports, source hashes and independent paired growth variances
reproduce. Each half uses its own frozen initial classifier; these remain
classified contrasts rather than absolutely calibrated populations.

At **4.000 GHz**, only 79 hot short-probe shots were accepted, below the
fixed minimum of 80. Both growth contrasts there stay masked. The other
**502 of 504 planned growth comparisons** pass quality checks, counting the
overlap measurements separately. No science acquisition was skipped.

**No confirmed afterglow in this first coarse broad pass.** Standardized
growth among valid comparisons has mean -0.0015 and standard deviation
1.0134; there are 15 points above +2 SE and 18 below -2 SE. This scatter is
compatible with shot noise. Shared short-probe baselines and references mean
these are descriptive diagnostics, not independent exact hypothesis tests.
The largest positive standardized growth is 2.84 SE; an approximate normal
one-sided Bonferroni screen across all 504 planned comparisons would require
3.72 SE. This is not evidence that all long-lived TLSs are absent: coarse
frequency spacing, finite shots, imperfect heralding and the return/readout
gap still limit visibility.

Exploratory observations (one-SE errors, percentage points):

| Frequency | Probe | Growth above 0.1 us | Direct hot-minus-cold |
|---|---|---|---|
| 3.862 GHz | 40 us | +14.27 +/- 5.03 | +11.04 +/- 3.71 |
| 3.984 GHz | 40 us | +11.65 +/- 4.19 | +9.89 +/- 2.93 |
| 4.046 GHz | 10 us | +15.06 +/- 6.38 | +7.50 +/- 4.69 |

The new 3.862/3.984-GHz observations are selected after looking at this broad
screen and require independent repetition. The earlier 4.046-GHz candidate
is positive again, making four positive growth observations since the
three-pass session. However its new direct excess is only 1.60 SE, and its
IQ growth is 0.122 +/- 0.102 of reference separation. Its large growth partly
reflects a negative short-probe offset; do not equate it with a 15-point
absolute upward-excitation signal or declare localized TLS memory.

Descriptive stricter-herald checks, admitting 2.5% instead of 5% of the
initial excited-reference tail, give growth +10.74 +/- 5.79 at 3.862 GHz,
+15.22 +/- 5.14 at 3.984 GHz, and +22.54 +/- 7.88 at 4.046 GHz. These are
sensitivity checks sharing the same data, not independent confirmations;
the stricter 4.046-GHz selection falls below the default accepted-shot gate.

Plots and the complete reproducible raw snapshot/audit are under
`~/.codex/visualizations/2026/10/04/q3_afterglow_full_band_212318Z/`.
`full_band_growth.png` combines the two blocks, preserves the invalid gap,
and uses a descriptive mean with a disagreement-error floor at the overlap.
The dashed boundary marks the separately calibrated blocks. The full band
was measured sequentially; it is not a simultaneous spectrum.

Next take **one independent repeat of the whole band**, upper block first
and lower block second, at unchanged spacing, shots and probe delays. Allow
roughly 57 minutes. This reverses block order only; each individual one-pass
session still scans frequencies and arms in its default order. The repeat
will provide a second broad observation with actual cell timestamps, rather
than treating a single sweep as a wall-clock series.

Before collecting it, specify three candidate checks: 3.862 GHz/40 us,
3.984 GHz/40 us and 4.046 GHz/10 us. A useful repeat requires positive direct
excess and growth, each exceeding 2.5 paired SE in the new data, with positive
IQ support. These are triage criteria for three selected endpoints, not a
discovery claim; neighboring frequencies and off-target loading controls
remain necessary for localization and attribution. Other frequencies remain
exploratory, and a shifted feature is reported as such rather than used to
silently redefine confirmation. Analyze the independent repeat separately
before any pooling that includes the original selection data.

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy &&
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSAfterglowTimeMap --run --freq-start 4.050 --freq-stop 4.300 --step-mhz 2 --shots 400 --passes 1 &&
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSAfterglowTimeMap --run --freq-start 3.800 --freq-stop 4.050 --step-mhz 2 --shots 400 --passes 1
```
