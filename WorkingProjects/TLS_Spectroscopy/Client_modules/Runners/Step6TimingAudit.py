import datetime
import gc
import json
import time

import numpy as np
import h5py
import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import SingleShot1Q
from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSSpectroscopy as TLS
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_fit as fx
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import tee_log

P6 = {
    "shots": 2000,
    "dc_min": 0,
    "freq_step_mhz": 1,
    "Ts_us": 60.0,
    "min_ref_contrast": 0.05,
    "max_plot_t1_multiple": 20.0,
    "reset_mode": "feedback",
    "reset_threshold_raw": None,
    "reset_oper": "lower",
    "reset_ground_below": False,
    "reset_max_iters": 3,
}

SPAN_MHZ = 400.0
SS_SHOTS = 1000
SS_GROUND_THRESHOLD = 0.7


def banner(text):
    print()
    print("=" * 96)
    print(text)
    print("=" * 96)


def hms(seconds):
    seconds = float(seconds)
    if seconds < 90:
        return f"{seconds:.1f} s"
    if seconds < 5400:
        return f"{seconds / 60:.1f} min"
    return f"{seconds / 3600:.2f} h"


def solve_dc_max(span_mhz):
    f0 = fx.estimate_fit_frequency_ghz_array(TLS.FLUX_FIT_PARAMS,
                                             np.array([0.0]))[0]
    target = f0 - span_mhz / 1e3
    lo, hi = 0.0, 30000.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        f = fx.estimate_fit_frequency_ghz_array(TLS.FLUX_FIT_PARAMS,
                                                np.array([mid]))[0]
        if f > target:
            lo = mid
        else:
            hi = mid
    return int(round(hi)), f0, target


def run_ss(soc, soccfg):
    c = dict(BaseConfig)
    c["shots"] = c["reps"] = SS_SHOTS
    t0 = time.time()
    ss = SingleShot1Q(soc=soc, soccfg=soccfg, path=TLS.QUBIT,
                      outerFolder=outerFolder, suffix="TimingAudit_SS",
                      cfg=c, repeats=1,
                      confidence_threshold=SS_GROUND_THRESHOLD)
    ss.acquire(progress=False, plotDisp=False)
    dt = time.time() - t0
    plt.close("all")
    gc.collect()
    return ss, dt


def save_raw_h5(path, ss, exp, dc_vec, freq_ghz, p, timing):
    with h5py.File(path, "w") as f:
        g = f.create_group("ss_cal")
        for name in ("I_0", "Q_0", "I_1", "Q_1"):
            g.create_dataset(name, data=np.asarray(getattr(ss, name), dtype=float))
        g.attrs["calib_params"] = json.dumps(
            {k: float(v) for k, v in ss.calib_params.items()})
        g.attrs["fidelity"] = float(ss.max_F)
        g.attrs["confusion"] = json.dumps(
            np.asarray(ss.data["confusion"], dtype=float).tolist())
        g.attrs["shots"] = int(SS_SHOTS)
        g.attrs["prep"] = ("I_0/Q_0 are single shots with NO pulse (ground prep); "
                           "I_1/Q_1 follow one pi pulse.  Units are the host-side "
                           "rotated-and-scaled values discriminate_shots consumes.")

        t = f.create_group("t1")
        t.create_dataset("dc_vec", data=np.asarray(dc_vec, dtype=float))
        t.create_dataset("freq_ghz", data=np.asarray(freq_ghz, dtype=float))
        for key in ("T1_3pt_us", "T1_3pt_valid_mask", "P0", "P1", "Ps",
                    "ref_contrast_3pt", "pe_3pt"):
            if key in exp.data:
                t.create_dataset(key, data=np.asarray(exp.data[key], dtype=float))
        t.attrs["Ts_ns"] = int(exp.Ts_ns)
        t.attrs["Ts_effective_ns"] = float(exp.data.get("Ts_effective_ns",
                                                        exp.Ts_ns))
        t.attrs["shots"] = int(p["shots"])

        r = f.create_group("reset")
        r.attrs["params"] = json.dumps(
            {k: (v if isinstance(v, (int, float, str, bool)) else str(v))
             for k, v in p.items()
             if str(k).startswith("reset") or k == "rot_reset"}, default=str)
        r.attrs["rotated_in_use"] = bool(p.get("rot_reset"))

        m = f.create_group("timing")
        for k, v in timing.items():
            m.attrs[k] = float(v)


