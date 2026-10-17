import re
import time

import numpy as np


# The dedicated TWPA bias source; the charge-line opener refuses this address.
TWPA_YOKO_ADDRESS = "GPIB1::12::INSTR"

CHARGE_V_LIMIT = 10.0  # |V| limit on the charge line: docs/hardware.md#charge-bias-yoko
RANGE_HEADROOM = 1.2  # GS200 sources up to 1.2x the nominal range (12 V on the 10 V range)
# ramp_to readback tolerance: the 10 V range resolves 100 uV; a clipped setpoint is off by far more
LEVEL_READBACK_TOL_V = 1e-4

# Last level each ramp landed on, per source, for the provenance record of later saves
# (qicklab.core.io.provenance; docs/architecture.md#provenance). Filled from the read-back the
# ramp already takes: recording it sends nothing to the instrument.
_LAST_LEVELS = {}


def _note_level(source, yoko, unit, setpoint, readback):
    _LAST_LEVELS[source] = {
        "address": getattr(yoko, "resource_name", None),
        "unit": unit,
        "setpoint": float(setpoint),
        "readback": float(readback),
        "time": time.time(),
    }


def last_levels():
    """{source: {address, unit, setpoint, readback, time}} of the last landed ramp per source.

    source is "charge_yoko" (ramp_to, volts) or "twpa_bias" (ramp_current, amperes); `readback`
    is the :SOUR:LEV? reply after the ramp (the GS200's setpoint register, not a measurement
    of the output); `time` is a time.time() value."""
    return {k: dict(v) for k, v in _LAST_LEVELS.items()}


def _gpib_key(address):
    """(board, primary address) of a GPIB VISA resource string, else the normalised string.

    'GPIB1::12', 'gpib1::12::instr' and 'GPIB1::12::0::INSTR' all name the device at primary
    address 12 on board 1 (a missing board number is board 0); the secondary address is ignored.
    A VISA alias (e.g. one defined in NI MAX) is not resolved."""
    m = re.fullmatch(r"GPIB(\d*)::(\d+)(?:::\d+)?(?:::INSTR)?", address.strip(), re.IGNORECASE)
    if m is None:
        return address.strip().upper()
    return (int(m.group(1) or 0), int(m.group(2)))


def _is_on(reply):
    return int(float(reply)) == 1


def _func(reply):
    return reply.strip().upper()[:4]  # "VOLT" / "CURR" (also accepts "VOLTAGE" / "CURRENT")


def ramp_to(yoko, target, step=0.001, delay=0.01):
    """Ramp the voltage setpoint to `target` in `step` V every `delay` s, then verify the level.

    Rejects |target| > 10 V (both signs). Raises RuntimeError if the read-back level differs from
    `target` by more than LEVEL_READBACK_TOL_V (e.g. the setpoint was clipped by the active range)."""
    if abs(target) > CHARGE_V_LIMIT:  # docs/hardware.md#charge-bias-yoko
        raise ValueError(
            f"|target| = {abs(target)} V exceeds the {CHARGE_V_LIMIT:g} V charge-line limit"
        )
    current = float(yoko.query(":SOUR:LEV?"))
    values = np.arange(current, target, step if target > current else -step)
    for v in values:
        yoko.write(f":SOUR:LEV {v}")
        time.sleep(delay)
    yoko.write(f":SOUR:LEV {target}")  # land exactly on target
    landed = float(yoko.query(":SOUR:LEV?"))
    _note_level("charge_yoko", yoko, "V", target, landed)
    if abs(landed - target) > LEVEL_READBACK_TOL_V:
        raise RuntimeError(
            f"yoko level reads {landed} V after ramping to {target} V "
            "(setpoint clipped by the active range, or rounded by a coarse one: the 30 V range "
            "resolves only 1 mV)"
        )


