# Section 3c — Data Visualization & Analysis

Audience: new colleague joining the Houck Lab triangle-lattice quench project.
Scope: this section covers **only** how data is laid out, displayed, saved, post-hoc reloaded, and analyzed by the helper modules. Software setup, hardware channel maps, calibration, and ramp experiments are covered in sections 1, 2, 3a, and 3b respectively. The repo-root `CLAUDE.md` already covers the operating loop and physics workflow; this section does not repeat that.

Active code lives in:

- `D:/Agentic_QSim_Measurement/WorkingProjects/triangle_lattice_quench/`
- its dependency `D:/Agentic_QSim_Measurement/WorkingProjects/Triangle_Lattice_tProcV2/`
- the GUI plotting layer in `D:/Agentic_QSim_Measurement/MasterProject/Client_modules/Desq_GUI/scripts/`

All file:line citations below are absolute in this repo.

---

## 1. Where the data lands

### 1.1 The save root

The single source of truth for *where on disk* every measurement ends up is `outerFolder` in the per-project initialization file:

```python
# D:/Agentic_QSim_Measurement/WorkingProjects/triangle_lattice_quench/MUXInitialize.py:25
outerFolder = "Z:\\QSimMeasurements\\Measurements\\8QV1_Triangle_Lattice\\"
```

That is a Windows mapped network drive (`Z:`), not a local path. Important consequences:

- If `Z:` is unmapped (laptop offline, fresh login), every `ExperimentClass.__init__` will fail at `os.makedirs`. There is no automatic fallback.
- Every script that imports from `MUXInitialize` inherits this same root.
- The companion project at `WorkingProjects/Triangle_Lattice_tProcV2/MUXInitialize.py` uses the same convention; the two projects share the same drive and a common folder schema.

### 1.2 Dated subfolder + `.h5` / `.json` / `.png` triplet

`ExperimentClass.__init__` (in `WorkingProjects/triangle_lattice_quench/Experiment.py:80-122`) is the construction site for the per-run filename triplet. The relevant lines:

```python
# D:/Agentic_QSim_Measurement/WorkingProjects/triangle_lattice_quench/Experiment.py:94-122
datetimenow = datetime.datetime.now()
datetimestring = datetimenow.strftime("%Y_%m_%d_%H_%M_%S")
datestring = datetimenow.strftime("%Y_%m_%d")
self.prefix = prefix
...
##### check to see if the file path exists
DataFolderBool = Path(self.outerFolder + self.path).is_dir()
if DataFolderBool == False:
    os.makedirs(self.outerFolder + self.path)
DataSubFolderBool = Path(os.path.join(self.outerFolder + self.path, self.path + "_" + datestring)).is_dir()
if DataSubFolderBool == False:
    os.makedirs(os.path.join(self.outerFolder + self.path, self.path + "_" + datestring))

self.titlename = self.path + "_"+datetimestring + "_" + self.prefix
self.fname = os.path.join(self.outerFolder + self.path, self.path + "_" + datestring, self.path + "_"+datetimestring + "_" + self.prefix + '.h5')
self.iname = os.path.join(self.outerFolder + self.path, self.path + "_" + datestring, self.path + "_"+datetimestring + "_" + self.prefix + '.png')
### define name for the config file
self.cname = os.path.join(self.outerFolder +  self.path, self.path + "_" + datestring, self.path + "_" + datetimestring + "_" + self.prefix + '.json')
```

Read this carefully — the schema is intentionally redundant and once you understand it the rest of the data layer is obvious.

For an experiment instantiated with `path="T1MUX"` and `prefix="Q3"`, the on-disk layout becomes:

```
Z:\QSimMeasurements\Measurements\8QV1_Triangle_Lattice\
  T1MUX\
    T1MUX_2026_04_27\
      T1MUX_2026_04_27_14_53_07_Q3.h5
      T1MUX_2026_04_27_14_53_07_Q3.png
      T1MUX_2026_04_27_14_53_07_Q3.json
```

