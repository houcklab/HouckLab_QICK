# transmission_fit

Class `CavitySpecFF` (see `qicklab.experiments.transmission`), hanger fit in
`qicklab.analysis.fitting`. Regime **A**.

## What it measures

Resonator transmission |S21| versus probe frequency around the current readout frequency,
followed by a hanger-model fit. The minimum of the fitted hanger curve replaces `pulse_freq`
for every later regime-A step in the same plan. Use it to find or re-centre the readout
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
| `..._data.h5` | `fpts` (N,) MHz; `results` (1, n_adc, 2, N) = [read, ro_ch, I/Q, freq]; if the display fit succeeds also `hanger_fit_popt` (5,) = [f0, Qtot, Qext, asym, offset], `hanger_fit_perr` (5,), `hanger_fit_f0_mhz`, `hanger_fit_min_freq_mhz`, `hanger_raw_min_freq_mhz`, `hanger_fit_Qtot`, `hanger_fit_Qext`, `hanger_fit_Qint`, `hanger_fit_kappa_mhz` |
| `..._data.png` | I, Q, \|S21\| vs frequency (GHz axis) with the raw minimum marked |
| `..._data_hanger_fit.png` | dB data, fit, raw and fit minima (only if the fit succeeded) |
| `..._data.json` | config; `pulse_freq` = fit minimum if the display fit succeeded, else the **last sweep point** |

Carry-over: `pulse_freq` of the session config is set to `hanger_fit_min_freq_mhz`, the
minimum of the display fit's curve (readout sits at the transmission minimum; with `asym != 0`
it differs from the `f0` parameter). It is the value saved in the h5 and marked red in
`_hanger_fit.png`. If the display fit failed, the step prints a `WARNING` and carries the raw
argmin of |S21| instead. The value persists for all following regime-A steps and is discarded
at the next switch to regime B.

## Analysis

One hanger fit runs, inside `CavitySpecFF.display(fit=True)` (printed, saved to h5, drives the
carry-over). Start point from the trace: f0 = raw minimum, Qtot = max(|f0| / (span/10), 1e3),
Qext = 1.5 Qtot, asym = 0, offset = 0.

Model (MATLAB-style hanger, on |S21| in dB):

```
S21_dB(f) = 20 log10 | 1 - (Qtot/Qext - 2i Qtot asym / (2 pi f0)) / (1 + 2i Qtot (f - f0)/f0) | + offset
Qint = | 1 / (1/Qtot - 1/Qext) |
```

Bounds: f0 inside the swept range, Qtot and Qext in [1e2, 1e9], asym in [-1e7, 1e7],
offset in [-200, 200] dB. The fit is done on the IF-style `fpts` axis, so `f0` is an
absolute frequency only while `cavity_LO = 0`.

Assumptions: a single dip in the window (hanger geometry). For a peak-type response use
[transmission_sweep](transmission_sweep.md) with `cavity_min=False`; this step always fits
a dip. Failure modes: no resonance in the window (f0 pinned to an edge), two resonances,
or a dip at the edge of the span; check the PNG before trusting the carry-over.

## Findings & notes

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

- The printed `kappa` (and `hanger_fit_kappa_mhz` in the h5) is `(f0/Qext)/1e6`: 1e6 too
  small, and it is the external (coupling) rate f0/Qext, not the total linewidth f0/Qtot.
  Compute kappa/2pi = f0/Qtot (MHz) yourself from the saved `hanger_fit_popt`.
- If the display fit fails, the saved JSON records `pulse_freq` = last sweep point, not the
  sweep centre.
- A point with zero amplitude gives `-inf` dB and breaks the fit.
- A failed display fit is reported (`Hanger fit failed: ...`, then the step's `WARNING`) but
  the step continues with the raw argmin; an accepted-but-wrong fit (f0 at a bound, Qtot >
  Qext) is not yet rejected, so check the PNG.
