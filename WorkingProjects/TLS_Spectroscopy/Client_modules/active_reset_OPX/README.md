# OPX-Style Active Reset Prototype

This folder is an isolated QICK/tProc-v1 implementation of the reset state
machine used by the QUA coherence experiments. It is not imported by the
production T1, T1-vs-flux, TLS, or Rabi programs.

## Park stability comes first

The QUA configuration applies `flux_dc_offset` as a persistent controller
analog-output offset. A QUA flux experiment temporarily changes that offset,
then restores `park_voltage`; active reset and the inter-shot wait therefore
happen at a nonzero, time-independent park.

The QICK code cannot assume equivalent behavior merely because
`stdysel="last"` retains the final digital sample. Its present safe waveform
ramps channel 3 from zero to `ff_park_gain` inside every shot, actively plays
the hold through the measurement/reset sequence, then ramps back to zero.
Earlier q3 testing at +32000 DAC found nearly the same qubit-frequency drift
for a latched sample and an actively played constant waveform, and a separate
continuous-park attempt heated the mixing chamber. The analog path must
therefore pass a bounded stability test before active-reset results at a
nonzero park are meaningful.

Run this first on the measurement PC:

```powershell
C:\Users\my\Documents\GitHub\HouckLab_QICK\venv\Scripts\python.exe `
  C:\Users\my\Documents\GitHub\HouckLab_QICK\WorkingProjects\TLS_Spectroscopy\Client_modules\active_reset_OPX\park_stability_q3.py
```

The runner inherits the live `ff_park_gain` and qubit frequency from
`Calib/initialize.py`. It applies no tail-correction JSON, performs qubit
spectroscopy while a constant channel-3 waveform is actively playing, covers
0.5--160 us at park, and checks the approximately 120 us worst-case reset
window. It always ramps back to zero each shot. A result is `pass` only when
the extracted frequency stays within the configured 0.5 MHz limit; a trace at
the edge of the spectroscopy window is reported as inconclusive. Send back
the entire printed output folder.

Do not run `benchmark_q3.py` again until this prerequisite either passes or
the park path/correction has been repaired and revalidated.

## What is different from the current QICK reset

The payload experiment's final measurement is decision zero. The tProc then
executes this logic without returning to Python:

1. confidently ground: exit immediately;
2. confidently excited: play X180, then remeasure;
3. ambiguous: do not play X180, but remeasure;
4. repeat for at most eight corrective attempts;
5. evaluate the eighth remeasurement before declaring a timeout.

The current production reset always emits a fixed number of reset readouts. The
new program contains bounded, compile-time-unrolled branch blocks, but a ground
branch jumps over the remaining blocks. The executed instruction path, reset
duration, pi-pulse count, and ADC-trigger count therefore vary shot by shot.

`AveragerProgram.acquire` cannot parse that variable trigger count. The prototype
instead writes one fixed eight-word record per shot to tProc data memory and
polls a completion counter. The record contains the preparation, initial
decision, corrective-attempt count, pi count, terminal status, verification I/Q,
and last reset decision.

## First run on the measurement PC

1. Pull the latest `tls-spectroscopy` branch.
2. Confirm that `requirements.txt` has installed `qick==0.2.133` and `numpy<2`.
3. Check the live q3 values in
   `WorkingProjects/TLS_Spectroscopy/Client_modules/Calib/initialize.py`. The
   runner deliberately uses that `BaseConfig` so the resonator, qubit pulse, and
   channel-3 park match the machine's current calibration.
4. Open `benchmark_q3.py` in this folder. Leave `PROFILE = "smoke"`,
   `RUN_CALIBRATION = True`, and `RUN_BENCHMARK = True` for the first run.
5. Run:

   ```powershell
   C:\Users\my\Documents\GitHub\HouckLab_QICK\venv\Scripts\python.exe `
     C:\Users\my\Documents\GitHub\HouckLab_QICK\WorkingProjects\TLS_Spectroscopy\Client_modules\active_reset_OPX\benchmark_q3.py
   ```

The smoke profile takes 1,000 prepared-ground and 1,000 prepared-excited shots
in each of two calibration contexts. It then takes 200 shots for every
combination of `{none, opx}` and `{prepared g, prepared e}`. It does not run the
current production-reset comparator yet.

Send back the complete output folder printed at the end of the run, not only a
screenshot. The important files are:

- `calibration.json`: payload and loop fixed-point classifiers;
- `calibration_raw.npz`: all timing-matched reference shots;
- `calibration.png`: raw and projected reference distributions;
- `shots.csv`: one row per completed benchmark shot;
- `summary.json`: timeout-inclusive residuals and attempt statistics;
- `benchmark.png`: residual, timeout, and mean-attempt comparison;
- `opx_reset.asm`: exact tProc assembly sent to the board;
- `opx_reset.asm.sha256`: binary-program fingerprint;
- `run_metadata.json`: source commit and effective test settings.

