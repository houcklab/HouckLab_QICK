"""Gate-charge sweep runs (two-tone spec and transmission vs yoko voltage)."""

import time

import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import find_peaks

from qicklab.analysis.iq import project_iq_signal
from qicklab.core.config import sanity_dump
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
    # will initialize after first acquisition, once x_pts length is known
    avgamp_map = None
    fig = None
    ax = None
    im = None
    cbar = None
    for i, voltage in enumerate(voltage_pts):
        if voltage > 10:
            print("voltage too high")
            break
        if not ctx.yoko_fixed:
            ramp_to(ctx.yoko, voltage)
        cfg["current_voltage"] = float(voltage)
        Instance_specSlice = QubitSpecSliceFF(
            path="QubitSpecFF", cfg=cfg, soc=ctx.soc, soccfg=ctx.soccfg, outerFolder=ctx.outerFolder
        )
        data_specSlice = QubitSpecSliceFF.acquire(Instance_specSlice)
        QubitSpecSliceFF.display(
            Instance_specSlice,
            data_specSlice,
            plotDisp=False,
            figNum=2,
            min_sep=Spec_relevant_params["min_sep_MHz"],
            fit_window_mhz=Spec_relevant_params["fit_window_mhz"],
            prominent_ratio=Spec_relevant_params["prominent_ratio"],
        )
        QubitSpecSliceFF.save_data(Instance_specSlice, data_specSlice)
        QubitSpecSliceFF.save_config(Instance_specSlice)
        x_pts = np.array(data_specSlice["data"]["x_pts"])
        avgi = np.array(data_specSlice["data"]["avgi"][0][0])
        avgq = np.array(data_specSlice["data"]["avgq"][0][0])
        # Rotate onto the signal-bearing IQ axis (background-subtracted) instead of
        # the raw magnitude |I+iQ|^2: the magnitude is dominated by the large, noisy
        # background quadrature, which both buries per-slice peaks and washes out the
        # charge-sweep heatmap. The projection gives each slice a ~0 baseline with the
        # qubit feature as a positive bump.
        avgamp0 = project_iq_signal(avgi, avgq)
        # find up to two peaks with a minimum spacing in x-units
        min_spacing = 0.05  # same units as x_pts
        dx = np.mean(np.diff(x_pts))
        min_distance_pts = max(1, int(np.ceil(min_spacing / dx)))

        peak_inds, _ = find_peaks(avgamp0, distance=min_distance_pts)

        # keep the two tallest peaks
        if len(peak_inds) > 0:
            peak_inds = peak_inds[np.argsort(avgamp0[peak_inds])[::-1][:2]]
            peak_inds = peak_inds[np.argsort(x_pts[peak_inds])]  # optional: sort by frequency
            peak_freqs = x_pts[peak_inds]
            peak_vals = avgamp0[peak_inds]
        else:
            peak_freqs = np.array([])
            peak_vals = np.array([])

        print("peak freqs:", peak_freqs)
        # initialize plotting objects once we know x axis length
        if avgamp_map is None:
            avgamp_map = np.full((len(voltage_pts), len(x_pts)), np.nan)
            plt.ion()
            fig, ax = plt.subplots(figsize=(8, 6))
            x_step = x_pts[1] - x_pts[0] if len(x_pts) > 1 else 1
            y_step = voltage_pts[1] - voltage_pts[0] if len(voltage_pts) > 1 else 1

            im = ax.imshow(
                avgamp_map,
                aspect="auto",
                origin="lower",
                interpolation="none",
                extent=[
                    x_pts[0] - x_step / 2,
                    x_pts[-1] + x_step / 2,
                    voltage_pts[0] - y_step / 2,
                    voltage_pts[-1] + y_step / 2,
                ],
            )
            cbar = fig.colorbar(im, ax=ax)
            cbar.set_label("rotated IQ projection")

            ax.set_xlabel("Frequency")
            ax.set_ylabel("Voltage")
            ax.set_title("Charge sweep for Qubit Spec")

            plt.show(block=False)
        # store this voltage slice
        avgamp_map[i, :] = avgamp0
        # update heatmap
        im.set_data(avgamp_map)
        # optional: rescale color as data comes in
        im.set_clim(np.nanmin(avgamp_map), np.nanmax(avgamp_map))
        ax.set_title(f"\nVoltage = {voltage:.4f}")
        fig.canvas.draw_idle()
        plt.pause(0.1)

    fig.savefig(
        Instance_specSlice.iname[:-4] + "_ChargeSweepHeatmap.png", dpi=300, bbox_inches="tight"
    )
    np.savez(
        Instance_specSlice.fname[:-3] + "_ChargeSweepHeatmap.npz",
        avgamp_map=avgamp_map,
        x_pts=x_pts,
        voltage_pts=voltage_pts,
    )

    plt.ioff()
    plt.close(fig)


