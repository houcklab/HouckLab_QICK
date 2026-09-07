from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production_tls_t1_correction_equivalence_q3 import (
    configure_runner,
)


class Runner:
    LIVE_PLOTS = True
    RESET_MODE = "passive"
    FLUX_FIT_PARAMS = None
    BASELINE_DC_OFFSET = 0
    TARGET_DC_OFFSET = 0
    FLUX_TAIL_COMPENSATION_GAIN = 0.1
    P1_RESONATOR = {"run": True}
    P2_QUBIT_SPEC_FULL = {"run": True}
    P3_STEP_RESPONSE = {"run_fit": True, "run_correct": True}
    P4_LONG_TIME = {"run": True}
    P5_SS_CAL = {"run": True}
    P6_3PT_T1 = {"run": False}
    P6_FULL_T1 = {"run": False}


def test_equivalence_runner_selects_corrected_three_point_and_full_t1():
    runner = Runner()

    configure_runner(runner)

    assert runner.LIVE_PLOTS is False
    assert runner.RESET_MODE == "active"
    assert runner.BASELINE_DC_OFFSET == -25790
    assert runner.TARGET_DC_OFFSET == -20000
    assert runner.FLUX_TAIL_COMPENSATION_GAIN == 0.75
    assert runner.P1_RESONATOR["run"] is False
    assert runner.P2_QUBIT_SPEC_FULL["run"] is False
    assert runner.P3_STEP_RESPONSE == {"run_fit": False, "run_correct": False}
    assert runner.P4_LONG_TIME["run"] is False
    assert runner.P5_SS_CAL["run"] is False
    assert runner.P6_3PT_T1 == {
        "run": True,
        "apply_flux_tail_compensation": True,
        "shots": 200,
        "dc_min": -20500,
        "dc_max": -19500,
        "dc_step": 500,
        "freq_step_mhz": None,
        "wall_clock_duration_min": None,
        "Ts_us": 70.0,
        "min_ref_contrast": 0.05,
        "max_plot_t1_multiple": 20.0,
    }
    assert runner.P6_FULL_T1 == {
        "run": True,
        "apply_flux_tail_compensation": True,
        "shots": 200,
        "dc_min": -20500,
        "dc_max": -19500,
        "dc_step": 500,
        "freq_step_mhz": None,
        "wall_clock_duration_min": None,
        "quality_factor": None,
        "t_max_us": 250.0,
        "auto_tmax_factor": 3.0,
        "t_min_us_default": 1.0,
        "t_points_default": 17,
        "T1_probe_cfg": None,
    }
