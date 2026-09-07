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
    emit_resident_stream_finish,
    emit_resident_stream_shot_boundary,
    initialize_resident_stream,
    resident_stream_plan,
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

    def math(self, page, dst, left, op, right):
        self.asm.append(("math", dst, left, op, right))

    def bitwi(self, page, dst, src, op, value):
        self.asm.append(("bitwi", dst, src, op, int(value)))

    def condj(self, page, left, op, right, label):
        self.asm.append(("condj", left, op, right, label))

    def label(self, label):
        self.asm.append(("label", label))

    def memw(self, page, value_reg, address_reg):
        self.asm.append(("memw", value_reg, address_reg))

    def memwi(self, page, value_reg, address):
        self.asm.append(("memwi", value_reg, address))

    def memr(self, page, value_reg, address_reg):
        self.asm.append(("memr", value_reg, address_reg))

    def loopnz(self, page, register, label):
        self.asm.append(("loopnz", register, label))

    def sync(self, page, register):
        self.asm.append(("sync", page, register))


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


def test_resident_stream_uses_two_whole_shot_banks():
    plan = resident_stream_plan(
        {"tprocs": [{"dmem_size": 4096}]},
        done_addr=1,
        record_base=32,
        record_words=2,
        records_per_unit=1,
        total_units=201000,
        records_per_shot=201,
        total_shots=1000,
    )

    assert plan == {
        "done_addr": 1,
        "ack_addr": 2,
        "ready_addr": 3,
        "bank_units": 1016,
        "bank_records": 1016,
        "bank_words": 2032,
        "total_shots": 1000,
        "total_units": 201000,
        "records_per_unit": 1,
        "records_per_shot": 201,
        "final_partial_units": 848,
    }


def test_one_shot_bank_record_base_forces_reuse_on_the_third_shot():
    record_base_fn = getattr(programs, "one_shot_bank_record_base", None)
    assert callable(record_base_fn), "one_shot_bank_record_base is missing"
    record_base = record_base_fn(
        dmem_words=4096,
        records_per_shot=121,
        record_words=2,
    )
    plan = resident_stream_plan(
        {"tprocs": [{"dmem_size": 4096}]},
        done_addr=1,
        record_base=record_base,
        record_words=2,
        records_per_unit=1,
        total_units=6 * 121,
        records_per_shot=121,
        total_shots=6,
    )
    assert record_base == 3612
    assert plan["bank_units"] == 121
    assert plan["bank_words"] == 242


def test_resident_stream_boundary_waits_only_before_reusing_a_bank():
    prog = RecordingProgram()
    regs = {
        "stream_remaining": 20,
        "stream_ready": 21,
        "stream_ack": 22,
        "stream_ack_addr": 23,
        "stream_bank": 24,
    }
    plan = resident_stream_plan(
        {"tprocs": [{"dmem_size": 64}]},
        done_addr=1,
        record_base=32,
        record_words=2,
        records_per_unit=2,
        total_units=5,
        records_per_shot=2,
        total_shots=5,
    )

    initialize_resident_stream(
        prog,
        controls=regs,
        address_page=1,
        address_register=9,
        plan=plan,
        label_prefix="STREAM",
    )
    emit_resident_stream_shot_boundary(prog)
    emit_resident_stream_finish(prog)

    assert ("memr", 22, 23) in prog.asm
    assert ("condj", 22, "<", 21, "STREAM_0_WAIT_ACK") in prog.asm
    assert ("mathi", 9, 9, "-", 32) in prog.asm
    assert ("memwi", 21, 3) in prog.asm


def test_resident_stream_boundary_rebases_timeline_by_ack_wait_cycles():
    prog = RecordingProgram()
    regs = {
        "stream_remaining": 20,
        "stream_ready": 21,
        "stream_ack": 22,
        "stream_ack_addr": 23,
        "stream_bank": 24,
    }
    plan = resident_stream_plan(
        {"tprocs": [{"dmem_size": 64}]},
        done_addr=1,
        record_base=32,
        record_words=2,
        records_per_unit=2,
        total_units=5,
        records_per_shot=2,
        total_shots=5,
    )

    initialize_resident_stream(
        prog,
        controls=regs,
        address_page=1,
        address_register=9,
        plan=plan,
        label_prefix="STREAM",
    )
    emit_resident_stream_shot_boundary(prog)

    elapsed_start = prog.asm.index(("regwi", 20, 200))
    wait_label = prog.asm.index(("label", "STREAM_0_WAIT_ACK"))
    elapsed_step = prog.asm.index(("mathi", 20, 20, "+", 14))
    ack_read = prog.asm.index(("memr", 22, 23))
    timeline_sync = prog.asm.index(("sync", 0, 20))
    ready_increment = prog.asm.index(("mathi", 21, 21, "+", 1))
    assert (
        elapsed_start
        < wait_label
        < elapsed_step
        < ack_read
        < timeline_sync
        < ready_increment
    )


