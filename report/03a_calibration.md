# 03a — Qubit and Resonator Calibration Recipe

Scope: the canonical "first time taking data" calibration sequence for the
triangle-lattice 8-qubit chip in this repo. Every step (a) what runs, (b) what
knobs you turn, (c) what comes out, (d) which `Qubit_Parameters[Q]` field gets
overwritten. All scripts referenced live under
`D:/Agentic_QSim_Measurement/WorkingProjects/triangle_lattice_quench/`.

The orchestrator is `Run_Experiments/Fast_calib.py`; that script chains the
"Basic_Experiments" classes below in the order this document walks through.
Hardware bring-up and the channel map are covered in `02_hardware_engineer.md`
— this document assumes `soc`/`soccfg` are already initialized via
`MUXInitialize.py` and that `BaseConfig`, `res_LO`, `qubit_LO`, `res_ch`,
`qubit_ch`, `ro_chs`, `mixer_freq` are all live.

---

## 0. Where the calibrated numbers live

The chip-level calibration state is a nested dict named `Qubit_Parameters`.
Every basic experiment reads from and ultimately writes back to fields of this
dict via the `UPDATE_CONFIG.py` mechanism (see step 6 below).

The canonical structure for one qubit
(`WorkingProjects/triangle_lattice_quench/Run_Experiments/qubit_parameter_files/pi_flux_J_ll_is_J/BS_Mux8_1234_Readout.py:20-50`):

```python
'1': {'Readout': {'Frequency': 7121.7, 'Gain': 1500,
                  'FF_Gains': Readout_1234_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
      'Qubit':   {'Frequency': 3913.5, 'sigma': 0.03, 'Gain': 3635},
      'Pulse_FF': Readout_1234_FF}
```

So per-qubit there are exactly three groups:

- `Qubit_Parameters[Q]['Readout']`: cavity tone — `Frequency` (MHz, RF), `Gain`
  (DAC gain into the MUX gen), `FF_Gains` (per-channel fast-flux DAC gains
  during readout, length-8 array), `Readout_Time` (us), `ADC_Offset` (us delay
  between resonator pulse start and ADC trigger), and the optional boolean
  `cavmin` (see step 1).
- `Qubit_Parameters[Q]['Qubit']`: drive tone — `Frequency` (MHz, RF), `sigma`
  (us, Gaussian envelope sigma; physical pulse length = 4*sigma), `Gain`
  (integer 16-bit DAC gain mapped to `gain/32766.` in QICK).
- `Qubit_Parameters[Q]['Pulse_FF']`: length-8 fast-flux array used while
  driving (typically equal to the readout-mux flux setpoint; see step 6).

The setpoint files (`BS_Mux8_<MUX>_Readout.py`) are imported by
`qubit_parameter_files/<flux>/Qubit_Parameters.py` (e.g.
`Run_Experiments/qubit_parameter_files/pi_flux_J_ll_is_J/Qubit_Parameters.py:8-15`),
which exposes the `drive_params` dict used by the experiment scripts. The
top-level dispatcher
`Run_Experiments/qubit_parameter_files/Qubit_Parameters_Master.py:14-17` simply
selects which setpoint dict the rest of the codebase sees:

```python
from ...BS_TEST_Readout import *
from ...pi_flux_J_ll_is_J.Qubit_Parameters import *
Qubit_Parameters = BSTEST_Readout
```

Switching flux conditions (zero-flux vs. pi-flux, J||/J ratio) is therefore a
single edit to `Qubit_Parameters_Master.py:17`. The directories
`qubit_parameter_files/zero_flux_J_ll_is_J/`,
`qubit_parameter_files/pi_flux_J_ll_is_2J/`,
`qubit_parameter_files/high_lattice_zero_flux_J_ll_is_3J/`, etc. are
independent calibration baselines. Treat them as snapshots — the calibration
recipe below regenerates the entries inside one of these baselines.

---

## 1. Resonator (cavity) sweep — `mTransmissionFFMUX.py`

**Class:** `CavitySpecFFMUX` and inner program `CavitySpecFFProg`
(`Experimental_Scripts/Basic_Experiments/mTransmissionFFMUX.py:15,47`).

