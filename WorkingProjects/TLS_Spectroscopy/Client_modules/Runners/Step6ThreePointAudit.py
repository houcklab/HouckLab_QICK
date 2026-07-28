import gc
import time

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import SingleShot1Q
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mT1VsFlux import (
    T13PointVsFlux, _compute_3pt_t1,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset, ff_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.active_reset import probe_reset_params
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.reset_phase import calibrate_res_phase
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_fit as fx

QUBIT = "q4"

RUN_PHASE_CAL = True
RUN_SS_CAL = True
RUN_RESET_PROBE = True
RUN_PREVIEW = True
RUN_FULL = False

PREVIEW_DC_POINTS = 6
PREVIEW_SHOTS = 1000

BASELINE_DC_OFFSET = 0
INTERLEAVE_ROUNDS = 10
RANDOMIZE_POINT_ORDER = True
POINT_ORDER_SEED = None
THERMALIZATION_US = 2.0
T1_FEEDBACK_RELAX_US = 25.0
T1_RESET_BACKSTOP_US = 2000.0
FLUX_TAIL_COMPENSATION = None

SS_SHOTS = 1000
SS_GROUND_THRESHOLD = 0.7

FLUX_FIT_PARAMS = [
    9.30070052036,
    0.100677145556,
    31881.294671,
    7115.71137189,
    0.822636051338,
    -4.13273417292e-05,
]

P6_3PT_T1 = {
    "shots": 500,
    "dc_min": 0,
    "dc_max": 10000,
    "freq_step_mhz": 1,
    "Ts_us": 60.0,
    "min_ref_contrast": 0.05,
    "max_plot_t1_multiple": 20.0,
    "reset_mode": "feedback",
    "reset_max_iters": 3,
}


ASSUMED_CONTRAST = 0.54


def resolvable_t1_window(Ts_us, shots, contrast=None, n_sigma=3.0):
    contrast = ASSUMED_CONTRAST if contrast is None else contrast
    sigma_p = np.sqrt(0.25 / max(int(shots), 1))
    sigma_pe = np.sqrt(2.0) * sigma_p / max(contrast, 1e-9)
    pe_lo = min(max(n_sigma * sigma_pe, 1e-6), 0.499)
    pe_hi = 1.0 - pe_lo
    return -Ts_us / np.log(pe_lo), -Ts_us / np.log(pe_hi)


def banner(text):
    print()
    print("=" * 78)
    print(text)
    print("=" * 78)


def describe_flux_fit():
    banner("STAGE A -- flux fit and DC vector (no hardware; pure geometry check)")
    EJmax, Ec, period, offset, d, tilt = FLUX_FIT_PARAMS
    f_max = np.sqrt(8.0 * EJmax * Ec) - Ec
    print(f"  EJmax={EJmax:.4f} GHz  Ec={Ec:.5f} GHz  period={period:.0f} DAC")
    print(f"  offset={offset:.0f} DAC  d={d:.4f}  tilt={tilt:+.3e} GHz/DAC")
    print(f"  -> sweet-spot f_max = sqrt(8*EJmax*Ec) - Ec = {f_max:.4f} GHz")
    print(f"  -> BaseConfig qubit_pi_freq = {BaseConfig['qubit_pi_freq'] / 1e3:.4f} GHz")
    if abs(f_max - BaseConfig["qubit_pi_freq"] / 1e3) > 0.2:
        print("  WARNING: the fit's sweet spot is far from the configured qubit frequency;")
        print("           FLUX_FIT_PARAMS may be from a different cooldown or qubit.")

    dc_vec = fx.build_freq_uniform_dc_vec(
        P6_3PT_T1["dc_min"], P6_3PT_T1["dc_max"],
        float(P6_3PT_T1["freq_step_mhz"]) * 1e6, FLUX_FIT_PARAMS)
    f_ghz = fx.estimate_fit_frequency_ghz_array(FLUX_FIT_PARAMS, dc_vec)
    print(f"\n  dc_vec: {len(dc_vec)} points, DC {dc_vec.min():+.0f}..{dc_vec.max():+.0f}")
    print(f"          f {np.nanmin(f_ghz):.4f}..{np.nanmax(f_ghz):.4f} GHz "
          f"(span {1e3 * (np.nanmax(f_ghz) - np.nanmin(f_ghz)):.0f} MHz)")
    print(f"          dc spacing {np.min(np.diff(dc_vec)):.0f}..{np.max(np.diff(dc_vec)):.0f} DAC")
    print(f"          NOTE dc_step is IGNORED because freq_step_mhz is set\n")
    print(f"  {'i':>4s} {'dc':>9s} {'f (GHz)':>10s} {'df to next (MHz)':>17s}")
    idx = list(range(min(3, len(dc_vec)))) + [len(dc_vec) // 2] + \
        list(range(max(0, len(dc_vec) - 3), len(dc_vec)))
    for i in sorted(set(idx)):
        dfn = (1e3 * (f_ghz[i + 1] - f_ghz[i])) if i + 1 < len(dc_vec) else np.nan
        print(f"  {i:>4d} {dc_vec[i]:>9.0f} {f_ghz[i]:>10.4f} {dfn:>17.3f}")
    return dc_vec, f_ghz


def describe_schedule(dc_vec):
    banner("STAGE B -- what the 3-point estimator will actually do")
    Ts = P6_3PT_T1["Ts_us"]
    print(f"  Ts = {Ts:g} us  (FIXED -- T1_probe_cfg/auto_Ts_factor are unused because")
    print(f"       Ts_us is not None; the park-T1 auto probe will NOT run)")
    print(f"  per DC point, 3 programs:")
    print(f"    P0 = park, no pi,  no flux   -> reference ground")
    print(f"    P1 = park, pi,     no flux   -> reference excited")
    print(f"    Ps = dc,   pi,     hold {Ts:g}us -> decayed")
    print(f"  pe = (Ps-P0)/(P1-P0);  T1 = -Ts/ln(pe)")
    print(f"  masks: contrast < {P6_3PT_T1['min_ref_contrast']} -> NaN, "
          f"T1 > {P6_3PT_T1['max_plot_t1_multiple']:g}xTs = "
          f"{P6_3PT_T1['max_plot_t1_multiple'] * Ts:g} us -> NaN")
    for shots, tag in ((PREVIEW_SHOTS, "preview"), (P6_3PT_T1["shots"], "full")):
        lo, hi = resolvable_t1_window(Ts, shots)
        print(f"  RESOLVABLE T1 WINDOW ({tag}, {shots} shots, assumed contrast "
              f"{ASSUMED_CONTRAST:g}): {lo:.0f} .. {hi:.0f} us")
    print(f"       (T1 below the floor reads pe<=0 and gets masked; above the ceiling")
    print(f"        pe->1 and T1 is unconstrained.  Pick Ts near the T1 you expect.)")
    settle = ff_pulse.flux_settle_us(BaseConfig)
    ramp = BaseConfig.get("ff_ramp_length", ff_pulse.STATE_SAFE_RAMP_US)
    print(f"\n  flux pulse: ramp {ramp:g} us, settle {settle:g} us "
          f"(flux ON at target = {settle + Ts:g} us for Ts={Ts:g})")
    print(f"  slew at dc_max: {abs(P6_3PT_T1['dc_max']) / ramp:.0f} DAC/us "
          f"(state-safe limit {ff_pulse.MAX_SAFE_SLEW_DAC_PER_US:.0f})")
    n_prog = 3 * len(dc_vec) * INTERLEAVE_ROUNDS
    per_shot_ms = (T1_FEEDBACK_RELAX_US + 3 * 21 + THERMALIZATION_US + 40 + Ts) / 1e3
    est_s = n_prog * (P6_3PT_T1["shots"] / INTERLEAVE_ROUNDS) * per_shot_ms / 1e3
    print(f"\n  one full pass: {len(dc_vec)} dc x 3 specs x {INTERLEAVE_ROUNDS} rounds "
          f"= {n_prog} programs")
    print(f"  rough time per pass: {est_s / 60:.1f} min (excluding per-program overhead)")


def base_cfg(dc_vec, shots, rec):
    cfg = dict(BaseConfig)
    cfg.update({
        "shots": int(shots), "reps": int(shots),
        "interleave_rounds": INTERLEAVE_ROUNDS,
        "randomize_point_order": bool(RANDOMIZE_POINT_ORDER),
        "point_order_seed": POINT_ORDER_SEED,
        "ff_gain_vec": dc_vec,
        "flux_tail_compensation": FLUX_TAIL_COMPENSATION,
        "flux_fit_params": FLUX_FIT_PARAMS,
        "qubit_pulse_style": "arb",
        "reset_mode": P6_3PT_T1["reset_mode"],
    })
    if active_reset.uses_feedback(cfg) and rec is not None:
        cfg.update({
            "reset_threshold_raw": int(rec["threshold_raw"]),
            "reset_oper": str(rec["oper"]),
            "reset_ground_below": bool(rec["ground_below"]),
            "reset_max_iters": int(P6_3PT_T1["reset_max_iters"]),
            "reset_thermalization_us": THERMALIZATION_US,
        })
        cfg["relax_delay"] = T1_FEEDBACK_RELAX_US
    else:
        cfg["reset_mode"] = "passive"
        cfg["relax_delay"] = T1_RESET_BACKSTOP_US
    return cfg


def report_points(exp, dc_vec, f_ghz):
    d = exp.data
    P0, P1, Ps = np.asarray(d["P0"]), np.asarray(d["P1"]), np.asarray(d["Ps"])
    est = _compute_3pt_t1(P0, P1, Ps, exp.Ts_ns,
                          min_ref_contrast=P6_3PT_T1["min_ref_contrast"],
                          max_t1_multiple=P6_3PT_T1["max_plot_t1_multiple"])
    print(f"\n  {'dc':>8s} {'f(GHz)':>9s} | {'P0':>6s} {'P1':>6s} {'Ps':>6s} | "
          f"{'contr':>6s} {'pe':>6s} | {'T1(us)':>9s} | why")
    for i, dc in enumerate(dc_vec):
        c, pe = est["contrast"][i], est["pe"][i]
        t1 = est["T1_3pt_us_raw"][i]
        ok = est["valid_mask"][i]
        if ok:
            why = "ok"
        elif not np.isfinite(c) or abs(c) < P6_3PT_T1["min_ref_contrast"]:
            why = f"contrast<{P6_3PT_T1['min_ref_contrast']}"
        elif not (0.0 < pe < 1.0):
            why = "pe outside (0,1)"
        else:
            why = f"T1>{est['max_t1_us']:.0f}us"
        print(f"  {dc:>8.0f} {f_ghz[i]:>9.4f} | {P0[i]:>6.3f} {P1[i]:>6.3f} {Ps[i]:>6.3f} | "
              f"{c:>6.3f} {pe:>6.3f} | {t1:>9.1f} | {why}")
    good = int(np.sum(est["valid_mask"]))
    print(f"\n  {good}/{len(dc_vec)} points valid")
    print(f"  reference contrast P1-P0: mean {np.nanmean(est['contrast']):.3f}, "
          f"min {np.nanmin(est['contrast']):.3f}")
    if np.nanmean(est["contrast"]) < 0.3:
        print("  WARNING: low reference contrast -- P0/P1 should straddle the readout")
        print("           range; if P1-P0 is small every T1 here is noise-dominated.")


def main():
    soc, soccfg = makeProxy()

    dc_vec_full, f_ghz_full = describe_flux_fit()
    describe_schedule(dc_vec_full)

    if RUN_PHASE_CAL:
        banner("STAGE C -- res-phase calibration")
        best = calibrate_res_phase(soc, soccfg, BaseConfig, QUBIT, outerFolder,
                                   apply_config=False)
        if best is not None:
            BaseConfig["res_phase"] = float(best)
            print(f"  applied res_phase = {best:.1f} deg for this session")

    calib_params = None
    if RUN_SS_CAL:
        banner("STAGE D -- single-shot calibration (passive)")
        c = dict(BaseConfig)
        c.update({"shots": SS_SHOTS, "reps": SS_SHOTS, "reset_mode": "passive",
                  "relax_delay": T1_RESET_BACKSTOP_US,
                  "qubit_gain": int(BaseConfig["qubit_pi_gain"])})
        ss = SingleShot1Q(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                          suffix="Step6Audit_SS", cfg=c, repeats=1,
                          confidence_threshold=SS_GROUND_THRESHOLD)
        ss.acquire(progress=False, plotDisp=False)
        calib_params = ss.calib_params
        print(f"  F = {ss.max_F:.4f}   calib_params = {calib_params}")
        plt.close("all"); gc.collect()
        if ss.max_F < 0.75:
            print("  WARNING: readout fidelity below 0.75; 3-point contrast will suffer.")

    rec = None
    if RUN_RESET_PROBE and active_reset.uses_feedback(P6_3PT_T1["reset_mode"]):
        banner("STAGE E -- active-reset probe and end-to-end gate")
        rec = probe_reset_params(soc, soccfg, BaseConfig, path=QUBIT,
                                 outer_folder=outerFolder, shots=2000)
        if rec is None:
            print("  gate FAILED -> this audit will fall back to passive relax "
                  f"({T1_RESET_BACKSTOP_US:.0f}us)")
        else:
            print(f"  threshold_raw={rec['threshold_raw']} oper={rec['oper']} "
                  f"ground_below={rec['ground_below']}")

    if RUN_PREVIEW:
        banner(f"STAGE F -- PREVIEW: {PREVIEW_DC_POINTS} DC points, per-point numbers")
        pick = np.unique(np.linspace(0, len(dc_vec_full) - 1,
                                     PREVIEW_DC_POINTS).astype(int))
        dc_prev, f_prev = dc_vec_full[pick], f_ghz_full[pick]
        print(f"  DC points: {[f'{d:.0f}' for d in dc_prev]}")
        cfg = base_cfg(dc_prev, PREVIEW_SHOTS, rec)
        t0 = time.time()
        exp = T13PointVsFlux(
            soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
            suffix="Step6Audit_3pt_preview", cfg=cfg, dc_vec=dc_prev,
            Ts_ns=int(round(P6_3PT_T1["Ts_us"] * 1e3)), shots=PREVIEW_SHOTS,
            calib_params=calib_params, park_voltage=BASELINE_DC_OFFSET,
            reset_mode=cfg["reset_mode"],
            min_ref_contrast=P6_3PT_T1["min_ref_contrast"],
            max_plot_t1_multiple=P6_3PT_T1["max_plot_t1_multiple"],
            run_park_T1_if_Ts_none=False, write_outputs=False)
        exp.acquire(progress=False)
        print(f"  preview took {time.time() - t0:.0f} s "
              f"({(time.time() - t0) / max(len(dc_prev), 1):.1f} s per DC point)")
        report_points(exp, dc_prev, f_prev)
        plt.close("all"); gc.collect()

    if RUN_FULL:
        banner("STAGE G -- FULL 3-point sweep")
        cfg = base_cfg(dc_vec_full, P6_3PT_T1["shots"], rec)
        exp = T13PointVsFlux(
            soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
            suffix="Step6Audit_3pt_full", cfg=cfg, dc_vec=dc_vec_full,
            Ts_ns=int(round(P6_3PT_T1["Ts_us"] * 1e3)), shots=P6_3PT_T1["shots"],
            calib_params=calib_params, park_voltage=BASELINE_DC_OFFSET,
            reset_mode=cfg["reset_mode"],
            min_ref_contrast=P6_3PT_T1["min_ref_contrast"],
            max_plot_t1_multiple=P6_3PT_T1["max_plot_t1_multiple"],
            run_park_T1_if_Ts_none=False, write_outputs=True)
        exp.acquire(progress=True)
        report_points(exp, dc_vec_full, f_ghz_full)

    banner("audit complete -- paste the whole log back")


if __name__ == "__main__":
    main()
