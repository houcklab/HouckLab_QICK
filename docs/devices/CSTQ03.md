# CSTQ03

Device record for CSTQ03, a six-qubit BFC chip and the production target for the zero-span /
Modified Ramsey charge-parity measurements. Current cooldown: **2026-10-01** (BFC cooldown).
The numbers the code uses live in `devices/CSTQ03.py`; this page holds the history and the
measurements behind them. The parameter set used before this cooldown table ("v2b nu cell")
is archived at the bottom and in `devices/archive/`.

Dating convention: entries marked "runner note, undated" come from inline comments in the
legacy runner as of 2026-10-13 and carry no date of their own. Measured facts are attributed
as "CSTQ03 Qn, YYYY-MM-DD".

## Setup

| item | value |
|---|---|
| `cooldown` | `2026-10-01` |
| `data_root` | `V:/t1Team/Data/2026-10-01_BFC_cooldown/CSTQ03/RFSOC` (per-qubit folders `.../Q1//` ... `.../Q6//`) |
| RFSoC | Pyro4 nameserver `192.168.0.103:8888`, server `myqick` |
| Charge-line yoko | `GPIB1::9::INSTR`, voltage mode |
| TWPA bias yoko | `GPIB1::12::INSTR`, current mode (distinct from the charge-line yoko) |
| TWPA pump | Windfreak SynthHD on `COM5` |
| PNA-X | `GPIB0::16::INSTR` |
| TWPA calibration data | `V:/t1Team/Data/2026-10-01_BFC_cooldown/TWPA_calibration` |
| `cavity_min` | `True`: the resonator appears as a dip, not a peak |

### Board (BASE_CONFIG, no CSTQ03 overrides yet)

| key | value | units |
|---|---|---|
| `res_ch` / `qubit_ch` / `ro_chs` | 0 / 1 / [0] | channel |
| `nqz` (readout) / `qubit_nqz` | 2 / 1 | Nyquist zone |
| `mixer_freq`, `cavity_LO` | 0, 0 | MHz, Hz |
| `cavity_winding_freq`, `cavity_winding_offset` | 0, 0 | (identity) |
| `trig_buffer_start` / `trig_buffer_end` / `trig_delay` | 0.02 / 0.02 / 0.082 | us |
| `adc_trig_offset` default | 1 | us (the session window overrides it) |

Measured board values (read from the live `QickConfig`, October 2026 audit): tProc
`f_time` 430.08 MHz; gen0/gen1 `f_fabric` 430.08 MHz; readout ro0 `f_output` 307.2 MHz;
`avg_maxlen` 16384; `buf_maxlen` 1024. Board qick 0.2.367; client qick pinned at 0.2.334. At
sigma = 0.1 us the board-verified Modified Ramsey limit is df < 1.2502 MHz (no pi) and
df < 0.6251 MHz (echo).

`FF_Qubits` (legacy fast-flux map, persisted into every cfg but read by no active code): Q1 ch 2
delay 0.0215 us (0.017 + 0.0045), Q2 ch 4, Q3 ch 5, Q4 ch 6, delay 0. It has four entries for a
six-qubit chip; it belongs in `Setup.ff_qubits` if it is kept at all.

### TWPA

| item | value | when |
|---|---|---|
| Pump, ch1 (active) | 10.7165 GHz, -5.5 dBm | 2026-10 cooldown |
| Pump, ch0 (earlier, commented out) | 10.7831 GHz, -1.0 dBm | undated |
| Pump ON point (earlier, commented out in gain compare) | 10.9187 GHz, -18 dBm | undated |
| Bias target committed in the set-bias script | 0 uA, with the note "18 (10/7/26)" | 18 uA presumably set on 2026-10-07 |
| Earlier bias optimum | flux sweep `20260521_144734`: max \|S21\|, broad plateau 3.5-5.5 uA | 2026-05-21 |
| Datasheet nominal | about 11 uA (about 15 uT internal field, impedance matched); first flux period ends about 25 uA; ramp at most 300 nA/s, pump off | |

The committed set-pump script has `DISABLE_PUMP = True`, so running it without `--on` turns
the pump off. Note 18 uA is above the datasheet's "do not sweep well above about 11 uA in normal
operation" guidance.

## Qubit parameters, 2026-10-01 cooldown

Frequencies in MHz, gains in DAC units (0..32767), sigma in us. pi/2 gain as written in the
runner.

