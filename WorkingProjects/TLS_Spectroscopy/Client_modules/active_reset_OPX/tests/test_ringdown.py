import numpy as np
import pytest

from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.ringdown import (
    analyze_ringdown,
    combine_ringdown_sweeps,
    delay_cycle_axis,
    select_noise_floor_delay,
)


def test_select_noise_floor_delay_rejects_an_isolated_low_snr_point():
    delays = np.arange(8, dtype=float)
    amplitudes = np.asarray([20, 12, 2, 9, 2, 2, 2, 2], dtype=float)
    sem = np.ones(8, dtype=float)

    selected = select_noise_floor_delay(
        delays,
        amplitudes,
        sem,
        sigma=3.0,
        consecutive=4,
    )

    assert selected == pytest.approx(4.0)


def test_analyze_ringdown_recovers_field_and_photon_decay_times():
    rng = np.random.default_rng(9274)
    delays = np.linspace(0.0, 8.0, 81)
    shots = 1000
    field_tau = 0.8
    phase = 0.35 + 2.0 * np.pi * 0.11 * delays
    coherent = 120.0 * np.exp(-delays / field_tau) * np.exp(1j * phase)
    shape = (delays.size, shots)
    baseline = rng.normal(0.0, 5.0, shape) + 1j * rng.normal(0.0, 5.0, shape)
    residual = (
        coherent[:, None]
        + rng.normal(0.0, 5.0, shape)
        + 1j * rng.normal(0.0, 5.0, shape)
    )

    result = analyze_ringdown(
        delays,
        baseline.real,
        baseline.imag,
        residual.real,
        residual.imag,
        sigma=3.0,
        consecutive=5,
        observation_offset_us=0.5,
        probe_length_us=0.25,
    )

    assert result["field_tau_us"] == pytest.approx(field_tau, rel=0.06)
    assert result["photon_tau_us"] == pytest.approx(field_tau / 2.0, rel=0.06)
    assert 3.5 <= result["programmed_noise_floor_delay_us"] <= 5.5
    assert result["noise_floor_delay_us"] == pytest.approx(
        result["programmed_noise_floor_delay_us"] + 0.75
    )
    assert result["recommended_thermalization_us"] >= result["noise_floor_delay_us"]
    thermalization_steps = result["recommended_thermalization_us"] / 0.1
    assert thermalization_steps == pytest.approx(round(thermalization_steps))


def test_analyze_ringdown_reports_incomplete_when_signal_never_reaches_noise():
    delays = np.linspace(0.0, 2.0, 21)
    shots = 100
    baseline_i = np.zeros((delays.size, shots))
    baseline_q = np.zeros_like(baseline_i)
    residual_i = np.full_like(baseline_i, 10.0)
    residual_q = np.zeros_like(residual_i)

    result = analyze_ringdown(
        delays,
        baseline_i,
        baseline_q,
        residual_i,
        residual_q,
        sigma=3.0,
        consecutive=5,
    )

    assert result["status"] == "scan_too_short"
    assert result["noise_floor_delay_us"] is None
    assert result["recommended_thermalization_us"] is None


def test_incoherent_energy_prevents_false_thermalization_from_phase_cancellation():
    rng = np.random.default_rng(812)
    delays = np.linspace(0.0, 5.0, 51)
    shots = 1200
    amplitude = 40.0 * np.exp(-delays / 0.9)
    phases = rng.uniform(-np.pi, np.pi, (delays.size, shots))
    field = amplitude[:, None] * np.exp(1j * phases)
    shape = field.shape
    baseline = rng.normal(0.0, 2.0, shape) + 1j * rng.normal(0.0, 2.0, shape)
    residual = field + rng.normal(0.0, 2.0, shape) + 1j * rng.normal(0.0, 2.0, shape)

    result = analyze_ringdown(
        delays,
        baseline.real,
        baseline.imag,
        residual.real,
        residual.imag,
        sigma=3.0,
        consecutive=5,
    )

    assert result["coherent_noise_floor_delay_us"] < 0.5
    assert result["energy_noise_floor_delay_us"] > 3.0
    assert result["programmed_noise_floor_delay_us"] == result["energy_noise_floor_delay_us"]


