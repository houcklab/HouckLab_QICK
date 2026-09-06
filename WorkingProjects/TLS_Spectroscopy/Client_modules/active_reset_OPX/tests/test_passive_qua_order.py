import sys
import types

import numpy as np

qick = sys.modules.get("qick")
if qick is None:
    qick = types.ModuleType("qick")
    qick.AveragerProgram = type("AveragerProgram", (), {})
    qick.RAveragerProgram = type("RAveragerProgram", (), {})
    sys.modules["qick"] = qick

from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments import (
    mQubitFluxStepResponse,
    mQubitLongTimeSpecVsFlux,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import qua_order
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.qua_order import (
    QUAPulseGridProgram,
    acquire_passive_flux_spectroscopy_grid,
    acquire_passive_optimizer_grid,
    acquire_passive_pulse_grid,
    acquire_passive_readout_grid,
    flux_spectroscopy_record_order,
    optimizer_record_order,
    reshape_optimizer_records,
    reshape_scalar_records,
    single_shot_record_order,
    scalar_record_order,
    _compensated_hold_segments,
    _uniform_frequency_registers,
)


class PulseGridRecorder:
    def __init__(self):
        self.cfg = {
            "res_ch": 0,
            "qubit_ch": 1,
            "qubit_nqz": 2,
        }
        self.frequencies = np.array([10.0, 20.0])
        self.gains = np.array([100, 200])
        self.drive_pulses = 1
        self.shots = 2
        self.instructions = []

    def declare_gen(self, **kwargs):
        return None

    def ch_page(self, channel):
        return channel

    def sreg(self, channel, name):
        return {"freq": 1, "gain": 2, "gain2": 3}[name]

    def regwi(self, page, register, value):
        self.instructions.append(("regwi", page, register, value))

    def safe_regwi(self, page, register, value):
        self.instructions.append(("safe_regwi", page, register, value))

    def label(self, name):
        self.instructions.append(("label", name))

    def pulse(self, **kwargs):
        self.instructions.append(("pulse", kwargs))

    def us2cycles(self, value, **kwargs):
        return int(round(float(value) * 100))

    def sync_all(self, cycles):
        self.instructions.append(("sync_all", cycles))

    def mathi(self, page, destination, source, operator, immediate):
        self.instructions.append(
            ("mathi", page, destination, source, operator, immediate)
        )

    def loopnz(self, page, register, label):
        self.instructions.append(("loopnz", page, register, label))

    def end(self):
        self.instructions.append(("end",))


class ResidentGridRecorder(PulseGridRecorder):
    def __init__(self):
        super().__init__()
        self.values = np.array([100.0])
        self.kind = "readout_gain"
        self.excursion_gain = None
        self.command_addr = 2
        self.ready_addr = 3
        self.frequency_addr = 4

    def memwi(self, page, register, address):
        self.instructions.append(("memwi", page, register, address))

    def memri(self, page, register, address):
        self.instructions.append(("memri", page, register, address))

    def condj(self, page, first, operator, second, label):
        self.instructions.append(
            ("condj", page, first, operator, second, label)
        )

    def sync(self, page, register):
        self.instructions.append(("sync", page, register))


def test_scalar_record_order_is_shot_then_declared_axes():
    assert scalar_record_order(2, (2, 3)) == [
        (shot, first, second)
        for shot in range(2)
        for first in range(2)
        for second in range(3)
    ]


def test_single_shot_order_matches_qua_state_blocks():
    assert single_shot_record_order(2) == [
        (0, 0),
        (0, 1),
        (1, 0),
        (1, 1),
    ]


def test_scalar_records_average_shots_without_changing_axis_order():
    values = np.array([
        0, 1, 2, 3, 4, 5,
        10, 11, 12, 13, 14, 15,
    ], dtype=float)
    result = reshape_scalar_records(values, shots=2, axis_lengths=(2, 3))
    np.testing.assert_array_equal(result, np.array([[5, 6, 7], [8, 9, 10]]))


def test_optimizer_record_order_pairs_states_inside_each_grid_point():
    assert optimizer_record_order(1, 2, 2) == [
        (0, 0, 0, 0),
        (0, 0, 0, 1),
        (0, 0, 1, 0),
        (0, 0, 1, 1),
        (0, 1, 0, 0),
        (0, 1, 0, 1),
        (0, 1, 1, 0),
        (0, 1, 1, 1),
    ]


def test_optimizer_records_preserve_shot_frequency_gain_state_axes():
    values = np.arange(2 * 2 * 3 * 2, dtype=float)
    result = reshape_optimizer_records(values, shots=2, frequencies=2, gains=3)
    assert result.shape == (2, 2, 3, 2)
    np.testing.assert_array_equal(result.ravel(), values)


def test_readout_grid_runs_host_frequency_programs_in_shot_major_order(monkeypatch):
    calls = []

    class Program:
        def __init__(self, soccfg, cfg, *, read_frequency_mhz, values, kind):
            self.frequency = float(read_frequency_mhz)
            self.values = np.asarray(values)
            self.reps = int(self.values.size)
            self.assert_park = bool(cfg["qua_assert_park_at_start"])

        def acquire_records(self, soc, progress=False, load_pulses=True):
            calls.append((self.frequency, self.assert_park, load_pulses))
            values = self.frequency + self.values
            return values, -values

    monkeypatch.setattr(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.qua_order.QUAReadoutFrequencyProgram",
        Program,
    )
    i_values, q_values, telemetry = acquire_passive_readout_grid(
        object(), object(), {"shots": 2},
        frequencies_mhz=[10.0, 20.0], values=[1, 2], kind="readout_gain",
    )
    assert calls == [
        (10.0, True, True),
        (20.0, False, False),
        (10.0, False, False),
        (20.0, False, False),
    ]
    assert i_values.shape == (2, 2, 2)
    assert q_values.shape == (2, 2, 2)
    assert telemetry["order"] == "shot_frequency_gain"


def test_readout_grid_batches_programs_on_the_soc_when_supported(monkeypatch):
    constructed = []

    class Program:
        def __init__(self, soccfg, cfg, *, read_frequency_mhz, values, kind):
            self.frequency = float(read_frequency_mhz)
            self.values = np.asarray(values)
            self.reps = int(self.values.size)
            self.assert_park = bool(cfg["qua_assert_park_at_start"])
            constructed.append((self.frequency, self.assert_park))

        def dump_prog(self):
            return {
                "frequency": self.frequency,
                "assert_park": self.assert_park,
                "values": self.values,
            }

        def acquire_records(self, *args, **kwargs):
            raise AssertionError("client-side acquisition should not run")

    class Soc:
        def __init__(self):
            self.calls = []

        def acquire_qick_program_batch(
            self, first_program, programs, shots, reads_per_rep=1
        ):
            self.calls.append((first_program, programs, shots, reads_per_rep))
            records = np.empty((shots, len(programs), 2, 2), dtype=float)
            for shot in range(shots):
                for frequency_index, program in enumerate(programs):
                    records[shot, frequency_index, :, 0] = (
                        program["frequency"] + program["values"] + shot
                    )
                    records[shot, frequency_index, :, 1] = -records[
                        shot, frequency_index, :, 0
                    ]
            return {"records": records, "controller_programs": shots * len(programs)}

    monkeypatch.setattr(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.qua_order.QUAReadoutFrequencyProgram",
        Program,
    )
    soc = Soc()
    i_values, q_values, telemetry = acquire_passive_readout_grid(
        soc, object(), {"shots": 2},
        frequencies_mhz=[10.0, 20.0], values=[1, 2], kind="readout_gain",
    )
    assert constructed == [(10.0, False), (20.0, False), (10.0, True)]
    assert len(soc.calls) == 1
    first_program, programs, shots, reads_per_rep = soc.calls[0]
    assert first_program["assert_park"] is True
    assert [program["assert_park"] for program in programs] == [False, False]
    assert shots == 2
    assert reads_per_rep == 1
    np.testing.assert_array_equal(i_values[0, :, 0], [11.0, 12.0])
    np.testing.assert_array_equal(i_values[1, :, 1], [22.0, 23.0])
    np.testing.assert_array_equal(q_values, -i_values)
    assert telemetry["host_programs"] == 1
    assert telemetry["controller_programs"] == 4
    assert telemetry["server_batches"] == 1
    assert telemetry["order"] == "shot_frequency_gain"


def test_readout_grid_prefers_resident_tproc_handshake(monkeypatch):
    class FrequencyProgram:
        def __init__(self, soccfg, cfg, *, read_frequency_mhz, values, kind):
            raise AssertionError(
                "resident acquisition must not build per-frequency programs"
            )

    class ResidentProgram:
        def __init__(self, soccfg, cfg, *, frequencies_mhz, values, kind,
                     excursion_gain=None):
            self.reps = int(cfg["shots"] * len(frequencies_mhz) * len(values))
            self.frequency_registers = np.asarray([101, 202], dtype=np.int64)
            self.command_addr = 2
            self.ready_addr = 3
            self.frequency_addr = 4
            self.ro_chs = {
                0: {
                    "freq": float(frequencies_mhz[0]),
                    "length": 5,
                    "sel": "product",
                    "gen_ch": 0,
                }
            }

        def dump_prog(self):
            return {"resident": True, "reps": self.reps}

    class Soc:
        def __init__(self):
            self.resident_calls = []

        def acquire_qick_resident_readout(
            self,
            program,
            readout_configs,
            frequency_registers,
            shots,
            command_addr,
            ready_addr,
            frequency_addr,
        ):
            self.resident_calls.append(
                (
                    program,
                    readout_configs,
                    frequency_registers,
                    shots,
                    command_addr,
                    ready_addr,
                    frequency_addr,
                )
            )
            records = np.arange(2 * 2 * 2 * 2, dtype=float).reshape(2, 2, 2, 2)
            return {
                "records": records,
                "controller_programs": 1,
                "readout_reconfigurations": 4,
            }

        def acquire_qick_program_batch(self, *args, **kwargs):
            raise AssertionError("resident acquisition must be preferred")

    monkeypatch.setattr(qua_order, "QUAReadoutFrequencyProgram", FrequencyProgram)
    monkeypatch.setattr(
        qua_order, "QUAResidentReadoutGridProgram", ResidentProgram, raising=False
    )
    soc = Soc()
    i_values, q_values, telemetry = acquire_passive_readout_grid(
        soc,
        object(),
        {"shots": 2},
        frequencies_mhz=[10.0, 20.0],
        values=[1, 2],
        kind="readout_gain",
    )
    assert len(soc.resident_calls) == 1
    call = soc.resident_calls[0]
    assert call[2] == [101, 202]
    assert call[3:] == (2, 2, 3, 4)
    assert [cfg[0]["freq"] for cfg in call[1]] == [10.0, 20.0]
    assert i_values.shape == (2, 2, 2)
    assert q_values.shape == (2, 2, 2)
    np.testing.assert_array_equal(i_values, np.arange(16).reshape(2, 2, 2, 2)[..., 0].transpose(1, 2, 0))
    assert telemetry["host_programs"] == 1
    assert telemetry["controller_programs"] == 1
    assert telemetry["readout_reconfigurations"] == 4
    assert telemetry["resident_handshake"] is True
    assert telemetry["order"] == "shot_frequency_gain"


def test_optimizer_grid_keeps_ground_excited_pairs_inside_each_point(monkeypatch):
    calls = []

    class Program:
        def __init__(self, soccfg, cfg, *, frequency_mhz, gains, kind, drive_pulses,
                     drive_gain):
            self.frequency = float(frequency_mhz)
            self.gains = np.asarray(gains)
            self.assert_park = bool(cfg["qua_assert_park_at_start"])

        def acquire_records(self, soc, progress=False, load_pulses=True):
            calls.append((self.frequency, self.assert_park, load_pulses))
            rows = np.column_stack((self.gains, self.gains + 100.0)).ravel()
            return rows, -rows

    monkeypatch.setattr(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.qua_order.QUAOptimizerFrequencyProgram",
        Program,
    )
    i_values, q_values, telemetry = acquire_passive_optimizer_grid(
        object(), object(), {"shots": 2}, frequencies_mhz=[10.0, 20.0],
        gains=[1, 2], kind="readout", drive_pulses=1, drive_gain=7,
    )
    assert calls == [
        (10.0, True, True),
        (20.0, False, False),
        (10.0, False, False),
        (20.0, False, False),
    ]
    assert i_values.shape == (2, 2, 2, 2)
    assert q_values.shape == (2, 2, 2, 2)
    np.testing.assert_array_equal(i_values[0, 0], [[1, 101], [2, 102]])
    assert telemetry["order"] == "shot_frequency_gain_state"


def test_readout_optimizer_batches_programs_on_the_soc(monkeypatch):
    class Program:
        def __init__(self, soccfg, cfg, *, frequency_mhz, gains, kind,
                     drive_pulses, drive_gain):
            self.frequency = float(frequency_mhz)
            self.gains = np.asarray(gains)
            self.reps = int(self.gains.size * 2)
            self.assert_park = bool(cfg["qua_assert_park_at_start"])

        def dump_prog(self):
            return {
                "frequency": self.frequency,
                "assert_park": self.assert_park,
                "gains": self.gains,
            }

        def acquire_records(self, *args, **kwargs):
            raise AssertionError("client-side acquisition should not run")

    class Soc:
        def __init__(self):
            self.calls = 0

        def acquire_qick_program_batch(
            self, first_program, programs, shots, reads_per_rep=1
        ):
            self.calls += 1
            records = np.empty((shots, len(programs), 4, 2), dtype=float)
            for shot in range(shots):
                for frequency_index, program in enumerate(programs):
                    row = np.array([1, 101, 2, 102], dtype=float)
                    row += program["frequency"] + shot
                    records[shot, frequency_index, :, 0] = row
                    records[shot, frequency_index, :, 1] = -row
            return {"records": records, "controller_programs": 4}

    monkeypatch.setattr(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.qua_order.QUAOptimizerFrequencyProgram",
        Program,
    )
    soc = Soc()
    i_values, q_values, telemetry = acquire_passive_optimizer_grid(
        soc, object(), {"shots": 2}, frequencies_mhz=[10.0, 20.0],
        gains=[1, 2], kind="readout", drive_pulses=1, drive_gain=7,
    )
    assert soc.calls == 1
    assert i_values.shape == (2, 2, 2, 2)
    np.testing.assert_array_equal(i_values[0, 0], [[11, 111], [12, 112]])
    np.testing.assert_array_equal(q_values, -i_values)
    assert telemetry["host_programs"] == 1
    assert telemetry["controller_programs"] == 4
    assert telemetry["server_batches"] == 1
    assert telemetry["order"] == "shot_frequency_gain_state"


def test_qubit_optimizer_uses_one_shot_major_streaming_program(monkeypatch):
    calls = []

    class Program:
        def __init__(self, soccfg, cfg, *, frequencies_mhz, gains, drive_pulses):
            calls.append((tuple(frequencies_mhz), tuple(gains), int(drive_pulses)))

        def acquire_records(self, soc, progress=False):
            values = np.arange(2 * 2 * 3 * 2, dtype=float)
            return values, -values

    monkeypatch.setattr(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.qua_order.QUAOptimizerGridProgram",
        Program,
    )
    i_values, q_values, telemetry = acquire_passive_optimizer_grid(
        object(), object(), {"shots": 2}, frequencies_mhz=[10.0, 20.0],
        gains=[1, 2, 3], kind="qubit", drive_pulses=3, drive_gain=7,
    )
    assert calls == [((10.0, 20.0), (1.0, 2.0, 3.0), 3)]
    assert i_values.shape == (2, 2, 3, 2)
    assert q_values.shape == (2, 2, 3, 2)
    assert telemetry["blocks"] == 1
    assert telemetry["order"] == "shot_frequency_gain_state"


def test_pulse_grid_uses_one_shot_major_streaming_program(monkeypatch):
    calls = []

    class Program:
        def __init__(self, soccfg, cfg, *, frequencies_mhz, gains, pulses):
            calls.append((tuple(frequencies_mhz), tuple(gains), int(pulses)))

        def acquire_records(self, soc, progress=False):
            values = np.arange(2 * 2 * 3, dtype=float)
            return values, -values

    monkeypatch.setattr(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.qua_order.QUAPulseGridProgram",
        Program,
    )
    i_values, q_values, telemetry = acquire_passive_pulse_grid(
        object(), object(), {"shots": 3}, frequencies_mhz=[10.0, 20.0],
        gains=[1, 2], pulses=1,
    )
    assert calls == [((10.0, 20.0), (1.0, 2.0), 1)]
    assert i_values.shape == (2, 2, 3)
    assert q_values.shape == (2, 2, 3)
    assert telemetry["blocks"] == 1
    assert telemetry["order"] == "shot_frequency_gain"


def test_pulse_grid_emits_valid_frequency_register_increment(monkeypatch):
    recorder = PulseGridRecorder()
    monkeypatch.setattr(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.qua_order._declare_readout",
        lambda program: None,
    )
    monkeypatch.setattr(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.qua_order._set_qubit_pulse",
        lambda program, frequency, gain: None,
    )
    monkeypatch.setattr(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.qua_order._declare_park",
        lambda program: None,
    )
    monkeypatch.setattr(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.qua_order._allocate_stream_counter",
        lambda program, names: {"shot_loop": 4, "frequency_loop": 5},
    )
    monkeypatch.setattr(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.qua_order._begin_park",
        lambda program, segments: None,
    )
    monkeypatch.setattr(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.qua_order._uniform_frequency_registers",
        lambda program, frequencies: (np.array([10, 20]), 10),
    )
    monkeypatch.setattr(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.qua_order._measure_record",
        lambda program: None,
    )
    QUAPulseGridProgram.make_program(recorder)
    assert ("mathi", 1, 1, 1, "+", 10) in recorder.instructions


def test_resident_readout_waits_then_loads_generator_frequency(monkeypatch):
    recorder = ResidentGridRecorder()
    monkeypatch.setattr(qua_order, "_declare_readout", lambda program: None)
    monkeypatch.setattr(
        qua_order, "_declare_park", lambda program, require_flux=False: None
    )
    monkeypatch.setattr(
        qua_order,
        "_allocate_stream_counter",
        lambda program, names: {
            "shot_loop": 4,
            "frequency_loop": 5,
            "command": 6,
            "ready": 7,
            "elapsed": 8,
        },
    )
    monkeypatch.setattr(qua_order, "_begin_park", lambda program, segments: None)
    monkeypatch.setattr(
        qua_order,
        "_measure_record",
        lambda program: program.instructions.append(("measure_record",)),
    )
    qua_order.QUAResidentReadoutGridProgram.make_program(recorder)
    wait_index = recorder.instructions.index(
        ("label", "QUA_RESIDENT_READOUT_WAIT")
    )
    assert recorder.instructions[wait_index + 1] == (
        "mathi",
        0,
        8,
        8,
        "+",
        14,
    )
    assert recorder.instructions[wait_index + 2] == ("memri", 0, 6, 2)
    assert recorder.instructions[wait_index + 3] == (
        "condj",
        0,
        6,
        "==",
        0,
        "QUA_RESIDENT_READOUT_WAIT",
    )
    assert recorder.instructions[wait_index + 4] == ("sync", 0, 8)
    assert recorder.instructions[wait_index + 5] == ("memri", 0, 1, 4)
    assert recorder.instructions.index(("measure_record",)) > wait_index
    assert recorder.instructions[-3:] == [
        ("loopnz", 0, 5, "QUA_RESIDENT_READOUT_FREQUENCY"),
        ("loopnz", 0, 4, "QUA_RESIDENT_READOUT_SHOT"),
        ("end",),
    ]


def test_uniform_mhz_axis_tolerates_qick_register_rounding_jitter():
    class Program:
        cfg = {"qubit_ch": 1}

        @staticmethod
        def freq2reg(value, gen_ch):
            return int(round(float(value) * 10.3))

    registers, step = _uniform_frequency_registers(
        Program(), np.array([0.0, 1.0, 2.0, 3.0])
    )
    np.testing.assert_array_equal(registers, [0, 10, 21, 31])
    assert step == 10


def test_pulse_grid_preserves_qick_waveform_library(monkeypatch):
    def initialize(program, soccfg):
        program.pulses = ["qick-waveforms"]

    monkeypatch.setattr(qua_order.QickProgram, "__init__", initialize)
    monkeypatch.setattr(QUAPulseGridProgram, "make_program", lambda program: None)
    program = QUAPulseGridProgram(
        object(),
        {"shots": 2},
        frequencies_mhz=[10.0, 20.0],
        gains=[100, 200],
        pulses=3,
    )
    assert program.pulses == ["qick-waveforms"]
    assert program.drive_pulses == 3


def test_tls_flux_spectroscopy_orders_match_marty_qua_nesting():
    assert flux_spectroscopy_record_order(
        1, frequencies=2, dc_points=2, times=2,
        order="shot_frequency_dc_time",
    ) == [
        (0, frequency, dc, delay)
        for frequency in range(2)
        for dc in range(2)
        for delay in range(2)
    ]


def test_hard_flux_hold_preserves_piecewise_compensation_and_total_time():
    segments = _compensated_hold_segments(
        park_gain=1000,
        target_gain=2000,
        hold_us=2.0,
        compensation={
            "segment_edges_ns": [0.0, 100.0, 1000.0],
            "multipliers": [1.2, 1.1, 1.0],
        },
        max_gain=32767,
    )
    assert segments == [(2200, 0.1), (2100, 0.9), (2000, 1.0)]
    assert sum(duration for _, duration in segments) == 2.0
    assert flux_spectroscopy_record_order(
        1, frequencies=2, dc_points=2, times=2,
        order="shot_dc_frequency_time",
    ) == [
        (0, dc, frequency, delay)
        for dc in range(2)
        for frequency in range(2)
        for delay in range(2)
    ]


def test_tls_flux_spectroscopy_maps_frequency_dc_time_shots_without_transpose_errors(
    monkeypatch,
):
    created = []

    class Program:
        def __init__(
            self, soccfg, cfg, *, frequencies_mhz, dc_gains, hold_times_us,
            read_frequencies_mhz, order, shots, baseline_rearm_us,
            post_readout_reset_us, readout_after_park,
        ):
            self.order = order
            self.shots = int(shots)
            self.frequencies = np.asarray(frequencies_mhz)
            self.dc_gains = np.asarray(dc_gains)
            self.hold_times = np.asarray(hold_times_us)
            self.assert_park = bool(cfg["qua_assert_park_at_start"])
            self.reps = (
                self.shots * self.frequencies.size * self.dc_gains.size
                * self.hold_times.size
            )
            created.append(self)

        def acquire_records(self, soc, progress=False, load_pulses=True):
            values = np.arange(self.reps, dtype=float)
            return values, -values

    monkeypatch.setattr(
        qua_order,
        "QUAFluxSpectroscopyProgram",
        Program,
    )
    common = dict(
        soc=object(),
        soccfg=object(),
        cfg={"shots": 2, "qua_order_max_records_per_block": 100},
        frequencies_mhz=[10.0, 20.0],
        dc_gains=[100, 200, 300],
        hold_times_us=[1.0, 2.0],
        read_frequencies_mhz=[7000.0, 7001.0, 7002.0],
        baseline_rearm_us=10.0,
        post_readout_reset_us=20.0,
        readout_after_park=False,
    )
    i_frequency, q_frequency, frequency_meta = acquire_passive_flux_spectroscopy_grid(
        **common,
        order="shot_frequency_dc_time",
    )
    assert len(created) == 1
    assert created[0].assert_park is True
    assert i_frequency.shape == (2, 3, 2, 2)
    assert q_frequency.shape == (2, 3, 2, 2)
    assert i_frequency[1, 2, 1, 1] == 23
    assert frequency_meta["order"] == "shot_frequency_dc_time"

    created.clear()
    i_dc, q_dc, dc_meta = acquire_passive_flux_spectroscopy_grid(
        **common,
        order="shot_dc_frequency_time",
    )
    assert len(created) == 1
    assert i_dc.shape == (2, 3, 2, 2)
    assert q_dc.shape == (2, 3, 2, 2)
    assert i_dc[1, 2, 1, 1] == 23
    assert dc_meta["order"] == "shot_dc_frequency_time"


def test_flux_step_response_routes_to_shot_frequency_time_stream(monkeypatch):
    observed = {}

    def acquire(*args, **kwargs):
        observed.update(kwargs)
        values = np.ones((2, 1, 3, 2), dtype=float)
        return values, np.zeros_like(values), {
            "order": "shot_frequency_dc_time",
            "records": 12,
        }

    monkeypatch.setattr(
        mQubitFluxStepResponse,
        "acquire_passive_flux_spectroscopy_grid",
        acquire,
        raising=False,
    )
    experiment = mQubitFluxStepResponse.QubitFluxStepResponse.__new__(
        mQubitFluxStepResponse.QubitFluxStepResponse
    )
    experiment.cfg = {
        "qua_shot_order": True,
        "read_pulse_freq": 7000.0,
        "qubit_freq": 4300.0,
        "qubit_gain": 1000,
        "qubit_length": 0.5,
        "readout_after_park": False,
        "relax_delay": 100.0,
    }
    experiment.soc = object()
    experiment.soccfg = object()
    experiment.f_vec = np.array([4300.0, 4301.0]) * 1e6
    experiment.t_vec = np.array([1000.0, 2000.0, 3000.0])
    experiment.dc_offset = 4000.0
    experiment.baseline_dc_offset = 0.0
    experiment.baseline_rearm_time_ns = 100000
    experiment.shots = 2
    experiment.resonator_if = 7_000_000_000
    experiment.flux_tail_compensation = None
    experiment.live_plot_enabled = False
    experiment.meta_dict = {"cw_amp": 1000}
    experiment.data = {}
    experiment._write_raw_sweep_csv = lambda: None
    experiment._extract_trace_from_map = lambda values: None
    experiment._fit_predistortion_from_step_response = lambda: None
    experiment._fit_rise_decay_bump_dc_correction_from_step_response = lambda: None
    experiment.finalize_analysis = lambda: None
    experiment.pickle_data = lambda: None

    result = experiment.acquire(progress=False, plotDisp=False)

    assert observed["order"] == "shot_frequency_dc_time"
    np.testing.assert_array_equal(observed["hold_times_us"], [1.0, 2.0, 3.0])
    assert result["data"]["acquisition_order"] == "shot_frequency_time"
    assert result["data"]["IQ_mag"].shape == (2, 3)


def test_long_time_routes_step2_and_step4_to_their_distinct_qua_orders(
    monkeypatch,
):
    orders = []

    def acquire(*args, **kwargs):
        orders.append(kwargs["order"])
        values = np.ones((2, 2, 1, 2), dtype=float)
        return values, np.zeros_like(values), {
            "order": kwargs["order"],
            "records": 8,
        }

    monkeypatch.setattr(
        mQubitLongTimeSpecVsFlux,
        "acquire_passive_flux_spectroscopy_grid",
        acquire,
        raising=False,
    )
    monkeypatch.setattr(mQubitLongTimeSpecVsFlux.np, "savetxt", lambda *a, **k: None)

    for tag in ("2", "4"):
        experiment = mQubitLongTimeSpecVsFlux.QubitLongTimeSpecVsFlux.__new__(
            mQubitLongTimeSpecVsFlux.QubitLongTimeSpecVsFlux
        )
        experiment.cfg = {
            "qua_shot_order": True,
            "qubit_freq_start": 4300.0,
            "qubit_freq_expts": 2,
            "qubit_freq_step": 1.0,
            "reps": 2,
        }
        experiment.soc = object()
        experiment.soccfg = object()
        experiment.dc_vec = np.array([1000.0, 2000.0])
        experiment._probe_time_window_ns = lambda: np.array([2000.0])
        experiment._build_resonator_curve = lambda: (
            np.array([7.0e9, 7.001e9]),
            np.array([7.0e9, 7.001e9]),
            "test",
        )
        experiment.readout_after_park = False
        experiment.park_voltage = 0.0
        experiment.inter_target_wait_ns = 100000.0
        experiment.post_readout_reset_ns = 100000.0
        experiment.long_time_ns = 2000
        experiment.average_window_ns = 0.0
        experiment.average_step_ns = 16.0
        experiment.park_readout_settle_ns = 500.0
        experiment.advanced_fit = False
        experiment.live_plot = False
        experiment.element = "q3"
        experiment.step_tag = tag
        experiment.iname = "/tmp/qua-order-test.png"
        experiment.pickle_data = lambda: None

        result = experiment.acquire(progress=False, plotDisp=False)

        expected = (
            "shot_frequency_dc"
            if tag == "2"
            else "shot_dc_frequency_time"
        )
        assert result["data"]["acquisition_order"] == expected
        assert result["data"]["magnitude"].shape == (2, 2, 1)

    assert orders == ["shot_frequency_dc_time", "shot_dc_frequency_time"]
