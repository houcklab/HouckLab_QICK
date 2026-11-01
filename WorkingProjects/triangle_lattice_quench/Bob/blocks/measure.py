"""Measure: MUX readout of chosen qubits at the readout flux point. Always the last column."""
from __future__ import annotations

from ..core.block import FieldSpec, MeasureBlock, vec_default
from ..core.params import Ref, Value
from .registry import register

MODES = ("populations_corrected", "populations", "iq")


@register
class Measure(MeasureBlock):
    TYPE = "Measure"
    LABEL = "Measure"
    DESCRIPTION = ("MUX readout of the chosen qubits. Readout frequencies, gains, lengths and single-shot "
                   "calibration come from the readout group.")
    FIELDS = [
        FieldSpec("readout_group", "Readout group", "str", lambda: Value("readout_3800"), template=True,
                  sources=("value",), options="readout_groups",
                  doc="Readout group in qubit_parameters.json: readout frequencies, gains, lengths, single-shot "
                      "calibration and the readout flux point."),
        FieldSpec("qubits", "Qubits", "qubits", lambda: Value([1, 2, 3, 4]), sources=("value",),
                  doc="Which qubits to read out, multiplexed."),
        FieldSpec("mode", "Result", "choice", lambda: Value("populations_corrected"), choices=MODES,
                  sources=("value",),
                  doc="populations_corrected: excited-state population with readout error removed. populations: "
                      "without the correction. iq: raw averaged I/Q. Populations need SingleShot data."),
        FieldSpec("ff_readout_gains", "Readout FF gains", "vector",
                  vec_default(lambda: Ref("calib:drive_groups/{readout_group}/FF_Readouts")),
                  unit="DAC", limits=(-32766, 32766), doc="Flux gains held during readout, per channel."),
        FieldSpec("res_length_us", "Readout pulse", "float", lambda: Ref("station:res_length"), unit="\u00b5s",
                  limits=(0.01, 100.0), sources=("value", "ref"),
                  doc="Length of the resonator readout pulse. Defaults to the station's res_length."),
    ]
