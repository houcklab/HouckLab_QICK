import numpy as np

from WorkingProjects.TLS_Spectroscopy.pynq import readout_batch
from WorkingProjects.TLS_Spectroscopy.pynq.readout_batch import (
    acquire_qick_program_batch,
    acquire_qick_resident_readout,
    install_qicksoc_batch_methods,
)


class FakeProgram:
    compiled = []
    loaded_pulses = 0
    configured_gens = 0

    def __init__(self, soc):
        self.soc = soc

    def load_prog(self, values):
        self.identifier = values["identifier"]
        self.reps = int(values["reps"])
        self.expts = values.get("expts")
        self.rounds = int(values.get("rounds", 1))
        self.counter_addr = int(values.get("counter_addr", 1))
        self.ro_chs = {0: {"length": int(values["read_length"])}}

    def compile(self):
        self.compiled.append(self.identifier)
        return [self.identifier]

    def load_pulses(self, soc):
        type(self).loaded_pulses += 1

    def config_gens(self, soc):
        type(self).configured_gens += 1

    def config_readouts(self, soc):
        soc.events.append(("readouts", self.identifier))

    def config_bufs(self, soc, enable_avg=True, enable_buf=False):
        soc.events.append(("buffers", self.identifier, enable_avg, enable_buf))


class FakeSoc:
    def __init__(self):
        self.events = []
        self.identifier = None

    def load_bin_program(self, compiled, reset=False):
        self.identifier = int(compiled[0])
        self.events.append(("load", self.identifier, reset))

    def start_src(self, source):
        self.events.append(("source", source))

    def start_readout(
        self, total_reps, counter_addr=1, ch_list=None, reads_per_rep=1
    ):
        self.expected = int(total_reps) * int(reads_per_rep)
        self.events.append(
            (
                "start",
                self.identifier,
                int(total_reps),
                int(counter_addr),
                tuple(ch_list),
                int(reads_per_rep),
            )
        )

    def poll_data(self, *args, **kwargs):
        values = np.empty((1, self.expected, 2), dtype=np.int32)
        values[0, :, 0] = self.identifier * 10 + np.arange(self.expected)
        values[0, :, 1] = -(self.identifier * 10 + np.arange(self.expected))
        return [(values, {"identifier": self.identifier})]


def program(identifier):
    return {
        "identifier": identifier,
        "reps": 2,
        "rounds": 1,
        "counter_addr": 1,
        "read_length": 5,
    }


def test_server_batch_preserves_first_then_shot_frequency_order():
    FakeProgram.compiled = []
    FakeProgram.loaded_pulses = 0
    FakeProgram.configured_gens = 0
    soc = FakeSoc()
    result = acquire_qick_program_batch(
        soc,
        program(9),
        [program(1), program(2)],
        shots=2,
        reads_per_rep=1,
        program_factory=FakeProgram,
    )
    assert FakeProgram.compiled == [9, 1, 2]
    assert FakeProgram.loaded_pulses == 1
    assert FakeProgram.configured_gens == 1
    assert [event[1] for event in soc.events if event[0] == "start"] == [9, 2, 1, 2]
    assert result["records"].shape == (2, 2, 2, 2)
    np.testing.assert_array_equal(result["records"][0, 0, :, 0], [18.0, 18.2])
    np.testing.assert_array_equal(result["records"][1, 0, :, 0], [2.0, 2.2])
    assert result["controller_programs"] == 4


def test_server_batch_rejects_rounds_and_inconsistent_record_counts():
    bad_rounds = program(1)
    bad_rounds["rounds"] = 2
    try:
        acquire_qick_program_batch(
            FakeSoc(), bad_rounds, [program(1)], shots=1,
            program_factory=FakeProgram,
        )
    except ValueError as exc:
        assert "rounds" in str(exc)
    else:
        raise AssertionError("rounds validation did not run")
    bad_reps = program(2)
    bad_reps["reps"] = 3
    try:
        acquire_qick_program_batch(
            FakeSoc(), program(9), [program(1), bad_reps], shots=1,
            program_factory=FakeProgram,
        )
    except ValueError as exc:
        assert "record" in str(exc)
    else:
        raise AssertionError("record-count validation did not run")


