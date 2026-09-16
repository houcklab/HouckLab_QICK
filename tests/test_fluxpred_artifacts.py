import json

import numpy as np
import pytest

from fluxpred import measurement, schema
from fluxpred.core import Filter, probe_delays, render_on_schedule
from fluxpred.validation import shot_schedule

Q5_PARK = 0.156232010522
Q5_TARGET = 0.387741615
Q5_MODEL = {"EJmax": 58.3318716696, "Ec": 0.0548297687280, "period_volts": 0.858215417187,
            "phase_offset_volts": 0.149633192179, "d": 0.0100000000551,
            "tilt_slope": 0.223631088988}
WINDOWS = (416.0, 2000.0)
IDLE = (16.0, 1600.0)
PULSE = 400.0
PARK_FRACTION = 0.10
TARGET_FRACTION = 0.50
ID_PARK = Q5_PARK+PARK_FRACTION*(Q5_TARGET-Q5_PARK)
ID_TARGET = Q5_PARK+TARGET_FRACTION*(Q5_TARGET-Q5_PARK)
HOLD_NS = 200_000.0
RECOVERY_NS = 600_000.0
AMPLITUDE = 0.049
SHOTS = 300


def frequency(coordinate):
    x = np.asarray(coordinate, dtype=float)
    phase = np.pi*(x-Q5_MODEL["phase_offset_volts"])/Q5_MODEL["period_volts"]
    ej = Q5_MODEL["EJmax"]*np.sqrt(np.cos(phase)**2+Q5_MODEL["d"]**2*np.sin(phase)**2)
    return np.sqrt(8.0*ej*Q5_MODEL["Ec"])-Q5_MODEL["Ec"]+Q5_MODEL["tilt_slope"]*x


def build_inputs():
    model = Filter(np.array([8e3, 24e3, 64e3, 192e3]), [1.0], [np.zeros(4)], resolution_ns=1000.0)
    schedule = shot_schedule(amplitude=AMPLITUDE, hold_ns=HOLD_NS, recovery_ns=RECOVERY_NS,
                             first_ns=6000.0, growth=1.2, max_ns=100_000.0, quantum_ns=1000.0)
    command, _ = render_on_schedule(model, schedule)
    delays = probe_delays(command, schedule, span_ns=5416.0, inset_ns=16.0, max_points=40)
    ideal = np.where(delays < HOLD_NS, AMPLITUDE, 0.0)
    from fluxpred import cryoscope
    probe = cryoscope.probe_frequencies(ideal, frequency, park=ID_PARK, target=ID_TARGET)
    return command, delays, probe


def fake_populations(delays, *, p_ground=0.069, p_excited=0.779, seed=0):
    rng = np.random.default_rng(seed)
    populations = {"g": np.full(delays.shape, p_ground), "e": np.full(delays.shape, p_excited)}
    keeps = {name: np.ones(delays.shape) for name in ("g", "e")}
    for index, window in enumerate(WINDOWS):
        detuning = 0.3*np.exp(-delays/24_000.0)
        phase = 2*np.pi*detuning*window/1000.0
        for arm, component in (("i", np.cos(phase)), ("q", np.sin(phase))):
            label = f"{arm}{index}"
            populations[label] = np.clip(
                p_ground+(p_excited-p_ground)*(component+1.0)/2.0
                + rng.normal(0.0, 0.01, delays.shape), 0.0, 1.0)
            keeps[label] = np.ones(delays.shape)
    return populations, keeps


def write(tmp_path, **overrides):
    command, delays, probe = build_inputs()
    populations, keeps = fake_populations(delays)
    kwargs = dict(
        device="q5", park=Q5_PARK, scale=Q5_TARGET-Q5_PARK, park_coordinate=ID_PARK,
        target_coordinate=ID_TARGET, amplitude=AMPLITUDE, delays_ns=delays,
        effective_windows_ns=WINDOWS, idle_windows_ns=IDLE, pulse_ns=PULSE, shots=SHOTS,
        rounds=1, recovery_ns=RECOVERY_NS, hold_ns=HOLD_NS, command=command,
        populations=populations, keep_fractions=keeps, probe_frequency_ghz=probe,
        static_flux_model=dict(Q5_MODEL, probe_frequency_ghz=float(probe[0])),
        frequency_of_coordinate=frequency, timestamp="2026-09-15T20:47:00",
        code_commit="c5a2145", operator_note="center identification")
    kwargs.update(overrides)
    return measurement.write_measurement_artifacts(tmp_path/"q5_20_47_00_Flux_Ramsey_Cryoscope",
                                                   **kwargs)


