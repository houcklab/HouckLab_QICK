# Timing and units

What a number in a cfg means, how it becomes a register value, and how time advances inside a
tProc v1 program.

## Clocks

| Clock | Where | Lab board (read from `QickConfig`, October 2026) | One cycle |
|---|---|---|---|
| tProc `f_time` | `soccfg["tprocs"][0]["f_time"]` | 430.08 MHz | 2.32515 ns = 0.00232515 us |
| generator fabric `f_fabric` | `soccfg["gens"][ch]["f_fabric"]` | 430.08 MHz (gen 0 and gen 1) | 2.32515 ns |
| readout output `f_output` | `soccfg["readouts"][ch]["f_output"]` | 307.2 MHz (ro 0) | 3.255 ns |
| averages buffer | `avg_maxlen` | 16384 | |
| decimated buffer | `buf_maxlen` | 1024 samples | |

Read these from `soccfg` in code; do not hard-code them. Print the full board config with
`print(soccfg)` after connecting.

## Converting values: always use the QICK helpers

| Helper | Converts | Clock / range |
|---|---|---|
| `us2cycles(us)` | us -> cycles | **tProc** clock when no channel is given |
| `us2cycles(us, gen_ch=ch)` | us -> cycles | generator fabric clock |
| `us2cycles(us, ro_ch=ch)` | us -> cycles | readout output clock |
| `cycles2us(n, ...)` | cycles -> us | same rules |
| `freq2reg(f_mhz, gen_ch=ch, ro_ch=ro)` | MHz -> DDS register | rounds to a frequency both the generator and the readout can represent, so the downconversion matches the tone; pass `ro_ch` for resonator tones |
| `deg2reg(deg, gen_ch=ch)` | degrees -> phase register | values above 360 wrap |

`us2cycles` rounds to the nearest cycle. Never compute register values by hand: values must
round-trip through the firmware's quantisation. A raw integer in a program (`synci(200)`,
`sync_all(200)`) is a number of tProc cycles.

