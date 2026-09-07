from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSSpectroscopy as runner


runner.LIVE_PLOTS = False
runner.SET_YOKO = False
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
runner.FLUX_TAIL_COMPENSATION_GAIN = 1.0
runner.USE_RESONATOR_LOOKUP = False
runner.RESONATOR_FIT_PARAMS = None
runner.RESET_MODE = "passive"
runner.P1_RESONATOR["run"] = False
runner.P2_QUBIT_SPEC_FULL["run"] = False
runner.P3_STEP_RESPONSE.update({"run_fit": False, "run_correct": False})
runner.P4_LONG_TIME.clear()
runner.P4_LONG_TIME.update({
    "run": True,
    "advanced_fit": False,
    "shots": 20,
    "relax_delay_us": 500.0,
    "spec_amp": 15000,
    "spec_len_us": 1.0,
    "freq_min": 4249.0,
    "freq_max": 4372.0,
    "freq_step": 3.0,
    "dc_min": -26000,
    "dc_max": -20000,
    "dc_step": 1000,
    "long_time_us": 5.0,
    "average_window_us": 0.0,
    "average_step_us": 0.016,
    "inter_target_wait_us": 100.0,
    "live_plot": False,
})
runner.P5_SS_CAL["run"] = False
runner.P6_3PT_T1["run"] = False
runner.P6_FULL_T1["run"] = False


if __name__ == "__main__":
    runner.main()
