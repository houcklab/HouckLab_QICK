"""Time-resolved q3 loss-flank sentinel, experiment-only.

The active run is deliberately gated by a fresh passive scout and static
profiles. QICK resident streaming pauses at data-memory bank handshakes, so
per-shot host completion times are acquired rather than inventing a uniform
global sample clock. No production TLS scan or reset default is modified.
"""

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import time
import uuid

import numpy as np
from scipy.optimize import curve_fit

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSPumpProbeLocalizer as localizer,
    TLSPumpProbeProtocolCheck as protocol,
    TLSPumpProbeResidentProbe as probe,
    TLSPumpProbeWidePassiveScan as wide,
    TLSPumpProbeShotAlternating as alternating,
    TLSPumpProbeResidentDrive as resident,
    TLSSwapHoldPilot as swap,
    TLSWeakAfterglowScreen as weak,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.programs import (
    _declare_common, _pulse_pi_and_align, _reserved_registers,
    allocate_named_registers, allocate_registers, resident_control_names,
)


PREFERRED_A_GHZ = 4.0947


def _quiet_window(indexed, center):
    """Reject reproducible narrow loss without vetoing one noisy direction."""
    neighbors = [round(center + .002*i, 3) for i in range(-5, 6)]
    if any(frequency not in indexed for frequency in neighbors):
        return None
    values = np.asarray([
        [weak._survival(indexed[frequency], 25, suffix)
         for frequency in neighbors]
        for suffix in ("", "_scan_up", "_scan_down")], dtype=float)
    if not np.all(np.isfinite(values)):
        return None
    directional_floor = float(np.min(np.median(values, axis=1)))
    frequency_floor = float(np.min(np.median(values, axis=0)))
    center_survival = float(np.median(values[:, 5]))
    if (directional_floor < .68 or frequency_floor < .58 or
            center_survival < .62):
        return None
    return {"directional_median_floor": directional_floor,
            "frequency_median_floor": frequency_floor,
            "center_survival": center_survival,
            "min_survival": float(np.min(values))}


def ranked_scout_candidates(rows):
    """Rank distinct broad troughs; a 20-cycle profile decides persistence."""
    indexed = {round(float(row["target_frequency_ghz"]), 3): row for row in rows}
    expected = {round(3.8 + .002 * i, 3) for i in range(251)}
    if len(rows) != 251 or set(indexed) != expected:
        raise ValueError("sentinel requires one complete 251-point wide scout")
    candidate_lines = []
    for center in sorted(indexed):
        if not 3.83 <= center <= 4.27:
            continue
        groups = {
            "center": [round(center + .002 * i, 3) for i in (-1, 0, 1)],
            "left": [round(center - .002 * i, 3) for i in (4, 5, 6)],
            "right": [round(center + .002 * i, 3) for i in (4, 5, 6)],
        }
        if any(f not in indexed for group in groups.values() for f in group):
            continue
        depths = {}
        for name, suffix in (("combined", ""), ("up", "_scan_up"),
                             ("down", "_scan_down")):
            values = {label: [weak._survival(indexed[f], 25, suffix)
                              for f in fs] for label, fs in groups.items()}
            if any(not math.isfinite(v) for vs in values.values() for v in vs):
                break
            depths[name] = min(float(np.median(values["left"])),
                               float(np.median(values["right"]))) - float(
                                   np.mean(values["center"]))
        if (len(depths) == 3 and depths["combined"] >= .12 and
                min(depths["up"], depths["down"]) >= .08):
            frequency = [round(1000*center + 2*i, 1) for i in range(-3, 4)]
            profile = fit_or_reject_profile(
                frequency,
                [weak._survival(indexed[round(target/1000, 3)], 25)
                 for target in frequency])
            if profile["gate"]["passed"]:
                candidate_lines.append({
                    "center_ghz": center, "depth": depths["combined"],
                    "depth_scan_up": depths["up"],
                    "depth_scan_down": depths["down"],
                    "scout_profile_contrast": profile["fit"]["measured_contrast_6mhz"]})
    ranked = sorted(candidate_lines,
                    key=lambda x: min(x["depth_scan_up"], x["depth_scan_down"]),
                    reverse=True)
    separated = []
    for candidate in ranked:
        if all(abs(candidate["center_ghz"]-old["center_ghz"]) >= .008-1e-9
               for old in separated):
            separated.append(candidate)
    return separated


def select_sites(rows):
    """Return provisional A/B scout lines and one quiet C site."""
    indexed = {round(float(row["target_frequency_ghz"]), 3): row for row in rows}
    candidate_lines = ranked_scout_candidates(rows)
    if not candidate_lines:
        raise ValueError("no qualified first loss line")
    near_preferred = [x for x in candidate_lines if
                      abs(x["center_ghz"] - PREFERRED_A_GHZ) <= .006]
    a = (near_preferred or candidate_lines)[0]
    alternatives = [x for x in candidate_lines if
                    abs(x["center_ghz"] - a["center_ghz"]) >= .020 - 1e-9]
    if not alternatives:
        raise ValueError("no qualified second loss line at least 20 MHz from first")
    b = alternatives[0]
    controls = []
    for center in sorted(indexed):
        if (not 3.83 <= center <= 4.27 or
                min(abs(center - x["center_ghz"]) for x in candidate_lines) < .010):
            continue
        metrics = _quiet_window(indexed, center)
        if metrics is not None:
            controls.append({"center_ghz": center, **metrics})
    if not controls:
        raise ValueError("no clean control at least 10 MHz from loss sites")
    c = min(controls, key=lambda x: (abs(x["center_ghz"] - 4.060),
                                     -x["directional_median_floor"]))
    return {"A": a, "B": b, "C": c}


def _loss_lorentzian(frequency_mhz, background, depth, center_mhz, hwhm_mhz):
    return background - depth / (1.0 +
                                 ((np.asarray(frequency_mhz) - center_mhz) /
                                  hwhm_mhz) ** 2)


