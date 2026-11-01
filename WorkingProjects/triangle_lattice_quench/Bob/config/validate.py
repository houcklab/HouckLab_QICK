"""Validator: checks a resolved sequence before anything reaches hardware.

Every finding is a Problem tied to a block (and field where it applies), so the GUI can
outline the block and jump to the field.
"""
from __future__ import annotations

from ..compiler.timing import schedule_drives
from ..core.block import ACT_LABELS, ACTS
from ..core.sequence import Sequence
from .problems import Problem
from .resolver import ResolvedSequence
from .station import Station


# data keys a run saves; an axis with one of these names would overwrite that data
RESERVED_AXIS_NAMES = {"I", "Q", "population", "population_corrected", "snapshot"}
MAX_SWEEP_POINTS = 1_000_000


def validate(seq: Sequence, res: ResolvedSequence, station: Station) -> list:
    probs: list = []

    def P(level, msg, block=None, fld=None):
        probs.append(Problem(level, msg, block.id if block else None, fld, block.name if block else None))

    # ---------------------------------------------------------------- structure
    if not seq.segments:
        empty = not seq.pulses and seq.measure is None
        P("info" if empty else "error",
          "The sequence has no flux segments. Drag an FF hold onto the flux track to start.")
    if not seq.act_order_ok():
        for a, b in zip(seq.segments, seq.segments[1:]):
            if ACTS.index(b.act) < ACTS.index(a.act):
                P("error", f"{ACT_LABELS[b.act]} block comes after a {ACT_LABELS[a.act]} block; "
                           f"acts must run preparation → dynamics → readout.", b)
    if seq.measure is None and seq.segments:
        P("warning", "No Measure block: nothing will be read out.")

    # ---------------------------------------------------------------- field limits
    for r in res.segments + res.pulses + ([res.measure] if res.measure else []):
        for spec in r.block.FIELDS:
            v = r.params.get(spec.name)
            if v is None or spec.limits is None:
                continue
            lo, hi = spec.limits
            vals = v if isinstance(v, list) else [v]
            for k, x in enumerate(vals):
                if isinstance(x, (int, float)) and not (lo <= x <= hi):
                    where = f" (Q{k + 1})" if isinstance(v, list) else ""
                    P("error", f"{spec.label}{where} = {x:g} is outside {lo:g} to {hi:g} {spec.unit}".rstrip(),
                      r.block, spec.name)
                    break

    # ---------------------------------------------------------------- segment lengths
    for r in res.segments:
        if r.wave is not None and r.wave.length == 0:
            P("info", "Zero length at this sweep point; the segment is skipped.", r.block, None)

    # ---------------------------------------------------------------- drives
    n_q = station.n_channels
    lo_mix = station["qubit_mixer_freq"] - station.data.get("qubit_mixer_halfband_mhz", 860)
    hi_mix = station["qubit_mixer_freq"] + station.data.get("qubit_mixer_halfband_mhz", 860)
    seg_ok = all(s.wave is not None for s in res.segments)
    drives_by_seg = [[] for _ in res.segments]
    for pi, rp in enumerate(res.pulses):
        if rp.drive is None:
            continue
        d = rp.drive
        if not 1 <= d.qubit <= n_q:
            P("error", f"Qubit {d.qubit} does not exist on this station (1 to {n_q}).", rp.block, "qubit")
        if not lo_mix <= d.freq_mhz <= hi_mix:
            P("error", f"{d.freq_mhz:.1f} MHz is outside the qubit mixer band {lo_mix:.0f} to {hi_mix:.0f} MHz.",
              rp.block, "freq")
        if rp.segment_index >= 0:
            drives_by_seg[rp.segment_index].append((pi, d))
    if seg_ok and res.segments:
        # schedule exactly as the compiler will, so "past the end" matches what would play
        lengths = [s.wave.length for s in res.segments]
        sched = schedule_drives(lengths, drives_by_seg, station.samples_per_us,
                                int(station.data.get("drive_offset_cycles", 0)))
        for sd in sched:
            rp = res.pulses[sd.pulse_index]
            if sd.t_us + sd.length_us > sd.segment_end_us + 1e-9:
                over_ns = (sd.t_us + sd.length_us - sd.segment_end_us) * 1e3
                P("error", f"Pulse runs {over_ns:.1f} ns past the end of its segment. Lengthen the segment "
                           f"or move the pulse.", rp.block, "relative_t")
        for si, items in enumerate(drives_by_seg):
            qubits = sorted({d.qubit for _, d in items})
            if len(qubits) > 1:
                seg = res.segments[si].block
                P("info", f"Pulses on Q{', Q'.join(map(str, qubits))} play one after another: all drives share "
                          f"qubit_ch {station['qubit_ch']}.", seg)

    # ---------------------------------------------------------------- readout
    m = res.measure
    if m is not None and m.ok:
        if not m.params["qubits"]:
            P("error", "Choose at least one qubit to read out.", m.block, "qubits")
        if m.params["mode"].startswith("populations") and "angle" not in (m.readout or {}):
            P("error", "Population readout needs SingleShot data (angle, threshold) for every read-out qubit "
                       "in this readout group.", m.block, "mode")

    # ---------------------------------------------------------------- sweeps
    used = set()                                    # axes some field points at
    for b in seq.blocks():
        for src in b.fields.values():
            base = getattr(src, "base", src)
            if getattr(base, "kind", None) == "sweep":
                used.add(base.axis)
    names = [a.name for a in seq.settings.sweeps]
    for a in seq.settings.sweeps:
        if a.name not in used:
            P("info", f"Sweep axis ‹{a.name}› is defined but no field uses it.")
        if a.points < 1:
            P("error", f"Sweep axis ‹{a.name}› needs at least one point.")
        if a.name in RESERVED_AXIS_NAMES:
            P("error", f"Sweep axis ‹{a.name}› has the same name as a saved data set "
                       f"({', '.join(sorted(RESERVED_AXIS_NAMES))}); rename it.")
    for name in sorted({n for n in names if names.count(n) > 1}):
        P("error", f"Two sweep axes are called ‹{name}›; each axis needs its own name.")
    n_points = seq.settings.n_points()
    if n_points > MAX_SWEEP_POINTS:
        P("error", f"The sweep has {n_points:,} points (the axes multiply); the limit is {MAX_SWEEP_POINTS:,}.")

    return probs
