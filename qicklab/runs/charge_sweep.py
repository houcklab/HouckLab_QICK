"""Gate-charge sweep runs (two-tone spec and transmission vs yoko voltage)."""

import time
from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np

from qicklab.analysis.iq import project_iq_signal
from qicklab.analysis.spectroscopy import (
    choose_two_tone_freqs_from_lorentz_or_peaks,
    fit_charge_dispersion_splitting,
    fit_doublet_mean,
    refit_doublet_jointly,
    single_line_splitting_bound,
)
from qicklab.core.config import sanity_dump
from qicklab.core.experiment import finish
from qicklab.core.io import write_provenance
from qicklab.experiments.qubit_spec import QubitSpecSliceFF
from qicklab.experiments.transmission import CavitySpecFF
from qicklab.hardware.yoko import ramp_to


def choose_next_voltage(current_v, dv, vmin, vmax, direction):
    proposed = current_v + direction * dv

    if proposed > vmax:
        direction = -1
        proposed = current_v + direction * dv

    if proposed < vmin:
        direction = +1
        proposed = current_v + direction * dv

    proposed = min(max(proposed, vmin), vmax)
    return proposed, direction


def _record_hold(cfg, i, voltage, v_hold):
    """yoko_fixed: the bias is held, so slice i is repeat i at v_hold, not a point of the grid.

    Records the held level, the grid value as nominal_voltage, repeat_index and a wall-clock
    acq_time (local ISO time, the ExperimentClass file-name clock). Returns the datetime.
    See docs/experiments/charge_sweep.md#holding-the-bias-yoko_fixed.
    """
    now = datetime.now()
    cfg["current_voltage"] = v_hold
    cfg["nominal_voltage"] = float(voltage)
    cfg["repeat_index"] = i
    cfg["acq_time"] = now.isoformat(timespec="milliseconds")
    return now


def _hold_npz(voltage_pts, v_hold, acq_times):
    """npz fields for a yoko_fixed run: the repeat axis instead of a voltage axis."""
    n = len(acq_times)
    return {
        "nominal_voltage_pts": voltage_pts,
        "repeat_index": np.arange(n),
        "acq_time": np.array([t.isoformat(timespec="milliseconds") for t in acq_times]),
        "elapsed_s": np.array([(t - acq_times[0]).total_seconds() for t in acq_times]),
        "held_voltage": v_hold,
    }


# points per S period (S(V) repeats every cd_period_mv/2) below which the grid gets a warning
CHARGE_GRID_MIN_PTS_PER_S_PERIOD = 8


def report_grid_sampling(voltage_pts, cd_period_mv=None):
    """Print the charge grid's range, step and points per mV; with a known period, its points per
    S period, and a WARNING when |step| > T_S / CHARGE_GRID_MIN_PTS_PER_S_PERIOD.

    T_S = cd_period_mv / 2: the modified_ramsey_control model S(V) = cd_max |cos(2 pi (V - V0)/T)|
    repeats every T/2 (the conservative reading). Never raises. Returns the points per S period
    (NaN when the period is unknown). docs/experiments/charge_sweep.md#sampling-the-period
    """
    v_mv = 1e3 * np.asarray(voltage_pts, dtype=float)
    step = abs(v_mv[1] - v_mv[0]) if v_mv.size > 1 else float("nan")
    print(
        f"[ChargeSweep] grid {v_mv[0]:.4g} to {v_mv[-1]:.4g} mV, {v_mv.size} points, "
        f"step {step:.4g} mV ({1.0 / step:.3g} points per mV)"
    )
    if cd_period_mv is None or not np.isfinite(step):
        print("[ChargeSweep] charge-dispersion period unknown: sampling not checked")
        return float("nan")
    t_s = float(cd_period_mv) / 2.0
    pts = t_s / step
    print(
        f"[ChargeSweep] {pts:.2f} points per S period (T_S = cd_period_mv/2 = {t_s:.4g} mV), "
        f"{(v_mv[-1] - v_mv[0]) / t_s:.2f} S periods covered"
    )
    if pts < CHARGE_GRID_MIN_PTS_PER_S_PERIOD:
        print(
            f"WARNING: [ChargeSweep] step {step:.4g} mV > T_S/{CHARGE_GRID_MIN_PTS_PER_S_PERIOD} "
            f"= {t_s / CHARGE_GRID_MIN_PTS_PER_S_PERIOD:.4g} mV: the splitting vs bias is "
            "undersampled and the map aliases (docs/experiments/charge_sweep.md)"
        )
    return pts


