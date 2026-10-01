# Flux_Files

Turn device calibration into **DC voltages** (set once, define the operating point) and **fast-flux gains** (pulsed, drive the dynamics) for the 8-qubit triangle-ladder, and push those voltages onto the Qblox SPI rack.

The calibration physics lives in [`Device_calib/`](Device_calib/DeviceModeling.md) (treat it as a black box — that folder has its own doc). This folder is the **operator-facing layer**: a handful of edit-the-top-then-run scripts, the JSON operating points they produce/consume, and one pointer file that ties them together.

---

## Run location (read this first)

All four scripts use **relative paths** (`open("PRESENT_CONFIG.json")`, `Voltage_jsons/...`) and import the calibration backend as `from Device_calib...`. So:

- **Run every script with the working directory set to `Flux_Files/`** (this folder). Running from anywhere else breaks both the file reads and the `Device_calib` import.
- **`SET_QBLOX_VOLTAGES.py` needs one more thing:** it imports the SPI driver as `from triangle_lattice_quench.PythonDrivers...`, an absolute package path. So the **repo root** (`...\HouckLab_QICK`, the parent of `WorkingProjects`) must be on `PYTHONPATH` *and* the CWD must still be `Flux_Files`.

---

## The pointer file: `PRESENT_CONFIG.json`

The shared config that the read-from-config scripts consult. Three fields:

| Field | Meaning |
|---|---|
| `DEVICE_PATH` | calibration JSON to load (e.g. `Device_calib/Device_jsons/8QV1.json`) |
| `VOLTAGES_PATH` | the voltages JSON treated as the **current DC operating point** |
| `currently_set_voltages` | free-text note only — **not** written automatically (see Known issues) |

`Calculate_FF_array.py` and `Modify_Qubit_Flux_Offsets.py` read `DEVICE_PATH`/`VOLTAGES_PATH` from here. `Generate_Voltages_Dict.py` and `SET_QBLOX_VOLTAGES.py` instead use their own hardcoded top-of-file path constants — so check both places when you change operating point.

---

## The scripts, in workflow order

Each is an "edit the constants at the top, then run" script. What you edit is called out below.

### 1. `Generate_Voltages_Dict.py` — design a DC operating point (offline)
Define a target **configuration** (per qubit/coupler: a frequency in MHz if `>10`, a flux if `≤10`, or `"<J∥/|J|>@<w_q>"` for a tunable coupler), and it inverts the crosstalk matrix to produce the voltages that realize it.
- **Edit:** the `configuration` dict, `SAVE_VOLTAGES_PATH`, and the `plot_bare_system` / `plot_effective_system` toggles.
- **Output:** a voltages JSON `{voltages, frequencies_comment, dac_map}` written to `SAVE_VOLTAGES_PATH`, a printed freq/voltage table, and (when the toggles are on) bare and dressed triangle-ladder plots via `Device_calib/helper_Triladder_plotting.py`.
- No hardware; safe to run. Defaults to writing `scratchwork.json` — repoint `SAVE_VOLTAGES_PATH` at a named file to save a real operating point (or set it to `None` to skip saving), and note it **overwrites** whatever path it points at.

### 2. `SET_QBLOX_VOLTAGES.py` — push a voltages JSON onto the chip ⚠️ hardware
The **only script that drives real DC onto the device.** Reads a voltages JSON and ramps each `dac_map` channel to its voltage on the D5a module.
- **Edit:** `_JSON_PATH` (which operating point to set), `set_unused_to_zero`.
- **Safety:** ±4 V bipolar span, ramped (`ramp_step=0.003`, `ramp_interval=0.01`), COM3 / module 2; channels not in `dac_map` are zeroed when `set_unused_to_zero`. The `dac_map` is **1-based** (Q1→DAC 1 … C6→DAC 14) — verify this against the current wiring map before trusting it.

### 3. `Calculate_FF_array.py` — fast-flux gains to reach target frequencies
Starting from the DC operating point in `PRESENT_CONFIG.VOLTAGES_PATH`, compute the **fast-flux gains** that move each qubit to a desired dressed frequency (the pulsed knob that drives the quench dynamics).
- **Edit:** the `frequencies` dict.
- **Output:** printed gains dict and an ordered gain list for the qubits.
- No hardware; read-only on the calibration.

### 4. `Modify_Qubit_Flux_Offsets.py` — recalibrate DC flux offsets ⚠️ writes calibration
Fold newly measured qubit frequencies back into `DeviceData.zero_voltage_fluxes` (the flux each loop sees at 0 V, which drifts between cooldowns). Use it when a qubit lands off its expected frequency at a known operating point.
- **Edit:** `found_qubits`, a list of `[qubit, expected, found]` (each of `expected`/`found` is a frequency in MHz if `>10`, else a flux directly).
- **Effect:** rewrites `DEVICE_PATH` in place and first saves a `DEVICE_PATH + ".previous"` backup to revert. Frequency→flux conversion is sign-ambiguous — the script prints the converted flux so you can check the sign.

---

## `Voltage_jsons/` — saved operating points

One subfolder per device (`8QV1`). File-name convention:

- `all_voltages_0.json`, `couplers_guess_0.json` — baseline / initial-guess points.
- `zero_flux_*` / `pi_flux_*` — qubits parked at flux 0 vs flux −0.5 (the two rung-coupling signs).
- `..._J_II_is_<N>J` — tunable-coupler setting: J∥/|J| ratio = `N` (`halfJ`, `1J`, `2J`, `3J`).
- `couplers_calib/Q<N>_high.json` — coupler-calibration points: qubit N parked at its max frequency, the rest pushed low, to isolate one qubit.
- `scratchwork.json` — throwaway.

Each file is a `{voltages, frequencies_comment, dac_map}` dict. `frequencies_comment` is a human-readable record only; `SET_QBLOX_VOLTAGES.py` reads only `voltages` and `dac_map`.

---

## Typical loops

- **Change operating point:** `Generate_Voltages_Dict` (design → JSON) → `SET_QBLOX_VOLTAGES` (`_JSON_PATH` = that JSON) → point `PRESENT_CONFIG.VOLTAGES_PATH` at it.
- **Plan a quench:** with `PRESENT_CONFIG` at the current point, `Calculate_FF_array` → fast-flux gains for the pulse sequence.
- **After re-measuring frequencies:** `Modify_Qubit_Flux_Offsets` (fill `found_qubits`) → regenerate voltages if needed.

---

## Known issues

- **`PRESENT_CONFIG.currently_set_voltages` is never written back** by `SET_QBLOX_VOLTAGES`, so it is not a reliable record of what is physically on the chip.
