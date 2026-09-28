"""Small hardware pilot for shot-alternating target-resident pump/probe.

Each hardware shot contains four complete park-preparation, corrected target
visit, return, and readout sequences. Cold/hot and sham/on conditions are
therefore separated by milliseconds inside one compiled program, rather than
by separate Python acquisitions. Forward and reverse orders diagnose
condition-order carryover. This is a sequencing pilot, not a TLS claim.
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
    TLSPumpProbeResidentProbe as probe,
    TLSPumpProbeWidePassiveScan as wide,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.programs import (
    _declare_common, _reserved_registers, allocate_named_registers,
    allocate_registers, resident_control_names,
)


SHOTS = 200
REFERENCE_SHOTS = 400
CONDITION_NAMES = ("sham_g", "sham_e", "on_g", "on_e")


def conditions(center_ghz, *, reverse=False):
    center = float(center_ghz)
    result = [{"name": name, "preparation_state": name[-1],
               "gain": 6000 if name.startswith("on") else 0,
               "drive_mhz": round(1000.0 * center + 5.0, 3)}
              for name in CONDITION_NAMES]
    return list(reversed(result)) if reverse else result


def split_records(records, order, *, shots):
    records = list(records)
    if len(records) != int(shots) * len(order):
        raise ValueError(f"expected {int(shots) * len(order)} IQ records; got {len(records)}")
    if len(order) != 4 or set(order) != set(CONDITION_NAMES):
        raise ValueError("interleaved order must contain each condition exactly once")
    return {name: records[index::4] for index, name in enumerate(order)}


def stream_dimensions(shots):
    return {"total_shots": int(shots), "records_per_shot": 4,
            "total_units": int(shots), "records_per_unit": 4}


class ShotAlternatingResidentProgram(resident.ResidentDriveProgram):
    """Four complete resident-probe subshots per streamed hardware shot."""

    def __init__(self, soccfg, condition_cfgs, payload_calibration, loop_calibration):
        configs = [dict(cfg) for cfg in condition_cfgs]
        if len(configs) != 4:
            raise ValueError("four condition configurations are required")
        common = ("ff_gain", "ff_park_gain", "opx_resident_pre_us",
                  "opx_resident_post_us", "opx_resident_freq_mhz", "shots", "reps")
        if any(any(cfg[key] != configs[0][key] for key in common)
               for cfg in configs[1:]):
            raise ValueError("interleaved conditions must share flux, timing, frequency, shots")
        expected = {(0, "g"), (0, "e"), (6000, "g"), (6000, "e")}
        observed = {(int(cfg["opx_resident_gain"]),
                     cfg["opx_resident_preparation_state"]) for cfg in configs}
        if observed != expected:
            raise ValueError("interleaved conditions must be sham/on crossed with g/e")
        self.condition_cfgs = configs
        super().__init__(soccfg, configs[0], payload_calibration, loop_calibration)

    def make_program(self):
        _declare_common(self)
        self._declare_experiment()
        self.reset_page = self.ch_page(self.cfg["qubit_ch"])
        self.reset_regs = allocate_registers(self, self.reset_page)
        reserved = _reserved_registers(self, 0)
        if self.reset_page == 0:
            reserved.update(self.reset_regs.values())
        controls = allocate_named_registers(
            self, 0, resident_control_names(self.cfg, ("shot_loop", "done")),
            reserved=reserved)
        self.regwi(self.reset_page, self.reset_regs["address"], self.record_base)
        self.regwi(0, controls["done"], 0)
        self.memwi(0, controls["done"], self.done_addr)
        self.regwi(0, controls["shot_loop"], self.reps - 1)
        self._initialize_stream(controls, **stream_dimensions(self.reps),
                                prefix="Q3_INTERLEAVED_RESIDENT")
        self._begin_park_lifecycle()
        self.label("Q3_INTERLEAVED_SHOT_LOOP")
        base_cfg = self.cfg
        for condition_cfg in self.condition_cfgs:
            self.cfg = condition_cfg
            self._emit_body()
        self.cfg = base_cfg
        # The acquisition reader checks completed *records*, not logical shots.
        self.mathi(0, controls["done"], controls["done"], "+", 4)
        self.memwi(0, controls["done"], self.done_addr)
        self._stream_after_shot()
        self.loopnz(0, controls["shot_loop"], "Q3_INTERLEAVED_SHOT_LOOP")
        self._finish_stream()
        self._end_park_lifecycle()
        self.end()


def plan():
    return {"hardware_access": False, "reset_mode": "passive",
            "purpose": "validate shot-alternating target-resident condition order",
            "site": "freshly selected loss feature",
            "condition_names": list(CONDITION_NAMES),
            "condition_orders": [list(CONDITION_NAMES), list(reversed(CONDITION_NAMES))],
            "programs": 2, "conditions_per_shot": 4,
            "shots_per_program": SHOTS, "raw_iq_saved": True,
            "pre_drive_us": resident.PRE_DRIVE_US,
            "post_drive_us": resident.POST_DRIVE_US,
            "full_return_before_each_readout_us": 40.0,
            "inter_shot_delay_us": 500.0,
            "calibration_session": probe.CALIBRATION_SESSION_ID,
            "note": __doc__}


def run(*, data_root=localizer.DATA_ROOT, correction_json=None):
    data_root = Path(data_root)
    calibration_path, calibration = probe.checked_calibration(data_root)
    correction = localizer.checked_correction(data_root, correction_json)
    scout = localizer.run(
        data_root=data_root, correction_json=correction,
        parameter_overrides={**adaptive.scout_parameters(phase="pre"),
                             "output_suffix": "TLS_PumpProbe_ShotAlternating_Scout"})
    selected = adaptive.select_loss_feature(adaptive.read_scout(scout))
    center = round(float(selected["center_ghz"]), 3)
    if not probe.calibration_brackets_feature(calibration, center):
        raise RuntimeError(f"{center:.3f} GHz lies outside the calibrated "
                           "gain-6000 region; rerun TLSPumpProbeResidentDrive")
    print(f"[shot-alternating] feature={center:.3f} GHz", flush=True)

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
        dc, realized = _integer_dc_grid(wide.parameters(), np.asarray([center]), tls)
        dc_lookup = {center: int(dc[0])}
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
        for pre in (resident.TRANSFER_PRE_US, resident.PRE_DRIVE_US):
            before, after, recovery = resident.resident_segments(
                compensation, pre_us=pre + ff_pulse.flux_settle_us(base),
                pulse_us=pulse_us, post_us=resident.POST_DRIVE_US,
                recovery_us=40.0)
            windows[str(pre)] = {"held_multiplier": before[-1][0],
                                 "post_multiplier": after[0][0],
                                 "recovery_us": sum(duration for _, duration in recovery)}
        session_id = ("q3_pump_probe_shot_alternating_" +
                      datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") +
                      "_" + uuid.uuid4().hex[:8])
        folder = data_root / "q3" / session_id
        folder.mkdir(parents=True, exist_ok=False)
        path = folder / "manifest.json"
        refs = (probe.reference_arms(center, phase="pre") +
                probe.reference_arms(center, phase="post"))
        for ref in refs:
            ref["shots"] = REFERENCE_SHOTS
        orders = [conditions(center), conditions(center, reverse=True)]
        manifest = {"schema": "q3.pump-probe-shot-alternating-pilot.v1",
                    "status": "running", "session_id": session_id,
                    "code_commit": os.environ.get("Q3_CODE_COMMIT", "unknown"),
                    "calibration_manifest": str(calibration_path),
                    "correction_json": str(correction),
                    "correction_sha256": localizer.CORRECTION_SHA256,
                    "scout_csv": str(scout), "selected": selected,
                    "center_ghz": center, "dc_gain": int(dc[0]),
                    "realized_ghz": realized.tolist(), "plan": plan(),
                    "correction_windows": windows,
                    "drive_pulse_nominal_us": pulse_us,
                    "references": [{**r, "status": "pending"} for r in refs],
                    "programs": [{"name": name, "order": [c["name"] for c in order],
                                  "conditions": order, "status": "pending"}
                                 for name, order in (("forward", orders[0]),
                                                     ("reverse", orders[1]))]}
        protocol.checkpoint(path, manifest)
        print(f"[shot-alternating] manifest={path}", flush=True)
        raw_refs = {}
        axis = None
        try:
            soc, soccfg = tls.makeProxy()
            bundle = runtime_bundle(base)
            # Build both full four-condition programs before the first readout.
            programs = {}
            for entry in manifest["programs"]:
                cfgs = [resident.arm_config(
                    base, {"flux_ghz": center, "drive_mhz": cond["drive_mhz"],
                           "gain": cond["gain"],
                           "preparation_state": cond["preparation_state"],
                           "pre_drive_us": resident.PRE_DRIVE_US,
                           "post_drive_us": resident.POST_DRIVE_US,
                           "shots": SHOTS}, dc_lookup)
                        for cond in entry["conditions"]]
                programs[entry["name"]] = ShotAlternatingResidentProgram(
                    soccfg, cfgs, bundle.payload, bundle.loop)
            for ref in manifest["references"]:
                resident.ResidentDriveProgram(
                    soccfg, resident.arm_config(base, ref, dc_lookup),
                    bundle.payload, bundle.loop)
            manifest["preflight_complete"] = True
            protocol.checkpoint(path, manifest)

            def acquire_ref(ref):
                nonlocal axis
                cfg = resident.arm_config(base, ref, dc_lookup)
                ref["status"] = "acquiring"
                protocol.checkpoint(path, manifest)
                program = resident.ResidentDriveProgram(
                    soccfg, cfg, bundle.payload, bundle.loop)
                records = _run_program(
                    soc, program, max(30.0, _block_timeout_s(cfg, REFERENCE_SHOTS)),
                    cfg, total_shots=REFERENCE_SHOTS)
                if len(records) != REFERENCE_SHOTS:
                    raise RuntimeError(f"{ref['name']}: incomplete reference records")
                raw_refs[ref["name"]] = records
                raw_path = folder / f"{ref['name']}.npz"
                np.savez_compressed(raw_path, i=[r.i for r in records],
                                    q=[r.q for r in records])
                ref["raw_npz"] = str(raw_path)
                if ref["name"] == "ref_e_pre":
                    axis = resident.fit_axis(
                        resident.record_iq(raw_refs["ref_g_pre"]),
                        resident.record_iq(records))
                    manifest["pre_readout_axis"] = axis
                    if not axis["valid"]:
                        raise RuntimeError("pre-run readout axis invalid")
                if axis is not None:
                    ref["excited_fraction_pre_axis"] = resident.classify(records, axis)
                ref["status"] = "complete"
                protocol.checkpoint(path, manifest)

            for ref in manifest["references"][:4]:
                print(f"[shot-alternating] {ref['name']}", flush=True)
                acquire_ref(ref)
            for entry in manifest["programs"]:
                name = entry["name"]
                print(f"[shot-alternating] {name} 200 x 4 conditions", flush=True)
                entry["status"] = "acquiring"
                protocol.checkpoint(path, manifest)
                start = time.monotonic()
                entry["acquisition_started_at_utc"] = datetime.now(timezone.utc).isoformat()
                records = _run_program(
                    soc, programs[name],
                    max(30.0, 4.0 * _block_timeout_s(base, SHOTS)),
                    base, total_shots=SHOTS)
                entry["acquisition_elapsed_s"] = time.monotonic() - start
                entry["acquisition_finished_at_utc"] = datetime.now(timezone.utc).isoformat()
                split = split_records(records, entry["order"], shots=SHOTS)
                for cond in entry["conditions"]:
                    subset = split[cond["name"]]
                    raw_path = folder / f"{name}_{cond['name']}.npz"
                    np.savez_compressed(raw_path, i=[r.i for r in subset],
                                        q=[r.q for r in subset])
                    cond["raw_npz"] = str(raw_path)
                    cond["excited_fraction_pre_axis"] = resident.classify(subset, axis)
                entry["status"] = "complete"
                protocol.checkpoint(path, manifest)
            for ref in manifest["references"][4:]:
                print(f"[shot-alternating] {ref['name']}", flush=True)
                acquire_ref(ref)
            manifest["post_readout_score"] = resident.score_axis(
                axis, resident.record_iq(raw_refs["ref_g_post"]),
                resident.record_iq(raw_refs["ref_e_post"]))
            manifest["transfer_control"] = {
                phase: {"ground": resident.classify(
                            raw_refs[f"ref_transfer_g_{phase}"], axis),
                        "excited": resident.classify(
                            raw_refs[f"ref_transfer_e_{phase}"], axis)}
                for phase in ("pre", "post")}
            for item in manifest["transfer_control"].values():
                item["usable"] = resident.transfer_usable(item["ground"],
                                                           item["excited"])
            order_scores = {}
            for entry in manifest["programs"]:
                x = {c["name"]: c["excited_fraction_pre_axis"]
                     for c in entry["conditions"]}
                order_scores[entry["name"]] = {
                    "cold_drive_contrast": x["on_g"] - x["sham_g"],
                    "hot_minus_cold_drive_change": (
                        x["on_e"] - x["on_g"] - x["sham_e"] + x["sham_g"])}
            manifest["order_scores"] = order_scores
            post_scout = localizer.run(
                data_root=data_root, correction_json=correction,
                parameter_overrides={**adaptive.scout_parameters(phase="post"),
                                     "output_suffix": "TLS_PumpProbe_ShotAlternating_Scout_post"})
            manifest["post_scout_csv"] = str(post_scout)
            try:
                manifest["post_selected"] = adaptive.select_loss_feature(
                    adaptive.read_scout(post_scout))
            except ValueError as exc:
                manifest["post_selection_error"] = str(exc)
            manifest["feature_stable"] = (
                resident.feature_stable(selected, manifest["post_selected"])
                if "post_selected" in manifest else False)
            valid = (manifest["post_readout_score"]["valid"] and
                     all(x["usable"] for x in manifest["transfer_control"].values()) and
                     manifest["feature_stable"] and
                     all(x["cold_drive_contrast"] >= 0.10
                         for x in order_scores.values()) and
                     abs(order_scores["forward"]["hot_minus_cold_drive_change"] -
                         order_scores["reverse"]["hot_minus_cold_drive_change"]) <= 0.25)
            manifest["status"] = "complete" if valid else "complete_controls_unstable"
            protocol.checkpoint(path, manifest)
            print(f"[shot-alternating] {manifest['status']}: {path}", flush=True)
            return path
        except BaseException as exc:
            manifest["status"] = "failed"
            manifest["error"] = f"{type(exc).__name__}: {exc}"
            protocol.checkpoint(path, manifest)
            raise


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