def _pad2(values):
    out = np.full(2, np.nan)
    values = np.asarray(values if values is not None else [], dtype=float).ravel()[:2]
    out[: values.size] = values
    return out


def _slice_doublet(data_spec, min_sep, fit_window):
    """Parity doublet of one displayed slice for the splitting fit.

    Returns (choice, refit, censor): the selection (choose_two_tone_freqs_from_lorentz_or_peaks),
    the joint two-Lorentzian refit of a selected pair (refit_doublet_jointly; None when there is
    no pair or the refit fails) and, for a single_line_unresolved slice, the upper bound on its
    hidden splitting (single_line_splitting_bound), else NaN.
    """
    choice = choose_two_tone_freqs_from_lorentz_or_peaks(data_spec, min_sep_mhz=min_sep)
    refit, censor = None, np.nan
    if len(choice["freqs"]) == 2:
        refit = refit_doublet_jointly(data_spec, choice["freqs"], fit_window, min_sep)
    elif choice["source"] == "single_line_unresolved":
        censor = single_line_splitting_bound(data_spec, min_sep)
    return choice, refit, censor


def run_charge_sweep(ctx, Spec_relevant_params, cd_period_mv=None):
    """QubitSpecSliceFF at every charge bias -> heatmap, parity doublet per slice, splitting fit.

    cd_period_mv (optional): the device's charge-dispersion period T (modified_ramsey_control
    convention) for the grid-sampling check and the fit's alias guard.
    docs/experiments/charge_sweep.md
    """
    cfg = ctx.working_config()
    sanity_dump(cfg)
    cfg["reps"] = Spec_relevant_params["reps"]
    cfg["rounds"] = Spec_relevant_params["rounds"]
    cfg["Gauss"] = Spec_relevant_params["Gauss"]

    if Spec_relevant_params["Gauss"]:
        cfg["sigma"] = Spec_relevant_params["sigma"]
        cfg["qubit_gain"] = Spec_relevant_params["gain"]

    voltage_pts = charge_sweep_voltages(cfg, {})
    if not ctx.yoko_fixed:
        report_grid_sampling(voltage_pts, cd_period_mv)
    min_sep = Spec_relevant_params["min_sep_MHz"]
    nv = len(voltage_pts)
    doublet_freqs = np.full((nv, 2), np.nan)
    refit_freqs = np.full((nv, 2), np.nan)
    refit_hwhm = np.full((nv, 2), np.nan)
    doublet_amp = np.full((nv, 2), np.nan)
    partner_snr = np.full(nv, np.nan)
    censor_mhz = np.full(nv, np.nan)
    sources = [""] * nv
    lorentz = {k: np.full((nv, 2), np.nan) for k in ("centers", "fwhm", "r2")}
    # yoko_fixed: rows are repeats in time at the held bias, read back once
    v_hold = float(ctx.yoko.query(":SOUR:LEV?")) if ctx.yoko_fixed else None
    acq_times = []
    row_pts = np.arange(len(voltage_pts)) if ctx.yoko_fixed else voltage_pts
    avgamp_map = None
    fig = None
    ax = None
    im = None
    cbar = None
    for i, voltage in enumerate(voltage_pts):
        if ctx.yoko_fixed:
            acq_times.append(_record_hold(cfg, i, voltage, v_hold))
        else:
            ramp_to(ctx.yoko, voltage)
            cfg["current_voltage"] = float(voltage)
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
            min_sep=min_sep,
            fit_window_mhz=Spec_relevant_params["fit_window_mhz"],
            prominent_ratio=Spec_relevant_params["prominent_ratio"],
        )
        x_pts = np.array(data_specSlice["data"]["x_pts"])
        avgi = np.array(data_specSlice["data"]["avgi"][0][0])
        avgq = np.array(data_specSlice["data"]["avgq"][0][0])
        avgamp0 = project_iq_signal(avgi, avgq)
        # parity doublet of this slice: one frequency when unresolved or not significant
        choice, refit, censor_mhz[i] = _slice_doublet(
            data_specSlice, min_sep, Spec_relevant_params["fit_window_mhz"]
        )
        freqs = np.asarray(choice["freqs"], dtype=float)
        doublet_freqs[i] = _pad2(freqs)
        doublet_amp[i] = _pad2([avgamp0[int(np.argmin(np.abs(x_pts - f)))] for f in freqs])
        partner_snr[i] = np.nan if choice["partner_snr"] is None else choice["partner_snr"]
        sources[i] = choice["source"]
        if refit is not None:
            refit_freqs[i], refit_hwhm[i] = refit["centers"], refit["hwhm"]
        for key in lorentz:
            lorentz[key][i] = _pad2(data_specSlice["data"].get("lorentz_" + key))
        sep_txt = ""
        if refit is not None:
            sep_txt = f", joint-fit sep {refit['centers'][1] - refit['centers'][0]:.4f} MHz"
        elif len(freqs) == 2:
            sep_txt = ", joint refit failed (slice dropped from the splitting fit)"
        print(f"doublet: {np.round(freqs, 4)} MHz{sep_txt} ({choice['source']})")
        if avgamp_map is None:
            avgamp_map = np.full((len(voltage_pts), len(x_pts)), np.nan)
            plt.ion()
            fig, ax = plt.subplots(figsize=(8, 6))
            x_step = x_pts[1] - x_pts[0] if len(x_pts) > 1 else 1
            y_step = row_pts[1] - row_pts[0] if len(row_pts) > 1 else 1

            im = ax.imshow(
                avgamp_map,
                aspect="auto",
                origin="lower",
                interpolation="none",
                extent=[
                    x_pts[0] - x_step / 2,
                    x_pts[-1] + x_step / 2,
                    row_pts[0] - y_step / 2,
                    row_pts[-1] + y_step / 2,
                ],
            )
            cbar = fig.colorbar(im, ax=ax)
            cbar.set_label("rotated IQ projection")

            ax.set_xlabel("Frequency")
            ax.set_ylabel("repeat index" if ctx.yoko_fixed else "Voltage")
            ax.set_title("Charge sweep for Qubit Spec")

            plt.show(block=False)
        avgamp_map[i, :] = avgamp0
        im.set_data(avgamp_map)
        im.set_clim(np.nanmin(avgamp_map), np.nanmax(avgamp_map))
        if ctx.yoko_fixed:
            ax.set_title(f"\nrepeat {i + 1}/{len(voltage_pts)} at V = {v_hold:.4f}")
        else:
            ax.set_title(f"\nVoltage = {voltage:.4f}")
        fig.canvas.draw_idle()
        plt.pause(0.1)

    fig.savefig(
        Instance_specSlice.iname[:-4] + "_ChargeSweepHeatmap.png", dpi=300, bbox_inches="tight"
    )
    axis = (
        _hold_npz(voltage_pts, v_hold, acq_times)
        if ctx.yoko_fixed
        else {"voltage_pts": voltage_pts}
    )
    # splitting and mean from the joint refit: NaN where one line or where the refit failed
    sep = refit_freqs[:, 1] - refit_freqs[:, 0]
    f_mean = 0.5 * (refit_freqs[:, 0] + refit_freqs[:, 1])
    # no splitting information: a partner that failed the significance gate, a failed refit
    exclude = (np.array(sources) == "partner_not_significant") | (
        np.isfinite(doublet_freqs[:, 1]) & ~np.isfinite(sep)
    )
    fit = _splitting_fit(
        voltage_pts, sep, f_mean, exclude, censor_mhz, cd_period_mv, ctx.yoko_fixed
    )
    np.savez(
        Instance_specSlice.fname[:-3] + "_ChargeSweepHeatmap.npz",
        avgamp_map=avgamp_map,
        x_pts=x_pts,
        yoko_fixed=bool(ctx.yoko_fixed),
        doublet_freqs_mhz=doublet_freqs,
        doublet_refit_mhz=refit_freqs,
        doublet_refit_hwhm_mhz=refit_hwhm,
        doublet_amp=doublet_amp,
        doublet_source=np.array(sources),
        partner_snr=partner_snr,
        censor_limit_mhz=censor_mhz,
        sep_mhz=sep,
        f_mean_mhz=f_mean,
        lorentz_centers_mhz=lorentz["centers"],
        lorentz_fwhm_mhz=lorentz["fwhm"],
        lorentz_r2=lorentz["r2"],
        **fit,
        **axis,
    )
    write_provenance(Instance_specSlice.fname[:-3] + "_ChargeSweepHeatmap", soccfg=ctx.soccfg)

    plt.ioff()
    plt.close(fig)


