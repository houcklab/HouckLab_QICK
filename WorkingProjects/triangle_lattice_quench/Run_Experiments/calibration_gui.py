"""
Interactive calibration wizard for the triangle-lattice quench project.

Walks a user through the canonical single-qubit / single-resonator calibration:
    Transmission -> Spec slice -> Amplitude Rabi -> Single-shot -> T1 -> T2R

Each stage is a tab with editable parameters, an inline matplotlib plot, and an
"Apply" button that pushes the result into the in-memory Qubit_Parameters dict.
The dict can be loaded from / saved to a JSON file from the toolbar.

Launch from the repo root:

    cd D:/Agentic_QSim_Measurement
    python -m WorkingProjects.triangle_lattice_quench.Run_Experiments.calibration_gui

The first time you run a stage, click "Connect to RFSoC" first. The GUI lazy-
imports socProxy so it won't try to talk to the nameserver until you ask.
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
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QSpinBox, QStatusBar, QTabWidget, QVBoxLayout, QWidget,
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

DEFAULT_FF_QUBITS: dict = {
    str(i + 1): {"channel": i, "delay_time": 0.0} for i in range(8)
}

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

# Seed Qubit_Parameters: 8 qubits with placeholder freqs/gains. Real values
# come from loading a JSON setpoint file via the toolbar.
DEFAULT_QUBIT_PARAMETERS: dict = {
    str(i + 1): {
        "Readout": {
            "Frequency": 7000.0 + 50 * i,
            "Gain": 5000,
            "FF_Gains": [0] * 8,
            "Readout_Time": 2.5,
            "ADC_Offset": 0.75,
            "cavmin": True,
        },
        "Qubit": {"Frequency": 4000.0, "sigma": 0.03, "Gain": 5000},
        "Pulse_FF": [0] * 8,
    }
    for i in range(8)
}


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
    soc: Any = None                  # set by Connect button
    soccfg: Any = None
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
        for i, ff in enumerate(("1", "2", "3", "4", "5", "6", "7", "8")):
            ff_qubits[ff].update({
                "Gain_Readout": readout_ff[i],
                "Gain_Expt": 0,
                "Gain_Pulse": pulse_ff[i],
                "Gain_BS": 0,
                "ramp_initial_gain": pulse_ff[i],
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
# Main window
# ---------------------------------------------------------------------------


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.state = CalibState()
        self.setWindowTitle("Triangle-Lattice Calibration Wizard")
        self.resize(1400, 800)

        # Toolbar (top row of controls)
        top = QWidget()
        top_layout = QHBoxLayout(top)

        self.connect_btn = QPushButton("Connect to RFSoC")
        self.connect_btn.clicked.connect(self.on_connect)
        top_layout.addWidget(self.connect_btn)

        self.qubit_combo = QComboBox()
        self.qubit_combo.addItems([f"Q{i+1}" for i in range(8)])
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
        self.status.showMessage(
            "Ready. Connect to the RFSoC and load a Qubit_Parameters JSON to begin."
        )
        self.refresh_qubit_summary()

    # --- handlers ---

    def on_connect(self):
        if self.state.is_connected():
            QMessageBox.information(self, "Already connected", "Already connected.")
            return
        try:
            from WorkingProjects.Triangle_Lattice_tProcV2.socProxy import makeProxy
            soc, soccfg = makeProxy()
            self.state.soc = soc
            self.state.soccfg = soccfg
        except Exception as exc:
            QMessageBox.critical(self, "Connection failed",
                                 f"makeProxy() failed: {exc}\n\n"
                                 f"Check that the RFSoC nameserver is reachable "
                                 f"(see socProxy.py for the IP).")
            return
        self.conn_label.setText("RFSoC: connected")
        self.connect_btn.setEnabled(False)
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
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
