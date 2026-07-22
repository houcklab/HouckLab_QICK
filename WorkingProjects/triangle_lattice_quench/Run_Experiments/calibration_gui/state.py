"""Session state, module-level constants, path anchors, and QSettings helpers.

This is the foundation layer of the calibration_gui package: it imports only
stdlib / third-party code plus the hardware-free flux defaults (``build_config``
and the ``MUXInitialize`` defaults, both load-safe). Nothing else in the package
is imported here, so ``state`` has no intra-package back-edges.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from PyQt5.QtCore import QSettings

from WorkingProjects.triangle_lattice_quench.MUXInitialize import (
    BaseConfig  as DEFAULT_BASE_CONFIG,
    outerFolder as DEFAULT_OUTER_FOLDER,
)
from WorkingProjects.triangle_lattice_quench.build_config import build_config

# Single readable anchor for the package's on-disk neighbours. From
# ``calibration_gui/state.py``: parent -> calibration_gui, parent -> Run_Experiments.
_RUN_EXPT_DIR = Path(__file__).resolve().parent.parent

# Default Qblox D5a coupler-bias setpoint file (mirrors QbloxVoltageSet.py).
DEFAULT_D5A_VOLTAGES_FILE = (
    _RUN_EXPT_DIR.parent / "Flux_Files"
    / "QbloxVoltageSet.py"
)

# Standard 8-qubit triangular-ladder D5a DAC mapping. Q1..Q8 -> DACs 1..8;
# coupler C1..C6 (legs 1-3, 2-4, 3-5, 4-6, 5-7, 6-8) -> DACs 9..14.
DEFAULT_D5A_DAC_MAP: dict[str, int] = {
    "Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4,
    "Q5": 5, "Q6": 6, "Q7": 7, "Q8": 8,
    "C1": 9, "C2": 10, "C3": 11, "C4": 12, "C5": 13, "C6": 14,
}

# Hardcoded coupled-pair list copied from
# WorkingProjects.triangle_lattice_quench.Flux_Files.plot_frequencies
# (PlotFrequenciesExperiment.coupled_pairs). Kept inline so the FF-frequency and
# pi/2-phase tabs can warn about crossings even when plot_frequencies fails to import.
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

# D5a connection defaults — match QbloxVoltageSet.py.
DEFAULT_D5A_PORT = "COM3"
DEFAULT_D5A_BAUD = int(1e6)
DEFAULT_D5A_TIMEOUT = 1.0
DEFAULT_D5A_MODULE = 2
DEFAULT_D5A_RAMP_STEP = 0.003
DEFAULT_D5A_RAMP_INTERVAL = 0.05

# Experiment library: scan this folder for ExperimentClass subclasses.
EXPERIMENTAL_SCRIPTS_DIR = _RUN_EXPT_DIR.parent / "Experimental_Scripts"
# Recipe files (saved JSON specs of {file, class, cfg, notes}) live here.
RECIPE_DIR = _RUN_EXPT_DIR / "recipes"
# Default location of the nested-groups parameter JSON.
QUBIT_PARAMETERS_JSON = _RUN_EXPT_DIR / "Qubit_Parameters" / "qubit_parameters.json"

# QSettings org/app — controls where Windows stores the recent-file pointer.
SETTINGS_ORG = "HouckLab"
SETTINGS_APP = "TriangleLatticeCalibrationGui"
SETTING_LAST_PARAMS = "last_qubit_params_path"
SETTING_D5A_VOLTAGES_PATH = "d5a_voltages_path"
SETTING_D5A_PORT = "d5a_port"
SETTING_D5A_MODULE = "d5a_module"
SETTING_D5A_LAST_APPLIED = "d5a_last_applied_at"
SETTING_LAST_RECIPE_PATH = "last_recipe_path"
SETTING_NS_HOST = "ns_host"   # Pyro4 nameserver host (RFSoC), remembered across sessions
SETTING_NS_PORT = "ns_port"


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
        "iterate": False, "max_iters": 6, "freq_tol": 0.3,
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
        "iterate": False, "max_iters": 6, "freq_tol": 0.3,
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


# Stages that run a MUXed readout: Qubit_Readout_List is built from the
# AutoCalibTab chip strip (state.mux_readouts) with the target prepended.
# All other stages get [target] only (single-qubit readout).
MUX_STAGES = frozenset({"ReadoutOpt", "PulseOpt", "SingleShot"})

# Stages that calibrate readout-side parameters (res frequency, gain, angle,
# threshold). Disabled in the AutoCalib table when a drive group is active —
# drive entries are not readout-calibration vehicles and their FF differs
# from the readout FF, so running these would write meaningless params.
READOUT_SIDE_STAGES = frozenset({"Transmission", "ReadoutOpt", "SingleShot"})


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
