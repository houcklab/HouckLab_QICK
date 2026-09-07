from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSSpectroscopy as runner


runner.LIVE_PLOTS = True
runner.SET_YOKO = False
runner.RESET_MODE = "passive"
runner.BaseConfig["qua_order_max_records_per_block"] = 3603
runner.P1_RESONATOR["run"] = False
runner.P2_QUBIT_SPEC_FULL.clear()
runner.P2_QUBIT_SPEC_FULL.update({
    "run": True,
    "advanced_fit": False,
    "shots": 100,
    "relax_delay_us": 100.0,
    "spec_amp": 20000,
    "spec_len_us": 0.5,
    "freq_min": 4200.0,
    "freq_max": 4450.0,
    "freq_step": 1.0,
    "dc_min": -26000,
    "dc_max": -25000,
    "dc_step": 500,
    "live_plot": True,
})
runner.P3_STEP_RESPONSE.update({"run_fit": False, "run_correct": False})
runner.P4_LONG_TIME["run"] = False
runner.P5_SS_CAL["run"] = False
runner.P6_3PT_T1["run"] = False
runner.P6_FULL_T1["run"] = False


if __name__ == "__main__":
    runner.main()
