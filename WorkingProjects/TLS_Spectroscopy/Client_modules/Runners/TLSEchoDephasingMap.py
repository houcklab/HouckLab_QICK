"""Map target-resident Hahn-echo contrast over the q3 3.8–4.3-GHz band.

At each site the qubit settles in its ground state before the coherent
pi/2–tau/2–pi–tau/2–pi/2 sequence. Four final-pulse phases recover its
visibility without confusing a deterministic phase shift with dephasing.
The native 40-us corrected return precedes the sole readout. A fresh T1
scout supplies an approximate loss comparison on the same frequency grid.
"""

import argparse
import json
import math
from pathlib import Path
from datetime import datetime, timezone
import subprocess
import uuid

import numpy as np


FREQUENCIES_GHZ = tuple(round(4.3 - .002 * index, 3)
                        for index in range(251))
DELAYS_US = (.3, 1.8)
PHASES_DEG = (0, 90, 180, 270)
SCIENCE_SHOTS = 200
PRE_ECHO_US = 30.0
POST_ECHO_US = 0.1
ECHO_SIGMA_US = 0.1


def make_program_class(parent):
    """Build the target-resident pulse sequence on the resident stream."""

    class TargetEchoProgram(parent):
        def _declare_experiment(self):
            from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import add_qubit_gaussian
            super()._declare_experiment()
            add_qubit_gaussian(self, name="echo_qubit", sigma_us=ECHO_SIGMA_US,
                               drag_beta=0.0)

        def _resident_excursion(self):
            from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
            cfg = self.cfg
            sigma = ECHO_SIGMA_US
            delay = float(cfg["echo_delay_us"])
            half = delay / 2
            pulse_us = 3 * (4 * sigma + .01) + delay
            park = int(cfg["ff_park_gain"])
            target = int(cfg["ff_gain"])
            if target != park:
                compensation = self._t1_ff_compensation
                if compensation is None:
                    raise ValueError("echo needs the pinned native correction")
                target_segments, recovery = ff_pulse.compensation_round_trip_segments(
                    compensation,
                    PRE_ECHO_US + self._t1_ff_settle_us + pulse_us + POST_ECHO_US,
                    recovery_us=self._t1_ff_predistortion_recovery_us)
                before, tail = ff_pulse.split_compensation_segments(
                    target_segments, PRE_ECHO_US + self._t1_ff_settle_us)
                during, after = ff_pulse.split_compensation_segments(tail, pulse_us)
                if not before or not during or not after:
                    raise ValueError("correction does not cover echo window")
                held = float(before[-1][0])
                if max(abs(float(level) - held) for level, _ in during) > .0015:
                    raise ValueError("flux correction varies too much during echo")
                ff_pulse.play_relative_compensation_segments(self, park, target, before)
                self.sync_all(0)
            else:
                self.sync_all(self.us2cycles(PRE_ECHO_US))
                after = recovery = []
            frequency = float(cfg["opx_resident_freq_mhz"])

            def pulse(gain, phase):
                self.set_pulse_registers(
                    ch=cfg["qubit_ch"], style="arb",
                    freq=self.freq2reg(frequency, gen_ch=cfg["qubit_ch"]),
                    phase=self.deg2reg(float(phase), gen_ch=cfg["qubit_ch"]),
                    gain=int(gain), waveform="echo_qubit")
                self.pulse(ch=cfg["qubit_ch"])
                self.sync_all(self.us2cycles(.01))

            pulse(cfg["echo_pi2_gain"], 0)
            self.sync_all(self.us2cycles(half))
            pulse(cfg["echo_pi_gain"], 0)
            self.sync_all(self.us2cycles(half))
            pulse(cfg["echo_pi2_gain"], cfg["echo_phase_deg"])
            if target != park:
                ff_pulse.play_relative_compensation_segments(self, park, target, after)
                ff_pulse.play_relative_compensation_segments(self, park, target, recovery)
                ff_pulse.play_hard_step(self, park)
                self.sync_all(0)
            else:
                self.sync_all(self.us2cycles(POST_ECHO_US))

    return TargetEchoProgram


