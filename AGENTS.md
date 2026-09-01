# AGENTS.md

This file provides guidance to Codex when working with code in this repository. It is kept in sync with CLAUDE.md; edit both together.

## Overview

HouckLab_QICK is the Houck Lab's RFSoC control framework for superconducting qubit
experiments, built on the open-source QICK (Quantum Instruction Control Kit) running on
Xilinx RFSoC PYNQ boards. Per the README: "This is the repository for the Houck lab RFSOC code."

This branch (`bfg_code`) is deliberately **compact**: it carries exactly one code tree,
the BFG/BFC qubit-measurement workspace. There is no `MasterProject/`, no `Archive/`, and
no other `WorkingProjects/*` setup here. Older branches have those; this one does not, and
they should not be reintroduced.

## Repository Layout

The entire tracked source tree (~69 files) is:

```
HouckLab_QICK/
  WorkingProjects/QM_Team/qubit_measurements/Client_modules/
    Calib/initialize4Q.py       BaseConfig + FF_Qubits channel map (the config root)
    CoreLib/
      Experiment.py             ExperimentClass: output folders, HDF5/JSON/PNG saving
      socProxy.py               makeProxy() -> (soc, soccfg) over Pyro4
    Experiments/                measurement implementations (see below)
      soccfg_snapshots/         captured QickConfig JSON (bfg_zcu216.json) for offline work
    Helpers/                    analysis utilities (histograms, IQ rotation, shot buffers)
    PythonDrivers/              YOKOGS200, control_atten (Vaunix DLL), sc5510a_client
    Runners/                    entry points + the runs/ routine package
  docs/superpowers/
    specs/                      design docs (charge-parity zero-span, validation harness,
                                runner refactor)
    plans/                      the corresponding implementation plans
  .venv/                        Python 3.13 virtualenv (the live one)
```

There is no `setup.py`, no `requirements.txt`, no build step, no linter, and no test runner.

## Core Architecture

### Imports are absolute from the repo root

Every intra-project import is spelled out in full from the repository root, e.g.:

```python
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.socProxy import *
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Calib.initialize4Q import *
```

So scripts must be run with the **repo root on `sys.path`** (run from the repo root, or with
the root marked as a sources root in PyCharm). Keep this style in new files.

### Connection to hardware (Pyro4)

`CoreLib/socProxy.py::makeProxy()` connects to the Pyro4 nameserver at **`192.168.1.112:8888`**,
object name `myqick`, and returns `(soc, soccfg)`. Note the board's JupyterLab UI is a separate
service on port 9090 -- do not point Pyro4 at it. `makeProxy_RFSOC_10/_11/_12/_119()` are
variants for other boards on the subnet.

### Configuration model

`Calib/initialize4Q.py` defines `BaseConfig` (channel assignments, nyquist zones, ADC trigger
offset, trigger buffers) and `FF_Qubits` (fast-flux channel + per-qubit `delay_time`). Configs
are assembled by dict union, later keys winning:

```python
config = BaseConfig | UpdateConfig
```

Common keys: `res_ch`, `qubit_ch`, `ro_chs`, `nqz`, `qubit_nqz`, `reps`, `relax_delay`,
`length` (resonator tone duration), `readout_length` (ADC integration window),
`adc_trig_offset`, `pulse_freq`, `pulse_gain`, `qubit_freq`, `qubit_gain`, `sigma`,
`flattop_length`.

**`length` vs `readout_length` is load-bearing.** The resonator tone starts at t=0 but ADC
integration starts `adc_trig_offset` later, so the tone must span
`adc_trig_offset + readout_length`, not merely equal `readout_length`. `build_context()` and
`rebuild_singleshot_config()` both compute it that way; preserve this in new code.

### Experiment layer (two-class pattern)

Each experiment file pairs:

1. **A QICK program** subclassing `AveragerProgram` / `RAveragerProgram` / `NDAveragerProgram`,
   implementing `initialize()` (pulse setup, register declarations) and `body()` (gate sequence).
   This is compiled to tProc code and runs on the RFSoC.
2. **An `ExperimentClass` subclass** (`CoreLib/Experiment.py`) wrapping it for orchestration:
   sweep setup, `acquire()`, saving, and plotting. `__init__` creates a dated subfolder under
   `outerFolder + path` and prepares `.h5` / `.png` / `.json` names for the run.

### Runner architecture (context + runs package)

Runners were refactored out of one monolithic script; see
`docs/superpowers/specs/2026-07-02-cstq03-runner-refactor-design.md`.

