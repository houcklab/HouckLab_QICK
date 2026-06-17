"""
T1-over-time plotter.

Reads all T1FF .h5 data sets in a folder (starting from a chosen file), refits
each T1 decay using the same exponential model as mT1FF.py, and plots the fitted
T1 vs. acquisition time with 1-sigma fit error bars.

Each .h5 file (from T1FF.save_data) contains:
    x_pts : (n,)        wait times (us)
    avgi  : (1, 1, n)   I quadrature
    avgq  : (1, 1, n)   Q quadrature
    qfreq : scalar      qubit frequency
The acquisition time is parsed from the filename timestamp
    T1_YYYY_MM_DD_HH_MM_SS_data_Q<N>.h5
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
DATA_FOLDER = rf"Z:\t1Team\Data\2026-06-08_BFG_cooldown\Device 4 KOH stats\RFSOC\{qubit}\T1\T1_2026_06_13"
# Only data sets at or after this file (by timestamp) are included.
START_FILE = None
# Where to save the output figure (defaults to this script's folder).
OUTPUT_DIR = rf"Z:\t1Team\Data\2026-06-08_BFG_cooldown\Device 4 KOH stats\RFSOC\{qubit}\T1\T1_2026_06_13"

# Filename timestamp pattern: T1_YYYY_MM_DD_HH_MM_SS_..._Q<N>.h5
_TS_RE = re.compile(r"T1_(\d{4})_(\d{2})_(\d{2})_(\d{2})_(\d{2})_(\d{2})")


# ---------------------------------------------------------------------------
# Helpers (mirrors mT1FF.py)
# ---------------------------------------------------------------------------
def amplitude_iq(I, Q, phase_num_points=200):
    """Find the rotation angle that puts (almost) all signal into I.

    Identical to Amplitude_IQ in mT1FF.py.
    """
    complex_iq = I + 1j * Q
    phase_values = np.linspace(0, np.pi, phase_num_points)
    multiplied_phase = [complex_iq * np.exp(1j * phase) for phase in phase_values]
    Q_range = np.array(
        [np.max(p.imag) - np.min(p.imag) for p in multiplied_phase]
    )
    phase_index = np.argmin(Q_range)
    return phase_values[phase_index]


def _exp_fit(x, a, T1, c):
    return a * np.exp(-1.0 * x / T1) + c


def fit_t1(x_pts, avgi, avgq):
    """Replicate the I-channel T1 fit from mT1FF.display().

    Returns (T1_est, T1_err) in the same units as x_pts (us).
    """
    rotation_angle = amplitude_iq(avgi, avgq)
    rotated_iq = (avgi + 1j * avgq) * np.exp(1j * rotation_angle)
    avgi = rotated_iq.real

    a_guess = avgi[0] - avgi[-1]
    b_guess = avgi[-1]
    approx_t1_val = a_guess / 2.6 + b_guess
    index_t1_guess = np.argmin(np.abs(avgi - approx_t1_val))
    t1_guess = x_pts[index_t1_guess]
    guess = [a_guess, t1_guess, b_guess]

    pOpt, pCov = curve_fit(_exp_fit, x_pts, avgi, p0=guess)
    perr = np.sqrt(np.diag(pCov))

    T1_est = np.abs(pOpt[1])
    T1_err = perr[1]
    return T1_est, T1_err


def parse_timestamp(filename):
    """Parse the acquisition datetime from a T1 data filename."""
    if filename is None:
        return datetime.datetime.min
    m = _TS_RE.search(filename)
    if not m:
        return None
    year, month, day, hour, minute, second = (int(g) for g in m.groups())
    return datetime.datetime(year, month, day, hour, minute, second)


def load_h5(path):
    """Load x_pts, avgi, avgq from a T1FF .h5 file."""
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

    # Collect candidate data files (the actual data is in the *_Q<N>.h5 files).
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

    times, t1_vals, t1_errs = [], [], []
    for dt, fn in records:
        path = os.path.join(DATA_FOLDER, fn)
        try:
            x_pts, avgi, avgq = load_h5(path)
            T1_est, T1_err = fit_t1(x_pts, avgi, avgq)
        except Exception as exc:
            print(f"[skip] {fn}: {exc}")
            continue
        times.append(dt)
        t1_vals.append(T1_est)
        t1_errs.append(T1_err)
        # print(f"{dt:%Y-%m-%d %H:%M:%S}  T1 = {T1_est:8.2f} +/- {T1_err:6.2f} us")

    if not times:
        raise RuntimeError("No data sets could be fit successfully.")

    times = np.array(times)
    t1_vals = np.array(t1_vals)
    t1_errs = np.array(t1_errs)

    # Elapsed hours since the first acquisition (more readable x-axis).
    t0 = times[0]
    elapsed_hours = np.array(
        [(t - t0).total_seconds() / 3600.0 for t in times]
    )

    mean_t1 = np.mean(t1_vals)
    std_t1 = np.std(t1_vals)

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.errorbar(
        times, t1_vals, yerr=t1_errs,
        fmt="o", capsize=3, label="T1 data",
    )
    ax.axhline(mean_t1, color="tab:red", ls="--",
               label=fr"Mean = {mean_t1:.1f} us")
    # Ticks only at full-hour marks (interval chosen to avoid crowding).
    span_hours = (times[-1] - times[0]).total_seconds() / 3600.0
    hour_interval = max(1, int(np.ceil(span_hours / 10)))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=hour_interval))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d-%H-00"))
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    ax.set_xlabel("Time")
    ax.set_ylabel(r"T1 ($\mu$s)")
    ax.set_title(f"{qubit} T1 over time  ({len(times)} data points)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    stamp = f"{times[0]:%Y%m%d_%H%M%S}_to_{times[-1]:%H%M%S}"
    out_path = os.path.join(OUTPUT_DIR, f"T1_overTime_{stamp}.png")
    fig.savefig(out_path, dpi=200)
    print(f"\nSaved figure: {out_path}")
    print(f"N = {len(times)} | mean T1 = {mean_t1:.2f} us | st2d = {std_t1:.2f} us")

    plt.show()


if __name__ == "__main__":
    main()