def phase_cycle_visibility(fractions):
    values = {int(phase): float(value) for phase, value in fractions.items()}
    if set(values) != set(PHASES_DEG) or any(
            not math.isfinite(value) or value < 0 or value > 1
            for value in values.values()):
        raise ValueError("echo phase cycle needs four finite probabilities")
    x = values[0] - values[180]
    y = values[90] - values[270]
    return {"x": x, "y": y, "visibility": math.hypot(x, y),
            "phase_rad": math.atan2(y, x)}


def echo_rate(short_visibility, long_visibility, *, short_us, long_us):
    short = float(short_visibility)
    long = float(long_visibility)
    if not 0 <= short <= 2 or not 0 <= long <= 2 or not all(
            map(math.isfinite, (short, long, short_us, long_us))):
        raise ValueError("echo visibility and delays must be finite")
    if not 0 <= short_us < long_us:
        raise ValueError("echo delays must increase")
    if short < .15:
        return {"status": "unresolved_short_contrast"}
    if long < .06:
        return {"status": "long_contrast_below_detection"}
    rate = math.log(short / long) / (long_us - short_us)
    return {"status": "resolved", "rate_per_us": rate,
            "t2_echo_us": 1 / rate if rate > 0 else None}


def science_schedule(*, shots=SCIENCE_SHOTS):
    if int(shots) <= 0:
        raise ValueError("shots must be positive")
    result = []
    for index, frequency in enumerate(FREQUENCIES_GHZ):
        delays = DELAYS_US if index % 2 == 0 else tuple(reversed(DELAYS_US))
        phases = PHASES_DEG if index % 2 == 0 else tuple(reversed(PHASES_DEG))
        arms = [{"delay_us": delay, "phase_deg": phase,
                 "shots": int(shots), "status": "pending"}
                for delay in delays for phase in phases]
        result.append({"frequency_ghz": frequency, "arms": arms,
                       "status": "pending"})
    return result


def _survival(row, delay_us):
    try:
        ground = float(row["P0"])
        excited = float(row["P1"])
        delayed = float(row[f"Ps_{delay_us}us"])
    except (KeyError, TypeError, ValueError):
        return math.nan
    contrast = excited - ground
    return ((delayed - ground) / contrast
            if contrast >= .15 else math.nan)


def select_quiet_anchor(rows):
    """Prefer a measured quiet high-frequency site, then any quiet site."""
    choices = []
    for row in rows:
        frequency = float(row["target_frequency_ghz"])
        two = _survival(row, 2)
        twenty_five = _survival(row, 25)
        if (math.isfinite(two) and math.isfinite(twenty_five) and
                two >= .75 and twenty_five >= .65):
            choices.append({"frequency_ghz": frequency,
                            "survival_2us": two,
                            "survival_25us": twenty_five,
                            "valid_t1_fit": row.get("T1_5pt_valid_mask") == "1.0"})
    if not choices:
        raise ValueError("no quiet pilot site in fresh scout")
    high = [row for row in choices if 4.25 <= row["frequency_ghz"] <= 4.3]
    if high:
        choices = high
    return max(choices, key=lambda row: (row["valid_t1_fit"],
                                         min(row["survival_25us"], 1.0),
                                         row["frequency_ghz"]))


def arm_config(base, *, target_gain, frequency_ghz, delay_us, phase_deg, shots):
    if int(phase_deg) not in PHASES_DEG:
        raise ValueError("echo analysis phase must be a cardinal quadrature")
    if float(delay_us) not in DELAYS_US:
        raise ValueError("echo delay is outside the checked schedule")
    cfg = dict(base)
    pulse_us = 3 * (4 * ECHO_SIGMA_US + .01) + float(delay_us)
    cfg.update({"ff_gain": int(target_gain),
                "ff_hold": PRE_ECHO_US + POST_ECHO_US + pulse_us,
                "opx_resident_pre_us": PRE_ECHO_US,
                "opx_resident_post_us": POST_ECHO_US,
                "opx_resident_freq_mhz": float(frequency_ghz) * 1000,
                "opx_resident_gain": 0,
                "opx_resident_reference_state": None,
                "opx_resident_preparation_state": "g",
                "echo_delay_us": float(delay_us),
                "echo_phase_deg": int(phase_deg),
                "echo_pi_gain": 2 * int(base["qubit_pi_gain"]),
                "echo_pi2_gain": 2 * int(base["qubit_pi2_gain"]),
                "shots": int(shots), "reps": int(shots)})
    if cfg["echo_pi_gain"] > 30000:
        raise ValueError("broad target pi gain exceeds 30000 DAC")
    return cfg


