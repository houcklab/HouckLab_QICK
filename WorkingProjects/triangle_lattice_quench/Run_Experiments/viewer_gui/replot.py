"""Best-effort redraw of an archived run, and the sandboxed experiment import it needs.

This is the ONLY module that reaches the experiment classes, and those import qick.
Every such import is lazy and wrapped, so on a machine without qick the file list,
png, Data and Config panes all still work and only this pane reports it is unavailable.
"""
from __future__ import annotations

import contextlib
import os
import re
import sys
import tempfile
import types
from pathlib import Path
from typing import Optional

# viewer_gui -> Run_Experiments -> triangle_lattice_quench
EXPERIMENTAL_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "Experimental_Scripts"

NO_QICK_MESSAGE = ("experiment classes unavailable (qick not installed on this machine) "
                   "- the Plot (png), Data and Config tabs still work")


@contextlib.contextmanager
def _import_sandbox():
    """Stub MUXInitialize / socProxy while an experiment module is imported.

    Legacy experiment files do ``from MUXInitialize import soc`` or call ``makeProxy()``
    at module scope. The viewer has no hardware, so the stubs expose None and the
    import succeeds without anyone trying to reach the RFSoC. Restores on exit.
    """
    # These two are the only live ones: every module-scope import under
    # Experimental_Scripts uses the triangle_lattice_quench. prefix (the old
    # WorkingProjects.Triangle_Lattice_tProcV2 spellings are all commented out).
    names = ["triangle_lattice_quench.MUXInitialize", "triangle_lattice_quench.socProxy"]
    saved = {n: sys.modules.get(n) for n in names}
    try:
        for n in names:
            mod = types.ModuleType(n)
            mod.BaseConfig = {}
            mod.soc = None
            mod.soccfg = None
            mod.makeProxy = lambda *a, **kw: (None, None)
            sys.modules[n] = mod
        yield
    finally:
        for n, prev in saved.items():
            if prev is None:
                sys.modules.pop(n, None)
            else:
                sys.modules[n] = prev


def find_class_files(name: str, root=EXPERIMENTAL_SCRIPTS_DIR) -> list[Path]:
    """Every module under Experimental_Scripts that defines ``class <name>``.

    Text-grep rather than importing each module to discover its classes. Several names
    are defined in more than one file (AmplitudeRabiFFMUX, SingleShotFFMUX, T1vsFF,
    ConstantTone_Experiment ...), which is why this returns a list and the caller
    reports the ambiguity instead of silently replotting with another class.
    """
    pattern = re.compile(rf"^class\s+{re.escape(name)}\b", re.M)
    out = []
    for path in sorted(Path(root).rglob("*.py")):
        try:
            if pattern.search(path.read_text(errors="ignore")):
                out.append(path)
        except Exception:
            continue
    return out


def import_experiment_class(file_path: str, class_name: str):
    """Sandbox-import ``file_path`` and return the named class. May raise ImportError
    (notably ModuleNotFoundError: qick) -- callers must handle that."""
    import importlib.util

    p = Path(file_path)
    spec = importlib.util.spec_from_file_location(
        f"_viewer_exp_{abs(hash(str(p)))}", str(p))
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load spec for {p}")
    with _import_sandbox():
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    cls = getattr(module, class_name, None)
    if cls is None:
        raise AttributeError(f"{p.name} has no class {class_name!r}")
    return cls


# Experiment classes are declared as ``class <Name>(ExperimentClass)``; matching that
# exactly keeps the folder-name guess away from the Program/helper classes in the file.
_EXPT_CLASS_RE = re.compile(r"^class\s+(\w+)\s*\(\s*ExperimentClass\s*\)", re.M)

# Session cache so repeated Replot clicks do not re-grep ~72 files and re-exec a module.
_CLASS_CACHE: dict[str, tuple] = {}
_GUESS_CACHE: dict[str, list] = {}


