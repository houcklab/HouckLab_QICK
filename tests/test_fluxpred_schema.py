import copy
import json

import pytest

from fluxpred import schema
from fluxpred.schema import SchemaError


Q3 = dict(device="q3", park=1200.0, scale=9000.0)
Q5 = dict(device="q5", park=0.0, scale=0.3955)


def q5_document(**overrides):
    document = schema.build_model_document(
        device="q5", park=Q5["park"], scale=Q5["scale"],
        taus_us=[8.0, 24.0, 64.0, 192.0], coefficients=[0.05, -0.03, 0.02, -0.01],
        source_files=["/nas/q5_raw.csv"], source_sha256=["a" * 64],
        static_flux_model={"kind": "transmon_p4"}, fit_settings={"regularization": 1e-4},
        cross_validation={"folds": 5, "held_out_rms": 0.004})
    document.update(overrides)
    return document


def q3_document():
    return schema.build_model_document(
        device="q3", park=Q3["park"], scale=Q3["scale"],
        taus_us=[8.0, 24.0, 64.0, 192.0], coefficients=[0.05, -0.03, 0.02, -0.01],
        source_files=["/nas/q3_raw.csv"], source_sha256=["b" * 64])


def write(tmp_path, document, name="model.json"):
    path = tmp_path / name
    path.write_text(json.dumps(document))
    return path


def test_build_and_validate_round_trip():
    document = q5_document()
    model = schema.validate_model_document(document, device="q5", unit="V", **{
        "park": Q5["park"], "scale": Q5["scale"]})
    assert model.taus_ns.tolist() == [8000.0, 24000.0, 64000.0, 192000.0]
    assert model.coefficients.shape == (1, 4)
    assert document["acceptance"] == {"software": False, "scientific": False, "hardware": False}


def test_json_round_trip_is_stable(tmp_path):
    document = q5_document()
    path = write(tmp_path, document)
    restored = schema.read_json(path)
    assert restored == document
    schema.validate_model_document(restored)


def test_amplitude_conditioned_model_round_trip():
    document = schema.build_model_document(
        device="q3", park=Q3["park"], scale=Q3["scale"], taus_us=[8.0, 24.0],
        amplitudes=[0.5, 1.0], coefficients=[[0.05, -0.02], [0.06, -0.03]],
        source_files=["/nas/q3.csv"], source_sha256=["c" * 64])
    model = schema.validate_model_document(document)
    assert model.amplitudes.tolist() == [0.5, 1.0]
    assert model.coefficients.shape == (2, 2)


def test_wrong_device_is_rejected(tmp_path):
    path = write(tmp_path, q3_document())
    with pytest.raises(SchemaError, match="device"):
        schema.load_model(path, device="q5", park=Q5["park"], scale=Q5["scale"],
                          diagnostic_override=True)


def test_controller_device_mismatch_is_rejected():
    document = q5_document(controller="QICK")
    with pytest.raises(SchemaError, match="QUA"):
        schema.validate_model_document(document)


def test_wrong_coordinate_unit_is_rejected():
    document = q5_document()
    document["coordinate"]["unit"] = "DAC_gain"
    with pytest.raises(SchemaError, match="unit"):
        schema.validate_model_document(document)


def test_park_mismatch_is_rejected(tmp_path):
    path = write(tmp_path, q5_document())
    with pytest.raises(SchemaError, match="park"):
        schema.load_model(path, device="q5", park=0.01, scale=Q5["scale"],
                          diagnostic_override=True)


def test_scale_mismatch_is_rejected(tmp_path):
    path = write(tmp_path, q5_document())
    with pytest.raises(SchemaError, match="scale"):
        schema.load_model(path, device="q5", park=Q5["park"], scale=0.4,
                          diagnostic_override=True)


def test_stale_schema_version_is_rejected():
    document = q5_document(schema="houcklab.fluxpred.model.v0")
    with pytest.raises(SchemaError, match="schema"):
        schema.validate_model_document(document)


def test_unknown_extra_field_is_rejected():
    document = q5_document()
    document["extra"] = 1
    with pytest.raises(SchemaError, match="unsupported field"):
        schema.validate_model_document(document)


