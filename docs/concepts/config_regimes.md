# Config regimes

Every experiment reads one flat `cfg` dict. The session keeps a persistent instrument config,
`ctx.config`, and each step copies it, adds its own keys and hands the copy to the experiment.
There are two ways to build `ctx.config`. They are called **regime A** (measurement config) and
**regime B** (single-shot config). Each step belongs to one regime, and `run()` rebuilds the
config whenever two consecutive steps of a plan belong to different regimes.

The split is historical. The legacy runner built config A at connect, ran every
non-single-shot experiment, then rebuilt the config once from scratch for the single-shot family.
The refactor keeps both builders byte-identical so that the hardware sees the same programs, and
makes the switch automatic.

## The two regimes at a glance

| | Regime A: measurement config | Regime B: single-shot config |
|---|---|---|
| Builder | `qicklab.core.config.measurement_config` (legacy `build_context`) | `qicklab.core.config.singleshot_config` (legacy `rebuild_singleshot_config`) |
| Built from | `BASE_CONFIG` + device readout/qubit values + session groups `transmission`, `spec`, `tones`, `charge` | `BASE_CONFIG` + device readout/qubit values + session group `single_shot`. **Not** from the current config. |
| Readout window | `Readout.window` of the readout qubit, else `Device.readout_window` | `Readout.ss_window` of the readout qubit, else `Device.ss_window` |
| `qubit_gain` means | **spectroscopy** drive gain (`spec` group, legacy `Spec_relevant_params["qubit_gain"]`) | **pi-pulse** gain of the pulse qubit (`Qubit.gain`) |
| `reps` | 1000 (set explicitly; steps override) | 1000 from `BASE_CONFIG`; single-shot programs overwrite it with `shots` |
| Carry-overs | `pulse_freq` and `res_phase` written by earlier steps persist | discarded: `pulse_freq` back to the device value, `res_phase` back to 0 |

Window details: [readout window](readout_window.md). `qubit_readout` selects the resonator
(readout frequency, gain, window, data folder); `qubit_pulse` selects the drive (qubit frequency,
pi gain, sigma, flat-top length).

## Regime A: what is in the config

`config = BASE_CONFIG | transmission | qubit | sweep | tones | ts | charge`, then `FF_Qubits` and
`cavity_min` are added.

