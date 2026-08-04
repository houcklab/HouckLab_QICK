from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils import *
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSingleShotProgramFFMUX import SingleShotProgramFFMUX
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mOptimizeReadoutandPulse_FF import ReadOpt_wSingleShotFF, QubitPulseOpt_wSingleShotFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mActiveResetVerify import ActiveResetVerify
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mUndrivenSingleShot import UndrivenSingleShot
import numpy as np
import matplotlib.pyplot as plt
from .context import Context
from .calibration import get_apriori_separator_from_singleshot, calibrate_active_reset_readout, wire_reset_into_mr_cfg, _extract_iq_from_singleshot_data


def run_active_reset_verify(ctx, ActiveResetVerify_params):
    arv_dir = os.path.join(ctx.outerFolder, "ActiveResetVerify")
    os.makedirs(arv_dir, exist_ok=True)

    # 1) Calibrate readout phase + I-threshold (rotates config["res_phase"] so
    #    |g>/|e> separate along I, and measures the threshold off the rotated blobs).
    arv_calib = calibrate_active_reset_readout(
        ctx
    )

    # 2) Base config shared by all conditions. g_center/e_center are in the
    #    rotated frame (consistent with config["res_phase"] set just above).
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
        "reset_readout_relax_delay": ActiveResetVerify_params[
            "reset_readout_relax_delay"
        ],
        "post_reset_wait": ActiveResetVerify_params["post_reset_wait"],
        "readout_threshold": arv_calib["readout_threshold"],
        "reset_ground_below_threshold": arv_calib["reset_ground_below_threshold"],
        "g_center": list(arv_calib["g_center"]),
        "e_center": list(arv_calib["e_center"]),
        "Qubit_number": ctx.Qubit_Readout,
    }

    # 3) Four conditions: prep |g>/|e>  ×  reset off/on, plus force-pi
    #    diagnostics: the corrective pi fires UNCONDITIONALLY after the
    #    conditioning readout, measuring the bare post-readout pi fidelity
    #    decoupled from the threshold decision (prep|e>_forcePI should match
    #    prep|g>_resetOFF if the pi is good; prep|g>_forcePI should match
    #    prep|e>_resetOFF).
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
        ActiveResetVerify.display(inst_arv, data_arv, plotDisp=False, figNum=20)
        ActiveResetVerify.save_data(inst_arv, data_arv)
        ActiveResetVerify.save_config(inst_arv)
        arv_results[arv_label] = np.asarray(data_arv["data"]["p_ground"])
        print(
            f"[ActiveResetVerify] {arv_label}: P(|g>) per read = "
            f"{np.array2string(arv_results[arv_label], precision=3)}"
        )

    # 4) Overlay P(|g>) vs read index for all conditions.
    read_idx_arv = np.arange(ActiveResetVerify_params["n_verify_reads"])
    timestamp_arv = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    plt.figure(figsize=(8, 5))
    for arv_label, *_ in arv_conditions:
        plt.plot(
            read_idx_arv, arv_results[arv_label], "o-", linewidth=1.5, label=arv_label
        )
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
    arv_overlay = os.path.join(
        arv_dir, f"ActiveResetVerify_overlay_{timestamp_arv}.png"
    )
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

    # 5) Verdict.
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


def run_single_shot(ctx, SS_params):
    cfg = ctx.working_config()
    cfg['number_of_pulses'] = SS_params['number_of_pulses']
    if SS_params['pi2_SS']:
        cfg['qubit_gain'] = ctx.pi2_gain
    Instance_SingleShotProgram = SingleShotProgramFFMUX(path="SingleShot", outerFolder=ctx.outerFolder, cfg=cfg, soc=ctx.soc,soccfg=ctx.soccfg)
    data_SingleShotProgram = SingleShotProgramFFMUX.acquire(Instance_SingleShotProgram)
    # print(data_SingleShotProgram)
    SingleShotProgramFFMUX.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True)

    SingleShotProgramFFMUX.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
    SingleShotProgramFFMUX.save_config(Instance_SingleShotProgram)
    print('Angle: ', data_SingleShotProgram['data']['angle'][0])
    print('threshold: ', data_SingleShotProgram['data']['threshold'][0])


def run_undriven_single_shot(ctx, US_params=None):
    """Single-shot readout with the qubit drive off — just look at the blobs.

    Runs under the same single-shot-regime config as `run_single_shot` (so the
    readout tone, window and ADC offset are identical), but the experiment never
    declares or pulses the qubit channel. `US_params` may override the shot count,
    the relax delay, and the blob-separation threshold; everything else comes from
    the config `rebuild_singleshot_config` already installed.
    """
    US_params = US_params or {}
    overrides = {}
    if 'Shots' in US_params:
        overrides['shots'] = US_params['Shots']
    if 'relax_delay' in US_params:
        overrides['relax_delay'] = US_params['relax_delay']
    if 'min_separation_sigma' in US_params:
        overrides['blob_min_separation_sigma'] = US_params['min_separation_sigma']
    cfg = ctx.working_config(overrides)

    inst = UndrivenSingleShot(path="UndrivenSingleShot", outerFolder=ctx.outerFolder,
                              cfg=cfg, soc=ctx.soc, soccfg=ctx.soccfg)
    data = UndrivenSingleShot.acquire(inst)
    UndrivenSingleShot.display(inst, data, plotDisp=US_params.get('plotDisp', True))
    UndrivenSingleShot.save_data(inst, data)
    UndrivenSingleShot.save_config(inst)
    return data


