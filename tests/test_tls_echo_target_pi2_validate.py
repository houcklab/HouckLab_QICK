"""Analysis and source gates for the short target-pulse follow-up."""

import importlib

import pytest


validate = importlib.import_module(
    "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSEchoTargetPi2Validate")


def test_source_requires_finished_target_rabi_and_pinned_correction():
    source = {"schema": "q3.target-pi2-calibration.v1",
              "status": "complete_pi2_midpoint_unstable",
              "correction_sha256": validate.CORRECTION_SHA256,
              "site_frequency_ghz": 4.288,
              "chosen_frequency": {"offset_mhz": 2.5},
              "rabi_fit": {"valid": True, "pi_gain": 18000,
                           "pi2_gain": 8174}}
    assert validate.validate_source(source) == (4.288, 2.5, 18000, 8174)
    with pytest.raises(ValueError):
        validate.validate_source({**source, "status": "running"})


def test_refine_pi2_uses_nearby_half_height_crossing():
    rows = [{"gain": 6000, "response": .31},
            {"gain": 7500, "response": .43},
            {"gain": 8174, "response": .54},
            {"gain": 9000, "response": .60},
            {"gain": 10500, "response": .72}]
    result = validate.refine_pi2(rows, source_gain=8174)
    assert result["valid"]
    assert 7500 < result["gain"] < 8174


def test_refine_pi2_rejects_unresolved_curve():
    rows = [{"gain": gain, "response": .1}
            for gain in (6000, 7500, 8174, 9000)]
    assert not validate.refine_pi2(rows, source_gain=8174)["valid"]


def test_plan_is_high_shot_phase_validation_without_scout():
    p = validate.plan()
    assert p["fresh_t1_scan"] is False
    assert p["frequency_sweep"] is False
    assert p["shots_per_arm"] >= 1000
