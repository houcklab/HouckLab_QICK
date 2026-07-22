"""Pure (non-Qt) logic shared across tabs.

Three clusters:
  * config / entry helpers that wrap ``build_config`` (``build_cfg_for_qubit``
    and friends) plus the ``build_config`` resolver aliases re-exported here so
    tabs import them from one place;
  * the recenter-and-zoom step function and its GUI-only param-key constants;
  * the qubit_parameters diff machinery used by the Save dialog and the
    dirty-styling in the table tabs, and the JSON pretty-printers.

This layer imports only stdlib / third-party (+ ``build_config`` and the
``state`` foundation). It pulls ``_confusion_matrix_for`` from ``state`` (its
canonical home, since ``CalibState`` also calls it); ``CalibState`` itself is
referenced only via string annotations, so there is no module-level
helpers->state back-edge beyond that one symbol.
"""
from __future__ import annotations

import json
import re
from typing import Optional, TYPE_CHECKING

from WorkingProjects.triangle_lattice_quench.build_config import (
    build_config,
    JSON_PATH         as BUILD_CONFIG_JSON_PATH,
    _deref_base       as _build_deref_base,
    _resolve_readout  as _build_resolve_readout,
    _resolve_drive    as _build_resolve_drive,
    _resolve_ramp     as _build_resolve_ramp,
    _resolve_dynamics as _build_resolve_dynamics,
)

from .state import _confusion_matrix_for

if TYPE_CHECKING:  # avoid a runtime helpers->state edge beyond _confusion_matrix_for
    from .state import CalibState

# build_config and its private resolver aliases are re-exported here so the tab
# modules import them from one place; list them in __all__ so they read as a
# deliberate re-export rather than dead imports.
__all__ = [
    "build_config",
    "BUILD_CONFIG_JSON_PATH",
    "_build_deref_base",
    "_build_resolve_readout",
    "_build_resolve_drive",
    "_build_resolve_ramp",
    "_build_resolve_dynamics",
    "build_cfg_for_qubit",
    "_readout_qubit_for_entry",
    "_mux_readout_list",
    "_pulse_chain_entries",
    "DAC_GAIN_MAX",
    "ITER_PARAM_KEYS",
    "recenter_zoom_step",
    "_values_differ",
    "_is_suspicious_change",
    "_walk_entry_diff",
    "_diff_entries",
    "_diff_base_params",
    "_fmt_diff_value",
    "_field_importance",
    "_leaf_at_path",
    "_path_is_dirty",
    "_entry_touched_paths",
    "_diff_path_set",
    "_snapshot_calibration_diff",
    "_make_jsonable",
    "_collapse_scalar_arrays",
    "dumps_pretty",
    "dump_pretty",
]


# ---------------------------------------------------------------------------
# Config / entry helpers
# ---------------------------------------------------------------------------


def _readout_qubit_for_entry(name: str) -> str:
    """Parse the leading digits of a drive-entry name to get the readout qubit.

    Convention used by AutoCalib: a drive entry like ``'1_3800+'`` belongs to
    readout qubit ``'1'``; an entry whose name has no leading digits falls
    back to the entry name itself.
    """
    m = re.match(r"^(\d+)", str(name))
    return m.group(1) if m else str(name)


def _mux_readout_list(state: "CalibState", target_ro_q: str) -> list[str]:
    """Target-first MUX list for ReadoutOpt / PulseOpt / SingleShot."""
    others = [q for q in (state.mux_readouts or []) if q != target_ro_q]
    return [target_ro_q] + others


def _pulse_chain_entries(state: "CalibState", target_entry: str) -> list[str]:
    """Build the pulse chain for PulseOpt: prefix in JSON order, target last.

    Walks the active drive group's entries dict in insertion order; appends
    each entry whose parsed qubit is in ``state.pulse_chain`` AND that
    appears before the target. Target is appended last so PulseOpt's swept
    qubit sits at qubit_sweep_index = len(prefix). Returns [target] if the
    drive group is unset or has no entries.
    """
    jd = state.qubit_parameters_json or {}
    dg = state.current_drive_group or ""
    if not dg:
        return [target_entry]
    entries = list((jd.get("drive_groups") or {}).get(dg, {}).get("entries", {}).keys())
    selection = set(state.pulse_chain or [])
    chain: list[str] = []
    for ename in entries:
        if ename == target_entry:
            break  # stop at target — anything after it isn't a precursor
        if _readout_qubit_for_entry(ename) in selection:
            chain.append(ename)
    return chain + [target_entry]


