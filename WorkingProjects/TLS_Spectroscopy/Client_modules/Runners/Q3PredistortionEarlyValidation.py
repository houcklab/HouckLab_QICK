"""Acquire a dense early-time q3 map with the composed residual correction."""

from pathlib import Path

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    Q3PredistortionResidualRefit as residual_refit,
)


OUTPUT_DIR = Path(
    "Z:/FluxTeam/Data/q3/2026_09_13/"
    "predistortion_validation/early_dense"
)
CORRECTION_JSON = residual_refit.OUTPUT_JSON


def frequency_grid_mhz():
    """Return the inclusive narrow grid surrounding both q3 shoulders."""
    return tuple(4025.0 + 0.5 * index for index in range(71))


def step_response_settings():
    """Return a measurement-only configuration for the first 40 microseconds."""
    grid = frequency_grid_mhz()
    return {
        "run_fit": False,
        "run_correct": True,
        "shots": 200,
        "spec_amp": 25_000,
        "spec_len_us": 0.5,
        "freq_step": 0.5,
        "auto_center_frequency_window": True,
        "auto_freq_absolute_min_mhz": float(grid[0]),
        "auto_freq_absolute_max_mhz": float(grid[-1]),
        "t_min_us": 1.0,
        "t_max_us": 41.0,
        "t_step_us": 1.0,
        "baseline_rearm_us": 100.0,
        "piecewise_min_multiplier": 0.5,
        "piecewise_max_multiplier": 1.5,
        "readout_after_park": True,
        "trace_tracking_mode": "image_v26",
        "trace_polarity": "dark",
        "trace_shoulder": "upper",
        "trace_max_jump_mhz": 8.0,
        "live_plot": True,
    }


def main():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
        TLSSpectroscopy as runner,
    )

    if not CORRECTION_JSON.is_file():
        raise FileNotFoundError(f"QICK correction JSON not found: {CORRECTION_JSON}")

    runner.P3_STEP_RESPONSE.update(step_response_settings())
    runner.FLUX_TAIL_COMPENSATION_GAIN = 1.0
    runner.STEP3B_GAIN_SWEEP = None

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    soc, soccfg = runner.makeProxy()
    runner._set_yoko_if_requested()
    print("[early] measuring the composed q3 correction; no correction will be fitted")
    print(f"[early] applying {CORRECTION_JSON}")
    print("[early] 200 shots; 4.025--4.060 GHz at 0.5 MHz")
    print("[early] 40 delays from 1--40 us at 1 us spacing")
    runner.run_step3b_step_response_correct(
        str(OUTPUT_DIR), soc, soccfg, correction_json=str(CORRECTION_JSON)
    )


if __name__ == "__main__":
    main()
