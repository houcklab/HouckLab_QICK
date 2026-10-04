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
