from types import SimpleNamespace

import numpy as np
import pytest

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import programs
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.classifier import (
    ClassifierCalibration,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.programs import (
    OPXResetBenchmarkProgram,
    OPXResetPulseGridProgram,
    OPXResetTLSMemoryProgram,
    OPXResetPulseSweepProgram,
    OPXResetT13PointProgram,
    OPXResetT1Program,
    OPXResetT1FluxSweepProgram,
    OPXResetT1SweepProgram,
    TimingMatchedReferenceDMemProgram,
    TimingMatchedReferenceProgram,
    allocate_named_registers,
    allocate_registers,
    emit_benchmark_shot,
    emit_payload_reset_shot,
    emit_record,
    emit_tls_memory_sequence,
    emit_t1_shot,
    emit_timing_matched_reference_shot,
    emit_shot_major_payload_loops,
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

    def safe_regwi(self, page, reg, value):
        self.asm.append(("safe_regwi", reg, int(value)))

    def mathi(self, page, dst, src, op, value):
        self.asm.append(("mathi", dst, src, op, int(value)))

    def condj(self, page, left, op, right, label):
        self.asm.append(("condj", left, op, right, label))

    def label(self, label):
        self.asm.append(("label", label))

    def memw(self, page, value_reg, address_reg):
        self.asm.append(("memw", value_reg, address_reg))

    def memwi(self, page, value_reg, address):
        self.asm.append(("memwi", value_reg, address))

    def loopnz(self, page, register, label):
        self.asm.append(("loopnz", register, label))


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


def test_named_register_allocator_can_leave_room_for_payload_state():
    names = ("i", "q", "z", "ground", "excited", "attempts", "pi_count",
             "status", "address")
    prog = RecordingProgram(reserved={0, 1, 2, 3, 13, 14, 15, 31})

    regs = allocate_named_registers(
        prog, page=1, names=names, reserved=prog._reserved)

    assert tuple(regs) == names
    assert len(set(regs.values())) == len(names)
    assert not set(regs.values()) & prog._reserved


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


def test_payload_hardware_loop_visits_all_points_inside_each_shot():
    prog = RecordingProgram()
    emit_shot_major_payload_loops(
        prog,
        page=0,
        shot_register=10,
        point_register=11,
        done_register=12,
        done_address=1,
        shots=3,
        points=4,
        initialize_point=lambda: prog.asm.append(("initialize_point",)),
        emit_point=lambda: prog.asm.append(("emit_point",)),
        advance_point=lambda: prog.asm.append(("advance_point",)),
        shot_label="SHOT",
        point_label="POINT",
    )

    labels = [entry for entry in prog.asm if entry[0] == "label"]
    loops = [entry for entry in prog.asm if entry[0] == "loopnz"]
    assert labels == [("label", "SHOT"), ("label", "POINT")]
    assert loops == [("loopnz", 11, "POINT"), ("loopnz", 10, "SHOT")]
    assert prog.asm.index(("initialize_point",)) < prog.asm.index(("label", "POINT"))


def test_hard_flux_step_latches_the_requested_dac_value():
    prog = RecordingProgram()
    prog.cfg = {"ff_ch": 3}
    prog.set_pulse_registers = lambda **values: prog.asm.append(("set", values))
    prog.pulse = lambda ch: prog.asm.append(("pulse", ch))

    ff_pulse.play_hard_step(prog, -25790)

    assert prog.asm == [
        ("set", {
            "ch": 3,
            "freq": 0,
            "style": "const",
            "phase": 0,
            "stdysel": "last",
            "gain": -25790,
            "length": 3,
        }),
        ("pulse", 3),
    ]


def test_reference_flux_cycle_reestablishes_park_before_state_preparation():
    assert hasattr(programs, "emit_reference_flux_cycle")
    events = []

    programs.emit_reference_flux_cycle(
        enabled=True,
        play_excursion=lambda: events.append("excursion"),
        wait_hold=lambda: events.append("hold"),
        play_park=lambda: events.append("park"),
        wait_settle=lambda: events.append("settle"),
    )
    events.append("prepare")

    assert events == ["excursion", "hold", "park", "settle", "prepare"]


def test_reference_flux_cycle_is_inert_when_not_requested():
    assert hasattr(programs, "emit_reference_flux_cycle")
    events = []

    programs.emit_reference_flux_cycle(
        enabled=False,
        play_excursion=lambda: events.append("excursion"),
        wait_hold=lambda: events.append("hold"),
        play_park=lambda: events.append("park"),
        wait_settle=lambda: events.append("settle"),
    )

    assert events == []


def test_dmem_reference_runs_requested_flux_cycle_before_measurement():
    events = []
    prog = object.__new__(TimingMatchedReferenceDMemProgram)
    prog.cfg = {
        "ff_ch": 3,
        "ff_gain": -20000,
        "ff_park_gain": -25790,
        "flux_settle_time_us": 0.5,
        "opx_reference_context": "payload",
        "opx_reference_flux_cycle": True,
        "opx_reference_flux_hold_us": 1.0,
        "opx_reference_park_recovery_us": 10.0,
        "prep_excited": False,
    }
    prog.reset_config = SimpleNamespace(
        persistent_park=True,
        hard_flux_steps=True,
        inter_shot_delay_us=10.0,
    )
    prog.reset_page = 1
    prog.reset_regs = {"i": 2, "q": 3, "address": 4}
    prog.set_pulse_registers = lambda **values: events.append(("set", values["gain"]))
    prog.pulse = lambda ch: events.append(("pulse", ch))
    prog.sync_all = lambda cycles: events.append(("wait", cycles))
    prog.us2cycles = lambda microseconds: float(microseconds)
    prog._measure_raw = lambda: events.append(("measure",))
    prog.memw = lambda *args: None
    prog.mathi = lambda *args: None

    prog._emit_reference()

    assert events[:7] == [
        ("set", -20000),
        ("pulse", 3),
        ("wait", 1.0),
        ("set", -25790),
        ("pulse", 3),
        ("wait", 10.0),
        ("measure",),
    ]


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


def test_t1_shot_prepares_independent_reset_pulse_after_payload_measurement():
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
        prepare_excited=lambda: events.append("payload_pi"),
        wait_payload=lambda: events.append("wait"),
        measure_project=lambda calibration, context: events.append(context),
        prepare_reset=lambda: events.append("prepare_reset"),
        play_pi=lambda: events.append("reset_pi"),
        label_prefix="T1_SEPARATE_PULSES",
    )

    assert events.index("payload") < events.index("prepare_reset")
    assert events.index("prepare_reset") < events.index("reset_pi")


def test_t1_program_keeps_payload_and_reset_frequencies_independent():
    prog = RecordingProgram()
    prog.cfg = {
        "qubit_ch": 1,
        "qubit_freq": 4361.0,
        "qubit_pi_freq": 4361.0,
        "qubit_pi_gain": 11100,
        "reset_pi_freq": 4367.25,
        "reset_pi_gain": 10900,
    }
    prog.freq2reg = lambda value, gen_ch: int(round(float(value) * 100.0))
    prog.deg2reg = lambda value, gen_ch: int(round(float(value)))
    prog.set_pulse_registers = lambda **values: prog.asm.append(
        ("set_pulse_registers", values)
    )

    OPXResetT1Program._set_payload_pulse(prog)
    OPXResetT1Program._set_reset_pulse(prog)

    payload = prog.asm[0][1]
    reset = prog.asm[1][1]
    assert payload["freq"] == 436100
    assert payload["gain"] == 11100
    assert payload["waveform"] == "qubit"
    assert reset["freq"] == 436725
    assert reset["gain"] == 10900
    assert reset["waveform"] == "qubit_reset"


def test_t1_hard_flux_cycle_has_no_four_microsecond_ramp():
    prog = RecordingProgram()
    prog.cfg = {
        "ff_ch": 3,
        "ff_gain": -20000,
        "ff_park_gain": -25790,
    }
    prog.reset_config = type("ResetConfig", (), {"hard_flux_steps": True})()
    prog._t1_stepping = True
    prog._t1_ff_settle_us = 0.5
    prog._t1_hold_us = 70.0
    prog.set_pulse_registers = lambda **values: prog.asm.append(("set", values))
    prog.pulse = lambda ch: prog.asm.append(("pulse", ch))
    prog.us2cycles = lambda value: int(round(float(value) * 100))
    prog.sync_all = lambda cycles: prog.asm.append(("sync", cycles))

    OPXResetT1Program._wait_t1_payload(prog, 12.5)

    gains = [entry[1]["gain"] for entry in prog.asm if entry[0] == "set"]
    waits = [entry[1] for entry in prog.asm if entry[0] == "sync"]
    assert gains == [-20000, -25790]
    assert waits == [50, 1250, 50]
    assert 400 not in waits


def test_three_point_dynamic_flux_target_comes_from_dc_loop_register():
    prog = RecordingProgram()
    prog.cfg = {"ff_ch": 3}
    prog._t1_3pt_ff_page = 1
    prog._t1_3pt_regs = {"dc_gain": 9}
    prog.sreg = lambda channel, name: 11
    prog.pulse = lambda ch: prog.asm.append(("pulse", ch))

    OPXResetT13PointProgram._play_dynamic_target(prog)

    assert prog.asm == [
        ("mathi", 11, 9, "+", 0),
        ("pulse", 3),
    ]


def test_three_point_flux_cycle_returns_to_park_after_requested_wait(monkeypatch):
    prog = RecordingProgram()
    prog.cfg = {"ff_ch": 3, "ff_park_gain": -25790}
    prog._t1_ff_settle_us = 0.5
    prog.us2cycles = lambda value: int(round(float(value) * 100))
    prog.sync_all = lambda cycles: prog.asm.append(("sync", cycles))
    prog._play_dynamic_target = lambda: prog.asm.append(("target",))
    monkeypatch.setattr(
        ff_pulse,
        "play_hard_step",
        lambda program, gain: program.asm.append(("park", int(gain))),
    )

    OPXResetT13PointProgram._wait_three_point_payload(prog, 70.0, True)

    assert prog.asm == [
        ("target",),
        ("sync", 50),
        ("sync", 7000),
        ("park", -25790),
        ("sync", 50),
    ]


@pytest.mark.parametrize(
    ("sequence", "expected"),
    (
        ("single", ["prepare", "excursion", "storage", "idle"]),
        ("double", ["prepare", "excursion", "storage", "excursion"]),
        ("ground_double", ["excursion", "storage", "excursion"]),
    ),
)
def test_tls_memory_sequence_preserves_signed_probe_timing(sequence, expected):
    events = []

    emit_tls_memory_sequence(
        sequence=sequence,
        prepare_excited=lambda: events.append("prepare"),
        play_excursion=lambda: events.append("excursion"),
        wait_storage=lambda: events.append("storage"),
        idle_excursion=lambda: events.append("idle"),
    )

    assert events == expected


def test_tls_memory_warmup_preserves_flux_timing_without_exciting_qubit():
    events = []

    emit_tls_memory_sequence(
        sequence="single",
        prepare_excited=lambda: events.append("prepare"),
        play_excursion=lambda: events.append("excursion"),
        wait_storage=lambda: events.append("storage"),
        idle_excursion=lambda: events.append("idle"),
        do_prepare=False,
    )

    assert events == ["excursion", "storage", "idle"]


def test_tls_memory_program_requires_hard_flux_steps():
    prog = RecordingProgram()
    prog.cfg = {
        "qubit_ch": 1,
        "ff_ch": 3,
        "opx_memory_shots": 1,
        "opx_memory_sequences": ["single"],
    }
    prog.reset_config = SimpleNamespace(hard_flux_steps=False)
    prog._declare_experiment = lambda: None
    prog.ch_page = lambda channel: 1

    with pytest.raises(ValueError, match="hard flux steps"):
        OPXResetTLSMemoryProgram.make_program(prog)


def test_pulse_sweep_hard_flux_cycle_matches_t1_step_order():
    assert hasattr(programs, "emit_hard_flux_excursion")
    events = []

    programs.emit_hard_flux_excursion(
        play_target=lambda: events.append("target"),
        wait_target_settle=lambda: events.append("target_settle"),
        emit_at_target=lambda: events.append("payload"),
        wait_hold=lambda: events.append("hold"),
        play_park=lambda: events.append("park"),
        wait_park_settle=lambda: events.append("park_settle"),
    )

    assert events == [
        "target",
        "target_settle",
        "payload",
        "hold",
        "park",
        "park_settle",
    ]


def test_park_history_probe_precedes_the_payload_pulse():
    assert hasattr(programs, "emit_park_history_probe")
    events = []

    programs.emit_park_history_probe(
        play_target=lambda: events.append("target"),
        wait_target_settle=lambda: events.append("target_settle"),
        wait_hold=lambda: events.append("hold"),
        play_park=lambda: events.append("park"),
        wait_recovery=lambda: events.append("recovery"),
        emit_payload=lambda: events.append("payload"),
    )

    assert events == [
        "target",
        "target_settle",
        "hold",
        "park",
        "recovery",
        "payload",
    ]


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


def test_t1_shot_diagnostic_hold_keeps_park_up_without_reset_load():
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
        reset_scheme="diagnostic_hold",
        payload_calibration=CAL,
        loop_calibration=CAL,
        park_up=lambda: events.append("up"),
        park_down=lambda: events.append("down"),
        prepare_excited=lambda: events.append("prep"),
        wait_payload=lambda: events.append("wait"),
        measure_project=lambda calibration, context: events.append(context),
        play_pi=lambda: events.append("reset_pi"),
        wait_diagnostic_hold=lambda: events.append("hold"),
        diagnostic_cycles=2,
        label_prefix="T1_HOLD",
    )

    assert events == ["up", "prep", "wait", "payload", "hold", "down"]
    assert ("regwi", regs["attempts"], 0) in prog.asm
    assert ("regwi", regs["pi_count"], 0) in prog.asm


