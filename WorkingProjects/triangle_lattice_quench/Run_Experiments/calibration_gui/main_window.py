"""
Interactive calibration wizard for superconducting-qubit experiments controlled
by a QICK RFSoC over Pyro4.

The main window opens at once, with or without an RFSoC. It starts a background
connection attempt with the previous session's nameserver / proxy name / channel map
(ConnectionController). Click the "RFSoC: ..." status or "Connection info..." to open the
ConnectionDialog panel, where you can:
   - Enter Pyro4 nameserver host/port, list the nameserver entries, pick the proxy name.
   - Connect (restarts an attempt already running) or Abort / Disconnect.
   - Inspect the soccfg description (DACs, ADCs, sample rates).
   - Choose the number of qubits and map each qubit to its FF DAC channel,
     plus the shared Readout-DAC / Qubit-DAC indices.

MainWindow (calibration wizard):
   - Tabs for Transmission -> Spec slice -> Amplitude Rabi -> Single-shot -> T1
     -> T2R -> T2E, each with editable parameters and an inline plot.
   - "Apply" pushes a stage result into the in-memory Qubit_Parameters dict;
     the dict can be loaded from / saved to JSON via the toolbar.

Launch from the repo root:

    cd D:/Agentic_QSim_Measurement
    python -m triangle_lattice_quench.Run_Experiments.calibration_gui

Pyro4 and qick are imported lazily by the connection thread, so the GUI opens
fine even when the RFSoC nameserver is unreachable.

Note: the underlying experiment classes are MUX-based (single shared res_ch /
qubit_ch / ADC across qubits, per-qubit FF DAC). The dialog reflects that.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QIcon, QImage, QKeySequence, QPixmap
from typing import Optional

import matplotlib
matplotlib.use("Qt5Agg")

from PyQt5.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QShortcut, QStatusBar, QTabWidget, QVBoxLayout, QWidget,
)

from . import style as st

# Session state (the only foundation symbols MainWindow itself needs).
from .state import (
    CalibState,
    DEFAULT_D5A_VOLTAGES_FILE,
    QUBIT_PARAMETERS_JSON,
    get_d5a_settings,
    get_settings,
    set_d5a_settings,
)

# One module per tab. MainWindow wires them together; each owns its own
# dialogs / workers / helpers.
from .tabs.qubit_parameters import QubitParametersTab
from .tabs.auto_calib import (
    StageTab,
    TransmissionTab,
    SpecSliceTab,
    AmplitudeRabiTab,
    ReadoutOptTab,
    PulseOptTab,
    SingleShotTab,
    T1Tab,
    T2RTab,
    T2ETab,
    AutoCalibTab,
)
from .tabs.lattice_point import LatticePointCalibrationTab
from .tabs.two_qubit import TwoQubitCalibTab
from .tabs.pi2_phase import Pi2PhaseCalibTab
from .tabs.experiment_library import ExperimentLibraryTab
from .tabs.connection import (
    ConnectionController,
    ConnectionDialog,
    D5aCouplerDialog,
    apply_channel_map,
    initial_channel_map,
    load_d5a_voltages_from_file,
    save_connection_params,
    saved_connection_params,
    state_from_channel_map,
)
from .tabs.program_builder import ProgramBuilderTab
from .tabs.agent_chat import AgentChatTab


class ClickableLabel(QLabel):
    """A status label that opens something when clicked."""
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


# status colours of the "RFSoC: ..." label (light backgrounds, dark text)
_CONN_STYLES = {
    "idle": "#e9ecef", "connecting": "#fff3cd", "connected": "#d4edda", "failed": "#f8d7da",
}


class MainWindow(QMainWindow):
    def __init__(self, state: Optional[CalibState] = None):
        super().__init__()
        self.state = state if state is not None else state_from_channel_map(initial_channel_map())
        self.setWindowTitle("Calibration Wizard")
        self.resize(1400, 800)  # clamped to the screen below, once the tabs exist
        # Item 9: window resizable (default behaviour, but be explicit — no
        # setFixedSize / setMinimumSize anywhere).

        # --- toolbar: connection + outerFolder + D5a (slimmed; readout/drive
        # selectors moved into AutoCalibTab, Target-qubit combo deleted). ---
        top = QWidget()
        top_layout = QHBoxLayout(top)

        self.connect_btn = QPushButton("Connection info...")
        self.connect_btn.clicked.connect(self.on_connect)
        top_layout.addWidget(self.connect_btn)

        self.outer_edit = QLineEdit(self.state.outer_folder)
        self.outer_edit.editingFinished.connect(
            lambda: setattr(self.state, "outer_folder", self.outer_edit.text())
        )
        top_layout.addWidget(QLabel("outerFolder:"))
        top_layout.addWidget(self.outer_edit, 1)

        self.d5a_btn = QPushButton("D5a coupler bias...")
        self.d5a_btn.setToolTip(
            "Open the Qblox D5a panel: load a voltage setpoint file, edit, and "
            "ramp the couplers to those voltages. Run this BEFORE any "
            "experiment so the legs sit at the right operating point."
        )
        self.d5a_btn.clicked.connect(self.on_d5a)
        top_layout.addWidget(self.d5a_btn)

        # Summary row (connection + D5a status). The per-qubit summary label
        # is gone — auto-calib table now exposes per-qubit state directly.
        summary = QWidget()
        summary_layout = QHBoxLayout(summary)
        self.conn_label = ClickableLabel()
        self.conn_label.setCursor(Qt.PointingHandCursor)
        self.conn_label.setToolTip("Click to open the RFSoC connection panel")
        self.conn_label.clicked.connect(self.on_connect)
        self._set_conn_status("idle", "RFSoC: not connected")
        self.d5a_status_label = QLabel("D5a: not applied")
        self.d5a_status_label.setStyleSheet("color: #b00; font-weight: bold;")
        summary_layout.addWidget(self.conn_label, 1)
        summary_layout.addWidget(self.d5a_status_label)

        # Construct the per-stage StageTab instances. They are NOT added to
        # the QTabWidget — they live as headless param-spec / make-experiment
        # / on-apply providers consumed by AutoCalibTab. AutoCalibTab steals
        # each stage's param_form widget for its right-side stack.
        self.stages: list[StageTab] = [
            TransmissionTab(self.state, lambda: self),
            SpecSliceTab(self.state, lambda: self),
            AmplitudeRabiTab(self.state, lambda: self),
            ReadoutOptTab(self.state, lambda: self),
            PulseOptTab(self.state, lambda: self),
            SingleShotTab(self.state, lambda: self),
            T1Tab(self.state, lambda: self),
            T2RTab(self.state, lambda: self),
            T2ETab(self.state, lambda: self),
        ]

        # Tabs.
        self.tabs = QTabWidget()
        self.params_tab = QubitParametersTab(self.state, lambda: self)
        self.auto_calib_tab = AutoCalibTab(self.state, lambda: self)
        # Re-parent stage param_forms into the auto-calib right-side stack.
        self.auto_calib_tab.attach_stage_forms(self.stages)
        self.lattice_point_tab = LatticePointCalibrationTab(self.state, lambda: self)
        self.two_qubit_tab = TwoQubitCalibTab(self.state, lambda: self)
        self.pi2_phase_tab = Pi2PhaseCalibTab(self.state, lambda: self)
        self.exp_lib_tab = ExperimentLibraryTab(self.state, lambda: self)
        self.tabs.addTab(self.params_tab, self.params_tab.name)
        self.program_builder_tab = ProgramBuilderTab(self.state, lambda: self)
        self.tabs.addTab(self.program_builder_tab, self.program_builder_tab.name)
        self.tabs.addTab(self.auto_calib_tab, self.auto_calib_tab.name)
        self.tabs.addTab(self.lattice_point_tab, self.lattice_point_tab.name)
        self.tabs.addTab(self.two_qubit_tab, self.two_qubit_tab.name)
        self.tabs.addTab(self.pi2_phase_tab, self.pi2_phase_tab.name)
        self.tabs.addTab(self.exp_lib_tab, self.exp_lib_tab.name)
        self.agent_tab = AgentChatTab(self.state, lambda: self)
        self.tabs.addTab(self.agent_tab, self.agent_tab.name)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(top)
        layout.addWidget(summary)
        layout.addWidget(self.tabs, 1)
        self.setCentralWidget(central)
        # A tab's natural size must not set the window's minimum: let the window shrink below it
        # and start no larger than the screen.
        for i in range(self.tabs.count()):
            self.tabs.widget(i).setMinimumSize(1, 1)
        avail = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1400, int(avail.width() * 0.95)), min(900, int(avail.height() * 0.9)))

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        for keys, action in ((("Ctrl+=", "Ctrl++"), lambda: self.set_zoom(st.current_scale() + st.ZOOM_STEP)),
                             (("Ctrl+-",), lambda: self.set_zoom(st.current_scale() - st.ZOOM_STEP)),
                             (("Ctrl+0",), lambda: self.set_zoom(st.ZOOM_DEFAULT))):
            for key in keys:
                QShortcut(QKeySequence(key), self, activated=action)
        # The connection panel is created once and re-shown on demand; the controller makes the
        # (background, abortable) connection, auto-started by start_auto_connect().
        self.conn_ctrl = ConnectionController(parent=self)
        self.conn_dialog = ConnectionDialog(self.conn_ctrl, self.state,
                                            busy_check=self._experiment_running, parent=self)
        self.conn_dialog.channel_map_applied.connect(self._on_channel_map_applied)
        self.conn_ctrl.started.connect(lambda msg: self._set_conn_status("connecting", f"RFSoC: {msg}"))
        self.conn_ctrl.succeeded.connect(self._on_conn_succeeded)
        self.conn_ctrl.failed.connect(self._on_conn_failed)
        self.conn_ctrl.aborted.connect(lambda: self._set_conn_status("idle", "RFSoC: not connected (attempt aborted)"))
        self.conn_ctrl.disconnected.connect(self._on_conn_disconnected)
        if self.state.is_connected():
            self._set_conn_status("connected",
                                  f"RFSoC: connected ({self.state.server_name or '?'} @ "
                                  f"{self.state.ns_host or '?'}:{self.state.ns_port or '?'})")
        self.status.showMessage("Ready. Load a Qubit_Parameters JSON or run a stage (needs the RFSoC).")
        self._restore_d5a_session()
        # Seed the readout/drive combos in AutoCalibTab (and refresh dependent
        # widgets) from whatever the QubitParametersTab loaded.
        self._on_qubit_params_loaded()
        self.tabs.setCurrentWidget(self.auto_calib_tab)
        self.refresh_qubit_summary()
        self._refresh_d5a_status()

    # --- handlers ---

    def on_connect(self):
        """Open the connection panel (non-modal, so its status updates stay visible)."""
        self.conn_dialog.show()
        self.conn_dialog.raise_()
        self.conn_dialog.activateWindow()

    def start_auto_connect(self) -> None:
        """Try the previous session's connection in the background; failures only colour the status."""
        p = saved_connection_params()
        self.conn_ctrl.connect_to(p["host"], p["port"], p["name"])

    def _experiment_running(self) -> bool:
        """True while any tab's experiment worker is alive (the connection must not change then)."""
        owners = [*getattr(self, "stages", []), getattr(self, "auto_calib_tab", None),
                  getattr(self, "lattice_point_tab", None), getattr(self, "two_qubit_tab", None),
                  getattr(self, "pi2_phase_tab", None), getattr(self, "exp_lib_tab", None)]
        for tab in owners:
            worker = getattr(tab, "worker", None)
            if worker is not None and hasattr(worker, "isRunning") and worker.isRunning():
                return True
        return False

    def _set_conn_status(self, kind: str, text: str) -> None:
        self.conn_label.setText(text)
        self.conn_label.setStyleSheet(
            f"background: {_CONN_STYLES[kind]}; color: #212529; padding: 3px 8px; border-radius: 3px;")

    def _on_conn_succeeded(self, soc, soccfg, cfg_dict, params) -> None:
        """Store the connection in the shared state IN PLACE (tabs hold that object), and keep the
        loaded Qubit_Parameters JSON and outerFolder untouched."""
        self.state.soc = soc
        self.state.soccfg = soccfg
        self.state.ns_host, self.state.ns_port, self.state.server_name = (
            params["host"], int(params["port"]), params["name"])
        save_connection_params(params["host"], params["port"], params["name"])
        cmap = self.conn_dialog.channel_map()      # what the panel shows (previous map unless edited)
        if cmap is not None:
            apply_channel_map(self.state, cmap)
        self._set_conn_status("connected", f"RFSoC: connected ({params['name']} @ "
                                           f"{params['host']}:{params['port']})")
        self.status.showMessage("Connected.", 3000)
        self.conn_dialog._refresh_buttons()

    def _on_conn_failed(self, msg: str) -> None:
        self._set_conn_status("failed", f"RFSoC: connection failed - {msg} (click to change)")
        self.status.showMessage("RFSoC connection failed; the rest of the GUI still works offline.", 5000)

    def _on_conn_disconnected(self) -> None:
        self.state.soc = None
        self.state.soccfg = None
        self._set_conn_status("idle", "RFSoC: not connected")
        self.conn_dialog._refresh_buttons()

    def _on_channel_map_applied(self, cmap: dict) -> None:
        if not apply_channel_map(self.state, cmap):
            QMessageBox.information(
                self, "Restart needed",
                f"The number of qubits is fixed while the GUI is open ({self.state.n_qubits}); the "
                f"new count ({cmap['n_qubits']}) is saved and used at the next start. The shared "
                f"readout / qubit channels were updated now.")
        self.status.showMessage("Channel map applied.", 3000)


    # ---- group-load orchestration ----

    def _on_qubit_params_loaded(self) -> None:
        """Notify tabs that depend on state.qubit_parameters_json that it changed.

        Kept as a thin orchestrator (QubitParametersTab._load_json calls this).
        The readout/drive combos themselves now live on AutoCalibTab and
        TwoQubitCalibTab, which own the refresh logic.
        """
        if hasattr(self, "auto_calib_tab"):
            self.auto_calib_tab.refresh_groups_from_state()
        if hasattr(self, "two_qubit_tab"):
            self.two_qubit_tab.refresh_groups_from_state()
        if hasattr(self, "pi2_phase_tab"):
            self.pi2_phase_tab.refresh_groups_from_state()
        if hasattr(self, "lattice_point_tab"):
            self.lattice_point_tab.refresh_groups_from_state()
        if hasattr(self, "program_builder_tab"):
            self.program_builder_tab.refresh_json()

    # ---- D5a coupler bias ----

    def _restore_d5a_session(self):
        """Pull D5a path/port/module/last-applied from QSettings into state.

        Does NOT touch hardware; users still must click Apply in the dialog
        once per session.
        """
        s = get_d5a_settings()
        if s["voltages_path"]:
            self.state.d5a_voltages_path = s["voltages_path"]
            try:
                self.state.d5a_voltages = load_d5a_voltages_from_file(s["voltages_path"])
            except Exception:
                # Stale path -> fall through to default below.
                self.state.d5a_voltages_path = ""
        if not self.state.d5a_voltages and DEFAULT_D5A_VOLTAGES_FILE.exists():
            try:
                self.state.d5a_voltages = load_d5a_voltages_from_file(
                    str(DEFAULT_D5A_VOLTAGES_FILE)
                )
                self.state.d5a_voltages_path = str(DEFAULT_D5A_VOLTAGES_FILE)
            except Exception:
                pass
        self.state.d5a_port = s["port"]
        self.state.d5a_module = int(s["module"])
        self.state.d5a_last_applied_at = s["last_applied_at"]

    def _refresh_d5a_status(self):
        if not hasattr(self, "d5a_status_label"):
            return
        if self.state.d5a_last_applied_at:
            name = (Path(self.state.d5a_voltages_path).name
                    if self.state.d5a_voltages_path else "(unknown file)")
            self.d5a_status_label.setText(
                f"D5a: {name} applied {self.state.d5a_last_applied_at}"
            )
            self.d5a_status_label.setStyleSheet("color: #060; font-weight: bold;")
        else:
            self.d5a_status_label.setText("D5a: not applied this session")
            self.d5a_status_label.setStyleSheet("color: #b00; font-weight: bold;")

    def on_d5a(self):
        dlg = D5aCouplerDialog(self.state, parent=self)
        dlg.exec_()
        # Persist whatever the user changed in the dialog (path/port/module).
        set_d5a_settings(
            voltages_path=self.state.d5a_voltages_path,
            port=self.state.d5a_port,
            module=self.state.d5a_module,
        )
        self._refresh_d5a_status()

    def set_zoom(self, scale: float) -> float:
        """Re-apply the style at ``scale`` (clamped to 0.8-2.0) and remember it."""
        scale = st.apply_style(QApplication.instance(), scale)
        get_settings().setValue(st.SETTING_ZOOM, scale)
        self.status.showMessage(f"zoom {scale:.1f}x  (Ctrl+= / Ctrl+- / Ctrl+0)", 3000)
        return scale

    def refresh_qubit_summary(self):
        """Mirror state changes into the params table (tree + detail table cell styles
        against the calibration-touched paths) without a manual reload."""
        params_tab = getattr(self, "params_tab", None)
        if params_tab is not None:
            params_tab.refresh_from_state()


