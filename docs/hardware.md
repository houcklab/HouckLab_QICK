# Hardware

The instruments qicklab talks to, how they are wired into the code, and the rules that protect
the fridge and the sample. Addresses and per-setup values live in `Device.setup`
(`qicklab.core.device.Setup`); the values below are the current lab setup (CSTQ03, 2026-10-01
cooldown).

| Instrument | Address | Driver (`qicklab.hardware.*`) | Used by |
|---|---|---|---|
| RFSoC running QICK | Pyro4 nameserver `192.168.0.103:8888`, server name `myqick` | `rfsoc.make_proxy` | every step |
| Legacy RFSoC boards | Pyro4 nameservers `192.168.1.10`, `192.168.1.11`, `192.168.1.12`, `192.168.1.119` (port 8888, `myqick`) | `rfsoc.make_proxy(host=...)` | no current step |
| Yokogawa GS200, charge bias | `GPIB1::9::INSTR`, voltage mode | `yoko` | `connect()`, charge sweeps, sweet-spot search |
| Yokogawa GS200, TWPA bias | `GPIB1::12::INSTR`, current mode | `yoko` (`ramp_current`) | `qicklab.twpa` scripts only |
| Windfreak SynthHD, TWPA pump | `COM5` | `synthhd` | `qicklab.twpa` scripts only |
| Keysight PNA-X | `GPIB0::16::INSTR` | `pnax` | TWPA calibration only |
| SignalCore SC5510A | Pyro5 nameserver, default host `192.168.0.102`, port 9090 | `sc5510a` | no current step |
| Vaunix LDA attenuator | `VNX_atten64.dll`, serial 27786 | `attenuator` | no current step |

## RFSoC

`make_proxy(host="192.168.0.103", port=8888, name="myqick")` locates the Pyro4 nameserver, prints
its full listing (on every connect), opens the `myqick` proxy and returns `(soc, soccfg)`; `soccfg`
is a `QickConfig` built from `soc.get_cfg()`. It sets the Pyro4 serializer to pickle (protocol 4)
globally. Nothing connects at import time; `connect(session)` or `run()` does.

