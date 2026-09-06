import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import (
    readout_thermalization_us,
)

from .acquisition import (
    AcquisitionTimeout,
    chunk_sizes,
    dmem_words_from_soccfg,
    run_dmem_block,
)
from .calibration import CalibrationBundle
from .programs import (
    OPXResetPulseSweepProgram,
    OPXResetTLSMemoryProgram,
    OPXResetT13PointProgram,
    OPXResetT1Program,
    OPXResetT1SweepProgram,
)
from .records import (
    PAYLOAD_RECORD_WORDS,
    RECORD_WORDS,
    TerminalStatus,
    max_records,
)


def runtime_bundle(cfg):
    value = cfg.get("opx_reset_calibration") if hasattr(cfg, "get") else None
    if isinstance(value, CalibrationBundle):
        return value
    if isinstance(value, dict):
        return CalibrationBundle.from_dict(value)
    raise ValueError(
        "reset_mode='opx_unbounded' requires cfg['opx_reset_calibration']"
    )


def payload_iq(records, read_length_cycles):
    cycles = int(read_length_cycles)
    if cycles <= 0:
        raise ValueError("read_length_cycles must be positive")
    records = list(records)
    i_values = np.asarray([record.final_i for record in records], dtype=float) / cycles
    q_values = np.asarray([record.final_q for record in records], dtype=float) / cycles
    return i_values, q_values


def classify_payload_iq(cfg, i_values, q_values, read_length_cycles):
    cycles = int(read_length_cycles)
    if cycles <= 0:
        raise ValueError("read_length_cycles must be positive")
    calibration = runtime_bundle(cfg).payload
    raw_i = np.rint(np.asarray(i_values, dtype=float) * cycles).astype(np.int64)
    raw_q = np.rint(np.asarray(q_values, dtype=float) * cycles).astype(np.int64)
    projected = calibration.project(raw_i, raw_q)
    return (projected > int(calibration.excited_threshold)).astype(int)


def reset_telemetry(records):
    records = list(records)
    if not records:
        return {
            "shots": 0,
            "mean_reset_attempts": float("nan"),
            "p95_reset_attempts": float("nan"),
            "p99_reset_attempts": float("nan"),
            "max_reset_attempts": 0,
            "mean_pi_pulses": float("nan"),
        }
    attempts = np.asarray([record.reset_attempts for record in records], dtype=float)
    pi_pulses = np.asarray([record.pi_pulses for record in records], dtype=float)
    return {
        "shots": len(records),
        "mean_reset_attempts": float(np.mean(attempts)),
        "p95_reset_attempts": float(np.percentile(attempts, 95)),
        "p99_reset_attempts": float(np.percentile(attempts, 99)),
        "max_reset_attempts": int(np.max(attempts)),
        "mean_pi_pulses": float(np.mean(pi_pulses)),
    }


def _block_timeout_s(cfg, shots):
    hold_us = max(float(cfg.get("ff_hold", cfg.get("t1_wait_us", 0.0))), 0.0)
    inter_shot_us = max(float(cfg.get(
        "opx_inter_shot_delay_us", readout_thermalization_us(cfg)
    )), 0.0)
    fixed_us = hold_us + inter_shot_us + 2.0 * float(cfg.get("ff_ramp_length", 0.0)) + 100.0
    margin = max(float(cfg.get("opx_timeout_margin", 3.0)), 1.0)
    watchdog = max(float(cfg.get("opx_unbounded_watchdog_s", 2.0)), 0.1)
    return watchdog + fixed_us * int(shots) * 1e-6 * margin


