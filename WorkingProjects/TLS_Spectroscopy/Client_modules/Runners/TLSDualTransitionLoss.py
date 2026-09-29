"""Compare one fresh q3 loss line through g-e and e-f relaxation.

The e-f frequency is calibrated at park; its value at other flux biases is
an anharmonicity-based prediction, not an independent local spectroscopy.
All new-runner progress is written to the NAS manifest, not the terminal.
"""

import argparse
import csv
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import time
import uuid

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSPumpProbeAdaptiveParkPump as adaptive,
    TLSPumpProbeLocalizer as localizer,
    TLSPumpProbeResidentDrive as resident,
    TLSPumpProbeWidePassiveScan as wide,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.programs import (
    OPXResetT1Program, _pulse_pi_and_align,
)


SHOTS = 300
REFERENCE_SHOTS = 300
SHORT_US = 0.25
LONG_US = 10.0
OFFSETS_MHZ = (0, 2, -2, 4, -4, 6, -6, 8, -8)
EF_SPEC_GAIN = 7000
EF_SPEC_OFFSETS_MHZ = tuple(range(-30, 31, 2))
EF_GAINS = tuple(range(2500, 17501, 1250))


def checkpoint(path, payload):
    """Checkpoint silently, including during transient Windows/NAS rename locks."""
    path = Path(path)
    pending = path.with_suffix(".pending")
    pending.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    for delay in (.05, .1, .2, .4, .8, 1., 1., None):
        try:
            os.replace(pending, path)
            return
        except PermissionError:
            if delay is None:
                raise
            time.sleep(delay)


def read_scout(path):
    with Path(path).open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 251 or len({row["wall_clock_run_index"] for row in rows}) != 1:
        raise ValueError("a complete single-pass wide scout is required")
    return rows


def recent_ef_calibration(data_root, *, max_age_minutes=120):
    """Find a recent passed park calibration, even if its science run stopped."""
    now = datetime.now(timezone.utc)
    folders = sorted((Path(data_root) / "q3").glob(
        "q3_tls_dual_transition_loss_*/manifest.json"), reverse=True)
    for path in folders:
        try:
            stamp = path.parent.name.rsplit("_", 2)[-2]
            started = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(
                tzinfo=timezone.utc)
            age_minutes = (now - started).total_seconds() / 60.0
            if not 0 <= age_minutes <= max_age_minutes:
                continue
            document = json.loads(path.read_text(encoding="utf-8"))
            calibration = document.get("calibration", {})
            if (document.get("schema") not in (
                    "q3.tls-dual-transition-loss.v1",
                    "q3.tls-dual-transition-shelved.v1")
                    or document.get("correction_sha256") != localizer.CORRECTION_SHA256
                    or calibration.get("status") != "passed"):
                continue
            frequency = float(calibration["ef_frequency_mhz"])
            gain = int(calibration["ef_pi_gain"])
            park_ge = float(calibration["park_ge_mhz"])
            if (not 4000 < frequency < 4300 or not 1000 <= gain <= 16000
                    or not -250 < frequency - park_ge < -100):
                continue
            return {"ef_frequency_mhz": frequency, "ef_pi_gain": gain,
                    "park_ge_mhz": park_ge, "source_manifest": str(path),
                    "age_minutes": age_minutes}
        except (ValueError, TypeError, KeyError, OSError, json.JSONDecodeError):
            continue
    raise FileNotFoundError("no passed e-f calibration from the last 120 minutes")


