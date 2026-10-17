# twpa: TWPA bias, pump and gain calibration (qicklab.twpa)

## What it measures

Five standalone scripts bring up the travelling-wave parametric amplifier (TWPA) in
front of the readout chain. They are not QICK experiments: no RFSoC, no session, no
`ExperimentClass`, no regime. They drive a dedicated YOKO GS200 (bias current), a
Windfreak SynthHD (pump) and a Keysight PNA-X (signal-path |S21|).

| Module | Purpose |
|---|---|
| `qicklab.twpa.set_bias` | Ramp the TWPA bias current to a target at ≤ 300 nA/s. Measurement-free. |
| `qicklab.twpa.set_pump` | Park the pump at one (frequency, power) and leave RF on, or switch it off. Measurement-free. |
| `qicklab.twpa.flux_sweep` | Sweep the bias across the first flux period with the pump OFF; PNA-X band-mean \|S21\| per point. Calibration only. |
| `qicklab.twpa.pump_sweep` | 2-D pump (frequency × power) grid at fixed bias; band-mean gain per point against a pump-OFF reference taken at the start of each frequency row. |
| `qicklab.twpa.gain_compare` | \|S21\| pump OFF vs ON across the signal band, interleaved; gain = ON − OFF (dB). A completed run leaves the pump ON at the ON point. |

`set_bias` and `set_pump` are measurement-free: map |S21| vs bias with `flux_sweep` (or a
separate transmission run, e.g. `CavitySpecFF`), and find the pump point with `pump_sweep`;
then park there with `set_bias` / `set_pump` before running qubit measurements.

Shared helpers: `qicklab.hardware.pnax` (`measure_s21_band`, `band_mean_dB`),
`qicklab.hardware.synthhd` (`SynthHD`, `set_pump_channels`), `qicklab.hardware.yoko`
(`pick_current_range`, `enable_current_output_safely`, `ramp_current`, default step period
`STEP_PERIOD_S`, the bias address `TWPA_YOKO_ADDRESS`) and `qicklab.twpa.common`
(`timestamped_paths`, the state log `append_state`, the read-only bias readback `query_bias` /
`read_bias_state`). The other instrument addresses (`PNAX_ADDRESS`, `PUMP_SYNTH_PORT`)
and the pump operating point are module-level constants in each script for now. A per-device
`Setup.twpa` (`TwpaSetup(yoko_addr, synth_port, pnax_addr, pump=(ghz, dbm, ch), bias_ua)`) is
planned but not yet in code (phase 5). When it lands, the charge-yoko refusal in
`open_charge_yoko` must also check the device's `twpa.yoko_addr`: today it compares only against
`TWPA_YOKO_ADDRESS`. See [hardware](../hardware.md).

## Pulse sequence

There is no pulse sequence. The bring-up order is:

```
pump OFF ──▶ flux_sweep ──▶ set_bias ──▶ pump_sweep ──▶ gain_compare ──▶ set_pump --on
             (once per      (0 → target,  (only if no    (pump left ON   (pump ON; needed
              cooldown;      ≤ 300 nA/s)   operating      if it           after pump_sweep or
              ends at 0 µA)                point; ends    completes)      an aborted
                                           pump OFF)                      gain_compare)
```

