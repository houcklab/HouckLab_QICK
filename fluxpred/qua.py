from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class QUAPlan:
    edges_clk: tuple
    commands_v: tuple
    park_v: float
    scale_v: float
    clock_ns: float
    voltage_quantum_v: float
    output_limit_v: float
    max_timing_error_ns: float
    max_voltage_error_v: float
    instruction_estimate: int
    hardware_compiled: bool = False


def compile_command(command, *, park_v, scale_v, clock_ns=4,
                    output_limit_v=0.5, voltage_quantum_v=2**-16,
                    max_instructions=10_000):
    park_v, scale_v, clock_ns = float(park_v), float(scale_v), float(clock_ns)
    output_limit_v, voltage_quantum_v = float(output_limit_v), float(voltage_quantum_v)
    parameters = (park_v, scale_v, clock_ns, output_limit_v, voltage_quantum_v)
    if not np.all(np.isfinite(parameters)):
        raise ValueError("QUA compiler parameters must be finite")
    if clock_ns != 4:
        raise ValueError("this QUA adapter requires a 4 ns clock")
    if scale_v == 0 or output_limit_v <= 0 or not 0 < voltage_quantum_v < output_limit_v:
        raise ValueError("scale must be nonzero; voltage limit and quantum must be positive")
    if not isinstance(max_instructions, (int, np.integer)) or isinstance(max_instructions, bool) or max_instructions < 1:
        raise ValueError("max_instructions must be a positive integer budget")

    edges = np.asarray(command.edges_ns, dtype=float)
    values = np.asarray(command.values, dtype=float)
    if edges.ndim != 1 or values.ndim != 1 or values.size == 0 or edges.size != values.size + 1:
        raise ValueError("command needs N values and N+1 one-dimensional edges")
    if not np.all(np.isfinite(edges)) or not np.all(np.isfinite(values)):
        raise ValueError("command edges and values must be finite")
    if edges[0] != 0 or np.any(np.diff(edges) <= 0):
        raise ValueError("command edges must start at zero and increase strictly")
    rounded_ticks = np.rint(edges / clock_ns)
    if np.any(rounded_ticks >= np.iinfo(np.int64).max):
        raise ValueError("command duration exceeds the supported timeline")
    ticks = rounded_ticks.astype(np.int64)
    durations = np.diff(ticks)
    if np.any(durations < 4) or np.any(durations > 2**31 - 1):
        raise ValueError("each quantized segment duration must be 4..2**31-1 clocks")

    instruction_estimate = 1 + 2 * values.size
    if instruction_estimate > max_instructions:
        raise ValueError(f"source instruction budget exceeded: {instruction_estimate} > {max_instructions}")
    lower, upper = -output_limit_v, output_limit_v - voltage_quantum_v
    with np.errstate(over="ignore", invalid="ignore"):
        requested_v = park_v + scale_v * values
    if (not np.all(np.isfinite(requested_v)) or not lower <= park_v <= upper
            or np.any(requested_v < lower) or np.any(requested_v > upper)):
        raise ValueError("absolute command or park voltage exceeds the output range")
    actual_v = np.rint(requested_v / voltage_quantum_v) * voltage_quantum_v
    if np.any(actual_v < lower) or np.any(actual_v > upper):
        raise ValueError("quantized command voltage exceeds the output range")
    return QUAPlan(
        edges_clk=tuple(int(value) for value in ticks),
        commands_v=tuple(float(value) for value in actual_v),
        park_v=park_v, scale_v=scale_v, clock_ns=clock_ns,
        voltage_quantum_v=voltage_quantum_v, output_limit_v=output_limit_v,
        max_timing_error_ns=float(np.max(np.abs(ticks * clock_ns - edges))),
        max_voltage_error_v=float(np.max(np.abs(actual_v - requested_v))),
        instruction_estimate=int(instruction_estimate),
    )


def reconstruct_command(plan):
    from .core import Command

    return Command(
        edges_ns=np.asarray(plan.edges_clk, dtype=float) * plan.clock_ns,
        values=(np.asarray(plan.commands_v, dtype=float) - plan.park_v) / plan.scale_v,
    )


def _validate_flux_config(config, flux_element):
    try:
        port = config["elements"][flux_element]["singleInput"]["port"]
        if len(port) != 2:
            raise ValueError("this adapter requires an OPX controller/port pair")
        controller, channel = port
        output = config["controllers"][controller]["analog_outputs"][channel]
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError("flux element must address a configured singleInput analog output") from exc
    taps = output.get("filter") or {}
    if not isinstance(taps, dict):
        raise ValueError("the OPX analog output filter entry must be a mapping of tap lists")
    populated = {name: list(value) for name, value in taps.items() if value}
    if populated:
        raise ValueError(
            f"software predistortion requires an empty OPX output filter on the flux port, but "
            f"the addressed analog output declares {populated}")


def emit(plan, flux_element, *, config, sync_elements, qua=None):
    if not isinstance(plan, QUAPlan):
        raise ValueError("emit requires a plan from compile_command")
    if not isinstance(flux_element, str) or not flux_element:
        raise ValueError("flux_element must be a nonempty element name")
    if isinstance(sync_elements, str):
        raise ValueError("sync_elements must be a sequence of drive/readout element names")
    elements = tuple(dict.fromkeys((flux_element,) + tuple(sync_elements)))
    if len(elements) < 2 or any(not isinstance(element, str) or not element for element in elements):
        raise ValueError("sync_elements must include drive/readout elements")
    _validate_flux_config(config, flux_element)
    if qua is None:
        from qm import qua
    qua.align(*elements)
    for index, voltage in enumerate(plan.commands_v):
        qua.set_dc_offset(flux_element, "single", voltage)
        qua.wait(int(plan.edges_clk[index + 1] - plan.edges_clk[index]), flux_element)
