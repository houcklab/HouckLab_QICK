"""TWPA pump (freq x power) sweep at parked bias; PNA-X band (or CW) gain per point.

Each pump-frequency row starts with one pump-RF-OFF reference trace; gain = |S21|_on - |S21|_off
(dB) per signal frequency, so drift slower than a row cancels. The best point is the largest
band-mean gain. Pump RF off on exit. Reads the TWPA bias read-only into the npz and appends the
end state to the TWPA state log. See docs/experiments/twpa.md.
"""

import os
import sys
import time
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pyvisa

from qicklab.core.io import write_provenance
from qicklab.hardware.pnax import band_mean_dB, measure_s21_band
from qicklab.hardware.synthhd import SynthHD, set_pump_channels
from qicklab.twpa.common import (
    append_state,
    bias_npz_fields,
    pump_state,
    query_bias,
    timestamped_paths,
)

PUMP_SYNTH_PORT = "COM5"  # SynthHD USB/serial COM port
PUMP_CHANNELS = [1]  # SynthHD channels to drive identically

F_START_GHz = 10.7
F_STOP_GHz = 10.73
N_FREQ_POINTS = 401

P_START_dBm = -10
P_STOP_dBm = 0
N_POWER_POINTS = 21
PUMP_POWER_MAX_dBm = 20.0  # hard ceiling — script refuses P > this

SETTLE_AFTER_FREQ_S = 0.20  # PLL lock + thermal settle
SETTLE_AFTER_POWER_S = 0.05  # power-only update settle

PNAX_ADDRESS = "GPIB0::16::INSTR"
# What the PNA-X measures: "BAND" = |S21| at PNAX_N_FREQ_POINTS across
# [PNAX_F_START_HZ, PNAX_F_STOP_HZ]; "CW" = |S21| at PNAX_CW_FREQ_HZ (single tone, faster).
# Figure of merit either way: band-mean gain = |S21| ON - |S21| of the row's pump-OFF trace (dB).
PNAX_MEAS_MODE = "BAND"
PNAX_CW_FREQ_HZ = 7.0e9  # CW tone (used only when PNAX_MEAS_MODE == "CW")
PNAX_F_START_HZ = 6e9
PNAX_F_STOP_HZ = 8e9
PNAX_N_FREQ_POINTS = 21  # points across the band (BAND mode only)
PNAX_IF_BW_HZ = 500.0
PNAX_POWER_dBm = -25.0  # keep low — the TWPA may be under-pumped at start
PNAX_N_AVG = 100  # sweep-averaging count (1 = off)
PNAX_TIMEOUT_MS = 30000  # floor of the estimated VISA timeout

SAVE_DIR = r"V:/t1Team/Data/2026-10-01_BFC_cooldown/TWPA_calibration"
RUN_TAG = "pump_sweep"


def estimate_group_timeout_ms(n_points, if_bw_hz, n_avg, floor_ms):
    """VISA timeout for a group of n_avg sweeps of ~n_points/IF_BW s each: 3x + 5 s, >= floor_ms.

    Why: docs/hardware.md#pna-x-at-gpib01616instr."""
    n_sweeps = max(int(n_avg), 1)
    per_sweep_s = n_points / max(if_bw_hz, 1.0)
    est_ms = (per_sweep_s * n_sweeps) * 3.0 * 1000.0 + 5000.0
    return int(max(floor_ms, est_ms))


