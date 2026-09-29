"""Calibrate the q3 pulse at the 4.288-GHz site of the failed echo pilot.

This is a single-site drive calibration, not a TLS locator or echo scan.
"""

import argparse
import json

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSParkPi2Calibration as calibration,
)


TARGET_GHZ = 4.288


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--target-ghz", type=float, default=TARGET_GHZ)
    parser.add_argument("--data-root")
    parser.add_argument("--correction-json")
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(calibration.plan(target_ghz=args.target_ghz),
                         indent=2))
        return 0
    calibration.run(data_root=args.data_root,
                    correction_json=args.correction_json,
                    target_ghz=args.target_ghz)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