Every script appends its end state to the [state log](#state-log); check its last line before
qubit measurements (bias at the operating point, pump ON).

1. Bias first, with the pump disabled, sweeping slowly from 0. Then pump.
   Before any ramp, `set_bias` and `flux_sweep` run `enable_current_output_safely`: it queries
   `:OUTP?`, `:SOUR:FUNC?` and `:SOUR:LEV?` and prints them. Output off: `:SOUR:FUNC CURR`,
   `:SOUR:RANG <range>`, `:SOUR:LEV 0`, `:OUTP ON` (the ramp starts from 0; a stale stored
   setpoint is discarded, never applied as a step). Output on in current mode: the setpoint is
   kept and the ramp starts from it (`:SOUR:RANG?` is read; the range is changed only at 0 A).
   Output on in voltage mode: the script stops without writing. Details:
   [hardware](../hardware.md#bias-gs200-at-gpib1112instr-current-mode).
2. `flux_sweep` ends by ramping the bias back to 0 (only once the YOKO is in current mode with
   its output on), so it runs before `set_bias`, never after it.
3. `pump_sweep` disables the pump RF on exit (success, exception or Ctrl-C); if that and
   `close()` both fail it warns and logs the pump state as unknown. `gain_compare`
   does too on Ctrl-C or an exception; after a completed run it re-enables the ON point and
   leaves the SynthHD port open, like `set_pump` (`LEAVE_PUMP_ON = True`; `--off`, or
   `LEAVE_PUMP_ON = False`, switches the pump off instead).

## How to run

Each script is configured by the UPPERCASE constants at the top of its module, prints its plan
and requires typing `yes` before it touches hardware.

```
python -m qicklab.twpa.set_bias
python -m qicklab.twpa.set_pump --on     # --on parks the pump ON; --off (the default) RF-disables
python -m qicklab.twpa.flux_sweep
python -m qicklab.twpa.pump_sweep
python -m qicklab.twpa.gain_compare      # --off: switch the pump off after a completed run
```

- **set_bias.** Verify the pump RF output is OFF, set `TARGET_CURRENT_uA`, run. The address
  is `TWPA_YOKO_ADDRESS` in `qicklab.hardware.yoko` (shared with the charge-line opener, which
  refuses it). `YOKO_CURR_RANGE_A = None` auto-picks the range; a number forces it.
- **set_pump.** Verify the DC bias is parked (`set_bias`); the script does not write to the YOKO.
  Set `PUMP_SYNTH_PORT` and `PUMP_SETTINGS`: each listed channel gets its **own**
  (freq_GHz, power_dBm); give both channels the same pair to drive them identically, different
  pairs to drive them independently. To turn the pump off, set `DISABLE_PUMP = True` or pass
  `--off`. `DISABLE_PUMP = True` is committed, so pass `--on` to park the pump ON (`--on` wins
  over the constant; passing both raises). The script also opens the TWPA YOKO read-only to log
  the bias with the pump state.
- **flux_sweep.** `PNAX_MEAS_MODE` picks the figure of merit: `"BAND"` sweeps
  [`PNAX_F_START_HZ`, `PNAX_F_STOP_HZ`] and uses the mean |S21| (dB) over the band; `"CW"` parks
  on `PNAX_CW_FREQ_HZ` and uses |S21| (dB) at that one tone (faster, no band averaging). The ramp
  rate is enforced ≤ 300 nA/s by `ramp_current`; on exit (success, exception or Ctrl-C) the bias
  is ramped back to 0. Do not use it for daily operation: set the operating point with
  `set_bias` afterwards.
- **pump_sweep.** Same `PNAX_MEAS_MODE` choice. The channels in `PUMP_CHANNELS` are driven
  **identically** (same frequency and power at every point); for offset or independent control,
  add fixed offsets where the channels are programmed inside the loop. Bias must already be
  parked; the script does not write to the YOKO (it reads the bias once, see below). Each
  pump-frequency row starts with one trace with
  the pump RF disabled (settle `SETTLE_AFTER_FREQ_S`), then enables RF and sweeps the powers.
- **gain_compare.** Set `PUMP_ON_FREQ_GHz` / `PUMP_ON_POWER_dBm` to the `pump_sweep` optimum for
  the signal band. "Pump OFF" disables RF on every listed channel; "pump ON" programs the ON
  point and enables RF. Bias must already be parked. On exit see step 3 of the bring-up order:
  the pump stays ON at the ON point only after a completed run.
- **pump_sweep, gain_compare bias readback.** Neither script writes to the YOKO. Each opens it
  once before the run, queries `:OUTP?`, `:SOUR:FUNC?` and `:SOUR:LEV?`, closes it, and stores
  `bias_uA`, `yoko_output_on`, `yoko_func` and `yoko_level` in the npz. A failed readback prints
  a warning and stores NaN / -1 / `"unknown"`; it never stops the run.
- SCPI was tested on a Keysight PNA-X N52xx; other VNAs may need command tweaks
  (`configure_pnax`, `qicklab.hardware.pnax.measure_s21_band`).

## Parameters

**Datasheet limits and safety.**

| Quantity | Value | Meaning |
|---|---|---|
| Max bias sweep rate | 300 nA/s | Datasheet ceiling. Faster risks flux trapping. Do not raise. |
| Nominal operating point | ~11 µA | ≈ 15 µT internal field, impedance matched. |
| End of first flux period | ~25 µA | One-off flux calibration only. |
| Normal-operation guidance | do not sweep well above ~11 µA | Higher currents may reduce performance or trap flux. |
| Bias hard limit in `set_bias` | 25 µA | Targets above it raise. |
| Bias step period | 0.05 s | GPIB update interval while ramping (`STEP_PERIOD_S` in `set_bias`, passed as `dt` by `set_bias` and `flux_sweep`; `qicklab.hardware.yoko.STEP_PERIOD_S` is the library default of `ramp_current`); smaller = smoother, more bus traffic. |
| YOKO current ranges | 1, 10, 100, 200 mA | Setpoints above the active range are **silently clipped**. The range is auto-picked from the target. |
| Pump power ceiling | 0 dBm (`set_pump`, `gain_compare`); 20 dBm (`pump_sweep`) | Hard refusal above. |
| Pump state after `gain_compare` | ON at the ON point after a completed run; OFF after Ctrl-C / an error | `LEAVE_PUMP_ON = True`; `--off` overrides. |

**Instruments.**

| Item | Value |
|---|---|
| TWPA bias YOKO | `GPIB1::12::INSTR`, current-source mode, connected directly to the TWPA bias port. This is not the charge-line YOKO at `GPIB1::9`. |
| Pump | Windfreak SynthHD on `COM5`, locked to the external 10 MHz reference on connect. |
| PNA-X | `GPIB0::16::INSTR`, Keysight N52xx SCPI. |
| Output | `<SAVE_DIR>/<%Y%m%d_%H%M%S>_<RUN_TAG>.npz/.png`. `flux_sweep` and `gain_compare` save the npz after each point; `pump_sweep` saves it once per pump-frequency row and once more on exit if a row was interrupted, atomically (`<npz>.tmp`, then rename); a failed write prints a warning and the sweep continues (the next row retries). If the rename fails after a complete write, the warning names `<npz>.tmp`, which is kept and holds the newest data. If the last save still fails on exit, the run ends with a `data NOT saved` warning instead of `Saved: <npz>`. CSTQ03 2026-10-01 cooldown: `V:/t1Team/Data/2026-10-01_BFC_cooldown/TWPA_calibration`. |

**Per-script settings** (legacy constants, CSTQ03 values).

| Script | Setting | Value |
|---|---|---|
| set_bias | `TARGET_CURRENT_uA` | 0 (committed). See findings for history. |
| set_pump | `PUMP_SETTINGS` | ch1: 10.7165 GHz, −5.5 dBm |
| set_pump | `DISABLE_PUMP` | True (committed): running it without `--on` only turns the pump off |
| flux_sweep | bias grid | −25 → +25 µA, 51 points (1.0 µA spacing), 0.5 s settle |
| flux_sweep | PNA-X | BAND 5–8 GHz, 201 points, IF BW 100 Hz, −25 dBm, 4 averages, 30 s timeout (CW mode: 7 GHz) |
| pump_sweep | grid | 10.70–10.73 GHz × 401 points, −10 → 0 dBm × 21 points; settle 0.20 s (freq) / 0.05 s (power) |
| pump_sweep | PNA-X | BAND 6–8 GHz, 21 points, IF BW 500 Hz, −25 dBm, 100 averages |
| pump_sweep | VISA timeout | 3 × (n_points / IF_BW × n_avg) + 5 s, floor 30 s |
| gain_compare | pump ON | 10.7165 GHz, −5.5 dBm, channel [1] |
| gain_compare | band | 2–10 GHz, 401 points, IF BW 1000 Hz, −25 dBm, 60 s timeout |
| gain_compare | repeats | 10 OFF/ON pairs, 0.30 s settle after each pump toggle |
| gain_compare | `LEAVE_PUMP_ON` | True: a completed run leaves the pump ON |
| all | `TWPA_STATE_DIR` (`qicklab.twpa.common`) | `V:/t1Team/Data/2026-10-01_BFC_cooldown/TWPA_calibration` |

## Outputs

- **flux_sweep:** npz/png of band-mean |S21| (dB) vs bias, and the bias that
  maximises it. Pump OFF, so this is bare transmission, not gain.
- **pump_sweep:** npz/png map of band-mean gain vs (frequency, power), and the best
  point. Gain is measured against a per-row pump-OFF reference:
  gain(f) = |S21|_on(f) − |S21|_off,row(f) (dB). The npz keeps the ON data as before
  (`s21_band`, `mean_band_dB` = band-mean ON |S21|, `completed`) and adds `s21_off`
  (rows × signal points), `off_band_dB`, `off_completed`, `gain_band_dB` (band-mean gain),
  `gain_min_dB` (band-min gain) and `gain_ripple_dB` (max − min of gain(f) across the band).
  The png shows the gain map and the gain(f) trace at the best point.
- **gain_compare:** npz/png of |S21|_off(f), |S21|_on(f), and gain(f) = on − off
  (dB), averaged over the repeats.
- **pump_sweep and gain_compare** npz also hold the TWPA bias readback taken before the run:
  `bias_uA` (NaN unless the YOKO is in CURR mode with its output on), `yoko_output_on`
  (1 / 0 / -1 unknown), `yoko_func` (`CURR` / `VOLT` / `unknown`) and `yoko_level` (the raw
  setpoint, A or V).
- set_bias and set_pump write no data file; like the other three they append one line to the
  state log.

### State log

`<TWPA_STATE_DIR>/twpa_state.jsonl` (`qicklab.twpa.common.TWPA_STATE_DIR`, the CSTQ03 TWPA
calibration folder; one shared file for all five scripts). Each script appends one JSON object
on exit, including Ctrl-C and errors, from the point where it can change the TWPA state: once
the YOKO (and PNA-X) are open, before the first write (`set_bias`, `flux_sweep`), or from the
SynthHD connect, which switches RF off (`set_pump`, `pump_sweep`, `gain_compare`). An exit
before that (declining the `yes` prompt, failing to open the PNA-X or YOKO) changes nothing and
writes no line, so the previous line still holds:

| Field | Content |
|---|---|
| `time`, `unix_time` | local ISO time and epoch seconds of the write |
| `script`, `action` | e.g. `twpa_set_pump` / `pump_on`, `twpa_gain_compare` / `gain_compare` |
| `outcome` | `completed`, `interrupted` (Ctrl-C) or `error` |
| `bias` | `{bias_uA, yoko_output_on, yoko_func, yoko_level}`, read-only from the TWPA YOKO (`set_bias`, `flux_sweep`: after their ramp; `set_pump`: after the pump action; `pump_sweep`, `gain_compare`: before the run). `bias_uA` is null unless CURR mode with the output on |
| `pump` | per listed channel `{channel, freq_hz, power_dbm, rf_enable}` as commanded at exit (the SynthHD is never read back); null from `set_bias` and `flux_sweep`, which do not touch it. `rf_enable` null means unknown: the SynthHD connect failed, `set_pump --on` stopped before every channel was programmed, or (`pump_sweep`, `gain_compare`) both the RF-disable writes and `close()` failed after the pump had been ON, so it may still be ON (the script prints a warning). `false` is logged only once every disable write or `close()` succeeded. Rerun `set_pump` (or `set_pump --on`) to put the pump in a known state |
| `pnax` | PNA-X address and sweep settings; null from `set_bias` and `set_pump` |
| others | `data_file`, `completed_repeats` / `completed_points`, `target_uA` where they apply |

It is the only record of the pump state: the SynthHD cannot be queried without connecting, and
connecting switches RF off. A failed write (network drive down) prints a warning; it never stops
a script. QICK sessions do not read it yet (no `twpa_*` keys in the experiment cfg).

## Analysis

- **flux_sweep.**
  - Expected: transmission enhancement near ~11 µA (operating point) and strong
    suppression near ~25 µA (end of the first flux period).
  - **Diagnostic:** if band-mean |S21| vs current is flat (spread < 0.5 dB), the
    **DC line is open** or the device is not flux-responsive.
- **pump_sweep.**
  - The best point is the largest band-mean gain (`gain_band_dB`); the script also prints the
    band-min gain, the ripple and the ON / OFF band-mean |S21| there. CW mode: one signal
    point, so ripple = 0.
  - The OFF reference is retaken every row (~90 s at the committed grid), so drift slower than a
    row cancels in the gain. Drift within a row does not. Before this change the map was
    absolute ON |S21| with no reference, so a 10 h drift was indistinguishable from gain.
- **gain_compare.**
  - OFF and ON traces are interleaved every repeat, so slow thermal and cable drift
    cancels in the difference.
  - A good operating point shows broadband positive gain, often ~15–20 dB, with
    modest ripple.
  - **Diagnostic:** band-mean gain < 1 dB means the pump is off-optimum,
    under-powered, or not reaching the TWPA.
- **PNA-X power** stays low (−25 dBm), so the signal does not saturate the TWPA, which
  may be unbiased or under-pumped during sweeps. It was previously −20 dBm in the pump
  sweep.

## Findings & notes

- **Wiring.** The YOKO sources current directly into the bias port. An earlier
  voltage-mode + series-resistor scheme was dropped because the resistor value was
  unreliable. A setup that drives the TWPA through a known series resistor in voltage mode
  would need a V↔I conversion reintroduced; the scripts assume the YOKO sources current
  directly.
- **Bias history.**
  - Optimum from flux sweep `20260521_144734`: maximum |S21| on a broad 3.5–5.5 µA
    plateau.
  - "18 (10/7/26)" is noted next to the target, i.e. 18 µA on 2026-10-07. That is
    above the ~11 µA guidance.
  - The committed target is 0.
- **Pump operating-point history.**
  - Current: ch1 10.7165 GHz / −5.5 dBm.
  - Earlier: ch0 10.7831 GHz / −1.0 dBm.
  - Earlier ON point in gain_compare: 10.9187 GHz / −18 dBm.
- **SynthHD behaviour** (verified against the installed `pywindfreak`):
  - Connecting disables RF on **both** channels.
  - `close()` also disables RF on both, so `set_pump` deliberately does not close the
    port, to leave the pump on.
- The PNA-X sweep time is ≈ n_points/IF_BW per sweep × n_avg. A fixed 30 s VISA
  timeout was exceeded at low IF BW with many averages; this is why the pump-sweep
  timeout is estimated.
- `pump_sweep` wall-clock model (printed before the run): per sweep = n_freq / IF_BW
  (per-point dwell ~ 1/IF_BW); per measure = per sweep × N_avg; per point = per measure +
  power settle; per row add one pump-OFF reference (per measure + freq settle); total =
  n_total × per point + N_FREQ_POINTS × (per measure + 2 × freq settle). It excludes
  VISA/transfer/save overhead.
- At the committed grid, `pump_sweep` is 401 × 21 = 8421 points at ~4.25 s each ≈ 10 h, plus
  401 pump-OFF references (~4.4 s each, ≈ 29 min, ~5 %).
- Saving once per row instead of after every point cuts the network-drive writes from
  8421 × 2.8 MB ≈ 24 GB to 401 × ~3 MB ≈ 1.2 GB.

## Known issues

- The legacy `set_pump` comments said that channels not listed "are left untouched". In fact,
  connecting disables RF on both channels, so setting ch1 switches ch0 off.
- `DISABLE_PUMP = True` is committed. Running `set_pump` without `--on` only turns
  the pump off.
- Leaving the pump on (`set_pump`, a completed `gain_compare`) relies on the interpreter exit
  not calling `SynthHD.close()` (which disables RF). Not re-checked against `pywindfreak`, which
  is not installed on the development PC; check the pump after the first such run on a new
  install.
- `set_bias`: the safety cap (25 µA) equals the hard limit, so the
  `ALLOW_CALIBRATION` branch is unreachable, and the "do not exceed ~11 µA" guidance is
  **not enforced**.
- Stale legacy text (removed from the code in the 2026-10 cleanup, kept here for the record):
  - the `flux_sweep` docstring referred to a "12 µA safety cap" that does not exist;
  - it said "0 → ~25 µA, 0.5 µA spacing", but the configured grid is −25 → +25 µA at
    1.0 µA;
  - `pump_sweep` comments described a 12.0–13.5 GHz, −25 → 0 dBm grid ("25 MHz spacing across
    12.0–13.5 GHz (centered on ~12.7 GHz)", "0.5 dB spacing across -25 → 0 dBm"). The configured
    grid is 10.70–10.73 GHz and −10 → 0 dBm.
- The `set_bias` and `flux_sweep` confirmation prompts still name a Holzworth HS9004A as the
  pump generator. The pump is a Windfreak SynthHD.
- `flux_sweep`, `pump_sweep` and `gain_compare` open the PNA-X (and the YOKO) outside
  the `try` block. If the SynthHD connection fails, the PNA-X is left open.
- `flux_sweep` uses a fixed VISA timeout. Raising the averages or points, or lowering
  the IF BW, can time out.
- History: the old `YOKOGS200.SetCurrent` driver (not used by these scripts, and not
  carried into qicklab) stepped 100 µA at a time with no rate limit. Never drive the
  TWPA line with a generic YOKO ramp.
