"""Twelve independent echo measurements per streamed hardware record.

The phase-major order interleaves short echo, long echo, and a late pulse
control on the millisecond scale. Each subshot keeps the existing corrected
return, park readout, and passive relaxation; batching only removes repeated
program uploads. One streamed record contains twelve complex IQ values.
"""

from copy import deepcopy
from dataclasses import dataclass
import math

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSEchoRefocusProgram as refocus
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.records import signed32


SHOTS_PER_CONDITION = 200
CONDITIONS_PER_CYCLE = 12
RECORD_WORDS = 2 * CONDITIONS_PER_CYCLE


def conditions():
    return [{"name": f"{group}_{phase}", "group": group,
             "kind": kind, "elapsed_us": elapsed, "phase_deg": phase}
            for phase in (0, 90, 180, 270)
            for group, kind, elapsed in (("short", "hahn_y", .35),
                                          ("long", "hahn_y", 1.35),
                                          ("late", "late_control", 1.35))]


@dataclass(frozen=True)
class EchoCycle:
    iq: tuple[complex, ...]


def decode_dmem_records(words, expected_records=None):
    flat = np.asarray(words).ravel()
    if flat.size % RECORD_WORDS:
        raise ValueError("echo cycle requires 24 words for twelve IQ pairs")
    count = flat.size // RECORD_WORDS
    if expected_records is not None and count != int(expected_records):
        raise ValueError(f"expected {expected_records} echo cycles; got {count}")
    signed = np.asarray([signed32(value) for value in flat], dtype=np.int64)
    pairs = signed.reshape(count, CONDITIONS_PER_CYCLE, 2)
    return [EchoCycle(tuple(complex(i, q) for i, q in cycle)) for cycle in pairs]


def records_iq(records):
    return np.asarray([record.iq for record in records], dtype=complex).reshape(
        -1, CONDITIONS_PER_CYCLE)


def make_program(parent):
    class FewPointProgram(refocus.make_decay_program(parent)):
        record_words = RECORD_WORDS
        decode_dmem_records = staticmethod(decode_dmem_records)

        def _emit_body(self):
            if (self.cfg.get("opx_resident_preparation_state", "g") != "g" or
                    self.cfg.get("opx_resident_reference_state") is not None):
                raise ValueError("few-point echo needs ground preparation and no final reference pi")
            relax = float(self.reset_config.inter_shot_delay_us)
            recovery = float(self._t1_ff_predistortion_recovery_us)
            if not math.isfinite(relax) or relax < 500.:
                raise ValueError("every echo subshot needs at least 500 us passive relaxation")
            if not math.isfinite(recovery) or recovery < 40.:
                raise ValueError("every echo subshot needs the complete 40 us corrected return")
            original = deepcopy(self.cfg)
            emitted = []
            try:
                for condition in conditions():
                    self.cfg.update(refocus_sequence=condition["kind"],
                                    refocus_elapsed_us=condition["elapsed_us"],
                                    echo_phase_deg=condition["phase_deg"])
                    super()._emit_body()
                    emitted.append({**condition,
                                    "timing": deepcopy(self.cfg["refocus_timing"])})
            finally:
                self.cfg.clear()
                self.cfg.update(original)
                self.cfg["few_point_conditions"] = emitted

    return FewPointProgram
