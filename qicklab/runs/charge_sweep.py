"""Gate-charge sweep runs (two-tone spec and transmission vs yoko voltage)."""

import time
from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import find_peaks

from qicklab.analysis.iq import project_iq_signal
from qicklab.core.config import sanity_dump
from qicklab.core.experiment import finish
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


def run_charge_sweep(ctx, Spec_relevant_params):
    cfg = ctx.working_config()
    sanity_dump(cfg)
    cfg["reps"] = Spec_relevant_params["reps"]
    cfg["rounds"] = Spec_relevant_params["rounds"]
    cfg["Gauss"] = Spec_relevant_params["Gauss"]

    if Spec_relevant_params["Gauss"]:
        cfg["sigma"] = Spec_relevant_params["sigma"]
        cfg["qubit_gain"] = Spec_relevant_params["gain"]

    voltage_pts = np.arange(cfg["voltage_start"], cfg["voltage_end"], cfg["voltage_step"])
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
        if voltage > 10:
            print("voltage too high")
            break
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
            min_sep=Spec_relevant_params["min_sep_MHz"],
            fit_window_mhz=Spec_relevant_params["fit_window_mhz"],
            prominent_ratio=Spec_relevant_params["prominent_ratio"],
        )
        x_pts = np.array(data_specSlice["data"]["x_pts"])
        avgi = np.array(data_specSlice["data"]["avgi"][0][0])
        avgq = np.array(data_specSlice["data"]["avgq"][0][0])
        avgamp0 = project_iq_signal(avgi, avgq)
        # up to two tallest peaks >= 0.05 MHz apart, sorted by frequency (printed only)
        min_spacing = 0.05
        dx = np.mean(np.diff(x_pts))
        min_distance_pts = max(1, int(np.ceil(min_spacing / dx)))

        peak_inds, _ = find_peaks(avgamp0, distance=min_distance_pts)
        if len(peak_inds) > 0:
            peak_inds = peak_inds[np.argsort(avgamp0[peak_inds])[::-1][:2]]
            peak_inds = peak_inds[np.argsort(x_pts[peak_inds])]
            peak_freqs = x_pts[peak_inds]
        else:
            peak_freqs = np.array([])

        print("peak freqs:", peak_freqs)
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
    np.savez(
        Instance_specSlice.fname[:-3] + "_ChargeSweepHeatmap.npz",
        avgamp_map=avgamp_map,
        x_pts=x_pts,
        yoko_fixed=bool(ctx.yoko_fixed),
        **axis,
    )

    plt.ioff()
    plt.close(fig)


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
