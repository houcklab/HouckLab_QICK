"""Measure q3 step 3b using the high-SNR 2026-09-13 candidate."""

from pathlib import Path


OUTPUT_DIR = Path(
    "Z:/FluxTeam/Data/q3/2026_09_13/"
    "predistortion_validation/high_snr_3b"
)
CORRECTION_JSON = Path(
    "Z:/FluxTeam/Data/q3/2026_09_13/predistortion_validation/high_snr_3b/"
    "q3/q3_2026_09_13/q3_20_03_47_Qubit_Flux_Step_Response_"
    "upper_phase_residual_composed_dc_compensation.json"
)


def validation_gain():
    """Apply the already-composed candidate without another gain transform."""
    return 1.0


def frequency_grid_mhz():
    """Return the inclusive frequency grid used by the calibration scan."""
    return tuple(4000.0 + 0.5 * index for index in range(161))


def step_response_settings():
    """Return settings for correction validation without fitting a new JSON."""
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
        "t_max_us": 200.0,
        "t_step_us": 4.0,
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
    runner.FLUX_TAIL_COMPENSATION_GAIN = validation_gain()
    runner.STEP3B_GAIN_SWEEP = None

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    soc, soccfg = runner.makeProxy()
    runner._set_yoko_if_requested()
    print("[P3b] validating the phase-corroborated q3 residual correction")
    print(f"[P3b] applying {CORRECTION_JSON}")
    print("[P3b] 200 shots; 4.000--4.080 GHz at 0.5 MHz")
    print("[P3b] 50 delays from 1--197 us; upper shoulder tracked for early-time visibility")
    runner.run_step3b_step_response_correct(
        str(OUTPUT_DIR), soc, soccfg, correction_json=str(CORRECTION_JSON)
    )


if __name__ == "__main__":
    main()
