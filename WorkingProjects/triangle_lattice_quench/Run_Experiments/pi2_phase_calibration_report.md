# Measurement π/2 Phase Calibration for the Mott-Quench Protocol

**Scope.** Three new experiment classes in `Experimental_Scripts/quench_experiments/mSweeppi2Phase.py`, a run script (`pi2_phase_calibration.py`), and a dedicated **Pi/2 Phase Calib** tab in `CALIBRATION_GUI.py`. This document explains what the calibration is for, what each of the three variants measures, and how to read the results.

Assumed background: Bloch sphere, π and π/2 rotations, basic state tomography, the QICK / `build_config` flow.

---

## 1. Why we need this calibration

The Mott-quench protocol (`mMottQuench.py`) prepares a six-qubit initial state, evolves it under a fast-flux ramp, and reads out populations. Concretely, in `_body`:

1. **Init** — every qubit gets a π pulse *except* the qubit at `pi2_init_index`, which gets a π/2 (the "superposition seed"). With your usual setup that's qubit 6 (index 3 in `[3,4,5,6,7,8]`).
2. **Dynamics** — a fast-flux ramp brings the qubits into resonance, where they swap via XY exchange. The seed qubit's superposition spreads coherently across the lattice.
3. **Measurement** — a *second* π/2 is applied to **every** qubit (`qubit_measurement_pi2_{i}`) immediately before readout, with phase `measurement_pi2_phase`. Then a resonator readout collects populations.

The role of that final π/2 is a basis rotation: readout natively measures ⟨σ_z⟩, but the interesting information in a quench is in the *coherence*, i.e. ⟨σ_x⟩ and ⟨σ_y⟩. A π/2 about an in-plane axis at azimuth φ rotates ⟨σ_φ⟩ → ±⟨σ_z⟩ so it can be read. So the **phase of that final π/2 sets the measurement quadrant**.

### Where the calibration need comes from

The qubit drive frame is fixed by `qubit_freqs[i]` (calibrated at the readout-point bias). During the FF ramp/dynamics, each qubit's instantaneous frequency departs from that frame, so by the time the measurement π/2 fires, each qubit has accumulated a dynamical phase

$$\phi_i(t)=\int_0^{t}\!\big(\omega_i(\tau)-\omega_{\text{drive},i}\big)\,d\tau$$

on top of whatever phase the XY swap produced. If `measurement_pi2_phase` doesn't absorb $\phi_i$, the final π/2 projects onto a *rotated* mix of ⟨σ_x⟩/⟨σ_y⟩ — you measure the wrong thing. The original `mott_quench_basic.py` script already noted this in its docstring: *"Doesn't account for phase evolution, so meant to be a foundation for tests of these concepts."*

### What "the right phase" looks like

Sweep `measurement_pi2_phase` φ over `[0°, 360°)` while keeping everything else fixed; the population traces a sinusoidal fringe

$$P_e(\varphi)=C+A\cos(\varphi-\varphi_0)\,.$$

Three features fall out, each diagnosing something different:

| Feature | Reads out | Interpretation |
|---|---|---|
| **Amplitude $A$** | π/2 **contrast** × coherence visibility | Maximized at θ = π/2 (correct rotation angle). Drops with decoherence or under/over-rotation. |
| **Peak phase $\varphi_0$** | **dynamical + swap-accumulated phase** | The phase you need to *lock in* for measurement. Depends on dynamics duration. |
| **Vertical offset $C$** | rotation-**angle** error | $C\approx 0.5$ for a clean π/2. Deviation says the pulse isn't actually π/2. |

The three calibration classes give you these features in different scope.

---

## 2. The fit (reused, not reinvented)

All three variants pipe their data through `fit_beamsplitter_offset` from `Helpers/Beamsplitter_Fit.py` — the same routine that fits the two-qubit chevron sinusoid in the BSClean calibration. It does:

- Multi-start `curve_fit` to the model $A\,e^{-\gamma(x-x_0)}\sin(wx+\varphi)+C$.
- FFT- and extrema-based initial frequency guesses, bounded fit, multiple seeds → picks the best by residual.
- Returns `popt = (A, w, φ, C, γ)` per readout, `perr`, `r_squared`, plus reconstructor metadata.

For a phase fringe on degrees, $w$ should converge near $2\pi/360 \approx 0.0175\,\text{rad/deg}$ (one period over a full sweep). The `γ` decay parameter should ride at ~0 — phase is cyclic so there's no real decay along the axis; γ exists in the model only because the chevron pipeline needs it for the wait-time axis.