def test_artifacts_are_written_next_to_the_experiment_stem(tmp_path):
    result = write(tmp_path)
    assert result["raw_csv"].name.endswith("_raw.csv")
    assert result["command_json"].name.endswith("_command.json")
    assert result["summary_json"].name.endswith("_summary.json")
    for key in ("raw_csv", "command_json", "summary_json"):
        assert result[key].exists()


def test_written_summary_validates_and_reloads(tmp_path):
    result = write(tmp_path)
    document = measurement.read_summary(result["summary_json"], device="q5", verify_hashes=True)
    assert document["schema"] == schema.MEASUREMENT_SCHEMA
    restored = measurement.command_from_summary(document)
    assert restored.edges_ns[-1] == pytest.approx(HOLD_NS+RECOVERY_NS)


def test_summary_records_the_center_to_center_convention(tmp_path):
    result = write(tmp_path)
    differentiator = result["document"]["analysis"]["differentiator"]
    assert differentiator["convention"] == "center_to_center"
    assert differentiator["pulse_ns"] == PULSE
    assert differentiator["idle_windows_ns"] == list(IDLE)
    assert differentiator["effective_window_ns"] == max(WINDOWS)
    assert result["document"]["sequence"]["probe_windows_ns"] == list(WINDOWS)


def test_raw_csv_round_trips_every_expected_column(tmp_path):
    result = write(tmp_path)
    raw = measurement.read_raw_csv(result["raw_csv"])
    for name in measurement.raw_columns(len(WINDOWS)):
        assert name in raw
    assert raw["delay_ns"].size == result["analysis"]["delays_ns"].size


def test_a_missing_population_column_is_refused(tmp_path):
    command, delays, probe = build_inputs()
    populations, keeps = fake_populations(delays)
    populations.pop("q1")
    with pytest.raises(ValueError, match="missing population column"):
        write(tmp_path, populations=populations, keep_fractions=keeps)


def test_a_wrong_length_population_column_is_refused(tmp_path):
    command, delays, probe = build_inputs()
    populations, keeps = fake_populations(delays)
    populations["i0"] = populations["i0"][:-1]
    with pytest.raises(ValueError, match="has shape"):
        write(tmp_path, populations=populations, keep_fractions=keeps)


def test_analysis_supports_a_realistic_readout_fidelity(tmp_path):
    result = write(tmp_path)
    analysis = result["analysis"]
    assert analysis["supported_fraction"] > 0.8
    assert analysis["resolved"]["ambiguous_count"] == 0


def test_a_collapsed_readout_reference_is_refused(tmp_path):
    command, delays, probe = build_inputs()
    populations, keeps = fake_populations(delays, p_ground=0.49, p_excited=0.51)
    with pytest.raises(ValueError, match="contrast"):
        write(tmp_path, populations=populations, keep_fractions=keeps)


def test_artifacts_are_json_clean(tmp_path):
    result = write(tmp_path)
    text = result["summary_json"].read_text()
    assert "NaN" not in text and "Infinity" not in text
    json.loads(text)


def test_production_park_is_a_flux_extremum_and_is_refused_for_identification():
    from fluxpred import cryoscope

    with pytest.raises(ValueError, match="sweet spot"):
        cryoscope.assert_branch_sensitivity(
            frequency, park=Q5_PARK, target=Q5_TARGET, minimum_mhz_per_unit=50.0)


def test_the_identification_interval_has_sensitivity_at_both_ends():
    from fluxpred import cryoscope

    report = cryoscope.assert_branch_sensitivity(
        frequency, park=ID_PARK, target=ID_TARGET, minimum_mhz_per_unit=50.0)
    assert abs(report[0.0]) >= 50.0
    assert abs(report[1.0]) >= 50.0


def test_the_summary_records_the_identification_interval_not_the_production_park(tmp_path):
    result = write(tmp_path)
    sequence = result["document"]["sequence"]
    coordinate = result["document"]["coordinate"]
    assert sequence["park_coordinate"] == pytest.approx(ID_PARK)
    assert sequence["target_coordinate"] == pytest.approx(ID_TARGET)
    assert coordinate["park"] == pytest.approx(Q5_PARK)
    assert coordinate["scale"] == pytest.approx(Q5_TARGET-Q5_PARK)
