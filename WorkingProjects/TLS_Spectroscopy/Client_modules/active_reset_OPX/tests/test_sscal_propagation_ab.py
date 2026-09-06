from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.sscal_propagation_ab_q3 import (
    build_run_configs,
    classify_ab,
)


def test_build_run_configs_forces_every_x180_field_without_mutating_imported_config():
    base = {
        "qubit_freq": 4367.25,
        "qubit_pi_freq": 4367.25,
        "qubit_gain": 11100,
        "qubit_pi_gain": 11100,
        "qubit_pi2_gain": 5550,
        "sigma": 0.25,
        "shots": 1000,
        "reps": 1000,
    }

    imported, forced = build_run_configs(
        base,
        forced_frequency_mhz=4365.8920294330965,
        forced_gain_dac=15500,
        forced_sigma_us=0.2,
        shots=400,
    )

    assert base["qubit_gain"] == 11100
    assert imported["qubit_gain"] == 11100
    assert imported["shots"] == 400
    assert imported["reps"] == 400
    assert forced["qubit_freq"] == 4365.8920294330965
    assert forced["qubit_pi_freq"] == 4365.8920294330965
    assert forced["qubit_gain"] == 15500
    assert forced["qubit_pi_gain"] == 15500
    assert forced["qubit_pi2_gain"] == 7750
    assert forced["sigma"] == 0.2


def test_classify_ab_identifies_configuration_propagation_failure():
    assert classify_ab(0.59, 0.89, 0.60) == "configuration_not_propagated"


def test_classify_ab_identifies_stale_known_good_pulse():
    assert classify_ab(0.59, 0.60, 0.58) == "known_good_pulse_no_longer_good"


def test_classify_ab_identifies_failure_that_does_not_reproduce():
    assert classify_ab(0.86, 0.89, 0.87) == "imported_configuration_now_works"


def test_classify_ab_identifies_drift_across_bracketing_runs():
    assert classify_ab(0.82, 0.84, 0.61) == "state_changed_during_test"
