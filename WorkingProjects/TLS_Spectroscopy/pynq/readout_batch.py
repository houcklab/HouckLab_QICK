import queue
import threading
import time

import numpy as np


_DMEM_READ_LOCK = threading.Lock()


def bounded_poll_timeout(timeout, default_s=0.25):
    """Keep a disconnected Pyro client from holding a poll worker forever."""
    return float(default_s) if timeout is None else float(timeout)


def _drain_queue(values):
    count = 0
    while True:
        try:
            values.get_nowait()
            count += 1
        except queue.Empty:
            return count


def cleanup_qick_readout(
    soc,
    *,
    wake_pollers=8,
    wake_wait_s=0.1,
):
    """Stop acquisition and wake Pyro calls abandoned by interrupted clients."""
    wake_pollers = max(int(wake_pollers), 1)
    wake_wait_s = max(float(wake_wait_s), 0.0)
    streamer = soc.streamer
    was_running = bool(streamer.readout_running())
    try:
        soc.tproc.reset()
    except Exception:
        soc.tproc.stop()
    streamer.stop_flag.set()
    if was_running:
        streamer.stop_readout()
    streamer.done_flag.wait(timeout=1.0)

    dropped_data = _drain_queue(streamer.data_queue)
    dropped_errors = _drain_queue(streamer.error_queue)
    for _ in range(wake_pollers):
        streamer.data_queue.put((0, None))
    if wake_wait_s:
        time.sleep(wake_wait_s)
    unused_wake_packets = _drain_queue(streamer.data_queue)
    streamer.stop_flag.clear()
    return {
        "was_running": was_running,
        "streamer_running": bool(streamer.readout_running()),
        "dropped_data_packets": int(dropped_data),
        "dropped_errors": int(dropped_errors),
        "wake_packets_consumed": int(wake_pollers - unused_wake_packets),
    }


def _allocate_qick_dmem_buffer(length):
    from pynq import allocate

    return allocate(shape=int(length), dtype=np.int32)


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


def _prepare_readout_frequency_updates(soc, readout_configs):
    updates = []
    for config in readout_configs:
        prepared = []
        for ch, cfg in config.items():
            try:
                buffer = soc.avg_bufs[int(ch)]
                if hasattr(buffer, "readoutport"):
                    return None
                readout = buffer.readout
                setter = readout.set_freq_int
                buffer.set_freq(float(cfg["freq"]), gen_ch=cfg["gen_ch"])
                frequency_register = int(readout.freq_reg)
            except (AttributeError, IndexError, KeyError, TypeError):
                return None
            prepared.append((setter, frequency_register))
        updates.append(tuple(prepared))
    return tuple(updates)


def _apply_readout_frequency_update(update):
    for setter, frequency_register in update:
        setter(frequency_register)


def _prepare_direct_readout_frequency_updates(soc, readout_configs):
    updates = []
    for config in readout_configs:
        prepared = []
        for ch, cfg in config.items():
            try:
                buffer = soc.avg_bufs[int(ch)]
                if hasattr(buffer, "readoutport"):
                    return None
                readout = buffer.readout
                registers = readout.REGISTERS
                memory = readout.mmio.array
                frequency_index = int(registers["freq_reg"])
                write_enable_index = int(registers["we_reg"])
                buffer.set_freq(float(cfg["freq"]), gen_ch=cfg["gen_ch"])
                frequency_register = int(readout.freq_reg)
            except (AttributeError, IndexError, KeyError, TypeError):
                return None
            prepared.append(
                (
                    memory,
                    frequency_index,
                    write_enable_index,
                    frequency_register,
                )
            )
        updates.append(tuple(prepared))
    return tuple(updates)


def _apply_direct_readout_frequency_update(update):
    for (
        memory,
        frequency_index,
        write_enable_index,
        frequency_register,
    ) in update:
        memory[frequency_index] = np.uint32(frequency_register)
        memory[write_enable_index] = np.uint32(1)
        memory[write_enable_index] = np.uint32(0)


def _direct_tproc_memory(tproc):
    try:
        return tproc.mmio.array, int(tproc.NREG)
    except (AttributeError, TypeError, ValueError):
        return None


def _read_tproc(tproc, address, direct_memory=None):
    if direct_memory is None:
        return int(tproc.single_read(addr=address))
    memory, offset = direct_memory
    return int(memory[offset + int(address)])


def _write_tproc(tproc, address, value, direct_memory=None):
    if direct_memory is None:
        tproc.single_write(addr=address, data=value)
        return
    memory, offset = direct_memory
    memory[offset + int(address)] = np.uint32(value)


