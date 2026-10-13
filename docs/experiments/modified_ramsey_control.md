# modified_ramsey_control: Modified Ramsey at the charge sweet spot (ModifiedRamsey)

## What it measures

This step is a sweet-spot null control for charge-parity detection. At a
charge-insensitive bias point (the "sweet spot") the two parity branches are
degenerate, so a Modified Ramsey record taken there should show **no** parity
telegraph. Each cycle:

1. searches for the sweet spot by two-tone spectroscopy and moves the yoko there;
2. runs a `ModifiedRamsey` record;
3. classifies the shots with KMeans and looks for jumps with a moving average and a
   hysteresis detector.

**It is not the same sequence as [modified_ramsey](modified_ramsey.md)** (see Known
issues), so a null here does not directly validate a modified_ramsey record. Code:
see `qicklab.runs.modified_ramsey` and `qicklab.runs.sweet_spot`.

## Charge-dispersion model

The device's branch separation vs yoko voltage is modelled as

```
S(V) = cd_max · |cos(2π (V − V0) / T)|,     T = cd_period_mv
```

with `cd_max_mhz` and `cd_period_mv` taken from an independent calibration. The
model sets:

- the Ramsey tau: `tau = 1/(2 · cd_max_mhz)`, the maximum-dispersion value, not a
  measured separation;
- the search step (Strategy A below).

## Pulse sequence

1. **Sweet-spot search** (`find_sweet_spot`, moves the yoko).
   - Each spectroscopy point is a `QubitSpecSliceFF` acquisition over ±`SpecSpan`
     around the qubit centre.
   - **Strategy A** (when `cd_period_mv` is known): if the first spectrum shows two
     peaks separated by ≥ `df`, jump **half a period** from the current V, then take
     one more spectrum. Typically 1–2 acquisitions.
   - **Strategy B** (fallback): walk in `dV` steps between `voltage_min` and
     `voltage_max`, at most `max_voltage_tries` steps, tracking the minimum
     separation. Return to the best voltage found.
   - Accept when a single peak is found, or when sep < `sweet_spot_max_df_mhz`.
   - Qubit frequency = midpoint of the two peaks, or the single peak.