Three things to internalize:

- **`self.path`** is reused twice in the directory tree: once as the experiment-type folder, once (with the date appended) as the per-day subfolder. Two scripts that share `path=` will end up in the same per-day subfolder.
- **`self.titlename`** (line 118) is what shows up as the matplotlib title in every `display()` method — so the plot, the .png on disk, and the .h5 filename all carry the same human-readable timestamp.
- **All three sibling files share the same basename**, only the extension differs. This is what makes "open the .png; the matching .h5 is right next to it" a reliable reload pattern.

The actual file objects are produced lazily:

- `self.datafile()` (lines 132-140) wraps the `.h5` path in the `MakeFile(h5py.File)` subclass; opening it in `'a'` (append) mode means a single `acquire_save_display` run can re-open the file repeatedly without truncation.
- `self.save_config()` (lines 126-130) writes the cfg dict as `.json` *and* attaches it as the `'config'` attribute of the `.h5` root group, so the .h5 alone is enough to reproduce the experiment if the .json is lost.

---

## 2. The display loop

### 2.1 The four entry points

`ExperimentClass` exposes a small family of orchestrator methods. They are all in `Experiment.py`:

- `acquire_save_display(**kwargs)` — `Experiment.py:197-202`. Acquire → save data → save config → display.
- `acquire_display_save(**kwargs)` — `Experiment.py:204-209`. Acquire → display → save data → save config. Use when the display step computes derived quantities you want saved.
- `acquire_display(**kwargs)` — `Experiment.py:211-215`. Acquire → display → save config. Use when `acquire()` *internally* already calls `save_data()` (long sweeps that checkpoint every iteration).
- `acquire_save(**kwargs)` — `Experiment.py:192-195`. Headless variant; never plots.

The legacy `go(save, analyze, display, progress)` (lines 142-151) is still around but new code uses the explicit triple-method names.

The `display(data, **kwargs)` method on the base class is a no-op stub (`Experiment.py:159-160`); every concrete experiment overrides it.

### 2.2 Worked example: `mTransmissionFFMUX.CavitySpecFFMUX.display`

Pick the cavity transmission scan. Its `display` is short enough to internalize:

```python
# D:/Agentic_QSim_Measurement/WorkingProjects/triangle_lattice_quench/Experimental_Scripts/Basic_Experiments/mTransmissionFFMUX.py:135-175
def display(self, data=None, plotDisp = True, figNum = 1, block=True, ax=None, **kwargs):
    if data is None:
        data = self.data
    avgi = data['data']['results'][:,0,0,0]
    avgq = data['data']['results'][:,0,0,1]
    x_pts = (data['data']['fpts'] + self.cfg["res_LO"]) / 1e3   # GHz

    sig = avgi + 1j * avgq
    avgamp0 = np.abs(sig)

    if ax is None:
        plt.figure()
    else:
        plt.sca(ax)
    plt.plot(x_pts, avgi, '.-', color='Green', label="I")
    plt.plot(x_pts, avgq, '.-', color='Blue',  label="Q")
    plt.plot(x_pts, avgamp0, color='Magenta',  label="Amp")

    if hasattr(self, 'peakFreq_lorentz_min') and self.lorentz_fit is not None:
        plt.plot(x_pts, self.lorentz_fit, '-', linewidth=2)
        ...
        plt.axvline(freq_min, color='black', linestyle='--', label=f"...")

    plt.ylabel("a.u.")
    plt.xlabel("Cavity Frequency (GHz)")
    plt.title(self.titlename)
    plt.legend()

    plt.savefig(self.iname)

    if plotDisp:
        plt.show(block=block)
        plt.pause(0.1)
```

Things to notice — they generalize to every other experiment in the project:

