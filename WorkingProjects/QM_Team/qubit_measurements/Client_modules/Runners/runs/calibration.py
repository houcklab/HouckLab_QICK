from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils import *
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSingleShotProgramFFMUX import SingleShotProgramFFMUX
import numpy as np
from .context import Context


def _extract_iq_from_singleshot_data(data_ss, state="g"):
    """
    Extracts SingleShotProgramFFMUX IQ arrays.

    state="g" uses ground-prep IQ.
    state="e" uses excited-prep IQ.
    state="thermal" uses thermal IQ if available.
    """
    d = data_ss["data"]

    key_pairs = {
        "g": [
            ("i_g0", "q_g0"),
            ("i_g", "q_g"),
            ("Ig", "Qg"),
        ],
        "e": [
            ("i_e0", "q_e0"),
            ("i_e", "q_e"),
            ("Ie", "Qe"),
        ],
        "thermal": [
            ("i_thermal0", "q_thermal0"),
            ("i_thermal", "q_thermal"),
        ],
    }

    for i_key, q_key in key_pairs.get(state, []):
        if i_key in d and q_key in d:
            return np.ravel(np.array(d[i_key])), np.ravel(np.array(d[q_key]))

    print("[SingleShot MR Calib] Available data keys:", d.keys())
    raise KeyError(f"Could not find raw I/Q arrays for state={state}.")
def get_apriori_separator_from_singleshot(ctx, ss_shots=1000):
    """
    Runs one SingleShot calibration using a pi pulse.
    Uses the returned ground/excited blobs to define a fixed separator.
    Also saves the SingleShot data/config/png through the normal SingleShot methods.
    """

    cfg_ss = ctx.working_config()
    cfg_ss["number_of_pulses"] = 1
    cfg_ss["shots"] = ss_shots
    cfg_ss["reps"] = ss_shots
    cfg_ss["qubit_gain"] = ctx.qubit_gain
    cfg_ss["f_ge"] = ctx.qubit_frequency_center
    cfg_ss["sigma"] = ctx.qubit_sigma
    cfg_ss["flattop_length"] = ctx.qubit_flattop
    cfg_ss["Qubit_number"] = ctx.Qubit_Readout
    cfg_ss["Read_Indeces"] = ctx.Qubit_Readout

    inst_ss = SingleShotProgramFFMUX(
        path="SingleShot_MRCalib",
        outerFolder=ctx.outerFolder,
        cfg=cfg_ss,
        soc=ctx.soc,
        soccfg=ctx.soccfg
    )

    data_ss = SingleShotProgramFFMUX.acquire(inst_ss)

    # Save SingleShot data, config, and display png.
    SingleShotProgramFFMUX.display(inst_ss, data_ss, plotDisp=False)
    SingleShotProgramFFMUX.save_data(inst_ss, data_ss)
    SingleShotProgramFFMUX.save_config(inst_ss)

    d = data_ss["data"]

    Ig = np.ravel(np.array(d["i_g0"]))
    Qg = np.ravel(np.array(d["q_g0"]))
    Ie = np.ravel(np.array(d["i_e0"]))
    Qe = np.ravel(np.array(d["q_e0"]))

    g_center = np.array([np.mean(Ig), np.mean(Qg)])
    e_center = np.array([np.mean(Ie), np.mean(Qe)])

    normal = e_center - g_center
    midpoint = 0.5 * (g_center + e_center)

    print("[ModifiedRamsey] A priori separator from saved SingleShot:")
    print(f"  g_center = {g_center}")
    print(f"  e_center = {e_center}")
    print(f"  midpoint = {midpoint}")
    print(f"  normal   = {normal}")
    print(f"  separation = {np.linalg.norm(normal):.6f}")

    return {
        "g_center": g_center,
        "e_center": e_center,
        "normal": normal,
        "midpoint": midpoint,
        "data_ss": data_ss,
    }


