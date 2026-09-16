import json
import sys
from pathlib import Path

import numpy as np
import pytest

from fluxpred import measurement, schema
from fluxpred.core import Command, Filter, probe_delays, render_on_schedule
from fluxpred.fit import plant_response
from fluxpred.validation import shot_schedule

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools import fit_ramsey_flux_response as fitter

TAUS_US = [8.0, 24.0, 64.0, 192.0]
TRUE_PLANT = np.array([0.06, -0.04, 0.03, -0.02])
STATIC_MODEL = {"EJmax": 19.0, "Ec": 0.22, "period_volts": 1.0, "phase_offset_volts": 0.0,
                "d": 0.1, "tilt_slope": 0.0}
PARK = 0.156232010522
TARGET = 0.387741615
SCALE = TARGET-PARK
HOLD_NS = 200_000.0
RECOVERY_NS = 600_000.0
WINDOWS_NS = (20.0, 100.0, 500.0)
SHOTS = 400
X90_NS = 40.0
AMPLITUDE = 0.04


def frequency(coordinate):
    return fitter.transmon_frequency(coordinate, STATIC_MODEL)


def identity_model():
    return Filter(np.asarray(TAUS_US)*1000.0, [1.0], [np.zeros(4)], resolution_ns=1000.0)


def build_measurement(tmp_path, *, seed=0, noise_shots=SHOTS, name="q5_center",
                      amplitude=AMPLITUDE):
    schedule = shot_schedule(amplitude=amplitude, hold_ns=HOLD_NS, recovery_ns=RECOVERY_NS,
                             first_ns=2000.0, growth=1.35, max_ns=100_000.0, quantum_ns=1000.0)
    command, _ = render_on_schedule(identity_model(), schedule)
    window_fine = max(WINDOWS_NS)
    span = 2.0*X90_NS+window_fine
    delays = probe_delays(command, schedule, span_ns=span)
    ideal = np.where(delays < HOLD_NS, amplitude, 0.0)
    probe_ghz = float(frequency(PARK+amplitude*(TARGET-PARK)))
    seen = plant_response(command, delays, np.asarray(TAUS_US)*1000.0, TRUE_PLANT,
                          probe_ns=window_fine)
    coordinate = PARK+seen*(TARGET-PARK)
    detuning_mhz = (frequency(coordinate)-probe_ghz)*1000.0
    nominal_mhz = (frequency(PARK+ideal*(TARGET-PARK))-probe_ghz)*1000.0
    residual_mhz = detuning_mhz-nominal_mhz

    rng = np.random.default_rng(seed)
    populations, keeps = {}, {}
    p_ground, p_excited = 0.03, 0.96
    for index, window in enumerate(WINDOWS_NS):
        phase = 2*np.pi*residual_mhz*window/1000.0
        for arm, component in (("i", np.cos(phase)), ("q", np.sin(phase))):
            probability = p_ground+(p_excited-p_ground)*(component+1.0)/2.0
            label = f"{arm}{index}"
            populations[label] = rng.binomial(
                noise_shots, np.clip(probability, 0, 1))/noise_shots
            keeps[label] = np.ones_like(delays)
    populations["g"] = np.full(delays.shape, p_ground)
    populations["e"] = np.full(delays.shape, p_excited)
    keeps["g"] = np.ones_like(delays)
    keeps["e"] = np.ones_like(delays)

    raw_path = measurement.write_raw_csv(
        tmp_path/f"{name}_raw.csv", delays_ns=delays, populations=populations,
        keep_fractions=keeps, window_count=len(WINDOWS_NS))
    command_path = measurement.write_command_json(tmp_path/f"{name}_command.json", command)
    static = dict(STATIC_MODEL)
    static["probe_frequency_ghz"] = probe_ghz
    raw = measurement.read_raw_csv(raw_path)
    analysis = measurement.analyze(
        delays_ns=raw["delay_ns"], p_ground=raw["p_g"], p_excited=raw["p_e"],
        quadratures=measurement.quadratures_from_raw(raw, len(WINDOWS_NS)),
        windows_ns=WINDOWS_NS, probe_frequency_ghz=probe_ghz,
        frequency_of_coordinate=frequency, park=PARK, target=TARGET, shots=noise_shots,
        ideal_amplitude=ideal)
    document = measurement.build_summary(
        device="q5", park=PARK, scale=SCALE, park_coordinate=PARK, target_coordinate=TARGET,
        normalized_amplitude=amplitude, delays_ns=delays,
        windows_ns=WINDOWS_NS, shots=noise_shots, rounds=1,
        recovery_ns=RECOVERY_NS, command=command, trace=analysis, static_flux_model=static,
        differentiator={"method": "fixed_window", "window_ns": window_fine},
        timestamp="2026-09-16T01:00:00", controller_commit="16001e0", code_commit="test",
        operator_note="synthetic", files={"raw_csv": measurement.describe_file(raw_path),
                                          "command_json": measurement.describe_file(command_path)})
    summary_path = measurement.write_summary(tmp_path/f"{name}_summary.json", document)
    return {"summary": summary_path, "raw": raw_path, "command": command,
            "analysis": analysis, "delays": delays, "truth": seen, "probe_ghz": probe_ghz}


