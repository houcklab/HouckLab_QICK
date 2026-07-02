# CSTQ03_BFC runner refactor — design

**Date:** 2026-07-02
**Status:** approved (pending spec review)
**Author:** refactor of `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/CSTQ03_BFC.py`

## 1. Motivation

`CSTQ03_BFC.py` is a 3,346-line "God script": ~46 lines of imports, 4 active-reset
helper functions, ~480 lines of device parameters + toggle flags + `*_params` dicts,
then **28 inline `if RunX:` measurement blocks** (~2,550 lines) that all share
module-level globals. Several blocks exceed 300–440 lines. It is the client-facing
runner the user edits and runs every session, and it is hard to navigate.

It also sits in `Experiments/` alongside the RFSoC program files (`m*.py`), mixing
client-facing orchestration with device-level programs.

## 2. Goals & non-goals

**Goals**
- Move the runner to a dedicated client-facing folder, separate from `m*.py`.
- Extract the 28 measurement bodies into a well-organized `runs/` package so the
  runner becomes a thin, navigable script (~550 lines) that is still run top-to-bottom.
- Fix the accidental cross-block `config` leak (see §5) **without** losing the
  intentional calibration carry-over.

**Non-goals (out of scope)**
- No physics/measurement-logic changes. Same programs, same call order, same saved data.
- Do not modify the RFSoC `m*.py` files.
- Do not retune any measurement parameters.

## 3. Target layout

```
Client_modules/
├── Experiments/          # RFSoC programs (m*.py) — UNTOUCHED
└── Runners/              # NEW — client-facing runners
    ├── CSTQ03_BFC.py     # the thin runner you edit + run (~550 lines)
    └── runs/             # extracted measurement procedures (package)
        ├── __init__.py       # re-exports Context, build_context, all run_*
        ├── context.py        # Context object + build_context()
        ├── calibration.py    # 4 active-reset / single-shot helper fns
        ├── basic.py          # transmission, two-tone spec, chi-shift, Rabi
        ├── coherence.py      # T1, T2, T2E, combos, T1SS, auto-coherence
        ├── charge_parity.py  # charge-dispersion variants, ModifiedRamsey(+Control), charge sweep
        ├── singleshot.py     # single-shot, readout/qubit optimize, active-reset verify
        └── zero_span.py      # zero-span parity + validation suite + evidence report
```

`runs/` lives under `Runners/` because it is shared only by device runners (future
`test_BTQ_BFC.py`, etc. reuse the same package).

## 4. The `Context` object (`runs/context.py`)

A dataclass bundling all shared runtime state the blocks currently read as globals, so
every routine has the signature `run_x(ctx, params)`:

```python
@dataclass
class Context:
    soc: object
    soccfg: object
    yoko: object
    config: dict            # persistent instrument config (see §5)
    outerFolder: str
    Qubit_Readout: int
    Qubit_Pulse: int
    Qubit_Parameters: dict
    start_voltage: float
    yoko_fixed: bool
    cavity_min: bool
    # derived scalars (from Qubit_Parameters[selected]):
    cavity_gain: float
    resonator_frequency_center: float
    qubit_gain: float
    pi2_gain: float
    qubit_frequency_center: float
    qubit_sigma: float
    qubit_flattop: object

    def working_config(self, *param_updates) -> dict:
        """Fresh shallow copy of self.config, updated with the given dict(s).
        Used for TRANSIENT per-experiment knobs; never mutates self.config."""
        cfg = dict(self.config)
        for u in param_updates:
            cfg.update(u)
        return cfg
```

`build_context(Qubit_Parameters, Qubit_Readout, Qubit_Pulse, start_voltage, *, trans_config,
qubit_config, extra_cfg=...)` performs the current top-of-script setup: `makeProxy()`,
yoko init + `ramp_to(start_voltage)`, assembles `config = BaseConfig | UpdateConfig`,
sets `config["FF_Qubits"]` and `config["cavity_min"]`, derives the scalars, and returns a
`Context`. This absorbs the ~250 lines of setup boilerplate.