def test_resident_stream_rejects_control_address_aliases():
    with pytest.raises(ValueError, match="distinct"):
        resident_stream_plan(
            {"tprocs": [{"dmem_size": 64}]},
            done_addr=2,
            record_base=32,
            record_words=2,
            records_per_unit=1,
            total_units=4,
            records_per_shot=2,
            total_shots=2,
            ack_addr=2,
            ready_addr=3,
        )


def test_resident_stream_requires_controls_before_record_memory():
    with pytest.raises(ValueError, match="precede record memory"):
        resident_stream_plan(
            {"tprocs": [{"dmem_size": 64}]},
            done_addr=32,
            record_base=32,
            record_words=2,
            records_per_unit=1,
            total_units=4,
            records_per_shot=2,
            total_shots=2,
        )


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


def test_t1_hard_flux_cycle_applies_compensation_on_target_and_return():
    prog = RecordingProgram()
    prog.soccfg = {"gens": [{}, {}, {}, {"maxv": 32767}]}
    prog.cfg = {
        "ff_ch": 3,
        "ff_gain": -20000,
        "ff_park_gain": -25790,
    }
    prog.reset_config = type("ResetConfig", (), {"hard_flux_steps": True})()
    prog._t1_stepping = True
    prog._t1_ff_settle_us = 0.5
    prog._t1_hold_us = 1.0
    prog._t1_ff_compensation = {
        "segment_edges_ns": [0.0, 500.0, 1000.0],
        "multipliers": [1.1, 1.0, 0.9],
    }
    prog.set_pulse_registers = lambda **values: prog.asm.append(("set", values))
    prog.pulse = lambda ch: prog.asm.append(("pulse", ch))
    prog.us2cycles = lambda value, gen_ch=None: int(round(float(value) * 100))
    prog.sync_all = lambda cycles: prog.asm.append(("sync", cycles))

    OPXResetT1Program._wait_t1_payload(prog, 1.0)

    gains = [entry[1]["gain"] for entry in prog.asm if entry[0] == "set"]
    lengths = [entry[1]["length"] for entry in prog.asm if entry[0] == "set"]
    assert gains == [-19421, -20000, -20579, -26369, -25790]
    assert lengths == [50, 50, 50, 50, 3]
    assert prog.asm[-1] == ("sync", 0)


def test_dynamic_compensated_hold_synchronizes_before_payload_readout(monkeypatch):
    prog = RecordingProgram()
    prog.cfg = {"ff_ch": 3, "ff_park_gain": -25790}
    prog._t1_ff_settle_us = 0.5
    prog._t1_ff_compensation = {
        "segment_edges_ns": [0.0],
        "multipliers": [1.1],
    }
    prog._play_dynamic_compensation_segment = (
        lambda multiplier, duration, returning=False: prog.asm.append(
            ("segment", multiplier, duration, returning)
        )
    )
    prog.sync_all = lambda cycles: prog.asm.append(("sync", cycles))
    monkeypatch.setattr(
        ff_pulse,
        "play_hard_step",
        lambda program, gain: program.asm.append(("park", int(gain))),
    )

    OPXResetT1FluxSweepProgram._play_dynamic_compensated_hold(prog, 10.0)

    assert prog.asm[-2:] == [("park", -25790), ("sync", 0)]


def test_dynamic_t1_compensation_uses_dc_delta_for_both_directions():
    prog = RecordingProgram()
    prog.soccfg = {
        "gens": [{}, {}, {}, {"type": "axis_signal_gen_v6"}],
    }
    prog.cfg = {"ff_ch": 3, "ff_park_gain": -25790}
    prog._t1_flux_ff_page = 1
    prog._t1_flux_regs = {
        "dc_gain": 9,
        "dc_delta": 10,
        "park_gain": 11,
        "command": 12,
    }
    prog._t1_flux_direction = 1
    prog.sreg = lambda channel, name: 13
    prog.set_pulse_registers = lambda **values: prog.asm.append(("set", values))
    prog.pulse = lambda ch: prog.asm.append(("pulse", ch))
    prog.us2cycles = lambda value, gen_ch=None: int(round(float(value) * 100))

    OPXResetT1FluxSweepProgram._play_dynamic_compensation_segment(
        prog, 1.1, 0.5, returning=False
    )
    OPXResetT1FluxSweepProgram._play_dynamic_compensation_segment(
        prog, 1.1, 0.5, returning=True
    )

    assert ("math", 12, 9, "+", 12) in prog.asm
    assert ("math", 12, 11, "-", 12) in prog.asm
    assert sum(entry == ("pulse", 3) for entry in prog.asm) == 2


