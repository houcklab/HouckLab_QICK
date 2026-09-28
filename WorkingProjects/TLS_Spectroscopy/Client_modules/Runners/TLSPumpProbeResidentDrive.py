"""Calibrate a qubit drive while q3 remains at the freshly found loss feature.

This is the first, readout-validated stage of a short-gap pump/probe. It tests
whether a Gaussian pulse at the target flux can re-excite the qubit. No result
from this calibration is itself evidence of TLS saturation. The pulse is played
between two pieces of one compensated target hold; the complete 40-us return
precedes the sole readout. Raw single-shot IQ and zero-drive brackets are saved.

Only this experimental runner is changed; the production TLS pipeline is not.
"""

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import uuid

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSPumpProbeAdaptiveParkPump as adaptive,
    TLSPumpProbeLocalizer as localizer,
    TLSPumpProbeProtocolCheck as protocol,
    TLSPumpProbeWidePassiveScan as wide,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.programs import (
    OPXResetT1Program, _pulse_pi_and_align,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.records import signed32


SHOTS = 200
PRE_DRIVE_US = 20.0
POST_DRIVE_US = 0.1
TRANSFER_PRE_US = 4.0
FLANK_OFFSET_GHZ = -0.014
DETUNINGS_MHZ = (-20, -10, -5, 0, 5, 10, 20)
DRIVEN_GAINS = (1000, 3000, 6000, 12000, 20000, 30000)


@dataclass(frozen=True)
class SingleIQ:
    i: int
    q: int


def decode_single_iq(words, expected_records=None):
    flat = np.asarray(words).ravel()
    if flat.size % 2:
        raise ValueError("single IQ needs two words per shot")
    count = flat.size // 2
    if expected_records is not None and count != int(expected_records):
        raise ValueError(f"expected {expected_records} records; got {count}")
    signed = np.asarray([signed32(v) for v in flat], dtype=np.int64).reshape(-1, 2)
    return [SingleIQ(int(i), int(q)) for i, q in signed]


def resident_segments(compensation, *, pre_us, pulse_us, post_us, recovery_us):
    """Split a corrected target visit only when its drive window is flat."""
    target, recovery = ff_pulse.compensation_round_trip_segments(
        compensation, pre_us + pulse_us + post_us,
        recovery_us=recovery_us)
    before, rest = ff_pulse.split_compensation_segments(target, pre_us)
    during, after = ff_pulse.split_compensation_segments(rest, pulse_us)
    if not before or not during or not after:
        raise ValueError("target correction does not cover the drive window")
    held = float(before[-1][0])
    if any(abs(float(level) - held) > 1e-6 for level, _ in during) or \
            abs(float(after[0][0]) - held) > 1e-6:
        raise ValueError("target correction is not flat across resident drive")
    if sum(duration for _, duration in recovery) < recovery_us - 1e-6:
        raise ValueError("target correction does not cover full return")
    return before, after, recovery


class ResidentDriveProgram(OPXResetT1Program):
    """One readout following a target-resident pulse and complete flux return."""

    record_words = 2
    decode_dmem_records = staticmethod(decode_single_iq)

    def __init__(self, soccfg, cfg, payload_calibration, loop_calibration):
        if not bool(cfg.get("opx_hard_flux_steps", False)):
            raise ValueError("resident drive requires hard flux steps")
        if not bool(cfg.get("opx_persistent_park", False)):
            raise ValueError("resident drive requires persistent park")
        if bool(cfg.get("flux_predistortion_overlap_payload_readout", True)):
            raise ValueError("readout must follow the complete corrected return")
        if cfg.get("opx_reset_scheme") != "none":
            raise ValueError("resident calibration uses passive preparation")
        if cfg.get("opx_resident_reference_state") not in (None, "g", "e"):
            raise ValueError("reference state must be g/e or absent")
        if cfg.get("opx_resident_preparation_state", "g") not in ("g", "e"):
            raise ValueError("preparation state must be g or e")
        for key in ("opx_resident_pre_us", "opx_resident_post_us"):
            if not math.isfinite(float(cfg[key])) or float(cfg[key]) < 0.05:
                raise ValueError(f"{key} must be finite and at least 0.05 us")
        if not math.isfinite(float(cfg["opx_resident_freq_mhz"])):
            raise ValueError("resident frequency must be finite")
        if not 0 <= int(cfg["opx_resident_gain"]) <= 30000:
            raise ValueError("resident gain must be 0..30000 DAC")
        super().__init__(soccfg, cfg, payload_calibration, loop_calibration)

    def _resident_excursion(self):
        cfg = self.cfg
        if self._t1_ff_compensation is None:
            raise ValueError("resident drive requires the pinned flux correction")
        park_gain = cfg["ff_park_gain"]
        target_gain = cfg["ff_gain"]
        # The Gaussian is 4 sigma long; _pulse_pi_and_align adds 0.01 us.
        pulse_us = 4.0 * float(cfg["sigma"]) + 0.01
        pre_us = float(cfg["opx_resident_pre_us"]) + self._t1_ff_settle_us
        post_us = float(cfg["opx_resident_post_us"])
        before, after, recovery = resident_segments(
            self._t1_ff_compensation, pre_us=pre_us, pulse_us=pulse_us,
            post_us=post_us,
            recovery_us=self._t1_ff_predistortion_recovery_us)
        # The FF DAC holds its last command while the qubit pulse plays.
        # This is equivalent to the calculated waveform only because the
        # helper verifies that its full drive window is exactly flat.
        ff_pulse.play_relative_compensation_segments(
            self, park_gain, target_gain, before)
        self.sync_all(0)
        self.set_pulse_registers(
            ch=cfg["qubit_ch"], style="arb",
            freq=self.freq2reg(float(cfg["opx_resident_freq_mhz"]),
                               gen_ch=cfg["qubit_ch"]),
            phase=self.deg2reg(0.0, gen_ch=cfg["qubit_ch"]),
            gain=int(cfg["opx_resident_gain"]), waveform="qubit")
        _pulse_pi_and_align(self)
        ff_pulse.play_relative_compensation_segments(
            self, park_gain, target_gain, after)
        ff_pulse.play_relative_compensation_segments(
            self, park_gain, target_gain, recovery)
        ff_pulse.play_hard_step(self, park_gain)
        self.sync_all(0)

    def _emit_body(self):
        park_up, park_down = self._shot_park_callbacks()
        park_up()
        self._set_payload_pulse(gain=(
            0 if self.cfg.get("opx_resident_preparation_state", "g") == "g"
            else None))
        _pulse_pi_and_align(self)
        self._resident_excursion()
        if self.cfg.get("opx_resident_reference_state") == "e":
            self._set_payload_pulse()
            _pulse_pi_and_align(self)
        self._measure_raw()
        for name in ("i", "q"):
            self.memw(self.reset_page, self.reset_regs[name], self.reset_regs["address"])
            self.mathi(self.reset_page, self.reset_regs["address"],
                       self.reset_regs["address"], "+", 1)
        park_down()
        self.sync_all(self.us2cycles(float(self.reset_config.inter_shot_delay_us)))


def record_iq(records):
    return np.asarray([complex(record.i, record.q) for record in records])


def fit_axis(ground_iq, excited_iq):
    ground = np.asarray(ground_iq, dtype=complex).reshape(-1)
    excited = np.asarray(excited_iq, dtype=complex).reshape(-1)
    if ground.size < 50 or excited.size < 50:
        raise ValueError("too few reference shots")
    delta = np.median(excited.real) - np.median(ground.real) + 1j * (
        np.median(excited.imag) - np.median(ground.imag))
    if abs(delta) < 1e-9 or not np.isfinite(delta):
        raise ValueError("readout reference centroids overlap")
    theta = float(np.angle(delta))
    g = np.real(ground * np.exp(-1j * theta))
    e = np.real(excited * np.exp(-1j * theta))
    threshold = float((np.median(g) + np.median(e)) / 2.0)
    fidelity = float((np.mean(g < threshold) + np.mean(e > threshold)) / 2.0)
    return {"theta_rad": theta, "threshold": threshold,
            "fidelity": fidelity, "valid": bool(fidelity >= 0.70)}


def score_axis(axis, ground_iq, excited_iq):
    rotation = np.exp(-1j * axis["theta_rad"])
    g = np.real(np.asarray(ground_iq, dtype=complex) * rotation)
    e = np.real(np.asarray(excited_iq, dtype=complex) * rotation)
    fidelity = float((np.mean(g < axis["threshold"]) +
                      np.mean(e > axis["threshold"])) / 2.0)
    return {"fidelity": fidelity, "valid": bool(fidelity >= 0.70),
            "ground_shots": int(g.size), "excited_shots": int(e.size)}


def classify(records, axis):
    iq = record_iq(records)
    projection = np.real(iq * np.exp(-1j * axis["theta_rad"]))
    return float(np.mean(projection > axis["threshold"]))


def feature_stable(pre, post):
    return bool(abs(1000.0 * (float(post["center_ghz"]) -
                              float(pre["center_ghz"]))) <= 2.0 + 1e-6
                and min(float(pre["depth"]), float(post["depth"])) >= 0.15)


def transfer_usable(ground_fraction, excited_fraction):
    """A park-prepared excitation must remain distinguishable after return."""
    return bool(float(excited_fraction) - float(ground_fraction) >= 0.15)


def calibration_arms(center_ghz, flank_ghz):
    arms = []
    # Reversing the detuning order on the flank avoids repeating one long
    # monotonic frequency trajectory. Zero-gain brackets track local drift.
    for site, flux_ghz, detunings in (
        ("feature", center_ghz, DETUNINGS_MHZ),
        ("flank", flank_ghz, tuple(reversed(DETUNINGS_MHZ))),
    ):
        for detuning in detunings:
            frequency = round(1000.0 * float(flux_ghz) + detuning, 3)
            label = f"{site}_{detuning:+d}MHz".replace("+", "p").replace("-", "m")
            for order, gain in enumerate((0, *DRIVEN_GAINS, 0)):
                arms.append({"name": f"{label}_{order:02d}",
                             "site": site, "flux_ghz": float(flux_ghz),
                             "detuning_mhz": int(detuning),
                             "drive_mhz": frequency, "gain": int(gain)})
    return arms


def fresh_map_scout_parameters(phase):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
        TLSPumpProbeHeralded as heralded,
    )
    return {**heralded.postselection_scout_parameters(phase),
            "output_suffix": f"TLS_ResidentDrive_FreshMap_Scout_{phase}"}