def test_t1_shot_diagnostic_readout_emits_two_readouts_without_pi():
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
        reset_scheme="diagnostic_readout",
        payload_calibration=CAL,
        loop_calibration=CAL,
        park_up=lambda: events.append("up"),
        park_down=lambda: events.append("down"),
        prepare_excited=lambda: events.append("prep"),
        wait_payload=lambda: events.append("wait"),
        measure_project=lambda calibration, context: events.append(context),
        play_pi=lambda: events.append("reset_pi"),
        wait_diagnostic_hold=lambda: events.append("hold"),
        diagnostic_cycles=2,
        label_prefix="T1_READOUT",
    )

    assert events == ["up", "prep", "wait", "payload", "loop", "loop", "down"]
    assert ("regwi", regs["attempts"], 2) in prog.asm
    assert ("regwi", regs["pi_count"], 0) in prog.asm


def test_t1_shot_diagnostic_pi_readout_emits_two_fixed_cycles():
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
        reset_scheme="diagnostic_pi_readout",
        payload_calibration=CAL,
        loop_calibration=CAL,
        park_up=lambda: events.append("up"),
        park_down=lambda: events.append("down"),
        prepare_excited=lambda: events.append("prep"),
        wait_payload=lambda: events.append("wait"),
        measure_project=lambda calibration, context: events.append(context),
        play_pi=lambda: events.append("reset_pi"),
        wait_diagnostic_hold=lambda: events.append("hold"),
        diagnostic_cycles=2,
        label_prefix="T1_PI_READOUT",
    )

    assert events == [
        "up", "prep", "wait", "payload",
        "reset_pi", "loop", "reset_pi", "loop", "down",
    ]
    assert ("regwi", regs["attempts"], 2) in prog.asm
    assert ("regwi", regs["pi_count"], 2) in prog.asm


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