`analyze()` writes the fit dict straight into `data['data']` so the values are saved alongside the IQ.

---

## 3. The three calibration variants

All three live in `mSweeppi2Phase.py` and obey the same input convention: `swept_qubit` is **1-based** (the qubit's position in `Qubit_Pulse`, so `swept_qubit-1` indexes `qubit_phases_matrix` / `measurement_pi2_phases`).

### Variant A — `SweepPi2Phase` (bare two-π/2 sanity check)

**What it does.** Plays two sequential π/2 pulses on one qubit (the `swept_qubit`), with no FF dynamics in between. The first π/2 has phase 0; the second has the swept phase. Gains for both pulses default to `qubit_gains/2` read directly from the JSON via `build_config` (the same path `mMottQuench` uses for its π/2 gain), so there is no separate hand-typed gain to maintain.

**What it calibrates.** The **pulse-pair phase reference and π/2 contrast** of one qubit, decoupled from any dynamics:

- $A$ = π/2 amplitude / contrast → tells you whether your gain is right.
- $\varphi_0$ = pulse-pair phase reference (electronics frame; no dynamical contribution).
- $C$ → angle error.

This is a pure Ramsey-style $\pi/2 - \pi/2$ fringe. Useful as a **sanity check** before you trust the more complicated variants — if Variant A doesn't give a clean fringe, none of the others will either.

**Limitations.** Says nothing about the swap-accumulated phase — for that, use Variants B.

### Variant B 1D — `MottQuenchPi2Phase` (full sequence at one dynamics time)

**What it does.** Runs the *full* Mott-quench `_body` (init π's on five qubits + prep π/2 on the seed + FF ramp + dynamics + measurement π/2 + readout), with `expt_samples` held fixed and only `measurement_pi2_phases[swept_qubit-1]` swept. Other qubits' measurement phases are zero by default; the array lives on `cfg['measurement_pi2_phases']` (per-qubit list, replacing the original scalar `measurement_pi2_phase` that couldn't represent per-qubit axes).

**What it calibrates.** The **measurement quadrant for the swept qubit at that specific dynamics time**:

- $\varphi_0$ now contains the **dynamical + swap-accumulated phase** — i.e. the actual offset you need to load into `measurement_pi2_phases[swept_qubit-1]` for honest coherence readout.
- $A$ tells you whether the coherence has survived to the chosen `expt_samples` (it decays with $T_2$ and with how much the swap has dispersed the excitation).
- $C\neq 0.5$ here is a more interesting signal — it can mean either an angle-error in the pulse or that the swap has redistributed population away from this qubit (the offset is no longer a pure pulse property once dynamics is in the loop).

**Use this when.** You want to **calibrate `measurement_pi2_phases` for the actual experiment configuration you intend to run** — pick the `expt_samples` of the run you care about, do the phase sweep, set `measurement_pi2_phases[swept_qubit-1] = φ₀`.

### Variant B 2D — `MottQuenchPi2Phase2D` (phase × dynamics-time map)

**What it does.** Same Mott sequence, but 2D: `x_key = expt_samples` (dynamics duration), `y_key = ('measurement_pi2_phases', swept_qubit-1)`. The output is a heatmap `Z(t, φ)` per readout — a chevron-like fringe pattern with phase rolling as a function of dynamics time.

**What it calibrates.** The **trajectory $\varphi_0(t)$** — i.e. how the dynamical phase grows with dynamics time:

- For each dynamics time slice, the sinusoid has its own peak phase. Plotted vs $t$, the peak phase walks linearly (slope = average detuning during the ramp) plus structure from the swap.
- The fit (run on the full 2D Z) extracts the best-wait column and reports a single $\varphi_0$, but the heatmap itself is the primary product — you read $\varphi_0(t)$ off the colormap.
- Amplitude vs $t$ shows the **coherence-decay envelope** of the swept qubit through the dynamics — effectively a $T_2$-like measurement under the actual quench drive.

**Use this when.** You want a **closed-form phase correction** to feed forward (e.g. "set `measurement_pi2_phase = a + b·expt_samples`" for analyses that scan dynamics time), or when you want to see at a glance whether the swap has visible structure in the phase.

---

## 4. Three things worth knowing before you run

**(i) Two-quadrature alternative.** The original `mott_quench_basic.py` already loops `pi2_phase ∈ {0, 90}` — that's a two-quadrature reconstruction: from $P_e$ at 0° and 90° you can recover both magnitude $\sqrt{P_0'^2+P_{90}'^2}$ (no phase to calibrate) and phase $\mathrm{atan2}(P_{90}', P_0')$. If you only care about magnitude, you can skip the calibration entirely and use that. The phase sweep here is the **finer-grained** version: a clean cosine fit gives you the same magnitude **and** phase plus a goodness-of-fit, which the two-point reconstruction can't.

**(ii) The 0-based / 1-based collision.** `pi2_init_index` is 0-based ("which position in `Qubit_Pulse` gets the prep π/2") while `swept_qubit` is 1-based ("which position's measurement phase is swept"). To calibrate the qubit you actually prepared, set `swept_qubit = pi2_init_index + 1`. The GUI's "Link swept = init+1" checkbox does this automatically and is on by default.

**(iii) Global vs per-qubit phase.** The original `measurement_pi2_phase` in `mMottQuench.py` was a single scalar applied to every qubit's measurement π/2 — fine for symmetric observables, wrong for per-qubit tomography because each qubit accumulates a different $\phi_i$. The new code stores `measurement_pi2_phases` as a length-`n_qubits` list, so the calibration value you extract is per-qubit and stays per-qubit. Other qubits' phases default to 0 if you don't fill them in.

---

## 5. How to run

### From the GUI (recommended)

1. Open `CALIBRATION_GUI.py`. Connect to the RFSoC and load a `qubit_parameters.json`.
2. Go to the **Pi/2 Phase Calib** tab.
3. Top row: pick `Readout group`, `Drive group`, and (for Variants B) `Ramp_State` + `Dynamics_Point` — same selectors as the Two-Qubit Calib tab.
4. Pick the variant in the dropdown — the parameter form below it swaps to match.
5. Set `pi2_init_combo` to the prep qubit; leave "Link swept = init+1" checked so the swept qubit matches.
6. Fill the sweep parameters (`phase_*`, plus `expt_samples` for B 1D or `samples_*` for B 2D) and **Run**.
7. Watch the canvas — 1D variants draw a line plot with the fitted sine overlay; 2D draws a heatmap. The result label shows the fitted $\varphi_0$, $A$, and $R^2$ for the swept readout.

### From a script

`pi2_phase_calibration.py` is structured exactly like `mott_quench_basic.py`. Three `run_*` flags toggle which variant fires, three matching `_dict`s hold the sweep parameters, and the cfg comes from the same `build_config(...) | characterize_readout(...)` path. No hand-rolled gains or phases — the JSON is the source of truth.

---

## 6. What gets recorded

After `acquire()` returns, the `analyze()` hook attaches the fit results to `data['data']`:

| Key | Shape | Meaning |
|---|---|---|
| `popt` | `(R, 5)` | Per-readout `(A, w, φ, C, γ)`. |
| `perr` | list of `(5,)` | 1σ errors from the covariance. |
| `r_squared` | `(R,)` | Goodness of fit, per readout. |
| `offset_sorted` | `(O,)` | The swept phase axis (deg). |
| `best_wait_idx` | `(R,)` | For 2D: which `expt_samples` column the fit picked. |
| `swept_qubit` | int | The qubit whose measurement phase was swept (1-based). |

Pull `popt[ro_idx][2]` for the calibrated phase (where `ro_idx = Qubit_Readout.index(qubit_pulse[swept_qubit-1])`) and write it into the next run's `measurement_pi2_phases` array.

---

## 7. Where to look in the code

| File | What lives there |
|---|---|
| `Experimental_Scripts/quench_experiments/mSweeppi2Phase.py` | The three experiment classes + the program that swaps in the per-qubit phase array. |
| `Experimental_Scripts/quench_experiments/mMottQuench.py` | The base Mott-quench program (`MottQuenchBasicProgram`) we inherit from. |
| `Helpers/Beamsplitter_Fit.py` | `fit_beamsplitter_offset` — the shared sinusoid fitter. |
| `Run_Experiments/pi2_phase_calibration.py` | Script-driven entry point. |
| `Run_Experiments/CALIBRATION_GUI.py` | `Pi2PhaseCalibTab` (~line 6750) + `Pi2PhaseWorker` (~line 6248). |

The fit, the sweep engine, the cfg builder, and the program body are all reused — the new code is just the three sweep classes and one program override (`_initialize` swapping a scalar phase for a per-qubit list), plus the GUI tab.