def build_cfg_for_qubit(state: "CalibState", Q: str, *,
                        qubit_pulse: Optional[list] = None,
                        qubit_readout: Optional[list] = None,
                        readout_group: Optional[str] = None,
                        overrides: Optional[dict] = None) -> dict:
    """GUI-side wrapper around ``build_config`` for single-qubit stages.

    Routes through the canonical pipeline (qubit_parameters.json -> build_config
    -> flat cfg) so GUI runs match external scripts. Layers on per-readout
    SingleShot calibration (angle/threshold/confusion_matrix) read from the
    JSON entry's Readout block, then applies stage-form overrides last.

    ``qubit_pulse`` defaults to ``[Q]`` (the drive resolver finds it inside the
    readout group's entry); pass an explicit list to override.

    ``qubit_readout`` defaults to ``[Q]``. AutoCalib passes an explicit value
    when iterating drive-group rows whose entry name (e.g. ``'1_3800+'``)
    differs from the readout-qubit label (``'1'``).
    """
    Q = str(Q)
    rg = readout_group or state.current_readout_group or None
    qp = list(qubit_pulse) if qubit_pulse is not None else [Q]
    qr = list(qubit_readout) if qubit_readout is not None else [Q]

    cfg = build_config(
        Qubit_Readout=qr,
        Qubit_Pulse=qp,
        Readout_Point=rg,
        jd=state.qubit_parameters_json or None,   # falls back to disk if None
    )

    # SingleShot cals — build_config does not promote angle/threshold/confusion_matrix
    # to top-level cfg keys; downstream experiments (notably SweepExperimentND's
    # population_corrected branch) require them. One entry per qubit in qr so
    # MUX stages (qr len > 1) have a matching-length list.
    jd = state.qubit_parameters_json or {}
    angles, thresholds, confusion_matrices = [], [], []
    for ro_key in (qr if qr else [Q]):
        ro_entry = {}
        if rg:
            ro_entry = (jd.get("readout_groups", {})
                          .get(rg, {})
                          .get("entries", {})
                          .get(str(ro_key), {})
                          .get("Readout", {})) or {}
        angles.append(float(ro_entry.get("angle", 0.0)))
        thresholds.append(float(ro_entry.get("threshold", 0.0)))
        confusion_matrices.append(_confusion_matrix_for(ro_entry))
    cfg["angle"] = angles
    cfg["threshold"] = thresholds
    cfg["confusion_matrix"] = confusion_matrices

    if overrides:
        cfg.update(overrides)
    return cfg


# ---------------------------------------------------------------------------
# Iterative recenter-and-zoom (ReadoutOpt / PulseOpt)
# ---------------------------------------------------------------------------

# Max DAC gain magnitude — same constant the experiment classes use to convert
# normalized (0..1) qubit gains to absolute DAC counts (qubit_gains[idx]*32766).
DAC_GAIN_MAX = 32766

# GUI-only knobs injected into cfg by the iterative-opt param forms. They are
# consumed by RecenterZoomMixin and MUST be stripped from cfg before it reaches
# an experiment class (which would otherwise see unexpected keys in data['config']).
ITER_PARAM_KEYS = ("iterate", "max_iters", "freq_tol", "gain_tol", "zoom_factor")


