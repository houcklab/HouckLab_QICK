# Protocol Selection Benchmark Design

## Purpose

Build one temporary, measurement-first benchmark on each controller that can answer a narrow production question before another multi-day scan begins:

> Which T1 protocol and shot budget gives q3 and q5 the cleanest, most trustworthy frequency-resolved Gamma1 map, and should the accepted controller-neutral predistortion be enabled?

The benchmark compares genuine 3-condition, 5-condition, and 7-condition acquisitions over the complete production band. It runs one map per condition, saves every map immediately, and does not use a QUA/QICK handshake. The two controllers can therefore run independently and in parallel.

This is a temporary characterization runner. It must not silently change the production protocol, the predistortion model, or the existing seven-day runners.

## Repositories and deployment workflow

The implementation spans two repositories:

- QICK development worktree: `/Users/rummanrahman/.codex/worktrees/qick-ramsey-neutral`
  - development branch: `codex/ramsey-neutral-predistortion`
  - measurement-PC production branch: `tls-spectroscopy`
  - runner package: `WorkingProjects/TLS_Spectroscopy/Client_modules/Runners`
- QUA development worktree: `/Users/rummanrahman/.codex/worktrees/qua-ramsey-neutral`
  - development branch: `codex/ramsey-neutral-predistortion`
  - measurement-PC production branch: `marty-branch`
  - runner package: `LabCode/Control/Flux_Tunable`

Development changes are committed and pushed to the corresponding production branch. The user pulls them on each Windows measurement PC, then launches the module with that repository's virtual-environment Python. Measurement artifacts are written to the already-mounted NAS under the normal device/date hierarchy:

- q3/QICK: `Z:/FluxTeam/Data/FTT02_AlOxJJ_2026_08_28/RFSOC/q3/q3_YYYY_MM_DD`
- q5/QUA: `Z:/FluxTeam/Data/FTT02_SiOxJJ_2026_08_28/OPX/q5/q5_YYYY_MM_DD`

The macOS development machine sees the same data under `/Volumes/ourphoton/FluxTeam/Data/...`, which is how completed results will be inspected and compared.

## Existing acquisition paths to preserve

The benchmark must reuse the controller-native acquisition implementations rather than emulate every protocol with one generic data set.

### QICK

- Real 3-condition path:
  - `WorkingProjects/TLS_Spectroscopy/Client_modules/Runners/ThreePointApplesToApples.py`
  - `WorkingProjects/TLS_Spectroscopy/Client_modules/Experiments/mT1VsFlux.py::T13PointVsFlux`
  - `WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/integration.py::acquire_t1_3pt_iq`
- Multi-condition path:
  - `WorkingProjects/TLS_Spectroscopy/Client_modules/Runners/FivePointApplesToApples.py`
  - `WorkingProjects/TLS_Spectroscopy/Client_modules/Runners/SevenPointApplesToApples.py`
  - `WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/integration.py::acquire_t1_5pt_iq`
  - the existing n-point resident-program mechanism used by diagnostic code for 7 conditions

### QUA

- Real 3-condition path:
  - `LabCode/Control/Flux_Tunable/ThreePointApplesToApples.py`
  - `LabCode/Experiments/Flux_Sweeps/m_swap_spec_vs_flux.py::T13PointVsFlux`
- Multi-condition path:
  - `LabCode/Control/Flux_Tunable/FivePointApplesToApples.py`
  - `LabCode/Control/Flux_Tunable/SevenPointApplesToApples.py`
  - `LabCode/Experiments/Flux_Sweeps/m_swap_spec_vs_flux.py::T15PointVsFlux`

The 3-point results must come from actual 3-condition sequences. They must not be reconstructed from a 5- or 7-condition scan. Likewise, 5- and 7-condition maps must use their intended condition ordering and timing.

## Fixed measurement conditions

Every pass uses the following conditions unless a protocol row below explicitly overrides one:

- frequency band: 4.3000 to 3.9000 GHz, descending
- frequency step: 0.5 MHz
- frequency points: 801
- reset mode: active
- readout: at park
- frequency-to-flux mapping: the currently accepted production mapping for that qubit
- one controller-native readout/reset calibration per benchmark session
- no QUA/QICK handshake, shared start file, or paired-run barrier
- output: standard q3/q5 dated NAS directory

