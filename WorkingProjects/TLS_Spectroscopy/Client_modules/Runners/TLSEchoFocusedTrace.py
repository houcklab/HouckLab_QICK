"""Repeat the q3 4.21-GHz echo candidate with a dense delay trace.

Two reversed blocks cover fixed sites around the blind-map candidate and
two quieter controls. Each site has local one-pulse turnover and two-pulse
phase checks bracketing seven four-phase Hahn-echo delays. Ordinary narrow
five-point scans before and after show whether the loss line moved. Neither
scan selects or gates the echo sites. All raw IQ is saved.
"""

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import subprocess
import uuid

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSEchoFastSquarePilot as fast,
    TLSEchoSquareMap as square,
    TLSPumpProbeLocalizer as localizer,
)


SITES_GHZ = (4.2, 4.204, 4.208, 4.212, 4.216, 4.22, 4.232, 4.284)
DELAYS_US = (.15, .3, .5, .8, 1.2, 1.8, 2.6)
PHASES_DEG = (0, 90, 180, 270)
SHOTS = 800
PRE_US = square.PRE_US
POST_US = square.POST_US
PI_US = square.PI_US
PI2_US = square.PI2_US
TWO_PI_US = 2 * PI_US


def schedule(block):
    if block not in (0, 1):
        raise ValueError("focused trace has exactly two reversed blocks")
    sites = SITES_GHZ if block == 0 else tuple(reversed(SITES_GHZ))
    delays = DELAYS_US if block == 0 else tuple(reversed(DELAYS_US))
    phases = PHASES_DEG if block == 0 else tuple(reversed(PHASES_DEG))
    return [{"frequency_ghz": frequency,
             "echo_arms": [(delay, phase) for delay in delays
                           for phase in phases],
             "control_pre_phases": phases,
             "control_post_phases": tuple(reversed(phases))}
            for frequency in sites]


def rabi_gate(half_response, twice_response):
    half, twice = float(half_response), float(twice_response)
    return {"valid": bool(math.isfinite(half) and math.isfinite(twice) and
                          .25 <= half <= .75 and -.2 <= twice <= .25),
            "pi2_response": half, "two_pi_response": twice}


def trace_report(cycles):
    visibilities = {float(delay): square.phase_visibility(values)
                    for delay, values in cycles.items()}
    if set(visibilities) != set(DELAYS_US):
        raise ValueError("focused trace needs every planned delay")
    ordered = [visibilities[delay]["visibility"] for delay in DELAYS_US]
    revivals = sum(b - a > .10 for a, b in zip(ordered, ordered[1:]))
    usable = [(delay, value) for delay, value in zip(DELAYS_US, ordered)
              if .06 <= value <= 2.]
    report = {"visibility": visibilities, "revival_count": revivals,
              "fit_points": len(usable)}
    if len(usable) < 4:
        report["status"] = "insufficient_echo_contrast"
        return report
    times = np.asarray([item[0] for item in usable])
    logs = np.log([item[1] for item in usable])
    slope, intercept = np.polyfit(times, logs, 1)
    residual = logs - (slope * times + intercept)
    report.update({"status": "fit",
                   "rate_per_us": float(-slope),
                   "t2_echo_us": float(-1 / slope) if slope < 0 else None,
                   "log_fit_rms": float(np.sqrt(np.mean(residual ** 2)))})
    return report


def scout_parameters(phase):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
        TLSPumpProbeWidePassiveScan as wide,
    )
    return {**wide.parameters(), "freq_min_ghz": 4.18,
            "freq_max_ghz": 4.29, "freq_step_mhz": 2.,
            "output_suffix": f"TLS_Echo_Focused_Trace_{phase}_T1"}


def plan():
    return {"hardware_access": False,
            "purpose": "test whether the 4.212-GHz echo-rate peak repeats",
            "sites_ghz": list(SITES_GHZ),
            "delays_us": list(DELAYS_US),
            "phase_cycle_deg": list(PHASES_DEG),
            "shots_per_arm": SHOTS, "reversed_blocks": 2,
            "one_pulse_half_and_two_pi_checks_at_each_site": True,
            "two_pulse_phase_controls_before_and_after_echo": True,
            "t1_scans": "narrow pre and post; no site selection",
            "native_corrected_return_us": 40.,
            "terminal": "no custom progress messages"}


