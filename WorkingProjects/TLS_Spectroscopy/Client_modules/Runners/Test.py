"""Measurement-first diagnostic for the q3 resident five-point acquisition.

This runs a small production-path measurement, retains the full condition/DC/
shot IQ tensors, and reports the populations before the long scan or sync layer
is involved.  Passive reset is the default so record generation and decoding
can be isolated from feedback reset.
"""

import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np


_directory = os.path.dirname(os.path.abspath(__file__))
while _directory != os.path.dirname(_directory):
    if os.path.isdir(os.path.join(_directory, "WorkingProjects")):
        if _directory not in sys.path:
            sys.path.insert(0, _directory)
        break
    _directory = os.path.dirname(_directory)
else:
    raise RuntimeError("Could not find the HouckLab_QICK repo root.")


from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.progress import (
    progress_counter,
)


def fresh_step3a_plan(environ=None):
    """Return the high-SNR, correction-free q3 calibration contract."""
    environ = os.environ if environ is None else environ
    delay_vector_us = np.concatenate([
        np.arange(0.5, 25.5, 0.5),
        np.arange(27.0, 61.0, 2.0),
        np.arange(65.0, 195.0, 10.0),
        np.asarray([197.0, 200.0]),
    ]).tolist()
    return {
        "shots": int(environ.get("Q3_FRESH_3A_SHOTS", "1000")),
        "spec_amp": int(environ.get("Q3_FRESH_3A_SPEC_AMP", "25000")),
        "frequency_window_mhz": [4000.0, 4100.0],
        "frequency_step_mhz": 0.5,
        "delay_vector_us": delay_vector_us,
        "apply_flux_tail_compensation": False,
        "compose_with_applied_flux_tail_compensation": False,
    }


def run_fresh_step3a(plan=None):
    """Run one absolute q3 step-response fit without an existing correction."""
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
        TLSSpectroscopy as tls,
    )

    plan = fresh_step3a_plan() if plan is None else dict(plan)
    low_mhz, high_mhz = plan["frequency_window_mhz"]
    tls.P3_STEP_RESPONSE.update({
        "shots": int(plan["shots"]),
        "spec_amp": int(plan["spec_amp"]),
        "freq_step": float(plan["frequency_step_mhz"]),
        "auto_center_frequency_window": True,
        "auto_freq_absolute_min_mhz": float(low_mhz),
        "auto_freq_absolute_max_mhz": float(high_mhz),
        "t_vec_us": list(plan["delay_vector_us"]),
        "correction_fit_start_us": None,
        "correction_time_origin_us": 0.0,
        "baseline_rearm_us": 40.0,
        "piecewise_desired_response": "unity",
        "piecewise_response_model": "rise_decay_bump",
        "trace_tracking_mode": "image_v26",
        "trace_polarity": "bright",
        "trace_shoulder": "auto",
        "trace_max_jump_mhz": 4.0,
        "trace_smoothing_window_points": 7,
        "trace_smoothing_polyorder": 2,
        "trace_use_smoothed_frequency": True,
        "fit_residual_composition": False,
        "live_plot": True,
    })
    print(
        "[fresh 3a] q3 absolute calibration: correction OFF, composition OFF; "
        f"{plan['shots']} shots, {len(plan['delay_vector_us'])} delays, "
        f"{low_mhz / 1000:.3f}--{high_mhz / 1000:.3f} GHz"
    )
    tls._set_yoko_if_requested()
    soc, soccfg = tls.makeProxy()
    return tls.run_step3a_step_response_fit(tls.outerFolder, soc, soccfg)


def select_diagnostic_slice(
    frequency_ghz,
    dc_values,
    *,
    center_ghz=4.05,
    points=11,
):
    frequency_ghz = np.asarray(frequency_ghz, dtype=float)
    dc_values = np.asarray(dc_values)
    points = int(points)
    if frequency_ghz.ndim != 1 or frequency_ghz.shape != dc_values.shape:
        raise ValueError("frequency and DC grids must be matching 1-D arrays")
    if points < 3 or points % 2 == 0 or points > frequency_ghz.size:
        raise ValueError("diagnostic points must be an odd integer within the grid")
    center = int(np.abs(frequency_ghz - float(center_ghz)).argmin())
    half = points // 2
    start = min(max(center - half, 0), frequency_ghz.size - points)
    indices = np.arange(start, start + points, dtype=int)
    return (
        frequency_ghz[indices].copy(),
        dc_values[indices].copy(),
        indices,
    )