def fit_static_profile(frequency_mhz, survival):
    frequency = np.asarray(frequency_mhz, dtype=float)
    values = np.asarray(survival, dtype=float)
    if (frequency.ndim != 1 or values.shape != frequency.shape or
            frequency.size < 7 or not np.all(np.isfinite(values)) or
            not np.all(np.diff(frequency) > 0)):
        raise ValueError("static profile needs seven or more ordered finite points")
    center_guess = float(frequency[np.argmin(values)])
    try:
        params, covariance = curve_fit(
            _loss_lorentzian, frequency, values,
            p0=(float(max(values)), max(float(max(values)-min(values)), .01),
                center_guess, 2.0),
            bounds=([0, 0, float(min(frequency)), .2],
                    [1.5, 1.5, float(max(frequency)), 10.0]),
            maxfev=20000)
    except (RuntimeError, ValueError) as exc:
        raise ValueError("Lorentzian static profile fit failed") from exc
    background, depth, center, width = map(float, params)
    near = float(_loss_lorentzian(center, *params))
    flanks = [_loss_lorentzian(center + offset, *params) for offset in (-6, 6)]
    contrast = float(min(flanks) - near)
    rmse = float(np.sqrt(np.mean((values - _loss_lorentzian(frequency, *params))**2)))
    # The acquired seven-point grid is ±6 MHz about the *scout* center.
    # Its edge samples remain measured controls if the fitted center moves
    # within the inner ±2-MHz guard; do not demand fictitious new samples
    # exactly 6 MHz from that continuous fitted center.
    center_index = int(np.argmin(abs(frequency-center)))
    measured_contrast = float(min(values[0], values[-1])-
                              values[center_index])
    return {"background": background, "depth": depth,
            "center_mhz": center, "hwhm_mhz": width,
            "contrast_6mhz": contrast, "fit_rmse": rmse,
            "measured_contrast_6mhz": measured_contrast,
            "profile_min_mhz": float(frequency[0]),
            "profile_max_mhz": float(frequency[-1]),
            "covariance": np.asarray(covariance).tolist()}


def profile_gate(profile):
    contrast = float(profile["contrast_6mhz"])
    measured = float(profile.get("measured_contrast_6mhz", float("nan")))
    width = float(profile["hwhm_mhz"])
    passed = bool(math.isfinite(contrast) and contrast >= .15 and
                  math.isfinite(measured) and measured >= .15 and
                  math.isfinite(float(profile.get("fit_rmse", float("nan")))) and
                  float(profile.get("fit_rmse", float("inf"))) <= .08 and
                  math.isfinite(width) and .2 <= width <= 10.0 and
                  float(profile["profile_min_mhz"]) + 4 <=
                  float(profile["center_mhz"]) <=
                  float(profile["profile_max_mhz"]) - 4)
    return {"passed": passed, "contrast_6mhz": contrast,
            "measured_contrast_6mhz": measured,
            "minimum_contrast": .15}


def fit_or_reject_profile(frequency_mhz, survival):
    try:
        fit = fit_static_profile(frequency_mhz, survival)
    except ValueError as exc:
        return {"fit": None, "gate": {"passed": False},
                "gate_error": str(exc)}
    return {"fit": fit, "gate": profile_gate(fit)}


def normalize_profile_survival(raw_fraction, *, ground, excited):
    """Match the wide scout's normalized e-survival convention."""
    span = float(excited)-float(ground)
    if not math.isfinite(span) or span < .15:
        raise ValueError("profile readout transfer is too small to normalize")
    return (np.asarray(raw_fraction, dtype=float)-float(ground))/span


def append_qualified_profile(accepted, candidate, profile_key, report):
    """Keep separated, high-shot profiles in scout priority order."""
    if not report["gate"]["passed"]:
        return False
    fit = report["fit"]
    if any(abs(fit["center_mhz"]-item["fit"]["center_mhz"]) < 20.0
           for item in accepted):
        return False
    accepted.append({"candidate": candidate, "fit": fit,
                     "profile_key": profile_key})
    return True


def make_flanks(profile):
    center = float(profile["center_mhz"])
    width = float(profile["hwhm_mhz"])
    depth = float(profile["depth"])
    offset = width / math.sqrt(3)
    def derivative(target):
        delta = target - center
        return 2 * depth * width**2 * delta / (delta**2 + width**2)**2
    minus, plus = center - offset, center + offset
    return {"A_minus_mhz": minus, "A_plus_mhz": plus,
            "slope_minus_per_mhz": derivative(minus),
            "slope_plus_per_mhz": derivative(plus)}


def integer_dac_targets(target_mhz, inverse_gain):
    """Quantize each physical target and its ±0.5-MHz dithers independently."""
    result = {}
    for name, mhz in target_mhz.items():
        value = float(mhz)
        base = int(np.rint(inverse_gain(value)))
        low = int(np.rint(inverse_gain(value - .5)))
        high = int(np.rint(inverse_gain(value + .5)))
        if not all(-32768 <= gain <= 32767 for gain in (base, low, high)):
            raise ValueError(f"{name} target/dither exceeds signed DAC range")
        if low == high or not (min(low, high) <= base <= max(low, high)):
            raise ValueError(f"{name} dither collapses on integer DAC grid")
        result[name] = {"target_mhz": value, "gain_dac": base,
                        "dither_minus_dac": low-base,
                        "dither_plus_dac": high-base}
    return result


SCIENCE_ORDER = ("A_minus", "A_plus", "B", "C", "C", "B",
                 "A_plus", "A_minus")


def sentinel_conditions(targets):
    """One e-prepared, 25-us corrected visit at each palindrome position."""
    if set(targets) != {"A_minus", "A_plus", "B", "C"}:
        raise ValueError("sentinel requires A±, B, C DAC targets")
    return [{"name": f"{site}_{position}", "site": site,
             "position": position, "half": "early" if position < 4 else "late",
             "flux_ghz": float(targets[site]["target_mhz"]) / 1000.0,
             "gain_dac": int(targets[site]["gain_dac"]),
             "state": "e", "reference_state": None,
             "hold_us": 25.0}
            for position, site in enumerate(SCIENCE_ORDER)]


