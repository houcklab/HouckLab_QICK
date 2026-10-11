# `qubit_parameters.json`: data only

The JSON stores **measured/calibrated values only**. It contains no logic: no recipes, no deltas to resolve, and no name references. Every FF array is a plain 8-int list (Q1..Q8), and **every FF array key starts with `FF_`**. Save the FF point where things actually happen (a swap point, a jump point), not a detuning. Compose any derived array in your script with `FF_gains` (§3).

## 1. Layout

```
_comment
drive_groups/<group>/             FF_Readouts, FF_Pulses (group level), description
                     entries/<e>/  Readout, Qubit, SingleShot  (Readout/Qubit may hold FF_override)
ff_groups/                        free-form FF data, no required structure
    ramp_groups/<group>/<entry>/      FF_Expt (+ FF_Init_delta, comment)
    dynamics_groups/<group>/<entry>/  FF_Dynamics | FF_BS, t_offset, exact_t_bs, ij_*, pad_bs, meas_pi2_*_abs
```

`drive_groups` holds both readout points (groups with `FF_Readouts` and `Readout` blocks, e.g. `readout_3800`) and pure drive groups (e.g. `ramsey_3800+`). In `ff_groups`, a group's entries sit directly under the group, next to its `description`.

**FF placement rule (drive_groups):** `FF_Readouts` and `FF_Pulses` live on the group. An entry's `Readout` / `Qubit` object may carry `FF_override`: a list replaces the whole group array; a single number replaces only index `int(entry_name[0]) - 1` (entry names start with their 1-based qubit number, e.g. `3`, `5A`, `3_3800+`). `FF_Readouts` / `FF_Pulses` inside an entry or its `Readout` / `Qubit` object raise a `KeyError`. Overrides are only applied by `drive_ff` when `qubit_entry` is given (so `res_config` applies it for a single readout entry only).

`FF_Init_delta` is an optional ramp-entry array of plain data. Scripts apply it themselves; nothing in `QubitParams` reads it. Its values are relative to the old `Expt_3800` base `[23036, 0, -6890, -9134, -6023, -8606, -5872, -7759]`, **not** to the entry's `FF_Expt`. The two are the same only for `6Q_highest`, `6Q_lowest`, `8Q_4815` and `8Q_4815_lowest`.

## 2. Retrievers (`triangle_lattice_quench/build_config.py`)

```python
from triangle_lattice_quench.build_config import QubitParams
qp = QubitParams(jd)                                          # loaded dict or path
qp.get_ff("ramp_groups", "ramp_3800", "56", "FF_Expt")        # any value under ff_groups
qp.drive_ff("FF_Pulses", "ramsey_3800+", "1_3800+")           # FF array under drive_groups (placement rule)
qp.drive_ff("FF_Readouts", "readout_3800")
qp.res_config("readout_3800", ["5", "6"])                     # res_freqs/res_gains/readout_lengths/adc_trig_delays, ro_chs, Qubit_Readout_List, FF_Readouts
qp.qubit_config("ramsey_3800+", ["5_3800+"])                  # qubit_freqs/qubit_gains/sigma, Qubit_Pulse (labels), FF_Pulses
qp.res_qubit_config("readout_3800", ["5", "6"], ["5"])        # pulses looked up in the readout group
```

Every lookup names its drive group explicitly, and entries are only looked up inside that group (nothing is searched). `FF_Pulses` is the first entry's array after its `FF_override`; with no entries it is the group-level array. All retrievers return deep copies and have no fallbacks. A missing key raises a `KeyError` that names the full path and lists the keys available where the lookup failed.

There is no `build_config()` function any more. Build the cfg yourself from `MUXInitialize.BaseConfig | qp.res_qubit_config(...)`; `Helpers/FF_utils.FFDefinitions` reads `fast_flux_chs`, `fast_flux_delays`, `FF_Readouts`, `FF_Pulses` (and an Expt array) from that cfg.

## 3. Composing FF arrays in a script

```python
from triangle_lattice_quench.Helpers.Qubit_Parameters_Helpers import FF_gains

expt = FF_gains(qp.get_ff("ramp_groups", "ramp_3800", "56", "FF_Expt"))
init = expt.subsys(5, 6, det=-6000).set(Q5=-9000).add(Q6=500)
```

`triangle_lattice_quench/test_build_config.py` has executable examples and shows the error messages.
