"""Station: everything fixed about one setup (channels, mixers, LOs, timing constants).

Loaded from ``library/stations/<name>/station.json``. Block fields can point at station
values with ``Ref("station:<key>")``.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Optional

LIBRARY = Path(__file__).resolve().parents[1] / "library"
STATIONS_DIR = LIBRARY / "stations"


class Station:
    def __init__(self, data: dict, folder: Optional[Path] = None):
        self.data = data
        self.folder = Path(folder) if folder else None

    # ------------------------------------------------------------------ loading
    @classmethod
    def load(cls, name_or_path) -> "Station":
        p = Path(name_or_path)
        if not p.suffix:                          # a station name
            p = STATIONS_DIR / str(name_or_path) / "station.json"
        elif p.is_dir():
            p = p / "station.json"
        if not p.exists():
            raise FileNotFoundError(f"station file not found: {p}")
        return cls(json.loads(p.read_text(encoding="utf-8")), folder=p.parent)

    @staticmethod
    def available() -> list:
        if not STATIONS_DIR.exists():
            return []
        return sorted(d.name for d in STATIONS_DIR.iterdir() if (d / "station.json").exists())

    # ------------------------------------------------------------------ access
    @property
    def name(self) -> str:
        return self.data.get("name", "station")

    def __getitem__(self, key):
        return self.data[key]

    def get(self, key_path: str, default=None):
        node = self.data
        for k in [x for x in key_path.split("/") if x]:
            if isinstance(node, dict) and k in node:
                node = node[k]
            else:
                if default is not None:
                    return default
                raise KeyError(f"station:{key_path}: {k!r} not found; available: "
                               f"{sorted(node) if isinstance(node, dict) else type(node).__name__}")
        return copy.deepcopy(node)

    @property
    def n_channels(self) -> int:
        return int(self.data.get("n_ff_channels", len(self.data.get("fast_flux_chs", [])) or 8))

    @property
    def samples_per_us(self) -> float:
        # FF DAC sample rate: 16 samples per cycle of the 215.04 MHz fabric clock
        return float(self.data.get("samples_per_us", 16 * 215.04))

    @property
    def cycle_us(self) -> float:
        """One fabric cycle (16 FF samples), the granularity of tProc timing."""
        return 16.0 / self.samples_per_us

    def iir_dir(self) -> Optional[Path]:
        comp = self.data.get("compensation") or {}
        if not comp or self.folder is None:
            return None
        return (self.folder / comp.get("iir_dir", "iir")).resolve()

    def to_dict(self) -> dict:
        return copy.deepcopy(self.data)
