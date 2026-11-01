"""Controller: owns the Sequence, applies every edit as an undoable command, and re-resolves.

Model / controller / view: the core Sequence is the single source of truth. Views never
edit it directly; they call controller methods. Each edit snapshots the sequence before
and after (sequences are small), which makes undo exact and simple. After any change a
debounced resolve -> validate -> compile runs and ``refreshed`` fires.
"""
from __future__ import annotations

import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from PyQt5.QtWidgets import QUndoCommand, QUndoStack

from ..blocks.registry import block_class, block_from_dict
from ..compiler.tlq_backend import compile_sequence
from ..config.calib_drift import drift_problems, used_values
from ..config.calibration import CalibrationStore
from ..config.problems import Problem
from ..config.resolver import Resolver
from ..config.settings import ExperimentSettings, SweepAxis
from ..config.station import Station
from ..config.summary import summarize
from ..core.block import MeasureBlock, PulseBlock, SegmentBlock
from ..core.params import Sweep, Value, VectorSource, base_source
from ..core.sequence import Sequence, sweep_users_text
from .app_settings import app_settings

BOB_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CALIB = BOB_ROOT.parent / "Run_Experiments" / "Qubit_Parameters" / "qubit_parameters.json"


class _Edit(QUndoCommand):
    """One undoable edit, stored as the whole sequence before and after (as dicts)."""

    def __init__(self, ctl: "Controller", text: str, before: dict, after: dict, select_before, select_after):
        super().__init__(text)
        self.ctl, self.before, self.after = ctl, before, after
        self.sel_before, self.sel_after = select_before, select_after
        self._first = True

    def redo(self):
        if self._first:          # the edit already happened when the command was pushed
            self._first = False
            return
        self.ctl._restore(self.after, self.sel_after)

    def undo(self):
        self.ctl._restore(self.before, self.sel_before)


