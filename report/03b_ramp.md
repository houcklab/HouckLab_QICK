# Section 3b — Ramping the Experiment

How fast-flux (FF) ramps are constructed, parameterized, and executed in QICK
tProc-V2 firmware. Active code is split between the front-end
`WorkingProjects/triangle_lattice_quench/` (Run scripts, qubit-parameter files)
and the dependency `WorkingProjects/Triangle_Lattice_tProcV2/` (helpers,
templates, experiment classes). The two `Helpers/` trees are byte-identical;
all production imports go through the `Triangle_Lattice_tProcV2` namespace
(e.g. `Program_Templates/AveragerProgramFF.py:1`).

---

## 1. Physical picture: what a "ramp" does

The triangle-lattice device is an array of 8 frequency-tunable transmons sitting
on a triangular lattice with engineered nearest-neighbour and next-nearest
exchange couplings. Each qubit has an individual fast-flux (FF) line whose
current sets the qubit's transition frequency. In the program we drive the FF
line as a DAC waveform: integer "FF gain" ∈ [-32766, 32766] maps via a
calibrated transfer function (Section 6) to a flux through the SQUID loop and
hence to a qubit detuning. By driving FF gains in time we get a time-dependent
single-qubit Hamiltonian, $H_q(t) = \frac{1}{2}\omega_q[\Phi(t)]\,\sigma^z_q$,
overlaid on the static exchange Hamiltonian $H_{XY} = \sum_{ij} J_{ij}(\sigma^+_i
\sigma^-_j + h.c.)$.

A **ramp** is a slow, smooth time-variation of these FF gains designed to drag
qubits in or out of mutual resonance. Two regimes matter for this project:

- *Adiabatic ramp.* If the ramp duration $\tau_\text{ramp}$ is much longer than
  the inverse of the smallest gap that opens during the sweep, the system stays
  in the instantaneous ground (or whatever Bloch-eigenstate) of the moving
  Hamiltonian. Used to *prepare* the ground state of the on-resonance XY model
  starting from a product state of detuned qubits.
- *Quench.* When the ramp is fast on the scale of the gap, the system retains
  population in higher Floquet/Bloch bands — this is the controlled
  non-equilibrium dynamics this project is built to study. "Quench" here is
  *not* an instantaneous step: it is a finite-duration ramp whose duration is
  the central knob (`ramp_duration` / `ramp_time`) that we sweep to interpolate
  between adiabatic and sudden limits. A pure jump (`ramp_duration = 0`)
  reduces to the legacy step-pulse, but in practice ramps of a few hundred
  to a few thousand ~290 ps samples are used.

The standard quench experiment is therefore a `ThreePartProgram`:
(1) prepare a product state at *initial* FF gains (qubits detuned), (2) ramp
the FF gains to bring qubits into resonance over `ramp_duration`, (3) measure
populations and density-density correlations after the ramp (or after an
additional hold + reverse ramp). The ramp shape, duration, start gain, and end
gain are exactly the knobs that interpolate between adiabatic state preparation
and a quench.

---

## 2. Ramp parameterization (`Helpers/RampHelpers.py`)

`Helpers/RampHelpers.py` is the single source of truth for waveform shapes.
The dispatcher is `generate_ramp` at `Helpers/RampHelpers.py:128`:

```python
def generate_ramp(initial_gain, final_gain, ramp_duration,
                  ramp_start_time=0, reverse=False, ramp_shape='cubic'):
```

It dispatches by `ramp_shape` to one of three primitive generators. All work
in **DAC sample units of 1 / 16 of a tProc clock cycle** (the file docstrings
note "clock cycles (4.65/16 ns)" — i.e. ~0.290 ns per sample at the V2 fabric
clock). All primitives return a numpy array of int-valued FF gains, exactly
sample-by-sample, that is later loaded as the I-data of a custom envelope.

### Shape options

- **Linear** — `generate_linear_ramp` (`RampHelpers.py:8`). Straight line from
  `initial_gain` to `final_gain` via `np.interp`. Args: `initial_gain`,
  `final_gain`, `ramp_duration`, `ramp_start_time=0`, `reverse=False`
  (no-op — `RampHelpers.py:16`), `flip=False` (reverses endpoints).
