# amplitude_rabi

Classes `AmplitudeRabiFF` (hardware gain sweep) and `AmplitudeRabiFF_N` (software gain
sweep), see `qicklab.experiments.rabi`; cosine fit in `qicklab.analysis.fitting`. Regime **A**.

## What it measures

Qubit response versus drive amplitude at fixed pulse shape. The oscillation period in
gain gives the pi-pulse gain (`pi = P/2`). Run it after [two_tone_spec](two_tone_spec.md)
has given f_ge, and before chi_shift / T1 / T2.

The step picks the class from the device qubit:

| Device `flattop_length` | Class | Sweep |
|---|---|---|
| None | `AmplitudeRabiFF` | register sweep inside one `RAveragerProgram` |
| set | `AmplitudeRabiFF_N` | one `AveragerProgram` per gain (Python loop) |

## Pulse sequence

```
            sync   t=1 us
qubit_ch  ___|_____[ Gauss 4 sigma @ f_ge, gain = swept ]_______        (flat-top: ramp + flattop_length + ramp)
PMOD 0    ___|___[~~~~~~~~~ trig_buffer_start + 4 sigma (+ flattop) + trig_buffer_end ~~~~~~~~~]___
                 ^ t = 1 + trig_delay - trig_buffer_start us
                                                       |<- 0.05 us ->|
res_ch    _____________________________________________________________[==== length ====]____
ADC 0,1   _____________________________________________________________|<-off->|## readout_length ##|__ 10 us __ relax_delay
```

| Item | Value |
|---|---|
| Qubit pulse | `qubit_ch`, freq `f_ge`; Gaussian sigma `sigma`, length 4 sigma, phase 90 deg (`arb`); with `flattop_length`: `flat_top` style, phase 0 |
| PMOD trigger | pin 0, starts `trig_delay - trig_buffer_start` after the pulse start time, width `trig_buffer_start + trig_buffer_end + 4 sigma (+ flattop_length)` |
| Readout | 0.05 us after the pulse; tone `pulse_freq`, `pulse_gain`, phase `res_phase`; ADC 0 and 1 (hard-coded) |
| Gain grid, `AmplitudeRabiFF` | `start = 0`, `step = int(max_gain / number_of_steps)`, `expts = number_of_steps` |
| Gain grid, `AmplitudeRabiFF_N` | `np.linspace(0, max_gain, number_of_steps)`, each played as `int(g)` |

## How to run

```python
PLAN = [R.two_tone_spec(), R.amplitude_rabi()]          # regime A
PLAN = [R.amplitude_rabi(max_gain=20000, fit=True)]
```

## Parameters

| Name (legacy key) | Legacy default | Units | Meaning |
|---|---|---|---|
| `qubit_freq` (-> `f_ge`) | device qubit frequency of `qubit_pulse` | MHz | Drive frequency |
| `max_gain` | 10000 | DAC | Top of the gain sweep |
| `number_of_steps` | 101 | - | Number of gain points |
| `reps` | 10 | shots | Hardware averages |
| `rounds` | 10 | - | Software repeats (`AmplitudeRabiFF_N`: folded into reps, see Outputs) |
| `relax_delay` | 3000 | us | Wait between shots (Gaussian pulse, `AmplitudeRabiFF`) |
| `flattop_relax_delay` | 8000 | us | Wait between shots when the pulse qubit has a `flattop_length` (`AmplitudeRabiFF_N`) |
| `fit` | False | bool | Run the cosine fit in the display |
| `sigma`, `flattop_length` | device | us | Pulse shape of `qubit_pulse` |

## Outputs

`path = "AmplitudeRabi"`. Files under `<outerFolder>AmplitudeRabi/AmplitudeRabi_<date>/`.

`AmplitudeRabiFF`:

