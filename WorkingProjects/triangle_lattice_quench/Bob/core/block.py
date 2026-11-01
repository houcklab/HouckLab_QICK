"""Block base classes and FieldSpec.

A block class declares its fields with ``FieldSpec``s. The palette, the inspector form,
the resolver and the validator are all driven by these specs, so adding a block type
means writing one class in ``Bob/blocks/``.

There are three kinds of block, set by which track they live on:

    SegmentBlock   the flux track: one time column, all FF channels (hold, ramp, beamsplitter)
    PulseBlock     one qubit lane, inside a segment (pi, pi/2, drive)
    MeasureBlock   the final column (MUX readout)
"""
from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass
from typing import Any, Callable, ClassVar, Optional

import numpy as np

from .params import FieldSource, Value, VectorSource, source_from_dict

ACTS = ("prep", "dynamics", "readout")
ACT_LABELS = {"prep": "Preparation", "dynamics": "Dynamics", "readout": "Beamsplitter + measure"}


@dataclass
class FieldSpec:
    name: str
    label: str
    ftype: str                       # float | int | str | choice | bool | qubit | qubits | vector
    default: Callable[[], FieldSource]
    unit: str = ""
    sources: tuple = ("value", "ref", "sweep")
    limits: Optional[tuple] = None   # (lo, hi) applied to every element
    choices: tuple = ()
    doc: str = ""
    template: bool = False           # its literal value fills {name} placeholders in Ref paths
    nullable: bool = False           # vector entries may be None (e.g. no intermediate jump)
    advanced: bool = False           # folded away in the inspector by default
    options: str = ""                # where the inspector finds choices: a calib path whose keys are the
                                     # options ("calib:drive_groups", may hold {placeholders}), or "readout_groups"

    @property
    def is_vector(self) -> bool:
        return self.ftype == "vector"

    def make_default(self) -> FieldSource:
        return self.default()


def vec_default(base_factory):
    return lambda: VectorSource(base_factory())


def short_id() -> str:
    return uuid.uuid4().hex[:8]


class Block:
    TYPE: ClassVar[str] = "Block"
    LABEL: ClassVar[str] = "Block"
    KIND: ClassVar[str] = "segment"
    FAMILY: ClassVar[str] = "Preparation"       # palette group
    DEFAULT_ACT: ClassVar[str] = "prep"
    ALLOWED_ACTS: ClassVar[tuple] = ACTS
    DESCRIPTION: ClassVar[str] = ""
    FIELDS: ClassVar[list] = []

    def __init__(self, name: Optional[str] = None, act: Optional[str] = None,
                 fields: Optional[dict] = None, id: Optional[str] = None,
                 segment_id: Optional[str] = None):
        self.id = id or short_id()
        self.name = name or self.LABEL
        self.act = act or self.DEFAULT_ACT
        self.segment_id = segment_id
        self.fields: dict[str, FieldSource] = {f.name: f.make_default() for f in self.FIELDS}
        if fields:
            for k, v in fields.items():
                if k in self.fields:
                    self.fields[k] = v

    # ------------------------------------------------------------------ specs
    @classmethod
    def spec(cls, name: str) -> FieldSpec:
        for f in cls.FIELDS:
            if f.name == name:
                return f
        raise KeyError(f"{cls.TYPE} has no field {name!r}")

    def set_field(self, name: str, source: FieldSource) -> None:
        self.spec(name)
        self.fields[name] = source

    def template_values(self) -> dict:
        """Literal values of template fields, used to fill {name} placeholders in Ref paths."""
        out = {}
        for f in self.FIELDS:
            src = self.fields.get(f.name)
            if f.template and isinstance(src, Value):
                out[f.name] = src.value
        return out

    # ------------------------------------------------------------------ copy / io
    def clone(self, new_id: bool = True) -> "Block":
        b = copy.deepcopy(self)
        if new_id:
            b.id = short_id()
        return b

    def to_dict(self) -> dict:
        d = {"type": self.TYPE, "id": self.id, "name": self.name,
             "fields": {k: v.to_dict() for k, v in self.fields.items()}}
        if self.KIND != "pulse":
            d["act"] = self.act
        if self.segment_id is not None:
            d["segment"] = self.segment_id
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Block":
        fields = {k: source_from_dict(v) for k, v in (d.get("fields") or {}).items()}
        # vector fields saved as plain sources get wrapped
        for f in cls.FIELDS:
            if f.is_vector and f.name in fields and not isinstance(fields[f.name], VectorSource):
                fields[f.name] = VectorSource(fields[f.name])
        return cls(name=d.get("name"), act=d.get("act"), fields=fields,
                   id=d.get("id"), segment_id=d.get("segment"))

    def __repr__(self) -> str:
        return f"<{self.TYPE} {self.name!r} {self.id}>"


# --------------------------------------------------------------------------------------
# Resolved data the compiler consumes. Blocks turn resolved params into these.
# --------------------------------------------------------------------------------------
@dataclass
class SegmentWave:
    """One segment's per-channel FF samples (uncompensated, applied gains)."""
    samples: np.ndarray              # shape (n_channels, length) float
    start_gains: np.ndarray          # level at the segment's first sample, per channel
    end_gains: np.ndarray            # level the segment ends on, per channel (FromPrev for the next)

    @property
    def length(self) -> int:
        return int(self.samples.shape[1])


@dataclass
class DriveSpec:
    qubit: int                       # 1-based qubit number (lane)
    freq_mhz: float                  # absolute drive frequency
    gain: float                      # DAC units, -32766..32766
    phase_deg: float
    sigma_us: float
    len_sigmas: float = 4.0
    relative_t: Any = "auto"         # "auto" or microseconds from segment start

    def length_us(self) -> float:
        return self.len_sigmas * self.sigma_us


class SegmentBlock(Block):
    KIND = "segment"

    def build(self, p: dict, ctx: "BuildContext") -> SegmentWave:  # pragma: no cover - abstract
        raise NotImplementedError


class PulseBlock(Block):
    KIND = "pulse"
    FAMILY = "Pulses"

    @property
    def qubit(self) -> int:
        """The qubit lane the pulse is on, or 0 when the field does not hold a usable number."""
        try:
            return int(getattr(self.fields.get("qubit"), "value", 0))
        except (TypeError, ValueError):
            return 0

    def drive(self, p: dict) -> DriveSpec:  # pragma: no cover - abstract
        raise NotImplementedError


class MeasureBlock(Block):
    KIND = "measure"
    FAMILY = "Readout"
    DEFAULT_ACT = "readout"
    ALLOWED_ACTS = ("readout",)


@dataclass
class BuildContext:
    """What a segment needs to build its samples."""
    n_channels: int
    samples_per_us: float
    prev_end: Optional[np.ndarray]   # previous segment's end gains (None for the first)

    def us_to_samples(self, us: float) -> int:
        return int(round(float(us) * self.samples_per_us))
