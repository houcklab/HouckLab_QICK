"""T1 / T2 Ramsey / T2 echo measurement routines and their combinations."""

import time

from qicklab.core.experiment import finish
from qicklab.experiments.t1 import T1FF
from qicklab.experiments.t2_echo import T2EMUX, quantised_t2e_step
from qicklab.experiments.t2_ramsey import T2R, ramsey_virtual_detuning


def run_t1(ctx, T1T2_params):
    for _ in range(T1T2_params["repetitions"]):
        # explicit plotDisp wins: docs/experiments/interleaved_coherence.md
        plot_disp = T1T2_params.get("plotDisp", T1T2_params["repetitions"] <= 1)
        expt_cfg = {
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

        cfg = ctx.working_config(expt_cfg)
        iT1 = T1FF(path="T1", cfg=cfg, soc=ctx.soc, soccfg=ctx.soccfg, outerFolder=ctx.outerFolder)
        dT1 = T1FF.acquire(iT1)
        finish(T1FF, iT1, dT1, plotDisp=plot_disp, figNum=2)

        time.sleep(10)
        ctx.soc.reset_gens()


def run_t1_t2e(ctx, T1T2_params, T2E_params):
    for _ in range(T1T2_params["repetitions"]):
        plot_disp = T1T2_params["repetitions"] <= 1

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
        iT1 = T1FF(
            path="T1", cfg=config_T1, soc=ctx.soc, soccfg=ctx.soccfg, outerFolder=ctx.outerFolder
        )
        dT1 = T1FF.acquire(iT1)
        finish(T1FF, iT1, dT1, plotDisp=plot_disp, figNum=2)

        num_pulses = T2E_params["num_pi_pulses"]
        int_steps, t2e_step = quantised_t2e_step(
            ctx.soccfg, T2E_params["T2_max_us"], T2E_params["T2_expts"], num_pulses
        )
        if int_steps == 0:
            print("[T2E] Step size is 0! need to increase total time or decrease experiments")
            break

        expt_cfg_T2E = {
            "start": 0,
            "step": t2e_step,
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
        if T2E_params.get("rotation_angle", False) != False:  # noqa: E712 (None passes)
            expt_cfg_T2E["rotation_angle"] = T2E_params["rotation_angle"]
            expt_cfg_T2E["min_max"] = T2E_params["min_max"]

        config_T2E = ctx.working_config(expt_cfg_T2E)
        iT2E = T2EMUX(
            path="T2E", cfg=config_T2E, soc=ctx.soc, soccfg=ctx.soccfg, outerFolder=ctx.outerFolder
        )
        dT2E = T2EMUX.acquire(iT2E)
        finish(T2EMUX, iT2E, dT2E, plotDisp=plot_disp, figNum=3)

        time.sleep(10)
        ctx.soc.reset_gens()


def run_t1_t2r_t2e(ctx, T1T2_params, T2E_params):
    def _run_experiment(ExptClass, path, expt_cfg, figNum, plot_disp=False):
        cfg_run = ctx.working_config(expt_cfg)
        inst = ExptClass(
            path=path, cfg=cfg_run, soc=ctx.soc, soccfg=ctx.soccfg, outerFolder=ctx.outerFolder
        )
        data = ExptClass.acquire(inst)
        finish(ExptClass, inst, data, plotDisp=plot_disp, figNum=figNum)
        return inst, data

    for _ in range(T1T2_params["repetitions"]):
        plot_disp = T1T2_params["repetitions"] <= 1

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

        num_pulses = T2E_params["num_pi_pulses"]
        int_steps, t2e_step = quantised_t2e_step(
            ctx.soccfg, T2E_params["T2_max_us"], T2E_params["T2_expts"], num_pulses
        )
        if int_steps == 0:
            print("[T2E] Step size is 0! need to increase total time or decrease experiments")
            break

        expt_cfg_T2E = {
            "start": 0,
            "step": t2e_step,
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

        expt_cfg_T2R = {
            "start": 0,
            "step": T1T2_params["T2_step"],
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
        # virtual detuning: docs/experiments/t2_ramsey.md#virtual-detuning
        expt_cfg_T2R.update(
            ramsey_virtual_detuning(
                ctx.soccfg, ctx.working_config(expt_cfg_T2R), T1T2_params.get("f_virt_mhz")
            )
        )
        _run_experiment(T2R, "T2R", expt_cfg_T2R, figNum=4, plot_disp=plot_disp)

        time.sleep(10)
        ctx.soc.reset_gens()


def run_t2(ctx, T1T2_params):
    T2R_cfg = {
        "start": 0,
        "step": T1T2_params["T2_step"],
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
    # virtual detuning: docs/experiments/t2_ramsey.md#virtual-detuning
    T2R_cfg.update(
        ramsey_virtual_detuning(
            ctx.soccfg, ctx.working_config(T2R_cfg), T1T2_params.get("f_virt_mhz")
        )
    )
    for _ in range(T1T2_params["repetitions"]):
        cfg = ctx.working_config(T2R_cfg)
        iT2R = T2R(path="T2R", cfg=cfg, soc=ctx.soc, soccfg=ctx.soccfg, outerFolder=ctx.outerFolder)
        dT2R = T2R.acquire(iT2R)
        finish(T2R, iT2R, dT2R, plotDisp=False, figNum=2)
        time.sleep(10)
        ctx.soc.reset_gens()


def run_t2e(ctx, T2E_params):
    for i in range(T2E_params["repetitions"]):
        # explicit plotDisp wins: docs/experiments/interleaved_coherence.md
        plot_disp = T2E_params.get("plotDisp", T2E_params["repetitions"] <= 1)

        num_pulses = T2E_params["num_pi_pulses"]
        int_steps, t2e_step = quantised_t2e_step(
            ctx.soccfg, T2E_params["T2_max_us"], T2E_params["T2_expts"], num_pulses
        )
        print(
            f"[T2E rep {i}] int_steps={int_steps}, step(us)={t2e_step}, expts={T2E_params['T2_expts']}"
        )

        if int_steps == 0:
            print("Step size is 0! need to increase total time or decrease experiments")
            break
        else:
            T2E_cfg = {
                "start": 0,
                "step": t2e_step,
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
            if T2E_params["rotation_angle"] != False:  # noqa: E712 (None passes)
                T2E_cfg["rotation_angle"] = T2E_params["rotation_angle"]
                T2E_cfg["min_max"] = T2E_params["min_max"]

            config_run = ctx.working_config(T2E_cfg)
            iT2E = T2EMUX(
                path="T2E",
                cfg=config_run,
                soc=ctx.soc,
                soccfg=ctx.soccfg,
                outerFolder=ctx.outerFolder,
            )

            dT2E = T2EMUX.acquire(iT2E)
            finish(T2EMUX, iT2E, dT2E, plotDisp=plot_disp, figNum=2)

            time.sleep(10)
            ctx.soc.reset_gens()