- The result tensor shape is `(fpts, ROs, loops, I/Q)`; the slice `[:,0,0,0]` and `[:,0,0,1]` is the canonical I/Q extraction. The convention is documented inline in the matching `acquire()` (`mTransmissionFFMUX.py:67-70`).
- The x-axis is restored to absolute GHz by adding `cfg["res_LO"]` and dividing by 1e3 — IF frequencies are stored in MHz throughout the codebase.
- `plt.title(self.titlename)` is the only place the timestamp shows up on the figure; this is your link back to the .h5 file later.
- **`plt.savefig(self.iname)` is the only thing that writes the .png to disk.** It runs unconditionally — regardless of `plotDisp`. If you skip `display()` you don't get a .png.
- The `ax=None / plt.sca(ax)` pattern is so the GUI/Desq tab can supply its own Axes; running directly, you get a fresh figure.
- `plt.show(block=block)` controls whether the script blocks; `plt.pause(0.1)` is the classic "give the event loop a tick" so the figure repaints when running inside a notebook.

`mT1MUX.T1MUX` follows exactly the same pattern (see `mT1MUX.py:1-80` for the acquire half; its `display` has the same `plt.title(self.titlename); plt.savefig(self.iname); plt.show(...)` ending). Once you know the shape conventions, every other experiment in `Experimental_Scripts/Basic_Experiments/` is a small variation.

### 2.3 The general recipe

Every concrete `display` method does roughly:

1. `data = data or self.data` — lets it be re-called on a reloaded dataset.
2. Pull I/Q (or already-thresholded populations) out of the standard tensor layout.
3. Convert sweep axis to physical units (often using `cfg["res_LO"]` or `cfg["qubit_LO"]`).
4. If `analyze()` ran, overlay fit results that were attached as `self.<something>`.
5. `plt.title(self.titlename)` to tie figure to filename.
6. `plt.savefig(self.iname)` — this is the single .png write.
7. `plt.show(block=block)` gated on `plotDisp` so headless overnight loops don't pop windows.

If your new experiment doesn't save a .png, 99% of the time the bug is that `display` was either skipped or returned early before `savefig`.

---

## 3. Helpers-level analysis utilities

`WorkingProjects/triangle_lattice_quench/Helpers/` contains the analysis primitives used across the experiment scripts. The five modules below are the ones you will touch most often.

### 3.1 `Helpers/CorrelationAnalysis.py`

`Helpers/CorrelationAnalysis.py:1-60`. Two-qubit shot-level correlation primitives.

- **Input shape.** Takes integer 0/1 single-shot arrays whose last axis is reps; earlier axes can be arbitrary timesteps / sweep coordinates. `n1, n2` come in as already-thresholded shots. `collate(n1, n2)` (`CorrelationAnalysis.py:5-23`) reshapes the pair into per-timestep probabilities `[P00, P01, P10, P11]`.
- **Returns.** `get_nn_correlations(n1, n2, n3, n4)` (lines 25-32) returns `<(n2−n1)(n4−n3)>` averaged over reps — the raw connected nearest-neighbor correlator. `get_corrected_nn_correlations(n1, n2, n3, n4, conf_mats)` (lines 34-60) does the same after applying the inverse of four readout-confusion matrices (one per qubit, 2x2 each). Useful when two-qubit assignment fidelity is below ~95%.
- **When to call.** After single-shot acquisition that already ran the histogram threshold (see §3.3) so each shot is a 0/1 integer. Use the corrected variant if you have populated the per-qubit confusion matrices from a calibration run.

### 3.2 `Helpers/IQ_contrast.py`

`Helpers/IQ_contrast.py:1-43`. Small, very general single-qubit IQ rotation utilities.

