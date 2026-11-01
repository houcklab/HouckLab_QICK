"""Resolver: turn every block field into a number for one sweep point.

Order of precedence (lowest to highest): station, calibration store, experiment settings,
block fields. A field's source decides where its value comes from; the resolver only
follows it. Segments are resolved in time order so ``FromPrev`` can use the previous
segment's end gains, and each segment's samples are built here so that chain holds.

Every calibration value read is also recorded in ``ResolvedSequence.calib_reads``, which
the calibration-change check (calib_drift.py) compares against what the file was saved with.

Nothing here touches Qt, disk (beyond what the stores already loaded) or hardware.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from ..core.block import Block, BuildContext, DriveSpec, FieldSpec, SegmentWave
from ..core.params import FromPrev, Ref, Sweep, Value, VectorSource
from ..core.sequence import Sequence
from .calibration import CalibrationError, CalibrationStore
from .problems import Problem
from .station import Station


@dataclass
class ResolvedSegment:
    block: Block
    params: dict
    wave: Optional[SegmentWave]
    ok: bool


@dataclass
class ResolvedPulse:
    block: Block
    params: dict
    drive: Optional[DriveSpec]
    segment_index: int
    ok: bool


@dataclass
class ResolvedMeasure:
    block: Block
    params: dict
    readout: Optional[dict]
    ok: bool


@dataclass
class ResolvedSequence:
    point: dict
    segments: list = field(default_factory=list)
    pulses: list = field(default_factory=list)
    measure: Optional[ResolvedMeasure] = None
    problems: list = field(default_factory=list)
    calib_reads: list = field(default_factory=list)   # [(key_path, value, block_id, field, block_name)]
    n_channels: int = 8
    samples_per_us: float = 3440.64

    @property
    def ok(self) -> bool:
        return not any(p.level == "error" for p in self.problems)

    def params_by_block(self) -> dict:
        out = {}
        for r in self.segments + self.pulses + ([self.measure] if self.measure else []):
            out[r.block.id] = r.params
        return out


class _FieldError(Exception):
    pass


class Resolver:
    def __init__(self, station: Station, calib: CalibrationStore):
        self.station = station
        self.calib = calib
        # set during resolve(): where calibration reads are recorded, and which block/field is being read
        self._out: Optional[ResolvedSequence] = None
        self._block: Optional[Block] = None
        self._field: Optional[str] = None

    # ------------------------------------------------------------------ public
    def resolve(self, seq: Sequence, point: Optional[dict] = None) -> ResolvedSequence:
        point = dict(point if point is not None else seq.settings.point(0))
        n = self.station.n_channels
        out = ResolvedSequence(point=point, n_channels=n, samples_per_us=self.station.samples_per_us)
        self._out, self._block, self._field = out, None, None
        defined_axes = {a.name for a in seq.settings.sweeps}

        prev_end = None
        for seg in seq.segments:
            params, ok = self._resolve_fields(seg, point, defined_axes, prev_end, out.problems)
            wave = None
            if ok:
                try:
                    wave = seg.build(params, BuildContext(n, self.station.samples_per_us, prev_end))
                except Exception as exc:  # a block's own consistency check
                    ok = False
                    out.problems.append(Problem("error", str(exc), seg.id, None, seg.name))
            out.segments.append(ResolvedSegment(seg, params, wave, ok))
            if wave is not None:
                prev_end = wave.end_gains

        index_of = {s.id: i for i, s in enumerate(seq.segments)}
        for pulse in seq.pulses:
            params, ok = self._resolve_fields(pulse, point, defined_axes, None, out.problems)
            drive = None
            if ok:
                try:
                    drive = pulse.drive(params)
                except Exception as exc:
                    ok = False
                    out.problems.append(Problem("error", str(exc), pulse.id, None, pulse.name))
            si = index_of.get(pulse.segment_id, -1)
            if si < 0:
                ok = False
                out.problems.append(Problem("error", "this pulse is not inside a segment", pulse.id, None, pulse.name))
            out.pulses.append(ResolvedPulse(pulse, params, drive, si, ok))

        if seq.measure is not None:
            m = seq.measure
            params, ok = self._resolve_fields(m, point, defined_axes, None, out.problems)
            readout = None
            if ok:
                try:
                    readout = self.calib.readout_config(params["readout_group"], list(params["qubits"]),
                                                        float(self.station["res_LO"]))
                    # readout_config reads these directly rather than through a Ref, so record them here
                    for q in params["qubits"]:
                        for part in ("Readout", "SingleShot"):
                            key = f"drive_groups/{params['readout_group']}/entries/{q}/{part}"
                            if self.calib.has(key):
                                out.calib_reads.append((key, self.calib.get(key), m.id, "qubits", m.name))
                except CalibrationError as exc:
                    ok = False
                    out.problems.append(Problem("error", _msg(exc), m.id, "qubits", m.name))
            out.measure = ResolvedMeasure(m, params, readout, ok)
        return out

    # ------------------------------------------------------------------ fields
    def _resolve_fields(self, block: Block, point: dict, axes: set, prev_end, problems: list):
        params, ok = {}, True
        tvals = block.template_values()
        for spec in block.FIELDS:
            src = block.fields.get(spec.name)
            self._block, self._field = block, spec.name
            try:
                params[spec.name] = self._resolve_one(spec, src, tvals, point, axes, prev_end)
            except _FieldError as exc:
                ok = False
                params[spec.name] = None
                problems.append(Problem("error", str(exc), block.id, spec.name, block.name))
        return params, ok

    def _resolve_one(self, spec: FieldSpec, src, tvals, point, axes, prev_end):
        if spec.is_vector:
            vs = src if isinstance(src, VectorSource) else VectorSource(src)
            raw = self._source_value(spec, vs.base, tvals, point, axes, prev_end)
            vec = self._as_vector(spec, raw)
            for k, v in vs.overrides.items():
                if not 0 <= int(k) < len(vec):
                    raise _FieldError(f"override index {k} is outside {len(vec)} channels")
                vec[int(k)] = None if v is None else float(v)
            return vec
        raw = self._source_value(spec, src, tvals, point, axes, prev_end)
        return self._coerce(spec, raw)

    def _source_value(self, spec, src, tvals, point, axes, prev_end):
        if isinstance(src, Value):
            return src.value
        if isinstance(src, Ref):
            try:
                ref = src.filled(tvals)
            except KeyError as exc:
                raise _FieldError(_msg(exc)) from None
            try:
                if ref.store == "station":
                    v = self.station.get(ref.key_path)
                else:
                    v = self.calib.get(ref.key_path)
                    if self._out is not None and self._block is not None:
                        self._out.calib_reads.append((ref.key_path, v, self._block.id, self._field,
                                                      self._block.name))
            except KeyError as exc:
                raise _FieldError(_msg(exc)) from None
            return _scaled(v, ref.scale)
        if isinstance(src, Sweep):
            if src.axis not in axes:
                raise _FieldError(f"sweep axis ‹{src.axis}› is not defined in the experiment settings")
            return point[src.axis]
        if isinstance(src, FromPrev):
            if prev_end is None:
                raise _FieldError("'from previous segment' needs a segment before this one")
            return list(np.asarray(prev_end, float))
        raise _FieldError("no source set")

    def _as_vector(self, spec: FieldSpec, raw) -> list:
        n = self.station.n_channels
        if raw is None or np.isscalar(raw):
            vals = [raw] * n
        else:
            vals = list(raw)
        if len(vals) != n:
            raise _FieldError(f"expected {n} values (one per FF channel), got {len(vals)}")
        out = []
        for v in vals:
            if v is None:
                if not spec.nullable:
                    raise _FieldError("an entry is empty (None)")
                out.append(None)
            else:
                try:
                    out.append(float(v))
                except (TypeError, ValueError):
                    raise _FieldError(f"{v!r} is not a number") from None
        return out

    def _coerce(self, spec: FieldSpec, raw):
        t = spec.ftype
        try:
            if t == "float":
                return float(raw)
            if t == "int":
                return int(round(float(raw)))
            if t == "qubit":
                return int(raw)
            if t == "qubits":
                if isinstance(raw, str):
                    raw = [x for x in raw.replace(",", " ").split() if x]
                return [int(x) for x in raw]
            if t == "bool":
                return bool(raw)
            if t == "choice":
                if spec.choices and raw not in spec.choices:
                    raise _FieldError(f"{raw!r} is not one of {', '.join(spec.choices)}")
                return raw
            return raw if raw is not None else ""
        except _FieldError:
            raise
        except (TypeError, ValueError):
            raise _FieldError(f"{raw!r} is not a valid {t}") from None


def _scaled(v, scale: float):
    if scale == 1.0:
        return v
    if isinstance(v, (int, float)):
        return v * scale
    if isinstance(v, list):
        return [None if x is None else x * scale for x in v]
    raise _FieldError(f"cannot scale {type(v).__name__} by {scale}")


def _msg(exc) -> str:
    s = str(exc)
    return s[1:-1] if len(s) > 1 and s[0] == s[-1] and s[0] in "'\"" else s
