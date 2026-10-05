# q3 fast local loss-map pilot — October 5, 2026

## Question and decision

Can a smaller frequency window and fewer shots resolve a q3 loss feature at
a substantially shorter frame cadence than the production wide scan? This
is a timing/contrast pilot before committing to long switching/diffusion
measurements. It does not revive the unresolved e–f or afterglow routes.

The production scans use active reset. A passive-relax timing estimate is
not a bound on their speed. The new runner also uses production active
reset, without falling back to passive reset if calibration fails.

The Oliver-group [adaptive spectroscopy paper](https://arxiv.org/html/2608.02086v1)
demonstrates fast maps with an FPGA estimator and adaptive delays. This
pilot keeps the existing fixed five-condition sequence and benchmarks a
small window first. It does not implement that estimator or promise the
paper's full-band cadence.

## Acquisition

1. Production active-reset/readout calibration with the explicit q3 settings.
2. One fresh 3.8–4.3 GHz scout, 2 MHz steps, 251 frequencies, 250 shots per
   condition. Select one bilateral loss trough reproduced in both scan
   directions. No second line or e–f quiet window is required.
3. One local 20 MHz window, 1 MHz steps, 21 frequencies; 250-shot local pre.
4. Forty local frames, 40 shots per condition per frequency per frame.
5. A 250-shot local post at the identical frequencies; then stop.

Each map contains P0, P1, and survival at additional 2, 10 and 25 µs delays.
The P0/P1 reference hold is 0.1 µs. Each logical scan shot alternates the
frequency direction, retaining the production fixed condition order.
Preparation and readout remain at park. The native correction and full
40 µs return are retained. There are no target microwave pulses.

Expected total duration is approximately **5–10 minutes**, including the
scout/calibration, compilation, host transport and NAS writes. Actual local
cadence is an output, not an established performance claim. Progress/ETA
counts maps; the scout and local reference maps take longer than a frame.

The scout selector requires reference contrast ≥0.2 at the center and both
flanks. It propagates normalized-survival uncertainty using paired-shot
influence functions, including covariance between conditions/frequencies.
Both flanks must have a depth ≥0.12 and shot-noise score ≥4.5 over all shots;
each direction independently requires depth ≥0.06 and score ≥2. The score
guard is conservative for the wide candidate search. These criteria select
a pilot window; they do not establish TLS identity or a formal discovery
significance. No qualified trough means a finite unresolved scout, not an
automatic rerun or evidence that the band contains no TLSs.

## Files and interpretation

Output: `q3/q3_fast_loss_map_<UTC>_<ID>/` under the normal RFSOC root.

- `manifest.json`: plan, source/commit/correction hashes, selection and status.
- `board_configuration.json`, `config.json`, production calibration files,
  and per-map configs/preflight/stream plans.
- `scout`, `local_pre`, `frame_0000`…`frame_0039`, `local_post` NPZ/JSON pairs.
  Arrays contain **integer integrated I/Q and every binary classified shot**,
  in condition × canonical frequency × shot order. Scan-direction metadata
  records the actual alternating order. Target frequencies, realized model
  frequencies and integer DC gains are saved.
- Frame start/end wall and monotonic times, compilation duration, and
  cumulative host receipt times for decoded banks. These are **host timing**,
  not individual hardware shot timestamps. Acquisition time includes
  hardware configuration/transport. Start-to-start cadence also includes
  analysis, compilation and NAS gaps.
- `summary.json`: actual acquisition durations, frame periods, pooled pre/post
  P0/P1 drift checks; no automatic switching claim.
- `fast_loss_map.png/.svg`: 10 µs normalized survival using pooled local
  pre/post references. Rectangles span actual frame acquisition intervals;
  gaps remain blank. Frequencies with reference contrast below 0.2 are masked.
  Values are not clipped in the saved data; the display color scale is 0–1.

The local window stays fixed for these forty frames. A moving line can leave
it; the data then constrain this window, not the entire band. Local frame
P0/P1 probabilities and raw shots are retained for later drift/noise checks.
The pooled pre/post reference check cannot prove per-frequency/sub-frame
stability. If it fails, the run is `complete_reference_drift` and interpretation
is unresolved. Low-shot frames are not fitted to full T1 curves here.

Ctrl+C or errors abort the controller/generators and preserve already decoded
records for the current map through acquisition, classification and file
publication. Complete NPZ files are published by a same-directory atomic
rename. Partial records remain in acquisition order and are not presented
as a complete canonical map. No automatic restart occurs.

## Scope and verification

New runner/test/doc files only. Production TLS spectroscopy, shared active
reset, `initialize.py`, YOKO bias and measurement-PC local overrides are not
edited. A scoped q3 configuration prevents stale q4 settings from selecting
the wrong qubit. The correction environment pins native gain 1.0 and the
checksum-verified production JSON; prior settings are restored on exit.

The observer subclass only records parent DMEM decoder output. Offline QICK
0.2.133 compilation against the saved board configuration confirms **identical
instruction binaries and stream plans** to `OPXResetT15PointProgram` for the
wide scout, local frame/reference, and both band-edge windows. Preflight
passes all five cases, maximum 5,777/8,192 instructions. This verifies pulse
equivalence/resource feasibility, not hardware cadence or readout quality.

Thirteen focused tests with offline QICK cover alternating-shot reconstruction,
known loss/flat/directional-artifact scouts, reference drift, finite collection,
acquisition gaps, correction/q3 scoping/restoration, raw integer IQ, atomic
publication, and interruption through acquisition and processing. A separate
100-seed flat 250-shot low-contrast null audit selected zero pilot windows.
Full maintained suite: **1,435 tests passed in 41.76 s**. Independent code
review found no remaining actionable P1/P2 issues after the selector,
environment-scoping and interruption-preservation fixes.

## Measurement-PC command

Stop any other hardware acquisition first, then:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSFastLossMap --run
```

The script enforces q3 even if the PC's local settings still describe q4.
Report completion; inspect timing, local contrast and reference stability
before choosing a longer run or implementing adaptive acquisition.

## First hardware result and bounded extension

`q3_fast_loss_map_20261005T052318Z_c0263e35`, commit `fc38b5a8`, completed
all 43 maps in approximately 1m42s. Source hash matches; explicit q3 park,
readout and π parameters, active reset, 10 µs readout thermalization and
40 µs corrected return are confirmed in the saved config. All 534,250
integer-IQ/classified records are present, with matching transfer counts,
array shapes and the identical local frequency grid in every frame.

Scout: 46.60 s acquisition, selected 4.108 GHz. Local window:
4.098–4.118 GHz, 21 points at 1 MHz. Local references: 3.93 s each.
Forty low-shot frames: acquisition median **0.684 s** (0.631–0.896 s);
start-to-start median **0.894 s** (0.813–1.378 s), including compile/save
gaps. The local recording spans **37.79 s**. This is a local-window result,
not a sub-second 500 MHz map or an adaptive FPGA result.

The loss remains resolved in independent pre/post scans and the pooled fast
frames. At 25 µs, pooled normalized survival reaches **0.304 at 4.109 GHz**,
versus approximately **0.65–0.71 at the window edges**. Pooled pre/post
references pass: P0 0.1335→0.1280, P1 0.6844→0.7082; reference contrast
0.5509→0.5802. The actual classifier contrast is approximately 0.5–0.6;
these are preparation-relative survival values, not absolute thermometry.

Individual frames are visibly noisy. A single Gaussian-notch center fitted
to five-frame groups depends materially on local versus pooled reference
normalization and on broad/secondary loss structure. Do not report its
few-MHz center excursions as a resolved switching result. The saved fit
numbers are descriptive audit data, not diffusion/linewidth estimates.
The pilot establishes useful cadence and persistent loss contrast; it does
not yet establish dynamics or a particular microscopic TLS model.

![First fast-map result](q3_fast_loss_map_20261005_result.png)

Raw NAS source remains under the run folder above. Local copied raw files,
analysis script and plots: `.codex/visualizations/2026/10/05/q3_fast_loss_map_052318Z`
under the user's home directory. Summary/audit statistics are also in
`docs/q3_fast_loss_map_20261005_audit.json`.

Next: keep the identical 21-point/40-shot sequence and acquire **1,000
frames**, expected approximately **15–22 min** with fresh calibration/scout
and local pre/post. `--frames` changes only the finite host frame count,
manifest, progress total and duration estimate; default remains 40 and the
accepted range is 1–2,000. No pulse instructions, shot count, feature
selector, return, reset defaults or automatic recentering change. This
longer record is justified by the successful speed/contrast pilot; inspect
raw references and both scan orders before interpreting apparent line
motion. Stop the controller with Ctrl+C if needed; partial preservation is
unchanged.

Extension verification: 15 focused tests with offline QICK and 1,437 full
suite tests pass (41.27 s); all five offline production/observer instruction
comparisons still match. Independent review found no actionable P1/P2 issues.

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSFastLossMap --run --frames 1000
```

## Longer attempt stopped at discovery; explicit-window follow-up

`q3_fast_loss_map_20261005T054544Z_e04e1bb0`, commit `b29ed706`, ended
`unresolved` after 46.86 s. It acquired the complete 251×250×5 scout
(313,750 records, 37.51 s acquisition) and **zero local references/frames**.
The source hash matches and the production active-reset calibration passed.
This is not a 1,000-frame measurement or a negative switching result.

Loss remains visible near 4.106–4.108 GHz (25 µs normalized survival about
0.354), but the scout reference contrast median is 0.480 versus 0.556 in
the successful pilot. No candidate passes the conservative discovery gate.
At 4.106 GHz, bilateral depth is 0.235 and score 3.243 over all shots;
the reverse score is 1.201, below the required 4.5/2 scores. The strongest
pooled candidate, 4.062 GHz, has score 4.590 but forward score 1.868.
Thus the rejection is reproduced from the raw shots; it is not a corrupt
file, missing acquisition, calibration exception or frequency-grid error.
These shot-noise scores do not identify the microscopic absorber or show
that a TLS disappeared.

![Scout comparison](q3_fast_loss_scout_20261005_result.png)

The automatic gate is suitable for discovering a new window across 500 MHz,
but reapplying it before every recording obstructs monitoring a previously
observed window when the signal weakens or changes. Add an **explicit model
frequency window** option, `--center-ghz 4.108`: record 4.098–4.118 GHz
directly with fresh active-reset calibration and 250-shot local pre/post,
plus the requested 1,000 unchanged 40-shot frames. There is no wide scout
in this mode. Data are recorded even if the region is flat; specifying a
window is not evidence of a fresh feature. Plan/manifest explicitly say
`explicit_window` and `fresh_feature_claim=False`. Default discovery behavior,
scores, pulse instructions, reset/calibration gates, return and shot count
remain unchanged. Progress total is frames+2 rather than frames+3.

This targets the recently observed region for dynamics measurement rather
than repeatedly attempting whole-band discovery. If loss moves outside the
window, the result only describes the requested window. No automatic
recenter, new TLS identity, or motion significance is inferred by the runner.

The audited scout and candidate scores are in
`docs/q3_fast_loss_scout_20261005_audit.json`; raw/analysis copies are under
the user's `.codex/visualizations/2026/10/05/q3_fast_loss_scout_054544Z`.
Focused regressions include flat explicit-window acquisition, CLI/plan
propagation, finite counts and band validation.

Explicit-window verification: 17 focused tests with offline QICK and
1,439 full suite tests pass (41.66 s). Six production/observer instruction
comparisons, including the exact 4.108 GHz requested window, match and
pass preflight; latest saved board configuration matches the successful
pilot. Independent review found no actionable P1/P2 issues.

Next measurement-PC command (approximately 15–22 min):

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSFastLossMap --run --frames 1000 --center-ghz 4.108
```
