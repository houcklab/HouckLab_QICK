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

import copy
import json
import sys
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

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit,
    QPushButton, QSpinBox, QSplitter, QStatusBar, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)


# ---------------------------------------------------------------------------
# Defaults mirroring MUXInitialize.py — kept inline so that importing this
# module does NOT trigger socProxy.makeProxy() at module load.
# ---------------------------------------------------------------------------

DEFAULT_OUTER_FOLDER = r"Z:\QSimMeasurements\Measurements\8QV1_Triangle_Lattice\\"

DEFAULT_BASE_CONFIG: dict = {
    "res_ch": 8,
    "qubit_ch": 9,
    "ro_chs": [0],
    "fast_flux_chs": [0, 1, 2, 3, 4, 5, 6, 7],
    "res_nqz": 1,
    "qubit_nqz": 2,
    "mixer_freq": -1750,
    "qubit_mixer_freq": 4000,
    "relax_delay": 200,
    "res_phase": 0,
    "res_length": 10,
    "res_LO": 9000,
    "qubit_LO": 0,
}

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
        str(i + 1): {"channel": int(channels[i]), "delay_time": 0.0}
        for i in range(n_qubits)
    }


def make_default_qubit_parameters(n_qubits: int = 8) -> dict:
    """Seed Qubit_Parameters dict with placeholder per-qubit values.

    Real values come from loading a JSON setpoint file via the toolbar or by
    running the calibration tabs.
    """
    return {
        str(i + 1): {
            "Readout": {
                "Frequency": 7000.0 + 50 * i,
                "Gain": 5000,
                "FF_Gains": [0] * n_qubits,
                "Readout_Time": 2.5,
                "ADC_Offset": 0.75,
                "cavmin": True,
            },
            "Qubit": {"Frequency": 4000.0, "sigma": 0.03, "Gain": 5000},
            "Pulse_FF": [0] * n_qubits,
        }
        for i in range(n_qubits)
    }


DEFAULT_FF_QUBITS: dict = make_default_ff_qubits(8)

# Sensible per-stage defaults distilled from Fast_calib.py
STAGE_DEFAULTS: dict[str, dict] = {
    "transmission": {
        "TransSpan": 1.5, "TransNumPoints": 91,
        "readout_length": 2.5, "cav_relax_delay": 10,
        "reps": 250,
    },
    "spec_coarse": {
        "qubit_gain": 500, "SpecSpan": 100.0, "SpecNumPoints": 71,
        "Gauss": False, "sigma": 0.07, "Gauss_gain": 3350,
        "qubit_length": 5.0, "reps": 200, "rounds": 1, "relax_delay": 100,
    },
    "spec_fine": {
        "qubit_gain": 50, "SpecSpan": 10.0, "SpecNumPoints": 81,
        "Gauss": False, "sigma": 0.05, "Gauss_gain": 1200,
        "qubit_length": 5.0, "reps": 250, "rounds": 1, "relax_delay": 100,
    },
    "rabi": {
        "max_gain": 12000, "expts": 31, "reps": 900,
        "sigma": 0.05, "relax_delay": 100, "rounds": 1,
    },
    "singleshot": {
        "Shots": 5000, "relax_delay": 200, "number_of_pulses": 1,
        "sigma": 0.05, "rounds": 1,
    },
    "t1": {
        "expts": 51, "stop_delay_us": 80.0, "reps": 200,
        "sigma": 0.05, "relax_delay": 250, "rounds": 1,
    },
    "t2r": {
        "expts": 81, "stop_delay_us": 5.0, "reps": 200,
        "sigma": 0.05, "relax_delay": 250, "rounds": 1,
        "freq_shift": 1.0, "phase_shift_cycles": 0,
    },
}

