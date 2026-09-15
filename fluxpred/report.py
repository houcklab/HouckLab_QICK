import numpy as np

from .core import Command, compare_commands
from .offline import common_horizon
from .schema import sha256_json
from .validation import build_shot, shot_schedule
from . import qick as qick_backend
from . import qua as qua_backend


def transitions(command, *, min_jump=0.0):
    values = np.asarray(command.values, dtype=float)
    edges = np.asarray(command.edges_ns, dtype=float)
    jumps = np.diff(values)
    changed = np.nonzero(np.abs(jumps) > float(min_jump))[0] + 1
    return edges[changed], jumps[changed - 1]


def transition_report(a, b, *, tolerance_ns, min_jump=0.0):
    times_a, jumps_a = transitions(a, min_jump=min_jump)
    times_b, jumps_b = transitions(b, min_jump=min_jump)
    if times_a.size != times_b.size:
        return {"matched": False,
                "reason": f"backends emit a different number of resolvable transitions: "
                          f"{times_a.size} vs {times_b.size}",
                "count_a": int(times_a.size), "count_b": int(times_b.size),
                "min_jump": float(min_jump),
                "max_edge_time_error_ns": None, "max_jump_error": None,
                "within_tolerance": False}
    if times_a.size == 0:
        return {"matched": True, "count_a": 0, "count_b": 0, "min_jump": float(min_jump),
                "max_edge_time_error_ns": 0.0, "max_jump_error": 0.0, "within_tolerance": True}
    edge_error = float(np.max(np.abs(times_a - times_b)))
    jump_error = float(np.max(np.abs(jumps_a - jumps_b)))
    return {"matched": True, "count_a": int(times_a.size), "count_b": int(times_b.size),
            "min_jump": float(min_jump),
            "max_edge_time_error_ns": edge_error, "max_jump_error": jump_error,
            "within_tolerance": bool(edge_error <= float(tolerance_ns))}


def command_hash(command):
    return sha256_json({"edges_ns": [float(value) for value in command.edges_ns],
                        "values": [float(value) for value in command.values]})


def condition_bank(model, *, amplitude, holds_ns, recovery_ns, initial_state=None,
                   tail_tolerance=1e-5, terminal_park_ns=4000, sample_ns=None,
                   schedule_first_ns=None, schedule_growth=1.35, schedule_max_ns=None,
                   schedule_quantum_ns=None):
    bank = []
    for hold_ns in holds_ns:
        schedule = None
        if schedule_first_ns is not None:
            schedule = shot_schedule(
                amplitude=amplitude, hold_ns=float(hold_ns), recovery_ns=float(recovery_ns),
                first_ns=schedule_first_ns, growth=schedule_growth, max_ns=schedule_max_ns,
                quantum_ns=schedule_quantum_ns)
        shot = build_shot(model, amplitude=amplitude, hold_ns=float(hold_ns),
                          recovery_ns=float(recovery_ns), initial_state=initial_state,
                          tail_tolerance=tail_tolerance, terminal_park_ns=terminal_park_ns,
                          sample_ns=sample_ns, schedule=schedule)
        bank.append({"hold_ns": float(hold_ns), "command": shot["command"],
                     "terminal_tail_bound": shot["terminal_tail_bound"],
                     "state_at_truncation": shot["state_at_truncation"]})
    return bank


