"""Helpers shared by the qicklab.twpa scripts (docs/experiments/twpa.md)."""

import datetime as _dt
import json
import math
import os
import time

from qicklab.hardware.yoko import TWPA_YOKO_ADDRESS, _func, _is_on

# One TWPA state log for every script: <TWPA_STATE_DIR>/twpa_state.jsonl, one JSON object per line
# (bias readback, pump state, PNA-X settings). The SynthHD cannot be queried without switching the
# pump off, so this log is the only record of the pump state. docs/experiments/twpa.md#state-log
TWPA_STATE_DIR = r"V:/t1Team/Data/2026-10-01_BFC_cooldown/TWPA_calibration"
TWPA_STATE_FILE = "twpa_state.jsonl"


def timestamped_paths(save_dir, run_tag):
    """Create save_dir; return ``<save_dir>/<%Y%m%d_%H%M%S>_<run_tag>`` + ``.npz`` / ``.png``."""
    os.makedirs(save_dir, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    base = os.path.join(save_dir, f"{stamp}_{run_tag}")
    return base + ".npz", base + ".png"


def read_bias_state(yoko):
    """Read-only TWPA bias readback: queries ``:OUTP?``, ``:SOUR:FUNC?``, ``:SOUR:LEV?``, writes nothing.

    Returns {bias_uA, yoko_output_on, yoko_func, yoko_level}. ``:SOUR:LEV?`` returns the setpoint
    even with the output off, and volts in voltage mode, so bias_uA is the level in uA only when the
    function is CURR and the output is on; otherwise NaN (yoko_level keeps the raw setpoint)."""
    on = _is_on(yoko.query(":OUTP?"))
    func = _func(yoko.query(":SOUR:FUNC?"))
    level = float(yoko.query(":SOUR:LEV?"))
    bias_uA = level * 1e6 if (on and func == "CURR") else math.nan
    return {"bias_uA": bias_uA, "yoko_output_on": on, "yoko_func": func, "yoko_level": level}


def query_bias(rm=None, address=TWPA_YOKO_ADDRESS, tag="twpa"):
    """Open the TWPA bias YOKO, read its state with read_bias_state (read-only), close it.

    rm: a pyvisa ResourceManager (None: make one). Never raises: a failed open or query prints a
    warning and returns NaN / None fields, so a provenance readback cannot stop a measurement."""
    try:
        if rm is None:
            import pyvisa

            rm = pyvisa.ResourceManager()
        yoko = rm.open_resource(address)
    except Exception as e:
        print(f"[{tag}] WARNING: could not open the TWPA bias YOKO {address} for readback: {e}")
        return {"bias_uA": math.nan, "yoko_output_on": None, "yoko_func": None, "yoko_level": None}
    try:
        return read_bias_state(yoko)
    except Exception as e:
        print(f"[{tag}] WARNING: TWPA bias readback from {address} failed: {e}")
        return {"bias_uA": math.nan, "yoko_output_on": None, "yoko_func": None, "yoko_level": None}
    finally:
        try:
            yoko.close()
        except Exception:
            pass


def bias_npz_fields(bias):
    """query_bias / read_bias_state result as npz-safe fields (no None, so no pickled arrays).

    bias_uA and yoko_level are NaN when unknown, yoko_output_on is 1 / 0 / -1 (unknown) and
    yoko_func is "CURR" / "VOLT" / "unknown"."""
    on = bias.get("yoko_output_on")
    level = bias.get("yoko_level")
    return {
        "bias_uA": float(bias.get("bias_uA", math.nan)),
        "yoko_output_on": -1 if on is None else int(bool(on)),
        "yoko_func": bias.get("yoko_func") or "unknown",
        "yoko_level": math.nan if level is None else float(level),
    }


def _jsonable(x):
    """NaN / inf -> None and numpy scalars / arrays -> Python, recursively (strict JSON)."""
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    if hasattr(x, "tolist"):  # numpy scalar or array
        return _jsonable(x.tolist())
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return x


def append_state(script, state_dir=None, **fields):
    """Append one JSON line {time, unix_time, script, **fields} to <state_dir>/twpa_state.jsonl.

    state_dir defaults to TWPA_STATE_DIR (read at call time). Never raises: a failed write
    (e.g. the network drive is down) prints a warning. Returns the line's dict, or None."""
    state_dir = TWPA_STATE_DIR if state_dir is None else state_dir
    path = os.path.join(state_dir, TWPA_STATE_FILE)
    now = time.time()
    entry = {
        "time": _dt.datetime.fromtimestamp(now).isoformat(timespec="seconds"),
        "unix_time": now,
        "script": script,
        **fields,
    }
    try:
        line = json.dumps(_jsonable(entry), allow_nan=False)
        os.makedirs(state_dir, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except (OSError, TypeError, ValueError) as e:
        print(f"[{script}] WARNING: could not append to the TWPA state log {path}: {e}")
        return None
    print(f"[{script}] TWPA state logged to {path}")
    return entry


def pump_state(channels, freq_hz, power_dbm, rf_enable):
    """Commanded pump state for the log: one {channel, freq_hz, power_dbm, rf_enable} per channel.

    rf_enable None (null in the log) means unknown: the script failed or was interrupted while
    connecting to or programming the SynthHD."""
    return [
        {
            "channel": int(c),
            "freq_hz": None if freq_hz is None else float(freq_hz),
            "power_dbm": None if power_dbm is None else float(power_dbm),
            "rf_enable": None if rf_enable is None else bool(rf_enable),
        }
        for c in channels
    ]
