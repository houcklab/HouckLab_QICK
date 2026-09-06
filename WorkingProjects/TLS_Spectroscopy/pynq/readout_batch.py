import time

import numpy as np


def _make_program(soc, values, program_factory):
    if program_factory is None:
        from qick import QickProgram

        program_factory = QickProgram
    program = program_factory(soc)
    program.load_prog(values)
    return program


def _record_count(program, reads_per_rep):
    expts = 1 if program.expts is None else int(program.expts)
    return expts * int(program.reps) * int(reads_per_rep)


def _acquire_once(soc, program, compiled, reads_per_rep):
    total_reps = _record_count(program, 1)
    total_count = _record_count(program, reads_per_rep)
    ro_channels = list(program.ro_chs)
    d_buf = np.zeros((len(ro_channels), total_count, 2), dtype=np.int32)
    program.config_readouts(soc)
    soc.load_bin_program(compiled, reset=False)
    soc.start_src("internal")
    program.config_bufs(soc, enable_avg=True, enable_buf=False)
    soc.start_readout(
        total_reps,
        counter_addr=program.counter_addr,
        ch_list=ro_channels,
        reads_per_rep=reads_per_rep,
    )
    count = 0
    while count < total_count:
        for data, _ in soc.poll_data():
            block = np.asarray(data)
            if block.ndim != 3 or block.shape[0] != len(ro_channels):
                raise RuntimeError(f"invalid streamed readout shape {block.shape}")
            new_points = int(block.shape[1])
            if count + new_points > total_count:
                raise RuntimeError("streamed readout exceeded the expected record count")
            d_buf[:, count:count + new_points] = block
            count += new_points
    return d_buf


def acquire_qick_program_batch(
    soc,
    first_program,
    programs,
    shots,
    reads_per_rep=1,
    program_factory=None,
):
    shots = int(shots)
    reads_per_rep = int(reads_per_rep)
    if shots <= 0 or reads_per_rep <= 0:
        raise ValueError("shots and reads_per_rep must be positive")
    program_values = list(programs)
    if not program_values:
        raise ValueError("programs must not be empty")
    first = _make_program(soc, first_program, program_factory)
    normal = [
        _make_program(soc, values, program_factory) for values in program_values
    ]
    all_programs = [first] + normal
    if any(int(program.rounds) != 1 for program in all_programs):
        raise ValueError("batched program rounds must equal one")
    record_counts = {
        _record_count(program, reads_per_rep) for program in all_programs
    }
    if len(record_counts) != 1:
        raise ValueError("batched programs must have identical record counts")
    ro_channels = [tuple(program.ro_chs) for program in all_programs]
    if len(set(ro_channels)) != 1 or not ro_channels[0]:
        raise ValueError("batched programs must have identical readout channels")
    first_ro = ro_channels[0][0]
    read_lengths = {
        int(program.ro_chs[first_ro]["length"]) for program in all_programs
    }
    if len(read_lengths) != 1 or next(iter(read_lengths)) <= 0:
        raise ValueError("batched programs must have one positive readout length")
    first.load_pulses(soc)
    first.config_gens(soc)
    compiled_first = first.compile()
    compiled_normal = [program.compile() for program in normal]
    records_per_program = next(iter(record_counts))
    records = np.empty(
        (shots, len(normal), records_per_program, 2), dtype=float
    )
    read_length = next(iter(read_lengths))
    for shot in range(shots):
        for frequency_index, program in enumerate(normal):
            if shot == 0 and frequency_index == 0:
                selected = first
                compiled = compiled_first
            else:
                selected = program
                compiled = compiled_normal[frequency_index]
            d_buf = _acquire_once(soc, selected, compiled, reads_per_rep)
            records[shot, frequency_index] = d_buf[0] / read_length
    return {
        "records": records,
        "controller_programs": int(shots * len(normal)),
    }


