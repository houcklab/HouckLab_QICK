import gc
import os
import sys
from datetime import datetime


_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d):
    if os.path.isdir(os.path.join(_d, "WorkingProjects")):
        if _d not in sys.path:
            sys.path.insert(0, _d)
        break
    _d = os.path.dirname(_d)
else:
    raise RuntimeError("Could not find the HouckLab_QICK repo root.")

import numpy as np
import matplotlib


matplotlib.use("Agg", force=True)


from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.global_slot_sync import (
    GlobalSlotSynchronizer,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mT1VsFlux import (
    T13PointVsFlux,
    _csv_base_from_pickle,
    build_wall_clock_repeat_metadata,
    get_wall_clock_repeat_full_spec,
    get_wall_clock_repeat_spec,
    save_wall_clock_repeat_full_outputs,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_fit as fx
from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSSpectroscopy as tls
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import (
    AUTOMATIC_RECALIBRATION_MIN,
    PASSIVE_T1_RESET_US,
    prepare_reset_session,
)


P6_3PT_APPLES_TO_APPLES = {
    "shots": 300,
    "dc_min": -20511,
    "dc_max": -6744,
    "freq_min_ghz": 3.8,
    "freq_max_ghz": 4.3,
    "freq_step_mhz": 0.5,
    "wall_clock_duration_min": 10080,
    "Ts_us": 100.0,
    "flux_settle_us": 0.5,
    "readout_thermalization_us": 10.0,
    "reset_mode": "active",
    "sync_enabled": True,
    "sync_role": "follower",
    "sync_session": "q3_q5_3pt_apples_20260907_v3",
    "sync_directory": "Z:/FluxTeam/Data",
    "sync_slot_s": 180.0,
    "sync_lead_s": 60.0,
    "sync_timeout_s": 3600.0,
    "sync_ntp_refresh_s": 1800.0,
    "min_ref_contrast": 0.05,
    "max_plot_t1_multiple": 20.0,
}


MAX_CONSECUTIVE_RUN_FAILURES = 3


def _target_frequency_grid_ghz(p):
    low = float(p["freq_min_ghz"])
    high = float(p["freq_max_ghz"])
    step = float(p["freq_step_mhz"]) / 1e3
    if high <= low or step <= 0.0:
        raise ValueError("freq_max_ghz must exceed freq_min_ghz and freq_step_mhz must be positive")
    count = int(round((high - low) / step)) + 1
    target = high - step * np.arange(count, dtype=float)
    if abs(float(target[-1]) - low) > 1e-9:
        raise ValueError("the requested frequency range is not divisible by freq_step_mhz")
    target[-1] = low
    return target


def _integer_dc_grid(p, target):
    candidates = np.arange(int(p["dc_min"]), int(p["dc_max"]) + 1, dtype=np.int64)
    fitted = fx.estimate_fit_frequency_ghz_array(tls.FLUX_FIT_PARAMS, candidates)
    delta = np.diff(fitted)
    if np.all(delta > 0):
        mapped = np.interp(target, fitted, candidates)
    elif np.all(delta < 0):
        mapped = np.interp(target, fitted[::-1], candidates[::-1])
    else:
        raise RuntimeError("the QICK inversion interval is not monotonic")
    dc_vec = np.rint(mapped).astype(np.int64)
    if np.unique(dc_vec).size != dc_vec.size:
        raise RuntimeError("the QICK DAC resolution cannot realize every target frequency")
    realized = fx.estimate_fit_frequency_ghz_array(tls.FLUX_FIT_PARAMS, dc_vec)
    error_mhz = 1e3 * (realized - target)
    if float(np.max(np.abs(error_mhz))) > 0.1:
        raise RuntimeError("the nearest-DAC frequency error exceeds 0.1 MHz")
    print(f"exact common frequency grid: {len(target)} points, "
          f"{target[0]:.4f}..{target[-1]:.4f} GHz at {p['freq_step_mhz']:g} MHz; "
          f"QICK nearest-DAC max error {np.max(np.abs(error_mhz)):.4f} MHz")
    return dc_vec, realized


def _run_series(factory, wall_clock_s, synchronizer, recalibrate):
    series_start = None
    base_path = None
    csv_path = None
    run_index = 0
    completed = 0
    consecutive_failures = 0
    last_cal = datetime.now()
    while True:
        sync_metadata = synchronizer.wait_for_start(run_index, wall_clock_s)
        if sync_metadata is None:
            break
        run_start = datetime.now()
        if series_start is None:
            series_start = run_start
            last_cal = run_start
        repeat_metadata = build_wall_clock_repeat_metadata(run_start, series_start, run_index)
        repeat_metadata.update(sync_metadata)
        print(f"apples-to-apples run {run_index + 1} "
              f"(elapsed {repeat_metadata['wall_clock_elapsed_minutes_from_first_run']:.1f} min)")
        try:
            exp = factory(repeat_metadata)
            exp.acquire(progress=True)
        except KeyboardInterrupt:
            print(f"interrupted after {completed} completed run(s)")
            break
        except Exception as exc:
            consecutive_failures += 1
            print(f"run {run_index + 1} FAILED ({type(exc).__name__}: {str(exc)[:160]})")
            if consecutive_failures >= MAX_CONSECUTIVE_RUN_FAILURES:
                raise
            synchronizer.wait_for_end(run_index)
            run_index += 1
            continue
        scan_finish = synchronizer.corrected_clock()
        repeat_metadata["sync_scan_finish_epoch_s"] = float(scan_finish)
        repeat_metadata["sync_scan_duration_s"] = float(
            scan_finish - repeat_metadata["sync_actual_start_epoch_s"]
        )
        exp.data.update(repeat_metadata)
        consecutive_failures = 0
        completed += 1
        if base_path is None:
            base_path = _csv_base_from_pickle(exp.pname)
            exp.save_config()
        spec = get_wall_clock_repeat_spec(exp)
        full_spec = get_wall_clock_repeat_full_spec(exp) or {}
        scalar_columns = dict(full_spec.get("scalar_columns", {}))
        scalar_columns["target_frequency_ghz"] = exp.data["target_frequency_ghz"]
        scalar_columns["fit_frequency_ghz"] = exp.data["fit_frequency_ghz"]
        run_data = {
            "run_metadata": repeat_metadata,
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
        csv_path = save_wall_clock_repeat_full_outputs(
            base_path,
            spec["file_tag"],
            [run_data],
            append=completed > 1,
        )
        print(f"one-stop CSV updated: {csv_path}")
        if (datetime.now() - last_cal).total_seconds() >= AUTOMATIC_RECALIBRATION_MIN * 60.0:
            try:
                recalibrate()
            except ValueError as exc:
                print(
                    "automatic reset recalibration rejected; retaining the last valid "
                    f"calibration ({exc})"
                )
            last_cal = datetime.now()
        synchronizer.wait_for_end(run_index)
        run_index += 1
    return csv_path


def main():
    gc.collect()
    tls._set_yoko_if_requested()
    soc, soccfg = tls.makeProxy()
    p = dict(P6_3PT_APPLES_TO_APPLES)
    target = _target_frequency_grid_ghz(p)
    dc_vec, realized = _integer_dc_grid(p, target)
    wall_clock_s = 60.0 * float(p["wall_clock_duration_min"])
    reset_session = prepare_reset_session(
        p["reset_mode"],
        outer_folder=tls.outerFolder,
        qubit=tls.QUBIT,
        base_cfg=tls.BaseConfig,
        soc=soc,
        soccfg=soccfg,
        purpose="ThreePointApplesToApples",
    )
    print(f"automatic reset calibration saved: {reset_session.calibration_output}")
    base = dict(tls.BaseConfig)
    base.update({
        "shots": int(p["shots"]),
        "ff_gain_vec": dc_vec,
        "apply_flux_tail_compensation": False,
        "flux_tail_compensation": None,
        "flux_fit_params": tls.FLUX_FIT_PARAMS,
        "relax_delay": PASSIVE_T1_RESET_US,
        "qubit_pulse_style": "arb",
        "flux_settle_time_us": float(p["flux_settle_us"]),
        "readout_thermalization_us": float(p["readout_thermalization_us"]),
        "opx_t1_3pt_gain_lookup": True,
    })
    base = reset_session.apply(base)
    base["three_point_matched_refs"] = False
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
            purpose="ThreePointApplesToApples",
        )
        refreshed = state["session"].apply(base)
        base.clear()
        base.update(refreshed)
        base["three_point_matched_refs"] = False
        print(f"automatic reset calibration refreshed: {state['session'].calibration_output}")

    def factory(repeat_metadata):
        exp = T13PointVsFlux(
            soc=soc,
            soccfg=soccfg,
            path=tls.QUBIT,
            outerFolder=tls.outerFolder,
            suffix="TLS_3pt_Apples_to_Apples",
            cfg=dict(base),
            dc_vec=dc_vec,
            Ts_ns=int(round(float(p["Ts_us"]) * 1e3)),
            shots=int(p["shots"]),
            calib_params=None,
            park_voltage=park_gain,
            min_ref_contrast=float(p["min_ref_contrast"]),
            max_plot_t1_multiple=p["max_plot_t1_multiple"],
            reset_mode=base["reset_mode"],
            flux_tail_compensation=None,
            repeat_metadata=repeat_metadata,
            write_outputs=False,
        )
        exp.data["target_frequency_ghz"] = target
        exp.data["fit_frequency_ghz"] = realized
        return exp

    synchronizer = GlobalSlotSynchronizer.from_config(p)
    synchronizer.prepare()
    csv_path = _run_series(factory, wall_clock_s, synchronizer, recalibrate)
    print(f"apples-to-apples 3-point scan complete: {csv_path}")


if __name__ == "__main__":
    main()