DEFAULT_QUBIT_PARAMETERS: dict = make_default_qubit_parameters(8)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class CalibState:
    """Mutable session state shared between tabs."""
    base_config: dict = field(default_factory=lambda: copy.deepcopy(DEFAULT_BASE_CONFIG))
    ff_qubits: dict = field(default_factory=lambda: copy.deepcopy(DEFAULT_FF_QUBITS))
    qubit_parameters: dict = field(default_factory=lambda: copy.deepcopy(DEFAULT_QUBIT_PARAMETERS))
    outer_folder: str = DEFAULT_OUTER_FOLDER
    target_qubit: int = 1            # the qubit currently being calibrated
    n_qubits: int = 8                # number of qubits being calibrated
    soc: Any = None                  # set by ConnectionDialog
    soccfg: Any = None
    ns_host: str = ""                # remembered for the status bar / reconnect
    ns_port: int = 0
    server_name: str = ""
    last_results: dict[str, dict] = field(default_factory=dict)

    def is_connected(self) -> bool:
        return self.soc is not None and self.soccfg is not None

    def build_single_qubit_config(self, stage_overrides: dict) -> dict:
        """Translate Qubit_Parameters[target] -> the flat cfg dict the experiments expect.

        Mirrors UPDATE_CONFIG_function.update_config but for a single-readout, single-pulse
        target (which is the case for these basic per-qubit calibrations).
        """
        Q = str(self.target_qubit)
        qp = self.qubit_parameters[Q]
        bc = self.base_config

        # readout side (single readout)
        res_freq_actual = qp["Readout"]["Frequency"]
        res_freq_if = res_freq_actual - bc["res_LO"]
        res_gain_norm = qp["Readout"]["Gain"] / 32766.0  # gain is single-qubit so no *N rescale

        # qubit side
        qubit_freq = qp["Qubit"]["Frequency"] - bc["qubit_LO"]
        qubit_gain_norm = qp["Qubit"]["Gain"] / 32766.0
        sigma = qp["Qubit"]["sigma"]

        # FF map: take the qubit's Pulse_FF as both pulse and "ramp_initial" gains.
        # User can override by editing the Qubit_Parameters JSON.
        ff_qubits = copy.deepcopy(self.ff_qubits)
        pulse_ff = qp["Pulse_FF"]
        readout_ff = qp["Readout"]["FF_Gains"]
        ff_keys = sorted(ff_qubits.keys(), key=int)
        for i, ff in enumerate(ff_keys):
            ff_qubits[ff].update({
                "Gain_Readout": readout_ff[i] if i < len(readout_ff) else 0,
                "Gain_Expt": 0,
                "Gain_Pulse": pulse_ff[i] if i < len(pulse_ff) else 0,
                "Gain_BS": 0,
                "ramp_initial_gain": pulse_ff[i] if i < len(pulse_ff) else 0,
            })

        cfg = {
            **bc,
            "res_freqs": [res_freq_if],
            "res_gains": [res_gain_norm],
            "readout_lengths": [qp["Readout"]["Readout_Time"]],
            "adc_trig_delays": [qp["Readout"]["ADC_Offset"]],
            "qubit_freqs": [qubit_freq],
            "qubit_gains": [qubit_gain_norm],
            "sigma": sigma,
            "FF_Qubits": ff_qubits,
            "Qubit_Readout_List": [self.target_qubit],
            "ro_chs": [0],
        }
        cfg.update(stage_overrides)
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


# ---------------------------------------------------------------------------
# Worker thread — runs an experiment off the GUI thread
# ---------------------------------------------------------------------------


