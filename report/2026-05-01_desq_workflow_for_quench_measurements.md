# Desq workflow for the triangle-ladder quench measurements

Date: 2026-05-01

Companion to `report/2026-04-29_quench_experiment_implementation_plan.md`. That document spelled out *what* to run; this one is the operator's how-to for *how* to run it via the Desq GUI. Authored by the project's `quantum-measurement-engineer`, after reading `MasterProject/Client_modules/Desq_GUI/sphinx/source/desq_basics.rst`, the Desq core code (`CoreLib/Experiment.py`, `scripts/ExperimentLoader.py`, `AccountsPanel`, `VoltagePanel`), and the existing experiment classes under `WorkingProjects/triangle_lattice_quench/`.

Treat this as a cold-start checklist. Audience is a competent qubit experimentalist who has not opened Desq before.

## 1. Launching Desq

Prerequisites: project `.venv` activated and the GUI dependencies installed.

```
.venv\Scripts\python.exe -m pip install -r MasterProject/Client_modules/Desq_GUI/requirements.txt
```

Entry point — from the repository root (`HouckLab_QICK/`):

```
.venv\Scripts\python.exe -m MasterProject.Client_modules.Desq_GUI.Desq
```

Run from the repo root, not from inside `Desq_GUI/`. The module path must resolve from the root so that `WorkingProjects.*` imports work when an experiment is loaded.

The main window opens with a toolbar at the top, a tab bar, a side panel containing Voltage / Accounts / Log tabs, a directory tree on the left, and a log panel at the bottom. The toolbar Run button is greyed out until an account is connected.

## 2. Set the D5a coupler baseline before opening Desq

The D5a (Qblox SPI rack) coupler bias on DACs 9..14 (legs C1..C6) must be at the calibrated baseline before any experiment that involves coupling. Desq's Voltage tab supports manual single-channel entry only and has no JSON-import. Run the baseline script in a separate Python console first:

```
.venv\Scripts\python.exe WorkingProjects/triangle_lattice_quench/Flux_Files/QbloxVoltageSet_8QTriangleLattice_Dictionary.py
```

That script sets all 14 D5a DACs (qubits 1..8 on DACs 1..8, couplers C1..C6 on DACs 9..14) using `D5aModule.set_voltage_ramp(...)`. Use the Voltage tab in Desq for fine trims only; never rely on it for the full coupler baseline reset.

## 3. Connect to the RFSoC (Accounts tab)

1. Click the Accounts tab in the side panel.
2. Add Account (or pick an existing one). Fields:
   - Account name: human label, e.g. `houcklab`.
   - IP address: the Pyro4 nameserver host, e.g. `192.168.1.114`.
   - Workspace: absolute path to the data root, e.g. `Z:\QSimMeasurements\Measurements\8QV1_Triangle_Lattice`.
3. Save. The JSON is written to `MasterProject/Client_modules/Desq_GUI/LocalStorage/accounts/<name>.json`.
4. Connect. Desq calls `Pyro4.locateNS(host, port=8888)`, fetches the registered RFSoC proxy (typically `myqick`), and constructs `QickConfig`. On success a checkmark appears next to the account name and the toolbar Run button activates.

The workspace path from step 2c is injected as the experiment's `outerFolder` attribute at run time. All `.h5` and `.png` outputs land beneath this folder.

If connection fails after ~4 s a timeout dialog appears. Verify the nameserver is running and the host/port match the running RFSoC.

## 4. Load an experiment

Two options:

- Toolbar Load Exp -> file picker.
- Double-click a `.py` file in the directory tree.

Under the hood (`scripts/ExperimentLoader.py`):

1. `load_module()` imports the file with the `socProxy` import-time blocking. This stops modules that do `from ... socProxy import makeProxy` from connecting to the device just by being imported. A 4-second timeout guards against slow imports.
2. `find_experiment_classes()` scans the imported module for any class whose MRO contains a class named `ExperimentClass`. Each match yields a new `QDesqTab`.
3. The tab extracts default config from each class's `config_template` attribute if defined.

For the quench project, the following files each yield Desq tabs:

| File | Discovered classes |
|---|---|
| `WorkingProjects/triangle_lattice_quench/Experimental_Scripts/quench_experiments/mQuenchExperiment.py` | `RampQuenchDynamics`, `RampQuenchFreq`, `RampQuenchSweepRampTime`, `RampQuenchSweepQuenchTime`, `RampQuenchRabi` |
| `WorkingProjects/triangle_lattice_quench/Experimental_Scripts/mGainSweepQubitOscillationsR.py` | `GainSweepOscillationsR` (chevron) |
| `WorkingProjects/triangle_lattice_quench/Experimental_Scripts/mRampCurrentCalibrationR_SSMUX.py` | `RampBeamsplitterGainR`, `RampBeamsplitterOffsetR` |
| `WorkingProjects/triangle_lattice_quench/Experimental_Scripts/Characterization_Sweeps/mSpecVsQblox.py` | `SpecVsQblox` |
| `Basic_Experiments/mTransmissionFFMUX.py`, `mSpecSliceFFMUX.py`, `mAmplitudeRabiFFMUX.py`, `mT1MUX.py`, `mT2EMUX.py`, `mT2RMUX.py`, `mSingleShotProgramFFMUX.py` | one per file (single-qubit cascade) |

The runner scripts under `Run_Experiments/calibration_scripts/` (`coupling_strength_calibration.py`, `beamsplitter_calibration.py`) are iteration wrappers around the chevron and beam-splitter classes. They contain no `ExperimentClass` subclass and **cannot be loaded via Load Exp**. Treat them as parameter-reference documents and bond-iteration recipes; in Desq you load `GainSweepOscillationsR` or `RampBeamsplitterGainR` and run it once per pair, replicating what the runner script's loop does.

## 5. Build the configuration

Each tab has two JSON-tree config panels:

- Global Config: shared across tabs in this session.
- Experiment Config: tab-local; wins on key conflict.

At run time Desq merges Global first, then Experiment overrides on top. There is no `config_template` defined on the quench classes, so configs must be loaded explicitly.

### Preferred workflow

1. Open `WorkingProjects/triangle_lattice_quench/Run_Experiments/qubit_parameter_files/Qubit_Parameters_Master.py` in a text editor and copy its contents.
2. In the Desq tab click Config Code Extraction. Paste the file contents into the sandboxed editor. Hardware imports are blocked in the sandbox. Click Extract to Global to populate Global Config with every dict variable defined in the file (`Qubit_Parameters`, `FF_Qubits`, `Init_FF`, `BaseConfig`, etc.).
3. Add the experiment-specific keys in Experiment Config. Authoritative key list per class lives in that class's `init_sweep_vars()`:
   - `RampQuenchDynamics`: `samples_start`, `samples_end`, `samples_num_points`.
   - `RampQuenchSweepRampTime`, `RampQuenchSweepQuenchTime`: same `samples_*` triple, swept against the corresponding `expt_samples_*` key.
   - `RampQuenchFreq`: `freq_start`, `freq_end`, `freq_num_points`.
   - `RampQuenchRabi`: `gain_start`, `gain_end`, `gain_num_points`.
   - `GainSweepOscillationsR`: `gainStart`, `gainStop`, `gainNumPoints`, `expts`, `start`, `step`, `qubit_FF_index`, `Qubit_Readout`, `Qubit_Pulse`.
   - `RampBeamsplitterGainR`: `gainStart`, `gainStop`, `gainNumPoints`, `swept_qubit`, `ramp_time`, `t_offset`.
4. Set `sets` (number of full repetitions); Desq uses 1 by default.

JSON files can also be loaded directly into either panel via Load JSON to replay a prior run.

## 6. Run

1. Verify configs.
2. Click Run. Desq merges Global + Experiment, allocates the experiment via `object.__new__()`, sets `outerFolder = workspace`, then calls `__init__(soc, soccfg, cfg)`. An `ExperimentThread` worker invokes `acquire()` once per set.
3. The toolbar progress bar tracks sets completed. Live `intermediateData` signals from inside `acquire()` update plots in flight.
4. Stop controls:
   - Stop / Safe Stop: sets a flag the inner sweep loop checks at natural breakpoints. Use first.
   - Force Stop: injects `ExperimentInterrupted` into the worker thread via `ctypes`. Bypasses cleanup; the last set's data file may be incomplete. Use only if the experiment is hung.
5. Plot backend: PyQtGraph by default for live update; toggle to Matplotlib per-tab when you need the full matplotlib toolchain (e.g., custom annotations from `display()`). The Figure Carousel at the tab bottom holds thumbnails when an experiment produces multiple figures; auto-hides for single-figure cases.