- **Input shape.** `Imat`, `Qmat` are arrays of any matching shape — usually `(sweep1, sweep2, ...)` of average IQ values.
- **Returns.** `IQ_angle(I, Q)` (lines 4-9) finds the rotation angle that puts all signal into the Q-axis-projected variance (a robust 1D scalar minimizer). `rotate(theta, I, Q)` returns the rotated pair. `IQ_contrast(I, Q)` (line 14) returns mean-subtracted rotated I — i.e. a 1D contrast trace ready to fit. `normalize_contrast` (line 19) maps it onto `[-1, 1]`. `frequency_guess(t, y)` and `omega_guess(t, y)` (lines 33-43) do an FFT-based dominant-frequency guess; useful as `p0` for chevron / Rabi cosine fits.
- **When to call.** Anytime you have raw IQ from a single readout and want a single real number per sweep point. This is the entry point for almost all quench-time-series plots and for chevron fits.

### 3.3 `Helpers/hist_analysis.py`

`Helpers/hist_analysis.py:1-280`. Single-shot histogram analysis and threshold extraction.

- **Input shape.** `hist_process(data, ...)` (lines 9-114) takes `data = [ig, qg, ie, qe]` — four 1D arrays of single-shot IQ values for prepared-g and prepared-e. `hist_process_2Q(data, ...)` (lines 119-261) takes a full data dict with keys `i_gg, q_gg, i_ge, ...` matching all four computational basis states for two qubits (looped per readout in `data['config']['Qubit_Readout_List']`).
- **Returns.** `hist_process` returns `(fid, threshold, theta)` (or with `ne_contrast, ng_contrast` if `return_errors=True`). `theta` is the rotation angle that maximizes g/e separation along I; `threshold` is the I-axis cut. With `plot=True` you also get a 3-panel figure (unrotated IQ, rotated IQ, histogram with fidelity in the title). `multivariate_gaussian(data)` (lines 263-279) does a 2-component Gaussian-mixture fit and returns `(means, variances)`.
- **When to call.** After every calibration-quality single-shot run. The returned `(threshold, theta)` is what you feed into downstream thresholding code (and into `rotate_SS_data.rotate_data` — see §3.6).

### 3.4 `Helpers/Beamsplitter_Fit.py`

`Helpers/Beamsplitter_Fit.py:1-363`. Two related chevron-style fitters for the two-qubit beamsplitter calibration.

- **Input shape.** `fit_double_beamsplitter(Z, gains)` (lines 68-168) takes `Z` of shape `(R, G, T)` — `R` readouts, `G` gain values, `T` time points — and a 1D `gains` array. `fit_beamsplitter_offset(Z, offsets, wait_times)` (lines 260-362) takes the same `(R, O, T)` shape and additionally a 1D `wait_times` array. Both internally extract per-row contrast (max−min over time), normalize, and run multi-start non-linear fits.
- **Returns.** A dict containing `popt` `(R, k)`, `perr` (list of stddev arrays), `r_squared` `(R,)`, plus the sorted gain/offset axis and any auxiliary indices needed to reproduce the fit. The companion `reconstruct_double_beamsplitter_fit` / `reconstruct_beamsplitter_offset_fit` (lines 7-66, 170-258) take the saved `popt` and rebuild dense fit curves and the locations of the `0`, `π/2`, `π`, `2π` crossings — the points you actually use to set gate parameters.
- **When to call.** After running a beamsplitter chevron sweep. Save the small `popt` array to .h5; later, re-run the `reconstruct_*` function in a notebook to get plotting-ready dense curves without storing the dense fit.

### 3.5 `Helpers/Coupling_strength_fit.py`

`Helpers/Coupling_strength_fit.py:1-45`. Extracts the qubit-qubit coupling `g` from a chevron.