ICON_PATH = Path(__file__).with_name("software_icon.png")
APP_ID = "HouckLab.CalibrationGUI"


def _app_icon() -> QIcon:
    """software_icon.png with its opaque white corners made transparent.

    The art is a dark rounded tile on an opaque near-white square, which shows as white
    nibs on a dark taskbar. Clear the background connected to the image border (at 256 px;
    plenty for an icon) and fall back to the plain file if PIL/scipy are unavailable.
    """
    try:
        import numpy as np
        from PIL import Image
        from scipy import ndimage
        rgb = np.asarray(Image.open(ICON_PATH).convert("RGB").resize((256, 256), Image.LANCZOS))
        labels, _ = ndimage.label(rgb.min(axis=2) > 225)
        border = np.unique(np.r_[labels[0], labels[-1], labels[:, 0], labels[:, -1]])
        clear = ndimage.binary_dilation(np.isin(labels, border[border > 0]), iterations=2)
        rgba = np.ascontiguousarray(np.dstack([rgb, np.where(clear, 0, 255).astype(np.uint8)]))
        return QIcon(QPixmap.fromImage(QImage(rgba.data, 256, 256, 1024,
                                              QImage.Format_RGBA8888).copy()))
    except Exception:
        return QIcon(str(ICON_PATH))


def _apply_app_identity(app) -> None:
    """Window/taskbar icon for every window and dialog of this app.

    Windows groups pythonw.exe windows under Python's own identity and icon unless the
    process sets an AppUserModelID, so set one (before any window is shown).
    """
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass                                  # not Windows
    if ICON_PATH.exists():
        app.setWindowIcon(_app_icon())


def main():
    # pythonw.exe / detached-console launches leave sys.stdout/stderr == None,
    # which crashes tqdm inside worker-thread acquire() calls.
    import os
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    app = QApplication(sys.argv)
    _apply_app_identity(app)
    st.apply_style(app, get_settings().value(st.SETTING_ZOOM, st.ZOOM_DEFAULT, type=float))

    # The window opens straight away; the RFSoC connects in the background.
    win = MainWindow()
    win.show()
    QTimer.singleShot(0, win.start_auto_connect)
    sys.exit(app.exec_())
