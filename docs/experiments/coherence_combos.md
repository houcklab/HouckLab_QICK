# coherence_combos: t1_t2e, t1_t2r_t2e

Classes `T1FF`, `T2EMUX`, `T2R` (see `qicklab.runs.coherence`). Regime **A**.

## What it measures

Back-to-back coherence sets, repeated: each repetition measures T1 and then the echo (and
Ramsey) under conditions as close in time as possible, so drifts show up as correlated
changes. Each measurement is exactly the standalone experiment; see [t1](t1.md),
[t2_echo](t2_echo.md), [t2_ramsey](t2_ramsey.md) for sequences and analysis.

| Step | Order inside one repetition |
|---|---|
| t1_t2e | T1 -> T2E |
| t1_t2r_t2e | T1 -> **T2E -> T2R** (the name lists T2R first; the run order is T1, T2E, T2R) |

## Pulse sequence

```
repetition k:   [ T1FF: pi - wait - readout ]  ->  [ T2EMUX: pi/2 - (w - pi)xn - w - pi/2 - readout ]  ->  [ T2R: pi/2 - wait - pi/2 - readout ]   (t1_t2r_t2e only)
                 then 10 s pause + soc.reset_gens()
```

Channels, trigger and readout window as on the individual pages (T1 and T2E fire the PMOD
pin-0 trigger, T2R does not).

## How to run

```python
PLAN = [R.t1_t2e()]                         # regime A; coherence + echo groups
PLAN = [R.t1_t2r_t2e(repetitions=200)]
```

## Parameters

The number of repetitions comes from the `coherence` group; the T2E part reads the `echo`
group but ignores its `repetitions`.

| Name (legacy key) | Group | Legacy default | Units | Meaning |
|---|---|---|---|---|
| `repetitions` | coherence | 1000 | - | Number of sets |
| `T1_step`, `T1_expts`, `T1_reps`, `T1_rounds` | coherence | 5, 100, 20, 20 | us, -, -, - | T1 part |
| `T2_step`, `T2_expts`, `T2_reps`, `T2_rounds` | coherence | 0.1, 100, 20, 20 | us, -, -, - | T2R part (t1_t2r_t2e) |
| `freq_shift` | coherence | 0.0 | MHz | T2R detuning (real, of the pi/2 pulses) |
| `f_virt_mhz` | coherence | None | MHz | T2R virtual detuning; None = 5 fringes over the window ([t2_ramsey](t2_ramsey.md#virtual-detuning)) |
| `relax_delay` | coherence | 3000 | us | T1 and T2R relax delay |
| `T2_max_us`, `T2_expts`, `T2_reps`, `T2_rounds` | echo | 20, 121, 25, 25 | us, -, -, - | T2E part |
| `num_pi_pulses` | echo | 1 | - | Echo pulses (odd) |
| `freq_shift` | echo | 0.0 | MHz | T2E detuning |
| `relax_delay` | echo | 500 | us | T2E relax delay |
| `rotation_angle`, `min_max` | echo | None, None | rad, [I_g, I_e] | T2E display rotation / normalisation |

## Outputs

Per repetition, the standard records of each experiment:

| Experiment | Folder (`path`) | h5 name |
|---|---|---|
| T1FF | `T1` | `..._data_Q{qubit_readout}.h5` + `I_Data.png`, `Q_Data.png` |
| T2EMUX | `T2E` | `..._data_n{num_pi_pulses}.h5` + `I_Data.png`, `Q_Data.png` |
| T2R | `T2R` | `..._data.h5` + `RotatedI_Fit.png`, `FFT.png` |

The T1 and T2E fits are saved in their h5 (`t1_fit_*`, `t2e_fit_*`; see [t1](t1.md#outputs),
[t2_echo](t2_echo.md#outputs)); the T2R fit is not ([t2_ramsey](t2_ramsey.md)). Pair records
by timestamp. `*_fit_ok` is a quality flag, not an unbiased selection: on marginal data it
drops mostly the fits that overestimate T, so a repetition series filtered on it is biased low
([t1](t1.md#analysis)); not-ok records keep their fitted values.

## Analysis

As on the individual pages. No combined analysis (no T1-vs-T2E correlation, no Tphi).

## Findings & notes

- The order inside t1_t2r_t2e is T1, T2E, T2R regardless of the name.

## Known issues

- `plotDisp` is `repetitions <= 1` and cannot be overridden (unlike t1 and t2_echo).
- If the T2E step quantisation gives `int_steps = 0`, the loop stops after the T1 of the
  first set was already saved (a T1 without its T2E partner).
- In t1_t2e, `rotation_angle: None` / `min_max: None` from the echo group are still copied
  into the T2E config (`!= False` test); T2EMUX treats None as automatic, so this is
  harmless.
- The T2R part uses figure number 4 and never sets `Qubit_number`; T2R filenames therefore
  carry no qubit suffix.
- A 10 s sleep follows every set, including the last.