**(a) What it does.** Hard-loops over `cfg["TransNumPoints"]` frequency points
spanning `cfg["res_freqs"][0] ± cfg["TransSpan"]` (in MHz at the IF, RF =
IF + `cfg["res_LO"]`). For each point the inner program plays one constant
MUX-readout pulse on `cfg["res_ch"]` of length `cfg["res_length"]` while
applying the static fast-flux setpoint via `FF.FFDefinitions` /
`self.FFPulses(self.FFReadouts, ...)`
(`mTransmissionFFMUX.py:32-42`). Acquired IQ for each ADC in
`cfg["ro_chs"]` is averaged. The frequency loop is in Python
(`mTransmissionFFMUX.py:62-66`), not on tProc, so this is slower than a
spectroscopy-style swept-pulse experiment but is robust.

**(b) Knobs.** Set in `Fast_calib.py:773-776` as `Trans_params`:

- `reps` (≈250), `TransSpan` (1.5 MHz default), `TransNumPoints` (≈91)
- `readout_length` (us, written into `cfg["readout_lengths"][0]`)
- `cav_relax_delay` (us between shots)
- `res_freqs[0]` is the *center* — set this to the seed
  `Qubit_Parameters[Q]['Readout']['Frequency'] - res_LO`
  in `UPDATE_CONFIG.py`.

**(c) Output.** `analyze()` does an `argmin` (`mTransmissionFFMUX.py:85-86`)
and an `argmax` (`:87-88`) on `|I + jQ|`, plus an inverted-Lorentzian-with-
linear-background fit
(`mTransmissionFFMUX.py:97-113`). Three frequencies are exposed:

- `self.peakFreq_argmin` — naive amplitude minimum
- `self.peakFreq_max` — naive amplitude maximum
- `self.peakFreq_lorentz_min` — fit center

`self.peakFreq_min` is selected as the fit center if `use_lorentzian=True` and
fit uncertainty < `0.2*linewidth`, else the argmin
(`mTransmissionFFMUX.py:124-126`).

**Min vs. max — which is "the" readout frequency?**
Hanger-coupled readout resonators on this chip dip in transmitted amplitude on
resonance, so the cavity resonance shows up as the *minimum* of |S21|. That is
why `peakFreq_min` is the canonical answer. However, when the qubit is in |e⟩
the cavity is dispersively shifted and on the original cold cavity frequency
the amplitude actually *rises* above the off-resonant level — that is what
`peakFreq_max` is there to track when present. For initial calibration of an
isolated qubit in |g⟩, `peakFreq_min` is the cold-cavity center.

The flag `Qubit_Parameters[Q]['Readout']['cavmin']` (boolean, see e.g.
`Run_Experiments/T1_TLS_calibs.py:20`,
`Run_Experiments/FF_calibs.py:14,19,24,29,34,39,44,49`) controls which the
loop drivers will actually copy into `config["res_freqs"][0]`:

```python
# Loop_SingleShot_Experiments.py:262-265
if Qubit_Parameters[str(Qubit_Readout[0])]['Readout'].get('cavmin', False):
    config["res_freqs"][0] = Instance_trans.peakFreq_min
else:
    config["res_freqs"][0] = Instance_trans.peakFreq_max
```

In practice you set `cavmin=True` for the bare-cavity transmission when
preparing a |g⟩ readout, and `cavmin=False` when you want to lock to the
dispersively-shifted (|e⟩-shifted) maximum — useful for chi-shift calibration
or when the bare dip is hidden under TWPA-pump artefacts. The MUX-multiplexed
readout dictionary and `Loop_SingleShot_Experiments.py` both consume this flag.
`Fast_calib.run_transmission` always uses the Lorentzian min
(`Fast_calib.py:484-490`).

**(d) Updates.** `Qubit_Parameters[Q]['Readout']['Frequency']` ← peak +
`res_LO` (writeback path:
`Fast_calib.py:490` and `Loop_SingleShot_Experiments.py:262-265`). The new
value persists into `config["res_freqs"][0]` for downstream steps in the same
session; the `Qubit_Parameters` source file
(e.g.
`qubit_parameter_files/pi_flux_J_ll_is_J/BS_Mux8_1234_Readout.py:21`) is
edited by hand once you accept the result.

