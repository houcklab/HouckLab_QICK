# Isolated OPX-Style Active Reset for QICK

**Status:** Approved architecture; written design awaiting final review

**Date:** 2026-09-04

**Initial target:** q3, QICK 0.2.133, tProc v1

## Purpose

Build and validate a new active-reset implementation whose control flow matches the QUA/OPX experiment semantics, without changing any production experiment. The implementation will live in a new, isolated `active_reset_OPX` package until hardware measurements demonstrate that it is at least as reliable as the QUA reset.

The essential change is not merely a different discriminator. The QICK program must use the payload experiment's final measurement as its first reset decision, stop immediately when the qubit is confidently in the ground state, apply a pi pulse only when confidently excited, and remeasure when the result is ambiguous. All decisions and jumps must execute on the tProc; a host-side Python decision loop is too slow and does not reproduce QUA timing.

## Scope

This phase will:

- create `WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/`;
- implement bounded, data-dependent reset control flow in tProc-v1 assembly through QICK 0.2.133;
- calibrate the classifier at the timing actually used inside the reset loop;
- provide a q3-only calibration and benchmark runner;
- save enough raw data and telemetry to diagnose every branch and failure;
- compare the new implementation with no reset, the current production QICK reset, and QUA reset data;
- leave the existing T1, T1-vs-flux, Rabi-chevron-SS, and other production programs unchanged.

This phase will not:

- replace or modify `Client_modules/Helpers/active_reset.py` or `active_reset_rot.py`;
- silently fall back to passive reset when the new reset fails;
- modify the P6 TLS workflow;
- claim equivalence to QUA without a same-day, statistically powered hardware comparison;
- try to correct a non-DC-coupled flux path in software.

Production integration is a later phase with a separate design and review after this subsystem passes its promotion gate.

## Reference Behavior

The reference is the QUA reset used by the coherence experiments. In normalized classifier coordinates, larger values mean “more excited.” Every raw-I/Q convention is converted to this one orientation during calibration.

The required state machine is:

```text
payload final measurement -> decision value z

for reset_attempt in 0..max_reset_attempts-1:
    if z <= ground_threshold[reset_attempt]:
        terminal = CONFIRMED_GROUND
        exit immediately

    if z > excited_threshold[reset_attempt]:
        play calibrated X180
    else:
        # ambiguous: do not risk an incorrect X180
        play no qubit pulse

    wait the calibrated feedback/readout cadence
    measure again -> z

if z <= ground_threshold_after_last_attempt:
    terminal = CONFIRMED_GROUND
    exit

terminal = MAX_ITERATIONS_REACHED
```

The first `z` is the final readout of the payload experiment. It is not an extra herald measurement. A separate post-reset verification readout is added only by the isolated benchmark program and is never part of the reset decision loop.

The default safety ceiling is eight corrective reset attempts after decision zero, matching the intended `max_active_reset_iters=8` QUA experiment configuration while preventing an unbounded hardware loop. At most eight reset remeasurements and nine decisions (including the payload measurement) occur. The eighth remeasurement is evaluated before a timeout is declared. Reaching the ceiling without confirming ground is a recorded reset failure, not a successful ground preparation.

## Why a New Implementation Is Required

The current production QICK reset emits a fixed number of reset-measurement blocks. Its conditional branch can skip a pi pulse, but it does not exit the reset sequence as soon as ground is confirmed. Acquisition also assumes a fixed number of readouts per shot and reshapes the streamed data accordingly.

QICK 0.2.133 and tProc v1 already provide the required primitives: feedback-port reads, conditional jumps, register arithmetic, and data-memory writes. The hardware can therefore make the reset decision without returning to Python. The incompatibility is in the current program and acquisition abstractions, not in the fundamental tProc instruction set.

The new implementation will use generated, bounded branch blocks rather than the existing fixed-readout helper. The initial decision and eight corrective-attempt blocks are unrolled at compile time, but a ground branch jumps directly to the terminal label, so runtime and number of readouts genuinely vary shot by shot.

## Package Layout

```text
WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/
    __init__.py
    README.md
    config.py
    fixed_point.py
    classifier.py
    programs.py
    acquisition.py
    calibration.py
    analysis.py
    benchmark_q3.py
    tests/
        test_classifier.py
        test_control_flow.py
        test_memory_layout.py
        test_acquisition_parser.py
        test_config_validation.py
```

