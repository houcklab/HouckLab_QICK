"""Measure 20–40 MHz fast-flux transfer from q3 park Ramsey phase.

This is an instrument calibration for the modulation-induced loss experiment.
The qubit stays at its park bias while a short AC waveform, a matched zero-AC
waveform, or a static-offset control plays between two park-frequency pi/2
pulses. No TLS loss-site visit or active reset occurs in this run.
"""

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import uuid

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.PulseFunctions import (
    ff_envelope_samples, ff_maxv,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSFluxModulationCalibration as calibration,
    TLSPumpProbeLocalizer as localizer,
    TLSPumpProbeProtocolCheck as protocol,
)


FREQUENCIES_MHZ = (20.0, 30.0, 40.0)
AMPLITUDES_DAC = (600, 1000, 1400, 1700, 2000)
DURATIONS_US = (0.1, 0.2)
STATIC_OFFSETS_DAC = (-700, 700)
RAMSEY_ARMS = ("g", "e", "i", "q")
SHOTS_PER_ARM = 300
PARK_CAL_SHOTS = 800
MIN_ASSIGNMENT_CONTRAST = 0.50
MIN_RAMSEY_CONTRAST = 0.25
MIN_RAMSEY_COHERENCE = 0.15


def plan():
    return {"hardware_access": False, "bias": "q3 park",
            "reset_mode": "passive", "frequencies_mhz": list(FREQUENCIES_MHZ),
            "amplitudes_dac": list(AMPLITUDES_DAC),
            "durations_us": list(DURATIONS_US),
            "static_offsets_dac": list(STATIC_OFFSETS_DAC),
            "ramsey_arms": list(RAMSEY_ARMS), "shots_per_arm": SHOTS_PER_ARM,
            "park_calibration_shots": PARK_CAL_SHOTS,
            "blocks": 2, "zero_ac_brackets_per_frequency_duration": 2,
            "raw_iq_saved": True,
            "purpose": "infer delivered fast-flux amplitude from park Ramsey phase",
            "interpretation": "transfer diagnostic, not independent TLS evidence"}


def schedule(*, frequencies_mhz=FREQUENCIES_MHZ,
             amplitudes_dac=AMPLITUDES_DAC,
             durations_us=DURATIONS_US,
             static_offsets_dac=STATIC_OFFSETS_DAC):
    first = []
    for duration in durations_us:
        duration = float(duration)
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("Ramsey durations must be finite and positive")
        t_label = f"t{round(duration * 1000):d}"
        for frequency in frequencies_mhz:
            frequency = float(frequency)
            if not math.isfinite(frequency) or frequency <= 0:
                raise ValueError("AC frequencies must be finite and positive")
            f_label = f"f{frequency:g}".replace(".", "p")
            stem = f"{f_label}_{t_label}"
            first.append({"suffix": f"{stem}_off_pre", "kind": "off",
                          "frequency_mhz": frequency,
                          "amplitude_dac": 0,
                          "static_offset_dac": 0,
                          "duration_us": duration})
            for amplitude in amplitudes_dac:
                amplitude = int(amplitude)
                if amplitude <= 0:
                    raise ValueError("AC amplitudes must be positive")
                first.append({"suffix": f"{stem}_a{amplitude}", "kind": "ac",
                              "frequency_mhz": frequency,
                              "amplitude_dac": amplitude,
                              "static_offset_dac": 0,
                              "duration_us": duration})
            first.append({"suffix": f"{stem}_off_post", "kind": "off",
                          "frequency_mhz": frequency,
                          "amplitude_dac": 0,
                          "static_offset_dac": 0,
                          "duration_us": duration})
        for offset in static_offsets_dac:
            offset = int(offset)
            if offset == 0:
                raise ValueError("static controls need nonzero offset")
            label = f"p{offset}" if offset > 0 else f"m{-offset}"
            first.append({"suffix": f"{t_label}_static_{label}",
                          "kind": "static", "frequency_mhz": 0.0,
                          "amplitude_dac": 0, "static_offset_dac": offset,
                          "duration_us": duration})
    result = []
    for block, rows in ((0, first), (1, list(reversed(first)))):
        for row in rows:
            result.append({"name": f"b{block}_{row['suffix']}",
                           "block": block, **{k: v for k, v in row.items()
                                              if k != "suffix"},
                           "status": "pending"})
    if len({row["name"] for row in result}) != len(result):
        raise ValueError("duplicate Ramsey program names")
    return result


