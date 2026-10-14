"""Resonator runs: constant tones, transmission fit/sweep and chi shift."""

from qicklab.core.experiment import finish
from qicklab.experiments.chi_shift import ChiShift
from qicklab.experiments.cw_tones import ConstantTwoTone, SingleTone
from qicklab.experiments.transmission import CavitySpecFF


def run_constant_two_tone(ctx, params=None):
    for _ in range(1000000):
        Instance_trans = ConstantTwoTone(
            path="ConstantTwoTone",
            cfg=ctx.working_config(),
            soc=ctx.soc,
            soccfg=ctx.soccfg,
            outerFolder=ctx.outerFolder,
        )
        Instance_trans.acquire()


def run_constant_tone(ctx, params=None):
    Instance_trans = SingleTone(
        path="TransmissionFF",
        cfg=ctx.working_config(),
        soc=ctx.soc,
        soccfg=ctx.soccfg,
        outerFolder=ctx.outerFolder,
    )
    SingleTone.acquire(Instance_trans)


def _carried_dip_freq(inst, data):
    """Readout frequency to carry from a finished CavitySpecFF: the display fit's minimum.

    Falls back to the raw argmin of |S21| (``peakFreq_min`` from acquire) with a warning when
    display()'s hanger fit failed. See docs/architecture.md#carry-overs.
    """
    if "hanger_fit_min_freq_mhz" in data["data"]:
        return float(data["data"]["hanger_fit_min_freq_mhz"])
    print(
        "WARNING: hanger fit failed (no hanger_fit_min_freq_mhz in the data); carrying the RAW "
        f"argmin of |S21| = {inst.peakFreq_min} MHz as pulse_freq. Check the transmission PNG."
    )
    return inst.peakFreq_min


def run_transmission_fit(ctx, params):
    cfg = ctx.working_config()
    cfg["reps"] = params["reps"]
    cfg["rounds"] = params["rounds"]

    Instance_trans = CavitySpecFF(
        path="TransmissionFF", cfg=cfg, soc=ctx.soc, soccfg=ctx.soccfg, outerFolder=ctx.outerFolder
    )
    data_trans = CavitySpecFF.acquire(Instance_trans)
    finish(CavitySpecFF, Instance_trans, data_trans, reraise=True, plotDisp=True, figNum=1)

    # carry-over: docs/architecture.md#carry-overs
    ctx.config["pulse_freq"] = _carried_dip_freq(Instance_trans, data_trans)

    freq_deviation = ctx.config["pulse_freq"] - ctx.resonator_frequency_center
    print(
        f"  deviation from resonator_frequency_center "
        f"({ctx.resonator_frequency_center:.6f}) = {freq_deviation:+.6f}"
    )
    print(f"Cavity frequency found at: {ctx.config['pulse_freq']:.6f}")


def run_transmission_sweep(ctx, params):
    cfg = ctx.working_config()
    cfg["reps"] = 20
    cfg["rounds"] = 20
    Instance_trans = CavitySpecFF(
        path="TransmissionFF", cfg=cfg, soc=ctx.soc, soccfg=ctx.soccfg, outerFolder=ctx.outerFolder
    )
    data_trans = CavitySpecFF.acquire(Instance_trans)
    finish(CavitySpecFF, Instance_trans, data_trans, reraise=True, plotDisp=True, figNum=1)

    if ctx.cavity_min:  # carry-over: docs/architecture.md#carry-overs
        ctx.config["pulse_freq"] = _carried_dip_freq(Instance_trans, data_trans)
    else:
        ctx.config["pulse_freq"] = Instance_trans.peakFreq_max
    print("Cavity frequency found at: ", ctx.config["pulse_freq"])


def run_chi_shift(ctx, params):
    updated_params = {
        "pi_gain": ctx.qubit_gain,
        "sigma": ctx.qubit_sigma,
        "f_ge": ctx.qubit_frequency_center,
        "flattop_length": ctx.qubit_flattop,
    }
    cfg = ctx.working_config(params, updated_params)
    iChi = ChiShift(
        path="ChiShift", cfg=cfg, soc=ctx.soc, soccfg=ctx.soccfg, outerFolder=ctx.outerFolder
    )
    dChi = ChiShift.acquire(iChi)
    finish(ChiShift, iChi, dChi, reraise=True, plotDisp=True, figNum=1)
