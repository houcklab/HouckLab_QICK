"""Field sources: where a block field gets its value from.

Every block field holds one of four sources:

    Value(x)        a literal typed by the user
    Ref(path)       a pointer into the calibration store or the station, resolved at run time
    Sweep(axis)     the current value of an experiment sweep axis
    FromPrev()      the previous flux segment's end gains (vector fields on segments only)

Per-qubit (vector) fields wrap a base source in ``VectorSource`` and may override single
entries with literals, mirroring the ``FF_override`` rule of qubit_parameters.json.

Ref paths look like ``calib:drive_groups/{readout_group}/entries/{qubit}/Qubit/Frequency``
or ``station:res_length``. ``{name}`` placeholders are filled from the block's own
literal fields (qubit, readout_group, ...) before the lookup.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Union

import numpy as np

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


@dataclass(frozen=True)
class Value:
    value: Any

    kind = "value"

    def to_dict(self) -> dict:
        return {"value": to_plain(self.value)}

    def describe(self) -> str:
        return f"{format_value(self.value)}"


@dataclass(frozen=True)
class Ref:
    path: str
    scale: float = 1.0

    kind = "ref"

    @property
    def store(self) -> str:
        return self.path.split(":", 1)[0] if ":" in self.path else "calib"

    @property
    def key_path(self) -> str:
        return self.path.split(":", 1)[1] if ":" in self.path else self.path

    def filled(self, values: dict) -> "Ref":
        """Return a copy with ``{name}`` placeholders filled from ``values``."""
        def sub(m):
            name = m.group(1)
            if name not in values:
                raise KeyError(f"placeholder {{{name}}} in {self.path!r} has no value")
            return str(values[name])
        return Ref(_PLACEHOLDER.sub(sub, self.path), self.scale)

    def to_dict(self) -> dict:
        d = {"ref": self.path}
        if self.scale != 1.0:
            d["scale"] = self.scale
        return d

    def describe(self) -> str:
        s = self.path
        if self.scale != 1.0:
            s += f" × {self.scale:g}"
        return s


@dataclass(frozen=True)
class Sweep:
    axis: str

    kind = "sweep"

    def to_dict(self) -> dict:
        return {"sweep": self.axis}

    def describe(self) -> str:
        return f"sweep ‹{self.axis}›"


@dataclass(frozen=True)
class FromPrev:
    kind = "from_prev"

    def to_dict(self) -> dict:
        return {"from_prev": True}

    def describe(self) -> str:
        return "from previous segment"


Source = Union[Value, Ref, Sweep, FromPrev]


@dataclass
class VectorSource:
    """A per-qubit vector: a base source plus literal overrides for single entries."""
    base: Source
    overrides: dict = field(default_factory=dict)  # {index (0-based): value}

    kind = "vector"

    def to_dict(self) -> dict:
        d = {"base": self.base.to_dict()}
        if self.overrides:
            d["overrides"] = {str(k): to_plain(v) for k, v in sorted(self.overrides.items())}
        return d

    def describe(self) -> str:
        s = self.base.describe()
        if self.overrides:
            s += f" (+{len(self.overrides)} override{'s' if len(self.overrides) > 1 else ''})"
        return s


FieldSource = Union[Value, Ref, Sweep, FromPrev, VectorSource]


def base_source(src: FieldSource) -> Source:
    """The underlying source of a field, unwrapping a per-qubit VectorSource."""
    return src.base if isinstance(src, VectorSource) else src


def source_from_dict(d: dict) -> FieldSource:
    if not isinstance(d, dict):
        return Value(d)
    if "base" in d:
        return VectorSource(source_from_dict(d["base"]),
                            {int(k): v for k, v in (d.get("overrides") or {}).items()})
    if "ref" in d:
        return Ref(d["ref"], float(d.get("scale", 1.0)))
    if "sweep" in d:
        return Sweep(d["sweep"])
    if d.get("from_prev"):
        return FromPrev()
    if "value" in d:
        return Value(d["value"])
    raise ValueError(f"not a field source: {d!r}")


def to_plain(v):
    """JSON-friendly copy (numpy scalars/arrays -> python)."""
    if isinstance(v, np.ndarray):
        return v.tolist()
    if isinstance(v, np.generic):
        return v.item()
    if isinstance(v, (list, tuple)):
        return [to_plain(x) for x in v]
    return v


def format_value(v) -> str:
    """Compact display text for a literal (6 significant figures)."""
    if isinstance(v, float):
        return f"{v:.6g}"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(format_value(x) for x in v) + "]"
    return str(v)
