def configure_runner(target):
    target.LIVE_PLOTS = False
    target.RESET_MODE = "active"
    target.P1_RESONATOR["run"] = False
    target.P2_QUBIT_SPEC_FULL["run"] = False
    target.P3_STEP_RESPONSE.update({"run_fit": False, "run_correct": False})
    target.P4_LONG_TIME["run"] = False
    target.P5_SS_CAL["run"] = False
    target.P6_3PT_T1["run"] = False
    target.P6_FULL_T1.clear()
    target.P6_FULL_T1.update({
        "run": True,
        "apply_flux_tail_compensation": False,
        "shots": 50,
        "dc_min": -20500,
        "dc_max": -20000,
        "dc_step": 500,
        "freq_step_mhz": None,
        "wall_clock_duration_min": None,
        "quality_factor": None,
        "t_max_us": 150.0,
        "auto_tmax_factor": 3.0,
        "t_min_us_default": 1.0,
        "t_points_default": 4,
        "T1_probe_cfg": None,
    })


def main():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSSpectroscopy as runner

    configure_runner(runner)
    runner.main()


if __name__ == "__main__":
    main()
