"""One pump-off q3 loss scan from 4.300 down to 3.800 GHz.

Use the existing matched-reference five-condition TLS scan with passive reset,
so no active-reset classifier calibration can stop the survey. A short 0.1-us
reference hold plus 2, 10, and 25-us additional survival delays samples the
early loss that identified the recent 4.110-GHz candidate. These are model
qubit-frequency coordinates, not independent TLS resonance measurements.

The target axis is descending at 2 MHz; the established acquisition alternates
up/down shot order within the pass. The same pinned native flux-tail correction,
complete 40-us return, and park readout are retained. No microwave pump runs.
One full pass is saved under a distinct experimental output suffix.
"""

import argparse
import json
from pathlib import Path

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSPumpProbeLocalizer as localizer,
)


def parameters():
    return {
        **localizer.parameters(),
        "freq_min_ghz": 3.8,
        "freq_max_ghz": 4.3,
        "freq_step_mhz": 2.0,
        "decay_delays_us": [2.0, 10.0, 25.0],
        "reference_hold_us": 0.1,
        "shots_per_condition": 250,
        "reset_mode": "passive",
        "calibrate_passive_readout": True,
        "max_runs": 1,
        "max_consecutive_failures": 1,
        "wall_clock_duration_min": 2.0,
        "sync_enabled": False,
        "output_suffix": "TLS_PumpProbe_Wide_Passive_3p8_4p3",
    }


def plan(*, data_root=localizer.DATA_ROOT, correction_json=None):
    p = parameters()
    frequencies = round(1000 * (p["freq_max_ghz"] - p["freq_min_ghz"])
                        / p["freq_step_mhz"]) + 1
    conditions = 2 + len(p["decay_delays_us"])
    return {
        "hardware_access": False,
        "microwave_pump_enabled": False,
        "scan_direction": "4.300 to 3.800 GHz",
        "frequency_count": frequencies,
        "condition_count": conditions,
        "total_measurements": frequencies * conditions * p["shots_per_condition"],
        "parameters": p,
        "data_root": str(data_root),
        "correction_json": str(correction_json or
                               Path(data_root) / localizer.CORRECTION_RELATIVE),
        "correction_sha256": localizer.CORRECTION_SHA256,
        "note": __doc__,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--data-root", type=Path, default=localizer.DATA_ROOT)
    parser.add_argument("--correction-json", type=Path)
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(plan(data_root=args.data_root,
                              correction_json=args.correction_json), indent=2))
    else:
        localizer.run(data_root=args.data_root,
                      correction_json=args.correction_json,
                      parameter_overrides=parameters())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
