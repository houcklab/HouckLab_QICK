"""
twpa_set_pump.py — Park the TWPA pump at a single (frequency, power) operating point.

This is the pump-side companion to twpa_set_bias.py. Where twpa_set_bias.py ramps
the DC bias YOKO, this script sets the RF pump tone: it programs the SignalCore
SC5510A pump generator(s) to a chosen frequency and power and enables RF output.

It is intentionally measurement-free — it only drives the pump. Use a separate
sweep (twpa_pump_sweep_pnax.py) to find the right (freq, power); once you know the
operating point, use THIS script to park there before running qubit measurements.

Pump source
  One or more SignalCore SC5510A signal generators, controlled remotely over Pyro5
  via sc5510a_client.py. Every device in PUMP_DEVICE_IDS is driven IDENTICALLY:
  same frequency, same power. (For offset/independent control, add per-device
  offsets where the devices are programmed below.)

  This is a two-machine setup. The SC5510A devices are physically connected to a
  *server PC* running the Pyro name server + instrument server. This script is the
  *client*: set SC5510A_SERVER_HOST to the server PC's LAN IP and PUMP_DEVICE_IDS
  to the device ids you want to drive.

  To find the device ids: from the client, with the server running, do
      import sc5510a_client as sc
      print(sc.list_instruments())
  which prints names like 'SC5510A#10002D35' — the trailing id is the device id.

Safety
  * DC bias should already be at the operating point before pumping (twpa_set_bias.py).
    This script does NOT touch the YOKO.
  * PUMP_POWER_MAX_dBm enforces a hard ceiling on the requested power.
  * The script shows the plan and requires explicit 'yes' confirmation before
    enabling RF, mirroring twpa_set_bias.py.

Usage:
  1. Verify DC bias is parked (twpa_set_bias.py).
  2. Set SC5510A_SERVER_HOST, PUMP_DEVICE_IDS, PUMP_FREQ_GHz, PUMP_POWER_dBm below.
  3. Run. To turn the pump OFF instead, set DISABLE_PUMP = True (or run with
     '--off' on the command line).
"""

import os
import sys

# sc5510a_client lives in the shared PythonDrivers directory (one level up).
_DRIVERS_DIR = os.path.join(os.path.dirname(__file__), "..", "PythonDrivers")
if os.path.normpath(_DRIVERS_DIR) not in sys.path:
    sys.path.insert(0, os.path.normpath(_DRIVERS_DIR))
import sc5510a_client as sc


# ---------------------------------------------------------------------------
# User-set parameters
# ---------------------------------------------------------------------------
# --- Pump source (SignalCore SC5510A, driven identically over Pyro5) --------
SC5510A_SERVER_HOST = "192.168.0.102"            # server PC LAN IP running the Pyro name server
PUMP_DEVICE_IDS     = ["10002D34", "10002D35"]   # TODO: SC5510A device ids (see sc.list_instruments())

# --- Operating point --------------------------------------------------------
PUMP_FREQ_GHz       = 12.7      # TODO: pump frequency at the chosen operating point
PUMP_POWER_dBm      = -15.0     # TODO: pump power at the chosen operating point
PUMP_POWER_MAX_dBm  = 0.0       # hard ceiling — script refuses power above this

DISABLE_PUMP        = True     # True (or pass '--off') to RF-disable the pumps and exit


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
            print(f"[twpa_set_pump] WARNING: failed to disable a device: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    disable = DISABLE_PUMP or ("--off" in sys.argv[1:])

    # --- Validate -----------------------------------------------------------
    if any("TODO" in str(d) for d in PUMP_DEVICE_IDS):
        raise ValueError(
            "PUMP_DEVICE_IDS still contains placeholders — fill in the SC5510A "
            "device ids (run sc5510a_client.list_instruments() to discover them)."
        )
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
        print(f"  SC5510A server  : {SC5510A_SERVER_HOST}    devices = {PUMP_DEVICE_IDS}")
        print(f"  action          : RF output OFF on all listed pump devices")
    else:
        print("TWPA PUMP — SET OPERATING POINT")
        print(f"  SC5510A server  : {SC5510A_SERVER_HOST}    devices = {PUMP_DEVICE_IDS}")
        print(f"  pump frequency  : {PUMP_FREQ_GHz:.6f} GHz")
        print(f"  pump power      : {PUMP_POWER_dBm:+.2f} dBm")
        print(f"  power ceiling   : {PUMP_POWER_MAX_dBm:+.2f} dBm")
        print(f"  scheme          : {PUMP_DEVICE_IDS} driven identically")
        print()
        print("BEFORE PROCEEDING, CONFIRM:")
        print("  [ ] DC bias is already at its operating point (twpa_set_bias.py).")
        print("  [ ] The SC5510A are wired to the pump line(s), nothing else is driving them.")
        print("  [ ] PUMP_FREQ_GHz and PUMP_POWER_dBm match the chosen operating point.")
    print("=" * 72)

    ans = input("Type 'yes' to proceed: ").strip().lower()
    if ans not in ("y", "yes"):
        print("[twpa_set_pump] Aborted by user.")
        sys.exit(0)

    # --- Connect and program ------------------------------------------------
    pump_devices = [sc.connect(dev_id, host=SC5510A_SERVER_HOST) for dev_id in PUMP_DEVICE_IDS]

    if disable:
        disable_pump_devices(pump_devices)
        print("[twpa_set_pump] Done. Pump RF disabled on all listed devices.")
        return

    # The server-side driver locks each SC5510A to its external reference at init;
    # warn (don't abort) if a device reports its ext ref undetected.
    for dev_id, dev in zip(PUMP_DEVICE_IDS, pump_devices):
        if not dev.clocked:
            print(f"[twpa_set_pump] WARNING: SC5510A {dev_id} reports external "
                  f"reference NOT detected — check the 10 MHz ref cabling.")

    set_pump_devices(pump_devices, freq_Hz, PUMP_POWER_dBm, rf_enable=True)

    # Read back and report what each device actually reports.
    print("[twpa_set_pump] Pump enabled. Readback:")
    for dev_id, dev in zip(PUMP_DEVICE_IDS, pump_devices):
        try:
            print(f"  {dev_id}: f={dev.frequency/1e9:.6f} GHz  "
                  f"P={dev.power:+.2f} dBm  RF={'ON' if dev.output else 'OFF'}")
        except Exception as e:
            print(f"  {dev_id}: readback failed: {e}")

    print(f"[twpa_set_pump] Done. Pump parked at "
          f"{PUMP_FREQ_GHz:.6f} GHz, {PUMP_POWER_dBm:+.2f} dBm.")


if __name__ == "__main__":
    main()