def acquire_t1_iq(soc, soccfg, cfg, shots=None):
    bundle = runtime_bundle(cfg)
    total = int(cfg.get("shots", cfg.get("reps", 1)) if shots is None else shots)
    if total <= 0:
        raise ValueError("T1 shots must be positive")
    capacity = max_records(
        dmem_words_from_soccfg(soccfg),
        int(cfg.get("opx_record_base", 32)),
        RECORD_WORDS,
    )
    capacity = min(capacity, int(cfg.get("opx_max_shots_per_block", 400)))
    records = []
    last_program = None
    for chunk in chunk_sizes(total, capacity):
        run_cfg = dict(cfg)
        run_cfg.update({
            "shots": int(chunk),
            "reps": int(chunk),
            "opx_reset_scheme": "opx_unbounded",
        })
        program = OPXResetT1Program(
            soccfg,
            run_cfg,
            bundle.payload,
            bundle.loop,
        )
        last_program = program
        try:
            block = run_dmem_block(
                soc,
                program,
                timeout_s=_block_timeout_s(run_cfg, chunk),
                poll_interval_s=float(run_cfg.get("opx_poll_interval_s", 0.002)),
            )
        except AcquisitionTimeout as exc:
            partial = records + list(exc.partial_records)
            raise AcquisitionTimeout(
                str(exc),
                completed_shots=len(partial),
                partial_records=partial,
            ) from exc
        records.extend(block)
    invalid = [
        record for record in records
        if record.terminal_status is not TerminalStatus.CONFIRMED_GROUND
    ]
    if invalid:
        raise RuntimeError(
            f"unbounded reset returned {len(invalid)} non-ground terminal records"
        )
    read_cycles = last_program.us2cycles(
        cfg["read_length"], ro_ch=cfg["ro_chs"][0]
    )
    i_values, q_values = payload_iq(records, read_cycles)
    telemetry = reset_telemetry(records)
    telemetry["read_length_cycles"] = int(read_cycles)
    return i_values, q_values, telemetry


def acquire_t1_3pt_iq(
    soc,
    soccfg,
    cfg,
    *,
    dc_gains,
    wait_us,
    shots=None,
):
    bundle = runtime_bundle(cfg)
    gains = np.asarray(dc_gains, dtype=float).reshape(-1)
    if gains.size == 0 or not np.all(np.isfinite(gains)):
        raise ValueError("at least one finite three-point DC gain is required")
    rounded = np.rint(gains).astype(np.int64)
    if not np.allclose(gains, rounded, rtol=0.0, atol=1e-9):
        raise ValueError("three-point DC gains must be integer DAC values")
    steps = np.diff(rounded)
    if steps.size and not np.all(steps == steps[0]):
        raise ValueError("three-point DC gains must be evenly spaced")
    wait_us = float(wait_us)
    if not np.isfinite(wait_us) or wait_us < 0.01:
        raise ValueError("three-point wait must be at least 0.01 us")
    total_shots = int(
        cfg.get("shots", cfg.get("reps", 1)) if shots is None else shots
    )
    if total_shots <= 0:
        raise ValueError("three-point shots must be positive")
    capacity = max_records(
        dmem_words_from_soccfg(soccfg),
        int(cfg.get("opx_record_base", 32)),
        PAYLOAD_RECORD_WORDS,
    )
    max_dc = capacity // 3
    if max_dc <= 0:
        raise ValueError("tProc data memory cannot hold one three-point DC record")
    max_dc = min(max_dc, int(cfg.get("opx_max_3pt_dc_per_program", max_dc)))
    i_values = np.empty((3, rounded.size, total_shots), dtype=float)
    q_values = np.empty_like(i_values)
    block_count = 0
    record_count = 0
    last_program = None
    for dc_start in range(0, rounded.size, max_dc):
        dc_stop = min(dc_start + max_dc, rounded.size)
        dc_chunk = rounded[dc_start:dc_stop]
        records_per_shot = int(dc_chunk.size) * 3
        shots_per_block = capacity // records_per_shot
        shot_start = 0
        for chunk in chunk_sizes(total_shots, shots_per_block):
            run_cfg = dict(cfg)
            run_cfg.update({
                "opx_reset_scheme": "opx_unbounded",
                "opx_t1_3pt_shots": int(chunk),
                "opx_t1_3pt_dc_gains": dc_chunk.tolist(),
                "opx_t1_3pt_wait_us": wait_us,
                "ff_hold": wait_us,
                "t1_wait_us": wait_us,
            })
            program = OPXResetT13PointProgram(
                soccfg,
                run_cfg,
                bundle.payload,
                bundle.loop,
            )
            last_program = program
            block = run_dmem_block(
                soc,
                program,
                timeout_s=_block_timeout_s(
                    run_cfg,
                    int(chunk) * records_per_shot,
                ),
                poll_interval_s=float(run_cfg.get("opx_poll_interval_s", 0.002)),
            )
            raw_i = np.asarray(
                [record.final_i for record in block], dtype=float
            ).reshape(chunk, dc_chunk.size, 3).transpose(2, 1, 0)
            raw_q = np.asarray(
                [record.final_q for record in block], dtype=float
            ).reshape(chunk, dc_chunk.size, 3).transpose(2, 1, 0)
            shot_stop = shot_start + int(chunk)
            i_values[:, dc_start:dc_stop, shot_start:shot_stop] = raw_i
            q_values[:, dc_start:dc_stop, shot_start:shot_stop] = raw_q
            shot_start = shot_stop
            block_count += 1
            record_count += len(block)
    read_cycles = last_program.us2cycles(
        cfg["read_length"], ro_ch=cfg["ro_chs"][0]
    )
    return i_values / int(read_cycles), q_values / int(read_cycles), {
        "shots_per_dc": int(total_shots),
        "dc_points": int(rounded.size),
        "records": int(record_count),
        "blocks": int(block_count),
        "order": "shot_dc_P0_P1_Ps",
        "read_length_cycles": int(read_cycles),
    }


