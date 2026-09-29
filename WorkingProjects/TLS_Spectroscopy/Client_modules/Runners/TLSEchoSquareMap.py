"""Blind q3 square-pulse Hahn-echo screen over 3.8--4.3 GHz.

At every 4-MHz site, bracket the readout with target-resident ground/pi
references, measure a two-pi/2 phase circle to test local pulse control,
and measure two Hahn-echo delays with four analysis phases. Failed local
controls mark a site unresolved; they never become a dephasing hotspot.
The ordinary five-point T1 scan runs *after* the echo screen for context.
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
    TLSEchoDephasingMap as previous_echo,
    TLSEchoFastSquarePilot as fast,
    TLSPumpProbeLocalizer as localizer,
)


FREQUENCIES_GHZ = tuple(round(4.3 - .004 * i, 3) for i in range(126))
DELAYS_US = (.3, .9, 1.8)
PHASES_DEG = (0, 90, 180, 270)
PI2_US = .045
PI_US = .0907
GAIN_DAC = 30000
DRIVE_OFFSET_MHZ = 2.5
PRE_US = 30.
POST_US = .1
SHOTS = 500
SOURCE_SESSION = "q3_echo_fast_square_phase_20260929T232207Z_1a22c113"


def validate_source(source):
    fit = source.get("source_rabi_refit", {})
    chosen = source.get("chosen_pi2", {})
    if (source.get("schema") != "q3.echo-fast-square-phase.v1" or
            source.get("session_id") != SOURCE_SESSION or
            source.get("status") != "complete_calibrated" or
            not source.get("two_pulse_gate", {}).get("valid") or
            source.get("correction_sha256") != localizer.CORRECTION_SHA256 or
            source.get("code_commit", "")[:8] != "e11d16b5" or
            not fit.get("valid") or
            abs(float(fit.get("pi_us", math.nan)) - PI_US) > .001 or
            abs(float(chosen.get("duration_us", math.nan)) - PI2_US) > .001 or
            float(source.get("gain_dac", -1)) != GAIN_DAC or
            float(source.get("target_frequency_ghz", math.nan)) != 4.288 or
            float(source.get("drive_frequency_mhz", math.nan)) != 4290.5):
        raise ValueError("pinned square-pulse calibration is unavailable or changed")


def echo_window_us(delay_us):
    delay = float(delay_us)
    if not math.isfinite(delay) or delay < 0:
        raise ValueError("echo free-evolution delay must be nonnegative")
    return 2 * PI2_US + PI_US + 3 * .01 + delay


def make_echo_program(parent):
    """Use the existing corrected target visit with three square pulses."""
    class SquareEchoProgram(parent):
        def _resident_excursion(self):
            from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse

            cfg = self.cfg
            delay = float(cfg["echo_delay_us"])
            window = echo_window_us(delay)
            park, target = int(cfg["ff_park_gain"]), int(cfg["ff_gain"])
            if target == park or self._t1_ff_compensation is None:
                raise ValueError("square echo requires corrected target visit")
            pre = float(cfg["opx_resident_pre_us"]) + self._t1_ff_settle_us
            post = float(cfg["opx_resident_post_us"])
            target_segments, recovery = ff_pulse.compensation_round_trip_segments(
                self._t1_ff_compensation, pre + window + post,
                recovery_us=self._t1_ff_predistortion_recovery_us)
            before, tail = ff_pulse.split_compensation_segments(target_segments,
                                                                  pre)
            during, after = ff_pulse.split_compensation_segments(tail, window)
            if not before or not during or not after:
                raise ValueError("correction does not cover square echo")
            held = float(before[-1][0])
            if max(abs(float(level) - held) for level, _ in during) > .0015:
                raise ValueError("flux correction varies during square echo")
            ff_pulse.play_relative_compensation_segments(self, park, target,
                                                          before)
            self.sync_all(0)

            def pulse(duration, phase):
                self.set_pulse_registers(
                    ch=cfg["qubit_ch"], style="const",
                    freq=self.freq2reg(float(cfg["opx_resident_freq_mhz"]),
                                       gen_ch=cfg["qubit_ch"]),
                    phase=self.deg2reg(phase, gen_ch=cfg["qubit_ch"]),
                    gain=GAIN_DAC,
                    length=self.us2cycles(duration, gen_ch=cfg["qubit_ch"]))
                self.pulse(ch=cfg["qubit_ch"])
                self.sync_all(self.us2cycles(.01))

            pulse(PI2_US, 0)
            self.sync_all(self.us2cycles(delay / 2))
            pulse(PI_US, 0)
            self.sync_all(self.us2cycles(delay / 2))
            pulse(PI2_US, int(cfg["echo_phase_deg"]))
            ff_pulse.play_relative_compensation_segments(self, park, target,
                                                          after)
            ff_pulse.play_relative_compensation_segments(self, park, target,
                                                          recovery)
            ff_pulse.play_hard_step(self, park)
            self.sync_all(0)

    return SquareEchoProgram


def control_gate(phase_values):
    report = phase_visibility(phase_values)
    values = list(map(float, phase_values.values()))
    center = sum(values) / len(values)
    amplitude = report["visibility"] / 2
    report.update({"center": center, "amplitude": amplitude,
                   "maximum": center + amplitude,
                   "minimum": center - amplitude})
    report["valid"] = bool(amplitude >= .22 and
                           abs(report["maximum"] - 1) <= .25 and
                           abs(report["minimum"]) <= .25)
    return report


def control_stability_gate(before, after):
    first, last = control_gate(before), control_gate(after)
    drift = math.degrees(abs(math.atan2(
        math.sin(first["phase_rad"] - last["phase_rad"]),
        math.cos(first["phase_rad"] - last["phase_rad"]))))
    return {"valid": bool(first["valid"] and last["valid"] and
                          abs(first["amplitude"] - last["amplitude"]) <= .15 and
                          abs(first["center"] - last["center"]) <= .15 and
                          drift <= 30),
            "before": first, "after": last, "phase_drift_deg": drift}


def echo_report(cycles):
    short = phase_visibility(cycles[DELAYS_US[0]])
    middle = phase_visibility(cycles[DELAYS_US[1]])
    long = phase_visibility(cycles[DELAYS_US[-1]])
    rate = previous_echo.echo_rate(short["visibility"], long["visibility"],
                                   short_us=DELAYS_US[0],
                                   long_us=DELAYS_US[-1])
    status = ("nondecaying" if rate["status"] == "resolved" and
              rate["rate_per_us"] <= 0 else rate["status"])
    if (status == "resolved" and
            (middle["visibility"] + .07 < long["visibility"] or
             middle["visibility"] > short["visibility"] + .07)):
        status = "nonmonotonic"
    report = {"status": status,
              "short": short, "middle": middle, "long": long}
    if status == "resolved":
        report["echo_rate_per_us"] = rate["rate_per_us"]
        report["t2_echo_us"] = rate["t2_echo_us"]
    return report


def phase_visibility(phase_values):
    """Calculate a phase circle from linear IQ projections, including noise tails."""
    values = {int(phase): float(value)
              for phase, value in phase_values.items()}
    if set(values) != set(PHASES_DEG) or not all(
            math.isfinite(value) for value in values.values()):
        raise ValueError("phase circle needs four finite projections")
    x = values[0] - values[180]
    y = values[90] - values[270]
    return {"x": x, "y": y, "visibility": math.hypot(x, y),
            "phase_rad": math.atan2(y, x)}


def site_schedule(index):
    phases = PHASES_DEG if index % 2 == 0 else tuple(reversed(PHASES_DEG))
    delays = DELAYS_US if index % 2 == 0 else tuple(reversed(DELAYS_US))
    return ([("control_pre", None, phase) for phase in phases] +
            [("echo", delay, phase) for delay in delays for phase in phases] +
            [("control_post", None, phase) for phase in reversed(phases)])


def plan():
    return {"hardware_access": False, "purpose": "blind Hahn echo screen",
            "frequency_ghz": [3.8, 4.3], "step_mhz": 4.,
            "frequency_count": len(FREQUENCIES_GHZ),
            "shots_per_arm": SHOTS,
            "echo_delays_us": list(DELAYS_US),
            "phase_cycle_deg": list(PHASES_DEG),
            "local_pulse_control_each_frequency": True,
            "bracketed_ground_pi_iq_each_frequency": True,
            "passive_reset": True, "corrected_return_us": 40.,
            "five_point_t1_after_echo": True,
            "invalid_controls_marked_unresolved": True,
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
    source_path = data_root / "q3" / SOURCE_SESSION / "manifest.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    validate_source(source)
    with localizer.scan_environment(correction):
        tls.QUBIT, tls.SET_YOKO, tls.outerFolder = "q3", False, str(data_root)
        five.install_scan_calibration(tls)
        base = ProductionResetSession.passive().apply(tls.BaseConfig)
        five.apply_verified_feedback_timing(base)
        if int(base["ff_park_gain"]) != -25146:
            raise RuntimeError("q3 park gain differs from verified setting")
        dc, realized = _integer_dc_grid(wide.parameters(),
                                        np.asarray(FREQUENCIES_GHZ), tls)
        dc_lookup = {frequency: int(gain)
                     for frequency, gain in zip(FREQUENCIES_GHZ, dc)}
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
        session_id = ("q3_echo_square_map_" +
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
        manifest = {"schema": "q3.echo-square-map.v1", "status": "running",
                    "session_id": session_id, "code_commit": commit,
                    "source_manifest": str(source_path),
                    "correction_json": str(correction),
                    "correction_sha256": localizer.CORRECTION_SHA256,
                    "plan": plan(),
                    "realized_frequency_ghz": realized.tolist(),
                    "points": []}
        dual.checkpoint(path, manifest)
        control_class = fast.make_program(resident.ResidentDriveProgram)
        echo_class = make_echo_program(resident.ResidentDriveProgram)
        try:
            soc, soccfg = tls.makeProxy()
            bundle = runtime_bundle(base)

            def configuration(frequency, kind, *, phase=0, delay=None):
                arm = {"flux_ghz": frequency,
                       "drive_mhz": 1000 * frequency + DRIVE_OFFSET_MHZ,
                       "gain": GAIN_DAC,
                       "reference_state": None,
                       "preparation_state": "g", "pre_drive_us": PRE_US,
                       "post_drive_us": POST_US, "shots": SHOTS}
                cfg = resident.arm_config(base, arm, dc_lookup)
                if kind == "echo":
                    cfg["echo_delay_us"] = float(delay)
                    cfg["echo_phase_deg"] = int(phase)
                    cfg["ff_hold"] = PRE_US + POST_US + echo_window_us(delay)
                else:
                    cfg["fast_pulse_us"] = PI2_US if kind in ("zero", "control_pre", "control_post") else PI_US
                    cfg["fast_second_phase_deg"] = int(phase) if kind.startswith("control") else None
                    cfg["opx_resident_gain"] = 0 if kind == "zero" else GAIN_DAC
                    count = 2 if kind.startswith("control") else 1
                    cfg["ff_hold"] = PRE_US + POST_US + count * (cfg["fast_pulse_us"] + .01)
                return cfg

            for frequency in (FREQUENCIES_GHZ[0], FREQUENCIES_GHZ[-1]):
                for kind, delay in (("control_pre", None), ("echo", DELAYS_US[0]),
                                    ("echo", DELAYS_US[-1])):
                    cfg = configuration(frequency, kind, phase=270, delay=delay)
                    (echo_class if kind == "echo" else control_class)(
                        soccfg, cfg, bundle.payload, bundle.loop)
            manifest["compiled_band_edges"] = True
            dual.checkpoint(path, manifest)

            def acquire(frequency, kind, *, phase=0, delay=None):
                cfg = configuration(frequency, kind, phase=phase, delay=delay)
                program = (echo_class if kind == "echo" else control_class)(
                    soccfg, cfg, bundle.payload, bundle.loop)
                records = _run_program(
                    soc, program, max(30., _block_timeout_s(cfg, SHOTS)),
                    cfg, total_shots=SHOTS)
                if len(records) != SHOTS:
                    raise RuntimeError("incomplete echo IQ records")
                return resident.record_iq(records)

            for index, frequency in enumerate(FREQUENCIES_GHZ):
                raw = {}
                zero_pre = acquire(frequency, "zero")
                pi_pre = acquire(frequency, "pi")
                raw["zero_pre"] = zero_pre
                raw["pi_pre"] = pi_pre
                schedule = site_schedule(index)
                acquired = []
                for kind, delay, phase in schedule:
                    iq = acquire(frequency, kind, phase=phase, delay=delay)
                    label = (f"{kind}_{phase}" if kind.startswith("control") else
                             f"echo_{round(delay * 1000)}ns_{phase}")
                    raw[label] = iq
                    acquired.append((kind, delay, phase, iq))
                zero_post = acquire(frequency, "zero")
                pi_post = acquire(frequency, "pi")
                raw["zero_post"] = zero_post
                raw["pi_post"] = pi_post
                raw_path = folder / f"echo_{round(1000 * frequency):04d}MHz.npz"
                np.savez_compressed(raw_path, **{
                    f"{name}_i": array.real.astype(np.int64)
                    for name, array in raw.items()}, **{
                    f"{name}_q": array.imag.astype(np.int64)
                    for name, array in raw.items()})
                refs = (zero_pre.mean(), pi_pre.mean(),
                        zero_post.mean(), pi_post.mean())
                bracket = fast.score_reference_bracket(*refs)
                point = {"frequency_ghz": frequency,
                         "drive_frequency_mhz": 1000 * frequency + DRIVE_OFFSET_MHZ,
                         "target_gain": dc_lookup[frequency],
                         "raw_npz": str(raw_path),
                         "reference_bracket": bracket,
                         "status": "unresolved_reference"}
                if bracket["valid"]:
                    controls = {"control_pre": {}, "control_post": {}}
                    cycles = {delay: {} for delay in DELAYS_US}
                    for position, (kind, delay, phase, iq) in enumerate(acquired):
                        response = fast.bracketed_response(
                            iq.mean(), *refs, (position + 1) /
                            (len(acquired) + 1))
                        if kind.startswith("control"):
                            controls[kind][phase] = response
                        else:
                            cycles[delay][phase] = response
                    point["control_phases"] = controls
                    point["control_gate"] = control_stability_gate(
                        controls["control_pre"], controls["control_post"])
                    point["echo_phases"] = cycles
                    if point["control_gate"]["valid"]:
                        point["echo"] = echo_report(cycles)
                        point["status"] = point["echo"]["status"]
                    else:
                        point["status"] = "unresolved_local_control"
                manifest["points"].append(point)
                dual.checkpoint(path, manifest)

            # T1 is context for a completed blind echo map, never a site gate.
            scout_parameters = {**wide.parameters(),
                                "output_suffix": "TLS_Echo_Square_Map_T1_Context"}
            scout = localizer.run(data_root=data_root, correction_json=correction,
                                  parameter_overrides=scout_parameters,
                                  announce=False)
            manifest["t1_context_csv"] = str(scout)
            resolved = sum(point["status"] == "resolved"
                           for point in manifest["points"])
            manifest["resolved_sites"] = resolved
            manifest["status"] = ("complete" if resolved else
                                  "complete_no_resolved_sites")
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
