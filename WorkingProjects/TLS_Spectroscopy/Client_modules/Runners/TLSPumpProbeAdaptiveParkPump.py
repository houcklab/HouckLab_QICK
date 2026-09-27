"""Find today's q3 loss dip, pump it immediately, and check for drift.

The passive pre-scout spans 4.090..4.170 GHz in 1-MHz steps. A localized
25-us survival dip must have contrast on both frequency flanks and in both
scan directions before the pump sequence starts. The pump uses the same
park-bias protocol as TLSPumpProbePassiveParkPump, then a post-scout checks
whether the selected feature remained nearby. No active reset is used.
"""

import argparse
import csv
import json
import math
from pathlib import Path
from statistics import mean, median

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSPumpProbeLocalizer as localizer,
    TLSPumpProbePassiveParkPump as park_pump,
    TLSPumpProbeWidePassiveScan as wide,
)


def scout_parameters(*, phase):
    if phase not in ("pre", "post"):
        raise ValueError("phase must be pre or post")
    return {
        **wide.parameters(),
        "freq_min_ghz": 4.090,
        "freq_max_ghz": 4.170,
        "freq_step_mhz": 1.0,
        "shots_per_condition": 350,
        "output_suffix": f"TLS_PumpProbe_Adaptive_Scout_{phase}",
    }


def read_scout(path):
    if path is None:
        raise RuntimeError("scout completed without a CSV output path")
    with Path(path).open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    frequencies = sorted(round(float(row["target_frequency_ghz"]), 3)
                         for row in rows)
    expected = [round(4.090 + 0.001 * index, 3) for index in range(81)]
    if (len(rows) != 81 or
            len({row["wall_clock_run_index"] for row in rows}) != 1 or
            frequencies != expected):
        raise RuntimeError("adaptive scout requires one complete 81-frequency pass")
    return rows


def _survival(row, direction=""):
    suffix = f"_scan_{direction}" if direction else ""
    try:
        p0 = float(row["P0" + suffix])
        p1 = float(row["P1" + suffix])
        ps = float(row["Ps_25us" + suffix])
    except (KeyError, TypeError, ValueError):
        return math.nan
    contrast = p1 - p0
    if not all(math.isfinite(value) for value in (p0, p1, ps)) or contrast < 0.15:
        return math.nan
    return (ps - p0) / contrast


def select_loss_feature(rows):
    """Choose a three-point dip flanked by quieter regions on both sides."""
    points = sorted((float(row["target_frequency_ghz"]), row) for row in rows)
    best = None
    for frequency, _ in points:
        center = [row for f, row in points if abs(f - frequency) <= 0.00101]
        left = [row for f, row in points if 0.010 <= frequency - f <= 0.02001]
        right = [row for f, row in points if 0.010 <= f - frequency <= 0.02001]
        if len(center) != 3 or len(left) < 6 or len(right) < 6:
            continue
        depths = {}
        for direction in ("", "up", "down"):
            center_values = [_survival(row, direction) for row in center]
            left_values = [_survival(row, direction) for row in left]
            right_values = [_survival(row, direction) for row in right]
            if (not all(math.isfinite(value) for value in center_values)
                    or sum(math.isfinite(value) for value in left_values) < 5
                    or sum(math.isfinite(value) for value in right_values) < 5):
                break
            center_survival = mean(center_values)
            depths[direction] = min(
                median(value for value in left_values if math.isfinite(value)) - center_survival,
                median(value for value in right_values if math.isfinite(value)) - center_survival,
            )
        if (len(depths) != 3 or depths[""] < 0.15
                or depths["up"] < 0.08 or depths["down"] < 0.08):
            continue
        candidate = {
            "center_ghz": round(frequency, 3),
            "depth": depths[""],
            "depth_scan_up": depths["up"],
            "depth_scan_down": depths["down"],
        }
        if best is None or candidate["depth"] > best["depth"]:
            best = candidate
    if best is None:
        raise ValueError("no sufficiently localized loss in both scan directions; "
                         "pump skipped")
    return best


def plan():
    scout = scout_parameters(phase="pre")
    return {
        "hardware_access": False,
        "pre_and_post_scout_frequencies": 81,
        "scout_range_ghz": [4.090, 4.170],
        "scout_step_mhz": 1.0,
        "scout_shots_per_condition": 350,
        "pump_arms": [
            {"label": arm["label"], "detuning_mhz": arm["frequency_mhz"] - 4140.0,
             "gain": arm["gain"]}
            for arm in park_pump.arms()
        ],
        "pump_center": "selected from pre-scout; aborts if no localized dip",
        "parameters": scout,
        "note": __doc__,
    }


def run(*, data_root=localizer.DATA_ROOT, correction_json=None):
    pre_path = localizer.run(
        data_root=data_root, correction_json=correction_json,
        parameter_overrides=scout_parameters(phase="pre"))
    selected = select_loss_feature(read_scout(pre_path))
    center = selected["center_ghz"]
    print(f"[adaptive-park-pump] pre-scout={pre_path}; "
          f"selected={center:.3f} GHz depth={selected['depth']:.3f} "
          f"(up={selected['depth_scan_up']:.3f}, "
          f"down={selected['depth_scan_down']:.3f})", flush=True)
    pump_paths = park_pump.run(
        data_root=data_root, correction_json=correction_json,
        center_ghz=center)
    post_path = localizer.run(
        data_root=data_root, correction_json=correction_json,
        parameter_overrides=scout_parameters(phase="post"))
    try:
        post_selected = select_loss_feature(read_scout(post_path))
        print(f"[adaptive-park-pump] post-scout={post_path}; "
              f"selected={post_selected['center_ghz']:.3f} GHz; "
              f"shift={1000 * (post_selected['center_ghz'] - center):+.1f} MHz",
              flush=True)
    except ValueError as exc:
        post_selected = None
        print(f"[adaptive-park-pump] post-scout={post_path}; {exc}", flush=True)
    return {"pre_scout": pre_path, "pre_selection": selected,
            "pump_arms": pump_paths, "post_scout": post_path,
            "post_selection": post_selected}


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