- **Input shape.** `fit_chevron(gains, times, pop_matrix, b_guess=1.36e-04, return_fit_points=False)` (lines 14-45). `gains` is the y-axis (e.g. flux gain or detuning proxy), `times` is the swap-time x-axis, `pop_matrix` has shape `(len(gains), len(times))` with single-qubit excited-state populations or expectation values along each row.
- **Returns.** Per-row, fits a damped cosine (`cosfit`, lines 7-8) to extract the swap frequency at each gain value. Then fits the resulting `freq(gain)` to `2*sqrt(b*(g − g0)^2 + g_coupling^2)` (`freqfit`, lines 10-12) and returns `[g0, b, g_coupling]` — i.e. the chevron center, the curvature, and the on-resonance coupling. With `return_fit_points=True` it also gives back the per-row frequencies for plotting.
- **When to call.** Right after a chevron acquisition once you trust the population conversion — i.e. after histogram thresholding and (if needed) confusion-matrix correction. This is the fit you cite when you quote a "g of N MHz" for a tunable coupler pair.

### 3.6 `Helpers/rotate_SS_data.py`

`Helpers/rotate_SS_data.py:1-34`. Tiny utility module for downstream single-shot processing.

- **Input shape.** All functions take a 2-tuple `data = (i, q)` of equal-length 1D arrays — these are the *post-acquisition* IQ traces from one readout.
- **Returns.** `rotate_data(data, theta)` (lines 5-11) returns `(i_new, q_new)` rotated by `theta` (the angle from `hist_analysis.hist_process`). `count_percentage(data, threshold)` (lines 13-17) returns the excited-state fraction by counting `i > threshold`. `average_data(data)` (lines 19-21) returns `mean(I)` for one shot batch. `correct_occ(pop_data, confusion_matrix)` (lines 23-29) inverts a 2×2 readout-confusion matrix on a 1D population vector. `pop_to_expect(pop_vec)` (lines 31-33) maps populations in `[0,1]` to expectation values in `[-1,1]`.
- **When to call.** Inside any user-side post-processing that consumes single-shot IQ. The standard pipeline is: run `hist_process` once to get `(theta, threshold)`, then for every subsequent dataset call `rotate_data → count_percentage → correct_occ → pop_to_expect` to get clean two-level expectation values.

---

## 4. Desq GUI's plotting layer

You don't need to read the Desq internals to use it, but knowing the three modules below explains what is going on under the hood when figures appear in the GUI tab without your script touching any GUI code.

### 4.1 `MasterProject/Client_modules/Desq_GUI/scripts/PlotSinkManager.py`

`PlotSinkManager.py:76-343`. Routes matplotlib figures from worker threads to GUI tabs.

It owns one `pyqtSignal(object, object, str, int)` (`PlotSinkManager.py:113`) that fires with `(figure, target_tab, event_type, session_id)` whenever the matplotlib backend draws. Per worker thread (each Desq tab spawns one) it registers a *sink callable* keyed by `threading.current_thread().ident`. Sinks are weak-ref'd against both the tab and the manager so neither outlives natural GC. The `sink_context(tab, session_id)` context manager (lines 252-276) is the canonical way to wrap the body of an experiment; on enter it calls `setup_sink_for_thread`, on exit `cleanup_sink_for_thread`. The session_id is a per-run integer that the receiving tab validates so figures from a previous run can't leak into a new run's carousel.

There is also a 50 ms time-based debounce per figure (`PlotSinkManager.py:189`) — only the most recent of a rapid burst of `draw()` calls makes it across the thread boundary, which is what keeps live-updated plots from spamming the GUI.

### 4.2 `MasterProject/Client_modules/Desq_GUI/scripts/FigureCarousel.py`

`FigureCarousel.py:1-450+`. Multi-figure thumbnail navigation.

A horizontal `QScrollArea` of clickable `ThumbnailWidget`s (`FigureCarousel.py:45-218`). Each thumbnail is a 120×80 raster snapshot of a matplotlib figure (or a pre-rendered `QPixmap` for a pyqtgraph snapshot — `add_pixmap`, line 341). The carousel is hidden when there is 0 or 1 figure (`FigureCarousel.py:317-318`) and reveals itself only once a second figure arrives. Newest figure becomes active by default; clicking a thumbnail switches the displayed figure but does **not** rerun the experiment. The class explicitly does not own figure lifecycles — the `PlotSinkManager` does — so calling `carousel.start_new_run()` or letting tabs swap is safe and won't double-free.

