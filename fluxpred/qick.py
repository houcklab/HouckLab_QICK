from dataclasses import dataclass

import numpy as np


MIN_CYCLES = 3
MAX_CYCLES = 65000
INSTRUCTIONS_PER_SEGMENT = 32


@dataclass(frozen=True)
class QickSegment:
    gain: int
    cycles: int


@dataclass(frozen=True)
class QickPlan:
    segments: tuple[QickSegment, ...]
    clock_ns: float
    park_gain: float
    scale_gain: float
    max_gain: int
    instruction_estimate: int
    max_instructions: int
    reserved_instructions: int

    @property
    def waveform_samples(self):
        return 0

    @property
    def actual_compile_checked(self):
        return False

    @property
    def normalized_command(self):
        return reconstruct_command(self)


def _integer(value, name, minimum, maximum=None):
    number = float(value)
    if (isinstance(value, (bool, np.bool_)) or not np.isfinite(number)
            or number != np.rint(number) or number < minimum
            or (maximum is not None and number > maximum)):
        raise ValueError(f"{name} must be an integer in the supported range")
    return int(number)


def compile_command(command, *, park_gain, scale_gain, clock_ns,
                    max_gain=32767, max_instructions=4096,
                    reserved_instructions=64):
    park_gain, scale_gain, clock_ns = map(float, (park_gain, scale_gain, clock_ns))
    if not np.isfinite(park_gain):
        raise ValueError("park_gain must be finite")
    if not np.isfinite(scale_gain) or scale_gain == 0:
        raise ValueError("scale_gain must be finite and nonzero")
    if not np.isfinite(clock_ns) or clock_ns <= 0:
        raise ValueError("clock_ns must be positive and finite")
    max_gain = _integer(max_gain, "max_gain", 1, 32767)
    max_instructions = _integer(max_instructions, "max_instructions", 1)
    reserved_instructions = _integer(reserved_instructions, "reserved_instructions", 0)
    edges = np.asarray(command.edges_ns, dtype=float)
    values = np.asarray(command.values, dtype=float)
    if (edges.ndim != 1 or values.ndim != 1 or values.size == 0
            or edges.size != values.size + 1 or edges[0] != 0
            or not np.all(np.isfinite(edges)) or not np.all(np.isfinite(values))
            or np.any(np.diff(edges) <= 0)):
        raise ValueError("command needs finite increasing edges from zero and one value per interval")
    with np.errstate(over="ignore", invalid="ignore"):
        gains = park_gain + scale_gain * values
        ticks = np.rint(edges / clock_ns)
    if (abs(park_gain) > max_gain or not np.all(np.isfinite(gains))
            or np.any(np.abs(gains) > max_gain)):
        raise ValueError("requested gain exceeds the configured DAC range; clipping is forbidden")
    if not np.all(np.isfinite(ticks)) or np.any(ticks > 2**53):
        raise ValueError("command duration exceeds exact cumulative cycle representation")
    integer_gains = [int(value) for value in np.rint(gains)]
    durations = [int(stop) - int(start) for start, stop in zip(ticks[:-1], ticks[1:])]
    merged = []
    for gain, cycles in zip(integer_gains, durations):
        if merged and merged[-1][0] == gain:
            merged[-1] = (gain, merged[-1][1] + cycles)
        else:
            merged.append((gain, cycles))
    if any(cycles < MIN_CYCLES for _, cycles in merged):
        raise ValueError("a distinct command segment is shorter than three fabric cycles")
    count = sum((cycles + MAX_CYCLES - 1) // MAX_CYCLES for _, cycles in merged)
    estimate = reserved_instructions + INSTRUCTIONS_PER_SEGMENT * count
    if estimate > max_instructions:
        raise ValueError(f"estimated instruction allowance {estimate} exceeds budget {max_instructions}")
    segments = []
    for gain, total in merged:
        chunks = (total + MAX_CYCLES - 1) // MAX_CYCLES
        base, extra = divmod(total, chunks)
        segments.extend(QickSegment(gain, base + int(index < extra)) for index in range(chunks))
    return QickPlan(tuple(segments), clock_ns, park_gain, scale_gain, max_gain,
                    estimate, max_instructions, reserved_instructions)


def reconstruct_command(plan):
    from .core import Command

    edges = np.concatenate(([0.0], np.cumsum([seg.cycles for seg in plan.segments], dtype=float)))
    values = (np.asarray([seg.gain for seg in plan.segments], dtype=float)
              - plan.park_gain) / plan.scale_gain
    return Command(edges * plan.clock_ns, values)


def validate_program_compatibility(plan, prog, *, channel):
    channel = _integer(channel, "channel", 0)
    try:
        generator = prog.soccfg["gens"][channel]
        fabric_mhz = float(generator["f_fabric"])
        hardware_max = int(float(generator["maxv"]) * float(generator.get("maxv_scale", 1.0)))
    except (AttributeError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise ValueError("program must report generator fabric clock and DAC limits") from exc
    if not np.isfinite(fabric_mhz) or fabric_mhz <= 0:
        raise ValueError("program reports an invalid generator clock")
    if not np.isclose(1000.0 / fabric_mhz, plan.clock_ns, rtol=1e-10, atol=1e-12):
        raise ValueError("compiled command clock does not match the generator fabric clock")
    if int(prog.us2cycles(plan.clock_ns, gen_ch=channel)) != 1000:
        raise ValueError("program us2cycles disagrees with the compiled generator clock")
    if hardware_max <= 0 or any(abs(segment.gain) > hardware_max for segment in plan.segments):
        raise ValueError("compiled command exceeds the program generator gain range")
    if hasattr(prog, "gen_chs") and channel not in prog.gen_chs:
        raise ValueError("flux generator channel must be declared before command emission")


def emit(plan, prog, *, channel):
    validate_program_compatibility(plan, prog, channel=channel)
    for segment in plan.segments:
        prog.set_pulse_registers(ch=int(channel), freq=0, style="const", phase=0,
                                 stdysel="last", gain=segment.gain, length=segment.cycles)
        prog.pulse(ch=int(channel))
