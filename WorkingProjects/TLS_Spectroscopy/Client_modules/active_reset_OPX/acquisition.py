import time

import numpy as np

from .records import decode_records, max_records


class AcquisitionTimeout(RuntimeError):
    def __init__(self, message, *, completed_shots, partial_records):
        super().__init__(message)
        self.completed_shots = int(completed_shots)
        self.partial_records = list(partial_records)


def chunk_sizes(total_shots, capacity):
    total_shots, capacity = int(total_shots), int(capacity)
    if total_shots < 0:
        raise ValueError("total_shots must be non-negative")
    if capacity <= 0:
        raise ValueError("capacity must be positive")
    full, remainder = divmod(total_shots, capacity)
    return [capacity] * full + ([remainder] if remainder else [])


def timeout_for_reset_scheme(
    reset_scheme,
    *,
    bounded_timeout_s,
    unbounded_watchdog_s,
):
    bounded_timeout_s = float(bounded_timeout_s)
    if not np.isfinite(bounded_timeout_s) or bounded_timeout_s <= 0:
        raise ValueError("bounded timeout must be positive and finite")
    if str(reset_scheme).strip().lower() != "opx_unbounded":
        return bounded_timeout_s
    unbounded_watchdog_s = float(unbounded_watchdog_s)
    if not np.isfinite(unbounded_watchdog_s) or unbounded_watchdog_s <= 0:
        raise ValueError("unbounded reset watchdog must be positive and finite")
    return unbounded_watchdog_s


def dmem_words_from_soccfg(soccfg):
    try:
        words = int(soccfg["tprocs"][0]["dmem_size"])
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ValueError("the board configuration does not report tProc data-memory size") from exc
    if words <= 0:
        raise ValueError("the board reports an invalid tProc data-memory size")
    return words


def _single_write(tproc, address, value):
    writer = getattr(tproc, "single_write", None)
    if not callable(writer):
        raise RuntimeError("the connected tProc exposes no single_write DMem API")
    writer(int(address), int(value))


def _single_read(tproc, address):
    reader = getattr(tproc, "single_read", None)
    if not callable(reader):
        raise RuntimeError("the connected tProc exposes no single_read DMem API")
    return int(reader(int(address)))


def _read_words(soc, address, length):
    address, length = int(address), int(length)
    tproc = soc.tproc
    server_reader = getattr(soc, "read_qick_dmem", None)
    if callable(server_reader):
        try:
            data = np.asarray(server_reader(address, length)).reshape(-1)
            if data.size >= length:
                return data[:length]
        except Exception:
            pass
    for owner in (tproc, soc):
        reader = getattr(owner, "read_dmem", None)
        if callable(reader):
            try:
                data = np.asarray(reader(address, length)).reshape(-1)
                if data.size >= length:
                    return data[:length]
            except Exception:
                pass
    return np.asarray([_single_read(tproc, address + offset) for offset in range(length)])


def _safe_abort(soc):
    try:
        reset = getattr(soc.tproc, "reset", None)
        if callable(reset):
            reset()
        else:
            stop = getattr(soc.tproc, "stop", None)
            if not callable(stop):
                raise RuntimeError("the connected tProc exposes no reset or stop API")
            stop()
    finally:
        reset_gens = getattr(soc, "reset_gens", None)
        if callable(reset_gens):
            reset_gens()


def _decode_program_records(program, words, expected_records):
    decoder = getattr(program, "decode_dmem_records", None)
    if callable(decoder):
        return decoder(words, expected_records=expected_records)
    return decode_records(words, expected_records=expected_records)


def run_dmem_block(
    soc,
    program,
    timeout_s,
    *,
    poll_interval_s=0.002,
    clock=time.monotonic,
    sleeper=time.sleep,
):
    """Run one bounded tProc block and return its fixed-size DMem records.

    This intentionally bypasses ``AveragerProgram.acquire``: the number of ADC
    triggers varies with the early-exit branch, while the DMem record count does
    not.  The completion counter is updated only after an entire shot record has
    been committed.
    """
    reps = int(program.reps)
    if reps <= 0:
        raise ValueError("program.reps must be positive")
    timeout_s = float(timeout_s)
    if not np.isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError("timeout_s must be positive and finite")
    poll_interval_s = float(poll_interval_s)
    if not np.isfinite(poll_interval_s) or poll_interval_s < 0:
        raise ValueError("poll_interval_s must be finite and non-negative")

    dmem_words = dmem_words_from_soccfg(program.soccfg)
    capacity = max_records(dmem_words, program.record_base, program.record_words)
    if reps > capacity:
        raise ValueError(
            f"{reps} shot records do not fit in tProc data memory (capacity {capacity})"
        )

    completed = 0
    started = False
    try:
        program.config_all(soc, load_pulses=True, start_src="internal", debug=False)
        program.config_bufs(soc, enable_avg=True, enable_buf=False)
        _single_write(soc.tproc, program.done_addr, 0)
        soc.tproc.start()
        started = True
        deadline = clock() + timeout_s
        while True:
            completed = _single_read(soc.tproc, program.done_addr)
            if completed == reps:
                break
            if completed < 0 or completed > reps:
                raise RuntimeError(
                    f"invalid tProc completion counter {completed}; expected 0..{reps}"
                )
            if clock() >= deadline:
                # Freeze all writers before reading the prefix whose completion
                # counter we just observed.  The tProc reset erases program memory,
                # not DMem, and reset_gens then returns latched outputs to zero.
                _safe_abort(soc)
                started = False
                words = _read_words(
                    soc, program.record_base, completed * program.record_words
                )
                partial = _decode_program_records(
                    program, words, expected_records=completed
                )
                raise AcquisitionTimeout(
                    f"OPX reset block timed out after {timeout_s:g} s "
                    f"({completed}/{reps} complete shots)",
                    completed_shots=completed,
                    partial_records=partial,
                )
            sleeper(poll_interval_s)

        words = _read_words(soc, program.record_base, reps * program.record_words)
        return _decode_program_records(program, words, expected_records=reps)
    except Exception:
        if started:
            _safe_abort(soc)
        raise