def open_charge_yoko(rm, address, start_voltage):
    """Open the charge-line GS200 in voltage mode with its output on, without stepping the output.

    Refuses the TWPA source address, and a source found in current mode with its output on (it is
    biasing something else). Output OFF: selects VOLT, sets the level to 0 and turns the output on
    (ramp_to then ramps from 0). Output ON in VOLT: leaves the level alone (ramp_to ramps from it).
    Raises if |start_voltage| exceeds the active voltage range, or if that range is above 10 V
    (the 30 V range resolves 1 mV, coarser than ramp_to's read-back tolerance); never changes it.
    Order and SCPI: docs/hardware.md#charge-bias-yoko."""
    if _gpib_key(address) == _gpib_key(TWPA_YOKO_ADDRESS):
        raise ValueError(f"{address} is the TWPA bias source, not the charge-line yoko")
    yoko = rm.open_resource(address)
    try:
        on = _is_on(yoko.query(":OUTP?"))
        func = _func(yoko.query(":SOUR:FUNC?"))
        stored = yoko.query(":SOUR:LEV?").strip()
        print(
            f"[charge yoko] {address}: function {func}, output {'ON' if on else 'OFF'}, setpoint {stored}"
        )
        if func == "CURR" and on:
            raise RuntimeError(
                f"{address} is sourcing current with its output ON; refusing to switch it to "
                "voltage mode (wrong address? the TWPA bias source?)"
            )
        if not on:
            yoko.write(":SOUR:FUNC VOLT")
        v_range = float(yoko.query(":SOUR:RANG?"))
        if v_range > CHARGE_V_LIMIT:
            raise ValueError(
                f"active voltage range is {v_range:g} V: it resolves only 1 mV, so ramp_to's "
                f"{LEVEL_READBACK_TOL_V:g} V read-back would fail on sub-mV sweep points, and the "
                f"charge line never needs more than {CHARGE_V_LIMIT:g} V; set the 10 V range on the "
                "GS200 with the output off"
            )
        if abs(start_voltage) > RANGE_HEADROOM * v_range:
            raise ValueError(
                f"start voltage {start_voltage} V exceeds the active {v_range:g} V range "
                "(it would be clipped); set a larger range on the GS200 with the output off"
            )
        if not on:
            yoko.write(":SOUR:LEV 0")
            yoko.write(":OUTP ON")
    except Exception:
        yoko.close()
        raise
    return yoko


# TWPA bias (current mode): docs/hardware.md#bias-gs200-at-gpib1112instr-current-mode
STEP_PERIOD_S = 0.05  # ramp_current GPIB update interval; smaller = smoother, more bus traffic


def pick_current_range(required_A):
    """Return the smallest YOKOGS200 current-source range that fits |required_A|."""
    for r in (1e-3, 10e-3, 100e-3, 200e-3):
        if abs(required_A) <= r:
            return r
    raise ValueError(f"|I|={abs(required_A) * 1e3:.3f} mA exceeds the YOKO's 200 mA max range.")


def enable_current_output_safely(yoko, range_A):
    """Put the TWPA GS200 in current mode with its output on, without stepping the output.

    Output OFF: selects CURR and `range_A`, sets the level to 0, then turns the output on (a stale
    stored setpoint is discarded, and printed). Output ON in CURR: keeps the setpoint (it is the
    real output); sets `range_A` only at 0 A, otherwise keeps a larger active range and refuses a
    smaller one. Output ON in VOLT: raises (switching function with the output on steps it).
    Returns the active range in A. Order and SCPI: docs/hardware.md#bias-gs200-at-gpib1112instr-current-mode."""
    on = _is_on(yoko.query(":OUTP?"))
    func = _func(yoko.query(":SOUR:FUNC?"))
    stored = float(yoko.query(":SOUR:LEV?"))
    print(
        f"[twpa_set_bias] YOKO found: function {func}, output {'ON' if on else 'OFF'}, setpoint {stored:g}"
    )
    if not on:
        yoko.write(":SOUR:FUNC CURR")
        yoko.write(f":SOUR:RANG {range_A:g}")
        yoko.write(":SOUR:LEV 0")
        yoko.write(":OUTP ON")
        if stored != 0:
            print(f"[twpa_set_bias] stored setpoint {stored:g} discarded; output enabled at 0 A.")
        return range_A
    if func != "CURR":
        raise RuntimeError(
            f"YOKO output is ON in {func} mode; switching to current mode with the output on "
            "would step the output. Ramp it to 0 and switch the output off by hand first."
        )
    active = float(yoko.query(":SOUR:RANG?"))
    if np.isclose(active, range_A):
        return range_A
    if stored == 0:
        yoko.write(f":SOUR:RANG {range_A:g}")
        return range_A
    if active > range_A:
        print(
            f"[twpa_set_bias] output ON at {stored * 1e6:+.3f} uA: keeping the {active * 1e3:g} mA range."
        )
        return active
    raise RuntimeError(
        f"YOKO output is ON at {stored * 1e6:+.3f} uA on the {active * 1e3:g} mA range, smaller "
        f"than the {range_A * 1e3:g} mA needed; changing range at a nonzero level can step the "
        "output. Ramp to 0 first."
    )


def ramp_current(yoko, target_A, max_rate_A_per_s, dt=STEP_PERIOD_S):
    """Linearly ramp the YOKO current setpoint to target_A at <= max_rate_A_per_s.

    Assumes current-source mode (:SOUR:FUNC CURR), so :SOUR:LEV is in amperes."""
    start_I = float(yoko.query(":SOUR:LEV?"))
    delta_I = target_A - start_I

    if abs(delta_I) < 1e-12:
        print(f"[twpa_set_bias] Already at {start_I * 1e6:+.3f} uA, nothing to do.")
        _note_level("twpa_bias", yoko, "A", target_A, start_I)
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
    _note_level("twpa_bias", yoko, "A", target_A, final_I)
    print(f"[twpa_set_bias] Done. Final I={final_I * 1e6:+.3f} uA.")