def recenter_zoom_step(prev_opt, new_opt, span_f, span_g,
                       freq_tol, gain_tol, zoom_factor,
                       stable, iteration, max_iters):
    """Pure step function for the recenter-and-zoom loop.

    Always recenters the next window on ``new_opt`` (the optimum just found).
    Tracks how many consecutive iterations landed within tolerance of the
    previous optimum (``stable``); once two consecutive in-tolerance moves
    have occurred (i.e. the first time ``converged`` is True, which is the
    "after the second time" point), the window is zoomed by ``zoom_factor``.

    Args:
        prev_opt: (f, g) optimum from the previous iteration, or None on iter 0.
        new_opt:  (f, g) optimum from the current iteration.
        span_f, span_g: current HALF-width spans (freq MHz, gain DAC).
        freq_tol, gain_tol: convergence tolerances.
        zoom_factor: multiplicative span shrink applied once stable.
        stable: running count of consecutive in-tolerance iterations.
        iteration: zero-based iteration index just completed.
        max_iters: total iteration budget.

    Returns:
        (center_f, center_g, span_f, span_g, stable, should_stop)
    """
    new_f, new_g = new_opt
    center_f, center_g = new_f, new_g

    if prev_opt is not None:
        prev_f, prev_g = prev_opt
        converged = (abs(new_f - prev_f) <= freq_tol
                     and abs(new_g - prev_g) <= gain_tol)
    else:
        converged = False

    stable = stable + 1 if converged else 0

    # Zoom only after two consecutive in-tolerance runs (stable >= 1, i.e. the
    # first iteration on which `converged` is True).
    if stable >= 1:
        span_f *= zoom_factor
        span_g *= zoom_factor

    should_stop = ((iteration + 1 >= max_iters)
                   or (converged and span_f <= freq_tol and span_g <= gain_tol))

    return center_f, center_g, span_f, span_g, stable, should_stop


# ---------------------------------------------------------------------------
# qubit_parameters diff machinery (Save dialog + dirty styling)
# ---------------------------------------------------------------------------

# Field paths that naturally drift run-to-run (T1/T2R fits, etc.). The "suspicious
# >3x change" highlight is suppressed for these so a routine 10us -> 35us T1
# update doesn't trip the warning glyph. Compared as a dotted path suffix
# (e.g. matches "Qubit.T1" within an entry).
_DIFF_NOISY_FIELDS = {"Qubit.T1", "Qubit.T2R"}


