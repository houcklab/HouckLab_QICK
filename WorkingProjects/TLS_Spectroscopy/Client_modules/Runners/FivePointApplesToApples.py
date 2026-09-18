"""Matched-reference five-point TLS scan for the QICK controller.

This is deliberately separate from ThreePointApplesToApples.py.  It uses the
same 900 Bernoulli measurements per frequency as the 300-shot three-point
scan, distributed as 180 shots for each of P0, P1, and three survival delays.
"""

import gc
import os
import sys
from datetime import datetime


_directory = os.path.dirname(os.path.abspath(__file__))
while _directory != os.path.dirname(_directory):
    if os.path.isdir(os.path.join(_directory, "WorkingProjects")):
        if _directory not in sys.path:
            sys.path.insert(0, _directory)
        break
    _directory = os.path.dirname(_directory)
else:
    raise RuntimeError("Could not find the HouckLab_QICK repo root.")

import matplotlib
import numpy as np


matplotlib.use("Agg", force=True)


from fluxpred import production as fluxpred_production
from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.global_slot_sync import (
    GlobalSlotSynchronizer,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mT1VsFlux import (
    T15PointVsFlux,
    _csv_base_from_pickle,
    build_wall_clock_repeat_metadata,
    get_wall_clock_repeat_full_spec,
    get_wall_clock_repeat_spec,
    save_wall_clock_repeat_full_outputs,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.five_point_t1 import five_point_output_metadata
from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.protocol_crossover import (
    apply_phase as apply_crossover_phase,
    annotate_metadata as annotate_crossover_metadata,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import (
    AUTOMATIC_RECALIBRATION_MIN,
    PASSIVE_T1_RESET_US,
    prepare_reset_session,
)


P6_5PT_APPLES_TO_APPLES = {
    "shots_per_condition": 180,
    "decay_delays_us": [40.0, 80.0, 200.0],
    "reference_hold_us": 2.0,
    "dc_min": -20550,
    "dc_max": -11800,
    "freq_min_ghz": 3.9,
    "freq_max_ghz": 4.3,
    "freq_step_mhz": 0.5,
    "wall_clock_duration_min": 10080,
    # The target only needs the common 0.5 us settling interval.  The q3
    # return/readout contract is separate: 24 us is the shortest tested
    # interval statistically equivalent to a fully waited park readout.
    "flux_settle_us": 0.5,
    "flux_predistortion_return_prefix_us": 24.0,
    "flux_predistortion_recovery_us": 40.0,
    "flux_predistortion_recovery_scale": 0.25,
    "readout_thermalization_us": 10.0,
    "apply_flux_tail_compensation": True,
    "reset_mode": "active",
    "sync_enabled": True,
    "sync_role": "follower",
    "sync_session": "q3_q5_5pt_apples_20260914_v1",
    "sync_directory": "Z:/FluxTeam/Data/.qick_qua_sync",
    "sync_slot_s": 150.0,
    "sync_lead_s": 60.0,
    "sync_timeout_s": 3600.0,
    "sync_ntp_refresh_s": 1800.0,
    "sync_peer_wait_s": 300.0,
    "sync_boundary_guard_s": 5.0,
    "reset_recalibration_min": 30.0,
    "min_ref_contrast": 0.05,
    "max_relative_error": 0.5,
    "max_fit_t1_us": 3000.0,
    "reverse_survival_order": False,
}


def apply_series_overrides(params, environ=None):
    environ = os.environ if environ is None else environ
    out = dict(params)
    duration = environ.get("Q3_5PT_DURATION_MIN")
    if duration is not None and str(duration).strip() != "":
        minutes = float(duration)
        if not (minutes > 0.0) or minutes != minutes:
            raise ValueError("Q3_5PT_DURATION_MIN must be finite and positive")
        out["wall_clock_duration_min"] = minutes
        print(f"[scan] wall-clock duration {params['wall_clock_duration_min']:g} -> "
              f"{minutes:g} min (Q3_5PT_DURATION_MIN)")
    predist = environ.get("Q3_5PT_PREDISTORTION")
    if predist is not None and str(predist).strip() != "":
        wanted = str(predist).strip().lower()
        if wanted not in {"on", "off", "1", "0", "true", "false", "yes", "no"}:
            raise ValueError("Q3_5PT_PREDISTORTION must be on or off")
        applied = wanted in {"on", "1", "true", "yes"}
        out["apply_flux_tail_compensation"] = applied
        out["predistortion_arm"] = "on" if applied else "off"
        if applied != bool(params.get("apply_flux_tail_compensation", True)):
            print(f"[scan] apply_flux_tail_compensation "
                  f"{bool(params.get('apply_flux_tail_compensation'))} -> {applied} "
                  "(Q3_5PT_PREDISTORTION)")
        if not applied:
            print("[scan] PREDISTORTION OFF arm: the qubit drifts during every "
                  "measurement, so this arm is expected to be physically wrong, not a "
                  "reference to match")
    delays = environ.get("Q3_5PT_DELAYS_US")
    if delays is not None and str(delays).strip() != "":
        vals = [float(v) for v in str(delays).replace(",", " ").split()]
        if len(vals) < 1:
            raise ValueError("Q3_5PT_DELAYS_US must list at least one delay")
        if any(not (v > 0.0) or v != v for v in vals):
            raise ValueError("Q3_5PT_DELAYS_US entries must be finite and positive")
        if sorted(vals) != vals:
            raise ValueError("Q3_5PT_DELAYS_US must be in increasing order")
        out["decay_delays_us"] = vals
        print(f"[scan] decay delays {params['decay_delays_us']} -> {vals} us "
              "(Q3_5PT_DELAYS_US)")
    for key, env in (("freq_min_ghz", "Q3_5PT_FREQ_MIN_GHZ"),
                     ("freq_max_ghz", "Q3_5PT_FREQ_MAX_GHZ"),
                     ("freq_step_mhz", "Q3_5PT_FREQ_STEP_MHZ")):
        raw = environ.get(env)
        if raw is not None and str(raw).strip() != "":
            val = float(raw)
            if not (val > 0.0) or val != val:
                raise ValueError(f"{env} must be finite and positive")
            out[key] = val
            print(f"[scan] {key} {params[key]} -> {val} ({env})")
    sync = environ.get("Q3_5PT_SYNC")
    if sync is not None and str(sync).strip() != "":
        wanted = str(sync).strip().lower()
        if wanted not in {"on", "off", "1", "0", "true", "false", "yes", "no"}:
            raise ValueError("Q3_5PT_SYNC must be on or off")
        enabled = wanted in {"on", "1", "true", "yes"}
        out["sync_enabled"] = enabled
        if enabled != bool(params.get("sync_enabled", False)):
            print(f"[scan] sync_enabled {bool(params.get('sync_enabled'))} -> {enabled} "
                  "(Q3_5PT_SYNC)")
    return out


def runtime_parameters(environ=None):
    return apply_series_overrides(
        apply_crossover_phase(
            P6_5PT_APPLES_TO_APPLES,
            expected="current_on",
            environ=environ,
        ),
        environ=environ,
    )


APPLE_FLUX_FIT_PARAMS = [
    6.0089036599253225,
    0.24978861537376948,
    46821.65898343736,
    -16500.00011106883,
    0.4052706711778531,
    -5.54146293201133e-05,
]
APPLE_BASELINE_DC_OFFSET = -25146
APPLE_TARGET_DC_OFFSET = -14750
APPLE_DT_PULSEPLAY_US = 0.5
APPLE_DT_PULSEDEF_US = 0.002


def apply_verified_feedback_timing(cfg):
    """Apply the q3 readout timing sequence accepted by the hardware gate."""
    cfg.update({
        "opx_feedback_read_timing": "official_wait_all",
        "opx_feedback_pre_measure_sync": True,
        "opx_feedback_flush_mode": "off",
        "opx_read_delay_us": 10.0,
    })
    return cfg


def install_scan_calibration(tls):
    """Install the P4/step-response calibration frozen for this long scan."""
    tls.FLUX_FIT_PARAMS = list(APPLE_FLUX_FIT_PARAMS)
    tls.BASELINE_DC_OFFSET = APPLE_BASELINE_DC_OFFSET
    tls.TARGET_DC_OFFSET = APPLE_TARGET_DC_OFFSET
    # Keep the scan waveform identical to the waveform used to fit the
    # accepted predistortion correction.  Scope this override to this runner
    # so legacy experiments retain their existing defaults.
    tls.BaseConfig["dt_pulseplay"] = APPLE_DT_PULSEPLAY_US
    tls.BaseConfig["dt_pulsedef"] = APPLE_DT_PULSEDEF_US
    requested_gain = os.environ.get("Q3_FLUX_TAIL_GAIN")
    if requested_gain is not None and str(requested_gain).strip() != "":
        gain = float(requested_gain)
        if not (gain > 0.0) or gain != gain:
            raise ValueError("Q3_FLUX_TAIL_GAIN must be finite and positive")
        if gain != tls.FLUX_TAIL_COMPENSATION_GAIN:
            print(f"[predistortion] flux tail gain "
                  f"{tls.FLUX_TAIL_COMPENSATION_GAIN} -> {gain} (Q3_FLUX_TAIL_GAIN)")
        tls.FLUX_TAIL_COMPENSATION_GAIN = gain


def resolve_production_correction(params, resolve, environ=None):
    """Resolve the exact requested correction, retaining auto-discovery fallback."""
    environ = os.environ if environ is None else environ
    correction_json = str(environ.get("Q3_5PT_CORRECTION_JSON", "")).strip() or None
    if correction_json is not None:
        print(
            "[predistortion] explicit Q3_5PT_CORRECTION_JSON="
            f"{correction_json}"
        )
    compensation, correction_mode = resolve(correction_json)
    return correction_json, compensation, correction_mode


def _run_series(
    factory,
    wall_clock_s,
    synchronizer,
    recalibrate,
    recalibration_min=AUTOMATIC_RECALIBRATION_MIN,
):
    series_start = None
    base_path = None
    csv_path = None
    run_index = 0
    completed = 0
    consecutive_failures = 0
    last_cal = datetime.now()
    unsynchronized_start = None
    while True:
        if not synchronizer.enabled:
            now = synchronizer.corrected_clock()
            if unsynchronized_start is None:
                unsynchronized_start = now
            elif wall_clock_s is not None and now - unsynchronized_start >= wall_clock_s:
                break
        sync_metadata = synchronizer.wait_for_start(run_index, wall_clock_s)
        if sync_metadata is None:
            break
        run_start = datetime.now()
        if series_start is None:
            series_start = run_start
            last_cal = run_start
        repeat_metadata = build_wall_clock_repeat_metadata(
            run_start, series_start, run_index
        )
        repeat_metadata.update(sync_metadata)
        repeat_metadata.setdefault("sync_actual_start_epoch_s", float(synchronizer.corrected_clock()))
        print(
            f"five-point apples-to-apples run {run_index + 1} "
            f"(elapsed {repeat_metadata['wall_clock_elapsed_minutes_from_first_run']:.1f} min)"
        )
        try:
            exp = factory(repeat_metadata)
            exp.acquire(progress=True)
        except KeyboardInterrupt:
            print(f"interrupted after {completed} completed run(s)")
            break
        except Exception as exc:
            consecutive_failures += 1
            detail = f"{type(exc).__name__}: {str(exc)[:160]}"
            print(
                f"run {run_index + 1} FAILED ({detail}); continuing "
                f"({consecutive_failures} consecutive failure(s))"
            )
            try:
                synchronizer.wait_for_end(
                    run_index, status="failed", error=detail
                )
            except Exception as sync_exc:
                print(
                    f"[sync] completion update failed "
                    f"({type(sync_exc).__name__}: {sync_exc}); continuing locally."
                )
            run_index += 1
            continue
        scan_finish = synchronizer.corrected_clock()
        repeat_metadata["sync_scan_finish_epoch_s"] = float(scan_finish)
        repeat_metadata["sync_scan_duration_s"] = float(
            scan_finish - repeat_metadata["sync_actual_start_epoch_s"]
        )
        repeat_metadata["sync_scan_overrun_s"] = max(
            0.0, float(scan_finish - repeat_metadata.get("sync_scheduled_end_epoch_s", scan_finish))
        )
        repeat_metadata.update(five_point_output_metadata(exp.data, exp.CONDITION_NAMES))
        exp.data.update(repeat_metadata)
        consecutive_failures = 0
        completed += 1
        if base_path is None:
            base_path = _csv_base_from_pickle(exp.pname)
            exp.save_config()
        spec = get_wall_clock_repeat_spec(exp)
        full_spec = get_wall_clock_repeat_full_spec(exp) or {}
        scalar_columns = dict(full_spec.get("scalar_columns", {}))
        scalar_columns["target_frequency_ghz"] = exp.data[
            "target_frequency_ghz"
        ]
        scalar_columns["fit_frequency_ghz"] = exp.data["fit_frequency_ghz"]
        run_data = {
            "run_metadata": repeat_metadata,
            "dc_vec": np.asarray(exp.dc_vec, dtype=float),
            "metric_column_name": spec["metric_column_name"],
            "metric_values": np.asarray(spec["metric_values"], dtype=float),
            "extra_metric_matrices": {
                key: np.asarray(values, dtype=float)
                for key, values in dict(
                    spec.get("extra_metric_matrices", {})
                ).items()
            },
            "axes": full_spec.get("axes", {}),
            "scalar_columns": scalar_columns,
            "array_columns": full_spec.get("array_columns", {}),
        }
        csv_path = save_wall_clock_repeat_full_outputs(
            base_path,
            spec["file_tag"],
            [run_data],
            append=completed > 1,
        )
        print(f"one-stop CSV updated: {csv_path}")
        if (
            datetime.now() - last_cal
        ).total_seconds() >= float(recalibration_min) * 60.0:
            try:
                recalibrate()
            except Exception as exc:
                print(
                    "automatic reset recalibration rejected; retaining the "
                    f"last valid calibration ({type(exc).__name__}: {exc})"
                )
            last_cal = datetime.now()
        try:
            synchronizer.wait_for_end(run_index, status="success")
        except Exception as sync_exc:
            print(
                f"[sync] completion update failed "
                f"({type(sync_exc).__name__}: {sync_exc}); continuing locally."
            )
        run_index += 1
    return csv_path


def resolve_neutral_selection(tls, environ=None, execution_test_mode=""):
    park = float(tls._baseline_dc_offset())
    scale = float(tls.TARGET_DC_OFFSET)-park
    choice = fluxpred_production.selection(
        "q3", park=park, scale=scale, environ=environ, amplitude_range=(0.0, 1.0))
    for line in fluxpred_production.describe(choice):
        print(line)
    if choice["mode"] == "neutral" and not execution_test_mode:
        acceptance = choice.get("document", {}).get("acceptance", {})
        required = ("software", "scientific", "hardware")
        missing = [gate for gate in required if acceptance.get(gate) is not True]
        if missing:
            raise RuntimeError(
                "Q3_FLUXPRED_MODE=neutral is currently limited to a single-round execution test "
                f"because the model is missing acceptance gate(s): {', '.join(missing)}. "
                "Set Q3_5PT_EXECUTION_TEST=active (or passive) to collect the full-band hardware "
                "acceptance map; the synchronized long series remains blocked until that map passes.")
    return choice


def render_neutral_scan_compensation(choice, params):
    """Render the shared model at every exact production hold."""
    settle_us = float(params["flux_settle_us"])
    reference_us = float(params["reference_hold_us"])
    holds_ns = tuple(dict.fromkeys(
        1000.0 * (settle_us + value)
        for value in (
            reference_us,
            *(reference_us + float(delay)
              for delay in params["decay_delays_us"]),
        )
    ))
    source = fluxpred_production.neutral_lifecycle_table(
        choice,
        holds_ns=holds_ns,
        recovery_ns=1000.0 * float(params["flux_predistortion_recovery_us"]),
        schedule_first_ns=500.0,
        schedule_growth=1.2,
        schedule_max_ns=100_000.0,
        quantum_ns=4.0,
    )
    return fluxpred_production.scale_lifecycle_recovery(
        source,
        float(params["flux_predistortion_recovery_scale"]),
    )


def execution_test_settings(environ=None):
    environ = os.environ if environ is None else environ
    mode = str(environ.get("Q3_5PT_EXECUTION_TEST", "")).strip().lower()
    if mode not in ("", "passive", "active"):
        raise ValueError(
            "Q3_5PT_EXECUTION_TEST must be unset, 'passive', or 'active'"
        )
    save = str(environ.get("Q3_5PT_EXECUTION_TEST_SAVE", "")).strip().lower() in {
        "1", "true", "yes", "on",
    }
    if save and not mode:
        raise ValueError(
            "Q3_5PT_EXECUTION_TEST_SAVE requires Q3_5PT_EXECUTION_TEST"
        )
    return mode, save


def save_execution_test_outputs(exp):
    """Save one isolated full-band acquisition without entering the series."""
    now = datetime.now()
    metadata = build_wall_clock_repeat_metadata(now, now, 0)
    metadata["execution_test"] = True
    metadata.update(five_point_output_metadata(exp.data, exp.CONDITION_NAMES))
    exp.data.update(metadata)
    exp.save_config()
    spec = get_wall_clock_repeat_spec(exp)
    full_spec = get_wall_clock_repeat_full_spec(exp) or {}
    scalar_columns = dict(full_spec.get("scalar_columns", {}))
    scalar_columns["target_frequency_ghz"] = exp.data["target_frequency_ghz"]
    scalar_columns["fit_frequency_ghz"] = exp.data["fit_frequency_ghz"]
    run_data = {
        "run_metadata": metadata,
        "dc_vec": np.asarray(exp.dc_vec, dtype=float),
        "metric_column_name": spec["metric_column_name"],
        "metric_values": np.asarray(spec["metric_values"], dtype=float),
        "extra_metric_matrices": {
            key: np.asarray(values, dtype=float)
            for key, values in dict(spec.get("extra_metric_matrices", {})).items()
        },
        "axes": full_spec.get("axes", {}),
        "scalar_columns": scalar_columns,
        "array_columns": full_spec.get("array_columns", {}),
    }
    return save_wall_clock_repeat_full_outputs(
        _csv_base_from_pickle(exp.pname),
        spec["file_tag"],
        [run_data],
        append=False,
    )


def main():
    execution_test_mode, execution_test_save = execution_test_settings()
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSSpectroscopy as tls
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.ThreePointApplesToApples import (
        _integer_dc_grid, _target_frequency_grid_ghz,
    )

    install_scan_calibration(tls)
    gc.collect()
    tls._set_yoko_if_requested()
    soc, soccfg = tls.makeProxy()
    p = runtime_parameters()
    if execution_test_mode:
        p["reset_mode"] = execution_test_mode
    target = _target_frequency_grid_ghz(p)
    dc_vec, realized = _integer_dc_grid(p, target)
    wall_clock_s = 60.0 * float(p["wall_clock_duration_min"])
    neutral = resolve_neutral_selection(
        tls, execution_test_mode=execution_test_mode
    )
    if neutral["mode"] == "neutral":
        correction_json = neutral["model_path"]
        compensation = render_neutral_scan_compensation(neutral, p)
        correction_mode = "distortion-corrected"
        print(
            "[predistortion] rendered controller-neutral model for the exact "
            f"production lifecycle: {len(compensation['multipliers'])} segments, "
            f"recovery={p['flux_predistortion_recovery_us']:g} us, "
            f"return scale={p['flux_predistortion_recovery_scale']:g}, "
            f"target settle={p['flux_settle_us']:g} us, "
            f"return prefix={p['flux_predistortion_return_prefix_us']:g} us"
        )
    else:
        correction_json, compensation, correction_mode = resolve_production_correction(
            p,
            lambda requested: tls._resolve_step6_correction(
                p, requested, tls.outerFolder
            ),
        )
    neutral_record = fluxpred_production.provenance(
        neutral, backend="qick",
        code_commit=os.environ.get("Q3_CODE_COMMIT", "unknown"))
    neutral_record["recovery_scale"] = float(
        p["flux_predistortion_recovery_scale"]
    )
    neutral_record["settle_us"] = float(p["flux_settle_us"])
    neutral_record["return_prefix_us"] = float(
        p["flux_predistortion_return_prefix_us"]
    )
    predistortion_on = bool(p.get("apply_flux_tail_compensation", True))
    if not predistortion_on:
        compensation = None
        correction_mode = "uncorrected"
        print("[predistortion] OFF arm: no flux tail compensation will be applied")

    reset_session = prepare_reset_session(
        p["reset_mode"],
        outer_folder=tls.outerFolder,
        qubit=tls.QUBIT,
        base_cfg=tls.BaseConfig,
        soc=soc,
        soccfg=soccfg,
        purpose=f"{2 + len(p['decay_delays_us'])}PointApplesToApples",
    )
    print(f"automatic reset calibration saved: {reset_session.calibration_output}")
    base = dict(tls.BaseConfig)
    base.update({
        "shots": int(p["shots_per_condition"]),
        "ff_gain_vec": dc_vec,
        "apply_flux_tail_compensation": predistortion_on,
        "flux_tail_compensation": compensation,
        "flux_fit_params": tls.FLUX_FIT_PARAMS,
        "relax_delay": PASSIVE_T1_RESET_US,
        "qubit_pulse_style": "arb",
        "flux_settle_time_us": float(p["flux_settle_us"]),
        "flux_predistortion_return_prefix_us": float(
            p["flux_predistortion_return_prefix_us"]
        ),
        "flux_predistortion_recovery_us": float(
            p["flux_predistortion_recovery_us"]
        ),
        "readout_thermalization_us": float(
            p["readout_thermalization_us"]
        ),
        "opx_t1_3pt_gain_lookup": True,
        "opx_reverse_survival_order": bool(
            p.get("reverse_survival_order", False)
        ),
    })
    base = reset_session.apply(base)
    apply_verified_feedback_timing(base)
    park_gain = base.get("ff_park_gain", tls._baseline_dc_offset())
    state = {"session": reset_session}

    def recalibrate():
        state["session"] = prepare_reset_session(
            p["reset_mode"],
            outer_folder=tls.outerFolder,
            qubit=tls.QUBIT,
            base_cfg=tls.BaseConfig,
            soc=soc,
            soccfg=soccfg,
            purpose=f"{2 + len(p['decay_delays_us'])}PointApplesToApples",
        )
        refreshed = state["session"].apply(base)
        base.clear()
        base.update(refreshed)
        print(
            "automatic reset calibration refreshed: "
            f"{state['session'].calibration_output}"
        )

    def factory(repeat_metadata):
        repeat_metadata.update(annotate_crossover_metadata({}, p))
        exp = T15PointVsFlux(
            soc=soc,
            soccfg=soccfg,
            path=tls.QUBIT,
            outerFolder=tls.outerFolder,
            suffix=p.get(
                "output_suffix",
                f"TLS_{2 + len(p['decay_delays_us'])}pt_Apples_to_Apples"
                + ("" if "predistortion_arm" not in p
                   else f"_pred_{p['predistortion_arm']}"),
            ),
            cfg=dict(base),
            dc_vec=dc_vec,
            decay_delays_us=p["decay_delays_us"],
            reference_hold_us=float(p["reference_hold_us"]),
            shots=int(p["shots_per_condition"]),
            calib_params=None,
            park_voltage=park_gain,
            min_ref_contrast=float(p["min_ref_contrast"]),
            max_relative_error=float(p["max_relative_error"]),
            max_fit_t1_us=float(p["max_fit_t1_us"]),
            reset_mode=base["reset_mode"],
            flux_tail_compensation=compensation,
            repeat_metadata=repeat_metadata,
            write_outputs=False,
        )
        exp.data["target_frequency_ghz"] = target
        exp.data["fit_frequency_ghz"] = realized
        exp.data["correction_mode"] = correction_mode
        exp.data["fluxpred_provenance"] = neutral_record
        return exp

    print(
        f"{2 + len(p['decay_delays_us'])}-condition protocol: {len(target)} frequencies, "
        f"{p['shots_per_condition']} shots x {2 + len(p['decay_delays_us'])} conditions, "
        f"delays={p['decay_delays_us']} us, {correction_mode}"
    )
    if execution_test_mode:
        print(
            f"[execution-test] one complete {p['shots_per_condition']} x "
            f"{len(target)} x {2 + len(p['decay_delays_us'])} pass with "
            f"{execution_test_mode} reset; scan results will "
            f"{'be saved' if execution_test_save else 'not be saved'}"
        )
        exp = factory({})
        exp.acquire(progress=True)
        if execution_test_save:
            output_path = save_execution_test_outputs(exp)
            print(f"[execution-test] saved full-band output: {output_path}")
        print("[execution-test] PASS: the complete workload finished")
        return
    synchronizer = GlobalSlotSynchronizer.from_config(p)
    synchronizer.prepare()
    csv_path = _run_series(
        factory,
        wall_clock_s,
        synchronizer,
        recalibrate,
        recalibration_min=float(p["reset_recalibration_min"]),
    )
    print(
        f"apples-to-apples {2 + len(p['decay_delays_us'])}-condition "
        f"scan complete: {csv_path}"
    )


if __name__ == "__main__":
    main()