def _wait_for_ready(
    tproc, ready_addr, expected, timeout_s, direct_memory=None
):
    deadline = time.monotonic() + float(timeout_s)
    polls = 0
    ahead_value = None
    ahead_reads = 0
    while True:
        polls += 1
        ready = _read_tproc(tproc, ready_addr, direct_memory=direct_memory)
        if ready == expected:
            return polls
        if ready > expected:
            if ready == ahead_value:
                ahead_reads += 1
            else:
                ahead_value = ready
                ahead_reads = 1
            if ahead_reads >= 3:
                raise RuntimeError(
                    f"resident tProcessor advanced to block {ready} before {expected}"
                )
        else:
            ahead_value = None
            ahead_reads = 0
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"resident tProcessor did not request block {expected}"
            )


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


def _has_reusable_dmem_reader(tproc):
    try:
        receive = tproc.dma.recvchannel
    except Exception:
        return False
    return all(
        hasattr(tproc, name)
        for name in (
            "mem_mode_reg",
            "mem_addr_reg",
            "mem_len_reg",
            "mem_start_reg",
        )
    ) and callable(getattr(receive, "transfer", None)) and callable(
        getattr(receive, "wait", None)
    )


def _read_qick_dmem_reusable(tproc, address, length, dmem_size):
    capacity = int(dmem_size) if dmem_size is not None else int(length)
    capacity = max(capacity, int(length))
    buffer = getattr(tproc, "_qick_reusable_dmem_read_buffer", None)
    if buffer is None or int(np.asarray(buffer).size) < capacity:
        previous = buffer
        buffer = _allocate_qick_dmem_buffer(capacity)
        tproc._qick_reusable_dmem_read_buffer = buffer
        release = getattr(previous, "freebuffer", None)
        if callable(release):
            release()

    tproc.mem_mode_reg = 0
    tproc.mem_addr_reg = int(address)
    tproc.mem_len_reg = int(length)
    tproc.mem_start_reg = 1
    try:
        try:
            tproc.dma.recvchannel.transfer(buffer, nbytes=int(length) * 4)
        except TypeError:
            tproc.dma.recvchannel.transfer(buffer[:length])
        tproc.dma.recvchannel.wait()
        return np.asarray(buffer)[:length].copy()
    finally:
        tproc.mem_start_reg = 0


def _has_reusable_dmem_writer(tproc):
    try:
        send = tproc.dma.sendchannel
    except Exception:
        return False
    return all(
        hasattr(tproc, name)
        for name in (
            "mem_mode_reg",
            "mem_addr_reg",
            "mem_len_reg",
            "mem_start_reg",
        )
    ) and callable(getattr(send, "transfer", None)) and callable(
        getattr(send, "wait", None)
    )


def _write_qick_dmem_reusable(tproc, address, words):
    length = int(words.size)
    buffer = getattr(tproc, "_qick_reusable_dmem_write_buffer", None)
    if buffer is None or int(np.asarray(buffer).size) < length:
        previous = buffer
        buffer = _allocate_qick_dmem_buffer(length)
        tproc._qick_reusable_dmem_write_buffer = buffer
        release = getattr(previous, "freebuffer", None)
        if callable(release):
            release()
    np.copyto(buffer[:length], words.view(np.int32))

    tproc.mem_mode_reg = 1
    tproc.mem_addr_reg = int(address)
    tproc.mem_len_reg = length
    tproc.mem_start_reg = 1
    try:
        try:
            tproc.dma.sendchannel.transfer(buffer, nbytes=length * 4)
        except TypeError:
            tproc.dma.sendchannel.transfer(buffer[:length])
        tproc.dma.sendchannel.wait()
    finally:
        tproc.mem_start_reg = 0


def read_qick_dmem(soc, address, length):
    address = int(address)
    length = int(length)
    if address < 0 or length <= 0:
        raise ValueError("DMem address must be non-negative and length must be positive")
    dmem_size = _tproc_dmem_size(soc)
    if dmem_size is not None and address + length > dmem_size:
        raise ValueError("DMem read exceeds tProcessor data memory")
    tproc = soc.tproc
    reader = getattr(tproc, "read_dmem", None)
    values = None
    try:
        if _has_reusable_dmem_reader(tproc):
            with _DMEM_READ_LOCK:
                values = _read_qick_dmem_reusable(
                    tproc,
                    address,
                    length,
                    dmem_size,
                )
            words = values
        elif callable(reader):
            values = reader(address, length)
            words = np.asarray(values).reshape(-1)
        else:
            words = np.asarray(
                [tproc.single_read(addr=address + offset)
                 for offset in range(length)]
            )
        if words.size < length:
            raise RuntimeError(
                f"DMem reader returned {words.size} words; expected {length}"
            )
        return words[:length].astype(np.uint32).astype(np.uint64).tolist()
    finally:
        release = getattr(values, "freebuffer", None)
        if callable(release) and values is not getattr(
            tproc, "_qick_reusable_dmem_read_buffer", None
        ):
            release()


