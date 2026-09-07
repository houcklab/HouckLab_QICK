from pathlib import Path

import pytest

from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import (
    ProductionResetSession,
    build_calibration_config,
    latest_park_history_result,
    normalize_reset_mode,
    prepare_reset_session,
)


def test_user_active_mode_selects_the_unbounded_hardware_loop():
    assert normalize_reset_mode("active") == "opx_unbounded"
    assert normalize_reset_mode("opx_unbounded") == "opx_unbounded"
    assert normalize_reset_mode(True) == "opx_unbounded"


def test_user_passive_mode_never_requires_an_active_calibration():
    session = ProductionResetSession.passive()
    cfg = session.apply({"relax_delay": 625.0, "ff_park_gain": 29000})

    assert cfg["reset_mode"] == "passive"
    assert cfg["relax_delay"] == pytest.approx(625.0)
    assert cfg["opx_inter_shot_delay_us"] == pytest.approx(625.0)
    assert "opx_reset_calibration" not in cfg
    assert cfg["opx_persistent_park"] is True
    assert cfg["opx_hard_flux_steps"] is True
    assert cfg["qua_shot_order"] is True
    assert cfg["single_shot_state_order"] == "ge"


def test_active_session_owns_reset_timing_and_loop_order():
    calibration = {"schema_version": 1, "payload": {}, "loop": {}}
    session = ProductionResetSession.active(calibration, 4366.392029)
    cfg = session.apply({
        "relax_delay": 1000.0,
        "ff_park_gain": 29000,
        "qubit_pi_freq": 4358.125,
        "randomize_point_order": True,
        "shuffle_detuning": True,
        "remeasure_outliers": True,
    })

    assert cfg["reset_mode"] == "opx_unbounded"
    assert cfg["opx_reset_calibration"] == calibration
    assert cfg["qubit_pi_freq"] == pytest.approx(4358.125)
    assert cfg["reset_pi_freq"] == pytest.approx(4366.392029)
    assert cfg["relax_delay"] == pytest.approx(10.0)
    assert cfg["opx_inter_shot_delay_us"] == pytest.approx(10.0)
    assert cfg["opx_persistent_park"] is True
    assert cfg["opx_hard_flux_steps"] is True
    assert cfg["randomize_point_order"] is False
    assert cfg["shuffle_detuning"] is False
    assert cfg["remeasure_outliers"] is False


def test_active_calibration_uses_park_history_frequency():
    cfg = build_calibration_config(
        {"qubit_pi_freq": 4340.3, "qubit_freq": 4340.3, "ff_park_gain": 29000},
        method_frequency_mhz=4366.392029,
    )

    assert cfg["qubit_pi_freq"] == pytest.approx(4366.392029)
    assert cfg["reset_pi_freq"] == pytest.approx(4366.392029)
    assert cfg["relax_delay"] == pytest.approx(1000.0)
    assert cfg["opx_persistent_park"] is False
    assert cfg["opx_hard_flux_steps"] is False


def test_latest_park_history_is_discovered(tmp_path):
    old = tmp_path / "q3" / "q3_2026_09_04" / "q3_01_active_reset_OPX_park_history_spectroscopy" / "result.json"
    new = tmp_path / "q3" / "q3_2026_09_05" / "q3_02_active_reset_OPX_park_history_spectroscopy" / "result.json"
    old.parent.mkdir(parents=True)
    new.parent.mkdir(parents=True)
    old.write_text("{}")
    new.write_text("{}")
    old_time = old.stat().st_mtime - 10.0
    import os
    os.utime(old, (old_time, old_time))

    assert latest_park_history_result(tmp_path, "q3") == Path(new)


def test_unknown_runner_reset_mode_is_rejected():
    with pytest.raises(ValueError, match="active.*passive"):
        normalize_reset_mode("feedback")


def test_passive_session_skips_hardware_calibration(tmp_path):
    session = prepare_reset_session(
        "passive",
        outer_folder=tmp_path,
        qubit="q3",
        base_cfg={},
        soc=None,
        soccfg=None,
        purpose="test",
    )

    assert session.runtime_mode == "passive"
