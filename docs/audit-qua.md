# QUA predistortion audit and isolated software adapter

Audited baseline: `422b6c9`, branch `codex/controller-neutral-predistortion`.
This audit did not run hardware, import the experiment stack, change legacy
paths, or write to `/Volumes`. File line references below refer to that baseline.

## Findings that affect identification and validation

* `LabCode/Helpers/flux_predistortion.py:647` solves a bounded, regularized
  piecewise command using shifted measured step responses. At lines 691 and
  713–727, time is reset to the first retained measurement and the response
  outside the measured window is held constant. This cannot identify the
  missing onset or the long unmeasured tail. Fitting a corrected trace identifies
  the effective corrected system, not the original bare flux line.
* `LabCode/Helpers/flux_predistortion.py:889` composes schedules only on the
  union of their edges. An exact cascade also has transitions at pairwise sums
  of edges. Reproduction: previous edges `[0,500]`, levels `[1,2]`, adjustment
  edges `[0,1000]`, levels `[1,0.5]`, damping 1 emits levels `[1,2,1.5]` at
  `[0,500,1000]`; the exact cascade changes again to 1 at 1500 ns. The saved
  approximation stays at 1.5. Lines 919–924 predict a damped response without
  re-simulating the emitted approximation or clipping.
* `LabCode/Helpers/flux_predistortion.py:1093` labels `plant * dac_output` as a
  filtered step. Pointwise multiplication is not propagation through a causal
  linear plant. Also, the additive exponential fit at lines 23–35 and the
  cascade of individual exponential inverse sections at lines 288–295 have
  different general multi-component transfer functions. Do not use these
  routines to validate the new state-space inverse.
* `LabCode/Helpers/qubit_step_response_trace.py:32` computes the positive-score
  centroid in an 8 MHz half-window after subtracting its 20th-percentile floor
  and squaring weights. Its width is a weighted second moment, not an estimated
  uncertainty of the centroid. Broad or overlapping features can move it.
* `LabCode/Experiments/Flux_Predistortion/m_qubit_step_response.py:633` removes a
  smooth frequency background and normalizes each slice's feature score.
  Lines 671–719 select a globally smooth ridge. Lines 787–804 smooth the
  extracted frequencies in time (default 17 samples), before support gating at
  904–910. A score threshold is not a calibrated confidence interval. Retain
  raw IQ, unsmoothed local centers, widths, and support for reanalysis.
* `LabCode/Experiments/Flux_Predistortion/m_qubit_step_response.py:579` inverts
  dispersion only between baseline and nominal target. The monotonic branch
  uses endpoint-clamped interpolation at lines 600–606; voltage overshoot
  beyond that interval can disappear. Nonmonotonic intervals use nearest
  frequency at lines 608–613. The normalized frequency response at 994–1001 is
  also different from the voltage-domain response at 1004–1012.
* `LabCode/Control/Flux_Tunable/Q5PredistortionMultiAmplitudeFit.py:106` late
  normalizes each residual independently using the median after 300 us, requires
  95% support, and interpolates unsupported points. The pointwise median of
  three traces is additionally smoothed over 7 samples at lines 143–159. It
  removes static amplitude differences and does not prove global amplitude
  linearity. Source CSVs must share a delay grid but their actual applied
  correction hashes and baseline metadata are not cross-checked (280–323).
* The multi-amplitude new adjustment uses at least 4 us spacing, bounds
  `[0.95,1.05]`, 50% composition damping, final levels `[0.5,1.5]`, and maximum
  change 0.005. Its per-trace 20% improvement gate at lines 385–399 evaluates a
  damped ideal residual composition, not the serialized command through an
  independent plant. The inherited onset remains underconstrained by these
  4 us measurements. Predicted improvement is not measured validation.

## Measurement and production histories differ

`m_qubit_step_response.py:526–550` iterates shots, frequencies, then ascending
delays. Each point hard-sets baseline, waits a fixed rearm interval, applies the
correction only until that delay, and then holds its last command through the
spectroscopy pulse and readout. The flux schedule does not continue while the
probe executes. The next point hard-returns to baseline. Prior hold length thus
changes the starting analog memory unless rearm is demonstrably sufficient.
The transfer validator sets a 100 us rearm and a 500 ns spectroscopy pulse.

`Q5PredistortionTransferValidation.py:140–183` validates only forward steps at
three amplitudes, with no refit. The delays are 1, 5, ..., 497 us (runner uses
exclusive `arange` at `flux_predistortion.py:870`); there is no sub-us onset
measurement. The 50 MHz scan starts at the fitted target and is centered 25 MHz
above it. Its frequencies/voltages are 4.3 GHz/0.362635611657 V,
4.053766324990 GHz/0.394 V, and 3.8 GHz/0.422429863264 V. The fit script calls
the center input “4.08 GHz”; do not confuse its observed ridge label with the
dispersion prediction.

