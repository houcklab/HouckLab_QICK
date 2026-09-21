"""q3 P4 long-time spectroscopy using the production 25-us target hold.

This is intentionally the QICK counterpart of QUA's P4ProductionTiming.py:
it only runs P4, writes the ordinary raw-sweep CSV, and uses the same
park -> target -> held spectroscopy -> park lifecycle as production.  It is
not a T1 scan and does not alter the production five-point runner.
"""

import os
import sys


_directory = os.path.dirname(os.path.abspath(__file__))
while _directory != os.path.dirname(_directory):
    if os.path.isdir(os.path.join(_directory, "WorkingProjects")):
        if _directory not in sys.path:
            sys.path.insert(0, _directory)
        break
    _directory = os.path.dirname(_directory)
else:
    raise RuntimeError("Could not find the HouckLab_QICK repo root.")


from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSSpectroscopy as tls


def _float(name, default):
    return float(os.environ.get(name, default))


def _int(name, default):
    return int(os.environ.get(name, default))


def apply_overrides(environ=None):
    environ = os.environ if environ is None else environ
    p = tls.P4_LONG_TIME
    p["run"] = True
    p["shots"] = _int("Q3_P4_SHOTS", p["shots"])
    p["spec_amp"] = _int("Q3_P4_SPEC_AMP", 25000)
    p["spec_len_us"] = _float("Q3_P4_SPEC_LEN_US", 0.5)
    # This contains q3's entire current 4.3 -> 3.9 GHz branch.  The raw
    # window deliberately has margin so the trace does not ride a scan edge.
    p["freq_min"] = _float("Q3_P4_FREQ_MIN_MHZ", 3700.0)
    p["freq_max"] = _float("Q3_P4_FREQ_MAX_MHZ", 4600.0)
    p["freq_step"] = _float("Q3_P4_FREQ_STEP_MHZ", 0.5)
    p["dc_min"] = _int("Q3_P4_DC_MIN", -30000)
    p["dc_max"] = _int("Q3_P4_DC_MAX", -12500)
    p["dc_step"] = _int("Q3_P4_DC_STEP", 250)
    p["long_time_us"] = _float("Q3_P4_HOLD_US", 25.0)
    p["average_window_us"] = 0.0
    p["live_plot"] = str(environ.get("Q3_P4_LIVE_PLOT", "1")).strip().lower() in {
        "1", "true", "yes", "on"}
    return p


def main():
    p = apply_overrides()
    correction_json = os.environ.get("Q3_P4_CORRECTION_JSON", "").strip() or None
    gain = os.environ.get("Q3_FLUX_TAIL_GAIN")
    if gain is not None and str(gain).strip() != "":
        value = float(gain)
        if not (value > 0.0) or value != value:
            raise ValueError("Q3_FLUX_TAIL_GAIN must be finite and positive")
        tls.FLUX_TAIL_COMPENSATION_GAIN = value

    n_dc = int(round((p["dc_max"] - p["dc_min"]) / p["dc_step"])) + 1
    n_freq = int(round((p["freq_max"] - p["freq_min"]) / p["freq_step"])) + 1
    print("\n=========== q3 P4 at production timing ===========")
    print(f"  hold                : {p['long_time_us']:g} us")
    print(f"  dc                  : {p['dc_min']:.0f} .. {p['dc_max']:.0f} DAC "
          f"step {p['dc_step']:.0f} ({n_dc} points)")
    print(f"  qubit spec window   : {p['freq_min']/1e3:.4f} .. {p['freq_max']/1e3:.4f} GHz "
          f"step {p['freq_step']:g} MHz ({n_freq} points)")
    print(f"  spec                : amp {p['spec_amp']}, len {p['spec_len_us']:g} us")
    print(f"  shots               : {p['shots']}")
    print(f"  correction          : {correction_json or 'none'}")
    print("  raw-sweep CSV is always saved; no automatic flux-fit overwrite")
    print("==================================================\n")

    tls._set_yoko_if_requested()
    soc, soccfg = tls.makeProxy()
    tls.run_step4_long_time_spec(tls.outerFolder, soc, soccfg, correction_json)


if __name__ == "__main__":
    main()
