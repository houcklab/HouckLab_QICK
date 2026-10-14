# Readout window

Every readout plays a constant resonator tone and integrates the ADC signal over a window.
Three cfg keys describe it:

| Key | Unit | Meaning |
|---|---|---|
| `adc_trig_offset` | us | delay from the start of the resonator tone to the ADC trigger |
| `readout_length` | us | ADC integration window |
| `length` | us | resonator tone duration; derived, **do not set by hand** |

```
t = 0                adc_trig_offset                adc_trig_offset + readout_length
|                          |                                       |
[======================= resonator tone (res_ch), length =========]
                           [===== ADC window on ro_chs[0] ========]
```

The tone starts at t = 0 and the ADC starts `adc_trig_offset` later, so the tone must last
through the offset plus the whole window:

    length = adc_trig_offset + readout_length

The config builders set `length` this way. `SingleShotProgram`, `ModifiedRamsey`,
`ActiveResetVerify` and `UndrivenSingleShot` fill it in if missing and raise `ValueError` if a
`length` shorter than the sum is passed.

The legacy builder printed the window at connect; a session prints the same line:
`[readout window] integration 15 us, adc_trig_offset 0.3 us, resonator tone 15.3 us`.

## Three windows, not one

| Window | Set in | Used by | CSTQ03 values (2026-10-01 cooldown) |
|---|---|---|---|
| Regime A | `Readout.window` of the qubit, else `Device.readout_window` (legacy `Readout_Time`, `ADC_Offset`) | every regime-A step: transmission, two-tone, chi shift, Rabi, T1/T2R/T2E, charge dispersion, Modified Ramsey, ActiveResetVerify, the apriori single-shot separator measured inside Modified Ramsey / ActiveResetVerify | 15 us window, 0.3 us offset |
| Single shot (regime B) | `Readout.ss_window`, else `Device.ss_window` (legacy `SS_params["Readout_Time"]`, `["ADC_Offset"]`) | `single_shot`, `undriven_single_shot`, `t1_ss`, `readout_optimize`, `qubit_optimize` | 15 us window, 0.3 us offset |
| Zero span | the step's own `read_length`, `adc_trig_offset` (and `sample_period_us` / `capture_length_us`) | `zero_span_parity` only | strobe: 5.0 us window, 0.488 us offset, 20 us sample period; decimated: 80 us window, 0.488 us offset, 100 us capture |

`auto_coherence` sets its own single-shot window (`ss_readout_time` 15 us, `ss_adc_offset` 1 us)
and, with `auto_readout_opt`, scans `readout_length` 5-30 us (6 points) x `adc_trig_offset`
0.2-3.0 us (5 points); the winners overwrite its single-shot window and the `readout_length`,
`adc_trig_offset`, `length` of its coherence configs. It never writes them back to the device.

`interleaved_coherence` runs `UndrivenSingleShot` under the single-shot window and T1 / T2R / T2E
under the regime-A window; the loop swaps configs for you.

Per-qubit windows differ. The CSTQ03 runner noted single-shot readout time "Q1 15 us, Q5 5 us"
(kept at 15 us), and a 5 us readout length for Q2. Put a qubit-specific window in that qubit's
`Readout(window=..., ss_window=...)`, not in the device default.

## Choosing the window length: SNR vs T1

A longer window integrates more photons and improves the per-shot SNR, until it becomes
comparable to the qubit T1. Past that, the tail of the window averages in population that has
already decayed from |e> to |g>, and the g/e contrast falls again. Start near the device default
and use `readout_optimize` / `auto_coherence` to scan.

Constraints that bound the window:

- The resonator must be empty of photons before the next qubit pulse. Active-reset readouts wait
  `reset_readout_relax_delay` >= about 6/kappa before the corrective pi. 5 us = 6/kappa for the
  TATQ01/BFE Q2 resonator (kappa/2pi = 190 kHz, measured 2026-06-06); kappa of the CSTQ03
  resonators has not been verified.
- The readout accumulator sums the window's samples. qick warns when the declared window exceeds
  2^16 samples (sum-buffer overflow risk; 12-bit ADC + 3 bits of decimation gain into a 32-bit
  signed sum).