class ShotClock:
    """Retain host-observed completion times, including stream bank gaps."""

    def __init__(self, shots, *, wall_start_ns=None,
                 monotonic_start_ns=None, now_ns=None):
        self.shots = int(shots)
        if self.shots <= 0:
            raise ValueError("shot clock needs positive shot count")
        self.wall_start_ns = int(time.time_ns() if wall_start_ns is None
                                 else wall_start_ns)
        self.monotonic_start_ns = int(time.monotonic_ns() if monotonic_start_ns is None
                                      else monotonic_start_ns)
        self.now_ns = time.monotonic_ns if now_ns is None else now_ns
        self.values = [None] * self.shots

    def __call__(self, completed, total):
        if int(total) != self.shots or not 1 <= int(completed) <= self.shots:
            raise ValueError("unexpected resident-stream progress counter")
        index = int(completed)-1
        if self.values[index] is not None:
            raise ValueError("duplicate resident-stream completion callback")
        self.values[index] = self.wall_start_ns + (
            int(self.now_ns()) - self.monotonic_start_ns)

    def finish(self):
        if any(value is None for value in self.values):
            raise ValueError("incomplete per-shot host timestamp series")
        stamps = np.asarray(self.values, dtype=np.int64)
        delta = np.diff(stamps)
        if np.any(delta < 0):
            raise ValueError("non-monotonic per-shot host timestamps")
        # Multiple completion callbacks from one host poll may differ by
        # microseconds or nanoseconds, even though their actual shot times
        # cannot be resolved. Keep those raw stamps but invalidate both ends.
        unresolved = delta < 500_000
        positive = delta[~unresolved]
        if positive.size == 0:
            raise ValueError("host timestamps cannot resolve any shot interval")
        # The high tail is mostly memory-bank handshakes and host scheduling.
        period = int(np.median(np.sort(positive)[:max(1, int(.75 * len(positive)))]))
        valid = [True] * self.shots
        for index, short in enumerate(unresolved):
            if short:
                valid[index] = False
                valid[index+1] = False
        gaps = [False] + [bool(step > 2 * period) for step in delta]
        return {"observed_utc_ns": stamps.tolist(), "valid": valid,
                "gap_after_previous": gaps, "median_shot_period_ns": period,
                "timing_method": "host progress callback; poll-limited, not exact tProc time"}


class SentinelProgram(swap.SwapHoldProgram):
    """Eight corrected, one-readout subshots per resident stream unit."""

    def __init__(self, soccfg, condition_cfgs, payload_calibration,
                 loop_calibration):
        cfgs = [dict(cfg) for cfg in condition_cfgs]
        if len(cfgs) != 8:
            raise ValueError("sentinel needs exactly eight subshot configs")
        common = ("ff_park_gain", "shots", "reps")
        if any(any(cfg[key] != cfgs[0][key] for key in common)
               for cfg in cfgs[1:]):
            raise ValueError("sentinel conditions must share park and shot count")
        if any(float(cfg["opx_swap_hold_us"]) != float(cfgs[0]["opx_swap_hold_us"])
               for cfg in cfgs[1:]):
            raise ValueError("sentinel subshots must have matched target dwells")
        self.logical_shots = int(cfgs[0]["shots"])
        if self.logical_shots <= 0:
            raise ValueError("sentinel logical shot count must be positive")
        self.conditions_per_shot = 8
        self.condition_cfgs = cfgs
        self.reset_mode = cfgs[0].get("opx_sentinel_reset_mode", "passive")
        if self.reset_mode not in ("passive", "dump"):
            raise ValueError("sentinel reset must be passive or dump")
        self.dump_gain_dac = cfgs[0].get("opx_sentinel_dump_gain_dac")
        if self.reset_mode == "dump" and self.dump_gain_dac is None:
            raise ValueError("dump mode needs a fresh strong-line DAC target")
        if any(cfg.get("opx_sentinel_reset_mode", "passive") != self.reset_mode
               for cfg in cfgs):
            raise ValueError("mixed reset modes inside one shot")
        run_cfg = dict(cfgs[0], reps=8*self.logical_shots)
        super().__init__(soccfg, run_cfg, payload_calibration, loop_calibration)

    def _emit_body(self):
        if self.reset_mode == "passive":
            super()._emit_body()
            return
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
        pump_gain = self.cfg["ff_gain"]
        try:
            self.cfg["ff_gain"] = int(self.dump_gain_dac)
            self._wait_t1_payload(60.0)
        finally:
            self.cfg["ff_gain"] = pump_gain
        park_down()
        self.sync_all(self.us2cycles(float(self.reset_config.inter_shot_delay_us)))

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
        self.regwi(0, controls["shot_loop"], self.logical_shots-1)
        self._initialize_stream(
            controls, **alternating.stream_dimensions(self.logical_shots,
                                                       records_per_shot=8),
            prefix="Q3_MS_SENTINEL")
        self._begin_park_lifecycle()
        self.label("Q3_MS_SENTINEL_SHOT_LOOP")
        run_cfg = self.cfg
        for cfg in self.condition_cfgs:
            self.cfg = cfg
            self._emit_body()
        self.cfg = run_cfg
        self.mathi(0, controls["done"], controls["done"], "+", 8)
        self.memwi(0, controls["done"], self.done_addr)
        self._stream_after_shot()
        self.loopnz(0, controls["shot_loop"], "Q3_MS_SENTINEL_SHOT_LOOP")
        self._finish_stream()
        self._end_park_lifecycle()
        self.end()


PROFILE_OFFSETS_MHZ = (-6, -4, -2, 0, 2, 4, 6)
PROFILE_CYCLES = 20
PROFILE_SHOTS_PER_CYCLE = 100
SCIENCE_CHUNKS = 12
NULL_CHUNKS = 3
CHUNK_TARGET_S = 5.0
CAL_SHOTS = 100
REFERENCE_SHOTS = 400


def profile_conditions(coarse_center_mhz, control, *, inverse_gain,
                       reverse=False):
    center = float(coarse_center_mhz)
    arms = [{"name": f"profile_{offset:+d}", "site": f"offset_{offset:+d}",
             "target_mhz": center + offset,
             "flux_ghz": (center + offset)/1000.0,
             "gain_dac": int(np.rint(inverse_gain(center + offset))),
             "state": "e", "reference_state": None, "hold_us": 25.0}
            for offset in PROFILE_OFFSETS_MHZ]
    arms.append({"name": "profile_C", "site": "C",
                 "target_mhz": float(control["target_mhz"]),
                 "flux_ghz": float(control["target_mhz"])/1000,
                 "gain_dac": int(control["gain_dac"]), "state": "e",
                 "reference_state": None, "hold_us": 25.0})
    return list(reversed(arms)) if reverse else arms


