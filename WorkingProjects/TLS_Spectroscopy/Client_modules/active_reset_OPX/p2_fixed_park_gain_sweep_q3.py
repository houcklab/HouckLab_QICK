from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import GateCalibration as runner


runner.LIVE_PLOTS = True
runner.RESET_MODE = "passive"
runner.P_TRANSMISSION["run"] = False
runner.P_TRANSMISSION_SWEEP["run"] = False
runner.P_QUBIT_SPEC["run"] = False
runner.P_QUBIT_SPEC_SWEEP.clear()
runner.P_QUBIT_SPEC_SWEEP.update({
    "run": True,
    "shots": 100,
    "freq_start_mhz": 4300.0,
    "freq_stop_mhz": 4400.0,
    "freq_points": 201,
    "gain_min": 0,
    "gain_max": 30000,
    "gain_points": 7,
    "spec_length_us": 1.0,
    "relax_delay_us": 100.0,
})
runner.P_SS_CAL["run"] = False
runner.P_RABI_CHEVRON_IQ["run"] = False
runner.P_RABI_CHEVRON_SS["run"] = False
runner.P_READOUT_OPT["run"] = False
runner.P_QUBIT_OPT["run"] = False


if __name__ == "__main__":
    runner.main()
