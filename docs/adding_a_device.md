# Adding a device

One chip in one cooldown is one file, `devices/<NAME>.py`, holding a single `DEVICE` object.
Switching chips never touches experiment, run or recipe code. This page walks through creating
that file, keeping it current during a cooldown, and archiving it afterwards. For the
measurement order on a fresh chip see [bringup_workflow.md](bringup_workflow.md); for an example
record see [devices/CSTQ03.md](devices/CSTQ03.md).

> Status (2026-10-17): the dataclasses live in `qicklab/core/device.py`, the CSTQ03 file in
> `devices/CSTQ03.py`, the session layer (`Session`, `run`, dry run) in
> `qicklab/core/session.py` and `record_calibration` in `qicklab/core/io.py`. `connect()` feeds
> `DEVICE.legacy_parameters()` to the legacy `build_context`.

## 1. Copy an existing device file

```
copy devices\CSTQ03.py devices\CSTQ04.py
```

The file name is the device name. Sessions import it directly: `from devices.CSTQ04 import DEVICE`.
A device file imports only `qicklab.core.device` (enforced by `tests/test_layering.py`); it is
data, not code.

## 2. Fill in the fields

```python
"""CSTQ04, 2026-12-01 cooldown."""
from qicklab.core.device import (
    Device, ParityParams, Qubit, Readout, ReadoutWindow, Setup, TwpaSetup,
)

DEVICE = Device(
    name="CSTQ04",
    cooldown="2026-12-01",
    data_root="V:/t1Team/Data/2026-12-01_BFC_cooldown/CSTQ04/RFSOC",
    cavity_min=True,                                   # resonator shows as a dip
    readout_window=ReadoutWindow(length_us=15, adc_offset_us=0.3),
    ss_window=ReadoutWindow(length_us=15, adc_offset_us=0.3),
    setup=Setup(
        rfsoc_host="192.168.0.103", rfsoc_port=8888, rfsoc_name="myqick",
        yoko_addr="GPIB1::9::INSTR",
        board_overrides={},                            # e.g. {"nqz": 2, "qubit_nqz": 1}
        twpa=TwpaSetup(yoko_addr="GPIB1::12::INSTR", synth_port="COM5",
                       pnax_addr="GPIB0::16::INSTR", pump=(10.7165, -5.5, 1), bias_ua=0.0),
    ),
    qubits={
        1: Qubit(freq=2763.0, gain=5000, sigma=0.6,
                 readout=Readout(freq=6791.2, gain=1000)),
        2: Qubit(freq=3754.5, gain=3800, sigma=0.02,
                 readout=Readout(freq=7452.9, gain=4500,
                                 window=ReadoutWindow(5, 0.3)),   # per-qubit override
                 notes="readout coarse 4000, behaviour at 4500"),
        # ...
    },
)
```

(Numbers borrowed from CSTQ03 for illustration.)

### Device

