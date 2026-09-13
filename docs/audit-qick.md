# QICK predistortion audit

Read-only baseline: `da387a3`, inspected on branch
`codex/controller-neutral-predistortion`. This audit describes the existing
paths; the new neutral adapter does not modify their behavior. Paths below are
relative to the repository root. No hardware calls or network-drive writes were
made. The requested `qubit_step_response_trace.py` and
`active_reset_OPX/predistortion_roundtrip_q3.py` are absent from this QICK checkout;
their QICK counterparts and related paths are described below.

## What the measured response establishes

The QICK extractor is
`WorkingProjects/TLS_Spectroscopy/Client_modules/Helpers/trace_extraction.py`.

- Lines 77–124 choose a globally smooth ridge, with a maximum jump specified per
  adjacent sample rather than per elapsed time. Lines 172–175 fall back to the
  ridge seed when a local Lorentzian fit fails. Line 298 marks every finite
  selected frequency as `supported`; it is not a fit-quality, prominence, SNR,
  or uncertainty test. A controlled baseline assertion confirmed that all
  local fits can fail while every support entry remains true.
- Lines 179–198 fill missing samples with interpolation and smooth with a
  Savitzky–Golay window, normally 17 samples. The time axis is used for filling
  gaps but does not change the smoothing weights. This smooths across a
  physical interval that depends on the scan spacing, and treats irregular
  time spacing as evenly spaced. The resulting apparent early waveform cannot
  independently establish the line's high-frequency transfer function.
- `Experiments/mQubitFluxStepResponse.py:592–627` independently extracts magnitude
  and phase ridges and selects the larger median normalized path score. The
  acquisition phase comes from `np.angle` (lines 1017–1018, 1071–1073); it is not
  unwrapped before being used as a Lorentzian-shaped feature. An observed ridge
  is a spectroscopy estimate, not a directly sampled analog step.
- The legacy RAverager path waits through the flux ramp and hold, adds 10 ns,
  then applies a finite spectroscopy pulse (`mQubitFluxStepResponse.py:90–119`).
  The spectroscopy pulse weights a finite temporal window. With readout after
  park, the return transition and settling may also affect observable contrast.
  A report should preserve requested hold time, physical transition timing,
  spectroscopy pulse length, acquisition order, and readout context.
- `mQubitFluxStepResponse.py:635–654` constructs both frequency-domain and
  voltage-domain normalized responses. The frequency response uses calibration
  baseline and target endpoints, not independently measured asymptotic values
  from the transient. Voltage inference samples a local monotonic branch of a
  parametric flux-frequency model (lines 490–577); when no parametric fit exists,
  it returns NaNs even if a forward CSV lookup exists. Outside the sampled
  branch, lines 549–570 linearly extrapolate inverse voltage with no uncertainty
  or extrapolation flag. Near a sweet spot the inferred voltage can be highly
  sensitive to frequency or branch error. Headers ending in `_V` in this port
  can contain DAC-gain units (`acquire`, lines 969–970); retain explicit units.

`Helpers/flux_predistortion.py` contains several different response assumptions:

- The direct measured wrapper discards nonfinite points, sorts, and zeroes time
  at the first retained sample (1089–1125). Its RMS is zero by construction
  because its fitted response is a copy; this is not validation error.
- Piecewise inversion independently sets `time_zeroed = time_ns - time_ns[0]`
  (603–617), uses linear interpolation and endpoint continuation (639–647),
  then adds command edges as solver evaluation points (655–661). Adding those
  points improves numerical conditioning but creates no new measurements.
  Cropping a blind early region changes the inferred physical time origin
  unless a model explicitly restores it.
- The visible-tail exponential path does provide an explicit physical origin
  and evaluates its fitted model from there (1129–1282). Early values are
  extrapolated from a single-exponential assumption. They must remain labelled
  extrapolated, even if a correction gives a small residual on that model.
- Correction error is evaluated on the same model used for inversion
  (707–749). Multiplier-bound checks (750–760) are not checks of the eventual
  DAC command after the park offset and excursion scale are applied.

