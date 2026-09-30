"""First dense two-delay Hahn screen: 4.250–4.300 GHz in 0.5-MHz steps.

Each resident hardware cycle contains twelve independent, passively relaxed
subshots: short echo, long echo, and a late-pulse control at four analysis
phases. This is a coherence-contrast screen, not an intrinsic T2 measurement.
Reference brackets, a repeated anchor, and an individual-program comparison
make this first use of batching reviewable. No T1 scout or site selection.
"""

import argparse
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace
import uuid

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSEchoFastSquarePilot as fast,
    TLSEchoFocusedTrace as focused,
    TLSEchoRefocusProgram as refocus,
    TLSEchoSquareMap as square,
    TLSPumpProbeLocalizer as localizer,
)

SHOTS = 200
REFERENCE_SHOTS = 400
REFERENCE_EVERY = 10
ANCHOR_GHZ = 4.288


def frequency_grid():
    return tuple(value / 1_000_000 for value in range(4_300_000, 4_249_999, -500))


def site_key(index, frequency):
    return f"site{index:03d}_{round(frequency * 1_000_000)}kHz"


def total_readouts():
    points = len(frequency_grid())
    brackets = (points + REFERENCE_EVERY - 1) // REFERENCE_EVERY + 1
    return (points + 3) * SHOTS * 12 + 12 * SHOTS + brackets * 2 * REFERENCE_SHOTS


def _progress_bar(enabled):
    from tqdm import tqdm
    return tqdm(total=total_readouts(), desc="Echo screen", unit="readout",
                disable=not enabled, dynamic_ncols=True, mininterval=.25,
                bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} readouts "
                           "[{elapsed} elapsed, ETA {remaining}]{postfix}")


def plan():
    return {"hardware_access": False, "frequency_min_ghz": 4.250,
            "frequency_max_ghz": 4.300, "frequency_step_mhz": .5,
            "frequency_count": len(frequency_grid()), "scan_order": "descending",
            "shots_per_condition": SHOTS, "conditions_per_cycle": 12,
            "total_readouts": total_readouts(),
            "echo_elapsed_us": [.35, 1.35], "phase_cycle_deg": [0, 90, 180, 270],
            "late_pulse_control_elapsed_us": 1.35,
            "reference_every_points": REFERENCE_EVERY,
            "reference_shots_per_state": REFERENCE_SHOTS,
            "anchor_ghz": ANCHOR_GHZ, "anchor_repeats": 3,
            "individual_program_bridge_conditions": 12,
            "reset_mode": "passive", "relax_us_per_subshot": 500.,
            "corrected_return_us": 40., "t1_scans": None,
            "full_decay_fit": False, "metric": "long/short phase-cycle visibility",
            "terminal": "one progress bar with elapsed time, ETA and acquisition stage; --quiet disables it",
            "estimated_runtime_minutes": [4, 7]}


