"""
twpa_gain_compare_pnax.py — TWPA gain: pump ON vs OFF, |S21| across the signal band.

Purpose
  With the DC bias already parked at its operating point (set via twpa_set_bias.py)
  and the pump (freq, power) already chosen (see twpa_pump_sweep_pnax.py), this is
  the final gain check: measure |S21| across a signal frequency band with the pump
  OFF (baseline chain response) and then ON, and report

      gain(f) = |S21|_on(f) − |S21|_off(f)     [dB]

  This is the standard TWPA gain curve — how much gain the amplifier adds, and
  over what band. A good operating point shows broadband positive gain (often
  ~15–20 dB) with modest ripple across the signal band.

  OFF and ON traces are interleaved every repeat (OFF, ON, OFF, ON, …) so slow
  thermal / cable drift between the two states largely cancels in the difference,
  then averaged over N_REPEATS.

Pump source
  Two SignalCore SC5510A signal generators over Pyro5 (sc5510a_client.py), driven
  IDENTICALLY — same frequency and power on every listed device (mirrors
  twpa_pump_sweep_pnax.py). "Pump OFF" disables RF on all of them; "pump ON"
  programs PUMP_ON_FREQ_GHz / PUMP_ON_POWER_dBm and enables RF.

Safety
  * DC bias should already be at its operating point. This script does NOT touch
    the YOKO. Verify in twpa_set_bias.py / on the panel.
  * PUMP_POWER_MAX_dBm enforces a hard ceiling on the ON power.
  * On exit (success / exception / Ctrl-C) the pump devices are RF-disabled.

Tested SCPI: Keysight PNA-X N52xx series (mirrors the other twpa_*_pnax scripts).
"""

import os
import sys
import time
import datetime as _dt

import numpy as np
import matplotlib.pyplot as plt
import pyvisa

# sc5510a_client lives in the shared PythonDrivers directory (one level up).
_DRIVERS_DIR = os.path.join(os.path.dirname(__file__), "..", "PythonDrivers")
if os.path.normpath(_DRIVERS_DIR) not in sys.path:
    sys.path.insert(0, os.path.normpath(_DRIVERS_DIR))
import sc5510a_client as sc


# ---------------------------------------------------------------------------
# User-set parameters
# ---------------------------------------------------------------------------
# --- Pump source (two SignalCore SC5510A, driven identically over Pyro5) ----
SC5510A_SERVER_HOST = "192.168.0.102"          # server PC LAN IP running the Pyro name server
PUMP_DEVICE_IDS     = ["10002D34", "10002D35"]  # TODO: the two SC5510A device ids (see sc.list_instruments())

# --- Pump ON operating point (THE knobs to set for the "on" state) ----------
# Use the optimum found in twpa_pump_sweep_pnax.py for this signal band.
# PUMP_ON_FREQ_GHz    = 10.9187                    # TODO: pump frequency for the ON state
# PUMP_ON_POWER_dBm   = -18.0                    # TODO: pump power for the ON state (per device, identical)

PUMP_ON_FREQ_GHz    = 10.9262                    # TODO: pump frequency for the ON state
PUMP_ON_POWER_dBm   = -18.3                    # TODO: pump power for the ON state (per device, identical)
PUMP_POWER_MAX_dBm  = 0.0                       # hard ceiling — script refuses ON power above this

# --- Signal band swept on the PNA-X (where we want to see TWPA gain) --------
F_SIGNAL_START_GHz  = 2.0                       # TODO: signal-band start (near the cavity / readout band)
F_SIGNAL_STOP_GHz   = 10.0                       # TODO: signal-band stop
N_SIGNAL_POINTS     = 401                       # PNA-X linear-sweep points across the band

# --- Repeats / timing -------------------------------------------------------
N_REPEATS            = 10                         # OFF/ON trace pairs to average (drift suppression)
SETTLE_AFTER_PUMP_S  = 0.30                      # PLL lock + thermal settle after toggling pump state

# --- PNA-X measurement ------------------------------------------------------
PNAX_ADDRESS         = "GPIB0::16::INSTR"
PNAX_IF_BW_HZ        = 1000.0
PNAX_POWER_dBm       = -50.0                    # keep low — signal must not saturate the TWPA
PNAX_TIMEOUT_MS      = 60000

# --- Output -----------------------------------------------------------------
SAVE_DIR             = r"V:/t1Team/Data/2026-05-29_BFC_cooldown/TWPA_calibration"
RUN_TAG              = "gain_on_vs_off"


# ---------------------------------------------------------------------------
# PNA-X helpers (Keysight PNA-X SCPI) — linear sweep across the signal band
# ---------------------------------------------------------------------------
def configure_pnax(pnax, f_start_hz, f_stop_hz, n_points, if_bw_hz, power_dbm, timeout_ms):
    pnax.timeout = timeout_ms
    pnax.write("*CLS")
    pnax.write("SYST:FPR")                                  # full preset
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
        x = np.fromstring(raw, sep=',')
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
    vals = np.fromstring(raw, sep=',')
    if vals.size != 2 * n_points:
        raise RuntimeError(
            f"Unexpected SDATA payload from PNA-X: {vals.size} values "
            f"(expected {2 * n_points} for {n_points} points)"
        )
    return vals[0::2] + 1j * vals[1::2]


