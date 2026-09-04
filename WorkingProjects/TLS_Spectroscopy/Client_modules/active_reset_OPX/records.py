from dataclasses import dataclass
from enum import IntEnum

import numpy as np


RECORD_SCHEMA_VERSION = 1
RECORD_WORDS = 8


class TerminalStatus(IntEnum):
    CONFIRMED_GROUND = 0
    MAX_ITERATIONS_REACHED = 1
    NO_RESET = 2
    ERROR = 3


@dataclass(frozen=True)
class ShotRecord:
    preparation: int
    initial_z: int
    reset_attempts: int
    pi_pulses: int
    terminal_status: TerminalStatus
    final_i: int
    final_q: int
    last_z: int

    def to_words(self):
        return [
            int(self.preparation),
            int(self.initial_z),
            int(self.reset_attempts),
            int(self.pi_pulses),
            int(self.terminal_status),
            int(self.final_i),
            int(self.final_q),
            int(self.last_z),
        ]


def signed32(value):
    value = int(value) & 0xFFFFFFFF
    return value - 2**32 if value >= 2**31 else value


def decode_records(words, expected_records=None):
    flat = np.asarray(words).ravel()
    if flat.size % RECORD_WORDS:
        raise ValueError(
            f"data-memory payload length {flat.size} is not a multiple of {RECORD_WORDS}"
        )
    count = flat.size // RECORD_WORDS
    if expected_records is not None and count != int(expected_records):
        raise ValueError(f"expected {int(expected_records)} records, received {count}")
    signed = np.asarray([signed32(v) for v in flat], dtype=np.int64).reshape(count, RECORD_WORDS)
    records = []
    for row in signed:
        try:
            status = TerminalStatus(int(row[4]))
        except ValueError as exc:
            raise ValueError(f"unknown active-reset terminal status {int(row[4])}") from exc
        records.append(ShotRecord(
            preparation=int(row[0]),
            initial_z=int(row[1]),
            reset_attempts=int(row[2]),
            pi_pulses=int(row[3]),
            terminal_status=status,
            final_i=int(row[5]),
            final_q=int(row[6]),
            last_z=int(row[7]),
        ))
    return records


def max_records(dmem_words, record_base, record_words=RECORD_WORDS):
    dmem_words, record_base, record_words = map(int, (dmem_words, record_base, record_words))
    if dmem_words <= 0 or record_words <= 0:
        raise ValueError("data-memory and record sizes must be positive")
    if record_base < 0 or record_base >= dmem_words:
        raise ValueError("record_base must lie inside data memory")
    return (dmem_words - record_base) // record_words