def calibration_conditions(targets):
    arms = []
    for site in ("A_minus", "A_plus", "B"):
        target = targets[site]
        for sign, suffix in ((-1, "m"), (1, "p")):
            offset = int(target[f"dither_{'minus' if sign < 0 else 'plus'}_dac"])
            arms.append({"name": f"{site}_{suffix}", "site": site,
                         "target_mhz": float(target["target_mhz"]) + sign*.5,
                         "flux_ghz": (float(target["target_mhz"])+sign*.5)/1000,
                         "gain_dac": int(target["gain_dac"])+offset,
                         "dc_offset_dac": offset, "state": "e",
                         "reference_state": None, "hold_us": 25.0})
    for state in ("g", "e"):
        target = targets["C"]
        arms.append({"name": f"ref_{state}", "site": "C",
                     "target_mhz": float(target["target_mhz"]),
                     "flux_ghz": float(target["target_mhz"])/1000,
                     "gain_dac": int(target["gain_dac"]), "state": "g",
                     "reference_state": state, "hold_us": 25.0})
    return arms


def select_null_sites(rows, selected):
    indexed = {round(float(row["target_frequency_ghz"]), 3): row for row in rows}
    chosen = []
    excluded = [float(selected[name]["center_ghz"]) for name in ("A", "B", "C")]
    anchors = (3.900, 4.200, 4.250)
    for anchor in anchors:
        choices = []
        for frequency in sorted(indexed):
            if not 3.83 <= frequency <= 4.27:
                continue
            if min(abs(frequency - old) for old in excluded + chosen) < .010:
                continue
            metrics = _quiet_window(indexed, frequency)
            if metrics is not None:
                choices.append((abs(frequency-anchor),
                                -metrics["directional_median_floor"], frequency))
        if not choices:
            raise ValueError("no three distinct quiet null-pass windows")
        chosen.append(min(choices)[2])
    return {site: value for site, value in zip(("A_minus", "A_plus", "B"), chosen)}


def null_conditions(null_sites, *, inverse_gain, control):
    targets = {site: {"target_mhz": 1000.0 * ghz,
                      "gain_dac": int(np.rint(inverse_gain(1000.0 * ghz)))}
               for site, ghz in null_sites.items()}
    targets["C"] = dict(control)
    return sentinel_conditions(targets)


def condition_config(base, condition, *, shots, reset_mode, dump_gain_dac=None):
    """Adapt a single physical integer DAC target to the proven swap pulse."""
    arm = {"flux_ghz": float(condition["flux_ghz"]),
           "hold_us": float(condition["hold_us"]),
           "state": condition["state"], "shots": int(shots)}
    cfg = swap.arm_config(base, arm, {arm["flux_ghz"]: int(condition["gain_dac"])})
    cfg["opx_resident_reference_state"] = condition.get("reference_state")
    cfg["opx_sentinel_reset_mode"] = reset_mode
    cfg["opx_sentinel_dump_gain_dac"] = dump_gain_dac
    return cfg


def acquire_chunk(soc, program, cfg, *, shots, path, order, run_program,
                  wall_start_ns=None, monotonic_start_ns=None, now_ns=None,
                  timeout_s=30.0):
    """Acquire eight raw-IQ records and host time per logical shot atomically."""
    clock = ShotClock(shots, wall_start_ns=wall_start_ns,
                      monotonic_start_ns=monotonic_start_ns, now_ns=now_ns)
    records = run_program(soc, program, timeout_s, cfg,
                          total_shots=int(shots), progress=clock)
    timing = clock.finish()
    if len(records) != 8*int(shots) or len(order) != 8:
        raise RuntimeError("sentinel chunk returned incomplete eight-subshot IQ")
    iq = np.asarray([(record.i, record.q) for record in records],
                    dtype=np.int64).reshape(int(shots), 8, 2)
    path = Path(path)
    pending = path.with_suffix(".pending")
    with pending.open("wb") as stream:
        np.savez_compressed(
            stream, iq=iq, order=np.asarray(order),
            observed_utc_ns=np.asarray(timing["observed_utc_ns"], dtype=np.int64),
            timing_valid=np.asarray(timing["valid"], dtype=bool),
            gap_after_previous=np.asarray(timing["gap_after_previous"], dtype=bool))
    os.replace(pending, path)
    return {"raw_npz": str(path), "shots": int(shots),
            "first_observed_utc_ns": timing["observed_utc_ns"][0],
            "last_observed_utc_ns": timing["observed_utc_ns"][-1],
            "median_shot_period_ns": timing["median_shot_period_ns"],
            "host_timing_valid_fraction": float(np.mean(timing["valid"])),
            "bank_or_host_gap_count": int(sum(timing["gap_after_previous"])),
            "timing_method": timing["timing_method"]}


def _iq_from_npz(path):
    with np.load(path, allow_pickle=False) as raw:
        return raw["iq"]


def _project_iq(iq, axis):
    complex_iq = np.asarray(iq[..., 0], dtype=float) + 1j*np.asarray(
        iq[..., 1], dtype=float)
    return np.real(complex_iq*np.exp(-1j*float(axis["theta_rad"])))


def _excited_fractions(path, axis):
    with np.load(path, allow_pickle=False) as raw:
        projected = _project_iq(raw["iq"], axis)
        names = [str(x) for x in raw["order"]]
    return {name: float(np.mean(projected[:, index] > axis["threshold"]))
            for index, name in enumerate(names)}


