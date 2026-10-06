# q3 single-delay fast loss maps

The five-condition loop resolved localized loss changes but averaged P0, P1,
2 us, 10 us and 25 us probes at every frequency. The user approved moving to
one fixed-delay survival probe, with periodic references, to prioritize time
resolution. Acquisition remains a frequency sweep, not a fixed-frequency trace;
“single point” means one decay delay per frequency. No Bayesian adaptation.

## Protocol and scope

New isolated runner: `TLSFastSinglePointMap`. Reuses the existing
`OPXResetT1NPointProgram` and its existing `opx_t1_include_references=False`
branch. No shared production/reset program, initialize, or QUA changes.
Explicit q3 configuration is restored on leaving the runner's context.

- 3.945–3.995 GHz, 0.5 MHz steps: 101 frequencies.
- 40 alternating upward/downward sweeps per science map.
- Science condition: active reset at park, prepare excited, corrected flux
  visit for the same 25 us effective probe delay, corrected 5 us return,
  final readout. No P0/P1, 2 us or 10 us conditions in science blocks.
- Fresh production active-reset calibration for every finite 100-map batch;
  readout gain 940 for calibration and all acquired data. Existing quality
  criteria and feedback timing retained. No passive fallback.
- 250-shot reference blocks before and after each batch; 40-shot periodic
  reference blocks after science maps 20, 40, 60, 80. Each reference block has
  P0/P1/the same 25 µs probe. The period is measured in science maps, not exact
  seconds. Reference pauses and calibration time are saved separately.
- Each science map contains 4,040 final records versus 20,200 for the previous
  five-condition map. Actual host cadence must be measured; compilation,
  transport, reset attempts and reference overhead prevent assuming 5× speedup.

Raw integrated integer I/Q, binary states, canonical frequency arrays,
realized frequencies, integer DC gains and shot scan directions are saved.
States have shape `(1,101,40)` for science and `(3,101,40 or 250)` for references.
JSON records condition labels, block timestamps, cumulative transfer receipts,
program configurations and memory preflight results. Runner/helper/production
sources and hashes, correction JSON/hash, board configuration, calibration
and git commit are archived per batch.

## Analysis and stopping

Periodic P0/P1 probabilities are interpolated in actual wall-clock time
between bracketing references within one calibration batch. Derived survival
is `(Pprobe-P0)/(P1-P0)`. No clipping of saved values. Intervals failing the
existing pooled reference-drift guard, cells with contrast below 0.2, and frames
without a later reference are masked in derived arrays. Raw measurements
remain available. This normalization assumes sufficiently stable/interpolable
references between blocks; it cannot distinguish unobserved fast reference
jumps from TLS dynamics.

This is a calibrated survival proxy, not a fitted T1 or a measurement of the
asymptotic equilibrium population. The changed duty cycle may also change
measurement backaction; acquisition is not proof of undriven TLS switching.
Individual sweeps have order but no exact hardware timestamps.

`--loop` makes a new folder and fresh calibration for each batch, continues
through flagged reference drift, and stops on acquisition/calibration errors
or Ctrl+C. Completed raw blocks are checkpointed individually. Interruptions
retain received partial IQ via the existing safe-abort acquisition wrapper;
normalization does not extrapolate past the last reference. Terminal output
is SS calibration, a `1pt loss maps` progress bar with ETA, final folder/status
and any failure; no per-frame debug chatter.

