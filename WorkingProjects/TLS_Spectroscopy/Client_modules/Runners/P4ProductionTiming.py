"""q3 P4 long-time spectroscopy using the production 25-us target hold.

This is intentionally the QICK counterpart of QUA's P4ProductionTiming.py:
it only runs P4, writes the ordinary raw-sweep CSV, and uses the same
park -> target -> held spectroscopy -> park lifecycle as production.  It is
not a T1 scan and does not alter the production five-point runner.
"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path

import numpy as np


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
    # Exact q3_08_54_58 P4 grid authority.  The only physics change from that
    # run is the 5 -> 25 us target hold requested for the production audit.
    p["freq_min"] = _float("Q3_P4_FREQ_MIN_MHZ", 3800.0)
    p["freq_max"] = _float("Q3_P4_FREQ_MAX_MHZ", 4500.0)
    # This is the reference P4's 1-MHz grid (700 points, stop-exclusive in
    # the underlying experiment), safely below QICK program memory.
    p["freq_step"] = _float("Q3_P4_FREQ_STEP_MHZ", 1.0)
    p["dc_min"] = _int("Q3_P4_DC_MIN", -30000)
    p["dc_max"] = _int("Q3_P4_DC_MAX", -12500)
    p["dc_step"] = _int("Q3_P4_DC_STEP", 250)
    p["dc_chunk_points"] = _int("Q3_P4_DC_CHUNK_POINTS", 16)
    if p["dc_chunk_points"] < 1:
        raise ValueError("Q3_P4_DC_CHUNK_POINTS must be positive")
    p["long_time_us"] = _float("Q3_P4_HOLD_US", 25.0)
    p["dt_pulseplay_us"] = _float("Q3_P4_DT_PULSEPLAY_US", 0.5)
    p["dt_pulsedef_us"] = _float("Q3_P4_DT_PULSEDEF_US", 0.002)
    p["opx_hard_flux_steps"] = True
    p["flux_settle_time_us"] = 0.5
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
    n_freq = int(np.arange(p["freq_min"], p["freq_max"], p["freq_step"]).size)
    print("\n=========== q3 P4 at production timing ===========")
    print(f"  hold                : {p['long_time_us']:g} us")
    print(f"  dc                  : {p['dc_min']:.0f} .. {p['dc_max']:.0f} DAC "
          f"step {p['dc_step']:.0f} ({n_dc} points; chunks of "
          f"{p['dc_chunk_points']})")
    print(f"  qubit spec window   : {p['freq_min']/1e3:.4f} .. {p['freq_max']/1e3:.4f} GHz "
          f"step {p['freq_step']:g} MHz ({n_freq} points)")
    print(f"  spec                : amp {p['spec_amp']}, len {p['spec_len_us']:g} us; "
          f"waveform grid {p['dt_pulseplay_us']:g} us")
    print(f"  shots               : {p['shots']}")
    print(f"  correction          : {correction_json or 'none'}")
    print("  raw-sweep CSV is always saved; no automatic flux-fit overwrite")
    print("==================================================\n")

    tls._set_yoko_if_requested()
    soc, soccfg = tls.makeProxy()
    # The QICK instruction image embeds a corrected waveform for every DC
    # target.  71 targets x 48 correction segments is larger than its 16k
    # instruction store, even with only a single MHz frequency grid.  Split
    # *only* the independent DC axis; every output remains a normal P4 raw CSV
    # at identical timing, and the manifest records the complete ordered set.
    dc_values = np.arange(
        p["dc_min"], p["dc_max"] + 0.5 * p["dc_step"], p["dc_step"], dtype=float
    )
    original = (p["dc_min"], p["dc_max"])
    outputs = []
    try:
        for block_number, start in enumerate(
            range(0, dc_values.size, p["dc_chunk_points"]), start=1
        ):
            block = dc_values[start:start + p["dc_chunk_points"]]
            p["dc_min"], p["dc_max"] = float(block[0]), float(block[-1])
            print(f"[p4] block {block_number}: {block[0]:.0f}..{block[-1]:.0f} DAC "
                  f"({block.size} DC targets)")
            result = tls.run_step4_long_time_spec(
                tls.outerFolder, soc, soccfg, correction_json
            )
            raw_csv = result["data"].get("raw_sweep_csv")
            if raw_csv:
                outputs.append(str(raw_csv))
    finally:
        p["dc_min"], p["dc_max"] = original

    if outputs:
        manifest = Path(outputs[-1]).with_name(
            datetime.now().strftime("q3_%H_%M_%S_P4_ProductionTiming_manifest.json")
        )
        manifest.write_text(json.dumps({
            "kind": "q3_production_timing_p4_manifest",
            "hold_us": p["long_time_us"],
            "frequency_window_mhz": [p["freq_min"], p["freq_max"]],
            "frequency_step_mhz": p["freq_step"],
            "dc_step_dac": p["dc_step"],
            "dc_chunk_points": p["dc_chunk_points"],
            "correction_json": correction_json,
            "raw_sweep_csvs": outputs,
        }, indent=2))
        print(f"P4_MANIFEST={manifest}")


if __name__ == "__main__":
    main()
