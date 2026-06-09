import json
import glob
import numpy as np
import matplotlib.pyplot as plt
import h5py
from scipy.optimize import curve_fit

data_dir = r'Z:\t1Team\Data\2026-05-22_BFF_cooldown\TAT3D02-ADT\Q1_6p8\ACStarkCalibration\ACStarkCalibration_2026_05_30'

def decaying_cos(t, A, T2, freq, phase, offset):
    return A * np.exp(-t / T2) * np.cos(2 * np.pi * freq * t + phase) + offset

amp_list = []
freq_list = []

h5_files = sorted(glob.glob(data_dir + r'\*.h5'))

# find where the second sweep starts (amplitude resets back near 0 after rising)
amps_all = []
for h5_path in h5_files:
    with open(h5_path.replace('.h5', '.json'), 'r') as f:
        amps_all.append(json.load(f)['ACStark_amplitude'])

second_sweep_start = 0
for i in range(1, len(amps_all)):
    if amps_all[i] < amps_all[i - 1] and amps_all[i] < 100:
        second_sweep_start = i

h5_files = h5_files[second_sweep_start:]

for h5_path in h5_files:
    json_path = h5_path.replace('.h5', '.json')

    # load ACStark amplitude from config
    with open(json_path, 'r') as f:
        cfg = json.load(f)
    ac_stark_amp = cfg['ACStark_amplitude']

    # load data
    with h5py.File(h5_path, 'r') as f:
        x_pts = np.array(f['x_pts'])
        avgi  = np.array(f['avgi'])
        avgq  = np.array(f['avgq'])

    # fit decaying cosine
    dt = x_pts[1] - x_pts[0]
    yf = np.fft.rfft(avgi - np.mean(avgi))
    xf = np.fft.rfftfreq(len(x_pts), dt)
    freq0  = xf[np.argmax(np.abs(yf[1:])) + 1]
    A0     = (np.max(avgi) - np.min(avgi)) / 2
    T2_0   = (x_pts[-1] - x_pts[0]) / 2
    offset0 = np.mean(avgi)

    try:
        pOpt, _ = curve_fit(decaying_cos, x_pts, avgi, p0=[A0, T2_0, freq0, 0, offset0],
                            maxfev=10000,
                            bounds=([-np.inf, 0, 0, -np.pi, -np.inf],
                                    [np.inf, np.inf, np.inf, np.pi, np.inf]))
        amp_list.append(ac_stark_amp)
        freq_list.append(pOpt[2])  # MHz
        print(f"amp={ac_stark_amp:5.1f}  freq={pOpt[2]*1e3:.4f} kHz")
    except Exception:
        print(f"amp={ac_stark_amp:5.1f}  fit failed, skipping")

amp_arr  = np.array(amp_list)
freq_arr = np.array(freq_list) * 1e3  # convert to kHz

# quadratic fit
coeffs = np.polyfit(amp_arr, freq_arr, 2)
a, b, c = coeffs
x_fit = np.linspace(amp_arr[0], amp_arr[-1], 300)
y_fit = np.polyval(coeffs, x_fit)

title_str = f"ACStarkCalibration_2026_05_30_{a:.4f}x^2+{b:.4f}x+{c:.4f}"

plt.figure()
plt.plot(amp_arr, freq_arr, 'o', label="data", color='orange')
plt.plot(x_fit, y_fit, '-', label="fit", color='black')
plt.xlabel("AC Stark Amplitude (a.u.)")
plt.ylabel("Ramsey Frequency (kHz)")
plt.title(title_str)
plt.legend()
plt.savefig(data_dir + r'\ACStarkCalibration_amp_sweep_reconstructed.png')
plt.show()
