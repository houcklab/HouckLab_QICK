# Onboarding Report — Triangle-Lattice Quench Project

Prepared for a colleague joining the Houck Lab measurement group. Assembled by three specialist passes over the codebase on branch `agentic_measurement` (off `qsim_quench`), repo root `D:\Agentic_QSim_Measurement`.

Read the root [`CLAUDE.md`](../CLAUDE.md) first for the 30-second architectural picture, then dive into the sections below in order.

## Sections

| # | File | Audience | What's inside |
|---|------|----------|---------------|
| 1 | [`01_software_engineer.md`](01_software_engineer.md) | Software | Environment setup, the `MUXInitialize → Qubit_Parameters_Master → run script → UPDATE_CONFIG → AveragerProgramV2 → ExperimentClass` chain, cross-project import quirks, GUI integration, import-time hardware coupling and Windows-isms. |
| 2 | [`02_hardware_engineer.md`](02_hardware_engineer.md) | Hardware | RFSoC channel map (`res_ch`, `qubit_ch`, `fast_flux_chs`, mixer/LO structure, Nyquist zones), Fast-Flux subsystem and `FF_Qubits` lifecycle, external instruments (Vaunix LDA, Yoko GS200, SPI rack/D5a), MUX readout architecture, hardware prerequisites per calibration tier. |
| 3a | [`03a_calibration.md`](03a_calibration.md) | Measurement | Canonical first-time-taking-data sequence: transmission → spec → Rabi → single-shot → T1/T2R/T2E. How `Qubit_Parameters` gets populated, where setpoint files live, when to use `Fast_calib.py` / `Loop_T1_T2.py` / etc. |
| 3b | [`03b_ramp.md`](03b_ramp.md) | Measurement | What "ramp" / "quench" mean physically, ramp parameterization (`generate_ramp`), `ramp_initial_gain` flow through `UPDATE_CONFIG.py`, the `ThreePartProgram` template, building and running a basic ramp, FF-gain → flux current calibration. |
| 3c | [`03c_data_visualization.md`](03c_data_visualization.md) | Measurement | Where `.h5/.json/.png` triplets land, the `acquire_save_display` flow, the six Helpers analysis utilities, the Desq plotting layer (PlotSinkManager / FigureCarousel / BackendDesq), and a notebook template for post-hoc reload. |

## Suggested reading order

1. **First day:** `CLAUDE.md` → `01_software_engineer.md` → boot the environment, get Desq running against the lab nameserver.
2. **Before touching hardware:** `02_hardware_engineer.md` — understand the channel map and which FF channel drives which qubit before you change a `BaseConfig` value.
3. **First measurement:** `03a_calibration.md` — run the transmission/spec/Rabi/single-shot loop until your `Qubit_Parameters` setpoint file is fresh.
4. **First quench:** `03b_ramp.md` — once the qubits are calibrated, build a ramp.
5. **Reading data:** `03c_data_visualization.md` — at any point you need to inspect saved `.h5` files or wire up custom plotting.

## Quick reference (cross-section)

- Repo root entrypoint for absolute imports: `D:\Agentic_QSim_Measurement` → `pip install -e .` makes them resolvable.
- Active project pair on this branch: `WorkingProjects/triangle_lattice_quench/` (depends on `WorkingProjects/Triangle_Lattice_tProcV2/`).
- RFSoC nameserver: `192.168.1.114:8888`, server name `myqick` (in `socProxy.py`).
- Data drive: `Z:\QSimMeasurements\Measurements\8QV1_Triangle_Lattice\`.
- Desq launch (from repo root): `python -m MasterProject.Client_modules.Desq_GUI.Desq`.
