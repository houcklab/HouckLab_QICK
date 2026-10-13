# cw_tones: constant_two_tone, constant_tone

Classes `ConstantTwoTone` and `SingleTone` (see `qicklab.experiments.cw_tones`). Regime **A**.

## What it measures

Nothing: these steps only put tones on the lines, for checks with an external instrument
(spectrum analyser, VNA, mixer/line debugging). No readout is declared and no data are
saved.

- **constant_two_tone**: resonator tone at `pulse_freq` and qubit tone at `qubit_freq`,
  played simultaneously and back to back.
- **constant_tone**: resonator tone only. The legacy runner labelled it "determine cavity
  frequency".

## Pulse sequence

constant_two_tone (`AveragerProgram`, repeated `reps` times by the tProc, 1000 in regime A):

```
res_ch    [====== const pulse_freq, pulse_gain, tone_length ======][====== ... ======][== ...
qubit_ch  [====== const qubit_freq, qubit_gain, tone_length ======][====== ... ======][== ...
          ^ both start together; sync_all; next rep
```

constant_tone (`AveragerProgram` with `reps = 100000`, `rounds = 1000`, acquired 100 times):

```
res_ch    [== const pulse_freq, pulse_gain, length ==][== ... ==][== ... ==] ...
```

| Item | constant_two_tone | constant_tone |
|---|---|---|
| Generators | `res_ch` (gen 0), `qubit_ch` (gen 1), phase 0 | `res_ch` only |
| Tone length | `min(us2cycles(tone_length, gen_ch), 65535)` generator cycles | `length` us (regime A: `adc_trig_offset + readout_length` = 15.3 us on CSTQ03) |
| Readout / trigger | none / none | none / none |
| Gaps | one `sync_all` between reps (small, not measured) | same |

## How to run

```python
PLAN = [R.constant_two_tone()]              # tones from the device; tone_length from the tones group
PLAN = [R.constant_tone()]
```

`Session(tones=R.tones(tone_length=151))` sets the tone length.

## Parameters

| Name (legacy key) | Legacy default | Units | Meaning |
|---|---|---|---|
| `tone_length` | 151 | us | Length of each two-tone pulse (group `tones`) |
| `pulse_freq` | device readout frequency (or carry-over) | MHz | Resonator tone |
| `pulse_gain` | device readout gain | DAC | Resonator amplitude |
| `qubit_freq` | device qubit frequency (`qubit_pulse`) | MHz | Qubit tone (two-tone only) |
| `qubit_gain` | `Spec_relevant_params["qubit_gain"]` = 1000 | DAC | Qubit amplitude: the regime-A **spectroscopy** gain, not the pi gain |
| `reps` | 1000 (BASE_CONFIG) | - | Tones per program (two-tone) |
| `length` | 15.3 (regime A) | us | Resonator tone length (constant_tone) |

## Outputs

None. `ConstantTwoTone` creates the empty folder `<outerFolder>ConstantTwoTone/ConstantTwoTone_<date>/`
on every iteration; `SingleTone` creates `<outerFolder>TransmissionFF/...`. Nothing is
written into them. `ConstantTwoTone.acquire()` prints the frequencies, gains and tone length.

## Analysis

None.

## Findings & notes

- The pulse-length register is 16 bits, so one tone is capped at 65535 generator cycles.
  At the 430.08 MHz generator fabric clock of the current board that is 152.4 us; the
  CSTQ03 value `tone_length = 151` us sits just under the cap. Longer values are silently
  clipped to the cap. On another board, derive the cap from the soccfg generator
  `f_fabric`.
- The output is near-CW, not CW: consecutive reps are separated by the tProc `sync_all`
  overhead.

## Known issues

- constant_two_tone runs a loop of 1,000,000 iterations, each building a new experiment
  object (creating a folder) and reprogramming the board. There is no stop condition; stop
  it with Ctrl-C. The tProc program in flight finishes its reps afterwards.
- `declare_gen` is called without `mixer_freq` and `freq2reg` without `ro_ch`; this is only
  correct while `mixer_freq = 0`.
- constant_tone calls `acquire()` on a program with no readout declared; whether that
  returns cleanly has not been verified on hardware. Nominal duration if it does:
  1e5 reps x 1000 rounds x ~15.3 us is about 25 min per acquire, x100 acquires (about 42 h).
- constant_tone overwrites `reps`/`rounds` in the config it was given (100000 / 1000).
