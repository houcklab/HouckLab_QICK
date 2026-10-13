"""Amplitude Rabi run."""

from qicklab.experiments.rabi import AmplitudeRabiFF, AmplitudeRabiFF_N


def run_amplitude_rabi(ctx, params):
    cfg = ctx.working_config()
    number_of_steps = params["number_of_steps"]
    step = int(params["max_gain"] / number_of_steps)
    ARabi_config = {
        "start": 0,
        "step": step,
        "expts": number_of_steps,
        "reps": params["reps"],
        "rounds": params["rounds"],
        "sigma": ctx.qubit_sigma,
        "f_ge": params["qubit_freq"],
        "relax_delay": params["relax_delay"],
        "flattop_length": ctx.qubit_flattop,
        "Qubit_number": ctx.Qubit_Pulse,
    }

    fit = params["fit"]

    cfg = cfg | ARabi_config
    if ctx.qubit_flattop != None:
        ARabi_config = {
            "gain_start": 0,
            "gain_end": params["max_gain"],
            "gainNumPoints": number_of_steps,
            "reps": params["reps"],
            "rounds": params["rounds"],
            "sigma": ctx.qubit_sigma,
            "f_ge": params["qubit_freq"],
            "relax_delay": 8000,
            "flattop_length": ctx.qubit_flattop,
        }
        cfg = cfg | ARabi_config  ### note that UpdateConfig will overwrite elements in BaseConfig
        iAmpRabi = AmplitudeRabiFF_N(
            path="AmplitudeRabi",
            cfg=cfg,
            soc=ctx.soc,
            soccfg=ctx.soccfg,
            outerFolder=ctx.outerFolder,
        )
        dAmpRabi = AmplitudeRabiFF_N.acquire(iAmpRabi)
        AmplitudeRabiFF_N.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2, fit=fit)
        AmplitudeRabiFF_N.save_data(iAmpRabi, dAmpRabi)
        AmplitudeRabiFF_N.save_config(iAmpRabi)
    else:
        iAmpRabi = AmplitudeRabiFF(
            path="AmplitudeRabi",
            cfg=cfg,
            soc=ctx.soc,
            soccfg=ctx.soccfg,
            outerFolder=ctx.outerFolder,
        )
        dAmpRabi = AmplitudeRabiFF.acquire(iAmpRabi)
        AmplitudeRabiFF.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2, fit=fit)
        AmplitudeRabiFF.save_data(iAmpRabi, dAmpRabi)
        AmplitudeRabiFF.save_config(iAmpRabi)
