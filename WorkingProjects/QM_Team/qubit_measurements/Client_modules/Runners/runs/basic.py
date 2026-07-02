from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils import *
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mTransmissionFF import CavitySpecFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSingleTone import SingleTone
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mConstantTwoTone import ConstantTwoTone
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSpecSliceFF import QubitSpecSliceFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mChiShift import ChiShift
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mAmplitudeRabiFF import AmplitudeRabiFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mAmplitudeRabiFF_noUpdate import AmplitudeRabiFF_N
import numpy as np
import matplotlib.pyplot as plt
from .context import Context, sanity_dump


def run_constant_two_tone(ctx, params=None):
    for i in range(1000000):
        Instance_trans = ConstantTwoTone(
            path="ConstantTwoTone",
            cfg=ctx.working_config(),
            soc=ctx.soc,
            soccfg=ctx.soccfg,
            outerFolder=ctx.outerFolder
        )
        data_trans = Instance_trans.acquire()


def run_constant_tone(ctx, params=None):
    Instance_trans = SingleTone(path="TransmissionFF", cfg=ctx.working_config(), soc=ctx.soc, soccfg=ctx.soccfg,
                                  outerFolder=ctx.outerFolder)
    data_trans = SingleTone.acquire(Instance_trans)


def run_transmission_fit(ctx, params):

    cfg = ctx.working_config()

    # -------------------- acquire transmission --------------------
    cfg["reps"] = params['reps']
    cfg["rounds"] = params['rounds']

    Instance_trans = CavitySpecFF(
        path="TransmissionFF",
        cfg=cfg,
        soc=ctx.soc,
        soccfg=ctx.soccfg,
        outerFolder=ctx.outerFolder
    )
    data_trans = CavitySpecFF.acquire(Instance_trans)
    CavitySpecFF.display(Instance_trans, data_trans, plotDisp=True, figNum=1)
    CavitySpecFF.save_data(Instance_trans, data_trans)
    CavitySpecFF.save_config(Instance_trans)

    sig = (
        data_trans['data']['results'][0][0][0]
        + 1j * data_trans['data']['results'][0][0][1]
    )
    x_pts = np.asarray(data_trans['data']['fpts'])

    y_mag = np.abs(sig)
    y_db = 20 * np.log10(y_mag)

    idx_min = np.argmin(y_db)
    center_guess = x_pts[idx_min]

    startpoint = [
        center_guess,   # f0
        4.1e4,          # Qtot
        4.3e4,          # Qext
        1e3,            # asym
        0.0             # offset
    ]

    fit_result = fit_hanger_transmission(
        freq=x_pts,
        amp_db=y_db,
        startpoint=startpoint
    )

    popt = fit_result["popt"]
    perr = fit_result["perr"]

    f0_fit, Qtot_fit, Qext_fit, asym_fit, offset_fit = popt
    df0_fit, dQtot_fit, dQext_fit, dasym_fit, doffset_fit = perr
    Qint_fit = fit_result["Qint"]

    # update config with fitted center frequency
    ctx.config["pulse_freq"] = f0_fit

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

    # -------------------- plot fit over data --------------------
    x_fit = np.linspace(np.min(x_pts), np.max(x_pts), 2000)
    y_fit = fit_result["model"](x_fit, *popt)

    fit_min_idx = np.argmin(y_fit)
    fit_min_freq = x_fit[fit_min_idx]
    fit_min_val = y_fit[fit_min_idx]

    fig_num_fit = 100
    while plt.fignum_exists(fig_num_fit):
        fig_num_fit += 1

    min_freq = x_pts[idx_min]

    plt.figure(fig_num_fit)
    plt.plot(x_pts, y_db, 'o', label='|sig| data (dB)')
    plt.plot(
        x_fit, y_fit, '-', linewidth=2,
        label=f'Hanger fit\nf0={f0_fit:.6f} ± {df0_fit:.6f}'
    )
    plt.axvline(
        ctx.resonator_frequency_center, linestyle='--', color='gray',
        label=f'input center = {ctx.resonator_frequency_center:.6f}'
    )
    plt.axvline(
        fit_min_freq, linestyle=':', color='red',
        label=f'fit minimum = {fit_min_freq:.6f}'
    )
    plt.axvline(
        min_freq, linestyle=':', color='blue',
        label=f'min freq = {min_freq:.6f}'
    )
    plt.xlabel("Frequency")
    plt.ylabel("Transmission (dB)")
    plt.title("Transmission sweep with hanger fit")
    plt.legend()
    plt.tight_layout()
    plt.show()