def test_delay_cycle_axis_reverses_the_same_quantized_points():
    def us2cycles(value):
        return int(round(float(value) * 430.08))

    ascending = delay_cycle_axis(0.0, 0.1, 121, False, us2cycles)
    descending = delay_cycle_axis(0.0, 0.1, 121, True, us2cycles)

    assert ascending[-1] == 5160
    assert us2cycles(12.0) == 5161
    assert descending.tolist() == ascending[::-1].tolist()


def test_combine_ringdown_sweeps_restores_delay_order_and_concatenates_shots():
    ascending = {
        "delays_us": np.asarray([0.0, 1.0, 2.0]),
        "baseline_i": np.asarray([[10], [11], [12]]),
        "baseline_q": np.asarray([[20], [21], [22]]),
        "residual_i": np.asarray([[30], [31], [32]]),
        "residual_q": np.asarray([[40], [41], [42]]),
    }
    descending = {
        "delays_us": np.asarray([2.0, 1.0, 0.0]),
        "baseline_i": np.asarray([[102], [101], [100]]),
        "baseline_q": np.asarray([[202], [201], [200]]),
        "residual_i": np.asarray([[302], [301], [300]]),
        "residual_q": np.asarray([[402], [401], [400]]),
    }

    combined = combine_ringdown_sweeps([ascending, descending])

    assert combined["delays_us"].tolist() == [0.0, 1.0, 2.0]
    assert combined["baseline_i"].tolist() == [[10, 100], [11, 101], [12, 102]]
    assert combined["residual_q"].tolist() == [[40, 400], [41, 401], [42, 402]]


def test_ringdown_sequence_uses_a_hard_latched_park_once_before_shots():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.resonator_ringdown_q3 import (
        emit_persistent_park,
        emit_ringdown_pair,
    )

    class RecordingProgram:
        def __init__(self):
            self.events = []

        def set_pulse_registers(self, **kwargs):
            self.events.append(("registers", kwargs))

        def pulse(self, **kwargs):
            self.events.append(("pulse", kwargs))

        def sync_all(self, cycles=0):
            self.events.append(("sync_all", cycles))

        def trigger(self, **kwargs):
            self.events.append(("trigger", kwargs))

        def wait_all(self, cycles=0):
            self.events.append(("wait_all", cycles))

        def sync(self, page, register):
            self.events.append(("sync", page, register))

    program = RecordingProgram()
    emit_persistent_park(program, ff_ch=3, park_gain=-25790, length_cycles=3, preroll_cycles=80)
    emit_ringdown_pair(
        program,
        res_ch=0,
        ro_chs=[0],
        adc_trig_offset_cycles=215,
        wait_page=1,
        wait_register=4,
        baseline_guard_cycles=20,
        clearance_cycles=43000,
    )

    registers = program.events[0]
    assert registers[1]["style"] == "const"
    assert registers[1]["stdysel"] == "last"
    assert registers[1]["length"] == 3
    assert registers[1]["gain"] == -25790
    assert [event[0] for event in program.events].count("registers") == 1
    assert [event[0] for event in program.events] == [
        "registers",
        "pulse",
        "sync_all",
        "trigger",
        "wait_all",
        "sync_all",
        "pulse",
        "sync_all",
        "sync",
        "trigger",
        "wait_all",
        "sync_all",
    ]


def test_ringdown_runner_uses_the_canonical_readout_generator_duration():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.resonator_ringdown_q3 import (
        _direction_config,
    )

    cfg = _direction_config(
        {
            "read_length": 5.0,
            "adc_trig_offset": 0.5,
            "readout_guard_us": 1.0,
        },
        start_us=0.0,
        step_us=0.1,
        points=121,
    )

    assert cfg["ringdown_pump_length_us"] == pytest.approx(6.5)
