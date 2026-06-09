import glob
import h5py
import numpy as np
import matplotlib.pyplot as plt
import os
import datetime

# ---------------------------------------------------------------------------
# Calibration fit from ACStarkCalibration_2 (2026-06-02 00:43:42)
# Ramsey Frequency (kHz) = A * amplitude^2 + B
# ---------------------------------------------------------------------------
A_FIT = 2.8043e-05  # kHz / a.u.^2
B_FIT = 89.1187     # kHz

def amp_to_freq_kHz(amp):
    return A_FIT * np.asarray(amp, dtype=float) ** 2 + B_FIT

# ---------------------------------------------------------------------------
# Data directory and end file
# ---------------------------------------------------------------------------
DIR_0602 = r'Z:\t1Team\Data\2026-05-22_BFF_cooldown\TAT3D02-ADT\Q1_6p8\T1ACStark\T1ACStark_2026_06_02'

# Read from the first file (in time) up to and including this file (inclusive)
END_FILE = 'T1ACStark_2026_06_02_09_33_08_data.h5'

# ---------------------------------------------------------------------------
# Collect files
# Filenames use fixed-width zero-padded timestamps, so a lexicographic sort
# is identical to chronological order.
# ---------------------------------------------------------------------------
all_files = sorted(glob.glob(os.path.join(DIR_0602, '*_data.h5')))
all_files = [f for f in all_files if os.path.basename(f) <= END_FILE]
print(f"Found {len(all_files)} files")

# ---------------------------------------------------------------------------
# Parse timestamp from filename: T1ACStark_YYYY_MM_DD_HH_MM_SS_data.h5
# ---------------------------------------------------------------------------
def parse_timestamp(fpath):
    parts = os.path.basename(fpath).split('_')
    return datetime.datetime(int(parts[1]), int(parts[2]), int(parts[3]),
                             int(parts[4]), int(parts[5]), int(parts[6]))

# ---------------------------------------------------------------------------
# Load data
# Each file: avgi_2D shape (n_amps, n_wait_times), n_wait_times=1 here (tau=80 us)
# ---------------------------------------------------------------------------
TAU_IDX = 0  # single wait time experiment, only one index

timestamps = []
avgi_cols = []
avgq_cols = []
amp_pts_ref = None

for fpath in all_files:
    try:
        with h5py.File(fpath, 'r') as f:
            amp_pts = np.array(f['amp_pts'])
            avgi_2D = np.array(f['avgi_2D'])  # (n_amps, n_wait_times)
            avgq_2D = np.array(f['avgq_2D'])
        if amp_pts_ref is None:
            amp_pts_ref = amp_pts
        timestamps.append(parse_timestamp(fpath))
        avgi_cols.append(avgi_2D[:, TAU_IDX])
        avgq_cols.append(avgq_2D[:, TAU_IDX])
    except Exception as e:
        print(f"Skipping {os.path.basename(fpath)}: {e}")

print(f"Loaded {len(timestamps)} files successfully")

# ---------------------------------------------------------------------------
# Build 2D arrays: shape (n_amps, n_times)
# ---------------------------------------------------------------------------
t0 = timestamps[0]
time_hours = np.array([(t - t0).total_seconds() / 3600 for t in timestamps])
freq_kHz = amp_to_freq_kHz(amp_pts_ref)

avgi_map = np.column_stack(avgi_cols)  # (n_amps, n_times)
avgq_map = np.column_stack(avgq_cols)

print(f"Time span: {time_hours[-1]:.2f} hours")
print(f"Frequency range: {freq_kHz[0]:.1f} – {freq_kHz[-1]:.1f} kHz")

# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------
fig, axes = plt.subplots(2, 1, figsize=(14, 10))

im0 = axes[0].pcolormesh(time_hours, freq_kHz, avgi_map, shading='nearest', cmap='viridis')
plt.colorbar(im0, ax=axes[0], label='I (a.u.)')
axes[0].set_xlabel('Time from start (hours)')
axes[0].set_ylabel('AC Stark Shift (kHz)')
axes[0].set_title(f'T1ACStark I quadrature  (tau = 80 µs, {len(timestamps)} reps)')

im1 = axes[1].pcolormesh(time_hours, freq_kHz, avgq_map, shading='nearest', cmap='viridis')
plt.colorbar(im1, ax=axes[1], label='Q (a.u.)')
axes[1].set_xlabel('Time from start (hours)')
axes[1].set_ylabel('AC Stark Shift (kHz)')
axes[1].set_title(f'T1ACStark Q quadrature  (tau = 80 µs, {len(timestamps)} reps)')

plt.tight_layout()
date_str = t0.strftime('%Y_%m_%d')
counter = 0
while True:
    save_path = os.path.join(DIR_0602, f'T1ACStark_2D_timeplot_{date_str}_{counter:04d}.png')
    if not os.path.exists(save_path):
        break
    counter += 1
plt.savefig(save_path, dpi=150)
print(f"Saved to {save_path}")
plt.show()
