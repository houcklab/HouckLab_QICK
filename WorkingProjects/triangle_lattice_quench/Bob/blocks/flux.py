"""Flux-track segment blocks: FF hold, Ramp, Dynamics (FF waveform)."""
from __future__ import annotations

import numpy as np

from ..core.block import BuildContext, FieldSpec, SegmentBlock, SegmentWave, vec_default
from ..core.params import FromPrev, Ref, Value
from ..hardware.ramps import SHAPES, ramp
from .registry import register

GAIN_LIMITS = (-32766, 32766)


def _vec(p, key, n):
    v = np.asarray(p[key], float)
    if v.shape != (n,):
        raise ValueError(f"{key} must have {n} entries, got shape {v.shape}")
    return v


@register
class FFHold(SegmentBlock):
    TYPE = "FFHold"
    LABEL = "FF hold"
    FAMILY = "Preparation"
    DEFAULT_ACT = "prep"
    DESCRIPTION = "Hold every flux channel at fixed gains. The init / drive point, or a wait."
    FIELDS = [
        FieldSpec("group", "Drive group", "str", lambda: Value("readout_3800"), template=True,
                  sources=("value",), options="calib:drive_groups",
                  doc="The drive group in qubit_parameters.json whose FF_Pulses (the drive point) this hold uses."),
        FieldSpec("gains", "FF gains", "vector", vec_default(lambda: Ref("calib:drive_groups/{group}/FF_Pulses")),
                  unit="DAC", limits=GAIN_LIMITS,
                  doc="The flux gain held on each channel, Q1 to Q8. Defaults to the drive group's FF_Pulses."),
        FieldSpec("duration_us", "Duration", "float", lambda: Value(0.3), unit="\u00b5s", limits=(0.0, 1000.0),
                  doc="How long to hold. Pulses placed in this segment must fit inside it."),
    ]

    def build(self, p: dict, ctx: BuildContext) -> SegmentWave:
        g = _vec(p, "gains", ctx.n_channels)
        n = ctx.us_to_samples(p["duration_us"])
        return SegmentWave(np.repeat(g[:, None], n, axis=1), g.copy(), g.copy())


@register
class FFRamp(SegmentBlock):
    TYPE = "FFRamp"
    LABEL = "Ramp"
    FAMILY = "Preparation"
    DEFAULT_ACT = "prep"
    DESCRIPTION = ("Ramp every flux channel from where the previous segment ended (plus an optional "
                   "init offset) to the target gains.")
    FIELDS = [
        FieldSpec("ramp_group", "Ramp group", "str", lambda: Value("ramp_3800"), template=True, sources=("value",),
                  options="calib:ff_groups/ramp_groups",
                  doc="Group under ff_groups/ramp_groups in qubit_parameters.json."),
        FieldSpec("ramp_entry", "Ramp entry", "str", lambda: Value("8Q_1854"), template=True, sources=("value",),
                  options="calib:ff_groups/ramp_groups/{ramp_group}",
                  doc="The ramp target within the group; its FF_Expt gives the end gains."),
        FieldSpec("start_gains", "Start gains", "vector", vec_default(FromPrev), unit="DAC", limits=GAIN_LIMITS,
                  sources=("from_prev", "value", "ref"),
                  doc="Where the ramp starts. Normally where the previous segment ended."),
        FieldSpec("start_offset", "Init offset", "vector", vec_default(lambda: Value([0] * 8)), unit="DAC",
                  sources=("value", "ref"), advanced=True,
                  doc="Added to the start gains before ramping, to detune chosen qubits first (FF_Init_delta)."),
        FieldSpec("end_gains", "End gains", "vector",
                  vec_default(lambda: Ref("calib:ff_groups/ramp_groups/{ramp_group}/{ramp_entry}/FF_Expt")),
                  unit="DAC", limits=GAIN_LIMITS, doc="The lattice point the ramp ends at, per channel."),
        FieldSpec("duration_us", "Duration", "float", lambda: Value(1.0), unit="\u00b5s", limits=(0.0, 1000.0),
                  doc="How long the ramp takes."),
        FieldSpec("shape", "Shape", "choice", lambda: Value("cubic"), choices=SHAPES, sources=("value",),
                  doc="linear: constant rate. cubic: fast start, gentle finish. exponential: e-folding approach."),
    ]

    def build(self, p: dict, ctx: BuildContext) -> SegmentWave:
        n_ch = ctx.n_channels
        start = _vec(p, "start_gains", n_ch) + _vec(p, "start_offset", n_ch)
        end = _vec(p, "end_gains", n_ch)
        n = ctx.us_to_samples(p["duration_us"])
        arr = np.vstack([ramp(start[j], end[j], n, p["shape"]) for j in range(n_ch)]) if n > 0 \
            else np.zeros((n_ch, 0))
        return SegmentWave(arr, start, end.copy())


@register
class FFDynamics(SegmentBlock):
    TYPE = "FFDynamics"
    LABEL = "Dynamics"
    FAMILY = "Dynamics"
    DEFAULT_ACT = "dynamics"
    DESCRIPTION = ("Jump to the dynamics point and hold, usually with a swept duration. "
                   "Or play a waveform from a .npy file of shape (channels, samples).")
    FIELDS = [
        FieldSpec("dyn_group", "Dynamics group", "str", lambda: Value("dynamics_FF_points"), template=True,
                  sources=("value",), options="calib:ff_groups/dynamics_groups",
                  doc="Group under ff_groups/dynamics_groups in qubit_parameters.json."),
        FieldSpec("dyn_entry", "Dynamics entry", "str", lambda: Value("resonant"), template=True,
                  sources=("value",), options="calib:ff_groups/dynamics_groups/{dyn_group}",
                  doc="The dynamics point within the group; its FF_Dynamics gives the gains."),
        FieldSpec("mode", "Mode", "choice", lambda: Value("hold"), choices=("hold", "file"), sources=("value",),
                  doc="hold: jump to the gains and stay for the duration. file: play a waveform from a .npy file "
                      "(set under Advanced); the duration is then ignored."),
        FieldSpec("gains", "FF gains", "vector",
                  vec_default(lambda: Ref("calib:ff_groups/dynamics_groups/{dyn_group}/{dyn_entry}/FF_Dynamics")),
                  unit="DAC", limits=GAIN_LIMITS, doc="The flux gains during the dynamics, per channel."),
        FieldSpec("duration_us", "Duration", "float", lambda: Value(0.5), unit="\u00b5s", limits=(0.0, 1000.0),
                  doc="How long the dynamics run. Usually swept."),
        FieldSpec("waveform_file", "Waveform file", "str", lambda: Value(""), sources=("value",), advanced=True,
                  doc="For mode = file: a .npy array shaped (channels, samples) of applied gains, "
                      "at the station sample rate (3440.64 per \u00b5s on 8QV1)."),
    ]

    def build(self, p: dict, ctx: BuildContext) -> SegmentWave:
        n_ch = ctx.n_channels
        if p["mode"] == "file":
            path = str(p["waveform_file"]).strip()
            if not path:
                raise ValueError("mode is 'file' but no waveform file is set")
            arr = np.asarray(np.load(path), float)
            if arr.ndim != 2 or arr.shape[0] != n_ch:
                raise ValueError(f"waveform file must have shape ({n_ch}, samples), got {arr.shape}")
            return SegmentWave(arr, arr[:, 0].copy(), arr[:, -1].copy())
        g = _vec(p, "gains", n_ch)
        n = ctx.us_to_samples(p["duration_us"])
        return SegmentWave(np.repeat(g[:, None], n, axis=1), g.copy(), g.copy())
