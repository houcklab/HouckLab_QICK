# Implementation plan: generic homogeneous quench on the 8-qubit triangular ladder

Source protocol: `report/2026-04-29_superconducting_triangular_ladder_generic_quench_measurement_protocol.md`.
Prior work (same hardware): `prev_work/2603.16993v1.pdf` — Molinelli, Wang, Martinez, Lowe, Osborne, Samajdar, Houck, "Chiral and bond-ordered phases in a triangular-ladder superconducting-qubit quantum simulator", arXiv:2603.16993v1 (March 2026). Reproduced ground-state physics on the device the new quench plan will reuse.

Created: 2026-04-29. Revisions: v2 (notes folded), v3 (Qblox D5a / Desq), v4 — current — fully grounded in the prior paper's measured parameters and calibration cascade. v4 also surfaces a hard constraint that v3 understated.

## 0. Constraint discovered when reading the paper

**Coupler bias (D5a) is quasi-static.** Discussion section, last page: "qubit frequencies can be tuned rapidly during an experimental sequence, whereas coupler parameters are adjusted more slowly between runs." The paper's "Outlook" lists dynamic coupler tunability as future hardware work.

This conflicts with the source protocol's Quench A (global hopping quench), which requires a sudden switch of `J̃_∥` in `tau_switch << 1/J`. On this device, the leg-coupling magnitude is set between runs by D5a voltage; we cannot move J̃_∥ during a single shot.

What we can quench dynamically:
- Qubit frequencies via QICK FF (the existing `IQArray_quench` step in `mQuenchExperiment.py:_body` already does this).
- The local rung-current kick `exp(i eta J_R)` via the calibrated rung beam-splitter (FF-domain).

What we cannot quench dynamically:
- The bare coupler parameter `J̃_∥`. Changing it requires a between-run D5a re-bias.

Implication: the implementation plan reframes the source protocol as follows.
- Quench A becomes a **detuning quench** instead of a coupling quench. Prep at one set of qubit-resonance frequencies (with `J̃_∥` set by D5a), then rapidly detune qubits via FF to suppress hopping. The ratio `J̃_∥/J` does not change at the bare level, but the *effective* hopping does because off-resonance pairs see suppressed exchange. This is physically different from the protocol's intended sudden-J quench and must be flagged in the writeup. If the strict-protocol Quench A is required, we wait for the hardware upgrade noted in the paper Outlook.
- Quench B (local kick) is **fully implementable** with the existing beam-splitter primitive.

## 1. Objective

Run the homogeneous, no-interface quench protocol from the source on the 8-qubit triangular ladder, modulo the constraint in section 0. Acceptance is the criteria from source-protocol section 9. The architecture is identical to arXiv:2603.16993v1.

## 2. Hardware reality, with paper-measured numbers

### 2.1 Lattice topology (paper Eq. 1, Fig. 1)

`N = 8` flux-tunable transmon qubits in a quasi-1D zigzag triangular ladder.

In the **paper / code convention**:
- "Rungs" = nearest-neighbor (NN) qubit pairs `(j, j+1)`. There are `N-1 = 7` rungs: (1,2), (2,3), ..., (7,8). Capacitively coupled, fixed magnitude. `J/(2π) = 6.1 MHz`.
- "Legs" = next-nearest-neighbor (NNN) pairs `(j, j+2)`, mediated by a flux-tunable transmon coupler. There are `N-2 = 6` legs: (1,3), (2,4), (3,5), (4,6), (5,7), (6,8). Tunable magnitude and sign.

In the **source-protocol convention**:
- Source "rung" + "diagonal triangular bond" = paper "rungs" (all 7 NN bonds carry the same `J`).
- Source "leg" = paper "leg" (NNN, the bond carrying the Peierls phase).
- L = 4 plaquettes.

Both conventions agree once aligned. The code uses paper convention (`rungs = ['12','23',...,'78']`, `legs = ['13','24',...,'68']`).

### 2.2 Hamiltonian (paper Eq. 1)

```
H/hbar = sum_j [ omega_j n_j + (U_j/2) n_j (n_j - 1) ]
       - sum_{j=1}^{N-1} J_j ( a†_j a_{j+1} + h.c. )
       + sum_{j=1}^{N-2} Jtilde_||,j ( a†_j a_{j+2} e^{i phi} + h.c. ).
```

Note the **sign**: the rung term is `-J`, the leg term is `+Jtilde_||`. The Peierls phase is allocated entirely to the leg.