Practical takeaway: an experiment that calls `plt.figure()` multiple times (e.g. `hist_process_2Q` in §3.3, which makes a 2×3 grid) will produce one carousel entry per `Figure` object; the carousel makes those navigable instead of all stacked into one tab.

### 4.3 `MasterProject/Client_modules/Desq_GUI/scripts/BackendDesq.py`

`BackendDesq.py:1-450+`. Custom matplotlib backend.

This is the trick that lets unmodified experiment scripts plot inside the GUI. The module declares itself as `module://MasterProject.Client_modules.Desq_GUI.scripts.BackendDesq` (see `PlotSinkManager.py:461`); when the GUI launches, `ensure_backend_installed()` (`PlotSinkManager.py:464-507`) calls `matplotlib.use(...)` so every subsequent `plt.figure()` / `plt.show()` lands here.

The mechanics:

- `FigureCanvasDesq` extends headless `FigureCanvasAgg` and **overrides `draw()` and `draw_idle()`** (`BackendDesq.py:242-285`). After matplotlib finishes rendering into the Agg buffer, it notifies whichever thread-local plot sink is currently registered.
- `FigureManagerDesq.show()` (`BackendDesq.py:363-376`) is a no-op except it calls `canvas.draw()` — so `plt.show()` from experiment code does not pop an OS window; it just triggers the sink notification.
- The plot sink is stored in `threading.local()` (`BackendDesq.py:121`) so each Desq tab's worker thread has an independent destination. This is what stops a multi-tab Desq session from cross-contaminating plots.

Net effect: `mTransmissionFFMUX.CavitySpecFFMUX.display` (which calls `plt.figure()`, `plt.plot(...)`, `plt.savefig(self.iname)`, `plt.show()`) **does not change at all** when run inside Desq. The `savefig` still writes the .png. The `show` triggers a `draw()`. The sink intercepts, fires the Qt signal, and the GUI tab re-renders. The script author never imports anything Qt.

### 4.4 When to use Desq vs. running scripts directly

- **Use Desq** for interactive exploration (parameter tweaks while watching the figure update), multi-experiment runs where you want a session-scoped carousel of every figure you generated, or when handing off a measurement to a colleague who shouldn't have to remember the script-level plumbing. Tabs isolate worker threads so you can have a long T1 sweep on tab A while doing single-shot calibration on tab B.
- **Run scripts directly** for batch / overnight loops, scripted parameter sweeps that don't need eyeballs, anything launched from a Jupyter notebook for post-hoc analysis, or anything that runs unattended over a network share where the GUI process would be a liability. The scripts do not depend on Desq — `display()` falls back to whatever matplotlib backend is active (typically `TkAgg` or `Qt5Agg`), and `savefig` always writes the .png regardless.

A common workflow is: prototype an experiment script under Desq until you're happy with the `display()`, then swap to direct execution from a `__main__` block or a notebook for the production overnight run.

---

## 5. Standalone post-hoc analysis

Once a measurement has finished, the .h5 / .json / .png triplet is self-contained. You can reload and re-plot any past dataset without re-running the experiment.

### 5.1 The `MakeFile` h5py wrapper

`Experiment.py:8-62`. `MakeFile` is a thin subclass of `h5py.File`:

- `__init__(*args, **kwargs)` — opens the file and immediately `flush()`es so partial writes are durable (lines 9-11).
- `add(key, data)` — writes a numpy array under `key` with a resizable `maxshape=(None,...)` so subsequent calls can overwrite even with a new shape; deletes the existing dataset first if `key` already lives in the file (lines 13-62). It also has fallbacks for the awkward case of string-typed `readout_list` / `Qubit_Readout_List`, which it converts to int arrays.

You almost never instantiate `MakeFile` yourself — `ExperimentClass.datafile()` (`Experiment.py:132-140`) returns one for you, opened on `self.fname` in `'a'` mode.

