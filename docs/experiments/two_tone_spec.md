# two_tone_spec

Class `QubitSpecSliceFF` (see `qicklab.experiments.qubit_spec`); projection and peak
helpers in `qicklab.analysis.iq` / `qicklab.analysis.spectroscopy`. Regime **A**.

## What it measures

Two-tone (pulsed) qubit spectroscopy: a qubit drive is swept in frequency around the
device qubit frequency and the resonator response is read after each drive pulse. The
display projects the IQ trace onto its signal-bearing axis, picks up to two peaks (a
charge-parity doublet shows as two) and fits a Lorentzian to each. Use it to find f_ge, to
see whether the qubit is split by charge dispersion, and to set spectroscopy power.

## Pulse sequence

`RAveragerProgram`; the qubit frequency is a register sweep (`expts` points in one
program). No PMOD trigger.

```
              sync  t=1 us
qubit_ch  ____|____[ drive @ f: const qubit_length, gain   | or Gauss 4*sigma, phase 90 ]____
                                                            |<- 0.5 us ->|
res_ch    _______________________________________________________________[==== length ====]___
ADC 0,1   _______________________________________________________________|<-off->|## readout_length ##|
                                                                                  ... 10 us ... relax_delay
```

| Item | Value |
|---|---|
| Qubit drive | `qubit_ch` (gen 1). `Gauss=False`: const pulse, `qubit_length` us, phase 0. `Gauss=True`: Gaussian, sigma `sigma`, length 4 sigma, phase 90 deg. Gain = recipe `gain` |
| Readout | starts 0.5 us after the drive ends; tone `pulse_freq`, `pulse_gain`, phase `res_phase`, length `adc_trig_offset + readout_length`; ADC channels **0 and 1** (hard-coded) |
| Repetition | 10 us after the readout, then `relax_delay` |
| Frequency grid | `start = f_qubit - SpecSpan`, `step = 2*SpecSpan/SpecNumPoints`, `expts = SpecNumPoints`: f_qubit - SpecSpan ... f_qubit + SpecSpan - step (half-open) |

## How to run

```python
PLAN = [R.two_tone_spec()]                                   # regime A, values from the spec group
PLAN = [R.two_tone_spec(gain=1500, spec_span=2, spec_num_points=401)]
```

Most values come from the session `spec` group (`Session(spec=R.spec(...))`), shared with
[spec_gain_length_sweep](spec_gain_length_sweep.md), [trans_qubit_spec](trans_qubit_spec.md)
and the charge-dispersion steps. The sweep is centred on the device qubit frequency of
`qubit_pulse`.

## Parameters

| Name (legacy key) | Legacy default | Units | Meaning |
|---|---|---|---|
| `gain` | 800 | DAC | Drive gain actually played by this step |
| `qubit_gain` | 1000 | DAC | Spec gain in the regime-A base config; used by constant_two_tone and trans_qubit_spec, **not** by this step |
| `SpecSpan` | 10 | MHz | Half-span of the frequency sweep |
| `SpecNumPoints` | 201 | - | Number of points |
| `Gauss` | False | bool | False: const (flat) drive of `qubit_length`; True: Gaussian of `sigma` |
| `qubit_length` | 50 | us | Const drive length (used when `Gauss=False`) |
| `sigma` | 2 | us | Gaussian sigma (used when `Gauss=True`; pulse is 4 sigma long) |
| `reps` | 20 | shots | Hardware averages |
| `rounds` | 10 | - | Software repeats of the whole sweep |
| `relax_delay` | 2500 | us | Wait between shots |
| `display` | True | bool | `plotDisp` for the two figures |
| `min_sep_MHz` | 0.2 | MHz | Minimum separation for a second peak |
| `fit_window_mhz` | 0.5 | MHz | Lorentzian fit window (half-width) around each peak. Fixed at 0.5 by this step |
| `prominent_ratio` | 0.1 | - | Second peak must be >= this fraction of the highest. Fixed at 0.1 by this step |

## Outputs

`path = "QubitSpecFF"`. Files under `<outerFolder>QubitSpecFF/QubitSpecFF_<date>/`:

