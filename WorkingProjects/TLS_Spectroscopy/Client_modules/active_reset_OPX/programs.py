"""QICK programs for isolated OPX-style reset calibration and benchmarking."""

import numpy as np

from .classifier import ClassifierCalibration
from .config import OPXResetConfig
from .control_flow import emit_reset_state_machine, emit_unbounded_reset_state_machine
from .records import (
    PAYLOAD_RECORD_WORDS,
    RECORD_WORDS,
    TerminalStatus,
    decode_payload_records,
    signed32,
)


try:
    from qick import AveragerProgram, QickProgram
    _QICK_IMPORT_ERROR = None
except Exception as exc:  # analysis and unit-test computers do not have PYNQ/QICK
    _QICK_IMPORT_ERROR = exc

    class _UnavailableQickProgram:
        def __init__(self, *args, **kwargs):
            raise RuntimeError(
                "QICK is unavailable; run hardware programs on the measurement PC"
            ) from _QICK_IMPORT_ERROR

    AveragerProgram = QickProgram = _UnavailableQickProgram


REGISTER_NAMES = (
    "i",
    "q",
    "z",
    "ground",
    "excited",
    "attempts",
    "pi_count",
    "status",
    "initial_z",
    "address",
)

TLS_MEMORY_SEQUENCES = ("single", "double", "ground_double")


def payload_sweep_plan(cfg, *, freq2reg):
    kind = str(cfg.get("opx_payload_sweep_kind", "gain")).strip().lower()
    if kind == "gain":
        gain_start = cfg.get("opx_payload_gain_start")
        if gain_start is None:
            gain_start = cfg["qubit_pi_gain"]
        fixed_frequency = cfg.get("opx_payload_frequency_mhz")
        if fixed_frequency is None:
            fixed_frequency = cfg.get("qubit_pi_freq", cfg.get("qubit_freq"))
        if fixed_frequency is None:
            raise ValueError("gain payload sweep requires a payload frequency")
        return {
            "kind": kind,
            "start_register": int(gain_start),
            "step_register": int(cfg.get("opx_payload_gain_step", 0)),
            "fixed_gain": None,
            "fixed_frequency_mhz": float(fixed_frequency),
            "target_register": "gain",
        }
    if kind == "frequency":
        start_mhz = float(cfg["opx_payload_frequency_start_mhz"])
        step_mhz = float(cfg.get("opx_payload_frequency_step_mhz", 0.0))
        start_register = int(freq2reg(start_mhz))
        fixed_gain = cfg.get("opx_payload_fixed_gain")
        if fixed_gain is None:
            fixed_gain = cfg["qubit_pi_gain"]
        return {
            "kind": kind,
            "start_register": start_register,
            "step_register": int(freq2reg(start_mhz + step_mhz)) - start_register,
            "fixed_gain": int(fixed_gain),
            "fixed_frequency_mhz": None,
            "target_register": "freq",
        }
    raise ValueError("opx_payload_sweep_kind must be 'gain' or 'frequency'")


def initialize_payload_sweep_register(prog, *, page, register, value):
    prog.safe_regwi(page, register, int(value))


def write_dynamic_const_gain(
    prog,
    *,
    page,
    channel,
    value_register,
    scratch_register=None,
):
    gen_type = str(prog.soccfg["gens"][int(channel)].get("type", ""))
    if gen_type == "axis_sg_int4_v1":
        packed_register = (
            int(value_register)
            if scratch_register is None
            else int(scratch_register)
        )
        prog.bitwi(
            int(page),
            packed_register,
            int(value_register),
            "<<",
            16,
        )
        prog.mathi(
            int(page),
            prog.sreg(int(channel), "addr"),
            packed_register,
            "+",
            0,
        )
        return
    prog.mathi(
        int(page),
        prog.sreg(int(channel), "gain"),
        int(value_register),
        "+",
        0,
    )


def _reserved_registers(prog, page):
    reserved = {0}
    if int(page) == 0:
        reserved.update({13, 14, 15, 31})
    for section, field in (("gens", "tproc_ch"), ("readouts", "tproc_ctrl")):
        try:
            entries = list(prog.soccfg[section])
        except (KeyError, TypeError, AttributeError):
            entries = []
        for entry in entries:
            try:
                channel = entry.get(field) if hasattr(entry, "get") else entry[field]
                if channel is None or prog._ch_page_tproc(int(channel)) != int(page):
                    continue
                for name in prog.pulse_registers:
                    reserved.add(prog._sreg_tproc(int(channel), name))
            except (KeyError, TypeError, ValueError, AttributeError):
                continue
    return reserved


def allocate_named_registers(prog, page, names, reserved=None):
    names = tuple(names)
    if not names or len(set(names)) != len(names):
        raise ValueError("scratch register names must be distinct and nonempty")
    reserved = set(_reserved_registers(prog, page) if reserved is None else reserved)
    available = [reg for reg in range(1, 31) if reg not in reserved]
    if len(available) < len(names):
        raise ValueError(
            f"OPX reset needs {len(names)} scratch registers on page {page}, "
            f"but only {len(available)} are free; reserved={sorted(reserved)}"
        )
    return dict(zip(names, available[:len(names)]))


def allocate_registers(prog, page, reserved=None):
    return allocate_named_registers(
        prog, page, REGISTER_NAMES, reserved=reserved
    )


def resident_stream_plan(
    soccfg,
    *,
    done_addr,
    record_base,
    record_words,
    records_per_unit,
    total_units,
    records_per_shot,
    total_shots,
    ack_addr=2,
    ready_addr=3,
):
    record_base = int(record_base)
    record_words = int(record_words)
    records_per_unit = int(records_per_unit)
    total_units = int(total_units)
    records_per_shot = int(records_per_shot)
    total_shots = int(total_shots)
    done_addr = int(done_addr)
    ack_addr = int(ack_addr)
    ready_addr = int(ready_addr)
    try:
        dmem_words = int(soccfg["tprocs"][0]["dmem_size"])
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ValueError("the board configuration does not report tProc data memory") from exc
    if min(record_words, records_per_unit, total_units, records_per_shot, total_shots) <= 0:
        raise ValueError("resident stream dimensions must be positive")
    if records_per_unit * total_units != records_per_shot * total_shots:
        raise ValueError("resident stream units do not cover the requested shot records")
    control_addresses = {done_addr, ack_addr, ready_addr}
    if len(control_addresses) != 3 or min(control_addresses) < 0:
        raise ValueError("resident stream control addresses must be distinct and non-negative")
    if max(control_addresses) >= record_base:
        raise ValueError("resident stream control addresses must precede record memory")
    words_per_unit = record_words * records_per_unit
    bank_units = (dmem_words - record_base) // (2 * words_per_unit)
    if bank_units <= 0:
        raise ValueError("two complete resident stream units do not fit in tProc data memory")
    bank_records = bank_units * records_per_unit
    return {
        "done_addr": done_addr,
        "ack_addr": ack_addr,
        "ready_addr": ready_addr,
        "bank_units": bank_units,
        "bank_records": bank_records,
        "bank_words": bank_records * record_words,
        "total_shots": total_shots,
        "total_units": total_units,
        "records_per_unit": records_per_unit,
        "records_per_shot": records_per_shot,
        "final_partial_units": total_units % bank_units,
    }


def initialize_resident_stream(
    prog,
    *,
    controls,
    address_page,
    address_register,
    plan,
    label_prefix,
):
    prog._resident_stream = {
        "controls": dict(controls),
        "address_page": int(address_page),
        "address_register": int(address_register),
        "plan": dict(plan),
        "label_prefix": str(label_prefix),
        "emission_index": 0,
    }
    prog.stream_plan = dict(plan)
    prog.regwi(0, controls["stream_remaining"], int(plan["bank_units"]) - 1)
    prog.regwi(0, controls["stream_ready"], 0)
    prog.memwi(0, controls["stream_ready"], int(plan["ready_addr"]))
    prog.regwi(0, controls["stream_ack_addr"], int(plan["ack_addr"]))
    prog.regwi(0, controls["stream_bank"], 0)


def emit_resident_stream_shot_boundary(prog):
    stream = prog._resident_stream
    controls = stream["controls"]
    plan = stream["plan"]
    prefix = f'{stream["label_prefix"]}_{stream["emission_index"]}'
    stream["emission_index"] += 1
    continuation = f"{prefix}_CONTINUE"
    if int(plan["bank_units"]) > 1:
        prog.loopnz(0, controls["stream_remaining"], continuation)
    wait_label = f"{prefix}_WAIT_ACK"
    first_bank = f"{prefix}_FIRST_BANK"
    switched = f"{prefix}_SWITCHED"
    prog.label(wait_label)
    prog.memr(0, controls["stream_ack"], controls["stream_ack_addr"])
    prog.condj(
        0,
        controls["stream_ack"],
        "<",
        controls["stream_ready"],
        wait_label,
    )
    prog.mathi(
        0,
        controls["stream_ready"],
        controls["stream_ready"],
        "+",
        1,
    )
    prog.memwi(0, controls["stream_ready"], int(plan["ready_addr"]))
    prog.condj(0, controls["stream_bank"], "==", 0, first_bank)
    prog.mathi(
        stream["address_page"],
        stream["address_register"],
        stream["address_register"],
        "-",
        2 * int(plan["bank_words"]),
    )
    prog.regwi(0, controls["stream_bank"], 0)
    prog.condj(0, controls["stream_bank"], "==", controls["stream_bank"], switched)
    prog.label(first_bank)
    prog.regwi(0, controls["stream_bank"], 1)
    prog.label(switched)
    prog.regwi(0, controls["stream_remaining"], int(plan["bank_units"]) - 1)
    prog.label(continuation)


def emit_resident_stream_finish(prog):
    stream = prog._resident_stream
    plan = stream["plan"]
    if int(plan["final_partial_units"]) == 0:
        return
    controls = stream["controls"]
    prog.mathi(
        0,
        controls["stream_ready"],
        controls["stream_ready"],
        "+",
        1,
    )
    prog.memwi(0, controls["stream_ready"], int(plan["ready_addr"]))


def resident_control_names(cfg, names):
    names = tuple(names)
    if not bool(cfg.get("opx_resident_dmem_stream", False)):
        return names
    return names + (
        "stream_remaining",
        "stream_ready",
        "stream_ack",
        "stream_ack_addr",
        "stream_bank",
    )


def emit_record(prog, *, page, regs, preparation):
    prog.regwi(page, regs["ground"], int(preparation), "preparation label")
    fields = (
        "ground",
        "initial_z",
        "attempts",
        "pi_count",
        "status",
        "i",
        "q",
        "z",
    )
    for name in fields:
        prog.memw(page, regs[name], regs["address"])
        prog.mathi(page, regs["address"], regs["address"], "+", 1)


def emit_benchmark_shot(
    prog,
    *,
    page,
    regs,
    preparation,
    reset_scheme,
    payload_calibration,
    loop_calibration,
    max_reset_attempts,
    park_up,
    park_down,
    prepare_excited,
    measure_project,
    measure_verification,
    play_pi,
    label_prefix,
    wait_reset_ringdown=None,
):
    park_up()
    if int(preparation):
        prepare_excited()
    measure_project(payload_calibration, "payload")
    prog.mathi(page, regs["initial_z"], regs["z"], "+", 0)

    scheme = str(reset_scheme).strip().lower()
    if scheme == "opx":
        emit_reset_state_machine(
            prog,
            page=page,
            regs=regs,
            payload_calibration=payload_calibration,
            loop_calibration=loop_calibration,
            max_reset_attempts=max_reset_attempts,
            measure_next=lambda: measure_project(loop_calibration, "loop"),
            play_pi=play_pi,
            label_prefix=label_prefix,
            wait_reset_ringdown=wait_reset_ringdown,
        )
    elif scheme == "opx_unbounded":
        emit_unbounded_reset_state_machine(
            prog,
            page=page,
            regs=regs,
            payload_calibration=payload_calibration,
            loop_calibration=loop_calibration,
            measure_next=lambda: measure_project(loop_calibration, "loop"),
            play_pi=play_pi,
            label_prefix=label_prefix,
            wait_reset_ringdown=wait_reset_ringdown,
        )
    elif scheme == "none":
        prog.regwi(page, regs["attempts"], 0, "no-reset attempts")
        prog.regwi(page, regs["pi_count"], 0, "no-reset pi count")
        prog.regwi(page, regs["status"], int(TerminalStatus.NO_RESET), "no reset")
    else:
        raise ValueError("reset_scheme must be 'opx', 'opx_unbounded', or 'none'")

    measure_verification()
    emit_record(prog, page=page, regs=regs, preparation=preparation)
    park_down()


