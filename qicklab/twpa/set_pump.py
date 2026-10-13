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
  port). The SynthHD has two channels; each channel listed in PUMP_SETTINGS gets
  its OWN frequency and power. Give both channels the same pair to drive them
  identically, different pairs to drive them independently, or omit a channel
  entirely to leave it untouched.

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
  2. Set PUMP_SYNTH_PORT and PUMP_SETTINGS below.
  3. Run. To turn the pump OFF instead, set DISABLE_PUMP = True (or run with
     '--off' on the command line).
"""

import sys

from pywindfreak import SynthHD

# ---------------------------------------------------------------------------
# User-set parameters
# ---------------------------------------------------------------------------
# --- Pump source (Windfreak SynthHD) ----------------------------------------
PUMP_SYNTH_PORT = "COM5"  # SynthHD USB/serial COM port

# --- Operating point: one (freq_GHz, power_dBm) per SynthHD channel ---------
# Channels not listed here are left untouched.
PUMP_SETTINGS = {
    # 0: (10.7831, -1.0),               # ch0: freq [GHz], power [dBm]
    1: (10.7165, -5.5),  # ch1: uncomment / edit for the second pump
}
PUMP_POWER_MAX_dBm = 0.0  # hard ceiling — script refuses power above this

DISABLE_PUMP = True  # True (or pass '--off') to RF-disable the pump and exit


# ---------------------------------------------------------------------------
# SynthHD pump helpers (per-channel variant of twpa_pump_sweep_pnax.py's)
# ---------------------------------------------------------------------------
def set_pump_channels(synth, settings, rf_enable):
    """Program each channel with its own (freq_GHz, power_dBm)."""
    for idx, (freq_ghz, power_dbm) in settings.items():
        ch = synth[idx]
        ch.frequency = float(freq_ghz) * 1e9
        ch.power = float(power_dbm)
        ch.rf_enable = bool(rf_enable)


def disable_pump_channels(synth, indices):
    for idx in indices:
        try:
            synth[idx].rf_enable = False
        except Exception as e:
            print(f"[twpa_set_pump] WARNING: failed to disable ch{idx}: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    disable = DISABLE_PUMP or ("--off" in sys.argv[1:])

    channels = list(PUMP_SETTINGS)

    # --- Validate -----------------------------------------------------------
    if not disable:
        if not PUMP_SETTINGS:
            raise ValueError("PUMP_SETTINGS is empty — no channel to drive.")
        for idx, (freq_ghz, power_dbm) in PUMP_SETTINGS.items():
            if freq_ghz <= 0:
                raise ValueError(f"ch{idx}: frequency must be > 0 GHz.")
            if power_dbm > PUMP_POWER_MAX_dBm:
                raise ValueError(
                    f"ch{idx}: power = {power_dbm:+.2f} dBm exceeds "
                    f"PUMP_POWER_MAX_dBm = {PUMP_POWER_MAX_dBm:+.2f} dBm. Refusing."
                )

    # --- Show plan and require explicit confirmation ------------------------
    print("=" * 72)
    if disable:
        print("TWPA PUMP — DISABLE")
        print(f"  SynthHD port    : {PUMP_SYNTH_PORT}    channels = {channels}")
        print(f"  action          : RF output OFF on all listed pump channels")
    else:
        print("TWPA PUMP — SET OPERATING POINT")
        print(f"  SynthHD port    : {PUMP_SYNTH_PORT}")
        for idx, (freq_ghz, power_dbm) in PUMP_SETTINGS.items():
            print(f"  ch{idx}             : {freq_ghz:.6f} GHz   {power_dbm:+.2f} dBm")
        print(f"  power ceiling   : {PUMP_POWER_MAX_dBm:+.2f} dBm")
        print()
        print("BEFORE PROCEEDING, CONFIRM:")
        print("  [ ] DC bias is already at its operating point (twpa_set_bias.py).")
        print("  [ ] The SynthHD is wired to the pump line(s), nothing else is driving them.")
        print("  [ ] Each channel's (freq, power) matches its chosen operating point.")
    print("=" * 72)

    ans = input("Type 'yes' to proceed: ").strip().lower()
    if ans not in ("y", "yes"):
        print("[twpa_set_pump] Aborted by user.")
        sys.exit(0)

    # --- Connect and program ------------------------------------------------
    # SynthHD.__init__ disables RF on both channels and locks to the external
    # 10 MHz reference on connect.
    synth = SynthHD(PUMP_SYNTH_PORT)

    if disable:
        try:
            disable_pump_channels(synth, channels)
        finally:
            synth.close()
        print("[twpa_set_pump] Done. Pump RF disabled on all listed channels.")
        return

    set_pump_channels(synth, PUMP_SETTINGS, rf_enable=True)

    # Read back and report what each channel actually reports.
    # NOTE: we deliberately do NOT call synth.close() here — close() disables RF
    # on both channels, and the whole point of this script is to leave the pump
    # parked ON. The serial port is released when the process exits without
    # sending a disable command, so the SynthHD retains its RF-on state.
    print("[twpa_set_pump] Pump enabled. Readback:")
    for idx in channels:
        ch = synth[idx]
        try:
            print(
                f"  ch{idx}: f={ch.frequency / 1e9:.6f} GHz  "
                f"P={ch.power:+.2f} dBm  RF={'ON' if ch.rf_enable else 'OFF'}"
            )
        except Exception as e:
            print(f"  ch{idx}: readback failed: {e}")

    parked = ", ".join(
        f"ch{idx} @ {f:.6f} GHz, {p:+.2f} dBm" for idx, (f, p) in PUMP_SETTINGS.items()
    )
    print(f"[twpa_set_pump] Done. Pump parked at {parked}.")


if __name__ == "__main__":
    main()
