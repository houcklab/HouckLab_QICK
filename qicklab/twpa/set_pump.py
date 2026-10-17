"""Park the TWPA pump (Windfreak SynthHD) at one (freq, power) per channel and leave RF ON.

``--off`` (or DISABLE_PUMP) RF-disables it instead; ``--on`` parks it ON even with DISABLE_PUMP.
Appends the pump state and a read-only TWPA bias readback to the TWPA state log.
Usage and notes: docs/experiments/twpa.md.
"""

import sys

from qicklab.hardware.synthhd import SynthHD
from qicklab.twpa.common import append_state, pump_state, query_bias

PUMP_SYNTH_PORT = "COM5"  # SynthHD USB/serial COM port

# One (freq_GHz, power_dBm) per SynthHD channel.
PUMP_SETTINGS = {
    1: (10.7165, -5.5),
}
PUMP_POWER_MAX_dBm = 0.0  # hard ceiling — script refuses power above this

DISABLE_PUMP = True  # True (or pass '--off') to RF-disable the pump and exit; '--on' overrides it


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
    args = sys.argv[1:]
    if "--on" in args and "--off" in args:
        raise ValueError("Pass either --on or --off, not both.")
    disable = ("--off" in args) or (DISABLE_PUMP and "--on" not in args)

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

    action = "pump_off" if disable else "pump_on"
    connected = False  # SynthHD open; its connect switched RF off on both channels
    parked = False  # every listed channel programmed and RF-enabled
    try:
        # Connecting disables RF on BOTH channels: docs/hardware.md#pump-windfreak-synthhd-on-com5
        synth = SynthHD(PUMP_SYNTH_PORT)
        connected = True

        if disable:
            try:
                disable_pump_channels(synth, channels)
            finally:
                synth.close()
            print("[twpa_set_pump] Done. Pump RF disabled on all listed channels.")
        else:
            set_pump_channels(synth, PUMP_SETTINGS, rf_enable=True)
            parked = True

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

            at = ", ".join(
                f"ch{idx} @ {f:.6f} GHz, {p:+.2f} dBm" for idx, (f, p) in PUMP_SETTINGS.items()
            )
            print(f"[twpa_set_pump] Done. Pump parked at {at}.")
    except BaseException as e:
        # Log even on Ctrl-C / an error so the last line never claims a stale pump state.
        # RF: ON once parked; OFF on the off path once connected (connect disabled it);
        # otherwise unknown (failed connect, or a partially programmed channel).
        rf = True if parked else (False if (disable and connected) else None)
        outcome = "interrupted" if isinstance(e, KeyboardInterrupt) else "error"
        log_state(action, logged_pump(disable, channels, rf), outcome)
        raise

    log_state(action, logged_pump(disable, channels, not disable), "completed")


def logged_pump(disable, channels, rf_enable):
    """Pump state for the log: the commanded (freq, power) per channel on the ON path."""
    if disable:
        return pump_state(channels, None, None, rf_enable)
    return [pump_state([idx], f * 1e9, p, rf_enable)[0] for idx, (f, p) in PUMP_SETTINGS.items()]


def log_state(action, pump, outcome):
    """Append the pump state and a read-only TWPA bias readback to the TWPA state log."""
    append_state(
        "twpa_set_pump",
        action=action,
        outcome=outcome,
        bias=query_bias(tag="twpa_set_pump"),
        pump=pump,
        pnax=None,
    )


if __name__ == "__main__":
    main()
