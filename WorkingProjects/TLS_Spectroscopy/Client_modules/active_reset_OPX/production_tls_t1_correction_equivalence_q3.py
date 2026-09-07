def configure_runner(target):
    target.LIVE_PLOTS = False
    target.RESET_MODE = "active"
    target.FLUX_FIT_PARAMS = [
        8.203384791028979,
        0.2902930003646722,
        8774.00218131707,
        -23058.31389817458,
        0.9831224825856887,
        -1.2183803188472806e-05,
    ]
    target.BASELINE_DC_OFFSET = -25790
    target.TARGET_DC_OFFSET = -20000
    target.FLUX_TAIL_COMPENSATION_GAIN = 0.75
    target.P1_RESONATOR["run"] = False
    target.P2_QUBIT_SPEC_FULL["run"] = False
    target.P3_STEP_RESPONSE.update({"run_fit": False, "run_correct": False})
    target.P4_LONG_TIME["run"] = False
    target.P5_SS_CAL["run"] = False
    target.P6_3PT_T1.clear()
    target.P6_3PT_T1.update({
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
    })
    target.P6_FULL_T1.clear()
    target.P6_FULL_T1.update({
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
    })


def main():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSSpectroscopy as runner

    configure_runner(runner)
    runner.main()


if __name__ == "__main__":
    main()
