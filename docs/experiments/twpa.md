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

Shared PNA-X and SynthHD helpers live in `qicklab.hardware.pnax`,
`qicklab.hardware.synthhd` and `qicklab.hardware.yoko`. Instrument addresses and the
pump operating point come from the device's `Setup.twpa` (`TwpaSetup(yoko_addr,
synth_port, pnax_addr, pump=(ghz, dbm, ch), bias_ua)`). See [hardware](../hardware.md).

## Pulse sequence

There is no pulse sequence. The bring-up order is:

```
pump OFF ──▶ set_bias (0 → target, ≤ 300 nA/s) ──▶ set_pump (freq, power, RF on) ──▶ gain_compare
                 ▲                                       ▲
         flux_sweep (pump OFF, calibration only)   pump_sweep (finds freq, power)
```

1. Bias first, with the pump disabled, sweeping slowly from 0. Then pump.
2. `flux_sweep` ends by ramping the bias back to 0.
3. `pump_sweep` and `gain_compare` disable the pump RF on exit (success, exception or
   Ctrl-C).

## How to run

Each script prints its plan and requires typing `yes` before it touches hardware.

```
python -m qicklab.twpa.set_bias
python -m qicklab.twpa.set_pump          # --off to RF-disable and exit
python -m qicklab.twpa.flux_sweep
python -m qicklab.twpa.pump_sweep
python -m qicklab.twpa.gain_compare
```

## Parameters

**Datasheet limits and safety.**

| Quantity | Value | Meaning |
|---|---|---|
| Max bias sweep rate | 300 nA/s | Datasheet ceiling. Faster risks flux trapping. Do not raise. |
| Nominal operating point | ~11 µA | ≈ 15 µT internal field, impedance matched. |
| End of first flux period | ~25 µA | One-off flux calibration only. |
| Normal-operation guidance | do not sweep well above ~11 µA | Higher currents may reduce performance or trap flux. |
| Bias hard limit in `set_bias` | 25 µA | Targets above it raise. |
| Bias step period | 0.05 s | GPIB update interval while ramping. |
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
  unreliable.
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
- At the committed grid, `pump_sweep` is 401 × 21 = 8421 points at ~4.25 s each ≈ 10 h.

## Known issues

- `set_pump` documents that channels not listed "are left untouched". In fact,
  connecting disables RF on both channels, so setting ch1 switches ch0 off.
- `DISABLE_PUMP = True` is committed. Running `set_pump` without editing it only turns
  the pump off.
- `set_bias`: the safety cap (25 µA) equals the hard limit, so the
  `ALLOW_CALIBRATION` branch is unreachable, and the "do not exceed ~11 µA" guidance is
  **not enforced**.
- `flux_sweep` docstring errors:
  - it refers to a "12 µA safety cap" that does not exist;
  - it says "0 → ~25 µA, 0.5 µA spacing", but the configured grid is −25 → +25 µA at
    1.0 µA.
- `pump_sweep` comments describe a 12.0–13.5 GHz, −25 → 0 dBm grid. The configured grid
  is 10.70–10.73 GHz and −10 → 0 dBm.
- Several docstrings name a Holzworth HS9004A as the pump. The pump is a Windfreak
  SynthHD.
- `set_bias` issues `:SOUR:FUNC CURR` without checking the YOKO's current mode or
  output state.
- `flux_sweep`, `pump_sweep` and `gain_compare` open the PNA-X (and the YOKO) outside
  the `try` block. If the SynthHD connection fails, the PNA-X is left open.
- `flux_sweep` uses a fixed VISA timeout. Raising the averages or points, or lowering
  the IF BW, can time out.
- History: the old `YOKOGS200.SetCurrent` driver (not used by these scripts, and not
  carried into qicklab) stepped 100 µA at a time with no rate limit. Never drive the
  TWPA line with a generic YOKO ramp.