def emit_t1_shot(
    prog,
    *,
    page,
    regs,
    reset_scheme,
    payload_calibration,
    loop_calibration,
    park_up,
    park_down,
    prepare_excited,
    wait_payload,
    measure_project,
    play_pi,
    label_prefix,
    do_prepare=True,
    prepare_reset=None,
    wait_diagnostic_hold=None,
    diagnostic_cycles=2,
    wait_reset_ringdown=None,
):
    park_up()
    if bool(do_prepare):
        prepare_excited()
    wait_payload()
    measure_project(payload_calibration, "payload")
    prog.mathi(page, regs["initial_z"], regs["z"], "+", 0)
    prog.mathi(page, regs["address"], regs["address"], "+", 5)
    prog.memw(page, regs["i"], regs["address"])
    prog.mathi(page, regs["address"], regs["address"], "+", 1)
    prog.memw(page, regs["q"], regs["address"])
    prog.mathi(page, regs["address"], regs["address"], "-", 6)
    scheme = str(reset_scheme).strip().lower()
    if scheme == "opx_unbounded":
        if prepare_reset is not None:
            prepare_reset()
        emit_unbounded_reset_state_machine(
            prog,
            page=page,
            regs=regs,
            payload_calibration=payload_calibration,
            loop_calibration=loop_calibration,
            measure_next=lambda: measure_project(loop_calibration, "loop"),
            play_pi=play_pi,
            label_prefix=label_prefix,
            wait_reset_ringdown=wait_reset_ringdown,
        )
    elif scheme == "none":
        prog.regwi(page, regs["attempts"], 0, "no-reset attempts")
        prog.regwi(page, regs["pi_count"], 0, "no-reset pi count")
        prog.regwi(page, regs["status"], int(TerminalStatus.NO_RESET), "no reset")
    elif scheme == "diagnostic_hold":
        if wait_diagnostic_hold is None:
            raise ValueError("diagnostic_hold requires wait_diagnostic_hold")
        wait_diagnostic_hold()
        prog.regwi(page, regs["attempts"], 0, "no-reset attempts")
        prog.regwi(page, regs["pi_count"], 0, "no-reset pi count")
        prog.regwi(page, regs["status"], int(TerminalStatus.NO_RESET), "no reset")
    elif scheme in ("diagnostic_readout", "diagnostic_pi_readout"):
        cycles = int(diagnostic_cycles)
        if cycles < 1:
            raise ValueError("diagnostic_cycles must be positive")
        for _ in range(cycles):
            if scheme == "diagnostic_pi_readout":
                play_pi()
            measure_project(loop_calibration, "loop")
        pi_count = cycles if scheme == "diagnostic_pi_readout" else 0
        prog.regwi(page, regs["attempts"], cycles, "fixed diagnostic readouts")
        prog.regwi(page, regs["pi_count"], pi_count, "fixed diagnostic pi count")
        prog.regwi(page, regs["status"], int(TerminalStatus.NO_RESET), "no reset")
    else:
        raise ValueError(
            "reset_scheme must be 'opx_unbounded', 'none', "
            "'diagnostic_hold', 'diagnostic_readout', or "
            "'diagnostic_pi_readout'"
        )
    prog.regwi(page, regs["ground"], int(bool(do_prepare)), "preparation label")
    for name in ("ground", "initial_z", "attempts", "pi_count", "status"):
        prog.memw(page, regs[name], regs["address"])
        prog.mathi(page, regs["address"], regs["address"], "+", 1)
    prog.mathi(page, regs["address"], regs["address"], "+", 2)
    prog.memw(page, regs["z"], regs["address"])
    prog.mathi(page, regs["address"], regs["address"], "+", 1)
    park_down()


def emit_payload_reset_shot(
    prog,
    *,
    page,
    regs,
    reset_scheme="opx_unbounded",
    payload_calibration,
    loop_calibration,
    park_up,
    park_down,
    emit_payload,
    measure_project,
    prepare_reset,
    play_pi,
    label_prefix,
    wait_reset_ringdown=None,
):
    park_up()
    emit_payload()
    measure_project(payload_calibration, "payload")
    prog.memw(page, regs["i"], regs["address"])
    prog.mathi(page, regs["address"], regs["address"], "+", 1)
    prog.memw(page, regs["q"], regs["address"])
    prog.mathi(page, regs["address"], regs["address"], "+", 1)
    scheme = str(reset_scheme).strip().lower()
    if scheme == "opx_unbounded":
        prepare_reset()
        emit_unbounded_reset_state_machine(
            prog,
            page=page,
            regs=regs,
            payload_calibration=payload_calibration,
            loop_calibration=loop_calibration,
            measure_next=lambda: measure_project(loop_calibration, "loop"),
            play_pi=play_pi,
            label_prefix=label_prefix,
            wait_reset_ringdown=wait_reset_ringdown,
        )
    elif scheme != "none":
        raise ValueError("reset_scheme must be 'opx_unbounded' or 'none'")
    park_down()


def emit_tls_memory_sequence(
    *,
    sequence,
    prepare_excited,
    play_excursion,
    wait_storage,
    idle_excursion,
    do_prepare=True,
):
    sequence = str(sequence).strip().lower()
    if sequence not in TLS_MEMORY_SEQUENCES:
        raise ValueError(
            f"memory sequence must be one of {TLS_MEMORY_SEQUENCES}"
        )
    if bool(do_prepare) and sequence != "ground_double":
        prepare_excited()
    play_excursion()
    wait_storage()
    if sequence in ("double", "ground_double"):
        play_excursion()
    else:
        idle_excursion()


def emit_shot_major_payload_loops(
    prog,
    *,
    page,
    shot_register,
    point_register,
    done_register,
    done_address,
    shots,
    points,
    initialize_point,
    emit_point,
    advance_point,
    shot_label,
    point_label,
    finish_point=None,
    finish_shot=None,
):
    shots = int(shots)
    points = int(points)
    if shots <= 0 or points <= 0:
        raise ValueError("shot-major payload loops need positive shots and points")
    prog.regwi(page, done_register, 0)
    prog.memwi(page, done_register, done_address)
    prog.regwi(page, shot_register, shots - 1)
    prog.label(shot_label)
    initialize_point()
    prog.regwi(page, point_register, points - 1)
    prog.label(point_label)
    emit_point()
    prog.mathi(page, done_register, done_register, "+", 1)
    prog.memwi(page, done_register, done_address)
    if finish_point is not None:
        finish_point()
    advance_point()
    prog.loopnz(page, point_register, point_label)
    if finish_shot is not None:
        finish_shot()
    prog.loopnz(page, shot_register, shot_label)


def emit_reference_flux_cycle(
    *,
    enabled,
    play_excursion,
    wait_hold,
    play_park,
    wait_settle,
):
    if not bool(enabled):
        return
    play_excursion()
    wait_hold()
    play_park()
    wait_settle()


def emit_hard_flux_excursion(
    *,
    play_target,
    wait_target_settle,
    emit_at_target,
    wait_hold,
    play_park,
    wait_park_settle,
):
    play_target()
    wait_target_settle()
    emit_at_target()
    wait_hold()
    play_park()
    wait_park_settle()


def emit_park_history_probe(
    *,
    play_target,
    wait_target_settle,
    wait_hold,
    play_park,
    wait_recovery,
    emit_payload,
):
    play_target()
    wait_target_settle()
    wait_hold()
    play_park()
    wait_recovery()
    emit_payload()


def _declare_common(prog):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import (
        add_qubit_gaussian,
        set_readout_pulse,
    )

    cfg = prog.cfg
    ro_ch = int(cfg["ro_chs"][0])
    prog.declare_gen(
        ch=cfg["res_ch"],
        nqz=cfg["nqz"],
        mixer_freq=cfg.get("mixer_freq", 0),
        ro_ch=ro_ch,
    )
    prog.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
    ff_pulse.declare_park_hold(prog)
    for channel in cfg["ro_chs"]:
        prog.declare_readout(
            ch=channel,
            freq=cfg["read_pulse_freq"],
            length=prog.us2cycles(cfg["read_length"], ro_ch=ro_ch),
            gen_ch=cfg["res_ch"],
        )
    add_qubit_gaussian(prog)
    qubit_freq = prog.freq2reg(
        cfg.get("qubit_pi_freq", cfg["qubit_freq"]), gen_ch=cfg["qubit_ch"]
    )
    prog.set_pulse_registers(
        ch=cfg["qubit_ch"],
        style="arb",
        freq=qubit_freq,
        phase=0,
        gain=int(cfg["qubit_pi_gain"]),
        waveform="qubit",
    )
    read_freq = prog.freq2reg(
        cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=ro_ch
    )
    set_readout_pulse(prog, read_freq)
    latch_us = max(float(cfg.get("opx_park_latch_us", 0.02)), 0.002)
    prog._opx_park_segments = ff_pulse.build_park_hold(prog, hold_us=latch_us)
    prog.synci(200)


def _pulse_pi_and_align(prog, delay_us=0.01):
    prog.pulse(ch=prog.cfg["qubit_ch"])
    prog.sync_all(prog.us2cycles(float(delay_us)))


def emit_timing_matched_reference_shot(
    *,
    context,
    prep_excited,
    measure,
    prepare_excited,
    wait_read_delay,
    wait_reset_ringdown,
    wait_reset_settle,
    wait_payload_alignment,
):
    context = str(context).lower()
    if context not in ("payload", "loop"):
        raise ValueError("opx_reference_context must be 'payload' or 'loop'")
    if context == "loop":
        measure()
        wait_read_delay()
        wait_reset_ringdown()
        if bool(prep_excited):
            prepare_excited()
        wait_reset_settle()
        measure()
        return
    if bool(prep_excited):
        prepare_excited()
        wait_payload_alignment()
    measure()


def reshape_interleaved_readouts(i_values, q_values, *, reps, readouts_per_rep):
    reps = int(reps)
    reads = int(readouts_per_rep)
    if reps <= 0 or reads <= 0:
        raise ValueError("reps and readouts_per_rep must be positive")
    usable = reps * reads
    outputs = []
    for values in (i_values, q_values):
        signed = np.asarray(
            [signed32(value) for value in np.asarray(values).ravel()],
            dtype=np.int64,
        )
        if signed.size < usable:
            raise ValueError(
                f"readout buffer has {signed.size} values but {usable} are required"
            )
        outputs.append(signed[:usable].reshape(reps, reads))
    return outputs[0], outputs[1]


