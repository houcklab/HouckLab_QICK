# Ramsey/Cryoscope neutral predistortion: operating guide

Companion to `controller_neutral_predistortion_schema.md`. This is the runbook.

## Status

Software validation: complete. 303 tests pass in `HouckLab_QICK`, 367 in
`Houck-Lab-Qua`, including the pre-existing five-point protocol and predistortion
production suites, which are unchanged.

Scientific validation: **not started** — no Ramsey measurement has been taken yet.

Hardware validation: **not started**.

Production predistortion is therefore **off**. `Q3_FLUXPRED_MODE` and
`Q5_FLUXPRED_MODE` default to `off`, and the production runners refuse `neutral`
until the center acceptance run has passed. The long scan is safe to launch as is.

## The measurement

For a desired flux command `r(t)` the qubit is prepared at park, the flux command is
played, and a short Ramsey (X90 — free precession window `w` — X90 or Y90) is
inserted at a variable delay `t`. The accumulated phase is

```
phi(t) = 2π w Δf(t)
```

so `Δf(t) = phi(t) / (2π w)` with no differentiation of noisy phase. The nominal
phase under the intended ideal command is computed from the static P4 flux model and
subtracted, leaving the residual detuning. The residual is converted back to a flux
coordinate on the local monotonic branch and normalized to `(target − park)`.

X and Y are measured as separate arms, with `g` and `e` as the assignment reference,
and the arm visit order is permuted per delay so drift cannot masquerade as
structure.

### Readout happens immediately after the probe

Reading out only after the whole 800 µs flux timeline would let T1 destroy the
reference contrast — `p_e` would decay to `p_g` and the Bloch inversion would fail.
The readout is therefore issued as soon as the second π/2 pulse ends.

q3 plays the flux prefix up to the probe and stops; `stdysel="last"` holds that
level through the readout, then an explicit park segment restores the line. q5 plays
only the emission segments before the probe's segment, sets that segment's voltage,
and reads out on the resonator while the level is held, then restores park. In both
cases the readout happens at a known, constant flux level.

Because the measured phase depends only on the flux history *before* the probe,
truncating after the probe is exactly equivalent for identification, and the
analysis uses the full command. This also cuts the per-shot sequence time from the
full 800 µs timeline to roughly the delay itself.

The readout resonator is pulled by the held flux level, but `g` and `e` are measured
at the same delay under the same flux, so the contrast normalization absorbs it.
That is why the reference arms are re-measured at every delay rather than once.

### The drive frequency follows the nominal level

A single fixed drive frequency would be roughly 100 MHz off resonance during the
recovery, so every post-return delay would have zero contrast — losing exactly the
data that makes the fit identifiable. The probe frequency is therefore computed per
delay from the static model at that delay's *nominal* commanded level: the
identification target during the hold, park after the return.

The measured phase is then the residual relative to the local nominal, which is what
`nominal_detuning_mhz` subtracts. The per-delay probe frequency is written as a
`probe_freq_ghz` column in the raw CSV, so the conversion is auditable and the fitter
never has to guess it. q5 retunes with `update_frequency` from a QUA array and
refuses a probe needing more than ±400 MHz of intermediate frequency; q3 sets the
frequency per program.

The π/2 gain is calibrated at park and is not re-tuned per flux point. A wrong
rotation angle shortens the Bloch vector but does not bias its phase, and the
contrast mask drops points where it degrades too far.

### Probe span and the emission grid

Each probe needs `inset + 2 × π/2 pulse + window + readout` of *constant* commanded
flux. The runners compute that span, print it, and abort if it does not fit the first
emission segment rather than silently dropping the early delays that carry the fast
pole. Defaults: first segment 4 µs, growth 1.2, cap 100 µs, inset 16 ns (four OPX
clocks, so every delay is a playable wait).

That grid gives about 33 delays for a 200 µs hold and 600 µs recovery, with roughly
seven points below 40 µs on each side of the return edge.

### The measurement must include the return

This is not optional. With a hold-only trace, contiguous-time-block cross-validation
cannot tell pole banks apart — on synthetic data a deliberately wrong slow-pair bank
scored within a factor of two of the true bank. With the return transient included,
the correct bank scores at the noise floor (9.8e-5) while wrong banks score
1.9e-3–4.7e-3, a 19–48× separation. The delay grid therefore spans hold **and**
recovery, and is dense on both sides of the return edge.

### Phase wrapping sets the identification amplitude

A fixed window `w` is unambiguous only over `±500/w` MHz. The q5 flux line runs about
3151 MHz per unit normalized amplitude near the full target; a 15–20% overshoot on a
full-amplitude uncorrected step is a ~470 MHz transient. Resolving that would need a
0.8 ns rung, which does not exist.

So identification runs at a reduced amplitude. `cryoscope.plan_window_ladder` builds
a geometric ladder (default 20 → 100 → 500 ns, ratio 5) and
`cryoscope.max_identification_amplitude` sizes the amplitude the coarsest rung can
unwrap. For q5 with a 20 ns coarsest rung and an assumed 20% overshoot that is about
5% of full amplitude. Both runners compute this, print it, and refuse a larger
`*_CRYO_AMPLITUDE` with an actionable message.

