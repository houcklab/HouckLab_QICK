"""Experiment Library tab + the experiment-import sandbox.

Browse the ``Experimental_Scripts`` tree, discover ``ExperimentClass``
subclasses, edit a JSON cfg, and run them (or save/load recipes). The
sandbox helpers (``_experiment_import_sandbox`` and the discover/import
functions) stub MUXInitialize/socProxy so legacy experiment files import
without a live connection; they are shared with the two-qubit and pi/2-phase
tabs, which import ``import_experiment_class`` from here.

Depends on state / helpers / widgets only.
"""
from __future__ import annotations

import contextlib
import json
import traceback
from pathlib import Path
from typing import Optional

from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
    QPushButton, QSplitter, QVBoxLayout, QWidget,
)

from ..state import (
    CalibState,
    EXPERIMENTAL_SCRIPTS_DIR,
    RECIPE_DIR,
    SETTING_LAST_RECIPE_PATH,
    get_settings,
)
from ..helpers import build_cfg_for_qubit, dump_pretty, _make_jsonable
from ..widgets import MplCanvas


@contextlib.contextmanager
def _experiment_import_sandbox(soc=None, soccfg=None):
    """Stub MUXInitialize / socProxy in sys.modules during experiment import.

    Legacy experiment files use module-level ``from MUXInitialize import soc``
    (no longer exposed since the refactor) or call ``makeProxy()`` at module
    scope. The sandbox replaces both modules with stubs whose ``soc`` /
    ``soccfg`` attributes hold the GUI's live proxies — so those files import
    cleanly without source changes. Restores the original modules on exit.
    """
    import sys
    import types

    target_names = [
        "WorkingProjects.triangle_lattice_quench.MUXInitialize",
        "WorkingProjects.triangle_lattice_quench.socProxy",
        "WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize",
        "WorkingProjects.Triangle_Lattice_tProcV2.socProxy",
    ]
    saved = {n: sys.modules.get(n) for n in target_names}
    try:
        for n in target_names:
            mod = types.ModuleType(n)
            mod.BaseConfig = {}
            mod.soc = soc
            mod.soccfg = soccfg
            mod.makeProxy = lambda *a, soc=soc, soccfg=soccfg, **kw: (soc, soccfg)
            sys.modules[n] = mod
        yield
    finally:
        for n, prev in saved.items():
            if prev is None:
                sys.modules.pop(n, None)
            else:
                sys.modules[n] = prev


def _experiment_module_name(p: Path) -> str:
    return f"_calibgui_exp_{abs(hash(str(p.resolve())))}"


def discover_experiment_classes(file_path: str) -> list[str]:
    """Return the names of every class defined in ``file_path`` whose MRO
    includes ``ExperimentClass``. Sandbox imports so no hardware connection
    is attempted.
    """
    import importlib.util
    import inspect

    p = Path(file_path)
    if not p.exists() or p.suffix.lower() != ".py":
        return []
    spec = importlib.util.spec_from_file_location(_experiment_module_name(p), str(p))
    if spec is None or spec.loader is None:
        return []
    with _experiment_import_sandbox():
        try:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception:
            return []
    out: list[str] = []
    for name in dir(module):
        if name.startswith("_") or name == "ExperimentClass":
            continue
        obj = getattr(module, name)
        if not inspect.isclass(obj):
            continue
        if obj.__module__ != module.__name__:
            continue  # only classes defined IN this file
        if "ExperimentClass" in (c.__name__ for c in inspect.getmro(obj)):
            out.append(name)
    return sorted(out)


