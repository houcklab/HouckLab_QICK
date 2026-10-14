# charge_sweep: qubit spectroscopy vs charge bias (QubitSpecSliceFF)

## What it measures

The step steps the charge-bias yoko through a voltage grid and takes a two-tone qubit
spectrum (`QubitSpecSliceFF`) at each bias. The result is a live heatmap of qubit
response vs (frequency, voltage). Charge dispersion appears as the qubit line
splitting into its two parity branches and recombining periodically with gate charge.
Use it to find sweet spots and maxima of the dispersion, and the period that feeds the
`cd_period_mv` / `cd_max_mhz` model of
[modified_ramsey_control](modified_ramsey_control.md). For the cavity version see
[charge_transmission_sweep](charge_transmission_sweep.md). Code: see
`qicklab.runs.charge_sweep`.

## Pulse sequence

Per voltage point, one `QubitSpecSliceFF` frequency sweep (`expts` points, `reps` ×
`rounds`):

```
yoko      ── ramp_to(V) ───────────────────────────────────────────────────────────▶
qubit_ch  ── sync ── 1 µs ─[ spec pulse @ f ]─ 0.5 µs ─┐            (Gauss: gaussian σ, gain; else const qubit_length, qubit_gain)
res_ch                                                  [ readout tone ]── 10 µs ── relax_delay
ADC (ro 0,1)                                              [ window ]
```

- Channels: `qubit_ch`, `res_ch`. Readouts 0 and 1 are hard-coded by the spectroscopy
  program. No trigger pin.
- Frequency grid: `start = f_qubit − SpecSpan`, `step = 2·SpecSpan/SpecNumPoints`. The
  grid is therefore asymmetric by one step: it ends at centre + span − step.
- The readout window is the regime-A window.

## How to run

Runs in **regime A**. The voltage grid comes from the session charge group
(`R.charge_range()`, legacy `charge_params`), and the spec settings from the spec group.

```python
session = Session(..., charge=R.charge_range(voltage_start=0.0, voltage_end=0.05,
                                             voltage_step=0.005))
PLAN = [R.charge_sweep()]
```

**Voltage grid rules.**

- The grid is `np.arange(voltage_start, voltage_end, voltage_step)`. It is half-open:
  `voltage_end` is not measured.
- A step's own parameters override the session group.
- With `yoko_fixed = True` the yoko is not moved. The sweep then just repeats the
  spectrum over time at a fixed bias ("lazy way of sweeping two-tone over time"). See
  below.

### Holding the bias (yoko_fixed)

With the session flag `yoko_fixed = True` the step never writes to the yoko. The
voltage grid only sets the **number of repeats**, N = `len(np.arange(voltage_start,
voltage_end, voltage_step))`. The bias is whatever the yoko already holds, usually
the session bias, but not always: some steps move it and do not restore it (for
example `charge_dispersion`).

- The held level is read back once, before the first slice (`:SOUR:LEV?`), and
  recorded as the bias of every slice.
- Each slice is repeat *i* (0-based) at that level. It is not a point of the grid.
- The heatmap y axis is the repeat index, not voltage. The title of each row reads
  `repeat i/N at V = <held level>`.

Without `yoko_fixed`, every slice records the grid value the yoko was ramped to.

## Parameters

| Key | Default | Units | Meaning |
|---|---|---|---|
| `voltage_start` | 0.0 | V | First bias. |
| `voltage_end` | 0.05 | V | End of the grid (exclusive). |
| `voltage_step` | 0.005 | V | Step. Runner note: "0.0001 has two periods in it" (meaning unclear). |
| `reps` / `rounds` | 20 / 10 | count | Spectroscopy averaging (spec group). |
| `Gauss` | False | bool | Gaussian (σ, gain) or const (`qubit_length`, `qubit_gain`) spec pulse. |
| `sigma` / `gain` | 2 / 800 | µs / DAC | Used only when `Gauss`. |
| `qubit_gain` / `qubit_length` | 1000 / 50 | DAC / µs | Const pulse (frozen into the config when the session is built). |
| `SpecSpan` / `SpecNumPoints` | 10 / 201 | MHz / count | Frequency grid (frozen into the config when the session is built). |
| `min_sep_MHz` / `fit_window_mhz` / `prominent_ratio` | 0.2 / 0.5 / 0.1 | MHz / MHz / – | Per-slice peak display options. |
| `yoko_fixed` | False | bool | Session flag: hold the bias and repeat in time (see above). |

## Outputs

- **Per slice:** `QubitSpecSliceFF` h5/png/json under `QubitSpecFF/`, with
  `current_voltage` in the cfg.
  - Sweeping: `current_voltage` is the grid value the yoko was ramped to.
  - With `yoko_fixed`: `current_voltage` is the held level read back before the
    loop. The cfg also has `repeat_index` (0-based), `acq_time` (local wall-clock ISO
    time, the same clock as the file names) and `nominal_voltage` (the unused grid
    value).
- **Heatmap:** `<last slice name>_ChargeSweepHeatmap.png` and
  `<last slice name>_ChargeSweepHeatmap.npz`, beside the last slice. The npz holds
  `avgamp_map` (row × frequency), `x_pts` and a `yoko_fixed` flag, plus the row
  axis:
  - Sweeping: `voltage_pts`.
  - With `yoko_fixed`: `repeat_index`, `acq_time` (ISO strings), `elapsed_s`
    (seconds since the first slice), `held_voltage` and `nominal_voltage_pts`.
    There is no `voltage_pts`, so code that loads it fails instead of plotting a
    sweep that never happened.
- Peak frequencies per slice (the two tallest peaks, ≥ 0.05 MHz apart) are **printed
  only**, not saved.

## Analysis

- Each slice is reduced with `project_iq_signal`: subtract the background, rotate
  onto the principal axis, and orient by excursion mass. This gives a ~0 baseline with
  the qubit as a positive bump. The background is taken from the outer 15 % of each
  side, so centre the span on the expected line.
- Do not use |I+iQ|². The magnitude is dominated by the large noisy background
  quadrature, buries the peaks and washes out the heatmap.
  - Example, 2026-06-02 Q6: a real feature in I at ~3054 MHz was missed in favour of Q
    noise spikes at 3038/3069 MHz.
  - Example, 2026-09-02 CSTQ03/Q2: a broad ~3753 MHz response inverted into a dip
    under the old whole-trace-median baseline. Hence the edge baseline.
- The live heatmap rescales its colour limits after every slice.

## Findings & notes

- Runner note: `voltage_step` "0.0001 has two periods in it". The meaning is unclear
  and kept verbatim.
- Spec gain history: "750 works Q5"; spec `qubit_length` "9.5 worked"; "500 used for
  charge sweeps" (it is ambiguous whether 500 is a gain or a relax delay). Device/date
  not recorded.

## Known issues

- **The yoko is not restored** after the sweep. Every later step runs at the last
  bias.
- The voltage check only stops the sweep at the first V > 10 V. A negative typo is
  not caught here; `ramp_to` raises on |target| > 10 V when the sweep reaches it.
- If the first point already breaks the loop, or the grid is empty, the heatmap save
  fails with AttributeError/NameError after the loop.
- The step does not use the shared grid validation that
  [charge_transmission_sweep](charge_transmission_sweep.md) has (zero step, empty
  grid, |V| ≤ 10 V).
- It ignores the spec group's `relax_delay`, `SpecSpan` and `qubit_length` and uses
  the values frozen into the config when the session was built. `relax_delay` then
  comes from BaseConfig (3000 µs).
