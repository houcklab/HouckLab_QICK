from dataclasses import replace

import pytest

from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.classifier import (
    ClassifierCalibration,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.control_flow import (
    emit_reset_state_machine,
    simulate_reset,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.records import (
    TerminalStatus,
)


CAL = ClassifierCalibration(
    schema_version=1,
    context="payload",
    theta_rad=0.0,
    shift=0,
    c_int=1,
    s_int=0,
    ground_threshold=-10,
    excited_threshold=10,
    max_abs_raw=100,
    holdout={},
)


def test_model_exits_on_payload_ground_without_a_corrective_attempt():
    result = simulate_reset([-11], CAL, CAL, max_reset_attempts=8)

    assert result.terminal_status is TerminalStatus.CONFIRMED_GROUND
    assert result.reset_attempts == 0
    assert result.pi_pulses == 0


def test_model_remeasures_ambiguous_without_firing_pi():
    result = simulate_reset([0, -11], CAL, CAL, max_reset_attempts=8)

    assert result.terminal_status is TerminalStatus.CONFIRMED_GROUND
    assert result.reset_attempts == 1
    assert result.pi_pulses == 0


def test_model_fires_pi_only_for_confident_excited_decisions():
    result = simulate_reset([11, 0, -11], CAL, CAL, max_reset_attempts=8)

    assert result.reset_attempts == 2
    assert result.pi_pulses == 1


def test_model_evaluates_the_eighth_remeasurement_before_timeout():
    result = simulate_reset([0] * 8 + [-11], CAL, CAL, max_reset_attempts=8)

    assert result.terminal_status is TerminalStatus.CONFIRMED_GROUND
    assert result.reset_attempts == 8
    assert result.pi_pulses == 0


def test_model_cannot_execute_a_ninth_corrective_attempt():
    result = simulate_reset([11] * 10, CAL, CAL, max_reset_attempts=8)

    assert result.terminal_status is TerminalStatus.MAX_ITERATIONS_REACHED
    assert result.reset_attempts == 8
    assert result.pi_pulses == 8


class RecordingProgram:
    def __init__(self):
        self.asm = []

    def regwi(self, page, reg, value, comment=""):
        self.asm.append(("regwi", reg, int(value)))

    def mathi(self, page, dst, src, op, value):
        self.asm.append(("mathi", dst, src, op, int(value)))

    def condj(self, page, left, op, right, label):
        self.asm.append(("condj", left, op, right, label))

    def label(self, label):
        self.asm.append(("label", label))


REGS = {
    "z": 1,
    "ground": 2,
    "excited": 3,
    "attempts": 4,
    "pi_count": 5,
    "status": 6,
}


def _build(max_attempts=8, calibration=CAL):
    prog = RecordingProgram()

    def measure_next():
        prog.asm.append(("measure_next", REGS["z"]))

    def play_pi():
        prog.asm.append(("pulse",))

    emit_reset_state_machine(
        prog,
        page=0,
        regs=REGS,
        payload_calibration=calibration,
        loop_calibration=calibration,
        max_reset_attempts=max_attempts,
        measure_next=measure_next,
        play_pi=play_pi,
        label_prefix="TEST",
    )
    return prog.asm


def _interpret(asm, decisions):
    labels = {op[1]: idx for idx, op in enumerate(asm) if op[0] == "label"}
    regs = {REGS["z"]: int(decisions[0])}
    read_index = 1
    pulses = measures = 0
    comparisons = {
        "<": lambda a, b: a < b,
        "<=": lambda a, b: a <= b,
        ">": lambda a, b: a > b,
        ">=": lambda a, b: a >= b,
        "==": lambda a, b: a == b,
    }
    pc = 0
    while pc < len(asm):
        op = asm[pc]
        if op[0] == "regwi":
            regs[op[1]] = op[2]
        elif op[0] == "mathi":
            assert op[3] == "+"
            regs[op[1]] = regs.get(op[2], 0) + op[4]
        elif op[0] == "condj" and comparisons[op[2]](
            regs.get(op[1], 0), regs.get(op[3], 0)
        ):
            pc = labels[op[4]]
            continue
        elif op[0] == "pulse":
            pulses += 1
        elif op[0] == "measure_next":
            measures += 1
            regs[op[1]] = int(decisions[min(read_index, len(decisions) - 1)])
            read_index += 1
        pc += 1
        assert pc < 10000
    return {
        "attempts": regs[REGS["attempts"]],
        "pi_pulses": regs[REGS["pi_count"]],
        "status": TerminalStatus(regs[REGS["status"]]),
        "measures": measures,
        "pulses": pulses,
    }


@pytest.mark.parametrize(
    "decisions, expected",
    [
        ([-11], (0, 0, TerminalStatus.CONFIRMED_GROUND)),
        ([0, -11], (1, 0, TerminalStatus.CONFIRMED_GROUND)),
        ([11, -11], (1, 1, TerminalStatus.CONFIRMED_GROUND)),
        ([11, 0, -11], (2, 1, TerminalStatus.CONFIRMED_GROUND)),
    ],
)
def test_emitter_executes_the_same_early_exit_paths_as_the_model(decisions, expected):
    observed = _interpret(_build(), decisions)
    model = simulate_reset(decisions, CAL, CAL, max_reset_attempts=8)

    assert (observed["attempts"], observed["pi_pulses"], observed["status"]) == expected
    assert observed["measures"] == model.reset_attempts
    assert observed["pulses"] == model.pi_pulses


def test_emitter_evaluates_final_readout_and_never_executes_attempt_nine():
    success = _interpret(_build(), [0] * 8 + [-11])
    timeout = _interpret(_build(), [11] * 10)

    assert success == {
        "attempts": 8,
        "pi_pulses": 0,
        "status": TerminalStatus.CONFIRMED_GROUND,
        "measures": 8,
        "pulses": 0,
    }
    assert timeout["attempts"] == timeout["measures"] == timeout["pulses"] == 8
    assert timeout["status"] is TerminalStatus.MAX_ITERATIONS_REACHED


def test_emitter_handles_the_reversed_assembly_orientation():
    reversed_cal = replace(CAL, c_int=-1, ground_threshold=-10, excited_threshold=10)
    # Canonical z is -raw; assembly acc is raw.  Therefore ground is acc >= +10
    # and excited is acc < -10.
    observed = _interpret(_build(calibration=reversed_cal), [11])

    assert observed["status"] is TerminalStatus.CONFIRMED_GROUND
    assert observed["attempts"] == 0
