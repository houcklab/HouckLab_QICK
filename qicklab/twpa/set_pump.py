"""Park the TWPA pump (Windfreak SynthHD) at one (freq, power) per channel and leave RF ON.

``--off`` (or DISABLE_PUMP) RF-disables it instead. Usage and notes: docs/experiments/twpa.md.
"""

import sys

from qicklab.hardware.synthhd import SynthHD

PUMP_SYNTH_PORT = "COM5"  # SynthHD USB/serial COM port

# One (freq_GHz, power_dBm) per SynthHD channel.
PUMP_SETTINGS = {
    1: (10.7165, -5.5),
}
PUMP_POWER_MAX_dBm = 0.0  # hard ceiling — script refuses power above this

DISABLE_PUMP = True  # True (or pass '--off') to RF-disable the pump and exit


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


def main():
    disable = DISABLE_PUMP or ("--off" in sys.argv[1:])

    channels = list(PUMP_SETTINGS)

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

    # Connecting disables RF on BOTH channels: docs/hardware.md#pump-windfreak-synthhd-on-com5
    synth = SynthHD(PUMP_SYNTH_PORT)

    if disable:
        try:
            disable_pump_channels(synth, channels)
        finally:
            synth.close()
        print("[twpa_set_pump] Done. Pump RF disabled on all listed channels.")
        return

    set_pump_channels(synth, PUMP_SETTINGS, rf_enable=True)

    # No synth.close(): it disables RF on both channels, and the pump must stay ON.
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
