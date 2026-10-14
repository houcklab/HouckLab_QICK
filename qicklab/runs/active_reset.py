"""Active-reset readout calibration and hardware verification."""

import os

import matplotlib.pyplot as plt
import numpy as np

from qicklab.core.experiment import finish
from qicklab.core.io import timestamp
from qicklab.experiments.active_reset_verify import ActiveResetVerify
from qicklab.runs.single_shot import get_apriori_separator_from_singleshot


def calibrate_active_reset_readout(ctx, max_align_iter=2, align_tol_frac=0.1):
    """Rotate ctx.config["res_phase"] (in place) so g/e separate along I and measure the I-threshold.

    Returns res_phase, readout_threshold, reset_ground_below_threshold, g_center, e_center
    (rotated frame); procedure in docs/experiments/active_reset.md.
    """
    res_ch = ctx.config["res_ch"]

    sep = get_apriori_separator_from_singleshot(ctx)
    n0 = np.asarray(sep["e_center"]) - np.asarray(sep["g_center"])
    phi_deg = float(np.degrees(np.arctan2(n0[1], n0[0])))
    base_phase = int(ctx.config.get("res_phase", 0))

    print(f"[ActiveReset calib] g->e axis at {phi_deg:.2f} deg; rotating res_phase to put it on I.")

    # try -phi, then +phi; keep the smaller |Q| separation (deg2reg sign never trusted)
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
    """Write readout_threshold and reset_ground_below_threshold from the separator into mr_cfg.

    Expects the separator measured in the rotated frame; idempotent, so re-call on recalibration.
    """
    g = np.asarray(apriori_sep["g_center"])
    e = np.asarray(apriori_sep["e_center"])
    mr_cfg["readout_threshold"] = float(0.5 * (g[0] + e[0]))
    mr_cfg["reset_ground_below_threshold"] = bool(g[0] < e[0])