---

## 2. Qubit spectroscopy — `mSpecSliceFFMUX.py`

**Class:** `QubitSpecSliceFFMUX` and program `QubitSpecSliceFFProg`
(`Experimental_Scripts/Basic_Experiments/mSpecSliceFFMUX.py:13,75`).

**(a) What it does.** With the cavity tone fixed at the result of step 1,
sweep the qubit drive frequency on tProc using a `QickSweep1D` named
`qubit_freq_loop` over
`cfg["qubit_freqs"][0] ± cfg["SpecSpan"]` with `cfg["SpecNumPoints"]` points
(`mSpecSliceFFMUX.py:33-36`). The drive is either a long constant pulse
(`Gauss=False`, default for spec) of length `cfg["qubit_length"]` (default
100 us, set in `acquire()` at `:86`) or a Gaussian
(`Gauss=True`) of `4*cfg["sigma"]`. After the drive, do a normal
MUX readout with the same FF setpoint as the readout pulse
(`mSpecSliceFFMUX.py:53-69`).

**(b) Knobs.** From `Fast_calib.py:778-788`, two passes:

- **Coarse** `First_Spec_params`: `qubit_gain=500`, `SpecSpan=100`,
  `SpecNumPoints=71`, `Gauss=False`, `sigma=0.07`, `reps=200`. This is a wide
  CW spec to find f01 from cold.
- **Fine** `Second_Spec_params`: `qubit_gain=50`, `SpecSpan=10`,
  `SpecNumPoints=81`, `reps=250` — narrows down to a clean Lorentzian on the
  found peak.

Other knobs: `qubit_LO`, `qubit_mixer_freq`, `qubit_nqz`. Keep the gain low
enough that you do not power-broaden the dip; if the fit linewidth is
suspiciously large drop `qubit_gain` and re-run.

**(c) Output.** `analyze()` performs argmax of `IQ_contrast(avgi, avgq)`
(`mSpecSliceFFMUX.py:117-121`; `IQ_contrast` rotates the IQ blob so that the
signal lives on I, see step 4) plus a windowed Lorentzian fit
(`mSpecSliceFFMUX.py:124-150`). The chosen frequency is `self.qubitFreq` —
either `qubitFreq_lorentz` (if fit uncertainty < `0.2*qubit_linewidth`) or
`qubitFreq_argmax`
(`mSpecSliceFFMUX.py:160-165`). Note: returned freq is already `qubit_LO`-
shifted because `loop_pts()` adds `qubit_LO`
(`mSpecSliceFFMUX.py:71-72`, `:97-98`).

**(d) Updates.** `Qubit_Parameters[Q]['Qubit']['Frequency']` ← `self.qubitFreq`.
Live writeback in `Fast_calib.py:513-516`.

---

## 3. Amplitude Rabi — `mAmplitudeRabiFFMUX.py`

**Class:** `AmplitudeRabiFFMUX` and program `AmplitudeRabiFFProg`
(`Experimental_Scripts/Basic_Experiments/mAmplitudeRabiFFMUX.py:12,68`).

**(a) What it does.** With the qubit drive frequency from step 2, play a
Gaussian envelope of fixed `sigma` (so fixed pulse length `4*sigma`) and
sweep its amplitude `gain` from 0 to `cfg["max_gain"]/32766.` over
`cfg["expts"]` points using the tProc sweep `qubit_gain_loop`
(`mAmplitudeRabiFFMUX.py:31-40`). One readout per gain.

**(b) Knobs.** From `Fast_calib.py:790-792`:

- `max_gain` (=12000 default; `Fast_calib.py:794-795` boosts by 1.4× for Q3
  and Q5).
- `expts=31`, `reps=900`, `f_ge` defaulted to the most recent
  `qubit_freqs[-1]`
  (`mAmplitudeRabiFFMUX.py:78-80`).
- `sigma` is read from `cfg["sigma"]` — by convention 0.03 us for a fast
  Gaussian (matches the values in `BS_Mux8_*_Readout.py:23,27,31,...`);
  pi-pulse length is therefore 4*0.03 = 120 ns. Increasing `sigma` lowers the
  pi-pulse gain at the cost of more decoherence during the gate.