- Firmware: tProc v1. Client `qick` pinned at 0.2.334 (`pyproject.toml`); the regression golden
  records the version and fails on a mismatch. The board itself runs qick 0.2.367 (per the
  shot-buffer helper's notes).
- Clocks and buffer sizes: [timing and units](concepts/timing_and_units.md#clocks).
- Older boards: the legacy proxy module also had hard-coded helpers for `192.168.1.10`, `.11`,
  `.12` and `.119`; none was used, and they are gone (pass `host=` instead). Older documentation
  that names `192.168.1.7` is stale (the `.103` nameserver answered in the October 2026 audit).
- If `locateNS` fails you are not on the lab network or the board's nameserver is down.

### Channel map

From `qicklab.hardware.board.BASE_CONFIG` (override per device in `Setup.board_overrides`):

| Key | Value | Meaning |
|---|---|---|
| `res_ch` | 0 | readout DAC generator |
| `qubit_ch` | 1 | qubit drive DAC generator |
| `ro_chs` | [0] | ADC readout channel(s) |
| `nqz` | 2 | readout DAC Nyquist zone |
| `qubit_nqz` | 1 | qubit DAC Nyquist zone |
| `mixer_freq` | 0.0 MHz | readout DAC mixer (NCO) |
| `cavity_LO` | 0 Hz | external readout LO; 0 = none (an earlier value, 6.5e9, was left commented out in the legacy file) |
| `cavity_winding_freq`, `cavity_winding_offset` | 0, 0 | cable winding correction, off ([IQ conventions](concepts/iq_conventions.md#1-cable-winding-not-used-at-present)) |
| `trig_buffer_start`, `trig_buffer_end`, `trig_delay` | 0.02, 0.02, 0.082 us | pin-0 trigger timing, below |

Readout 0 maps to tProc input channel 0 (`soccfg["readouts"][0]["tproc_ch"] == 0`). Several
programs declare ADC channels `[0, 1]` regardless of `ro_chs` (see
[readout window](concepts/readout_window.md#known-issues)).

### Fast-flux channels

`FF_Qubits` maps fast-flux lines to generator channels and line delays. It is copied into every
config as metadata; **no active code reads it**, and no current step plays a fast-flux pulse
(the `FF` in class names is historical).

| FF qubit | Generator | `delay_time` (us) |
|---|---|---|
| 1 | 2 | 0.0215 (= 0.017 + 0.0045) |
| 2 | 4 | 0 |
| 3 | 5 | 0 |
| 4 | 6 | 0 |

This map has four entries while CSTQ03 has six qubits; it belongs to the setup, so it moves to
`Setup.ff_qubits`.

### Trigger pin 0 (PMOD)

Some programs raise tProc trigger pin 0 around every qubit pulse:

```
qubit pulse            |<--- 4 sigma (+ flattop_length) --->|
pin 0          |<-tbs->|<--------------------------------->|<-tbe->|
               start = pulse_t + trig_delay - trig_buffer_start
               width = trig_buffer_start + trig_buffer_end + 4 sigma (+ flattop_length)
```

`trig_delay` = 0.082 us compensates the latency between the trigger output and the DAC;
`trig_buffer_start` = `trig_buffer_end` = 0.02 us.

| Fires pin 0 | Does not |
|---|---|
| `AmplitudeRabiFF`, `AmplitudeRabiFF_N`, `T1FF`, `T2EMUX` (every pulse), `SingleShotProgram` (every pulse; so `single_shot`, `readout_optimize`, `qubit_optimize`, the apriori separator) | `CavitySpecFF`, `QubitSpecSliceFF`, `ChiShift`, `T2R`, `T1_SS`, `ChargeDispersion`, `ChargeDispersionQuasiCW`, `ModifiedRamsey`, `ActiveResetVerify`, `UndrivenSingleShot`, `ZeroSpanParity` |

What pin 0 drives in the current fridge wiring (an RF switch on the drive line, a scope trigger,
nothing) is not recorded in the code. If it gates the drive path, every experiment in the right
column plays its qubit pulses into a closed switch. Confirm on the bench before relying on either
behaviour.

## Charge-bias yoko

Yokogawa GS200 at `GPIB1::9::INSTR` in voltage mode, connected to the charge line.

- `connect()` opens it with `open_charge_yoko(rm, address, start_voltage)` and then ramps to the
  session `bias_v`. `run()` closes the VISA session in `finally`. Closing does not turn the output
  off: the source keeps holding the last level.
- Bring-up order (`open_charge_yoko`, `qicklab.hardware.yoko`), so the output is never stepped:
  1. Refuse the TWPA bias address (`yoko.TWPA_YOKO_ADDRESS`, `GPIB1::12::INSTR`) before opening.
     GPIB addresses are compared by (board, primary address), so `GPIB1::12` and
     `GPIB1::12::0::INSTR` are refused too. A VISA alias (e.g. from NI MAX) is not resolved.
  2. Query `:OUTP?` (0/1), `:SOUR:FUNC?` (`VOLT`/`CURR`) and `:SOUR:LEV?`, and print them.
  3. Function `CURR` with the output on: raise without writing anything (the address points at a
     source that is biasing something else, e.g. the TWPA).
  4. Output off: `:SOUR:FUNC VOLT`. Then (both cases) read `:SOUR:RANG?` and raise if the range
     is above 10 V (the 30 V range resolves only 1 mV, coarser than the read-back tolerance below,
     and the charge line never needs it) or if |`bias_v`| exceeds 1.2x the range (the GS200
     maximum; above it the setpoint would be clipped). The range is never changed here; set it on
     the instrument with the output off.
  5. Output off: `:SOUR:LEV 0`, then `:OUTP ON`, so a stale stored setpoint is never applied.
     Output already on in `VOLT`: the level is left alone and `ramp_to` ramps from it.
- Always ramp. `ramp_to(yoko, target, step=0.001, delay=0.01)` reads the current level and steps
  1 mV every 10 ms, then lands exactly on the target. The legacy GS200 driver noted that the ramp
  interval must not go below 0.001 s, or the fridge heats up (the MATLAB default it copied is 0.01 s).
- 10 V guard: `ramp_to` rejects |target| > 10 V on both signs, before writing anything.
- Read-back: after landing, `ramp_to` queries `:SOUR:LEV?` and raises if the level differs from the
  target by more than 1e-4 V (`LEVEL_READBACK_TOL_V`; the 10 V range resolves 100 uV), e.g. when
  the active range clipped the setpoint. On the 30 V range (1 mV resolution) a target that is not
  a whole mV would trip it, so `open_charge_yoko` refuses that range at bring-up; the error message
  names both causes.
- Never park the bias. An aborted sweep must not leave the bias at an arbitrary point: every later
  measurement would silently run at that charge offset, while the cfg still records the session
  value. `undriven_single_shot` (charge sweep) and `charge_transmission_sweep` return to the start
  bias in `finally` (also on Ctrl-C). Other steps that move the bias do not; see Known issues.
- `yoko_fixed=True` in the session holds the bias during a "charge sweep", which then just repeats
  two-tone spectroscopy over time.
- Read the actual level with `:SOUR:LEV?` (`yoko.read_voltage`) when in doubt.

## TWPA instruments

The TWPA is run by standalone scripts (`python -m qicklab.twpa.<script>`), not by steps. Each asks
for `yes` before touching hardware. Order: set the bias first (pump off), then the pump.

### Bias: GS200 at `GPIB1::12::INSTR`, current mode

A dedicated source, separate from the charge-bias yoko. It drives the TWPA bias port directly in
current mode; an earlier voltage-mode scheme with a series resistor was dropped because the
resistor value was unreliable.

- Ramp with the pump **off**, starting from 0.
- Maximum sweep rate 300 nA/s (TWPA datasheet; faster risks flux trapping). Do not raise it.
- Nominal operating point about 11 uA (about 15 uT internal field, impedance matched). The first
  flux period ends near 25 uA; go there only for a one-off flux calibration. Do not sweep well
  above about 11 uA in normal operation.
- GS200 current ranges are 1, 10, 100, 200 mA. A setpoint above the active range is silently
  clipped; `pick_current_range` chooses the range from the target.
- Bring-up order (`enable_current_output_safely(yoko, range_A)`, called by `set_bias` and
  `flux_sweep` before any ramp), so the output is never stepped:
  1. Query `:OUTP?`, `:SOUR:FUNC?` and `:SOUR:LEV?`, and print them (a stale setpoint is visible).
  2. Output off: `:SOUR:FUNC CURR`, `:SOUR:RANG <range_A>`, `:SOUR:LEV 0`, then `:OUTP ON`. The
     ramp starts from 0 A; the stored setpoint is discarded.
  3. Output on in `VOLT`: raise (switching function with the output on steps the output).
  4. Output on in `CURR`: keep the setpoint (it is the real output; the ramp starts there). Read
     `:SOUR:RANG?`; write `range_A` only if the level is 0 A. At a nonzero level a larger active
     range is kept, a smaller one raises (ramp to 0 first).
  `flux_sweep` ramps back to 0 in `finally` only if this step succeeded.
- `ramp_current(yoko, target_A, max_rate_A_per_s, dt=STEP_PERIOD_S)` steps linearly from the
  present `:SOUR:LEV?` every `dt` s (default `yoko.STEP_PERIOD_S` = 0.05 s; the twpa scripts pass
  `set_bias.STEP_PERIOD_S`, also 0.05 s); it assumes current-source mode.
- The script refuses targets above 25 uA.

### Pump: Windfreak SynthHD on `COM5`

- Connecting (`SynthHD.__init__`) disables RF on **both** channels and locks to the external
  10 MHz reference; `SynthHD.close()` disables RF on both as well. The set-pump script therefore
  deliberately leaves the port open to keep the pump on. Setting one channel switches the other
  off.
- Pump power ceiling 0 dBm in the set-pump and gain-compare scripts (the pump-sweep script uses
  20 dBm; inconsistent).

### PNA-X at `GPIB0::16::INSTR`

- Probe power -25 dBm so the signal does not saturate the TWPA (previously -20 dBm).
- Sweep time is about `n_points / IF_BW` per sweep times `n_avg`. A fixed 30 s VISA timeout was
  exceeded at low IF bandwidth with many averages; the pump sweep sizes its timeout as
  3 x estimate + 5 s with the configured timeout as a floor. The flux sweep still uses a fixed
  timeout.

TWPA results save as `<SAVE_DIR>/<YYYYmmdd_HHMMSS>_<RUN_TAG>.npz/.png` (not the
`ExperimentClass` layout). Operating points and bias history per cooldown: device pages.

## Attenuator (Vaunix LDA)

`set_attenuation(db, serial=27786, dll_dir=..., verbose=False)` drives the attenuator through
`VNX_atten64.dll`. Python 3.8 and later do not search `PATH` for DLLs, so the DLL directory must be
registered with `os.add_dll_directory` before the DLL loads; the driver does this from `dll_dir`.
The DLL is not in the repository. Attenuation is set in units of 0.05 dB. No current step uses
the attenuator. The legacy driver searched the current working directory at import time, silently
did nothing when the serial was not found, and raised `NameError` in verbose mode when the
readback was negative; the refactored driver raises instead.

## SignalCore SC5510A

Pyro5 client for remote SC5510A generators: `connect(name=None, host, port)` returns a proxy with
`.frequency` (Hz), `.power` (dBm), `.output`, `.clocked`. Host from the environment variable
`SC5510A_SERVER_HOST` (default `192.168.0.102`), nameserver port 9090, object prefix `SC5510A#`
(example id `10002D35`). The server PC must run `start_nameserver.py` and
`start_instrument_server.py` from `https://github.com/NPdL-SQTeam/sc5510a-py`. The default host
is read at import; changing the variable afterwards has no effect. Needs Pyro5 (the `signalcore`
extra in `pyproject.toml`). Typical use: `list_instruments()`, then `inst = connect("10002D35")`,
`inst.frequency = 6e9`, `inst.power = 10`, `inst.output = True`.

## Data paths

Every experiment writes three files with one timestamp:

    <outerFolder><path>/<path>_<YYYY_MM_DD>/<path>_<YYYY_MM_DD_HH_MM_SS>_data.h5   (+ .png, .json)

- `outerFolder` = `Device.folder(qubit_readout)` = `f"{data_root}/Q{q}//"`. `data_root` is set per
  device and cooldown, e.g. `V:/t1Team/Data/2026-10-01_BFC_cooldown/CSTQ03/RFSOC`.
- `outerFolder + path` is plain string concatenation, so the folder must end with `/`. The
  resulting mix of `/`, `//` and `\` is what is on disk; keep it (code compares these strings).
  Example: `V:/t1Team/Data/2026-10-01_BFC_cooldown/CSTQ03/RFSOC/Q1//TransmissionFF\TransmissionFF_2026_10_13\TransmissionFF_2026_10_13_14_03_22_data.h5`.
- `path` (`"T1"`, `"QubitSpecFF"`, `"SingleShot"`, ...) is fixed per step and unchanged by the
  refactor. Some experiments append a suffix to the h5 name (`_Q{n}` for T1 and the soft-sweep
  Rabi, `_n{num_pi_pulses}` for T2E).
- The h5 holds one float64 dataset per data key and the full cfg as a JSON string in
  `attrs["config"]`; the `.json` holds the same cfg. Load offline with h5py:
  `cfg = json.loads(f.attrs["config"])`.
- Scripts are intentionally not embedded in the h5 ("caused more trouble than convenience",
  Ge Yang, legacy comment).
- Calibration write-back: `<data_root>/Q{q}/calibrations.jsonl`; zero-span caches:
  `<data_root>/Q{q}/zsp_cache.json`.

## Known issues

- Steps that move the charge bias without restoring it: `auto_coherence` sweet-spot walk,
  `charge_sweep`, `two_tone_charge_dispersion_quasicw` (ramps even with `yoko_fixed`),
  `modified_ramsey_control` (via the sweet-spot search). Later steps run at the new bias while
  their cfg shows `current_voltage` = session bias.
- The legacy connect turned the yoko output on and ramped before validating the readout window;
  a validation error left the yoko open and on.
- `pick_current_range` / the TWPA bias script: the 25 uA safety cap equals the hard limit, so the
  `ALLOW_CALIBRATION` branch is unreachable, and the "about 11 uA" guidance is not enforced.
- The TWPA bias script and the flux sweep confirmation prompts still name a Holzworth HS9004A as
  the pump; the pump is the Windfreak SynthHD.
- The set-pump script is committed with `DISABLE_PUMP = True`: run unchanged, it only turns the
  pump off.
- TWPA sweeps open the PNA-X (and yoko) before the `try` block; a failure to connect the
  SynthHD leaves the PNA-X session open.
