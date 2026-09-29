"""Measure loss at the center and first 30-MHz modulation sidebands on q3.

The scan follows a fresh, qualified loss feature. Within each program, AC
off/on, two target dwells, and ground/excited preparations are interleaved.
Two blocks reverse frequency order and re-center after a midpoint scout.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import uuid

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSFloquetJ0Pilot as j0,
    TLSFloquetSwitch as switch,
    TLSFluxModulatedT1 as modulated,
    TLSPumpProbeLocalizer as localizer,
    TLSPumpProbeProtocolCheck as protocol,
    TLSPumpProbeResidentDrive as resident,
    TLSPumpProbeResidentProbe as probe,
    TLSPumpProbeWidePassiveScan as wide,
    TLSSwapHoldPilot as swap,
)


OFFSETS_MHZ = (-34, -32, -30, -28, -26, 0, 26, 28, 30, 32, 34)
TRANSLATION_OFFSETS_MHZ = (-38, -36, -34, -32, -30, -28, -26, -24, -22, 0)
TRANSLATION_FREQUENCIES_MHZ = (25.0, 35.0)
MODULATION_MHZ = 30.0
AMPLITUDE_DAC = 1000
HOLDS_US = (1.6, 5.6)
PRE_US = 0.05
SHOTS = 4000
REFERENCE_SHOTS = 400
LABEL = "TLS_Floquet_Sideband_Loss"


def plan(*, translation_check=False):
    offsets = (TRANSLATION_OFFSETS_MHZ if translation_check else OFFSETS_MHZ)
    return {"hardware_access": False, "reset_mode": "passive",
            "purpose": ("test whether lower loss sideband moves with modulation frequency"
                        if translation_check else
                        "look for mirrored narrow loss peaks at first Floquet sidebands"),
            "fresh_wide_scout": "3.8-4.3 GHz corrected five-point scan",
            "offsets_mhz": list(offsets),
            "modulation_frequencies_mhz": (list(TRANSLATION_FREQUENCIES_MHZ)
                                           if translation_check else [MODULATION_MHZ]),
            "amplitude_dac": AMPLITUDE_DAC,
            "holds_us": list(HOLDS_US),
            "pre_target_hold_us": PRE_US,
            "blocks": 2, "shots_per_program": SHOTS,
            "conditions_per_shot": modulated.RECORDS_PER_SHOT,
            "full_return_before_readout_us": 40.0,
            "raw_iq_and_compiled_waveforms_saved": True}


def _entry(feature, offset, repeat, *, shots=SHOTS,
           modulation_mhz=MODULATION_MHZ):
    target = round(float(feature) + offset / 1000.0, 3)
    conditions = modulated.conditions(
        target, amplitude_dac=AMPLITUDE_DAC,
        reverse=bool(repeat), holds_us=HOLDS_US, pre_us=PRE_US)
    label = "c" if offset == 0 else f"{'m' if offset < 0 else 'p'}{abs(offset)}"
    prefix = (f"r{repeat}_f{modulation_mhz:g}_" if
              modulation_mhz != MODULATION_MHZ else f"r{repeat}_")
    return {"name": f"{prefix}{label}", "repeat": repeat,
            "feature_ghz": float(feature), "center_ghz": target,
            "offset_mhz": offset, "modulation_mhz": modulation_mhz,
            "shots": int(shots),
            "order": [row["name"] for row in conditions],
            "conditions": conditions, "status": "pending"}


def program_specs(feature, *, shots=SHOTS, translation_check=False):
    center = round(float(feature), 3)
    offsets = (TRANSLATION_OFFSETS_MHZ if translation_check else OFFSETS_MHZ)
    frequencies = (TRANSLATION_FREQUENCIES_MHZ if translation_check else
                   (MODULATION_MHZ,))
    if center + min(offsets) / 1000.0 < 3.8 or (
            center + max(offsets) / 1000.0 > 4.3):
        raise ValueError("sideband windows lie outside the 3.8-4.3 GHz wide scout")
    settings = [(frequency, offset) for offset in offsets
                for frequency in frequencies]
    return [_entry(center, offset, repeat, shots=shots,
                   modulation_mhz=frequency)
            for repeat in (0, 1)
            for frequency, offset in (settings if repeat == 0 else settings[::-1])]


def recenter_repeat(specs, *, center, repeat):
    pending = [item for item in specs if item["repeat"] == repeat]
    if any(item["status"] != "pending" for item in pending):
        raise ValueError("cannot retarget an acquired sideband program")
    program_specs(center, shots=pending[0]["shots"],
                  translation_check=(pending[0]["modulation_mhz"] !=
                                     MODULATION_MHZ))
    for item in pending:
        item.update(_entry(center, item["offset_mhz"], repeat,
                           shots=item["shots"],
                           modulation_mhz=item["modulation_mhz"]))


def _survival(row, direction):
    suffix = "" if not direction else f"_scan_{direction}"
    p0 = float(row[f"P0{suffix}"])
    p1 = float(row[f"P1{suffix}"])
    p25 = float(row[f"Ps_25us{suffix}"])
    if not np.all(np.isfinite((p0, p1, p25))) or p1 - p0 < .25:
        raise ValueError("unusable wide-scout reference contrast")
    return (p25 - p0) / (p1 - p0)


def validate_sideband_windows(rows, feature):
    """Require low-loss ±30-MHz windows before interpreting sideband gain."""
    indexed = {round(float(row["target_frequency_ghz"]), 3): row
               for row in rows}
    if len(rows) != 251 or len(indexed) != 251:
        raise ValueError("sideband preflight needs a complete wide scout")
    feature = round(float(feature), 3)
    advantages = {}
    window_survival = {}
    for direction in ("", "up", "down"):
        center = _survival(indexed[feature], direction)
        for side, offsets in (("left", OFFSETS_MHZ[:5]),
                              ("right", OFFSETS_MHZ[-5:])):
            values = [_survival(indexed[round(feature + off / 1000.0, 3)],
                                direction) for off in offsets]
            key = f"{side}{'_' + direction if direction else ''}"
            window_survival[key] = float(np.median(values))
            advantages[key] = window_survival[key] - center
    usable = (min(advantages["left"], advantages["right"]) >= .15 and
              min(advantages[f"{side}_{direction}"]
                  for side in ("left", "right")
                  for direction in ("up", "down")) >= .08 and
              min(window_survival.values()) >= .60)
    return {**{f"{key}_advantage": value for key, value in advantages.items()},
            **{f"{key}_survival": value
               for key, value in window_survival.items()},
            "usable": bool(usable)}


def validate_translation_window(rows, feature):
    """Require a quiet lower flank over both predicted peak positions."""
    indexed = {round(float(row["target_frequency_ghz"]), 3): row
               for row in rows}
    if len(rows) != 251 or len(indexed) != 251:
        raise ValueError("translation preflight needs a complete wide scout")
    feature = round(float(feature), 3)
    report = {}
    for direction in ("", "up", "down"):
        center = _survival(indexed[feature], direction)
        values = [_survival(indexed[round(feature + off / 1000.0, 3)],
                            direction)
                  for off in TRANSLATION_OFFSETS_MHZ if off != 0]
        label = direction or "combined"
        report[f"{label}_median_survival"] = float(np.median(values))
        report[f"{label}_min_survival"] = float(min(values))
        report[f"{label}_advantage"] = float(np.median(values) - center)
    report["usable"] = bool(
        min(report[f"{direction}_median_survival"]
            for direction in ("combined", "up", "down")) >= .60 and
        min(report[f"{direction}_min_survival"]
            for direction in ("combined", "up", "down")) >= .45 and
        report["combined_advantage"] >= .15 and
        min(report["up_advantage"], report["down_advantage"]) >= .08)
    return report


def select_candidate(rows, *, preferred_center, translation_check=False):
    candidate_filter = None
    if translation_check:
        candidate_filter = lambda item: (
            round(item["center_ghz"] +
                  min(TRANSLATION_OFFSETS_MHZ) / 1000.0, 3) >= 3.8 and
            validate_translation_window(
                rows, item["center_ghz"])["usable"])
    return switch.select_switch_candidate(
        rows, preferred_center=preferred_center,
        candidate_filter=candidate_filter)


def run(*, data_root=localizer.DATA_ROOT, correction_json=None,
        translation_check=False):
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

    data_root = Path(data_root)
    label = f"{LABEL}_Translation" if translation_check else LABEL
    window_check = (validate_translation_window if translation_check else
                    validate_sideband_windows)

    correction = localizer.checked_correction(data_root, correction_json)
    scout = localizer.run(
        data_root=data_root, correction_json=correction,
        parameter_overrides={**wide.parameters(),
                             "output_suffix": f"{label}_Scout_pre"})
    scout_rows = swap.read_wide_scout(scout)
    selected = select_candidate(scout_rows, preferred_center=4.106,
                                translation_check=translation_check)
    center = round(float(selected["center_ghz"]), 3)
    specs = program_specs(center, translation_check=translation_check)
    first_block_size = len(specs) // 2
    windows = window_check(scout_rows, center)
    if not windows["usable"]:
        raise ValueError(f"fresh feature has occupied modulation windows: {windows}")
    print(f"[sideband-loss] feature={center:.3f} GHz; "
          f"window check={windows}", flush=True)

    with localizer.scan_environment(correction):
        if int(tls.BaseConfig["ff_park_gain"]) != -25146:
            raise RuntimeError("q3 park gain differs from verified configuration")
        tls.QUBIT, tls.SET_YOKO, tls.outerFolder = "q3", False, str(data_root)
        five.install_scan_calibration(tls)
        grid = np.asarray(sorted({item["center_ghz"]
                                  for item in specs[:first_block_size]}))
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
                     "ff_ramp_length": modulated.PARK_RAMP_US,
                     "qubit_pulse_style": "arb", "do_ff": True,
                     "opx_reset_scheme": "none",
                     "opx_resident_dmem_stream": True,
                     "opx_inter_shot_delay_us": 500.0})
        for hold in HOLDS_US:
            modulated._target_segments(
                compensation, pre_us=PRE_US + .5, hold_us=hold,
                recovery_us=40.0)

        session_id = (("q3_floquet_sideband_translation_" if translation_check
                       else "q3_floquet_sideband_loss_") +
                      datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") +
                      "_" + uuid.uuid4().hex[:8])
        folder = data_root / "q3" / session_id
        folder.mkdir(parents=True, exist_ok=False)
        path = folder / "manifest.json"
        refs = (probe.reference_arms(center, phase="pre") +
                probe.reference_arms(center, phase="post"))
        for ref in refs:
            ref["shots"] = REFERENCE_SHOTS
            ref["status"] = "pending"
        manifest = {"schema": "q3.floquet-sideband-loss.v1",
                    "status": "running", "session_id": session_id,
                    "code_commit": os.environ.get("Q3_CODE_COMMIT", "unknown"),
                    "correction_json": str(correction),
                    "correction_sha256": localizer.CORRECTION_SHA256,
                    "scout_csv": str(scout), "selected": selected,
                    "center_ghz": center, "sideband_windows_pre": windows,
                    "dc_lookup": dc_lookup,
                    "realized_ghz": realized.tolist(),
                    "plan": plan(translation_check=translation_check),
                    "translation_check": bool(translation_check),
                    "references": refs,
                    "programs": specs}
        protocol.checkpoint(path, manifest)
        print(f"[sideband-loss] manifest={path}", flush=True)

        raw_refs = {}
        axis = None
        try:
            soc, soccfg = tls.makeProxy()
            bundle = runtime_bundle(base)
            programs = {}

            def compile_entry(entry):
                cfgs = modulated._condition_configs(base, entry, dc_lookup)
                program = modulated.ModulatedT1Program(
                    soccfg, cfgs, bundle.payload, bundle.loop,
                    holds_us=HOLDS_US, pre_us=PRE_US,
                    allowed_amplitudes=(AMPLITUDE_DAC,),
                    modulation_mhz=entry["modulation_mhz"])
                entry["waveform_reports"] = program.ac_reports
                entry["ff_envelope_report"] = program.ff_envelope_report
                for hold, samples in program.ac_waveforms.items():
                    wave_path = folder / f"{entry['name']}_waveform_{hold}.npz"
                    np.savez_compressed(wave_path, idata=samples)
                    entry.setdefault("waveform_npz", {})[hold] = str(wave_path)
                programs[entry["name"]] = program

            for entry in specs[:first_block_size]:
                compile_entry(entry)
            for ref in refs[:4]:
                resident.ResidentDriveProgram(
                    soccfg, resident.arm_config(base, ref, dc_lookup),
                    bundle.payload, bundle.loop)
            manifest["first_block_preflight_complete"] = True
            protocol.checkpoint(path, manifest)

            def acquire_ref(ref):
                nonlocal axis
                cfg = resident.arm_config(base, ref, dc_lookup)
                ref["status"] = "acquiring"
                protocol.checkpoint(path, manifest)
                program = resident.ResidentDriveProgram(
                    soccfg, cfg, bundle.payload, bundle.loop)
                records = _run_program(
                    soc, program,
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
                print(f"[sideband-loss] {ref['name']}", flush=True)
                acquire_ref(ref)

            for entry in specs:
                if entry["repeat"] == 1 and "mid_selected" not in manifest:
                    mid_scout = localizer.run(
                        data_root=data_root, correction_json=correction,
                        parameter_overrides={**wide.parameters(),
                                             "output_suffix": f"{label}_Scout_mid"})
                    mid_rows = swap.read_wide_scout(mid_scout)
                    mid_selected = select_candidate(
                        mid_rows, preferred_center=center,
                        translation_check=translation_check)
                    mid_center = round(float(mid_selected["center_ghz"]), 3)
                    if abs(mid_center - center) > .004001:
                        raise RuntimeError("midpoint scout no longer selects the same loss site")
                    mid_windows = window_check(mid_rows, mid_center)
                    manifest.update({"mid_scout_csv": str(mid_scout),
                                     "mid_selected": mid_selected,
                                     "mid_center_ghz": mid_center,
                                     "sideband_windows_mid": mid_windows})
                    protocol.checkpoint(path, manifest)
                    if not mid_windows["usable"]:
                        raise RuntimeError("modulation windows became occupied")
                    recenter_repeat(specs, center=mid_center, repeat=1)
                    mid_grid = np.asarray(sorted({x["center_ghz"]
                                                  for x in specs[first_block_size:]}))
                    mid_dc, mid_realized = _integer_dc_grid(
                        wide.parameters(), mid_grid, tls)
                    dc_lookup.update({float(f): int(g)
                                      for f, g in zip(mid_grid, mid_dc)})
                    manifest["mid_realized_ghz"] = mid_realized.tolist()
                    for ref in refs[4:]:
                        ref["flux_ghz"] = mid_center
                        ref["drive_mhz"] = round(1000.0 * mid_center + 5.0, 3)
                        resident.ResidentDriveProgram(
                            soccfg, resident.arm_config(base, ref, dc_lookup),
                            bundle.payload, bundle.loop)
                    for future in specs[first_block_size:]:
                        compile_entry(future)
                    manifest["preflight_complete"] = True
                    protocol.checkpoint(path, manifest)
                    print(f"[sideband-loss] midpoint feature={mid_center:.3f} GHz",
                          flush=True)

                print(f"[sideband-loss] {entry['name']} "
                      f"{entry['center_ghz']:.3f} GHz", flush=True)
                entry["status"] = "acquiring"
                protocol.checkpoint(path, manifest)
                records = _run_program(
                    soc, programs[entry["name"]],
                    max(30.0, modulated.RECORDS_PER_SHOT *
                        _block_timeout_s(base, entry["shots"])),
                    base, total_shots=entry["shots"])
                split = j0.split_records(records, entry["order"],
                                         shots=entry["shots"])
                for condition in entry["conditions"]:
                    subset = split[condition["name"]]
                    raw_path = folder / f"{entry['name']}_{condition['name']}.npz"
                    np.savez_compressed(raw_path, i=[r.i for r in subset],
                                        q=[r.q for r in subset])
                    condition["raw_npz"] = str(raw_path)
                    condition["excited_fraction_pre_axis"] = resident.classify(
                        subset, axis)
                fractions = {c["name"]: c["excited_fraction_pre_axis"]
                             for c in entry["conditions"]}
                entry["score"] = modulated.score_conditions(fractions)
                entry["controls_usable"] = j0._score_usable(
                    {"kind": "ac"}, entry["score"])
                entry["status"] = "complete"
                protocol.checkpoint(path, manifest)
                print(f"[sideband-loss] {entry['name']} loss suppression="
                      f"{entry['score']['modulation_survival_change']:+.4f} "
                      f"controls={entry['controls_usable']}", flush=True)

            for ref in refs[4:]:
                print(f"[sideband-loss] {ref['name']}", flush=True)
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
            post_scout = localizer.run(
                data_root=data_root, correction_json=correction,
                parameter_overrides={**wide.parameters(),
                                     "output_suffix": f"{label}_Scout_post"})
            manifest["post_scout_csv"] = str(post_scout)
            try:
                post_rows = swap.read_wide_scout(post_scout)
                manifest["post_selected"] = select_candidate(
                    post_rows, preferred_center=manifest["mid_center_ghz"],
                    translation_check=translation_check)
                manifest["sideband_windows_post"] = window_check(
                    post_rows, manifest["post_selected"]["center_ghz"])
            except ValueError as exc:
                manifest["post_selection_error"] = str(exc)
            if "post_selected" in manifest:
                manifest["block_stability"] = modulated.block_stability(
                    selected, manifest["mid_selected"],
                    manifest["post_selected"])
                manifest["feature_stable"] = all(
                    manifest["block_stability"].values())
            else:
                manifest["feature_stable"] = False
            valid = (manifest["post_readout_score"]["valid"] and
                     all(x["usable"] for x in manifest["transfer_control"].values())
                     and all(x["controls_usable"] for x in specs) and
                     manifest["feature_stable"] and
                     manifest.get("sideband_windows_post", {}).get("usable", False))
            manifest["status"] = ("complete" if valid else
                                  "complete_controls_unstable")
            protocol.checkpoint(path, manifest)
            print(f"[sideband-loss] {manifest['status']}: {path}", flush=True)
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
    parser.add_argument("--translation-check", action="store_true",
                        help="compare 25 and 35 MHz at fixed 1000-DAC amplitude")
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(plan(translation_check=args.translation_check), indent=2))
    else:
        run(data_root=args.data_root, correction_json=args.correction_json,
            translation_check=args.translation_check)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
