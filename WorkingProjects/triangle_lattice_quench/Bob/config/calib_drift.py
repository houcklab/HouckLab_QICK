"""Detect calibration values a sequence uses that have changed since it was saved.

When a sequence is saved, Bob records every calibration value it read (flattened to leaf
paths, e.g. ``drive_groups/readout_3800/entries/3/Qubit/Frequency``) in the file's
``calibration.used``. On open, or after picking another calibration file, the values read
now are compared against that record. Each changed value becomes a warning on the block
that uses it. Saving again records the current values, which accepts the change.

Values the sequence didn't use when it was saved (a block added since) are not compared.
"""
from __future__ import annotations

import math
from typing import Optional

from .problems import Problem

MAX_LISTED = 3          # changed vector entries listed in one message


def flatten(path: str, value, out: Optional[dict] = None) -> dict:
    """{leaf path: value}; dicts are walked, lists and scalars are leaves."""
    out = {} if out is None else out
    if isinstance(value, dict):
        for k, v in value.items():
            flatten(f"{path}/{k}", v, out)
    else:
        out[path] = value
    return out


def used_values(res) -> dict:
    """Every calibration leaf this resolved sequence read, as a JSON-ready dict."""
    out: dict = {}
    for key, value, *_ in getattr(res, "calib_reads", []):
        flatten(key, value, out)
    return out


def _same(a, b) -> bool:
    """Equal, treating numbers that differ only by float rounding as equal."""
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return math.isclose(float(a), float(b), rel_tol=1e-12, abs_tol=1e-12)
    return a == b


def _short(path: str, keep: int = 5) -> str:
    parts = path.split("/")
    return path if len(parts) <= keep else "…/" + "/".join(parts[-keep:])


def _num(v) -> str:
    if isinstance(v, float):
        return f"{v:.6g}"
    return str(v)


def describe_change(path: str, old, new, n_channels: int = 0) -> str:
    if isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
        diffs = [i for i, (a, b) in enumerate(zip(old, new)) if not _same(a, b)]
        name = (lambda i: f"Q{i + 1}") if len(old) == n_channels else (lambda i: f"[{i}]")
        shown = ", ".join(f"{name(i)} {_num(old[i])} → {_num(new[i])}" for i in diffs[:MAX_LISTED])
        more = f" and {len(diffs) - MAX_LISTED} more" if len(diffs) > MAX_LISTED else ""
        return f"{_short(path)}: {shown}{more}"
    return f"{_short(path)}: {_num(old)} → {_num(new)}"


def changed(baseline: dict, res) -> list:
    """[(leaf path, old, new)] for values used now that differ from the saved record."""
    now = used_values(res)
    return [(k, baseline[k], v) for k, v in now.items() if k in baseline and not _same(baseline[k], v)]


def drift_problems(baseline: Optional[dict], res) -> list:
    """One warning per (block, changed value) it reads."""
    if not baseline or res is None:
        return []
    diffs = {k: (old, new) for k, old, new in changed(baseline, res)}
    if not diffs:
        return []
    probs, seen = [], set()
    for key, value, block_id, fld, name in res.calib_reads:
        for leaf in flatten(key, value):
            if leaf in diffs and (block_id, leaf) not in seen:
                seen.add((block_id, leaf))
                old, new = diffs[leaf]
                change = describe_change(leaf, old, new, res.n_channels)
                probs.append(Problem("warning", f"Calibration changed since this sequence was saved: {change}. "
                                                "Save to accept the new value.", block_id, fld, name))
    return probs