- `relax_delay` (=100 us in `Fast_calib`).

**(c) Output.** `IQ_contrast(avgi,avgq)` is fit to
`fit_func_simple(gain) = ampl * cos(pi*gain/pi_gain)`
(`mAmplitudeRabiFFMUX.py:62-63,113-117`). The fit returns
`self.pi_gain_fit` — the gain register value (in 16-bit DAC units, i.e. before
the `/32766` normalization) at which `cos(π·g/π_gain) = -1`, i.e. a π pulse.
A frequency-domain seed is derived from `frequency_guess(x_pts, contrast)`
(`Helpers/IQ_contrast.py:33-39`). The complex 4-parameter fit is intentionally
disabled
(`mAmplitudeRabiFFMUX.py:121-122`).

**(d) Updates.** Two fields:

- `Qubit_Parameters[Q]['Qubit']['Gain']` ← `pi_gain_fit` (rounded). Writeback:
  `Fast_calib.py:535-536` (`config["qubit_gains"][OptQubit_index] =
  data['data']['pi_gain_fit'] / 32766`).
- `Qubit_Parameters[Q]['Qubit']['sigma']` is *not* updated by the Rabi script;
  it is the input you fix beforehand. If you want a faster pi pulse, edit
  `sigma` in the qubit-parameter file and re-run Rabi to get the new
  `Gain`.

After this step the chip has a working π pulse — single-shot calibration is
next.

---

## 4. Single-shot readout calibration — `mSingleShotProgramFFMUX.py` + `CALIBRATE_SINGLESHOT_READOUTS.py`

**Class:** `SingleShotFFMUX` and `SingleShot_2QFFMUX` for two-qubit confusion
matrices
(`Experimental_Scripts/Basic_Experiments/mSingleShotProgramFFMUX.py:70,175`),
both built on `SingleShotProgram`
(`mSingleShotProgramFFMUX.py:11`).

**(a) What it does.** Two acquisition runs on the same readout schedule:

1. `cfg["Pulse"]=False` → no qubit pulse, take `cfg["Shots"]` single shots →
   ground IQ blob `(i_g, q_g)`
   (`mSingleShotProgramFFMUX.py:95-97`).
2. `cfg["Pulse"]=True` → π pulse(s) at the calibrated `qubit_freqs` and
   `qubit_gains` (one or many qubits, controlled by `number_of_pulses` and
   the lengths of the freq/gain lists), then read → excited IQ blob
   `(i_e, q_e)` (`mSingleShotProgramFFMUX.py:99-101`). Unlike the averaged
   experiments, this calls `prog.acquire_shots`, returning per-shot I/Q.

For each readout channel `i` in `cfg["Qubit_Readout_List"]` it then calls
`hist_process(data=[i_g, q_g, i_e, q_e], ...)`
(`mSingleShotProgramFFMUX.py:117`).

**(b) Knobs.** Lifted from `cfg` and from `Fast_calib.py:813-817`:

- `Shots` (=2500 in final pass; `CALIBRATE_SINGLESHOT_READOUTS.py:17` uses
  `2*4000`).
- `relax_delay` (=200 us — must be ≥ several T1).
- `number_of_pulses` (1 for a normal π; >1 for repeated π pulses, used to
  push to higher excited states for population leakage tests).
- The driver script `CALIBRATE_SINGLESHOT_READOUTS.py:23-30` rebuilds
  `new_config` per qubit from `Qubit_Parameters`:
  `qubit_freqs` ← `Qubit['Frequency'] - qubit_LO`,
  `qubit_gains` ← `Qubit['Gain']/32766.`,
  `sigma` ← `Qubit['sigma']`, and per-channel
  `FF_Qubits[Q+1]['Gain_Pulse']` ← `Pulse_FF[Q]`. So the single-shot is taken
  at exactly the calibrated π pulse and FF setpoint.

**(c) Output.** Per readout channel:

- `data['data']['angle'][ro_ind]` — IQ rotation angle θ in radians.
- `data['data']['threshold'][ro_ind]` — discrimination threshold on rotated
  I (after rotation, the |g⟩↔|e⟩ separation is along I).