class ExperimentWorker(QThread):
    finished_ok = pyqtSignal(object, object)   # (experiment instance, data dict)
    failed = pyqtSignal(str)

    def __init__(self, factory: Callable[[], Any]):
        super().__init__()
        self.factory = factory

    def run(self):
        try:
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

    def render(self, expt, data):
        """Default render: delegate to expt.display(ax=self.canvas.ax). Override
        for experiments whose display() does not accept ax= (e.g. SingleShot)."""
        expt.display(data, ax=self.canvas.ax, **self.display_kwargs())

    def on_success(self, expt, data) -> str:
        """Called on the GUI thread after acquire(); returns a text summary."""
        return "Done."

    def on_apply(self, expt, data):
        """Push results into state.qubit_parameters."""
        pass

    # --- common machinery ---
    def _build_cfg(self) -> dict:
        return self.state.build_single_qubit_config(self.param_form.values())

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

        def factory():
            return self.make_experiment(cfg)

        self.worker = ExperimentWorker(factory)
        self.worker.finished_ok.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

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
        try:
            self.on_apply(self.expt, self.data)
            QMessageBox.information(self, "Applied",
                                    "Updated in-memory Qubit_Parameters. "
                                    "Use Save to persist.")
            self.get_main().refresh_qubit_summary()
        except Exception as exc:
            QMessageBox.critical(self, "Apply failed", str(exc))


# ----- concrete stages ------------------------------------------------------


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
        from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mTransmissionFFMUX import CavitySpecFFMUX
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
        f_actual = expt.peakFreq_min + expt.cfg["res_LO"]
        self.state.qubit_parameters[Q]["Readout"]["Frequency"] = float(f_actual)


class SpecSliceTab(StageTab):
    name = "QubitSpec"

    def param_spec(self):
        d = STAGE_DEFAULTS["spec_coarse"]
        return [
            ("qubit_gain",     "CW qubit gain (DAC)",  "int",   d["qubit_gain"]),
            ("SpecSpan",       "Span around f_q (MHz)","float", d["SpecSpan"]),
            ("SpecNumPoints",  "Num points",           "int",   d["SpecNumPoints"]),
            ("Gauss",          "Gauss pulse?",         "bool",  d["Gauss"]),
            ("sigma",          "Gauss sigma (us)",     "float", d["sigma"]),
            ("Gauss_gain",     "Gauss gain",           "int",   d["Gauss_gain"]),
            ("qubit_length",   "CW length (us)",       "float", d["qubit_length"]),
            ("reps",           "Repetitions",          "int",   d["reps"]),
            ("rounds",         "Rounds",               "int",   d["rounds"]),
            ("relax_delay",    "Relax delay (us)",     "float", d["relax_delay"]),
        ]

    def make_experiment(self, cfg):
        from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSpecSliceFFMUX import QubitSpecSliceFFMUX
        return QubitSpecSliceFFMUX(
            soc=self.state.soc, soccfg=self.state.soccfg,
            path="QubitSpec", outerFolder=self.state.outer_folder, cfg=cfg,
        )

    def on_success(self, expt, data):
        return f"f_q = {expt.qubitFreq:.3f} MHz"

    def on_apply(self, expt, data):
        Q = str(self.state.target_qubit)
        self.state.qubit_parameters[Q]["Qubit"]["Frequency"] = float(expt.qubitFreq)


class AmplitudeRabiTab(StageTab):
    name = "AmplitudeRabi"

    def param_spec(self):
        d = STAGE_DEFAULTS["rabi"]
        return [
            ("max_gain",    "Max gain (DAC)",      "int",   d["max_gain"]),
            ("expts",       "Num gain points",     "int",   d["expts"]),
            ("reps",        "Repetitions",         "int",   d["reps"]),
            ("sigma",       "Gauss sigma (us)",    "float", d["sigma"]),
            ("relax_delay", "Relax delay (us)",    "float", d["relax_delay"]),
            ("rounds",      "Rounds",              "int",   d["rounds"]),
        ]

    def make_experiment(self, cfg):
        from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mAmplitudeRabiFFMUX import AmplitudeRabiFFMUX
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
        self.state.qubit_parameters[Q]["Qubit"]["Gain"] = int(pi_gain)
        self.state.qubit_parameters[Q]["Qubit"]["sigma"] = expt.cfg["sigma"]