| Source | Keys (value or origin) |
|---|---|
| `BASE_CONFIG` ([hardware](../hardware.md#channel-map)) | `res_ch`=0, `qubit_ch`=1, `mixer_freq`=0.0, `ro_chs`=[0], `nqz`=2, `qubit_nqz`=1, `relax_delay`=3000, `res_phase`=0, `pulse_style`="const", `cavity_LO`=0, `cavity_winding_freq`=0, `cavity_winding_offset`=0, `trig_buffer_start`=0.02, `trig_buffer_end`=0.02, `trig_delay`=0.082 |
| readout block | `reps`=1000, `length`=`adc_trig_offset + readout_length`, `readout_length`, `adc_trig_offset`, `pulse_gain`=readout gain, `pulse_freq`=readout frequency, `TransSpan`, `TransNumPoints` (from `transmission`), `cav_relax_delay`=30 |
| qubit block | `qubit_pulse_style`="const", `qubit_gain`=**spec gain**, `qubit_freq`=qubit centre frequency, `qubit_length`, `SpecSpan`, `SpecNumPoints` (from `spec`), `current_voltage`=session bias |
| sweep block | `start`=`qubit_freq - SpecSpan`, `step`=`2*SpecSpan/SpecNumPoints`, `expts`=`SpecNumPoints` |
| `tones` | `tone_length` (read by `constant_two_tone`) |
| `ts` | `start_ts_gain`, `end_ts_gain`, `ts_step`: read by nothing (dead keys, dropped later as an allowed diff) |
| `charge` | `voltage_start`, `voltage_end`, `voltage_step` (read by `charge_sweep`, `charge_transmission_sweep`) |
| added last | `FF_Qubits` (metadata only, see [hardware](../hardware.md#fast-flux-channels)), `cavity_min` |

Not in regime A: `sigma`, `f_ge`, `flattop_length`, `pi_gain`, `pi2_gain`, `shots`,
`qubit_gains`, `f_ges`, `Read_Indeces`, `pi2_SS`, `read_pulse_style`, `Gauss`. Each step adds
the ones it needs to its own copy.

## Regime B: what is in the config

`config = BASE_CONFIG | single_shot_block`, then `FF_Qubits` and `Read_Indeces` = `qubit_readout`.

| Key | Value |
|---|---|
| `read_pulse_style` | "const" |
| `length` | `ss_window.adc_offset_us + ss_window.length_us` |
| `readout_length`, `adc_trig_offset` | the single-shot window (legacy `SS_params["Readout_Time"]`, `SS_params["ADC_Offset"]`) |
| `pi2_SS` | from the `single_shot` group; `single_shot` then plays `pi2_gain` instead of the pi gain |
| `pulse_gain`, `pulse_freq` | readout gain and frequency **from the device file** |
| `qubit_pulse_style` | "arb" |
| `sigma`, `qubit_gain`, `f_ge`, `flattop_length` | pulse qubit: sigma, **pi gain**, centre frequency, flat-top length |
| `qubit_gains`, `f_ges` | lists over the `single_shot` group's `Qubit_Pulse` entries |
| `shots`, `relax_delay` | from the `single_shot` group |

## What changes at the switch A -> B

Dropped (present in A, absent in B): `TransSpan`, `TransNumPoints`, `cav_relax_delay`,
`qubit_freq`, `qubit_length`, `SpecSpan`, `SpecNumPoints`, `current_voltage`, `step`, `start`,
`expts`, `tone_length`, the `ts` keys, `voltage_start/end/step`, `cavity_min`.

Carry-overs discarded. A carry-over is a measured value a step writes back into `ctx.config` so
that later steps use it. There are exactly two:

| Key | Written by | Value written | After the switch to B |
|---|---|---|---|
| `pulse_freq` | `transmission_fit` | hanger-fit minimum (IF MHz, absolute only if `cavity_LO` = 0) | back to the device readout frequency |
| `pulse_freq` | `transmission_sweep` | `peakFreq_min` if `cavity_min` else `peakFreq_max` | back to the device readout frequency |
| `res_phase` | active-reset readout calibration, run by `active_reset_verify` and by `modified_ramsey` with `use_active_reset` | phase (tProc register units) that puts the g-e axis on I | back to 0 |

`qubit_gain` changes meaning. Steps that read `cfg["qubit_gain"]` directly:

| Step | Reads `qubit_gain` as | Correct regime |
|---|---|---|
| `constant_two_tone`, `trans_qubit_spec` (when `Gauss` is False) | spec drive gain | A |
| `t1_ss` (`T1_SS` plays `cfg["qubit_gain"]` as its pi pulse) | pi gain | B only; in A it would play the spec gain |
| `qubit_optimize` (centre of the gain scan) | pi gain (or pi/2 gain with `pi2_SS`) | B only; in A `cfg["pi2_SS"]` is missing and the step raises `KeyError` |
| `single_shot` | pi gain, replaced by `pi2_gain` when `pi2_SS` | B |

Most other steps set `pi_gain` / `pi2_gain` explicitly from the device and do not depend on
`qubit_gain`. `two_tone_spec` drives at the `spec` group's `gain` (800 in the CSTQ03 runner), not
at `qubit_gain`: one quantity, two keys.

The data folder does not change: both regimes write under `Device.folder(qubit_readout)`.

## Which step runs under which regime

| Regime A | Regime B |
|---|---|
| `constant_two_tone`, `constant_tone`, `transmission_fit`, `transmission_sweep`, `two_tone_spec`, `spec_gain_length_sweep`, `trans_qubit_spec`, `chi_shift`, `amplitude_rabi`, `t1`, `t2_ramsey`, `t2_echo`, `t1_t2e`, `t1_t2r_t2e`, `two_tone_charge_dispersion_quasicw`, `charge_dispersion_quasicw`, `charge_dispersion_ramsey`, `modified_ramsey`, `modified_ramsey_control`, `charge_sweep`, `charge_transmission_sweep`, `active_reset_verify`, `interleaved_coherence` | `single_shot`, `undriven_single_shot`, `t1_ss`, `readout_optimize`, `qubit_optimize`, `auto_coherence`, `zero_span_parity` |

The registry `qicklab.runs.STEPS` is the authority; if this table and `STEPS` disagree, `STEPS`
wins.

Three steps are regime B by position but build most of their own config:

- `auto_coherence` copies the config and sets its own spectroscopy, Rabi, single-shot window
  (`ss_readout_time` 15 us, `ss_adc_offset` 1 us, optionally optimised) and coherence keys. It
  never writes back to `ctx.config`.
- `zero_span_parity` builds its cfg from scratch: it takes only channels, Nyquist zones,
  `mixer_freq` and the device frequencies and gains, and has its own window keys (`read_length`,
  `adc_trig_offset`) and its own `res_phase` (default 0, so a calibrated `res_phase` is not used).
- `interleaved_coherence` is listed under A but swaps per sub-step: `UndrivenSingleShot` runs on a
  freshly built B config, `T1FF` / `T2R` / `T2EMUX` on the A config it started with, which it
  restores at the end (so A carry-overs survive the loop; the B sub-steps do not see them).

The apriori single-shot separator used by `modified_ramsey` and `active_reset_verify` is measured
inside those steps with `SingleShotProgram` under **regime A**, so with the regime-A window. That
is deliberate: the threshold and the measurement must use the same window.

## How `run()` switches

```python
for step in PLAN:
    if step.regime != current_regime:      # the connect builds A, so the first B step switches
        ctx.config = measurement_config(...) if step.regime == "A" else singleshot_config(...)
        current_regime = step.regime
    step.fn(ctx, *groups_needed_by(step), **step.params)
```

- The config builders are pure functions of the device, the session and its groups. They
  do not read the previous config.
- A plan in the legacy order (all A steps, then all B steps) produces exactly one switch,
  which reproduces the legacy runner and its regression golden.
- A plan may go back and forth. Each switch drops carry-overs as described above. Design v3
  does not say that a B -> A switch restores the carry-overs of earlier A steps; assume it
  does not, and re-run `transmission_fit` (or put the value in the device file) after a
  B step if a later A step needs the fitted frequency.
- `run(session, PLAN, dry_run=True)` performs the same switches against fake hardware and
  prints the effective parameters of every step, so you can check what each step will see.

Example:

```python
PLAN = [
    R.transmission_fit(reps=20),   # A (built at connect). Writes pulse_freq = fitted f0.
    R.amplitude_rabi(),            # A. Uses the fitted pulse_freq.
    R.single_shot(),               # switch A -> B. pulse_freq back to the device value.
    R.t1(relax_delay=5000),        # switch B -> A. Rebuilt from the device: no fitted pulse_freq.
]
```

To keep a measured value across switches and sessions, write it into the device file.
Calibrating steps print a paste-ready `Qubit(...)` line and append to
`<data_root>/Q{q}/calibrations.jsonl`; for a quick trial without editing the tracked file use
`Device.with_qubit(q, **changes)`. See [adding a device](../adding_a_device.md).

Parameter precedence inside a step: library recipe default < session group < keyword on the
step (`R.t1(relax_delay=5000)`).

## Transient knobs never leak

Steps build their experiment cfg with `ctx.working_config(...)`: a shallow copy of
`ctx.config` plus the step's keys. `reps`, spans, sigma, scan gains and so on therefore do not
reach the next step. Only the two carry-overs above are written back on purpose. The copy is
shallow: the nested `ro_chs` list and the `FF_Qubits` dict are shared, so mutating them in place
would leak (no current code does).

## Practical rules

- Run `transmission_fit` immediately before the A steps that should use the fitted resonator
  frequency. Single-shot steps always use the device readout frequency.
- Run `active_reset_verify` in the same regime as `modified_ramsey` (both A) so its verdict
  transfers to the measurement. A following `single_shot` runs with `res_phase` = 0, not the
  calibrated phase.
- `undriven_single_shot` cannot read the charge-sweep range from the `charge` group, because
  regime B drops `voltage_start/end/step`. Pass the range in the step's own parameters
  (`voltage_end` is exclusive, as in `np.arange`).
- Do not rely on `qubit_gain` in custom code. Read `pi_gain` / `pi2_gain` / the spec gain
  explicitly.

## History

- Before 2026-07-02 the whole sequence lived in one script with two top-level
  `config = BaseConfig | UpdateConfig` statements; the 2026-07-02 split into run functions kept
  the second rebuild at the same point, unconditionally.
- 2026-08-04: the regime-A window became a runner setting (`Readout_Time`, `ADC_Offset`) instead
  of being hard-coded to 15 us. Details in [readout window](readout_window.md#history).
- The refactor (design v3) turns the fixed switch into an automatic per-step switch.

## Known issues

- Carry-overs are silently discarded at every switch to regime B; the fitted `pulse_freq` from
  `transmission_fit` never reaches single-shot steps, and the calibrated `res_phase` from
  `active_reset_verify` never reaches `single_shot`.
- `qubit_optimize` raises `KeyError: 'pi2_SS'` if called under regime A.
- `t1_ss` plays `cfg["qubit_gain"]`; it is a pi pulse only under regime B.
- Experiments write into their own cfg during acquire and display (`pulse_freq` left at the last
  sweep point, `reps`, `rounds`, `qubit_gain`, `Pulse`, `pulse_01`, `variable_wait`, `length`).
  The saved `.json` / h5 `config` attribute shows these mutated values, not the values the step
  passed in. If `transmission_fit` runs with `fit=False` or the fit fails, the saved `pulse_freq`
  is the last sweep point, not the centre.
- `two_tone_charge_dispersion_quasicw` writes the probe frequency it found into the caller's
  `ChargeDispersion` parameter dict; a later `charge_dispersion_quasicw` in the same session uses
  that value. This leak is preserved by the refactor (regression label
  `Run2ToneChargeDispersionQuasiCW+RunChargeDispersionQuasiCW`).
- Several steps move the yoko and do not return it; later steps then run at another bias while
  `current_voltage` in their cfg still shows the session value. See
  [hardware](../hardware.md#charge-bias-yoko).