### 2.3 Measured parameters (paper section "Device and Model" + Methods + SI tables)

- `J/(2pi) = 6.1 MHz`: rung hopping, fixed.
- `Jtilde_||/(2pi) in [2.5, 20.4] MHz` (positive) or `[-17.3, -7.0] MHz` (negative). Coupler frequency above qubit -> positive; below -> negative. **There is a gap around zero**: the device cannot reach `|Jtilde_||| < 2.5 MHz`. The paper Outlook lists closing this gap as future hardware work.
- `U/(2pi) = -186.1 MHz`: average. **Negative** — attractive Bose-Hubbard. The repulsive case is accessed via the sign-flip mapping `-H(phi, U) = H(phi + pi, -U)`.
- Idle qubit frequencies tunable `omega_q/(2pi) in [3.5, 4.4] GHz`. Operating resonance `omega_lattice/(2pi) = 3.85 GHz` or `4.30 GHz`.
- Readout resonators `omega_r/(2pi) in [7.1, 7.6] GHz` (matches `quench_readout.py`).
- T1 per-qubit, per-`Jtilde_||/J` operating point: paper SI Table reports values in the range 16-52 us; some qubits at some operating points sit close to a TLS (`T1 ~ 16-19 us`). Calibration must avoid those specific frequencies.
- `|U|/J = 30.5` at the rung scale. At the source-protocol target ratio `Jtilde_||/J = 1.5`, `|U|/Jtilde_|| ~ 20` (matches the senior-personnel note "U / J approximately 20", which referenced the leg).

### 2.4 chi mechanism (paper Eq. 1, "Device and Model")

The paper defines `phi = 0` for `Jtilde_|| > 0`, `phi = pi` for `Jtilde_|| < 0`. The sign of `Jtilde_||` flips by tuning the coupler frequency above vs below the qubit frequency. Only the two values are accessible; continuous chi requires Floquet modulation (paper Outlook), not implemented.

### 2.5 State preparation (paper section "Results", Fig. 1c)

To prepare the **ground state of the repulsive Hamiltonian at pi flux** (the physically interesting regime), the paper does:

1. Excite the **four highest-frequency qubits** (initial product state, half filling).
2. Adiabatically ramp all qubits onto the operating resonance frequency (3.85 GHz or 4.30 GHz).
3. The result is the **highest excited state of the attractive Hamiltonian at 0 flux**. By the sign-flip mapping `-H(phi, U) = H(phi+pi, -U)`, this state represents the ground state of the repulsive Hamiltonian at `phi + pi` flux.

In the existing code this maps to the `init` and `ramp` periods of `mQuenchExperiment.py:QuenchProgram._body()`. The init pulse fires the four highest-frequency qubits (`init_pulse=True`, sequential pi pulses on `qubit_ch`), and `IQArray_ramp` brings the qubits onto resonance.

### 2.6 Readout primitives (paper Fig. 2, Fig. 4, SI)

Two distinct readout sequences are needed.

**Current readout**: rotate `<a†_j a_{j+1} - a†_{j+1} a_j>` (proportional to rung current `J_j`) onto a population imbalance.
- Sequence: a single beam-splitter `H_BS,j = hbar J_j (a†_j a_{j+1} + h.c.)` for time `t_BS = pi / (4 J_j)`. This is exactly `sqrt(iSWAP)`.
- Then detune all qubits to freeze dynamics, mux readout for population.
- The relation is `J_j(0) ~ J_j ( n_j(t_BS) - n_{j+1}(t_BS) )` (paper Eq. 4), exact in the hard-core limit.

**Bond kinetic energy readout**: rotate `Re<a†_j a_{j+1}>` (kinetic energy on a bond) onto population imbalance.
- Sequence: idle period at large detuning `|Delta| >> J` for `t_idle = pi / (4 Delta)`, which rotates `x -> y` on the {|01>,|10>} Bloch sphere. Then beam-splitter at `t_BS`. Then mux readout.
- Distinct from the current readout — needed for bond-order observable, not for j_perp.

The existing `RampBeamsplitterGainR` and friends in `mRampCurrentCalibrationR_SSMUX.py` calibrate the beam-splitter gain. The specific operating point `t_BS = pi/(4J)` is a calibrated time at which the population swap fits a sinusoid with phase pi/2 (paper SI calibration cascade).

### 2.7 Hardware drive constraints

