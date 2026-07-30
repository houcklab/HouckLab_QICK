import csv
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
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import (
    SingleShot1Q, SingleShotFluxRamp)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSSpectroscopy as TLS
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_fit as fx
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import tee_log

P6 = {
    "shots": 500,
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
    "ss_flux_hold_us": 1.0,
}

SPAN_MHZ = 400.0
SS_SHOTS_PER_DC = 500
SS_GROUND_THRESHOLD = 0.7
PROGRESS_EVERY = 25


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


def run_park_ss(soc, soccfg, tag):
    c = dict(BaseConfig)
    c["shots"] = c["reps"] = SS_SHOTS_PER_DC
    t0 = time.time()
    ss = SingleShot1Q(
        soc=soc, soccfg=soccfg, path=TLS.QUBIT,
        outerFolder=outerFolder, suffix=tag,
        cfg=c, repeats=1,
        confidence_threshold=SS_GROUND_THRESHOLD)
    ss.acquire(progress=False, plotDisp=False)
    dt = time.time() - t0
    plt.close("all")
    return ss, dt


def run_ss_flux_ramp(soc, soccfg, base, dc, p, tag):
    c = dict(base)
    c["shots"] = c["reps"] = SS_SHOTS_PER_DC
    t0 = time.time()
    ss = SingleShotFluxRamp(
        soc=soc, soccfg=soccfg, path=TLS.QUBIT,
        outerFolder=outerFolder, suffix=tag,
        cfg=c, repeats=1,
        confidence_threshold=SS_GROUND_THRESHOLD,
        ff_gain=float(dc), flux_hold_us=float(p.get("ss_flux_hold_us", 1.0)))
    ss.acquire(progress=False, plotDisp=False)
    dt = time.time() - t0
    plt.close("all")
    return ss, dt


def run_t1_point(soc, soccfg, p, base, dc, calib_params, tag):
    t0 = time.time()
    exp = TLS.T13PointVsFlux(
        soc=soc, soccfg=soccfg, path=TLS.QUBIT, outerFolder=outerFolder,
        suffix=tag, cfg=dict(base),
        dc_vec=np.asarray([float(dc)]),
        Ts_ns=int(round(p["Ts_us"] * 1e3)),
        shots=int(p["shots"]), calib_params=calib_params,
        park_voltage=TLS.BASELINE_DC_OFFSET,
        min_ref_contrast=float(p.get("min_ref_contrast", 0.05)),
        max_plot_t1_multiple=p.get("max_plot_t1_multiple", 20.0),
        reset_mode=p.get("reset_mode", "passive"),
        flux_tail_compensation=base.get("flux_tail_compensation"),
        repeat_metadata=None, write_outputs=False)
    exp.acquire(progress=False)
    dt = time.time() - t0
    out = {k: float(np.asarray(exp.data[k]).ravel()[0])
           for k in ("T1_3pt_us", "T1_3pt_valid_mask", "P0", "P1", "Ps",
                     "ref_contrast_3pt")}
    out["Ts_effective_ns"] = float(exp.data.get("Ts_effective_ns", exp.Ts_ns))
    plt.close("all")
    return out, dt


