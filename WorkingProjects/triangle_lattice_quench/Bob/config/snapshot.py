"""Snapshot: a readable record saved next to every run (``_bob_snapshot.json``).

Holds the sequence file (including its summary), the station, the calibration file's path
and hash, and the resolved numbers at the first ``max_points`` sweep points. A run saves the
first point here; the .h5 holds every point (runner/save.py, ``resolved/``) and the inputs
needed to run it again.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

import numpy as np

from .. import __version__
from ..core.params import to_plain
from ..core.sequence import Sequence
from .calibration import CalibrationStore
from .resolver import Resolver
from .station import Station


def make_snapshot(seq: Sequence, station: Station, calib: CalibrationStore, max_points: int | None = None) -> dict:
    resolver = Resolver(station, calib)
    points = []
    for k, pt in seq.settings.iter_points():
        if max_points is not None and k >= max_points:
            break
        r = resolver.resolve(seq, pt)
        resolved_blocks = r.segments + r.pulses + ([r.measure] if r.measure else [])
        points.append({
            "index": k,
            "point": pt,
            "blocks": {f"{x.block.name} [{x.block.id}]": _clean(x.params) for x in resolved_blocks},
            "readout": _clean(r.measure.readout) if r.measure else None,
            "problems": [str(p) for p in r.problems],
        })
    return {
        "bob_version": __version__,
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
        "sequence": seq.to_dict(),
        "station": station.to_dict(),
        "calibration": {"path": calib.path, "sha256": calib.sha256},
        "points": points,
    }


def save_snapshot(snapshot: dict, path) -> None:
    Path(path).write_text(json.dumps(snapshot, indent=1), encoding="utf-8")


def _clean(d):
    if d is None:
        return None
    if isinstance(d, dict):
        return {k: _clean(v) for k, v in d.items()}
    if isinstance(d, np.ndarray):
        return d.tolist()
    return to_plain(d)
