# charge_sweep: qubit spectroscopy vs charge bias (QubitSpecSliceFF)

## What it measures

The step steps the charge-bias yoko through a voltage grid and takes a two-tone qubit
spectrum (`QubitSpecSliceFF`) at each bias. The result is a live heatmap of qubit
response vs (frequency, voltage). Charge dispersion appears as the qubit line
splitting into its two parity branches and recombining periodically with gate charge.
Use it to find sweet spots and maxima of the dispersion, and the period that feeds the
`cd_period_mv` / `cd_max_mhz` model of
[modified_ramsey_control](modified_ramsey_control.md): each slice's doublet is extracted
and the splitting vs bias is fitted (see
[Doublet splitting fit](#doublet-splitting-fit)). For the cavity version see
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
- The grid is validated before the yoko moves (`charge_sweep_voltages`, shared with
  [charge_transmission_sweep](charge_transmission_sweep.md)): a zero step, an empty grid
  (for example a step of the wrong sign) or any |V| > 10 V raises `ValueError`.
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

### Sampling the period

Before the first slice the step prints the grid range, the step and the points per mV.
`run_charge_sweep(ctx, Spec_relevant_params, cd_period_mv=None)` takes the device's
charge-dispersion period T (the `cd_period_mv` of
[modified_ramsey_control](modified_ramsey_control.md); the CSTQ03 runner passes
`ModifiedRamsey_Control_params["cd_period_mv"]`). With it the step also prints the points
per **S period** and warns (never raises) when |step| > T_S/8.

- **Period convention.** The model S(V) = cd_max·|cos(2π(V − V0)/T)| repeats every
  T_S = T/2, so the check uses T_S = `cd_period_mv`/2. This is the conservative reading
  (see the open question in
  [modified_ramsey_control](modified_ramsey_control.md#known-issues)).
- Example: the runner's 5 mV step against T = 4.37 mV gives 0.44 points per S period. The
  map is fully aliased: it shows an apparent period of tens of mV that is not the device's.
  A step of 0.27 mV or less is needed for 8 points per S period.
- Under `yoko_fixed` there is no bias axis and nothing is checked.

## Parameters

| Key | Default | Units | Meaning |
|---|---|---|---|
| `voltage_start` | 0.0 | V | First bias. |
| `voltage_end` | 0.05 | V | End of the grid (exclusive). |
| `voltage_step` | 0.005 | V | Step. Runner note: "0.0001 has two periods in it" (meaning unclear). Against `cd_period_mv` = 4.37 mV this step aliases; see [Sampling the period](#sampling-the-period). |
| `cd_period_mv` | None | mV | Function argument, not a cfg key: the model period T for the sampling check and the fit's alias guard. |
| `reps` / `rounds` | 20 / 10 | count | Spectroscopy averaging (spec group). |
| `Gauss` | False | bool | Gaussian (σ, gain) or const (`qubit_length`, `qubit_gain`) spec pulse. |
| `sigma` / `gain` | 2 / 800 | µs / DAC | Used only when `Gauss`. |
| `qubit_gain` / `qubit_length` | 1000 / 50 | DAC / µs | Const pulse (frozen into the config when the session is built). |
| `SpecSpan` / `SpecNumPoints` | 10 / 201 | MHz / count | Frequency grid (frozen into the config when the session is built). |
| `min_sep_MHz` / `fit_window_mhz` / `prominent_ratio` | 0.2 / 0.5 / 0.1 | MHz / MHz / – | Per-slice peak display options. `min_sep_MHz` is also the doublet resolution and the floor of the censoring level of the splitting fit (see Censoring); `fit_window_mhz` also seeds the joint doublet refit's window. |
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
- **Doublet per slice** (also in the npz, one row per slice; frequencies in MHz on the
  `x_pts` axis):
  - `doublet_freqs_mhz` (rows × 2, NaN-padded): the selected line(s), sorted.
  - `doublet_refit_mhz` and `doublet_refit_hwhm_mhz` (rows × 2, NaN-padded): centres and
    HWHMs of the joint two-Lorentzian refit of a selected pair (see Splitting below);
    NaN where the slice has one line or the refit failed.
  - `doublet_amp` (rows × 2): the projected trace at each selected line's nearest bin.
  - `doublet_source`: the selection provenance (`two_lorentzian_centers`,
    `one_lorentzian_center_plus_peak`, `two_highest_peaks`, `single_line_unresolved`,
    `partner_not_significant`) and `partner_snr`.
  - `sep_mhz` and `f_mean_mhz`: splitting and centre of the two lines from the joint
    refit. NaN where the slice has one line or the refit failed.
  - `censor_limit_mhz`: the censoring level of each `single_line_unresolved` slice
    (see Censoring below); NaN for every other slice and for a trace with no line
    above 5 noise sigmas.
  - `lorentz_centers_mhz`, `lorentz_fwhm_mhz`, `lorentz_r2` (rows × 2, NaN-padded): the
    display's Lorentzian fits.
- **Splitting fit** (in the npz, see below): `fit_status`, `fit_message`,
  `fit_cd_max_mhz`, `fit_s_period_mv` (T_S), `fit_cd_period_mv` (2·T_S, the
  `cd_period_mv` convention), `fit_v0_mv`, each value with an `_err` 1σ partner; the
  f_mean line `fit_f0_mhz` and `fit_f_slope_mhz_per_mv` with errors; and
  `prior_cd_period_mv` (the argument, NaN if not given). Values are NaN unless
  `fit_status` is `ok`. Under `yoko_fixed`, `fit_status` is `yoko_fixed` and nothing is
  fitted. Nothing is written back to the session or the device file.
- One line per slice is printed: the doublet, its joint-fit splitting (or that the refit
  failed) and its source.

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
- The doublet of each slice is picked by `choose_two_tone_freqs_from_lorentz_or_peaks`
  (the selection and significance gate of [two_tone_spec](two_tone_spec.md)) with
  `min_sep_MHz` as the resolution. It returns one frequency when the lines are closer
  than `min_sep_MHz`, or when a partner bin peak lies within the fitted half width of a
  single Lorentzian (`single_line_unresolved`), or when the weaker one fails the
  significance gate (`partner_not_significant`).
- **Splitting.** A selected pair is refitted jointly (`refit_doublet_jointly`: one
  offset and two Lorentzians, seeded at the selected frequencies, window grown to 3 FWHM
  beyond the pair and capped at the half-span), and `sep_mhz` is the difference of the
  refitted centres. The selection's own frequencies are not used for the splitting: the
  display fits each line alone in a window clipped to half the pair's separation and
  ignores the other line's tail, which pulls both centres inward. In simulation through
  the real display (SNR 20) the selected separation reads 0.8× the true one at 2 HWHM,
  0.88× at 2.5 HWHM and 0.95× at 3.4 HWHM; end to end that put cd_max 6 to 18 of its own
  σ low for HWHM 0.1 to 0.3 MHz. The joint refit is within 0.2 % of the truth and the mean
  end-to-end pull (5 seeds) is below 1σ. A refit that fails (no convergence, R² < 0.6, or a centre
  more than half of max(`min_sep_MHz`, its HWHM) from its seed) drops the slice from the
  fit.

### Doublet splitting fit

After the last slice, `fit_charge_dispersion_splitting` (`qicklab.analysis.spectroscopy`)
fits

```
sep(V) = cd_max · |cos(π (V − V0) / T_S)|,     T_S = cd_period_mv / 2
```

This is the same curve as the [modified_ramsey_control](modified_ramsey_control.md) model
cd_max·|cos(2π(V − V0)/T)| with T = `cd_period_mv`. The fit reports T_S and
`cd_period_mv` = 2·T_S. V0 is a maximum of the splitting, the one in
[V_min, V_min + T_S).

- **Censoring.** A `single_line_unresolved` slice is a point with sep below a per-slice
  bound, not sep = 0. The bound (`single_line_splitting_bound`) is max(`min_sep_MHz`, W).
  W is the extent of the projected trace above a quarter of its peak: the trace minus the
  edge baseline is smoothed over 5 bins, and W runs from the first to the last bin at or
  above 0.25 × the smoothed maximum, gaps included.
  - Why it bounds the splitting: each line's centre stands at least as high as that line
    alone. Noise-free, both centres therefore lie inside W whenever the weaker line is at
    least a quarter of the trace's peak, which holds for any splitting and line width once
    the weaker line is at least 1/3 as high as the stronger. Smoothing and the wings lifting
    the edge baseline erode that margin a little.
  - Checked through the real display on a 2 MHz span (HWHM 0.04 to 0.3 MHz, splittings 0 to
    1.2 MHz in 20 kHz steps, 3 seeds, about 200 to 300 unresolved slices per case): no bound
    fell below the true splitting for height ratios 1, 0.6 and 0.5 at SNR 8 and 20, or for
    equal heights at SNR 6. At a ratio of 0.4 (SNR 8) one did; at 0.3, broad lines far
    apart are not bounded. Parity lines more unequal than about 70/30 are outside the
    check.
  - End to end (`run_charge_sweep` with the real display, 0 to 20 mV in 0.2 mV steps,
    `cd_period_mv` = 4.37, 12 seeds per case) no censored slice was bounded below its true
    splitting. Mean cd_max pull (SD about 1, so ±0.3 is noise): HWHM 0.2 MHz −0.02 at
    SNR 20, −0.06 at SNR 8, +0.11 at 60/40 heights, −0.17 at 67/33, −0.12 at SNR 8 and
    60/40; HWHM 0.1 MHz +0.17 (SNR 20) and +0.18 (SNR 8); HWHM 0.3 MHz −0.39 (SNR 20) and
    −0.56 (SNR 8), a small residual not from the censoring.
  - Previous bounds that were not bounds. The half-maximum width of the contiguous run around
    the tallest bin fell below the splitting of blends 2 to 4 HWHM wide: the dip before the
    weaker line, one noisy flank bin or a noise-raised tallest bin ends the run inside the
    doublet. It put cd_max about −1.5σ low at SNR 8 and −1.4σ low at 60/40 heights. The
    display's Lorentzian widths are not a bound either: with two seeds its window is clipped
    to half their separation and the surviving fit can be narrower than the splitting (in
    simulation, a 0.55 MHz doublet of 0.3 MHz HWHM lines came back with one 0.16 MHz HWHM
    line).
  - W is looser than the FWHM (√3 × it for one line), which only weakens the constraint. A
    bound wider than `min_sep_MHz` matters: censoring at `min_sep_MHz` alone when the
    resolution is 0.5 MHz biases cd_max about −4σ.
  - The point enters the fit one-sided: it is penalised only if the model there is above the
    bound. A trace whose tallest bin is under 5 noise sigmas, or whose quarter-peak level is
    under 3 sigmas of the smoothed trace, has no trustworthy bound and is dropped, as is a
    `partner_not_significant` slice (no splitting information).
- **Method.** The seed comes from a scan of the period: sep² is a sinusoid of period T_S.
  A least-squares fit of (cd_max, V0, T_S) follows. The 1σ errors come from the Jacobian,
  scaled by the residual variance.
- **Refusals.** The fit reports a status other than `ok`, with NaN values, when:
  - `undersampled`: a known `cd_period_mv` gives fewer than 4 grid points per T_S (the
    runner's 5 mV grid: 0.44), or the fitted T_S is shorter than 4 steps;
  - `insufficient_coverage`: the grid spans less than one fitted T_S;
  - `too_few_points`: fewer than 5 resolved doublets;
  - `fit_failed`.
- **Without `cd_period_mv`** the scan only considers periods of at least 4 steps. A true
  period shorter than that aliases and cannot be detected from the data, so the message
  says the result holds only under that assumption.
- **f_mean(V)**, the centre of resolved doublets, is fitted with a straight line
  f0 + slope·(V − V_c), where V_c is the mean bias of those points. The parity branches
  sit symmetrically about it, so a slope is drift of the line, not dispersion.
- **Errors.** The 1σ errors are statistical only. The joint refit removes the systematic
  of the selected frequencies, but not a line-shape mismatch (a non-Lorentzian line). The
  censoring bound is checked down to a weaker parity line half as high as the stronger (67/33);
  more unequal lines can leave a censored slice bounded below its splitting, which biases
  cd_max low.
- Checks (`tests/test_charge_dispersion_fit.py`): on synthetic sep(V) over a 0.2 mV grid
  the fit recovers cd_max = 0.682 MHz and T = 4.37 mV within the errors, and the 5 mV grid
  is refused. End to end, `run_charge_sweep` with the real `QubitSpecSliceFF.display` on
  simulated spectra (HWHM 0.2 MHz; SNR 20, SNR 8, and SNR 20 with 60/40 heights) recovers
  cd_max and T within 4σ, and every censored slice's bound is at or above its true
  splitting. The bound alone is checked through the real display at SNR 8 and 20 for
  height ratios 1, 0.6 and 0.5, and in fine steps just above `min_sep_MHz` for narrow
  lines.

## Findings & notes

- Runner note: `voltage_step` "0.0001 has two periods in it". The meaning is unclear
  and kept verbatim.
- Spec gain history: "750 works Q5"; spec `qubit_length` "9.5 worked"; "500 used for
  charge sweeps" (it is ambiguous whether 500 is a gain or a relax delay). Device/date
  not recorded.

## Known issues

- **The yoko is not restored** after the sweep. Every later step runs at the last
  bias.
- The runner's grid (5 mV step) undersamples the CSTQ03 period (`cd_period_mv` =
  4.37 mV). The step warns and the splitting fit refuses; use a step ≤ 0.27 mV over at
  least one period to measure cd_max and T.
- `cd_max_mhz` / `cd_period_mv` in the runner still come from the earlier, unrecorded
  calibration. The fit here reports values but does not write them back.
- It ignores the spec group's `relax_delay`, `SpecSpan` and `qubit_length` and uses
  the values frozen into the config when the session was built. `relax_delay` then
  comes from BaseConfig (3000 µs).