| field | units | meaning |
|---|---|---|
| `name` | | chip name; matches the file name |
| `cooldown` | date `YYYY-MM-DD` | cooldown start; also used in the archive file name |
| `data_root` | path | root of all RFSoC data for this device and cooldown. Qubit `q` writes under `f"{data_root}/Q{q}//"` (the trailing `//` is deliberate, see [architecture.md](architecture.md#file-naming-must-stay-byte-identical)) |
| `qubits` | dict int -> `Qubit` | keys 1..N, contiguous |
| `setup` | `Setup` | instrument endpoints and board overrides (required; `Setup()` takes the lab defaults) |
| `cavity_min` | bool | `True` if the resonator is a dip in transmission; `transmission_sweep` and the charge transmission sweep then track the minimum, otherwise the maximum |
| `readout_window` | `ReadoutWindow` | default window for regime-A steps (transmission, spec, Rabi, T1/T2/T2E, charge dispersion, Modified Ramsey, active-reset verify). Default 15 us / 0.3 us |
| `ss_window` | `ReadoutWindow` | default window for the single-shot family (single shot, undriven, T1 single-shot, readout/qubit optimise, AutoCoherence). Default 15 us / 0.3 us. Zero-span parity sets its own `read_length` |

Methods: `folder(q)` is the qubit's data folder; `window(q, single_shot=False)` is the window
qubit `q` runs with (its `Readout.window` / `Readout.ss_window` override, else the device
default); `legacy_parameters()` returns a fresh dict in the old `Qubit_Parameters` shape (string
keys `"1".."N"`, `Readout`/`Qubit`/`outerfoldername`, values byte-for-byte as the legacy runner
wrote them), which `build_context` and AutoCoherence consume; `with_qubit` and `validate` are
below.

`ReadoutWindow(length_us, adc_offset_us)`: integration window and delay from tone start to ADC
trigger, both us. The resonator tone length is derived as `adc_offset_us + length_us`; never set
it separately. A longer window raises SNR per shot until it approaches T1, after which the
integration tail averages in decayed population.

### Qubit

| field | units | meaning |
|---|---|---|
| `freq` | MHz | qubit drive frequency (for a charge-sensitive qubit: the doublet centre or the single peak at the sweet spot) |
| `gain` | DAC units, 0..32767 | pi-pulse gain at this `sigma` |
| `sigma` | us | Gaussian sigma; the envelope is 4 sigma long |
| `readout` | `Readout` | readout resonator of this qubit |
| `pi2_gain` | DAC units | pi/2 gain; `None` means `gain // 2` (read it as `qubit.effective_pi2_gain`; a `with_qubit(q, gain=...)` trial re-derives it). Set it explicitly once calibrated (qubit optimise with two pulses) |
| `flattop_length` | us | flat segment of a flat-top pulse; `None` for plain Gaussian. Flat-top gains do not transfer to a Gaussian envelope |
| `spec_gain` | DAC units | spectroscopy drive gain that shows this qubit well: fills the `spec` group's `gain` when the session leaves it `None` (an explicit `G.spec(gain=...)` or a step's `gain=` still wins; the base-config `qubit_gain` is not affected); `None` uses the library 800 |
| `bias_v` | V | preferred charge-line bias for this qubit (e.g. a good T2R point) |
| `t1_us` | us | last measured T1; used to sanity-check relax delays (3-5 x T1) |
| `parity` | `ParityParams` or `None` | charge-parity calibration (below) |
| `notes` | str | one-line current status |

### Readout

| field | units | meaning |
|---|---|---|
| `freq` | MHz | readout tone frequency (`pulse_freq`); with `cavity_LO` = 0 this is the physical frequency |
| `gain` | DAC units | readout tone gain (`pulse_gain`) |
| `window` | `ReadoutWindow` or `None` | per-qubit regime-A window; `None` uses `Device.readout_window` |
| `ss_window` | `ReadoutWindow` or `None` | per-qubit single-shot window; `None` uses `Device.ss_window` |
| `kappa_mhz` | MHz (kappa/2pi) | resonator linewidth; sets the minimum `reset_readout_relax_delay` for active reset: about 6/kappa with the angular kappa = 2 pi x `kappa_mhz` (0.19 MHz gives 5 us) |

Per-qubit windows exist because the right integration time differs by qubit (CSTQ03 notes: Q2
readout length 5 us; single-shot Q1 15 us, Q5 5 us).

### ParityParams

Only for charge-sensitive qubits used in Modified Ramsey / zero-span work.

| field | units | meaning |
|---|---|---|
| `df_mhz` | MHz | measured splitting between the two parity branches; Modified Ramsey sets tau = k / (2 df) |
| `f_upper_mhz` | MHz | the upper parity branch, not the doublet centre. Required when `symmetric_ramsey=True` (the recipe raises otherwise) |
| `cd_max_mhz` | MHz | peak charge dispersion from a charge sweep fit, S(V) = cd_max * \|cos(2 pi (V - V0) / T)\| |
| `cd_period_mv` | mV of yoko voltage | period T of that fit |
| `p_e_state0`, `p_e_state1` | probability | Ramsey mapping P(e \| parity state); defaults 0.1 / 0.9 are assumed, not measured |
| `calibrated` | bool | set `True` only once the mapping probabilities come from a device-specific calibration |

### Setup

| field | default | meaning |
|---|---|---|
| `rfsoc_host`, `rfsoc_port`, `rfsoc_name` | `192.168.0.103`, 8888, `myqick` | Pyro4 nameserver and QICK server name |
| `yoko_addr` | `GPIB1::9::INSTR` | charge-line yoko (voltage mode) |
| `board_overrides` | `{}` | merged over `BASE_CONFIG`: `nqz` (readout DAC Nyquist zone), `qubit_nqz`, `cavity_winding_freq/offset`, `trig_buffer_start/end`, `trig_delay`. Use this instead of editing the library when a chip sits in another Nyquist zone or the fridge is rewired |
| `ff_qubits` | `None` | fast-flux channel map (`{q: {"channel": ch, "delay_time": us}}`); persisted in the cfg, not read by current experiments |
| `twpa` | `None` | `TwpaSetup(yoko_addr, synth_port, pnax_addr, pump=(freq_GHz, power_dBm, channel), bias_ua)`, all required; the record of the TWPA instruments (the `qicklab.twpa` scripts still carry their own constants) |

`setup.board_config()` returns a fresh `BASE_CONFIG` copy with `board_overrides` applied.

CSTQ03 runs with readouts at 6.8-7.6 GHz in `nqz` 2 and qubits at 2.5-4.2 GHz in `qubit_nqz` 1
(the `BASE_CONFIG` values). At a DAC fs of 6881.28 MS/s Q2 and Q4 are then in Nyquist zone 2 at
`qubit_nqz` 1, which `validate` reports (below). That fs is the regression harness's board variant
A, implied by the 430.08 MHz fabric clock the runs assume; it has not been read from a soccfg dump
of the lab board, so run `validate(soc_cfg)` on the real board to confirm.

## 3. Validate

```python
from devices.CSTQ04 import DEVICE
DEVICE.validate()          # field checks only (warns that the zone check was skipped)
DEVICE.validate(soccfg)    # plus the Nyquist-zone / image check against the board
```

`validate(soccfg=None, *, image_tol_mhz=20.0, coincide_tol_mhz=2.0)` raises one `ValueError`
listing every hard error, emits a `UserWarning` per soft problem, and returns the zone report (one
line per tone; empty without `soccfg`).

Hard errors: qubit keys are not the ints 1..N; a gain (`gain`, `pi2_gain`, `readout.gain`,
`spec_gain`) that is not an integer in 0..32767 (DAC gains are register values: write `4200`,
not `4200.0` or a fitted `4200.5`); `pi2_gain > gain`; a non-positive frequency or `sigma`; a negative
`flattop_length`; a window with `length_us <= 0` or `adc_offset_us < 0`; `kappa_mhz <= 0`;
`parity.df_mhz` or `f_upper_mhz <= 0` or a mapping probability outside 0..1; a `board_overrides`
key that is not in `BASE_CONFIG`; `nqz` / `qubit_nqz` not 1 or 2. With `soccfg`: a tone at or above
2 fs, or within `coincide_tol_mhz` of a multiple of fs/2 (tone and image coincide).

Warnings: an explicit `pi2_gain` on a Gaussian pulse with `pi2_gain / gain` more than 0.1 from 0.5
(CSTQ03 Q1 and Q3: `3975 // 2` against 5000); `parity.f_upper_mhz` further than
max(`df_mhz`, `cd_max_mhz`) + 1 MHz from `freq` (wrong qubit or stale value). With `soccfg`, per
readout (gen `res_ch`, `nqz`) and qubit tone (gen `qubit_ch`, `qubit_nqz`), with
zone = floor(f / (fs/2)) + 1 and fs = `soccfg["gens"][ch]["fs"]`: a tone outside zone 1 at nqz 1 (its first-zone image is
the stronger output), a tone outside zones 2-3 at nqz 2; and every DAC image k fs +/- (f mod fs)
below 2 fs that lands within `image_tol_mhz` of another device frequency (CSTQ03 at harness variant A's fs:
the Q4 drive's image at 2764.28 MHz is 1.28 MHz from Q1, and Q1's at 4118.28 MHz is 1.28 MHz from
Q4). Zone 3 at nqz 2 is normal mix-mode operation and only appears in the report.

Then do a dry run of a short plan before the cooldown session (no hardware needed):

```python
from qicklab.core.session import Session, run
from qicklab.runs import recipes as R

run(Session(DEVICE, qubit_readout=1, qubit_pulse=1), [R.transmission_fit(), R.t1()], dry_run=True)
```

## 4. Day-to-day edits during a cooldown

The device file is the lab notebook's source of numbers. Keep a short dated note next to a value
when you change it, in the file itself (device files are exempt from the "no measured values in
comments" rule):

```python
4: Qubit(freq=4117.0, gain=4900, sigma=0.02,    # YYYY-MM-DD: pi 4900 (was <old>), Rabi at sigma 0.02
         readout=Readout(freq=7593.0, gain=4000)),
```

Long narrative (root-cause analyses, diagnostic tables) goes in `docs/devices/<NAME>.md`.

### Trying a value without editing the file

```python
SESSION = Session(DEVICE.with_qubit(4, gain=4800, sigma=0.025), qubit_readout=4, qubit_pulse=4)
```

`with_qubit(q, **changes)` returns a new `Device` with that qubit's fields replaced
(`dataclasses.replace`); the tracked file is untouched. Use it for a trial, then write the winner
into the file.

The objects are frozen: assigning a field raises `FrozenInstanceError`, and the dict fields
(`qubits`, `setup.board_overrides`, `setup.ff_qubits`) are stored as read-only copies, so
`DEVICE.qubits[4] = ...` raises `TypeError` instead of changing the device for every later import.
Values nested inside those dicts (an `ff_qubits` entry) are not frozen; pass `dict(...)` copies
when a consumer needs a plain or JSON-serialisable dict.

### Calibration write-back

`qicklab.core.io.record_calibration(device, q, step=None, **values)` records a measured device
value. It:

1. appends one JSON line to `<data_root>/Q<q>/calibrations.jsonl` with the device, cooldown,
   qubit, step, time and values, and
2. prints a paste-ready `Qubit(...)` line with the new values filled in (fields at their
   default are left out), and returns that `Qubit`.

The keywords are `Qubit` field names (`freq`, `gain`, `pi2_gain`, `sigma`, `flattop_length`,
`spec_gain`, `bias_v`, `t1_us`), `readout_freq` / `readout_gain` / `readout_kappa_mhz`, and
`parity_<field>` for `ParityParams` (`parity_f_upper_mhz`, `parity_df_mhz`, ...). Any other
keyword raises `TypeError` before anything is written. A qubit without `ParityParams` gets one
in the printed line only when both `parity_df_mhz` and `parity_f_upper_mhz` are given. A failed
write (data drive offline) is printed, not raised.

```python
from qicklab.core.io import record_calibration

record_calibration(DEVICE, 5, step="amplitude_rabi", gain=4300)
#   [calibration] CSTQ03 Q5 (amplitude_rabi): gain=4300 -> V:/.../RFSOC/Q5/calibrations.jsonl
#       5: Qubit(freq=2651, gain=4300, sigma=0.08, readout=Readout(freq=7095.4, gain=1500), notes='...'),
```

Today the session calls it for:

- a `transmission_fit` or `transmission_sweep` whose carry-over gate wrote a new `pulse_freq`:
  `readout_freq` of the readout qubit (skipped with a printed note when `cavity_LO` != 0,
  because `pulse_freq` is then an IF, not the absolute `Readout.freq`);
- a zero-span parity step that recalibrated the doublet (`parity_f_upper_mhz` = the higher line,
  `parity_df_mhz` = the splitting).

The other calibrating steps (`amplitude_rabi`, `readout_optimize`, `qubit_optimize`,
`auto_coherence`) do not call it yet: their run functions return nothing the session can record,
and changing that is a separate change. Call it yourself with the value the step printed.

Nothing rewrites the device file automatically. Review the printed line, paste it into
`devices/<NAME>.py`, and commit. `calibrations.jsonl` is the audit trail of every calibration in
the cooldown, including the ones you did not adopt.

Zero-span parity keeps its calibration cache (parity peak frequencies, g/e separator) in
`<data_root>/Q<q>/zsp_cache.json` (`q` = the pulse qubit). When a session runs the step, a
cache entry still `None` after the step's own values and `Qubit.parity` is filled from that
file (only if it was written for the same readout and pulse qubits), and after a successful run
the file is rewritten with the run's caches. The legacy `run_zero_span_parity(ctx, p)` call
itself never reads or writes it.

## 5. End of cooldown: archive

Before editing the file for a new cooldown of the same chip:

```
copy devices\CSTQ04.py devices\archive\CSTQ04_2026-12-01.py
```

then change `cooldown`, `data_root` and the qubit values in `devices/CSTQ04.py`. Archive files are
never deleted and never imported by sessions; they are the record of what each cooldown used
(`devices/archive/README.md`). CSTQ03's earlier "v2b nu cell" table moves to
`devices/archive/CSTQ03_v2b.py` in phase 5b (until then it is `Qubit_Parameters_v2b` in
`runners/CSTQ03_BFC.py`).

Also update `docs/devices/<NAME>.md`: move the old parameter table to an "Archived" section and
start the new cooldown's table.

## Checklist

- [ ] `devices/<NAME>.py` copied from an existing device file; `name`, `cooldown`, `data_root` set
- [ ] every qubit: freq, gain, sigma, readout freq and gain (design values are fine to start)
- [ ] `cavity_min` matches what transmission shows
- [ ] `board_overrides` if Nyquist zones or wiring differ from `BASE_CONFIG`
- [ ] `setup.twpa` if the TWPA scripts will be used
- [ ] `DEVICE.validate(soccfg)` raises nothing and its warnings are understood; a dry run of one plan passes
- [ ] `runners/<NAME>_session.py` copied from `runners/CSTQ03_session.py`: import the new `DEVICE`,
      set the qubits, bias and the `STEP` values ([running_a_session.md](running_a_session.md#the-cstq03-session-runner))
- [ ] previous cooldown archived under `devices/archive/`
- [ ] `docs/devices/<NAME>.md` started
