import numpy as np
import pytest

from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.acquisition import (
    AcquisitionTimeout,
    chunk_sizes,
    run_dmem_block,
    timeout_for_reset_scheme,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.records import (
    PAYLOAD_RECORD_WORDS,
    PayloadRecord,
    RECORD_WORDS,
    ShotRecord,
    TerminalStatus,
    decode_payload_records,
)


RECORDS = [
    ShotRecord(0, -100, 0, 0, TerminalStatus.CONFIRMED_GROUND, -20, 30, -100),
    ShotRecord(1, 200, 1, 1, TerminalStatus.CONFIRMED_GROUND, -10, 40, -90),
]


class FakeTProc:
    def __init__(self, records, done_values=None, expose_bulk=True):
        self.memory = np.zeros(256, dtype=np.int64)
        words = np.asarray([w for record in records for w in record.to_words()], dtype=np.int64)
        self.memory[32:32 + words.size] = words & 0xFFFFFFFF
        self.done_values = list(done_values or [len(records)])
        self.done_addr = 1
        self.started = False
        self.reset_called = False
        self.events = []
        if not expose_bulk:
            self.read_dmem = None

    def single_write(self, addr, data):
        self.memory[int(addr)] = int(data)

    def single_read(self, addr):
        if int(addr) == self.done_addr and self.done_values:
            return self.done_values.pop(0)
        return int(self.memory[int(addr)])

    def read_dmem(self, addr, length):
        self.events.append("read_dmem")
        return self.memory[int(addr):int(addr) + int(length)].copy()

    def start(self):
        self.started = True

    def reset(self):
        self.reset_called = True
        self.events.append("reset")


class FakeSoc:
    def __init__(self, tproc):
        self.tproc = tproc
        self.reset_gens_called = False

    def reset_gens(self):
        self.reset_gens_called = True


class FakeProgram:
    record_base = 32
    record_words = RECORD_WORDS
    done_addr = 1

    def __init__(self, reps):
        self.reps = int(reps)
        self.soccfg = {"tprocs": [{"dmem_size": 256}]}
        self.config_all_called = False
        self.config_bufs_args = None

    def config_all(self, soc, load_pulses=True, start_src="internal", debug=False):
        self.config_all_called = True

    def config_bufs(self, soc, enable_avg=True, enable_buf=False):
        self.config_bufs_args = (enable_avg, enable_buf)


def test_chunk_sizes_cover_requested_shots_without_exceeding_capacity():
    assert chunk_sizes(1025, 508) == [508, 508, 9]
    assert chunk_sizes(0, 508) == []
    with pytest.raises(ValueError, match="capacity"):
        chunk_sizes(10, 0)


def test_unbounded_reset_uses_independent_host_watchdog():
    assert timeout_for_reset_scheme(
        "opx_unbounded",
        bounded_timeout_s=15.0,
        unbounded_watchdog_s=1.5,
    ) == pytest.approx(1.5)
    assert timeout_for_reset_scheme(
        "opx",
        bounded_timeout_s=15.0,
        unbounded_watchdog_s=1.5,
    ) == pytest.approx(15.0)


def test_unbounded_reset_rejects_a_disabled_host_watchdog():
    with pytest.raises(ValueError, match="watchdog"):
        timeout_for_reset_scheme(
            "opx_unbounded",
            bounded_timeout_s=15.0,
            unbounded_watchdog_s=0.0,
        )


def test_successful_block_uses_direct_tproc_execution_and_decodes_records():
    tproc = FakeTProc(RECORDS, done_values=[0, 2])
    soc = FakeSoc(tproc)
    program = FakeProgram(reps=2)
    times = iter([0.0, 0.0, 0.1])

    observed = run_dmem_block(
        soc,
        program,
        timeout_s=1.0,
        poll_interval_s=0.001,
        clock=lambda: next(times),
        sleeper=lambda _: None,
    )

    assert observed == RECORDS
    assert program.config_all_called
    assert program.config_bufs_args == (True, False)
    assert tproc.started
    assert not tproc.reset_called
    assert not soc.reset_gens_called


def test_single_read_fallback_handles_board_without_bulk_dmem_proxy():
    tproc = FakeTProc(RECORDS, done_values=[2], expose_bulk=False)
    observed = run_dmem_block(
        FakeSoc(tproc),
        FakeProgram(reps=2),
        timeout_s=1.0,
        clock=lambda: 0.0,
        sleeper=lambda _: None,
    )

    assert observed == RECORDS


def test_timeout_fails_closed_and_preserves_complete_partial_records():
    tproc = FakeTProc(RECORDS, done_values=[1, 1, 1])
    soc = FakeSoc(tproc)
    times = iter([0.0, 0.1, 1.0])

    with pytest.raises(AcquisitionTimeout) as caught:
        run_dmem_block(
            soc,
            FakeProgram(reps=2),
            timeout_s=0.5,
            poll_interval_s=0.001,
            clock=lambda: next(times),
            sleeper=lambda _: None,
        )

    assert caught.value.completed_shots == 1
    assert caught.value.partial_records == RECORDS[:1]
    assert tproc.reset_called
    assert soc.reset_gens_called
    assert tproc.events.index("reset") < tproc.events.index("read_dmem")


def test_block_rejects_a_record_allocation_larger_than_dmem():
    program = FakeProgram(reps=100)
    tproc = FakeTProc([], done_values=[0])

    with pytest.raises(ValueError, match="data memory"):
        run_dmem_block(FakeSoc(tproc), program, timeout_s=1.0)

    assert not tproc.started


def test_block_uses_program_specific_compact_record_decoder():
    records = [PayloadRecord(-20, 30), PayloadRecord(-10, 40)]
    tproc = FakeTProc(records, done_values=[2])
    program = FakeProgram(reps=2)
    program.record_words = PAYLOAD_RECORD_WORDS
    program.decode_dmem_records = decode_payload_records

    observed = run_dmem_block(
        FakeSoc(tproc),
        program,
        timeout_s=1.0,
        clock=lambda: 0.0,
        sleeper=lambda _: None,
    )

    assert observed == records