def run_readout_optimize(ctx, SS_R_params):
    span = SS_R_params['span']
    cav_gain_start = SS_R_params['gain_start']
    cav_gain_stop = SS_R_params['gain_stop']
    cav_gain_pts = SS_R_params['gain_pts']
    cav_trans_pts = SS_R_params['trans_pts']
    cfg = ctx.working_config()
    cfg['number_of_pulses'] = 1
    exp_parameters = {
        ###### cavity
        "cav_gain_Start": cav_gain_start,
        "cav_gain_Stop": cav_gain_stop,
        "cav_gain_Points": cav_gain_pts,
        "trans_freq_start": cfg["pulse_freq"] - span / 2,
        "trans_freq_stop": cfg["pulse_freq"] + span / 2,
        "TransNumPoints": cav_trans_pts,
    }
    cfg = cfg | exp_parameters  # merge into the copy already holding number_of_pulses=1
    # Now lets optimize powers and readout frequencies
    Instance_SingleShotOptimize = ReadOpt_wSingleShotFF(path="SingleShot_OptReadout", outerFolder=ctx.outerFolder, cfg=cfg,soc=ctx.soc,soccfg=ctx.soccfg)
    data_SingleShotProgramOptimize = ReadOpt_wSingleShotFF.acquire(Instance_SingleShotOptimize)
    # print(data_SingleShotProgram)
    ReadOpt_wSingleShotFF.display(Instance_SingleShotOptimize, data_SingleShotProgramOptimize, plotDisp=True)

    ReadOpt_wSingleShotFF.save_data(Instance_SingleShotOptimize, data_SingleShotProgramOptimize)
    ReadOpt_wSingleShotFF.save_config(Instance_SingleShotOptimize)


def run_qubit_optimize(ctx, SS_Q_params, SS_params):
    qubit_gains = [ctx.Qubit_Parameters[str(Q_R)]['Qubit']['Gain'] for Q_R in SS_params["Qubit_Pulse"]]
    qubit_frequency_centers = [ctx.Qubit_Parameters[str(Q_R)]['Qubit']['Frequency'] for Q_R in SS_params["Qubit_Pulse"]]
    q_gain_span = SS_Q_params['q_gain_span']
    q_gain_pts = SS_Q_params['q_gain_pts']
    q_freq_pts = SS_Q_params['q_freq_pts']
    q_freq_span = SS_Q_params['q_freq_span']
    cfg = ctx.working_config()
    cfg['number_of_pulses'] = SS_Q_params['number_of_pulses']
    if cfg['pi2_SS']:
        cfg['qubit_gain'] = ctx.pi2_gain
    Qubit_Pulse_Index = 0
    exp_parameters = {
        ###### cavity
        "qubit_gain_Start": max([0, int( cfg['qubit_gain'] - int(q_gain_span))]), # - q_gain_span / 2,
        "qubit_gain_Stop":  min([32767, int( cfg['qubit_gain']+ int(q_gain_span))]),# *qubit_gains[Qubit_Pulse_Index] + q_gain_span / 2,
        "qubit_gain_Points": q_gain_pts,
        "qubit_freq_start": qubit_frequency_centers[Qubit_Pulse_Index] - q_freq_span,
        "qubit_freq_stop": qubit_frequency_centers[Qubit_Pulse_Index] + q_freq_span,
        "QubitNumPoints": q_freq_pts,
        "number_of_pulses": SS_Q_params["number_of_pulses"]
    }
    print(exp_parameters)
    cfg = cfg | exp_parameters  # preserve number_of_pulses + pi2 qubit_gain set above (mirrors original config | exp_parameters)
    g0 = qubit_gains[Qubit_Pulse_Index]
    f0 = qubit_frequency_centers[Qubit_Pulse_Index]
    # # Now lets optimize powers and readout frequencies
    Instance_SingleShotOptimize = QubitPulseOpt_wSingleShotFF(path="SingleShot_OptQubit", outerFolder=ctx.outerFolder,
                                                                 cfg=cfg,soc=ctx.soc,soccfg=ctx.soccfg)
    data_SingleShotProgramOptimize = QubitPulseOpt_wSingleShotFF.acquire(Instance_SingleShotOptimize,
                                                                            Qubit_Sweep_Index = Qubit_Pulse_Index)
    # print(data_SingleShotProgram)
    QubitPulseOpt_wSingleShotFF.display(Instance_SingleShotOptimize, data_SingleShotProgramOptimize, plotDisp=True)
    print(exp_parameters)

    QubitPulseOpt_wSingleShotFF.save_data(Instance_SingleShotOptimize, data_SingleShotProgramOptimize)
    QubitPulseOpt_wSingleShotFF.save_config(Instance_SingleShotOptimize)
