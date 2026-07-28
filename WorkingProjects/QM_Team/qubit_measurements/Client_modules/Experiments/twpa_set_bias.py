"""
twpa_set_bias.py — Slow current sweep on a dedicated YOKO to set TWPA bias current.

Physics constraints (from the TWPA datasheet):
  * With the pump DISABLED, sweep the bias current slowly from 0 up to the
    target operating point.
  * Max sweep rate: 300 nA/s — exceeding this risks flux trapping.
  * Nominal operating point: ~11 uA (≈ 15 uT internal field, impedance matched).
  * End of the first flux period: ~25 uA (use only for one-off flux calibration).
  * Do NOT sweep significantly above ~11 uA in normal operation: it may reduce
    performance or trap flux. High bias currents are for calibration only.

This script is intentionally measurement-free: it only ramps the YOKO that drives
the TWPA bias line. Use a separate transmission run (e.g. CavitySpecFF) to map
S21 vs bias.

Wiring assumption:
  YOKO in CURRENT-SOURCE mode → TWPA bias port (direct).
  The bias current is set in hardware by the YOKO; there is no series resistor
  in the math. (The previous voltage-mode + series-resistor scheme was dropped
  because the attached resistance value was unreliable.)
  If your setup instead drives the TWPA through a known series resistor in
  voltage mode, you would need to reintroduce a V↔I conversion; this script
  assumes the YOKO sources current directly.

Usage:
  1. Verify the TWPA pump generator (Holzworth HS9004A) output is OFF.
  2. Set TWPA_YOKO_ADDRESS, TARGET_CURRENT_uA below.
  3. Run.
"""

import sys
import time
import numpy as np
import pyvisa


# ---------------------------------------------------------------------------
# User-set parameters — fill in for the current setup
# ---------------------------------------------------------------------------
TWPA_YOKO_ADDRESS   = "GPIB1::12::INSTR"   # TODO: dedicated TWPA YOKO address
#                                          # (NOT the charge-line yoko, which is now on USB:
#                                          #  USB0::0x0B21::0x0039::91T621492::0::INSTR)

TARGET_CURRENT_uA   = 0 # 22             # optimum from 20260521_144734 flux sweep (max |S21|, broad 3.5–5.5 uA plateau); datasheet nominal ≈ 11 uA
MAX_RATE_nA_per_s   = 300.0                # datasheet ceiling — do not raise

SAFETY_CAP_uA       = 25.0                 # script refuses targets above this in normal operation
ALLOW_CALIBRATION   = False                # set True for a one-off sweep up to 25 uA (full first flux period)

STEP_PERIOD_S       = 0.05                 # GPIB update interval; smaller = smoother, more bus traffic

# YOKO current-source range — discrete steps {1e-3, 10e-3, 100e-3, 200e-3} A.
# The YOKO clips at the active range; setpoints above it are silently capped.
# Auto-picked below from |target_A| if left as None.
YOKO_CURR_RANGE_A   = None                 # e.g. 1e-3 forces the 1 mA range; None = auto-pick


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def pick_current_range(required_A):
    """Return the smallest YOKOGS200 current-source range that fits |required_A|."""
    for r in (1e-3, 10e-3, 100e-3, 200e-3):
        if abs(required_A) <= r:
            return r
    raise ValueError(f"|I|={abs(required_A)*1e3:.3f} mA exceeds the YOKO's 200 mA max range.")


def slow_ramp_to_current(yoko, target_A, max_rate_A_per_s, dt=STEP_PERIOD_S):
    """Linearly ramp the YOKO current setpoint from its present value to target_A,
    bounded above by max_rate_A_per_s on the bias-current axis.

    Assumes the YOKO is already in current-source mode (:SOUR:FUNC CURR), so
    :SOUR:LEV is read and written directly in amperes."""
    start_I = float(yoko.query(":SOUR:LEV?"))
    delta_I = target_A - start_I

    if abs(delta_I) < 1e-12:
        print(f"[twpa_set_bias] Already at {start_I*1e6:+.3f} uA, nothing to do.")
        return

    step_I = max_rate_A_per_s * dt
    n_steps = max(2, int(np.ceil(abs(delta_I) / step_I)))
    Is = np.linspace(start_I, target_A, n_steps + 1, endpoint=True)

    eff_rate_nA_per_s = abs(delta_I) / (n_steps * dt) * 1e9
    eta_s = n_steps * dt

    print(f"[twpa_set_bias] Ramp {start_I*1e6:+.3f} uA → {target_A*1e6:+.3f} uA "
          f"(ΔI={delta_I*1e6:+.3f} uA)")
    print(f"               {n_steps} steps × {dt*1e3:.0f} ms ≈ {eta_s:.1f} s, "
          f"rate ≈ {eff_rate_nA_per_s:.1f} nA/s (cap {max_rate_A_per_s*1e9:.0f} nA/s)")

    progress_every = max(1, n_steps // 10)
    t0 = time.time()
    for i, I in enumerate(Is):
        yoko.write(f":SOUR:LEV {I:.10f}")
        time.sleep(dt)
        if (i % progress_every) == 0:
            elapsed = time.time() - t0
            print(f"  step {i:>5d}/{n_steps}  I={I*1e6:+.3f} uA  t={elapsed:5.1f}s")

    final_I = float(yoko.query(":SOUR:LEV?"))
    print(f"[twpa_set_bias] Done. Final I={final_I*1e6:+.3f} uA.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    # --- Safety checks on the requested target ------------------------------
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
            f"YOKO_CURR_RANGE_A = {range_A} A is too small for target I = {target_A*1e6:+.3f} uA. "
            "Pick a larger range or leave YOKO_CURR_RANGE_A = None for auto."
        )

    # --- Show plan and require explicit confirmation ------------------------
    print("=" * 72)
    print("TWPA BIAS RAMP  (YOKO current-source mode)")
    print(f"  YOKO            : {TWPA_YOKO_ADDRESS}")
    print(f"  target current  : {TARGET_CURRENT_uA:+.3f} uA")
    print(f"  YOKO I range    : {range_A*1e3:g} mA "
          f"({'auto' if YOKO_CURR_RANGE_A is None else 'forced'})")
    print(f"  max rate        : {MAX_RATE_nA_per_s:.0f} nA/s")
    print(f"  safety cap      : {SAFETY_CAP_uA:.1f} uA "
          f"({'CALIBRATION OVERRIDE — cap lifted to 25 uA' if ALLOW_CALIBRATION else 'enforced'})")
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

    # --- Connect and ramp ---------------------------------------------------
    rm = pyvisa.ResourceManager()
    yoko = rm.open_resource(TWPA_YOKO_ADDRESS)
    try:
        yoko.write(":SOUR:FUNC CURR")
        yoko.write(f":SOUR:RANG {range_A:g}")
        yoko.write(":OUTP ON")

        max_rate_A_per_s = MAX_RATE_nA_per_s * 1e-9

        slow_ramp_to_current(yoko, target_A, max_rate_A_per_s)
    finally:
        yoko.close()


if __name__ == "__main__":
    main()