def run_active_reset_verify(ctx, ActiveResetVerify_params):
    arv_dir = os.path.join(ctx.outerFolder, "ActiveResetVerify")
    os.makedirs(arv_dir, exist_ok=True)

    arv_calib = calibrate_active_reset_readout(ctx)

    arv_base_cfg = {
        "f_ge": ctx.qubit_frequency_center,
        "pi_gain": ctx.qubit_gain,
        "sigma": ctx.qubit_sigma,
        "flattop_length": ctx.qubit_flattop,
        "reps": ActiveResetVerify_params["reps"],
        "rounds": 1,
        "relax_delay": ActiveResetVerify_params["relax_delay"],
        "n_verify_reads": ActiveResetVerify_params["n_verify_reads"],
        "verify_relax_delay": ActiveResetVerify_params["verify_relax_delay"],
        "reset_cycles": ActiveResetVerify_params["reset_cycles"],
        "reset_readout_relax_delay": ActiveResetVerify_params["reset_readout_relax_delay"],
        "post_reset_wait": ActiveResetVerify_params["post_reset_wait"],
        "readout_threshold": arv_calib["readout_threshold"],
        "reset_ground_below_threshold": arv_calib["reset_ground_below_threshold"],
        "g_center": list(arv_calib["g_center"]),
        "e_center": list(arv_calib["e_center"]),
        "Qubit_number": ctx.Qubit_Readout,
    }
    # forwarded only when set, so the program's 0.5 us default/floor applies otherwise
    if "reset_read_latency_us" in ActiveResetVerify_params:
        arv_base_cfg["reset_read_latency_us"] = ActiveResetVerify_params["reset_read_latency_us"]

    # (label, prep_excited, use_active_reset, reset_force_pi): docs/experiments/active_reset_verify.md
    arv_conditions = [
        ("prep|g>_resetOFF", False, False, False),
        ("prep|e>_resetOFF", True, False, False),
        ("prep|g>_resetON", False, True, False),
        ("prep|e>_resetON", True, True, False),
        ("prep|e>_forcePI", True, True, True),
        ("prep|g>_forcePI", False, True, True),
    ]
    arv_results = {}
    for arv_label, arv_prep, arv_reset, arv_force in arv_conditions:
        print(f"\n[ActiveResetVerify] Condition: {arv_label}")
        cfg_arv = (
            ctx.working_config()
            | arv_base_cfg
            | {
                "prep_excited": arv_prep,
                "use_active_reset": arv_reset,
                "reset_force_pi": arv_force,
            }
        )
        inst_arv = ActiveResetVerify(
            path="ActiveResetVerify",
            cfg=cfg_arv,
            soc=ctx.soc,
            soccfg=ctx.soccfg,
            outerFolder=ctx.outerFolder,
        )
        data_arv = ActiveResetVerify.acquire(inst_arv)
        finish(ActiveResetVerify, inst_arv, data_arv, plotDisp=False, figNum=20)
        arv_results[arv_label] = np.asarray(data_arv["data"]["p_ground"])
        print(
            f"[ActiveResetVerify] {arv_label}: P(|g>) per read = "
            f"{np.array2string(arv_results[arv_label], precision=3)}"
        )

    read_idx_arv = np.arange(ActiveResetVerify_params["n_verify_reads"])
    timestamp_arv = timestamp()
    plt.figure(figsize=(8, 5))
    for arv_label, *_ in arv_conditions:
        plt.plot(read_idx_arv, arv_results[arv_label], "o-", linewidth=1.5, label=arv_label)
    plt.xlabel("Verification readout index")
    plt.ylabel("P(|g>)")
    plt.ylim(-0.05, 1.05)
    plt.title(
        "Active-reset verification\n"
        f"f_ge={ctx.qubit_frequency_center:.4f} MHz, "
        f"reset_cycles={ActiveResetVerify_params['reset_cycles']}"
    )
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    arv_overlay = os.path.join(arv_dir, f"ActiveResetVerify_overlay_{timestamp_arv}.png")
    plt.savefig(arv_overlay, dpi=300, bbox_inches="tight")
    if ActiveResetVerify_params.get("plotDisp", False):
        plt.show(block=False)
        plt.pause(0.1)
    else:
        plt.close()

    np.savez(
        os.path.join(arv_dir, f"ActiveResetVerify_{timestamp_arv}.npz"),
        read_index=read_idx_arv,
        readout_threshold=arv_calib["readout_threshold"],
        res_phase=arv_calib["res_phase"],
        g_center=arv_calib["g_center"],
        e_center=arv_calib["e_center"],
        **{f"p_ground_{lbl}": arv_results[lbl] for lbl, *_ in arv_conditions},
    )

    # verdict criteria: docs/experiments/active_reset_verify.md
    pg_g_off = float(np.mean(arv_results["prep|g>_resetOFF"]))
    pg_e_off = float(np.mean(arv_results["prep|e>_resetOFF"]))
    pg_g_on = float(np.mean(arv_results["prep|g>_resetON"]))
    pg_e_on = float(np.mean(arv_results["prep|e>_resetON"]))
    print("\n[ActiveResetVerify] ===== VERDICT =====")
    print(f"  prep|g> reset OFF : P(|g>)={pg_g_off:.3f}  (thermal baseline)")
    print(f"  prep|e> reset OFF : P(|g>)={pg_e_off:.3f}  (control, should be low)")
    print(f"  prep|g> reset ON  : P(|g>)={pg_g_on:.3f}")
    print(f"  prep|e> reset ON  : P(|g>)={pg_e_on:.3f}  (key proof)")
    pg_e_force = float(np.mean(arv_results["prep|e>_forcePI"][:1]))
    pg_g_force = float(np.mean(arv_results["prep|g>_forcePI"][:1]))
    print(
        f"  prep|e> force-pi  : P(|g>) read0 = {pg_e_force:.3f}  "
        f"(bare post-readout pi fidelity; expect ~ prep|g> baseline)"
    )
    print(
        f"  prep|g> force-pi  : P(|g>) read0 = {pg_g_force:.3f}  "
        f"(expect ~ prep|e> reset-OFF baseline)"
    )
    recovery_arv = pg_e_on - pg_e_off
    print(f"  reset recovery from |e> : dP(|g>) = {recovery_arv:+.3f}")
    if pg_e_on >= 0.9 * pg_g_on and recovery_arv >= 0.3:
        print("  => Active reset is WORKING (recovers |g> from |e>).")
    else:
        print(
            "  => Active reset NOT clearly working; inspect readout_threshold / "
            "res_phase / pi_gain calibration."
        )
    print(f"[ActiveResetVerify] complete. Overlay: {arv_overlay}")
