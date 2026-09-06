import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.qua_order import (
    QUAPulseGridProgram,
    acquire_passive_optimizer_grid,
    acquire_passive_pulse_grid,
    acquire_passive_readout_grid,
    optimizer_record_order,
    reshape_optimizer_records,
    reshape_scalar_records,
    scalar_record_order,
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
        self.pulses = 1
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


def test_scalar_record_order_is_shot_then_declared_axes():
    assert scalar_record_order(2, (2, 3)) == [
        (shot, first, second)
        for shot in range(2)
        for first in range(2)
        for second in range(3)
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