def test_persistent_park_lifecycle_hoists_park_outside_the_shot_body():
    prog = RecordingProgram()
    prog.reset_config = type("ResetConfig", (), {"persistent_park": True})()
    events = []
    prog._park_up = lambda: events.append("up")
    prog._park_down = lambda: events.append("down")

    OPXResetBenchmarkProgram._begin_park_lifecycle(prog)
    park_up, park_down = OPXResetBenchmarkProgram._shot_park_callbacks(prog)
    for shot in (1, 2):
        park_up()
        events.append(f"shot_{shot}")
        park_down()
    OPXResetBenchmarkProgram._end_park_lifecycle(prog)

    assert events == ["up", "shot_1", "shot_2"]


def test_hard_persistent_park_steps_once_and_prerolls_before_all_shots():
    prog = RecordingProgram()
    prog.cfg = {"ff_ch": 3, "ff_park_gain": -25790}
    prog.reset_config = type(
        "ResetConfig",
        (),
        {
            "persistent_park": True,
            "hard_flux_steps": True,
            "park_preroll_us": 400.0,
        },
    )()
    prog.set_pulse_registers = lambda **values: prog.asm.append(("set", values))
    prog.pulse = lambda ch: prog.asm.append(("pulse", ch))
    prog.us2cycles = lambda value: int(round(float(value) * 100))
    prog.sync_all = lambda cycles: prog.asm.append(("sync", cycles))

    OPXResetBenchmarkProgram._begin_park_lifecycle(prog)
    park_up, park_down = OPXResetBenchmarkProgram._shot_park_callbacks(prog)
    park_up()
    park_down()
    OPXResetBenchmarkProgram._end_park_lifecycle(prog)

    gains = [entry[1]["gain"] for entry in prog.asm if entry[0] == "set"]
    assert gains == [-25790]
    assert ("sync", 40000) in prog.asm