def _configure_readouts(soc, readout_config):
    for ch, cfg in readout_config.items():
        soc.configure_readout(
            int(ch),
            output=cfg["sel"],
            frequency=float(cfg["freq"]),
            gen_ch=cfg["gen_ch"],
        )


def _set_readout_frequencies(soc, readout_config):
    for ch, cfg in readout_config.items():
        try:
            soc.avg_bufs[int(ch)].set_freq(
                float(cfg["freq"]), gen_ch=cfg["gen_ch"]
            )
        except (AttributeError, IndexError, TypeError):
            soc.configure_readout(
                int(ch),
                output=cfg["sel"],
                frequency=float(cfg["freq"]),
                gen_ch=cfg["gen_ch"],
            )


def _wait_for_ready(tproc, ready_addr, expected, timeout_s):
    deadline = time.monotonic() + float(timeout_s)
    while True:
        ready = int(tproc.single_read(addr=ready_addr))
        if ready == expected:
            return
        if ready > expected:
            raise RuntimeError(
                f"resident tProcessor advanced to block {ready} before {expected}"
            )
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"resident tProcessor did not request block {expected}"
            )
        time.sleep(0)


def _tproc_dmem_size(soc):
    try:
        cfg = soc.get_cfg()
    except Exception:
        try:
            cfg = soc
            return int(cfg["tprocs"][0]["dmem_size"])
        except Exception:
            return None
    try:
        return int(cfg["tprocs"][0]["dmem_size"])
    except Exception:
        return None


def _abort_resident_readout(soc):
    try:
        soc.tproc.reset()
    except Exception:
        try:
            soc.tproc.stop()
        except Exception:
            pass
    try:
        streamer = soc.streamer
        if streamer.readout_running():
            streamer.stop_readout()
            streamer.done_flag.wait(timeout=1.0)
    except Exception:
        pass


