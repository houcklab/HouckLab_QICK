"""Single-shot readout routines: blob calibration, undriven shots, readout/pulse optimisation, T1 single-shot."""

import time

import numpy as np

from qicklab.core.experiment import finish
from qicklab.experiments.readout_optimize import QubitPulseOpt_wSingleShotFF, ReadOpt_wSingleShotFF
from qicklab.experiments.single_shot import SingleShotProgramFFMUX
from qicklab.experiments.t1_single_shot import T1_SS, readout_assignment_errors
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
    finish(SingleShotProgramFFMUX, inst_ss, data_ss, reraise=True, plotDisp=False)

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


# Below this g/e contrast the T1_SS threshold barely separates the blobs (warn only).
T1SS_MIN_CALIBRATION_CONTRAST = 0.3


def _check_t1ss_discriminator(angle, threshold, source):
    """Raise ValueError unless `angle` and `threshold` are finite real numbers.

    A NaN threshold makes every shot count as |g> (val > nan is False), so the whole T1 curve
    would read 0 with no error; None raises a TypeError deep in the counting step.
    """
    for name, value in (("angle", angle), ("threshold", threshold)):
        try:
            ok = np.isfinite(float(value))
        except (TypeError, ValueError):
            ok = False
        if not ok:
            raise ValueError(
                f"run_t1_ss: {source} {name} is {value!r}, not a finite number; "
                "T1_SS would count every shot against it. See docs/experiments/t1_single_shot.md"
            )


def run_t1_ss(ctx, T1SS_params, SS_params):
    """T1 from thresholded single shots, `repetitions` times.

    Keys: docs/experiments/t1_single_shot.md.

    With calibrate_SS the angle/threshold come from a g / one-pi-pulse single_shot at the pi
    gain; the single_shot group's number_of_pulses and pi2_SS are not used (`SS_params` is kept
    for the call signature).
    """
    for _ in range(T1SS_params["repetitions"]):
        cfg = ctx.working_config()
        if T1SS_params["calibrate_SS"]:
            # Separate cfg: always one pi pulse at the pi gain (as in
            # get_apriori_separator_from_singleshot); nothing leaks into the T1 cfg.
            cfg_cal = ctx.working_config({"number_of_pulses": 1, "qubit_gain": ctx.qubit_gain})
            Instance_SingleShotProgram = SingleShotProgramFFMUX(
                path="SingleShot",
                outerFolder=ctx.outerFolder,
                cfg=cfg_cal,
                soc=ctx.soc,
                soccfg=ctx.soccfg,
            )
            data_SingleShotProgram = SingleShotProgramFFMUX.acquire(Instance_SingleShotProgram)
            finish(
                SingleShotProgramFFMUX,
                Instance_SingleShotProgram,
                data_SingleShotProgram,
                plotDisp=False,
            )
            if data_SingleShotProgram["data"].get("thermal_mode"):
                raise ValueError(
                    "run_t1_ss: the calibration single_shot ran in thermal mode; "
                    "its threshold is not a g/e discriminator"
                )
            angle = data_SingleShotProgram["data"]["angle"][0]
            threshold = data_SingleShotProgram["data"]["threshold"][0]
            _check_t1ss_discriminator(angle, threshold, "calibrated")
            # P(e|g), P(g|e) of the calibration shots under this angle/threshold, for the
            # readout-corrected curve (docs/experiments/t1_single_shot.md#analysis).
            readout_errors = readout_assignment_errors(
                *_extract_iq_from_singleshot_data(data_SingleShotProgram, "g"),
                *_extract_iq_from_singleshot_data(data_SingleShotProgram, "e"),
                angle,
                threshold,
            )
            print(
                f"[T1_SS] calibration P(e|g) = {readout_errors[0]:.4f}, "
                f"P(g|e) = {readout_errors[1]:.4f}"
            )
            # hist_process contrast (labelled fid); display() may overwrite the list with read 0's.
            contrast = np.ravel(np.asarray(Instance_SingleShotProgram.fid, dtype=float))[0]
            if contrast < T1SS_MIN_CALIBRATION_CONTRAST:
                print(
                    f"[T1_SS] WARNING calibration contrast {contrast:.3f} < "
                    f"{T1SS_MIN_CALIBRATION_CONTRAST}: the threshold barely separates g and e"
                )
        else:
            angle = T1SS_params["angle"]
            threshold = T1SS_params["threshold"]
            _check_t1ss_discriminator(angle, threshold, "T1SS_params")
            readout_errors = None
        print(angle, threshold)

        expt_cfg = {
            "start": 0,
            "step": T1SS_params["T1_step"],
            "expts": T1SS_params["T1_expts"],
            "reps": T1SS_params["reps"],
            "pi_gain": ctx.qubit_gain,
            "relax_delay": T1SS_params["relax_delay"],
        }
        cfg = cfg | expt_cfg
        iT1 = T1_SS(
            path="T1SS", cfg=cfg, soc=ctx.soc, soccfg=ctx.soccfg, outerFolder=ctx.outerFolder
        )
        dT1 = T1_SS.acquire(iT1, angle=angle, threshold=threshold, readout_errors=readout_errors)
        finish(T1_SS, iT1, dT1, plotDisp=False, figNum=2)

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
    finish(
        SingleShotProgramFFMUX,
        Instance_SingleShotProgram,
        data_SingleShotProgram,
        reraise=True,
        plotDisp=True,
    )
    print("Angle: ", data_SingleShotProgram["data"]["angle"][0])
    print("threshold: ", data_SingleShotProgram["data"]["threshold"][0])