def _splitting_fit(voltage_pts, sep, f_mean, exclude, censor_mhz, cd_period_mv, yoko_fixed):
    """Fit and print sep(V) and f_mean(V); returns the npz fields (fit_*, prior_cd_period_mv).

    sep: the joint-refit splitting. single_line_unresolved slices are censored at censor_mhz
    (per slice, single_line_splitting_bound; NaN: dropped); `exclude` (partner not significant,
    joint refit failed) is dropped. Diagnostic only: nothing is written back.
    """
    nan = float("nan")
    if yoko_fixed:
        cd = {"status": "yoko_fixed", "message": "no bias axis: the bias was held"}
        line = {}
    else:
        cd = fit_charge_dispersion_splitting(
            voltage_pts,
            sep,
            censored_below_mhz=censor_mhz,
            cd_period_mv=cd_period_mv,
            exclude=exclude,
        )
        line = fit_doublet_mean(voltage_pts, f_mean)
    out = {
        "prior_cd_period_mv": nan if cd_period_mv is None else float(cd_period_mv),
        "fit_status": cd["status"],
        "fit_message": cd["message"],
        "fit_cd_max_mhz": cd.get("cd_max_mhz", nan),
        "fit_cd_max_err_mhz": cd.get("cd_max_err_mhz", nan),
        "fit_s_period_mv": cd.get("s_period_mv", nan),
        "fit_s_period_err_mv": cd.get("s_period_err_mv", nan),
        "fit_cd_period_mv": cd.get("cd_period_mv", nan),
        "fit_cd_period_err_mv": cd.get("cd_period_err_mv", nan),
        "fit_v0_mv": cd.get("v0_mv", nan),
        "fit_v0_err_mv": cd.get("v0_err_mv", nan),
        "fit_f0_mhz": line.get("f0_mhz", nan),
        "fit_f0_err_mhz": line.get("f0_err_mhz", nan),
        "fit_f_slope_mhz_per_mv": line.get("slope_mhz_per_mv", nan),
        "fit_f_slope_err_mhz_per_mv": line.get("slope_err_mhz_per_mv", nan),
    }
    if yoko_fixed:
        return out
    print(f"[ChargeSweep] doublet resolved in {int(np.isfinite(sep).sum())}/{len(sep)} slices")
    if cd["status"] == "ok":
        print(
            "[ChargeSweep] sep(V) = cd_max |cos(pi (V - V0)/T_S)|: "
            f"cd_max = {cd['cd_max_mhz']:.4f} +- {cd['cd_max_err_mhz']:.4f} MHz, "
            f"T_S = {cd['s_period_mv']:.4f} +- {cd['s_period_err_mv']:.4f} mV "
            f"(cd_period_mv = 2 T_S = {cd['cd_period_mv']:.4f} +- {cd['cd_period_err_mv']:.4f}), "
            f"V0 = {cd['v0_mv']:.4f} +- {cd['v0_err_mv']:.4f} mV"
        )
        if cd["message"]:
            print(f"[ChargeSweep] note: {cd['message']}")
    else:
        print(f"[ChargeSweep] splitting fit {cd['status']}: {cd['message']}")
    if np.isfinite(out["fit_f0_mhz"]):
        print(
            f"[ChargeSweep] f_mean = {out['fit_f0_mhz']:.4f} +- {out['fit_f0_err_mhz']:.4f} MHz, "
            f"slope {out['fit_f_slope_mhz_per_mv']:.4g} +- "
            f"{out['fit_f_slope_err_mhz_per_mv']:.2g} MHz/mV"
        )
    return out