def acquire_qick_resident_readout(
    soc,
    program_values,
    readout_configs,
    frequency_registers,
    shots,
    command_addr,
    ready_addr,
    frequency_addr,
    timeout_s=10.0,
    program_factory=None,
):
    shots = int(shots)
    timeout_s = float(timeout_s)
    command_addr = int(command_addr)
    ready_addr = int(ready_addr)
    frequency_addr = int(frequency_addr)
    if shots <= 0:
        raise ValueError("shots must be positive")
    if timeout_s <= 0:
        raise ValueError("timeout_s must be positive")
    if len({command_addr, ready_addr, frequency_addr}) != 3:
        raise ValueError("resident handshake addresses must be distinct")
    if min(command_addr, ready_addr, frequency_addr) < 0:
        raise ValueError("resident handshake addresses must be non-negative")
    dmem_size = _tproc_dmem_size(soc)
    if dmem_size is not None and max(
        command_addr, ready_addr, frequency_addr
    ) >= dmem_size:
        raise ValueError(
            "resident handshake addresses exceed tProcessor data memory"
        )
    configurations = list(readout_configs)
    registers = [int(value) for value in frequency_registers]
    if not configurations or len(configurations) != len(registers):
        raise ValueError("readout configurations and frequency registers must match")
    if any(value < 0 or value >= 2**32 for value in registers):
        raise ValueError("frequency registers must be unsigned 32-bit values")
    program = _make_program(soc, program_values, program_factory)
    if int(program.rounds) != 1:
        raise ValueError("resident program rounds must equal one")
    total_blocks = shots * len(configurations)
    total_records = _record_count(program, 1)
    if total_records % total_blocks:
        raise ValueError("resident program records must divide into frequency blocks")
    records_per_block = total_records // total_blocks
    ro_channels = tuple(program.ro_chs)
    if not ro_channels:
        raise ValueError("resident program must declare a readout channel")
    for config in configurations:
        if tuple(config) != ro_channels:
            raise ValueError("resident readout configurations must use identical channels")
    first_ro = ro_channels[0]
    read_lengths = {
        int(config[first_ro]["length"]) for config in configurations
    }
    if len(read_lengths) != 1 or next(iter(read_lengths)) <= 0:
        raise ValueError("resident readout lengths must match and be positive")
    setup_started = time.perf_counter()
    program.load_pulses(soc)
    program.config_gens(soc)
    compiled = program.compile()
    soc.init_readouts()
    _configure_readouts(soc, configurations[0])
    soc.load_bin_program(compiled, reset=False)
    soc.start_src("internal")
    program.config_bufs(soc, enable_avg=True, enable_buf=False)
    soc.tproc.single_write(addr=command_addr, data=0)
    soc.tproc.single_write(addr=ready_addr, data=0)
    soc.tproc.single_write(addr=frequency_addr, data=0)
    setup_s = time.perf_counter() - setup_started
    acquisition_started = time.perf_counter()
    try:
        soc.start_readout(
            total_records,
            counter_addr=program.counter_addr,
            ch_list=list(ro_channels),
            reads_per_rep=1,
        )
        handshake_started = time.perf_counter()
        for block in range(total_blocks):
            _wait_for_ready(
                soc.tproc,
                ready_addr,
                block + 1,
                timeout_s,
            )
            frequency_index = block % len(configurations)
            _set_readout_frequencies(soc, configurations[frequency_index])
            soc.tproc.single_write(
                addr=frequency_addr,
                data=registers[frequency_index],
            )
            soc.tproc.single_write(addr=command_addr, data=1)
        handshake_s = time.perf_counter() - handshake_started
        d_buf = np.zeros(
            (len(ro_channels), total_records, 2), dtype=np.int32
        )
        count = 0
        last_progress = time.monotonic()
        while count < total_records:
            chunks = soc.poll_data(timeout=min(timeout_s, 0.1))
            previous_count = count
            for data, _ in chunks:
                block = np.asarray(data)
                if block.ndim != 3 or block.shape[0] != len(ro_channels):
                    raise RuntimeError(
                        f"invalid streamed readout shape {block.shape}"
                    )
                new_points = int(block.shape[1])
                if count + new_points > total_records:
                    raise RuntimeError(
                        "streamed readout exceeded the expected record count"
                    )
                d_buf[:, count:count + new_points] = block
                count += new_points
            if count > previous_count:
                last_progress = time.monotonic()
            elif time.monotonic() - last_progress >= timeout_s:
                raise TimeoutError(
                    "resident streamed readout made no progress"
                )
    except Exception:
        _abort_resident_readout(soc)
        raise
    acquisition_s = time.perf_counter() - acquisition_started
    read_length = next(iter(read_lengths))
    records = (d_buf[0] / read_length).reshape(
        shots,
        len(configurations),
        records_per_block,
        2,
    )
    return {
        "records": records,
        "controller_programs": 1,
        "readout_reconfigurations": int(total_blocks),
        "setup_s": float(setup_s),
        "handshake_s": float(handshake_s),
        "acquisition_s": float(acquisition_s),
    }


def install_qicksoc_batch_methods(qicksoc_class=None):
    if qicksoc_class is None:
        from qick import QickSoc

        qicksoc_class = QickSoc

    def program_batch(self, first_program, programs, shots, reads_per_rep=1):
        return acquire_qick_program_batch(
            self,
            first_program,
            programs,
            shots,
            reads_per_rep=reads_per_rep,
        )

    def resident_readout(
        self,
        program,
        readout_configs,
        frequency_registers,
        shots,
        command_addr,
        ready_addr,
        frequency_addr,
    ):
        return acquire_qick_resident_readout(
            self,
            program,
            readout_configs,
            frequency_registers,
            shots,
            command_addr,
            ready_addr,
            frequency_addr,
        )

    qicksoc_class.acquire_qick_program_batch = program_batch
    qicksoc_class.acquire_qick_resident_readout = resident_readout
    return qicksoc_class
