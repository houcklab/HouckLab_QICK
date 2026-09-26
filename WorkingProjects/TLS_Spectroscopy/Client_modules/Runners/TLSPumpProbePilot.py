"""q3 direct-microwave pump--reset--probe pilot with ground/excited probes.

Run on the measurement PC after stopping other acquisitions. This tests a
per-shot pump response, NOT persistent TLS displacement. All controls use the
same flux excursions; only the pump microwave gain/frequency changes. Pump and
probe visit the same DAC target. The nominal resonant tone uses the frozen flux
model, so it is not an independent calibration of the actual TLS frequency.

The 500-us park idle is after the probe readout; a native reset precedes the
next pump and another follows the pump. Additional recovery is zero, but actual
pump-to-probe latency includes the 40-us flux return, readout, variable feedback
reset and a timing guard after the final reset readout (20 us for this config,
including the 10-us feedback wait). Only probe IQ is recorded; total reset
latency is not measured. The actual guard is saved in per-block telemetry.
Ground probes play a zero-gain pi-length waveform. Probe holds are 2 and 10 us
(8-us increment), each with the same 0.5-us arrival and 40-us return.

--frequency-check maps microwave detuning at fixed pump amplitude/duration.
It uses four probe targets, four repeats of 400 shots, and a zero-gain sham
before and after each randomized 13-frequency pump sweep. It follows the pilot's
inconclusive response and possible extra ground-probe excitation; it is not a
power escalation or a claim of TLS suppression.

--confirmation-check tests 0/+8/-20 MHz at 4.098/4.110 GHz with eight repeats
of 400 shots. Every test has its own immediately adjacent zero-gain controls
at the same tone frequency. A fourth test is itself zero-gain (null), providing
a drift/noise check. All three blocks share comparison_id and test_condition.

--dose-check holds the probe at 4.110 GHz and tests +8/-20 MHz pumps at gains
1500/3000, plus the zero-gain null, with twelve repeats of 400 shots. Each test
is locally bracketed as above. Pump duration stays 15 us; no gain exceeds 3000.
"""

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import random
import uuid

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSPumpProbeLocalizer as localizer,
    TLSPumpProbeProtocolCheck as protocol,
)


def parameters(*, frequency_check=False, confirmation_check=False, dose_check=False):
    if sum((frequency_check, confirmation_check, dose_check)) > 1:
        raise ValueError("Choose only one pump-probe follow-up stage.")
    p = {
        "target_frequency_ghz": [4.094, 4.098, 4.100, 4.102, 4.104, 4.106, 4.110],
        "shots": 200, "repeats": 3, "order_seed": 20260926,
        "pump_gain": 3000, "pump_us": 15.0, "probe_holds_us": [2.0, 10.0],
        "inter_shot_delay_us": 500.0, "additional_recovery_us": 0.0,
        "return_us": 40.0, "dc_min": -20550, "dc_max": -11800,
        "freq_step_mhz": 2.0,
        "pump_detunings_mhz": [0.0, -20.0, 20.0], "bracket_sham": False,
        "bracket_each": False,
    }
    if frequency_check:
        p.update({
            "target_frequency_ghz": [4.098, 4.104, 4.106, 4.110],
            "shots": 400, "repeats": 4, "order_seed": 20260927,
            "pump_detunings_mhz": [-20.0, -10.0, -8.0, -6.0, -4.0, -2.0,
                                   0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 20.0],
            "bracket_sham": True,
        })
    if confirmation_check:
        p.update({
            "target_frequency_ghz": [4.098, 4.110],
            "shots": 400, "repeats": 8, "order_seed": 20260928,
            "pump_detunings_mhz": [0.0, 8.0, -20.0],
            "bracket_each": True,
        })
    if dose_check:
        p.update({
            "target_frequency_ghz": [4.110],
            "shots": 400, "repeats": 12, "order_seed": 20260929,
            "pump_detunings_mhz": [8.0, -20.0], "pump_gains": [1500, 3000],
            "bracket_each": True,
        })
    return p