The readout/reset calibration is performed once before the first benchmark pass. Recalibrating between protocols would introduce a new experimental variable. If initial calibration fails its normal contrast or fidelity gate, the benchmark aborts before collecting any maps. The repeated terminal sentinel described below measures whether the shared calibration and device state drifted materially during the suite.

## Predistortion contract

`ON` means the currently accepted controller-neutral Ramsey-cryoscope model rendered through the exact production waveform lifecycle:

- q3 neutral model: `q3_22_45_58_Flux_Ramsey_Cryoscope_joint_neutral_candidate.json`
- q5 neutral model: `q5_21_12_16_Flux_Ramsey_Cryoscope_joint_neutral_candidate.json`
- corrected outbound transition from park to target
- corrected held target waveform
- corrected return transition from target to park
- stateful recovery command and the same readout-at-park timing used by production
- model path, SHA-256, schema, coordinate convention, time constants, and coefficients recorded in every artifact

`OFF` means a unity-equivalent waveform rendered through the same production lifecycle and timing. In particular, OFF retains the same 40 us recovery-window occupancy and readout placement where the controller permits it. This prevents the A/B comparison from accidentally comparing different sequence durations or readout timing. Only the correction coefficients differ.

The benchmark does not fit or modify either neutral model. Predistortion identification is outside this experiment's scope.

## Benchmark matrix

Two total Bernoulli-measurement budgets are compared. The lower budget is approximately 900 condition shots per frequency and the higher budget is approximately 1500. Integer shot counts are chosen so the 3-, 5-, and 7-condition protocols consume nearly equal totals.

| Protocol | Decay delays | Lower shots/condition | Lower total/frequency | Higher shots/condition | Higher total/frequency |
|---|---|---:|---:|---:|---:|
| 3pt Ts=50 us | `[50]` plus P0/P1 references | 300 | 900 | 500 | 1500 |
| 3pt Ts=100 us | `[100]` plus P0/P1 references | 300 | 900 | 500 | 1500 |
| 5pt | `[40, 80, 200]` us plus P0/P1 | 180 | 900 | 300 | 1500 |
| 7pt | `[40, 80, 120, 160, 200]` us plus P0/P1 | 128 | 896 | 214 | 1498 |

Each of the eight protocol/budget combinations is measured once with predistortion ON and once OFF, producing 16 primary maps per qubit. A seventeenth map repeats the opening condition as a drift sentinel.

### Canonical pass order

The order counterbalances ON/OFF within each shot budget so that correction state is not systematically confounded with elapsed time:

| Pass | Protocol | Shots/condition | Predistortion | Role |
|---:|---|---:|---|---|
| 0 | 3pt Ts=100 us | 300 | OFF | opening primary map and drift anchor |
| 1 | 3pt Ts=100 us | 300 | ON | primary |
| 2 | 3pt Ts=100 us | 500 | ON | primary |
| 3 | 3pt Ts=100 us | 500 | OFF | primary |
| 4 | 3pt Ts=50 us | 300 | OFF | primary |
| 5 | 3pt Ts=50 us | 300 | ON | primary |
| 6 | 3pt Ts=50 us | 500 | ON | primary |
| 7 | 3pt Ts=50 us | 500 | OFF | primary |
| 8 | 5pt | 180 | OFF | primary |
| 9 | 5pt | 180 | ON | primary |
| 10 | 5pt | 300 | ON | primary |
| 11 | 5pt | 300 | OFF | primary |
| 12 | 7pt | 128 | OFF | primary |
| 13 | 7pt | 128 | ON | primary |
| 14 | 7pt | 214 | ON | primary |
| 15 | 7pt | 214 | OFF | primary |
| 16 | 3pt Ts=100 us | 300 | OFF | terminal drift sentinel |

Pass order is part of a canonical plan and must be identical in both repositories. The controllers do not synchronize their starts; they simply execute the same ordered plan independently.

## Architecture

Each repository gains two focused modules and one test module.

