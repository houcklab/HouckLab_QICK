"""Two-qubit chevron calibration tab.

Pick (q_i, q_j) and a sweep qubit, set the sweep params, and run a
``GainSweepOscillationsR`` chevron on a worker thread to extract the coupling
rate g (MHz). Shares ``import_experiment_class`` with the experiment library.

Depends on state / helpers / widgets / experiment_library.
"""
from __future__ import annotations

import traceback
from typing import Any, Optional

from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QMessageBox,
    QPlainTextEdit, QPushButton, QSplitter, QVBoxLayout, QWidget,
)

from ..state import CalibState, EXPERIMENTAL_SCRIPTS_DIR
from ..helpers import _build_resolve_ramp
from ..widgets import MplCanvas, ParamForm, _agent_set_combo
from .experiment_library import import_experiment_class


class TwoQubitChevronWorker(QThread):
    """Run ``GainSweepOscillationsR`` for one (q_i, q_j) pair on a worker thread.

    The class is sandbox-imported with ``soc`` injected, so its module-level
    ``from MUXInitialize import soc`` (and the subsequent ``soc.reset_gens()``
    in ``set_up_instance``) get the real proxy.
    """

    log = pyqtSignal(str)
    finished_ok = pyqtSignal(object, object)  # expt, data
    failed = pyqtSignal(str)

    def __init__(self, soc, soccfg, outer_folder: str, cfg: dict,
                 q_i: int, q_j: int, sweep_qubit: int):
        super().__init__()
        self.soc = soc
        self.soccfg = soccfg
        self.outer_folder = outer_folder
        self.cfg = cfg
        self.q_i = int(q_i)
        self.q_j = int(q_j)
        self.sweep_qubit = int(sweep_qubit)

    def run(self):
        try:
            file_path = str(
                EXPERIMENTAL_SCRIPTS_DIR / "mGainSweepQubitOscillationsR.py"
            )
            self.log.emit(
                f"Importing GainSweepOscillationsR for Q{self.q_i}-Q{self.q_j} "
                f"(sweep Q{self.sweep_qubit})..."
            )
            cls = import_experiment_class(
                file_path, "GainSweepOscillationsR",
                soc=self.soc, soccfg=self.soccfg,
            )

            # SweepExperimentND.acquire() line ~215 has buggy parens:
            #   if (plotDisp or plotSave) and (len <= 1) or (last_x_idx):
            # which means the plot branch fires after every row of a 2D sweep
            # regardless of plotDisp/plotSave. That ends in
            # ``fig.canvas.draw()`` from this worker thread on a pyplot-managed
            # Qt5Agg figure -> Qt event-loop deadlock = window freeze.
            # Fix locally: subclass and redirect display() to a headless Agg
            # figure so the base class's plot calls are harmless. (Upstream
            # fix would be one set of parens in SweepExperimentND.py.)
            from matplotlib.figure import Figure as _BareFigure
            from matplotlib.backends.backend_agg import FigureCanvasAgg

            class _GainSweepForGui(cls):
                def display(self, data=None, plotDisp=False, figNum=1,
                            plotSave=True, block=False, fig_axs=None):
                    fig = _BareFigure()
                    FigureCanvasAgg(fig)  # attach Agg canvas; no Qt involvement
                    ax = fig.add_subplot(111)
                    return fig, [ax]

                def _update_fig(self, data, fig, axs):
                    pass  # no-op; we render after acquire on the GUI canvas

            self.log.emit("Constructing experiment...")
            expt = _GainSweepForGui(
                soc=self.soc, soccfg=self.soccfg,
                path=f"GainSweepOscillationsR_Q{self.q_i}{self.q_j}",
                outerFolder=self.outer_folder,
                cfg=self.cfg,
            )
            self.log.emit("acquire() ...")
            data = None
            for kwargs in ({"progress": False, "plotDisp": False, "plotSave": False},
                           {"progress": False, "plotDisp": False},
                           {"progress": False}):
                try:
                    data = expt.acquire(**kwargs)
                    break
                except TypeError:
                    continue
            if data is None:
                data = expt.acquire()
            self.finished_ok.emit(expt, data)
        except Exception as exc:
            self.failed.emit(f"{exc}\n\n{traceback.format_exc()}")


