import json

import numpy as np
import pytest

from fluxpred import production, schema
from fluxpred.schema import SchemaError

Q3 = dict(device="q3", park=-25146.0, scale=10396.0)
Q5 = dict(device="q5", park=0.156232010522, scale=0.231509604478)
HOLDS_NS = (2_000.0, 40_000.0, 80_000.0, 200_000.0)


def model_file(tmp_path, device, park, scale, *, accepted=False, name="model.json"):
    document = schema.build_model_document(
        device=device, park=park, scale=scale, taus_us=[8.0, 24.0, 64.0, 192.0],
        coefficients=[-0.056, 0.036, -0.028, 0.020],
        source_files=["/nas/raw.csv"], source_sha256=["a"*64],
        acceptance={"software": True, "scientific": accepted, "hardware": accepted})
    path = tmp_path/name
    path.write_text(json.dumps(document))
    return path


def test_mode_defaults_to_off_when_nothing_is_set():
    assert production.resolve_mode("q3", environ={}) == "off"
    assert production.resolve_mode("q5", environ={}) == "off"


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError, match="must be one of"):
        production.resolve_mode("q3", environ={"Q3_FLUXPRED_MODE": "piecewise"})


@pytest.mark.parametrize("device,coords", [("q3", Q3), ("q5", Q5)])
def test_off_selection_carries_no_model(device, coords):
    choice = production.selection(device, park=coords["park"], scale=coords["scale"], environ={})
    assert choice["mode"] == "off"
    assert choice["model"] is None and choice["model_path"] is None
    assert "no software flux correction" in "\n".join(production.describe(choice))


def test_neutral_mode_requires_an_explicit_model_path():
    with pytest.raises(ValueError, match="MODEL_JSON"):
        production.selection("q3", park=Q3["park"], scale=Q3["scale"],
                             environ={"Q3_FLUXPRED_MODE": "neutral"})


def test_unaccepted_candidate_is_refused_without_an_override(tmp_path):
    path = model_file(tmp_path, "q3", Q3["park"], Q3["scale"])
    with pytest.raises(SchemaError, match="acceptance.scientific=false"):
        production.selection("q3", park=Q3["park"], scale=Q3["scale"],
                             environ={"Q3_FLUXPRED_MODE": "neutral",
                                      "Q3_FLUXPRED_MODEL_JSON": str(path)})


def test_diagnostic_override_is_allowed_and_loudly_reported(tmp_path):
    path = model_file(tmp_path, "q3", Q3["park"], Q3["scale"])
    choice = production.selection(
        "q3", park=Q3["park"], scale=Q3["scale"],
        environ={"Q3_FLUXPRED_MODE": "neutral", "Q3_FLUXPRED_MODEL_JSON": str(path),
                 "Q3_FLUXPRED_DIAGNOSTIC_OVERRIDE": "1"})
    assert choice["diagnostic_override"]
    text = "\n".join(production.describe(choice))
    assert "WARNING" in text and "not a production-validated correction" in text


def test_accepted_candidate_loads_and_prints_full_provenance(tmp_path):
    path = model_file(tmp_path, "q5", Q5["park"], Q5["scale"], accepted=True)
    choice = production.selection(
        "q5", park=Q5["park"], scale=Q5["scale"],
        environ={"Q5_FLUXPRED_MODE": "neutral", "Q5_FLUXPRED_MODEL_JSON": str(path)})
    text = "\n".join(production.describe(choice))
    for expected in ("model ", "sha256", "schema", "coordinate", "taus_us", "coeffs",
                     "method", "sources", "acceptance"):
        assert expected in text
    assert choice["model_sha256"] == schema.sha256_file(path)
    assert "WARNING" not in text


def test_cross_device_model_is_refused(tmp_path):
    path = model_file(tmp_path, "q3", Q3["park"], Q3["scale"], accepted=True)
    with pytest.raises(SchemaError, match="device"):
        production.selection("q5", park=Q5["park"], scale=Q5["scale"],
                             environ={"Q5_FLUXPRED_MODE": "neutral",
                                      "Q5_FLUXPRED_MODEL_JSON": str(path)})


def test_wrong_park_is_refused(tmp_path):
    path = model_file(tmp_path, "q5", Q5["park"], Q5["scale"], accepted=True)
    with pytest.raises(SchemaError, match="park"):
        production.selection("q5", park=0.2, scale=Q5["scale"],
                             environ={"Q5_FLUXPRED_MODE": "neutral",
                                      "Q5_FLUXPRED_MODEL_JSON": str(path)})


