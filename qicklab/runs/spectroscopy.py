"""Qubit spectroscopy runs: two-tone spec, gain x length sweep and transmission + qubit spec."""

import os
import traceback

from qicklab.analysis.spectroscopy import (
    gain_sweep_point,
    print_gain_length_summary,
    save_gain_length_summary,
    summarize_gain_length_sweep,
)
from qicklab.core.config import check_gain, sanity_dump
from qicklab.core.experiment import finish
from qicklab.experiments.qubit_spec import QubitSpecSliceFF


def _peak_kwargs(params):
    """display()'s peak-picking knobs from the spec group, with the legacy defaults."""
    return {
        "fit_window_mhz": params.get("fit_window_mhz", 0.5),
        "prominent_ratio": params.get("prominent_ratio", 0.1),
    }


def run_two_tone_spec(ctx, params):
    cfg = ctx.working_config()
    cfg["reps"] = params["reps"]
    cfg["rounds"] = params["rounds"]
    cfg["Gauss"] = params["Gauss"]
    if params["Gauss"]:
        cfg["sigma"] = params["sigma"]
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
    peak_kw = _peak_kwargs(params)

    Instance_specSlice = QubitSpecSliceFF(
        path="QubitSpecFF", cfg=cfg, soc=ctx.soc, soccfg=ctx.soccfg, outerFolder=ctx.outerFolder
    )
    data_specSlice = QubitSpecSliceFF.acquire(Instance_specSlice)
    finish(
        QubitSpecSliceFF,
        Instance_specSlice,
        data_specSlice,
        reraise=True,
        plotDisp=display,
        figNum=2,
        min_sep=min_sep,
        **peak_kw,
    )


def run_spec_gain_length_sweep(ctx, params):
    """Full two-tone spec at every (qubit_length, qubit_gain) of sweep_lengths x sweep_gains,
    then a saturation summary (FWHM^2 = FWHM_0^2 + c gain^2 per length, SNR, recommended gain)
    printed and saved as GainLengthSweep_summary_<timestamp>.npz/.png in the QubitSpecFF dated
    folder. Summary rules: docs/experiments/spec_gain_length_sweep.md#analysis."""
    cfg = ctx.working_config()
    sweep_lengths = params["sweep_lengths"]
    sweep_gains = params["sweep_gains"]
    check_gain("Spec_relevant_params['sweep_gains']", sweep_gains)

    _disp = params["display"]
    _minsep = params["min_sep_MHz"]
    _peak_kw = _peak_kwargs(params)

    rows = []
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
            finish(
                QubitSpecSliceFF,
                _inst,
                _data,
                plotDisp=_disp,
                figNum=2,
                min_sep=_minsep,
                **_peak_kw,
            )
            rows.append(
                gain_sweep_point(
                    _data,
                    q_length,
                    q_gain,
                    fit_window_mhz=_peak_kw["fit_window_mhz"],
                    span_mhz=params["SpecSpan"],
                    min_sep_mhz=_minsep,
                )
            )

    if not rows:
        return
    try:
        summary = summarize_gain_length_sweep(
            rows, gauss=params["Gauss"], sigma_us=params.get("sigma")
        )
        print_gain_length_summary(summary)
        save_gain_length_summary(summary, os.path.dirname(_inst.fname), plotDisp=_disp)
    except Exception:  # the per-point records are saved; only the summary is lost
        traceback.print_exc()


def run_trans_qubit_spec(ctx, params, T1T2_params):
    cfg = ctx.working_config()
    # the spec group's drive gain and relax delay, as in two_tone_spec (const and Gaussian drive)
    cfg["qubit_gain"] = params["gain"]
    cfg["relax_delay"] = params["relax_delay"]
    sanity_dump(cfg)
    for _ in range(T1T2_params["repetitions"]):
        cfg["reps"] = params["reps"]
        cfg["rounds"] = params["rounds"]
        cfg["Gauss"] = params["Gauss"]
        if params["Gauss"]:
            cfg["sigma"] = params["sigma"]
        Instance_specSlice = QubitSpecSliceFF(
            path="QubitSpecFF", cfg=cfg, soc=ctx.soc, soccfg=ctx.soccfg, outerFolder=ctx.outerFolder
        )
        data_specSlice = QubitSpecSliceFF.acquire(Instance_specSlice)
        finish(
            QubitSpecSliceFF,
            Instance_specSlice,
            data_specSlice,
            plotDisp=False,
            figNum=2,
            min_sep=params["min_sep_MHz"],
            fit_window_mhz=params["fit_window_mhz"],
            prominent_ratio=params["prominent_ratio"],
        )
