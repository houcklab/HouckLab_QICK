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


def parameters(*, center_ghz=4.140):
    center_ghz = float(center_ghz)
    return {
        **wide.parameters(),
        "freq_min_ghz": round(center_ghz - 0.002, 3),
        "freq_max_ghz": round(center_ghz + 0.002, 3),
        "freq_step_mhz": 2.0,
        "shots_per_condition": 500,
        "output_suffix": (
            "TLS_PumpProbe_Passive_ParkPump_"
            + f"{center_ghz:.3f}".replace(".", "p")
        ),
    }


def arms(*, center_ghz=4.140):
    frequency = round(1000.0 * float(center_ghz), 3)
    return [
        {"label": "sham", "frequency_mhz": frequency, "gain": 0},
        {"label": "resonant", "frequency_mhz": frequency, "gain": 3000},
        {"label": "minus20", "frequency_mhz": frequency - 20.0, "gain": 3000},
        {"label": "sham", "frequency_mhz": frequency, "gain": 0},
        {"label": "plus20", "frequency_mhz": frequency + 20.0, "gain": 3000},
        {"label": "resonant", "frequency_mhz": frequency, "gain": 3000},
        {"label": "sham", "frequency_mhz": frequency, "gain": 0},
    ]


def plan(*, center_ghz=4.140):
    p = parameters(center_ghz=center_ghz)
    return {
        "hardware_access": False,
        "microwave_pump_enabled": True,
        "pump_location": "q3 parked near 4.367 GHz",
        "probe_frequency_ghz": [p["freq_max_ghz"], float(center_ghz),
                                p["freq_min_ghz"]],
        "pump_us": 15.0,
        "arms": arms(center_ghz=center_ghz),
        "shots_per_condition": p["shots_per_condition"],
        "conditions": ["P0", "P1", "Ps_2us", "Ps_10us", "Ps_25us"],
        "parameters": p,
        "note": __doc__,
    }


def run(*, data_root=localizer.DATA_ROOT, correction_json=None,
        center_ghz=4.140):
    p = parameters(center_ghz=center_ghz)
    schedule = arms(center_ghz=center_ghz)
    outputs = []
    for index, arm in enumerate(schedule, start=1):
        overrides = {
            **p,
            "park_pump_frequency_mhz": arm["frequency_mhz"],
            "park_pump_gain": arm["gain"],
            "park_pump_us": 15.0,
            "output_suffix": f"{p['output_suffix']}_{index:02d}_{arm['label']}",
        }
        print(f"[park-pump] arm {index}/{len(schedule)}: {arm['label']} "
              f"{arm['frequency_mhz']:.1f} MHz gain={arm['gain']}", flush=True)
        outputs.append(localizer.run(
            data_root=data_root, correction_json=correction_json,
            parameter_overrides=overrides))
    return outputs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--data-root", type=Path, default=localizer.DATA_ROOT)
    parser.add_argument("--correction-json", type=Path)
    parser.add_argument("--center-ghz", type=float, default=4.140)
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(plan(center_ghz=args.center_ghz), indent=2))
    else:
        run(data_root=args.data_root, correction_json=args.correction_json,
            center_ghz=args.center_ghz)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