Responsibilities:

- `config.py`: typed/default configuration, validation, and a frozen record of the effective hardware settings.
- `fixed_point.py`: overflow-checked conversion between floating-point rotations/thresholds and tProc integer arithmetic.
- `classifier.py`: fit the projection direction, orient it ground-to-excited, fit the two confidence thresholds, and report held-out classification statistics.
- `programs.py`: isolated calibration and benchmark programs plus the assembly-emitting reset state machine.
- `acquisition.py`: direct program execution, tProc completion handling, bounded data-memory reads, record decoding, and safe hardware cleanup. It will not call the fixed-shape `AveragerProgram.acquire` path for the variable loop.
- `calibration.py`: stage-by-stage calibration orchestration and JSON serialization.
- `analysis.py`: confidence intervals, residual-excitation estimates, attempt distributions, and comparison plots.
- `benchmark_q3.py`: the only executable measurement runner in this phase. All q3-specific values remain in its user-editable configuration block.

The package must not be imported by production runners during this phase.

## Classifier Design

### Projection

The classifier uses a rotated projection of the integrated I/Q measurement:

```text
z = sign * (I*cos(theta) + Q*sin(theta))
```

`sign` is chosen so the excited centroid is greater than the ground centroid. The exact expression is converted to bounded tProc fixed-point arithmetic. Calibration must verify all intermediate values against the signed register width; a configuration that can overflow is rejected rather than clipped.

### Three zones

Each decision has two thresholds:

- `z <= ground_threshold`: confidently ground; exit;
- `ground_threshold < z <= excited_threshold`: ambiguous; remeasure without a pi pulse;
- `z > excited_threshold`: confidently excited; apply X180 and remeasure.

The ground threshold controls false acceptance of an excited state. The excited threshold controls false pi pulses on a ground state. The gap is deliberately allowed to trade a small amount of additional measurement time for safer decisions.

### Timing-matched calibration

The threshold used after a prior measurement cannot be assumed to equal a standalone single-shot-calibration threshold. Residual cavity field, feedback latency, pi-pulse timing, and the reset read delay change the distributions seen inside the loop.

Calibration therefore records prepared-ground and prepared-excited distributions in two contexts:

1. the payload-final-readout context used for decision zero;
2. the post-measurement loop cadence used for subsequent decisions.

The implementation supports one threshold pair for decision zero and one pair for decisions one through eight. It may serialize per-decision diagnostic fits, but a more complex per-iteration threshold bank will only be enabled if the recorded distributions demonstrate a statistically meaningful timing dependence. This avoids fitting noise while preserving a path to handle real drift.

Training and evaluation shots are separated. The saved calibration includes the fit data summary, held-out confusion matrices, projection scale, fixed-point coefficients, threshold values, timing, firmware/QICK version, generator and readout channels, and configuration hash.

## tProc Program Design

### Reset state machine

`programs.py` will expose a small assembly-emitting component that is called immediately after a measurement whose I/Q result is available on the feedback input. It receives dedicated register and label allocations instead of using hard-coded global register numbers.

For the initial decision and each of the eight compile-time corrective-attempt blocks it will:

1. wait until the integrated result is valid on the feedback path;
2. read I and Q from the feedback port;
3. compute the signed, rotated classifier value with checked fixed-point operations;
4. branch to `confirmed_ground` if it passes the ground-confidence criterion;
5. branch around X180 unless it passes the excited-confidence criterion;
6. conditionally emit X180;
7. wait/align for the calibrated cadence;
8. issue the next measurement and continue to the next decision block when another attempt remains.

After the eighth corrective attempt, the program evaluates its remeasurement once and branches either to `confirmed_ground` or `max_iterations_reached`; it does not emit another pi pulse or measurement. Both terminal paths write status telemetry. No path can execute a ninth corrective attempt or a tenth decision.

The branch behavior will first be verified with a small instruction-level interpreter in the unit tests. Test vectors will cover immediate ground, excited then ground, repeated ambiguity, reversed raw-I/Q orientation, signed boundary values, and the maximum-iteration path.

### Shot and block structure

