"""Ramp the dedicated TWPA bias YOKO (current mode) to TARGET_CURRENT_uA at <= 300 nA/s.

Measurement-free; pump OFF first. Appends the bias readback after the ramp to the TWPA state log.
Usage, limits and bias history: docs/experiments/twpa.md.
"""

import sys

import pyvisa

from qicklab.hardware import yoko as _hw_yoko
from qicklab.hardware.yoko import (
    STEP_PERIOD_S,
    enable_current_output_safely,
    pick_current_range,
    ramp_current,
)
from qicklab.twpa.common import append_state, read_bias_state

# GPIB1::12; not the charge-line yoko at ::9::. One shared constant, edit it in hardware.yoko
# (the charge-line opener refuses this address).
TWPA_YOKO_ADDRESS = _hw_yoko.TWPA_YOKO_ADDRESS

TARGET_CURRENT_uA = 0  # datasheet nominal ≈ 11 uA; history in docs/experiments/twpa.md
MAX_RATE_nA_per_s = 300.0  # datasheet ceiling — do not raise

SAFETY_CAP_uA = 25.0  # script refuses targets above this in normal operation
ALLOW_CALIBRATION = False  # set True for a one-off sweep up to 25 uA (full first flux period)


# YOKO current-source range in A, one of {1e-3, 10e-3, 100e-3, 200e-3}; setpoints above the
# active range are silently clipped. None = auto-pick from |target|.
YOKO_CURR_RANGE_A = None


def main():
    if MAX_RATE_nA_per_s > 300.0:
        raise ValueError("MAX_RATE_nA_per_s > 300 nA/s violates the TWPA datasheet ceiling.")
    if abs(TARGET_CURRENT_uA) > 25.0:
        raise ValueError(
            f"TARGET_CURRENT_uA = {TARGET_CURRENT_uA} uA is past the first flux period (~25 uA). "
            "Refusing."
        )
    if abs(TARGET_CURRENT_uA) > SAFETY_CAP_uA and not ALLOW_CALIBRATION:
        raise ValueError(
            f"TARGET_CURRENT_uA = {TARGET_CURRENT_uA} uA exceeds SAFETY_CAP_uA = {SAFETY_CAP_uA} uA. "
            "Set ALLOW_CALIBRATION = True only for a one-off flux-period calibration sweep."
        )

    target_A = TARGET_CURRENT_uA * 1e-6
    range_A = YOKO_CURR_RANGE_A if YOKO_CURR_RANGE_A is not None else pick_current_range(target_A)
    if abs(target_A) > range_A:
        raise ValueError(
            f"YOKO_CURR_RANGE_A = {range_A} A is too small for target I = {target_A * 1e6:+.3f} uA. "
            "Pick a larger range or leave YOKO_CURR_RANGE_A = None for auto."
        )

    print("=" * 72)
    print("TWPA BIAS RAMP  (YOKO current-source mode)")
    print(f"  YOKO            : {TWPA_YOKO_ADDRESS}")
    print(f"  target current  : {TARGET_CURRENT_uA:+.3f} uA")
    print(
        f"  YOKO I range    : {range_A * 1e3:g} mA "
        f"({'auto' if YOKO_CURR_RANGE_A is None else 'forced'})"
    )
    print(f"  max rate        : {MAX_RATE_nA_per_s:.0f} nA/s")
    print(
        f"  safety cap      : {SAFETY_CAP_uA:.1f} uA "
        f"({'CALIBRATION OVERRIDE — cap lifted to 25 uA' if ALLOW_CALIBRATION else 'enforced'})"
    )
    print()
    print("BEFORE PROCEEDING, CONFIRM:")
    print("  [ ] TWPA pump generator (Holzworth HS9004A) RF output is OFF.")
    print("  [ ] No other process is writing to this YOKO.")
    print("  [ ] TWPA_YOKO_ADDRESS matches the physical wiring and the YOKO is")
    print("      wired to source current directly into the TWPA bias line.")
    print("=" * 72)

    ans = input("Type 'yes' to proceed: ").strip().lower()
    if ans not in ("y", "yes"):
        print("[twpa_set_bias] Aborted by user.")
        sys.exit(0)

    rm = pyvisa.ResourceManager()
    yoko = rm.open_resource(TWPA_YOKO_ADDRESS)
    outcome = "error"
    try:
        enable_current_output_safely(yoko, range_A)

        max_rate_A_per_s = MAX_RATE_nA_per_s * 1e-9

        ramp_current(yoko, target_A, max_rate_A_per_s, dt=STEP_PERIOD_S)
        outcome = "completed"
    except KeyboardInterrupt:
        outcome = "interrupted"
        raise
    finally:
        try:
            bias = read_bias_state(yoko)  # read-only
        except Exception as e:
            print(f"[twpa_set_bias] WARNING: TWPA bias readback failed: {e}")
            bias = None
        append_state(
            "twpa_set_bias",
            action="set_bias",
            outcome=outcome,
            target_uA=TARGET_CURRENT_uA,
            bias=bias,
            pump=None,  # not touched by this script (pump must be OFF)
            pnax=None,
        )
        yoko.close()


if __name__ == "__main__":
    main()
