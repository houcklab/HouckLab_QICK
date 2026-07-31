import csv
import datetime
import gc
import json
import os
import time

import h5py
import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mRoundTripRamsey import (
    RAMSEY_ARMS, RoundTripRamsey,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import (
    SingleShot1Q, discriminate_shots,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_fit as fx
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import tee_log
from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSSpectroscopy as TLS


P = {
    "shots": 500,
    "channel_shots": 250,
    "channel_rounds": 5,
    "dc_min": 0,
    "freq_step_mhz": 1,
    "Ts_us": 60.0,
    "flux_hold_us": 1.0,
    "min_ref_contrast": 0.05,
    "max_plot_t1_multiple": 20.0,
    "reset_mode": "feedback",
    "reset_threshold_raw": None,
    "reset_oper": "lower",
    "reset_ground_below": False,
    "reset_max_iters": 3,
}

SPAN_MHZ = 400.0
PARK_CAL_SHOTS = 500
PARK_GROUND_THRESHOLD = 0.7
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
    f0 = fx.estimate_fit_frequency_ghz_array(
        TLS.FLUX_FIT_PARAMS, np.array([0.0]))[0]
    target = f0 - float(span_mhz) / 1e3
    lo, hi = 0.0, 30000.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        f = fx.estimate_fit_frequency_ghz_array(
            TLS.FLUX_FIT_PARAMS, np.array([mid]))[0]
        if f > target:
            lo = mid
        else:
            hi = mid
    return int(round(hi)), f0, target


def run_park_ss(soc, soccfg):
    cfg = dict(BaseConfig)
    cfg["shots"] = cfg["reps"] = PARK_CAL_SHOTS
    t0 = time.time()
    ss = SingleShot1Q(
        soc=soc, soccfg=soccfg, path=TLS.QUBIT, outerFolder=outerFolder,
        suffix="RoundTripRamsey_SS_Park", cfg=cfg, repeats=1,
        confidence_threshold=PARK_GROUND_THRESHOLD)
    ss.acquire(progress=False, plotDisp=False)
    dt = time.time() - t0
    plt.close("all")
    return ss, dt


def run_channel_point(soc, soccfg, base, dc, p, calib_params, assignment_reference):
    cfg = dict(base)
    cfg["reset_mode"] = p.get("reset_mode", "passive")
    cfg["shots"] = cfg["reps"] = int(p["channel_shots"])
    t0 = time.time()
    exp = RoundTripRamsey(
        soc=soc, soccfg=soccfg, path=TLS.QUBIT, outerFolder=outerFolder,
        suffix="RoundTripRamsey_Point", cfg=cfg,
        ff_gain=float(dc), flux_hold_us=float(p["flux_hold_us"]),
        shots=int(p["channel_shots"]), rounds=int(p["channel_rounds"]),
        calib_params=calib_params,
        assignment_reference=assignment_reference,
        min_reference_contrast=float(p["min_ref_contrast"]), save=False)
    exp.acquire(progress=False, plotDisp=False)
    return exp, time.time() - t0


def run_t1_point(soc, soccfg, p, base, dc, calib_params):
    t0 = time.time()
    exp = TLS.T13PointVsFlux(
        soc=soc, soccfg=soccfg, path=TLS.QUBIT, outerFolder=outerFolder,
        suffix="RoundTripRamsey_T1_Point", cfg=dict(base),
        dc_vec=np.asarray([float(dc)]),
        Ts_ns=int(round(float(p["Ts_us"]) * 1e3)),
        shots=int(p["shots"]), calib_params=calib_params,
        park_voltage=TLS.BASELINE_DC_OFFSET,
        min_ref_contrast=float(p["min_ref_contrast"]),
        max_plot_t1_multiple=p.get("max_plot_t1_multiple", 20.0),
        reset_mode=p.get("reset_mode", "passive"),
        flux_tail_compensation=base.get("flux_tail_compensation"),
        repeat_metadata=None, write_outputs=False)
    exp.acquire(progress=False)
    result = {k: float(np.asarray(exp.data[k]).ravel()[0])
              for k in ("T1_3pt_us", "T1_3pt_valid_mask", "P0", "P1", "Ps",
                        "ref_contrast_3pt")}
    result["Ts_effective_ns"] = float(
        exp.data.get("Ts_effective_ns", exp.Ts_ns))
    plt.close("all")
    return result, time.time() - t0


def finite_unwrap(phase, valid):
    phase = np.asarray(phase, dtype=float)
    valid = np.asarray(valid, dtype=bool) & np.isfinite(phase)
    result = np.full_like(phase, np.nan)
    if not np.any(valid):
        return result
    index = np.arange(phase.size)
    filled = np.interp(index, index[valid], phase[valid])
    result[valid] = np.unwrap(filled)[valid]
    return result


def json_default(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return str(value)


def save_plot(base_path, freq_ghz, channel, t1):
    valid_t1 = t1["T1_3pt_valid_mask"] > 0.5
    valid_channel = channel["valid"] > 0.5
    inv_t1 = np.where(valid_t1 & (t1["T1_3pt_us"] > 0),
                      1.0 / t1["T1_3pt_us"], np.nan)
    phase_unwrapped = channel["coherence_phase_relative_unwrapped_rad"]
    fig, axes = plt.subplots(3, 2, figsize=(14, 12), constrained_layout=True)
    axes[0, 0].plot(freq_ghz, inv_t1, color="#0f766e", lw=0.9)
    axes[0, 0].set(ylabel="1/T1 (1/us)", title="Three-point relaxation loss")
    for key, label in (("P_g", "g -> Z"), ("P_e", "e -> Z"),
                       ("P_i", "+x -> I"), ("P_q", "+x -> Q")):
        axes[0, 1].plot(freq_ghz, channel[key], lw=0.8, label=label)
    axes[0, 1].set(ylabel="P(excited)", title="Four raw channel arms")
    axes[0, 1].legend(ncol=2)
    axes[1, 0].plot(freq_ghz, channel["ramsey_i"], lw=0.8, label="I")
    axes[1, 0].plot(freq_ghz, channel["ramsey_q"], lw=0.8, label="Q")
    axes[1, 0].axhline(0.0, color="black", lw=0.7)
    axes[1, 0].set(ylabel="Normalized quadrature", title="Complex round-trip response")
    axes[1, 0].legend()
    axes[1, 1].plot(freq_ghz, channel["coherence_relative_to_park"],
                    color="#7c3aed", lw=0.9)
    axes[1, 1].set(ylabel="|C| / |C_park|", title="Transverse coherence relative to park")
    axes[2, 0].plot(freq_ghz, phase_unwrapped, color="#c2410c", lw=0.9)
    axes[2, 0].set(xlabel="Ramped qubit frequency (GHz)",
                   ylabel="Unwrapped phase from park (rad)",
                   title="Round-trip coherence phase relative to park")
    axes[2, 1].plot(freq_ghz, channel["reference_contrast"],
                    lw=0.9, label="Channel e-g")
    axes[2, 1].plot(freq_ghz, t1["ref_contrast_3pt"],
                    lw=0.9, alpha=0.7, label="T1 P1-P0")
    axes[2, 1].set(xlabel="Ramped qubit frequency (GHz)", ylabel="Contrast",
                   title="Matched-reference validity")
    axes[2, 1].legend()
    for ax in axes.flat:
        ax.grid(True, alpha=0.2)
    fig.suptitle("Round-trip Ramsey channel map interleaved with Step 6 T1", fontsize=14)
    path = f"{base_path}.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path


def main():
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    with tee_log.tee(f"RoundTripRamseyAudit_{stamp}", outerFolder):
        soc, soccfg = makeProxy()
        banner("ROUND-TRIP RAMSEY CHANNEL MAP -- four park-pulse arms + 3-point T1 per DC")
        print(f"  g/e references and two Ramsey quadratures use {P['channel_shots']} shots "
              f"per arm in {P['channel_rounds']} balanced rounds.")
        print(f"  Every arm prepares at {float(BaseConfig['qubit_pi_freq']):.6f} MHz, "
              "ramps to the target, returns to park, and reads at park.")
        print(f"  The Ramsey arms use the configured park X90 gain "
              f"{int(BaseConfig['qubit_pi2_gain'])}; no ramp-frequency microwave pulse is used.")
        print("  Production Step 6 is unchanged.")

        p = dict(P)
        dc_max, f0, f_end = solve_dc_max(SPAN_MHZ)
        p["dc_max"] = dc_max
        dc_vec = np.asarray(TLS._step6_dc_vec(p), dtype=float)
        freq_ghz = fx.estimate_fit_frequency_ghz_array(TLS.FLUX_FIT_PARAMS, dc_vec)
        n_dc = len(dc_vec)
        print(f"\n  {SPAN_MHZ:g} MHz span: f {f0:.4f} -> {f_end:.4f} GHz maps to "
              f"dc 0..{dc_max} DAC ({n_dc} frequency-uniform points)")

        banner("MEASURE -- reset probe")
        projected_shots = n_dc * (
            3 * int(p["shots"]) + 4 * int(p["channel_shots"]))
        p["_projected_points"] = int(np.ceil(projected_shots / int(p["shots"])))
        t0 = time.time()
        p = TLS._resolve_step6_reset(p, soc, soccfg, outerFolder)
        t_probe = time.time() - t0
        print(f"  probe + validation: {hms(t_probe)}")

        flux_tail = TLS._load_correction(None, outerFolder)
        base = TLS._t1_base_cfg(p, flux_tail, dc_vec)
        base["reset_mode"] = p.get("reset_mode", "passive")
        base["three_point_ref_hold_us"] = float(p["flux_hold_us"])

        banner("MEASURE -- park IQ discriminator")
        park_ss, t_park_ss = run_park_ss(soc, soccfg)
        print(f"  park calibration: F {park_ss.max_F:.3f}, {hms(t_park_ss)}")
        assignment_reference = {
            "P_g": float(np.mean(discriminate_shots(
                park_ss.I_0, park_ss.Q_0, park_ss.calib_params))),
            "P_e": float(np.mean(discriminate_shots(
                park_ss.I_1, park_ss.Q_1, park_ss.calib_params))),
        }
        print(f"  fixed assignment reference: P_g={assignment_reference['P_g']:.3f}, "
              f"P_e={assignment_reference['P_e']:.3f}, "
              f"contrast={assignment_reference['P_e'] - assignment_reference['P_g']:.3f}")

        banner("MEASURE -- park four-arm Ramsey reference")
        park_channel, t_park_channel = run_channel_point(
            soc, soccfg, base, TLS.BASELINE_DC_OFFSET, p, park_ss.calib_params,
            assignment_reference)
        pm = park_channel.metrics
        print(f"  P_g={pm['P_g']:.3f}, P_e={pm['P_e']:.3f}, "
              f"I={pm['ramsey_i']:+.3f}, Q={pm['ramsey_q']:+.3f}, "
              f"|C|={pm['coherence_magnitude']:.3f}, "
              f"contrast={pm['reference_contrast']:.3f}, {hms(t_park_channel)}")
        if not pm["valid"]:
            raise RuntimeError("fixed park assignment reference has insufficient contrast")
        if not pm["local_reference_valid"]:
            raise RuntimeError("park four-arm g/e reference has insufficient contrast; verify qubit_pi_gain")
        if not np.isfinite(pm["coherence_magnitude"]) or pm["coherence_magnitude"] < 0.35:
            raise RuntimeError("park four-arm reference has insufficient Ramsey coherence; verify qubit_pi2_gain")
        print(f"  park coherence phase {pm['coherence_phase_rad']:+.3f} rad is the "
              "relative phase origin for the scan.")

        channel_keys = (
            "P_g", "P_e", "P_i", "P_q", "reference_contrast", "ramsey_i",
            "local_reference_valid", "assignment_P_g", "assignment_P_e",
            "assignment_contrast", "population_g", "population_e", "ramsey_q",
            "coherence_magnitude", "coherence_phase_rad", "valid",
            "keep_fraction_g", "keep_fraction_e", "keep_fraction_i", "keep_fraction_q",
        )
        channel = {key: np.full(n_dc, np.nan) for key in channel_keys}
        raw = {
            f"{prefix}_{arm}": np.full((n_dc, int(p["channel_shots"])), np.nan)
            for arm in RAMSEY_ARMS
            for prefix in ("herald_I", "herald_Q", "I", "Q")
        }
        t1_keys = ("T1_3pt_us", "T1_3pt_valid_mask", "P0", "P1", "Ps",
                   "ref_contrast_3pt")
        t1 = {key: np.full(n_dc, np.nan) for key in t1_keys}
        t_channel = np.zeros(n_dc)
        t_t1 = np.zeros(n_dc)
        Ts_eff_ns = float(p["Ts_us"] * 1e3)

        banner(f"MEASURE -- {n_dc} x (four-arm channel point + 3-point T1)")
        series_t0 = time.time()
        for index, dc in enumerate(dc_vec):
            exp, t_channel[index] = run_channel_point(
                soc, soccfg, base, dc, p, park_ss.calib_params,
                assignment_reference)
            for key in channel:
                channel[key][index] = float(exp.metrics[key])
            for arm in RAMSEY_ARMS:
                values = exp.raw[arm]
                raw[f"herald_I_{arm}"][index] = values["herald_i"]
                raw[f"herald_Q_{arm}"][index] = values["herald_q"]
                raw[f"I_{arm}"][index] = values["i"]
                raw[f"Q_{arm}"][index] = values["q"]
            result, t_t1[index] = run_t1_point(
                soc, soccfg, p, base, dc, park_ss.calib_params)
            for key in t1:
                t1[key][index] = result[key]
            Ts_eff_ns = result["Ts_effective_ns"]
            if (index + 1) % PROGRESS_EVERY == 0 or index == n_dc - 1:
                elapsed = time.time() - series_t0
                eta = elapsed / (index + 1) * (n_dc - index - 1)
                print(f"  {index + 1:>4}/{n_dc}  f {freq_ghz[index]:.4f} GHz  "
                      f"|C| {channel['coherence_magnitude'][index]:.3f}  "
                      f"phase {channel['coherence_phase_rad'][index]:+.2f}  "
                      f"T1 {t1['T1_3pt_us'][index]:7.1f} us  "
                      f"[{hms(elapsed)} elapsed, ETA {hms(eta)}]", flush=True)
            if index % 50 == 0:
                gc.collect()
        t_total = time.time() - series_t0
        channel["coherence_relative_to_park"] = (
            channel["coherence_magnitude"] / pm["coherence_magnitude"])
        channel["coherence_phase_relative_rad"] = np.angle(np.exp(
            1j * (channel["coherence_phase_rad"] - pm["coherence_phase_rad"])))
        channel["coherence_phase_relative_unwrapped_rad"] = finite_unwrap(
            channel["coherence_phase_relative_rad"], channel["valid"] > 0.5)

        banner("SAVE -- CSV, overview, and complete raw H5")
        stamp_dir = datetime.datetime.now()
        base_path = TLS._csv_base_from_pickle(
            f"{outerFolder}/{TLS.QUBIT}/{TLS.QUBIT}_{stamp_dir:%Y_%m_%d}/"
            f"{TLS.QUBIT}_{stamp_dir:%H_%M_%S}_RoundTripRamseyAudit")
        os.makedirs(os.path.dirname(base_path), exist_ok=True)
        valid_t1 = t1["T1_3pt_valid_mask"] > 0.5
        inv_t1 = np.where(valid_t1 & (t1["T1_3pt_us"] > 0),
                          1.0 / t1["T1_3pt_us"], np.nan)
        phase_unwrapped = finite_unwrap(
            channel["coherence_phase_rad"], channel["valid"] > 0.5)
        csv_path = f"{base_path}.csv"
        fields = (["scan_index", "dc_target_V", "freq_ghz", "Ts_ns",
                   "inv_T1_3pt_per_us"] + list(t1) + list(channel)
                  + ["coherence_phase_unwrapped_rad", "t_channel_s", "t_t1_s"])
        with open(csv_path, "w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for index in range(n_dc):
                row = {
                    "scan_index": index,
                    "dc_target_V": dc_vec[index],
                    "freq_ghz": freq_ghz[index],
                    "Ts_ns": Ts_eff_ns,
                    "inv_T1_3pt_per_us": inv_t1[index],
                    "coherence_phase_unwrapped_rad": phase_unwrapped[index],
                    "t_channel_s": t_channel[index],
                    "t_t1_s": t_t1[index],
                }
                for key in t1:
                    row[key] = t1[key][index]
                for key in channel:
                    row[key] = channel[key][index]
                writer.writerow(row)

        h5_path = f"{base_path}_raw.h5"
        with h5py.File(h5_path, "w") as handle:
            handle.attrs["schema"] = "round_trip_ramsey_audit_v1"
            handle.attrs["runner_settings"] = json.dumps(p, default=json_default)
            handle.attrs["base_config"] = json.dumps(base, default=json_default)
            handle.attrs["flux_fit_params"] = json.dumps(
                TLS.FLUX_FIT_PARAMS, default=json_default)
            park = handle.create_group("park_cal")
            for key in ("I_0", "Q_0", "I_1", "Q_1"):
                park.create_dataset(key, data=np.asarray(getattr(park_ss, key), dtype=float))
            park.attrs["calib_params"] = json.dumps(park_ss.calib_params)
            park.attrs["fidelity"] = float(park_ss.max_F)
            park.attrs["assignment_reference"] = json.dumps(assignment_reference)
            pref = handle.create_group("park_channel_reference")
            for arm in RAMSEY_ARMS:
                for key, values in park_channel.raw[arm].items():
                    label = {"herald_i": "herald_I", "herald_q": "herald_Q",
                             "i": "I", "q": "Q"}[key]
                    pref.create_dataset(f"{label}_{arm}", data=np.asarray(values, dtype=float))
            pref.attrs["metrics"] = json.dumps(park_channel.metrics)
            chan = handle.create_group("channel")
            chan.create_dataset("dc_vec", data=dc_vec)
            chan.create_dataset("freq_ghz", data=freq_ghz)
            for key, values in channel.items():
                chan.create_dataset(key, data=values)
            chan.create_dataset("coherence_phase_unwrapped_rad", data=phase_unwrapped)
            for key, values in raw.items():
                chan.create_dataset(key, data=values)
            chan.attrs["shots_per_arm"] = int(p["channel_shots"])
            chan.attrs["rounds"] = int(p["channel_rounds"])
            chan.attrs["flux_hold_us"] = float(p["flux_hold_us"])
            chan.attrs["park_pi_freq_mhz"] = float(BaseConfig["qubit_pi_freq"])
            chan.attrs["park_pi_gain"] = int(BaseConfig["qubit_pi_gain"])
            chan.attrs["park_pi2_gain"] = int(BaseConfig["qubit_pi2_gain"])
            chan.attrs["assignment_reference"] = json.dumps(assignment_reference)
            chan.attrs["quadrature_normalization"] = (
                "2*(P_arm-park_assignment_P_g)/(park_assignment_P_e-"
                "park_assignment_P_g)-1")
            chan.attrs["arm_meaning"] = json.dumps({
                "g": "ground preparation and Z readout",
                "e": "X180 preparation and Z readout",
                "i": "X90 preparation and X90 phase-0 analysis",
                "q": "X90 preparation and X90 phase-90 analysis",
            })
            tg = handle.create_group("t1")
            tg.create_dataset("dc_vec", data=dc_vec)
            tg.create_dataset("freq_ghz", data=freq_ghz)
            for key, values in t1.items():
                tg.create_dataset(key, data=values)
            tg.attrs["Ts_ns"] = int(round(float(p["Ts_us"]) * 1e3))
            tg.attrs["Ts_effective_ns"] = float(Ts_eff_ns)
            tg.attrs["shots"] = int(p["shots"])
            reset = handle.create_group("reset")
            reset.attrs["params"] = json.dumps(
                {key: (value if isinstance(value, (int, float, str, bool)) else str(value))
                 for key, value in p.items()
                 if str(key).startswith("reset") or key == "rot_reset"}, default=str)
            reset.attrs["rotated_in_use"] = bool(p.get("rot_reset"))
            timing = handle.create_group("timing")
            timing.create_dataset("t_channel_s", data=t_channel)
            timing.create_dataset("t_t1_s", data=t_t1)
            timing.attrs["t_probe_s"] = float(t_probe)
            timing.attrs["t_park_ss_s"] = float(t_park_ss)
            timing.attrs["t_park_channel_s"] = float(t_park_channel)
            timing.attrs["t_total_s"] = float(t_total)
            timing.attrs["n_dc"] = int(n_dc)
            timing.attrs["span_mhz"] = float(SPAN_MHZ)
        plot_path = save_plot(base_path, freq_ghz, channel, t1)

        valid_channel = int(np.sum(channel["valid"] > 0.5))
        print(f"  CSV: {csv_path}")
        print(f"  raw H5: {h5_path}")
        print(f"  overview: {plot_path}")
        print(f"\n  pass complete: {hms(t_total)} ({t_total / n_dc:.2f} s/DC)")
        print(f"  valid channel points: {valid_channel}/{n_dc}")
        print(f"  valid T1 points: {int(np.sum(valid_t1))}/{n_dc}")
        print(f"  channel total: {hms(np.sum(t_channel))}")
        print(f"  T1 total: {hms(np.sum(t_t1))}")
        banner("done")


if __name__ == "__main__":
    main()
