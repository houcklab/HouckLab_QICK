"""Beamsplitter segment: per-channel timed jumps, after BSClean (mBSDoubleJump_CleanTiming.py).

Per FF channel j, in samples:

    t_offset[j]              at the level the previous segment ended on (alignment pad)
    intermediate_samples[j]  at intermediate_gains[j]            (double jump; skipped if None)
    bs_samples[j]            at bs_gains[j]                       (the swap) + pad_samples[j] + extra_samples
    padding to the longest   at exit_gains[j]                     (settle before readout)

t_offset is shifted so its minimum is 0, as BSClean does. ``extra_samples`` is added to
every channel's swap and is the field to sweep for a beamsplitter-time trace.
"""
from __future__ import annotations

import numpy as np

from ..core.block import BuildContext, FieldSpec, SegmentBlock, SegmentWave, vec_default
from ..core.params import FromPrev, Ref, Value
from .flux import GAIN_LIMITS, _vec
from .registry import register

_BS = "calib:ff_groups/dynamics_groups/{bs_group}/{bs_entry}"


@register
class Beamsplitter(SegmentBlock):
    TYPE = "Beamsplitter"
    LABEL = "Beamsplitter"
    FAMILY = "Readout"
    DEFAULT_ACT = "readout"
    DESCRIPTION = ("Jump pairs onto resonance for a timed swap, with per-channel alignment offsets and an "
                   "optional intermediate jump, then settle at the readout point.")
    FIELDS = [
        FieldSpec("bs_group", "BS group", "str", lambda: Value("four_qubit_correlations"), template=True,
                  sources=("value",), options="calib:ff_groups/dynamics_groups",
                  doc="Group under ff_groups/dynamics_groups that holds the beamsplitter calibration."),
        FieldSpec("bs_entry", "BS entry", "str", lambda: Value("1234_correlations"), template=True,
                  sources=("value",), options="calib:ff_groups/dynamics_groups/{bs_group}",
                  doc="The beamsplitter calibration: its FF_BS, t_offset and exact_t_bs fill the fields below."),
        FieldSpec("readout_group", "Readout group", "str", lambda: Value("readout_3800"), template=True,
                  sources=("value",), options="readout_groups",
                  doc="Readout group whose FF_Readouts the segment settles at after the swap."),
        FieldSpec("from_gains", "From gains", "vector", vec_default(FromPrev), unit="DAC", limits=GAIN_LIMITS,
                  sources=("from_prev", "value", "ref"), advanced=True,
                  doc="The level each channel holds during its alignment offset. Normally the previous segment's end."),
        FieldSpec("bs_gains", "BS gains", "vector", vec_default(lambda: Ref(_BS + "/FF_BS")), unit="DAC",
                  limits=GAIN_LIMITS, doc="The flux gains that bring pairs onto resonance for the swap."),
        FieldSpec("bs_samples", "Swap samples", "vector", vec_default(lambda: Ref(_BS + "/exact_t_bs")),
                  unit="samples", limits=(0, 100000),
                  doc="How long each channel sits at its BS gain, in samples (3440.64 per \u00b5s on 8QV1)."),
        FieldSpec("extra_samples", "Extra swap samples", "int", lambda: Value(0), unit="samples",
                  limits=(0, 100000), doc="Added to every channel's swap. Sweep this for a beamsplitter-time trace."),
        FieldSpec("t_offset", "Alignment offset", "vector", vec_default(lambda: Ref(_BS + "/t_offset")),
                  unit="samples", limits=(0, 10000),
                  doc="Per-channel delay before the jump, so all channels reach the BS point together. "
                      "Shifted so the smallest is 0."),
        FieldSpec("intermediate_gains", "Intermediate gains", "vector",
                  vec_default(lambda: Value([None] * 8)), unit="DAC", limits=GAIN_LIMITS, nullable=True,
                  sources=("value", "ref"), advanced=True,
                  doc="Double jump: a stop on the way to the BS gain. Leave a cell empty for no stop on that channel."),
        FieldSpec("intermediate_samples", "Intermediate samples", "vector", vec_default(lambda: Value([0] * 8)),
                  unit="samples", limits=(0, 10000), sources=("value", "ref"), advanced=True,
                  doc="How long each channel holds its intermediate gain."),
        FieldSpec("pad_samples", "Swap pad", "vector", vec_default(lambda: Value([0] * 8)), unit="samples",
                  limits=(0, 10000), sources=("value", "ref"), advanced=True,
                  doc="Extra samples at the BS gain per channel (pad_bs)."),
        FieldSpec("exit_gains", "Exit gains", "vector",
                  vec_default(lambda: Ref("calib:drive_groups/{readout_group}/FF_Readouts")), unit="DAC",
                  limits=GAIN_LIMITS, doc="Where each channel settles after its swap, until readout."),
    ]

    def build(self, p: dict, ctx: BuildContext) -> SegmentWave:
        n = ctx.n_channels
        frm = _vec(p, "from_gains", n)
        bs = _vec(p, "bs_gains", n)
        exit_ = _vec(p, "exit_gains", n)
        t_off = np.asarray(p["t_offset"], float).astype(int)
        t_off = t_off - t_off.min()
        inter_g = list(p["intermediate_gains"])
        inter_n = np.asarray(p["intermediate_samples"], float).astype(int)
        swap = (np.asarray(p["bs_samples"], float).astype(int) + np.asarray(p["pad_samples"], float).astype(int)
                + int(p["extra_samples"]))
        ig = np.array([bs[j] if inter_g[j] is None else float(inter_g[j]) for j in range(n)])
        inter_n = np.array([0 if inter_g[j] is None else inter_n[j] for j in range(n)])
        busy = t_off + inter_n + swap
        total = int(busy.max()) if n else 0
        rows = []
        for j in range(n):
            rows.append(np.repeat([frm[j], ig[j], bs[j], exit_[j]],
                                  [t_off[j], inter_n[j], swap[j], total - busy[j]]).astype(float))
        return SegmentWave(np.vstack(rows) if rows else np.zeros((0, 0)), frm.copy(), exit_.copy())