def test_per_shot_park_lifecycle_preserves_existing_behavior():
    prog = RecordingProgram()
    prog.reset_config = type("ResetConfig", (), {"persistent_park": False})()
    events = []
    prog._park_up = lambda: events.append("up")
    prog._park_down = lambda: events.append("down")

    OPXResetBenchmarkProgram._begin_park_lifecycle(prog)
    park_up, park_down = OPXResetBenchmarkProgram._shot_park_callbacks(prog)
    for shot in (1, 2):
        park_up()
        events.append(f"shot_{shot}")
        park_down()
    OPXResetBenchmarkProgram._end_park_lifecycle(prog)

    assert events == ["up", "shot_1", "down", "up", "shot_2", "down"]


def test_persistent_park_refresh_cycles_immediately_before_each_shot():
    prog = RecordingProgram()
    prog.reset_config = type(
        "ResetConfig",
        (),
        {"persistent_park": True, "refresh_park_before_shot": True},
    )()
    events = []
    prog._park_up = lambda: events.append("up")
    prog._park_down = lambda: events.append("down")
    prog._refresh_park = lambda: OPXResetBenchmarkProgram._refresh_park(prog)

    OPXResetBenchmarkProgram._begin_park_lifecycle(prog)
    park_up, park_down = OPXResetBenchmarkProgram._shot_park_callbacks(prog)
    for shot in (1, 2):
        park_up()
        events.append(f"shot_{shot}")
        park_down()
    OPXResetBenchmarkProgram._end_park_lifecycle(prog)

    assert events == [
        "up",
        "down", "up", "shot_1",
        "down", "up", "shot_2",
    ]