- **Cubic** — `generate_cubic_ramp` (`RampHelpers.py:32`). $g(t) = \Delta g\cdot
  (t/\tau)^3 + g_f$ for the default "soft-landing" version (flat near the end),
  or $\Delta g\cdot(t/\tau)^3 + g_i$ for `reverse=True` (flat near the start)
  (`RampHelpers.py:53-69`). This is the **default** and what every production
  experiment uses unless explicitly switched.
- **Exponential** — `generate_exp_ramp` (`RampHelpers.py:73`). One-tau
  exponential approach with `tau_factor = ±4` controlling concavity
  (`RampHelpers.py:94`).
- **Three-exponential (specialty)** — `generate_three_exp_ramp`
  (`RampHelpers.py:109`) is a hard-coded three-exponential profile (parameters
  on `RampHelpers.py:110`) intended to compensate the FF flux-line transfer
  function for arbitrary endpoints. It is *not* exposed through `generate_ramp`
  but is reachable through `FFEnvelope_Helpers.ThreeExpRampArrays`
  (`FFEnvelope_Helpers.py:81`).

### Common arguments

`initial_gain` (int DAC) — gain at $t \le$ `ramp_start_time`. `final_gain`
(int DAC) — gain at $t \ge$ `ramp_start_time + ramp_duration`. `ramp_duration`
(int, samples = clock-cycles/16) — must be non-negative
(`RampHelpers.py:22, 47`); the `__main__` example uses 750 samples ≈ 217 ns
(line 139). `ramp_start_time` (int, samples) — pre-ramp constant pad
(default 0). `reverse` — selects cubic/exponential concavity (ignored by
linear). Output array length is `ramp_start_time + ramp_duration + 1`
(lines 25, 50, 91).

### Per-channel arrays (`Helpers/FFEnvelope_Helpers.py`)

`get_gains(cfg, key)` (`FFEnvelope_Helpers.py:14`) reads
`cfg['FF_Qubits'][str(Q)][key]` for Q = 1..N then applies crosstalk
correction via `FF_Crosstalk_Helper.correct(...)`. Every gain vector going
into a ramp (initial, intermediate, final) is crosstalk-corrected, not raw.
`CubicRampArrays`, `LinearRampArrays` (line 73), and `ThreeExpRampArrays`
(line 81) call the corresponding shape primitive between two crosstalk-
corrected gain vectors. `CompensatedRampArrays(cfg, prev_key, initial_key,
final_key, ramp_duration, reverse=False)` (line 44) is the **production
path** used by every `set_up_instance` in `mRampExperiments.py` (lines 31,
201): it takes *three* gain points — `prev_key` (where the FF line is just
before the ramp window, typically `Gain_Pulse`), `initial_key` (ramp start),
`final_key` (ramp end) — generates the cubic ramp, then IIR-compensates the
combined (jump + ramp) waveform against the FF transfer function via
`Compensate(arr - prev_gains[j], prev_gains[j], Q)` (line 62). The
prev → initial jump is therefore pre-distorted to undo line settling.

---

## 3. `ramp_initial_gain` per FF qubit (UPDATE_CONFIG.py)

Every FF qubit ends up with three distinct gain settings inside
`config['FF_Qubits'][str(Q)]`:

- `Gain_Readout` (FF gain during readout)
- `Gain_Pulse` (FF gain during initial X-pulse / state preparation;
  the "pre-ramp" gain that the FF line has just before the ramp window)
- `Gain_Expt` (FF gain at the *end* of the ramp — i.e. the on-resonance,
  simulation-Hamiltonian point)
- `Gain_BS` (beamsplitter gain — used by `ThreePartProgramTwoFF`-style
  experiments after the ramp)
- `ramp_initial_gain` — the gain at the **start** of the ramp window. This is
  the topic of this subsection.

The `ramp_initial_gain` is set by the `try/except` block in
`Run_Experiments/UPDATE_CONFIG.py:14-24`:

```python
try:
    if Init_FF is not None:
        for Qubit, FFI in zip(('1','2','3','4','5','6','7','8'), Init_FF):
            FF_Qubits[Qubit]['ramp_initial_gain'] = FFI
        print('using init FFs')
    else:
        raise Exception
except:
    print('using pulse FFs as init FFs')
    for Qubit, FFI in zip(('1','2','3','4','5','6','7','8'), FFPulse):
        FF_Qubits[Qubit]['ramp_initial_gain'] = FFI
```

The same logic appears in `Run_Experiments/UPDATE_CONFIG_function.py:28-38` for
the function-style update.

### Where `Init_FF` comes from

`Init_FF` is a *module-level* variable defined in the active qubit-parameter
file before `UPDATE_CONFIG.py` is `exec`-ed. The convention is illustrated by
`Run_Experiments/qubit_parameter_files/pi_flux_J_ll_is_2J/Qubit_Parameters.py:318`:

```python
Init_FF = Qubit_Parameters[Ramp_state]['Ramp']['Init_FF']
```

i.e. the qubit-parameter file picks an "active ramp state" (e.g.
`Ramp_state = '8Q_4815'`, `Qubit_Parameters.py:304`) and copies that state's
`Ramp.Init_FF` 8-vector to the top-level `Init_FF`. The same pattern is used
in `pi_flux_J_ll_is_3J/Qubit_Parameters.py:341`,
`pi_flux_J_ll_is_J/Qubit_Parameters.py:316`,
`zero_flux_J_ll_is_J/Qubit_Parameters_old.py:285`, and so on. Calibration
helpers under `Run_Experiments/calibration_scripts/` (e.g.
`beamsplitter_calibration.py:90, 190`,
`beamsplitter_calibration_double_jump.py:98, 192, 297`,
`beamsplitter_pi_phase_check.py:54, 154`) re-fetch `Init_FF` per ramp state in
the same way.

### Why `ramp_initial_gain` matters

`ramp_initial_gain` is distinct from both `Gain_Pulse` and `Gain_Expt`. Just
before the ramp the FF line is held at `Gain_Pulse` (the qubit drive sweet
spot, where qubit frequency = `Qubit_Parameters['Qubit']['Frequency']`) for
the X-pulse. At the start of the ramp window the FF line *jumps* from
`Gain_Pulse` to `ramp_initial_gain` (the `Gain_Pulse → ramp_initial_gain`
step inside `CompensatedRampArrays`, `FFEnvelope_Helpers.py:62`); this places
the qubit at the *start detuning* of the simulation — typically far
off-resonance from neighbours so the prepared product state is a
near-eigenstate. The ramp then evolves from `ramp_initial_gain` to
`Gain_Expt` (on-resonance).

If `Init_FF` is `None` or undefined, the bare `except` at
`UPDATE_CONFIG.py:21` copies `Gain_Pulse` into `ramp_initial_gain` (lines
22-24): no start-of-ramp jump, ramp begins at the X-pulse flux. Acceptable
for single-qubit Rabi/spectroscopy; *wrong* for adiabatic preparation since
the qubits would start the ramp on top of each other in frequency.

`ramp_initial_gain` is consumed via `initial_key='ramp_initial_gain'` at
`mRampExperiments.py:31, 201`, `mRampCurrentCalibration_SSMUX.py:206`, and
`mRampCurrentCalibrationR_SSMUX.py:36`.

---

## 4. `ThreePartProgram` template

The template lives at
`Experimental_Scripts/Program_Templates/ThreePartProgram.py`. There are two
classes: `ThreePartProgramOneFF` (single FF segment — used for pure ramp
experiments) and `ThreePartProgramTwoFF` (two FF segments — ramp followed by a
BS step, used by the current-calibration scripts in Section 6). Both inherit
from `FFAveragerProgramV2`
(`Program_Templates/AveragerProgramFF.py:18`), which itself wraps QICK V2's
`AveragerProgramV2` with FF helpers and adds shot-readout
(`AveragerProgramFF.py:38-98`).

### `_initialize` (`ThreePartProgram.py:7-32`)

