"""Run a fresh q3 P3a calibration with return-to-park readout.

No existing compensation is applied.  Returning to park before readout makes
the dark qubit transition visible from the first delay point, allowing the
full uncorrected plant response to be fitted without early-time extrapolation.
"""

from pathlib import Path

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSSpectroscopy as runner,
)


OUTPUT_DIR = Path(
    "Z:/FluxTeam/Data/q3/2026_09_13/"
    "predistortion_validation/high_snr_3a"
)


def main():
    runner.P3_STEP_RESPONSE.update(
        {
            "run_fit": True,
            "run_correct": False,
            "shots": 1000,
            "spec_amp": 25_000,
            "spec_len_us": 0.5,
            "freq_step": 0.5,
            "auto_center_frequency_window": True,
            "auto_freq_absolute_min_mhz": 4000.0,
            "auto_freq_absolute_max_mhz": 4080.0,
            "t_min_us": 1.0,
            "t_max_us": 200.0,
            "t_step_us": 4.0,
            "correction_fit_start_us": None,
            "correction_time_origin_us": 0.0,
            "baseline_rearm_us": 100.0,
            "piecewise_min_multiplier": 0.5,
            "piecewise_max_multiplier": 1.5,
            "readout_after_park": True,
            "trace_tracking_mode": "image_v26",
            "trace_polarity": "dark",
            "trace_shoulder": "auto",
            "trace_max_jump_mhz": 8.0,
            "live_plot": True,
        }
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    soc, soccfg = runner.makeProxy()
    runner._set_yoko_if_requested()
    print("[P3a] uncorrected plant-response measurement")
    print("[P3a] readout after park; dark transition expected")
    print("[P3a] 1000 shots; 4.000--4.080 GHz at 0.5 MHz")
    print("[P3a] 50 delay points from 1 to 197 us")
    correction_json = runner.run_step3a_step_response_fit(
        str(OUTPUT_DIR), soc, soccfg
    )
    print(f"[P3a] fresh correction candidate={correction_json}")


if __name__ == "__main__":
    main()
