"""Qubit-lane pulse blocks: pi, pi/2 and a generic Gaussian drive.

All qubit drives share one generator (the station's qubit_ch), so pulses on different
qubits inside one segment play one after another; the validator says so.

Calibration paths use ``{entry}``, which is the drive-group entry for this qubit. It
defaults to the qubit number ("3"); groups whose entries are named differently
(e.g. ramsey_3800+ uses "3_3800+") set ``entry`` explicitly. Bob never parses a qubit
index out of an entry name.
"""
from __future__ import annotations

from ..core.block import DriveSpec, FieldSpec, PulseBlock
from ..core.params import Ref, Value
from .registry import register

_Q = "calib:drive_groups/{drive_group}/entries/{entry}/Qubit"


def _common_fields(gain_scale: float = 1.0):
    half = " Half the \u03c0 gain by default." if gain_scale == 0.5 else ""
    return [
        FieldSpec("qubit", "Qubit", "qubit", lambda: Value(1), template=True, sources=("value",),
                  doc="Which qubit lane the pulse is on, and whose calibration it reads."),
        FieldSpec("drive_group", "Drive group", "str", lambda: Value("readout_3800"), template=True,
                  sources=("value",), options="calib:drive_groups",
                  doc="Drive group in qubit_parameters.json the pulse's frequency, gain and sigma come from."),
        FieldSpec("entry", "Entry", "str", lambda: Value(""), template=True, sources=("value",), advanced=True,
                  options="calib:drive_groups/{drive_group}/entries",
                  doc="The group entry for this qubit. Leave as (qubit number) when entries are named 1, 2, 3...; "
                      "pick one for groups like ramsey_3800+ that name them 3_3800+."),
        FieldSpec("freq", "Frequency", "float", lambda: Ref(_Q + "/Frequency"), unit="MHz", limits=(0, 20000),
                  doc="Drive frequency. Must sit within the qubit mixer band."),
        FieldSpec("gain", "Gain", "float", lambda: Ref(_Q + "/Gain", gain_scale), unit="DAC",
                  limits=(-32766, 32766), doc="Drive amplitude, out of 32766." + half),
        FieldSpec("sigma_us", "Sigma", "float", lambda: Ref(_Q + "/sigma"), unit="\u00b5s", limits=(0.0005, 10.0),
                  doc="Width of the Gaussian. The pulse lasts Length \u00d7 sigma."),
        FieldSpec("phase", "Phase", "float", lambda: Value(0.0), unit="deg", limits=(-3600, 3600),
                  doc="Drive phase. Sets the rotation axis, e.g. for measurement \u03c0/2 pulses."),
        FieldSpec("relative_t", "Start", "str", lambda: Value("auto"), sources=("value",), advanced=True,
                  doc="auto: right after the previous pulse in this segment. "
                      "A number: \u00b5s from the segment start."),
        FieldSpec("len_sigmas", "Length", "float", lambda: Value(4.0), unit="\u03c3", limits=(1.0, 12.0),
                  sources=("value",), advanced=True, doc="Pulse length in units of sigma."),
    ]


class _GaussianPulse(PulseBlock):
    def template_values(self) -> dict:
        v = super().template_values()
        if not str(v.get("entry", "")).strip():
            v["entry"] = str(v.get("qubit", ""))
        return v

    def drive(self, p: dict) -> DriveSpec:
        rt = p.get("relative_t", "auto")
        if isinstance(rt, str) and rt.strip().lower() != "auto":
            rt = float(rt)
        return DriveSpec(qubit=int(p["qubit"]), freq_mhz=float(p["freq"]), gain=float(p["gain"]),
                         phase_deg=float(p["phase"]), sigma_us=float(p["sigma_us"]),
                         len_sigmas=float(p["len_sigmas"]), relative_t=rt)


@register
class PiPulse(_GaussianPulse):
    TYPE = "PiPulse"
    LABEL = "π pulse"
    DESCRIPTION = "Calibrated π pulse on one qubit, from its drive-group entry."
    FIELDS = _common_fields(1.0)


@register
class Pi2Pulse(_GaussianPulse):
    TYPE = "Pi2Pulse"
    LABEL = "π/2 pulse"
    DESCRIPTION = "Half-gain π pulse with a settable phase: state prep or measurement π/2."
    FIELDS = _common_fields(0.5)


@register
class Drive(_GaussianPulse):
    TYPE = "Drive"
    LABEL = "Drive"
    DESCRIPTION = "A Gaussian drive with every parameter set by hand. Sweep its gain for a Rabi."
    FIELDS = [
        FieldSpec("qubit", "Qubit", "qubit", lambda: Value(1), template=True, sources=("value",),
                  doc="Which qubit lane the pulse is drawn on."),
        FieldSpec("freq", "Frequency", "float", lambda: Value(4000.0), unit="MHz", limits=(0, 20000),
                  doc="Drive frequency. Must sit within the qubit mixer band."),
        FieldSpec("gain", "Gain", "float", lambda: Value(5000.0), unit="DAC", limits=(-32766, 32766),
                  doc="Drive amplitude, out of 32766. Sweep it for a Rabi."),
        FieldSpec("sigma_us", "Sigma", "float", lambda: Value(0.03), unit="\u00b5s", limits=(0.0005, 10.0),
                  doc="Width of the Gaussian."),
        FieldSpec("phase", "Phase", "float", lambda: Value(0.0), unit="deg", limits=(-3600, 3600),
                  doc="Drive phase."),
        FieldSpec("relative_t", "Start", "str", lambda: Value("auto"), sources=("value",), advanced=True,
                  doc="auto: right after the previous pulse in this segment. "
                      "A number: \u00b5s from the segment start."),
        FieldSpec("len_sigmas", "Length", "float", lambda: Value(4.0), unit="\u03c3", limits=(1.0, 12.0),
                  sources=("value",), advanced=True, doc="Pulse length in units of sigma."),
    ]