| File | Content |
|---|---|
| `..._data.h5` | `x_pts` (expts,) gain; `avgi`, `avgq` (2, 1, expts), winding-corrected **and** rotated onto ADC 0's principal axis (both ADCs by the same angle); `iq_rotation_rad`; `iq_axis_contrast_ratio`; with `fit=True` also `fit_i_popt` (4,) = [y0, A, P, phi], `fit_i_perr` (4,) (1-sigma errors of `fit_i_popt`, sqrt of the covariance diagonal), `fit_i_pi_gain`, `fit_i_pi_gain_err` (= dP/2), `fit_i_flag` (quality bitmask, see Analysis), and the same five for Q (a fit that fails leaves its keys out) |
| `..._data.png` | I and Q vs gain, fits and pi markers |
| `..._data.json` | config |
| `..._data_provenance.json` | provenance record ([architecture](../architecture.md#provenance)) |

`AmplitudeRabiFF_N`:

| File | Content |
|---|---|
| `..._data_Q{qubit_pulse}.h5` | `x_pts` (float linspace), `avgi`, `avgq` (1, 1, N), winding-corrected, **not** rotated; with `rotate=True` also `rotation_phase` (the multiplier phase: rotated = raw x exp(1j rotation_phase)); with `fit=True` the same `fit_i_*` / `fit_q_*` keys as `AmplitudeRabiFF` (popt, perr, pi_gain, pi_gain_err, flag; fitted to the rotated trace; a fit that fails leaves its keys out). Before 2026-10 no fit result was saved |
| `..._data.png` | rotated I and Q, fits, pi markers (only if inside the swept range) |
| `..._data.json` | config, with `reps = reps x rounds`, `rounds = 1`, `qubit_gain` = last gain |
| `..._data_provenance.json` | provenance record ([architecture](../architecture.md#provenance)) |

The pi gain is not written back automatically; copy it into the device file
(`Qubit(gain=...)`).

## Analysis

- `AmplitudeRabiFF`: in acquire, the IQ data (after cavity winding) are rotated by the
  principal-axis angle of the analysed read, ADC 0 (`avgi[0][0]`, the trace the display fits):
  `0.5 * angle(sum(dev**2))` of the mean-subtracted trace (`qicklab.analysis.iq.principal_axis_angle`),
  so the oscillation lands in I. The axis is defined modulo pi; the sign is fixed so that I
  increases toward the pi pulse (the mean of the first k = max(1, min(3, N // 20)) points of
  the sweep, gain ~ 0 = |g>, lies below the trace mean). This start-of-sweep reference also
  holds when the sweep spans a full period and ends back at |g>. It assumes the sweep starts
  near gain 0 (both runners use start = 0) and that those k points span less than half a Rabi
  period: up to about (N - 1) / 4 periods in the sweep (25 on the 101-point grid). Beyond that
  the sign is unreliable (the pi gain is not affected: P/2 does not depend on the sign). Both ADCs are rotated by this one angle (stored as
  `iq_rotation_rad`, in (-pi, pi]). The eigenvalue ratio of the 2x2 IQ covariance (major over
  minor variance, >= 1) is stored as `iq_axis_contrast_ratio` and printed: near 1 there is no
  oscillation and the angle is noise-driven (pure noise gives about 1.3 to 1.9 on 101 points,
  1.7 to 4.3 on 21, median to 99th percentile); below 5 a `[warn]` line is printed.
  With `fit=True`, `y0 + A cos(2 pi x / P + phi)` is fitted to I and to Q separately;
  `pi_gain = P/2`. Each fit is guarded (a failure prints and leaves the key out).
- `AmplitudeRabiFF_N`: in display (`rotate=True`), the trace is rotated by the same signed
  principal-axis angle and the ratio is printed (kept as `rotation_phase` = -angle, the
  multiplier phase, saved, and `iq_axis_contrast_ratio` on the instance, not saved), then
  fitted the same way. Each fit is guarded (a failure prints and that quadrature is drawn
  without a fit). Before 2026-10 it used the phase in [0, pi] (500-point grid) that minimised
  the peak-to-peak of Q, an estimator set by the two most extreme (noisiest) points.

The fit (`qicklab.analysis.fitting.fit_rabi_cosine`, also re-exported as
`qicklab.runs.fit_rabi_cosine`) runs four starts and keeps the one with the lowest residual:
two period seeds, the peak of the zero-padded (16x) FFT of `y - mean` (DC bin zeroed) and
the gain span `max(span, 1)`, each with `A = +-(max - min)/2`, `y0 = mean`, `phi = 0`.
The FFT seed locks onto the right period when the sweep holds one or more periods; the span
seed covers the sub-period case, where the FFT peak is poorly defined. Bounds:
`P >= 2 x` the median gain step (the Nyquist limit), `|phi| <= 4 pi`. The lower bound is
needed: on a sampled grid a period shorter than two steps is an alias of the true one with
the same residual, and without the bound the `-A` start could converge onto it (seen on
11 to 51 point grids, about 1 trace in 200 to 500: pi gain ~ 40..270, no flag). It returns
`pi_gain = P/2` and `dpi_gain = dP/2` (the covariance error); the P/2 rule needs the
response to be periodic in gain (linear drive) and does not depend on `phi`. On synthetic
traces on the default grid (0..9900, 3 % noise) the pi gain is within 3 % from 0.75 to
several periods in the sweep, and on coarse 11 to 41 point grids it is within 3 % from 1.5
periods up to 4 points per period (`tests/test_fitting_rabi.py`). On a coarse grid near one
period the error is noise-limited (a 21-point sweep at 0.75 to 1 period misses 3 % about one
time in five), so read it against `dpi_gain`.

Quality flags (printed as `[warn]` lines, returned as `flags` and the bitmask `flag_code`,
stored as `fit_i_flag` / `fit_q_flag`; they never raise):

| Bit | Condition | Meaning |
|---|---|---|
| 1 | `phi` more than 0.3 rad from 0 or pi | the fitted trace does not start at an extremum at zero gain |
| 2 | `P/2` outside `[min gain, max gain]` | the pi pulse was not reached in the sweep |
| 4 | fewer than 0.75 periods in the sweep | under-sampled: the period, and so the pi gain, is poorly constrained |

Failure modes: no visible oscillation (the fit returns a runaway period, flags 2 and 4);
too small `max_gain` (fewer than 0.75 periods, flag 4, raise `max_gain`); fewer than about 4
gain points per period (the period is poorly resolved; below 2, the Nyquist limit, the true
oscillation is under-sampled and the fit, which is bounded at 2 steps, returns an aliased
longer period: lower `step`); f_ge off resonance (reduced, faster oscillation; the fit
still returns its P/2). Before this fit (2026-10), the single start `P = span` locked onto
a wrong period from about 1.5 periods in the sweep, sometimes with a plausible in-range pi
gain, and `qicklab.runs.fit_rabi_cosine` was a grid search that reported the global
extremum (the 3 pi or 5 pi point) instead of `P/2`.

## Findings & notes

- Flat-top caveat: the flat segment of a `flat_top` pulse does NOT follow the swept gain
  register (only the ramp's `gain` register is updated; the flat part uses `gain2`). A
  register-swept Rabi is therefore invalid with flat-top pulses, which is why the step
  switches to the software sweep `AmplitudeRabiFF_N` when `flattop_length` is set.
- The principal-axis rotation in `AmplitudeRabiFF` is layered on top of the cavity-winding
  phase and stored as `iq_rotation_rad`; it does not replace the fit. Before 2026-10 the axis
  was estimated over both ADCs concatenated and its sign was arbitrary: the ADC 0 - ADC 1
  background offset then set the axis (ADC 0 at 30+40j with a 5 a.u. excursion along 120 deg
  gave 55.4 deg, 2.15 of the 5 a.u. contrast in I and 4.52 in Q), so `avgi`, `avgq` and
  `iq_rotation_rad` saved before then are not principal-axis aligned. `cavity_winding_*`
  is a frequency-dependent cable-delay correction, not a quadrature alignment.
- Below about 0.75 periods in the sweep the fitted period is poorly constrained even when
  the fit converges; the fit flags it (bit 4) rather than refusing.
- A failed cosine fit (no visible oscillation) returns a runaway period; drawing its pi
  marker would autoscale the x axis to ~1e9, so `AmplitudeRabiFF_N` hides markers that fall
  outside the swept range and prints a warning.
- If you do not see an oscillation, raise `max_gain`, and compare with the transmission
  data (CSTQ03 runner note). `max_gain` above 32767 raises ValueError: the gain register
  would wrap it ([gains](../concepts/timing_and_units.md#gains)).

## Known issues

- `step = int(max_gain / number_of_steps)` truncates: with 10000 / 101 the step is 99 and
  the sweep ends at 9900, not 10000. `AmplitudeRabiFF_N` uses `linspace` and does reach
  `max_gain`.
- The flat-top branch uses `flattop_relax_delay` (default 8000 us), not `relax_delay`.
  Before 2026-10 it was a hard-coded 8000 that no key could change (F84).
- `AmplitudeRabiFF_N` plots the axis as float `linspace` values but plays `int(g)`
  (difference < 1 DAC unit), and draws the fit only at the data points.
- `AmplitudeRabiFF_N` display errors other than the (guarded) fit raise out of the
  display; the h5 and json are saved first and the error is then re-raised
  (`finish(..., reraise=True)`, see
  [architecture](../architecture.md#display-never-loses-the-record)).
- Filename suffix `_Q{n}` uses `qubit_pulse`, whereas T1 and single shot use
  `qubit_readout`.
- In the legacy runner the drive frequency was frozen when the runner was imported;
  through the session layer it comes from the device at run time.