def write_qick_dmem(soc, address, values):
    address = int(address)
    words = np.asarray(values, dtype=np.int64).reshape(-1).astype(np.uint32)
    length = int(words.size)
    if address < 0 or length <= 0:
        raise ValueError("DMem address must be non-negative and values must be nonempty")
    dmem_size = _tproc_dmem_size(soc)
    if dmem_size is not None and address + length > dmem_size:
        raise ValueError("DMem write exceeds tProcessor data memory")
    tproc = soc.tproc
    loader = getattr(tproc, "load_dmem", None)
    if _has_reusable_dmem_writer(tproc):
        with _DMEM_READ_LOCK:
            _write_qick_dmem_reusable(tproc, address, words)
    elif callable(loader):
        loader(words.view(np.int32), addr=address)
    else:
        for offset, value in enumerate(words):
            tproc.single_write(
                addr=address + offset,
                data=int(value),
            )
    return length


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


def _store_stream_chunks(chunks, d_buf, count, total_records):
    for data, _ in chunks:
        block = np.asarray(data)
        if block.ndim != 3 or block.shape[0] != d_buf.shape[0]:
            raise RuntimeError(f"invalid streamed readout shape {block.shape}")
        new_points = int(block.shape[1])
        if count + new_points > total_records:
            raise RuntimeError("streamed readout exceeded the expected record count")
        d_buf[:, count:count + new_points] = block
        count += new_points
    return count


