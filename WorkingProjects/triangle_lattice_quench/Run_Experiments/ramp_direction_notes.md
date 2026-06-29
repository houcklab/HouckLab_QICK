# Ramp Direction: Why It Matters for the Quench Experiment

The choice of detune-DOWN-and-ramp-UP vs. detune-UP-and-ramp-DOWN is not cosmetic. It selects **which eigenstate of the on-resonance Hamiltonian you prepare**, and therefore which sector of the spectrum your quench probes.

---

## 1. The Hamiltonian after the ramp

When all the ramping qubits are on resonance, the active sector behaves (to leading order) as a hopping Hamiltonian on the qubit lattice:

$$
H \;=\; -J \sum_{\langle i,j\rangle} \big(b_i^\dagger b_j + \text{h.c.}\big) \;+\; (\text{interactions})
$$

For a 5-site chain (Q3, Q4, Q6, Q7, Q8) with one excitation, the spectrum spreads into a **band** of $N$ delocalized eigenstates indexed by quasi-momentum $k$:

$$
E_k \;=\; -2J\cos k, \qquad k \in \{k_1, k_2, \ldots, k_N\}
$$

- **Bottom of band** (lowest energy, $k \approx 0$): bonding / "symmetric" / superfluid-like — all sites in phase.
- **Top of band** (highest energy, $k \approx \pi$): antibonding / "staggered" — alternating signs site to site.
- **Middle**: intermediate $k$ states.

---

## 2. What the $\pi$ pulses prepare *before* the ramp

While the $\pi$-pulse qubits are detuned by $\Delta$ from the others, the $\pi$ pulses prepare a **product state** like

$$
|\psi_0\rangle \;=\; |1\rangle_{Q3} \otimes |0\rangle_{Q4} \otimes |1\rangle_{Q6} \otimes |1\rangle_{Q7} \otimes |0\rangle_{Q8}
$$

This is **not** an eigenstate of the resonant Hamiltonian. It has overlap with every band state simultaneously — analogous to how a position-basis state has overlap with every momentum eigenstate.

---

## 3. What the adiabatic ramp does

The ramp turns on the effective hopping $J$ slowly while sweeping the detuned qubits' bare energies toward resonance. By the adiabatic theorem, each instantaneous eigenstate of $H(t)$ evolves continuously into the corresponding eigenstate at the new parameter — **as long as gaps don't close**.

The key question: at $|\Delta| \gg J$, where does the product state sit in the energy spectrum?

### Detune DOWN ($\Delta < 0$)

The bare $|1\rangle$ excitations sit at **low** energy (their bare frequencies are below resonance). At large $|\Delta|$, the joint product state $|\psi_0\rangle$ is among the lowest-energy levels of the full $H(\Delta)$. Adiabatic ramp UP to resonance then connects $|\psi_0\rangle$ to the **bottom of the band**:

$$
|\psi_0\rangle \;\xrightarrow{\text{ramp UP, adiabatic}}\; |k \approx 0\rangle \quad \text{(bonding, superfluid-like)}
$$

### Detune UP ($\Delta > 0$)

The bare $|1\rangle$ excitations sit at **high** energy. At large $|\Delta|$, $|\psi_0\rangle$ is near the top of the spectrum of $H(\Delta)$. Adiabatic ramp DOWN connects it to the **top of the band**:

$$
|\psi_0\rangle \;\xrightarrow{\text{ramp DOWN, adiabatic}}\; |k \approx \pi\rangle \quad \text{(antibonding, staggered)}
$$

**Intuition in one line**: $\Delta$ sets where the excited qubits sit relative to the rest. The ramp slowly mixes them in, and energy ordering is preserved adiabatically.

---

## 4. What this means physically for the quench spectral function

The QSF is the Fourier transform of post-quench correlations:

$$
S(k, \omega) \;=\; \int dt\, dx \; e^{i(\omega t - kx)} \; \langle \psi_0 | \, c_x^\dagger(t)\, c_0(0) \, | \psi_0 \rangle
$$

The signal depends entirely on what state $|\psi_0\rangle$ you started in:

- Start in the **bottom of band** ($k \approx 0$, superfluid) and quench by turning on Q5 → you populate the bonding sector. Spectral weight sits at low $k$, and you map out the dispersion as Q5 injects momentum.
- Start in the **top of band** ($k \approx \pi$, staggered) and quench → you populate the antibonding sector. Spectral weight sits at high $k$. This is *different physics* — think repulsive Bose-Hubbard at negative temperature.

So choosing the ramp direction = choosing **which row of $S(k, \omega)$ you populate**, and consequently what the dynamics look like. **These are not equivalent measurements**: they probe different sectors of the same dispersion.

---

## 5. The $H \to -H$ symmetry

The legacy file's comment about `Init_4815_FF_lowest` is invoking a symmetry argument:

$$
H \;\longleftrightarrow\; -H \qquad \Longleftrightarrow \qquad \text{(lowest state)} \;\longleftrightarrow\; \text{(highest state)}
$$

For a hopping Hamiltonian, $-H$ corresponds to flipping the sign of $J$:

$$
H \;=\; -J\sum (b_i^\dagger b_j + \text{h.c.}) \qquad\longleftrightarrow\qquad -H \;=\; +J\sum (b_i^\dagger b_j + \text{h.c.})
$$

which is physically equivalent to a momentum shift $k \to k + \pi$ (gauge transformation on the bipartite lattice). So the "highest of $H$" prep is exactly the "ground of $-H$" prep — you can simulate negative-hopping physics by preparing the top of the band and watching its evolution under $+J$ hopping.

That is why both options exist in the legacy code: they cover **two different regimes of the same device**, accessed by changing only the ramp direction.

---

## 6. Summary table

| Direction | Init detuning | Ramp | Prepares | Physics regime |
|---|---|---|---|---|
| **Down → Up** | $\Delta < 0$ (e.g. $-6000$ FF) | UP onto resonance | $\lvert k \approx 0 \rangle$, bonding | Superfluid ground state of $H$ |
| **Up → Down** | $\Delta > 0$ (e.g. $+5000$ FF) | DOWN onto resonance | $\lvert k \approx \pi \rangle$, antibonding | Highest excited state of $H$ = ground of $-H$ |

### Legacy default in this codebase

