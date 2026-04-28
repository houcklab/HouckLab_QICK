# Agentic QSim Measurement

Houck Lab (Princeton) RFSoC measurement code, on the `agentic_measurement`
branch (forked from `qsim_quench`). The active project is the **triangle-lattice
quench** experiment under
`WorkingProjects/triangle_lattice_quench/`, which depends on
`WorkingProjects/Triangle_Lattice_tProcV2/`.

For onboarding docs see [`report/README.md`](report/README.md). For the
big-picture architecture see [`CLAUDE.md`](CLAUDE.md).

---

## 1. One-time setup

Python 3.12. From the repo root:

```bash
# create env
conda create -n qsim python=3.12
conda activate qsim

# install dependencies (the canonical requirements.txt lives in Desq_GUI)
pip install -r MasterProject/Client_modules/Desq_GUI/requirements.txt

# make the absolute imports (e.g. WorkingProjects.triangle_lattice_quench....) resolvable
pip install -e .
```

> Imports throughout this codebase are absolute from the repo root. **Always run
> commands from the repo root** (`D:\Agentic_QSim_Measurement`) — otherwise
> `from WorkingProjects.…` will fail.

Hardware prerequisites (only needed when actually taking data):

- The lab RFSoC nameserver reachable at the IP hardcoded in
  `WorkingProjects/Triangle_Lattice_tProcV2/socProxy.py` (currently
  `192.168.1.114:8888`, server name `myqick`).
- The lab data share mounted as `Z:\` (`outerFolder` is hardcoded as
  `Z:\QSimMeasurements\Measurements\8QV1_Triangle_Lattice\`).

---

## 2. Launching the calibration GUI

A PyQt5 wizard that walks you through the canonical single-qubit calibration
sequence (Transmission → Spec → AmplitudeRabi → SingleShot → T1 → T2R):

```bash
# from D:\Agentic_QSim_Measurement
python -m WorkingProjects.triangle_lattice_quench.Run_Experiments.calibration_gui
```

The GUI imports `socProxy` lazily, so it will open even if the RFSoC is
unreachable; clicking **Connect to RFSoC** is what actually opens the Pyro4
proxy. You can edit parameters and load JSON setpoint files without hardware,
which is useful for sanity-checking before driving to the lab.

### Workflow

1. **Connect to RFSoC** (top toolbar). The label flips to "RFSoC: connected".
2. **Load Qubit_Parameters JSON** if you have a recent setpoint file (or skip
   to start from the inlined defaults). The status line shows the loaded
   values for the currently selected qubit.
3. **Pick the target qubit** (`Q1` … `Q8`) from the toolbar dropdown.
4. **Walk the tabs in order**, top-to-bottom:

   | Tab            | What it measures                    | Updates on Apply                                  |
   |----------------|-------------------------------------|---------------------------------------------------|
   | Transmission   | Cavity transmission sweep → f_r     | `Readout.Frequency`                               |
   | QubitSpec      | CW or Gaussian spec slice → f_q     | `Qubit.Frequency`                                 |
   | AmplitudeRabi  | Gain sweep with a Gaussian pulse    | `Qubit.Gain`, `Qubit.sigma`                       |
   | SingleShot     | Ground / excited IQ blobs → fidelity| `Readout.angle`, `Readout.threshold`, `fidelity`  |
   | T1             | Energy relaxation                   | `Qubit.T1`                                        |
   | T2R            | Ramsey decoherence                  | `Qubit.T2R`                                       |

   For each stage:
   - tweak the parameters in the left-hand form (sensible defaults are
     pre-filled from `Fast_calib.py`),
   - click **Run** — the experiment runs on a worker thread; the plot lands in
     the inline canvas; the result label shows the fit summary,
   - click **Apply result → Qubit_Parameters** to push the fit back into the
     in-memory dict.

5. **Save Qubit_Parameters JSON** when done. The format is compatible with
   `Run_Experiments/qubit_parameter_files/Qubit_Parameters_Master.py` once you
   wrap it (see below).

### Where data goes

Each Run also writes the standard triplet to `outerFolder`:

```
<outerFolder>/<stage>/<stage>_YYYY_MM_DD/<stage>_YYYY_MM_DD_HH_MM_SS_data.h5
                                                                ..._data.json
                                                                ..._data.png
```

These are the same files a normal run script produces, so the saved data is
fully interchangeable with `mTransmissionFFMUX.py`, `mT1MUX.py`, etc.

### Loading a saved JSON back into a normal run script

The GUI saves under the key `Qubit_Parameters`:

```json
{ "Qubit_Parameters": { "1": {...}, "2": {...}, ... } }
```

To plug into a `Run_Experiments/*.py` script, either point
`qubit_parameter_files/Qubit_Parameters_Master.py` at a Python file that
re-exports this dict, or do it inline:

```python
import json
with open("Qubit_Parameters.json") as f:
    Qubit_Parameters = json.load(f)["Qubit_Parameters"]
```

---

## 3. Common gotchas

- **Run from the repo root.** `python WorkingProjects/.../calibration_gui.py`
  will break absolute imports — use `python -m ...` instead.
- **Don't import `MUXInitialize` in offline tooling.** That module connects to
  the RFSoC at import time. The GUI inlines a copy of `BaseConfig` and
  `FF_Qubits` to avoid this.
- **T1 / T2R `display()` calls `plt.close(fig)`** when `plotDisp=False`, so the
  GUI passes `plotDisp=True, block=False` for those two stages.
- **SingleShot `display()` does not accept `ax=`.** The GUI renders the rotated
  IQ scatter itself instead.
- **`outerFolder` must exist** when you click Run — `ExperimentClass.__init__`
  `mkdir`s the dated subfolder eagerly. If `Z:\` is not mounted you'll get a
  `FileNotFoundError` before the experiment even starts.

---

## 4. Going deeper

- [`CLAUDE.md`](CLAUDE.md) — architecture, config flow, two-tProc-paradigms note.
- [`report/README.md`](report/README.md) — onboarding report with sections on
  software setup, hardware channel map, calibration recipe, ramp experiments,
  and data visualization.
- `WorkingProjects/triangle_lattice_quench/Run_Experiments/Fast_calib.py` — the
  scripted equivalent of this GUI, with quality checks and refinement loops.
