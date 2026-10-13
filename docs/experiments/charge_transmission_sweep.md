# charge_transmission_sweep: cavity transmission vs charge bias (CavitySpecFF)

## What it measures

The step steps the charge-bias yoko through a voltage grid and takes a full cavity
transmission sweep (`CavitySpecFF`) at each bias. The result is a live |S21| (dB)
heatmap vs (frequency, voltage), plus the tracked resonator frequency (raw dip or
peak, and optionally the hanger-fit minimum) at each bias. Use it to see the
dispersive pull of the charge-dependent qubit on the readout resonator, and how far
the resonator moves over the charge range. For the qubit-side map see
[charge_sweep](charge_sweep.md). Code: see `qicklab.runs.charge_sweep`.

## Pulse sequence

Per voltage point, one `CavitySpecFF` frequency sweep around the current `pulse_freq`:

```
yoko     ── ramp_to(V) ── settle_s ─────────────────────────────────────────────▶
res_ch   ── sync 200 ─[ readout tone @ f ]── 10 µs ── cav_relax_delay ──▶ next point
ADC                     [ window ]
                  ^ adc_trig_offset
```

- Channels: `res_ch`, `ro_chs`. There is no qubit pulse and no trigger pin.
- The window is the regime-A window.
- `CavitySpecFF.acquire()` sweeps `cfg["pulse_freq"]` in place, and `display(fit=True)`
  rewrites it with the fitted minimum. The step therefore **resets `pulse_freq` to the
  starting centre before every slice**.

## How to run

Runs in **regime A**.

```python
PLAN = [R.charge_transmission_sweep(reps=400, rounds=1, fit=False, settle_s=0.0)]
# voltage grid: from the step, else from the session charge group
PLAN = [R.charge_transmission_sweep(voltage_start=0.0, voltage_end=0.05,
                                    voltage_step=0.005)]
```

**Voltage grid rules.**

- The step's own `voltage_start/end/step` override the session charge group.
  Parameters left at None inherit it.
- The grid is half-open, like `np.arange`.
- The step rejects a zero step, an empty grid and any |V| > 10 V. The ±10 V check
  matters because `ramp_to` only rejects targets above +10 V, so a negative typo
  would otherwise slip past.

**Bias restore.** The starting voltage is read before the sweep and the yoko is
ramped back to it in a `finally` block, also on error or Ctrl-C. An aborted sweep
must not leave the bias parked at an arbitrary point, because every later measurement
would silently run at that charge offset. With `yoko_fixed` nothing is moved or
restored.

**reps vs rounds.**

- `reps` are hardware averages inside one tProc program. `rounds` re-run the program
  and average in software.
- `reps = 400, rounds = 1` and `reps = 20, rounds = 20` both average 400 shots, but
  the second starts 20× more programs.
- Every program start risks the stale-shot-counter race. It surfaces as `could not
  broadcast input array from shape (26,2) into shape (20,2)`.
- Prefer `reps`. Raise `rounds` only if the accumulation buffer overflows.

## Parameters

Legacy `ChargeTransmission_params` keys (CSTQ03 runner values). None means "inherit".

| Key | Default | Units | Meaning |
|---|---|---|---|
| `reps` | 20 | count | Hardware averages per frequency point. |
| `rounds` | 20 | count | Software re-runs. Prefer `reps` (see above). |
| `span` → `TransSpan` | None (→ transmission group, 5) | MHz | Frequency span. |
| `num_points` → `TransNumPoints` | None (→ transmission group, 201) | count | Frequency points. |
| `fit` | False | bool | Per-slice hanger fit. Slower; adds a fit-minimum trace. |
| `settle_s` | 0.0 | s | Wait after each ramp. |
| `voltage_start` / `voltage_end` / `voltage_step` | 0 / 0.05 / 0.005 | V | Grid. None inherits the session charge group. |
| `cavity_min` | True | bool | Device: the resonance is a dip (True) or a peak. |

## Outputs

- **Per slice:** `CavitySpecFF` h5/png/json under `ChargeTransmissionFF/`, with
  `current_voltage` in the cfg.
- **Map:** `<last slice name>_ChargeTransmissionHeatmap.png` (with the tracked
  extremum overlaid) and `…_ChargeTransmissionHeatmap.npz`, beside the last slice. The
  npz holds `db_map`, `avgi_map`, `avgq_map`, `fpts_mhz`, `x_pts_ghz` (absolute,
  including `cavity_LO`), `voltage_pts`, `raw_extremum_mhz`, `fit_extremum_mhz` and
  `cavity_min`.
- A printed summary of how far the resonator moved (kHz) over the voltage range.
- The cavity frequency is **not** written back to the session config: "the" cavity
  frequency is undefined across a charge sweep. Contrast this with
  `transmission_sweep`, which does write it back.

## Analysis

`y_dB = 20·log10|I + iQ|` per slice. The raw extremum is the argmin if `cavity_min`,
else the argmax. With `fit=True`, the hanger-fit minimum is tracked as well.
`cavity_LO` (Hz) is added only for the GHz display axis. A slice whose frequency count
differs from the first raises RuntimeError.

## Findings & notes

- reps vs rounds and the shape-(26,2) broadcast error: see above (runner note, also on
  [averaging](../concepts/averaging.md#reps-vs-rounds-prefer-reps)).

## Known issues

- The `if db_map is None: return` branch is unreachable: an exception before the first
  slice propagates past it.
- The live plot uses interactive matplotlib. Under the import-time Agg backend it does
  not refresh on screen; the png is still saved.
