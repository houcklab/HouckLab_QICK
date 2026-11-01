"""Plain-language descriptions of a sequence: the prepared state, and a one-paragraph summary.

The prepared state follows each qubit through the pulses in the Preparation act, assuming
ideal pulses and no coupling between qubits during preparation (prep happens at a detuned
point). Every qubit starts in |0⟩. π and π/2 pulses are rotations about an axis in the
xy-plane set by their phase. A generic Drive, or a qubit whose prep pulses are swept in gain,
gives "?". A swept phase uses its value at the previewed sweep point.

The summary is regenerated on every save and stored as ``summary`` in the sequence file, so
the file (and every run's data, which embeds it) explains itself without opening Bob.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from ..core.params import FromPrev, Ref, Sweep, VectorSource, base_source

ANGLE = {"PiPulse": math.pi, "Pi2Pulse": math.pi / 2}
TOL = 1e-6


@dataclass
class PreparedState:
    qubit: int
    kind: str                     # "0", "1", "+" (on the equator), "~" (partial), "?" (unknown)
    p1: Optional[float] = None    # excited population for ideal pulses
    pulses: list = field(default_factory=list)   # [(name, label)] that acted on it
    swept: bool = False


def _rotate(v: np.ndarray, theta: float, phi_deg: float) -> np.ndarray:
    """Rotate Bloch vector v by theta about the axis (cos φ, sin φ, 0) (Rodrigues)."""
    phi = math.radians(phi_deg)
    k = np.array([math.cos(phi), math.sin(phi), 0.0])
    return (v * math.cos(theta) + np.cross(k, v) * math.sin(theta)
            + k * np.dot(k, v) * (1 - math.cos(theta)))


def prep_pulses(seq) -> list:
    """Pulses in Preparation-act segments, in play order."""
    out = []
    for s in seq.segments:
        if s.act == "prep":
            out.extend(seq.pulses_in(s.id))
    return out


def prepared_states(seq, resolved=None, n_qubits: int = 8) -> dict:
    """{qubit: PreparedState} after the Preparation act; empty when prep has no pulses."""
    pulses = prep_pulses(seq)
    if not pulses:
        return {}
    params = resolved.params_by_block() if resolved is not None else {}
    vec = {q: np.array([0.0, 0.0, 1.0]) for q in range(1, n_qubits + 1)}     # +z = |0⟩
    states = {q: PreparedState(q, "0", 0.0) for q in range(1, n_qubits + 1)}
    for b in pulses:
        q = b.qubit
        if q not in states:
            continue
        st = states[q]
        label = {"PiPulse": "π", "Pi2Pulse": "π/2"}.get(b.TYPE, b.LABEL)
        st.pulses.append((b.name, label))
        if st.kind == "?":
            continue
        gain_swept = isinstance(base_source(b.fields.get("gain")), Sweep)
        if b.TYPE not in ANGLE or gain_swept:
            st.kind, st.p1 = "?", None
            continue
        st.swept |= isinstance(base_source(b.fields.get("phase")), Sweep)
        phase = (params.get(b.id) or {}).get("phase")
        if phase is None:
            phase = getattr(b.fields.get("phase"), "value", 0.0) or 0.0
        vec[q] = _rotate(vec[q], ANGLE[b.TYPE], float(phase))
        z = float(vec[q][2])
        st.p1 = (1 - z) / 2
        st.kind = "0" if z > 1 - TOL else "1" if z < -1 + TOL else "+" if abs(z) < TOL else "~"
    return states


def state_string(states: dict) -> str:
    """'00111+11'."""
    return "".join(states[q].kind for q in sorted(states))


def state_counts(states: dict) -> str:
    """'5 excitations, 1 superposition'."""
    n1 = sum(1 for s in states.values() if s.kind == "1")
    parts = [f"{n1} excitation{'s' if n1 != 1 else ''}"]
    for k, word in (("+", "superposition"), ("~", "partial rotation"), ("?", "unknown")):
        n = sum(1 for s in states.values() if s.kind == k)
        if n:
            parts.append(f"{n} {word}{'s' if n != 1 else ''}")
    return ", ".join(parts)


# ------------------------------------------------------------------ summary text
def qubit_list_text(qs) -> str:
    """[3, 4, 5, 6, 7, 8] -> 'Q3–Q8'; [1, 3, 4] -> 'Q1, Q3–Q4'."""
    qs = sorted({int(q) for q in qs})
    if not qs:
        return "no qubits"
    runs, start, prev = [], qs[0], qs[0]
    for q in qs[1:] + [None]:
        if q is not None and q == prev + 1:
            prev = q
            continue
        runs.append(f"Q{start}" if start == prev else f"Q{start}–Q{prev}")
        if q is not None:
            start = prev = q
    return ", ".join(runs)


def _num(v) -> str:
    return f"{v:.6g}"


def _dur(seq, resolved, seg) -> str:
    src = seg.fields.get("duration_us")
    if isinstance(src, Sweep):
        ax = seq.settings.axis(src.axis)
        if ax is not None:
            return f"{src.axis} = {_num(ax.start)}–{_num(ax.stop)} {ax.unit}".rstrip()
        return f"swept ‹{src.axis}›"
    for r in (resolved.segments if resolved is not None else []):
        if r.block.id == seg.id and r.wave is not None:
            us = r.wave.length / resolved.samples_per_us
            return f"{us * 1e3:.0f} ns" if us < 1 else f"{us:.3g} µs"
    return "?"


def _ref_text(block, name) -> str:
    """Where a field's value comes from, briefly: 'ramp_6Q/6Q_Pulse_init/FF_Expt' or 'set by hand'."""
    src = block.fields.get(name)
    over = src.overrides if isinstance(src, VectorSource) else {}
    src = base_source(src)
    extra = f" (+{len(over)} override{'s' if len(over) > 1 else ''})" if over else ""
    if isinstance(src, Ref):
        try:
            path = src.filled(block.template_values()).key_path
        except KeyError:
            path = src.key_path
        parts = path.split("/")
        if parts[0] == "ff_groups" and len(parts) > 2:
            parts = parts[2:]
        elif parts[0] == "drive_groups" and len(parts) > 1:
            parts = parts[1:]
        return "/".join(parts) + extra
    if isinstance(src, Sweep):
        return f"swept ‹{src.axis}›" + extra
    if isinstance(src, FromPrev):
        return "the previous segment's end" + extra
    return "gains set by hand" + extra