def acquire_tls_memory_iq(
    soc,
    soccfg,
    cfg,
    *,
    sequences,
    interaction_us,
    storage_us,
    ff_gain,
    shots=None,
):
    bundle = runtime_bundle(cfg)
    sequence_values = tuple(str(value).strip().lower() for value in sequences)
    allowed = ("single", "double", "ground_double")
    if not sequence_values:
        raise ValueError("at least one TLS memory sequence is required")
    if any(value not in allowed for value in sequence_values):
        raise ValueError(f"TLS memory sequences must be one of {allowed}")
    interaction_us = float(interaction_us)
    storage_us = float(storage_us)
    ff_gain = float(ff_gain)
    if not np.isfinite(interaction_us) or interaction_us < 0.01:
        raise ValueError("TLS memory interaction must be at least 0.01 us")
    if not np.isfinite(storage_us) or storage_us < 0.0:
        raise ValueError("TLS memory storage must be non-negative")
    if not np.isfinite(ff_gain):
        raise ValueError("TLS memory flux gain must be finite")
    rounded_gain = int(round(ff_gain))
    if not np.isclose(ff_gain, rounded_gain, rtol=0.0, atol=1e-9):
        raise ValueError("TLS memory flux gain must be an integer DAC value")
    if not -32768 <= rounded_gain <= 32767:
        raise ValueError("TLS memory flux gain exceeds the signed DAC range")
    total_shots = int(
        cfg.get("shots", cfg.get("reps", 1)) if shots is None else shots
    )
    if total_shots <= 0:
        raise ValueError("TLS memory shots must be positive")
    capacity = max_records(
        dmem_words_from_soccfg(soccfg),
        int(cfg.get("opx_record_base", 32)),
        PAYLOAD_RECORD_WORDS,
    )
    capacity = min(
        capacity,
        int(cfg.get("opx_max_payload_records_per_block", capacity)),
    )
    shots_per_block = capacity // len(sequence_values)
    if shots_per_block <= 0:
        raise ValueError("TLS memory sequences do not fit in tProc data memory")
    i_blocks = []
    q_blocks = []
    last_program = None
    for chunk in chunk_sizes(total_shots, shots_per_block):
        run_cfg = dict(cfg)
        run_cfg.update({
            "opx_reset_scheme": "opx_unbounded",
            "opx_memory_shots": int(chunk),
            "opx_memory_sequences": list(sequence_values),
            "opx_memory_interaction_us": interaction_us,
            "opx_memory_storage_us": storage_us,
            "ff_gain": rounded_gain,
            "ff_hold": 2.0 * interaction_us + storage_us,
            "do_ff": True,
        })
        program = OPXResetTLSMemoryProgram(
            soccfg,
            run_cfg,
            bundle.payload,
            bundle.loop,
        )
        last_program = program
        block = run_dmem_block(
            soc,
            program,
            timeout_s=_block_timeout_s(
                run_cfg, int(chunk) * len(sequence_values)
            ),
            poll_interval_s=float(run_cfg.get("opx_poll_interval_s", 0.002)),
        )
        i_blocks.append(np.asarray(
            [record.final_i for record in block], dtype=float
        ).reshape(chunk, len(sequence_values)).T)
        q_blocks.append(np.asarray(
            [record.final_q for record in block], dtype=float
        ).reshape(chunk, len(sequence_values)).T)
    read_cycles = last_program.us2cycles(
        cfg["read_length"], ro_ch=cfg["ro_chs"][0]
    )
    i_values = np.concatenate(i_blocks, axis=1) / int(read_cycles)
    q_values = np.concatenate(q_blocks, axis=1) / int(read_cycles)
    return i_values, q_values, {
        "shots_per_sequence": int(total_shots),
        "sequences": list(sequence_values),
        "blocks": int(len(i_blocks)),
        "records": int(total_shots * len(sequence_values)),
        "order": "shot_sequence",
        "read_length_cycles": int(read_cycles),
    }


