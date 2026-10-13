# trans_qubit_spec

Class `QubitSpecSliceFF` (see `qicklab.experiments.qubit_spec`). Regime **A**.

## What it measures

The same [two_tone_spec](two_tone_spec.md) measurement repeated many times back to back
at fixed settings, producing a time series of qubit spectra. Use it to watch the qubit
line (or a charge-parity doublet) move or switch over minutes to hours. Despite the name,
no transmission sweep is taken.

## Pulse sequence

As [two_tone_spec](two_tone_spec.md#pulse-sequence). The differences are in which
config values are used:

```
qubit_ch  ____|____[ const qubit_length (base cfg), qubit_gain (base cfg) ]______________
res_ch    __________________________________________ 0.5 us __[==== length ====]____
ADC 0,1   _____________________________________________________|<-off->|## readout ##|__ 10 us __ relax_delay (BASE_CONFIG 3000 us)
            repeated `repetitions` times
```

| Item | Source |
|---|---|
| Drive gain | `Gauss=False`: base-config `qubit_gain` (spec group `qubit_gain`, 1000). `Gauss=True`: spec group `gain` (800) |
| Drive length | base-config `qubit_length` (spec group at session start, 50 us) |
| Frequency grid | base-config `start`/`step`/`expts` built at session start from `SpecSpan`, `SpecNumPoints` and the device qubit frequency |
| `relax_delay` | not set by the step: `BASE_CONFIG["relax_delay"]` = 3000 us |

No PMOD trigger.

## How to run

```python
PLAN = [R.trans_qubit_spec()]                       # regime A
PLAN = [R.trans_qubit_spec(repetitions=50)]
```

The number of repetitions comes from the `coherence` group (`T1T2_params["repetitions"]`
in the legacy runner), not from the spec group.

## Parameters

| Name (legacy key) | Legacy default | Units | Meaning |
|---|---|---|---|
| `repetitions` | 1000 (group `coherence`) | - | Number of spectra |
| `reps`, `rounds` | 20, 10 (group `spec`) | - | Averaging per spectrum |
| `Gauss` | False | bool | Drive shape |
| `sigma`, `gain` | 2 us, 800 | us, DAC | Used only when `Gauss=True` |
| `qubit_gain` | 1000 | DAC | Drive gain when `Gauss=False` (from the base config) |
| `qubit_length` | 50 | us | Const drive length (from the base config) |
| `SpecSpan`, `SpecNumPoints` | 10, 201 | MHz, - | Grid, frozen into the base config at session start |
| `min_sep_MHz`, `fit_window_mhz`, `prominent_ratio` | 0.2, 0.5, 0.1 | MHz, MHz, - | Display settings (all used) |

## Outputs

One standard two_tone_spec record per repetition under `path = "QubitSpecFF"`: h5 with
`x_pts`, `avgi`, `avgq`, peak and Lorentzian keys; `_IQ.png`, `_Amp2_LorentzFits.png`;
`.json`. Plots are never displayed (`plotDisp=False`). Before the loop the step prints a
sanity dump of the key config values.

## Analysis

Per spectrum as in [two_tone_spec](two_tone_spec.md#analysis). There is no built-in
time-series analysis; group files by timestamp and read `two_tone_peak_freqs` /
`lorentz_centers`.

## Findings & notes

None recorded beyond those on [two_tone_spec](two_tone_spec.md#findings--notes).

## Known issues

- `relax_delay` silently falls back to the base-config 3000 us; the spec group's
  `relax_delay` (2500) is not applied.
- The repetition count is borrowed from the `coherence` group (legacy default 1000), so
  changing the T1/T2 repetitions also changes this step.
- Drive gain depends on `Gauss`: 1000 (`qubit_gain`) for a const drive, 800 (`gain`) for a
  Gaussian. two_tone_spec uses `gain` in both cases.
