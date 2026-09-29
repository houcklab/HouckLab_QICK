"""Two-excitation blockade test at a freshly located q3 loss feature.

The first visit prepares a possible environmental excitation. A timed park pi
pulse flips the qubit before a second visit, all within one continuously
predistorted flux waveform and before the only readout. A zero-gain middle
pulse and four first/second-site pairs provide a memoryless-process control.
This experimental runner does not change production spectroscopy or reset.
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
    TLSPumpProbeHeralded as heralded,
    TLSPumpProbeLocalizer as localizer,
    TLSPumpProbeProtocolCheck as protocol,
    TLSPumpProbeResidentDrive as resident,
    TLSPumpProbeResidentProbe as probe,
    TLSPumpProbeWidePassiveScan as wide,
    TLSTwoVisitMemory as memory,
)


LOAD_US = 1.5
PROBE_US = 1.5
GAPS_US = (2.0, 10.0)
PARK_SETTLE_BEFORE_PI_US = 0.5
RECOVERY_US = 40.0
SHOTS = 1200
REFERENCE_SHOTS = 400
PAIRS = ("ff", "fc", "cf", "cc")
CONDITION_NAMES = tuple(
    f"{pair}_{state}_{pulse}" for pair in PAIRS for state in ("g", "e")
    for pulse in ("sham", "pi"))


def program_specs(feature_ghz, control_ghz):
    sites = {"f": float(feature_ghz), "c": float(control_ghz)}
    specs = []
    for repeat in (0, 1):
        gaps = GAPS_US if not repeat else tuple(reversed(GAPS_US))
        for gap in gaps:
            conditions = [
                {"name": f"{pair}_{state}_{'pi' if middle else 'sham'}",
                 "load_site": pair[0], "probe_site": pair[1],
                 "load_ghz": sites[pair[0]], "probe_ghz": sites[pair[1]],
                 "state": state, "middle_pi": middle,
                 "load_us": LOAD_US, "gap_us": gap, "probe_us": PROBE_US}
                for pair in PAIRS for state in ("g", "e")
                for middle in (False, True)]
            if repeat:
                conditions.reverse()
            specs.append({"name": f"gap{gap:g}_r{repeat}",
                          "gap_us": gap, "repeat": repeat,
                          "shots": SHOTS, "order": [c["name"] for c in conditions],
                          "conditions": conditions, "status": "pending"})
    return specs


def split_records(records, order, *, shots):
    records = list(records)
    if len(order) != 16 or set(order) != set(CONDITION_NAMES):
        raise ValueError("invalid blockade stream order")
    if len(records) != len(order) * int(shots):
        raise ValueError("incomplete blockade IQ stream")
    return {name: records[index::len(order)] for index, name in enumerate(order)}


def arm_config(base, condition, dc_lookup, *, shots=SHOTS):
    cfg = memory.arm_config(base, {
        "load_ghz": condition["load_ghz"],
        "probe_ghz": condition["probe_ghz"],
        "state": condition["state"],
        "load_us": condition["load_us"],
        "store_us": condition["gap_us"],
        "probe_us": condition["probe_us"],
    }, dc_lookup, shots=shots)
    cfg["opx_middle_pi"] = bool(condition["middle_pi"])
    return cfg


class BlockadeProgram(memory.TwoVisitProgram):
    """Schedule the middle park pulse over the ongoing compensated flux gap."""

    def __init__(self, soccfg, condition_cfgs, payload_calibration, loop_calibration):
        configs = [dict(cfg) for cfg in condition_cfgs]
        if len(configs) != 16:
            raise ValueError("blockade requires sixteen interleaved conditions")
        common = ("ff_park_gain", "shots", "opx_load_us", "opx_store_us",
                  "opx_probe_us")
        if any(any(cfg[key] != configs[0][key] for key in common)
               for cfg in configs[1:]):
            raise ValueError("blockade conditions must share shot and visit timing")
        gains = {int(cfg["ff_gain"]) for cfg in configs}
        observed = {(int(cfg["ff_gain"]), int(cfg["opx_probe_ff_gain"]),
                     cfg["opx_resident_preparation_state"],
                     bool(cfg["opx_middle_pi"])) for cfg in configs}
        expected = {(a, b, state, middle)
                    for a in gains for b in gains for state in ("g", "e")
                    for middle in (False, True)}
        if len(gains) != 2 or observed != expected:
            raise ValueError("blockade conditions must span four visit pairs, "
                             "g/e, and pi/sham")
        pulse_us = 4.0 * float(configs[0]["sigma"])
        if (PARK_SETTLE_BEFORE_PI_US + pulse_us + 0.01 >
                float(configs[0]["opx_store_us"])):
            raise ValueError("park pi pulse does not fit inside compensated gap")
        self.conditions_per_shot = 16
        self.logical_shots = int(configs[0]["shots"])
        if self.logical_shots <= 0:
            raise ValueError("logical shot count must be positive")
        self.condition_cfgs = configs
        run_cfg = dict(configs[0], reps=16 * self.logical_shots)
        resident.ResidentDriveProgram.__init__(
            self, soccfg, run_cfg, payload_calibration, loop_calibration)

    def _resident_excursion(self):
        if self._t1_ff_compensation is None:
            raise ValueError("blockade requires pinned flux correction")
        cfg = self.cfg
        park = float(cfg["ff_park_gain"])
        first = float(cfg["ff_gain"])
        second = float(cfg["opx_probe_ff_gain"])
        if first == park:
            raise ValueError("first visit gain equals park")
        load_us = float(cfg["opx_load_us"])
        gap_us = float(cfg["opx_store_us"])
        pulse_us = 4.0 * float(cfg["sigma"])
        if PARK_SETTLE_BEFORE_PI_US + pulse_us + .01 > gap_us:
            raise ValueError("middle pulse exceeds compensated park gap")
        segments = memory.two_visit_segments(
            self._t1_ff_compensation, load_us=load_us, store_us=gap_us,
            probe_us=cfg["opx_probe_us"],
            second_amplitude=(second - park) / (first - park),
            recovery_us=self._t1_ff_predistortion_recovery_us)
        through_gap, after_gap = ff_pulse.split_compensation_segments(
            segments, load_us + gap_us)
        if not through_gap or not after_gap:
            raise ValueError("blockade waveform did not span both visits")
        self.sync_all(0)
        # Set the second microwave pulse before scheduling flux, then place it
        # at an explicit tProc time. Both channels run concurrently. Scheduling
        # it first gives the tProc time to enqueue the future pi pulse.
        self._set_payload_pulse(gain=None if cfg["opx_middle_pi"] else 0)
        self.pulse(ch=cfg["qubit_ch"],
                   t=self.us2cycles(load_us + PARK_SETTLE_BEFORE_PI_US))
        ff_pulse.play_relative_compensation_segments(
            self, park, first, through_gap)
        self.sync_all(0)
        ff_pulse.play_relative_compensation_segments(
            self, park, first, after_gap)
        ff_pulse.play_hard_step(self, park)
        self.sync_all(0)


def score(fractions):
    """A Markovian two-state qubit channel factorizes across visit sites.

    The middle pi reverses the g/e contrast sign. An occupied, saturable
    feature raises ff_e_pi, making the factorization residual positive even
    if the ff contrast itself changes sign.
    No microscopic TLS inference is made from this score alone.
    """
    contrasts = {}
    for pulse in ("sham", "pi"):
        contrasts[pulse] = {
            pair: float(fractions[f"{pair}_e_{pulse}"] -
                        fractions[f"{pair}_g_{pulse}"])
            for pair in PAIRS}
    controls = ("fc", "cf", "cc")
    usable = all(contrasts["sham"][pair] >= .08 and
                 contrasts["pi"][pair] <= -.08 for pair in controls)
    result = {"contrasts": contrasts, "usable": bool(usable),
              "pi_blockade_excess": None,
              "sham_blockade_excess": None,
              "pi_minus_sham_blockade_excess": None}
    if usable:
        for pulse in ("sham", "pi"):
            c = contrasts[pulse]
            predicted = c["fc"] * c["cf"] / c["cc"]
            result[f"{pulse}_blockade_excess"] = c["ff"] - predicted
        result["pi_minus_sham_blockade_excess"] = (
            result["pi_blockade_excess"] -
            result["sham_blockade_excess"])
    return result


def score_entry(entry):
    return score({c["name"]: c["excited_fraction_pre_axis"]
                  for c in entry["conditions"]})


def report(specs, scores):
    result = {}
    for gap in GAPS_US:
        entries = [entry for entry in specs if entry["gap_us"] == gap]
        values = [scores[entry["name"]]["pi_minus_sham_blockade_excess"]
                  for entry in entries]
        result[str(gap)] = {
            "repeat_scores": values,
            "mean_score": (float(np.mean(values))
                           if all(value is not None for value in values)
                           else None),
            "same_positive_sign": bool(all(value is not None and value > 0
                                           for value in values)),
        }
    return result


def plan():
    return {"hardware_access": False,
            "goal": "test whether a loss feature blocks a second excitation",
            "load_us": LOAD_US, "probe_us": PROBE_US,
            "gaps_us": list(GAPS_US),
            "middle_pulse": "park pi or matched zero-gain sham",
            "middle_pulse_start_after_first_return_us": PARK_SETTLE_BEFORE_PI_US,
            "intermediate_readouts": 0,
            "conditions_per_shot": 16, "programs": 4,
            "shots_per_program": SHOTS,
            "control": "four visit pairs x initial g/e x middle pi/sham",
            "primary_score": "pi minus sham nonfactorization of g/e contrast",
            "interpretation": "positive short-gap score with controls is a "
                              "candidate one-excitation blockade, not TLS proof"}


def run(*, data_root=localizer.DATA_ROOT, correction_json=None):
    data_root = Path(data_root)
    correction = localizer.checked_correction(data_root, correction_json)
    scout = localizer.run(
        data_root=data_root, correction_json=correction,
        parameter_overrides={**heralded.postselection_scout_parameters("pre"),
                             "output_suffix": "TLS_Second_Quantum_Blockade_Scout_pre"})
    selected = heralded.select_postselection_feature(
        heralded.read_postselection_scout(scout))
    center, control = selected["center_ghz"], selected["control_ghz"]
    print(f"[blockade] feature={center:.3f} GHz; "
          f"control={control:.3f} GHz", flush=True)

    with localizer.scan_environment(correction):
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
            FivePointApplesToApples as five, TLSSpectroscopy as tls,
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
        specs = program_specs(center, control)
        grid = np.asarray(sorted((center, control)), dtype=float)
        dc, realized = _integer_dc_grid(wide.parameters(), grid, tls)
        dc_lookup = {float(f): int(g) for f, g in zip(grid, dc)}
        compensation = tls._load_correction(str(correction), str(data_root))
        park = float(tls.BaseConfig["ff_park_gain"])
        for entry in specs:
            for condition in entry["conditions"]:
                first = dc_lookup[condition["load_ghz"]]
                second = dc_lookup[condition["probe_ghz"]]
                memory.two_visit_segments(
                    compensation, load_us=LOAD_US,
                    store_us=condition["gap_us"], probe_us=PROBE_US,
                    second_amplitude=(second - park) / (first - park))
        base = ProductionResetSession.passive().apply(tls.BaseConfig)
        five.apply_verified_feedback_timing(base)
        base.update({"apply_flux_tail_compensation": True,
                     "flux_tail_compensation": compensation,
                     "flux_fit_params": tls.FLUX_FIT_PARAMS,
                     "flux_settle_time_us": 0.5,
                     "flux_predistortion_return_prefix_us": 0.5,
                     "flux_predistortion_recovery_us": RECOVERY_US,
                     "flux_predistortion_overlap_payload_readout": False,
                     "flux_predistortion_round_trip_mode": "stateful",
                     "readout_thermalization_us": 10.0,
                     "qubit_pulse_style": "arb", "do_ff": True,
                     "opx_reset_scheme": "none",
                     "opx_resident_dmem_stream": True,
                     "opx_inter_shot_delay_us": 500.0})
        session_id = ("q3_tls_second_quantum_blockade_" +
                      datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") +
                      "_" + uuid.uuid4().hex[:8])
        folder = data_root / "q3" / session_id
        folder.mkdir(parents=True, exist_ok=False)
        path = folder / "manifest.json"
        refs = (probe.reference_arms(center, phase="pre") +
                probe.reference_arms(center, phase="post"))
        for ref in refs:
            ref.update(shots=REFERENCE_SHOTS, status="pending")
        manifest = {
            "schema": "q3.tls-second-quantum-blockade.v1",
            "status": "running", "session_id": session_id,
            "code_commit": os.environ.get("Q3_CODE_COMMIT", "unknown"),
            "correction_json": str(correction),
            "correction_sha256": localizer.CORRECTION_SHA256,
            "scout_csv": str(scout), "selected": selected,
            "center_ghz": center, "control_ghz": control,
            "dc_lookup": dc_lookup, "realized_ghz": realized.tolist(),
            "plan": plan(), "references": refs, "programs": specs,
        }
        protocol.checkpoint(path, manifest)
        print(f"[blockade] manifest={path}", flush=True)
        raw_refs = {}
        axis = None
        try:
            soc, soccfg = tls.makeProxy()
            bundle = runtime_bundle(base)
            programs = {}
            for entry in specs:
                configs = [arm_config(base, c, dc_lookup, shots=entry["shots"])
                           for c in entry["conditions"]]
                programs[entry["name"]] = BlockadeProgram(
                    soccfg, configs, bundle.payload, bundle.loop)
            for ref in refs:
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
                records = _run_program(
                    soc, resident.ResidentDriveProgram(
                        soccfg, cfg, bundle.payload, bundle.loop),
                    max(30.0, _block_timeout_s(cfg, REFERENCE_SHOTS)),
                    cfg, total_shots=REFERENCE_SHOTS)
                if len(records) != REFERENCE_SHOTS:
                    raise RuntimeError(f"{ref['name']}: incomplete reference IQ")
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
                        raise RuntimeError("pre-run readout reference invalid")
                if axis is not None:
                    ref["excited_fraction_pre_axis"] = resident.classify(
                        records, axis)
                ref["status"] = "complete"
                protocol.checkpoint(path, manifest)

            for ref in refs[:4]:
                print(f"[blockade] {ref['name']}", flush=True)
                acquire_ref(ref)
            for entry in specs:
                shots = int(entry["shots"])
                print(f"[blockade] {entry['name']} {shots} x 16", flush=True)
                entry["status"] = "acquiring"
                protocol.checkpoint(path, manifest)
                entry["acquisition_started_at_utc"] = (
                    datetime.now(timezone.utc).isoformat())
                started = time.monotonic()
                records = _run_program(
                    soc, programs[entry["name"]],
                    max(30.0, 16 * _block_timeout_s(base, shots)),
                    base, total_shots=shots)
                entry["acquisition_elapsed_s"] = time.monotonic() - started
                entry["acquisition_finished_at_utc"] = (
                    datetime.now(timezone.utc).isoformat())
                split = split_records(records, entry["order"], shots=shots)
                for cond in entry["conditions"]:
                    subset = split[cond["name"]]
                    raw_path = folder / f"{entry['name']}_{cond['name']}.npz"
                    np.savez_compressed(raw_path, i=[r.i for r in subset],
                                        q=[r.q for r in subset])
                    cond["raw_npz"] = str(raw_path)
                    cond["excited_fraction_pre_axis"] = resident.classify(
                        subset, axis)
                entry["score"] = score_entry(entry)
                entry["status"] = "complete"
                protocol.checkpoint(path, manifest)
            for ref in refs[4:]:
                print(f"[blockade] {ref['name']}", flush=True)
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
                item["usable"] = resident.transfer_usable(
                    item["ground"], item["excited"])
            scores = {entry["name"]: entry["score"] for entry in specs}
            manifest["blockade_report"] = report(specs, scores)
            post_scout = localizer.run(
                data_root=data_root, correction_json=correction,
                parameter_overrides={**heralded.postselection_scout_parameters("post"),
                                     "output_suffix": "TLS_Second_Quantum_Blockade_Scout_post"})
            manifest["post_scout_csv"] = str(post_scout)
            try:
                manifest["post_selected"] = (
                    heralded.select_postselection_feature(
                        heralded.read_postselection_scout(post_scout)))
            except ValueError as exc:
                manifest["post_selection_error"] = str(exc)
            manifest["feature_stable"] = bool(
                "post_selected" in manifest and
                resident.feature_stable(selected, manifest["post_selected"]))
            manifest["status"] = (
                "complete" if manifest["post_readout_score"]["valid"] and
                all(item["usable"] for item in
                    manifest["transfer_control"].values()) and
                all(item["usable"] for item in scores.values()) and
                manifest["feature_stable"] else "complete_controls_unstable")
            protocol.checkpoint(path, manifest)
            print(f"[blockade] {manifest['status']}: {path}", flush=True)
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
    parser.add_argument("--data-root", default=str(localizer.DATA_ROOT))
    parser.add_argument("--correction-json")
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(plan(), indent=2))
        return 0
    run(data_root=args.data_root, correction_json=args.correction_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