- `data['data']['fid'][ro_ind]` — single-shot fidelity = max of the cumulative
  contrast (`Helpers/hist_analysis.py:96-100`).
- `data['data']['ng_contrast'][ro_ind]`, `ne_contrast[ro_ind]` — the
  P(measure 1|prepared g) and P(measure 0|prepared e) error rates
  (`hist_analysis.py:101-102`).
- `data['data']['confusion_matrix'][ro_ind]` —
  `[[1-ng, ne],[ng, 1-ne]]` (`mSingleShotProgramFFMUX.py:125-128`).

**How angle and threshold are computed.** In `hist_process`
(`hist_analysis.py:9-114`):

1. Compute medians `(xg, yg)` and `(xe, ye)` of the two blobs
   (`hist_analysis.py:17-18`).
2. The rotation angle is `theta = -atan2(ye - yg, xe - xg)`
   (`hist_analysis.py:50`). This is a *blob-to-blob* angle so that after
   rotation the g-to-e displacement vector lies along +I.
3. Rotate every shot:
   `i_new = i*cos(θ) - q*sin(θ); q_new = i*sin(θ) + q*cos(θ)`
   (`hist_analysis.py:51-55`). The same rotation formula appears in
   `Helpers/rotate_SS_data.py:5-11` (`rotate_data((i,q), theta)`) and
   in-line in `mSingleShotProgramFFMUX.py:340-347` for the 2Q confusion
   matrix.
4. Histogram both clouds along the rotated I-axis with 200 bins
   (`hist_analysis.py:86-93`).
5. The threshold is `binsg[argmax(cumsum(ng)/Σng - cumsum(ne)/Σne)]`
   (`hist_analysis.py:96-99`) — the I value that maximizes
   `P(I<thr | g) - P(I<thr | e)`. Fidelity = that contrast value
   (`hist_analysis.py:100`).
6. Binarization is `(rotated_I > threshold).astype(int)` — explicit example
   in `mSingleShotProgramFFMUX.py:349-352`.

The closely related helper `Helpers/IQ_contrast.py:14-17` is used for
*averaged* experiments (T1, T2, Rabi). It picks θ by *minimizing peak-to-peak
of the rotated Q* (`IQ_contrast.py:4-9`) — i.e., it forces the variance onto
I — and returns `rotated_I - mean(rotated_I)`. Two distinct rotation choices,
same idea. `IQ_contrast` is the one used during fitting because it does not
require a separate ground-state reference.

**(d) Updates.** Per readout channel index `i`,
`config['angle'][i]`, `config['threshold'][i]`,
`config['confusion_matrix'][i]`
(`CALIBRATE_SINGLESHOT_READOUTS.py:74-76`). These are config-side fields;
they are *not* stored back into `Qubit_Parameters[Q]` itself but are
re-derived every time `CALIBRATE_SINGLESHOT_READOUTS.py` runs, since they
depend on the entire MUXed readout group, ADC cable phase, TWPA state, and
flux setpoint. Fidelity is reported but not saved as a parameter — track it
manually. The classifier output `(angle[i], threshold[i])` is what every
later population experiment (Ramsey populations, T1 vs FF, correlation
experiments) uses to convert IQ shots into 0/1 outcomes via
`Helpers/rotate_SS_data.py:rotate_data` and `count_percentage`
(`rotate_SS_data.py:13-17`); `correct_occ` then optionally inverts the
confusion matrix (`rotate_SS_data.py:23-29`).

---

## 5. Coherence — `mT1MUX.py`, `mT2RMUX.py`, `mT2EMUX.py`

All three are structurally identical: one tProc loop named `delay_loop` of
length `cfg["expts"]` sweeping a delay from 0 to `cfg["stop_delay_us"]`
(`mT1MUX.py:32-33`, `mT2RMUX.py:31-34`, `mT2EMUX.py:31-34`). They use the
calibrated `qubit_freqs[0]`, `qubit_gains[0]`, and `sigma`.

### 5.1 T1 — `mT1MUX.py`