`ThreePointApplesToApples.py:242,285` explicitly disables tail compensation in
both precompile and execution. It inherits `TLSSpectroscopy.py:78` park
**0.1625 V**; the transfer validator explicitly overrides park to **0.1827868 V**.
These are distinct excursions. Its active-reset cadence is variable, with
10 us waits and confidence-triggered loops.

`m_swap_spec_vs_flux.py:1008–1009,1090–1113` uses an outbound hold of Ts plus
settle (100.5 us with the current runner), then a separate 0.5 us return hold.
Each `_hold_flux_step` starts its correction from time zero and restores the
nominal target at its end (357–411). For a normalized inverse step c(t), the
complete round-trip command is proportional to c(t)-c(t-T). An independent
reversed step instead gives 1-c(t-T), losing the still-active c(t)-1 history.
Resetting a software state at that edge does not erase physical memory.
Active reset follows readout at lines 1125–1133; any model must either advance
through the actual variable elapsed time or establish a bounded settled-park
boundary before a new prepared shot.

## Existing scheduler and configuration limitations

* `_coerce_flux_tail_compensation` at `m_swap_spec_vs_flux.py:306` drops nonfinite
  points, accepts negative edges, rounds edges upward to 4 ns clocks, and keeps
  the first point when edges collapse. Edges `[0,1,5,9]` produce `[0,1,2,3]`
  clocks, although QUA waits need at least 4 clocks. The new adapter rejects
  malformed, collapsed, and short segments rather than altering their meaning.
* Old `_hold_flux_step` emits unrolled conditionals for every retained segment.
  Its comment at 372–378 records a five-minute compiler timeout for a
  78-segment program and motivates pruning by maximum hold. Python source
  operation counts are not QOP compiled-memory measurements.
* The old multiplier bounds do not bound absolute voltage. At park 0.1827868 V,
  the 3.8 GHz excursion and multiplier 1.5 yield **0.542251395 V**. This is a
  possible allowed-bound command, not a claim about the fitted candidate's
  actual maximum. It exceeds the nominal direct OPX output range.
* `LabCode/Config/config_helpers.py:344–386` can load output filters from several
  metadata aliases. Lines 411–420 can add legacy `feedback_taps` and
  `feedforward_taps` even when the newer metadata flag disables filters. Check
  the final addressed port configuration, not just a runner flag.
* `LabCode/CoreLib/experiment.py:19` initializes a hardware QMM during import;
  its base constructor also creates data directories. The new offline adapter
  never imports it. The old files named `flux_predistortion_arbitrary_waveform`
  are not a usable arbitrary-waveform implementation: the control file aliases
  the ordinary runner and the experiment still uses `set_dc_offset` at line 261.

Official QUA documentation specifies 4 ns clocks, a 4-clock minimum wait, and
notes that computation can add timing latency. Therefore waveform timing must
be inspected in the installed compiler/simulator; offline lowering does not
prove physical timing. See [QUA 1.2 API](https://docs.quantum-machines.co/1.2.0/docs/API_references/qua/dsl_main/).
The nominal direct-output range and offset-plus-waveform overflow constraint
are documented in [QM API](https://docs.quantum-machines.co/1.2.3/docs/API_references/qm_opx1000_api/).
If later adding sampled pulse emission, waveform memory compression and sample
rate are separate decisions; see [configuration](https://docs.quantum-machines.co/1.2.6/docs/Introduction/config/).

## New isolated adapter

`fluxpred/qua.py` lowers the shared normalized absolute Command to immutable
voltage/clock tuples. It uses cumulative `numpy.rint` quantization, rejects
sub-16-ns waits, rejects pre/post-quantization output overflow, estimates source
instructions, reconstructs the realized normalized command, and never installs
an OPX filter. `emit` rejects a nonempty final flux-port filter before importing
QUA or emitting statements. `hardware_compiled=False` is deliberate.

`LabCode/Helpers/neutral_flux.py` is an explicit opt-in bridge. A new shot owner
must establish a settled park boundary after active reset, then call
`start_prepared_schedule(..., initial_state='settled_park')`. The emitter aligns
flux, drive, and readout once at the start, emits only flux-timeline waits, and
leaves drive/readout timelines at that start so probe operations can run during
the schedule. Do not align through the full flux schedule before placing the
probe. The caller's command contains the whole outbound/return/tail history;
there is no hidden final voltage reset. The explicit initial-state marker is
an assertion by the caller, not a hardware validation.

Offline verification: baseline 12 tests passed before edits. The new backend's
12 tests cover cumulative quantization, normalized reconstruction, amplitude
and duration limits, program budget, filter rejection, no hardware imports,
unchanged probe timing after three different active-reset lengths, and final
level persistence. All 24 unittest-discovered tests pass with Python 3.13,
NumPy 2.3.1, SciPy 1.15.2; these differ from the repository's pinned hardware
environment. No actual QOP compilation or physical timing validation was run.