def phase_gate(first, second, *, reference_contrast):
    first_report = phase_cycle_visibility(first)
    second_report = phase_cycle_visibility(second)
    reference_contrast = float(reference_contrast)
    valid = bool(math.isfinite(reference_contrast) and
                 reference_contrast >= .40 and
                 min(first_report["visibility"],
                     second_report["visibility"]) >= .25 and
                 abs(first_report["visibility"] -
                     second_report["visibility"]) <= .20)
    return {"valid": valid, "reference_contrast": reference_contrast,
            "first": first_report, "reversed": second_report}


def point_report(phase_fractions, scout_row):
    cycles = {delay: phase_cycle_visibility(phase_fractions[delay])
              for delay in DELAYS_US}
    rate = echo_rate(cycles[DELAYS_US[0]]["visibility"],
                     cycles[DELAYS_US[1]]["visibility"],
                     short_us=DELAYS_US[0], long_us=DELAYS_US[1])
    report = {"status": rate["status"], "cycles": cycles}
    if rate["status"] != "resolved":
        return report
    report["echo_rate_per_us"] = rate["rate_per_us"]
    report["t2_echo_us"] = rate["t2_echo_us"]
    try:
        fit_valid = float(scout_row.get("T1_5pt_valid_mask", 0)) > .5
        fit_rate = float(scout_row.get("inv_T1_5pt_per_us", "nan"))
    except (TypeError, ValueError):
        fit_valid, fit_rate = False, math.nan
    survival = _survival(scout_row, 2)
    if fit_valid and math.isfinite(fit_rate) and fit_rate > 0:
        t1_rate, source = fit_rate, "five_point_fit"
    elif math.isfinite(survival) and 0 < survival < 1:
        t1_rate, source = -math.log(survival) / 2, "two_us_survival"
    else:
        return report
    if math.isfinite(t1_rate):
        report["t1_rate_per_us"] = t1_rate
        report["t1_rate_source"] = source
        report["excess_dephasing_rate_per_us"] = rate["rate_per_us"] - t1_rate / 2
    return report


def plan():
    return {"hardware_access": False, "reset_mode": "passive",
            "phase_axis_preflight": True,
            "fresh_t1_scout": True,
            "frequency_ghz": [3.8, 4.3],
            "frequency_step_mhz": 2.0,
            "frequency_count": len(FREQUENCIES_GHZ),
            "free_evolution_delays_us": list(DELAYS_US),
            "final_pulse_phases_deg": list(PHASES_DEG),
            "shots_per_arm": SCIENCE_SHOTS,
            "target_resident_echo": True,
            "ground_state_settle_us": PRE_ECHO_US,
            "intrinsic_target_t2_claim": False,
            "native_40_us_return": True,
            "quiet_flux_echo_pilot_before_band_map": True,
            "raw_iq_saved": True,
            "terminal": "no custom run-progress messages"}


