"""Time units: microseconds, FF DAC samples, and fabric clock cycles (16 samples each).

At the 8QV1 clock (215.04 MHz fabric, 16 samples per cycle) one cycle is 4.65 ns and
there are 3440.64 samples per microsecond.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

SAMPLES_PER_CYCLE = 16


def us_to_samples(us: float, samples_per_us: float) -> int:
    return int(round(float(us) * samples_per_us))


def samples_to_us(n: float, samples_per_us: float) -> float:
    return float(n) / samples_per_us


def ceil_to_cycle(n_samples: int) -> int:
    return SAMPLES_PER_CYCLE * math.ceil(int(n_samples) / SAMPLES_PER_CYCLE)


@dataclass
class ScheduledDrive:
    pulse_index: int          # index into ResolvedSequence.pulses
    segment_index: int
    t_us: float               # start time from the start of the stitched FF body
    length_us: float
    segment_start_us: float
    segment_end_us: float


def schedule_drives(seg_lengths: list, drives_by_segment: list, samples_per_us: float,
                    drive_offset_cycles: int = 0) -> list:
    """Start time of every drive, replicating ProgramBuilder.drive_schedule / _body.

    ``drives_by_segment[i]`` is a list of (pulse_index, DriveSpec) in play order.
    Each segment's drives are measured from the segment start rounded UP to the next clock
    cycle; ``relative_t == "auto"`` places a drive right after the latest-ending one. A
    positive ``drive_offset_cycles`` shifts every drive later by that many cycles.
    """
    cycle_us = SAMPLES_PER_CYCLE / samples_per_us
    out = []
    cumulative = SAMPLES_PER_CYCLE * max(0, int(drive_offset_cycles))
    for si, n_seg in enumerate(seg_lengths):
        # tProc timing has cycle resolution, so a segment's drives start at its first cycle boundary
        seg_start_us = cycle_us * math.ceil(cumulative / SAMPLES_PER_CYCLE)
        seg_end_us = (cumulative + n_seg) / samples_per_us
        cursor = seg_start_us
        for pi, d in drives_by_segment[si]:
            t = cursor if d.relative_t == "auto" else seg_start_us + float(d.relative_t)
            cursor = max(cursor, t + d.length_us())
            out.append(ScheduledDrive(pi, si, t, d.length_us(), seg_start_us, seg_end_us))
        cumulative += int(n_seg)
    return out