## 5. Config model — the leak fix

**Current behavior (the smell):** all 28 blocks mutate one module-level `config` dict,
and 8 blocks rebind it via `config = config | <ExperimentParams>`. Whole `*_params`
dicts therefore leak into `config` and pollute later measurements in the same run.

**Scan result — what actually needs to persist across measurements:** only two keys are
ever written from a *measured/fitted result* rather than from a params dict or constant:

| Key          | Written by                                   | Meaning                    |
|--------------|----------------------------------------------|----------------------------|
| `pulse_freq` | `run_transmission_fit`, `run_transmission_sweep` | found cavity frequency |
| `res_phase`  | `calibrate_active_reset_readout`             | calibrated readout phase   |

(Plus one-time setup keys `FF_Qubits`, `cavity_min` set by `build_context`.)

Every other `config[...]` write is a transient scan knob: `reps`, `rounds`, `Gauss`,
`sigma`, `qubit_gain`, `qubit_length`, `SpecSpan`, `SpecNumPoints`, `step`, `start`,
`expts`, `relax_delay`, `current_voltage`.

**Design (fix, made safe):**
1. `ctx.config` is the **persistent instrument config**: channel/nqz assignments,
   readout & qubit frequencies/gains, `res_phase`, `pulse_freq`, `FF_Qubits`, `cavity_min`.
2. Each routine builds a **local** working config for its scan knobs:
   `cfg = ctx.working_config(params_mapped)`, and uses `cfg` locally. Transient knobs
   never touch `ctx.config`, so nothing leaks between measurements.
3. Persisting a result to the session is done **only** through the explicit allow-list
   above (`ctx.config["pulse_freq"] = ...`, `ctx.config["res_phase"] = ...`). These are
   the sole intended carry-overs and are greppable / documented — not "unintuitive".
4. No routine bulk-merges a `*_params` dict into `ctx.config` and no routine rebinds it.

This eliminates the accidental leak while preserving the two carry-overs that are
physically meaningful (finding the cavity first, then reusing its frequency; calibrating
readout phase, then reusing it).

## 6. Extraction rules (behavior-preservation contract)

- Each `if RunX:` block → one `run_x(ctx, params)` function. The body is copied
  **verbatim**, with only these rewrites:
  - bare shared names → `ctx.<field>` (e.g. `soc` → `ctx.soc`, `outerFolder` → `ctx.outerFolder`,
    `qubit_frequency_center` → `ctx.qubit_frequency_center`);
  - `config` reads → a local `cfg` obtained from `ctx.working_config(...)` (§5);
  - persistent writes → the §5 allow-list on `ctx.config`.
- Per-experiment `*_params` dicts are **passed in** by the client, not global.
- The 4 helper fns (`_extract_iq_from_singleshot_data`, `get_apriori_separator_from_singleshot`,
  `calibrate_active_reset_readout`, `wire_reset_into_mr_cfg`) move to `calibration.py` and
  take `ctx` where they currently read globals. `calibrate_active_reset_readout` mutates
  `ctx.config["res_phase"]` (an allowed carry-over).
- Same programs instantiated, same acquire/display/save calls, same order.

### Block → function → module map