def main():
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    with tee_log.tee(f"Step6TimingAudit_{stamp}", outerFolder):
        soc, soccfg = makeProxy()
        banner("STEP 6 TIMING AUDIT -- one full 400 MHz pass, timed and fully saved")
        print("  This runs ONE complete 3-point pass over the 400 MHz production")
        print("  span, so the pass time is measured directly rather than")
        print("  extrapolated, and every output is written to disk:")
        print("    - the standard step-6 one-stop CSV and config JSON")
        print("    - a raw-data HDF5 holding the single-shot calibration shots")
        print("      (enough to reconstruct the calibration offline), the 3-point")
        print("      arrays, the reset parameters in use, and the timings")

        p = dict(P6)
        dc_max, f0, f_end = solve_dc_max(SPAN_MHZ)
        p["dc_max"] = dc_max
        dc_vec = TLS._step6_dc_vec(p)
        freq_ghz = fx.estimate_fit_frequency_ghz_array(
            TLS.FLUX_FIT_PARAMS, np.asarray(dc_vec, dtype=float))
        print(f"\n  {SPAN_MHZ:g} MHz span: f {f0:.4f} -> {f_end:.4f} GHz maps to "
              f"dc 0..{dc_max} DAC")
        print(f"  production dc vector: {len(dc_vec)} freq-uniform points at "
              f"{p['freq_step_mhz']:g} MHz steps")

        banner("MEASURE -- single-shot calibration (raw shots kept for the h5)")
        ss, t_ss = run_ss(soc, soccfg)
        print(f"  ss cal: {hms(t_ss)} (F = {ss.max_F:.4f}, {SS_SHOTS} shots per prep)")

        banner("MEASURE -- reset probe")
        p["_projected_points"] = len(dc_vec) * 3
        t0 = time.time()
        p = TLS._resolve_step6_reset(p, soc, soccfg, outerFolder)
        t_probe = time.time() - t0
        print(f"  probe + validation: {hms(t_probe)}")
        if not TLS.active_reset.uses_feedback(p.get("reset_mode")):
            print("  WARNING: probe fell back to PASSIVE; the pass below will run at")
            print("  2 ms pacing and its time will NOT represent a feedback run.")

        flux_tail = TLS._load_correction(None, outerFolder)
        base = TLS._t1_base_cfg(p, flux_tail, dc_vec)

        banner(f"MEASURE -- one full 3-point pass ({len(dc_vec)} dc points x "
               f"{p['shots']} shots)")
        series_start = datetime.datetime.now()
        run_start = series_start
        t0 = time.time()
        exp = TLS.T13PointVsFlux(
            soc=soc, soccfg=soccfg, path=TLS.QUBIT, outerFolder=outerFolder,
            suffix="TimingAudit_FullPass", cfg=dict(base),
            dc_vec=np.asarray(dc_vec, dtype=float),
            Ts_ns=int(round(p["Ts_us"] * 1e3)),
            shots=int(p["shots"]), calib_params=ss.calib_params,
            park_voltage=TLS.BASELINE_DC_OFFSET,
            min_ref_contrast=float(p.get("min_ref_contrast", 0.05)),
            max_plot_t1_multiple=p.get("max_plot_t1_multiple", 20.0),
            reset_mode=p.get("reset_mode", "passive"),
            flux_tail_compensation=flux_tail,
            repeat_metadata=TLS.build_wall_clock_repeat_metadata(
                run_start, series_start, 0),
            write_outputs=False)
        exp.acquire(progress=True)
        t_pass = time.time() - t0
        plt.close("all")
        gc.collect()
        valid = np.asarray(exp.data["T1_3pt_valid_mask"], dtype=float)
        print(f"  full pass: {hms(t_pass)} ({t_pass / len(dc_vec):.2f} s/dc); "
              f"{int(valid.sum())}/{len(dc_vec)} valid 3-point estimates")

        banner("SAVE -- standard step-6 outputs plus the raw-data h5")
        base_path = TLS._csv_base_from_pickle(exp.pname)
        try:
            exp.save_config()
            print(f"  config JSON saved alongside {base_path}")
        except Exception as exc:
            print(f"  config JSON not written ({exc}); the CSV is still complete")
        spec = TLS.get_wall_clock_repeat_spec(exp)
        full_spec = TLS.get_wall_clock_repeat_full_spec(exp) or {}
        run_entry = {
            "run_metadata": TLS.build_wall_clock_repeat_metadata(
                run_start, series_start, 0),
            "dc_vec": np.asarray(exp.dc_vec, dtype=float),
            "metric_column_name": spec["metric_column_name"],
            "metric_values": np.asarray(spec["metric_values"], dtype=float),
            "extra_metric_matrices": {
                key: np.asarray(values, dtype=float)
                for key, values in dict(spec.get("extra_metric_matrices",
                                                 {})).items()},
            "axes": full_spec.get("axes", {}),
            "scalar_columns": full_spec.get("scalar_columns", {}),
            "array_columns": full_spec.get("array_columns", {}),
        }
        csv_path = TLS.save_wall_clock_repeat_full_outputs(
            base_path, spec["file_tag"], [run_entry])
        print(f"  one-stop CSV: {csv_path}")

        h5_path = f"{base_path}_raw.h5"
        timing = {"t_ss_s": t_ss, "t_probe_s": t_probe, "t_pass_s": t_pass,
                  "n_dc": len(dc_vec), "span_mhz": SPAN_MHZ,
                  "shots": p["shots"]}
        save_raw_h5(h5_path, ss, exp, dc_vec, freq_ghz, p, timing)
        print(f"  raw-data h5:  {h5_path}")
        print("  h5 layout: ss_cal/{I_0,Q_0,I_1,Q_1 + calib/confusion attrs}, "
              "t1/{dc_vec, freq_ghz, T1_3pt_us, P0, P1, Ps, valid, contrast}, "
              "reset/{params}, timing/{...}")

        banner("TIMING SUMMARY")
        print(f"  ss cal              {hms(t_ss)}")
        print(f"  reset probe         {hms(t_probe)}")
        print(f"  full pass           {hms(t_pass)}  "
              f"({t_pass / len(dc_vec):.2f} s per dc point)")
        reprobes_per_hour = (60.0 / TLS.RESET_REPROBE_MIN
                             if TLS.RESET_REPROBE_MIN else 0.0)
        overhead = reprobes_per_hour * t_probe / 3600.0
        print(f"  wall-clock series   ~{3600.0 * (1 - overhead) / t_pass:.1f} "
              f"passes/hour ({TLS.RESET_REPROBE_MIN:g}-min re-probes cost "
              f"{100 * overhead:.1f}%)")
        banner("done -- the .txt log, CSV and h5 together are the complete record")


if __name__ == "__main__":
    main()
