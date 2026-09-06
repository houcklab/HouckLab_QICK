from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSSpectroscopy as runner


runner.LIVE_PLOTS = False
runner.SET_YOKO = False
runner.BASELINE_DC_OFFSET = -25790
runner.USE_RESONATOR_LOOKUP = False
runner.RESONATOR_FIT_PARAMS = None
runner.RESET_MODE = "passive"
runner.P1_RESONATOR["run"] = False
runner.P2_QUBIT_SPEC_FULL.clear()
runner.P2_QUBIT_SPEC_FULL.update({
    "run": True,
    "advanced_fit": True,
    "shots": 20,
    "relax_delay_us": 100.0,
    "spec_amp": 10000,
    "spec_len_us": 0.5,
    "freq_min": 4000.0,
    "freq_max": 4372.0,
    "freq_step": 2.0,
    "dc_min": -26000,
    "dc_max": -19500,
    "dc_step": 500,
    "live_plot": False,
})
runner.P3_STEP_RESPONSE.update({"run_fit": False, "run_correct": False})
runner.P4_LONG_TIME["run"] = False
runner.P5_SS_CAL["run"] = False
runner.P6_3PT_T1["run"] = False
runner.P6_FULL_T1["run"] = False


if __name__ == "__main__":
    runner.main()