def test_compact_payload_shot_records_iq_then_resets_and_releases_park():
    prog = RecordingProgram()
    regs = {name: index + 1 for index, name in enumerate((
        "i", "q", "z", "ground", "excited", "attempts", "pi_count",
        "status", "address",
    ))}
    events = []

    emit_payload_reset_shot(
        prog,
        page=1,
        regs=regs,
        payload_calibration=CAL,
        loop_calibration=CAL,
        park_up=lambda: events.append("up"),
        park_down=lambda: events.append("down"),
        emit_payload=lambda: events.append("payload_sequence"),
        measure_project=lambda calibration, context: events.append(context),
        prepare_reset=lambda: events.append("prepare_reset"),
        play_pi=lambda: events.append("reset_pi"),
        label_prefix="PAYLOAD",
    )

    assert events[:3] == ["up", "payload_sequence", "payload"]
    assert events[-1] == "down"
    assert events.index("prepare_reset") < events.index("reset_pi")
    writes = [operation for operation in prog.asm if operation[0] == "memw"]
    assert len(writes) == 2
    assert [operation[1] for operation in writes] == [regs["i"], regs["q"]]


def test_compact_payload_shot_can_use_passive_delay_without_reset():
    prog = RecordingProgram()
    regs = {name: index + 1 for index, name in enumerate((
        "i", "q", "z", "ground", "excited", "attempts", "pi_count",
        "status", "address",
    ))}
    events = []

    emit_payload_reset_shot(
        prog,
        page=1,
        regs=regs,
        reset_scheme="none",
        payload_calibration=CAL,
        loop_calibration=CAL,
        park_up=lambda: events.append("up"),
        park_down=lambda: events.append("down"),
        emit_payload=lambda: events.append("payload_sequence"),
        measure_project=lambda calibration, context: events.append(context),
        prepare_reset=lambda: events.append("prepare_reset"),
        play_pi=lambda: events.append("reset_pi"),
        label_prefix="PAYLOAD_PASSIVE",
    )

    assert events == ["up", "payload_sequence", "payload", "down"]
    writes = [operation for operation in prog.asm if operation[0] == "memw"]
    assert len(writes) == 2


