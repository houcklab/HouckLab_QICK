"""FF-frequencies tab — dressed-frequency trajectory plot across sections.

For each experimental stage (Readout / Drive / Ramp / Dynamics) the user picks a
group+entry; the tab resolves the FF gains, converts to dressed frequencies via
the flux model, and plots the per-qubit trajectory, warning about coupled-pair
crossings. Reuses ``EntryEditDialog`` from the qubit-parameters tab.

Depends on state / helpers / widgets / qubit_parameters and the flux model.
"""
from __future__ import annotations

import copy
import traceback
from typing import Optional

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from WorkingProjects.triangle_lattice_quench.Flux_Files.LEGACY.Initialize_Qubit_Information import model_mapping
from WorkingProjects.triangle_lattice_quench.Flux_Files.LEGACY.Whole_system_to_Voltages import flux_vector, beta_matrix
from WorkingProjects.triangle_lattice_quench.Helpers.Device_calibration import full_device_calib

from ..state import CalibState, _FF_FREQ_COUPLED_PAIRS
from ..helpers import (
    _build_resolve_drive,
    _build_resolve_ramp,
    _build_resolve_dynamics,
    _build_deref_base,
    _values_differ,
    _leaf_at_path,
    _entry_touched_paths,
)
from ..widgets import MplCanvas
from .qubit_parameters import EntryEditDialog


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