def acquire_t1_sweep_iq(
    soc,
    soccfg,
    cfg,
    *,
    delays_us,
    shots=None,
    reset_scheme="opx_unbounded",
):
    bundle = runtime_bundle(cfg)
    delays = np.asarray(delays_us, dtype=float).reshape(-1)
    if delays.size == 0 or not np.all(np.isfinite(delays)):
        raise ValueError("at least one finite T1 delay is required")
    if np.any(delays < 0.01):
        raise ValueError("T1 delays must be at least 0.01 us")
    total_shots = int(
        cfg.get("shots", cfg.get("reps", 1)) if shots is None else shots
    )
    if total_shots <= 0:
        raise ValueError("T1 shots must be positive")
    reset_scheme = str(reset_scheme).strip().lower()
    if reset_scheme not in ("opx_unbounded", "none"):
        raise ValueError("reset_scheme must be 'opx_unbounded' or 'none'")
    capacity = max_records(
        dmem_words_from_soccfg(soccfg),
        int(cfg.get("opx_record_base", 32)),
        PAYLOAD_RECORD_WORDS,
    )
    capacity = min(
        capacity,
        int(cfg.get("opx_max_payload_records_per_block", capacity)),
    )
    shots_per_block = capacity // delays.size
    if shots_per_block <= 0:
        raise ValueError(
            f"{delays.size} T1 points do not fit in tProc data memory"
        )
    i_blocks = []
    q_blocks = []
    last_program = None
    for chunk in chunk_sizes(total_shots, shots_per_block):
        run_cfg = dict(cfg)
        run_cfg.update({
            "opx_reset_scheme": reset_scheme,
            "opx_t1_shots": int(chunk),
            "opx_t1_delays_us": delays.tolist(),
            "ff_hold": float(np.max(delays)),
            "t1_wait_us": float(np.max(delays)),
        })
        program = OPXResetT1SweepProgram(
            soccfg,
            run_cfg,
            bundle.payload,
            bundle.loop,
        )
        last_program = program
        block = run_dmem_block(
            soc,
            program,
            timeout_s=_block_timeout_s(run_cfg, int(chunk) * delays.size),
            poll_interval_s=float(run_cfg.get("opx_poll_interval_s", 0.002)),
        )
        i_blocks.append(np.asarray(
            [record.final_i for record in block], dtype=float
        ).reshape(chunk, delays.size).T)
        q_blocks.append(np.asarray(
            [record.final_q for record in block], dtype=float
        ).reshape(chunk, delays.size).T)
    read_cycles = last_program.us2cycles(
        cfg["read_length"], ro_ch=cfg["ro_chs"][0]
    )
    i_values = np.concatenate(i_blocks, axis=1) / int(read_cycles)
    q_values = np.concatenate(q_blocks, axis=1) / int(read_cycles)
    return i_values, q_values, {
        "shots_per_point": int(total_shots),
        "points": int(delays.size),
        "blocks": int(len(i_blocks)),
        "records": int(total_shots * delays.size),
        "order": "shot_major",
        "read_length_cycles": int(read_cycles),
    }