- **Device runners** -- `Runners/CSTQ03_BFC.py`, `Runners/TATQ01-SiO2_BFG.py`. Each is
  client-facing: a device-parameter section, per-experiment param dicts, `RunX` boolean flags,
  then an `# 3. EXECUTE` section. You edit and run these top to bottom. They contain no
  measurement logic -- only `from ...Runners.runs import *` plus flag selection.
- **`Runners/runs/`** -- the measurement procedures, one module per family: `basic`,
  `calibration`, `coherence`, `charge_parity`, `singleshot`, `zero_span`, `verify`, and
  `context`. Every routine takes `(ctx, params)`.
- **`Runners/run_verify_only.py`** -- executes a runner's parameter section only (everything
  above the `# 3. EXECUTE` banner), then runs just the ModifiedRamsey verification. This exists
  because running a device runner to reach one flag also fires every other enabled flag.

#### `Context` and the persistent/transient config split

`runs/context.py::build_context()` connects to the RFSoC and yoko, assembles the config, derives
per-qubit scalars, and returns a `Context` dataclass. The split matters:

- `ctx.config` is the **persistent** instrument config. Only measured carry-overs --
  `pulse_freq` (found cavity frequency) and `res_phase` (calibrated readout phase) -- get
  written back to it.
- Transient per-experiment knobs (reps, spans, sigma, per-scan gains) go on a fresh copy from
  `ctx.working_config(params)` so they never leak into later measurements.

`rebuild_singleshot_config(ctx, SS_params)` deliberately switches `ctx.config` into the
single-shot regime partway through a run; everything after that call executes under the new
config. This reproduces the original script's ordering -- do not "clean it up" by moving it.

#### `NullYoko`

When there is no charge line (`use_yoko=False`), `ctx.yoko` is a `NullYoko` stub that answers
`:SOUR:LEV?` from a virtual level so experiments that never move the voltage run unchanged.
It **refuses** to fake a voltage change: charge-sweep / charge-dispersion / ModifiedRamsey
derive their physics from stepping the yoko, and silently pretending would yield
plausible-looking but meaningless data. Keep that refusal.

## Experiments directory

**QICK experiments (`m*.py`)** -- `mTransmissionFF`, `mSingleTone`, `mConstantTwoTone`,
`mSpecSliceFF`, `mChiShift`, `mAmplitudeRabiFF` (+ `_noUpdate`), `mT1FF`, `mT2R`, `mT2EFF`,
`mT1_SS`, `mAutoCoherence`, `mSingleShotProgramFFMUX`, `mUndrivenSingleShot`,
`mOptimizeReadoutandPulse_FF`, `mChargeDispersion`, `mChargeDispersionQuasiCW`,
`mModifiedRamsey`, `mActiveResetVerify`, `mZeroSpanParity`.

**Offline analysis / validation** -- `analyze_ZeroSpanParity.py`, `validate_ZeroSpanParity.py`,
`verify_ModifiedRamsey.py`, `verify_ModifiedRamsey_timing.py`. These run without hardware.

**Shared helpers** -- `utils.py` (includes `ramp_to()` for the yoko).

### Suffix conventions

- **FF** -- Fast Flux variant (adds a flux pulse channel for tuneable qubits)
- **MUX** -- Multiplexed readout (multiple resonators on one ADC channel)
- **SS** -- Single-Shot (returns IQ point clouds instead of averaged values)
- **PS** -- Post-Selection (heralded readout)

## TWPA scripts (handle with care)

`Experiments/twpa_*.py` are a five-script TWPA bring-up chain. They are **standalone
instrument scripts, not QICK experiments** -- they talk to a YOKO, a Windfreak SynthHD, and a
PNA-X, and they do not use `ExperimentClass`. Intended order:

1. `twpa_set_bias.py` -- ramp the DC bias YOKO to the operating point. Measurement-free.
2. `twpa_flux_sweep_pnax.py` -- sweep bias across the first flux period, read |S21| from the
   PNA-X (BAND or CW mode) to verify the bias path is alive.
3. `twpa_pump_sweep_pnax.py` -- 2-D pump (frequency, power) sweep, figure of merit = mean
   band |S21|. Reports transmission, not gain relative to an unpumped reference.
4. `twpa_set_pump.py` -- park the Windfreak pump at the chosen (freq, power). Measurement-free.
5. `twpa_gain_compare_pnax.py` -- final check: `gain(f) = |S21|_on - |S21|_off` across the band.

**Do not adjust the physics constants in these files.** They encode TWPA datasheet limits, and
violating them can trap flux in the device:

