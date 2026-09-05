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