class SingleShotTab(StageTab):
    name = "SingleShot"

    def param_spec(self):
        d = STAGE_DEFAULTS["singleshot"]
        return [
            ("Shots",            "Shots",              "int",   d["Shots"]),
            ("relax_delay",      "Relax delay (us)",   "float", d["relax_delay"]),
            ("number_of_pulses", "Number of pi pulses","int",   d["number_of_pulses"]),
            ("sigma",            "Gauss sigma (us)",   "float", d["sigma"]),
            ("rounds",           "Rounds",             "int",   d["rounds"]),
        ]

    def make_experiment(self, cfg):
        from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import SingleShotFFMUX
        return SingleShotFFMUX(
            soc=self.state.soc, soccfg=self.state.soccfg,
            path="SingleShot", outerFolder=self.state.outer_folder, cfg=cfg,
        )

    def render(self, expt, data):
        # SingleShot.display() does not accept an `ax=` kwarg (it relies on
        # hist_process making its own figure). Plot the rotated IQ scatter
        # ourselves so it lands in the embedded canvas.
        import numpy as np
        Q = self.state.target_qubit
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

        ax = self.canvas.ax
        ax.scatter(ig_r, qg_r, s=3, alpha=0.4, label="ground", color="tab:blue")
        ax.scatter(ie_r, qe_r, s=3, alpha=0.4, label="excited", color="tab:red")
        ax.axvline(threshold, color="black", linestyle="--",
                   label=f"threshold = {threshold:.4f}")
        ax.set_xlabel("I (rotated)")
        ax.set_ylabel("Q (rotated)")
        ax.set_title(f"Q{Q} single-shot — F = {fid:.3f}, angle = {angle:.3f} rad")
        ax.legend()
        ax.set_aspect("equal", adjustable="datalim")

    def on_success(self, expt, data):
        fid = data["data"]["fid"][0]
        ang = data["data"]["angle"][0]
        thr = data["data"]["threshold"][0]
        return f"F = {fid:.3f}, angle = {ang:.3f} rad, thr = {thr:.4f}"

    def on_apply(self, expt, data):
        # Single-shot calibration doesn't update Qubit_Parameters directly; the
        # angle/threshold are session-state used by downstream experiments. We
        # stash them on the state so other tabs can read them, and write them
        # into the qubit's Readout dict for persistence.
        Q = str(self.state.target_qubit)
        self.state.qubit_parameters[Q]["Readout"]["angle"] = float(data["data"]["angle"][0])
        self.state.qubit_parameters[Q]["Readout"]["threshold"] = float(data["data"]["threshold"][0])
        self.state.qubit_parameters[Q]["Readout"]["fidelity"] = float(data["data"]["fid"][0])


class T1Tab(StageTab):
    name = "T1"

    def param_spec(self):
        d = STAGE_DEFAULTS["t1"]
        return [
            ("expts",         "Num delay points",  "int",   d["expts"]),
            ("stop_delay_us", "Max delay (us)",    "float", d["stop_delay_us"]),
            ("reps",          "Repetitions",       "int",   d["reps"]),
            ("sigma",         "Gauss sigma (us)",  "float", d["sigma"]),
            ("relax_delay",   "Relax delay (us)",  "float", d["relax_delay"]),
            ("rounds",        "Rounds",            "int",   d["rounds"]),
        ]

    def make_experiment(self, cfg):
        from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mT1MUX import T1MUX
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

    def on_apply(self, expt, data):
        Q = str(self.state.target_qubit)
        T1 = getattr(expt, "T1", None)
        if T1 is None:
            raise RuntimeError("No T1 fit to apply.")
        self.state.qubit_parameters[Q]["Qubit"]["T1"] = float(T1)


