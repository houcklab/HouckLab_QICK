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
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import (
    AUTOMATIC_RECALIBRATION_MIN,
    PASSIVE_T1_RESET_US,
    prepare_reset_session,
)


P6_5PT_APPLES_TO_APPLES = {
    "shots_per_condition": 180,
    "decay_delays_us": [10.0, 50.0, 200.0],
    "reference_hold_us": 2.0,
    "dc_min": -20550,
    "dc_max": -11800,
    "freq_min_ghz": 3.9,
    "freq_max_ghz": 4.3,
    "freq_step_mhz": 0.5,
    "wall_clock_duration_min": 10080,
    "flux_settle_us": 0.5,
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
}


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


def main():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSSpectroscopy as tls
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.ThreePointApplesToApples import (
        _integer_dc_grid, _target_frequency_grid_ghz,
    )

    install_scan_calibration(tls)
    gc.collect()
    tls._set_yoko_if_requested()
    soc, soccfg = tls.makeProxy()
    p = dict(P6_5PT_APPLES_TO_APPLES)
    target = _target_frequency_grid_ghz(p)
    dc_vec, realized = _integer_dc_grid(p, target)
    wall_clock_s = 60.0 * float(p["wall_clock_duration_min"])
    compensation, correction_mode = tls._resolve_step6_correction(
        p, None, tls.outerFolder
    )
    reset_session = prepare_reset_session(
        p["reset_mode"],
        outer_folder=tls.outerFolder,
        qubit=tls.QUBIT,
        base_cfg=tls.BaseConfig,
        soc=soc,
        soccfg=soccfg,
        purpose="FivePointApplesToApples",
    )
    print(f"automatic reset calibration saved: {reset_session.calibration_output}")
    base = dict(tls.BaseConfig)
    base.update({
        "shots": int(p["shots_per_condition"]),
        "ff_gain_vec": dc_vec,
        "apply_flux_tail_compensation": True,
        "flux_tail_compensation": compensation,
        "flux_fit_params": tls.FLUX_FIT_PARAMS,
        "relax_delay": PASSIVE_T1_RESET_US,
        "qubit_pulse_style": "arb",
        "flux_settle_time_us": float(p["flux_settle_us"]),
        "readout_thermalization_us": float(
            p["readout_thermalization_us"]
        ),
        "opx_t1_3pt_gain_lookup": True,
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
            purpose="FivePointApplesToApples",
        )
        refreshed = state["session"].apply(base)
        base.clear()
        base.update(refreshed)
        print(
            "automatic reset calibration refreshed: "
            f"{state['session'].calibration_output}"
        )

    def factory(repeat_metadata):
        exp = T15PointVsFlux(
            soc=soc,
            soccfg=soccfg,
            path=tls.QUBIT,
            outerFolder=tls.outerFolder,
            suffix="TLS_5pt_Apples_to_Apples",
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
        return exp

    print(
        f"five-point protocol: {len(target)} frequencies, "
        f"{p['shots_per_condition']} shots x 5 conditions, "
        f"delays={p['decay_delays_us']} us, {correction_mode}"
    )
    synchronizer = GlobalSlotSynchronizer.from_config(p)
    synchronizer.prepare()
    csv_path = _run_series(
        factory,
        wall_clock_s,
        synchronizer,
        recalibrate,
        recalibration_min=float(p["reset_recalibration_min"]),
    )
    print(f"apples-to-apples five-point scan complete: {csv_path}")


if __name__ == "__main__":
    main()