The benchmark program executes many shots in a tProc outer loop. Each shot contains:

1. prepared ground or prepared excited state;
2. a payload-style final measurement, which becomes decision zero;
3. the OPX-style reset state machine;
4. an independent verification measurement;
5. restoration of the requested idle state and the configured inter-shot delay.

Ground-prepared and excited-prepared conditions are interleaved in short blocks to reject slow drift. Comparator modes—no reset and the existing production reset—use the same preparation, verification readout, and timing wherever their semantics permit.

### Data memory and variable read counts

The standard QICK averager assumes a fixed `readouts_per_experiment`, so it is not the acquisition engine for this program. The new acquisition layer starts the compiled tProc program directly, waits for a bounded completion condition, and reads compact records from tProc data memory.

Each shot stores a fixed-size record even though its execution time varies. The record contains at least:

- preparation label;
- decision-zero projected value;
- number of decisions performed;
- number of X180 pulses applied;
- terminal status (`CONFIRMED_GROUND`, `MAX_ITERATIONS_REACHED`, or hardware/software error);
- final verification I and Q;
- optional per-decision zone bits packed into one word.

The exact word layout is versioned. Block size is calculated from the data-memory capacity reported by the connected board and the words per record. The runner refuses to start a block that could overflow data memory. Address arithmetic and packing/unpacking are unit-tested.

If raw per-decision I/Q is requested for a diagnostic run, the runner reduces the block size to fit the expanded record. Routine benchmarks store compact decision telemetry plus the independent verification I/Q.

### Timing and channel ownership

The reset component explicitly owns its feedback registers, scratch registers, labels, and timing variables. Program construction fails on register collisions. The qubit, resonator, ADC, and fast-flux channels are synchronized at the same points in every comparator program.

When a park-flux pulse is requested, it is raised before state preparation, held with the configured steady-output mode through the payload measurement, reset loop, and verification measurement, and restored to the configured idle gain afterward. This preserves the existing short-timescale park behavior; it does not claim to turn an AC-coupled analog output into a DC source.

## Acquisition and Safety

The runner performs the following checks before enabling outputs:

- QICK package version and board configuration are compatible with 0.2.133/tProc v1;
- the expected feedback data port and I/Q word ordering pass a signedness self-test;
- thresholds and fixed-point products fit their register widths;
- all waveform, register, label, program-memory, and data-memory allocations fit;
- the configured maximum corrective-attempt count is between one and eight;
- a finite host timeout is derived from the worst-case per-shot sequence time and block size.

On timeout, malformed telemetry, capacity violation, or classifier-calibration failure, the isolated runner aborts. It does not substitute passive reset and continue. Cleanup runs in `finally`: generators are returned to their requested idle values, the tProc is stopped when supported by the connected QICK version, and the partial block is saved with an explicit failure status.

The runner writes data incrementally after every block so a later fault does not discard completed measurements. It records start/end timestamps, host and board versions, the source commit, complete effective configuration, calibration identifier, and every exception.

## Calibration Workflow

The q3 runner exposes explicit stages that can be run and inspected separately:

1. **Feedback-path self-test.** Verify I/Q port ordering, signed representation, decision latency, and deterministic visibility of the latest readout.
2. **Timing-matched reference capture.** Acquire prepared-ground and prepared-excited data for the payload and in-loop contexts.
3. **Classifier fit and holdout validation.** Fit rotation and confidence thresholds; reject inadequate separation, excessive false-ground acceptance, or fixed-point overflow.
4. **Reset timing calibration.** Sweep the measurement-to-decision wait, post-pi alignment, and reset-read delay over a bounded grid. Select the shortest stable values, not simply the shortest observed values.
5. **Bounded-loop benchmark.** Compare no reset, current production reset, and OPX-style reset using interleaved prepared-ground and prepared-excited trials.
6. **QUA comparison.** Import a same-day QUA result or a CSV with the same preparation and verification definitions and produce the equivalence report.

Each stage creates a new timestamped artifact. Later stages require a compatible successful artifact from earlier stages and do not silently use unrelated standalone SSCal values.

## Outputs

Every benchmark saves:

- a row-oriented CSV with one row per shot;
- a JSON metadata and calibration record;
- a human-readable text summary;
- plots of verification-I/Q clouds, projected distributions, excited residual by preparation and method, decisions per shot, pi pulses per shot, timeout fraction, and metrics versus block/time;
- the generated assembly listing and a hash of the binary program.

Primary reported quantities are:

- residual excited-state probability after reset for ground-prepared and excited-prepared inputs;
- false-ground acceptance estimated from held-out excited references;
- unnecessary-pi probability estimated from held-out ground references;
- maximum-iteration fraction;
- mean and percentile decision counts and reset duration;
- readout contrast before and after repeated reset operation;
- Wilson or exact binomial confidence intervals for all proportions.

No shot reaching `MAX_ITERATIONS_REACHED` is silently counted as ground. Reports show both an unconditional residual (timeouts included) and a conditional residual for confirmed-ground shots.

## Verification Strategy

### Software verification

Before hardware use:

- all new unit tests pass without requiring `pynq` or a connected board;
- the instruction-level control-flow tests exercise every state-machine branch;
- floating-point and fixed-point classifiers agree on randomized boundary and overflow-safe inputs;
- memory-layout tests prove that no permitted block can exceed board-reported capacity;
- acquisition-parser tests cover complete, partial, timed-out, and corrupt blocks;
- the existing TLS spectroscopy active-reset tests continue to pass unchanged.

### Hardware bring-up

Hardware testing advances only after each preceding gate passes:

1. 100-shot feedback and signedness smoke test with no conditional pi pulse;
2. 100-shot forced-branch test for each terminal path;
3. 1,000-shot prepared-ground and prepared-excited classifier validation;
4. 1,000-shot bounded-loop run with full diagnostic I/Q telemetry;
5. statistically powered interleaved comparison runs.

Any stale-readout signature, register collision, unexplained status word, buffer mismatch, or host timeout blocks advancement.

## Promotion Gate

The subsystem may be proposed for production integration only when all of the following are true:

- zero program hangs, memory overruns, corrupt records, or unexplained terminal states occur in the accepted data set;
- no shot executes more than eight corrective attempts or nine decisions including the payload readout;
- the maximum-iteration fraction is at most 1% for both ground-prepared and excited-prepared inputs;
- post-reset residual excitation is at most 10% for both input preparations;
- the one-sided 95% confidence bound on `(QICK OPX residual - QUA residual)` is no greater than two percentage points for both preparations in a same-day matched comparison;
- unnecessary pi pulses on ground-prepared shots and false-ground acceptance on excited-prepared shots satisfy their calibration confidence limits and show no statistically significant growth across blocks;
- final verification-readout contrast is not reduced by more than 5% relative to the matched no-reset reference;
- results are stable across at least four interleaved blocks of at least 1,000 shots per preparation and method;
- the source, configuration, calibration artifacts, raw shot data, and analysis are sufficient to reproduce every reported metric.

The 10% absolute bound is a sanity ceiling, not the definition of “identically good.” Equivalence to QUA is determined by the two-percentage-point, one-sided confidence bound. If no same-day matched QUA data are available, the implementation may be described as functioning but not as proven equivalent.

## Later Production Integration

After the promotion gate is met and separately approved, a follow-on design will expose the validated state machine through a production helper and integrate it one experiment family at a time. The expected order is:

1. ordinary T1;
2. T1 versus flux / TLS three-point scans;
3. Rabi-chevron single-shot workflows;
4. other experiments that currently select feedback reset.

Each integration must preserve the payload final measurement as decision zero, account for the variable reset duration in experiment timing, update acquisition metadata, and retain a selectable passive-reset path. Production rollout is explicitly outside this design's implementation phase.

## Assumptions and Decisions

- q3 and the board-served QICK 0.2.133 API are the first supported environment.
- tProc v1 conditional branches and feedback reads are sufficient; no FPGA firmware modification is planned initially.
- compile-time unrolling with early terminal jumps is considered true hardware active reset because the executed instruction path and readout count are data-dependent.
- eight corrective attempts are a safety maximum, not a target number of repetitions.
- thresholds are trained in the loop timing where they are used.
- isolated failures are explicit and fail closed; they never trigger an unnoticed passive-reset fallback.
- all commits use the repository's configured Rumman identity and contain no assistant co-author tags.