def acquire_pulse_sweep_iq(
    soc,
    soccfg,
    cfg,
    *,
    gains,
    pulses,
    frequency_mhz,
    shots=None,
    pulse_placement="excursion",
    do_excursion=False,
    excursion_gain=None,
    flux_hold_us=0.05,
    park_recovery_us=0.0,
    herald=False,
    reset_scheme="opx_unbounded",
):
    bundle = runtime_bundle(cfg)
    gains = np.asarray(gains, dtype=int).reshape(-1)
    if gains.size == 0:
        raise ValueError("at least one payload gain is required")
    if gains.size > 1:
        steps = np.diff(gains)
        if not np.all(steps == steps[0]):
            raise ValueError("payload gains must be uniformly spaced")
        gain_step = int(steps[0])
    else:
        gain_step = 0
    total_shots = int(
        cfg.get("shots", cfg.get("reps", 1)) if shots is None else shots
    )
    if total_shots <= 0:
        raise ValueError("payload shots must be positive")
    reset_scheme = str(reset_scheme).strip().lower()
    if reset_scheme not in ("opx_unbounded", "none"):
        raise ValueError("reset_scheme must be 'opx_unbounded' or 'none'")
    capacity = max_records(
        dmem_words_from_soccfg(soccfg),
        int(cfg.get("opx_record_base", 32)),
        PAYLOAD_RECORD_WORDS,
    )
    capacity = min(
        capacity,
        int(cfg.get("opx_max_payload_records_per_block", capacity)),
    )
    shots_per_block = capacity // gains.size
    if shots_per_block <= 0:
        raise ValueError(
            f"{gains.size} payload points do not fit in tProc data memory"
        )
    i_blocks = []
    q_blocks = []
    last_program = None
    for chunk in chunk_sizes(total_shots, shots_per_block):
        run_cfg = dict(cfg)
        run_cfg.update({
            "opx_reset_scheme": reset_scheme,
            "opx_payload_shots_per_expt": int(chunk),
            "opx_payload_expts": int(gains.size),
            "opx_payload_gain_start": int(gains[0]),
            "opx_payload_gain_step": int(gain_step),
            "opx_payload_pulses": int(pulses),
            "opx_payload_frequency_mhz": float(frequency_mhz),
            "opx_payload_pulse_placement": str(pulse_placement),
            "opx_payload_do_excursion": bool(do_excursion),
            "opx_payload_flux_hold_us": float(flux_hold_us),
            "opx_payload_park_recovery_us": float(park_recovery_us),
            "opx_payload_herald": bool(herald),
        })
        if do_excursion:
            if excursion_gain is None:
                raise ValueError("excursion_gain is required when do_excursion=True")
            run_cfg["opx_payload_excursion_gain"] = float(excursion_gain)
        program = OPXResetPulseSweepProgram(
            soccfg,
            run_cfg,
            bundle.payload,
            bundle.loop,
        )
        last_program = program
        block = run_dmem_block(
            soc,
            program,
            timeout_s=_block_timeout_s(run_cfg, chunk * gains.size),
            poll_interval_s=float(run_cfg.get("opx_poll_interval_s", 0.002)),
        )
        i_block = np.asarray(
            [record.final_i for record in block], dtype=float
        ).reshape(chunk, gains.size).T
        q_block = np.asarray(
            [record.final_q for record in block], dtype=float
        ).reshape(chunk, gains.size).T
        i_blocks.append(i_block)
        q_blocks.append(q_block)
    read_cycles = last_program.us2cycles(
        cfg["read_length"], ro_ch=cfg["ro_chs"][0]
    )
    i_values = np.concatenate(i_blocks, axis=1) / int(read_cycles)
    q_values = np.concatenate(q_blocks, axis=1) / int(read_cycles)
    return i_values, q_values, {
        "shots_per_point": int(total_shots),
        "points": int(gains.size),
        "blocks": int(len(i_blocks)),
        "records": int(total_shots * gains.size),
        "read_length_cycles": int(read_cycles),
    }