| Q | readout f | readout gain | qubit f | pi gain | pi/2 gain | sigma | flat-top |
|---|---|---|---|---|---|---|---|
| 1 | 6791.2 | 1000 | 2763 | 5000 | 1987 (`3975 // 2`) | 0.6 | none |
| 2 | 7452.9 | 4500 | 3754.5 | 3800 | 1900 (`3800 // 2`) | 0.02 | none |
| 3 | 6916.2 | 1000 | 2512 | 5000 | 1987 (`3975 // 2`) | 0.06 | none |
| 4 | 7593 | 4000 | 4117 | 4900 | 2450 (`4900 // 2`) | 0.02 | none |
| 5 | 7095.4 | 1500 | 2651 | 4200 | 2100 (`4200 // 2`) | 0.08 | none |
| 6 | 7285 | 1500 | 2955.6 | 4000 | 2000 (`4000 // 2`) | 0.04 | none |

Q1 and Q3 have pi/2 = `3975 // 2` while their pi gain is 5000; the pi/2 value looks carried over
from another qubit and was not re-derived.

### Readout windows

| window | integration | ADC offset | tone | notes |
|---|---|---|---|---|
| Measurement (regime A) | 15 us | 0.3 us | 15.3 us | device default |
| Single shot (regime B) | 15 us | 0.3 us | 15.3 us | device default |

Per-qubit notes (runner notes, undated): Q2 "readout length 5 us"; single-shot readout time
"qubit 1: 15 us, qubit 5: 5 us", next to the instruction "keep at 15". Whether Q2 and Q5 should
get per-qubit `Readout.window` / `Readout.ss_window` overrides of 5 us is not settled.

### Session snapshot (legacy runner, 2026-10-13)

`qubit_readout` = 5, `qubit_pulse` = 5, bias 0.0 V, `yoko_fixed` False. Single-shot group:
1000 shots, relax 6000 us, `number_of_pulses` 1, `pi2_SS` False. Spec group: `qubit_gain` 1000,
drive `gain` 800, span +/-10 MHz, 201 points, flat drive 50 us (`Gauss` False, sigma 2 us),
reps 20 x rounds 10, relax 2500 us.

## Per-qubit history

"Currently working on N" (runner notes, undated): each slot carried a comment
"currently working on N": Q1 -> 2, Q2 -> 4, Q3 -> 3, Q4 -> 5, Q5 -> "6?", Q6 -> (blank). In the
v2b table: Q1 -> 3, Q2 -> 6, Q3 -> 4, Q4 -> (blank), Q5 -> 5, Q6 -> 2. **Meaning unknown.** It
may map table slot to physical qubit label or readout line; until confirmed, treat the slot
number (Q1..Q6, which also names the data folder) as the only identifier.

| Q | notes |
|---|---|
| 1 | No history recorded for this cooldown. |
| 2 | Readout coarsely tuned to 4000, "seeing behaviour at 4500"; readout length 5 us; "qubit, T1 found" (runner note, undated). Spectroscopy 2026-09-02 12:03: broad response near 3753 MHz (see below). |
| 3 | Readout gain was 1200 before, now 1000 (runner note, undated). |
| 4 | Readout history: 7288.48 MHz at gain 1180; gain 400 good, 420 "too much i think", 600 too much; with the directional coupler 1400 good, 1500 "maybe too much". Pi-pulse history: 7468 at sigma 0.15 us, 5396 at sigma 0.225 us, then 6435; 2603.33 used for Ramsey; pi/2 `7009 // 2` (runner note, undated; the same comment appears on the v2b slot, so it may predate this cooldown). Spectroscopy drive "qubit_length 10 was the best for Q4" (legacy config-builder note; device not stated). |
| 5 | Alternative qubit frequency 2756.685 MHz (runner note, undated). Spectroscopy gain 750 works for Q5. |
| 6 | Readout gain previously 1400. Previous qubit frequencies: 3056, 3238.7, 2965, 3921.5, 2963.5 MHz (runner note, undated). Possibly also the Q6 spectroscopy of 2026-06-02 (real feature in I near 3054 MHz; the source note names Q6 but not the device, see below). |

Other undated runner notes:

- Bias: `start_voltage` 0.0059 V "working for good T2Rs" (qubit not stated; current setting
  0.000 V).