## Causal history and real scheduling

`Helpers/ff_pulse.py:145–184` is correct for an isolated two-edge trip from a
known initial park state: if `m(t)` is the inverse unit-step command and the
target is held for `H`, its recovery is `m(H+r) - m(r)`. Shifted breakpoints
are included; a synthetic baseline verified exact coefficients and duration.
`1 - m(r)` would only match after the first edge has fully settled.

This helper has no persistent state, timestamps of earlier trips, or arbitrary
edge history. Each call starts from the same assumed initial state. The default
recovery is 40 us, capped by the last correction edge (`ff_pulse.py:48–69`),
even when the stored response extends to 497 us. `full` uses the stored horizon,
which is still an assumed endpoint continuation, not evidence that an
unmeasured physical tail is absent. Truncating at 40 us and forcing park adds a
new command edge and can leave residual plant state for the next excursion.

The active-reset path is
`WorkingProjects/TLS_Spectroscopy/Client_modules/active_reset_OPX/programs.py`:

1. `_wait_t1_payload` (1339–1436) and `_play_dynamic_compensated_hold`
   (1710–1781) use target duration `max(hold_us, 0.01) + flux_settle_time_us`.
   The desired hold therefore includes the target settling interval. Recovery
   is split into a settling prefix and a tail.
2. Target and prefix are queued, then `sync_all(0)` establishes the readout
   origin. The remaining flux tail and final park latch are queued after that
   origin (1386–1397, 1750–1762). There is no subsequent sync before the payload
   readout, so that readout can overlap the scheduled correction tail.
3. `_measure_raw` (1076–1097) waits for ADC completion plus the read delay, then
   reads the tProc feedback values. `_measure_project` (1099–1124) forms a fixed
   point IQ projection. The payload and loop classifiers use different stored
   calibrations.
4. `control_flow.py:187–260` emits a true unbounded, early-exit runtime reset
   loop. A ground result exits; an excited result gets a pi pulse; an uncertain
   result is remeasured without a pi pulse. Reset attempt counts vary per shot.
   `_wait_reset_ringdown` (programs.py:1126–1130) calls `sync_all` before the
   corrective pi/readout, so it also waits for any pending flux tail. The final
   shot sync (1462, 1816, 2070) likewise includes unfinished channel timelines.
5. Persistent park is latched once and normally remains through runtime reset
   (`ff_pulse.py:470–481`, `programs.py:1158–1179`). Variable reset duration
   changes the dwell at park and therefore the history before the next target
   edge. The repeated two-edge helper does not propagate that dwell into a
   filter state. The compact three-point payload record contains IQ only
   (`programs.py:1943–1945`, `emit_payload_reset_shot:527–549`), so it cannot
   reconstruct exact per-shot dwell times after the fact.

Full inverse-state handling therefore needs either the actual sequence of edge
times, including variable park holds, or a verified return/recovery policy that
bounds the residual before each new excursion. Merely invoking a function
called `stateful` is not sufficient.

## Timing, amplitude, and memory limitations of existing paths

- `ff_pulse.py:250–270` rounds and silently clips each gain to the configured
  symmetric maximum. It rounds each duration independently and forces at least
  three generator cycles. Shifted return edges can be arbitrarily close, so a
  valid mathematical schedule can stretch. A synthetic 250-MHz generator test
  turned requested intervals of 1 ns and 12 ns into 24 ns total. A requested
  gain of 45000 silently became 32767. Long chunks are balanced to avoid a
  short remainder, but this does not fix short source segments or cumulative
  edge drift.
- `programs.py:1622–1690` applies a normalized coefficient at runtime using a
  Q16 magnitude multiplication, right shift, and signed add/subtract. Only the
  target gain axis is range checked (1580–1589, 1949–1958). There is no range
  check for each corrected DAC value or the 32-bit intermediate multiplication.
  `axis_sg_int4_v1` gains are packed into the high word (90–119). Therefore a
  legal target axis alone does not establish corrected-command headroom or
  freedom from fixed-point overflow.