- Active reset: the raw accumulated I grows with the window (|raw I| <= `ro_norm * 2^15`, with
  `ro_norm` the window length in readout cycles). See
  [IQ conventions](iq_conventions.md#6-active-reset-thresholds).
- Zero span (checked when `ZeroSpanParity` is constructed): strobe
  `sample_period_us >= adc_trig_offset + read_length + 1.0`; decimated
  `capture_length_us >= adc_trig_offset + read_length`; `us2cycles(sample_period_us or
  capture_length_us)` <= 65535; decimated `read_length` in readout samples <= `buf_maxlen` (1024
  on the lab board).

## Three clocks, one window

Durations are converted to cycles of the clock that owns them:

| Duration | Clock | Lab board value | Conversion |
|---|---|---|---|
| `adc_trig_offset` | tProc | 430.08 MHz | `us2cycles(adc_trig_offset)` |
| `readout_length` (ADC window) | readout output (decimated) | 307.2 MHz | `us2cycles(readout_length, ro_ch=ch)` |
| `length` (tone) | generator fabric of `res_ch` | 430.08 MHz | `us2cycles(length, gen_ch=res_ch)` |

Because each is rounded to an integer of a different clock, the rounded tone can end a fraction
of a cycle before the rounded window. The single-shot family therefore computes the end of the
ADC window in tProc cycles and extends the tone by the minimum number of generator cycles:

    adc_end_tproc  = offset_cycles + window_cycles * f_time / f_output
    tone_cycles    = max(us2cycles(length, gen_ch=res_ch),
                         ceil(adc_end_tproc * f_fabric / f_time - 1e-12))

Worked example with the lab clocks, `adc_trig_offset` = 0.3 us, `readout_length` = 15 us:
offset = round(0.3 x 430.08) = 129 tProc cycles; window = 15 x 307.2 = 4608 readout cycles =
6451.2 tProc cycles; ADC ends at 6580.2 tProc cycles; requested tone = round(15.3 x 430.08) = 6580
generator cycles; required = ceil(6580.2) = 6581. The tone is extended by 1 cycle (2.3 ns).
The program stores `readout_window_cycles`, `readout_tone_cycles` and
`readout_tone_extension_cycles`.

Why it matters: the active-reset threshold is calibrated with `SingleShotProgram` and consumed by
`ModifiedRamsey` and `ActiveResetVerify`. All three must integrate the same physical window and
play the same tone, or the threshold lands in the wrong place. The shared calculation is
`qicklab.core.readout.cover_readout_window`, used by `ModifiedRamsey`. `SingleShotProgram`,
`ActiveResetVerify` and `UndrivenSingleShot` still carry their own copies of the same
arithmetic (UndrivenSingleShot does not store `readout_tone_extension_cycles`).

## History

- `BASE_CONFIG["adc_trig_offset"]` is 1 us. Its old inline note "try varying adc_trig_offset from
  100 to 220 clock ticks" dates from when the value was given in tProc cycles; the key is in us now.
- Until 2026-08-04 the regime-A window was hard-coded to 15 us with the `BASE_CONFIG` 1 us
  offset, and the single-shot window was 15 us / 1 us.
- 2026-08-04 (2026-07-25 cooldown): the regime-A window became a runner setting; both windows
  were set to 10 us / 0.3 us.
- 2026-10-13 (parameters for the 2026-10-01 cooldown): both windows 15 us / 0.3 us.
- The zero-span step has used `adc_trig_offset` = 0.488 us since it was added. The Modified Ramsey
  timing check (`tests/hardware/verify_modified_ramsey_timing.py`) builds its CSTQ03 Q6 cfg with a
  1 us offset, 15 us window and 16 us tone.
- How 0.3 us and 0.488 us were chosen (cable latency, resonator ring-up, a scan) is not recorded.

## Known issues

- **Regime-A programs declare the ADC window in tProc cycles.** `CavitySpecFF`,
  `QubitSpecSliceFF`, `AmplitudeRabiFF`, `AmplitudeRabiFF_N`, `ChiShift`, `T1FF`, `T2EMUX`, `T2R`,
  `ChargeDispersion`, `ChargeDispersionQuasiCW` and `T1_SS` call
  `declare_readout(length=us2cycles(readout_length))` without `ro_ch`. In qick 0.2.334 (tProc v1)
  that length is a number of **readout** samples, so the physical window is
  `readout_length * f_time / f_output` = 1.4 x `readout_length` on the lab board, while the tone
  (tProc cycles = generator cycles here) is `length`. Derived consequence for 15 us / 0.3 us: the
  tone ends at 15.3 us, the window runs from 0.3 us to about 21.3 us, so about 6 us of the window
  integrates after the tone has stopped. Not measured on hardware. Only `SingleShotProgram`,
  `ModifiedRamsey`, `ActiveResetVerify` and `UndrivenSingleShot` use the readout clock.
- `T1_SS` declares its window in tProc cycles but normalises shots by the readout-clock window,
  so its IQ scale differs (by f_time/f_output) from the `single_shot` calibration it reuses the
  threshold and angle from. Plausible, clock-dependent; check before trusting `t1_ss` populations.
- `ZeroSpanParity` declares its readout the same way (`us2cycles(read_length)` without `ro_ch`).
  The zero-span notes report that on some firmware `soccfg` `f_output` is "empirically not the
  decimated rate" seen in a loopback test; this declaration is a plausible cause. The decimated
  buffer-size check and the strobe normalisation inherit the same factor. Sidecars store
  `read_length_us`, `capture_length_us`, `samples_per_capture` and `decimated_fs_source` so
  records can be re-timed later.
- `QubitSpecSliceFF`, `AmplitudeRabiFF`, `AmplitudeRabiFF_N` and `ChargeDispersionQuasiCW` declare
  readouts on ADC channels `[0, 1]` regardless of `ro_chs`; ADC 1 is acquired and saved but not
  analysed.
