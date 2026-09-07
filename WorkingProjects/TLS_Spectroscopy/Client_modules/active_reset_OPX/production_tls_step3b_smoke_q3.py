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
runner.FLUX_TAIL_COMPENSATION_GAIN = 0.75
runner.STEP3B_GAIN_SWEEP = None
runner.USE_RESONATOR_LOOKUP = False
runner.RESONATOR_FIT_PARAMS = None
runner.RESET_MODE = "passive"
runner.P1_RESONATOR["run"] = False
runner.P2_QUBIT_SPEC_FULL["run"] = False
runner.P3_STEP_RESPONSE.clear()
runner.P3_STEP_RESPONSE.update({
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
})
runner.P4_LONG_TIME["run"] = False
runner.P5_SS_CAL["run"] = False
runner.P6_3PT_T1["run"] = False
runner.P6_FULL_T1["run"] = False


if __name__ == "__main__":
    runner.main()
