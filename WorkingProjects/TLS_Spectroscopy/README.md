# TLS Spectroscopy (QICK port of the QUA `TLSSpectroscopy.py` pipeline)

A self-contained QICK/RFSoC implementation of the De Leon–Houck lab's QUA (Quantum
Machines OPX) TLS-spectroscopy workflow
(`Houck-Lab-Qua/LabCode/Control/Flux_Tunable/TLSSpectroscopy.py`), targeting the
**FTTv02_SiOxJJ** flux-tunable transmon (same board as the QICK `BFF_ACStark`
branch, nameserver `192.168.1.125`).

**What it measures.** A two-level-system (TLS) defect sits at a fixed frequency.
When the flux-tuned qubit is swept through a TLS resonance, energy swaps into the
defect and the qubit **T₁ dips**. Mapping T₁ (or 1/T₁) vs qubit frequency reveals
TLS defects as sharp dips (peaks in 1/T₁). Steps 1–5 are the calibration required
to do that map cleanly at fast-flux-pulsed operating points; step 6 is the map.

## The six steps

| # | File (`Client_modules/Experiments/…`) | QUA source | Measures |
|---|---|---|---|
| 1 | `mTransmissionVsFlux.py` | `m_transmission_vs_flux.py` | resonator dip vs DC flux → **resonator lookup CSV** |
| 2 | `mQubitSpecVsFlux.py` | `m_qubit_spec_vs_flux_full_range.py` | qubit f₀₁ vs DC flux → **`FLUX_FIT_PARAMS`** (transmon arc) |
| 3 | `mQubitFluxStepResponse.py` | `m_qubit_step_response.py` + `flux_predistortion.py` | flux step response → **predistortion JSON** (fit), then verify flat (correct) |
| 4 | `mQubitLongTimeSpecVsFlux.py` | `m_qubit_long_time_frequency_vs_flux.py` | f_q vs fast-flux target at long delays → settling check + **f_q(ff_gain) map** |
| 5 | `mSingleShot1Q.py` | `m_single_shot_1Q.py` | readout fidelity → **`calib_params`** (threshold, θ) |
| 6 | `mT1VsFlux.py` | `m_swap_spec_vs_flux.py` | **T₁ / 1/T₁ vs flux → the TLS map** (`T1FullCurveVsFlux`, `T13PointVsFlux`) |

Orchestrator: `Client_modules/Runners/TLSSpectroscopy.py` (mirrors the QUA one:
`P1..P6` param dicts, `run_*` step functions, artifact threading, `run` gating).

Run from the repo root:
```
python -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSpectroscopy
```

## The key QUA → QICK translations

- **No external LO / IQ mixer.** QUA used an E8257D analog LO + IQ mixer + digital IF,
  so `f_physical = LO_freq + IF`. QICK synthesizes the whole tone digitally, so every
  `*_freq` in `Calib/initialize.py` is an **absolute MHz** and the Nyquist zone
  (`nqz`/`qubit_nqz`) places it. Mixer-imbalance/LO-power calibration is dropped.
- **Two flux mechanisms, split.** QUA drove one OPX baseband line for *both* the DC
  offset and fast pulses. QICK splits them: **static/DC flux = Yokogawa GS200**
  (`SetVoltage`, swept in a Python loop for steps 1–2), **fast/dynamic flux = a
  dedicated DAC channel `ff_ch`** playing a shaped pulse (steps 3, 4, 6).
- **Flux target axis.** QUA's steps 4 & 6 swept the flux *target voltage* (`dc_vec`).
  QICK reaches a dynamic operating point with a fast-flux DAC pulse, so the swept axis
  is **`ff_gain` (DAC units)**. Step 4 measures f_q(ff_gain), giving the frequency
  axis that step 6 uses to plot T₁ vs qubit frequency.
- **Predistortion.** QUA played a real-time `set_dc_offset` staircase of
  per-segment *multipliers*. QICK has no in-program DC primitive, so the same
  multipliers are **baked into the fast-flux `idata` waveform** (a piecewise-constant
  staircase streamed via `safe_regwi` on the ff gain register, exactly like escher's
  `mFFRampHoldTest`). The solver math (`Helpers/flux_predistortion.py`:
  `rise_decay_bump` fit + `calculate_piecewise_dc_correction`) is a faithful,
  unit-tested port. An escher IIR predistortion (`PulseFunctions.Simple*TailDistortion`)
  is also supported via `cfg['predist_taps']`.
- **Readout rotation.** QUA baked `read_theta` into hardware integration weights;
  QICK rotates in Python (`Helpers/hist_analysis.hist_process`).

## Reused lab code (copied verbatim from `Tantalum_fluxonium_escher`)

`Helpers/PulseFunctions.py` (predistortion engine + `create_ff_ramp`),
`hist_analysis.py` (single-shot fidelity), `Shot_Analysis/`, `GammaFit.py`,
`SingleShot_ErrorCalc_2.py`, `MixedShots_analysis.py`, `PythonDrivers/YOKOGS200.py`.

New pure-numpy analysis (unit-tested locally, no hardware): `Helpers/fit_functions.py`,
`Helpers/flux_fit.py`, `Helpers/flux_predistortion.py`, and the FF playback helper
`Helpers/ff_pulse.py`.

## Before you run on hardware — validate these

This code is **tProc v1** and follows the proven escher FF stack, but the intricate
fast-flux timing must be checked on your board (I could not run against hardware):

1. **`# DEVICE` constants** in `Calib/initialize.py` — `read_pulse_freq`, `qubit_freq`,
   gains, `adc_trig_offset`, `read_length`, `ff_ch`, `BASELINE/TARGET_DC_OFFSET`,
   `YOKO_VISA`, `outerFolder`. Steps 1, 2, 5 exist precisely to find several of these.
2. **FF pulse timing** (steps 3/4/6): `dt_pulseplay`, `ff_ramp_length`,
   `pre_meas_delay`, and that the qubit probe / decay actually overlaps the held flux
   (the code relies on `stdysel='last'` holding the DAC between hold pulses — the same
   idiom escher uses). Sanity-check with a loopback/`FFRampTest` before trusting T₁.
3. **`ff_gain` range** — pick from a spec-vs-ff_gain scan (step 4 is that scan); the
   `ff_gain → flux → frequency` mapping is device-specific.
4. **Long holds** — the staircase (not an arb envelope) removes the ~9.5 µs memory
   limit, but very long T₁ waits × many segments cost tProc instructions; tune
   `dt_pulseplay` up for long holds.

## Status

Every file compiles; the pure-numpy analysis helpers pass a synthetic unit-test suite
(T₁/spec/resonator/Ramsey/transmon fits, the predistortion solver flattening a
slow-settling plant, JSON round-trips). The QICK `Program` classes require the `qick`
package + the live board to run (lab PC), which was not available here.
