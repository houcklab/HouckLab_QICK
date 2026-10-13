"""TWPA gain: PNA-X |S21| across the signal band, pump OFF vs ON, interleaved over N_REPEATS.

gain(f) = |S21|_on - |S21|_off (dB); pump RF off on exit. See docs/experiments/twpa.md.
"""

import sys
import time

import matplotlib.pyplot as plt
import numpy as np
import pyvisa

from qicklab.hardware.synthhd import SynthHD, set_pump_channels
from qicklab.twpa.common import timestamped_paths

PUMP_SYNTH_PORT = "COM5"  # SynthHD USB/serial COM port
PUMP_CHANNELS = [1]  # SynthHD channels to drive identically

# Pump ON operating point (the optimum from qicklab.twpa.pump_sweep for this band).
PUMP_ON_FREQ_GHz = 10.7165
PUMP_ON_POWER_dBm = -5.5  # per channel, identical
PUMP_POWER_MAX_dBm = 0.0  # hard ceiling — script refuses ON power above this

F_SIGNAL_START_GHz = 2.0
F_SIGNAL_STOP_GHz = 10.0
N_SIGNAL_POINTS = 401  # PNA-X linear-sweep points across the band

N_REPEATS = 10  # OFF/ON trace pairs to average (drift suppression)
SETTLE_AFTER_PUMP_S = 0.30  # PLL lock + thermal settle after toggling pump state

PNAX_ADDRESS = "GPIB0::16::INSTR"
PNAX_IF_BW_HZ = 1000.0
PNAX_POWER_dBm = -25.0  # keep low — signal must not saturate the TWPA
PNAX_TIMEOUT_MS = 60000

SAVE_DIR = r"V:/t1Team/Data/2026-10-01_BFC_cooldown/TWPA_calibration"
RUN_TAG = "gain_on_vs_off"


def configure_pnax(pnax, f_start_hz, f_stop_hz, n_points, if_bw_hz, power_dbm, timeout_ms):
    pnax.timeout = timeout_ms
    pnax.write("*CLS")
    pnax.write("SYST:FPR")  # full preset
    pnax.write("CALC:PAR:DEL:ALL")
    pnax.write("CALC:PAR:DEF:EXT 'CH1_S21', 'S21'")
    pnax.write("CALC:PAR:SEL 'CH1_S21'")
    pnax.write("DISP:WIND1:STAT ON")
    pnax.write("DISP:WIND1:TRAC1:FEED 'CH1_S21'")
    pnax.write("CALC:FORM MLOG")
    pnax.write("SENS:SWE:TYPE LIN")
    pnax.write(f"SENS:FREQ:STAR {f_start_hz:.6e}")
    pnax.write(f"SENS:FREQ:STOP {f_stop_hz:.6e}")
    pnax.write(f"SENS:SWE:POIN {int(n_points)}")
    pnax.write(f"SENS:BWID {if_bw_hz:.6e}")
    pnax.write(f"SOUR:POW1 {power_dbm:.2f}")
    pnax.write("SOUR:POW1:MODE ON")
    pnax.write("SENS:AVER OFF")
    pnax.write("TRIG:SOUR IMM")
    pnax.write("SENS:SWE:MODE HOLD")
    pnax.query("*OPC?")


def read_freq_axis(pnax, f_start_hz, f_stop_hz, n_points):
    """Read the stimulus frequency axis from the PNA-X, falling back to a
    computed linspace if the instrument does not return a usable payload."""
    try:
        raw = pnax.query("SENS:X?")
        x = np.fromstring(raw, sep=",")
        if x.size == n_points:
            return x
    except Exception:
        pass
    return np.linspace(f_start_hz, f_stop_hz, n_points)


def measure_s21_trace(pnax, n_points):
    """Trigger one full linear sweep and return the complex S21 trace."""
    pnax.write("SENS:SWE:MODE SING")
    pnax.query("*OPC?")
    raw = pnax.query("CALC:DATA? SDATA")
    vals = np.fromstring(raw, sep=",")
    if vals.size != 2 * n_points:
        raise RuntimeError(
            f"Unexpected SDATA payload from PNA-X: {vals.size} values "
            f"(expected {2 * n_points} for {n_points} points)"
        )
    return vals[0::2] + 1j * vals[1::2]


def disable_pump_channels(channels):
    for ch in channels:
        try:
            ch.rf_enable = False
        except Exception as e:
            print(f"[twpa_gain_compare] WARNING: failed to disable a channel: {e}")


