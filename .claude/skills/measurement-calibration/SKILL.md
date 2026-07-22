---
name: measurement-calibration
description: Use BEFORE running any qubit measurement/experiment on the QICK calibration GUI. Encodes the general→specific calibration order, the recalibrate-what-the-experiment-changes rule, the pair→ramp→swap-dynamics convention, and time-respecting (fast vs careful) parameter ranges. Consult for HOW MUCH to measure and WHICH knobs to touch — not for the action-key list (that comes from the live system prompt).
---

# Measurement Calibration

A workflow for getting qubits into a trustworthy state before a real measurement, and
for choosing measurement/calibration parameters that respect the scientist's time. This
generalizes beyond any one experiment: **calibrate generally first, then calibrate the
specific thing the experiment changes or needs.**

## Source of truth: keys vs. values

Two different sources, do not confuse them:

- **WHICH parameters exist (keys)** come from your live system prompt: each Auto-Calib
  stage lists its settable `param_form` keys, and each whole-tab calibration lists its
  `AGENT_PARAMS`. Read those for the exact key names — they change when the GUI changes.
- **WHAT VALUES to use, and WHICH knobs are worth touching**, come from *this* skill.

So: keys from the system prompt, values + decision logic from here. Never re-derive the
key list from this file (it will drift); never invent a sane value when this file gives one.

## Action protocol (reminder)

The GUI auto-runs (no approval) any fenced `action` block you emit. Two forms:

````
```action
{"stage": "QubitSpec", "qubits": [6], "params": {"reps": 200}, "summary": "one line"}
```
````
````
```action
{"calibration": "pi2_phase", "params": {"variant": "...", ...}, "summary": "one line"}
```
````

`params` is optional; omitted keys keep the GUI's current value; unknown keys are dropped.
Emit one action only for a real run, and never claim a result before the GUI reports it.

## Order of operations

Follow the project calibration hierarchy (see `CLAUDE.md`). The 8 Auto-Calib stages map
onto it as:

| Hierarchy layer | Auto-Calib stages | Tab calibration |
|---|---|---|
| Readout calibration | `Transmission`, `ReadoutOpt`, `SingleShot` | — |
| Single-qubit calibration | `QubitSpec`, `AmplitudeRabi`, `PulseOpt`, `T1`, `T2R` | — |
| Multi-qubit / coupler | — | `two_qubit_chevron` |
| Simulation-specific | — | `pi2_phase` (measurement-π/2 gain/freq/phase) |

**Step 1 — General single-qubit calibration, every qubit involved.** Bring each qubit up
in this order so each stage depends only on already-calibrated quantities:
`Transmission → QubitSpec → AmplitudeRabi → (ReadoutOpt → SingleShot) → (PulseOpt) → T2R → (T1)`.

- **Minimal fast path** (just trying things, want a result quickly):
  `QubitSpec → AmplitudeRabi → T2R`. This gives qubit frequency, π-pulse gain, and a
  Ramsey detuning to refine the frequency — enough to drive and read out. Add
  `Transmission` first only if the resonator may have drifted.
- **Full careful path** (publication / discrimination matters): add `ReadoutOpt` +
  `SingleShot` (readout fidelity / threshold), `PulseOpt` (refine π gain & freq together),
  and `T1` (slow — long relax delay; run only when you need the number).

**Step 2 — Specific calibration for what THIS experiment changes or needs.** Decide from
the experiment, not by rote:

- **Qubit frequency or gain moves** (e.g. a flux/FF ramp parks a qubit at a new operating
  point): recalibrate *that qubit at the new point* — its drive frequency and π/π-2 gain
  are no longer the on-resonance values. The measurement pulses live at the moved
  frequency, not the bare qubit frequency.
- **The experiment needs pulses beyond the π pulse** (π/2, a measurement-π/2, a basis
  rotation): calibrate them explicitly — gain, frequency, and phase as the protocol
  requires. Do not assume the π-pulse calibration transfers.
- **If you are unsure what the experiment needs** — which pulses, which operating point,
  what observable, what counts as "calibrated enough" — **ask the scientist** before
  running. Do not guess a protocol or invent device parameters.

## Two-qubit convention: pair → ramp → swap dynamics

When a two-qubit operation between chip qubits `i` and `j` is involved, three things are
chosen together and must be consistent:

1. **Ramp state** keyed `"<i><j>"` — e.g. the 6–8 pair uses ramp state `"68"`.
2. **Dynamics point** keyed `swap_<i>_<j>` — e.g. `swap_6_8`.
3. The swap dynamics entry **stores that pair's measurement-π/2 calibration**
   (`meas_pi2_freq_abs`, `meas_pi2_gain_abs`). pi2-phase reads/writes these. So
   recalibrating the measurement π/2 for a pair = updating its swap dynamics entry.

Rule that generalizes: **whenever you pick a qubit pair for two-qubit / pi2 calibration,
use that pair's ramp state and its matching `swap_i_j` dynamics point.** Verify both keys
exist in `qubit_parameters.json` (`ramp_groups`, `dynamics_groups`) before using them; if
a pair's ramp or swap point is missing, stop and ask — do not fabricate one.