def main():
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    with tee_log.tee(f"Step6TimingAudit_{stamp}", outerFolder):
        soc, soccfg = makeProxy()
        banner("STEP 6 TIMING AUDIT -- per-dc interleave: 500-shot flux-ramped IQ blobs + "
               "500-shot 3-point T1 at EVERY dc point")
        print("  Structure per dc point:")
        print(f"    1. prepare |g>/|e> at park, ramp to that dc, hold, ramp back, and "
              f"retain the IQ blobs ({SS_SHOTS_PER_DC} shots per prep)")
        print(f"    2. 3-point T1 at that dc ({P6['shots']} shots) discriminated "
              f"with one clean park calibration")
        print("  The per-dc fitted blob metrics describe the post-interaction clouds;")
        print("  they are not used as T1 discriminator settings.  Every raw shot is")
        print("  kept so the h5 can correlate cloud weights and shapes with TLS spikes.")
        print("  The reset is probed once up front (this is still the testing script;")
        print("  production step 6 is unchanged).")

        p = dict(P6)
        dc_max, f0, f_end = solve_dc_max(SPAN_MHZ)
        p["dc_max"] = dc_max
        dc_vec = np.asarray(TLS._step6_dc_vec(p), dtype=float)
        freq_ghz = fx.estimate_fit_frequency_ghz_array(TLS.FLUX_FIT_PARAMS, dc_vec)
        n_dc = len(dc_vec)
        print(f"\n  {SPAN_MHZ:g} MHz span: f {f0:.4f} -> {f_end:.4f} GHz maps to "
              f"dc 0..{dc_max} DAC ({n_dc} freq-uniform points)")

        banner("MEASURE -- reset probe (once)")
        p["_projected_points"] = n_dc * 5 + 2
        t0 = time.time()
        p = TLS._resolve_step6_reset(p, soc, soccfg, outerFolder)
        t_probe = time.time() - t0
        print(f"  probe + validation: {hms(t_probe)}")
        if not TLS.active_reset.uses_feedback(p.get("reset_mode")):
            print("  WARNING: probe fell back to PASSIVE; per-dc pacing below will "
                  "not represent a feedback run.")

        flux_tail = TLS._load_correction(None, outerFolder)
        base = TLS._t1_base_cfg(p, flux_tail, dc_vec)
        base["three_point_ref_hold_us"] = float(p["ss_flux_hold_us"])

        banner("MEASURE -- clean park IQ calibration")
        park_ss, t_park_ss = run_park_ss(
            soc, soccfg, "TimingAudit_SS_Park_Reference")
        print(f"  park calibration: F {park_ss.max_F:.3f}, {hms(t_park_ss)}")

        banner(f"MEASURE -- {n_dc} x (flux-ramped IQ blobs + 3-point T1)")
        ss_raw = {k: np.zeros((n_dc, SS_SHOTS_PER_DC)) for k in
                  ("I_0", "Q_0", "I_1", "Q_1")}
        ss_cols = {k: np.zeros(n_dc) for k in
                   ("ss_F", "ss_threshold", "ss_theta", "ss_ground_threshold",
                    "ss_ff_gain", "ss_park_pi_freq_mhz", "ss_qubit_pi_gain",
                    "ss_flux_hold_us")}
        t1_cols = {k: np.zeros(n_dc) for k in
                   ("T1_3pt_us", "T1_3pt_valid_mask", "P0", "P1", "Ps",
                    "ref_contrast_3pt")}
        t_ss = np.zeros(n_dc)
        t_t1 = np.zeros(n_dc)
        Ts_eff_ns = float(p["Ts_us"] * 1e3)
        series_t0 = time.time()
        for i, dc in enumerate(dc_vec):
            ss, t_ss[i] = run_ss_flux_ramp(
                soc, soccfg, base, dc, p, f"TimingAudit_SS_Flux_{i:03d}")
            for k in ss_raw:
                v = np.asarray(getattr(ss, k), dtype=float).ravel()
                ss_raw[k][i, :min(len(v), SS_SHOTS_PER_DC)] = \
                    v[:SS_SHOTS_PER_DC]
            ss_cols["ss_F"][i] = float(ss.max_F)
            ss_cols["ss_threshold"][i] = float(ss.calib_params["threshold"])
            ss_cols["ss_theta"][i] = float(ss.calib_params["read_theta"])
            ss_cols["ss_ground_threshold"][i] = float(
                ss.calib_params.get("ground_threshold", np.nan))
            ss_cols["ss_ff_gain"][i] = float(
                ss.calib_params.get("flux_ramp_ff_gain", dc))
            ss_cols["ss_park_pi_freq_mhz"][i] = float(
                ss.calib_params.get(
                    "flux_ramp_park_pi_freq_mhz", BaseConfig["qubit_pi_freq"]))
            ss_cols["ss_qubit_pi_gain"][i] = float(
                ss.calib_params.get("flux_ramp_pi_gain", BaseConfig["qubit_pi_gain"]))
            ss_cols["ss_flux_hold_us"][i] = float(
                ss.calib_params.get("flux_ramp_hold_us", p["ss_flux_hold_us"]))
            out, t_t1[i] = run_t1_point(soc, soccfg, p, base, dc,
                                        park_ss.calib_params,
                                        f"TimingAudit_T1_{i:03d}")
            for k in t1_cols:
                t1_cols[k][i] = out[k]
            Ts_eff_ns = out["Ts_effective_ns"]
            if (i + 1) % PROGRESS_EVERY == 0 or i == n_dc - 1:
                el = time.time() - series_t0
                eta = el / (i + 1) * (n_dc - i - 1)
                print(f"  {i + 1:>4}/{n_dc}  f {freq_ghz[i]:.4f} GHz  "
                      f"F {ss_cols['ss_F'][i]:.3f}  "
                      f"T1 {t1_cols['T1_3pt_us'][i]:7.1f} us  "
                      f"valid {int(t1_cols['T1_3pt_valid_mask'][i])}  "
                      f"[{hms(el)} elapsed, ETA {hms(eta)}]", flush=True)
            if i % 50 == 0:
                gc.collect()
        t_total = time.time() - series_t0
        valid = t1_cols["T1_3pt_valid_mask"] > 0.5
        print(f"\n  per-dc pass complete: {hms(t_total)} "
              f"({t_total / n_dc:.2f} s/dc); {int(valid.sum())}/{n_dc} valid")
        print(f"  per-dc split: ss cal median {np.median(t_ss):.2f} s, "
              f"3-point T1 median {np.median(t_t1):.2f} s")

        banner("SAVE -- per-dc CSV and raw-data h5")
        stamp_dir = datetime.datetime.now()
        base_path = TLS._csv_base_from_pickle(
            f"{outerFolder}/{TLS.QUBIT}/{TLS.QUBIT}_{stamp_dir:%Y_%m_%d}/"
            f"{TLS.QUBIT}_{stamp_dir:%H_%M_%S}_TimingAudit_PerDC")
        csv_path = f"{base_path}.csv"
        fieldnames = (["scan_index", "dc_target_V", "freq_ghz", "Ts_ns",
                       "inv_T1_3pt_per_us"]
                      + list(t1_cols.keys()) + list(ss_cols.keys())
                      + ["t_ss_s", "t_t1_s"])
        with open(csv_path, "w", newline="") as fcsv:
            w = csv.DictWriter(fcsv, fieldnames=fieldnames)
            w.writeheader()
            for i in range(n_dc):
                row = {"scan_index": i, "dc_target_V": dc_vec[i],
                       "freq_ghz": freq_ghz[i], "Ts_ns": Ts_eff_ns,
                       "inv_T1_3pt_per_us":
                           (1.0 / t1_cols["T1_3pt_us"][i]
                            if valid[i] and t1_cols["T1_3pt_us"][i] > 0
                            else float("nan")),
                       "t_ss_s": t_ss[i], "t_t1_s": t_t1[i]}
                for k in t1_cols:
                    row[k] = t1_cols[k][i]
                for k in ss_cols:
                    row[k] = ss_cols[k][i]
                w.writerow(row)
        print(f"  per-dc CSV: {csv_path}")

        h5_path = f"{base_path}_raw.h5"
        with h5py.File(h5_path, "w") as f:
            pcal = f.create_group("park_cal")
            for k in ("I_0", "Q_0", "I_1", "Q_1"):
                pcal.create_dataset(k, data=np.asarray(getattr(park_ss, k), dtype=float))
            pcal.attrs["calib_params"] = json.dumps(park_ss.calib_params)
            pcal.attrs["fidelity"] = float(park_ss.max_F)
            pcal.attrs["role"] = "fixed discriminator used for every T1 point"
            g = f.create_group("ss_cal")
            g.create_dataset("dc_vec", data=dc_vec)
            g.create_dataset("freq_ghz", data=np.asarray(freq_ghz, dtype=float))
            for k, v in ss_raw.items():
                g.create_dataset(k, data=v)
            for k, v in ss_cols.items():
                g.create_dataset(k, data=v)
            g.attrs["shots_per_prep"] = SS_SHOTS_PER_DC
            g.attrs["flux_hold_us"] = float(p.get("ss_flux_hold_us", 1.0))
            g.attrs["qubit_pi_gain"] = int(BaseConfig["qubit_pi_gain"])
            g.attrs["metrics_role"] = "post-interaction blob descriptors"
            g.attrs["layout"] = ("2-D arrays [n_dc, shots]: row i is the "
                                 "flux-ramped IQ acquisition taken immediately before "
                                 "the 3-point T1 at dc_vec[i].  Both preparations "
                                 "use the calibrated park pulse, ramp to dc_vec[i], "
                                 "hold, and ramp back before the park readout.")
            t = f.create_group("t1")
            t.create_dataset("dc_vec", data=dc_vec)
            t.create_dataset("freq_ghz", data=np.asarray(freq_ghz, dtype=float))
            for k, v in t1_cols.items():
                t.create_dataset(k, data=v)
            t.attrs["Ts_ns"] = int(round(p["Ts_us"] * 1e3))
            t.attrs["Ts_effective_ns"] = float(Ts_eff_ns)
            t.attrs["shots"] = int(p["shots"])
            r = f.create_group("reset")
            r.attrs["params"] = json.dumps(
                {k: (v if isinstance(v, (int, float, str, bool)) else str(v))
                 for k, v in p.items()
                 if str(k).startswith("reset") or k == "rot_reset"}, default=str)
            r.attrs["rotated_in_use"] = bool(p.get("rot_reset"))
            m = f.create_group("timing")
            m.create_dataset("t_ss_s", data=t_ss)
            m.create_dataset("t_t1_s", data=t_t1)
            m.attrs["t_probe_s"] = float(t_probe)
            m.attrs["t_park_ss_s"] = float(t_park_ss)
            m.attrs["t_total_s"] = float(t_total)
            m.attrs["n_dc"] = int(n_dc)
            m.attrs["span_mhz"] = float(SPAN_MHZ)
        print(f"  raw-data h5: {h5_path}")

        banner("TIMING SUMMARY")
        print(f"  reset probe (once)   {hms(t_probe)}")
        print(f"  park ss cal (once)   {hms(t_park_ss)}")
        print(f"  ss cal per dc        {np.median(t_ss):.2f} s median "
              f"({hms(float(np.sum(t_ss)))} total)")
        print(f"  3-point T1 per dc    {np.median(t_t1):.2f} s median "
              f"({hms(float(np.sum(t_t1)))} total)")
        print(f"  full per-dc pass     {hms(t_total)}  "
              f"({t_total / n_dc:.2f} s per dc point)")
        reprobes_per_hour = (60.0 / TLS.RESET_REPROBE_MIN
                             if TLS.RESET_REPROBE_MIN else 0.0)
        overhead = reprobes_per_hour * t_probe / 3600.0
        print(f"  wall-clock series    ~{3600.0 * (1 - overhead) / t_total:.1f} "
              f"passes/hour ({TLS.RESET_REPROBE_MIN:g}-min re-probes cost "
              f"{100 * overhead:.1f}%)")
        banner("done -- the .txt log, CSV and h5 together are the complete record")


if __name__ == "__main__":
    main()
