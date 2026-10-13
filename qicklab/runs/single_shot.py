"""Single-shot readout routines: blob calibration, undriven shots, readout/pulse optimisation, T1 single-shot."""

import time

import numpy as np

from qicklab.experiments.readout_optimize import QubitPulseOpt_wSingleShotFF, ReadOpt_wSingleShotFF
from qicklab.experiments.single_shot import SingleShotProgramFFMUX
from qicklab.experiments.t1_single_shot import T1_SS
from qicklab.experiments.undriven_single_shot import UndrivenSingleShot


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
        soccfg=ctx.soccfg,
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


def run_t1_ss(ctx, T1SS_params, SS_params):
    for i in range(T1SS_params["repetitions"]):
        cfg = ctx.working_config()
        if T1SS_params["calibrate_SS"]:
            cfg["number_of_pulses"] = SS_params["number_of_pulses"]
            Instance_SingleShotProgram = SingleShotProgramFFMUX(
                path="SingleShot",
                outerFolder=ctx.outerFolder,
                cfg=cfg,
                soc=ctx.soc,
                soccfg=ctx.soccfg,
            )
            data_SingleShotProgram = SingleShotProgramFFMUX.acquire(Instance_SingleShotProgram)
            SingleShotProgramFFMUX.display(
                Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=False
            )
            SingleShotProgramFFMUX.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
            SingleShotProgramFFMUX.save_config(Instance_SingleShotProgram)
            angle = data_SingleShotProgram["data"]["angle"][0]
            threshold = data_SingleShotProgram["data"]["threshold"][0]
        else:
            angle = T1SS_params["angle"]
            threshold = T1SS_params["threshold"]
        print(angle, threshold)

        expt_cfg = {
            "start": 0,
            "step": T1SS_params["T1_step"],
            "expts": T1SS_params["T1_expts"],
            "reps": T1SS_params["reps"],
            "pi_gain": ctx.qubit_gain,
            "relax_delay": T1SS_params["relax_delay"],
        }
        cfg = (
            cfg | expt_cfg
        )  ### preserve number_of_pulses set above (mirrors original config | expt_cfg)
        iT1 = T1_SS(
            path="T1SS", cfg=cfg, soc=ctx.soc, soccfg=ctx.soccfg, outerFolder=ctx.outerFolder
        )
        dT1 = T1_SS.acquire(iT1, angle=angle, threshold=threshold)
        T1_SS.display(iT1, dT1, plotDisp=False, figNum=2)
        T1_SS.save_data(iT1, dT1)
        T1_SS.save_config(iT1)

        time.sleep(10)
        ctx.soc.reset_gens()


def run_single_shot(ctx, SS_params):
    cfg = ctx.working_config()
    cfg["number_of_pulses"] = SS_params["number_of_pulses"]
    if SS_params["pi2_SS"]:
        cfg["qubit_gain"] = ctx.pi2_gain
    Instance_SingleShotProgram = SingleShotProgramFFMUX(
        path="SingleShot", outerFolder=ctx.outerFolder, cfg=cfg, soc=ctx.soc, soccfg=ctx.soccfg
    )
    data_SingleShotProgram = SingleShotProgramFFMUX.acquire(Instance_SingleShotProgram)
    # print(data_SingleShotProgram)
    SingleShotProgramFFMUX.display(
        Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True
    )

    SingleShotProgramFFMUX.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
    SingleShotProgramFFMUX.save_config(Instance_SingleShotProgram)
    print("Angle: ", data_SingleShotProgram["data"]["angle"][0])
    print("threshold: ", data_SingleShotProgram["data"]["threshold"][0])


def run_undriven_single_shot(ctx, US_params=None):
    """Single-shot readout with the qubit drive off — just look at the blobs.

    Runs under the same single-shot-regime config as `run_single_shot` (so the
    readout tone, window and ADC offset are identical), but the experiment never
    declares or pulses the qubit channel. `US_params` may override the shot count,
    the relax delay, the blob-separation threshold, and the number of consecutive
    shots averaged into each time-series point (`average_shots`); everything else
    comes from the config `rebuild_singleshot_config` already installed.

    Shots come off the tProc in acquisition order at a fixed cadence, so the
    record is also a time series: the experiment projects it onto the
    blob-separating axis and reports how it hops between the blobs. Raising
    `average_shots` trades time resolution for the sqrt(n) noise reduction that
    makes a marginal blob split resolvable; the rate-vs-averaging panel in the
    output plot shows where the useful plateau is.

    `US_params['Repeat']` (default 1) runs the whole acquisition that many times
    back to back. Each pass is an independent experiment with its own timestamped
    h5/png/json, so nothing is overwritten and the passes can be compared or
    concatenated offline. Returns the list of per-pass data dicts.
    """
    US_params = US_params or {}
    overrides = {}
    if "Shots" in US_params:
        overrides["shots"] = US_params["Shots"]
    if "relax_delay" in US_params:
        overrides["relax_delay"] = US_params["relax_delay"]
    if "min_separation_sigma" in US_params:
        overrides["blob_min_separation_sigma"] = US_params["min_separation_sigma"]
    if "average_shots" in US_params:
        overrides["shot_average"] = US_params["average_shots"]
    if "bin_sizes" in US_params:
        overrides["ts_bin_sizes"] = US_params["bin_sizes"]
    # Sweep the charge bias with the yoko. The range must come through US_params:
    # rebuild_singleshot_config() drops charge_params from ctx.config.
    overrides["charge_sweep"] = US_params.get("charge_sweep", False)
    for key in ("voltage_start", "voltage_end", "voltage_step", "charge_settle_s"):
        if key in US_params:
            overrides[key] = US_params[key]

    n_repeat = max(1, int(US_params.get("Repeat", 1)))
    plot_disp = US_params.get("plotDisp", True)
    runs = []
    for k in range(n_repeat):
        if n_repeat > 1:
            print(f"\n[UndrivenSingleShot] pass {k + 1}/{n_repeat}")
        # Fresh cfg per pass: the program mutates reps/rounds/length in place.
        cfg = ctx.working_config(overrides)
        inst = UndrivenSingleShot(
            path="UndrivenSingleShot",
            outerFolder=ctx.outerFolder,
            cfg=cfg,
            soc=ctx.soc,
            soccfg=ctx.soccfg,
            yoko=ctx.yoko,
        )
        data = UndrivenSingleShot.acquire(inst)
        # display(plotDisp=True) blocks until the window is closed, which would
        # stall every pass. The PNG is written either way, so only put the last
        # pass on screen.
        UndrivenSingleShot.display(inst, data, plotDisp=plot_disp and k == n_repeat - 1)
        UndrivenSingleShot.save_data(inst, data)
        UndrivenSingleShot.save_config(inst)
        runs.append(data)
    return runs


