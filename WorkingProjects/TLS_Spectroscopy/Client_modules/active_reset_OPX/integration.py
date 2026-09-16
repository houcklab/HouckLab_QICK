import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import (
    readout_thermalization_us,
)

from .acquisition import (
    AcquisitionTimeout,
    dmem_words_from_soccfg,
    run_dmem_block,
    run_dmem_stream,
)
from .calibration import CalibrationBundle
from .analysis import ReferenceAxis
from .classifier import ClassifierCalibration
from .programs import (
    OPXResetPulseGridProgram,
    OPXResetPulseSweepProgram,
    OPXResetTLSMemoryProgram,
    OPXResetT13PointProgram,
    OPXResetT15PointProgram,
    OPXResetT1NPointProgram,
    OPXResetT1FluxSweepProgram,
    OPXResetT1Program,
    OPXResetT1SweepProgram,
)
from .records import (
    PAYLOAD_RECORD_WORDS,
    RECORD_WORDS,
    TerminalStatus,
    max_records,
)
from .three_point import (
    canonicalize_bidirectional_records,
    distributed_p0_reference_indices,
)


def runtime_bundle(cfg):
    value = cfg.get("opx_reset_calibration") if hasattr(cfg, "get") else None
    if isinstance(value, CalibrationBundle):
        return value
    if isinstance(value, dict):
        return CalibrationBundle.from_dict(value)
    if str(cfg.get("reset_mode", "")).strip().lower() in ("passive", "none"):
        neutral = ClassifierCalibration(
            schema_version=1,
            context="passive",
            theta_rad=0.0,
            shift=0,
            c_int=1,
            s_int=0,
            ground_threshold=-1,
            excited_threshold=1,
            max_abs_raw=1,
            holdout={},
        )
        return CalibrationBundle(
            schema_version=1,
            payload=neutral,
            loop=neutral,
            reference_axis=ReferenceAxis.from_centers(0.0, 0.0, 1.0, 0.0),
            metadata={"purpose": "passive shot-major acquisition"},
        )
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