def run(*, data_root=None, correction_json=None):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
        FivePointApplesToApples as five,
        TLSDualTransitionLoss as dual,
        TLSPumpProbeResidentDrive as resident,
        TLSPumpProbeWidePassiveScan as wide,
        TLSSpectroscopy as tls,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.ThreePointApplesToApples import _integer_dc_grid
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import (
        _block_timeout_s, _run_program, runtime_bundle,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import ProductionResetSession

    data_root = Path(data_root or localizer.DATA_ROOT)
    correction = localizer.checked_correction(data_root, correction_json)
    source_path = data_root / "q3" / square.SOURCE_SESSION / "manifest.json"
    square.validate_source(json.loads(source_path.read_text(encoding="utf-8")))
    session_id = ("q3_echo_focused_trace_" +
                  datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") +
                  "_" + uuid.uuid4().hex[:8])
    folder = data_root / "q3" / session_id
    folder.mkdir(parents=True, exist_ok=False)
    path = folder / "manifest.json"
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[4], text=True,
            stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
    manifest = {"schema": "q3.echo-focused-trace.v1", "status": "running",
                "session_id": session_id, "code_commit": commit,
                "source_manifest": str(source_path),
                "correction_json": str(correction),
                "correction_sha256": localizer.CORRECTION_SHA256,
                "plan": plan(), "blocks": []}
    dual.checkpoint(path, manifest)
    try:
        manifest["t1_pre_csv"] = str(localizer.run(
            data_root=data_root, correction_json=correction,
            parameter_overrides=scout_parameters("pre"), announce=False))
        dual.checkpoint(path, manifest)
        with localizer.scan_environment(correction):
            tls.QUBIT, tls.SET_YOKO, tls.outerFolder = "q3", False, str(data_root)
            five.install_scan_calibration(tls)
            base = ProductionResetSession.passive().apply(tls.BaseConfig)
            five.apply_verified_feedback_timing(base)
            if int(base["ff_park_gain"]) != -25146:
                raise RuntimeError("q3 park gain differs from verified setting")
            dc, realized = _integer_dc_grid(wide.parameters(),
                                            np.asarray(SITES_GHZ), tls)
            dc_lookup = {frequency: int(gain)
                         for frequency, gain in zip(SITES_GHZ, dc)}
            manifest["realized_frequency_ghz"] = realized.tolist()
            base.update({"apply_flux_tail_compensation": True,
                         "flux_tail_compensation": tls._load_correction(
                             str(correction), str(data_root)),
                         "flux_fit_params": tls.FLUX_FIT_PARAMS,
                         "flux_settle_time_us": .5,
                         "flux_predistortion_return_prefix_us": .5,
                         "flux_predistortion_recovery_us": 40.,
                         "flux_predistortion_overlap_payload_readout": False,
                         "flux_predistortion_round_trip_mode": "stateful",
                         "readout_thermalization_us": 10.,
                         "qubit_pulse_style": "arb", "do_ff": True,
                         "opx_reset_scheme": "none",
                         "opx_resident_dmem_stream": True,
                         "opx_inter_shot_delay_us": 500.})
            control_class = fast.make_program(resident.ResidentDriveProgram)
            echo_class = square.make_echo_program(resident.ResidentDriveProgram)
            soc, soccfg = tls.makeProxy()
            bundle = runtime_bundle(base)

            def configuration(frequency, kind, *, phase=0, delay=None,
                              duration=None):
                arm = {"flux_ghz": frequency,
                       "drive_mhz": 1000 * frequency + square.DRIVE_OFFSET_MHZ,
                       "gain": square.GAIN_DAC,
                       "reference_state": None,
                       "preparation_state": "g", "pre_drive_us": PRE_US,
                       "post_drive_us": POST_US, "shots": SHOTS}
                cfg = resident.arm_config(base, arm, dc_lookup)
                if kind == "echo":
                    cfg["echo_delay_us"] = float(delay)
                    cfg["echo_phase_deg"] = int(phase)
                    cfg["ff_hold"] = PRE_US + POST_US + square.echo_window_us(delay)
                else:
                    cfg["fast_pulse_us"] = float(
                        duration if duration is not None else
                        (PI2_US if kind in ("zero", "control") else PI_US))
                    cfg["fast_second_phase_deg"] = (
                        int(phase) if kind == "control" else None)
                    cfg["opx_resident_gain"] = (0 if kind == "zero"
                                                else square.GAIN_DAC)
                    count = 2 if kind == "control" else 1
                    cfg["ff_hold"] = (PRE_US + POST_US + count *
                                      (cfg["fast_pulse_us"] + .01))
                return cfg

            for frequency in (SITES_GHZ[0], SITES_GHZ[-1]):
                for kind, delay in (("control", None),
                                    ("echo", DELAYS_US[0]),
                                    ("echo", DELAYS_US[-1])):
                    cfg = configuration(frequency, kind, phase=270, delay=delay)
                    (echo_class if kind == "echo" else control_class)(
                        soccfg, cfg, bundle.payload, bundle.loop)
            manifest["compiled_edges"] = True
            dual.checkpoint(path, manifest)

            def acquire(frequency, kind, *, phase=0, delay=None,
                        duration=None):
                cfg = configuration(frequency, kind, phase=phase,
                                    delay=delay, duration=duration)
                program = (echo_class if kind == "echo" else control_class)(
                    soccfg, cfg, bundle.payload, bundle.loop)
                records = _run_program(
                    soc, program, max(30., _block_timeout_s(cfg, SHOTS)),
                    cfg, total_shots=SHOTS)
                if len(records) != SHOTS:
                    raise RuntimeError("incomplete focused-echo IQ records")
                return resident.record_iq(records)

            for block in (0, 1):
                block_entry = {"index": block, "sites": []}
                manifest["blocks"].append(block_entry)
                dual.checkpoint(path, manifest)
                for entry in schedule(block):
                    frequency = entry["frequency_ghz"]
                    raw = {}
                    zero_pre = acquire(frequency, "zero")
                    pi_pre = acquire(frequency, "pi")
                    raw["zero_pre"], raw["pi_pre"] = zero_pre, pi_pre
                    acquired = []

                    def take(name, kind, *, phase=0, delay=None,
                             duration=None):
                        iq = acquire(frequency, kind, phase=phase,
                                     delay=delay, duration=duration)
                        raw[name] = iq
                        acquired.append((name, iq))

                    take("rabi_half", "pi", duration=PI2_US)
                    take("rabi_twice", "pi", duration=TWO_PI_US)
                    for phase in entry["control_pre_phases"]:
                        take(f"control_pre_{phase}", "control", phase=phase)
                    for delay, phase in entry["echo_arms"]:
                        take(f"echo_{round(delay * 1000)}ns_{phase}", "echo",
                             phase=phase, delay=delay)
                    for phase in entry["control_post_phases"]:
                        take(f"control_post_{phase}", "control", phase=phase)
                    zero_post = acquire(frequency, "zero")
                    pi_post = acquire(frequency, "pi")
                    raw["zero_post"], raw["pi_post"] = zero_post, pi_post
                    raw_path = folder / f"block{block}_{round(1000*frequency)}MHz.npz"
                    np.savez_compressed(raw_path, **{
                        f"{name}_i": iq.real.astype(np.int64)
                        for name, iq in raw.items()}, **{
                        f"{name}_q": iq.imag.astype(np.int64)
                        for name, iq in raw.items()})
                    refs = (zero_pre.mean(), pi_pre.mean(),
                            zero_post.mean(), pi_post.mean())
                    bracket = fast.score_reference_bracket(*refs)
                    point = {"frequency_ghz": frequency,
                             "raw_npz": str(raw_path),
                             "reference_bracket": bracket,
                             "status": "unresolved_reference"}
                    if bracket["valid"]:
                        responses = {name: fast.bracketed_response(
                            iq.mean(), *refs, (position + 1) /
                            (len(acquired) + 1))
                            for position, (name, iq) in enumerate(acquired)}
                        point["rabi_gate"] = rabi_gate(
                            responses["rabi_half"], responses["rabi_twice"])
                        controls = {
                            label: {phase: responses[f"{label}_{phase}"]
                                    for phase in PHASES_DEG}
                            for label in ("control_pre", "control_post")}
                        point["control_gate"] = square.control_stability_gate(
                            controls["control_pre"], controls["control_post"])
                        cycles = {delay: {
                            phase: responses[f"echo_{round(delay*1000)}ns_{phase}"]
                            for phase in PHASES_DEG} for delay in DELAYS_US}
                        point["rabi_responses"] = {
                            "half": responses["rabi_half"],
                            "twice": responses["rabi_twice"]}
                        point["control_phases"] = controls
                        point["echo_phases"] = cycles
                        point["trace"] = trace_report(cycles)
                        point["status"] = (
                            "valid_controls" if point["rabi_gate"]["valid"] and
                            point["control_gate"]["valid"] else
                            "unresolved_local_control")
                    block_entry["sites"].append(point)
                    dual.checkpoint(path, manifest)

        manifest["t1_post_csv"] = str(localizer.run(
            data_root=data_root, correction_json=correction,
            parameter_overrides=scout_parameters("post"), announce=False))
        manifest["valid_site_blocks"] = sum(
            site["status"] == "valid_controls"
            for block in manifest["blocks"] for site in block["sites"])
        manifest["status"] = "complete"
        dual.checkpoint(path, manifest)
        return path
    except BaseException as exc:
        manifest["status"] = "failed"
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        dual.checkpoint(path, manifest)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--correction-json", type=Path)
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(plan(), indent=2))
    else:
        run(data_root=args.data_root, correction_json=args.correction_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
