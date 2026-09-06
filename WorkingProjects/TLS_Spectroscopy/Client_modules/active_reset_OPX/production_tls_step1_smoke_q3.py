from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSSpectroscopy as runner


runner.LIVE_PLOTS = False
runner.SET_YOKO = False
runner.BASELINE_DC_OFFSET = -25790
runner.RESET_MODE = "passive"
runner.P1_RESONATOR.clear()
runner.P1_RESONATOR.update({
    "run": True,
    "shots": 20,
    "freq_min": 6931.0,
    "freq_max": 6935.0,
    "freq_step": 0.1,
    "dc_min": -30000,
    "dc_max": -18000,
    "dc_step": 2000,
    "lookup_smooth_points": None,
    "live_plot": False,
    "spec_amp": 1000,
    "spec_len_us": 5.0,
})
runner.P2_QUBIT_SPEC_FULL["run"] = False
runner.P3_STEP_RESPONSE.update({"run_fit": False, "run_correct": False})
runner.P4_LONG_TIME["run"] = False
runner.P5_SS_CAL["run"] = False
runner.P6_3PT_T1["run"] = False
runner.P6_FULL_T1["run"] = False


if __name__ == "__main__":
    runner.main()