class TimingMatchedReferenceProgram(AveragerProgram):
    """Fixed-shape reference acquisition for payload or in-loop timing."""

    def initialize(self):
        self.cfg.setdefault("reps", int(self.cfg.get("shots", 2000)))
        context = str(self.cfg.get("opx_reference_context", "payload")).lower()
        if context not in ("payload", "loop"):
            raise ValueError("opx_reference_context must be 'payload' or 'loop'")
        self.reference_context = context
        self.readouts_per_rep = 1 if context == "payload" else 2
        _declare_common(self)

    def _measure(self):
        self.measure(
            pulse_ch=self.cfg["res_ch"],
            adcs=self.cfg["ro_chs"],
            adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
            wait=True,
            syncdelay=None,
        )

    def _wait_read_delay(self):
        adc_end = int(max(self._adc_ts))
        delay = max(
            int(self.us2cycles(float(self.cfg.get("opx_read_delay_us", 2.0)))), 0
        )
        self.waiti(0, adc_end + delay)

    def body(self):
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse

        ff_pulse.play_park_up(self, self._opx_park_segments)
        emit_timing_matched_reference_shot(
            context=self.reference_context,
            prep_excited=bool(self.cfg.get("prep_excited", False)),
            measure=self._measure,
            prepare_excited=lambda: self.pulse(ch=self.cfg["qubit_ch"]),
            wait_read_delay=self._wait_read_delay,
            wait_reset_ringdown=lambda: self.sync_all(
                self.us2cycles(max(
                    float(self.cfg.get("opx_feedback_syncdelay_us", 2.0)),
                    float(self.cfg.get("opx_loop_recovery_us", 10.0)),
                ))
            ),
            wait_reset_settle=lambda: self.sync_all(
                self.us2cycles(float(self.cfg.get("opx_reset_settle_us", 0.05)))
            ),
            wait_payload_alignment=lambda: self.sync_all(self.us2cycles(0.01)),
        )
        ff_pulse.play_park_down(self, self._opx_park_segments)
        self.sync_all(self.us2cycles(float(self.cfg.get("relax_delay", 400.0))))

    def acquire_readouts(self, soc, load_pulses=True, progress=False, **kwargs):
        super().acquire(
            soc,
            readouts_per_experiment=self.readouts_per_rep,
            load_pulses=load_pulses,
            progress=progress,
            **kwargs,
        )
        return reshape_interleaved_readouts(
            self.di_buf[0],
            self.dq_buf[0],
            reps=self.cfg["reps"],
            readouts_per_rep=self.readouts_per_rep,
        )

    def acquire(self, soc, load_pulses=True, progress=False, **kwargs):
        i_reads, q_reads = self.acquire_readouts(
            soc,
            load_pulses=load_pulses,
            progress=progress,
            **kwargs,
        )
        return i_reads[:, -1], q_reads[:, -1]


class TimingMatchedReferenceDMemProgram(QickProgram):
    record_words = PAYLOAD_RECORD_WORDS
    decode_dmem_records = staticmethod(decode_payload_records)

    def __init__(self, soccfg, cfg):
        super().__init__(soccfg)
        self.cfg = dict(cfg)
        self.reset_config = OPXResetConfig.from_mapping(self.cfg)
        self.reps = int(self.cfg.get("reps", self.cfg.get("shots", 1)))
        if self.reps <= 0:
            raise ValueError("reference reps must be positive")
        self.record_base = int(self.reset_config.record_base)
        self.done_addr = int(self.reset_config.done_addr)
        self.expts = None
        self.rounds = 1
        self.make_program()

    def _measure_raw(self):
        cfg = self.cfg
        ro_ch = int(cfg["ro_chs"][0])
        self.measure(
            pulse_ch=cfg["res_ch"],
            adcs=cfg["ro_chs"],
            adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
            wait=True,
            syncdelay=None,
        )
        adc_end = int(max(self._adc_ts))
        self.waiti(
            0,
            adc_end + max(
                int(self.us2cycles(float(self.reset_config.read_delay_us))), 0
            ),
        )
        tproc_ch = int(self.soccfg["readouts"][ro_ch].get("tproc_ch", -1))
        if tproc_ch < 0:
            raise RuntimeError(
                f"readout {ro_ch} has no tProc feedback path (tproc_ch={tproc_ch})"
            )
        self.read(tproc_ch, self.reset_page, "lower", self.reset_regs["i"])
        self.read(tproc_ch, self.reset_page, "upper", self.reset_regs["q"])

    def _park_up(self):
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse

        if self.reset_config.hard_flux_steps:
            ff_pulse.play_hard_step(self, self.cfg.get("ff_park_gain", 0))
            return
        ff_pulse.play_park_up(self, self._opx_park_segments)

    def _park_down(self):
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse

        if self.reset_config.hard_flux_steps:
            ff_pulse.play_hard_step(self, 0)
            return
        ff_pulse.play_park_down(self, self._opx_park_segments)

    def _emit_reference(self):
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse

        context = str(self.cfg.get("opx_reference_context", "payload")).lower()
        prep_excited = bool(self.cfg.get("prep_excited", False))
        if not self.reset_config.persistent_park:
            self._park_up()
        use_flux_cycle = bool(self.cfg.get("opx_reference_flux_cycle", False))
        if use_flux_cycle and not (
            self.reset_config.persistent_park and self.reset_config.hard_flux_steps
        ):
            raise ValueError(
                "opx_reference_flux_cycle requires persistent park and hard flux steps"
            )
        emit_reference_flux_cycle(
            enabled=use_flux_cycle,
            play_excursion=lambda: ff_pulse.play_hard_step(
                self, self.cfg["ff_gain"]
            ),
            wait_hold=lambda: self.sync_all(self.us2cycles(float(
                self.cfg.get("opx_reference_flux_hold_us", 1.0)
            ))),
            play_park=lambda: ff_pulse.play_hard_step(
                self, self.cfg.get("ff_park_gain", 0)
            ),
            wait_settle=lambda: self.sync_all(self.us2cycles(float(
                self.cfg.get(
                    "opx_reference_park_recovery_us",
                    self.cfg.get("flux_settle_time_us", 0.0),
                )
            ))),
        )
        if context == "loop":
            self._measure_raw()
            self.sync_all(self.us2cycles(max(
                float(self.reset_config.feedback_syncdelay_us),
                float(self.reset_config.loop_recovery_us),
            )))
            if prep_excited:
                self.pulse(ch=self.cfg["qubit_ch"])
            self.sync_all(self.us2cycles(float(self.reset_config.reset_settle_us)))
            self._measure_raw()
        elif context == "payload":
            if prep_excited:
                _pulse_pi_and_align(self)
            self._measure_raw()
        else:
            raise ValueError("opx_reference_context must be 'payload' or 'loop'")
        self.memw(self.reset_page, self.reset_regs["i"], self.reset_regs["address"])
        self.mathi(
            self.reset_page,
            self.reset_regs["address"],
            self.reset_regs["address"],
            "+",
            1,
        )
        self.memw(self.reset_page, self.reset_regs["q"], self.reset_regs["address"])
        self.mathi(
            self.reset_page,
            self.reset_regs["address"],
            self.reset_regs["address"],
            "+",
            1,
        )
        if not self.reset_config.persistent_park:
            self._park_down()
        self.sync_all(self.us2cycles(float(self.reset_config.inter_shot_delay_us)))

    def make_program(self):
        _declare_common(self)
        self.reset_page = self.ch_page(self.cfg["qubit_ch"])
        self.reset_regs = allocate_named_registers(
            self,
            self.reset_page,
            ("i", "q", "address"),
        )
        control_reserved = _reserved_registers(self, 0)
        if self.reset_page == 0:
            control_reserved.update(self.reset_regs.values())
        controls = allocate_named_registers(
            self,
            0,
            ("shot_loop", "done"),
            reserved=control_reserved,
        )
        self.regwi(
            self.reset_page,
            self.reset_regs["address"],
            self.record_base,
        )
        self.regwi(0, controls["done"], 0)
        self.memwi(0, controls["done"], self.done_addr)
        self.regwi(0, controls["shot_loop"], self.reps - 1)
        if self.reset_config.persistent_park:
            self._park_up()
            self.sync_all(self.us2cycles(float(self.reset_config.park_preroll_us)))
        self.label("OPX_REFERENCE_SHOT_LOOP")
        self._emit_reference()
        self.mathi(0, controls["done"], controls["done"], "+", 1)
        self.memwi(0, controls["done"], self.done_addr)
        self.loopnz(0, controls["shot_loop"], "OPX_REFERENCE_SHOT_LOOP")
        self.end()


class OPXResetBenchmarkProgram(QickProgram):
    """Variable-runtime tProc program with fixed-size per-shot DMem telemetry."""

    record_words = RECORD_WORDS

    def __init__(self, soccfg, cfg, payload_calibration, loop_calibration):
        super().__init__(soccfg)
        self.cfg = dict(cfg)
        self.reset_config = OPXResetConfig.from_mapping(self.cfg)
        self.payload_calibration = (
            payload_calibration
            if isinstance(payload_calibration, ClassifierCalibration)
            else ClassifierCalibration.from_dict(payload_calibration)
        )
        self.loop_calibration = (
            loop_calibration
            if isinstance(loop_calibration, ClassifierCalibration)
            else ClassifierCalibration.from_dict(loop_calibration)
        )
        self.reps = int(self.cfg.get("reps", self.cfg.get("shots", 1)))
        if self.reps <= 0:
            raise ValueError("reps must be positive")
        self.record_base = int(self.reset_config.record_base)
        self.done_addr = int(self.reset_config.done_addr)
        self.expts = None
        self.rounds = 1
        self.make_program()

    def _initialize_stream(
        self,
        controls,
        *,
        total_shots,
        records_per_shot,
        total_units,
        records_per_unit,
        prefix,
    ):
        if not bool(self.cfg.get("opx_resident_dmem_stream", False)):
            self.stream_plan = None
            return
        plan = resident_stream_plan(
            self.soccfg,
            done_addr=self.done_addr,
            record_base=self.record_base,
            record_words=self.record_words,
            records_per_unit=records_per_unit,
            total_units=total_units,
            records_per_shot=records_per_shot,
            total_shots=total_shots,
            ack_addr=int(self.cfg.get("opx_stream_ack_addr", 2)),
            ready_addr=int(self.cfg.get("opx_stream_ready_addr", 3)),
        )
        initialize_resident_stream(
            self,
            controls=controls,
            address_page=self.reset_page,
            address_register=self.reset_regs["address"],
            plan=plan,
            label_prefix=prefix,
        )

    def _stream_after_shot(self):
        if self.stream_plan is not None:
            emit_resident_stream_shot_boundary(self)

    def _finish_stream(self):
        if self.stream_plan is not None:
            emit_resident_stream_finish(self)

    def _measure_raw(self):
        cfg = self.cfg
        ro_ch = int(cfg["ro_chs"][0])
        self.measure(
            pulse_ch=cfg["res_ch"],
            adcs=cfg["ro_chs"],
            adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
            wait=True,
            syncdelay=None,
        )
        adc_end = int(max(self._adc_ts))
        read_delay = max(
            int(self.us2cycles(float(self.reset_config.read_delay_us))), 0
        )
        self.waiti(0, adc_end + read_delay)
        tproc_ch = int(self.soccfg["readouts"][ro_ch].get("tproc_ch", -1))
        if tproc_ch < 0:
            raise RuntimeError(
                f"readout {ro_ch} has no tProc feedback path (tproc_ch={tproc_ch})"
            )
        self.read(tproc_ch, self.reset_page, "lower", self.reset_regs["i"])
        self.read(tproc_ch, self.reset_page, "upper", self.reset_regs["q"])

    def _measure_project(self, calibration, context):
        if context == "loop":
            self.sync_all(self.us2cycles(float(self.reset_config.reset_settle_us)))
        self._measure_raw()
        plan = calibration.assembly_plan()
        self.mathi(
            self.reset_page,
            self.reset_regs["z"],
            self.reset_regs["i"],
            "*",
            int(plan["c_abs"]),
        )
        self.mathi(
            self.reset_page,
            self.reset_regs["status"],
            self.reset_regs["q"],
            "*",
            int(plan["s_abs"]),
        )
        self.math(
            self.reset_page,
            self.reset_regs["z"],
            self.reset_regs["z"],
            plan["combine_op"],
            self.reset_regs["status"],
        )

    def _wait_reset_ringdown(self):
        self.sync_all(self.us2cycles(max(
            float(self.reset_config.feedback_syncdelay_us),
            float(self.reset_config.loop_recovery_us),
        )))

    def _measure_verification(self):
        self.sync_all(self.us2cycles(float(self.reset_config.verification_delay_us)))
        self._measure_raw()
        self.sync_all(0)

    def _park_up(self):
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse

        if getattr(self.reset_config, "hard_flux_steps", False):
            ff_pulse.play_hard_step(self, self.cfg.get("ff_park_gain", 0))
            self.sync_all(self.us2cycles(float(self.cfg.get("ff_park_settle_us", 0.0))))
            return
        ff_pulse.play_park_up(self, self._opx_park_segments)

    def _park_down(self):
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse

        if getattr(self.reset_config, "hard_flux_steps", False):
            ff_pulse.play_hard_step(self, 0)
            return
        ff_pulse.play_park_down(self, self._opx_park_segments)

    def _refresh_park(self):
        self._park_down()
        self._park_up()

    def _shot_park_callbacks(self):
        if self.reset_config.persistent_park:
            if getattr(self.reset_config, "refresh_park_before_shot", False):
                return self._refresh_park, lambda: None
            return lambda: None, lambda: None
        return self._park_up, self._park_down

    def _begin_park_lifecycle(self):
        if self.reset_config.persistent_park:
            if getattr(self.reset_config, "hard_flux_steps", False):
                from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse

                ff_pulse.play_hard_step(self, self.cfg.get("ff_park_gain", 0))
                self.sync_all(self.us2cycles(float(
                    getattr(self.reset_config, "park_preroll_us", 0.0)
                )))
                return
            self._park_up()

    def _end_park_lifecycle(self):
        return None

    def _emit_body(self):
        preparation = int(bool(self.cfg.get("prep_excited", False)))
        park_up, park_down = self._shot_park_callbacks()
        emit_benchmark_shot(
            self,
            page=self.reset_page,
            regs=self.reset_regs,
            preparation=preparation,
            reset_scheme=self.cfg.get("opx_reset_scheme", "opx"),
            payload_calibration=self.payload_calibration,
            loop_calibration=self.loop_calibration,
            max_reset_attempts=self.reset_config.max_reset_attempts,
            park_up=park_up,
            park_down=park_down,
            prepare_excited=lambda: _pulse_pi_and_align(self),
            measure_project=self._measure_project,
            measure_verification=self._measure_verification,
            play_pi=lambda: self.pulse(ch=self.cfg["qubit_ch"]),
            label_prefix="OPX_RESET",
            wait_reset_ringdown=self._wait_reset_ringdown,
        )
        self.sync_all(self.us2cycles(float(self.reset_config.inter_shot_delay_us)))

    def _declare_experiment(self):
        return None

    def make_program(self):
        _declare_common(self)
        self._declare_experiment()
        self.reset_page = self.ch_page(self.cfg["qubit_ch"])
        self.reset_regs = allocate_registers(self, self.reset_page)
        control_reserved = _reserved_registers(self, 0)
        if self.reset_page == 0:
            control_reserved.update(self.reset_regs.values())
        controls = allocate_named_registers(
            self,
            0,
            resident_control_names(self.cfg, ("shot_loop", "done")),
            reserved=control_reserved,
        )
        self.regwi(
            self.reset_page,
            self.reset_regs["address"],
            self.record_base,
            "OPX DMem record address",
        )
        self.regwi(0, controls["done"], 0, "completed OPX shots")
        self.memwi(0, controls["done"], self.done_addr)
        self.regwi(0, controls["shot_loop"], self.reps - 1, "OPX shot loop")
        self._initialize_stream(
            controls,
            total_shots=self.reps,
            records_per_shot=1,
            total_units=self.reps,
            records_per_unit=1,
            prefix="OPX_STREAM",
        )
        self._begin_park_lifecycle()
        self.label("OPX_SHOT_LOOP")
        self._emit_body()
        self.mathi(0, controls["done"], controls["done"], "+", 1)
        self.memwi(0, controls["done"], self.done_addr)
        self._stream_after_shot()
        self.loopnz(0, controls["shot_loop"], "OPX_SHOT_LOOP")
        self._finish_stream()
        self._end_park_lifecycle()
        self.end()


