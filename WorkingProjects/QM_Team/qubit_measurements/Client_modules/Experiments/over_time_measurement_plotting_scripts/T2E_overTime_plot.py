"""
T2E (Hahn echo)-over-time plotter.

Reads all T2EMUX .h5 data sets in a folder (optionally starting from a chosen
file), refits each echo decay using the same exponential model as mT2EFF.py, and
plots the fitted T2E vs. acquisition time with 1-sigma fit error bars.

Each .h5 file (from T2EMUX.save_data) contains:
    x_pts : (n,)        wait times (us)
    avgi  : (1, 1, n)   I quadrature
    avgq  : (1, 1, n)   Q quadrature
    qfreq : scalar      qubit frequency
The acquisition time is parsed from the filename timestamp
    T2E_YYYY_MM_DD_HH_MM_SS_data_Q<N>_n<num_pi_pulses>.h5
"""

import os
import re
import datetime

import h5py
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from scipy.optimize import curve_fit

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
qubit = "Q1"
DATA_FOLDER = rf"Z:\t1Team\Data\2026-06-08_BFG_cooldown\Device 4 KOH stats\RFSOC\{qubit}\T2E\T2E_2026_06_13"
# Only data sets at or after this file (by timestamp) are included.
START_FILE = None
# Where to save the output figure (defaults to the data folder).
OUTPUT_DIR = rf"Z:\t1Team\Data\2026-06-08_BFG_cooldown\Device 4 KOH stats\RFSOC\{qubit}\T2E\T2E_2026_06_13"

# Filename timestamp pattern: T2E_YYYY_MM_DD_HH_MM_SS_..._Q<N>_n<N>.h5
_TS_RE = re.compile(r"T2E_(\d{4})_(\d{2})_(\d{2})_(\d{2})_(\d{2})_(\d{2})")


# ---------------------------------------------------------------------------
# Helpers (mirrors mT2EFF.py)
# ---------------------------------------------------------------------------
def amplitude_iq(I, Q, phase_num_points=200):
    """Find the rotation angle that puts (almost) all signal into I.

    Identical to Amplitude_IQ in mT2EFF.py.
    """
    complex_iq = I + 1j * Q
    phase_values = np.linspace(0, np.pi, phase_num_points)
    multiplied_phase = [complex_iq * np.exp(1j * phase) for phase in phase_values]
    Q_range = np.array(
        [np.max(p.imag) - np.min(p.imag) for p in multiplied_phase]
    )
    phase_index = np.argmin(Q_range)
    return phase_values[phase_index]


def _exp_fit(x, a, T, c):
    return a * np.exp(-1.0 * x / T) + c


def fit_t2e(x_pts, avgi, avgq):
    """Replicate the I-channel echo fit from mT2EFF.display().

    Returns (T2E_est, T2E_err) in the same units as x_pts (us).
    """
    rotation_angle = amplitude_iq(avgi, avgq)
    rotated_iq = (avgi + 1j * avgq) * np.exp(1j * rotation_angle)
    avgi = rotated_iq.real

    a_guess = avgi[0] - avgi[-1]
    b_guess = avgi[-1]
    approx_t1_val = a_guess / 2.6 + b_guess
    index_t1_guess = np.argmin(np.abs(avgi - approx_t1_val))
    t_guess = x_pts[index_t1_guess]
    guess = [a_guess, t_guess, b_guess]

    pOpt, pCov = curve_fit(_exp_fit, x_pts, avgi, p0=guess)
    perr = np.sqrt(np.diag(pCov))

    T2E_est = np.abs(pOpt[1])
    T2E_err = perr[1]
    return T2E_est, T2E_err


def parse_timestamp(filename):
    """Parse the acquisition datetime from a T2E data filename."""
    if filename is None:
        return datetime.datetime.min
    m = _TS_RE.search(filename)
    if not m:
        return None
    year, month, day, hour, minute, second = (int(g) for g in m.groups())
    return datetime.datetime(year, month, day, hour, minute, second)


def load_h5(path):
    """Load x_pts, avgi, avgq from a T2EMUX .h5 file."""
    with h5py.File(path, "r") as f:
        x_pts = f["x_pts"][()]
        avgi = f["avgi"][()][0][0]
        avgq = f["avgq"][()][0][0]
    return np.asarray(x_pts, float), np.asarray(avgi, float), np.asarray(avgq, float)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    start_dt = parse_timestamp(START_FILE)
    if start_dt is None:
        raise ValueError(f"Could not parse timestamp from START_FILE: {START_FILE}")

    # Collect candidate data files (the actual data is in the *_Q<N>_n<N>.h5 files).
    all_files = [
        fn for fn in os.listdir(DATA_FOLDER)
        if fn.endswith(".h5") and "_data" in fn
    ]

    records = []
    for fn in all_files:
        dt = parse_timestamp(fn)
        if dt is None or dt < start_dt:
            continue
        records.append((dt, fn))

    records.sort(key=lambda r: r[0])

    if not records:
        raise RuntimeError(
            f"No .h5 data files found at/after {START_FILE} in {DATA_FOLDER}"
        )

    times, t2e_vals, t2e_errs = [], [], []
    for dt, fn in records:
        path = os.path.join(DATA_FOLDER, fn)
        try:
            x_pts, avgi, avgq = load_h5(path)
            T2E_est, T2E_err = fit_t2e(x_pts, avgi, avgq)
        except Exception as exc:
            print(f"[skip] {fn}: {exc}")
            continue
        times.append(dt)
        t2e_vals.append(T2E_est)
        t2e_errs.append(T2E_err)
        # print(f"{dt:%Y-%m-%d %H:%M:%S}  T2E = {T2E_est:8.2f} +/- {T2E_err:6.2f} us")

    if not times:
        raise RuntimeError("No data sets could be fit successfully.")

    times = np.array(times)
    t2e_vals = np.array(t2e_vals)
    t2e_errs = np.array(t2e_errs)

    mean_t2e = np.mean(t2e_vals)
    std_t2e = np.std(t2e_vals)

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.errorbar(
        times, t2e_vals, yerr=t2e_errs,
        fmt="o", capsize=3, label="T2E data",
    )
    ax.axhline(mean_t2e, color="tab:red", ls="--",
               label=fr"Mean = {mean_t2e:.1f} us")
    # Ticks only at full-hour marks (interval chosen to avoid crowding).
    span_hours = (times[-1] - times[0]).total_seconds() / 3600.0
    hour_interval = max(1, int(np.ceil(span_hours / 10)))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=hour_interval))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d-%H-00"))
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    ax.set_xlabel("Time")
    ax.set_ylabel(r"T2E ($\mu$s)")
    ax.set_title(f"{qubit} T2E over time  ({len(times)} data points)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    stamp = f"{times[0]:%Y%m%d_%H%M%S}_to_{times[-1]:%H%M%S}"
    out_path = os.path.join(OUTPUT_DIR, f"T2E_overTime_{stamp}.png")
    fig.savefig(out_path, dpi=200)
    print(f"\nSaved figure: {out_path}")
    print(f"N = {len(times)} | mean T2E = {mean_t2e:.2f} us | std = {std_t2e:.2f} us")

    plt.show()


if __name__ == "__main__":
    main()
