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
