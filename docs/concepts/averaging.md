# Averaging and repetition

Several words in the code mean "do it again". They act at different levels: inside one tProc
program, across reruns of a program, or across whole experiments. Mixing them up costs time and,
in single-shot programs, silently loses data.

## Vocabulary

| Name (legacy key) | Level | What it does | Notes |
|---|---|---|---|
| `reps` | hardware, one tProc program | the tProc loops the body `reps` times; QICK averages the readouts | `AveragerProgram` reads `cfg["reps"]` in `make_program()` at construction: set it before building the program |
| `rounds` | software | the same program is run `rounds` times; results are averaged in Python | each round is a new program start (see the race below); raw per-shot buffers keep only the **last** round |
| `expts` | hardware sweep | number of points of a register sweep (`RAveragerProgram`: frequency, gain, wait) | total shots = `reps x rounds x expts` |
| `shots` (`Shots` in recipes) | single-shot programs | number of single shots; the program sets `reps = shots` and `rounds = 1` | `SingleShotProgram`, `UndrivenSingleShot`; `t1_ss` uses `reps` as shots per wait |
| `soft_avgs` | QICK, decimated acquisition | number of captures averaged by `acquire_decimated` | qick takes `cfg["rounds"]` over `soft_avgs` if both exist |
| `repetitions` | experiment loop | run the whole experiment N times; each run writes its own h5/png/json | coherence recipes (`T1T2_params`, `T2E_params`); also, legacy cross-coupling, the loop count of `trans_qubit_spec` and `charge_dispersion_ramsey` |
| `Repeat` | experiment loop | `undriven_single_shot` passes; each pass its own files, only the last is displayed | |
| `num_cycles` | experiment loop | records of `modified_ramsey`, `modified_ramsey_control`, `two_tone_charge_dispersion_quasicw` | `ss_recalib_every_n_cycles`, `validation_controls_every_n_cycles` count these |
| `cycles` | experiment loop | `interleaved_coherence` cycles (undriven SS -> T1 -> T2R -> T2E) | inner `Repeat` / `repetitions` forced to 1 |
| `reps_per_chunk`, `n_chunks` | `zero_span_parity` strobe | shots per program, programs per record | record length = `reps_per_chunk x n_chunks x sample_period_us x 1e-6` s (about 12 s for 10000 x 60 x 20 us); `reps_per_chunk` is not bounded by `avg_maxlen` (the averages buffer is streamed), only by a 2e7 memory cap |
| `n_captures` | `zero_span_parity` decimated | back-to-back decimated captures, concatenated | boundaries recorded in `gap_indices` |
| `average_shots` | analysis (`undriven_single_shot`) | average n consecutive shots into one time-series point | noise falls as 1/sqrt(n), but switching faster than n x rep period averages away; pick n on the plateau of the rate-vs-averaging panel |
| `average_n_shots` | analysis (`modified_ramsey`) | bin size of the legacy hard-threshold plot only | keep well below one dwell (see the Modified Ramsey page) |

The recipe layer uses one snake_case spelling per concept (for example `shots`, `repeat`) and
maps it to the legacy key inside the run function. The cfg keys themselves are unchanged.

## reps vs rounds: prefer reps

`reps` are hardware averages inside **one** tProc program. `rounds` rerun the whole program and
average in software. `reps=400, rounds=1` and `reps=20, rounds=20` both average 400 shots per
point, but the second starts 20x more tProc programs. Every program start is a chance to hit the
stale-shot-counter race below. Prefer `reps`; raise `rounds` only when the accumulation buffer
overflows.

A transmission slice (`CavitySpecFF`) starts one program per frequency point and round, i.e.
`TransNumPoints x rounds` programs; a charge sweep runs many slices.

## The stale-shot-counter race

Symptom (intermittent, more likely the more programs a step starts):

    ValueError: could not broadcast input array from shape (26,2) into shape (20,2)

The second number is `reps`; the first is `reps` plus leftover counts. Cause: when programs run
back to back, the streamer zeroes the shot counter and starts the next program while the previous
one is still retiring its last reps; those counts land on top of the new run and `acquire` tries
to write more points than it allocated. The condition does not persist. `soc.stop_tproc()`
(tProc v1 full reset and program reload, tens of ms) clears it, and the point can be retried
with a **fresh** program object (the failed one has a half-written buffer).

`CavitySpecFF`, `T1_SS` and `UndrivenSingleShot` retry automatically (`acquire_with_retry`,
3 tries, also on "got too much data"). In every other experiment the error ends the step. Re-run
it, and reduce `rounds` in favour of `reps`.