Rule of thumb for which clock owns a duration: the tProc owns waits, trigger times and the ADC
trigger offset; the generator owns pulse and envelope lengths; the readout owns the ADC window.
See [readout window](readout_window.md#three-clocks-one-window) for the case where all three meet.

## Units

| Quantity | Unit | Keys (examples) |
|---|---|---|
| Frequencies | MHz | `pulse_freq`, `f_ge`, `qubit_freq`, `mixer_freq`, `SpecSpan`, `TransSpan`, `df`, `cd_max_mhz`, `kappa_mhz` |
| External readout LO | **Hz** | `cavity_LO` (code divides by 1e6) |
| Times | us | `relax_delay`, `sigma`, `readout_length`, `adc_trig_offset`, `length`, `flattop_length`, `T1_step`, `T2_step`, `sample_period_us` |
| Settle times | s | `charge_settle_s`, `settle_s` |
| Charge bias | V | `bias_v`, `voltage_start/end/step` |
| Charge-dispersion period | mV | `cd_period_mv` |
| Drive / readout amplitude | DAC units, 0..32767 | `pulse_gain`, `qubit_gain`, `pi_gain`, `pi2_gain`, `gain` |
| Readout phase | **tProc phase-register units**, not degrees | `res_phase` |
| TWPA bias | uA (scripts), A (yoko SCPI) | see [hardware](../hardware.md#twpa-instruments) |

### Frequencies

- All frequencies in cfg are what the generator is programmed to. With `cavity_LO` = 0 and
  `mixer_freq` = 0 (the current wiring) that is the absolute frequency. Transmission sweeps keep
  IF-style MHz in `fpts` and plot `(fpts + cavity_LO/1e6)/1e3` GHz. The hanger fit runs on `fpts`,
  so the fitted f0 is absolute only while `cavity_LO` = 0.
- `mixer_freq` (MHz) is the readout DAC mixer/NCO. Only `CavitySpecFF`, `QubitSpecSliceFF`,
  `ChiShift`, `SingleTone`, `ChargeDispersionQuasiCW` and `ZeroSpanParity` pass it to
  `declare_gen`; the others work only because it is 0.0.
- The DDS accepts `[-f_dds/2, +f_dds/2]` (the `freq2reg` range check), not `[0, f_dds]`.
- Sweep grids are not all alike. Two-tone spec: `start = f - SpecSpan`, `step = 2*SpecSpan/N`, N
  points, so the last point is `f + SpecSpan - step` (half-open). `ChiShift`: same half-open
  rule around `pulse_freq + cavity_shift`. `CavitySpecFF`: `np.linspace(f - TransSpan,
  f + TransSpan, TransNumPoints)`, inclusive.

### Gains

DAC gain is a signed 16-bit amplitude; usable range 0..32767 (full scale). It is linear in drive
amplitude. Code clamps scans to 32767 (`qubit_optimize`), and AutoCoherence caps its
frequency-calibration gain at 30000. `Device.validate()` rejects gains outside 0..32767 and a
pi/2 gain larger than the pi gain.

### Nyquist zones

`nqz` (readout DAC, `res_ch`) and `qubit_nqz` (qubit DAC, `qubit_ch`) are passed to
`declare_gen`; QICK uses them to pick the DAC output mode (1 = first Nyquist zone, 2 = mix-mode
for the second zone). The lab board uses `nqz` = 2 for the resonator ("refers to cavity" in the
legacy config) and `qubit_nqz` = 1 for the qubit. A new chip in another band may need different
values, set per device in `Setup.board_overrides`. The DAC sampling rate is
`soccfg["gens"][ch]["fs"]` (the Nyquist frequency is `fs/2`); check it before putting a new
chip's frequencies in a device file. `Device.validate()` checks frequencies against the declared
zones.

## Pulse envelopes

- Gaussian pulses are `4*sigma` long, both measured in generator cycles:
  `sigma = us2cycles(sigma, gen_ch=qubit_ch)`, `length = us2cycles(4*sigma, gen_ch=qubit_ch)`.
- Flat-top pulses (`flattop_length` not None) use the same Gaussian as rise/fall and a flat
  segment of `flattop_length`. The flat segment does not follow a register-swept gain (only the
  ramp `gain` register is updated), so a register-swept Rabi is invalid with flat-top;
  `amplitude_rabi` switches to the software sweep `AmplitudeRabiFF_N` when `flattop_length` is set.
- Gains calibrated for a flat-top pulse do not transfer to a plain Gaussian. `ModifiedRamsey`
  refuses `flattop_length`. `T2R`, `T1_SS`, `ChargeDispersion` and `QubitSpecSliceFF` ignore it and
  play a plain Gaussian at the given gain.
- Envelope memory is 65536 samples per generator (16 samples per 430.08 MHz fabric cycle, so about
  9.5 us of envelope in total). A sigma = 2 us Gaussian takes about 55056 samples; two copies
  (about 110112) fail with `AxisSignalGen: buffer length must be 65536 samples or less`. Share one
  envelope between pi and pi/2 (vary the gain).
- Pulse phases: `arb` Gaussian pulses in Rabi, T1, Gaussian spec and chi shift are played at
  `deg2reg(90)`; flat-top at 0; single shot, T2R and the T2E pi/2 pulses at 0; T2E pi pulses at 90
  (CPMG). `res_phase` is passed raw as a register value.
- Constant pulses and the tProc length register are 16 bit: at most 65535 generator cycles,
  152.38 us at 430.08 MHz. `constant_two_tone` caps `tone_length` there (CSTQ03 uses 151 us);
  `zero_span_parity` checks `sample_period_us` / `capture_length_us` against it.

## How time advances in a tProc v1 program

```
synci(n)        advance the reference time by n tProc cycles
sync_all(n)     wait until every generator and readout timestamp has passed, then add n
sync(page, r)   advance by the value in register r (a swept wait)
measure(..., adc_trig_offset=o, wait=True, syncdelay=d)
                play the readout tone, trigger the ADC o cycles later, wait for the
                readout (waiti), then sync_all(d); d is the relax delay
```

- Only `synci` (and the `sync` family) advance tProc time. The `waiti` that `measure(wait=True)`
  emits does not.
- QICK tracks generator and readout timestamps in their native cycles converted to tProc cycles;
  `sync_all()` truncates the largest to an integer tProc cycle.
- The rep period is the sum of the `synci` and `sync` advances in the loop body. `ModifiedRamsey`
  and `UndrivenSingleShot` compute it from the compiled program (`scheduled_rep_period_us`) and use
  it as the time axis of shot records. A register-valued `sync` in the loop makes the period not a
  compile-time constant; `UndrivenSingleShot` raises in that case.
- Streamer wall-clock statistics include polling and transfer latency. Use the scheduled period,
  not wall-clock time, as the physical time base (it includes active-reset overhead).

### Waits are between pulse edges

`sync_all()` waits for the **end** of the last envelope, so a programmed wait is the gap between
the trailing edge of one pulse and the leading edge of the next. Free precession in a Ramsey
experiment accrues from pulse centre to pulse centre.

```
     pi/2                     pi/2
   |<-4s->|<---- gap ---->|<-4s->|
       ^                       ^
       centre <-- gap + 4 sigma --> centre
```

| Step | Programmed wait | Centre-to-centre |
|---|---|---|
| `t1` | gap from the end of the pi pulse to the readout tone | (not a Ramsey; wait counted from pulse end, standard for T1) |
| `t2_ramsey` | x-axis = edge gap | gap + 4 sigma |
| `t2_echo` | x-axis = total edge gap, split into `num_pi_pulses + 1` segments | each segment + pulse widths |
| `charge_dispersion_ramsey` | `1/df` us as edge gap | gap + 4 sigma |
| `modified_ramsey` | gap = `tau/n_gaps - 4 sigma` (no pi: `tau - 4 sigma`; echo: `(tau - 8 sigma)/2`) | **tau** (corrected; see history) |

History: `modified_ramsey` programmed tau as the edge gap until the 2026-07-28 timing audit, so
the realised centre-to-centre interval overshot by 4 sigma (8 sigma with echo), worst when the
doublet is best resolved (large df, short tau). Fixed; the hardware check confirms the realised
centre-to-centre interval equals `1/(2 df)` within 2 tProc cycles.

### T2E step quantisation

`t2_echo` splits each wait into `num_pi_pulses + 1` equal segments and steps the segment register
by `step/(n+1)`. To keep every segment an integer number of tProc cycles the run function sets

    k    = floor(T2_max_us / (0.00232515 * (n + 1) * T2_expts))
    step = 0.00232515 * (n + 1) * k            # us

Example (CSTQ03 runner values): `T2_max_us` = 20, `T2_expts` = 121, n = 1 -> k = 35, step =
0.16276 us, last point (120 x step) about 19.53 us. If k = 0 the step prints "Step size is 0!" and stops:
raise `T2_max_us` or lower `T2_expts`. `auto_coherence` uses the same quantum; the two must agree.
`num_pi_pulses` must be odd and >= 1: `T2EProgram.initialize` raises `ValueError` otherwise (see
[t2_echo](../experiments/t2_echo.md#refocusing-condition)).

## Registers

| Register | Use |
|---|---|
| 3 (`r_wait`) | swept or computed wait, on the qubit page |
| 4 (`r_phase2`) | Ramsey phase advance (T2R); `r_read` in the active-reset block |
| 5 (`r_thresh`) | active-reset threshold |
| page 0: 13-21 | reserved by the QICK framework (`AveragerProgram` loop counters `rjj` = 14, `rcount` = 15, trigger word 16) |
| 22-31 (one-manager page), 12-31 (two-manager page) | pulse registers, allocated top-down |

Registers 3, 4 and 5 are free on any page. The tProc `read` instruction takes the tProc **input**
channel (`soccfg["readouts"][ch]["tproc_ch"]`), not the readout index; they coincide on the
current firmware (`tproc_ch` = 0 for readout 0), but resolve it explicitly.

## Known issues

- Wait-sweep programs (`T1FF`, `T2EMUX`, `T2R`) load `cfg["start"]` into the wait register as raw
  tProc cycles but label the x-axis as `start + i*step` in us. Correct only for `start = 0`, which
  every run function passes.
- `0.00232515` is hard-coded in the coherence run functions, AutoCoherence and a dead AWG
  helper (which used `0.00232515/16` per envelope sample). A board with another tProc clock needs
  `soccfg.cycles2us(1)` instead.
- `T2R` ignores `flattop_length` and always plays a 4-sigma Gaussian at `pi2_gain`; if `pi2_gain`
  was calibrated for flat-top pulses the rotation is wrong.
- The calibration code adds `deg2reg(+-phi)` to `res_phase` without wrapping, so `res_phase` can
  leave the register range.
- `charge_dispersion_ramsey` waits `1/df`; two branches split by `df` then differ in phase by 2 pi
  and are indistinguishable. `modified_ramsey` uses `tau = k/(2 df)`, odd k. Likely a physics bug.
