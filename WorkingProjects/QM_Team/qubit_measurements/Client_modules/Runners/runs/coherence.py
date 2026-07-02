from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils import *
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT1FF import T1FF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT2R import T2R
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT2EFF import T2EMUX
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT1_SS import T1_SS
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSingleShotProgramFFMUX import SingleShotProgramFFMUX
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mAutoCoherence import run_auto_coherence as _run_auto_coherence, AUTO_COHERENCE_PARAMS, find_sweet_spot
import numpy as np
import matplotlib.pyplot as plt
from .context import Context


def run_t1(ctx, T1T2_params):
    for i in range(T1T2_params['repetitions']):
        if T1T2_params['repetitions'] > 1:
            plot_disp = False
        else:
            plot_disp = True
        expt_cfg = {"start": 0, "step": T1T2_params["T1_step"], "expts": T1T2_params["T1_expts"],
                    "reps": T1T2_params["T1_reps"],"Qubit_number": ctx.Qubit_Readout,
                    "rounds": T1T2_params["T1_rounds"], "pi_gain": ctx.qubit_gain, "relax_delay": T1T2_params["relax_delay"],
                    "sigma": ctx.qubit_sigma, "flattop_length": ctx.qubit_flattop,
                    "f_ge": ctx.qubit_frequency_center
                    }

        cfg = ctx.working_config(expt_cfg)  ### note that UpdateConfig will overwrite elements in BaseConfig
        iT1 = T1FF(path="T1", cfg=cfg, soc=ctx.soc, soccfg=ctx.soccfg, outerFolder=ctx.outerFolder)
        dT1 = T1FF.acquire(iT1)
        T1FF.display(iT1, dT1, plotDisp=plot_disp, figNum=2)
        T1FF.save_data(iT1, dT1)
        T1FF.save_config(iT1)

        time.sleep(10)
        ctx.soc.reset_gens()


def run_t1_t2e(ctx, T1T2_params, T2E_params):
    for i in range(T1T2_params['repetitions']):
        # match your plotting behavior
        plot_disp = (T1T2_params['repetitions'] <= 1)

        # -------------------- T1 --------------------
        expt_cfg_T1 = {
            "start": 0,
            "step": T1T2_params["T1_step"],
            "expts": T1T2_params["T1_expts"],
            "reps": T1T2_params["T1_reps"],
            "Qubit_number": ctx.Qubit_Readout,
            "rounds": T1T2_params["T1_rounds"],
            "pi_gain": ctx.qubit_gain,
            "relax_delay": T1T2_params["relax_delay"],
            "sigma": ctx.qubit_sigma,
            "flattop_length": ctx.qubit_flattop,
            "f_ge": ctx.qubit_frequency_center,
        }

        config_T1 = ctx.working_config(expt_cfg_T1)
        iT1 = T1FF(path="T1", cfg=config_T1, soc=ctx.soc, soccfg=ctx.soccfg, outerFolder=ctx.outerFolder)
        dT1 = T1FF.acquire(iT1)
        T1FF.display(iT1, dT1, plotDisp=plot_disp, figNum=2)
        T1FF.save_data(iT1, dT1)
        T1FF.save_config(iT1)

        # -------------------- T2E immediately after --------------------
        num_pulses = T2E_params["num_pi_pulses"]

        # compute time step with your hardware quantization
        int_steps = T2E_params["T2_max_us"] // (0.00232515 * (num_pulses + 1) * T2E_params["T2_expts"])
        if int_steps == 0:
            print("[T2E] Step size is 0! need to increase total time or decrease experiments")
            break

        expt_cfg_T2E = {
            "start": 0,
            "step": 0.00232515 * (num_pulses + 1) * int_steps,
            "expts": T2E_params["T2_expts"],
            "reps": T2E_params["T2_reps"],
            "rounds": T2E_params["T2_rounds"],
            "pi_gain": ctx.qubit_gain,
            "pi2_gain": ctx.pi2_gain,
            "relax_delay": T2E_params["relax_delay"],
            "f_ge": ctx.qubit_frequency_center + T2E_params["freq_shift"],
            "num_pi_pulses": num_pulses,
            "sigma": ctx.qubit_sigma,
            "flattop_length": ctx.qubit_flattop,
            "Qubit_number": ctx.Qubit_Readout,
        }

        # optional display normalization params
        if T2E_params.get("rotation_angle", False) != False:
            expt_cfg_T2E["rotation_angle"] = T2E_params["rotation_angle"]
            expt_cfg_T2E["min_max"] = T2E_params["min_max"]

        config_T2E = ctx.working_config(expt_cfg_T2E)
        iT2E = T2EMUX(path="T2E", cfg=config_T2E, soc=ctx.soc, soccfg=ctx.soccfg, outerFolder=ctx.outerFolder)
        dT2E = T2EMUX.acquire(iT2E)
        T2EMUX.display(iT2E, dT2E, plotDisp=plot_disp, figNum=3)
        T2EMUX.save_data(iT2E, dT2E)
        T2EMUX.save_config(iT2E)

        # -------------------- between iterations --------------------
        time.sleep(10)
        ctx.soc.reset_gens()


