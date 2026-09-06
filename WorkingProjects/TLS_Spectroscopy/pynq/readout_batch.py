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
