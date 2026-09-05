import numpy as np
import pytest

from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.classifier import (
    ClassifierCalibration,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.programs import (
    OPXResetBenchmarkProgram,
    OPXResetT1Program,
    TimingMatchedReferenceProgram,
    allocate_registers,
    emit_benchmark_shot,
    emit_record,
    emit_t1_shot,
    emit_timing_matched_reference_shot,
    reshape_interleaved_readouts,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.records import (
    RECORD_WORDS,
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


class RecordingProgram:
    pulse_registers = ("freq", "phase", "addr", "gain", "mode", "t")

    def __init__(self, reserved=()):
        self.asm = []
        self._reserved = set(reserved)
        self.soccfg = {"gens": [], "readouts": []}

    def regwi(self, page, reg, value, comment=""):
        self.asm.append(("regwi", reg, int(value)))

    def mathi(self, page, dst, src, op, value):
        self.asm.append(("mathi", dst, src, op, int(value)))

    def condj(self, page, left, op, right, label):
        self.asm.append(("condj", left, op, right, label))

    def label(self, label):
        self.asm.append(("label", label))

    def memw(self, page, value_reg, address_reg):
        self.asm.append(("memw", value_reg, address_reg))


def test_register_allocator_returns_ten_distinct_nonreserved_registers():
    prog = RecordingProgram(reserved={0, 1, 2, 3, 13, 14, 15, 31})
    regs = allocate_registers(prog, page=1, reserved=prog._reserved)

    assert set(regs) == {
        "i", "q", "z", "ground", "excited", "attempts", "pi_count",
        "status", "initial_z", "address",
    }
    assert len(set(regs.values())) == 10
    assert not set(regs.values()) & prog._reserved


def test_register_allocator_rejects_insufficient_scratch_space():
    with pytest.raises(ValueError, match="scratch registers"):
        allocate_registers(RecordingProgram(), page=1, reserved=set(range(1, 25)))


def test_emit_record_writes_exactly_eight_words_and_advances_address():
    prog = RecordingProgram()
    regs = {
        "ground": 1,
        "initial_z": 2,
        "attempts": 3,
        "pi_count": 4,
        "status": 5,
        "i": 6,
        "q": 7,
        "z": 8,
        "address": 9,
    }
    emit_record(prog, page=1, regs=regs, preparation=1)

    assert sum(op[0] == "memw" for op in prog.asm) == RECORD_WORDS
    assert sum(op[:4] == ("mathi", 9, 9, "+") for op in prog.asm) == RECORD_WORDS
    assert ("regwi", 1, 1) in prog.asm


def test_benchmark_shot_emits_payload_before_reset_and_verification_after_it():
    prog = RecordingProgram()
    regs = {
        "i": 1,
        "q": 2,
        "z": 3,
        "ground": 4,
        "excited": 5,
        "attempts": 6,
        "pi_count": 7,
        "status": 8,
        "initial_z": 9,
        "address": 10,
    }
    events = []

    def measure_project(calibration, context):
        events.append(("measure", context))

    emit_benchmark_shot(
        prog,
        page=1,
        regs=regs,
        preparation=1,
        reset_scheme="opx",
        payload_calibration=CAL,
        loop_calibration=CAL,
        max_reset_attempts=2,
        park_up=lambda: events.append(("park", "up")),
        park_down=lambda: events.append(("park", "down")),
        prepare_excited=lambda: events.append(("prepare", "excited")),
        measure_project=measure_project,
        measure_verification=lambda: events.append(("measure", "verification")),
        play_pi=lambda: events.append(("pulse", "pi")),
        label_prefix="SHOT",
    )

    assert events[0:3] == [
        ("park", "up"),
        ("prepare", "excited"),
        ("measure", "payload"),
    ]
    assert events[-2:] == [("measure", "verification"), ("park", "down")]
    assert events.index(("measure", "payload")) < events.index(("pulse", "pi"))
    assert events.index(("pulse", "pi")) < events.index(("measure", "verification"))


def test_no_reset_still_uses_payload_and_independent_verification_readouts():
    prog = RecordingProgram()
    regs = {name: index + 1 for index, name in enumerate((
        "i", "q", "z", "ground", "excited", "attempts", "pi_count",
        "status", "initial_z", "address",
    ))}
    events = []
    emit_benchmark_shot(
        prog,
        page=1,
        regs=regs,
        preparation=0,
        reset_scheme="none",
        payload_calibration=CAL,
        loop_calibration=CAL,
        max_reset_attempts=8,
        park_up=lambda: events.append("up"),
        park_down=lambda: events.append("down"),
        prepare_excited=lambda: events.append("prep"),
        measure_project=lambda calibration, context: events.append(context),
        measure_verification=lambda: events.append("verification"),
        play_pi=lambda: events.append("pi"),
        label_prefix="NONE",
    )

    assert events == ["up", "payload", "verification", "down"]


def test_benchmark_shot_dispatches_unbounded_reset_before_verification():
    prog = RecordingProgram()
    regs = {name: index + 1 for index, name in enumerate((
        "i", "q", "z", "ground", "excited", "attempts", "pi_count",
        "status", "initial_z", "address",
    ))}
    events = []

    emit_benchmark_shot(
        prog,
        page=1,
        regs=regs,
        preparation=1,
        reset_scheme="opx_unbounded",
        payload_calibration=CAL,
        loop_calibration=CAL,
        max_reset_attempts=1,
        park_up=lambda: events.append("up"),
        park_down=lambda: events.append("down"),
        prepare_excited=lambda: events.append("prep"),
        measure_project=lambda calibration, context: events.append(context),
        measure_verification=lambda: events.append("verification"),
        play_pi=lambda: events.append("pi"),
        label_prefix="UNBOUNDED",
    )

    assert events[:3] == ["up", "prep", "payload"]
    assert events[-2:] == ["verification", "down"]
    assert "loop" in events
    assert "pi" in events


def test_t1_shot_uses_payload_as_the_unbounded_reset_decision():
    prog = RecordingProgram()
    regs = {name: index + 1 for index, name in enumerate((
        "i", "q", "z", "ground", "excited", "attempts", "pi_count",
        "status", "initial_z", "address",
    ))}
    events = []

    emit_t1_shot(
        prog,
        page=1,
        regs=regs,
        reset_scheme="opx_unbounded",
        payload_calibration=CAL,
        loop_calibration=CAL,
        park_up=lambda: events.append("up"),
        park_down=lambda: events.append("down"),
        prepare_excited=lambda: events.append("prep"),
        wait_payload=lambda: events.append("wait"),
        measure_project=lambda calibration, context: events.append(context),
        play_pi=lambda: events.append("reset_pi"),
        label_prefix="T1_UNBOUNDED",
    )

    assert events[:4] == ["up", "prep", "wait", "payload"]
    assert events[-1] == "down"
    assert "loop" in events
    assert "reset_pi" in events
    assert sum(op[0] == "memw" for op in prog.asm) == RECORD_WORDS


def test_t1_shot_passive_path_has_no_feedback_measurement_or_reset_pi():
    prog = RecordingProgram()
    regs = {name: index + 1 for index, name in enumerate((
        "i", "q", "z", "ground", "excited", "attempts", "pi_count",
        "status", "initial_z", "address",
    ))}
    events = []

    emit_t1_shot(
        prog,
        page=1,
        regs=regs,
        reset_scheme="none",
        payload_calibration=CAL,
        loop_calibration=CAL,
        park_up=lambda: events.append("up"),
        park_down=lambda: events.append("down"),
        prepare_excited=lambda: events.append("prep"),
        wait_payload=lambda: events.append("wait"),
        measure_project=lambda calibration, context: events.append(context),
        play_pi=lambda: events.append("reset_pi"),
        label_prefix="T1_PASSIVE",
    )

    assert events == ["up", "prep", "wait", "payload", "down"]
    assert ("regwi", regs["status"], 2) in prog.asm
    writes = [op for op in prog.asm if op[0] == "memw"]
    assert len(writes) == RECORD_WORDS
    assert writes[0][1] == regs["i"]
    assert writes[1][1] == regs["q"]


def test_t1_shot_can_measure_a_no_pi_reference():
    prog = RecordingProgram()
    regs = {name: index + 1 for index, name in enumerate((
        "i", "q", "z", "ground", "excited", "attempts", "pi_count",
        "status", "initial_z", "address",
    ))}
    events = []

    emit_t1_shot(
        prog,
        page=1,
        regs=regs,
        reset_scheme="none",
        payload_calibration=CAL,
        loop_calibration=CAL,
        park_up=lambda: events.append("up"),
        park_down=lambda: events.append("down"),
        prepare_excited=lambda: events.append("prep"),
        wait_payload=lambda: events.append("wait"),
        measure_project=lambda calibration, context: events.append(context),
        play_pi=lambda: events.append("reset_pi"),
        label_prefix="T1_P0",
        do_prepare=False,
    )

    assert events == ["up", "wait", "payload", "down"]


def test_loop_reference_matches_the_runtime_feedback_timing():
    events = []

    emit_timing_matched_reference_shot(
        context="loop",
        prep_excited=True,
        measure=lambda: events.append("measure"),
        prepare_excited=lambda: events.append("pi"),
        wait_read_delay=lambda: events.append("read_delay"),
        wait_feedback_delay=lambda: events.append("feedback_delay"),
        wait_reset_settle=lambda: events.append("reset_settle"),
        wait_payload_alignment=lambda: events.append("payload_alignment"),
    )

    assert events == [
        "measure",
        "read_delay",
        "feedback_delay",
        "pi",
        "reset_settle",
        "measure",
    ]


def test_payload_reference_keeps_the_existing_preparation_sequence():
    events = []

    emit_timing_matched_reference_shot(
        context="payload",
        prep_excited=True,
        measure=lambda: events.append("measure"),
        prepare_excited=lambda: events.append("pi"),
        wait_read_delay=lambda: events.append("read_delay"),
        wait_feedback_delay=lambda: events.append("feedback_delay"),
        wait_reset_settle=lambda: events.append("reset_settle"),
        wait_payload_alignment=lambda: events.append("payload_alignment"),
    )

    assert events == ["pi", "payload_alignment", "measure"]


def test_readout_pair_extraction_preserves_per_shot_trigger_order():
    i_values = np.asarray([10, 11, 20, 21, 30, 31], dtype=np.int64)
    q_values = np.asarray([-10, -11, -20, -21, -30, -31], dtype=np.int64)

    i_reads, q_reads = reshape_interleaved_readouts(
        i_values,
        q_values,
        reps=3,
        readouts_per_rep=2,
    )

    assert i_reads.tolist() == [[10, 11], [20, 21], [30, 31]]
    assert q_reads.tolist() == [[-10, -11], [-20, -21], [-30, -31]]


def test_qick_program_classes_are_exposed_even_on_analysis_computers():
    assert TimingMatchedReferenceProgram is not None
    assert OPXResetBenchmarkProgram is not None
    assert OPXResetT1Program is not None