2. **Ramsey** at V_sweet, only if the sweet spot was verified. The sequence is the
   [modified_ramsey](modified_ramsey.md#pulse-sequence) program with
   `df = cd_max_mhz`, `f_ge` = the frequency found, and `rounds = 1`:

```
qubit_ch  ─[pi/2]── tau − 4σ ──[pi/2, φ_close]─ 0.05 µs ─┐
res_ch                                                    [ readout ]── mr_relax_delay ──▶
```

Channels `qubit_ch`, `res_ch`, `ro_chs[0]`; no trigger pin; regime-A readout window.

## How to run

Runs in **regime A**. It moves the yoko and leaves it at the last sweet spot.

```python
PLAN = [R.modified_ramsey_control(mr_reps=500, sweet_spot_max_df_mhz=0.1,
                                  hysteresis_low=0.4, hysteresis_high=0.6,
                                  window_ms=0.1)]
```

`cd_max_mhz` and `cd_period_mv` resolve from the device (`Qubit.parity`).

## Parameters

Legacy `ModifiedRamsey_Control_params` keys. Defaults are the CSTQ03 runner values.

| Key | Default | Units | Meaning |
|---|---|---|---|
| `cd_max_mhz` | 0.682 | MHz | Peak charge dispersion of the model. Sets tau and the Ramsey `df`. Required. |
| `cd_period_mv` | 4.37 | mV | Model period T. Enables Strategy A. Required (read with `[]`). |
| `sweet_spot_max_df_mhz` | 0.1 | MHz | Accept the sweet spot if the separation is below this (or a single peak). |
| `df` | 0.5 | MHz | Separation that triggers the Strategy-A half-period jump. |
| `dV` | 0.0005 | V | Strategy-B step. |
| `voltage_min` / `voltage_max` | 0.000 / 0.010 | V | Search bounds. |
| `max_voltage_tries` | 1000 | count | Strategy-B step limit. |
| `num_cycles` | 1000 | count | Search + Ramsey cycles. |
| `SpecSpan` | 1.0 | MHz | ± spectroscopy span. |
| `SpecNumPoints` | 101 | count | Spectroscopy points. |
| `reps` / `rounds` | 10 / 10 | count | Spectroscopy averaging. |
| `relax_delay` | 1500 | µs | Spectroscopy relax (not used by the Ramsey). |
| `sigma` / `gain` / `qubit_length` | 2 / 700 / 2 | µs / DAC / µs | Spectroscopy drive. `Gauss` is in the dict but unread. |
| `mr_relax_delay` | 0.0 | µs | Ramsey relax. See the modified_ramsey findings: 0 leaves residual excitation. |
| `mr_reps` | 500 | shots | Ramsey shots per cycle. |
| `hysteresis_low` / `hysteresis_high` | 0.4 / 0.6 | fraction | Hysteresis thresholds on the moving average. Set by default if absent. |
| `window_ms` | 0.1 | ms | Moving-average window. Set by default if absent. |
| `use_pi_pulse`, `flip_final_pi2`, `symmetric_ramsey`, `use_active_reset`, `reset_*`, `post_reset_wait` | False, False, False, False, … | — | Forwarded to the program (see Known issues). |

## Outputs

- **Spectra** from the search: `QubitSpecSliceFF` records with path `auto-Spec`,
  under `<outer>/ModifiedRamsey_Control/`.
- **Ramsey record:** `ModifiedRamsey_Control/…_data.h5`, png and json. Same h5
  schema as [modified_ramsey](modified_ramsey.md#outputs). The cfg json includes
  `modified_ramsey_timing`.
- **Analysis files** with base `…/ModifiedRamsey_Control/<…>`:
  - `_iq_labeled.png`, `_binary.png`, `_state_moving_avg.png`,
    `_state_hysteresis.png`, `_state_hysteresis_jumps.png`;
  - `.npz`, `_config.json`;
  - one `CycleSummary_<ts>.json` per run.
  - A cycle whose sweet spot is not verified is recorded with
    `stage_failed = "sweet_spot_not_verified"` and **no Ramsey is run**.
- No rate fit is saved: the hysteresis switch count is the output.

## Analysis

1. **KMeans(2)** on the IQ shots, scored against the perpendicular bisector of the
   two centroids.
2. **Blob-SNR gate.** KMeans always returns two centroids. With majority relabelling
   it manufactures a ~50/50 split from a single blob, so the control could never
   report "no switching". The gate is centroid distance / pooled within-cluster RMS:
   - resolved blobs give ≳ 2, one blob ≲ 1;
   - **below 2.0, all shots are set to state 0** (no switching).
3. Otherwise the majority cluster is relabelled state 0.
4. Moving average over `round(window_ms / dt)` shots, then a hysteresis state machine
   (rise above `hysteresis_high`, fall below `hysteresis_low`), which counts switches.

## Findings & notes

- Charge-dispersion model parameters `cd_max_mhz = 0.682 MHz`, `cd_period_mv =
  4.37 mV`. They come from an independent calibration; the device and date are not
  recorded in the code.
- CSTQ03 Q2, 2026-08-04: the measured doublet splitting df = 2.7 MHz is 4× this
  `cd_max_mhz`. Either the fit is stale, or that doublet is not charge parity (see
  [modified_ramsey](modified_ramsey.md#findings--notes)).
- Runner note, undated: `start_voltage = 0.0059 V` "worked for good T2R", i.e. a
  charge-insensitive point. Under the model, the maxima sit a quarter period
  (~1.09 mV) away from a sweet spot.
- History: older runner comments said "tau is computed from S1 (the separation at
  V1)", "f_ge from two-tone at V_sweet" and "either way the Ramsey still runs". The
  code instead uses tau = 1/(2·`cd_max_mhz`), f_ge from `find_sweet_spot`, and
  **skips** the Ramsey when the sweet spot is not verified.

## Known issues

- **Not the same sequence as modified_ramsey.** It omits `tau_harmonic_k` and
  `ramsey_tau_us`, does not forward `max_drive_bandwidth_ratio` (so the limit is 1.0;
  the CSTQ03 MR used 1.4), and uses `df = cd_max_mhz` (0.682) instead of the MR `df`.
  A null here is therefore not comparable to a modified_ramsey record.
- `use_active_reset=True` is forwarded, but no separator or threshold is calibrated.
  The program then raises (missing `readout_threshold`).
- "No peaks at all" (`peak_sep` None) is treated as a verified sweet spot.
- **Acceptance threshold vs peak finder.** The peak finder never returns two peaks
  closer than its 0.10 MHz minimum separation, so `sep < 0.1 MHz` is effectively
  unreachable for a two-peak spectrum. Acceptance in practice comes only from a
  single peak.
- **Half-period jump vs the model.** As written, S(V) = cd_max·|cos(2π(V−V0)/T)|
  repeats every T/2, so a jump of T/2 lands where S is unchanged. Zeros are a
  quarter period from maxima. If Strategy A never converges, this is the likely
  reason. Which of the model or the jump is intended is not documented.
- Strategy A drops the pre-jump voltage from best-tracking. If the jump makes things
  worse, the search cannot return to the starting voltage.
- The step mutates the caller's parameter dict (`setdefault` of the hysteresis keys).
  The yoko is not restored, and `yoko_fixed` is ignored.
- If `window_n` exceeds the number of shots, the moving-average trace is longer than
  the time axis and the plot raises.
- f_ge from the search is the peak midpoint, but the program treats `f_ge` as the
  upper branch. At a true sweet spot the branches are degenerate, so this only matters
  if the spot is not reached.
