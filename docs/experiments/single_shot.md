# single_shot: g/e single-shot readout (SingleShotProgramFFMUX)

## What it measures

This step acquires two IQ clouds of single shots: one with no qubit pulse (|g>
reference) and one after N qubit pulses (|e> reference for N = 1). From the two
clouds it computes a rotation angle, a threshold along the rotated I axis, and a
number labelled "fidelity", which is actually the readout **contrast** (see Analysis).
With `number_of_pulses = 0` it switches to **thermal mode**: one undriven cloud,
with the excited-state tail estimated from the shape of that cloud.

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
    (`qicklab.core.readout` in ModifiedRamsey, own copies elsewhere), so they
    integrate the same physical window and thresholds transfer between them. This
    matters most for the [active-reset](active_reset.md) threshold.
- Shots are normalised by `us2cycles(readout_length, ro_ch)` (the "normalised units"
  used everywhere else).

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
| `sigma`, `qubit_gain`, `f_ge`, `flattop_length` | device | µs, DAC, MHz, µs | Pulse definition. |

## Outputs

Path `SingleShot/` (or `SingleShot_MRCalib/` for separator calibrations).

- **h5, normal mode:** for each read index r: `i_g<r>`, `q_g<r>`, `i_e<r>`, `q_e<r>`
  (shape `(shots,)`, normalised units). If r differs from its enumeration index i,
  the same data is also saved under `i_g<i>` …. Also `threshold` (list per read),
  `angle` (list per read, rad) and `thermal_mode = 0`.
- **h5, thermal mode:** `i_thermal<r>`, `q_thermal<r>`, `thermal_labels<r>`,
  `thermal_population_tail<r>`, `thermal_center_g<r>`, `thermal_center_e<r>`,
  `thermal_md2<r>`, `thermal_projection<r>`, `thermal_projection_threshold<r>`, the
  split clouds as `i_g/q_g/i_e/q_e<r>`, plus `threshold`, `angle`,
  `thermal_mode = 1`, `thermal_fit_type = 1`.
- **png:** three panels (unrotated, rotated, I histogram), titled
  `Fidelity = xx.xx %`. In thermal mode: a labelled scatter with
  `P_excited-like`.
- **json:** the cfg.
- **The "fidelity" is NOT saved** in the h5. It exists only in the png title and in
  the attribute `fid` after `display()`. Threshold and angle are saved.

## Analysis

`hist_process` (default numerics; see `qicklab.analysis.readout`):

1. Rotate both clouds by `θ = −arctan2(Q̃_e − Q̃_g, Ĩ_e − Ĩ_g)` (tilde = median), so
   the g→e axis lies along +I.
2. Histogram the rotated I of each cloud in 200 bins spanning both blobs.
3. `contrast(x) = |cumsum(n_g) − cumsum(n_e)| / (½N_g + ½N_e)`. The threshold is at
   the maximum; "fid" is the maximum value.

**"Fidelity" is the readout contrast**, `C = P(g|g) + P(e|e) − 1`. It is not the
assignment fidelity. For equal priors at the optimal threshold, `F_assign = (1 + C)/2`;
for example, the legacy "Fidelity = 44.90 %" means F_assign ≈ 0.72. Nothing in
the single-shot code applies the (1+C)/2 conversion. The Modified Ramsey analysis
(`calibrate_readout_from_labeled_shots`) reports both under unambiguous names. The
display clips "fid" at 1.0.

Thermal mode (`classify_thermal_tail`):

1. Fit the main blob robustly (`MinCovDet`, support fraction 0.75, random state 0).
2. Mark Mahalanobis d² > `thermal_tail_md2_threshold` as tail candidates.
3. Take the protrusion axis as the mean of the farthest max(10, 5 %) points minus the
   centre.
4. Compute σ along that axis as 1.4826·MAD of the non-tail points.
5. Call a point excited if its projection > median + `thermal_tail_sigma_threshold`·σ.

The population is conservative: only protruding points count. "fid" is NaN in
thermal mode.

Failure modes:

- Overlapping clouds give a meaningless angle (medians close together).
- A drifting readout moves the threshold between calibrations.
- In thermal mode any exception, including a missing sklearn, silently returns all
  labels 0 and threshold NaN; only a print reports it.

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

- The threshold is the **left** edge of the optimal histogram bin (off by one bin).
  With `ran` given, the histogram range is centred on the g blob only, so the e blob
  can fall outside it.
- `display()` replaces the per-read lists `fid/threshold/angle` with scalars of read
  0. Code that reads `inst.fid[0]` before `display()` sees the list; after it, a scalar.
- `display()` only plots read index 0. Other reads are reachable only through the
  alias keys.
- `SingleShotProgram` does not pass `mixer_freq` to `declare_gen`. This is harmless
  while `mixer_freq = 0.0`.
- Calling `save_data()` without an argument raises a TypeError.
- [t1_single_shot](t1_single_shot.md) declares its readout window on a different clock
  than this program. Thresholds do not transfer exactly to it.