class Controller(QObject):
    changed = pyqtSignal()                 # structure or fields changed (redraw)
    selection_changed = pyqtSignal(object)  # block id or None
    refreshed = pyqtSignal()               # resolve/validate/compile finished
    files_changed = pyqtSignal()           # station / calibration / document path changed
    message = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings_store = app_settings()
        self.seq = Sequence()
        self.undo = QUndoStack(self)
        self.undo.cleanChanged.connect(self._clean_changed)
        self.selected: Optional[str] = None
        self.clipboard: Optional[dict] = None
        self.doc_path: Optional[Path] = None
        self.preview_index = 0
        self.compensate = True
        self.station = self._load_station(self.settings_store.value("station", "8QV1"))
        self.calib = CalibrationStore.empty()
        self.calib_error: Optional[str] = None
        self.compiled = None
        self.resolved = None
        self.problems: list = []
        self.calib_baseline: Optional[dict] = None   # calibration values the open file was saved with
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self.refresh_now)
        last = self.settings_store.value("calibration_path", "")
        for cand in [last, str(DEFAULT_CALIB)]:
            if cand and Path(cand).exists():
                self.set_calibration(cand, push_message=False)
                break
        else:
            self.calib_error = "No calibration file loaded. Choose qubit_parameters.json from the toolbar."

    def _clean_changed(self, _clean):
        self.files_changed.emit()

    # ================================================================== files
    def _load_station(self, name):
        try:
            return Station.load(name)
        except Exception:
            return Station.load("8QV1")

    def set_station(self, name: str) -> None:
        self.station = self._load_station(name)
        self.seq.station = self.station.name
        self.settings_store.setValue("station", self.station.name)
        self.files_changed.emit()
        self.schedule_refresh()

    def set_calibration(self, path: str, push_message: bool = True) -> bool:
        try:
            self.calib = CalibrationStore.load(path)
        except Exception as exc:
            self.calib_error = f"Couldn't read {path}: {exc}"
            self.message.emit(self.calib_error)
            return False
        self.calib_error = None
        self.seq.calibration = {"path": str(path), "sha256": self.calib.sha256}
        self.settings_store.setValue("calibration_path", str(path))
        if push_message:
            self.message.emit(f"Calibration: {Path(path).name}")
        self.files_changed.emit()
        self.schedule_refresh()
        return True

    def new_sequence(self) -> None:
        calib = {"path": self.calib.path, "sha256": self.calib.sha256} if self.calib.path else {}
        self.seq = Sequence(station=self.station.name, calibration=calib)
        self.doc_path = None
        self.selected = None
        self.preview_index = 0
        self.calib_baseline = None
        self.undo.clear()
        self._after_load()

    def open_sequence(self, path, as_template: bool = False) -> None:
        seq = Sequence.load(path)
        if seq.station != self.station.name and seq.station in Station.available():
            self.station = self._load_station(seq.station)      # use the station the file was made for
        saved = dict(seq.calibration or {})
        pinned = saved.get("sha256")
        file_changed = bool(pinned and self.calib.sha256 and pinned != self.calib.sha256)
        if self.calib.path:
            seq.calibration = {"path": self.calib.path, "sha256": self.calib.sha256}
            if "used" in saved:
                seq.calibration["used"] = saved["used"]
        self.seq = seq
        self.doc_path = None if as_template else Path(path)
        self.selected = None
        self.preview_index = 0
        self.calib_baseline = None if as_template else saved.get("used")
        self.undo.clear()
        self._after_load()
        if as_template or not file_changed:
            return
        if self.calib_baseline is None:          # saved before Bob recorded the values it used
            self.message.emit("The calibration file changed since this sequence was saved; values are read from "
                              "the current file. Check the Resolved tab.")
        else:
            self.refresh_now()
            n = sum(1 for p in self.problems if p.message.startswith("Calibration changed"))
            if n:
                self.message.emit(f"Calibration changed since this sequence was saved ({n} warning"
                                  f"{'s' if n != 1 else ''}). See Problems.")

    def save(self, path=None) -> Path:
        path = Path(path) if path else self.doc_path
        if path is None:
            raise ValueError("no path")
        if self.calib.path:
            self.seq.calibration = {"path": self.calib.path, "sha256": self.calib.sha256}
            # record the calibration values in use, so a later open can tell which ones changed
            self.refresh_now()
            if self.resolved is not None:
                used = used_values(self.resolved)
                self.seq.calibration["used"] = used
                self.calib_baseline = used
        self.seq.summary = self.summary_text()
        self.seq.save(path)
        self.doc_path = path
        self.undo.setClean()
        self.files_changed.emit()
        return path

    def _after_load(self):
        self.changed.emit()
        self.selection_changed.emit(None)
        self.files_changed.emit()
        self.schedule_refresh()

    @property
    def dirty(self) -> bool:
        return not self.undo.isClean()

    # ================================================================== edits
    def _push(self, text: str, mutate, select_after="keep"):
        """Run ``mutate()`` on the live sequence and record it on the undo stack.

        If it raises, the sequence is restored and the error shown; if it changes nothing,
        no undo step is added. ``select_after`` is a block id, None, or "keep".
        """
        before = self.seq.to_dict()
        sel_before = self.selected
        try:
            result = mutate()
        except Exception as exc:
            self.seq = Sequence.from_dict(before)
            self.message.emit(f"{text} failed: {exc}")
            return None
        after = self.seq.to_dict()
        if after == before:
            return result
        sel_after = self.selected if select_after == "keep" else select_after
        if sel_after is not None and self.seq.get(sel_after) is None:
            sel_after = None                     # the edit removed the selected block (e.g. a pulse in a deleted segment)
        self.undo.push(_Edit(self, text, before, after, sel_before, sel_after))
        if sel_after != self.selected:
            self.select(sel_after)
        self.changed.emit()
        self.schedule_refresh()
        return result

    def _restore(self, d: dict, select):
        self.seq = Sequence.from_dict(d)
        self.selected = select if select is None or self.seq.get(select) else None
        self.changed.emit()
        self.selection_changed.emit(self.selected)
        self.schedule_refresh()

    def select(self, block_id) -> None:
        if block_id is not None and self.seq.get(block_id) is None:
            block_id = None
        if block_id != self.selected:
            self.selected = block_id
        self.selection_changed.emit(block_id)

    def add_block(self, type_name: str, *, index: Optional[int] = None, act: Optional[str] = None,
                  segment_id: Optional[str] = None, qubit: Optional[int] = None):
        cls = block_class(type_name)
        b = cls()
        if act and b.KIND == "segment":
            b.act = act
        if qubit is not None and "qubit" in b.fields:
            b.fields["qubit"] = Value(int(qubit))
            b.name = f"{cls.LABEL} Q{qubit}"
        return self._insert(b, index=index, segment_id=segment_id, text=f"Add {cls.LABEL}")

    def add_preset(self, preset: dict, *, index=None, act=None, segment_id=None, qubit=None):
        blocks = [block_from_dict(d).clone() for d in preset.get("blocks", [])]
        if not blocks:
            return None
        b = blocks[0]
        if act and b.KIND == "segment":
            b.act = act
        if qubit is not None and "qubit" in b.fields:
            b.fields["qubit"] = Value(int(qubit))
        return self._insert(b, index=index, segment_id=segment_id, text=f"Add preset {preset.get('name', '')}")

    def _insert(self, b, *, index, segment_id, text):
        def do():
            if isinstance(b, SegmentBlock):
                self.seq.insert_segment(b, index)
            elif isinstance(b, PulseBlock):
                if segment_id is None:
                    raise ValueError("drop a pulse inside a segment's lane")
                self.seq.add_pulse(b, segment_id)
            elif isinstance(b, MeasureBlock):
                if self.seq.measure is not None:
                    raise ValueError("there is already a Measure block; select it to edit")
                self.seq.set_measure(b)
            return b.id
        return self._push(text, do, select_after=b.id)

    def remove(self, block_id: str) -> None:
        b = self.seq.get(block_id)
        if b is None:
            return
        self._push(f"Delete {b.name}", lambda: self.seq.remove(block_id),
                   select_after=None if self.selected == block_id else "keep")

    def duplicate(self, block_id: str) -> None:
        b = self.seq.get(block_id)
        if b is None or isinstance(b, MeasureBlock):
            return
        nb = b.clone()
        nb.name = b.name + " copy"

        def do():
            if isinstance(b, SegmentBlock):
                i = self.seq.segment_index(block_id)
                self.seq.insert_segment(nb, i + 1)
                for p in self.seq.pulses_in(block_id):
                    self.seq.add_pulse(p.clone(), nb.id)
            else:
                self.seq.add_pulse(nb, b.segment_id)
        self._push(f"Duplicate {b.name}", do, select_after=nb.id)

    def move_segment(self, block_id: str, index: int, act: Optional[str] = None) -> None:
        b = self.seq.get(block_id)
        if b is None:
            return

        def do():
            i = self.seq.segment_index(block_id)
            # ``index`` is a gap position counted with the segment still in place
            self.seq.move_segment(block_id, index - 1 if index > i else index)
            if act:
                b.act = act
        self._push(f"Move {b.name}", do)

    def move_pulse(self, block_id: str, segment_id: str, qubit: Optional[int]) -> None:
        b = self.seq.get(block_id)
        if b is None:
            return

        def do():
            b.segment_id = segment_id
            if qubit is not None and "qubit" in b.fields:
                b.fields["qubit"] = Value(int(qubit))
        self._push(f"Move {b.name}", do)

    def set_field(self, block_id: str, name: str, source) -> None:
        b = self.seq.get(block_id)
        if b is None:
            return
        self._push(f"Edit {b.name}.{name}", lambda: b.set_field(name, source))

    @contextmanager
    def undo_group(self, text: str):
        """Edits made inside ``with ctl.undo_group(...)`` undo and redo as one step."""
        self.undo.beginMacro(text)
        try:
            yield
        finally:
            self.undo.endMacro()

    def set_name(self, name: str) -> None:
        """Rename the sequence (undoable). The top bar and the Experiment tab both call this."""
        name = name.strip()
        if name and name != self.seq.name:
            self._push("Rename sequence", lambda: setattr(self.seq, "name", name))

    def rename(self, block_id: str, name: str) -> None:
        b = self.seq.get(block_id)
        if b is None or not name.strip():
            return
        self._push(f"Rename {b.name}", lambda: setattr(b, "name", name.strip()))

    def set_act(self, block_id: str, act: str) -> None:
        b = self.seq.get(block_id)
        if b is None:
            return
        self._push(f"Move {b.name} to {act}", lambda: setattr(b, "act", act))

    def set_settings(self, settings: ExperimentSettings, name=None, description=None, rename_axes=None) -> None:
        """Replace the experiment settings. ``rename_axes`` ({old: new}) re-points swept fields."""
        def do():
            if rename_axes:
                for b in self.seq.blocks():
                    for k, src in list(b.fields.items()):
                        base = base_source(src)
                        if isinstance(base, Sweep) and base.axis in rename_axes:
                            nb = Sweep(rename_axes[base.axis])
                            b.fields[k] = VectorSource(nb, dict(src.overrides)) \
                                if isinstance(src, VectorSource) else nb
            self.seq.settings = settings
            if name is not None:
                self.seq.name = name
            if description is not None:
                self.seq.description = description
        self._push("Edit experiment settings", do)

    def add_sweep_axis(self, name: str, start=0.0, stop=1.0, points=11, unit="") -> str:
        existing = {a.name for a in self.seq.settings.sweeps}
        base, k = name, 2
        while name in existing:
            name = f"{base}{k}"
            k += 1
        new = ExperimentSettings.from_dict(self.seq.settings.to_dict())
        new.sweeps.append(SweepAxis(name, start, stop, points, unit))
        self.set_settings(new)
        return name

    def update_sweep_axis(self, name: str, **changes) -> None:
        """Change an axis's start, stop, points or unit (undoable). The Experiment tab and the
        inspector both edit axes through here."""
        new = ExperimentSettings.from_dict(self.seq.settings.to_dict())
        axis = new.axis(name)
        if axis is None:
            return
        for k, v in changes.items():
            setattr(axis, k, v)
        self.set_settings(new)

    def remove_sweep_axis(self, name: str) -> Optional[str]:
        """Remove an axis no field uses. Returns why not, or None when removed."""
        users = self.seq.sweep_users().get(name, [])
        if users:
            return (f"‹{name}› is still swept by {sweep_users_text(users)}. Give those fields another "
                    "source first.")
        new = ExperimentSettings.from_dict(self.seq.settings.to_dict())
        new.sweeps = [a for a in new.sweeps if a.name != name]
        self.set_settings(new)
        return None

    # ------------------------------------------------------------------ copy / paste
    def copy(self, block_id: Optional[str] = None) -> bool:
        """Copy a block (a segment brings its pulses) to Bob's clipboard."""
        b = self.seq.get(block_id or self.selected) if (block_id or self.selected) else None
        if b is None:
            return False
        payload = {"block": b.to_dict()}
        if isinstance(b, SegmentBlock):
            payload["pulses"] = [p.to_dict() for p in self.seq.pulses_in(b.id)]
        self.clipboard = payload
        self.message.emit(f"Copied {b.name}")
        return True

    def can_paste(self) -> bool:
        return self.clipboard is not None

    def paste(self) -> None:
        """Paste after the selection: a segment goes right after the selected segment (or at the end of its
        act's run); a pulse goes into the selected segment, or the segment of the selected pulse."""
        clip = self.clipboard
        if not clip:
            return
        b = block_from_dict(clip["block"]).clone()
        sel = self.seq.get(self.selected) if self.selected else None
        if isinstance(b, SegmentBlock):
            if isinstance(sel, SegmentBlock):
                index = self.seq.segment_index(sel.id) + 1
            elif isinstance(sel, PulseBlock):
                index = self.seq.segment_index(sel.segment_id) + 1
            else:
                index = len(self.seq.segments)
            pulses = [block_from_dict(d).clone() for d in clip.get("pulses", [])]

            def do():
                self.seq.insert_segment(b, index)
                for p in pulses:
                    self.seq.add_pulse(p, b.id)
            self._push(f"Paste {b.name}", do, select_after=b.id)
        elif isinstance(b, PulseBlock):
            target = sel.id if isinstance(sel, SegmentBlock) else (sel.segment_id if isinstance(sel, PulseBlock)
                                                                   else None)
            if target is None:
                self.message.emit("Select a segment (or a pulse in it) to paste a pulse into.")
                return
            self._insert(b, index=None, segment_id=target, text=f"Paste {b.name}")
        else:
            self._insert(b, index=None, segment_id=None, text=f"Paste {b.name}")

    def block_as_preset(self, block_id: str) -> Optional[dict]:
        b = self.seq.get(block_id)
        if b is None:
            return None
        return {"bob_preset": 1, "name": b.name, "blocks": [b.to_dict()]}

    # ================================================================== refresh
    def schedule_refresh(self) -> None:
        self._timer.start()

    def set_preview_index(self, k: int) -> None:
        self.preview_index = max(0, min(int(k), self.seq.settings.n_points() - 1))
        self.schedule_refresh()

    def set_compensate(self, on: bool) -> None:
        self.compensate = bool(on)
        self.schedule_refresh()

    def refresh_now(self) -> None:
        self.preview_index = min(self.preview_index, self.seq.settings.n_points() - 1)
        pt = self.seq.settings.point(self.preview_index)
        try:
            compiled, res, problems = compile_sequence(self.seq, self.station, self.calib, pt, self.compensate)
        except Exception as exc:  # never let a bug in a block take the GUI down
            compiled, res = None, None
            problems = [Problem("error", f"Internal error while compiling: {exc}")]
            traceback.print_exc()
        if self.calib_error:
            problems.insert(0, Problem("warning", self.calib_error))
        if self.seq.station != self.station.name:
            problems.insert(0, Problem("warning", f"This sequence was made for station {self.seq.station!r}, "
                                                  f"which is not in library/stations; compiling for "
                                                  f"{self.station.name!r} instead."))
        problems.extend(drift_problems(self.calib_baseline, res))
        if compiled is not None:
            for note in compiled.notes:
                if not any(note == p.message for p in problems):
                    problems.append(Problem("info", note))
        self.compiled, self.resolved, self.problems = compiled, res, problems
        self.refreshed.emit()

    def summary_text(self) -> str:
        """Plain-language summary, at the first sweep point (what the file stores)."""
        try:
            res = Resolver(self.station, self.calib).resolve(self.seq)
            return summarize(self.seq, res, self.station.n_channels)
        except Exception as exc:  # a summary must never stop a save
            return f"(summary unavailable: {exc})"

    def problems_for(self, block_id: str) -> list:
        return [p for p in self.problems if p.block_id == block_id]

    def worst_level(self, block_id: str) -> Optional[str]:
        levels = {p.level for p in self.problems_for(block_id)}
        for lvl in ("error", "warning"):
            if lvl in levels:
                return lvl
        return None