def import_experiment_class(file_path: str, class_name: str,
                             soc=None, soccfg=None):
    """Sandbox-import the file and return the named class.

    If ``soc``/``soccfg`` are provided, the stub MUXInitialize/socProxy modules
    expose them, so experiments that do ``from MUXInitialize import soc`` at
    module scope work without source changes.
    """
    import importlib.util

    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(p)
    spec = importlib.util.spec_from_file_location(
        _experiment_module_name(p) + "_run", str(p)
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load spec for {p}")
    with _experiment_import_sandbox(soc=soc, soccfg=soccfg):
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    cls = getattr(module, class_name, None)
    if cls is None:
        raise AttributeError(f"{p.name} has no class {class_name!r}")
    return cls


class RecipeRunWorker(QThread):
    """Run a recipe end-to-end on a worker thread.

    Steps: import the class, instantiate with the given cfg, ``acquire`` it
    (with a few signature fallbacks to suppress in-acquire matplotlib calls
    where possible), emit ``acquired(expt, data)`` for the GUI thread to do
    ``display(ax=...)``, then optionally call ``save_data(data)``.
    """

    log = pyqtSignal(str)
    acquired = pyqtSignal(object, object)
    saved = pyqtSignal(str)
    failed = pyqtSignal(str)
    finished_ok = pyqtSignal()

    def __init__(self, file_path: str, class_name: str, cfg: dict,
                 soc, soccfg, outer_folder: str,
                 path_label: str, do_save: bool):
        super().__init__()
        self.file_path = file_path
        self.class_name = class_name
        self.cfg = cfg
        self.soc = soc
        self.soccfg = soccfg
        self.outer_folder = outer_folder
        self.path_label = path_label
        self.do_save = do_save

    def _acquire(self, expt):
        """Try a few common acquire() signatures; suppress in-acquire plots."""
        for kwargs in ({"progress": False, "plotDisp": False},
                       {"progress": False},
                       {}):
            try:
                return expt.acquire(**kwargs)
            except TypeError:
                continue
        # Last resort: bare call (the TypeError loop only catches kwarg mismatch).
        return expt.acquire()

    def run(self):
        try:
            self.log.emit(f"Importing {Path(self.file_path).name}::{self.class_name}...")
            cls = import_experiment_class(
                self.file_path, self.class_name,
                soc=self.soc, soccfg=self.soccfg,
            )
            self.log.emit(f"Constructing {self.class_name} ...")
            expt = cls(
                soc=self.soc, soccfg=self.soccfg,
                path=self.path_label, outerFolder=self.outer_folder,
                cfg=self.cfg,
            )
            self.log.emit("acquire() ...")
            data = expt.acquire() if False else self._acquire(expt)
            self.acquired.emit(expt, data)
            if self.do_save and hasattr(expt, "save_data"):
                self.log.emit("save_data() ...")
                try:
                    try:
                        expt.save_data(data=data)
                    except TypeError:
                        expt.save_data(data)
                    self.saved.emit(getattr(expt, "fname", "(saved)"))
                except Exception as exc:
                    self.log.emit(f"save_data failed: {exc}")
            self.finished_ok.emit()
        except Exception as exc:
            self.failed.emit(f"{exc}\n\n{traceback.format_exc()}")


class ExperimentLibraryTab(QWidget):
    """Browse Experimental_Scripts/, pick a class, edit its cfg, run.

    Saves the (file, class, cfg, notes) bundle as a JSON "recipe" so the
    same run can be replayed later without editing source files.
    """

    name = "Experiment Library"

    def __init__(self, state: CalibState, get_main, parent=None):
        super().__init__(parent)
        self.state = state
        self.get_main = get_main
        self.worker: Optional[RecipeRunWorker] = None
        self._current_file: Optional[Path] = None
        self._current_class: Optional[str] = None

        # ---- left: file list + class list + docstring ----
        self.file_list = QListWidget()
        self.file_list.itemSelectionChanged.connect(self._on_file_selected)
        self.refresh_files_btn = QPushButton("Refresh file list")
        self.refresh_files_btn.clicked.connect(self._populate_file_list)

        self.class_list = QListWidget()
        self.class_list.itemSelectionChanged.connect(self._on_class_selected)

        self.class_info = QPlainTextEdit()
        self.class_info.setReadOnly(True)
        self.class_info.setMaximumHeight(140)
        f = QFont(); f.setStyleHint(QFont.Monospace); f.setFamily("Consolas")
        self.class_info.setFont(f)
        self.class_info.setPlaceholderText("Class docstring will appear here.")

        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("Files (Experimental_Scripts/):"))
        left_layout.addWidget(self.file_list, 2)
        left_layout.addWidget(self.refresh_files_btn)
        left_layout.addWidget(QLabel("ExperimentClass subclasses in file:"))
        left_layout.addWidget(self.class_list, 1)
        left_layout.addWidget(QLabel("Class docstring:"))
        left_layout.addWidget(self.class_info, 1)
        left_w = QWidget(); left_w.setLayout(left_layout)

        # ---- middle: recipe metadata + cfg editor + run row ----
        self.recipe_name_edit = QLineEdit()
        self.recipe_name_edit.setPlaceholderText("recipe name")
        self.notes_edit = QLineEdit()
        self.notes_edit.setPlaceholderText("optional notes")
        recipe_form = QFormLayout()
        recipe_form.addRow("Recipe name:", self.recipe_name_edit)
        recipe_form.addRow("Notes:", self.notes_edit)
        recipe_form_w = QWidget(); recipe_form_w.setLayout(recipe_form)

        self.cfg_editor = QPlainTextEdit()
        self.cfg_editor.setFont(f)
        self.cfg_editor.setPlaceholderText(
            'cfg JSON. "Seed from current state" fills in res_freqs, '
            "qubit_freqs, FF_Qubits, ... for the active target qubit."
        )

        self.seed_btn = QPushButton("Seed cfg from current state")
        self.seed_btn.clicked.connect(self._on_seed)
        self.save_recipe_btn = QPushButton("Save recipe...")
        self.save_recipe_btn.clicked.connect(self._on_save_recipe)
        self.load_recipe_btn = QPushButton("Load recipe...")
        self.load_recipe_btn.clicked.connect(self._on_load_recipe)
        recipe_btn_row = QHBoxLayout()
        recipe_btn_row.addWidget(self.seed_btn)
        recipe_btn_row.addWidget(self.save_recipe_btn)
        recipe_btn_row.addWidget(self.load_recipe_btn)
        recipe_btn_w = QWidget(); recipe_btn_w.setLayout(recipe_btn_row)

        self.do_save_check = QCheckBox("save_data")
        self.do_save_check.setChecked(True)
        self.do_display_check = QCheckBox("display")
        self.do_display_check.setChecked(True)
        self.run_btn = QPushButton("Run")
        self.run_btn.setStyleSheet("font-weight: bold;")
        self.run_btn.clicked.connect(self._on_run)
        self.stop_lbl = QLabel("")
        self.stop_lbl.setStyleSheet("color: #888;")

        run_row = QHBoxLayout()
        run_row.addWidget(self.do_save_check)
        run_row.addWidget(self.do_display_check)
        run_row.addStretch(1)
        run_row.addWidget(self.stop_lbl)
        run_row.addWidget(self.run_btn)
        run_row_w = QWidget(); run_row_w.setLayout(run_row)

        mid_layout = QVBoxLayout()
        mid_layout.addWidget(recipe_form_w)
        mid_layout.addWidget(recipe_btn_w)
        mid_layout.addWidget(QLabel("cfg (JSON):"))
        mid_layout.addWidget(self.cfg_editor, 1)
        mid_layout.addWidget(run_row_w)
        mid_w = QWidget(); mid_w.setLayout(mid_layout)

        # ---- right: plot canvas + log ----
        self.canvas = MplCanvas(self, height=4.0)
        self.toolbar = NavigationToolbar(self.canvas, self)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(f)
        self.log.setPlaceholderText("Run progress / errors appear here.")

        right_layout = QVBoxLayout()
        right_layout.addWidget(self.toolbar)
        right_layout.addWidget(self.canvas, 2)
        right_layout.addWidget(QLabel("Log:"))
        right_layout.addWidget(self.log, 1)
        right_w = QWidget(); right_w.setLayout(right_layout)

        splitter = QSplitter()
        splitter.addWidget(left_w)
        splitter.addWidget(mid_w)
        splitter.addWidget(right_w)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 3)

        outer = QVBoxLayout(self)
        outer.addWidget(splitter, 1)

        self._populate_file_list()

    # ---- file / class discovery ----

    def _populate_file_list(self):
        self.file_list.clear()
        if not EXPERIMENTAL_SCRIPTS_DIR.is_dir():
            self.log.appendPlainText(
                f"[no Experimental_Scripts dir at {EXPERIMENTAL_SCRIPTS_DIR}]"
            )
            return
        files: list[Path] = []
        for p in EXPERIMENTAL_SCRIPTS_DIR.rglob("*.py"):
            if p.name.startswith("__") or "__pycache__" in p.parts:
                continue
            files.append(p)
        files.sort()
        for p in files:
            try:
                rel = p.relative_to(EXPERIMENTAL_SCRIPTS_DIR)
            except ValueError:
                rel = p
            item = QListWidgetItem(str(rel))
            item.setData(Qt.UserRole, str(p))
            self.file_list.addItem(item)
        self.log.appendPlainText(f"Loaded {len(files)} Python files.")

    def _on_file_selected(self):
        items = self.file_list.selectedItems()
        if not items:
            return
        path = Path(items[0].data(Qt.UserRole))
        self._current_file = path
        self.class_list.clear()
        self.class_info.clear()
        try:
            classes = discover_experiment_classes(str(path))
        except Exception as exc:
            self.log.appendPlainText(f"[discovery failed] {path.name}: {exc}")
            return
        for c in classes:
            self.class_list.addItem(c)
        if not classes:
            self.log.appendPlainText(f"[no ExperimentClass in {path.name}]")

    def _on_class_selected(self):
        items = self.class_list.selectedItems()
        if not items:
            return
        cls_name = items[0].text()
        self._current_class = cls_name
        if self._current_file is None:
            return
        try:
            cls = import_experiment_class(str(self._current_file), cls_name)
            doc = (cls.__doc__ or "(no docstring)").strip()
            self.class_info.setPlainText(doc)
        except Exception as exc:
            self.class_info.setPlainText(f"(import failed: {exc})")
        # Suggest a recipe name if the field is empty
        if not self.recipe_name_edit.text().strip():
            self.recipe_name_edit.setText(cls_name)

    # ---- cfg seeding ----

    def _on_seed(self):
        try:
            cfg = build_cfg_for_qubit(self.state, str(self.state.target_qubit))
        except Exception as exc:
            QMessageBox.warning(
                self, "Seed failed",
                f"Could not build single-qubit cfg: {exc}\n\n"
                "Load a Qubit_Parameters file first, or pick a target qubit.",
            )
            return
        try:
            text = json.dumps(_make_jsonable(cfg), indent=2)
        except Exception as exc:
            QMessageBox.critical(self, "JSON error", str(exc))
            return
        self.cfg_editor.setPlainText(text)

    # ---- recipe save / load ----

    def _on_save_recipe(self):
        if self._current_class is None or self._current_file is None:
            QMessageBox.information(self, "No class", "Pick a class first.")
            return
        try:
            cfg = json.loads(self.cfg_editor.toPlainText() or "{}")
        except Exception as exc:
            QMessageBox.warning(self, "Invalid cfg JSON", str(exc))
            return
        name = self.recipe_name_edit.text().strip() or self._current_class
        RECIPE_DIR.mkdir(parents=True, exist_ok=True)
        default_path = str(RECIPE_DIR / f"{name}.json")
        path, _ = QFileDialog.getSaveFileName(
            self, "Save recipe", default_path, "JSON (*.json)"
        )
        if not path:
            return
        from datetime import datetime
        recipe = {
            "name": name,
            "file": str(self._current_file),
            "class": self._current_class,
            "cfg": cfg,
            "notes": self.notes_edit.text(),
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        try:
            with open(path, "w") as fh:
                dump_pretty(recipe, fh)
            get_settings().setValue(SETTING_LAST_RECIPE_PATH, path)
            self.log.appendPlainText(f"Saved recipe to {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

    def _on_load_recipe(self):
        last = str(get_settings().value(SETTING_LAST_RECIPE_PATH, "", type=str) or "")
        start_dir = str(Path(last).parent) if last and Path(last).exists() else str(RECIPE_DIR)
        path, _ = QFileDialog.getOpenFileName(
            self, "Load recipe", start_dir, "JSON (*.json)"
        )
        if not path:
            return
        try:
            with open(path) as fh:
                recipe = json.load(fh)
        except Exception as exc:
            QMessageBox.critical(self, "Load failed", str(exc))
            return
        self.recipe_name_edit.setText(recipe.get("name", ""))
        self.notes_edit.setText(recipe.get("notes", ""))
        self.cfg_editor.setPlainText(json.dumps(recipe.get("cfg", {}), indent=2))
        # Try to select the file & class in the list widgets.
        target = recipe.get("file")
        if target:
            for i in range(self.file_list.count()):
                if self.file_list.item(i).data(Qt.UserRole) == target:
                    self.file_list.setCurrentRow(i)
                    break
        target_cls = recipe.get("class")
        if target_cls:
            QApplication.processEvents()  # let _on_file_selected populate class_list
            for i in range(self.class_list.count()):
                if self.class_list.item(i).text() == target_cls:
                    self.class_list.setCurrentRow(i)
                    break
        get_settings().setValue(SETTING_LAST_RECIPE_PATH, path)
        self.log.appendPlainText(f"Loaded recipe from {path}")

    # ---- run ----

    def _on_run(self):
        if self.worker is not None and self.worker.isRunning():
            return
        if self._current_file is None or self._current_class is None:
            QMessageBox.information(self, "No selection", "Pick a file and class first.")
            return
        if not self.state.is_connected():
            QMessageBox.warning(self, "Not connected", "Connect to the RFSoC first.")
            return
        try:
            cfg = json.loads(self.cfg_editor.toPlainText() or "{}")
        except Exception as exc:
            QMessageBox.warning(self, "Invalid cfg JSON", str(exc))
            return

        self.canvas.reset()
        self.log.clear()
        self.run_btn.setEnabled(False)
        self.stop_lbl.setText("running...")

        path_label = self.recipe_name_edit.text().strip() or self._current_class

        self.worker = RecipeRunWorker(
            file_path=str(self._current_file),
            class_name=self._current_class,
            cfg=cfg,
            soc=self.state.soc, soccfg=self.state.soccfg,
            outer_folder=self.state.outer_folder,
            path_label=path_label,
            do_save=self.do_save_check.isChecked(),
        )
        self.worker.log.connect(self.log.appendPlainText)
        self.worker.acquired.connect(self._on_acquired)
        self.worker.saved.connect(lambda p: self.log.appendPlainText(f"Saved -> {p}"))
        self.worker.failed.connect(self._on_failed)
        self.worker.finished_ok.connect(self._on_finished)
        self.worker.start()

    def _on_acquired(self, expt, data):
        if not self.do_display_check.isChecked():
            return
        if not hasattr(expt, "display"):
            self.log.appendPlainText("(no display() on this class)")
            return
        # Try the signatures we've seen across the codebase.
        for kwargs in (
            {"data": data, "ax": self.canvas.ax, "plotDisp": False},
            {"data": data, "ax": self.canvas.ax},
            {"data": data},
        ):
            try:
                expt.display(**kwargs)
                self.canvas.draw()
                return
            except TypeError:
                continue
            except Exception as exc:
                self.log.appendPlainText(f"display() raised: {exc}")
                traceback.print_exc()
                return
        self.log.appendPlainText("display(): could not match any known signature")

    def _on_failed(self, msg: str):
        first, _, rest = msg.partition("\n")
        self.log.appendPlainText(f"[FAIL] {first}")
        for line in rest.rstrip().splitlines():
            self.log.appendPlainText(f"       {line}")
        self.run_btn.setEnabled(True)
        self.stop_lbl.setText("")
        self.worker = None

    def _on_finished(self):
        self.log.appendPlainText("--- done ---")
        self.run_btn.setEnabled(True)
        self.stop_lbl.setText("")
        self.worker = None
