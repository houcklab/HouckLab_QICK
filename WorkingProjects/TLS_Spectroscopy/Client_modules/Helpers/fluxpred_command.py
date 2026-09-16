import numpy as np

from fluxpred.core import Command, Filter, render, render_on_schedule, slice_command
from fluxpred.validation import shot_schedule
from fluxpred import qick as qick_backend

DEVICE = "q3"
COORDINATE_UNIT = "DAC_gain"
DEFAULT_SCHEDULE_FIRST_NS = 2000.0
DEFAULT_SCHEDULE_GROWTH = 1.35
DEFAULT_SCHEDULE_MAX_NS = 100_000.0


def fabric_clock_ns(soccfg, channel):
    try:
        fabric_mhz = float(soccfg["gens"][int(channel)]["f_fabric"])
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise ValueError(
            f"soccfg does not report a fabric clock for generator channel {channel}; the "
            f"flux command clock must never be hard coded") from error
    if not np.isfinite(fabric_mhz) or fabric_mhz <= 0:
        raise ValueError(f"soccfg reports an invalid fabric clock {fabric_mhz!r}")
    return 1000.0 / fabric_mhz


def identity_model(taus_ns=(8_000.0, 24_000.0, 64_000.0, 192_000.0), resolution_ns=1000.0):
    taus = np.asarray(taus_ns, dtype=float)
    return Filter(taus, [1.0], [np.zeros(taus.size)], resolution_ns=resolution_ns)


def build_timeline(model, *, amplitude, hold_ns, recovery_ns, initial_state=None,
                   schedule_first_ns=DEFAULT_SCHEDULE_FIRST_NS,
                   schedule_growth=DEFAULT_SCHEDULE_GROWTH,
                   schedule_max_ns=DEFAULT_SCHEDULE_MAX_NS, quantum_ns=None):
    if model is None:
        command = Command([0.0, float(hold_ns), float(hold_ns)+float(recovery_ns)],
                          [float(amplitude), 0.0])
        return command, np.zeros(0)
    schedule = shot_schedule(amplitude=amplitude, hold_ns=hold_ns, recovery_ns=recovery_ns,
                             first_ns=schedule_first_ns, growth=schedule_growth,
                             max_ns=schedule_max_ns, quantum_ns=quantum_ns)
    return render_on_schedule(model, schedule, initial_state=initial_state)


def compile_for_program(command, prog, *, channel, park_gain, scale_gain, max_instructions=4096,
                        reserved_instructions=64):
    clock_ns = fabric_clock_ns(prog.soccfg, channel)
    plan = qick_backend.compile_command(
        command, park_gain=float(park_gain), scale_gain=float(scale_gain), clock_ns=clock_ns,
        max_instructions=int(max_instructions), reserved_instructions=int(reserved_instructions))
    qick_backend.validate_program_compatibility(plan, prog, channel=channel)
    return plan


def split_for_probe(command, *, probe_start_ns, probe_window_ns, pulse_ns):
    probe_start_ns = float(probe_start_ns)
    probe_window_ns = float(probe_window_ns)
    pulse_ns = float(pulse_ns)
    if probe_window_ns <= 0 or pulse_ns < 0:
        raise ValueError("probe window must be positive and the pulse length nonnegative")
    horizon = float(command.edges_ns[-1])
    first_end = probe_start_ns + pulse_ns
    probe_end = first_end + probe_window_ns
    second_end = probe_end + pulse_ns
    if second_end > horizon + 1e-9:
        raise ValueError(
            f"the probe at {probe_start_ns/1000.0:g} us plus its {probe_window_ns:g} ns window and "
            f"two {pulse_ns:g} ns pulses runs past the {horizon/1000.0:g} us flux timeline")
    parts = {"before": slice_command(command, 0.0, probe_start_ns) if probe_start_ns > 0 else None,
             "first_pulse": slice_command(command, probe_start_ns, first_end) if pulse_ns > 0 else None,
             "probe": slice_command(command, first_end, probe_end),
             "second_pulse": slice_command(command, probe_end, second_end) if pulse_ns > 0 else None,
             "after": slice_command(command, second_end, horizon) if horizon-second_end > 1e-9 else None}
    parts["probe_level"] = float(parts["probe"].values[0])
    parts["probe_start_ns"] = first_end
    parts["probe_end_ns"] = probe_end
    return parts


def freeze_probe_segment(part):
    return Command([0.0, float(part.edges_ns[-1])], [float(part.values[0])])


def emit_part(plan, prog, *, channel):
    qick_backend.emit(plan, prog, channel=channel)


def plan_report(plan, command):
    return {"clock_ns": float(plan.clock_ns),
            "segments": int(len(plan.segments)),
            "instruction_estimate": int(plan.instruction_estimate),
            "max_instructions": int(plan.max_instructions),
            "park_gain": float(plan.park_gain),
            "scale_gain": float(plan.scale_gain),
            "min_gain": int(min(segment.gain for segment in plan.segments)),
            "max_gain": int(max(segment.gain for segment in plan.segments)),
            "dac_limit": int(plan.max_gain),
            "horizon_ns": float(sum(segment.cycles for segment in plan.segments)*plan.clock_ns),
            "requested_horizon_ns": float(command.edges_ns[-1])}
