# transmission_fit

Class `CavitySpecFF` (see `qicklab.experiments.transmission`), hanger fit in
`qicklab.analysis.fitting`. Regime **A**.

## What it measures

Resonator transmission |S21| versus probe frequency around the current readout frequency,
followed by a hanger-model fit. If the trace passes the [carry-over gate](#carry-over-gate),
the minimum of the fitted hanger curve replaces `pulse_freq` for every later regime-A step in
the same plan. Use it to find or re-centre the readout
resonator at the start of a session. For the same sweep with fixed averaging that can also
track a peak (`cavity_min=False`), see [transmission_sweep](transmission_sweep.md).

## Pulse sequence

One `AveragerProgram` per frequency point (Python loop; the frequency is not a register
sweep). Only the resonator generator is used; no qubit pulse, no PMOD trigger.

```
             sync 200 cyc
res_ch  ____|[=========== const, pulse_gain, length = adc_trig_offset + readout_length ===========]____
ADC     ____|<- adc_trig_offset ->|################ readout_length ################|______________
                                                                       ... 10 us ... cav_relax_delay (30 us)
```

| Item | Value |
|---|---|
| Generator | `res_ch` (gen 0), const pulse, phase 0, gain `pulse_gain` (device readout gain) |
| Readout | every `ro_chs` entry (CSTQ03: `[0]`), window `readout_length` us, ADC triggered `adc_trig_offset` us after the tone starts |
| After measure | 10 us sync, then `cav_relax_delay` (30 us, fixed in the regime-A config) |
| Averaging | `reps` in hardware per program x `rounds` programs per point |

Frequency grid: `np.linspace(pulse_freq - TransSpan, pulse_freq + TransSpan, TransNumPoints)`,
inclusive at both ends. `TransSpan` is the **half**-span.

## How to run

```python
PLAN = [R.transmission_fit()]                       # regime A
PLAN = [R.transmission_fit(reps=400, rounds=1)]     # same shots, 20x fewer programs (see Findings)
```

Span and number of points come from the session `transmission` group
(`Session(transmission=R.transmission(span=5, num_points=201))`), because they are baked
into the regime-A base config.

## Parameters

| Name (legacy key) | Legacy default | Units | Meaning |
|---|---|---|---|
| `reps` | 20 | shots | Hardware averages inside one tProc program |
| `rounds` | 20 | - | Programs per point, averaged in software |
| `span` (-> `TransSpan`) | 5 | MHz | Half-span of the sweep around `pulse_freq` (group `transmission`) |
| `num_points` (-> `TransNumPoints`) | 201 | - | Number of frequency points (group `transmission`) |
| `cav_relax_delay` | 30 | us | Wait after each readout (regime-A config, not a recipe knob) |
| `pulse_freq` | device readout frequency | MHz | Sweep centre (or the value carried over from an earlier step) |
| `pulse_gain` | device readout gain | DAC | Probe amplitude |

## Outputs

`path = "TransmissionFF"`. Files under `<outerFolder>TransmissionFF/TransmissionFF_<date>/`:

| File | Content |
|---|---|
| `..._data.h5` | `fpts` (N,) MHz; `results` (1, n_adc, 2, N) = [read, ro_ch, I/Q, freq]; if the display fit succeeds also `hanger_fit_popt` (5,) = [f0, Qtot, Qext, asym, offset], `hanger_fit_perr` (5,), `hanger_fit_pcov` (5, 5) (the full covariance in the `hanger_fit_popt` layout; `hanger_fit_perr` is the square root of its diagonal), `hanger_fit_f0_mhz`, `hanger_fit_min_freq_mhz`, `hanger_raw_min_freq_mhz`, `hanger_fit_Qtot`, `hanger_fit_Qext`, `hanger_fit_Qint`, `hanger_fit_kappa_tot_mhz` (kappa/2pi = \|f0\|/Qtot, MHz), `hanger_fit_kappa_ext_mhz` (\|f0\|/Qext, MHz), and their 1-sigma errors `hanger_fit_Qtot_err`, `hanger_fit_Qext_err`, `hanger_fit_Qint_err`, `hanger_fit_kappa_tot_mhz_err`, `hanger_fit_kappa_ext_mhz_err` (from the full covariance, see [Analysis](#analysis)) |
| `..._data.png` | I, Q, \|S21\| vs frequency (GHz axis) with the raw minimum marked |
| `..._data_hanger_fit.png` | dB data, fit, raw and fit minima (only if the fit succeeded) |
| `..._data.json` | config; `pulse_freq` = fit minimum if the display fit succeeded, else the **last sweep point** |

Carry-over: `pulse_freq` of the session config is set to `hanger_fit_min_freq_mhz`, the
minimum of the display fit's curve (readout sits at the transmission minimum; with `asym != 0`
it differs from the `f0` parameter). It is the value saved in the h5 and marked red in
`_hanger_fit.png`. If the display fit failed, the step prints a `WARNING` and carries the raw
argmin of |S21| instead. Either candidate is written only if it passes the
[carry-over gate](#carry-over-gate); otherwise `pulse_freq` is left as it was. The value
persists for all following regime-A steps and is discarded at the next switch to regime B.

## Analysis

One hanger fit runs, inside `CavitySpecFF.display(fit=True)` (printed, saved to h5, drives the
carry-over). Start point from the trace (`hanger_startpoint`): f0 = raw minimum,
Qtot = max(|f0| / (span/10), 1e3), offset = the edge level (mean of the medians of the first
and last tenth of the points), Qext = Qtot / (1 - 10^(-depth/20)) from the dip depth below that
level (Qtot/Qext clipped to [0.01, 0.99]), asym = 0.

Model (MATLAB-style hanger, on |S21| in dB):

```
S21_dB(f) = 20 log10 | 1 - (Qtot/Qext - 2i Qtot asym / (2 pi f0)) / (1 + 2i Qtot (f - f0)/f0) | + offset
Qtot = 1 / (1/Qint + 1/Qext)
```

The fit parameters are (f0, Qint, Qext, asym, offset) (`hanger_model_db_qint`); Qtot is derived,
so Qtot < Qext always. This matters because |S21| depends on a = Qtot/Qext only through
(1 - a)^2: every dip has an unphysical twin a -> 2 - a (Qtot > Qext, same curve, same Qtot and
Qint, wrong Qext and kappa_ext) that a fit in (Qtot, Qext) could land on, and the old
Qint = |1/(1/Qtot - 1/Qext)| hid it (finding F36). Magnitude alone already fixes the dip depth
|1 - a|; this removes the twin, it does not tell under- from over-coupling. `hanger_fit_popt`
keeps the [f0, Qtot, Qext, asym, offset] layout.

Bounds: f0 inside the swept range, Qint and Qext in [1e2, 1e9], asym in [-1e7, 1e7],
offset in [-200, 200] dB. The fit is done on the IF-style `fpts` axis, so `f0` is an
absolute frequency only while `cavity_LO = 0`.

Error bars: the fit is unweighted least squares in dB, but under Gaussian IQ noise a dB point's
noise is proportional to 1/|S21|, so near a dip the plain curve_fit covariance was too small
(median |pull| ~1.8 on Qtot for Qi = 1e5, Qc = 2e4). The covariance is now the sandwich
estimator for that noise model (|S21| of the fitted curve relative to its baseline, floored at
1e-2); every saved error (`hanger_fit_perr`, the `_err` keys) is propagated from the full
covariance (Qtot and Qext correlate at rho ~ 0.7). On synthetic complex data (201 points,
1-5% IQ noise per quadrature, Qi/Qc = 1e5/2e4, 3e4/3e4, 2e4/1e5 on +-5 MHz, 200 traces each) the
median |pull| of f0, Qtot, Qint, Qext and both kappas is 0.55-0.9 (0.67 is exact) and 92-97% of
pulls fall within 2 sigma (86% for kappa_tot on the under-coupled trace at 5% noise). The
Jacobian's f0 step is 1e-6 linewidths (|f0|/Qtot), so the f0 error holds at high Q too: for
Qi = Qc = 5e5 (+-0.2 MHz) and 2e6 (Qtot = 1e6, kappa = 7 kHz, +-0.05 MHz), 1% noise, 100 traces,
the median |pull| on f0 and Qtot is 0.58-0.60 with 95-97% within 2 sigma (a step of 1e-6 |f0|
made perr_f0 1.2x and 1.9x too large there). A
1/|S21|-weighted fit would be slightly more precise but lets an unmodelled background tilt
(0.3 dB/MHz) pull it onto a broad Fano shape away from even a 20 dB dip, so the estimate stays
unweighted. Tests: `tests/test_hanger_fit.py`.

Assumptions: a single dip in the window (hanger geometry). For a peak-type response use
[transmission_sweep](transmission_sweep.md) with `cavity_min=False`; this step always fits
a dip. Failure modes: no resonance in the window (f0 pinned to an edge), two resonances,
or a dip at the edge of the span; check the PNG before trusting the carry-over.

## Carry-over gate

`qicklab.analysis.fitting.assess_resonator_fit` (and `assess_resonator_feature` when there is no
fit) decides whether the trace holds a resonator worth moving the readout to. All checks
must pass:

| Check | Rule |
|---|---|
| (a) depth | baseline median minus the lowest point within one linewidth of f0 >= 6 x 1.4826 x MAD of the baseline. Baseline = points more than 3 linewidths from f0 (at least 10 of them, which caps the linewidth of a centred resonator at about (span - 10 steps)/6, i.e. ~1.6 MHz on a +-5 MHz, 201-point sweep); with a fit, the MAD is of the fit residuals there, so a Fano-sloped baseline is not counted as noise; a straight line fitted to those baseline points is removed first, so a tilted background is not either |
| (b) linewidth | linewidth >= 2 frequency steps and < half the span; with a fit, also the data's own half-power width (number of contiguous points below half-way from the baseline to the lowest point in linear power \|S21\|^2, around the lowest point within one linewidth of f0) >= 2 steps, so a fit that settles on one bad point is rejected. Widths are counted in grid points, so a two-point run is exactly 2 steps. A real resonance narrower than 2 steps cannot be told from a spike and is rejected too: on the default +-5 MHz / 201-point grid (step 0.05 MHz) that is every kappa below 0.1 MHz, and kappa near 0.1 MHz passes only sometimes. The printed reason then says `too narrow for the grid`; raise `num_points` or narrow `span` until the step is at most kappa/2 (e.g. +-2 MHz / 401 points, step 0.01 MHz, for kappa 0.03 MHz, keeping (span - 10 steps)/6 above kappa) |
| (c) edge | f0 >= 2 linewidths from both sweep edges |

Linewidth = \|f0\|/Qtot of the display fit (`hanger_fit_kappa_tot_mhz`); for the raw argmin
(failed fit) or a raw peak it is the number of contiguous points beyond half the feature height
in linear power times the step (the full width at half power, which is the linewidth of a
Lorentzian; half the dB depth would make a deep notch look one point wide). Neither `Qtot <= Qext` (the fit always returns Qtot < Qext; a popt with Qtot > Qext is
the |S21| twin of one with Qtot/Qext -> 2 - Qtot/Qext and is judged the same) nor the fit's
`perr` (small on pure noise) is used.

If any check fails, the step prints `WARNING: no resonator dip passes the carry-over gate`, every
failed check and the metrics (`depth_sigmas`, `linewidth_steps`, `edge_linewidths`,
`n_baseline`, ...), then `Cavity frequency NOT updated`, and leaves `pulse_freq` unchanged (an
earlier good carry-over survives). A gate that raises counts as failed. The verdict is printed
only; the h5 and JSON are unchanged.

What it separates, on a +-5 MHz sweep with the display fit's start point: the checks work
together, and the depth check alone does not separate noise. Of 400 resonator-free noise traces
(0.3 dB on a flat line) at each of 201, 401 and 1001 points, none passed the gate, but most
fits reach 1-4 sigma and a few 4-6 sigma (with the start point and fit before F36, a few broad
fits also reached more than 6 sigma: 8.0 sigma at 201 points, 8.1 and 22 sigma at 401; the 22
sigma one had 3 baseline points; with the current ones none of the 1200 exceeded 5.9 sigma).
Every trace above 4 sigma failed at least two checks (baseline count, edge, linewidth or the
data's half-power width), before and after. A single point pulled 1-20 dB below a flat line was rejected in 60/60 cases, by the
data's half-power width (before that check, a fit to it passed up to 15/20 times with a
linewidth of 2.2 steps). A 2 dB dip reaches ~20 sigma under 0.1 dB noise but only 6-8 sigma
(marginal, 18/20 passed) under 0.3 dB, and a 14 dB dip over 100 sigma. Deep, near-critically-coupled notches (Qtot/Qext 0.9-1.05,
20-34 dB, minimum on a grid point, with or without a 0.8 rad Fano phase) pass with a half-power
width of about one linewidth; half-way down in dB they are one point wide, which is why the
width is measured in power. A tilted background
(0.3-1 dB/MHz) does not count as noise; but the hanger model has no slope term, and on such a
tilt `display()`'s fit itself often lands on a broad Fano shape far from the dip (3 dB dips at
0.3 dB/MHz, every dip up to 10 dB at 0.6 dB/MHz; before F36 also 6 dB dips at 0.3 dB/MHz); the gate then rejects that fit,
correctly, and `pulse_freq` is not updated. Level the background (calibrate the line, narrow the
span) if that happens. A real dip that fails is too shallow for the averaging (raise `reps`), too
wide for the span (a centred linewidth above about (span - 10 steps)/6 leaves fewer than 10
baseline points: raise `span`) or too narrow for the grid (raise
`num_points`). Tests:
`tests/test_resonator_gate.py`, `tests/test_run_transmission.py`.

## Findings & notes

- Until 2026-10 (finding F36) the fit ran in (f0, Qtot, Qext, asym, offset) from Qext = 1.5 Qtot
  and offset = 0 dB, and reported Qint = |1/(1/Qtot - 1/Qext)|. A start on the Qtot > Qext twin
  (see [Analysis](#analysis)) stayed there: on Qi = Qc = 3e4 it returned the correct f0, Qtot
  and Qint but Qext = 1e4 instead of 3e4 (kappa_ext 3x too large), with nothing printed. Its
  errors came from the unweighted-dB covariance, about 2.7x too small near the dip; Qint had no
  error at all. f0 and Qint were never wrong; Qext and kappa_ext could be.
- Until 2026-10 the step ran a second hanger fit of its own, started at
  `[center, 4.1e4, 4.3e4, asym 1e3, 0]` (copied from a MATLAB fit in Hz), and carried its `f0`.
  In MHz that asym start is ~1e6 too large (the start curve is a +65 dB peak, not a dip); on
  synthetic hangers it landed more than half a linewidth off in about a quarter of fits (up to
  the sweep edge), where the display fit did not. It was removed (finding F03); the step now
  carries the display fit's minimum.
- `reps` vs `rounds`: `reps` are hardware averages inside ONE tProc program, `rounds`
  rerun the program and average in software. `reps=400, rounds=1` and `reps=20, rounds=20`
  average the same 400 shots, but the second starts 20x more programs per point, and every
  program start risks the stale-shot-counter race (`could not broadcast input array from
  shape (26,2) into shape (20,2)`). Prefer `reps`; raise `rounds` only if the accumulation
  buffer overflows. Each point is retried up to 3 times on that transient error, with a
  fresh program and a tProc reset between attempts (see
  [concepts/averaging.md](../concepts/averaging.md)).
- The plotted axis is `(fpts + cavity_LO/1e6) / 1e3` GHz; `fpts` itself is in MHz.

## Known issues

- If the display fit fails, the saved JSON records `pulse_freq` = last sweep point, not the
  sweep centre.
- A point with zero amplitude gives `-inf` dB and breaks the fit.
- A failed display fit is reported (`Hanger fit failed: ...`, then the step's `WARNING`) and
  the step judges the raw argmin instead. The [carry-over gate](#carry-over-gate) rejects fits
  to noise, an f0 at the sweep edge and implausible linewidths, but not a clean dip of the
  wrong resonator (two resonances in the window): check the PNG.
