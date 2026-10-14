# active_reset: hardware measurement-feedback reset to |g>

Active reset is not a step on its own. It is a block that
[modified_ramsey](modified_ramsey.md) (`ModifiedRamsey`) and
[active_reset_verify](active_reset_verify.md) (`ActiveResetVerify`) can put at the
start of every shot. This page explains how it works, how it is calibrated, and
why it has failed before. Code: see `qicklab.core.active_reset` (`ActiveResetMixin`,
used by ModifiedRamsey; ActiveResetVerify still has its own copy, see
[active_reset_verify](active_reset_verify.md#known-issues)) and
`qicklab.runs.active_reset` (calibration helpers).

## What it does

For each reset cycle the tProc measures the qubit, reads the accumulated I value of
that readout back into a register, and compares it with a threshold. If the qubit
looks like |e> it plays a pi pulse. If it looks like |g> it skips the pi pulse.
After `reset_cycles` rounds the qubit should be in |g>, so the experiment does not
depend on thermal relaxation between shots.

## Pulse sequence

One reset cycle. With `reset_cycles = N` the block repeats N times.

```
res_ch   ──[ readout tone (length) ]──────────────────────────────────────
ADC      ───────[ window: readout_length ]─────────────────────────────────
              ^ adc_trig_offset
tProc         measure ─┬─ syncdelay = reset_readout_relax_delay ─┐
                       │                                          read I -> r_read
                       │                                          r_read += cmp_offset
                       │                                          condj(r_read <op> r_thresh) ─┐
qubit_ch                                                          [ pi, phase 0 ]              │ (skip)
                                                                  RESET_DONE_k <───────────────┘
                                                                  sync_all()
after N cycles: sync_all(post_reset_wait)
```

- Readout: `res_ch`, `ro_chs[0]`. The readout tone and ADC window are the same as
  the rest of the experiment (see [single_shot](single_shot.md#pulse-sequence) for
  the cross-clock tone extension).
- The corrective pi uses `pi_gain` and the shared 4σ gaussian envelope. It plays at
  the experiment's **drive** frequency: `f_ge` in the standard Ramsey scheme,
  `f_ge - df/2` in the symmetric scheme (see Known issues).
- The `RESET_DONE_k` label sits before the shared `sync_all()`. QICK reserves the pi
  pulse's full duration on both branches, so a shot costs the same time whether or
  not the pi played.
- No trigger pin is fired by the reset block.

## How it decides

1. **The tProc only sees raw I.** The feedback compares the accumulated in-phase
   value only. |g> and |e> must therefore separate along I. Calibration rotates the
   readout phase `res_phase` until they do.
2. **Threshold units.** `readout_threshold` is given in normalised units: the
   accumulated I divided by the readout window length in readout-clock cycles,
   `ro_norm = us2cycles(readout_length, ro_ch)`. These are the same units as the IQ
   plots of [single_shot](single_shot.md). The program multiplies by `ro_norm`
   before writing the register: `raw_threshold = round(readout_threshold * ro_norm)`.
3. **Comparison direction.** `reset_ground_below_threshold = True` means |g> has I
   below the threshold. The pi is skipped when `I < threshold` (or `>` when False).
4. **Sign-safe compare.** Both operands get the same positive offset:
   `r_thresh = raw_threshold + cmp_offset` and `r_read += cmp_offset` right after
   the `read`. The offset is `cmp_offset = int(ro_norm) << 15`.
5. **Input channel.** The tProc `read` instruction takes a tProc *input* channel,
   `soccfg["readouts"][ro_ch]["tproc_ch"]`, not the readout index. The program
   resolves it and raises if the readout has no tProc input.

### Why `cmp_offset = int(ro_norm) << 15`

- The deployed tProc compares as if **unsigned**. On TATQ01/BFE (Q2, RFSOC_147),
  2026-06-05/06, all 31 saved ActiveResetVerify sweeps failed. The corrective pi
  fired on every shot whose accumulated I was negative: a negative two's-complement
  I reads as a huge positive number. Ground-state damage tracked the below-zero
  fraction of the g blob, and a sweep with g_I ≈ 0 lost exactly half its ground
  shots. Adding the same large positive constant to both operands keeps them
  positive, so signed and unsigned comparisons agree.
- **Size of the offset.** The accumulator sums `ro_norm` decimated samples of at
  most 15 bits (12-bit ADC + 3 bits of decimation gain, per the overflow note in
  `qick_asm.declare_readout`), so |raw I| ≤ `ro_norm · 2^15`. The first fix
  (2026-06-11/12) used a fixed `2^24`. That is too small for any window longer than
  2^24 / 2^15 = 512 readout cycles, about 1.7 µs at f_output 307.2 MHz (the code
  comment says "~0.5 µs", which does not follow from its own bound). With the CSTQ03 readout (15 µs at f_output 307.2 MHz,
  `ro_norm = 4608`) the bound is 4608·2^15 = 150,994,944 and 2^24 = 16,777,216 is
  about **9x too small** (finding of 2026-07-28). A shot below −2^24 still wraps
  around and the pi fires on the wrong branch. No error is raised.
- A threshold check alone cannot catch this. The threshold sits between the blobs,
  but individual shots sit on the blobs.
- **Limits.** Both operands must fit a 32-bit signed register, and the immediate must
  stay below 2^30 (the `safe_regwi` plain-`regwi` window). The program raises if
  `cmp_offset ≥ 2^30` (shorten the window) or if `|raw_threshold| ≥ cmp_offset`
  (the readout saturates the accumulator).
- History: the 2^24 offset was added 2026-06-11 (BFE) and ported to this code
  2026-06-12. It was replaced by `int(ro_norm) << 15` in `ModifiedRamsey` on
  2026-07-28. `ActiveResetVerify` still carries 2^24 (see Known issues).

### Reset readout k is taken before flip k

`ModifiedRamsey` saves every reset readout (`reset_shots_i/q`, shape
`(reset_cycles, reps)`). Readout k measures the state **before** corrective flip k.
Row 0 is the pre-reset thermal or leftover population, and row k only validates the
k flips before it. The last flip is never observed. Use
[active_reset_verify](active_reset_verify.md) before trusting initialisation.

### The 6/κ delay

`reset_readout_relax_delay` is the wait between the end of the conditioning readout
and the corrective pi. It must be at least about **6/κ** of the readout resonator, so
that the pi acts on a photon-free qubit that is not Stark-shifted. The value 5 µs
equals 6/κ for the TATQ01/BFE Q2 resonator (κ/2π = 190 kHz, 1/κ = 0.84 µs, measured
2026-06-06). κ for the CSTQ03 readout resonator has **not** been measured. Verify it
and trim the delay if the linewidth is wider. Keep the value identical in
`modified_ramsey` and `active_reset_verify` so that the verification tests the same
timing.

## How to run

Enable it on the step that uses it, then verify it:

```python
PLAN = [
    R.active_reset_verify(),                       # regime A, same config as MR
    R.modified_ramsey(use_active_reset=True,       # regime A
                      reset_cycles=1, reset_readout_relax_delay=5.0),
]
```

With `use_active_reset=True` the modified_ramsey run does three things:

1. It calls `calibrate_active_reset_readout` before anything else.
   - The first SingleShot g/e run measures the g→e axis angle φ.
   - `res_phase` is set to `base + deg2reg(-φ)`. If that does not align g→e with I,
     `base + deg2reg(+φ)` is tried. The run keeps whichever leaves the smaller |Q|
     separation; the sign convention of `deg2reg` is never trusted.
   - The loop stops early when Q separation ≤ 0.1 × I separation. Otherwise it warns.
   - Each trial re-measures, so the full calibration takes 2–3 SingleShot
     acquisitions, all saved under `SingleShot_MRCalib`.
2. It sets `readout_threshold = (g_I + e_I)/2` and
   `reset_ground_below_threshold = g_I < e_I`, both from the rotated blobs.
3. It re-derives the threshold every time the separator is recalibrated
   (`ss_recalib_every_n_cycles`). The derivation is idempotent, so it tracks a
   drifting threshold.

Rules:

- A manual `readout_threshold` overrides the automatic one. None (auto) is
  recommended.
- `use_active_reset=True` requires `use_apriori_separator=True`. Otherwise the run
  raises before acquiring.
- `calibrate_active_reset_readout` must run **before** the a-priori separator, so
  that shot classification uses the rotated frame.

## Parameters

Keys are the legacy cfg / `ModifiedRamsey_params` names. Defaults are the CSTQ03
runner values; the code fallback is given in the meaning column when it differs.

| Key | Default | Units | Meaning |
|---|---|---|---|
| `use_active_reset` | True (MR), per condition (ARV) | bool | Prepend the reset block to every shot. Code fallback False. |
| `reset_cycles` | 1 | count | Measure→feedback rounds per shot. More rounds give better ground fidelity at the cost of more readouts. |
| `readout_threshold` | None (auto) | normalised I | Manual threshold. None derives it from the rotated SingleShot blobs. |
| `reset_ground_below_threshold` | True | bool | \|g> lies below the threshold in I. Overwritten by the calibration. |
| `reset_readout_relax_delay` | 5.0 | µs | Wait after each reset readout before the conditional pi. Should be ≥ ~6/κ. Code fallback 1.0. |
| `post_reset_wait` | 0.0 | µs | Settle time after the whole reset block. |
| `pi_gain` | device pi gain | DAC | Gain of the corrective pi (same envelope as the Ramsey pulses). |
| `res_phase` | rotated by calibration | tProc phase register units | Readout phase. Rotated in place so g/e separate along I. |

## Outputs

The reset itself writes nothing. Its traces are:

- In `ModifiedRamsey` h5: `reset_shots_i`, `reset_shots_q` (shape `(reset_cycles,
  reps)`), `readout_threshold`, `reset_ground_below_threshold`, `reset_cycles`,
  `reset_readout_relax_delay_us`, `post_reset_wait_us`.
- The analysis computes the per-row ground fraction (`reset_pre_correction_g_fraction`
  in `<base>_continuous_analysis.json`) and plots `<base>_continuous_reset_success.png`.
  `converged` is only set when a post-reset verification readout exists (> 0.9 ground
  fraction). Modified Ramsey has none, so it always warns.
- The calibration prints `res_phase` (register units), threshold, sign, g_I and e_I.
  Cross-check these against the ARV diagnostics.

## Findings & notes

- TATQ01/BFE Q2, 2026-06-05/06: corrective pi fired on every negative-I shot → the
  deployed compare is unsigned. Fixed with the sign-safe offset.
- 2026-07-28: the fixed 2^24 offset is about 9x too small for a 15 µs window. The
  correct offset is `int(ro_norm) << 15`. It is verified on the warm RFSoC at
  192.168.0.103 by the timing harness (`tests/hardware/verify_modified_ramsey_timing.py`):
  - offset sizing, equal-time condj branches and register non-collision all pass;
  - live rep cadence for reset ×1 (38.85 µs) and ×2 (60.25 µs) is within 3% of the
    schedule, with a real ~50/50 branch split.

  Whether the reset actually drives the qubit to |g> still needs a cold device.
- Registers: `r_wait = 3`, `r_read = 4`, `r_thresh = 5` on the qubit page. Pulse
  registers are allocated top-down per page, and the AveragerProgram loop counters
  live on page 0, so 3/4/5 are free on any page.
- Expected ceiling of a correct reset with `reset_cycles = 1` (lab analysis,
  2026-07-28): one feedback round pays the readout error twice, once in the decision
  and once in the verification read. So prep|e>+ON ≈ 0.74 and prep|g>+ON ≈ 0.78, not
  the thermal baseline and not the force-pi value. Even `reset_cycles = 2` only
  reaches about 0.78. Do not read a correct reset as a failure.

## Known issues

- **Read latency, not fixed on this branch.** The `read` after `measure()` can pick up
  the *previous* rep's readout.
  - Cause: `measure(wait=True)` stalls the core, but `syncdelay` only advances the
    tProc time reference. The read executes before the accumulated word of the
    current readout has crossed into the tProc domain (tens to ~150 ns).
  - Evidence (TATQ01-SiO2 Q3, 2000 reps/condition): reset ON gave P(|g>) = 0.539
    (prep g) and 0.497 (prep e), against 0.847 for force-pi. The correlation between
    read0 of rep n and read4 of rep n−1 was −0.723 (prep e) and +0.750 (prep g),
    against |corr| ≤ 0.04 in the controls.
  - Fix: an explicit `wait_all(...)` stall between the reset readout and the `read`
    (commit 4be2b7a, Alex Place, 2026-07-28, branch `bfg_code`). It is not in the
    code this package was built from.
  - What you will see: corrective-pi success near 0.5, independent of
    `reset_readout_relax_delay`.
- `active_reset_verify` uses its own copy of the reset with the old fixed
  `cmp_offset = 2^24`. It also passes the readout index to `read` instead of the tProc
  input channel, and has no `cmp_offset < 2^30` guard. With a 15 µs window, shots
  with raw I < −2^24 wrap, so ARV does **not** exercise the mechanism
  `modified_ramsey` uses.
- In the symmetric Ramsey scheme and in the `drive_detuned` control, the corrective
  pi plays at the drive frequency. That is df/2 or more away from each parity branch,
  so the reset flip is off-resonant.
- `calibrate_active_reset_readout` adds `deg2reg(±φ)` to `res_phase` without wrapping
  modulo the full phase range. The register value can go negative or exceed the range.
- The calibration ignores modified_ramsey's `ss_calib_shots` and always uses 1000
  shots. Its `max_align_iter` argument is unused.
- The rotated `res_phase` persists in the session config for later regime-A steps. It
  is reset to the device value at the next switch to regime B.
