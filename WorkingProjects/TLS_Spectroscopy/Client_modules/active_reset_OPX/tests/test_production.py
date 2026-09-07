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


def test_qubit_opt_smoke_runner_selects_only_qubit_optimization(monkeypatch):
    calls = []
    runner = SimpleNamespace(
        LIVE_PLOTS=True,
        RESET_MODE="active",
        P_TRANSMISSION={"run": True},
        P_TRANSMISSION_SWEEP={"run": True},
        P_QUBIT_SPEC={"run": True},
        P_QUBIT_SPEC_SWEEP={"run": True},
        P_SS_CAL={"run": True},
        P_RABI_CHEVRON_IQ={"run": True},
        P_RABI_CHEVRON_SS={"run": True},
        P_READOUT_OPT={"run": True},
        P_QUBIT_OPT={"run": False},
    )
    runner.main = lambda: calls.append({
        "reset_mode": runner.RESET_MODE,
        "qubit_opt": dict(runner.P_QUBIT_OPT),
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
    path = Path(__file__).parents[1] / "production_qubit_opt_smoke_q3.py"

    runpy.run_path(str(path), run_name="__main__")

    assert calls == [{
        "reset_mode": "passive",
        "qubit_opt": {
            "run": True,
            "shots": 50,
            "num_pi": 1,
            "pulse_type": "X180",
            "freq_span_mhz": 1.0,
            "freq_points": 5,
            "gain_min": 11500,
            "gain_max": 15500,
            "gain_points": 5,
            "x90_validation_shots": 100,
            "x90_validation_rounds": 2,
        },
        "selected": [False, False, False, False, False, False, False, False, True],
    }]


def test_ss_flux_ramp_smoke_runner_selects_only_flux_ramp_calibration(monkeypatch):
    calls = []
    runner = SimpleNamespace(
        LIVE_PLOTS=True,
        RESET_MODE="active",
        P_SS_CAL={"run": True},
        P_SS_FLUX_RAMP={"run": False},
        P_T1={"run": True},
        P_T1_FLUX_RAMP={"run": True},
    )
    runner.main = lambda: calls.append({
        "reset_mode": runner.RESET_MODE,
        "ss_flux_ramp": dict(runner.P_SS_FLUX_RAMP),
        "selected": [
            runner.P_SS_CAL["run"],
            runner.P_SS_FLUX_RAMP["run"],
            runner.P_T1["run"],
            runner.P_T1_FLUX_RAMP["run"],
        ],
    })
    from WorkingProjects.TLS_Spectroscopy.Client_modules import Runners

    module_name = (
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.SingleQubitCoherence"
    )
    monkeypatch.setitem(sys.modules, module_name, runner)
    monkeypatch.setattr(Runners, "SingleQubitCoherence", runner, raising=False)
    path = Path(__file__).parents[1] / "production_ss_flux_ramp_smoke_q3.py"

    runpy.run_path(str(path), run_name="__main__")

    assert calls == [{
        "reset_mode": "passive",
        "ss_flux_ramp": {
            "run": True,
            "shots": 500,
            "number_pi_pulses": 1,
            "ground_threshold": 0.7,
            "excursion_gain": -20000,
            "qubit_pi_gain": None,
            "flux_hold_us": 1.0,
            "flux_tail_compensation": None,
        },
        "selected": [False, True, False, False],
    }]


def test_tls_step1_smoke_runner_selects_only_resonator_flux_sweep(monkeypatch):
    calls = []
    runner = SimpleNamespace(
        LIVE_PLOTS=True,
        SET_YOKO=True,
        BASELINE_DC_OFFSET=0,
        RESET_MODE="active",
        P1_RESONATOR={"run": False},
        P2_QUBIT_SPEC_FULL={"run": True},
        P3_STEP_RESPONSE={"run_fit": True, "run_correct": True},
        P4_LONG_TIME={"run": True},
        P5_SS_CAL={"run": True},
        P6_3PT_T1={"run": True},
        P6_FULL_T1={"run": True},
    )
    runner.main = lambda: calls.append({
        "live_plots": runner.LIVE_PLOTS,
        "set_yoko": runner.SET_YOKO,
        "baseline": runner.BASELINE_DC_OFFSET,
        "reset_mode": runner.RESET_MODE,
        "step1": dict(runner.P1_RESONATOR),
        "selected": [
            runner.P1_RESONATOR["run"],
            runner.P2_QUBIT_SPEC_FULL["run"],
            runner.P3_STEP_RESPONSE["run_fit"],
            runner.P3_STEP_RESPONSE["run_correct"],
            runner.P4_LONG_TIME["run"],
            runner.P5_SS_CAL["run"],
            runner.P6_3PT_T1["run"],
            runner.P6_FULL_T1["run"],
        ],
    })
    from WorkingProjects.TLS_Spectroscopy.Client_modules import Runners

    module_name = (
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSpectroscopy"
    )
    monkeypatch.setitem(sys.modules, module_name, runner)
    monkeypatch.setattr(Runners, "TLSSpectroscopy", runner, raising=False)
    path = Path(__file__).parents[1] / "production_tls_step1_smoke_q3.py"

    runpy.run_path(str(path), run_name="__main__")

    assert calls == [{
        "live_plots": False,
        "set_yoko": False,
        "baseline": -25790,
        "reset_mode": "passive",
        "step1": {
            "run": True,
            "shots": 20,
            "freq_min": 6931.0,
            "freq_max": 6935.0,
            "freq_step": 0.1,
            "dc_min": -30000,
            "dc_max": -18000,
            "dc_step": 2000,
            "lookup_smooth_points": None,
            "live_plot": False,
            "spec_amp": 1000,
            "spec_len_us": 5.0,
        },
        "selected": [True, False, False, False, False, False, False, False],
    }]


def test_tls_step2_smoke_runner_selects_only_qubit_flux_sweep(monkeypatch):
    calls = []
    runner = SimpleNamespace(
        LIVE_PLOTS=True,
        SET_YOKO=True,
        BASELINE_DC_OFFSET=0,
        USE_RESONATOR_LOOKUP=True,
        RESONATOR_FIT_PARAMS=[1],
        RESET_MODE="active",
        P1_RESONATOR={"run": True},
        P2_QUBIT_SPEC_FULL={"run": False},
        P3_STEP_RESPONSE={"run_fit": True, "run_correct": True},
        P4_LONG_TIME={"run": True},
        P5_SS_CAL={"run": True},
        P6_3PT_T1={"run": True},
        P6_FULL_T1={"run": True},
    )
    runner.main = lambda: calls.append({
        "live_plots": runner.LIVE_PLOTS,
        "set_yoko": runner.SET_YOKO,
        "baseline": runner.BASELINE_DC_OFFSET,
        "lookup": runner.USE_RESONATOR_LOOKUP,
        "fit": runner.RESONATOR_FIT_PARAMS,
        "reset_mode": runner.RESET_MODE,
        "step2": dict(runner.P2_QUBIT_SPEC_FULL),
        "selected": [
            runner.P1_RESONATOR["run"],
            runner.P2_QUBIT_SPEC_FULL["run"],
            runner.P3_STEP_RESPONSE["run_fit"],
            runner.P3_STEP_RESPONSE["run_correct"],
            runner.P4_LONG_TIME["run"],
            runner.P5_SS_CAL["run"],
            runner.P6_3PT_T1["run"],
            runner.P6_FULL_T1["run"],
        ],
    })
    from WorkingProjects.TLS_Spectroscopy.Client_modules import Runners

    module_name = (
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSpectroscopy"
    )
    monkeypatch.setitem(sys.modules, module_name, runner)
    monkeypatch.setattr(Runners, "TLSSpectroscopy", runner, raising=False)
    path = Path(__file__).parents[1] / "production_tls_step2_smoke_q3.py"

    runpy.run_path(str(path), run_name="__main__")

    assert calls == [{
        "live_plots": False,
        "set_yoko": False,
        "baseline": -25790,
        "lookup": False,
        "fit": None,
        "reset_mode": "passive",
        "step2": {
            "run": True,
            "advanced_fit": False,
            "shots": 20,
            "relax_delay_us": 100.0,
            "spec_amp": 10000,
            "spec_len_us": 0.5,
            "freq_min": 4364.0,
            "freq_max": 4368.0,
            "freq_step": 0.5,
            "dc_min": -26000,
            "dc_max": -25250,
            "dc_step": 250,
            "live_plot": False,
        },
        "selected": [False, True, False, False, False, False, False, False],
    }]


def test_tls_step2_fit_runner_measures_current_negative_gain_branch(monkeypatch):
    calls = []
    runner = SimpleNamespace(
        LIVE_PLOTS=True,
        SET_YOKO=True,
        BASELINE_DC_OFFSET=0,
        USE_RESONATOR_LOOKUP=True,
        RESONATOR_FIT_PARAMS=[1],
        RESET_MODE="active",
        P1_RESONATOR={"run": True},
        P2_QUBIT_SPEC_FULL={"run": False},
        P3_STEP_RESPONSE={"run_fit": True, "run_correct": True},
        P4_LONG_TIME={"run": True},
        P5_SS_CAL={"run": True},
        P6_3PT_T1={"run": True},
        P6_FULL_T1={"run": True},
    )
    runner.main = lambda: calls.append({
        "live_plots": runner.LIVE_PLOTS,
        "set_yoko": runner.SET_YOKO,
        "baseline": runner.BASELINE_DC_OFFSET,
        "lookup": runner.USE_RESONATOR_LOOKUP,
        "fit": runner.RESONATOR_FIT_PARAMS,
        "reset_mode": runner.RESET_MODE,
        "step2": dict(runner.P2_QUBIT_SPEC_FULL),
        "selected": [
            runner.P1_RESONATOR["run"],
            runner.P2_QUBIT_SPEC_FULL["run"],
            runner.P3_STEP_RESPONSE["run_fit"],
            runner.P3_STEP_RESPONSE["run_correct"],
            runner.P4_LONG_TIME["run"],
            runner.P5_SS_CAL["run"],
            runner.P6_3PT_T1["run"],
            runner.P6_FULL_T1["run"],
        ],
    })
    from WorkingProjects.TLS_Spectroscopy.Client_modules import Runners

    module_name = (
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSpectroscopy"
    )
    monkeypatch.setitem(sys.modules, module_name, runner)
    monkeypatch.setattr(Runners, "TLSSpectroscopy", runner, raising=False)
    path = Path(__file__).parents[1] / "production_tls_step2_fit_q3.py"

    runpy.run_path(str(path), run_name="__main__")

    assert calls == [{
        "live_plots": False,
        "set_yoko": False,
        "baseline": -25790,
        "lookup": False,
        "fit": None,
        "reset_mode": "passive",
        "step2": {
            "run": True,
            "advanced_fit": True,
            "shots": 100,
            "relax_delay_us": 100.0,
            "spec_amp": 15000,
            "spec_len_us": 1.0,
            "freq_min": 4200.0,
            "freq_max": 4372.0,
            "freq_step": 1.0,
            "dc_min": -26000,
            "dc_max": -19500,
            "dc_step": 500,
            "live_plot": False,
        },
        "selected": [False, True, False, False, False, False, False, False],
    }]


def test_tls_step3a_smoke_runner_uses_measured_negative_gain_flux_fit(monkeypatch):
    calls = []
    runner = SimpleNamespace(
        LIVE_PLOTS=True,
        SET_YOKO=True,
        FLUX_FIT_PARAMS=None,
        BASELINE_DC_OFFSET=0,
        TARGET_DC_OFFSET=0,
        USE_RESONATOR_LOOKUP=True,
        RESONATOR_FIT_PARAMS=[1],
        RESET_MODE="active",
        P1_RESONATOR={"run": True},
        P2_QUBIT_SPEC_FULL={"run": True},
        P3_STEP_RESPONSE={"run_fit": False, "run_correct": True},
        P4_LONG_TIME={"run": True},
        P5_SS_CAL={"run": True},
        P6_3PT_T1={"run": True},
        P6_FULL_T1={"run": True},
    )
    runner.main = lambda: calls.append({
        "live_plots": runner.LIVE_PLOTS,
        "set_yoko": runner.SET_YOKO,
        "flux_fit": list(runner.FLUX_FIT_PARAMS),
        "baseline": runner.BASELINE_DC_OFFSET,
        "target": runner.TARGET_DC_OFFSET,
        "lookup": runner.USE_RESONATOR_LOOKUP,
        "resonator_fit": runner.RESONATOR_FIT_PARAMS,
        "reset_mode": runner.RESET_MODE,
        "step3": dict(runner.P3_STEP_RESPONSE),
        "selected": [
            runner.P1_RESONATOR["run"],
            runner.P2_QUBIT_SPEC_FULL["run"],
            runner.P3_STEP_RESPONSE["run_fit"],
            runner.P3_STEP_RESPONSE["run_correct"],
            runner.P4_LONG_TIME["run"],
            runner.P5_SS_CAL["run"],
            runner.P6_3PT_T1["run"],
            runner.P6_FULL_T1["run"],
        ],
    })
    from WorkingProjects.TLS_Spectroscopy.Client_modules import Runners

    module_name = (
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSpectroscopy"
    )
    monkeypatch.setitem(sys.modules, module_name, runner)
    monkeypatch.setattr(Runners, "TLSSpectroscopy", runner, raising=False)
    path = Path(__file__).parents[1] / "production_tls_step3a_smoke_q3.py"

    runpy.run_path(str(path), run_name="__main__")

    assert calls == [{
        "live_plots": False,
        "set_yoko": False,
        "flux_fit": [
            8.203384791028979,
            0.2902930003646722,
            8774.00218131707,
            -23058.31389817458,
            0.9831224825856887,
            -1.2183803188472806e-05,
        ],
        "baseline": -25790,
        "target": -20000,
        "lookup": False,
        "resonator_fit": None,
        "reset_mode": "passive",
        "step3": {
            "run_fit": True,
            "run_correct": False,
            "shots": 50,
            "spec_amp": 15000,
            "spec_len_us": 1.0,
            "freq_step": 1.0,
            "auto_center_frequency_window": True,
            "auto_freq_absolute_min_mhz": 4200.0,
            "auto_freq_absolute_max_mhz": 4372.0,
            "t_min_us": 1.0,
            "t_max_us": 501.0,
            "t_step_us": 10.0,
            "baseline_rearm_us": 100.0,
            "piecewise_min_multiplier": 0.5,
            "piecewise_max_multiplier": 1.5,
            "readout_after_park": False,
            "live_plot": False,
        },
        "selected": [False, False, True, False, False, False, False, False],
    }]


def test_tls_step3b_smoke_runner_applies_latest_correction_once(monkeypatch):
    calls = []
    runner = SimpleNamespace(
        LIVE_PLOTS=True,
        SET_YOKO=True,
        FLUX_FIT_PARAMS=None,
        BASELINE_DC_OFFSET=0,
        TARGET_DC_OFFSET=0,
        FLUX_TAIL_COMPENSATION_GAIN=0.75,
        STEP3B_GAIN_SWEEP=[0.5, 1.0],
        USE_RESONATOR_LOOKUP=True,
        RESONATOR_FIT_PARAMS=[1],
        RESET_MODE="active",
        P1_RESONATOR={"run": True},
        P2_QUBIT_SPEC_FULL={"run": True},
        P3_STEP_RESPONSE={"run_fit": True, "run_correct": False},
        P4_LONG_TIME={"run": True},
        P5_SS_CAL={"run": True},
        P6_3PT_T1={"run": True},
        P6_FULL_T1={"run": True},
    )
    runner.main = lambda: calls.append({
        "gain": runner.FLUX_TAIL_COMPENSATION_GAIN,
        "gain_sweep": runner.STEP3B_GAIN_SWEEP,
        "step3": dict(runner.P3_STEP_RESPONSE),
        "selected": [
            runner.P1_RESONATOR["run"],
            runner.P2_QUBIT_SPEC_FULL["run"],
            runner.P3_STEP_RESPONSE["run_fit"],
            runner.P3_STEP_RESPONSE["run_correct"],
            runner.P4_LONG_TIME["run"],
            runner.P5_SS_CAL["run"],
            runner.P6_3PT_T1["run"],
            runner.P6_FULL_T1["run"],
        ],
    })
    from WorkingProjects.TLS_Spectroscopy.Client_modules import Runners

    module_name = (
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSpectroscopy"
    )
    monkeypatch.setitem(sys.modules, module_name, runner)
    monkeypatch.setattr(Runners, "TLSSpectroscopy", runner, raising=False)
    path = Path(__file__).parents[1] / "production_tls_step3b_smoke_q3.py"

    runpy.run_path(str(path), run_name="__main__")

    assert calls == [{
        "gain": 0.75,
        "gain_sweep": None,
        "step3": {
            "run_fit": False,
            "run_correct": True,
            "shots": 50,
            "spec_amp": 15000,
            "spec_len_us": 1.0,
            "freq_step": 1.0,
            "auto_center_frequency_window": True,
            "auto_freq_absolute_min_mhz": 4200.0,
            "auto_freq_absolute_max_mhz": 4372.0,
            "t_min_us": 1.0,
            "t_max_us": 501.0,
            "t_step_us": 10.0,
            "baseline_rearm_us": 100.0,
            "piecewise_min_multiplier": 0.5,
            "piecewise_max_multiplier": 1.5,
            "readout_after_park": False,
            "live_plot": False,
        },
        "selected": [False, False, False, True, False, False, False, False],
    }]


def test_tls_3pt_smoke_combines_active_reset_with_validated_flux_compensation(monkeypatch):
    calls = []
    runner = SimpleNamespace(
        LIVE_PLOTS=True,
        RESET_MODE="passive",
        FLUX_FIT_PARAMS=None,
        BASELINE_DC_OFFSET=0,
        TARGET_DC_OFFSET=0,
        FLUX_TAIL_COMPENSATION_GAIN=0.1,
        P1_RESONATOR={"run": True},
        P2_QUBIT_SPEC_FULL={"run": True},
        P3_STEP_RESPONSE={"run_fit": True, "run_correct": True},
        P4_LONG_TIME={"run": True},
        P5_SS_CAL={"run": True},
        P6_3PT_T1={"run": False},
        P6_FULL_T1={"run": True},
    )
    runner.main = lambda: calls.append({
        "reset_mode": runner.RESET_MODE,
        "flux_fit_params": runner.FLUX_FIT_PARAMS,
        "baseline_dc_offset": runner.BASELINE_DC_OFFSET,
        "target_dc_offset": runner.TARGET_DC_OFFSET,
        "gain": runner.FLUX_TAIL_COMPENSATION_GAIN,
        "step6": dict(runner.P6_3PT_T1),
        "selected": [
            runner.P1_RESONATOR["run"],
            runner.P2_QUBIT_SPEC_FULL["run"],
            runner.P3_STEP_RESPONSE["run_fit"],
            runner.P3_STEP_RESPONSE["run_correct"],
            runner.P4_LONG_TIME["run"],
            runner.P5_SS_CAL["run"],
            runner.P6_3PT_T1["run"],
            runner.P6_FULL_T1["run"],
        ],
    })
    from WorkingProjects.TLS_Spectroscopy.Client_modules import Runners

    module_name = (
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSpectroscopy"
    )
    monkeypatch.setitem(sys.modules, module_name, runner)
    monkeypatch.setattr(Runners, "TLSSpectroscopy", runner, raising=False)
    path = Path(__file__).parents[1] / "production_tls_3pt_smoke_q3.py"

    runpy.run_path(str(path), run_name="__main__")

    assert calls == [{
        "reset_mode": "active",
        "flux_fit_params": [
            8.203384791028979,
            0.2902930003646722,
            8774.00218131707,
            -23058.31389817458,
            0.9831224825856887,
            -1.2183803188472806e-05,
        ],
        "baseline_dc_offset": -25790,
        "target_dc_offset": -20000,
        "gain": 0.75,
        "step6": {
            "run": True,
            "apply_flux_tail_compensation": True,
            "shots": 100,
            "dc_min": -20500,
            "dc_max": -19500,
            "dc_step": 500,
            "freq_step_mhz": None,
            "wall_clock_duration_min": None,
            "Ts_us": 70.0,
            "min_ref_contrast": 0.05,
            "max_plot_t1_multiple": 20.0,
        },
        "selected": [False, False, False, False, False, False, True, False],
    }]