def select_eligible_feature(rows, *, anharmonicity_mhz):
    """Require loss at g-e and a quiet g-e window at the shifted e-f bias."""
    indexed = {round(float(row["target_frequency_ghz"]), 3): row for row in rows}
    candidates = []
    for center in sorted(indexed):
        ef_bias = center - anharmonicity_mhz / 1000.0
        if not 3.82 <= center <= 4.155 or ef_bias > 4.345:
            continue
        # A separate g-e loss line at the e-f matching bias can turn an
        # f→e→g cascade into an apparent f-loss peak. Demand a quiet 10-us
        # and 25-us g-e background across the entire science window.
        shifted = []
        for offset in OFFSETS_MHZ:
            requested = ef_bias + offset / 1000.0
            nearest = round(3.8 + .002 * round((requested - 3.8) / .002), 3)
            if abs(nearest - requested) > .00101 or nearest not in indexed:
                break
            shifted.append(indexed[nearest])
        if len(shifted) != len(OFFSETS_MHZ):
            continue
        quiet_25 = [adaptive._survival(row) for row in shifted]
        quiet_10 = []
        for row in shifted:
            try:
                p0, p1, ps = (float(row[key]) for key in
                              ("P0", "P1", "Ps_10us"))
                value = (ps - p0) / (p1 - p0) if p1 - p0 >= .15 else math.nan
            except (KeyError, TypeError, ValueError, ZeroDivisionError):
                value = math.nan
            quiet_10.append(value)
        if (not all(math.isfinite(value) for value in quiet_10 + quiet_25)
                or min(quiet_10) < .65 or min(quiet_25) < .60):
            continue
        groups = {
            "center": [round(center + .002 * k, 3) for k in (-1, 0, 1)],
            "left": [round(center - .002 * k, 3) for k in (5, 6, 7)],
            "right": [round(center + .002 * k, 3) for k in (5, 6, 7)],
        }
        if any(f not in indexed for frequencies in groups.values()
               for f in frequencies):
            continue
        depths = {}
        for direction in ("", "up", "down"):
            values = {name: [adaptive._survival(indexed[f], direction)
                             for f in frequencies]
                      for name, frequencies in groups.items()}
            if any(not math.isfinite(value)
                   for block in values.values() for value in block):
                break
            trough = float(np.mean(values["center"]))
            depths[direction or "combined"] = min(
                float(np.median(values["left"])) - trough,
                float(np.median(values["right"])) - trough)
        if (len(depths) == 3 and depths["combined"] >= .14
                and min(depths["up"], depths["down"]) >= .07):
            candidates.append({"center_ghz": center,
                               "ef_bias_ghz": round(ef_bias, 6),
                               "shifted_bias_min_10us_survival": min(quiet_10),
                               "shifted_bias_min_25us_survival": min(quiet_25),
                               "depths": depths})
    if not candidates:
        raise ValueError("no bidirectional loss line with a quiet shifted e-f bias")
    return max(candidates, key=lambda row: (
        min(row["depths"]["up"], row["depths"]["down"]),
        row["depths"]["combined"]))


def science_schedule(center_ghz, anharmonicity_mhz):
    schedule = []
    for repeat in (0, 1):
        offsets = OFFSETS_MHZ if repeat == 0 else tuple(reversed(OFFSETS_MHZ))
        for offset in offsets:
            frequency = round(center_ghz + offset / 1000.0, 6)
            for transition in (("ge", "ef") if repeat == 0 else ("ef", "ge")):
                bias = (frequency if transition == "ge" else
                        frequency - anharmonicity_mhz / 1000.0)
                schedule.append({"pass": repeat, "offset_mhz": offset,
                                 "transition": transition,
                                 "transition_frequency_ghz": frequency,
                                 "bias_ge_ghz": round(bias, 6),
                                 "status": "pending"})
    return schedule


def shelved_schedule(center_ghz, anharmonicity_mhz):
    return [row for row in science_schedule(center_ghz, anharmonicity_mhz)
            if row["transition"] == "ef"]


def iq(records):
    return resident.record_iq(records)


def _standard_error(values):
    values = np.asarray(values, dtype=complex).ravel()
    return float(np.sqrt(np.var(values.real, ddof=1) +
                         np.var(values.imag, ddof=1)) / np.sqrt(values.size))


def validate_ef_audit(zero, pi, two_pi):
    zero, pi, two_pi = (np.asarray(block, dtype=complex).ravel()
                        for block in (zero, pi, two_pi))
    if min(len(zero), len(pi), len(two_pi)) < 50:
        raise ValueError("too few e-f audit shots")
    contrast = abs(np.mean(pi) - np.mean(zero))
    noise = 4.0 * math.hypot(_standard_error(zero), _standard_error(pi))
    if contrast <= noise:
        raise ValueError("e-f π pulse has unresolved IQ contrast")
    return_error = abs(np.mean(two_pi) - np.mean(zero))
    allowance = .35 * contrast + 4.0 * math.hypot(
        _standard_error(zero), _standard_error(two_pi))
    if return_error > allowance:
        raise ValueError("e-f 2π return failed")
    return {"contrast": float(contrast), "return_error": float(return_error),
            "return_allowance": float(allowance)}


