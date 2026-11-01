"""Backend interface: a resolved sequence in, a runnable program description out.

A backend owns everything device-specific. ``tlq_backend`` is the triangle-lattice one;
another device needs a new backend and a station folder, not changes to the core.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np


class CompileError(Exception):
    def __init__(self, message: str, problems: Optional[list] = None):
        super().__init__(message)
        self.problems = problems or []


@dataclass
class CompiledDrive:
    qubit: int
    freq_mhz: float
    gain: float
    phase_deg: float
    sigma_us: float
    length_us: float
    t_us: float                     # on the drive clock (0 = start of the FF body)
    segment_index: int
    block_id: str
    block_name: str


@dataclass
class CompiledProgram:
    """Everything needed to build the QICK program, plus what the preview draws."""
    samples_per_us: float
    ff_raw: np.ndarray              # (n_ch, N) applied gains before compensation
    ff: np.ndarray                  # (n_ch, N) what is uploaded (compensated if available)
    init_gains: np.ndarray
    readout_gains: np.ndarray
    segment_bounds: list            # body sample index where each segment starts, plus the end
    segment_names: list
    segment_acts: list
    segment_ids: list
    channel_delays: np.ndarray      # per-channel head delay in samples
    drives: list                    # list[CompiledDrive]
    qick_cfg: dict                  # the cfg dict BobProgram reads
    compensated: bool
    notes: list = field(default_factory=list)

    @property
    def n_samples(self) -> int:
        return int(self.ff.shape[1])

    @property
    def body_us(self) -> float:
        return self.n_samples / self.samples_per_us

    def time_axis_us(self) -> np.ndarray:
        return np.arange(self.n_samples) / self.samples_per_us


class Backend:
    name = "backend"

    def compile(self, seq, resolved) -> CompiledProgram:  # pragma: no cover - interface
        raise NotImplementedError
