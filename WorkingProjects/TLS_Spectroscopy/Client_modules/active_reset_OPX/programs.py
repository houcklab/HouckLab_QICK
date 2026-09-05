"""QICK programs for isolated OPX-style reset calibration and benchmarking."""

import numpy as np

from .classifier import ClassifierCalibration
from .config import OPXResetConfig
from .control_flow import emit_reset_state_machine, emit_unbounded_reset_state_machine
from .records import RECORD_WORDS, TerminalStatus, signed32


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
    "q_projected",
    "z",
    "ground",
    "excited",
    "attempts",
    "pi_count",
    "status",
    "initial_z",
    "address",
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


def allocate_registers(prog, page, reserved=None):
    reserved = set(_reserved_registers(prog, page) if reserved is None else reserved)
    available = [reg for reg in range(1, 31) if reg not in reserved]
    if len(available) < len(REGISTER_NAMES):
        raise ValueError(
            f"OPX reset needs {len(REGISTER_NAMES)} scratch registers on page {page}, "
            f"but only {len(available)} are free; reserved={sorted(reserved)}"
        )
    return dict(zip(REGISTER_NAMES, available[:len(REGISTER_NAMES)]))


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
        raise ValueError("reset_scheme must be 'opx_unbounded' or 'none'")
    prog.regwi(page, regs["ground"], int(bool(do_prepare)), "preparation label")
    for name in ("ground", "initial_z", "attempts", "pi_count", "status"):
        prog.memw(page, regs[name], regs["address"])
        prog.mathi(page, regs["address"], regs["address"], "+", 1)
    prog.mathi(page, regs["address"], regs["address"], "+", 2)
    prog.memw(page, regs["z"], regs["address"])
    prog.mathi(page, regs["address"], regs["address"], "+", 1)
    park_down()


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
            self.reset_regs["q_projected"],
            self.reset_regs["q"],
            "*",
            int(plan["s_abs"]),
        )
        self.math(
            self.reset_page,
            self.reset_regs["z"],
            self.reset_regs["z"],
            plan["combine_op"],
            self.reset_regs["q_projected"],
        )
        self.sync_all(self.us2cycles(float(self.reset_config.feedback_syncdelay_us)))

    def _measure_verification(self):
        self.sync_all(self.us2cycles(float(self.reset_config.verification_delay_us)))
        self._measure_raw()
        self.sync_all(0)

    def _emit_body(self):
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse

        preparation = int(bool(self.cfg.get("prep_excited", False)))
        emit_benchmark_shot(
            self,
            page=self.reset_page,
            regs=self.reset_regs,
            preparation=preparation,
            reset_scheme=self.cfg.get("opx_reset_scheme", "opx"),
            payload_calibration=self.payload_calibration,
            loop_calibration=self.loop_calibration,
            max_reset_attempts=self.reset_config.max_reset_attempts,
            park_up=lambda: ff_pulse.play_park_up(self, self._opx_park_segments),
            park_down=lambda: ff_pulse.play_park_down(self, self._opx_park_segments),
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
        self.label("OPX_SHOT_LOOP")
        self._emit_body()
        self.mathi(outer_page, done_reg, done_reg, "+", 1)
        self.memwi(outer_page, done_reg, self.done_addr)
        self.loopnz(outer_page, loop_reg, "OPX_SHOT_LOOP")
        self.end()


class OPXResetT1Program(OPXResetBenchmarkProgram):
    def _declare_experiment(self):
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse

        cfg = self.cfg
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

    def _wait_t1_payload(self):
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse

        if self._t1_stepping:
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
                self.us2cycles(max(self._t1_hold_us, 0.01))
            )

    def _emit_body(self):
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse

        emit_t1_shot(
            self,
            page=self.reset_page,
            regs=self.reset_regs,
            reset_scheme=self.cfg.get("opx_reset_scheme", "opx_unbounded"),
            payload_calibration=self.payload_calibration,
            loop_calibration=self.loop_calibration,
            park_up=lambda: ff_pulse.play_park_up(self, self._opx_park_segments),
            park_down=lambda: ff_pulse.play_park_down(self, self._opx_park_segments),
            prepare_excited=lambda: _pulse_pi_and_align(self),
            wait_payload=self._wait_t1_payload,
            measure_project=self._measure_project,
            play_pi=lambda: self.pulse(ch=self.cfg["qubit_ch"]),
            label_prefix="OPX_T1_RESET",
            do_prepare=bool(self.cfg.get("do_pi", True)),
        )
        self.sync_all(self.us2cycles(float(self.reset_config.inter_shot_delay_us)))
