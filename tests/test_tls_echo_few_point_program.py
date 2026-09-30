"""A hardware cycle must preserve all twelve independent echo subshots."""

import copy
import importlib
from types import SimpleNamespace

import numpy as np
import pytest


MODULE = "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSEchoFewPointProgram"


def module():
    return importlib.import_module(MODULE)


class Recorder:
    """Record QICK instructions, retaining the real resident and flux builders."""

    def __init__(self):
        self.cfg = {"qubit_ch": 1, "ff_ch": 3, "ff_park_gain": -25146,
                    "ff_gain": -20130, "opx_resident_pre_us": 30.,
                    "opx_resident_post_us": .1, "opx_resident_freq_mhz": 4290.5,
                    "refocus_sequence": "hahn_y", "refocus_elapsed_us": .35,
                    "echo_phase_deg": 0, "ff_hold": 31.,
                    "opx_resident_preparation_state": "g",
                    "opx_resident_reference_state": None}
        self._t1_ff_compensation = {
            "segment_edges_ns": [0., 30000., 32000., 40000., 80000.],
            "multipliers": [1.03, 1.02, 1.01, 1., 1.]}
        self._t1_ff_settle_us = .5
        self._t1_ff_predistortion_recovery_us = 40.
        self.reset_config = SimpleNamespace(inter_shot_delay_us=500.)
        self.reset_page, self.reset_regs = 0, {"i": 1, "q": 2, "address": 3}
        self.registers, self.ends = {}, {1: 0, 3: 0}
        self.time = 0
        self.events = []

    def us2cycles(self, value, gen_ch=None):
        return round(value * 430.08)

    def cycles2us(self, value, gen_ch=None):
        return value / 430.08

    def freq2reg(self, value, gen_ch):
        return value

    def deg2reg(self, value, gen_ch):
        return value

    def set_pulse_registers(self, **kwargs):
        self.registers[kwargs["ch"]] = kwargs

    def pulse(self, ch, t="auto"):
        register = dict(self.registers[ch])
        start = self.ends[ch] if t == "auto" else t
        self.events.append(("pulse", {**register, "start": self.time + start}))
        self.ends[ch] = start + register["length"]

    def sync_all(self, value):
        self.time += max(self.ends.values()) + value
        self.events.append(("sync", value))
        self.ends = {1: 0, 3: 0}

    def _set_payload_pulse(self, gain=None):
        self.set_pulse_registers(ch=1, style="arb", waveform="qubit", freq=5324.,
                                 phase=0, gain=0 if gain == 0 else 12000, length=86)

    def _shot_park_callbacks(self):
        return (lambda: self.events.append(("park_up", self.time)),
                lambda: self.events.append(("park_down", self.time)))

    def _measure_raw(self):
        self.events.append(("readout", self.time))

    def memw(self, *args):
        self.events.append(("memw", args))

    def mathi(self, *args):
        self.events.append(("mathi", args))

    def _emit_body(self):
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSPumpProbeResidentDrive
        TLSPumpProbeResidentDrive.ResidentDriveProgram._emit_body(self)


@pytest.fixture
def flux_sink(monkeypatch):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import PulseFunctions
    monkeypatch.setattr(PulseFunctions, "ff_maxv", lambda *_args, **_kwargs: 32766)


def test_cycle_matches_independent_echo_programs_and_preserves_every_relax(flux_sink):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSEchoRefocusProgram as refocus
    few = module()
    program = few.make_program(Recorder)()
    original = copy.deepcopy(program.cfg)
    expected = refocus.make_decay_program(Recorder)()
    saved_timings = []
    for phase in (0, 90, 180, 270):
        for sequence, elapsed in (("hahn_y", .35), ("hahn_y", 1.35),
                                  ("late_control", 1.35)):
            expected.cfg.update(refocus_sequence=sequence,
                                refocus_elapsed_us=elapsed, echo_phase_deg=phase)
            expected._emit_body()
            saved_timings.append(copy.deepcopy(expected.cfg["refocus_timing"]))
    program._emit_body()
    assert program.events == expected.events
    assert program.record_words == 24
    assert len([e for e in program.events if e[0] == "memw"]) == 24
    assert len([e for e in program.events if e[0] == "readout"]) == 12
    assert program.events.count(("sync", 215040)) == 12
    assert program.time == expected.time
    metadata = program.cfg.pop("few_point_conditions")
    assert program.cfg == original
    assert len(metadata) == 12
    assert [arm["name"] for arm in metadata] == [
        "short_0", "long_0", "late_0", "short_90", "long_90", "late_90",
        "short_180", "long_180", "late_180", "short_270", "long_270", "late_270"]
    assert [arm["timing"] for arm in metadata] == saved_timings
    assert all(arm["timing"]["concurrent_flux_correction"] for arm in metadata)
    # Metadata for early conditions must not alias the last emitted condition.
    assert metadata[0]["timing"]["elapsed_cycles"] == 152
    assert metadata[1]["timing"]["elapsed_cycles"] == 580
    assert metadata[2]["timing"]["elapsed_cycles"] == 23