class ResidentTProc:
    def __init__(self):
        self.memory = {}
        self.command_addr = 2
        self.ready_addr = 3
        self.frequency_addr = 4
        self.total_blocks = 0
        self.completed_blocks = 0
        self.releases = []
        self.reset_count = 0

    def single_read(self, addr):
        return self.memory.get(int(addr), 0)

    def single_write(self, addr=0, data=0):
        addr = int(addr)
        data = int(data)
        self.memory[addr] = data
        if addr == self.command_addr and data == 1:
            self.releases.append(self.memory[self.frequency_addr])
            self.completed_blocks += 1
            if self.completed_blocks < self.total_blocks:
                self.memory[self.ready_addr] = self.completed_blocks + 1

    def reset(self):
        self.reset_count += 1


class ResidentProgram(FakeProgram):
    def load_prog(self, values):
        super().load_prog(values)
        self.ro_chs = {
            0: {
                "freq": 10.0,
                "length": int(values["read_length"]),
                "sel": "product",
                "gen_ch": 0,
            }
        }

    def config_readouts(self, soc):
        raise AssertionError("readouts must be initialized only once")


def test_ready_wait_ignores_one_transient_overshoot():
    class Array:
        def __init__(self):
            self.values = iter((63775, 63760))

        def __getitem__(self, index):
            return next(self.values)

    polls = readout_batch._wait_for_ready(
        object(),
        ready_addr=3,
        expected=63760,
        timeout_s=1.0,
        direct_memory=(Array(), 0),
    )
    assert polls == 2


def test_ready_wait_rejects_a_stable_overshoot():
    class Array:
        def __getitem__(self, index):
            return 12

    try:
        readout_batch._wait_for_ready(
            object(),
            ready_addr=3,
            expected=10,
            timeout_s=1.0,
            direct_memory=(Array(), 0),
        )
    except RuntimeError as exc:
        assert "advanced to block 12 before 10" in str(exc)
    else:
        raise AssertionError("stable ready overshoot was not rejected")


class ResidentSoc(FakeSoc):
    def __init__(self):
        super().__init__()
        self.tproc = ResidentTProc()
        self.readout_frequencies = []
        self.polls = 0

    def init_readouts(self):
        self.events.append(("init_readouts",))

    def configure_readout(self, ch, output, frequency, gen_ch=0):
        self.readout_frequencies.append(float(frequency))
        self.events.append(("configure_readout", int(ch), float(frequency)))

    def start_readout(
        self, total_reps, counter_addr=1, ch_list=None, reads_per_rep=1
    ):
        self.expected = int(total_reps) * int(reads_per_rep)
        self.tproc.total_blocks = 4
        self.tproc.memory[self.tproc.ready_addr] = 1
        self.events.append(("resident_start", int(total_reps)))

    def poll_data(self, *args, **kwargs):
        self.polls += 1
        values = np.empty((1, self.expected, 2), dtype=np.int32)
        values[0, :, 0] = np.arange(self.expected)
        values[0, :, 1] = -np.arange(self.expected)
        return [(values, {})]


def test_resident_server_uses_one_program_and_shot_frequency_handshake():
    FakeProgram.compiled = []
    ResidentProgram.loaded_pulses = 0
    ResidentProgram.configured_gens = 0
    soc = ResidentSoc()
    resident = program(7)
    resident["reps"] = 8
    configs = [
        {0: {"freq": 10.0, "length": 5, "sel": "product", "gen_ch": 0}},
        {0: {"freq": 20.0, "length": 5, "sel": "product", "gen_ch": 0}},
    ]
    result = acquire_qick_resident_readout(
        soc,
        resident,
        configs,
        [101, 202],
        shots=2,
        command_addr=2,
        ready_addr=3,
        frequency_addr=4,
        program_factory=ResidentProgram,
    )
    assert FakeProgram.compiled == [7]
    assert ResidentProgram.loaded_pulses == 1
    assert ResidentProgram.configured_gens == 1
    assert soc.readout_frequencies == [10.0, 10.0, 20.0, 10.0, 20.0]
    assert soc.tproc.releases == [101, 202, 101, 202]
    assert [event for event in soc.events if event[0] == "resident_start"] == [
        ("resident_start", 8)
    ]
    assert len([event for event in soc.events if event[0] == "load"]) == 1
    assert result["records"].shape == (2, 2, 2, 2)
    np.testing.assert_array_equal(result["records"][0, 0, :, 0], [0.0, 0.2])
    assert result["controller_programs"] == 1
    assert result["readout_reconfigurations"] == 4