def configure_pnax(
    pnax,
    meas_mode,
    f_start_hz,
    f_stop_hz,
    n_points,
    cw_freq_hz,
    if_bw_hz,
    power_dbm,
    n_avg,
    timeout_ms,
):
    eff_points = 1 if meas_mode == "CW" else n_points
    pnax.timeout = estimate_group_timeout_ms(eff_points, if_bw_hz, n_avg, timeout_ms)
    pnax.write("*CLS")
    pnax.write("SYST:FPR")
    pnax.write("CALC:PAR:DEL:ALL")
    pnax.write("CALC:PAR:DEF:EXT 'CH1_S21', 'S21'")
    pnax.write("CALC:PAR:SEL 'CH1_S21'")
    pnax.write("DISP:WIND1:STAT ON")
    pnax.write("DISP:WIND1:TRAC1:FEED 'CH1_S21'")
    pnax.write("CALC:FORM MLOG")
    if meas_mode == "CW":
        # Single-tone: zero-span CW sweep at one frequency, one point.
        pnax.write("SENS:SWE:TYPE CW")
        pnax.write(f"SENS:FREQ:CW {cw_freq_hz:.6e}")
        pnax.write("SENS:SWE:POIN 1")
    else:
        pnax.write("SENS:SWE:TYPE LIN")
        pnax.write(f"SENS:FREQ:STAR {f_start_hz:.6e}")
        pnax.write(f"SENS:FREQ:STOP {f_stop_hz:.6e}")
        pnax.write(f"SENS:SWE:POIN {int(n_points)}")
    pnax.write(f"SENS:BWID {if_bw_hz:.6e}")
    pnax.write(f"SOUR:POW1 {power_dbm:.2f}")
    pnax.write("SOUR:POW1:MODE ON")
    if n_avg and int(n_avg) > 1:
        pnax.write(f"SENS:AVER:COUN {int(n_avg)}")
        pnax.write("SENS:AVER ON")
        pnax.write("SENS:AVER:CLE")
    else:
        pnax.write("SENS:AVER OFF")
    pnax.write("TRIG:SOUR IMM")
    pnax.write("SENS:SWE:MODE HOLD")
    pnax.query("*OPC?")


def disable_pump_channels(channels):
    """Write rf_enable = False to every channel; True only if every write succeeded."""
    ok = True
    for ch in channels:
        try:
            ch.rf_enable = False
        except Exception as e:
            ok = False
            print(f"[twpa_pump_sweep] WARNING: failed to disable a channel: {e}")
    return ok


def gain_trace_dB(s21_on, s21_off):
    """Per-signal-frequency gain (dB) = 20 log10|S21_on| - 20 log10|S21_off| (broadcasts)."""
    with np.errstate(divide="ignore", invalid="ignore"):
        return 20.0 * np.log10(np.abs(s21_on)) - 20.0 * np.log10(np.abs(s21_off))


def gain_band_stats(gain_dB):
    """(band mean, band min, ripple = max - min) of gain_dB over its last axis; NaN-safe."""
    gain_dB = np.asarray(gain_dB, dtype=float)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN slices -> NaN
        g_mean = np.nanmean(gain_dB, axis=-1)
        g_min = np.nanmin(gain_dB, axis=-1)
        g_max = np.nanmax(gain_dB, axis=-1)
    return g_mean, g_min, g_max - g_min


def best_point(fom, completed):
    """(i, j) of the largest finite fom among completed points, or None if there is none."""
    masked = np.where(np.isfinite(fom) & completed, fom, np.nan)
    if not np.isfinite(masked).any():
        return None
    i, j = np.unravel_index(int(np.nanargmax(masked)), masked.shape)
    return int(i), int(j)


def save_npz_atomic(npz_path, **arrays):
    """Write npz_path via ``<npz_path>.tmp`` + os.replace, so a crash never leaves a torn file.

    A failed write (e.g. a transient network-drive error) prints a warning and returns
    False instead of raising, so the sweep keeps running and the next save retries. If the
    temp file was written completely but the rename failed (e.g. the npz is open elsewhere),
    the temp file is kept and the warning names it: it holds the newest data."""
    tmp_path = npz_path + ".tmp"
    written = False
    try:
        with open(tmp_path, "wb") as f:  # a file handle: numpy appends no second ".npz"
            np.savez(f, **arrays)
        written = True
        os.replace(tmp_path, npz_path)
    except OSError as e:
        if written:
            where = f"the newest data is complete in {tmp_path}"
        else:
            where = f"{npz_path} keeps the last successful save"
            try:
                os.remove(tmp_path)  # torn temp file
            except OSError:
                pass
        print(f"[twpa_pump_sweep] WARNING: saving {npz_path} failed ({e}); {where}.")
        return False
    return True


