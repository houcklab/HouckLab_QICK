"""Short text about blocks for the canvas: Measure chip lines, lane markers and hover tooltips.

Pure functions of the controller's state (sequence, resolved values, compiled program), so the
tests can check them without painting anything.
"""
from __future__ import annotations

import html
from typing import Optional

from ...config.summary import qubit_list_text
from ...core.block import MeasureBlock, PulseBlock, SegmentBlock
from ...core.params import FromPrev, Ref, Sweep, VectorSource, base_source

MODE_SHORT = {"populations_corrected": "P", "populations": "P raw", "iq": "IQ"}
MODE_LONG = {"populations_corrected": "populations, corrected", "populations": "populations, raw",
             "iq": "raw I/Q"}
MODE_HELP = {"populations_corrected": "excited-state population, corrected with the single-shot confusion matrix",
             "populations": "excited-state population from the single-shot threshold, not corrected",
             "iq": "averaged I/Q, no thresholding"}


# ------------------------------------------------------------------ small helpers
def _val(block, name, default=None):
    v = block.fields.get(name)
    return getattr(v, "value", default)


def measure_qubits(seq) -> list:
    m = seq.measure
    if m is None:
        return []
    try:
        return [int(x) for x in (_val(m, "qubits", []) or [])]
    except (TypeError, ValueError):
        return []


def measure_mode(seq) -> str:
    return str(_val(seq.measure, "mode", "")) if seq.measure is not None else ""


def measure_chip_lines(seq) -> tuple:
    """(title, right-hand tag, second line) for the Measure chip."""
    m = seq.measure
    group = str(_val(m, "readout_group", "") or "")
    mode = measure_mode(seq)
    second = f"{qubit_list_text(measure_qubits(seq))} · {MODE_SHORT.get(mode, mode)}"
    if mode == "populations_corrected":
        second += " corrected"
    return m.name, group, second


def _fmt_num(v, unit: str = "") -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        if unit in ("µs", "µs") and abs(v) < 1:
            return f"{v * 1e3:.4g} ns"
        s = f"{v:.6g}"
        return f"{s} {unit}".strip() if unit else s
    return str(v)


def phase_text(pulse, params: Optional[dict]) -> str:
    src = pulse.fields.get("phase")
    if isinstance(src, Sweep):
        return f"‹{src.axis}›"
    v = (params or {}).get("phase")
    if v is None:
        v = getattr(src, "value", None)
    try:
        return f"{float(v):g}°"
    except (TypeError, ValueError):
        return "?"


def readout_rotation(seq, resolved, q: int) -> Optional[tuple]:
    """(pulse block, phase text) when the last pulse on qubit q, in the last segment before Measure,
    is a π/2; that pulse sets the measurement basis. None otherwise."""
    if not seq.segments:
        return None
    last = seq.segments[-1]
    mine = [p for p in seq.pulses_in(last.id) if p.qubit == q]
    if not mine or mine[-1].TYPE != "Pi2Pulse":
        return None
    p = mine[-1]
    params = resolved.params_by_block().get(p.id) if resolved is not None else None
    return p, phase_text(p, params)


# ------------------------------------------------------------------ tooltips
def _source_tag(block, name: str) -> str:
    src = block.fields.get(name)
    extra = ""
    if isinstance(src, VectorSource):
        if src.overrides:
            extra = f" + {len(src.overrides)} override{'s' if len(src.overrides) > 1 else ''}"
        src = src.base
    if isinstance(src, Ref):
        try:
            r = src.filled(block.template_values())
        except KeyError:
            r = src
        parts = r.key_path.split("/")
        path = "…/" + "/".join(parts[-4:]) if len(parts) > 4 else r.key_path
        scale = f" × {r.scale:g}" if r.scale != 1.0 else ""
        return f"{r.store} {path}{scale}{extra}"
    if isinstance(src, Sweep):
        return f"sweep ‹{src.axis}›{extra}"
    if isinstance(src, FromPrev):
        return f"from previous segment{extra}"
    return ("set here" + extra) if extra else ""


def _vector_html(vals, unit="") -> str:
    cells = []
    for i, v in enumerate(vals):
        cells.append(f"<td style='color:#8A8A90'>Q{i + 1}</td><td align='right'>{_fmt_num(v)}</td>")
    rows = ["<tr>" + "".join(cells[k:k + 4]) + "</tr>" for k in range(0, len(cells), 4)]
    return "<table cellspacing='0' cellpadding='1'>" + "".join(rows) + "</table>"