def _acquire_reference(soc, soccfg, base, bundle, control_ghz, control_gain,
                       *, phase, folder, manifest, manifest_path, run_program,
                       axis=None):
    """Use the established four-arm frozen-axis/transfer reference bundle."""
    result = {}
    raw = {}
    for arm in probe.reference_arms(control_ghz, phase=phase):
        arm["shots"] = REFERENCE_SHOTS
        name = arm["name"]
        manifest.setdefault("references", {})[name] = {"status": "acquiring"}
        protocol.checkpoint(manifest_path, manifest)
        cfg = resident.arm_config(base, arm, {float(control_ghz): int(control_gain)})
        program = resident.ResidentDriveProgram(
            soccfg, cfg, bundle.payload, bundle.loop)
        records = run_program(soc, program, 30.0, cfg,
                              total_shots=REFERENCE_SHOTS)
        if len(records) != REFERENCE_SHOTS:
            raise RuntimeError(f"{name}: incomplete reference IQ")
        iq = np.asarray([(r.i, r.q) for r in records], dtype=np.int64)
        path = folder / f"{name}.npz"
        pending = path.with_suffix(".pending")
        with pending.open("wb") as stream:
            np.savez_compressed(stream, iq=iq)
        os.replace(pending, path)
        raw[name] = resident.record_iq(records)
        result[name] = {"status": "complete", "raw_npz": str(path)}
        manifest["references"][name] = result[name]
        protocol.checkpoint(manifest_path, manifest)
    if axis is None:
        axis = resident.fit_axis(raw[f"ref_g_{phase}"], raw[f"ref_e_{phase}"])
        score = {"fidelity": axis["fidelity"], "valid": axis["valid"]}
    else:
        score = resident.score_axis(axis, raw[f"ref_g_{phase}"],
                                    raw[f"ref_e_{phase}"])
    transfer = {state: resident.classify(
        [resident.SingleIQ(int(x.real), int(x.imag)) for x in
         raw[f"ref_transfer_{state}_{phase}"]], axis)
                for state in ("g", "e")}
    transfer["usable"] = resident.transfer_usable(transfer["g"], transfer["e"])
    return axis, {"axis": score, "transfer": transfer}


def _base_config(tls, correction, *, data_root, reset_mode):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
        FivePointApplesToApples as five,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import (
        ProductionResetSession,
    )
    if int(tls.BaseConfig["ff_park_gain"]) != -25146:
        raise RuntimeError("q3 park gain differs from verified configuration")
    five.install_scan_calibration(tls)
    base = ProductionResetSession.passive().apply(tls.BaseConfig)
    five.apply_verified_feedback_timing(base)
    base.update({"apply_flux_tail_compensation": True,
                 "flux_tail_compensation": tls._load_correction(
                     str(correction), str(data_root)),
                 "flux_fit_params": tls.FLUX_FIT_PARAMS,
                 "flux_settle_time_us": .5,
                 "flux_predistortion_return_prefix_us": .5,
                 "flux_predistortion_recovery_us": 40.0,
                 "flux_predistortion_overlap_payload_readout": False,
                 "flux_predistortion_round_trip_mode": "stateful",
                 "readout_thermalization_us": 10.0,
                 "qubit_pulse_style": "arb", "do_ff": True,
                 "opx_reset_scheme": "none",
                 "opx_resident_dmem_stream": True,
                 "opx_poll_interval_s": .0005,
                 "opx_inter_shot_delay_us": 500.0 if reset_mode == "passive" else 0.0})
    return base


def _inverse_gain(tls):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_fit
    parameters = wide.parameters()
    gains = np.arange(int(parameters["dc_min"]), int(parameters["dc_max"])+1,
                      dtype=np.int64)
    frequency = flux_fit.estimate_fit_frequency_ghz_array(
        tls.FLUX_FIT_PARAMS, gains)
    if np.all(np.diff(frequency) < 0):
        frequency, gains = frequency[::-1], gains[::-1]
    elif not np.all(np.diff(frequency) > 0):
        raise RuntimeError("q3 frequency-to-DAC model is nonmonotonic")

    def convert(mhz):
        target = float(mhz)/1000.0
        if not float(frequency[0]) <= target <= float(frequency[-1]):
            raise ValueError("sentinel target is outside calibrated flux model")
        gain = int(np.rint(np.interp(target, frequency, gains)))
        realized = float(flux_fit.estimate_fit_frequency_ghz_array(
            tls.FLUX_FIT_PARAMS, np.asarray([gain], dtype=np.int64))[0])
        if abs(realized-target) > .0001:
            raise ValueError("sentinel nearest-DAC error exceeds 0.1 MHz")
        return gain
    return convert


def _compile_program(soccfg, base, bundle, conditions, *, shots,
                     reset_mode, dump_gain_dac):
    configs = [condition_config(base, condition, shots=shots,
                                reset_mode=reset_mode,
                                dump_gain_dac=dump_gain_dac)
               for condition in conditions]
    return SentinelProgram(soccfg, configs, bundle.payload, bundle.loop), configs[0]


def _run_profile(soc, soccfg, base, bundle, *, line_name, coarse_mhz,
                 control, inverse_gain, axis, folder, manifest,
                 manifest_path, run_program, reset_mode, dump_gain_dac,
                 transfer_levels, phase="pre"):
    report = {"line": line_name, "coarse_center_mhz": coarse_mhz,
              "cycles": [], "status": "running"}
    manifest.setdefault("profiles", {})[f"{line_name}_{phase}"] = report
    protocol.checkpoint(manifest_path, manifest)
    by_frequency = {coarse_mhz+offset: [] for offset in PROFILE_OFFSETS_MHZ}
    for cycle in range(PROFILE_CYCLES):
        arms = profile_conditions(coarse_mhz, control,
                                  inverse_gain=inverse_gain,
                                  reverse=bool(cycle % 2))
        program, cfg = _compile_program(
            soccfg, base, bundle, arms, shots=PROFILE_SHOTS_PER_CYCLE,
            reset_mode=reset_mode, dump_gain_dac=dump_gain_dac)
        path = folder / f"profile_{line_name}_{phase}_{cycle:02d}.npz"
        result = acquire_chunk(
            soc, program, cfg, shots=PROFILE_SHOTS_PER_CYCLE, path=path,
            order=[a["name"] for a in arms], run_program=run_program,
            timeout_s=30.0)
        fractions = _excited_fractions(path, axis)
        for arm in arms:
            if arm["site"] != "C":
                by_frequency[arm["target_mhz"]].append(fractions[arm["name"]])
        report["cycles"].append({"cycle": cycle, **result,
                                  "excited_fractions": fractions})
        protocol.checkpoint(manifest_path, manifest)
    frequency = sorted(by_frequency)
    average = [float(np.mean(by_frequency[f])) for f in frequency]
    normalized = normalize_profile_survival(
        average, ground=transfer_levels["g"], excited=transfer_levels["e"])
    report["raw_excited_fractions"] = average
    report["normalized_survival"] = normalized.tolist()
    report["reference_transfer"] = dict(transfer_levels)
    report.update(fit_or_reject_profile(frequency, normalized))
    report["status"] = "complete"
    protocol.checkpoint(manifest_path, manifest)
    return report