def run_readout_optimize(ctx, SS_R_params):
    span = SS_R_params["span"]
    cav_gain_start = SS_R_params["gain_start"]
    cav_gain_stop = SS_R_params["gain_stop"]
    cav_gain_pts = SS_R_params["gain_pts"]
    cav_trans_pts = SS_R_params["trans_pts"]
    cfg = ctx.working_config()
    cfg["number_of_pulses"] = 1
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
    Instance_SingleShotOptimize = ReadOpt_wSingleShotFF(
        path="SingleShot_OptReadout",
        outerFolder=ctx.outerFolder,
        cfg=cfg,
        soc=ctx.soc,
        soccfg=ctx.soccfg,
    )
    data_SingleShotProgramOptimize = ReadOpt_wSingleShotFF.acquire(Instance_SingleShotOptimize)
    # print(data_SingleShotProgram)
    ReadOpt_wSingleShotFF.display(
        Instance_SingleShotOptimize, data_SingleShotProgramOptimize, plotDisp=True
    )

    ReadOpt_wSingleShotFF.save_data(Instance_SingleShotOptimize, data_SingleShotProgramOptimize)
    ReadOpt_wSingleShotFF.save_config(Instance_SingleShotOptimize)


def run_qubit_optimize(ctx, SS_Q_params, SS_params):
    qubit_gains = [
        ctx.Qubit_Parameters[str(Q_R)]["Qubit"]["Gain"] for Q_R in SS_params["Qubit_Pulse"]
    ]
    qubit_frequency_centers = [
        ctx.Qubit_Parameters[str(Q_R)]["Qubit"]["Frequency"] for Q_R in SS_params["Qubit_Pulse"]
    ]
    q_gain_span = SS_Q_params["q_gain_span"]
    q_gain_pts = SS_Q_params["q_gain_pts"]
    q_freq_pts = SS_Q_params["q_freq_pts"]
    q_freq_span = SS_Q_params["q_freq_span"]
    cfg = ctx.working_config()
    cfg["number_of_pulses"] = SS_Q_params["number_of_pulses"]
    if cfg["pi2_SS"]:
        cfg["qubit_gain"] = ctx.pi2_gain
    Qubit_Pulse_Index = 0
    exp_parameters = {
        ###### cavity
        "qubit_gain_Start": max(
            [0, int(cfg["qubit_gain"] - int(q_gain_span))]
        ),  # - q_gain_span / 2,
        "qubit_gain_Stop": min(
            [32767, int(cfg["qubit_gain"] + int(q_gain_span))]
        ),  # *qubit_gains[Qubit_Pulse_Index] + q_gain_span / 2,
        "qubit_gain_Points": q_gain_pts,
        "qubit_freq_start": qubit_frequency_centers[Qubit_Pulse_Index] - q_freq_span,
        "qubit_freq_stop": qubit_frequency_centers[Qubit_Pulse_Index] + q_freq_span,
        "QubitNumPoints": q_freq_pts,
        "number_of_pulses": SS_Q_params["number_of_pulses"],
    }
    print(exp_parameters)
    cfg = (
        cfg | exp_parameters
    )  # preserve number_of_pulses + pi2 qubit_gain set above (mirrors original config | exp_parameters)
    g0 = qubit_gains[Qubit_Pulse_Index]
    f0 = qubit_frequency_centers[Qubit_Pulse_Index]
    # # Now lets optimize powers and readout frequencies
    Instance_SingleShotOptimize = QubitPulseOpt_wSingleShotFF(
        path="SingleShot_OptQubit",
        outerFolder=ctx.outerFolder,
        cfg=cfg,
        soc=ctx.soc,
        soccfg=ctx.soccfg,
    )
    data_SingleShotProgramOptimize = QubitPulseOpt_wSingleShotFF.acquire(
        Instance_SingleShotOptimize, Qubit_Sweep_Index=Qubit_Pulse_Index
    )
    # print(data_SingleShotProgram)
    QubitPulseOpt_wSingleShotFF.display(
        Instance_SingleShotOptimize, data_SingleShotProgramOptimize, plotDisp=True
    )
    print(exp_parameters)

    QubitPulseOpt_wSingleShotFF.save_data(
        Instance_SingleShotOptimize, data_SingleShotProgramOptimize
    )
    QubitPulseOpt_wSingleShotFF.save_config(Instance_SingleShotOptimize)