def test_missing_field_is_rejected():
    document = q5_document()
    del document["calibration"]
    with pytest.raises(SchemaError, match="missing required field"):
        schema.validate_model_document(document)


def test_nonunity_dc_gain_is_rejected():
    document = q5_document()
    document["model"]["dc_gain"] = 0.98
    with pytest.raises(SchemaError, match="dc_gain"):
        schema.validate_model_document(document)


@pytest.mark.parametrize("taus", [[-8.0, 24.0], [0.0, 24.0], [24.0, 8.0]])
def test_invalid_time_constants_are_rejected(taus):
    document = q5_document()
    document["model"]["taus_us"] = taus
    document["model"]["coefficients"] = [0.01] * len(taus)
    with pytest.raises(SchemaError):
        schema.validate_model_document(document)


def test_coefficient_l1_overflow_is_rejected():
    document = q5_document()
    document["model"]["coefficients"] = [0.2, 0.2, 0.2, 0.2]
    with pytest.raises(SchemaError, match="L1"):
        schema.validate_model_document(document)


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_json_literals_are_rejected(tmp_path, literal):
    path = tmp_path / "bad.json"
    path.write_text('{"model": {"coefficients": [%s]}}' % literal)
    with pytest.raises(SchemaError, match="nonfinite"):
        schema.read_json(path)


def test_coefficient_shape_mismatch_is_rejected():
    document = q5_document()
    document["model"]["coefficients"] = [0.05, -0.03]
    with pytest.raises(SchemaError, match="shape"):
        schema.validate_model_document(document)


def test_missing_provenance_is_rejected():
    document = q5_document()
    document["calibration"]["source_files"] = []
    document["calibration"]["source_sha256"] = []
    with pytest.raises(SchemaError, match="at least one"):
        schema.validate_model_document(document)


def test_provenance_length_mismatch_is_rejected():
    document = q5_document()
    document["calibration"]["source_sha256"] = ["a" * 64, "b" * 64]
    with pytest.raises(SchemaError, match="provenance mismatch"):
        schema.validate_model_document(document)


def test_malformed_hash_is_rejected():
    document = q5_document()
    document["calibration"]["source_sha256"] = ["NOTAHASH"]
    with pytest.raises(SchemaError, match="SHA-256"):
        schema.validate_model_document(document)


def test_ridge_derived_calibration_method_is_rejected():
    document = q5_document()
    document["calibration"]["method"] = "spectroscopy_ridge"
    with pytest.raises(SchemaError, match="ridge"):
        schema.validate_model_document(document)


def test_failed_scientific_gate_blocks_loading(tmp_path):
    path = write(tmp_path, q5_document())
    with pytest.raises(SchemaError, match="acceptance.scientific=false"):
        schema.load_model(path, device="q5", park=Q5["park"], scale=Q5["scale"])


def test_diagnostic_override_allows_a_candidate(tmp_path):
    path = write(tmp_path, q5_document())
    model, document = schema.load_model(path, device="q5", park=Q5["park"], scale=Q5["scale"],
                                        diagnostic_override=True)
    assert document["acceptance"]["scientific"] is False
    assert model.taus_ns.size == 4


def test_accepted_model_loads_without_override(tmp_path):
    document = q5_document()
    document["acceptance"] = {"software": True, "scientific": True, "hardware": True}
    path = write(tmp_path, document)
    model, _ = schema.load_model(path, device="q5", park=Q5["park"], scale=Q5["scale"],
                                 require_hardware=True)
    assert model.taus_ns.size == 4


def test_non_boolean_acceptance_gate_is_rejected():
    document = q5_document()
    document["acceptance"]["scientific"] = "true"
    with pytest.raises(SchemaError, match="boolean"):
        schema.validate_model_document(document)


def test_amplitude_beyond_the_calibrated_range_is_refused(tmp_path):
    document = q5_document()
    document["acceptance"] = {"software": True, "scientific": True, "hardware": True}
    path = write(tmp_path, document)
    with pytest.raises(SchemaError, match="outside the calibrated"):
        schema.load_model(path, device="q5", park=Q5["park"], scale=Q5["scale"],
                          amplitude_range=(0.0, 1.4))