class OPXResetT1Program(OPXResetBenchmarkProgram):
    def _set_payload_pulse(self):
        cfg = self.cfg
        frequency = cfg.get("qubit_pi_freq")
        if frequency is None:
            frequency = cfg["qubit_freq"]
        self.set_pulse_registers(
            ch=cfg["qubit_ch"],
            style="arb",
            freq=self.freq2reg(float(frequency), gen_ch=cfg["qubit_ch"]),
            phase=self.deg2reg(0.0, gen_ch=cfg["qubit_ch"]),
            gain=int(cfg["qubit_pi_gain"]),
            waveform="qubit",
        )

    def _set_reset_pulse(self):
        cfg = self.cfg
        frequency = cfg.get("reset_pi_freq")
        if frequency is None:
            frequency = cfg.get("qubit_pi_freq")
        if frequency is None:
            frequency = cfg["qubit_freq"]
        gain = cfg.get("reset_pi_gain")
        if gain is None:
            gain = cfg["qubit_pi_gain"]
        self.set_pulse_registers(
            ch=cfg["qubit_ch"],
            style="arb",
            freq=self.freq2reg(float(frequency), gen_ch=cfg["qubit_ch"]),
            phase=self.deg2reg(0.0, gen_ch=cfg["qubit_ch"]),
            gain=int(gain),
            waveform="qubit_reset",
        )

    def _prepare_excited(self):
        self._set_payload_pulse()
        _pulse_pi_and_align(self)

    def _declare_experiment(self):
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import add_qubit_gaussian

        cfg = self.cfg
        add_qubit_gaussian(
            self,
            name="qubit_reset",
            sigma_us=float(cfg.get("reset_pi_sigma", cfg["sigma"])),
            drag_beta=float(cfg.get(
                "reset_pi_drag_beta", cfg.get("qubit_drag_beta", 0.0))),
        )
        self._t1_do_ff = bool(cfg.get("do_ff", True))
        self._t1_hold_us = float(cfg.get("ff_hold", cfg.get("t1_wait_us", 0.01)))
        park_gain = float(cfg.get("ff_park_gain", 0) or 0)
        self._t1_stepping = self._t1_do_ff and abs(
            float(cfg.get("ff_gain", park_gain)) - park_gain
        ) > 0
        self._t1_ff_segments = None
        self._t1_ff_compensation = None
        self._t1_ff_settle_us = 0.0
        if self._t1_stepping:
            if not getattr(self, "do_park_hold", False):
                ff_pulse.declare_ff(self)
            self._t1_ff_settle_us = ff_pulse.flux_settle_us(cfg)
            self._t1_ff_compensation = ff_pulse.load_compensation(cfg)
            if not getattr(self.reset_config, "hard_flux_steps", False):
                self._t1_ff_segments = ff_pulse.build_ramp_hold_ramp(
                    self,
                    hold_us=self._t1_hold_us + self._t1_ff_settle_us,
                    ff_gain=cfg["ff_gain"],
                    dt_play_us=cfg.get("dt_pulseplay", 5.0),
                    ramp_us=cfg.get("ff_ramp_length", ff_pulse.STATE_SAFE_RAMP_US),
                    dt_def_us=cfg.get("dt_pulsedef", 0.002),
                    compensation=self._t1_ff_compensation,
                    distortion_model=ff_pulse.make_distortion_model(self),
                )

    def _wait_t1_payload(self, hold_us=None):
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse

        hold_us = self._t1_hold_us if hold_us is None else float(hold_us)
        if self._t1_stepping:
            if getattr(self.reset_config, "hard_flux_steps", False):
                if getattr(self, "_t1_ff_compensation", None) is not None:
                    park_gain = self.cfg.get("ff_park_gain", 0)
                    target_gain = self.cfg["ff_gain"]
                    ff_pulse.play_compensated_hard_step(
                        self,
                        park_gain,
                        target_gain,
                        max(hold_us, 0.01) + self._t1_ff_settle_us,
                        self._t1_ff_compensation,
                        restore_target_at_end=False,
                    )
                    ff_pulse.play_compensated_hard_step(
                        self,
                        target_gain,
                        park_gain,
                        self._t1_ff_settle_us,
                        self._t1_ff_compensation,
                    )
                    return
                ff_pulse.play_hard_step(self, self.cfg["ff_gain"])
                self.sync_all(self.us2cycles(self._t1_ff_settle_us))
                self.sync_all(self.us2cycles(max(hold_us, 0.01)))
                ff_pulse.play_hard_step(self, self.cfg.get("ff_park_gain", 0))
                self.sync_all(self.us2cycles(self._t1_ff_settle_us))
                return
            ff_pulse.play_ramp_up_hold(
                self,
                self._t1_ff_segments,
                dt_play_us=self.cfg.get("dt_pulseplay", 5.0),
            )
            self.sync_all(self.us2cycles(0.01))
            ff_pulse.play_ramp_down(self, self._t1_ff_segments)
            self.sync_all(self.us2cycles(self._t1_ff_settle_us))
        else:
            self.sync_all(
                self.us2cycles(max(hold_us, 0.01))
            )

    def _emit_body(self):
        park_up, park_down = self._shot_park_callbacks()
        emit_t1_shot(
            self,
            page=self.reset_page,
            regs=self.reset_regs,
            reset_scheme=self.cfg.get("opx_reset_scheme", "opx_unbounded"),
            payload_calibration=self.payload_calibration,
            loop_calibration=self.loop_calibration,
            park_up=park_up,
            park_down=park_down,
            prepare_excited=self._prepare_excited,
            wait_payload=self._wait_t1_payload,
            measure_project=self._measure_project,
            prepare_reset=self._set_reset_pulse,
            play_pi=lambda: self.pulse(ch=self.cfg["qubit_ch"]),
            label_prefix="OPX_T1_RESET",
            do_prepare=bool(self.cfg.get("do_pi", True)),
            wait_diagnostic_hold=lambda: self.sync_all(
                self.us2cycles(float(self.cfg.get("opx_diagnostic_hold_us", 65.1)))
            ),
            diagnostic_cycles=int(self.cfg.get("opx_diagnostic_cycles", 2)),
            wait_reset_ringdown=self._wait_reset_ringdown,
        )
        self.sync_all(self.us2cycles(float(self.reset_config.inter_shot_delay_us)))