Compile-time setup. Declares the qubit drive gen (line 9) and MUX readout
gen + ADCs (lines 12-19) with a `const` `"res_drive"` pulse (lines 20-21).
`FF.FFDefinitions(self)` at line 23 (defined in `FF_utils.py:169-208`)
iterates `cfg["FF_Qubits"]`, declares each FF gen (`FF_utils.py:175`), reads
and crosstalk-corrects the readout/expt/pulse/BS gains
(`FF_utils.py:177-190`), and stores per-channel delays `gen_t0`
(`FF_utils.py:193-206`) so all FF lines arrive at the chip simultaneously.
After this call the program has `self.FFChannels`, `self.FFReadouts`,
`self.FFExpts`, `self.FFPulse`, `self.FFBS` as numpy arrays. A Gaussian
envelope `"qubit"` of width `cfg["sigma"]` and one `qubit_drive{i}` arb
pulse per qubit are added at lines 25-30.

### `_body` (`ThreePartProgram.py:33-68`) — the three parts

**Part 1 — X-pulse at `Gain_Pulse`** (lines 35-40): hold all FF lines at
`self.FFPulse` long enough to cover all pi-pulses plus a 9-cycle FF settling
delay (`FF_Delay_time = 9`, line 35), then play each `qubit_drive{i}` arb
pulse (lines 37-39). Prepares the product state at the qubit-drive sweet
spots. `delay_auto()` advances.

**Part 2 — Ramp to `Gain_Expt`** (lines 41-44): `FFPulses_direct` is called
with the 8-channel `IDataArray` (built by `CompensatedRampArrays`), length
`expt_samples` (= `ramp_duration` for a pure ramp), previous-gain context
`self.FFPulse`, label `'FFExpts'`. `FFPulses_direct` (`FF_utils.py:9-68`)
truncates each pulse to `length_dt`, head-pads to a multiple of 16 samples
and at least 3 cycles (`FF_utils.py:43-50`), registers a new envelope per
channel (lines 56-57), and plays at `t='auto'` (or `t_start + gen_t0[ch]`).

**Part 3 — Readout at `Gain_Readout`** (lines 47-55): hold FF at
`self.FFReadouts` for `res_length` µs (line 48), trigger each ADC (lines
51-52), play `res_drive` (line 53), `wait_auto()` (line 54), `delay_auto(10)`
(line 55).

**End — Inverted echo** (lines 57-68): each FF segment is replayed with
gain × −1 on a parallel waveform — `FFPulses(-1*self.FFReadouts, …)`,
`FFPulses_direct(-1*self.FFExpts, …, waveform_label='FF2')`,
`FFPulses(-1*self.FFPulse, …)` (lines 58, 65, 67). This integrates the FF
output to zero so no DC charges between shots. The separate
`waveform_label='FF2'` is required so QICK doesn't reuse the original
waveform memory.

### `ThreePartProgramTwoFF` (`ThreePartProgram.py:70-111`)

Adds a second FF segment between the ramp and readout. Concatenates
`IDataArray1[:expt_samples1]` with `IDataArray2[:expt_samples2]` into one
per-channel envelope played via one `FFPulses_direct` call (lines 84-87).
Used by current-calibration scripts: segment 1 = ramp to on-resonance,
segment 2 = beamsplitter step.

### Sweep-waveform variant

`ThreePartProgram_SweepOneFF` (`ThreePartProgram_SweepWaveform.py:11-41`) and
`SweepTwoFF` (line 46) replace the ramp segment with `FFLoad16Waveforms`
(`SweepWaveformAveragerProgram.py:47`) + `FFPulses_arb_length_and_delay`
(line 81), which lets QICK sweep ramp length *inside* one compiled program.
tProc-V2 plays waveforms in 16-sample (one clock cycle) increments, so 16
shifted copies of the envelope are pre-loaded — one per starting-sample
within a cycle — and `cycle_counter` / `sample_counter` registers
(`SweepWaveformAveragerProgram.py:140-153`) pick the right copy and length at
runtime. Initial values are written via `before_reps` at lines 36-43.

---

## 5. Building and running a basic ramp experiment

A complete recipe to run a ramp experiment (the standard adiabatic preparation
+ population readout) using `Run_Experiments/Ramp_Experiments.py`:

### Step 1 — choose qubits

Edit the top of
`Run_Experiments/Ramp_Experiments.py:14-26`:

```python
Qubit_Readout = [7,2,3,4,5,6,7,8]
Qubit_Pulse   = ['1_4Q_readout', '4_4Q_readout', '8_4Q_readout', '5_4Q_readout']
```

`Qubit_Readout` is a list of integers (1..8) — which qubits to read out
through the MUX. `Qubit_Pulse` is a list of *qubit-parameter keys* (e.g.
`'1_4Q_readout'`) that select a calibrated single-qubit pi-pulse for each
qubit you want to *excite* before the ramp. The strings are looked up in the
`Qubit_Parameters` dict from `qubit_parameter_files/Qubit_Parameters_Master.py`
(imported at `Ramp_Experiments.py:12`). For an
"all-qubits-detuned, only Q1/Q4/Q8/Q5 excited" initial state, this list
encodes the four sites that get a pi-pulse.

### Step 2 — choose ramp parameters

Pick which experiment to run by toggling the `run_*` flags
(`Ramp_Experiments.py:28-92`). The most basic one is *"populations vs delay
through the ramp"*, controlled by `run_ramp_population_over_time = True`
(`Ramp_Experiments.py:57`). Its parameter dict at line 59-61:

```python
population_vs_delay_dict = {
    'ramp_duration' : 1000, 'ramp_shape': 'cubic',
    'time_start': 0, 'time_end' : 1500, 'time_num_points' : 21,
    'reps': 1000, 'relax_delay':200,
    'time_to_show_shots_samples': 0,
}
```

Knobs:

- `ramp_duration` (samples = 290 ps each) — total ramp time. 1000 → ~290 ns
  ramp. This is the central adiabaticity knob.
- `ramp_shape` — `'cubic'`, `'linear'`, or `'exponential'`. Cubic is the
  standard "soft start, soft stop" choice used in production.
  (Note: in `PopulationVsTime` the ramp shape is currently hard-wired to
  cubic via `CompensatedRampArrays` —
  `mRampExperiments.py:201`.)
- `time_start`, `time_end`, `time_num_points` — sweep of the *hold time
  after the ramp ends*, in 290 ps samples. So the experiment plots the
  population at every probe time during the ramp + the constant-gain hold
  after.
- `reps` — number of averages per point (1000 here).
- `relax_delay` — µs between shots, set to ~5 T1.

### Step 3 — load qubit parameters and run

`exec(open("UPDATE_CONFIG.py").read())` (`Ramp_Experiments.py:175`) reads the
active qubit-parameter file (star-imported at line 12) which exports
`Init_FF`, `Ramp_FF`, `BS_FF` from the chosen `Ramp_state` and populates all
four `Gain_*` keys plus `ramp_initial_gain` (Section 3). Single-shot readout
calibration loads next via line 176. From the project root:

```bash
python -m WorkingProjects.triangle_lattice_quench.Run_Experiments.Ramp_Experiments
```

The active block at `Ramp_Experiments.py:218-222` instantiates
`PopulationVsTime` (`mRampExperiments.py:193-237`), a
`SweepExperiment1D_lines` whose `Program = ThreePartProgramOneFF`. Its
`init_sweep_vars` builds the FF waveform by calling
`FFEnvelope_Helpers.CompensatedRampArrays(cfg, 'Gain_Pulse',
'ramp_initial_gain', 'Gain_Expt', cfg['ramp_duration'])`
(`mRampExperiments.py:201-202`), concatenates a constant `time_end`-long hold
at `Gain_Expt` (lines 204-207), and previews the waveform before sending
(lines 209-214).

### Other useful experiment classes (same module, same recipe)

- `RampDurationVsPopulation` (`mRampExperiments.py:161`) — sweep
  `ramp_duration` to map adiabaticity. Set
  `run_ramp_duration_calibration = True`
  (`Ramp_Experiments.py:38`). Uses `ramp_duration_calibration_dict`
  (`Ramp_Experiments.py:39-41`) with `duration_start/end/num_points` and
  `double=True` to play the ramp forwards then in reverse (see
  `mRampExperiments.py:178`).
