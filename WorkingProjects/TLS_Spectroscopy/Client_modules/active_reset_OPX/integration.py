import numpy as np

from .acquisition import (
    AcquisitionTimeout,
    chunk_sizes,
    dmem_words_from_soccfg,
    run_dmem_block,
)
from .calibration import CalibrationBundle
from .programs import OPXResetPulseSweepProgram, OPXResetT1Program
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
    inter_shot_us = max(float(cfg.get("opx_inter_shot_delay_us", 25.0)), 0.0)
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
    return i_values, q_values, reset_telemetry(records)


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
        ).reshape(gains.size, chunk)
        q_block = np.asarray(
            [record.final_q for record in block], dtype=float
        ).reshape(gains.size, chunk)
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
