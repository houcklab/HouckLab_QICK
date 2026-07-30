import datetime
import gc
import time

import numpy as np
import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import SingleShot1Q
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mTransmission import Transmission
from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSSpectroscopy as TLS
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import tee_log

P6 = {
    "shots": 2000,
    "dc_min": 0,
    "dc_max": 15000,
    "dc_step": 60,
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

P_TRANSMISSION = {
    "shots": 500,
    "freq_start_mhz": 7248,
    "freq_stop_mhz": 7250,
    "freq_points": 201,
    "spec_amp": 2000,
    "spec_len_us": 15,
}

SS_SHOTS = 1000
SS_GROUND_THRESHOLD = 0.7
SAMPLE_DC_COUNTS = [4, 12]
TIMING_REPS = 2


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


def time_ss(soc, soccfg):
    times = []
    calib = None
    for k in range(TIMING_REPS):
        c = dict(BaseConfig)
        c["shots"] = c["reps"] = SS_SHOTS
        t0 = time.time()
        ss = SingleShot1Q(soc=soc, soccfg=soccfg, path=TLS.QUBIT,
                          outerFolder=outerFolder, suffix="TimingAudit_SS",
                          cfg=c, repeats=1,
                          confidence_threshold=SS_GROUND_THRESHOLD)
        ss.acquire(progress=False, plotDisp=False)
        times.append(time.time() - t0)
        calib = ss.calib_params
        plt.close("all")
        gc.collect()
        print(f"  ss cal run {k + 1}: {hms(times[-1])} (F = {ss.max_F:.4f})",
              flush=True)
    return float(np.mean(times)), calib


def time_transmission(soc, soccfg):
    p = P_TRANSMISSION
    f_vec = np.linspace(float(p["freq_start_mhz"]), float(p["freq_stop_mhz"]),
                        int(p["freq_points"]))
    times = []
    for k in range(TIMING_REPS):
        cfg = dict(BaseConfig)
        cfg["shots"] = cfg["reps"] = int(p["shots"])
        cfg["relax_delay"] = 50
        cfg["read_pulse_gain"] = int(p["spec_amp"])
        cfg["read_length"] = float(p["spec_len_us"])
        cfg["ff_gain"] = 0
        cfg["ff_hold_gain"] = 0
        cfg["reset_mode"] = "passive"
        t0 = time.time()
        exp = Transmission(soc=soc, soccfg=soccfg, path=TLS.QUBIT,
                           outerFolder=outerFolder,
                           suffix="TimingAudit_Transmission", cfg=cfg, f_vec=f_vec)
        exp.acquire(progress=False, plotDisp=False)
        times.append(time.time() - t0)
        plt.close("all")
        gc.collect()
        print(f"  transmission run {k + 1}: {hms(times[-1])} "
              f"({p['freq_points']} freqs x {p['shots']} shots, "
              f"{p['spec_len_us']:g} us pulses)", flush=True)
    return float(np.mean(times))


def time_t1_sample(soc, soccfg, p, flux_tail, calib_params, dc_sub, tag):
    base = TLS._t1_base_cfg(p, flux_tail, dc_sub)
    t0 = time.time()
    exp = TLS.T13PointVsFlux(
        soc=soc, soccfg=soccfg, path=TLS.QUBIT, outerFolder=outerFolder,
        suffix=f"TimingAudit_{tag}", cfg=dict(base),
        dc_vec=dc_sub, Ts_ns=int(round(p["Ts_us"] * 1e3)),
        shots=int(p["shots"]), calib_params=calib_params,
        park_voltage=TLS.BASELINE_DC_OFFSET,
        min_ref_contrast=float(p.get("min_ref_contrast", 0.05)),
        max_plot_t1_multiple=p.get("max_plot_t1_multiple", 20.0),
        reset_mode=p.get("reset_mode", "passive"),
        flux_tail_compensation=flux_tail,
        repeat_metadata=None, write_outputs=False)
    exp.acquire(progress=True)
    dt = time.time() - t0
    plt.close("all")
    gc.collect()
    return dt


def main():
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    with tee_log.tee(f"Step6TimingAudit_{stamp}", outerFolder):
        soc, soccfg = makeProxy()
        banner("STEP 6 TIMING AUDIT -- how long does one pass actually take?")
        print("  Nothing here is estimated from theory: every building block is")
        print("  measured on this hardware right now, and the full-scan numbers are")
        print("  extrapolated from a two-size sample of the REAL dc vector, which")
        print("  separates the per-dc cost from the per-pass fixed overhead.")
        print("  Scenario A: the 3-point T1 pass exactly as P6_3PT_T1 configures it.")
        print(f"  Scenario B: the same pass plus, at EVERY dc point, a {SS_SHOTS}-shot")
        print(f"  single-shot calibration and a {P_TRANSMISSION['freq_points']}-point "
              f"resonator transmission")
        print(f"  ({P_TRANSMISSION['shots']} shots, "
              f"{P_TRANSMISSION['spec_len_us']:g} us pulses).")

        p = dict(P6)
        dc_full = TLS._step6_dc_vec(p)
        n_full = len(dc_full)
        print(f"\n  production dc vector: {n_full} points, "
              f"{dc_full[0]:.0f}..{dc_full[-1]:.0f} DAC "
              f"(freq-uniform at {p['freq_step_mhz']} MHz/step over "
              f"dc {p['dc_min']}..{p['dc_max']})")

        banner("MEASURE -- single-shot calibration")
        t_ss, calib_params = time_ss(soc, soccfg)
        print(f"  mean: {hms(t_ss)}")

        banner("MEASURE -- reset probe (runs once per pass-start and every "
               f"{TLS.RESET_REPROBE_MIN:g} min in a series)")
        p["_projected_points"] = n_full * 3
        t0 = time.time()
        p = TLS._resolve_step6_reset(p, soc, soccfg, outerFolder)
        t_probe = time.time() - t0
        print(f"  probe + validation: {hms(t_probe)}")
        if not TLS.active_reset.uses_feedback(p.get("reset_mode")):
            print("  WARNING: the probe fell back to PASSIVE (2 ms relax).  The T1")
            print("  sample timings below will reflect passive pacing and the")
            print("  extrapolation will NOT match a feedback-reset production run.")

        flux_tail = TLS._load_correction(None, outerFolder)

        banner("MEASURE -- 3-point T1 pass on two sample sizes of the real dc vector")
        sample_times = []
        for n in SAMPLE_DC_COUNTS:
            idx = np.unique(np.linspace(0, n_full - 1, int(n)).astype(int))
            dc_sub = np.asarray(dc_full, dtype=float)[idx]
            dt = time_t1_sample(soc, soccfg, p, flux_tail, calib_params, dc_sub,
                                f"T1x{len(dc_sub)}")
            sample_times.append((len(dc_sub), dt))
            print(f"  {len(dc_sub):>3} dc points: {hms(dt)} "
                  f"({dt / len(dc_sub):.2f} s/dc raw)", flush=True)
        (n1, t1), (n2, t2) = sample_times[0], sample_times[-1]
        per_dc = (t2 - t1) / max(n2 - n1, 1)
        fixed = max(t1 - per_dc * n1, 0.0)
        print(f"  -> per-dc T1 cost {per_dc:.2f} s, per-pass fixed overhead "
              f"{hms(fixed)}")
        print("  (the fixed part is program builds, waveform loads and the class's")
        print("  own setup; it is paid once per pass, not per dc)")

        banner("MEASURE -- per-dc extras for scenario B")
        t_trans = time_transmission(soc, soccfg)
        print(f"  transmission mean: {hms(t_trans)}")
        print(f"  ss cal mean (from above): {hms(t_ss)}")
        extra_per_dc = t_ss + t_trans

        banner("EXTRAPOLATION -- the numbers you asked for")
        pass_a = fixed + per_dc * n_full
        total_a = t_probe + t_ss + pass_a
        print(f"  SCENARIO A ({n_full} dc points, 3-point T1 only):")
        print(f"    one pass (T1 sweep itself)          {hms(pass_a)}")
        print(f"    first pass incl. probe + one ss cal {hms(total_a)}")
        reprobes_per_hour = (60.0 / TLS.RESET_REPROBE_MIN
                             if TLS.RESET_REPROBE_MIN else 0.0)
        overhead_frac = (reprobes_per_hour * t_probe) / 3600.0
        print(f"    wall-clock series: ~{3600.0 * (1 - overhead_frac) / pass_a:.1f} "
              f"passes/hour after re-probe overhead "
              f"({TLS.RESET_REPROBE_MIN:g}-min cadence costs "
              f"{100 * overhead_frac:.1f}% of wall time)")
        print(f"\n  SCENARIO B (per dc: T1 + {SS_SHOTS}-shot ss cal + transmission):")
        print(f"    per-dc cost: {per_dc:.2f} s (T1) + {t_ss:.2f} s (ss) + "
              f"{t_trans:.2f} s (transmission) = {per_dc + extra_per_dc:.2f} s")
        pass_b = fixed + (per_dc + extra_per_dc) * n_full
        print(f"    one pass                            {hms(pass_b)}")
        print(f"    first pass incl. probe              {hms(t_probe + pass_b)}")
        print(f"    scenario B is {pass_b / pass_a:.1f}x scenario A; the extras "
              f"account for {100 * extra_per_dc / (per_dc + extra_per_dc):.0f}% "
              f"of every dc point")
        print("\n  NOTE: scenario B is a cost projection from separately measured")
        print("  building blocks; the per-dc interleaving itself is not implemented")
        print("  in the production runner.  If it gets implemented with per-dc")
        print("  program reuse, treat these numbers as an upper bound.")
        banner("done -- the .txt log is the complete record of this run")


if __name__ == "__main__":
    main()
