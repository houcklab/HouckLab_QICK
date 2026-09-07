from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production_tls_full_t1_smoke_q3 import (
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
    P6_3PT_T1 = {"run": True}
    P6_FULL_T1 = {"run": False}


def test_full_t1_smoke_selects_one_corrected_active_qua_order_grid():
    runner = Runner()

    configure_runner(runner)

    assert runner.LIVE_PLOTS is False
    assert runner.RESET_MODE == "active"
    assert runner.FLUX_FIT_PARAMS == [
        8.203384791028979,
        0.2902930003646722,
        8774.00218131707,
        -23058.31389817458,
        0.9831224825856887,
        -1.2183803188472806e-05,
    ]
    assert runner.BASELINE_DC_OFFSET == -25790
    assert runner.TARGET_DC_OFFSET == -20000
    assert runner.FLUX_TAIL_COMPENSATION_GAIN == 0.75
    assert runner.P1_RESONATOR["run"] is False
    assert runner.P2_QUBIT_SPEC_FULL["run"] is False
    assert runner.P3_STEP_RESPONSE == {"run_fit": False, "run_correct": False}
    assert runner.P4_LONG_TIME["run"] is False
    assert runner.P5_SS_CAL["run"] is False
    assert runner.P6_3PT_T1["run"] is False
    assert runner.P6_FULL_T1 == {
        "run": True,
        "apply_flux_tail_compensation": True,
        "shots": 50,
        "dc_min": -20500,
        "dc_max": -19500,
        "dc_step": 500,
        "freq_step_mhz": None,
        "wall_clock_duration_min": None,
        "quality_factor": None,
        "t_max_us": 150.0,
        "auto_tmax_factor": 3.0,
        "t_min_us_default": 1.0,
        "t_points_default": 4,
        "T1_probe_cfg": None,
    }