Unchanged from v3.
- One qubit drive (`qubit_ch = 9`); pulses must be sequential.
- One mux resonator drive (`res_ch = 8`); CW only (`style="const"`).
- 8 QICK FF DAC channels (one per qubit); per-channel waveform memory; can fire in parallel.
- 6 D5a DC channels (DACs 9..14) -> couplers C1..C6 -> legs (1,3),(2,4),(3,5),(4,6),(5,7),(6,8). **Slow** — set between runs.

### 2.8 Calibration cascade in the paper (SI)

Order of operations the paper SI describes; we should mirror it:

1. Single-qubit calibrations at idle frequencies.
2. Anharmonicity per qubit via `omega_12` pulse on |1>.
3. DC flux crosstalk matrix (D5a -> qubit and coupler frequencies), measured via avoided crossings.
4. Fast-flux crosstalk matrix (RFSoC FF -> qubit frequency), measured via flat-pulse spec.
5. Fast-flux filter function calibration (3 iterations) — the FF DAC has a non-flat impulse response that must be deconvolved.
6. Inter-channel pulse-delay calibration (FF waveform timing resolution = 290 ps; channels must be aligned).
7. Beam-splitter time calibration: tune `t_idle` to minimize swap contrast (current readout) or maximize swap contrast (bond kinetic energy readout). Then fine-tune frequency difference. Then fit the swap to a sinusoid for `t_BS`.
8. Readout calibration: 8000 single-shot per run, before every adiabatic-ramp run.
9. T1 / T2R measured at `omega_lattice` with all other qubits detuned away.

Most of this is already wired in the codebase (DC crosstalk, FF crosstalk, filter function, pulse-delay calibration are existing scripts I cite below). What we must NOT skip when adding the quench experiment.

## 3. Existing experiment inventory (cited)

### 3.1 J_perp and Jtilde_|| chevrons
- `Experimental_Scripts/mGainSweepQubitOscillationsR.py:GainSweepOscillationsR` (2D chevron, fits coupling rate `g`).
- Driver: `Run_Experiments/calibration_scripts/coupling_strength_calibration.py`. Iterates `pairs = rungs` (7 NN bonds) or `pairs = legs` (6 NNN bonds).

### 3.2 Coupler voltage (D5a) calibration
- `Characterization_Sweeps/mSpecVsQblox.py:SpecVsQblox`. 2D: y = D5a voltage, x = spec frequency.
- `Run_Experiments/Qblox_coupler_calib.py` driver.
- D5a init voltages: `Flux_Files/QbloxVoltageSet_8QTriangleLattice_Dictionary.py`.
- API: `Qblox.set_voltage(DACs, voltages)` in `WorkingProjects/Inductive_Coupler/Client_modules/Helpers/Qblox_Functions.py`.

### 3.3 Rung beam-splitter primitive
- `Experimental_Scripts/mRampCurrentCalibrationR_SSMUX.py:RampBeamsplitterGainR` and siblings. Composes a compensated ramp followed by a BS step at level `Gain_BS`.
- Driver: `Run_Experiments/calibration_scripts/beamsplitter_calibration.py`.
- The 50:50 operating point `t_BS = pi/(4J)` is one specific point on this calibration; small-angle (kick) is another.

### 3.4 Quench skeleton (init / ramp / quench / dynamics / readout)
- `Experimental_Scripts/quench_experiments/mQuenchExperiment.py:QuenchProgram._body()`.
- Sweep classes already present: `RampQuenchDynamics`, `RampQuenchSweepRampTime`, `RampQuenchSweepQuenchTime`, `RampQuenchFreq`, `RampQuenchRabi`.

### 3.5 Per-segment FF spec / Ramsey / drift
- `Characterization_Sweeps/mSpecVsFF.py` (`Gain_Pulse`).
- `mT1vsFF.py`, `mT1vsFF_gain_tproc_sweep.py` (`Gain_Expt`).
- `mRamseyVsFF.py`, `mRamseyVsFF_Ramp.py`, `mRamseyVsFF_CompPulse.py`.
- `mFFSpecCalibration_MUX.py` (readout-level).
- `mFluxStabilitySpec.py`, `mMultiFluxStabilitySpec.py` (drift).
- Missing: spec at `Gain_BS` and `Gain_Dynamics`.

