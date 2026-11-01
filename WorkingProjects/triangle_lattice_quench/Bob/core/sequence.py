"""Sequence: the whole experiment as Bob edits and saves it.

A sequence is an ordered list of flux segments, each labelled with an act (preparation,
dynamics, readout). Pulses sit inside segments on qubit lanes, and at most one Measure block
ends the sequence. The file also stores the experiment settings (reps, sweep axes), the
station name, the calibration file it was saved with, and a plain-language summary.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

from ..config.settings import ExperimentSettings
from .block import ACTS, Block, MeasureBlock, PulseBlock, SegmentBlock

BOB_FILE_VERSION = 1


@dataclass
class Sequence:
    name: str = "Untitled"
    description: str = ""
    summary: str = ""                                  # written by Bob on save (config/summary.py)
    station: str = "8QV1"
    calibration: dict = field(default_factory=dict)   # {"path", "sha256", "used": {leaf path: value}}
    settings: ExperimentSettings = field(default_factory=ExperimentSettings)
    segments: list = field(default_factory=list)       # list[SegmentBlock], in time order
    pulses: list = field(default_factory=list)         # list[PulseBlock]
    measure: Optional[MeasureBlock] = None

    # ------------------------------------------------------------------ lookup
    def blocks(self) -> Iterator[Block]:
        yield from self.segments
        yield from self.pulses
        if self.measure is not None:
            yield self.measure

    def get(self, block_id: str) -> Optional[Block]:
        for b in self.blocks():
            if b.id == block_id:
                return b
        return None

    def sweep_users(self) -> dict:
        """{axis name: [(block, field spec), ...]} for every field swept over that axis, in play order."""
        from .params import base_source
        users: dict = {}
        for b in self.blocks():
            for spec in b.FIELDS:
                src = base_source(b.fields.get(spec.name))
                if getattr(src, "kind", None) == "sweep":
                    users.setdefault(src.axis, []).append((b, spec))
        return users

    def segment_index(self, segment_id: str) -> int:
        for i, s in enumerate(self.segments):
            if s.id == segment_id:
                return i
        raise KeyError(segment_id)

    def pulses_in(self, segment_id: str) -> list:
        return [p for p in self.pulses if p.segment_id == segment_id]

    # ------------------------------------------------------------------ edits
    def insert_segment(self, block: SegmentBlock, index: Optional[int] = None) -> None:
        if not isinstance(block, SegmentBlock):
            raise TypeError(f"{block!r} is not a segment block")
        if index is None or index > len(self.segments):
            index = len(self.segments)
        self.segments.insert(max(0, index), block)

    def add_pulse(self, block: PulseBlock, segment_id: str) -> None:
        if not isinstance(block, PulseBlock):
            raise TypeError(f"{block!r} is not a pulse block")
        self.segment_index(segment_id)  # raises if missing
        block.segment_id = segment_id
        self.pulses.append(block)

    def set_measure(self, block: Optional[MeasureBlock]) -> None:
        self.measure = block

    def remove(self, block_id: str) -> list:
        """Remove a block; removing a segment removes its pulses. Returns what was removed."""
        removed = []
        for i, s in enumerate(self.segments):
            if s.id == block_id:
                removed.append(self.segments.pop(i))
                removed += [p for p in self.pulses if p.segment_id == block_id]
                self.pulses = [p for p in self.pulses if p.segment_id != block_id]
                return removed
        for i, p in enumerate(self.pulses):
            if p.id == block_id:
                return [self.pulses.pop(i)]
        if self.measure is not None and self.measure.id == block_id:
            removed = [self.measure]
            self.measure = None
        return removed

    def move_segment(self, block_id: str, new_index: int) -> None:
        i = self.segment_index(block_id)
        seg = self.segments.pop(i)
        new_index = max(0, min(int(new_index), len(self.segments)))
        self.segments.insert(new_index, seg)

    def act_order_ok(self) -> bool:
        order = [ACTS.index(s.act) for s in self.segments]
        return all(a <= b for a, b in zip(order, order[1:]))

    # ------------------------------------------------------------------ io
    def to_dict(self) -> dict:
        blocks = [b.to_dict() for b in self.segments] + [p.to_dict() for p in self.pulses]
        if self.measure is not None:
            blocks.append(self.measure.to_dict())
        return {"bob_version": BOB_FILE_VERSION, "name": self.name,
                "description": self.description, "summary": self.summary, "station": self.station,
                "calibration": dict(self.calibration), "settings": self.settings.to_dict(),
                "blocks": blocks}

    @classmethod
    def from_dict(cls, d: dict) -> "Sequence":
        from ..blocks.registry import block_from_dict
        seq = cls(name=d.get("name", "Untitled"), description=d.get("description", ""),
                  summary=d.get("summary", ""),
                  station=d.get("station", "8QV1"), calibration=dict(d.get("calibration") or {}),
                  settings=ExperimentSettings.from_dict(d.get("settings") or {}))
        for bd in d.get("blocks", []):
            b = block_from_dict(bd)
            if isinstance(b, SegmentBlock):
                seq.segments.append(b)
            elif isinstance(b, PulseBlock):
                seq.pulses.append(b)
            elif isinstance(b, MeasureBlock):
                seq.measure = b
        return seq

    def save(self, path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path) -> "Sequence":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def clone(self) -> "Sequence":
        return Sequence.from_dict(self.to_dict())


def sweep_users_text(users) -> str:
    """'Quench › Duration, Hold › Duration' for a list of (block, field spec)."""
    return ", ".join(f"{b.name} › {spec.label}" for b, spec in users)
