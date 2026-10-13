# spec_gain_length_sweep

Class `QubitSpecSliceFF` (see `qicklab.experiments.qubit_spec`). Regime **A**.

## What it measures

A grid of [two_tone_spec](two_tone_spec.md) runs: for every drive length in
`sweep_lengths`, a full spectrum at every drive gain in `sweep_gains`. Use it to choose a
spectroscopy power and length: enough to see the line, not so much that it power-broadens
or shows multi-photon features.

## Pulse sequence

Identical to [two_tone_spec](two_tone_spec.md#pulse-sequence), with the drive gain and
const-drive length replaced per grid point:

```
qubit_ch  ____|____[ const qubit_length = L, gain = G ]________________________________
res_ch    ________________________________________ 0.5 us __[==== length ====]____
ADC 0,1   ___________________________________________________|<-off->|## readout ##|__ 10 us __ relax_delay
            for L in sweep_lengths:  for G in sweep_gains:  one spectrum
```

`qubit_length` only matters while `Gauss=False`; with `Gauss=True` the length loop
repeats identical Gaussian spectra at each gain. No PMOD trigger.

## How to run

```python
PLAN = [R.spec_gain_length_sweep()]                                         # regime A
PLAN = [R.spec_gain_length_sweep(sweep_lengths=[10, 20], sweep_gains=list(range(200, 2001, 200)))]
```

Cost: `len(sweep_lengths) * len(sweep_gains)` spectra. The legacy defaults are
10 lengths x 49 gains = 490 spectra.

## Parameters

| Name (legacy key) | Legacy default | Units | Meaning |
|---|---|---|---|
| `sweep_lengths` | `range(10, 101, 10)` = 10 ... 100 | us | Const-drive lengths (outer loop) |
| `sweep_gains` | `range(200, 5001, 100)` = 200 ... 5000 | DAC | Drive gains (inner loop) |
| `SpecSpan` | 10 | MHz | Half-span (group `spec`) |
| `SpecNumPoints` | 201 | - | Points per spectrum |
| `Gauss`, `sigma` | False, 2 | -, us | Drive shape, as in two_tone_spec |
| `reps`, `rounds` | 20, 10 | - | Averaging per spectrum |
| `relax_delay` | 2500 | us | Wait between shots |
| `display` | True | bool | `plotDisp` |
| `min_sep_MHz` | 0.2 | MHz | Peak separation |
| `fit_window_mhz` | 0.5 | MHz | Lorentzian window (used, unlike two_tone_spec) |
| `prominent_ratio` | 0.1 | - | Second-peak threshold (used) |

## Outputs

One standard two_tone_spec record per grid point, `path = "QubitSpecFF"` (same folder as
two_tone_spec): `..._data.h5` (`x_pts`, `avgi`, `avgq`, peak and Lorentzian keys),
`..._data_IQ.png`, `..._data_Amp2_LorentzFits.png`, `..._data.json`. Every PNG title
carries `gain=... length=... us` (or the Gaussian sigma), so the grid can be browsed by
file. The console prints `=== GainLengthSweep: qubit_length=... qubit_gain=... ===` before
each point.

## Analysis

Per spectrum: as in [two_tone_spec](two_tone_spec.md#analysis). No cross-grid summary
(no map, no best-point selection); compare the saved `lorentz_fwhm` / `two_tone_peak_amps`
across files yourself.

## Findings & notes

- Purpose (from the legacy runner): nested gain x `qubit_length` sweep; `qubit_gain` and
  `qubit_length` appear in every saved plot title for identification.
- "qubit_length 10 was best for Q4" (legacy comment; device and date not recorded).

## Known issues

- With `Gauss=True` the length loop is redundant (identical spectra per length).
- All points go to the same `QubitSpecFF` folder as ordinary spectra; nothing in the
  filename marks them as part of a grid (only the config/title do).