def test_resident_server_selects_output_once_and_updates_only_dds_in_loop():
    class Buffer:
        def __init__(self):
            self.frequencies = []

        def set_freq(self, frequency, gen_ch=0):
            self.frequencies.append((float(frequency), int(gen_ch)))

    class DirectFrequencySoc(ResidentSoc):
        def __init__(self):
            super().__init__()
            self.avg_bufs = [Buffer()]

    soc = DirectFrequencySoc()
    configs = [
        {0: {"freq": 10.0, "length": 5, "sel": "product", "gen_ch": 0}},
        {0: {"freq": 20.0, "length": 5, "sel": "product", "gen_ch": 0}},
    ]
    acquire_qick_resident_readout(
        soc,
        {**program(7), "reps": 8},
        configs,
        [101, 202],
        shots=2,
        command_addr=2,
        ready_addr=3,
        frequency_addr=4,
        program_factory=ResidentProgram,
    )
    assert soc.readout_frequencies == [10.0]
    assert soc.avg_bufs[0].frequencies == [
        (10.0, 0),
        (20.0, 0),
        (10.0, 0),
        (20.0, 0),
    ]


def test_ready_poll_does_not_yield_to_the_linux_scheduler(monkeypatch):
    class DelayedReady:
        def __init__(self):
            self.reads = 0

        def single_read(self, addr):
            self.reads += 1
            return 0 if self.reads == 1 else 7

    sleeps = []
    monkeypatch.setattr(readout_batch.time, "sleep", sleeps.append)
    tproc = DelayedReady()
    readout_batch._wait_for_ready(tproc, 3, 7, 1.0)
    assert tproc.reads == 2
    assert sleeps == []


def test_resident_server_precomputes_readout_dds_registers_once():
    class Readout:
        def __init__(self):
            self.freq_reg = 0
            self.integer_updates = []

        def set_freq_int(self, value):
            self.freq_reg = int(value)
            self.integer_updates.append(int(value))

    class Buffer:
        def __init__(self):
            self.readout = Readout()
            self.frequency_conversions = []

        def set_freq(self, frequency, gen_ch=0):
            self.frequency_conversions.append((float(frequency), int(gen_ch)))
            self.readout.freq_reg = int(round(float(frequency) * 10))

    class PrecomputedFrequencySoc(ResidentSoc):
        def __init__(self):
            super().__init__()
            self.avg_bufs = [Buffer()]

    soc = PrecomputedFrequencySoc()
    configs = [
        {0: {"freq": 10.0, "length": 5, "sel": "product", "gen_ch": 0}},
        {0: {"freq": 20.0, "length": 5, "sel": "product", "gen_ch": 0}},
    ]
    result = acquire_qick_resident_readout(
        soc,
        {**program(7), "reps": 8},
        configs,
        [101, 202],
        shots=2,
        command_addr=2,
        ready_addr=3,
        frequency_addr=4,
        program_factory=ResidentProgram,
    )
    assert soc.avg_bufs[0].frequency_conversions == [(10.0, 0), (20.0, 0)]
    assert soc.avg_bufs[0].readout.integer_updates == [100, 200, 100, 200]
    assert result["frequency_update_mode"] == "precomputed_register"
    assert result["ready_wait_s"] >= 0.0
    assert result["frequency_update_s"] >= 0.0
    assert result["release_s"] >= 0.0
    assert result["ready_polls"] == 4