def test_dynamic_t1_compensation_packs_gain_for_interpolated_generator():
    prog = RecordingProgram()
    prog.soccfg = {
        "gens": [{}, {}, {}, {"type": "axis_sg_int4_v1"}],
    }
    prog.cfg = {"ff_ch": 3, "ff_park_gain": -25790}
    prog._t1_flux_ff_page = 1
    prog._t1_flux_regs = {
        "dc_gain": 9,
        "dc_delta": 10,
        "park_gain": 11,
        "command": 12,
    }
    prog._t1_flux_direction = 1
    prog.sreg = lambda channel, name: {"gain": 13, "addr": 14}[name]
    prog.set_pulse_registers = lambda **values: prog.asm.append(("set", values))
    prog.pulse = lambda ch: prog.asm.append(("pulse", ch))
    prog.us2cycles = lambda value, gen_ch=None: int(round(float(value) * 100))

    OPXResetT1FluxSweepProgram._play_dynamic_compensation_segment(
        prog, 1.1, 0.5, returning=False
    )

    assert ("bitwi", 12, 12, "<<", 16) in prog.asm
    assert ("mathi", 14, 12, "+", 0) in prog.asm
    assert ("mathi", 13, 12, "+", 0) not in prog.asm


def test_dynamic_t1_compensation_writes_raw_gain_for_full_speed_generator():
    prog = RecordingProgram()
    prog.soccfg = {
        "gens": [{}, {}, {}, {"type": "axis_signal_gen_v6"}],
    }
    prog.cfg = {"ff_ch": 3, "ff_park_gain": -25790}
    prog._t1_flux_ff_page = 1
    prog._t1_flux_regs = {
        "dc_gain": 9,
        "dc_delta": 10,
        "park_gain": 11,
        "command": 12,
    }
    prog._t1_flux_direction = 1
    prog.sreg = lambda channel, name: {"gain": 13, "addr": 14}[name]
    prog.set_pulse_registers = lambda **values: prog.asm.append(("set", values))
    prog.pulse = lambda ch: prog.asm.append(("pulse", ch))
    prog.us2cycles = lambda value, gen_ch=None: int(round(float(value) * 100))

    OPXResetT1FluxSweepProgram._play_dynamic_compensation_segment(
        prog, 1.1, 0.5, returning=False
    )

    assert ("mathi", 13, 12, "+", 0) in prog.asm
    assert ("bitwi", 12, 12, "<<", 16) not in prog.asm


def test_three_point_dynamic_flux_target_comes_from_dc_loop_register():
    prog = RecordingProgram()
    prog.soccfg = {
        "gens": [{}, {}, {}, {"type": "axis_signal_gen_v6"}],
    }
    prog.cfg = {"ff_ch": 3}
    prog._t1_3pt_ff_page = 1
    prog._t1_3pt_regs = {"dc_gain": 9, "command": 12}
    prog.sreg = lambda channel, name: 11
    prog.pulse = lambda ch: prog.asm.append(("pulse", ch))

    OPXResetT13PointProgram._play_dynamic_target(prog)

    assert prog.asm == [
        ("mathi", 11, 9, "+", 0),
        ("pulse", 3),
    ]