## 7. Per-experiment recipes

### 7.1 Single-qubit health
Load each FFMUX experiment in turn (`mTransmissionFFMUX`, `mSpecSliceFFMUX`, `mAmplitudeRabiFFMUX`, `mSingleShotProgramFFMUX`, `mT1MUX`, `mT2RMUX`, `mT2EMUX`). For each, set `Qubit_Readout` and `Qubit_Pulse` to the qubit under test, then Run. Repeat across all 8 qubits. The output `Qubit_Parameters` dict (saved per run) feeds every downstream calibration.

### 7.2 Coupler bias (legs)
Load `mSpecVsQblox.py:SpecVsQblox`. Set `Qblox_start`, `Qblox_stop`, `Qblox_steps`, `DAC` (one of 9..14 corresponding to C1..C6). `set_up_instance()` drives the D5a directly through `self.QbloxClass.set_voltage(...)` per sweep point; the D5a must be physically connected. Run per coupler and pick the operating points for `chi = 0` (positive `Jtilde_||`) and `chi = pi` (negative `Jtilde_||`) at the target ratio.

### 7.3 Two-qubit chevrons
Load `mGainSweepQubitOscillationsR.py:GainSweepOscillationsR`. Configure for one bond pair and Run. Inspect the fitted coupling rate `g` (MHz) on the plot legend. Repeat per bond. The full-bond set is `rungs = ['12','23','34','45','56','67','78']` (7 NN bonds, fixed `J/(2pi) = 6.1 MHz`) and `legs = ['13','24','35','46','57','68']` (6 NNN bonds, tunable). The runner `coupling_strength_calibration.py` is the reference for the per-bond config keys.

### 7.4 Beam-splitter calibration (rung)
Load `mRampCurrentCalibrationR_SSMUX.py`. Run `RampBeamsplitterGainR` for amplitude calibration first; then `RampBeamsplitterOffsetR` for time-offset calibration. Per rung. The 50:50 (sqrt(iSWAP)) operating point sits at `t_BS = pi / (4 J)` in the BS Hamiltonian; the calibration finds the FF gain and timing offset that reproduce this in hardware.

### 7.5 Quench dynamics
Load `mQuenchExperiment.py`. Choose:
- `RampQuenchDynamics` to sweep dynamics evolution time.
- `RampQuenchSweepRampTime` to sweep the ramp duration.
- `RampQuenchSweepQuenchTime` to sweep the quench-pulse duration.
- `RampQuenchFreq` to sweep the qubit-drive frequency during the quench step.
- `RampQuenchRabi` to sweep the quench-pulse amplitude (pi vs pi/2 calibration).

Config Code Extraction from `Qubit_Parameters_Master.py` populates the Global Config. Add the relevant `samples_*`, `freq_*`, or `gain_*` triple in Experiment Config. Run.

## 8. Data outputs

After each set Desq writes three files under the workspace:

```
<workspace>/<experiment_path>/<experiment_path>_YYYY_MM_DD/<experiment_path>_YYYY_MM_DD_HH_MM_SS_data.h5
                                                          ..._data.json
                                                          ..._data.png
```

`<experiment_path>` is the experiment class name (or the `path` argument constructor-injected). The JSON holds the merged config dict. The H5 holds raw averaged IQ, sweep arrays, and any fit products that `acquire()` placed in the returned data dict. Single-shot per-shot IQ is only saved when the experiment explicitly includes it.

To re-load: toolbar Load Data, pick the `.h5`. The tab enters dataset mode (no Run; analysis and re-display only).

## 9. Re-plotting and exporting

- RePlot: re-runs `display()` on the last acquired data without re-acquiring. Use after toggling backends or editing display-only config keys.
- Snip: clipboard PNG of the current plot.
- Export: file dialog; saves the current data to a chosen path as the same three-file bundle.
- Sync: forces config panels to re-read from disk if you edited the JSON externally.

## 10. Common failure modes