- Spectroscopy: flat drive length 9.5 us "worked"; "500 used for charge sweeps" next to the
  spec group (unclear whether it refers to relax delay or gain).
- Charge range: `voltage_start` 0.0, `voltage_end` 0.05, `voltage_step` 0.005 V, with the note
  "0.0001 has two periods in it" (verbatim; meaning unclear).
- Previous T1 settings: step 80 us, 100 points, reps 30, rounds 30; relax delay 5000 us (now
  5 us, 100 points, 20 x 20, 3000 us).

## Spectroscopy findings

- Q6, 2026-06-02 (QubitSpecFF; the source note does not name the device, and the date
  precedes the 2026-10-01 cooldown): the real feature lay in I near 3054 MHz; the old
  `|I + iQ|` peak finder picked Q-quadrature noise spikes at 3038 and 3069 MHz instead. Led to
  projecting onto the principal IQ axis.
- CSTQ03 Q2, 2026-09-02 12:03: a broad response near 3753 MHz was inverted into a dip by the old
  whole-trace-median baseline (abs(min) > abs(max) orientation), and both "peaks" landed on edge
  noise at 3764 MHz. Led to taking the baseline from the outer 15% of the span on each side
  (span centred on the expected line) and orienting by total excursion mass.

## Charge parity and charge dispersion

### Doublet measurements

| quantity | value | source |
|---|---|---|
| Modified Ramsey doublet, upper branch | 4186.7 MHz | CSTQ03 Q2, 2026-08-04 |
| lower branch | 4184.0 MHz | CSTQ03 Q2, 2026-08-04 |
| df | 2.7 MHz (midpoint 4185.35 MHz) | CSTQ03 Q2, 2026-08-04 |
| Charge-dispersion amplitude `cd_max_mhz` | 0.682 MHz | independent calibration, qubit and date not recorded |
| Charge-dispersion period `cd_period_mv` | 4.37 mV of yoko voltage | same calibration |
| Charge-dispersion doublet | middle 2306.310396, upper 2306.567327, lower 2306.032673 MHz (split 0.5347 MHz) | runner, device and date not recorded; not a frequency of the current table |

Model used by the sweet-spot logic: S(V) = cd_max_mhz * |cos(2 pi (V - V0) / T)|,
T = cd_period_mv.

**Unreconciled:** the 2026-08-04 df of 2.7 MHz is about 4x the 0.682 MHz `cd_max_mhz`. Either the
two describe different qubits/cooldowns, or the 2.7 MHz doublet is not charge parity. Confirm
before trusting `expected_parity_dwell_ms` or any tau derived from df. Observation: the
2026-08-04 midpoint 4185.35 MHz is close to the v2b table's Q2 frequency 4185.6 MHz, not to the
current Q2 (3754.5 MHz); the doublet was probably measured under the v2b parameter set.

No parity parameters (`ParityParams`) are calibrated for the 2026-10-01 cooldown. The legacy
Modified Ramsey dict carries `df` = 1 MHz and `f_ge` = 3754.5 MHz with the comment "measured TOP
branch (bottom = 4184.0)". That is stale: 3754.5 is Q2's centre frequency in the current table,
not an upper branch, and the session qubit is Q5. With `symmetric_ramsey=True` a centre value
puts the drive on the lower branch with the 90 degree closing phase, which looks like a contrast
failure. In qicklab, `f_upper_mhz` must be set in the qubit's `ParityParams`; the recipe raises
if it is missing. History: the two-tone doublet search and yoko walk were removed from
`modified_ramsey` (never worked reliably); df and the upper branch are configured, and the step
never moves the yoko.

A Modified Ramsey base config for Q6 in the hardware timing check (date not recorded): readout
7285.11 MHz at gain 800, integration 15 us, tone 16 us, ADC offset 1 us; sigma 0.1 us, pi 4600,
pi/2 2375, f_ge 3055.2 MHz, df 0.5 MHz, reps 1000, nqz 2, qubit_nqz 1, `res_ch` 0, `qubit_ch` 1,
`ro_chs` [0]. Its pi/pi2/sigma match the v2b Q6 slot.

### Modified Ramsey at df = 2.7 MHz: timing choice

tau = k / (2 df) with odd k (CSTQ03 Q2 parameters, 2026-08-04, sigma = 0.1 us):

