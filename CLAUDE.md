# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

HouckLab_QICK is the Houck Lab's RFSoC control framework for superconducting qubit experiments. It is built on top of the open-source QICK (Quantum Instruction Control Kit), which runs on Xilinx RFSoC PYNQ boards. Per the README: "This is the repository for the Houck lab RFSOC code."

## Repository Layout

```
HouckLab_QICK/
├── MasterProject/Client_modules/     # THE central shared library — everything imports from here
│   ├── CoreLib/                      # ExperimentClass, MakeFile (h5py wrapper), socProxy
│   ├── Init/initialize.py            # Template: BaseConfig + attenuator/yoko setup
│   ├── PythonDrivers/                # YOKOGS200, control_atten (DLL), SPIRack drivers
│   ├── Helpers/                      # Shared analysis utilities
│   ├── Experiments/                  # Shared experiment implementations
│   ├── Runners/                      # Top-level scripts (RunRabiAmp_ND, RunSpecSlice)
│   └── LAKE_GUI/                     # PyQt5 GUI for live experiment control
├── WorkingProjects/                  # Per-hardware-setup workspaces
│   ├── QM_Team/qubit_measurements/   # General qubit characterization (+ JeroCode subworkspace)
│   ├── Inductive_Coupler/            # Inductive coupler experiments (MUX variants)
│   ├── Tantalum_fluxonium/           # Tantalum fluxonium qubits
│   ├── Tantalum_fluxonium_escher/    # Escher chip
│   ├── Tantalum_fluxonium_marvin/    # Marvin chip
│   └── Switch_SetupTesting/          # RF switch testing
├── Archive/                          # Legacy projects (Basil, Protomon, q4diamond)
└── README                            # One-line repo description
```

Each WorkingProject mirrors the MasterProject layout (Client_modules with CoreLib/Experiments/Helpers/PythonDrivers) but contains setup-specific code. Newer projects increasingly import from MasterProject rather than duplicating.

## Core Architecture

### Connection to Hardware (Pyro4 over network)

`MasterProject/Client_modules/CoreLib/socProxy.py` defines `makeProxy()`, which connects to a QICK server running on a Pyro4 nameserver. Default endpoint is `192.168.1.7:8888`, server name `myqick`. Returns `(soc, soccfg)` — the QickSoc proxy and config used throughout experiments.

### Experiment Layer (two-class pattern)

Every experiment has two cooperating classes:

1. **A QICK Program** subclassing `RAveragerProgram` / `AveragerProgram` / `NDAveragerProgram` from `qick`. Implements `initialize()` (pulse setup, register declarations) and `body()` (gate sequence). Generated code runs on the RFSoC tProc.

2. **An ExperimentClass subclass** (from `MasterProject/Client_modules/CoreLib/Experiment.py`) wrapping the QICK program for orchestration: configuring sweeps, calling `acquire()`, saving HDF5/JSON/PNG to timestamped paths, and plotting.

`ExperimentClass.__init__` auto-creates a dated subfolder under `outerFolder + path` and prepares three filenames per run: `.h5` (data), `.png` (plot), `.json` (config).

### Configuration (cfg dict)

All measurement parameters flow through a single `cfg` dict. Hardware-level defaults live in `MasterProject/Client_modules/Init/initialize.py` as `BaseConfig` (channel assignments, ADC offsets, nyquist zones). Runners build on `BaseConfig` with experiment-specific `UpdateConfig` overrides.

Common keys: `res_ch`, `qubit_ch`, `ro_chs`, `nqz`, `qubit_nqz`, `reps`, `relax_delay`, `read_length`, `read_pulse_freq`, `read_pulse_gain`, `qubit_freq`, `sigma`, `flat_top_length`, `adc_trig_offset`.

### Runners (top-level entry points)

`MasterProject/Client_modules/Runners/Run*.py` are the actual scripts a user executes. Each Runner:
1. Sets `outerFolder` (often a network path like `Z:\TantalumFluxonium\Data\...`)
2. Calls `makeProxy()` once to grab `soc, soccfg`
3. Instantiates instruments (YOKOGS200 over GPIB, attenuators over USB DLL)
4. Defines an `UpdateConfig` dict and merges into `BaseConfig`
5. Instantiates and runs experiment classes, often in loops

### LAKE_GUI (interactive frontend)

`MasterProject/Client_modules/LAKE_GUI/LAKE_GUI.py` is a PyQt5 app that wraps experiments for interactive use. `ExperimentThread` runs measurements off the UI thread; `PlotWidget` and `QDictEdit` handle live plots and parameter editing. There is also a `Quarky_GUI` (separate, in MasterProject) — distinct from LAKE_GUI.

### Hardware Driver Quirks

`PythonDrivers/control_atten.py` loads `VNX_atten64.dll` (Vaunix variable attenuators). Calling code must register the DLL directory before import:

```python
os.add_dll_directory(os.path.dirname(path) + '\\PythonDrivers')
```

This pattern appears at the top of nearly every Runner and the LAKE_GUI entry point. If you write a new top-level script, replicate it.

## Common Experiment Families