The alternative, if a larger amplitude is wanted: pass an existing correction as
`*_CRYO_BASE_MODEL_JSON` and identify the *residual* on top of it, which is much
smaller and fits the ladder at full amplitude.

The fit normalizes the trace and command to unit amplitude before regularizing,
because the ridge penalty is not scale-invariant; without that a reduced-amplitude
identification is silently over-regularized and returns a wrong plant that still
fits the data.

## Step 1 — center identification (run both, they are independent)

q3 / QICK, on `escher@escher-pc`:

```bash
cd ~/Documents/GitHub/HouckLab_QICK && git pull --ff-only origin tls-spectroscopy && git rev-parse --short HEAD && Q3_CODE_COMMIT=$(git rev-parse --short HEAD) c:/Users/escher/Documents/GitHub/HouckLab_QICK/.venv/Scripts/python.exe -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.FluxRamseyCryoscope
```

q5 / QUA, on `PRINCETON+ece-houck-j409@ELE-V-57HF5G4`:

```bash
cd ~/Documents/GitHub/Houck-Lab-Qua && git pull --ff-only origin marty-branch && git rev-parse --short HEAD && Q5_CODE_COMMIT=$(git rev-parse --short HEAD) c:/Users/ece-houck-j409/Documents/GitHub/Houck-Lab-Qua/qua-env/Scripts/python.exe -m LabCode.Control.Flux_Tunable.FluxRamseyCryoscope
```

Both print the plan before acquiring: park/target, amplitude and its ceiling, the
window ladder, the delay count, the probe frequency, the flux timeline length and
emission count, and an estimated sequence time. The QUA runner also prints an
explicit OPX output-filter check on the addressed analog port and aborts if any tap
is populated. QICK prints the fabric clock it read from `soccfg`; it is never hard
coded. Progress is a heartbeat with stage, completed/total, elapsed and ETA.

Outputs, in the standard date folder, ending with:

```
RAW_CSV=...
COMMAND_JSON=...
SUMMARY_JSON=...
```

Both restore the flux line to park, QUA in a `finally` block.

### Useful knobs

`Q3_`/`Q5_` prefixed: `CRYO_AMPLITUDE`, `CRYO_HOLD_US` (200), `CRYO_RECOVERY_US`
(600), `CRYO_SHOTS` (300), `CRYO_WINDOWS_NS` (explicit ladder, comma separated),
`CRYO_COARSEST_WINDOW_NS` (20), `CRYO_FINEST_WINDOW_NS` (500), `CRYO_LADDER_RATIO`
(5), `CRYO_MAX_DELAYS` (40), `CRYO_ASSUMED_OVERSHOOT` (0.20),
`CRYO_SCHEDULE_FIRST_US` (4), `CRYO_SCHEDULE_GROWTH` (1.2), `CRYO_SCHEDULE_MAX_US`
(100), `CRYO_PROBE_INSET_NS` (16), `CRYO_BASE_MODEL_JSON`, `CRYO_NOTE`.

Expected duration: roughly 33 delays × 6 arm/window conditions × 300 shots, with a
mean sequence length near the mean delay (~220 µs) plus reset. On q5 that is a few
minutes of sequence time plus compilation; q3 adds per-program overhead because each
arm is a separate `AveragerProgram`. Both print an estimate before acquiring.

## Step 2 — fit a candidate (on the Mac, off the NAS)

```bash
python3 tools/fit_ramsey_flux_response.py --summary <SUMMARY_JSON> --device q5 --park 0.156232010522 --scale 0.231509604478 --out q5_center_candidate.json
```

Pass several `--summary` files to fit repeats jointly; per-trace offsets are fitted
separately so drift shows up as differing offsets instead of being averaged away.

The fitter verifies every source hash, compares the prespecified pole banks
(`8,24,64,192` and `12,40,120,360` µs) and a regularization grid by contiguous-time-
block cross-validation, prefers the simplest adequate bank, solves a bounded stable
inverse against the emitted interval-mean waveform, and writes a candidate with
`acceptance.scientific = false`. It also writes a six-panel audit PNG: per-rung X/Y
contrast, unwrapped phase with masked points marked, residual detuning, measured
normalized amplitude against the plant fit, inverse cancellation forecast, and the
return-to-park forecast.

Reject the trace and re-measure rather than fitting if the contrast collapses, the
supported fraction is low, or the ambiguous branch count is non-zero.

## Step 3 — acceptance, before anything is enabled

A candidate is not production-ready because it compiles or makes one step plot
flatter. It must pass the exact repeated T1 lifecycle: reach the target during the
T1 interval, return to the calibrated park/readout condition before the measurement
is interpreted, not read out during a large correction tail, and not drift shot to
shot. Targets: held-target residual RMS < 0.5 MHz, early-to-late target error
< 1.0 MHz, park/readout residual < 0.5 MHz, with 0.25/0.5 MHz as the preferred
targets. `validation.acceptance` reports both tiers and will not let the preferred
tier be claimed when measurement uncertainty is larger.

Only then set `acceptance.scientific = true` and enable the mode. Until then the
production runners refuse `neutral` with a message naming the missing step.

## Stop rule

One candidate plus at most one residual update. If that does not pass, set
production predistortion off, run the long scan, and keep the artifacts.