def plan(*, fresh_map=False):
    result = {"hardware_access": False, "reset_mode": "passive",
            "purpose": "calibrate a target-resident qubit re-excitation pulse",
            "sites": ["loss feature", "14-MHz lower flank"],
            "detunings_mhz": list(DETUNINGS_MHZ),
            "driven_gains_dac": list(DRIVEN_GAINS),
            "zero_drive_brackets_per_detuning": 2,
            "shots_per_arm": SHOTS,
            "pre_drive_us": PRE_DRIVE_US,
            "post_drive_us": POST_DRIVE_US,
            "park_excited_return_control_pre_us": TRANSFER_PRE_US,
            "complete_return_before_readout_us": 40.0,
            "raw_iq_saved": True,
            "follow_up": "Choose pulse from raw IQ, then run short-gap hot/cold probe",
            "note": __doc__}
    if fresh_map:
        result["scout_range_ghz"] = [4.060, 4.170]
        result["control"] = "qualified 14-MHz lower flux point"
    return result


def arm_config(base, arm, dc_lookup):
    cfg = dict(base)
    post_us = float(arm.get("post_drive_us", POST_DRIVE_US))
    cfg.update({"ff_gain": dc_lookup[arm["flux_ghz"]],
                "ff_hold": float(arm.get("pre_drive_us", PRE_DRIVE_US)) + post_us +
                           4.0 * float(base["sigma"]) + 0.01,
                "opx_resident_pre_us": float(arm.get("pre_drive_us", PRE_DRIVE_US)),
                "opx_resident_post_us": post_us,
                "opx_resident_freq_mhz": arm["drive_mhz"],
                "opx_resident_gain": arm["gain"],
                "opx_resident_reference_state": arm.get("reference_state"),
                "opx_resident_preparation_state": arm.get("preparation_state", "g"),
                "shots": int(arm.get("shots", SHOTS)),
                "reps": int(arm.get("shots", SHOTS))})
    return cfg


