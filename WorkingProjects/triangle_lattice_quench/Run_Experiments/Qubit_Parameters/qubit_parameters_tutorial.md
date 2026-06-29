# `qubit_parameters.json` — A Tutorial on Drive Groups, Ramp States, and Dynamics Points

This file documents the four namespaces inside `qubit_parameters.json` and how they get assembled into the `cfg` dict that every experiment consumes. Read this if you've ever stared at `Readout_Point="readout_3800_new"`, `Ramp_State="56"`, `Dynamics_Point="resonant"` and wondered which knob does what.

Assumed background: basic quantum-info (qubits, drive frequencies, readout), QICK terminology (FF channel = fast-flux DAC channel), and Python.

---

## 1. The mental model: qubits visit several "FF states" during one shot

Each FF channel is a DAC that biases one qubit's transition frequency through a magnetic-flux coupler. During a single shot the FFs walk through **a sequence of bias settings** — one per logical "stage" of the experiment:

```
[Pulse_FF]    ← qubits at their individual drive frequencies; play single-qubit pulses here
   │
[RampInit_FF] ← optional: starting bias for an explicit ramp into Expt_FF
   │   ramp (linear/compensated)
   ▼
[Expt_FF]     ← experiment bias point (e.g. two qubits brought into resonance for swap)
   │
[Dynamics_FF] ← optional further jump (used by beamsplitter / quench protocols)
   │
[Pulse_FF]    ← back to drive freq for measurement pulses (if any)
   │
[Readout_FF]  ← qubits at readout frequencies; play resonator pulse, ADC trigger
```

Not every experiment uses every stage. A simple T1 lives at one bias. A beamsplitter calibration jumps `Pulse → Expt → Dynamics → Pulse → Readout`. The William-Oliver phase calibration we just built jumps `Pulse → Expt → Pulse → Readout`.

**Each FF stage's gain value (one int per FF channel, 8 channels total in this firmware)** lives in a different place in the JSON. The four namespaces below each own one or more of these stages.

---

## 2. The four namespaces — what each one is for

| Namespace | Owns (FF stages it defines) | Owns (per-qubit params it defines) | One entry = |
|---|---|---|---|
| **`readout_groups`** | `Readout_FF`, `Pulse_FF` (fallback) | Readout freq/gain/length/ADC offset/fidelity; **also** drive params (Frequency/Gain/sigma) for that operating point | one qubit at one readout operating point |
| **`drive_groups`** | `Pulse_FF` (alternative) | Drive Frequency/Gain/sigma | one qubit at one drive operating point (independent of readout) |
| **`ramp_groups`** | `Init_FF`, `Expt_FF` | — | one "experimental state" (where the FFs end up after the ramp) |
| **`dynamics_groups`** | `Dynamics_FF` (a.k.a. `BS_FF`), plus `t_offset` / `ij_samples` / etc. | — | one "dynamics point" (further FF settings + channel-skew timing) |

Each namespace contains multiple **groups** (e.g. `readout_3800_new` is one readout group); each group contains multiple **entries** (e.g. `"3"`, `"4"`, …, `"8"` inside `readout_3800_new.entries`). When you call `build_config(...)`, you pick **one** group/entry combo for each stage:

```python
build_config(
    Qubit_Readout = [3,4,5,6,7,8],   # which entries in the readout group → which qubits to read out
    Qubit_Pulse   = [3,4,5,6,7,8],   # which entries to use as drive (defaults to Qubit_Readout)
    Readout_Point = "readout_3800_new",   # picks the readout group
    Ramp_State    = "56",                  # picks an entry inside some ramp group
    Dynamics_Point= "resonant",            # picks an entry inside some dynamics group
)
```

`build_config` then resolves each pick into the final cfg dict. The next sections walk through each namespace in detail.

---

## 3. `readout_groups` — readout operating points

### Anatomy