## Parameter discipline (respect time)

Be deliberate. Wall-clock ≈ `reps × (sum of all sweep points) × (relax_delay + sequence)`.
Sweep points and `relax_delay` dominate. Coarse-and-fast first; tighten only when the
result demands it. You rarely need full precision just to *see* whether something works.

**Fast vs careful, grounded in the GUI defaults:**

| Calibration | Knob | Fast (exploring) | Careful (default) |
|---|---|---|---|
| QubitSpec | `reps` / `SpecNumPoints` | 200 / 51 | 200 / 71 |
| AmplitudeRabi | `reps` / `expts` | 200 / 31 | 200 / 31 |
| T2R | `reps` / `expts` | 200 / 51 | 200 / 81 |
| T1 (slow) | `expts` / `reps` | run only if needed | 51 / 200 |
| SingleShot | `Shots` | 1000 | 3000 |
| two_qubit_chevron | `gainNumPoints` / `expts` | 7 / 41 | 11 / 71 |
| pi2_phase (1D/2D) | `phase_num_points` | **21** | 41 |
| pi2_phase 2D | `samples_start..end` / `samples_num_points` | **0–300 / 21** | (default ships 0–8000 / 81) |
| pi2_phase | `reps` | 200–300 | 500 |

**Avoid these shipped defaults — they are the slow trap the scientist flagged:** the
pi2-phase **2D** form defaults to `samples_end = 8000` with `samples_num_points = 81` and
`phase_num_points = 41`. That is far longer than any normal run (~8000 samples ≈ tens of µs
of evolution, sampled 81×41 ≈ 3300 points). For fast iteration use **`samples 0–300`,
`samples_num_points 21`, `phase_num_points 21`**.

**General principle for the sample/time axis:** span it to ≈ one relevant dynamics
timescale (e.g. roughly one swap period for a swap experiment), with just enough points
(~20) to resolve the fringe — not the full 8000-sample default. The `0–300 / 21` figure is
the right setting *for the 6–8 swap*; rescale the span to the pair's actual swap period for
other pairs, keep the point count modest.

**Red flags (stop and reconsider):** `samples_num_points` or any sweep > ~100 points;
`samples_end` near 8000 for a quick look; `reps` > ~2000; `Shots` > ~10000; `relax_delay`
> ~1000 µs. None of these are wrong in principle, but they cost a lot of wall-clock — only
use them when the measurement genuinely needs that precision.

## Worked example (the 6 & 8 swap workflow)

Goal: calibrate Q3–8, then characterize the 6–8 swap and its measurement-π/2 for a
pi2-phase fringe. Pair (6,8) ⇒ ramp `"68"`, dynamics `swap_6_8`. Finish Q6 & Q8 first.

1. **General single-qubit** for Q6 and Q8 (then 3,4,5,7): `QubitSpec → AmplitudeRabi → T2R`
   (fast path), via `stage` actions, one qubit at a time. Add readout stages if
   discrimination quality matters.
2. **Chevron** on the pair to find the coupling/swap timing:
   `{"calibration": "two_qubit_chevron", "params": {"q_i": 6, "q_j": 8, "ramp_state": "68"}}`.
3. **Measurement-π/2 recalibration on 6 and 8** — the flux ramp moved their frequency, so
   the π/2 lives at the parked frequency. Use the pi2-phase tab's gain/freq calibration
   variant (`MottQuenchPi2GainFreqCal`) at ramp `"68"` / dynamics `swap_6_8`; in its default
   mode it calibrates the **measurement** π/2 and writes `meas_pi2_freq`/`meas_pi2_gain` back
   onto `swap_6_8`. There are *two* π/2 pulses in the common-frequency scheme: the **init**
   π/2 (first pulse, gain = `pi2_init_gain`/`init_pi2_gain`, calibrated by GFCAL's init mode)
   and the **measurement** π/2 (second pulse, `meas_pi2_*`). If unsure which one a run is
   calibrating, check whether GFCAL's init mode is enabled before trusting the write-back.
4. **pi2-phase 1D and 2D** on 6 and 8 at ramp `"68"` / dynamics `swap_6_8`:
   `phase 0–360 / 21 pts`, 2D `samples 0–300 / 21 pts`, `reps` 200–300. Confirm the
   low→high population fringe.

## Safety gates (never auto-run these)

These require explicit human action even when running is otherwise unattended:

- Coupler / qubit **bias ramps** to new operating regions, RFSoC **connect / clock /
  firmware reconfig**, board reset.
- **Overwriting `qubit_parameters.json`** as a bulk action (single calibration write-backs
  by a tab are fine; wholesale edits are not).
- Frequency sweeps that could cross a protected band, pump line, or known collision region
  without approval; flux/bias outside the latest calibrated safe range.

When the next safe step needs code changes (new/modified experiment code, or creating
files), say what you'd change and ask the scientist to enable edits — do not attempt it
read-only.
