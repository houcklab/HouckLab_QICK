# Software Engineer Onboarding — Triangle Lattice Quench Codebase

Audience: a new software engineer in the Houck Lab measurement team.
Scope: the *how-to* of running and modifying the RFSoC qubit-measurement code that lives at the root `D:\Agentic_QSim_Measurement\` (Windows). Hardware/calibration content is intentionally out of scope; the hardware and measurement engineers cover those.

The active code for the quench experiment is split between two project folders that you should keep open side-by-side:

- `D:\Agentic_QSim_Measurement\WorkingProjects\triangle_lattice_quench\` — the project you are nominally working in.
- `D:\Agentic_QSim_Measurement\WorkingProjects\Triangle_Lattice_tProcV2\` — the older, "donor" project that owns the experiment classes, helpers, and qubit-parameter database. The quench project leans heavily on it.

`CLAUDE.md` at the repo root already covers the high-level scientific workflow and operating loop. This document does *not* repeat that. It focuses on what you actually need to do to get a script running, what breaks, and how the pieces wire together.

---

## 1. Install and bootstrap

### 1.1 Python and conda

The codebase targets **Python 3.12** with QICK 0.2.367 and PyQt5 5.15. The single canonical pinned manifest is:

- `D:\Agentic_QSim_Measurement\MasterProject\Client_modules\Desq_GUI\requirements.txt:1-32`

That file is shared by the GUI and the rest of the lab, so just use it for everything. Top-of-file shows the intended workflow:

```text
# conda create -n my_env_name python=3.12
# pip install -r requirements.txt
# If some installations fail, comment them out and pip install them independently
```
(`requirements.txt:1-3`)

Important pinned versions:

- `qick==0.2.367` (`requirements.txt:23`) — the `asm_v2` API used by V2 programs depends on this. Mismatches here are the single most common cause of weird `AveragerProgramV2` errors.
- `Pyro4==4.82` and `serpent==1.41` for the RFSoC Pyro proxy.
- `PyQt5==5.15.11`, `pyqtgraph==0.13.7`, `QScintilla==2.14.1` for Desq.
- `spirack==0.2.5` for the Qblox/SPI Rack voltage hardware (the `QbloxVoltageSet_8QTriangleLattice.py` machinery — out of scope here, just don't be surprised it imports).

### 1.2 Editable install of the repo

There is a `setup.py` at the repo root:

- `D:\Agentic_QSim_Measurement\setup.py:1-8`

```python
setup(
    name="houcklab-qick",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[],
)
```

It's deliberately minimal. From the repo root run:

```bash
pip install -e .
```

This step is **not optional**. Almost every file in this codebase uses absolute imports rooted at the repo root, e.g.:

```python
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *
from MasterProject.Client_modules.Desq_GUI.CoreLib.socProxy import makeProxy
```

Without an editable install (or without launching Python with `D:\Agentic_QSim_Measurement\` on `PYTHONPATH`), every import like the above will fail with `ModuleNotFoundError: No module named 'WorkingProjects'`.

`setup.py` uses `find_packages()`, so `WorkingProjects`, `MasterProject`, etc. are picked up only if they contain `__init__.py` (they mostly do, where it matters).

### 1.3 Where to launch Python from

Once `pip install -e .` is done, the *imports* work from anywhere. But several run scripts assume **the current working directory is `Run_Experiments/` of the quench project** because they do raw file reads like:

- `WorkingProjects\triangle_lattice_quench\Run_Experiments\Loop_T1_T2.py:80`:
  ```python
  exec(open("UPDATE_CONFIG.py").read())
  ```
- `WorkingProjects\triangle_lattice_quench\Run_Experiments\Loop_T1_T2.py:36`:
  ```python
  from qubit_parameter_files.Qubit_Parameters_Master import *
  ```
  This is a *relative* import from the cwd — it only resolves if cwd is `triangle_lattice_quench/Run_Experiments/`.

So the actual "run a script" recipe is:

```bash
cd D:\Agentic_QSim_Measurement\WorkingProjects\triangle_lattice_quench\Run_Experiments
python Loop_T1_T2.py
```

Running the same file from the repo root, or from PyCharm with the wrong working directory set, will produce one of:
- `ModuleNotFoundError: No module named 'qubit_parameter_files'` (bare `from qubit_parameter_files...`)
- `FileNotFoundError: UPDATE_CONFIG.py` (the `open(...)`)
- `os.add_dll_directory(os.getcwd() + '\\..\\PythonDrivers')` silently failing because cwd is wrong.

Configure your IDE's run configuration accordingly. PyCharm: set the script's "Working directory" to the script's parent folder, not the project root.

### 1.4 Where data is written

Data goes to a hardcoded `Z:\` UNC path. See `MUXInitialize.py:25` (both copies):
```python
outerFolder = "Z:\\QSimMeasurements\\Measurements\\8QV1_Triangle_Lattice\\"
```

`Z:` is a mapped network drive (the lab fileserver). If you are off the lab network or the share is not mapped, every `acquire_save_display(...)` will fail when the `ExperimentClass.__init__` tries `os.makedirs(self.outerFolder + self.path)` (`Experiment.py:111-116`). Either map the drive or temporarily edit `outerFolder` to a local directory while debugging.

---

## 2. Anatomy of an experiment script

This is the bit that takes the longest to internalize. Every quench experiment runs through the same 5-stage chain:

```
MUXInitialize.py           (BaseConfig, FF_Qubits, soc/soccfg, outerFolder)
        |
        v
