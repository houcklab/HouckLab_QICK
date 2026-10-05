# q3 feedback afterglow pilot

The independent broad repeat did not confirm afterglow. Before spending
another hour on a spectrum, this finite pilot tests whether actual feedback
removes the hot–cold qubit carryover and whether additional excitation appears
during a subsequent visit. It is a preparation and return check at three fixed
sites, not a TLS discovery scan or a lifetime measurement.

## Sequence and workload

At each of **3.984, 3.862 and 4.046 GHz**, one logical hardware shot interleaves
all eight combinations of nominal hot/cold loading, feedback/sham, and
0.1/40 µs probing. Block two reverses frequency and condition order. There are
600 logical shots per site per block, two blocks, **28,800 science trials**,
2,400 final-reference trials and 8,000 fresh reset-calibration trials.

Each trial performs:

1. Wait 5 ms at q3 park. Prepare with the calibrated park π pulse for hot
   loading, or an identical-duration zero-gain pulse for cold loading. Cold is
   a nominal preparation following passive recovery, not a perfect ground state.
2. Visit the same loading/probing frequency for 10 µs, then complete the
   established distortion-corrected 40 µs return to park.
3. Use the previously validated gain-1200 reset readout. Four fixed feedback
   opportunities save raw IQ and apply either π or zero gain according to the
   fresh conservative classifier. Sham uses the same decisions, reads and
   waveform durations, but every correction has zero gain. A fifth weak
   readout independently verifies ground confidence.
4. Play a matched zero-gain preparation slot, visit the same frequency for
   0.1 or 40 µs, then complete the corrected return. Read at park with gain
   1880. Keep all six IQ pairs, including shots that fail ground verification.

The board compilation gives **169.250 µs from the end of loading to the start
of the probe excursion**, with an additional scheduled 0.5 µs arrival.
Feedback may perturb or erase the loaded environment. Consequently a null
only constrains return that survives this sequence; it cannot exclude faster
memory or establish that no TLS was loaded. The pilot is faster in wall-clock
runtime than the broad maps, not faster in its load–probe gap.

Expected total runtime is **4–8 minutes**, depending on calibration and
transport. Calibration gets one attempt; there is no automatic retry train,
peak-selection gate, extended run or two-frequency scan. The progress bar
includes ETA. Standard calibration/setup messages and the final path are the
only other output; compile details go to the session's `compile.log`.

## Analysis and decisions

The pre-run final-reference axis is fit on alternating ground-conditioned
reference shots and checked on the held-out half. Post-run references check
that frozen axis, and an independent post-axis refit is saved as a sensitivity
analysis. Classification fractions and reference-normalized IQ are measured
quantities; neither is an absolute population or a TLS temperature.

For each arm, save the ground-verification fraction, accepted count, inferred
correction count, conditional final excitation/IQ and all-shot final
excitation/IQ. Paired influence covariance retains correlations between the
eight conditions in each logical shot. Two-block uncertainties include an
order-disagreement floor.

First check short-probe equivalence: the hot-minus-cold normalized IQ interval
(estimate ± 1.96 SE) must lie within ±0.05 reference separation, in both
conditional and all-shot data. Failing this is *unmatched or unresolved
preparation*, not a negative TLS result. Arm quality also requires at least
80 accepted shots, at least 20% ground verification and no feedback-IQ
multiplier-range overflow. Both blocks and pre/post references must pass.

Then compute:

`growth = (hot − cold at 40 µs) − (hot − cold at 0.1 µs)`.

Report feedback and sham separately, including all-shot growth and IQ growth.
A positive long-probe offset without positive growth does not qualify.
Exploratory follow-up flags require short-probe equivalence, positive
conditional growth > max(0.03, 3.35 SE), positive long excess > 3.35 SE,
growth > 0.02 in each block, and positive conditional and all-shot IQ growth
in each block. These are conservative triage rules, not calibrated discovery
significance. A flag warrants an independent test with detuned loading and
carryover controls, not an automatic long map. A null at three fixed sites
does not exclude other frequencies or a smaller effect.

## Validation before release

- New regression tests cover matched/reversed controls, paired covariance,
  carryover, insufficient reset verification, missing blocks, IQ overflow,
  a selection-only apparent return, timing bookkeeping and bank preservation.
- The maintained repository suite passes: **1,402 tests**, including seven
  new pilot tests. Independent code review found no remaining major issue.
- All ten science/reference programs compile against QICK **0.2.133** and the
  saved Oct 4 board configuration. Maximum instruction usage is
  **6,715 / 8,192**; waveform and resident-stream storage checks pass.
- A conservative tProc instruction emulator checks both classifier
  orientations and both correction outcomes, exact 12-word records, matched
  pulse timelines and absence of late pulses in the modeled instruction paths.
- Offline acquisition-boundary simulations exercise completion, interrupted
  transferred-bank recovery, invalid initial/post references and failed reset
  calibration, while using the real program compilation and analysis.
  Original q3 configuration context is restored in every case.
- No measurement was performed locally. Analog pulse delivery and current
  preparation quality remain hardware questions for this pilot.

Reproducible local audit artifacts are in
`/Users/rummanrahman/.codex/visualizations/2026/10/04/q3_afterglow_feedback_pilot_validation/`.

## Measurement PC command

```bash
git -c gc.auto=0 pull --ff-only origin tls-spectroscopy
python -u -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSAfterglowFeedbackPilot --run
```

Session prefix: `q3_afterglow_feedback_pilot_` under the existing q3 data root.
The runner uses temporary explicit q3 settings; production reset defaults,
TLS spectroscopy and `initialize.py` are unchanged.