1. `protocol_selection_benchmark.py` is hardware-free. It defines the canonical pass plan, validates budgets and ordering, produces a canonical JSON representation and SHA-256 plan fingerprint, defines artifact schemas, and contains comparison metrics that can be unit tested with synthetic arrays.
2. `ProtocolSelectionBenchmark.py` is the temporary hardware runner. It performs the single calibration, dispatches each pass to the real 3-point or n-point acquisition path, renders ON or OFF waveforms through the same lifecycle, reports progress, checkpoints outputs, and restores park in all exit paths.
3. `tests/test_protocol_selection_benchmark.py` verifies the plan, dispatch, waveform mode, checkpoint behavior, analysis, and cleanup contract without hardware.

The QUA and QICK pure-plan modules must serialize the same canonical plan and therefore produce the same plan fingerprint. Controller-specific metadata is stored outside the canonical plan so it cannot make fingerprints diverge.

No existing long-scan runner changes behavior as part of this benchmark. Small shared helper fixes are allowed only when required to make the temporary runner call an existing production path safely.

## Execution and data flow

At startup, the runner:

1. resolves the dated output directory and current git commit;
2. creates or resumes a benchmark manifest;
3. resolves and validates the neutral predistortion model;
4. performs one readout/reset calibration and stores its artifact identifier;
5. iterates through the 17 canonical passes;
6. restores the flux line to park after every pass, including exceptions;
7. writes the final aggregate table and comparison figure after all passes finish.

For every pass, the runner:

1. prints `[pass i/17]`, protocol, delays, shots/condition, total shots/frequency, and ON/OFF state;
2. builds the real controller-native sequence for that protocol;
3. acquires the full 801-frequency map with its normal shot/frequency progress reporting;
4. fits Gamma1 using the protocol-appropriate estimator;
5. saves raw reference and delay populations, fit products, metadata, and pass status;
6. atomically updates the session manifest before advancing.

The expected total duration is roughly 35 to 60 minutes per controller, depending on compilation and hardware throughput. The runners operate independently, so the wall-clock cost is the slower controller rather than the sum of both.

## Progress reporting

Every pass must show:

- current pass and total passes;
- completed and total frequencies or shots;
- elapsed wall-clock time;
- an ETA based on observed completed work in the current pass;
- total benchmark elapsed time and an ETA based on completed passes once at least one pass has completed.

Time values are calculated from monotonic seconds and formatted only after unit conversion. The previously observed enormous-hour ETA failure must not recur.

## Artifacts and checkpointing

The benchmark uses a session stem such as:

`q5_HH_MM_SS_TLS_Protocol_Selection_Benchmark`

Every completed pass is saved immediately in the normal dated device directory. Required outputs are:

- `<stem>_manifest.json`: canonical plan, plan fingerprint, code/model provenance, calibration identifier, pass status, timestamps, durations, and artifact checksums;
- `<stem>_pass_00_3pt_Ts100_300_OFF_raw.csv`: one row per frequency with raw P0, P1, each signal population, scan-direction components, realized coordinate, and fit products;
- `<stem>_pass_00_3pt_Ts100_300_OFF_metadata.json`: complete pass configuration and provenance;
- equivalent CSV and JSON pairs for all 17 passes;
- `<stem>_summary.csv`: one row per pass and frequency with normalized metrics used for cross-protocol comparison;
- `<stem>_comparison.png`: a fixed-layout visual comparing all 16 primary maps and the opening/closing sentinel difference.

The per-frequency CSV schema contains at minimum:

- target and realized frequency;
- requested and realized flux coordinate;
- P0, P1, and every signal population;
- up-scan and down-scan values when the acquisition supplies them;
- Gamma1, T1, fit uncertainty, fit validity, residual deviance, and non-exponential diagnostic;
- reference contrast and normalization denominator;
- pass index, protocol, delays, shots/condition, predistortion state, and timestamps.

The manifest is written atomically by replacing a temporary file only after the new JSON is complete. A pass is marked `complete` only after both pass artifacts exist and their checksums are recorded.

## Resume and failure behavior

Rerunning a partially completed benchmark resumes only when all of the following match:

- canonical plan fingerprint;
- device identifier;
- controller type;
- neutral-model SHA-256;
- frequency grid;
- calibration identifier, unless the prior session ended before the first pass.

Completed passes with valid checksums are skipped. A partial or failed pass is reacquired from the beginning. Any mismatch causes a clear refusal to resume instead of silently combining incompatible data.