Qubit_Parameters_Master.py (per-device qubit/readout dictionary)
        |
        v
run script (e.g. Loop_T1_T2.py)
   - sets Qubit_Readout, Qubit_Pulse, FF_gain*_expt, FF_gain*_BS, ...
        |
        v
exec(open("UPDATE_CONFIG.py").read())
        |
        v
flat `config` dict in the local namespace
        |
        v
T1Program(FFAveragerProgramV2)  <- compiled QICK program
T1MUX(ExperimentClass)          <- driver / save / display
```

Concrete files to open while reading the rest of this section:

- `D:\Agentic_QSim_Measurement\WorkingProjects\triangle_lattice_quench\Run_Experiments\Loop_T1_T2.py` (full script, 95 lines).
- `D:\Agentic_QSim_Measurement\WorkingProjects\Triangle_Lattice_tProcV2\MUXInitialize.py` (the BaseConfig source).
- `D:\Agentic_QSim_Measurement\WorkingProjects\Triangle_Lattice_tProcV2\Run_Experiments\UPDATE_CONFIG.py` (the dict-translation step).
- `D:\Agentic_QSim_Measurement\WorkingProjects\Triangle_Lattice_tProcV2\Experimental_Scripts\Basic_Experiments\mT1MUX.py` (a representative `AveragerProgramV2` + `ExperimentClass` pair).

### 2.1 `MUXInitialize.py` — the global "what hardware looks like" file

`Triangle_Lattice_tProcV2\MUXInitialize.py:8`:
```python
from WorkingProjects.Triangle_Lattice_tProcV2.socProxy import makeProxy, soc, soccfg
```

That single import has two effects:

1. It runs `socProxy.py` at module-import time, which immediately calls `soc, soccfg = makeProxy()` (`socProxy.py:30`). That contacts the RFSoC over Pyro4. If you are off-network, this **hangs** (see Section 5).
2. It exposes the live `soc` and `soccfg` objects as module-level names in `MUXInitialize`, so any caller that does `from ... .MUXInitialize import *` automatically gets `soc`, `soccfg`, plus everything else this file defines.

What `MUXInitialize.py` then defines:

- `BaseConfig` — a flat dict of channel numbers, Nyquist zones, mixer frequencies, LOs, default `relax_delay`, etc. (`MUXInitialize.py:29-49`).
- `FF_Qubits` — a dict mapping qubit index `'1'..'8'` to a fast-flux DAC channel and per-qubit `delay_time` (`MUXInitialize.py:52-61`).
- `Additional_Delays`, attached to `BaseConfig` (`MUXInitialize.py:63-67`).
- `outerFolder` — the `Z:\...` data directory (`MUXInitialize.py:25`).
- A best-effort `os.add_dll_directory` call to add the project's `PythonDrivers/` folder to the Windows DLL search path (`MUXInitialize.py:13-22`). On non-Windows it falls back to setting `LD_LIBRARY_PATH`. Both variants paths are wrapped in `try/except: pass`.

The `triangle_lattice_quench` copy of `MUXInitialize.py` is byte-identical to the V2 copy — see Section 3.

### 2.2 `Qubit_Parameters_Master.py` — the device parameter database

A run script does not import a specific qubit-parameter file directly. It imports `Qubit_Parameters_Master`, which is a thin wrapper that picks the active parameter set:

`WorkingProjects\Triangle_Lattice_tProcV2\Run_Experiments\qubit_parameter_files\Qubit_Parameters_Master.py:1-17`:
```python
'''
Wrapper file to switch between different qubit parameters
'''
# from WorkingProjects.Triangle_Lattice_tProcV2.Run_Experiments.qubit_parameter_files.Qubit_Parameters_1234 import *
# from WorkingProjects.Triangle_Lattice_tProcV2.Run_Experiments.qubit_parameter_files.Qubit_Parameters_8Q import *
# ...

from WorkingProjects.Triangle_Lattice_tProcV2.Run_Experiments.qubit_parameter_files.BS_TEST_Readout import *
from WorkingProjects.Triangle_Lattice_tProcV2.Run_Experiments.qubit_parameter_files.pi_flux_J_ll_is_J.Qubit_Parameters import *

