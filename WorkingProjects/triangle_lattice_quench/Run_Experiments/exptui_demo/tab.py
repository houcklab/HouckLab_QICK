"""ExptUI_demo Qt tab — interactive experiment-config panel.

Visual model:
    * 8 horizontal qubit traces (Q1..Q8) crossing 4 stage columns.
    * Each (qubit, stage) intersection has a "dot" — click to override its FF
      gain; the y-offset of the dot visualises the override.
    * Right-click on a Drive-hold dot → submenu of valid drive-pulse labels
      for that qubit (scanned from qubit_parameters.json drive/readout groups
      whose entry keys start with "{q}_"). Click adds the label to
      ``spec.drive_pulses``.
    * Right-click on a stage column header → "Configure stage…" dialog
      (covers reps / sweep / readout pairs / FF-channel arrays / Ramp_State
      / Dynamics_Point — i.e. the global non-FF-gain knobs).
    * Run button → validate → ``generate_script`` → write file → show path
      in status label. Never executes the script.

No hardware touch. Reads ``qubit_parameters_json`` from the shared
``CalibState`` (same source as FFFrequenciesTab); writes nothing back to
the JSON.
"""
from __future__ import annotations

import dataclasses
import datetime
import os
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QInputDialog,
    QMenu, QMessageBox, QDialog, QFormLayout, QSpinBox, QLineEdit,
    QDialogButtonBox, QGroupBox, QComboBox, QPlainTextEdit,
)
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg

from .spec import ExperimentSpec
from .codegen import generate_script, validate_against_json


# Output directory for generated scripts; created on first Run.
_OUT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    os.pardir, "gui_generated_script",
)

# Stage order is fixed at v1 — the four boxes the user described.
STAGE_LABELS = ("Drive-hold", "Ramp", "Dynamics", "Readout")
STAGE_OVERRIDE_ATTR = {
    "Drive-hold": "drive_hold_overrides",
    "Ramp":       "ramp_overrides",
    "Dynamics":   "dynamics_overrides",
    "Readout":    "readout_overrides",
}


