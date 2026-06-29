# Device_calib

A clean, multi-qubit device calibration backend. The entirety of required calibration and an interface for retrieving voltages and fast-flux gains, in three files (plus a diagonalization helper).

The interface should also include a way to update zero-voltage flux offsets. A nice way to load data into `DataModel` would be welcome but is not required.

**Units:** frequencies/energies in MHz, fluxes dimensionless (ratio of π), times in ns.

The ultimate purpose is take **qubit, coupling, and crosstalk calibration data** to produce a **fast-flux to frequency mapping** (and coupling strengths). It takes 

**VoltageConfiguration**: specific voltage point, such as all qubits at quarter-flux and couplers at a desired tunable coupling strength. **The key purpose is fast-flux to frequency mapping** (dressed by couplers). Initialization takes a human-entered flux configuration, and adds the chosen applied voltages to information on the **DeviceInterface**.

**DeviceInterface**: contains all device-specific calibrations, independent across different set voltage points. Mostly helper functions for **VoltageConfiguration**.

**DataModel**: json storing of device data. 

Everything below was written by Claude. It is technically true but in the human text I talk about the purpose of this module.

## Pipeline

1. **`DeviceData`** — the calibration as numbers on disk, storable and loadable by JSON. Per-transmon spectrum parameters, the crosstalk matrix encoded into each transmon's `crosstalk_map`, pairwise couplings, and the flux offsets of each loop at zero voltage.
2. **`DeviceInterface`** — the calibration as an object. Assembles the crosstalk matrix from the per-transmon maps and exposes the matrix operations (flux↔voltage) and topology queries (which couplers are adjacent to which qubits).
3. **`VoltageConfiguration`** — one operating point with chosen J_||/J and resting qubit flux. Takes a human-friendly spec (some qubits by frequency, some couplers by tunable-coupling target), resolves it into a `flux_map`, and exposes the user interface for: "what fast-flux gain do I apply to land Q1 at 4500 MHz?"

## Module map

| Module | Purpose |
|---|---|
| [DeviceData.py](DeviceData.py) | Storage dataclasses + JSON I/O |
| [DeviceInterface.py](DeviceInterface.py) | `DeviceInterface` — crosstalk, flux↔voltage, coupling lookups |
| [VoltageConfiguration.py](VoltageConfiguration.py) | One operating point; dressed↔bare frequencies; fast-flux gain conversion |
| [qt_qubit_sys.py](qt_qubit_sys.py) | QuTiP M-qubit diagonalization helper (used for dressing) |

## Quick start

```python
from Device_calib.DeviceData import DeviceData
from Device_calib.DeviceInterface import DeviceInterface

data = DeviceData.from_json("8QV1.json")
dev = DeviceInterface(data)

# Build an operating point. Values >10 are MHz; ≤10 are flux; "<ratio>@<w_q>" targets a tunable coupler.
vc = dev.create_voltage_configuration({"Q1": 4380, "Q2": 3820, "C1": 0.5, "C2": 0.5})

# What fast-flux gain pushes Q1 to 4500 MHz (dressed)?
gains = vc.desired_freqs_to_fast_flux({"Q1": 4500})

# What voltages produce the DC operating point?
flux_vec = [vc.flux_map[n] for n in dev.ordered_names]
V = dev.flux_to_voltage(flux_vec)
```

## DeviceData — storage layer

Frequencies in MHz, fluxes dimensionless. The only logic lives on `TransmonData.freq` / `flux`; everything else is plain fields.

### `TransmonData` [DeviceData.py:10](DeviceData.py#L10)

| Field | Meaning |
|---|---|
| `name` | string identifier, e.g. `"Q1"` |
| `role` | `"Qubit"` or `"Coupler"` |
| `w_max`, `w_min`, `c` | spectrum parameters: f(φ) = √(A²cos²(πφ) + B²sin²(πφ)) − c, with A = w_max+c, B = w_min+c |
| `ffgain_quantum` | fast-flux gain units per unit of flux. `0` if no fast-flux line exists (couplers) |
| `Ec` | charging energy (default 180). Decoupled from `c` because non-physical `c` fits are common |
| `crosstalk_map` | `{flux_line_name: sensitivity}` — one row of the crosstalk matrix |

