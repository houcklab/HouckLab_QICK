from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSSpectroscopy as runner


park_gain = int(runner.BaseConfig["ff_park_gain"])
runner.LIVE_PLOTS = True
runner.SET_YOKO = False
runner.RESET_MODE = "passive"
runner.BASELINE_DC_OFFSET = None
runner.USE_RESONATOR_LOOKUP = False
runner.RESONATOR_FIT_PARAMS = None
runner.P1_RESONATOR["run"] = False
runner.P2_QUBIT_SPEC_FULL.clear()
runner.P2_QUBIT_SPEC_FULL.update({
    "run": True,
    "advanced_fit": False,
    "shots": 200,
    "relax_delay_us": 100.0,
    "spec_amp": 15000,
    "spec_len_us": 1.0,
    "freq_min": 4358.0,
    "freq_max": 4373.0,
    "freq_step": 0.25,
    "dc_min": park_gain,
    "dc_max": park_gain,
    "dc_step": 1,
    "live_plot": True,
})
runner.P3_STEP_RESPONSE["run_fit"] = False
runner.P3_STEP_RESPONSE["run_correct"] = False
runner.P4_LONG_TIME["run"] = False
runner.P5_SS_CAL["run"] = False
runner.P6_3PT_T1["run"] = False
runner.P6_FULL_T1["run"] = False


if __name__ == "__main__":
    runner.main()