def schedule(p):
    """Randomize short control blocks while completing every matched condition."""
    rng = random.Random(p["order_seed"])
    points = []
    modes = [
        ("near" if d == 0 else f"{'minus' if d < 0 else 'plus'}{abs(d):g}", d)
        for d in p["pump_detunings_mhz"]
    ]
    for repeat in range(p["repeats"]):
        targets = list(range(len(p["target_frequency_ghz"])))
        rng.shuffle(targets)
        for target in targets:
            # Keep each state/hold's microwave controls adjacent in time.
            probes = [(state, hold) for state in ("g", "e") for hold in p["probe_holds_us"]]
            rng.shuffle(probes)
            for state, hold in probes:
                if p["bracket_each"]:
                    gains = p.get("pump_gains", [p["pump_gain"]])
                    tests = [(mode, d, f"{mode}_gain{gain}" if len(gains) > 1 else mode, gain)
                             for mode, d in modes for gain in gains]
                    tests.append(("sham", 8.0, "null", 0))
                    rng.shuffle(tests)
                    controls = []
                    for mode, d, condition, gain in tests:
                        controls.extend([("sham", d, "before", condition, 0),
                                         (mode, d, "test", condition, gain),
                                         ("sham", d, "after", condition, 0)])
                elif p["bracket_sham"]:
                    controls = [(mode, d, "sweep", "", p["pump_gain"]) for mode, d in modes]
                    rng.shuffle(controls)
                    controls = [("sham", 0.0, "before", "", 0), *controls, ("sham", 0.0, "after", "", 0)]
                else:
                    controls = [("sham", 0.0, "randomized", "", 0),
                                *((mode, d, "randomized", "", p["pump_gain"]) for mode, d in modes)]
                    rng.shuffle(controls)
                for mode, detuning, position, condition, gain in controls:
                    points.append({
                        "name": f"point_{len(points):04d}", "repeat": repeat,
                        "target_index": target, "pump_mode": mode,
                        "pump_detuning_mhz": detuning, "probe_state": state,
                        "pump_gain": gain,
                        "probe_us": float(hold),
                        "control_position": position,
                        "test_condition": condition,
                        "comparison_id": f"comparison_{len(points) // 3:04d}" if p["bracket_each"] else "",
                    })
    return points


def drive_settings(entry, p):
    """Map physical gain to the acquisition API's positive nominal-gain contract."""
    sham = entry["pump_mode"] == "sham"
    # no_pump sets the waveform gain to zero inside the backend; its nominal
    # gain argument must still be positive, including for the zero-drive null.
    return {"arm": "no_pump" if sham else "pump",
            "pump_gain": p["pump_gain"] if sham else entry["pump_gain"]}


def collect_points(manifest, path, acquire):
    """Checkpoint complete raw-data references and stop on any exception."""
    for entry in manifest["points"]:
        entry.update(status="acquiring", started_at=datetime.now(timezone.utc).isoformat())
        protocol.checkpoint(path, manifest)
        try:
            entry["result"] = acquire(entry)
            entry.update(status="complete", completed_at=datetime.now(timezone.utc).isoformat())
            protocol.checkpoint(path, manifest)
        except BaseException as exc:
            entry.update(status="failed", error=f"{type(exc).__name__}: {exc}")
            manifest["status"] = "failed"
            protocol.checkpoint(path, manifest)
            raise
    manifest["status"] = "complete"
    protocol.checkpoint(path, manifest)


