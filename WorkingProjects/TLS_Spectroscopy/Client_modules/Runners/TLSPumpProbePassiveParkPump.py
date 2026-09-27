"""q3 passive-reset pump test at the September 27 loss feature near 4.140 GHz.

Apply a 15-us microwave tone while q3 is parked near 4.367 GHz, then prepare
the probe state and make the same corrected target-flux excursion as the wide
passive scan. This avoids an active-reset decision between pump and probe.
Zero-gain shams play an equal-duration pulse. The two off-resonant tones and
bracketing shams check for broadband drive effects and time drift. A response
is evidence for pump sensitivity, not on its own identification of a TLS.
"""

import argparse
import json
from pathlib import Path

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSPumpProbeLocalizer as localizer,
    TLSPumpProbeWidePassiveScan as wide,
)


def parameters():
    return {
        **wide.parameters(),
        "freq_min_ghz": 4.138,
        "freq_max_ghz": 4.142,
        "freq_step_mhz": 2.0,
        "shots_per_condition": 500,
        "output_suffix": "TLS_PumpProbe_Passive_ParkPump_4p140",
    }


def arms():
    return [
        {"label": "sham", "frequency_mhz": 4140.0, "gain": 0},
        {"label": "resonant", "frequency_mhz": 4140.0, "gain": 3000},
        {"label": "minus20", "frequency_mhz": 4120.0, "gain": 3000},
        {"label": "sham", "frequency_mhz": 4140.0, "gain": 0},
        {"label": "plus20", "frequency_mhz": 4160.0, "gain": 3000},
        {"label": "resonant", "frequency_mhz": 4140.0, "gain": 3000},
        {"label": "sham", "frequency_mhz": 4140.0, "gain": 0},
    ]


def plan():
    p = parameters()
    return {
        "hardware_access": False,
        "microwave_pump_enabled": True,
        "pump_location": "q3 parked near 4.367 GHz",
        "probe_frequency_ghz": [4.142, 4.140, 4.138],
        "pump_us": 15.0,
        "arms": arms(),
        "shots_per_condition": p["shots_per_condition"],
        "conditions": ["P0", "P1", "Ps_2us", "Ps_10us", "Ps_25us"],
        "parameters": p,
        "note": __doc__,
    }


def run(*, data_root=localizer.DATA_ROOT, correction_json=None):
    p = parameters()
    for index, arm in enumerate(arms(), start=1):
        overrides = {
            **p,
            "park_pump_frequency_mhz": arm["frequency_mhz"],
            "park_pump_gain": arm["gain"],
            "park_pump_us": 15.0,
            "output_suffix": f"{p['output_suffix']}_{index:02d}_{arm['label']}",
        }
        print(f"[park-pump] arm {index}/{len(arms())}: {arm['label']} "
              f"{arm['frequency_mhz']:.1f} MHz gain={arm['gain']}", flush=True)
        localizer.run(data_root=data_root, correction_json=correction_json,
                      parameter_overrides=overrides)


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