def run_t1_t2r_t2e(ctx, T1T2_params, T2E_params):
    def _run_experiment(ExptClass, path, expt_cfg, figNum, plot_disp=False):
        cfg_run = ctx.working_config(expt_cfg)
        inst = ExptClass(path=path, cfg=cfg_run, soc=ctx.soc, soccfg=ctx.soccfg, outerFolder=ctx.outerFolder)
        data = ExptClass.acquire(inst)
        ExptClass.display(inst, data, plotDisp=plot_disp, figNum=figNum)
        ExptClass.save_data(inst, data)
        ExptClass.save_config(inst)
        return inst, data

    for i in range(T1T2_params["repetitions"]):
        plot_disp = (T1T2_params["repetitions"] <= 1)

        # -------------------- T1 --------------------
        expt_cfg_T1 = {
            "start": 0,
            "step": T1T2_params["T1_step"],
            "expts": T1T2_params["T1_expts"],
            "reps": T1T2_params["T1_reps"],
            "rounds": T1T2_params["T1_rounds"],
            "Qubit_number": ctx.Qubit_Readout,
            "pi_gain": ctx.qubit_gain,
            "relax_delay": T1T2_params["relax_delay"],
            "sigma": ctx.qubit_sigma,
            "flattop_length": ctx.qubit_flattop,
            "f_ge": ctx.qubit_frequency_center,
        }
        _run_experiment(T1FF, "T1", expt_cfg_T1, figNum=2, plot_disp=plot_disp)

        # -------------------- T2E --------------------
        num_pulses = T2E_params["num_pi_pulses"]
        int_steps = T2E_params["T2_max_us"] // (
            0.00232515 * (num_pulses + 1) * T2E_params["T2_expts"]
        )
        if int_steps == 0:
            print("[T2E] Step size is 0! need to increase total time or decrease experiments")
            break

        expt_cfg_T2E = {
            "start": 0,
            "step": 0.00232515 * (num_pulses + 1) * int_steps,
            "expts": T2E_params["T2_expts"],
            "reps": T2E_params["T2_reps"],
            "rounds": T2E_params["T2_rounds"],
            "Qubit_number": ctx.Qubit_Readout,
            "pi_gain": ctx.qubit_gain,
            "pi2_gain": ctx.pi2_gain,
            "relax_delay": T2E_params["relax_delay"],
            "f_ge": ctx.qubit_frequency_center + T2E_params["freq_shift"],
            "num_pi_pulses": num_pulses,
            "sigma": ctx.qubit_sigma,
            "flattop_length": ctx.qubit_flattop,
        }
        if T2E_params.get("rotation_angle") is not None:
            expt_cfg_T2E["rotation_angle"] = T2E_params["rotation_angle"]
            expt_cfg_T2E["min_max"] = T2E_params["min_max"]

        _run_experiment(T2EMUX, "T2E", expt_cfg_T2E, figNum=3, plot_disp=plot_disp)

        # -------------------- T2R --------------------
        expt_cfg_T2R = {
            "start": 0,
            "step": T1T2_params["T2_step"],
            "phase_step": ctx.soccfg.deg2reg(0 * 360 / 50, gen_ch=2),
            "expts": T1T2_params["T2_expts"],
            "reps": T1T2_params["T2_reps"],
            "rounds": T1T2_params["T2_rounds"],
            "pi_gain": ctx.qubit_gain,
            "pi2_gain": ctx.pi2_gain,
            "relax_delay": T1T2_params["relax_delay"],
            "f_ge": ctx.qubit_frequency_center + T1T2_params["freq_shift"],
            "sigma": ctx.qubit_sigma,
            "flattop_length": ctx.qubit_flattop,
        }
        _run_experiment(T2R, "T2R", expt_cfg_T2R, figNum=4, plot_disp=plot_disp)

        time.sleep(10)
        ctx.soc.reset_gens()


def run_t2(ctx, T1T2_params):
    T2R_cfg = {"start": 0, "step": T1T2_params["T2_step"], "phase_step": ctx.soccfg.deg2reg(0 * 360 / 50, gen_ch=2),
               "expts": T1T2_params["T2_expts"], "reps": T1T2_params["T2_reps"], "rounds": T1T2_params["T2_rounds"],
               "pi_gain": ctx.qubit_gain,
               "pi2_gain": ctx.pi2_gain, "relax_delay": T1T2_params["relax_delay"],
               'f_ge': ctx.qubit_frequency_center + T1T2_params["freq_shift"],
               "sigma": ctx.qubit_sigma, "flattop_length": ctx.qubit_flattop
               }
    for i in range(T1T2_params['repetitions']):
        cfg = ctx.working_config(T2R_cfg)  ### note that UpdateConfig will overwrite elements in BaseConfig
        iT2R = T2R(path="T2R", cfg=cfg, soc=ctx.soc, soccfg=ctx.soccfg, outerFolder=ctx.outerFolder)
        dT2R = T2R.acquire(iT2R)
        T2R.display(iT2R, dT2R, plotDisp=False, figNum=2)
        T2R.save_data(iT2R, dT2R)
        T2R.save_config(iT2R)
        time.sleep(10)
        ctx.soc.reset_gens()


