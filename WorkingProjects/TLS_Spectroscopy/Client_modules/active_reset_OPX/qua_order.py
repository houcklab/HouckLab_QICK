import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import (
    add_qubit_gaussian,
    readout_thermalization_us,
    set_readout_pulse,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.programs import (
    allocate_named_registers,
)


try:
    from qick import QickProgram
    _QICK_IMPORT_ERROR = None
except Exception as exc:
    _QICK_IMPORT_ERROR = exc

    class QickProgram:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("QICK is unavailable on this computer") from _QICK_IMPORT_ERROR


def scalar_record_order(shots, axis_lengths):
    shots = int(shots)
    lengths = tuple(int(length) for length in axis_lengths)
    if shots <= 0 or not lengths or any(length <= 0 for length in lengths):
        raise ValueError("shots and axis lengths must be positive")
    return [
        (shot,) + index
        for shot in range(shots)
        for index in np.ndindex(lengths)
    ]


def single_shot_record_order(shots, state_order="ge"):
    shots = int(shots)
    order = str(state_order).strip().lower()
    if shots <= 0:
        raise ValueError("shots must be positive")
    if order not in ("ge", "eg"):
        raise ValueError("state_order must be 'ge' or 'eg'")
    states = (0, 1) if order == "ge" else (1, 0)
    return [(state, shot) for state in states for shot in range(shots)]


def reshape_scalar_records(values, *, shots, axis_lengths):
    shots = int(shots)
    lengths = tuple(int(length) for length in axis_lengths)
    array = np.asarray(values)
    expected = shots * int(np.prod(lengths, dtype=int))
    if array.size != expected:
        raise ValueError(f"received {array.size} records but expected {expected}")
    return array.reshape((shots,) + lengths).mean(axis=0)


def optimizer_record_order(shots, frequencies, gains):
    shots = int(shots)
    frequencies = int(frequencies)
    gains = int(gains)
    if shots <= 0 or frequencies <= 0 or gains <= 0:
        raise ValueError("shots, frequencies, and gains must be positive")
    return [
        (shot, frequency, gain, state)
        for shot in range(shots)
        for frequency in range(frequencies)
        for gain in range(gains)
        for state in range(2)
    ]


def flux_spectroscopy_record_order(
    shots, *, frequencies, dc_points, times, order
):
    shots = int(shots)
    frequencies = int(frequencies)
    dc_points = int(dc_points)
    times = int(times)
    if min(shots, frequencies, dc_points, times) <= 0:
        raise ValueError("shots and axis lengths must be positive")
    order = str(order)
    if order == "shot_frequency_dc_time":
        return [
            (shot, frequency, dc, delay)
            for shot in range(shots)
            for frequency in range(frequencies)
            for dc in range(dc_points)
            for delay in range(times)
        ]
    if order == "shot_dc_frequency_time":
        return [
            (shot, dc, frequency, delay)
            for shot in range(shots)
            for dc in range(dc_points)
            for frequency in range(frequencies)
            for delay in range(times)
        ]
    raise ValueError(
        "order must be 'shot_frequency_dc_time' or "
        "'shot_dc_frequency_time'"
    )


def reshape_optimizer_records(values, *, shots, frequencies, gains):
    shots = int(shots)
    frequencies = int(frequencies)
    gains = int(gains)
    array = np.asarray(values)
    expected = shots * frequencies * gains * 2
    if array.size != expected:
        raise ValueError(f"received {array.size} records but expected {expected}")
    return array.reshape(shots, frequencies, gains, 2)


def _declare_readout(program):
    cfg = program.cfg
    program.declare_gen(
        ch=cfg["res_ch"],
        nqz=cfg["nqz"],
        mixer_freq=cfg.get("mixer_freq", 0),
        ro_ch=cfg["ro_chs"][0],
    )
    for ro_ch in cfg["ro_chs"]:
        program.declare_readout(
            ch=ro_ch,
            freq=cfg["read_pulse_freq"],
            length=program.us2cycles(cfg["read_length"], ro_ch=cfg["ro_chs"][0]),
            gen_ch=cfg["res_ch"],
        )
    set_readout_pulse(program)


def _declare_park(program, require_flux=False):
    cfg = program.cfg
    ff_pulse.declare_park_hold(program)
    if require_flux and int(cfg["ff_ch"]) not in program.gen_chs:
        ff_pulse.declare_ff(program)
    if not ff_pulse.park_hold_configured(cfg):
        return None
    if bool(cfg.get("opx_hard_flux_steps", False)):
        return {"park": int(round(float(cfg.get("ff_park_gain", 0))))}
    return ff_pulse.build_park_hold(program, hold_us=ff_pulse.flux_settle_us(cfg))


def _begin_park(program, segments):
    if bool(program.cfg.get("qua_assert_park_at_start", True)):
        ff_pulse.begin_park_lifecycle(program, segments)


def _allocate_stream_counter(program, extra_names=()):
    names = ("stream_count",) + tuple(extra_names)
    controls = allocate_named_registers(program, 0, names)
    program.stream_count_register = controls["stream_count"]
    program.regwi(0, program.stream_count_register, 0)
    program.memwi(0, program.stream_count_register, program.counter_addr)
    return controls


def _emit_stream_record(program):
    program.mathi(
        0,
        program.stream_count_register,
        program.stream_count_register,
        "+",
        1,
    )
    program.memwi(0, program.stream_count_register, program.counter_addr)


def _measure_record(program, delay_us=None):
    cfg = program.cfg
    program.measure(
        pulse_ch=cfg["res_ch"],
        adcs=cfg["ro_chs"],
        adc_trig_offset=program.us2cycles(cfg["adc_trig_offset"]),
        wait=True,
        syncdelay=program.us2cycles(0.01),
    )
    _emit_stream_record(program)
    delay = readout_thermalization_us(cfg) if delay_us is None else float(delay_us)
    if delay > 0:
        program.sync_all(program.us2cycles(delay))


def _acquire_stream_records(program, soc, progress=False, load_pulses=True):
    d_buf, _, _ = QickProgram.acquire(
        program,
        soc,
        reads_per_rep=1,
        load_pulses=bool(load_pulses),
        start_src="internal",
        progress=progress,
        debug=False,
    )
    read_cycles = program.us2cycles(
        program.cfg["read_length"], ro_ch=program.cfg["ro_chs"][0]
    )
    data = np.asarray(d_buf[0], dtype=float)
    if data.shape != (program.reps, 2):
        raise RuntimeError(
            f"streamed readout shape {data.shape} does not match {(program.reps, 2)}"
        )
    return data[:, 0] / read_cycles, data[:, 1] / read_cycles


def _set_qubit_pulse(program, frequency_mhz, gain):
    cfg = program.cfg
    style = str(cfg.get("qubit_pulse_style", "arb")).lower()
    frequency = program.freq2reg(float(frequency_mhz), gen_ch=cfg["qubit_ch"])
    if style == "arb":
        add_qubit_gaussian(program)
        program.set_pulse_registers(
            ch=cfg["qubit_ch"],
            style="arb",
            freq=frequency,
            phase=program.deg2reg(0, gen_ch=cfg["qubit_ch"]),
            gain=int(gain),
            waveform="qubit",
        )
    elif style == "flat_top":
        add_qubit_gaussian(program)
        program.set_pulse_registers(
            ch=cfg["qubit_ch"],
            style="flat_top",
            freq=frequency,
            phase=0,
            gain=int(gain),
            waveform="qubit",
            length=program.us2cycles(
                cfg["flat_top_length"], gen_ch=cfg["qubit_ch"]
            ),
        )
    else:
        program.set_pulse_registers(
            ch=cfg["qubit_ch"],
            style="const",
            freq=frequency,
            phase=0,
            gain=int(gain),
            length=program.us2cycles(
                cfg["qubit_length"], gen_ch=cfg["qubit_ch"]
            ),
        )


def _uniform_frequency_registers(program, frequencies):
    cfg = program.cfg
    frequencies = np.asarray(frequencies, dtype=float)
    frequency_steps = np.diff(frequencies)
    if frequency_steps.size and not np.allclose(
        frequency_steps,
        frequency_steps[0],
        rtol=1e-9,
        atol=1e-12,
    ):
        raise ValueError("qubit frequencies must be uniformly spaced")
    registers = np.asarray([
        program.freq2reg(float(value), gen_ch=cfg["qubit_ch"])
        for value in frequencies
    ], dtype=np.int64)
    if registers.size < 2:
        return registers, 0
    step = int(round((int(registers[-1]) - int(registers[0])) / (registers.size - 1)))
    return registers, step


def _compensated_hold_segments(
    *, park_gain, target_gain, hold_us, compensation, max_gain
):
    park_gain = float(park_gain)
    target_gain = float(target_gain)
    hold_us = float(hold_us)
    max_gain = abs(float(max_gain))
    if not np.isfinite(hold_us) or hold_us <= 0:
        raise ValueError("hold time must be positive and finite")
    delta = target_gain - park_gain
    if not compensation:
        gain = int(np.clip(round(target_gain), -max_gain, max_gain))
        return [(gain, hold_us)]
    edges = np.asarray(
        compensation.get("segment_edges_ns", []), dtype=float
    ).reshape(-1) / 1e3
    multipliers = np.asarray(
        compensation.get("multipliers", []), dtype=float
    ).reshape(-1)
    if edges.size == 0 or multipliers.size == 0:
        gain = int(np.clip(round(target_gain), -max_gain, max_gain))
        return [(gain, hold_us)]
    if not np.all(np.isfinite(edges)) or not np.all(np.isfinite(multipliers)):
        raise ValueError("flux compensation contains non-finite values")
    starts = sorted(set(
        [0.0] + [float(edge) for edge in edges if 0.0 < edge < hold_us]
    ))
    segments = []
    for index, start in enumerate(starts):
        stop = starts[index + 1] if index + 1 < len(starts) else hold_us
        multiplier_index = int(
            np.clip(np.searchsorted(edges, start + 1e-12, side="right") - 1,
                    0, multipliers.size - 1)
        )
        gain = int(np.clip(
            round(park_gain + multipliers[multiplier_index] * delta),
            -max_gain,
            max_gain,
        ))
        segments.append((gain, stop - start))
    return segments


def _ff_max_gain(program):
    try:
        return int(ff_pulse.PulseFunctions.ff_maxv(program, scaled=True))
    except Exception:
        return 32767


def _build_flux_point(program, target_gain, hold_us, name_prefix):
    cfg = program.cfg
    if bool(cfg.get("opx_hard_flux_steps", False)):
        return {
            "hard": True,
            "park": int(round(float(cfg.get("ff_park_gain", 0) or 0))),
            "hold_segs": _compensated_hold_segments(
                park_gain=float(cfg.get("ff_park_gain", 0) or 0),
                target_gain=float(target_gain),
                hold_us=float(hold_us),
                compensation=ff_pulse.load_compensation(cfg),
                max_gain=_ff_max_gain(program),
            ),
        }
    return ff_pulse.build_ramp_hold_ramp(
        program,
        hold_us=float(hold_us),
        ff_gain=float(target_gain),
        dt_play_us=cfg.get("dt_pulseplay", 5.0),
        ramp_us=cfg.get("ff_ramp_length", ff_pulse.STATE_SAFE_RAMP_US),
        dt_def_us=cfg.get("dt_pulsedef", 0.002),
        compensation=ff_pulse.load_compensation(cfg),
        distortion_model=ff_pulse.make_distortion_model(program),
        name_prefix=str(name_prefix),
    )


def _play_flux_point(program, segments):
    if segments.get("hard", False):
        for gain, duration_us in segments["hold_segs"]:
            ff_pulse.play_hard_step(program, gain)
            if duration_us > 0:
                program.sync_all(program.us2cycles(float(duration_us)))
        return
    ff_pulse.play_ramp_up_hold(
        program,
        segments,
        dt_play_us=program.cfg.get("dt_pulseplay", 5.0),
    )


def _restore_flux_park(program, segments, settle_us=0.0):
    if segments.get("hard", False):
        ff_pulse.play_hard_step(program, segments.get("park", 0))
    else:
        ff_pulse.play_ramp_down(program, segments)
    if float(settle_us) > 0:
        program.sync_all(program.us2cycles(float(settle_us)))


class QUAReadoutFrequencyProgram(QickProgram):
    def __init__(self, soccfg, cfg, *, read_frequency_mhz, values, kind,
                 excursion_gain=None):
        QickProgram.__init__(self, soccfg)
        self.cfg = dict(cfg)
        self.cfg["read_pulse_freq"] = float(read_frequency_mhz)
        self.values = np.asarray(values, dtype=float).reshape(-1)
        if self.values.size == 0 or not np.all(np.isfinite(self.values)):
            raise ValueError("values must contain finite values")
        self.kind = str(kind)
        if self.kind not in ("readout_gain", "flux_gain"):
            raise ValueError("kind must be 'readout_gain' or 'flux_gain'")
        self.excursion_gain = None if excursion_gain is None else float(excursion_gain)
        self.reps = int(self.values.size)
        self.expts = None
        self.rounds = 1
        self.make_program()

    def _set_flux(self, gain):
        ff_pulse.play_hard_step(self, float(gain))
        settle = ff_pulse.flux_settle_us(self.cfg)
        if settle > 0:
            self.sync_all(self.us2cycles(settle))

    def make_program(self):
        cfg = self.cfg
        _declare_readout(self)
        requires_flux = self.kind == "flux_gain" or self.excursion_gain is not None
        park_segments = _declare_park(self, require_flux=requires_flux)
        _allocate_stream_counter(self)
        _begin_park(self, park_segments)
        res_page = self.ch_page(cfg["res_ch"])
        res_gain = self.sreg(cfg["res_ch"], "gain")
        park_gain = float(cfg.get("ff_park_gain", 0) or 0)
        for value in self.values:
            if self.kind == "readout_gain":
                self.safe_regwi(res_page, res_gain, int(round(float(value))))
                if self.excursion_gain is not None:
                    self._set_flux(self.excursion_gain)
            else:
                self._set_flux(float(value))
            _measure_record(self)
            if self.kind == "readout_gain" and self.excursion_gain is not None:
                self._set_flux(park_gain)
        if self.kind == "flux_gain":
            self._set_flux(park_gain)
        self.end()

    def acquire_records(self, soc, progress=False, load_pulses=True):
        return _acquire_stream_records(
            self, soc, progress=progress, load_pulses=load_pulses
        )


class QUAResidentReadoutGridProgram(QickProgram):
    def __init__(self, soccfg, cfg, *, frequencies_mhz, values, kind,
                 excursion_gain=None):
        QickProgram.__init__(self, soccfg)
        self.cfg = dict(cfg)
        self.frequencies = _finite_axis(frequencies_mhz, "frequencies_mhz")
        self.cfg["read_pulse_freq"] = float(self.frequencies[0])
        self.values = _finite_axis(values, "values")
        self.kind = str(kind)
        if self.kind not in ("readout_gain", "flux_gain"):
            raise ValueError("kind must be 'readout_gain' or 'flux_gain'")
        self.excursion_gain = (
            None if excursion_gain is None else float(excursion_gain)
        )
        self.shots = _positive_shots(self.cfg)
        self.reps = int(
            self.shots * self.frequencies.size * self.values.size
        )
        self.expts = None
        self.rounds = 1
        self.command_addr = self.counter_addr + 1
        self.ready_addr = self.counter_addr + 2
        self.frequency_addr = self.counter_addr + 3
        self.command_mode = str(
            self.cfg.get("qick_resident_command_mode", "sequenced")
        )
        if self.command_mode not in (
            "split", "packed_frequency", "sequenced"
        ):
            raise ValueError("invalid resident command mode")
        self.frequency_registers = np.asarray(
            [
                self.freq2reg(
                    float(frequency),
                    gen_ch=self.cfg["res_ch"],
                    ro_ch=self.cfg["ro_chs"][0],
                )
                for frequency in self.frequencies
            ],
            dtype=np.int64,
        )
        self.make_program()

    def _set_flux(self, gain):
        ff_pulse.play_hard_step(self, float(gain))
        settle = ff_pulse.flux_settle_us(self.cfg)
        if settle > 0:
            self.sync_all(self.us2cycles(settle))

    def make_program(self):
        cfg = self.cfg
        _declare_readout(self)
        requires_flux = self.kind == "flux_gain" or self.excursion_gain is not None
        park_segments = _declare_park(self, require_flux=requires_flux)
        controls = _allocate_stream_counter(
            self,
            (
                "shot_loop",
                "frequency_loop",
                "command",
                "ready",
                "elapsed",
            ),
        )
        res_page = self.ch_page(cfg["res_ch"])
        res_frequency = self.sreg(cfg["res_ch"], "freq")
        res_gain = self.sreg(cfg["res_ch"], "gain")
        self.regwi(0, controls["command"], 0)
        self.memwi(0, controls["command"], self.command_addr)
        self.regwi(0, controls["ready"], 0)
        self.memwi(0, controls["ready"], self.ready_addr)
        self.regwi(0, controls["shot_loop"], self.shots - 1)
        _begin_park(self, park_segments)
        self.label("QUA_RESIDENT_READOUT_SHOT")
        self.regwi(
            0,
            controls["frequency_loop"],
            int(self.frequencies.size) - 1,
        )
        self.label("QUA_RESIDENT_READOUT_FREQUENCY")
        self.regwi(0, controls["elapsed"], 200)
        self.mathi(
            0,
            controls["ready"],
            controls["ready"],
            "+",
            1,
        )
        self.memwi(0, controls["ready"], self.ready_addr)
        self.label("QUA_RESIDENT_READOUT_WAIT")
        self.mathi(
            0,
            controls["elapsed"],
            controls["elapsed"],
            "+",
            14,
        )
        if self.command_mode == "packed_frequency":
            self.memri(res_page, res_frequency, self.command_addr)
            self.condj(
                res_page,
                res_frequency,
                "==",
                0,
                "QUA_RESIDENT_READOUT_WAIT",
            )
        elif self.command_mode == "sequenced":
            self.memri(0, controls["command"], self.command_addr)
            self.condj(
                0,
                controls["command"],
                "!=",
                controls["ready"],
                "QUA_RESIDENT_READOUT_WAIT",
            )
        else:
            self.memri(0, controls["command"], self.command_addr)
            self.condj(
                0,
                controls["command"],
                "==",
                0,
                "QUA_RESIDENT_READOUT_WAIT",
            )
        self.sync(0, controls["elapsed"])
        if self.command_mode != "packed_frequency":
            self.memri(res_page, res_frequency, self.frequency_addr)
        if self.command_mode != "sequenced":
            self.regwi(0, controls["command"], 0)
            self.memwi(0, controls["command"], self.command_addr)
        park_gain = float(cfg.get("ff_park_gain", 0) or 0)
        for value in self.values:
            if self.kind == "readout_gain":
                self.safe_regwi(res_page, res_gain, int(round(float(value))))
                if self.excursion_gain is not None:
                    self._set_flux(self.excursion_gain)
            else:
                self._set_flux(float(value))
            _measure_record(self)
            if self.kind == "readout_gain" and self.excursion_gain is not None:
                self._set_flux(park_gain)
        if self.kind == "flux_gain":
            self._set_flux(park_gain)
        self.loopnz(
            0,
            controls["frequency_loop"],
            "QUA_RESIDENT_READOUT_FREQUENCY",
        )
        self.loopnz(
            0,
            controls["shot_loop"],
            "QUA_RESIDENT_READOUT_SHOT",
        )
        self.end()


class QUAResidentReadoutOptimizerProgram(QickProgram):
    def __init__(self, soccfg, cfg, *, frequencies_mhz, gains, drive_pulses,
                 drive_gain):
        QickProgram.__init__(self, soccfg)
        self.cfg = dict(cfg)
        self.frequencies = _finite_axis(frequencies_mhz, "frequencies_mhz")
        self.cfg["read_pulse_freq"] = float(self.frequencies[0])
        self.gains = np.rint(_finite_axis(gains, "gains")).astype(np.int64)
        self.drive_pulses = int(drive_pulses)
        self.drive_gain = int(drive_gain)
        if self.drive_pulses <= 0:
            raise ValueError("drive_pulses must be positive")
        self.shots = _positive_shots(self.cfg)
        self.reps = int(
            self.shots * self.frequencies.size * self.gains.size * 2
        )
        self.expts = None
        self.rounds = 1
        self.command_addr = self.counter_addr + 1
        self.ready_addr = self.counter_addr + 2
        self.frequency_addr = self.counter_addr + 3
        self.command_mode = str(
            self.cfg.get("qick_resident_command_mode", "sequenced")
        )
        if self.command_mode not in (
            "split", "packed_frequency", "sequenced"
        ):
            raise ValueError("invalid resident command mode")
        self.frequency_registers = np.asarray(
            [
                self.freq2reg(
                    float(frequency),
                    gen_ch=self.cfg["res_ch"],
                    ro_ch=self.cfg["ro_chs"][0],
                )
                for frequency in self.frequencies
            ],
            dtype=np.int64,
        )
        self.make_program()

    def make_program(self):
        cfg = self.cfg
        _declare_readout(self)
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        _set_qubit_pulse(
            self,
            float(cfg.get("qubit_pi_freq", cfg["qubit_freq"])),
            self.drive_gain,
        )
        park_segments = _declare_park(self)
        controls = _allocate_stream_counter(
            self,
            (
                "shot_loop",
                "frequency_loop",
                "command",
                "ready",
                "elapsed",
            ),
        )
        res_page = self.ch_page(cfg["res_ch"])
        res_frequency = self.sreg(cfg["res_ch"], "freq")
        res_gain = self.sreg(cfg["res_ch"], "gain")
        self.regwi(0, controls["command"], 0)
        self.memwi(0, controls["command"], self.command_addr)
        self.regwi(0, controls["ready"], 0)
        self.memwi(0, controls["ready"], self.ready_addr)
        self.regwi(0, controls["shot_loop"], self.shots - 1)
        _begin_park(self, park_segments)
        self.label("QUA_RESIDENT_OPTIMIZER_SHOT")
        self.regwi(
            0,
            controls["frequency_loop"],
            int(self.frequencies.size) - 1,
        )
        self.label("QUA_RESIDENT_OPTIMIZER_FREQUENCY")
        self.regwi(0, controls["elapsed"], 200)
        self.mathi(0, controls["ready"], controls["ready"], "+", 1)
        self.memwi(0, controls["ready"], self.ready_addr)
        self.label("QUA_RESIDENT_OPTIMIZER_WAIT")
        self.mathi(0, controls["elapsed"], controls["elapsed"], "+", 14)
        if self.command_mode == "packed_frequency":
            self.memri(res_page, res_frequency, self.command_addr)
            self.condj(
                res_page,
                res_frequency,
                "==",
                0,
                "QUA_RESIDENT_OPTIMIZER_WAIT",
            )
        elif self.command_mode == "sequenced":
            self.memri(0, controls["command"], self.command_addr)
            self.condj(
                0,
                controls["command"],
                "!=",
                controls["ready"],
                "QUA_RESIDENT_OPTIMIZER_WAIT",
            )
        else:
            self.memri(0, controls["command"], self.command_addr)
            self.condj(
                0,
                controls["command"],
                "==",
                0,
                "QUA_RESIDENT_OPTIMIZER_WAIT",
            )
        self.sync(0, controls["elapsed"])
        if self.command_mode != "packed_frequency":
            self.memri(res_page, res_frequency, self.frequency_addr)
        if self.command_mode != "sequenced":
            self.regwi(0, controls["command"], 0)
            self.memwi(0, controls["command"], self.command_addr)
        passive_reset = float(cfg.get("relax_delay", 1000.0))
        for gain in self.gains:
            self.safe_regwi(res_page, res_gain, int(gain))
            if passive_reset > 0:
                self.sync_all(self.us2cycles(passive_reset))
            _measure_record(self, delay_us=0.0)
            if passive_reset > 0:
                self.sync_all(self.us2cycles(passive_reset))
            for _ in range(self.drive_pulses):
                self.pulse(ch=cfg["qubit_ch"])
                self.sync_all(self.us2cycles(0.01))
            _measure_record(self, delay_us=0.0)
        self.loopnz(
            0,
            controls["frequency_loop"],
            "QUA_RESIDENT_OPTIMIZER_FREQUENCY",
        )
        self.loopnz(
            0,
            controls["shot_loop"],
            "QUA_RESIDENT_OPTIMIZER_SHOT",
        )
        self.end()


class QUAPulseGridProgram(QickProgram):
    def __init__(self, soccfg, cfg, *, frequencies_mhz, gains, pulses):
        QickProgram.__init__(self, soccfg)
        self.cfg = dict(cfg)
        self.frequencies = _finite_axis(frequencies_mhz, "frequencies_mhz")
        rounded = np.rint(_finite_axis(gains, "gains")).astype(np.int64)
        self.gains = rounded
        self.drive_pulses = int(pulses)
        if self.drive_pulses < 0:
            raise ValueError("pulses must be non-negative")
        self.shots = _positive_shots(self.cfg)
        self.reps = int(self.shots * self.frequencies.size * self.gains.size)
        self.expts = None
        self.rounds = 1
        self.make_program()

    def make_program(self):
        cfg = self.cfg
        _declare_readout(self)
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        _set_qubit_pulse(self, self.frequencies[0], self.gains[0])
        park_segments = _declare_park(self)
        controls = _allocate_stream_counter(
            self, ("shot_loop", "frequency_loop")
        )
        qubit_page = self.ch_page(cfg["qubit_ch"])
        frequency_register = self.sreg(cfg["qubit_ch"], "freq")
        gain_register = self.sreg(cfg["qubit_ch"], "gain")
        try:
            gain2_register = self.sreg(cfg["qubit_ch"], "gain2")
        except Exception:
            gain2_register = None
        frequency_values, frequency_step = _uniform_frequency_registers(
            self, self.frequencies
        )
        passive_reset_us = float(cfg.get(
            "qua_passive_pre_point_delay_us",
            max(
                float(cfg.get("relax_delay", readout_thermalization_us(cfg))),
                readout_thermalization_us(cfg),
            ),
        ))
        self.regwi(0, controls["shot_loop"], self.shots - 1)
        _begin_park(self, park_segments)
        self.label("QUA_PASSIVE_PULSE_SHOT")
        self.safe_regwi(qubit_page, frequency_register, int(frequency_values[0]))
        self.regwi(0, controls["frequency_loop"], self.frequencies.size - 1)
        self.label("QUA_PASSIVE_PULSE_FREQUENCY")
        for gain in self.gains:
            self.safe_regwi(qubit_page, gain_register, int(gain))
            if gain2_register is not None:
                self.safe_regwi(qubit_page, gain2_register, int(gain // 2))
            if passive_reset_us > 0:
                self.sync_all(self.us2cycles(passive_reset_us))
            for _ in range(self.drive_pulses):
                self.pulse(ch=cfg["qubit_ch"])
                self.sync_all(self.us2cycles(0.01))
            _measure_record(self)
        self.mathi(
            qubit_page,
            frequency_register,
            frequency_register,
            "+",
            frequency_step,
        )
        self.loopnz(0, controls["frequency_loop"], "QUA_PASSIVE_PULSE_FREQUENCY")
        self.loopnz(0, controls["shot_loop"], "QUA_PASSIVE_PULSE_SHOT")
        self.end()

    def acquire_records(self, soc, progress=False, load_pulses=True):
        return _acquire_stream_records(
            self, soc, progress=progress, load_pulses=load_pulses
        )


class QUAFluxSpectroscopyProgram(QickProgram):
    def __init__(
        self,
        soccfg,
        cfg,
        *,
        frequencies_mhz,
        dc_gains,
        hold_times_us,
        read_frequencies_mhz,
        order,
        shots,
        baseline_rearm_us,
        post_readout_reset_us,
        readout_after_park,
    ):
        QickProgram.__init__(self, soccfg)
        self.cfg = dict(cfg)
        self.frequencies = _finite_axis(frequencies_mhz, "frequencies_mhz")
        self.dc_gains = _finite_axis(dc_gains, "dc_gains")
        self.hold_times = _finite_axis(hold_times_us, "hold_times_us")
        self.read_frequencies = _finite_axis(
            read_frequencies_mhz, "read_frequencies_mhz"
        )
        if self.read_frequencies.size != self.dc_gains.size:
            raise ValueError("read frequencies must have one value per DC point")
        if np.any(self.hold_times <= 0):
            raise ValueError("hold times must be positive")
        self.order = str(order)
        if self.order not in (
            "shot_frequency_dc_time",
            "shot_dc_frequency_time",
        ):
            raise ValueError("unsupported flux spectroscopy order")
        self.shots = int(shots)
        if self.shots <= 0:
            raise ValueError("shots must be positive")
        self.baseline_rearm_us = max(float(baseline_rearm_us), 0.0)
        self.post_readout_reset_us = max(float(post_readout_reset_us), 0.0)
        self.readout_after_park = bool(readout_after_park)
        self.reps = int(
            self.shots * self.frequencies.size * self.dc_gains.size
            * self.hold_times.size
        )
        self.expts = None
        self.rounds = 1
        self.make_program()

    def _set_readout_frequency(self, dc_index):
        cfg = self.cfg
        register = self.freq2reg(
            float(self.read_frequencies[int(dc_index)]),
            gen_ch=cfg["res_ch"],
            ro_ch=cfg["ro_chs"][0],
        )
        self.safe_regwi(self.res_page, self.res_frequency_register, int(register))

    def _rearm_park(self, delay_us):
        if bool(self.cfg.get("opx_hard_flux_steps", False)):
            ff_pulse.play_hard_step(
                self, float(self.cfg.get("ff_park_gain", 0) or 0)
            )
        delay_us = max(float(delay_us), readout_thermalization_us(self.cfg))
        if delay_us > 0:
            self.sync_all(self.us2cycles(delay_us))

    def _measure_flux_point(self, dc_index, time_index):
        cfg = self.cfg
        segments = self.flux_points[int(dc_index)][int(time_index)]
        _play_flux_point(self, segments)
        self.sync_all(self.us2cycles(0.01))
        self.pulse(ch=cfg["qubit_ch"])
        self.sync_all(self.us2cycles(0.01))
        if self.readout_after_park:
            _restore_flux_park(
                self, segments, settle_us=ff_pulse.flux_settle_us(cfg)
            )
        _measure_record(self, delay_us=0.0)
        if not self.readout_after_park:
            _restore_flux_park(self, segments)
        cooldown = 0.0
        if self.order == "shot_dc_frequency_time":
            cooldown = max(
                self.post_readout_reset_us,
                readout_thermalization_us(cfg),
            )
        if cooldown > 0:
            self.sync_all(self.us2cycles(cooldown))

    def _frequency_loop(self, dc_indices, label_suffix):
        self.safe_regwi(
            self.qubit_page,
            self.qubit_frequency_register,
            int(self.frequency_registers[0]),
        )
        self.regwi(0, self.controls["frequency_loop"], self.frequencies.size - 1)
        label = f"QUA_FLUX_FREQUENCY_{label_suffix}"
        self.label(label)
        for dc_index in dc_indices:
            self._set_readout_frequency(dc_index)
            for time_index in range(self.hold_times.size):
                if self.order == "shot_frequency_dc_time":
                    self._rearm_park(max(
                        self.baseline_rearm_us,
                        self.post_readout_reset_us,
                    ))
                self._measure_flux_point(dc_index, time_index)
        self.mathi(
            self.qubit_page,
            self.qubit_frequency_register,
            self.qubit_frequency_register,
            "+",
            self.frequency_step,
        )
        self.loopnz(0, self.controls["frequency_loop"], label)

    def make_program(self):
        cfg = self.cfg
        cfg["read_pulse_freq"] = float(self.read_frequencies[0])
        _declare_readout(self)
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        _set_qubit_pulse(
            self,
            self.frequencies[0],
            int(cfg.get("qubit_gain", cfg.get("qubit_pi_gain", 0))),
        )
        park_segments = _declare_park(self, require_flux=True)
        self.controls = _allocate_stream_counter(
            self, ("shot_loop", "frequency_loop")
        )
        self.qubit_page = self.ch_page(cfg["qubit_ch"])
        self.qubit_frequency_register = self.sreg(cfg["qubit_ch"], "freq")
        self.res_page = self.ch_page(cfg["res_ch"])
        self.res_frequency_register = self.sreg(cfg["res_ch"], "freq")
        self.frequency_registers, self.frequency_step = _uniform_frequency_registers(
            self, self.frequencies
        )
        self.flux_points = [
            [
                _build_flux_point(
                    self,
                    target_gain=dc_gain,
                    hold_us=hold_time,
                    name_prefix=f"qua_flux_{dc_index}_{time_index}",
                )
                for time_index, hold_time in enumerate(self.hold_times)
            ]
            for dc_index, dc_gain in enumerate(self.dc_gains)
        ]
        self.regwi(0, self.controls["shot_loop"], self.shots - 1)
        _begin_park(self, park_segments)
        self.label("QUA_FLUX_SHOT")
        if self.order == "shot_frequency_dc_time":
            self._frequency_loop(range(self.dc_gains.size), "ALL_DC")
        else:
            for dc_index in range(self.dc_gains.size):
                self._rearm_park(self.baseline_rearm_us)
                self._set_readout_frequency(dc_index)
                self._frequency_loop((dc_index,), str(dc_index))
        self.loopnz(0, self.controls["shot_loop"], "QUA_FLUX_SHOT")
        if bool(cfg.get("opx_hard_flux_steps", False)):
            ff_pulse.play_hard_step(
                self, float(cfg.get("ff_park_gain", 0) or 0)
            )
        self.end()

    def acquire_records(self, soc, progress=False, load_pulses=True):
        return _acquire_stream_records(
            self, soc, progress=progress, load_pulses=load_pulses
        )


class QUAOptimizerFrequencyProgram(QickProgram):
    def __init__(self, soccfg, cfg, *, frequency_mhz, gains, kind, drive_pulses,
                 drive_gain):
        QickProgram.__init__(self, soccfg)
        self.cfg = dict(cfg)
        self.frequency_mhz = float(frequency_mhz)
        self.gains = np.rint(_finite_axis(gains, "gains")).astype(np.int64)
        self.kind = str(kind)
        if self.kind not in ("readout", "qubit"):
            raise ValueError("kind must be 'readout' or 'qubit'")
        self.drive_pulses = int(drive_pulses)
        self.drive_gain = int(drive_gain)
        if self.drive_pulses <= 0:
            raise ValueError("drive_pulses must be positive")
        self.reps = int(self.gains.size * 2)
        self.expts = None
        self.rounds = 1
        self.make_program()

    def make_program(self):
        cfg = self.cfg
        if self.kind == "readout":
            cfg["read_pulse_freq"] = self.frequency_mhz
        _declare_readout(self)
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        qubit_frequency = (
            self.frequency_mhz
            if self.kind == "qubit"
            else float(cfg.get("qubit_pi_freq", cfg["qubit_freq"]))
        )
        initial_gain = int(self.gains[0]) if self.kind == "qubit" else self.drive_gain
        _set_qubit_pulse(self, qubit_frequency, initial_gain)
        park_segments = _declare_park(self)
        _allocate_stream_counter(self)
        _begin_park(self, park_segments)
        res_page = self.ch_page(cfg["res_ch"])
        res_gain = self.sreg(cfg["res_ch"], "gain")
        qubit_page = self.ch_page(cfg["qubit_ch"])
        qubit_gain = self.sreg(cfg["qubit_ch"], "gain")
        try:
            qubit_gain2 = self.sreg(cfg["qubit_ch"], "gain2")
        except Exception:
            qubit_gain2 = None
        passive_reset = float(cfg.get("relax_delay", 1000.0))
        for gain in self.gains:
            if self.kind == "readout":
                self.safe_regwi(res_page, res_gain, int(gain))
                self.safe_regwi(qubit_page, qubit_gain, self.drive_gain)
                if qubit_gain2 is not None:
                    self.safe_regwi(qubit_page, qubit_gain2, self.drive_gain // 2)
            else:
                self.safe_regwi(qubit_page, qubit_gain, int(gain))
                if qubit_gain2 is not None:
                    self.safe_regwi(qubit_page, qubit_gain2, int(gain // 2))
            if passive_reset > 0:
                self.sync_all(self.us2cycles(passive_reset))
            _measure_record(self, delay_us=0.0)
            if passive_reset > 0:
                self.sync_all(self.us2cycles(passive_reset))
            for _ in range(self.drive_pulses):
                self.pulse(ch=cfg["qubit_ch"])
                self.sync_all(self.us2cycles(0.01))
            _measure_record(self, delay_us=0.0)
        self.end()

    def acquire_records(self, soc, progress=False, load_pulses=True):
        return _acquire_stream_records(
            self, soc, progress=progress, load_pulses=load_pulses
        )


class QUAOptimizerGridProgram(QickProgram):
    def __init__(self, soccfg, cfg, *, frequencies_mhz, gains, drive_pulses):
        QickProgram.__init__(self, soccfg)
        self.cfg = dict(cfg)
        self.frequencies = _finite_axis(frequencies_mhz, "frequencies_mhz")
        self.gains = np.rint(_finite_axis(gains, "gains")).astype(np.int64)
        self.drive_pulses = int(drive_pulses)
        if self.drive_pulses <= 0:
            raise ValueError("drive_pulses must be positive")
        self.shots = _positive_shots(self.cfg)
        self.reps = int(
            self.shots * self.frequencies.size * self.gains.size * 2
        )
        self.expts = None
        self.rounds = 1
        self.make_program()

    def make_program(self):
        cfg = self.cfg
        _declare_readout(self)
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        _set_qubit_pulse(self, self.frequencies[0], self.gains[0])
        park_segments = _declare_park(self)
        controls = _allocate_stream_counter(
            self, ("shot_loop", "frequency_loop")
        )
        qubit_page = self.ch_page(cfg["qubit_ch"])
        frequency_register = self.sreg(cfg["qubit_ch"], "freq")
        gain_register = self.sreg(cfg["qubit_ch"], "gain")
        try:
            gain2_register = self.sreg(cfg["qubit_ch"], "gain2")
        except Exception:
            gain2_register = None
        frequency_values, frequency_step = _uniform_frequency_registers(
            self, self.frequencies
        )
        passive_reset = float(cfg.get("relax_delay", 1000.0))
        self.regwi(0, controls["shot_loop"], self.shots - 1)
        _begin_park(self, park_segments)
        self.label("QUA_PASSIVE_OPTIMIZER_SHOT")
        self.safe_regwi(qubit_page, frequency_register, int(frequency_values[0]))
        self.regwi(0, controls["frequency_loop"], self.frequencies.size - 1)
        self.label("QUA_PASSIVE_OPTIMIZER_FREQUENCY")
        for gain in self.gains:
            self.safe_regwi(qubit_page, gain_register, int(gain))
            if gain2_register is not None:
                self.safe_regwi(qubit_page, gain2_register, int(gain // 2))
            if passive_reset > 0:
                self.sync_all(self.us2cycles(passive_reset))
            _measure_record(self, delay_us=0.0)
            if passive_reset > 0:
                self.sync_all(self.us2cycles(passive_reset))
            for _ in range(self.drive_pulses):
                self.pulse(ch=cfg["qubit_ch"])
                self.sync_all(self.us2cycles(0.01))
            _measure_record(self, delay_us=0.0)
        self.mathi(
            qubit_page,
            frequency_register,
            frequency_register,
            "+",
            frequency_step,
        )
        self.loopnz(
            0,
            controls["frequency_loop"],
            "QUA_PASSIVE_OPTIMIZER_FREQUENCY",
        )
        self.loopnz(0, controls["shot_loop"], "QUA_PASSIVE_OPTIMIZER_SHOT")
        self.end()

    def acquire_records(self, soc, progress=False, load_pulses=True):
        return _acquire_stream_records(
            self, soc, progress=progress, load_pulses=load_pulses
        )


def _positive_shots(cfg):
    shots = int(cfg.get("shots", cfg.get("reps", 0)))
    if shots <= 0:
        raise ValueError("shots must be positive")
    return shots


def _finite_axis(values, label):
    axis = np.asarray(values, dtype=float).reshape(-1)
    if axis.size == 0 or not np.all(np.isfinite(axis)):
        raise ValueError(f"{label} must contain finite values")
    return axis


def _optional_soc_method(soc, name):
    try:
        method = getattr(soc, name)
    except Exception:
        return None
    return method if callable(method) else None


def _resident_program_records(
    method,
    resident,
    readout_configs,
    shots,
    access_mode="driver",
    command_mode="sequenced",
):
    args = (
        resident.dump_prog(),
        readout_configs,
        resident.frequency_registers.tolist(),
        int(shots),
        resident.command_addr,
        resident.ready_addr,
        resident.frequency_addr,
    )
    kwargs = {}
    if access_mode != "driver":
        kwargs["access_mode"] = access_mode
    if command_mode != "split":
        kwargs["command_mode"] = command_mode
    if not kwargs:
        result = method(*args)
    else:
        result = method(*args, **kwargs)
    if not isinstance(result, dict) or "records" not in result:
        raise RuntimeError("RFSoC resident acquisition returned an invalid result")
    records = np.asarray(result["records"], dtype=float)
    records_per_block = int(
        resident.reps // (int(shots) * len(readout_configs))
    )
    expected = (int(shots), len(readout_configs), records_per_block, 2)
    if records.shape != expected:
        raise RuntimeError(
            f"RFSoC resident readout shape {records.shape} does not match {expected}"
        )
    timing = {
        key: float(result[key])
        for key in (
            "setup_s",
            "handshake_s",
            "acquisition_s",
            "ready_wait_s",
            "frequency_update_s",
            "release_s",
            "stream_drain_s",
        )
        if key in result
    }
    return records, {
        "controller_programs": int(result.get("controller_programs", 1)),
        "readout_reconfigurations": int(
            result.get(
                "readout_reconfigurations", shots * len(readout_configs)
            )
        ),
        "server_timing_s": timing,
        "ready_polls": int(result.get("ready_polls", 0)),
        "frequency_update_mode": str(
            result.get("frequency_update_mode", "unknown")
        ),
        "tproc_access_mode": str(
            result.get("tproc_access_mode", "driver")
        ),
        "command_mode": str(result.get("command_mode", "split")),
    }


def _batch_program_records(soc, first, normal, shots):
    method = _optional_soc_method(soc, "acquire_qick_program_batch")
    if method is None:
        return None
    result = method(
        first.dump_prog(),
        [program.dump_prog() for program in normal],
        int(shots),
        reads_per_rep=1,
    )
    if not isinstance(result, dict) or "records" not in result:
        raise RuntimeError("RFSoC batch acquisition returned an invalid result")
    records = np.asarray(result["records"], dtype=float)
    expected = (
        int(shots),
        len(normal),
        int(first.reps),
        2,
    )
    if records.shape != expected:
        raise RuntimeError(
            f"RFSoC batch readout shape {records.shape} does not match {expected}"
        )
    return records, int(result.get("controller_programs", shots * len(normal)))


def acquire_passive_readout_grid(
    soc,
    soccfg,
    cfg,
    *,
    frequencies_mhz,
    values,
    kind,
    excursion_gain=None,
    progress=None,
    access_mode="direct_mmio",
    command_mode="sequenced",
):
    frequencies = _finite_axis(frequencies_mhz, "frequencies_mhz")
    values = _finite_axis(values, "values")
    shots = _positive_shots(cfg)
    access_mode = str(access_mode)
    if access_mode not in ("driver", "direct_mmio"):
        raise ValueError("invalid resident access mode")
    command_mode = str(command_mode)
    if command_mode not in ("split", "packed_frequency", "sequenced"):
        raise ValueError("invalid resident command mode")
    resident_method = _optional_soc_method(
        soc, "acquire_qick_resident_readout"
    )
    axis_name = "gain" if kind == "readout_gain" else "dc"
    total = shots * frequencies.size
    if resident_method is not None:
        resident_cfg = dict(cfg)
        resident_cfg["qua_assert_park_at_start"] = True
        resident_cfg["qick_resident_command_mode"] = command_mode
        resident = QUAResidentReadoutGridProgram(
            soccfg,
            resident_cfg,
            frequencies_mhz=frequencies,
            values=values,
            kind=kind,
            excursion_gain=excursion_gain,
        )
        if all("freq" in ro_cfg for ro_cfg in resident.ro_chs.values()):
            readout_configs = []
            for frequency in frequencies:
                readout_configs.append(
                    {
                        ch: {**ro_cfg, "freq": float(frequency)}
                        for ch, ro_cfg in resident.ro_chs.items()
                    }
                )
            records, resident_meta = _resident_program_records(
                resident_method,
                resident,
                readout_configs,
                shots,
                access_mode=access_mode,
                command_mode=command_mode,
            )
            if progress is not None:
                progress(total, total)
            return (
                records[..., 0].transpose(1, 2, 0),
                records[..., 1].transpose(1, 2, 0),
                {
                    "shots_per_point": shots,
                    "frequency_points": int(frequencies.size),
                    f"{axis_name}_points": int(values.size),
                    "host_programs": 1,
                    "controller_programs": resident_meta[
                        "controller_programs"
                    ],
                    "readout_reconfigurations": resident_meta[
                        "readout_reconfigurations"
                    ],
                    "server_batches": 1,
                    "resident_handshake": True,
                    "server_timing_s": resident_meta["server_timing_s"],
                    "ready_polls": resident_meta["ready_polls"],
                    "frequency_update_mode": resident_meta[
                        "frequency_update_mode"
                    ],
                    "tproc_access_mode": resident_meta[
                        "tproc_access_mode"
                    ],
                    "command_mode": resident_meta["command_mode"],
                    "records": int(
                        shots * frequencies.size * values.size
                    ),
                    "order": f"shot_frequency_{axis_name}",
                },
            )
    normal = []
    for frequency in frequencies:
        run_cfg = dict(cfg)
        run_cfg["qua_assert_park_at_start"] = False
        kwargs = {
            "read_frequency_mhz": float(frequency),
            "values": values,
            "kind": kind,
        }
        if excursion_gain is not None:
            kwargs["excursion_gain"] = float(excursion_gain)
        normal.append(QUAReadoutFrequencyProgram(soccfg, run_cfg, **kwargs))
    first_cfg = dict(cfg)
    first_cfg["qua_assert_park_at_start"] = True
    first_kwargs = {
        "read_frequency_mhz": float(frequencies[0]),
        "values": values,
        "kind": kind,
    }
    if excursion_gain is not None:
        first_kwargs["excursion_gain"] = float(excursion_gain)
    first = QUAReadoutFrequencyProgram(soccfg, first_cfg, **first_kwargs)
    batched = _batch_program_records(soc, first, normal, shots)
    if batched is not None:
        records, controller_programs = batched
        if progress is not None:
            progress(total, total)
        return (
            records[..., 0].transpose(1, 2, 0),
            records[..., 1].transpose(1, 2, 0),
            {
                "shots_per_point": shots,
                "frequency_points": int(frequencies.size),
                f"{axis_name}_points": int(values.size),
                "host_programs": 1,
                "controller_programs": controller_programs,
                "server_batches": 1,
                "resident_handshake": False,
                "records": int(shots * frequencies.size * values.size),
                "order": f"shot_frequency_{axis_name}",
            },
        )
    i_values = np.empty((shots, frequencies.size, values.size), dtype=float)
    q_values = np.empty_like(i_values)
    done = 0
    for shot in range(shots):
        for frequency_index in range(frequencies.size):
            program = first if shot == 0 and frequency_index == 0 else normal[frequency_index]
            i_row, q_row = program.acquire_records(
                soc, progress=False, load_pulses=(done == 0)
            )
            i_values[shot, frequency_index] = np.asarray(i_row, dtype=float)
            q_values[shot, frequency_index] = np.asarray(q_row, dtype=float)
            done += 1
            if progress is not None:
                progress(done, total)
    return (
        i_values.transpose(1, 2, 0),
        q_values.transpose(1, 2, 0),
        {
            "shots_per_point": shots,
            "frequency_points": int(frequencies.size),
            f"{axis_name}_points": int(values.size),
            "host_programs": int(total),
            "controller_programs": int(total),
            "server_batches": 0,
            "records": int(shots * frequencies.size * values.size),
            "order": f"shot_frequency_{axis_name}",
        },
    )


def acquire_passive_pulse_grid(
    soc,
    soccfg,
    cfg,
    *,
    frequencies_mhz,
    gains,
    pulses,
    progress=False,
):
    frequencies = _finite_axis(frequencies_mhz, "frequencies_mhz")
    gains = _finite_axis(gains, "gains")
    shots = _positive_shots(cfg)
    run_cfg = dict(cfg)
    run_cfg["qua_assert_park_at_start"] = True
    program = QUAPulseGridProgram(
        soccfg,
        run_cfg,
        frequencies_mhz=frequencies,
        gains=gains,
        pulses=int(pulses),
    )
    i_records, q_records = program.acquire_records(soc, progress=progress)
    shape = (shots, frequencies.size, gains.size)
    i_values = np.asarray(i_records, dtype=float).reshape(shape).transpose(1, 2, 0)
    q_values = np.asarray(q_records, dtype=float).reshape(shape).transpose(1, 2, 0)
    return i_values, q_values, {
        "shots_per_point": shots,
        "frequency_points": int(frequencies.size),
        "gain_points": int(gains.size),
        "blocks": 1,
        "records": int(shots * frequencies.size * gains.size),
        "order": "shot_frequency_gain",
    }


def acquire_passive_flux_spectroscopy_grid(
    soc,
    soccfg,
    cfg,
    *,
    frequencies_mhz,
    dc_gains,
    hold_times_us,
    read_frequencies_mhz,
    order,
    baseline_rearm_us,
    post_readout_reset_us,
    readout_after_park,
    progress=None,
):
    frequencies = _finite_axis(frequencies_mhz, "frequencies_mhz")
    dc_values = _finite_axis(dc_gains, "dc_gains")
    hold_times = _finite_axis(hold_times_us, "hold_times_us")
    read_frequencies = _finite_axis(
        read_frequencies_mhz, "read_frequencies_mhz"
    )
    if read_frequencies.size != dc_values.size:
        raise ValueError("read frequencies must have one value per DC point")
    total_shots = _positive_shots(cfg)
    points_per_shot = int(
        frequencies.size * dc_values.size * hold_times.size
    )
    record_limit = int(cfg.get("qua_order_max_records_per_block", 262144))
    if record_limit <= 0:
        raise ValueError("qua_order_max_records_per_block must be positive")
    shots_per_block = max(record_limit // points_per_shot, 1)
    chunks = []
    remaining = total_shots
    while remaining:
        chunk = min(remaining, shots_per_block)
        chunks.append(chunk)
        remaining -= chunk
    i_blocks = []
    q_blocks = []
    completed = 0
    for block_index, chunk in enumerate(chunks):
        run_cfg = dict(cfg)
        run_cfg["qua_assert_park_at_start"] = block_index == 0
        program = QUAFluxSpectroscopyProgram(
            soccfg,
            run_cfg,
            frequencies_mhz=frequencies,
            dc_gains=dc_values,
            hold_times_us=hold_times,
            read_frequencies_mhz=read_frequencies,
            order=order,
            shots=chunk,
            baseline_rearm_us=baseline_rearm_us,
            post_readout_reset_us=post_readout_reset_us,
            readout_after_park=readout_after_park,
        )
        raw_i, raw_q = program.acquire_records(
            soc,
            progress=False,
            load_pulses=block_index == 0,
        )
        if order == "shot_frequency_dc_time":
            block_shape = (
                chunk,
                frequencies.size,
                dc_values.size,
                hold_times.size,
            )
            axes = (1, 2, 3, 0)
        elif order == "shot_dc_frequency_time":
            block_shape = (
                chunk,
                dc_values.size,
                frequencies.size,
                hold_times.size,
            )
            axes = (2, 1, 3, 0)
        else:
            raise ValueError(
                "order must be 'shot_frequency_dc_time' or "
                "'shot_dc_frequency_time'"
            )
        i_blocks.append(
            np.asarray(raw_i, dtype=float).reshape(block_shape).transpose(axes)
        )
        q_blocks.append(
            np.asarray(raw_q, dtype=float).reshape(block_shape).transpose(axes)
        )
        completed += int(chunk)
        if progress is not None:
            progress(completed, total_shots)
    i_values = np.concatenate(i_blocks, axis=3)
    q_values = np.concatenate(q_blocks, axis=3)
    return i_values, q_values, {
        "shots_per_point": int(total_shots),
        "frequency_points": int(frequencies.size),
        "dc_points": int(dc_values.size),
        "time_points": int(hold_times.size),
        "blocks": int(len(chunks)),
        "records": int(total_shots * points_per_shot),
        "order": str(order),
    }


def acquire_passive_optimizer_grid(
    soc,
    soccfg,
    cfg,
    *,
    frequencies_mhz,
    gains,
    kind,
    drive_pulses,
    drive_gain,
    progress=None,
    access_mode="direct_mmio",
    command_mode="sequenced",
):
    frequencies = _finite_axis(frequencies_mhz, "frequencies_mhz")
    gains = _finite_axis(gains, "gains")
    shots = _positive_shots(cfg)
    if kind == "qubit":
        run_cfg = dict(cfg)
        run_cfg["qua_assert_park_at_start"] = True
        program = QUAOptimizerGridProgram(
            soccfg,
            run_cfg,
            frequencies_mhz=frequencies,
            gains=gains,
            drive_pulses=drive_pulses,
        )
        i_records, q_records = program.acquire_records(soc, progress=bool(progress))
        shape = (shots, frequencies.size, gains.size, 2)
        return (
            np.asarray(i_records, dtype=float).reshape(shape),
            np.asarray(q_records, dtype=float).reshape(shape),
            {
                "shots_per_point": shots,
                "frequency_points": int(frequencies.size),
                "gain_points": int(gains.size),
                "states": 2,
                "blocks": 1,
                "records": int(np.prod(shape, dtype=int)),
                "order": "shot_frequency_gain_state",
            },
        )
    access_mode = str(access_mode)
    if access_mode not in ("driver", "direct_mmio"):
        raise ValueError("invalid resident access mode")
    command_mode = str(command_mode)
    if command_mode not in ("split", "packed_frequency", "sequenced"):
        raise ValueError("invalid resident command mode")
    resident_method = _optional_soc_method(
        soc, "acquire_qick_resident_readout"
    )
    total = shots * frequencies.size
    if resident_method is not None:
        resident_cfg = dict(cfg)
        resident_cfg["qua_assert_park_at_start"] = True
        resident_cfg["qick_resident_command_mode"] = command_mode
        resident = QUAResidentReadoutOptimizerProgram(
            soccfg,
            resident_cfg,
            frequencies_mhz=frequencies,
            gains=gains,
            drive_pulses=drive_pulses,
            drive_gain=drive_gain,
        )
        if all("freq" in ro_cfg for ro_cfg in resident.ro_chs.values()):
            readout_configs = [
                {
                    ch: {**ro_cfg, "freq": float(frequency)}
                    for ch, ro_cfg in resident.ro_chs.items()
                }
                for frequency in frequencies
            ]
            records, resident_meta = _resident_program_records(
                resident_method,
                resident,
                readout_configs,
                shots,
                access_mode=access_mode,
                command_mode=command_mode,
            )
            shape = (shots, frequencies.size, gains.size, 2)
            if progress is not None:
                progress(total, total)
            return (
                records[..., 0].reshape(shape),
                records[..., 1].reshape(shape),
                {
                    "shots_per_point": shots,
                    "frequency_points": int(frequencies.size),
                    "gain_points": int(gains.size),
                    "states": 2,
                    "host_programs": 1,
                    "controller_programs": resident_meta[
                        "controller_programs"
                    ],
                    "readout_reconfigurations": resident_meta[
                        "readout_reconfigurations"
                    ],
                    "server_batches": 1,
                    "resident_handshake": True,
                    "server_timing_s": resident_meta["server_timing_s"],
                    "ready_polls": resident_meta["ready_polls"],
                    "frequency_update_mode": resident_meta[
                        "frequency_update_mode"
                    ],
                    "tproc_access_mode": resident_meta[
                        "tproc_access_mode"
                    ],
                    "command_mode": resident_meta["command_mode"],
                    "records": int(
                        shots * frequencies.size * gains.size * 2
                    ),
                    "order": "shot_frequency_gain_state",
                },
            )
    normal = []
    for frequency in frequencies:
        run_cfg = dict(cfg)
        run_cfg["qua_assert_park_at_start"] = False
        normal.append(QUAOptimizerFrequencyProgram(
            soccfg,
            run_cfg,
            frequency_mhz=float(frequency),
            gains=gains,
            kind=kind,
            drive_pulses=drive_pulses,
            drive_gain=drive_gain,
        ))
    first_cfg = dict(cfg)
    first_cfg["qua_assert_park_at_start"] = True
    first = QUAOptimizerFrequencyProgram(
        soccfg,
        first_cfg,
        frequency_mhz=float(frequencies[0]),
        gains=gains,
        kind=kind,
        drive_pulses=drive_pulses,
        drive_gain=drive_gain,
    )
    batched = _batch_program_records(soc, first, normal, shots)
    if batched is not None:
        records, controller_programs = batched
        shape = (shots, frequencies.size, gains.size, 2)
        if progress is not None:
            progress(total, total)
        return (
            records[..., 0].reshape(shape),
            records[..., 1].reshape(shape),
            {
                "shots_per_point": shots,
                "frequency_points": int(frequencies.size),
                "gain_points": int(gains.size),
                "states": 2,
                "host_programs": 1,
                "controller_programs": controller_programs,
                "server_batches": 1,
                "records": int(shots * frequencies.size * gains.size * 2),
                "order": "shot_frequency_gain_state",
            },
        )
    i_values = np.empty((shots, frequencies.size, gains.size, 2), dtype=float)
    q_values = np.empty_like(i_values)
    done = 0
    for shot in range(shots):
        for frequency_index in range(frequencies.size):
            program = first if shot == 0 and frequency_index == 0 else normal[frequency_index]
            i_row, q_row = program.acquire_records(
                soc, progress=False, load_pulses=(done == 0)
            )
            i_values[shot, frequency_index] = np.asarray(i_row, dtype=float).reshape(
                gains.size, 2
            )
            q_values[shot, frequency_index] = np.asarray(q_row, dtype=float).reshape(
                gains.size, 2
            )
            done += 1
            if progress is not None:
                progress(done, total)
    return i_values, q_values, {
        "shots_per_point": shots,
        "frequency_points": int(frequencies.size),
        "gain_points": int(gains.size),
        "states": 2,
        "host_programs": int(total),
        "controller_programs": int(total),
        "server_batches": 0,
        "records": int(shots * frequencies.size * gains.size * 2),
        "order": "shot_frequency_gain_state",
    }
