# charge_dispersion: quasi-CW telegraph and fixed-wait Ramsey (ChargeDispersion, ChargeDispersionQuasiCW)

This page covers three steps that probe charge dispersion directly. For the main
parity-rate measurement use [modified_ramsey](modified_ramsey.md), and for the CW
two-tone version use [zero_span_parity](zero_span_parity.md).

| Step | Class | Idea |
|---|---|---|
| `charge_dispersion_quasicw` | `ChargeDispersionQuasiCW` | Park the qubit drive on one parity branch and record shot-resolved readout IQ. Parity flips move the qubit on and off resonance, and the readout telegraphs. |
| `two_tone_charge_dispersion_quasicw` | `QubitSpecSliceFF` + `ChargeDispersionQuasiCW` | Walk the yoko until two-tone spectroscopy shows a resolved doublet, then run the quasi-CW record on one branch. Repeats per cycle. |
| `charge_dispersion_ramsey` | `ChargeDispersion` | One fixed-wait Ramsey point (pi/2 – wait – pi/2), repeated. |

Code: see `qicklab.experiments.charge_dispersion` and `qicklab.runs.charge_dispersion`.

## What it measures

- **Quasi-CW.** A pulse-then-measure loop runs in hardware (`reps` iterations in one
  acquire) at a single qubit frequency. The program returns the rep-resolved raw IQ,
  `(reps, expts)`. Each shot is a g/e readout whose P(e) depends on the parity (the
  drive is resonant with one branch), so the record is a parity-modulated g/e sequence,
  not a parity trace. The parity rate comes from the same HMM analysis as
  [modified_ramsey](modified_ramsey.md#analysis), with the readout self-calibrated from the
  record and the mapping P(e | parity) fitted. A gated KMeans split into two blobs gives the
  per-shot g/e assignment vs time, as a diagnostic.
- **Ramsey.** A single-point Ramsey whose wait is set from `df`, the splitting of the
  two parity branches. It reports the averaged I/Q/amplitude of that one point. The
  aim is a charge-parity-sensitive readout, but see the 1/df caveat below.

## Pulse sequence

Quasi-CW (the body is identical to `QubitSpecSliceFF`, at one frequency):

```
qubit_ch  ── 1 µs ─[ qubit pulse @ probe_freq ]─ 0.5 µs ─┐   (Gauss: gaussian σ, gain; else const qubit_length)
res_ch                                                    [ readout tone ]── 10 µs ── relax_delay ──▶ next rep
ADC (ro 0,1)                                                [ window ]
```

- Channels: `qubit_ch`, `res_ch`. Readouts 0 and 1 are hard-coded. No trigger pin.
- `start = probe_freq`, `step = 0`, `expts = 1`, `reps = repetitions`, `rounds = 1`.

Fixed-wait Ramsey:

```
qubit_ch  ─[pi/2, φ=0]── wait = us2cycles(1/df) (edge-to-edge) ──[pi/2, φ=0]─ 0.05 µs ─┐
res_ch                                                                                    [ readout ]── relax_delay
```

- Both pulses are `pi2_gain` 4σ gaussians at `f_ge`, phase 0.
- No trigger, no winding correction. `flattop_length` is ignored.
- `reps = 1`, `rounds = 1`: one shot per program build.

## How to run

All three run in **regime A**.

```python
PLAN = [R.charge_dispersion_quasicw(probe_freq=2306.567327, repetitions=500,
                                    relax_delay=2000)]
PLAN = [R.two_tone_charge_dispersion_quasicw(df=0.5, voltage_min=0.0,
                                             voltage_max=0.010)]
PLAN = [R.charge_dispersion_ramsey(df=..., repetitions=...)]   # see Known issues
```

`two_tone_charge_dispersion_quasicw` runs this loop for each of `num_cycles` cycles:

1. Two-tone spectroscopy with `QubitSpecSliceFF` over ±`SpecSpan` around the qubit
   centre. The response is projected onto the signal-bearing IQ axis.
2. Choose the peaks: Lorentzian centres if available, otherwise a peak finder with
   `min_sep_MHz` ([two_tone_spec](two_tone_spec.md#analysis) step 4). A second peak whose
   height is below 5 x the per-point noise (`MIN_PARTNER_SNR`, not configurable in this
   step) is dropped as noise: one peak, separation `None`. The `TwoTone_*` amplitude
   PNG title then shows `sep=None` and `_summary.txt` one `peak_freqs` entry and
   `peak_sep: None`; the dashed markers are the raw bin peaks and still show both.
3. Decide:
   - If the **strongest** peak is within `center_peak_tol_mhz` of the qubit centre,
     accept it as the probe (any separation, including 0). With no second line (one
     peak, or the partner dropped as noise in step 2) the separation is saved as 0.0
     in the quasi-CW record (`peak_sep`) and the cycle summary.
   - Else, if the separation ≥ `df`, take the upper peak (`use_upper_peak`) or the
     lower one as the probe.
   - Otherwise step the yoko by `dV`, bouncing between `voltage_min` (clamped to
     ≥ 0) and `voltage_max`, and stop when the step stalls or after
     `max_voltage_tries`.
4. If a probe was found, run the quasi-CW record (`qcw_repetitions`,
   `qcw_relax_delay`) at it, split the shots with the gated KMeans and run the parity
   analysis (see Analysis).

The voltage and search direction carry over to the next cycle.

## Parameters

`ChargeDispersion_params` (CSTQ03 runner values):

| Key | Default | Units | Meaning |
|---|---|---|---|
| `probe_freq` | 2306.567327 | MHz | Qubit frequency for quasi-CW (one parity branch). |
| `relax_delay` | 2000 | µs | Relax after each readout (quasi-CW and Ramsey). |
| `repetitions` | 500 | count | Quasi-CW hardware reps. |
| `df` | — (missing) | MHz | Ramsey: branch splitting, sets wait = 1/df. Absent in the runner dict. |
| `upper_freq` / `lower_freq` | 2306.567327 / 2306.032673 | MHz | Documentation only; read nowhere. |
| `expected_parity_dwell_ms` | 2.5 (absent: default) | ms | Expected parity dwell of the quasi-CW parity analysis (HMM rate seed, lag window, feasibility warning). |

Quasi-CW drive, from the session spec group (`Spec_relevant_params`):

- `Gauss` False (then `qubit_length` and `qubit_gain` from the config: spec length
  50 µs, gain 1000);
- `sigma` 2 µs and `gain` 800 DAC are used only when `Gauss` is True.

`TwoToneChargeDispersion_params`:

| Key | Default | Units | Meaning |
|---|---|---|---|
| `df` | 0.5 | MHz | Required peak separation to accept a voltage. |
| `dV` | 0.0005 | V | Yoko step. |
| `voltage_min` / `voltage_max` | 0.000 / 0.010 | V | Search bounds (min clamped to ≥ 0). |
| `max_voltage_tries` | 1000 | count | Steps per cycle. |
| `num_cycles` | 1000 | count | Search → quasi-CW cycles. |
| `use_upper_peak` | True | bool | Probe the higher-frequency peak. |
| `center_peak_tol_mhz` | 0.05 | MHz | Accept the strongest peak if this close to the qubit centre. |
| `SpecSpan` / `SpecNumPoints` | 1.0 / 101 | MHz / count | Search spectroscopy (± span). |
| `reps` / `rounds` / `relax_delay` | 10 / 10 / 850 | count / count / µs | Search spectroscopy averaging. |
| `Gauss` / `sigma` / `gain` / `qubit_length` | True / 2 / 500 / 2 | – / µs / DAC / µs | Search drive. |
| `qcw_repetitions` | 1000 | count | Quasi-CW reps once a doublet is found. |
| `qcw_relax_delay` | 850 | µs | Quasi-CW relax. |
| `expected_parity_dwell_ms` | 2.5 (absent: default) | ms | As in `ChargeDispersion_params`, for the quasi-CW record of this step. |

The charge_dispersion_ramsey loop count is the coherence group's `repetitions` (1000
in the CSTQ03 runner), not a key of its own.

## Outputs

- **charge_dispersion_quasicw:**
  - In `<outer>/ChargeDispersion/ChargeDispersionQuasiCW_<ts>`:
    `_iq_blobs_labeled.png`, `_separator_score_hist.png`, `_binary.png`,
    `.npz` (`elapsed_s`, `raw_i`, `raw_q`, `amps` = |I+iQ|², `scores`,
    `binary_amps`, `centers`, `midpoint`, `normal`, `x_pts`, `config`, `rep_period_us`,
    `blob_snr`, `parity_analysis`), `_config.json`, and `_provenance.json`
    ([provenance](../architecture.md#provenance), with the program hash).
  - When the parity analysis runs: `<name>_parity_analysis.json`,
    `<name>_parity_analysis.h5` (written only if h5py is importable) and the
    `_calibration`, `_projected_trace`, `_hmm`, `_acf_psd`, `_rate_vs_bin`, `_dwells` PNGs
    of analyze_modified_ramsey_record (prefix `<name>_parity`).
  - **No raw-data h5** is written. The experiment's `save_data` is not called; the raw
    data lives only in the npz. The only h5 is the parity-analysis sidecar above.
  - The first plot (IQ + separator) is shown but never saved.
- **two_tone_charge_dispersion_quasicw:**
  - Every spectroscopy attempt is saved by `QubitSpecSliceFF` (path
    `TwoToneChargeDispersion`), with a two-tone plot and `<base>_summary.txt`.
  - Per successful cycle: `Cycle_<nnn>_QuasiCW_<ts>` with `_iq_separator.png`,
    `_iq_labeled.png`, `_amplitude_vs_time.png`, `_binary.png`, `.npz` (also
    `rep_period_us`, `blob_snr`, `parity_analysis`), `_config.json`, `_provenance.json`, and the
    `_parity_*` analysis files as above.
  - One `CycleSummary_<ts>.json` per run.
  - No raw-data h5 for the quasi-CW record; the only h5 is the
    `<name>_parity_analysis.h5` sidecar.
- **charge_dispersion_ramsey:** per repetition, a `ChargeDispersion/` h5 (`avgi`,
  `avgq`, `amp`), `<name>_ChargeDispersion.png` and json.

## Analysis

- **Quasi-CW raw buffer.** For qick 0.2.334 the `acc_buf` loop dims are `[expts,
  reps]` (expts outer), so `reshape(expts, reps).T` gives the correct `(reps, expts)`
  ordering. The averaged return value is incidental; `di_buf`/`dq_buf` carry one entry
  per hardware shot.
- `raw_i`/`raw_q` are **raw accumulator sums**: not divided by the window length, no
  offset removal. They are not in the normalised units of single_shot.
- **Split (diagnostic g/e assignment).**
  1. KMeans(2) on raw IQ, scored against the perpendicular bisector of the two
     centroids.
  2. Relabel so state 1 is the **less** populated blob.
  3. Blob gate `MIN_BLOB_SNR` = 2.0 (centroid distance / pooled within-cluster RMS, as
     [modified_ramsey_control](modified_ramsey_control.md#analysis)): below it the
     record is one blob, every shot is 0 (`binary_states` / `binary_amps` all zero) and
     the parity analysis is skipped. `blob_snr` is saved.
  4. The `_binary.png` y-axis reads "assigned g/e (not parity)": the assignment is a
     per-shot readout result. Parity only sets P(e) of each shot, and P(e) ≤ 0.5 under a
     saturating drive, so this trace cannot show parity dwells by eye.
- **Time axis.** dt is the program's scheduled rep period
  (`ChargeDispersionQuasiCWProg.scheduled_rep_period_us()`, the sum of the loop's
  `synci` advances: 1 µs + drive + 0.5 µs, the readout tone + 10 µs, `relax_delay`).
  A 50 µs const drive with 850 µs relax gives 926.81 µs (398599 tProc cycles, pinned in
  `tests/test_program_timing.py`). The CSTQ03 runs give 2076.80 µs
  (`charge_dispersion_quasicw`: 50 µs drive, 2000 µs relax) and 878.80 µs (the two-tone
  path: the search's 2 µs drive leaks into the record, 850 µs relax). Until 2026-10 the
  runner used `1.0 + 0.5 + readout_length + 10 + relax_delay` µs, which omitted the drive
  (2 to 50 µs short, up to about 5 %).
- **Parity analysis** (`qcw_parity_analysis`, when the blob gate passes):
  1. Readout self-calibrated from the record (`calibrate_readout_from_record`): a
     two-Gaussian mixture of the shots themselves, the more populated cloud taken as g.
     The shots are raw accumulator sums, so a SingleShot calibration in normalised units
     does not apply, and no calibration acquisition is added. The mixture weight `w_e`
     is the record's mean P(e).
  2. `analyze_modified_ramsey_record` on the projected record with dt above, the
     expected dwell `expected_parity_dwell_ms`, and the mapping P(e | parity) **fitted**
     with the rate (seeded at (w_e/2, 3 w_e/2), whose mean is w_e;
     `mapping_probabilities_calibrated` False). No on-resonance value is assumed: the
     two-tone path's drive is not necessarily saturating. The emission-SNR gate and
     every other gate of that analysis apply unchanged.
  3. Feasibility: when the expected dwell holds fewer than `MIN_SAMPLES_PER_DWELL` = 10
     samples a warning is printed and saved (`parity_analysis["feasibility_warning"]`):
     shorten `relax_delay` and use active reset. Synthetic records give a usable rate at
     25 samples per dwell, an error of tens of % at 2.7 and often no identifiable fit at
     1.2. Both CSTQ03 quasi-CW configurations warn (2.8 samples per dwell in the two-tone
     path, 1.2 in `charge_dispersion_quasicw`).
  4. The result dict (`rep_period_us`, `samples_per_expected_dwell`, `blob_snr`,
     `feasibility_warning`, `analysed`, `reason`, `summary`) is saved as the npz key
     `parity_analysis`. An analysis error is recorded in `reason`, never raised, so the
     record is always written.
- **Ramsey.** Single averaged point; no fit.

## Findings & notes

- Charge-dispersion doublet in the runner: middle 2306.310396 MHz, upper 2306.567327,
  lower 2306.032673, split 0.5347 MHz. The device and date are not recorded; it is
  not a CSTQ03 frequency in the current table. Verify before reuse.
- The Ramsey step needs tuned pi and pi/2 pulses. Choose the frequency at one of the
  charge-dispersion extrema (runner note, undated).
- Use the background-subtracted IQ projection, not |I+iQ|², for two-tone peaks. The
  magnitude is dominated by the large noisy background quadrature and buries the
  qubit feature.
- 2026-07-28: a NameError in `run_charge_dispersion_quasicw` used to abort before the
  npz was written, so every earlier quasi-CW run lost its data. That is fixed.
- The doublet search in `two_tone_charge_dispersion_quasicw` is the same idea that was
  removed from modified_ramsey because it "never worked reliably".

## Known issues

- **Wait 1/df vs 1/(2·df).** Two branches split by df accumulate a relative phase
  2π·df·τ. At τ = 1/df that is 2π, i.e. the branches are indistinguishable. The
  Modified Ramsey uses τ = k/(2·df) with odd k. The wait here is also edge-to-edge,
  not centre-to-centre. Unless `df` here means something else (not documented),
  expect no parity contrast.
- `charge_dispersion_ramsey` raises KeyError: `df` is missing from the CSTQ03
  `ChargeDispersion_params`. Its loop count is borrowed from the coherence group's
  `repetitions`.
- `display(plotDisp=True)` blocks on every repetition (unless the Agg backend is
  active).
- `two_tone_charge_dispersion_quasicw` leaks state:
  - it writes the found `probe_freq` into the caller's `ChargeDispersion_params`, so a
    later `charge_dispersion_quasicw` in the same session uses the leaked value;
  - one cfg is reused across all cycles, so with spec `Gauss = False` the search's
    `qubit_gain`/`qubit_length` carry into the quasi-CW record;
  - the quasi-CW drive takes Gauss/sigma/gain from the **spec** group, not from this
    step's own keys.
- The centred-peak branch is checked first. Whenever the strongest peak sits within
  0.05 MHz of the qubit centre, the `df` requirement is bypassed (separation may be 0).
- The yoko is ramped even with `yoko_fixed`, and it is not restored afterwards.
- The summary txt pairs `peak_vals` from the raw peak finder with `peak_freqs` from
  the Lorentzian choice. These can refer to different peaks.
- `rounds > 1` would keep only the last round in `di_buf`. The program is built in
  `__init__`, so cfg edits after construction are ignored.
