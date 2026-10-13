# t2_echo

Class `T2EMUX` (see `qicklab.experiments.t2_echo`). Regime **A**.

## What it measures

Echo dephasing time T2E with `num_pi_pulses` refocusing pulses: one pi pulse is a Hahn
echo, more give a CPMG train. Low-frequency noise that limits T2* is refocused, so
T2E >= T2* and the comparison with [t2_ramsey](t2_ramsey.md) tells you how much of the
dephasing is slow. The class name says MUX but the readout is not multiplexed.

## Pulse sequence

n = `num_pi_pulses`. Every wait has the same length `w`; the swept quantity on the x axis
is the total free evolution `(n + 1) * w`.

```
qubit_ch  [pi/2 X]|<- w ->|[pi Y]|<- w ->|[pi Y]| ... |<- w ->|[pi/2 X]|0.05 us|
PMOD 0    ^trig          ^trig          ^trig              ^trig
res_ch    ______________________________________________________________________[== length ==]___
ADC       ______________________________________________________________________|<-off->|## readout_length ##|__ relax_delay
                                                       (n pi pulses, n + 1 waits)
```

| Item | Value |
|---|---|
| pi/2 pulses | `pi2_gain`, phase 0 deg (first one at t = 0.01 us) |
| pi pulses | `pi_gain`, phase 90 deg (CPMG: refocusing axis perpendicular to the pi/2 axis) |
| Pulse shape | Gaussian sigma `sigma`, 4 sigma long; flat-top when `flattop_length` is set |
| Drive frequency | `f_ge + freq_shift` |
| Waits | pulse edge to pulse edge; each wait register grows by `us2cycles(step / (n + 1))` per point |
| PMOD trigger | pin 0 before every pulse, width `trig_buffer_start + trig_buffer_end + 4 sigma (+ flattop_length)` |
| Readout | 0.05 us after the last pi/2; `relax_delay` after the readout |

### Step quantisation

The step quantises the total-time increment so that each of the n + 1 waits is a whole
number of tProc cycles (1 cycle = 0.00232515 us = 1 / 430.08 MHz):

```
int_steps = T2_max_us // (0.00232515 * (n + 1) * T2_expts)
step      = 0.00232515 * (n + 1) * int_steps          # us, total free evolution per point
```

With the defaults (`T2_max_us` 20, `T2_expts` 121, n = 1): `int_steps` = 35,
`step` = 0.16276 us, last point 19.53 us. If `int_steps` is 0 (too many points for the
time) the step prints `Step size is 0!` and measures nothing.

## How to run

```python
PLAN = [R.t2_echo()]                                    # regime A, echo group
PLAN = [R.t2_echo(num_pi_pulses=3, t2_max_us=60)]       # CPMG-3
```

`Session(echo=R.echo(...))` sets the shared group (also read by the combos and
interleaved_coherence).

## Parameters

Group `echo` (legacy `T2E_params`).

| Name (legacy key) | Legacy default | Units | Meaning |
|---|---|---|---|
| `T2_max_us` | 20 | us | Target maximum total free evolution (actual max is quantised down) |
| `T2_expts` | 121 | - | Number of points |
| `T2_reps` | 25 | shots | Hardware averages |
| `T2_rounds` | 25 | - | Software repeats |
| `num_pi_pulses` | 1 | - | Refocusing pulses; must be odd (not enforced) |
| `freq_shift` | 0.0 | MHz | Added to f_ge |
| `relax_delay` | 500 | us | Wait after each readout |
| `rotation_angle` | None | rad | Fixed IQ rotation; None = automatic |
| `min_max` | None | [I_g, I_e] | Normalise rotated I to population; None = off |
| `repetitions` | 3000 | - | Records in a row (10 s pause + `soc.reset_gens()` after each) |
| `plotDisp` | `repetitions <= 1` | bool | Show the figures (explicit value wins) |
| `pi_gain`, `pi2_gain`, `sigma`, `flattop_length`, `f_ge` | device | | Pulses |

## Outputs

`path = "T2E"`. Files under `<outerFolder>T2E/T2E_<date>/`:

| File | Content |
|---|---|
| `..._data_n{num_pi_pulses}.h5` | `x_pts` (expts,) us (total free evolution); `avgi`, `avgq` as returned by qick (no cavity-winding correction); `qfreq` = f_ge |
| `..._dataI_Data.png` | rotated (or normalised) I with the fit; title `Num Pulses: n ; ... T2E = x +- y us` |
| `..._dataQ_Data.png` | rotated Q |
| `..._data.json` | config |

The T2E fit is **not** saved (title only).

## Analysis

Same as [t1](t1.md#analysis): rotation by `rotation_angle` or by the Q-range-minimising
phase (200-point grid over [0, pi]); optional `min_max` normalisation; fit
`a exp(-t/T) + c` with start `a = I[0] - I[-1]`, `c = I[-1]`, T at the point closest to
`a/2.6 + c`. The x axis is the total free evolution, so the fitted T is T2E directly.
Assumes an exponential echo decay; a Gaussian-shaped decay (1/f noise) is fitted with an
exponential anyway.

## Findings & notes

- `num_pi_pulses` must be odd (CSTQ03 runner rule, repeated in the auto_coherence
  defaults). The code does not enforce it and nowhere records why; treat even values as
  untested.
- The 0.00232515 us constant is one tProc clock cycle (430.08 MHz). The step must be an
  integer multiple of (n + 1) cycles so all pulses stay on the cycle grid; the same
  constant is used by [auto_coherence](auto_coherence.md). On a board with a different tProc
  clock the constant must change (it is not read from soccfg); see
  [concepts/timing_and_units.md](../concepts/timing_and_units.md#t2e-step-quantisation).
- Phase convention: pi/2 at 0 deg, pi at 90 deg (CPMG).

## Known issues

- An even `num_pi_pulses` runs without warning.
- When `int_steps` is 0 the standalone step stops on the first repetition without
  measuring; in [coherence_combos](coherence_combos.md) the T1 of that pair has already
  been saved.
- The waits are pulse edge to pulse edge, not pulse centre to centre (the same convention
  that was found and fixed in ModifiedRamsey on 2026-07-28), so the true free evolution
  differs from `x_pts` by the pulse lengths.
- `x_pts = start + i * step` matches the programmed total wait only for `start = 0` and a
  quantised step (both guaranteed by the recipe).
- If the cfg contains `rotation_angle` but not `min_max`, acquire raises `KeyError`.
- The fit is not guarded; a failure raises before saving.
