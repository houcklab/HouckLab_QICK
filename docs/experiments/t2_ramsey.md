# t2_ramsey

Class `T2R` (see `qicklab.experiments.t2_ramsey`); fit functions in
`qicklab.analysis.ramsey`. Regime **A**.

## What it measures

Ramsey dephasing time T2* and the fringe frequency: pi/2, variable free evolution, pi/2,
readout. The wait (and optionally the phase of the second pulse) is a register sweep. The
fringe frequency is the detuning between the drive (`f_ge + freq_shift`) and the qubit,
so the step also checks f_ge. The FFT-seeded fit can also resolve two frequencies, which
is how a charge-parity doublet shows up in Ramsey.

## Pulse sequence

```
qubit_ch  [ pi/2: Gauss 4 sigma, pi2_gain, phase 0 ]|<---- wait (swept) ---->|[ pi/2, phase = k * phase_step ]
res_ch    ______________________________________________________________________________|0.05 us|[== length ==]___
ADC       _____________________________________________________________________________________|<-off->|## readout_length ##|__ relax_delay
```

| Item | Value |
|---|---|
| Pulses | two identical Gaussian pi/2 pulses, `pi2_gain`, sigma `sigma`, 4 sigma long; always Gaussian (`flattop_length` is ignored) |
| Drive frequency | `f_ge + freq_shift` |
| Wait | pulse edge to pulse edge (end of first to start of second) |
| Second-pulse phase | advanced by `phase_step` (DAC phase register units) per point; the recipe sets 0 |
| PMOD trigger | none |
| Readout | 0.05 us after the second pulse; ADC on `ro_chs`; `relax_delay` after |

## How to run

```python
PLAN = [R.t2_ramsey()]                        # regime A, coherence group
PLAN = [R.t2_ramsey(freq_shift=0.5)]          # 0.5 MHz artificial detuning -> visible fringes
```

## Parameters

Group `coherence` (legacy `T1T2_params`).

| Name (legacy key) | Legacy default | Units | Meaning |
|---|---|---|---|
| `T2_step` | 0.1 | us | Wait increment |
| `T2_expts` | 100 | - | Number of waits (0 ... 9.9 us with the defaults) |
| `T2_reps` | 20 | shots | Hardware averages |
| `T2_rounds` | 20 | - | Software repeats |
| `freq_shift` | 0.0 | MHz | Detuning added to f_ge for the pi/2 pulses (the only way to set a detuning) |
| `relax_delay` | 3000 | us | Wait after each readout (shared with t1) |
| `repetitions` | 1000 | - | Records in a row (10 s pause + `soc.reset_gens()` after each) |
| `phase_step` | 0 | DAC phase units | Per-point phase advance of the second pulse (virtual detuning); fixed at 0 |
| `pi2_gain`, `sigma`, `f_ge` | device | DAC, us, MHz | Pulse |

## Outputs

`path = "T2R"`. Files under `<outerFolder>T2R/T2R_<date>/`:

| File | Content |
|---|---|
| `..._data.h5` | `x_pts` (expts,) us; `avgi`, `avgq` as returned by qick (n_adc arrays of (1, expts)); no cavity-winding correction |
| `..._dataRotatedI_Fit.png` | projected I with the fit; legend has T2* and the fitted frequency (on a failed fit: no fit curve, the title is marked "(no fit)", and `fit failed: <error>` is printed to stdout); a warning line if the fit and the FFT peak disagree by more than one FFT bin |
| `..._dataFFT.png` | FFT of the projected trace, its peaks, and the fitted frequency |
| `..._data.json` | config |

Fit results live only on the instance (`osc_fit`, `env_fit`) and are **not** saved. Plots
are never shown (`plotDisp=False`). Both dicts carry `ok` (bool); on a failed fit they are
`{'ok': False, 'error': repr(exception), ...}` (see step 7).

## Analysis

1. Project the IQ trace onto its g-e oscillation axis: `dev = sig - mean(sig)`, axis
   `ang = 0.5 * angle(sum(dev**2))` (principal axis, the same estimator as the spectroscopy
   projection, [IQ conventions](../concepts/iq_conventions.md)), `y = Re(dev * exp(-i ang))`,
   sign chosen so the first point (t = 0, about |e>) is positive. (Only the first point: the
   mean of the first 3 points goes negative for fringes with f dt in (1/4, 1/3), 2.5-3.3 MHz
   at 0.1 us steps, and the fit, seeded at phi = 0 with A >= 0, then often collapses.) `y` is
   centred on 0 and carries the full g-e contrast whatever the readout geometry; `ang` is kept
   as `osc_fit['iq_axis_rad']` and the complex projection as `osc_fit['sig_rot']`.
