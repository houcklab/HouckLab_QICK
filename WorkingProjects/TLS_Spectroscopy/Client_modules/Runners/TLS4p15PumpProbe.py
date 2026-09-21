"""q3 direct TLS-saturation pump--probe after a local five-point locator.

This runner deliberately leaves the long apples-to-apples scan untouched.
It runs the existing checkpointed TLS-saturation experiment at an explicitly
specified local TLS center, with matched detuned controls on either side.
"""

import os

from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import outerFolder
from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSSaturationRecovery as saturation


def _float(name, default, environ):
    raw = environ.get(name)
    return float(default if raw is None or str(raw).strip() == "" else raw)


def _integer_list(name, default, environ):
    raw = environ.get(name)
    if raw is None or str(raw).strip() == "":
        return list(default)
    values = [int(round(float(item))) for item in str(raw).replace(",", " ").split()]
    if not values or any(value <= 0 for value in values):
        raise ValueError(f"{name} must contain positive pump gains")
    return values


def _bool(name, default, environ):
    raw = environ.get(name)
    if raw is None or str(raw).strip() == "":
        return bool(default)
    value = str(raw).strip().lower()
    if value not in {"on", "off", "true", "false", "1", "0", "yes", "no"}:
        raise ValueError(f"{name} must be on or off")
    return value in {"on", "true", "1", "yes"}


def settings(environ=None):
    """Return a q3-local pump-probe plan without mutating global defaults."""
    environ = os.environ if environ is None else environ
    p = dict(saturation.P)
    p.update({
        # q3's calibrated TLS branch and current park coordinate are negative
        # DAC values; the generic historical defaults are not valid here.
        "tls_nominal_freq_ghz": _float("Q3_TLS_PUMP_CENTER_GHZ", 4.150, environ),
        "control_detuning_mhz": _float("Q3_TLS_PUMP_CONTROL_DETUNING_MHZ", 8.0, environ),
        "dc_search_min": _float("Q3_TLS_PUMP_DC_MIN", -20550.0, environ),
        "dc_search_max": _float("Q3_TLS_PUMP_DC_MAX", -11800.0, environ),
        "pump_gains": _integer_list(
            "Q3_TLS_PUMP_GAINS", [1500, 3000, 6000, 9000, 12000], environ),
        "pump_us": _float("Q3_TLS_PUMP_US", 15.0, environ),
        "probe_us": _float("Q3_TLS_PUMP_PROBE_US", 5.0, environ),
        "shots": int(_float("Q3_TLS_PUMP_SHOTS", 400, environ)),
        "dose_repeats": int(_float("Q3_TLS_PUMP_DOSE_REPEATS", 3, environ)),
        "confirmation_repeats": int(_float("Q3_TLS_PUMP_CONFIRM_REPEATS", 5, environ)),
        "recovery_repeats": int(_float("Q3_TLS_PUMP_RECOVERY_REPEATS", 3, environ)),
        "run_confirmation_if_detected": _bool(
            "Q3_TLS_PUMP_CONFIRM", True, environ),
        "run_recovery_if_confirmed": _bool(
            "Q3_TLS_PUMP_RECOVERY", True, environ),
        "correction_json": str(environ.get("Q3_TLS_PUMP_CORRECTION_JSON", "")).strip() or None,
    })
    if p["dc_search_max"] <= p["dc_search_min"]:
        raise ValueError("Q3 TLS pump DC bounds must be increasing")
    if p["shots"] <= 0 or p["dose_repeats"] <= 0:
        raise ValueError("Q3 TLS pump shots and dose repeats must be positive")
    return p


def main():
    p = settings()
    print("[q3 TLS pump-probe] center={:.6f} GHz; controls=+/-{:.3f} MHz; "
          "pump={} us; gains={}".format(
              p["tls_nominal_freq_ghz"], p["control_detuning_mhz"],
              p["pump_us"], p["pump_gains"]), flush=True)
    soc, soccfg = makeProxy()
    return saturation.run(soc, soccfg, outer_folder=outerFolder, settings=p)


if __name__ == "__main__":
    main()
