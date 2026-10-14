# Experiments

One page per **step**. A step is one entry in a session `PLAN`; it wraps one or more
experiment classes (`T1FF`, `QubitSpecSliceFF`, ...) and decides which config they
see, what they save and what they hand to later steps.

- New to the code base: read [running_a_session.md](../running_a_session.md) first, then
  the page of the step you want to run.
- Changing three numbers before a run: jump to the **Parameters** table of the step.
- Every parameter with units and defaults will also be in `docs/parameters.md`, generated
  from the parameter registry (refactor phase 6; not present yet).

## Running a step

```python
from devices.CSTQ03 import DEVICE
from qicklab.core.session import Session, run
from qicklab.runs import recipes as R

SESSION = Session(DEVICE, qubit_readout=5, qubit_pulse=5)

PLAN = [
    R.transmission_fit(),
    R.two_tone_spec(),
    R.amplitude_rabi(),
    R.t1(),
    R.t1(relax_delay=5000),        # repeats allowed; per-step override
]
run(SESSION, PLAN)                 # run(SESSION, PLAN, dry_run=True) compiles every program without hardware
```

The snippets on the experiment pages show only the `PLAN` lines; imports and `SESSION` are
as above. Values resolve as library recipe default < session group
(`Session(coherence=R.coherence(...))`, see
[shared groups](../running_a_session.md#shared-groups)) < keyword on the step. Recipe
keywords are the snake_case form of the legacy keys in each **Parameters** table; the
final spelling comes from the parameter registry.

## Config regimes A and B

Every step runs under one of two configs; `run()` rebuilds the config only when two
consecutive steps differ in regime. Details in
[concepts/config_regimes.md](../concepts/config_regimes.md).

| | Regime A (measurement) | Regime B (single shot) |
|---|---|---|
| Readout window | `Device.readout_window` (CSTQ03: 15 us window, 0.3 us ADC offset) | `Device.ss_window` / `single_shot` group |
| `qubit_gain` means | spectroscopy drive gain | pi-pulse gain |
| Carry-overs | `pulse_freq` (transmission steps) and `res_phase` (active-reset calibration) persist | dropped: rebuilt from `BASE_CONFIG` |

## Index

| Step | Class(es) | Regime | Purpose | Page |
|---|---|---|---|---|
| constant_two_tone | `ConstantTwoTone` | A | Resonator + qubit tones on continuously, no readout | [cw_tones.md](cw_tones.md) |
| constant_tone | `SingleTone` | A | Resonator tone only, no readout | [cw_tones.md](cw_tones.md) |
| transmission_fit | `CavitySpecFF` | A | Resonator sweep + hanger fit; carries the fit minimum to later steps | [transmission_fit.md](transmission_fit.md) |
| transmission_sweep | `CavitySpecFF` | A | Fixed-averaging resonator sweep; carries dip (or peak) to later steps | [transmission_sweep.md](transmission_sweep.md) |
| two_tone_spec | `QubitSpecSliceFF` | A | Qubit spectroscopy, up to two peaks + Lorentzian fits | [two_tone_spec.md](two_tone_spec.md) |
| spec_gain_length_sweep | `QubitSpecSliceFF` | A | Two-tone spec on a grid of drive gain x drive length | [spec_gain_length_sweep.md](spec_gain_length_sweep.md) |
| trans_qubit_spec | `QubitSpecSliceFF` | A | The same two-tone spec repeated many times (time series) | [trans_qubit_spec.md](trans_qubit_spec.md) |
| chi_shift | `ChiShift` | A | Resonator sweep with and without a pi pulse; dispersive shift | [chi_shift.md](chi_shift.md) |
| amplitude_rabi | `AmplitudeRabiFF`, `AmplitudeRabiFF_N` | A | Drive-amplitude sweep; pi gain | [amplitude_rabi.md](amplitude_rabi.md) |
| t1 | `T1FF` | A | Energy relaxation | [t1.md](t1.md) |
| t2_ramsey | `T2R` | A | Ramsey T2*, fringe frequency | [t2_ramsey.md](t2_ramsey.md) |
| t2_echo | `T2EMUX` | A | Hahn / CPMG echo T2E | [t2_echo.md](t2_echo.md) |
| t1_t2e, t1_t2r_t2e | `T1FF`, `T2EMUX`, `T2R` | A | Back-to-back coherence sets, repeated | [coherence_combos.md](coherence_combos.md) |
| interleaved_coherence | `UndrivenSingleShot`, `T1FF`, `T2R`, `T2EMUX` | A, swaps to B per sub-step | Long unattended loop: undriven single shot, T1, T2R, T2E | [interleaved_coherence.md](interleaved_coherence.md) |
| two_tone_charge_dispersion_quasicw | `QubitSpecSliceFF`, `ChargeDispersionQuasiCW` | A | Find the parity doublet, then stream shots at it | [charge_dispersion.md](charge_dispersion.md) |
| modified_ramsey | `ModifiedRamsey` | A | Fixed-tau charge-parity Ramsey record + HMM | [modified_ramsey.md](modified_ramsey.md) |
| modified_ramsey_control | `ModifiedRamsey`, `QubitSpecSliceFF` | A | Sweet-spot control for modified_ramsey | [modified_ramsey_control.md](modified_ramsey_control.md) |
| charge_dispersion_quasicw | `ChargeDispersionQuasiCW` | A | Shot-resolved two-tone at a fixed qubit frequency | [charge_dispersion.md](charge_dispersion.md) |
| charge_dispersion_ramsey | `ChargeDispersion` | A | Fixed-wait Ramsey parity readout | [charge_dispersion.md](charge_dispersion.md) |
| charge_sweep | `QubitSpecSliceFF` | A | Two-tone spec vs charge bias | [charge_sweep.md](charge_sweep.md) |
| charge_transmission_sweep | `CavitySpecFF` | A | Resonator sweep vs charge bias | [charge_transmission_sweep.md](charge_transmission_sweep.md) |
| active_reset_verify | `ActiveResetVerify` | A | Verifies the measurement-based active reset ([how reset works](active_reset.md)) | [active_reset_verify.md](active_reset_verify.md) |
| single_shot | `SingleShotProgramFFMUX` | B | g/e IQ clouds, threshold, readout contrast | [single_shot.md](single_shot.md) |
| undriven_single_shot | `UndrivenSingleShot` | B | IQ clouds and switching with no qubit drive | [undriven_single_shot.md](undriven_single_shot.md) |
| t1_ss | `T1_SS` | B | Single-shot (thresholded) T1 | [t1_single_shot.md](t1_single_shot.md) |
| readout_optimize | `ReadOpt_wSingleShotFF` | B | Readout gain x frequency map | [readout_optimize.md](readout_optimize.md) |
| qubit_optimize | `QubitPulseOpt_wSingleShotFF` | B | Qubit gain x frequency map | [qubit_optimize.md](qubit_optimize.md) |
| auto_coherence | `QubitSpecSliceFF`, `AmplitudeRabiFF`, `SingleShotProgramFFMUX`, `T1FF`, `T2R`, `T2EMUX` | B | Automated calibration, then T1/T2R/T2E | [auto_coherence.md](auto_coherence.md) |
| zero_span_parity | `ZeroSpanParity` | B | Zero-span two-tone parity switching | [zero_span_parity.md](zero_span_parity.md) |

Pages that are not steps: [active_reset.md](active_reset.md) (the reset block shared by
`modified_ramsey` and `active_reset_verify`) and [twpa.md](twpa.md) (standalone TWPA
bias/pump scripts, no session).

## Behaviour common to all steps

- **Files.** `outerFolder` is `<data_root>/Q{qubit_readout}//`. Each experiment instance
  writes `<outerFolder><path>/<path>_<YYYY_MM_DD>/<path>_<YYYY_MM_DD_HH_MM_SS>_data.h5`
  (+ `.png`, `.json`). The h5 holds one float64 dataset per key of `data['data']` and the
  config as a JSON string in `attrs["config"]`; the `.json` holds the same config. Each
  page gives its `path` and any filename suffix.
- **Saved config is the experiment's own copy after the run.** Several experiments write
  into it during acquire/display (`pulse_freq` at the last sweep point, `reps`, `rounds`,
  ...). Each page lists what changes.
- **Units.** Frequencies in MHz as programmed (absolute only while `cavity_LO = 0` and
  `mixer_freq = 0`), times in us, gains in DAC units (0..32767). Raw integers in pulse
  diagrams are tProc cycles (1 cycle = 2.32515 ns at the 430.08 MHz tProc clock of the
  current board). See [concepts/timing_and_units.md](../concepts/timing_and_units.md).
- **Waits.** Every wait in these programs runs from the end of one pulse to the start of the
  next ([timing_and_units](../concepts/timing_and_units.md#waits-are-between-pulse-edges)).
- **Plot windows.** Importing the analysis package currently switches matplotlib to Agg, so
  `plotDisp=True` does not open or block on a window; figures are only saved as PNG
  ([running_a_session](../running_a_session.md#plots)).
- **Fits.** Unless a page says otherwise, fit results are printed and drawn in the PNG
  title but are **not** written to the h5. Refit from the saved arrays if you need them.
- **PMOD pin 0.** Some programs fire a trigger on pin 0 around each qubit pulse
  (`trig_delay`, `trig_buffer_start/end`); others do not. Each page says which. The code
  does not say what pin 0 drives on the current setup; check
  [hardware.md](../hardware.md) before relying on it.