Stop the older five-condition process with Ctrl+C before pulling/running:

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSFastSinglePointMap --run --loop --frames 100 --center-ghz 3.970 --width-mhz 50 --step-mhz 0.5 --delay-us 25 --shots 40 --reference-every 20 --readout-gain 940
```

## Verification

Tests witnessed failing before implementation. Focused validation:162 passed,
1 hardware-dependent skipped. Maintained suite:1,471 passed in 40.96 s.
The new CLI plan validates the 101-point grid, 4,040 science records/map,
100-map finite batches, 6 reference blocks and unlimited repeated batches.

Offline hardware compilation used QICK 0.2.133 / Python 3.10 / NumPy 1.26.4 and the
saved ZCU216 configuration, calibration and gains from successful gain 940
batch `q3_fast_loss_map_20261005T212700Z_518386ba`:

- science 40 shots: 1,403/8,192 instructions, 4,040 records;
- periodic references 40 shots: 3,437 instructions, 12,120 records;
- endpoint references 250 shots: 3,437 instructions, 75,750 records;
- flux waveform memory 55,040/65,536 samples; qubit 11,008/65,536 samples;
- resident banks 996 records, with correct 1/3 records per frequency unit and
  retained final partial banks. Full report in adjacent preflight JSON.

An initial local compilation using Python 3.13 / NumPy 2.3.1 hit an old QICK
uint16 promotion OverflowError; using the existing Python 3.10 / NumPy 1.26.4
compiler environment succeeds without a code workaround. This is offline
compilation, not execution on hardware or validation of the speedup.

Repository-root `python3 -m pytest -q` still cannot collect six pre-existing
legacy scripts (6 errors in 47.60 s):

- `Archive/q4diamond/Client_modules/Running_Experiments_MUX/Timing_test.py`: missing qick.
- `WorkingProjects/Inductive_Coupler/Client_modules/Running_Experiments_MUX/Timing_test.py`: missing qick.
- `WorkingProjects/Tantalum_fluxonium_escher/Client_modules/Calib_escher/Experiment_test.py`: missing remote nameserver (`NoneType.list`).
- `WorkingProjects/Tantalum_fluxonium_escher/Client_modules/Experiments/mFFDelayedTransSlice_test.py`: missing PyQt5.
- `WorkingProjects/Tantalum_fluxonium_escher/Client_modules/Experiments/mFFSpecSlice_test.py`: missing PyQt5.
- `WorkingProjects/Tantalum_fluxonium_marvin/Client_modules/Experiments/mTransmission_GUI_test.py`: duplicate imported module basename from the escher folder.

These collection limitations are distinct from the maintained 1,471-test suite
and do not represent execution of the new pulse sequence on hardware.

Final maintained-suite recheck: 1,471 passed in 39.55 s; quicklook rendering
and Python compilation also passed.

## Five-microsecond return update

At the user's request, the experimental fast-map runners now end the corrected
return at 5 us and wait until it finishes before readout. The return prefix is
also 5 us, which pads any zero tail removed by the compensation renderer,
keeping the reference and survival conditions on the same return timing.
The target dwell, active reset, readout gain, reference schedule, and shared
production settings are unchanged. This follows the September 24 full-return
5-us timing tests, rather than overlapping readout with a longer correction.
The 25-us probe delay remains separate from this return interval.

Offline QICK 0.2.133 compilation against the saved ZCU216 configuration and
calibration uses 761 instructions for science and 1,527 for reference blocks,
out of 8,192. The saved report is
`q3_fast_single_point_map_20261005_5us_preflight.json`. The earlier preflight
report above describes the original 40-us implementation. Scheduler tests
exercise all four holds (reference, 2, 10, and 25 us), including zero-tail
padding and the final synchronization. Generator rounding and the existing
park pulse add small hardware timing overhead; no new hardware result is
claimed by this offline check. Focused tests: 166 passed with QICK available.

Bare root pytest retains six pre-existing collection errors:
- Archive/q4diamond/Client_modules/Running_Experiments_MUX/Timing_test.py: missing qick.
- WorkingProjects/Inductive_Coupler/Client_modules/Running_Experiments_MUX/Timing_test.py: missing qick.
- WorkingProjects/Tantalum_fluxonium_escher/Client_modules/Calib_escher/Experiment_test.py: unavailable hardware proxy (None.list).
- WorkingProjects/Tantalum_fluxonium_escher/Client_modules/Experiments/mFFDelayedTransSlice_test.py: missing PyQt5.
- WorkingProjects/Tantalum_fluxonium_escher/Client_modules/Experiments/mFFSpecSlice_test.py: missing PyQt5.
- WorkingProjects/Tantalum_fluxonium_marvin/Client_modules/Experiments/mTransmission_GUI_test.py: duplicate imported test module name.

The October 5 q5 scout failed at SS calibration (F=0.530) before its first
flux excursion. Its saved frequencies, pulse amplitudes, lengths, and mixer settings match
successful September 27 SS calibrations. The stored readout angle differs
(-2.62575 versus -0.85672 rad); SS calibration measures both IQ quadratures
and fits the discrimination axis, so a coordinate rotation alone does not
explain the lost blob separation. YOKO metadata is corrected to the user's
actual 0 V; an obsolete unused flux_cphase key is also absent. Hardware path
and current qubit/readout frequency calibration remain unverified.
The QUA scout can request the same complete 5-us return with
`Q5_5PT_RECOVERY_US=5`, leaving `Q5_5PT_READOUT_AFTER_RETURN_US` empty.
The calibration failure must be diagnosed separately; do not lower its gate.

The maintained test suite passed: 1,475 tests in 40.51 s. An independent review
found no actionable issues in the timing change.

## October 6: minimum-shot full-band recording

The user requested replacing the running 50 MHz movie with an infinite
3.9–4.3 GHz movie at the fastest supported settings. The running October 6
process still has the old 40 µs return loaded. Pulling alone cannot alter an
already imported module: stop it with Ctrl+C, wait for the shell prompt,
then pull and launch a new process. The committed fast-map timing already
uses a full 5 µs corrected return before final readout.

Retain 0.5 MHz spacing (801 frequencies) and the 25 µs science probe, but
use four alternating sweeps per science map: 3,204 final records. This is
the runner's minimum supported shot count, and individual maps will be
noisy. All raw shots are retained for later averaging. Readout integration
remains 3.5 µs at gain 940; verified active-reset feedback/recovery timing
remains unchanged. Shortening those further has not been validated.

Added `--reference-shots` for independent periodic-reference statistics.
Its default is the science count, preserving existing commands. The wide
command uses 40 shots per periodic-reference condition every 100 science
maps, and existing 250-shot endpoint references. Four-shot P0/P1 estimates
would add substantial frequency-dependent normalization noise; using more
shots in sparse reference blocks avoids that particular shortcut. Reference
interpolation still assumes no unobserved rapid reference changes.

Each batch contains 1,000 science maps, nine periodic reference blocks and
two endpoint reference blocks, with a fresh calibration before the next
batch. The loop has no total map limit; it stops on Ctrl+C or a calibration/
acquisition error. Reference drift is flagged and masks derived data while
raw IQ survives. The first high-shot full-band reference will take longer
than a science map; later references and recalibrations create real pauses.

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSFastSinglePointMap --run --loop --frames 1000 --center-ghz 4.100 --width-mhz 400 --step-mhz 0.5 --delay-us 25 --shots 4 --reference-every 100 --reference-shots 40 --readout-gain 940
```