### 3.6 Crosstalk, filter, pulse-delay (matches SI cascade)
- DC flux crosstalk + fast-flux crosstalk: `Run_Experiments/FF_crosstalk.py`, `FF_calibs.py`, `FFCompensationSpec.py`, `FFCompensationRamsey.py`.
- Filter function: `Compensated_Pulse_Josh.py` in `Helpers/`.
- Pulse-delay calibration: `Run_Experiments/FF_delay_calib.py`, `Basic_Experiments/CalibrateFFvsDriveTiming.py`.

### 3.7 Single-qubit calibration GUI
- `Run_Experiments/calibration_gui.py`. Phase 0 health-check tool.

### 3.8 Production GUI
- Desq, `MasterProject/Client_modules/Desq_GUI/sphinx/source/desq_basics.rst`.
- Extension: subclass `ExperimentClass`, set `config_template`, drop `.py` in. All existing experiment classes here are loadable via `Load Exp`.
- **All new experiments below sit in Desq.**

## 4. Hamiltonian-to-control mapping

| H term | Control | Calibrated by |
|---|---|---|
| `J_j` on 7 rungs (NN) | fixed coupler hardware; FF detuning sets the operating qubit frequencies for chevron / beam-splitter | `coupling_strength_calibration.py` with `pairs = rungs` |
| `Jtilde_||,j` on 6 legs (NNN) | D5a DC voltage on couplers C1..C6 (DACs 9..14) | `Qblox_coupler_calib.py` + chevron with `pairs = legs` |
| `phi in {0, pi}` | sign of `Jtilde_||` = which side of the coupler-vs-qubit frequency the D5a operating point sits | new: `ChiSignVerify` (paired chevron at +J and -J D5a points) |
| Per-segment qubit detuning | per-qubit FF labels `Gain_Pulse`, `Gain_Expt`, `Gain_BS`, `Gain_Dynamics`, `Gain_Readout` | existing FF-vs-segment sweeps + new `SpecVsFF_Quench`, `SpecVsFF_Dynamics` |
| `U` | transmon anharmonicity (negative, fixed) | per-qubit `omega_12` calibration |
| `<n_{R,l}>` readout | mux dispersive readout | existing |
| `<J_j>` (rung current) | calibrated 50:50 beam-splitter at `t_BS = pi/(4J)` (sqrt(iSWAP)) on rung pair, then mux readout | `RampBeamsplitterGainR` |
| `<O_j>` (bond kinetic energy) | idle at `Delta >> J` for `t_idle = pi/(4 Delta)`, then 50:50 BS, then mux | new readout sequence; primitives all exist |
| local kick `exp(i eta J_R0)` | rung beam-splitter at small angle `eta` on R0 | same calibration as 50:50 BS, different operating point |

## 5. What is genuinely missing (small list, all goes in Desq)

1. `SpecVsFF_Quench`, `SpecVsFF_Dynamics`: ports of `mSpecVsFF.py` for `Gain_BS` and `Gain_Dynamics`.
2. `ChiSignVerify`: paired chevron at +J / -J D5a points per leg bond. Asserts equal-magnitude / opposite-sign `Jtilde_||`.
3. **Bond-kinetic-energy readout sequence**: idle + BS + mux. New Desq experiment.
4. Local kick stage in `QuenchProgram._body`: applies BS at small `eta` on R0 after the ramp, before the dynamics period.
5. **Detuning-quench program**: replaces protocol's Quench A. Prep GS, then rapidly detune all qubits via FF to a far-off-resonance frequency, then read out. Documents the detuning quench is a substitute for the coupling quench.
6. ED reference for L = 4: takes `(J, Jtilde_||, phi, U)` and time-evolves on 8 sites.
7. Data pipeline: per-run `metadata.toml`, raw shots, baselines, raw complex FFT next to magnitude, FFT housekeeping. Path `data/hardware_quench/<YYYY-MM-DD>_<device>_<mode>_<L>/`.

Optional / further:
- `RampQuenchPhase`: complete `mSweepXPhase.py:NGateProgram` to sweep `quench_phase`.
- Continuous-chi via Floquet (paper Outlook). Out of scope for first run.

## 6. Phase plan

### Phase 0 - Single-qubit health
GUI auto-cal across all 8 qubits at the Phase-1 chosen `omega_lattice`. Pass criteria use the paper SI T1/T2R bands as floors. Anharmonicity per qubit via `omega_12`.