# ---------------------------------------------------------------------------
# SC5510A pump helpers (mirror twpa_pump_sweep_pnax.py)
# ---------------------------------------------------------------------------
def set_pump_devices(devices, freq_hz, power_dbm, rf_enable):
    """Program every pump device identically (freq, power, RF on/off)."""
    for dev in devices:
        dev.frequency = float(freq_hz)
        dev.power = float(power_dbm)
        dev.output = bool(rf_enable)


def disable_pump_devices(devices):
    for dev in devices:
        try:
            dev.output = False
        except Exception as e:
            print(f"[twpa_gain_compare] WARNING: failed to disable a device: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    # --- Validate -----------------------------------------------------------
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
    if any("TODO" in str(d) for d in PUMP_DEVICE_IDS):
        raise ValueError(
            "PUMP_DEVICE_IDS still contains placeholders — fill in the two SC5510A "
            "device ids (run sc5510a_client.list_instruments() to discover them)."
        )

    f_start_hz = F_SIGNAL_START_GHz * 1e9
    f_stop_hz  = F_SIGNAL_STOP_GHz * 1e9
    pump_on_hz = PUMP_ON_FREQ_GHz * 1e9

    # off[r], on[r] complex traces per repeat.
    s21_off = np.full((N_REPEATS, N_SIGNAL_POINTS), np.nan + 1j * np.nan, dtype=complex)
    s21_on  = np.full((N_REPEATS, N_SIGNAL_POINTS), np.nan + 1j * np.nan, dtype=complex)

    # --- Pre-flight ---------------------------------------------------------
    print("=" * 72)
    print("TWPA GAIN: PUMP ON vs OFF  (|S21| across signal band)")
    print(f"  SC5510A server  : {SC5510A_SERVER_HOST}    devices = {PUMP_DEVICE_IDS}")
    print(f"  PNA-X           : {PNAX_ADDRESS}")
    print(f"  pump ON point   : {PUMP_ON_FREQ_GHz:.4f} GHz   {PUMP_ON_POWER_dBm:+.2f} dBm "
          f"(per device, identical)")
    print(f"  power ceiling   : {PUMP_POWER_MAX_dBm:+.2f} dBm")
    print(f"  signal band     : {N_SIGNAL_POINTS} pts  {F_SIGNAL_START_GHz:.4f} → "
          f"{F_SIGNAL_STOP_GHz:.4f} GHz "
          f"(Δ = {(F_SIGNAL_STOP_GHz-F_SIGNAL_START_GHz)/(N_SIGNAL_POINTS-1)*1e3:.3f} MHz)")
    print(f"  PNA-X           : IF BW = {PNAX_IF_BW_HZ:g} Hz   P = {PNAX_POWER_dBm:+.1f} dBm")
    print(f"  repeats         : {N_REPEATS}  (OFF/ON interleaved per repeat)")
    print(f"  save dir        : {SAVE_DIR}")
    print()
    print("CONFIRM:")
    print("  [ ] DC bias is already at its operating point (twpa_set_bias.py).")
    print("  [ ] The two SC5510A are wired to the pump line(s), nothing else is driving them.")
    print("  [ ] PNA-X RF output safe at {:+.1f} dBm into the line.".format(PNAX_POWER_dBm))
    print("=" * 72)
    ans = input("Type 'yes' to proceed: ").strip().lower()
    if ans not in ("y", "yes"):
        print("[twpa_gain_compare] Aborted by user.")
        sys.exit(0)

    os.makedirs(SAVE_DIR, exist_ok=True)
    stamp    = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    base     = os.path.join(SAVE_DIR, f"{stamp}_{RUN_TAG}")
    npz_path = base + ".npz"
    png_path = base + ".png"

    rm   = pyvisa.ResourceManager()
    pnax = rm.open_resource(PNAX_ADDRESS)

    # Connect to the two SC5510A pump devices over Pyro5.
    pump_devices = [sc.connect(dev_id, host=SC5510A_SERVER_HOST) for dev_id in PUMP_DEVICE_IDS]

    freqs_Hz = None
    t0 = time.time()
    try:
        # --- Pump source setup ---------------------------------------------
        for dev_id, dev in zip(PUMP_DEVICE_IDS, pump_devices):
            if not dev.clocked:
                print(f"[twpa_gain_compare] WARNING: SC5510A {dev_id} reports external "
                      f"reference NOT detected — check the 10 MHz ref cabling.")

        # Park the pump at the ON point but RF disabled to start.
        set_pump_devices(pump_devices, pump_on_hz, PUMP_ON_POWER_dBm, rf_enable=False)

        # --- PNA-X setup ---------------------------------------------------
        configure_pnax(pnax, f_start_hz, f_stop_hz, N_SIGNAL_POINTS,
                       PNAX_IF_BW_HZ, PNAX_POWER_dBm, PNAX_TIMEOUT_MS)
        freqs_Hz = read_freq_axis(pnax, f_start_hz, f_stop_hz, N_SIGNAL_POINTS)

        # --- Interleaved OFF/ON repeats ------------------------------------
        for r in range(N_REPEATS):
            # OFF: disable pump RF (freq/power left parked at the ON point).
            disable_pump_devices(pump_devices)
            time.sleep(SETTLE_AFTER_PUMP_S)
            s21_off[r] = measure_s21_trace(pnax, N_SIGNAL_POINTS)

            # ON: program the operating point and enable RF.
            set_pump_devices(pump_devices, pump_on_hz, PUMP_ON_POWER_dBm, rf_enable=True)
            time.sleep(SETTLE_AFTER_PUMP_S)
            s21_on[r] = measure_s21_trace(pnax, N_SIGNAL_POINTS)

            off_dB = 20 * np.log10(np.abs(s21_off[r]))
            on_dB  = 20 * np.log10(np.abs(s21_on[r]))
            gain_dB = on_dB - off_dB
            elapsed = time.time() - t0
            print(f"  repeat [{r+1:>2d}/{N_REPEATS}]  "
                  f"mean gain = {np.nanmean(gain_dB):+6.2f} dB   "
                  f"band-max = {np.nanmax(gain_dB):+6.2f} dB   "
                  f"t={elapsed:6.1f}s")

            # Incremental save so a crash mid-run keeps the partial dataset.
            np.savez(npz_path,
                     freqs_Hz=freqs_Hz,
                     s21_off=s21_off,
                     s21_on=s21_on,
                     completed_repeats=r + 1,
                     pump_on_freq_hz=pump_on_hz,
                     pump_on_power_dbm=PUMP_ON_POWER_dBm,
                     pump_power_max_dbm=PUMP_POWER_MAX_dBm,
                     pump_device_ids=np.array(PUMP_DEVICE_IDS),
                     pnax_if_bw_hz=PNAX_IF_BW_HZ,
                     pnax_power_dbm=PNAX_POWER_dBm,
                     scheme="identical_devices")

    except KeyboardInterrupt:
        print("\n[twpa_gain_compare] Ctrl-C — disabling pump RF before exit.")
    finally:
        try:
            disable_pump_devices(pump_devices)
        except Exception as e:
            print(f"[twpa_gain_compare] WARNING: failed to disable pumps cleanly: {e}")
        try:
            pnax.write("SOUR:POW1:MODE OFF")
        except Exception:
            pass
        pnax.close()

    # ---------------- Reduce ----------------
    if freqs_Hz is None:
        freqs_Hz = np.linspace(f_start_hz, f_stop_hz, N_SIGNAL_POINTS)
    freqs_GHz = freqs_Hz / 1e9

    # Average in dB across completed repeats (NaN-safe).
    off_dB_all = 20 * np.log10(np.abs(s21_off))
    on_dB_all  = 20 * np.log10(np.abs(s21_on))
    off_dB = np.nanmean(off_dB_all, axis=0)
    on_dB  = np.nanmean(on_dB_all, axis=0)
    gain_dB = on_dB - off_dB

    # ---------------- Plot ----------------
    fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize=(8, 7))

    ax1.plot(freqs_GHz, off_dB, '-', lw=1.2, color='C0', label="pump OFF")
    ax1.plot(freqs_GHz, on_dB, '-', lw=1.2, color='C3', label="pump ON")
    ax1.set_ylabel("|S21|  (dB)")
    ax1.grid(True, alpha=0.3)
    ax1.set_title(f"TWPA gain: pump ON vs OFF   "
                  f"(pump {PUMP_ON_FREQ_GHz:.4f} GHz, {PUMP_ON_POWER_dBm:+.1f} dBm, "
                  f"{N_REPEATS} reps)")
    ax1.legend(loc="best", fontsize=9)

    ax2.plot(freqs_GHz, gain_dB, '-', lw=1.2, color='C2')
    ax2.axhline(0.0, ls='--', alpha=0.4, color='k')
    ax2.set_ylabel("gain = ON − OFF  (dB)")
    ax2.set_xlabel("Signal frequency  (GHz)")
    ax2.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(png_path, dpi=140)
    print(f"[twpa_gain_compare] Saved: {npz_path}")
    print(f"[twpa_gain_compare] Saved: {png_path}")

    # ---------------- Summary ----------------
    finite = np.isfinite(gain_dB)
    if finite.sum() >= 3:
        k_max = np.nanargmax(gain_dB)
        print("[twpa_gain_compare] Gain (pump ON − OFF):")
        print(f"  band-mean gain : {np.nanmean(gain_dB[finite]):+.2f} dB")
        print(f"  peak gain      : {gain_dB[k_max]:+.2f} dB  @ {freqs_GHz[k_max]:.4f} GHz")
        print(f"  ripple (max−min): {np.nanmax(gain_dB[finite]) - np.nanmin(gain_dB[finite]):.2f} dB")
        if np.nanmean(gain_dB[finite]) < 1.0:
            print("  ⚠ Band-mean gain < 1 dB → pump may be off-optimum, "
                  "under-powered, or not reaching the TWPA.")
        else:
            print("  ✓ Net positive gain with the pump ON.")


if __name__ == "__main__":
    main()
