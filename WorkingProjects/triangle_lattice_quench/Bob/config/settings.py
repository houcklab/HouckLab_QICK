"""Experiment-wide settings: reps, relax delay, the sweep axes blocks can point at, and where runs are saved."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class SweepAxis:
    name: str
    start: float
    stop: float
    points: int
    unit: str = ""

    def values(self) -> np.ndarray:
        n = max(1, int(self.points))
        return np.linspace(float(self.start), float(self.stop), n)

    def to_dict(self) -> dict:
        return {"axis": self.name, "start": self.start, "stop": self.stop,
                "points": int(self.points), "unit": self.unit}

    @classmethod
    def from_dict(cls, d: dict) -> "SweepAxis":
        return cls(d["axis"], float(d["start"]), float(d["stop"]), int(d["points"]), d.get("unit", ""))


@dataclass
class ExperimentSettings:
    reps: int = 1000
    rounds: int = 1
    relax_delay_us: Optional[float] = None     # None = the station's default
    sweeps: list = field(default_factory=list)  # list[SweepAxis], outermost first
    save_folder: str = ""                       # where runs are saved; "" = the station's outer_folder

    def axis(self, name: str) -> Optional[SweepAxis]:
        for a in self.sweeps:
            if a.name == name:
                return a
        return None

    def n_points(self) -> int:
        n = 1
        for a in self.sweeps:
            n *= max(1, int(a.points))
        return n

    def point(self, flat_index: int = 0) -> dict:
        """Sweep values at one point of the (outer-to-inner) grid, as {axis: value}."""
        if not self.sweeps:
            return {}
        shape = [max(1, int(a.points)) for a in self.sweeps]
        idx = np.unravel_index(int(flat_index) % int(np.prod(shape)), shape)
        return {a.name: float(a.values()[i]) for a, i in zip(self.sweeps, idx)}

    def iter_points(self):
        for k in range(self.n_points()):
            yield k, self.point(k)

    def to_dict(self) -> dict:
        d = {"reps": int(self.reps), "rounds": int(self.rounds),
             "sweeps": [a.to_dict() for a in self.sweeps]}
        if self.relax_delay_us is not None:
            d["relax_delay_us"] = self.relax_delay_us
        if self.save_folder:
            d["save_folder"] = self.save_folder
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ExperimentSettings":
        return cls(reps=int(d.get("reps", 1000)), rounds=int(d.get("rounds", 1)),
                   relax_delay_us=d.get("relax_delay_us"),
                   sweeps=[SweepAxis.from_dict(a) for a in d.get("sweeps", [])],
                   save_folder=str(d.get("save_folder", "") or ""))