def _median(values):
    values = np.asarray(values, dtype=float)
    finite = values[np.isfinite(values)]
    return float(np.median(finite)) if finite.size else float("nan")


def make_shot_progress(start_time):
    """Report resident-stream progress in completed shot sweeps."""
    return lambda done, total: progress_counter(
        done - 1,
        total,
        start_time=start_time,
        label="five-point diagnostic",
    )


def start_diagnostic_timers(
    *,
    monotonic_clock=time.monotonic,
    wall_clock=time.time,
):
    """Start elapsed and ETA timers in the clock domains they each require."""
    return float(monotonic_clock()), float(wall_clock())


def _json_default(value):
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _save_csv(path, columns):
    with open(path, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for row in zip(*columns.values()):
            writer.writerow(row)


def apply_diagnostic_read_delay(cfg, environ=None):
    """Apply the requested ADC-accumulator settling delay to a diagnostic run."""
    environ = os.environ if environ is None else environ
    read_delay_us = float(environ.get("Q3_DIAGNOSTIC_READ_DELAY_US", "2.0"))
    if not np.isfinite(read_delay_us) or read_delay_us < 0.0:
        raise ValueError(
            "Q3_DIAGNOSTIC_READ_DELAY_US must be finite and non-negative"
        )
    cfg["opx_read_delay_us"] = read_delay_us
    return read_delay_us


def apply_diagnostic_dmem_verification(cfg, environ=None):
    """Keep exhaustive per-word DMem checks opt-in for small transport tests."""
    environ = os.environ if environ is None else environ
    value = environ.get(
        "Q3_DIAGNOSTIC_VERIFY_DMEM_READS", "off"
    ).strip().lower()
    if value not in ("on", "off"):
        raise ValueError("Q3_DIAGNOSTIC_VERIFY_DMEM_READS must be on or off")
    enabled = value == "on"
    cfg["opx_verify_dmem_reads"] = enabled
    return enabled


def apply_diagnostic_feedback_timing(cfg, environ=None):
    """Select the accumulator handoff sequence for this isolated test."""
    environ = os.environ if environ is None else environ
    mode = environ.get(
        "Q3_DIAGNOSTIC_FEEDBACK_TIMING", "official_wait_all"
    ).strip().lower()
    if mode not in ("official_wait_all", "legacy_absolute_wait"):
        raise ValueError(
            "Q3_DIAGNOSTIC_FEEDBACK_TIMING must be official_wait_all or "
            "legacy_absolute_wait"
        )
    cfg["opx_feedback_read_timing"] = mode
    return mode


def apply_diagnostic_feedback_flush(cfg, environ=None):
    """Enable a second readout event solely to locate accumulator latency."""
    environ = os.environ if environ is None else environ
    value = environ.get("Q3_DIAGNOSTIC_FEEDBACK_FLUSH", "off").strip().lower()
    value = {"on": "readout"}.get(value, value)
    if value not in ("off", "readout", "adc_only"):
        raise ValueError(
            "Q3_DIAGNOSTIC_FEEDBACK_FLUSH must be off, readout, or adc_only"
        )
    cfg["opx_feedback_flush_mode"] = value
    return value


def apply_diagnostic_pre_measure_sync(cfg, environ=None):
    """Align all scheduled channels before the original payload readout."""
    environ = os.environ if environ is None else environ
    value = environ.get(
        "Q3_DIAGNOSTIC_PRE_MEASURE_SYNC", "off"
    ).strip().lower()
    if value not in ("on", "off"):
        raise ValueError("Q3_DIAGNOSTIC_PRE_MEASURE_SYNC must be on or off")
    enabled = value == "on"
    cfg["opx_feedback_pre_measure_sync"] = enabled
    return enabled


def verify_dmem_roundtrip(soc, *, dmem_words, scratch_words=8):
    """Cross-check server bulk DMA against direct tProc AXI access."""
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.acquisition import (
        _read_words,
        _single_read,
        _single_write,
        _write_words,
    )

    dmem_words = int(dmem_words)
    scratch_words = int(scratch_words)
    if scratch_words < 2 or dmem_words <= scratch_words:
        raise ValueError("DMem scratch region must fit at the end of data memory")
    address = dmem_words - scratch_words
    tproc = soc.tproc

    def direct_read():
        return np.asarray(
            [_single_read(tproc, address + offset) for offset in range(scratch_words)],
            dtype=np.uint32,
        )

    def bulk_read():
        return np.asarray(
            _read_words(soc, address, scratch_words, tproc=tproc),
            dtype=np.uint32,
        )

    original = direct_read()
    pattern_a = np.asarray(
        [
            (0x13579BDF + 0x1020304 * index) & 0xFFFFFFFF
            for index in range(scratch_words)
        ],
        dtype=np.uint32,
    )
    pattern_b = np.bitwise_xor(pattern_a, np.uint32(0xA5A5A5A5))
    report = {"address": address, "words": scratch_words}
    try:
        _write_words(soc, address, pattern_a, tproc=tproc)
        report["bulk_write_bulk_read_matches"] = bool(
            np.array_equal(bulk_read(), pattern_a)
        )
        report["bulk_write_direct_read_matches"] = bool(
            np.array_equal(direct_read(), pattern_a)
        )
        for offset, value in enumerate(pattern_b):
            _single_write(tproc, address + offset, int(value))
        report["direct_write_bulk_read_matches"] = bool(
            np.array_equal(bulk_read(), pattern_b)
        )
        report["direct_write_direct_read_matches"] = bool(
            np.array_equal(direct_read(), pattern_b)
        )
    finally:
        for offset, value in enumerate(original):
            _single_write(tproc, address + offset, int(value))
    failures = [
        name for name, passed in report.items()
        if name.endswith("_matches") and not passed
    ]
    if failures:
        raise RuntimeError(
            "DMem round-trip mismatch at the bulk/direct boundary: "
            + ", ".join(failures)
        )
    return report


def main():
    if os.environ.get("Q3_FRESH_3A", "0").strip().lower() in {
        "1", "true", "yes", "on",
    }:
        correction_json = run_fresh_step3a()
        print(f"FRESH_3A_CORRECTION_JSON={correction_json}")
        return

    reset_mode = os.environ.get(
        "Q3_DIAGNOSTIC_RESET_MODE", "passive"
    ).strip().lower()
    if reset_mode not in ("passive", "active"):
        raise ValueError("Q3_DIAGNOSTIC_RESET_MODE must be passive or active")
    shots = int(os.environ.get("Q3_DIAGNOSTIC_SHOTS", "60"))
    points = int(os.environ.get("Q3_DIAGNOSTIC_POINTS", "11"))
    center_ghz = float(os.environ.get("Q3_DIAGNOSTIC_CENTER_GHZ", "4.05"))
    if shots < 2:
        raise ValueError("Q3_DIAGNOSTIC_SHOTS must be at least two")

    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.five_point_t1 import (
        estimate_five_point_t1,
        reduce_bidirectional_condition_states,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
        FivePointApplesToApples as runner,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
        TLSSpectroscopy as tls,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.ThreePointApplesToApples import (
        _integer_dc_grid,
        _target_frequency_grid_ghz,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import (
        acquire_t1_5pt_iq,
        classify_payload_iq,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import (
        PASSIVE_T1_RESET_US,
        ProductionResetSession,
        prepare_reset_session,
    )

    runner.install_scan_calibration(tls)
    tls._set_yoko_if_requested()
    soc, soccfg = tls.makeProxy()
    if bool(soc.streamer.readout_running()):
        raise RuntimeError(
            "QICK streamer is already running. Stop the other QICK acquisition "
            "before launching this isolated diagnostic."
        )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.acquisition import (
        dmem_words_from_soccfg,
    )
    dmem_roundtrip = verify_dmem_roundtrip(
        soc,
        dmem_words=dmem_words_from_soccfg(soccfg),
    )
    print(
        "[transport] DMem sentinel PASS: bulk DMA and direct AXI agree for "
        f"both write paths at address {dmem_roundtrip['address']} "
        f"({dmem_roundtrip['words']} words)"
    )

    params = dict(runner.P6_5PT_APPLES_TO_APPLES)
    full_target = _target_frequency_grid_ghz(params)
    full_dc, full_realized = _integer_dc_grid(params, full_target)
    target, dc_vec, indices = select_diagnostic_slice(
        full_target, full_dc, center_ghz=center_ghz, points=points
    )
    realized = np.asarray(full_realized)[indices]
    compensation, correction_mode = tls._resolve_step6_correction(
        params, None, tls.outerFolder
    )

    print(
        "[diagnostic] acquiring the DMem-native IQ classifier; the five-point "
        f"scan itself will use {reset_mode} reset"
    )
    classifier_session = prepare_reset_session(
        "active",
        outer_folder=tls.outerFolder,
        qubit=tls.QUBIT,
        base_cfg=tls.BaseConfig,
        soc=soc,
        soccfg=soccfg,
        purpose="FivePointMeasurementDiagnosticClassifier",
    )
    print(
        "[diagnostic] DMem-native classifier calibration saved: "
        f"{classifier_session.calibration_output}"
    )

    cfg = dict(tls.BaseConfig)
    cfg.update({
        "shots": shots,
        "ff_gain_vec": dc_vec,
        "apply_flux_tail_compensation": True,
        "flux_tail_compensation": compensation,
        "flux_fit_params": tls.FLUX_FIT_PARAMS,
        "relax_delay": PASSIVE_T1_RESET_US,
        "qubit_pulse_style": "arb",
        "flux_settle_time_us": float(params["flux_settle_us"]),
        "readout_thermalization_us": float(
            params["readout_thermalization_us"]
        ),
        "opx_t1_3pt_gain_lookup": True,
        "opx_diagnostic_condition_tags": True,
    })
    verify_dmem_reads = apply_diagnostic_dmem_verification(cfg)
    read_delay_us = apply_diagnostic_read_delay(cfg)
    feedback_timing = apply_diagnostic_feedback_timing(cfg)
    feedback_flush = apply_diagnostic_feedback_flush(cfg)
    pre_measure_sync = apply_diagnostic_pre_measure_sync(cfg)
    if reset_mode == "active":
        cfg = classifier_session.apply(cfg)
    else:
        cfg = ProductionResetSession.passive().apply(cfg)
        # Preserve the DMem-native payload classifier while leaving the scan's
        # between-record reset behavior strictly passive.
        cfg["opx_reset_calibration"] = dict(classifier_session.calibration)
    park_gain = cfg.get("ff_park_gain", tls._baseline_dc_offset())
    condition_names = ("P0", "P1", "Ps_10us", "Ps_50us", "Ps_200us")
    reset_scheme = "opx_unbounded" if reset_mode == "active" else "none"

    print(
        "[diagnostic] small real measurement: "
        f"{shots} shots x {len(dc_vec)} frequencies x 5 conditions; "
        f"{target[0]:.4f}..{target[-1]:.4f} GHz; "
        f"reset={reset_mode}; predistortion={correction_mode}; "
        f"accumulator_read_delay={read_delay_us:g} us; "
        f"feedback_timing={feedback_timing}; feedback_flush={feedback_flush}"
        f"; pre_measure_sync={pre_measure_sync}; "
        f"exhaustive_dmem_verify={verify_dmem_reads}"
    )
    print(
        f"[diagnostic] expecting {shots * len(dc_vec) * 5} resident records; "
        "acquiring now"
    )
    started, progress_started = start_diagnostic_timers()
    i_values, q_values, telemetry = acquire_t1_5pt_iq(
        soc,
        soccfg,
        cfg,
        dc_gains=dc_vec,
        delays_us=params["decay_delays_us"],
        reference_hold_us=float(params["reference_hold_us"]),
        shots=shots,
        reset_scheme=reset_scheme,
        progress=make_shot_progress(progress_started),
    )
    elapsed = time.monotonic() - started
    states = classify_payload_iq(
        cfg, i_values, q_values, telemetry["read_length_cycles"]
    )
    directional = reduce_bidirectional_condition_states(
        states, condition_names, canonical_dc_axis=True
    )
    survival = np.column_stack(
        [directional[name] for name in condition_names[2:]]
    )
    estimate = estimate_five_point_t1(
        directional["P0"],
        directional["P1"],
        survival,
        params["decay_delays_us"],
        shots_per_condition=shots,
        min_ref_contrast=float(params["min_ref_contrast"]),
        max_relative_error=float(params["max_relative_error"]),
        max_t1_us=float(params["max_fit_t1_us"]),
    )

    print(
        f"[measurement] completed in {elapsed:.2f} s; "
        f"IQ shape={i_values.shape}; states shape={states.shape}"
    )
    dmem_verification = telemetry.get("dmem_read_verification", {})
    print(
        "[transport] resident-bank verification: "
        f"bulk_matches_direct={dmem_verification.get('bulk_matches_direct')}, "
        f"banks={dmem_verification.get('banks_compared')}, "
        f"words={dmem_verification.get('words_compared')}"
    )
    print(
        "[ordering] FPGA condition tags: "
        f"mismatches={telemetry.get('condition_tag_mismatches')}; "
        "zero means the tProc emission order and host decode agree"
    )
    print(
        "[populations] medians: "
        + ", ".join(
            f"{name}={_median(directional[name]):.4f}"
            for name in condition_names
        )
    )
    contrast = np.asarray(directional["P1"]) - np.asarray(directional["P0"])
    valid = np.asarray(estimate["T1_5pt_valid_mask"], dtype=bool)
    print(
        f"[quality] median P1-P0={_median(contrast):.4f}; "
        f"valid T1={int(valid.sum())}/{valid.size} "
        f"({100.0 * valid.mean():.1f}%)"
    )
    print(
        "[direction-check] median P1-P0: "
        f"up={_median(np.asarray(directional['P1_scan_up']) - np.asarray(directional['P0_scan_up'])):.4f}, "
        f"down={_median(np.asarray(directional['P1_scan_down']) - np.asarray(directional['P0_scan_down'])):.4f}"
    )
    print(
        "[iq-check] median I by decoded condition: "
        + ", ".join(
            f"{name}={_median(i_values[index]):.7g}"
            for index, name in enumerate(condition_names)
        )
    )
    print("[record-offset-check] median P1-P0 under cyclic condition shifts:")
    shift_contrasts = {}
    for shift in range(len(condition_names)):
        shifted = reduce_bidirectional_condition_states(
            np.roll(states, shift, axis=0),
            condition_names,
            canonical_dc_axis=True,
        )
        shift_contrasts[shift] = _median(
            np.asarray(shifted["P1"]) - np.asarray(shifted["P0"])
        )
        print(f"  shift={shift:+d}: {shift_contrasts[shift]:+.4f}")

    now = datetime.now()
    output_dir = (
        Path(tls.outerFolder)
        / tls.QUBIT
        / f"{tls.QUBIT}_{now:%Y_%m_%d}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = output_dir / f"{tls.QUBIT}_{now:%H_%M_%S}_5pt_measurement_diagnostic"
    npz_path = Path(str(stem) + "_raw_iq.npz")
    csv_path = Path(str(stem) + "_populations.csv")
    json_path = Path(str(stem) + "_summary.json")
    np.savez_compressed(
        npz_path,
        I=i_values,
        Q=q_values,
        states=states,
        condition_names=np.asarray(condition_names),
        target_frequency_ghz=target,
        realized_frequency_ghz=realized,
        dc_offset_dac=dc_vec,
    )
    columns = {
        "target_frequency_ghz": target,
        "realized_frequency_ghz": realized,
        "dc_offset_dac": dc_vec,
    }
    for name in condition_names:
        columns[name] = np.asarray(directional[name])
        columns[f"{name}_scan_up"] = np.asarray(
            directional[f"{name}_scan_up"]
        )
        columns[f"{name}_scan_down"] = np.asarray(
            directional[f"{name}_scan_down"]
        )
    for name in (
        "ref_contrast_5pt",
        "T1_5pt_us_raw",
        "T1_5pt_us",
        "T1_5pt_err_us",
        "T1_5pt_valid_mask",
    ):
        columns[name] = np.asarray(estimate[name])
    _save_csv(csv_path, columns)
    summary = {
        "created": now.isoformat(),
        "reset_mode": reset_mode,
        "shots_per_condition": shots,
        "frequency_points": int(len(dc_vec)),
        "condition_names": condition_names,
        "median_populations": {
            name: _median(directional[name]) for name in condition_names
        },
        "median_reference_contrast": _median(contrast),
        "valid_t1_points": int(valid.sum()),
        "total_t1_points": int(valid.size),
        "condition_shift_reference_contrasts": shift_contrasts,
        "telemetry": telemetry,
        "dmem_roundtrip": dmem_roundtrip,
        "classifier_calibration": str(classifier_session.calibration_output),
        "accumulator_read_delay_us": read_delay_us,
        "feedback_read_timing": feedback_timing,
        "feedback_flush_mode": feedback_flush,
        "pre_measure_sync": pre_measure_sync,
        "correction_mode": correction_mode,
        "raw_iq_npz": str(npz_path),
        "populations_csv": str(csv_path),
        "park_gain": park_gain,
    }
    with open(json_path, "w") as handle:
        json.dump(summary, handle, indent=2, default=_json_default)
    print(f"RAW_IQ_NPZ={npz_path}")
    print(f"DIAGNOSTIC_CSV={csv_path}")
    print(f"SUMMARY_JSON={json_path}")
    if _median(contrast) <= 0.05:
        print(
            "[diagnostic] FAIL: P1 is not above P0 with usable contrast before "
            "the five-point fitter. Inspect the condition-shift table and raw IQ."
        )
    else:
        print("[diagnostic] PASS: measured P1 is above P0 with usable contrast")


if __name__ == "__main__":
    main()
