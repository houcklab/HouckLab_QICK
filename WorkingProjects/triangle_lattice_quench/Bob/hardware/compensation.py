"""IIR pre-distortion of FF waveforms, from triangle_lattice_quench/Helpers/Compensated_Pulse_Josh.py.

Kept: the filter (scipy.signal.lfilter with complex a/b coefficients, real part taken),
the per-qubit chain of coefficient files, cached loading, and the per-qubit asymptote correction
(comp_asymptote / true_asymptote).

Changed: the coefficient files and asymptote values come from the station folder
(station.json -> "compensation") instead of a hardcoded Z:\\ path and arrays in code, and
a Compensator with no files available says so instead of failing, so previews work
off the lab network.

Usage matches every working experiment (MottQuench, BSClean): pass the waveform RELATIVE
to its starting level, and the level as the offset:

    comp.apply(arr - init, init, qubit)
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np


@lru_cache(maxsize=None)
def _load_ab(path: str) -> np.ndarray:
    """IIR coefficients for one flux line, cached per file (loading from disk is slow)."""
    return np.loadtxt(path, dtype=np.complex128)


def apply_iir(ab: np.ndarray, waveform: np.ndarray) -> np.ndarray:
    from scipy.signal import lfilter
    a, b = ab
    return np.real(lfilter(b, a, waveform))


class Compensator:
    def __init__(self, files: dict, asymptote_scale: np.ndarray, iir_dir: Optional[Path]):
        self.files = {int(k): list(v) for k, v in (files or {}).items()}
        # per-qubit factor applied after filtering (None = no correction)
        self.asymptote_scale = np.asarray(asymptote_scale, float) if asymptote_scale is not None else None
        self.iir_dir = Path(iir_dir) if iir_dir else None

    @classmethod
    def from_station(cls, station) -> "Compensator":
        comp = station.data.get("compensation") or {}
        scale = None
        if comp.get("true_asymptote") and comp.get("comp_asymptote"):
            scale = np.asarray(comp["comp_asymptote"], float) / np.asarray(comp["true_asymptote"], float)
        return cls(comp.get("files", {}), scale, station.iir_dir())

    @classmethod
    def disabled(cls) -> "Compensator":
        return cls({}, None, None)

    def _paths(self, qubit: int) -> list:
        if self.iir_dir is None:
            return []
        return [self.iir_dir / f for f in self.files.get(int(qubit), [])]

    def available(self, qubit: Optional[int] = None) -> bool:
        """True when every coefficient file for ``qubit`` (or for all qubits) is on disk."""
        qubits = [qubit] if qubit is not None else list(self.files)
        if not qubits:
            return False
        return all(self._paths(q) and all(p.exists() for p in self._paths(q)) for q in qubits)

    def apply(self, waveform_rel: np.ndarray, offset: float, qubit: int) -> np.ndarray:
        """Compensate a waveform given relative to ``offset``; returns absolute gains."""
        w = np.asarray(waveform_rel, float)
        for p in self._paths(qubit):
            w = apply_iir(_load_ab(str(p)), w)
        if self.asymptote_scale is not None and 1 <= int(qubit) <= len(self.asymptote_scale):
            w = w * self.asymptote_scale[int(qubit) - 1]
        return w + float(offset)
