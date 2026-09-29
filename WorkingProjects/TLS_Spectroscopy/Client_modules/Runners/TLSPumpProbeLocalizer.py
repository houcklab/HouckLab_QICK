"""First pump/probe stage: three full-band q3 scans, with no conditioning pump.

From the repository root in the measurement PC's QICK Python environment:
    python -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeLocalizer --plan
    python -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeLocalizer --run

Run only after the other q3 acquisition has stopped. The existing five-point
runner calibrates native reset and checkpoints one combined CSV after each pass.
Outputs retain the usual q3/date folders, with TLS_PumpProbe_Localizer in the name.
The 30-minute series limit is checked between passes; three completed passes
normally end the run sooner. Calibration and a pass in progress can exceed it.
"""

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import subprocess


DATA_ROOT = Path("Z:/FluxTeam/Data/FTT02_AlOxJJ_2026_08_28/RFSOC")
CORRECTION_RELATIVE = Path(
    "q3/q3_2026_09_15/"
    "q3_05_42_07_Qubit_Flux_Step_Response_CLOSED_LOOP_RESIDUAL_075_CANDIDATE.json"
)
# Exact artifact used by the completed September 24 return/readout audit.
CORRECTION_SHA256 = "7f4884732d5a66dcf280119b075a003827206c28f5377199a96dec7542b60b82"


def parameters():
    return {
        "shots_per_condition": 300,
        "decay_delays_us": [25.0, 60.0, 100.0],
        "reference_hold_us": 2.0,
        "freq_min_ghz": 3.9,
        "freq_max_ghz": 4.3,
        "freq_step_mhz": 0.5,
        "dc_min": -20550,
        "dc_max": -11800,
        "max_runs": 3,
        "wall_clock_duration_min": 30.0,
        "sync_enabled": False,
        "reset_mode": "active",
        "apply_flux_tail_compensation": True,
        "flux_settle_us": 0.5,
        "flux_predistortion_return_prefix_us": 0.5,
        "flux_predistortion_recovery_us": 40.0,
        "flux_predistortion_overlap_payload_readout": False,
        "readout_thermalization_us": 10.0,
        "reverse_survival_order": False,
        "output_suffix": "TLS_PumpProbe_Localizer",
    }


def _scan_key(key):
    return key.startswith(("Q3_5PT_", "Q3_FLUXPRED_")) or key in {
        "Q3_PROTOCOL_CROSSOVER_PHASE", "Q3_FLUX_TAIL_GAIN", "Q3_CODE_COMMIT",
    }


@contextmanager
def scan_environment(correction):
    """Override prior diagnostic settings for this run, then restore them."""
    previous = {key: value for key, value in os.environ.items() if _scan_key(key)}
    for key in previous:
        os.environ.pop(key)
    try:
        try:
            commit = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=Path(__file__).resolve().parents[4],
                text=True, stderr=subprocess.DEVNULL,
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            commit = "unknown"
        os.environ.update({
            # Neutral model OFF selects the native correction path, which is ON.
            "Q3_FLUXPRED_MODE": "off",
            "Q3_FLUX_TAIL_GAIN": "1.0",
            "Q3_5PT_CORRECTION_JSON": str(correction),
            "Q3_CODE_COMMIT": commit,
        })
        yield
    finally:
        for key in list(os.environ):
            if _scan_key(key):
                os.environ.pop(key)
        os.environ.update(previous)


def checked_correction(data_root, correction_json=None):
    """Resolve and verify the shared, pinned NAS artifact before hardware imports."""
    data_root = Path(data_root)
    correction = Path(correction_json) if correction_json else data_root / CORRECTION_RELATIVE
    if not correction.is_file():
        raise FileNotFoundError(f"Required correction file unavailable: {correction}")
    if hashlib.sha256(correction.read_bytes()).hexdigest() != CORRECTION_SHA256:
        raise RuntimeError("Correction checksum differs from the September 24 audit.")
    if not data_root.is_dir():
        raise FileNotFoundError(f"NAS data directory unavailable: {data_root}")
    return correction


def run(*, data_root=DATA_ROOT, correction_json=None, parameter_overrides=None,
        announce=True):
    """Run the baseline protocol, optionally with a follow-up runner's grid."""
    p = {**parameters(), **(parameter_overrides or {})}
    data_root = Path(data_root)
    correction = checked_correction(data_root, correction_json)

    # Hardware-dependent imports occur only on the explicit --run path, after
    # checking the NAS artifact. Previewing the plan needs only the standard library.
    with scan_environment(correction):
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
            FivePointApplesToApples as runner,
            TLSSpectroscopy as tls,
        )

        if "max_runs" not in runner.P6_5PT_APPLES_TO_APPLES:
            raise RuntimeError("This checkout lacks finite-run support; update the branch.")
        if int(tls.BaseConfig["ff_park_gain"]) != -25146:
            raise RuntimeError("Park calibration differs from the planned q3 configuration.")
        tls.QUBIT = "q3"
        tls.SET_YOKO = False
        tls.outerFolder = str(data_root)
        original = runner.P6_5PT_APPLES_TO_APPLES
        runner.P6_5PT_APPLES_TO_APPLES = {**original, **p}
        try:
            if announce:
                print(f"Starting {p['output_suffix']}: {p['max_runs']} passes, "
                      f"{p['freq_min_ghz']:g}-{p['freq_max_ghz']:g} GHz, "
                      f"delays={p['decay_delays_us']} us.", flush=True)
                print(f"Native correction ON (SHA256 {CORRECTION_SHA256}); 40 us return.", flush=True)
                print(f"Output root: {data_root / 'q3'}", flush=True)
            return runner.main()
        finally:
            runner.P6_5PT_APPLES_TO_APPLES = original


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true", help="print the plan without hardware/NAS access")
    mode.add_argument("--run", action="store_true", help="acquire the three baseline scans")
    parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    parser.add_argument("--correction-json", type=Path,
                        help="relocated copy of the same checksum-verified correction")
    args = parser.parse_args(argv)
    if args.plan:
        p = parameters()
        print(json.dumps({
            "hardware_access": False,
            "parameters": p,
            "frequency_count": round(1000 * (p["freq_max_ghz"] - p["freq_min_ghz"])
                                     / p["freq_step_mhz"]) + 1,
            "data_root": str(args.data_root),
            "correction_json": str(args.correction_json or args.data_root / CORRECTION_RELATIVE),
            "correction_sha256": CORRECTION_SHA256,
        }, indent=2))
    else:
        run(data_root=args.data_root, correction_json=args.correction_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
