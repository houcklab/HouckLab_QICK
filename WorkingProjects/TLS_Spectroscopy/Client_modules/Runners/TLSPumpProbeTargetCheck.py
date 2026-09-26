"""Resolve early-time loss around the observed q3 4.098-GHz candidate.

This follows the September 26 full-band localizer, which found a repeatable
feature near 4.098 GHz and low-loss flanks near 4.086 and 4.110 GHz. The original
25-us first survival point was already near the ground reference at the peak.
This scan measures eight shorter/longer delays across the entire local window,
so the feature can be relocated and its interaction time chosen from raw data.
No conditioning pump is applied.

Delays are additional target holds relative to the 2-us reference hold. They
are not the complete flux-excursion duration. Outbound/return timing, native
correction, park readout, and automatic active reset match the localizer.
The existing N-point backend acquires delay triplets in three program chunks;
P0/P1 are acquired in the first chunk. Checkpointed CSVs preserve all populations
and scan directions. Assess the raw curves before interpreting exponential fits.
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
        "freq_min_ghz": 4.085,
        "freq_max_ghz": 4.112,
        "freq_step_mhz": 0.25,
        "decay_delays_us": [0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0],
        "shots_per_condition": 500,
        "output_suffix": "TLS_PumpProbe_TargetCheck",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--data-root", type=Path, default=localizer.DATA_ROOT)
    parser.add_argument("--correction-json", type=Path)
    args = parser.parse_args(argv)
    p = parameters()
    if args.plan:
        print(json.dumps({
            "hardware_access": False,
            "parameters": p,
            "frequency_count": round(1000 * (p["freq_max_ghz"] - p["freq_min_ghz"])
                                     / p["freq_step_mhz"]) + 1,
            "condition_count": 2 + len(p["decay_delays_us"]),
            "delay_definition": "additional target hold beyond the 2-us matched reference",
            "program_chunks": 3,
            "reference_acquisition": "first delay chunk",
            "data_root": str(args.data_root),
            "correction_json": str(args.correction_json or args.data_root / localizer.CORRECTION_RELATIVE),
            "correction_sha256": localizer.CORRECTION_SHA256,
        }, indent=2))
    else:
        localizer.run(data_root=args.data_root, correction_json=args.correction_json,
                      parameter_overrides=p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