- The spectroscopy QUA-order path is distinct from active-reset stateful T1.
  `qua_order.py:427–474` uses forward correction segments and then restores park
  directly. It does not call the stateful two-edge recovery helper.
  `_play_flux_point` (454–460) latches a three-cycle hard step and then syncs
  for the requested duration. The compact compensated runtime loop (368–417)
  likewise latches and aligns before its duration wait. That latch time must
  be included in realized edge timing; the requested hold is not itself a
  waveform timestamp. The runtime hold lookup (333–365) saves program memory
  relative to unrolling every delay.
- The old non-QUA spectroscopy path uses a ramp-up, corrected plateau, and
  independent reverse ramp (`mQubitFluxStepResponse.py:90–119`). Its applied
  input is different from a hard-step inverse command. Recorded ramp mismatch
  metadata produces warnings only (`ff_pulse.py:575–614`).
- DMem streaming/LUT allocations are checked (`programs.py:180–233`,
  1975–1997). That is separate from tProc instruction memory. Tail segments,
  delay points, and alternating scan branches increase unrolled instructions;
  there is no actual program-size guard in these inspected helper paths.
  Minimum legal constant-pulse length also does not prove sustainable tProc
  dispatch rate, FIFO capacity, or sufficient lead before an early drive.

## Dedicated Apples-to-Apples path and new integration boundary

`Runners/ThreePointApplesToApples.py:44–69` specifies the dedicated 100-us
three-point scan. It converts the common 0.5-MHz grid to a monotonic integer DAC
lookup and checks frequency quantization error (72–106). Correction is explicitly
disabled (235–236 and 281). It uses an alternating bidirectional lookup scan and
distributed reference measurements through `OPXResetT13PointProgram`; runtime
reset is applied after each payload. `active_reset_OPX/production.py:82–110`
selects QUA shot order, persistent/hard park settings from the benchmark, and
active or passive reset delay. None of these paths were changed.

The additive integration is `fluxpred/qick.py` plus
`Helpers/neutral_flux.py`. The former compiles an already-designed *complete*
command, rounds cumulative fabric-clock edges and nearest-even integer gains,
merges equal levels, rejects sub-three-cycle distinct intervals and all gain
clipping, and balances chunks up to 65000 cycles. Its reconstructed `Command`
is the waveform that offline plant simulation must use. It allocates zero
waveform samples and reports an instruction allowance, explicitly not a real
QICK compilation or dispatch feasibility result.

The new helper requires the caller to finish reset at park, account for or bound
prior physical history, provide an explicit final park plateau, and establish a
shared origin. It aligns only before emission, then queues the entire flux
schedule without aligning through it. A new runner can queue drive and readout
at explicit offsets on other channels, and align all channels afterward. The
runner still needs a measured/modelled terminal-state bound, a sufficient
instruction-dispatch lead, and full compiled-program timing/memory checks.
An acknowledgment boolean cannot verify physical settling.

The minimum isolated extension for the existing scan semantics is a new runner
and a new subclass overriding `_wait_three_point_payload`, using the new
compiler and complete precomputed histories. It should preserve the dedicated
gain lookup and scan ordering while requiring explicit neutral selection.
Feeding a new method string to `load_compensation_json` is inappropriate: the
legacy loader accepts only `rise_decay_bump_set_dc_offset_correction`
(`flux_predistortion.py:1417–1440`). Do not rename a new artifact to pass this
legacy gate or monkeypatch the existing runner.

## Verification scope

No dedicated baseline tests were present in the QICK checkout, and the local
Python environment does not have `qick`. Hardware-free AST assertions exercised
the existing two-edge superposition, duration split, 40-us default recovery,
gain clipping, short-duration stretching, and support-mask fallback behavior.
The new deterministic adapter tests exercise real command compilation and a
recording boundary for the unavailable QICK program object. They do not claim
an FPGA compile, measured correction quality, or hardware execution.
