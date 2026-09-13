"""Render static scientific diagnostics from the frozen offline report."""
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import savgol_filter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fluxpred.core import Filter
from fluxpred.validation import build_shot

root = Path(__file__).resolve().parents[1]/'reports'/'neutral_flux'
report = json.loads((root/'comparison.json').read_text())
traces = json.loads((root/'forecast_traces.json').read_text())
fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True, constrained_layout=True)
colors = ['#475569', '#1565c0', '#b45309']
labels = ['Existing piecewise: measured', 'Shared LTI: conditional forecast', 'Conditioned: conditional forecast']
for ax, entry, target in zip(axes, traces.values(), ['4.3 GHz', 'Center', '3.8 GHz']):
    t = np.asarray(entry['time_ns'])/1000
    valid = np.array(entry['support'])
    for key, color, label in zip(['piecewise_frequency_mhz','lti_forecast_frequency_mhz','conditioned_forecast_frequency_mhz'], colors, labels):
        f = np.array(entry[key], float)
        good = valid & np.isfinite(f)
        smoothed = savgol_filter(np.interp(t, t[good], f[good]), 17, 2)
        late = good & (t >= 300)
        smoothed -= np.mean(smoothed[late])
        ax.plot(t[good], smoothed[good], color=color, lw=1.7, label=label)
    ax.axhspan(-.25, .25, color='#16a34a', alpha=.12, label='±0.25 MHz reference band')
    ax.axvspan(0, 5, color='#94a3b8', alpha=.4)
    ax.axhline(0, color='#64748b', lw=.6)
    ax.set_ylabel('Frequency − late mean (MHz)')
    ax.set_title(target, loc='left', fontweight='bold')
    ax.grid(alpha=.17)
axes[0].legend(loc='upper right', fontsize=8, ncol=2)
axes[-1].set_xlabel('Delay from target edge (µs)')
axes[-1].set_xlim(0, 500)
fig.suptitle('Offline gate fails: measured discrepancy survives the new command\nRaw estimates smoothed once over 17 samples; forecasts restricted to ≥5 µs', fontsize=12)
fig.savefig(root/'residual_comparison.png', dpi=170)
plt.close(fig)

model = Filter.from_dict(json.loads((root/'conditioned_candidate.json').read_text())['model'])
shot = build_shot(model, amplitude=1, hold_ns=100000, recovery_ns=1600000, sample_ns=2000)
c = shot['command']; t = c.edges_ns/1000
fig, axes = plt.subplots(2, 1, figsize=(10, 6), constrained_layout=True)
axes[0].stairs(c.values, t, color='#1565c0')
axes[0].set_xlim(0, 100); axes[0].set_ylim(.99, 1.045)
axes[0].set_title('Target command: four stable states, 2 µs interval means', loc='left')
axes[1].stairs(c.values, t-100, color='#b45309')
axes[1].set_xlim(0, 600); axes[1].set_ylim(-.045, .015)
axes[1].set_title('Return command: outbound history continues through park', loc='left')
for ax in axes:
    ax.set_ylabel('Normalized command'); ax.set_xlabel('Time from edge (µs)'); ax.grid(alpha=.2)
fig.savefig(root/'causal_command.png', dpi=170)
plt.close(fig)
print('Wrote residual_comparison.png and causal_command.png')
