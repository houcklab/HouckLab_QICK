# Measurement protocol: generic quench on a superconducting triangular Bose-Hubbard ladder

Date: 2026-04-29

Scope: first homogeneous, no-interface quench experiment on the superconducting triangular-ladder simulator. This protocol is intended to validate the hardware, readout, quench operators, and data pipeline before moving to phase-boundary/interface scattering.

## 1. Hamiltonian convention

Use the two-leg triangular Bose-Hubbard ladder

```text
H =
-J_parallel sum_R [
    exp(-i chi) bdag_{R,1} b_{R+1,1}
  + exp(+i chi) bdag_{R,2} b_{R+1,2}
  + h.c.
]
-J_perp sum_R [
    bdag_{R,1} b_{R,2}
  + bdag_{R+1,1} b_{R,2}
  + h.c.
]
+ (U/2) sum_{R,l} n_{R,l}(n_{R,l}-1).
```

Use `J_perp` as the energy unit. Report all times in `1/J_perp`.

Gauge convention:

- Leg 1 hopping phase: `exp(-i chi)`.
- Leg 2 hopping phase: `exp(+i chi)`.
- Rung and diagonal triangular bonds: real hopping `J_perp`.
- Rung index: `R = 1,...,L`.
- Leg index: `l = 1,2`.

Do not change this convention between simulation and hardware analysis. A sign error in `chi` or in the rung-current definition will flip the physics.

## 2. First hardware parameter set

Start with a homogeneous ladder, no interface.

Recommended first run:

| quantity | value |
|---|---:|
| rungs | `L = 12`, if available |
| sites | `2L = 24` |
| filling | half filling, `N = L` bosons/excitations |
| `J_perp` | hardware reference coupling |
| `J_parallel/J_perp` | `1.5` |
| `chi` | `pi` |
| `U/J_perp` | native hard-core or large-`U` value |
| boundary | open |
| evolution window | `0 <= t J_perp <= 10` |
| sampling | `Delta t J_perp <= 0.05` preferred |

Also run a trivial control at `chi = 0`, with the same `J_parallel/J_perp`, to check the current readout and gauge signs.

## 3. State preparation

Prepare the ground state, or the lowest experimentally reachable adiabatic state, of the homogeneous Hamiltonian `H0`.

Recommended preparation route:

1. Initialize the desired total excitation number, ideally half filling.
2. Start from a large-detuning or weak-coupling product state.
3. Adiabatically ramp to the target `J_perp`, `J_parallel`, `U`, and `chi`.
4. Hold briefly to let fast transients settle.
5. Measure the ground-state baseline before any quench.

Baseline observables to record:

```text
<n_{R,l}>,
<j_perp(R)>,
<j_parallel,l(R)>,
<n_{R,1} - n_{R,2}>.
```

The no-quench baseline must be repeated with the same timing sequence used for the quenched experiment.

## 4. Quench protocols

Run two generic quenches.

### A. Global hopping quench

This reproduces the spirit of the original quench experiment.

Prepare the ground state of `H_i`, then suddenly switch to `H_f`:

```text
J_parallel,i / J_perp = 1.5
J_parallel,f / J_perp = 1.35
```

For a stronger first signal, use

```text
J_parallel,f / J_perp = 1.2.
```

Keep `U`, `J_perp`, and `chi` fixed.

The switch time must satisfy

```text
tau_switch << 1/J_perp.
```

Measure density and current dynamics after the switch.

### B. Local rung-current kick

This matches the current interface-quench direction, but in a homogeneous system.

Choose a central rung `R0 = L/2`, or `R0 = L/2 + 1` if the hardware layout makes that cleaner.

Apply

```text
|psi(0+)> = exp(i eta j_perp_hat(R0)) |psi0>,
```

with

```text
j_perp_hat(R)
= -i J_perp [bdag_{R,1} b_{R,2} - bdag_{R,2} b_{R,1}].
```

Use at least

