"""
Interactive calibration wizard for superconducting-qubit experiments controlled
by a QICK RFSoC over Pyro4.

Two stages:

1. ConnectionDialog (pre-step):
   - Enter Pyro4 nameserver host/port.
   - List nameserver entries (every name => uri pair the ns knows about).
   - Pick the RFSoC proxy name and connect; the dialog acts as a thin client
     for the nameserver and the soc proxy (no hidden hardcoded address).
   - Inspect the soccfg description (DACs, ADCs, sample rates).
   - Choose the number of qubits and map each qubit to its FF DAC channel,
     plus the shared Readout-DAC / Qubit-DAC / ADC indices.

2. MainWindow (calibration wizard):
   - Tabs for Transmission -> Spec slice -> Amplitude Rabi -> Single-shot -> T1
     -> T2R, each with editable parameters and an inline plot.
   - "Apply" pushes a stage result into the in-memory Qubit_Parameters dict;
     the dict can be loaded from / saved to JSON via the toolbar.

Launch from the repo root:

    cd D:/Agentic_QSim_Measurement
    python -m WorkingProjects.triangle_lattice_quench.Run_Experiments.calibration_gui

Pyro4 and qick are imported lazily inside ConnectionDialog, so the GUI opens
fine even when the RFSoC nameserver is unreachable.

Note: the underlying experiment classes are MUX-based (single shared res_ch /
qubit_ch / ADC across qubits, per-qubit FF DAC). The dialog reflects that.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Qt5Agg")

from PyQt5.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QStatusBar, QTabWidget, QVBoxLayout, QWidget,
)

# Session state (the only foundation symbols MainWindow itself needs).
from .state import (
    CalibState,
    DEFAULT_D5A_VOLTAGES_FILE,
    QUBIT_PARAMETERS_JSON,
    get_d5a_settings,
    set_d5a_settings,
)

# One module per tab. MainWindow wires them together; each owns its own
# dialogs / workers / helpers.
from .tabs.qubit_parameters import QubitParametersTab
from .tabs.ff_frequencies import FFFrequenciesTab
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
    AutoCalibTab,
)
from .tabs.lattice_point import LatticePointCalibrationTab
from .tabs.two_qubit import TwoQubitCalibTab
from .tabs.pi2_phase import Pi2PhaseCalibTab
from .tabs.experiment_library import ExperimentLibraryTab
from .tabs.connection import (
    ConnectionDialog,
    D5aCouplerDialog,
    load_d5a_voltages_from_file,
)
from .tabs.program_builder import ProgramBuilderTab
from .tabs.agent_chat import AgentChatTab


class MainWindow(QMainWindow):
    def __init__(self, state: Optional[CalibState] = None):
        super().__init__()
        self.state = state if state is not None else CalibState()
        self.setWindowTitle("Calibration Wizard")
        self.resize(1400, 800)
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
        self.conn_label = QLabel("RFSoC: not connected")
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
        self.ff_freq_tab = FFFrequenciesTab(self.state, lambda: self)
        self.tabs.addTab(self.params_tab, self.params_tab.name)
        self.tabs.addTab(self.ff_freq_tab, self.ff_freq_tab.name)
        self.tabs.addTab(self.auto_calib_tab, self.auto_calib_tab.name)
        self.tabs.addTab(self.lattice_point_tab, self.lattice_point_tab.name)
        self.tabs.addTab(self.two_qubit_tab, self.two_qubit_tab.name)
        self.tabs.addTab(self.pi2_phase_tab, self.pi2_phase_tab.name)
        self.tabs.addTab(self.exp_lib_tab, self.exp_lib_tab.name)
        self.program_builder_tab = ProgramBuilderTab(self.state, lambda: self)
        self.tabs.addTab(self.program_builder_tab, self.program_builder_tab.name)
        self.agent_tab = AgentChatTab(self.state, lambda: self)
        self.tabs.addTab(self.agent_tab, self.agent_tab.name)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(top)
        layout.addWidget(summary)
        layout.addWidget(self.tabs, 1)
        self.setCentralWidget(central)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        if self.state.is_connected():
            self.conn_label.setText(
                f"RFSoC: connected ({self.state.server_name or '?'} @ "
                f"{self.state.ns_host or '?'}:{self.state.ns_port or '?'})"
            )
            self.status.showMessage(
                f"Ready — {self.state.n_qubits} qubits configured. "
                f"Load a Qubit_Parameters JSON or run a stage."
            )
        else:
            self.status.showMessage(
                "Not connected. Click 'Connection info...' to (re)open the connection dialog."
            )
        self._restore_d5a_session()
        # Seed the readout/drive combos in AutoCalibTab (and refresh dependent
        # widgets) from whatever the QubitParametersTab loaded.
        self._on_qubit_params_loaded()
        self.tabs.setCurrentWidget(self.auto_calib_tab)
        self.refresh_qubit_summary()
        self._refresh_d5a_status()

    # --- handlers ---

    def on_connect(self):
        if self.state.is_connected():
            QMessageBox.information(
                self, "Connection info",
                f"Connected to '{self.state.server_name}' at "
                f"{self.state.ns_host}:{self.state.ns_port}.\n\n"
                f"Qubits configured: {self.state.n_qubits}\n"
                f"Readout DAC: {self.state.base_config.get('res_ch')}\n"
                f"Qubit DAC: {self.state.base_config.get('qubit_ch')}\n"
                f"ADC channel: {self.state.base_config.get('ro_chs')}\n"
                f"FF DACs: {self.state.base_config.get('fast_flux_chs')}\n\n"
                f"Restart the GUI to change the channel map."
            )
            return
        dlg = ConnectionDialog(self)
        if dlg.exec_() != QDialog.Accepted or dlg.state is None:
            return
        self.state = dlg.state
        for stage in self.stages:
            stage.state = self.state
        self.params_tab.state = self.state
        if self.state.qubit_parameters_json_path is None:
            self.state.qubit_parameters_json_path = QUBIT_PARAMETERS_JSON
        self.params_tab._load_json(
            self.state.qubit_parameters_json_path, silent=True,
        )
        self.auto_calib_tab.state = self.state
        self.two_qubit_tab.state = self.state
        self.two_qubit_tab.refresh_qubit_combos()
        self.two_qubit_tab.refresh_groups_from_state()
        self.pi2_phase_tab.state = self.state
        self.pi2_phase_tab.refresh_qubit_combos()
        self.pi2_phase_tab.refresh_groups_from_state()
        self.lattice_point_tab.state = self.state
        self.lattice_point_tab.refresh_groups_from_state()
        self.exp_lib_tab.state = self.state
        self.conn_label.setText(
            f"RFSoC: connected ({self.state.server_name} @ "
            f"{self.state.ns_host}:{self.state.ns_port})"
        )
        self.outer_edit.setText(self.state.outer_folder)
        self._on_qubit_params_loaded()
        self.refresh_qubit_summary()
        self.status.showMessage("Connected.", 3000)

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
        if hasattr(self, "ff_freq_tab"):
            self.ff_freq_tab.refresh_from_state()

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

    def refresh_qubit_summary(self):
        """Mirror state changes into the params table.

        Repaints both the QubitParametersTab (tree + detail table cell styles
        against the calibration-touched paths) AND the FFFrequenciesTab's
        group/entry combo styling so dirty-after-on_apply state is visible on
        both tabs without a manual reload.
        """
        params_tab = getattr(self, "params_tab", None)
        if params_tab is not None:
            params_tab.refresh_from_state()
        ff_tab = getattr(self, "ff_freq_tab", None)
        if ff_tab is not None:
            try:
                ff_tab._apply_combo_styles()
            except Exception:
                pass


def main():
    # pythonw.exe / detached-console launches leave sys.stdout/stderr == None,
    # which crashes tqdm inside worker-thread acquire() calls.
    import os
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    app = QApplication(sys.argv)
    # Item 9: slightly larger buttons across the whole app.
    app.setStyleSheet("QPushButton { padding: 4px 10px; }")

    # Launch the connection / channel-mapping dialog first.
    dlg = ConnectionDialog()
    if dlg.exec_() != QDialog.Accepted or dlg.state is None:
        sys.exit(0)

    win = MainWindow(state=dlg.state)
    win.show()
    sys.exit(app.exec_())
