# transmission_sweep

Class `CavitySpecFF` (see `qicklab.experiments.transmission`). Regime **A**.

## What it measures

The same resonator transmission sweep as [transmission_fit](transmission_fit.md), with
the same `transmission` group averaging (`reps`, `rounds`), and a carry-over chosen by the device's
`cavity_min` flag: the dip frequency (default) or the peak frequency becomes `pulse_freq`
for later regime-A steps, if it passes the
[carry-over gate](transmission_fit.md#carry-over-gate). Use it when the resonator shows up as a peak, or when you only
want "move the readout to the minimum".

## Pulse sequence

Identical to [transmission_fit](transmission_fit.md#pulse-sequence): one
`AveragerProgram` per frequency point, const resonator tone of length
`adc_trig_offset + readout_length`, ADC on `ro_chs`, 10 us sync, then `cav_relax_delay`
(30 us). No qubit pulse, no PMOD trigger.

```
res_ch  ____|[=========== const, pulse_gain, length ===========]____
ADC     ____|<- adc_trig_offset ->|#### readout_length ####|___ 10 us ___ 30 us
```

Grid: `np.linspace(pulse_freq - TransSpan, pulse_freq + TransSpan, TransNumPoints)` (inclusive).

## How to run

```python
PLAN = [R.transmission_sweep(), R.two_tone_spec()]   # regime A; spec reads at the new pulse_freq
```

`cavity_min` is a device property (`Device(cavity_min=True)`: resonator is a dip).

## Parameters

| Name (legacy key) | Legacy default | Units | Meaning |
|---|---|---|---|
| `reps` | 20 (group `transmission`) | shots | Hardware averages per program |
| `rounds` | 20 (group `transmission`) | - | Programs per point |
| `TransSpan` | 5 (from group `transmission`, key `span`) | MHz | Half-span around `pulse_freq` |
| `TransNumPoints` | 201 (group `transmission`, key `num_points`) | - | Number of points |
| `cavity_min` | True (device) | bool | True: carry the dip; False: carry the peak |

## Outputs

`path = "TransmissionFF"` (same folder as transmission_fit). Files and h5 keys are those of
[transmission_fit](transmission_fit.md#outputs): `fpts`, `results`, and the `hanger_fit_*`
keys when the display hanger fit succeeds; `..._data.png`, `..._data_hanger_fit.png`,
`..._data.json`.

Carry-over to the session config:

| `cavity_min` | New `pulse_freq` |
|---|---|
| True | `hanger_fit_min_freq_mhz`: the minimum of the fitted hanger curve if the display fit succeeded; else the raw argmin of \|S21\| (`peakFreq_min`), with a printed `WARNING` saying the raw value was carried |
| False | `peakFreq_max`: the raw argmax of \|S21\| (no fit involved) |

The candidate is written only if it passes the
[carry-over gate](transmission_fit.md#carry-over-gate): with the display fit's popt for a dip,
and for a raw argmin or a peak (sign flipped) with the half-power width (full width at half power, in grid points) as the linewidth (the
dip fit's popt is never used for a peak). On failure the reasons and metrics are printed and
`pulse_freq` is left unchanged (`Cavity frequency NOT updated: ...`). An accepted value is
printed (`Cavity frequency found at: ...`). It persists for later regime-A
steps and is discarded at the next switch to regime B.

## Analysis

`display(fit=True)` runs the hanger fit described in
[transmission_fit](transmission_fit.md#analysis) (fit in (f0, Qint, Qext, asym, offset), so
Qtot < Qext; start point from the trace: Qtot = max(|f0|/(span/10), 1e3), Qext from the dip
depth, asym 0, offset = the edge level) and stores the results and their errors in the h5. No second fit. The fit assumes a dip; with `cavity_min=False` it still runs (and may
fail harmlessly), but the carry-over uses the raw maximum, gated without the fit.

## Findings & notes

- `cavity_min = True` means "look for a dip, not a peak" (CSTQ03 setting).
- With the CSTQ03 values averaging is 20 x 20 = 400 shots per point, split over 20 programs per point; see the
  `reps` vs `rounds` note on [transmission_fit](transmission_fit.md#findings--notes).

## Known issues

- Before 2026-10 `reps`/`rounds` were hard-coded to 20/20 and the `transmission` group's
  values were ignored; the step now uses them (F84).
- Saved JSON `pulse_freq` = fit minimum if the fit succeeded, else the last sweep point.
- In the legacy runner the flag names were swapped: `RunTransmissionSweep` ran
  transmission_fit and `RunTransmissionSweeps` ran this step. Use the step names.
