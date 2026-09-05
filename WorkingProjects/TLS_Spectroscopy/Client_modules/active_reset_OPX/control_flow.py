from dataclasses import dataclass

from .classifier import Zone, classify
from .config import MAX_RESET_ATTEMPTS
from .records import TerminalStatus


@dataclass(frozen=True)
class ResetOutcome:
    terminal_status: TerminalStatus
    reset_attempts: int
    pi_pulses: int
    last_z: int
    zones: tuple


def simulate_reset(decisions, payload_calibration, loop_calibration, *, max_reset_attempts=8):
    """Execute the OPX reset semantics on a supplied sequence of decisions.

    ``decisions[0]`` is the payload measurement.  Every later value is the
    remeasurement produced by one corrective attempt.
    """
    max_attempts = int(max_reset_attempts)
    if not 1 <= max_attempts <= MAX_RESET_ATTEMPTS:
        raise ValueError(
            f"max_reset_attempts must be in the range 1..{MAX_RESET_ATTEMPTS}"
        )
    decisions = [int(value) for value in decisions]
    if not decisions:
        raise ValueError("at least the payload decision is required")

    attempts = 0
    pi_pulses = 0
    value = decisions[0]
    calibration = payload_calibration
    zones = []
    for _ in range(max_attempts):
        zone = classify(value, calibration)
        zones.append(zone)
        if zone is Zone.GROUND:
            return ResetOutcome(
                TerminalStatus.CONFIRMED_GROUND, attempts, pi_pulses, value, tuple(zones)
            )
        if zone is Zone.EXCITED:
            pi_pulses += 1
        attempts += 1
        if len(decisions) <= attempts:
            raise ValueError(
                f"decision sequence ended before remeasurement {attempts}"
            )
        value = decisions[attempts]
        calibration = loop_calibration

    final_zone = classify(value, loop_calibration)
    zones.append(final_zone)
    status = (
        TerminalStatus.CONFIRMED_GROUND
        if final_zone is Zone.GROUND
        else TerminalStatus.MAX_ITERATIONS_REACHED
    )
    return ResetOutcome(status, attempts, pi_pulses, value, tuple(zones))


def _comparison_ops(excited_above):
    if bool(excited_above):
        return "<=", "<="
    return ">=", ">="


def _write_thresholds(prog, page, regs, calibration, comment_prefix):
    thresholds = calibration.assembly_thresholds()
    prog.regwi(page, regs["ground"], int(thresholds["ground"]),
               f"{comment_prefix} ground threshold")
    prog.regwi(page, regs["excited"], int(thresholds["excited"]),
               f"{comment_prefix} excited threshold")


def emit_reset_state_machine(
    prog,
    *,
    page,
    regs,
    payload_calibration,
    loop_calibration,
    max_reset_attempts,
    measure_next,
    play_pi,
    label_prefix,
):
    """Emit a bounded, early-exit tProc-v1 reset branch graph.

    The caller must place the payload decision value in ``regs['z']`` first.
    ``measure_next`` must issue one reset readout and replace that register with
    the loop-context projected result.  The emitted graph executes zero to the
    configured number of callbacks even though all paths exist in program memory.
    """
    max_attempts = int(max_reset_attempts)
    if not 1 <= max_attempts <= MAX_RESET_ATTEMPTS:
        raise ValueError(
            f"max_reset_attempts must be in the range 1..{MAX_RESET_ATTEMPTS}"
        )
    required = {"z", "ground", "excited", "attempts", "pi_count", "status"}
    missing = sorted(required - set(regs))
    if missing:
        raise ValueError(f"missing reset registers: {missing}")
    selected = {name: int(regs[name]) for name in required}
    if len(set(selected.values())) != len(selected):
        raise ValueError(f"reset registers must be distinct: {selected}")

    ground_label = f"{label_prefix}_GROUND"
    terminal_label = f"{label_prefix}_TERMINAL"
    prog.regwi(page, regs["attempts"], 0, "OPX reset attempts")
    prog.regwi(page, regs["pi_count"], 0, "OPX reset pi count")
    _write_thresholds(prog, page, regs, payload_calibration, "payload")

    calibration = payload_calibration
    for attempt in range(max_attempts):
        ground_op, no_pi_op = _comparison_ops(
            calibration.assembly_plan()["excited_above"]
        )
        no_pi_label = f"{label_prefix}_NO_PI_{attempt}"
        prog.condj(page, regs["z"], ground_op, regs["ground"], ground_label)
        prog.condj(page, regs["z"], no_pi_op, regs["excited"], no_pi_label)
        play_pi()
        prog.mathi(page, regs["pi_count"], regs["pi_count"], "+", 1)
        prog.label(no_pi_label)
        prog.mathi(page, regs["attempts"], regs["attempts"], "+", 1)
        measure_next()
        if attempt == 0:
            _write_thresholds(prog, page, regs, loop_calibration, "loop")
        calibration = loop_calibration

    ground_op, _ = _comparison_ops(loop_calibration.assembly_plan()["excited_above"])
    prog.condj(page, regs["z"], ground_op, regs["ground"], ground_label)
    prog.regwi(
        page,
        regs["status"],
        int(TerminalStatus.MAX_ITERATIONS_REACHED),
        "OPX reset reached safety ceiling",
    )
    prog.condj(page, regs["status"], "==", regs["status"], terminal_label)
    prog.label(ground_label)
    prog.regwi(
        page,
        regs["status"],
        int(TerminalStatus.CONFIRMED_GROUND),
        "OPX reset confirmed ground",
    )
    prog.label(terminal_label)
