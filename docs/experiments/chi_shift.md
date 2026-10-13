# chi_shift

Class `ChiShift` (see `qicklab.experiments.chi_shift`). Regime **A**.

## What it measures

The dispersive shift: a resonator transmission sweep taken twice at every frequency, once
with the qubit in |g> and once after a pi pulse. chi is reported as
`f_min(|1>) - f_min(|0>)`, the difference of the two transmission minima. Needs a
calibrated pi pulse ([amplitude_rabi](amplitude_rabi.md)).

## Pulse sequence

Python loop over frequency; at each point two `AveragerProgram`s (`pulse_01 = False`,
then `True`). No PMOD trigger.

```
           0.05 us  t=0.1 us
qubit_ch  __|_______[ pi: Gauss 4 sigma, pi_gain ]______        (pulse_01 = True only)
                                            |<- 0.05 us ->|
res_ch    _______________________________________________[==== length ====]___
ADC 0     _______________________________________________|<-off->|## readout_length ##|__ 10 us __ cav_relax_delay (30 us)
                                                                     + (relax_delay - cav_relax_delay) if pulse_01
```

| Item | Value |
|---|---|
| Pi pulse | `qubit_ch`, freq `qubit_freq`, gain `pi_gain`, Gaussian sigma `sigma`, 4 sigma long, phase 90 deg; flat-top (phase 0) if `flattop_length` is set |
| Readout | ADC 0 only, tone at the swept frequency, `pulse_gain`, phase 0 |
| Wait | ground-state run: 30 us (`cav_relax_delay`); pi run: total `relax_delay` |
| Grid | centre `pulse_freq + cavity_shift`; `start = centre - TransSpan`, `step = 2*TransSpan/TransNumPoints`, `TransNumPoints` points: centre - span ... centre + span - step (half-open) |

## How to run

```python
PLAN = [R.amplitude_rabi(), R.chi_shift()]      # regime A; pi pulse from the device qubit
PLAN = [R.chi_shift(cavity_shift=-0.3, trans_span=0.5)]
```

The pi pulse uses the device values of `qubit_pulse` (gain, sigma, flat-top, frequency).

## Parameters

| Name (legacy key) | Legacy default | Units | Meaning |
|---|---|---|---|
| `reps` | 10 | shots | Hardware averages per program (the only averaging, see Known issues) |
| `rounds` | 100 | - | Ignored: the program forces `rounds = 1` |
| `TransSpan` | 1 | MHz | Half-span around the centre |
| `TransNumPoints` | 101 | - | Number of points |
| `cavity_shift` | 0.2 | MHz | Offset of the sweep centre from `pulse_freq` |
| `relax_delay` | 4000 | us | Total wait after the pi-pulse run |
| `pi_gain`, `sigma`, `flattop_length`, `qubit_freq` | device | DAC, us, us, MHz | Pi pulse |

## Outputs

`path = "ChiShift"`. Files under `<outerFolder>ChiShift/ChiShift_<date>/`:

| File | Content |
|---|---|
| `..._data.h5` | `fpts` (N,) MHz; `results_ground`, `results_01` (1, n_adc, 2, N) |
| `..._data.png` | \|S21\| for both states (GHz axis), minima marked; chi in the title |
| `..._data.json` | config (with `pulse_freq` = last sweep point, `pulse_01 = True`, `rounds = 1`) |

chi is printed and put in the title only; it is **not** saved in the h5.

## Analysis

`argmin(|I + iQ|)` for each trace (ADC 0), converted to GHz with `cavity_LO`; chi =
difference in MHz. No fit. Resolution is the grid step (`2*TransSpan/TransNumPoints` =
0.0198 MHz with the defaults). Assumes the resonator is a dip; a peak-type resonator
gives meaningless chi.

## Findings & notes

- The sweep is half-open (`start + step*arange(expts)`, excludes `centre + span`), unlike
  the inclusive `linspace` grid of [transmission_fit](transmission_fit.md).

## Known issues

- `rounds` from the recipe has no effect: the program sets `rounds = 1` while building,
  so each state is averaged over `reps` shots only (10 by default).
- The program reads `qubit_freq`, while the step supplies `f_ge`; it works only because the
  regime-A base config already holds `qubit_freq` = the device qubit frequency. A
  calibrated `f_ge` override does not reach the pi pulse.
- No PMOD trigger is fired around the pi pulse (Rabi/T1 fire one). If pin 0 gates the drive
  path on your setup, the pi pulse is blocked.
- The figure is not closed when `plotDisp=False` (one figure leaks per run).
