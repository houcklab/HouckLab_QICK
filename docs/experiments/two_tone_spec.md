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
   HWHM, FWHM = 2 gamma) fitted within +-w of the peak, where w = `fit_window_mhz`, or,
   when two peaks were picked, `min(fit_window_mhz, 0.5 * |peak2 - peak1|)` so that no
   window holds both lines (one Lorentzian over both lines of a doublet lands on their
   midpoint). A fit is accepted only if R^2 >= 0.60, 0 < gamma < window width, centre
   inside the window, at least 6 points in the window, and:
   - its HWHM is at least a quarter of a grid step (`MIN_FIT_GAMMA_STEPS` in
     `qicklab/experiments/qubit_spec.py`). A fit narrower than that has collapsed onto a
     single bin. Most such fits are noise maxima, but the width does not separate noise
     from line, so this gate loses some real lines and lets some noise through:
     - noise fits removed in the golden runs have HWHM between 0.003 and 0.22 step, so a
       noise fit can sit just under the cut, and one just above it is kept;
     - a genuine line narrower than about half a step often collapses the same way and is
       dropped, although its collapsed centre is still several times closer to the line
       than its bin peak. On the 0.0995 MHz Run2ToneSpec step (line at a random sub-bin
       offset, 100 trials each) the cut loses the line's fit in about 30 % of trials at
       HWHM 40 kHz and SNR 20 (kept 54 of the 75 the fit would otherwise return), about
       10 % at HWHM 40 kHz and SNR 50, about a third at HWHM 30 kHz and SNR 50 and about
       13 % at HWHM 50 kHz and SNR 20. The loss is largest midway between bins (HWHM
       40 kHz, SNR 50: 98 % kept on a bin, 79 % midway). A cut at half a step would drop
       most of these lines.

     On such coarse grids `lorentz_*` is only reported (PNG and h5 of Run2ToneSpec,
     RunChargeSweep, RunSpecGainLengthSweep); on the zero-span parity grid (0.00995 MHz
     step) a 40 kHz line is four steps wide and the gate does not touch it;
   - its centre is not on the window edge (within half a grid step of the outermost
     point in the window: the line is outside the window, not in it);
   - its centre is within `0.5 * max(min_sep, gamma)` of its seed peak bin (the gamma
     term allows for a broad line, whose flat top moves the highest bin around);
   - its centre is at least `min_sep` from an already accepted centre. The fits are taken
     tallest peak first, so the line keeps its own fit and a flank or noise maximum
     picked as peak 2 cannot displace it.

   If the clipped window gives no acceptable fit (on a coarse grid it often holds fewer
   than 6 points), the fit is retried with the full `fit_window_mhz`, under the same
   gates. Rejected fits are dropped silently (`lorentz_num_fits` tells you how many
   survived). The accepted fits are saved in frequency order.
