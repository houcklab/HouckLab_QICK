"""
twpa_set_pump.py — Park the TWPA pump at a single (frequency, power) operating point.

This is the pump-side companion to twpa_set_bias.py. Where twpa_set_bias.py ramps
the DC bias YOKO, this script sets the RF pump tone: it programs a Windfreak SynthHD
(dual-channel) signal generator to a chosen frequency and power and enables RF output.

It is intentionally measurement-free — it only drives the pump. Use a separate
sweep (twpa_pump_sweep_pnax.py) to find the right (freq, power); once you know the
operating point, use THIS script to park there before running qubit measurements.

Pump source
  One Windfreak SynthHD signal generator, connected LOCALLY over USB/serial (a COM
  port). The SynthHD has two channels; the channels listed in PUMP_CHANNELS are
  driven IDENTICALLY: same frequency, same power. (For offset/independent control,
  set per-channel offsets where the channels are programmed below.)

  Set PUMP_SYNTH_PORT to the SynthHD's COM port. The driver (pywindfreak.SynthHD)
  locks the unit to its external 10 MHz reference on connect.

Safety
  * DC bias should already be at the operating point before pumping (twpa_set_bias.py).
    This script does NOT touch the YOKO.
  * PUMP_POWER_MAX_dBm enforces a hard ceiling on the requested power.
  * The script shows the plan and requires explicit 'yes' confirmation before
    enabling RF, mirroring twpa_set_bias.py.

Usage:
  1. Verify DC bias is parked (twpa_set_bias.py).
  2. Set PUMP_SYNTH_PORT, PUMP_FREQ_GHz, PUMP_POWER_dBm below.
  3. Run. To turn the pump OFF instead, set DISABLE_PUMP = True (or run with
     '--off' on the command line).
"""

import sys

from pywindfreak import SynthHD


# ---------------------------------------------------------------------------
# User-set parameters
# ---------------------------------------------------------------------------
# --- Pump source (Windfreak SynthHD, channels driven identically) -----------
PUMP_SYNTH_PORT     = "COM5"          # SynthHD USB/serial COM port
PUMP_CHANNELS       = [0, 1]          # SynthHD channels to drive identically

# --- Operating point --------------------------------------------------------
PUMP_FREQ_GHz       = 10.875      # TODO: pump frequency at the chosen operating point
PUMP_POWER_dBm      = -1.05     # TODO: pump power at the chosen operating point
PUMP_POWER_MAX_dBm  = 0.0       # hard ceiling — script refuses power above this

DISABLE_PUMP        = True    # True (or pass '--off') to RF-disable the pump and exit


# ---------------------------------------------------------------------------
# SynthHD pump helpers (mirror twpa_pump_sweep_pnax.py)
# ---------------------------------------------------------------------------
def set_pump_channels(channels, freq_hz, power_dbm, rf_enable):
    """Program every pump channel identically (freq, power, RF on/off)."""
    for ch in channels:
        ch.frequency = float(freq_hz)
        ch.power = float(power_dbm)
        ch.rf_enable = bool(rf_enable)


def disable_pump_channels(channels):
    for ch in channels:
        try:
            ch.rf_enable = False
        except Exception as e:
            print(f"[twpa_set_pump] WARNING: failed to disable a channel: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    disable = DISABLE_PUMP or ("--off" in sys.argv[1:])

    # --- Validate -----------------------------------------------------------
    if not disable:
        if PUMP_FREQ_GHz <= 0:
            raise ValueError("PUMP_FREQ_GHz must be > 0.")
        if PUMP_POWER_dBm > PUMP_POWER_MAX_dBm:
            raise ValueError(
                f"PUMP_POWER_dBm = {PUMP_POWER_dBm:+.2f} dBm exceeds "
                f"PUMP_POWER_MAX_dBm = {PUMP_POWER_MAX_dBm:+.2f} dBm. Refusing."
            )

    freq_Hz = PUMP_FREQ_GHz * 1e9

    # --- Show plan and require explicit confirmation ------------------------
    print("=" * 72)
    if disable:
        print("TWPA PUMP — DISABLE")
        print(f"  SynthHD port    : {PUMP_SYNTH_PORT}    channels = {list(PUMP_CHANNELS)}")
        print(f"  action          : RF output OFF on all listed pump channels")
    else:
        print("TWPA PUMP — SET OPERATING POINT")
        print(f"  SynthHD port    : {PUMP_SYNTH_PORT}    channels = {list(PUMP_CHANNELS)}")
        print(f"  pump frequency  : {PUMP_FREQ_GHz:.6f} GHz")
        print(f"  pump power      : {PUMP_POWER_dBm:+.2f} dBm")
        print(f"  power ceiling   : {PUMP_POWER_MAX_dBm:+.2f} dBm")
        print(f"  scheme          : channels {list(PUMP_CHANNELS)} driven identically")
        print()
        print("BEFORE PROCEEDING, CONFIRM:")
        print("  [ ] DC bias is already at its operating point (twpa_set_bias.py).")
        print("  [ ] The SynthHD is wired to the pump line(s), nothing else is driving them.")
        print("  [ ] PUMP_FREQ_GHz and PUMP_POWER_dBm match the chosen operating point.")
    print("=" * 72)

    ans = input("Type 'yes' to proceed: ").strip().lower()
    if ans not in ("y", "yes"):
        print("[twpa_set_pump] Aborted by user.")
        sys.exit(0)

    # --- Connect and program ------------------------------------------------
    # SynthHD.__init__ disables RF on both channels and locks to the external
    # 10 MHz reference on connect.
    synth = SynthHD(PUMP_SYNTH_PORT)
    pump_channels = [synth[i] for i in PUMP_CHANNELS]

    if disable:
        try:
            disable_pump_channels(pump_channels)
        finally:
            synth.close()
        print("[twpa_set_pump] Done. Pump RF disabled on all listed channels.")
        return

    set_pump_channels(pump_channels, freq_Hz, PUMP_POWER_dBm, rf_enable=True)

    # Read back and report what each channel actually reports.
    # NOTE: we deliberately do NOT call synth.close() here — close() disables RF
    # on both channels, and the whole point of this script is to leave the pump
    # parked ON. The serial port is released when the process exits without
    # sending a disable command, so the SynthHD retains its RF-on state.
    print("[twpa_set_pump] Pump enabled. Readback:")
    for idx, ch in zip(PUMP_CHANNELS, pump_channels):
        try:
            print(f"  ch{idx}: f={ch.frequency/1e9:.6f} GHz  "
                  f"P={ch.power:+.2f} dBm  RF={'ON' if ch.rf_enable else 'OFF'}")
        except Exception as e:
            print(f"  ch{idx}: readback failed: {e}")

    print(f"[twpa_set_pump] Done. Pump parked at "
          f"{PUMP_FREQ_GHz:.6f} GHz, {PUMP_POWER_dBm:+.2f} dBm.")


if __name__ == "__main__":
    main()