def test_measurement_projection_preserves_raw_q_for_t1_payload_storage():
    prog = RecordingProgram()
    prog.cfg = {}
    prog.reset_page = 1
    prog.reset_regs = {
        "i": 1,
        "q": 2,
        "status": 3,
        "z": 4,
    }
    prog.reset_config = type(
        "ResetConfig",
        (),
        {
            "reset_settle_us": 0.05,
            "feedback_syncdelay_us": 8.0,
            "loop_recovery_us": 10.0,
        },
    )()
    prog._measure_raw = lambda: prog.asm.append(("measure_raw",))
    prog.us2cycles = lambda value: int(round(100 * value))
    prog.sync_all = lambda cycles: prog.asm.append(("sync_all", cycles))
    prog.math = lambda page, dst, left, op, right: prog.asm.append(
        ("math", dst, left, op, right)
    )

    OPXResetBenchmarkProgram._measure_project(prog, CAL, "payload")

    assert ("mathi", 3, 2, "*", 0) in prog.asm
    assert not any(op[0] == "mathi" and op[1] == 2 for op in prog.asm)


def test_loop_measurement_waits_for_qua_resonator_recovery():
    prog = RecordingProgram()
    prog.cfg = {}
    prog.reset_page = 1
    prog.reset_regs = {
        "i": 1,
        "q": 2,
        "status": 3,
        "z": 4,
    }
    prog.reset_config = type(
        "ResetConfig",
        (),
        {
            "reset_settle_us": 0.05,
            "feedback_syncdelay_us": 8.0,
            "loop_recovery_us": 10.0,
        },
    )()
    prog._measure_raw = lambda: prog.asm.append(("measure_raw",))
    prog.us2cycles = lambda value: int(round(100 * value))
    prog.sync_all = lambda cycles: prog.asm.append(("sync_all", cycles))
    prog.math = lambda page, dst, left, op, right: prog.asm.append(
        ("math", dst, left, op, right)
    )

    OPXResetBenchmarkProgram._measure_project(prog, CAL, "loop")

    syncs = [operation for operation in prog.asm if operation[0] == "sync_all"]
    assert syncs == [("sync_all", 5), ("sync_all", 1000)]


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
    assert TimingMatchedReferenceDMemProgram is not None
    assert OPXResetBenchmarkProgram is not None
    assert OPXResetT1Program is not None
    assert OPXResetT1SweepProgram is not None
    assert OPXResetT1FluxSweepProgram is not None
    assert OPXResetPulseGridProgram is not None