4. **Doublet choice** (`choose_two_tone_freqs_from_lorentz_or_peaks`, used by the
   charge-dispersion steps and, through `pick_parity_drive_freq`, by
   [zero_span_parity](zero_span_parity.md)). Lorentzian centres closer than `min_sep` are
   first merged into their mean. Then: two centres (`two_lorentzian_centers`); else one
   centre plus a peak of `find_two_tone_peaks` at least `max(min_sep, gamma)` from it,
   gamma being the widest accepted fit's HWHM, since a bin peak inside the fitted line
   belongs to that line (`one_lorentzian_center_plus_peak`); else the two highest
   `find_two_tone_peaks` peaks (`two_highest_peaks`). Two frequencies are returned only
   when they are at least `min_sep` apart. Otherwise the result is a single frequency
   with `peak_sep = None` and source `single_line_unresolved`: a single line, or a
   doublet split by less than `min_sep`, which this selection cannot resolve by design.
   Two frequencies whose weaker line is not significant (below) also come back as one,
   source `partner_not_significant`.

   **Partner significance gate.** Two frequencies that pass the separation test are then
   tested for significance: each gets the height of the projected trace at its nearest
   bin above the off-resonant baseline, in units of the per-point noise sigma
   (`spectrum_noise_floor`). The baseline is the median of the outer 15 % of each side of
   the span, the one `project_iq_signal` subtracts (so about 0). The whole-trace median
   (`estimate_noise_floor`) is not used: the Lorentzian wings of broad lines lift it (a
   200 kHz HWHM doublet split by 0.6 MHz at SNR 10 then read about 5 sigma and was rejected
   in half the trials). Sigma is `estimate_noise_floor`'s MAD sigma of the first
   differences divided by sqrt(2); the MAD of the trace itself is inflated by the wings in
   proportion to the line height, so a 100 kHz HWHM doublet would read about 4 sigma at
   any SNR. The weaker of the two heights is `partner_snr`. If it is below
   `min_partner_snr` (`MIN_PARTNER_SNR` = 5 in `qicklab/analysis/spectroscopy.py`; `None`
   or 0 switches the gate off) it is taken to be a noise maximum and the result is the
   stronger frequency alone, `peak_sep = None`, source `partner_not_significant`.
   `partner_snr` is returned whenever two frequencies reached the gate. Limits: because
   differencing removes slow drift, sigma is the point-to-point noise, and a broad
   baseline wobble can still pass as a line; lines broad enough that their wings fill the
   outer 15 % of the span lift the edge baseline too and read low (a 300 kHz HWHM doublet
   split by 1.0 MHz on the 2 MHz span, each line 0.2 MHz from the outer 15 %, reads about
   0.55 x its SNR): centre the span on the doublet and make it wide enough. The gate is provisional until checked on a real CSTQ03 doublet and single line.

   Operating curve, measured through the real display on the ZSP grid (2 MHz span, 201
   points, `min_sep` 0.2, `fit_window_mhz` 0.5, `prominent_ratio` 0.1), lines offset at
   random by up to 5 kHz, IQ rotated by a random phase, 200 trials per case (so about
   +-3 %). SNR = line peak height over the per-point noise sigma of the projected trace;
   `partner_snr` of a genuine equal-height line comes out at about 0.85-1.0 x its SNR
   (nearest bin).
   - False doublets (a single line, a 0.15 MHz doublet below `min_sep`, or a noise-only
     trace reported as two lines). Without the gate (`min_partner_snr=None`) such a trace
     is paired with a noise maximum at least `min_sep` away whenever
     `find_two_tone_peaks` reports one (source `one_lorentzian_center_plus_peak`, or
     `two_highest_peaks` on noise only):

     | Case | SNR 6 | 8 | 10 | 15 | 20 |
     |---|---|---|---|---|---|
     | single line, HWHM 40 kHz, no gate | 99 % | 89.5 % | 54.5 % | 2.5 % | 0 % |
     | single line, HWHM 100 kHz, no gate | 97 % | 81.5 % | 39 % | 1 % | 0 % |
     | single line, HWHM 200 kHz, no gate | 90.5 % | 72 % | 31.5 % | 0 % | 0 % |
     | 0.15 MHz doublet, HWHM 40 kHz, no gate | 96 % | 75 % | 23 % | 0 % | 0 % |
     | 0.15 MHz doublet, HWHM 100 kHz, no gate | 70.5 % | 12.5 % | 1 % | 0 % | 0 % |
     | noise only (no line), no gate | 99.5 % | 99 % | 100 % | 99 % | 98.5 % |
     | any of the above, gate at 5 | 0 % (1 %) | 0 % (1.5 %) | 0 % | 0 % | 0 % |

     In brackets: the HWHM 200 kHz single line, the only case with false doublets at 5
     (5 of the 6000 trials): its partner is a noise maximum on the line's own shoulder,
     `max(min_sep, HWHM)` from the centre. The noise maxima taken as partners have a
     median `partner_snr` of 1.4-2.6 (3.9 beside a 100 kHz line at SNR 15). At a threshold
     of 4, 47 of the 6000 trials came out as doublets (up to 7 % for the 200 kHz single
     line); at 6, one.
   - Genuine doublets, equal heights, gate at 5 (accepted with both centres within
     max(25 kHz, HWHM/4) of the true lines; split 0.3, 0.45 and 0.6 MHz for 40 and
     100 kHz, 0.6 MHz for 200 kHz, 1.0 MHz for 300 kHz):

     | HWHM | SNR 6 | 8 | 10 | 15 | 20 |
     |---|---|---|---|---|---|
     | 40 kHz | 64.5-73 % | 98-99.5 % | 100 % | 100 % | 100 % |
     | 100 kHz | 55.5-66 % | 89.5-100 % | 99-100 % | 100 % | 100 % |
     | 200 kHz | 53 % | 94.5 % | 99.5 % | 100 % | 100 % |
     | 300 kHz (wings reach the edges) | 3 % | 21 % | 64.5 % | 100 % | 100 % |

     Without the gate the same cases are accepted in 99-100 % of trials at every SNR
     shown, except the blended 0.3 MHz doublet at 100 kHz HWHM (66.5 % at SNR 6, 89.5 %
     at SNR 8; 55.5 % and 89.5 % with the gate) and the broad lines at SNR 6 (79.5 % at
     200 kHz, 86.5 % at 300 kHz). A 100 kHz doublet split by 0.6 MHz off-centre (upper
     line 0.3 MHz from the span edge) is accepted in 41 %, 95 % and 100 % of trials at
     SNR 6, 8 and 10. With the weaker line half as tall (HWHM 40 kHz, SNR of the taller
     line; split 0.3 and 0.6 MHz) the gate accepts 4-4.5 % at SNR 6, 20-20.5 % at 8,
     47.5-48 % at 10, 98-99 % at 15 and 100 % at 20: what counts is the weaker line,
     which needs an SNR of about 7.5 to be accepted in 90 % of trials or more. With the
     whole-trace median as the baseline instead, the same trials give 1 false doublet in
     6000, but the 200 kHz doublet is accepted in only 47 % of trials at SNR 10 and the
     300 kHz one in 58.5 % at SNR 15.

   So below an SNR of about 8 for the weaker line (10 for blended doublets, 15 for lines
   whose wings reach the span edges) a genuine doublet is often reported as
   `partner_not_significant`: average more or raise the drive gain rather than lower the
   threshold.

   Accuracy (synthetic Lorentzian doublets, SNR 20, `min_sep` 0.2, `fit_window_mhz` 0.5,
   `prominent_ratio` 0.1, 0.01-0.04 MHz grids): for splits of about 2.5 HWHM and more,
   both centres nearly always come out within HWHM/4 of the true lines (within 10 kHz for 40 kHz HWHM
   lines split by 0.3 MHz or more, and for 100 kHz HWHM lines split by 0.6 MHz). Near a
   split of 2 HWHM each window still holds the other line's tail, and both centres come
   out about 0.2 HWHM too close together (30 kHz for a 0.3 MHz split at 150 kHz HWHM).
   Below that the result is mostly `single_line_unresolved`. A joint two-Lorentzian fit
   would remove the bias; it is not implemented.

Display defaults when called directly (not through the step): `min_sep = 0.1` MHz,
`fit_window_mhz = 3 * min_sep`, `prominent_ratio = 0.35`. The step passes
`min_sep = min_sep_MHz` (0.2), `fit_window_mhz = 0.5`, `prominent_ratio = 0.1`.

Failure modes: with `prominent_ratio = 0.1` a noise maximum 10 % as tall as the qubit
peak becomes "peak 2" of the display (the step-4 doublet choice drops it unless it stands
5 sigma above the noise); check `lorentz_r2` and the PNG before reading a doublet. A feature
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
