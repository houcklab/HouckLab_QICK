"""Find a qubit-mediated loading time for the current q3 loss feature.

This is the first stage of an on-target pump-probe sequence. The existing
five-condition experiment prepares one qubit excitation at park, moves the
qubit to the freshly selected loss coordinate, waits a controlled time, then
returns and reads out the qubit. The early-time frequency map can reveal a
swap minimum or coherent return; the longer holds characterize incoherent
transfer. There is no parked microwave tone or active reset. The earliest
panel is repeated after the others so that a drifting feature or reference
cannot masquerade as a time-domain oscillation. A later run will use the
measured loading time and add a separate signed return probe.
"""

import argparse
import json
from pathlib import Path

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSPumpProbeAdaptiveParkPump as adaptive,
    TLSPumpProbeLocalizer as localizer,
    TLSPumpProbeWidePassiveScan as wide,
)


PANELS = (
    ("early", (0.25, 0.5, 1.0)),
    ("middle", (1.5, 2.5, 4.0)),
    ("late", (6.0, 10.0, 20.0)),
    ("early_repeat", (0.25, 0.5, 1.0)),
)
REFERENCE_HOLD_US = 0.1


def scout_parameters(*, phase):
    return {
        **adaptive.scout_parameters(phase=phase),
        "output_suffix": f"TLS_PumpProbe_OnTargetTiming_Scout_{phase}",
    }


def panel_parameters(*, center_ghz, label, delays_us):
    center = round(float(center_ghz), 3)
    if not 3.8 <= center <= 4.3:
        raise ValueError("selected feature lies outside the surveyed q3 range")
    center_tag = f"{center:.3f}".replace(".", "p")
    return {
        **wide.parameters(),
        "freq_min_ghz": round(center - 0.012, 3),
        "freq_max_ghz": round(center + 0.012, 3),
        "freq_step_mhz": 1.0,
        "shots_per_condition": 400,
        "decay_delays_us": list(delays_us),
        "reference_hold_us": REFERENCE_HOLD_US,
        "output_suffix": f"TLS_PumpProbe_OnTargetTiming_{center_tag}_{label}",
    }


def plan():
    return {
        "hardware_access": False,
        "reset_mode": "passive",
        "pump_mechanism": "qubit excitation plus target flux excursion",
        "microwave_tone_enabled": False,
        "scout_frequencies": 81,
        "probe_frequencies": 25,
        "probe_step_mhz": 1.0,
        "shots_per_condition": 400,
        "reference_hold_us": REFERENCE_HOLD_US,
        "panels": [label for label, _ in PANELS],
        "additional_delays_us": [list(delays) for _, delays in PANELS],
        "actual_target_holds_us": [
            [REFERENCE_HOLD_US + delay for delay in delays]
            for _, delays in PANELS
        ],
        "note": __doc__,
    }


def run(*, data_root=localizer.DATA_ROOT, correction_json=None):
    pre_path = localizer.run(
        data_root=data_root, correction_json=correction_json,
        parameter_overrides=scout_parameters(phase="pre"))
    selected = adaptive.select_loss_feature(adaptive.read_scout(pre_path))
    center = selected["center_ghz"]
    print(f"[on-target-timing] pre-scout={pre_path}; "
          f"selected={center:.3f} GHz depth={selected['depth']:.3f}",
          flush=True)
    paths = []
    for label, delays in PANELS:
        parameters = panel_parameters(
            center_ghz=center, label=label, delays_us=delays)
        print(f"[on-target-timing] {label}: target holds "
              f"{[REFERENCE_HOLD_US + delay for delay in delays]} us",
              flush=True)
        output = localizer.run(
            data_root=data_root, correction_json=correction_json,
            parameter_overrides=parameters)
        if output is None:
            raise RuntimeError(f"{label} completed without a CSV output path")
        paths.append(output)
    post_path = localizer.run(
        data_root=data_root, correction_json=correction_json,
        parameter_overrides=scout_parameters(phase="post"))
    try:
        post_selected = adaptive.select_loss_feature(
            adaptive.read_scout(post_path))
        print(f"[on-target-timing] post-scout={post_path}; "
              f"selected={post_selected['center_ghz']:.3f} GHz", flush=True)
    except ValueError as exc:
        post_selected = None
        print(f"[on-target-timing] post-scout={post_path}; {exc}", flush=True)
    return {
        "pre_scout": pre_path, "selected": selected,
        "panels": paths, "post_scout": post_path,
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