@contextmanager
def _hardware_session(data_root, correction):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
        FivePointApplesToApples as five,
        TLSEchoFewPointProgram as batch,
        TLSPumpProbeResidentDrive as resident,
        TLSPumpProbeWidePassiveScan as wide,
        TLSSpectroscopy as tls,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.ThreePointApplesToApples import _integer_dc_grid
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import (
        _block_timeout_s, _run_program, runtime_bundle,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import ProductionResetSession

    source_path = data_root / "q3" / square.SOURCE_SESSION / "manifest.json"
    square.validate_source(json.loads(source_path.read_text(encoding="utf-8")))
    with localizer.scan_environment(correction):
        tls.QUBIT, tls.SET_YOKO, tls.outerFolder = "q3", False, str(data_root)
        five.install_scan_calibration(tls)
        base = ProductionResetSession.passive().apply(tls.BaseConfig)
        five.apply_verified_feedback_timing(base)
        if int(base["ff_park_gain"]) != -25146:
            raise RuntimeError("q3 park gain differs from verified setting")
        frequencies = tuple(dict.fromkeys((*frequency_grid(), ANCHOR_GHZ)))
        dc, realized = _integer_dc_grid({**wide.parameters(), "freq_step_mhz": .5},
                                       np.asarray(frequencies), tls)
        dc_lookup = {f: int(gain) for f, gain in zip(frequencies, dc)}
        if len(set(dc_lookup.values())) != len(frequencies):
            raise ValueError("dense frequency grid contains duplicate realized DAC settings")
        base.update({"apply_flux_tail_compensation": True,
                     "flux_tail_compensation": tls._load_correction(str(correction), str(data_root)),
                     "flux_fit_params": tls.FLUX_FIT_PARAMS,
                     "flux_settle_time_us": .5,
                     "flux_predistortion_return_prefix_us": .5,
                     "flux_predistortion_recovery_us": 40.,
                     "flux_predistortion_overlap_payload_readout": False,
                     "flux_predistortion_round_trip_mode": "stateful",
                     "readout_thermalization_us": 10., "qubit_pulse_style": "arb",
                     "do_ff": True, "opx_reset_scheme": "none",
                     "opx_resident_dmem_stream": True, "opx_inter_shot_delay_us": 500.})
        batch_class = batch.make_program(resident.ResidentDriveProgram)
        single_class = refocus.make_decay_program(resident.ResidentDriveProgram)
        control_class = fast.make_program(resident.ResidentDriveProgram)
        soc, soccfg = tls.makeProxy()
        bundle = runtime_bundle(base)

        def build(frequency, kind, shots, condition=None):
            arm = {"flux_ghz": frequency, "drive_mhz": 1000*frequency + square.DRIVE_OFFSET_MHZ,
                   "gain": square.GAIN_DAC, "reference_state": None,
                   "preparation_state": "g", "pre_drive_us": focused.PRE_US,
                   "post_drive_us": focused.POST_US, "shots": shots}
            cfg = resident.arm_config(base, arm, dc_lookup)
            cfg.update({"refocus_elapsed_us": 1.35, "refocus_sequence": "hahn_y",
                        "echo_phase_deg": 0,
                        "ff_hold": focused.PRE_US + focused.POST_US + 1.35 + square.PI2_US + .01})
            if kind == "batch":
                cls = batch_class
            elif kind == "individual":
                cfg.update({"refocus_elapsed_us": condition["elapsed_us"],
                            "refocus_sequence": condition["kind"],
                            "echo_phase_deg": condition["phase_deg"]})
                cls = single_class
            elif kind in ("ground", "excited"):
                cfg.update({"fast_pulse_us": square.PI_US, "fast_second_phase_deg": None,
                            "opx_resident_gain": 0 if kind == "ground" else square.GAIN_DAC,
                            "ff_hold": focused.PRE_US + focused.POST_US + square.PI_US + .01})
                cls = control_class
            else:
                raise ValueError("unknown few-point acquisition kind")
            return cls(soccfg, cfg, bundle.payload, bundle.loop)

        def acquire(program, shots, subshots):
            records = _run_program(soc, program,
                max(30., _block_timeout_s(program.cfg, shots*subshots)),
                program.cfg, total_shots=shots)
            return batch.records_iq(records) if subshots == 12 else resident.record_iq(records)

        # Compile the actual endpoint waveforms before any acquisition.
        for frequency in (frequencies[0], frequencies[-1], ANCHOR_GHZ):
            build(frequency, "batch", SHOTS)
        yield SimpleNamespace(build=build, acquire=acquire,
            realized_frequency=dict(zip(frequencies, map(float, realized))),
            metadata={"board_configuration": focused.json_safe(soc.get_cfg()),
                      "effective_base_config": focused.json_safe(base),
                      "source_manifest": str(source_path),
                      "source_file_sha256": focused.source_file_sha256([
                          __file__, batch.__file__, refocus.__file__, resident.__file__,
                          fast.__file__, square.__file__, ff_pulse.__file__])})


def _reference_stability(before, after):
    g0, e0 = [np.mean(before[state]) for state in ("ground", "excited")]
    g1, e1 = [np.mean(after[state]) for state in ("ground", "excited")]
    if not np.isfinite([g0, e0, g1, e1]).all():
        return {"valid": False, "reason": "nonfinite reference centroid"}
    d0, d1 = e0-g0, e1-g1
    scale = max(abs(d0), abs(d1))
    if min(abs(d0), abs(d1)) <= 0 or not np.isfinite(scale):
        return {"valid": False, "reason": "unresolved reference separation"}
    cosine = float(np.real(d0*np.conj(d1))/(abs(d0)*abs(d1)))
    movement = float(max(abs(g1-g0), abs(e1-e0))/scale)
    ratio = float(abs(d1)/abs(d0))
    return {"valid": bool(cosine >= .98 and movement <= .20 and .75 <= ratio <= 1.25),
            "axis_cosine": cosine, "center_movement_over_separation": movement,
            "separation_ratio": ratio}


def _write_csv(path, sites):
    fields = ("frequency_ghz", "realized_frequency_ghz", "valid", "ratio",
              "ratio_ci95_low", "ratio_ci95_high", "raw_ratio", "short_visibility",
              "long_visibility", "late_visibility", "status", "reasons")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for point in sites:
            a = point["analysis"]
            interval = a.get("ratio_ci95") or [None, None]
            writer.writerow({"frequency_ghz": point["frequency_ghz"],
                "realized_frequency_ghz": point["realized_frequency_ghz"],
                "valid": a["valid"], "ratio": a.get("ratio"),
                "ratio_ci95_low": interval[0], "ratio_ci95_high": interval[1],
                "raw_ratio": a.get("raw_ratio"),
                **{f"{group}_visibility": a["groups"][group]["visibility"] for group in ("short", "long", "late")},
                "status": a["status"], "reasons": "; ".join(a.get("reasons", []))})


def run(*, data_root=None, correction_json=None, show_progress=True):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
        TLSDualTransitionLoss as dual,
        TLSEchoFewPointProgram as batch,
        TLSEchoFewPointAnalysis as analysis,
    )
    data_root = Path(data_root or localizer.DATA_ROOT)
    correction = localizer.checked_correction(data_root, correction_json)
    session = "q3_echo_few_point_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    folder = data_root / "q3" / session
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "program_configs").mkdir()
    path = folder / "manifest.json"
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[4], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
    manifest = {"schema": "q3.echo-few-point.v1", "session_id": session,
                "status": "running", "code_commit": commit, "plan": plan(),
                "started_at_utc": datetime.now(timezone.utc).isoformat(),
                "correction_json": str(correction), "correction_sha256": localizer.CORRECTION_SHA256,
                "sites": [], "anchors": [], "references": [], "acquisitions": [],
                "summary_csv": str(folder / "contrast_vs_frequency.csv")}
    dual.checkpoint(path, manifest)
    progress = _progress_bar(show_progress)
    completed_sites = 0
    try:
        progress.set_postfix_str("setup; 0/101 frequencies")
        with _hardware_session(data_root, correction) as hw:
            manifest["hardware_metadata"] = hw.metadata
            manifest["analysis_source_sha256"] = focused.source_file_sha256([analysis.__file__])
            dual.checkpoint(path, manifest)

            def measure(label, frequency, kind, shots, condition=None):
                nonlocal completed_sites
                stage = (f"{frequency:.4f} GHz" if label.startswith("site") else
                         "readout reference" if kind in ("ground", "excited") else
                         "pulse comparison" if kind == "individual" else
                         label.replace("_", " "))
                progress.set_postfix_str(f"{stage}; {completed_sites}/101 frequencies")
                program = hw.build(frequency, kind, shots, condition=condition)
                config_path = folder / "program_configs" / (label + ".json")
                config_path.write_text(json.dumps(focused.json_safe(program.cfg), indent=2,
                                                   allow_nan=False) + "\n", encoding="utf-8")
                raw_path = folder / (label + ".npz")
                record = {"label": label, "frequency_ghz": frequency, "kind": kind,
                          "shots": shots, "condition": condition,
                          "program_config_json": str(config_path), "raw_npz": str(raw_path),
                          "started_at_utc": datetime.now(timezone.utc).isoformat(), "status": "running"}
                manifest["acquisitions"].append(record)
                dual.checkpoint(path, manifest)
                start = time.monotonic()
                try:
                    iq = np.asarray(hw.acquire(program, shots, 12 if kind == "batch" else 1), dtype=complex)
                    np.savez_compressed(raw_path, iq=iq)
                    expected = (shots, 12) if kind == "batch" else (shots,)
                    record["received_shape"] = list(iq.shape)
                    if iq.shape != expected:
                        record["status"] = "incomplete"
                        raise RuntimeError(f"incomplete few-point acquisition: expected {expected}, got {iq.shape}")
                    record["status"] = "complete"
                    if label.startswith("site"):
                        completed_sites += 1
                    progress.set_postfix_str(f"{stage}; {completed_sites}/101 frequencies", refresh=False)
                    progress.update(shots * (12 if kind == "batch" else 1))
                    return iq, record
                except BaseException as exc:
                    if record["status"] == "running":
                        record["status"] = "failed"
                    record["error"] = f"{type(exc).__name__}: {exc}"
                    partial = getattr(exc, "partial_records", None)
                    if partial is not None:
                        recovered = (batch.records_iq(partial) if kind == "batch" else
                                     np.asarray([complex(r.i, r.q) for r in partial]))
                        np.savez_compressed(raw_path, iq=recovered)
                        record["partial_records_saved"] = len(recovered)
                    raise
                finally:
                    record["elapsed_s"] = time.monotonic()-start
                    record["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
                    dual.checkpoint(path, manifest)

            def reference(index):
                values, saved = {}, {"index": index}
                for state in ("ground", "excited"):
                    values[state], rec = measure(f"reference{index:03d}_{state}", ANCHOR_GHZ,
                                                state, REFERENCE_SHOTS)
                    saved[state + "_raw_npz"] = rec["raw_npz"]
                manifest["references"].append(saved)
                return values

            def anchor(label, refs):
                iq, rec = measure("anchor_" + label, ANCHOR_GHZ, "batch", SHOTS)
                result = analysis.analyze_site(iq, refs["ground"], refs["excited"], seed=9701+len(manifest["anchors"]))
                point = {"label": label, "frequency_ghz": ANCHOR_GHZ, "raw_npz": rec["raw_npz"], "analysis": result}
                manifest["anchors"].append(point)
                return iq, result

            before = reference(0)
            _, batched = anchor("pre", before)
            individual = []
            for condition in batch.conditions():
                iq, _ = measure("bridge_" + condition["name"], ANCHOR_GHZ, "individual", SHOTS, condition)
                individual.append(iq)
            manifest["batching_bridge"] = {"batched": batched,
                "individual": analysis.analyze_site(np.stack(individual, axis=1), before["ground"],
                                                    before["excited"], seed=9710),
                "interpretation": "independent acquisitions; compare uncertainty, no automatic equivalence claim"}
            frequencies = frequency_grid()
            for chunk_start in range(0, len(frequencies), REFERENCE_EVERY):
                pending = []
                for index in range(chunk_start, min(chunk_start+REFERENCE_EVERY, len(frequencies))):
                    frequency = frequencies[index]
                    iq, rec = measure(site_key(index, frequency), frequency, "batch", SHOTS)
                    pending.append((iq, {"index": index, "frequency_ghz": frequency,
                        "realized_frequency_ghz": hw.realized_frequency[frequency],
                        "raw_npz": rec["raw_npz"],
                        "reference_brackets": [chunk_start//REFERENCE_EVERY, chunk_start//REFERENCE_EVERY+1]}))
                after = reference(chunk_start//REFERENCE_EVERY+1)
                stability = _reference_stability(before, after)
                ground = np.concatenate([before["ground"], after["ground"]])
                excited = np.concatenate([before["excited"], after["excited"]])
                for iq, point in pending:
                    result = analysis.analyze_site(iq, ground, excited, seed=9800+point["index"])
                    if not stability["valid"]:
                        result["valid"], result["status"] = False, "unresolved"
                        result["reasons"].append("reference bracket drift")
                        result["ratio_before_drift_mask"] = result["ratio"]
                        result["ratio"], result["ratio_ci95"] = None, None
                    point.update({"analysis": result, "reference_stability": stability})
                    manifest["sites"].append(point)
                before = after
                if chunk_start == 40:
                    anchor("mid", before)
                _write_csv(Path(manifest["summary_csv"]), manifest["sites"])
                dual.checkpoint(path, manifest)
            anchor("post", before)
            manifest["valid_sites"] = sum(p["analysis"]["valid"] for p in manifest["sites"])
            manifest["assessment"] = {"complete_grid": len(manifest["sites"]) == 101,
                "intrinsic_t2_inferred": False, "hotspot_claimed": False,
                "next_check": "compare anchors, individual/batched bridge, and validated-band contrast before expanding"}
        manifest["status"] = "complete_few_point_screen"
        manifest["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        dual.checkpoint(path, manifest)
        progress.set_description_str("Echo screen complete")
        return path
    except BaseException as exc:
        progress.set_description_str("Echo screen stopped")
        manifest["status"] = "failed"
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        dual.checkpoint(path, manifest)
        raise
    finally:
        progress.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--plan", action="store_true")
    action.add_argument("--run", action="store_true")
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--correction-json", type=Path)
    parser.add_argument("--quiet", action="store_true", help="disable the elapsed-time and ETA progress bar")
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(plan(), indent=2))
    else:
        run(data_root=args.data_root, correction_json=args.correction_json,
            show_progress=not args.quiet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