class _StageConfigDialog(QDialog):
    """Form dialog for the global non-FF-gain parameters.

    The user dragged dots = per-qubit FF gain (handled by the main tab).
    Everything else (sweep, timing, readout pairs, base config keys, FF
    arrays) lives here so the canvas stays uncluttered.
    """

    def __init__(self, spec: ExperimentSpec, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Experiment config")
        self._result_spec: Optional[ExperimentSpec] = None

        form = QFormLayout()

        self.reps = QSpinBox(); self.reps.setRange(1, 10_000_000); self.reps.setValue(spec.reps)
        self.ramp_time = QSpinBox(); self.ramp_time.setRange(3, 1_000_000); self.ramp_time.setValue(spec.ramp_time)
        self.relax_delay = QSpinBox(); self.relax_delay.setRange(0, 10_000); self.relax_delay.setValue(spec.relax_delay)
        self.start = QSpinBox(); self.start.setRange(0, 1_000_000); self.start.setValue(spec.start)
        self.step = QSpinBox(); self.step.setRange(1, 1_000_000); self.step.setValue(spec.step)
        self.expts = QSpinBox(); self.expts.setRange(1, 1_000_000); self.expts.setValue(spec.expts)
        self.ramp_state = QLineEdit(spec.ramp_state)
        self.dynamics_point = QLineEdit(spec.dynamics_point)
        self.readout_point = QLineEdit(spec.readout_point)
        self.qubit_readout = QLineEdit(",".join(str(q) for q in spec.qubit_readout))
        self.readout_pair_1 = QLineEdit(",".join(str(q) for q in spec.readout_pair_1))
        self.readout_pair_2 = QLineEdit(",".join(str(q) for q in spec.readout_pair_2))

        self.t_offset = QLineEdit(",".join(str(v) for v in spec.t_offset))
        self.bs_samples = QLineEdit(",".join(str(v) for v in spec.bs_samples))
        self.ij_samples = QLineEdit(",".join(str(v) for v in spec.intermediate_jump_samples))
        self.ij_gains = QLineEdit(
            ",".join("" if v is None else str(v) for v in spec.intermediate_jump_gains)
        )

        form.addRow("reps", self.reps)
        form.addRow("ramp_time", self.ramp_time)
        form.addRow("relax_delay (us)", self.relax_delay)
        form.addRow("sweep start", self.start)
        form.addRow("sweep step", self.step)
        form.addRow("sweep expts", self.expts)
        form.addRow("Ramp_State (JSON key)", self.ramp_state)
        form.addRow("Dynamics_Point (JSON key)", self.dynamics_point)
        form.addRow("Readout_Point (JSON key)", self.readout_point)
        form.addRow("Qubit_Readout (comma)", self.qubit_readout)
        form.addRow("readout_pair_1 (comma, 2 ints)", self.readout_pair_1)
        form.addRow("readout_pair_2 (comma, 2 ints)", self.readout_pair_2)
        form.addRow("t_offset (comma, 8 ints)", self.t_offset)
        form.addRow("bs_samples (comma, 8 ints)", self.bs_samples)
        form.addRow("intermediate_jump_samples (comma, 8 ints)", self.ij_samples)
        form.addRow("intermediate_jump_gains (comma, 8 ints, blank=None)", self.ij_gains)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._on_ok)
        bb.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(bb)

        self._original = spec

    @staticmethod
    def _parse_int_list(text: str, expected_len: Optional[int], allow_none=False):
        parts = [s.strip() for s in text.split(",")]
        out = []
        for p in parts:
            if p == "" and allow_none:
                out.append(None)
            else:
                out.append(int(p))
        if expected_len is not None and len(out) != expected_len:
            raise ValueError(f"expected {expected_len} entries, got {len(out)}")
        return out

    def _on_ok(self):
        try:
            qr = tuple(self._parse_int_list(self.qubit_readout.text(), None))
            rp1 = tuple(self._parse_int_list(self.readout_pair_1.text(), 2))
            rp2 = tuple(self._parse_int_list(self.readout_pair_2.text(), 2))
            t_off = tuple(self._parse_int_list(self.t_offset.text(), 8))
            bs = tuple(self._parse_int_list(self.bs_samples.text(), 8))
            ijs = tuple(self._parse_int_list(self.ij_samples.text(), 8))
            ijg = tuple(self._parse_int_list(self.ij_gains.text(), 8, allow_none=True))
        except Exception as e:
            QMessageBox.warning(self, "Parse error", str(e))
            return

        self._result_spec = dataclasses.replace(
            self._original,
            reps=self.reps.value(),
            ramp_time=self.ramp_time.value(),
            relax_delay=self.relax_delay.value(),
            start=self.start.value(),
            step=self.step.value(),
            expts=self.expts.value(),
            ramp_state=self.ramp_state.text(),
            dynamics_point=self.dynamics_point.text(),
            readout_point=self.readout_point.text(),
            qubit_readout=qr,
            readout_pair_1=rp1,
            readout_pair_2=rp2,
            t_offset=t_off,
            bs_samples=bs,
            intermediate_jump_samples=ijs,
            intermediate_jump_gains=ijg,
        )
        self.accept()

    def result_spec(self) -> Optional[ExperimentSpec]:
        return self._result_spec