The most recent twenty completed science maps in the old 50 MHz batch
`q3_fast_single_point_map_20261006T061823Z_4a2d681d` had median acquisition
0.511 s, compile 0.028 s and start spacing 0.673 s. The new full-band map
has fewer records (3,204 versus 4,040) and a shorter return, so roughly
0.5–1 s per science map is a planning estimate. It is not an observed
full-band cadence, and reference/calibration pauses are excluded.

Offline QICK 0.2.133 compilation with Python 3.10/NumPy 1.26.4 and the
saved board/calibration confirms all three 801-frequency block types fit:
science four shots uses 761/8,192 instructions and 3,204 records; periodic
references 40 shots use 1,527 instructions and 96,120 records; endpoint
references 250 shots use 1,527 instructions and 600,750 records. Maximum
waveform memory is 55,040/65,536 samples. The adjacent
`q3_fast_single_point_full_band_20261006_preflight.json` retains full
memory/stream-bank reports and realized frequency errors. This checks
compilation and memory, not execution or cadence on hardware.

Validation: 21 single-point tests passed, including independent reference
counts, minimum-shot full-band planning, invalid inputs, saved reference
array dimensions and repeated CLI propagation. Maintained suite: 1,482
passed. CLI plan, Python compilation and whitespace checks passed;
independent review found no actionable findings. Existing production/reset,
initialize.py and QUA sources are unchanged.