def test_resident_server_direct_mmio_preserves_latch_and_handshake_sequence():
    class ReadoutArray:
        def __init__(self):
            self.values = [0] * 6
            self.writes = []

        def __getitem__(self, index):
            return self.values[int(index)]

        def __setitem__(self, index, value):
            self.values[int(index)] = int(value)
            self.writes.append((int(index), int(value)))

    class Readout:
        REGISTERS = {"freq_reg": 0, "we_reg": 5}

        def __init__(self):
            self.mmio = type("MMIO", (), {"array": ReadoutArray()})()

        @property
        def freq_reg(self):
            return self.mmio.array.values[0]

        def set_freq_int(self, value):
            raise AssertionError("direct MMIO mode must not call set_freq_int")

    class Buffer:
        def __init__(self):
            self.readout = Readout()

        def set_freq(self, frequency, gen_ch=0):
            self.readout.mmio.array.values[0] = int(round(float(frequency) * 10))

    class TProcArray:
        def __init__(self, owner):
            self.owner = owner
            self.reads = []
            self.writes = []

        def __getitem__(self, index):
            address = int(index) - self.owner.NREG
            self.reads.append(address)
            return self.owner.memory.get(address, 0)

        def __setitem__(self, index, value):
            address = int(index) - self.owner.NREG
            value = int(value)
            self.writes.append((address, value))
            self.owner.memory[address] = value
            if address == self.owner.command_addr and value == 1:
                self.owner.releases.append(
                    self.owner.memory[self.owner.frequency_addr]
                )
                self.owner.completed_blocks += 1
                if self.owner.completed_blocks < self.owner.total_blocks:
                    self.owner.memory[self.owner.ready_addr] = (
                        self.owner.completed_blocks + 1
                    )

    class DirectTProc(ResidentTProc):
        NREG = 16

        def __init__(self):
            super().__init__()
            self.mmio = type("MMIO", (), {"array": TProcArray(self)})()

    class DirectMMIOSoc(ResidentSoc):
        def __init__(self):
            super().__init__()
            self.tproc = DirectTProc()
            self.avg_bufs = [Buffer()]

    soc = DirectMMIOSoc()
    configs = [
        {0: {"freq": 10.0, "length": 5, "sel": "product", "gen_ch": 0}},
        {0: {"freq": 20.0, "length": 5, "sel": "product", "gen_ch": 0}},
    ]
    result = acquire_qick_resident_readout(
        soc,
        {**program(7), "reps": 8},
        configs,
        [101, 202],
        shots=2,
        command_addr=2,
        ready_addr=3,
        frequency_addr=4,
        access_mode="direct_mmio",
        program_factory=ResidentProgram,
    )
    assert soc.avg_bufs[0].readout.mmio.array.writes == [
        (0, 100),
        (5, 1),
        (5, 0),
        (0, 200),
        (5, 1),
        (5, 0),
        (0, 100),
        (5, 1),
        (5, 0),
        (0, 200),
        (5, 1),
        (5, 0),
    ]
    assert soc.tproc.mmio.array.writes == [
        (4, 101),
        (2, 1),
        (4, 202),
        (2, 1),
        (4, 101),
        (2, 1),
        (4, 202),
        (2, 1),
    ]
    assert soc.tproc.releases == [101, 202, 101, 202]
    assert result["frequency_update_mode"] == "direct_mmio_latched"
    assert result["tproc_access_mode"] == "direct_mmio"


def test_resident_server_can_pack_frequency_into_release_command():
    class PackedTProc(ResidentTProc):
        def __init__(self):
            super().__init__()
            self.writes = []

        def single_write(self, addr=0, data=0):
            address = int(addr)
            value = int(data)
            self.writes.append((address, value))
            self.memory[address] = value
            if address == self.command_addr and value != 0:
                self.releases.append(value)
                self.completed_blocks += 1
                if self.completed_blocks < self.total_blocks:
                    self.memory[self.ready_addr] = self.completed_blocks + 1

    class PackedSoc(ResidentSoc):
        def __init__(self):
            super().__init__()
            self.tproc = PackedTProc()

    soc = PackedSoc()
    result = acquire_qick_resident_readout(
        soc,
        {**program(7), "reps": 8},
        [
            {0: {"freq": 10.0, "length": 5, "sel": "product", "gen_ch": 0}},
            {0: {"freq": 20.0, "length": 5, "sel": "product", "gen_ch": 0}},
        ],
        [101, 202],
        shots=2,
        command_addr=2,
        ready_addr=3,
        frequency_addr=4,
        command_mode="packed_frequency",
        program_factory=ResidentProgram,
    )
    assert soc.tproc.releases == [101, 202, 101, 202]
    assert [
        value for address, value in soc.tproc.writes
        if address == soc.tproc.frequency_addr and value != 0
    ] == []
    assert [
        value for address, value in soc.tproc.writes
        if address == soc.tproc.command_addr and value != 0
    ] == [101, 202, 101, 202]
    assert result["command_mode"] == "packed_frequency"