class OPXResetT1SweepProgram(OPXResetT1Program):
    record_words = PAYLOAD_RECORD_WORDS
    decode_dmem_records = staticmethod(decode_payload_records)

    def __init__(self, soccfg, cfg, payload_calibration, loop_calibration):
        run_cfg = dict(cfg)
        delays = np.asarray(run_cfg.get("opx_t1_delays_us", ()), dtype=float)
        if delays.ndim != 1 or delays.size == 0:
            raise ValueError("opx_t1_delays_us must be a nonempty vector")
        if not np.all(np.isfinite(delays)) or np.any(delays < 0.01):
            raise ValueError("opx_t1_delays_us must be finite and at least 0.01 us")
        shots = int(run_cfg.get("opx_t1_shots", 0))
        if shots <= 0:
            raise ValueError("opx_t1_shots must be positive")
        run_cfg["opx_t1_delays_us"] = delays.tolist()
        run_cfg["reps"] = shots * int(delays.size)
        super().__init__(soccfg, run_cfg, payload_calibration, loop_calibration)

    def _emit_t1_point(self, point_index, delay_us):
        park_up, park_down = self._shot_park_callbacks()

        def emit_payload():
            if bool(self.cfg.get("do_pi", True)):
                self._prepare_excited()
            self._wait_t1_payload(delay_us)

        emit_payload_reset_shot(
            self,
            page=self.reset_page,
            regs=self.reset_regs,
            reset_scheme=self.cfg.get("opx_reset_scheme", "opx_unbounded"),
            payload_calibration=self.payload_calibration,
            loop_calibration=self.loop_calibration,
            park_up=park_up,
            park_down=park_down,
            emit_payload=emit_payload,
            measure_project=self._measure_project,
            prepare_reset=self._set_reset_pulse,
            play_pi=lambda: self.pulse(ch=self.cfg["qubit_ch"]),
            label_prefix=f"OPX_T1_SWEEP_{int(point_index)}",
            wait_reset_ringdown=self._wait_reset_ringdown,
        )
        self.sync_all(self.us2cycles(float(self.reset_config.inter_shot_delay_us)))

    def make_program(self):
        _declare_common(self)
        self._declare_experiment()
        if self._t1_stepping and not getattr(
            self.reset_config, "hard_flux_steps", False
        ):
            raise ValueError("shot-major T1 flux sweeps require hard flux steps")
        self.reset_page = self.ch_page(self.cfg["qubit_ch"])
        names = (
            "i",
            "q",
            "z",
            "ground",
            "excited",
            "attempts",
            "pi_count",
            "status",
            "address",
        )
        self.reset_regs = allocate_named_registers(self, self.reset_page, names)
        control_reserved = _reserved_registers(self, 0)
        if self.reset_page == 0:
            control_reserved.update(self.reset_regs.values())
        controls = allocate_named_registers(
            self,
            0,
            resident_control_names(self.cfg, ("shot_loop", "done")),
            reserved=control_reserved,
        )
        self.regwi(
            self.reset_page,
            self.reset_regs["address"],
            self.record_base,
            "OPX T1 sweep record address",
        )
        self.regwi(0, controls["done"], 0)
        self.memwi(0, controls["done"], self.done_addr)
        self.regwi(0, controls["shot_loop"], int(self.cfg["opx_t1_shots"]) - 1)
        self._initialize_stream(
            controls,
            total_shots=int(self.cfg["opx_t1_shots"]),
            records_per_shot=len(self.cfg["opx_t1_delays_us"]),
            total_units=(
                int(self.cfg["opx_t1_shots"])
                * len(self.cfg["opx_t1_delays_us"])
            ),
            records_per_unit=1,
            prefix="OPX_T1_SWEEP_STREAM",
        )
        self._begin_park_lifecycle()
        self.label("OPX_T1_SWEEP_SHOT_LOOP")
        for point_index, delay_us in enumerate(self.cfg["opx_t1_delays_us"]):
            self._emit_t1_point(point_index, float(delay_us))
            self.mathi(0, controls["done"], controls["done"], "+", 1)
            self.memwi(0, controls["done"], self.done_addr)
            self._stream_after_shot()
        self.loopnz(0, controls["shot_loop"], "OPX_T1_SWEEP_SHOT_LOOP")
        self._finish_stream()
        self._end_park_lifecycle()
        self.end()