def main():
    if PUMP_ON_POWER_dBm > PUMP_POWER_MAX_dBm:
        raise ValueError(
            f"PUMP_ON_POWER_dBm = {PUMP_ON_POWER_dBm:+.2f} dBm exceeds "
            f"PUMP_POWER_MAX_dBm = {PUMP_POWER_MAX_dBm:+.2f} dBm."
        )
    if PUMP_ON_FREQ_GHz <= 0:
        raise ValueError("PUMP_ON_FREQ_GHz must be > 0.")
    if F_SIGNAL_START_GHz <= 0 or F_SIGNAL_STOP_GHz <= F_SIGNAL_START_GHz:
        raise ValueError("Require 0 < F_SIGNAL_START_GHz < F_SIGNAL_STOP_GHz.")
    if N_REPEATS < 1:
        raise ValueError("N_REPEATS must be ≥ 1.")

    f_start_hz = F_SIGNAL_START_GHz * 1e9
    f_stop_hz = F_SIGNAL_STOP_GHz * 1e9
    pump_on_hz = PUMP_ON_FREQ_GHz * 1e9

    s21_off = np.full((N_REPEATS, N_SIGNAL_POINTS), np.nan + 1j * np.nan, dtype=complex)
    s21_on = np.full((N_REPEATS, N_SIGNAL_POINTS), np.nan + 1j * np.nan, dtype=complex)

    print("=" * 72)
    print("TWPA GAIN: PUMP ON vs OFF  (|S21| across signal band)")
    print(f"  SynthHD port    : {PUMP_SYNTH_PORT}    channels = {list(PUMP_CHANNELS)}")
    print(f"  PNA-X           : {PNAX_ADDRESS}")
    print(
        f"  pump ON point   : {PUMP_ON_FREQ_GHz:.4f} GHz   {PUMP_ON_POWER_dBm:+.2f} dBm "
        f"(per channel, identical)"
    )
    print(f"  power ceiling   : {PUMP_POWER_MAX_dBm:+.2f} dBm")
    print(
        f"  signal band     : {N_SIGNAL_POINTS} pts  {F_SIGNAL_START_GHz:.4f} → "
        f"{F_SIGNAL_STOP_GHz:.4f} GHz "
        f"(Δ = {(F_SIGNAL_STOP_GHz - F_SIGNAL_START_GHz) / (N_SIGNAL_POINTS - 1) * 1e3:.3f} MHz)"
    )
    print(f"  PNA-X           : IF BW = {PNAX_IF_BW_HZ:g} Hz   P = {PNAX_POWER_dBm:+.1f} dBm")
    print(f"  repeats         : {N_REPEATS}  (OFF/ON interleaved per repeat)")
    print(f"  save dir        : {SAVE_DIR}")
    print()
    print("CONFIRM:")
    print("  [ ] DC bias is already at its operating point (twpa_set_bias.py).")
    print("  [ ] The SynthHD is wired to the pump line(s), nothing else is driving them.")
    print(f"  [ ] PNA-X RF output safe at {PNAX_POWER_dBm:+.1f} dBm into the line.")
    print("=" * 72)
    ans = input("Type 'yes' to proceed: ").strip().lower()
    if ans not in ("y", "yes"):
        print("[twpa_gain_compare] Aborted by user.")
        sys.exit(0)

    npz_path, png_path = timestamped_paths(SAVE_DIR, RUN_TAG)

    rm = pyvisa.ResourceManager()
    pnax = rm.open_resource(PNAX_ADDRESS)

    # Connecting disables RF on both channels and locks to the external 10 MHz reference.
    synth = SynthHD(PUMP_SYNTH_PORT)
    pump_channels = [synth[i] for i in PUMP_CHANNELS]

    freqs_Hz = None
    t0 = time.time()
    try:
        # Park the pump at the ON point but RF disabled to start.
        set_pump_channels(pump_channels, pump_on_hz, PUMP_ON_POWER_dBm, rf_enable=False)

        configure_pnax(
            pnax,
            f_start_hz,
            f_stop_hz,
            N_SIGNAL_POINTS,
            PNAX_IF_BW_HZ,
            PNAX_POWER_dBm,
            PNAX_TIMEOUT_MS,
        )
        freqs_Hz = read_freq_axis(pnax, f_start_hz, f_stop_hz, N_SIGNAL_POINTS)

        for r in range(N_REPEATS):
            # OFF: disable pump RF (freq/power left parked at the ON point).
            disable_pump_channels(pump_channels)
            time.sleep(SETTLE_AFTER_PUMP_S)
            s21_off[r] = measure_s21_trace(pnax, N_SIGNAL_POINTS)

            # ON: program the operating point and enable RF.
            set_pump_channels(pump_channels, pump_on_hz, PUMP_ON_POWER_dBm, rf_enable=True)
            time.sleep(SETTLE_AFTER_PUMP_S)
            s21_on[r] = measure_s21_trace(pnax, N_SIGNAL_POINTS)

            off_dB = 20 * np.log10(np.abs(s21_off[r]))
            on_dB = 20 * np.log10(np.abs(s21_on[r]))
            gain_dB = on_dB - off_dB
            elapsed = time.time() - t0
            print(
                f"  repeat [{r + 1:>2d}/{N_REPEATS}]  "
                f"mean gain = {np.nanmean(gain_dB):+6.2f} dB   "
                f"band-max = {np.nanmax(gain_dB):+6.2f} dB   "
                f"t={elapsed:6.1f}s"
            )

            # Incremental save so a crash mid-run keeps the partial dataset.
            np.savez(
                npz_path,
                freqs_Hz=freqs_Hz,
                s21_off=s21_off,
                s21_on=s21_on,
                completed_repeats=r + 1,
                pump_on_freq_hz=pump_on_hz,
                pump_on_power_dbm=PUMP_ON_POWER_dBm,
                pump_power_max_dbm=PUMP_POWER_MAX_dBm,
                pump_synth_port=PUMP_SYNTH_PORT,
                pump_channels=np.array(PUMP_CHANNELS),
                pnax_if_bw_hz=PNAX_IF_BW_HZ,
                pnax_power_dbm=PNAX_POWER_dBm,
                scheme="identical_channels",
            )

    except KeyboardInterrupt:
        print("\n[twpa_gain_compare] Ctrl-C — disabling pump RF before exit.")
    finally:
        try:
            disable_pump_channels(pump_channels)
        except Exception as e:
            print(f"[twpa_gain_compare] WARNING: failed to disable pumps cleanly: {e}")
        try:
            synth.close()
        except Exception:
            pass
        try:
            pnax.write("SOUR:POW1:MODE OFF")
        except Exception:
            pass
        pnax.close()

    if freqs_Hz is None:
        freqs_Hz = np.linspace(f_start_hz, f_stop_hz, N_SIGNAL_POINTS)
    freqs_GHz = freqs_Hz / 1e9

    # Average in dB across completed repeats (NaN-safe).
    off_dB_all = 20 * np.log10(np.abs(s21_off))
    on_dB_all = 20 * np.log10(np.abs(s21_on))
    off_dB = np.nanmean(off_dB_all, axis=0)
    on_dB = np.nanmean(on_dB_all, axis=0)
    gain_dB = on_dB - off_dB

    fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize=(8, 7))

    ax1.plot(freqs_GHz, off_dB, "-", lw=1.2, color="C0", label="pump OFF")
    ax1.plot(freqs_GHz, on_dB, "-", lw=1.2, color="C3", label="pump ON")
    ax1.set_ylabel("|S21|  (dB)")
    ax1.grid(True, alpha=0.3)
    ax1.set_title(
        f"TWPA gain: pump ON vs OFF   "
        f"(pump {PUMP_ON_FREQ_GHz:.4f} GHz, {PUMP_ON_POWER_dBm:+.1f} dBm, "
        f"{N_REPEATS} reps)"
    )
    ax1.legend(loc="best", fontsize=9)

    ax2.plot(freqs_GHz, gain_dB, "-", lw=1.2, color="C2")
    ax2.axhline(0.0, ls="--", alpha=0.4, color="k")
    ax2.set_ylabel("gain = ON − OFF  (dB)")
    ax2.set_xlabel("Signal frequency  (GHz)")
    ax2.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(png_path, dpi=140)
    print(f"[twpa_gain_compare] Saved: {npz_path}")
    print(f"[twpa_gain_compare] Saved: {png_path}")

    finite = np.isfinite(gain_dB)
    if finite.sum() >= 3:
        k_max = np.nanargmax(gain_dB)
        print("[twpa_gain_compare] Gain (pump ON − OFF):")
        print(f"  band-mean gain : {np.nanmean(gain_dB[finite]):+.2f} dB")
        print(f"  peak gain      : {gain_dB[k_max]:+.2f} dB  @ {freqs_GHz[k_max]:.4f} GHz")
        print(
            f"  ripple (max−min): {np.nanmax(gain_dB[finite]) - np.nanmin(gain_dB[finite]):.2f} dB"
        )
        if np.nanmean(gain_dB[finite]) < 1.0:
            print(
                "  ⚠ Band-mean gain < 1 dB → pump may be off-optimum, "
                "under-powered, or not reaching the TWPA."
            )
        else:
            print("  ✓ Net positive gain with the pump ON.")


if __name__ == "__main__":
    main()