def park_waveform(*, park_gain, amplitude_dac, frequency_mhz,
                  static_offset_dac, duration_us,
                  sample_rate_mhz, fabric_rate_mhz, max_gain):
    """Build a period-matched AC or constant park-bias waveform."""
    amplitude = int(amplitude_dac)
    offset = int(static_offset_dac)
    if amplitude and offset:
        raise ValueError("AC and static-offset controls are exclusive")
    fabric = float(fabric_rate_mhz)
    sample_rate = float(sample_rate_mhz)
    cycles = int(round(float(duration_us) * fabric))
    ratio = sample_rate / fabric
    samples_per_clock = int(round(ratio))
    if (not all(math.isfinite(v) for v in (fabric, sample_rate, park_gain,
                                           duration_us, max_gain)) or
            fabric <= 0 or sample_rate <= 0 or cycles < 3 or
            abs(ratio - samples_per_clock) > 1e-6):
        raise ValueError("invalid park Ramsey waveform clock or duration")
    if amplitude < 0 or abs(float(park_gain) + offset) + amplitude > min(
            float(max_gain), 32767.0):
        raise ValueError("park Ramsey waveform exceeds fast-flux DAC range")
    if offset:
        waveform = np.full(cycles * samples_per_clock,
                           round(float(park_gain) + offset), dtype=np.int16)
        report = {"samples": int(waveform.size),
                  "duration_us": cycles / fabric,
                  "static_offset_dac": offset,
                  "requested_modulation_mhz": 0.0,
                  "actual_modulation_mhz": 0.0,
                  "cycles_per_waveform": 0}
    else:
        waveform, report = calibration.modulation_waveform(
            sample_rate_mhz=sample_rate,
            fabric_rate_mhz=fabric, cycles=cycles,
            baseline_gain=float(park_gain),
            amplitude_gain=amplitude,
            modulation_mhz=float(frequency_mhz),
            max_gain=max_gain)
        report["static_offset_dac"] = 0
    return waveform, report


def ramsey_signal(fractions):
    """Normalize two Ramsey quadratures with contemporaneous g/e arms."""
    values = {arm: float(fractions[arm]) for arm in RAMSEY_ARMS}
    contrast = values["e"] - values["g"]
    if not np.isfinite(list(values.values())).all() or contrast < MIN_RAMSEY_CONTRAST:
        raise ValueError("park Ramsey reference contrast is too small")
    real = 2.0 * (values["i"] - values["g"]) / contrast - 1.0
    imag = 2.0 * (values["q"] - values["g"]) / contrast - 1.0
    magnitude = float(np.hypot(real, imag))
    return {"reference_contrast": contrast,
            "coherence_real": float(real), "coherence_imag": float(imag),
            "coherence_magnitude": magnitude,
            "phase_rad": float(np.arctan2(imag, real)),
            "valid": bool(magnitude >= MIN_RAMSEY_COHERENCE)}