def test_source_hash_verification_detects_a_changed_file(tmp_path):
    raw = tmp_path / "raw.csv"
    raw.write_text("t,x,y\n0,1,0\n")
    document = q5_document()
    document["calibration"]["source_files"] = [str(raw)]
    document["calibration"]["source_sha256"] = [schema.sha256_file(raw)]
    assert schema.verify_source_hashes(document)[0]["status"] == "verified"
    raw.write_text("t,x,y\n0,0,1\n")
    with pytest.raises(SchemaError, match="SHA-256"):
        schema.verify_source_hashes(document)


def test_missing_source_file_fails_unless_explicitly_allowed(tmp_path):
    document = q5_document()
    document["calibration"]["source_files"] = [str(tmp_path / "absent.csv")]
    with pytest.raises(SchemaError, match="not readable"):
        schema.verify_source_hashes(document)
    assert schema.verify_source_hashes(document, missing_ok=True)[0]["status"] == "missing"


def measurement_document(**overrides):
    document = {
        "schema": schema.MEASUREMENT_SCHEMA,
        "device": "q5", "controller": "QUA",
        "coordinate": {"unit": "V", "park": 0.0, "scale": 0.3955},
        "sequence": {"park_coordinate": 0.0, "target_coordinate": 0.3955,
                     "normalized_amplitude": 1.0, "delays_ns": [1000.0, 2000.0, 3000.0],
                     "probe_windows_ns": [80.0, 400.0], "shots_per_point": 180,
                     "rounds": 4, "recovery_ns": 400000.0, "emitted_plan_sha256": "d" * 64},
        "observable": {"quadratures": ["x", "y"], "contrast": [0.9, 0.88, 0.85],
                       "contrast_threshold": 0.25, "supported_fraction": 1.0},
        "analysis": {"nominal_phase_model": {"kind": "transmon_p4"},
                     "unwrap": {"method": "multiwindow_branch"},
                     "differentiator": {"method": "fixed_window", "window_ns": 400.0},
                     "detuning_uncertainty_mhz": [0.02, 0.02, 0.03]},
        "provenance": {"timestamp": "2026-09-15T23:00:00", "controller_commit": "16001e0",
                       "code_commit": "16001e0", "operator_note": "center calibration"},
        "files": {"raw_csv": {"path": "/nas/raw.csv", "sha256": "e" * 64, "bytes": 1024}},
    }
    document.update(overrides)
    return document


def test_measurement_document_validates():
    assert schema.validate_measurement_document(measurement_document(), device="q5")


def test_measurement_rejects_a_single_quadrature():
    document = measurement_document()
    document["observable"]["quadratures"] = ["x"]
    with pytest.raises(SchemaError, match="quadratures"):
        schema.validate_measurement_document(document)


def test_measurement_rejects_unsorted_delays():
    document = measurement_document()
    document["sequence"]["delays_ns"] = [3000.0, 1000.0, 2000.0]
    with pytest.raises(SchemaError, match="increasing"):
        schema.validate_measurement_document(document)


def test_measurement_rejects_zero_shots():
    document = measurement_document()
    document["sequence"]["shots_per_point"] = 0
    with pytest.raises(SchemaError, match="positive integer"):
        schema.validate_measurement_document(document)


def test_measurement_rejects_a_cross_device_coordinate():
    document = measurement_document()
    document["coordinate"]["unit"] = "DAC_gain"
    with pytest.raises(SchemaError, match="unit"):
        schema.validate_measurement_document(document)


def test_model_and_measurement_hashes_are_order_independent():
    left = schema.sha256_json({"a": 1, "b": [1, 2]})
    right = schema.sha256_json({"b": [1, 2], "a": 1})
    assert left == right


def test_build_model_document_is_not_mutated_by_validation():
    document = q5_document()
    before = copy.deepcopy(document)
    schema.validate_model_document(document)
    assert document == before