- `FFExptVsPopulation` (`mRampExperiments.py:186`) — fix `ramp_duration`,
  sweep one qubit's `Gain_Expt` to find on-resonance.
- `RampCheckDensityCorrelations` (`mRampExperiments.py:41`) — read
  density-density correlations $\langle n_i n_j n_k n_l\rangle$ after the
  ramp, with confusion-matrix-corrected populations.
- `PopulationVsTime_GainSweep` (`mRampExperiments.py:306`) — 2D map of
  population vs (time, ramp gain offset).
- `RampSweepLengthCorrelations` (`mRampExperiments.py:117`) — sweep
  ramp duration and read correlations; useful to check adiabaticity by
  measuring ground-state fidelity vs ramp time.

For a beamsplitter-after-ramp experiment use
`Run_Experiments/RampBeamsplitter_Correlations.py`, which uses
`ThreePartProgram_SweepTwoFF` (sweep-waveform two-FF program, see
`mRampCurrentCalibrationR_SSMUX.py:5-7, 27`).

---

## 6. Current-calibration scripts

The FF gain → physical flux mapping is calibrated by a chain of scripts under
`Experimental_Scripts/`:

- `mCurrentCalibration_SSMUX.py` — single-flux step calibration
  (no ramp, FF jumps directly).
- `mRampCurrentCalibration_SSMUX.py` — uses ramp (`ThreePartProgramTwoFF`)
  followed by a swap step. The "two FF" half of the program is the
  *beamsplitter swap pulse* whose oscillation period reads off the
  on-resonance pair detuning.
- `mRampCurrentCalibrationR_SSMUX.py` — the **R**-version:
  same physics but with the sweep-waveform program
  `ThreePartProgram_SweepTwoFF`, which lets QICK sweep the BS interaction
  time inside one program (`mRampCurrentCalibrationR_SSMUX.py:27`) — orders of
  magnitude faster than recompiling per point.

### What is being measured

In all of these, after the ramp, two qubits are placed close to resonance and
allowed to undergo coherent population swap (a beamsplitter / iSWAP-type
exchange). The **swap rate** $J_{ij}$ depends on the residual detuning between
the two qubits at the BS gain. By scanning the BS gain of one qubit and the
swap time, you map out a chevron pattern:

$P_\text{swap}(g, t) = \frac{J^2}{J^2 + \delta(g)^2}\sin^2\left(\sqrt{J^2 +
\delta(g)^2}\cdot t\right)$

where $\delta(g) = \omega_1 - \omega_2(g)$ and $g$ is the swept FF gain. The
chevron centre $g^*$ where $\delta(g^*) = 0$ defines on-resonance for that
pair, i.e. the FF gain that puts the two qubits at the same physical
frequency. That is the "current calibration" — it converts a DAC integer into
a known qubit-frequency operating point. The vertical (gain) axis of the
chevron, multiplied by the local FF transfer function (qubit-spectroscopy
slope $d\omega/dg$ at that bias), gives an absolute flux/current scale.

### Concrete fits and config

`Helpers/Beamsplitter_Fit.py` provides `fit_double_beamsplitter`,
`fit_beamsplitter_offset` (imported at
`mRampCurrentCalibrationR_SSMUX.py:18-19`). The two key sweeps:

- **Gain sweep** `RampBeamsplitterGainR` (lines 66-71): 2D population vs
  (BS time, swept-qubit `Gain_BS`). y-axis is
  `('FF_Qubits', str(swept_qubit), 'Gain_BS')`. Chevron centre $g^*$ →
  new `BS_FF` entry.
- **Offset sweep** `RampBeamsplitterOffsetR` (lines 59-64): 2D population vs
  (BS time, per-qubit arrival offset). y-axis is
  `("t_offset", swept_qubit-1)`. Fits the per-line cable-delay alignment;
  output is the `t_offset` 8-vector.

