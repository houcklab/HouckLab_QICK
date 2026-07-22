"""Pi/2-phase calibration tab.

Sweeps the measurement pi/2 phase (and optionally a dynamics-time axis) for a
chosen qubit via ``MottQuenchPi2Phase`` variants, using the flux model to seed
dressed-frequency context. Shares ``import_experiment_class`` with the
experiment library.

Depends on state / helpers / widgets / experiment_library and the flux model.
"""
from __future__ import annotations

import traceback
from typing import Any, Optional

from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QVBoxLayout, QWidget,
)

from WorkingProjects.triangle_lattice_quench.Flux_Files.LEGACY.Initialize_Qubit_Information import model_mapping
from WorkingProjects.triangle_lattice_quench.Flux_Files.LEGACY.Whole_system_to_Voltages import flux_vector, beta_matrix
from WorkingProjects.triangle_lattice_quench.Helpers.Device_calibration import full_device_calib

from ..state import (
    CalibState,
    EXPERIMENTAL_SCRIPTS_DIR,
    _FF_FREQ_COUPLED_PAIRS,
    _confusion_matrix_for,
)
from ..helpers import (
    build_config,
    _build_resolve_drive,
    _build_resolve_ramp,
)
from ..widgets import MplCanvas, ParamForm, _agent_set_combo
from .experiment_library import import_experiment_class


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
            from WorkingProjects.triangle_lattice_quench.Flux_Files.LEGACY.Calculate_FF import (
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
