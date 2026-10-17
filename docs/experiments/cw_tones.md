# cw_tones: constant_two_tone, constant_tone

Classes `ConstantTwoTone` and `SingleTone` (see `qicklab.experiments.cw_tones`). Regime **A**.

## What it measures

Nothing: these steps only put tones on the lines, for checks with an external instrument
(spectrum analyser, VNA, mixer/line debugging). No readout is declared and no data are
saved apart from the settings (JSON, below).

- **constant_two_tone**: CW resonator tone at `pulse_freq` and CW qubit tone at `qubit_freq`,
  together.
- **constant_tone**: CW resonator tone only. The legacy runner labelled it "determine cavity
  frequency".

The step turns the tones on, **holds them until you press Enter** (or for `hold_s` seconds),
then stops them with `soc.reset_gens()` and returns, so the next step of the plan starts with
quiet lines.

## Pulse sequence

One tProc program per step (`QickProgram`, no loop, no readout), started once:

```
res_ch    [== const pulse_freq, pulse_gain, mode=periodic ==][== repeated by the gen ==][== ...  until reset_gens
qubit_ch  [== const qubit_freq, qubit_gain, mode=periodic ==][== repeated by the gen ==][== ...  (two-tone only)
          ^ both queued at t = 0; then `end`
```

A `periodic` const pulse is replayed back to back by the signal generator itself after the tProc
has reached `end`, until another pulse is queued on that generator. The phase accumulator is
not reset (`phrst = 0`), so the output is a true CW tone: the pulse length only sets the
repetition period, not a gap.

| Item | constant_two_tone | constant_tone |
|---|---|---|
| Generators | `res_ch` (gen 0), `qubit_ch` (gen 1), phase 0 | `res_ch` only |
| Resonator gen | `declare_gen(res_ch, nqz, mixer_freq, ro_ch=ro_chs[0])`, `freq2reg(pulse_freq, ro_ch=ro_chs[0])`, as `CavitySpecFF` | same |
| Period (repeated segment) | `min(us2cycles(tone_length, gen_ch), 65535)` generator cycles | `us2cycles(length, gen_ch)` generator cycles (regime A: `adc_trig_offset + readout_length` = 15.3 us on CSTQ03) |
| Readout / trigger | none / none | none / none |
| Gaps | none (continuous phase) | none |
| Stop | `soc.reset_gens()` in a `finally` | same |

## How to run

```python
PLAN = [R.constant_two_tone()]              # tones from the device; tone_length from the tones group
PLAN = [R.constant_tone()]
```

`Session(tones=R.tones(tone_length=151))` sets the two-tone period. From a runner,
`run_constant_two_tone(ctx)` / `run_constant_tone(ctx)` wait for Enter;
`run_constant_two_tone(ctx, {"hold_s": 60})` holds for 60 s instead.

How the hold ends:

- **Enter** (or `hold_s` elapsed): tones stopped, the step returns, the plan continues.
- **Ctrl-C**: tones stopped, then the `KeyboardInterrupt` propagates (the plan stops).
- **No usable stdin** (stdin closed, or captured as under pytest and the golden harness) and no
  `hold_s`: a warning is printed and the tones are stopped at once. Pass `hold_s` when running
  non-interactively.
- Any error while starting the program also stops the tones.

**Stray-tone hazard.** A periodic output keeps playing after the program ends, after Python
returns and after the Pyro client disconnects; only `reset_gens()` (or a later pulse on the same
generator) replaces it. The step therefore never returns with the tones on. If a session is
killed hard (process killed, PC crash) while the tones are on, run `soc.reset_gens()` before
the next measurement: a later program that does not use the qubit channel would otherwise run
with a CW tone on that line.

## Parameters

| Name (legacy key) | Legacy default | Units | Meaning |
|---|---|---|---|
| `tone_length` | 151 | us | Repetition period of the periodic two-tone segment (group `tones`); does not change the output |
| `pulse_freq` | device readout frequency (or carry-over) | MHz | Resonator tone |
| `pulse_gain` | device readout gain | DAC | Resonator amplitude |
| `mixer_freq` | 0.0 | MHz | Resonator DAC mixer, passed to `declare_gen` (both steps) |
| `qubit_freq` | device qubit frequency (`qubit_pulse`) | MHz | Qubit tone (two-tone only) |
| `qubit_gain` | `Spec_relevant_params["qubit_gain"]` = 1000 | DAC | Qubit amplitude: the regime-A **spectroscopy** gain, not the pi gain |
| `length` | 15.3 (regime A) | us | Repetition period of the resonator segment (constant_tone) |
| `hold_s` (run `params`, not cfg) | None = wait for Enter | s | How long to hold the tones |

`reps`/`rounds` are not used (and no longer overwritten in the caller's config).

## Outputs

One experiment object per step, so one folder:
`<outerFolder>ConstantTwoTone/ConstantTwoTone_<date>/` (`SingleTone`:
`<outerFolder>TransmissionFF/...`) holding the run's settings: `save_config()` writes the cfg
as `<path>_<timestamp>_data.json` and as the `config` attribute of the `.h5` (no datasets),
plus `<path>_<timestamp>_data_provenance.json` ([provenance](../architecture.md#provenance)).
`ConstantTwoTone.acquire()` also prints the frequencies, gains and period, and returns them.

## Analysis

None.

## Findings & notes

- The pulse-length register is 16 bits (3 to 65535 generator cycles). In periodic mode the
  length is only the repetition period, so the cap no longer limits how long the tone is on.
  At 430.08 MHz `tone_length = 151` us is 64942 cycles; on a board whose generator fabric
  clock is faster the value is clipped to 65535 cycles, which is harmless.
- Before 2026-10-16 (F69) the tones were near-CW, rebuilt from one-shot pulses: two-tone
  reprogrammed the board up to 1,000,000 times (a new experiment object and an empty folder
  each time, dead time at every program boundary, i.e. every `reps x tone_length` = 151 ms
  plus the Python/Pyro restart), and constant_tone ran 100 `acquire()` calls of
  1e5 reps x 1000 rounds (about 42 h nominal) on a program with no readout. The two programs
  also declared the resonator generator differently (two-tone without `mixer_freq`/`ro_ch`).
  Check the new output once on a spectrum analyser (no fridge needed).

## Known issues

- None specific. `declare_gen` of the qubit generator takes no `mixer_freq` (as in every other
  qubit program); this is only correct while that generator has no mixer in use.
