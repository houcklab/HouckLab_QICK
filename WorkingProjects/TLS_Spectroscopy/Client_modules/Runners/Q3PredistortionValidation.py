"""Validate the q3 piecewise flux-step correction measured on 2026-09-13."""

from pathlib import Path


OUTPUT_DIR = Path(
    "Z:/FluxTeam/Data/q3/2026_09_13/"
    "predistortion_validation/corrected_readout_after_park_gain_0p8"
)
CORRECTION_JSON = Path(
    "Z:/FluxTeam/Data/q3/2026_09_13/predistortion_validation/"
    "uncorrected_readout_after_park/q3/q3_2026_09_13/"
    "q3_00_53_50_Qubit_Flux_Step_Response_"
    "rise_decay_bump_dc_compensation.json"
)


def validation_gain():
    """Return the damped gain inferred from the gain-zero and gain-one traces."""
    return 0.8


def frequency_grid_mhz():
    """Return the inclusive frequency grid used by the calibration scan."""
    return tuple(range(3950, 4081, 1))


def step_response_settings():
    """Return settings for correction validation without fitting a new JSON."""
    grid = frequency_grid_mhz()
    return {
        "run_fit": False,
        "run_correct": True,
        "shots": 100,
        "spec_amp": 25_000,
        "spec_len_us": 0.5,
        "freq_step": 1.0,
        "auto_center_frequency_window": True,
        "auto_freq_absolute_min_mhz": float(grid[0]),
        "auto_freq_absolute_max_mhz": float(grid[-1]),
        "t_min_us": 1.0,
        "t_max_us": 400.0,
        "t_step_us": 4.0,
        "baseline_rearm_us": 100.0,
        "piecewise_min_multiplier": 0.5,
        "piecewise_max_multiplier": 1.5,
        "readout_after_park": True,
        "live_plot": True,
    }


def main():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
        TLSSpectroscopy as runner,
    )

    if not CORRECTION_JSON.is_file():
        raise FileNotFoundError(f"QICK correction JSON not found: {CORRECTION_JSON}")

    runner.P3_STEP_RESPONSE.update(step_response_settings())
    runner.FLUX_TAIL_COMPENSATION_GAIN = validation_gain()
    runner.STEP3B_GAIN_SWEEP = None

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    soc, soccfg = runner.makeProxy()
    runner._set_yoko_if_requested()
    print(
        f"[P3b] corrected q3 validation at gain {validation_gain():.3f}; "
        "no new correction will be fitted"
    )
    print(f"[P3b] applying {CORRECTION_JSON}")
    print("[P3b] 100 shots; 3.950--4.080 GHz at 1 MHz")
    runner.run_step3b_step_response_correct(
        str(OUTPUT_DIR), soc, soccfg, correction_json=str(CORRECTION_JSON)
    )


if __name__ == "__main__":
    main()