class TwoQubitCalibTab(QWidget):
    """Two-qubit chevron calibration. Pick (q_i, q_j) and a sweep qubit, set
    sweep params, hit Run. Result is the coupling rate g (MHz) and the FF
    gain on the swept qubit at which the two come into resonance — same as
    ``Run_Experiments/calibration_scripts/coupling_strength_calibration.py``.

    Apply mirrors the (coupling, resonance_gain) pair into the readout-group
    entry for each qubit (``entries[q]['TwoQubit'][partner]``) symmetrically.
    No existing reader consumes that slot — it's informational state the
    user can persist via Save on the Qubit Parameters tab.
    """

    name = "Two-Qubit Calib"

    def __init__(self, state: CalibState, get_main, parent=None):
        super().__init__(parent)
        self.state = state
        self.get_main = get_main
        self.worker: Optional[TwoQubitChevronWorker] = None
        self._last_data: Any = None
        self._last_expt: Any = None
        self._last_pair: Optional[tuple[int, int, int]] = None  # (q_i, q_j, sweep_qubit)
        self._last_ramp_state: Optional[str] = None  # ramp used for the last chevron

        # ---- readout/drive group selectors (item 7: mirror AutoCalibTab) ----
        self.readout_group_combo = QComboBox()
        self.readout_group_combo.setMinimumWidth(160)
        self.readout_group_combo.setToolTip(
            "Readout point for this chevron (sets state.current_readout_group)."
        )
        self.readout_group_combo.currentIndexChanged.connect(
            self._on_readout_group_changed
        )
        self.drive_group_combo = QComboBox()
        self.drive_group_combo.setMinimumWidth(160)
        self.drive_group_combo.setToolTip(
            "Drive (Pulse) point. Optional; empty = use readout group's Pulse_FF."
        )
        self.drive_group_combo.currentIndexChanged.connect(
            self._on_drive_group_changed
        )
        self.ramp_state_combo = QComboBox()
        self.ramp_state_combo.setMinimumWidth(140)
        self.ramp_state_combo.setToolTip(
            "Optional Ramp_State. Empty = sweep the swept qubit's FF from DC baseline "
            "(bare resonance). Selected = hold every qubit at that ramp's Expt_FF and "
            "sweep only the swept qubit's FF around it -- measures the swap AT that ramp."
        )
        group_row = QHBoxLayout()
        group_row.addWidget(QLabel("Readout group:"))
        group_row.addWidget(self.readout_group_combo)
        group_row.addSpacing(16)
        group_row.addWidget(QLabel("Drive group:"))
        group_row.addWidget(self.drive_group_combo)
        group_row.addSpacing(16)
        group_row.addWidget(QLabel("Ramp_State:"))
        group_row.addWidget(self.ramp_state_combo)
        group_row.addStretch(1)
        group_w = QWidget(); group_w.setLayout(group_row)

        # ---- pair selector ----
        pair_box = QGroupBox("Pair selection")
        pair_form = QFormLayout(pair_box)
        self.qi_combo = QComboBox()
        self.qj_combo = QComboBox()
        self.sweep_combo = QComboBox()
        self.sweep_combo.addItems(["Q_j (second)", "Q_i (first)"])
        for cb in (self.qi_combo, self.qj_combo):
            cb.currentIndexChanged.connect(self._validate_pair)
        pair_form.addRow("Q_i:", self.qi_combo)
        pair_form.addRow("Q_j:", self.qj_combo)
        pair_form.addRow("Swept qubit (FF varies):", self.sweep_combo)
        # Preset pair shortcut
        preset_row = QHBoxLayout()
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("(presets — pick to fill Q_i / Q_j)", None)
        # rungs and legs from coupling_strength_calibration.py
        for label, qi, qj in [
            ("Rung 1-2", 1, 2), ("Rung 2-3", 2, 3), ("Rung 3-4", 3, 4),
            ("Rung 4-5", 4, 5), ("Rung 5-6", 5, 6), ("Rung 6-7", 6, 7),
            ("Rung 7-8", 7, 8),
            ("Leg 1-3", 1, 3), ("Leg 2-4", 2, 4), ("Leg 3-5", 3, 5),
            ("Leg 4-6", 4, 6), ("Leg 5-7", 5, 7), ("Leg 6-8", 6, 8),
        ]:
            self.preset_combo.addItem(label, (qi, qj))
        self.preset_combo.currentIndexChanged.connect(self._on_preset)
        preset_row.addWidget(QLabel("Preset:"))
        preset_row.addWidget(self.preset_combo, 1)
        preset_w = QWidget(); preset_w.setLayout(preset_row)
        pair_form.addRow(preset_w)

        # ---- sweep params ----
        self.param_form = ParamForm("Sweep parameters", [
            ("gainStart",     "FF gain start (DAC)",    "int",   -1000),
            ("gainStop",      "FF gain stop (DAC)",     "int",    1000),
            ("gainNumPoints", "Num gain points",        "int",    11),
            ("expts",         "Num time points",        "int",    71),
            ("start",         "Start (samples)",        "int",    1),
            ("step",          "Step (samples)",         "int",    7),
            ("reps",          "Repetitions",            "int",    200),
            ("relax_delay",   "Relax delay (us)",       "float",  150.0),
        ])

        # ---- buttons + result ----
        self.run_btn = QPushButton("Run chevron")
        self.run_btn.setStyleSheet("font-weight: bold;")
        self.run_btn.clicked.connect(self._on_run)
        self.apply_btn = QPushButton("Apply -> Qubit_Parameters")
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self._on_apply)
        self.apply_ramp_btn = QPushButton("Apply -> Ramp Expt_FF")
        self.apply_ramp_btn.setToolTip(
            "Write the fitted resonance gain into the selected Ramp_State's Expt_FF "
            "for the swept qubit (in memory; Save Qubit_Parameters JSON to persist)."
        )
        self.apply_ramp_btn.setEnabled(False)
        self.apply_ramp_btn.clicked.connect(self._on_apply_ramp)
        self.result_lbl = QLabel("(no result)")
        self.result_lbl.setStyleSheet("font-weight: bold; color: #555;")
        run_row = QHBoxLayout()
        run_row.addWidget(self.run_btn)
        run_row.addWidget(self.apply_btn)
        run_row.addWidget(self.apply_ramp_btn)
        run_row.addStretch(1)
        run_w = QWidget(); run_w.setLayout(run_row)

        # ---- canvas + log ----
        self.canvas = MplCanvas(self, height=4.5)
        self.toolbar = NavigationToolbar(self.canvas, self)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        f = QFont(); f.setStyleHint(QFont.Monospace); f.setFamily("Consolas")
        self.log.setFont(f)
        self.log.setPlaceholderText("Chevron progress / fit results appear here.")

        # ---- layout (group selectors on top, splitter under) ----
        left_layout = QVBoxLayout()
        left_layout.addWidget(pair_box)
        left_layout.addWidget(self.param_form)
        left_layout.addWidget(run_w)
        left_layout.addWidget(self.result_lbl)
        left_layout.addStretch(1)
        # Item 9 / item 2: do NOT cap the left pane width — let the splitter
        # decide. Users want to be able to widen the left side freely.
        left_w = QWidget(); left_w.setLayout(left_layout)

        right_layout = QVBoxLayout()
        right_layout.addWidget(self.toolbar)
        right_layout.addWidget(self.canvas, 2)
        right_layout.addWidget(QLabel("Log:"))
        right_layout.addWidget(self.log, 1)
        right_w = QWidget(); right_w.setLayout(right_layout)

        splitter = QSplitter()
        splitter.addWidget(left_w)
        splitter.addWidget(right_w)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        outer = QVBoxLayout(self)
        outer.addWidget(group_w)
        outer.addWidget(splitter, 1)

        self.refresh_qubit_combos()

    # ---- helpers ----

    def refresh_qubit_combos(self):
        """Repopulate Q_i / Q_j from the current ``state.n_qubits``."""
        for cb in (self.qi_combo, self.qj_combo):
            cb.blockSignals(True)
            cb.clear()
            for i in range(self.state.n_qubits):
                cb.addItem(f"Q{i + 1}", i + 1)
            cb.blockSignals(False)
        if self.qi_combo.count() > 0:
            self.qi_combo.setCurrentIndex(0)
        if self.qj_combo.count() > 1:
            self.qj_combo.setCurrentIndex(1)
        self._validate_pair()

    def _validate_pair(self):
        qi = self.qi_combo.currentData()
        qj = self.qj_combo.currentData()
        if qi is not None and qj is not None and qi == qj:
            self.result_lbl.setText("Q_i and Q_j must differ.")
            self.run_btn.setEnabled(False)
        else:
            self.result_lbl.setText("(no result)" if self._last_data is None
                                    else self.result_lbl.text())
            self.run_btn.setEnabled(True)

    def _on_preset(self, idx: int):
        data = self.preset_combo.itemData(idx)
        if data is None:
            return
        qi, qj = data
        for cb, target in ((self.qi_combo, qi), (self.qj_combo, qj)):
            for i in range(cb.count()):
                if cb.itemData(i) == target:
                    cb.setCurrentIndex(i)
                    break

    # ---- group selectors (mirror AutoCalibTab) ----

    def _on_readout_group_changed(self, _idx: int) -> None:
        self.state.current_readout_group = self.readout_group_combo.currentText() or ""

    def _on_drive_group_changed(self, _idx: int) -> None:
        data = self.drive_group_combo.currentData()
        self.state.current_drive_group = data or ""

    def refresh_groups_from_state(self) -> None:
        """Repopulate readout/drive combos from state.qubit_parameters_json.

        Called by MainWindow._on_qubit_params_loaded after the params JSON
        is (re)loaded. Same wiring as AutoCalibTab; the two tabs each own
        their own visible combos but share state.current_readout_group.
        """
        jd = self.state.qubit_parameters_json or {}
        readout_groups = list((jd.get("readout_groups") or {}).keys())
        drive_groups = list((jd.get("drive_groups") or {}).keys())

        self.readout_group_combo.blockSignals(True)
        self.readout_group_combo.clear()
        for n in readout_groups:
            self.readout_group_combo.addItem(n)
        # If state already has a current group (set by the AutoCalib combo),
        # mirror it here; else default to first.
        cur = self.state.current_readout_group or ""
        if cur and readout_groups and cur in readout_groups:
            self.readout_group_combo.setCurrentIndex(readout_groups.index(cur))
        elif readout_groups:
            self.readout_group_combo.setCurrentIndex(0)
        self.readout_group_combo.blockSignals(False)

        self.drive_group_combo.blockSignals(True)
        self.drive_group_combo.clear()
        self.drive_group_combo.addItem("(readout)", "")
        for n in drive_groups:
            self.drive_group_combo.addItem(n, n)
        self.drive_group_combo.setCurrentIndex(0)
        self.drive_group_combo.blockSignals(False)

        # Ramp_State entries (any entry in any ramp_groups), like the Pi2 Phase tab.
        ramp_entries = [e for grp in (jd.get("ramp_groups") or {}).values()
                        if isinstance(grp, dict) for e in (grp.get("entries") or {})]
        self.ramp_state_combo.blockSignals(True)
        self.ramp_state_combo.clear()
        self.ramp_state_combo.addItem("(none)", "")
        for n in ramp_entries:
            self.ramp_state_combo.addItem(n, n)
        self.ramp_state_combo.setCurrentIndex(0)
        self.ramp_state_combo.blockSignals(False)

    # ---- run / apply ----

    def _on_run(self):
        if self.worker is not None and self.worker.isRunning():
            return
        if not self.state.is_connected():
            QMessageBox.warning(self, "Not connected",
                                "Connect to the RFSoC first.")
            return
        qi = int(self.qi_combo.currentData())
        qj = int(self.qj_combo.currentData())
        if qi == qj:
            QMessageBox.information(self, "Pick two different qubits",
                                    "Q_i and Q_j must differ.")
            return
        sweep_qubit = qj if self.sweep_combo.currentIndex() == 0 else qi
        ramp_state = str(self.ramp_state_combo.currentData() or "") or None
        overrides = self.param_form.values()

        try:
            cfg = self.state.build_two_qubit_chevron_config(
                qi, qj, sweep_qubit, ramp_state=ramp_state, overrides=overrides,
            )
        except Exception as exc:
            QMessageBox.critical(
                self, "Cfg build failed",
                f"Could not build chevron cfg:\n\n{exc}\n\n"
                "Make sure both qubits have entries in Qubit_Parameters.",
            )
            return

        self.canvas.reset()
        self.log.clear()
        self.run_btn.setEnabled(False)
        self.apply_btn.setEnabled(False)
        self.result_lbl.setText(f"Running Q{qi}-Q{qj} (sweep Q{sweep_qubit})...")
        self._last_pair = (qi, qj, sweep_qubit)
        self._last_ramp_state = ramp_state
        self.apply_ramp_btn.setEnabled(False)
        if ramp_state:
            ffq = cfg.get("FF_Qubits", {})
            full_expt = [ffq.get(str(k), {}).get("Gain_Expt") for k in range(1, len(ffq) + 1)]
            g_expt = ffq.get(str(sweep_qubit), {}).get("Gain_Expt")
            self.log.appendPlainText(
                f"Holding all qubits at Ramp_State '{ramp_state}' Expt_FF = {full_expt}")
            self.log.appendPlainText(
                f"Sweeping only Q{sweep_qubit}; its Expt_FF gain = {g_expt} "
                f"-- center the gain sweep there.")

        self.worker = TwoQubitChevronWorker(
            soc=self.state.soc, soccfg=self.state.soccfg,
            outer_folder=self.state.outer_folder,
            cfg=cfg, q_i=qi, q_j=qj, sweep_qubit=sweep_qubit,
        )
        self.worker.log.connect(self.log.appendPlainText)
        self.worker.finished_ok.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    # Measurement-Agent hook: run this calibration without UI clicks.
    AGENT_ACTION = "two_qubit_chevron"
    AGENT_PARAMS = ("q_i (chip int), q_j (chip int), sweep_qubit (chip int, default q_j), "
                    "ramp_state (str or null); sweep sizes: gainStart, gainStop, "
                    "gainNumPoints, expts, start, step, reps (int), relax_delay (float)")

    def agent_run(self, params: dict) -> str:
        """Set the pair/sweep/ramp controls from agent params and trigger the normal
        run. Returns a one-line status (raises nothing the caller can't show)."""
        qi = int(params["q_i"]); qj = int(params["q_j"])
        sweep = int(params.get("sweep_qubit", qj))
        ramp = params.get("ramp_state")
        if not _agent_set_combo(self.qi_combo, qi):
            return f"Q_i {qi} not in the pair list"
        if not _agent_set_combo(self.qj_combo, qj):
            return f"Q_j {qj} not in the pair list"
        self.sweep_combo.setCurrentIndex(0 if sweep == qj else 1)
        if ramp is not None:
            _agent_set_combo(self.ramp_state_combo, str(ramp))
        applied = self.param_form.apply(params)
        self._on_run()
        extra = f", set {applied}" if applied else ""
        return f"chevron Q{qi}-Q{qj} (sweep Q{sweep}, ramp {ramp}{extra})"

    def _on_finished(self, expt, data):
        self._last_expt = expt
        self._last_data = data
        try:
            self._render(expt, data)
        except Exception:
            traceback.print_exc()
            self.log.appendPlainText("Render failed (see traceback in console).")

        # Summarise the fit
        coupling_str, gain_str = self._extract_summary(data)
        qi, qj, sweep_qubit = self._last_pair
        self.result_lbl.setText(
            f"Q{qi}-Q{qj} (sweep Q{sweep_qubit}): {coupling_str}, gain {gain_str}"
        )
        self.log.appendPlainText(
            f"--- DONE Q{qi}-Q{qj}: coupling = {coupling_str}, "
            f"resonance gain = {gain_str} ---"
        )
        self.run_btn.setEnabled(True)
        self.apply_btn.setEnabled(True)
        self.apply_ramp_btn.setEnabled(bool(self._last_ramp_state))
        self.worker = None

    def _on_failed(self, msg: str):
        first, _, rest = msg.partition("\n")
        self.log.appendPlainText(f"[FAIL] {first}")
        for line in rest.rstrip().splitlines():
            self.log.appendPlainText(f"       {line}")
        self.result_lbl.setText("FAILED")
        self.run_btn.setEnabled(True)
        self.apply_btn.setEnabled(False)
        self.worker = None

    def _render(self, expt, data):
        """Render the two-readout chevron heatmaps with fit overlay."""
        import numpy as np
        d = data["data"]
        Z = d.get("population_corrected")
        if Z is None:
            self.log.appendPlainText("(no population_corrected in data)")
            return
        time = np.asarray(d.get("expt_samples", d.get("expt_samples2", [])))
        gains = np.asarray(d.get("Gain_Expt", d.get("Gain_BS", [])))
        n_ros = len(Z)
        # Two side-by-side panels, one per readout.
        self.canvas.fig.clf()
        # One shared color scale + single colorbar across both readouts.
        Zall = np.asarray(Z, float)
        finite = Zall[np.isfinite(Zall)]
        vmin, vmax = (float(finite.min()), float(finite.max())) if finite.size else (0.0, 1.0)
        if vmin == vmax:
            vmax = vmin + 1e-9
        axs, ims = [], []
        for r in range(n_ros):
            ax = self.canvas.fig.add_subplot(1, n_ros, r + 1)
            mat = np.asarray(Z[r])
            extent = [time[0], time[-1], gains[0], gains[-1]] if len(time) and len(gains) else None
            im = ax.imshow(
                mat, aspect="auto", origin="lower",
                extent=extent, interpolation="none", vmin=vmin, vmax=vmax,
            )
            ims.append(im)
            ax.set_title(f"RO {r}")
            ax.set_xlabel("samples (0.291 ns)")
            if r == 0:
                ax.set_ylabel("FF gain (DAC)")
            # Fit overlay if available
            popt = (d.get("popt_list") or [None] * n_ros)[r]
            perr = (d.get("perr_list") or [None] * n_ros)[r]
            try:
                if popt is not None and not (isinstance(popt, float) and np.isnan(popt)):
                    g_lo, g_hi = float(gains[0]), float(gains[-1])
                    g_lin = np.linspace(g_lo, g_hi, 80)
                    # popt = [center_gain, ?, g_MHz, ?, ...]; centre line + g
                    center_gain = float(popt[0])
                    g_MHz = float(popt[2])
                    err = float(perr[2]) if perr is not None else float("nan")
                    ax.axhline(center_gain, color="red", lw=2,
                               label=f"FF = {center_gain:.0f}")
                    ax.legend(
                        loc="upper right", fontsize=9,
                        title=f"g = {g_MHz:.2f} ± {err:.2f} MHz",
                    )
            except Exception:
                pass
            axs.append(ax)
        # Shared colorbar reserves its own space; skip tight_layout (it warns/fights it).
        self.canvas.fig.colorbar(ims[-1], ax=axs, label="population (corr.)")
        self.canvas.draw()

    @staticmethod
    def _extract_summary(data):
        d = data["data"]
        popts = d.get("popt_list") or []
        if not popts:
            return "(no fit)", "(n/a)"
        couplings = []
        gains = []
        for p in popts:
            try:
                couplings.append(float(p[2]))
                gains.append(float(p[0]))
            except Exception:
                continue
        if not couplings:
            return "(no fit)", "(n/a)"
        avg_c = sum(couplings) / len(couplings)
        avg_g = sum(gains) / len(gains)
        return f"g = {avg_c:.2f} MHz", f"{avg_g:.0f}"

    def _on_apply(self):
        if self._last_data is None or self._last_pair is None:
            return
        d = self._last_data["data"]
        popts = d.get("popt_list") or []
        if not popts:
            QMessageBox.warning(self, "No fit", "Cannot apply: chevron fit was not produced.")
            return
        couplings = [float(p[2]) for p in popts if hasattr(p, "__getitem__")]
        gains = [float(p[0]) for p in popts if hasattr(p, "__getitem__")]
        if not couplings:
            QMessageBox.warning(self, "No fit", "popt_list contains no usable rows.")
            return
        from datetime import datetime
        avg_coupling = sum(couplings) / len(couplings)
        avg_gain = sum(gains) / len(gains)
        qi, qj, sweep_qubit = self._last_pair
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        record = {
            "coupling_MHz": avg_coupling,
            "resonance_gain": avg_gain,
            "swept_qubit": sweep_qubit,
            "calibrated_at": ts,
        }
        # Stash on the readout-group entry. The JSON schema doesn't have a
        # canonical TwoQubit slot; no existing reader consumes this — it's
        # informational state the user can persist via Save.
        jd = self.state.qubit_parameters_json or {}
        rg = self.state.current_readout_group or ""
        for q, partner in ((qi, qj), (qj, qi)):
            if not jd or not rg:
                break
            entry = (jd.get("readout_groups", {})
                       .get(rg, {})
                       .get("entries", {})
                       .get(str(q)))
            if isinstance(entry, dict):
                entry.setdefault("TwoQubit", {})[str(partner)] = dict(record)
        self.log.appendPlainText(
            f"Applied: Q{qi}<->Q{qj} g = {avg_coupling:.2f} MHz, "
            f"gain = {avg_gain:.0f}"
        )
        # Mirror into the params tab + summary line.
        try:
            self.get_main().refresh_qubit_summary()
        except Exception:
            pass
        QMessageBox.information(
            self, "Applied",
            f"Wrote Q{qi} <-> Q{qj} into Qubit_Parameters.TwoQubit.\n\n"
            f"coupling = {avg_coupling:.2f} MHz at FF gain {avg_gain:.0f} on Q{sweep_qubit}.\n"
            "Use 'Save Qubit_Parameters JSON' on the toolbar to persist.",
        )

    def _on_apply_ramp(self):
        """Write the fitted resonance gain into the selected Ramp_State's Expt_FF for
        the swept qubit. In-memory; persisted via Save Qubit_Parameters JSON. Only the
        swept qubit's value changes; the entry's delta/abs representation is preserved.
        """
        if self._last_data is None or self._last_pair is None:
            return
        ramp_state = self._last_ramp_state
        if not ramp_state:
            QMessageBox.warning(
                self, "No Ramp_State",
                "This chevron was run without a Ramp_State, so there is no ramp Expt_FF "
                "to update. Re-run with a Ramp_State selected.")
            return
        popts = self._last_data["data"].get("popt_list") or []
        gains = [float(p[0]) for p in popts if hasattr(p, "__getitem__")]
        if not gains:
            QMessageBox.warning(self, "No fit", "Cannot apply: chevron fit was not produced.")
            return
        res_gain = int(round(sum(gains) / len(gains)))
        qi, qj, sweep_qubit = self._last_pair
        idx = int(sweep_qubit) - 1
        jd = self.state.qubit_parameters_json or {}
        base = jd.get("base_params", {})

        # Locate the ramp group that owns this entry.
        grp = None
        for g in (jd.get("ramp_groups") or {}).values():
            if isinstance(g, dict) and ramp_state in (g.get("entries") or {}):
                grp = g
                break
        if grp is None:
            QMessageBox.critical(self, "Not found",
                                 f"Ramp_State {ramp_state!r} not found in ramp_groups.")
            return
        entry = grp["entries"][ramp_state]

        # Current resolved Expt_FF (handles delta/abs + base deref) for the old value.
        try:
            resolved = list(_build_resolve_ramp(jd, ramp_state)["Expt_FF"])
        except Exception as exc:
            QMessageBox.critical(self, "Resolve failed",
                                 f"Could not resolve ramp Expt_FF:\n{exc}")
            return
        old_resolved = int(round(resolved[idx]))

        abs_arr = entry.get("Expt_FF_abs")
        if abs_arr is not None:
            # Absolute representation (may be a base_params name-reference).
            arr = list(base.get(abs_arr, resolved)) if isinstance(abs_arr, str) else list(abs_arr)
            arr[idx] = res_gain
            entry["Expt_FF_abs"] = [int(round(x)) for x in arr]
            mode = "Expt_FF_abs"
        else:
            # Delta representation: bump only the swept qubit's delta so the resolved
            # Expt_FF lands exactly on the measured resonance gain.
            delta = list(entry.get("Expt_FF_delta") or [0] * len(resolved))
            delta[idx] = int(round(delta[idx] + (res_gain - old_resolved)))
            entry["Expt_FF_delta"] = delta
            mode = "Expt_FF_delta"

        self.log.appendPlainText(
            f"Applied to Ramp_State '{ramp_state}' ({mode}): Q{sweep_qubit} Expt_FF "
            f"{old_resolved} -> {res_gain} (resonance gain).")
        try:
            self.get_main().refresh_qubit_summary()
        except Exception:
            pass
        QMessageBox.information(
            self, "Applied to ramp",
            f"Set Q{sweep_qubit} Expt_FF in Ramp_State '{ramp_state}' to {res_gain} "
            f"(was {old_resolved}).\n\nUse 'Save Qubit_Parameters JSON' on the toolbar to persist.")