def _row(label, value_html, tag="") -> str:
    tag_html = f"<br><span style='color:#8A8A90'>{html.escape(tag)}</span>" if tag else ""
    return (f"<tr><td style='color:#5A5A60; padding-right:8px' valign='top'>{html.escape(label)}</td>"
            f"<td valign='top'>{value_html}{tag_html}</td></tr>")


def _shown_fields(block):
    for spec in block.FIELDS:
        src = block.fields.get(spec.name)
        if spec.advanced:
            try:
                if src == spec.make_default():
                    continue
            except Exception:
                pass
        yield spec


def block_tooltip(ctl, block_id: str) -> str:
    """Rich-text tooltip: what the block is, its resolved values at the previewed point, problems."""
    seq, res = ctl.seq, ctl.resolved
    b = seq.get(block_id)
    if b is None:
        return ""
    params = (res.params_by_block().get(b.id) if res is not None else None) or {}
    out = [f"<b>{html.escape(b.name)}</b> <span style='color:#8A8A90'>· {html.escape(b.LABEL)}</span>"]
    extra = []
    if isinstance(b, SegmentBlock) and res is not None:
        for r in res.segments:
            if r.block.id == b.id and r.wave is not None:
                us = r.wave.length / res.samples_per_us
                extra.append(_row("Length", f"{_fmt_num(us, 'µs')} <span style='color:#8A8A90'>"
                                            f"({r.wave.length} samples)</span>"))
    if isinstance(b, PulseBlock) and ctl.compiled is not None:
        for d in ctl.compiled.drives:
            if d.block_id == b.id:
                extra.append(_row("Plays", f"at {_fmt_num(d.t_us, 'µs')}, for {_fmt_num(d.length_us, 'µs')}"))
    rows = []
    for spec in _shown_fields(b):
        v = params.get(spec.name)
        if v is None and spec.name not in params:
            v = getattr(b.fields.get(spec.name), "value", None)
        unit = spec.unit or ""
        if isinstance(v, list) and spec.is_vector:
            val = _vector_html(v, unit)
            label = f"{spec.label} ({unit})" if unit else spec.label
        elif isinstance(v, list):
            val = html.escape(qubit_list_text(v) if spec.name == "qubits" else ", ".join(map(str, v)))
            label = spec.label
        else:
            if spec.name == "mode":
                val = html.escape(MODE_LONG.get(str(v), str(v)))
            elif spec.name in ("entry",) and not str(v or "").strip():
                val = "(qubit number)"
            else:
                val = html.escape(_fmt_num(v, unit))
            label = spec.label
        rows.append(_row(label, val, _source_tag(b, spec.name)))
    out.append("<table cellspacing='0' cellpadding='2'>" + "".join(extra + rows) + "</table>")
    if isinstance(b, MeasureBlock):
        out.append(_readout_table(ctl))
    probs = ctl.problems_for(b.id)
    if probs:
        color = {"error": "#CD5C5C", "warning": "#C27A1A", "info": "#4A78C8"}
        out.append("<br>".join(f"<span style='color:{color.get(p.level, '#555')}'>• {html.escape(p.message)}</span>"
                               for p in probs[:5]))
    if res is not None and res.point:
        pt = ", ".join(f"{k} = {_fmt_num(v)}" for k, v in res.point.items())
        out.append(f"<span style='color:#8A8A90'>Values at the previewed sweep point ({html.escape(pt)}).</span>")
    return "<br>".join(out)


def _res_lo(ctl) -> float:
    """Readout frequencies in the cfg are relative to the resonator LO; tooltips show absolute MHz."""
    try:
        return float(ctl.station["res_LO"])
    except Exception:
        return 0.0


def _readout_table(ctl) -> str:
    res = ctl.resolved
    if res is None or res.measure is None or not res.measure.readout:
        return ""
    ro = res.measure.readout
    lo = _res_lo(ctl)
    head = "".join(f"<td style='color:#5A5A60; padding-right:8px'>{h}</td>"
                   for h in ("", "Readout MHz", "Gain", "Length µs", "Threshold"))
    rows = [f"<tr>{head}</tr>"]
    for k, q in enumerate(ro["Qubit_Readout_List"]):
        thr = ro.get("threshold", [None] * len(ro["res_freqs"]))[k]
        rows.append("<tr>" + "".join(f"<td align='right' style='padding-right:8px'>{c}</td>" for c in (
            f"Q{q}", _fmt_num(ro["res_freqs"][k] + lo), _fmt_num(ro["res_gains"][k]),
            _fmt_num(ro["readout_lengths"][k]), _fmt_num(thr))) + "</tr>")
    return "<table cellspacing='0' cellpadding='1'>" + "".join(rows) + "</table>"


