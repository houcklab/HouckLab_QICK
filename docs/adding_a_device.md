# Adding a device

One chip in one cooldown is one file, `devices/<NAME>.py`, holding a single `DEVICE` object.
Switching chips never touches experiment, run or recipe code. This page walks through creating
that file, keeping it current during a cooldown, and archiving it afterwards. For the
measurement order on a fresh chip see [bringup_workflow.md](bringup_workflow.md); for an example
record see [devices/CSTQ03.md](devices/CSTQ03.md).

> Status (2026-10-13): the `Device` dataclasses are part of the phase-5 session layer from the
> refactor design. Field names below follow that design.

## 1. Copy the template

```
copy devices\_template.py devices\CSTQ04.py
```

The file name is the device name. Sessions import it directly
(`from devices.CSTQ04 import DEVICE`) or by name (`from devices import load_device;
DEVICE = load_device("CSTQ04")`).

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
| `setup` | `Setup` | instrument endpoints and board overrides |
| `cavity_min` | bool | `True` if the resonator is a dip in transmission; `transmission_sweep` and the charge transmission sweep then track the minimum, otherwise the maximum |
| `readout_window` | `ReadoutWindow` | default window for regime-A steps (transmission, spec, Rabi, T1/T2/T2E, charge dispersion, Modified Ramsey, active-reset verify). Default 15 us / 0.3 us |
| `ss_window` | `ReadoutWindow` | default window for the single-shot family (single shot, undriven, T1 single-shot, readout/qubit optimise, AutoCoherence). Default 15 us / 0.3 us. Zero-span parity sets its own `read_length` |

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
| `pi2_gain` | DAC units | pi/2 gain; `None` means `gain // 2`. Set it explicitly once calibrated (qubit optimise with two pulses) |
| `flattop_length` | us | flat segment of a flat-top pulse; `None` for plain Gaussian. Flat-top gains do not transfer to a Gaussian envelope |
| `spec_gain` | DAC units | spectroscopy drive gain that shows this qubit well; `None` uses the `spec` group's value |
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
| `kappa_mhz` | MHz (kappa/2pi) | resonator linewidth; sets the minimum `reset_readout_relax_delay` (about 6/kappa) for active reset |

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
| `twpa` | `None` | `TwpaSetup(yoko_addr, synth_port, pnax_addr, pump=(freq_GHz, power_dBm, channel), bias_ua)`, shared by the TWPA scripts |

CSTQ03 runs with readouts at 6.8-7.6 GHz in `nqz` 2 and qubits at 2.5-4.2 GHz in `qubit_nqz` 1
(the `BASE_CONFIG` values).

## 3. Validate

```python
from devices.CSTQ04 import DEVICE
DEVICE.validate()
```

`validate()` checks: qubit keys are 1..N; every gain is within 0..32767; `pi2_gain <= gain`;
each frequency lies in the band of its Nyquist zone. It raises on the first problem. Then do a
dry run of a short plan before the cooldown session (no hardware needed):

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

### Calibration write-back

Steps that measure a device value (`transmission_fit` for the resonator frequency,
`amplitude_rabi` for the pi gain, `readout_optimize`, `qubit_optimize`, `auto_coherence`,
zero-span recalibration) call `qicklab.core.io.record_calibration(device, q, **values)`. It:

1. appends one JSON line to `<data_root>/Q<q>/calibrations.jsonl` with the step, the time and the
   values, and
2. prints a paste-ready `Qubit(...)` line with the new values filled in.

Nothing rewrites the device file automatically. Review the printed line, paste it into
`devices/<NAME>.py`, and commit. `calibrations.jsonl` is the audit trail of every calibration in
the cooldown, including the ones you did not adopt.

Zero-span parity keeps its calibration cache (parity peak frequencies, g/e separator) in
`<data_root>/Q<q>/zsp_cache.json`, read and written by the step.

## 5. End of cooldown: archive

Before editing the file for a new cooldown of the same chip:

```
copy devices\CSTQ04.py devices\archive\CSTQ04_2026-12-01.py
```

then change `cooldown`, `data_root` and the qubit values in `devices/CSTQ04.py`. Archive files are
never deleted and never imported by sessions; they are the record of what each cooldown used.
CSTQ03's earlier "v2b nu cell" table lives in `devices/archive/CSTQ03_v2b.py`.

Also update `docs/devices/<NAME>.md`: move the old parameter table to an "Archived" section and
start the new cooldown's table.

## Checklist

- [ ] `devices/<NAME>.py` created from `_template.py`; `name`, `cooldown`, `data_root` set
- [ ] every qubit: freq, gain, sigma, readout freq and gain (design values are fine to start)
- [ ] `cavity_min` matches what transmission shows
- [ ] `board_overrides` if Nyquist zones or wiring differ from `BASE_CONFIG`
- [ ] `setup.twpa` if the TWPA scripts will be used
- [ ] `DEVICE.validate()` passes; a dry run of one plan passes
- [ ] previous cooldown archived under `devices/archive/`
- [ ] `docs/devices/<NAME>.md` started