def run(*, data_root=None, correction_json=None):
    """Acquire a fresh loss scout, gated echo controls, then the echo map."""
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
        TLSPumpProbeLocalizer as localizer,
    )
    data_root = Path(data_root or localizer.DATA_ROOT)
    correction = localizer.checked_correction(data_root, correction_json)
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

    scout_parameters = {**wide.parameters(),
                        "output_suffix": "TLS_Echo_Dephasing_Map_Scout"}
    scout_path = localizer.run(data_root=data_root, correction_json=correction,
                               parameter_overrides=scout_parameters,
                               announce=False)
    rows = dual.read_scout(scout_path)
    row_by_frequency = {round(float(row["target_frequency_ghz"]), 3): row
                        for row in rows}
    anchor = select_quiet_anchor(rows)
    tls.QUBIT, tls.SET_YOKO, tls.outerFolder = "q3", False, str(data_root)
    five.install_scan_calibration(tls)
    if int(tls.BaseConfig["ff_park_gain"]) != -25146:
        raise RuntimeError("q3 park gain differs from the verified configuration")
    frequencies = np.asarray(FREQUENCIES_GHZ)
    dc, realized = _integer_dc_grid(wide.parameters(), frequencies, tls)
    dc_lookup = {float(frequency): int(gain)
                 for frequency, gain in zip(frequencies, dc)}
    compensation = tls._load_correction(str(correction), str(data_root))
    base = ProductionResetSession.passive().apply(tls.BaseConfig)
    five.apply_verified_feedback_timing(base)
    base.update({"apply_flux_tail_compensation": True,
                 "flux_tail_compensation": compensation,
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
    if 2 * int(base["qubit_pi_gain"]) > 30000:
        raise ValueError("verified park pi gain cannot support broad echo pulse")
    session_id = ("q3_echo_dephasing_map_" +
                  datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") +
                  "_" + uuid.uuid4().hex[:8])
    try:
        code_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[4], text=True,
            stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        code_commit = "unknown"
    folder = data_root / "q3" / session_id
    folder.mkdir(parents=True, exist_ok=False)
    manifest_path = folder / "manifest.json"
    manifest = {"schema": "q3.echo-dephasing-map.v1", "status": "running",
                "session_id": session_id, "code_commit": code_commit,
                "scout_csv": str(scout_path),
                "correction_json": str(correction),
                "correction_sha256": localizer.CORRECTION_SHA256,
                "quiet_anchor": anchor,
                "dc_lookup": {str(key): value for key, value in dc_lookup.items()},
                "realized_frequency_ghz": realized.tolist(),
                "plan": plan(), "park_phase_cycles": [],
                "quiet_pilot": {}, "points": science_schedule()}
    dual.checkpoint(manifest_path, manifest)
    program_class = make_program_class(resident.ResidentDriveProgram)
    try:
        soc, soccfg = tls.makeProxy()
        bundle = runtime_bundle(base)
        for frequency in (FREQUENCIES_GHZ[0], FREQUENCIES_GHZ[-1]):
            for delay in DELAYS_US:
                cfg = arm_config(base, target_gain=dc_lookup[frequency],
                                 frequency_ghz=frequency, delay_us=delay,
                                 phase_deg=270, shots=SCIENCE_SHOTS)
                program_class(soccfg, cfg, bundle.payload, bundle.loop)
        manifest["compiled_band_edges"] = True
        dual.checkpoint(manifest_path, manifest)

        def acquire_echo(frequency, delay, phase, shots=SCIENCE_SHOTS,
                         target_gain=None):
            cfg = arm_config(base, target_gain=(dc_lookup[frequency]
                                                if target_gain is None else target_gain),
                             frequency_ghz=frequency, delay_us=delay,
                             phase_deg=phase, shots=shots)
            program = program_class(soccfg, cfg, bundle.payload, bundle.loop)
            records = _run_program(
                soc, program, max(30., _block_timeout_s(cfg, shots)), cfg,
                total_shots=shots)
            if len(records) != shots:
                raise RuntimeError(f"echo received {len(records)} of {shots} shots")
            return records

        def acquire_reference(state):
            cfg = resident.arm_config(base, {
                "flux_ghz": anchor["frequency_ghz"],
                "drive_mhz": 1000 * anchor["frequency_ghz"],
                "gain": 0, "reference_state": state,
                "preparation_state": "g", "pre_drive_us": PRE_ECHO_US,
                "post_drive_us": POST_ECHO_US,
                "shots": 400,
            }, dc_lookup)
            program = resident.ResidentDriveProgram(
                soccfg, cfg, bundle.payload, bundle.loop)
            records = _run_program(
                soc, program, max(30., _block_timeout_s(cfg, 400)), cfg,
                total_shots=400)
            if len(records) != 400:
                raise RuntimeError("reference shot count incomplete")
            return records

        ref_g = acquire_reference("g")
        ref_e = acquire_reference("e")
        for name, records in (("ref_g_pre", ref_g), ("ref_e_pre", ref_e)):
            np.savez_compressed(folder / f"{name}.npz",
                                i=[r.i for r in records], q=[r.q for r in records])
        axis = resident.fit_axis(resident.record_iq(ref_g),
                                 resident.record_iq(ref_e))
        reference_contrast = resident.classify(ref_e, axis) - resident.classify(ref_g, axis)
        manifest["readout_axis"] = axis
        manifest["reference_contrast"] = reference_contrast
        dual.checkpoint(manifest_path, manifest)
        if not axis["valid"] or reference_contrast < .4:
            manifest["status"] = "stopped_readout_reference"
            dual.checkpoint(manifest_path, manifest)
            return manifest_path

        # The short broad pulses must form a real phase axis at park before
        # any whole-band acquisition is attempted.
        park = float(base["qubit_pi_freq"]) / 1000
        for phases in (PHASES_DEG, tuple(reversed(PHASES_DEG))):
            fractions = {}
            raw = {}
            for phase in phases:
                records = acquire_echo(park, DELAYS_US[0], phase,
                                       target_gain=base["ff_park_gain"])
                fractions[phase] = resident.classify(records, axis)
                raw[f"phase_{phase}"] = np.asarray(
                    [(r.i, r.q) for r in records], dtype=np.int64)
            index = len(manifest["park_phase_cycles"])
            np.savez_compressed(folder / f"park_phase_cycle_{index}.npz", **raw)
            manifest["park_phase_cycles"].append({"frequency_ghz": park,
                                                   "fractions": fractions})
            dual.checkpoint(manifest_path, manifest)
        gate = phase_gate(*(entry["fractions"] for entry in
                            manifest["park_phase_cycles"]),
                          reference_contrast=reference_contrast)
        manifest["park_phase_gate"] = gate
        dual.checkpoint(manifest_path, manifest)
        if not gate["valid"]:
            manifest["status"] = "stopped_park_phase_gate"
            dual.checkpoint(manifest_path, manifest)
            return manifest_path

        pilot_fractions = {}
        pilot_raw = {}
        pilot_frequency = anchor["frequency_ghz"]
        for delay in DELAYS_US:
            pilot_fractions[delay] = {}
            for phase in PHASES_DEG:
                records = acquire_echo(pilot_frequency, delay, phase)
                pilot_fractions[delay][phase] = resident.classify(records, axis)
                pilot_raw[f"delay_{delay}_phase_{phase}"] = np.asarray(
                    [(r.i, r.q) for r in records], dtype=np.int64)
        np.savez_compressed(folder / "quiet_pilot.npz", **pilot_raw)
        pilot = point_report(pilot_fractions, row_by_frequency[pilot_frequency])
        manifest["quiet_pilot"] = pilot
        dual.checkpoint(manifest_path, manifest)
        if (pilot["status"] != "resolved" or
                pilot["cycles"][DELAYS_US[0]]["visibility"] < .25 or
                pilot["cycles"][DELAYS_US[1]]["visibility"] < .12):
            manifest["status"] = "stopped_quiet_pilot"
            dual.checkpoint(manifest_path, manifest)
            return manifest_path

        for point in manifest["points"]:
            frequency = point["frequency_ghz"]
            fractions = {delay: {} for delay in DELAYS_US}
            raw = {}
            for arm in point["arms"]:
                delay, phase = arm["delay_us"], arm["phase_deg"]
                records = acquire_echo(frequency, delay, phase)
                fractions[delay][phase] = resident.classify(records, axis)
                raw[f"delay_{delay}_phase_{phase}"] = np.asarray(
                    [(r.i, r.q) for r in records], dtype=np.int64)
                arm["excited_fraction"] = fractions[delay][phase]
                arm["status"] = "complete"
            raw_path = folder / f"echo_{round(1000*frequency):04d}MHz.npz"
            np.savez_compressed(raw_path, **raw)
            point["raw_npz"] = str(raw_path)
            point["report"] = point_report(fractions, row_by_frequency[frequency])
            point["status"] = "complete"
            dual.checkpoint(manifest_path, manifest)
        ref_g_post = acquire_reference("g")
        ref_e_post = acquire_reference("e")
        for name, records in (("ref_g_post", ref_g_post),
                              ("ref_e_post", ref_e_post)):
            np.savez_compressed(folder / f"{name}.npz",
                                i=[r.i for r in records], q=[r.q for r in records])
        manifest["post_readout_score"] = resident.score_axis(
            axis, resident.record_iq(ref_g_post), resident.record_iq(ref_e_post))
        manifest["status"] = ("complete" if manifest["post_readout_score"]["valid"]
                              else "complete_readout_unstable")
        dual.checkpoint(manifest_path, manifest)
        return manifest_path
    except BaseException as exc:
        manifest["status"] = "failed"
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        dual.checkpoint(manifest_path, manifest)
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