def run_dmem_stream(
    soc,
    program,
    timeout_s,
    *,
    poll_interval_s=0.002,
    progress=None,
    clock=time.monotonic,
    sleeper=time.sleep,
):
    plan = dict(program.stream_plan)
    if int(plan["done_addr"]) != int(program.done_addr):
        raise ValueError("program completion address does not match its resident stream plan")
    total_shots = int(plan["total_shots"])
    total_units = int(plan["total_units"])
    records_per_unit = int(plan["records_per_unit"])
    records_per_shot = int(plan["records_per_shot"])
    bank_units = int(plan["bank_units"])
    bank_words = int(plan["bank_words"])
    expected_records = total_shots * records_per_shot
    if min(total_shots, total_units, records_per_unit, records_per_shot, bank_units) <= 0:
        raise ValueError("resident stream dimensions must be positive")
    if int(program.reps) != expected_records:
        raise ValueError("program record count does not match its resident stream plan")
    timeout_s = float(timeout_s)
    if not np.isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError("timeout_s must be positive and finite")
    poll_interval_s = float(poll_interval_s)
    if not np.isfinite(poll_interval_s) or poll_interval_s < 0:
        raise ValueError("poll_interval_s must be finite and non-negative")

    records = []
    reported_shots = 0
    observed_records = 0
    observed_ready = 0
    received_units = 0
    acknowledged = 0
    started = False
    try:
        program.config_all(soc, load_pulses=True, start_src="internal", debug=False)
        program.config_bufs(soc, enable_avg=True, enable_buf=False)
        _single_write(soc.tproc, program.done_addr, 0)
        _single_write(soc.tproc, int(plan["ack_addr"]), 0)
        _single_write(soc.tproc, int(plan["ready_addr"]), 0)
        soc.tproc.start()
        started = True
        last_activity_at = clock()
        while received_units < total_units:
            now = clock()
            activity = False
            completed_records = _single_read(soc.tproc, program.done_addr)
            if completed_records < 0 or completed_records > expected_records:
                raise RuntimeError(
                    f"invalid tProc completion counter {completed_records}; "
                    f"expected 0..{expected_records}"
                )
            if completed_records < observed_records:
                raise RuntimeError(
                    "resident stream completion counter moved backwards from "
                    f"{observed_records} to {completed_records}"
                )
            if completed_records > observed_records:
                activity = True
            observed_records = completed_records
            completed_shots = min(
                completed_records // records_per_shot,
                total_shots,
            )
            if progress is not None:
                for completed in range(reported_shots + 1, completed_shots + 1):
                    progress(completed, total_shots)
            reported_shots = completed_shots
            ready = _single_read(soc.tproc, int(plan["ready_addr"]))
            if ready < acknowledged:
                raise RuntimeError(
                    f"resident stream ready counter moved backwards from {acknowledged} to {ready}"
                )
            if ready > observed_ready:
                activity = True
            observed_ready = max(observed_ready, ready)
            previous_acknowledged = acknowledged
            while acknowledged < ready and received_units < total_units:
                bank_index = acknowledged % 2
                unit_count = min(bank_units, total_units - received_units)
                record_count = unit_count * records_per_unit
                address = int(program.record_base) + bank_index * bank_words
                words = _read_words(
                    soc,
                    address,
                    record_count * int(program.record_words),
                )
                records.extend(
                    _decode_program_records(
                        program,
                        words,
                        expected_records=record_count,
                    )
                )
                received_units += unit_count
                acknowledged += 1
                _single_write(soc.tproc, int(plan["ack_addr"]), acknowledged)
            if acknowledged > previous_acknowledged:
                activity = True
            if activity:
                last_activity_at = now
            if received_units >= total_units:
                break
            if now - last_activity_at >= timeout_s:
                _safe_abort(soc)
                started = False
                recovered_shots = min(
                    len(records) // records_per_shot,
                    total_shots,
                )
                recovered_records = recovered_shots * records_per_shot
                partial_records = records[:recovered_records]
                raise AcquisitionTimeout(
                    f"resident OPX reset stream made no progress for {timeout_s:g} s "
                    f"({recovered_shots}/{total_shots} recovered shots; "
                    f"controller reported {reported_shots})",
                    completed_shots=recovered_shots,
                    partial_records=partial_records,
                )
            sleeper(poll_interval_s)

        completed_records = _single_read(soc.tproc, program.done_addr)
        if completed_records != expected_records:
            raise RuntimeError(
                f"resident stream completed {completed_records} records; "
                f"expected {expected_records}"
            )
        if progress is not None:
            for completed in range(reported_shots + 1, total_shots + 1):
                progress(completed, total_shots)
        return records
    except Exception:
        if started:
            _safe_abort(soc)
        raise