def measure_lane_tooltip(ctl, q: int) -> str:
    """Tooltip for one qubit's marker in the Measure column."""
    seq, res = ctl.seq, ctl.resolved
    mode = measure_mode(seq)
    lines = [f"<b>Q{q}</b> <span style='color:#8A8A90'>· {html.escape(seq.measure.name)}</span>",
             f"Reports: {html.escape(MODE_LONG.get(mode, mode))}<br>"
             f"<span style='color:#8A8A90'>{html.escape(MODE_HELP.get(mode, ''))}</span>"]
    rot = readout_rotation(seq, res, q)
    if rot:
        p, ph = rot
        lines.append(f"Basis: after <b>{html.escape(p.name)}</b> (π/2, phase {html.escape(ph)}) in the last "
                     "segment. Which axis that is depends on your phase convention.")
    else:
        lines.append("Basis: no π/2 on this qubit in the last segment, so Z unless an earlier pulse rotates it.")
    if res is not None and res.measure is not None and res.measure.readout:
        ro = res.measure.readout
        qs = list(ro["Qubit_Readout_List"])
        if q in qs:
            k = qs.index(q)
            lo = _res_lo(ctl)
            group = _val(seq.measure, "readout_group", "")
            parts = [f"{_fmt_num(ro['res_freqs'][k] + lo)} MHz", f"gain {_fmt_num(ro['res_gains'][k])}",
                     f"{_fmt_num(ro['readout_lengths'][k])} µs"]
            if "threshold" in ro:
                parts.append(f"threshold {_fmt_num(ro['threshold'][k])}")
            lines.append(f"Readout ({html.escape(str(group))}): " + ", ".join(parts))
    return "<br>".join(lines)


# ------------------------------------------------------------------ chip badges
BADGE_HELP = {"ref": "Purple dot: reads values from the calibration file (or the station file)",
              "sweep": "Orange triangle: swept over an experiment axis"}


def calib_fields(block) -> list:
    """[(label, filled path)] for fields that read from calibration/station."""
    out, tv = [], block.template_values()
    for spec in block.FIELDS:
        src = base_source(block.fields.get(spec.name))
        if isinstance(src, Ref):
            try:
                path = src.filled(tv).path
            except KeyError:
                path = src.path
            out.append((spec.label, path))
    return out


def swept_fields(block) -> list:
    """[(label, axis)] for fields swept over an experiment axis."""
    return [(spec.label, base_source(block.fields.get(spec.name)).axis) for spec in block.FIELDS
            if isinstance(base_source(block.fields.get(spec.name)), Sweep)]


def badge_tooltip(block, kind: str) -> str:
    if block is None:
        return ""
    head = f"<b>{html.escape(BADGE_HELP[kind])}</b>"
    if kind == "ref":
        rows = [f"{html.escape(lbl)} <span style='color:#8A8A90'>← {html.escape(path)}</span>"
                for lbl, path in calib_fields(block)]
    else:
        rows = [f"{html.escape(lbl)} <span style='color:#8A8A90'>‹{html.escape(ax)}›</span>"
                for lbl, ax in swept_fields(block)]
    return head + "<br>" + "<br>".join(rows)


# ------------------------------------------------------------------ prepared state
STATE_WORDS = {"0": "ground |0⟩", "1": "excited |1⟩", "+": "equal superposition",
               "~": "partial rotation", "?": "unknown"}


def state_tooltip(st) -> str:
    lines = [f"<b>Q{st.qubit}</b> after Preparation: {html.escape(STATE_WORDS.get(st.kind, st.kind))}"]
    if st.kind in ("+", "~") and st.p1 is not None:
        lines.append(f"P(1) = {st.p1:.2f} for ideal pulses")
    if st.kind == "?":
        lines.append("A generic Drive or a swept gain: Bob can't tell the resulting state.")
    if st.pulses:
        lines.append("From: " + ", ".join(f"{html.escape(n)} ({html.escape(lbl)})" for n, lbl in st.pulses))
    else:
        lines.append("No pulses on this qubit in Preparation.")
    if st.swept:
        lines.append("A pulse phase is swept; shown at the previewed sweep point.")
    lines.append("<span style='color:#8A8A90'>Starts in |0⟩, ideal pulses, no coupling during "
                 "Preparation.</span>")
    return "<br>".join(lines)