def _val(block, name, default=""):
    return getattr(block.fields.get(name), "value", default)


def _segment_phrase(seq, resolved, seg) -> str:
    d = _dur(seq, resolved, seg)
    t = seg.TYPE
    if t == "FFHold":
        what = f"hold at {_ref_text(seg, 'gains')}"
    elif t == "FFRamp":
        what = f"{_val(seg, 'shape', 'linear')} ramp to {_ref_text(seg, 'end_gains')}"
    elif t == "FFDynamics":
        mode = _val(seg, "mode", "hold")
        what = f"{'play waveform file' if mode == 'file' else 'hold'} at {_ref_text(seg, 'gains')}"
    elif t == "Beamsplitter":
        what = f"beamsplitter {_val(seg, 'bs_group')}/{_val(seg, 'bs_entry')}"
    else:
        what = seg.LABEL.lower()
    return f"{seg.name} ({d}): {what}"


def _pulse_phrase(seq, resolved, pulses) -> str:
    """'π on Q3–Q5, Q7–Q8; π/2 at 0° on Q6'."""
    params = resolved.params_by_block() if resolved is not None else {}
    groups: dict = {}
    for b in pulses:
        label = {"PiPulse": "π", "Pi2Pulse": "π/2"}.get(b.TYPE, b.LABEL)
        ph_src = base_source(b.fields.get("phase"))
        if isinstance(ph_src, Sweep):
            ph = f" at phase ‹{ph_src.axis}›"
        else:
            ph_v = (params.get(b.id) or {}).get("phase", getattr(ph_src, "value", 0.0)) or 0.0
            ph = f" at {float(ph_v):g}°" if b.TYPE != "PiPulse" or float(ph_v) != 0.0 else ""
        swept = [spec.label.lower() for spec in b.FIELDS
                 if spec.name != "phase" and isinstance(base_source(b.fields.get(spec.name)), Sweep)]
        sw = f" (swept {', '.join(swept)})" if swept else ""
        groups.setdefault(label + ph + sw, []).append(b.qubit)
    return "; ".join(f"{k} on {qubit_list_text(v)}" for k, v in groups.items())


def summarize(seq, resolved=None, n_qubits: int = 8) -> str:
    """One paragraph, in play order. Values that depend on the sweep point use the previewed one."""
    lines = []
    st = seq.settings
    sweeps = ", ".join(f"{a.name} {_num(a.start)}–{_num(a.stop)} {a.unit}".rstrip() + f" ({a.points} pts)"
                       for a in st.sweeps)
    head = f"{seq.name}: {st.reps} reps" + (f" × {st.rounds} rounds" if st.rounds and st.rounds > 1 else "")
    head += f", sweeping {sweeps}" if sweeps else ", no sweep"
    lines.append(head + ".")
    for act, title in (("prep", "Preparation"), ("dynamics", "Dynamics"), ("readout", "Beamsplitter + measure")):
        segs = [s for s in seq.segments if s.act == act]
        if not segs:
            continue
        parts = []
        for s in segs:
            ph = _segment_phrase(seq, resolved, s)
            pulses = seq.pulses_in(s.id)
            if pulses:
                ph += "; " + _pulse_phrase(seq, resolved, pulses)
            parts.append(ph)
        text = f"{title}: " + ". ".join(parts) + "."
        if act == "prep":
            states = prepared_states(seq, resolved, n_qubits)
            if states:
                text += f" Prepared state {state_string(states)} (Q1→Q{n_qubits}; {state_counts(states)})."
        lines.append(text)
    m = seq.measure
    if m is not None:
        mode = {"populations_corrected": "corrected populations", "populations": "raw populations",
                "iq": "averaged I/Q"}.get(_val(m, "mode"), _val(m, "mode"))
        qs = _val(m, "qubits", []) or []
        lines.append(f"Measure: {qubit_list_text(qs)} at {_val(m, 'readout_group')}, reporting {mode}.")
    else:
        lines.append("No Measure block.")
    return " ".join(lines)