## "Overflowed the averages buffer" is different

This error means the tProc is outrunning the readout. Lengthen `relax_delay`. Do not retry it
blindly: the same program will fail the same way. `acquire_with_retry` deliberately does not
catch it.

## Single-shot programs and raw buffers

Single-shot style programs read one accumulated I/Q value per shot from the raw buffers.

- `rounds` must be 1. QICK overwrites the raw accumulation buffer every round, so with
  `rounds > 1` only the last round survives and the earlier ones are dropped without a warning.
  `SingleShotProgram`, `T1_SS` and `UndrivenSingleShot` force `rounds = 1`; `ChiShift` sets it in
  `initialize`; `ModifiedRamsey` raises if `rounds != 1`; `AmplitudeRabiFF_N` folds
  `reps *= rounds; rounds = 1`. Scale `reps` (or `shots`) instead.
- qick changed the buffer layout. Up to about 0.2.28x, `prog.di_buf` / `prog.dq_buf` held the flat
  raw stream (`reps x reads_per_shot`, times `expts` for `RAveragerProgram`). From about 0.2.29x
  they hold one averaged, length-normalised point per read, and old reshapes fail with
  `ValueError: cannot reshape array of size 1 into shape (1,1000)`. The raw stream is then in
  `prog.acc_buf`, shaped `(*loop_dims, reads_per_shot, 2)`, raw units, no normalisation or offset
  removal. The client is pinned at qick 0.2.334, which still exposes the raw `di_buf`; the board
  runs 0.2.367. `qicklab.core.acquisition.raw_shot_buffers` returns the raw stream on either
  version. Only `UndrivenSingleShot` uses it; `SingleShotProgram`, `ActiveResetVerify`,
  `ModifiedRamsey`, `ZeroSpanParity`, `T1_SS` and `ChargeDispersionQuasiCW` read `di_buf` directly
  and would break on a client upgrade.
- `di_buf` / `dq_buf` are indexed by readout **declaration order**, not by absolute ADC channel.
  `soccfg["readouts"][ch]` is keyed by absolute channel.
- `ChargeDispersionQuasiCW` reshapes its raw stream as `reshape(expts, reps).T`; for qick 0.2.334
  the accumulator loop order is `[expts, reps]` (expts outer), so the result `(reps, expts)` is
  correct.
- `acquire_decimated` returns, per readout channel, `(2, length)` for `reps = 1` and
  `(reps, 2, length)` for `reps > 1`; some code paths give `(length, 2)`. Do not pass `soft_avgs`
  to it: `AveragerProgram` injects it and the keyword collides.
- `zero_span_parity`: `soft_avgs` must be 1 unless `allow_soft_avgs=True`, because averaging
  independent captures destroys parity trajectories. A `rounds` key in its cfg would override
  `soft_avgs` and bypass that check (the run function builds a cfg without `rounds`).
- Chunked acquisitions (`zero_span_parity` strobe with `n_chunks > 1`): each inner `acquire()`
  leaves only its last chunk in `experiment.data`; the chunking helper assembles and stores the
  full record.

## Chunked acquisition helpers

`qicklab.core.acquisition` holds the helpers used above.

- `acquire_with_retry(make_prog, soc, n_tries=3, label="", **acquire_kwargs)` builds a fresh
  program with `make_prog()` on every attempt and returns `prog.acquire(soc, **acquire_kwargs)`
  (the failed program has a half-written accumulation buffer and must not be reused). It retries
  only a `ValueError` or `RuntimeError` whose text contains `could not broadcast input array` or
  `got too much data`. Any other exception type passes through uncaught even when its text holds
  a marker, and a `ValueError`/`RuntimeError` without a marker is re-raised unchanged. After each
  transient failure (the last one included) it prints the error, calls `soc.stop_tproc()` (a
  failure there is printed and ignored) and sleeps 0.1 s. After `n_tries` transient failures it
  raises `RuntimeError` chained from the last one. Without it a long sweep can lose hours of
  acquisition to the race.