`RampBeamsplitterBase.set_up_instance` (lines 34-55) builds the two-segment
envelope: `IDataArray1` is the compensated cubic ramp from `Gain_Pulse →
ramp_initial_gain → Gain_Expt` over `ramp_time` samples (line 36, via
`CompensatedRampArrays`); `IDataArray2` is the step `Gain_Expt → Gain_BS`,
padded per-channel by `t_offset[i]` samples (lines 37, 53-55).
`expt_samples1 = ramp_time` (line 35), `expt_samples2` (BS hold time) is the
swept axis. Starting parameter dicts at
`Ramp_Experiments.py:96-167` — `current_calibration_gain_dict` (line 97,
±1000 DAC around previous best), `current_calibration_offset_dict`
(line 110, ±20 samples ≈ ±6 ns), `current_calibration_dict` (line 141, 1D
check). Existing `t_offset` 8-vectors live in
`Qubit_Parameters[beamsplitter_point]['t_offset']` and are pulled by
`RampBeamsplitter_Correlations.py:39-40, 64, 79, 129`.

### Calibration order

(1) `Gain_Pulse` from single-qubit Rabi (covered in section 3 of this
onboarding); (2) `Init_FF` from `Qubit_Parameters[Ramp_state]['Ramp']
['Init_FF']`; (3) `RampBeamsplitterOffsetR` for `t_offset`;
(4) `RampBeamsplitterGainR` per pair for `Gain_BS`;
(5) `RampBeamsplitterR1D` to verify clean BS oscillation, half-period =
$t_\text{BS}^{\pi/2}$. Fits write to the *live* `cfg['FF_Qubits']` only —
persisting requires a manual edit of the qubit-parameter file under
`Run_Experiments/qubit_parameter_files/`.

---

## File reference

Core ramp code (under `WorkingProjects/Triangle_Lattice_tProcV2/`,
mirrored under `triangle_lattice_quench/`):
`Helpers/RampHelpers.py` (generate_ramp:128, linear:8, cubic:32, exp:73,
three_exp:109);
`Helpers/FF_utils.py` (FFPulses:72, FFPulses_direct:9,
FFPulses_compensated:105, FFDefinitions:169, FFInvertWaveforms:218);
`Helpers/FFEnvelope_Helpers.py` (get_gains:14, StepPulseArrays:24,
CubicRampArrays:32, **CompensatedRampArrays:44**, LinearRampArrays:73,
ThreeExpRampArrays:81);
`Helpers/Compensated_Pulse_Josh.py` (Compensate:36, IIR CSVs at
`Z:\QSimMeasurements\...\_IIR_PulseCompensations`).

Program templates (`Experimental_Scripts/Program_Templates/`):
`AveragerProgramFF.py` (FFAveragerProgramV2:18, acquire_shots:38,
acquire_populations:56, acquire_population_shots:77);
`ThreePartProgram.py` (ThreePartProgramOneFF:6, ThreePartProgramTwoFF:70);
`ThreePartProgram_SweepWaveform.py` (SweepOneFF:11, SweepTwoFF:46);
`SweepWaveformAveragerProgram.py` (class:9, FFLoad16Waveforms:47,
FFPulses_arb_length_and_delay:81, FFInvert_arb_length_and_delay:99).

Experiment classes (`Experimental_Scripts/`):
`mRampExperiments.py` (BaseRampExperiment:19, RampCheckDensityCorrelations:41,
RampSweepLengthCorrelations:117, RampDurationVsPopulation:161,
FFExptVsPopulation:186, PopulationVsTime:193, PopulationVsTime_GainSweep:306);
`mRampCurrentCalibration_SSMUX.py` (Offset:11, Gain:129, 1D:183);
`mRampCurrentCalibrationR_SSMUX.py` (Base:22, OffsetR:59, GainR:66, R1D:73,
CurrentCorrelationsR:85, SweepRampLengthCorrelations:182).

Run scripts (`triangle_lattice_quench/Run_Experiments/`):
`Ramp_Experiments.py` (entry-point for ramp experiments);
`RampBeamsplitter_Correlations.py` (ramp + beamsplitter + correlations);
`9-3-25_Ramp_expts_loop.py` (per-qubit loop); `UPDATE_CONFIG.py:14-24` and
`UPDATE_CONFIG_function.py:28-38` (ramp_initial_gain ← Init_FF with
fallback to FFPulse).