2. FFT of `y - mean(y)`; peaks (DC excluded) with prominence >= 0.25 x the largest, sorted by height.
3. Fewer than two FFT peaks: 1-frequency fit `A exp(-t/T2) cos(2 pi f t + phi) + C`, f
   seeded at the top FFT peak (0.05 MHz if none).
   Two or more: a 2-frequency fit (shared T2, f1 < f2 from the two highest FFT peaks) and
   a 1-frequency fit at f1; the 2-frequency model is kept only if `RSS2 < 0.85 * RSS1`.
4. Bounds come from the sampling (`dt` = mean wait step): f in [0, 0.5/dt] (Nyquist, 5 MHz
   at `T2_step` = 0.1 us), T2* in [dt/2, 1e5] us, `A` in [0, 10 |A0|], `phi` in
   [-2 pi, 2 pi], `C` within the data range +- |A0|. The FFT frequency seeds are clipped into
   the frequency bounds. T2* start value max(0.7 x span, 1 us). (With fewer than 2 points the
   old fixed f <= 2 MHz, T2* >= 1 us are used.)
5. Reported frequency (`f_report`, legend): always the fitted f (or f1 for 2f), with its
   error. The tallest FFT peak is kept as `dominant_fft_freq` only as a cross-check:
   `fft_fit_mismatch` is True, and the legend warns, when no fitted frequency is within one
   FFT bin `1 / (N dt)` of it (fit failure or aliasing).
6. An envelope fit on |IQ| (exponential vs Gaussian, lower RSS wins) is computed and kept
   on `env_fit`, but not plotted or saved.
7. A failed fit does not raise: the traceback is printed, `osc_fit` / `env_fit` become
   `{'ok': False, 'error': ...}` (`osc_fit` still holds the projection and FFT), the projected
   data and the FFT are plotted without a fit curve, and `display` returns normally.

FFT resolution is `1 / (T2_expts * T2_step)` = 0.1 MHz with the defaults; the fit
frequency can go up to Nyquist `0.5 / T2_step` (5 MHz with the defaults), so keep
`freq_shift` plus the expected detuning below that and well above the FFT resolution.

## Findings & notes

- Tuning constants (current behaviour): FFT prominence 0.25 of max; 2-tone accepted only if
  `rss2 < 0.85 * rss1`; frequency bounds [0, 0.5/dt]; T2* bounds [dt/2, 1e5] us.
- Fixed 2026-10-13: the trace used to be rotated so its **mean** lay on +I, which aligns the
  centroid, not the oscillation axis. With |g| ~ |e| at different phases (the usual dispersive
  geometry) almost all of the fringe ended up in Q and T2* pinned at the 1e5 us bound. The
  fixed bounds (f <= 2 MHz, T2* >= 1 us) made `curve_fit` raise "Initial guess is outside of
  provided bounds" whenever the tallest FFT peak was above 2 MHz (including on noise), and that
  exception escaped `display`. The legend used to report the FFT bin frequency as "USED"
  (resolution ~50-100 kHz) instead of the fitted one; the `fft_peak_dominance` kwarg is now
  ignored.
- Detuning is set with `freq_shift`, not with `phase_step` (which the recipe fixes at 0).

## Known issues

- `flattop_length` is ignored: the pi/2 pulses are always plain Gaussians at `pi2_gain`. If
  `pi2_gain` was calibrated for a flat-top pulse the rotation angle is wrong.
- No PMOD trigger is fired (T1 and T2E fire one).
- `ok` only means `curve_fit` converged: on noise-only data the fit usually succeeds and
  returns a meaningless T2*. Check `perr`. `fft_fit_mismatch` only says the fit and the
  tallest FFT peak disagree; it is not a noise detector (on pure noise it is False about
  half the time, because the fit locks onto the tallest noise peak).
- Two FFT peaks closer than one bin can still be taken as a 2f doublet (no resolvability check).
- The wait is edge to edge, and the x axis is correct only for `start = 0` (always the
  case from the recipe).
- The FFT figure uses figure number `figNum + 2` (skips `+1`); cosmetic.