`Qubit_Parameters.py:333` sets `Ramp_state = '8Q_4815'`, which maps to `Init_4815_FF` → **Down-and-ramp-Up** → prepares the **lowest band state** (the project's historical default).

### Which to pick for your QSF experiment

- Standard "superfluid quench" — pre-quench state is the bonding ground state of on-resonance $H$, quench by jumping Q5 onto resonance: **Down → Up**.
- Want the *highest* excited state of on-resonance $H$ (staggered correlations, inverted-$J$ physics): **Up → Down**.

Both are real, well-defined initial states. The choice picks which physical regime the post-quench spectral function is exploring.

---

## 7. A third option: ramp from BOTH sides to the middle

Instead of treating all detuned qubits as one group, split them into two sublattices and ramp them toward the same target frequency $f_{\text{res}}$ (the "middle"):

$$
\text{Group A (initially UP):} \quad \Delta_i > 0, \quad i \in A
$$

$$
\text{Group B (initially DOWN):} \quad \Delta_i < 0, \quad i \in B
$$

Both groups ramp adiabatically toward the same $f_{\text{res}}$. What state you prepare depends on the **pattern** of which sites went up vs. down — not on the magnitudes individually.

### Alternating sublattices (the most useful case)

If A and B form the two sublattices of a bipartite chain (e.g. $A$ = even sites, $B$ = odd sites), then at large $|\Delta|$ the single-particle eigenstates of $H(\Delta)$ are localized on individual sites with a definite energy ordering: $A$-sites near $+|\Delta|$, $B$-sites near $-|\Delta|$. The product state $|\psi_0\rangle$ created by the $\pi$ pulses lives in this energy-stratified basis.

As $|\Delta| \to 0$, adiabatic evolution maps each bare site state onto the corresponding momentum state, **but with the bipartite phase factor baked in**. The result has definite **staggered** character:

$$
|\psi_{\text{ramp}}\rangle \;\propto\; \prod_{i \in \text{driven}} \big(b_i^\dagger \, e^{i\pi x_i}\big) |0\rangle
\;\sim\; |k = \pi/2\rangle\text{-like superposition}
$$

So a "ramp from both sides to the middle" with alternating sublattices selects an initial state **somewhere in the middle of the band**, with quasi-momentum near $k = \pi/2$ — neither the bonding $k = 0$ state nor the antibonding $k = \pi$ state.

### Why this is useful for QSF

For the quench spectral function, the initial state determines which slice of $S(k,\omega)$ lights up:

- All-down → bonding: spectral weight at $k \approx 0$.
- All-up → antibonding: spectral weight at $k \approx \pi$.
- **Alternating up/down → mid-band: spectral weight at $k \approx \pi/2$.**

That last option is often what you want for QSF, because the $k \approx \pi/2$ states have the steepest dispersion $|\partial E/\partial k|$. Quench excitations then propagate at *maximum* group velocity, producing the cleanest light-cone / Lieb-Robinson signal. Several published quench-dynamics protocols use this trick for exactly that reason.

### Equivalence to a sublattice gauge transformation

Mathematically, alternating detunings $\Delta_i = (-1)^i \Delta$ on a bipartite lattice are gauge-equivalent to applying a $\pi$-phase rotation on one sublattice — i.e. they shift the momentum origin by $\pi$:

$$
b_i \;\to\; e^{i\pi x_i} \, b_i \quad\Longleftrightarrow\quad k \;\to\; k + \pi
$$

So "up-and-down to middle" is exactly the "down-and-up" protocol *in the rotated frame* where the band minimum has been shifted from $k = 0$ to $k = \pi/2$.

### Updated summary table

| Direction | Init pattern | Ramp | Prepares | QSF spectral weight |
|---|---|---|---|---|
| **Down → Up** | $\Delta_i < 0$ for all driven $i$ | UP onto resonance | $\lvert k \approx 0 \rangle$ bonding | low $k$ |
| **Up → Down** | $\Delta_i > 0$ for all driven $i$ | DOWN onto resonance | $\lvert k \approx \pi \rangle$ antibonding | high $k$ |
| **Both → Middle** | $\Delta_i = (-1)^i \Delta$, staggered | Both groups → $f_{\text{res}}$ | $\lvert k \approx \pi/2 \rangle$ mid-band | mid $k$, maximum group velocity |

### Implementation note

The FF infrastructure already handles this. Each qubit's `Gain_RampInit` is independent, and `IQArray_ramp` builds a per-channel ramp from `Gain_Pulse → Gain_RampInit → Gain_Expt` per qubit. So we just assign:

- Group A qubits: `Gain_RampInit = Gain_Expt + offset` (start above)
- Group B qubits: `Gain_RampInit = Gain_Expt - offset` (start below)

with all qubits sharing the same `Gain_Expt` target. No code changes — only configuration.

### Picking the pattern for our 5-qubit chain (Q3, Q4, Q6, Q7, Q8)

The natural staggering for a 1D bipartite chain is

$$
\text{Up}: \{Q3, Q6, Q8\}, \qquad \text{Down}: \{Q4, Q7\}
$$

or its complement. The driven qubits Q3, Q6, Q7 then split: two start UP (Q3, Q6) and one starts DOWN (Q7), giving a mixed-momentum initial product state that adiabatically connects to the mid-band sector.