def test_resident_server_releases_each_block_with_its_sequence_number():
    class SequencedTProc(ResidentTProc):
        def __init__(self):
            super().__init__()
            self.writes = []

        def single_write(self, addr=0, data=0):
            address = int(addr)
            value = int(data)
            self.writes.append((address, value))
            self.memory[address] = value
            if address == self.command_addr and value == self.completed_blocks + 1:
                self.releases.append(value)
                self.completed_blocks += 1
                if self.completed_blocks < self.total_blocks:
                    self.memory[self.ready_addr] = self.completed_blocks + 1

    class SequencedSoc(ResidentSoc):
        def __init__(self):
            super().__init__()
            self.tproc = SequencedTProc()

    soc = SequencedSoc()
    result = acquire_qick_resident_readout(
        soc,
        {**program(7), "reps": 8},
        [
            {0: {"freq": 10.0, "length": 5, "sel": "product", "gen_ch": 0}},
            {0: {"freq": 20.0, "length": 5, "sel": "product", "gen_ch": 0}},
        ],
        [101, 202],
        shots=2,
        command_addr=2,
        ready_addr=3,
        frequency_addr=4,
        command_mode="sequenced",
        program_factory=ResidentProgram,
    )
    assert soc.tproc.releases == [1, 2, 3, 4]
    assert [
        value for address, value in soc.tproc.writes
        if address == soc.tproc.command_addr and value != 0
    ] == [1, 2, 3, 4]
    assert result["command_mode"] == "sequenced"


def test_resident_server_drains_stream_before_readout_backpressure_overflows():
    class BackpressureTProc(ResidentTProc):
        def __init__(self, owner):
            super().__init__()
            self.owner = owner

        def single_write(self, addr=0, data=0):
            previous = self.completed_blocks
            super().single_write(addr=addr, data=data)
            if self.completed_blocks > previous:
                self.owner.pending += 1
                if self.owner.pending > self.owner.capacity:
                    raise RuntimeError("exception in readout loop")

    class BackpressureSoc(ResidentSoc):
        def __init__(self):
            super().__init__()
            self.capacity = 64
            self.pending = 0
            self.delivered = 0
            self.tproc = BackpressureTProc(self)

        def start_readout(
            self, total_reps, counter_addr=1, ch_list=None, reads_per_rep=1
        ):
            self.expected = int(total_reps) * int(reads_per_rep)
            self.tproc.total_blocks = self.expected
            self.tproc.memory[self.tproc.ready_addr] = 1
            self.events.append(("resident_start", int(total_reps)))

        def poll_data(self, *args, **kwargs):
            self.polls += 1
            if self.pending == 0:
                return []
            values = np.empty((1, self.pending, 2), dtype=np.int32)
            sequence = np.arange(self.delivered, self.delivered + self.pending)
            values[0, :, 0] = sequence
            values[0, :, 1] = -sequence
            self.delivered += self.pending
            self.pending = 0
            return [(values, {})]

    soc = BackpressureSoc()
    configs = [
        {0: {"freq": 10.0, "length": 5, "sel": "product", "gen_ch": 0}},
        {0: {"freq": 20.0, "length": 5, "sel": "product", "gen_ch": 0}},
    ]
    result = acquire_qick_resident_readout(
        soc,
        {**program(7), "reps": 130},
        configs,
        [101, 202],
        shots=65,
        command_addr=2,
        ready_addr=3,
        frequency_addr=4,
        program_factory=ResidentProgram,
    )
    assert result["records"].shape == (65, 2, 1, 2)
    np.testing.assert_array_equal(
        result["records"][:, :, 0, 0].reshape(-1),
        np.arange(130) / 5,
    )


