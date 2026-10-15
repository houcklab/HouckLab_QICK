# t1_single_shot: single-shot T1 (T1_SS)

## What it measures

T1 measured from thresholded single shots instead of averaged IQ. At each wait time
the step prepares |e> with one pi pulse, waits, reads out `reps` single shots,
rotates them by the [single_shot](single_shot.md) angle, and counts the fraction
above the single-shot threshold (the "excited population"). The result is the
excited fraction vs wait time, fitted for T1 (see [Analysis](#analysis)), plus a
readout-corrected copy of the curve when the run calibrated first. Code: see
`qicklab.experiments.t1_single_shot` (program class `T1SingleShotProgram`;
experiment class `T1_SS`).

## Pulse sequence

One `AveragerProgram` per wait point (a Python loop over `expts` points), each with
`reps` shots and `rounds = 1`.

```
qubit_ch  ── 0.05 µs ─[ gauss 4σ @ f_ge, gain pi_gain, phase 0 ]────┐
                                                                     ├── variable_wait ──┐
res_ch    ───────────────────────────────────────────────────────────────────────────────[ readout tone: length ]── relax_delay
ADC       ─────────────────────────────────────────────────────────────────────────────────────[ window ]
                                                                                     ^ adc_trig_offset
```

- Channels: `qubit_ch`, `res_ch`, `ro_chs` (only `ro_chs[0]` is used).
- No trigger pin. Plain gaussian only: `flattop_length` is ignored.
- Pi pulse gain: `cfg["pi_gain"]`, which `run_t1_ss` sets to the device pi gain
  (`ctx.qubit_gain`), the gain its single_shot calibration also uses. Until 2026-10-15 the
  program played `cfg["qubit_gain"]` (the pi gain only in regime B, where the two are equal).
  A cfg without `pi_gain` now raises `KeyError`.
- `variable_wait = start + k·step` (µs).
- Readout window: set by `cover_readout_window`. The ADC window is `readout_length` on
  the readout clock (`readout_window_cycles`), the tone covers `adc_trig_offset` plus
  that window on the generator clock (`readout_tone_cycles`), with the cross-clock tone
  extension of [single_shot](single_shot.md#pulse-sequence). Shots are normalised by
  the declared window, so their IQ scale matches the `single_shot` calibration (see
  Findings & notes).

## How to run

Runs in **regime B** (it needs `f_ge` and `sigma`). The pi pulse plays `pi_gain`, which
the run writes from the device pi gain.

```python
PLAN = [R.t1_single_shot()]                                  # calibrates SS first
PLAN = [R.t1_single_shot(calibrate_ss=False, angle=0.12, threshold=1.3)]
```

With `calibrate_SS = True`, each repetition first runs a [single_shot](single_shot.md)
(saved under `SingleShot/`) and uses its read-0 `angle` and `threshold`. The
calibration is always g vs one pi pulse at the pi gain (`ctx.qubit_gain`), in its own
cfg. The single_shot group's `pi2_SS` and `number_of_pulses` are ignored, and
`number_of_pulses` is not written into the T1 cfg. After every repetition the run
sleeps 10 s and calls `soc.reset_gens()`.

Guards (the T1 points are not acquired when one trips):

- The run raises `ValueError` if the calibration comes back in thermal mode, or if its
  `angle` or `threshold` is not finite. A NaN threshold would make every shot count
  as |g>, so the whole T1 curve would read 0.
- With `calibrate_SS = False`, the same finiteness check applies to the
  `T1SS_params` `angle` and `threshold` (`None` raises here, not in the counting step).
- A calibration contrast (the `hist_process` value labelled fidelity) below 0.3 only
  prints a warning.

## Parameters

Legacy `T1SS_params` keys. Defaults are the CSTQ03 runner values.

| Key | Default | Units | Meaning |
|---|---|---|---|
| `T1_step` → `step` | 80 | µs | Wait-time step (`start` is fixed at 0). |
| `T1_expts` → `expts` | 100 | count | Number of wait points; one program each. |
| `reps` | 2000 | count | Single shots per wait point. |
| `relax_delay` | 8000 | µs | Wait after each readout. |
| `calibrate_SS` | True | bool | Run single_shot before each repetition to get angle and threshold. |
| `angle` | 0 | rad | Rotation used when `calibrate_SS = False`. Same convention as single_shot. |
| `threshold` | 0 | normalised I | Threshold used when `calibrate_SS = False`. |
| `repetitions` | 3000 | count | Back-to-back T1_SS runs. |

`pi_gain` is written into the cfg by the run (the device pi gain) and is the gain of the
program's pi pulse.

## Outputs

Path `T1SS/`.

- **h5:**
  - `Exp_values`: raw excited fraction per wait point, shape `(expts,)`.
  - `Exp_err`: its binomial standard error `sqrt(p(1-p)/reps)`, shape `(expts,)` (0 where p
    is exactly 0 or 1).
  - `RotatedIQ`: rotated I/Q per point.
  - `threshold` and `angle` as used.
  - `wait_times`: µs.
  - T1 fit (written by display, saved by `finish`): `t1ss_fit_ok` (bool), `t1ss_fit_us`,
    `t1ss_fit_err_us` (T1 and its standard error, µs), `t1ss_fit_a`, `t1ss_fit_c`,
    `t1ss_fit_popt` / `t1ss_fit_perr` (`[a, T1, c]` and errors), `t1ss_fit_curve` (the fit
    evaluated at `wait_times`, raw-fraction units). NaN where the fit has no value; same
    key layout as `t1_fit_*` of [t1](t1.md#outputs).
  - Only with `calibrate_SS = True`: `readout_P_e_given_g`, `readout_P_g_given_e` (the
    calibration's assignment errors) and `Exp_values_readout_corrected`, shape `(expts,)`.
    Read the caveats in [Analysis](#analysis) before using it.
- **png:** raw excited fraction vs wait time (µs) with binomial error bars and the fit; the
  title carries `T1 = value ± error us`, or "T1 fit not reliable" (the curve, if any, dashed
  grey). The corrected curve is not plotted.
- **json:** the cfg, including `variable_wait` (last point) and `Excited_PulseT1`,
  which nothing reads.
- The fit is also on the instance as `iT1.fit` (the `fit_exp_decay` dict; after an exception
  inside the fit only `{'ok': False, 'error': repr(exc)}`).
- **Aborted run:** an error or Ctrl-C after at least one wait point saves the completed
  points (h5 + json, no png, no fit, no `Exp_err` or corrected curve) before re-raising:
  `Exp_values`, `RotatedIQ` and `wait_times` for the first `points_completed` points, `threshold`/`angle` (when not
  None) and a `points_completed` dataset. The json cfg carries `points_completed` and
  `aborted` (the error's repr). A complete run has neither key.
- Each wait point's program goes through `acquire_with_retry` (3 tries on the
  [stale-shot-counter race](../concepts/averaging.md#the-stale-shot-counter-race)).

## Analysis

Each shot is rotated: `I' = I cosθ − Q sinθ`. A shot counts as excited if `I' >
threshold`. The single_shot rotation puts |e> at larger I', so the raw fraction is
P(e) without readout-error correction. It plateaus at the readout error floor, not at 0,
and starts below 1 by the pi infidelity plus the readout error.

**T1 fit.** `a exp(-t/T1) + c` with `qicklab.analysis.fitting.fit_exp_decay` on the raw
fraction: the bounds, start values and `ok` checks of [t1](t1.md#analysis), in two passes
(`fit_t1ss_decay`). Pass 1 is unweighted. Pass 2 refits with per-point weights `1/sigma²`,
the binomial `sigma = sqrt(p(1-p)/reps)` evaluated at pass 1's **model** curve, p moved at
least `0.5/reps` away from 0 and 1 so a plateau at 0 keeps a finite weight. The weights
come from the model, not from the observed fraction: weighting by the observed p (a Neyman
chi-square) over-weights the points that fluctuate low, and when the plateau holds about
one excited shot per point or fewer (`reps * P(e|g)` below ~5) it pulled T1 low by 1-2
sigma (Monte Carlo, T1 = 60 us, 100 points at 5 us, reps = 200, `P(e|g)` = 0: mean 58.1 us
against 60.0 us; the model-weighted fit gives 60.0 us with a ~30 % smaller spread than the
unweighted one). If pass 1 has no finite curve (degenerate data), pass 1 is the result. The
weights are relative (`absolute_sigma=False`): the reported `T1_err` is rescaled by the
reduced chi-square, so excess scatter (drift, TLS switching) widens it instead of being
hidden behind the binomial error. The free offset `c` absorbs the readout floor. The
display is guarded: degenerate data (constant, too short) give `t1ss_fit_ok = False` and
NaN fields, never an exception.

**Readout-corrected curve.** With `calibrate_SS = True` the run counts the calibration
shots (`i_g0`/`q_g0`, `i_e0`/`q_e0`) with the same angle and threshold: `P(e|g)` = fraction of
g-prep shots above threshold, `P(g|e)` = fraction of pi-prep shots below it
(`readout_assignment_errors`). `Exp_values_readout_corrected = (p − P(e|g)) / (1 − P(e|g) −
P(g|e))`, unclipped (noise can take it outside [0, 1]), all NaN when
`1 − P(e|g) − P(g|e) <= 0`. What it is and is not:

- It is affine in p, so it **cannot change T1**: the display fits the raw curve.
- It is **not an absolute population**. The "errors" include the calibration's own prep
  errors (thermal |e> in the g shots; pi infidelity and decay during the readout in the
  pi shots). When the calibration plays the same pi pulse as T1_SS (same gain, and
  `flattop_length = None`), the correction maps the first point to ~1 and the plateau to
  ~0 by construction, whatever the true pi fidelity or thermal population is.
- **Flat-top qubits are the exception.** With `flattop_length` set, the single_shot
  calibration plays a flat-top pi pulse while T1_SS plays the plain 4-sigma Gaussian (see
  Known issues), so `P(g|e)` describes a different pulse and the corrected t = 0 point is
  not ~1 by construction; it is off by the difference in rotation between the two pulses.
- The calibration runs at `SS_params["relax_delay"]` and T1_SS at
  `T1SS_params["relax_delay"]`. If the first is too short to re-thermalise, the residual
  excitation in `P(e|g)` is larger in the calibration than in the T1 points, and the
  corrected plateau sits below 0.
- It assumes the calibration and the T1 points share one readout (same window, angle and
  threshold, same session). With `calibrate_SS = False` there are no calibration shots and
  the corrected curve is not written.

## Findings & notes

- 2026-10-15: the window and tone are set by `cover_readout_window`, as in
  [single_shot](single_shot.md), and shots are normalised by the declared window of
  `ro_chs[0]`. Before, the window was declared with a tProc-clock cycle count (1.4x
  `readout_length` on the lab board) but normalised by the readout-clock count, so the
  `single_shot` threshold and angle were applied on a scale f_time/f_output too large.
  Populations from before that date are unreliable
  ([readout window](../concepts/readout_window.md#history)).

- 2026-10-15: T1_SS fits T1 (weighted by the binomial error of the model curve, saved as `t1ss_fit_*` with the curve),
  saves `Exp_err` and, after a calibration, the confusion-corrected curve with the
  calibration's `P(e|g)` / `P(g|e)`. The pi pulse plays `pi_gain` instead of `qubit_gain`.
  Before, the step saved only the raw fraction, with no fit.

## Known issues

- `flattop_length` is ignored. Devices with a flat-top pi pulse get a mis-rotation, and
  their `Exp_values_readout_corrected` is calibrated on a different pulse
  ([analysis](#analysis)).
- One program per wait point, plus a 10 s sleep per repetition: long runs are slow.