def json_default(value):
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def run(*, data_root=localizer.DATA_ROOT, correction_json=None, frequency_check=False,
        confirmation_check=False, dose_check=False):
    p = parameters(frequency_check=frequency_check, confirmation_check=confirmation_check,
                   dose_check=dose_check)
    data_root = Path(data_root)
    correction = localizer.checked_correction(data_root, correction_json)
    with localizer.scan_environment(correction):
        import numpy as np
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
            FivePointApplesToApples as five, TLSSpectroscopy as tls,
        )
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.ThreePointApplesToApples import _integer_dc_grid
        from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import prepare_reset_session
        from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import (
            acquire_tls_saturation_iq, classify_payload_iq,
        )

        if int(tls.BaseConfig["ff_park_gain"]) != -25146:
            raise RuntimeError("Park calibration differs from the planned q3 configuration.")
        tls.QUBIT, tls.SET_YOKO, tls.outerFolder = "q3", False, str(data_root)
        five.install_scan_calibration(tls)
        # Invert a regular grid, then select this stage's probe targets.
        full_grid = np.linspace(4.094, 4.110, 9)
        all_dc, all_realized = _integer_dc_grid(p, full_grid)
        indices = [int(np.argmin(abs(full_grid - f))) for f in p["target_frequency_ghz"]]
        dc_vec, realized = all_dc[indices], all_realized[indices]
        compensation = tls._load_correction(str(correction), str(data_root))
        kind = ("dose_check" if dose_check else "confirmation_check" if confirmation_check
                else "frequency_check" if frequency_check else "pilot")
        session_id = f"q3_pump_probe_{kind}_" + datetime.now(timezone.utc).strftime(
            "%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
        folder = data_root / "q3" / session_id
        folder.mkdir(parents=True, exist_ok=False)
        manifest_path = folder / "manifest.json"
        manifest = {
            "schema": "q3.pump-probe-pilot.v1", "session_id": session_id,
            "frequency_check": frequency_check,
            "confirmation_check": confirmation_check,
            "dose_check": dose_check,
            "status": "calibrating", "code_commit": os.environ["Q3_CODE_COMMIT"],
            "created_at": datetime.now(timezone.utc).isoformat(), "parameters": p,
            "correction_json": str(correction), "correction_sha256": localizer.CORRECTION_SHA256,
            "realized_frequency_ghz": realized.tolist(), "dc_vec": dc_vec.tolist(),
            "timing_note": __doc__,
            "points": [dict(entry, status="pending") for entry in schedule(p)],
        }
        protocol.checkpoint(manifest_path, manifest)
        print(f"[pump-probe] manifest={manifest_path}", flush=True)
        try:
            soc, soccfg = tls.makeProxy()
            reset = prepare_reset_session(
                "active", outer_folder=str(data_root), qubit="q3", base_cfg=tls.BaseConfig,
                soc=soc, soccfg=soccfg, purpose="TLSPumpProbePilot",
            )
            manifest["reset_calibration_path"] = str(reset.calibration_output)
            cfg = reset.apply(dict(tls.BaseConfig))
            cfg.update({
                "shots": p["shots"], "opx_inter_shot_delay_us": p["inter_shot_delay_us"],
                "opx_saturation_reset_before_pump": True,
                "apply_flux_tail_compensation": True, "flux_tail_compensation": compensation,
                "flux_fit_params": tls.FLUX_FIT_PARAMS, "qubit_pulse_style": "arb",
                "flux_settle_time_us": 0.5, "flux_predistortion_return_prefix_us": 0.5,
                "flux_predistortion_recovery_us": p["return_us"],
                "flux_predistortion_overlap_payload_readout": False,
                "flux_predistortion_round_trip_mode": "stateful", "readout_thermalization_us": 10.0,
            })
            five.apply_verified_feedback_timing(cfg)
            (folder / "config.json").write_text(
                json.dumps(cfg, default=json_default, indent=2) + "\n", encoding="utf-8")
            manifest["status"] = "running"
            protocol.checkpoint(manifest_path, manifest)
            summary_path = folder / "summary.csv"
            with summary_path.open("w", newline="", encoding="utf-8") as stream:
                writer = None

                def acquire(entry):
                    nonlocal writer
                    target = entry["target_index"]
                    pump_freq = float(realized[target] * 1000 + entry["pump_detuning_mhz"])
                    point_cfg = {**cfg, "opx_saturation_probe_state": entry["probe_state"]}
                    i, q, telemetry = acquire_tls_saturation_iq(
                        soc, soccfg, point_cfg, ff_gain=int(dc_vec[target]),
                        pump_frequency_mhz=pump_freq,
                        pump_us=p["pump_us"], probe_us=entry["probe_us"],
                        **drive_settings(entry, p),
                        recovery_us=p["additional_recovery_us"], shots=p["shots"],
                    )
                    raw_path = folder / f"{entry['name']}.npz"
                    # Save even an incomplete returned block before rejecting it.
                    np.savez_compressed(raw_path, i=i, q=q,
                                        read_length_cycles=telemetry["read_length_cycles"])
                    if len(i) != p["shots"] or len(q) != p["shots"]:
                        raise RuntimeError(f"Incomplete IQ block saved to {raw_path}")
                    states = classify_payload_iq(point_cfg, i, q, telemetry["read_length_cycles"])
                    result = {
                        "raw_npz": str(raw_path), "P_excited": float(np.mean(states)),
                        "excited_count": int(np.sum(states)), "shots": len(i),
                        "I_mean": float(np.mean(i)), "Q_mean": float(np.mean(q)),
                        "target_frequency_ghz": p["target_frequency_ghz"][target],
                        "realized_frequency_ghz": float(realized[target]), "dc_gain": int(dc_vec[target]),
                        "pump_frequency_mhz": pump_freq,
                        "effective_pump_gain": entry["pump_gain"],
                    }
                    row = {k: entry[k] for k in ("name", "repeat", "target_index", "pump_mode",
                                                "pump_detuning_mhz", "probe_state", "probe_us",
                                                "control_position", "test_condition", "comparison_id", "started_at")}
                    row.update(result)
                    if writer is None:
                        writer = csv.DictWriter(stream, fieldnames=list(row))
                        writer.writeheader()
                    writer.writerow(row)
                    stream.flush()
                    result["telemetry"] = telemetry
                    print(f"[pump-probe] {entry['name']} {result['target_frequency_ghz']:.3f} GHz "
                          f"{entry['pump_mode']} gain={result['effective_pump_gain']} "
                          f"{entry['probe_state']} {entry['probe_us']:g} us "
                          f"P={result['P_excited']:.3f}", flush=True)
                    return result

                collect_points(manifest, manifest_path, acquire)
        except BaseException as exc:
            manifest.update(status="failed", error=f"{type(exc).__name__}: {exc}")
            protocol.checkpoint(manifest_path, manifest)
            raise
        print(f"[pump-probe] complete: {summary_path}", flush=True)
        return manifest_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--run", action="store_true")
    stage = parser.add_mutually_exclusive_group()
    stage.add_argument("--frequency-check", action="store_true",
                       help="scan pump detuning with bracketing sham references")
    stage.add_argument("--confirmation-check", action="store_true",
                       help="bracket each candidate tone and a zero-gain null test")
    stage.add_argument("--dose-check", action="store_true",
                       help="test gains 1500/3000 at +8/-20 MHz with local shams and a null")
    parser.add_argument("--data-root", type=Path, default=localizer.DATA_ROOT)
    parser.add_argument("--correction-json", type=Path)
    args = parser.parse_args(argv)
    if args.plan:
        p = parameters(frequency_check=args.frequency_check, confirmation_check=args.confirmation_check,
                       dose_check=args.dose_check)
        print(json.dumps({"hardware_access": False, "parameters": p,
                          "acquisition_blocks": len(schedule(p)), "reset_calibrations": 1,
                          "pump_modes": sorted({e["pump_mode"] for e in schedule(p)}),
                          "probe_states": ["g", "e"], "timing_note": __doc__}, indent=2))
    else:
        run(data_root=args.data_root, correction_json=args.correction_json,
            frequency_check=args.frequency_check, confirmation_check=args.confirmation_check,
            dose_check=args.dose_check)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