def _calibration_report(path, axis):
    fractions = _excited_fractions(path, axis)
    with np.load(path, allow_pickle=False) as raw:
        iq = raw["iq"]
    # score_axis expects complex IQ; retain the actual quadratures rather
    # than the thresholded fractions when validating a frozen axis.
    ground_iq = iq[:, 6, 0] + 1j*iq[:, 6, 1]
    excited_iq = iq[:, 7, 0] + 1j*iq[:, 7, 1]
    score = resident.score_axis(axis, ground_iq, excited_iq)
    slopes = {site: -(fractions[f"{site}_p"] - fractions[f"{site}_m"])
              for site in ("A_minus", "A_plus", "B")}
    # A hundred shots cannot resolve each 0.5-MHz dither slope reliably;
    # retain the per-chunk estimate but gate its sign after pooling the run.
    usable = bool(score["valid"])
    return {"fractions": fractions, "readout_score": score,
            "line_shift_slopes_per_mhz": slopes, "valid": usable}


def pooled_dither_gate(reports, *, shots_per_calibration):
    """Test signed slopes on all calibrations, retaining local readout checks."""
    reports = list(reports)
    if not reports or shots_per_calibration <= 0:
        raise ValueError("pooled dither needs completed calibrations")
    pairs = {site: (f"{site}_m", f"{site}_p")
             for site in ("A_minus", "A_plus", "B")}
    fractions = {key: float(np.mean([report["fractions"][key]
                                     for report in reports]))
                 for pair in pairs.values() for key in pair}
    shots = len(reports)*int(shots_per_calibration)
    slopes, z = {}, {}
    for site, (minus, plus) in pairs.items():
        slopes[site] = fractions[minus]-fractions[plus]
        variance = (fractions[minus]*(1-fractions[minus]) +
                    fractions[plus]*(1-fractions[plus]))/shots
        z[site] = (slopes[site]/math.sqrt(variance)
                   if variance > 0 else 0.0)
    valid = (all(report["readout_score"]["valid"] for report in reports)
             and slopes["A_minus"] >= .02 and z["A_minus"] >= 3
             and slopes["A_plus"] <= -.02 and z["A_plus"] <= -3
             and slopes["B"] >= .02 and z["B"] >= 3)
    return {"valid": bool(valid), "slopes_per_mhz": slopes,
            "slope_z": z, "pooled_shots_per_arm": shots,
            "fractions": fractions}


def _check_passive_predecessor(path, *, correction_sha256):
    if path is None:
        raise ValueError("--reset dump requires --passive-manifest from a completed pass")
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if (payload.get("schema") != "q3.tls-millisecond-sentinel.v1" or
            payload.get("reset_mode") != "passive" or
            payload.get("status") != "complete" or
            payload.get("correction_sha256") != correction_sha256):
        raise ValueError("passive predecessor did not pass sentinel controls")
    return payload