def test_frequency_payload_sweep_uses_frequency_register_and_fixed_gain():
    plan = programs.payload_sweep_plan(
        {
            "opx_payload_sweep_kind": "frequency",
            "opx_payload_frequency_start_mhz": 4350.0,
            "opx_payload_frequency_step_mhz": 0.5,
            "opx_payload_fixed_gain": 11100,
        },
        freq2reg=lambda frequency: int(round(float(frequency) * 10.0)),
    )

    assert plan == {
        "kind": "frequency",
        "start_register": 43500,
        "step_register": 5,
        "fixed_gain": 11100,
        "fixed_frequency_mhz": None,
        "target_register": "freq",
    }


def test_payload_sweep_start_accepts_unsigned_frequency_register_value():
    prog = RecordingProgram()

    programs.initialize_payload_sweep_register(
        prog,
        page=1,
        register=7,
        value=2713346438,
    )

    assert prog.asm == [("safe_regwi", 7, 2713346438)]


def test_gain_payload_sweep_preserves_existing_fixed_frequency_behavior():
    plan = programs.payload_sweep_plan(
        {
            "opx_payload_gain_start": 1000,
            "opx_payload_gain_step": 250,
            "opx_payload_frequency_mhz": 4367.25,
        },
        freq2reg=lambda frequency: int(round(float(frequency) * 10.0)),
    )

    assert plan == {
        "kind": "gain",
        "start_register": 1000,
        "step_register": 250,
        "fixed_gain": None,
        "fixed_frequency_mhz": 4367.25,
        "target_register": "gain",
    }


def test_grid_payload_uses_the_current_unrolled_frequency_and_dynamic_gain():
    prog = RecordingProgram()
    prog.cfg = {"qubit_ch": 1}
    prog.reset_page = 1
    prog.reset_regs = {"payload_sweep": 7}
    prog._payload_frequency_mhz = 4368.25
    prog._payload_sweep_plan = {
        "kind": "gain",
        "fixed_gain": None,
        "fixed_frequency_mhz": 4367.25,
        "target_register": "gain",
    }
    prog.freq2reg = lambda frequency, gen_ch: int(round(float(frequency) * 10))
    prog.set_pulse_registers = lambda **values: prog.asm.append(
        ("set_pulse_registers", values)
    )
    prog.sreg = lambda channel, name: {"freq": 21, "gain": 22}[name]
    prog.deg2reg = lambda value, gen_ch: 0

    OPXResetPulseGridProgram._set_payload_pulse(prog)

    pulse = next(values for name, values in prog.asm if name == "set_pulse_registers")
    assert pulse["freq"] == 43682
    assert pulse["gain"] == 0
    assert ("mathi", 22, 7, "+", 0) in prog.asm


def test_frequency_payload_pulse_copies_sweep_register_only_to_drive_frequency():
    prog = RecordingProgram()
    prog.cfg = {"qubit_ch": 1}
    prog.reset_page = 1
    prog.reset_regs = {"payload_sweep": 7}
    prog._payload_sweep_plan = {
        "kind": "frequency",
        "fixed_gain": 11100,
        "fixed_frequency_mhz": None,
        "target_register": "freq",
    }
    prog.set_pulse_registers = lambda **values: prog.asm.append(
        ("set_pulse_registers", values)
    )
    prog.sreg = lambda channel, name: {"freq": 21, "gain": 22}[name]
    prog.deg2reg = lambda value, gen_ch: 0

    OPXResetPulseSweepProgram._set_payload_pulse(prog)

    pulse = next(values for name, values in prog.asm if name == "set_pulse_registers")
    assert pulse["freq"] == 0
    assert pulse["gain"] == 11100
    assert ("mathi", 21, 7, "+", 0) in prog.asm
    assert not any(op[0] == "mathi" and op[1] == 22 for op in prog.asm)
