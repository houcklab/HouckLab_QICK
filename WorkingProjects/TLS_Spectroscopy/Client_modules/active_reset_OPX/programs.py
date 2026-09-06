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
        )
    elif scheme != "none":
        raise ValueError("reset_scheme must be 'opx_unbounded' or 'none'")
    park_down()


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
    advance_point()
    prog.loopnz(page, point_register, point_label)
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
    wait_feedback_delay,
    wait_reset_settle,
    wait_payload_alignment,
):
    context = str(context).lower()
    if context not in ("payload", "loop"):
        raise ValueError("opx_reference_context must be 'payload' or 'loop'")
    if context == "loop":
        measure()
        wait_read_delay()
        wait_feedback_delay()
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
            wait_feedback_delay=lambda: self.sync_all(
                self.us2cycles(float(self.cfg.get("opx_feedback_syncdelay_us", 2.0)))
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
                self.cfg.get("flux_settle_time_us", 0.0)
            ))),
        )
        if context == "loop":
            self._measure_raw()
            self.sync_all(self.us2cycles(float(
                self.reset_config.feedback_syncdelay_us
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
        recovery_us = float(self.reset_config.feedback_syncdelay_us)
        if context == "loop":
            recovery_us = max(
                recovery_us,
                float(self.reset_config.loop_recovery_us),
            )
        self.sync_all(self.us2cycles(recovery_us))

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
        )
        self.sync_all(self.us2cycles(float(self.reset_config.inter_shot_delay_us)))

    def _declare_experiment(self):
        return None

    def make_program(self):
        _declare_common(self)
        self._declare_experiment()
        self.reset_page = self.ch_page(self.cfg["qubit_ch"])
        self.reset_regs = allocate_registers(self, self.reset_page)
        outer_page, loop_reg, done_reg = 0, 14, 15
        self.regwi(
            self.reset_page,
            self.reset_regs["address"],
            self.record_base,
            "OPX DMem record address",
        )
        self.regwi(outer_page, done_reg, 0, "completed OPX shots")
        self.memwi(outer_page, done_reg, self.done_addr)
        self.regwi(outer_page, loop_reg, self.reps - 1, "OPX shot loop")
        self._begin_park_lifecycle()
        self.label("OPX_SHOT_LOOP")
        self._emit_body()
        self.mathi(outer_page, done_reg, done_reg, "+", 1)
        self.memwi(outer_page, done_reg, self.done_addr)
        self.loopnz(outer_page, loop_reg, "OPX_SHOT_LOOP")
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
        self._t1_ff_settle_us = 0.0
        if self._t1_stepping:
            if not getattr(self, "do_park_hold", False):
                ff_pulse.declare_ff(self)
            self._t1_ff_settle_us = ff_pulse.flux_settle_us(cfg)
            if not getattr(self.reset_config, "hard_flux_steps", False):
                self._t1_ff_segments = ff_pulse.build_ramp_hold_ramp(
                    self,
                    hold_us=self._t1_hold_us + self._t1_ff_settle_us,
                    ff_gain=cfg["ff_gain"],
                    dt_play_us=cfg.get("dt_pulseplay", 5.0),
                    ramp_us=cfg.get("ff_ramp_length", ff_pulse.STATE_SAFE_RAMP_US),
                    dt_def_us=cfg.get("dt_pulsedef", 0.002),
                    compensation=ff_pulse.load_compensation(cfg),
                    distortion_model=ff_pulse.make_distortion_model(self),
                )

    def _wait_t1_payload(self, hold_us=None):
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse

        hold_us = self._t1_hold_us if hold_us is None else float(hold_us)
        if self._t1_stepping:
            if getattr(self.reset_config, "hard_flux_steps", False):
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
            ("shot_loop", "done"),
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
        self._begin_park_lifecycle()
        self.label("OPX_T1_SWEEP_SHOT_LOOP")
        for point_index, delay_us in enumerate(self.cfg["opx_t1_delays_us"]):
            self._emit_t1_point(point_index, float(delay_us))
            self.mathi(0, controls["done"], controls["done"], "+", 1)
            self.memwi(0, controls["done"], self.done_addr)
        self.loopnz(0, controls["shot_loop"], "OPX_T1_SWEEP_SHOT_LOOP")
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
            gain = int(plan["fixed_gain"])
        else:
            frequency_register = self.freq2reg(
                float(plan["fixed_frequency_mhz"]),
                gen_ch=cfg["qubit_ch"],
            )
            gain = 0
        self.set_pulse_registers(
            ch=cfg["qubit_ch"],
            style="arb",
            freq=frequency_register,
            phase=self.deg2reg(
                float(cfg.get("opx_payload_phase_deg", 0.0)),
                gen_ch=cfg["qubit_ch"],
            ),
            gain=gain,
            waveform="qubit",
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
        if str(cfg.get("qubit_pulse_style", "arb")).lower() != "arb":
            raise ValueError("OPX pulse-sweep reset requires an arb qubit pulse")
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
        if placement not in ("park", "excursion"):
            raise ValueError("opx_payload_pulse_placement must be 'park' or 'excursion'")
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
        if self._payload_do_excursion:
            if not getattr(self, "do_park_hold", False):
                ff_pulse.declare_ff(self)
            if not bool(cfg.get("readout_after_park", True)):
                raise ValueError(
                    "OPX pulse-sweep reset requires readout_after_park=True"
                )
            self._payload_excursion_segments = ff_pulse.build_ramp_hold_ramp(
                self,
                hold_us=float(cfg.get("opx_payload_flux_hold_us", 0.05)),
                ff_gain=float(cfg["opx_payload_excursion_gain"]),
                dt_play_us=cfg.get("dt_pulseplay", 5.0),
                ramp_us=cfg.get("ff_ramp_length", ff_pulse.STATE_SAFE_RAMP_US),
                dt_def_us=cfg.get("dt_pulsedef", 0.002),
                compensation=ff_pulse.load_compensation(cfg),
                distortion_model=ff_pulse.make_distortion_model(self),
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
        if self._payload_pulse_placement == "park":
            for _ in range(self._payload_pulses):
                self.pulse(ch=cfg["qubit_ch"])
                self.sync_all(self.us2cycles(0.01))
        if self._payload_do_excursion:
            ff_pulse.play_ramp_up_hold(
                self,
                self._payload_excursion_segments,
                dt_play_us=cfg.get("dt_pulseplay", 5.0),
            )
            self.sync_all(self.us2cycles(0.01))
        if self._payload_pulse_placement == "excursion":
            for _ in range(self._payload_pulses):
                self.pulse(ch=cfg["qubit_ch"])
                self.sync_all(self.us2cycles(0.01))
        if self._payload_do_excursion:
            ff_pulse.play_ramp_down(self, self._payload_excursion_segments)
            self.sync_all(self.us2cycles(ff_pulse.flux_settle_us(cfg)))

    def _emit_body(self):
        park_up, park_down = self._shot_park_callbacks()
        emit_payload_reset_shot(
            self,
            page=self.reset_page,
            regs=self.reset_regs,
            reset_scheme=self.cfg.get("opx_reset_scheme", "opx_unbounded"),
            payload_calibration=self.payload_calibration,
            loop_calibration=self.loop_calibration,
            park_up=park_up,
            park_down=park_down,
            emit_payload=self._emit_payload_pulses,
            measure_project=self._measure_project,
            prepare_reset=self._set_reset_pulse,
            play_pi=lambda: self.pulse(ch=self.cfg["qubit_ch"]),
            label_prefix="OPX_PAYLOAD_RESET",
        )
        self.sync_all(self.us2cycles(float(self.reset_config.inter_shot_delay_us)))

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
            ("shot_loop", "expt_loop", "done"),
            reserved=control_reserved,
        )
        self.regwi(
            self.reset_page,
            self.reset_regs["address"],
            self.record_base,
            "OPX payload record address",
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
        )
        self._end_park_lifecycle()
        self.end()
