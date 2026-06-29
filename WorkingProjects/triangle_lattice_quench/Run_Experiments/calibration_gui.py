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

import contextlib
import copy
import json
import re
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import matplotlib
matplotlib.use("Qt5Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure

from PyQt5.QtCore import Qt, QThread, QSettings, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QPen
from PyQt5.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit,
    QPushButton, QSpinBox, QSplitter, QStackedWidget, QStatusBar,
    QStyledItemDelegate, QTableWidget, QTableWidgetItem, QTabWidget,
    QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

# Flux model + resolver imports. MUXInitialize and build_config are now
# hardware-free (no socProxy side effects at module load), so we import them
# directly. The GUI still opens without RFSoC.
from WorkingProjects.triangle_lattice_quench.Flux_Files.Initialize_Qubit_Information import model_mapping
from WorkingProjects.triangle_lattice_quench.Flux_Files.Whole_system_to_Voltages import flux_vector, beta_matrix
from WorkingProjects.triangle_lattice_quench.Helpers.Device_calibration import full_device_calib
from WorkingProjects.triangle_lattice_quench.Run_Experiments.exptui_demo.tab import ExptUIDemoTab
from WorkingProjects.triangle_lattice_quench.Run_Experiments.agent_chat_tab import AgentChatTab
from WorkingProjects.triangle_lattice_quench.MUXInitialize import (
    BaseConfig  as DEFAULT_BASE_CONFIG,
    outerFolder as DEFAULT_OUTER_FOLDER,
)
from WorkingProjects.triangle_lattice_quench.build_config import (
    build_config,
    JSON_PATH         as BUILD_CONFIG_JSON_PATH,
    _deref_base       as _build_deref_base,
    _resolve_readout  as _build_resolve_readout,
    _resolve_drive    as _build_resolve_drive,
    _resolve_ramp     as _build_resolve_ramp,
    _resolve_dynamics as _build_resolve_dynamics,
)

# Default Qblox D5a coupler-bias setpoint file (mirrors QbloxVoltageSet_8QTriangleLattice_Dictionary.py).
DEFAULT_D5A_VOLTAGES_FILE = (
    Path(__file__).parent.parent / "Flux_Files"
    / "QbloxVoltageSet_8QTriangleLattice_Dictionary.py"
)

# Standard 8-qubit triangular-ladder D5a DAC mapping. Q1..Q8 -> DACs 1..8;
# coupler C1..C6 (legs 1-3, 2-4, 3-5, 4-6, 5-7, 6-8) -> DACs 9..14.
DEFAULT_D5A_DAC_MAP: dict[str, int] = {
    "Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4,
    "Q5": 5, "Q6": 6, "Q7": 7, "Q8": 8,
    "C1": 9, "C2": 10, "C3": 11, "C4": 12, "C5": 13, "C6": 14,
}

# D5a connection defaults — match QbloxVoltageSet_8QTriangleLattice_Dictionary.py.
DEFAULT_D5A_PORT = "COM3"
DEFAULT_D5A_BAUD = int(1e6)
DEFAULT_D5A_TIMEOUT = 1.0
DEFAULT_D5A_MODULE = 2
DEFAULT_D5A_RAMP_STEP = 0.003
DEFAULT_D5A_RAMP_INTERVAL = 0.05

# Experiment library: scan this folder for ExperimentClass subclasses.
EXPERIMENTAL_SCRIPTS_DIR = Path(__file__).parent.parent / "Experimental_Scripts"
# Recipe files (saved JSON specs of {file, class, cfg, notes}) live here.
RECIPE_DIR = Path(__file__).parent / "recipes"

# QSettings org/app — controls where Windows stores the recent-file pointer.
SETTINGS_ORG = "HouckLab"
SETTINGS_APP = "TriangleLatticeCalibrationGui"
SETTING_LAST_PARAMS = "last_qubit_params_path"
SETTING_D5A_VOLTAGES_PATH = "d5a_voltages_path"
SETTING_D5A_PORT = "d5a_port"
SETTING_D5A_MODULE = "d5a_module"
SETTING_D5A_LAST_APPLIED = "d5a_last_applied_at"
SETTING_LAST_RECIPE_PATH = "last_recipe_path"


def get_settings() -> QSettings:
    return QSettings(SETTINGS_ORG, SETTINGS_APP)


def get_last_qubit_params_path() -> str:
    return str(get_settings().value(SETTING_LAST_PARAMS, "", type=str) or "")


def set_last_qubit_params_path(path: str) -> None:
    get_settings().setValue(SETTING_LAST_PARAMS, path)


def get_d5a_settings() -> dict:
    """Return the saved D5a session preferences (path, port, module, last-applied)."""
    s = get_settings()
    return {
        "voltages_path": str(s.value(SETTING_D5A_VOLTAGES_PATH, "", type=str) or ""),
        "port": str(s.value(SETTING_D5A_PORT, DEFAULT_D5A_PORT, type=str) or DEFAULT_D5A_PORT),
        "module": int(s.value(SETTING_D5A_MODULE, DEFAULT_D5A_MODULE, type=int) or DEFAULT_D5A_MODULE),
        "last_applied_at": str(s.value(SETTING_D5A_LAST_APPLIED, "", type=str) or ""),
    }


def set_d5a_settings(voltages_path: Optional[str] = None,
                     port: Optional[str] = None,
                     module: Optional[int] = None,
                     last_applied_at: Optional[str] = None) -> None:
    s = get_settings()
    if voltages_path is not None:
        s.setValue(SETTING_D5A_VOLTAGES_PATH, voltages_path)
    if port is not None:
        s.setValue(SETTING_D5A_PORT, port)
    if module is not None:
        s.setValue(SETTING_D5A_MODULE, int(module))
    if last_applied_at is not None:
        s.setValue(SETTING_D5A_LAST_APPLIED, last_applied_at)

def make_default_ff_qubits(n_qubits: int = 8,
                           channels: Optional[list[int]] = None) -> dict:
    """Return an FF_Qubits dict keyed by qubit index ('1','2',...).

    `channels[i]` is the FF DAC channel index assigned to qubit i+1; defaults
    to the identity map (qubit i+1 -> FF channel i).
    """
    if channels is None:
        channels = list(range(n_qubits))
    if len(channels) != n_qubits:
        raise ValueError(
            f"channels has length {len(channels)} but n_qubits={n_qubits}"
        )
    return {
        str(i + 1): {"channel": int(channels[i]),
                     "delay_time": 0.0,
                     "Additional_Delay_Time": 0.0}
        for i in range(n_qubits)
    }


DEFAULT_FF_QUBITS: dict = make_default_ff_qubits(8)

# Sensible per-stage defaults distilled from Fast_calib.py
STAGE_DEFAULTS: dict[str, dict] = {
    "transmission": {
        "TransSpan": 1.5, "TransNumPoints": 61,
        "readout_length": 2.5, "cav_relax_delay": 10,
        "reps": 200,
    },
    "spec_coarse": {
        "qubit_gain": 500, "SpecSpan": 100.0, "SpecNumPoints": 71,
        "Gauss": False, "sigma": 0.07, "Gauss_gain": 3350,
        "qubit_length": 5.0, "reps": 200, "rounds": 1, "relax_delay": 150,
    },
    "spec_fine": {
        "qubit_gain": 50, "SpecSpan": 10.0, "SpecNumPoints": 71,
        "Gauss": False, "sigma": 0.05, "Gauss_gain": 1200,
        "qubit_length": 5.0, "reps": 250, "rounds": 1, "relax_delay": 150,
    },
    "rabi": {
        "max_gain": 12000, "expts": 31, "reps": 200,
        "sigma": 0.05, "relax_delay": 200, "rounds": 1,
    },
    # Readout-fidelity optimisation: 2D scan of cavity gain x cavity freq.
    # Defaults distilled from Fast_calib.py SS_R_params.
    "readout_opt": {
        "Shots": 400, "relax_delay": 150.0,
        "gain_start": 200, "gain_stop": 2000, "gain_pts": 8,
        "span": 1.0, "trans_pts": 5, "number_of_pulses": 1,
        # Iterative recenter-and-zoom controls (GUI-only; see RecenterZoomMixin).
        "iterate": True, "max_iters": 6, "freq_tol": 0.3,
        "gain_tol": 100, "zoom_factor": 0.5,
    },
    # Qubit-pulse-fidelity optimisation: 2D scan of qubit gain x qubit freq.
    # Defaults distilled from Fast_calib.py SS_Q_params.
    "pulse_opt": {
        "Shots": 400, "relax_delay": 150.0,
        "q_gain_span": 2000, "q_gain_pts": 7,
        "q_freq_span": 3.0, "q_freq_pts": 7,
        "number_of_pulses": 1,
        # Iterative recenter-and-zoom controls (GUI-only; see RecenterZoomMixin).
        "iterate": True, "max_iters": 6, "freq_tol": 0.3,
        "gain_tol": 100, "zoom_factor": 0.5,
    },
    "singleshot": {
        "Shots": 3000, "relax_delay": 200, "number_of_pulses": 1,
        "rounds": 1,
    },
    "t1": {
        "expts": 51, "stop_delay_us": 80.0, "reps": 200,
        "relax_delay": 250, "rounds": 1,
    },
    "t2r": {
        "expts": 81, "stop_delay_us": 5.0, "reps": 200,
        "relax_delay": 250, "rounds": 1,
        "freq_shift": 0.0, "phase_shift_cycles": 5,
    },
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _confusion_matrix_for(readout_dict: dict):
    """Build the 2x2 readout confusion matrix from a per-qubit Readout dict.

    Layout matches mSingleShotProgramFFMUX.py:124-127:
        [[1 - ng,   ne],
         [    ng, 1-ne]]
    where ne = ne_contrast (P(measured=excited|prepared=ground) — readout error
    on |g>) and ng = ng_contrast (the equivalent on |e>).
    Returns the 2x2 identity if either contrast is missing — a no-op
    correction that still satisfies SweepExperimentND.acquire's gating check
    `"confusion_matrix" in self.cfg`, so `population_corrected` gets built.
    """
    import numpy as np
    ne = readout_dict.get("ne_contrast")
    ng = readout_dict.get("ng_contrast")
    if ne is None or ng is None:
        return np.eye(2)
    ne = float(ne); ng = float(ng)
    return np.array([[1.0 - ng,        ne],
                     [      ng, 1.0 - ne]])


def _jd_entry_for(state: "CalibState", Q: str) -> Optional[dict]:
    """Locate the entry on_apply should mutate.

    If a drive group is active, the row is a drive entry (e.g. ``'1_3800+'``)
    and on_apply should write into that drive entry — the readout-side entry
    of the same qubit is irrelevant for drive calibrations. Otherwise fall
    back to the readout-group entry. Returns None when no JSON / no group /
    entry doesn't exist. We never auto-create entries.
    """
    jd = state.qubit_parameters_json
    if not jd:
        return None
    label = state.current_qubit_label or str(Q)
    dg = state.current_drive_group or ""
    if dg:
        entry = (jd.get("drive_groups", {})
                   .get(dg, {})
                   .get("entries", {})
                   .get(label))
        if isinstance(entry, dict):
            return entry
    rg = state.current_readout_group or ""
    if not rg:
        return None
    entry = (jd.get("readout_groups", {})
               .get(rg, {})
               .get("entries", {})
               .get(label))
    return entry if isinstance(entry, dict) else None


def _readout_qubit_for_entry(name: str) -> str:
    """Parse the leading digits of a drive-entry name to get the readout qubit.

    Convention used by AutoCalib: a drive entry like ``'1_3800+'`` belongs to
    readout qubit ``'1'``; an entry whose name has no leading digits falls
    back to the entry name itself.
    """
    m = re.match(r"^(\d+)", str(name))
    return m.group(1) if m else str(name)


# Stages that run a MUXed readout: Qubit_Readout_List is built from the
# AutoCalibTab chip strip (state.mux_readouts) with the target prepended.
# All other stages get [target] only (single-qubit readout).
MUX_STAGES = frozenset({"ReadoutOpt", "PulseOpt", "SingleShot"})

# Stages that calibrate readout-side parameters (res frequency, gain, angle,
# threshold). Disabled in the AutoCalib table when a drive group is active —
# drive entries are not readout-calibration vehicles and their FF differs
# from the readout FF, so running these would write meaningless params.
READOUT_SIDE_STAGES = frozenset({"Transmission", "ReadoutOpt", "SingleShot"})


def _mux_readout_list(state: "CalibState", target_ro_q: str) -> list[str]:
    """Target-first MUX list for ReadoutOpt / PulseOpt / SingleShot."""
    others = [q for q in (state.mux_readouts or []) if q != target_ro_q]
    return [target_ro_q] + others


def _pulse_chain_entries(state: "CalibState", target_entry: str) -> list[str]:
    """Build the pulse chain for PulseOpt: prefix in JSON order, target last.

    Walks the active drive group's entries dict in insertion order; appends
    each entry whose parsed qubit is in ``state.pulse_chain`` AND that
    appears before the target. Target is appended last so PulseOpt's swept
    qubit sits at qubit_sweep_index = len(prefix). Returns [target] if the
    drive group is unset or has no entries.
    """
    jd = state.qubit_parameters_json or {}
    dg = state.current_drive_group or ""
    if not dg:
        return [target_entry]
    entries = list((jd.get("drive_groups") or {}).get(dg, {}).get("entries", {}).keys())
    selection = set(state.pulse_chain or [])
    chain: list[str] = []
    for ename in entries:
        if ename == target_entry:
            break  # stop at target — anything after it isn't a precursor
        if _readout_qubit_for_entry(ename) in selection:
            chain.append(ename)
    return chain + [target_entry]


def build_cfg_for_qubit(state: "CalibState", Q: str, *,
                        qubit_pulse: Optional[list] = None,
                        qubit_readout: Optional[list] = None,
                        readout_group: Optional[str] = None,
                        overrides: Optional[dict] = None) -> dict:
    """GUI-side wrapper around ``build_config`` for single-qubit stages.

    Routes through the canonical pipeline (qubit_parameters.json -> build_config
    -> flat cfg) so GUI runs match external scripts. Layers on per-readout
    SingleShot calibration (angle/threshold/confusion_matrix) read from the
    JSON entry's Readout block, then applies stage-form overrides last.

    ``qubit_pulse`` defaults to ``[Q]`` (the drive resolver finds it inside the
    readout group's entry); pass an explicit list to override.

    ``qubit_readout`` defaults to ``[Q]``. AutoCalib passes an explicit value
    when iterating drive-group rows whose entry name (e.g. ``'1_3800+'``)
    differs from the readout-qubit label (``'1'``).
    """
    Q = str(Q)
    rg = readout_group or state.current_readout_group or None
    qp = list(qubit_pulse) if qubit_pulse is not None else [Q]
    qr = list(qubit_readout) if qubit_readout is not None else [Q]

    cfg = build_config(
        Qubit_Readout=qr,
        Qubit_Pulse=qp,
        Readout_Point=rg,
        jd=state.qubit_parameters_json or None,   # falls back to disk if None
    )

    # SingleShot cals — build_config does not promote angle/threshold/confusion_matrix
    # to top-level cfg keys; downstream experiments (notably SweepExperimentND's
    # population_corrected branch) require them. One entry per qubit in qr so
    # MUX stages (qr len > 1) have a matching-length list.
    jd = state.qubit_parameters_json or {}
    angles, thresholds, confusion_matrices = [], [], []
    for ro_key in (qr if qr else [Q]):
        ro_entry = {}
        if rg:
            ro_entry = (jd.get("readout_groups", {})
                          .get(rg, {})
                          .get("entries", {})
                          .get(str(ro_key), {})
                          .get("Readout", {})) or {}
        angles.append(float(ro_entry.get("angle", 0.0)))
        thresholds.append(float(ro_entry.get("threshold", 0.0)))
        confusion_matrices.append(_confusion_matrix_for(ro_entry))
    cfg["angle"] = angles
    cfg["threshold"] = thresholds
    cfg["confusion_matrix"] = confusion_matrices

    if overrides:
        cfg.update(overrides)
    return cfg


@dataclass
class CalibState:
    """Mutable session state shared between tabs."""
    base_config: dict = field(default_factory=lambda: copy.deepcopy(DEFAULT_BASE_CONFIG))
    ff_qubits: dict = field(default_factory=lambda: copy.deepcopy(DEFAULT_FF_QUBITS))
    outer_folder: str = DEFAULT_OUTER_FOLDER
    target_qubit: int = 1            # the qubit currently being calibrated
    n_qubits: int = 8                # number of qubits being calibrated
    soc: Any = None                  # set by ConnectionDialog
    soccfg: Any = None
    ns_host: str = ""                # remembered for the status bar / reconnect
    ns_port: int = 0
    server_name: str = ""
    last_results: dict[str, dict] = field(default_factory=dict)
    # D5a (Qblox) coupler-bias session state.
    d5a_voltages: dict = field(default_factory=dict)        # label -> volts (e.g. "C1": -0.1604)
    d5a_dac_map: dict = field(default_factory=lambda: dict(DEFAULT_D5A_DAC_MAP))
    d5a_voltages_path: str = ""                             # most-recently loaded file
    d5a_port: str = DEFAULT_D5A_PORT
    d5a_module: int = DEFAULT_D5A_MODULE
    d5a_last_applied_at: str = ""                           # ISO timestamp of last successful apply
    # Nested-groups JSON state (loaded by QubitParametersTab; mutated in-memory
    # by stage on_apply hooks and saved on user click). Path is None until
    # something is loaded; the dict mirrors qubit_parameters.json's structure.
    qubit_parameters_json: dict = field(default_factory=dict)
    qubit_parameters_json_path: Optional[Path] = None
    # Deep-copy of the on-disk dict at the last successful load/save. Used by
    # the Save dialog to compute per-qubit diffs vs. in-memory mutations from
    # calibration runs. The snapshot is refreshed only on Load (any source) and
    # on Save accept — NOT on Save-with-timestamp (those are checkpoints, the
    # working file's baseline must remain untouched).
    qubit_parameters_json_snapshot: dict = field(default_factory=dict)
    # JSON paths (as tuples) that have been mutated by a calibration on_apply
    # since the last load/save. Drives the italic-bold "calibration-touched"
    # styling in the table tabs. Cleared on every load and on every successful
    # Save (the snapshot becomes the new baseline at that point).
    calibration_touched_paths: set = field(default_factory=set)
    # Currently selected readout group + qubit label within that group. Drive
    # group is optional and may be unset; readout group is the canonical
    # "Readout_Point" the resolver expects. current_qubit_label is the entry
    # name within current_readout_group (e.g. "1", "1_4Q_readout").
    current_readout_group: str = ""
    current_drive_group: str = ""
    current_qubit_label: str = ""
    # Other qubits to MUX alongside the target for ReadoutOpt / PulseOpt /
    # SingleShot. Empty => target-only (no MUX). The target is always
    # prepended at dispatch time, so qubit_sweep_index stays 0.
    mux_readouts: list = field(default_factory=list)
    # Qubits in the experimental drive sequence (chip strip on AutoCalibTab,
    # only consumed by PulseOpt when a drive group is active). For each row,
    # the chain = drive-group entries in JSON order whose parsed qubit is in
    # this set AND that come before the target, with the target appended last.
    pulse_chain: list = field(default_factory=list)

    def is_connected(self) -> bool:
        return self.soc is not None and self.soccfg is not None

    def build_two_qubit_chevron_config(self, q_i: int, q_j: int,
                                       sweep_qubit: int,
                                       ramp_state: Optional[str] = None,
                                       overrides: Optional[dict] = None) -> dict:
        """Build a 2-readout / 1-pulse cfg for ``GainSweepOscillationsR``.

        Routes through ``build_config`` (same pipeline as single-qubit stages),
        then overlays chevron-specific cfg: ``qubit_FF_index`` for the swept
        FF channel, SingleShot cals from each readout-entry, and explicit
        ``Gain_Expt=0`` / ``Gain_BS=0`` / ``Gain_Dynamics=0`` on every FF
        qubit (build_config emits None when Ramp_State/Dynamics_Point are
        absent; the chevron sweep needs a numeric baseline). The pulse
        fires on the *non-swept* qubit.
        """
        Qubit_Readout = [int(q_i), int(q_j)]
        sweep_qubit = int(sweep_qubit)
        pulse_qubit = int(q_i if sweep_qubit == q_j else q_j)
        rg = self.current_readout_group or None

        cfg = build_config(
            Qubit_Readout=[str(q) for q in Qubit_Readout],
            Qubit_Pulse=[str(pulse_qubit)],
            Readout_Point=rg,
            Ramp_State=ramp_state or None,
            jd=self.qubit_parameters_json or None,
        )

        # SingleShot cals (build_config doesn't promote these). Read from the
        # JSON readout-entry's Readout block, one per readout qubit.
        jd = self.qubit_parameters_json or {}
        angle_list, threshold_list, confusion_matrix = [], [], []
        for Q in Qubit_Readout:
            ro = {}
            if rg:
                ro = (jd.get("readout_groups", {})
                        .get(rg, {})
                        .get("entries", {})
                        .get(str(Q), {})
                        .get("Readout", {})) or {}
            angle_list.append(float(ro.get("angle", 0.0)))
            threshold_list.append(float(ro.get("threshold", 0.0)))
            confusion_matrix.append(_confusion_matrix_for(ro))
        cfg["angle"] = angle_list
        cfg["threshold"] = threshold_list
        cfg["confusion_matrix"] = confusion_matrix

        # FF baseline during the swap dwell. With NO Ramp_State, hold every qubit at its
        # DC baseline (Gain_Expt=0) and let the chevron move only the swept qubit (original
        # behaviour -- finds the bare resonance). With a Ramp_State, KEEP each qubit at the
        # ramp's Expt_FF (build_config already set Gain_Expt = Expt_FF), so the swap is
        # measured AT that ramp point; the chevron still overwrites only the swept qubit's
        # Gain_Expt at runtime. Gain_BS / Gain_Dynamics are zeroed either way (no BS stage).
        for q, entry in cfg.get("FF_Qubits", {}).items():
            if not ramp_state:
                entry["Gain_Expt"] = 0
            elif entry.get("Gain_Expt") is None:
                entry["Gain_Expt"] = 0   # defensive: ramp didn't define this qubit
            entry["Gain_BS"] = 0
            entry["Gain_Dynamics"] = 0
            if entry.get("Gain_RampInit") is None:
                entry["Gain_RampInit"] = entry.get("Gain_Pulse", 0)

        cfg["qubit_FF_index"] = sweep_qubit

        if overrides:
            cfg.update(overrides)
        return cfg


# ---------------------------------------------------------------------------
# Reusable widgets
# ---------------------------------------------------------------------------


class MplCanvas(FigureCanvas):
    """Embeddable matplotlib figure with a single axis."""
    def __init__(self, parent=None, height=4.0):
        self.fig = Figure(figsize=(7.0, height), tight_layout=True)
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setParent(parent)

    def reset(self):
        self.fig.clf()
        self.ax = self.fig.add_subplot(111)
        self.draw()


class ParamForm(QGroupBox):
    """Generic dict<->form editor.

    spec is a list of (key, label, kind, default) where kind is one of
    'int', 'float', 'bool'. Read back with .values().
    """
    def __init__(self, title: str, spec: list[tuple[str, str, str, Any]]):
        super().__init__(title)
        self.spec = spec
        self.widgets: dict[str, QWidget] = {}
        layout = QFormLayout()
        for key, label, kind, default in spec:
            w = self._make_widget(kind, default)
            self.widgets[key] = w
            layout.addRow(label, w)
        self.setLayout(layout)

    def _make_widget(self, kind: str, default: Any) -> QWidget:
        if kind == "int":
            w = QSpinBox()
            w.setRange(-2**31, 2**31 - 1)
            w.setValue(int(default))
            return w
        if kind == "float":
            w = QDoubleSpinBox()
            w.setRange(-1e9, 1e9)
            w.setDecimals(4)
            w.setValue(float(default))
            return w
        if kind == "bool":
            w = QCheckBox()
            w.setChecked(bool(default))
            return w
        raise ValueError(f"unknown widget kind: {kind}")

    def values(self) -> dict:
        out = {}
        for key, _, kind, _ in self.spec:
            w = self.widgets[key]
            if kind == "int":
                out[key] = int(w.value())
            elif kind == "float":
                out[key] = float(w.value())
            elif kind == "bool":
                out[key] = bool(w.isChecked())
        return out

    def apply(self, overrides: dict) -> list[str]:
        """Set widget values from `overrides` (key->value), coercing by widget kind.
        Keys not in this form and None values are ignored. Returns the keys applied
        (used by agent_run to honor sweep params and report what actually changed)."""
        kinds = {key: kind for key, _, kind, _ in self.spec}
        applied = []
        for key, val in (overrides or {}).items():
            if key not in self.widgets or val is None:
                continue
            w = self.widgets[key]
            try:
                if kinds[key] == "int":
                    w.setValue(int(val))
                elif kinds[key] == "float":
                    w.setValue(float(val))
                elif kinds[key] == "bool":
                    w.setChecked(bool(val))
                else:
                    continue
            except (TypeError, ValueError):
                continue
            applied.append(key)
        return applied


# ---------------------------------------------------------------------------
# Iterative recenter-and-zoom (ReadoutOpt / PulseOpt)
# ---------------------------------------------------------------------------

# Max DAC gain magnitude — same constant the experiment classes use to convert
# normalized (0..1) qubit gains to absolute DAC counts (qubit_gains[idx]*32766).
DAC_GAIN_MAX = 32766

# GUI-only knobs injected into cfg by the iterative-opt param forms. They are
# consumed by RecenterZoomMixin and MUST be stripped from cfg before it reaches
# an experiment class (which would otherwise see unexpected keys in data['config']).
ITER_PARAM_KEYS = ("iterate", "max_iters", "freq_tol", "gain_tol", "zoom_factor")


def recenter_zoom_step(prev_opt, new_opt, span_f, span_g,
                       freq_tol, gain_tol, zoom_factor,
                       stable, iteration, max_iters):
    """Pure step function for the recenter-and-zoom loop.

    Always recenters the next window on ``new_opt`` (the optimum just found).
    Tracks how many consecutive iterations landed within tolerance of the
    previous optimum (``stable``); once two consecutive in-tolerance moves
    have occurred (i.e. the first time ``converged`` is True, which is the
    "after the second time" point), the window is zoomed by ``zoom_factor``.

    Args:
        prev_opt: (f, g) optimum from the previous iteration, or None on iter 0.
        new_opt:  (f, g) optimum from the current iteration.
        span_f, span_g: current HALF-width spans (freq MHz, gain DAC).
        freq_tol, gain_tol: convergence tolerances.
        zoom_factor: multiplicative span shrink applied once stable.
        stable: running count of consecutive in-tolerance iterations.
        iteration: zero-based iteration index just completed.
        max_iters: total iteration budget.

    Returns:
        (center_f, center_g, span_f, span_g, stable, should_stop)
    """
    new_f, new_g = new_opt
    center_f, center_g = new_f, new_g

    if prev_opt is not None:
        prev_f, prev_g = prev_opt
        converged = (abs(new_f - prev_f) <= freq_tol
                     and abs(new_g - prev_g) <= gain_tol)
    else:
        converged = False

    stable = stable + 1 if converged else 0

    # Zoom only after two consecutive in-tolerance runs (stable >= 1, i.e. the
    # first iteration on which `converged` is True).
    if stable >= 1:
        span_f *= zoom_factor
        span_g *= zoom_factor

    should_stop = ((iteration + 1 >= max_iters)
                   or (converged and span_f <= freq_tol and span_g <= gain_tol))

    return center_f, center_g, span_f, span_g, stable, should_stop


class RecenterZoomMixin:
    """Adds an iterative recenter-and-zoom driver to a 2D-optimization StageTab.

    Subclasses implement four hooks (see ReadoutOptTab / PulseOptTab):
      ``_iter_read_center(cfg) -> (center_f, center_g)``  (absolute freq MHz, DAC gain)
      ``_iter_initial_spans(cfg) -> (span_f, span_g)``    (HALF-widths)
      ``_iter_write(cfg, center_f, center_g, span_f, span_g, log)``  (mutate cfg)
      ``_iter_extract(expt, data) -> (f, g, fidelity)``   (best point of one run)

    The internal convention is HALF-width spans and absolute gains; the
    experiment classes use full spans / absolute (ReadoutOpt) or normalized
    (PulseOpt) gains — the hooks translate. The driver returns the FINAL
    iteration's ``(expt, data)`` so the existing ``on_apply`` (which argmaxes
    the final data) applies the converged point unchanged.
    """

    def _iter_clamp_gain(self, name, v, log):
        """Clamp a DAC gain to [0, DAC_GAIN_MAX]; WARN via log if clamped."""
        c = max(0.0, min(float(DAC_GAIN_MAX), float(v)))
        if c != float(v) and log is not None:
            log(f"[WARN] {name} gain {v:.0f} clamped to {c:.0f} "
                f"(allowed 0..{DAC_GAIN_MAX})")
        return c

    def _iter_clamp_freq(self, name, v, log):
        """Sanity-clamp a frequency to be finite and non-negative."""
        import math
        fv = float(v)
        if not math.isfinite(fv):
            if log is not None:
                log(f"[WARN] {name} freq {v} not finite; coerced to 0.0")
            return 0.0
        if fv < 0.0:
            if log is not None:
                log(f"[WARN] {name} freq {fv:.3f} < 0; clamped to 0.0")
            return 0.0
        return fv

    def iterate_recenter_zoom(self, cfg, log, should_abort):
        """Run the recenter-and-zoom loop. Returns the BEST (expt, data).

        Normal path (optimum improved): recenter on the optimum just found and,
        once stable, zoom -- via recenter_zoom_step (unchanged).

        Regression path (this iteration's optimum has LOWER fidelity than the
        best seen so far): do NOT chase the worse point. Revert the center to the
        previous best point and zoom into the GAIN only (shrink span_g, keep
        span_f), refining the gain axis around the known-good point.

        Returns the best run's (expt, data) -- not necessarily the final one --
        so on_apply/on_success/render (which argmax fid_mat) act on the best
        point. Under monotonic improvement this is identical to the old behavior
        (best updates every iteration, so best == final and no gain-zoom fires).
        """
        if log is None:
            log = lambda *_a, **_k: None

        center_f, center_g = self._iter_read_center(cfg)
        span_f, span_g = self._iter_initial_spans(cfg)
        prev = None
        stable = 0
        expt = data = None
        best = None                       # (f, g, fid) of the best iteration so far
        best_expt = best_data = None
        max_iters = int(cfg.get("max_iters", 6))
        freq_tol = float(cfg.get("freq_tol", 0.3))
        gain_tol = float(cfg.get("gain_tol", 100))
        zoom_factor = float(cfg.get("zoom_factor", 0.5))

        for it in range(max_iters):
            if should_abort():
                log(f"[iter {it}] aborted before run")
                break
            cfg_i = copy.deepcopy(cfg)
            for k in ITER_PARAM_KEYS:
                cfg_i.pop(k, None)
            self._iter_write(cfg_i, center_f, center_g, span_f, span_g, log)
            expt = self.make_experiment(cfg_i)
            data = expt.acquire()
            try:
                f, g, fid = self._iter_extract(expt, data)
            except ValueError:
                # All-NaN fidelity matrix (nanargmax raises). Stop here and hand
                # back the best run so far (or this run if none) so on_apply/
                # on_success report it gracefully rather than hard-crashing.
                log(f"[iter {it}] no finite fidelity points; stopping iteration")
                break

            if best is None or fid > best[2]:
                # Improvement: accept, track as best, recenter/zoom as before.
                best = (f, g, fid)
                best_expt, best_data = expt, data
                log(f"[iter {it}] center=({center_f:.3f},{center_g:.0f}) -> "
                    f"opt=({f:.3f},{g:.0f}) F={fid * 100:.1f}% "
                    f"span=({span_f:.3f},{span_g:.0f}) (new best)")
                (center_f, center_g, span_f, span_g,
                 stable, stop) = recenter_zoom_step(
                    prev, (f, g), span_f, span_g,
                    freq_tol, gain_tol, zoom_factor,
                    stable, it, max_iters,
                )
                prev = (f, g)
            else:
                # Regression: revert the center to the best point and zoom into
                # the GAIN only (keep span_f), refining the gain around it. Next
                # iteration is compared against the best, not this worse point.
                bf, bg, bfid = best
                span_g_old = span_g
                span_g *= zoom_factor
                center_f, center_g = bf, bg
                stable = 0
                prev = (bf, bg)
                stop = ((it + 1 >= max_iters)
                        or (span_g <= gain_tol and span_f <= freq_tol))
                log(f"[iter {it}] opt=({f:.3f},{g:.0f}) F={fid * 100:.1f}% "
                    f"(regressed vs best F={bfid * 100:.1f}%; revert to "
                    f"({bf:.3f},{bg:.0f}), zoom gain span_g {span_g_old:.0f}->{span_g:.0f})")
            if stop:
                break

        # Apply the BEST point measured, not necessarily the final iteration's.
        if best_expt is not None:
            return best_expt, best_data
        return expt, data


# ---------------------------------------------------------------------------
# Worker thread — runs an experiment off the GUI thread
# ---------------------------------------------------------------------------


class ExperimentWorker(QThread):
    finished_ok = pyqtSignal(object, object)   # (experiment instance, data dict)
    failed = pyqtSignal(str)
    log_msg = pyqtSignal(str)                   # iterative-opt progress lines

    def __init__(self, factory: Callable[[], Any], runner=None):
        super().__init__()
        self.factory = factory
        # Optional runner(log_emit) -> (expt, data). When set, it fully owns
        # acquisition (used by the iterative recenter-and-zoom path). When None,
        # the original single-shot factory().acquire() path runs unchanged.
        self.runner = runner

    def run(self):
        try:
            if self.runner is not None:
                expt, data = self.runner(self.log_msg.emit)
            else:
                expt = self.factory()
                data = expt.acquire()
            self.finished_ok.emit(expt, data)
        except Exception as exc:
            self.failed.emit(f"{exc}\n\n{traceback.format_exc()}")


# ---------------------------------------------------------------------------
# Stage tabs — one per experiment
# ---------------------------------------------------------------------------


class StageTab(QWidget):
    """Base class. Subclasses provide param spec, factory, on_success, on_apply."""

    name: str = "stage"

    def __init__(self, state: CalibState, get_main, parent=None):
        super().__init__(parent)
        self.state = state
        self.get_main = get_main  # callable returning MainWindow (for status updates)
        self.expt = None
        self.data = None
        self.worker: Optional[ExperimentWorker] = None

        self.canvas = MplCanvas(self)
        self.toolbar_mpl = NavigationToolbar(self.canvas, self)
        self.param_form = ParamForm("Parameters", self.param_spec())
        self.run_btn = QPushButton("Run")
        self.apply_btn = QPushButton("Apply result -> Qubit_Parameters")
        self.apply_btn.setEnabled(False)
        self.result_label = QLabel("(no result yet)")
        self.result_label.setStyleSheet("font-weight: bold;")

        # Layout
        left = QVBoxLayout()
        left.addWidget(self.param_form)
        left.addWidget(self.run_btn)
        left.addWidget(self.apply_btn)
        left.addWidget(self.result_label)
        left.addStretch(1)

        right = QVBoxLayout()
        right.addWidget(self.toolbar_mpl)
        right.addWidget(self.canvas)

        layout = QHBoxLayout()
        left_box = QWidget(); left_box.setLayout(left); left_box.setMaximumWidth(360)
        right_box = QWidget(); right_box.setLayout(right)
        layout.addWidget(left_box)
        layout.addWidget(right_box, 1)
        self.setLayout(layout)

        self.run_btn.clicked.connect(self._on_run)
        self.apply_btn.clicked.connect(self._on_apply)

    # --- to be overridden ---
    def param_spec(self) -> list[tuple[str, str, str, Any]]:
        raise NotImplementedError

    def make_experiment(self, cfg: dict):
        """Construct the experiment object — called on the worker thread."""
        raise NotImplementedError

    def display_kwargs(self) -> dict:
        """kwargs passed to expt.display(...). Override per stage where the
        underlying display() handles plotDisp differently."""
        return {"plotDisp": False, "block": False}

    def render_into(self, ax, expt, data, qubit_id=None):
        """Render this stage's plot onto an arbitrary axis.

        Default delegates to ``expt.display(ax=ax, ...)``. Subclasses with
        bespoke plotting (e.g. SingleShot, where the experiment's display()
        does not accept ``ax``) override this. ``qubit_id`` is forwarded to
        let stages that key data by qubit (SingleShot) re-render later from
        a stored result dict, where ``state.target_qubit`` is no longer the
        right qubit."""
        expt.display(data, ax=ax, **self.display_kwargs())

    def render(self, expt, data):
        """Render into this tab's own canvas. Lives here so the auto-calib
        tab can reuse render_into on a different canvas (live preview /
        results matrix)."""
        self.render_into(
            self.canvas.ax, expt, data,
            qubit_id=getattr(self.state, "target_qubit", None),
        )

    def on_success(self, expt, data) -> str:
        """Called on the GUI thread after acquire(); returns a text summary."""
        return "Done."

    def on_apply(self, expt, data):
        """Push results into state.qubit_parameters_json (in-memory JSON dict).

        Subclasses look up the readout-group entry via ``_jd_entry_for`` and
        mutate it in place; QubitParametersTab's Save buttons persist.
        """
        pass

    def cell_summary(self, expt, data) -> str:
        """Short text painted into the AutoCalib table cell on success.

        Default: ``"OK"`` — matches the legacy behaviour for every stage.
        Override per-stage to surface a single headline number (e.g.
        SingleShot fidelity, T1 in us). This is the (a) pattern referenced
        in the calibration GUI rewrite plan: log lines still come from
        ``on_success`` (richer / multi-field), the cell shows one glanceable
        value, and the two evolve independently. ``_on_stage_done`` falls
        back to ``"OK"`` if this raises, so subclasses don't need a try/except.
        """
        return "OK"

    # --- common machinery ---
    def _build_cfg(self) -> dict:
        # Routes through build_config() so GUI cfg matches external scripts.
        # All single-qubit stages drive the target qubit's own pulse; the drive
        # resolver finds it inside the active readout group's entry.
        Q = str(self.state.target_qubit)
        return build_cfg_for_qubit(
            self.state, Q,
            overrides=self.param_form.values(),
        )

    def _on_run(self):
        if not self.state.is_connected():
            QMessageBox.warning(self, "Not connected",
                                "Click 'Connect to RFSoC' in the toolbar first.")
            return
        self.run_btn.setEnabled(False)
        self.apply_btn.setEnabled(False)
        self.result_label.setText("Running...")
        self.canvas.reset()
        self.get_main().status.showMessage(f"Running {self.name}...")

        cfg = self._build_cfg()

        # Iterative recenter-and-zoom path: ReadoutOpt/PulseOpt with iterate=True
        # hand the full acquisition loop to the mixin (which strips ITER_PARAM_KEYS
        # per iteration). The non-iterate path must reproduce today's behaviour
        # byte-for-byte, so strip the GUI-only iter keys (guarded pop) before they
        # reach the experiment and land in data['config'].
        runner = None
        if isinstance(self, RecenterZoomMixin) and cfg.get("iterate"):
            runner = lambda log: self.iterate_recenter_zoom(
                cfg, log, should_abort=lambda: False
            )
        else:
            for _k in ITER_PARAM_KEYS:
                cfg.pop(_k, None)

        def factory():
            return self.make_experiment(cfg)

        self.worker = ExperimentWorker(factory, runner=runner)
        self.worker.finished_ok.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        # Surface iterative-opt progress lines on the result label (no log pane
        # in the single-stage tabs). Best-effort: never crash the run on this.
        self.worker.log_msg.connect(self._on_iter_log)
        self.worker.start()

    def _on_iter_log(self, msg: str):
        try:
            self.result_label.setText(msg)
        except Exception:
            pass

    def _on_finished(self, expt, data):
        self.expt = expt
        self.data = data
        try:
            self.canvas.reset()
            self.render(expt, data)
            self.canvas.draw()
            summary = self.on_success(expt, data)
        except Exception as exc:
            summary = f"display() raised: {exc}"
            traceback.print_exc()
        self.result_label.setText(summary)
        self.apply_btn.setEnabled(True)
        self.run_btn.setEnabled(True)
        self.state.last_results[self.name] = {"summary": summary}
        self.get_main().status.showMessage(f"{self.name}: {summary}", 5000)

    def _on_failed(self, msg: str):
        self.result_label.setText("FAILED")
        self.run_btn.setEnabled(True)
        QMessageBox.critical(self, f"{self.name} failed", msg)
        self.get_main().status.showMessage(f"{self.name} failed", 5000)

    def _on_apply(self):
        if self.expt is None:
            return
        # Snapshot the JSON so we can tag every leaf this on_apply mutates as
        # "calibration-touched" (italic-bold styling on the params tab).
        before = copy.deepcopy(self.state.qubit_parameters_json or {})
        try:
            self.on_apply(self.expt, self.data)
            _snapshot_calibration_diff(self.state, before)
            QMessageBox.information(self, "Applied",
                                    "Updated in-memory qubit_parameters JSON. "
                                    "Use Save on the Qubit Parameters tab to persist.")
            self.get_main().refresh_qubit_summary()
        except Exception as exc:
            QMessageBox.critical(self, "Apply failed", str(exc))


# Default location of the nested-groups parameter JSON.
QUBIT_PARAMETERS_JSON = Path(__file__).parent / "Qubit_Parameters" / "qubit_parameters.json"


# --- per-qubit-entry diff helpers (Save dialog) ----------------------------


# Field paths that naturally drift run-to-run (T1/T2R fits, etc.). The "suspicious
# >3x change" highlight is suppressed for these so a routine 10us -> 35us T1
# update doesn't trip the warning glyph. Compared as a dotted path suffix
# (e.g. matches "Qubit.T1" within an entry).
_DIFF_NOISY_FIELDS = {"Qubit.T1", "Qubit.T2R"}


def _values_differ(a, b) -> bool:
    """True if (a, b) should count as a change.

    Numeric tolerance: floats compare with relative-epsilon to avoid
    floating-point noise. NaN/None transitions are always treated as a change
    (so the dialog can flag them as suspicious). ``bool`` is checked before
    ``int`` because ``isinstance(True, int)`` is True in Python.
    """
    if a is b:
        return False
    # NaN: any comparison with NaN is False, so equal-NaN should NOT count as
    # changed, but NaN-vs-non-NaN should. Use the math-style check.
    def _is_nan(x):
        return isinstance(x, float) and x != x
    a_nan, b_nan = _is_nan(a), _is_nan(b)
    if a_nan and b_nan:
        return False
    if a_nan or b_nan:
        return True
    # None transitions count as a change unless both None (caught by `a is b`).
    if a is None or b is None:
        return True
    # Bool first (subclass of int).
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) != bool(b)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        try:
            return abs(float(a) - float(b)) > 1e-9 * max(abs(float(a)), abs(float(b)), 1.0)
        except Exception:
            return a != b
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            return True
        return any(_values_differ(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a.keys()) != set(b.keys()):
            return True
        return any(_values_differ(a[k], b[k]) for k in a)
    return a != b


def _is_suspicious_change(path_str: str, old, new) -> bool:
    """Magnitude-change flag for the Save dialog.

    Triggers on (a) any NaN/None transition between non-equal values, or
    (b) a >3x change in absolute magnitude when both sides are numeric and
    the old value is non-zero. Skipped for fields known to drift run-to-run
    (T1, T2R) so routine fit updates don't get flagged.
    """
    for noisy in _DIFF_NOISY_FIELDS:
        if path_str == noisy or path_str.endswith("." + noisy):
            return False
    def _bad(x):
        return x is None or (isinstance(x, float) and x != x)
    if _bad(old) != _bad(new):
        return True
    if _bad(old) or _bad(new):
        return False
    try:
        old_f = float(old); new_f = float(new)
    except (TypeError, ValueError):
        return False
    if not isinstance(old, (int, float)) or not isinstance(new, (int, float)):
        return False
    if isinstance(old, bool) or isinstance(new, bool):
        return False
    if old_f == 0.0:
        # Treat 0 -> nonzero as suspicious (avoids divide-by-zero and is
        # genuinely worth a second look — a calibration that flips a value on
        # from zero is a structural change).
        return new_f != 0.0
    return abs(new_f) > 3.0 * abs(old_f) or abs(new_f) < abs(old_f) / 3.0


def _walk_entry_diff(snapshot, live, path: list[str], out: list[tuple[str, object, object]]) -> None:
    """Recursive walker collecting (path_str, old, new) tuples for one entry."""
    # Dict: descend on union of keys.
    if isinstance(snapshot, dict) and isinstance(live, dict):
        for k in sorted(set(snapshot.keys()) | set(live.keys())):
            sub_s = snapshot.get(k, _MISSING)
            sub_l = live.get(k, _MISSING)
            if sub_s is _MISSING:
                out.append((".".join(path + [str(k)]), None, sub_l))
                continue
            if sub_l is _MISSING:
                out.append((".".join(path + [str(k)]), sub_s, None))
                continue
            _walk_entry_diff(sub_s, sub_l, path + [str(k)], out)
        return
    # Leaf / mismatched type: compare.
    if _values_differ(snapshot, live):
        out.append((".".join(path) if path else "(value)", snapshot, live))


class _MissingType:
    """Sentinel for `_walk_entry_diff` — distinguishes "key absent" from None."""
    def __repr__(self): return "<MISSING>"
_MISSING = _MissingType()


def _diff_entries(snapshot: dict, live: dict) -> list[dict]:
    """Compute per-entry diffs between two qubit_parameters dicts.

    Walks ``readout_groups[*].entries[*]`` and ``drive_groups[*].entries[*]``.
    The diff unit is a single ``(kind, group, entry)`` triple. Within each
    matched entry, fields are walked recursively into nested dicts (e.g.
    ``Readout.angle``, ``Qubit.Frequency``). Groups or entries that exist on
    only one side are reported as structural additions/removals with no
    field-level breakdown (the dialog tags those and persists them
    unconditionally — the user can't safely revert a brand-new entry to
    "nothing").

    Returns a list of records:
        {
            'kind':    'readout_groups' | 'drive_groups',
            'group':   group name,
            'entry':   entry name,
            'changes': [(path_str, old, new), ...],   # empty for structural
            'status':  'modified' | 'added' | 'removed',
        }
    """
    records: list[dict] = []
    for kind in ("readout_groups", "drive_groups"):
        snap_groups = (snapshot or {}).get(kind, {}) or {}
        live_groups = (live or {}).get(kind, {}) or {}
        group_names = sorted(set(snap_groups.keys()) | set(live_groups.keys()))
        for gname in group_names:
            snap_entries = (snap_groups.get(gname, {}) or {}).get("entries", {}) or {}
            live_entries = (live_groups.get(gname, {}) or {}).get("entries", {}) or {}
            entry_names = sorted(set(snap_entries.keys()) | set(live_entries.keys()))
            for ename in entry_names:
                snap_e = snap_entries.get(ename, _MISSING)
                live_e = live_entries.get(ename, _MISSING)
                if snap_e is _MISSING and live_e is _MISSING:
                    continue
                if snap_e is _MISSING:
                    records.append({
                        'kind': kind, 'group': gname, 'entry': ename,
                        'changes': [], 'status': 'added',
                    })
                    continue
                if live_e is _MISSING:
                    records.append({
                        'kind': kind, 'group': gname, 'entry': ename,
                        'changes': [], 'status': 'removed',
                    })
                    continue
                # Modified-or-equal: walk to find any field changes.
                changes: list[tuple[str, object, object]] = []
                _walk_entry_diff(snap_e, live_e, [], changes)
                if changes:
                    records.append({
                        'kind': kind, 'group': gname, 'entry': ename,
                        'changes': changes, 'status': 'modified',
                    })
    # base_params — flat name -> array. Emitted last so RO/Drive records lead.
    records.extend(_diff_base_params(snapshot, live))
    return records


def _diff_base_params(snapshot: dict, live: dict) -> list[dict]:
    """Element-wise diff for ``base_params[array_name]``.

    One record per affected array. ``entry`` is None; ``kind`` is
    ``"base_params"``. For modified arrays, ``changes`` is a list of
    ``("[i]", old_i, new_i)`` tuples (one per differing element).
    Added/removed arrays have an empty changes list.
    """
    out: list[dict] = []
    snap_bp = (snapshot or {}).get("base_params", {}) or {}
    live_bp = (live or {}).get("base_params", {}) or {}
    names = sorted(set(snap_bp.keys()) | set(live_bp.keys()))
    for name in names:
        snap_arr = snap_bp.get(name, _MISSING)
        live_arr = live_bp.get(name, _MISSING)
        if snap_arr is _MISSING and live_arr is _MISSING:
            continue
        if snap_arr is _MISSING:
            out.append({'kind': 'base_params', 'group': name, 'entry': None,
                        'changes': [], 'status': 'added'})
            continue
        if live_arr is _MISSING:
            out.append({'kind': 'base_params', 'group': name, 'entry': None,
                        'changes': [], 'status': 'removed'})
            continue
        # Both sides arrays: element-wise compare. Length mismatch = treat
        # missing-on-shorter-side slots as None so they surface as diffs.
        if not isinstance(snap_arr, (list, tuple)) or not isinstance(live_arr, (list, tuple)):
            # Unexpected scalar/dict — fall back to whole-value diff.
            if _values_differ(snap_arr, live_arr):
                out.append({'kind': 'base_params', 'group': name, 'entry': None,
                            'changes': [("(value)", snap_arr, live_arr)],
                            'status': 'modified'})
            continue
        n = max(len(snap_arr), len(live_arr))
        changes: list[tuple[str, object, object]] = []
        for i in range(n):
            sv = snap_arr[i] if i < len(snap_arr) else None
            lv = live_arr[i] if i < len(live_arr) else None
            if _values_differ(sv, lv):
                changes.append((f"[{i}]", sv, lv))
        if changes:
            out.append({'kind': 'base_params', 'group': name, 'entry': None,
                        'changes': changes, 'status': 'modified'})
    return out


def _fmt_diff_value(v, path_str: str = "") -> str:
    """Short, single-line repr for the diff dialog's "old -> new" column.

    ``path_str`` lets the formatter narrow precision for fields where 6-sig
    digits are noise: readout angle is in radians (3 decimals are plenty),
    threshold is a DAC-count discriminator (one decimal suffices).
    """
    if v is None:
        return "None"
    if isinstance(v, float):
        if v != v:  # NaN
            return "NaN"
        if path_str.endswith(".angle"):
            return f"{v:.3f}"
        if path_str.endswith(".threshold"):
            return f"{v:.1f}"
        return f"{v:.6g}"
    if isinstance(v, (int, bool)):
        return repr(v)
    if isinstance(v, str):
        return v if len(v) <= 32 else v[:29] + "..."
    if isinstance(v, (list, tuple)):
        s = repr(list(v))
        return s if len(s) <= 64 else s[:61] + "..."
    if isinstance(v, dict):
        s = repr(v)
        return s if len(s) <= 64 else s[:61] + "..."
    return repr(v)


def _field_importance(path_str: str) -> int:
    """Sort key for changed fields inside the diff dialog's "What changed".

    Qubit.* are the user-relevant calibration outputs; Readout.angle and
    Readout.threshold are auxiliary discriminator params the user rarely
    cares about per-save. Lower = earlier in the summary.
    """
    if path_str.endswith(".angle") or path_str.endswith(".threshold"):
        return 30
    if path_str.startswith("Qubit"):
        return 0
    if path_str.startswith("Readout"):
        return 10
    return 20


# --- dirty-tracking helpers shared by QubitParametersTab + FFFrequenciesTab ---


def _leaf_at_path(root: dict, path: tuple) -> tuple[bool, object]:
    """Walk a path of (key|int-index) into a nested dict/list structure.

    Returns ``(found, value)``. ``found=False`` means a segment was missing or
    the structure didn't match (e.g. tried to index a non-list). Used by the
    style helpers to look up the corresponding leaf in the on-disk snapshot.
    """
    cur = root
    for seg in path:
        if isinstance(cur, dict):
            if seg not in cur:
                return False, None
            cur = cur[seg]
        elif isinstance(cur, (list, tuple)):
            try:
                i = int(seg)
            except (TypeError, ValueError):
                return False, None
            if i < 0 or i >= len(cur):
                return False, None
            cur = cur[i]
        else:
            return False, None
    return True, cur


def _path_is_dirty(snapshot: dict, live: dict, path: tuple) -> bool:
    """True if the leaf at ``path`` differs between snapshot and live.

    Routes through ``_values_differ`` so float/NaN/None handling matches the
    Save dialog. A missing-on-one-side leaf counts as dirty (matches the
    behaviour the Save dialog already exposes via _walk_entry_diff).
    """
    snap_found, snap_v = _leaf_at_path(snapshot or {}, path)
    live_found, live_v = _leaf_at_path(live or {}, path)
    if snap_found != live_found:
        return True
    if not snap_found:
        return False
    return _values_differ(snap_v, live_v)


def _apply_dirty_style(item: "QTableWidgetItem", dirty: bool,
                       calibration_touched: bool) -> None:
    """Repaint an item's font to reflect dirty / calibration-touched state.

    Three visual states, matching the existing pattern at lines 4876 / 5128 /
    5353:
      - plain (not dirty)                : font.bold=False, font.italic=False
      - user-typed unsaved (dirty only)  : font.bold=True,  font.italic=False
      - calibration-touched unsaved      : font.bold=True,  font.italic=True
    """
    f = item.font()
    if not dirty:
        f.setBold(False); f.setItalic(False)
    elif calibration_touched:
        f.setBold(True);  f.setItalic(True)
    else:
        f.setBold(True);  f.setItalic(False)
    item.setFont(f)


def _entry_touched_paths(touched: set, prefix: tuple) -> bool:
    """True if any path in ``touched`` starts with ``prefix``.

    Used to bold the combo text in FFFrequenciesTab when the selected group
    has any calibration-touched leaf below it.
    """
    if not touched:
        return False
    n = len(prefix)
    for p in touched:
        if len(p) >= n and tuple(p[:n]) == prefix:
            return True
    return False


def _diff_path_set(snapshot: dict, live: dict) -> set:
    """All leaf-paths that differ between snapshot and live (any namespace).

    Used to drive group-level dirty styling (e.g. bold a combo entry when ANY
    leaf below it is dirty vs snapshot). Walks both sides via the same
    semantics as _walk_entry_diff but emits full path tuples rather than
    dotted strings.
    """
    dirty: set = set()

    def walk(s, l, path: tuple) -> None:
        if isinstance(s, dict) and isinstance(l, dict):
            for k in set(s.keys()) | set(l.keys()):
                walk(s.get(k, _MISSING), l.get(k, _MISSING), path + (k,))
            return
        if isinstance(s, list) and isinstance(l, list):
            n = max(len(s), len(l))
            for i in range(n):
                sv = s[i] if i < len(s) else _MISSING
                lv = l[i] if i < len(l) else _MISSING
                walk(sv, lv, path + (i,))
            return
        # Treat _MISSING as "absent" — only count as dirty if the other side
        # has a value.
        if s is _MISSING and l is _MISSING:
            return
        if s is _MISSING or l is _MISSING:
            dirty.add(path); return
        if _values_differ(s, l):
            dirty.add(path)

    walk(snapshot or {}, live or {}, ())
    return dirty


def _snapshot_calibration_diff(state: "CalibState", before: dict) -> None:
    """Compute the diff between ``before`` and ``state.qubit_parameters_json``
    and add every changed leaf-path to ``state.calibration_touched_paths``.

    Used by both StageTab._on_apply and AutoCalibWorker.run to tag calibration-
    written leaves without modifying each individual on_apply method.
    """
    try:
        changed = _diff_path_set(before, state.qubit_parameters_json)
    except Exception:
        # Defensive: never let a tagging failure abort an apply.
        return
    if changed:
        state.calibration_touched_paths.update(changed)


class SaveDiffDialog(QDialog):
    """Per-qubit save-diff confirmation dialog.

    One row per changed entry (``(kind, group, entry)`` triple). Each row
    carries a checkbox; checked rows have their live values persisted, and
    unchecked rows have their snapshot values restored on accept. Structural
    additions/removals are always-on (checkbox disabled+checked) — the user
    can't safely "revert" a fresh entry whose snapshot side is empty. Suspicious
    changes (>3x magnitude, NaN/None transitions; skipped for T1/T2R) are
    prepended with a warning glyph and the row text is tinted red.
    """

    WARN_GLYPH = "(!) "  # ASCII-safe; the spec asks for a glyph cue without forcing a font.
    WARN_COLOR = QColor("#a32a2a")

    def __init__(self, records: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Save changes to qubit_parameters.json")
        self.resize(900, 500)
        self.records = records

        layout = QVBoxLayout(self)
        header = QLabel(
            "Review changes before writing to disk. Unchecked rows are reverted "
            "to the on-disk snapshot. Structural additions/removals are always "
            "persisted."
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        btn_row = QHBoxLayout()
        self.select_all_btn = QPushButton("Select all")
        self.clear_btn = QPushButton("Clear")
        self.select_all_btn.clicked.connect(self._select_all)
        self.clear_btn.clicked.connect(self._clear_all)
        btn_row.addWidget(self.select_all_btn)
        btn_row.addWidget(self.clear_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.table = QTableWidget(len(records), 5)
        self.table.setHorizontalHeaderLabels(["", "Kind", "Group", "Entry", "What changed"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        # No stretchLastSection: let the "What changed" column size to its
        # content so the horizontal scrollbar kicks in when summaries are
        # wider than the dialog. Pixel-grained scroll for nicer drag-pan.
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        layout.addWidget(self.table, 1)

        self._checkboxes: list[QCheckBox] = []
        for i, rec in enumerate(records):
            cb = QCheckBox()
            cb.setChecked(True)
            cell = QWidget()
            h = QHBoxLayout(cell)
            h.setContentsMargins(8, 0, 0, 0)
            h.addWidget(cb)
            h.addStretch(1)
            self.table.setCellWidget(i, 0, cell)
            self._checkboxes.append(cb)

            # Kind/Group/Entry columns. base_params records get Kind="Base",
            # entry shown as "(array)" — they're one-record-per-array, no entry name.
            if rec['kind'] == 'readout_groups':
                kind_short = "RO"
            elif rec['kind'] == 'drive_groups':
                kind_short = "Drive"
            elif rec['kind'] == 'base_params':
                kind_short = "Base"
            else:
                kind_short = str(rec['kind'])
            self.table.setItem(i, 1, QTableWidgetItem(kind_short))
            self.table.setItem(i, 2, QTableWidgetItem(str(rec['group'])))
            entry_disp = "(array)" if rec['kind'] == 'base_params' else str(rec['entry'])
            self.table.setItem(i, 3, QTableWidgetItem(entry_disp))

            # "What changed" — build a compact summary string.
            suspicious = False
            if rec['status'] == 'added':
                summary = "[ADDED]  new entry" if rec['kind'] != 'base_params' else "[ADDED]  new array"
            elif rec['status'] == 'removed':
                summary = "[REMOVED]  entry deleted" if rec['kind'] != 'base_params' else "[REMOVED]  array deleted"
            else:
                parts = []
                is_base = rec['kind'] == 'base_params'
                # Sort field changes: Qubit.* first, Readout main next,
                # Readout.angle/threshold last (auxiliary, less user-relevant).
                # base_params entries (path_str "[i]") sort stably by index.
                ordered = sorted(
                    rec['changes'],
                    key=lambda c: (_field_importance(c[0]), c[0]),
                )
                for path_str, old, new in ordered:
                    # base_params: format "[i]" -> "Q{i+1}[i]" for readability.
                    if is_base and path_str.startswith("[") and path_str.endswith("]"):
                        try:
                            idx = int(path_str[1:-1])
                            label = f"Q{idx + 1}{path_str}"
                        except ValueError:
                            label = path_str
                    else:
                        label = path_str
                    if _is_suspicious_change(path_str, old, new):
                        suspicious = True
                    parts.append(
                        f"{label} {_fmt_diff_value(old, path_str)} "
                        f"-> {_fmt_diff_value(new, path_str)}"
                    )
                summary = ",  ".join(parts)
            if suspicious:
                summary = self.WARN_GLYPH + summary
            change_item = QTableWidgetItem(summary)
            change_item.setToolTip(summary)
            if suspicious:
                change_item.setForeground(self.WARN_COLOR)
                # Tint other cells in the same row too so the user notices.
                for col in (1, 2, 3):
                    cell_item = self.table.item(i, col)
                    if cell_item is not None:
                        cell_item.setForeground(self.WARN_COLOR)
            self.table.setItem(i, 4, change_item)

        self.table.resizeColumnsToContents()

        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)

    def _select_all(self) -> None:
        for cb in self._checkboxes:
            if cb.isEnabled():
                cb.setChecked(True)

    def _clear_all(self) -> None:
        for cb in self._checkboxes:
            if cb.isEnabled():
                cb.setChecked(False)

    def selections(self) -> list[bool]:
        """Per-record checked state (parallel to ``self.records``)."""
        return [cb.isChecked() for cb in self._checkboxes]


class QubitParametersTab(QWidget):
    """View-only tree browser for the nested-groups qubit_parameters.json file.

    Hierarchy (top-level JSON namespaces -> groups -> entries) is shown in a
    QTreeWidget on the left; clicking any node populates a read-only
    pretty-printed JSON pane on the right. Entry nodes additionally render
    `_resolved_*` keys computed by the `_build_resolve_*` helpers above,
    making the dereferenced/recipe-applied FF arrays visible alongside the
    raw JSON. Reload + Load JSON... toolbar buttons re-read the file;
    editing is intentionally out-of-scope here.
    """

    name = "Qubit Parameters"

    # Constructor signature preserved from the previous flat-table version,
    # since main wires it as `QubitParametersTab(self.state, lambda: self)`.
    def __init__(self, state: CalibState, get_main, parent=None):
        super().__init__(parent)
        self.state = state
        self.get_main = get_main
        # The loaded JSON lives on CalibState so other tabs (AutoCalib,
        # SingleShot's on_apply, etc.) can mutate it. _jd / _json_path are
        # convenience aliases pointing at the same place — read via self._jd
        # to stay backwards-compatible with all the helpers below.
        if self.state.qubit_parameters_json_path is None:
            self.state.qubit_parameters_json_path = QUBIT_PARAMETERS_JSON

        # --- toolbar ---
        self.load_btn = QPushButton("Load JSON...")
        self.load_btn.clicked.connect(self._on_load_json)
        self.reload_btn = QPushButton("Reload")
        self.reload_btn.clicked.connect(self._on_reload)
        self.save_btn = QPushButton("Save")
        self.save_btn.setToolTip(
            "Overwrite the loaded JSON file with the current in-memory dict."
        )
        self.save_btn.clicked.connect(self._on_save)
        self.save_ts_btn = QPushButton("Save with timestamp")
        self.save_ts_btn.setToolTip(
            "Write a copy of the in-memory dict to "
            "<basename>_<YYYYMMDD_HHMMSS>.json in the same folder."
        )
        self.save_ts_btn.clicked.connect(self._on_save_timestamp)
        self.path_label = QLabel("(no file loaded)")
        self.path_label.setStyleSheet("color: #555;")
        self.path_label.setWordWrap(False)
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        # View-mode toggle (item 7): JSON pretty-print or human-readable table.
        self.view_json_btn = QPushButton("JSON")
        self.view_json_btn.setCheckable(True)
        self.view_table_btn = QPushButton("Table")
        self.view_table_btn.setCheckable(True)
        self.view_table_btn.setChecked(True)  # Default to table (sticky).
        self.view_json_btn.clicked.connect(lambda: self._set_view_mode("json"))
        self.view_table_btn.clicked.connect(lambda: self._set_view_mode("table"))

        top_row = QHBoxLayout()
        top_row.addWidget(self.load_btn)
        top_row.addWidget(self.reload_btn)
        top_row.addWidget(self.save_btn)
        top_row.addWidget(self.save_ts_btn)
        top_row.addSpacing(16)
        top_row.addWidget(QLabel("View:"))
        top_row.addWidget(self.view_json_btn)
        top_row.addWidget(self.view_table_btn)
        top_row.addWidget(self.path_label, 1)
        top_widget = QWidget()
        top_widget.setLayout(top_row)

        # --- splitter: tree on left, detail (stacked JSON/Table) on right ---
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("qubit_parameters.json")
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.currentItemChanged.connect(self._on_tree_selection)

        # Pane 1: JSON pretty-print.
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        f = QFont()
        f.setStyleHint(QFont.Monospace)
        f.setFamily("Consolas")
        self.detail.setFont(f)

        # Pane 2: tabular entry view (for group nodes with `entries`). Cells
        # carrying a JSON leaf path (UserRole = path tuple) are editable; the
        # placeholder "entry"/"field" header cells are flagged read-only via
        # Qt.ItemIsEditable being absent in setFlags.
        self.detail_table = QTableWidget()
        # Allow double-click + key-press editing on cells that opt in via
        # Qt.ItemIsEditable; locked cells stay read-only because they don't
        # carry that flag.
        self.detail_table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
        )
        self.detail_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.detail_table.horizontalHeader().setStretchLastSection(True)
        # itemChanged fires on every edit commit; the leaf path stored in
        # UserRole tells us which JSON leaf to mutate.
        self._suppress_table_changed = False
        self.detail_table.itemChanged.connect(self._on_table_item_changed)

        # QStackedWidget would be ideal but we keep a plain QWidget with a
        # QVBoxLayout that hides/shows whichever pane is active — simpler to
        # ferry signals to.
        self._detail_container = QWidget()
        _detail_layout = QVBoxLayout(self._detail_container)
        _detail_layout.setContentsMargins(0, 0, 0, 0)
        _detail_layout.addWidget(self.detail)
        _detail_layout.addWidget(self.detail_table)

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.addWidget(self.tree)
        splitter.addWidget(self._detail_container)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([400, 800])

        layout = QVBoxLayout(self)
        layout.addWidget(top_widget)
        layout.addWidget(splitter, 1)

        self._view_mode = "table"
        self._set_view_mode_widgets()

        # Initial load: try the default path; failure -> empty tree + message.
        self._load_json(self.state.qubit_parameters_json_path, silent=True)

    # --- aliases that keep the older helpers (_render_detail, _on_reload, etc.)
    # working against the new CalibState-backed storage. ---

    @property
    def _jd(self) -> dict:
        return self.state.qubit_parameters_json

    @_jd.setter
    def _jd(self, value: dict) -> None:
        self.state.qubit_parameters_json = value

    @property
    def _json_path(self) -> Path:
        return self.state.qubit_parameters_json_path or QUBIT_PARAMETERS_JSON

    @_json_path.setter
    def _json_path(self, value: Path) -> None:
        self.state.qubit_parameters_json_path = Path(value) if value else None

    # --- view-mode toggle ---

    def _set_view_mode(self, mode: str) -> None:
        self._view_mode = mode
        self.view_json_btn.setChecked(mode == "json")
        self.view_table_btn.setChecked(mode == "table")
        self._set_view_mode_widgets()
        # Re-render the current selection in the new mode.
        item = self.tree.currentItem()
        if item is not None:
            self._on_tree_selection(item, None)

    def _set_view_mode_widgets(self) -> None:
        self.detail.setVisible(self._view_mode == "json")
        self.detail_table.setVisible(self._view_mode == "table")

    # --- save buttons ---

    def _confirm_save_diffs(self) -> Optional[dict]:
        """Show the per-qubit diff dialog and return the live dict to persist.

        Returns:
          - ``None`` if the user cancelled (caller must abort the save).
          - The in-memory dict (with unchecked diffs reverted to the snapshot)
            if the user accepted, OR if no diffs were found (fast path).

        Side effect: when the user un-checks a diff, the corresponding entry
        is reverted in-place inside ``state.qubit_parameters_json`` so the
        live dict matches what's about to be written to disk. The snapshot is
        NOT updated here — callers do that after the file write succeeds.
        """
        live = self.state.qubit_parameters_json
        snapshot = self.state.qubit_parameters_json_snapshot or {}
        records = _diff_entries(snapshot, live)
        if not records:
            return live  # no-diff fast path; no dialog shown.

        dlg = SaveDiffDialog(records, parent=self)
        if dlg.exec_() != QDialog.Accepted:
            return None
        selections = dlg.selections()
        # Revert any unchecked entry to its snapshot value (deep copy so
        # later in-memory mutations don't trash the snapshot).
        for rec, keep in zip(records, selections):
            if keep:
                continue
            kind = rec['kind']; gname = rec['group']; ename = rec['entry']
            # base_params: revert at the array level (no entries layer).
            if kind == 'base_params':
                snap_arr = (snapshot.get("base_params", {}) or {}).get(gname)
                live_bp = live.setdefault("base_params", {})
                if rec['status'] == 'added':
                    live_bp.pop(gname, None)
                elif rec['status'] == 'removed':
                    if snap_arr is not None:
                        live_bp[gname] = copy.deepcopy(snap_arr)
                else:
                    if snap_arr is not None:
                        live_bp[gname] = copy.deepcopy(snap_arr)
                continue
            snap_entry = (snapshot.get(kind, {})
                                 .get(gname, {})
                                 .get("entries", {})
                                 .get(ename))
            live_entries = (live.get(kind, {})
                                .get(gname, {})
                                .get("entries"))
            if rec['status'] == 'added':
                # Revert addition: drop from live.
                if isinstance(live_entries, dict):
                    live_entries.pop(ename, None)
            elif rec['status'] == 'removed':
                # Revert removal: restore snapshot copy.
                if snap_entry is not None:
                    entries = (live.setdefault(kind, {})
                                   .setdefault(gname, {})
                                   .setdefault("entries", {}))
                    entries[ename] = copy.deepcopy(snap_entry)
            else:
                # Modified: restore the original entry.
                if snap_entry is not None and isinstance(live_entries, dict):
                    live_entries[ename] = copy.deepcopy(snap_entry)
        return live

    def _on_save(self) -> None:
        if not self.state.qubit_parameters_json:
            QMessageBox.information(
                self, "Nothing to save",
                "No JSON has been loaded into memory yet."
            )
            return
        path = self.state.qubit_parameters_json_path
        if path is None:
            self._on_save_timestamp()  # nowhere to overwrite — pivot to Save-As.
            return
        live = self._confirm_save_diffs()
        if live is None:
            return  # user cancelled — disk and in-memory both untouched.
        try:
            written = []
            with open(path, "w") as fh:
                dump_pretty(live, fh)
            written.append(Path(path))
            # Always also overwrite the canonical qubit_parameters.json that
            # build_config (and therefore every experiment script) actually
            # loads. If the active save path already IS the canonical file this
            # is a no-op skip — avoid a redundant double write. Compare resolved
            # paths so a relative/loaded-elsewhere path still matches.
            canonical = Path(BUILD_CONFIG_JSON_PATH)
            try:
                same = Path(path).resolve() == canonical.resolve()
            except Exception:
                same = Path(path) == canonical
            if not same:
                with open(canonical, "w") as fh:
                    dump_pretty(live, fh)
                written.append(canonical)
            # Rebaseline: future diffs measure against what we just wrote.
            self.state.qubit_parameters_json_snapshot = copy.deepcopy(live)
            self.state.calibration_touched_paths = set()
            self._refresh_styles()
            self.path_label.setText(f"{path}  (saved)")
            msg = "Saved " + "; ".join(str(p) for p in written)
            try:
                self.get_main().status.showMessage(msg, 6000)
            except Exception:
                pass
            if len(written) > 1:
                QMessageBox.information(
                    self, "Saved",
                    "Wrote:\n  " + "\n  ".join(str(p) for p in written)
                    + "\n\nThe canonical qubit_parameters.json (loaded by "
                      "build_config) was overwritten so experiment scripts "
                      "pick up these values.")
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", f"{exc}")

    def _on_save_timestamp(self) -> None:
        from datetime import datetime
        if not self.state.qubit_parameters_json:
            QMessageBox.information(
                self, "Nothing to save",
                "No JSON has been loaded into memory yet."
            )
            return
        path = self.state.qubit_parameters_json_path or QUBIT_PARAMETERS_JSON
        live = self._confirm_save_diffs()
        if live is None:
            return  # user cancelled.
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = path.with_name(f"{path.stem}_{ts}.json")
        try:
            with open(out_path, "w") as fh:
                dump_pretty(live, fh)
            written = [out_path]
            # The timestamped file is a history checkpoint that build_config
            # NEVER loads — so a timestamp-only save would not reach any
            # experiment script. ALSO overwrite the canonical
            # qubit_parameters.json that build_config reads, so saved values
            # actually take effect. Skip if out_path already IS the canonical
            # file (it isn't, given the timestamp suffix — but guard anyway).
            canonical = Path(BUILD_CONFIG_JSON_PATH)
            try:
                same = out_path.resolve() == canonical.resolve()
            except Exception:
                same = out_path == canonical
            if not same:
                with open(canonical, "w") as fh:
                    dump_pretty(live, fh)
                written.append(canonical)
                # The canonical file IS the working file: rebaseline diffs and
                # styling against what we just wrote, matching plain Save.
                self.state.qubit_parameters_json_snapshot = copy.deepcopy(live)
                self.state.calibration_touched_paths = set()
                try:
                    self._refresh_styles()
                except Exception:
                    pass
            self.path_label.setText(f"{path}  (snapshot: {out_path.name})")
            msg = "Saved " + "; ".join(str(p) for p in written)
            try:
                self.get_main().status.showMessage(msg, 6000)
            except Exception:
                pass
            if len(written) > 1:
                QMessageBox.information(
                    self, "Saved",
                    "Wrote:\n  " + "\n  ".join(str(p) for p in written)
                    + "\n\nThe canonical qubit_parameters.json (loaded by "
                      "build_config) was overwritten so experiment scripts "
                      "pick up these values; the timestamped copy is history.")
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", f"{exc}")

    # ----- file I/O -----

    def _on_load_json(self) -> None:
        start = str(self._json_path.parent if self._json_path.exists()
                    else QUBIT_PARAMETERS_JSON.parent)
        path, _ = QFileDialog.getOpenFileName(
            self, "Load qubit_parameters JSON", start, "JSON (*.json)"
        )
        if not path:
            return
        self._load_json(Path(path), silent=False)

    def _on_reload(self) -> None:
        self._load_json(self._json_path, silent=False)

    def refresh_from_state(self) -> None:
        """Compatibility shim for existing call sites in MainWindow.

        Two behaviours: if state.qubit_parameters_json is already populated
        (e.g. another tab mutated it via on_apply), just re-render the tree
        without re-reading the file. Otherwise fall back to reloading the
        file at state.qubit_parameters_json_path.
        """
        if self.state.qubit_parameters_json:
            self._populate_tree()
            if self.tree.topLevelItemCount() > 0:
                self.tree.setCurrentItem(self.tree.topLevelItem(0))
            # Repaint per-cell bold styling against the (possibly newly
            # calibration-touched) snapshot.
            self._refresh_styles()
            return
        self._load_json(self._json_path, silent=True)

    def _load_json(self, path: Path, *, silent: bool) -> None:
        """Read `path` into self._jd and rebuild the tree. silent=True swallows
        the missing-file case (used at startup with the default path)."""
        path = Path(path)
        try:
            with open(path) as fh:
                self._jd = json.load(fh)
            # Snapshot the just-loaded on-disk state. Subsequent calibration
            # runs mutate self._jd in-place; the snapshot is what Save diffs
            # against. Both error branches below reset this to {} alongside _jd.
            self.state.qubit_parameters_json_snapshot = copy.deepcopy(self._jd)
            # Fresh on-disk baseline -> no calibration-touched leaves yet.
            self.state.calibration_touched_paths = set()
        except FileNotFoundError:
            self._jd = {}
            self.state.qubit_parameters_json_snapshot = {}
            self.state.calibration_touched_paths = set()
            self._json_path = path
            self.path_label.setText(f"(not found: {path})")
            self.tree.clear()
            self.detail.setPlainText("")
            self.detail_table.clear()
            self.detail_table.setRowCount(0); self.detail_table.setColumnCount(0)
            if not silent:
                QMessageBox.warning(self, "Load failed", f"JSON file not found: {path}")
            return
        except Exception as exc:
            self._jd = {}
            self.state.qubit_parameters_json_snapshot = {}
            self.state.calibration_touched_paths = set()
            self._json_path = path
            self.path_label.setText(f"(error loading {path})")
            self.tree.clear()
            self.detail.setPlainText(f"Failed to load {path}:\n{exc}\n\n{traceback.format_exc()}")
            self.detail_table.clear()
            self.detail_table.setRowCount(0); self.detail_table.setColumnCount(0)
            if not silent:
                QMessageBox.critical(self, "Load failed", f"{exc}\n\n{traceback.format_exc()}")
            return

        self._json_path = path
        self.path_label.setText(str(path))
        self._populate_tree()
        # Default selection: top-level item (root) so the detail pane shows
        # the namespace summary right away.
        if self.tree.topLevelItemCount() > 0:
            self.tree.setCurrentItem(self.tree.topLevelItem(0))
        # Notify the main window so the toolbar readout-group combo refreshes.
        try:
            main = self.get_main()
        except Exception:
            main = None
        if main is not None and hasattr(main, "_on_qubit_params_loaded"):
            try:
                main._on_qubit_params_loaded()
            except Exception:
                traceback.print_exc()

    # ----- tree construction -----

    # Path-encoding scheme stored in QTreeWidgetItem.UserRole. A node's path
    # is a tuple of (namespace, group_name, sub_key, entry_name). Subkey is
    # used for group-level scalar/array fields like "Readout_FF", "Pulse_FF",
    # "_recipe", "Expt_FF". `entries` is encoded as sub_key="entries" with
    # `entry_name` set on the leaf level.
    NS_KEYS = ("base_params", "readout_groups", "drive_groups",
               "ramp_groups", "dynamics_groups")

    def _populate_tree(self) -> None:
        self.tree.clear()
        if not self._jd:
            return
        for ns in self.NS_KEYS:
            if ns not in self._jd:
                continue
            ns_item = QTreeWidgetItem([ns])
            ns_item.setData(0, Qt.UserRole, ("ns", ns))
            self.tree.addTopLevelItem(ns_item)

            if ns == "base_params":
                # base_params is flat: name -> array.
                for name in self._jd[ns]:
                    leaf = QTreeWidgetItem([name])
                    leaf.setData(0, Qt.UserRole, ("base", name))
                    ns_item.addChild(leaf)
                continue

            # Group-bearing namespaces.
            for group_name, group_body in self._jd[ns].items():
                if not isinstance(group_body, dict):
                    continue
                g_item = QTreeWidgetItem([group_name])
                g_item.setData(0, Qt.UserRole, ("group", ns, group_name))
                desc = group_body.get("description")
                if isinstance(desc, str) and desc:
                    g_item.setToolTip(0, desc)
                ns_item.addChild(g_item)

                # Group-level non-entry fields shown as children (Readout_FF,
                # Pulse_FF, _recipe, Expt_FF). description is hidden because
                # it's already exposed as the tooltip.
                for key, val in group_body.items():
                    if key in ("entries", "description"):
                        continue
                    sub_item = QTreeWidgetItem([key])
                    sub_item.setData(0, Qt.UserRole, ("group_field", ns, group_name, key))
                    g_item.addChild(sub_item)

                # entries node (always present in non-base namespaces).
                entries = group_body.get("entries", {})
                if isinstance(entries, dict) and entries:
                    e_root = QTreeWidgetItem(["entries"])
                    e_root.setData(0, Qt.UserRole, ("entries_root", ns, group_name))
                    g_item.addChild(e_root)
                    for ename in entries:
                        e_leaf = QTreeWidgetItem([ename])
                        e_leaf.setData(0, Qt.UserRole, ("entry", ns, group_name, ename))
                        e_root.addChild(e_leaf)

        self.tree.expandToDepth(0)

    # ----- detail rendering -----

    def _on_tree_selection(self, current: QTreeWidgetItem, _previous) -> None:
        if current is None:
            self.detail.setPlainText("")
            self.detail_table.clear()
            self.detail_table.setRowCount(0); self.detail_table.setColumnCount(0)
            return
        tag = current.data(0, Qt.UserRole)
        if tag is None:
            self.detail.setPlainText("")
            self.detail_table.clear()
            self.detail_table.setRowCount(0); self.detail_table.setColumnCount(0)
            return
        try:
            self.detail.setPlainText(self._render_detail(tag))
        except Exception as exc:
            self.detail.setPlainText(
                f"Failed to render selection {tag}:\n{exc}\n\n{traceback.format_exc()}"
            )
        # Table view: rendered only for group nodes that have `entries`. Every
        # other node type falls back to a one-row scalar summary.
        try:
            self._render_detail_table(tag)
        except Exception as exc:
            self.detail_table.clear()
            self.detail_table.setRowCount(1); self.detail_table.setColumnCount(1)
            self.detail_table.setHorizontalHeaderLabels(["error"])
            self.detail_table.setItem(0, 0, QTableWidgetItem(
                f"render failed: {exc}"
            ))

    def _render_detail(self, tag: tuple) -> str:
        """Build pretty-printed JSON for the selected node, augmented with
        `_resolved_*` keys for entry nodes."""
        jd = self._jd
        kind = tag[0]

        if kind == "ns":
            ns = tag[1]
            # Show top-level keys (names of groups / base entries) as a summary.
            body = jd.get(ns, {})
            if ns == "base_params":
                return dumps_pretty(body)
            summary = {name: list(grp.keys()) for name, grp in body.items()
                       if isinstance(grp, dict)}
            return dumps_pretty({ns: summary})

        if kind == "base":
            name = tag[1]
            return dumps_pretty({name: jd.get("base_params", {}).get(name)})

        if kind == "group":
            _, ns, gname = tag
            return dumps_pretty(jd.get(ns, {}).get(gname, {}))

        if kind == "group_field":
            _, ns, gname, key = tag
            group = jd.get(ns, {}).get(gname, {})
            val = group.get(key)
            base = jd.get("base_params", {})
            # If this is a name-reference (e.g. Expt_FF: "Expt_3800"), show
            # both the raw form and the dereferenced array.
            if isinstance(val, str) and val in base:
                return dumps_pretty({
                    key: val,
                    f"_resolved_{key}": list(base[val]),
                })
            return dumps_pretty({key: val})

        if kind == "entries_root":
            _, ns, gname = tag
            entries = jd.get(ns, {}).get(gname, {}).get("entries", {})
            return dumps_pretty({"entries": list(entries.keys())})

        if kind == "entry":
            _, ns, gname, ename = tag
            entry = jd.get(ns, {}).get(gname, {}).get("entries", {}).get(ename, {})
            # Start from the raw entry, then layer in _resolved_* keys.
            out: dict = dict(entry)  # shallow copy preserves key order
            try:
                if ns == "readout_groups":
                    resolved = _build_resolve_readout(jd, ename, gname)
                    out["_resolved_Readout_FF"] = resolved["Readout_FF"]
                    out["_resolved_Pulse_FF"] = resolved["Pulse_FF"]
                elif ns == "drive_groups":
                    resolved = _build_resolve_drive(jd, ename)
                    out["_resolved_Pulse_FF"] = resolved["Pulse_FF"]
                elif ns == "ramp_groups":
                    resolved = _build_resolve_ramp(jd, ename)
                    out["_resolved_Init_FF"] = resolved["Init_FF"]
                    out["_resolved_Expt_FF"] = resolved["Expt_FF"]
                elif ns == "dynamics_groups":
                    resolved = _build_resolve_dynamics(jd, ename)
                    for k, v in resolved.items():
                        if k not in entry:
                            out[f"_resolved_{k}"] = v
            except Exception as exc:
                out["_resolved_ERROR"] = f"{type(exc).__name__}: {exc}"
            return dumps_pretty(out)

        return f"(unhandled tag: {tag!r})"

    # ---- Table view rendering ----

    @staticmethod
    def _flatten_entry_row(entry: dict, ns: str) -> dict:
        """Flatten a per-entry dict into {column: scalar/short-string} pairs.

        Readout/drive groups have nested Readout / Qubit sub-dicts; we prefix
        their keys (e.g. `Readout.Frequency`). Ramp/dynamics entries are flat;
        array values are stringified (so e.g. Expt_FF_delta shows as
        '[0, -6000, ...]').
        """
        out: dict = {}
        for k, v in entry.items():
            if isinstance(v, dict):
                for kk, vv in v.items():
                    out[f"{k}.{kk}"] = vv
            else:
                out[k] = v
        return out

    @staticmethod
    def _fmt_cell(v) -> str:
        if v is None:
            return ""
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, float):
            return f"{v:g}"
        if isinstance(v, (list, tuple)):
            # Compact list display; tooltip can hold the full thing.
            inner = ", ".join(QubitParametersTab._fmt_cell(x) for x in v)
            return f"[{inner}]"
        return str(v)

    def _render_detail_table(self, tag: tuple) -> None:
        """Populate self.detail_table for the selected tree node.

        Only group nodes that own an `entries` dict produce a meaningful table;
        every other node renders a single-row "(see JSON view)" placeholder.

        Editable cells (entry rows) store their JSON leaf-path tuple in
        Qt.UserRole + 1; ``_on_table_item_changed`` reads that to write back
        into ``state.qubit_parameters_json``. ``_apply_dirty_style`` paints the
        per-cell bold / italic-bold indicators against the snapshot +
        ``calibration_touched_paths``.
        """
        jd = self._jd
        kind = tag[0]
        table = self.detail_table
        self._suppress_table_changed = True
        try:
            table.clear()

            # The only really useful tabular views are group nodes and entries_root
            # nodes: both expand the per-entry dict for that group. Other nodes get
            # a "(switch to JSON view)" placeholder.
            if kind in ("group", "entries_root"):
                ns, gname = tag[1], tag[2]
                entries = jd.get(ns, {}).get(gname, {}).get("entries", {})
                if not isinstance(entries, dict) or not entries:
                    table.setRowCount(1); table.setColumnCount(1)
                    table.setHorizontalHeaderLabels(["(no entries)"])
                    table.setItem(0, 0, QTableWidgetItem(
                        "Group has no `entries` block."
                    ))
                    return
                # Collect column union across all entries (preserve first-seen order).
                cols: list[str] = []
                row_dicts: list[tuple[str, dict, dict]] = []
                for name, entry in entries.items():
                    if not isinstance(entry, dict):
                        flat = {"value": entry}
                        leaf_paths: dict = {}
                    else:
                        flat = self._flatten_entry_row(entry, ns)
                        leaf_paths = self._leaf_paths_for_entry(entry, ns, gname, name)
                    row_dicts.append((name, flat, leaf_paths))
                    for k in flat:
                        if k not in cols:
                            cols.append(k)
                table.setRowCount(len(row_dicts))
                table.setColumnCount(1 + len(cols))
                table.setHorizontalHeaderLabels(["entry"] + cols)
                for r, (name, flat, leaf_paths) in enumerate(row_dicts):
                    name_item = QTableWidgetItem(str(name))
                    name_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    # Bold the entry name when any leaf under the entry is dirty.
                    if self._row_dirty_for_entry(ns, gname, name):
                        f = name_item.font(); f.setBold(True); name_item.setFont(f)
                    table.setItem(r, 0, name_item)
                    for c, col in enumerate(cols, start=1):
                        val = flat.get(col, None)
                        item = QTableWidgetItem(self._fmt_cell(val))
                        leaf_path = leaf_paths.get(col)
                        # Only "simple" scalar leaves are editable here. Lists
                        # are read-only in the detail table; their full editor
                        # lives in EntryEditDialog (FF gains grid).
                        if leaf_path is not None and not isinstance(val, (list, tuple, dict)):
                            item.setFlags(
                                Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable
                            )
                            item.setData(Qt.UserRole + 1, leaf_path)
                        else:
                            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                        if isinstance(val, (list, tuple)):
                            item.setToolTip(json.dumps(_make_jsonable(val)))
                        table.setItem(r, c, item)
                table.resizeColumnsToContents()
                self._apply_table_styles()
                return

            if kind == "entry":
                _, ns, gname, ename = tag
                entry = jd.get(ns, {}).get(gname, {}).get("entries", {}).get(ename, {})
                flat = self._flatten_entry_row(entry, ns) if isinstance(entry, dict) else {"value": entry}
                leaf_paths = self._leaf_paths_for_entry(entry, ns, gname, ename) if isinstance(entry, dict) else {}
                # Bold the entry's row label if any leaf below it is dirty.
                row_dirty = self._row_dirty_for_entry(ns, gname, ename)
                table.setRowCount(len(flat))
                table.setColumnCount(2)
                table.setHorizontalHeaderLabels(["field", "value"])
                for r, (k, v) in enumerate(flat.items()):
                    fk = QTableWidgetItem(k); fk.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    # Bold the field label whenever this row is dirty (any leaf
                    # below the entry differs from snapshot).
                    if row_dirty:
                        f = fk.font(); f.setBold(True); fk.setFont(f)
                    fv = QTableWidgetItem(self._fmt_cell(v))
                    leaf_path = leaf_paths.get(k)
                    if leaf_path is not None and not isinstance(v, (list, tuple, dict)):
                        fv.setFlags(
                            Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable
                        )
                        fv.setData(Qt.UserRole + 1, leaf_path)
                    else:
                        fv.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    if isinstance(v, (list, tuple)):
                        fv.setToolTip(json.dumps(_make_jsonable(v)))
                    table.setItem(r, 0, fk)
                    table.setItem(r, 1, fv)
                table.resizeColumnsToContents()
                self._apply_table_styles()
                return

            # Editable per-qubit FF-gain grid for group_field nodes whose
            # selected key is a flat numeric array (e.g. Readout_FF / Pulse_FF).
            # String name-references (Expt_FF: "Expt_3800"), _recipe, and scalars
            # fall through to the placeholder below.
            if kind == "group_field":
                _, ns, gname, key = tag
                group = self._jd.get(ns, {}).get(gname, {})

                def _is_flat_numeric(v) -> bool:
                    if not isinstance(v, (list, tuple)):
                        return False
                    return all(
                        isinstance(x, (int, float)) and not isinstance(x, bool)
                        for x in v
                    )

                ff_cols: list[tuple[str, list]] = [
                    (k, v) for k, v in group.items() if _is_flat_numeric(v)
                ]
                ff_names = [c[0] for c in ff_cols]
                if key in ff_names:
                    nrows = max(len(arr) for _, arr in ff_cols)
                    table.setRowCount(nrows)
                    table.setColumnCount(len(ff_cols))
                    table.setHorizontalHeaderLabels(ff_names)
                    table.setVerticalHeaderLabels(
                        [f"Q{i + 1}" for i in range(nrows)]
                    )
                    for c, (col, arr) in enumerate(ff_cols):
                        for r in range(nrows):
                            val = arr[r] if r < len(arr) else None
                            item = QTableWidgetItem(self._fmt_cell(val))
                            if r < len(arr) and isinstance(val, (int, float)) \
                                    and not isinstance(val, bool):
                                item.setFlags(
                                    Qt.ItemIsEnabled | Qt.ItemIsSelectable
                                    | Qt.ItemIsEditable
                                )
                                item.setData(Qt.UserRole + 1, (ns, gname, col, r))
                            else:
                                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                            table.setItem(r, c, item)
                    table.resizeColumnsToContents()
                    self._apply_table_styles()
                    return

            # Fallback: placeholder for namespace / base / group_field nodes.
            table.setRowCount(1); table.setColumnCount(1)
            table.setHorizontalHeaderLabels([" "])
            table.setItem(0, 0, QTableWidgetItem(
                "(Table view shows only group / entry nodes. Switch to JSON for "
                "namespaces, base_params, or group fields.)"
            ))
        finally:
            self._suppress_table_changed = False

    # ----- editable-cell support (leaf paths, write-back, style refresh) -----

    @staticmethod
    def _leaf_paths_for_entry(entry: dict, ns: str, gname: str,
                              ename: str) -> dict:
        """Map ``_flatten_entry_row`` column keys to JSON leaf paths.

        Mirrors the flatten rule (dict subkey -> ``"sub.key"``); the path is a
        tuple suitable for ``_leaf_at_path`` against ``state.qubit_parameters_json``.
        Lists/dicts get a path too (used to check entry-row dirtiness), but the
        renderer keeps them read-only.
        """
        out: dict = {}
        if not isinstance(entry, dict):
            return out
        base = (ns, gname, "entries", ename)
        for k, v in entry.items():
            if isinstance(v, dict):
                for kk in v.keys():
                    out[f"{k}.{kk}"] = base + (k, kk)
            else:
                out[k] = base + (k,)
        return out

    def _row_dirty_for_entry(self, ns: str, gname: str, ename: str) -> bool:
        """True if any leaf below entry path differs from snapshot."""
        snap = self.state.qubit_parameters_json_snapshot or {}
        live = self.state.qubit_parameters_json or {}
        prefix = (ns, gname, "entries", ename)
        # Check any path in calibration_touched_paths first (cheap), then
        # fall back to a structural diff of the entry subtree.
        if _entry_touched_paths(self.state.calibration_touched_paths, prefix):
            return True
        snap_entry = (snap.get(ns, {}) or {}).get(gname, {}).get("entries", {}).get(ename)
        live_entry = (live.get(ns, {}) or {}).get(gname, {}).get("entries", {}).get(ename)
        if snap_entry is None and live_entry is None:
            return False
        return _values_differ(snap_entry, live_entry)

    def _apply_table_styles(self) -> None:
        """Repaint every editable cell's font from snapshot + touched-paths."""
        snap = self.state.qubit_parameters_json_snapshot or {}
        live = self.state.qubit_parameters_json or {}
        touched = self.state.calibration_touched_paths
        table = self.detail_table
        self._suppress_table_changed = True
        try:
            for r in range(table.rowCount()):
                for c in range(table.columnCount()):
                    item = table.item(r, c)
                    if item is None:
                        continue
                    leaf_path = item.data(Qt.UserRole + 1)
                    if not leaf_path:
                        continue
                    path = tuple(leaf_path)
                    dirty = _path_is_dirty(snap, live, path)
                    calibration = path in touched
                    _apply_dirty_style(item, dirty, calibration)
        finally:
            self._suppress_table_changed = False

    def _refresh_styles(self) -> None:
        """Public hook used by Save / Reload / external mutations."""
        self._apply_table_styles()

    def _on_table_item_changed(self, item: "QTableWidgetItem") -> None:
        """Commit an in-place table edit back into the JSON mirror.

        Coerces numeric text via the existing convention (try int first, then
        float, then leave as-is). On a successful write, the cell is flagged
        as a *user edit* (not calibration-touched) by REMOVING the leaf path
        from ``calibration_touched_paths`` — a hand-edit replaces any prior
        calibration value. If the new value happens to match snapshot, the
        bold styling drops.
        """
        if self._suppress_table_changed:
            return
        leaf_path = item.data(Qt.UserRole + 1)
        if not leaf_path:
            return
        path = tuple(leaf_path)
        text = item.text().strip()
        # Locate parent container + key/index for write-back.
        cur = self.state.qubit_parameters_json
        if not isinstance(cur, dict):
            return
        try:
            for seg in path[:-1]:
                if isinstance(cur, dict):
                    cur = cur[seg]
                else:
                    cur = cur[int(seg)]
            leaf_key = path[-1]
            # Read the prior value for fallback on parse failure.
            prior_found, prior_val = _leaf_at_path(
                self.state.qubit_parameters_json, path
            )
        except (KeyError, IndexError, TypeError, ValueError):
            return
        # Coerce: empty -> None, numeric -> int/float, "true"/"false" -> bool,
        # everything else -> string.
        new_val = self._coerce_cell_value(text, prior_val if prior_found else None)
        # Write into the parent container.
        try:
            if isinstance(cur, dict):
                cur[leaf_key] = new_val
            else:
                cur[int(leaf_key)] = new_val
        except (KeyError, IndexError, TypeError, ValueError):
            return
        # User keystroke overrides any calibration tag for this path.
        self.state.calibration_touched_paths.discard(path)
        # Re-render the cell text (e.g. "0.05" -> coerced float prints "0.05")
        # AND the per-cell style. Suppress reentry on text update.
        self._suppress_table_changed = True
        try:
            item.setText(self._fmt_cell(new_val))
        finally:
            self._suppress_table_changed = False
        snap = self.state.qubit_parameters_json_snapshot or {}
        dirty = _path_is_dirty(snap, self.state.qubit_parameters_json, path)
        _apply_dirty_style(item, dirty, calibration_touched=False)
        # Bubble the dirty/clean transition to the row-label and FF-tab combos
        # — both are computed at render time. A cheap re-render of the current
        # selection covers the row-label transition; FF combos restyle below.
        try:
            ff_tab = self.get_main().ff_freq_tab if hasattr(self.get_main(), "ff_freq_tab") else None
        except Exception:
            ff_tab = None
        if ff_tab is not None:
            try:
                ff_tab._apply_combo_styles()
            except Exception:
                pass

    @staticmethod
    def _coerce_cell_value(text: str, prior):
        """Best-effort coercion for table edits.

        Empty string -> None. Try the prior value's type first (so ints stay
        ints, floats stay floats), then fall back to int -> float -> str.
        """
        if text == "":
            return None
        if text.lower() in ("true", "false"):
            return text.lower() == "true"
        # Preserve prior int vs float typing where possible.
        if isinstance(prior, bool):
            return text.lower() == "true"
        if isinstance(prior, int) and not isinstance(prior, bool):
            try:
                return int(text)
            except ValueError:
                pass
        if isinstance(prior, float):
            try:
                return float(text)
            except ValueError:
                pass
        try:
            return int(text)
        except ValueError:
            pass
        try:
            return float(text)
        except ValueError:
            return text


# ---------------------------------------------------------------------------
# FF -> Frequencies plot tab.
#
# Pulls section-by-section FF gain arrays out of qubit_parameters.json
# (Pulse / Init / Ramp / Dynamics / Readout), runs each one through
# PlotFrequenciesExperiment.ff_gains_to_freqs, and plots 8 per-qubit
# trajectories across the sections.
# ---------------------------------------------------------------------------


# Hardcoded coupled-pair list copied from
# WorkingProjects.triangle_lattice_quench.Flux_Files.plot_frequencies
# (PlotFrequenciesExperiment.coupled_pairs). Kept inline so this tab can warn
# about crossings even when plot_frequencies fails to import.
_FF_FREQ_COUPLED_PAIRS: list[tuple[int, int]] = [
    # top rail
    (1, 3), (3, 5), (5, 7),
    # bottom rail
    (2, 4), (4, 6), (6, 8),
    # diagonals (up-right)
    (2, 3), (4, 5), (6, 7),
    # diagonals (down-right)
    (1, 4), (3, 6), (5, 8),
]


class CalculatorTable(QTableWidget):
    """QTableWidget that fans bulk-typed digits across the current selection.

    Behaviour:
      - Multi-cell extended selection (set up by EntryEditDialog).
      - On a printable keystroke when >=2 cells are selected, intercept the
        key before Qt's default editor takes the anchor cell; remember the
        full selection; start the editor on the anchor with the keystroke
        as the initial text; on commit, fan the committed text out to every
        cell in the saved selection.
      - The "Set selected to" side widget in EntryEditDialog uses
        ``set_selection_value`` and is the guaranteed fallback.

    Coupling between columns (Frequency/Flux/Gain) is left to the dialog;
    this widget is column-agnostic.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Anchor + selection captured at keyPress time, restored when the
        # editor commits via cellChanged.
        self._fanout_cells: list[tuple[int, int]] = []
        self._fanout_active = False
        self._fan_suppress = False
        self.cellChanged.connect(self._on_cell_changed_fanout)

    @staticmethod
    def _is_printable(text: str) -> bool:
        if not text:
            return False
        # Allow digits, sign, decimal point, exponent letters — anything that
        # could start a numeric literal.
        return any(c.isalnum() or c in "+-.eE" for c in text)

    def keyPressEvent(self, event):  # type: ignore[override]
        sel = self.selectedIndexes()
        if len(sel) >= 2 and self._is_printable(event.text()):
            # Remember every selected cell, anchor first. We compare via
            # (row, col) tuples so the editor's later commit can find them.
            anchor = (self.currentRow(), self.currentColumn())
            self._fanout_cells = [(ix.row(), ix.column()) for ix in sel]
            if anchor not in self._fanout_cells:
                self._fanout_cells.append(anchor)
            self._fanout_active = True
            # Fall through to default — Qt opens the editor on the anchor
            # cell and seeds it with event.text().
        else:
            self._fanout_active = False
        super().keyPressEvent(event)

    def _on_cell_changed_fanout(self, r: int, c: int) -> None:
        if not self._fanout_active or self._fan_suppress:
            return
        item = self.item(r, c)
        if item is None:
            return
        new_text = item.text()
        targets = [(rr, cc) for (rr, cc) in self._fanout_cells if (rr, cc) != (r, c)]
        self._fanout_active = False
        if not targets:
            return
        self._fan_suppress = True
        try:
            for rr, cc in targets:
                tgt = self.item(rr, cc)
                if tgt is None:
                    tgt = QTableWidgetItem("")
                    self.setItem(rr, cc, tgt)
                tgt.setText(new_text)
        finally:
            self._fan_suppress = False

    def set_selection_value(self, value: str) -> None:
        """Backup path: explicit Apply button writes ``value`` into every
        selected cell. Bypasses the keystroke-fanout machinery entirely.
        """
        sel = self.selectedIndexes()
        if not sel:
            return
        self._fan_suppress = True
        try:
            for ix in sel:
                item = self.item(ix.row(), ix.column())
                if item is None:
                    item = QTableWidgetItem("")
                    self.setItem(ix.row(), ix.column(), item)
                item.setText(value)
        finally:
            self._fan_suppress = False


class EntryEditDialog(QDialog):
    """Modal editor for a single ramp_groups / dynamics_groups entry.

    Three sections, top to bottom:
      1. Name + Group header.
      2. FF gains editor (one row per FF channel, columns dynamic from the
         entry's actual keys — e.g. Init_FF_delta + Expt_FF_delta for ramp).
      3. Calculator (8 rows = qubits, 3 columns = Frequency/Flux/Gain) with
         multi-cell bulk typing and a guaranteed "Set selected to" fallback.

    The calculator's coupling between columns is intentionally NOT wired —
    ``self._conversion_wired`` defaults to False and ``_freq_to_gain`` /
    ``_gain_to_freq`` raise NotImplementedError. Wire those when the
    conversion is available; the change-handlers already consult the flag.
    """

    NS_LABELS = {
        "ramp_groups": "ramp",
        "dynamics_groups": "dynamics",
    }

    def __init__(self, jd: dict, namespace: str, group: str,
                 entry_name: str, *, source_entry: Optional[dict] = None,
                 mode: str = "edit", n_qubits: int = 8, parent=None):
        """
        Args:
          jd:            shared qubit_parameters_json dict (used for collision
                         checks; we do not mutate it until on_apply).
          namespace:     'ramp_groups' or 'dynamics_groups'.
          group:         containing group name.
          entry_name:    initial entry name (suggested for new / copy modes).
          source_entry:  the entry dict to clone fields from (None for blank).
          mode:          'new' | 'duplicate' | 'edit'.
        """
        super().__init__(parent)
        self._jd = jd
        self._ns = namespace
        self._group = group
        self._mode = mode
        self._original_name = entry_name if mode == "edit" else None
        self._n_qubits = int(n_qubits)
        self._conversion_wired = False  # flip when gain<->flux<->freq lands

        kind = self.NS_LABELS.get(namespace, namespace)
        self.setWindowTitle(f"{mode.title()} {kind} entry: {group} / {entry_name}")
        self.resize(720, 640)

        # Snapshot the opened values for the "modified cell" bold styling.
        self._opening_name = entry_name
        self._opening_values: dict[tuple[str, int], object] = {}

        layout = QVBoxLayout(self)

        # --- Name + Group header ---
        header_form = QFormLayout()
        self.name_edit = QLineEdit(entry_name)
        self.name_edit.selectAll()
        self.name_edit.textChanged.connect(self._on_name_changed)
        header_form.addRow("Name", self.name_edit)
        header_form.addRow("Group", QLabel(f"{group}  ({namespace})"))
        layout.addLayout(header_form)
        # Inline validation error label for name collisions.
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #a32a2a;")
        layout.addWidget(self.error_label)

        # --- FF gains editor ---
        ff_box = QGroupBox("FF gains")
        ff_lay = QVBoxLayout(ff_box)
        ff_lay.addWidget(QLabel(
            "Per-qubit FF gains for this entry. Bold = changed from open."
        ))
        self.ff_columns: list[str] = self._ff_columns_for(source_entry, namespace)
        self.ff_table = QTableWidget(self._n_qubits, len(self.ff_columns))
        self.ff_table.setHorizontalHeaderLabels(self.ff_columns)
        self.ff_table.setVerticalHeaderLabels([f"Q{i+1}" for i in range(self._n_qubits)])
        # Seed values from the source entry (or zeros / null for new).
        self._fill_ff_table(source_entry)
        self.ff_table.itemChanged.connect(self._on_ff_item_changed)
        ff_lay.addWidget(self.ff_table)
        layout.addWidget(ff_box, 1)

        # --- Calculator ---
        calc_box = QGroupBox("Calculator")
        calc_lay = QVBoxLayout(calc_box)
        warn = QLabel(
            "TODO: wire gain-to-flux conversion code here to automatically "
            "generate gains from desired frequencies, or see expected "
            "frequencies from chosen gains. For now, the three columns are "
            "independent and do not auto-update each other."
        )
        warn.setWordWrap(True)
        warn.setStyleSheet("color: #884400; font-style: italic;")
        calc_lay.addWidget(warn)

        self.calc_table = CalculatorTable(self._n_qubits, 3)
        self.calc_table.setHorizontalHeaderLabels(["Frequency (MHz)", "Flux (Φ₀)", "Gain (DAC)"])
        self.calc_table.setVerticalHeaderLabels([f"Q{i+1}" for i in range(self._n_qubits)])
        self.calc_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.calc_table.setSelectionBehavior(QAbstractItemView.SelectItems)
        for r in range(self._n_qubits):
            for c in range(3):
                self.calc_table.setItem(r, c, QTableWidgetItem(""))
        # cellChanged handler: future home of column-coupling propagation.
        self.calc_table.cellChanged.connect(self._on_calc_cell_changed)
        calc_lay.addWidget(self.calc_table)

        # Belt-and-suspenders "Set selected to" widget.
        set_row = QHBoxLayout()
        set_row.addWidget(QLabel("Set selected to:"))
        self.bulk_edit = QLineEdit()
        self.bulk_edit.setPlaceholderText("value to write into every selected cell")
        set_row.addWidget(self.bulk_edit, 1)
        self.bulk_apply_btn = QPushButton("Apply")
        self.bulk_apply_btn.clicked.connect(self._on_bulk_apply)
        set_row.addWidget(self.bulk_apply_btn)
        calc_lay.addLayout(set_row)

        # "Apply gain to entry" — copy the calc's Gain column to a chosen
        # FF-editor column. Active regardless of conversion-wired (the user
        # may have pasted hand-entered gains).
        apply_row = QHBoxLayout()
        apply_row.addWidget(QLabel("Apply Gain column to FF field:"))
        self.apply_target_combo = QComboBox()
        for col in self.ff_columns:
            self.apply_target_combo.addItem(col)
        apply_row.addWidget(self.apply_target_combo)
        self.apply_calc_btn = QPushButton("Apply")
        self.apply_calc_btn.clicked.connect(self._on_apply_calc_to_ff)
        apply_row.addWidget(self.apply_calc_btn)
        apply_row.addStretch(1)
        calc_lay.addLayout(apply_row)

        layout.addWidget(calc_box, 1)

        # --- bottom buttons ---
        bb = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Apply).setText("Apply")
        bb.button(QDialogButtonBox.Apply).clicked.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)

        # Compute and stash result. _on_accept fills these on success.
        self.result_name: Optional[str] = None
        self.result_entry: Optional[dict] = None

    # ---- FF column inference + seed ----

    @staticmethod
    def _ff_columns_for(source_entry: Optional[dict], ns: str) -> list[str]:
        """Decide which FF-array fields to expose as columns.

        Inspects the source entry's actual keys; falls back to a per-namespace
        default if the source is None (i.e. "New entry"):
          - ramp_groups:     Init_FF_delta, Expt_FF_delta
          - dynamics_groups: Dynamics_FF_abs, BS_FF_abs (whichever are present)
        Both branches preserve the source entry's key order if it has any
        array-valued field; unrecognized array fields are appended.
        """
        defaults = {
            "ramp_groups":     ["Init_FF_delta", "Expt_FF_delta"],
            "dynamics_groups": ["Dynamics_FF_abs", "BS_FF_abs"],
        }
        if not isinstance(source_entry, dict):
            return list(defaults.get(ns, []))
        cols: list[str] = []
        for k, v in source_entry.items():
            if isinstance(v, list) and (k.endswith("_FF") or "_FF_" in k):
                cols.append(k)
        if not cols:
            cols = list(defaults.get(ns, []))
        return cols

    def _fill_ff_table(self, source_entry: Optional[dict]) -> None:
        """Seed the FF table from ``source_entry``; record opening values."""
        self.ff_table.blockSignals(True)
        try:
            for c, col in enumerate(self.ff_columns):
                arr = (source_entry or {}).get(col)
                # Accept lists or None. None -> blank cells (treated as
                # "field absent" on commit; the user can fill in to add it).
                for r in range(self._n_qubits):
                    val = None
                    if isinstance(arr, list) and r < len(arr):
                        val = arr[r]
                    item = QTableWidgetItem("" if val is None else str(val))
                    self.ff_table.setItem(r, c, item)
                    self._opening_values[(col, r)] = val
        finally:
            self.ff_table.blockSignals(False)

    # ---- name + collision handling ----

    def _existing_names(self) -> set:
        entries = (self._jd.get(self._ns, {}) or {}).get(self._group, {}).get("entries", {}) or {}
        names = set(entries.keys())
        if self._mode == "edit" and self._original_name is not None:
            names.discard(self._original_name)
        return names

    def _on_name_changed(self, _t: str) -> None:
        # Inline-validate and surface the error label; commit happens on Apply.
        name = self.name_edit.text().strip()
        if not name:
            self.error_label.setText("Name is required.")
        elif name in self._existing_names():
            self.error_label.setText(f"Name collision: {name!r} already exists in {self._group}.")
        else:
            self.error_label.setText("")
        # Bold the name edit when it differs from open value.
        f = self.name_edit.font()
        f.setBold(name != self._opening_name)
        self.name_edit.setFont(f)

    # ---- FF table edit -> bold ----

    def _on_ff_item_changed(self, item: QTableWidgetItem) -> None:
        r, c = item.row(), item.column()
        col_name = self.ff_columns[c] if 0 <= c < len(self.ff_columns) else None
        if col_name is None:
            return
        new_text = item.text().strip()
        opening = self._opening_values.get((col_name, r))
        # Compare against opening to drive bold styling.
        new_val = self._parse_ff_value(new_text)
        differs = new_val != opening if (new_val is not None or opening is not None) else False
        f = item.font(); f.setBold(bool(differs)); item.setFont(f)

    @staticmethod
    def _parse_ff_value(text: str):
        """Parse a single FF cell. Empty -> None; ints stay ints; floats float."""
        if text == "" or text.lower() == "null":
            return None
        try:
            return int(text)
        except ValueError:
            pass
        try:
            return float(text)
        except ValueError:
            return text

    # ---- calculator handlers ----

    def _on_calc_cell_changed(self, r: int, c: int) -> None:
        """Single source of truth for future column coupling.

        Currently a no-op on other columns because the conversion is unwired
        (``self._conversion_wired = False``). When the stubs below are
        implemented, this handler should propagate the change to the other
        two columns of the same qubit row.
        """
        if not self._conversion_wired:
            return
        # NOTE: when wired, route through _freq_to_gain / _gain_to_freq /
        # _flux_to_gain etc., write into the OTHER two columns via
        # blockSignals(True)/(False) to avoid recursion. Kept as a sentinel
        # so the structure of the eventual call site is obvious.

    def _freq_to_gain(self, q_idx: int, freq_mhz: float, flux: float):  # noqa: ARG002
        """Stub: convert (qubit, target frequency, current flux) -> DAC gain."""
        raise NotImplementedError(
            "_freq_to_gain not wired yet — see _conversion_wired flag."
        )

    def _gain_to_freq(self, q_idx: int, gain: float):  # noqa: ARG002
        """Stub: convert (qubit, DAC gain) -> expected frequency in MHz."""
        raise NotImplementedError(
            "_gain_to_freq not wired yet — see _conversion_wired flag."
        )

    def _on_bulk_apply(self) -> None:
        text = self.bulk_edit.text().strip()
        if not text:
            return
        self.calc_table.set_selection_value(text)

    def _on_apply_calc_to_ff(self) -> None:
        """Copy the calculator's Gain column into the selected FF column."""
        target_col_name = self.apply_target_combo.currentText()
        if target_col_name not in self.ff_columns:
            return
        target_c = self.ff_columns.index(target_col_name)
        for r in range(self._n_qubits):
            calc_item = self.calc_table.item(r, 2)  # column 2 = Gain
            if calc_item is None:
                continue
            txt = calc_item.text().strip()
            if txt == "":
                continue
            ff_item = self.ff_table.item(r, target_c)
            if ff_item is None:
                ff_item = QTableWidgetItem("")
                self.ff_table.setItem(r, target_c, ff_item)
            ff_item.setText(txt)

    # ---- commit ----

    def _on_accept(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            self.error_label.setText("Name is required.")
            return
        if name in self._existing_names():
            self.error_label.setText(
                f"Name collision: {name!r} already exists in {self._group}."
            )
            return
        # Build the entry dict. Start from the source-entry layout we opened
        # with so non-FF keys (Expt_FF, _recipe, etc.) round-trip unchanged.
        entries = (self._jd.get(self._ns, {}) or {}).get(self._group, {}).get("entries", {}) or {}
        src = entries.get(self._original_name) if self._mode == "edit" else (
            entries.get(self._opening_name) if self._mode == "duplicate" else None
        )
        new_entry: dict = copy.deepcopy(src) if isinstance(src, dict) else {}

        # Update each FF column from the table. Treat blank columns as
        # "field absent" on creation (drop the key) when the whole column
        # is empty; otherwise write a list with None in blank slots.
        for c, col in enumerate(self.ff_columns):
            arr: list = []
            all_blank = True
            for r in range(self._n_qubits):
                item = self.ff_table.item(r, c)
                txt = item.text().strip() if item is not None else ""
                if txt == "":
                    arr.append(None)
                else:
                    all_blank = False
                    arr.append(self._parse_ff_value(txt))
            if all_blank:
                # Don't introduce an all-blank field. Preserve existing if any.
                if col in new_entry:
                    new_entry.pop(col, None)
                continue
            new_entry[col] = arr

        self.result_name = name
        self.result_entry = new_entry
        self.accept()


class FFFrequenciesTab(QWidget):
    """Trajectory plot of dressed qubit frequencies across experiment sections.

    For each experimental stage (Readout, Drive, Ramp, Dynamics) the user
    picks a group AND optionally an entry from `qubit_parameters.json`. The
    plot shows the 8-qubit frequency trajectory through every stage that
    resolves to a non-null FF array. Per-qubit visibility toggles let the
    user isolate subsets of traces.

    Resolution rules per stage (see _resolve_*_section docstrings for the
    precise per-stage decision table):
      - If the selected group has a group-level FF (e.g. `readout_3800` with
        `Readout_FF`+`Pulse_FF`, or `ramp_3800` with `Expt_FF`), that FF is
        used and the entry is OPTIONAL — picking an entry only affects
        non-FF fields (and, for ramp entries, can supply an Init section
        and/or override Expt_FF via delta arrays).
      - If the group has NO group-level FF (e.g. `ramsey_3800+` is recipe-
        only; `dynamics_FF_points` is per-entry), an entry MUST be picked
        for the stage to contribute a section. Group-only is skipped.
    """

    name = "FF Frequencies"

    NONE_LABEL = "(none)"
    DRIVE_FALLBACK_LABEL = "(readout)"  # drive combo only — falls back to readout group's entries

    def __init__(self, state: CalibState, get_main, parent=None):
        super().__init__(parent)
        self.state = state
        self.get_main = get_main
        # JSON is owned by QubitParametersTab; we just read from state via
        # the `_jd` property below. Refreshes are triggered by
        # MainWindow._on_qubit_params_loaded → self.refresh_from_state().

        # --- per-stage group+entry selectors (two combos per stage) ---
        # Each stage gets a QGroupBox containing a group combo (top) and an
        # entry combo (bottom). Both default to (none); picking a group
        # refreshes its entry combo to that group's `entries` keys.
        def _make_stage_box(title: str) -> tuple[QComboBox, QComboBox, QGroupBox]:
            group = QComboBox()
            entry = QComboBox()
            box = QGroupBox(title)
            lay = QVBoxLayout(box)
            lay.addWidget(QLabel("Group"))
            lay.addWidget(group)
            lay.addWidget(QLabel("Entry"))
            lay.addWidget(entry)
            lay.addStretch(1)
            return group, entry, box

        (self.readout_group_combo, self.readout_entry_combo,
         readout_box) = _make_stage_box("Readout stage")
        (self.drive_group_combo, self.drive_entry_combo,
         drive_box) = _make_stage_box("Drive (Pulse) stage")
        (self.ramp_group_combo, self.ramp_entry_combo,
         ramp_box) = _make_stage_box("Ramp stage")
        (self.dynamics_group_combo, self.dynamics_entry_combo,
         dynamics_box) = _make_stage_box("Dynamics stage")

        # Wire group→entry refresh per stage. The wiring is by namespace so
        # the same handler works for every stage. We deliberately reset the
        # entry combo to (none) on every group change — picking a new group
        # almost never preserves the meaning of the old entry name.
        self.readout_group_combo.currentTextChanged.connect(
            lambda _t: (self._refresh_entry_combo(
                self.readout_group_combo, self.readout_entry_combo,
                "readout_groups",
            ), self._on_plot())
        )
        self.drive_group_combo.currentTextChanged.connect(
            lambda _t: (self._refresh_entry_combo(
                self.drive_group_combo, self.drive_entry_combo,
                # Drive group combo includes BOTH drive_groups and
                # readout_groups (parity with _build_resolve_drive's
                # fallback search).
                ("drive_groups", "readout_groups"),
            ), self._on_plot())
        )
        self.ramp_group_combo.currentTextChanged.connect(
            lambda _t: (self._refresh_entry_combo(
                self.ramp_group_combo, self.ramp_entry_combo,
                "ramp_groups",
            ), self._on_plot())
        )
        self.dynamics_group_combo.currentTextChanged.connect(
            lambda _t: (self._refresh_entry_combo(
                self.dynamics_group_combo, self.dynamics_entry_combo,
                "dynamics_groups",
            ), self._on_plot())
        )
        # Entry combos: replot on entry change too (group change above also
        # resets the entry combo to (none) which fires this signal — single
        # replot per group change is fine).
        self.readout_entry_combo.currentTextChanged.connect(lambda _t: self._on_plot())
        self.drive_entry_combo.currentTextChanged.connect(lambda _t: self._on_plot())
        self.ramp_entry_combo.currentTextChanged.connect(lambda _t: self._on_plot())
        self.dynamics_entry_combo.currentTextChanged.connect(lambda _t: self._on_plot())

        # Per-group/entry CRUD buttons (ramp + dynamics only). Each row carries
        # six buttons: entry New/Duplicate/Edit and group New/Duplicate/Edit.
        def _make_crud_row(label: str, kind: str) -> tuple[QWidget, dict]:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.addWidget(QLabel(label))
            buttons: dict = {}
            for key, txt in (
                ("entry_new",   "New entry"),
                ("entry_dup",   "Duplicate entry"),
                ("entry_edit",  "Edit entry"),
                ("group_new",   "New group"),
                ("group_dup",   "Dup. group"),
                ("group_edit",  "Rename group"),
            ):
                b = QPushButton(txt)
                buttons[key] = b
                row.addWidget(b)
            row.addStretch(1)
            w = QWidget()
            w.setLayout(row)
            return w, buttons

        ramp_crud_w, self.ramp_crud_btns = _make_crud_row("Ramp:", "ramp_groups")
        dyn_crud_w,  self.dyn_crud_btns  = _make_crud_row("Dynamics:", "dynamics_groups")

        # Wire each button to a single handler keyed on (namespace, action).
        def _wire(buttons: dict, ns: str, group_combo: QComboBox,
                  entry_combo: QComboBox) -> None:
            buttons["entry_new"].clicked.connect(
                lambda: self._on_crud_entry(ns, group_combo, entry_combo, "new")
            )
            buttons["entry_dup"].clicked.connect(
                lambda: self._on_crud_entry(ns, group_combo, entry_combo, "duplicate")
            )
            buttons["entry_edit"].clicked.connect(
                lambda: self._on_crud_entry(ns, group_combo, entry_combo, "edit")
            )
            buttons["group_new"].clicked.connect(
                lambda: self._on_crud_group(ns, group_combo, "new")
            )
            buttons["group_dup"].clicked.connect(
                lambda: self._on_crud_group(ns, group_combo, "duplicate")
            )
            buttons["group_edit"].clicked.connect(
                lambda: self._on_crud_group(ns, group_combo, "rename")
            )
        _wire(self.ramp_crud_btns, "ramp_groups",
              self.ramp_group_combo, self.ramp_entry_combo)
        _wire(self.dyn_crud_btns,  "dynamics_groups",
              self.dynamics_group_combo, self.dynamics_entry_combo)

        selectors = QHBoxLayout()
        selectors.addWidget(readout_box,  1)
        selectors.addWidget(drive_box,    1)
        selectors.addWidget(ramp_box,     1)
        selectors.addWidget(dynamics_box, 1)
        selectors_w = QWidget()
        selectors_w.setLayout(selectors)

        # --- controls row: smoothing checkbox only ---
        # No Plot button — every selector replots automatically. The JSON
        # is reloaded centrally via QubitParametersTab → orchestrator notifies
        # this tab through refresh_from_state(), so no per-tab Reload button.
        self.smooth_cb = QCheckBox("Smooth ramp segment")
        self.smooth_cb.setChecked(True)
        self.smooth_cb.stateChanged.connect(lambda _s: self._on_plot())

        controls = QHBoxLayout()
        controls.addWidget(self.smooth_cb)
        controls.addStretch(1)
        controls_w = QWidget()
        controls_w.setLayout(controls)

        # --- per-qubit visibility row: drag/shift-click selectable list ---
        # Each visible item == that qubit is plotted. All selected by default.
        self.qubit_list = QListWidget()
        # MultiSelection: each click TOGGLES that item's selection without
        # touching the others. Drag passes the toggle across items it touches.
        # Easier than ExtendedSelection for "hide just Q2" style edits.
        self.qubit_list.setSelectionMode(QAbstractItemView.MultiSelection)
        self.qubit_list.setFlow(QListWidget.LeftToRight)
        self.qubit_list.setFixedHeight(36)
        self.qubit_list.setSpacing(2)
        for qi in range(1, 9):
            it = QListWidgetItem(f"Q{qi}")
            it.setData(Qt.UserRole, qi - 1)  # store 0-based index
            self.qubit_list.addItem(it)
            it.setSelected(True)
        self.qubit_list.itemSelectionChanged.connect(self._on_plot)
        qubit_row = QHBoxLayout()
        qubit_row.addWidget(QLabel("Show (drag/shift-click):"))
        qubit_row.addWidget(self.qubit_list, 1)
        qubit_row_w = QWidget()
        qubit_row_w.setLayout(qubit_row)

        # --- canvas (taller than other tabs so 8 traces resolve cleanly) ---
        self.canvas = MplCanvas(self, height=7.0)
        self.canvas.setMinimumHeight(500)
        self.toolbar_mpl = NavigationToolbar(self.canvas, self)

        # --- layout ---
        layout = QVBoxLayout(self)
        layout.addWidget(selectors_w)
        # CRUD rows scoped to ramp + dynamics only (per spec).
        layout.addWidget(ramp_crud_w)
        layout.addWidget(dyn_crud_w)
        layout.addWidget(controls_w)
        layout.addWidget(qubit_row_w)
        layout.addWidget(self.toolbar_mpl)
        layout.addWidget(self.canvas, 1)

        # Initial population — QubitParametersTab loads the JSON before us
        # in MainWindow.__init__, so state.qubit_parameters_json is already
        # populated here. Subsequent reloads come through refresh_from_state().
        self._populate_selectors()
        self._apply_combo_styles()

    # ----- JSON state hookup / selector population -----

    @property
    def _jd(self) -> dict:
        """Shared JSON dict owned by CalibState (loaded by QubitParametersTab)."""
        return self.state.qubit_parameters_json or {}

    def refresh_from_state(self) -> None:
        """Called by MainWindow._on_qubit_params_loaded whenever the shared
        qubit_parameters_json is reloaded. Re-populates selectors and replots
        while preserving combo selections where possible. Also restyles
        combos so groups/entries with unsaved changes are visibly bolded.
        """
        self._reload_and_populate_keep_selection()
        self._apply_combo_styles()

    def _group_names(self, namespace: str) -> list[str]:
        """Return the group keys under `jd[namespace]` in insertion order."""
        ns = self._jd.get(namespace, {})
        if not isinstance(ns, dict):
            return []
        return [n for n, g in ns.items() if isinstance(g, dict)]

    def _populate_selectors(self) -> None:
        """Fill every group combo from `self._jd` and reset all entries to (none).

        Block signals while we fill so the group-change handlers don't fire
        spuriously and clear out a peer combo we're about to populate.
        """
        # --- Readout: groups from `readout_groups`. Auto-select the first
        # real group (preserving prior UX where the readout combo was
        # never blank by default — the trajectory needs a readout anchor
        # at the right edge). The other three stages stay at (none). ---
        readout_groups = self._group_names("readout_groups")
        self._fill_group_combo(self.readout_group_combo, readout_groups)
        if readout_groups:
            # findText is +1 because index 0 is the (none) sentinel.
            self.readout_group_combo.setCurrentIndex(1)
        # Refresh fires the wired handler too, but we call it explicitly here
        # for clarity (idempotent).
        self._refresh_entry_combo(
            self.readout_group_combo, self.readout_entry_combo,
            "readout_groups",
        )

        # --- Drive: groups from `drive_groups` AND `readout_groups` (parity
        # with _build_resolve_drive's fallback search). Order: drives first,
        # then readouts. No filtering by "has group Pulse_FF" — recipe-only
        # groups like ramsey_3800+ MUST be exposed so the user can pick an
        # entry under them. ---
        # Drive combo lists only true drive_groups. Sentinel at index 0 is
        # "(readout)" meaning "fall back to the readout group's entries".
        self.drive_group_combo.blockSignals(True)
        self.drive_group_combo.clear()
        self.drive_group_combo.addItem(self.DRIVE_FALLBACK_LABEL)
        for n in self._group_names("drive_groups"):
            self.drive_group_combo.addItem(n)
        self.drive_group_combo.setCurrentIndex(0)
        self.drive_group_combo.blockSignals(False)
        self._refresh_entry_combo(
            self.drive_group_combo, self.drive_entry_combo,
            ("drive_groups", "readout_groups"),
        )

        # --- Ramp: groups from `ramp_groups`. ---
        self._fill_group_combo(self.ramp_group_combo,
                               self._group_names("ramp_groups"))
        self._refresh_entry_combo(
            self.ramp_group_combo, self.ramp_entry_combo, "ramp_groups",
        )

        # --- Dynamics: groups from `dynamics_groups`. ---
        self._fill_group_combo(self.dynamics_group_combo,
                               self._group_names("dynamics_groups"))
        self._refresh_entry_combo(
            self.dynamics_group_combo, self.dynamics_entry_combo,
            "dynamics_groups",
        )

    def _fill_group_combo(self, combo: QComboBox, names: list[str]) -> None:
        """Clear+refill a group combo with [(none), *names]; reset to (none)."""
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(self.NONE_LABEL)
        for n in names:
            combo.addItem(n)
        combo.setCurrentIndex(0)
        combo.blockSignals(False)

    def _refresh_entry_combo(self,
                             group_combo: QComboBox,
                             entry_combo: QComboBox,
                             namespace) -> None:
        """Refill `entry_combo` with the entries of `group_combo`'s current group.

        `namespace` is either a single string or a tuple of namespaces to
        search (for the drive stage which spans drive_groups+readout_groups).
        Picking (none) for the group clears+disables the entry combo.
        """
        group_name = group_combo.currentText()
        entry_combo.blockSignals(True)
        entry_combo.clear()
        entry_combo.addItem(self.NONE_LABEL)
        if not group_name or group_name == self.NONE_LABEL:
            entry_combo.setCurrentIndex(0)
            entry_combo.setEnabled(False)
            entry_combo.blockSignals(False)
            return

        namespaces = (namespace,) if isinstance(namespace, str) else tuple(namespace)
        entries: dict = {}
        for ns in namespaces:
            group = self._jd.get(ns, {}).get(group_name)
            if isinstance(group, dict):
                entries = group.get("entries", {}) or {}
                if entries:
                    break

        for entry_name in entries.keys():
            entry_combo.addItem(entry_name)
        entry_combo.setCurrentIndex(0)
        entry_combo.setEnabled(True)
        entry_combo.blockSignals(False)

    def _reload_and_populate_keep_selection(self) -> None:
        """Re-read shared state and preserve every combo selection where possible.

        Capture all 8 selections FIRST (group+entry per stage), then refill
        from state, then restore group selections (which fires the group-
        change handlers and refills the entry combos), then restore entries.
        """
        prev = {
            "readout_group":  self.readout_group_combo.currentText(),
            "readout_entry":  self.readout_entry_combo.currentText(),
            "drive_group":    self.drive_group_combo.currentText(),
            "drive_entry":    self.drive_entry_combo.currentText(),
            "ramp_group":     self.ramp_group_combo.currentText(),
            "ramp_entry":     self.ramp_entry_combo.currentText(),
            "dynamics_group": self.dynamics_group_combo.currentText(),
            "dynamics_entry": self.dynamics_entry_combo.currentText(),
        }
        self._populate_selectors()

        # Restore group selections first; each setCurrentIndex triggers the
        # entry refresh via the group-change handler. Then restore the entry
        # selections by text where they still exist.
        def _restore(combo: QComboBox, text: str) -> None:
            idx = combo.findText(text)
            if idx >= 0:
                combo.setCurrentIndex(idx)

        _restore(self.readout_group_combo,  prev["readout_group"])
        _restore(self.drive_group_combo,    prev["drive_group"])
        _restore(self.ramp_group_combo,     prev["ramp_group"])
        _restore(self.dynamics_group_combo, prev["dynamics_group"])
        _restore(self.readout_entry_combo,  prev["readout_entry"])
        _restore(self.drive_entry_combo,    prev["drive_entry"])
        _restore(self.ramp_entry_combo,     prev["ramp_entry"])
        _restore(self.dynamics_entry_combo, prev["dynamics_entry"])

    # ----- helpers -----

    @staticmethod
    def _segment_intersection(p1, p2, p3, p4):
        """Return the (x, y) intersection of segments p1-p2 and p3-p4 if it
        lies within both segments; else None. Copy of
        PlotFrequenciesExperiment._segment_intersection."""
        x1, y1 = p1
        x2, y2 = p2
        x3, y3 = p3
        x4, y4 = p4
        denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(denom) < 1e-12:
            return None
        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
        u = ((x1 - x3) * (y1 - y2) - (y1 - y3) * (x1 - x2)) / denom
        if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
            xi = x1 + t * (x2 - x1)
            yi = y1 + t * (y2 - y1)
            return (xi, yi)
        return None

    def _visible_qubits(self) -> list[int]:
        """0-based qubit indices currently selected in the qubit list."""
        return [
            int(it.data(Qt.UserRole))
            for it in self.qubit_list.selectedItems()
        ]

    # ----- plot pipeline -----

    # ----- per-stage resolvers -----
    #
    # Each takes (jd, group_name, entry_name) where empty/"(none)" strings
    # represent "not selected". Returns the resolved FF dict, or None if the
    # stage contributes no section. These factor the per-stage decision tree
    # out of _resolve_sections so the rules are testable in isolation.

    def _resolve_readout_section(self, jd: dict, group_name: str,
                                 entry_name: str):
        """Return {'Readout_FF': [...], 'Pulse_FF': [...]} for the readout stage,
        or None when no group is selected.

        Readout groups in the current schema always have group-level
        `Readout_FF` and `Pulse_FF`, so the entry is purely optional
        (entry-level non-FF fields aren't consumed by the trajectory plot).
        """
        if not group_name or group_name == self.NONE_LABEL:
            return None
        rg = jd.get("readout_groups", {}).get(group_name)
        if rg is None:
            raise KeyError(f"Readout group {group_name!r} not in readout_groups.")
        base = jd.get("base_params", {})
        # readout_3800 always has Readout_FF + Pulse_FF; defensively allow
        # either to be missing by skipping that part of the section.
        readout_ff = rg.get("Readout_FF")
        pulse_ff = rg.get("Pulse_FF")
        if readout_ff is None:
            raise KeyError(
                f"Readout group {group_name!r} is missing Readout_FF; "
                f"cannot plot a Readout section."
            )
        return {
            "Readout_FF": list(_build_deref_base(readout_ff, base)),
            "Pulse_FF":   (None if pulse_ff is None
                           else list(_build_deref_base(pulse_ff, base))),
        }

    def _resolve_drive_section(self, jd: dict, group_name: str,
                               entry_name: str):
        """Return {'Pulse_FF': [...]} for the drive stage, or None to skip.

        Decision tree:
          - No group selected -> None.
          - Group has a group-level Pulse_FF (e.g. `4Q_readout`, or any
            readout_groups entry) -> use that array; entry is optional.
          - Group has NO group-level Pulse_FF (recipe-only, e.g.
            `ramsey_3800+`) -> require an entry; resolve via the existing
            `_build_resolve_drive` (which walks drive_groups +
            readout_groups, handles `_recipe` + `_recipe_arg`).
            If no entry selected, return None (skip the stage).
        """
        # Sentinel "(readout)" means "fall back to readout group" — handled
        # by the caller (resolve via the readout group's entry).
        if not group_name or group_name in (self.NONE_LABEL, self.DRIVE_FALLBACK_LABEL):
            return None
        base = jd.get("base_params", {})
        group = jd.get("drive_groups", {}).get(group_name)
        if not isinstance(group, dict):
            raise KeyError(f"Drive group {group_name!r} not in drive_groups.")

        # Group-level Pulse_FF wins when present — entry just contributes
        # non-FF fields (frequency / gain / sigma), which the trajectory
        # plot doesn't consume.
        if group.get("Pulse_FF") is not None:
            return {"Pulse_FF": list(_build_deref_base(group.get("Pulse_FF"), base))}

        # No group Pulse_FF -> entry is required.
        if not entry_name or entry_name == self.NONE_LABEL:
            return None
        return {"Pulse_FF": _build_resolve_drive(jd, entry_name)["Pulse_FF"]}

    def _resolve_ramp_sections(self, jd: dict, group_name: str,
                               entry_name: str):
        """Return {'Init_FF': [...] | None, 'Expt_FF': [...]} for ramp,
        or None when no group is selected.

        - If no entry is selected, only the Expt section is plotted: use the
          group-level `Expt_FF` directly (always present in current schema's
          ramp_groups).
        - If an entry is selected, hand off to `_build_resolve_ramp`, which
          applies any `Expt_FF_delta` / `Expt_FF_abs` override and supplies
          an Init array (or None) from `Init_FF_delta` / `Init_FF_abs`.
        """
        if not group_name or group_name == self.NONE_LABEL:
            return None
        rg = jd.get("ramp_groups", {}).get(group_name)
        if rg is None:
            raise KeyError(f"Ramp group {group_name!r} not in ramp_groups.")
        base = jd.get("base_params", {})
        if entry_name and entry_name != self.NONE_LABEL:
            return _build_resolve_ramp(jd, entry_name)
        # Group only: Expt_FF from the group, no Init.
        expt_base = rg.get("Expt_FF")
        if expt_base is None:
            raise KeyError(
                f"Ramp group {group_name!r} is missing Expt_FF; "
                f"cannot plot a ramp Expt section without an entry."
            )
        return {"Init_FF": None,
                "Expt_FF": list(_build_deref_base(expt_base, base))}

    def _resolve_dynamics_section(self, jd: dict, group_name: str,
                                  entry_name: str):
        """Return {'Dynamics_FF' | 'BS_FF': [...]} for the dynamics stage,
        or None to skip.

        Current schema has no group-level dynamics FF; every dynamics entry
        carries its own `Dynamics_FF_abs` or `BS_FF_abs`, so an entry MUST
        be selected. Reuses `_build_resolve_dynamics`.
        """
        if not group_name or group_name == self.NONE_LABEL:
            return None
        if not entry_name or entry_name == self.NONE_LABEL:
            return None
        return _build_resolve_dynamics(jd, entry_name)

    def _resolve_sections(self) -> tuple[list[list[int]], list[str], list[str]]:
        """Build the section FF list across all four stages.

        Returns (sections, labels, warnings). Each stage contributes 0..2
        sections depending on its group+entry selection (see the four
        _resolve_*_section helpers for the per-stage rules). Section order
        is fixed: Pulse -> Init -> Ramp -> Dynamics -> Readout.
        """
        warnings: list[str] = []
        jd = self._jd

        # Capture every selection up-front.
        rd_group = self.readout_group_combo.currentText()
        rd_entry = self.readout_entry_combo.currentText()
        dr_group = self.drive_group_combo.currentText()
        dr_entry = self.drive_entry_combo.currentText()
        rp_group = self.ramp_group_combo.currentText()
        rp_entry = self.ramp_entry_combo.currentText()
        dy_group = self.dynamics_group_combo.currentText()
        dy_entry = self.dynamics_entry_combo.currentText()

        # Resolve each stage.
        readout_sec = self._resolve_readout_section(jd, rd_group, rd_entry)
        drive_sec   = self._resolve_drive_section(  jd, dr_group, dr_entry)
        ramp_sec    = self._resolve_ramp_sections(  jd, rp_group, rp_entry)
        dynamics_sec = self._resolve_dynamics_section(jd, dy_group, dy_entry)

        # The trajectory plot needs at least a readout reference at the right
        # edge, so insist on a readout group. (We still tolerate no other
        # stages — degenerate, but harmless.)
        if readout_sec is None:
            raise ValueError("No Readout group selected.")

        sections: list[list[int]] = []
        labels: list[str] = []

        # 1. Pulse: drive group's Pulse_FF (or readout group's Pulse_FF, if
        # the user picked a readout-namespace group for the drive stage; or
        # if no drive group selected, fall back to readout's Pulse_FF so the
        # left edge of the trajectory is still anchored).
        if drive_sec is not None and drive_sec.get("Pulse_FF") is not None:
            pulse_ff = list(drive_sec["Pulse_FF"])
        elif readout_sec.get("Pulse_FF") is not None:
            pulse_ff = list(readout_sec["Pulse_FF"])
        else:
            pulse_ff = None
            warnings.append(
                "No Pulse_FF available (no drive group selected and readout "
                "group has no Pulse_FF); skipping Pulse section."
            )
        if pulse_ff is not None:
            sections.append(pulse_ff)
            labels.append("Pulse")

        # 2-3. Init + Ramp. Init only appears when an entry is selected and
        # the entry's Init_FF is not null. Expt is always added when a ramp
        # group is selected.
        if ramp_sec is not None:
            init_ff = ramp_sec.get("Init_FF")
            if init_ff is not None:
                sections.append(list(init_ff))
                labels.append("Init")
            elif rp_entry and rp_entry != self.NONE_LABEL and pulse_ff is not None:
                # When an entry IS selected but its Init_FF is null (e.g.
                # "8Q_1854"), historical behaviour was to use Pulse_FF as
                # the Init reference so the ramp's start point is visible.
                sections.append(list(pulse_ff))
                labels.append("Init")
            sections.append(list(ramp_sec["Expt_FF"]))
            labels.append("Ramp")

        # 4. Dynamics.
        if dynamics_sec is not None:
            dyn_ff = dynamics_sec.get("Dynamics_FF") or dynamics_sec.get("BS_FF")
            if dyn_ff is None:
                warnings.append(
                    f"Dynamics entry {dy_entry!r} has neither Dynamics_FF nor "
                    f"BS_FF; skipping dynamics section."
                )
            else:
                sections.append(list(dyn_ff))
                labels.append("Dynamics")

        # 5. Readout — always last, anchors the right edge.
        sections.append(list(readout_sec["Readout_FF"]))
        labels.append("Readout")

        return sections, labels, warnings

    def _compute_frequencies(self, sections):
        """Run each 8-element FF gain array through the flux-model.

        Direct copy of `Flux_Files/plot_frequencies.py::ff_gains_to_freqs`;
        inlined to avoid that module's import-time failure path.
        """
        import numpy as np

        bare_qubits   = [f'Q{i}_bare' for i in range(1, 9)]
        bare_couplers = ['C1', 'C2', 'C3', 'C4', 'C5', 'C6']
        bare_all      = bare_qubits + bare_couplers
        FF_flux_quanta = np.array(
            [model_mapping[bq].flux_quantum_voltage for bq in bare_qubits]
        )

        out = []
        for ff_gains in sections:
            flux_changes  = np.asarray(ff_gains) / FF_flux_quanta
            target_fluxes = flux_vector + np.concatenate([flux_changes, np.zeros(6)])
            bare_freqs    = [1000 * model_mapping[name].freq(flux)
                             for name, flux in zip(bare_all, target_fluxes)]
            dressed_freqs, _g = full_device_calib.dress_system(
                bare_freqs, beta_matrix=beta_matrix, plot=False,
            )
            out.append(dressed_freqs)
        return np.array(out)

    def _on_plot(self) -> None:
        # Render from the in-memory JSON dict only — reloading from disk here
        # would re-populate the combos and recurse back into _on_plot via the
        # currentTextChanged auto-replot wiring. Use the Reload JSON button
        # to explicitly pick up disk changes.
        self.canvas.fig.clf()
        ax = self.canvas.fig.add_subplot(111)
        self.canvas.ax = ax

        try:
            sections, labels, warns = self._resolve_sections()
        except Exception as exc:
            ax.set_axis_off()
            ax.text(
                0.5, 0.5,
                f"Failed to resolve sections:\n{exc}\n\n{traceback.format_exc()}",
                ha="center", va="center", fontsize=8, family="monospace",
                wrap=True,
            )
            self.canvas.draw()
            return

        try:
            freqs = self._compute_frequencies(sections)  # shape (S, 8)
        except Exception as exc:
            ax.set_axis_off()
            ax.text(
                0.5, 0.5,
                "ff_gains_to_freqs call failed:\n"
                f"{exc}\n\n{traceback.format_exc()}",
                ha="center", va="center", fontsize=8, family="monospace",
                wrap=True,
            )
            self.canvas.draw()
            return

        self._build_plot(ax, sections, labels, freqs, warns)
        self.canvas.draw()

    # ----- plot building -----

    def _build_plot(self, ax, sections, labels, freqs, warns) -> None:
        """Render the per-qubit trajectory plot onto `ax`.

        Only qubits whose visibility checkbox is checked are drawn (lines,
        annotations, and crossing markers are all filtered by `visible`).
        """
        import numpy as np
        num_sections, num_qubits = freqs.shape
        xs = np.arange(num_sections, dtype=float)
        visible: set[int] = set(self._visible_qubits())

        # Init->Ramp segment indices to render with the cubic ease-out curve.
        smooth_pairs: set[int] = set()
        if self.smooth_cb.isChecked():
            for i in range(num_sections - 1):
                if labels[i] == "Init" and labels[i + 1] == "Ramp":
                    smooth_pairs.add(i)

        cmap = plt.get_cmap("tab10")
        for qi in range(num_qubits):
            if qi not in visible:
                continue
            color = cmap(qi % 10)
            y = freqs[:, qi]
            if not smooth_pairs:
                ax.plot(xs, y, "-o", color=color, label=f"Q{qi+1}")
            else:
                # Piecewise: straight line on every segment except the
                # Init->Ramp pair(s), which get the cubic ease-out curve.
                for i in range(num_sections - 1):
                    if i in smooth_pairs:
                        xc, yc = self._ease_out_segment(xs[i], xs[i + 1], y[i], y[i + 1])
                        ax.plot(xc, yc, "-", color=color)
                    else:
                        ax.plot(xs[i:i + 2], y[i:i + 2], "-", color=color)
                ax.plot(xs, y, "o", color=color, label=f"Q{qi+1}")

            ax.annotate(
                f"Q{qi+1}", xy=(xs[0], y[0]),
                xytext=(-12, 0), textcoords="offset points",
                ha="right", va="center", fontsize=8, color=color,
            )
            ax.annotate(
                f"Q{qi+1}", xy=(xs[-1], y[-1]),
                xytext=(8, 0), textcoords="offset points",
                ha="left", va="center", fontsize=8, color=color,
            )

        # Mark crossings on the LAST inter-section segment between coupled
        # pairs that are BOTH visible.
        if num_sections >= 2:
            last = num_sections - 1
            x_l, x_r = xs[last - 1], xs[last]
            for q_a, q_b in _FF_FREQ_COUPLED_PAIRS:
                if (q_a - 1) not in visible or (q_b - 1) not in visible:
                    continue
                ya1, ya2 = freqs[last - 1, q_a - 1], freqs[last, q_a - 1]
                yb1, yb2 = freqs[last - 1, q_b - 1], freqs[last, q_b - 1]
                hit = self._segment_intersection(
                    (x_l, ya1), (x_r, ya2),
                    (x_l, yb1), (x_r, yb2),
                )
                if hit is not None:
                    xi, yi = hit
                    ax.plot([xi], [yi], marker="v", color="red", markersize=10, zorder=5)
                    ax.annotate(
                        "!", xy=(xi, yi),
                        xytext=(4, 4), textcoords="offset points",
                        color="red", fontweight="bold", fontsize=9,
                    )

        ax.set_xticks(list(xs))
        ax.set_xticklabels(labels)
        ax.set_xlabel("experimental section")
        ax.set_ylabel("Dressed frequency (MHz)")
        ax.legend(fontsize=8, ncol=2, loc="best")

        if warns:
            ax.set_title(" | ".join(warns), color="#a00", fontsize=8)

    @staticmethod
    def _ease_out_segment(x0, x1, y0, y1, samples: int = 22):
        """Cubic ease-out from (x0, y0) to (x1, y1).

        y(t) = y0 + (y1 - y0) * (1 - (1 - t)**3),  t in [0, 1]

        Starts steep (slope 3*(y1 - y0) at t=0), asymptotes flat at t=1.
        Used to depict ramps that initialize quickly and settle slowly.
        """
        import numpy as np
        xc = np.linspace(x0, x1, samples)
        t = (xc - x0) / (x1 - x0)
        yc = y0 + (y1 - y0) * (1.0 - (1.0 - t) ** 3)
        return xc, yc

    # ----- CRUD: New / Duplicate / Edit (ramp + dynamics only) -----

    def _on_crud_entry(self, ns: str, group_combo: QComboBox,
                       entry_combo: QComboBox, action: str) -> None:
        """Open the EntryEditDialog for new/duplicate/edit entry actions."""
        jd = self.state.qubit_parameters_json or {}
        gname = group_combo.currentText()
        if not gname or gname == self.NONE_LABEL:
            QMessageBox.information(
                self, "Pick a group first",
                f"Select a {ns.replace('_groups','')} group before adding or editing entries."
            )
            return
        groups = jd.setdefault(ns, {})
        group = groups.get(gname)
        if not isinstance(group, dict):
            QMessageBox.warning(self, "Unknown group", f"{ns}/{gname} is not a dict.")
            return
        entries = group.setdefault("entries", {})

        source_entry: Optional[dict] = None
        suggested_name = ""
        if action == "new":
            suggested_name = self._unique_name("new_entry", set(entries.keys()))
        elif action == "duplicate":
            ename = entry_combo.currentText()
            if not ename or ename == self.NONE_LABEL:
                QMessageBox.information(self, "Select an entry",
                                        "Pick an entry to duplicate first.")
                return
            source_entry = entries.get(ename)
            suggested_name = self._unique_name(f"{ename}_copy", set(entries.keys()))
        elif action == "edit":
            ename = entry_combo.currentText()
            if not ename or ename == self.NONE_LABEL:
                QMessageBox.information(self, "Select an entry",
                                        "Pick an entry to edit first.")
                return
            source_entry = entries.get(ename)
            suggested_name = ename
        else:
            return

        dlg = EntryEditDialog(
            jd, ns, gname, suggested_name,
            source_entry=source_entry, mode=action, parent=self,
        )
        if dlg.exec_() != QDialog.Accepted:
            return
        new_name = dlg.result_name or suggested_name
        new_entry = dlg.result_entry or {}

        # Apply into the in-memory mirror.
        if action == "edit":
            original = entry_combo.currentText()
            self._commit_edit_entry(ns, gname, original, new_name, new_entry)
        else:
            # new / duplicate -> insert (collision already caught in dialog).
            entries[new_name] = new_entry
            self._after_jd_mutation(select_group=gname, select_entry=new_name)

    def _commit_edit_entry(self, ns: str, gname: str, original: str,
                           new_name: str, new_entry: dict) -> None:
        """Replace the existing entry; on rename, optionally rewrite refs."""
        entries = self._jd.get(ns, {}).get(gname, {}).get("entries", {})
        if original != new_name:
            # Find string-leaf references to `original` anywhere in the JSON.
            ref_paths = self._find_string_refs(self._jd, original)
            # Filter out the self-reference at this entry's own key.
            self_path = (ns, gname, "entries", original)
            ref_paths = [p for p in ref_paths if p[:len(self_path)] != self_path]
            if ref_paths:
                msg_box = QMessageBox(self)
                msg_box.setWindowTitle("Rename references?")
                msg_box.setText(
                    f"The name {original!r} is referenced by {len(ref_paths)} "
                    f"other leaves. Rename in those entries too?"
                )
                msg_box.setStandardButtons(
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
                )
                msg_box.setDefaultButton(QMessageBox.Yes)
                choice = msg_box.exec_()
                if choice == QMessageBox.Cancel:
                    return
                if choice == QMessageBox.Yes:
                    self._rewrite_string_refs(self._jd, ref_paths, new_name)
            # Reinsert preserving key order.
            new_entries = {}
            for k, v in entries.items():
                if k == original:
                    new_entries[new_name] = new_entry
                else:
                    new_entries[k] = v
            self._jd[ns][gname]["entries"] = new_entries
        else:
            entries[new_name] = new_entry
        self._after_jd_mutation(select_group=gname, select_entry=new_name)

    def _on_crud_group(self, ns: str, group_combo: QComboBox,
                       action: str) -> None:
        """Group-level New / Duplicate / Rename."""
        jd = self.state.qubit_parameters_json
        if not isinstance(jd, dict):
            return
        groups = jd.setdefault(ns, {})
        gname = group_combo.currentText()
        if action == "new":
            new_name = self._prompt_group_name(
                f"New {ns.replace('_groups','')} group name", set(groups.keys())
            )
            if not new_name:
                return
            groups[new_name] = {"entries": {}}
            self._after_jd_mutation(select_group=new_name)
        elif action == "duplicate":
            if not gname or gname == self.NONE_LABEL:
                QMessageBox.information(self, "Select a group",
                                        "Pick a group to duplicate first.")
                return
            new_name = self._prompt_group_name(
                f"Duplicate {gname!r} as", set(groups.keys()),
                suggested=self._unique_name(f"{gname}_copy", set(groups.keys())),
            )
            if not new_name:
                return
            groups[new_name] = copy.deepcopy(groups.get(gname, {}))
            self._after_jd_mutation(select_group=new_name)
        elif action == "rename":
            if not gname or gname == self.NONE_LABEL:
                QMessageBox.information(self, "Select a group",
                                        "Pick a group to rename first.")
                return
            new_name = self._prompt_group_name(
                f"Rename {gname!r} to", set(groups.keys()) - {gname},
                suggested=gname,
            )
            if not new_name or new_name == gname:
                return
            # Rename keeping insertion order.
            new_groups = {}
            for k, v in groups.items():
                new_groups[new_name if k == gname else k] = v
            jd[ns] = new_groups
            # Group names rarely appear as string leaves elsewhere, but if
            # they do (e.g. an experiment cfg pointing to a Readout_Point),
            # walk the JSON and offer to rewrite. Skip our own entry-name
            # subtree under the renamed group (those are entry names, not
            # group refs).
            ref_paths = self._find_string_refs(jd, gname)
            old_prefix = (ns, new_name)  # the renamed group lives under new_name now
            ref_paths = [p for p in ref_paths if tuple(p[:2]) != old_prefix]
            if ref_paths:
                box = QMessageBox(self)
                box.setWindowTitle("Rename references?")
                box.setText(
                    f"Group name {gname!r} is referenced by {len(ref_paths)} "
                    f"other leaves. Rename in those entries too?"
                )
                box.setStandardButtons(
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
                )
                box.setDefaultButton(QMessageBox.Yes)
                choice = box.exec_()
                if choice == QMessageBox.Cancel:
                    # Roll back the rename.
                    rb_groups = {}
                    for k, v in jd[ns].items():
                        rb_groups[gname if k == new_name else k] = v
                    jd[ns] = rb_groups
                    return
                if choice == QMessageBox.Yes:
                    self._rewrite_string_refs(jd, ref_paths, new_name)
            self._after_jd_mutation(select_group=new_name)

    # ----- helpers shared by CRUD handlers -----

    def _prompt_group_name(self, prompt: str, existing: set,
                           suggested: str = "") -> Optional[str]:
        """Tiny inline dialog for group-name entry — avoids QInputDialog
        import sprawl. Returns the trimmed name or None on cancel.
        """
        dlg = QDialog(self)
        dlg.setWindowTitle(prompt)
        form = QFormLayout(dlg)
        edit = QLineEdit(suggested)
        edit.selectAll()
        form.addRow("Name", edit)
        err = QLabel("")
        err.setStyleSheet("color: #a32a2a;")
        form.addRow(err)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        form.addRow(bb)

        def _validate() -> None:
            n = edit.text().strip()
            if not n:
                err.setText("Name is required.")
            elif n in existing:
                err.setText(f"Name collision: {n!r}.")
            else:
                err.setText("")
        edit.textChanged.connect(lambda _t: _validate())

        def _accept() -> None:
            n = edit.text().strip()
            if not n or n in existing:
                _validate()
                return
            dlg.accept()
        bb.accepted.connect(_accept)
        bb.rejected.connect(dlg.reject)
        if dlg.exec_() != QDialog.Accepted:
            return None
        return edit.text().strip()

    @staticmethod
    def _unique_name(base: str, existing: set) -> str:
        """Return ``base`` if free, else ``base_2``, ``base_3``, ..."""
        if base not in existing:
            return base
        i = 2
        while f"{base}_{i}" in existing:
            i += 1
        return f"{base}_{i}"

    @staticmethod
    def _find_string_refs(jd, target: str) -> list[tuple]:
        """Walk the whole JSON dict and return paths to every str-leaf
        whose value equals ``target`` (exact match only).
        """
        hits: list[tuple] = []

        def walk(node, path: tuple) -> None:
            if isinstance(node, dict):
                for k, v in node.items():
                    walk(v, path + (k,))
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    walk(v, path + (i,))
            elif isinstance(node, str) and node == target:
                hits.append(path)
        walk(jd, ())
        return hits

    @staticmethod
    def _rewrite_string_refs(jd, paths: list[tuple], new_value: str) -> None:
        for p in paths:
            cur = jd
            for seg in p[:-1]:
                if isinstance(cur, dict):
                    cur = cur[seg]
                else:
                    cur = cur[int(seg)]
            leaf = p[-1]
            if isinstance(cur, dict):
                cur[leaf] = new_value
            else:
                cur[int(leaf)] = new_value

    def _after_jd_mutation(self, *, select_group: Optional[str] = None,
                           select_entry: Optional[str] = None) -> None:
        """Repopulate combos + replot + repaint dirty styling + notify others.

        Snapshot already differs vs the in-memory mirror, so the relevant
        group/entry combo entries will display bold via _apply_combo_styles.
        """
        self._reload_and_populate_keep_selection()
        if select_group is not None:
            for combo in (self.ramp_group_combo, self.dynamics_group_combo,
                          self.readout_group_combo, self.drive_group_combo):
                idx = combo.findText(select_group)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                    break
        if select_entry is not None:
            for combo in (self.ramp_entry_combo, self.dynamics_entry_combo):
                idx = combo.findText(select_entry)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                    break
        self._apply_combo_styles()
        # Notify the QubitParametersTab so its tree + detail table refresh.
        try:
            main = self.get_main()
        except Exception:
            main = None
        if main is not None and hasattr(main, "refresh_qubit_summary"):
            try:
                main.refresh_qubit_summary()
            except Exception:
                pass

    def _apply_combo_styles(self) -> None:
        """Bold combo items whose JSON subtree differs from snapshot.

        Each group combo's items map to (ns, group_name); entry combos map to
        (ns, group_name, "entries", entry_name). Compared via _values_differ.
        """
        snap = self.state.qubit_parameters_json_snapshot or {}
        live = self.state.qubit_parameters_json or {}
        touched = self.state.calibration_touched_paths

        def _style_combo(combo: QComboBox, prefix_for_text) -> None:
            for i in range(combo.count()):
                txt = combo.itemText(i)
                if not txt or txt in (self.NONE_LABEL, self.DRIVE_FALLBACK_LABEL):
                    continue
                prefix = prefix_for_text(txt)
                if prefix is None:
                    continue
                snap_v = (_leaf_at_path(snap, prefix)[1])
                live_v = (_leaf_at_path(live, prefix)[1])
                dirty = _values_differ(snap_v, live_v)
                cal = _entry_touched_paths(touched, prefix)
                f = combo.font()
                # Set font on the item rather than the combo so the popup
                # list distinguishes the dirty ones.
                item_font = QFont(f)
                if dirty:
                    item_font.setBold(True)
                    if cal:
                        item_font.setItalic(True)
                else:
                    item_font.setBold(False); item_font.setItalic(False)
                combo.setItemData(i, item_font, Qt.FontRole)

        # Group combos.
        _style_combo(self.readout_group_combo,
                     lambda t: ("readout_groups", t))
        _style_combo(self.ramp_group_combo,
                     lambda t: ("ramp_groups", t))
        _style_combo(self.dynamics_group_combo,
                     lambda t: ("dynamics_groups", t))
        _style_combo(self.drive_group_combo,
                     lambda t: ("drive_groups", t))

        # Entry combos: prefix from the current group selection.
        rg = self.readout_group_combo.currentText()
        _style_combo(self.readout_entry_combo,
                     lambda t, _g=rg: ("readout_groups", _g, "entries", t) if _g and _g != self.NONE_LABEL else None)
        dg = self.drive_group_combo.currentText()
        _style_combo(self.drive_entry_combo,
                     lambda t, _g=dg: ("drive_groups", _g, "entries", t) if _g and _g not in (self.NONE_LABEL, self.DRIVE_FALLBACK_LABEL) else None)
        rp = self.ramp_group_combo.currentText()
        _style_combo(self.ramp_entry_combo,
                     lambda t, _g=rp: ("ramp_groups", _g, "entries", t) if _g and _g != self.NONE_LABEL else None)
        dy = self.dynamics_group_combo.currentText()
        _style_combo(self.dynamics_entry_combo,
                     lambda t, _g=dy: ("dynamics_groups", _g, "entries", t) if _g and _g != self.NONE_LABEL else None)


class TransmissionTab(StageTab):
    name = "Transmission"

    def param_spec(self):
        d = STAGE_DEFAULTS["transmission"]
        return [
            ("TransSpan",      "Span around current f_r (MHz)", "float", d["TransSpan"]),
            ("TransNumPoints", "Num points",                    "int",   d["TransNumPoints"]),
            ("readout_length", "Readout length (us)",           "float", d["readout_length"]),
            ("cav_relax_delay", "Cavity relax delay (us)",      "float", d["cav_relax_delay"]),
            ("reps",           "Repetitions",                   "int",   d["reps"]),
        ]

    def make_experiment(self, cfg):
        from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Basic_Experiments.mTransmissionFFMUX import CavitySpecFFMUX
        return CavitySpecFFMUX(
            soc=self.state.soc, soccfg=self.state.soccfg,
            path="TransmissionFF", outerFolder=self.state.outer_folder, cfg=cfg,
        )

    def on_success(self, expt, data):
        f_if = expt.peakFreq_min
        f_actual = f_if + expt.cfg["res_LO"]
        return f"f_r = {f_actual:.3f} MHz (IF = {f_if:.3f}, LO = {expt.cfg['res_LO']})"

    def on_apply(self, expt, data):
        Q = str(self.state.target_qubit)
        f_actual = float(expt.peakFreq_min + expt.cfg["res_LO"])
        entry = _jd_entry_for(self.state, Q)
        if entry is not None:
            entry.setdefault("Readout", {})["Frequency"] = f_actual


class SpecSliceTab(StageTab):
    name = "QubitSpec"

    def param_spec(self):
        # sigma is NOT exposed: per-qubit value lives in JSON entry's Qubit.sigma
        # and reaches cfg as a list via build_config. A scalar override here
        # would clobber the list and break mSpecSliceFFMUX (cfg["sigma"][0]).
        d = STAGE_DEFAULTS["spec_coarse"]
        return [
            ("qubit_gain",     "CW qubit gain (DAC)",  "int",   d["qubit_gain"]),
            ("SpecSpan",       "Span around f_q (MHz)","float", d["SpecSpan"]),
            ("SpecNumPoints",  "Num points",           "int",   d["SpecNumPoints"]),
            ("Gauss",          "Gauss pulse?",         "bool",  d["Gauss"]),
            ("Gauss_gain",     "Gauss gain",           "int",   d["Gauss_gain"]),
            ("qubit_length",   "CW length (us)",       "float", d["qubit_length"]),
            ("reps",           "Repetitions",          "int",   d["reps"]),
            # rounds: not exposed — firmware doesn't distinguish reps vs rounds;
            # the experiment class default (1) applies.
            ("relax_delay",    "Relax delay (us)",     "float", d["relax_delay"]),
        ]

    def make_experiment(self, cfg):
        from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Basic_Experiments.mSpecSliceFFMUX import QubitSpecSliceFFMUX
        return QubitSpecSliceFFMUX(
            soc=self.state.soc, soccfg=self.state.soccfg,
            path="QubitSpec", outerFolder=self.state.outer_folder, cfg=cfg,
        )

    def on_success(self, expt, data):
        return f"f_q = {expt.qubitFreq:.3f} MHz"

    def on_apply(self, expt, data):
        Q = str(self.state.target_qubit)
        entry = _jd_entry_for(self.state, Q)
        if entry is not None:
            entry.setdefault("Qubit", {})["Frequency"] = float(expt.qubitFreq)


class AmplitudeRabiTab(StageTab):
    name = "AmplitudeRabi"

    def param_spec(self):
        # sigma is intentionally NOT exposed here: the per-qubit Gaussian
        # width comes from the JSON entry's Qubit.sigma via build_config and
        # must not be overridden by the form. (cfg['sigma'] is a list.)
        d = STAGE_DEFAULTS["rabi"]
        return [
            ("max_gain",    "Max gain (DAC)",      "int",   d["max_gain"]),
            ("expts",       "Num gain points",     "int",   d["expts"]),
            ("reps",        "Repetitions",         "int",   d["reps"]),
            ("relax_delay", "Relax delay (us)",    "float", d["relax_delay"]),
            # rounds removed; experiment-class default (1) applies.
        ]

    def make_experiment(self, cfg):
        from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Basic_Experiments.mAmplitudeRabiFFMUX import AmplitudeRabiFFMUX
        return AmplitudeRabiFFMUX(
            soc=self.state.soc, soccfg=self.state.soccfg,
            path="AmplitudeRabi", outerFolder=self.state.outer_folder, cfg=cfg,
        )

    def on_success(self, expt, data):
        pi_gain = data["data"].get("pi_gain_fit")
        if pi_gain is None:
            return "Rabi: fit failed (try wider/narrower max_gain)"
        return f"pi-pulse gain = {pi_gain:.0f} DAC"

    def on_apply(self, expt, data):
        Q = str(self.state.target_qubit)
        pi_gain = data["data"].get("pi_gain_fit")
        if pi_gain is None:
            raise RuntimeError("No pi-gain fit to apply.")
        entry = _jd_entry_for(self.state, Q)
        if entry is not None:
            entry.setdefault("Qubit", {})["Gain"] = int(pi_gain)
        # Do NOT write sigma here — the per-qubit value lives in the JSON
        # entry's Qubit.sigma and is the source of truth.


class ReadoutOptTab(RecenterZoomMixin, StageTab):
    """2D readout-fidelity optimisation: cavity gain x cavity freq.

    Wraps `ReadOpt_wSingleShotFFMUX` with `plotDisp=False` so the experiment
    does not try to drive a pyplot-managed figure from the worker thread.
    Final fidelity matrix is rendered onto the GUI canvas via render_into.
    """

    name = "ReadoutOpt"

    def param_spec(self):
        d = STAGE_DEFAULTS["readout_opt"]
        return [
            ("Shots",            "Shots / single-shot",   "int",   d["Shots"]),
            ("relax_delay",      "Relax delay (us)",      "float", d["relax_delay"]),
            ("gain_start",       "Cav gain start (DAC)",  "int",   d["gain_start"]),
            ("gain_stop",        "Cav gain stop (DAC)",   "int",   d["gain_stop"]),
            ("gain_pts",         "Num cav gain points",   "int",   d["gain_pts"]),
            ("span",             "Cav freq span (MHz)",   "float", d["span"]),
            ("trans_pts",        "Num cav freq points",   "int",   d["trans_pts"]),
            ("number_of_pulses", "Num pi pulses",         "int",   d["number_of_pulses"]),
            ("iterate",          "Iterate recenter+zoom", "bool",  d["iterate"]),
            ("max_iters",        "Max iterations",        "int",   d["max_iters"]),
            ("freq_tol",         "Freq tol (MHz)",        "float", d["freq_tol"]),
            ("gain_tol",         "Gain tol (DAC)",        "int",   d["gain_tol"]),
            ("zoom_factor",      "Zoom factor",           "float", d["zoom_factor"]),
        ]

    # --- RecenterZoomMixin hooks (HALF-width spans, absolute DAC gains) ---
    def _iter_read_center(self, cfg):
        idx = int(cfg.get("qubit_sweep_index", 0))
        center_f = float(cfg["res_freqs"][idx]) + float(cfg.get("res_LO", 0))
        center_g = 0.5 * (float(cfg["gain_start"]) + float(cfg["gain_stop"]))
        return center_f, center_g

    def _iter_initial_spans(self, cfg):
        span_f = 0.5 * float(cfg["span"])
        span_g = 0.5 * abs(float(cfg["gain_stop"]) - float(cfg["gain_start"]))
        return span_f, span_g

    def _iter_write(self, cfg, center_f, center_g, span_f, span_g, log):
        idx = int(cfg.get("qubit_sweep_index", 0))
        cf = self._iter_clamp_freq("res", center_f, log)
        cfg["res_freqs"][idx] = cf - float(cfg.get("res_LO", 0))
        cfg["span"] = 2.0 * span_f
        cfg["gain_start"] = int(round(self._iter_clamp_gain(
            "cav (start)", center_g - span_g, log)))
        cfg["gain_stop"] = int(round(self._iter_clamp_gain(
            "cav (stop)", center_g + span_g, log)))

    def _iter_extract(self, expt, data):
        import numpy as np
        d = data["data"]
        fid_mat = np.asarray(d["fid_mat"])
        iy, ix = self._best_index(fid_mat)
        f = float(d["trans_fpts"][ix]) + float(expt.cfg.get("res_LO", 0))
        g = float(d["gain_pts"][iy])
        return f, g, float(fid_mat[iy, ix])

    def display_kwargs(self):
        # Not used: we override render_into entirely, so expt.display() is never called.
        return {}

    def make_experiment(self, cfg):
        from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Characterization_Sweeps.mOptimizeReadoutandPulse_FFMUX import (
            ReadOpt_wSingleShotFFMUX,
        )

        class _ReadOptForGui(ReadOpt_wSingleShotFFMUX):
            def acquire(self_inner, progress=False):
                # Suppress in-acquire matplotlib calls; we re-render onto the GUI canvas.
                return ReadOpt_wSingleShotFFMUX.acquire(
                    self_inner, progress=progress, plotDisp=False, ax=None,
                )

        cfg = dict(cfg)
        cfg.setdefault("qubit_sweep_index", 0)
        return _ReadOptForGui(
            soc=self.state.soc, soccfg=self.state.soccfg,
            path="SingleShot_OptReadout",
            outerFolder=self.state.outer_folder, cfg=cfg,
        )

    def _best_index(self, fid_mat):
        import numpy as np
        return np.unravel_index(np.nanargmax(fid_mat), fid_mat.shape)

    def render_into(self, ax, expt, data, qubit_id=None):
        import numpy as np
        d = data["data"]
        fid_mat = np.asarray(d["fid_mat"]) * 100  # percent
        trans_fpts = np.asarray(d["trans_fpts"])
        gain_pts = np.asarray(d["gain_pts"])
        cfg = data.get("config", {})
        x = trans_fpts + cfg.get("res_LO", 0)
        x_step = (x[1] - x[0]) if len(x) > 1 else 1.0
        y_step = (gain_pts[1] - gain_pts[0]) if len(gain_pts) > 1 else 1.0
        im = ax.imshow(
            fid_mat, aspect="auto",
            extent=[x[0] - x_step / 2, x[-1] + x_step / 2,
                    gain_pts[0] - y_step / 2, gain_pts[-1] + y_step / 2],
            origin="lower", interpolation="none",
        )
        if np.isfinite(fid_mat).any():
            iy, ix = self._best_index(fid_mat)
            ax.scatter([x[ix]], [gain_pts[iy]], s=80,
                       c="white", edgecolor="black", zorder=3,
                       label=f"max F = {fid_mat[iy, ix]:.1f}%")
            ax.legend(loc="lower right")
        ax.set_xlabel("Cavity Frequency (MHz)")
        ax.set_ylabel("Cavity Gain (DAC)")
        ax.set_title(f"Readout Opt — Q{qubit_id if qubit_id is not None else self.state.target_qubit}")
        try:
            ax.figure.colorbar(im, ax=ax, label="fidelity (%)")
        except Exception:
            pass

    def on_success(self, expt, data):
        import numpy as np
        d = data["data"]
        fid_mat = np.asarray(d["fid_mat"])
        if not np.isfinite(fid_mat).any():
            return "Readout-opt: no fidelity points produced"
        iy, ix = self._best_index(fid_mat)
        f_actual = float(d["trans_fpts"][ix]) + expt.cfg.get("res_LO", 0)
        gain = int(round(float(d["gain_pts"][iy])))
        return f"max F = {fid_mat[iy, ix] * 100:.1f}%, f_r = {f_actual:.2f} MHz, gain = {gain}"

    def on_apply(self, expt, data):
        import numpy as np
        d = data["data"]
        fid_mat = np.asarray(d["fid_mat"])
        if not np.isfinite(fid_mat).any():
            raise RuntimeError("Readout-opt produced no usable fidelity matrix.")
        iy, ix = self._best_index(fid_mat)
        f_actual = float(d["trans_fpts"][ix]) + expt.cfg.get("res_LO", 0)
        gain = int(round(float(d["gain_pts"][iy])))
        Q = str(self.state.target_qubit)
        entry = _jd_entry_for(self.state, Q)
        if entry is not None:
            ro = entry.setdefault("Readout", {})
            ro["Frequency"] = float(f_actual)
            ro["Gain"] = gain
            ro["fidelity"] = float(np.nanmax(fid_mat))


class PulseOptTab(RecenterZoomMixin, StageTab):
    """2D qubit-pulse-fidelity optimisation: qubit gain x qubit freq.

    Wraps `QubitPulseOpt_wSingleShotFFMUX` like ReadoutOptTab.
    """

    name = "PulseOpt"

    def param_spec(self):
        d = STAGE_DEFAULTS["pulse_opt"]
        return [
            ("Shots",            "Shots / single-shot",       "int",   d["Shots"]),
            ("relax_delay",      "Relax delay (us)",          "float", d["relax_delay"]),
            ("q_gain_span",      "Qubit gain span (DAC)",     "int",   d["q_gain_span"]),
            ("q_gain_pts",       "Num qubit gain points",     "int",   d["q_gain_pts"]),
            ("q_freq_span",      "Qubit freq span (MHz)",     "float", d["q_freq_span"]),
            ("q_freq_pts",       "Num qubit freq points",     "int",   d["q_freq_pts"]),
            ("number_of_pulses", "Num pi pulses",             "int",   d["number_of_pulses"]),
            ("iterate",          "Iterate recenter+zoom",     "bool",  d["iterate"]),
            ("max_iters",        "Max iterations",            "int",   d["max_iters"]),
            ("freq_tol",         "Freq tol (MHz)",            "float", d["freq_tol"]),
            ("gain_tol",         "Gain tol (DAC)",            "int",   d["gain_tol"]),
            ("zoom_factor",      "Zoom factor",               "float", d["zoom_factor"]),
        ]

    # --- RecenterZoomMixin hooks (HALF-width spans, absolute DAC gains) ---
    def _iter_read_center(self, cfg):
        idx = int(cfg.get("qubit_sweep_index", 0))
        center_f = float(cfg["qubit_freqs"][idx]) + float(cfg.get("qubit_LO", 0))
        center_g = float(cfg["qubit_gains"][idx]) * DAC_GAIN_MAX
        return center_f, center_g

    def _iter_initial_spans(self, cfg):
        span_f = 0.5 * float(cfg["q_freq_span"])
        span_g = 0.5 * float(cfg["q_gain_span"])
        return span_f, span_g

    def _iter_write(self, cfg, center_f, center_g, span_f, span_g, log):
        idx = int(cfg.get("qubit_sweep_index", 0))
        cf = self._iter_clamp_freq("qubit", center_f, log)
        cfg["qubit_freqs"][idx] = cf - float(cfg.get("qubit_LO", 0))
        cfg["q_freq_span"] = 2.0 * span_f
        # Keep the whole gain window [center_g - span_g, center_g + span_g]
        # inside [0, DAC_GAIN_MAX] by shifting the center if needed (WARN on shift).
        lo = center_g - span_g
        hi = center_g + span_g
        shifted = center_g
        if lo < 0.0:
            shifted = span_g
        elif hi > DAC_GAIN_MAX:
            shifted = DAC_GAIN_MAX - span_g
        if shifted != center_g and log is not None:
            log(f"[WARN] qubit gain window center {center_g:.0f}+-{span_g:.0f} "
                f"out of [0,{DAC_GAIN_MAX}]; center shifted to {shifted:.0f}")
        center_g = self._iter_clamp_gain("qubit", shifted, log)
        cfg["qubit_gains"][idx] = center_g / DAC_GAIN_MAX
        cfg["q_gain_span"] = 2.0 * span_g

    def _iter_extract(self, expt, data):
        import numpy as np
        d = data["data"]
        fid_mat = np.asarray(d["fid_mat"])
        iy, ix = self._best_index(fid_mat)
        f = float(d["qubit_fpts"][ix]) + float(expt.cfg.get("qubit_LO", 0))
        g = float(d["gain_pts"][iy])
        return f, g, float(fid_mat[iy, ix])

    def display_kwargs(self):
        return {}

    def make_experiment(self, cfg):
        from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Characterization_Sweeps.mOptimizeReadoutandPulse_FFMUX import (
            QubitPulseOpt_wSingleShotFFMUX,
        )

        class _PulseOptForGui(QubitPulseOpt_wSingleShotFFMUX):
            def acquire(self_inner, progress=False):
                return QubitPulseOpt_wSingleShotFFMUX.acquire(
                    self_inner, progress=progress, plotDisp=False, ax=None,
                )

        cfg = dict(cfg)
        cfg.setdefault("qubit_sweep_index", 0)
        cfg.setdefault("readout_index", 0)
        return _PulseOptForGui(
            soc=self.state.soc, soccfg=self.state.soccfg,
            path="SingleShot_OptQubit",
            outerFolder=self.state.outer_folder, cfg=cfg,
        )

    def _best_index(self, fid_mat):
        import numpy as np
        return np.unravel_index(np.nanargmax(fid_mat), fid_mat.shape)

    def render_into(self, ax, expt, data, qubit_id=None):
        import numpy as np
        d = data["data"]
        fid_mat = np.asarray(d["fid_mat"]) * 100
        qubit_fpts = np.asarray(d["qubit_fpts"])
        gain_pts = np.asarray(d["gain_pts"])
        cfg = data.get("config", {})
        x = qubit_fpts + cfg.get("qubit_LO", 0)
        x_step = (x[1] - x[0]) if len(x) > 1 else 1.0
        y_step = (gain_pts[1] - gain_pts[0]) if len(gain_pts) > 1 else 1.0
        im = ax.imshow(
            fid_mat, aspect="auto",
            extent=[x[0] - x_step / 2, x[-1] + x_step / 2,
                    gain_pts[0] - y_step / 2, gain_pts[-1] + y_step / 2],
            origin="lower", interpolation="none",
        )
        if np.isfinite(fid_mat).any():
            iy, ix = self._best_index(fid_mat)
            ax.scatter([x[ix]], [gain_pts[iy]], s=80,
                       c="white", edgecolor="black", zorder=3,
                       label=f"max F = {fid_mat[iy, ix]:.1f}%")
            ax.legend(loc="lower right")
        ax.set_xlabel("Qubit Frequency (MHz)")
        ax.set_ylabel("Qubit Gain (DAC)")
        ax.set_title(f"Pulse Opt — Q{qubit_id if qubit_id is not None else self.state.target_qubit}")
        try:
            ax.figure.colorbar(im, ax=ax, label="fidelity (%)")
        except Exception:
            pass

    def on_success(self, expt, data):
        import numpy as np
        d = data["data"]
        fid_mat = np.asarray(d["fid_mat"])
        if not np.isfinite(fid_mat).any():
            return "Pulse-opt: no fidelity points produced"
        iy, ix = self._best_index(fid_mat)
        f_actual = float(d["qubit_fpts"][ix]) + expt.cfg.get("qubit_LO", 0)
        gain = int(round(float(d["gain_pts"][iy])))
        return f"max F = {fid_mat[iy, ix] * 100:.1f}%, f_q = {f_actual:.3f} MHz, gain = {gain}"

    def on_apply(self, expt, data):
        import numpy as np
        d = data["data"]
        fid_mat = np.asarray(d["fid_mat"])
        if not np.isfinite(fid_mat).any():
            raise RuntimeError("Pulse-opt produced no usable fidelity matrix.")
        iy, ix = self._best_index(fid_mat)
        f_actual = float(d["qubit_fpts"][ix]) + expt.cfg.get("qubit_LO", 0)
        gain = int(round(float(d["gain_pts"][iy])))
        Q = str(self.state.target_qubit)
        entry = _jd_entry_for(self.state, Q)
        if entry is not None:
            q = entry.setdefault("Qubit", {})
            q["Frequency"] = float(f_actual)
            q["Gain"] = gain
            entry.setdefault("Readout", {})["fidelity"] = float(np.nanmax(fid_mat))


class SingleShotTab(StageTab):
    name = "SingleShot"

    def param_spec(self):
        # sigma is intentionally NOT exposed here: per-qubit width comes from
        # the JSON entry's Qubit.sigma via build_config. (cfg['sigma'] is a list.)
        d = STAGE_DEFAULTS["singleshot"]
        return [
            ("Shots",            "Shots",              "int",   d["Shots"]),
            ("relax_delay",      "Relax delay (us)",   "float", d["relax_delay"]),
            ("number_of_pulses", "Number of pi pulses","int",   d["number_of_pulses"]),
            # rounds removed; experiment-class default (1) applies.
        ]

    def make_experiment(self, cfg):
        from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import SingleShotFFMUX
        return SingleShotFFMUX(
            soc=self.state.soc, soccfg=self.state.soccfg,
            path="SingleShot", outerFolder=self.state.outer_folder, cfg=cfg,
        )

    def render_into(self, ax, expt, data, qubit_id=None):
        # SingleShot.display() does not accept an `ax=` kwarg (it relies on
        # hist_process making its own figure). Plot the rotated IQ scatter
        # ourselves so it lands in the embedded canvas.
        import numpy as np
        Q = qubit_id if qubit_id is not None else self.state.target_qubit
        d = data["data"]
        i_g = np.asarray(d[f"i_g{Q}"]); q_g = np.asarray(d[f"q_g{Q}"])
        i_e = np.asarray(d[f"i_e{Q}"]); q_e = np.asarray(d[f"q_e{Q}"])
        angle = float(d["angle"][0])
        threshold = float(d["threshold"][0])
        fid = float(d["fid"][0])

        # Rotate so that the discrimination axis is horizontal.
        c, s = np.cos(angle), np.sin(angle)
        ig_r = i_g * c - q_g * s; qg_r = i_g * s + q_g * c
        ie_r = i_e * c - q_e * s; qe_r = i_e * s + q_e * c

        ax.scatter(ig_r, qg_r, s=3, alpha=0.4, label="ground", color="tab:blue")
        ax.scatter(ie_r, qe_r, s=3, alpha=0.4, label="excited", color="tab:red")
        ax.axvline(threshold, color="black", linestyle="--",
                   label=f"threshold = {threshold:.4f}")
        ax.set_xlabel("I (rotated)")
        ax.set_ylabel("Q (rotated)")
        ax.set_title(f"Q{Q} single-shot - F = {fid:.3f}, angle = {angle:.3f} rad")
        ax.legend()
        ax.set_aspect("equal", adjustable="datalim")

    def on_success(self, expt, data):
        fid = data["data"]["fid"][0]
        ang = data["data"]["angle"][0]
        thr = data["data"]["threshold"][0]
        return f"F = {fid:.3f}, angle = {ang:.3f} rad, thr = {thr:.4f}"

    def cell_summary(self, expt, data) -> str:
        # AutoCalib table override: show fidelity as a percentage. Read from
        # the raw acquisition (data['data']['fid'][0]) rather than the JSON
        # entry — that way the cell displays the value even when on_apply
        # was skipped or the JSON entry isn't present yet.
        fid = float(data["data"]["fid"][0])
        return f"{fid * 100.0:.1f}%"

    def on_apply(self, expt, data):
        # Mirrors angle/threshold/fidelity (+ optional ne/ng_contrast) into the
        # JSON entry's Readout sub-dict. build_cfg_for_qubit reads these to
        # populate cfg['angle']/['threshold']/['confusion_matrix'], which
        # SweepExperimentND needs to build population_corrected. The user
        # persists via the QubitParametersTab Save buttons.
        Q = str(self.state.target_qubit)
        d = data["data"]
        entry = _jd_entry_for(self.state, Q)
        if entry is None:
            return
        ro = entry.setdefault("Readout", {})
        ro["angle"] = float(d["angle"][0])
        ro["threshold"] = float(d["threshold"][0])
        ro["fidelity"] = float(d["fid"][0])
        if "ne_contrast" in d:
            ro["ne_contrast"] = float(d["ne_contrast"][0])
        if "ng_contrast" in d:
            ro["ng_contrast"] = float(d["ng_contrast"][0])


class T1Tab(StageTab):
    name = "T1"

    def param_spec(self):
        # sigma is NOT exposed: per-qubit value lives in JSON entry's
        # Qubit.sigma and reaches cfg as a list via build_config. A scalar
        # override here would clobber the list shape mT1MUX expects.
        # TODO: sigma override pattern (per-stage scalar -> list) if T1
        # needs a wider pulse than the calibrated pi-pulse sigma.
        d = STAGE_DEFAULTS["t1"]
        return [
            ("expts",         "Num delay points",  "int",   d["expts"]),
            ("stop_delay_us", "Max delay (us)",    "float", d["stop_delay_us"]),
            ("reps",          "Repetitions",       "int",   d["reps"]),
            ("relax_delay",   "Relax delay (us)",  "float", d["relax_delay"]),
            # rounds removed; experiment-class default (1) applies.
        ]

    def make_experiment(self, cfg):
        from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Basic_Experiments.mT1MUX import T1MUX
        return T1MUX(
            soc=self.state.soc, soccfg=self.state.soccfg,
            path="T1", outerFolder=self.state.outer_folder, cfg=cfg,
        )

    def display_kwargs(self):
        # T1.display() does plt.close(fig) when plotDisp=False, which would
        # destroy the embedded canvas. Force plotDisp=True; with block=False
        # plt.show is non-blocking on Qt5Agg so no extra window appears.
        return {"plotDisp": True, "block": False}

    def on_success(self, expt, data):
        T1 = getattr(expt, "T1", None)
        if T1 is None:
            return "T1 fit failed"
        return f"T1 = {T1:.2f} us"

    def cell_summary(self, expt, data) -> str:
        T1 = getattr(expt, "T1", None)
        return f"{T1:.1f} us" if T1 is not None else "OK"

    def on_apply(self, expt, data):
        Q = str(self.state.target_qubit)
        T1 = getattr(expt, "T1", None)
        if T1 is None:
            raise RuntimeError("No T1 fit to apply.")
        entry = _jd_entry_for(self.state, Q)
        if entry is not None:
            entry.setdefault("Qubit", {})["T1"] = float(T1)


class T2RTab(StageTab):
    name = "T2R"

    def param_spec(self):
        # sigma is NOT exposed: per-qubit value lives in JSON entry's
        # Qubit.sigma and reaches cfg as a list via build_config. A scalar
        # override here would clobber the list shape mT2RMUX expects.
        # TODO: sigma override pattern if T2R needs a different pulse width.
        d = STAGE_DEFAULTS["t2r"]
        return [
            ("expts",              "Num delay points",     "int",   d["expts"]),
            ("stop_delay_us",      "Max delay (us)",       "float", d["stop_delay_us"]),
            ("reps",               "Repetitions",          "int",   d["reps"]),
            ("relax_delay",        "Relax delay (us)",     "float", d["relax_delay"]),
            # rounds removed; experiment-class default (1) applies.
            ("freq_shift",         "Detuning (MHz)",       "float", d["freq_shift"]),
            ("phase_shift_cycles", "Phase shift cycles",   "int",   d["phase_shift_cycles"]),
        ]

    def make_experiment(self, cfg):
        from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Basic_Experiments.mT2RMUX import T2RMUX
        return T2RMUX(
            soc=self.state.soc, soccfg=self.state.soccfg,
            path="T2R", outerFolder=self.state.outer_folder, cfg=cfg,
        )

    def display_kwargs(self):
        # Same plotDisp=False -> plt.close(fig) issue as T1.
        return {"plotDisp": True, "block": False}

    def on_success(self, expt, data):
        T2 = getattr(expt, "T2", None)
        if T2 is None:
            return "T2R fit failed"
        return f"T2R = {T2:.2f} us"

    def cell_summary(self, expt, data) -> str:
        T2 = getattr(expt, "T2", None)
        return f"{T2:.1f} us" if T2 is not None else "OK"

    def on_apply(self, expt, data):
        Q = str(self.state.target_qubit)
        T2 = getattr(expt, "T2", None)
        if T2 is None:
            raise RuntimeError("No T2R fit to apply.")
        entry = _jd_entry_for(self.state, Q)
        if entry is not None:
            entry.setdefault("Qubit", {})["T2R"] = float(T2)


# ---------------------------------------------------------------------------
# Auto-calibration worker + tab
# ---------------------------------------------------------------------------


class AutoCalibWorker(QThread):
    """Run a list of (qubit, stage_name, params_snapshot) jobs sequentially.

    All experiment work happens here off the GUI thread. The worker calls
    ``stage.make_experiment``, ``expt.acquire``, ``stage.on_apply`` (which
    only mutates ``state.qubit_parameters_json`` — no widget access), and
    emits progress signals for the GUI thread to consume.
    """

    progress     = pyqtSignal(str, str, str)                          # qubit, stage, status
    stage_done   = pyqtSignal(str, str, str, object, object, float)   # qubit, stage, summary, expt, data, elapsed_s
    stage_failed = pyqtSignal(str, str, str, object, object, float)   # qubit, stage, error, expt, data (None if acquire failed), elapsed_s
    log_msg      = pyqtSignal(str)
    finished_all = pyqtSignal()

    def __init__(self, state: CalibState, schedule: list[tuple[str, str, dict]],
                 stages_by_name: dict[str, "StageTab"]):
        super().__init__()
        self.state = state
        self.schedule = schedule
        self.stages_by_name = stages_by_name
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        for Q, stage_name, params in self.schedule:
            if self._stop:
                self.log_msg.emit(f"--- aborted before Q{Q}/{stage_name} ---")
                break
            stage = self.stages_by_name.get(stage_name)
            if stage is None:
                self.stage_failed.emit(Q, stage_name, f"unknown stage: {stage_name}", None, None, 0.0)
                continue
            t0 = time.perf_counter()
            try:
                # Q is a row label. With a drive group selected it may be a
                # drive-entry name like '1_3800+' (leading digits = readout
                # qubit). Without a drive group it is the readout qubit itself.
                drive_active = bool(getattr(self.state, "current_drive_group", "") or "")
                ro_q = _readout_qubit_for_entry(Q) if drive_active else str(Q)
                self.state.target_qubit = int(ro_q) if ro_q.isdigit() else self.state.target_qubit
                # Use the row label as the writeback key: drive-active rows are
                # entry names like '1_3800+' that must resolve in drive_groups,
                # not the parsed leading-digit. Readout-side stages are
                # disabled when drive_active (see READOUT_SIDE_STAGES).
                self.state.current_qubit_label = str(Q)
                self.progress.emit(Q, stage_name, "starting")
                # Same cfg pipeline as StageTab._build_cfg — keep AutoCalib
                # runs bit-identical to single-stage runs. When a drive group
                # is active, the row label IS the drive entry name; the
                # readout-qubit is parsed from its leading digits.
                # MUX stages (ReadoutOpt/PulseOpt/SingleShot) widen the
                # readout list using the chip-strip selection; target is
                # always first so qubit_sweep_index = 0 remains valid.
                qr = (_mux_readout_list(self.state, ro_q)
                      if stage_name in MUX_STAGES else [ro_q])
                # PulseOpt may also prepend a pulse chain (drive precursors)
                # from the pulse-chain chip strip; target is last so the
                # swept qubit sits at qubit_sweep_index = len(chain).
                if stage_name == "PulseOpt" and drive_active:
                    qp = _pulse_chain_entries(self.state, str(Q))
                else:
                    qp = [str(Q)] if drive_active else None
                cfg = build_cfg_for_qubit(
                    self.state, ro_q,
                    qubit_pulse=qp,
                    qubit_readout=qr,
                    overrides=params,
                )
                if stage_name == "PulseOpt" and drive_active:
                    cfg["qubit_sweep_index"] = len(qp) - 1
                self.progress.emit(Q, stage_name, "acquiring")
                # Iterative recenter-and-zoom for ReadoutOpt/PulseOpt; otherwise
                # the original single-shot acquire. The iterate path strips
                # ITER_PARAM_KEYS per iteration; the non-iterate path strips them
                # here (guarded) so data['config'] stays bit-identical to legacy.
                if params.get("iterate") and isinstance(stage, RecenterZoomMixin):
                    expt, data = stage.iterate_recenter_zoom(
                        cfg, self.log_msg.emit, should_abort=lambda: self._stop)
                else:
                    for _k in ITER_PARAM_KEYS:
                        cfg.pop(_k, None)
                    expt = stage.make_experiment(cfg)
                    data = expt.acquire()
                self.progress.emit(Q, stage_name, "applying")
                # Snapshot before on_apply so we can tag calibration-touched
                # leaves for the italic-bold styling on the params tab.
                _calib_before = copy.deepcopy(self.state.qubit_parameters_json or {})
                try:
                    stage.on_apply(expt, data)
                    _snapshot_calibration_diff(self.state, _calib_before)
                except Exception as apply_exc:
                    # Apply may legitimately fail (e.g. fit was rejected). The
                    # acquired data is still useful — pass it on so the GUI
                    # caches it for the results-matrix popup.
                    self.stage_failed.emit(
                        Q, stage_name,
                        f"acquire OK but on_apply failed: {apply_exc}",
                        expt, data, time.perf_counter() - t0,
                    )
                    continue
                try:
                    summary = stage.on_success(expt, data)
                except Exception:
                    summary = "(no summary)"
                self.stage_done.emit(Q, stage_name, summary, expt, data, time.perf_counter() - t0)
            except Exception as exc:
                # Acquire (or anything before it) failed — no usable data.
                self.stage_failed.emit(
                    Q, stage_name,
                    f"{exc}\n{traceback.format_exc()}",
                    None, None, time.perf_counter() - t0,
                )
        self.finished_all.emit()


# ----- delegate: paints a selection border on top of the status background --


# Selection-layer storage role. Status uses setBackground; selection uses this
# item-data role + the delegate below, so the two visual layers are orthogonal.
SELECTION_ROLE = Qt.UserRole + 1


class CalibCellDelegate(QStyledItemDelegate):
    """Draw a 2px border around body cells whose SELECTION_ROLE is truthy.

    Status (last-run outcome) is encoded in the cell's QBrush background via
    setBackground; selection (queued for re-run) is encoded only here, so the
    two visual layers compose without one stomping the other.
    """

    BORDER_COLOR = QColor("#1f6feb")
    BORDER_WIDTH = 2

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        if not index.data(SELECTION_ROLE):
            return
        painter.save()
        pen = QPen(self.BORDER_COLOR)
        pen.setWidth(self.BORDER_WIDTH)
        pen.setJoinStyle(Qt.MiterJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        # Inset by half the pen width so the stroke isn't clipped by the cell rect.
        inset = self.BORDER_WIDTH // 2
        rect = option.rect.adjusted(inset, inset, -inset - 1, -inset - 1)
        painter.drawRect(rect)
        painter.restore()


# ----- shared drag-paint state machine: rect / range / path -----------------


class DragPainter:
    """Click-drag-persistent toggle state machine.

    Region flavor is decided by the ``region`` callback the host supplies:
      - rectangle:   ``lambda s, c, _: cells_in_rect(s, c)``
      - linear range: ``lambda s, c, _: cells_in_range(s, c)``
      - path:        ``lambda s, c, prev: prev | {c}``  (no shrink semantics)

    On press, latches ``target = NOT get_state(start)`` and seeds the region.
    On move, recomputes the region; cells leaving revert to their snapshot,
    cells entering get ``target``. release() returns True iff a drag was in
    progress, so the host can emit any "I'm done" signal it owns.

    Host wires three callables: target_at(pos), get_state(key), set_state(key, on).
    """

    def __init__(self, target_at, get_state, set_state, region):
        self._target_at = target_at
        self._get_state = get_state
        self._set_state = set_state
        self._region_fn = region
        self._start = None
        self._target: bool = False
        self._snapshot: dict = {}
        self._region: set = set()

    def in_progress(self) -> bool:
        return self._start is not None

    def press(self, pos) -> bool:
        key = self._target_at(pos)
        if key is None:
            return False
        self._start = key
        self._target = not self._get_state(key)
        self._snapshot = {}
        self._region = set()
        self._update_to(key)
        return True

    def move(self, pos) -> None:
        if self._start is None:
            return
        key = self._target_at(pos)
        if key is None:
            return
        self._update_to(key)

    def release(self) -> bool:
        if self._start is None:
            return False
        self._start = None
        self._snapshot = {}
        self._region = set()
        return True

    def _update_to(self, current_key) -> None:
        new_region = self._region_fn(self._start, current_key, self._region)
        for k in self._region - new_region:
            self._set_state(k, self._snapshot.get(k, False))
        for k in new_region - self._region:
            self._snapshot.setdefault(k, self._get_state(k))
            self._set_state(k, self._target)
        self._region = new_region


# ----- chip strip: click-drag-persistent multi-toggle for MUX-readout pick --


class MuxChipStrip(QWidget):
    """Horizontal row of checkable qubit chips with click-drag-persistent toggle.

    Path-mode DragPainter: each chip the cursor visits during a stroke gets
    the latched check/uncheck state; dragging back over a chip does not
    revert it (no snapshot/restore). Emits selection_changed on release.

    Chips are mouse-transparent so all events route through the container —
    the toggle visual is driven by isChecked() only.
    """

    selection_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._chips: dict[str, QToolButton] = {}
        self._lo = QHBoxLayout(self)
        self._lo.setContentsMargins(4, 2, 4, 2)
        self._lo.setSpacing(4)
        self._lo.addStretch(1)
        self._painter = DragPainter(
            target_at=self._chip_at,
            get_state=lambda q: self._chips[q].isChecked(),
            set_state=lambda q, on: self._chips[q].setChecked(on),
            region=lambda s, c, prev: prev | {c},
        )

    def set_qubits(self, qubits: list, selected: list) -> None:
        for chip in self._chips.values():
            chip.setParent(None); chip.deleteLater()
        self._chips.clear()
        sel = set(selected)
        for q in qubits:
            chip = QToolButton(self)
            chip.setText(f"Q{q}")
            chip.setCheckable(True)
            chip.setChecked(q in sel)
            chip.setFocusPolicy(Qt.NoFocus)
            chip.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self._chips[q] = chip
            self._lo.insertWidget(self._lo.count() - 1, chip)

    def selected(self) -> list:
        return [q for q, c in self._chips.items() if c.isChecked()]

    def _chip_at(self, pos) -> Optional[str]:
        for q, c in self._chips.items():
            if c.geometry().contains(pos):
                return q
        return None

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton or not self._painter.press(event.pos()):
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self._painter.move(event.pos())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._painter.release():
            self.selection_changed.emit(self.selected())


# ----- table subclass: persistent per-cell enabled state + drag-paint -------


class CalibTable(QTableWidget):
    """QTableWidget whose body cells carry a persistent enabled/disabled flag.

    Selection is handled by the parent AutoCalibTab via this widget's mouse
    events: press latches a target state (= NOT current), and every body cell
    entered during the drag is set to that target. Header-row (row 0) and
    qubit-label column (col 0) clicks fire ``header_clicked`` / nothing
    respectively — parent decides what to do. We deliberately do NOT call
    super().mousePressEvent() so Qt's own selection model is never engaged
    (the parent sets ``setSelectionMode(NoSelection)``).
    """

    body_toggled = pyqtSignal(int, int, bool)   # (row, col, new_state)
    body_clicked = pyqtSignal(int, int)         # (row, col) — single click on body cell
    header_clicked = pyqtSignal(int)            # column of header row
    label_clicked = pyqtSignal(int)             # row of qubit-label column

    def __init__(self, parent=None):
        super().__init__(parent)
        # Parent populates after construction; defaults are safe placeholders.
        self.body_col_min: int = 1
        self.body_col_max: int = 1
        self.header_row: int = 0
        self._painter = DragPainter(
            target_at=self._body_cell_at,
            get_state=lambda rc: self._cell_state(*rc),
            set_state=lambda rc, on: self.body_toggled.emit(rc[0], rc[1], on),
            region=lambda s, c, _: self._rect_cells(s[0], s[1], c[0], c[1]),
        )

    def _is_body_cell(self, r: int, c: int) -> bool:
        return (r != self.header_row
                and self.body_col_min <= c <= self.body_col_max
                and r >= 0 and c >= 0)

    def _cell_state(self, r: int, c: int) -> bool:
        item = self.item(r, c)
        return bool(item.data(SELECTION_ROLE)) if item is not None else False

    def _body_cell_at(self, pos) -> Optional[tuple]:
        """Map mouse pos -> (r, c) clamped to the body region, or None."""
        idx = self.indexAt(pos)
        r, c = idx.row(), idx.column()
        if r < 0 or c < 0:
            return None
        # Clamp to body so the rectangle never escapes into headers.
        r = max(r, self.header_row + 1)
        c = min(max(c, self.body_col_min), self.body_col_max)
        return (r, c)

    def _rect_cells(self, r0: int, c0: int, r1: int, c1: int) -> set:
        r_lo, r_hi = sorted([r0, r1])
        c_lo, c_hi = sorted([c0, c1])
        return {(r, c)
                for r in range(r_lo, r_hi + 1)
                for c in range(c_lo, c_hi + 1)
                if self._is_body_cell(r, c)}

    def mousePressEvent(self, event):
        idx = self.indexAt(event.pos())
        r, c = idx.row(), idx.column()
        if r < 0 or c < 0:
            return
        if r == self.header_row and self.body_col_min <= c <= self.body_col_max:
            self.header_clicked.emit(c)
            event.accept()
            return
        if c == 0 and r != self.header_row:
            self.label_clicked.emit(r)
            event.accept()
            return
        if not self._is_body_cell(r, c):
            event.accept()
            return
        if self._painter.press(event.pos()):
            self.body_clicked.emit(r, c)
        event.accept()

    def mouseMoveEvent(self, event):
        self._painter.move(event.pos())

    def mouseReleaseEvent(self, event):
        self._painter.release()
        event.accept()


class AutoCalibTab(QWidget):
    """Per-(qubit, stage) calibration matrix.

    Layout: top row of selectors (readout group / drive group), then a row of
    run/stop/select-all controls, then a horizontal splitter — left side is
    the table (header-as-row 0 of in-table cells, qubit label in col 0,
    stage status cells in cols 1..N, result-popup button in last col); right
    side is a QStackedWidget that switches between the live-plot page and
    per-stage parameter-form pages.

    State model — two ORTHOGONAL visual layers:
      - **Status (background color)** is the last-run outcome:
          white = never run,  green = OK,  red = failed.
        Stored in ``self._cell_outcome[(Q, stage)]`` and painted by
        ``setBackground``. Clicking a cell does NOT change status.
      - **Selection (border)** is "queued for the next Run-selected":
          no border = not queued, blue 2px border = queued.
        Stored in ``self._cell_enabled[(Q, stage)]`` and mirrored to the
        item's ``SELECTION_ROLE`` data; CalibCellDelegate paints the border.

    A cell can carry any combination, e.g. green-with-border = "OK, queued
    for re-run" (previously indistinguishable from plain green).

    Mouse semantics:
      - Single click on a body cell toggles SELECTION only.
      - Click-drag rectangular paints SELECTION across cells, leaving status
        untouched.
      - "Clear selection" wipes selection only; status colors persist.
      - "Select all" sets selection True everywhere; status untouched.
      - "Run selected" runs every selected cell, updates status as each
        finishes, and LEAVES selection on so the user can see what they
        just ran. They explicitly Clear before queueing the next batch.

    Rows: the row set is driven by the currently selected drive group's
    entries (e.g. ``ramsey_3800+`` -> ``1_3800+`` ... ``8_3800+``). When no
    drive group is selected, the rows are the readout group's entries
    (e.g. ``1, 3, 4, ..., 8``). When the drive group changes, the table
    rebuilds and best-effort preserves OK/Fail status for rows whose name
    still exists.
    """

    name = "Auto-Calibration"

    # (canonical stage name = StageTab.name, header label)
    STAGE_KEYS = [
        ("Transmission",  "Trans"),
        ("QubitSpec",     "Spec"),
        ("AmplitudeRabi", "Rabi"),
        ("ReadoutOpt",    "ROpt"),
        ("PulseOpt",      "POpt"),
        ("SingleShot",    "SS"),
        ("T1",            "T1"),
        ("T2R",           "T2R"),
    ]

    # Status-layer cell colors (background only; selection is a border drawn
    # by CalibCellDelegate). Light shades chosen so dark text stays readable.
    COLOR_DISABLED = QColor("#ffffff")   # never run / no status
    COLOR_OK       = QColor("#cdf5cd")   # pale green
    COLOR_FAIL     = QColor("#f8c4c4")   # pale red
    COLOR_HEADER   = QColor("#dcdcdc")   # light gray for label col + header row
    COLOR_BLOCKED  = QColor("#ebebeb")   # readout-side stage blocked by drive group

    def __init__(self, state: CalibState, get_main, parent=None):
        super().__init__(parent)
        self.state = state
        self.get_main = get_main
        self.worker: Optional[AutoCalibWorker] = None
        self._row_qubit: list[str] = []        # data-row r -> qubit label; row 0 is header in-table
        self._result_buttons: dict[str, QPushButton] = {}
        # Per-qubit per-stage cache of (expt, data) for the results dialog.
        self.results: dict[str, dict[str, tuple[Any, Any]]] = {}
        # Persistent selection (item 3) + run-outcome (item 6 colors).
        self._cell_enabled: dict[tuple[str, str], bool] = {}
        self._cell_outcome: dict[tuple[str, str], Optional[str]] = {}

        # --- readout / drive group selectors (moved from MainWindow toolbar) ---
        self.readout_group_combo = QComboBox()
        self.readout_group_combo.setMinimumWidth(160)
        self.readout_group_combo.setToolTip(
            "Readout point — entries become the qubit rows below."
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
        selector_row = QHBoxLayout()
        selector_row.addWidget(QLabel("Readout group:"))
        selector_row.addWidget(self.readout_group_combo)
        selector_row.addSpacing(16)
        selector_row.addWidget(QLabel("Drive group:"))
        selector_row.addWidget(self.drive_group_combo)
        selector_row.addStretch(1)
        selector_widget = QWidget(); selector_widget.setLayout(selector_row)

        # MUX chip strip — qubits selected here are MUXed alongside the
        # target row's qubit for ReadoutOpt / PulseOpt / SingleShot only.
        # Target is always read out; the chips toggle the *other* qubits.
        self.mux_strip = MuxChipStrip()
        self.mux_strip.setToolTip(
            "Qubits to MUX alongside the target for ReadoutOpt / PulseOpt / "
            "SingleShot. Click-drag to toggle. Other stages ignore this."
        )
        self.mux_strip.selection_changed.connect(self._on_mux_changed)
        mux_row = QHBoxLayout()
        mux_row.addWidget(QLabel("MUX with:"))
        mux_row.addWidget(self.mux_strip, 1)
        mux_widget = QWidget(); mux_widget.setLayout(mux_row)

        # Pulse chain chip strip — qubits in the experimental drive sequence.
        # Only consumed by PulseOpt. Visible only when a drive group is
        # active (the chain concept needs JSON-ordered drive-group entries).
        self.pulse_chain_strip = MuxChipStrip()
        self.pulse_chain_strip.setToolTip(
            "Experimental drive sequence (JSON-ordered): qubits ticked here "
            "are pre-pulsed in JSON order before the calibrated target. "
            "Only PulseOpt consumes this. Click-drag to toggle."
        )
        self.pulse_chain_strip.selection_changed.connect(self._on_pulse_chain_changed)
        self.pulse_chain_label = QLabel("Pulse chain:")
        pulse_chain_row = QHBoxLayout()
        pulse_chain_row.addWidget(self.pulse_chain_label)
        pulse_chain_row.addWidget(self.pulse_chain_strip, 1)
        self.pulse_chain_widget = QWidget(); self.pulse_chain_widget.setLayout(pulse_chain_row)
        self.pulse_chain_widget.setVisible(False)  # shown when drive group active

        # --- run / stop / progress ---
        button_row = QHBoxLayout()
        self.run_btn = QPushButton("Run selected")
        self.run_btn.setToolTip(
            "Run every enabled (qubit, stage) cell sequentially. "
            "Click a cell to toggle; click-drag to paint many at once."
        )
        self.run_btn.clicked.connect(self.on_run)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.on_stop)
        self.progress_lbl = QLabel("Idle.")
        self.select_all_btn = QPushButton("Select all")
        self.select_all_btn.clicked.connect(self._select_all_cells)
        self.select_none_btn = QPushButton("Clear selection")
        self.select_none_btn.clicked.connect(self._deselect_all_cells)
        button_row.addWidget(self.run_btn)
        button_row.addWidget(self.stop_btn)
        button_row.addSpacing(20)
        button_row.addWidget(self.select_all_btn)
        button_row.addWidget(self.select_none_btn)
        button_row.addSpacing(20)
        button_row.addWidget(self.progress_lbl, 1)
        button_widget = QWidget(); button_widget.setLayout(button_row)

        # --- table: in-table header row (row 0) holds stage labels ---
        self.table = CalibTable(self)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.verticalHeader().setVisible(False)
        # We use an in-table header row (row 0) instead of the Qt horizontal
        # header, because cellClicked-style mouse handling on QHeaderView is
        # awkward; this also makes "click a stage column to show its param
        # form" trivially uniform with body-cell clicks.
        self.table.horizontalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(False)
        # Wire the parent's mouse-handler signals from the subclass.
        self.table.body_toggled.connect(self._on_body_toggled)
        self.table.body_clicked.connect(self._on_body_clicked)
        self.table.header_clicked.connect(self._on_header_clicked)
        self.table.label_clicked.connect(self._on_label_clicked)

        # --- log area (left side, under the table) ---
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        f = QFont(); f.setStyleHint(QFont.Monospace); f.setFamily("Consolas")
        self.log.setFont(f)
        self.log.setPlaceholderText("Per-stage status messages will appear here.")

        # --- right side: stacked plot page + per-stage param-form pages ---
        # Page 0 is the live plot. Pages 1..N (one per stage) are the
        # re-parented param_form widgets owned by each StageTab (option (a)
        # from the rewrite plan). The per-stage tab classes are still
        # instantiated in MainWindow but never added to the QTabWidget, so
        # their param_form widgets persist as the source of truth for stage
        # parameters across runs.
        self.right_stack = QStackedWidget()
        self._stage_page_index: dict[str, int] = {}

        # Page 0: live plot.
        self.live_canvas = MplCanvas(self, height=4.0)
        self.live_toolbar = NavigationToolbar(self.live_canvas, self)
        self.live_label = QLabel("Live plot — click a body cell to view its cached result.")
        self.live_label.setStyleSheet("color: #555;")
        plot_w = QWidget()
        pv = QVBoxLayout(plot_w)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.addWidget(self.live_label)
        pv.addWidget(self.live_toolbar)
        pv.addWidget(self.live_canvas, 1)
        self.right_stack.addWidget(plot_w)
        # Stage-form pages are added lazily after MainWindow constructs the
        # StageTab instances and calls self.attach_stage_forms(stages).

        # --- splitter: left = table + log, right = stacked panel ---
        left_v = QVBoxLayout()
        left_v.setContentsMargins(0, 0, 0, 0)
        left_v.addWidget(self.table, 3)
        left_v.addWidget(self.log, 1)
        left_w = QWidget(); left_w.setLayout(left_v)

        splitter = QSplitter()
        splitter.addWidget(left_w)
        splitter.addWidget(self.right_stack)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        layout = QVBoxLayout(self)
        layout.addWidget(selector_widget)
        layout.addWidget(mux_widget)
        layout.addWidget(self.pulse_chain_widget)
        layout.addWidget(button_widget)
        layout.addWidget(splitter, 1)

        self.refresh_qubits()

    # ---- stage param-form wiring (called by MainWindow after stages exist) ----

    def attach_stage_forms(self, stages: list["StageTab"]) -> None:
        """Re-parent each stage's ``param_form`` into the right-side stack.

        Stages are kept as headless StageTab instances (per the (a) strategy):
        their param_form, make_experiment, on_apply, render_into are still the
        single source of truth; we only steal the param_form QWidget for
        display here.
        """
        for s in stages:
            page = QWidget()
            v = QVBoxLayout(page)
            v.setContentsMargins(0, 0, 0, 0)
            title = QLabel(
                f"<b>{s.name}</b> — parameters used by every Run of this stage."
            )
            title.setWordWrap(True)
            v.addWidget(title)
            # param_form is a QGroupBox owned by the StageTab; re-parent it
            # by adding to this layout (Qt auto-reparents on addWidget).
            v.addWidget(s.param_form)
            v.addStretch(1)
            idx = self.right_stack.addWidget(page)
            self._stage_page_index[s.name] = idx

    # ---- group selectors ----

    def _on_readout_group_changed(self, _idx: int) -> None:
        name = self.readout_group_combo.currentText() or ""
        self.state.current_readout_group = name
        # Mirror to current_qubit_label so SingleShot.on_apply writes into
        # the right entry on subsequent runs.
        self.refresh_qubits()
        # Rebuild MUX chips from this group's entries; default all selected.
        self._rebuild_mux_strip()

    def _rebuild_mux_strip(self) -> None:
        jd = self.state.qubit_parameters_json or {}
        rg = self.state.current_readout_group or ""
        entries = list(((jd.get("readout_groups") or {}).get(rg, {})
                                                      .get("entries") or {}).keys())
        # Default: every qubit in the readout group is MUXed.
        self.mux_strip.set_qubits(entries, entries)
        self.state.mux_readouts = list(entries)

    def _on_mux_changed(self, selected: list) -> None:
        self.state.mux_readouts = list(selected)

    def _on_pulse_chain_changed(self, selected: list) -> None:
        self.state.pulse_chain = list(selected)

    def _rebuild_pulse_chain_strip(self) -> None:
        """Populate the pulse-chain chips from the active drive group, in
        JSON order. Hides the strip entirely when no drive group is active.
        Selection resets to empty on every rebuild (chain off by default).
        """
        jd = self.state.qubit_parameters_json or {}
        dg = self.state.current_drive_group or ""
        if not dg:
            self.pulse_chain_widget.setVisible(False)
            self.pulse_chain_strip.set_qubits([], [])
            self.state.pulse_chain = []
            return
        entries = list(((jd.get("drive_groups") or {}).get(dg, {})
                                                     .get("entries") or {}).keys())
        # Parse qubit labels from entry names; preserve JSON order and dedupe.
        seen: set = set()
        qubits_in_order: list[str] = []
        for ename in entries:
            q = _readout_qubit_for_entry(ename)
            if q not in seen:
                seen.add(q)
                qubits_in_order.append(q)
        self.pulse_chain_strip.set_qubits(qubits_in_order, [])
        self.state.pulse_chain = []
        self.pulse_chain_widget.setVisible(True)

    def _on_drive_group_changed(self, _idx: int) -> None:
        data = self.drive_group_combo.currentData()
        self.state.current_drive_group = data or ""
        # Rows are driven by drive group when set, readout group otherwise.
        self.refresh_qubits()
        self._rebuild_pulse_chain_strip()

    def refresh_groups_from_state(self) -> None:
        """Repopulate readout/drive combos from state.qubit_parameters_json.

        Called by MainWindow after the params JSON is (re)loaded.
        """
        jd = self.state.qubit_parameters_json or {}
        readout_groups = list((jd.get("readout_groups") or {}).keys())
        drive_groups = list((jd.get("drive_groups") or {}).keys())

        self.readout_group_combo.blockSignals(True)
        self.readout_group_combo.clear()
        for n in readout_groups:
            self.readout_group_combo.addItem(n)
        if readout_groups:
            self.readout_group_combo.setCurrentIndex(0)
            self.state.current_readout_group = readout_groups[0]
        else:
            self.state.current_readout_group = ""
        self.readout_group_combo.blockSignals(False)

        self.drive_group_combo.blockSignals(True)
        self.drive_group_combo.clear()
        self.drive_group_combo.addItem("(readout)", "")
        for n in drive_groups:
            self.drive_group_combo.addItem(n, n)
        self.drive_group_combo.setCurrentIndex(0)
        self.state.current_drive_group = ""
        self.drive_group_combo.blockSignals(False)

        self.refresh_qubits()
        self._rebuild_mux_strip()
        self._rebuild_pulse_chain_strip()

    # ---- table population ----

    def refresh_qubits(self):
        """Rebuild rows from the selected drive group, or readout group fallback.

        Row 0 is an in-table header row holding stage labels (so clicking a
        stage label is just a cellClicked-style event on (0, c)). Data rows
        follow; col 0 is the row label, cols 1..N are stage cells, last col
        is the Result-popup button.

        Row source: drive_groups[<drive>].entries if a drive group is picked,
        else readout_groups[<readout>].entries. Selection is wiped on every
        rebuild; status (outcomes + cached results) is preserved best-effort
        for rows whose name survives the rebuild.
        """
        jd = getattr(self.state, "qubit_parameters_json", {}) or {}
        readout_name = getattr(self.state, "current_readout_group", "") or ""
        drive_name = getattr(self.state, "current_drive_group", "") or ""

        entries: list[str] = []
        if drive_name and drive_name in (jd.get("drive_groups") or {}):
            entries = list(jd["drive_groups"][drive_name].get("entries", {}).keys())
        elif readout_name and readout_name in (jd.get("readout_groups") or {}):
            entries = list(jd["readout_groups"][readout_name].get("entries", {}).keys())
        if not entries:
            # Legacy fallback: number qubits 1..N from CalibState.
            entries = [str(i + 1) for i in range(self.state.n_qubits)]
        keys = entries

        # Best-effort preserve outcomes/results for surviving row names. Drop
        # selection entirely on rebuild (user explicitly Clears anyway, and
        # selection across schema changes is ambiguous).
        prev_outcome = dict(self._cell_outcome)
        prev_results = dict(self.results)

        n_stages = len(self.STAGE_KEYS)
        result_col = 1 + n_stages
        n_cols = 1 + n_stages + 1
        self.table.setColumnCount(n_cols)
        # Row 0 is the header; followed by len(keys) data rows.
        self.table.setRowCount(1 + len(keys))
        self._row_qubit = list(keys)
        self._result_buttons = {}
        self._cell_enabled = {}
        self._cell_outcome = {}
        self.results = {}
        # Install the selection-border delegate once; safe to reinstall.
        self.table.setItemDelegate(CalibCellDelegate(self.table))

        # Inform the subclass which cells are body cells.
        self.table.body_col_min = 1
        self.table.body_col_max = n_stages
        self.table.header_row = 0

        # --- header row (row 0): "Qubit \ Stage" in col 0, stage labels in 1..N ---
        corner = QTableWidgetItem("Qubit \\ Stage")
        corner.setFlags(Qt.ItemIsEnabled)
        corner.setTextAlignment(Qt.AlignCenter)
        corner.setBackground(self.COLOR_HEADER)
        f = corner.font(); f.setBold(True); corner.setFont(f)
        self.table.setItem(0, 0, corner)
        for c, (stage_name, hdr) in enumerate(self.STAGE_KEYS, start=1):
            it = QTableWidgetItem(hdr)
            it.setFlags(Qt.ItemIsEnabled)
            it.setTextAlignment(Qt.AlignCenter)
            it.setBackground(self.COLOR_HEADER)
            f = it.font(); f.setBold(True); it.setFont(f)
            it.setToolTip(f"Click to edit {stage_name} parameters.")
            self.table.setItem(0, c, it)
        # Header corner-spanning cell over the result column too.
        hdr_result = QTableWidgetItem("Result")
        hdr_result.setFlags(Qt.ItemIsEnabled)
        hdr_result.setTextAlignment(Qt.AlignCenter)
        hdr_result.setBackground(self.COLOR_HEADER)
        f = hdr_result.font(); f.setBold(True); hdr_result.setFont(f)
        self.table.setItem(0, result_col, hdr_result)

        # --- data rows ---
        for ri, Q in enumerate(keys):
            r = ri + 1
            label = QTableWidgetItem(str(Q))
            label.setFlags(Qt.ItemIsEnabled)
            label.setTextAlignment(Qt.AlignCenter)
            label.setBackground(self.COLOR_HEADER)
            self.table.setItem(r, 0, label)

            for c, (stage_name, _) in enumerate(self.STAGE_KEYS, start=1):
                cell = QTableWidgetItem("")
                cell.setFlags(Qt.ItemIsEnabled)
                cell.setTextAlignment(Qt.AlignCenter)
                # Selection flag (drives border via CalibCellDelegate).
                cell.setData(SELECTION_ROLE, False)
                self.table.setItem(r, c, cell)
                self._cell_enabled[(Q, stage_name)] = False
                # Best-effort restore last outcome for surviving row names.
                self._cell_outcome[(Q, stage_name)] = prev_outcome.get((Q, stage_name))
                self._paint_cell(r, c)
                if self._is_disabled_stage(stage_name):
                    cell.setToolTip(
                        f"{stage_name} disabled: drive groups are not "
                        f"readout-calibration vehicles."
                    )
                # Restore status text for cells with a preserved outcome.
                if self._cell_outcome[(Q, stage_name)] == "ok":
                    cell.setText("OK")
                elif self._cell_outcome[(Q, stage_name)] == "fail":
                    cell.setText("FAIL")

            result_btn = QPushButton("-")
            # Restore cached-results presence for surviving rows.
            if Q in prev_results:
                self.results[Q] = prev_results[Q]
                result_btn.setText("View")
                result_btn.setEnabled(True)
            else:
                result_btn.setEnabled(False)
            result_btn.setToolTip("Open a grid of all stage plots for this qubit.")
            result_btn.clicked.connect(
                lambda _checked=False, qid=Q: self._on_result_clicked(qid)
            )
            holder = QWidget()
            hl = QHBoxLayout(holder); hl.addWidget(result_btn)
            hl.setAlignment(Qt.AlignCenter); hl.setContentsMargins(0, 0, 0, 0)
            self.table.setCellWidget(r, result_col, holder)
            self._result_buttons[Q] = result_btn

        # Make the table fill space (item 2): all columns stretch evenly, all
        # rows resize-to-contents. No fixed-width groupbox wrapper.
        hh = self.table.horizontalHeader()
        # Even though horizontalHeader is hidden, its size-policy still drives
        # column widths.
        hh.setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

    # ---- selection / paint helpers ----

    def _data_row_for(self, Q: str) -> int:
        """Return the actual table row for qubit label Q (data rows start at 1)."""
        return self._row_qubit.index(Q) + 1

    def _col_for(self, stage_name: str) -> Optional[int]:
        for i, (name, _) in enumerate(self.STAGE_KEYS):
            if name == stage_name:
                return 1 + i
        return None

    def _key_at(self, r: int, c: int) -> Optional[tuple[str, str]]:
        """(qubit_label, stage_name) for a body cell, or None if not a body cell."""
        if r < 1 or r > len(self._row_qubit):
            return None
        if c < 1 or c > len(self.STAGE_KEYS):
            return None
        return (self._row_qubit[r - 1], self.STAGE_KEYS[c - 1][0])

    def _is_disabled_stage(self, stage_name: str) -> bool:
        """True when this stage is non-runnable for the current row source.

        Drive-group rows are not readout-calibration vehicles: their FF is
        the drive-side point, not the readout point, so running Transmission
        / ReadoutOpt / SingleShot from such a row would write meaningless
        readout params.
        """
        drive_active = bool(getattr(self.state, "current_drive_group", "") or "")
        return drive_active and stage_name in READOUT_SIDE_STAGES

    def _paint_cell(self, r: int, c: int) -> None:
        """Set one body cell's STATUS background from _cell_outcome only.

        Selection is drawn by CalibCellDelegate from SELECTION_ROLE; see
        _set_cell_enabled. The two layers are independent. Cells for
        disabled stages get a distinct gray that overrides outcome color.
        """
        key = self._key_at(r, c)
        if key is None:
            return
        item = self.table.item(r, c)
        if item is None:
            return
        _, stage_name = key
        if self._is_disabled_stage(stage_name):
            item.setBackground(self.COLOR_BLOCKED)
            return
        outcome = self._cell_outcome.get(key)
        if outcome == "ok":
            item.setBackground(self.COLOR_OK)
        elif outcome == "fail":
            item.setBackground(self.COLOR_FAIL)
        else:
            item.setBackground(self.COLOR_DISABLED)

    def _set_cell_enabled(self, r: int, c: int, on: bool) -> None:
        """Toggle SELECTION (border) only — status background is untouched.

        Disabled stages (readout-side stages while a drive group is active)
        cannot be selected; the toggle is silently dropped.
        """
        key = self._key_at(r, c)
        if key is None:
            return
        _, stage_name = key
        if self._is_disabled_stage(stage_name):
            return
        self._cell_enabled[key] = bool(on)
        item = self.table.item(r, c)
        if item is not None:
            # SELECTION_ROLE drives the delegate's border paint. Setting data
            # triggers a repaint automatically; no _paint_cell call needed.
            item.setData(SELECTION_ROLE, bool(on))

    def _set_cell_status_text(self, Q: str, stage_name: str, text: str) -> None:
        """Set status text + (optionally) refresh color via _cell_outcome."""
        try:
            r = self._data_row_for(Q)
        except ValueError:
            return
        c = self._col_for(stage_name)
        if c is None:
            return
        item = self.table.item(r, c)
        if item is not None:
            item.setText(text)

    def _select_all_cells(self) -> None:
        """Enable every body cell."""
        for ri, Q in enumerate(self._row_qubit):
            r = ri + 1
            for ci, (stage_name, _) in enumerate(self.STAGE_KEYS):
                c = ci + 1
                self._set_cell_enabled(r, c, True)

    def _deselect_all_cells(self) -> None:
        for ri, Q in enumerate(self._row_qubit):
            r = ri + 1
            for ci, (stage_name, _) in enumerate(self.STAGE_KEYS):
                c = ci + 1
                self._set_cell_enabled(r, c, False)

    # ---- mouse-handler signal slots ----

    def _on_body_toggled(self, r: int, c: int, new_state: bool) -> None:
        """A body cell was painted on by mouse press/move; update enabled flag."""
        self._set_cell_enabled(r, c, new_state)

    def _on_body_clicked(self, r: int, c: int) -> None:
        """Body cell click: switch right panel to live plot, render cached result if any."""
        self.right_stack.setCurrentIndex(0)
        key = self._key_at(r, c)
        if key is None:
            return
        Q, stage_name = key
        entry = self.results.get(Q, {}).get(stage_name)
        if entry is None:
            self.live_canvas.reset()
            self.live_canvas.ax.text(
                0.5, 0.5, "(no data — run this scan first)",
                ha="center", va="center",
                transform=self.live_canvas.ax.transAxes,
                color="#888",
            )
            self.live_canvas.ax.set_xticks([])
            self.live_canvas.ax.set_yticks([])
            self.live_canvas.draw()
            self.live_label.setText(f"Live plot — Q{Q} / {stage_name}: (no data)")
            return
        expt, data = entry
        try:
            self._render_live(Q, stage_name, expt, data)
        except Exception:
            traceback.print_exc()

    def _on_header_clicked(self, c: int) -> None:
        """Stage-label header cell: switch the right pane to that stage's param form."""
        if c < 1 or c > len(self.STAGE_KEYS):
            return
        stage_name = self.STAGE_KEYS[c - 1][0]
        idx = self._stage_page_index.get(stage_name)
        if idx is not None:
            self.right_stack.setCurrentIndex(idx)

    def _on_label_clicked(self, r: int) -> None:
        """Qubit-label cell: currently inert. Reserved for a future summary view."""
        return

    # ---- run / stop ----

    def _enabled_pairs(self) -> list[tuple[str, str]]:
        return [k for k, v in self._cell_enabled.items() if v]

    def on_run(self):
        if self.worker is not None and self.worker.isRunning():
            return
        if not self.state.is_connected():
            QMessageBox.warning(self, "Not connected",
                                "Connect to the RFSoC before running.")
            return
        pairs = self._enabled_pairs()
        if not pairs:
            QMessageBox.information(
                self, "Nothing to run",
                "Click cells in the stage columns to enable them, then Run."
            )
            return

        main = self.get_main()
        stages_by_name = {s.name: s for s in main.stages}

        # Snapshot per-stage params on the GUI thread (worker shouldn't touch widgets).
        schedule: list[tuple[str, str, dict]] = []
        for Q, stage_name in pairs:
            stage = stages_by_name.get(stage_name)
            if stage is None:
                self.log.appendPlainText(f"[skip] no stage {stage_name}")
                continue
            params = stage.param_form.values()
            schedule.append((Q, stage_name, params))

        if not schedule:
            return

        run_pairs = {(Q, name) for Q, name, _ in schedule}
        # Reset stale results/outcomes for cells about to run; clear status text.
        for Q, stage_name in run_pairs:
            self._cell_outcome[(Q, stage_name)] = None
            self._set_cell_status_text(Q, stage_name, "queued")
        for Q, _ in run_pairs:
            self.results.pop(Q, None)
            btn = self._result_buttons.get(Q)
            if btn is not None:
                btn.setText("-")
                btn.setEnabled(False)
        # Repaint the touched cells.
        for Q, stage_name in run_pairs:
            try:
                r = self._data_row_for(Q)
            except ValueError:
                continue
            c = self._col_for(stage_name)
            if c is not None:
                self._paint_cell(r, c)

        # Reset live canvas + UI.
        self.live_canvas.reset()
        self.live_label.setText("Live plot — waiting for the first stage to acquire...")
        self.log.clear()
        self.progress_lbl.setText(f"Running {len(schedule)} jobs...")
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        # Disable group selectors while running — mid-run group changes would
        # call refresh_qubits and trash _row_qubit while the worker iterates it.
        self.readout_group_combo.setEnabled(False)
        self.drive_group_combo.setEnabled(False)

        self.worker = AutoCalibWorker(self.state, schedule, stages_by_name)
        self.worker.progress.connect(self._on_progress)
        self.worker.stage_done.connect(self._on_stage_done)
        self.worker.stage_failed.connect(self._on_stage_failed)
        self.worker.log_msg.connect(self.log.appendPlainText)
        self.worker.finished_all.connect(self._on_all_finished)
        self.worker.start()

    def on_stop(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.log.appendPlainText("[STOP] requested — finishing current stage...")
            self.stop_btn.setEnabled(False)

    # ---- worker signal handlers (GUI thread) ----

    def _on_progress(self, Q: str, stage_name: str, status: str):
        self._set_cell_status_text(Q, stage_name, status)
        self.progress_lbl.setText(f"Q{Q} / {stage_name}: {status}")

    def _on_stage_done(self, Q: str, stage_name: str, summary: str, expt, data, elapsed_s: float = 0.0):
        self._cell_outcome[(Q, stage_name)] = "ok"
        # Cell text comes from stage.cell_summary (default "OK"); SingleShot
        # overrides to show fidelity %. Log line below still uses the rich
        # on_success summary. Fallback to "OK" on any error so a broken hook
        # never blocks the cell repaint.
        cell_text = "OK"
        try:
            main = self.get_main()
            stage = next((s for s in main.stages if s.name == stage_name), None)
            if stage is not None:
                cell_text = stage.cell_summary(expt, data) or "OK"
        except Exception:
            traceback.print_exc()
        self._set_cell_status_text(Q, stage_name, cell_text)
        try:
            r = self._data_row_for(Q); c = self._col_for(stage_name)
            if c is not None:
                self._paint_cell(r, c)
        except ValueError:
            pass
        self.log.appendPlainText(f"[OK]   ({elapsed_s:5.1f} s)  Q{Q} {stage_name}: {summary}")

        # Cache result + render to live.
        self.results.setdefault(Q, {})[stage_name] = (expt, data)
        try:
            self._render_live(Q, stage_name, expt, data)
        except Exception:
            traceback.print_exc()

        btn = self._result_buttons.get(Q)
        if btn is not None:
            btn.setText("View")
            btn.setEnabled(True)

        # Mirror state changes into the params tab.
        try:
            self.get_main().refresh_qubit_summary()
        except Exception:
            pass

    def _render_live(self, Q: str, stage_name: str, expt, data):
        # Switch to plot page before rendering so the user sees the plot.
        self.right_stack.setCurrentIndex(0)
        try:
            main = self.get_main()
            stages_by_name = {s.name: s for s in main.stages}
        except Exception:
            return
        stage = stages_by_name.get(stage_name)
        if stage is None:
            return
        self.live_canvas.reset()
        try:
            # Row label Q may be a drive-entry name like '1_3800+'; render_into
            # expects the underlying integer readout-qubit id.
            ro_q = _readout_qubit_for_entry(Q)
            qid = int(ro_q) if ro_q.isdigit() else None
            stage.render_into(self.live_canvas.ax, expt, data, qubit_id=qid)
        except Exception as exc:
            self.live_canvas.ax.text(
                0.5, 0.5, f"render failed:\n{exc}",
                ha="center", va="center",
                transform=self.live_canvas.ax.transAxes,
            )
            traceback.print_exc()
        self.live_canvas.draw()
        self.live_label.setText(f"Live plot — Q{Q} / {stage_name}")

    def _on_result_clicked(self, Q: str):
        res = self.results.get(Q)
        if not res:
            QMessageBox.information(
                self, "No results",
                f"No data for Q{Q} yet. Run a calibration first.",
            )
            return
        try:
            main = self.get_main()
            stages_by_name = {s.name: s for s in main.stages}
        except Exception:
            stages_by_name = {}
        dlg = ResultsDialog(Q, res, stages_by_name, parent=self)
        dlg.exec_()

    def _on_stage_failed(self, Q: str, stage_name: str, msg: str, expt, data, elapsed_s: float = 0.0):
        self._cell_outcome[(Q, stage_name)] = "fail"
        self._set_cell_status_text(Q, stage_name, "FAIL")
        try:
            r = self._data_row_for(Q); c = self._col_for(stage_name)
            if c is not None:
                self._paint_cell(r, c)
        except ValueError:
            pass
        first, sep, rest = msg.partition("\n")
        self.log.appendPlainText(f"[FAIL] ({elapsed_s:5.1f} s)  Q{Q} {stage_name}: {first}")
        if rest:
            for line in rest.rstrip().splitlines():
                self.log.appendPlainText(f"       {line}")

        # Cache partial result + render even on fail (mirrors prior behaviour).
        if expt is not None and data is not None:
            self.results.setdefault(Q, {})[stage_name] = (expt, data)
            try:
                self._render_live(Q, stage_name, expt, data)
            except Exception:
                traceback.print_exc()
            btn = self._result_buttons.get(Q)
            if btn is not None:
                btn.setText("View")
                btn.setEnabled(True)

    def _on_all_finished(self):
        self.progress_lbl.setText("Done.")
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.readout_group_combo.setEnabled(True)
        self.drive_group_combo.setEnabled(True)
        self.worker = None


# ---------------------------------------------------------------------------
# LatticePointCalibrationTab — per-qubit Ramsey-vs-FF -> shared base_params slot
# ---------------------------------------------------------------------------


class LatticePointCalibWorker(QThread):
    """Run ``RamseyVsFF`` once per scheduled (drive_entry, ro_qubit) row.

    Each row's sweep window is snapshotted on the GUI thread (so concurrent
    mutations of ``base_params`` between rows don't drift the start/stop) and
    handed in as part of the schedule. The worker subclasses ``RamseyVsFF``
    locally with a headless Agg ``display()`` to dodge the
    ``SweepExperimentND.acquire`` Qt-from-worker-thread deadlock (same fix as
    ``TwoQubitChevronWorker``); ``analyze()`` is then called to populate
    ``data["data"]["center_gain"]``.
    """

    progress     = pyqtSignal(str, str)                    # row_label, status text
    row_done     = pyqtSignal(str, object, object, float)  # row_label, expt, data, elapsed_s
    row_failed   = pyqtSignal(str, str, object, object, float)  # row_label, err, expt, data, elapsed_s
    log_msg      = pyqtSignal(str)
    finished_all = pyqtSignal()

    def __init__(self, state: CalibState, schedule: list[dict]):
        super().__init__()
        self.state = state
        # schedule: list of {row_label, ro_q, current_value, sweep_params}
        self.schedule = schedule
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        # Lazy import — RamseyVsFF pulls qick-flavored deps; keep GUI cold-start cheap.
        try:
            from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Characterization_Sweeps.mRamseyVsFF import (
                RamseyVsFF,
            )
        except Exception as exc:
            self.log_msg.emit(f"[FATAL] cannot import RamseyVsFF: {exc}")
            self.finished_all.emit()
            return

        from matplotlib.figure import Figure as _BareFigure
        from matplotlib.backends.backend_agg import FigureCanvasAgg

        # Headless-display subclass: same workaround the TwoQubit worker uses.
        # SweepExperimentND.acquire()'s plot branch fires regardless of
        # plotDisp/plotSave (parenthesization bug at line 215); routing that
        # through an Agg canvas keeps Qt out of the worker thread.
        class _RamseyVsFFHeadless(RamseyVsFF):
            def display(self, data=None, plotDisp=False, figNum=1,
                        plotSave=False, block=False, fig_axs=None):
                fig = _BareFigure()
                FigureCanvasAgg(fig)
                ax = fig.add_subplot(111)
                return fig, [ax]

            def _update_fig(self, data, fig, axs):
                pass

        for row in self.schedule:
            if self._stop:
                self.log_msg.emit(f"--- aborted before {row['row_label']} ---")
                break
            row_label = row['row_label']
            ro_q = row['ro_q']
            current_value = row['current_value']
            sweep_params = row['sweep_params']
            t0 = time.perf_counter()
            self.progress.emit(row_label, "starting")
            expt = None
            data = None
            try:
                overrides = dict(sweep_params)
                overrides.update({
                    "qubit_FF_index": int(ro_q),
                    "FF_gain_start": int(current_value) - int(sweep_params["__window"]),
                    "FF_gain_stop":  int(current_value) + int(sweep_params["__window"]),
                    "FF_gain_steps": int(sweep_params["__steps"]),
                    "populations": False,
                })
                # Pop GUI-only carry-throughs before they reach cfg.
                overrides.pop("__window", None)
                overrides.pop("__steps", None)

                # build_cfg_for_qubit: drive entry = row_label, readout qubit = ro_q.
                cfg = build_cfg_for_qubit(
                    self.state, str(ro_q),
                    qubit_pulse=[row_label],
                    qubit_readout=[str(ro_q)],
                    overrides=overrides,
                )
                self.progress.emit(row_label, "acquiring")
                expt = _RamseyVsFFHeadless(
                    path="FF_vs_Ramsey",
                    cfg=cfg,
                    soc=self.state.soc, soccfg=self.state.soccfg,
                    outerFolder=self.state.outer_folder,
                )
                # Pass plotDisp/plotSave=False so the base acquire() doesn't
                # try to plt.show()/plt.savefig() from the worker thread; the
                # Agg-display subclass above already handles the inline
                # plot branch at line 215.
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
                # mRamseyVsFF.analyze() writes center_gain into data["data"].
                try:
                    expt.analyze(data)
                except Exception as ana_exc:
                    self.log_msg.emit(
                        f"[warn] analyze() raised for {row_label}: {ana_exc}"
                    )
                elapsed = time.perf_counter() - t0
                center_gain = data.get("data", {}).get("center_gain")
                if center_gain is None:
                    self.row_failed.emit(
                        row_label,
                        "Ramsey fit returned no center_gain",
                        expt, data, elapsed,
                    )
                    continue
                self.row_done.emit(row_label, expt, data, elapsed)
            except Exception as exc:
                elapsed = time.perf_counter() - t0
                self.row_failed.emit(
                    row_label,
                    f"{exc}\n{traceback.format_exc()}",
                    expt, data, elapsed,
                )
        self.finished_all.emit()


class _LatticeRowTable(QTableWidget):
    """Whole-row click-toggle + drag-rectangle selection.

    Mirrors ``CalibTable``'s pattern but in 1D (row state only — no column
    structure). Clicking anywhere on a row toggles that row's selection;
    dragging extends the selection to every row between press and current,
    restoring rows that leave the range to their pre-drag state.
    """
    row_toggled = pyqtSignal(int, bool)   # (row, new_state) — emitted per row
    row_clicked = pyqtSignal(int)         # (row) — emitted on press for plot focus

    # Columns whose clicks should NOT toggle selection — they need normal Qt
    # event flow (e.g. double-click to enter an editor). Populated by the tab.
    PASSTHROUGH_COLS: set = set()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self._painter = DragPainter(
            target_at=self._row_at,
            get_state=self._row_state,
            set_state=lambda r, on: self.row_toggled.emit(r, on),
            region=lambda s, c, _: {r for r in range(min(s, c), max(s, c) + 1)
                                   if 0 <= r < self.rowCount()},
        )

    def _row_state(self, row: int) -> bool:
        item = self.item(row, 0)
        return bool(item.data(SELECTION_ROLE)) if item is not None else False

    def _row_at(self, pos) -> Optional[int]:
        r = self.indexAt(pos).row()
        return r if r >= 0 else None

    def mousePressEvent(self, event):
        idx = self.indexAt(event.pos())
        r, c = idx.row(), idx.column()
        if r < 0 or c in self.PASSTHROUGH_COLS:
            super().mousePressEvent(event)
            return
        if self._painter.press(event.pos()):
            self.row_clicked.emit(r)
        event.accept()

    def mouseMoveEvent(self, event):
        if not self._painter.in_progress():
            super().mouseMoveEvent(event)
            return
        self._painter.move(event.pos())

    def mouseReleaseEvent(self, event):
        if not self._painter.release():
            super().mouseReleaseEvent(event)
            return
        event.accept()

    def mouseDoubleClickEvent(self, event):
        # Always let double-click through (enables in-place editing on
        # editable cells regardless of column).
        super().mouseDoubleClickEvent(event)


class LatticePointCalibrationTab(QWidget):
    """Per-qubit Ramsey-vs-FF calibration of a shared ``base_params`` array.

    The selected drive group (e.g. ``ramsey_3800+``) carries a ``_recipe.base``
    pointing at a base_params array key (e.g. ``Expt_3800``). Each enabled
    row runs RamseyVsFF on that drive entry, sweeps FF around the array's
    current slot, and writes the fitted ``center_gain`` back into one slot of
    that shared array. Subsequent rows in the same batch pick up the updated
    array (build_cfg_for_qubit re-resolves the recipe each call).
    """

    name = "Lattice Point Calibration"
    # Column 0 of the row table — selection layer is painted here via
    # SELECTION_ROLE + CalibCellDelegate.
    SEL_COL = 0

    # Δ-magnitude color thresholds. White below the lower bound, amber up to
    # the upper bound, red above. Easy to tweak.
    DELTA_AMBER_MIN = 50
    DELTA_RED_MIN   = 300

    COLOR_WHITE  = QColor("#ffffff")
    COLOR_AMBER  = QColor("#fff1c2")
    COLOR_RED    = QColor("#f8c4c4")
    COLOR_OK     = QColor("#cdf5cd")
    COLOR_FAIL   = QColor("#f8c4c4")
    COLOR_HEADER = QColor("#dcdcdc")

    # (key, label, kind, default) — matches ParamForm spec format.
    SWEEP_FIELDS = [
        ("window",        "FF window (± from current)", "int",   200),
        ("steps",         "FF steps",                   "int",   7),
        ("expts",         "Ramsey expts",               "int",   71),
        ("stop_delay_us", "Stop delay (us)",            "float", 1.0),
        ("reps",          "reps",                       "int",   200),
        ("relax_delay",   "relax_delay",                "float", 100.0),
    ]

    # Presets pre-fill (window, steps). Other fields stay user-controlled.
    PRESETS = {
        "Fine":  (200, 7),
        "Rough": (5000, 11),
    }

    def __init__(self, state: CalibState, get_main, parent=None):
        super().__init__(parent)
        self.state = state
        self.get_main = get_main
        self.worker: Optional[LatticePointCalibWorker] = None
        # row_label -> bool (enabled for next batch).
        self._row_enabled: dict[str, bool] = {}
        # row_label -> (expt, data) for plot rendering on row-click.
        self._row_results: dict[str, tuple[Any, Any]] = {}
        # row_label -> new center_gain (int) from last successful run.
        self._row_new_ff: dict[str, int] = {}
        # row_label -> "ok"|"fail"|None.
        self._row_status: dict[str, Optional[str]] = {}
        # row_label -> ro_q (cached on rebuild for quick lookup).
        self._row_ro_q: dict[str, str] = {}

        # --- top: selectors / read-only labels ---
        self.drive_group_combo = QComboBox()
        self.drive_group_combo.setMinimumWidth(180)
        self.drive_group_combo.setToolTip(
            "Recipe-driven drive group whose _recipe.base names the target "
            "base_params array."
        )
        self.drive_group_combo.currentIndexChanged.connect(self._on_drive_group_changed)
        self.target_array_lbl = QLabel("Target array: —")
        self.target_freq_lbl = QLabel("Drive frequency: —")
        self.readout_group_lbl = QLabel("Readout group: —")
        for lbl in (self.target_array_lbl, self.target_freq_lbl, self.readout_group_lbl):
            lbl.setStyleSheet("color: #444; font-weight: bold;")
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Drive group:"))
        top_row.addWidget(self.drive_group_combo)
        top_row.addSpacing(20)
        top_row.addWidget(self.target_array_lbl)
        top_row.addSpacing(20)
        top_row.addWidget(self.target_freq_lbl)
        top_row.addSpacing(20)
        top_row.addWidget(self.readout_group_lbl)
        top_row.addStretch(1)
        top_w = QWidget(); top_w.setLayout(top_row)

        # --- per-qubit table ---
        # Columns: sel | Drive entry | Qubit | Current FF | New FF | Δ | Status
        # Column 0 carries the selection layer (SELECTION_ROLE on its item,
        # painted with a border by CalibCellDelegate). Click-drag toggles
        # rows persistently — same gesture as AutoCalib.
        self.table = _LatticeRowTable()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["", "Drive entry", "Qubit", "Current FF", "New FF", "Δ", "Status"]
        )
        self.table.verticalHeader().setVisible(False)
        # Col 3 (Current FF) is editable — double-click or F2 to enter editor.
        # Clicks on col 3 bypass the row-toggle gesture so the editor opens.
        # Current FF == base_params[idx] (sweep center, saved to disk on Save).
        # Edits write through to base_params; clearing reverts to snapshot.
        self.table.PASSTHROUGH_COLS = {3}
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
        )
        self.table.setItemDelegate(CalibCellDelegate(self.table))
        self.table.row_toggled.connect(self._on_row_toggled)
        self.table.row_clicked.connect(self._on_row_clicked)
        # Guard against itemChanged firing during programmatic table rebuilds.
        self._suppress_item_changed = False
        self.table.itemChanged.connect(self._on_item_changed)
        # Per-row flag: True if Current FF was hand-edited (vs fit or snapshot).
        # Drives the italic+bold display on col 3.
        self._row_current_user_edited: set[str] = set()
        # Set by _on_drive_group_changed; consumed by _rebuild_table_unguarded
        # to discard fit results that belong to the prior group.
        self._drive_group_changed: bool = False

        # --- sweep parameter form ---
        self.param_form = ParamForm("Sweep parameters", self.SWEEP_FIELDS)
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("(preset)", None)
        for name in self.PRESETS:
            self.preset_combo.addItem(name, name)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Preset:"))
        preset_row.addWidget(self.preset_combo)
        preset_row.addStretch(1)
        preset_w = QWidget(); preset_w.setLayout(preset_row)

        # --- run controls ---
        self.run_btn = QPushButton("Run selected")
        self.run_btn.setStyleSheet("font-weight: bold;")
        self.run_btn.clicked.connect(self._on_run)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop)
        self.select_all_btn = QPushButton("Select all")
        self.select_all_btn.clicked.connect(self._select_all)
        self.clear_btn = QPushButton("Clear selection")
        self.clear_btn.clicked.connect(self._clear_all)
        self.progress_lbl = QLabel("Idle.")
        run_row = QHBoxLayout()
        run_row.addWidget(self.run_btn)
        run_row.addWidget(self.stop_btn)
        run_row.addSpacing(16)
        run_row.addWidget(self.select_all_btn)
        run_row.addWidget(self.clear_btn)
        run_row.addSpacing(16)
        run_row.addWidget(self.progress_lbl, 1)
        run_w = QWidget(); run_w.setLayout(run_row)

        # --- log area ---
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        f = QFont(); f.setStyleHint(QFont.Monospace); f.setFamily("Consolas")
        self.log.setFont(f)
        self.log.setPlaceholderText("Per-row status appears here.")

        # --- right pane: plot canvas ---
        self.canvas = MplCanvas(self, height=4.5)
        self.toolbar = NavigationToolbar(self.canvas, self)
        self.plot_label = QLabel("Plot — click a row to view its last RamseyVsFF.")
        self.plot_label.setStyleSheet("color: #555;")

        # --- layout ---
        left_v = QVBoxLayout()
        left_v.setContentsMargins(0, 0, 0, 0)
        left_v.addWidget(self.table, 3)
        left_v.addWidget(self.param_form)
        left_v.addWidget(preset_w)
        left_v.addWidget(run_w)
        left_v.addWidget(self.log, 1)
        left_w = QWidget(); left_w.setLayout(left_v)

        right_v = QVBoxLayout()
        right_v.setContentsMargins(0, 0, 0, 0)
        right_v.addWidget(self.plot_label)
        right_v.addWidget(self.toolbar)
        right_v.addWidget(self.canvas, 1)
        right_w = QWidget(); right_w.setLayout(right_v)

        splitter = QSplitter()
        splitter.addWidget(left_w)
        splitter.addWidget(right_w)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        outer = QVBoxLayout(self)
        outer.addWidget(top_w)
        outer.addWidget(splitter, 1)

        # Initial population (combos will be set by refresh_groups_from_state).
        self._update_run_enable()

    def showEvent(self, event):
        # The readout group is owned by AutoCalibTab; refresh our display
        # label every time we become visible so a switch over there is
        # reflected here. Cheap (just a label set).
        super().showEvent(event)
        self._refresh_readout_label()

    # ---- public hooks ----

    def refresh_groups_from_state(self) -> None:
        """Repopulate drive-group combo from state.qubit_parameters_json.

        Filters to drive groups whose ``_recipe.base`` is a string (i.e. the
        recipe-driven calibration tools — ``ramsey_3800+`` etc.); recipe-less
        groups like ``4Q_readout`` are excluded.
        """
        jd = self.state.qubit_parameters_json or {}
        dg = jd.get("drive_groups") or {}
        names: list[str] = []
        for gname, gbody in dg.items():
            if not isinstance(gbody, dict):
                continue
            recipe = gbody.get("_recipe")
            if not isinstance(recipe, dict):
                continue
            base = recipe.get("base")
            if isinstance(base, str) and base:
                names.append(gname)

        prev = self.drive_group_combo.currentData()
        self.drive_group_combo.blockSignals(True)
        self.drive_group_combo.clear()
        self.drive_group_combo.addItem("(none)", "")
        for n in names:
            self.drive_group_combo.addItem(n, n)
        # Try to restore prior selection so refreshes don't reset the user.
        if prev:
            for i in range(self.drive_group_combo.count()):
                if self.drive_group_combo.itemData(i) == prev:
                    self.drive_group_combo.setCurrentIndex(i)
                    break
            else:
                self.drive_group_combo.setCurrentIndex(0)
        else:
            self.drive_group_combo.setCurrentIndex(0)
        self.drive_group_combo.blockSignals(False)
        self._on_drive_group_changed(self.drive_group_combo.currentIndex())

    # ---- selectors / labels ----

    def _on_drive_group_changed(self, _idx: int) -> None:
        self._drive_group_changed = True
        self._refresh_readout_label()
        self._refresh_target_labels()
        self._rebuild_table()
        self._update_run_enable()

    def _refresh_readout_label(self) -> None:
        rg = self.state.current_readout_group or "—"
        self.readout_group_lbl.setText(f"Readout group: {rg}")

    def _refresh_target_labels(self) -> None:
        gname = self.drive_group_combo.currentData() or ""
        if not gname:
            self.target_array_lbl.setText("Target array: —")
            self.target_freq_lbl.setText("Drive frequency: —")
            return
        jd = self.state.qubit_parameters_json or {}
        gbody = (jd.get("drive_groups") or {}).get(gname, {}) or {}
        recipe = gbody.get("_recipe") or {}
        base = recipe.get("base", "?")
        self.target_array_lbl.setText(f"Target array: {base}")

        entries = gbody.get("entries") or {}
        freqs = []
        for ebody in entries.values():
            if isinstance(ebody, dict):
                q = ebody.get("Qubit", {}) or {}
                f = q.get("Frequency")
                if f is not None:
                    freqs.append(f)
        if not freqs:
            self.target_freq_lbl.setText("Drive frequency: —")
            return
        first = freqs[0]
        # Recipe-filtered groups always share the drive frequency; tolerate
        # disagreement with a ⚠ glyph just in case.
        all_same = all(f == first for f in freqs)
        warn = "" if all_same else " (!)"
        try:
            text = f"Drive frequency: {first:g} MHz{warn}"
        except Exception:
            text = f"Drive frequency: {first} MHz{warn}"
        self.target_freq_lbl.setText(text)

    # ---- table rebuild ----

    def _rebuild_table(self) -> None:
        """Rebuild rows from the selected drive group's entries.

        Preserves per-row enabled state, new-FF, status, and cached results
        for row labels that survive the rebuild.
        """
        self._suppress_item_changed = True
        try:
            self._rebuild_table_unguarded()
        finally:
            self._suppress_item_changed = False

    def _rebuild_table_unguarded(self) -> None:
        # Drive-group changes invalidate fit results and hand-edit flags
        # (those belong to a specific calibration session). Selection state
        # survives across groups when the entry name still exists.
        prev_enabled = dict(self._row_enabled)
        prev_new = dict(self._row_new_ff) if not self._drive_group_changed else {}
        prev_status = dict(self._row_status) if not self._drive_group_changed else {}
        prev_results = dict(self._row_results) if not self._drive_group_changed else {}
        if self._drive_group_changed:
            self._row_current_user_edited.clear()
            self._drive_group_changed = False
        # Re-derive from JSON.
        self._row_enabled = {}
        self._row_new_ff = {}
        self._row_status = {}
        self._row_results = {}
        self._row_ro_q = {}

        gname = self.drive_group_combo.currentData() or ""
        jd = self.state.qubit_parameters_json or {}
        gbody = (jd.get("drive_groups") or {}).get(gname, {}) or {}
        entries = list((gbody.get("entries") or {}).keys())
        base_name = (gbody.get("_recipe") or {}).get("base")
        base_arr = (jd.get("base_params") or {}).get(base_name) if base_name else None

        self.table.setRowCount(len(entries))
        for r, ename in enumerate(entries):
            ro_q = _readout_qubit_for_entry(ename)
            self._row_ro_q[ename] = ro_q
            # Restore prior state where the label survives.
            self._row_enabled[ename] = bool(prev_enabled.get(ename, False))
            if ename in prev_new:
                self._row_new_ff[ename] = prev_new[ename]
            if ename in prev_status:
                self._row_status[ename] = prev_status[ename]
            if ename in prev_results:
                self._row_results[ename] = prev_results[ename]

            # Col 0: selection cell. The visible glyph is intentionally
            # minimal — the selection state is communicated by the delegate-
            # painted border (CalibCellDelegate reads SELECTION_ROLE here).
            sel_item = QTableWidgetItem("")
            sel_item.setFlags(Qt.ItemIsEnabled)
            sel_item.setData(SELECTION_ROLE, self._row_enabled[ename])
            self.table.setItem(r, 0, sel_item)

            # Col 1: drive entry.
            it = QTableWidgetItem(ename)
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.table.setItem(r, 1, it)

            # Col 2: ro qubit.
            it = QTableWidgetItem(ro_q)
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            it.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 2, it)

            # Col 3: current FF (editable). Italic+bold when hand-edited
            # (state.qubit_parameters_json[base_name][idx] differs from the
            # on-disk snapshot due to a user keystroke rather than a fit).
            cur = None
            if isinstance(base_arr, list) and ro_q.isdigit():
                idx = int(ro_q) - 1
                if 0 <= idx < len(base_arr):
                    cur = base_arr[idx]
            cur_txt = "" if cur is None else str(cur)
            it = QTableWidgetItem(cur_txt)
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
            it.setTextAlignment(Qt.AlignCenter)
            if ename in self._row_current_user_edited:
                f = it.font(); f.setItalic(True); f.setBold(True); it.setFont(f)
            self.table.setItem(r, 3, it)

            # Col 4: New FF — read-only display of the most recent fit
            # result. Bold while a fit value is held; cleared on re-run.
            new_val = self._row_new_ff.get(ename)
            new_txt = "" if new_val is None else str(int(new_val))
            it = QTableWidgetItem(new_txt)
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            it.setTextAlignment(Qt.AlignCenter)
            if new_val is not None:
                f = it.font(); f.setBold(True); it.setFont(f)
            self.table.setItem(r, 4, it)

            # Col 5: Δ = Current FF − Snapshot (the "save preview" — what
            # this row would write to disk on Save). Independent of fit.
            snap_val = self._snapshot_val_for_row(ename)
            delta_txt = ""
            delta_color = self.COLOR_WHITE
            if cur is not None and snap_val is not None:
                try:
                    delta = int(round(float(cur))) - int(snap_val)
                    delta_txt = f"{delta:+d}"
                    delta_color = self._delta_color(delta)
                except (TypeError, ValueError):
                    pass
            it = QTableWidgetItem(delta_txt)
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            it.setTextAlignment(Qt.AlignCenter)
            it.setBackground(delta_color)
            self.table.setItem(r, 5, it)

            # Col 6: status.
            status = self._row_status.get(ename)
            stxt = ""
            sbg = self.COLOR_WHITE
            if status == "ok":
                stxt = "OK"; sbg = self.COLOR_OK
            elif status == "fail":
                stxt = "FAIL"; sbg = self.COLOR_FAIL
            it = QTableWidgetItem(stxt)
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            it.setTextAlignment(Qt.AlignCenter)
            it.setBackground(sbg)
            self.table.setItem(r, 6, it)

        # Sizing: stretch Drive-entry / Status; narrow checkbox / qubit cols.
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setStretchLastSection(True)

    def _delta_color(self, delta: int) -> QColor:
        a = abs(int(delta))
        if a >= self.DELTA_RED_MIN:
            return self.COLOR_RED
        if a >= self.DELTA_AMBER_MIN:
            return self.COLOR_AMBER
        return self.COLOR_WHITE

    def _current_base_name(self) -> Optional[str]:
        gname = self.drive_group_combo.currentData() or ""
        jd = self.state.qubit_parameters_json or {}
        gbody = (jd.get("drive_groups") or {}).get(gname, {}) or {}
        return (gbody.get("_recipe") or {}).get("base")

    def _snapshot_val_for_row(self, ename: str):
        """Return snapshot.base_params[<base>][idx] for the row's qubit, or None."""
        snap = self.state.qubit_parameters_json_snapshot or {}
        base_name = self._current_base_name()
        if not base_name:
            return None
        snap_arr = (snap.get("base_params") or {}).get(base_name)
        if not isinstance(snap_arr, list):
            return None
        ro_q = self._row_ro_q.get(ename) or _readout_qubit_for_entry(ename)
        if not ro_q.isdigit():
            return None
        idx = int(ro_q) - 1
        if not (0 <= idx < len(snap_arr)):
            return None
        return snap_arr[idx]

    def _refresh_current_ff_column(self) -> None:
        """Re-read base_params[<array>] and rewrite Current FF + Δ for every row.

        Called after a successful row run (and after hand edits) so the
        visible Current FF tracks the in-memory state without rebuilding the
        whole table. Font is left untouched — italic+bold for user-edited
        rows is set by _on_item_changed / cleared by _on_row_done.
        Δ = Current − Snapshot.
        """
        jd = self.state.qubit_parameters_json or {}
        base_name = self._current_base_name()
        base_arr = (jd.get("base_params") or {}).get(base_name) if base_name else None
        if not isinstance(base_arr, list):
            return
        self._suppress_item_changed = True
        try:
            for r in range(self.table.rowCount()):
                ename_item = self.table.item(r, 1)
                if ename_item is None:
                    continue
                ename = ename_item.text()
                ro_q = self._row_ro_q.get(ename, "")
                if not ro_q.isdigit():
                    continue
                idx = int(ro_q) - 1
                if not (0 <= idx < len(base_arr)):
                    continue
                cur = base_arr[idx]
                cur_it = self.table.item(r, 3)
                if cur_it is not None:
                    cur_it.setText(str(cur))
                # Recompute Δ vs snapshot.
                snap_val = self._snapshot_val_for_row(ename)
                d_it = self.table.item(r, 5)
                if d_it is None:
                    continue
                if cur is None or snap_val is None:
                    d_it.setText("")
                    d_it.setBackground(self.COLOR_WHITE)
                    continue
                try:
                    delta = int(round(float(cur))) - int(snap_val)
                    d_it.setText(f"{delta:+d}")
                    d_it.setBackground(self._delta_color(delta))
                except (TypeError, ValueError):
                    d_it.setText("")
                    d_it.setBackground(self.COLOR_WHITE)
        finally:
            self._suppress_item_changed = False

    # ---- selection helpers ----

    def _ename_for_row(self, row: int) -> Optional[str]:
        it = self.table.item(row, 1)
        return it.text() if it is not None else None

    def _set_row_selection(self, row: int, on: bool) -> None:
        """Single source of truth for the selection layer: updates the
        per-row enabled flag AND the col-0 item's SELECTION_ROLE so the
        delegate repaints the border."""
        ename = self._ename_for_row(row)
        if ename is None:
            return
        self._row_enabled[ename] = bool(on)
        sel_item = self.table.item(row, 0)
        if sel_item is not None:
            sel_item.setData(SELECTION_ROLE, bool(on))

    def _on_row_toggled(self, row: int, new_state: bool) -> None:
        self._set_row_selection(row, new_state)
        self._update_run_enable()

    def _on_row_clicked(self, row: int) -> None:
        # Row press also drives the right-pane plot focus (mirrors AutoCalib).
        self._on_row_selected(row)

    def _select_all(self) -> None:
        for r in range(self.table.rowCount()):
            self._set_row_selection(r, True)
        self._update_run_enable()

    def _clear_all(self) -> None:
        for r in range(self.table.rowCount()):
            self._set_row_selection(r, False)
        self._update_run_enable()

    def _base_arr_for_row(self, ename: str):
        """Return (base_arr, idx) for the in-memory base_params slot that
        backs ``ename``, or (None, None) if any link in the chain is missing.
        """
        gname = self.drive_group_combo.currentData() or ""
        jd = self.state.qubit_parameters_json or {}
        gbody = (jd.get("drive_groups") or {}).get(gname, {}) or {}
        base_name = (gbody.get("_recipe") or {}).get("base")
        base_arr = (jd.get("base_params") or {}).get(base_name) if base_name else None
        ro_q = self._row_ro_q.get(ename) or _readout_qubit_for_entry(ename)
        if not (isinstance(base_arr, list) and ro_q.isdigit()):
            return None, None
        idx = int(ro_q) - 1
        if not (0 <= idx < len(base_arr)):
            return None, None
        return base_arr, idx

    def _write_base_arr_slot(self, ename: str, value: int) -> None:
        """Write ``value`` into the live base_params slot for ``ename``."""
        base_arr, idx = self._base_arr_for_row(ename)
        if base_arr is None:
            return
        base_arr[idx] = int(value)
        self._refresh_current_ff_column()

    def _restore_snapshot_slot(self, ename: str) -> None:
        """Revert the live base_params slot for ``ename`` to its on-disk
        snapshot value. Used when the user clears the Current FF cell.
        """
        base_arr, idx = self._base_arr_for_row(ename)
        if base_arr is None:
            return
        snap_val = self._snapshot_val_for_row(ename)
        if snap_val is not None:
            base_arr[idx] = snap_val
            self._refresh_current_ff_column()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        """Handle in-place edit of the Current FF cell (col 3).

        Current FF *is* the sweep center — base_params[<base>][idx] in the
        held JSON. Empty text reverts the slot to its snapshot value (and
        clears the italic+bold marker). Valid int writes through to the
        slot and italic+bold-marks the cell. Invalid text reverts the cell
        text without touching state.
        """
        if self._suppress_item_changed:
            return
        if item.column() != 3:
            return
        r = item.row()
        ename = self._ename_for_row(r)
        if ename is None:
            return
        text = item.text().strip()
        if text == "":
            new_val = None
        else:
            try:
                new_val = int(round(float(text)))
            except ValueError:
                # Revert to whatever's in state — base_arr[idx] is the
                # authoritative source.
                base_arr, idx = self._base_arr_for_row(ename)
                prev = base_arr[idx] if base_arr is not None else None
                self._suppress_item_changed = True
                try:
                    item.setText("" if prev is None else str(prev))
                finally:
                    self._suppress_item_changed = False
                return
        # Commit to the in-memory JSON's base_params slot.
        if new_val is None:
            self._row_current_user_edited.discard(ename)
            self._restore_snapshot_slot(ename)
        else:
            self._row_current_user_edited.add(ename)
            self._write_base_arr_slot(ename, new_val)
        # Italic+bold flag — under signal-suppress so setFont/setText below
        # doesn't re-enter this handler.
        self._suppress_item_changed = True
        try:
            f = item.font()
            edited = ename in self._row_current_user_edited
            f.setItalic(edited); f.setBold(edited)
            item.setFont(f)
        finally:
            self._suppress_item_changed = False

    def _update_run_enable(self) -> None:
        has_drive = bool(self.drive_group_combo.currentData() or "")
        busy = self.worker is not None and self.worker.isRunning()
        any_checked = any(self._row_enabled.values())
        self.run_btn.setEnabled(has_drive and any_checked and not busy)
        self.stop_btn.setEnabled(busy)
        self.select_all_btn.setEnabled(has_drive and not busy)
        self.clear_btn.setEnabled(has_drive and not busy)
        self.drive_group_combo.setEnabled(not busy)

    # ---- preset form filler ----

    def _on_preset_changed(self, _idx: int) -> None:
        name = self.preset_combo.currentData()
        if name not in self.PRESETS:
            return
        window, steps = self.PRESETS[name]
        # Mutate widget values via ParamForm internals.
        w_window = self.param_form.widgets.get("window")
        w_steps = self.param_form.widgets.get("steps")
        if w_window is not None:
            w_window.setValue(int(window))
        if w_steps is not None:
            w_steps.setValue(int(steps))

    # ---- row click -> render plot ----

    def _on_row_selected(self, row: int) -> None:
        if row < 0 or row >= self.table.rowCount():
            return
        ename_item = self.table.item(row, 1)
        if ename_item is None:
            return
        ename = ename_item.text()
        entry = self._row_results.get(ename)
        self.canvas.reset()
        if entry is None:
            self.canvas.ax.text(
                0.5, 0.5, "(no data yet — run this calibration first)",
                ha="center", va="center",
                transform=self.canvas.ax.transAxes, color="#888",
            )
            self.canvas.ax.set_xticks([]); self.canvas.ax.set_yticks([])
            self.canvas.draw()
            self.plot_label.setText(f"Plot — {ename}: (no data)")
            return
        expt, data = entry
        try:
            # RamseyVsFF inherits SweepExperiment2D_plots whose _display_plot
            # signature is (data, fig_axs=(fig, axs)). Render onto our canvas.
            # The parent's _display_plot calls fig.show(), which matplotlib
            # rejects for non-pyplot figures — temporarily neuter it.
            _show = self.canvas.fig.show
            self.canvas.fig.show = lambda *a, **kw: None
            try:
                expt._display_plot(data, fig_axs=(self.canvas.fig, [self.canvas.ax]))
            finally:
                self.canvas.fig.show = _show
        except Exception as exc:
            self.canvas.ax.text(
                0.5, 0.5, f"render failed:\n{exc}",
                ha="center", va="center",
                transform=self.canvas.ax.transAxes,
            )
            traceback.print_exc()
        self.canvas.draw()
        self.plot_label.setText(f"Plot — {ename}")

    # ---- run / stop ----

    def _on_run(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        if not self.state.is_connected():
            QMessageBox.warning(self, "Not connected",
                                "Connect to the RFSoC before running.")
            return
        gname = self.drive_group_combo.currentData() or ""
        if not gname:
            QMessageBox.information(self, "No drive group",
                                    "Select a recipe-driven drive group first.")
            return
        jd = self.state.qubit_parameters_json or {}
        gbody = (jd.get("drive_groups") or {}).get(gname, {}) or {}
        base_name = (gbody.get("_recipe") or {}).get("base")
        if not base_name or base_name not in (jd.get("base_params") or {}):
            QMessageBox.critical(self, "Bad drive group",
                                 f"Drive group {gname!r} has no resolvable _recipe.base.")
            return
        base_arr = jd["base_params"][base_name]
        if not isinstance(base_arr, list):
            QMessageBox.critical(self, "Bad base_params",
                                 f"base_params[{base_name!r}] is not a list.")
            return

        params = self.param_form.values()
        # Snapshot each row's current_value at schedule time so the worker's
        # FF_gain_start/stop bounds don't drift if a prior row mutates the
        # slot before the next row starts.
        schedule: list[dict] = []
        for ename, enabled in self._row_enabled.items():
            if not enabled:
                continue
            ro_q = self._row_ro_q.get(ename) or _readout_qubit_for_entry(ename)
            if not ro_q.isdigit():
                self.log.appendPlainText(
                    f"[skip] {ename}: cannot parse readout qubit index"
                )
                continue
            idx = int(ro_q) - 1
            if not (0 <= idx < len(base_arr)):
                self.log.appendPlainText(
                    f"[skip] {ename}: ro qubit {ro_q} out of bounds for {base_name}"
                )
                continue
            # Sweep center is Current FF == base_arr[idx] in the held JSON.
            # Hand-edits and prior fits both flow through this slot.
            current_value = base_arr[idx]
            if not isinstance(current_value, (int, float)):
                self.log.appendPlainText(
                    f"[skip] {ename}: base_params[{base_name}][{idx}] is "
                    f"non-numeric ({current_value!r})"
                )
                continue
            sweep_params = {
                # Carry-throughs the worker consumes (not forwarded to cfg).
                "__window": int(params["window"]),
                "__steps":  int(params["steps"]),
                # Forwarded to cfg via overrides.
                "expts":         int(params["expts"]),
                "stop_delay_us": float(params["stop_delay_us"]),
                "reps":          int(params["reps"]),
                "relax_delay":   float(params["relax_delay"]),
            }
            schedule.append({
                "row_label":     ename,
                "ro_q":          ro_q,
                "current_value": int(current_value),
                "sweep_params":  sweep_params,
            })
        if not schedule:
            QMessageBox.information(
                self, "Nothing to run",
                "Tick at least one row's checkbox to enable it for the batch."
            )
            return

        # Reset status for queued rows.
        for row in schedule:
            ename = row["row_label"]
            self._row_status[ename] = None
            self._set_row_cell(ename, 6, "queued", self.COLOR_WHITE)
            # Clear stale plot if user re-runs.
            self._row_results.pop(ename, None)

        self.canvas.reset()
        self.plot_label.setText("Plot — running...")
        self.log.clear()
        self.log.appendPlainText(
            f"Running {len(schedule)} row(s) on drive group {gname!r} -> {base_name}."
        )
        self.progress_lbl.setText(f"Running {len(schedule)} row(s)...")
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.drive_group_combo.setEnabled(False)
        self.select_all_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)

        self.worker = LatticePointCalibWorker(self.state, schedule)
        self.worker.progress.connect(self._on_worker_progress)
        self.worker.row_done.connect(self._on_row_done)
        self.worker.row_failed.connect(self._on_row_failed)
        self.worker.log_msg.connect(self.log.appendPlainText)
        self.worker.finished_all.connect(self._on_all_finished)
        self.worker.start()

    def _on_stop(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.log.appendPlainText("[STOP] requested — finishing current row...")
            self.stop_btn.setEnabled(False)

    # ---- worker signal handlers ----

    def _on_worker_progress(self, row_label: str, status: str) -> None:
        self._set_row_cell(row_label, 6, status, self.COLOR_WHITE)
        self.progress_lbl.setText(f"{row_label}: {status}")

    def _on_row_done(self, row_label: str, expt, data, elapsed_s: float) -> None:
        center_gain = data.get("data", {}).get("center_gain") if data else None
        if center_gain is None:
            # Defensive: worker shouldn't emit row_done without center_gain.
            self._on_row_failed(row_label, "row_done with no center_gain", expt, data, elapsed_s)
            return
        new_ff = int(round(float(center_gain)))
        ro_q = self._row_ro_q.get(row_label) or _readout_qubit_for_entry(row_label)
        base_name = self._current_base_name()
        jd = self.state.qubit_parameters_json or {}
        base_arr = (jd.get("base_params") or {}).get(base_name) if base_name else None
        old_val = None
        if isinstance(base_arr, list) and ro_q.isdigit():
            idx = int(ro_q) - 1
            if 0 <= idx < len(base_arr):
                old_val = base_arr[idx]
                base_arr[idx] = new_ff

        # Record in caches. A successful fit clears the hand-edit marker
        # (Current FF font drops italic+bold below) — the cell now reflects
        # a fit, not a user keystroke.
        self._row_new_ff[row_label] = new_ff
        self._row_current_user_edited.discard(row_label)
        self._row_status[row_label] = "ok"
        self._row_results[row_label] = (expt, data)

        # New FF cell: text = fit value, bold.
        self._suppress_item_changed = True
        try:
            new_item = self._set_row_cell(row_label, 4, str(new_ff), None)
            if new_item is not None:
                new_item.setTextAlignment(Qt.AlignCenter)
                f = new_item.font(); f.setBold(True); new_item.setFont(f)
            # Current FF cell: text = fit value, no italic+bold (not hand-edited).
            cur_item = self._set_row_cell(row_label, 3, str(new_ff), None)
            if cur_item is not None:
                cur_item.setTextAlignment(Qt.AlignCenter)
                f = cur_item.font(); f.setItalic(False); f.setBold(False); cur_item.setFont(f)
        finally:
            self._suppress_item_changed = False
        self._set_row_cell(row_label, 6, "OK", self.COLOR_OK)
        # Δ + Current FF column refresh for this row and every other row
        # (a fit can shift the shared base_arr; Δ on other rows is unaffected
        # since they own different slots, but the call is idempotent).
        self._refresh_current_ff_column()

        snap_val = self._snapshot_val_for_row(row_label)
        old_txt = old_val if old_val is not None else "—"
        delta_str = (f"Δ {new_ff - int(snap_val):+d} (vs disk)"
                     if isinstance(snap_val, (int, float)) else "")
        self.log.appendPlainText(
            f"[OK]   ({elapsed_s:5.1f} s)  {row_label}  "
            f"{base_name}[{int(ro_q) - 1 if ro_q.isdigit() else '?'}]: "
            f"{old_txt} -> {new_ff}  {delta_str}"
        )
        # Notify the params tab so the tree refreshes.
        try:
            self.get_main().refresh_qubit_summary()
        except Exception:
            pass

    def _on_row_failed(self, row_label: str, err: str, expt, data, elapsed_s: float) -> None:
        self._row_status[row_label] = "fail"
        if expt is not None and data is not None:
            self._row_results[row_label] = (expt, data)
        self._set_row_cell(row_label, 6, "FAIL", self.COLOR_FAIL)
        first, _, rest = err.partition("\n")
        self.log.appendPlainText(
            f"[FAIL] ({elapsed_s:5.1f} s)  {row_label}  {first}"
        )
        for line in rest.rstrip().splitlines():
            self.log.appendPlainText(f"       {line}")

    def _on_all_finished(self) -> None:
        self.progress_lbl.setText("Done.")
        self.worker = None
        self._update_run_enable()
        # Re-enable controls that were locked during the run.
        self.drive_group_combo.setEnabled(True)
        self.select_all_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)

    # ---- helpers ----

    def _row_index_for(self, row_label: str) -> Optional[int]:
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 1)
            if it is not None and it.text() == row_label:
                return r
        return None

    def _set_row_cell(self, row_label: str, col: int, text: str,
                      bg: Optional[QColor]) -> Optional[QTableWidgetItem]:
        r = self._row_index_for(row_label)
        if r is None:
            return None
        it = self.table.item(r, col)
        if it is None:
            it = QTableWidgetItem(text)
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            it.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, col, it)
        else:
            it.setText(text)
        if bg is not None:
            it.setBackground(bg)
        return it


# ---------------------------------------------------------------------------
# ResultsDialog — 2x3 grid of stage plots for a single qubit
# ---------------------------------------------------------------------------


class ResultsDialog(QDialog):
    """Pop-up showing the six standard calibration plots (Trans, Spec, Rabi,
    SingleShot, T1, T2R) for one qubit, in a 2x3 grid.

    Each cell is its own ``MplCanvas`` so the matplotlib navigation toolbar
    works per panel and the original ``expt.display(ax=...)`` (or the bespoke
    SingleShot scatter) renders directly into the canvas. Stages without
    data show a "no data" placeholder.
    """

    POSITIONS = [
        ("Transmission",  0, 0),
        ("QubitSpec",     0, 1),
        ("AmplitudeRabi", 0, 2),
        ("ReadoutOpt",    0, 3),
        ("PulseOpt",      1, 0),
        ("SingleShot",    1, 1),
        ("T1",            1, 2),
        ("T2R",           1, 3),
    ]

    def __init__(self, qubit_id, results_for_q: dict, stages_by_name: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Q{qubit_id} - calibration results")
        self.resize(1500, 850)

        grid = QGridLayout()
        grid.setSpacing(8)
        for stage_name, r, c in self.POSITIONS:
            box = QGroupBox(stage_name)
            v = QVBoxLayout(box)
            canvas = MplCanvas(box, height=3.0)
            tb = NavigationToolbar(canvas, box)
            v.addWidget(tb)
            v.addWidget(canvas, 1)

            entry = results_for_q.get(stage_name)
            if entry is None:
                canvas.ax.text(
                    0.5, 0.5, "(no data)",
                    ha="center", va="center", transform=canvas.ax.transAxes,
                    color="#888",
                )
                canvas.ax.set_xticks([]); canvas.ax.set_yticks([])
            else:
                expt, data = entry
                stage = stages_by_name.get(stage_name)
                if stage is None:
                    canvas.ax.text(
                        0.5, 0.5, "(stage tab missing)",
                        ha="center", va="center", transform=canvas.ax.transAxes,
                    )
                else:
                    try:
                        # qubit_id may be a drive-entry name like '1_3800+';
                        # parse leading digits for the integer readout id.
                        ro_q = _readout_qubit_for_entry(qubit_id)
                        qid = int(ro_q) if ro_q.isdigit() else None
                        stage.render_into(
                            canvas.ax, expt, data, qubit_id=qid
                        )
                    except Exception as exc:
                        canvas.ax.clear()
                        canvas.ax.text(
                            0.5, 0.5, f"render failed:\n{exc}",
                            ha="center", va="center",
                            transform=canvas.ax.transAxes,
                        )
                        traceback.print_exc()
            canvas.draw()
            grid.addWidget(box, r, c)

        layout = QVBoxLayout(self)
        layout.addLayout(grid, 1)
        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)


# ---------------------------------------------------------------------------
# Qblox D5a coupler-bias loader, worker, and dialog
# ---------------------------------------------------------------------------


def load_d5a_voltages_from_file(path: str) -> dict[str, float]:
    """Return a {label: volts} dict loaded from a .py or .json setpoint file.

    Accepted formats:
      - .json containing either {"voltages": {...}} or a flat dict.
      - .py defining a top-level dict variable whose values are all numbers.
        Dict variables containing "voltage" in the name are preferred.
    The .py path stubs the SPIRack/D5aModule imports so the file can be
    parsed without touching hardware.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    if p.suffix.lower() == ".json":
        with open(p, "r") as fh:
            d = json.load(fh)
        if isinstance(d, dict) and "voltages" in d and isinstance(d["voltages"], dict):
            d = d["voltages"]
        if not isinstance(d, dict):
            raise ValueError(f"{p} JSON is not a dict")
        return {str(k): float(v) for k, v in d.items()}

    # .py path — stub the SPIRack drivers so import is harmless.
    import runpy
    import sys
    import types

    class _StubD5a:
        range_4V_uni = 0
        range_4V_bi = 2
        range_2V_bi = 4
        _num_dacs = 16
        def __init__(self, *a, **kw): pass
        def get_settings(self, dac): return (0.0, self.range_4V_bi)
        def change_span(self, dac, span): pass
        def change_span_update(self, dac, span): pass
        def set_voltage(self, dac, v): pass
        def set_voltage_ramp(self, dac, v): pass

    class _StubSPIRack:
        def __init__(self, *a, **kw): pass
        def close(self): pass
        def unlock(self): pass

    targets = [
        "WorkingProjects.triangle_lattice_quench.PythonDrivers.SPIRackvoltage",
        "WorkingProjects.triangle_lattice_quench.Client_modules.PythonDrivers.SPIRackvoltage",
    ]
    saved = {t: sys.modules.get(t) for t in targets}
    fake = types.ModuleType("spirack_stub")
    fake.SPIRack = _StubSPIRack
    fake.D5aModule = _StubD5a
    for t in targets:
        sys.modules[t] = fake
    try:
        ns = runpy.run_path(str(p), run_name="<gui-load-d5a>")
    finally:
        for t, mod in saved.items():
            if mod is None:
                sys.modules.pop(t, None)
            else:
                sys.modules[t] = mod

    candidates: list[tuple[str, dict]] = []
    for name, val in ns.items():
        if name.startswith("_"):
            continue
        if isinstance(val, dict) and val and \
                all(isinstance(v, (int, float)) for v in val.values()):
            candidates.append((name, val))
    if not candidates:
        raise ValueError(
            f"No voltage dictionary found in {p}. "
            "Expected a top-level dict whose values are numbers."
        )
    candidates.sort(key=lambda nv: 0 if "voltage" in nv[0].lower() else 1)
    chosen = candidates[0][1]
    return {str(k): float(v) for k, v in chosen.items()}


class D5aApplyWorker(QThread):
    """Open the SPI rack, ramp every configured channel to its target voltage,
    set unused channels to 0 (optional), then close the connection.

    All hardware access is on the worker thread so the GUI stays responsive.
    """

    log = pyqtSignal(str)
    finished_ok = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, port: str, baud: int, timeout: float, module: int,
                 voltages_by_dac: dict[int, float], set_unused_to_zero: bool):
        super().__init__()
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self.module = module
        self.voltages_by_dac = dict(voltages_by_dac)
        self.set_unused_to_zero = set_unused_to_zero

    def run(self):
        spi = None
        try:
            self.log.emit(f"Opening SPI rack on {self.port} (module={self.module})...")
            from WorkingProjects.triangle_lattice_quench.PythonDrivers.SPIRackvoltage import (
                SPIRack, D5aModule,
            )
            spi = SPIRack(self.port, self.baud, self.timeout)
            d5a = D5aModule(
                spi, module=self.module, reset_voltages=False,
                ramp_step=DEFAULT_D5A_RAMP_STEP,
                ramp_interval=DEFAULT_D5A_RAMP_INTERVAL,
            )

            # Make sure every DAC is on the bipolar 4 V span.
            span = d5a.range_4V_bi
            for i in range(d5a._num_dacs):
                if d5a.get_settings(i)[1] != span:
                    cur = d5a.get_settings(i)[0]
                    d5a.change_span(i, span)
                    d5a.set_voltage(i, cur)

            # Apply target voltages with ramp.
            for dac in sorted(self.voltages_by_dac):
                v = float(self.voltages_by_dac[dac])
                self.log.emit(f"DAC {dac:2d} -> {v:+.4f} V")
                d5a.set_voltage_ramp(int(dac), v)

            if self.set_unused_to_zero:
                used = set(int(d) for d in self.voltages_by_dac)
                for i in range(d5a._num_dacs):
                    if i not in used:
                        d5a.set_voltage(i, 0.0)
                self.log.emit("Unused DACs zeroed.")

            # Read back final voltages for the log.
            self.log.emit("Final readback:")
            for i in range(d5a._num_dacs):
                self.log.emit(f"  DAC {i:2d}: {d5a.get_settings(i)[0]:+.4f} V")

            self.finished_ok.emit()
        except Exception as exc:
            self.failed.emit(f"{exc}\n\n{traceback.format_exc()}")
        finally:
            if spi is not None:
                try:
                    spi.close()
                except Exception:
                    pass


class D5aCouplerDialog(QDialog):
    """Edit + apply Qblox D5a coupler-bias voltages.

    Two-column form for connection params (port / module / etc.), an editable
    table of (label, DAC, target voltage), Load / Save / Apply buttons, and a
    log pane showing the worker's progress.
    """

    def __init__(self, state: CalibState, parent=None):
        super().__init__(parent)
        self.state = state
        self.worker: Optional[D5aApplyWorker] = None
        self.setWindowTitle("Qblox D5a coupler bias")
        self.resize(720, 720)

        # ---- connection params ----
        conn_box = QGroupBox("SPI rack connection")
        conn_form = QFormLayout(conn_box)
        self.port_edit = QLineEdit(state.d5a_port or DEFAULT_D5A_PORT)
        self.module_spin = QSpinBox(); self.module_spin.setRange(0, 31)
        self.module_spin.setValue(state.d5a_module or DEFAULT_D5A_MODULE)
        self.baud_spin = QSpinBox(); self.baud_spin.setRange(9600, 10_000_000)
        self.baud_spin.setValue(DEFAULT_D5A_BAUD)
        self.timeout_spin = QDoubleSpinBox(); self.timeout_spin.setRange(0.05, 30.0)
        self.timeout_spin.setDecimals(2); self.timeout_spin.setValue(DEFAULT_D5A_TIMEOUT)
        self.zero_unused_check = QCheckBox("Set unused DACs to 0 V on apply")
        self.zero_unused_check.setChecked(True)
        conn_form.addRow("COM port:", self.port_edit)
        conn_form.addRow("Module index:", self.module_spin)
        conn_form.addRow("Baud:", self.baud_spin)
        conn_form.addRow("Timeout (s):", self.timeout_spin)
        conn_form.addRow(self.zero_unused_check)

        # ---- voltage table ----
        table_box = QGroupBox("Channel voltages (span = 4V_bi, +/-4 V)")
        table_layout = QVBoxLayout(table_box)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Label", "DAC", "Target voltage (V)"])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.verticalHeader().setVisible(False)
        table_layout.addWidget(self.table, 1)

        # ---- buttons ----
        btn_row = QHBoxLayout()
        self.load_btn = QPushButton("Load voltages...")
        self.load_btn.clicked.connect(self.on_load)
        self.save_btn = QPushButton("Save voltages...")
        self.save_btn.clicked.connect(self.on_save)
        self.reload_default_btn = QPushButton("Reload default")
        self.reload_default_btn.setToolTip(
            "Reload voltages from the project default file "
            f"({DEFAULT_D5A_VOLTAGES_FILE.name})."
        )
        self.reload_default_btn.clicked.connect(self.on_reload_default)
        self.apply_btn = QPushButton("Apply (ramp to targets)")
        self.apply_btn.setStyleSheet("font-weight: bold;")
        self.apply_btn.clicked.connect(self.on_apply)
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        btn_row.addWidget(self.load_btn)
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(self.reload_default_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.apply_btn)
        btn_row.addWidget(self.close_btn)
        btn_widget = QWidget(); btn_widget.setLayout(btn_row)

        # ---- log ----
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        f = QFont(); f.setStyleHint(QFont.Monospace); f.setFamily("Consolas")
        self.log.setFont(f)
        self.log.setPlaceholderText("Apply progress will appear here.")

        layout = QVBoxLayout(self)
        layout.addWidget(conn_box)
        layout.addWidget(table_box, 2)
        layout.addWidget(btn_widget)
        layout.addWidget(self.log, 1)

        # populate from state (or default file if state is empty).
        if not self.state.d5a_voltages:
            self._try_load_default_silently()
        self._populate_table()

    # ---- helpers ----

    def _try_load_default_silently(self):
        try:
            volts = load_d5a_voltages_from_file(str(DEFAULT_D5A_VOLTAGES_FILE))
            self.state.d5a_voltages = volts
            self.state.d5a_voltages_path = str(DEFAULT_D5A_VOLTAGES_FILE)
        except Exception as exc:
            self.log.appendPlainText(f"[default load failed] {exc}")

    def _populate_table(self):
        labels = sorted(
            self.state.d5a_dac_map.keys(),
            key=lambda lbl: self.state.d5a_dac_map.get(lbl, 1 << 30),
        )
        self.table.setRowCount(len(labels))
        for r, lbl in enumerate(labels):
            label_item = QTableWidgetItem(lbl)
            label_item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(r, 0, label_item)
            dac_item = QTableWidgetItem(str(self.state.d5a_dac_map[lbl]))
            dac_item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(r, 1, dac_item)
            v = self.state.d5a_voltages.get(lbl, 0.0)
            v_item = QTableWidgetItem(f"{float(v):+.4f}")
            self.table.setItem(r, 2, v_item)
        self.table.resizeColumnsToContents()

    def _read_table_into_state(self) -> None:
        """Read every editable cell into self.state.d5a_voltages, raising on bad input."""
        new_volts: dict[str, float] = {}
        for r in range(self.table.rowCount()):
            lbl = self.table.item(r, 0).text()
            txt = self.table.item(r, 2).text().strip()
            if txt == "":
                continue
            try:
                v = float(txt)
            except ValueError:
                raise ValueError(f"Row {r+1} ({lbl}): cannot parse {txt!r} as a float.")
            if abs(v) > 4.0 + 1e-6:
                raise ValueError(
                    f"Row {r+1} ({lbl}): {v:+.4f} V is outside the +/-4 V span."
                )
            new_volts[lbl] = v
        self.state.d5a_voltages = new_volts

    def _voltages_by_dac(self) -> dict[int, float]:
        return {
            int(self.state.d5a_dac_map[lbl]): float(v)
            for lbl, v in self.state.d5a_voltages.items()
            if lbl in self.state.d5a_dac_map
        }

    # ---- handlers ----

    def on_load(self):
        start_dir = ""
        if self.state.d5a_voltages_path and Path(self.state.d5a_voltages_path).exists():
            start_dir = str(Path(self.state.d5a_voltages_path).parent)
        elif DEFAULT_D5A_VOLTAGES_FILE.parent.exists():
            start_dir = str(DEFAULT_D5A_VOLTAGES_FILE.parent)
        path, _ = QFileDialog.getOpenFileName(
            self, "Load D5a voltages", start_dir, "Python or JSON (*.py *.json)"
        )
        if not path:
            return
        try:
            volts = load_d5a_voltages_from_file(path)
        except Exception as exc:
            QMessageBox.critical(self, "Load failed", f"{exc}")
            return
        self.state.d5a_voltages = volts
        self.state.d5a_voltages_path = path
        self._populate_table()
        self.log.appendPlainText(f"Loaded {len(volts)} voltages from {path}")

    def on_reload_default(self):
        try:
            volts = load_d5a_voltages_from_file(str(DEFAULT_D5A_VOLTAGES_FILE))
        except Exception as exc:
            QMessageBox.critical(self, "Default load failed", f"{exc}")
            return
        self.state.d5a_voltages = volts
        self.state.d5a_voltages_path = str(DEFAULT_D5A_VOLTAGES_FILE)
        self._populate_table()
        self.log.appendPlainText(f"Loaded default ({DEFAULT_D5A_VOLTAGES_FILE.name})")

    def on_save(self):
        try:
            self._read_table_into_state()
        except Exception as exc:
            QMessageBox.warning(self, "Invalid value", str(exc))
            return
        start_path = ""
        if self.state.d5a_voltages_path:
            stem = Path(self.state.d5a_voltages_path).stem
            start_path = str(Path(self.state.d5a_voltages_path).with_name(f"{stem}.json"))
        path, _ = QFileDialog.getSaveFileName(
            self, "Save D5a voltages", start_path or "d5a_voltages.json",
            "JSON (*.json)"
        )
        if not path:
            return
        payload = {"voltages": self.state.d5a_voltages,
                   "dac_map": self.state.d5a_dac_map}
        try:
            with open(path, "w") as fh:
                dump_pretty(payload, fh)
            self.log.appendPlainText(f"Saved to {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

    def on_apply(self):
        if self.worker is not None and self.worker.isRunning():
            return
        try:
            self._read_table_into_state()
        except Exception as exc:
            QMessageBox.warning(self, "Invalid value", str(exc))
            return
        self.state.d5a_port = self.port_edit.text().strip() or DEFAULT_D5A_PORT
        self.state.d5a_module = int(self.module_spin.value())
        baud = int(self.baud_spin.value())
        timeout = float(self.timeout_spin.value())
        zero_unused = self.zero_unused_check.isChecked()
        v_by_dac = self._voltages_by_dac()
        if not v_by_dac:
            QMessageBox.warning(self, "Empty voltage list",
                                "No DACs to apply. Load or enter voltages first.")
            return
        self.apply_btn.setEnabled(False)
        self.load_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        self.reload_default_btn.setEnabled(False)
        self.log.appendPlainText("--- Apply started ---")
        self.worker = D5aApplyWorker(
            port=self.state.d5a_port, baud=baud, timeout=timeout,
            module=self.state.d5a_module,
            voltages_by_dac=v_by_dac, set_unused_to_zero=zero_unused,
        )
        self.worker.log.connect(self.log.appendPlainText)
        self.worker.finished_ok.connect(self._on_finished_ok)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_finished_ok(self):
        from datetime import datetime
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.state.d5a_last_applied_at = ts
        set_d5a_settings(
            voltages_path=self.state.d5a_voltages_path,
            port=self.state.d5a_port,
            module=self.state.d5a_module,
            last_applied_at=ts,
        )
        self.log.appendPlainText(f"--- Apply OK at {ts} ---")
        self._reenable_buttons()
        # Tell the parent main window so the toolbar status updates.
        parent = self.parent()
        if parent is not None and hasattr(parent, "_refresh_d5a_status"):
            try:
                parent._refresh_d5a_status()
            except Exception:
                pass

    def _on_failed(self, msg: str):
        QMessageBox.critical(self, "D5a apply failed", msg)
        self.log.appendPlainText("--- Apply FAILED ---")
        self._reenable_buttons()

    def _reenable_buttons(self):
        self.apply_btn.setEnabled(True)
        self.load_btn.setEnabled(True)
        self.save_btn.setEnabled(True)
        self.reload_default_btn.setEnabled(True)
        self.worker = None


# ---------------------------------------------------------------------------
# Experiment library — discovery, recipe runner, browse-and-run tab
# ---------------------------------------------------------------------------


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


def _make_jsonable(d):
    """Convert numpy scalars/arrays and unknown types to JSON-friendly forms."""
    import numpy as np
    if isinstance(d, dict):
        return {k: _make_jsonable(v) for k, v in d.items()}
    if isinstance(d, (list, tuple)):
        return [_make_jsonable(v) for v in d]
    if isinstance(d, np.ndarray):
        return d.tolist()
    if isinstance(d, (np.integer,)):
        return int(d)
    if isinstance(d, (np.floating,)):
        return float(d)
    if d is None or isinstance(d, (str, int, float, bool)):
        return d
    return str(d)


# Matches a JSON list whose elements are all scalar literals (number, string,
# true/false/null) split across lines by json.dumps(indent=...). Used to
# collapse e.g. FF_Gains arrays back onto a single line for readability.
_SCALAR_ARRAY_RE = re.compile(
    r'\[\s*\n\s*'
    r'(?:-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|"[^"\n]*"|true|false|null)'
    r'(?:\s*,\s*\n\s*'
    r'(?:-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|"[^"\n]*"|true|false|null))*'
    r'\s*\n\s*\]'
)


def _collapse_scalar_arrays(text: str) -> str:
    def _repl(m):
        inner = m.group(0)[1:-1]
        parts = [p.strip() for p in inner.split(',')]
        return '[' + ', '.join(parts) + ']'
    return _SCALAR_ARRAY_RE.sub(_repl, text)


def dumps_pretty(obj, indent: int = 2) -> str:
    """json.dumps but collapses scalar-only arrays onto one line."""
    return _collapse_scalar_arrays(json.dumps(_make_jsonable(obj), indent=indent))


def dump_pretty(obj, fp, indent: int = 2) -> None:
    """json.dump but collapses scalar-only arrays onto one line."""
    fp.write(dumps_pretty(obj, indent=indent))


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


class Pi2PhaseWorker(QThread):
    """Run one of the ``mSweeppi2Phase`` classes on a worker thread.

    ``class_name`` selects between ``SweepPi2Phase`` (variant A, bare two-pi/2),
    ``MottQuenchPi2Phase`` (variant B 1D, Mott seq @ fixed expt_samples), and
    ``MottQuenchPi2Phase2D`` (variant B 2D, phase x dynamics-time). Same
    sandbox-import + display-neuter pattern as ``TwoQubitChevronWorker``.
    """

    log = pyqtSignal(str)
    finished_ok = pyqtSignal(object, object)  # expt, data
    failed = pyqtSignal(str)

    def __init__(self, soc, soccfg, outer_folder: str, cfg: dict,
                 class_name: str, file_path: Optional[str] = None):
        super().__init__()
        self.soc = soc
        self.soccfg = soccfg
        self.outer_folder = outer_folder
        self.cfg = cfg
        self.class_name = str(class_name)
        # Default = the mSweeppi2Phase variants; FF Ramsey passes the FFRamseyCal path.
        self.file_path = file_path

    def run(self):
        try:
            file_path = self.file_path or str(
                EXPERIMENTAL_SCRIPTS_DIR / "quench_experiments" / "mSweeppi2Phase.py"
            )
            self.log.emit(f"Importing {self.class_name}...")
            cls = import_experiment_class(
                file_path, self.class_name,
                soc=self.soc, soccfg=self.soccfg,
            )

            # Same SweepExperimentND.acquire() paren-bug workaround as
            # TwoQubitChevronWorker — the bug lives on the shared ND base,
            # so all three variants (1D + 2D) need the display-neuter.
            from matplotlib.figure import Figure as _BareFigure
            from matplotlib.backends.backend_agg import FigureCanvasAgg

            class _Pi2PhaseForGui(cls):
                def display(self, data=None, plotDisp=False, figNum=1,
                            plotSave=True, block=False, fig_axs=None):
                    fig = _BareFigure()
                    FigureCanvasAgg(fig)  # attach Agg canvas; no Qt involvement
                    ax = fig.add_subplot(111)
                    return fig, [ax]

                def _update_fig(self, data, fig, axs):
                    pass  # no-op; we render after acquire on the GUI canvas

            self.log.emit("Constructing experiment...")
            expt = _Pi2PhaseForGui(
                soc=self.soc, soccfg=self.soccfg,
                path=self.class_name,
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


def _agent_set_combo(combo, val) -> bool:
    """Select a combo item by its data, then by str(data), then by text ('Q<val>'
    or '<val>'). Lets the Measurement Agent address controls by chip number even
    when the combo's data is a position. Returns True if a matching item was set."""
    i = combo.findData(val)
    if i < 0:
        i = combo.findData(str(val))
    if i < 0:
        for k in range(combo.count()):
            t = combo.itemText(k)
            if t == f"Q{val}" or t == str(val):
                i = k
                break
    if i >= 0:
        combo.setCurrentIndex(i)
    return i >= 0


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


class Pi2PhaseCalibTab(QWidget):
    """Run the three ``mSweeppi2Phase`` variants under one tab.

    Variant A (``SweepPi2Phase``): bare two pi/2 pulses; sweep the phase of
    the second on ``swept_qubit``. 1D fit -> ``fit_beamsplitter_offset``.

    Variant B 1D (``MottQuenchPi2Phase``): full Mott-quench sequence; sweep
    the measurement pi/2 phase of ``swept_qubit`` at fixed ``expt_samples``.

    Variant B 2D (``MottQuenchPi2Phase2D``): full Mott-quench sequence;
    measurement pi/2 phase of ``swept_qubit`` x dynamics-time samples.

    Multi-qubit cfg is rebuilt directly via ``build_config`` (single-qubit
    ``build_cfg_for_qubit`` is the cfg seed used to look up the SingleShot
    cals; the readout/pulse qubit sets come from the readout-group entries,
    mirroring ``mott_quench_basic.py``). For variants B, Ramp_State /
    Dynamics_Point combos are required so ``Gain_Pulse`` / ``Gain_Expt`` /
    ``Gain_Dynamics`` are populated; variant A leaves them empty.
    """

    name = "Pi/2 Phase Calib"

    # Variant keys — used as both stack id and worker class_name.
    VAR_A = "SweepPi2Phase"
    VAR_B1D = "MottQuenchPi2Phase"
    VAR_B2D = "MottQuenchPi2Phase2D"
    # Constant IS the worker class_name (same convention as the others), so
    # _on_run's class_name=variant dispatch needs no separate map. The dropdown
    # DISPLAY text is set in addItem; this value is what currentData() returns.
    VAR_GFCAL = "MottQuenchPi2GainFreqCal"
    # Single-qubit T2 (Ramsey) at the Expt_FF operating flux. Non-standard variant:
    # its own cfg builder / finish handler / render (FFRamseyCal, not a SweepExperimentND).
    VAR_FFRAMSEY = "FFRamseyCal"
    NONE_LABEL = "(none)"

    def __init__(self, state: CalibState, get_main, parent=None):
        super().__init__(parent)
        self.state = state
        self.get_main = get_main
        self.worker: Optional[Pi2PhaseWorker] = None
        # In-situ 2nd-pi/2 gain×freq calibration runs the MottQuenchPi2GainFreqCal
        # variant through a Pi2PhaseWorker (same sweep-engine path as the main Run button).
        self._spec_worker: Optional[Pi2PhaseWorker] = None
        self._last_data: Any = None
        self._last_expt: Any = None
        self._last_class: Optional[str] = None
        self._last_swept_qubit: Optional[int] = None

        # ---- readout/drive group selectors (mirror TwoQubitCalibTab) ----
        self.readout_group_combo = QComboBox()
        self.readout_group_combo.setMinimumWidth(160)
        self.readout_group_combo.setToolTip(
            "Readout point for the pi/2-phase sweep "
            "(sets state.current_readout_group)."
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
        # Ramp_State / Dynamics_Point entry combos (variants B only — the
        # Mott sequence needs Gain_Pulse / Gain_Expt / Gain_Dynamics resolved
        # via build_config, which is what these select).
        self.ramp_state_combo = QComboBox()
        self.ramp_state_combo.setMinimumWidth(160)
        self.ramp_state_combo.setToolTip(
            "Ramp_State entry (any entry in any ramp_groups). "
            "Required for the Mott-quench variants."
        )
        self.dynamics_point_combo = QComboBox()
        self.dynamics_point_combo.setMinimumWidth(160)
        self.dynamics_point_combo.setToolTip(
            "Dynamics_Point entry (any entry in any dynamics_groups). "
            "Required for the Mott-quench variants."
        )
        # Opt-in (variants B only): fire the 2nd (measurement) pi/2 while parked at the
        # swapped-frequency dynamics point (FFBS) rather than after jumping back to Pulse_FF.
        # Needs a Dynamics_Point with swapped FF gains selected to do anything physical.
        self.second_pulse_dyn_check = QCheckBox("2nd π/2 at dynamics point (swapped freq)")
        self.second_pulse_dyn_check.setChecked(False)
        self.second_pulse_dyn_check.setToolTip(
            "Variant B only. Play the measurement pi/2 at the swapped-frequency dynamics "
            "point (FFBS / Dynamics_Point) driven at the seed qubit's frequency, instead of "
            "jumping back to Pulse_FF. Select a Dynamics_Point with swapped FF gains for the "
            "swap to take effect."
        )
        # Gain×Freq Cal target: when checked, the cal writes its measured gain to the INIT pi/2
        # slot (pi2_init_gain_abs) instead of the measurement slot (meas_pi2_gain_abs), and leaves
        # meas_pi2_freq untouched (both pulses share one frequency). Run the cal with the INIT
        # qubit as the swept qubit to calibrate the first pi/2 -- no manual gain entry needed.
        self.gfcal_init_check = QCheckBox("Gain×Freq Cal → init π/2 gain")
        self.gfcal_init_check.setChecked(False)
        self.gfcal_init_check.setToolTip(
            "Gain×Freq Cal only. When checked, the cal writes its measured gain into the INIT "
            "pi/2 slot (pi2_init_gain) instead of the measurement pi/2 slot, and does NOT change "
            "meas_pi2_freq. Set the swept qubit to the INIT qubit, run the cal, and the first "
            "pi/2 gain is stored automatically."
        )
        # Generate a swapped-frequency dynamics point from the current Pulse_FF
        # via the existing forward (ff_gains_to_freqs) / inverse (CalculateFF)
        # pipeline. Writes a new dynamics_groups entry and selects it. Variant-B
        # only (same gate as second_pulse_dyn_check) — the swap is meaningless
        # for the bare variant A.
        self.swap_dyn_btn = QPushButton("Swap two qubits → dynamics point")
        self.swap_dyn_btn.setToolTip(
            "Forward-map the selected config's Pulse_FF to 8 dressed freqs, "
            "exchange the seed/swept qubit frequencies, inverse-map the full "
            "8-vector (CalculateFF, compensating crosstalk on the others), and "
            "write the result as a new dynamics_groups entry 'swap_<seed>_<swept>'. "
            "Review the gains/freqs in the log + FF table, then Save. "
            "Does NOT run anything on hardware."
        )
        self.swap_dyn_btn.clicked.connect(self._on_swap_two_qubits)
        # NOTE: the in-situ 2nd-pi/2 gain×freq calibration that used to live on a
        # dedicated "Calibrate 2nd π/2 freq" button here is now the VAR_GFCAL variant
        # in the variant dropdown (its parameters are editable in param_form_gfcal,
        # and it runs through the normal Run button via Pi2PhaseWorker like every
        # other variant).
        group_row = QHBoxLayout()
        group_row.addWidget(QLabel("Readout group:"))
        group_row.addWidget(self.readout_group_combo)
        group_row.addSpacing(12)
        group_row.addWidget(QLabel("Drive group:"))
        group_row.addWidget(self.drive_group_combo)
        group_row.addSpacing(12)
        group_row.addWidget(QLabel("Ramp_State:"))
        group_row.addWidget(self.ramp_state_combo)
        group_row.addSpacing(12)
        group_row.addWidget(QLabel("Dynamics_Point:"))
        group_row.addWidget(self.dynamics_point_combo)
        group_row.addSpacing(8)
        group_row.addWidget(self.swap_dyn_btn)
        group_row.addSpacing(12)
        group_row.addWidget(self.second_pulse_dyn_check)
        group_row.addSpacing(12)
        group_row.addWidget(self.gfcal_init_check)
        group_row.addStretch(1)
        group_w = QWidget(); group_w.setLayout(group_row)

        # ---- variant selector ----
        var_box = QGroupBox("Variant")
        var_layout = QVBoxLayout(var_box)
        self.variant_combo = QComboBox()
        self.variant_combo.addItem(
            "SweepPi2Phase (bare two-pi/2, 1D)", self.VAR_A,
        )
        self.variant_combo.addItem(
            "MottQuenchPi2Phase (Mott seq, 1D)", self.VAR_B1D,
        )
        self.variant_combo.addItem(
            "MottQuenchPi2Phase2D (Mott seq, 2D)", self.VAR_B2D,
        )
        self.variant_combo.addItem(
            "2nd π/2 Gain×Freq Cal (in-situ, 2D)", self.VAR_GFCAL,
        )
        self.variant_combo.addItem(
            "FF Ramsey T2 (at Expt_FF, 1D)", self.VAR_FFRAMSEY,
        )
        self.variant_combo.currentIndexChanged.connect(self._on_variant_changed)
        var_layout.addWidget(self.variant_combo)

        # ---- qubit selector group ----
        qubit_box = QGroupBox("Qubit selection")
        qubit_form = QFormLayout(qubit_box)
        self.pi2_init_combo = QComboBox()
        self.pi2_init_combo.setToolTip(
            "pi2_init_index is 0-based into Qubit_Pulse (the qubit prepared in "
            "the superposition state for the Mott quench)."
        )
        self.swept_qubit_combo = QComboBox()
        self.swept_qubit_combo.setToolTip(
            "swept_qubit is 1-based POSITION into Qubit_Pulse. Index-convention "
            "mismatch w/ pi2_init_index (0-based) is intentional; see the source "
            "in mSweeppi2Phase.py."
        )
        self.link_check = QCheckBox("Link swept_qubit = pi2_init_index + 1")
        self.link_check.setChecked(True)
        self.link_check.setToolTip(
            "When checked, swept_qubit follows pi2_init_index+1 automatically."
        )
        self.pi2_init_combo.currentIndexChanged.connect(self._on_pi2_init_changed)
        self.link_check.toggled.connect(self._on_link_toggled)
        qubit_form.addRow("pi2_init_index (0-based):", self.pi2_init_combo)
        qubit_form.addRow("Swept qubit (0-based):", self.swept_qubit_combo)
        qubit_form.addRow(self.link_check)

        # ---- sweep params (three sibling ParamForms; toggle visibility) ----
        # Common keys (reps, phase_*) live on every form so the read-back path
        # in _on_run is just self._current_param_form().values() — no row-by-
        # row visibility juggling on a single QFormLayout.
        # qubit_gains_matrix defaults to qubit_gains/2 from the JSON inside SweepPi2Phase.init_sweep_vars,
        # so the form no longer exposes it — same convention as mMottQuench and the other calibrations.
        self.param_form_a = ParamForm("Sweep parameters (variant A)", [
            ("reps",               "Repetitions",                "int",   500),
            ("phase_start",        "Phase start (deg)",          "float", 0.0),
            ("phase_end",          "Phase end (deg)",            "float", 360.0),
            ("phase_num_points",   "Num phase points",           "int",   41),
        ])
        # init_pi2_gain: DAC gain of the FIRST (init) pi/2 pulse at the interaction freq, used only
        # in the 2nd-pi/2-at-dynamics (common-frequency) mode. 0 = fall back to the measurement pi/2
        # gain (meas_pi2_gain). Calibrate it by running the Gain×Freq Cal with the INIT qubit as the
        # swept qubit (read its gain off the result), then enter that value here.
        self.param_form_b1d = ParamForm("Sweep parameters (variant B 1D)", [
            ("reps",             "Repetitions",        "int",   500),
            ("phase_start",      "Phase start (deg)",  "float", 0.0),
            ("phase_end",        "Phase end (deg)",    "float", 360.0),
            ("phase_num_points", "Num phase points",   "int",   41),
            ("expt_samples",     "expt_samples (4.65/16 ns)", "int", 2000),
            ("pi2_init_gain",    "Init π/2 gain (DAC, 0=auto)", "int", 0),
        ])
        self.param_form_b2d = ParamForm("Sweep parameters (variant B 2D)", [
            ("reps",               "Repetitions",         "int",   500),
            ("phase_start",        "Phase start (deg)",   "float", 0.0),
            ("phase_end",          "Phase end (deg)",     "float", 360.0),
            ("phase_num_points",   "Num phase points",    "int",   41),
            ("samples_start",      "samples start",       "int",   0),
            ("samples_end",        "samples end",         "int",   8000),
            ("samples_num_points", "Num samples points",  "int",   81),
            ("init_pi2_gain",      "Init π/2 gain (DAC, 0=auto)", "int", 0),
        ])
        # In-situ 2nd-pi/2 gain×freq calibration (MottQuenchPi2GainFreqCal). Runs the
        # full Mott-quench pi/2 sequence and sweeps the 2nd pi/2's freq (x, abs MHz)
        # and gain (y, DAC). The freq axis is auto-centred on the selected swap
        # entry's meas_pi2_freq_abs (± freq_span). gain_end<=0 => auto =
        # CALIB_PI2_GAIN_MULT × default-pi/2-gain. expt_samples is the swap dwell and
        # MUST match the real run. Requires a Dynamics_Point + the 2nd-pi/2 checkbox.
        self.param_form_gfcal = ParamForm("Sweep parameters (2nd π/2 gain×freq cal)", [
            ("freq_span",        "Freq half-span (MHz)",        "float", self.CALIB_PI2_FREQ_SPAN_MHZ),
            ("freq_num_points",  "Num freq points",             "int",   self.CALIB_PI2_FREQ_NUM_POINTS),
            ("gain_start",       "Gain start (DAC)",            "int",   0),
            ("gain_end",         "Gain end (DAC, 0=auto)",      "int",   0),
            ("gain_num_points",  "Num gain points",             "int",   self.CALIB_PI2_GAIN_NUM_POINTS),
            ("expt_samples",     "expt_samples (4.65/16 ns)",   "int",   2000),
            ("reps",             "Repetitions",                 "int",   500),
        ])
        # Single-qubit FF Ramsey T2 (FFRamseyCal). Wait sweep is in samples (start/step/expts),
        # measured at the Expt_FF flux of the selected Ramp_State on the pi2_init qubit.
        self.param_form_fframsey = ParamForm("Sweep parameters (FF Ramsey T2)", [
            ("start",  "Wait start (samples)", "int", 0),
            ("step",   "Wait step (samples)",  "int", 16),
            ("expts",  "Num wait points",      "int", 51),
            ("reps",   "Repetitions",          "int", 1000),
        ])

        # ---- buttons + result ----
        self.run_btn = QPushButton("Run")
        self.run_btn.setStyleSheet("font-weight: bold;")
        self.run_btn.clicked.connect(self._on_run)
        self.result_lbl = QLabel("(no result)")
        self.result_lbl.setStyleSheet("font-weight: bold; color: #555;")
        run_row = QHBoxLayout()
        run_row.addWidget(self.run_btn)
        run_row.addStretch(1)
        run_w = QWidget(); run_w.setLayout(run_row)

        # ---- canvas + log ----
        self.canvas = MplCanvas(self, height=4.5)
        self.toolbar = NavigationToolbar(self.canvas, self)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        f = QFont(); f.setStyleHint(QFont.Monospace); f.setFamily("Consolas")
        self.log.setFont(f)
        self.log.setPlaceholderText("Pi/2-phase progress / fit results appear here.")

        # ---- layout (group selectors on top, splitter under) ----
        left_layout = QVBoxLayout()
        left_layout.addWidget(var_box)
        left_layout.addWidget(qubit_box)
        left_layout.addWidget(self.param_form_a)
        left_layout.addWidget(self.param_form_b1d)
        left_layout.addWidget(self.param_form_b2d)
        left_layout.addWidget(self.param_form_gfcal)
        left_layout.addWidget(self.param_form_fframsey)
        left_layout.addWidget(run_w)
        left_layout.addWidget(self.result_lbl)
        left_layout.addStretch(1)
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
        self._on_variant_changed()  # set initial form visibility / enable states

    # ---- helpers ----

    def refresh_qubit_combos(self):
        """Repopulate pi2_init / swept_qubit combos labeled by CHIP qubit number.

        Pulls the qubit set from the currently-selected readout group's entries
        (sorted numerically). Labels read 'Q<chip_q>' so the user sees the chip
        number directly. currentData() still stores the position index used by
        the program (0-based for pi2_init_index, 1-based for swept_qubit), so
        the cfg-building path is unchanged.

        Falls back to 'Q1..Q<n_qubits>' positional labels only if no readout
        group is selected yet (state may not be ready at construction time).
        """
        # Try to resolve the chip-qubit list from the selected readout group.
        jd = getattr(self.state, "qubit_parameters_json", None) or {}
        rg = (self.readout_group_combo.currentData()
              or self.readout_group_combo.currentText()
              or "")
        chip_qubits: list[str] = []
        if rg and isinstance(jd, dict):
            entries = (jd.get("readout_groups", {})
                         .get(rg, {})
                         .get("entries", {}))
            try:
                chip_qubits = sorted(entries.keys(), key=lambda s: int(str(s)))
            except ValueError:
                chip_qubits = list(entries.keys())
        if not chip_qubits:
            # Pre-selection / no readout group: positional fallback.
            n = max(int(self.state.n_qubits), 1)
            chip_qubits = [str(i + 1) for i in range(n)]

        # Both combos store 0-based position indices as currentData(), matching the
        # uniform 0-based convention inside mSweeppi2Phase.py.
        for cb in (self.pi2_init_combo, self.swept_qubit_combo):
            cb.blockSignals(True)
            cb.clear()
            for i, q in enumerate(chip_qubits):
                cb.addItem(f"Q{q}", i)  # label = chip-q; data = 0-based position index
            cb.blockSignals(False)
        if self.pi2_init_combo.count() > 0:
            self.pi2_init_combo.setCurrentIndex(0)
        if self.swept_qubit_combo.count() > 0:
            self.swept_qubit_combo.setCurrentIndex(0)

    def _current_variant(self) -> str:
        return str(self.variant_combo.currentData() or self.VAR_A)

    def _current_param_form(self) -> ParamForm:
        v = self._current_variant()
        if v == self.VAR_A:
            return self.param_form_a
        if v == self.VAR_B1D:
            return self.param_form_b1d
        if v == self.VAR_GFCAL:
            return self.param_form_gfcal
        if v == self.VAR_FFRAMSEY:
            return self.param_form_fframsey
        return self.param_form_b2d

    def _on_variant_changed(self, *_):
        v = self._current_variant()
        self.param_form_a.setVisible(v == self.VAR_A)
        self.param_form_b1d.setVisible(v == self.VAR_B1D)
        self.param_form_b2d.setVisible(v == self.VAR_B2D)
        self.param_form_gfcal.setVisible(v == self.VAR_GFCAL)
        self.param_form_fframsey.setVisible(v == self.VAR_FFRAMSEY)
        # Ramp_State / Dynamics_Point needed for every Mott variant (B-1D/B-2D and
        # the in-situ gain×freq cal, which runs the same Mott sequence). FF Ramsey also
        # needs a Ramp_State (it supplies Expt_FF, the flux the T2 is measured at).
        need_ramp = v != self.VAR_A
        self.ramp_state_combo.setEnabled(need_ramp)
        self.dynamics_point_combo.setEnabled(need_ramp)
        # 2nd-pi/2-at-dynamics is variant-B-only; disable (don't clear) for variant A.
        self.second_pulse_dyn_check.setEnabled(need_ramp)
        # The swap-generator only makes sense for the Mott variants (its product
        # is a Dynamics_Point); gate it identically to second_pulse_dyn_check.
        self.swap_dyn_btn.setEnabled(need_ramp)

    def _on_pi2_init_changed(self, _idx: int):
        if not self.link_check.isChecked():
            return
        # swept_qubit (1-based) = pi2_init_index (0-based) + 1.
        target = int(self.pi2_init_combo.currentData() or 0) + 1
        for i in range(self.swept_qubit_combo.count()):
            if int(self.swept_qubit_combo.itemData(i)) == target:
                self.swept_qubit_combo.blockSignals(True)
                self.swept_qubit_combo.setCurrentIndex(i)
                self.swept_qubit_combo.blockSignals(False)
                break

    def _on_link_toggled(self, checked: bool):
        self.swept_qubit_combo.setEnabled(not checked)
        if checked:
            self._on_pi2_init_changed(self.pi2_init_combo.currentIndex())

    # ---- group selectors (mirror TwoQubitCalibTab) ----

    def _on_readout_group_changed(self, _idx: int) -> None:
        self.state.current_readout_group = self.readout_group_combo.currentText() or ""
        # Chip-q labels in pi2_init / swept_qubit combos depend on this group's
        # entries -- relabel them now so the user sees correct Q<n> numbers.
        self.refresh_qubit_combos()

    def _on_drive_group_changed(self, _idx: int) -> None:
        data = self.drive_group_combo.currentData()
        self.state.current_drive_group = data or ""

    def refresh_groups_from_state(self) -> None:
        """Repopulate readout/drive + Ramp_State/Dynamics_Point combos.

        Readout/drive mirrors TwoQubitCalibTab. Ramp_State and Dynamics_Point
        enumerate every entry across all ramp_groups / dynamics_groups (flat
        list) -- build_config consumes them as entry names, not group names.
        After repopulating the readout group combo, relabel the qubit combos
        with chip-q numbers from the selected group's entries.
        """
        jd = self.state.qubit_parameters_json or {}
        readout_groups = list((jd.get("readout_groups") or {}).keys())
        drive_groups = list((jd.get("drive_groups") or {}).keys())

        self.readout_group_combo.blockSignals(True)
        self.readout_group_combo.clear()
        for n in readout_groups:
            self.readout_group_combo.addItem(n)
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

        # Flatten ramp_groups / dynamics_groups -> entry-name list.
        ramp_entries: list[str] = []
        for grp in (jd.get("ramp_groups") or {}).values():
            ramp_entries.extend((grp or {}).get("entries", {}).keys())
        dyn_entries: list[str] = []
        for grp in (jd.get("dynamics_groups") or {}).values():
            dyn_entries.extend((grp or {}).get("entries", {}).keys())

        self.ramp_state_combo.blockSignals(True)
        self.ramp_state_combo.clear()
        self.ramp_state_combo.addItem(self.NONE_LABEL, "")
        for n in ramp_entries:
            self.ramp_state_combo.addItem(n, n)
        self.ramp_state_combo.setCurrentIndex(0)
        self.ramp_state_combo.blockSignals(False)

        self.dynamics_point_combo.blockSignals(True)
        self.dynamics_point_combo.clear()
        self.dynamics_point_combo.addItem(self.NONE_LABEL, "")
        for n in dyn_entries:
            self.dynamics_point_combo.addItem(n, n)
        self.dynamics_point_combo.setCurrentIndex(0)
        self.dynamics_point_combo.blockSignals(False)

        # After the readout group combo is populated and a default is selected,
        # relabel the pi2_init / swept_qubit combos with chip-q numbers from it.
        self.refresh_qubit_combos()

    # ---- run ----

    def _build_cfg(self, variant: str, pi2_init_index: int, swept_qubit: int,
                   sweep_params: dict) -> dict:
        """Build a multi-qubit cfg for the selected variant.

        Mirrors mott_quench_basic.py: Qubit_Readout / Qubit_Pulse come from
        the readout group's entries (sorted by integer key), Readout_Point /
        Ramp_State / Dynamics_Point come from the top-row combos. SingleShot
        cals are layered in the same way as ``build_two_qubit_chevron_config``.
        """
        jd = self.state.qubit_parameters_json or {}
        rg = self.state.current_readout_group or None
        if not rg:
            raise RuntimeError("No readout group selected.")

        # Qubit_Readout / Qubit_Pulse = all entries in the selected readout
        # group. This follows mott_quench_basic.py's pattern.
        entries = (jd.get("readout_groups", {}).get(rg, {}).get("entries", {}) or {})
        try:
            qubit_list = sorted(entries.keys(), key=lambda s: int(str(s)))
        except ValueError:
            qubit_list = list(entries.keys())
        if not qubit_list:
            raise RuntimeError(
                f"Readout group {rg!r} has no entries; cannot build a multi-qubit cfg."
            )
        Qubit_Readout = [str(q) for q in qubit_list]
        Qubit_Pulse = list(Qubit_Readout)  # same set, same order (mott_quench_basic.py)

        # Ramp_State is required for variants B (provides Gain_Expt -- the FF endpoint
        # of the dynamics window). Dynamics_Point is OPTIONAL: when omitted, no Gain_Dynamics
        # / t_offset overrides are applied, so the FF goes straight from Expt_FF to Readout_FF
        # with zero channel-skew. Variant A ignores both.
        ramp_state = str(self.ramp_state_combo.currentData() or "") or None
        dynamics_point = str(self.dynamics_point_combo.currentData() or "") or None
        if variant != self.VAR_A and not ramp_state:
            raise RuntimeError(
                "Variants B (Mott-quench) need a Ramp_State (the dynamics FF endpoint). "
                "Pick an entry in the top-row Ramp_State combo. "
                "Dynamics_Point is optional -- leave it as (none) to go straight to readout."
            )

        build_kwargs: dict = {
            "Qubit_Readout": Qubit_Readout,
            "Qubit_Pulse": Qubit_Pulse,
            "Readout_Point": rg,
            "jd": jd,
        }
        if variant != self.VAR_A:
            build_kwargs["Ramp_State"] = ramp_state
            if dynamics_point:
                build_kwargs["Dynamics_Point"] = dynamics_point
        cfg = build_config(**build_kwargs)

        # SingleShot cals (lifted from build_two_qubit_chevron_config).
        angle_list, threshold_list, confusion_matrix = [], [], []
        for Q in Qubit_Readout:
            ro = (jd.get("readout_groups", {})
                    .get(rg, {})
                    .get("entries", {})
                    .get(str(Q), {})
                    .get("Readout", {})) or {}
            angle_list.append(float(ro.get("angle", 0.0)))
            threshold_list.append(float(ro.get("threshold", 0.0)))
            confusion_matrix.append(_confusion_matrix_for(ro))
        cfg["angle"] = angle_list
        cfg["threshold"] = threshold_list
        cfg["confusion_matrix"] = confusion_matrix

        # Tab-supplied keys (these override anything build_config produced).
        cfg["pi2_init_index"] = int(pi2_init_index)
        cfg["swept_qubit"] = int(swept_qubit)
        # Opt-in 2nd-pi/2-at-dynamics path is a variant-B-only feature (MottQuenchPi2Phase /
        # MottQuenchPi2Phase2D). Only set the flag for those so it can't affect variant A.
        if variant != self.VAR_A:
            cfg["second_pulse_at_dynamics"] = bool(self.second_pulse_dyn_check.isChecked())
        # Init π/2 gain: build_config already loaded it from the dynamics entry (auto). The form
        # field is an OPTIONAL manual override -- apply it only when > 0, and pull it out of the
        # blind cfg.update so a 0 ("auto") can't clobber the entry-derived value.
        _field_init_gain = int(sweep_params.pop("pi2_init_gain", 0) or 0)
        cfg.update(sweep_params)
        if _field_init_gain > 0:
            cfg["pi2_init_gain"] = _field_init_gain
        # Stash the qubit set for the result label.
        cfg["_Qubit_Readout_list"] = Qubit_Readout
        cfg["_Qubit_Pulse_list"] = Qubit_Pulse
        return cfg

    # ---- swap-two-qubits -> dynamics point ----

    @staticmethod
    def _ff_gains_to_freqs8(ff_gains):
        """Forward map: 8 FF gains -> 8 dressed frequencies (MHz), chip 1..8.

        Same algorithm as FFFrequenciesTab._compute_frequencies, which is a
        direct copy of Flux_Files.print_bs_ff.ff_gains_to_freqs. We do NOT
        import print_bs_ff (it runs a module-level print loop and uses bare,
        non-package imports); instead we reuse the already-imported flux-model
        globals (model_mapping / flux_vector / beta_matrix / full_device_calib).
        """
        import numpy as np
        bare_qubits = [f"Q{i}_bare" for i in range(1, 9)]
        bare_all = bare_qubits + ["C1", "C2", "C3", "C4", "C5", "C6"]
        FF_flux_quanta = np.array(
            [model_mapping[bq].flux_quantum_voltage for bq in bare_qubits]
        )
        flux_changes = np.asarray(ff_gains, float) / FF_flux_quanta
        target_fluxes = flux_vector + np.concatenate([flux_changes, np.zeros(6)])
        bare_freqs = [
            1000 * model_mapping[name].freq(flux)
            for name, flux in zip(bare_all, target_fluxes)
        ]
        dressed, _g = full_device_calib.dress_system(
            bare_freqs, beta_matrix=beta_matrix, plot=False,
        )
        return np.asarray(dressed, float)

    def _resolve_base_pulse_ff(self):
        """Resolve the base Pulse_FF exactly as build_config does.

        build_config sets Gain_Pulse = drives[0]['Pulse_FF'] (build_config.py),
        where each drive is _resolve_drive(jd, Qubit_Pulse[i]). _build_cfg never
        passes a drive group to build_config, so we mirror that: resolve each
        Qubit_Pulse entry's Pulse_FF and require they agree (build_config's own
        consistency assert). Returns an 8-int list indexed chip qubit 1..8.
        """
        jd = self.state.qubit_parameters_json or {}
        rg = self.state.current_readout_group or None
        if not rg:
            raise RuntimeError("No readout group selected.")
        entries = (jd.get("readout_groups", {}).get(rg, {}).get("entries", {}) or {})
        try:
            qubit_list = sorted(entries.keys(), key=lambda s: int(str(s)))
        except ValueError:
            qubit_list = list(entries.keys())
        if not qubit_list:
            raise RuntimeError(f"Readout group {rg!r} has no entries.")
        Qubit_Pulse = [str(q) for q in qubit_list]
        resolved = {P: list(_build_resolve_drive(jd, P)["Pulse_FF"]) for P in Qubit_Pulse}
        distinct = {tuple(v) for v in resolved.values()}
        if len(distinct) > 1:
            raise RuntimeError(
                "Qubit_Pulse entries do not share one Pulse_FF: "
                + str(resolved)
            )
        pulse_ff = resolved[Qubit_Pulse[0]]
        if len(pulse_ff) != 8:
            raise RuntimeError(
                f"Resolved Pulse_FF has length {len(pulse_ff)}, expected 8."
            )
        return Qubit_Pulse, [int(round(g)) for g in pulse_ff]

    def _on_swap_two_qubits(self):
        """Generate a swapped-frequency dynamics point and select it.

        Forward-map current Pulse_FF -> 8 freqs, exchange seed/swept entries,
        inverse-map the full 8-vector via CalculateFFExperiment (so crosstalk
        from moving the pair is compensated on the others), write the result as
        a new dynamics_groups entry, refresh, and select it. No hardware I/O.
        """
        try:
            import numpy as np
            jd = self.state.qubit_parameters_json or {}

            # 1. Seed / swept as CHIP qubit numbers. Both combos store 0-based
            #    positions into Qubit_Pulse as currentData() (refresh_qubit_combos).
            seed_idx = int(self.pi2_init_combo.currentData() or 0)
            swept_idx = int(self.swept_qubit_combo.currentData() or 0)

            # 2. Base Pulse_FF resolved the build_config way (8 ints, chip 1..8).
            Qubit_Pulse, _ = self._resolve_base_pulse_ff()  # also validates Pulse_FF consistency
            if not (0 <= seed_idx < len(Qubit_Pulse) and 0 <= swept_idx < len(Qubit_Pulse)):
                raise RuntimeError(
                    f"seed/swept index out of range for Qubit_Pulse {Qubit_Pulse}."
                )
            seed_chip = int(Qubit_Pulse[seed_idx])
            swept_chip = int(Qubit_Pulse[swept_idx])
            if seed_chip == swept_chip:
                raise RuntimeError(
                    f"Seed and swept qubit are the same (Q{seed_chip}); pick two distinct qubits."
                )

            # 3. Resolve the ramp. Spectators stay at their ramp (Expt_FF) frequencies, so the
            #    dynamics point is the Expt_FF gains with ONLY the swap pair overwritten
            #    (per-qubit FF gains are independent). The swap pair takes each other's
            #    INIT_FF (init_ff_delta) frequencies.
            ramp_state = str(self.ramp_state_combo.currentData() or "") or None
            if not ramp_state:
                raise RuntimeError("Select a Ramp_State first -- spectators inherit its Expt_FF.")
            ramp = _build_resolve_ramp(jd, ramp_state)
            expt_ff = list(ramp["Expt_FF"])                  # spectator base (the held ramp point)
            if len(expt_ff) != 8:
                raise RuntimeError(f"Resolved Expt_FF has length {len(expt_ff)}, expected 8.")
            init_ff = ramp["Init_FF"]
            if init_ff is None:                              # no distinct init segment
                init_ff = expt_ff
                self.log.appendPlainText(
                    f"[note] Ramp_State {ramp_state!r} has no Init_FF; using Expt_FF for the swap pair.")
            init_ff = list(init_ff)

            # 4. Swap the pair's *Init_FF* (init_ff_delta) frequencies -- where the qubits sit
            #    in the ramp's init segment. The swept qubit lands on the seed's Init_FF
            #    frequency; that value is also passed to the program as the measurement-pi/2
            #    drive frequency so it stays on-resonance.
            init_freqs = self._ff_gains_to_freqs8(init_ff)   # 8 dressed freqs at the init segment
            seed_init = float(init_freqs[seed_chip - 1])
            swept_init = float(init_freqs[swept_chip - 1])

            # 5. Pair FF gains for the exchanged Init_FF frequencies (freq->gain). Only the
            #    pair is specified; other gains are per-qubit independent, so keep the ramp
            #    (Expt_FF) values and overwrite just the pair.
            from WorkingProjects.triangle_lattice_quench.Flux_Files.Calculate_FF import (
                CalculateFFExperiment,
            )
            cfg = {
                "frequencies": {f"Q{seed_chip}": swept_init, f"Q{swept_chip}": seed_init},
                "plot_effective_system": False,  # keep headless: no plt.show()
            }
            pair_g = np.asarray(
                CalculateFFExperiment(path="", prefix="CalculateFF", soc=None,
                                      soccfg=None, cfg=cfg).acquire()["gains_list"], int)
            new_gains = [int(round(g)) for g in expt_ff]
            new_gains[seed_chip - 1] = int(pair_g[seed_chip - 1])
            new_gains[swept_chip - 1] = int(pair_g[swept_chip - 1])
            meas_pi2_freq_abs = seed_init  # swept qubit parks here -> measurement pi/2 drive freq
            # Achieved dressed freqs of the ACTUAL dynamics point (Expt_FF spectators + pair swap),
            # for the review log + collision check below.
            dressed = self._ff_gains_to_freqs8(new_gains)

            # 6. Write a new dynamics_groups entry. Reuse the FFFrequenciesTab's
            #    in-memory write + refresh path so dirty styling / Save behave
            #    exactly like the existing add-entry flow.
            ff_tab = getattr(self.get_main(), "ff_freq_tab", None)
            dyn_groups = jd.setdefault("dynamics_groups", {})
            if "dynamics_FF_points" in dyn_groups:
                gname = "dynamics_FF_points"
            elif dyn_groups:
                gname = next(iter(dyn_groups.keys()))
            else:
                gname = "dynamics_FF_points"
                dyn_groups[gname] = {"entries": {}}
            group = dyn_groups[gname]
            if not isinstance(group, dict):
                raise RuntimeError(f"dynamics_groups/{gname} is not a dict.")
            entries = group.setdefault("entries", {})

            base_name = f"swap_{seed_chip}_{swept_chip}"
            ename = base_name
            n = 2
            while ename in entries:
                ename = f"{base_name}_{n}"
                n += 1
            entries[ename] = {"Dynamics_FF_abs": list(new_gains),
                              "meas_pi2_freq_abs": round(float(meas_pi2_freq_abs), 4)}

            # Refresh + dirty styling via the FF tab (mirrors _on_crud_entry's
            # _after_jd_mutation call). Snapshot already differs, so Save persists.
            if ff_tab is not None and hasattr(ff_tab, "_after_jd_mutation"):
                ff_tab._after_jd_mutation(select_group=gname, select_entry=ename)
            else:
                main = self.get_main()
                if main is not None and hasattr(main, "refresh_qubit_summary"):
                    main.refresh_qubit_summary()

            # 7. Add the new entry to this tab's Dynamics_Point combo and select
            #    it. Insert directly rather than refresh_groups_from_state(),
            #    which would reset Ramp_State and the pi2/swept combos (the user
            #    needs Ramp_State to stay set so the Variant-B run still builds).
            if self.dynamics_point_combo.findData(ename) < 0:
                self.dynamics_point_combo.addItem(ename, ename)
            self.dynamics_point_combo.setCurrentIndex(
                self.dynamics_point_combo.findData(ename)
            )

            # 8. Review / safety: log gains + freqs; warn on coupled-pair collisions.
            log = self.log.appendPlainText
            log(f"--- Swap Q{seed_chip} <-> Q{swept_chip} -> dynamics entry "
                f"'{gname}/{ename}' ---")
            log(f"Ramp_State         : {ramp_state}  (spectators keep its Expt_FF)")
            log(f"Expt_FF (ramp)     : {[int(round(g)) for g in expt_ff]}")
            log(f"pair swap freqs    : Q{seed_chip}->{swept_init:.1f}, Q{swept_chip}->{seed_init:.1f} MHz (Init_FF)")
            log(f"measurement pi/2   : driven at {meas_pi2_freq_abs:.1f} MHz (swept Q{swept_chip} parks here)")
            log(f"new_gains          : {new_gains}")
            log(f"achieved dressed   : {np.round(dressed, 1).tolist()}")
            log("NOTE: Q2 FF gain is hard-coded to 0 in CalculateFF (broken qubit); "
                "its frequency is fixed and will not track a swap.")

            # Collision check on the ACHIEVED dressed freqs (not the target).
            COLL_MHZ = 5.0
            warned = False
            for q_a, q_b in _FF_FREQ_COUPLED_PAIRS:
                df = abs(float(dressed[q_a - 1]) - float(dressed[q_b - 1]))
                if df < COLL_MHZ:
                    log(f"[WARN] coupled pair Q{q_a}/Q{q_b} are {df:.1f} MHz apart "
                        f"(< {COLL_MHZ:.0f} MHz) at this dynamics point — possible collision.")
                    warned = True
            if not warned:
                log(f"No coupled-pair collisions < {COLL_MHZ:.0f} MHz detected.")
            log("Review the gains in the FF table, then Save to persist. "
                "Tick '2nd π/2 at dynamics point' and run a Variant B sweep.")

            self.result_lbl.setText(
                f"Generated dynamics point '{ename}' (swap Q{seed_chip}<->Q{swept_chip}). "
                "Review + Save."
            )
        except Exception:
            self.log.appendPlainText("[FAIL] Swap-two-qubits generation failed:")
            for line in traceback.format_exc().rstrip().splitlines():
                self.log.appendPlainText(f"       {line}")
            self.log.appendPlainText(
                "       If the flux-model import failed, the Flux_Files model "
                "(Whole_system_to_Voltages / model_mapping) may be stale or unloadable."
            )
            self.result_lbl.setText("Swap generation FAILED (see log).")

    # ---- calibrate 2nd pi/2 frequency at the swap point ----

    def _find_dynamics_entry(self, dyn_name: str):
        """Return (group_name, raw_entry_dict) for the named dynamics entry.

        The combo stores only the entry NAME; the raw entry (with the
        ``meas_pi2_freq_abs`` key UN-stripped) lives under some group's
        ``entries``. We must mutate the raw entry, NOT the dict returned by
        ``_build_resolve_dynamics`` (that one has the ``_abs`` suffix stripped
        to ``meas_pi2_freq``).
        """
        jd = self.state.qubit_parameters_json or {}
        for gname, grp in (jd.get("dynamics_groups") or {}).items():
            ents = (grp or {}).get("entries", {})
            if dyn_name in ents:
                return gname, ents[dyn_name]
        raise RuntimeError(f"Dynamics entry {dyn_name!r} not found in any dynamics_groups.")

    # 2nd-pi/2 in-situ 2D (gain x freq) calibration. Frequency axis: half-width
    # (MHz) around the entry's current meas_pi2_freq_abs. Gain axis: 0 ..
    # CALIB_PI2_GAIN_MULT * default-pi/2-gain (covers ~one full Rabi period so the
    # pi/2 = quarter is bracketed).
    CALIB_PI2_FREQ_SPAN_MHZ = 40.0
    CALIB_PI2_FREQ_NUM_POINTS = 21
    CALIB_PI2_GAIN_MULT = 4.0
    CALIB_PI2_GAIN_NUM_POINTS = 21

    def _build_gfcal_cfg(self, pi2_init_index: int, swept_qubit: int,
                         sweep_params: dict) -> dict:
        """Build the cfg for the VAR_GFCAL (MottQuenchPi2GainFreqCal) run.

        Runs the FULL Mott-quench pi/2 sequence (init pi/2 / ramp / swap / 2nd pi/2)
        UNCHANGED and sweeps the 2nd (measurement) pi/2's drive FREQUENCY x GAIN (2D)
        around the selected Dynamics_Point's meas_pi2_freq_abs. ``sweep_params`` is the
        param_form_gfcal read-back (freq_span / freq_num_points / gain_start / gain_end
        / gain_num_points / expt_samples / reps).

        Stashes the write-back targets (_calib_*) used by _on_gfcal_finished, since the
        finished slot runs after the worker and needs the raw swap entry + old values.
        Raises (caught by _on_run -> QMessageBox.critical) on any precondition failure.
        """
        dyn_name = str(self.dynamics_point_combo.currentData() or "")
        if not dyn_name:
            raise RuntimeError("Select a Dynamics_Point (swap entry) first.")
        # Force the 2nd-pi/2-at-dynamics path on (the only mode that consumes
        # meas_pi2_freq); require the checkbox so the user has set the matching state.
        if not self.second_pulse_dyn_check.isChecked():
            raise RuntimeError(
                "Tick '2nd π/2 at dynamics point (swapped freq)' first -- "
                "meas_pi2_freq is only consumed in that mode."
            )

        # Map swept combo (0-based position) -> chip qubit, same convention as
        # _build_cfg / _resolve_base_pulse_ff (readout-group entries sorted by int key).
        Qubit_Pulse, _ = self._resolve_base_pulse_ff()
        swept_idx = int(swept_qubit)
        if not (0 <= swept_idx < len(Qubit_Pulse)):
            raise RuntimeError(
                f"Swept index {swept_idx} out of range for Qubit_Pulse {Qubit_Pulse}."
            )
        swept_chip = int(Qubit_Pulse[swept_idx])

        # Raw swap entry (UN-stripped meas_pi2_freq_abs). Sweep centre = that value
        # (the model prediction we are replacing); fall back to the swept qubit's
        # drive frequency if absent.
        gname, raw_entry = self._find_dynamics_entry(dyn_name)
        center = raw_entry.get("meas_pi2_freq_abs")
        if center is None:
            jd = self.state.qubit_parameters_json or {}
            center = float(_build_resolve_drive(jd, str(swept_chip))["Frequency"])
        center = float(center)

        # Build the Variant-B-1D base cfg the SAME way a Variant-B run does (readout/
        # drive/Ramp_State/Dynamics_Point + SingleShot cals + second_pulse_at_dynamics).
        # MottQuenchPi2GainFreqCal reads freq_*/gain_* from cfg; the rest of the sequence
        # (init/ramp/swap/expt_samples) is identical to the real run. We feed the B-1D
        # base only the keys it consumes (reps + expt_samples); freq_* must be in
        # sweep_params BEFORE the build (build_config copies them through cfg.update).
        span = float(sweep_params["freq_span"])
        base_params = {
            "reps": int(sweep_params["reps"]),
            "expt_samples": int(sweep_params["expt_samples"]),
            "freq_start": center - span,
            "freq_end": center + span,
            "freq_num_points": int(sweep_params["freq_num_points"]),
        }
        cfg = self._build_cfg(self.VAR_B1D, pi2_init_index, swept_idx, base_params)
        cfg["second_pulse_at_dynamics"] = True
        # analyze() needs Qubit_Pulse (chip labels) to map swept -> readout idx;
        # _build_cfg stashes it as _Qubit_Pulse_list. Expose under the key analyze reads.
        cfg.setdefault("Qubit_Pulse", list(cfg.get("_Qubit_Pulse_list", Qubit_Pulse)))

        # Gain axis (DAC). Default centre = the default pi/2 gain = qubit_gains[swept_idx]
        # (normalized full-pi gain, set by build_config) * 32766 / 2. swept_idx is the
        # 0-based POSITION in Qubit_Pulse (what we pass as swept_qubit), NOT the chip
        # number. qubit_gains only exists post-build_config, so this MUST run after
        # _build_cfg.
        center_gain_dac = float(cfg["qubit_gains"][swept_idx]) * 32766.0 / 2.0
        cfg["gain_start"] = int(sweep_params["gain_start"])
        gain_end = int(sweep_params["gain_end"])
        if gain_end <= 0:
            # Auto: MULT * default-pi/2-gain (one ~full Rabi period brackets the pi/2 =
            # quarter point).
            gain_end = int(round(self.CALIB_PI2_GAIN_MULT * center_gain_dac))
        # DAC full-scale guard: meas_pi2_gain feeds add_pulse as gain/32766, so any
        # sweep point > 32766 would drive a normalized gain > 1.0 (QICK error / silent
        # wrap). Cap VISIBLY rather than clip silently (per the no-silent-clip rule).
        self._calib_gain_capped = gain_end > 32766
        if self._calib_gain_capped:
            gain_end = 32766
        cfg["gain_end"] = gain_end
        cfg["gain_num_points"] = int(sweep_params["gain_num_points"])

        # Stash write-back targets for the finished slot (write-back is on GUI thread).
        self._calib_swept_chip = swept_chip
        self._calib_dyn_name = dyn_name
        self._calib_dyn_group = gname
        self._calib_raw_entry = raw_entry
        self._calib_meas_freq_old = float(center)
        _old_g = raw_entry.get("meas_pi2_gain_abs")
        self._calib_meas_gain_old = (float(_old_g) if _old_g is not None else None)

        self.log.appendPlainText(
            f"--- 2nd π/2 gain×freq cal (IN-SITU 2D): Q{swept_chip} at swap point "
            f"'{gname}/{dyn_name}' ---"
        )
        self.log.appendPlainText(
            f"Full Mott-quench sequence, sweeping the 2nd pi/2 FREQ + GAIN. "
            f"freq: {cfg['freq_start']:.2f} .. {cfg['freq_end']:.2f} MHz "
            f"({cfg['freq_num_points']} pts), centre {center:.2f} MHz (model). "
            f"gain: {cfg['gain_start']} .. {cfg['gain_end']} DAC "
            f"({cfg['gain_num_points']} pts)."
        )
        if self._calib_gain_capped:
            self.log.appendPlainText(
                f"[WARN] auto gain_end exceeds DAC full-scale (32766); gain axis CAPPED "
                f"at 32766 DAC. The swept qubit's normalized pi-gain is >0.5, so the full "
                f"Rabi period may not be bracketed -- the pi/2 gain estimate could land "
                f"below the true quarter point. Inspect the 2D map."
            )
        self.log.appendPlainText(
            f"dynamics dwell expt_samples = {cfg.get('expt_samples')} "
            f"(from the gain×freq cal form) -- this MUST match the real run's swap dwell, "
            f"else the swept qubit isn't parked at the swapped frequency."
        )
        return cfg

    def _build_fframsey_cfg(self, measured_idx: int, sweep_params: dict) -> dict:
        """Build a SINGLE-QUBIT cfg for the VAR_FFRAMSEY (FFRamseyCal) run.

        Measures single-qubit T2 (Ramsey) at the Ramp_State's Expt_FF flux on the
        qubit selected in pi2_init_combo (0-based POSITION into the readout group).
        FFRamseyCal reads index 0 of every per-qubit list, so we hand build_config a
        one-element Qubit_Readout/Qubit_Pulse = [measured_chip]. ``sweep_params`` is
        the param_form_fframsey read-back (start / step / expts / reps, in samples).
        Raises (caught by _on_run -> QMessageBox.critical) on any precondition failure.
        """
        jd = self.state.qubit_parameters_json or {}
        rg = self.state.current_readout_group or None
        if not rg:
            raise RuntimeError("No readout group selected.")
        # Ramp_State supplies Expt_FF -- the flux the free precession (T2) happens at.
        ramp_state = str(self.ramp_state_combo.currentData() or "") or None
        if not ramp_state:
            raise RuntimeError(
                "FF Ramsey needs a Ramp_State (it supplies Expt_FF, the flux the T2 is "
                "measured at). Pick an entry in the top-row Ramp_State combo."
            )

        # Map measured combo (0-based position) -> chip qubit, same convention as
        # _build_cfg (readout-group entries sorted by integer key).
        entries = (jd.get("readout_groups", {}).get(rg, {}).get("entries", {}) or {})
        try:
            qubit_list = sorted(entries.keys(), key=lambda s: int(str(s)))
        except ValueError:
            qubit_list = list(entries.keys())
        if not qubit_list:
            raise RuntimeError(f"Readout group {rg!r} has no entries.")
        Qubit_Readout = [str(q) for q in qubit_list]
        if not (0 <= int(measured_idx) < len(Qubit_Readout)):
            raise RuntimeError(
                f"Measured index {measured_idx} out of range for {Qubit_Readout}."
            )
        measured_chip = str(Qubit_Readout[int(measured_idx)])

        # SINGLE-QUBIT build: one-element Qubit_Readout/Qubit_Pulse so FFRamseyCal's
        # index-0 reads land on the measured qubit. Ramp_State sets Gain_Expt = Expt_FF.
        cfg = build_config(
            Qubit_Readout=[measured_chip], Qubit_Pulse=[measured_chip],
            Readout_Point=rg, Ramp_State=ramp_state, jd=jd,
        )

        # Partner-detune: hold every OTHER qubit at its Pulse_FF (idle) during the wait,
        # so only the measured qubit sits at Expt_FF (no swap -> clean single-qubit T2).
        for q, entry in cfg.get("FF_Qubits", {}).items():
            if str(q) != measured_chip:
                entry["Gain_Expt"] = entry.get("Gain_Pulse", 0)

        # SingleShot cals for the single measured qubit (parity with _build_cfg; FFRamseyCal
        # itself uses normalize_contrast on raw IQ, so these are carried as metadata).
        ro = (jd.get("readout_groups", {})
                .get(rg, {})
                .get("entries", {})
                .get(measured_chip, {})
                .get("Readout", {})) or {}
        cfg["angle"] = [float(ro.get("angle", 0.0))]
        cfg["threshold"] = [float(ro.get("threshold", 0.0))]
        cfg["confusion_matrix"] = [_confusion_matrix_for(ro)]

        # FFRamseyCal's _body loads cfg["IDataArray"] for the variable-length wait segment:
        # a compensated step from Pulse_FF (idle) to Gain_Expt per FF channel. The class does
        # not build it (its usual runner does), so build it here from the (already partner-
        # detuned) gains -- only the measured qubit steps to Expt_FF; others stay flat at idle.
        from WorkingProjects.triangle_lattice_quench.Helpers.FFEnvelope_Helpers import StepPulseArrays
        cfg["IDataArray"] = StepPulseArrays(cfg, 'Gain_Pulse', 'Gain_Expt')

        # Wait sweep (samples) + reps from the form. sigma / relax_delay come from
        # build_config/BaseConfig -- do not invent them.
        cfg["start"] = int(sweep_params["start"])
        cfg["step"] = int(sweep_params["step"])
        cfg["expts"] = int(sweep_params["expts"])
        cfg["reps"] = int(sweep_params["reps"])

        # Stash the measured chip for the render title / result label.
        cfg["_measured_chip"] = measured_chip

        self.log.appendPlainText(
            f"--- FF Ramsey T2 (single-qubit): Q{measured_chip} at Ramp_State "
            f"'{ramp_state}' (Expt_FF) ---"
        )
        self.log.appendPlainText(
            f"wait: {cfg['start']} .. "
            f"{cfg['start'] + cfg['step'] * cfg['expts']} samples "
            f"({cfg['expts']} pts), reps {cfg['reps']}. "
            f"All other qubits held at Pulse_FF (idle) so only Q{measured_chip} precesses."
        )
        return cfg

    def _render_calib_pi2_2d(self, data, ro_idx):
        """Render the 2D gain×freq calibration map on the GUI canvas. The cal
        data dict's axes are 'meas_pi2_freq' (x) and 'meas_pi2_gain' (y) -- NOT
        the (expt_samples, measurement_pi2_phases) axes _render's VAR_B2D branch
        hardcodes -- so we draw a dedicated imshow per readout here."""
        import numpy as np
        try:
            d = data.get("data", {}) if isinstance(data, dict) else {}
            Z = d.get("population_corrected")
            if Z is None:
                self.log.appendPlainText("(no population_corrected to plot)")
                return
            Z = np.asarray(Z, float)                     # (R, len(gain), len(freq))
            x = np.asarray(d.get("meas_pi2_freq", []), float)   # freq (x)
            y = np.asarray(d.get("meas_pi2_gain", []), float)   # gain (y)
            ro_list = d.get("readout_list") or d.get("Qubit_Readout_List") or []
            self.canvas.fig.clf()
            n_ros = Z.shape[0]
            extent = None
            if len(x) and len(y):
                extent = [x[0], x[-1], y[0], y[-1]]
            # One shared color scale + single colorbar across all readouts.
            finite = Z[np.isfinite(Z)]
            vmin, vmax = (float(finite.min()), float(finite.max())) if finite.size else (0.0, 1.0)
            if vmin == vmax:
                vmax = vmin + 1e-9
            axs, ims = [], []
            for r in range(n_ros):
                ax = self.canvas.fig.add_subplot(1, n_ros, r + 1)
                im = ax.imshow(Z[r], aspect="auto", origin="lower",
                          extent=extent, interpolation="none", vmin=vmin, vmax=vmax)
                title = f"Q{ro_list[r]}" if r < len(ro_list) else f"RO {r}"
                if ro_idx is not None and r == ro_idx:
                    title += " (swept)"
                ax.set_title(title)
                ax.set_xlabel("2nd pi/2 freq (MHz)")
                if r == 0:
                    ax.set_ylabel("2nd pi/2 gain (DAC)")
                axs.append(ax); ims.append(im)
            self.canvas.fig.colorbar(ims[-1], ax=axs, label="population (corr.)")
            self.canvas.draw()
        except Exception:
            self.log.appendPlainText("Calib 2D render failed (see console).")
            traceback.print_exc()

    def _on_gfcal_finished(self, expt, data):
        """VAR_GFCAL finish path: render the 2D gain×freq map, write the measured
        freq+gain back into the raw swap entry, refresh the summary, and pop an info
        box. Folded in from the old dedicated-button handler. Caller (_on_finished)
        re-enables the Run button + clears the worker."""
        d = data.get("data", {}) if isinstance(data, dict) else {}
        if "meas_pi2_freq_cal" not in d or "meas_pi2_gain_cal" not in d:
            raise RuntimeError(
                "MottQuenchPi2GainFreqCal.analyze produced no "
                "'meas_pi2_freq_cal'/'meas_pi2_gain_cal' "
                f"(data keys: {list(d.keys())})."
            )
        qubit_freq = float(d["meas_pi2_freq_cal"])
        meas_gain = float(d["meas_pi2_gain_cal"])
        ro_idx = d.get("meas_pi2_cal_ro_idx")
        swept_chip = int(self._calib_swept_chip)
        dyn_name = str(self._calib_dyn_name)
        old_freq = float(self._calib_meas_freq_old)
        old_gain = self._calib_meas_gain_old

        # Render the 2D gain×freq map (freq x-axis, gain y-axis) -- NOT the B-2D
        # render (which assumes expt_samples/phase axes).
        self._render_calib_pi2_2d(data, ro_idx)

        # Target slot: init-mode writes the INIT pi/2 gain (and leaves the shared freq alone);
        # else the measurement pi/2 freq+gain (default).
        init_mode = bool(self.gfcal_init_check.isChecked())
        pulse_label = "init π/2" if init_mode else "2nd π/2"
        old_gain_str = (f"{old_gain:.0f}" if old_gain is not None else "n/a")
        self.log.appendPlainText(
            f"{pulse_label} for Q{swept_chip} at swap point '{dyn_name}': "
            f"measured freq {qubit_freq:.2f} MHz (was {old_freq:.2f}), "
            f"measured gain {meas_gain:.0f} DAC (was {old_gain_str}); "
            f"readout idx {ro_idx}."
        )

        # Write the measured value(s) back into the RAW swap entry (in memory).
        # Persist via the toolbar Save action, not here.
        new_freq = round(qubit_freq, 4)
        new_gain = int(round(meas_gain))
        if init_mode:
            # Both pulses share one frequency, so the init cal writes ONLY its gain; set the
            # shared meas_pi2_freq via a measurement-mode cal.
            self._calib_raw_entry["pi2_init_gain_abs"] = new_gain
            wrote = f"pi2_init_gain_abs = {new_gain}"
        else:
            self._calib_raw_entry["meas_pi2_freq_abs"] = new_freq
            self._calib_raw_entry["meas_pi2_gain_abs"] = new_gain
            wrote = f"meas_pi2_freq_abs = {new_freq} and meas_pi2_gain_abs = {new_gain}"

        try:
            main = self.get_main()
            if main is not None and hasattr(main, "refresh_qubit_summary"):
                main.refresh_qubit_summary()
        except Exception as exc:
            self.log.appendPlainText(f"refresh_qubit_summary failed: {exc}")

        if init_mode:
            self.result_lbl.setText(
                f"Q{swept_chip} init π/2 @ swap: gain {old_gain_str}->{new_gain} DAC. Save.")
        else:
            self.result_lbl.setText(
                f"Q{swept_chip} @ swap: freq {old_freq:.2f}->{new_freq:.2f} MHz, "
                f"gain {old_gain_str}->{new_gain} DAC. Save.")
        QMessageBox.information(
            self, f"{pulse_label} gain×freq measured",
            f"Swept qubit Q{swept_chip} at swap point '{dyn_name}' ({pulse_label}):\n\n"
            f"  measured frequency : {qubit_freq:.4f} MHz (was {old_freq:.4f})\n"
            f"  measured pi/2 gain : {new_gain} DAC (was {old_gain_str})\n\n"
            f"Wrote {wrote} into the dynamics entry (in memory).\n\n"
            "Use 'Save Qubit_Parameters JSON' on the toolbar to persist.",
        )

    def _on_fframsey_finished(self, expt, data):
        """VAR_FFRAMSEY finish path: plot X/Y contrast vs wait, fit the Ramsey
        vector length r = sqrt(X^2 + Y^2) to A*exp(-t/T2)+c (detuning-independent),
        annotate T2. Fully defensive: the plot still ships if the fit degenerates."""
        import numpy as np
        d = data.get("data", {}) if isinstance(data, dict) else {}
        cfg = getattr(expt, "cfg", {}) or {}
        measured_chip = cfg.get("_measured_chip", "?")
        x_samples = np.asarray(d.get("expt_samples", []), float)
        x_contrast = np.asarray(d.get("x_contrast", []), float)
        y_contrast = np.asarray(d.get("y_contrast", []), float)

        # Plot first so a fit failure below still leaves a useful figure.
        self.canvas.fig.clf()
        ax = self.canvas.fig.add_subplot(111)
        ax.plot(x_samples, x_contrast, "o-", color="blue", label="X")
        ax.plot(x_samples, y_contrast, "o-", color="orange", label="Y")
        ax.set_xlabel("wait (samples)")
        ax.set_ylabel("contrast")
        ax.set_title(f"Q{measured_chip} FF Ramsey @ Expt_FF")
        ax.legend(loc="best")

        # Sample index -> us. soccfg from state (the source _on_run uses).
        samples2us = None
        try:
            samples2us = self.state.soccfg.cycles2us(1) / 16
        except Exception:
            samples2us = None

        # Fit the Ramsey vector length r (decays ~exp(-t/T2) independent of detuning).
        t2_ns = None
        try:
            from scipy.optimize import curve_fit
            r = np.sqrt(x_contrast ** 2 + y_contrast ** 2)
            t = x_samples * samples2us if samples2us is not None else x_samples
            unit = "us" if samples2us is not None else "samples"

            def _decay(tt, A, T2, c):
                return A * np.exp(-tt / T2) + c

            span = float(t[-1] - t[0]) if len(t) > 1 else 1.0
            p0 = [float(r[0] - r[-1]), max(span / 2.0, 1e-9), float(r[-1])]
            popt, _ = curve_fit(_decay, t, r, p0=p0, maxfev=20000)
            T2_fit = abs(float(popt[1]))
            # Overlay on the SAME (samples) x-axis as the data traces; _decay(t, *popt)
            # already carries the correct time-unit T2, so its y-values are right.
            ax.plot(x_samples, _decay(t, *popt), "--", color="green", label="T2 fit")
            ax.legend(loc="best")
            if samples2us is not None:
                t2_ns = T2_fit * 1000.0  # us -> ns
                ax.text(0.02, 0.04, f"T2 = {t2_ns:.0f} ns", transform=ax.transAxes,
                        fontsize=10, color="green")
            else:
                # No soccfg -> report in sample units (cannot convert to ns).
                ax.text(0.02, 0.04, f"T2 = {T2_fit:.1f} samples", transform=ax.transAxes,
                        fontsize=10, color="green")
            self.log.appendPlainText(f"T2 fit: {T2_fit:.4g} {unit} (A={popt[0]:.3g}, c={popt[2]:.3g}).")
        except Exception:
            self.log.appendPlainText("[note] T2 envelope fit failed/degenerate; plot only:")
            for line in traceback.format_exc().rstrip().splitlines():
                self.log.appendPlainText(f"       {line}")

        if t2_ns is not None:
            self.result_lbl.setText(f"Q{measured_chip} FF Ramsey: T2 = {t2_ns:.0f} ns.")
        else:
            self.result_lbl.setText(f"Q{measured_chip} FF Ramsey done (see log/plot).")
        self.canvas.draw()

    def _on_run(self):
        if self.worker is not None and self.worker.isRunning():
            return
        if not self.state.is_connected():
            QMessageBox.warning(self, "Not connected",
                                "Connect to the RFSoC first.")
            return
        variant = self._current_variant()
        pi2_init_index = int(self.pi2_init_combo.currentData() or 0)
        swept_qubit = int(self.swept_qubit_combo.currentData() or 1)
        sweep_params = self._current_param_form().values()
        # GFCAL maps the swept-qubit combo's 0-based POSITION (not the 1-based swept_qubit
        # default) -- mirror the old dedicated handler exactly.
        if variant == self.VAR_GFCAL:
            swept_qubit = int(self.swept_qubit_combo.currentData() or 0)

        # Clear BEFORE the cfg build: the GFCAL builder logs its sweep ranges /
        # capping warnings into self.log, which a post-build clear would wipe.
        self.canvas.reset()
        self.log.clear()

        try:
            if variant == self.VAR_FFRAMSEY:
                # Single-qubit FF Ramsey T2: measured qubit = pi2_init_combo position.
                measured_idx = int(self.pi2_init_combo.currentData() or 0)
                cfg = self._build_fframsey_cfg(measured_idx, sweep_params)
            elif variant == self.VAR_GFCAL:
                # In-situ gain×freq cal: full Mott sequence, sweeps 2nd-pi/2 freq+gain.
                # Builds the B-1D base + freq/gain axes and stashes the write-back targets.
                cfg = self._build_gfcal_cfg(pi2_init_index, swept_qubit, sweep_params)
            else:
                cfg = self._build_cfg(
                    variant, pi2_init_index, swept_qubit, sweep_params,
                )
        except Exception as exc:
            QMessageBox.critical(
                self, "Cfg build failed",
                f"Could not build pi/2-phase cfg:\n\n{exc}\n\n"
                "Make sure a readout group is selected and (for Mott variants) "
                "Ramp_State / Dynamics_Point are picked.",
            )
            self.run_btn.setEnabled(True)
            return

        self.run_btn.setEnabled(False)
        self.result_lbl.setText(
            f"Running {variant} (pi2_init={pi2_init_index}, swept={swept_qubit})..."
        )
        self._last_class = variant
        self._last_swept_qubit = swept_qubit

        # FF Ramsey lives in Basic_Experiments; all other variants use the worker default
        # (mSweeppi2Phase.py). class_name=variant matches the FFRamseyCal constant.
        ff_file_path = (
            str(EXPERIMENTAL_SCRIPTS_DIR / "Basic_Experiments" / "mFFRamseyCalibration.py")
            if variant == self.VAR_FFRAMSEY else None
        )
        self.worker = Pi2PhaseWorker(
            soc=self.state.soc, soccfg=self.state.soccfg,
            outer_folder=self.state.outer_folder,
            cfg=cfg, class_name=variant, file_path=ff_file_path,
        )
        self.worker.log.connect(self.log.appendPlainText)
        self.worker.finished_ok.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    # Measurement-Agent hook: run a pi2-phase variant without UI clicks.
    AGENT_ACTION = "pi2_phase"
    AGENT_PARAMS = ("variant (one of SweepPi2Phase / MottQuenchPi2Phase / "
                    "MottQuenchPi2Phase2D / MottQuenchPi2GainFreqCal / FFRamseyCal), "
                    "pi2_init (chip int), swept (chip int), ramp_state (str), "
                    "dynamics_point (str), second_pulse_at_dynamics (bool); sweep sizes "
                    "(applied to the active variant's form): phase_start, phase_end, "
                    "phase_num_points, reps; 2D adds samples_start, samples_end, "
                    "samples_num_points; 1D adds expt_samples, pi2_init_gain; GainFreqCal "
                    "adds freq_span, freq_num_points, gain_start, gain_end, gain_num_points, "
                    "expt_samples; FFRamseyCal adds start, step, expts")

    def agent_run(self, params: dict) -> str:
        """Set variant/qubit/ramp/dynamics controls from agent params and trigger the
        normal run. Param values keep their existing widget value when omitted."""
        variant = params.get("variant")
        if variant is not None:
            _agent_set_combo(self.variant_combo, variant)
            self._on_variant_changed()
        if params.get("pi2_init") is not None:
            _agent_set_combo(self.pi2_init_combo, int(params["pi2_init"]))
        if params.get("swept") is not None:
            _agent_set_combo(self.swept_qubit_combo, int(params["swept"]))
        if params.get("ramp_state") is not None:
            _agent_set_combo(self.ramp_state_combo, str(params["ramp_state"]))
        if params.get("dynamics_point") is not None:
            _agent_set_combo(self.dynamics_point_combo, str(params["dynamics_point"]))
        if "second_pulse_at_dynamics" in params:
            self.second_pulse_dyn_check.setChecked(bool(params["second_pulse_at_dynamics"]))
        # Sweep sizes go into the variant's active form (selected by _on_variant_changed
        # above) so the agent can honor fast settings instead of the slow shipped defaults.
        applied = self._current_param_form().apply(params)
        self._on_run()
        extra = f", set {applied}" if applied else ""
        return (f"pi2-phase {self._current_variant()} "
                f"(init Q{params.get('pi2_init')}, swept Q{params.get('swept')}{extra})")

    def _on_finished(self, expt, data):
        self._last_expt = expt
        self._last_data = data

        # FF Ramsey has its own 1D render + T2 fit and produces no beamsplitter popt that
        # the generic _render path below assumes. Handle it fully here and return.
        if (self._last_class or self.VAR_A) == self.VAR_FFRAMSEY:
            try:
                self._on_fframsey_finished(expt, data)
            except Exception:
                self.log.appendPlainText("[FAIL] FF Ramsey render/fit failed:")
                for line in traceback.format_exc().rstrip().splitlines():
                    self.log.appendPlainText(f"       {line}")
                self.result_lbl.setText("FF Ramsey render FAILED (see log).")
            finally:
                self.log.appendPlainText("--- DONE FF Ramsey T2 ---")
                self.run_btn.setEnabled(True)
                self.worker = None
            return

        # GFCAL has its own render (gain×freq axes) + write-back + info box, and the
        # generic popt/_render path below assumes the beamsplitter-fit data this variant
        # does not produce. Handle it fully here and return.
        if (self._last_class or self.VAR_A) == self.VAR_GFCAL:
            try:
                self._on_gfcal_finished(expt, data)
            except Exception:
                self.log.appendPlainText(
                    "[FAIL] 2nd π/2 gain×freq render/write-back failed:")
                for line in traceback.format_exc().rstrip().splitlines():
                    self.log.appendPlainText(f"       {line}")
                self.result_lbl.setText("2nd π/2 gain×freq write-back FAILED (see log).")
            finally:
                self.log.appendPlainText("--- DONE 2nd π/2 gain×freq cal ---")
                self.run_btn.setEnabled(True)
                self.worker = None
            return

        try:
            self._render(expt, data)
        except Exception:
            traceback.print_exc()
            self.log.appendPlainText("Render failed (see traceback in console).")

        # Map swept_qubit (0-based position in Qubit_Pulse) -> readout index.
        cfg = getattr(expt, "cfg", {}) or {}
        Qubit_Pulse = cfg.get("_Qubit_Pulse_list") or []
        Qubit_Readout = cfg.get("_Qubit_Readout_list") or []
        sq = int(self._last_swept_qubit or 0)
        ro_idx: Optional[int] = None
        if 0 <= sq < len(Qubit_Pulse):
            chip_q = str(Qubit_Pulse[sq])
            if chip_q in Qubit_Readout:
                ro_idx = Qubit_Readout.index(chip_q)
            else:
                self.log.appendPlainText(
                    f"swept_qubit chip Q{chip_q} not in Qubit_Readout "
                    f"{Qubit_Readout}; skipping result label."
                )

        # popt shape (R, 5) = [A, w, phi, offset, gamma] per fit_beamsplitter_offset.
        d = data.get("data", {}) if isinstance(data, dict) else {}
        popt = d.get("popt")
        perr = d.get("perr")
        r_squared = d.get("r_squared")
        if popt is not None and ro_idx is not None:
            try:
                row = popt[ro_idx]
                A, w, phi, offset, gamma = (float(row[i]) for i in range(5))
                r2 = float(r_squared[ro_idx]) if r_squared is not None else float("nan")
                self.result_lbl.setText(
                    f"swept Q{Qubit_Pulse[sq]}: "
                    f"phi = {phi:.2f} deg, A = {A:.3g}, R^2 = {r2:.3f}"
                )
                self.log.appendPlainText(f"popt[{ro_idx}] = {list(row)}")
                if perr is not None:
                    self.log.appendPlainText(f"perr[{ro_idx}] = {list(perr[ro_idx])}")
            except Exception as exc:
                self.result_lbl.setText("(fit row read failed)")
                self.log.appendPlainText(f"Could not extract popt row: {exc}")
        else:
            self.result_lbl.setText("(no fit / swept qubit not in readout)")

        self.log.appendPlainText(f"--- DONE {self._last_class} ---")
        self.run_btn.setEnabled(True)
        self.worker = None

    def _on_failed(self, msg: str):
        first, _, rest = msg.partition("\n")
        self.log.appendPlainText(f"[FAIL] {first}")
        for line in rest.rstrip().splitlines():
            self.log.appendPlainText(f"       {line}")
        self.result_lbl.setText("FAILED")
        self.run_btn.setEnabled(True)
        self.worker = None

    def _render(self, expt, data):
        """Render directly on the GUI canvas (avoid expt.display() so we
        don't re-enter the SweepExperimentND plot path that was neutered in
        the worker). 1D variants: one line plot per readout, with fitted
        sine overlay. 2D variant: imshow per readout (phase vs samples).
        """
        import numpy as np
        d = data.get("data", {}) if isinstance(data, dict) else {}
        Z = d.get("population_corrected")
        if Z is None:
            self.log.appendPlainText("(no population_corrected in data)")
            return
        Z = np.asarray(Z, float)
        # phase axis lives under the savename of the swept x_key; the experiment
        # populates it via SweepHelpers.key_savename. Common names below.
        phases = None
        for k in ("measurement_pi2_phases", "qubit_phases_matrix"):
            v = d.get(k)
            if v is not None:
                phases = np.asarray(v, float)
                break
        if phases is None:
            # Fall back: any 1D axis with the right length.
            phases = np.arange(Z.shape[1] if Z.ndim >= 2 else len(Z))

        variant = self._last_class or self.VAR_A
        self.canvas.fig.clf()

        # Map readout-row index -> chip qubit number for plot titles.
        cfg = getattr(expt, "cfg", {}) or {}
        readout_qubits = (cfg.get("_Qubit_Readout_list")
                          or d.get("readout_list")
                          or [])

        def _ro_title(r: int) -> str:
            return f"Q{readout_qubits[r]}" if r < len(readout_qubits) else f"RO {r}"

        if variant == self.VAR_B2D:
            samples = np.asarray(d.get("expt_samples", []), float)
            # Z shape: (R, O=phase, T=samples)
            n_ros = Z.shape[0]
            # One shared color scale across all readouts (equal color == equal
            # population everywhere) with a single colorbar for the whole figure.
            finite = Z[np.isfinite(Z)]
            vmin, vmax = (float(finite.min()), float(finite.max())) if finite.size else (0.0, 1.0)
            if vmin == vmax:
                vmax = vmin + 1e-9
            extent = None
            if len(samples) and len(phases):
                extent = [samples[0], samples[-1], phases[0], phases[-1]]
            axs, ims = [], []
            for r in range(n_ros):
                ax = self.canvas.fig.add_subplot(1, n_ros, r + 1)
                im = ax.imshow(Z[r], aspect="auto", origin="lower",
                          extent=extent, interpolation="none", vmin=vmin, vmax=vmax)
                ax.set_title(_ro_title(r))
                ax.set_xlabel("samples (4.65/16 ns)")
                if r == 0:
                    ax.set_ylabel("measurement pi/2 phase (deg)")
                axs.append(ax); ims.append(im)
            self.canvas.fig.colorbar(ims[-1], ax=axs, label="population (corr.)")
        else:
            # 1D: Z shape (R, O=phase) or (R, O, 1). Plot line + fit overlay.
            popt = d.get("popt")
            mat = Z.squeeze()
            if mat.ndim == 1:
                mat = mat[None, :]
            n_ros = mat.shape[0]
            for r in range(n_ros):
                ax = self.canvas.fig.add_subplot(1, n_ros, r + 1)
                ax.plot(phases, mat[r], "o-", ms=3, label="data")
                # Sine + exp-decay overlay if popt available.
                try:
                    if popt is not None:
                        A, w, phi, off, gamma = (float(popt[r][i]) for i in range(5))
                        ph_lin = np.linspace(float(phases[0]), float(phases[-1]), 200)
                        # fit_beamsplitter_offset model: A*sin(w*ph + phi)*exp(-gamma*0) + off
                        # at fixed t=0 (variant A) or fixed expt_samples (variant B 1D),
                        # the decay is constant — we just draw the sine.
                        fit = A * np.sin(np.deg2rad(w * ph_lin + phi)) + off
                        ax.plot(ph_lin, fit, "-", lw=1.5, label="fit")
                        ax.legend(loc="best", fontsize=9,
                                  title=f"phi = {phi:.1f} deg")
                except Exception:
                    pass
                ax.set_title(_ro_title(r))
                ax.set_xlabel("measurement pi/2 phase (deg)")
                if r == 0:
                    ax.set_ylabel("P(excited)")

        # The 2D branch's shared colorbar already reserves space; tight_layout fights
        # it (and warns). Only tighten the 1D line-plot layout.
        if variant != self.VAR_B2D:
            self.canvas.fig.tight_layout()
        self.canvas.draw()


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


# ---------------------------------------------------------------------------
# Connection dialog — Pyro4 nameserver / RFSoC proxy / channel mapping
# ---------------------------------------------------------------------------


# Defaults for the nameserver address. Edit here or override in the dialog.
DEFAULT_NS_HOST = "192.168.1.104"  # matches socProxy.py
DEFAULT_NS_PORT = 8888
DEFAULT_SERVER_NAME = "myqick"


class ConnectionDialog(QDialog):
    """Pre-step dialog: nameserver lookup + RFSoC proxy + channel mapping.

    Acts as a thin client over Pyro4 and the RFSoC's ``soc.get_cfg()``: nothing
    is hardcoded, the user supplies the address. On accept, ``self.state`` holds
    a fully populated :class:`CalibState` (soc, soccfg, channel map, n_qubits).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("RFSoC connection — nameserver & channel map")
        self.resize(1000, 780)

        self.soc: Any = None
        self.soccfg: Any = None
        self.ns: Any = None
        self.state: Optional[CalibState] = None  # set on accept()

        # cached so we know how many channels are available for the dropdowns
        self.n_gens = 0
        self.n_readouts = 0

        # ---- Nameserver group ----
        ns_box = QGroupBox("Pyro4 nameserver")
        ns_form = QFormLayout()
        self.host_edit = QLineEdit(DEFAULT_NS_HOST)
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(DEFAULT_NS_PORT)
        self.list_btn = QPushButton("List nameserver entries")
        self.list_btn.clicked.connect(self.on_list_ns)
        self.ns_list = QListWidget()
        self.ns_list.itemSelectionChanged.connect(self.on_ns_item_selected)
        ns_form.addRow("Host:", self.host_edit)
        ns_form.addRow("Port:", self.port_spin)
        ns_form.addRow(self.list_btn)
        ns_form_widget = QWidget()
        ns_form_widget.setLayout(ns_form)
        ns_layout = QVBoxLayout(ns_box)
        ns_layout.addWidget(ns_form_widget)
        ns_layout.addWidget(QLabel("Registered names (click to select):"))
        ns_layout.addWidget(self.ns_list, 1)

        # ---- Proxy group ----
        proxy_box = QGroupBox("RFSoC proxy")
        proxy_form = QFormLayout(proxy_box)
        self.proxy_name_edit = QLineEdit(DEFAULT_SERVER_NAME)
        self.connect_btn = QPushButton("Connect to RFSoC")
        self.connect_btn.clicked.connect(self.on_connect)
        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.clicked.connect(self.on_disconnect)
        self.disconnect_btn.setEnabled(False)
        self.connection_status = QLabel("Not connected.")
        self.connection_status.setWordWrap(True)
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.connect_btn)
        btn_row.addWidget(self.disconnect_btn)
        btn_row.addStretch(1)
        btn_row_widget = QWidget(); btn_row_widget.setLayout(btn_row)
        proxy_form.addRow("Proxy name:", self.proxy_name_edit)
        proxy_form.addRow(btn_row_widget)
        proxy_form.addRow("Status:", self.connection_status)

        # ---- soccfg description ----
        cfg_box = QGroupBox("soccfg description (read-only)")
        cfg_layout = QVBoxLayout(cfg_box)
        self.cfg_view = QPlainTextEdit()
        self.cfg_view.setReadOnly(True)
        f = QFont(); f.setStyleHint(QFont.Monospace); f.setFamily("Consolas")
        self.cfg_view.setFont(f)
        cfg_layout.addWidget(self.cfg_view)

        # ---- Channels (editable; defaults from BaseConfig) ----
        # Dropdowns are pre-populated from DEFAULT_BASE_CONFIG so the dialog is
        # functional before the user connects (99% of users will accept the
        # defaults and click Continue). On connect, the combos are repopulated
        # from cfg_dict['gens'] with richer fs/type labels, with the previous
        # selection restored by data value via _select_combo_value.
        # NOTE: no ADC combo — for MUX firmware, ro_chs is derived from
        # n_qubits (first n MUXed ADC channels of the 8-channel readout).
        chan_box = QGroupBox("Channels (editable; defaults from BaseConfig)")
        chan_layout = QVBoxLayout(chan_box)

        shared_form = QFormLayout()
        self.res_ch_combo = QComboBox()
        self.qubit_ch_combo = QComboBox()
        shared_form.addRow("Readout DAC channel (shared, MUX):", self.res_ch_combo)
        shared_form.addRow("Qubit DAC channel (shared, MUX):",   self.qubit_ch_combo)
        shared_widget = QWidget(); shared_widget.setLayout(shared_form)
        chan_layout.addWidget(shared_widget)

        # Number of qubits = number of MUXed readouts to use.
        nq_row = QHBoxLayout()
        nq_row.addWidget(QLabel("Number of qubits (= MUXed readouts to enable):"))
        self.n_qubits_spin = QSpinBox()
        self.n_qubits_spin.setRange(1, len(DEFAULT_BASE_CONFIG["fast_flux_chs"]))
        self.n_qubits_spin.setValue(len(DEFAULT_BASE_CONFIG["fast_flux_chs"]))
        self.n_qubits_spin.valueChanged.connect(self.on_n_qubits_changed)
        nq_row.addWidget(self.n_qubits_spin)
        nq_row.addStretch(1)
        nq_widget = QWidget(); nq_widget.setLayout(nq_row)
        chan_layout.addWidget(nq_widget)

        # Per-qubit FF DAC channel table (one row per qubit, combo per row).
        self.qubit_table = QTableWidget(0, 2)
        self.qubit_table.setHorizontalHeaderLabels(["Qubit", "FF DAC channel"])
        self.qubit_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.qubit_table.verticalHeader().setVisible(False)
        chan_layout.addWidget(self.qubit_table, 1)

        # Derived ro_chs display (updates when n_qubits changes).
        self.ro_chs_label = QLabel()
        chan_layout.addWidget(self.ro_chs_label)

        chan_hint = QLabel(
            "Defaults come from BaseConfig (MUXInitialize.py). Firmware MUXes "
            "ADC channels 0–7; ro_chs is derived as the first n_qubits of "
            "those (not user-editable here). After connecting to the RFSoC, "
            "the combos refresh with fs/type labels from the live soccfg."
        )
        chan_hint.setWordWrap(True)
        chan_hint.setStyleSheet("color: #555;")
        chan_layout.addWidget(chan_hint)

        # Seed all combos from DEFAULT_BASE_CONFIG so the dialog is usable
        # before the user connects (no soccfg available yet).
        self._populate_channel_combos_from_defaults()

        # ---- Continue / Cancel ----
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        self.button_box.button(QDialogButtonBox.Ok).setText("Continue")
        self.button_box.button(QDialogButtonBox.Ok).setEnabled(False)
        self.button_box.accepted.connect(self.on_accept)
        self.button_box.rejected.connect(self.reject)

        # ---- Layout (left = ns/proxy, right = soccfg + channels) ----
        left = QVBoxLayout()
        left.addWidget(ns_box, 1)
        left.addWidget(proxy_box)
        left_w = QWidget(); left_w.setLayout(left)

        right = QVBoxLayout()
        right.addWidget(cfg_box, 1)
        right.addWidget(chan_box, 1)
        right_w = QWidget(); right_w.setLayout(right)

        splitter = QSplitter()
        splitter.addWidget(left_w)
        splitter.addWidget(right_w)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        outer = QVBoxLayout(self)
        outer.addWidget(splitter, 1)
        outer.addWidget(self.button_box)

        # initial empty table
        self.on_n_qubits_changed(self.n_qubits_spin.value())

    # ------------------ nameserver / proxy actions ------------------

    def _busy(self, msg: str):
        self.connection_status.setText(msg)
        QApplication.processEvents()

    def on_list_ns(self):
        host = self.host_edit.text().strip()
        port = int(self.port_spin.value())
        try:
            import Pyro4
        except ImportError as exc:
            QMessageBox.critical(self, "Pyro4 missing", str(exc))
            return
        Pyro4.config.SERIALIZER = "pickle"
        Pyro4.config.PICKLE_PROTOCOL_VERSION = 4
        self._busy(f"Locating nameserver at {host}:{port}...")
        try:
            ns = Pyro4.locateNS(host=host, port=port)
            entries = ns.list()
        except Exception as exc:
            QMessageBox.critical(self, "Nameserver error",
                                 f"Could not reach Pyro4 NS at {host}:{port}:\n{exc}")
            self.connection_status.setText("Nameserver unreachable.")
            return
        self.ns = ns
        self.ns_list.clear()
        # Sort with likely-soc names on top
        def rank(name: str) -> int:
            n = name.lower()
            if "qick" in n or "soc" in n:
                return 0
            if name.startswith("Pyro.NameServer"):
                return 2
            return 1
        for name in sorted(entries, key=lambda n: (rank(n), n)):
            uri = entries[name]
            item = QListWidgetItem(f"{name}    =>    {uri}")
            item.setData(Qt.UserRole, name)
            self.ns_list.addItem(item)
        self.connection_status.setText(
            f"Nameserver OK — {len(entries)} entries. Pick one and Connect."
        )

    def on_ns_item_selected(self):
        items = self.ns_list.selectedItems()
        if not items:
            return
        name = items[0].data(Qt.UserRole)
        if name and not name.startswith("Pyro.NameServer"):
            self.proxy_name_edit.setText(name)

    def on_connect(self):
        name = self.proxy_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing name",
                                "Enter a Pyro4 proxy name (or pick one from the list).")
            return
        if self.ns is None:
            # try to locate the nameserver implicitly
            self.on_list_ns()
            if self.ns is None:
                return
        try:
            import Pyro4
            from qick import QickConfig
        except ImportError as exc:
            QMessageBox.critical(self, "Import failed",
                                 f"Pyro4 / qick not importable: {exc}")
            return
        self._busy(f"Looking up '{name}'...")
        try:
            uri = self.ns.lookup(name)
            soc = Pyro4.Proxy(uri)
            cfg_dict = soc.get_cfg()
            soccfg = QickConfig(cfg_dict)
        except Exception as exc:
            QMessageBox.critical(self, "Connection failed",
                                 f"Could not connect to '{name}':\n{exc}")
            self.connection_status.setText("Connect failed.")
            return

        self.soc = soc
        self.soccfg = soccfg
        self.connection_status.setText(
            f"Connected to '{name}' at {self.host_edit.text()}:{self.port_spin.value()}."
        )
        try:
            self.cfg_view.setPlainText(soccfg.description())
        except Exception:
            self.cfg_view.setPlainText(repr(cfg_dict))
        self.connect_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(True)
        self.button_box.button(QDialogButtonBox.Ok).setEnabled(True)

        # Repopulate the channel combos from the live gens list, preserving
        # whatever the user had selected (data value) — typically the
        # BaseConfig defaults seeded at construction time.
        gens = cfg_dict.get("gens", []) or []
        readouts = cfg_dict.get("readouts", []) or []
        self.n_gens = len(gens)
        self.n_readouts = len(readouts)

        # Capture prior selections so we can restore them after clear/refill.
        prev_res = self.res_ch_combo.currentData()
        prev_qubit = self.qubit_ch_combo.currentData()
        prev_ff: list[int | None] = []
        for i in range(self.qubit_table.rowCount()):
            w = self.qubit_table.cellWidget(i, 1)
            prev_ff.append(w.currentData() if w is not None else None)

        def _gen_label(i: int, gen: dict) -> str:
            return f"{i}: {gen.get('type', '?')} fs={gen.get('fs', '?')} MHz"

        for combo in (self.res_ch_combo, self.qubit_ch_combo):
            combo.blockSignals(True)
            combo.clear()
            for i, gen in enumerate(gens):
                combo.addItem(_gen_label(i, gen), i)
            combo.blockSignals(False)

        # Restore prior selections; fall back to BaseConfig default if missing.
        self._select_combo_value(
            self.res_ch_combo,
            prev_res if prev_res is not None else DEFAULT_BASE_CONFIG["res_ch"],
        )
        self._select_combo_value(
            self.qubit_ch_combo,
            prev_qubit if prev_qubit is not None else DEFAULT_BASE_CONFIG["qubit_ch"],
        )

        # Rebuild FF rows (keeps prior per-row selection where possible).
        self._populate_qubit_table(prev_ff=prev_ff)
        # Refresh ro_chs label.
        self.on_n_qubits_changed(self.n_qubits_spin.value())

    def on_disconnect(self):
        # Pyro4 proxies clean up on garbage collection; just drop the references.
        self.soc = None
        self.soccfg = None
        self.cfg_view.clear()
        self.connection_status.setText("Disconnected.")
        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)
        self.button_box.button(QDialogButtonBox.Ok).setEnabled(False)

    def on_n_qubits_changed(self, n: int):
        # ro_chs = first n MUXed ADC channels of the 8-channel firmware.
        ro_chs = list(range(n))
        self.ro_chs_label.setText(f"<b>ro_chs (derived):</b> {ro_chs}")
        # Resize the per-qubit FF table to match n; preserve existing combos'
        # data values so changing n doesn't reset user picks for unchanged rows.
        prev_ff: list[int | None] = []
        for i in range(self.qubit_table.rowCount()):
            w = self.qubit_table.cellWidget(i, 1)
            prev_ff.append(w.currentData() if w is not None else None)
        self._populate_qubit_table(prev_ff=prev_ff)

    @staticmethod
    def _select_combo_value(combo: QComboBox, value):
        """Select the combo entry whose data() == value, if it exists."""
        if value is None:
            return
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _populate_channel_combos_from_defaults(self) -> None:
        """Seed res/qubit/per-qubit FF combos from DEFAULT_BASE_CONFIG.

        Used at dialog construction (no soccfg yet) and as a fallback path.
        Items carry the int channel as their data so currentData() works
        identically before and after a connect (where the labels become
        richer fs/type strings but the data values stay the same).
        """
        default_ff_chs = list(DEFAULT_BASE_CONFIG["fast_flux_chs"])
        # The two shared combos: list every plausible channel index. We don't
        # have a soccfg yet, so use the union of BaseConfig's res/qubit/FF
        # channels — enough to surface the default and any sibling channel
        # the user might want to pick before connecting.
        candidate_chs = sorted(set(
            [int(DEFAULT_BASE_CONFIG["res_ch"]),
             int(DEFAULT_BASE_CONFIG["qubit_ch"])]
            + [int(c) for c in default_ff_chs]
        ))
        for combo in (self.res_ch_combo, self.qubit_ch_combo):
            combo.blockSignals(True)
            combo.clear()
            for ch in candidate_chs:
                combo.addItem(f"ch {ch} (BaseConfig default)", ch)
            combo.blockSignals(False)
        self._select_combo_value(self.res_ch_combo, int(DEFAULT_BASE_CONFIG["res_ch"]))
        self._select_combo_value(self.qubit_ch_combo, int(DEFAULT_BASE_CONFIG["qubit_ch"]))
        # Build the FF rows for the initial n_qubits.
        self._populate_qubit_table(prev_ff=None)

    def _populate_qubit_table(self, prev_ff: Optional[list] = None) -> None:
        """(Re)build the per-qubit FF combo table to match n_qubits_spin.

        Each row's combo is populated from the live gens list when connected,
        else from DEFAULT_BASE_CONFIG['fast_flux_chs']. `prev_ff[i]` (data
        value, int or None) is used to restore row i's selection; if missing,
        the default per-qubit FF channel from BaseConfig is used.
        """
        n = int(self.n_qubits_spin.value())
        default_ff_chs = list(DEFAULT_BASE_CONFIG["fast_flux_chs"])
        # If we have a live cfg with gens, drive the combos from it.
        if self.soccfg is not None and self.n_gens > 0:
            try:
                gens = self.soc.get_cfg().get("gens", []) or []
            except Exception:
                gens = []
        else:
            gens = []

        self.qubit_table.setRowCount(n)
        for i in range(n):
            label_item = QTableWidgetItem(f"Q{i + 1}")
            label_item.setFlags(Qt.ItemIsEnabled)
            self.qubit_table.setItem(i, 0, label_item)
            existing = self.qubit_table.cellWidget(i, 1)
            combo = existing if isinstance(existing, QComboBox) else QComboBox()
            if existing is None:
                self.qubit_table.setCellWidget(i, 1, combo)
            combo.blockSignals(True)
            combo.clear()
            if gens:
                for j, gen in enumerate(gens):
                    combo.addItem(
                        f"{j}: {gen.get('type', '?')} fs={gen.get('fs', '?')} MHz",
                        j,
                    )
            else:
                # Pre-connect: list BaseConfig's FF channels as candidates so
                # the user can change a mapping before connecting if needed.
                for ch in sorted(set(int(c) for c in default_ff_chs)):
                    combo.addItem(f"ch {ch} (BaseConfig default)", ch)
            combo.blockSignals(False)
            # Restore prior data, else fall back to BaseConfig default for Q_i.
            prev_val = prev_ff[i] if (prev_ff is not None and i < len(prev_ff)) else None
            if prev_val is not None:
                self._select_combo_value(combo, int(prev_val))
            else:
                default_ch = int(default_ff_chs[i]) if i < len(default_ff_chs) else i
                self._select_combo_value(combo, default_ch)

    # ------------------ accept ------------------

    def on_accept(self):
        if self.soc is None or self.soccfg is None:
            QMessageBox.warning(self, "Not connected",
                                "Connect to the RFSoC before continuing.")
            return

        n_qubits = int(self.n_qubits_spin.value())

        # Read per-qubit FF channels from the table combos.
        ff_channels: list[int] = []
        for i in range(n_qubits):
            combo = self.qubit_table.cellWidget(i, 1)
            if combo is None or combo.currentData() is None:
                QMessageBox.warning(
                    self, "Missing FF channel",
                    f"Q{i + 1} has no FF DAC channel selected.",
                )
                return
            ff_channels.append(int(combo.currentData()))

        # Warn (don't block) on duplicate FF channel assignments — the
        # underlying firmware will happily accept it, but it's almost always
        # a mistake.
        if len(set(ff_channels)) != len(ff_channels):
            res = QMessageBox.question(
                self, "Duplicate FF channels",
                "Two or more qubits are assigned to the same FF DAC channel. "
                "Continue anyway?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if res != QMessageBox.Yes:
                return

        # Start from DEFAULT_BASE_CONFIG so non-channel fields (mixer_freq,
        # nqz, relax_delay, ...) flow through, then override the channels from
        # the dialog selections.
        base = copy.deepcopy(DEFAULT_BASE_CONFIG)
        base["res_ch"] = int(self.res_ch_combo.currentData())
        base["qubit_ch"] = int(self.qubit_ch_combo.currentData())
        # ro_chs is derived from n_qubits (MUX firmware), not user-editable.
        base["ro_chs"] = list(range(n_qubits))
        base["fast_flux_chs"] = list(ff_channels)

        self.state = CalibState(
            base_config=base,
            ff_qubits=make_default_ff_qubits(n_qubits, ff_channels),
            n_qubits=n_qubits,
            soc=self.soc,
            soccfg=self.soccfg,
            ns_host=self.host_edit.text().strip(),
            ns_port=int(self.port_spin.value()),
            server_name=self.proxy_name_edit.text().strip(),
        )
        self.accept()


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------


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
        self.exptui_demo_tab = ExptUIDemoTab(self.state, lambda: self)
        self.tabs.addTab(self.exptui_demo_tab, self.exptui_demo_tab.name)
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


if __name__ == "__main__":
    main()
