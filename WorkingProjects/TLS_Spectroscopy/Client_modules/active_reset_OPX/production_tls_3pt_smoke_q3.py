from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSSpectroscopy as runner


def main():
    runner.LIVE_PLOTS = False
    runner.RESET_MODE = "active"
    runner.FLUX_FIT_PARAMS = [
        8.203384791028979,
        0.2902930003646722,
        8774.00218131707,
        -23058.31389817458,
        0.9831224825856887,
        -1.2183803188472806e-05,
    ]
    runner.BASELINE_DC_OFFSET = -25790
    runner.TARGET_DC_OFFSET = -20000
    runner.FLUX_TAIL_COMPENSATION_GAIN = 0.75
    runner.P1_RESONATOR["run"] = False
    runner.P2_QUBIT_SPEC_FULL["run"] = False
    runner.P3_STEP_RESPONSE["run_fit"] = False
    runner.P3_STEP_RESPONSE["run_correct"] = False
    runner.P4_LONG_TIME["run"] = False
    runner.P5_SS_CAL["run"] = False
    runner.P6_FULL_T1["run"] = False
    runner.P6_3PT_T1.update({
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
    })
    runner.main()


if __name__ == "__main__":
    main()