### Phase 1 - Coupler bias and bond calibration
- D5a coupler bias via `Qblox_coupler_calib.py`. Two operating points per leg: `chi = 0` (positive Jtilde_||) and `chi = pi` (negative Jtilde_||) at the protocol target ratio `|Jtilde_||/J| = 1.5`. Note device cannot reach `|Jtilde_||| < 2.5 MHz`; ratio `1.5 * 6.1 = 9.15 MHz` is comfortably inside the positive range.
- `coupling_strength_calibration.py` with `pairs = rungs` and `pairs = legs` to fix all 13 bond rates.
- New `ChiSignVerify`: confirm sign symmetry per leg.
- New `SpecVsFF_Quench`, `SpecVsFF_Dynamics`: per-qubit frequency at every FF level used in the experiment.
- DC + fast-flux crosstalk matrices via existing scripts.
- FF filter-function calibration (paper SI Fig. S4 cascade).
- Pulse-delay calibration across FF channels (paper SI 290 ps timing).
- `beamsplitter_calibration.py` to refresh `t_BS` per rung pair.

### Phase 2 - State preparation and homogeneity
- Reuse `RampQuenchBase` with `expt_samples_quench = 0` and `expt_samples_dynamics = 0`. The init + ramp prepares the state.
- Verify the four highest-freq qubits are excited by the init step (paper Fig. 1c).
- Read out `<n_{R,l}>` and `<J_j>` at chi = 0 and chi = pi. ED-compare on L = 4.
- Sanity check: `chi = 0` rung currents `<J_j>` average to zero (the time-reversal-symmetric superposition); current-current correlations are nonzero. Reproduces paper Fig. 3.

### Phase 3 - Quench primitives
- **Quench B (local kick)**: implement the kick stage in `QuenchProgram._body`. Apply BS at small `eta in {-0.10, -0.05, +0.05, +0.10}` on R0 (rung 4 -> qubit pair (4,5), or rung 3 -> (3,4)). Mandatory plus/minus pairs.
- **Detuning quench (substitute for protocol Quench A)**: prep GS, then rapidly detune qubits to off-resonance via FF amplitude switch (the existing `IQArray_quench` step). Document explicitly as detuning quench, not coupling quench.
- Verify `tau_switch` from compiled tProc timing. With `J/(2pi) = 6.1 MHz`, `1/J = 26 ns`. The FF transition must complete in much less than that — likely tight given FF filter response (paper SI Fig. S4).

### Phase 4 - Measurement and analysis
- Current readout sequence: BS at `t_BS = pi/(4J)` per rung, then mux.
- Bond-energy readout sequence: idle + BS + mux.
- Density and density-correlation derived from existing number readout.
- Pipeline writes to the `data/hardware_quench/...` path with full `metadata.toml`.

## 7. Sweep and acquisition plan

Time grid `0 <= t * J <= 10`, step `Delta t * J <= 0.05`. With `J/(2pi) = 6.1 MHz`, `t_max = 10/J ~ 260 ns`, step ~ 1.3 ns. The QICK fabric clock is 0.291 ns (`mGainSweepQubitOscillationsR.py:67`); sample 5 fabric cycles per step is fine.

Repetition delay >> max per-qubit T1 (paper SI: ~50 us). Choose ~250 us.

Shots per point: target SNR > 5 on smallest current. Set after Phase 0 fidelity table.

Quench B `eta in {-0.10, -0.05, +0.05, +0.10}`. Plus/minus pairs mandatory (sanity check 3 of source-protocol section 8).

Detuning-quench (Quench A substitute): two final detunings producing different effective hopping-suppression ratios. Document as such.

No-quench baseline: same time grid, no quench applied. Run with the same timing sequence as the quenched runs.

## 8. Risks

- **Couplers are slow.** Source-protocol Quench A (sudden change of `Jtilde_||/J`) is not directly implementable. We substitute with detuning quench and document the difference. If strict Quench A is required, wait for the hardware upgrade noted in the paper Outlook.
- **`Jtilde_|| = 0` is not reachable** due to the device's coupler-tunability gap. Quenches that pass through `Jtilde_|| = 0` are out of scope.
- **TLS dips** in T1 at specific qubit operating frequencies. Phase 0 must blacklist those frequencies; if `omega_lattice` lands on a dip, choose the alternate (3.85 vs 4.30 GHz).
- **Sequential qubit pulses** limit init complexity. The init step fires 4 sequential pi pulses on `qubit_ch` (paper convention).
- **Fast-flux filter response** (paper SI Fig. S4) is non-trivial; the filter calibration must be re-run if the operating point or pulse shapes change.
- **Pulse-delay across FF channels** (290 ps timing) — every simultaneous FF segment needs the delay calibration alive.
- **Soft-core leakage** (`|U|/J ~ 30`): not strictly hard-core. Number conservation per sanity check 5 is mandatory.
- **Beam-splitter t_BS drift** over the 1 us evolution window. Re-run BS calibration before and after; interleave if drift exceeds tolerance.