def test_off_mode_emits_the_plain_uncorrected_square_command():
    choice = production.selection("q3", park=Q3["park"], scale=Q3["scale"], environ={})
    bank = production.condition_commands(
        choice, amplitude=1.0, holds_ns=HOLDS_NS, recovery_ns=400_000.0,
        schedule_first_ns=2000.0, schedule_growth=1.35, schedule_max_ns=100_000.0,
        quantum_ns=1000.0)
    assert len(bank) == len(HOLDS_NS)
    for entry in bank:
        assert entry["command"].values.tolist() == [1.0, 0.0]


def test_neutral_mode_emits_one_distinct_command_per_condition(tmp_path):
    path = model_file(tmp_path, "q3", Q3["park"], Q3["scale"], accepted=True)
    choice = production.selection(
        "q3", park=Q3["park"], scale=Q3["scale"],
        environ={"Q3_FLUXPRED_MODE": "neutral", "Q3_FLUXPRED_MODEL_JSON": str(path)})
    bank = production.condition_commands(
        choice, amplitude=1.0, holds_ns=HOLDS_NS, recovery_ns=1_600_000.0,
        schedule_first_ns=2000.0, schedule_growth=1.35, schedule_max_ns=100_000.0,
        quantum_ns=1000.0)
    hashes = {entry["hold_ns"]: len(entry["command"].values) for entry in bank}
    assert len(hashes) == len(HOLDS_NS)
    record = production.provenance(choice, bank=bank, backend="qick", code_commit="deadbee")
    assert len(record["conditions"]) == len(HOLDS_NS)
    assert len(record["plan_sha256"]) == 64
    assert len({condition["command_sha256"] for condition in record["conditions"]}) == len(HOLDS_NS)
    assert record["acceptance"] == {"software": True, "scientific": True, "hardware": True}


def test_provenance_is_json_serializable(tmp_path):
    path = model_file(tmp_path, "q5", Q5["park"], Q5["scale"], accepted=True)
    choice = production.selection(
        "q5", park=Q5["park"], scale=Q5["scale"],
        environ={"Q5_FLUXPRED_MODE": "neutral", "Q5_FLUXPRED_MODEL_JSON": str(path)})
    bank = production.condition_commands(
        choice, amplitude=1.0, holds_ns=HOLDS_NS, recovery_ns=1_600_000.0,
        schedule_first_ns=2000.0, schedule_growth=1.35, schedule_max_ns=100_000.0,
        quantum_ns=1000.0)
    record = production.provenance(choice, bank=bank, backend="qua", code_commit="16001e0")
    json.dumps(record, allow_nan=False)


def test_amplitude_beyond_the_calibrated_range_is_refused(tmp_path):
    path = model_file(tmp_path, "q3", Q3["park"], Q3["scale"], accepted=True)
    with pytest.raises(SchemaError, match="outside the calibrated"):
        production.selection("q3", park=Q3["park"], scale=Q3["scale"],
                             environ={"Q3_FLUXPRED_MODE": "neutral",
                                      "Q3_FLUXPRED_MODEL_JSON": str(path)},
                             amplitude_range=(0.0, 1.3))


def test_neutral_conditions_fit_the_qick_instruction_budget(tmp_path):
    from fluxpred import qick as qick_backend

    path = model_file(tmp_path, "q3", Q3["park"], Q3["scale"], accepted=True)
    choice = production.selection(
        "q3", park=Q3["park"], scale=Q3["scale"],
        environ={"Q3_FLUXPRED_MODE": "neutral", "Q3_FLUXPRED_MODEL_JSON": str(path)})
    bank = production.condition_commands(
        choice, amplitude=1.0, holds_ns=HOLDS_NS, recovery_ns=1_600_000.0,
        schedule_first_ns=2000.0, schedule_growth=1.35, schedule_max_ns=100_000.0,
        quantum_ns=1000.0)
    for entry in bank:
        plan = qick_backend.compile_command(
            entry["command"], park_gain=Q3["park"], scale_gain=Q3["scale"],
            clock_ns=1000.0/430.08, max_instructions=4096)
        assert plan.instruction_estimate <= 4096
        assert abs(plan.segments[-1].gain-round(Q3["park"])) <= 1
