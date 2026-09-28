"""Measure q3's moving loss feature with ten corrected passive T1-flux maps.

Each completed pass checkpoints the existing five-point one-stop CSV.
No pump is applied. The wider 4.060–4.170-GHz grid captures movement
beyond the shorter swap-hold scouts, and the finite series stops after
ten passes or 25 minutes, whichever limit is reached between passes.
"""

import argparse
import json
from pathlib import Path

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSPumpProbeAdaptiveParkPump as adaptive,
    TLSPumpProbeLocalizer as localizer,
)


def parameters():
    return {**adaptive.scout_parameters(phase="pre"),
            "freq_min_ghz": 4.060,
            "freq_max_ghz": 4.170,
            "freq_step_mhz": 1.0,
            "shots_per_condition": 350,
            "reset_mode": "passive",
            "max_runs": 10,
            "max_consecutive_failures": 1,
            "wall_clock_duration_min": 25.0,
            "output_suffix": "TLS_Spectral_Diffusion_Monitor_4p060_4p170"}


def plan():
    p = parameters()
    return {"hardware_access": False,
            "purpose": "measure loss-frequency drift before another fixed-frequency "
                       "swap or pump test",
            "frequency_count": (round(1000.0 *
                                      (p["freq_max_ghz"] - p["freq_min_ghz"])
                                      / p["freq_step_mhz"]) + 1),
            "condition_count": 2 + len(p["decay_delays_us"]),
            "planned_passes": p["max_runs"],
            "parameters": p}


def run(*, data_root=localizer.DATA_ROOT, correction_json=None):
    path = localizer.run(
        data_root=data_root, correction_json=correction_json,
        parameter_overrides=parameters())
    print(f"[spectral-diffusion] one-stop CSV={path}", flush=True)
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--data-root", type=Path, default=localizer.DATA_ROOT)
    parser.add_argument("--correction-json", type=Path)
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(plan(), indent=2))
    else:
        run(data_root=args.data_root, correction_json=args.correction_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