def run(*, data_root=localizer.DATA_ROOT, correction_json=None,
        fresh_map=False):
    data_root = Path(data_root)
    correction = localizer.checked_correction(data_root, correction_json)
    if fresh_map:
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
            TLSPumpProbeHeralded as heralded,
        )
    scout_parameters = (fresh_map_scout_parameters("pre") if fresh_map else
                        {**adaptive.scout_parameters(phase="pre"),
                         "output_suffix": "TLS_PumpProbe_ResidentDrive_Scout"})
    scout = localizer.run(
        data_root=data_root, correction_json=correction,
        parameter_overrides=scout_parameters)
    selected = (heralded.select_postselection_feature(
        heralded.read_postselection_scout(scout)) if fresh_map else
        adaptive.select_loss_feature(adaptive.read_scout(scout)))
    center = round(float(selected["center_ghz"]), 3)
    flank = (float(selected["control_ghz"]) if fresh_map else
             round(center + FLANK_OFFSET_GHZ, 3))
    print(f"[resident-drive] feature={center:.3f} GHz, "
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
        correction_windows = {}
        for pre in (PRE_DRIVE_US, TRANSFER_PRE_US):
            before, after, recovery = resident_segments(
                compensation, pre_us=pre + ff_pulse.flux_settle_us(base),
                pulse_us=pulse_us, post_us=POST_DRIVE_US,
                recovery_us=40.0)
            correction_windows[str(pre)] = {
                "held_multiplier": before[-1][0],
                "post_multiplier": after[0][0],
                "recovery_us": sum(duration for _, duration in recovery),
            }
        session_id = (("q3_pump_probe_resident_drive_fresh_map_" if fresh_map else
                       "q3_pump_probe_resident_drive_") +
                      datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") +
                      "_" + uuid.uuid4().hex[:8])
        folder = data_root / "q3" / session_id
        folder.mkdir(parents=True, exist_ok=False)
        manifest_path = folder / "manifest.json"
        def reference(name, state, *, transfer=False):
            return {"name": name, "site": "feature",
                    "flux_ghz": center, "drive_mhz": 1000.0 * center,
                    "gain": 0,
                    "reference_state": None if transfer else state,
                    "preparation_state": state if transfer else "g",
                    "pre_drive_us": TRANSFER_PRE_US if transfer else PRE_DRIVE_US}

        arms = ([reference("ref_g_pre", "g"),
                 reference("ref_e_pre", "e"),
                 reference("ref_transfer_g_pre", "g", transfer=True),
                 reference("ref_transfer_e_pre", "e", transfer=True)] +
                calibration_arms(center, flank) +
                [reference("ref_transfer_g_post", "g", transfer=True),
                 reference("ref_transfer_e_post", "e", transfer=True),
                 reference("ref_g_post", "g"),
                 reference("ref_e_post", "e")])
        manifest = {"schema": ("q3.pump-probe-resident-drive-fresh-map.v1"
                               if fresh_map else "q3.pump-probe-resident-drive.v1"),
                    "status": "running", "session_id": session_id,
                    "code_commit": os.environ.get("Q3_CODE_COMMIT", "unknown"),
                    "correction_json": str(correction),
                    "correction_sha256": localizer.CORRECTION_SHA256,
                    "scout_csv": str(scout), "selected": selected,
                    "center_ghz": center, "flank_ghz": flank,
                    "dc_lookup": {str(k): v for k, v in dc_lookup.items()},
                    "realized_ghz": realized.tolist(), "plan": plan(fresh_map=fresh_map),
                    "drive_pulse_nominal_us": pulse_us,
                    "correction_windows": correction_windows,
                    "arms": [{**arm, "status": "pending"} for arm in arms]}
        protocol.checkpoint(manifest_path, manifest)
        print(f"[resident-drive] manifest={manifest_path}", flush=True)
        raw_by_name = {}
        axis = None
        try:
            soc, soccfg = tls.makeProxy()
            bundle = runtime_bundle(base)
            # Build representative short/long visits and both frequency
            # extremes before the first acquisition. This catches QICK
            # register and waveform-construction errors without a
            # partially measured frequency sweep.
            preflight = list(arms[:4])
            for site in ("feature", "flank"):
                for detuning in (min(DETUNINGS_MHZ), max(DETUNINGS_MHZ)):
                    preflight.append(next(
                        arm for arm in arms
                        if arm["site"] == site and
                        arm.get("detuning_mhz") == detuning and
                        arm["gain"] == max(DRIVEN_GAINS)))
            for arm in preflight:
                ResidentDriveProgram(
                    soccfg, arm_config(base, arm, dc_lookup),
                    bundle.payload, bundle.loop)
            manifest["preflight_program_arms"] = [arm["name"] for arm in preflight]
            protocol.checkpoint(manifest_path, manifest)
            for index, arm in enumerate(manifest["arms"], start=1):
                cfg = arm_config(base, arm, dc_lookup)
                print(f"[resident-drive] {index}/{len(arms)} {arm['name']}",
                      flush=True)
                arm["status"] = "acquiring"
                protocol.checkpoint(manifest_path, manifest)
                program = ResidentDriveProgram(
                    soccfg, cfg, bundle.payload, bundle.loop)
                records = _run_program(
                    soc, program, max(30.0, _block_timeout_s(cfg, SHOTS)),
                    cfg, total_shots=SHOTS)
                if len(records) != SHOTS:
                    raise RuntimeError(f"{arm['name']}: received {len(records)} of {SHOTS} shots")
                raw_path = folder / f"{arm['name']}.npz"
                np.savez_compressed(raw_path,
                                    i=[r.i for r in records],
                                    q=[r.q for r in records])
                raw_by_name[arm["name"]] = records
                arm["raw_npz"] = str(raw_path)
                if arm["name"] == "ref_e_pre":
                    try:
                        axis = fit_axis(record_iq(raw_by_name["ref_g_pre"]),
                                        record_iq(records))
                    except ValueError as exc:
                        manifest["pre_readout_error"] = str(exc)
                    else:
                        manifest["pre_readout_axis"] = axis
                        manifest["pre_readout_valid"] = axis["valid"]
                if axis is not None and axis["valid"]:
                    arm["excited_fraction_pre_axis"] = classify(records, axis)
                arm["status"] = "complete"
                protocol.checkpoint(manifest_path, manifest)
            if axis is not None and axis["valid"]:
                manifest["post_readout_score"] = score_axis(
                    axis, record_iq(raw_by_name["ref_g_post"]),
                    record_iq(raw_by_name["ref_e_post"]))
                manifest["transfer_control"] = {
                    phase: {
                        "ground": classify(raw_by_name[f"ref_transfer_g_{phase}"], axis),
                        "excited": classify(raw_by_name[f"ref_transfer_e_{phase}"], axis),
                    } for phase in ("pre", "post")}
                for result in manifest["transfer_control"].values():
                    result["usable"] = transfer_usable(
                        result["ground"], result["excited"])
            else:
                manifest["post_readout_score"] = {
                    "valid": False, "reason": "no valid pre-run readout axis"}
            post_scout_parameters = (
                fresh_map_scout_parameters("post") if fresh_map else
                {**adaptive.scout_parameters(phase="post"),
                 "output_suffix": "TLS_PumpProbe_ResidentDrive_Scout_post"})
            post_scout = localizer.run(
                data_root=data_root, correction_json=correction,
                parameter_overrides=post_scout_parameters)
            manifest["post_scout_csv"] = str(post_scout)
            try:
                manifest["post_selected"] = (
                    heralded.select_postselection_feature(
                        heralded.read_postselection_scout(post_scout))
                    if fresh_map else
                    adaptive.select_loss_feature(adaptive.read_scout(post_scout)))
            except ValueError as exc:
                manifest["post_selection_error"] = str(exc)
            manifest["feature_stable"] = (
                feature_stable(selected, manifest["post_selected"])
                if "post_selected" in manifest else False)
            readout_valid = bool(axis is not None and axis["valid"] and
                                 manifest["post_readout_score"]["valid"])
            transfer_valid = bool(all(
                result["usable"]
                for result in manifest.get("transfer_control", {}).values())
                and len(manifest.get("transfer_control", {})) == 2)
            manifest["status"] = (
                "complete" if readout_valid and transfer_valid and
                              manifest["feature_stable"]
                else "complete_controls_unstable")
            protocol.checkpoint(manifest_path, manifest)
            print(f"[resident-drive] {manifest['status']}: {manifest_path}",
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
    parser.add_argument("--fresh-map", action="store_true")
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(plan(fresh_map=args.fresh_map), indent=2))
    else:
        run(data_root=args.data_root, correction_json=args.correction_json,
            fresh_map=args.fresh_map)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
