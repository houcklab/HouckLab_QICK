"""Resonator runs: constant tones, transmission fit/sweep and chi shift."""

import matplotlib.pyplot as plt
import numpy as np

from qicklab.analysis.fitting import fit_hanger_transmission
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


def run_transmission_fit(ctx, params):
    cfg = ctx.working_config()
    cfg["reps"] = params["reps"]
    cfg["rounds"] = params["rounds"]

    Instance_trans = CavitySpecFF(
        path="TransmissionFF", cfg=cfg, soc=ctx.soc, soccfg=ctx.soccfg, outerFolder=ctx.outerFolder
    )
    data_trans = CavitySpecFF.acquire(Instance_trans)
    CavitySpecFF.display(Instance_trans, data_trans, plotDisp=True, figNum=1)
    CavitySpecFF.save_data(Instance_trans, data_trans)
    CavitySpecFF.save_config(Instance_trans)

    sig = data_trans["data"]["results"][0][0][0] + 1j * data_trans["data"]["results"][0][0][1]
    x_pts = np.asarray(data_trans["data"]["fpts"])

    y_mag = np.abs(sig)
    y_db = 20 * np.log10(y_mag)

    idx_min = np.argmin(y_db)
    center_guess = x_pts[idx_min]

    startpoint = [
        center_guess,  # f0
        4.1e4,  # Qtot
        4.3e4,  # Qext
        1e3,  # asym
        0.0,  # offset
    ]

    fit_result = fit_hanger_transmission(freq=x_pts, amp_db=y_db, startpoint=startpoint)

    popt = fit_result["popt"]
    perr = fit_result["perr"]

    f0_fit, Qtot_fit, Qext_fit, asym_fit, offset_fit = popt
    df0_fit, dQtot_fit, dQext_fit, dasym_fit, doffset_fit = perr
    Qint_fit = fit_result["Qint"]

    ctx.config["pulse_freq"] = f0_fit  # carry-over: docs/architecture.md#carry-overs

    freq_deviation = f0_fit - ctx.resonator_frequency_center
    kappa_mhz = (f0_fit / Qext_fit) / 1e6

    print("Hanger resonator fit:")
    print(f"  f0       = {f0_fit:.6f} ± {df0_fit:.6f}")
    print(f"  Qtot     = {Qtot_fit:.6e} ± {dQtot_fit:.6e}")
    print(f"  Qext     = {Qext_fit:.6e} ± {dQext_fit:.6e}")
    print(f"  Qint     = {Qint_fit:.6e}")
    print(f"  kappa    = {kappa_mhz:.6f} MHz")
    print(f"  asym     = {asym_fit:.6e} ± {dasym_fit:.6e}")
    print(f"  offset   = {offset_fit:.6e} ± {doffset_fit:.6e}")
    print(
        f"  deviation from resonator_frequency_center "
        f"({ctx.resonator_frequency_center:.6f}) = {freq_deviation:+.6f}"
    )
    print(f"Cavity frequency found at: {ctx.config['pulse_freq']:.6f}")

    x_fit = np.linspace(np.min(x_pts), np.max(x_pts), 2000)
    y_fit = fit_result["model"](x_fit, *popt)

    fit_min_idx = np.argmin(y_fit)
    fit_min_freq = x_fit[fit_min_idx]

    fig_num_fit = 100
    while plt.fignum_exists(fig_num_fit):
        fig_num_fit += 1

    min_freq = x_pts[idx_min]

    plt.figure(fig_num_fit)
    plt.plot(x_pts, y_db, "o", label="|sig| data (dB)")
    plt.plot(x_fit, y_fit, "-", linewidth=2, label=f"Hanger fit\nf0={f0_fit:.6f} ± {df0_fit:.6f}")
    plt.axvline(
        ctx.resonator_frequency_center,
        linestyle="--",
        color="gray",
        label=f"input center = {ctx.resonator_frequency_center:.6f}",
    )
    plt.axvline(fit_min_freq, linestyle=":", color="red", label=f"fit minimum = {fit_min_freq:.6f}")
    plt.axvline(min_freq, linestyle=":", color="blue", label=f"min freq = {min_freq:.6f}")
    plt.xlabel("Frequency")
    plt.ylabel("Transmission (dB)")
    plt.title("Transmission sweep with hanger fit")
    plt.legend()
    plt.tight_layout()
    plt.show()


def run_transmission_sweep(ctx, params):
    cfg = ctx.working_config()
    cfg["reps"] = 20
    cfg["rounds"] = 20
    Instance_trans = CavitySpecFF(
        path="TransmissionFF", cfg=cfg, soc=ctx.soc, soccfg=ctx.soccfg, outerFolder=ctx.outerFolder
    )
    data_trans = CavitySpecFF.acquire(Instance_trans)
    CavitySpecFF.display(Instance_trans, data_trans, plotDisp=True, figNum=1)
    CavitySpecFF.save_data(Instance_trans, data_trans)
    CavitySpecFF.save_config(Instance_trans)

    if ctx.cavity_min:  # carry-over: docs/architecture.md#carry-overs
        ctx.config["pulse_freq"] = Instance_trans.peakFreq_min
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
    ChiShift.display(iChi, dChi, plotDisp=True, figNum=1)
    ChiShift.save_data(iChi, dChi)
    ChiShift.save_config(iChi)