def test_partial_cycle_exception_restores_config_and_retains_only_finished_timings(flux_sink):
    class BrokenRecorder(Recorder):
        def _measure_raw(self):
            if sum(e[0] == "readout" for e in self.events) == 2:
                raise RuntimeError("readout emission failed")
            super()._measure_raw()

    program = module().make_program(BrokenRecorder)()
    original = copy.deepcopy(program.cfg)
    with pytest.raises(RuntimeError, match="readout emission"):
        program._emit_body()
    completed = program.cfg.pop("few_point_conditions")
    assert program.cfg == original
    assert [arm["name"] for arm in completed] == ["short_0", "long_0"]


def test_decoder_preserves_cycles_condition_order_and_signed_iq():
    few = module()
    words = list(range(24)) + [0xffffffff, 0x80000000] + list(range(2, 24))
    records = few.decode_dmem_records(words, expected_records=2)
    assert records[0] == few.EchoCycle(tuple(complex(i, i + 1) for i in range(0, 24, 2)))
    assert records[1].iq[0] == complex(-1, -2147483648)
    assert records[1].iq[-1] == complex(22, 23)
    iq = few.records_iq(records)
    assert iq.shape == (2, 12)
    assert iq[1, 0] == complex(-1, -2147483648)
    assert few.records_iq([]).shape == (0, 12)
    assert few.decode_dmem_records([], expected_records=0) == []


@pytest.mark.parametrize("words,expected", [([0] * 23, None), ([0] * 25, None),
                                            ([0] * 24, 2), ([0] * 48, 1)])
def test_decoder_rejects_partial_or_wrong_number_of_cycles(words, expected):
    with pytest.raises(ValueError):
        module().decode_dmem_records(words, expected_records=expected)


def test_inherited_stream_uses_whole_24_word_cycles(flux_sink, monkeypatch):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import programs
    few = module()
    program = few.make_program(Recorder)()
    program.cfg["opx_resident_dmem_stream"] = True
    program.soccfg = {"tprocs": [{"dmem_size": 1024}]}
    program.record_base, program.done_addr = 16, 1
    monkeypatch.setattr(programs, "initialize_resident_stream",
                        lambda p, **kw: setattr(p, "stream_plan", kw["plan"]))
    programs.OPXResetBenchmarkProgram._initialize_stream(
        program, {}, total_shots=200, records_per_shot=1,
        total_units=200, records_per_unit=1, prefix="ECHO_STREAM")
    assert program.stream_plan["bank_units"] == 21
    assert program.stream_plan["bank_words"] == 504
    assert program.stream_plan["total_shots"] == 200
    assert program.stream_plan["final_partial_units"] == 11
    assert program.decode_dmem_records(np.arange(504), expected_records=21)[-1].iq[-1] == 502 + 503j


@pytest.mark.parametrize("change", ["excited_preparation", "excited_reference",
                                    "short_relaxation", "short_return"])
def test_invalid_cycle_is_rejected_before_any_subshot(change, flux_sink):
    program = module().make_program(Recorder)()
    if change == "excited_preparation":
        program.cfg["opx_resident_preparation_state"] = "e"
    elif change == "excited_reference":
        program.cfg["opx_resident_reference_state"] = "e"
    elif change == "short_relaxation":
        program.reset_config.inter_shot_delay_us = 100.
    else:
        program._t1_ff_predistortion_recovery_us = 1.
    with pytest.raises(ValueError):
        program._emit_body()
    assert program.events == []


def test_actual_stream_decodes_complete_cycles_across_full_and_partial_banks():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import acquisition, programs
    few = module()
    program = few.make_program(Recorder)()
    program.record_base, program.done_addr, program.reps = 16, 1, 3
    program.stream_plan = programs.resident_stream_plan(
        {"tprocs": [{"dmem_size": 112}]}, done_addr=1, record_base=16,
        record_words=program.record_words, total_shots=3, records_per_shot=1,
        total_units=3, records_per_unit=1)
    program.config_all = lambda *_a, **_kw: None
    program.config_bufs = lambda *_a, **_kw: None

    class Memory:
        def __init__(self):
            self.started = False
            self.ack = 0
            self.reads = []

        def start(self):
            self.started = True

        def single_write(self, address, value):
            if address == 2:
                self.ack = value

        def single_read(self, address):
            assert self.started
            if address == 1:
                return 2 if self.ack == 0 else 3
            assert address == 3
            return min(self.ack + 1, 2)

        def read_dmem(self, address, length):
            self.reads.append((address, length))
            if address == 16:
                return np.arange(48)
            assert address == 64
            return np.arange(48, 72)

    memory = Memory()
    soc = SimpleNamespace(tproc=memory)
    progress = []
    records = acquisition.run_dmem_stream(
        soc, program, timeout_s=1., sleeper=lambda _: None,
        progress=lambda done, total: progress.append((done, total)))
    assert memory.reads == [(16, 48), (64, 24)]
    assert progress == [(1, 3), (2, 3), (3, 3)]
    assert few.records_iq(records).shape == (3, 12)
    assert records[1].iq[-1] == 46 + 47j
    assert records[2].iq[0] == 48 + 49j
    assert records[2].iq[-1] == 70 + 71j
