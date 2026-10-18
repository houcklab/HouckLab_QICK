# single_shot: g/e single-shot readout (SingleShotProgramFFMUX)

Recipe: `R.single_shot(...)` (`qicklab.runs.recipes`; every keyword with its default and unit is in the docstring, `help(R.single_shot)`). Session groups: [step table](../running_a_session.md#steps). Generated parameter tables come in phase 6.

## What it measures

This step acquires two IQ clouds of single shots: one with no qubit pulse (|g>
reference) and one after N qubit pulses (|e> reference for N = 1). From the two
clouds it computes a rotation angle, a threshold along the rotated I axis, and a
number labelled "fidelity", which is actually the readout **contrast** (see Analysis).
With `number_of_pulses = 0` it switches to **thermal mode**: one undriven cloud plus
a labelled pi-pulse reference, with the excited (thermal) population fitted as a
maximum-likelihood mixture weight.

The same program (`SingleShotProgram`) supplies the g/e calibration for the
active-reset threshold, the a-priori separator of [modified_ramsey](modified_ramsey.md)
and [zero_span_parity](zero_span_parity.md), the threshold/angle of
[t1_single_shot](t1_single_shot.md), and the sweeps of
[readout_optimize](readout_optimize.md) and [qubit_optimize](qubit_optimize.md).
Code: see `qicklab.experiments.single_shot`.

## Pulse sequence

Two programs per acquisition, each with `reps = shots` and `rounds = 1`. The first
has `Pulse = False` (qubit block skipped), the second `Pulse = True`.

```
                 ┌── repeated number_of_pulses times ──┐
pin 0     ───────[trig]────────────────────────────────────────────────────────
qubit_ch  ─────────[ gauss 4σ (or flat_top) @ f_ge, gain qubit_gain ]─ 0.05 µs ─
res_ch    ──────────────────────────────────────────── 0.05 µs ─[ readout tone ]──── relax_delay ──
ADC       ─────────────────────────────────────────────────────────── [ window ]
                                                                   ^ adc_trig_offset
```

- Channels: `qubit_ch`, `res_ch`, `ro_chs` (I/Q of every channel in `ro_chs`).
- **Trigger pin 0** fires before every qubit pulse. It starts `trig_delay −
  trig_buffer_start` after the pulse reference and its width is
  `trig_buffer_start + trig_buffer_end + 4σ (+ flattop_length)`. BaseConfig values:
  `trig_delay` 0.082 µs, `trig_buffer_start` 0.02 µs, `trig_buffer_end` 0.02 µs. What pin 0 drives on the current setup is not
  documented in the code (see [hardware](../hardware.md)).
- Qubit pulse: a 4σ gaussian `"arb"` pulse, or `flat_top` when `flattop_length` is
  set. Phase 0, frequency `f_ge`, gain `qubit_gain`. Each pulse is followed by
  `sync_all(0.05 µs)`.
- **Readout window, cross-clock block.**
  - The ADC trigger offset `adc_trig_offset` is converted on the tProc clock.
  - The integration window `readout_length` is converted on the readout clock
    (`us2cycles(readout_length, ro_ch=ch)`).
  - The tone `length` (default `adc_trig_offset + readout_length`) is converted on
    the generator clock.
  - The tone is then extended by the minimum number of generator cycles needed to
    cover the quantised ADC window: `ceil(adc_end_tproc · f_fabric / f_time − 1e-12)`.
    `length < adc_trig_offset + readout_length` raises.
  - [modified_ramsey](modified_ramsey.md), [active_reset_verify](active_reset_verify.md)
    and [undriven_single_shot](undriven_single_shot.md) use the same arithmetic
    (all call `qicklab.core.readout.cover_readout_window`), so they
    integrate the same physical window and thresholds transfer between them. This
    matters most for the [active-reset](active_reset.md) threshold.
- Shots are normalised by the declared window `readout_window_cycles[ro_ch]` =
  `us2cycles(readout_length, ro_ch)` (the "normalised units" used everywhere else).

## How to run

Runs in **regime B**, the single-shot config built from the session's single_shot
group (`SS_params`): its own readout window, `qubit_gain` = pi gain, and
`qubit_pulse_style = "arb"`.

```python
PLAN = [R.single_shot()]                         # g/e, one pi pulse
PLAN = [R.single_shot(number_of_pulses=0)]       # thermal mode
PLAN = [R.single_shot(pi2_ss=True, number_of_pulses=2)]  # check pi/2: two pi/2 = pi
```

`pi2_SS = True` replaces `qubit_gain` with the device pi/2 gain.

## Parameters

Legacy keys. Regime-B keys come from the session single_shot group (`SS_params`);
defaults are the CSTQ03 runner values.

| Key | Default | Units | Meaning |
|---|---|---|---|
| `Shots` → `shots` | 1000 | count | Shots per cloud (program sets `reps = shots`). |
| `Readout_Time` → `readout_length` | 15 | µs | ADC integration window for the single-shot family. |
| `ADC_Offset` → `adc_trig_offset` | 0.3 | µs | Tone start → ADC trigger. Tone length = offset + window. |
| `relax_delay` | 6000 | µs | Wait after each readout. |
| `number_of_pulses` | 1 | count | Pulses in the "e" program. 0 = thermal mode. |
| `pi2_SS` | False | bool | Use the pi/2 gain instead of the pi gain. |
| `Qubit_Pulse` | [session pulse qubit] | list | Qubit(s) whose gain/frequency fill `qubit_gains`, `f_ges`. |
| `Read_Indeces` (sic) | session readout qubit | int/list | Labels for the saved keys (`i_g<r>` …). |
| `thermal_tail_md2_threshold` | 6.0 | Mahalanobis d² | Thermal mode: a point is a tail candidate above this. 95 % χ² for 2-D is ≈ 5.99; use 6–9 depending on overlap. |
| `thermal_tail_sigma_threshold` | 2.5 | σ | Thermal mode: excited if the projection > median + k·σ. Use 2.0–3.0 depending on aggressiveness. |
| `thermal_pi_calibration` | True | bool | Thermal mode: acquire a second cloud after one pi pulse (`qubit_gain` at `f_ge`) right after the undriven one, as the labelled \|e> reference for the population fit. Doubles the acquisition time. The pi pulse drives only the qubit on `qubit_ch`, so with several reads only that qubit's read is a population; the other reads normally save NaN, but can return a meaningless number (see Failure modes). |
| `thermal_e_center` | unset | (I, Q), normalised units | Thermal mode, only when `thermal_pi_calibration` is False: fixed e centre (one pair, or one pair per read). Without it the population is NaN. |
| `sigma`, `qubit_gain`, `f_ge`, `flattop_length` | device | µs, DAC, MHz, µs | Pulse definition. |

## Outputs

Path `SingleShot/` (or `SingleShot_MRCalib/` for separator calibrations).

- **h5, normal mode:** for each read index r: `i_g<r>`, `q_g<r>`, `i_e<r>`, `q_e<r>`
  (shape `(shots,)`, normalised units). If r differs from its enumeration index i,
  the same data is also saved under `i_g<i>` …. Also `threshold` (list per read),
  `angle` (list per read, rad) and `thermal_mode = 0`.
- **h5, normal mode, readout figures of merit** (per read r, also under `<i>` when r
  differs; since 2026-10, so readout quality can be tracked across calibrations):
  - `contrast_hist<r>`: the `hist_process` contrast C (the png number, `inst.fid`).
  - `P_e_given_g<r>`, `P_g_given_e<r>`: fraction of g shots above / e shots at or below
    the saved threshold after rotating by the saved angle, counted by
    `readout_assignment_errors`, the same helper `t1_single_shot` uses for its readout correction
    (so its printed P(e|g), P(g|e) are these numbers exactly). They include prep errors
    (thermal |e⟩, pi infidelity, decay during readout).
  - `assignment_fidelity<r>` = 1 − (P_e_given_g + P_g_given_e)/2 = (1 + C)/2.
  - `g_center_median<r>`, `e_center_median<r>` (the centres the angle uses) and
    `g_center_mean<r>`, `e_center_mean<r>`, each (I, Q).
  - From `calibrate_readout_from_labeled_shots` (mean/LDA axis, the Modified Ramsey
    calibration): `snr_analog<r>`, `cal_contrast<r>`, and its own discriminator
    `cal_axis<r>`, `cal_midpoint<r>`, `cal_threshold<r>` (on (IQ − cal_midpoint)·cal_axis,
    not on the rotated I; `t1_single_shot` and active reset use `threshold`/`angle`).
    `readout_gate_pass<r>` = 1 when none of the parity-analysis readout gates trips
    (analog SNR < 1, contrast < 0.3, fewer than 500 shots in a class), else 0; each
    tripped gate is printed as a WARNING. The calibration's e-cloud warnings (purity
    of the pi-prepared shots < 0.9, mixture fallback; see
    [modified_ramsey](modified_ramsey.md#analysis)) are printed too but do not fail the
    gate. All of these are NaN when the calibration
    raises (fewer than 10 shots per class, coincident centres).
  Not in thermal mode (no labelled e cloud).
- **h5, thermal mode:** `i_thermal<r>`, `q_thermal<r>`, the population fit
  `thermal_population<r>` (ML mixture weight, fraction), `thermal_population_err<r>`
  (its standard error), `thermal_pi_population<r>` (excited fraction of the pi run),
  `thermal_fit_e_width_ratio<r>` (e/g cloud width ratio of the fit, should be ≈ 1),
  `thermal_fit_g_center<r>`, `thermal_fit_e_center<r>`, `thermal_fit_cov<r>` (all of
  these NaN when the population is undetermined, see Analysis), the pi
  reference `i_pi<r>`, `q_pi<r>` (when `thermal_pi_calibration`), and the tail
  classifier's `thermal_labels<r>`, `thermal_tail_fraction<r>` (named
  `thermal_population_tail<r>` before 2026-10-13; not a population),
  `thermal_center_g<r>`, `thermal_center_e<r>`, `thermal_md2<r>`,
  `thermal_projection<r>`, `thermal_projection_threshold<r>`, the tail-split clouds as
  `i_g/q_g/i_e/q_e<r>`, plus `threshold`, `angle`, `thermal_mode = 1`,
  `thermal_fit_type = 1`. If r differs from its enumeration index i, the clouds
  (`i_thermal`, `q_thermal`, `thermal_labels`, `i_g/q_g/i_e/q_e`) and the keys the png
  uses (`thermal_population`, `thermal_population_err`, `thermal_tail_fraction`,
  `thermal_center_g`, `thermal_center_e`) are also saved under `<i>`; the png shows the
  first read.
- **png:** three panels (unrotated, rotated, I histogram), titled
  `Contrast C = xx.xx % (F_assign = yy.yy %)` (`Fidelity = xx.xx %` before 2026-10;
  same C). In thermal mode: a tail-labelled scatter titled with the
  fitted population ± SE and the tail fraction.
- **json:** the cfg.
- The contrast is also the attribute `fid` (per-read list after `acquire()`, read 0's
  value after `display()`). Before 2026-10 it was not saved in the h5.

## Analysis

`hist_process` (default numerics; see `qicklab.analysis.readout`):

1. Rotate both clouds by `θ = −arctan2(Q̃_e − Q̃_g, Ĩ_e − Ĩ_g)` (tilde = median), so
   the g→e axis lies along +I.
2. Take the exact empirical CDF of the rotated I of each cloud (every shot counts).
3. `contrast(t) = CDF_g(t) − CDF_e(t)` with g := I ≤ t (the rule `t1_single_shot` applies).
   "fid" is the maximum; the threshold is the midpoint between the maximising shot
   value and the next one, so "fid" is exactly the contrast the saved threshold gives
   on these shots. The 200-bin histogram is drawn in the png only, with the threshold
   as a dashed line. Before 2026-10 the contrast came from that histogram and the
   threshold was the left edge of the peak bin
   ([IQ conventions, known issues](../concepts/iq_conventions.md#known-issues)).

**"Fidelity" is the readout contrast**, `C = P(g|g) + P(e|e) − 1`. It is not the
assignment fidelity. For equal priors at the optimal threshold, `F_assign = (1 + C)/2`;
for example, the legacy "Fidelity = 44.90 %" means F_assign ≈ 0.72. The h5 saves
both (`contrast_hist<r>`, `assignment_fidelity<r>`, see [Outputs](#outputs)), as does
the Modified Ramsey analysis (`calibrate_readout_from_labeled_shots`). The
display clips "fid" at 1.0.

Thermal mode, population (`fit_thermal_population`; details in
[IQ conventions section 7](../concepts/iq_conventions.md)): both clouds (undriven and
pi) are modelled as (1 − q)·N(g, Σ) + q·N(e, Σ) with a shared covariance; EM fits g, e,
Σ and the two weights jointly, and the undriven weight is the thermal population, with a
standard error that includes the centre uncertainty. EM starts both from p = 0.05,
w = 0.9 and from a KMeans split of the pooled shots and keeps the better fit. Unbiased
within its SE on synthetic data with equal g/e widths at d = 2–5 σ, including p ≈ 0.45.
The population, its SE, the pi-run fraction w, the width ratio and the fitted centres and
covariance are all saved as NaN (with a printed WARNING giving the unguarded p and w) when
the fitted g–e separation is below 1 σ, or when w exceeds p by less than 4 standard
errors, i.e. when the data cannot say which cloud is |e>. Two model biases remain: an e
cloud wider than the g cloud biases p **low** (narrower: high), most at small separation
(σ_e = 1.2 σ_g: true 3 % reads 1.9/2.6/3.1 % at d = 2/3/5 σ); `thermal_fit_e_width_ratio`
shows it and a WARNING is printed when it is off 1 by more than 5 % and 4 SE. T1 decay
during the window biases p **low**, by about 0.5–0.9 × the fraction of excited shots that
decay within the window (relative).

Thermal mode, scatter labels (`classify_thermal_tail`):

1. Fit the main blob robustly (`MinCovDet`, support fraction 0.75, random state 0).
2. Mark Mahalanobis d² > `thermal_tail_md2_threshold` as tail candidates.
3. Take the protrusion axis as the mean of the farthest max(10, 5 %) points minus the
   centre.
4. Compute σ along that axis as 1.4826·MAD of the non-tail points.
5. Call a point excited if its projection > median + `thermal_tail_sigma_threshold`·σ.

The labelled-excited fraction (`thermal_tail_fraction`) is **not** a population and
not conservative: at k = 2.5, N = 2000 it reads about 1 % at zero population, and below
a g–e separation of about 4 σ it reads low by up to 4× (true 10 % reads 2.7 % at d = 2 σ).
"fid" is NaN in thermal mode.

Failure modes:

- Overlapping clouds give a meaningless angle (medians close together).
- A drifting readout moves the threshold between calibrations.
- In thermal mode any exception in the tail classifier, including a missing sklearn,
  silently returns all labels 0 and threshold NaN; only a print reports it. A failed
  population fit likewise saves NaN with a print.
- With several reads (`Read_Indeces` a list, MUX), the pi reference drives only the qubit
  on `qubit_ch`, and only that qubit's read is a population, even if another read returns a
  number (a WARNING says so). For every other read the "pi" cloud is a second undriven
  cloud, so its `thermal_population<r>` is normally NaN with a "not driven" WARNING (its
  tail fraction is still saved). The guard sees any change between the two runs, not the pi
  pulse itself: if that read's cloud moved (readout drift, cross-Kerr/ZZ to the pi'd qubit)
  the fit can take the moved cloud as |e> and save a finite, meaningless population with no
  per-read warning (synthetic d = 3 σ, p = 3 %, 2000 + 2000 shots: finite in 0/20 seeds
  unshifted, 1–4/20 at a 0.3–0.5 σ shift, 14–16/20 at 1 σ). To measure another qubit, run
  thermal mode again with that qubit's `qubit_ch`, `f_ge` and `qubit_gain`.
- A population near 50 % is undetermined: a pi pulse swaps nearly equal populations, so
  w ≈ p and the result is NaN.
- An e cloud wider than the g cloud (long window, measurement-induced transitions) biases
  the population low; the "as wide as the g cloud" WARNING and
  `thermal_fit_e_width_ratio` > 1 flag it. Shorten the window or treat p as a lower bound.
- The thermal-mode pi reference is acquired after the undriven cloud, not shot-interleaved,
  so readout drift between the two runs (see Findings) shifts the fitted e centre.

## Findings & notes

- CSTQ03 single-shot readout time: Q1 15 µs, Q5 5 µs; "keep at 15" (runner note,
  undated).
- CSTQ03 Q2, 2026-08-04: three consecutive labelled calibrations over ~4 min gave
  analog SNR 0.86 / 1.05 / 0.77 (assignment fidelity 0.66–0.71). About 10 % of the
  g–e separation drifted within one 2000-shot record. Later that day readout SNR
  drifted 0.746 → 1.399 → 1.481 within ~4 min of one run. Let the readout settle and
  interleave calibrations before comparing across time.
- Quality gates used downstream: analog SNR < 1, contrast < 0.3, or < 500 labelled
  shots per class all produce warnings (see [modified_ramsey](modified_ramsey.md#analysis)).

## Known issues

- With `ran` given, the plotted histogram range is centred on the g blob only, so the
  e blob can fall outside the plot. This affects the png only: the contrast and
  threshold use every shot (see [Analysis](#analysis)). Before 2026-10 the threshold
  was the left edge of the optimal histogram bin (off by one bin) and shots outside
  the range were not counted.
- `display()` replaces the per-read lists `fid/threshold/angle` with scalars of read
  0. Code that reads `inst.fid[0]` before `display()` sees the list; after it, a scalar.
- `display()` only plots read index 0. Other reads are reachable only through the
  alias keys.
- `SingleShotProgram` does not pass `mixer_freq` to `declare_gen`. This is harmless
  while `mixer_freq = 0.0`.
- Calling `save_data()` without an argument raises a TypeError.
- [t1_single_shot](t1_single_shot.md) declares its readout window on a different clock
  than this program. Thresholds do not transfer exactly to it.
