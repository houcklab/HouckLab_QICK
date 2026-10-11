"""Readable one-line summaries of a run's config, for a lazy tree view. No Qt.

A real config (BSClean_BSGain) pretty-prints to ~12,900 lines, 98% of them two long
numeric arrays; the ~220 lines worth reading drown. ``describe`` turns any JSON value
into one summary line plus LAZY children, so the view materialises only what is opened,
and long numeric lists become a shape + min/max line (and a plottable ``array``).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Optional

import numpy as np

MAX_CHILDREN = 200     # never list more children than this under one node
INLINE_MAX = 16        # lists of scalars up to this length print on one line
STR_MAX = 200          # summary text is cut here; the tooltip keeps everything


class More:
    """Stand-in child for the elements beyond MAX_CHILDREN."""

    def __init__(self, n: int):
        self.n = n


@dataclass
class Node:
    summary: str                                   # the one-line Value column text
    kind: str                                      # dict|list|array|str|number|bool|null|more
    children: Optional[Callable[[], Iterator[tuple[str, Any]]]] = None   # lazy; None=leaf
    array: Optional[np.ndarray] = None             # set when the value is plottable
    tooltip: str = ""                              # full text when the summary is cut


def _is_num(v) -> bool:
    return isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool)


def _is_scalar(v) -> bool:
    return v is None or isinstance(v, (str, bool)) or _is_num(v)


def fmt_scalar(v) -> str:
    """JSON spelling for null/true/false, `.6g` for floats, ints as is, str quoted."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (float, np.floating)):
        return format(float(v), ".6g")
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    return json.dumps(v)


def _cut(text: str) -> tuple[str, str]:
    """(summary, tooltip): cut at STR_MAX, the full text kept only when it was cut."""
    return (text, "") if len(text) <= STR_MAX else (text[:STR_MAX - 1] + "…", text)


def _stats(a: np.ndarray, dtype: str) -> str:
    return f"{dtype}   min {np.nanmin(a):.3g}   max {np.nanmax(a):.3g}" if a.size else dtype


def _capped(pairs: list) -> Callable[[], Iterator[tuple[str, Any]]]:
    """Children generator: the first MAX_CHILDREN pairs, then one '... N more' row."""
    def gen():
        yield from pairs[:MAX_CHILDREN]
        if len(pairs) > MAX_CHILDREN:
            yield ("…", More(len(pairs) - MAX_CHILDREN))
    return gen


def _indexed(seq) -> Callable[[], Iterator[tuple[str, Any]]]:
    """Lazy children by index for a long sequence; the pairs are never built upfront."""
    def gen():
        for i in range(min(len(seq), MAX_CHILDREN)):
            yield (str(i), seq[i])
        if len(seq) > MAX_CHILDREN:
            yield ("…", More(len(seq) - MAX_CHILDREN))
    return gen


def describe(value: Any) -> Node:
    """One summary line + lazy children for any JSON-like value (rules in the module doc)."""
    if isinstance(value, More):
        return Node(f"... {value.n:,} more", "more")
    if isinstance(value, dict):
        n = len(value)
        return Node(f"{{{n} key{'s' if n != 1 else ''}}}", "dict",
                    _capped(list(value.items())) if n else None)
    if isinstance(value, np.ndarray):
        return _describe_ndarray(value)
    if isinstance(value, (list, tuple)):
        return _describe_list(value)
    if isinstance(value, str):
        summary, tip = _cut(value)
        return Node(summary, "str", tooltip=tip)
    if isinstance(value, bool):
        return Node(fmt_scalar(value), "bool")
    if value is None:
        return Node("null", "null")
    if _is_num(value):
        return Node(fmt_scalar(value), "number")
    summary, tip = _cut(repr(value))
    return Node(summary, "str", tooltip=tip)


def _describe_ndarray(a: np.ndarray) -> Node:
    """numpy arrays (the Data tab): summary straight off the array -- never tolist(),
    which costs seconds on an 8 x 100,000 shot array. 1-D and 2-D numeric are plottable;
    higher dimensions expand along the first axis into plottable slices."""
    if a.ndim == 0:
        return describe(a.item())
    numeric = a.dtype.kind in "iuf"
    shape = " x ".join(f"{n:,}" for n in a.shape)
    if a.ndim == 1 and a.size <= INLINE_MAX:
        summary, tip = _cut("[" + ", ".join(fmt_scalar(v) for v in a.tolist()) + "]")
        return Node(summary, "list", tooltip=tip)
    stats = _stats(a, str(a.dtype)) if numeric else str(a.dtype)
    plottable = numeric and a.ndim <= 2 and a.size > 0
    return Node(f"ndarray [{shape}] {stats}", "array" if plottable else "list",
                _indexed(a) if a.size else None,
                a.astype(float, copy=False) if plottable else None)


def _describe_list(seq) -> Node:
    n = len(seq)
    if n == 0:
        return Node("[]", "list")
    if all(_is_scalar(v) for v in seq):
        numeric = all(_is_num(v) for v in seq)
        if n <= INLINE_MAX:                         # short: one readable line, no children
            summary, tip = _cut("[" + ", ".join(fmt_scalar(v) for v in seq) + "]")
            return Node(summary, "list", tooltip=tip)
        if numeric:
            a = np.asarray(seq, dtype=float)
            dtype = "int" if all(isinstance(v, (int, np.integer)) for v in seq) else "float"
            return Node(f"list[{n:,}] {_stats(a, dtype)}", "array", _indexed(seq), a)
        kinds = sorted({type(v).__name__ for v in seq})
        return Node(f"list[{n:,}] {'/'.join(kinds)}", "list", _indexed(seq))
    if all(isinstance(v, (list, tuple)) and v and all(_is_num(x) for x in v) for v in seq):
        if len({len(v) for v in seq}) == 1:          # rectangular numeric -> 2-D array
            a = np.asarray(seq, dtype=float)
            dtype = "int" if all(isinstance(x, (int, np.integer)) for v in seq for x in v) \
                else "float"
            return Node(f"array [{a.shape[0]:,} x {a.shape[1]:,}] {_stats(a, dtype)}",
                        "array", _indexed(seq), a)
        return Node(f"[{n:,} lists]", "list", _indexed(seq))
    if all(isinstance(v, dict) for v in seq):
        return Node(f"[{n:,} dicts]", "list", _indexed(seq))
    if all(isinstance(v, (list, tuple)) for v in seq):          # e.g. confusion_matrix
        return Node(f"[{n:,} lists]", "list", _indexed(seq))
    return Node(f"[{n:,} items]", "list", _indexed(seq))


def find_paths(cfg: Any, text: str, limit: int = 500) -> list[tuple]:
    """Key paths (tuples of str) whose KEY or one-line summary contains ``text``.

    Case-insensitive. Containers match on their key only; leaves (scalars, strings,
    inline lists) also on their summary. Long numeric arrays are never descended into,
    and only the first MAX_CHILDREN children of any node are searched -- the same ones
    the tree can show -- so every returned path can be materialised.
    """
    needle = text.strip().lower()
    out: list[tuple] = []
    if not needle:
        return out

    def walk(value, path):
        if len(out) >= limit:
            return
        node = describe(value)
        key = path[-1].lower() if path else ""
        leafish = node.children is None
        if path and (needle in key or (leafish and needle in node.summary.lower())):
            out.append(path)
        if node.kind == "array" or node.children is None:
            return
        for k, v in node.children():
            if isinstance(v, More) or len(out) >= limit:
                break
            walk(v, path + (str(k),))

    walk(cfg, ())
    return out
