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
):
    frequencies = _finite_axis(frequencies_mhz, "frequencies_mhz")
    values = _finite_axis(values, "values")
    shots = _positive_shots(cfg)
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
    i_values = np.empty((shots, frequencies.size, values.size), dtype=float)
    q_values = np.empty_like(i_values)
    total = shots * frequencies.size
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
    axis_name = "gain" if kind == "readout_gain" else "dc"
    return (
        i_values.transpose(1, 2, 0),
        q_values.transpose(1, 2, 0),
        {
            "shots_per_point": shots,
            "frequency_points": int(frequencies.size),
            f"{axis_name}_points": int(values.size),
            "host_programs": int(total),
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
    i_values = np.empty((shots, frequencies.size, gains.size, 2), dtype=float)
    q_values = np.empty_like(i_values)
    total = shots * frequencies.size
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
        "records": int(shots * frequencies.size * gains.size * 2),
        "order": "shot_frequency_gain_state",
    }