def _resident_stream_schedule(soc, ro_channels, records_per_block):
    capacities = []
    for channel in ro_channels:
        try:
            capacities.append(int(soc.get_avg_max_length(int(channel))))
        except Exception:
            pass
    capacity = min(capacities) if capacities else 16384
    if capacity <= 0:
        capacity = 16384
    stride = max(1, min(2048, capacity // 8))
    drain_blocks = max(1, min(64, stride // int(records_per_block)))
    return capacity, stride, drain_blocks


def _start_resident_stream(soc, total_records, counter_addr, ro_channels, stride):
    values = {
        "counter_addr": counter_addr,
        "ch_list": list(ro_channels),
        "reads_per_rep": 1,
    }
    try:
        soc.start_readout(total_records, stride=stride, **values)
    except TypeError as exc:
        if "stride" not in str(exc):
            raise
        soc.start_readout(total_records, **values)


def acquire_qick_resident_readout(
    soc,
    program_values,
    readout_configs,
    frequency_registers,
    shots,
    command_addr,
    ready_addr,
    frequency_addr,
    access_mode="driver",
    command_mode="split",
    timeout_s=10.0,
    program_factory=None,
):
    shots = int(shots)
    timeout_s = float(timeout_s)
    command_addr = int(command_addr)
    ready_addr = int(ready_addr)
    frequency_addr = int(frequency_addr)
    access_mode = str(access_mode)
    command_mode = str(command_mode)
    if shots <= 0:
        raise ValueError("shots must be positive")
    if timeout_s <= 0:
        raise ValueError("timeout_s must be positive")
    if len({command_addr, ready_addr, frequency_addr}) != 3:
        raise ValueError("resident handshake addresses must be distinct")
    if min(command_addr, ready_addr, frequency_addr) < 0:
        raise ValueError("resident handshake addresses must be non-negative")
    if access_mode not in ("driver", "direct_mmio"):
        raise ValueError("invalid resident access mode")
    if command_mode not in ("split", "packed_frequency", "sequenced"):
        raise ValueError("invalid resident command mode")
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
    stream_capacity, stream_stride, stream_drain_blocks = (
        _resident_stream_schedule(soc, ro_channels, records_per_block)
    )
    setup_started = time.perf_counter()
    program.load_pulses(soc)
    program.config_gens(soc)
    compiled = program.compile()
    soc.init_readouts()
    _configure_readouts(soc, configurations[0])
    direct_memory = None
    if access_mode == "direct_mmio":
        frequency_updates = _prepare_direct_readout_frequency_updates(
            soc, configurations
        )
        direct_memory = _direct_tproc_memory(soc.tproc)
        if frequency_updates is None or direct_memory is None:
            raise RuntimeError("direct resident MMIO access is unavailable")
    else:
        frequency_updates = _prepare_readout_frequency_updates(
            soc, configurations
        )
    soc.load_bin_program(compiled, reset=False)
    soc.start_src("internal")
    program.config_bufs(soc, enable_avg=True, enable_buf=False)
    soc.tproc.single_write(addr=command_addr, data=0)
    soc.tproc.single_write(addr=ready_addr, data=0)
    soc.tproc.single_write(addr=frequency_addr, data=0)
    setup_s = time.perf_counter() - setup_started
    acquisition_started = time.perf_counter()
    try:
        _start_resident_stream(
            soc,
            total_records,
            program.counter_addr,
            ro_channels,
            stream_stride,
        )
        d_buf = np.zeros(
            (len(ro_channels), total_records, 2), dtype=np.int32
        )
        count = 0
        handshake_started = time.perf_counter()
        ready_wait_s = 0.0
        frequency_update_s = 0.0
        release_s = 0.0
        stream_drain_s = 0.0
        ready_polls = 0
        for block in range(total_blocks):
            phase_started = time.perf_counter()
            ready_polls += _wait_for_ready(
                soc.tproc,
                ready_addr,
                block + 1,
                timeout_s,
                direct_memory=direct_memory,
            )
            ready_wait_s += time.perf_counter() - phase_started
            frequency_index = block % len(configurations)
            phase_started = time.perf_counter()
            if access_mode == "direct_mmio":
                _apply_direct_readout_frequency_update(
                    frequency_updates[frequency_index]
                )
            elif frequency_updates is None:
                _set_readout_frequencies(
                    soc, configurations[frequency_index]
                )
            else:
                _apply_readout_frequency_update(
                    frequency_updates[frequency_index]
                )
            frequency_update_s += time.perf_counter() - phase_started
            phase_started = time.perf_counter()
            if command_mode == "packed_frequency":
                _write_tproc(
                    soc.tproc,
                    command_addr,
                    registers[frequency_index],
                    direct_memory=direct_memory,
                )
            else:
                _write_tproc(
                    soc.tproc,
                    frequency_addr,
                    registers[frequency_index],
                    direct_memory=direct_memory,
                )
                _write_tproc(
                    soc.tproc,
                    command_addr,
                    block + 1 if command_mode == "sequenced" else 1,
                    direct_memory=direct_memory,
                )
            release_s += time.perf_counter() - phase_started
            if (block + 1) % stream_drain_blocks == 0:
                phase_started = time.perf_counter()
                count = _store_stream_chunks(
                    soc.poll_data(timeout=0),
                    d_buf,
                    count,
                    total_records,
                )
                time.sleep(0)
                stream_drain_s += time.perf_counter() - phase_started
        handshake_s = time.perf_counter() - handshake_started
        last_progress = time.monotonic()
        while count < total_records:
            phase_started = time.perf_counter()
            chunks = soc.poll_data(timeout=min(timeout_s, 0.1))
            previous_count = count
            count = _store_stream_chunks(
                chunks,
                d_buf,
                count,
                total_records,
            )
            stream_drain_s += time.perf_counter() - phase_started
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
        "ready_wait_s": float(ready_wait_s),
        "frequency_update_s": float(frequency_update_s),
        "release_s": float(release_s),
        "stream_drain_s": float(stream_drain_s),
        "stream_capacity_records": int(stream_capacity),
        "stream_stride_records": int(stream_stride),
        "stream_drain_blocks": int(stream_drain_blocks),
        "ready_polls": int(ready_polls),
        "frequency_update_mode": (
            "direct_mmio_latched"
            if access_mode == "direct_mmio"
            else (
                "dynamic"
                if frequency_updates is None
                else "precomputed_register"
            )
        ),
        "tproc_access_mode": access_mode,
        "command_mode": command_mode,
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
        access_mode="driver",
        command_mode="split",
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
            access_mode=access_mode,
            command_mode=command_mode,
        )

    def dmem_read(self, address, length):
        return read_qick_dmem(self, address, length)

    def dmem_write(self, address, values):
        return write_qick_dmem(self, address, values)

    qicksoc_class.acquire_qick_program_batch = program_batch
    qicksoc_class.acquire_qick_resident_readout = resident_readout
    qicksoc_class.read_qick_dmem = dmem_read
    qicksoc_class.write_qick_dmem = dmem_write
    return qicksoc_class
