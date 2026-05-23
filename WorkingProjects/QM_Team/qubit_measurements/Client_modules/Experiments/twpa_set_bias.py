"""
twpa_set_bias.py — Slow voltage sweep on a dedicated YOKO to set TWPA bias current.

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
  YOKO in VOLTAGE mode → series resistor R_SERIES_OHMS → TWPA bias port.
  Bias current I = V_yoko / R_SERIES_OHMS.
  If your setup drives the TWPA from a current-mode source directly, swap
  ":SOUR:FUNC VOLT" → ":SOUR:FUNC CURR" and treat TARGET_CURRENT_uA as the
  level directly (set R_SERIES_OHMS = 1.0 for the math to still work).

Usage:
  1. Verify the TWPA pump generator output is OFF.
  2. Set TWPA_YOKO_ADDRESS, R_SERIES_OHMS, TARGET_CURRENT_uA below.
  3. Run.
"""

import sys
import time
import numpy as np
import pyvisa


# ---------------------------------------------------------------------------
# User-set parameters — fill in for the current setup
# ---------------------------------------------------------------------------
TWPA_YOKO_ADDRESS   = "GPIB1::9::INSTR"   # TODO: dedicated TWPA YOKO address (NOT the charge-line yoko at ::9::)
R_SERIES_OHMS       = 10.0e3                # TODO: series resistor V→I, in ohms

TARGET_CURRENT_uA   = 0.0             # optimum from 20260521_144734 flux sweep (max |S21|, broad 3.5–5.5 uA plateau); datasheet nominal ≈ 11 uA
MAX_RATE_nA_per_s   = 300.0                # datasheet ceiling — do not raise

SAFETY_CAP_uA       = 12.0                 # script refuses targets above this in normal operation
ALLOW_CALIBRATION   = False                # set True for a one-off sweep up to 25 uA (full first flux period)

STEP_PERIOD_S       = 0.05                 # GPIB update interval; smaller = smoother, more bus traffic

# YOKO voltage range — discrete steps {10e-3, 100e-3, 1, 10, 30}. The YOKO clips
# at the active range; outputs above it are silently capped (e.g. 10 mV range
# refuses to exceed ~12 mV). Auto-picked below from |target_V| if left as None.
YOKO_VOLT_RANGE_V   = None                 # e.g. 1.0 forces the 1 V range; None = auto-pick


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def pick_voltage_range(required_V):
    """Return the smallest YOKOGS200 voltage range that fits |required_V|."""
    for r in (10e-3, 100e-3, 1.0, 10.0, 30.0):
        if abs(required_V) <= r:
            return r
    raise ValueError(f"|V|={abs(required_V):.3f} V exceeds the YOKO's 30 V max range.")



def amp_to_volt(I_amps):
    return I_amps * R_SERIES_OHMS


def volt_to_amp(V):
    return V / R_SERIES_OHMS


def slow_ramp_to_current(yoko, target_A, max_rate_A_per_s, dt=STEP_PERIOD_S):
    """Linearly ramp the YOKO voltage from its present value to amp_to_volt(target_A),
    bounded above by max_rate_A_per_s on the bias-current axis."""
    start_V = float(yoko.query(":SOUR:LEV?"))
    target_V = amp_to_volt(target_A)
    start_I = volt_to_amp(start_V)
    delta_I = target_A - start_I

    if abs(delta_I) < 1e-12:
        print(f"[twpa_set_bias] Already at {start_I*1e6:+.3f} uA, nothing to do.")
        return

    step_I = max_rate_A_per_s * dt
    n_steps = max(2, int(np.ceil(abs(delta_I) / step_I)))
    Vs = np.linspace(start_V, target_V, n_steps + 1, endpoint=True)

    eff_rate_nA_per_s = abs(delta_I) / (n_steps * dt) * 1e9
    eta_s = n_steps * dt

    print(f"[twpa_set_bias] Ramp {start_I*1e6:+.3f} uA → {target_A*1e6:+.3f} uA "
          f"(ΔI={delta_I*1e6:+.3f} uA)")
    print(f"               {n_steps} steps × {dt*1e3:.0f} ms ≈ {eta_s:.1f} s, "
          f"rate ≈ {eff_rate_nA_per_s:.1f} nA/s (cap {max_rate_A_per_s*1e9:.0f} nA/s)")

    progress_every = max(1, n_steps // 10)
    t0 = time.time()
    for i, V in enumerate(Vs):
        yoko.write(f":SOUR:LEV {V:.8f}")
        time.sleep(dt)
        if (i % progress_every) == 0:
            elapsed = time.time() - t0
            print(f"  step {i:>5d}/{n_steps}  V={V:.6f}  I={volt_to_amp(V)*1e6:+.3f} uA  t={elapsed:5.1f}s")

    final_V = float(yoko.query(":SOUR:LEV?"))
    print(f"[twpa_set_bias] Done. Final V={final_V:.6f} V ({volt_to_amp(final_V)*1e6:+.3f} uA).")


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

    target_V = amp_to_volt(TARGET_CURRENT_uA * 1e-6)
    range_V = YOKO_VOLT_RANGE_V if YOKO_VOLT_RANGE_V is not None else pick_voltage_range(target_V)
    if abs(target_V) > range_V:
        raise ValueError(
            f"YOKO_VOLT_RANGE_V = {range_V} V is too small for target V = {target_V:+.4f} V. "
            "Pick a larger range or leave YOKO_VOLT_RANGE_V = None for auto."
        )

    # --- Show plan and require explicit confirmation ------------------------
    print("=" * 72)
    print("TWPA BIAS RAMP")
    print(f"  YOKO            : {TWPA_YOKO_ADDRESS}")
    print(f"  R_series        : {R_SERIES_OHMS:.4g} Ω")
    print(f"  target current  : {TARGET_CURRENT_uA:+.3f} uA "
          f"(→ {target_V:+.6f} V)")
    print(f"  YOKO V range    : {range_V:g} V "
          f"({'auto' if YOKO_VOLT_RANGE_V is None else 'forced'})")
    print(f"  max rate        : {MAX_RATE_nA_per_s:.0f} nA/s")
    print(f"  safety cap      : {SAFETY_CAP_uA:.1f} uA "
          f"({'CALIBRATION OVERRIDE — cap lifted to 25 uA' if ALLOW_CALIBRATION else 'enforced'})")
    print()
    print("BEFORE PROCEEDING, CONFIRM:")
    print("  [ ] TWPA pump generator RF output is OFF.")
    print("  [ ] No other process is writing to this YOKO.")
    print("  [ ] R_SERIES_OHMS and TWPA_YOKO_ADDRESS match the physical wiring.")
    print("=" * 72)

    ans = input("Type 'yes' to proceed: ").strip().lower()
    if ans not in ("y", "yes"):
        print("[twpa_set_bias] Aborted by user.")
        sys.exit(0)

    # --- Connect and ramp ---------------------------------------------------
    rm = pyvisa.ResourceManager()
    yoko = rm.open_resource(TWPA_YOKO_ADDRESS)
    try:
        yoko.write(":SOUR:FUNC VOLT")
        yoko.write(f":SOUR:RANG {range_V:g}")
        yoko.write(":OUTP ON")

        target_A = TARGET_CURRENT_uA * 1e-6
        max_rate_A_per_s = MAX_RATE_nA_per_s * 1e-9

        slow_ramp_to_current(yoko, target_A, max_rate_A_per_s)
    finally:
        yoko.close()


if __name__ == "__main__":
    main()