All acquisition blocks use `try/finally` to restore the flux line to park and close or halt the active job. A failure record includes the pass index, exception type, message, traceback, and timestamp. The manifest remains resumable, but the process exits nonzero so a hardware fault cannot be mistaken for a completed suite.

## Comparison and decision criteria

The benchmark reports individual metrics and a ranked table; it does not hide the result behind one opaque composite score.

Primary criteria, in order, are:

1. **Validity:** at least 99% valid Gamma1 values and no systematic frequency interval of NaNs.
2. **Reference quality:** stable P0/P1 contrast across the band and between the opening and terminal sentinels.
3. **Directional agreement:** small up/down disagreement, especially absence of vertical full-band streaks caused by one corrupted sweep direction.
4. **Statistical precision:** median and 90th-percentile Gamma1 uncertainty, compared at the approximately equal 900- and 1500-shot budgets.
5. **Temporal stability:** opening-versus-terminal sentinel change small compared with normal point uncertainty.
6. **Spectral fidelity:** consistent peak centroid and linewidth across protocols; a protocol that narrows or moves every feature systematically is treated as suspect rather than automatically better.
7. **Model adequacy:** residual deviance and the non-exponential diagnostic, particularly in frequency bands that produced questionable fits during earlier scans.
8. **Runtime:** measured duration per map and projected seven-day cadence after scientific quality requirements are satisfied.

ON/OFF comparisons are paired within the same protocol and shot budget. Protocol comparisons use the nearest equal-total-shot budget. The recommended production setting is the lowest-cost protocol that satisfies validity and reference gates and does not introduce systematic frequency shifts, linewidth artifacts, directional streaking, or excess non-exponential residuals.

The analysis must not infer that narrower features are intrinsically more accurate. A linewidth change is evidence to investigate alongside centroid stability, reference contrast, and ON/OFF differences.

## Final visualization

The final figure uses the same visual language as the existing Gamma1-versus-frequency linecut and colormap comparisons. It includes:

- a 4 by 4 grid of the 16 primary Gamma1 maps, grouped by protocol and shot budget with ON/OFF adjacent;
- shared frequency axis and protocol-appropriate but explicitly labeled color normalization;
- a table or compact panel of validity, uncertainty, directional disagreement, runtime, and reference contrast;
- opening and terminal sentinel linecuts and their difference;
- representative Gamma1-versus-frequency linecuts for every protocol at one matched time/pass, with uncertainty bands;
- explicit model hash and plan fingerprint in the caption or metadata panel.

Raw values remain authoritative. The figure must never clip or mask invalid points without marking them.

## Test strategy

Hardware-free tests in both repositories cover:

- exact 17-pass order and unique pass identifiers;
- exact delay arrays, shot counts, condition counts, and total-shot budgets;
- identical canonical JSON and a fixed expected plan fingerprint in QUA and QICK fixtures;
- absence of handshake or synchronization configuration;
- calibration called exactly once;
- 3-point passes dispatched to the true 3-condition path;
- 5- and 7-point passes dispatched to the n-point path with correct dimensions;
- ON receiving the accepted neutral model and OFF receiving the unity-equivalent timing schedule;
- frequency grid fixed to 801 points from 4.3000 to 3.9000 GHz;
- atomic checkpointing and exact resume rules;
- park restoration on success, acquisition failure, and analysis failure;
- pass artifacts containing the required schema and matching array lengths;
- synthetic exponential data producing the expected Gamma1 and uncertainty;
- synthetic corrupted references producing an invalid result rather than a plausible number;
- synthetic direction offsets, linewidth shifts, and non-exponential curves being flagged by their respective metrics;
- ETA formatting from monotonic seconds.

The measurement PCs provide the final verification: each controller first runs a tiny smoke configuration through the same runner, then runs the full canonical suite. A successful offline unit suite is necessary but not sufficient.

## Non-goals

This benchmark does not:

- synchronize QUA and QICK;
- collect 30-minute repeated sessions;
- identify or refit predistortion models;
- alter the production seven-day scan configuration automatically;
- replace existing acquisition classes;
- compare different frequency bands or flux fits;
- recalibrate readout between passes;
- make a production choice without inspecting the saved scientific results.

After both suites finish, the results will be inspected from the NAS and the production protocol will be selected explicitly. Only that later decision authorizes updates to the long-scan runners.