# perform the cavity transmission experiment
def run_transmission_sweep(ctx, params):
    cfg = ctx.working_config()
    cfg["reps"] = 20  # fast axis number of points
    cfg["rounds"] = 20  # slow axis number of points
    Instance_trans = CavitySpecFF(path="TransmissionFF", cfg=cfg, soc=ctx.soc, soccfg=ctx.soccfg,
                                  outerFolder=ctx.outerFolder)
    data_trans = CavitySpecFF.acquire(Instance_trans)
    CavitySpecFF.display(Instance_trans, data_trans, plotDisp=True, figNum=1)
    CavitySpecFF.save_data(Instance_trans, data_trans)
    CavitySpecFF.save_config(Instance_trans)

    # update the transmission frequency to be the peak
    if ctx.cavity_min:
        ctx.config["pulse_freq"] = Instance_trans.peakFreq_min
    else:
        ctx.config["pulse_freq"] = Instance_trans.peakFreq_max
    print("Cavity frequency found at: ", ctx.config["pulse_freq"])


# qubit spec experiment
def run_two_tone_spec(ctx, params):
    cfg = ctx.working_config()
    cfg["reps"] = params['reps']
    cfg["rounds"] = params['rounds']
    cfg["Gauss"] = params['Gauss']
    if params['Gauss']:
        cfg['sigma'] = params["sigma"]
        cfg["qubit_gain"] = params['gain']

    cfg["qubit_gain"] = params['gain']

    cfg["qubit_length"] = params["qubit_length"]
    cfg["SpecSpan"] = params["SpecSpan"]
    cfg["SpecNumPoints"] = params["SpecNumPoints"]
    cfg["step"] = 2 * cfg["SpecSpan"] / cfg["SpecNumPoints"]
    cfg["start"] = ctx.qubit_frequency_center - cfg["SpecSpan"]
    cfg["expts"] = cfg["SpecNumPoints"]
    cfg['relax_delay'] = params['relax_delay']
    display = params['display']
    min_sep = params['min_sep_MHz']

    Instance_specSlice = QubitSpecSliceFF(
        path="QubitSpecFF",
        cfg=cfg,
        soc=ctx.soc,
        soccfg=ctx.soccfg,
        outerFolder=ctx.outerFolder
    )
    data_specSlice = QubitSpecSliceFF.acquire(Instance_specSlice)
    QubitSpecSliceFF.display(Instance_specSlice, data_specSlice, plotDisp=display, figNum=2, min_sep=min_sep,
                             fit_window_mhz = 0.5, prominent_ratio = 0.1) # can change to True
    QubitSpecSliceFF.save_data(Instance_specSlice, data_specSlice)
    QubitSpecSliceFF.save_config(Instance_specSlice)


# Nested gain × qubit_length sweep.
# For each length in sweep_lengths, runs a full qubit spec at every gain in sweep_gains.
# qubit_gain and qubit_length appear in every saved plot title for easy identification.
def run_spec_gain_length_sweep(ctx, params):
    cfg = ctx.working_config()
    sweep_lengths = params['sweep_lengths']
    sweep_gains   = params['sweep_gains']

    _disp  = params['display']
    _minsep = params['min_sep_MHz']
    _fw    = params.get('fit_window_mhz', 0.5)
    _pr    = params.get('prominent_ratio', 0.1)

    for q_length in sweep_lengths:
        for q_gain in sweep_gains:
            print(f"\n=== GainLengthSweep: qubit_length={q_length} µs  qubit_gain={q_gain} ===")

            cfg["reps"]          = params['reps']
            cfg["rounds"]        = params['rounds']
            cfg["Gauss"]         = params['Gauss']
            cfg["qubit_gain"]    = q_gain
            cfg["qubit_length"]  = q_length
            cfg["SpecSpan"]      = params["SpecSpan"]
            cfg["SpecNumPoints"] = params["SpecNumPoints"]
            cfg["step"]          = 2 * cfg["SpecSpan"] / cfg["SpecNumPoints"]
            cfg["start"]         = ctx.qubit_frequency_center - cfg["SpecSpan"]
            cfg["expts"]         = cfg["SpecNumPoints"]
            cfg["relax_delay"]   = params['relax_delay']
            if params['Gauss']:
                cfg['sigma'] = params["sigma"]

            _inst = QubitSpecSliceFF(
                path="QubitSpecFF",
                cfg=cfg,
                soc=ctx.soc,
                soccfg=ctx.soccfg,
                outerFolder=ctx.outerFolder,
            )
            _data = QubitSpecSliceFF.acquire(_inst)
            QubitSpecSliceFF.display(_inst, _data, plotDisp=_disp, figNum=2,
                                     min_sep=_minsep, fit_window_mhz=_fw,
                                     prominent_ratio=_pr)
            QubitSpecSliceFF.save_data(_inst, _data)
            QubitSpecSliceFF.save_config(_inst)