def guess_classes_for_folder(folder: str, root=EXPERIMENTAL_SCRIPTS_DIR) -> list[tuple]:
    """Candidate (path, class_name) for a file with no 'Experiment' attr.

    The archive folder is ``self.path`` ('T2R'); the class is ``type(self).__name__``
    ('T2RMUX'), so an exact grep on the folder name usually misses. Accept an
    ExperimentClass subclass whose NAME starts with the folder name, or one defined in
    a module called ``m<Folder>*.py``. The caller only uses the result when exactly one
    candidate matches, and always labels it a guess.
    """
    if folder in _GUESS_CACHE:
        return _GUESS_CACHE[folder]
    low = folder.lower()
    hits: list[tuple] = []
    for path in sorted(Path(root).rglob("*.py")):
        try:
            text = path.read_text(errors="ignore")
        except Exception:
            continue
        names = _EXPT_CLASS_RE.findall(text)
        if not names:
            continue
        module_hit = path.stem.lower() in (low, "m" + low)
        for class_name in names:
            if class_name.lower().startswith(low) or module_hit:
                hits.append((path, class_name))
    _GUESS_CACHE[folder] = hits
    return hits


def resolve_experiment_class(name: str, root=EXPERIMENTAL_SCRIPTS_DIR):
    """Returns (cls_or_None, candidate_paths, error_or_None).

    ``error`` is the last ImportError, so the caller can tell "qick is missing" from
    "that class does not exist here". Successful resolutions are cached for the session.
    """
    if name in _CLASS_CACHE:
        return _CLASS_CACHE[name]
    paths = find_class_files(name, root)
    error = None
    for path in paths:
        try:
            result = (import_experiment_class(str(path), name), paths, None)
            _CLASS_CACHE[name] = result
            return result
        except Exception as exc:                # includes ModuleNotFoundError: qick
            error = exc
    return None, paths, error                   # not cached: a retry may succeed


# Subplot grid per readout count, as in SweepExperimentND._make_subplots.
_GRIDS = {1: (1, 1), 2: (1, 2), 3: (2, 2), 4: (2, 2), 5: (2, 3), 6: (2, 3), 7: (2, 4), 8: (2, 4)}


def _make_axes(fig, count: int) -> list:
    """Clear ``fig`` and give it one axes per readout, laid out like the experiments' own figures."""
    rows, cols = _GRIDS.get(count, _GRIDS[8])
    fig.clf()
    axs = [fig.add_subplot(rows, cols, i + 1) for i in range(rows * cols)]
    for extra in axs[count:]:
        extra.set_axis_off()
    return axs


def _restore_sweep_state(expt, loaded) -> str:
    """Set what a sweep's __init__ would have (y_key, z_value, labels, ...) without running it:
    __init__ compiles a QICK program and makes files. Returns an error text, "" when fine."""
    init = getattr(expt, "init_sweep_vars", None)
    if init is None:
        return ""
    expt.keys, expt.sweep_arrays = tuple(), tuple()
    try:
        init()
    except Exception as exc:
        return f"init_sweep_vars: {exc}"
    d = loaded["data"]
    if "x_name" in expt.__dict__ and "x_key" not in expt.__dict__:
        expt.loop_names = (expt.x_name,)            # the QICK loop that is the plot's x axis
    if getattr(expt, "z_value", None) in ("population", "population_shots") and "population_corrected" in d:
        expt.z_value = "population_corrected"       # acquire() promotes it when a confusion matrix exists
    return ""