def test_synthetic_measurement_recovers_the_commanded_amplitude(tmp_path):
    built = build_measurement(tmp_path, noise_shots=20000)
    analysis = built["analysis"]
    support = analysis["support"]
    assert support.mean() > 0.9
    error = np.asarray(analysis["normalized_amplitude"])[support]-built["truth"][support]
    assert np.sqrt(np.mean(error**2)) < 5e-3
    assert analysis["resolved"]["ambiguous_count"] == 0
    assert len(analysis["resolved"]["rungs"]) == len(WINDOWS_NS)


def test_measurement_summary_validates_and_round_trips(tmp_path):
    built = build_measurement(tmp_path)
    document = measurement.read_summary(built["summary"], device="q5", verify_hashes=True)
    assert document["schema"] == schema.MEASUREMENT_SCHEMA
    command = measurement.command_from_summary(document)
    assert command.edges_ns[-1] == pytest.approx(built["command"].edges_ns[-1])


def test_summary_rejects_a_changed_raw_file(tmp_path):
    built = build_measurement(tmp_path)
    Path(built["raw"]).write_text("delay_ns,p_g\n0,0\n")
    with pytest.raises(schema.SchemaError, match="SHA-256"):
        measurement.read_summary(built["summary"], device="q5", verify_hashes=True)


def test_summary_rejects_a_tampered_command(tmp_path):
    built = build_measurement(tmp_path)
    document = measurement.read_summary(built["summary"], device="q5")
    path = Path(document["files"]["command_json"]["path"])
    path.write_text(json.dumps({"edges_ns": [0.0, 1000.0], "values": [1.0]}))
    with pytest.raises(schema.SchemaError, match="hashes to"):
        measurement.command_from_summary(document)


def test_end_to_end_fitter_recovers_the_known_plant(tmp_path):
    first = build_measurement(tmp_path, seed=1, noise_shots=20000, name="q5_a")
    second = build_measurement(tmp_path, seed=2, noise_shots=20000, name="q5_b")
    out = tmp_path/"q5_candidate.json"
    code = fitter.main([
        "--summary", str(first["summary"]), str(second["summary"]),
        "--device", "q5", "--park", str(PARK), "--scale", str(SCALE),
        "--out", str(out), "--folds", "5", "--emission-sample-ns", "4000",
        "--inverse-horizon-ns", "800000", "--recovery-ns", "1600000",
    ])
    assert code == 0
    document = schema.read_json(out)
    model = schema.validate_model_document(document, device="q5", park=PARK, scale=SCALE)
    assert document["acceptance"] == {"software": True, "scientific": False, "hardware": False}
    recovered = np.asarray(document["calibration"]["fit_settings"]["plant_coefficients"])
    assert recovered == pytest.approx(TRUE_PLANT, abs=5e-3)
    assert document["model"]["taus_us"] == TAUS_US
    assert np.sum(np.abs(model.coefficients)) <= 0.25+1e-12
    cross = document["calibration"]["cross_validation"]
    assert cross["forecast_improvement"] > 5.0
    assert cross["round_trip_park_error_rms"] < 0.02
    assert out.with_name(out.stem+"_audit.png").exists()


def test_fitted_candidate_is_refused_by_the_production_loader(tmp_path):
    first = build_measurement(tmp_path, seed=3, noise_shots=20000, name="q5_c")
    out = tmp_path/"q5_candidate.json"
    fitter.main(["--summary", str(first["summary"]), "--device", "q5", "--park", str(PARK),
                 "--scale", str(SCALE), "--out", str(out), "--folds", "5"])
    with pytest.raises(schema.SchemaError, match="acceptance.scientific=false"):
        schema.load_model(out, device="q5", park=PARK, scale=SCALE)
    model, _ = schema.load_model(out, device="q5", park=PARK, scale=SCALE,
                                 diagnostic_override=True)
    assert model.taus_ns.size == 4


def test_fitter_refuses_a_cross_device_summary(tmp_path):
    built = build_measurement(tmp_path, name="q5_d")
    with pytest.raises(schema.SchemaError, match="device"):
        fitter.load_traces([built["summary"]], device="q3")