| Symptom | Cause | Recovery |
|---|---|---|
| Import timeout dialog on Load Exp | Slow import chain or a module-level call that survived the `socProxy` block | Inspect terminal; remove module-level hardware calls |
| `AttributeError: 'NoneType' object has no attribute 'reset_gens'` | Module-level `soc` imported from `MUXInitialize` is `None` under Desq's import-time blocking; some legacy experiment files (e.g. `Triangle_Lattice_tProcV2/Experimental_Scripts/mGainSweepQubitOscillationsR.py`) call `soc.reset_gens()` in `set_up_instance()` | Replace the module-level `soc` import with `self.soc.reset_gens()` inside the method, or run that experiment via the runner script (`coupling_strength_calibration.py`) instead. See section 11. |
| Run button stays grey | RFSoC not connected | Reconnect via Accounts tab |
| No plot after acquire | Stale figure or backend mismatch | Click RePlot; check terminal for `[ExperimentThread]` errors |
| Flat IQ traces | D5a baseline not set, or readout params wrong for current flux point | Verify section 2 was done; run `SpecVsQblox` to confirm qubit frequency at current bias |
| `KeyError` during acquire | Required sweep key missing in Experiment Config | Add the missing key (check the class's `init_sweep_vars()`); RePlot after correction |
| Progress hangs at 0 | `acquire()` blocked on hardware | Safe Stop; if no response, Force Stop and inspect terminal |
| `import qick` fails inside Load Exp | qick package not installed in the active environment | `pip install -r requirements.txt` in `.venv` |

## 11. Known issue: legacy module-level `soc` imports

Several legacy experiment files import `soc` at module level from `WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize`. Under Desq's `socProxy` import-time blocking, that `soc` resolves to `None`, and any later use of it (e.g. `soc.reset_gens()` in `set_up_instance`) raises `AttributeError`. `mGainSweepQubitOscillationsR.py` line 7 + line 37 is one example. Two acceptable mitigations:

- (Per file) Remove the module-level import and replace the call with `self.soc.reset_gens()` inside `set_up_instance`. Self-contained, no cross-file impact.
- (Per session) Run that specific calibration via the standalone runner script (`Run_Experiments/calibration_scripts/coupling_strength_calibration.py`) instead of through Desq. The runner imports `MUXInitialize` legitimately and does not hit the block.

The senior-personnel directive is that all *future* development sits on top of Desq. Existing runner scripts can keep working as standalone scripts during the transition; we are not obligated to port them into Desq if they already do their job.

## 12. What not to do

- Do not run `QbloxVoltageSet_8QTriangleLattice_Dictionary.py` from inside Desq via Load Exp. It calls `SPIRack(...)` at import time; under Desq's import sandbox the call may fail or set nothing. Run it from a separate console (section 2).
- Do not load `coupling_strength_calibration.py` or `beamsplitter_calibration.py` via Load Exp. They contain no `ExperimentClass` subclass and yield empty tab sets.
- Do not bypass `set_voltages()` to drive the D5a directly during a sweep without an explicit `ExperimentClass` that owns the voltage state. The `SpecVsQblox` class is the template for sweeps that move the D5a per point.
- Do not click Force Stop unless the experiment is genuinely hung. It bypasses flush and file-write; the last set's data may be incomplete.
- Do not assume Global Config persists across Desq restarts. Save a baseline via Export and reload at the start of each session.
- Do not run quench dynamics before a fresh single-qubit pulse calibration. Quench fidelity is bounded by T1, T2, and pi-pulse accuracy; stale calibrations produce physically meaningless time traces.
- Do not re-implement the calibration GUI inside Desq. The single-qubit calibration GUI at `WorkingProjects/triangle_lattice_quench/Run_Experiments/calibration_gui.py` is a Phase-0 health-check tool and stays as-is. New development goes into Desq as `ExperimentClass` subclasses.

## 13. Cold-start checklist (one-shot reference)

```
[ ] activate .venv
[ ] pip install -r MasterProject/Client_modules/Desq_GUI/requirements.txt    # once
[ ] python WorkingProjects/triangle_lattice_quench/Flux_Files/QbloxVoltageSet_8QTriangleLattice_Dictionary.py
[ ] python -m MasterProject.Client_modules.Desq_GUI.Desq
[ ] Accounts tab -> Connect
[ ] (optional) trim individual D5a channels in Voltage tab
[ ] Load Exp -> the FFMUX single-qubit experiment of interest
[ ] Config Code Extraction -> paste Qubit_Parameters_Master.py -> Extract to Global
[ ] Experiment Config: add the per-class sweep keys
[ ] Run; watch progress and live plot
[ ] (optional) Load Data on a prior .h5 to compare
[ ] Save the session's Global Config via Export Config before closing
```

That sequence reproduces the daily measurement workflow used to take the data in `prev_work/2603.16993v1.pdf`.