def replot_into(path: str, ax) -> str:
    """Redraw an archived run into ``ax``; returns a status message, never raises.

    Resolves the saving class from the h5 'Experiment' attr, builds it with ``__new__``
    (``__init__`` would create a new dated folder and filenames), and calls
    ``display(ax=...)``. A display that takes ``fig_axs`` instead (a ``(fig, axs)`` tuple, the
    figure being needed for colorbars) gets ``ax``'s whole figure, rebuilt with one axes per
    readout, so the caller should treat ``ax`` as replaced afterwards.
    """
    import inspect
    import matplotlib.pyplot as plt
    from triangle_lattice_quench.Experiment import ExperimentClass, FileBeingSaved
    from .data_index import BUSY_MESSAGE

    ax.clear()
    try:
        meta = ExperimentClass.load_metadata(path)
    except FileBeingSaved:
        return BUSY_MESSAGE
    except Exception as exc:
        return f"cannot read metadata: {exc}"
    name = meta.get("Experiment")
    if isinstance(name, bytes):
        name = name.decode()
    guessed = ""
    if not name:
        # No attr (saved before save_metadata). Guess from the archive folder, but only
        # when exactly one ExperimentClass subclass matches -- never silently.
        folder = Path(path).parents[1].name
        hits = guess_classes_for_folder(folder)
        if len(hits) != 1:
            which = ", ".join(sorted({n for _, n in hits})) or "none"
            return (f"this file has no 'Experiment' attr (saved before save_metadata) and "
                    f"folder {folder!r} matches {len(hits)} experiment classes ({which}) - "
                    f"use the Plot (png) tab")
        name = hits[0][1]
        guessed = f" GUESS: no Experiment attr; {name} inferred from folder {folder!r}."

    cls, candidates, error = resolve_experiment_class(str(name))
    if cls is None:
        if isinstance(error, ImportError) and "qick" in str(error):
            return NO_QICK_MESSAGE
        if not candidates:
            return f"no file under Experimental_Scripts defines class {name!r} - use the png tab"
        return f"could not import {name} from {candidates[0].name}: {error}"
    ambiguity = ("" if len(candidates) < 2 else
                 f" WARNING: {len(candidates)} files define {name}; used {candidates[0].name}.")

    sig = inspect.signature(cls.display)
    fig_param = next((k for k in ("fig_axs", "fig_ax") if k in sig.parameters), None)
    if "ax" not in sig.parameters and fig_param is None:
        return (f"{name}.display() takes no 'ax' or 'fig_axs' - it cannot draw into the viewer; "
                f"use the Plot (png) tab")

    expt = cls.__new__(cls)                       # bypass __init__: it would mkdir a
    try:                                          # new dated folder and new filenames
        loaded = ExperimentClass.load_data(path)
    except FileBeingSaved:
        return BUSY_MESSAGE
    except Exception as exc:
        return f"cannot read data: {exc}"
    expt.cfg = loaded["config"]
    expt.data = loaded
    expt.titlename = Path(path).stem
    err = _restore_sweep_state(expt, loaded)
    if err:
        return f"{name}: cannot rebuild its sweep settings ({err})"
    # SAFETY: most display() implementations end with plt.savefig(self.iname[:-4]+'.png').
    # Point the whole stem at a temp dir so a replot can NEVER overwrite the archived
    # png (or h5/json) next to the original file.
    stem = os.path.join(tempfile.mkdtemp(prefix="viewer_replot_"), Path(path).stem)
    expt.fname, expt.iname, expt.cname = stem + ".h5", stem + ".png", stem + ".json"

    # plotDisp/block default to True in several displays; pass False only where the
    # signature actually accepts them.
    kwargs = {}
    if "ax" in sig.parameters:
        kwargs["ax"] = ax
    elif fig_param == "fig_ax":
        kwargs[fig_param] = (ax.figure, ax)
    else:
        try:
            count = len(loaded["data"]["Qubit_Readout_List"])
        except Exception:
            count = 1
        kwargs[fig_param] = (ax.figure, _make_axes(ax.figure, max(1, count)))
    var_kw = any(p.kind is p.VAR_KEYWORD for p in sig.parameters.values())
    for key in ("plotDisp", "block"):
        if var_kw or key in sig.parameters:
            kwargs[key] = False

    ax.figure.show = lambda *args, **kw: None     # the viewer's figure has no pyplot window to show
    before = set(plt.get_fignums())
    try:
        expt.display(loaded, **kwargs)
    except Exception as exc:
        return f"{name}.display() failed: {exc}"
    finally:
        for num in set(plt.get_fignums()) - before:
            plt.close(num)                        # no stray pyplot windows
    return (f"replotted {name}.{guessed}{ambiguity} Fit overlays only appear if the fit "
            f"arrays were saved; older files stored data but not fit results, so the "
            f"curve may be bare.")
