import numpy as np

from WorkingProjects.TLS_Spectroscopy.pynq.readout_batch import (
    acquire_qick_program_batch,
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

    def poll_data(self):
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