```jsonc
"readout_3800_new": {
    "description": "...",
    "Readout_FF": [27320, 0, -20534, -9200, 3463, -21422, -3764, 4481],
    "Pulse_FF":   [27320, 0, -20534, -9200, 3463, -21422, -3764, 4481],
    "entries": {
        "6": {
            "Readout": {
                "Frequency":    7441.1,
                "Gain":         2500,
                "Readout_Time": 3,
                "ADC_Offset":   1,
                "fidelity":     0.689,
                "angle":        3.131,        // IQ rotation for SingleShot
                "threshold":    2.528,        // SingleShot threshold
                ...
            },
            "Qubit": {                       // ← drive params at this operating point
                "Frequency": 3557.38,
                "Gain":      3019,
                "sigma":     0.03,
                "T1":        13.5,
                "T2R":       0.61
            }
        },
        "4": { ... }, "5": { ... }, ...
    }
}
```

### What each field is for

- **Group-level `Readout_FF`** (8 floats) — the FF bias that puts all qubits at their **readout frequencies** simultaneously. Used during ADC acquisition.
- **Group-level `Pulse_FF`** (8 floats) — the FF bias for driving qubits during this readout point. **Often equal to `Readout_FF`** (as in `readout_3800_new` above), meaning "drive and read out at the same FF point". The drive_groups namespace exists for cases where you want them different.
- **Entry `Readout` sub-dict** — everything that goes into `res_freqs`, `res_gains`, `readout_lengths`, `adc_trig_delays`, and SingleShot's `angle` / `threshold` / `confusion_matrix`.
- **Entry `Qubit` sub-dict** — the per-qubit drive params (`qubit_freqs`, `qubit_gains`, `sigma`). Present **when the drive and the readout happen at the same FF point**, so the qubit characterization "lives with" the readout entry.

### What it controls in cfg

```
res_freqs[i]       <- entries[Qubit_Readout[i]].Readout.Frequency - res_LO
res_gains[i]       <- entries[Qubit_Readout[i]].Readout.Gain / 32766 * N
readout_lengths[i] <- entries[Qubit_Readout[i]].Readout.Readout_Time
adc_trig_delays[i] <- entries[Qubit_Readout[i]].Readout.ADC_Offset
FF_Qubits[i].Gain_Readout <- group.Readout_FF[i]
FF_Qubits[i].Gain_Pulse   <- (drive group's Pulse_FF, or readout group's Pulse_FF if no drive given)
```

### Which to pick

Pick the readout group whose qubits are calibrated at the operating point you want to read out at. `readout_3800` and `readout_3800_new` both target the same 3800 readout point — `_new` is the more recent calibration. For our six-qubit work (Qubit_Readout = 3..8) use **`readout_3800_new`**.

---

## 4. `drive_groups` — alternative drive operating points

### Why this namespace exists separately from readout_groups

Sometimes you want to drive at a **different FF point** than where you read out. For example: drive at a sweet-spot where the qubit has long T2 (for high-fidelity gates), then FF-ramp to the readout point, then read. The `Pulse_FF` and qubit drive params at the drive operating point come from the drive group; the readout point and the FF settings for readout come from the readout group.

If you don't need this separation (drive and readout at the same FF point), you can leave `Qubit_Pulse` blank, and `build_config` falls back to the readout group's entries for drive params. That's the common case.

### Anatomy

```jsonc
"ramsey_3800+": {
    "description": "Ramsey drives at +6 MHz detuning, all 8 qubits",
    "_recipe": {                          // ← see §6 below
        "base":   "Expt_3800",            // base FF array from base_params
        "method": "subsys",
        "det":    6000                    // each channel gets +6000 except listed qubits
    },
    "entries": {
        "6_3800+": {
            "_recipe_arg": [6],           // ← which channels keep the base value
            "Qubit": {
                "Frequency": 3800,
                "Gain":      4284,
                "sigma":     0.03
            }
        },
        "7_3800+": { "_recipe_arg": [7], "Qubit": {...} },
        ...
    }
}
```

### What each field is for