def main():
    if max(P_START_dBm, P_STOP_dBm) > PUMP_POWER_MAX_dBm:
        raise ValueError(
            f"Power sweep reaches {max(P_START_dBm, P_STOP_dBm):+.2f} dBm, above "
            f"PUMP_POWER_MAX_dBm = {PUMP_POWER_MAX_dBm:+.2f} dBm."
        )
    if F_START_GHz <= 0 or F_STOP_GHz <= 0:
        raise ValueError("Pump frequencies must be > 0.")
    if PNAX_MEAS_MODE not in ("BAND", "CW"):
        raise ValueError("PNAX_MEAS_MODE must be 'BAND' or 'CW'.")
    if PNAX_MEAS_MODE == "BAND" and PNAX_F_STOP_HZ <= PNAX_F_START_HZ:
        raise ValueError("PNAX_F_STOP_HZ must be greater than PNAX_F_START_HZ.")
    if PNAX_MEAS_MODE == "CW" and PNAX_CW_FREQ_HZ <= 0:
        raise ValueError("PNAX_CW_FREQ_HZ must be > 0.")

    freqs_GHz = np.linspace(F_START_GHz, F_STOP_GHz, N_FREQ_POINTS)
    powers_dBm = np.linspace(P_START_dBm, P_STOP_dBm, N_POWER_POINTS)
    freqs_Hz = freqs_GHz * 1e9
    cw_mode = PNAX_MEAS_MODE == "CW"
    if cw_mode:
        n_freq = 1
        pnax_freq_hz = np.array([PNAX_CW_FREQ_HZ])
        fom_desc = f"gain (dB, ON - row OFF) at {PNAX_CW_FREQ_HZ / 1e9:.4f} GHz CW tone"
    else:
        n_freq = PNAX_N_FREQ_POINTS
        pnax_freq_hz = np.linspace(PNAX_F_START_HZ, PNAX_F_STOP_HZ, PNAX_N_FREQ_POINTS)
        fom_desc = "band-mean gain (dB, ON - row OFF); band-min gain and ripple reported"
    band_GHz = (PNAX_F_START_HZ / 1e9, PNAX_F_STOP_HZ / 1e9)

    n_total = N_FREQ_POINTS * N_POWER_POINTS
    s21_band = np.full((N_FREQ_POINTS, N_POWER_POINTS, n_freq), np.nan + 1j * np.nan, dtype=complex)
    mean_band_dB = np.full((N_FREQ_POINTS, N_POWER_POINTS), np.nan)
    completed = np.zeros((N_FREQ_POINTS, N_POWER_POINTS), dtype=bool)
    # Pump-RF-OFF reference, one per frequency row, and the gain against it.
    s21_off = np.full((N_FREQ_POINTS, n_freq), np.nan + 1j * np.nan, dtype=complex)
    off_band_dB = np.full(N_FREQ_POINTS, np.nan)
    off_completed = np.zeros(N_FREQ_POINTS, dtype=bool)
    gain_band_dB = np.full((N_FREQ_POINTS, N_POWER_POINTS), np.nan)  # band-mean gain
    gain_min_dB = np.full((N_FREQ_POINTS, N_POWER_POINTS), np.nan)  # band-min gain
    gain_ripple_dB = np.full((N_FREQ_POINTS, N_POWER_POINTS), np.nan)  # band max - min

    print("=" * 72)
    print("TWPA PUMP (FREQ, POWER) SWEEP + PNA-X banded S21")
    print(f"  SynthHD port    : {PUMP_SYNTH_PORT}    channels = {list(PUMP_CHANNELS)}")
    print(f"  PNA-X           : {PNAX_ADDRESS}")
    print(
        f"  freq grid       : {N_FREQ_POINTS} pts  {F_START_GHz:.4f} → {F_STOP_GHz:.4f} GHz "
        f"(Δ = {(F_STOP_GHz - F_START_GHz) / (N_FREQ_POINTS - 1) * 1e3:.2f} MHz)"
    )
    print(
        f"  power grid      : {N_POWER_POINTS} pts  {P_START_dBm:+.2f} → {P_STOP_dBm:+.2f} dBm "
        f"(Δ = {(P_STOP_dBm - P_START_dBm) / (N_POWER_POINTS - 1):.2f} dB)"
    )
    print(f"  power ceiling   : {PUMP_POWER_MAX_dBm:+.2f} dBm")
    print(f"  scheme          : channels {list(PUMP_CHANNELS)} driven identically")
    if cw_mode:
        print(
            f"  PNA-X mode      : CW @ {PNAX_CW_FREQ_HZ / 1e9:.6f} GHz   "
            f"IF BW = {PNAX_IF_BW_HZ:g} Hz   "
            f"P = {PNAX_POWER_dBm:+.1f} dBm   N_avg = {PNAX_N_AVG}"
        )
    else:
        print(
            f"  PNA-X band      : {band_GHz[0]:.6f} → {band_GHz[1]:.6f} GHz   "
            f"{PNAX_N_FREQ_POINTS} pts   IF BW = {PNAX_IF_BW_HZ:g} Hz   "
            f"P = {PNAX_POWER_dBm:+.1f} dBm   N_avg = {PNAX_N_AVG}"
        )
    print(f"  figure of merit : {fom_desc}")
    # Wall-clock estimate, dominated by the PNA-X sweeps (per-point dwell ~ 1/IF_BW).
    per_sweep_s = n_freq / max(PNAX_IF_BW_HZ, 1.0)
    per_meas_s = per_sweep_s * max(int(PNAX_N_AVG), 1)
    # + one pump-OFF reference per row (its own settle, then the RF-on settle).
    est_s = n_total * (per_meas_s + SETTLE_AFTER_POWER_S) + N_FREQ_POINTS * (
        per_meas_s + 2 * SETTLE_AFTER_FREQ_S
    )
    print(
        f"  total points    : {n_total} + {N_FREQ_POINTS} pump-OFF refs  "
        f"(est. ~{est_s / 60.0:.1f} min wall-clock: "
        f"{per_meas_s:.2f} s/point PNA-X + settles; excludes VISA/transfer/save overhead)"
    )
    print(f"  save dir        : {SAVE_DIR}")
    print()
    print("CONFIRM:")
    print("  [ ] DC bias is already at its operating point (twpa_set_bias.py).")
    print("  [ ] The SynthHD is wired to the pump line(s), nothing else is driving them.")
    print(f"  [ ] PNA-X RF output safe at {PNAX_POWER_dBm:+.1f} dBm into the line at this bias.")
    print("=" * 72)
    ans = input("Type 'yes' to proceed: ").strip().lower()
    if ans not in ("y", "yes"):
        print("[twpa_pump_sweep] Aborted by user.")
        sys.exit(0)

    npz_path, png_path = timestamped_paths(SAVE_DIR, RUN_TAG)
    t_start = time.time()  # provenance start_time

    def save():
        ok = save_npz_atomic(
            npz_path,
            freqs_GHz=freqs_GHz,
            powers_dBm=powers_dBm,
            pnax_freq_hz=pnax_freq_hz,
            s21_band=s21_band,
            mean_band_dB=mean_band_dB,
            completed=completed,
            s21_off=s21_off,
            off_band_dB=off_band_dB,
            off_completed=off_completed,
            gain_band_dB=gain_band_dB,
            gain_min_dB=gain_min_dB,
            gain_ripple_dB=gain_ripple_dB,
            meas_mode=PNAX_MEAS_MODE,
            pnax_cw_freq_hz=PNAX_CW_FREQ_HZ,
            pnax_f_start_hz=PNAX_F_START_HZ,
            pnax_f_stop_hz=PNAX_F_STOP_HZ,
            pnax_if_bw_hz=PNAX_IF_BW_HZ,
            pnax_power_dbm=PNAX_POWER_dBm,
            pump_power_max_dbm=PUMP_POWER_MAX_dBm,
            pump_synth_port=PUMP_SYNTH_PORT,
            pump_channels=np.array(PUMP_CHANNELS),
            scheme="identical_channels",
            **bias_npz_fields(bias),
        )
        write_provenance(npz_path[: -len(".npz")], t_start=t_start)
        return ok

    unsaved = False  # data measured since the last successful save
    saved_once = False  # npz_path has been written at least once

    rm = pyvisa.ResourceManager()
    # Read-only TWPA bias readback for the npz and the state log (never writes to the YOKO).
    bias = query_bias(rm, tag="twpa_pump_sweep")
    pnax = rm.open_resource(PNAX_ADDRESS)

    synth = None  # connected inside the try, so a failed connect is logged too
    pump_channels = []

    outcome = "error"  # -> "completed" after the last row, "interrupted" on Ctrl-C
    t0 = time.time()
    try:
        # Connecting disables RF on both channels and locks to the external 10 MHz reference.
        synth = SynthHD(PUMP_SYNTH_PORT)
        pump_channels = [synth[i] for i in PUMP_CHANNELS]

        # Start every channel disabled at the sweep's lowest power / first freq
        set_pump_channels(pump_channels, freqs_Hz[0], powers_dBm[0], rf_enable=False)

        configure_pnax(
            pnax,
            PNAX_MEAS_MODE,
            PNAX_F_START_HZ,
            PNAX_F_STOP_HZ,
            PNAX_N_FREQ_POINTS,
            PNAX_CW_FREQ_HZ,
            PNAX_IF_BW_HZ,
            PNAX_POWER_dBm,
            PNAX_N_AVG,
            PNAX_TIMEOUT_MS,
        )
        print(
            f"[twpa_pump_sweep] VISA timeout set to {pnax.timeout / 1000:.0f} s "
            f"for {PNAX_N_AVG}-average group sweeps "
            f"(~{n_freq / max(PNAX_IF_BW_HZ, 1.0) * PNAX_N_AVG:.0f} s/group)."
        )

        # outer = freq (slow PLL retune), inner = power
        for i, f_Hz in enumerate(freqs_Hz):
            # Pump-RF-OFF reference for this row (drift on the row timescale cancels in the gain).
            set_pump_channels(pump_channels, f_Hz, powers_dBm[0], rf_enable=False)
            time.sleep(SETTLE_AFTER_FREQ_S)
            s21_off[i] = measure_s21_band(pnax, PNAX_N_AVG)
            off_band_dB[i] = band_mean_dB(s21_off[i])
            off_completed[i] = True
            unsaved = True

            # Re-tune frequency at the inner-loop start power, then enable RF.
            set_pump_channels(pump_channels, f_Hz, powers_dBm[0], rf_enable=True)
            time.sleep(SETTLE_AFTER_FREQ_S)

            for j, p_dBm in enumerate(powers_dBm):
                for ch in pump_channels:
                    ch.power = float(p_dBm)
                time.sleep(SETTLE_AFTER_POWER_S)

                trace = measure_s21_band(pnax, PNAX_N_AVG)
                s21_band[i, j] = trace
                mean_band_dB[i, j] = band_mean_dB(trace)
                g_mean, g_min, g_ripple = gain_band_stats(gain_trace_dB(trace, s21_off[i]))
                gain_band_dB[i, j] = g_mean
                gain_min_dB[i, j] = g_min
                gain_ripple_dB[i, j] = g_ripple
                completed[i, j] = True
                unsaved = True

                elapsed = time.time() - t0
                n_done = int(completed.sum())
                print(
                    f"  [{n_done:>4d}/{n_total}] f={f_Hz / 1e9:7.4f} GHz  "
                    f"P={p_dBm:+6.2f} dBm  "
                    f"mean|S21|={mean_band_dB[i, j]:+7.2f} dB  "
                    f"gain={gain_band_dB[i, j]:+7.2f} dB  "
                    f"t={elapsed:6.1f}s"
                )

            # Save once per frequency row (not per point), so a crash keeps the finished rows.
            if save():
                unsaved = False
                saved_once = True
        outcome = "completed"

    except KeyboardInterrupt:
        outcome = "interrupted"
        print("\n[twpa_pump_sweep] Ctrl-C — disabling pump RF before exit.")
    finally:
        rf_off_confirmed = False  # every rf_enable=False write, or close(), succeeded
        try:
            rf_off_confirmed = disable_pump_channels(pump_channels)
        except Exception as e:
            print(f"[twpa_pump_sweep] WARNING: failed to disable pumps cleanly: {e}")
        try:
            if synth is not None:
                synth.close()  # also disables RF on both channels
                rf_off_confirmed = True
        except Exception:
            pass
        if synth is not None and not rf_off_confirmed:
            print(
                "[twpa_pump_sweep] WARNING: could not disable the pump RF or close the SynthHD; "
                "pump RF state unknown (it may still be ON). Run set_pump to switch it off."
            )
        try:
            pnax.write("SOUR:POW1:MODE OFF")
        except Exception:
            pass
        if unsaved:  # partial row from Ctrl-C / an error, or a row whose save failed
            if save():
                unsaved = False
                saved_once = True
            else:
                tmp_note = (
                    f"; the newest complete write is {npz_path}.tmp"
                    if os.path.exists(npz_path + ".tmp")
                    else ""
                )
                kept = "holds only the last successful save" if saved_once else "was never written"
                print(f"[twpa_pump_sweep] WARNING: data NOT saved: {npz_path} {kept}{tmp_note}.")
        append_state(
            "twpa_pump_sweep",
            action="pump_sweep",
            outcome=outcome,
            data_file=npz_path,
            completed_points=int(completed.sum()),
            bias=bias,
            # RF off once confirmed (every disable write, or close(), succeeded); unknown (None)
            # if the connect failed, or if both the disable and close() failed
            pump=pump_state(
                PUMP_CHANNELS, None, None, False if synth is not None and rf_off_confirmed else None
            ),
            pnax={
                "address": PNAX_ADDRESS,
                "meas_mode": PNAX_MEAS_MODE,
                "cw_freq_hz": PNAX_CW_FREQ_HZ,
                "f_start_hz": PNAX_F_START_HZ,
                "f_stop_hz": PNAX_F_STOP_HZ,
                "n_points": PNAX_N_FREQ_POINTS,
                "if_bw_hz": PNAX_IF_BW_HZ,
                "power_dbm": PNAX_POWER_dBm,
                "n_avg": PNAX_N_AVG,
            },
        )
        pnax.close()

    # pcolormesh with shading='nearest' centers each cell on its (f, P)
    # coordinate — no off-by-half-cell misalignment vs sweep points.
    PP, FF = np.meshgrid(powers_dBm, freqs_GHz)

    if cw_mode:
        fig, ax1 = plt.subplots(1, 1, figsize=(7, 6))
        ax2 = None
        map_title = f"gain (dB, ON - row OFF) @ {PNAX_CW_FREQ_HZ / 1e9:.4f} GHz CW"
        cbar_label = "gain  (dB)"
    else:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 6))
        map_title = (
            f"band-mean gain (dB, ON - row OFF) over {band_GHz[0]:.3f}–{band_GHz[1]:.3f} GHz"
        )
        cbar_label = "band-mean gain  (dB)"

    pm1 = ax1.pcolormesh(PP, FF, gain_band_dB, shading="nearest", cmap="viridis")
    ax1.set_xlabel("Pump power  (dBm, pump channels)")
    ax1.set_ylabel("Pump frequency  (GHz, pump channels)")
    ax1.set_title(map_title)
    fig.colorbar(pm1, ax=ax1, label=cbar_label)

    # Mark the best pump point (and, in BAND mode, show its gain trace).
    best = best_point(gain_band_dB, completed)
    if best is not None:
        i_best, j_best = best
        ax1.plot(
            powers_dBm[j_best],
            freqs_GHz[i_best],
            "r*",
            ms=14,
            markeredgecolor="k",
            label="best point",
        )
        ax1.legend(loc="best", fontsize=8)

        if ax2 is not None:
            best_gain_dB = gain_trace_dB(s21_band[i_best, j_best], s21_off[i_best])
            ax2.plot(pnax_freq_hz / 1e9, best_gain_dB, "-")
            ax2.axhline(
                gain_band_dB[i_best, j_best],
                ls="--",
                color="C3",
                alpha=0.7,
                label=f"band mean = {gain_band_dB[i_best, j_best]:+.2f} dB",
            )
            ax2.set_title(
                f"Best point: f={freqs_GHz[i_best]:.4f} GHz, P={powers_dBm[j_best]:+.2f} dBm\n"
                f"band-min gain {gain_min_dB[i_best, j_best]:+.2f} dB, "
                f"ripple {gain_ripple_dB[i_best, j_best]:.2f} dB"
            )
            ax2.legend(loc="best", fontsize=8)
    if ax2 is not None:
        ax2.set_xlabel("Signal frequency  (GHz)")
        ax2.set_ylabel("gain = |S21|_on - |S21|_off  (dB)")
        ax2.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(png_path, dpi=140)
    if saved_once and not unsaved:
        print(f"[twpa_pump_sweep] Saved: {npz_path}")
    elif not saved_once and not unsaved:
        print("[twpa_pump_sweep] No data measured; no npz written.")
    print(f"[twpa_pump_sweep] Saved: {png_path}")

    finite = np.isfinite(gain_band_dB) & completed
    if finite.sum() >= 3:
        i_max, j_max = best_point(gain_band_dB, completed)
        where = (
            f"at {PNAX_CW_FREQ_HZ / 1e9:.4f} GHz CW"
            if cw_mode
            else f"over {band_GHz[0]:.3f}–{band_GHz[1]:.3f} GHz"
        )
        print("[twpa_pump_sweep] Best pump point for band-mean gain (ON - row pump-OFF):")
        print(
            f"  f = {freqs_GHz[i_max]:.4f} GHz   P = {powers_dBm[j_max]:+.2f} dBm   "
            f"gain = {gain_band_dB[i_max, j_max]:+.2f} dB {where}"
        )
        print(
            f"  band-min gain = {gain_min_dB[i_max, j_max]:+.2f} dB   "
            f"ripple (max - min) = {gain_ripple_dB[i_max, j_max]:.2f} dB   "
            f"|S21| ON = {mean_band_dB[i_max, j_max]:+.2f} dB, OFF = {off_band_dB[i_max]:+.2f} dB"
        )


if __name__ == "__main__":
    main()
