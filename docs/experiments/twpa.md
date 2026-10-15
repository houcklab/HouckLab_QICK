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
| `qicklab.twpa.pump_sweep` | 2-D pump (frequency × power) grid at fixed bias; band-mean \|S21\| per point. |
| `qicklab.twpa.gain_compare` | \|S21\| pump OFF vs ON across the signal band, interleaved; gain = ON − OFF (dB). |

`set_bias` and `set_pump` are measurement-free: map |S21| vs bias with `flux_sweep` (or a
separate transmission run, e.g. `CavitySpecFF`), and find the pump point with `pump_sweep`;
then park there with `set_bias` / `set_pump` before running qubit measurements.

Shared helpers: `qicklab.hardware.pnax` (`measure_s21_band`, `band_mean_dB`),
`qicklab.hardware.synthhd` (`SynthHD`, `set_pump_channels`), `qicklab.hardware.yoko`
(`pick_current_range`, `enable_current_output_safely`, `ramp_current`, default step period
`STEP_PERIOD_S`, the bias address `TWPA_YOKO_ADDRESS`) and `qicklab.twpa.common`
(`timestamped_paths`). The other instrument addresses (`PNAX_ADDRESS`, `PUMP_SYNTH_PORT`)
and the pump operating point are module-level constants in each script for now. A per-device
`Setup.twpa` (`TwpaSetup(yoko_addr, synth_port, pnax_addr, pump=(ghz, dbm, ch), bias_ua)`) is
planned but not yet in code (phase 5). When it lands, the charge-yoko refusal in
`open_charge_yoko` must also check the device's `twpa.yoko_addr`: today it compares only against
`TWPA_YOKO_ADDRESS`. See [hardware](../hardware.md).

## Pulse sequence

There is no pulse sequence. The bring-up order is:

```
pump OFF ──▶ set_bias (0 → target, ≤ 300 nA/s) ──▶ set_pump (freq, power, RF on) ──▶ gain_compare
                 ▲                                       ▲
         flux_sweep (pump OFF, calibration only)   pump_sweep (finds freq, power)
```