def run(*, data_root=localizer.DATA_ROOT, correction_json=None,
        reset_mode="passive", passive_manifest=None):
    """Gate and acquire a complete sentinel pass, retaining all raw records."""
    if reset_mode not in ("passive", "dump"):
        raise ValueError("reset must be passive or dump")
    root = Path(data_root)
    correction = localizer.checked_correction(root, correction_json)
    if reset_mode == "dump":
        _check_passive_predecessor(
            passive_manifest, correction_sha256=localizer.CORRECTION_SHA256)
    session_id = (f"q3_tls_millisecond_sentinel_{reset_mode}_" +
                  datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") +
                  "_" + uuid.uuid4().hex[:8])
    folder = root / "q3" / session_id
    folder.mkdir(parents=True, exist_ok=False)
    manifest_path = folder / "manifest.json"
    manifest = {"schema": "q3.tls-millisecond-sentinel.v1",
                "status": "scouting", "session_id": session_id,
                "reset_mode": reset_mode,
                "code_commit": os.environ.get("Q3_CODE_COMMIT", "unknown"),
                "correction_json": str(correction),
                "correction_sha256": localizer.CORRECTION_SHA256,
                "passive_predecessor": None if passive_manifest is None else
                str(passive_manifest), "plan": plan(reset_mode=reset_mode),
                "profiles": {}, "chunks": [], "references": {}}
    protocol.checkpoint(manifest_path, manifest)
    print(f"[ms-sentinel] manifest={manifest_path}", flush=True)
    try:
        pre_scout = localizer.run(
            data_root=root, correction_json=correction,
            parameter_overrides={**wide.parameters(),
                                 "output_suffix": "TLS_Millisecond_Sentinel_Scout_pre"})
        manifest["pre_scout_csv"] = str(pre_scout)
        scout_rows = swap.read_wide_scout(pre_scout)
        protocol.checkpoint(manifest_path, manifest)
        try:
            candidate_queue = ranked_scout_candidates(scout_rows)
            candidate_queue.sort(
                key=lambda item: (abs(item["center_ghz"]-PREFERRED_A_GHZ) <= .006,
                                  min(item["depth_scan_up"],
                                      item["depth_scan_down"])),
                reverse=True)
            selected = select_sites(scout_rows)
            null_sites = select_null_sites(scout_rows, selected)
        except ValueError as exc:
            manifest["status"] = "stopped_site_gate"
            manifest["gate_error"] = str(exc)
            protocol.checkpoint(manifest_path, manifest)
            return manifest_path
        manifest["selected"] = selected
        manifest["scout_candidate_queue"] = candidate_queue[:6]
        manifest["null_sites_ghz"] = null_sites
        protocol.checkpoint(manifest_path, manifest)
        print(f"[ms-sentinel] A={selected['A']['center_ghz']:.3f} "
              f"B={selected['B']['center_ghz']:.3f} "
              f"C={selected['C']['center_ghz']:.3f} GHz", flush=True)

        with localizer.scan_environment(correction):
            from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
                TLSSpectroscopy as tls,
            )
            from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import (
                _run_program, runtime_bundle,
            )

            tls.QUBIT, tls.SET_YOKO, tls.outerFolder = "q3", False, str(root)
            base = _base_config(tls, correction, data_root=root,
                                reset_mode=reset_mode)
            inverse = _inverse_gain(tls)
            control_ghz = float(selected["C"]["center_ghz"])
            control = {"target_mhz": 1000*control_ghz,
                       "gain_dac": inverse(1000*control_ghz)}
            dump_gain = (inverse(1000*float(selected["A"]["center_ghz"]))
            if reset_mode == "dump" else None)
            soc, soccfg = tls.makeProxy()
            bundle = runtime_bundle(base)
            axis, reference = _acquire_reference(
                soc, soccfg, base, bundle, control_ghz, control["gain_dac"],
                phase="pre", folder=folder, manifest=manifest,
                manifest_path=manifest_path, run_program=_run_program)
            manifest["pre_readout_axis"] = axis
            manifest["pre_reference_score"] = reference
            protocol.checkpoint(manifest_path, manifest)
            if not axis["valid"] or not reference["transfer"]["usable"]:
                manifest["status"] = "stopped_reference_gate"
                protocol.checkpoint(manifest_path, manifest)
                return manifest_path

            accepted = []
            for index, candidate in enumerate(candidate_queue[:6]):
                profile_name = f"candidate_{index:02d}"
                _run_profile(
                    soc, soccfg, base, bundle, line_name=profile_name,
                    coarse_mhz=1000*float(candidate["center_ghz"]),
                    control=control, inverse_gain=inverse, axis=axis,
                    folder=folder, manifest=manifest, manifest_path=manifest_path,
                    run_program=_run_program, reset_mode=reset_mode,
                    dump_gain_dac=dump_gain,
                    transfer_levels=reference["transfer"])
                report = manifest["profiles"][f"{profile_name}_pre"]
                append_qualified_profile(
                    accepted, candidate, f"{profile_name}_pre", report)
                if len(accepted) == 2:
                    break
            if len(accepted) < 2:
                manifest["status"] = "stopped_profile_gate"
                manifest["gate_error"] = (
                    "fewer than two separated, normalized-contrast-qualified "
                    "profiles among the first six scout candidates")
                protocol.checkpoint(manifest_path, manifest)
                return manifest_path
            selected = {"A": accepted[0]["candidate"],
                        "B": accepted[1]["candidate"], "C": selected["C"]}
            fits = {"A": accepted[0]["fit"], "B": accepted[1]["fit"]}
            manifest["selected"] = selected
            manifest["pre_profile_keys"] = {"A": accepted[0]["profile_key"],
                                            "B": accepted[1]["profile_key"]}
            null_sites = select_null_sites(scout_rows, selected)
            manifest["null_sites_ghz"] = null_sites
            protocol.checkpoint(manifest_path, manifest)
            print(f"[ms-sentinel] qualified A={fits['A']['center_mhz']:.2f} "
                  f"B={fits['B']['center_mhz']:.2f} MHz after "
                  f"{len(manifest['profiles'])} pre-profiles", flush=True)
            if abs(fits["A"]["center_mhz"]-fits["B"]["center_mhz"]) < 20.0:
                manifest["status"] = "stopped_profile_gate"
                manifest["gate_error"] = "A/B fitted centers are less than 20 MHz apart"
                protocol.checkpoint(manifest_path, manifest)
                return manifest_path
            a_flanks = make_flanks(fits["A"])
            b_flanks = make_flanks(fits["B"])
            frequencies = {"A_minus": a_flanks["A_minus_mhz"],
                           "A_plus": a_flanks["A_plus_mhz"],
                           "B": b_flanks["A_minus_mhz"],
                           "C": control["target_mhz"]}
            targets = integer_dac_targets(frequencies, inverse)
            manifest["flank_targets"] = targets
            manifest["predicted_flank_slopes_per_mhz"] = {
                "A_minus": -a_flanks["slope_minus_per_mhz"],
                "A_plus": -a_flanks["slope_plus_per_mhz"],
                "B": -b_flanks["slope_minus_per_mhz"]}
            protocol.checkpoint(manifest_path, manifest)
            science = sentinel_conditions(targets)
            calibration = calibration_conditions(targets)
            null = null_conditions(null_sites, inverse_gain=inverse,
                                   control=targets["C"])
            # Compile every instruction family before committing minutes of data.
            for conditions in (science, calibration, null):
                _compile_program(soccfg, base, bundle, conditions, shots=2,
                                 reset_mode=reset_mode,
                                 dump_gain_dac=dump_gain)
            manifest["preflight_complete"] = True
            protocol.checkpoint(manifest_path, manifest)

            pilot, pilot_cfg = _compile_program(
                soccfg, base, bundle, science, shots=64,
                reset_mode=reset_mode, dump_gain_dac=dump_gain)
            pilot_result = acquire_chunk(
                soc, pilot, pilot_cfg, shots=64,
                path=folder / "pilot.npz",
                order=[arm["name"] for arm in science],
                run_program=_run_program, timeout_s=30.0)
            manifest["pilot"] = pilot_result
            period = int(pilot_result["median_shot_period_ns"])
            if (pilot_result["host_timing_valid_fraction"] < .9 or
                    not 500_000 <= period <= 20_000_000):
                manifest["status"] = "stopped_timing_gate"
                protocol.checkpoint(manifest_path, manifest)
                return manifest_path
            shots_per_chunk = max(200, min(2500, round(
                CHUNK_TARGET_S*1e9 / period)))
            manifest["planned_shots_per_chunk"] = shots_per_chunk
            manifest["timing_caveat"] = (
                "Progress callbacks observe completed shots with host polling latency; "
                "resident-stream bank handshakes are nonuniform and preserved in each NPZ. "
                "Subshot absolute times are not hardware timestamped.")
            protocol.checkpoint(manifest_path, manifest)
            science_program, science_cfg = _compile_program(
                soccfg, base, bundle, science, shots=shots_per_chunk,
                reset_mode=reset_mode, dump_gain_dac=dump_gain)
            cal_program, cal_cfg = _compile_program(
                soccfg, base, bundle, calibration, shots=CAL_SHOTS,
                reset_mode=reset_mode, dump_gain_dac=dump_gain)
            null_program, null_cfg = _compile_program(
                soccfg, base, bundle, null, shots=shots_per_chunk,
                reset_mode=reset_mode, dump_gain_dac=dump_gain)
            manifest["status"] = "acquiring"
            protocol.checkpoint(manifest_path, manifest)
            for index in range(SCIENCE_CHUNKS):
                entry = {"index": index, "kind": "science", "status": "acquiring"}
                manifest["chunks"].append(entry)
                protocol.checkpoint(manifest_path, manifest)
                entry.update(acquire_chunk(
                    soc, science_program, science_cfg, shots=shots_per_chunk,
                    path=folder / f"science_{index:02d}.npz",
                    order=[arm["name"] for arm in science],
                    run_program=_run_program, timeout_s=30.0))
                cal_path = folder / f"calibration_{index:02d}.npz"
                entry["calibration"] = acquire_chunk(
                    soc, cal_program, cal_cfg, shots=CAL_SHOTS, path=cal_path,
                    order=[arm["name"] for arm in calibration],
                    run_program=_run_program, timeout_s=30.0)
                entry["calibration_report"] = _calibration_report(cal_path, axis)
                entry["status"] = "complete"
                protocol.checkpoint(manifest_path, manifest)
                print(f"[ms-sentinel] science {index+1}/{SCIENCE_CHUNKS} "
                      f"cal={'ok' if entry['calibration_report']['valid'] else 'weak'}",
                      flush=True)
            for index in range(NULL_CHUNKS):
                entry = {"index": index, "kind": "null", "status": "acquiring"}
                manifest["chunks"].append(entry)
                protocol.checkpoint(manifest_path, manifest)
                entry.update(acquire_chunk(
                    soc, null_program, null_cfg, shots=shots_per_chunk,
                    path=folder / f"null_{index:02d}.npz",
                    order=[arm["name"] for arm in null],
                    run_program=_run_program, timeout_s=30.0))
                entry["status"] = "complete"
                protocol.checkpoint(manifest_path, manifest)
                print(f"[ms-sentinel] null {index+1}/{NULL_CHUNKS}", flush=True)

            _, reference_post = _acquire_reference(
                soc, soccfg, base, bundle, control_ghz, control["gain_dac"],
                phase="post", folder=folder, manifest=manifest,
                manifest_path=manifest_path, run_program=_run_program,
                axis=axis)
            manifest["post_reference_score"] = reference_post
            for name in ("A", "B"):
                _run_profile(
                    soc, soccfg, base, bundle, line_name=name,
                    coarse_mhz=1000*float(selected[name]["center_ghz"]),
                    control=control, inverse_gain=inverse, axis=axis,
                    folder=folder, manifest=manifest, manifest_path=manifest_path,
                    run_program=_run_program, reset_mode=reset_mode,
                    dump_gain_dac=dump_gain,
                    transfer_levels=(reference_post["transfer"]
                                     if reference_post["transfer"]["usable"]
                                     else reference["transfer"]), phase="post")
            post_scout = localizer.run(
                data_root=root, correction_json=correction,
                parameter_overrides={**wide.parameters(),
                                     "output_suffix": "TLS_Millisecond_Sentinel_Scout_post"})
            manifest["post_scout_csv"] = str(post_scout)
            post_profile_valid = all(
                manifest["profiles"][f"{name}_post"]["gate"]["passed"]
                for name in ("A", "B"))
            manifest["post_profile_valid"] = post_profile_valid
            manifest["pooled_dither"] = pooled_dither_gate(
                [chunk["calibration_report"] for chunk in manifest["chunks"]
                 if chunk["kind"] == "science"],
                shots_per_calibration=CAL_SHOTS)
            manifest["line_moved"] = (None if not post_profile_valid else any(
                abs(manifest["profiles"][f"{name}_post"]["fit"]["center_mhz"] -
                    fits[name]["center_mhz"]) > fits[name]["hwhm_mhz"]/2
                for name in ("A", "B")))
            controls_valid = bool(
                post_profile_valid and
                reference_post["axis"]["valid"] and
                reference_post["transfer"]["usable"] and
                manifest["pooled_dither"]["valid"])
            manifest["controls_valid"] = controls_valid
            manifest["status"] = ("complete" if controls_valid and not
                                  manifest["line_moved"] else
                                  "complete_line_moved" if controls_valid else
                                  "complete_controls_uncertain")
            protocol.checkpoint(manifest_path, manifest)
            print(f"[ms-sentinel] {manifest['status']}: {manifest_path}", flush=True)
            return manifest_path
    except BaseException as exc:
        manifest["status"] = "failed"
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        protocol.checkpoint(manifest_path, manifest)
        raise


