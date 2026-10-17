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
`..._data_IQ.png`, `..._data_Amp2_LorentzFits.png`, `..._data.json`,
`..._data_provenance.json` ([provenance](../architecture.md#provenance)). Every PNG title
carries `gain=... length=... us` (or the Gaussian sigma), so the grid can be browsed by
file. The console prints `=== GainLengthSweep: qubit_length=... qubit_gain=... ===` before
each point.

After the last point (not on an aborted grid) the run prints one summary line per length and
writes `GainLengthSweep_summary_<YYYY_MM_DD_HH_MM_SS>.npz` and `.png` into the dated
`QubitSpecFF` folder of the last point. The npz holds plain arrays (`np.load(...,
allow_pickle=False)` works):

| Key | Shape | Meaning |
|---|---|---|
| `point_q_length`, `point_q_gain` | (N,) | Grid point, in run order |
| `point_peak_freqs`, `point_peak_amps`, `point_snr` | (N, 2) | display's selected peaks (ascending frequency) and each one's SNR |
| `point_lorentz_centers`, `_fwhm`, `_amplitudes`, `_r2` | (N, 2) | display's Lorentzian fits (its 0.5 MHz window), copied |
| `point_refit_centers`, `_fwhm`, `_fwhm_err`, `_window_mhz`, `_censored` | (N, 2) | Summary refit per peak (below); censored = 1 when the width is not trusted |
| `point_fwhm_line`, `_fwhm_line_err`, `_snr_line`, `_center_line` | (N,) | The narrower uncensored line of the point, the saturation fit's input |
| `point_blended` | (N,) | 1 when that line is a merged doublet (below), left out of the fit; 0 when used; NaN with no line |
| `point_splitting_mhz` | (N,) | Refit centre separation of a resolved doublet |
| `point_step_mhz`, `point_noise_sigma`, `point_lorentz_num_fits` | (N,) | Grid step, per-point noise, display's fit count |
| `group_length` | (M,) | One group per `qubit_length` (one group, NaN, with `Gauss=True`) |
| `group_status` | (M,) str | `ok`, `resolution-limited`, `insufficient` or `failed` |
| `group_a`, `group_c`, `group_fwhm0`, `group_fwhm0_err`, `group_n_points` | (M,) | Saturation fit FWHM^2 = a + c gain^2, FWHM_0 = sqrt(a) |
| `group_n_blended` | (M,) | Lines left out of the fit as merged doublets |
| `group_t2star_lower_us`, `group_fourier_fwhm_mhz` | (M,) | 1/(pi FWHM_0) when `ok`; the drive's 1/T |
| `group_recommended_gain`, `group_highest_unbroadened_gain` | (M,) | See below |
| `group_splitting_min_mhz`, `group_splitting_max_mhz` | (M,) | Doublet splitting range over the group |

Missing values are NaN (a point with no line above the noise, a display that raised). The
per-point h5 records are unchanged.

## Analysis

Per spectrum: as in [two_tone_spec](two_tone_spec.md#analysis). Across the grid
(`qicklab.analysis.spectroscopy.gain_sweep_point` per point, `summarize_gain_length_sweep`),
to separate power broadening from a real doublet and to bound T2*:

1. **SNR.** Each selected peak's height over the off-resonant edge baseline, in units of the
   per-point noise (`spectrum_noise_floor`, the partner gate's estimate). A peak is used only at
   SNR >= 5 (`GAIN_SWEEP_MIN_SNR`).
2. **Width refit.** display's Lorentzian window (`fit_window_mhz`, 0.5 MHz) biases lines wider
   than about 1 MHz and rejects them above about 2 MHz, exactly the high-gain lines the
   saturation fit needs, so the summary refits each used peak with a window grown to 3 FWHM
   (`GAIN_SWEEP_WINDOW_FWHM`), capped at `SpecSpan`. display's own fits and the per-point
   records are not changed. Two used peaks are a doublet only if the trace dips 4 noise sigmas
   (`GAIN_SWEEP_VALLEY_SIGMA`) below the lower one between them; then both are fitted jointly
   (two Lorentzians on one offset) and the splitting is reported. Otherwise the second peak is
   a noise maximum on the flank of one broad line (display's `prominent_ratio` 0.1 picks such
   maxima at high gain) and only the taller one is refitted. A width is censored when the fitted
   data reach less than 2 FWHM beyond the centre (outer side for a doublet), e.g. a line wider
   than the span. Per point the narrower uncensored line is the candidate for the fit.
3. **Merged doublets.** A doublet resolved at low gain merges at high gain: the branches
   broaden until the valley disappears, and the single Lorentzian refitted over the pair is
   about splitting + branch FWHM wide. That width is not a branch width and would pull FWHM_0
   down and c up. So in a group with a resolved doublet at any gain, a single-line point whose
   width is at least the group's smallest splitting (`GAIN_SWEEP_BLEND_SPLITTING` = 1) is
   marked `blended` and left out of the fit and the recommendation. A group with no resolved
   doublet keeps all its lines. A doublet never resolved at any gain of a group cannot be
   told from one broad line and is fitted as one.
4. **Saturation fit,** per `qubit_length`: FWHM^2 = a + c gain^2 with a, c >= 0, weighted by
   the refit width errors, on at least 3 unblended lines (else `insufficient`). FWHM_0 = sqrt(a), its error
   from the fit covariance. With `Gauss=True` the lengths are pooled (the length loop repeats
   identical spectra).
5. **T2* bound.** Status `ok` and T2* >= 1/(pi FWHM_0) (MHz in, us out) only when FWHM_0 is
   above 3 grid steps (`GAIN_SWEEP_RESOLUTION_STEPS`; 0.3 MHz on the 201-point, 10 MHz half-span
   grid) and above the drive's Fourier width 1/T (T = `qubit_length`, or 4 sigma for a Gaussian).
   Otherwise `resolution-limited`: FWHM_0 is set by the grid or the pulse, not by the qubit, and
   no bound is quoted. FWHM_0 includes every zero-power width (T1, dephasing, inhomogeneous,
   residual drive), so it bounds T2* from below only.
6. **Recommendation** (printed and saved, never written back to the device): the smallest gain
   whose line has SNR >= 5 and FWHM <= 1.2 FWHM_0 (`GAIN_SWEEP_BROADENING`), and the highest such
   gain (most signal without measurable broadening). For a `resolution-limited` group the
   reference width is the larger of FWHM_0 and the narrowest measured line. A parity doublet is
   resolvable at a gain when its splitting there exceeds the line FWHM; compare
   `point_splitting_mhz` with `point_fwhm_line`.

## Findings & notes

- Purpose (from the legacy runner): nested gain x `qubit_length` sweep; `qubit_gain` and
  `qubit_length` appear in every saved plot title for identification.
- "qubit_length 10 was best for Q4" (legacy comment; device and date not recorded).

## Known issues

- With `Gauss=True` the length loop is redundant (identical spectra per length).
- All points go to the same `QubitSpecFF` folder as ordinary spectra; nothing in the
  filename marks them as part of a grid (only the config/title do). The summary npz lists
  the grid in run order, so its rows match the point files by time.
- An aborted grid (Ctrl-C, an exception) writes no summary.