def test_three_point_dynamic_flux_target_packs_interpolated_gain_without_mutating_loop_register():
    prog = RecordingProgram()
    prog.soccfg = {
        "gens": [{}, {}, {}, {"type": "axis_sg_int4_v1"}],
    }
    prog.cfg = {"ff_ch": 3}
    prog._t1_3pt_ff_page = 1
    prog._t1_3pt_regs = {"dc_gain": 9, "command": 12}
    prog.sreg = lambda channel, name: {"gain": 13, "addr": 14}[name]
    prog.pulse = lambda ch: prog.asm.append(("pulse", ch))

    OPXResetT13PointProgram._play_dynamic_target(prog)

    assert prog.asm == [
        ("bitwi", 12, 9, "<<", 16),
        ("mathi", 14, 12, "+", 0),
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


def test_three_point_placeholder_preserves_fixed_stream_shape_without_a_measurement():
    prog = RecordingProgram()
    prog.reset_page = 1
    prog.reset_regs = {"i": 6, "q": 7, "address": 9}

    OPXResetT13PointProgram._emit_placeholder_payload_record(prog)

    assert prog.asm == [
        ("regwi", 6, 0),
        ("regwi", 7, 0),
        ("memw", 6, 9),
        ("mathi", 9, 9, "+", 1),
        ("memw", 7, 9),
        ("mathi", 9, 9, "+", 1),
    ]


def test_three_point_p0_reference_flag_compares_the_distributed_shot_schedule():
    prog = RecordingProgram()
    prog.cfg = {"opx_t1_3pt_p0_reference_shot_indices": [0, 1, 8, 9]}
    controls = {"shot_index": 4, "branch_flag": 5, "p0_target": 6}

    OPXResetT13PointProgram._set_p0_reference_flag(prog, controls, "P0_REF")

    assert [entry for entry in prog.asm if entry[:2] == ("regwi", 6)] == [
        ("regwi", 6, 0),
        ("regwi", 6, 1),
        ("regwi", 6, 8),
        ("regwi", 6, 9),
    ]
    assert [
        entry for entry in prog.asm
        if entry[:4] == ("condj", 4, "==", 6)
    ] == [
        ("condj", 4, "==", 6, "P0_REF_ENABLED"),
        ("condj", 4, "==", 6, "P0_REF_ENABLED"),
        ("condj", 4, "==", 6, "P0_REF_ENABLED"),
        ("condj", 4, "==", 6, "P0_REF_ENABLED"),
    ]
    assert ("regwi", 5, 0) in prog.asm
    assert ("regwi", 5, 1) in prog.asm


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


def test_passive_payload_grid_waits_before_each_payload_without_active_tail(monkeypatch):
    prog = object.__new__(OPXResetPulseSweepProgram)
    prog.cfg = {
        "opx_reset_scheme": "none",
        "qua_passive_pre_point_delay_us": 1000.0,
        "qubit_ch": 1,
    }
    prog.reset_config = SimpleNamespace(inter_shot_delay_us=10.0)
    prog.reset_page = 1
    prog.reset_regs = {}
    prog.payload_calibration = CAL
    prog.loop_calibration = CAL
    prog._payload_label_prefix = "PASSIVE"
    prog._shot_park_callbacks = lambda: (lambda: None, lambda: None)
    prog._emit_payload_pulses = lambda: None
    prog._measure_project = lambda *args: None
    prog._set_reset_pulse = lambda: None
    prog.pulse = lambda ch: None
    prog.us2cycles = lambda value: float(value)
    waits = []
    prog.sync_all = lambda cycles: waits.append(cycles)
    monkeypatch.setattr(programs, "emit_payload_reset_shot", lambda *args, **kwargs: None)

    OPXResetPulseSweepProgram._emit_body(prog)

    assert waits == [1000.0]


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


def test_loop_measurement_does_not_hide_ringdown_inside_the_measurement_callback():
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
    assert syncs == [("sync_all", 5)]


def test_reset_ringdown_wait_covers_feedback_latency_and_resonator_depletion():
    prog = RecordingProgram()
    prog.reset_config = type(
        "ResetConfig",
        (),
        {
            "feedback_syncdelay_us": 8.0,
            "loop_recovery_us": 10.0,
        },
    )()
    prog.us2cycles = lambda value: int(round(100 * value))
    prog.sync_all = lambda cycles: prog.asm.append(("sync_all", cycles))

    OPXResetBenchmarkProgram._wait_reset_ringdown(prog)

    assert prog.asm == [("sync_all", 1000)]


def test_loop_reference_matches_the_runtime_feedback_timing():
    events = []

    emit_timing_matched_reference_shot(
        context="loop",
        prep_excited=True,
        measure=lambda: events.append("measure"),
        prepare_excited=lambda: events.append("pi"),
        wait_read_delay=lambda: events.append("read_delay"),
        wait_reset_ringdown=lambda: events.append("ringdown"),
        wait_reset_settle=lambda: events.append("reset_settle"),
        wait_payload_alignment=lambda: events.append("payload_alignment"),
    )

    assert events == [
        "measure",
        "read_delay",
        "ringdown",
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
        wait_reset_ringdown=lambda: events.append("ringdown"),
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


def test_grid_payload_uses_the_current_unrolled_gain_and_dynamic_frequency():
    prog = RecordingProgram()
    prog.cfg = {"qubit_ch": 1}
    prog.reset_page = 1
    prog.reset_regs = {"payload_sweep": 7}
    prog._payload_gain_dac = 12500
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

    OPXResetPulseGridProgram._set_payload_pulse(prog)

    pulse = next(values for name, values in prog.asm if name == "set_pulse_registers")
    assert pulse["freq"] == 0
    assert pulse["gain"] == 12500
    assert ("mathi", 21, 7, "+", 0) in prog.asm


def test_grid_program_unrolls_gains_instead_of_frequencies(monkeypatch):
    prog = RecordingProgram()
    prog.cfg = {
        "qubit_ch": 1,
        "opx_payload_shots_per_expt": 2,
        "opx_payload_frequencies_mhz": [4365.0, 4366.0, 4367.0, 4368.0],
        "opx_payload_gains": [5000, 10000],
    }
    prog.record_base = 32
    prog.done_addr = 0
    prog._payload_sweep_plan = {
        "start_register": 43650,
        "step_register": 10,
    }
    prog.ch_page = lambda channel: channel
    prog.end = lambda: prog.asm.append(("end",))
    prog._declare_experiment = lambda: None
    prog._begin_park_lifecycle = lambda: None
    prog._end_park_lifecycle = lambda: None
    prog._initialize_stream = lambda *args, **kwargs: setattr(prog, "stream_plan", None)
    prog._stream_after_shot = lambda: None
    prog._finish_stream = lambda: None
    emitted = []
    prog._emit_body = lambda: emitted.append(prog._payload_gain_dac)
    monkeypatch.setattr(programs, "_declare_common", lambda program: None)
    monkeypatch.setattr(
        programs,
        "allocate_named_registers",
        lambda program, page, names, reserved=(): {
            name: index + 1 for index, name in enumerate(names)
        },
    )

    OPXResetPulseGridProgram.make_program(prog)

    assert emitted == [5000, 10000]
    assert any(
        instruction[-1] == "OPX_PAYLOAD_GRID_FREQUENCY_LOOP"
        for instruction in prog.asm
        if instruction[0] == "loopnz"
    )


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


def test_frequency_payload_supports_a_constant_spectroscopy_pulse():
    prog = RecordingProgram()
    prog.cfg = {
        "qubit_ch": 1,
        "qubit_pulse_style": "const",
        "qubit_length": 1.25,
    }
    prog.reset_page = 1
    prog.reset_regs = {"payload_sweep": 7}
    prog._payload_sweep_plan = {
        "kind": "frequency",
        "fixed_gain": 15000,
        "fixed_frequency_mhz": None,
        "target_register": "freq",
    }
    prog.set_pulse_registers = lambda **values: prog.asm.append(
        ("set_pulse_registers", values)
    )
    prog.sreg = lambda channel, name: {"freq": 21, "gain": 22}[name]
    prog.deg2reg = lambda value, gen_ch: 0
    prog.us2cycles = lambda value, gen_ch: int(round(float(value) * 100))

    OPXResetPulseSweepProgram._set_payload_pulse(prog)

    pulse = next(values for name, values in prog.asm if name == "set_pulse_registers")
    assert pulse == {
        "ch": 1,
        "style": "const",
        "freq": 0,
        "phase": 0,
        "gain": 15000,
        "length": 125,
    }
    assert ("mathi", 21, 7, "+", 0) in prog.asm


def test_pulse_sweep_declaration_accepts_constant_spectroscopy_payloads():
    prog = RecordingProgram()
    prog.cfg = {
        "qubit_ch": 1,
        "qubit_pulse_style": "const",
        "read_pulse_freq": 6933.0,
        "ro_chs": [0],
        "res_ch": 0,
        "opx_payload_shots_per_expt": 2,
        "opx_payload_expts": 3,
        "opx_payload_sweep_kind": "frequency",
        "opx_payload_frequency_start_mhz": 4360.0,
        "opx_payload_frequency_step_mhz": 1.0,
        "opx_payload_fixed_gain": 15000,
        "opx_payload_pulses": 1,
        "sigma": 0.25,
        "qubit_drag_beta": 0.0,
    }
    prog.reset_config = SimpleNamespace(hard_flux_steps=True)
    prog.freq2reg = lambda value, **kwargs: int(round(float(value) * 10))
    prog.us2cycles = lambda value, **kwargs: int(round(float(value) * 100))
    prog.add_gauss = lambda **kwargs: prog.asm.append(("add_gauss", kwargs))

    OPXResetPulseSweepProgram._declare_experiment(prog)

    assert prog._payload_sweep_plan["kind"] == "frequency"
    assert prog._payload_expts == 3
    assert not any(op[0] == "mathi" and op[1] == 22 for op in prog.asm)