def charge_sweep_voltages(cfg, params):
    """Charge-bias grid np.arange(voltage_start, voltage_end, voltage_step), half-open.

    Each value comes from `params`, else from cfg (charge_params); validated non-empty, |V| <= 10.
    """
    resolved = {}
    for key in ("voltage_start", "voltage_end", "voltage_step"):
        value = params.get(key)
        if value is None:
            if key not in cfg:
                raise ValueError(
                    f"charge sweep needs {key} in params or in the config (set it in charge_params)"
                )
            value = cfg[key]
        resolved[key] = float(value)

    if resolved["voltage_step"] == 0:
        raise ValueError("voltage_step must be non-zero")
    v = np.arange(resolved["voltage_start"], resolved["voltage_end"], resolved["voltage_step"])
    if v.size == 0:
        raise ValueError(
            f"empty charge sweep: voltage_start={resolved['voltage_start']} "
            f"voltage_end={resolved['voltage_end']} "
            f"voltage_step={resolved['voltage_step']} (check the step sign)"
        )
    if np.any(np.abs(v) > 10):  # whole grid before moving: docs/architecture.md#yoko-safety
        raise ValueError(f"charge sweep exceeds +-10 V: {v.min()} to {v.max()}")
    return v


def run_charge_transmission_sweep(ctx, params=None):
    """CavitySpecFF transmission sweep at every charge bias -> dB heatmap + tracked extremum.

    params (all optional): reps, rounds, span, num_points, fit, settle_s, voltage_start/end/step.
    Leaves ctx.config untouched and restores the start bias: docs/experiments/charge_transmission_sweep.md
    """
    params = params or {}
    cfg = ctx.working_config()
    sanity_dump(cfg)

    for key, cfg_key in (
        ("reps", "reps"),
        ("rounds", "rounds"),
        ("span", "TransSpan"),
        ("num_points", "TransNumPoints"),
    ):
        if params.get(key) is not None:
            cfg[cfg_key] = params[key]

    do_fit = bool(params.get("fit", False))
    settle_s = float(params.get("settle_s", 0.0))
    voltage_pts = charge_sweep_voltages(cfg, params)

    # acquire/display rewrite cfg["pulse_freq"]: reset per slice (docs/architecture.md#carry-overs)
    center_freq = float(cfg["pulse_freq"])
    lo_mhz = cfg.get("cavity_LO", 0.0) / 1e6

    db_map = None
    avgi_map = None
    avgq_map = None
    raw_extremum = np.full(len(voltage_pts), np.nan)
    fit_extremum = np.full(len(voltage_pts), np.nan)
    fig = ax = im = None
    Instance_trans = None
    x_pts = None

    v_return = float(ctx.yoko.query(":SOUR:LEV?"))  # also the held bias under yoko_fixed
    acq_times = []
    row_pts = np.arange(len(voltage_pts)) if ctx.yoko_fixed else voltage_pts
    try:  # restore the start bias even on abort: docs/architecture.md#yoko-safety
        for i, voltage in enumerate(voltage_pts):
            if ctx.yoko_fixed:
                print(
                    f"[ChargeTransmissionSweep] repeat {i + 1}/{len(voltage_pts)} "
                    f"at held {v_return:.6f} V"
                )
                acq_times.append(_record_hold(cfg, i, voltage, v_return))
            else:
                print(f"[ChargeTransmissionSweep] bias {i + 1}/{len(voltage_pts)}: {voltage:.6f} V")
                ramp_to(ctx.yoko, float(voltage))
                if settle_s:
                    time.sleep(settle_s)
                cfg["current_voltage"] = float(voltage)
            cfg["pulse_freq"] = center_freq

            Instance_trans = CavitySpecFF(
                path="ChargeTransmissionFF",
                cfg=cfg,
                soc=ctx.soc,
                soccfg=ctx.soccfg,
                outerFolder=ctx.outerFolder,
            )
            data_trans = CavitySpecFF.acquire(Instance_trans)
            finish(CavitySpecFF, Instance_trans, data_trans, plotDisp=False, figNum=20, fit=do_fit)

            fpts = np.asarray(data_trans["data"]["fpts"], dtype=float)
            avgi = np.asarray(data_trans["data"]["results"][0][0][0], dtype=float)
            avgq = np.asarray(data_trans["data"]["results"][0][0][1], dtype=float)
            y_db = 20 * np.log10(np.abs(avgi + 1j * avgq))

            extremum_idx = np.argmin(y_db) if ctx.cavity_min else np.argmax(y_db)
            raw_extremum[i] = fpts[extremum_idx]
            if do_fit and "hanger_fit_min_freq_mhz" in data_trans["data"]:
                fit_extremum[i] = float(data_trans["data"]["hanger_fit_min_freq_mhz"])
            print(
                f"    {'min' if ctx.cavity_min else 'max'} at "
                f"{raw_extremum[i]:.6f} MHz ({y_db[extremum_idx]:.3f} dB)"
            )

            if db_map is None:  # live heatmap, once the frequency axis length is known
                x_pts = (fpts + lo_mhz) / 1e3  # GHz absolute, as in CavitySpecFF
                db_map = np.full((len(voltage_pts), len(x_pts)), np.nan)
                avgi_map = np.full_like(db_map, np.nan)
                avgq_map = np.full_like(db_map, np.nan)
                plt.ion()
                fig, ax = plt.subplots(figsize=(8, 6))
                x_step = x_pts[1] - x_pts[0] if len(x_pts) > 1 else 1
                y_step = row_pts[1] - row_pts[0] if len(row_pts) > 1 else 1
                im = ax.imshow(
                    db_map,
                    aspect="auto",
                    origin="lower",
                    interpolation="none",
                    extent=[
                        x_pts[0] - x_step / 2,
                        x_pts[-1] + x_step / 2,
                        row_pts[0] - y_step / 2,
                        row_pts[-1] + y_step / 2,
                    ],
                )
                cbar = fig.colorbar(im, ax=ax)
                cbar.set_label("Transmission (dB)")
                ax.set_xlabel("Cavity Frequency (GHz)")
                ax.set_ylabel("repeat index" if ctx.yoko_fixed else "Voltage (V)")
                ax.set_title("Charge sweep for cavity transmission")
                plt.show(block=False)
            elif len(fpts) != db_map.shape[1]:
                raise RuntimeError(
                    f"transmission slice at {voltage:.6f} V returned "
                    f"{len(fpts)} points, expected {db_map.shape[1]}"
                )

            db_map[i, :] = y_db
            avgi_map[i, :] = avgi
            avgq_map[i, :] = avgq
            im.set_data(db_map)
            im.set_clim(np.nanmin(db_map), np.nanmax(db_map))
            if ctx.yoko_fixed:
                row_label = f"repeat {i + 1}/{len(voltage_pts)} at V = {v_return:.6f}"
            else:
                row_label = f"Voltage = {voltage:.6f}"
            ax.set_title(f"Charge sweep for cavity transmission\n{row_label}")
            fig.canvas.draw_idle()
            plt.pause(0.1)
    finally:
        if not ctx.yoko_fixed:
            ramp_to(ctx.yoko, v_return)

    # tracked resonator frequency over the sweep, on the same GHz axis
    ax.plot(
        (raw_extremum + lo_mhz) / 1e3,
        row_pts,
        ".-",
        color="white",
        linewidth=1,
        markersize=4,
        label=f"raw {'min' if ctx.cavity_min else 'max'}",
    )
    if np.any(np.isfinite(fit_extremum)):
        ax.plot(
            (fit_extremum + lo_mhz) / 1e3,
            row_pts,
            ".-",
            color="red",
            linewidth=1,
            markersize=4,
            label="hanger fit min",
        )
    ax.legend(loc="best", fontsize=8)
    fig.canvas.draw_idle()

    fig.savefig(
        Instance_trans.iname[:-4] + "_ChargeTransmissionHeatmap.png", dpi=300, bbox_inches="tight"
    )
    axis = (
        _hold_npz(voltage_pts, v_return, acq_times)
        if ctx.yoko_fixed
        else {"voltage_pts": voltage_pts}
    )
    np.savez(
        Instance_trans.fname[:-3] + "_ChargeTransmissionHeatmap.npz",
        db_map=db_map,
        avgi_map=avgi_map,
        avgq_map=avgq_map,
        fpts_mhz=(np.asarray(x_pts) * 1e3 - lo_mhz),
        x_pts_ghz=np.asarray(x_pts),
        raw_extremum_mhz=raw_extremum,
        fit_extremum_mhz=fit_extremum,
        cavity_min=ctx.cavity_min,
        yoko_fixed=bool(ctx.yoko_fixed),
        **axis,
    )
    write_provenance(Instance_trans.fname[:-3] + "_ChargeTransmissionHeatmap", soccfg=ctx.soccfg)

    span_khz = 1e3 * (np.nanmax(raw_extremum) - np.nanmin(raw_extremum))
    if ctx.yoko_fixed:
        print(
            f"[ChargeTransmissionSweep] resonator frequency drifted {span_khz:.3f} kHz "
            f"over {len(acq_times)} repeats ({axis['elapsed_s'][-1]:.1f} s) "
            f"at held {v_return:.6f} V"
        )
    else:
        print(
            f"[ChargeTransmissionSweep] resonator frequency moved "
            f"{span_khz:.3f} kHz over {voltage_pts[0]:.6f} to "
            f"{voltage_pts[-1]:.6f} V"
        )

    plt.ioff()
    plt.close(fig)
