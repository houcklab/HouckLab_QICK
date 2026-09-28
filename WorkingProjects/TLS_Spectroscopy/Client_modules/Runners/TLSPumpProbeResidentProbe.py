"""Short-gap hot/cold target-resident pump/probe at the current q3 loss feature.

A park-prepared hot or cold qubit spends 20 us at the selected target flux.
Without returning to park or reading out, a previously calibrated microwave
pulse re-excites the qubit at that flux. A 0.1, 2, or 6-us target hold probes
subsequent loss; only then does the compensated 40-us return and one readout
occur. Feature/flank, zero-drive, and detuned-drive arms are paired and
repeated in reverse order. A pump-dependent difference in the hold response
would be a candidate TLS/bath effect, not proof of a single TLS.

The optional loading-time check instead compares 20- and 80-us target visits
with 0.1- and 2-us post-drive holds at gain 6000. Its purpose is to test
whether the short-gap response follows residual qubit excitation.

The optional carryover check repeats sham baseline, pump block, sham baseline
groups to test whether a pump changes *subsequent* loss over many shots.

This runner is experiment-only; it does not modify production TLS scans.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
import uuid

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSPumpProbeAdaptiveParkPump as adaptive,
    TLSPumpProbeLocalizer as localizer,
    TLSPumpProbeProtocolCheck as protocol,
    TLSPumpProbeResidentDrive as resident,
    TLSPumpProbeWidePassiveScan as wide,
)


CALIBRATION_SESSION_ID = "q3_pump_probe_resident_drive_20260928T041637Z_8faee4a6"
SHOTS = 400
POST_HOLDS_US = (0.1, 2.0, 6.0)
LOADING_TIMES_US = (20.0, 80.0)
LOADING_POST_HOLDS_US = (0.1, 2.0)
LOADING_TONE_ORDER = ("sham_a", "on_6000", "detuned_6000", "sham_b")
CARRYOVER_TONE_ORDERS = (
    ("sham", "on_6000", "detuned_6000"),
    ("on_6000", "detuned_6000", "sham"),
    ("detuned_6000", "sham", "on_6000"),
    ("detuned_6000", "on_6000", "sham"),
    ("on_6000", "sham", "detuned_6000"),
    ("sham", "detuned_6000", "on_6000"),
)
CARRYOVER_WASHOUT_S = 5.0
TONE_ORDER = ("sham_a", "on_6000", "detuned_6000",
              "on_30000", "sham_b")
TONE_SETTINGS = {
    "sham_a": (0, 5),
    "on_6000": (6000, 5),
    "detuned_6000": (6000, -10),
    "on_30000": (30000, 5),
    "sham_b": (0, 5),
}


def probe_arms(center_ghz, flank_ghz):
    arms = []
    for repeat in (0, 1):
        sites = (("feature", center_ghz), ("flank", flank_ghz))
        if repeat:
            sites = tuple(reversed(sites))
        holds = POST_HOLDS_US if not repeat else tuple(reversed(POST_HOLDS_US))
        tones = TONE_ORDER if not repeat else tuple(reversed(TONE_ORDER))
        preparations = ("g", "e") if not repeat else ("e", "g")
        for site, flux_ghz in sites:
            for hold in holds:
                for tone in tones:
                    gain, detuning = TONE_SETTINGS[tone]
                    for state in preparations:
                        arms.append({
                            "name": (f"r{repeat}_{site}_{hold:g}us_"
                                     f"{tone}_{state}".replace(".", "p")),
                            "repeat": repeat, "site": site,
                            "flux_ghz": float(flux_ghz),
                            "drive_mhz": round(1000.0 * float(flux_ghz) + detuning, 3),
                            "gain": gain, "tone": tone,
                            "preparation_state": state,
                            "pre_drive_us": resident.PRE_DRIVE_US,
                            "post_drive_us": float(hold),
                            "shots": SHOTS,
                        })
    return arms


def loading_time_arms(center_ghz, flank_ghz):
    """Interleave hot/cold while reversing site, load, hold and tone order."""
    arms = []
    for repeat in (0, 1):
        sites = (("feature", center_ghz), ("flank", flank_ghz))
        if repeat:
            sites = tuple(reversed(sites))
        loads = LOADING_TIMES_US if not repeat else tuple(reversed(LOADING_TIMES_US))
        holds = LOADING_POST_HOLDS_US if not repeat else tuple(reversed(LOADING_POST_HOLDS_US))
        tones = LOADING_TONE_ORDER if not repeat else tuple(reversed(LOADING_TONE_ORDER))
        preparations = ("g", "e") if not repeat else ("e", "g")
        for site, flux_ghz in sites:
            for load in loads:
                for hold in holds:
                    for tone in tones:
                        gain, detuning = TONE_SETTINGS[tone]
                        for state in preparations:
                            arms.append({
                                "name": (f"r{repeat}_{site}_load{load:g}us_"
                                         f"hold{hold:g}us_{tone}_{state}").replace(".", "p"),
                                "repeat": repeat, "site": site,
                                "flux_ghz": float(flux_ghz),
                                "drive_mhz": round(1000.0 * float(flux_ghz) + detuning, 3),
                                "gain": gain, "tone": tone,
                                "preparation_state": state,
                                "pre_drive_us": float(load),
                                "post_drive_us": float(hold),
                                "shots": SHOTS,
                            })
    return arms


def carryover_arms(center_ghz, flank_ghz):
    """Short ABBA-like groups that measure pump-induced cross-arm memory."""
    arms = []
    for cycle, pump_tones in enumerate(CARRYOVER_TONE_ORDERS):
        sites = (("feature", center_ghz), ("flank", flank_ghz))
        if cycle % 2:
            sites = tuple(reversed(sites))
        for site, flux_ghz in sites:
            for pump_tone in pump_tones:
                for role, state in (("pre_g", "g"), ("pre_e", "e"),
                                    ("pump_e", "e"), ("post_e", "e"),
                                    ("post_g", "g")):
                    is_pump = role == "pump_e"
                    gain, detuning = (TONE_SETTINGS[pump_tone]
                                      if is_pump and pump_tone != "sham" else (0, 5))
                    arms.append({
                        "name": f"c{cycle}_{site}_{pump_tone}_{role}",
                        "cycle": cycle, "site": site, "pump_tone": pump_tone,
                        "role": role, "tone": pump_tone if is_pump else "sham",
                        "flux_ghz": float(flux_ghz),
                        "drive_mhz": round(1000.0 * float(flux_ghz) + detuning, 3),
                        "gain": gain, "preparation_state": state,
                        "pre_drive_us": resident.PRE_DRIVE_US,
                        "post_drive_us": resident.POST_DRIVE_US,
                        "shots": 100,
                    })
    return arms


def carryover_drive_checks(center_ghz, flank_ghz):
    """Fresh ground-state drive checks at both actual flux coordinates."""
    arms = []
    for site, flux_ghz in (("feature", center_ghz), ("flank", flank_ghz)):
        for tone in ("sham_a", "on_6000", "detuned_6000", "sham_b"):
            gain, detuning = TONE_SETTINGS[tone]
            arms.append({
                "name": f"drivecheck_{site}_{tone}", "drive_check": True,
                "site": site, "tone": tone,
                "flux_ghz": float(flux_ghz),
                "drive_mhz": round(1000.0 * float(flux_ghz) + detuning, 3),
                "gain": gain, "preparation_state": "g",
                "pre_drive_us": resident.PRE_DRIVE_US,
                "post_drive_us": resident.POST_DRIVE_US,
                "shots": 200,
            })
    return arms


def evaluate_drive_check(fractions):
    """Gate the current-site qubit drive against local sham and detuned arms."""
    result = dict(fractions)
    sham = (float(result["sham_a"]) + float(result["sham_b"])) / 2.0
    result.update({"on_excess": float(result["on_6000"]) - sham,
                   "detuned_excess": float(result["detuned_6000"]) - sham,
                   "bracket_drift": abs(float(result["sham_b"]) -
                                        float(result["sham_a"]))})
    result["usable"] = bool(result["on_excess"] >= 0.10 and
                            abs(result["detuned_excess"]) <= 0.10 and
                            result["bracket_drift"] <= 0.10)
    return result


def reference_arms(center_ghz, *, phase):
    def arm(name, state, *, transfer=False):
        return {"name": f"{name}_{phase}", "site": "feature",
                "flux_ghz": float(center_ghz),
                "drive_mhz": round(1000.0 * float(center_ghz) + 5.0, 3),
                "gain": 0,
                "reference_state": None if transfer else state,
                "preparation_state": state if transfer else "g",
                "pre_drive_us": (resident.TRANSFER_PRE_US if transfer
                                 else resident.PRE_DRIVE_US),
                "post_drive_us": resident.POST_DRIVE_US,
                "shots": SHOTS}
    return [arm("ref_g", "g"), arm("ref_e", "e"),
            arm("ref_transfer_g", "g", transfer=True),
            arm("ref_transfer_e", "e", transfer=True)]


def plan(*, loading_time_check=False, carryover_check=False):
    if loading_time_check and carryover_check:
        raise ValueError("select at most one check mode")
    if carryover_check:
        return {"hardware_access": False, "reset_mode": "passive",
                "purpose": "test reproducible pump-induced change in later sham loss",
                "group_order": ["pre_g", "pre_e", "pump_e", "post_e", "post_g"],
                "pump_tones": ["sham", "on_6000", "detuned_6000"],
                "pump_gain_dac": 6000, "pump_detunings_mhz": [5, -10],
                "sites": ["selected loss feature", "14-MHz lower flank"],
                "pre_drive_us": resident.PRE_DRIVE_US,
                "post_drive_us": resident.POST_DRIVE_US,
                "cycles": 6, "science_arms": 180, "shots_per_arm": 100,
                "drive_check_arms": 8,
                "group_washout_s": CARRYOVER_WASHOUT_S,
                "max_pre_baseline_spread_per_site_cycle": 0.20,
                "raw_iq_saved": True, "intermediate_readout": False,
                "full_return_before_final_readout_us": 40.0,
                "calibration_session": CALIBRATION_SESSION_ID,
                "note": "Compare post-minus-pre hot/cold baseline after each pump block; "
                        "check sham and detuned controls before physical interpretation."}
    if loading_time_check:
        return {"hardware_access": False, "reset_mode": "passive",
                "purpose": "test whether short-gap response follows residual qubit excitation",
                "pump": "park pi (hot) or matched zero-gain pulse (cold)",
                "pre_drive_holds_us": list(LOADING_TIMES_US),
                "target_resident_probe": "Gaussian qubit drive at model +5 MHz",
                "probe_dac_gains": [0, 6000],
                "detuned_control_mhz": -10,
                "probe_holds_us": list(LOADING_POST_HOLDS_US),
                "sites": ["selected loss feature", "14-MHz lower flank"],
                "paired_preparations": ["g", "e"],
                "repeats": 2, "science_arms": 128,
                "shots_per_arm": SHOTS, "intermediate_readout": False,
                "full_return_before_final_readout_us": 40.0,
                "calibration_session": CALIBRATION_SESSION_ID,
                "note": "A load-time trend alone is not proof of TLS memory."}
    return {"hardware_access": False, "reset_mode": "passive",
            "pump": "park pi (hot) or zero-gain matched pulse (cold), then 20-us target visit",
            "target_resident_probe": "Gaussian qubit drive at model +5 MHz",
            "probe_dac_gains": [0, 6000, 30000],
            "detuned_control_mhz": -10,
            "probe_holds_us": list(POST_HOLDS_US),
            "sites": ["selected loss feature", "14-MHz lower flank"],
            "paired_preparations": ["g", "e"],
            "repeats": 2,
            "science_arms": 120,
            "shots_per_arm": SHOTS,
            "intermediate_readout": False,
            "full_return_before_final_readout_us": 40.0,
            "calibration_session": CALIBRATION_SESSION_ID,
            "note": __doc__}


def checked_calibration(data_root):
    path = Path(data_root) / "q3" / CALIBRATION_SESSION_ID / "manifest.json"
    manifest = json.loads(path.read_text())
    if manifest.get("status") != "complete":
        raise ValueError("resident drive calibration did not pass its controls")
    if manifest.get("schema") != "q3.pump-probe-resident-drive.v1":
        raise ValueError("resident drive calibration schema differs")
    if manifest.get("correction_sha256") != localizer.CORRECTION_SHA256:
        raise ValueError("resident drive calibration used a different flux correction")
    if not manifest.get("feature_stable") or not manifest.get("pre_readout_valid"):
        raise ValueError("resident drive calibration feature/readout unstable")
    prior_plan = manifest.get("plan", {})
    if (prior_plan.get("pre_drive_us") != resident.PRE_DRIVE_US or
            prior_plan.get("post_drive_us") != resident.POST_DRIVE_US or
            not {6000, 30000}.issubset(set(prior_plan.get("driven_gains_dac", ())))):
        raise ValueError("resident drive calibration used different drive settings")
    for site in ("feature", "flank"):
        arms = [arm for arm in manifest["arms"]
                if arm.get("site") == site and arm.get("detuning_mhz") == 5]
        if len(arms) != len(resident.DRIVEN_GAINS) + 2:
            raise ValueError(f"{site}: calibrated +5-MHz arm set is incomplete")
        reference = (arms[0]["excited_fraction_pre_axis"] +
                     arms[-1]["excited_fraction_pre_axis"]) / 2.0
        driven = next(arm["excited_fraction_pre_axis"] for arm in arms
                      if arm["gain"] == 6000)
        if driven - reference < 0.10:
            raise ValueError(f"{site}: calibrated 6000-DAC drive contrast below 0.10")
    return path, manifest


def calibration_covers_feature(calibrated_ghz, current_ghz):
    return abs(1000.0 * (float(current_ghz) - float(calibrated_ghz))) <= 5.0 + 1e-6


def calibration_brackets_feature(calibration, current_ghz):
    """Both calibration sites showed gain-6000 contrast in this interval."""
    high = float(calibration["center_ghz"])
    low = high + resident.FLANK_OFFSET_GHZ
    return low - 1e-9 <= float(current_ghz) <= high + 1e-9


def run(*, data_root=localizer.DATA_ROOT, correction_json=None,
        loading_time_check=False, carryover_check=False):
    if loading_time_check and carryover_check:
        raise ValueError("select at most one check mode")
    data_root = Path(data_root)
    label = ("carryover" if carryover_check else
             "loading-time" if loading_time_check else "resident-probe")
    suffix = ("TLS_PumpProbe_Carryover" if carryover_check else
              "TLS_PumpProbe_LoadingTime" if loading_time_check else
              "TLS_PumpProbe_ResidentProbe")
    post_holds = ((resident.POST_DRIVE_US,) if carryover_check else
                  LOADING_POST_HOLDS_US if loading_time_check else POST_HOLDS_US)
    pre_holds = LOADING_TIMES_US if loading_time_check else (resident.PRE_DRIVE_US,)
    calibration_path, calibration = checked_calibration(data_root)
    correction = localizer.checked_correction(data_root, correction_json)
    scout = localizer.run(
        data_root=data_root, correction_json=correction,
        parameter_overrides={**adaptive.scout_parameters(phase="pre"),
                             "output_suffix": suffix + "_Scout"})
    selected = adaptive.select_loss_feature(adaptive.read_scout(scout))
    center = round(float(selected["center_ghz"]), 3)
    calibrated = (calibration_brackets_feature(calibration, center)
                  if carryover_check else
                  calibration_covers_feature(calibration["center_ghz"], center))
    if not calibrated:
        raise RuntimeError(
            f"current feature {center:.3f} GHz is outside the "
            f"validated drive calibration region near "
            f"{calibration['center_ghz']:.3f} GHz; "
            "rerun TLSPumpProbeResidentDrive first")
    flank = round(center + resident.FLANK_OFFSET_GHZ, 3)
    print(f"[{label}] feature={center:.3f} GHz, "
          f"flank={flank:.3f} GHz", flush=True)

    with localizer.scan_environment(correction):
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
            FivePointApplesToApples as five,
            TLSSpectroscopy as tls,
        )
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.ThreePointApplesToApples import (
            _integer_dc_grid,
        )
        from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import (
            _block_timeout_s, _run_program, runtime_bundle,
        )
        from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import (
            ProductionResetSession,
        )

        if int(tls.BaseConfig["ff_park_gain"]) != -25146:
            raise RuntimeError("q3 park gain differs from verified configuration")
        tls.QUBIT, tls.SET_YOKO, tls.outerFolder = "q3", False, str(data_root)
        five.install_scan_calibration(tls)
        grid = np.asarray([center, flank], dtype=float)
        dc, realized = _integer_dc_grid(wide.parameters(), grid, tls)
        dc_lookup = {float(f): int(g) for f, g in zip(grid, dc)}
        compensation = tls._load_correction(str(correction), str(data_root))
        base = ProductionResetSession.passive().apply(tls.BaseConfig)
        five.apply_verified_feedback_timing(base)
        base.update({"apply_flux_tail_compensation": True,
                     "flux_tail_compensation": compensation,
                     "flux_fit_params": tls.FLUX_FIT_PARAMS,
                     "flux_settle_time_us": 0.5,
                     "flux_predistortion_return_prefix_us": 0.5,
                     "flux_predistortion_recovery_us": 40.0,
                     "flux_predistortion_overlap_payload_readout": False,
                     "flux_predistortion_round_trip_mode": "stateful",
                     "readout_thermalization_us": 10.0,
                     "qubit_pulse_style": "arb", "do_ff": True,
                     "opx_reset_scheme": "none",
                     "opx_resident_dmem_stream": True,
                     "opx_inter_shot_delay_us": 500.0})
        pulse_us = 4.0 * float(base["sigma"]) + 0.01
        if abs(pulse_us - float(calibration["drive_pulse_nominal_us"])) > 0.01:
            raise RuntimeError("qubit Gaussian duration changed since drive calibration")
        windows = {}
        for pre in sorted(set(pre_holds) | {resident.TRANSFER_PRE_US,
                                          resident.PRE_DRIVE_US}):
            for post in post_holds:
                before, after, recovery = resident.resident_segments(
                    compensation,
                    pre_us=pre + ff_pulse.flux_settle_us(base),
                    pulse_us=pulse_us, post_us=post, recovery_us=40.0)
                windows[f"{pre:g}/{post:g}"] = {
                    "held_multiplier": before[-1][0],
                    "post_multiplier": after[0][0],
                    "recovery_us": sum(duration for _, duration in recovery)}
        session_id = (("q3_pump_probe_carryover_" if carryover_check else
                       "q3_pump_probe_loading_time_" if loading_time_check
                       else "q3_pump_probe_resident_probe_") +
                      datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") +
                      "_" + uuid.uuid4().hex[:8])
        folder = data_root / "q3" / session_id
        folder.mkdir(parents=True, exist_ok=False)
        manifest_path = folder / "manifest.json"
        science_arms = (carryover_arms(center, flank) if carryover_check else
                        loading_time_arms(center, flank) if loading_time_check
                        else probe_arms(center, flank))
        drive_checks = (carryover_drive_checks(center, flank)
                        if carryover_check else [])
        arms = (reference_arms(center, phase="pre") +
                drive_checks +
                science_arms +
                reference_arms(center, phase="post"))
        manifest = {"schema": ("q3.pump-probe-carryover.v1" if carryover_check else
                               "q3.pump-probe-loading-time.v1" if loading_time_check
                               else "q3.pump-probe-resident-probe.v1"),
                    "status": "running", "session_id": session_id,
                    "code_commit": os.environ.get("Q3_CODE_COMMIT", "unknown"),
                    "calibration_manifest": str(calibration_path),
                    "calibration_selected": calibration["selected"],
                    "correction_json": str(correction),
                    "correction_sha256": localizer.CORRECTION_SHA256,
                    "scout_csv": str(scout), "selected": selected,
                    "center_ghz": center, "flank_ghz": flank,
                    "dc_lookup": {str(k): v for k, v in dc_lookup.items()},
                    "realized_ghz": realized.tolist(),
                    "plan": plan(loading_time_check=loading_time_check,
                                 carryover_check=carryover_check),
                    "drive_pulse_nominal_us": pulse_us,
                    "correction_windows": windows,
                    "fresh_drive_checks": {},
                    "group_results": {},
                    "arms": [{**arm, "status": "pending"} for arm in arms]}
        protocol.checkpoint(manifest_path, manifest)
        print(f"[{label}] manifest={manifest_path}", flush=True)
        raw_by_name = {}
        axis = None
        try:
            soc, soccfg = tls.makeProxy()
            bundle = runtime_bundle(base)
            preflight = list(arms[:4 + len(drive_checks)])
            if carryover_check:
                preflight += [next(arm for arm in science_arms
                                   if arm["site"] == site and
                                   arm["pump_tone"] == tone and
                                   arm["role"] == "pump_e")
                              for site in ("feature", "flank")
                              for tone in ("on_6000", "detuned_6000")]
            elif loading_time_check:
                preflight += [next(arm for arm in science_arms
                                   if arm["site"] == site and
                                   arm["tone"] == "on_6000" and
                                   arm["pre_drive_us"] == load and
                                   arm["post_drive_us"] == hold)
                              for site in ("feature", "flank")
                              for load in LOADING_TIMES_US
                              for hold in LOADING_POST_HOLDS_US]
            else:
                preflight += [next(arm for arm in science_arms
                                   if arm["site"] == site and
                                   arm["tone"] == "on_30000" and
                                   arm["post_drive_us"] == hold)
                              for site in ("feature", "flank")
                              for hold in (min(POST_HOLDS_US), max(POST_HOLDS_US))]
            for arm in preflight:
                resident.ResidentDriveProgram(
                    soccfg, resident.arm_config(base, arm, dc_lookup),
                    bundle.payload, bundle.loop)
            manifest["preflight_program_arms"] = [arm["name"] for arm in preflight]
            protocol.checkpoint(manifest_path, manifest)
            for index, arm in enumerate(manifest["arms"], start=1):
                cfg = resident.arm_config(base, arm, dc_lookup)
                print(f"[{label}] {index}/{len(arms)} {arm['name']}",
                      flush=True)
                arm["status"] = "acquiring"
                arm["started_at_utc"] = datetime.now(timezone.utc).isoformat()
                protocol.checkpoint(manifest_path, manifest)
                program = resident.ResidentDriveProgram(
                    soccfg, cfg, bundle.payload, bundle.loop)
                shots = int(arm["shots"])
                arm["acquisition_started_at_utc"] = datetime.now(timezone.utc).isoformat()
                acquisition_start = time.monotonic()
                records = _run_program(
                    soc, program, max(30.0, _block_timeout_s(cfg, shots)),
                    cfg, total_shots=shots)
                arm["acquisition_elapsed_s"] = time.monotonic() - acquisition_start
                arm["acquisition_finished_at_utc"] = datetime.now(timezone.utc).isoformat()
                if len(records) != shots:
                    raise RuntimeError(f"{arm['name']}: received {len(records)} of {shots} shots")
                raw_path = folder / f"{arm['name']}.npz"
                np.savez_compressed(raw_path,
                                    i=[r.i for r in records],
                                    q=[r.q for r in records])
                raw_by_name[arm["name"]] = records
                arm["raw_npz"] = str(raw_path)
                if arm["name"] == "ref_e_pre":
                    try:
                        axis = resident.fit_axis(
                            resident.record_iq(raw_by_name["ref_g_pre"]),
                            resident.record_iq(records))
                    except ValueError as exc:
                        manifest["pre_readout_error"] = str(exc)
                    else:
                        manifest["pre_readout_axis"] = axis
                        manifest["pre_readout_valid"] = axis["valid"]
                if axis is not None and axis["valid"]:
                    arm["excited_fraction_pre_axis"] = resident.classify(records, axis)
                arm["status"] = "complete"
                arm["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
                protocol.checkpoint(manifest_path, manifest)
                if carryover_check and arm.get("drive_check") and arm["tone"] == "sham_b":
                    if axis is None or not axis["valid"]:
                        raise RuntimeError("fresh drive checks require a valid readout axis")
                    site = arm["site"]
                    checks = {tone: next(a["excited_fraction_pre_axis"]
                                         for a in manifest["arms"]
                                         if a.get("drive_check") and a["site"] == site
                                         and a["tone"] == tone)
                              for tone in ("sham_a", "on_6000",
                                           "detuned_6000", "sham_b")}
                    checks = evaluate_drive_check(checks)
                    manifest["fresh_drive_checks"][site] = checks
                    protocol.checkpoint(manifest_path, manifest)
                    if not checks["usable"]:
                        raise RuntimeError(f"{site} fresh drive check failed: {checks}")
                if carryover_check and arm.get("role") == "pre_e":
                    key = f"c{arm['cycle']}_{arm['site']}_{arm['pump_tone']}"
                    ground = next(a["excited_fraction_pre_axis"]
                                  for a in manifest["arms"]
                                  if a["name"] == key + "_pre_g")
                    excited = arm["excited_fraction_pre_axis"]
                    manifest["group_results"][key] = {
                        "pre_ground": ground, "pre_excited": excited,
                        "pre_hot_minus_cold": excited - ground}
                    protocol.checkpoint(manifest_path, manifest)
                if carryover_check and arm.get("role") == "post_g":
                    key = f"c{arm['cycle']}_{arm['site']}_{arm['pump_tone']}"
                    result = manifest["group_results"][key]
                    excited = next(a["excited_fraction_pre_axis"]
                                   for a in manifest["arms"]
                                   if a["name"] == key + "_post_e")
                    ground = arm["excited_fraction_pre_axis"]
                    result.update({
                        "post_ground": ground, "post_excited": excited,
                        "post_hot_minus_cold": excited - ground,
                        "delta_hot_minus_cold": (
                            excited - ground - result["pre_hot_minus_cold"])})
                    start = time.monotonic()
                    time.sleep(CARRYOVER_WASHOUT_S)
                    result["washout_s_actual"] = time.monotonic() - start
                    protocol.checkpoint(manifest_path, manifest)
                elif carryover_check and arm.get("drive_check") and arm["tone"] == "sham_b":
                    start = time.monotonic()
                    time.sleep(CARRYOVER_WASHOUT_S)
                    manifest["fresh_drive_checks"][arm["site"]]["washout_s_actual"] = (
                        time.monotonic() - start)
                    protocol.checkpoint(manifest_path, manifest)
            if carryover_check:
                spreads = {}
                for cycle in range(len(CARRYOVER_TONE_ORDERS)):
                    for site in ("feature", "flank"):
                        values = [manifest["group_results"][
                            f"c{cycle}_{site}_{tone}"]["pre_hot_minus_cold"]
                            for tone in ("sham", "on_6000", "detuned_6000")]
                        spreads[f"c{cycle}_{site}"] = max(values) - min(values)
                manifest["pre_baseline_spread_by_cycle_site"] = spreads
                manifest["pre_baseline_stable"] = bool(
                    all(value <= 0.20 for value in spreads.values()))
                protocol.checkpoint(manifest_path, manifest)
            if axis is not None and axis["valid"]:
                manifest["post_readout_score"] = resident.score_axis(
                    axis, resident.record_iq(raw_by_name["ref_g_post"]),
                    resident.record_iq(raw_by_name["ref_e_post"]))
                manifest["transfer_control"] = {
                    phase: {
                        "ground": resident.classify(
                            raw_by_name[f"ref_transfer_g_{phase}"], axis),
                        "excited": resident.classify(
                            raw_by_name[f"ref_transfer_e_{phase}"], axis),
                    } for phase in ("pre", "post")}
                for result in manifest["transfer_control"].values():
                    result["usable"] = resident.transfer_usable(
                        result["ground"], result["excited"])
            else:
                manifest["post_readout_score"] = {
                    "valid": False, "reason": "no valid pre-run readout axis"}
            post_scout = localizer.run(
                data_root=data_root, correction_json=correction,
                parameter_overrides={**adaptive.scout_parameters(phase="post"),
                                     "output_suffix": suffix + "_Scout_post"})
            manifest["post_scout_csv"] = str(post_scout)
            try:
                manifest["post_selected"] = adaptive.select_loss_feature(
                    adaptive.read_scout(post_scout))
            except ValueError as exc:
                manifest["post_selection_error"] = str(exc)
            manifest["feature_stable"] = (
                resident.feature_stable(selected, manifest["post_selected"])
                if "post_selected" in manifest else False)
            readout_valid = bool(axis is not None and axis["valid"] and
                                 manifest["post_readout_score"]["valid"])
            transfer_valid = bool(all(
                result["usable"]
                for result in manifest.get("transfer_control", {}).values())
                and len(manifest.get("transfer_control", {})) == 2)
            manifest["status"] = (
                "complete" if readout_valid and transfer_valid and
                              manifest["feature_stable"] and
                              (not carryover_check or manifest["pre_baseline_stable"])
                else "complete_controls_unstable")
            protocol.checkpoint(manifest_path, manifest)
            print(f"[{label}] {manifest['status']}: {manifest_path}",
                  flush=True)
            return manifest_path
        except BaseException as exc:
            manifest["status"] = "failed"
            manifest["error"] = f"{type(exc).__name__}: {exc}"
            protocol.checkpoint(manifest_path, manifest)
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--data-root", type=Path, default=localizer.DATA_ROOT)
    parser.add_argument("--correction-json", type=Path)
    check = parser.add_mutually_exclusive_group()
    check.add_argument("--loading-time-check", action="store_true",
                       help="vary target loading time to separate qubit residual from memory")
    check.add_argument("--carryover-check", action="store_true",
                       help="test whether a pump block changes later zero-drive loss")
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(plan(loading_time_check=args.loading_time_check,
                              carryover_check=args.carryover_check), indent=2))
    else:
        run(data_root=args.data_root, correction_json=args.correction_json,
            loading_time_check=args.loading_time_check,
            carryover_check=args.carryover_check)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
