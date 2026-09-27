"""Compare sham/pump/sham over the whole moving q3 loss band.

A passive 81-point pre-scout chooses the current loss coordinate. Three
otherwise identical 41-point scans then measure a 40-MHz-wide band around it:
zero-gain sham, 15-us park-bias pump at the selected frequency, zero-gain sham.
A passive post-scout checks the loss after the comparison. The full-band
comparison is less sensitive to a few-MHz shift of the loss coordinate than
the previous three-frequency arms. No active reset is used. A changed loss
profile alone is not proof of TLS saturation.
"""

import argparse
import json
from pathlib import Path

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSPumpProbeAdaptiveParkPump as adaptive,
    TLSPumpProbeLocalizer as localizer,
    TLSPumpProbePassiveParkPump as park_pump,
)


BAND_HALF_WIDTH_MHZ = 20.0
ARM_GAINS = (0, 3000, 0)


def scout_parameters(*, phase):
    return {
        **adaptive.scout_parameters(phase=phase),
        "output_suffix": f"TLS_PumpProbe_Band_Scout_{phase}",
    }


def band_parameters(*, center_ghz):
    center = round(float(center_ghz), 3)
    return {
        **park_pump.parameters(center_ghz=center),
        "freq_min_ghz": round(center - BAND_HALF_WIDTH_MHZ / 1000.0, 3),
        "freq_max_ghz": round(center + BAND_HALF_WIDTH_MHZ / 1000.0, 3),
        "freq_step_mhz": 1.0,
        "shots_per_condition": 350,
        "output_suffix": (
            "TLS_PumpProbe_Band_" + f"{center:.3f}".replace(".", "p")
        ),
    }


def plan():
    return {
        "hardware_access": False,
        "scout_range_ghz": [4.090, 4.170],
        "scout_frequencies": 81,
        "band_half_width_mhz": BAND_HALF_WIDTH_MHZ,
        "band_frequencies": 41,
        "band_step_mhz": 1.0,
        "band_shots_per_condition": 350,
        "arm_gains": list(ARM_GAINS),
        "pump_us": 15.0,
        "pump_location": "q3 parked near 4.367 GHz",
        "pump_frequency": "selected from the pre-scout",
        "conditions": ["P0", "P1", "Ps_2us", "Ps_10us", "Ps_25us"],
        "note": __doc__,
    }


def run(*, data_root=localizer.DATA_ROOT, correction_json=None):
    pre_path = localizer.run(
        data_root=data_root, correction_json=correction_json,
        parameter_overrides=scout_parameters(phase="pre"))
    selected = adaptive.select_loss_feature(adaptive.read_scout(pre_path))
    center = selected["center_ghz"]
    print(f"[band-pump] pre-scout={pre_path}; selected={center:.3f} GHz; "
          f"depth={selected['depth']:.3f}", flush=True)
    base = band_parameters(center_ghz=center)
    outputs = []
    for index, gain in enumerate(ARM_GAINS, start=1):
        label = "pump" if gain else "sham"
        overrides = {
            **base,
            "park_pump_frequency_mhz": 1000.0 * center,
            "park_pump_gain": gain,
            "park_pump_us": 15.0,
            "output_suffix": f"{base['output_suffix']}_{index:02d}_{label}",
        }
        print(f"[band-pump] arm {index}/3: {label} gain={gain}; "
              f"band={base['freq_min_ghz']:.3f}.."
              f"{base['freq_max_ghz']:.3f} GHz", flush=True)
        outputs.append(localizer.run(
            data_root=data_root, correction_json=correction_json,
            parameter_overrides=overrides))
    post_path = localizer.run(
        data_root=data_root, correction_json=correction_json,
        parameter_overrides=scout_parameters(phase="post"))
    try:
        post_selected = adaptive.select_loss_feature(
            adaptive.read_scout(post_path))
        print(f"[band-pump] post-scout={post_path}; "
              f"selected={post_selected['center_ghz']:.3f} GHz", flush=True)
    except ValueError as exc:
        post_selected = None
        print(f"[band-pump] post-scout={post_path}; {exc}", flush=True)
    return {
        "pre_scout": pre_path,
        "selected": selected,
        "arms": outputs,
        "post_scout": post_path,
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