**(a)** π pulse at t=1 us, then `delay(swept_delay)`, then MUX readout
(`mT1MUX.py:42-60`). FF pulses bracket the entire experiment so the
qubit relaxes at the calibrated FF setpoint.

**(b) Knobs.** `Fast_calib.py:819` — `stop_delay_us=100`, `expts=40`,
`reps=150`. `relax_delay` from outer config. If T1 looks longer than
the sweep window, increase `stop_delay_us` until the curve has actually
flattened.

**(c) Output.** `display()` fits `IQ_contrast(avgi, avgq)` to
`A*exp(-t/T1) + y0` (`mT1MUX.py:127-131`). `self.T1` (us) is set on success
(`mT1MUX.py:137`). Plotted contrast is `sign(A) * Contrast` so the curve
always decays downward
(`mT1MUX.py:132-135`).

**(d) Updates.** None automatically. T1 is monitored, not stored in
`Qubit_Parameters`. Use it as a sanity check (`Fast_calib.MIN_T1=12.0`,
`Fast_calib.py:925`).

### 5.2 T2 Ramsey — `mT2RMUX.py`

**(a)** Two π/2 pulses around `swept_delay`. The second π/2 has phase that
either is fixed at 180° (default `phase_shift_cycles=0`) or sweeps as
`360*phase_shift_cycles` over the same loop — this is "phase ramping",
giving a controllable artificial detuning that produces clean cosine fringes
even when the qubit is on resonance (`mT2RMUX.py:36-47, 50-67`). Drive
frequency is `cfg["qubit_drive_freq"]` defaulted to
`qubit_freqs[0] + cfg["freq_shift"]` (`mT2RMUX.py:81`). `pi2_gain` defaults to
`qubit_gains[0]/2` (`mT2RMUX.py:83`).

**(b) Knobs.** `Fast_calib.py:821-828` — `stop_delay_us=5`, `expts=125`,
`reps=300`, `freq_shift=0.0`, `phase_shift_cycles=-3`, `relax_delay=150`.
Step-size warning if `stop_delay_us/expts < 4.65 ns` (one tProc cycle)
(`mT2RMUX.py:33-34`). Increase `phase_shift_cycles` magnitude for more visible
fringes; reduce when measuring the actual detuning so fewer cycles fit in
the window.

**(c) Output.** `IQ_contrast(avgi,avgq)` is fit to
`A*exp(-t/T2)*cos(ω·t - φ) + y0` (`mT2RMUX.py:141-146`). `self.T2` set on
success (`mT2RMUX.py:152`). The extracted `omega` (vs. expected `2π *
phase_shift_cycles / stop_delay_us`) gives the actual qubit-to-drive
detuning and is the input to `RamseyFreqCalibs.py` for closing the loop on
`Qubit_Parameters[Q]['Qubit']['Frequency']`.

**(d) Updates.** None automatically. T2R is the diagnostic; the *frequency
correction* uses the fit-omega and is applied either by hand or by
`RamseyFreqCalibs.py` (step 7c).

### 5.3 T2 Echo — `mT2EMUX.py`

**(a)** π/2 → wait `swept_delay/2` → π → wait `swept_delay/2` → π/2 (with
swept phase, identical to T2R)
(`mT2EMUX.py:53-62`). The `loop_pts()` doubles the swept delay
(`mT2EMUX.py:74-75`) so the x-axis is total free-evolution time.

**(b) Knobs.** Same family as T2R; longer `stop_delay_us` is reasonable
because echo refocuses low-frequency noise. Echo program also adds a third
pulse `qubit_drive_echo` at full `pi_gain` (`mT2EMUX.py:48-50`).

**(c) Output.** Same fit as T2R, with `self.T2` returned for echo. Used to
diagnose whether dephasing is dominated by quasistatic flux noise (T2R ≪
T2E) vs. high-frequency noise (T2R ≈ T2E).

**(d) Updates.** None automatic.

---

## 6. How calibrated numbers flow back into `Qubit_Parameters` and `config`

Two-stage update pattern:

1. **In-session `config` update.** Every loop driver (`Loop_T1_T2.py`,
   `Loop_SingleShot_Experiments.py`, `Fast_calib.py`, `RamseyFreqCalibs.py`)
   sets `Qubit_Readout = [Q]`, `Qubit_Pulse = [Q]` (or `[f"{Q}R"]`) and then
   `exec(open("UPDATE_CONFIG.py").read())`
   (`Loop_T1_T2.py:80`, `RamseyFreqCalibs.py:40`,
   `Loop_SingleShot_Experiments.py:252`). `UPDATE_CONFIG.py` (and its
   functional twin `UPDATE_CONFIG_function.py`) reads
   `Qubit_Parameters[str(Q)]['Readout']` and `['Qubit']` and assigns into
   `config["res_freqs"][0]`, `config["res_gains"][0]`,
   `config["qubit_freqs"][...]`, `config["qubit_gains"][...]`, `config["sigma"]`,
   `config["readout_lengths"][...]`, `config["adc_trig_delays"][...]` etc. So
   the experiment classes always see the most recent `Qubit_Parameters`
   values for the chosen qubit.

2. **Persistence to disk.** `Fast_calib.py` and the other calibration drivers
   *do not* rewrite the qubit-parameter `.py` files automatically. They print
   the new values via `QubitConfig.__str__` (used at
   `Fast_calib.py:1018-1023`) and via the dashboard
   `create_calibration_summary_dashboard`
   (`Fast_calib.py:41-324`). You hand-paste the new
   `Frequency`/`Gain`/`sigma` numbers into the appropriate
   `BS_Mux8_<MUX>_Readout.py` file under
   `qubit_parameter_files/<flux>/`. The repo treats those `.py` files as the
   source of truth and the calibration summary print as the diff.

`Qubit_Parameters_Master.py:14-17` controls which baseline is loaded — flip
the imported module or change the final `Qubit_Parameters = ...` assignment
to switch flux configurations.

---

## 7. Fast calibration utilities — when to use which

### 7a. `Run_Experiments/Fast_calib.py`
**When.** Cold start of a session, after the cryostat has been swept or after
any disruptive change (cable swap, TWPA-pump retune, flux excursion). It is
the canonical "press one button and recalibrate one qubit end-to-end"
script.
**What it runs.** In one outer loop over `qubits_to_calibrate`
(`Fast_calib.py:936`): transmission → coarse spec → fine spec → Rabi →
readout-frequency/gain optimization (`ReadOpt_wSingleShotFFMUX`) → qubit
freq/gain optimization (`QubitPulseOpt_wSingleShotFFMUX`) → optional T1+T2 →
final single-shot
(`Fast_calib.py:830-901`). Quality checks live in `QualityChecker`
(`Fast_calib.py:330-413`) with thresholds `MIN_FIDELITY=0.78`, `MIN_T1=12 us`,
`MIN_T2=2 us`, `MAX_FREQ_DRIFT=20 MHz`
(`Fast_calib.py:919-928`). Iterative refinement narrows the search window
when fidelity is below `MIN_FIDELITY`
(`Fast_calib.py:849-895`). Use this to repopulate every field of
`Qubit_Parameters[Q]` for one or several qubits.

### 7b. `Run_Experiments/RamseyFreqCalibs.py`
**When.** Mid-session, after the qubit frequency has drifted or after you
detuned via fast-flux (e.g. before a quench). Cheaper than re-running spec.
**What it runs.** `RamseyVsFF` (and optional `RamseyVsFFComp`,
`RamseyVsFF_Ramp`) which sweeps the FF gain near the current setpoint
(`Expt_FF[Q-1] ± 200`, 7 steps) at fixed Ramsey time and fits for the FF
gain at which the Ramsey detuning is zero
(`RamseyFreqCalibs.py:24-32, 44-47`). Output is `data['data']['center_gain']`
appended to `Gain_list` (`:47, :57`). Use to recenter `Expt_FF` so the
calibrated `Qubit_Parameters[Q]['Qubit']['Frequency']` matches reality. Pair
with `populations=True` (`:30, :41-42`) to also re-run
`CALIBRATE_SINGLESHOT_READOUTS.py` so the single-shot classifier remains
valid at the new FF point.