| k | tau | result |
|---|---|---|
| 1 | 0.185 us | infeasible: the two pi/2 envelopes already span 4 sigma = 0.4 us; the program raises |
| 3 | 0.5556 us | gap 0.156 us, realised phase 3.0008 pi, mapping contrast 1.000; but echo_null needs tau > 8 sigma = 0.80 us, so it is skipped and `all_expected` is forced False |
| 5 | 0.9259 us | echo gap 0.063 us, realised phase 4.997 pi; echo_null is feasible but, at sigma = 0.1 us, not a null: it keeps 0.641 contrast against the main 0.732 (symmetric), so `build_control_variants` marks it "not a null at these settings" |

Normally prefer the smallest feasible odd k (T2* is worst at maximum charge sensitivity). k = 5
was recommended on the premise that it keeps echo_null as a decisive control, but at sigma =
0.1 us the finite-pulse echo is not a null at either k (skipped at k = 3, not a null at k = 5;
see [the echo null](../experiments/modified_ramsey.md#echo-is-a-null-only-for-short-pulses)).
The echo becomes a usable null only at shorter sigma (sigma = 0.04 us, k = 3: echo 0.063
against main 0.960). The legacy runner still has `df` = 1, `tau_harmonic_k` = 1, which
contradicts this analysis.

### Unresolved drive-bandwidth limit (df = 2.7 MHz, sigma = 0.1 us)

A 4-sigma Gaussian pi/2 has peak Rabi rate 0.0997 / sigma = 0.997 MHz. The symmetric drive
detunes each branch by df/2 = 1.35 MHz: ratio 1.354 (standard drive: 2.708). Above 1.0 the
off-resonant branch is under-rotated and mapping contrast degrades for any tau. Ratio <= 1 needs
sigma <= 0.0739 us (symmetric) or <= 0.0369 us (standard). The pi/2 sits at only 3.7% of DAC full
scale; halving sigma needs gain about 2400 (7.3% FS), so there is headroom. The session runs with
`max_drive_bandwidth_ratio` = 1.4 "under protest" so the degraded contrast is measured rather
than guessed; return it to 1.0 once sigma allows.

### Root cause of the spurious kHz parity rate (CSTQ03 Q2, 2026-08-04)

Four-arm diagnostic, analog readout SNR 0.91:

| arm | relax | r(1) | r(10) | ACF amplitude |
|---|---|---|---|---|
| parity | 0 us | +0.289 | +0.099 | 0.004582 |
| drive_off (pi2_gain = 0) | 0 us | +0.469 | +0.301 | 0.011050 |
| parity | 200 us | +0.072 | +0.010 | 0.002301 |
| drive_off | 200 us | +0.115 | +0.032 | 0.000575 |

drive_off plays no pi/2 pulses and cannot carry parity, yet it showed 2.4x the parity arm's
ACF amplitude: the correlation is an artifact and dominates. 200 us of relax collapses it 4x
(parity) and 19x (drive_off), which identifies incomplete inter-shot reset: with relax 0 and no
active reset the readout collapses the qubit but never returns it to `|g>`. With T1 about 50 us,
carryover is exp(-11.75/50) = 79% at relax 0 and exp(-211.75/50) = 1.4% at 200 us; the residual
r(1) of 0.07-0.12 in the 200 us arms is slow readout drift (ACF tau about 122 ms). 250 us
(5 x T1) leaves 0.5%.

Cost: the rep period becomes about 262 us, so a 2.5 ms dwell is sampled about 9.6 times instead
of about 213 times; per-dwell SNR drops from about 8.8 to about 2.3. Compensate with many dwells,
not with a lower HMM gate. At 250 us relax: 100 000 shots is about 26 s and 10 500 dwells;
400 000 shots about 105 s and 42 000 dwells (the old 4.7 s relax-0 record had 1880). Start at
100k.

The legacy runner has `mr_relax_delay` = 500 us with the comment "5x T1=50us" (5 x 50 = 250) and
`mr_reps` = 50 000, while the text recommends 250 us and 100k. Which is intended is not settled.

### HMM emission gate (CSTQ03 Q2, 2026-08-04)

On 2026-08-04 the gate tested analog SNR x |p_e(state1) - p_e(state0)| using the assumed mapping
probabilities (0.1, 0.9). At the measured analog SNR of about 0.77 the product was about 0.62,
under the 0.7 default, so the HMM withheld a rate. That is bookkeeping, not physics (per-dwell
separation is about 8.8 at about 213 samples per dwell). The mapping is now fitted with the rate
(`hmm_fit_mapping`, default True) and the gate uses the fitted probabilities, with the same 0.7
threshold: at this analog SNR it passes only for a fitted contrast above about 0.92. **Do not lower the gate.** At 0.3 the HMM returned
4921 +/- 68 Hz while ACF gave 9606 Hz and PSD 15056 Hz (more than 3x apart, auto-flagged), and the
echo_null control showed 44% of the parity record's ACF amplitude. That was read at the time as
proof that the correlation is not parity, on the premise that the echo cannot contain parity
contrast; the premise is wrong at sigma = 0.1 us, df = 2.7 MHz (the finite-pulse echo is
predicted to keep 0.77 of the parity ACF amplitude, see
[the echo null](../experiments/modified_ramsey.md#echo-is-a-null-only-for-short-pulses)), so the
echo does not decide the question; the HMM / ACF / PSD disagreement and the drive_off diagnostic
do. The fit locked onto the 50-200 us shot-to-shot correlation above. 0.7 correctly
withheld the number; `None` keeps 0.7. History: an older comment in the Modified Ramsey run code
advised lowering the gate deliberately; this measurement supersedes it.

### Active reset and resonator linewidth

`reset_readout_relax_delay` (delay from the conditioning readout to the corrective pi) must be
at least about 6/kappa of the readout resonator so the pi fires on a photon-free qubit. The
5 us in use equals 6/kappa for the TATQ01/BFE Q2 resonator (kappa/2pi = 190 kHz, measured
2026-06-06). **kappa has not been measured for CSTQ03**; measure it per readout resonator and
set `Readout.kappa_mhz`. `transmission_fit` prints and saves kappa_tot/2pi in MHz
(`hanger_fit_kappa_tot_mhz`, the total linewidth |f0|/Qtot) and kappa_ext/2pi; use kappa_tot,
and remember 6/kappa = 6/(2 pi x kappa_tot/2pi): 0.19 MHz gives 5 us. ActiveResetVerify must use the same
`reset_readout_relax_delay` as Modified Ramsey; its own relax delay is 3500 us (>= 3 x T1).

## Archived: v2b "nu cell" parameter set

Kept in `devices/archive/CSTQ03_v2b.py`; not used by any code. Whether "v2b nu cell" is a
previous cooldown of this chip or a sibling chip is not recorded.

| Q | readout f | readout gain | qubit f | pi gain | pi/2 gain | sigma | flat-top | notes (runner notes, undated) |
|---|---|---|---|---|---|---|---|---|
| 1 | 6748 | 2000 | 1752 | 5000 | 1987 | 0.2 | none | readout gain 500 okay, 520 maybe too much, 530 too much, 700 too much |
| 2 | 7408.37 | 3500 | 4185.6 | 2675 | 1200 (`2400 // 2`) | 0.04 | none | readout coarsely tuned to 4000, behaviour at 4500; qubit and T1 found |
| 3 | 6870.8 | 1500 | 2900 | 5000 | 1987 | 1 | 1 | readout gain 600 too much; qubit found at 1719.8273 MHz |
| 4 | 7535.96 | 2000 | 4590 | 2800 | 1400 | 0.02 | none | same readout and pi history as the current Q4 slot |
| 5 | 7050 | 3000 | 2758.3 | 4000 | 2000 | 1 | none | readout 4500 with directional coupler, 1500 good without; alternative frequency 2756.685 MHz; qubit and T1 found |
| 6 | 7244.8 | 2000 | 3258.1 | 4600 | 2375 (`4750 // 2`) | 0.1 | none | qubit "can't find" |

## Open items

- Meaning of "currently working on N".
- Reconcile df = 2.7 MHz (2026-08-04) with `cd_max_mhz` = 0.682 MHz; record qubit and date of the
  charge-dispersion calibration.
- Measure kappa for each readout resonator.
- Decide `mr_relax_delay` (250 vs 500 us) and `mr_reps` (50k vs 100k).
- Per-qubit readout windows for Q2 and Q5.
- Identity of the 2306.3 MHz charge-dispersion doublet.
- TWPA bias in use for this cooldown (18 uA per the 2026-10-07 note, or 0 as committed). From
  now on the `twpa_state.jsonl` log in the TWPA calibration folder records it.