def test_installer_adds_both_batch_methods_to_qicksoc_class():
    class Soc:
        pass

    result = install_qicksoc_batch_methods(Soc)
    assert result is Soc
    assert callable(Soc.acquire_qick_program_batch)
    assert callable(Soc.acquire_qick_resident_readout)


def test_resident_server_rejects_handshake_outside_tproc_memory():
    class SmallMemorySoc(ResidentSoc):
        def get_cfg(self):
            return {"tprocs": [{"dmem_size": 4}]}

    try:
        acquire_qick_resident_readout(
            SmallMemorySoc(),
            {**program(7), "reps": 8},
            [
                {0: {"freq": 10.0, "length": 5, "sel": "product", "gen_ch": 0}},
                {0: {"freq": 20.0, "length": 5, "sel": "product", "gen_ch": 0}},
            ],
            [101, 202],
            shots=2,
            command_addr=2,
            ready_addr=3,
            frequency_addr=4,
            program_factory=ResidentProgram,
        )
    except ValueError as exc:
        assert "data memory" in str(exc)
    else:
        raise AssertionError("resident handshake memory validation did not run")


def test_resident_timeout_stops_tproc_and_streamer():
    class DoneFlag:
        def __init__(self):
            self.waits = []

        def wait(self, timeout=None):
            self.waits.append(timeout)
            return True

    class Streamer:
        def __init__(self):
            self.stopped = 0
            self.done_flag = DoneFlag()

        def readout_running(self):
            return True

        def stop_readout(self):
            self.stopped += 1

    class StalledSoc(ResidentSoc):
        def __init__(self):
            super().__init__()
            self.streamer = Streamer()

        def start_readout(
            self, total_reps, counter_addr=1, ch_list=None, reads_per_rep=1
        ):
            self.expected = int(total_reps) * int(reads_per_rep)
            self.events.append(("resident_start", int(total_reps)))

    soc = StalledSoc()
    try:
        acquire_qick_resident_readout(
            soc,
            {**program(7), "reps": 8},
            [
                {0: {"freq": 10.0, "length": 5, "sel": "product", "gen_ch": 0}},
                {0: {"freq": 20.0, "length": 5, "sel": "product", "gen_ch": 0}},
            ],
            [101, 202],
            shots=2,
            command_addr=2,
            ready_addr=3,
            frequency_addr=4,
            timeout_s=0.001,
            program_factory=ResidentProgram,
        )
    except TimeoutError:
        pass
    else:
        raise AssertionError("resident timeout did not run")
    assert soc.tproc.reset_count == 1
    assert soc.streamer.stopped == 1
    assert soc.streamer.done_flag.waits == [1.0]


def test_resident_stream_timeout_stops_tproc_and_streamer():
    class DoneFlag:
        def __init__(self):
            self.waits = []

        def wait(self, timeout=None):
            self.waits.append(timeout)
            return True

    class Streamer:
        def __init__(self):
            self.stopped = 0
            self.done_flag = DoneFlag()

        def readout_running(self):
            return True

        def stop_readout(self):
            self.stopped += 1

    class EmptyStreamSoc(ResidentSoc):
        def __init__(self):
            super().__init__()
            self.streamer = Streamer()

        def poll_data(self, *args, **kwargs):
            return []

    soc = EmptyStreamSoc()
    try:
        acquire_qick_resident_readout(
            soc,
            {**program(7), "reps": 8},
            [
                {0: {"freq": 10.0, "length": 5, "sel": "product", "gen_ch": 0}},
                {0: {"freq": 20.0, "length": 5, "sel": "product", "gen_ch": 0}},
            ],
            [101, 202],
            shots=2,
            command_addr=2,
            ready_addr=3,
            frequency_addr=4,
            timeout_s=0.001,
            program_factory=ResidentProgram,
        )
    except TimeoutError as exc:
        assert "streamed readout" in str(exc)
    else:
        raise AssertionError("resident stream timeout did not run")
    assert soc.tproc.reset_count == 1
    assert soc.streamer.stopped == 1
    assert soc.streamer.done_flag.waits == [1.0]
