"""CalibrationStore: read-only access to qubit_parameters.json, rewritten from build_config.QubitParams.

The file format is unchanged. Differences from QubitParams:

* Lookups take explicit paths (``drive_groups/readout_3800/entries/3/Qubit/Gain``) and
  return deep copies; a missing key names the path walked and what was available.
* Nothing parses a qubit index out of an entry name. Readout entries are looked up by
  the qubit number the caller gives.
* The file's SHA-256 is kept so a saved sequence can tell when the file has changed
  (see calib_drift.py for the value-by-value comparison).
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Optional


class CalibrationError(KeyError):
    pass


class CalibrationStore:
    def __init__(self, data: dict, path: Optional[str] = None, sha256: Optional[str] = None):
        self.data = data
        self.path = str(path) if path else None
        self.sha256 = sha256

    @classmethod
    def load(cls, path) -> "CalibrationStore":
        raw = Path(path).read_bytes()
        return cls(json.loads(raw.decode("utf-8")), path=str(path), sha256=hashlib.sha256(raw).hexdigest())

    @classmethod
    def empty(cls) -> "CalibrationStore":
        return cls({"drive_groups": {}, "ff_groups": {}})

    # ------------------------------------------------------------------ lookup
    def get(self, key_path: str):
        keys = [k for k in str(key_path).split("/") if k]
        node = self.data
        for i, k in enumerate(keys):
            if not isinstance(node, dict) or k not in node:
                where = "/".join(keys[:i]) or "(top)"
                avail = sorted(node) if isinstance(node, dict) else type(node).__name__
                raise CalibrationError(f"calib:{key_path}: {k!r} not found under {where}; available: {avail}")
            node = node[k]
        return copy.deepcopy(node)

    def has(self, key_path: str) -> bool:
        try:
            self.get(key_path)
            return True
        except CalibrationError:
            return False

    def children(self, key_path: str = "") -> list:
        """(key, is_branch, preview) for browsing the file in the GUI."""
        node = self.get(key_path) if key_path else self.data
        if not isinstance(node, dict):
            return []
        out = []
        for k, v in node.items():
            if k.startswith("_"):
                continue
            out.append((k, isinstance(v, dict), _preview(v)))
        return out

    def readout_groups(self) -> list:
        return sorted(g for g, v in (self.data.get("drive_groups") or {}).items()
                      if isinstance(v, dict) and "FF_Readouts" in v)

    def entries(self, group: str) -> list:
        return list(((self.data.get("drive_groups") or {}).get(group) or {}).get("entries", {}).keys())

    # ------------------------------------------------------------------ readout
    def readout_config(self, group: str, qubits: list, res_LO: float) -> dict:
        """MUX readout settings for ``qubits`` from drive_groups/<group>, matching QubitParams.res_config."""
        entries = [self.get(f"drive_groups/{group}/entries/{q}") for q in qubits]
        ros = [e["Readout"] for e in entries]
        n = len(qubits)
        cfg = {
            "res_gains": [r["Gain"] / 32766.0 * n for r in ros],
            "res_freqs": [r["Frequency"] - res_LO for r in ros],
            "readout_lengths": [r["Readout_Time"] for r in ros],
            "adc_trig_delays": [r["ADC_Offset"] for r in ros],
            "ro_chs": list(range(n)),
            "Qubit_Readout_List": list(qubits),
        }
        sss = [e.get("SingleShot") for e in entries]
        if n and all(sss):
            cfg["angle"] = [s["angle"] for s in sss]
            cfg["threshold"] = [s["threshold"] for s in sss]
            cfg["confusion_matrix"] = [[[1 - s["ng_contrast"], s["ne_contrast"]],
                                        [s["ng_contrast"], 1 - s["ne_contrast"]]] for s in sss]
        return cfg


def _preview(v) -> str:
    if isinstance(v, dict):
        return f"{len(v)} item{'s' if len(v) != 1 else ''}"
    if isinstance(v, list):
        s = json.dumps(v)
        return s if len(s) <= 60 else s[:57] + "…"
    if isinstance(v, float):
        return f"{v:.6g}"
    return str(v)