class OPXResetT1FluxSweepProgram(OPXResetT1Program):
    record_words = PAYLOAD_RECORD_WORDS
    decode_dmem_records = staticmethod(decode_payload_records)

    def __init__(self, soccfg, cfg, payload_calibration, loop_calibration):
        run_cfg = dict(cfg)
        delays = np.asarray(run_cfg.get("opx_t1_delays_us", ()), dtype=float)
        if delays.ndim != 1 or delays.size == 0:
            raise ValueError("opx_t1_delays_us must be a nonempty vector")
        if not np.all(np.isfinite(delays)) or np.any(delays < 0.01):
            raise ValueError("opx_t1_delays_us must be finite and at least 0.01 us")
        gains = np.asarray(run_cfg.get("opx_t1_dc_gains", ()), dtype=float)
        if gains.ndim != 1 or gains.size == 0:
            raise ValueError("opx_t1_dc_gains must be a nonempty vector")
        rounded = np.rint(gains).astype(np.int64)
        if not np.allclose(gains, rounded, rtol=0.0, atol=1e-9):
            raise ValueError("opx_t1_dc_gains must contain integer DAC values")
        if np.any(rounded < -32768) or np.any(rounded > 32767):
            raise ValueError("opx_t1_dc_gains exceed the signed DAC range")
        steps = np.diff(rounded)
        if steps.size and not np.all(steps == steps[0]):
            raise ValueError("opx_t1_dc_gains must be evenly spaced")
        shots = int(run_cfg.get("opx_t1_shots", 0))
        if shots <= 0:
            raise ValueError("opx_t1_shots must be positive")
        park_gain = int(round(float(run_cfg.get("ff_park_gain", 0) or 0)))
        representative_gain = next(
            (int(gain) for gain in rounded if int(gain) != park_gain),
            park_gain - 1 if park_gain == 32767 else park_gain + 1,
        )
        run_cfg.update({
            "opx_t1_delays_us": delays.tolist(),
            "opx_t1_dc_gains": rounded.tolist(),
            "ff_gain": representative_gain,
            "ff_hold": float(np.max(delays)),
            "t1_wait_us": float(np.max(delays)),
            "do_ff": True,
            "reps": shots * int(rounded.size) * int(delays.size),
        })
        super().__init__(soccfg, run_cfg, payload_calibration, loop_calibration)

    def _play_dynamic_target(self):
        write_dynamic_const_gain(
            self,
            page=self._t1_flux_ff_page,
            channel=self.cfg["ff_ch"],
            value_register=self._t1_flux_regs["dc_gain"],
            scratch_register=self._t1_flux_regs["command"],
        )
        self.pulse(ch=self.cfg["ff_ch"])

    def _play_dynamic_compensation_segment(self, multiplier, duration_us, returning=False):
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse

        page = self._t1_flux_ff_page
        regs = self._t1_flux_regs
        factor = float(multiplier) - 1.0
        factor_fixed = int(round(abs(factor) * (1 << 16)))
        base_register = regs["park_gain"] if returning else regs["dc_gain"]
        if factor_fixed:
            self.mathi(page, regs["command"], regs["dc_delta"], "*", factor_fixed)
            self.bitwi(page, regs["command"], regs["command"], ">>", 16)
            correction_sign = self._t1_flux_direction * (1 if factor > 0 else -1)
            if returning:
                correction_sign *= -1
            self.math(
                page,
                regs["command"],
                base_register,
                "+" if correction_sign > 0 else "-",
                regs["command"],
            )
        else:
            self.mathi(page, regs["command"], base_register, "+", 0)
        total = max(int(self.us2cycles(duration_us, gen_ch=self.cfg["ff_ch"])), 3)
        chunk_count = max(1, (total + ff_pulse._MAX_CONST_LEN - 1) // ff_pulse._MAX_CONST_LEN)
        base, extra = divmod(total, chunk_count)
        for chunk in range(chunk_count):
            length = max(base + (1 if chunk < extra else 0), 3)
            self.set_pulse_registers(
                ch=self.cfg["ff_ch"],
                freq=0,
                style="const",
                phase=0,
                stdysel="last",
                gain=0,
                length=length,
            )
            write_dynamic_const_gain(
                self,
                page=page,
                channel=self.cfg["ff_ch"],
                value_register=regs["command"],
            )
            self.pulse(ch=self.cfg["ff_ch"])

    def _play_dynamic_compensated_hold(self, delay_us):
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse

        target_hold = max(float(delay_us), 0.01) + self._t1_ff_settle_us
        for multiplier, duration in ff_pulse.compensation_hold_segments(
            self._t1_ff_compensation, target_hold
        ):
            self._play_dynamic_compensation_segment(multiplier, duration)
        for multiplier, duration in ff_pulse.compensation_hold_segments(
            self._t1_ff_compensation, self._t1_ff_settle_us
        ):
            self._play_dynamic_compensation_segment(
                multiplier, duration, returning=True
            )
        ff_pulse.play_hard_step(self, self.cfg.get("ff_park_gain", 0))

    def _emit_t1_flux_point(self, point_index, delay_us):
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse

        park_up, park_down = self._shot_park_callbacks()

        def emit_payload():
            if bool(self.cfg.get("do_pi", True)):
                self._prepare_excited()
            if self._t1_ff_compensation is not None:
                self._play_dynamic_compensated_hold(delay_us)
                return
            self._play_dynamic_target()
            self.sync_all(self.us2cycles(self._t1_ff_settle_us))
            self.sync_all(self.us2cycles(max(float(delay_us), 0.01)))
            ff_pulse.play_hard_step(self, self.cfg.get("ff_park_gain", 0))
            self.sync_all(self.us2cycles(self._t1_ff_settle_us))

        emit_payload_reset_shot(
            self,
            page=self.reset_page,
            regs=self.reset_regs,
            reset_scheme=self.cfg.get("opx_reset_scheme", "opx_unbounded"),
            payload_calibration=self.payload_calibration,
            loop_calibration=self.loop_calibration,
            park_up=park_up,
            park_down=park_down,
            emit_payload=emit_payload,
            measure_project=self._measure_project,
            prepare_reset=self._set_reset_pulse,
            play_pi=lambda: self.pulse(ch=self.cfg["qubit_ch"]),
            label_prefix=f"OPX_T1_FLUX_T{int(point_index)}",
            wait_reset_ringdown=self._wait_reset_ringdown,
        )
        self.sync_all(self.us2cycles(float(self.reset_config.inter_shot_delay_us)))

    def make_program(self):
        _declare_common(self)
        self._declare_experiment()
        if not getattr(self.reset_config, "hard_flux_steps", False):
            raise ValueError("QUA-order T1 flux sweeps require hard flux steps")
        self.reset_page = self.ch_page(self.cfg["qubit_ch"])
        names = (
            "i",
            "q",
            "z",
            "ground",
            "excited",
            "attempts",
            "pi_count",
            "status",
            "address",
        )
        self.reset_regs = allocate_named_registers(self, self.reset_page, names)
        self._t1_flux_ff_page = self.ch_page(self.cfg["ff_ch"])
        ff_reserved = _reserved_registers(self, self._t1_flux_ff_page)
        if self._t1_flux_ff_page == self.reset_page:
            ff_reserved.update(self.reset_regs.values())
        self._t1_flux_regs = allocate_named_registers(
            self,
            self._t1_flux_ff_page,
            ("dc_gain", "dc_loop", "dc_delta", "park_gain", "command"),
            reserved=ff_reserved,
        )
        control_reserved = _reserved_registers(self, 0)
        if self.reset_page == 0:
            control_reserved.update(self.reset_regs.values())
        if self._t1_flux_ff_page == 0:
            control_reserved.update(self._t1_flux_regs.values())
        controls = allocate_named_registers(
            self,
            0,
            resident_control_names(self.cfg, ("shot_loop", "done")),
            reserved=control_reserved,
        )
        gains = self.cfg["opx_t1_dc_gains"]
        gain_step = int(gains[1] - gains[0]) if len(gains) > 1 else 0
        self.regwi(self.reset_page, self.reset_regs["address"], self.record_base)
        self.regwi(0, controls["done"], 0)
        self.memwi(0, controls["done"], self.done_addr)
        self.regwi(0, controls["shot_loop"], int(self.cfg["opx_t1_shots"]) - 1)
        self._initialize_stream(
            controls,
            total_shots=int(self.cfg["opx_t1_shots"]),
            records_per_shot=len(gains) * len(self.cfg["opx_t1_delays_us"]),
            total_units=(
                int(self.cfg["opx_t1_shots"])
                * len(gains)
                * len(self.cfg["opx_t1_delays_us"])
            ),
            records_per_unit=1,
            prefix="OPX_T1_FLUX_STREAM",
        )
        self._begin_park_lifecycle()
        self.label("OPX_T1_FLUX_SHOT_LOOP")
        self.safe_regwi(
            self._t1_flux_ff_page,
            self._t1_flux_regs["dc_gain"],
            int(gains[0]),
        )
        park_gain = int(round(float(self.cfg.get("ff_park_gain", 0) or 0)))
        self.safe_regwi(
            self._t1_flux_ff_page,
            self._t1_flux_regs["park_gain"],
            park_gain,
        )
        directions = {
            int(np.sign(int(gain) - park_gain))
            for gain in gains
            if int(gain) != park_gain
        }
        if len(directions) > 1 and self._t1_ff_compensation is not None:
            raise ValueError(
                "compensated T1 flux sweeps cannot cross ff_park_gain in one program"
            )
        self._t1_flux_direction = next(iter(directions), 1)
        self.regwi(
            self._t1_flux_ff_page,
            self._t1_flux_regs["dc_loop"],
            len(gains) - 1,
        )
        self.label("OPX_T1_FLUX_DC_LOOP")
        if self._t1_flux_direction > 0:
            self.math(
                self._t1_flux_ff_page,
                self._t1_flux_regs["dc_delta"],
                self._t1_flux_regs["dc_gain"],
                "-",
                self._t1_flux_regs["park_gain"],
            )
        else:
            self.math(
                self._t1_flux_ff_page,
                self._t1_flux_regs["dc_delta"],
                self._t1_flux_regs["park_gain"],
                "-",
                self._t1_flux_regs["dc_gain"],
            )
        for point_index, delay_us in enumerate(self.cfg["opx_t1_delays_us"]):
            self._emit_t1_flux_point(point_index, float(delay_us))
            self.mathi(0, controls["done"], controls["done"], "+", 1)
            self.memwi(0, controls["done"], self.done_addr)
            self._stream_after_shot()
        self.mathi(
            self._t1_flux_ff_page,
            self._t1_flux_regs["dc_gain"],
            self._t1_flux_regs["dc_gain"],
            "+",
            gain_step,
        )
        self.loopnz(
            self._t1_flux_ff_page,
            self._t1_flux_regs["dc_loop"],
            "OPX_T1_FLUX_DC_LOOP",
        )
        self.loopnz(0, controls["shot_loop"], "OPX_T1_FLUX_SHOT_LOOP")
        self._finish_stream()
        self._end_park_lifecycle()
        self.end()


class OPXResetT13PointProgram(OPXResetT1Program):
    record_words = PAYLOAD_RECORD_WORDS
    decode_dmem_records = staticmethod(decode_payload_records)

    def __init__(self, soccfg, cfg, payload_calibration, loop_calibration):
        run_cfg = dict(cfg)
        gains = np.asarray(run_cfg.get("opx_t1_3pt_dc_gains", ()), dtype=float)
        if gains.ndim != 1 or gains.size == 0:
            raise ValueError("opx_t1_3pt_dc_gains must be a nonempty vector")
        if not np.all(np.isfinite(gains)):
            raise ValueError("opx_t1_3pt_dc_gains must be finite")
        rounded = np.rint(gains).astype(np.int64)
        if not np.allclose(gains, rounded, rtol=0.0, atol=1e-9):
            raise ValueError("opx_t1_3pt_dc_gains must contain integer DAC values")
        if np.any(rounded < -32768) or np.any(rounded > 32767):
            raise ValueError("opx_t1_3pt_dc_gains exceed the signed DAC range")
        steps = np.diff(rounded)
        if steps.size and not np.all(steps == steps[0]):
            raise ValueError("opx_t1_3pt_dc_gains must be evenly spaced")
        shots = int(run_cfg.get("opx_t1_3pt_shots", 0))
        wait_us = float(run_cfg.get("opx_t1_3pt_wait_us", 0.0))
        if shots <= 0:
            raise ValueError("opx_t1_3pt_shots must be positive")
        if not np.isfinite(wait_us) or wait_us < 0.01:
            raise ValueError("opx_t1_3pt_wait_us must be at least 0.01 us")
        park_gain = int(round(float(run_cfg.get("ff_park_gain", 0) or 0)))
        representative_gain = next(
            (int(gain) for gain in rounded if int(gain) != park_gain),
            park_gain - 1 if park_gain == 32767 else park_gain + 1,
        )
        run_cfg.update({
            "opx_t1_3pt_dc_gains": rounded.tolist(),
            "ff_gain": representative_gain,
            "ff_hold": wait_us,
            "t1_wait_us": wait_us,
            "do_ff": True,
            "reps": shots * int(rounded.size) * 3,
        })
        super().__init__(soccfg, run_cfg, payload_calibration, loop_calibration)

    def _play_dynamic_target(self):
        write_dynamic_const_gain(
            self,
            page=self._t1_3pt_ff_page,
            channel=self.cfg["ff_ch"],
            value_register=self._t1_3pt_regs["dc_gain"],
            scratch_register=self._t1_3pt_regs["command"],
        )
        self.pulse(ch=self.cfg["ff_ch"])

    def _wait_three_point_payload(self, hold_us, do_ff):
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse

        if not bool(do_ff):
            if float(hold_us) > 0:
                self.sync_all(self.us2cycles(float(hold_us)))
            return
        if getattr(self, "_t1_ff_compensation", None) is not None:
            OPXResetT1FluxSweepProgram._play_dynamic_compensated_hold(
                self, hold_us
            )
            return
        self._play_dynamic_target()
        self.sync_all(self.us2cycles(self._t1_ff_settle_us))
        self.sync_all(self.us2cycles(max(float(hold_us), 0.01)))
        ff_pulse.play_hard_step(self, self.cfg.get("ff_park_gain", 0))
        self.sync_all(self.us2cycles(self._t1_ff_settle_us))

    def _emit_three_point_payload(self, label, do_pi, do_ff, hold_us):
        park_up, park_down = self._shot_park_callbacks()

        def emit_payload():
            if bool(do_pi):
                self._prepare_excited()
            self._wait_three_point_payload(hold_us, do_ff)

        emit_payload_reset_shot(
            self,
            page=self.reset_page,
            regs=self.reset_regs,
            reset_scheme=self.cfg.get("opx_reset_scheme", "opx_unbounded"),
            payload_calibration=self.payload_calibration,
            loop_calibration=self.loop_calibration,
            park_up=park_up,
            park_down=park_down,
            emit_payload=emit_payload,
            measure_project=self._measure_project,
            prepare_reset=self._set_reset_pulse,
            play_pi=lambda: self.pulse(ch=self.cfg["qubit_ch"]),
            label_prefix=label,
            wait_reset_ringdown=self._wait_reset_ringdown,
        )
        self.sync_all(self.us2cycles(float(self.reset_config.inter_shot_delay_us)))

    def make_program(self):
        _declare_common(self)
        self._declare_experiment()
        if not getattr(self.reset_config, "hard_flux_steps", False):
            raise ValueError("QUA-order three-point T1 requires hard flux steps")
        self.reset_page = self.ch_page(self.cfg["qubit_ch"])
        names = (
            "i",
            "q",
            "z",
            "ground",
            "excited",
            "attempts",
            "pi_count",
            "status",
            "address",
        )
        self.reset_regs = allocate_named_registers(self, self.reset_page, names)
        self._t1_3pt_ff_page = self.ch_page(self.cfg["ff_ch"])
        ff_reserved = _reserved_registers(self, self._t1_3pt_ff_page)
        if self._t1_3pt_ff_page == self.reset_page:
            ff_reserved.update(self.reset_regs.values())
        self._t1_3pt_regs = allocate_named_registers(
            self,
            self._t1_3pt_ff_page,
            ("dc_gain", "dc_loop", "dc_delta", "park_gain", "command"),
            reserved=ff_reserved,
        )
        self._t1_flux_ff_page = self._t1_3pt_ff_page
        self._t1_flux_regs = self._t1_3pt_regs
        self._play_dynamic_compensation_segment = (
            OPXResetT1FluxSweepProgram._play_dynamic_compensation_segment.__get__(
                self, type(self)
            )
        )
        control_reserved = _reserved_registers(self, 0)
        if self.reset_page == 0:
            control_reserved.update(self.reset_regs.values())
        if self._t1_3pt_ff_page == 0:
            control_reserved.update(self._t1_3pt_regs.values())
        controls = allocate_named_registers(
            self,
            0,
            resident_control_names(self.cfg, ("shot_loop", "done")),
            reserved=control_reserved,
        )
        gains = self.cfg["opx_t1_3pt_dc_gains"]
        gain_step = int(gains[1] - gains[0]) if len(gains) > 1 else 0
        self.regwi(self.reset_page, self.reset_regs["address"], self.record_base)
        self.regwi(0, controls["done"], 0)
        self.memwi(0, controls["done"], self.done_addr)
        self.regwi(
            0,
            controls["shot_loop"],
            int(self.cfg["opx_t1_3pt_shots"]) - 1,
        )
        self._initialize_stream(
            controls,
            total_shots=int(self.cfg["opx_t1_3pt_shots"]),
            records_per_shot=len(gains) * 3,
            total_units=int(self.cfg["opx_t1_3pt_shots"]) * len(gains),
            records_per_unit=3,
            prefix="OPX_T1_3PT_STREAM",
        )
        self._begin_park_lifecycle()
        self.label("OPX_T1_3PT_SHOT_LOOP")
        self.safe_regwi(
            self._t1_3pt_ff_page,
            self._t1_3pt_regs["dc_gain"],
            int(gains[0]),
        )
        park_gain = int(round(float(self.cfg.get("ff_park_gain", 0) or 0)))
        self.safe_regwi(
            self._t1_3pt_ff_page,
            self._t1_3pt_regs["park_gain"],
            park_gain,
        )
        directions = {
            int(np.sign(int(gain) - park_gain))
            for gain in gains
            if int(gain) != park_gain
        }
        if len(directions) > 1 and self._t1_ff_compensation is not None:
            raise ValueError(
                "compensated three-point T1 sweeps cannot cross ff_park_gain in one program"
            )
        self._t1_flux_direction = next(iter(directions), 1)
        self.regwi(
            self._t1_3pt_ff_page,
            self._t1_3pt_regs["dc_loop"],
            len(gains) - 1,
        )
        self.label("OPX_T1_3PT_DC_LOOP")
        if self._t1_flux_direction > 0:
            self.math(
                self._t1_3pt_ff_page,
                self._t1_3pt_regs["dc_delta"],
                self._t1_3pt_regs["dc_gain"],
                "-",
                self._t1_3pt_regs["park_gain"],
            )
        else:
            self.math(
                self._t1_3pt_ff_page,
                self._t1_3pt_regs["dc_delta"],
                self._t1_3pt_regs["park_gain"],
                "-",
                self._t1_3pt_regs["dc_gain"],
            )
        self._emit_three_point_payload("OPX_T1_3PT_P0", False, False, 0.0)
        self._emit_three_point_payload("OPX_T1_3PT_P1", True, False, 0.0)
        self._emit_three_point_payload(
            "OPX_T1_3PT_PS",
            True,
            True,
            float(self.cfg["opx_t1_3pt_wait_us"]),
        )
        self.mathi(0, controls["done"], controls["done"], "+", 3)
        self.memwi(0, controls["done"], self.done_addr)
        self._stream_after_shot()
        self.mathi(
            self._t1_3pt_ff_page,
            self._t1_3pt_regs["dc_gain"],
            self._t1_3pt_regs["dc_gain"],
            "+",
            gain_step,
        )
        self.loopnz(
            self._t1_3pt_ff_page,
            self._t1_3pt_regs["dc_loop"],
            "OPX_T1_3PT_DC_LOOP",
        )
        self.loopnz(0, controls["shot_loop"], "OPX_T1_3PT_SHOT_LOOP")
        self._finish_stream()
        self._end_park_lifecycle()
        self.end()


class OPXResetTLSMemoryProgram(OPXResetT1Program):
    record_words = PAYLOAD_RECORD_WORDS
    decode_dmem_records = staticmethod(decode_payload_records)

    def __init__(self, soccfg, cfg, payload_calibration, loop_calibration):
        run_cfg = dict(cfg)
        sequences = tuple(
            str(value).strip().lower()
            for value in run_cfg.get("opx_memory_sequences", ())
        )
        if not sequences:
            raise ValueError("opx_memory_sequences must be nonempty")
        invalid = [
            value for value in sequences if value not in TLS_MEMORY_SEQUENCES
        ]
        if invalid:
            raise ValueError(
                f"memory sequence must be one of {TLS_MEMORY_SEQUENCES}"
            )
        shots = int(run_cfg.get("opx_memory_shots", 0))
        warmup_shots = int(run_cfg.get("opx_memory_warmup_shots", 0))
        interaction_us = float(run_cfg.get("opx_memory_interaction_us", 0.0))
        storage_us = float(run_cfg.get("opx_memory_storage_us", 0.0))
        if shots <= 0:
            raise ValueError("opx_memory_shots must be positive")
        if warmup_shots < 0:
            raise ValueError("opx_memory_warmup_shots must be non-negative")
        if not np.isfinite(interaction_us) or interaction_us < 0.01:
            raise ValueError("opx_memory_interaction_us must be at least 0.01 us")
        if not np.isfinite(storage_us) or storage_us < 0.0:
            raise ValueError("opx_memory_storage_us must be non-negative")
        run_cfg.update({
            "opx_memory_sequences": list(sequences),
            "opx_memory_warmup_shots": warmup_shots,
            "ff_hold": interaction_us,
            "t1_wait_us": interaction_us,
            "do_ff": True,
            "reps": shots * len(sequences),
        })
        super().__init__(soccfg, run_cfg, payload_calibration, loop_calibration)

    def _idle_memory_excursion(self):
        duration_us = (
            2.0 * float(self._t1_ff_settle_us)
            + max(float(self.cfg["opx_memory_interaction_us"]), 0.01)
        )
        self.sync_all(self.us2cycles(duration_us))

    def _emit_memory_point(self, sequence, *, label_context, do_prepare):
        park_up, park_down = self._shot_park_callbacks()

        def emit_payload():
            emit_tls_memory_sequence(
                sequence=sequence,
                prepare_excited=self._prepare_excited,
                play_excursion=lambda: self._wait_t1_payload(
                    float(self.cfg["opx_memory_interaction_us"])
                ),
                wait_storage=lambda: self.sync_all(self.us2cycles(
                    float(self.cfg["opx_memory_storage_us"])
                )),
                idle_excursion=self._idle_memory_excursion,
                do_prepare=do_prepare,
            )

        emit_payload_reset_shot(
            self,
            page=self.reset_page,
            regs=self.reset_regs,
            reset_scheme="opx_unbounded",
            payload_calibration=self.payload_calibration,
            loop_calibration=self.loop_calibration,
            park_up=park_up,
            park_down=park_down,
            emit_payload=emit_payload,
            measure_project=self._measure_project,
            prepare_reset=self._set_reset_pulse,
            play_pi=lambda: self.pulse(ch=self.cfg["qubit_ch"]),
            label_prefix=(
                f"OPX_TLS_MEMORY_{label_context}_{sequence.upper()}"
            ),
            wait_reset_ringdown=self._wait_reset_ringdown,
        )
        self.sync_all(self.us2cycles(float(self.reset_config.inter_shot_delay_us)))

    def make_program(self):
        if not getattr(self.reset_config, "hard_flux_steps", False):
            raise ValueError("QUA-order TLS memory requires hard flux steps")
        _declare_common(self)
        self._declare_experiment()
        self.reset_page = self.ch_page(self.cfg["qubit_ch"])
        names = (
            "i",
            "q",
            "z",
            "ground",
            "excited",
            "attempts",
            "pi_count",
            "status",
            "address",
        )
        self.reset_regs = allocate_named_registers(
            self, self.reset_page, names
        )
        control_reserved = _reserved_registers(self, 0)
        if self.reset_page == 0:
            control_reserved.update(self.reset_regs.values())
        controls = allocate_named_registers(
            self,
            0,
            resident_control_names(
                self.cfg,
                ("shot_loop", "warmup_loop", "done"),
            ),
            reserved=control_reserved,
        )
        self.regwi(self.reset_page, self.reset_regs["address"], self.record_base)
        self.regwi(0, controls["done"], 0)
        self.memwi(0, controls["done"], self.done_addr)
        self.regwi(
            0,
            controls["shot_loop"],
            int(self.cfg["opx_memory_shots"]) - 1,
        )
        self._initialize_stream(
            controls,
            total_shots=int(self.cfg["opx_memory_shots"]),
            records_per_shot=len(self.cfg["opx_memory_sequences"]),
            total_units=(
                int(self.cfg["opx_memory_shots"])
                * len(self.cfg["opx_memory_sequences"])
            ),
            records_per_unit=1,
            prefix="OPX_TLS_MEMORY_STREAM",
        )
        self._begin_park_lifecycle()
        warmup_shots = int(self.cfg["opx_memory_warmup_shots"])
        if warmup_shots > 0:
            self.regwi(0, controls["warmup_loop"], warmup_shots - 1)
            self.label("OPX_TLS_MEMORY_WARMUP_LOOP")
            for sequence in self.cfg["opx_memory_sequences"]:
                self.regwi(
                    self.reset_page,
                    self.reset_regs["address"],
                    self.record_base,
                )
                self._emit_memory_point(
                    sequence,
                    label_context="WARMUP",
                    do_prepare=False,
                )
            self.loopnz(
                0,
                controls["warmup_loop"],
                "OPX_TLS_MEMORY_WARMUP_LOOP",
            )
            self.regwi(
                self.reset_page,
                self.reset_regs["address"],
                self.record_base,
            )
        self.label("OPX_TLS_MEMORY_SHOT_LOOP")
        for sequence in self.cfg["opx_memory_sequences"]:
            self._emit_memory_point(
                sequence,
                label_context="RECORDED",
                do_prepare=True,
            )
            self.mathi(0, controls["done"], controls["done"], "+", 1)
            self.memwi(0, controls["done"], self.done_addr)
            self._stream_after_shot()
        self.loopnz(0, controls["shot_loop"], "OPX_TLS_MEMORY_SHOT_LOOP")
        self._finish_stream()
        self._end_park_lifecycle()
        self.end()


class OPXResetPulseSweepProgram(OPXResetBenchmarkProgram):
    record_words = PAYLOAD_RECORD_WORDS
    decode_dmem_records = staticmethod(decode_payload_records)

    def __init__(self, soccfg, cfg, payload_calibration, loop_calibration):
        run_cfg = dict(cfg)
        shots = int(run_cfg.get("opx_payload_shots_per_expt", 0))
        expts = int(run_cfg.get("opx_payload_expts", 1))
        if shots <= 0 or expts <= 0:
            raise ValueError("payload shots and experiment count must be positive")
        run_cfg["reps"] = shots * expts
        super().__init__(soccfg, run_cfg, payload_calibration, loop_calibration)

    def _set_payload_pulse(self):
        cfg = self.cfg
        plan = self._payload_sweep_plan
        if plan["kind"] == "frequency":
            frequency_register = 0
            gain = int(getattr(self, "_payload_gain_dac", plan["fixed_gain"]))
        else:
            frequency_register = self.freq2reg(
                float(getattr(
                    self,
                    "_payload_frequency_mhz",
                    plan["fixed_frequency_mhz"],
                )),
                gen_ch=cfg["qubit_ch"],
            )
            gain = 0
        pulse = {
            "ch": cfg["qubit_ch"],
            "style": str(cfg.get("qubit_pulse_style", "arb")).lower(),
            "freq": frequency_register,
            "phase": self.deg2reg(
                float(cfg.get("opx_payload_phase_deg", 0.0)),
                gen_ch=cfg["qubit_ch"],
            ),
            "gain": gain,
        }
        if pulse["style"] == "arb":
            pulse["waveform"] = "qubit"
        elif pulse["style"] == "const":
            pulse["length"] = self.us2cycles(
                float(cfg["qubit_length"]), gen_ch=cfg["qubit_ch"]
            )
        else:
            raise ValueError(
                "OPX pulse-sweep reset requires an arb or const qubit pulse"
            )
        self.set_pulse_registers(
            **pulse,
        )
        self.mathi(
            self.reset_page,
            self.sreg(cfg["qubit_ch"], plan["target_register"]),
            self.reset_regs["payload_sweep"],
            "+",
            0,
        )

    def _set_reset_pulse(self):
        cfg = self.cfg
        self.set_pulse_registers(
            ch=cfg["qubit_ch"],
            style="arb",
            freq=self.freq2reg(
                float(cfg.get("reset_pi_freq", cfg.get(
                    "qubit_pi_freq", cfg["qubit_freq"]))),
                gen_ch=cfg["qubit_ch"],
            ),
            phase=self.deg2reg(0.0, gen_ch=cfg["qubit_ch"]),
            gain=int(cfg.get("reset_pi_gain", cfg["qubit_pi_gain"])),
            waveform="qubit_reset",
        )
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import set_readout_pulse

        set_readout_pulse(
            self,
            self._payload_read_freq_reg,
            gain=int(cfg.get("reset_read_pulse_gain", cfg["read_pulse_gain"])),
        )

    def _declare_experiment(self):
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import add_qubit_gaussian

        cfg = self.cfg
        if str(cfg.get("qubit_pulse_style", "arb")).lower() not in ("arb", "const"):
            raise ValueError(
                "OPX pulse-sweep reset requires an arb or const qubit pulse"
            )
        reset_read_frequency = float(cfg.get(
            "reset_read_pulse_freq", cfg["read_pulse_freq"]))
        if not np.isclose(
            reset_read_frequency,
            float(cfg["read_pulse_freq"]),
            rtol=0.0,
            atol=1e-9,
        ):
            raise ValueError("payload and reset readout frequencies must match")
        self._payload_shots = int(cfg["opx_payload_shots_per_expt"])
        self._payload_expts = int(cfg.get("opx_payload_expts", 1))
        self._payload_sweep_plan = payload_sweep_plan(
            cfg,
            freq2reg=lambda frequency: self.freq2reg(
                frequency, gen_ch=cfg["qubit_ch"]),
        )
        self._payload_pulses = int(cfg.get("opx_payload_pulses", 1))
        if self._payload_pulses < 0:
            raise ValueError("opx_payload_pulses must be non-negative")
        placement = str(cfg.get("opx_payload_pulse_placement", "excursion")).lower()
        if placement not in ("park", "excursion", "park_after_excursion"):
            raise ValueError(
                "opx_payload_pulse_placement must be 'park', 'excursion', "
                "or 'park_after_excursion'"
            )
        self._payload_pulse_placement = placement
        add_qubit_gaussian(
            self,
            name="qubit_reset",
            sigma_us=float(cfg.get("reset_pi_sigma", cfg["sigma"])),
            drag_beta=float(cfg.get(
                "reset_pi_drag_beta", cfg.get("qubit_drag_beta", 0.0))),
        )
        self._payload_read_freq_reg = self.freq2reg(
            cfg["read_pulse_freq"],
            gen_ch=cfg["res_ch"],
            ro_ch=cfg["ro_chs"][0],
        )
        self._payload_do_excursion = bool(cfg.get("opx_payload_do_excursion", False))
        self._payload_excursion_segments = None
        self._payload_hard_flux_steps = bool(
            self._payload_do_excursion
            and getattr(self.reset_config, "hard_flux_steps", False)
        )
        self._payload_flux_hold_us = float(
            cfg.get("opx_payload_flux_hold_us", 0.05)
        )
        self._payload_flux_settle_us = ff_pulse.flux_settle_us(cfg)
        self._payload_park_recovery_us = float(
            cfg.get("opx_payload_park_recovery_us", 0.0)
        )
        if (
            not np.isfinite(self._payload_park_recovery_us)
            or self._payload_park_recovery_us < 0
        ):
            raise ValueError("opx_payload_park_recovery_us must be non-negative")
        if self._payload_do_excursion:
            if not getattr(self, "do_park_hold", False):
                ff_pulse.declare_ff(self)
            if not bool(cfg.get("readout_after_park", True)):
                raise ValueError(
                    "OPX pulse-sweep reset requires readout_after_park=True"
                )
            if not self._payload_hard_flux_steps:
                self._payload_excursion_segments = ff_pulse.build_ramp_hold_ramp(
                    self,
                    hold_us=self._payload_flux_hold_us,
                    ff_gain=float(cfg["opx_payload_excursion_gain"]),
                    dt_play_us=cfg.get("dt_pulseplay", 5.0),
                    ramp_us=cfg.get("ff_ramp_length", ff_pulse.STATE_SAFE_RAMP_US),
                    dt_def_us=cfg.get("dt_pulsedef", 0.002),
                    compensation=ff_pulse.load_compensation(cfg),
                    distortion_model=ff_pulse.make_distortion_model(self),
                )
        if placement == "park_after_excursion":
            if not self._payload_do_excursion:
                raise ValueError(
                    "park_after_excursion requires opx_payload_do_excursion=True"
                )
            if not self._payload_hard_flux_steps:
                raise ValueError(
                    "park_after_excursion requires opx_hard_flux_steps=True"
                )

    def _emit_payload_pulses(self):
        cfg = self.cfg
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import set_readout_pulse

        set_readout_pulse(
            self,
            self._payload_read_freq_reg,
            gain=int(cfg["read_pulse_gain"]),
        )
        if bool(cfg.get("opx_payload_herald", False)):
            self._measure_raw()
            self.sync_all(self.us2cycles(float(cfg.get("herald_delay", 8.0))))
        self._set_payload_pulse()

        def emit_pulses():
            for _ in range(self._payload_pulses):
                self.pulse(ch=cfg["qubit_ch"])
                self.sync_all(self.us2cycles(0.01))

        if self._payload_pulse_placement == "park_after_excursion":
            emit_park_history_probe(
                play_target=lambda: ff_pulse.play_hard_step(
                    self, cfg["opx_payload_excursion_gain"]
                ),
                wait_target_settle=lambda: self.sync_all(
                    self.us2cycles(self._payload_flux_settle_us)
                ),
                wait_hold=lambda: self.sync_all(
                    self.us2cycles(max(self._payload_flux_hold_us, 0.01))
                ),
                play_park=lambda: ff_pulse.play_hard_step(
                    self, cfg.get("ff_park_gain", 0)
                ),
                wait_recovery=lambda: self.sync_all(
                    self.us2cycles(max(
                        self._payload_park_recovery_us,
                        self._payload_flux_settle_us,
                    ))
                ),
                emit_payload=emit_pulses,
            )
            return
        if self._payload_pulse_placement == "park":
            emit_pulses()
        if self._payload_hard_flux_steps:
            emit_hard_flux_excursion(
                play_target=lambda: ff_pulse.play_hard_step(
                    self, cfg["opx_payload_excursion_gain"]
                ),
                wait_target_settle=lambda: self.sync_all(
                    self.us2cycles(self._payload_flux_settle_us)
                ),
                emit_at_target=(
                    emit_pulses
                    if self._payload_pulse_placement == "excursion"
                    else lambda: None
                ),
                wait_hold=lambda: self.sync_all(
                    self.us2cycles(max(self._payload_flux_hold_us, 0.01))
                ),
                play_park=lambda: ff_pulse.play_hard_step(
                    self, cfg.get("ff_park_gain", 0)
                ),
                wait_park_settle=lambda: self.sync_all(
                    self.us2cycles(self._payload_flux_settle_us)
                ),
            )
            return
        if self._payload_do_excursion:
            ff_pulse.play_ramp_up_hold(
                self,
                self._payload_excursion_segments,
                dt_play_us=cfg.get("dt_pulseplay", 5.0),
            )
            self.sync_all(self.us2cycles(0.01))
        if self._payload_pulse_placement == "excursion":
            emit_pulses()
        if self._payload_do_excursion:
            ff_pulse.play_ramp_down(self, self._payload_excursion_segments)
            self.sync_all(self.us2cycles(ff_pulse.flux_settle_us(cfg)))

    def _emit_body(self):
        reset_scheme = str(
            self.cfg.get("opx_reset_scheme", "opx_unbounded")
        ).strip().lower()
        if reset_scheme == "none":
            passive_delay_us = float(
                self.cfg.get("qua_passive_pre_point_delay_us", 0.0)
            )
            if passive_delay_us > 0:
                self.sync_all(self.us2cycles(passive_delay_us))
        park_up, park_down = self._shot_park_callbacks()
        emit_payload_reset_shot(
            self,
            page=self.reset_page,
            regs=self.reset_regs,
            reset_scheme=reset_scheme,
            payload_calibration=self.payload_calibration,
            loop_calibration=self.loop_calibration,
            park_up=park_up,
            park_down=park_down,
            emit_payload=self._emit_payload_pulses,
            measure_project=self._measure_project,
            prepare_reset=self._set_reset_pulse,
            play_pi=lambda: self.pulse(ch=self.cfg["qubit_ch"]),
            label_prefix=getattr(
                self,
                "_payload_label_prefix",
                "OPX_PAYLOAD_RESET",
            ),
            wait_reset_ringdown=self._wait_reset_ringdown,
        )
        if reset_scheme != "none":
            self.sync_all(
                self.us2cycles(float(self.reset_config.inter_shot_delay_us))
            )

    def make_program(self):
        _declare_common(self)
        self._declare_experiment()
        self.reset_page = self.ch_page(self.cfg["qubit_ch"])
        names = (
            "i",
            "q",
            "z",
            "ground",
            "excited",
            "attempts",
            "pi_count",
            "status",
            "address",
            "payload_sweep",
        )
        self.reset_regs = allocate_named_registers(self, self.reset_page, names)
        control_reserved = _reserved_registers(self, 0)
        if self.reset_page == 0:
            control_reserved.update(self.reset_regs.values())
        controls = allocate_named_registers(
            self,
            0,
            resident_control_names(
                self.cfg,
                ("shot_loop", "expt_loop", "done"),
            ),
            reserved=control_reserved,
        )
        self.regwi(
            self.reset_page,
            self.reset_regs["address"],
            self.record_base,
            "OPX payload record address",
        )
        self._initialize_stream(
            controls,
            total_shots=self._payload_shots,
            records_per_shot=self._payload_expts,
            total_units=self._payload_shots * self._payload_expts,
            records_per_unit=1,
            prefix="OPX_PAYLOAD_STREAM",
        )
        self._begin_park_lifecycle()
        emit_shot_major_payload_loops(
            self,
            page=0,
            shot_register=controls["shot_loop"],
            point_register=controls["expt_loop"],
            done_register=controls["done"],
            done_address=self.done_addr,
            shots=self._payload_shots,
            points=self._payload_expts,
            initialize_point=lambda: initialize_payload_sweep_register(
                self,
                page=self.reset_page,
                register=self.reset_regs["payload_sweep"],
                value=self._payload_sweep_plan["start_register"],
            ),
            emit_point=self._emit_body,
            advance_point=lambda: self.mathi(
                self.reset_page,
                self.reset_regs["payload_sweep"],
                self.reset_regs["payload_sweep"],
                "+",
                int(self._payload_sweep_plan["step_register"]),
            ),
            shot_label="OPX_PAYLOAD_SHOT_LOOP",
            point_label="OPX_PAYLOAD_EXPT_LOOP",
            finish_point=self._stream_after_shot,
        )
        self._finish_stream()
        self._end_park_lifecycle()
        self.end()


class OPXResetPulseGridProgram(OPXResetPulseSweepProgram):
    def __init__(self, soccfg, cfg, payload_calibration, loop_calibration):
        run_cfg = dict(cfg)
        frequencies = np.asarray(
            run_cfg.get("opx_payload_frequencies_mhz", ()), dtype=float
        )
        if frequencies.ndim != 1 or frequencies.size == 0:
            raise ValueError("opx_payload_frequencies_mhz must be a nonempty vector")
        if not np.all(np.isfinite(frequencies)):
            raise ValueError("opx_payload_frequencies_mhz must be finite")
        frequency_steps = np.diff(frequencies)
        if frequency_steps.size and not np.allclose(
            frequency_steps,
            frequency_steps[0],
            rtol=0.0,
            atol=1e-9,
        ):
            raise ValueError("opx_payload_frequencies_mhz must be evenly spaced")
        gains = np.asarray(run_cfg.get("opx_payload_gains", ()), dtype=float)
        if gains.ndim != 1 or gains.size == 0:
            raise ValueError("opx_payload_gains must be a nonempty vector")
        rounded = np.rint(gains).astype(np.int64)
        if not np.allclose(gains, rounded, rtol=0.0, atol=1e-9):
            raise ValueError("opx_payload_gains must contain integer DAC values")
        steps = np.diff(rounded)
        if steps.size and not np.all(steps == steps[0]):
            raise ValueError("opx_payload_gains must be evenly spaced")
        shots = int(run_cfg.get("opx_payload_shots_per_expt", 0))
        if shots <= 0:
            raise ValueError("opx_payload_shots_per_expt must be positive")
        run_cfg.update({
            "opx_payload_frequencies_mhz": frequencies.tolist(),
            "opx_payload_gains": rounded.tolist(),
            "opx_payload_expts": int(frequencies.size),
            "opx_payload_frequency_start_mhz": float(frequencies[0]),
            "opx_payload_frequency_step_mhz": (
                float(frequency_steps[0]) if frequency_steps.size else 0.0
            ),
            "opx_payload_fixed_gain": int(rounded[0]),
            "opx_payload_sweep_kind": "frequency",
            "reps": shots * int(frequencies.size) * int(rounded.size),
        })
        OPXResetBenchmarkProgram.__init__(
            self,
            soccfg,
            run_cfg,
            payload_calibration,
            loop_calibration,
        )

    def make_program(self):
        _declare_common(self)
        self._declare_experiment()
        self.reset_page = self.ch_page(self.cfg["qubit_ch"])
        names = (
            "i",
            "q",
            "z",
            "ground",
            "excited",
            "attempts",
            "pi_count",
            "status",
            "address",
            "payload_sweep",
        )
        self.reset_regs = allocate_named_registers(self, self.reset_page, names)
        control_reserved = _reserved_registers(self, 0)
        if self.reset_page == 0:
            control_reserved.update(self.reset_regs.values())
        controls = allocate_named_registers(
            self,
            0,
            resident_control_names(
                self.cfg,
                ("shot_loop", "frequency_loop", "done"),
            ),
            reserved=control_reserved,
        )
        gains = self.cfg["opx_payload_gains"]
        self.regwi(self.reset_page, self.reset_regs["address"], self.record_base)
        self.regwi(0, controls["done"], 0)
        self.memwi(0, controls["done"], self.done_addr)
        self.regwi(
            0,
            controls["shot_loop"],
            int(self.cfg["opx_payload_shots_per_expt"]) - 1,
        )
        self._initialize_stream(
            controls,
            total_shots=int(self.cfg["opx_payload_shots_per_expt"]),
            records_per_shot=(
                len(self.cfg["opx_payload_frequencies_mhz"])
                * len(gains)
            ),
            total_units=(
                int(self.cfg["opx_payload_shots_per_expt"])
                * len(self.cfg["opx_payload_frequencies_mhz"])
                * len(gains)
            ),
            records_per_unit=1,
            prefix="OPX_PAYLOAD_GRID_STREAM",
        )
        self._begin_park_lifecycle()
        self.label("OPX_PAYLOAD_GRID_SHOT_LOOP")
        initialize_payload_sweep_register(
            self,
            page=self.reset_page,
            register=self.reset_regs["payload_sweep"],
            value=self._payload_sweep_plan["start_register"],
        )
        self.regwi(
            0,
            controls["frequency_loop"],
            len(self.cfg["opx_payload_frequencies_mhz"]) - 1,
        )
        self.label("OPX_PAYLOAD_GRID_FREQUENCY_LOOP")
        for gain_index, gain in enumerate(gains):
            self._payload_gain_dac = int(gain)
            self._payload_label_prefix = (
                f"OPX_PAYLOAD_GRID_G{int(gain_index)}_RESET"
            )
            self._emit_body()
            self.mathi(0, controls["done"], controls["done"], "+", 1)
            self.memwi(0, controls["done"], self.done_addr)
            self._stream_after_shot()
        self.mathi(
            self.reset_page,
            self.reset_regs["payload_sweep"],
            self.reset_regs["payload_sweep"],
            "+",
            int(self._payload_sweep_plan["step_register"]),
        )
        self.loopnz(
            0,
            controls["frequency_loop"],
            "OPX_PAYLOAD_GRID_FREQUENCY_LOOP",
        )
        self.loopnz(0, controls["shot_loop"], "OPX_PAYLOAD_GRID_SHOT_LOOP")
        self._finish_stream()
        self._end_park_lifecycle()
        self.end()