def charge_sweep_voltages(cfg, params):
    """Charge-bias points shared by the charge sweeps.

    Reads voltage_start/end/step from `params` when given, else from the config
    (where build_context puts the runner's charge_params). Half-open like
    np.arange: voltage_end itself is not measured.
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
    if np.any(np.abs(v) > 10):
        # ramp_to only rejects target > 10, so a negative typo slips past it
        raise ValueError(f"charge sweep exceeds +-10 V: {v.min()} to {v.max()}")
    return v


def run_charge_transmission_sweep(ctx, params=None):
    """Cavity transmission sweep repeated at every charge bias.

    Steps the yoko through voltage_start/end/step (params, else the runner's
    charge_params) and runs a full CavitySpecFF frequency sweep at each bias,
    building a transmission-vs-(frequency, voltage) heatmap. Every slice is
    saved by CavitySpecFF as usual; the map, the per-voltage I/Q and the tracked
    resonator frequency are saved alongside the last slice.

    params (all optional): reps, rounds, span, num_points, fit (per-slice hanger
    fit -> adds a fit-minimum trace), settle_s (wait after each ramp),
    voltage_start / voltage_end / voltage_step (override charge_params).

    ctx.config is left untouched: unlike run_transmission_sweep this does NOT
    write the found cavity frequency back, since "the" cavity frequency is not
    defined across a charge sweep. The yoko returns to its starting bias, also
    on an error or Ctrl-C.
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

    # CavitySpecFF.acquire() sweeps cfg["pulse_freq"] in place and display(fit=True)
    # rewrites it with the fitted minimum, so every slice has to start again from
    # the same centre rather than from whatever the previous slice left behind.
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

    v_return = float(ctx.yoko.query(":SOUR:LEV?"))
    # An abort must not leave the bias parked at an arbitrary point: every later
    # measurement in the session would silently run at that charge offset.
    try:
        for i, voltage in enumerate(voltage_pts):
            print(f"[ChargeTransmissionSweep] bias {i + 1}/{len(voltage_pts)}: {voltage:.6f} V")
            if not ctx.yoko_fixed:
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
            CavitySpecFF.display(Instance_trans, data_trans, plotDisp=False, figNum=20, fit=do_fit)
            CavitySpecFF.save_data(Instance_trans, data_trans)
            CavitySpecFF.save_config(Instance_trans)

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

            # ── live heatmap, built once the frequency axis length is known ──
            if db_map is None:
                x_pts = (fpts + lo_mhz) / 1e3  # GHz absolute, as in CavitySpecFF
                db_map = np.full((len(voltage_pts), len(x_pts)), np.nan)
                avgi_map = np.full_like(db_map, np.nan)
                avgq_map = np.full_like(db_map, np.nan)
                plt.ion()
                fig, ax = plt.subplots(figsize=(8, 6))
                x_step = x_pts[1] - x_pts[0] if len(x_pts) > 1 else 1
                y_step = voltage_pts[1] - voltage_pts[0] if len(voltage_pts) > 1 else 1
                im = ax.imshow(
                    db_map,
                    aspect="auto",
                    origin="lower",
                    interpolation="none",
                    extent=[
                        x_pts[0] - x_step / 2,
                        x_pts[-1] + x_step / 2,
                        voltage_pts[0] - y_step / 2,
                        voltage_pts[-1] + y_step / 2,
                    ],
                )
                cbar = fig.colorbar(im, ax=ax)
                cbar.set_label("Transmission (dB)")
                ax.set_xlabel("Cavity Frequency (GHz)")
                ax.set_ylabel("Voltage (V)")
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
            ax.set_title(f"Charge sweep for cavity transmission\nVoltage = {voltage:.6f}")
            fig.canvas.draw_idle()
            plt.pause(0.1)
    finally:
        if not ctx.yoko_fixed:
            ramp_to(ctx.yoko, v_return)

    if db_map is None:  # every slice failed before the first one landed
        return

    # tracked resonator frequency over the sweep, on the same GHz axis
    ax.plot(
        (raw_extremum + lo_mhz) / 1e3,
        voltage_pts,
        ".-",
        color="white",
        linewidth=1,
        markersize=4,
        label=f"raw {'min' if ctx.cavity_min else 'max'}",
    )
    if np.any(np.isfinite(fit_extremum)):
        ax.plot(
            (fit_extremum + lo_mhz) / 1e3,
            voltage_pts,
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
    np.savez(
        Instance_trans.fname[:-3] + "_ChargeTransmissionHeatmap.npz",
        db_map=db_map,
        avgi_map=avgi_map,
        avgq_map=avgq_map,
        fpts_mhz=(np.asarray(x_pts) * 1e3 - lo_mhz),
        x_pts_ghz=np.asarray(x_pts),
        voltage_pts=voltage_pts,
        raw_extremum_mhz=raw_extremum,
        fit_extremum_mhz=fit_extremum,
        cavity_min=ctx.cavity_min,
    )

    span_khz = 1e3 * (np.nanmax(raw_extremum) - np.nanmin(raw_extremum))
    print(
        f"[ChargeTransmissionSweep] resonator frequency moved "
        f"{span_khz:.3f} kHz over {voltage_pts[0]:.6f} to "
        f"{voltage_pts[-1]:.6f} V"
    )

    plt.ioff()
    plt.close(fig)
