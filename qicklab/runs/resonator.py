"""Resonator runs: constant tones, transmission fit/sweep and chi shift."""

import numpy as np

from qicklab.analysis.fitting import assess_resonator_feature, assess_resonator_fit
from qicklab.core.experiment import finish
from qicklab.experiments.chi_shift import ChiShift
from qicklab.experiments.cw_tones import ConstantTwoTone, SingleTone
from qicklab.experiments.transmission import CavitySpecFF


def run_constant_two_tone(ctx, params=None):
    """CW resonator + qubit tones until Enter (or params['hold_s'] seconds), then stopped.

    One program; the tones are stopped (soc.reset_gens()) before this returns, also on Ctrl-C.
    The tone settings are saved as the run's JSON. docs/experiments/cw_tones.md.
    """
    hold_s = (params or {}).get("hold_s")
    Instance_trans = ConstantTwoTone(
        path="ConstantTwoTone",
        cfg=ctx.working_config(),
        soc=ctx.soc,
        soccfg=ctx.soccfg,
        outerFolder=ctx.outerFolder,
    )
    Instance_trans.save_config()
    Instance_trans.acquire(hold_s=hold_s)


def run_constant_tone(ctx, params=None):
    """CW resonator tone until Enter (or params['hold_s'] seconds), then stopped (as above)."""
    hold_s = (params or {}).get("hold_s")
    Instance_trans = SingleTone(
        path="TransmissionFF",
        cfg=ctx.working_config(),
        soc=ctx.soc,
        soccfg=ctx.soccfg,
        outerFolder=ctx.outerFolder,
    )
    Instance_trans.save_config()
    Instance_trans.acquire(hold_s=hold_s)


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


def _trace_db(data):
    """(fpts MHz, |S21| dB) of the first ADC, the trace display() fits."""
    results = np.asarray(data["data"]["results"], dtype=float)
    amp = np.abs(results[0][0][0] + 1j * results[0][0][1])
    return np.asarray(data["data"]["fpts"], dtype=float), 20 * np.log10(amp)


def _carry_if_resonator(ctx, inst, data, dip=True):
    """Gate the carry-over (docs/experiments/transmission_fit.md#carry-over-gate).

    Dip: the display fit's minimum, judged by assess_resonator_fit on its popt (or the raw argmin,
    judged by assess_resonator_feature, when that fit failed). Peak: the raw argmax, judged by
    assess_resonator_feature with the sign flipped. Writes ctx.config['pulse_freq'] only when the
    gate passes; on failure prints the reasons and metrics and leaves pulse_freq unchanged.
    """
    d = data["data"]
    if dip:
        freq = _carried_dip_freq(inst, data)
        popt = d.get("hanger_fit_popt")
    else:
        freq, popt = inst.peakFreq_max, None
    try:
        x, y_db = _trace_db(data)
        if popt is not None:
            ok, reasons, metrics = assess_resonator_fit(x, y_db, popt)
        else:
            ok, reasons, metrics = assess_resonator_feature(x, y_db, freq, dip=dip)
    except Exception as err:
        ok, reasons, metrics = False, [f"gate raised {err!r}"], {}
    if ok:
        ctx.config["pulse_freq"] = freq
        return True
    print(
        f"WARNING: no resonator {'dip' if dip else 'peak'} passes the carry-over gate; "
        f"pulse_freq LEFT at {ctx.config['pulse_freq']} MHz (candidate {freq} MHz rejected):"
    )
    for reason in reasons:
        print(f"  - {reason}")
    print(
        "  metrics: "
        + ", ".join(
            f"{k}={v:.6g}" if isinstance(v, float) else f"{k}={v}" for k, v in metrics.items()
        )
    )
    return False


def run_transmission_fit(ctx, params):
    cfg = ctx.working_config()
    cfg["reps"] = params["reps"]
    cfg["rounds"] = params["rounds"]

    Instance_trans = CavitySpecFF(
        path="TransmissionFF", cfg=cfg, soc=ctx.soc, soccfg=ctx.soccfg, outerFolder=ctx.outerFolder
    )
    data_trans = CavitySpecFF.acquire(Instance_trans)
    finish(CavitySpecFF, Instance_trans, data_trans, reraise=True, plotDisp=True, figNum=1)

    # gated carry-over: docs/architecture.md#carry-overs
    carried = _carry_if_resonator(ctx, Instance_trans, data_trans, dip=True)

    freq_deviation = ctx.config["pulse_freq"] - ctx.resonator_frequency_center
    print(
        f"  deviation from resonator_frequency_center "
        f"({ctx.resonator_frequency_center:.6f}) = {freq_deviation:+.6f}"
    )
    if carried:
        print(f"Cavity frequency found at: {ctx.config['pulse_freq']:.6f}")
    else:
        print(f"Cavity frequency NOT updated: pulse_freq stays {ctx.config['pulse_freq']:.6f}")


def run_transmission_sweep(ctx, params):
    cfg = ctx.working_config()
    cfg["reps"] = params["reps"]
    cfg["rounds"] = params["rounds"]
    Instance_trans = CavitySpecFF(
        path="TransmissionFF", cfg=cfg, soc=ctx.soc, soccfg=ctx.soccfg, outerFolder=ctx.outerFolder
    )
    data_trans = CavitySpecFF.acquire(Instance_trans)
    finish(CavitySpecFF, Instance_trans, data_trans, reraise=True, plotDisp=True, figNum=1)

    # gated carry-over: docs/architecture.md#carry-overs
    if _carry_if_resonator(ctx, Instance_trans, data_trans, dip=ctx.cavity_min):
        print("Cavity frequency found at: ", ctx.config["pulse_freq"])
    else:
        print("Cavity frequency NOT updated: pulse_freq stays ", ctx.config["pulse_freq"])


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