Files follow a `m<Name>.py` naming convention. Recurring families:
- **Transmission** (`mTransmission`, `mTransmissionFF`, `mTransVsGain`, `mTransmissionFFMUX`): Resonator/readout characterization
- **Spectroscopy** (`mSpecSlice`, `mSpecSliceFF`, `mSpecVsFlux`, `mSpecSliceFFMUX`): Qubit frequency hunting
- **Rabi** (`mAmplitudeRabi`, `mAmplitudeRabiFF`, `mAmplitudeRabi_Blob`, `mRabiOscillations*`): Drive amplitude calibration
- **Coherence** (`mT1`, `mT2Experiment`, `mT2EchoExperiment`, `mT1MUX`): T1/T2/Echo decay times
- **Single-Shot** (`mSingleShotProgram`, `mSingleShot_2Dsweep`, `mSingleShotPS`): Readout discrimination
- **Optimization** (`mReadOpt_wSingleShot`, `mOptimizeReadoutandPulse_FFMUX`): Joint readout/pulse tuning
- **Benchmarking** (`mRB`, `mSingleQubitRB`): Randomized benchmarking
- **Stark** (`mACStarkShift`): AC Stark calibration
- **Auto** (`mAutoCoherence`): Automated T1/T2 collection loop

### Suffix conventions
- **FF** = Fast Flux variant (adds a flux pulse channel for tuneable qubits)
- **MUX** = Multiplexed readout (multiple resonators on one ADC channel)
- **SS** = Single-Shot (returns IQ point clouds instead of averaged values)
- **_HigherLevels** = Drives `|2⟩` or `|3⟩` (qutrit/ququart experiments)
- **PS** = Post-Selection (heralded readout)

## Development Notes

### Python environment

The project has no `setup.py` or `requirements.txt` at the repo root in the `bfc_code` branch. The interpreter is `.venv\` (Python virtual environment, Windows). Key packages: `qick`, `numpy`, `scipy`, `matplotlib`, `h5py`, `pandas`, `tqdm`, `PyQt5`, `Pyro4`, `pyvisa`. The `.venv\Lib\site-packages\qick\` directory contains the installed QICK library.

### Running an experiment

There is no build step, lint config, or test command. A measurement run is:

1. Activate `.venv`
2. Ensure the RFSoC server is reachable at `192.168.1.7` (the Pyro4 nameserver)
3. Edit or copy a Runner script under `MasterProject/Client_modules/Runners/` (or a project-local equivalent)
4. Update `outerFolder` to the data destination and `UpdateConfig` to the measurement parameters
5. Execute the script directly (`python Runners/RunRabiAmp_ND.py`) or run via LAKE_GUI

There is no automated test framework — `TestExperiment.py` files contain manually-run smoke checks against actual hardware.

### Conventions to preserve

- **Don't compute frequency-to-register values manually.** Use QICK helpers (`freq2reg`, `us2cycles`, `deg2reg`) so values round-trip correctly with the firmware.
- **Pulse envelope length must be ≥ 4× sigma** for Gaussian pulses — this is hardcoded into `add_gauss(..., length=us2cycles(sigma)*4)` throughout the experiments.
- **Don't refactor across `WorkingProjects/*/`.** Each project workspace is owned by one researcher / setup and may have drifted intentionally from MasterProject. When in doubt, ask before pushing shared changes upward.
- **Don't edit `Archive/`.** Treated as historical record.
- **DLL path setup is load-bearing.** Removing the `os.add_dll_directory` lines breaks attenuator control silently.

### Branch context

- Main branch: `main`
- Active branch (per current checkout): `bfc_code` — BFC (Broadband Flux Control) experiment development. Recent commits add `mRB.py`, `mACStarkShift.py`, and extend `mAmplitudeRabiFF.py`, `mTransmissionFF.py`, `LFTM01_BFC.py`, `CSTQ02_BFC.py`, and `utils.py`.
- Branch names typically encode the chip/setup or measurement target (e.g., `QM_Team`, `bfc_code`).

### Current user scope (IMPORTANT)

The user is working **exclusively on BFC code** inside `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/`. Their previous measurements ran out of `CSTQ02_BFC.py` in that directory, which orchestrates all involved measurements for that chip. Next devices in pipeline: **test_BTQ_BFC** (test device, first target, being prepared) → **CSTQ03** (production target). New per-device orchestrators (e.g. `test_BTQ_BFC.py`) follow the existing `CSTQ02_BFC.py` pattern.

**Edit scope rule:** Edit files only inside `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/` (and helper files at the same level the user opens) without asking. **Ask before editing anything upward** of this directory — including `MasterProject/`, `CoreLib/`, sibling `WorkingProjects/`, or shared helpers — even if a change there would be cleaner. Those files are shared across setups and researchers and may not be safe to modify without coordination.

### Active spec

Zero-span two-tone charge-parity-switching measurement, designed 2026-05-16. Canonical reference: `docs/superpowers/specs/2026-05-16-bfc-charge-parity-zero-span-design.md`. Designs v1 (rep-based "strobe", ~10–30 μs/sample, unbounded record) and v2 (`acquire_decimated()`, sub-μs/sample). New files: device-agnostic `mZeroSpanParity.py` + `analyze_ZeroSpanParity.py`, per-device orchestrator `test_BTQ_BFC.py`. Implementation can proceed up to §6.2 (RFSoC loopback) without hardware; §6.3 physics validation is blocked on test_BTQ_BFC cooldown + characterization. Coherence times (T1/T2/T2E) are measured on every new device as a standard benchmark before running specialized measurements.

### Gitignored areas

`/__pycache__/`, `*.iml`, `*.pyc`, `/.idea/`, and several `WorkingProjects/QM_Team/resonator_measurements/` subdirectories (FPGA build artifacts: `bd/`, `ip/`, `xdc/`, `pynq/`, `hdl/`, `proj.tcl`, `dBm_lookup`).