def run_chi_shift(ctx, params):
    updated_params = {
        "pi_gain": ctx.qubit_gain,
        "sigma": ctx.qubit_sigma, "f_ge": ctx.qubit_frequency_center,
        "flattop_length": ctx.qubit_flattop
    }
    cfg = ctx.working_config(params, updated_params)
    iChi = ChiShift(path="ChiShift", cfg=cfg, soc=ctx.soc, soccfg=ctx.soccfg,
                    outerFolder=ctx.outerFolder)
    dChi = ChiShift.acquire(iChi)
    ChiShift.display(iChi, dChi, plotDisp=True, figNum=1)
    ChiShift.save_data(iChi, dChi)
    ChiShift.save_config(iChi)


def run_amplitude_rabi(ctx, params):
    cfg = ctx.working_config()
    number_of_steps = params["number_of_steps"]
    step = int(params["max_gain"] / number_of_steps)
    ARabi_config = {'start': 0, 'step': step, "expts": number_of_steps, "reps": params['reps'],
                    "rounds": params['rounds'],
                    "sigma": ctx.qubit_sigma, "f_ge": params["qubit_freq"],
                    "relax_delay": params["relax_delay"],
                    "flattop_length": ctx.qubit_flattop,
                    "Qubit_number": ctx.Qubit_Pulse}

    fit = params["fit"]

    cfg = cfg | ARabi_config
    if ctx.qubit_flattop != None:
        ARabi_config = {'gain_start': 0, "gain_end": params["max_gain"],
                        'gainNumPoints': number_of_steps,
                        "reps": params['reps'],
                        "rounds": params['rounds'],
                        "sigma": ctx.qubit_sigma, "f_ge": params["qubit_freq"],
                        "relax_delay": 8000,
                        "flattop_length": ctx.qubit_flattop}
        cfg = cfg | ARabi_config  ### note that UpdateConfig will overwrite elements in BaseConfig
        iAmpRabi = AmplitudeRabiFF_N(path="AmplitudeRabi", cfg=cfg, soc=ctx.soc, soccfg=ctx.soccfg,
                                   outerFolder=ctx.outerFolder)
        dAmpRabi = AmplitudeRabiFF_N.acquire(iAmpRabi)
        AmplitudeRabiFF_N.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2, fit=fit)
        AmplitudeRabiFF_N.save_data(iAmpRabi, dAmpRabi)
        AmplitudeRabiFF_N.save_config(iAmpRabi)
    else:
        iAmpRabi = AmplitudeRabiFF(path="AmplitudeRabi", cfg=cfg, soc=ctx.soc, soccfg=ctx.soccfg,
                                   outerFolder=ctx.outerFolder)
        dAmpRabi = AmplitudeRabiFF.acquire(iAmpRabi)
        AmplitudeRabiFF.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2, fit=fit)
        AmplitudeRabiFF.save_data(iAmpRabi, dAmpRabi)
        AmplitudeRabiFF.save_config(iAmpRabi)


def run_trans_qubit_spec(ctx, params, T1T2_params):
    cfg = ctx.working_config()
    sanity_dump(cfg)
    for i in range(T1T2_params['repetitions']):

        cfg["reps"] = params['reps']  # want more reps and rounds for qubit data
        cfg["rounds"] = params['rounds']
        cfg["Gauss"] = params['Gauss']
        if params['Gauss']:
            cfg['sigma'] = params["sigma"]
            cfg["qubit_gain"] = params['gain']
        Instance_specSlice = QubitSpecSliceFF(path="QubitSpecFF", cfg=cfg, soc=ctx.soc, soccfg=ctx.soccfg,
                                              outerFolder=ctx.outerFolder)
        data_specSlice = QubitSpecSliceFF.acquire(Instance_specSlice)
        QubitSpecSliceFF.display(
            Instance_specSlice,
            data_specSlice,
            plotDisp=False,
            figNum=2,
            min_sep=params["min_sep_MHz"],
            fit_window_mhz=params["fit_window_mhz"],
            prominent_ratio=params["prominent_ratio"],
        )
        QubitSpecSliceFF.save_data(Instance_specSlice, data_specSlice)
        QubitSpecSliceFF.save_config(Instance_specSlice)