- `freq(flux) -> MHz` — spectrum from the parameters above. [DeviceData.py:22](DeviceData.py#L22)
- `flux(freq) -> [-0.5, 0]` — inverse via `root_scalar`; raises `ValueError` if outside [w_min, w_max]. Accepts scalars or arrays. [DeviceData.py:28](DeviceData.py#L28)

### `Coupling` [DeviceData.py:52](DeviceData.py#L52)
`q1`, `q2`, `gamma`. Coupling J = gamma/4000 · √((w₁+Ec₁)(w₂+Ec₂)); `gamma` is approximately the coupling in MHz when both transmons sit at 4 GHz.

### `DeviceData` [DeviceData.py:59](DeviceData.py#L59)
Top-level container and JSON entry point. Fields: `name`, `timestamp`, `transmons: {name: TransmonData}`, `couplings: [Coupling]`, `zero_voltage_fluxes: {name: φ₀}` (the flux each loop sees at V = 0; drifts between cooldowns).

- `to_json(path=None, indent=2) -> str` — write to disk and/or return JSON text.
- `from_json(source)` — classmethod; `source` may be a JSON string or a path. Round-trips via `dacite`.

## DeviceInterface — interface layer

`DeviceInterface(data)` ingests a `DeviceData`, partitions transmons by `role`, and precomputes the crosstalk matrix C and its inverse so that **F = C·V + F₀**, where F is the vector of fluxes through each loop and V is the vector of applied voltages.

### Attributes

| Attribute | Meaning |
|---|---|
| `transmons`, `qubits`, `couplers` | dicts keyed by name |
| `ordered_names` | sorted qubits then sorted couplers — row/column order for all vectors below |
| `crosstalk_matrix`, `crosstalk_inverse` | M×M, ordered per `ordered_names` |
| `zero_voltage_fluxes` | F₀ vector in `ordered_names` order |
| `couplings` | `{(q1, q2): gamma}` with sorted-name keys |

### Methods

- `create_voltage_configuration(configuration: dict) -> VoltageConfiguration` — main entry point. [DeviceInterface.py:43](DeviceInterface.py#L43)
- `flux_to_voltage(flux_vector)` / `voltage_to_flux(voltage_vector)` — vector conversions in `ordered_names` order. [DeviceInterface.py:46](DeviceInterface.py#L46)
- `bare_freqs_to_flux(bare_freqs)` — element-wise inverse of each transmon's spectrum.
- `coupling_exists(q1, q2) -> bool`.
- `get_coupling(Q1=w1, Q2=w2) -> MHz` — direct exchange given bare frequencies. The kwarg syntax encodes both the names *and* the frequencies. [DeviceInterface.py:59](DeviceInterface.py#L59)
- `get_adjacent_couplers(qubit_name)` / `get_adjacent_qubits_of_coupler(coupler_name)` — return `[(name, gamma), …]`.
- `determine_coupler_freq(c_name, g_eff, w_q) -> MHz` — solves the Q-C-Q dispersive formula for the coupler frequency that yields effective coupling `g_eff` between two adjacent qubits, both at `w_q`. [DeviceInterface.py:80](DeviceInterface.py#L80)

Module-level helper `signed_eff_g(w1, w2, wc, g1, g2, g12)` — dispersive effective coupling formula. [DeviceInterface.py:94](DeviceInterface.py#L94)

## VoltageConfiguration — operating point

`VoltageConfiguration(device, configuration: dict)` resolves one set point and stores `flux_map: {name: φ}` — the qubit/coupler fluxes *before* any fast-flux is applied. Fast-flux is then a perturbation around this point.

### `configuration` value conventions

Per-entry, keyed by qubit/coupler name:

| Value | Interpretation |
|---|---|
| `float > 10` | frequency in MHz (dressed, for qubits; bare, for couplers) |
| `float ≤ 10` | flux directly (dimensionless) |
| `"<ratio>@<w_q>"` (couplers only) | tunable coupler target: J_∥/J = `ratio` when both adjacent qubits are at `w_q` MHz |
| omitted | defaults to φ = 0 (warned via `print`) |
| unknown name | `ValueError` |

Couplers are resolved first (their dressing by qubits is treated as negligible), then qubits are dressed via the local C-Q-C subspace.

### Fast-flux interface

- `desired_freqs_to_fast_flux({name: dressed_freq_MHz}) -> {name: gain}` — what FF gain reaches each desired dressed frequency, starting from `flux_map`. Raises if any `name` isn't a qubit. [VoltageConfiguration.py:59](VoltageConfiguration.py#L59)
- `fast_fluxes_to_freqs({name: gain}) -> {name: freq_MHz}` — inverse: applies gains, returns resulting bare qubit frequencies. [VoltageConfiguration.py:71](VoltageConfiguration.py#L71)

Convention: **1 flux quantum = `ffgain_quantum` FF gain units**, so `Δgain = Δflux · ffgain_quantum`.

### Dressing

- `bare_to_dressed_freq(q_name, bare_freq)` / `dressed_to_bare_freq(q_name, dressed_freq)` — invertible map through the local C-Q-C diagonalization. `dressed_to_bare_freq` uses `root_scalar` bracketed by `[w_min, w_max]`. [VoltageConfiguration.py:82](VoltageConfiguration.py#L82)

### Private helpers

- `_adjacent_coupler_data(q_name) -> (names, freqs, gammas)`
- `_dressed_qubit_freq(bare, q_name, coupler_freqs, gammas)` — builds an `M_qubit_sys`, returns the energy of the eigenstate with maximum overlap on `|1, 0, …, 0⟩` (qubit excited, couplers ground).

## qt_qubit_sys — diagonalization helper

`M_qubit_sys(w, U, couplings={}, ...)` is a general-purpose QuTiP wrapper used here only via `dressed_state(fock_label)`. The copy in this folder is pasted from the `8QV1` folder — see the header note in [qt_qubit_sys.py](qt_qubit_sys.py).

## Known gaps / TODO

- No interface yet for updating `zero_voltage_fluxes` between cooldowns.
- `get_coupling` uses `**kwargs` to encode both names and frequencies — clever but awkward for programmatic callers.
- `crosstalk_map` stores every entry including zeros; could be sparsified since `DeviceInterface` defaults missing entries to 0.
