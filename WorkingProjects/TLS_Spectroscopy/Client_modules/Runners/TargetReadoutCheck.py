import csv
import os
from os import environ

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import (
    BaseConfig, outerFolder,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mTransmission import (
    Transmission,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.readout_dip import (
    dip_metrics, ladder_verdict, print_table,
)

QUBIT = environ.get("Q3_READOUT_CHECK_QUBIT", "q3")
MODE = environ.get("Q3_READOUT_CHECK_MODE", "sweep").strip().lower()
TARGET_GAIN = int(environ.get("Q3_READOUT_CHECK_TARGET_GAIN", "-14750"))
PARK_GAIN = int(environ.get("Q3_READOUT_CHECK_PARK_GAIN", "-25146"))
GAIN_MIN = int(environ.get("Q3_READOUT_CHECK_GAIN_MIN", "150"))
GAIN_MAX = int(environ.get("Q3_READOUT_CHECK_GAIN_MAX", "12000"))
NUM_GAIN = int(environ.get("Q3_READOUT_CHECK_NUM_GAIN", "12"))
FREQ_MIN = float(environ.get("Q3_READOUT_CHECK_FREQ_MIN_MHZ", "6930.5"))
FREQ_MAX = float(environ.get("Q3_READOUT_CHECK_FREQ_MAX_MHZ", "6935.5"))
FREQ_STEP = float(environ.get("Q3_READOUT_CHECK_FREQ_STEP_MHZ", "0.05"))
SHOTS = int(environ.get("Q3_READOUT_CHECK_SHOTS", "300"))
READ_LEN_US = float(environ.get("Q3_READOUT_CHECK_READ_LEN_US",
                                str(BaseConfig.get("read_length", 3.5))))
SHIFT_TOL_MHZ = float(environ.get("Q3_READOUT_CHECK_SHIFT_TOL_MHZ", "0.05"))
EXPECTED_MHZ = environ.get("Q3_READOUT_CHECK_EXPECTED_MHZ")
BATCHED = environ.get("Q3_READOUT_CHECK_BATCHED", "1").strip().lower() in {"1", "true", "yes", "on"}

RESONATOR_FIT_PARAMS = [
    6929532609.626256, 102183842.77558708, 12.457027141606355,
    0.18504287441157935, 60361.19628170067, -25581.578015529918,
    0.18012547035756307,
]


def predicted_resonator_mhz(gain, params=None):
    p = RESONATOR_FIT_PARAMS if params is None else params
    f_bare, g, ejmax, ec, period, offset, d = [float(v) for v in p]
    x = float(gain)
    phase = np.pi * (x - offset) / period
    ej = ejmax * np.sqrt(np.cos(phase) ** 2 + d ** 2 * np.sin(phase) ** 2)
    fq = 1e9 * (np.sqrt(8.0 * ej * ec) - ec)
    delta = f_bare - fq
    dressed = 0.5 * (f_bare + fq) + 0.5 * np.sign(delta) * np.sqrt(delta ** 2 + 4.0 * g ** 2)
    return dressed / 1e6


def build_cfg(gain):
    cfg = dict(BaseConfig)
    cfg["ff_park_gain"] = TARGET_GAIN
    cfg["read_pulse_gain"] = int(gain)
    cfg["read_length"] = READ_LEN_US
    cfg["shots"] = SHOTS
    cfg["reps"] = SHOTS
    cfg["resonator_fit_parameters"] = list(RESONATOR_FIT_PARAMS)
    cfg["qua_shot_order"] = BATCHED
    return cfg


def main():
    soc, soccfg = makeProxy()
    f_vec = np.arange(FREQ_MIN, FREQ_MAX + 0.5 * FREQ_STEP, FREQ_STEP)
    gains = np.unique(np.geomspace(GAIN_MIN, GAIN_MAX, NUM_GAIN).round().astype(int))
    expected = (float(EXPECTED_MHZ) if EXPECTED_MHZ
                else predicted_resonator_mhz(TARGET_GAIN))
    park_pred = predicted_resonator_mhz(PARK_GAIN)

    print("")
    print("=========== q3 target-flux readout check ===========")
    print(f"  mode                : {MODE}")
    print(f"  qubit               : {QUBIT}")
    print(f"  park ff_gain        : {PARK_GAIN:+d}  (resonator model {park_pred:.4f} MHz)")
    print(f"  TARGET ff_gain      : {TARGET_GAIN:+d}  (resonator model {expected:.4f} MHz)")
    print(f"  park->target moves the resonator {expected - park_pred:+.4f} MHz")
    print(f"  live read_pulse_gain: {BaseConfig.get('read_pulse_gain')}")
    print(f"  live read_pulse_freq: {BaseConfig.get('read_pulse_freq')} MHz")
    print(f"  read_length         : {READ_LEN_US} us")
    print(f"  window              : {f_vec.min():.3f} .. {f_vec.max():.3f} MHz, "
          f"{len(f_vec)} pts, {FREQ_STEP:.4f} MHz step")
    print(f"  gain ladder         : {len(gains)} pts geometric {gains.min()} .. {gains.max()}")
    print(f"  shots               : {SHOTS}   batched acquisition: {BATCHED}")
    print("====================================================")
    print("")

    if MODE == "reference":
        gains = np.array([int(BaseConfig.get("read_pulse_gain", 1880))])

    rows = []
    traces = {}
    for gain in gains:
        cfg = build_cfg(gain)
        exp = Transmission(soc=soc, soccfg=soccfg, path=QUBIT,
                           outerFolder=outerFolder,
                           prefix=f"Target_Readout_Gain_{int(gain)}",
                           suffix="Target_Readout_Check", cfg=cfg,
                           f_vec=f_vec, plot=False, save=False)
        out = exp.acquire(progress=True)
        mag = np.asarray(out["data"]["IQ_magnitude_dBm"], dtype=float)
        traces[int(gain)] = mag
        m = dip_metrics(f_vec, mag)
        m["gain"] = int(gain)
        rows.append(m)
        print(f"  gain {int(gain):6d}: dip {m['dip_mhz']:10.4f} MHz  depth "
              f"{m['depth_db']:6.3f} dB  {m['sigma']:5.1f} sigma  FWHM "
              f"{m['fwhm_mhz']:7.4f} MHz" + ("   EDGE" if m["edge_flag"] else ""))

    verdict = ladder_verdict(rows, expect_dip_mhz=expected,
                             shift_tol_mhz=SHIFT_TOL_MHZ)
    print_table(rows, verdict, shift_tol_mhz=SHIFT_TOL_MHZ)

    base = os.path.join(outerFolder, QUBIT)
    os.makedirs(base, exist_ok=True)
    csv_path = os.path.join(base, f"{QUBIT}_target_readout_check_gain_table.csv")
    with open(csv_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["read_gain", "dip_MHz", "depth_dB", "sigma", "fwhm_MHz",
                    "baseline_dB", "noise_dB", "shift_from_lowest_MHz",
                    "off_consensus_MHz", "edge_flag", "stray_flag"])
        for r in rows:
            w.writerow([r["gain"], f"{r['dip_mhz']:.6f}", f"{r['depth_db']:.4f}",
                        f"{r['sigma']:.2f}", f"{r['fwhm_mhz']:.6f}",
                        f"{r['baseline_db']:.4f}", f"{r['noise_db']:.5f}",
                        f"{r['shift_from_lowest_mhz']:.6f}",
                        f"{r['off_consensus_mhz']:.6f}",
                        int(r["edge_flag"]), int(r.get("stray_flag", False))])
    trace_path = os.path.join(base, f"{QUBIT}_target_readout_check_traces.csv")
    with open(trace_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["freq_MHz"] + [f"gain_{g}" for g in sorted(traces)])
        for i, f in enumerate(f_vec):
            w.writerow([f"{f:.6f}"] + [f"{traces[g][i]:.4f}" for g in sorted(traces)])

    print("=========== verdict ===========")
    if verdict["trustworthy"] and verdict["best"] is not None:
        b = verdict["best"]
        print(f"  measured dip        : {verdict['consensus_mhz']:.4f} MHz")
        print(f"  model prediction    : {expected:.4f} MHz")
        print(f"  disagreement        : {verdict['expect_offset_mhz']:+.4f} MHz")
        print(f"  recommended gain    : {b['gain']}   (currently "
              f"{BaseConfig.get('read_pulse_gain')})")
        print(f"  recommended freq    : {b['dip_mhz']:.4f} MHz   (currently "
              f"{BaseConfig.get('read_pulse_freq')})")
    else:
        print("  UNUSABLE -- see the warning above; nothing should be promoted.")
    print(f"  gain table          : {csv_path}")
    print(f"  raw traces          : {trace_path}")
    print("===============================")
    print("")
    print("Nothing was written to BaseConfig. Promote read_pulse_gain / "
          "read_pulse_freq only after inspecting the traces.")
    return rows, verdict


if __name__ == "__main__":
    main()
