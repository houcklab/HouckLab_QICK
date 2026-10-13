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
| `..._dataRotatedI_Fit.png` | rotated I with the fit; legend has T2*, frequency, and whether the FFT frequency was used |
| `..._dataFFT.png` | FFT of the rotated trace, peaks and the used frequency |
| `..._data.json` | config |

Fit results live only on the instance (`osc_fit`, `env_fit`) and are **not** saved. Plots
are never shown (`plotDisp=False`).

## Analysis

1. Rotate the IQ trace so its **mean** lies on +I; take `y = Re`.
2. FFT of `y - mean(y)`; peaks (DC excluded) with prominence >= 0.25 x the largest, sorted by height.
3. Fewer than two FFT peaks: 1-frequency fit `A exp(-t/T2) cos(2 pi f t + phi) + C`, f
   seeded at the top FFT peak (0.05 MHz if none).
   Two or more: a 2-frequency fit (shared T2, f1 < f2 from the two highest FFT peaks) and
   a 1-frequency fit at f1; the 2-frequency model is kept only if `RSS2 < 0.85 * RSS1`.
4. Bounds: `A` in [0, 10 |A0|], T2* in [1, 1e5] us, f in [0, 2] MHz, `phi` in
   [-2 pi, 2 pi], `C` within the data range +- |A0|. T2* start value max(0.7 x span, 1 us).
5. Reported frequency: the FFT frequency is used (marked "USED") when there is a single
   FFT peak or the top peak is more than `fft_peak_dominance` = 2.5 x the second;
   otherwise the fitted f (or f1).
6. An envelope fit on |IQ| (exponential vs Gaussian, lower RSS wins) is computed and kept
   on `env_fit`, but not plotted or saved.

FFT resolution is `1 / (T2_expts * T2_step)` = 0.1 MHz with the defaults; the fit
frequency is capped at 2 MHz, so keep `freq_shift` plus the expected detuning below that
and well above the FFT resolution.

## Findings & notes

- Tuning constants (current behaviour): FFT prominence 0.25 of max; 2-tone accepted only if
  `rss2 < 0.85 * rss1`; FFT frequency reported when the dominant peak is > 2.5x the second;
  frequency bounds [0, 2] MHz; T2* bounds [1, 1e5] us.
- Detuning is set with `freq_shift`, not with `phase_step` (which the recipe fixes at 0).

## Known issues

- `flattop_length` is ignored: the pi/2 pulses are always plain Gaussians at `pi2_gain`. If
  `pi2_gain` was calibrated for a flat-top pulse the rotation angle is wrong.
- No PMOD trigger is fired (T1 and T2E fire one).
- The rotation aligns the centroid, not the oscillation axis; the fringes can end up partly
  in Q and fit poorly.
- T2* below 1 us cannot be fitted (lower bound).
- The 1-frequency path is not guarded: a `curve_fit` failure raises out of display (before
  saving). auto_coherence calls this display too.
- The wait is edge to edge, and the x axis is correct only for `start = 0` (always the
  case from the recipe).
- The FFT figure uses figure number `figNum + 2` (skips `+1`); cosmetic.
