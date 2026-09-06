import csv
from dataclasses import replace
import json
import math

import numpy as np
import pytest

from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import (
    analysis,
    calibration,
    integration,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.analysis import (
    ReferenceAxis,
    append_records_csv,
    build_interleaved_schedule,
    diagnose_t1_flux_lifecycle,
    evaluate_inter_shot_recovery_sweep,
    evaluate_t1_flux_lifecycle,
    evaluate_t1_equivalence,
    fit_t1_decay,
    json_safe,
    summarize_post_readout_pi,
    summarize_records,
    wilson_interval,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.calibration import (
    CalibrationBundle,
    load_calibration,
    per_shot_reference_config,
    save_calibration,
    threshold_policy_metadata,
    validate_confident_calibration,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.classifier import (
    ClassifierCalibration,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import (
    payload_iq,
    runtime_bundle,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.records import (
    PayloadRecord,
    ShotRecord,
    TerminalStatus,
)


CAL = ClassifierCalibration(
    schema_version=1,
    context="payload",
    theta_rad=0.0,
    shift=0,
    c_int=1,
    s_int=0,
    ground_threshold=-10,
    excited_threshold=10,
    max_abs_raw=100,
    holdout={"ground_median": -100, "excited_median": 100},
)


def test_reference_axis_recovers_mixture_population_from_mean_iq():
    axis = ReferenceAxis.from_centers(10, -5, 110, 45)
    i = np.asarray([10, 110, 110, 10], dtype=float)
    q = np.asarray([-5, 45, 45, -5], dtype=float)

    assert axis.population(i, q) == pytest.approx([0, 1, 1, 0])
    assert axis.mean_population(i, q) == pytest.approx(0.5)


def test_production_reference_calibration_disables_persistent_hard_park():
    cfg = per_shot_reference_config({
        "opx_persistent_park": True,
        "opx_hard_flux_steps": True,
        "opx_reference_flux_cycle": True,
        "opx_inter_shot_delay_us": 10.0,
    })

    assert cfg["opx_persistent_park"] is False
    assert cfg["opx_hard_flux_steps"] is False
    assert cfg["opx_reference_flux_cycle"] is False
    assert cfg["opx_inter_shot_delay_us"] == pytest.approx(400.0)


def test_t1_fit_recovers_a_known_exponential_decay():
    times = np.logspace(0, np.log10(750.0), 21)
    populations = 0.035 + 0.81 * np.exp(-times / 150.0)

    fit = fit_t1_decay(times, populations, shots=np.full(times.size, 500))

    assert fit["decaying"] is True
    assert fit["tau_us"] == pytest.approx(150.0, rel=1e-3)
    assert fit["P0"] == pytest.approx(0.035, abs=1e-4)
    assert fit["P1"] == pytest.approx(0.845, abs=1e-4)


def test_spectroscopy_fit_recovers_lorentzian_center_and_width():
    frequencies = np.linspace(4347.0, 4387.0, 161)
    center = 4362.75
    width = 2.4
    populations = 0.08 + 0.72 / (1.0 + 4.0 * ((frequencies - center) / width) ** 2)

    fit = analysis.fit_spectroscopy_peak(frequencies, populations)

    assert fit["center_mhz"] == pytest.approx(center, abs=0.02)
    assert fit["fwhm_mhz"] == pytest.approx(width, abs=0.03)
    assert fit["contrast"] == pytest.approx(0.72, abs=0.01)
    assert fit["boundary_peak"] is False


def test_flux_cycle_spectroscopy_identifies_correctable_periodic_detuning():
    fits = {
        "passive_1000": {"center_mhz": 4367.2, "fwhm_mhz": 2.0, "contrast": 0.70},
        "no_reset_25": {"center_mhz": 4361.1, "fwhm_mhz": 2.3, "contrast": 0.62},
        "active_25": {"center_mhz": 4361.0, "fwhm_mhz": 2.4, "contrast": 0.60},
        "active_100": {"center_mhz": 4367.0, "fwhm_mhz": 2.1, "contrast": 0.68},
    }

    result = analysis.evaluate_flux_cycle_spectroscopy(fits)

    assert result["diagnosis"] == "correctable_flux_cycle_detuning"
    assert result["recommended_payload_frequency_mhz"] == pytest.approx(4361.0)
    assert result["active_25_center_shift_mhz"] == pytest.approx(-6.2)


def test_flux_cycle_spectroscopy_identifies_short_cycle_broadening():
    fits = {
        "passive_1000": {"center_mhz": 4367.2, "fwhm_mhz": 2.0, "contrast": 0.70},
        "no_reset_25": {"center_mhz": 4365.0, "fwhm_mhz": 6.0, "contrast": 0.20},
        "active_25": {"center_mhz": 4364.8, "fwhm_mhz": 6.5, "contrast": 0.18},
        "active_100": {"center_mhz": 4367.0, "fwhm_mhz": 2.1, "contrast": 0.68},
    }

    result = analysis.evaluate_flux_cycle_spectroscopy(fits)

    assert result["diagnosis"] == "short_cycle_broadening_or_heating"
    assert result["recommended_payload_frequency_mhz"] is None


def test_flux_cycle_spectroscopy_rejects_a_peak_at_the_sweep_boundary():
    fits = {
        "passive_1000": {"center_mhz": 4367.2, "fwhm_mhz": 2.0, "contrast": 0.70},
        "no_reset_25": {"center_mhz": 4347.2, "fwhm_mhz": 2.3, "contrast": 0.62},
        "active_25": {
            "center_mhz": 4347.2,
            "fwhm_mhz": 2.4,
            "contrast": 0.60,
            "boundary_peak": True,
        },
        "active_100": {"center_mhz": 4367.0, "fwhm_mhz": 2.1, "contrast": 0.68},
    }

    result = analysis.evaluate_flux_cycle_spectroscopy(fits)

    assert result["diagnosis"] == "sweep_boundary"
    assert result["recommended_payload_frequency_mhz"] is None


def test_flux_cycle_runner_maps_reset_and_recovery_conditions():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import (
        flux_cycle_spectroscopy_q3 as runner,
    )

    assert runner._method_config("passive_1000") == ("none", 1000.0)
    assert runner._method_config("no_reset_25") == ("none", 25.0)
    assert runner._method_config("active_25") == ("opx_unbounded", 25.0)
    assert runner._method_config("active_100") == ("opx_unbounded", 100.0)
    frequencies = np.asarray([1.0, 2.0, 3.0])
    assert runner._ordered_frequency_axis(frequencies, 0).tolist() == [1.0, 2.0, 3.0]
    assert runner._ordered_frequency_axis(frequencies, 1).tolist() == [3.0, 2.0, 1.0]


def test_flux_cycle_rabi_selects_restored_active_25_gain():
    result = analysis.evaluate_flux_cycle_rabi(
        [0, 5000, 10000, 15000, 20000],
        {
            "passive_1000": [0.02, 0.35, 0.78, 0.42, 0.04],
            "no_reset_25": [0.03, 0.31, 0.74, 0.50, 0.06],
            "active_25": [0.02, 0.22, 0.58, 0.73, 0.30],
            "active_100": [0.03, 0.34, 0.75, 0.45, 0.05],
        },
    )

    assert result["status"] == "pass"
    assert result["diagnosis"] == "gain_retune_restores_25us"
    assert result["recommended_active_25_gain"] == 15000
    assert result["metrics"]["active_25"]["peak_population"] == pytest.approx(0.73)


def test_flux_cycle_rabi_identifies_active_reset_suppression():
    result = analysis.evaluate_flux_cycle_rabi(
        [0, 5000, 10000, 15000, 20000],
        {
            "passive_1000": [0.02, 0.35, 0.78, 0.42, 0.04],
            "no_reset_25": [0.03, 0.31, 0.74, 0.50, 0.06],
            "active_25": [0.03, 0.18, 0.49, 0.51, 0.28],
            "active_100": [0.03, 0.34, 0.75, 0.45, 0.05],
        },
    )

    assert result["status"] == "diagnostic"
    assert result["diagnosis"] == "active_reset_suppression"
    assert result["recommended_active_25_gain"] is None


def test_flux_cycle_rabi_runner_maps_exact_lifecycle_conditions():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import (
        flux_cycle_rabi_q3 as runner,
    )

    assert runner._method_config("passive_1000") == ("none", 1000.0, "passive")
    assert runner._method_config("no_reset_25") == ("none", 25.0, "active")
    assert runner._method_config("active_25") == (
        "opx_unbounded", 25.0, "active"
    )
    assert runner._method_config("active_100") == (
        "opx_unbounded", 100.0, "active_100"
    )


def test_t1_frequency_retune_selects_payload_only_when_it_restores_equivalence():
    fits = {
        "passive_1000": {"P0": 0.05, "P1": 0.80, "tau_us": 100.0, "decaying": True},
        "active_100": {"P0": 0.06, "P1": 0.78, "tau_us": 103.0, "decaying": True},
        "active_25_default": {"P0": 0.05, "P1": 0.30, "tau_us": 105.0, "decaying": True},
        "active_25_payload": {"P0": 0.06, "P1": 0.76, "tau_us": 107.0, "decaying": True},
        "active_25_both": {"P0": 0.06, "P1": 0.48, "tau_us": 106.0, "decaying": True},
    }

    result = analysis.evaluate_t1_frequency_retune(fits)

    assert result["status"] == "pass"
    assert result["diagnosis"] == "payload_retune_restores_25us"
    assert result["selected_method"] == "active_25_payload"


def test_t1_frequency_retune_runner_keeps_payload_and_reset_options_separate():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import (
        t1_flux_ramp_frequency_retune_q3 as runner,
    )

    runner.BASELINE_FREQUENCY_MHZ = 4367.2
    runner.ACTIVE25_FREQUENCY_MHZ = 4361.0

    assert runner._method_config("passive_1000") == ("none", 1000.0)
    assert runner._method_config("active_25_payload") == ("opx_unbounded", 25.0)
    assert runner._method_overrides("active_25_payload") == {
        "qubit_pi_freq": 4361.0,
        "reset_pi_freq": 4367.2,
    }
    assert runner._method_overrides("active_25_both") == {
        "qubit_pi_freq": 4361.0,
        "reset_pi_freq": 4361.0,
    }


def test_t1_frequency_retune_loader_uses_measured_method_centers(tmp_path):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import (
        t1_flux_ramp_frequency_retune_q3 as runner,
    )

    path = tmp_path / "result.json"
    path.write_text(json.dumps({
        "fits": {
            "passive_1000": {
                "center_mhz": 4367.2,
                "boundary_peak": False,
            },
            "active_25": {
                "center_mhz": 4366.55,
                "boundary_peak": False,
            },
        },
        "evaluation": {
            "active_100_control_passed": True,
            "short_shape_healthy": True,
        },
    }))

    assert runner._load_frequencies(path) == pytest.approx((4367.2, 4366.55))


def test_t1_frequency_retune_finds_latest_completed_diagnostic(tmp_path, monkeypatch):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import (
        t1_flux_ramp_frequency_retune_q3 as runner,
    )

    monkeypatch.setattr(runner, "DIAGNOSTIC_RESULT_PATH", None)
    older = (
        tmp_path / "q3" / "q3_2026_09_05"
        / "q3_10_00_00_active_reset_OPX_flux_cycle_spectroscopy" / "result.json"
    )
    newer = (
        tmp_path / "q3" / "q3_2026_09_05"
        / "q3_11_00_00_active_reset_OPX_flux_cycle_spectroscopy" / "result.json"
    )
    older.parent.mkdir(parents=True)
    newer.parent.mkdir(parents=True)
    older.write_text("{}")
    newer.write_text("{}")
    older.touch()
    newer.touch()
    older.chmod(0o600)
    newer.chmod(0o600)
    import os
    os.utime(older, (1.0, 1.0))
    os.utime(newer, (2.0, 2.0))

    assert runner._latest_result(tmp_path) == newer


def test_frequency_sweep_acquisition_preserves_point_order_and_reset_frequency(monkeypatch):
    bundle = CalibrationBundle(
        schema_version=1,
        payload=CAL,
        loop=CAL,
        reference_axis=ReferenceAxis.from_centers(0, 0, 100, 0),
        metadata={},
    )
    created = []

    class FakeProgram:
        def __init__(self, soccfg, cfg, payload_calibration, loop_calibration):
            self.cfg = dict(cfg)
            created.append(self)

        def us2cycles(self, value, ro_ch=None):
            return 10

    records = [
        PayloadRecord(10, -10), PayloadRecord(20, -20), PayloadRecord(30, -30),
        PayloadRecord(11, -11), PayloadRecord(21, -21), PayloadRecord(31, -31),
    ]
    monkeypatch.setattr(integration, "OPXResetPulseSweepProgram", FakeProgram)
    monkeypatch.setattr(integration, "dmem_words_from_soccfg", lambda soccfg: 4096)
    monkeypatch.setattr(integration, "run_dmem_block", lambda *args, **kwargs: records)
    cfg = {
        "opx_reset_calibration": bundle.to_dict(),
        "shots": 2,
        "read_length": 1.0,
        "ro_chs": [0],
        "qubit_pi_freq": 4367.25,
    }

    i_values, q_values, telemetry = integration.acquire_frequency_sweep_iq(
        None,
        {},
        cfg,
        frequencies_mhz=[4350.0, 4350.5, 4351.0],
        gain=11100,
        pulses=1,
        shots=2,
        pulse_placement="park_after_excursion",
        do_excursion=True,
        excursion_gain=-20000,
        flux_hold_us=750.0,
        park_recovery_us=1000.0,
    )

    assert i_values.tolist() == [[1.0, 1.1], [2.0, 2.1], [3.0, 3.1]]
    assert q_values.tolist() == [[-1.0, -1.1], [-2.0, -2.1], [-3.0, -3.1]]
    assert telemetry["points"] == 3
    assert created[0].cfg["opx_payload_sweep_kind"] == "frequency"
    assert created[0].cfg["opx_payload_frequency_start_mhz"] == pytest.approx(4350.0)
    assert created[0].cfg["opx_payload_frequency_step_mhz"] == pytest.approx(0.5)
    assert created[0].cfg["opx_payload_fixed_gain"] == 11100
    assert created[0].cfg["qubit_pi_freq"] == pytest.approx(4367.25)
    assert created[0].cfg["opx_payload_pulse_placement"] == "park_after_excursion"
    assert created[0].cfg["opx_payload_excursion_gain"] == pytest.approx(-20000)
    assert created[0].cfg["opx_payload_flux_hold_us"] == pytest.approx(750.0)
    assert created[0].cfg["opx_payload_park_recovery_us"] == pytest.approx(1000.0)


def test_qua_order_t1_uses_recovery_matched_park_frequencies(tmp_path):
    result = tmp_path / "result.json"
    result.write_text(json.dumps({
        "fits": {
            "history_1_recovery_10": {
                "center_mhz": 4366.36,
                "center_err_mhz": 0.04,
                "contrast": 1.2,
                "boundary_peak": False,
            },
            "history_750_recovery_10": {
                "center_mhz": 4366.42,
                "center_err_mhz": 0.04,
                "contrast": 1.3,
                "boundary_peak": False,
            },
            "history_1_recovery_1000": {
                "center_mhz": 4366.12,
                "center_err_mhz": 0.04,
                "contrast": 1.1,
                "boundary_peak": False,
            },
            "history_750_recovery_1000": {
                "center_mhz": 4365.92,
                "center_err_mhz": 0.05,
                "contrast": 0.8,
                "boundary_peak": False,
            },
        }
    }))

    frequencies = analysis.load_park_history_method_frequencies(result)

    assert frequencies == pytest.approx({
        "opx_unbounded": 4366.39,
        "passive": 4366.02,
    })


def test_t1_sweep_acquisition_preserves_qua_shot_major_order(monkeypatch):
    bundle = CalibrationBundle(
        schema_version=1,
        payload=CAL,
        loop=CAL,
        reference_axis=ReferenceAxis.from_centers(0, 0, 100, 0),
        metadata={},
    )
    created = []

    class FakeProgram:
        def __init__(self, soccfg, cfg, payload_calibration, loop_calibration):
            self.cfg = dict(cfg)
            self.reps = int(cfg["opx_t1_shots"]) * len(cfg["opx_t1_delays_us"])
            created.append(self)

        def us2cycles(self, value, ro_ch=None):
            return 10

    records = [
        PayloadRecord(10, -10), PayloadRecord(20, -20), PayloadRecord(30, -30),
        PayloadRecord(11, -11), PayloadRecord(21, -21), PayloadRecord(31, -31),
    ]
    monkeypatch.setattr(integration, "OPXResetT1SweepProgram", FakeProgram)
    monkeypatch.setattr(integration, "dmem_words_from_soccfg", lambda soccfg: 4096)
    monkeypatch.setattr(integration, "run_dmem_block", lambda *args, **kwargs: records)
    cfg = {
        "opx_reset_calibration": bundle.to_dict(),
        "shots": 2,
        "read_length": 1.0,
        "ro_chs": [0],
    }

    i_values, q_values, telemetry = integration.acquire_t1_sweep_iq(
        None,
        {},
        cfg,
        delays_us=[1.0, 10.0, 100.0],
        shots=2,
        reset_scheme="opx_unbounded",
    )

    assert i_values.tolist() == [[1.0, 1.1], [2.0, 2.1], [3.0, 3.1]]
    assert q_values.tolist() == [[-1.0, -1.1], [-2.0, -2.1], [-3.0, -3.1]]
    assert telemetry == {
        "shots_per_point": 2,
        "points": 3,
        "blocks": 1,
        "records": 6,
        "order": "shot_major",
        "read_length_cycles": 10,
    }
    assert created[0].cfg["opx_t1_delays_us"] == [1.0, 10.0, 100.0]
    assert created[0].cfg["opx_reset_scheme"] == "opx_unbounded"


def test_timing_matched_calibration_chunks_dmem_without_changing_park_mode(monkeypatch):
    created = []

    class FakeProgram:
        def __init__(self, soccfg, cfg):
            self.cfg = dict(cfg)
            self.reps = int(cfg["reps"])
            created.append(self)

    monkeypatch.setattr(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.programs."
        "TimingMatchedReferenceDMemProgram",
        FakeProgram,
    )
    monkeypatch.setattr(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.acquisition."
        "run_dmem_block",
        lambda soc, program, timeout_s: [
            PayloadRecord(index, -index) for index in range(program.reps)
        ],
    )

    result = calibration._capture_context(
        None,
        {"tprocs": [{"dmem_size": 42}]},
        {
            "opx_record_base": 32,
            "opx_persistent_park": True,
            "opx_hard_flux_steps": True,
            "opx_inter_shot_delay_us": 2.8,
            "read_length": 5.0,
        },
        context="payload",
        shots=7,
    )

    assert [program.reps for program in created] == [5, 2, 5, 2]
    assert all(program.cfg["opx_persistent_park"] for program in created)
    assert all(program.cfg["opx_hard_flux_steps"] for program in created)
    assert result["ground"]["i"].tolist() == [0, 1, 2, 3, 4, 0, 1]
    assert result["excited"]["q"].tolist() == [0, -1, -2, -3, -4, 0, -1]


def test_t1_equivalence_requires_matching_decay_and_population_endpoints():
    passive = {"P0": 0.05, "P1": 0.82, "tau_us": 100.0, "decaying": True}
    active = {"P0": 0.06, "P1": 0.42, "tau_us": 105.0, "decaying": True}

    result = evaluate_t1_equivalence(
        passive,
        active,
        max_relative_tau_difference=0.20,
        max_abs_p0_difference=0.12,
        max_abs_p1_difference=0.12,
    )

    assert result["status"] == "fail"
    assert result["tau_passed"] is True
    assert result["P0_passed"] is True
    assert result["P1_passed"] is False
    assert result["failed_checks"] == ["P1"]


def test_t1_equivalence_passes_matching_curves():
    passive = {"P0": 0.05, "P1": 0.82, "tau_us": 100.0, "decaying": True}
    active = {"P0": 0.07, "P1": 0.76, "tau_us": 112.0, "decaying": True}

    result = evaluate_t1_equivalence(
        passive,
        active,
        max_relative_tau_difference=0.20,
        max_abs_p0_difference=0.12,
        max_abs_p1_difference=0.12,
    )

    assert result["status"] == "pass"
    assert result["failed_checks"] == []


def test_inter_shot_recovery_sweep_selects_first_population_and_drift_match():
    result = evaluate_inter_shot_recovery_sweep(
        passive_excited_fraction=0.80,
        rows=[
            {"active_relax_us": 50, "excited_fraction": 0.48, "shot_drift": 0.28},
            {"active_relax_us": 100, "excited_fraction": 0.63, "shot_drift": 0.18},
            {"active_relax_us": 200, "excited_fraction": 0.70, "shot_drift": 0.11},
            {"active_relax_us": 400, "excited_fraction": 0.74, "shot_drift": 0.07},
            {"active_relax_us": 800, "excited_fraction": 0.76, "shot_drift": 0.04},
        ],
        max_abs_population_difference=0.12,
        max_abs_shot_drift=0.10,
    )

    assert result["status"] == "pass"
    assert result["selected_active_relax_us"] == pytest.approx(400.0)
    assert [row["passed"] for row in result["rows"]] == [
        False,
        False,
        False,
        True,
        True,
    ]


def test_inter_shot_recovery_sweep_fails_closed_when_no_delay_matches():
    result = evaluate_inter_shot_recovery_sweep(
        passive_excited_fraction=0.80,
        rows=[
            {"active_relax_us": 50, "excited_fraction": 0.48, "shot_drift": 0.28},
            {"active_relax_us": 100, "excited_fraction": 0.63, "shot_drift": 0.18},
        ],
        max_abs_population_difference=0.12,
        max_abs_shot_drift=0.10,
    )

    assert result["status"] == "fail"
    assert result["selected_active_relax_us"] is None


def test_inter_shot_recovery_sweep_requires_every_round_to_match_population():
    result = evaluate_inter_shot_recovery_sweep(
        passive_excited_fraction=0.76,
        rows=[
            {
                "active_relax_us": 100,
                "excited_fraction": 0.678,
                "shot_drift": 0.05,
                "round_population_differences": [-0.04, -0.124],
            },
            {
                "active_relax_us": 200,
                "excited_fraction": 0.728,
                "shot_drift": 0.09,
                "round_population_differences": [-0.04, -0.024],
            },
        ],
        max_abs_population_difference=0.12,
        max_abs_shot_drift=0.10,
    )

    assert result["selected_active_relax_us"] == pytest.approx(200.0)
    assert result["rows"][0]["population_passed"] is False
    assert result["rows"][0]["worst_abs_population_difference"] == pytest.approx(0.124)


def test_json_safe_converts_nested_numpy_arrays_and_nonfinite_values():
    converted = json_safe({"delays": np.asarray([1.0, 2.0]), "bad": np.float64(np.nan)})

    assert converted == {"delays": [1.0, 2.0], "bad": None}


def test_wilson_interval_contains_observed_fraction_and_handles_zero_shots():
    low, high = wilson_interval(10, 100)
    assert low < 0.1 < high
    assert all(math.isnan(value) for value in wilson_interval(0, 0))


def test_summary_includes_timeouts_in_unconditional_residual():
    axis = ReferenceAxis.from_centers(0, 0, 100, 0)
    records = [
        ShotRecord(1, 100, 1, 1, TerminalStatus.CONFIRMED_GROUND, 0, 0, -100),
        ShotRecord(1, 100, 8, 8, TerminalStatus.MAX_ITERATIONS_REACHED, 100, 0, 100),
    ]

    summary = summarize_records(records, axis, CAL)

    assert summary["shots"] == 2
    assert summary["timeout_fraction"] == 0.5
    assert summary["verification_excited_fraction"] == 0.5
    assert summary["verification_population"] == pytest.approx(0.5)
    assert summary["max_reset_attempts"] == 8
    assert summary["p99_reset_attempts"] == pytest.approx(7.93)


def test_calibration_bundle_round_trips_through_json(tmp_path):
    bundle = CalibrationBundle(
        schema_version=1,
        payload=CAL,
        loop=CAL,
        reference_axis=ReferenceAxis.from_centers(0, 1, 10, 11),
        metadata={"qick_version": "0.2.133", "qubit": "q3"},
    )
    path = tmp_path / "calibration.json"

    save_calibration(path, bundle)

    assert load_calibration(path) == bundle


def test_calibration_save_sanitizes_numpy_metadata(tmp_path):
    bundle = CalibrationBundle(
        schema_version=1,
        payload=CAL,
        loop=CAL,
        reference_axis=ReferenceAxis.from_centers(0, 1, 10, 11),
        metadata={"delays_us": np.asarray([1.0, 2.0]), "missing": np.float64(np.nan)},
    )
    path = tmp_path / "calibration_numpy.json"

    save_calibration(path, bundle)

    loaded = load_calibration(path)
    assert loaded.metadata == {"delays_us": [1.0, 2.0], "missing": None}


def test_runtime_bundle_accepts_serialized_calibration_and_rejects_missing_config():
    bundle = CalibrationBundle(
        schema_version=1,
        payload=CAL,
        loop=CAL,
        reference_axis=ReferenceAxis.from_centers(0, 1, 10, 11),
        metadata={},
    )

    assert runtime_bundle({"opx_reset_calibration": bundle.to_dict()}) == bundle
    with pytest.raises(ValueError, match="opx_reset_calibration"):
        runtime_bundle({})


def test_payload_iq_returns_normalized_main_readout_from_t1_records():
    records = [
        ShotRecord(1, 100, 3, 2, TerminalStatus.CONFIRMED_GROUND, 120, -60, -100),
        ShotRecord(0, -100, 0, 0, TerminalStatus.NO_RESET, -40, 80, -100),
    ]

    i_values, q_values = payload_iq(records, read_length_cycles=20)

    assert i_values == pytest.approx([6.0, -2.0])
    assert q_values == pytest.approx([-3.0, 4.0])


def test_payload_classifier_uses_timing_matched_raw_threshold():
    bundle = CalibrationBundle(
        schema_version=1,
        payload=CAL,
        loop=CAL,
        reference_axis=ReferenceAxis.from_centers(0, 0, 100, 0),
        metadata={},
    )
    cfg = {"opx_reset_calibration": bundle.to_dict()}

    classified = integration.classify_payload_iq(
        cfg,
        i_values=np.asarray([[-0.5, 0.5, 0.55]]),
        q_values=np.zeros((1, 3)),
        read_length_cycles=20,
    )

    assert classified.tolist() == [[0, 0, 1]]


def test_three_point_acquisition_preserves_qua_shot_dc_reference_order(monkeypatch):
    captured = []

    class Program:
        record_words = 2

        def __init__(self, soccfg, cfg, payload, loop):
            self.soccfg = soccfg
            self.cfg = dict(cfg)
            self.record_base = 32
            self.done_addr = 1
            self.reps = (
                int(cfg["opx_t1_3pt_shots"])
                * len(cfg["opx_t1_3pt_dc_gains"])
                * 3
            )
            captured.append(self.cfg)

        def us2cycles(self, value, ro_ch=None):
            return 10

    next_value = iter(range(10_000))

    def run(soc, program, **kwargs):
        return [
            PayloadRecord(next(next_value), 0)
            for _ in range(program.reps)
        ]

    monkeypatch.setattr(integration, "OPXResetT13PointProgram", Program)
    monkeypatch.setattr(integration, "run_dmem_block", run)
    monkeypatch.setattr(
        integration,
        "runtime_bundle",
        lambda cfg: type("Bundle", (), {"payload": CAL, "loop": CAL})(),
    )

    i_values, q_values, telemetry = integration.acquire_t1_3pt_iq(
        object(),
        {"tprocs": [{"dmem_size": 64}]},
        {
            "shots": 3,
            "read_length": 5.0,
            "ro_chs": [0],
            "opx_record_base": 32,
        },
        dc_gains=[1000, 1100],
        wait_us=70.0,
    )

    assert len(captured) == 2
    assert [cfg["opx_t1_3pt_shots"] for cfg in captured] == [2, 1]
    assert i_values.shape == (3, 2, 3)
    assert q_values.shape == (3, 2, 3)
    assert i_values[:, :, 0].tolist() == [[0.0, 0.3], [0.1, 0.4], [0.2, 0.5]]
    assert telemetry["order"] == "shot_dc_P0_P1_Ps"
    assert telemetry["shots_per_dc"] == 3
    assert telemetry["dc_points"] == 2


def test_tls_memory_acquisition_preserves_shot_sequence_order(monkeypatch):
    bundle = CalibrationBundle(
        schema_version=1,
        payload=CAL,
        loop=CAL,
        reference_axis=ReferenceAxis.from_centers(0, 0, 100, 0),
        metadata={},
    )
    created = []

    class Program:
        def __init__(self, soccfg, cfg, payload_calibration, loop_calibration):
            self.cfg = dict(cfg)
            self.reps = (
                int(cfg["opx_memory_shots"])
                * len(cfg["opx_memory_sequences"])
            )
            created.append(self)

        def us2cycles(self, value, ro_ch=None):
            return 10

    def run(soc, program, **kwargs):
        sequences = program.cfg["opx_memory_sequences"]
        return [
            PayloadRecord(100 * sequence_index + shot, -shot)
            for shot in range(program.cfg["opx_memory_shots"])
            for sequence_index in range(len(sequences))
        ]

    monkeypatch.setattr(integration, "OPXResetTLSMemoryProgram", Program)
    monkeypatch.setattr(integration, "run_dmem_block", run)
    monkeypatch.setattr(integration, "dmem_words_from_soccfg", lambda soccfg: 4096)
    cfg = {
        "opx_reset_calibration": bundle.to_dict(),
        "shots": 3,
        "read_length": 5.0,
        "ro_chs": [0],
        "opx_record_base": 32,
    }

    i_values, q_values, telemetry = integration.acquire_tls_memory_iq(
        object(),
        {},
        cfg,
        sequences=("single", "double", "ground_double"),
        interaction_us=4.0,
        storage_us=12.0,
        ff_gain=-20000,
        shots=3,
        warmup_shots=128,
    )

    assert len(created) == 1
    assert i_values.shape == (3, 3)
    assert i_values.tolist() == [
        [0.0, 0.1, 0.2],
        [10.0, 10.1, 10.2],
        [20.0, 20.1, 20.2],
    ]
    assert q_values.tolist() == [
        [0.0, -0.1, -0.2],
        [0.0, -0.1, -0.2],
        [0.0, -0.1, -0.2],
    ]
    assert telemetry == {
        "shots_per_sequence": 3,
        "sequences": ["single", "double", "ground_double"],
        "blocks": 1,
        "records": 9,
        "order": "shot_sequence",
        "warmup_shots": 128,
        "read_length_cycles": 10,
    }
    assert created[0].cfg["opx_memory_warmup_shots"] == 128

def test_production_opx_mode_skips_legacy_single_shot_calibration():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments import (
        mCoherence,
    )

    assert mCoherence.needs_standalone_ss_calibration("passive") is True
    assert mCoherence.needs_standalone_ss_calibration("opx_unbounded") is False


def test_loading_missing_calibration_fails_closed(tmp_path):
    with pytest.raises(FileNotFoundError, match="calibration"):
        load_calibration(tmp_path / "missing.json")


def test_calibration_rejects_a_loop_classifier_with_no_confident_states():
    payload = replace(CAL, holdout={"ground_accept": 0.4, "excited_fire": 0.5})
    loop = replace(
        CAL,
        context="loop",
        holdout={"ground_accept": 0.07, "excited_fire": 0.03},
    )
    bundle = CalibrationBundle(
        schema_version=1,
        payload=payload,
        loop=loop,
        reference_axis=ReferenceAxis.from_centers(0, 0, 100, 0),
        metadata={},
    )

    with pytest.raises(ValueError, match="confident.*loop"):
        validate_confident_calibration(bundle, min_confident_fraction=0.2)


def test_qua_calibration_metadata_does_not_claim_tail_error_limits():
    metadata = threshold_policy_metadata(
        false_ground_limit=0.01,
        false_pi_limit=0.01,
        ground_confidence_fidelity=0.7,
        qua_threshold_steps=100,
    )

    assert metadata == {
        "threshold_policy": "qua_fidelity",
        "ground_confidence_fidelity": 0.7,
        "qua_threshold_steps": 100,
    }


def test_incremental_csv_has_one_row_per_shot_and_preserves_method(tmp_path):
    axis = ReferenceAxis.from_centers(0, 0, 100, 0)
    records = [
        ShotRecord(0, -100, 0, 0, TerminalStatus.CONFIRMED_GROUND, 0, 0, -100),
        ShotRecord(0, -100, 1, 0, TerminalStatus.CONFIRMED_GROUND, 0, 0, -100),
    ]
    path = tmp_path / "shots.csv"

    append_records_csv(path, records, axis=axis, assignment=CAL, method="opx", block=3)
    append_records_csv(path, records[:1], axis=axis, assignment=CAL, method="none", block=4)

    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 3
    assert [row["method"] for row in rows] == ["opx", "opx", "none"]
    assert [int(row["block"]) for row in rows] == [3, 3, 4]


def test_interleaved_schedule_contains_every_condition_once_per_block():
    schedule = build_interleaved_schedule(
        methods=("none", "opx", "current"), blocks=3, seed=7
    )

    assert len(schedule) == 18
    for block in range(3):
        conditions = {(method, preparation) for b, method, preparation in schedule if b == block}
        assert conditions == {
            (method, preparation)
            for method in ("none", "opx", "current")
            for preparation in (0, 1)
        }


def test_post_readout_pi_summary_selects_the_earliest_working_delay():
    summary = summarize_post_readout_pi(
        pre_pi_delay_us=[2.0, 4.0, 10.0],
        read_delay_us=2.0,
        first_ground_population=[0.02, 0.01, 0.00],
        first_pi_population=[0.03, 0.02, 0.01],
        second_ground_population=[0.05, 0.04, 0.03],
        second_pi_population=[0.20, 0.72, 0.90],
        min_transfer_contrast=0.5,
        max_first_preparation_delta=0.2,
        min_second_pi_population=0.5,
        max_abs_second_ground_population=0.3,
    )

    assert summary["selected_pre_pi_delay_us"] == pytest.approx(4.0)
    assert [row["pre_pi_delay_us"] for row in summary["rows"]] == [2.0, 4.0, 10.0]
    assert [row["passed"] for row in summary["rows"]] == [False, True, True]


def test_post_readout_pi_summary_rejects_delay_shorter_than_read_wait():
    with pytest.raises(ValueError, match="at least the read delay"):
        summarize_post_readout_pi(
            pre_pi_delay_us=[1.0, 2.0],
            read_delay_us=2.0,
            first_ground_population=[0.0, 0.0],
            first_pi_population=[0.0, 0.0],
            second_ground_population=[0.0, 0.0],
            second_pi_population=[0.0, 1.0],
            min_transfer_contrast=0.5,
            max_first_preparation_delta=0.2,
            min_second_pi_population=0.5,
            max_abs_second_ground_population=0.3,
        )


def test_feedback_delay_sweep_selects_shortest_delay_passing_both_preparations():
    rows = [
        {
            "feedback_syncdelay_us": 16.0,
            "preparation": 1,
            "timeout_fraction": 0.006,
            "verification_excited_fraction": 0.07,
        },
        {
            "feedback_syncdelay_us": 8.0,
            "preparation": 0,
            "timeout_fraction": 0.008,
            "verification_excited_fraction": 0.05,
        },
        {
            "feedback_syncdelay_us": 12.0,
            "preparation": 1,
            "timeout_fraction": 0.009,
            "verification_excited_fraction": 0.08,
        },
        {
            "feedback_syncdelay_us": 16.0,
            "preparation": 0,
            "timeout_fraction": 0.004,
            "verification_excited_fraction": 0.05,
        },
        {
            "feedback_syncdelay_us": 8.0,
            "preparation": 1,
            "timeout_fraction": 0.03,
            "verification_excited_fraction": 0.09,
        },
        {
            "feedback_syncdelay_us": 12.0,
            "preparation": 0,
            "timeout_fraction": 0.005,
            "verification_excited_fraction": 0.05,
        },
    ]

    result = analysis.evaluate_feedback_delay_sweep(
        rows,
        max_timeout_fraction=0.01,
        max_verification_excited_fraction=0.1,
    )

    assert result["status"] == "pass"
    assert result["selected_feedback_syncdelay_us"] == pytest.approx(12.0)
    assert [row["passed"] for row in result["delays"]] == [False, True, True]


def test_feedback_delay_sweep_fails_closed_for_incomplete_or_nonpassing_delays():
    rows = [
        {
            "feedback_syncdelay_us": 8.0,
            "preparation": 0,
            "timeout_fraction": 0.0,
            "verification_excited_fraction": 0.04,
        },
        {
            "feedback_syncdelay_us": 12.0,
            "preparation": 0,
            "timeout_fraction": 0.0,
            "verification_excited_fraction": 0.04,
        },
        {
            "feedback_syncdelay_us": 12.0,
            "preparation": 1,
            "timeout_fraction": 0.02,
            "verification_excited_fraction": 0.08,
        },
    ]

    result = analysis.evaluate_feedback_delay_sweep(
        rows,
        max_timeout_fraction=0.01,
        max_verification_excited_fraction=0.1,
    )

    assert result["status"] == "fail"
    assert result["selected_feedback_syncdelay_us"] is None
    assert result["delays"][0]["complete"] is False


@pytest.mark.parametrize(
    "baseline_rmse,short_interval_rmse,active_short_rmse,expected",
    [
        (0.04, 0.03, 0.05, "equivalent"),
        (0.20, 0.03, 0.05, "compact_payload_path"),
        (0.04, 0.20, 0.05, "short_inter_shot_lifecycle"),
        (0.04, 0.03, 0.20, "active_reset_state_machine"),
        (0.04, 0.20, 0.20, "short_inter_shot_and_active_reset"),
    ],
)
def test_rabi_lifecycle_diagnosis_separates_short_interval_from_feedback(
    baseline_rmse, short_interval_rmse, active_short_rmse, expected
):
    result = analysis.diagnose_rabi_lifecycle(
        baseline_rmse=baseline_rmse,
        short_interval_rmse=short_interval_rmse,
        active_short_rmse=active_short_rmse,
        max_rmse=0.15,
    )

    assert result == expected


def test_rabi_lifecycle_diagnosis_rejects_nonfinite_metrics():
    with pytest.raises(ValueError, match="finite"):
        analysis.diagnose_rabi_lifecycle(
            baseline_rmse=0.04,
            short_interval_rmse=float("nan"),
            active_short_rmse=0.05,
            max_rmse=0.15,
        )


@pytest.mark.parametrize(
    "short_passed,reset_passed,combined_passed,expected",
    [
        (True, True, True, "equivalent"),
        (False, True, False, "short_inter_shot_lifecycle"),
        (True, False, False, "active_reset_lifecycle"),
        (False, False, False, "short_inter_shot_and_active_reset"),
        (True, True, False, "short_inter_shot_active_reset_interaction"),
    ],
)
def test_t1_flux_lifecycle_diagnosis_separates_factorial_effects(
    short_passed, reset_passed, combined_passed, expected
):
    result = diagnose_t1_flux_lifecycle(
        short_passed=short_passed,
        reset_passed=reset_passed,
        combined_passed=combined_passed,
    )

    assert result == expected


def test_t1_flux_lifecycle_evaluation_compares_each_factor_to_long_passive():
    fits = {
        "passive_1000": {
            "P0": 0.03, "P1": 0.80, "tau_us": 100.0, "decaying": True
        },
        "passive_400": {
            "P0": 0.04, "P1": 0.78, "tau_us": 105.0, "decaying": True
        },
        "active_1000": {
            "P0": 0.03, "P1": 0.79, "tau_us": 70.0, "decaying": True
        },
        "active_400": {
            "P0": 0.04, "P1": 0.77, "tau_us": 65.0, "decaying": True
        },
    }

    result = evaluate_t1_flux_lifecycle(
        fits,
        max_relative_tau_difference=0.20,
        max_abs_p0_difference=0.12,
        max_abs_p1_difference=0.12,
    )

    assert result["status"] == "fail"
    assert result["diagnosis"] == "active_reset_lifecycle"
    assert result["comparisons"]["short_interval"]["status"] == "pass"
    assert result["comparisons"]["active_reset"]["status"] == "fail"
    assert result["comparisons"]["combined"]["status"] == "fail"


def test_t1_flux_lifecycle_runner_crosses_reset_with_recovery():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import (
        t1_flux_ramp_lifecycle_q3 as runner,
    )

    observed = {
        name: runner._method_config(name) for name in runner.METHODS
    }

    assert observed == {
        "passive_1000": ("none", 1000.0),
        "passive_400": ("none", 400.0),
        "active_1000": ("opx_unbounded", 1000.0),
        "active_400": ("opx_unbounded", 400.0),
    }


def test_t1_flux_recovery_sweep_selects_first_delay_passing_every_round():
    fits = {
        "passive_1000": {
            "P0": 0.03, "P1": 0.80, "tau_us": 100.0, "decaying": True
        },
        "active_400": {
            "P0": 0.03, "P1": 0.79, "tau_us": 96.0, "decaying": True
        },
        "active_600": {
            "P0": 0.04, "P1": 0.78, "tau_us": 102.0, "decaying": True
        },
        "active_800": {
            "P0": 0.04, "P1": 0.79, "tau_us": 101.0, "decaying": True
        },
    }
    round_fits = {
        "0": {
            "passive_1000": {
                "P0": 0.03, "P1": 0.80, "tau_us": 100.0, "decaying": True
            },
            "active_400": {
                "P0": 0.03, "P1": 0.79, "tau_us": 72.0, "decaying": True
            },
            "active_600": {
                "P0": 0.04, "P1": 0.78, "tau_us": 104.0, "decaying": True
            },
            "active_800": {
                "P0": 0.04, "P1": 0.79, "tau_us": 99.0, "decaying": True
            },
        },
        "1": {
            "passive_1000": {
                "P0": 0.02, "P1": 0.79, "tau_us": 98.0, "decaying": True
            },
            "active_400": {
                "P0": 0.03, "P1": 0.78, "tau_us": 101.0, "decaying": True
            },
            "active_600": {
                "P0": 0.03, "P1": 0.78, "tau_us": 100.0, "decaying": True
            },
            "active_800": {
                "P0": 0.03, "P1": 0.78, "tau_us": 102.0, "decaying": True
            },
        },
    }

    result = analysis.evaluate_t1_recovery_sweep(
        fits,
        round_fits,
        candidate_delays_us={
            "active_400": 400.0,
            "active_600": 600.0,
            "active_800": 800.0,
        },
        baseline_method="passive_1000",
        max_relative_tau_difference=0.20,
        max_abs_p0_difference=0.12,
        max_abs_p1_difference=0.12,
    )

    assert result["status"] == "pass"
    assert result["selected_active_relax_us"] == pytest.approx(600.0)
    assert [row["passed"] for row in result["rows"]] == [False, True, True]
    assert result["rows"][0]["failed_rounds"] == ["0"]


def test_t1_flux_recovery_sweep_fails_closed_for_missing_round_fit():
    baseline = {
        "P0": 0.03, "P1": 0.80, "tau_us": 100.0, "decaying": True
    }
    active = {
        "P0": 0.03, "P1": 0.79, "tau_us": 102.0, "decaying": True
    }

    result = analysis.evaluate_t1_recovery_sweep(
        {"passive_1000": baseline, "active_400": active},
        {"0": {"passive_1000": baseline}},
        candidate_delays_us={"active_400": 400.0},
        baseline_method="passive_1000",
        max_relative_tau_difference=0.20,
        max_abs_p0_difference=0.12,
        max_abs_p1_difference=0.12,
    )

    assert result["status"] == "fail"
    assert result["selected_active_relax_us"] is None
    assert result["rows"][0]["complete"] is False


def test_paired_t1_recovery_sweep_selects_shortest_stable_delay():
    methods = (
        "passive_1000",
        "active_25",
        "active_100",
        "active_400",
        "active_1000",
    )
    aggregate_taus = {
        "passive_1000": 100.0,
        "active_25": 75.0,
        "active_100": 97.0,
        "active_400": 101.0,
        "active_1000": 100.0,
    }
    fits = {
        method: {
            "P0": 0.03,
            "P1": 0.80,
            "tau_us": tau,
            "tau_err_us": 4.0,
            "decaying": True,
        }
        for method, tau in aggregate_taus.items()
    }
    round_fits = {}
    for round_index, baseline_tau in enumerate((96.0, 100.0, 104.0)):
        round_fits[str(round_index)] = {
            method: {
                "P0": 0.03,
                "P1": 0.80,
                "tau_us": (
                    0.75 * baseline_tau
                    if method == "active_25"
                    else aggregate_taus[method] * baseline_tau / 100.0
                ),
                "tau_err_us": 5.0,
                "decaying": True,
            }
            for method in methods
        }

    result = analysis.evaluate_paired_t1_recovery_sweep(
        fits,
        round_fits,
        candidate_delays_us={
            "active_25": 25.0,
            "active_100": 100.0,
            "active_400": 400.0,
            "active_1000": 1000.0,
        },
        baseline_method="passive_1000",
        control_method="active_1000",
        max_relative_tau_difference=0.15,
        max_abs_p0_difference=0.12,
        max_abs_p1_difference=0.12,
        max_heterogeneity_i2=0.5,
    )

    assert result["status"] == "pass"
    assert result["control_passed"] is True
    assert result["selected_active_relax_us"] == pytest.approx(100.0)
    assert [row["passed"] for row in result["rows"]] == [False, True, True, True]


def test_paired_active_delay_runner_keeps_each_delay_matched_across_methods():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import (
        t1_flux_ramp_active_delay_paired_q3 as runner,
    )

    observed = {
        method: runner._method_config(method) for method in runner.METHODS
    }

    assert observed == {
        "passive_1000": ("none", 1000.0),
        "active_25": ("opx_unbounded", 25.0),
        "active_100": ("opx_unbounded", 100.0),
        "active_400": ("opx_unbounded", 400.0),
        "active_1000": ("opx_unbounded", 1000.0),
    }
    schedule = runner._schedule(np.asarray([1.0, 100.0, 750.0]))
    assert len(schedule) == runner.ROUNDS * 3 * len(runner.METHODS)
    for start in range(0, len(schedule), len(runner.METHODS)):
        group = schedule[start:start + len(runner.METHODS)]
        assert len({round_index for round_index, _, _ in group}) == 1
        assert len({delay_index for _, _, delay_index in group}) == 1
        assert {method for _, method, _ in group} == set(runner.METHODS)


def test_persistent_park_runner_scans_park_lifecycle_and_recovery_together():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import (
        t1_flux_ramp_persistent_park_paired_q3 as runner,
    )

    observed = {
        method: (
            runner._method_config(method),
            runner._method_overrides(method),
        )
        for method in runner.METHODS
    }

    assert observed == {
        "passive_1000": (("none", 1000.0), {"opx_persistent_park": False}),
        "persistent_25": (("opx_unbounded", 25.0), {"opx_persistent_park": True}),
        "persistent_100": (("opx_unbounded", 100.0), {"opx_persistent_park": True}),
        "persistent_400": (("opx_unbounded", 400.0), {"opx_persistent_park": True}),
        "per_shot_1000": (("opx_unbounded", 1000.0), {"opx_persistent_park": False}),
    }
    schedule = runner._schedule(np.asarray([1.0, 100.0, 750.0]))
    assert len(schedule) == runner.ROUNDS * 3 * len(runner.METHODS)
    for start in range(0, len(schedule), len(runner.METHODS)):
        group = schedule[start:start + len(runner.METHODS)]
        assert len({round_index for round_index, _, _ in group}) == 1
        assert len({delay_index for _, _, delay_index in group}) == 1
        assert {method for _, method, _ in group} == set(runner.METHODS)


def test_park_refresh_runner_compares_short_refresh_against_both_controls():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import (
        t1_flux_ramp_park_refresh_paired_q3 as runner,
    )

    observed = {
        method: (
            runner._method_config(method),
            runner._method_overrides(method),
        )
        for method in runner.METHODS
    }

    assert observed == {
        "passive_1000": (("none", 1000.0), {
            "opx_persistent_park": False,
            "opx_refresh_park_before_shot": False,
        }),
        "per_shot_25": (("opx_unbounded", 25.0), {
            "opx_persistent_park": False,
            "opx_refresh_park_before_shot": False,
        }),
        "refresh_25": (("opx_unbounded", 25.0), {
            "opx_persistent_park": True,
            "opx_refresh_park_before_shot": True,
        }),
        "refresh_100": (("opx_unbounded", 100.0), {
            "opx_persistent_park": True,
            "opx_refresh_park_before_shot": True,
        }),
        "per_shot_1000": (("opx_unbounded", 1000.0), {
            "opx_persistent_park": False,
            "opx_refresh_park_before_shot": False,
        }),
    }
    schedule = runner._schedule(np.asarray([1.0, 100.0, 750.0]))
    assert len(schedule) == runner.ROUNDS * 3 * len(runner.METHODS)
    for start in range(0, len(schedule), len(runner.METHODS)):
        group = schedule[start:start + len(runner.METHODS)]
        assert len({round_index for round_index, _, _ in group}) == 1
        assert len({delay_index for _, _, delay_index in group}) == 1
        assert {method for _, method, _ in group} == set(runner.METHODS)


def test_t1_runner_fits_each_acquisition_round_independently():
    delays = np.asarray([1.0, 10.0, 50.0, 100.0, 300.0, 750.0])
    round_rows = {}
    for round_index, tau in ((0, 100.0), (1, 130.0)):
        rows = []
        for method in ("passive", "opx_unbounded"):
            for delay_index, delay in enumerate(delays):
                probability = 0.02 + 0.78 * np.exp(-delay / tau)
                rows.append({
                    "method": method,
                    "delay_index": delay_index,
                    "delay_us": delay,
                    "shots": 200,
                    "excited_fraction": round(200 * probability) / 200,
                })
        round_rows[round_index] = rows

    fits, errors = analysis.fit_t1_rounds(
        round_rows,
        methods=("passive", "opx_unbounded"),
    )

    assert errors == {"0": {}, "1": {}}
    assert fits["0"]["passive"]["tau_us"] == pytest.approx(100.0, rel=0.08)
    assert fits["1"]["opx_unbounded"]["tau_us"] == pytest.approx(130.0, rel=0.08)


def test_t1_flux_recovery_runner_scans_only_reset_recovery_time():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import (
        t1_flux_ramp_recovery_t1_q3 as runner,
    )

    observed = {
        name: runner._method_config(name) for name in runner.METHODS
    }

    assert observed == {
        "passive_1000": ("none", 1000.0),
        "active_400": ("opx_unbounded", 400.0),
        "active_600": ("opx_unbounded", 600.0),
        "active_800": ("opx_unbounded", 800.0),
        "active_1000": ("opx_unbounded", 1000.0),
    }


def test_attempt_limit_sweep_selects_smallest_limit_passing_both_preparations():
    rows = [
        {
            "max_reset_attempts": 16,
            "preparation": 1,
            "timeout_fraction": 0.008,
            "verification_excited_fraction": 0.06,
        },
        {
            "max_reset_attempts": 8,
            "preparation": 0,
            "timeout_fraction": 0.009,
            "verification_excited_fraction": 0.04,
        },
        {
            "max_reset_attempts": 12,
            "preparation": 1,
            "timeout_fraction": 0.009,
            "verification_excited_fraction": 0.07,
        },
        {
            "max_reset_attempts": 16,
            "preparation": 0,
            "timeout_fraction": 0.004,
            "verification_excited_fraction": 0.04,
        },
        {
            "max_reset_attempts": 8,
            "preparation": 1,
            "timeout_fraction": 0.05,
            "verification_excited_fraction": 0.09,
        },
        {
            "max_reset_attempts": 12,
            "preparation": 0,
            "timeout_fraction": 0.005,
            "verification_excited_fraction": 0.04,
        },
    ]

    result = analysis.evaluate_attempt_limit_sweep(
        rows,
        max_timeout_fraction=0.01,
        max_verification_excited_fraction=0.1,
    )

    assert result["status"] == "pass"
    assert result["selected_max_reset_attempts"] == 12
    assert [row["passed"] for row in result["attempt_limits"]] == [False, True, True]


def test_attempt_limit_sweep_fails_closed_for_incomplete_limits():
    rows = [
        {
            "max_reset_attempts": 16,
            "preparation": 0,
            "timeout_fraction": 0.0,
            "verification_excited_fraction": 0.04,
        }
    ]

    result = analysis.evaluate_attempt_limit_sweep(
        rows,
        max_timeout_fraction=0.01,
        max_verification_excited_fraction=0.1,
    )

    assert result["status"] == "fail"
    assert result["selected_max_reset_attempts"] is None
    assert result["attempt_limits"][0]["complete"] is False


@pytest.mark.parametrize(
    "taus, expected",
    [
        ((100.0, 100.0, 100.0, 100.0, 95.0), "no_active_effect"),
        ((100.0, 80.0, 80.0, 80.0, 80.0), "park_dwell"),
        ((100.0, 100.0, 80.0, 80.0, 80.0), "reset_readout_load"),
        ((100.0, 100.0, 100.0, 80.0, 80.0), "reset_pi_load"),
        ((100.0, 100.0, 100.0, 100.0, 80.0), "feedback_dependent_reset"),
    ],
)
def test_t1_load_attribution_reports_the_first_shortening_stage(taus, expected):
    methods = (
        "passive_1000",
        "park_hold_1000",
        "readout_x2_1000",
        "pi_readout_x2_1000",
        "active_1000",
    )
    fits = {
        method: {
            "tau_us": tau,
            "tau_err_us": 5.0,
            "P0": 0.03,
            "P1": 0.82,
            "decaying": True,
        }
        for method, tau in zip(methods, taus)
    }
    round_fits = {
        str(round_index): {
            method: dict(fit) for method, fit in fits.items()
        }
        for round_index in range(3)
    }

    result = analysis.evaluate_t1_load_attribution(
        fits,
        round_fits,
        baseline_method="passive_1000",
        active_method="active_1000",
        staged_methods={
            "park_hold_1000": "park_dwell",
            "readout_x2_1000": "reset_readout_load",
            "pi_readout_x2_1000": "reset_pi_load",
        },
        max_relative_tau_difference=0.15,
        max_abs_p0_difference=0.12,
        max_abs_p1_difference=0.12,
    )

    assert result["diagnosis"] == expected
    assert set(result["comparisons"]) == set(methods[1:])


def test_t1_load_attribution_rejects_a_heterogeneous_apparent_cause():
    methods = (
        "passive_1000",
        "park_hold_1000",
        "readout_x2_1000",
        "pi_readout_x2_1000",
        "active_1000",
    )
    aggregate_taus = (115.25, 85.30, 103.66, 98.78, 97.86)
    fits = {
        method: {
            "tau_us": tau,
            "tau_err_us": 7.0,
            "P0": 0.03,
            "P1": 0.78,
            "decaying": True,
        }
        for method, tau in zip(methods, aggregate_taus)
    }
    round_taus = {
        "0": (98.52, 87.48, 128.77, 95.53, 113.49),
        "1": (139.90, 68.05, 86.87, 106.16, 88.40),
        "2": (102.49, 108.13, 93.69, 92.20, 89.81),
    }
    round_fits = {
        round_index: {
            method: {
                "tau_us": tau,
                "tau_err_us": 10.0,
                "P0": 0.03,
                "P1": 0.78,
                "decaying": True,
            }
            for method, tau in zip(methods, taus)
        }
        for round_index, taus in round_taus.items()
    }

    result = analysis.evaluate_t1_load_attribution(
        fits,
        round_fits,
        baseline_method="passive_1000",
        active_method="active_1000",
        staged_methods={
            "park_hold_1000": "park_dwell",
            "readout_x2_1000": "reset_readout_load",
            "pi_readout_x2_1000": "reset_pi_load",
        },
        max_relative_tau_difference=0.15,
        max_abs_p0_difference=0.12,
        max_abs_p1_difference=0.12,
    )

    assert result["diagnosis"] == "time_dependent_or_inconclusive"
    assert result["comparisons"]["park_hold_1000"]["robust_shortened"] is False
    assert result["comparisons"]["active_1000"]["robust_shortened"] is False


def test_t1_load_attribution_runner_holds_recovery_constant_across_loads():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import (
        t1_flux_ramp_reset_load_q3 as runner,
    )

    observed = {
        method: runner._method_config(method) for method in runner.METHODS
    }

    assert observed == {
        "passive_1000": ("none", 1000.0),
        "park_hold_1000": ("diagnostic_hold", 1000.0),
        "readout_x2_1000": ("diagnostic_readout", 1000.0),
        "pi_readout_x2_1000": ("diagnostic_pi_readout", 1000.0),
        "active_1000": ("opx_unbounded", 1000.0),
    }
    assert runner.DIAGNOSTIC_CYCLES == 2
    assert runner.DIAGNOSTIC_HOLD_US == pytest.approx(65.1)


def test_t1_runner_resolves_explicit_delays_without_replacing_them_with_logspace():
    delays = analysis.resolve_t1_delays(
        explicit_delays_us=(1.0, 35.0, 100.0, 250.0, 750.0),
        minimum_us=1.0,
        maximum_us=750.0,
        points=9,
    )

    assert delays.tolist() == [1.0, 35.0, 100.0, 250.0, 750.0]


def test_reset_load_schedule_keeps_each_delay_matched_across_methods():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import (
        t1_flux_ramp_reset_load_q3 as runner,
    )

    schedule = runner._schedule(np.asarray([1.0, 100.0, 750.0]))

    assert len(schedule) == runner.ROUNDS * 3 * len(runner.METHODS)
    for start in range(0, len(schedule), len(runner.METHODS)):
        group = schedule[start:start + len(runner.METHODS)]
        assert len({round_index for round_index, _, _ in group}) == 1
        assert len({delay_index for _, _, delay_index in group}) == 1
        assert {method for _, method, _ in group} == set(runner.METHODS)