def calibrate_active_reset_readout(
    ctx, max_align_iter=2, align_tol_frac=0.1
):
    """
    Calibrate the readout phase + single-shot I-threshold for hardware active reset.

    The active-reset feedback (ModifiedRamsey / ActiveResetVerify) thresholds on the
    RAW in-phase (I) value only, so |g> and |e> must separate ALONG I. This:
      1) runs a SingleShot g/e calibration at the current res_phase,
      2) rotates config["res_phase"] so the g->e axis lands on +I,
      3) RE-MEASURES and reads the I-threshold directly off the rotated blobs
         (so the deg2reg sign convention is never trusted -- the result is measured).

    Mutates config["res_phase"] in place. Returns dict:
      res_phase, readout_threshold, reset_ground_below_threshold,
      g_center, e_center  (rotated-frame, normalized collect_shots() units).
    """
    res_ch = ctx.config["res_ch"]

    sep = get_apriori_separator_from_singleshot(ctx)
    n0 = np.asarray(sep["e_center"]) - np.asarray(sep["g_center"])
    phi_deg = float(np.degrees(np.arctan2(n0[1], n0[0])))
    base_phase = int(ctx.config.get("res_phase", 0))

    print(
        f"[ActiveReset calib] g->e axis at {phi_deg:.2f} deg; rotating res_phase "
        f"to put it on I."
    )

    # Try rotating by -phi (align g->e with +I); if the sign convention flips it,
    # fall back to +phi. Keep whichever leaves the smallest |Q separation|.
    best = None
    for sign in (-1.0, +1.0):
        ctx.config["res_phase"] = int(
            base_phase + ctx.soccfg.deg2reg(sign * phi_deg, gen_ch=res_ch)
        )
        sep_r = get_apriori_separator_from_singleshot(ctx)
        gr = np.asarray(sep_r["g_center"])
        er = np.asarray(sep_r["e_center"])
        nr = er - gr
        i_sep, q_sep = abs(nr[0]), abs(nr[1])
        if best is None or q_sep < best["q_sep"]:
            best = {
                "res_phase": ctx.config["res_phase"],
                "g": gr,
                "e": er,
                "i_sep": i_sep,
                "q_sep": q_sep,
            }
        if q_sep <= align_tol_frac * i_sep:
            break

    ctx.config["res_phase"] = best["res_phase"]
    gr, er = best["g"], best["e"]
    if best["q_sep"] > align_tol_frac * best["i_sep"]:
        print(
            f"[ActiveReset calib] WARNING: residual Q separation {best['q_sep']:.4f} "
            f"vs I separation {best['i_sep']:.4f}; reset thresholding on I may be "
            f"degraded. Improve the SingleShot fidelity or rotate manually."
        )

    readout_threshold = 0.5 * (gr[0] + er[0])
    reset_ground_below = bool(gr[0] < er[0])
    print(
        f"[ActiveReset calib] res_phase={best['res_phase']} (reg units), "
        f"readout_threshold={readout_threshold:.6f}, "
        f"reset_ground_below_threshold={reset_ground_below} "
        f"(g_I={gr[0]:.4f}, e_I={er[0]:.4f})"
    )

    return {
        "res_phase": best["res_phase"],
        "readout_threshold": float(readout_threshold),
        "reset_ground_below_threshold": reset_ground_below,
        "g_center": gr,
        "e_center": er,
    }


def wire_reset_into_mr_cfg(mr_cfg, apriori_sep):
    """
    Derive the active-reset I-threshold (and the |g>-below-threshold sign) from
    the apriori SingleShot separator and write them into mr_cfg, in place.

    Assumes calibrate_active_reset_readout() has already rotated res_phase so
    g/e separate along I (the separator must be measured in that rotated
    frame). Idempotent, so it is safe to re-call on ss recalibrations to track
    the (drifting) threshold.
    """
    g = np.asarray(apriori_sep["g_center"])
    e = np.asarray(apriori_sep["e_center"])
    mr_cfg["readout_threshold"] = float(0.5 * (g[0] + e[0]))
    mr_cfg["reset_ground_below_threshold"] = bool(g[0] < e[0])
