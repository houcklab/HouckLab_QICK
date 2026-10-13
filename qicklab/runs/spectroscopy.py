"""Qubit spectroscopy runs: two-tone spec, gain x length sweep and transmission + qubit spec."""

from qicklab.core.config import sanity_dump
from qicklab.experiments.qubit_spec import QubitSpecSliceFF


# qubit spec experiment
def run_two_tone_spec(ctx, params):
    cfg = ctx.working_config()
    cfg["reps"] = params["reps"]
    cfg["rounds"] = params["rounds"]
    cfg["Gauss"] = params["Gauss"]
    if params["Gauss"]:
        cfg["sigma"] = params["sigma"]
        cfg["qubit_gain"] = params["gain"]

    cfg["qubit_gain"] = params["gain"]

    cfg["qubit_length"] = params["qubit_length"]
    cfg["SpecSpan"] = params["SpecSpan"]
    cfg["SpecNumPoints"] = params["SpecNumPoints"]
    cfg["step"] = 2 * cfg["SpecSpan"] / cfg["SpecNumPoints"]
    cfg["start"] = ctx.qubit_frequency_center - cfg["SpecSpan"]
    cfg["expts"] = cfg["SpecNumPoints"]
    cfg["relax_delay"] = params["relax_delay"]
    display = params["display"]
    min_sep = params["min_sep_MHz"]

    Instance_specSlice = QubitSpecSliceFF(
        path="QubitSpecFF", cfg=cfg, soc=ctx.soc, soccfg=ctx.soccfg, outerFolder=ctx.outerFolder
    )
    data_specSlice = QubitSpecSliceFF.acquire(Instance_specSlice)
    QubitSpecSliceFF.display(
        Instance_specSlice,
        data_specSlice,
        plotDisp=display,
        figNum=2,
        min_sep=min_sep,
        fit_window_mhz=0.5,
        prominent_ratio=0.1,
    )  # can change to True
    QubitSpecSliceFF.save_data(Instance_specSlice, data_specSlice)
    QubitSpecSliceFF.save_config(Instance_specSlice)


# Nested gain × qubit_length sweep.
# For each length in sweep_lengths, runs a full qubit spec at every gain in sweep_gains.
# qubit_gain and qubit_length appear in every saved plot title for easy identification.
def run_spec_gain_length_sweep(ctx, params):
    cfg = ctx.working_config()
    sweep_lengths = params["sweep_lengths"]
    sweep_gains = params["sweep_gains"]

    _disp = params["display"]
    _minsep = params["min_sep_MHz"]
    _fw = params.get("fit_window_mhz", 0.5)
    _pr = params.get("prominent_ratio", 0.1)

    for q_length in sweep_lengths:
        for q_gain in sweep_gains:
            print(f"\n=== GainLengthSweep: qubit_length={q_length} µs  qubit_gain={q_gain} ===")

            cfg["reps"] = params["reps"]
            cfg["rounds"] = params["rounds"]
            cfg["Gauss"] = params["Gauss"]
            cfg["qubit_gain"] = q_gain
            cfg["qubit_length"] = q_length
            cfg["SpecSpan"] = params["SpecSpan"]
            cfg["SpecNumPoints"] = params["SpecNumPoints"]
            cfg["step"] = 2 * cfg["SpecSpan"] / cfg["SpecNumPoints"]
            cfg["start"] = ctx.qubit_frequency_center - cfg["SpecSpan"]
            cfg["expts"] = cfg["SpecNumPoints"]
            cfg["relax_delay"] = params["relax_delay"]
            if params["Gauss"]:
                cfg["sigma"] = params["sigma"]

            _inst = QubitSpecSliceFF(
                path="QubitSpecFF",
                cfg=cfg,
                soc=ctx.soc,
                soccfg=ctx.soccfg,
                outerFolder=ctx.outerFolder,
            )
            _data = QubitSpecSliceFF.acquire(_inst)
            QubitSpecSliceFF.display(
                _inst,
                _data,
                plotDisp=_disp,
                figNum=2,
                min_sep=_minsep,
                fit_window_mhz=_fw,
                prominent_ratio=_pr,
            )
            QubitSpecSliceFF.save_data(_inst, _data)
            QubitSpecSliceFF.save_config(_inst)


def run_trans_qubit_spec(ctx, params, T1T2_params):
    cfg = ctx.working_config()
    sanity_dump(cfg)
    for i in range(T1T2_params["repetitions"]):
        cfg["reps"] = params["reps"]  # want more reps and rounds for qubit data
        cfg["rounds"] = params["rounds"]
        cfg["Gauss"] = params["Gauss"]
        if params["Gauss"]:
            cfg["sigma"] = params["sigma"]
            cfg["qubit_gain"] = params["gain"]
        Instance_specSlice = QubitSpecSliceFF(
            path="QubitSpecFF", cfg=cfg, soc=ctx.soc, soccfg=ctx.soccfg, outerFolder=ctx.outerFolder
        )
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