class T2RTab(StageTab):
    name = "T2R"

    def param_spec(self):
        d = STAGE_DEFAULTS["t2r"]
        return [
            ("expts",              "Num delay points",     "int",   d["expts"]),
            ("stop_delay_us",      "Max delay (us)",       "float", d["stop_delay_us"]),
            ("reps",               "Repetitions",          "int",   d["reps"]),
            ("sigma",              "Gauss sigma (us)",     "float", d["sigma"]),
            ("relax_delay",        "Relax delay (us)",     "float", d["relax_delay"]),
            ("rounds",             "Rounds",               "int",   d["rounds"]),
            ("freq_shift",         "Detuning (MHz)",       "float", d["freq_shift"]),
            ("phase_shift_cycles", "Phase shift cycles",   "int",   d["phase_shift_cycles"]),
        ]

    def make_experiment(self, cfg):
        from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mT2RMUX import T2RMUX
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

    def on_apply(self, expt, data):
        Q = str(self.state.target_qubit)
        T2 = getattr(expt, "T2", None)
        if T2 is None:
            raise RuntimeError("No T2R fit to apply.")
        self.state.qubit_parameters[Q]["Qubit"]["T2R"] = float(T2)


# ---------------------------------------------------------------------------
# Connection dialog — Pyro4 nameserver / RFSoC proxy / channel mapping
# ---------------------------------------------------------------------------