def make_program_class(parent):
    """Bind the park-only AC burst to the established Ramsey pulse sequence."""

    class ParkTransferRamseyProgram(parent):
        def initialize(self):
            super().initialize()
            cfg = self.cfg
            park = float(cfg["ff_park_gain"])
            if (not cfg.get("ramsey_park_idle_only") or
                    float(cfg["ff_gain"]) != park or cfg.get("ramsey_echo")):
                raise ValueError("transfer Ramsey requires a non-echo park-only sequence")
            generator = self.soccfg["gens"][int(cfg["ff_ch"])]
            waveform, report = park_waveform(
                park_gain=park,
                amplitude_dac=cfg["transfer_amplitude_dac"],
                frequency_mhz=cfg["transfer_frequency_mhz"],
                static_offset_dac=cfg["transfer_static_offset_dac"],
                duration_us=cfg["ramsey_flux_hold_us"],
                sample_rate_mhz=generator["fs"],
                fabric_rate_mhz=generator["f_fabric"],
                max_gain=ff_maxv(self, scaled=True))
            park_ramp_cycles = self.us2cycles(
                float(cfg["ff_ramp_length"]), gen_ch=cfg["ff_ch"])
            samples_per_clock = int(report.get(
                "samples_per_clock",
                round(float(generator["fs"]) / float(generator["f_fabric"]))))
            total_samples = 2 * park_ramp_cycles * samples_per_clock + len(waveform)
            capacity = ff_envelope_samples(self)
            if total_samples > capacity:
                raise ValueError("park ramps and AC burst exceed fast-flux memory")
            self.memory_report = {
                "park_ramp_samples": 2 * park_ramp_cycles * samples_per_clock,
                "burst_samples": len(waveform),
                "total_samples": total_samples, "capacity_samples": capacity}
            self.waveform_report = report
            self.park_transfer_waveform = waveform
            self.add_pulse(ch=cfg["ff_ch"], name="q3_park_transfer",
                           idata=waveform, qdata=np.zeros_like(waveform))

        def _play_excursion(self):
            cfg = self.cfg
            self.set_pulse_registers(
                ch=cfg["ff_ch"], freq=0, style="arb", phase=0,
                stdysel="last", gain=ff_maxv(self),
                waveform="q3_park_transfer", outsel="input")
            self.pulse(ch=cfg["ff_ch"])
            self.sync_all(0)
            ff_pulse.play_hard_step(self, cfg["ff_park_gain"])
            self.sync_all(0)

    return ParkTransferRamseyProgram


def phase_report(entries):
    """Compare each AC phase with its two surrounding zero-AC arms."""
    rows = {entry["name"]: entry for entry in entries}
    report = {}

    def coherence(entry):
        signal = entry.get("signal") or {}
        if not signal.get("valid", False):
            return None
        return complex(float(signal["coherence_real"]),
                       float(signal["coherence_imag"]))

    for index, entry in enumerate(entries):
        if entry["kind"] == "off":
            continue
        name = entry["name"]
        value = coherence(entry)
        if entry["kind"] == "ac":
            stem = name.rsplit("_a", 1)[0]
            pre_name = stem + "_off_pre"
            post_name = stem + "_off_post"
            pre = coherence(rows[pre_name])
            post = coherence(rows[post_name])
            refs = [pre_name, post_name]
            baseline = ((pre + post) / 2.0
                        if pre is not None and post is not None else None)
            drift = (float(np.angle(post * np.conj(pre)))
                     if pre is not None and post is not None else None)
        else:
            candidates = [(abs(i - index), row) for i, row in enumerate(entries)
                          if row["kind"] == "off" and
                          row["block"] == entry["block"] and
                          row["duration_us"] == entry["duration_us"] and
                          coherence(row) is not None]
            nearest = min(candidates, key=lambda item: item[0])[1] if candidates else None
            baseline = coherence(nearest) if nearest else None
            refs = [nearest["name"]] if nearest else []
            drift = None
        if value is None or baseline is None or abs(baseline) < 1e-9:
            report[name] = {"valid": False, "off_references": refs}
            continue
        report[name] = {
            "valid": True, "off_references": refs,
            "phase_relative_to_off_rad": float(np.angle(value * np.conj(baseline))),
            "coherence_ratio_to_off": float(abs(value) / abs(baseline)),
            "off_bracket_drift_rad": drift}
    return report