## 9. Open questions for senior personnel

1. **Quench-A substitute**. Detuning quench acceptable as the first-run Quench-A analogue, or do we wait for dynamic coupler hardware? Without an answer, I plan around detuning quench and flag it in the writeup.
2. **omega_lattice choice**. 3.85 GHz or 4.30 GHz? Phase 0 T1 tables pick one; need confirmation.
3. **Local-kick rung R0**. Most central rung is (4,5) (rung index 4 in the paper convention) since the 7 NN rungs go (1,2),(2,3),(3,4),(4,5),(5,6),(6,7),(7,8). Confirm.
4. **chi gauge handedness**. Paper allocates the entire Peierls phase to the leg. With sign-flip on D5a, do we sign-flip every leg coupler simultaneously, or alternate? Source-protocol gauge has `exp(-i chi)` on leg-1, `exp(+i chi)` on leg-2; on the device with all 6 legs sharing one phase (chi or 0), this gauge has to be re-derived.
5. **Path token convention**. `<device>` and `<mode>` strings.

## 10. Concrete next actions

In order:

1. Run calibration GUI auto-cal at `omega_lattice` candidates; pick the one without TLS dips on critical qubits.
2. Anharmonicity per qubit via `omega_12`.
3. DC + FF crosstalk matrices, FF filter calibration, pulse-delay calibration (existing scripts, all need a current snapshot).
4. `Qblox_coupler_calib.py` per leg; choose D5a operating points for `Jtilde_||/J = +/- 1.5`.
5. `coupling_strength_calibration.py` with `pairs = rungs` then `pairs = legs`.
6. `ChiSignVerify`, `SpecVsFF_Quench`, `SpecVsFF_Dynamics` (ports, ~20-30 lines each).
7. `beamsplitter_calibration.py` to refresh `t_BS = pi/(4J)` per rung pair.
8. Build the bond-kinetic-energy readout sequence (idle + BS + mux).
9. Implement the local-kick stage in `QuenchProgram._body`; test on a single rung pair.
10. Build the detuning-quench program (Quench A substitute).
11. ED reference for L = 4. Audit prepared state at chi = 0 and chi = pi.
12. First end-to-end local-kick run with `eta in {+/-0.05, +/-0.10}`. No-quench baseline first.
13. First end-to-end detuning-quench run.

## 11. Deferred

- Strict Quench A (coupler-amplitude quench): waits for dynamic coupler hardware.
- Continuous chi: requires Floquet modulation (paper Outlook).
- Interface scattering experiments.
- Disorder-averaged runs.
- Multi-rung simultaneous kicks.

## Changelog

- v1: assumed L = 4 vertical rungs, hard-core encoding, beam-splitter primitive missing.
- v2: corrected lattice topology (8 qubits, 7 NN rungs + 6 NNN legs), `|U|/J ~ 20`, J_rung calibration and 2-qubit chevrons exist, hardware constraints, chi via sign of Jtilde_||, BS primitive exists.
- v3: corrected J-tunability mechanism (D5a on leg couplers, not per-qubit FF). All future development on Desq. "pi/4 BS" replaced by "calibrated 50:50 BS".
- v4 (current): folded prior-paper specifics — `J/(2pi) = 6.1 MHz`, `Jtilde_|| in [2.5, 20.4]` or `[-17.3, -7.0]` MHz with a gap around zero, `U/(2pi) = -186.1 MHz` (negative; repulsive accessed via sign-flip mapping), state-prep is "highest excited state of attractive H at 0 flux = ground state of repulsive H at pi flux", `t_BS = pi/(4J)`, separate readout sequences for current vs bond kinetic energy, paper SI calibration cascade (anharmonicity, DC crosstalk, FF crosstalk, filter function, pulse delay, BS time fitting). **Surfaced the constraint that couplers are slow (between runs); source-protocol Quench A is not directly implementable on this device, replaced by detuning quench.**