| File | Content |
|---|---|
| `..._data.h5` | `x_pts` (N,) MHz; `avgi`, `avgq` (2, 1, N) = [ADC, read, freq], cavity-winding corrected; display results `two_tone_peak_freqs`, `two_tone_peak_amps`, `lorentz_num_fits`, `lorentz_centers`, `lorentz_fwhm`, `lorentz_gamma`, `lorentz_amplitudes`, `lorentz_offsets`, `lorentz_r2` |
| `..._data_IQ.png` | I and Q vs drive frequency, peaks marked; title has gain and length/sigma |
| `..._data_Amp2_LorentzFits.png` | rotated IQ projection + Lorentzian fits |
| `..._data.json` | config |

The peak and Lorentzian results **are** saved (display runs before save). The attribute
`qubitFreq` (argmax of the projection, computed in acquire) is not saved. No `_data.png`
is written.

## Analysis

1. **Projection.** Only ADC 0, read 0 (`avgi[0][0]`) is used. The complex trace is centred
   on its median, rotated onto its principal axis (`theta = 0.5 * arg(sum(dev**2))`), the
   baseline is taken from the outer 15 % of points on each side (`edge_frac=0.15`), and the
   sign is chosen so the larger total excursion is positive. The qubit appears as a positive
   peak from ~0. Background: [concepts/iq_conventions.md](../concepts/iq_conventions.md).
2. **Peak pick.** Local maxima (edges included) sorted by height; the highest is peak 1;
   the next candidate becomes peak 2 if it is at least `min_sep` MHz from peak 1 and at
   least `prominent_ratio` x the height of peak 1. At most two peaks, reported in
   frequency order.
3. **Lorentzian per peak.** `y = y0 + A * gamma**2 / ((x - x0)**2 + gamma**2)` (gamma =
   HWHM, FWHM = 2 gamma) fitted within +-`fit_window_mhz` of the peak. Accepted only if
   R^2 >= 0.60, 0 < gamma < window width, centre inside the window, and at least 6 points
   in the window. Rejected fits are dropped silently (`lorentz_num_fits` tells you how many
   survived).

Display defaults when called directly (not through the step): `min_sep = 0.1` MHz,
`fit_window_mhz = 3 * min_sep`, `prominent_ratio = 0.35`. The step passes
`min_sep = min_sep_MHz` (0.2), `fit_window_mhz = 0.5`, `prominent_ratio = 0.1`.

Failure modes: with `prominent_ratio = 0.1` a noise maximum 10 % as tall as the qubit
peak becomes "peak 2"; check `lorentz_r2` and the PNG before reading a doublet. A feature
wider than about 70 % of the span leaves no off-resonant edge for the baseline.

## Findings & notes

- Use the background-subtracted principal-axis projection, not |I+iQ|. The magnitude is
  dominated by the large, noisy background quadrature and buries a qubit response that
  lies in one quadrature. Q6, 2026-06-02 (QubitSpecFF; device not recorded): the real
  feature in I at ~3054 MHz was missed in favour of Q-noise spikes at 3038 / 3069 MHz.
- Baseline from the outer edges, orientation by total excursion mass. CSTQ03 Q2,
  2026-09-02 12:03: the earlier whole-trace-median baseline with "flip if |min| > |max|"
  inverted a broad ~3753 MHz response into a dip and put both peaks on edge noise at
  3764 MHz, although I and Q both showed the bump.
- History: peak finding once used a plain argmax over the flattened array, which mixed
  both ADC channels and overran `x_pts`; it now indexes `[0][0]` (first ADC, first read).
- CSTQ03 runner notes (date not recorded): `qubit_gain` 750 works for Q5; `qubit_length`
  9.5 us worked; "500 used for charge sweeps" (whether this refers to the gain or the
  relax delay is not recorded).

## Known issues

- The step plays `gain` (800), not `qubit_gain` (1000); two keys for one knob.
- `fit_window_mhz` and `prominent_ratio` from the `spec` group are ignored by this step
  (fixed 0.5 / 0.1); the other spec steps do use them.
- Readouts are hard-coded to ADC 0 and 1 regardless of `ro_chs`; ADC 1 is acquired and
  saved but never analysed.
- The frequency grid is half-open: the last point is `f_qubit + SpecSpan - step`.
- `flattop_length` is ignored (drive is const or plain Gaussian).
- The console line "amplitude^2 = ..." actually prints the rotated projection value.
- Cavity-winding correction uses the scalar `pulse_freq` (a constant phase); harmless while
  `cavity_winding_freq = 0`.
