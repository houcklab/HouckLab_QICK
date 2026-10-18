# active_reset_verify: differential test of the hardware active reset (ActiveResetVerify)

Recipe: `R.active_reset_verify(...)` (`qicklab.runs.recipes`; every keyword with its default and unit is in the docstring, `help(R.active_reset_verify)`). Session groups: [step table](../running_a_session.md#steps). Generated parameter tables come in phase 6.

## What it measures

This step tests whether the [active reset](active_reset.md) actually puts the qubit
in |g>. A reset started from thermal equilibrium cannot tell a working reset from a
qubit that was already cold, so the test is **differential**: it prepares |g> or |e>
on purpose, runs the reset on or off, and then reads the qubit `n_verify_reads` times
in a row. The result is P(|g>) per read for each condition. Code: see
`qicklab.experiments.active_reset_verify` (program and experiment) and
`qicklab.runs.active_reset` (conditions, overlay and verdict).

## Pulse sequence

One program per condition, `reps` shots each.

```
qubit_ch  ─[ prep pi (if prep_excited) ]─ sync ─┐
                                                │  ┌── reset block × reset_cycles (if use_active_reset) ──┐
res_ch    ──────────────────────────────────────┴──[ readout ]─ reset_readout_relax_delay ─ read/compare ─[pi?]─┘
                                                                post_reset_wait
res_ch    ─[ verify read 0 ]─ verify_relax_delay ─[ verify read 1 ]─ … ─[ verify read N−1 ]─ relax_delay ─▶ next rep
ADC         [ window ]                              [ window ]               [ window ]
```

- Channels: `qubit_ch`, `res_ch`, `ro_chs[0]`. No trigger pin.
- Prep pi and corrective pi: `pi_gain`, 4σ gaussian, phase 0, at `f_ge`. Both use the
  same envelope.
- **Reads per shot** = `reset_cycles` (only when the reset is on) + `n_verify_reads`.
  Only the verification reads are returned. They live at
  `di_buf[reset_cycles + k :: reads_per_rep]`.
- Intermediate verification reads wait `verify_relax_delay`. The **last** one waits
  `relax_delay`, so the qubit re-thermalises before the next rep's prep.
- Readout window: identical block to [single_shot](single_shot.md#pulse-sequence).
- The reset block is the shared one from [active_reset](active_reset.md)
  (`ActiveResetMixin`, the exact code modified_ramsey runs): `cmp_offset =
  int(ro_norm) << 15`, `read` on the readout's tProc input channel, labels
  `RESET_DONE_<i>`.
- `reset_force_pi = True` skips the threshold decision and fires the corrective pi
  **unconditionally**. This measures the bare post-readout pi fidelity, decoupled
  from the threshold. It only removes the `condj`; the reset readout, `read` and
  offset are unchanged.

## How to run

Runs in **regime A**: the same config as [modified_ramsey](modified_ramsey.md), so the
verdict transfers 1:1 to the Ramsey.

```python
PLAN = [R.active_reset_verify(n_verify_reads=5, reps=2000,
                              reset_readout_relax_delay=5.0, relax_delay=3500)]
```

The run does the following:

1. Calls `calibrate_active_reset_readout`. This takes 2–3 SingleShot runs: it rotates
   `res_phase` so g/e separate along I, and sets the threshold and its sign (see
   [active_reset](active_reset.md#how-to-run)).
2. Measures six conditions:

| Label | prep | reset | force pi | Expected for a working QND reset |
|---|---|---|---|---|
| `prep\|g>_resetOFF` | g | off | – | Thermal baseline. |
| `prep\|e>_resetOFF` | e | off | – | Control: P(g) low (qubit stays excited, decays with T1 across reads). |
| `prep\|g>_resetON` | g | on | – | ≈ ground readout fidelity. |
| `prep\|e>_resetON` | e | on | – | **Key proof:** ≈ prep\|g>_resetON, ≫ prep\|e>_resetOFF, flat across reads. |
| `prep\|e>_forcePI` | e | on | yes | Read 0 ≈ prep\|g>_resetOFF if the pi is good. |
| `prep\|g>_forcePI` | g | on | yes | Read 0 ≈ prep\|e>_resetOFF. |

3. Plots an overlay of P(|g>) vs read index for all conditions, saves an npz, and
   prints a verdict.

**Verdict rule.** Let `pg_X` be the mean of P(g) over all verification reads. The
reset is called WORKING if both hold:

- `pg_e_on ≥ 0.9 · pg_g_on`
- recovery `pg_e_on − pg_e_off ≥ 0.3`

The force-pi diagnostics use read 0 only and are printed, not scored.

## Parameters

Legacy `ActiveResetVerify_params` keys. Defaults are the CSTQ03 runner values.

| Key | Default | Units | Meaning |
|---|---|---|---|
| `n_verify_reads` | 5 | count | Back-to-back readouts after the reset block. Code fallback 5; must be ≥ 1. |
| `verify_relax_delay` | 5.0 | µs | Wait between consecutive verification reads. |
| `reps` | 2000 | count | Shots per condition. |
| `reset_cycles` | 1 | count | Measure→feedback rounds when the reset is on. |
| `reset_readout_relax_delay` | 5.0 | µs | Wait after each reset readout. Keep equal to modified_ramsey's value (≥ ~6/κ). |
| `reset_read_latency_us` | 0.5 (code fallback) | µs | Stall before the reset `read`; floor 0.5, `reset_readout_relax_delay` must exceed it by ≥ 0.2. Forwarded only when set. See [active_reset](active_reset.md#read-latency). |
| `post_reset_wait` | 0.0 | µs | Settle time after the reset block. |
| `relax_delay` | 3500 | µs | Wait after the last verification read. ≥ 3·T1 (3–5·T1 convention, as for T1/T2E). |
| `plotDisp` | True | bool | Show the overlay (non-blocking). |

The run also writes `f_ge`, `pi_gain`, `sigma`, `flattop_length`, `rounds = 1`,
`readout_threshold`, `reset_ground_below_threshold`, `g_center`, `e_center`,
`prep_excited`, `use_active_reset` and `reset_force_pi` into each cfg.

## Outputs

- **Per condition**, path `ActiveResetVerify/`:
  - h5: `verify_i`, `verify_q` (shape `(n_verify_reads, reps)`, normalised units),
    `p_ground` (per read), `read_index`, `g_center`, `e_center`, `prep_excited`,
    `use_active_reset`, `reset_force_pi`, `reset_cycles`.
  - png: `<name>_Pg.png`.
  - json: the cfg.
- **Overlay**, in `<outer>/ActiveResetVerify/`:
  - `ActiveResetVerify_overlay_<ts>.png`.
  - `ActiveResetVerify_<ts>.npz`: `read_index`, `readout_threshold`, `res_phase`,
    `g_center`, `e_center`, `p_ground_<label>` per condition.
  - `ActiveResetVerify_<ts>_provenance.json` ([provenance](../architecture.md#provenance)).
- The verdict is **printed only**; it is not saved.
- The reset readouts themselves are not returned.

## Analysis

Each verification shot is classified against the perpendicular bisector of the
calibrated `g_center`/`e_center`: `score = (iq − midpoint)·(e − g)`, and it counts
as |g> if `score ≤ 0`. P(g) per read is the fraction of |g> shots. Because the read
index is resolved, you can tell:

- a reset that works but is not QND (P(g) drifts across reads), from
- a reset that fails (prep|e>+ON stays near prep|e>+OFF).

Diagnostic cross-check: the pi is **skipped** when `r_read <op> r_thresh`. Compare the
printed `g_I` and `e_I` from the calibration with the threshold. If the threshold is
not between them, the reset is miswired.

## Findings & notes

- TATQ01/BFE Q2, 2026-06-05/06: all 31 saved sweeps showed ground-state damage that
  tracked the below-zero fraction of the g blob. A g_I ≈ 0 sweep lost exactly half
  its ground shots. Conclusion: the tProc compares unsigned (see
  [active_reset](active_reset.md#why-cmp_offset--intro_norm--15)). This program
  used a fixed offset of 2^24 on the claim "2^24 ≫ any |raw I| (~1e4–1e5)", which is
  **superseded**: |raw I| can reach `ro_norm·2^15`, and 2^24 is about 9x too small for
  a 15 µs window (2026-07-28). Since 2026-10-13 it runs the shared reset block with
  `int(ro_norm) << 15`, so ARV data taken before then with negative-I shots below
  −2^24 does not test the reset modified_ramsey runs.
- TATQ01-SiO2 Q3 (lab record, 2000 reps/condition): reset ON gave P(g) = 0.539
  (prep g) / 0.497 (prep e), against force-pi 0.847. Pi and readout were fine; the
  reset `read` was sampling the previous rep's readout (see
  [active_reset known issues](active_reset.md#known-issues)).
- Expected ceiling for a correct reset at `reset_cycles = 1`: prep|e>+ON ≈ 0.74,
  prep|g>+ON ≈ 0.78, the two within ~0.06, flat vs read index. These are below the
  thermal baseline and below force-pi, because the readout error is paid twice.
  A deliberate g_I ≈ 0 condition is the sharpest regression test of the sign fix.

## Known issues

- Fixed 2026-10-13: until then this step kept its own copy of the reset, with a fixed
  `cmp_offset = 2^24` (no `< 2^30` guard) and the readout index passed to `read`
  instead of `readouts[ro_ch]["tproc_ch"]`. With a 15 µs window, shots with raw
  I < −2^24 wrapped and the pi fired on the wrong branch; on a board whose readout is
  not wired to the same-numbered tProc input it read the wrong input. It now uses the
  shared `ActiveResetMixin`, so it tests exactly what modified_ramsey runs.
- No `flattop_length` guard. The run passes the device `flattop_length`, but the
  program plays a 4σ gaussian with that gain, which mis-rotates a flat-top-calibrated
  pi.
- No `rounds != 1` guard. Only the last round would be kept.
- Prep and corrective pi play at `f_ge`. Modified Ramsey plays them at the drive
  frequency, which differs in the symmetric scheme.
- The read-latency fix of 2026-10-13 ([active_reset](active_reset.md#read-latency)) is
  in the shared block, so it applies here too; ARV data with the reset on from before
  then sampled the previous rep's readout. Pending hardware validation (this step's
  rep-to-rep correlation check, see [active_reset](active_reset.md#known-issues)).
- The calibration rotates `res_phase` in the session config; later regime-A steps
  inherit it.
- Calling `save_data()` without an argument raises.