# Defaults for the nameserver address. Edit here or override in the dialog.
DEFAULT_NS_HOST = "192.168.1.114"
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

        # ---- Channel mapping ----
        chan_box = QGroupBox("Channel assignment")
        chan_layout = QVBoxLayout(chan_box)

        shared_form = QFormLayout()
        self.res_ch_combo = QComboBox()
        self.qubit_ch_combo = QComboBox()
        self.adc_ch_combo = QComboBox()
        shared_form.addRow("Readout DAC channel (shared, MUX):", self.res_ch_combo)
        shared_form.addRow("Qubit DAC channel (shared, MUX):", self.qubit_ch_combo)
        shared_form.addRow("ADC / readout channel:", self.adc_ch_combo)
        shared_widget = QWidget(); shared_widget.setLayout(shared_form)
        chan_layout.addWidget(shared_widget)

        nq_row = QHBoxLayout()
        nq_row.addWidget(QLabel("Number of qubits:"))
        self.n_qubits_spin = QSpinBox()
        self.n_qubits_spin.setRange(1, 32)
        self.n_qubits_spin.setValue(8)
        self.n_qubits_spin.valueChanged.connect(self.on_n_qubits_changed)
        nq_row.addWidget(self.n_qubits_spin)
        nq_row.addStretch(1)
        nq_widget = QWidget(); nq_widget.setLayout(nq_row)
        chan_layout.addWidget(nq_widget)

        self.qubit_table = QTableWidget(0, 2)
        self.qubit_table.setHorizontalHeaderLabels(["Qubit", "FF DAC channel"])
        self.qubit_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.qubit_table.verticalHeader().setVisible(False)
        chan_layout.addWidget(self.qubit_table, 1)

        chan_hint = QLabel(
            "Tip: the underlying experiment classes are MUX — all qubits share "
            "one Readout DAC, one Qubit DAC, and one ADC. Each qubit has its own "
            "FF DAC for slow flux pulses."
        )
        chan_hint.setWordWrap(True)
        chan_hint.setStyleSheet("color: #555;")
        chan_layout.addWidget(chan_hint)

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

        # Populate channel dropdowns from the raw cfg dict (robust across QickConfig versions)
        gens = cfg_dict.get("gens", []) or []
        readouts = cfg_dict.get("readouts", []) or []
        self.n_gens = len(gens)
        self.n_readouts = len(readouts)

        self.res_ch_combo.clear(); self.qubit_ch_combo.clear(); self.adc_ch_combo.clear()
        for i, gen in enumerate(gens):
            label = f"{i}: {gen.get('type', '?')} fs={gen.get('fs', '?')} MHz"
            self.res_ch_combo.addItem(label, i)
            self.qubit_ch_combo.addItem(label, i)
        for i, ro in enumerate(readouts):
            label = f"{i}: {ro.get('type', '?')} fs={ro.get('fs', '?')} MHz"
            self.adc_ch_combo.addItem(label, i)

        # Sensible defaults from the existing triangle-lattice config
        self._select_combo_value(self.res_ch_combo, DEFAULT_BASE_CONFIG["res_ch"])
        self._select_combo_value(self.qubit_ch_combo, DEFAULT_BASE_CONFIG["qubit_ch"])
        self._select_combo_value(self.adc_ch_combo, DEFAULT_BASE_CONFIG["ro_chs"][0])

        # Refresh the per-qubit FF dropdowns now that we know channel count.
        self.on_n_qubits_changed(self.n_qubits_spin.value())

    @staticmethod
    def _select_combo_value(combo: QComboBox, value: int):
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

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
        self.qubit_table.setRowCount(n)
        for i in range(n):
            label_item = QTableWidgetItem(f"Q{i + 1}")
            label_item.setFlags(Qt.ItemIsEnabled)
            self.qubit_table.setItem(i, 0, label_item)
            existing = self.qubit_table.cellWidget(i, 1)
            if existing is None:
                combo = QComboBox()
                self.qubit_table.setCellWidget(i, 1, combo)
            else:
                combo = existing
            combo.blockSignals(True)
            combo.clear()
            if self.n_gens > 0:
                for j in range(self.n_gens):
                    combo.addItem(f"gen {j}", j)
                default_ch = i if i < self.n_gens else 0
                idx = combo.findData(default_ch)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            else:
                # no soccfg yet — let user type-in (will be re-populated on connect)
                combo.addItem("(connect first)", 0)
            combo.blockSignals(False)

    # ------------------ accept ------------------

    def on_accept(self):
        if self.soc is None or self.soccfg is None:
            QMessageBox.warning(self, "Not connected",
                                "Connect to the RFSoC before continuing.")
            return

        n_qubits = int(self.n_qubits_spin.value())
        ff_channels: list[int] = []
        for i in range(n_qubits):
            combo = self.qubit_table.cellWidget(i, 1)
            ff_channels.append(int(combo.currentData()))

        if len(set(ff_channels)) != len(ff_channels):
            res = QMessageBox.question(
                self, "Duplicate FF channels",
                "Two or more qubits are assigned to the same FF DAC channel. "
                "Continue anyway?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if res != QMessageBox.Yes:
                return

        base = copy.deepcopy(DEFAULT_BASE_CONFIG)
        base["res_ch"] = int(self.res_ch_combo.currentData())
        base["qubit_ch"] = int(self.qubit_ch_combo.currentData())
        base["ro_chs"] = [int(self.adc_ch_combo.currentData())]
        base["fast_flux_chs"] = list(ff_channels)

        self.state = CalibState(
            base_config=base,
            ff_qubits=make_default_ff_qubits(n_qubits, ff_channels),
            qubit_parameters=make_default_qubit_parameters(n_qubits),
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

        # Toolbar (top row of controls)
        top = QWidget()
        top_layout = QHBoxLayout(top)

        self.connect_btn = QPushButton("Connection info...")
        self.connect_btn.clicked.connect(self.on_connect)
        top_layout.addWidget(self.connect_btn)

        self.qubit_combo = QComboBox()
        self.qubit_combo.addItems([f"Q{i+1}" for i in range(self.state.n_qubits)])
        self.qubit_combo.currentIndexChanged.connect(self.on_qubit_changed)
        top_layout.addWidget(QLabel("Target qubit:"))
        top_layout.addWidget(self.qubit_combo)

        self.outer_edit = QLineEdit(self.state.outer_folder)
        self.outer_edit.editingFinished.connect(
            lambda: setattr(self.state, "outer_folder", self.outer_edit.text())
        )
        top_layout.addWidget(QLabel("outerFolder:"))
        top_layout.addWidget(self.outer_edit, 1)

        self.load_btn = QPushButton("Load Qubit_Parameters JSON")
        self.load_btn.clicked.connect(self.on_load)
        self.save_btn = QPushButton("Save Qubit_Parameters JSON")
        self.save_btn.clicked.connect(self.on_save)
        top_layout.addWidget(self.load_btn)
        top_layout.addWidget(self.save_btn)

        # Connection / qubit-summary line
        summary = QWidget()
        summary_layout = QHBoxLayout(summary)
        self.conn_label = QLabel("RFSoC: not connected")
        self.qubit_label = QLabel("")
        f = QFont(); f.setStyleHint(QFont.Monospace); f.setFamily("Consolas")
        self.qubit_label.setFont(f)
        summary_layout.addWidget(self.conn_label)
        summary_layout.addWidget(self.qubit_label, 1)

        # Tabs
        self.tabs = QTabWidget()
        self.stages: list[StageTab] = [
            TransmissionTab(self.state, lambda: self),
            SpecSliceTab(self.state, lambda: self),
            AmplitudeRabiTab(self.state, lambda: self),
            SingleShotTab(self.state, lambda: self),
            T1Tab(self.state, lambda: self),
            T2RTab(self.state, lambda: self),
        ]
        for s in self.stages:
            self.tabs.addTab(s, s.name)

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
        self.refresh_qubit_summary()

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
        # No connection yet — open the dialog.
        dlg = ConnectionDialog(self)
        if dlg.exec_() != QDialog.Accepted or dlg.state is None:
            return
        # Replace state and rebuild qubit combo for the new n_qubits.
        self.state = dlg.state
        self.qubit_combo.blockSignals(True)
        self.qubit_combo.clear()
        self.qubit_combo.addItems([f"Q{i+1}" for i in range(self.state.n_qubits)])
        self.qubit_combo.blockSignals(False)
        for stage in self.stages:
            stage.state = self.state
        self.conn_label.setText(
            f"RFSoC: connected ({self.state.server_name} @ "
            f"{self.state.ns_host}:{self.state.ns_port})"
        )
        self.outer_edit.setText(self.state.outer_folder)
        self.refresh_qubit_summary()
        self.status.showMessage("Connected.", 3000)

    def on_qubit_changed(self, idx: int):
        self.state.target_qubit = idx + 1
        self.refresh_qubit_summary()

    def on_load(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Qubit_Parameters JSON", "", "JSON (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "r") as fh:
                qp = json.load(fh)
            # accept either {"Qubit_Parameters": {...}} or the dict directly
            if "Qubit_Parameters" in qp and isinstance(qp["Qubit_Parameters"], dict):
                qp = qp["Qubit_Parameters"]
            for k in qp:
                self.state.qubit_parameters[str(k)] = qp[k]
            self.status.showMessage(f"Loaded {path}", 3000)
            self.refresh_qubit_summary()
        except Exception as exc:
            QMessageBox.critical(self, "Load failed", str(exc))

    def on_save(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Qubit_Parameters JSON", "Qubit_Parameters.json",
            "JSON (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "w") as fh:
                json.dump({"Qubit_Parameters": self.state.qubit_parameters},
                          fh, indent=2)
            self.status.showMessage(f"Saved to {path}", 3000)
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

    def refresh_qubit_summary(self):
        Q = str(self.state.target_qubit)
        qp = self.state.qubit_parameters.get(Q, {})
        ro = qp.get("Readout", {})
        qb = qp.get("Qubit", {})
        line = (
            f"Q{Q}: f_r={ro.get('Frequency', '?')} MHz, "
            f"r_gain={ro.get('Gain', '?')}, "
            f"f_q={qb.get('Frequency', '?')} MHz, "
            f"q_gain={qb.get('Gain', '?')}, "
            f"sigma={qb.get('sigma', '?')} us, "
            f"T1={qb.get('T1', '-')}, T2R={qb.get('T2R', '-')}, "
            f"F={ro.get('fidelity', '-')}"
        )
        self.qubit_label.setText(line)


def main():
    app = QApplication(sys.argv)

    # Launch the connection / channel-mapping dialog first.
    dlg = ConnectionDialog()
    if dlg.exec_() != QDialog.Accepted or dlg.state is None:
        sys.exit(0)

    win = MainWindow(state=dlg.state)
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