def flux_predistortion_telemetry(program):
    mode = str(getattr(program, "_t1_ff_predistortion_mode", "none"))
    tail_us = float(getattr(program, "_t1_ff_predistortion_tail_us", 0.0))
    recovery_us = float(getattr(
        program,
        "_t1_ff_predistortion_recovery_us",
        0.0,
    ))
    overlap_payload_readout = bool(getattr(
        program,
        "cfg",
        {},
    ).get("flux_predistortion_overlap_payload_readout", True))
    return {
        "flux_predistortion_round_trip_mode": mode,
        "flux_predistortion_recovery_window_us": recovery_us,
        "flux_predistortion_return_tail_us": tail_us,
        "flux_predistortion_tail_overlaps_payload_readout": bool(
            mode == "stateful" and tail_us > 0.0 and overlap_payload_readout
        ),
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


def _run_program(soc, program, timeout_s, cfg, *, total_shots, progress=None):
    poll_interval_s = float(cfg.get("opx_poll_interval_s", 0.002))
    if getattr(program, "stream_plan", None) is not None:
        return run_dmem_stream(
            soc,
            program,
            timeout_s=timeout_s,
            poll_interval_s=poll_interval_s,
            progress=progress,
            verify_dmem_reads=bool(cfg.get("opx_verify_dmem_reads", False)),
        )
    records = run_dmem_block(
        soc,
        program,
        timeout_s=timeout_s,
        poll_interval_s=poll_interval_s,
    )
    if progress is not None:
        for completed in range(1, int(total_shots) + 1):
            progress(completed, int(total_shots))
    return records


def acquire_t1_iq(soc, soccfg, cfg, shots=None):
    bundle = runtime_bundle(cfg)
    total = int(cfg.get("shots", cfg.get("reps", 1)) if shots is None else shots)
    if total <= 0:
        raise ValueError("T1 shots must be positive")
    run_cfg = dict(cfg)
    run_cfg.update({
        "shots": total,
        "reps": total,
        "opx_reset_scheme": "opx_unbounded",
        "opx_resident_dmem_stream": True,
    })
    last_program = OPXResetT1Program(
        soccfg,
        run_cfg,
        bundle.payload,
        bundle.loop,
    )
    records = _run_program(
        soc,
        last_program,
        _block_timeout_s(run_cfg, total),
        run_cfg,
        total_shots=total,
    )
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
    telemetry.update(flux_predistortion_telemetry(last_program))
    return i_values, q_values, telemetry


def acquire_t1_3pt_iq(
    soc,
    soccfg,
    cfg,
    *,
    dc_gains,
    wait_us,
    shots=None,
    reset_scheme="opx_unbounded",
):
    bundle = runtime_bundle(cfg)
    gains = np.asarray(dc_gains, dtype=float).reshape(-1)
    if gains.size == 0 or not np.all(np.isfinite(gains)):
        raise ValueError("at least one finite three-point DC gain is required")
    rounded = np.rint(gains).astype(np.int64)
    if not np.allclose(gains, rounded, rtol=0.0, atol=1e-9):
        raise ValueError("three-point DC gains must be integer DAC values")
    steps = np.diff(rounded)
    if (steps.size and not np.all(steps == steps[0])
            and not bool(cfg.get("opx_t1_3pt_gain_lookup", False))):
        raise ValueError("three-point DC gains must be evenly spaced")
    wait_us = float(wait_us)
    if not np.isfinite(wait_us) or wait_us < 0.01:
        raise ValueError("three-point wait must be at least 0.01 us")
    total_shots = int(
        cfg.get("shots", cfg.get("reps", 1)) if shots is None else shots
    )
    if total_shots < 2:
        raise ValueError("three-point shots must be at least two")
    reset_scheme = str(reset_scheme).strip().lower()
    if reset_scheme not in ("opx_unbounded", "none"):
        raise ValueError("reset_scheme must be 'opx_unbounded' or 'none'")
    records_per_shot = int(rounded.size) * 3
    p0_reference_shot_indices = distributed_p0_reference_indices(total_shots)
    run_cfg = dict(cfg)
    run_cfg.update({
        "opx_reset_scheme": reset_scheme,
        "opx_t1_3pt_shots": total_shots,
        "opx_t1_3pt_dc_gains": rounded.tolist(),
        "opx_t1_3pt_wait_us": wait_us,
        "opx_t1_3pt_dc_scan_order": "alternating_bidirectional",
        "opx_t1_3pt_p0_reference_shot_indices": list(
            p0_reference_shot_indices
        ),
        "ff_hold": wait_us,
        "t1_wait_us": wait_us,
        "opx_resident_dmem_stream": True,
    })
    last_program = OPXResetT13PointProgram(
        soccfg,
        run_cfg,
        bundle.payload,
        bundle.loop,
    )
    block = _run_program(
        soc,
        last_program,
        _block_timeout_s(run_cfg, total_shots * records_per_shot),
        run_cfg,
        total_shots=total_shots,
    )
    i_records = np.asarray(
        [record.final_i for record in block], dtype=float
    ).reshape(total_shots, rounded.size, 3)
    q_records = np.asarray(
        [record.final_q for record in block], dtype=float
    ).reshape(total_shots, rounded.size, 3)
    i_values = canonicalize_bidirectional_records(i_records).transpose(2, 1, 0)
    q_values = canonicalize_bidirectional_records(q_records).transpose(2, 1, 0)
    read_cycles = last_program.us2cycles(
        cfg["read_length"], ro_ch=cfg["ro_chs"][0]
    )
    up_shots = (total_shots + 1) // 2
    down_shots = total_shots // 2
    p0_up_sweeps = sum(
        value % 2 == 0 for value in p0_reference_shot_indices
    )
    p0_down_sweeps = len(p0_reference_shot_indices) - p0_up_sweeps
    return i_values / int(read_cycles), q_values / int(read_cycles), {
        "shots_per_dc": int(total_shots),
        "dc_points": int(rounded.size),
        "records": int(len(block)),
        "blocks": 1,
        "resident_stream": True,
        "order": "shot_alternating_dc_P0_sparse_P1_Ps",
        "dc_scan_order": "alternating_bidirectional",
        "dc_scan_up_shots": int(up_shots),
        "dc_scan_down_shots": int(down_shots),
        "p0_mode": "distributed_scalar",
        "p0_reference_sweeps": int(len(p0_reference_shot_indices)),
        "p0_reference_up_sweeps": int(p0_up_sweeps),
        "p0_reference_down_sweeps": int(p0_down_sweeps),
        "p0_reference_shot_indices": tuple(p0_reference_shot_indices),
        "p0_placeholder_records": int(
            (total_shots - len(p0_reference_shot_indices)) * rounded.size
        ),
        "read_length_cycles": int(read_cycles),
        **flux_predistortion_telemetry(last_program),
    }


def canonicalize_matched_t1_records(records):
    """Canonicalize odd-shot reverse-survival records, preserving P0/P1."""
    canonical = np.asarray(records).copy()
    if canonical.ndim != 3 or canonical.shape[-1] < 3:
        raise ValueError("records must have shape (shot, dc, condition>=3)")
    order = (0, 1, *range(canonical.shape[-1] - 1, 1, -1))
    canonical[1::2] = canonical[1::2][..., order]
    return canonical


def acquire_t1_5pt_iq(
    soc,
    soccfg,
    cfg,
    *,
    dc_gains,
    delays_us,
    reference_hold_us,
    shots=None,
    reset_scheme="opx_unbounded",
    progress=None,
    _include_references=True,
    _survival_index_offset=0,
    _allow_chunking=True,
):
    bundle = runtime_bundle(cfg)
    gains = np.asarray(dc_gains, dtype=float).reshape(-1)
    if gains.size == 0 or not np.all(np.isfinite(gains)):
        raise ValueError("at least one finite five-point DC gain is required")
    rounded = np.rint(gains).astype(np.int64)
    if not np.allclose(gains, rounded, rtol=0.0, atol=1e-9):
        raise ValueError("five-point DC gains must be integer DAC values")
    delays = np.asarray(delays_us, dtype=float).reshape(-1)
    if (
        delays.size < 1
        or not np.all(np.isfinite(delays))
        or np.any(delays <= 0.0)
        or np.any(np.diff(delays) <= 0.0)
    ):
        raise ValueError(
            "matched-reference delays must contain positive increasing values"
        )
    reference_hold_us = float(reference_hold_us)
    if not np.isfinite(reference_hold_us) or reference_hold_us < 0.01:
        raise ValueError("five-point reference hold must be at least 0.01 us")
    requested_shots = float(cfg.get("shots", cfg.get("reps", 1)) if shots is None else shots)
    if not np.isfinite(requested_shots) or requested_shots < 2 or not requested_shots.is_integer():
        raise ValueError("five-point shots must be an integer of at least two")
    total_shots = int(requested_shots)
    reset_scheme = str(reset_scheme).strip().lower()
    if reset_scheme not in ("opx_unbounded", "none"):
        raise ValueError("reset_scheme must be 'opx_unbounded' or 'none'")
    if _allow_chunking and delays.size > 3:
        delay_chunks = tuple(
            delays[index:index + 3]
            for index in range(0, delays.size, 3)
        )
        chunk_results = []
        survival_offset = 0
        for chunk_index, chunk_delays in enumerate(delay_chunks):
            include_references = chunk_index == 0
            chunk_progress = None
            if progress is not None:
                chunk_progress = (
                    lambda done, total, index=chunk_index: progress(
                        index * total_shots + done,
                        len(delay_chunks) * total_shots,
                    )
                )
            chunk_results.append(acquire_t1_5pt_iq(
                soc,
                soccfg,
                cfg,
                dc_gains=rounded,
                delays_us=chunk_delays,
                reference_hold_us=reference_hold_us,
                shots=total_shots,
                reset_scheme=reset_scheme,
                progress=chunk_progress,
                _include_references=include_references,
                _survival_index_offset=survival_offset,
                _allow_chunking=False,
            ))
            survival_offset += int(chunk_delays.size)

        i_values = np.concatenate(
            [result[0] for result in chunk_results], axis=0
        )
        q_values = np.concatenate(
            [result[1] for result in chunk_results], axis=0
        )
        chunk_telemetry = [dict(result[2]) for result in chunk_results]
        telemetry = dict(chunk_telemetry[0])
        telemetry.update({
            "records": int(sum(item["records"] for item in chunk_telemetry)),
            "records_per_dc": 2 + int(delays.size),
            "blocks": int(sum(item["blocks"] for item in chunk_telemetry)),
            "program_chunks": len(chunk_telemetry),
            "condition_names": (
                "P0", "P1", *(f"Ps_{delay:g}us" for delay in delays)
            ),
            "decay_delays_us": tuple(float(value) for value in delays),
            "condition_tag_mismatches": int(sum(
                item.get("condition_tag_mismatches", 0)
                for item in chunk_telemetry
            )),
            "condition_tags_match_decoded_conditions": bool(all(
                item.get("condition_tags_match_decoded_conditions", True)
                for item in chunk_telemetry
            )),
            "chunk_telemetry": chunk_telemetry,
            "order": "shot_alternating_dc_chunked_P0_P1_then_survivals",
        })
        return i_values, q_values, telemetry

    include_references = bool(_include_references)
    survival_index_offset = int(_survival_index_offset)
    records_per_dc = (
        (2 if include_references else 0) + int(delays.size)
    )
    records_per_shot = int(rounded.size) * records_per_dc
    run_cfg = dict(cfg)
    run_cfg.update({
        "opx_reset_scheme": reset_scheme,
        "opx_t1_3pt_shots": total_shots,
        "opx_t1_3pt_dc_gains": rounded.tolist(),
        "opx_t1_5pt_delays_us": delays.tolist(),
        "opx_t1_5pt_reference_hold_us": reference_hold_us,
        "opx_t1_include_references": include_references,
        "opx_t1_survival_index_offset": survival_index_offset,
        "ff_hold": reference_hold_us + float(delays[-1]),
        "t1_wait_us": reference_hold_us + float(delays[-1]),
        "opx_resident_dmem_stream": True,
    })
    program_type = (
        OPXResetT15PointProgram if delays.size == 3 else OPXResetT1NPointProgram
    )
    program = program_type(
        soccfg,
        run_cfg,
        bundle.payload,
        bundle.loop,
    )
    block = _run_program(
        soc,
        program,
        _block_timeout_s(run_cfg, total_shots * records_per_shot),
        run_cfg,
        total_shots=total_shots,
        progress=progress,
    )
    i_records = np.asarray(
        [record.final_i for record in block], dtype=float
    ).reshape(total_shots, rounded.size, records_per_dc)
    q_records = np.asarray(
        [record.final_q for record in block], dtype=float
    ).reshape(total_shots, rounded.size, records_per_dc)
    condition_tags = None
    if block and all(hasattr(record, "condition_tag") for record in block):
        condition_tags = np.asarray(
            [record.condition_tag for record in block], dtype=int
        ).reshape(total_shots, rounded.size, records_per_dc)
    i_records[1::2] = i_records[1::2, ::-1]
    q_records[1::2] = q_records[1::2, ::-1]
    if condition_tags is not None:
        condition_tags[1::2] = condition_tags[1::2, ::-1]
    if bool(run_cfg.get("opx_reverse_survival_order", False)):
        if include_references:
            i_records = canonicalize_matched_t1_records(i_records)
            q_records = canonicalize_matched_t1_records(q_records)
            if condition_tags is not None:
                condition_tags = canonicalize_matched_t1_records(condition_tags)
        else:
            i_records[1::2] = i_records[1::2, ..., ::-1]
            q_records[1::2] = q_records[1::2, ..., ::-1]
            if condition_tags is not None:
                condition_tags[1::2] = condition_tags[1::2, ..., ::-1]
    i_values = i_records.transpose(2, 1, 0)
    q_values = q_records.transpose(2, 1, 0)
    tag_telemetry = {}
    if condition_tags is not None:
        decoded_tags = condition_tags.transpose(2, 1, 0)
        expected_tags = np.asarray(
            (
                ([0, 1] if include_references else [])
                + [
                    2 + survival_index_offset + index
                    for index in range(delays.size)
                ]
            ),
            dtype=int,
        )[:, None, None]
        mismatches = int(np.count_nonzero(decoded_tags != expected_tags))
        tag_telemetry = {
            "condition_tag_mismatches": mismatches,
            "condition_tags_match_decoded_conditions": bool(mismatches == 0),
        }
    read_cycles = program.us2cycles(
        cfg["read_length"], ro_ch=cfg["ro_chs"][0]
    )
    return i_values / int(read_cycles), q_values / int(read_cycles), {
        "shots_per_condition": int(total_shots),
        "dc_points": int(rounded.size),
        "records": int(len(block)),
        "records_per_dc": records_per_dc,
        "blocks": 1,
        "resident_stream": True,
        "order": (
            "shot_alternating_dc_and_survival_P0_P1_Ps"
            if bool(run_cfg.get("opx_reverse_survival_order", False))
            else "shot_alternating_dc_P0_P1_Ps0_Ps1_Ps2"
        ),
        "condition_names": (
            *(("P0", "P1") if include_references else ()),
            *(f"Ps_{delay:g}us" for delay in delays),
        ),
        "dc_scan_order": "alternating_bidirectional",
        "dc_scan_up_shots": int((total_shots + 1) // 2),
        "dc_scan_down_shots": int(total_shots // 2),
        "p0_mode": "matched_frequency_resolved",
        "reference_hold_us": reference_hold_us,
        "decay_delays_us": tuple(float(value) for value in delays),
        "read_length_cycles": int(read_cycles),
        **tag_telemetry,
        "dmem_read_verification": getattr(
            program,
            "dmem_read_verification",
            {"enabled": False},
        ),
        **flux_predistortion_telemetry(program),
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
    warmup_shots=None,
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
    total_warmup_shots = int(
        cfg.get("opx_memory_warmup_shots", 0)
        if warmup_shots is None else warmup_shots
    )
    if total_warmup_shots < 0:
        raise ValueError("TLS memory warmup shots must be non-negative")
    run_cfg = dict(cfg)
    run_cfg.update({
        "opx_reset_scheme": "opx_unbounded",
        "opx_memory_shots": total_shots,
        "opx_memory_warmup_shots": total_warmup_shots,
        "opx_memory_sequences": list(sequence_values),
        "opx_memory_interaction_us": interaction_us,
        "opx_memory_storage_us": storage_us,
        "ff_gain": rounded_gain,
        "ff_hold": 2.0 * interaction_us + storage_us,
        "do_ff": True,
        "opx_resident_dmem_stream": True,
    })
    last_program = OPXResetTLSMemoryProgram(
        soccfg,
        run_cfg,
        bundle.payload,
        bundle.loop,
    )
    block = _run_program(
        soc,
        last_program,
        _block_timeout_s(
            run_cfg,
            (total_shots + total_warmup_shots) * len(sequence_values),
        ),
        run_cfg,
        total_shots=total_shots,
    )
    read_cycles = last_program.us2cycles(
        cfg["read_length"], ro_ch=cfg["ro_chs"][0]
    )
    i_values = np.asarray(
        [record.final_i for record in block], dtype=float
    ).reshape(total_shots, len(sequence_values)).T / int(read_cycles)
    q_values = np.asarray(
        [record.final_q for record in block], dtype=float
    ).reshape(total_shots, len(sequence_values)).T / int(read_cycles)
    return i_values, q_values, {
        "shots_per_sequence": int(total_shots),
        "sequences": list(sequence_values),
        "blocks": 1,
        "resident_stream": True,
        "records": int(total_shots * len(sequence_values)),
        "order": "shot_sequence",
        "warmup_shots": int(total_warmup_shots),
        "read_length_cycles": int(read_cycles),
        **flux_predistortion_telemetry(last_program),
    }


def acquire_t1_sweep_iq(
    soc,
    soccfg,
    cfg,
    *,
    delays_us,
    shots=None,
    reset_scheme="opx_unbounded",
    progress=None,
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
    run_cfg = dict(cfg)
    run_cfg.update({
        "opx_reset_scheme": reset_scheme,
        "opx_t1_shots": total_shots,
        "opx_t1_delays_us": delays.tolist(),
        "ff_hold": float(np.max(delays)),
        "t1_wait_us": float(np.max(delays)),
        "opx_resident_dmem_stream": True,
    })
    last_program = OPXResetT1SweepProgram(
        soccfg,
        run_cfg,
        bundle.payload,
        bundle.loop,
    )
    block = _run_program(
        soc,
        last_program,
        _block_timeout_s(run_cfg, total_shots * delays.size),
        run_cfg,
        total_shots=total_shots,
        progress=progress,
    )
    read_cycles = last_program.us2cycles(
        cfg["read_length"], ro_ch=cfg["ro_chs"][0]
    )
    i_values = np.asarray(
        [record.final_i for record in block], dtype=float
    ).reshape(total_shots, delays.size).T / int(read_cycles)
    q_values = np.asarray(
        [record.final_q for record in block], dtype=float
    ).reshape(total_shots, delays.size).T / int(read_cycles)
    return i_values, q_values, {
        "shots_per_point": int(total_shots),
        "points": int(delays.size),
        "blocks": 1,
        "resident_stream": True,
        "records": int(total_shots * delays.size),
        "order": "shot_delay",
        "read_length_cycles": int(read_cycles),
    }


def acquire_t1_flux_sweep_iq(
    soc,
    soccfg,
    cfg,
    *,
    dc_gains,
    delays_us,
    shots=None,
    reset_scheme="opx_unbounded",
    progress=None,
):
    bundle = runtime_bundle(cfg)
    gains = np.asarray(dc_gains, dtype=float).reshape(-1)
    if gains.size == 0 or not np.all(np.isfinite(gains)):
        raise ValueError("at least one finite T1 DC gain is required")
    rounded = np.rint(gains).astype(np.int64)
    if not np.allclose(gains, rounded, rtol=0.0, atol=1e-9):
        raise ValueError("T1 DC gains must be integer DAC values")
    steps = np.diff(rounded)
    if steps.size and not np.all(steps == steps[0]):
        raise ValueError("T1 DC gains must be evenly spaced")
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
    point_count = int(rounded.size) * int(delays.size)
    run_cfg = dict(cfg)
    run_cfg.update({
        "opx_reset_scheme": reset_scheme,
        "opx_t1_shots": total_shots,
        "opx_t1_dc_gains": rounded.tolist(),
        "opx_t1_delays_us": delays.tolist(),
        "ff_hold": float(np.max(delays)),
        "t1_wait_us": float(np.max(delays)),
        "opx_resident_dmem_stream": True,
    })
    last_program = OPXResetT1FluxSweepProgram(
        soccfg,
        run_cfg,
        bundle.payload,
        bundle.loop,
    )
    block = _run_program(
        soc,
        last_program,
        _block_timeout_s(run_cfg, total_shots * point_count),
        run_cfg,
        total_shots=total_shots,
        progress=progress,
    )
    read_cycles = last_program.us2cycles(
        cfg["read_length"], ro_ch=cfg["ro_chs"][0]
    )
    i_values = np.asarray(
        [record.final_i for record in block], dtype=float
    ).reshape(total_shots, rounded.size, delays.size).transpose(1, 2, 0) / int(read_cycles)
    q_values = np.asarray(
        [record.final_q for record in block], dtype=float
    ).reshape(total_shots, rounded.size, delays.size).transpose(1, 2, 0) / int(read_cycles)
    return i_values, q_values, {
        "shots_per_point": int(total_shots),
        "dc_points": int(rounded.size),
        "delay_points": int(delays.size),
        "blocks": 1,
        "resident_stream": True,
        "records": int(total_shots * point_count),
        "order": "shot_dc_delay",
        "read_length_cycles": int(read_cycles),
        **flux_predistortion_telemetry(last_program),
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
    run_cfg = dict(cfg)
    run_cfg.update({
        "opx_reset_scheme": reset_scheme,
        "opx_payload_shots_per_expt": total_shots,
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
        "opx_resident_dmem_stream": True,
    })
    if do_excursion:
        if excursion_gain is None:
            raise ValueError("excursion_gain is required when do_excursion=True")
        run_cfg["opx_payload_excursion_gain"] = float(excursion_gain)
    last_program = OPXResetPulseSweepProgram(
        soccfg,
        run_cfg,
        bundle.payload,
        bundle.loop,
    )
    block = _run_program(
        soc,
        last_program,
        _block_timeout_s(run_cfg, total_shots * gains.size),
        run_cfg,
        total_shots=total_shots,
    )
    read_cycles = last_program.us2cycles(
        cfg["read_length"], ro_ch=cfg["ro_chs"][0]
    )
    i_values = np.asarray(
        [record.final_i for record in block], dtype=float
    ).reshape(total_shots, gains.size).T / int(read_cycles)
    q_values = np.asarray(
        [record.final_q for record in block], dtype=float
    ).reshape(total_shots, gains.size).T / int(read_cycles)
    return i_values, q_values, {
        "shots_per_point": int(total_shots),
        "points": int(gains.size),
        "blocks": 1,
        "resident_stream": True,
        "records": int(total_shots * gains.size),
        "read_length_cycles": int(read_cycles),
    }


def acquire_pulse_grid_iq(
    soc,
    soccfg,
    cfg,
    *,
    frequencies_mhz,
    gains,
    pulses,
    shots=None,
    pulse_placement="excursion",
    do_excursion=False,
    excursion_gain=None,
    flux_hold_us=0.05,
    park_recovery_us=0.0,
    herald=False,
    reset_scheme="opx_unbounded",
    progress=None,
):
    bundle = runtime_bundle(cfg)
    frequencies = np.asarray(frequencies_mhz, dtype=float).reshape(-1)
    if frequencies.size == 0 or not np.all(np.isfinite(frequencies)):
        raise ValueError("at least one finite payload frequency is required")
    gains = np.asarray(gains, dtype=float).reshape(-1)
    if gains.size == 0 or not np.all(np.isfinite(gains)):
        raise ValueError("at least one finite payload gain is required")
    rounded = np.rint(gains).astype(np.int64)
    if not np.allclose(gains, rounded, rtol=0.0, atol=1e-9):
        raise ValueError("payload gains must be integer DAC values")
    steps = np.diff(rounded)
    if steps.size and not np.all(steps == steps[0]):
        raise ValueError("payload gains must be uniformly spaced")
    total_shots = int(
        cfg.get("shots", cfg.get("reps", 1)) if shots is None else shots
    )
    if total_shots <= 0:
        raise ValueError("payload shots must be positive")
    reset_scheme = str(reset_scheme).strip().lower()
    if reset_scheme not in ("opx_unbounded", "none"):
        raise ValueError("reset_scheme must be 'opx_unbounded' or 'none'")
    point_count = int(frequencies.size) * int(rounded.size)
    run_cfg = dict(cfg)
    run_cfg.update({
        "opx_reset_scheme": reset_scheme,
        "opx_payload_shots_per_expt": total_shots,
        "opx_payload_frequencies_mhz": frequencies.tolist(),
        "opx_payload_gains": rounded.tolist(),
        "opx_payload_pulses": int(pulses),
        "opx_payload_pulse_placement": str(pulse_placement),
        "opx_payload_do_excursion": bool(do_excursion),
        "opx_payload_flux_hold_us": float(flux_hold_us),
        "opx_payload_park_recovery_us": float(park_recovery_us),
        "opx_payload_herald": bool(herald),
        "opx_resident_dmem_stream": True,
    })
    if do_excursion:
        if excursion_gain is None:
            raise ValueError("excursion_gain is required when do_excursion=True")
        run_cfg["opx_payload_excursion_gain"] = float(excursion_gain)
    last_program = OPXResetPulseGridProgram(
        soccfg,
        run_cfg,
        bundle.payload,
        bundle.loop,
    )
    block = _run_program(
        soc,
        last_program,
        _block_timeout_s(run_cfg, total_shots * point_count),
        run_cfg,
        total_shots=total_shots,
        progress=progress,
    )
    read_cycles = last_program.us2cycles(
        cfg["read_length"], ro_ch=cfg["ro_chs"][0]
    )
    i_values = np.asarray(
        [record.final_i for record in block], dtype=float
    ).reshape(total_shots, frequencies.size, rounded.size).transpose(1, 2, 0) / int(read_cycles)
    q_values = np.asarray(
        [record.final_q for record in block], dtype=float
    ).reshape(total_shots, frequencies.size, rounded.size).transpose(1, 2, 0) / int(read_cycles)
    return i_values, q_values, {
        "shots_per_point": int(total_shots),
        "frequency_points": int(frequencies.size),
        "gain_points": int(rounded.size),
        "blocks": 1,
        "resident_stream": True,
        "records": int(total_shots * point_count),
        "order": "shot_frequency_gain",
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
    run_cfg = dict(cfg)
    run_cfg.update({
        "opx_reset_scheme": reset_scheme,
        "opx_payload_shots_per_expt": total_shots,
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
        "opx_resident_dmem_stream": True,
    })
    if do_excursion:
        if excursion_gain is None:
            raise ValueError("excursion_gain is required when do_excursion=True")
        run_cfg["opx_payload_excursion_gain"] = float(excursion_gain)
    last_program = OPXResetPulseSweepProgram(
        soccfg,
        run_cfg,
        bundle.payload,
        bundle.loop,
    )
    block = _run_program(
        soc,
        last_program,
        _block_timeout_s(run_cfg, total_shots * frequencies.size),
        run_cfg,
        total_shots=total_shots,
    )
    read_cycles = last_program.us2cycles(
        cfg["read_length"], ro_ch=cfg["ro_chs"][0]
    )
    i_values = np.asarray(
        [record.final_i for record in block], dtype=float
    ).reshape(total_shots, frequencies.size).T / int(read_cycles)
    q_values = np.asarray(
        [record.final_q for record in block], dtype=float
    ).reshape(total_shots, frequencies.size).T / int(read_cycles)
    return i_values, q_values, {
        "shots_per_point": int(total_shots),
        "points": int(frequencies.size),
        "blocks": 1,
        "resident_stream": True,
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
