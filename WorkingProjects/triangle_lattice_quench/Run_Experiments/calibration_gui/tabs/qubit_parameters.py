"""Qubit Parameters tab + its Save dialog and inline table editors.

Owns the in-memory ``qubit_parameters.json`` view: the nested readout/drive/
ramp/dynamics group tree, the Save-diff confirmation dialog, the bulk-entry
calculator table, and the entry-edit dialog. ``_apply_dirty_style`` (Qt, used
only here) rides along. ``EntryEditDialog`` is also imported by the
FF-frequencies tab.

Depends on state / helpers only.
"""
from __future__ import annotations

import copy
import json
import traceback
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QPushButton, QSplitter,
    QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
    QWidget,
)

from ..state import CalibState, QUBIT_PARAMETERS_JSON
from ..helpers import (
    BUILD_CONFIG_JSON_PATH,
    _build_resolve_readout,
    _build_resolve_drive,
    _build_resolve_ramp,
    _build_resolve_dynamics,
    dumps_pretty,
    dump_pretty,
    _make_jsonable,
    _values_differ,
    _is_suspicious_change,
    _diff_entries,
    _fmt_diff_value,
    _field_importance,
    _leaf_at_path,
    _path_is_dirty,
    _entry_touched_paths,
)


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
