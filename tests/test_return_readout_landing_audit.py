"""Hardware-free contracts for the independent q3 return/readout audit."""

import importlib

import pytest


MODULE = (
    "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners."
    "ReturnReadoutLandingAudit"
)


def audit():
    return importlib.import_module(MODULE)


def test_landing_matrix_brackets_each_repeat_without_a_sync_session():
    arms = audit().landing_arms()
    names = [arm.name for arm in arms]
    assert names[0] == "landing_control_start"
    assert names[-1] == "landing_control_end"
    assert len(names) == len(set(names))
    for repeat in (1, 2, 3):
        for stem in ("recovery_1us", "recovery_5us", "recovery_40us",
                     "continuous_stateful_1us", "continuous_stateful_5us",
                     "continuous_stateful_25us"):
            assert f"{stem}_l{repeat}" in names
        assert any(name.startswith(f"landing_control_l{repeat}_") for name in names)
    assert all(arm.reset_mode == "active" for arm in arms)


def test_q3_timing_arm_config_separates_truncated_from_continuous_return():
    module = audit()
    baseline = {"readout_thermalization_us": 10.0}
    short = module.arm_config(baseline, module.AuditArm("short", 1, 1, False))
    full = module.arm_config(baseline, module.AuditArm("full", 40, 1, True))
    assert short["flux_predistortion_recovery_us"] == 1
    assert short["flux_predistortion_return_prefix_us"] == 1
    assert short["flux_predistortion_overlap_payload_readout"] is False
    assert full["flux_predistortion_recovery_us"] == 40
    assert full["flux_predistortion_return_prefix_us"] == 1
    assert full["flux_predistortion_overlap_payload_readout"] is True
    assert full["diagnostic_iq_summary"] is True


def test_invalid_timing_arm_rejected_before_hardware_access():
    module = audit()
    with pytest.raises(ValueError, match="prefix"):
        module.validate_arm(module.AuditArm("bad", 5, 10, True))