```text
eta = +0.05, -0.05, +0.10, -0.10.
```

The `eta -> -eta` pair is mandatory. The odd-in-`eta` response checks the rung-current sign convention and isolates the linear response.

## 5. Measurement channels

For each evolution time `t_m`, repeat the experiment many shots and measure the following.

### Required

1. Site occupation:

```text
n_{R,l}(t)
```

from standard number-state readout.

2. Rung current:

```text
j_perp(R,t)
= -i J_perp [
    <bdag_{R,1} b_{R,2}>
  - <bdag_{R,2} b_{R,1}>
].
```

Measure this by a calibrated two-mode interference or beam-splitter readout on each rung before number measurement.

3. Density imbalance:

```text
Delta n_R(t) = n_{R,1}(t) - n_{R,2}(t).
```

### Strongly recommended

4. Leg currents:

```text
j_parallel,l(R,t)
```

using pair-interference readout on leg bonds.

5. Connected density correlations:

```text
C_nn(i,j;t) = <n_i(t)n_j(t)> - <n_i(t)><n_j(t)>.
```

This is especially important for comparing to the original global-quench QSF.

## 6. Data products

For every parameter point, save:

- `metadata.toml`.
- Raw shot records or shot histograms.
- Calibrated `<n_{R,l}(t)>`.
- Calibrated `<j_perp(R,t)>`.
- Calibrated `Delta n_R(t)`.
- No-quench baseline traces.
- `eta = +eta0` and `eta = -eta0` traces.
- Hardware calibration table: `J_perp`, `J_parallel`, `U`, `chi`, disorder, decoherence rates.
- Exact pulse sequence and timestamps.

Use a path convention like:

```text
data/hardware_quench/<YYYY-MM-DD_HHMM>_<device>_<mode>_<L>/
```

## 7. Analysis pipeline

For local quench data, form baseline-subtracted one-point signals:

```text
delta O(R,t) = O_quench(R,t) - O_no_quench(R,t).
```

For current-kick data, also form the odd response:

```text
delta O_odd(R,t) = [O_{+eta}(R,t) - O_{-eta}(R,t)] / 2.
```

Then compute the quench spectral function by a space-time FFT:

```text
S_O(k,omega) = |FFT_{R,t}[w_R w_t delta O(R,t)]|.
```

Use Hann windows in space and time. Save both raw complex FFT data and magnitude-normalized plots. Do not only save normalized images.

For global quench data, compute QSFs from connected two-point observables, especially density-density correlations.

## 8. Mandatory sanity checks

Before treating the data as physics:

1. No-quench check: dynamics should be flat up to decoherence and residual calibration drift.
2. Gauge check: at `chi = 0`, equilibrium rung currents should be near zero in the homogeneous system.
3. Current sign check: `eta -> -eta` must flip the odd current response.
4. Linearity check: compare `eta = 0.05` and `eta = 0.10`. Linear-response amplitudes should scale approximately by 2 before normalization.
5. Particle-number check: number-conserving kicks should preserve total excitation number within readout error.
6. Two-site calibration: isolated rung dynamics must reproduce the measured `J_perp` and the sign of `j_perp`.
7. Small-system benchmark: run ED or trusted TEBD for the actual `L`, `J`, `U`, `chi`, and pulse parameters used in hardware.
8. FFT check: report `Delta omega = 2pi/T`, `omega_Nyquist = pi/Delta t`, and effective `Delta k`.

## 9. Acceptance criteria for the first generic run

The first generic quench experiment is successful if:

- The calibrated Hamiltonian parameters match target values within stated error bars.
- The no-quench control is stable.
- The `eta -> -eta` current response flips sign.
- Density and rung-current light cones are visible above noise.
- The measured QSF peak structure agrees with ED or TEBD within finite-size and decoherence limits.
- Metadata is complete enough that the run can be reproduced without verbal explanation.

Do not proceed to interface scattering until this homogeneous protocol passes.