| Flag | Function | Module |
|------|----------|--------|
| `Constant2Tone` | `run_constant_two_tone` | basic |
| `ConstantTone` | `run_constant_tone` | basic |
| `RunTransmissionSweep` | `run_transmission_fit` | basic |
| `RunTransmissionSweeps` | `run_transmission_sweep` | basic |
| `Run2ToneSpec` | `run_two_tone_spec` | basic |
| `RunSpecGainLengthSweep` | `run_spec_gain_length_sweep` | basic |
| `RunChiShift` | `run_chi_shift` | basic |
| `RunAmplitudeRabi` | `run_amplitude_rabi` | basic |
| `RunTrans_QubitSpec` | `run_trans_qubit_spec` | basic |
| `RunT1` | `run_t1` | coherence |
| `RunT2` | `run_t2` | coherence |
| `RunT2E` | `run_t2e` | coherence |
| `RunT1T2E` | `run_t1_t2e` | coherence |
| `RunT1T2RT2E` | `run_t1_t2r_t2e` | coherence |
| `RunT1SS` | `run_t1_ss` | coherence |
| `RunAutoCoherence` | `run_auto_coherence` | coherence |
| `Run2ToneChargeDispersionQuasiCW` | `run_two_tone_charge_dispersion_quasicw` | charge_parity |
| `RunChargeDispersionQuasiCW` | `run_charge_dispersion_quasicw` | charge_parity |
| `RunChargeDispersionRamsey` | `run_charge_dispersion_ramsey` | charge_parity |
| `RunChargeSweep` | `run_charge_sweep` | charge_parity |
| `RunModifiedRamsey` | `run_modified_ramsey` | charge_parity |
| `RunModifiedRamsey_Control` | `run_modified_ramsey_control` | charge_parity |
| `SingleShot` | `run_single_shot` | singleshot |
| `SingleShot_ReadoutOptimize` | `run_readout_optimize` | singleshot |
| `SingleShot_QubitOptimize` | `run_qubit_optimize` | singleshot |
| `RunActiveResetVerify` | `run_active_reset_verify` | singleshot |
| `RunZeroSpanParity` (+ `Validate_*`, `Build_EvidenceReport`) | `run_zero_span_parity` (+ validation dispatch) | zero_span |

## 7. The thin client (`Runners/CSTQ03_BFC.py`, ~550 lines)

Three clearly-bannered sections; params stay front-and-center (user's choice):

```python
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Runners.runs import *

# ═══ 1. DEVICE PARAMETERS (edit every session) ═══
Qubit_Parameters = { '1': {...}, ..., '6': {...} }
Qubit_Readout, Qubit_Pulse = 6, 6
start_voltage = 0.0

# ═══ 2. WHAT TO RUN — flags + per-experiment params ═══
Run2ToneSpec = True;  Spec_relevant_params = {...}
RunT1        = False; T1T2_params          = {...}
# ... all 36 flags + 23 params dicts ...

# ═══ 3. EXECUTE (don't edit) ═══
ctx = build_context(Qubit_Parameters, Qubit_Readout, Qubit_Pulse, start_voltage, ...)
if Run2ToneSpec: run_two_tone_spec(ctx, Spec_relevant_params)
if RunT1:        run_t1(ctx, T1T2_params)
# ... ~28 one-line dispatches ...
```

## 8. Import fix (required by the move)

`from utils import *` (bare) resolves today only because `Experiments/` is on the source
path; it breaks once the runner leaves that folder. All `runs/` modules use the absolute
path `from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils import *`.
The `m*.py` files (which also use bare `from utils import *`) are untouched.

## 9. Verification

1. All new files byte-compile (`python -m py_compile`).
2. AST import-trace from the new runner resolves with no dangling/missing imports and no
   reference to deleted trees.
3. Mechanical fidelity check: each extracted body issues the same program instantiations
   and acquire/display/save calls, in the same order, as its source block.
4. **Adversarial code review via dynamic workflow** targeting extraction fidelity:
   missed globals, dropped/incorrect `config` mutations, broken carry-over (`pulse_freq`
   / `res_phase`), wrong param threading, changed call order, and any accidental
   physics change. Findings verified by independent skeptic agents before acceptance.

## 10. Risks

- **Missed shared global** in an extracted block → `NameError` at run time. Mitigated by
  AST global-usage analysis (already enumerated) + the adversarial review.
- **Over-localizing a meaningful carry-over** (treating `pulse_freq`/`res_phase` as
  transient) → later measurement uses stale value. Mitigated by the explicit §5 allow-list
  and a review check dedicated to it.
- **`from utils import *` name collisions** surfaced by absolute import → none expected
  (same module), verified by byte-compile + trace.
```