### 5.2 `ExperimentClass.load_data(f)`

`Experiment.py:185-190`:

```python
def load_data(self, f):
    data={}
    for k in f.keys():
        data[k]=np.array(f[k])
    data['attrs']=f.get_dict()
    return data
```

Note: the upstream `MakeFile` does not actually define `get_dict()`, so the `'attrs'` line will raise unless the file you opened is one of the SLab-style `SlabFile` derivatives. In practice the safe pattern is to skip `load_data` and just iterate keys directly with vanilla `h5py` (see template below), or call `dict(f.attrs)` manually for the cfg JSON.

### 5.3 Notebook template — load and replot a saved dataset

Drop-in starter for a Jupyter notebook. Replace the `H5_PATH` with any `.h5` produced by an `ExperimentClass`-derived run.

```python
import json
import h5py
import numpy as np
import matplotlib.pyplot as plt

# Path to the .h5 produced by acquire_save_display
H5_PATH = r"Z:\QSimMeasurements\Measurements\8QV1_Triangle_Lattice\TransmissionFFMUX\TransmissionFFMUX_2026_04_27\TransmissionFFMUX_2026_04_27_14_53_07_Q3.h5"

# 1) Load every dataset and the embedded config
with h5py.File(H5_PATH, "r") as f:
    data = {k: np.array(f[k]) for k in f.keys()}
    cfg  = json.loads(f.attrs["config"]) if "config" in f.attrs else None

# 2) Inspect what was saved
print(list(data.keys()))
# typical keys for a transmission run: ['results', 'fpts']

# 3) Replot using the same logic as ExperimentClass.display
results = data["results"]                   # shape: (fpts, ROs, loops, I/Q)
fpts    = data["fpts"]
avgi    = results[:, 0, 0, 0]
avgq    = results[:, 0, 0, 1]
amp     = np.abs(avgi + 1j * avgq)

x_pts = (fpts + cfg["res_LO"]) / 1e3        # GHz, matching display()

plt.figure()
plt.plot(x_pts, avgi, '.-', label="I")
plt.plot(x_pts, avgq, '.-', label="Q")
plt.plot(x_pts, amp,   '-',  label="Amp")
plt.xlabel("Cavity Frequency (GHz)")
plt.ylabel("a.u.")
plt.legend()
plt.title(H5_PATH.split("\\")[-1])
plt.show()
```

For a more elaborate experiment (single-shot, two-qubit, anything that calls `analyze()` and stores derived quantities), the same pattern works — just enumerate `data.keys()` and pull out what you need. If you want to literally re-run the original `display()` method, the canonical recipe is:

```python
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Basic_Experiments.mT1MUX import T1MUX
exp = T1MUX(soc=None, soccfg=None, path="T1MUX", outerFolder="...", prefix="Q3", cfg=cfg)
exp.data = {"data": data, "config": cfg}    # mimic what acquire() would have stored
exp.display(exp.data, plotDisp=True, block=False)
```

This works because every `display()` is written to take `data=None` and fall back to `self.data`, and because none of the plot logic touches `self.soc` / `self.soccfg`. The constructor *will* attempt to `os.makedirs` a fresh dated subfolder for `self.iname`, so if you only want to look at a figure and don't want a new empty folder, point `outerFolder` at a scratch directory or skip the wrapper and inline the plotting code (as in the first snippet).

---

## Cross-references

- §1 (software setup): `report/01_software_engineer.md`
- §2 (hardware channel maps): `report/02_hardware_engineer.md`
- §3a (calibration), §3b (ramp experiments): companion sections.
- For the underlying `ExperimentClass` (donor project, identical interface): `D:/Agentic_QSim_Measurement/WorkingProjects/Triangle_Lattice_tProcV2/Experiment.py`.
- For the GUI launch code that wires the backend in: `MasterProject/Client_modules/Desq_GUI/scripts/PlotSinkManager.py:461-535`.
