"""Amplitude Rabi run."""

from qicklab.core.config import check_gain
from qicklab.core.experiment import finish
from qicklab.experiments.rabi import AmplitudeRabiFF, AmplitudeRabiFF_N


def run_amplitude_rabi(ctx, params):
    check_gain("Amplitude_Rabi_params['max_gain']", params["max_gain"])
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
    if ctx.qubit_flattop is not None:
        ARabi_config = {
            "gain_start": 0,
            "gain_end": params["max_gain"],
            "gainNumPoints": number_of_steps,
            "reps": params["reps"],
            "rounds": params["rounds"],
            "sigma": ctx.qubit_sigma,
            "f_ge": params["qubit_freq"],
            "relax_delay": params.get("flattop_relax_delay", 8000),
            "flattop_length": ctx.qubit_flattop,
        }
        cfg = cfg | ARabi_config
        iAmpRabi = AmplitudeRabiFF_N(
            path="AmplitudeRabi",
            cfg=cfg,
            soc=ctx.soc,
            soccfg=ctx.soccfg,
            outerFolder=ctx.outerFolder,
        )
        dAmpRabi = AmplitudeRabiFF_N.acquire(iAmpRabi)
        finish(
            AmplitudeRabiFF_N, iAmpRabi, dAmpRabi, reraise=True, plotDisp=True, figNum=2, fit=fit
        )
    else:
        iAmpRabi = AmplitudeRabiFF(
            path="AmplitudeRabi",
            cfg=cfg,
            soc=ctx.soc,
            soccfg=ctx.soccfg,
            outerFolder=ctx.outerFolder,
        )
        dAmpRabi = AmplitudeRabiFF.acquire(iAmpRabi)
        finish(AmplitudeRabiFF, iAmpRabi, dAmpRabi, reraise=True, plotDisp=True, figNum=2, fit=fit)
