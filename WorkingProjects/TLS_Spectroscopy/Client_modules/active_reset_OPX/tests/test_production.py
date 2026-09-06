from pathlib import Path
import runpy
import sys
from types import SimpleNamespace

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


def test_active_session_owns_timing_frequency_calibration_and_loop_order():
    calibration = {"schema_version": 1, "payload": {}, "loop": {}}
    session = ProductionResetSession.active(
        calibration=calibration,
        method_frequency_mhz=4366.392029,
    )

    cfg = session.apply({
        "relax_delay": 1000.0,
        "ff_park_gain": 29000,
        "randomize_point_order": True,
        "shuffle_detuning": True,
        "remeasure_outliers": True,
    })

    assert cfg["reset_mode"] == "opx_unbounded"
    assert cfg["opx_reset_calibration"] == calibration
    assert cfg["qubit_pi_freq"] == pytest.approx(4366.392029)
    assert cfg["reset_pi_freq"] == pytest.approx(4366.392029)
    assert cfg["relax_delay"] == pytest.approx(10.0)
    assert cfg["opx_inter_shot_delay_us"] == pytest.approx(10.0)
    assert cfg["opx_persistent_park"] is True
    assert cfg["opx_hard_flux_steps"] is True
    assert cfg["randomize_point_order"] is False
    assert cfg["shuffle_detuning"] is False
    assert cfg["remeasure_outliers"] is False


def test_active_calibration_prepares_excited_references_at_park_history_frequency():
    cfg = build_calibration_config(
        {
            "qubit_pi_freq": 4340.3,
            "qubit_freq": 4340.3,
            "ff_park_gain": 29000,
        },
        method_frequency_mhz=4366.392029,
    )

    assert cfg["qubit_pi_freq"] == pytest.approx(4366.392029)
    assert cfg["reset_pi_freq"] == pytest.approx(4366.392029)
    assert cfg["relax_delay"] == pytest.approx(1000.0)
    assert cfg["opx_persistent_park"] is False
    assert cfg["opx_hard_flux_steps"] is False


def test_latest_park_history_is_discovered_without_a_runner_path_setting(tmp_path):
    old = tmp_path / "q3" / "q3_2026_09_04" / "q3_01_active_reset_OPX_park_history_spectroscopy" / "result.json"
    new = tmp_path / "q3" / "q3_2026_09_05" / "q3_02_active_reset_OPX_park_history_spectroscopy" / "result.json"
    old.parent.mkdir(parents=True)
    new.parent.mkdir(parents=True)
    old.write_text("{}")
    new.write_text("{}")
    old.touch()
    new.touch()
    old_time = old.stat().st_mtime - 10.0
    import os
    os.utime(old, (old_time, old_time))

    assert latest_park_history_result(tmp_path, "q3") == Path(new)


def test_unknown_runner_reset_mode_is_rejected():
    with pytest.raises(ValueError, match="active.*passive"):
        normalize_reset_mode("feedback")


def test_active_session_is_calibrated_automatically_with_central_defaults(tmp_path, monkeypatch):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import production

    result = tmp_path / "q3" / "q3_2026_09_05" / "q3_02_active_reset_OPX_park_history_spectroscopy" / "result.json"
    result.parent.mkdir(parents=True)
    result.write_text("{}")
    observed = {}

    class Bundle:
        def to_dict(self):
            return {"schema_version": 1, "payload": {}, "loop": {}}

    monkeypatch.setattr(
        production,
        "load_park_history_method_frequencies",
        lambda path: {"opx_unbounded": 4366.392029},
    )

    def acquire(soc, soccfg, cfg, **kwargs):
        observed["cfg"] = dict(cfg)
        observed["kwargs"] = dict(kwargs)
        return Bundle(), {"payload": {}, "loop": {}}

    monkeypatch.setattr(production, "acquire_calibration", acquire)
    monkeypatch.setattr(production, "save_calibration", lambda path, bundle: Path(path))
    monkeypatch.setattr(production, "save_raw_calibration", lambda path, raw: Path(path))
    monkeypatch.setattr(production, "validate_confident_calibration", lambda bundle, **kwargs: bundle)

    session = prepare_reset_session(
        "active",
        outer_folder=tmp_path,
        qubit="q3",
        base_cfg={"qubit_pi_freq": 4340.3, "ff_park_gain": 29000},
        soc=object(),
        soccfg=object(),
        purpose="test",
        now="2026_09_05_12_34_56",
    )

    assert session.runtime_mode == "opx_unbounded"
    assert session.method_frequency_mhz == pytest.approx(4366.392029)
    assert observed["cfg"]["qubit_pi_freq"] == pytest.approx(4366.392029)
    assert observed["kwargs"]["shots"] == 2000
    assert observed["kwargs"]["ground_confidence_fidelity"] == pytest.approx(0.7)


def test_passive_session_skips_frequency_lookup_and_hardware_calibration(tmp_path):
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