## What counts as a useful smoke result

The smoke run is a wiring and semantics test, not proof of QUA equivalence. It
must have:

- two separated calibration clouds in both timing contexts;
- holdout false-ground and false-pi rates consistent with the configured limits;
- zero malformed records and no host timeout;
- `opx` prepared-excited residual below the `none` prepared-excited residual;
- near-zero mean corrective attempts for prepared-ground shots;
- no shot with more than eight corrective attempts.

If any condition fails, do not switch to `PROFILE = "full"`. The runner raises
on missing/stale calibration, DMem overflow, unsupported QICK version, invalid
feedback mapping, or timeout; it never substitutes passive reset.

## Full comparison

After the smoke artifacts have been reviewed, change only:

```python
PROFILE = "full"
```

The full profile runs four interleaved blocks with 1,000 shots per preparation
and method. Its methods are:

- `none`: payload measurement followed by independent verification, no reset;
- `current`: the existing fixed-iteration rotated QICK reset and verification;
- `opx`: the new payload-first, early-exit reset and verification.

The order of all six method/preparation conditions is randomized independently
within each block. Completed data are appended to CSV after each tProc chunk, so
a later hardware fault does not erase earlier shots.

True equivalence still requires same-day QUA data with matching preparation and
verification definitions. The design promotion gate is in
`docs/superpowers/specs/2026-09-04-opx-active-reset-design.md`.

## Feedback-delay diagnostic

If the full comparison meets the residual-excitation limit but exceeds the 1%
max-iteration limit, run `feedback_delay_sweep_q3.py`. It tests 8, 12, 16, 24,
and 32 us while holding the threshold policy, attempt cap, and every other reset
setting fixed. Each delay receives a fresh timing-matched calibration followed
by 1,000 shots per preparation. The result selects the shortest delay for which
both preparations have at most 1% max-iteration outcomes and at most 10%
verification excitation.

```powershell
C:\Users\my\Documents\GitHub\HouckLab_QICK\venv\Scripts\python.exe `
  C:\Users\my\Documents\GitHub\HouckLab_QICK\WorkingProjects\TLS_Spectroscopy\Client_modules\active_reset_OPX\feedback_delay_sweep_q3.py
```

If that result is not monotonic with feedback delay, run
`attempt_limit_sweep_q3.py`. The QUA coherence code uses an unbounded loop,
whereas the prototype defaults to an eight-attempt hardware safety ceiling.
This diagnostic holds the established 8 us feedback timing fixed and compares
ceilings of 8, 12, 16, and 24 attempts in four interleaved 250-shot blocks per
preparation. It selects the smallest ceiling meeting the same 1% timeout and
10% residual limits.

```powershell
C:\Users\my\Documents\GitHub\HouckLab_QICK\venv\Scripts\python.exe `
  C:\Users\my\Documents\GitHub\HouckLab_QICK\WorkingProjects\TLS_Spectroscopy\Client_modules\active_reset_OPX\attempt_limit_sweep_q3.py
```

## Reusing a calibration

For a deliberate same-session rerun, set:

```python
RUN_CALIBRATION = False
CALIBRATION_JSON = r"Z:\...\calibration.json"
```

The path must be explicit. The runner does not search for the newest JSON because
silently selecting an old standalone SSCal threshold is one of the failure modes
this package is designed to eliminate.

## Flux park behavior

If `ff_park_gain` is nonzero, the program ramps channel 3 to park, latches the
last generator value, and holds it through preparation, payload measurement,
reset, and verification. It ramps down after the per-shot record is committed.
Early reset exit therefore does not turn the park off early.

This only controls the RFSoC waveform. It does not compensate decay in an
AC-coupled physical output path and does not replace a DC-coupled flux source.

## Package map

- `classifier.py`: timing-matched rotated classifier and two confidence zones;
- `control_flow.py`: reference state-machine model and tProc branch emitter;
- `records.py`: versioned DMem record format;
- `acquisition.py`: direct tProc execution, DMem reads, and fail-closed cleanup;
- `programs.py`: fixed-shape calibration and variable-runtime benchmark programs;
- `calibration.py`: calibration acquisition and JSON/NPZ serialization;
- `analysis.py`: population projection, confidence intervals, CSV, and summaries;
- `park_stability.py`: hardware-independent park trace checks and safety limits;
- `park_stability_q3.py`: standalone q3 park-prerequisite measurement;
- `benchmark_q3.py`: standalone user-editable q3 runner;
- `feedback_delay_sweep_q3.py`: timing-matched reset-ceiling diagnostic;
- `attempt_limit_sweep_q3.py`: interleaved safety-ceiling diagnostic;
- `tests/`: hardware-independent regression suite.