def validate_site_references(ground, excited, second=None):
    blocks = [np.asarray(x, dtype=complex).ravel() for x in
              ((ground, excited) if second is None else (ground, excited, second))]
    if min(len(x) for x in blocks) < 50:
        raise ValueError("too few site reference shots")
    # Fit on the first half and score on held-out IQ; no optimistically
    # in-sample discriminator gate at a newly selected flux point.
    centers = np.asarray([np.mean(x[:len(x) // 2]) for x in blocks])
    correct = []
    for index, block in enumerate(blocks):
        held = block[len(block) // 2:]
        predictions = np.argmin(abs(held[:, None] - centers[None, :]), axis=1)
        correct.append(float(np.mean(predictions == index)))
    ge = .5 * (correct[0] + correct[1])
    def contrast_snr(first, second):
        delta = np.mean(second) - np.mean(first)
        if not np.isfinite(delta) or abs(delta) < 1e-9:
            return 0., [0., 0.]
        axis = np.conj(delta / abs(delta))
        def block_snr(a, b):
            x, y = np.real(a * axis), np.real(b * axis)
            error = math.sqrt(np.var(x, ddof=1) / len(x) +
                              np.var(y, ddof=1) / len(y))
            return float((np.mean(y) - np.mean(x)) / max(error, 1e-12))
        overall = block_snr(first, second)
        halfway = min(len(first), len(second)) // 2
        halves = [block_snr(first[:halfway], second[:halfway]),
                  block_snr(first[-halfway:], second[-halfway:])]
        return overall, halves

    ge_snr, ge_halves = contrast_snr(blocks[0], blocks[1])
    if ge_snr < 5 or min(ge_halves) < 3:
        raise ValueError("g/e ensemble readout at target bias is unresolved")
    report = {"valid": True, "ge_fidelity": ge,
              "ge_mean_contrast_snr": ge_snr,
              "ge_half_snrs": ge_halves,
              "correct_by_state": correct,
              "centroids": [[float(c.real), float(c.imag)] for c in centers]}
    if second is not None:
        f = correct[2]
        report["f_vs_e_fidelity"] = .5 * (correct[1] + f)
        ef_snr, ef_halves = contrast_snr(blocks[1], blocks[2])
        report["ef_mean_contrast_snr"] = ef_snr
        report["ef_half_snrs"] = ef_halves
        if ef_snr < 5 or min(ef_halves) < 3:
            raise ValueError("f readout at target bias is unresolved")
    return report


def target_fraction(values, reference_report, state):
    """Fraction assigned to the prepared state using local held-out centroids."""
    labels = {"g": 0, "e": 1, "f": 2}
    centers = np.asarray([complex(*pair)
                          for pair in reference_report["centroids"]])
    sample = np.asarray(values, dtype=complex).ravel()
    predicted = np.argmin(abs(sample[:, None] - centers[None, :]), axis=1)
    return float(np.mean(predicted == labels[state]))


def differential_loss(short_target, long_target, short_ground, long_ground):
    """Target-state disappearance after subtracting matched ground drift."""
    values = [float(v) for v in (short_target, long_target,
                                 short_ground, long_ground)]
    if any(not math.isfinite(v) or not 0 <= v <= 1 for v in values):
        raise ValueError("differential loss needs four valid fractions")
    return values[0] - values[1] - values[2] + values[3]


def projected_differential_loss(short_ground, short_target, long_ground,
                                long_target, *, baseline_iq):
    """Use a resolved ensemble IQ axis without demanding shot classification."""
    sg, st, lg, lt, baseline = [np.asarray(values, dtype=complex).ravel()
                                for values in (short_ground, short_target,
                                               long_ground, long_target,
                                               baseline_iq)]
    axis_delta = np.mean(st) - np.mean(baseline)
    if not np.isfinite(axis_delta) or abs(axis_delta) < 1e-9:
        raise ValueError("local IQ contrast is zero")
    axis = np.conj(axis_delta) / abs(axis_delta) ** 2
    projected = [np.real(values * axis) for values in (sg, st, lg, lt)]
    value = (np.mean(projected[1]) - np.mean(projected[3]) -
             np.mean(projected[0]) + np.mean(projected[2]))
    variance = sum(np.var(values, ddof=1) / len(values)
                   for values in projected)
    return {"value": float(value), "se_conditional": float(math.sqrt(variance)),
            "reference_contrast_iq": float(abs(axis_delta))}


def _shelved_vector(blocks):
    """Two complex mean IQ values as a four-real-coordinate response."""
    means = [np.mean(np.asarray(blocks[name], dtype=complex))
             for name in ("identity", "shelved")]
    return np.asarray([part for value in means
                       for part in (value.real, value.imag)], dtype=float)


def _shelved_matrix(references):
    columns = [_shelved_vector({name: references[name][state]
                                for name in ("identity", "shelved")})
               for state in ("g", "e", "f")]
    return np.column_stack((columns[1] - columns[0],
                            columns[2] - columns[0])), columns


def validate_shelved_references(references):
    """Require two independent ensemble IQ response directions."""
    for name in ("identity", "shelved"):
        for state in ("g", "e", "f"):
            sample = np.asarray(references[name][state], dtype=complex).ravel()
            if len(sample) < 100 or not np.all(np.isfinite(sample)):
                raise ValueError("shelved response has incomplete references")
    matrix, columns = _shelved_matrix(references)
    condition = float(np.linalg.cond(matrix))
    snrs = {}
    for a, b in (("g", "e"), ("g", "f"), ("e", "f")):
        ia, ib = ("g", "e", "f").index(a), ("g", "e", "f").index(b)
        error = math.sqrt(sum(_standard_error(references[name][state]) ** 2
                              for name in ("identity", "shelved")
                              for state in (a, b)))
        snrs[a + b] = float(np.linalg.norm(columns[ib] - columns[ia]) /
                            max(error, 1e-12))
    if (not math.isfinite(condition) or condition > 8.0
            or min(snrs.values()) < 5.0):
        raise ValueError("shelved response is rank-deficient or unresolved")
    return {"valid": True, "condition": condition, "pair_snrs": snrs,
            "centroids": {state: columns[index].tolist()
                          for index, state in enumerate(("g", "e", "f"))}}


def shelved_population(references, observed, *, ground_shift=None):
    """Infer g/e/f populations from direct and permutation-mapped mean IQ."""
    matrix, columns = _shelved_matrix(references)
    target = _shelved_vector(observed)
    if ground_shift is not None:
        target -= (_shelved_vector(ground_shift) -
                   _shelved_vector({name: references[name]["g"]
                                    for name in ("identity", "shelved")}))
    fit, *_ = np.linalg.lstsq(matrix, target - columns[0], rcond=None)
    p_e, p_f = map(float, fit)
    residual = float(np.linalg.norm(matrix @ fit - (target - columns[0])))
    return {"g": float(1 - p_e - p_f), "e": p_e, "f": p_f,
            "condition": float(np.linalg.cond(matrix)),
            "residual_iq": residual}


def summarize_science(points):
    """Keep each arm visible while giving a conservative peak-location comparison."""
    by_transition = {}
    for transition in ("ge", "ef"):
        rows = []
        for offset in OFFSETS_MHZ:
            matched = [point for point in points
                       if point["transition"] == transition
                       and point["offset_mhz"] == offset
                       and point["status"] == "complete"]
            rows.append({"offset_mhz": offset,
                         "completed_passes": len(matched),
                         "mean_differential_loss": (float(np.mean(
                             [point["differential_loss"] for point in matched]))
                             if matched else None),
                         "pass_values": [float(point["differential_loss"])
                                         for point in matched]})
        by_transition[transition] = rows
    peak = {transition: max((row for row in rows if row["completed_passes"]),
                            key=lambda row: row["mean_differential_loss"])
            for transition, rows in by_transition.items()}
    return {"profiles": by_transition,
            "unresolved_points": sum(point["status"] != "complete"
                                     for point in points),
            "peak_offset_mhz": {key: value["offset_mhz"]
                                for key, value in peak.items()},
            "peak_separation_mhz": abs(peak["ge"]["offset_mhz"] -
                                       peak["ef"]["offset_mhz"]),
            "note": "Peak positions use park-calibrated anharmonicity; "
                    "positive identity requires independent local e-f calibration."}


def summarize_shelved_science(points):
    profile = []
    for offset in OFFSETS_MHZ:
        rows = [point for point in points
                if point["offset_mhz"] == offset and point["status"] == "complete"]
        profile.append({
            "offset_mhz": offset, "passes": len(rows),
            "f_loss_mean": (float(np.mean([row["f_loss"] for row in rows]))
                            if rows else None),
            "f_loss_passes": [float(row["f_loss"]) for row in rows],
            "e_control_f_mean": (float(np.mean([row["e_control_f"] for row in rows]))
                                 if rows else None),
        })
    return {"profile": profile,
            "unresolved_points": sum(point["status"] != "complete"
                                     for point in points),
            "note": "Two-map f population is preparation-relative; the matching "
                    "e-f frequency still uses park-calibrated anharmonicity."}


class DualTransitionProgram(OPXResetT1Program):
    """Passive park preparation and prompt readout during corrected return."""

    record_words = 2
    decode_dmem_records = staticmethod(resident.decode_single_iq)

    def __init__(self, soccfg, cfg, payload_calibration, loop_calibration):
        if cfg.get("opx_reset_scheme") != "none":
            raise ValueError("dual transition requires passive reset")
        if not cfg.get("opx_hard_flux_steps") or not cfg.get("opx_persistent_park"):
            raise ValueError("dual transition requires persistent hard-step park")
        if cfg["dual_state"] not in ("g", "e", "f"):
            raise ValueError("unknown qutrit preparation")
        if cfg["dual_mode"] not in ("park", "science"):
            raise ValueError("unknown dual-transition mode")
        if cfg.get("dual_readout_map", "identity") not in ("identity", "shelved"):
            raise ValueError("unknown dual-transition readout map")
        if cfg["dual_mode"] == "science" and not cfg.get(
                "flux_predistortion_overlap_payload_readout"):
            raise ValueError("science readout must overlap the corrected return")
        if cfg["dual_mode"] == "science" and cfg.get(
                "opx_feedback_pre_measure_sync"):
            raise ValueError("pre-measure sync would wait out the return tail")
        super().__init__(soccfg, cfg, payload_calibration, loop_calibration)

    def _declare_experiment(self):
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import (
            add_qubit_gaussian,
        )
        super()._declare_experiment()
        add_qubit_gaussian(self, name="qubit_ef", drag_beta=0.0)

    def _set_ef_pulse(self, *, gain):
        cfg = self.cfg
        self.set_pulse_registers(
            ch=cfg["qubit_ch"], style="arb",
            freq=self.freq2reg(float(cfg["dual_ef_freq_mhz"]),
                               gen_ch=cfg["qubit_ch"]),
            phase=self.deg2reg(0, gen_ch=cfg["qubit_ch"]),
            gain=int(gain), waveform="qubit_ef")

    def _ef_pulse(self):
        self._set_ef_pulse(gain=(self.cfg["dual_ef_gain"]
                                 if self.cfg["dual_state"] == "f" else 0))
        _pulse_pi_and_align(self)

    def _shelve_readout(self):
        # The compensated return tail is already scheduled on the flux DAC.
        # sync_all would advance the reference time past that 40-us tail and
        # erase f before readout. QICK's auto timestamps put the second pulse
        # after the first on the same qubit channel. One fixed synci after
        # both advances readout beyond their combined duration, not the tail.
        cfg = self.cfg
        mapping_us = 8.0 * float(cfg["sigma"]) + .04
        self._set_ef_pulse(gain=cfg["dual_ef_gain"])
        self.pulse(ch=cfg["qubit_ch"])
        self._set_payload_pulse()
        self.pulse(ch=cfg["qubit_ch"])
        self.synci(self.us2cycles(mapping_us))

    def _emit_body(self):
        cfg = self.cfg
        park_up, park_down = self._shot_park_callbacks()
        park_up()
        self._set_payload_pulse(gain=0 if cfg["dual_state"] == "g" else None)
        _pulse_pi_and_align(self)
        self._ef_pulse()
        if cfg["dual_mode"] == "science":
            self._wait_t1_payload(hold_us=float(cfg["dual_hold_us"]))
        if cfg.get("dual_readout_map", "identity") == "shelved":
            self._shelve_readout()
        self._measure_raw()
        for name in ("i", "q"):
            self.memw(self.reset_page, self.reset_regs[name],
                      self.reset_regs["address"])
            self.mathi(self.reset_page, self.reset_regs["address"],
                       self.reset_regs["address"], "+", 1)
        # The tail was launched asynchronously to preserve f; finish it
        # before the next shot and restore the persistent park.
        self.sync_all(0)
        park_down()
        self.sync_all(self.us2cycles(float(self.reset_config.inter_shot_delay_us)))


def arm_config(base, *, state, ef_freq_mhz, ef_gain, shots,
               mode="park", bias_ghz=None, dc_lookup=None, hold_us=SHORT_US,
               readout_map="identity"):
    cfg = dict(base)
    cfg.update({"dual_state": state, "dual_mode": mode,
                "dual_ef_freq_mhz": float(ef_freq_mhz),
                "dual_ef_gain": int(ef_gain),
                "dual_readout_map": readout_map,
                "dual_hold_us": float(hold_us), "shots": int(shots),
                "reps": int(shots), "ff_hold": float(hold_us)})
    if mode == "science":
        cfg["ff_gain"] = int(dc_lookup[float(bias_ghz)])
    else:
        cfg["ff_gain"] = int(base["ff_park_gain"])
    return cfg


def configure_prompt_readout(cfg):
    """Keep the readout inside the corrected return tail.

    The standard five-point scan intentionally syncs every channel before
    measuring. That sync would wait for this runner's 40-us flux tail and
    invalidate its prompt f-state measurement.
    """
    if not cfg.get("flux_predistortion_overlap_payload_readout"):
        raise ValueError("prompt readout requires overlapped return tail")
    cfg["opx_feedback_pre_measure_sync"] = False
    cfg["opx_feedback_flush_mode"] = "off"
    return cfg


def plan(*, shelved_confirm=False):
    return {"hardware_access": False, "reset": "passive",
            "calibration": "opposed e-f frequency scans, gain sweep, 0/pi/2pi audit",
            "scout": "one standard 3.8–4.3 GHz passive five-point scan",
            "science": ("two-map e-f population with long e/g controls"
                        if shelved_confirm else
                        "interleaved g-e and e-f loss at matched transition frequencies"),
            "offsets_mhz": list(OFFSETS_MHZ),
            "dwells_us": [SHORT_US, LONG_US],
            "readout": ("direct and e-f/g-e mapped IQ during corrected return tail"
                        if shelved_confirm else
                        "park during 40-us corrected return tail; local IQ references"),
            "terminal": "new runner has no progress prints; NAS manifest has progress"}


def run(*, data_root=localizer.DATA_ROOT, correction_json=None,
        reuse_recent_ef=False, shelved_confirm=False):
    data_root = Path(data_root)
    correction = localizer.checked_correction(data_root, correction_json)
    reused = None
    if reuse_recent_ef:
        try:
            reused = recent_ef_calibration(data_root)
        except FileNotFoundError:
            # An old calibration is not a reason to abort before science.
            # The ordinary opposed scans below supply a fresh replacement.
            pass
    session_id = ("q3_tls_dual_transition_loss_" +
                  datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") +
                  "_" + uuid.uuid4().hex[:8])
    folder = data_root / "q3" / session_id
    folder.mkdir(parents=True, exist_ok=False)
    path = folder / "manifest.json"
    manifest = {"schema": ("q3.tls-dual-transition-shelved.v1"
                           if shelved_confirm else
                           "q3.tls-dual-transition-loss.v1"),
                "session_id": session_id, "status": "calibrating",
                "code_commit": os.environ.get("Q3_CODE_COMMIT", "unknown"),
                "correction_json": str(correction),
                "correction_sha256": localizer.CORRECTION_SHA256,
                "plan": plan(shelved_confirm=shelved_confirm),
                "calibration": {}, "points": []}
    checkpoint(path, manifest)
    try:
        with localizer.scan_environment(correction):
            manifest["code_commit"] = os.environ["Q3_CODE_COMMIT"]
            checkpoint(path, manifest)
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

            tls.QUBIT, tls.SET_YOKO, tls.outerFolder = "q3", False, str(data_root)
            if int(tls.BaseConfig["ff_park_gain"]) != -25146:
                raise RuntimeError("q3 park configuration changed")
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
                         "flux_predistortion_overlap_payload_readout": True,
                         "flux_predistortion_round_trip_mode": "stateful",
                         "readout_thermalization_us": 10.,
                         "qubit_pulse_style": "arb", "do_ff": True,
                         "opx_reset_scheme": "none",
                         "opx_resident_dmem_stream": True,
                         "opx_inter_shot_delay_us": 500.0})
            configure_prompt_readout(base)
            soc, soccfg = tls.makeProxy()
            bundle = runtime_bundle(base)

            def acquire(name, *, state, freq, gain, mode="park", bias=None,
                        lookup=None, hold=SHORT_US, shots=SHOTS,
                        readout_map="identity"):
                cfg = arm_config(base, state=state, ef_freq_mhz=freq,
                                 ef_gain=gain, shots=shots, mode=mode,
                                 bias_ghz=bias, dc_lookup=lookup, hold_us=hold,
                                 readout_map=readout_map)
                program = DualTransitionProgram(
                    soccfg, cfg, bundle.payload, bundle.loop)
                records = _run_program(
                    soc, program, max(30., _block_timeout_s(cfg, shots)),
                    cfg, total_shots=shots)
                if len(records) != shots:
                    raise RuntimeError(f"{name}: incomplete IQ")
                raw_path = folder / f"{name}.npz"
                np.savez_compressed(raw_path, i=[r.i for r in records],
                                    q=[r.q for r in records])
                return iq(records), str(raw_path)

            park_ge = float(base["qubit_pi_freq"])
            ef_prior = park_ge + float(base["qubit_anharmonicity_mhz"])
            if reused is not None and abs(reused["park_ge_mhz"] - park_ge) > .1:
                raise RuntimeError("park frequency changed since e-f calibration")
            reference_e, ref_path = acquire(
                "park_e_reference", state="e", freq=ef_prior,
                gain=0, shots=REFERENCE_SHOTS)
            manifest["calibration"]["park_e_reference_npz"] = ref_path
            checkpoint(path, manifest)
            if reused is not None:
                ef_frequency = reused["ef_frequency_mhz"]
                ef_gain = reused["ef_pi_gain"]
                manifest["calibration"]["reused_from"] = reused
                checkpoint(path, manifest)
            else:
                # Opposed scans distinguish an e-f line from monotonic drift.
                spectra = []
                for repeat, offsets in enumerate((
                        EF_SPEC_OFFSETS_MHZ,
                        tuple(reversed(EF_SPEC_OFFSETS_MHZ)))):
                    response = []
                    for offset in offsets:
                        frequency = ef_prior + offset
                        name = f"ef_spec_r{repeat}_{offset:+d}".replace(
                            "+", "p").replace("-", "m")
                        values, raw = acquire(name, state="f", freq=frequency,
                                              gain=EF_SPEC_GAIN, shots=SHOTS)
                        response.append({"frequency_mhz": frequency,
                                         "mean_i": float(np.mean(values.real)),
                                         "mean_q": float(np.mean(values.imag)),
                                         "se": _standard_error(values),
                                         "raw_npz": raw})
                        manifest["calibration"]["spectra"] = spectra + [response]
                        checkpoint(path, manifest)
                    spectra.append(response)
                def strongest(spectrum):
                    return max(spectrum, key=lambda row:
                               abs(complex(row["mean_i"], row["mean_q"]) -
                                   np.mean(reference_e)))
                peaks = [strongest(spectrum) for spectrum in spectra]
                if abs(peaks[0]["frequency_mhz"] - peaks[1]["frequency_mhz"]) > 2.01:
                    raise RuntimeError("e-f line did not reproduce in opposed scans")
                for spectrum, peak in zip(spectra, peaks):
                    baseline = .5 * (
                        complex(spectrum[0]["mean_i"], spectrum[0]["mean_q"]) +
                        complex(spectrum[-1]["mean_i"], spectrum[-1]["mean_q"]))
                    peak_mean = complex(peak["mean_i"], peak["mean_q"])
                    if abs(peak_mean - baseline) < max(
                            4 * float(peak["se"]),
                            .20 * abs(peak_mean - np.mean(reference_e))):
                        raise RuntimeError("e-f spectroscopy lacks a resolved peak")
                ef_frequency = .5 * (peaks[0]["frequency_mhz"] +
                                     peaks[1]["frequency_mhz"])
                if not ef_prior - 25 <= ef_frequency <= ef_prior + 25:
                    raise RuntimeError("e-f line at scan boundary")
                gains = []
                for gain in EF_GAINS:
                    values, raw = acquire(f"ef_gain_{gain}", state="f",
                                          freq=ef_frequency, gain=gain)
                    gains.append({"gain": gain,
                                  "mean_i": float(np.mean(values.real)),
                                  "mean_q": float(np.mean(values.imag)),
                                  "raw_npz": raw})
                    manifest["calibration"]["gain_scan"] = gains
                    checkpoint(path, manifest)
                best = max(gains, key=lambda row:
                           abs(complex(row["mean_i"], row["mean_q"]) -
                               np.mean(reference_e)))
                ef_gain = int(best["gain"])
                if (ef_gain in (EF_GAINS[0], EF_GAINS[-1])
                        or 2 * ef_gain > 32767):
                    raise RuntimeError("e-f pi gain is unresolved or 2pi exceeds DAC range")
            pi, pi_path = acquire("ef_audit_pi", state="f", freq=ef_frequency,
                                  gain=ef_gain, shots=REFERENCE_SHOTS)
            twice, twice_path = acquire("ef_audit_2pi", state="f",
                                        freq=ef_frequency, gain=2 * ef_gain,
                                        shots=REFERENCE_SHOTS)
            audit = validate_ef_audit(reference_e, pi, twice)
            alpha = ef_frequency - park_ge
            if not -250 < alpha < -100:
                raise RuntimeError("calibrated e-f frequency is not transmon-like")
            manifest["calibration"].update({
                "status": "passed", "park_ge_mhz": park_ge,
                "ef_frequency_mhz": ef_frequency, "anharmonicity_mhz": alpha,
                "ef_pi_gain": ef_gain, "audit": audit,
                "audit_pi_npz": pi_path, "audit_2pi_npz": twice_path})
            checkpoint(path, manifest)

            manifest["status"] = "scouting"
            checkpoint(path, manifest)
            scout = localizer.run(
                data_root=data_root, correction_json=correction,
                parameter_overrides={**wide.parameters(),
                                     "output_suffix": "TLS_Dual_Transition_Scout"},
                announce=False)
            manifest["scout_csv"] = str(scout)
            selected = select_eligible_feature(read_scout(scout),
                                               anharmonicity_mhz=alpha)
            manifest["selected"] = selected
            schedule = (shelved_schedule if shelved_confirm else
                        science_schedule)(selected["center_ghz"], alpha)
            all_biases = np.asarray(sorted({row["bias_ge_ghz"] for row in schedule}))
            dc, realized = _integer_dc_grid(
                {**wide.parameters(), "dc_min": -25000}, all_biases, tls)
            lookup = {float(f): int(g) for f, g in zip(all_biases, dc)}
            manifest["bias_grid"] = [{"ge_ghz": float(f), "dc": int(g),
                                      "realized_ge_ghz": float(r)}
                                     for f, g, r in zip(all_biases, dc, realized)]
            manifest["points"] = schedule
            manifest["status"] = "acquiring"
            checkpoint(path, manifest)
            for index, point in enumerate(schedule):
                bias = point["bias_ge_ghz"]
                transition = point["transition"]
                prefix = f"point_{index:03d}_{transition}"
                point["status"] = "acquiring"
                checkpoint(path, manifest)
                if shelved_confirm:
                    blocks = {hold: {mapping: {} for mapping in
                                     ("identity", "shelved")}
                              for hold in ("short", "long")}
                    state_order = (("g", "e", "f") if point["pass"] == 0
                                   else ("f", "e", "g"))
                    map_order = (("identity", "shelved") if point["pass"] == 0
                                 else ("shelved", "identity"))
                    for hold_name, hold_us in (("short", SHORT_US),
                                               ("long", LONG_US)):
                        for state in state_order:
                            for mapping in map_order:
                                name = f"{prefix}_{hold_name}_{state}_{mapping}"
                                values, raw = acquire(
                                    name, state=state, freq=ef_frequency,
                                    gain=ef_gain, mode="science", bias=bias,
                                    lookup=lookup, hold=hold_us,
                                    readout_map=mapping)
                                blocks[hold_name][mapping][state] = values
                                point.setdefault("raw_npz", {})[name] = raw
                                checkpoint(path, manifest)
                    try:
                        point["reference_gate"] = validate_shelved_references(
                            blocks["short"])
                    except ValueError as exc:
                        point["status"] = "unresolved_reference"
                        point["reference_error"] = str(exc)
                        checkpoint(path, manifest)
                        continue
                    long_ground = {mapping: blocks["long"][mapping]["g"]
                                   for mapping in ("identity", "shelved")}
                    def long_population(state):
                        return shelved_population(
                            blocks["short"],
                            {mapping: blocks["long"][mapping][state]
                             for mapping in ("identity", "shelved")},
                            ground_shift=long_ground)
                    point["long_f_population"] = long_population("f")
                    point["long_e_population"] = long_population("e")
                    point["f_loss"] = 1.0 - point["long_f_population"]["f"]
                    point["e_control_f"] = point["long_e_population"]["f"]
                    point["status"] = "complete"
                    checkpoint(path, manifest)
                    continue
                refs = {}
                ref_states = ("g", "e") if transition == "ge" else ("g", "e", "f")
                for state in ref_states:
                    values, raw = acquire(
                        f"{prefix}_short_{state}", state=state,
                        freq=ef_frequency, gain=ef_gain, mode="science",
                        bias=bias, lookup=lookup, hold=SHORT_US)
                    refs[state] = values
                    point[f"short_{state}_npz"] = raw
                    checkpoint(path, manifest)
                try:
                    point["reference_gate"] = validate_site_references(
                        refs["g"], refs["e"], refs.get("f"))
                except ValueError:
                    # One extra independent reference block can distinguish
                    # a noisy half-block from a genuinely unresolved state.
                    for state in ref_states:
                        retry, raw = acquire(
                            f"{prefix}_short_{state}_retry", state=state,
                            freq=ef_frequency, gain=ef_gain, mode="science",
                            bias=bias, lookup=lookup, hold=SHORT_US)
                        refs[state] = np.concatenate((refs[state], retry))
                        point[f"short_{state}_retry_npz"] = raw
                        checkpoint(path, manifest)
                    try:
                        point["reference_gate"] = validate_site_references(
                            refs["g"], refs["e"], refs.get("f"))
                    except ValueError as exc:
                        point["status"] = "unresolved_reference"
                        point["reference_error"] = str(exc)
                        checkpoint(path, manifest)
                        continue
                state = "e" if transition == "ge" else "f"
                ground_long, ground_raw = acquire(
                    f"{prefix}_long_g", state="g",
                    freq=ef_frequency, gain=ef_gain, mode="science",
                    bias=bias, lookup=lookup, hold=LONG_US)
                point["long_g_npz"] = ground_raw
                values, raw = acquire(
                    f"{prefix}_long_{state}", state=state,
                    freq=ef_frequency, gain=ef_gain, mode="science",
                    bias=bias, lookup=lookup, hold=LONG_US)
                point["long_npz"] = raw
                point["short_target_mean_iq"] = [float(np.mean(refs[state].real)),
                                                   float(np.mean(refs[state].imag))]
                point["long_target_mean_iq"] = [float(np.mean(values.real)),
                                                  float(np.mean(values.imag))]
                point["mean_iq_loss"] = projected_differential_loss(
                    refs["g"], refs[state], ground_long, values,
                    baseline_iq=refs["g" if transition == "ge" else "e"])
                point["differential_loss"] = point["mean_iq_loss"]["value"]
                point["status"] = "complete"
                checkpoint(path, manifest)
            manifest["summary"] = (summarize_shelved_science(schedule)
                                   if shelved_confirm else
                                   summarize_science(schedule))
            manifest["status"] = ("complete_with_unresolved" if
                                  manifest["summary"]["unresolved_points"] else
                                  "complete")
            checkpoint(path, manifest)
            return path
    except BaseException as exc:
        manifest["status"] = "failed"
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        checkpoint(path, manifest)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--data-root", type=Path, default=localizer.DATA_ROOT)
    parser.add_argument("--correction-json", type=Path)
    parser.add_argument("--reuse-recent-ef", action="store_true",
                        help="reuse a recent passed e-f calibration, with a fresh 0/pi/2pi audit")
    parser.add_argument("--shelved-confirm", action="store_true",
                        help="measure f population with direct and mapped readout")
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(plan(shelved_confirm=args.shelved_confirm), indent=2))
    else:
        run(data_root=args.data_root, correction_json=args.correction_json,
            reuse_recent_ef=args.reuse_recent_ef,
            shelved_confirm=args.shelved_confirm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