- Max bias sweep rate **300 nA/s**; exceeding it risks flux trapping.
- Nominal operating point **~11 uA** (~15 uT internal field, impedance matched).
- First flux period ends **~25 uA** -- calibration only, not normal operation.

Treat the rate limit, the operating point, and the sweep bounds as hardware safety limits, not
tunable defaults. Change them only when the user explicitly asks.

## Helpers and drivers

- `Helpers/hist_analysis.py`, `hist_analysis_opt.py` -- single-shot histogram fits / fidelity.
- `Helpers/rotate_SS_data.py`, `MixedShots_analysis.py` -- IQ rotation and mixed-state analysis.
- `Helpers/shot_buffers.py` -- **version-sensitive.** Up to qick ~0.2.28x, `prog.di_buf` /
  `dq_buf` held the raw per-repetition accumulated stream. From ~0.2.29x on (the BFG board runs
  **0.2.367**) `_process_accumulated` averages over reps first. This module restores real
  per-shot extraction; single-shot experiments must go through it rather than reading
  `di_buf` directly.
- `PythonDrivers/YOKOGS200.py` -- yoko voltage/current source over GPIB (pyvisa).
- `PythonDrivers/control_atten.py` -- Vaunix attenuators via `VNX_atten64.dll`. It calls
  `os.add_dll_directory(os.getcwd())` **itself**, at import time, so the DLL must be resolvable
  from the current working directory. Callers no longer register the DLL path; don't re-add
  that boilerplate, but do keep the CWD assumption in mind when launching scripts.
- `PythonDrivers/sc5510a_client.py` -- client for remote SignalCore SC5510A generators over
  Pyro (from the `sc5510a-py` repo). Needs `SC5510A_SERVER_HOST` set, or `host=...` passed, and
  the server PC running its nameserver + instrument server.

## Running an experiment

1. Activate `.venv` (Python 3.13).
2. Ensure the RFSoC Pyro4 nameserver is reachable at `192.168.1.112:8888`.
3. Open the device runner (`Runners/CSTQ03_BFC.py` or `Runners/TATQ01-SiO2_BFG.py`).
4. Edit the device-parameter block and the per-experiment params; set the `RunX` flags.
5. Run it from the repo root so the absolute imports resolve.

Data goes to the per-qubit `outerFolder` (a network path such as
`V:/t1Team/Data/<cooldown>/<device>/RFSOC/Q<n>/`), one
`<Experiment>/<Experiment>_<date>/` subfolder per run.

There is no automated test framework. `verify_*.py` and `validate_*.py` are the closest thing:
run them directly, and note that some are hardware-free while others need the board.

## Conventions to preserve

- **Don't compute frequency-to-register values by hand.** Use the QICK helpers (`freq2reg`,
  `us2cycles`, `deg2reg`) so values round-trip correctly with the firmware.
- **Gaussian envelope length must be >= 4x sigma** -- `add_gauss(..., length=us2cycles(sigma)*4)`
  throughout.
- **Keep the resonator tone >= `adc_trig_offset + readout_length`** (see above).
- **Keep runners declarative.** Measurement logic belongs in `runs/`; device runners should stay
  parameters + flags.
- **Don't reintroduce `MasterProject/`, `Archive/`, or other `WorkingProjects/*` trees.** This
  branch is intentionally single-tree. Stale checkouts of those directories are cruft; the
  `.gitignore` is written to keep caches and virtualenvs from re-accumulating.
- **Don't loosen the TWPA safety constants** (see the TWPA section).

## Current user scope

Work happens in `WorkingProjects/QM_Team/qubit_measurements/Client_modules/`. Active devices:
**CSTQ03** (BFC cooldown, `CSTQ03_BFC.py`) and **TATQ01-SiO2** (BFG 2026-06-27 recooldown,
`TATQ01-SiO2_BFG.py`). Coherence times (T1/T2/T2E) are measured on every new device as the
standard benchmark before running specialized measurements.

Edit files inside `Client_modules/` freely. Ask before touching anything outside it.

## Active work

Zero-span two-tone charge-parity switching (`mZeroSpanParity.py` + `analyze_ZeroSpanParity.py`,
wired into the runners via `runs/zero_span.py`). Canonical reference:
`docs/superpowers/specs/2026-05-16-bfc-charge-parity-zero-span-design.md`. Physics validation is
gated on device cooldown + characterization.

ModifiedRamsey / active-reset timing: `tau` is programmed **centre-to-centre**, not as the
pulse-edge gap, and the active-reset compare offset is readout-scaled. See
`verify_ModifiedRamsey_timing.py` and commits `225b9c0` / `fb020f9`.