Qubit_Parameters = BSTEST_Readout
```

So in practice "switching to new device parameters" is **not** done by changing function arguments — you uncomment a different `from ... import *` line, and the run script picks it up on the next launch. This is the closest thing to a configuration system in the project.

The dict it exposes (`Qubit_Parameters`, `Expt_FF`, etc.) is keyed by qubit index. Concrete shape — see e.g. `BS_TEST_Readout.py:7-40`:

```python
BSTEST_Readout = {
    '1': {'Readout': {'Frequency': 7121.4, 'Gain': 714,
                      'FF_Gains': Readout_TEST_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit':   {'Frequency': 3925.7, 'sigma': 0.03, 'Gain': 5732},
          'Pulse_FF': Readout_TEST_FF},
    ...
}
```

`'Readout'`, `'Qubit'`, `'Pulse_FF'`, `'FF_Gains'` are the four keys consumed by `UPDATE_CONFIG.py`. Anything else is allowed but ignored.

### 2.3 The run script — the only place experiment knobs live

A canonical run script body, `Run_Experiments\Loop_T1_T2.py:48-95`:

```python
for Q in [1,2,3,4,5,6,7,8]:
    Qubit_Readout = [Q]
    Qubit_Pulse   = [Q]

    RunT1 = True
    RunT2 = True

    T1_params  = {"stop_delay_us": 100, "expts": 80,  "reps": 150}
    T2R_params = {"stop_delay_us": 4,   "expts": 150, "reps": 300,
                  "freq_shift": 0.0, "phase_shift_cycles": 4, "relax_delay":200}

    exec(open("UPDATE_CONFIG.py").read())

    if RunT1:
        T1MUX(path="T1", cfg=config | T1_params, soc=soc, soccfg=soccfg,
              outerFolder=outerFolder).acquire_save_display(plotDisp=True, block=False, ax=next(iter_axs1))
    ...
```

What you set in this scope:

- `Qubit_Readout`, `Qubit_Pulse` — lists of qubit indices/names from the `Qubit_Parameters` dict.
- Per-experiment param dicts (`T1_params`, `T2R_params`, `Spec_relevant_params`, `SS_params`, …). Convention is suffix `_params`; these are merged into `config` per call with `config | T1_params`.
- Optionally `FF_gain1_expt..FF_gain8_expt`, `FF_gain1_BS..FF_gain8_BS`, and `Init_FF`. These are bare locals, not dict entries, because `UPDATE_CONFIG.py` reads them as bare names. If you forget to set them you get a `NameError` from inside `UPDATE_CONFIG.py`.

### 2.4 `UPDATE_CONFIG.py` — the `exec(open(...))` translation step

This is the strangest pattern in the project for a software person, so it gets its own section. The literal contents are at:

- `D:\Agentic_QSim_Measurement\WorkingProjects\Triangle_Lattice_tProcV2\Run_Experiments\UPDATE_CONFIG.py:1-43`
- `D:\Agentic_QSim_Measurement\WorkingProjects\triangle_lattice_quench\Run_Experiments\UPDATE_CONFIG.py:1-43` (byte-identical copy)

Key body:

```python
FFReadouts = Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['FF_Gains']
FFPulse    = Qubit_Parameters[str(Qubit_Pulse[0])]['Pulse_FF']
FFExpt     = [FF_gain1_expt, FF_gain2_expt, ..., FF_gain8_expt]
FF_BS      = [FF_gain1_BS,   FF_gain2_BS,   ..., FF_gain8_BS]

for Qubit, FFR, FFE, FFP, FFBS in zip(('1','2','3','4','5','6','7','8'),
                                       FFReadouts, FFExpt, FFPulse, FF_BS):
    FF_Qubits[Qubit] |= {'Gain_Readout': FFR, 'Gain_Expt': FFE,
                         'Gain_Pulse': FFP, 'Gain_BS': FFBS}

trans_config = {
    "res_gains":   [Qubit_Parameters[str(Q_R)]['Readout']['Gain'] / 32766. * len(Qubit_Readout)
                    for Q_R in Qubit_Readout],
    "res_freqs":   [Qubit_Parameters[str(Q_R)]['Readout']['Frequency'] - BaseConfig["res_LO"]
                    for Q_R in Qubit_Readout],
    "readout_lengths": [Qubit_Parameters[str(Q_R)]['Readout']['Readout_Time']
                        for Q_R in Qubit_Readout],
    "adc_trig_delays": [Qubit_Parameters[str(Q_R)]['Readout']['ADC_Offset']
                        for Q_R in Qubit_Readout],
}
qubit_config = {
    "qubit_freqs": [Qubit_Parameters[str(Q)]['Qubit']['Frequency'] - BaseConfig['qubit_LO']
                    for Q in Qubit_Pulse],
    "qubit_gains": [Qubit_Parameters[str(Q)]['Qubit']['Gain'] / 32766. for Q in Qubit_Pulse],
    "sigma":       Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit']['sigma'],
}
config = BaseConfig | trans_config | qubit_config
config["FF_Qubits"]          = FF_Qubits
config["Qubit_Readout_List"] = Qubit_Readout
config['ro_chs']             = [i for i in range(len(Qubit_Readout))]
```

Things to internalize:

- It is `exec`'d, not imported. `exec(open("UPDATE_CONFIG.py").read())` runs in the **caller's** namespace, so it reads `Qubit_Parameters`, `Qubit_Readout`, `FF_gain*_expt`, `BaseConfig`, `FF_Qubits` directly from the run script's locals, and writes back `config`, `FFReadouts`, `FFPulse`, etc. into those same locals. There is no import boundary.
- The DAC normalization `/ 32766.` is hardcoded here. If the gain convention changes, this is the file that has to change.
- `config = BaseConfig | trans_config | qubit_config` is the only place the flat config dict is constructed. From here on the `config` dict is what gets handed to every experiment.
- The `try/except` around `Init_FF` (`UPDATE_CONFIG.py:14-24`) means the run script can omit `Init_FF` entirely; the file falls back to using `FFPulse` and prints `"using pulse FFs as init FFs"`. This is benign but loud.

There is also an experimental "function" form of the same logic at `Run_Experiments\UPDATE_CONFIG_function.py:1-60`, taking everything via `**kwargs`. As of this writing it is not used by any of the run scripts. Treat it as unfinished refactor.

#### 2.4.1 Variant exec patterns

Some scripts use a path-resolved variant when the script lives in a subdirectory:

`Run_Experiments\DESQ_Runners\DESQ_Singleshots.py:135`:
```python
from pathlib import Path
exec(Path("../UPDATE_CONFIG.py").resolve().read_text(), globals())
```

Functionally the same; just one level deeper from `Run_Experiments/`.

### 2.5 `AveragerProgramV2` subclass — the QICK program

The flat `config` dict is then handed to a `qick.asm_v2.AveragerProgramV2` subclass. The relevant base class for nearly everything in this project is `FFAveragerProgramV2` in:

- `D:\Agentic_QSim_Measurement\WorkingProjects\Triangle_Lattice_tProcV2\Experimental_Scripts\Program_Templates\AveragerProgramFF.py:18` —
  ```python
  class FFAveragerProgramV2(AveragerProgramV2):
      '''Averager Program but adds FF and acquire helpers'''
  ```
  This adds `FFPulses`, `FFPulses_direct`, `acquire_shots`, `acquire_populations`, etc. Most experiments inherit from this rather than `AveragerProgramV2` directly.

A representative concrete program is `mT1MUX.py:12-63`:

```python
class T1Program(FFAveragerProgramV2):
    def _initialize(self, cfg):
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"],
                         mixer_freq=cfg["qubit_mixer_freq"])
        self.declare_gen(ch=cfg["res_ch"],   nqz=cfg["res_nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["res_freqs"],
                         mux_gains=cfg["res_gains"],
                         ro_ch=cfg["ro_chs"][0])
        for iCh, ch in enumerate(cfg["ro_chs"]):
            self.declare_readout(ch=ch, length=cfg["readout_lengths"][iCh],
                                 freq=cfg["res_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.add_pulse(ch=cfg["res_ch"], name="res_drive", style="const",
                       mask=cfg["ro_chs"], length=cfg["res_length"])
        FF.FFDefinitions(self)
        self.add_loop("delay_loop", self.cfg["expts"])
        self.delay_loop = QickSweep1D("delay_loop", start=0, end=cfg["stop_delay_us"])
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=cfg["sigma"],
                       length=4 * cfg["sigma"])
        self.add_pulse(ch=cfg["qubit_ch"], name='qubit_drive', style="arb",
                       envelope="qubit", freq=cfg["qubit_freqs"][0],
                       phase=90, gain=cfg["qubit_gains"][0])

    def _body(self, cfg):
        ...
```

Key things:

- The contract between the run script and the program is **just the flat `config` dict**. Everything you see indexed as `cfg["..."]` either came from `BaseConfig`, was added by `UPDATE_CONFIG.py`, or was merged in via `config | T1_params` at the call site.
- New keys are added casually in run scripts. There is no schema; if you misspell `"stop_delay_us"`, you get a `KeyError` at `_initialize` time, not earlier.

### 2.6 `ExperimentClass` — the wrapper that saves and plots

`ExperimentClass` is the project's tiny answer to "an experiment is a thing with `acquire`, `analyze`, `display`, `save`". It's defined twice — see Section 3.

Canonical V2 copy: `WorkingProjects\Triangle_Lattice_tProcV2\Experiment.py:77-216`.

Key contract for subclass authors:

- `__init__(self, soc, soccfg, path, outerFolder, prefix, cfg, ...)` is inherited; it sets up `self.fname`, `self.iname`, `self.cname` (h5/png/json), creates the data subfolder under `outerFolder/path/path_YYYY_MM_DD/`, and stores everything (`Experiment.py:80-122`).
- Subclass overrides `acquire`, `display`, optionally `analyze`, `save_data`. There are many entry points (`acquire_save_display`, `acquire_display_save`, `acquire_save`, `acquire_display`); they only differ in plot/save ordering — see `Experiment.py:142-216`.

So a real T1 experiment = `T1Program` (the QICK program) + `T1MUX` (the `ExperimentClass` subclass), wired up at `mT1MUX.py:65-156`. The run script only ever sees `T1MUX`.

---

## 3. The cross-project import quirk

This is the single biggest "huh?" for a new reader. Both `triangle_lattice_quench` and `Triangle_Lattice_tProcV2` are full project folders with the same shape (`Experiment.py`, `MUXInitialize.py`, `socProxy.py`, `Helpers/`, `Experimental_Scripts/`, `Run_Experiments/`, etc.). And many of those files are byte-identical copies between the two folders.

**But the actual code does not run from inside `triangle_lattice_quench`. It imports from `Triangle_Lattice_tProcV2`.** The quench folder is currently more of a script-and-config workspace; the actual experiment classes, helpers, and parameter database live in the V2 folder.

### 3.1 Concrete examples

Quench-side `MUXInitialize.py` reaches into the V2 socProxy:

`WorkingProjects\triangle_lattice_quench\MUXInitialize.py:8`:
```python
from WorkingProjects.Triangle_Lattice_tProcV2.socProxy import makeProxy, soc, soccfg
```

A quench-side run script does **all** experiment imports from the V2 namespace. From `triangle_lattice_quench\Run_Experiments\Loop_T1_T2.py:3-34`:

```python
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.CalibrateFFvsDriveTiming import \
    CalibrateFFvsDriveTiming
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotDecimated import \
    SingleShotDecimated
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSpecSliceFFMUX import \
    QubitSpecSliceFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mT1MUX import T1MUX
...
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mT2RMUX import T2RMUX
...
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *
from qubit_parameter_files.Qubit_Parameters_Master import *
```

Note line 34: `from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *` — even the `BaseConfig`/`FF_Qubits`/`outerFolder`/`soc`/`soccfg` come from the V2 copy, not the local quench copy.

And at line 36:
```python
from qubit_parameter_files.Qubit_Parameters_Master import *
```

That's the **bare** import (no `WorkingProjects.` prefix). It works only because cwd is `triangle_lattice_quench/Run_Experiments/`, which has its own `qubit_parameter_files/` subdir whose `Qubit_Parameters_Master.py` then *itself* imports from `Triangle_Lattice_tProcV2`. From `triangle_lattice_quench\Run_Experiments\qubit_parameter_files\Qubit_Parameters_Master.py:14-17`:

```python
from WorkingProjects.Triangle_Lattice_tProcV2.Run_Experiments.qubit_parameter_files.BS_TEST_Readout import *
from WorkingProjects.Triangle_Lattice_tProcV2.Run_Experiments.qubit_parameter_files.pi_flux_J_ll_is_J.Qubit_Parameters import *

Qubit_Parameters = BSTEST_Readout
```

So even the device-parameter database is in V2. The quench copy of `qubit_parameter_files/` only contains the `Qubit_Parameters_Master.py` selector and a couple of locally tweaked variants.

### 3.2 Practical implications

- If you need to change the meaning of `T1MUX`, you edit `Triangle_Lattice_tProcV2/Experimental_Scripts/Basic_Experiments/mT1MUX.py`, not anything in `triangle_lattice_quench/`.
- If you need to change a device frequency, you usually edit a file under `Triangle_Lattice_tProcV2/Run_Experiments/qubit_parameter_files/...`.
- The duplicated files in `triangle_lattice_quench/` (`MUXInitialize.py`, `Experiment.py`, `socProxy.py`, `UPDATE_CONFIG.py`) are mostly **dead weight** — they exist because the folder was forked from V2, but the imports don't use them. Don't trust changes to those copies to take effect; the V2 copies are what runs.
- This will eventually be cleaned up. For now, when in doubt, follow the import line and grep for the actual filename used.

### 3.3 Programs imported within V2

V2 internal imports use absolute `WorkingProjects.Triangle_Lattice_tProcV2....` paths. From `mT1MUX.py:4-9`:

```python
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.IQ_contrast import IQ_contrast
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.AveragerProgramFF import FFAveragerProgramV2
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Triangle_Lattice_tProcV2.Experiment import ExperimentClass
import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.FF_utils as FF
```

These are the same patterns you'll write when adding a new experiment class.

---

## 4. The two GUIs: Desq and LAKE

Both GUIs sit on top of `ExperimentClass` — they don't replace it, they just instantiate it differently and route plots into a Qt widget. There is otherwise nothing magical about them; everything you can do in a GUI is also doable from a plain run script.

### 4.1 Desq

Location: `D:\Agentic_QSim_Measurement\MasterProject\Client_modules\Desq_GUI\`. Entry point: `Desq.py` (~78k chars).

What Desq adds on top:

- A custom matplotlib backend (`module://MasterProject.Client_modules.Desq_GUI.scripts.BackendDesq`) installed via `MPLBACKEND` *before* any matplotlib import, so any `plt.plot(...)` inside an experiment is intercepted into a Qt panel rather than opening a desktop window. See `Desq.py:34-41`.
  ```python
  BACKEND_MODULE = 'module://MasterProject.Client_modules.Desq_GUI.scripts.BackendDesq'
  os.environ["MPLBACKEND"] = BACKEND_MODULE
  import matplotlib
  matplotlib.use(BACKEND_MODULE, force=True)
  ```
  This is why the order of imports matters: if anything imports `pyplot` before this, plot interception is silently lost.
- A dynamic experiment loader — `MasterProject\Client_modules\Desq_GUI\scripts\ExperimentLoader.py` — which scans a Python file for classes inheriting from `ExperimentClass` and surfaces them in the GUI. So as long as your new experiment subclasses `ExperimentClass`, it shows up automatically.
- Threaded execution (`ExperimentThread`, `AuxiliaryThread`), live config tree editing (`ConfigTreePanel`, `ConfigCodeEditor`, `ConfigManager`), voltage panels for the Qblox/D5a, and a directory tree for browsing prior runs.
- Its own `socProxy.py` at `Desq_GUI\CoreLib\socProxy.py`. Critically, this is the **safer** version: `makeProxy(ns_host=None)` is a callable, the module does **not** call it at import time (`socProxy.py:1-26`), and the default IP is parameterized. The Desq tab calls `makeProxy(...)` only when the user explicitly connects.
- A `TESTING` flag at the top of `Desq.py` (see module docstring, `Desq.py:14-16`) that skips the RFSoC connection. Pair this with the Mock experiments at `Desq_GUI\Experiments\MockExperiments.py` to develop GUI features without hardware.

Desq also ships its own minimal copy of `ExperimentClass` and a parallel set of FFMUX experiments at `Desq_GUI\Experiments\FFMUX\` (e.g. `mT1FFMUX.py`). These are deliberately decoupled from the V2 implementations — they import from `MasterProject.Client_modules.Desq_GUI.CoreLib.Experiment` and `MasterProject.Client_modules.Desq_GUI.Experiments.FFMUX.FFAveragerProgram`, not from V2. Treat the Desq experiments folder as a starter pack / demo, not as the production quench code.

So in practice:
- **For the quench experiment**: use the run scripts under `triangle_lattice_quench/Run_Experiments/` directly.
- **For interactive single-shot / exploratory work**: Desq, with the mock or real RFSoC.

Desq runners that bridge into the quench codebase live at `triangle_lattice_quench\Run_Experiments\DESQ_Runners\` (currently just `DESQ_Singleshots.py`). They follow the same `Qubit_Parameters_Master` → `UPDATE_CONFIG.py` pattern (see `DESQ_Singleshots.py:1` and `:135`).

### 4.2 LAKE_GUI

Location: `D:\Agentic_QSim_Measurement\MasterProject\Client_modules\LAKE_GUI\LAKE_GUI.py`. Single-file PyQt5 app.

Key differences from Desq:

- LAKE imports the **CoreLib** `socProxy` and calls `makeProxy()` at module top level (`LAKE_GUI.py:14-15`):
  ```python
  from MasterProject.Client_modules.CoreLib.socProxy import makeProxy
  soc, soccfg = makeProxy()
  ```
  So LAKE has the same "import = hang" hazard described in Section 5. There is no testing mode.
- It works against the older `qick.RAveragerProgram` / `AveragerProgram` / `NDAveragerProgram` API (`LAKE_GUI.py:46`), not the V2 `AveragerProgramV2`. The quench experiments are V2, so LAKE is mostly useful for legacy fluxonium experiments rather than the triangle-lattice work.
- Hardcoded `outerFolder` for an unrelated cooldown — `LAKE_GUI.py:92`:
  ```python
  self.outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_07_20_BF2_cooldown_3\\TF4\\"
  ```
  Anyone reusing LAKE for the quench device must edit this.
- Uses `QDictEdit` (a third-party widget) and a different plot-widget architecture (`PlotWidget` next to the script). The custom `ExperimentThread` lives at `MasterProject\Client_modules\LAKE_GUI\ExperimentThread.py`.

Practically, treat LAKE as the "older GUI" and Desq as the "current GUI". Both ride on top of an `ExperimentClass`-shaped object; the experiment code itself does not need to know which one is launching it.

---

## 5. Common gotchas

Numbered so the colleague can scan.

### 5.1 `soc, soccfg = makeProxy()` at import time → import hangs without RFSoC

`WorkingProjects\Triangle_Lattice_tProcV2\socProxy.py:30`:
```python
soc, soccfg = makeProxy()
```

This is a **module-top-level** call, not wrapped in a function or `if __name__`. So the moment any code does:

```python
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *
```

…Pyro4 immediately tries to contact `192.168.1.114:8888` (`socProxy.py:16`). If the RFSoC is unreachable (off-network, VPN issue, lab nameserver down) the call blocks until the Pyro4 timeout — which is long. Symptom: `import` line in your script stalls for ~30 s and then throws.

Workarounds:

- Use Desq with `TESTING = True` for offline development.
- Comment out the bottom line of `socProxy.py:30` while developing offline. Don't commit that.
- For Desq specifically, `Desq_GUI\CoreLib\socProxy.py:22` does **not** call `makeProxy` at import time — that variant is safe to import offline.

### 5.2 Hardcoded RFSoC nameserver IP

`WorkingProjects\Triangle_Lattice_tProcV2\socProxy.py:16`:
```python
ns_host = "192.168.1.114"
```

Same line in `triangle_lattice_quench\socProxy.py:16`. The CoreLib variant defaults to `"192.168.1.7"` (`MasterProject\Client_modules\CoreLib\socProxy.py:11`). If the lab subnet changes or you are bringing up a second RFSoC, this is a project-wide find-and-replace, not a config setting.

There is commented-out machinery in `socProxy.py:11-14` that branches on `socket.gethostname()` (e.g. selecting `128.112.49.105` for the `Euler` machine). That is the canonical place to add per-host overrides if you need them.

### 5.3 Hardcoded `Z:\` `outerFolder`

`WorkingProjects\Triangle_Lattice_tProcV2\MUXInitialize.py:25`:
```python
outerFolder = "Z:\\QSimMeasurements\\Measurements\\8QV1_Triangle_Lattice\\"
```

Every experiment writes h5/json/png there via `ExperimentClass` (`Experiment.py:111-122`). If `Z:` is not mapped, every `acquire_save_display(...)` errors out at the `os.makedirs` step. Map the share or override `outerFolder` in your run script before invoking the experiment (it gets passed as a `kwarg` via `outerFolder=outerFolder`, so just shadowing the local name works).

Other project areas have their own copies of this constant — see e.g. `LAKE_GUI.py:92`, `MasterProject\Client_modules\Runners\RunRabiAmp_ND.py:17`. None of them are connected; each project hardcodes its own path.

### 5.4 `os.add_dll_directory(...)` is Windows-only

`MUXInitialize.py:13-22`:
```python
try:
    if 'macOS' in platform.platform():
        if "LD_LIBRARY_PATH" in os.environ.keys():
            os.environ["LD_LIBRARY_PATH"] += ":.\\..\\PythonDrivers"
        else:
            os.environ["LD_LIBRARY_PATH"] = ".\\..\\PythonDrivers"
    else:
        os.add_dll_directory(os.getcwd() + '\\..\\PythonDrivers')
except:
    pass
```

Notes:

- `os.add_dll_directory` is Windows + Python 3.8+ only. On Linux it raises `AttributeError`, on macOS the `if` branch sets `LD_LIBRARY_PATH` instead — but using Windows-style `\\` separators, which won't help much on Linux.
- The whole thing is wrapped in a bare `try/except: pass`, so failures are silent. If the Vaunix attenuator (`VNX_atten64.dll`, see `MasterProject\Client_modules\PythonDrivers\`) doesn't load, you get a confusing later failure inside `control_atten.py`.
- `os.getcwd() + '\\..\\PythonDrivers'` is *cwd-relative*, so this only resolves correctly when you launch from `Run_Experiments/` (Section 1.3). Yet another reason the cwd matters.

A cleaner replacement would compute the path from `__file__`, but until that lands, just respect the launch convention.

### 5.5 `exec(open("UPDATE_CONFIG.py").read())` instead of import

Already covered in Section 2.4, but flagging it again as a gotcha:

- It's not picked up by static analyzers, IDE refactors, or `find usages`. If you rename `Qubit_Parameters` your IDE won't see the consumer in `UPDATE_CONFIG.py`.
- Errors raise from inside the `exec`, so the traceback's filename is `"<string>"` unless you use the `Path("...").read_text(), globals()` form (which `DESQ_Singleshots.py:135` does).
- You cannot simply `from UPDATE_CONFIG import config` because the file references run-script-local names (`FF_gain*_expt`, `Qubit_Readout`, etc.) that don't exist at import time.

Treat it as a macro expansion. Don't try to "fix" it casually; the unfinished `UPDATE_CONFIG_function.py` next to it is the in-progress refactor.

### 5.6 Duplicated files between `triangle_lattice_quench` and `Triangle_Lattice_tProcV2`

`MUXInitialize.py`, `Experiment.py`, `socProxy.py`, `QbloxVoltageSet_8QTriangleLattice.py`, `UPDATE_CONFIG.py` all exist in both folders. The runtime imports from V2 (Section 3); the quench copies are unused except for the parts that `exec(open(...))` reads. If you edit the quench copy of `Experiment.py` expecting it to take effect, nothing happens. Always grep for the actual import path.

### 5.7 No `__init__.py` discipline / case-sensitive paths

The two folder names differ only in case and underscore: `triangle_lattice_quench` (lowercase) vs `Triangle_Lattice_tProcV2` (mixed). On Windows this is fine; if anyone ever runs this on Linux, the import strings are case-sensitive and any typo silently fails. Be careful when copy-pasting import lines.

### 5.8 The flat `config` dict has no schema

Run scripts merge in arbitrary keys (`stop_delay_us`, `expts`, `reps`, `freq_shift`, `phase_shift_cycles`, `Shots`, …). Consumers index them by string. There is no `pydantic` or dataclass. Symptoms of a typo:

- `KeyError: 'stop_delay_us'` raised inside `_initialize` of an `AveragerProgramV2`.
- Silent re-use of a default from `BaseConfig` (because `BaseConfig | trans_config | qubit_config | T1_params` keeps later keys; if you typo'd the key it's silently dropped).

When debugging an unexpected value, `print(config)` right after `exec(open("UPDATE_CONFIG.py").read())` is your friend.

### 5.9 `Pyro4` pickle protocol

`socProxy.py:8-9`:
```python
Pyro4.config.SERIALIZER = "pickle"
Pyro4.config.PICKLE_PROTOCOL_VERSION = 4
```

This forces pickle as the wire format and pins the protocol at 4. If the RFSoC server side is updated to a newer Pyro/Python that prefers protocol 5, expect compat issues. Match the lab's RFSoC firmware Python before debugging.

---

## 6. Quick index of files to keep open

A short list to keep in tabs while you're getting started:

- `D:\Agentic_QSim_Measurement\CLAUDE.md` — project-level operating manual.
- `D:\Agentic_QSim_Measurement\setup.py` — the editable install.
- `D:\Agentic_QSim_Measurement\MasterProject\Client_modules\Desq_GUI\requirements.txt` — pinned dependencies.
- `D:\Agentic_QSim_Measurement\WorkingProjects\Triangle_Lattice_tProcV2\MUXInitialize.py` — `BaseConfig`, `FF_Qubits`, `outerFolder`, `soc/soccfg` re-export.
- `D:\Agentic_QSim_Measurement\WorkingProjects\Triangle_Lattice_tProcV2\socProxy.py` — RFSoC Pyro4 connection, ns_host hardcoded.
- `D:\Agentic_QSim_Measurement\WorkingProjects\Triangle_Lattice_tProcV2\Experiment.py` — `ExperimentClass` base.
- `D:\Agentic_QSim_Measurement\WorkingProjects\Triangle_Lattice_tProcV2\Run_Experiments\UPDATE_CONFIG.py` — translation step.
- `D:\Agentic_QSim_Measurement\WorkingProjects\Triangle_Lattice_tProcV2\Run_Experiments\qubit_parameter_files\Qubit_Parameters_Master.py` — wrapper that picks the active device parameters.
- `D:\Agentic_QSim_Measurement\WorkingProjects\Triangle_Lattice_tProcV2\Experimental_Scripts\Program_Templates\AveragerProgramFF.py` — `FFAveragerProgramV2`.
- `D:\Agentic_QSim_Measurement\WorkingProjects\Triangle_Lattice_tProcV2\Experimental_Scripts\Basic_Experiments\mT1MUX.py` — canonical example pairing of `Program` + `ExperimentClass`.
- `D:\Agentic_QSim_Measurement\WorkingProjects\triangle_lattice_quench\Run_Experiments\Loop_T1_T2.py` — canonical example run script using all of the above.
- `D:\Agentic_QSim_Measurement\MasterProject\Client_modules\Desq_GUI\Desq.py` — Desq entry point.
- `D:\Agentic_QSim_Measurement\MasterProject\Client_modules\LAKE_GUI\LAKE_GUI.py` — legacy GUI entry point.

If you can read those twelve files and reproduce the chain in Section 2, you are ready to write your own run script.

---

## 7. Suggested first day

1. `conda create -n quench python=3.12; conda activate quench`
2. From repo root: `pip install -r MasterProject\Client_modules\Desq_GUI\requirements.txt`
3. From repo root: `pip install -e .`
4. Verify the `Z:` share is mapped, or temporarily change `outerFolder` to a local path.
5. `cd WorkingProjects\triangle_lattice_quench\Run_Experiments`
6. Confirm the RFSoC at `192.168.1.114` is reachable (`ping` it).
7. Open `Loop_T1_T2.py`, set `for Q in [3]` (a single qubit), run it, watch a T1 and T2R measurement come out.
8. Open Desq (`python MasterProject\Client_modules\Desq_GUI\Desq.py`) with `TESTING=True` and play with Mock experiments while offline.
9. Read one of the `*Experiments.py` scripts in `Run_Experiments/` to see how a multi-step calibration sequence is composed. The hardware and measurement engineers will pick up there.