- **Group-level `Pulse_FF`** OR **`_recipe`** — the FF bias for drive operations. May be `null` if a `_recipe` is provided (see §6 below).
- **Entry `Qubit` sub-dict** — drive params (frequency, gain, sigma) at this drive operating point. Different from the readout group's `Qubit` because you're driving at a different FF.

### When to pick a drive group vs. leave it blank

- **Leave blank** (`Drive group: (none)` in the GUI) for the common case: drive at the readout point. `_resolve_drive` then falls back to the readout group's entries. This is what `mott_quench_basic.py` does.
- **Pick one** (e.g. `ramsey_3800+`) when you specifically want a non-readout drive FF — typically for high-fidelity Ramsey/T2/AllXY style experiments where you want to drive at a sweet spot.

For our pi/2 phase calibration → leave blank.

---

## 5. `ramp_groups` — where the FFs go for the experiment

The "ramp" is the FF transition from `Pulse_FF` (drive bias) to `Expt_FF` (experiment bias). The entry inside a ramp group defines **where Expt_FF ends up** — i.e., the FF biases during the experiment window itself.

### Anatomy

```jsonc
"ramp_3800": {
    "description": "Ramp groups starting from Expt_3800",
    "Expt_FF": "Expt_3800",               // ← group-level baseline (deref'd from base_params)
    "entries": {
        "67": {
            "Init_FF_delta":  [12000, 12000, 12000, 12000, 12000, 0, -5000, 12000],
            "Expt_FF_delta":  [12000, 12000, 12000, 12000, 12000, 0,     0, 12000]
        },
        "56": {
            "Init_FF_delta":  [12000, 12000, 12000, 12000, 0, -5000, 12000, 12000],
            "Expt_FF_delta":  [12000, 12000, 12000, 12000, 0,     0, 12000, 12000]
        },
        "6Q_Pulse_init": { "Init_FF_delta": null },
        ...
    }
}
```

### How entries resolve

Three independent specifications, in priority order:

1. **`Init_FF_abs`** / **`Expt_FF_abs`** — absolute 8-element arrays. Used as-is.
2. **`Init_FF_delta`** / **`Expt_FF_delta`** — 8-element arrays **added** to the group-level `Expt_FF`. So `Expt_FF_delta = [12000, ..., 0, 0, 12000]` for the `67` entry means "all channels +12000 except channels 6 and 7 which stay at the base value". The qubits at delta=0 are the ones in resonance.
3. **Nothing** — `Init_FF` falls back to `Expt_FF` (no separate init bias); `Expt_FF` falls back to the group-level baseline.

The group-level `Expt_FF` is itself a string `"Expt_3800"` that gets dereferenced from `base_params["Expt_3800"] = [23036, 0, -6890, -9134, -6023, -8606, -5872, -7759]`. So the final `Expt_FF` for entry `67` is:

```
base "Expt_3800"  = [23036,    0, -6890, -9134, -6023, -8606, -5872, -7759]
Expt_FF_delta    = [12000, 12000, 12000, 12000, 12000,     0,     0, 12000]
                 = [35036, 12000,  5110,  2866,  6977, -8606, -5872,  4241]
                                                       ↑ Q6   ↑ Q7 at the base ("resonant") FF
```

