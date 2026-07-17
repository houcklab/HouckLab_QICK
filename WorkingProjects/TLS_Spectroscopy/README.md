# TLS Spectroscopy (QICK port of the QUA `TLSSpectroscopy.py` pipeline)

A self-contained QICK/RFSoC implementation of the De Leon–Houck lab's QUA (Quantum
Machines OPX) TLS-spectroscopy workflow
(`Houck-Lab-Qua/LabCode/Control/Flux_Tunable/TLSSpectroscopy.py`), configured for
**FTTv02_SiOxJJ qubit 4** (ZCU216 board, nameserver `192.168.1.107`) in the
**all-fast-flux workflow**: every flux operation — park, sweep, step — is the
`ff_ch` DAC (generator 3 → DAC `3_230` P/N pigtails); no Yokogawa is required
(matching the QUA original, which also left its Yoko untouched).

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
- **One flux line, all-DAC (QUA-style).** QUA drove one OPX baseband line for both
  the DC offset and fast pulses. Here the `ff_ch` DAC on the DC-coupled P/N pigtails
  plays the same role: the static park is `ff_park_gain` (held between pulses via
  `stdysel='last'`, analogous to QUA's `flux_dc_offset`), and steps/holds are shaped
  pulses on top of it. Steps 1–2 (Yoko-swept DC scans) are kept only as optional
  extras — readout always happens at park, so no resonator-tracking lookup is needed.
- **Flux target axis.** QUA's steps 4 & 6 swept the flux *target voltage* (`dc_vec`).
  Here the swept axis is **`ff_gain` (DAC units)**, and `FLUX_FIT_PARAMS` is fit with
  that axis (period/offset in DAC units) by step 4, which also gives the f_q(ff_gain)
  frequency axis step 6 uses to plot T₁ vs qubit frequency. The runner keeps the
  QUA step order **1 → 2 → 3a → 3b → 4 → 5 → 6** with the QUA constants, param
  dicts, defaults, and printouts: step 1 = resonator spec vs flux (cosine fit is
  the default readout-IF source, `USE_RESONATOR_LOOKUP=False`), step 2 = full-range
  qubit spec that prints paste-ready `FLUX_FIT_PARAMS`, step 4 runs FIT OFF, and
  `FLUX_TAIL_COMPENSATION_GAIN` is applied at load time from `undamped_multipliers`
  exactly like QUA's `_scale_gain`.
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

1. **Device constants** in `Calib/initialize.py` are filled from the working q4 setup
   (readout 7248.95 MHz @ 4300, qubit 2557.25/π 2557.37 @ 12850, σ=0.125 µs,
   read 20 µs, `adc_trig_offset` 0.5 µs, `ff_ch=3`). Still to establish on hardware:
   `FLUX_FIT_PARAMS` (run step 4), `FF_STEP_TARGET_GAIN` (pick from step 4's map),
   the ff-line `delay_time`, and optionally a nonzero `ff_park_gain`.
2. **FF pulse timing** (steps 3/4/6): `dt_pulseplay`, `ff_ramp_length`,
   `pre_meas_delay`, and that the qubit probe / decay actually overlaps the held flux
   (the code relies on `stdysel='last'` holding the DAC between hold pulses — the same
   idiom escher uses). Sanity-check with a loopback/`FFRampTest` before trusting T₁.
3. **`ff_gain` range** — pick from a spec-vs-ff_gain scan (step 4 is that scan); the
   `ff_gain → flux → frequency` mapping is device-specific.
4. **Long holds** — the staircase (not an arb envelope) removes the ~9.5 µs envelope
   memory limit, but each staircase segment costs tProc instructions and this board's
   **program memory is 8192 words**. Rule of thumb: segments ≈ hold / `dt_pulseplay`,
   ~3 words each; the runner defaults `dt_pulseplay=5 µs` for the T₁ steps (300 µs
   hold → ~60 segments) and 1 µs for the step response. Raise `dt_pulseplay` if a
   long-hold program fails to load.

## Status

Every file compiles; the pure-numpy analysis helpers pass a synthetic unit-test suite
(T₁/spec/resonator/Ramsey/transmon fits, the predistortion solver flattening a
slow-settling plant, JSON round-trips). The QICK `Program` classes require the `qick`
package + the live board to run (lab PC), which was not available here.