def cross_backend_report(bank, *, qua_park_v, qua_scale_v, qick_park_gain, qick_scale_gain,
                         qick_clock_ns, qua_max_instructions=10000, qick_max_instructions=4096,
                         edge_tolerance_ns=None, significant_jump_fraction=0.01):
    if edge_tolerance_ns is None:
        edge_tolerance_ns = max(4.0, float(qick_clock_ns))
    conditions = []
    worst = {"max_abs": 0.0, "rms": 0.0, "integrated_abs_ns": 0.0,
             "max_edge_time_error_ns": 0.0, "max_jump_error": 0.0}
    all_within = True
    for entry in bank:
        command = entry["command"]
        qua_plan = qua_backend.compile_command(
            command, park_v=qua_park_v, scale_v=qua_scale_v, max_instructions=qua_max_instructions)
        qick_plan = qick_backend.compile_command(
            command, park_gain=qick_park_gain, scale_gain=qick_scale_gain,
            clock_ns=qick_clock_ns, max_instructions=qick_max_instructions)
        qua_command = qua_backend.reconstruct_command(qua_plan)
        qick_command = qick_backend.reconstruct_command(qick_plan)
        terminal_tolerance = max(float(qua_plan.voltage_quantum_v / abs(qua_scale_v)),
                                 1.0 / abs(float(qick_scale_gain)))

        aligned_qua, aligned_qick = common_horizon(
            qua_command, qick_command, terminal_tolerance=terminal_tolerance)
        difference = compare_commands(aligned_qua, aligned_qick)
        qua_lsb = float(qua_plan.voltage_quantum_v / abs(qua_scale_v))
        qick_lsb = 1.0 / abs(float(qick_scale_gain))
        amplitude = float(np.max(np.abs(np.diff(np.r_[0.0, command.values]))))
        min_jump = max(2.0 * max(qua_lsb, qick_lsb),
                       float(significant_jump_fraction) * amplitude)
        edges = transition_report(qua_command, qick_command, tolerance_ns=edge_tolerance_ns,
                                  min_jump=min_jump)
        within = bool(edges["within_tolerance"])
        all_within = all_within and within
        conditions.append({
            "hold_ns": entry["hold_ns"],
            "requested_command_sha256": command_hash(command),
            "qua_command_sha256": command_hash(qua_command),
            "qick_command_sha256": command_hash(qick_command),
            "qua_segments": len(qua_plan.commands_v),
            "qick_segments": len(qick_plan.segments),
            "qua_instruction_estimate": int(qua_plan.instruction_estimate),
            "qick_instruction_estimate": int(qick_plan.instruction_estimate),
            "qua_max_timing_error_ns": float(qua_plan.max_timing_error_ns),
            "qua_max_voltage_error_v": float(qua_plan.max_voltage_error_v),
            "normalized_lsb": {"qua": float(qua_plan.voltage_quantum_v / abs(qua_scale_v)),
                               "qick": 1.0 / abs(float(qick_scale_gain))},
            "terminal_tail_bound": float(entry["terminal_tail_bound"]),
            "terminal_park_quantization": {
                "tolerance": float(terminal_tolerance),
                "qua_residual": float(qua_command.values[-1]),
                "qick_residual": float(qick_command.values[-1])},
            "normalized_difference": difference,
            "transitions": edges,
            "within_edge_tolerance": within,
        })
        worst["max_abs"] = max(worst["max_abs"], difference["max_abs"])
        worst["rms"] = max(worst["rms"], difference["rms"])
        worst["integrated_abs_ns"] = max(worst["integrated_abs_ns"], difference["integrated_abs_ns"])
        if edges["max_edge_time_error_ns"] is not None:
            worst["max_edge_time_error_ns"] = max(worst["max_edge_time_error_ns"],
                                                  edges["max_edge_time_error_ns"])
            worst["max_jump_error"] = max(worst["max_jump_error"], edges["max_jump_error"])
        else:
            worst["unmatched_transition_counts"] = True
    summary = {"schema": "houcklab.fluxpred.equivalence.v1",
               "edge_tolerance_ns": float(edge_tolerance_ns),
               "significant_jump_fraction": float(significant_jump_fraction),
               "conditions": conditions, "worst_case": worst,
               "all_conditions_within_edge_tolerance": bool(all_within),
               "qua_instruction_total": sum(c["qua_instruction_estimate"] for c in conditions),
               "qick_instruction_total": sum(c["qick_instruction_estimate"] for c in conditions)}
    summary["report_sha256"] = sha256_json(
        {key: value for key, value in summary.items() if key != "report_sha256"})
    return summary


def repeated_shot_state(model, *, amplitude, hold_ns, recovery_ns, repeats, sample_ns=None):
    from .core import render

    state = None
    history = []
    for _ in range(int(repeats)):
        _, state = render(model, [(amplitude, float(hold_ns)), (0.0, float(recovery_ns))],
                          initial_state=state, sample_ns=sample_ns)
        history.append(float(np.sum(np.abs(state))))
    return {"tail_bound_per_shot": history,
            "converged": bool(len(history) > 1 and abs(history[-1] - history[-2]) <= 1e-9),
            "final_state": state,
            "max_tail_bound": float(np.max(history)),
            "steady_state_tail_bound": history[-1]}
