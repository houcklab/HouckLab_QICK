"""q3 park-tone sweep up to gain 30000 with matched frequency controls.

The qubit remains parked near 4.367 GHz during each 15-us tone. This tests
whether much more drive at the loss coordinate has a selective effect; it is
not an on-target qubit-mediated pump. A fresh passive scout chooses the loss
coordinate. Sham, gain-12000, and gain-30000 arms measure ground and excited
probes at 2 and 25 us; equal-gain tones 40 MHz to either side check broadband
effects. A final scout checks feature position. Readout-reference guards stop
the staged scan if broad excitation or reference collapse appears.
"""

import argparse
import csv
import json
import math
from pathlib import Path
from statistics import median

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSPumpProbeAdaptiveParkPump as adaptive,
    TLSPumpProbeHighGainBidirectional as high_gain,
    TLSPumpProbeLocalizer as localizer,
    TLSPumpProbeWidePassiveScan as wide,
)


SCREEN_GAIN = 12000
MAXIMUM_GAIN = 30000
PUMP_US = 15.0
PROBE_DELAYS_US = (2.0, 25.0)
_GROUPS = (
    ("sham_before", 0, 0),
    ("screen_on", SCREEN_GAIN, 0),
    ("sham_mid", 0, 0),
    ("high_minus40", MAXIMUM_GAIN, -40),
    ("high_on_a", MAXIMUM_GAIN, 0),
    ("high_plus40", MAXIMUM_GAIN, 40),
    ("high_on_b", MAXIMUM_GAIN, 0),
    ("sham_after", 0, 0),
)
ARMS = tuple(
    {"label": label, "gain": gain, "detuning_mhz": detuning, "state": state}
    for label, gain, detuning in _GROUPS for state in ("g", "e")
)


def probe_parameters(*, center_ghz, arm, index):
    center = round(float(center_ghz), 3)
    if not 3.8 <= center <= 4.3:
        raise ValueError("selected feature lies outside the surveyed q3 range")
    gain = int(arm["gain"])
    if gain not in (0, SCREEN_GAIN, MAXIMUM_GAIN):
        raise ValueError("unplanned pump gain")
    center_tag = f"{center:.3f}".replace(".", "p")
    return {
        **wide.parameters(),
        "freq_min_ghz": round(center - 0.020, 3),
        "freq_max_ghz": round(center + 0.020, 3),
        "freq_step_mhz": 2.0,
        "shots_per_condition": 350,
        "decay_delays_us": list(PROBE_DELAYS_US),
        "reference_hold_us": 0.1,
        "survival_probe_state": arm["state"],
        "park_pump_frequency_mhz": round(1000.0 * center + arm["detuning_mhz"], 3),
        "park_pump_gain": gain,
        "park_pump_us": PUMP_US,
        "output_suffix": (
            f"TLS_PumpProbe_NearMax_{center_tag}_{index:02d}_"
            f"{arm['label']}_{arm['state']}"
        ),
    }


def quality_guard(path):
    """Stop if a completed arm loses usable references or excites broadly."""
    with Path(path).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 21:
        raise RuntimeError(f"reference guard: expected 21 frequency rows, got {len(rows)}")
    try:
        p0 = [float(row["P0"]) for row in rows]
        contrast = [float(row["P1"]) - float(row["P0"]) for row in rows]
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("reference guard: missing P0/P1 data") from exc
    if not all(math.isfinite(value) for value in (*p0, *contrast)):
        raise RuntimeError("reference guard: nonfinite P0/P1 data")
    baseline = median(p0)
    separation = median(contrast)
    print(f"[near-max] references median P0={baseline:.3f}, "
          f"P1-P0={separation:.3f}", flush=True)
    if baseline > 0.20:
        raise RuntimeError("reference guard: broad excitation (median P0 > 0.20)")
    if separation < 0.15:
        raise RuntimeError("reference guard: reference contrast < 0.15")


def plan():
    return {
        "hardware_access": False,
        "reset_mode": "passive",
        "pump_location": "park, near 4.367 GHz qubit frequency",
        "maximum_gain": MAXIMUM_GAIN,
        "screen_gain": SCREEN_GAIN,
        "pump_us": PUMP_US,
        "probe_delays_us": list(PROBE_DELAYS_US),
        "probe_frequencies": 21,
        "shots_per_condition": 350,
        "arms": list(ARMS),
        "guard": "median P0 <= 0.20 and median P1-P0 >= 0.15 after every arm",
        "note": __doc__,
    }


def run(*, data_root=localizer.DATA_ROOT, correction_json=None):
    pre_path = localizer.run(
        data_root=data_root, correction_json=correction_json,
        parameter_overrides={
            **high_gain.scout_parameters(phase="pre"),
            "output_suffix": "TLS_PumpProbe_NearMax_Scout_pre",
        })
    selected = adaptive.select_loss_feature(adaptive.read_scout(pre_path))
    center = selected["center_ghz"]
    print(f"[near-max] pre-scout={pre_path}; selected={center:.3f} GHz "
          f"depth={selected['depth']:.3f}", flush=True)
    paths = []
    for index, arm in enumerate(ARMS, start=1):
        overrides = probe_parameters(center_ghz=center, arm=arm, index=index)
        print(f"[near-max] arm {index}/{len(ARMS)} {arm['label']} "
              f"{arm['state']}, gain={arm['gain']}, "
              f"detuning={arm['detuning_mhz']:+g} MHz", flush=True)
        output = localizer.run(
            data_root=data_root, correction_json=correction_json,
            parameter_overrides=overrides)
        if output is None:
            raise RuntimeError(f"arm {index} completed without a CSV output path")
        paths.append(output)
        quality_guard(output)
    post_path = localizer.run(
        data_root=data_root, correction_json=correction_json,
        parameter_overrides={
            **high_gain.scout_parameters(phase="post"),
            "output_suffix": "TLS_PumpProbe_NearMax_Scout_post",
        })
    try:
        post_selected = adaptive.select_loss_feature(
            adaptive.read_scout(post_path))
        print(f"[near-max] post-scout={post_path}; "
              f"selected={post_selected['center_ghz']:.3f} GHz", flush=True)
    except ValueError as exc:
        post_selected = None
        print(f"[near-max] post-scout={post_path}; {exc}", flush=True)
    return {
        "pre_scout": pre_path, "selected": selected,
        "arms": paths, "post_scout": post_path,
        "post_selection": post_selected,
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
        print(json.dumps(plan(), indent=2))
    else:
        run(data_root=args.data_root, correction_json=args.correction_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