- `chunked_acquire(experiment, n_chunks)` calls `experiment.acquire(progress=False)` `n_chunks`
  times. Each call must return 1-D `I`, `Q`, `t_us` of equal length and optionally
  `wall_clock_start`. The stitched `t_us` is monotonic: each later chunk is shifted by the
  previous chunk's last `t_us` plus the sample period (its intra-chunk spacing; for a
  single-sample chunk the first chunk's `sample_period_us`, else `experiment.cfg`, so no
  timestamp repeats, spec §6.2). Python + tProc gaps between chunks are **not** modelled in
  `t_us`; `gap_indices` (first index of every chunk after the first, `n_chunks - 1` entries)
  marks them so the analysis never counts a switch across one. It also returns
  `chunk_wall_clock_starts` and `chunk_wall_clock_ends` (each chunk's optional
  `wall_clock_start` / `wall_clock_end`, None when absent). They bracket each chunk's
  `acquire()` call, program load and final transfer included, so with T the sampling time
  of one chunk they bound the gap between chunk i's last sample and chunk i+1's first:
  `starts[i+1] - ends[i] <= gap <= ends[i+1] - starts[i] - 2T`; `(ends[i] - starts[i]) - T`
  is chunk i's overhead. It also returns `n_chunks`, `wall_clock_start` (first chunk),
  `wall_clock_end` (last chunk), and the mode/unit keys (`mode`,
  `sample_period_us`, `read_length_us`, `adc_trig_offset_us`, `ro_norm_cycles`,
  `decimated_fs_MHz`, `decimated_fs_source`, `capture_length_us`, `samples_per_capture`,
  `soft_avgs`, `n_captures`) copied from the first chunk. It sets
  `experiment.data = {"data": stitched}`, so a bare `save_data()` writes the whole record.
- `modulated_strobe_acquire(experiment, gain_schedule, reps_per_block)` runs one block per gain
  (e.g. `[G_on, 0, G_on, 0, ...]`), calling `experiment.set_qubit_gain(gain)` before each
  `acquire()`. `reps_per_block` (= time samples per block) must be >= 1 (else `ValueError`)
  and <= `avg_maxlen`, so each block fits the averages buffer without streaming (checked
  before any block when the experiment has a `soccfg` and `ro_chs`; else `RuntimeError`).
  This cap is the helper's choice, not a qick limit (see zero_span_parity rule 4). `set_qubit_gain` compiles `cfg["reps"]`, which
  it re-syncs from `cfg["reps_per_chunk"]`, so for the blocks the helper sets both keys to
  `reps_per_block`. Afterwards (also when a block raises) it restores both keys and rebuilds
  the program once with them at the last gain applied. It returns the `chunked_acquire` keys
  plus `modulation_reference` (per sample, 1.0 where the block gain > 0, else 0.0),
  `block_labels` (the gains applied), `reps_per_block`, `sample_period_us` and
  `modulation_freq_hz` = `1 / (2 x reps_per_block x sample_period_us x 1e-6)`. That frequency
  is in stitched sample time: like `chunked_acquire`, the stitched `t_us` leaves out the dead
  time between block programs, so the wall-clock modulation is slower. It does not set
  `experiment.data` and leaves the experiment at the last gain of the schedule.
- `raw_shot_buffers(prog)` returns one flat raw array per declared readout channel, length
  `prod(loop_dims) x reads_per_shot`. With `rounds > 1` `acc_buf` holds the last round only,
  which matches the old `di_buf` (also re-derived per round).

## Estimating run time

Rough wall-clock per point: `reps x rounds x` rep period, where the rep period is the scheduled
sequence (pulses + readout + `relax_delay`, or `syncdelay`) plus Python and transfer overhead
per program start. For shot records the physical time base is the compiled tProc schedule
(`scheduled_rep_period_us`), not wall-clock statistics from the streamer.

Measured examples (Modified Ramsey, CSTQ03 Q2, 2026-08-04): rep period about 11.75 us with no
relax delay, about 262 us with 250 us relax; at 250 us relax, 100k shots take about 26 s.

## Known issues

- Only `CavitySpecFF`, `T1_SS` and `UndrivenSingleShot` retry the stale-shot-counter error; long
  loops of other experiments can stop on it. `T1_SS` and the `UndrivenSingleShot` charge sweep
  save their completed points when they stop; the others lose the step.
- `AmplitudeRabiFF_N` and `ChiShift` rewrite `reps` / `rounds` in the experiment cfg; the saved
  config shows `reps x rounds` and `rounds = 1`, not what the step was given.
- `trans_qubit_spec` loops `repetitions` from the coherence group (1000 in the CSTQ03 runner), and
  `charge_dispersion_ramsey` also uses it: changing the coherence group changes those steps.
- `ChargeDispersionQuasiCW` returns averages over all rounds but raw per-shot data from the last
  round only, and its raw arrays are unnormalised accumulator sums while its averages are
  normalised.
- The coherence loops sleep 10 s after every repetition, including the last.