def acquire_entry(entry, *, soc, soccfg, base_cfg, program_class, acquire,
                  discriminate, calib_params, folder, shots, checkpoint=None):
    """Acquire all four arms for one burst and persist IQ before scoring it."""
    arms = RAMSEY_ARMS if entry["block"] == 0 else tuple(reversed(RAMSEY_ARMS))
    entry["arms"] = {}
    entry["status"] = "acquiring"
    if checkpoint is not None:
        checkpoint()
    for arm in arms:
        cfg = dict(base_cfg)
        cfg.update({"ramsey_arm": arm, "ramsey_park_idle_only": True,
                    "ramsey_echo": False,
                    "ramsey_flux_hold_us": entry["duration_us"],
                    "transfer_amplitude_dac": entry["amplitude_dac"],
                    "transfer_frequency_mhz": entry["frequency_mhz"],
                    "transfer_static_offset_dac": entry["static_offset_dac"],
                    "shots": int(shots), "reps": int(shots)})
        if "ff_park_gain" in cfg:
            cfg["ff_gain"] = cfg["ff_park_gain"]
        program = program_class(soccfg, cfg)
        if "waveform_npz" not in entry:
            waveform_path = folder / f"{entry['name']}_waveform.npz"
            np.savez_compressed(waveform_path,
                                idata=program.park_transfer_waveform)
            entry["waveform_npz"] = str(waveform_path)
            entry["waveform_report"] = program.waveform_report
            entry["memory_report"] = program.memory_report
            if checkpoint is not None:
                checkpoint()
        herald_i, herald_q, i, q = acquire(program, soc)
        arrays = [np.asarray(x, dtype=float).reshape(-1)
                  for x in (herald_i, herald_q, i, q)]
        if any(x.size != shots for x in arrays):
            raise RuntimeError(f"{entry['name']} {arm}: incomplete shot IQ")
        raw_path = folder / f"{entry['name']}_{arm}.npz"
        np.savez_compressed(raw_path, herald_i=arrays[0], herald_q=arrays[1],
                            i=arrays[2], q=arrays[3])
        excited = np.asarray(discriminate(arrays[2], arrays[3], calib_params))
        if excited.size != shots:
            raise RuntimeError(f"{entry['name']} {arm}: incomplete classifications")
        entry["arms"][arm] = {"excited_fraction": float(np.mean(excited)),
                              "raw_npz": str(raw_path)}
        if checkpoint is not None:
            checkpoint()
    try:
        entry["signal"] = ramsey_signal({
            arm: entry["arms"][arm]["excited_fraction"] for arm in RAMSEY_ARMS})
    except ValueError as exc:
        entry["signal"] = {"valid": False, "error": str(exc)}
    entry["status"] = "complete"
    if checkpoint is not None:
        checkpoint()
    return entry


def _json_value(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"cannot serialize {type(value).__name__}")


