"""q3 higher-gain park pump with ground and excited target probes.

The pre-scout selects a fresh localized loss feature. Eight short passive scans
then compare gain 0, 3000, and 6000 at the same 15-us park-bias pulse. Each arm
measures both a ground-prepared and an excited-prepared qubit after 25 us at
the target, using frequency-matched P0/P1 short-hold references. The ground
scan saves raw upward excitation and deliberately does not report a T1 fit.
A post-scout checks feature position. No active reset or production default is
changed. A pump-specific effect requires target localization and later
off-resonant/power controls before identifying TLS saturation.
"""

import argparse
import json
from pathlib import Path

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSPumpProbeAdaptiveParkPump as adaptive,
    TLSPumpProbeLocalizer as localizer,
    TLSPumpProbeWidePassiveScan as wide,
)


DEFAULT_PUMP_GAIN = 6000
MAX_PUMP_GAIN = 6000
COMPARISON_PUMP_GAIN = 3000
PUMP_US = 15.0
ARMS = (("sham", 0, "g"), ("sham", 0, "e"),
        ("gain3000", COMPARISON_PUMP_GAIN, "g"),
        ("gain3000", COMPARISON_PUMP_GAIN, "e"),
        ("high", None, "g"), ("high", None, "e"),
        ("sham", 0, "g"), ("sham", 0, "e"))


def validate_gain(gain):
    gain = int(gain)
    if not COMPARISON_PUMP_GAIN < gain <= MAX_PUMP_GAIN:
        raise ValueError(f"pump gain must be {COMPARISON_PUMP_GAIN + 1}..{MAX_PUMP_GAIN}")
    return gain


def scout_parameters(*, phase):
    return {
        **adaptive.scout_parameters(phase=phase),
        "output_suffix": f"TLS_PumpProbe_HighGain_Scout_{phase}",
    }


def probe_parameters(*, center_ghz, state):
    if state not in ("g", "e"):
        raise ValueError("probe state must be 'g' or 'e'")
    center = round(float(center_ghz), 3)
    return {
        **wide.parameters(),
        "freq_min_ghz": round(center - 0.020, 3),
        "freq_max_ghz": round(center + 0.020, 3),
        "freq_step_mhz": 2.0,
        "shots_per_condition": 350,
        "decay_delays_us": [25.0],
        "reference_hold_us": 0.1,
        "survival_probe_state": state,
    }


def plan(*, pump_gain=DEFAULT_PUMP_GAIN):
    gain = validate_gain(pump_gain)
    return {
        "hardware_access": False,
        "reset_mode": "passive",
        "pump_location": "q3 parked near 4.367 GHz",
        "pump_gain": gain,
        "comparison_gain": COMPARISON_PUMP_GAIN,
        "pump_gain_cap": MAX_PUMP_GAIN,
        "pump_us": PUMP_US,
        "pump_frequency": "current loss coordinate selected by pre-scout",
        "probe_states": ["g", "e"],
        "probe_hold_us": 25.1,
        "reference_hold_us": 0.1,
        "probe_band_half_width_mhz": 20.0,
        "probe_step_mhz": 2.0,
        "probe_frequencies": 21,
        "shots_per_condition": 350,
        "arm_order": [f"{label}_{state}" for label, _, state in ARMS],
        "note": __doc__,
    }


def run(*, data_root=localizer.DATA_ROOT, correction_json=None,
        pump_gain=DEFAULT_PUMP_GAIN):
    gain = validate_gain(pump_gain)
    pre_path = localizer.run(
        data_root=data_root, correction_json=correction_json,
        parameter_overrides=scout_parameters(phase="pre"))
    selected = adaptive.select_loss_feature(adaptive.read_scout(pre_path))
    center = selected["center_ghz"]
    center_tag = f"{center:.3f}".replace(".", "p")
    print(f"[high-gain-bidirectional] pre-scout={pre_path}; "
          f"selected={center:.3f} GHz depth={selected['depth']:.3f}", flush=True)
    paths = []
    for index, (label, arm_gain, state) in enumerate(ARMS, start=1):
        overrides = {
            **probe_parameters(center_ghz=center, state=state),
            "park_pump_frequency_mhz": 1000.0 * center,
            "park_pump_gain": gain if arm_gain is None else arm_gain,
            "park_pump_us": PUMP_US,
            "output_suffix": (
                f"TLS_PumpProbe_HighGain_Bidirectional_{center_tag}_"
                f"{index:02d}_{label}_{state}"
            ),
        }
        print(f"[high-gain-bidirectional] arm {index}/{len(ARMS)} "
              f"{label} {state}, gain={overrides['park_pump_gain']}", flush=True)
        output = localizer.run(
            data_root=data_root, correction_json=correction_json,
            parameter_overrides=overrides)
        if output is None:
            raise RuntimeError(f"arm {index} completed without a CSV output path")
        paths.append(output)
    post_path = localizer.run(
        data_root=data_root, correction_json=correction_json,
        parameter_overrides=scout_parameters(phase="post"))
    try:
        post_selected = adaptive.select_loss_feature(
            adaptive.read_scout(post_path))
        print(f"[high-gain-bidirectional] post-scout={post_path}; "
              f"selected={post_selected['center_ghz']:.3f} GHz", flush=True)
    except ValueError as exc:
        post_selected = None
        print(f"[high-gain-bidirectional] post-scout={post_path}; {exc}",
              flush=True)
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
    parser.add_argument("--pump-gain", type=int, default=DEFAULT_PUMP_GAIN)
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(plan(pump_gain=args.pump_gain), indent=2))
    else:
        run(data_root=args.data_root, correction_json=args.correction_json,
            pump_gain=args.pump_gain)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