class ExptUIDemoTab(QWidget):
    """Interactive experiment-builder tab. Generates a runnable Python
    script in ``Run_Experiments/gui_generated_script/`` on Run."""

    # Matches the user's request "ExptUI_demo".
    name = "ExptUI_demo"

    # Visual scaling: 1 unit of plot y per `_GAIN_PER_Y` of DAC gain override.
    _GAIN_PER_Y = 5000.0

    def __init__(self, state, get_main, parent=None):
        super().__init__(parent)
        self.state = state
        self.get_main = get_main
        self._spec = ExperimentSpec()

        # --- matplotlib canvas ---
        self._fig = Figure(figsize=(8.0, 4.5))
        self._canvas = FigureCanvasQTAgg(self._fig)
        self._ax = self._fig.add_subplot(111)
        # Click dispatch for the dots / stage labels.
        self._canvas.mpl_connect("button_press_event", self._on_canvas_press)

        # --- controls row ---
        cfg_btn = QPushButton("Stage / global config…")
        cfg_btn.clicked.connect(self._open_config_dialog)
        run_btn = QPushButton("Run (write script)")
        run_btn.clicked.connect(self._on_run)
        preview_btn = QPushButton("Preview generated script")
        preview_btn.clicked.connect(self._on_preview)
        reset_btn = QPushButton("Reset to defaults")
        reset_btn.clicked.connect(self._on_reset)
        controls = QHBoxLayout()
        controls.addWidget(cfg_btn)
        controls.addWidget(preview_btn)
        controls.addWidget(reset_btn)
        controls.addStretch(1)
        controls.addWidget(run_btn)

        # --- status label ---
        self._status = QLabel("Ready. Click a dot to set its gain override; "
                              "right-click for menus.")
        self._status.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self._canvas, 1)
        layout.addLayout(controls)
        layout.addWidget(self._status)

        self._dot_positions: dict[tuple[int, int], tuple[float, float]] = {}
        self._stage_label_xs: list[float] = []  # x-position of each stage label
        self._redraw()

    # ----- spec mutation helpers -----

    def _replace(self, **kwargs) -> None:
        self._spec = dataclasses.replace(self._spec, **kwargs)
        self._redraw()

    def _stage_override_dict(self, stage_label: str) -> dict[int, int]:
        return dict(getattr(self._spec, STAGE_OVERRIDE_ATTR[stage_label]))

    def _set_stage_override(self, stage_label: str, q: int, gain: Optional[int]) -> None:
        d = self._stage_override_dict(stage_label)
        if gain is None:
            d.pop(q, None)
        else:
            d[q] = gain
        self._replace(**{STAGE_OVERRIDE_ATTR[stage_label]: d})

    # ----- canvas drawing -----

    def _redraw(self) -> None:
        ax = self._ax
        ax.clear()
        self._dot_positions.clear()
        self._stage_label_xs = []

        # 8 qubit baselines. y = qubit index (1..8), inverted so Q1 on top.
        for q in range(1, 9):
            ax.axhline(y=q, color="lightgrey", linewidth=0.7, zorder=1)
            ax.text(-0.4, q, f"Q{q}", ha="right", va="center", fontsize=9)

        # 4 stage columns at x = 1, 2, 3, 4. Stage label at the top.
        for i, label in enumerate(STAGE_LABELS):
            x = i + 1.0
            self._stage_label_xs.append(x)
            ax.axvline(x=x, color="lightgrey", linestyle=":", linewidth=0.7, zorder=1)
            ax.text(x, 0.3, label, ha="center", va="bottom", fontsize=10,
                    fontweight="bold")

        # Plot dots at (stage_x, qubit_y + offset_from_override) per qubit.
        for i, label in enumerate(STAGE_LABELS):
            x = self._stage_label_xs[i]
            overrides = self._stage_override_dict(label)
            for q in range(1, 9):
                g = overrides.get(q)
                # Y-offset visualises override magnitude (capped at ±0.4).
                if g is None:
                    dy = 0.0
                    color = "C0"
                    edge = "C0"
                else:
                    dy = max(-0.4, min(0.4, -g / self._GAIN_PER_Y))
                    color = "C3"  # red-ish when override present
                    edge = "black"
                y = q + dy
                ax.plot([x], [y], marker="o", markersize=10,
                        color=color, markeredgecolor=edge, zorder=3)
                self._dot_positions[(i, q)] = (x, y)

        # Show drive pulses currently in spec.
        if self._spec.drive_pulses:
            ax.text(self._stage_label_xs[0], 9.3,
                    "σx: " + ", ".join(self._spec.drive_pulses),
                    ha="center", va="bottom", fontsize=8, color="C2")

        ax.set_xlim(-0.6, len(STAGE_LABELS) + 0.6)
        ax.set_ylim(9.5, 0.0)  # inverted (Q1 top); 0..9.5 for stage labels at top
        ax.set_xticks([])
        ax.set_yticks([])
        for s in ("top", "right", "left", "bottom"):
            ax.spines[s].set_visible(False)
        self._fig.tight_layout()
        self._canvas.draw_idle()

    # ----- canvas event dispatch -----

    def _hit_dot(self, event) -> Optional[tuple[int, int]]:
        """Return (stage_index, qubit) of the closest dot to a click within a
        small radius, else None."""
        if event.xdata is None or event.ydata is None:
            return None
        best = None
        best_d2 = 0.09  # ~0.3 in plot units, generous
        for (si, q), (x, y) in self._dot_positions.items():
            d2 = (event.xdata - x) ** 2 + (event.ydata - y) ** 2
            if d2 < best_d2:
                best, best_d2 = (si, q), d2
        return best

    def _hit_stage_label(self, event) -> Optional[int]:
        """Return stage index if the click is near a stage-label header."""
        if event.xdata is None or event.ydata is None:
            return None
        if event.ydata > 0.6:  # above the top baseline (Q1 at y=1)
            return None
        for i, x in enumerate(self._stage_label_xs):
            if abs(event.xdata - x) < 0.3:
                return i
        return None

    def _on_canvas_press(self, event) -> None:
        # Left = 1, Right = 3 (matplotlib convention).
        if event.button not in (1, 3):
            return
        hit = self._hit_dot(event)
        if hit is not None:
            si, q = hit
            stage_label = STAGE_LABELS[si]
            if event.button == 1:
                self._prompt_gain(stage_label, q)
            else:  # right-click
                self._show_dot_menu(stage_label, q, event)
            return
        stage_idx = self._hit_stage_label(event)
        if stage_idx is not None:
            if event.button == 3:
                self._show_stage_menu(stage_idx, event)
            else:
                # left-click on label → open global config too
                self._open_config_dialog()

    # ----- per-dot interactions -----

    def _prompt_gain(self, stage_label: str, q: int) -> None:
        current = self._stage_override_dict(stage_label).get(q)
        title = f"Q{q} • {stage_label} gain (DAC units, -32766..32766)"
        text, ok = QInputDialog.getText(
            self, "Set gain override", title,
            text="" if current is None else str(current),
        )
        if not ok:
            return
        text = text.strip()
        if text == "":
            self._set_stage_override(stage_label, q, None)
            self._status.setText(f"Cleared override Q{q} • {stage_label}.")
            return
        try:
            gain = int(text)
        except ValueError:
            QMessageBox.warning(self, "Not an integer", f"{text!r} is not an integer.")
            return
        if not (-32766 <= gain <= 32766):
            QMessageBox.warning(self, "Out of range",
                                "Gain must be in [-32766, 32766].")
            return
        self._set_stage_override(stage_label, q, gain)
        self._status.setText(f"Set Q{q} • {stage_label} → {gain}.")

    def _show_dot_menu(self, stage_label: str, q: int, event) -> None:
        menu = QMenu(self)
        if stage_label == "Drive-hold":
            labels = self._drive_labels_for_qubit(q)
            if not labels:
                act = menu.addAction(f"(no drive entry for Q{q} in JSON)")
                act.setEnabled(False)
            else:
                sigma = menu.addMenu(f"Add σx on Q{q}")
                for lbl in labels:
                    act = sigma.addAction(lbl)
                    act.triggered.connect(
                        lambda _checked, _lbl=lbl: self._add_drive_pulse(_lbl))
        if self._stage_override_dict(stage_label).get(q) is not None:
            clear = menu.addAction(f"Clear gain override on Q{q} • {stage_label}")
            clear.triggered.connect(
                lambda _checked: self._set_stage_override(stage_label, q, None))
        if menu.isEmpty():
            return
        self._exec_menu_at_event(menu, event)

    def _show_stage_menu(self, stage_idx: int, event) -> None:
        menu = QMenu(self)
        cfg = menu.addAction(f"Configure {STAGE_LABELS[stage_idx]} stage / global…")
        cfg.triggered.connect(self._open_config_dialog)
        self._exec_menu_at_event(menu, event)

    def _exec_menu_at_event(self, menu: QMenu, event) -> None:
        """Translate a matplotlib event's pixel position into a global Qt
        QPoint and pop the menu there."""
        canvas = self._canvas
        # matplotlib y is from bottom; Qt y is from top.
        px = int(round(event.x))
        py = int(round(canvas.height() - event.y))
        menu.exec_(canvas.mapToGlobal(_qpoint(px, py)))

    # ----- drive-pulse lookup -----

    def _qubit_json(self) -> dict:
        # Same accessor pattern as FFFrequenciesTab._jd.
        return getattr(self.state, "qubit_parameters_json", None) or {}

    def _drive_labels_for_qubit(self, q: int) -> list[str]:
        """Scan drive_groups + readout_groups; return every entry key that
        starts with f'{q}_'. Mirrors _resolve_drive's fallback search."""
        jd = self._qubit_json()
        prefix = f"{q}_"
        out: list[str] = []
        seen: set[str] = set()
        for ns in ("drive_groups", "readout_groups"):
            for grp in jd.get(ns, {}).values():
                if not isinstance(grp, dict):
                    continue
                for k in (grp.get("entries", {}) or {}).keys():
                    if isinstance(k, str) and k.startswith(prefix) and k not in seen:
                        out.append(k)
                        seen.add(k)
        return out

    def _add_drive_pulse(self, label: str) -> None:
        if label in self._spec.drive_pulses:
            self._status.setText(f"σx pulse {label!r} already in spec.")
            return
        new_pulses = self._spec.drive_pulses + (label,)
        self._replace(drive_pulses=new_pulses)
        self._status.setText(f"Added σx pulse {label!r}.")

    # ----- buttons -----

    def _open_config_dialog(self) -> None:
        dlg = _StageConfigDialog(self._spec, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            new_spec = dlg.result_spec()
            if new_spec is not None:
                self._spec = new_spec
                self._redraw()
                self._status.setText("Config updated.")

    def _on_reset(self) -> None:
        self._spec = ExperimentSpec()
        self._redraw()
        self._status.setText("Spec reset to defaults.")

    def _validate_or_warn(self) -> bool:
        """Run codegen gates + JSON gate. Return True if all pass."""
        jd = self._qubit_json()
        # JSON gate first (so drive-pulse + readout-group errors land before
        # the generic gate failures with weaker messages).
        if jd:
            try:
                validate_against_json(self._spec, jd)
            except ValueError as e:
                QMessageBox.warning(self, "Spec invalid (JSON check)", str(e))
                return False
        try:
            # Compile-only call to surface ValueError without writing anything.
            generate_script(self._spec)
        except ValueError as e:
            QMessageBox.warning(self, "Spec invalid", str(e))
            return False
        return True

    def _on_preview(self) -> None:
        if not self._validate_or_warn():
            return
        text = generate_script(self._spec)
        dlg = QDialog(self)
        dlg.setWindowTitle("Generated script preview")
        dlg.resize(900, 700)
        editor = QPlainTextEdit(dlg)
        editor.setReadOnly(True)
        editor.setPlainText(text)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        bb.accepted.connect(dlg.accept)
        # Close button is on the "rejected" channel by default.
        lay = QVBoxLayout(dlg)
        lay.addWidget(editor, 1)
        lay.addWidget(bb)
        dlg.exec_()

    def _on_run(self) -> None:
        if not self._validate_or_warn():
            return
        text = generate_script(self._spec)
        os.makedirs(_OUT_DIR, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(_OUT_DIR, f"exptui_{ts}.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        self._status.setText(f"Wrote {path}. Inspect it, then run with your venv python.")


def _qpoint(x: int, y: int):
    """Local import wrapper so the test layer doesn't need PyQt at import time."""
    from PyQt5.QtCore import QPoint
    return QPoint(x, y)
