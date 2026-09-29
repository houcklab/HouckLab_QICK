"""Probe a loss line with square-wave frequency hops between quiet endpoints.

The ideal periodic-latching prediction is a spectral carrier at the line even
though both commanded dwell frequencies are off it. This experimental runner
records the programmed waveform and static endpoint controls; it does not
assume that the device receives an ideal square wave.
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
    TLSDualTransitionLoss as dual,
    TLSPumpProbeLocalizer as localizer,
    TLSPumpProbeResidentDrive as resident,
    TLSPumpProbeResidentProbe as probe,
    TLSPumpProbeShotAlternating as alternating,
    TLSPumpProbeWidePassiveScan as wide,
    TLSFluxModulatedT1 as modulated,
)


HOLDS_US = (.4, 3.6)
PRE_US = .05
PARK_RAMP_US = 1.0
HOP_MHZ = 20.0  # complete square-wave cycles per microsecond
ENDPOINT_OFFSETS_MHZ = (-40, -20, -10, 0, 10, 20, 40)
PATTERNS = ("center", "minus10", "plus10", "hop10",
            "minus20", "plus20", "hop20",
            "minus40", "plus40", "hop40")
PAIRS = (("center", "hop10"), ("minus10", "plus10"),
         ("center", "hop20"), ("minus20", "plus20"),
         ("center", "hop40"), ("minus40", "plus40"))
SHOTS = 4000
REFERENCE_SHOTS = 400
RECORDS_PER_SHOT = 4


def _pooled_survival(indexed, center_ghz, offset_mhz, direction="", *,
                     delay_us=25):
    keys = [round(center_ghz + (offset_mhz + step * 2) / 1000, 3)
            for step in (-1, 0, 1)]
    if any(key not in indexed for key in keys):
        return math.nan
    if delay_us == 25:
        return dual.pooled_group_survival([indexed[key] for key in keys],
                                          direction)
    suffix = "" if not direction else "_scan_" + direction
    try:
        rows = [indexed[key] for key in keys]
        contrast = sum(float(row["P1" + suffix]) -
                       float(row["P0" + suffix]) for row in rows)
        surviving = sum(float(row[f"Ps_{delay_us}us" + suffix]) -
                        float(row["P0" + suffix]) for row in rows)
    except (KeyError, TypeError, ValueError):
        return math.nan
    return surviving / contrast if contrast / len(rows) >= .15 else math.nan


def select_candidate(rows, *, preferred_center=None):
    """Require quiet ±20/±40 sites; enable ±10 only when it is also quiet."""
    indexed = {round(float(row["target_frequency_ghz"]), 3): row
               for row in rows}
    expected = {round(3.8 + .002 * index, 3) for index in range(251)}
    if len(rows) != 251 or set(indexed) != expected:
        raise ValueError("phantom pilot requires one complete wide scout")
    candidates = []
    for center in sorted(indexed):
        survival = {direction: {
            offset: _pooled_survival(indexed, center, offset, direction)
            for offset in (-40, -20, -12, -10, 0, 10, 12, 20, 40)}
            for direction in ("", "up", "down")}
        early = {direction: {
            offset: _pooled_survival(indexed, center, offset, direction,
                                     delay_us=10)
            for offset in (-12, 0, 12)}
            for direction in ("", "up", "down")}
        required_offsets = (-40, -20, -12, 0, 12, 20, 40)
        if any(not math.isfinite(survival[direction][offset])
               for direction in ("", "up", "down")
               for offset in required_offsets) or any(
                   not math.isfinite(value) for values in early.values()
                   for value in values.values()):
            continue
        depth = {direction or "combined": (
            min(survival[direction][-12], survival[direction][12]) -
            survival[direction][0]) for direction in ("", "up", "down")}
        early_depth = {direction or "combined": (
            min(early[direction][-12], early[direction][12]) -
            early[direction][0]) for direction in ("", "up", "down")}
        endpoints = {offset: survival[""][offset]
                     for offset in (-40, -20, -10, 10, 20, 40)}
        if (depth["combined"] < .15 or
                min(depth["up"], depth["down"]) < .08 or
                early_depth["combined"] < .10 or
                min(early_depth["up"], early_depth["down"]) < .05 or
                min(endpoints[-20], endpoints[20]) < .65 or
                min(endpoints[-40], endpoints[40]) < .68 or
                min(survival[direction][offset]
                    for direction in ("up", "down")
                    for offset in (-20, 20)) < .55 or
                min(survival[direction][offset]
                    for direction in ("up", "down")
                    for offset in (-40, 40)) < .50):
            continue
        quiet10 = (all(math.isfinite(survival[direction][offset])
                       for direction in ("", "up", "down")
                       for offset in (-10, 10)) and
                   min(endpoints[-10], endpoints[10]) >= .60 and
                   min(survival[direction][offset]
                       for direction in ("up", "down")
                       for offset in (-10, 10)) >= .50)
        candidates.append({
            "center_ghz": center, "depth": depth["combined"],
            "depth_scan_up": depth["up"],
            "depth_scan_down": depth["down"],
            "early_depth": early_depth["combined"],
            "early_depth_scan_up": early_depth["up"],
            "early_depth_scan_down": early_depth["down"],
            "endpoint_survival": {str(k): (float(v) if math.isfinite(v)
                                          else None)
                                  for k, v in endpoints.items()},
            "endpoint_directional_survival": {
                direction: {str(offset): (
                    float(survival[direction][offset])
                    if math.isfinite(survival[direction][offset]) else None)
                            for offset in endpoints}
                for direction in ("up", "down")},
            "eligible_amplitudes_mhz": [10, 20, 40] if quiet10 else [20, 40],
            "selector": "wide_pooled_phantom_candidate"})
    if preferred_center is not None:
        candidates = [row for row in candidates if
                      abs(row["center_ghz"] - preferred_center) <= .004001]
    if not candidates:
        raise ValueError("no qualified loss line with quiet ±20/±40-MHz endpoints")
    return max(candidates, key=lambda row: (
        min(row["early_depth_scan_up"], row["early_depth_scan_down"]),
        row["early_depth"], row["depth"]))


def square_waveform(*, pattern, segments, park_gain, center_gain,
                    endpoint_gains, sample_rate_mhz, fabric_rate_mhz,
                    cycles, max_gain, start_high=True):
    """Compile static and 20-MHz-latched corrected holds on the same grid."""
    if pattern not in PATTERNS:
        raise ValueError("unknown phantom-resonance pattern")
    fs, fabric = float(sample_rate_mhz), float(fabric_rate_mhz)
    samples_per_clock = int(round(fs / fabric))
    if (not all(map(math.isfinite, (fs, fabric, max_gain))) or
            fs <= 0 or fabric <= 0 or samples_per_clock <= 0 or
            abs(fs / fabric - samples_per_clock) > 1e-6):
        raise ValueError("fast-flux sample and fabric clocks are incompatible")
    cycles = int(cycles)
    duration = cycles / fabric
    requested_hops = HOP_MHZ * duration
    full_cycles = int(round(requested_hops))
    if (cycles < 3 or full_cycles < 1 or
            abs(requested_hops - full_cycles) > .1):
        raise ValueError("hold must contain whole square-wave cycles")
    lengths = np.asarray([duration for _, duration in segments], dtype=float)
    levels = np.asarray([level for level, _ in segments], dtype=float)
    if (not lengths.size or not np.all(np.isfinite(lengths)) or
            not np.all(np.isfinite(levels)) or np.any(lengths <= 0) or
            sum(lengths) < duration - 1 / fs):
        raise ValueError("correction segments do not cover square-wave hold")
    count = cycles * samples_per_clock
    times = np.arange(count, dtype=float) / fs
    segment_index = np.minimum(np.searchsorted(np.cumsum(lengths), times,
                                               side="right"), len(levels)-1)
    correction = levels[segment_index]
    centered = np.full(count, float(center_gain))
    if pattern.startswith("minus") or pattern.startswith("plus"):
        offset = int(pattern.replace("minus", "-").replace("plus", ""))
        centered[:] = float(endpoint_gains[offset])
    elif pattern.startswith("hop"):
        amplitude = int(pattern.removeprefix("hop"))
        phase_is_high = ((np.arange(count, dtype=np.int64) *
                          2 * full_cycles) % (2 * count)) < count
        if not start_high:
            phase_is_high = ~phase_is_high
        centered = np.where(phase_is_high,
                            float(endpoint_gains[amplitude]),
                            float(endpoint_gains[-amplitude]))
    command = np.rint(float(park_gain) + correction *
                      (centered - float(park_gain)))
    if (not np.all(np.isfinite(command)) or
            np.max(np.abs(command)) > min(float(max_gain), 32767)):
        raise ValueError("square-wave command exceeds fast-flux DAC range")
    samples = command.astype(np.int16)
    amplitude = int(pattern.removeprefix("hop")) if pattern.startswith("hop") else 0
    return samples, {
        "pattern": pattern, "samples": count, "duration_us": duration,
        "full_cycles": full_cycles,
        "requested_hop_mhz": HOP_MHZ,
        "actual_hop_mhz": full_cycles / duration,
        "start_high": bool(start_high),
        "command_min": int(samples.min()), "command_max": int(samples.max()),
        "commanded_center_samples": int(np.count_nonzero(
            centered == float(center_gain))) if amplitude else None,
        "positive_duty": (float(np.mean(phase_is_high)) if amplitude else None),
        "ideal_carrier_weight": (float(np.sinc(
            amplitude / (2 * (full_cycles / duration))) ** 2)
            if amplitude else None),
        "ideal_model_note": "ideal instantaneous square wave and narrow weak line; not delivered amplitude",
    }


def conditions(center, patterns, *, hold_us, reverse=False):
    rows = [{"name": f"{pattern}_{state}", "flux_ghz": float(center),
             "drive_mhz": 1000.0 * float(center), "gain": 0,
             "preparation_state": state, "reference_state": None,
             "pre_drive_us": PRE_US, "post_drive_us": float(hold_us),
             "phantom_pattern": pattern}
            for pattern in patterns for state in ("g", "e")]
    return list(reversed(rows)) if reverse else rows


def program_specs(center, *, shots=SHOTS, amplitudes=(10, 20, 40)):
    amplitudes = tuple(int(value) for value in amplitudes)
    if (len(set(amplitudes)) != len(amplitudes) or
            not {20, 40}.issubset(amplitudes) or
            not set(amplitudes).issubset({10, 20, 40})):
        raise ValueError("phantom pilot requires clean 20/40-MHz endpoint pairs")
    selected_pairs = tuple(
        pair for amplitude in amplitudes for pair in
        (("center", f"hop{amplitude}"),
         (f"minus{amplitude}", f"plus{amplitude}")))
    specs = []
    for repeat in (0, 1):
        pairs = selected_pairs if repeat == 0 else tuple(reversed(selected_pairs))
        holds = HOLDS_US if repeat == 0 else tuple(reversed(HOLDS_US))
        for pair_index, patterns in enumerate(pairs):
            for hold in holds:
                rows = conditions(center, patterns, hold_us=hold,
                                  reverse=bool(repeat))
                name = f"r{repeat}_pair{pair_index}_hold{str(hold).replace('.', 'p')}"
                specs.append({"name": name, "repeat": repeat,
                              "pair": list(patterns), "patterns": list(patterns),
                              "hold_us": float(hold), "shots": int(shots),
                              "center_ghz": float(center),
                              "start_high": repeat == 0,
                              "order": [row["name"] for row in rows],
                              "conditions": rows, "status": "pending"})
    return specs


def recenter_repeat(specs, *, center, repeat):
    for spec in specs:
        if spec["repeat"] != repeat:
            continue
        if spec["status"] != "pending":
            raise ValueError("cannot recenter an acquired phantom program")
        spec["center_ghz"] = float(center)
        spec["conditions"] = conditions(center, spec["patterns"],
                                        hold_us=spec["hold_us"],
                                        reverse=bool(repeat))
        spec["order"] = [row["name"] for row in spec["conditions"]]


def site_stable(before, after):
    """Allow up to two 2-MHz scout steps when every program is recentered."""
    return bool(abs(float(before["center_ghz"]) -
                    float(after["center_ghz"])) <= .004001 and
                min(float(before["depth"]), float(after["depth"])) >= .15)


def score_contrasts(contrasts):
    """Compare decay rates above the mean static-endpoint background."""
    delta = HOLDS_US[1] - HOLDS_US[0]
    rates = {}
    patterns = tuple(pattern for pattern in PATTERNS if pattern in contrasts)
    amplitudes = tuple(amplitude for amplitude in (10, 20, 40)
                       if f"hop{amplitude}" in contrasts)
    if ("center" not in contrasts or not {20, 40}.issubset(amplitudes) or
            set(patterns) != set(contrasts) or
            any(f"minus{amplitude}" not in contrasts or
                f"plus{amplitude}" not in contrasts
                for amplitude in amplitudes)):
        raise ValueError("incomplete phantom contrast set")
    for pattern in patterns:
        short = float(contrasts[pattern][HOLDS_US[0]])
        long = float(contrasts[pattern][HOLDS_US[1]])
        if (not all(map(math.isfinite, (short, long))) or
                min(short, long) <= .03):
            raise ValueError("unresolved short/long preparation contrast")
        rates[pattern] = math.log(short / long) / delta
    report = {"rates_per_us": rates, "amplitudes_mhz": list(amplitudes),
              "center_excess_by_amplitude": {}}
    for amplitude in amplitudes:
        background = (rates[f"minus{amplitude}"] +
                      rates[f"plus{amplitude}"]) / 2
        center_excess = rates["center"] - background
        hop_excess = rates[f"hop{amplitude}"] - background
        report[f"background{amplitude}_per_us"] = background
        report[f"hop{amplitude}_excess"] = hop_excess
        report["center_excess_by_amplitude"][str(amplitude)] = center_excess
        report[f"hop{amplitude}_fraction_of_center"] = (
            hop_excess / center_excess if center_excess > .01 else None)
    report["center_excess"] = report["center_excess_by_amplitude"]["20"]
    return report


class PhantomProgram(alternating.ShotAlternatingResidentProgram):
    """Four complete park/visit/return/readout subshots with two flux patterns."""

    def __init__(self, soccfg, condition_cfgs, payload_calibration,
                 loop_calibration, *, endpoint_gains, start_high=True):
        cfgs = [dict(cfg) for cfg in condition_cfgs]
        if len(cfgs) != RECORDS_PER_SHOT:
            raise ValueError("phantom program requires four conditions")
        common = ("ff_gain", "ff_park_gain", "opx_resident_pre_us",
                  "opx_resident_post_us", "shots", "reps")
        if any(any(cfg[key] != cfgs[0][key] for key in common)
               for cfg in cfgs[1:]):
            raise ValueError("phantom conditions must share flux, timing, shots")
        patterns = tuple(dict.fromkeys(cfg["opx_phantom_pattern"] for cfg in cfgs))
        observed = {(cfg["opx_phantom_pattern"],
                     cfg["opx_resident_preparation_state"]) for cfg in cfgs}
        if (len(patterns) != 2 or
                frozenset(patterns) not in {frozenset(pair) for pair in PAIRS} or
                observed != {(pattern, state) for pattern in patterns
                             for state in ("g", "e")} or
                any(int(cfg["opx_resident_gain"]) != 0 for cfg in cfgs) or
                float(cfgs[0]["opx_resident_pre_us"]) != PRE_US or
                float(cfgs[0]["opx_resident_post_us"]) not in HOLDS_US):
            raise ValueError("invalid phantom pattern/preparation coverage")
        if set(endpoint_gains) != {-40, -20, -10, 10, 20, 40}:
            raise ValueError("all six static endpoint gains are required")
        self.patterns = patterns
        self.endpoint_gains = {int(k): int(v) for k, v in endpoint_gains.items()}
        self.start_high = bool(start_high)
        self.logical_shots = int(cfgs[0]["shots"])
        if self.logical_shots <= 0:
            raise ValueError("phantom shot count must be positive")
        self.condition_cfgs = cfgs
        run_cfg = dict(cfgs[0], reps=RECORDS_PER_SHOT * self.logical_shots)
        resident.ResidentDriveProgram.__init__(
            self, soccfg, run_cfg, payload_calibration, loop_calibration)

    def _declare_experiment(self):
        super()._declare_experiment()
        cfg = self.cfg
        generator = self.soccfg["gens"][int(cfg["ff_ch"])]
        hold = float(cfg["opx_resident_post_us"])
        _, during, _ = modulated._target_segments(
            self._t1_ff_compensation,
            pre_us=PRE_US + self._t1_ff_settle_us,
            hold_us=hold,
            recovery_us=self._t1_ff_predistortion_recovery_us)
        cycles = int(self.us2cycles(hold, gen_ch=cfg["ff_ch"]))
        self.waveforms = {}
        self.waveform_reports = {}
        for pattern in self.patterns:
            samples, report = square_waveform(
                pattern=pattern, segments=during,
                park_gain=cfg["ff_park_gain"], center_gain=cfg["ff_gain"],
                endpoint_gains=self.endpoint_gains,
                sample_rate_mhz=generator["fs"],
                fabric_rate_mhz=generator["f_fabric"],
                cycles=cycles, max_gain=ff_maxv(self, scaled=True),
                start_high=self.start_high)
            self.waveforms[pattern] = samples
            self.waveform_reports[pattern] = report
        park_samples = sum(
            length for channel, _, _, length in getattr(self, "_ff_ramp_cache", {})
            if channel == int(cfg["ff_ch"]))
        total_samples = park_samples + sum(len(w) for w in self.waveforms.values())
        capacity = ff_envelope_samples(self)
        if total_samples > capacity:
            raise ValueError(f"phantom envelopes need {total_samples} samples; "
                             f"generator has {capacity}")
        self.ff_envelope_report = {
            "park_samples": park_samples,
            "phantom_samples": total_samples - park_samples,
            "total_samples": total_samples, "capacity_samples": capacity}
        for pattern, samples in self.waveforms.items():
            self.add_pulse(ch=cfg["ff_ch"], name=f"q3_phantom_{pattern}",
                           idata=samples, qdata=np.zeros_like(samples))

    def _resident_excursion(self):
        cfg = self.cfg
        if self._t1_ff_compensation is None:
            raise ValueError("phantom experiment requires pinned correction")
        park, target = float(cfg["ff_park_gain"]), float(cfg["ff_gain"])
        before, _, recovery = modulated._target_segments(
            self._t1_ff_compensation,
            pre_us=float(cfg["opx_resident_pre_us"]) + self._t1_ff_settle_us,
            hold_us=float(cfg["opx_resident_post_us"]),
            recovery_us=self._t1_ff_predistortion_recovery_us)
        ff_pulse.play_relative_compensation_segments(
            self, park, target, before)
        self.set_pulse_registers(
            ch=cfg["ff_ch"], freq=0, style="arb", phase=0,
            stdysel="last", gain=ff_maxv(self),
            waveform=f"q3_phantom_{cfg['opx_phantom_pattern']}",
            outsel="input")
        self.pulse(ch=cfg["ff_ch"])
        self.sync_all(0)
        ff_pulse.play_relative_compensation_segments(
            self, park, target, recovery)
        ff_pulse.play_hard_step(self, park)
        self.sync_all(0)


def _condition_configs(base, spec, dc_lookup):
    cfgs = []
    for condition in spec["conditions"]:
        cfg = resident.arm_config(
            base, dict(condition, shots=spec["shots"]), dc_lookup)
        cfg["opx_phantom_pattern"] = condition["phantom_pattern"]
        cfgs.append(cfg)
    return cfgs


def split_records(records, order, *, shots):
    records = list(records)
    if (len(order) != RECORDS_PER_SHOT or len(set(order)) != RECORDS_PER_SHOT or
            len(records) != int(shots) * RECORDS_PER_SHOT):
        raise ValueError("incomplete phantom IQ stream")
    return {name: records[index::RECORDS_PER_SHOT]
            for index, name in enumerate(order)}


def run(*, data_root=localizer.DATA_ROOT, correction_json=None):
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
    correction = localizer.checked_correction(data_root, correction_json)
    session_id = ("q3_phantom_resonance_" +
                  datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") +
                  "_" + uuid.uuid4().hex[:8])
    folder = data_root / "q3" / session_id
    folder.mkdir(parents=True, exist_ok=False)
    path = folder / "manifest.json"
    manifest = {"schema": "q3.phantom-resonance.v1",
                "status": "scouting", "session_id": session_id,
                "code_commit": os.environ.get("Q3_CODE_COMMIT", "unknown"),
                "correction_json": str(correction),
                "correction_sha256": localizer.CORRECTION_SHA256,
                "plan": plan(), "programs": [], "references": []}
    dual.checkpoint(path, manifest)
    try:
        scout = localizer.run(
            data_root=data_root, correction_json=correction,
            parameter_overrides={**wide.parameters(),
                                 "output_suffix": "TLS_Phantom_Resonance_Scout_pre"},
            announce=False)
        manifest["pre_scout_csv"] = str(scout)
        dual.checkpoint(path, manifest)
        selected = select_candidate(dual.read_scout(scout))
        center = float(selected["center_ghz"])
        manifest["pre_selected"] = selected
        manifest["center_ghz"] = center
        dual.checkpoint(path, manifest)

        with localizer.scan_environment(correction):
            manifest["code_commit"] = os.environ["Q3_CODE_COMMIT"]
            dual.checkpoint(path, manifest)
            if int(tls.BaseConfig["ff_park_gain"]) != -25146:
                raise RuntimeError("q3 park gain differs from verified configuration")
            tls.QUBIT, tls.SET_YOKO, tls.outerFolder = "q3", False, str(data_root)
            five.install_scan_calibration(tls)
            compensation = tls._load_correction(str(correction), str(data_root))
            base = ProductionResetSession.passive().apply(tls.BaseConfig)
            five.apply_verified_feedback_timing(base)
            base.update({"apply_flux_tail_compensation": True,
                         "flux_tail_compensation": compensation,
                         "flux_fit_params": tls.FLUX_FIT_PARAMS,
                         "flux_settle_time_us": .5,
                         "flux_predistortion_return_prefix_us": .5,
                         "flux_predistortion_recovery_us": 40.0,
                         "flux_predistortion_overlap_payload_readout": False,
                         "flux_predistortion_round_trip_mode": "stateful",
                         "readout_thermalization_us": 10.0,
                         "ff_ramp_length": PARK_RAMP_US,
                         "qubit_pulse_style": "arb", "do_ff": True,
                         "opx_reset_scheme": "none",
                         "opx_resident_dmem_stream": True,
                         "opx_inter_shot_delay_us": 500.0})
            for hold in HOLDS_US:
                modulated._target_segments(
                    compensation, pre_us=PRE_US + .5,
                    hold_us=hold, recovery_us=40.0)

            def grid_for(site):
                targets = np.asarray([round(site + off / 1000, 3)
                                      for off in ENDPOINT_OFFSETS_MHZ])
                dc, realized = _integer_dc_grid(wide.parameters(), targets, tls)
                return ({float(site): int(dc[3])},
                        {off: int(gain) for off, gain in
                         zip(ENDPOINT_OFFSETS_MHZ, dc) if off},
                        [{"offset_mhz": off, "target_ghz": float(target),
                          "dc_gain": int(gain),
                          "realized_ghz": float(actual)}
                         for off, target, gain, actual in zip(
                             ENDPOINT_OFFSETS_MHZ, targets, dc, realized)])

            dc_lookup, endpoint_gains, grid = grid_for(center)
            manifest["pre_flux_grid"] = grid
            refs = (probe.reference_arms(center, phase="pre") +
                    probe.reference_arms(center, phase="post"))
            for ref in refs:
                ref["shots"] = REFERENCE_SHOTS
                ref["status"] = "pending"
            manifest["references"] = refs
            manifest["programs"] = program_specs(
                center, amplitudes=selected["eligible_amplitudes_mhz"])
            manifest["status"] = "preflight"
            dual.checkpoint(path, manifest)
            soc, soccfg = tls.makeProxy()
            bundle = runtime_bundle(base)
            compiled = {}

            def compile_entry(entry, gains):
                cfgs = _condition_configs(base, entry, dc_lookup)
                program = PhantomProgram(
                    soccfg, cfgs, bundle.payload, bundle.loop,
                    endpoint_gains=gains, start_high=entry["start_high"])
                compiled[entry["name"]] = program
                entry["waveform_reports"] = program.waveform_reports
                entry["ff_envelope_report"] = program.ff_envelope_report
                for pattern, samples in program.waveforms.items():
                    wave_path = folder / f"{entry['name']}_{pattern}_waveform.npz"
                    np.savez_compressed(wave_path, idata=samples)
                    entry.setdefault("waveform_npz", {})[pattern] = str(wave_path)

            first_block_count = len(manifest["programs"]) // 2
            for entry in manifest["programs"][:first_block_count]:
                compile_entry(entry, endpoint_gains)
            for ref in refs[:4]:
                resident.ResidentDriveProgram(
                    soccfg, resident.arm_config(base, ref, dc_lookup),
                    bundle.payload, bundle.loop)
            manifest["first_block_preflight_complete"] = True
            dual.checkpoint(path, manifest)
            raw_refs = {}
            axis = None

            def acquire_ref(ref):
                nonlocal axis
                cfg = resident.arm_config(base, ref, dc_lookup)
                ref["status"] = "acquiring"
                dual.checkpoint(path, manifest)
                program = resident.ResidentDriveProgram(
                    soccfg, cfg, bundle.payload, bundle.loop)
                records = _run_program(
                    soc, program,
                    max(30., _block_timeout_s(cfg, REFERENCE_SHOTS)),
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
                dual.checkpoint(path, manifest)

            for ref in refs[:4]:
                acquire_ref(ref)
            manifest["status"] = "acquiring"
            dual.checkpoint(path, manifest)
            for entry in manifest["programs"]:
                if entry["repeat"] == 1 and "mid_selected" not in manifest:
                    mid_scout = localizer.run(
                        data_root=data_root, correction_json=correction,
                        parameter_overrides={**wide.parameters(),
                                             "output_suffix": "TLS_Phantom_Resonance_Scout_mid"},
                        announce=False)
                    manifest["mid_scout_csv"] = str(mid_scout)
                    dual.checkpoint(path, manifest)
                    try:
                        mid_selected = select_candidate(
                            dual.read_scout(mid_scout), preferred_center=center)
                    except ValueError as exc:
                        manifest["status"] = "halted_midpoint"
                        manifest["mid_selection_error"] = str(exc)
                        dual.checkpoint(path, manifest)
                        return path
                    mid_center = float(mid_selected["center_ghz"])
                    manifest["mid_selected"] = mid_selected
                    if not site_stable(selected, mid_selected):
                        manifest["status"] = "halted_midpoint"
                        manifest["mid_selection_error"] = (
                            "loss line moved by more than two 2-MHz scout steps")
                        dual.checkpoint(path, manifest)
                        return path
                    recenter_repeat(manifest["programs"], center=mid_center,
                                    repeat=1)
                    mid_lookup, endpoint_gains, grid = grid_for(mid_center)
                    dc_lookup.update(mid_lookup)
                    manifest["mid_flux_grid"] = grid
                    manifest["mid_center_ghz"] = mid_center
                    for ref in refs[4:]:
                        ref["flux_ghz"] = mid_center
                        ref["drive_mhz"] = round(mid_center * 1000 + 5, 3)
                        resident.ResidentDriveProgram(
                            soccfg, resident.arm_config(base, ref, dc_lookup),
                            bundle.payload, bundle.loop)
                    for future in manifest["programs"][first_block_count:]:
                        compile_entry(future, endpoint_gains)
                    manifest["second_block_preflight_complete"] = True
                    dual.checkpoint(path, manifest)
                entry["status"] = "acquiring"
                dual.checkpoint(path, manifest)
                records = _run_program(
                    soc, compiled[entry["name"]],
                    max(30., RECORDS_PER_SHOT *
                        _block_timeout_s(base, entry["shots"])),
                    base, total_shots=entry["shots"])
                split = split_records(records, entry["order"],
                                      shots=entry["shots"])
                for condition in entry["conditions"]:
                    subset = split[condition["name"]]
                    raw_path = folder / f"{entry['name']}_{condition['name']}.npz"
                    np.savez_compressed(raw_path, i=[r.i for r in subset],
                                        q=[r.q for r in subset])
                    condition["raw_npz"] = str(raw_path)
                    condition["excited_fraction_pre_axis"] = resident.classify(
                        subset, axis)
                entry["status"] = "complete"
                dual.checkpoint(path, manifest)
            for ref in refs[4:]:
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
            block_scores = {}
            for repeat in (0, 1):
                science_patterns = tuple(dict.fromkeys(
                    pattern for entry in manifest["programs"]
                    if entry["repeat"] == repeat
                    for pattern in entry["patterns"]))
                gathered = {pattern: {hold: [] for hold in HOLDS_US}
                            for pattern in science_patterns}
                ground_spread = 0.0
                for entry in manifest["programs"]:
                    if entry["repeat"] != repeat:
                        continue
                    fractions = {row["name"]: row["excited_fraction_pre_axis"]
                                 for row in entry["conditions"]}
                    ground_spread = max(ground_spread,
                                        abs(fractions[f"{entry['patterns'][0]}_g"] -
                                            fractions[f"{entry['patterns'][1]}_g"]))
                    for pattern in entry["patterns"]:
                        gathered[pattern][entry["hold_us"]].append(
                            fractions[f"{pattern}_e"] -
                            fractions[f"{pattern}_g"])
                center_spread = max(max(values) - min(values)
                                    for values in gathered["center"].values())
                contrasts = {pattern: {hold: float(np.mean(values))
                                       for hold, values in by_hold.items()}
                             for pattern, by_hold in gathered.items()}
                try:
                    block_score = score_contrasts(contrasts)
                    block_score["usable"] = bool(
                        ground_spread <= .10 and center_spread <= .12)
                except ValueError as exc:
                    block_score = {"usable": False, "error": str(exc)}
                block_score.update({"contrasts": contrasts,
                                    "ground_spread": ground_spread,
                                    "center_pair_spread": center_spread})
                block_scores[f"r{repeat}"] = block_score
            manifest["effect_report"] = block_scores
            dual.checkpoint(path, manifest)
            post_scout = localizer.run(
                data_root=data_root, correction_json=correction,
                parameter_overrides={**wide.parameters(),
                                     "output_suffix": "TLS_Phantom_Resonance_Scout_post"},
                announce=False)
            manifest["post_scout_csv"] = str(post_scout)
            try:
                manifest["post_selected"] = select_candidate(
                    dual.read_scout(post_scout),
                    preferred_center=manifest["mid_center_ghz"])
            except ValueError as exc:
                manifest["post_selection_error"] = str(exc)
            if "post_selected" in manifest:
                manifest["feature_stable"] = bool(
                    site_stable(selected, mid_selected) and
                    site_stable(mid_selected, manifest["post_selected"]))
                manifest["ten_mhz_endpoints_quiet_all_scouts"] = all(
                    10 in scout["eligible_amplitudes_mhz"] for scout in
                    (selected, mid_selected, manifest["post_selected"]))
            else:
                manifest["feature_stable"] = False
                manifest["ten_mhz_endpoints_quiet_all_scouts"] = False
            valid = (manifest["post_readout_score"]["valid"] and
                     all(item["usable"] for item in
                         manifest["transfer_control"].values()) and
                     all(item["usable"] for item in block_scores.values()) and
                     manifest["feature_stable"])
            manifest["status"] = ("complete" if valid else
                                  "complete_controls_unstable")
            dual.checkpoint(path, manifest)
            return path
    except BaseException as exc:
        manifest["status"] = "failed"
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        dual.checkpoint(path, manifest)
        raise


def plan():
    return {"hardware_access": False, "reset_mode": "passive",
            "site": "fresh bidirectional q3 loss line with quiet ±20/±40-MHz endpoints; ±10 optional",
            "full_cycle_hop_mhz": HOP_MHZ,
            "commanded_peak_excursions_mhz": [10, 20, 40],
            "holds_us": list(HOLDS_US), "patterns": list(PATTERNS),
            "programs": 2 * len(HOLDS_US) * len(PAIRS),
            "minimum_programs": 16,
            "optional_ten_mhz_amplitude": True,
            "shots_per_program": SHOTS,
            "conditions_per_shot": RECORDS_PER_SHOT,
            "pre_mid_post_wide_scout": True,
            "recenter_tolerance_mhz_per_scout": 4.0,
            "reversed_second_block": True,
            "full_return_before_readout_us": 40.0,
            "raw_iq_and_compiled_waveforms_saved": True,
            "delivered_square_wave_verified": False,
            "interpretation": "A signal above both static endpoints warrants independent fast-edge verification; programmed square-wave weights are not delivered-amplitude calibration.",
            "terminal": "no custom run-progress messages"}


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