def _values_differ(a, b) -> bool:
    """True if (a, b) should count as a change.

    Numeric tolerance: floats compare with relative-epsilon to avoid
    floating-point noise. NaN/None transitions are always treated as a change
    (so the dialog can flag them as suspicious). ``bool`` is checked before
    ``int`` because ``isinstance(True, int)`` is True in Python.
    """
    if a is b:
        return False
    # NaN: any comparison with NaN is False, so equal-NaN should NOT count as
    # changed, but NaN-vs-non-NaN should. Use the math-style check.
    def _is_nan(x):
        return isinstance(x, float) and x != x
    a_nan, b_nan = _is_nan(a), _is_nan(b)
    if a_nan and b_nan:
        return False
    if a_nan or b_nan:
        return True
    # None transitions count as a change unless both None (caught by `a is b`).
    if a is None or b is None:
        return True
    # Bool first (subclass of int).
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) != bool(b)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        try:
            return abs(float(a) - float(b)) > 1e-9 * max(abs(float(a)), abs(float(b)), 1.0)
        except Exception:
            return a != b
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            return True
        return any(_values_differ(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a.keys()) != set(b.keys()):
            return True
        return any(_values_differ(a[k], b[k]) for k in a)
    return a != b


def _is_suspicious_change(path_str: str, old, new) -> bool:
    """Magnitude-change flag for the Save dialog.

    Triggers on (a) any NaN/None transition between non-equal values, or
    (b) a >3x change in absolute magnitude when both sides are numeric and
    the old value is non-zero. Skipped for fields known to drift run-to-run
    (T1, T2R) so routine fit updates don't get flagged.
    """
    for noisy in _DIFF_NOISY_FIELDS:
        if path_str == noisy or path_str.endswith("." + noisy):
            return False
    def _bad(x):
        return x is None or (isinstance(x, float) and x != x)
    if _bad(old) != _bad(new):
        return True
    if _bad(old) or _bad(new):
        return False
    try:
        old_f = float(old); new_f = float(new)
    except (TypeError, ValueError):
        return False
    if not isinstance(old, (int, float)) or not isinstance(new, (int, float)):
        return False
    if isinstance(old, bool) or isinstance(new, bool):
        return False
    if old_f == 0.0:
        # Treat 0 -> nonzero as suspicious (avoids divide-by-zero and is
        # genuinely worth a second look — a calibration that flips a value on
        # from zero is a structural change).
        return new_f != 0.0
    return abs(new_f) > 3.0 * abs(old_f) or abs(new_f) < abs(old_f) / 3.0


def _walk_entry_diff(snapshot, live, path: list[str], out: list[tuple[str, object, object]]) -> None:
    """Recursive walker collecting (path_str, old, new) tuples for one entry."""
    # Dict: descend on union of keys.
    if isinstance(snapshot, dict) and isinstance(live, dict):
        for k in sorted(set(snapshot.keys()) | set(live.keys())):
            sub_s = snapshot.get(k, _MISSING)
            sub_l = live.get(k, _MISSING)
            if sub_s is _MISSING:
                out.append((".".join(path + [str(k)]), None, sub_l))
                continue
            if sub_l is _MISSING:
                out.append((".".join(path + [str(k)]), sub_s, None))
                continue
            _walk_entry_diff(sub_s, sub_l, path + [str(k)], out)
        return
    # Leaf / mismatched type: compare.
    if _values_differ(snapshot, live):
        out.append((".".join(path) if path else "(value)", snapshot, live))


class _MissingType:
    """Sentinel for `_walk_entry_diff` — distinguishes "key absent" from None."""
    def __repr__(self): return "<MISSING>"
_MISSING = _MissingType()


def _diff_entries(snapshot: dict, live: dict) -> list[dict]:
    """Compute per-entry diffs between two qubit_parameters dicts.

    Walks ``readout_groups[*].entries[*]`` and ``drive_groups[*].entries[*]``.
    The diff unit is a single ``(kind, group, entry)`` triple. Within each
    matched entry, fields are walked recursively into nested dicts (e.g.
    ``Readout.angle``, ``Qubit.Frequency``). Groups or entries that exist on
    only one side are reported as structural additions/removals with no
    field-level breakdown (the dialog tags those and persists them
    unconditionally — the user can't safely revert a brand-new entry to
    "nothing").

    Returns a list of records:
        {
            'kind':    'readout_groups' | 'drive_groups',
            'group':   group name,
            'entry':   entry name,
            'changes': [(path_str, old, new), ...],   # empty for structural
            'status':  'modified' | 'added' | 'removed',
        }
    """
    records: list[dict] = []
    for kind in ("readout_groups", "drive_groups"):
        snap_groups = (snapshot or {}).get(kind, {}) or {}
        live_groups = (live or {}).get(kind, {}) or {}
        group_names = sorted(set(snap_groups.keys()) | set(live_groups.keys()))
        for gname in group_names:
            snap_entries = (snap_groups.get(gname, {}) or {}).get("entries", {}) or {}
            live_entries = (live_groups.get(gname, {}) or {}).get("entries", {}) or {}
            entry_names = sorted(set(snap_entries.keys()) | set(live_entries.keys()))
            for ename in entry_names:
                snap_e = snap_entries.get(ename, _MISSING)
                live_e = live_entries.get(ename, _MISSING)
                if snap_e is _MISSING and live_e is _MISSING:
                    continue
                if snap_e is _MISSING:
                    records.append({
                        'kind': kind, 'group': gname, 'entry': ename,
                        'changes': [], 'status': 'added',
                    })
                    continue
                if live_e is _MISSING:
                    records.append({
                        'kind': kind, 'group': gname, 'entry': ename,
                        'changes': [], 'status': 'removed',
                    })
                    continue
                # Modified-or-equal: walk to find any field changes.
                changes: list[tuple[str, object, object]] = []
                _walk_entry_diff(snap_e, live_e, [], changes)
                if changes:
                    records.append({
                        'kind': kind, 'group': gname, 'entry': ename,
                        'changes': changes, 'status': 'modified',
                    })
    # base_params — flat name -> array. Emitted last so RO/Drive records lead.
    records.extend(_diff_base_params(snapshot, live))
    return records


def _diff_base_params(snapshot: dict, live: dict) -> list[dict]:
    """Element-wise diff for ``base_params[array_name]``.

    One record per affected array. ``entry`` is None; ``kind`` is
    ``"base_params"``. For modified arrays, ``changes`` is a list of
    ``("[i]", old_i, new_i)`` tuples (one per differing element).
    Added/removed arrays have an empty changes list.
    """
    out: list[dict] = []
    snap_bp = (snapshot or {}).get("base_params", {}) or {}
    live_bp = (live or {}).get("base_params", {}) or {}
    names = sorted(set(snap_bp.keys()) | set(live_bp.keys()))
    for name in names:
        snap_arr = snap_bp.get(name, _MISSING)
        live_arr = live_bp.get(name, _MISSING)
        if snap_arr is _MISSING and live_arr is _MISSING:
            continue
        if snap_arr is _MISSING:
            out.append({'kind': 'base_params', 'group': name, 'entry': None,
                        'changes': [], 'status': 'added'})
            continue
        if live_arr is _MISSING:
            out.append({'kind': 'base_params', 'group': name, 'entry': None,
                        'changes': [], 'status': 'removed'})
            continue
        # Both sides arrays: element-wise compare. Length mismatch = treat
        # missing-on-shorter-side slots as None so they surface as diffs.
        if not isinstance(snap_arr, (list, tuple)) or not isinstance(live_arr, (list, tuple)):
            # Unexpected scalar/dict — fall back to whole-value diff.
            if _values_differ(snap_arr, live_arr):
                out.append({'kind': 'base_params', 'group': name, 'entry': None,
                            'changes': [("(value)", snap_arr, live_arr)],
                            'status': 'modified'})
            continue
        n = max(len(snap_arr), len(live_arr))
        changes: list[tuple[str, object, object]] = []
        for i in range(n):
            sv = snap_arr[i] if i < len(snap_arr) else None
            lv = live_arr[i] if i < len(live_arr) else None
            if _values_differ(sv, lv):
                changes.append((f"[{i}]", sv, lv))
        if changes:
            out.append({'kind': 'base_params', 'group': name, 'entry': None,
                        'changes': changes, 'status': 'modified'})
    return out


def _fmt_diff_value(v, path_str: str = "") -> str:
    """Short, single-line repr for the diff dialog's "old -> new" column.

    ``path_str`` lets the formatter narrow precision for fields where 6-sig
    digits are noise: readout angle is in radians (3 decimals are plenty),
    threshold is a DAC-count discriminator (one decimal suffices).
    """
    if v is None:
        return "None"
    if isinstance(v, float):
        if v != v:  # NaN
            return "NaN"
        if path_str.endswith(".angle"):
            return f"{v:.3f}"
        if path_str.endswith(".threshold"):
            return f"{v:.1f}"
        return f"{v:.6g}"
    if isinstance(v, (int, bool)):
        return repr(v)
    if isinstance(v, str):
        return v if len(v) <= 32 else v[:29] + "..."
    if isinstance(v, (list, tuple)):
        s = repr(list(v))
        return s if len(s) <= 64 else s[:61] + "..."
    if isinstance(v, dict):
        s = repr(v)
        return s if len(s) <= 64 else s[:61] + "..."
    return repr(v)


def _field_importance(path_str: str) -> int:
    """Sort key for changed fields inside the diff dialog's "What changed".

    Qubit.* are the user-relevant calibration outputs; Readout.angle and
    Readout.threshold are auxiliary discriminator params the user rarely
    cares about per-save. Lower = earlier in the summary.
    """
    if path_str.endswith(".angle") or path_str.endswith(".threshold"):
        return 30
    if path_str.startswith("Qubit"):
        return 0
    if path_str.startswith("Readout"):
        return 10
    return 20


# --- dirty-tracking helpers shared by QubitParametersTab + FFFrequenciesTab ---


def _leaf_at_path(root: dict, path: tuple) -> tuple[bool, object]:
    """Walk a path of (key|int-index) into a nested dict/list structure.

    Returns ``(found, value)``. ``found=False`` means a segment was missing or
    the structure didn't match (e.g. tried to index a non-list). Used by the
    style helpers to look up the corresponding leaf in the on-disk snapshot.
    """
    cur = root
    for seg in path:
        if isinstance(cur, dict):
            if seg not in cur:
                return False, None
            cur = cur[seg]
        elif isinstance(cur, (list, tuple)):
            try:
                i = int(seg)
            except (TypeError, ValueError):
                return False, None
            if i < 0 or i >= len(cur):
                return False, None
            cur = cur[i]
        else:
            return False, None
    return True, cur


def _path_is_dirty(snapshot: dict, live: dict, path: tuple) -> bool:
    """True if the leaf at ``path`` differs between snapshot and live.

    Routes through ``_values_differ`` so float/NaN/None handling matches the
    Save dialog. A missing-on-one-side leaf counts as dirty (matches the
    behaviour the Save dialog already exposes via _walk_entry_diff).
    """
    snap_found, snap_v = _leaf_at_path(snapshot or {}, path)
    live_found, live_v = _leaf_at_path(live or {}, path)
    if snap_found != live_found:
        return True
    if not snap_found:
        return False
    return _values_differ(snap_v, live_v)


def _entry_touched_paths(touched: set, prefix: tuple) -> bool:
    """True if any path in ``touched`` starts with ``prefix``.

    Used to bold the combo text in FFFrequenciesTab when the selected group
    has any calibration-touched leaf below it.
    """
    if not touched:
        return False
    n = len(prefix)
    for p in touched:
        if len(p) >= n and tuple(p[:n]) == prefix:
            return True
    return False


def _diff_path_set(snapshot: dict, live: dict) -> set:
    """All leaf-paths that differ between snapshot and live (any namespace).

    Used to drive group-level dirty styling (e.g. bold a combo entry when ANY
    leaf below it is dirty vs snapshot). Walks both sides via the same
    semantics as _walk_entry_diff but emits full path tuples rather than
    dotted strings.
    """
    dirty: set = set()

    def walk(s, l, path: tuple) -> None:
        if isinstance(s, dict) and isinstance(l, dict):
            for k in set(s.keys()) | set(l.keys()):
                walk(s.get(k, _MISSING), l.get(k, _MISSING), path + (k,))
            return
        if isinstance(s, list) and isinstance(l, list):
            n = max(len(s), len(l))
            for i in range(n):
                sv = s[i] if i < len(s) else _MISSING
                lv = l[i] if i < len(l) else _MISSING
                walk(sv, lv, path + (i,))
            return
        # Treat _MISSING as "absent" — only count as dirty if the other side
        # has a value.
        if s is _MISSING and l is _MISSING:
            return
        if s is _MISSING or l is _MISSING:
            dirty.add(path); return
        if _values_differ(s, l):
            dirty.add(path)

    walk(snapshot or {}, live or {}, ())
    return dirty


def _snapshot_calibration_diff(state: "CalibState", before: dict) -> None:
    """Compute the diff between ``before`` and ``state.qubit_parameters_json``
    and add every changed leaf-path to ``state.calibration_touched_paths``.

    Used by both StageTab._on_apply and AutoCalibWorker.run to tag calibration-
    written leaves without modifying each individual on_apply method.
    """
    try:
        changed = _diff_path_set(before, state.qubit_parameters_json)
    except Exception:
        # Defensive: never let a tagging failure abort an apply.
        return
    if changed:
        state.calibration_touched_paths.update(changed)


# ---------------------------------------------------------------------------
# JSON pretty-printers
# ---------------------------------------------------------------------------


def _make_jsonable(d):
    """Convert numpy scalars/arrays and unknown types to JSON-friendly forms."""
    import numpy as np
    if isinstance(d, dict):
        return {k: _make_jsonable(v) for k, v in d.items()}
    if isinstance(d, (list, tuple)):
        return [_make_jsonable(v) for v in d]
    if isinstance(d, np.ndarray):
        return d.tolist()
    if isinstance(d, (np.integer,)):
        return int(d)
    if isinstance(d, (np.floating,)):
        return float(d)
    if d is None or isinstance(d, (str, int, float, bool)):
        return d
    return str(d)


# Matches a JSON list whose elements are all scalar literals (number, string,
# true/false/null) split across lines by json.dumps(indent=...). Used to
# collapse e.g. FF_Gains arrays back onto a single line for readability.
_SCALAR_ARRAY_RE = re.compile(
    r'\[\s*\n\s*'
    r'(?:-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|"[^"\n]*"|true|false|null)'
    r'(?:\s*,\s*\n\s*'
    r'(?:-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|"[^"\n]*"|true|false|null))*'
    r'\s*\n\s*\]'
)


def _collapse_scalar_arrays(text: str) -> str:
    def _repl(m):
        inner = m.group(0)[1:-1]
        parts = [p.strip() for p in inner.split(',')]
        return '[' + ', '.join(parts) + ']'
    return _SCALAR_ARRAY_RE.sub(_repl, text)


def dumps_pretty(obj, indent: int = 2) -> str:
    """json.dumps but collapses scalar-only arrays onto one line."""
    return _collapse_scalar_arrays(json.dumps(_make_jsonable(obj), indent=indent))


def dump_pretty(obj, fp, indent: int = 2) -> None:
    """json.dump but collapses scalar-only arrays onto one line."""
    fp.write(dumps_pretty(obj, indent=indent))