def run_t2e(ctx, T2E_params):
    for i in range(T2E_params['repetitions']):
        # match T1 behavior: only show plots if single repetition
        if T2E_params['repetitions'] > 1:
            plot_disp = False
        else:
            plot_disp = True

        num_pulses = T2E_params["num_pi_pulses"]

        # compute time step with your hardware quantization
        int_steps = T2E_params["T2_max_us"] // (0.00232515 * (num_pulses + 1) * T2E_params["T2_expts"])
        print(f"[T2E rep {i}] int_steps={int_steps}, step(us)={0.00232515*(num_pulses+1)*int_steps}, expts={T2E_params['T2_expts']}")

        if int_steps == 0:
            print('Step size is 0! need to increase total time or decrease experiments')
            break  # or continue, but breaking is usually safer
        else:
            T2E_cfg = {
                "start": 0,
                "step": 0.00232515 * (num_pulses + 1) * int_steps,
                "expts": T2E_params["T2_expts"],
                "reps": T2E_params["T2_reps"],
                "rounds": T2E_params["T2_rounds"],
                "pi_gain": ctx.qubit_gain,
                "pi2_gain": ctx.pi2_gain,
                "relax_delay": T2E_params["relax_delay"],
                "f_ge": ctx.qubit_frequency_center + T2E_params["freq_shift"],
                "num_pi_pulses": num_pulses,
                "sigma": ctx.qubit_sigma,
                "flattop_length": ctx.qubit_flattop,
            }

            # optional display normalization params
            if T2E_params["rotation_angle"] != False:
                T2E_cfg["rotation_angle"] = T2E_params["rotation_angle"]
                T2E_cfg["min_max"] = T2E_params["min_max"]

            config_run = ctx.working_config(T2E_cfg)

            # new instance each repetition (like T1)
            iT2E = T2EMUX(path="T2E", cfg=config_run, soc=ctx.soc, soccfg=ctx.soccfg, outerFolder=ctx.outerFolder)

            dT2E = T2EMUX.acquire(iT2E)
            T2EMUX.display(iT2E, dT2E, plotDisp=plot_disp, figNum=2)
            T2EMUX.save_data(iT2E, dT2E)
            T2EMUX.save_config(iT2E)

            time.sleep(10)
            ctx.soc.reset_gens()


def run_t1_ss(ctx, T1SS_params, SS_params):
    for i in range(T1SS_params["repetitions"]):
        if T1SS_params["calibrate_SS"]:
            cfg = ctx.working_config()
            cfg['number_of_pulses'] = SS_params['number_of_pulses']
            Instance_SingleShotProgram = SingleShotProgramFFMUX(path="SingleShot", outerFolder=ctx.outerFolder, cfg=cfg,
                                                                soc=ctx.soc, soccfg=ctx.soccfg)
            data_SingleShotProgram = SingleShotProgramFFMUX.acquire(Instance_SingleShotProgram)
            SingleShotProgramFFMUX.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=False)
            SingleShotProgramFFMUX.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
            SingleShotProgramFFMUX.save_config(Instance_SingleShotProgram)
            angle = data_SingleShotProgram['data']['angle'][0]
            threshold = data_SingleShotProgram['data']['threshold'][0]
        else:
            angle = T1SS_params["angle"]
            threshold = T1SS_params["threshold"]
        print(angle, threshold)

        expt_cfg = {"start": 0, "step": T1SS_params["T1_step"], "expts": T1SS_params["T1_expts"],
                    'reps': T1SS_params['reps'],
                    "pi_gain": ctx.qubit_gain, "relax_delay": T1SS_params["relax_delay"]
                    }
        cfg = ctx.working_config(expt_cfg)  ### note that UpdateConfig will overwrite elements in BaseConfig
        iT1 = T1_SS(path="T1SS", cfg=cfg, soc=ctx.soc, soccfg=ctx.soccfg, outerFolder=ctx.outerFolder)
        dT1 = T1_SS.acquire(iT1, angle = angle, threshold = threshold)
        T1_SS.display(iT1, dT1, plotDisp=False, figNum=2)
        T1_SS.save_data(iT1, dT1)
        T1_SS.save_config(iT1)

        time.sleep(10)
        ctx.soc.reset_gens()


def run_auto_coherence(ctx, AutoCoherence_override_params):
    auto_results = _run_auto_coherence(
        soc=ctx.soc,
        soccfg=ctx.soccfg,
        config=ctx.working_config(),                    # full config dict built above
        outerFolder=ctx.outerFolder,
        qubit_readout=ctx.Qubit_Readout,
        qubit_params=ctx.Qubit_Parameters,
        yoko=ctx.yoko,                        # set to None if no charge line
        auto_params=AutoCoherence_override_params,
    )
    print("[AutoCoherence] Results:", auto_results)