def plan(*, reset_mode="passive"):
    if reset_mode not in ("passive", "dump"):
        raise ValueError("reset must be passive or dump")
    return {"hardware_access": False, "reset_mode": reset_mode,
            "scout_ghz": [3.8, 4.3], "site_selection": "qualified A and B >=20 MHz apart; quiet C",
            "profiles_per_line": PROFILE_CYCLES,
            "profile_shots_per_cycle": PROFILE_SHOTS_PER_CYCLE,
            "science_chunks": SCIENCE_CHUNKS, "null_chunks": NULL_CHUNKS,
            "target_chunk_seconds": CHUNK_TARGET_S, "conditions_per_shot": 8,
            "condition_order": list(SCIENCE_ORDER), "dwell_us": 25.0,
            "passive_recovery_us": 500.0, "dump_visit_us": 60.0,
            "calibration_dither_mhz": .5, "raw_iq_saved": True,
            "timestamp_method": "per-shot host progress callback; stream-bank gaps retained",
            "note": "Host timestamps are poll-limited; the science band is limited by measured cadence."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--reset", choices=("passive", "dump"), default="passive")
    parser.add_argument("--data-root", type=Path, default=localizer.DATA_ROOT)
    parser.add_argument("--correction-json", type=Path)
    parser.add_argument("--passive-manifest", type=Path,
                        help="required successful passive pass before --reset dump")
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(plan(reset_mode=args.reset), indent=2))
    else:
        run(data_root=args.data_root, correction_json=args.correction_json,
            reset_mode=args.reset, passive_manifest=args.passive_manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