def acquire_frequency_sweep_iq(
    soc,
    soccfg,
    cfg,
    *,
    frequencies_mhz,
    gain,
    pulses,
    shots=None,
    pulse_placement="park",
    do_excursion=False,
    excursion_gain=None,
    flux_hold_us=0.05,
    park_recovery_us=0.0,
    herald=False,
    reset_scheme="opx_unbounded",
):
    bundle = runtime_bundle(cfg)
    frequencies = np.asarray(frequencies_mhz, dtype=float).reshape(-1)
    if frequencies.size == 0 or not np.all(np.isfinite(frequencies)):
        raise ValueError("at least one finite payload frequency is required")
    if frequencies.size > 1:
        steps = np.diff(frequencies)
        if not np.allclose(steps, steps[0], rtol=0.0, atol=1e-9):
            raise ValueError("payload frequencies must be uniformly spaced")
        frequency_step = float(steps[0])
    else:
        frequency_step = 0.0
    total_shots = int(
        cfg.get("shots", cfg.get("reps", 1)) if shots is None else shots
    )
    if total_shots <= 0:
        raise ValueError("payload shots must be positive")
    reset_scheme = str(reset_scheme).strip().lower()
    if reset_scheme not in ("opx_unbounded", "none"):
        raise ValueError("reset_scheme must be 'opx_unbounded' or 'none'")
    capacity = max_records(
        dmem_words_from_soccfg(soccfg),
        int(cfg.get("opx_record_base", 32)),
        PAYLOAD_RECORD_WORDS,
    )
    capacity = min(
        capacity,
        int(cfg.get("opx_max_payload_records_per_block", capacity)),
    )
    shots_per_block = capacity // frequencies.size
    if shots_per_block <= 0:
        raise ValueError(
            f"{frequencies.size} payload points do not fit in tProc data memory"
        )
    i_blocks = []
    q_blocks = []
    last_program = None
    for chunk in chunk_sizes(total_shots, shots_per_block):
        run_cfg = dict(cfg)
        run_cfg.update({
            "opx_reset_scheme": reset_scheme,
            "opx_payload_shots_per_expt": int(chunk),
            "opx_payload_expts": int(frequencies.size),
            "opx_payload_sweep_kind": "frequency",
            "opx_payload_frequency_start_mhz": float(frequencies[0]),
            "opx_payload_frequency_step_mhz": frequency_step,
            "opx_payload_fixed_gain": int(gain),
            "opx_payload_pulses": int(pulses),
            "opx_payload_pulse_placement": str(pulse_placement),
            "opx_payload_do_excursion": bool(do_excursion),
            "opx_payload_flux_hold_us": float(flux_hold_us),
            "opx_payload_park_recovery_us": float(park_recovery_us),
            "opx_payload_herald": bool(herald),
        })
        if do_excursion:
            if excursion_gain is None:
                raise ValueError("excursion_gain is required when do_excursion=True")
            run_cfg["opx_payload_excursion_gain"] = float(excursion_gain)
        program = OPXResetPulseSweepProgram(
            soccfg,
            run_cfg,
            bundle.payload,
            bundle.loop,
        )
        last_program = program
        block = run_dmem_block(
            soc,
            program,
            timeout_s=_block_timeout_s(run_cfg, chunk * frequencies.size),
            poll_interval_s=float(run_cfg.get("opx_poll_interval_s", 0.002)),
        )
        i_block = np.asarray(
            [record.final_i for record in block], dtype=float
        ).reshape(chunk, frequencies.size).T
        q_block = np.asarray(
            [record.final_q for record in block], dtype=float
        ).reshape(chunk, frequencies.size).T
        i_blocks.append(i_block)
        q_blocks.append(q_block)
    read_cycles = last_program.us2cycles(
        cfg["read_length"], ro_ch=cfg["ro_chs"][0]
    )
    i_values = np.concatenate(i_blocks, axis=1) / int(read_cycles)
    q_values = np.concatenate(q_blocks, axis=1) / int(read_cycles)
    return i_values, q_values, {
        "shots_per_point": int(total_shots),
        "points": int(frequencies.size),
        "blocks": int(len(i_blocks)),
        "records": int(total_shots * frequencies.size),
    }


def acquire_pulse_iq(
    soc,
    soccfg,
    cfg,
    *,
    gain,
    pulses,
    frequency_mhz,
    shots=None,
    pulse_placement="excursion",
    do_excursion=False,
    excursion_gain=None,
    flux_hold_us=0.05,
    herald=False,
):
    i_values, q_values, telemetry = acquire_pulse_sweep_iq(
        soc,
        soccfg,
        cfg,
        gains=[int(gain)],
        pulses=pulses,
        frequency_mhz=frequency_mhz,
        shots=shots,
        pulse_placement=pulse_placement,
        do_excursion=do_excursion,
        excursion_gain=excursion_gain,
        flux_hold_us=flux_hold_us,
        herald=herald,
    )
    return i_values[0], q_values[0], telemetry
