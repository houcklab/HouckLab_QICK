# t2_echo

Recipe: `R.t2_echo(...)` (`qicklab.runs.recipes`; every keyword with its default and unit is in the docstring, `help(R.t2_echo)`). Session groups: [step table](../running_a_session.md#steps). Generated parameter tables come in phase 6.

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

### Refocusing condition

Each pi pulse about Y maps the in-plane phase phi to pi - phi, so with n + 1 equal waits
a static detuning delta leaves a phase `delta * w * sum_{k=0..n} (-1)^k`: zero for odd n,
`delta * w` (one wait of Ramsey phase) for even n. `T2EProgram.initialize` therefore
raises `ValueError` when `num_pi_pulses` is even or < 1 (n = 0 would be a Ramsey). For
n = 1 equal spacing is the Hahn echo (two waits of T/2). For odd n >= 3 the equal spacing
`w, w, ..., w` refocuses a static detuning but is not CPMG spacing (`w/2, w, ..., w, w/2`);
switching to CPMG spacing is a separate planned change.

### Step quantisation

The step quantises the total-time increment so that each of the n + 1 waits is a whole
number of tProc cycles. The cycle `c` is read from the board,
`c = tproc_cycle_us(soccfg) = soccfg.cycles2us(1)` (1 / 430.08 MHz = 0.0023251488 us on the
lab board), and `quantised_t2e_step(soccfg, T2_max_us, T2_expts, n)` in
`qicklab.experiments.t2_echo` returns:

```
int_steps = floor(T2_max_us / (c * (n + 1) * T2_expts))
step      = c * (n + 1) * int_steps          # us, total free evolution per point
```

With the defaults (`T2_max_us` 20, `T2_expts` 121, n = 1): `int_steps` = 35,
`step` = 0.16276 us (70 cycles / 430.08 MHz), last point 19.53 us. If `int_steps` is 0
(too many points for the time) the step prints `Step size is 0!` and measures nothing.

## How to run

```python
PLAN = [R.t2_echo()]                                    # regime A, echo group
PLAN = [R.t2_echo(num_pi_pulses=3, t2_max_us=60)]       # CPMG-3
```

`Session(echo=G.echo(...))` sets the shared group (also read by the combos and
interleaved_coherence).

## Parameters

Group `echo` (legacy `T2E_params`).

| Name (legacy key) | Legacy default | Units | Meaning |
|---|---|---|---|
| `T2_max_us` | 20 | us | Target maximum total free evolution (actual max is quantised down) |
| `T2_expts` | 121 | - | Number of points |
| `T2_reps` | 25 | shots | Hardware averages |
| `T2_rounds` | 25 | - | Software repeats |
| `num_pi_pulses` | 1 | - | Refocusing pulses; must be odd and >= 1 (`ValueError` otherwise) |
| `freq_shift` | 0.0 | MHz | Added to f_ge |
| `relax_delay` | 500 | us | Wait after each readout |
| `rotation_angle` | None | rad | Fixed IQ rotation; None = automatic |
| `min_max` | None | [I_g, I_e] | Normalise rotated I to population, only with a fixed `rotation_angle`; None = off |
| `repetitions` | 3000 | - | Records in a row (10 s pause + `soc.reset_gens()` after each) |
| `plotDisp` | `repetitions <= 1` | bool | Show the figures (explicit value wins) |
| `pi_gain`, `pi2_gain`, `sigma`, `flattop_length`, `f_ge` | device | | Pulses |

## Outputs

`path = "T2E"`. Files under `<outerFolder>T2E/T2E_<date>/`:

| File | Content |
|---|---|
| `..._data_n{num_pi_pulses}.h5` | `x_pts` (expts,) us (total free evolution); `avgi`, `avgq` as returned by qick (no cavity-winding correction); `qfreq` = f_ge; the fit fields below |
| `..._dataI_Data.png` | rotated (or normalised) I with the fit; title `Num Pulses: n ; ... T2E = x +- y us`, or `T2E fit not reliable` (fit drawn dashed grey if one exists) |
| `..._dataQ_Data.png` | rotated Q |
| `..._data.json` | config |
| `..._data_provenance.json` | provenance record ([architecture](../architecture.md#provenance)) |

Fit fields in the h5, as for [t1](t1.md#outputs) with prefix `t2e_`: `t2e_fit_ok`,
`t2e_fit_us`, `t2e_fit_err_us`, `t2e_fit_a`, `t2e_fit_c`, `t2e_fit_popt`, `t2e_fit_perr`
(`[a, T2E, c]`), `t2e_fit_rotation_rad` (IQ rotation used). NaN where the fit has no value.
The instance keeps the same result as `iT2E.fit`.

## Analysis

Same as [t1](t1.md#analysis): rotation by `rotation_angle` or by the principal-axis phase
(`decay_axis_phase`, first point at or above the mean; a 200-point min-Q-range grid until
2026-10); `min_max` normalisation only with a fixed `rotation_angle`; bounded fit
`a exp(-t/T) + c` (T in `[dx/2, 20 * span]`) with start `a = I[0] - I[-1]`, `c = I[-1]`, T at
the point closest to `a/2.6 + c`, and the same reliability checks (`ok`). The x axis is the
total free evolution, so the fitted T is T2E directly. A failed or unreliable fit never
raises; the record is saved with `t2e_fit_ok = 0` (and its values, if the optimiser returned
any). As for T1, `t2e_fit_ok` is a quality flag, not an unbiased selection: on marginal data
(T2E comparable to the sweep, or a noisy trace) the dropped fits are mostly the ones that
overestimate T2E, so a T2E(t) series filtered on it is biased low (numbers in
[t1](t1.md#analysis)). Keep the sweep at 3-5 T2E.
Assumes an exponential echo decay; a Gaussian-shaped decay (1/f noise) is fitted with an
exponential anyway.

## Findings & notes

- `num_pi_pulses` must be odd (CSTQ03 runner rule, repeated in the auto_coherence
  defaults). Enforced since 2026-10-14: the program raises `ValueError` at compile time,
  before anything is sent to the board; the reason is the
  [refocusing condition](#refocusing-condition).
- The step must be an integer multiple of (n + 1) tProc cycles so every wait stays on the
  cycle grid and the x axis `i * step` is the realised free evolution. The cycle is read
  from `soccfg` (since 2026-10-15; before, the literal 0.00232515 us was hard-coded, which
  on a board with another tProc clock would have scaled the T2E axis by up to about 1-2 %);
  [auto_coherence](auto_coherence.md) uses the same `quantised_t2e_step`; see
  [concepts/timing_and_units.md](../concepts/timing_and_units.md#t2e-step-quantisation).
- Phase convention: pi/2 at 0 deg, pi at 90 deg (CPMG).

## Known issues

- An even `num_pi_pulses` used to run without warning (a partial Ramsey reported as T2E);
  it now raises `ValueError`. In [coherence_combos](coherence_combos.md) the check runs
  when the T2E program is built, so the T1 of that pair has already been saved.
- For odd n >= 3 the waits are equal (`w, ..., w`), not CPMG-spaced (`w/2, w, ..., w/2`);
  CPMG spacing is a separate planned change.
- When `int_steps` is 0 the standalone step stops on the first repetition without
  measuring; in [coherence_combos](coherence_combos.md) the T1 of that pair has already
  been saved.
- The waits are pulse edge to pulse edge, not pulse centre to centre (the same convention
  that was found and fixed in ModifiedRamsey on 2026-07-28), so the true free evolution
  differs from `x_pts` by the pulse lengths.
- `x_pts` is the realised total wait, `(n + 1) * i * us2cycles(step / (n + 1))` tProc cycles
  ([timing_and_units](../concepts/timing_and_units.md#register-swept-wait-axis)); with the
  recipe's quantised step this equals `i * step`. A non-zero `start` is loaded into the
  register as raw cycles, so the axis is correct only for `start = 0` (always the recipe).
- If the cfg contains `rotation_angle` but not `min_max`, acquire raises `KeyError`.