def test_transmission_sweep_smoke_selects_only_the_production_sweep():
    import ast

    path = Path(__file__).parents[1] / "production_transmission_sweep_q3.py"
    tree = ast.parse(path.read_text())
    assignments = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Subscript):
            continue
        owner = getattr(target.value, "attr", None)
        key = ast.literal_eval(target.slice)
        assignments[(owner, key)] = ast.literal_eval(node.value)

    assert assignments[("P_TRANSMISSION", "run")] is False
    assert assignments[("P_TRANSMISSION_SWEEP", "run")] is True
    assert assignments[("P_TRANSMISSION_SWEEP", "shots")] == 100
    assert assignments[("P_TRANSMISSION_SWEEP", "freq_points")] == 41
    assert assignments[("P_TRANSMISSION_SWEEP", "gain_points")] == 3
    assert assignments[("P_SS_CAL", "run")] is False


def test_readout_opt_smoke_selects_only_the_production_optimizer():
    import ast

    path = Path(__file__).parents[1] / "production_readout_opt_smoke_q3.py"
    tree = ast.parse(path.read_text())
    updates = []
    disabled = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "update" and isinstance(node.func.value, ast.Attribute):
                if node.func.value.attr == "P_READOUT_OPT":
                    updates.append(ast.literal_eval(node.args[0]))
        if not isinstance(node, ast.Assign):
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Subscript):
            continue
        owner = getattr(target.value, "attr", None)
        key = ast.literal_eval(target.slice)
        if key == "run" and owner != "P_READOUT_OPT":
            disabled.append((owner, ast.literal_eval(node.value)))

    assert updates == [{
        "run": True,
        "shots": 20,
        "num_pi": 1,
        "pulse_type": "X180",
        "freq_span_mhz": 1.0,
        "freq_points": 3,
        "gain_min": 1000,
        "gain_max": 2500,
        "gain_points": 5,
    }]
    assert disabled
    assert all(value is False for _, value in disabled)


def test_qubit_spec_equivalence_runner_uses_identical_passive_and_active_grids():
    import ast

    path = Path(__file__).parents[1] / "production_qubit_spec_equivalence_q3.py"
    tree = ast.parse(path.read_text())
    updates = []
    modes = []
    main_calls = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "update" and isinstance(node.func.value, ast.Attribute):
                if node.func.value.attr == "P_QUBIT_SPEC":
                    updates.append(ast.literal_eval(node.args[0]))
            if node.func.attr == "main" and isinstance(node.func.value, ast.Name):
                if node.func.value.id == "runner":
                    main_calls += 1
        if not isinstance(node, ast.Assign):
            continue
        target = node.targets[0]
        if (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "runner"
            and target.attr == "RESET_MODE"
        ):
            modes.append(ast.literal_eval(node.value))

    assert updates == [{
        "run": True,
        "shots": 300,
        "freq_start_mhz": 4364.5,
        "freq_stop_mhz": 4367.5,
        "freq_points": 31,
        "spec_gain": 15000,
        "spec_length_us": 1.0,
        "relax_delay_us": 1000.0,
    }]
    assert modes == ["passive", "active"]
    assert main_calls == 2


def test_full_qubit_spec_runner_uses_gate_calibration_path(monkeypatch):
    calls = []
    runner = SimpleNamespace(
        LIVE_PLOTS=True,
        RESET_MODE="passive",
        P_TRANSMISSION={"run": True},
        P_TRANSMISSION_SWEEP={"run": True},
        P_QUBIT_SPEC={"run": False},
        P_QUBIT_SPEC_SWEEP={"run": True},
        P_SS_CAL={"run": True},
        P_RABI_CHEVRON_IQ={"run": True},
        P_RABI_CHEVRON_SS={"run": True},
        P_READOUT_OPT={"run": True},
        P_QUBIT_OPT={"run": True},
    )
    runner.main = lambda: calls.append({
        "reset_mode": runner.RESET_MODE,
        "qubit_spec": dict(runner.P_QUBIT_SPEC),
        "selected": [
            runner.P_TRANSMISSION["run"],
            runner.P_TRANSMISSION_SWEEP["run"],
            runner.P_QUBIT_SPEC["run"],
            runner.P_QUBIT_SPEC_SWEEP["run"],
            runner.P_SS_CAL["run"],
            runner.P_RABI_CHEVRON_IQ["run"],
            runner.P_RABI_CHEVRON_SS["run"],
            runner.P_READOUT_OPT["run"],
            runner.P_QUBIT_OPT["run"],
        ],
    })
    from WorkingProjects.TLS_Spectroscopy.Client_modules import Runners

    module_name = (
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.GateCalibration"
    )
    monkeypatch.setitem(sys.modules, module_name, runner)
    monkeypatch.setattr(Runners, "GateCalibration", runner, raising=False)
    path = Path(__file__).parents[1] / "production_qubit_spec_q3.py"

    runpy.run_path(str(path), run_name="__main__")

    assert calls == [{
        "reset_mode": "passive",
        "qubit_spec": {
            "run": True,
            "shots": 1000,
            "freq_start_mhz": 4364.5,
            "freq_stop_mhz": 4367.5,
            "freq_points": 201,
            "spec_gain": 15000,
            "spec_length_us": 1.0,
            "relax_delay_us": 1000.0,
        },
        "selected": [False, False, True, False, False, False, False, False, False],
    }]