### 7c. `Run_Experiments/T1_TLS_calibs.py`
**When.** When you suspect a TLS sitting near the operating frequency
(symptoms: T1 drops sharply, varies wildly between qubits, jumps after
thermal cycle). Also useful as a periodic flux-stability check.
**What it runs.** `FFvsT1` from `Characterization_Sweeps/mT1vsFF.py`,
sweeping FF gain across `[-30000, 30000]` in 201 steps and measuring T1 at
each point
(`T1_TLS_calibs.py:75-80`). This produces a 2D map of T1 vs FF gain — TLS
appear as dark stripes. Inputs include `voltage_arrays` for the SPI rack
(`T1_TLS_calibs.py:55-63`), so the same script also validates the slow flux
DAC. Result: pick FF setpoints in `Expt_FF` that avoid the dark stripes;
update `Qubit_Parameters[Q]['Qubit']['Frequency']` accordingly via spec.

### 7d. `Run_Experiments/Loop_T1_T2.py`
**When.** Health-check sweep across all 8 qubits. Run at the start of each
shift to verify nothing has degraded vs. baseline.
**What it runs.** Loops `Q in [1..8]` and runs `T1MUX` then `T2RMUX` with
`T1_params={"stop_delay_us":100, "expts":80, "reps":150}` and
`T2R_params={"stop_delay_us":4, "expts":150, "reps":300,
"phase_shift_cycles":4, "relax_delay":200}`
(`Loop_T1_T2.py:48-92`). Plots all 8 onto two
`2×4` subplot grids (`Loop_T1_T2.py:39-46`). Fastest existing
"is the chip alive?" diagnostic. Does not write back; just plots.

### 7e. `Run_Experiments/Loop_SingleShot_Experiments.py`
**When.** Anytime you want to run *anything* (transmission, spec, Rabi,
single-shot, T1, T2, FF/qubit/Qblox sweeps) for an arbitrary subset of
qubits using the calibrated `Qubit_Parameters` baseline. It is the
general-purpose driver for one-off measurements.
**What it does.** Outer loop picks the qubit, sets `Qubit_Readout`,
`Qubit_Pulse`, builds per-qubit FF subsystem detunings via
`Expt_FF.subsys(Q, det=...)` (`Loop_SingleShot_Experiments.py:54-67`), then
runs every experiment whose `Run*` boolean is `True`
(`Loop_SingleShot_Experiments.py:83-300`). The transmission writeback
honours `cavmin` (`:262-265`). Use this script (rather than calling the
classes directly) so the standard config update / FF-subsystem / single-shot
classifier path is preserved.

---

## Recipe summary (cheat sheet)

| Step | Script | Reads | Writes (`Qubit_Parameters[Q]`) | Diagnostic |
|------|--------|-------|------------------------------|------------|
| 1 | `mTransmissionFFMUX.CavitySpecFFMUX` | `Readout.Frequency`, `cavmin` | `Readout.Frequency` | `peakFreq_min`, fit linewidth |
| 2 | `mSpecSliceFFMUX.QubitSpecSliceFFMUX` | `Qubit.Frequency`, `Readout.*` | `Qubit.Frequency` | `qubitFreq`, fit linewidth |
| 3 | `mAmplitudeRabiFFMUX.AmplitudeRabiFFMUX` | `Qubit.Frequency`, `Qubit.sigma` | `Qubit.Gain` | `pi_gain_fit` |
| 4 | `mSingleShotProgramFFMUX.SingleShotFFMUX` + `CALIBRATE_SINGLESHOT_READOUTS.py` | all of the above | `config['angle']`, `config['threshold']`, `config['confusion_matrix']` | fidelity, `ng_contrast`, `ne_contrast` |
| 5a | `mT1MUX.T1MUX` | calibrated π pulse | none (monitor) | T1 |
| 5b | `mT2RMUX.T2RMUX` | calibrated π/2 | none (monitor; feeds RamseyFreqCalibs) | T2R, ω |
| 5c | `mT2EMUX.T2EMUX` | calibrated π/2, π | none (monitor) | T2E |

If any step fails the quality check
(`Fast_calib.QualityChecker.print_summary`, `Fast_calib.py:399-413`), drop
back one step — usually re-running fine spec at lower drive gain or
re-running readout optimization fixes it before you bother repeating the
slow ones.