1. Bias first, with the pump disabled, sweeping slowly from 0. Then pump.
   Before any ramp, `set_bias` and `flux_sweep` run `enable_current_output_safely`: it queries
   `:OUTP?`, `:SOUR:FUNC?` and `:SOUR:LEV?` and prints them. Output off: `:SOUR:FUNC CURR`,
   `:SOUR:RANG <range>`, `:SOUR:LEV 0`, `:OUTP ON` (the ramp starts from 0; a stale stored
   setpoint is discarded, never applied as a step). Output on in current mode: the setpoint is
   kept and the ramp starts from it (`:SOUR:RANG?` is read; the range is changed only at 0 A).
   Output on in voltage mode: the script stops without writing. Details:
   [hardware](../hardware.md#bias-gs200-at-gpib1112instr-current-mode).
2. `flux_sweep` ends by ramping the bias back to 0 (only once the YOKO is in current mode with
   its output on).
3. `pump_sweep` and `gain_compare` disable the pump RF on exit (success, exception or
   Ctrl-C).

## How to run

Each script is configured by the UPPERCASE constants at the top of its module, prints its plan
and requires typing `yes` before it touches hardware.

```
python -m qicklab.twpa.set_bias
python -m qicklab.twpa.set_pump          # --off to RF-disable and exit
python -m qicklab.twpa.flux_sweep
python -m qicklab.twpa.pump_sweep
python -m qicklab.twpa.gain_compare
```

- **set_bias.** Verify the pump RF output is OFF, set `TARGET_CURRENT_uA`, run. The address
  is `TWPA_YOKO_ADDRESS` in `qicklab.hardware.yoko` (shared with the charge-line opener, which
  refuses it). `YOKO_CURR_RANGE_A = None` auto-picks the range; a number forces it.
- **set_pump.** Verify the DC bias is parked (`set_bias`); the script does not touch the YOKO.
  Set `PUMP_SYNTH_PORT` and `PUMP_SETTINGS`: each listed channel gets its **own**
  (freq_GHz, power_dBm); give both channels the same pair to drive them identically, different
  pairs to drive them independently. To turn the pump off, set `DISABLE_PUMP = True` or pass
  `--off`.
- **flux_sweep.** `PNAX_MEAS_MODE` picks the figure of merit: `"BAND"` sweeps
  [`PNAX_F_START_HZ`, `PNAX_F_STOP_HZ`] and uses the mean |S21| (dB) over the band; `"CW"` parks
  on `PNAX_CW_FREQ_HZ` and uses |S21| (dB) at that one tone (faster, no band averaging). The ramp
  rate is enforced ≤ 300 nA/s by `ramp_current`; on exit (success, exception or Ctrl-C) the bias
  is ramped back to 0. Do not use it for daily operation: set the operating point with
  `set_bias` afterwards.
- **pump_sweep.** Same `PNAX_MEAS_MODE` choice. The channels in `PUMP_CHANNELS` are driven
  **identically** (same frequency and power at every point); for offset or independent control,
  add fixed offsets where the channels are programmed inside the loop. Bias must already be
  parked; the script does not touch the YOKO.
- **gain_compare.** Set `PUMP_ON_FREQ_GHz` / `PUMP_ON_POWER_dBm` to the `pump_sweep` optimum for
  the signal band. "Pump OFF" disables RF on every listed channel; "pump ON" programs the ON
  point and enables RF. Bias must already be parked.
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

**Instruments.**

| Item | Value |
|---|---|
| TWPA bias YOKO | `GPIB1::12::INSTR`, current-source mode, connected directly to the TWPA bias port. This is not the charge-line YOKO at `GPIB1::9`. |
| Pump | Windfreak SynthHD on `COM5`, locked to the external 10 MHz reference on connect. |
| PNA-X | `GPIB0::16::INSTR`, Keysight N52xx SCPI. |
| Output | `<SAVE_DIR>/<%Y%m%d_%H%M%S>_<RUN_TAG>.npz/.png`, saved incrementally after each point. CSTQ03 2026-10-01 cooldown: `V:/t1Team/Data/2026-10-01_BFC_cooldown/TWPA_calibration`. |

**Per-script settings** (legacy constants, CSTQ03 values).

| Script | Setting | Value |
|---|---|---|
| set_bias | `TARGET_CURRENT_uA` | 0 (committed). See findings for history. |
| set_pump | `PUMP_SETTINGS` | ch1: 10.7165 GHz, −5.5 dBm |
| set_pump | `DISABLE_PUMP` | True (committed): running it only turns the pump off |
| flux_sweep | bias grid | −25 → +25 µA, 51 points (1.0 µA spacing), 0.5 s settle |
| flux_sweep | PNA-X | BAND 5–8 GHz, 201 points, IF BW 100 Hz, −25 dBm, 4 averages, 30 s timeout (CW mode: 7 GHz) |
| pump_sweep | grid | 10.70–10.73 GHz × 401 points, −10 → 0 dBm × 21 points; settle 0.20 s (freq) / 0.05 s (power) |
| pump_sweep | PNA-X | BAND 6–8 GHz, 21 points, IF BW 500 Hz, −25 dBm, 100 averages |
| pump_sweep | VISA timeout | 3 × (n_points / IF_BW × n_avg) + 5 s, floor 30 s |
| gain_compare | pump ON | 10.7165 GHz, −5.5 dBm, channel [1] |
| gain_compare | band | 2–10 GHz, 401 points, IF BW 1000 Hz, −25 dBm, 60 s timeout |
| gain_compare | repeats | 10 OFF/ON pairs, 0.30 s settle after each pump toggle |

## Outputs

- **flux_sweep:** npz/png of band-mean |S21| (dB) vs bias, and the bias that
  maximises it. Pump OFF, so this is bare transmission, not gain.
- **pump_sweep:** npz/png map of band-mean |S21| vs (frequency, power), and the best
  point. This is transmission, not gain: for absolute gain, subtract an unpumped
  reference offline.
- **gain_compare:** npz/png of |S21|_off(f), |S21|_on(f), and gain(f) = on − off
  (dB), averaged over the repeats.
- set_bias and set_pump write nothing.

## Analysis

- **flux_sweep.**
  - Expected: transmission enhancement near ~11 µA (operating point) and strong
    suppression near ~25 µA (end of the first flux period).
  - **Diagnostic:** if band-mean |S21| vs current is flat (spread < 0.5 dB), the
    **DC line is open** or the device is not flux-responsive.
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
  power settle; total = n_total × per point + N_FREQ_POINTS × freq settle. It excludes
  VISA/transfer/save overhead.
- At the committed grid, `pump_sweep` is 401 × 21 = 8421 points at ~4.25 s each ≈ 10 h.

## Known issues

- The legacy `set_pump` comments said that channels not listed "are left untouched". In fact,
  connecting disables RF on both channels, so setting ch1 switches ch0 off.
- `DISABLE_PUMP = True` is committed. Running `set_pump` without editing it only turns
  the pump off.
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