def run(*, data_root=localizer.DATA_ROOT):
    """Run park-only Ramsey bursts after one checked single-shot calibration."""
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
        FivePointApplesToApples as five,
        TLSSpectroscopy as tls,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mRoundTripRamsey import (
        RoundTripRamseyProgram,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import (
        SingleShot1Q, discriminate_shots,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.acquisition import (
        acquire_with_retry,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import (
        ProductionResetSession,
    )

    data_root = Path(data_root)
    if int(tls.BaseConfig["ff_park_gain"]) != -25146:
        raise RuntimeError("q3 park gain differs from verified configuration")
    base = ProductionResetSession.passive().apply(tls.BaseConfig)
    base.update({"ff_gain": base["ff_park_gain"],
                 "ff_ramp_length": 4.0,
                 "ramsey_park_idle_only": True,
                 "ramsey_echo": False,
                 "qubit_pulse_style": "arb",
                 "relax_delay": 1000.0})
    session_id = ("q3_floquet_transfer_ramsey_" +
                  datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") +
                  "_" + uuid.uuid4().hex[:8])
    folder = data_root / "q3" / session_id
    folder.mkdir(parents=True, exist_ok=False)
    path = folder / "manifest.json"
    entries = schedule()
    manifest = {"schema": "q3.floquet-transfer-ramsey.v1",
                "status": "running", "session_id": session_id,
                "code_commit": os.environ.get("Q3_CODE_COMMIT", "unknown"),
                "plan": plan(), "park_config": {
                    "ff_park_gain": base["ff_park_gain"],
                    "static_flux_fit_params": list(five.APPLE_FLUX_FIT_PARAMS),
                    "qubit_pi_freq_mhz": base["qubit_pi_freq"],
                    "qubit_pi_gain": base["qubit_pi_gain"],
                    "qubit_pi2_gain": base["qubit_pi2_gain"],
                    "ff_ramp_length_us": base["ff_ramp_length"],
                    "relax_delay_us": base["relax_delay"]},
                "entries": entries}
    protocol.checkpoint(path, manifest)
    print(f"[transfer-Ramsey] manifest={path}", flush=True)
    try:
        soc, soccfg = tls.makeProxy()
        program_class = make_program_class(RoundTripRamseyProgram)
        # Compile every waveform shape and the largest static excursions before
        # taking shots. QICK checks actual generator clocks and envelope memory.
        preflight = []
        for entry in entries[:len(entries) // 2]:
            cfg = dict(base, ramsey_arm="g", shots=1, reps=1,
                       ramsey_flux_hold_us=entry["duration_us"],
                       transfer_amplitude_dac=entry["amplitude_dac"],
                       transfer_frequency_mhz=entry["frequency_mhz"],
                       transfer_static_offset_dac=entry["static_offset_dac"])
            program = program_class(soccfg, cfg)
            report = program.waveform_report
            if (entry["kind"] == "ac" and
                    abs(report["actual_modulation_mhz"] -
                        entry["frequency_mhz"]) > 0.03):
                raise RuntimeError(f"{entry['name']}: modulation frequency mismatch")
            preflight.append({"name": entry["name"],
                              "waveform_report": report,
                              "memory_report": program.memory_report})
        manifest["preflight"] = preflight
        manifest["preflight_complete"] = True
        protocol.checkpoint(path, manifest)
        print(f"[transfer-Ramsey] preflight {len(preflight)} waveform shapes passed",
              flush=True)

        cal_cfg = dict(base, shots=PARK_CAL_SHOTS, reps=PARK_CAL_SHOTS)
        ss = SingleShot1Q(
            soc=soc, soccfg=soccfg, path="q3", outerFolder=str(data_root),
            suffix="TLS_Floquet_Transfer_Ramsey_SS_Park", cfg=cal_cfg,
            repeats=1, confidence_threshold=0.0, plot=False, save=False)
        ss.acquire(progress=False, plotDisp=False)
        ss_path = folder / "park_single_shot.npz"
        np.savez_compressed(ss_path, I_0=ss.I_0, Q_0=ss.Q_0,
                            I_1=ss.I_1, Q_1=ss.Q_1)
        assignment = {
            "P_g": float(np.mean(discriminate_shots(
                ss.I_0, ss.Q_0, ss.calib_params))),
            "P_e": float(np.mean(discriminate_shots(
                ss.I_1, ss.Q_1, ss.calib_params)))}
        assignment["contrast"] = assignment["P_e"] - assignment["P_g"]
        manifest["park_calibration"] = {
            "raw_npz": str(ss_path), "fidelity": float(ss.max_F),
            "assignment": assignment,
            "calib_params": json.loads(json.dumps(
                ss.calib_params, default=_json_value))}
        protocol.checkpoint(path, manifest)
        if assignment["contrast"] < MIN_ASSIGNMENT_CONTRAST:
            raise RuntimeError(
                f"park assignment contrast {assignment['contrast']:.3f} is below "
                f"{MIN_ASSIGNMENT_CONTRAST:.3f}")
        print(f"[transfer-Ramsey] park SS F={ss.max_F:.3f}, "
              f"contrast={assignment['contrast']:.3f}", flush=True)

        for index, entry in enumerate(entries, start=1):
            print(f"[transfer-Ramsey] {index}/{len(entries)} {entry['name']}",
                  flush=True)
            acquire_entry(
                entry, soc=soc, soccfg=soccfg, base_cfg=base,
                program_class=program_class,
                acquire=lambda prog, proxy: acquire_with_retry(
                    prog, proxy, load_pulses=True, progress=False),
                discriminate=discriminate_shots,
                calib_params=ss.calib_params, folder=folder,
                shots=SHOTS_PER_ARM,
                checkpoint=lambda: protocol.checkpoint(path, manifest))
        manifest["phase_report"] = phase_report(entries)
        valid = sum(item["valid"] for item in manifest["phase_report"].values())
        manifest["valid_phase_count"] = valid
        manifest["total_phase_count"] = len(manifest["phase_report"])
        manifest["status"] = ("complete" if valid == len(manifest["phase_report"])
                              else "complete_controls_unstable")
        protocol.checkpoint(path, manifest)
        print(f"[transfer-Ramsey] {manifest['status']}: "
              f"{valid}/{manifest['total_phase_count']} phase contrasts; {path}",
              flush=True)
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
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(plan(), indent=2))
    else:
        run(data_root=args.data_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
