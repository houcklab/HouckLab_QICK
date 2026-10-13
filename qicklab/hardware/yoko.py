import time

import numpy as np


def ramp_to(yoko, target, step=0.001, delay=0.01):
    if target > 10:  # charge-line limit, positive side only: docs/hardware.md#charge-bias-yoko
        raise ValueError("Voltage too high")
    current = float(yoko.query(":SOUR:LEV?"))
    values = np.arange(current, target, step if target > current else -step)
    for v in values:
        yoko.write(f":SOUR:LEV {v}")
        time.sleep(delay)
    yoko.write(f":SOUR:LEV {target}")  # land exactly on target


# TWPA bias (current mode): docs/hardware.md#bias-gs200-at-gpib1112instr-current-mode
STEP_PERIOD_S = 0.05  # ramp_current GPIB update interval; smaller = smoother, more bus traffic


def pick_current_range(required_A):
    """Return the smallest YOKOGS200 current-source range that fits |required_A|."""
    for r in (1e-3, 10e-3, 100e-3, 200e-3):
        if abs(required_A) <= r:
            return r
    raise ValueError(f"|I|={abs(required_A) * 1e3:.3f} mA exceeds the YOKO's 200 mA max range.")


def ramp_current(yoko, target_A, max_rate_A_per_s, dt=STEP_PERIOD_S):
    """Linearly ramp the YOKO current setpoint to target_A at <= max_rate_A_per_s.

    Assumes current-source mode (:SOUR:FUNC CURR), so :SOUR:LEV is in amperes."""
    start_I = float(yoko.query(":SOUR:LEV?"))
    delta_I = target_A - start_I

    if abs(delta_I) < 1e-12:
        print(f"[twpa_set_bias] Already at {start_I * 1e6:+.3f} uA, nothing to do.")
        return

    step_I = max_rate_A_per_s * dt
    n_steps = max(2, int(np.ceil(abs(delta_I) / step_I)))
    Is = np.linspace(start_I, target_A, n_steps + 1, endpoint=True)

    eff_rate_nA_per_s = abs(delta_I) / (n_steps * dt) * 1e9
    eta_s = n_steps * dt

    print(
        f"[twpa_set_bias] Ramp {start_I * 1e6:+.3f} uA → {target_A * 1e6:+.3f} uA "
        f"(ΔI={delta_I * 1e6:+.3f} uA)"
    )
    print(
        f"               {n_steps} steps × {dt * 1e3:.0f} ms ≈ {eta_s:.1f} s, "
        f"rate ≈ {eff_rate_nA_per_s:.1f} nA/s (cap {max_rate_A_per_s * 1e9:.0f} nA/s)"
    )

    progress_every = max(1, n_steps // 10)
    t0 = time.time()
    for i, I in enumerate(Is):
        yoko.write(f":SOUR:LEV {I:.10f}")
        time.sleep(dt)
        if (i % progress_every) == 0:
            elapsed = time.time() - t0
            print(f"  step {i:>5d}/{n_steps}  I={I * 1e6:+.3f} uA  t={elapsed:5.1f}s")

    final_I = float(yoko.query(":SOUR:LEV?"))
    print(f"[twpa_set_bias] Done. Final I={final_I * 1e6:+.3f} uA.")
