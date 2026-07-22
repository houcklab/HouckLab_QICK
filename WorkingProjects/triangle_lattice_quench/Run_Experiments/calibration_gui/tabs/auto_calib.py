"""Auto-Calibration tab and the single-stage calibration tabs.

The biggest cluster: the ``StageTab`` base + its iterative recenter-and-zoom
mixin + the off-thread ``ExperimentWorker``, the eight concrete stage tabs
(Transmission / SpecSlice / AmplitudeRabi / ReadoutOpt / PulseOpt / SingleShot /
T1 / T2R), the ``AutoCalibWorker`` that drives a queued matrix of stages off the
GUI thread, the ``AutoCalibTab`` itself, and the per-qubit ``ResultsDialog``.

Depends on the package foundation (state / helpers / widgets); no other tab is
imported here. ``main_window`` imports the stage classes + AutoCalibTab from
here, and the package ``__init__`` re-exports ``AutoCalibWorker`` from here.
"""
from __future__ import annotations

import copy
import time
import traceback
from typing import Any, Callable, Optional

from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QGridLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QMessageBox, QPlainTextEdit, QPushButton, QSplitter,
    QStackedWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..state import (
    CalibState,
    STAGE_DEFAULTS,
    MUX_STAGES,
    READOUT_SIDE_STAGES,
    _jd_entry_for,
)
from ..helpers import (
    build_cfg_for_qubit,
    _readout_qubit_for_entry,
    _mux_readout_list,
    _pulse_chain_entries,
    DAC_GAIN_MAX,
    ITER_PARAM_KEYS,
    recenter_zoom_step,
    _snapshot_calibration_diff,
)
from ..widgets import (
    MplCanvas,
    ParamForm,
    SELECTION_ROLE,
    CalibCellDelegate,
    MuxChipStrip,
    CalibTable,
)


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

    def iterate_recenter_zoom(self, cfg, log, should_abort, on_point=None):
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
            data = expt.acquire(live_callback=on_point)
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


# --- per-qubit-entry diff helpers (Save dialog) ----------------------------


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
            def acquire(self_inner, progress=False, live_callback=None):
                # Suppress in-acquire matplotlib calls; we re-render onto the GUI canvas.
                return ReadOpt_wSingleShotFFMUX.acquire(
                    self_inner, progress=progress, plotDisp=False, ax=None,
                    live_callback=live_callback,
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
            def acquire(self_inner, progress=False, live_callback=None):
                return QubitPulseOpt_wSingleShotFFMUX.acquire(
                    self_inner, progress=progress, plotDisp=False, ax=None,
                    live_callback=live_callback,
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
    live_update  = pyqtSignal(str, str, object)                       # qubit, stage, snapshot data dict

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
                # Live per-point plot updates for ReadoutOpt/PulseOpt
                # (RecenterZoomMixin): snapshot a COPY of fid_mat (avoid a
                # read/write race with this worker thread) and emit, throttled
                # to ~5 Hz. Fed to BOTH the iterate path (each sub-scan) and the
                # single-shot path, so the heatmap fills in live even with
                # "Iterate recenter+zoom" off.
                _on_point = None
                if isinstance(stage, RecenterZoomMixin):
                    _last = [0.0]
                    def _on_point(d, Q=Q, stage_name=stage_name, _last=_last):
                        import numpy as np
                        now = time.perf_counter()
                        if now - _last[0] < 0.2:
                            return
                        _last[0] = now
                        try:
                            dd = d.get('data', {})
                            snap = {'config': d.get('config', {}),
                                    'data': {**dd, 'fid_mat': np.array(dd['fid_mat'])}}
                            self.live_update.emit(str(Q), stage_name, snap)
                        except Exception:
                            pass
                if params.get("iterate") and isinstance(stage, RecenterZoomMixin):
                    expt, data = stage.iterate_recenter_zoom(
                        cfg, self.log_msg.emit, should_abort=lambda: self._stop,
                        on_point=_on_point)
                else:
                    for _k in ITER_PARAM_KEYS:
                        cfg.pop(_k, None)
                    expt = stage.make_experiment(cfg)
                    # ROpt/POpt accept live_callback; other stages' acquire() does not.
                    if _on_point is not None:
                        data = expt.acquire(live_callback=_on_point)
                    else:
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
        # (Q, stage_name) currently acquiring, for the live-frame stale guard.
        self._live_running: Optional[tuple[str, str]] = None

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
        # Clear-on-change: a new group is a clean slate. Drop cached results and
        # cell colors BEFORE refresh_qubits so its prev-snapshot restore finds
        # nothing (cells paint neutral, View buttons rebuild disabled). Preserve
        # _cell_enabled (stage selection) — that's a UI choice, not a result.
        self.results.clear()
        self._cell_outcome.clear()
        self._live_running = None   # drop any late live frame from a prior run
        # Mirror to current_qubit_label so SingleShot.on_apply writes into
        # the right entry on subsequent runs.
        self.refresh_qubits()
        # Rebuild MUX chips from this group's entries; default all selected.
        self._rebuild_mux_strip()
        # Reset the live plot + label to their idle state.
        self.live_canvas.reset()
        self.live_canvas.draw()
        self.live_label.setText(
            "Live plot — click a body cell to view its cached result.")
        # refresh_qubits rebuilt the View buttons; ensure they read as empty.
        for btn in self._result_buttons.values():
            btn.setText("-")
            btn.setEnabled(False)

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
        self.worker.live_update.connect(self._on_live_update)
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
        # Track the currently-acquiring (Q, stage) for the live-frame stale guard.
        if status in ("acquiring", "starting"):
            self._live_running = (Q, stage_name)

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

    def _render_live(self, Q: str, stage_name: str, expt, data, switch_page: bool = True):
        # Switch to plot page before rendering so the user sees the plot. Live
        # per-point frames pass switch_page=False so they don't yank the user
        # off the log page every update; only the final stage_done frame switches.
        if switch_page:
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

    def _on_live_update(self, Q: str, stage_name: str, snapshot):
        # Stale-frame guard: drop frames when no run is active or when this
        # frame is not from the stage currently acquiring (e.g. a late frame
        # emitted from a prior run/group). _render_live reads only
        # data["data"]/data["config"], so expt=None is safe here.
        if self._live_running is None:
            return
        if (Q, stage_name) != self._live_running:
            return
        self._render_live(Q, stage_name, None, snapshot, switch_page=False)

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
        self._live_running = None
        self.worker = None


# ---------------------------------------------------------------------------
# LatticePointCalibrationTab — per-qubit Ramsey-vs-FF -> shared base_params slot
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