Channels 6 and 7 sit at the unperturbed base FF (where they're calibrated for resonance with each other); all others get pushed by +12000 (a large detuning, putting them well off-resonance from the 6-7 pair).

### What it controls in cfg

```
FF_Qubits[i].Gain_RampInit <- ramp_entry's Init_FF (or Expt_FF if Init_FF_delta is null)
FF_Qubits[i].Gain_Expt     <- ramp_entry's Expt_FF
```

### Two big practical patterns

- **Pair entries** (`"56"`, `"67"`, `"68"`, `"45"`, `"34"`, `"78"`, …) — bring **two qubits** into resonance, push everyone else far off. Use these for **2-qubit calibrations and the William-Oliver phase calibration**.
- **6Q_* entries** (`"6Q_Pulse_init"`, `"6Q_highest"`, `"6Q_lowest"`) — bring **all six qubits 3-8** to a common configuration. Used for **6-qubit Mott-quench and lattice protocols**.

If a pair entry exists for your pair, use it. Otherwise the closest one (or write a new entry in the JSON).

---

## 6. `dynamics_groups` — extra FF jump + channel-skew timing

`dynamics_groups` is the most subtle namespace, and its role depends on which experiment program is reading the cfg.

### Anatomy

```jsonc
"dynamics_FF_points": {
    "entries": {
        "resonant": {
            "Dynamics_FF_abs": "Expt_3800",        // string -> base_params lookup
            "t_offset":        [22, 25, 14, 25, 14, 14, 14, 6]
        },
        "345678": {
            "Dynamics_FF_abs": [0, 0, -6635, 2890, 6011, 3477, 6188, 4269]
        },
        "Q1_quench": {
            "BS_FF_abs": [2886, 0, -14316, -13195, -7754, 17156, -1880, -1076],
            "t_offset":  [22, 25, 14, 25, 14, 14, 14, 6]
        }
    }
}
```

### What it controls in cfg

```
FF_Qubits[i].Gain_BS       <- entry.Dynamics_FF or entry.BS_FF
FF_Qubits[i].Gain_Dynamics <- entry.Dynamics_FF or entry.BS_FF
cfg.t_offset               <- entry.t_offset                  (FF channel timing skews)
cfg.ij_samples             <- entry.ij_samples  (if present)  (beamsplitter intermediate-jump samples)
cfg.exact_t_bs             <- entry.exact_t_bs  (if present)  (exact beamsplitter time)
cfg.ij_gains               <- entry.ij_gains    (if present)
cfg.pad_bs                 <- entry.pad_bs      (if present)
```

(`Gain_BS` and `Gain_Dynamics` are the same value, written under both keys because different experiment programs read different names — `Gain_BS` for the beamsplitter pipeline, `Gain_Dynamics` for the newer code.)

### Which fields actually get used downstream

This depends on the program:

- **Beamsplitter / `mRampCurrentCalibrationR_SSMUX.py` family** — actively jumps the FFs to `Gain_BS / Gain_Dynamics` mid-sequence. The `Dynamics_FF_abs` matters.
- **`mMottQuench.py` / `MottQuenchBase.set_up_instance`** (and so our William-Oliver `MottQuenchPi2PhaseProgram`) — reads `Gain_Pulse`, `Gain_Expt`, `Gain_Readout` from the FF_Qubits dict. **`Gain_Dynamics` is NOT used by the IQArray builder.** What IS used: `cfg.t_offset` for FF channel timing skews.
- **Other quench protocols (`mQuenchExperiment.py`)** — use `Gain_BS` as the quench-amplitude endpoint.

### Practical implication for our pi/2 phase calibration

Because our IQArray builder reads `Gain_Expt` (from the ramp) but **not** `Gain_Dynamics`, the only thing the Dynamics_Point contributes is `t_offset`. So **any entry with a sensible t_offset will work** — `resonant` is the canonical default, `Q1_quench` provides the same `t_offset`, etc. The `Dynamics_FF_abs` field is along for the ride.

That's why I recommended `resonant` for the William-Oliver setup — it provides the standard channel-skew timing, and its Dynamics_FF (which would otherwise put qubits at `Expt_3800`) is unused by the program.

---

## 7. The `base_params` dereferencing and `_recipe` system

Two patterns in the JSON keep things DRY (don't repeat yourself).

### `base_params` named arrays

The top-level `base_params` dict holds named 8-channel FF arrays:

```jsonc
"base_params": {
    "Expt_3800": [23036, 0, -6890, -9134, -6023, -8606, -5872, -7759]
}
```

Anywhere the JSON expects an 8-array, you can put **the string name instead** and `build_config._deref_base(value, base_params)` will look it up. So `"Expt_FF": "Expt_3800"` at the ramp group level means "use the base_params array named `Expt_3800` as my group's Expt_FF baseline".

### `_recipe` for drive groups

Drive groups can compute `Pulse_FF` per entry via a recipe:

```jsonc
"_recipe": {
    "base":   "Expt_3800",      // start from this base array
    "method": "subsys",         // recipe method (see _apply_recipe in build_config.py)
    "det":    6000              // extra arg for this method
}
```

with `_recipe_arg` on each entry providing the per-entry data the recipe needs:

```jsonc
"_recipe_arg": [6]              // for method="subsys", these are the channels that DON'T get det'd
```

The recipe methods are:

- **`subsys`** — start from `base`, add `det` to every channel **except** the ones listed in `_recipe_arg`. Used by `ramsey_3800+/-` to detune all qubits except the one being driven.
- **`set`** — start from `base`, overwrite channels named in `_recipe_arg` (a dict like `{"q3": value}`).
- **`add`** — start from `base`, add to channels named in `_recipe_arg` (also a dict).

You'll mostly see `subsys` in the wild. Read `build_config.py:_apply_recipe` (lines 34-53) if you need the gory detail.

---

## 8. End-to-end: tracing one `build_config` call

Let's trace what happens with the William-Oliver inputs:

```python
build_config(
    Qubit_Readout = [5, 6],            # 2-qubit pair
    Qubit_Pulse   = [5, 6],
    Readout_Point = "readout_3800_new",
    Ramp_State    = "56",
    Dynamics_Point= "resonant",
)
```

### Step 1: Resolve readouts

For each `Q in [5, 6]`, look up `readout_3800_new.entries["5"]` and `readout_3800_new.entries["6"]`. Pull each entry's `Readout` sub-dict:

```python
readouts = [
    {Frequency: 7XXX, Gain: ..., Readout_Time: 3, ADC_Offset: 1, ...,
     Readout_FF: [27320, 0, -20534, -9200, 3463, -21422, -3764, 4481],
     Pulse_FF:   [27320, 0, -20534, -9200, 3463, -21422, -3764, 4481]},
    {Frequency: 7441.1, Gain: 2500, Readout_Time: 3, ADC_Offset: 1, ...,
     Readout_FF: ...,
     Pulse_FF:   ...},
]
```

(Both entries share the same group-level `Readout_FF` and `Pulse_FF`.)

### Step 2: Resolve drives

For each `P in [5, 6]`, `_resolve_drive` searches drive_groups first, doesn't find a matching entry, then searches readout_groups and finds `"5"` / `"6"` in `readout_3800_new`. Pull each entry's `Qubit` sub-dict.

### Step 3: Build per-qubit arrays

```python
qubit_config = {
    'qubit_freqs': [F5 - qubit_LO, F6 - qubit_LO],
    'qubit_gains': [G5 / 32766,   G6 / 32766],
    'sigma':       [s5, s6],
}
```

### Step 4: Resolve ramp_state="56"

`_resolve_ramp` finds `"56"` in `ramp_3800`. Computes:

```python
Init_FF = Expt_FF_baseline + Init_FF_delta   # 8 floats
Expt_FF = Expt_FF_baseline + Expt_FF_delta   # 8 floats
```

where `Expt_FF_baseline = base_params["Expt_3800"]`. So channels 5 and 6 sit at their base ("resonant for the 5-6 pair") and others get pushed by +12000.

### Step 5: Resolve dynamics_point="resonant"

`_resolve_dynamics` returns:

```python
{
    'Dynamics_FF': [Expt_3800_array],   # not used downstream by our program
    't_offset':    [22, 25, 14, 25, 14, 14, 14, 6]
}
```

`build_config` sets `cfg['t_offset'] = [22, 25, 14, ...]`.

### Step 6: Assemble FF_Qubits

For each of 8 FF channels:

```python
FF_Qubits["i"] = {
    'channel':       i,
    'Gain_Readout':  readout_FF[i-1],
    'Gain_Pulse':    pulse_FF[i-1],
    'Gain_RampInit': ramp_Init_FF[i-1],
    'Gain_Expt':     ramp_Expt_FF[i-1],
    'Gain_BS':       dyn_FF[i-1],         # unused by Mott
    'Gain_Dynamics': dyn_FF[i-1],         # unused by Mott (only t_offset is)
}
```

### Final cfg

A flat dict with:

- per-qubit arrays (`qubit_freqs`, `qubit_gains`, `sigma`, `res_freqs`, `res_gains`, `readout_lengths`, `adc_trig_delays`) — length 2 (one per qubit in `Qubit_Readout`)
- per-channel `FF_Qubits["1"]` … `FF_Qubits["8"]` (always 8 FF channels)
- `t_offset` from the dynamics entry
- `Qubit_Readout_List = [5, 6]` and `ro_chs = [0, 1]`

That's what every experiment program (Mott, William-Oliver, beamsplitter, T1) sees as its starting cfg.

---

## 9. Practical guidance: how to pick

### For single-qubit calibrations (T1, T2, Rabi, Spec)
- `Readout_Point`: the readout group calibrated for your operating point (e.g. `readout_3800_new`).
- `Qubit_Pulse`: usually the same as `Qubit_Readout` (leave drive group blank).
- `Ramp_State`: not needed (no FF excursion). Leave blank → `Gain_Expt = Gain_Pulse`.
- `Dynamics_Point`: not needed.

### For 2-qubit calibrations (chevron, William-Oliver phase)
- `Readout_Point`: same as above (the readout group with both qubits).
- `Qubit_Pulse`: leave blank.
- `Ramp_State`: pick the **pair entry** for your pair — `"56"`, `"67"`, `"45"`, `"34"`, … from `ramp_3800`.
- `Dynamics_Point`: `"resonant"` (the program uses only its `t_offset` — generic is fine).

### For 6-qubit Mott-style protocols
- `Readout_Point`: `readout_3800_new`.
- `Qubit_Pulse`: blank.
- `Ramp_State`: `"6Q_Pulse_init"` (or another `6Q_*` entry as needed).
- `Dynamics_Point`: `"345678"` (brings all six to common resonance) or `"resonant"` if you only need `t_offset`.

### For Ramsey / drive-frequency-sensitive experiments
- `Readout_Point`: your readout group.
- `Qubit_Pulse`: pick from `ramsey_3800+` (or `ramsey_3800-`) to drive at a specific detuning sweet-spot.
- `Ramp_State`, `Dynamics_Point`: as appropriate.

### When in doubt
Read the run script for the experiment you're trying to reproduce — they all pass the four selectors to `build_config(...)` near the top, and that tells you what was known to work.

---

## 10. Where to look in the code

| File | What lives there |
|---|---|
| `triangle_lattice_quench/Run_Experiments/Qubit_Parameters/qubit_parameters.json` | The JSON itself. |
| `triangle_lattice_quench/build_config.py` | `_resolve_readout`, `_resolve_drive`, `_resolve_ramp`, `_resolve_dynamics`, `_deref_base`, `_apply_recipe`, and the public `build_config(...)`. |
| `triangle_lattice_quench/Run_Experiments/mott_quench_basic.py` | Example: 6-qubit Mott setup. |
| `triangle_lattice_quench/Run_Experiments/pi2_phase_calibration.py` | Example: 2-qubit William-Oliver setup. |
| `triangle_lattice_quench/Experimental_Scripts/quench_experiments/mMottQuench.py` | Consumer: how `Gain_Pulse / Gain_Expt / Gain_Readout / t_offset` get wired into the FF program. |

---

## 11. TL;DR cheat sheet

```
readout_groups   = "where + how to read out + (often) drive params at the same point"
drive_groups     = "alternative drive operating point if you want to drive ≠ read"
ramp_groups      = "where the FFs go for the experiment (Init_FF + Expt_FF)"
dynamics_groups  = "extra FF jump (some programs) + FF channel timing skews (t_offset)"
```

When you call `build_config(Readout_Point=..., Qubit_Pulse=..., Ramp_State=..., Dynamics_Point=...)`, you're picking one entry from each of these namespaces, and `build_config` assembles their contributions into a single flat cfg dict that the experiment program then runs from.