def run_undriven_single_shot(ctx, US_params=None):
    """Single-shot readout with the qubit drive off, `Repeat` passes; returns per-pass data.

    Uses the single-shot-regime config; `US_params` keys: docs/experiments/undriven_single_shot.md
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
    # the charge range must come via US_params: the regime-B config has no charge_params
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
        cfg = ctx.working_config(overrides)  # fresh per pass: the program mutates it
        inst = UndrivenSingleShot(
            path="UndrivenSingleShot",
            outerFolder=ctx.outerFolder,
            cfg=cfg,
            soc=ctx.soc,
            soccfg=ctx.soccfg,
            yoko=ctx.yoko,
        )
        data = UndrivenSingleShot.acquire(inst)
        # only the last pass on screen: plotDisp blocks until the window is closed
        finish(UndrivenSingleShot, inst, data, plotDisp=plot_disp and k == n_repeat - 1)
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
        "cav_gain_Start": cav_gain_start,
        "cav_gain_Stop": cav_gain_stop,
        "cav_gain_Points": cav_gain_pts,
        "trans_freq_start": cfg["pulse_freq"] - span / 2,
        "trans_freq_stop": cfg["pulse_freq"] + span / 2,
        "TransNumPoints": cav_trans_pts,
    }
    cfg = cfg | exp_parameters
    Instance_SingleShotOptimize = ReadOpt_wSingleShotFF(
        path="SingleShot_OptReadout",
        outerFolder=ctx.outerFolder,
        cfg=cfg,
        soc=ctx.soc,
        soccfg=ctx.soccfg,
    )
    data_SingleShotProgramOptimize = ReadOpt_wSingleShotFF.acquire(Instance_SingleShotOptimize)
    finish(
        ReadOpt_wSingleShotFF,
        Instance_SingleShotOptimize,
        data_SingleShotProgramOptimize,
        reraise=True,
        plotDisp=True,
    )


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
        "qubit_gain_Start": max([0, int(cfg["qubit_gain"] - int(q_gain_span))]),
        "qubit_gain_Stop": min([32767, int(cfg["qubit_gain"] + int(q_gain_span))]),
        "qubit_gain_Points": q_gain_pts,
        "qubit_freq_start": qubit_frequency_centers[Qubit_Pulse_Index] - q_freq_span,
        "qubit_freq_stop": qubit_frequency_centers[Qubit_Pulse_Index] + q_freq_span,
        "QubitNumPoints": q_freq_pts,
        "number_of_pulses": SS_Q_params["number_of_pulses"],
    }
    print(exp_parameters)
    cfg = cfg | exp_parameters
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
    finish(
        QubitPulseOpt_wSingleShotFF,
        Instance_SingleShotOptimize,
        data_SingleShotProgramOptimize,
        reraise=True,
        plotDisp=True,
    )
    print(exp_parameters)
