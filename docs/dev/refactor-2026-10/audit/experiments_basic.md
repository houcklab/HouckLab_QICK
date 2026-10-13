# Audit: experiments_basic

Source root: `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/` (all paths below relative to it unless noted).
QICK installed: 0.2.334 (tProc v1, `asm_v1`). BaseConfig source: `Calib/initialize4Q.py` (`ro_chs=[0]`, `mixer_freq=0.0`, `res_ch=0`, `qubit_ch=1`, `trig_buffer_start=0.02`, `trig_buffer_end=0.02`, `trig_delay=0.082`, `cavity_winding_*=0`, `cavity_LO=0`).

---------------------------------------------------------------------------
## 0. Cross-file summary tables

### 0.1 Common structure (every ExperimentClass in this group)

| Element | What it does everywhere |
|---|---|
| `__init__(soc, soccfg, path, outerFolder, prefix, cfg, config_file, progress)` | Pure pass-through to `ExperimentClass.__init__` (base already accepts these; `progress` lands in `**kwargs`). Redundant in all 14 files except `ChargeDispersionQuasiCW` (also builds `self.prog`) and `SingleShotProgramFFMUX` (inits `threshold`/`angle` lists). |
| `acquire()` | Build Program(s) with `self.cfg` (same dict object, NOT copied), call `prog.acquire(...)`, optionally apply cavity-winding phase `exp(1j*(2*pi*cavity_winding_freq*pulse_freq + cavity_winding_offset))`, store `self.data = {'config': self.cfg, 'data': {...}}`, return it. `data['config']` aliases `self.cfg`, so later cfg mutations show up in it. |
| `display(data=None, plotDisp=..., figNum=..., **kwargs)` | `data = data or self.data`; extract `avgi[0][0]`/`avgq[0][0]` (readout ch 0, read 0); optional rotate/fit; `plt.figure(figNum)` (several bump with `while plt.fignum_exists(figNum): figNum += 1`); `plt.savefig(self.iname or self.iname[:-4]+suffix)`; `plotDisp` -> `plt.show(block=True); plt.pause(0.1)` else `fig.clf(True); plt.close(fig)`. |
| `save_data(data=None)` | `print(f'Saving {self.fname}')`; `super().save_data(data=data['data'])` (crashes on `data=None` despite the default). T1FF/AmplitudeRabiFF_N rename `self.fname` -> `..._Q{Qubit_number}.h5`; T2EMUX -> `..._n{num_pi_pulses}.h5`. ConstantTwoTone/SingleTone: no-op. QuasiCW: not overridden. |
| Runner usage pattern | `Cls.acquire(inst)`, `Cls.display(inst, data, ...)`, `Cls.save_data(inst, data)`, `Cls.save_config(inst)` (unbound-method style) in `Runners/runs/*.py` and `mAutoCoherence.py`. |

### 0.2 acquire() return structures and display() signatures

Shape notation (qick 0.2.334): RAveragerProgram returns per ro-ch arrays of shape `(n_reads=1, expts)`; AveragerProgram per ro-ch `(n_reads=1,)`. "n_adc" = number of declared readouts (2 where `[0,1]` hard-coded, else `len(ro_chs)` = 1).

| Class (file) | acquire signature | Return `data['data']` | display signature |
|---|---|---|---|
| CavitySpecFF (mTransmissionFF) | `acquire(self, progress=False, debug=False)` | `results`: ndarray `(1, n_adc, 2, N)` axes [read, ro_ch, I/Q, freq]; `fpts`: `(N,)` MHz. display() later adds `hanger_fit_popt (5,)`, `hanger_fit_perr (5,)`, `hanger_fit_f0_mhz`, `hanger_fit_min_freq_mhz`, `hanger_raw_min_freq_mhz`, `hanger_fit_Qtot`, `hanger_fit_Qext`, `hanger_fit_Qint`, `hanger_fit_kappa_mhz` (0-d arrays). Attrs: `peakFreq_min`, `peakFreq_max`. | `display(self, data=None, plotDisp=False, figNum=1, fit=True, **kwargs)` |
| QubitSpecSliceFF (mSpecSliceFF) | `acquire(self, progress=False, debug=False)` | `x_pts (expts,)` MHz; `avgi`,`avgq` ndarray `(2, 1, expts)` (winding-rotated). display() adds `two_tone_peak_freqs`, `two_tone_peak_amps`, `lorentz_num_fits` (int), `lorentz_centers`, `lorentz_fwhm`, `lorentz_gamma`, `lorentz_amplitudes`, `lorentz_offsets`, `lorentz_r2`. Attr: `qubitFreq`. | `display(self, data=None, plotDisp=False, figNum=1, min_sep=0.1, **kwargs)`; kwargs: `min_sep_mhz` (default=min_sep), `fit_window_mhz` (3*min_sep), `prominent_ratio` (0.35) |
| AmplitudeRabiFF (mAmplitudeRabiFF) | `acquire(self, progress=False, debug=False)` | `x_pts (expts,)` float64 gain; `avgi`,`avgq` `(2,1,expts)` winding+principal-axis rotated; `iq_rotation_rad` float. display(fit=True) adds `fit_i_popt (4,)`, `fit_i_pi_gain`, `fit_q_popt`, `fit_q_pi_gain`. Attrs `fit_i`, `fit_q`. | `display(self, data=None, plotDisp=True, figNum=1, fit=False, **kwargs)` (note plotDisp default True) |
| AmplitudeRabiFF_N (mAmplitudeRabiFF_noUpdate) | `acquire(self, progress=False, debug=False)` | `x_pts` = `np.linspace(gain_start, gain_end, gainNumPoints)` float; `avgi`=`[[ndarray (N,)]]`, `avgq` same (nested lists, ADC0 only, winding-rotated). Attrs after display: `rotation_phase`, `fit_i`, `fit_q`. | `display(self, data=None, plotDisp=False, figNum=1, fit=True, rotate=True, **kwargs)` |
| ChiShift (mChiShift) | `acquire(self, progress=False, debug=False)` | `results_ground`, `results_01`: ndarray `(1, n_adc, 2, N)`; `fpts (N,)` MHz. Chi value printed/titled only, not stored. | `display(self, data=None, plotDisp=False, figNum=1, **kwargs)` |
| ConstantTwoTone (mConstantTwoTone) | `acquire(self, progress=False, debug=False)` | returns (not stored in self.data) `{'config', 'data': {res_freq_MHz, res_gain, qubit_freq_MHz, qubit_gain, tone_length_us}}` scalars | `display(...)`: no-op |
| SingleTone (mSingleTone) | `acquire(self, progress=False)` | returns `None` | `display(self, data=None, plotDisp=False, figNum=1, **kwargs)`: no-op |
| T1FF (mT1FF) | `acquire(self, progress=False, debug=False)` | `x_pts (expts,)` us; `avgi`,`avgq` `(n_adc,1,expts)` winding-rotated; `qfreq` = f_ge. Top-level (not in 'data', not saved): `rotation_angle`, `min_max` if in cfg. Fit result NOT stored (title only). | `display(self, data=None, plotDisp=False, figNum=1, **kwargs)` |
| T2EMUX (mT2EFF) | `acquire(self, progress=False)` | `x_pts (expts,)` us; `avgi`,`avgq` raw qick lists of n_adc arrays `(1,expts)` (no winding); `qfreq`. Top-level `rotation_angle`, `min_max` (conditional). Fit not stored. | `display(self, data=None, plotDisp=False, figNum=1, **kwargs)` |
| T2R (mT2R) | `acquire(self, progress=False, debug=False)` | `x_pts`, `avgi`, `avgq` raw qick lists (no winding). Fit in `self.osc_fit`, `self.env_fit` only. | `display(self, data=None, plotDisp=False, figNum=1, **kwargs)`; kwarg `fft_peak_dominance` (2.5) |
| T1_SS (mT1_SS) | `acquire(self, threshold=None, angle=None, excited_pulse=2, progress=False)` | `Exp_values (expts,)` excited fraction; `RotatedIQ` list of expts tuples `(i (1,reps), q (1,reps))`; `threshold`; `angle`; `wait_times (expts,)` us | `display(self, data=None, plotDisp=False, figNum=1, **kwargs)` |
| ChargeDispersion (mChargeDispersion) | `acquire(self, progress=False, debug=False)` | `avgi`,`avgq`: list of n_adc arrays `(1,)`; `amp` ndarray `(n_adc,1)` | `display(self, data=None, plotDisp=False, figNum=1, **kwargs)` |
| ChargeDispersionQuasiCW (mChargeDispersionQuasiCW) | `acquire(self, progress=False, debug=False, load_pulses=True, print_time=False)` | returns `{'data': ...}` with NO 'config' key: `x_pts (expts,)`, `avgi`/`avgq` `(2,1,expts)` (winding), `raw_i`/`raw_q` `(reps, expts)` (un-normalized accumulator, winding), `raw_amp (reps,expts)` = abs^2, `amps_per_rep (reps,)` | inherited no-op |
| SingleShotProgramFFMUX (mSingleShotProgramFFMUX) | `acquire(self, progress=False)` | Normal: per read index r: `i_g{r}`,`q_g{r}`,`i_e{r}`,`q_e{r}` `(reps,)`; plus alias keys with enumerate index i when `str(r)!=str(i)`; `threshold` list, `angle` list, `thermal_mode=False`. Thermal (`number_of_pulses==0`): `i_g/q_g/i_e/q_e{r}`, `i_thermal{r}`, `q_thermal{r}`, `thermal_labels{r}`, `thermal_population_tail{r}`, `thermal_center_g{r}`, `thermal_center_e{r}`, `thermal_md2{r}`, `thermal_projection{r}`, `thermal_projection_threshold{r}`, aliases (i_g,q_g,i_e,q_e,i_thermal,q_thermal,thermal_labels), `threshold`, `angle`, `thermal_mode=True`, `thermal_fit_type=1`. Attrs: `fid`, `threshold`, `angle` (lists), `data_in_hist`. | `display(self, data=None, plotDisp=False, figNum=1, ran=None, **kwargs)` (`ran` ignored) |

### 0.3 tProc timing conventions (keep byte-identical)

`us2cycles(x)` with no gen/ro arg = tProc clock. Raw integers (200) are tProc cycles.

| Program | end of initialize() | body() sequence | measure() kwargs |
|---|---|---|---|
| CavitySpecFFProg (Averager) | `synci(200)` | `sync_all(200)`; measure; `sync_all(us2cycles(cav_relax_delay))` | `pulse_ch=res_ch, adcs=cfg["ro_chs"], adc_trig_offset=us2cycles(adc_trig_offset), wait=True, syncdelay=us2cycles(10)` |
| QubitSpecSliceFFProg (RAverager) | none (just print) | `sync_all()`; `pulse(qubit_ch, t=us2cycles(1))`; `sync_all(us2cycles(0.5))`; measure; `sync_all(us2cycles(relax_delay))` | `adcs=[0,1]`, offset as above, `wait=True, syncdelay=us2cycles(10)` |
| AmplitudeRabiFFProg (RAverager) & (Averager, noUpdate) | `sync_all(us2cycles(0.05))` | `sync_all()`; `trigger(pins=[0], t=us2cycles(1+trig_delay-trig_buffer_start), width=trig_length)`; `pulse(qubit_ch, t=us2cycles(1))`; `sync_all(us2cycles(0.05))`; measure; `sync_all(us2cycles(relax_delay))` | `adcs=[0,1]`, `syncdelay=us2cycles(10)` |
| ChiProgram (Averager) | none | `sync_all(us2cycles(0.05))`; if pulse_01: `pulse(qubit_ch, t=us2cycles(0.1))`; `sync_all(us2cycles(0.05))`; measure; `sync_all(us2cycles(cav_relax_delay))`; if pulse_01: `sync_all(us2cycles(relax_delay-cav_relax_delay))` | `adcs=[0]`, `syncdelay=us2cycles(10)` |
| ConstantTwoToneProg (Averager) | `synci(200)` | `pulse(res_ch)`; `pulse(qubit_ch)`; `sync_all()` | none (no readout declared) |
| ConstantTone (Averager) | `synci(200)` | `pulse(res_ch)`; `sync_all()` | none |
| T1Program (mT1FF, RAverager) | `sync_all(us2cycles(0.05))` | `sync_all()`; `trigger(pins=[0], t=us2cycles(0.01+trig_delay-trig_buffer_start), width=trig_length)`; `pulse(qubit_ch, t=us2cycles(0.01))`; `sync_all()`; `sync(q_rp, r_wait)`; measure | `adcs=self.ro_chs`, `syncdelay=us2cycles(relax_delay)` |
| T2EProgram (RAverager) | `sync_all(us2cycles(0.2))` | `sync_all(us2cycles(0.05))`; trigger(t=us2cycles(0.01+trig_delay-trig_buffer_start)); `setup_and_pulse(pi2, phase=0, t=us2cycles(0.01))`; `sync_all(); sync(r_wait)`; repeat num_pi_pulses x [trigger(t=us2cycles(trig_delay-trig_buffer_start)); setup_and_pulse(pi, phase=deg2reg(90)); `sync_all(); sync(r_wait)`]; trigger; setup_and_pulse(pi2, phase=0); `sync_all(us2cycles(0.05))`; measure | `adcs=self.ro_chs`, `syncdelay=us2cycles(relax_delay)` |
| T2RProgram (RAverager) | `sync_all(us2cycles(0.2))` | `regwi(q_rp, r_phase, 0)`; `pulse(qubit_ch)`; `mathi(q_rp, r_phase, r_phase2, "+", 0)`; `sync_all()`; `sync(q_rp, r_wait)`; `pulse(qubit_ch)`; `sync_all(us2cycles(0.05))`; measure. No trigger. | `adcs=self.ro_chs`, `syncdelay=us2cycles(relax_delay)` |
| T1Program (mT1_SS, Averager) | `sync_all(us2cycles(0.05))` | `sync_all(us2cycles(0.05))`; `pulse(qubit_ch)`; `sync_all(us2cycles(variable_wait))`; measure. No trigger. | `adcs=self.ro_chs`, `syncdelay=us2cycles(relax_delay)` |
| ChargeDispersionProgram (Averager) | `sync_all(us2cycles(0.2))` | `regwi(q_rp, r_phase, 0)`; `pulse`; `sync_all()`; `sync(q_rp, r_wait)` (r_wait = us2cycles(1/df)); `pulse`; `sync_all(us2cycles(0.05))`; measure. No trigger. | `adcs=self.ro_chs`, `syncdelay=us2cycles(relax_delay)` |
| ChargeDispersionQuasiCWProg (RAverager) | none | identical to QubitSpecSliceFFProg body | `adcs=[0,1]`, `syncdelay=us2cycles(10)` |
| SingleShotProgram (Averager) | `sync_all(200)` | `sync_all()`; if Pulse: N x [`trigger(pins=[0], t=us2cycles(trig_delay-trig_buffer_start), width=trig_length)`; `setup_and_pulse(flat_top|arb, phase=0, gain=qubit_gain)`; `sync_all(us2cycles(0.05))`]; `sync_all(us2cycles(0.05))`; measure | `adcs=self.ro_chs`, `adc_trig_offset=self.adc_trig_offset_cycles` (=us2cycles(adc_trig_offset)), `wait=True`, `syncdelay=us2cycles(relax_delay)` |

Shared constructs:
- Gaussian: `pulse_sigma = us2cycles(sigma, gen_ch=qubit_ch)`; `length = us2cycles(sigma*4, gen_ch=qubit_ch)`; `add_gauss(ch=qubit_ch, name="qubit", ...)`. (Loopback/dead class uses `us2cycles(sigma)*4` in tProc cycles.)
- arb style phase = `deg2reg(90)` (Rabi, T1FF, Spec Gauss, Chi arb); flat_top phase = `deg2reg(0)`; SingleShot/T2R/T2E pi2 phase 0; T2E pi phase 90.
- Flat-top: `style='flat_top', waveform="qubit", length=us2cycles(flattop_length, gen_ch=qubit_ch)` when `cfg["flattop_length"] != None`.
- PMOD trigger `pins=[0]`, `width = us2cycles(trig_buffer_start + trig_buffer_end + 4*sigma [+ flattop_length])`, start `= pulse_t + trig_delay - trig_buffer_start`. Fired by: AmplitudeRabiFF, AmplitudeRabiFF_N, T1FF, T2EMUX, SingleShotProgram. NOT fired by: QubitSpecSliceFF, ChiShift, T2R, T1_SS, ChargeDispersion, QuasiCW.
- Readout: `declare_readout(ch, length=us2cycles(readout_length), freq=pulse_freq, gen_ch=res_ch)` (tProc-clock count used as readout sample count) everywhere except SingleShotProgram (`us2cycles(readout_length, ro_ch=ch)`).
- `declare_gen(res_ch, nqz, mixer_freq=cfg["mixer_freq"], ro_ch=ro_chs[0])` only in CavitySpecFF, QubitSpecSliceFF, ChiShift, ConstantTone, QuasiCW (and dead WITHUPDATE/Loopback). Others `declare_gen(res_ch, nqz)` (OK only because mixer_freq=0.0).
- Res pulse: `set_pulse_registers(res_ch, style="const", freq=freq2reg(pulse_freq, gen_ch=res_ch, ro_ch=ro_chs[0] | 0), phase=res_phase (0 in CavitySpec/Chi/ConstantTone/TwoTone), gain=pulse_gain, length=us2cycles(length))` (no gen_ch -> tProc cycles!) except SingleShotProgram (gen-clock + extension) and ConstantTwoTone (`min(us2cycles(tone_length, gen_ch), 65535)`).
- Sweep registers: qubit page `ch_page(qubit_ch)`; scratch regs `r_wait=3`, `r_phase2=4`; `sreg(qubit_ch,"freq"|"gain"|"phase")`. Register allocation in asm_v1 is top-down (`32 - nRegs`), so 3/4 are safe.

### 0.4 Duplicated helpers (unify in `qicklab/analysis/`)

| Helper | Locations | Notes / proposed home |
|---|---|---|
| `Amplitude_IQ(I, Q, phase_num_points)` (grid-search phase minimizing Q range over [0, pi]) | mAmplitudeRabiFF_noUpdate.py:239-253 (500 pts), mT1FF.py:221-235 (200 pts), mT2EFF.py:247-261 (200 pts) | `analysis/iq.py::min_q_range_phase(i, q, n=...)`; keep per-caller n to preserve results |
| Principal-axis angle | mAmplitudeRabiFF.py:12-27 `iq_rotation_angle` (0.5*arctan2(2<iq>, <ii>-<qq>)); utils.py:65-140 `project_iq_signal` (0.5*angle(sum(dev^2))) | same math; `analysis/iq.py::principal_axis_angle` |
| `rotate_iq(avgi, avgq)` (rotate mean onto +real) | mT2R.py:12-16, mChargeDispersion.py:11-15 (identical; latter unused) | `analysis/iq.py` |
| `cos_func`, `fit_rabi_cosine` | mAmplitudeRabiFF.py:30-79, mAmplitudeRabiFF_noUpdate.py:11-60 (identical simple: single guess, `pi_gain=P/2`); utils.py:759-848 (robust multi-start, `pi_gain` = first opposite extremum, adds `x_fit_dense`/`y_fit_dense`/`fit_error`) | Local defs SHADOW the utils star import in mAmplitudeRabiFF. Behavior-preserving default = simple version. `analysis/rabi.py` |
| Exponential decay fit `_expFit(x, a, T1, c)` + guess (`a=y0-y_end`, `c=y_end`, `T1 = x at y≈a/2.6+c`) | mT1FF.py:142-157, mT2EFF.py:179-195 (identical) | `analysis/coherence.py::fit_exp_decay` |
| `rotation_angle`/`min_max` normalization block | mT1FF.py:127-140, mT2EFF.py:164-178 (T2E also handles None) | `analysis/coherence.py` |
| Lorentzian peak model | mSpecSliceFF.py:121-122 `_lorentzian` == utils.py:348 `lorentzian_peak` (algebraically identical) | `analysis/spectroscopy.py` |
| Windowed Lorentzian refine | mSpecSliceFF.py:124-185 `_fit_lorentzian_near_peak` (R2>=0.60 gate, >=6 pts) vs utils.py:505-546 `_refine_peak_lorentzian` (>=5 pts) | different gates; keep spec version for SpecSlice |
| Two-peak selection | mSpecSliceFF.py:204-241 (local maxima, min_sep, prominent_ratio) vs utils.py:398-479 `find_two_tone_peaks` (savgol+prominence) | different algorithms |
| Hanger fit + report/plot | mTransmissionFF.py:94-163 & 192-247 vs Runners/runs/basic.py:52-142 `run_transmission_fit` | `analysis/resonator.py::fit_hanger` (+`hanger_model_db`, `fit_hanger_transmission` from utils.py:240-331) |
| Cavity-winding phase | mSpecSliceFF.py:92-95, mAmplitudeRabiFF.py:181-182, mAmplitudeRabiFF_noUpdate.py:140-141, mT1FF.py:100-103, mChargeDispersionQuasiCW.py:106-111 & 127-132 | `core/iq.py::apply_cavity_winding(sig, cfg)`; NOT applied in CavitySpecFF, ChiShift, T2E, T2R, T1_SS, ChargeDispersion |
| `collect_shots` (di_buf/reshape/normalize) | mT1_SS.py:68-74, mSingleShotProgramFFMUX.py:99-107 (dead), 253-264, 856-860 (dead); also mActiveResetVerify.py:327, mModifiedRamsey.py:790, mUndrivenSingleShot.py:97 | `core/shots.py` |
| Readout-window / tone-extension timing block | mSingleShotProgramFFMUX.py:148-189; duplicated in mActiveResetVerify.py:127-188, mModifiedRamsey.py:419-584, mUndrivenSingleShot.py:56-81 | `core/readout.py::configure_readout(prog, cfg)` — single source of truth (it is load-bearing for active-reset threshold transfer) |
| fig-number bump `while plt.fignum_exists(num=figNum): figNum += 1` | mAmplitudeRabiFF:237, noUpdate:194, T1FF:160, T2EFF:198, T2R:425, T1_SS:122, ChargeDispersion:154 | `analysis/plotting.py::new_figure` |
| `save_data` override (print + `super().save_data(data['data'])`) | 11 files | base-class default |

---------------------------------------------------------------------------
## 1. mTransmissionFF.py (256 lines)

1. Purpose: resonator transmission vs frequency (Python-loop sweep, one AveragerProgram per point) + optional hanger fit that rewrites `pulse_freq`.
2. Symbols:
   - `CavitySpecFFProg(AveragerProgram)` — const res tone + readout. Reads: `res_ch, nqz, mixer_freq, ro_chs, readout_length, pulse_freq, pulse_gain, length, adc_trig_offset, cav_relax_delay` (+ qick: `reps`, `rounds`).
   - `CavitySpecFF(ExperimentClass)` — sweep `pulse_freq ± TransSpan` (`np.linspace`, inclusive, `TransNumPoints`), uses `acquire_with_retry`; display: I/Q/amp plot + hanger fit plot.
3. cfg READ: `pulse_freq, TransSpan, TransNumPoints, cavity_LO` (+program keys). WRITTEN: `pulse_freq` (L49, each sweep point -> left at `fpts[-1]` after acquire); `pulse_freq = fit_min_freq_mhz` (L135, display fit=True). Attrs: `peakFreq_min` (argmin |sig|, overwritten by fit min L136), `peakFreq_max`, `data`.
4. Imports: `from qick import *`; `CoreLib.Experiment.ExperimentClass`; `Experiments.utils import *` (star; uses `acquire_with_retry`, `fit_hanger_transmission`). Unused: `gauss`, `datetime` (also rebound by utils star to the class), `tqdm` used with disable=True only. Imported by: Runners/runs/basic.py:2, Runners/runs/charge_parity.py:14. `CavitySpecFFProg`: unused externally.
5. Dead: `y_edge`/`depth_db` L98-100 (computed, unused); L203 `fit_min_freq_mhz` recomputed and unused; `start` only for print. Trailing blank lines L253-256.
6. Lab notes:
   - L50-52: one slice starts TransNumPoints x rounds tProc programs; a charge sweep runs many slices; the rare stale-shot-counter failure is retried rather than losing the sweep (see `acquire_with_retry`). -> architecture (acquisition reliability).
   - L80/L82: `fpts` are IF-style MHz; plotted axis = `(fpts + cavity_LO/1e6)/1e3` GHz. -> parameters (`cavity_LO`, `pulse_freq` units).
7. Noise: L13, 14, 18, 21 (trailing), L32, L35-37, L64, L96, L107-111, L167, L192.
8. Bugs/suspicious:
   - L126 `kappa_mhz = (f0_fit / Qext_fit) / 1e6`: f0 is in MHz, so f0/Qext is already MHz; /1e6 makes it 1e6 too small (same bug Runners/runs/basic.py:89). Also uses Qext (coupling rate), labelled as kappa.
   - L49 + L135: acquire mutates `self.cfg["pulse_freq"]` and leaves it at the last sweep point; if fit fails or `fit=False`, saved config JSON records `pulse_freq = fpts[-1]` not the sweep centre (charge_parity.py:1841-1843 works around this).
   - L82/L132: hanger fit is done on IF `fpts`; f0 reported in IF MHz, absolute only if `cavity_LO=0`.
   - L85 `20*log10(amp)` -> -inf if amp==0.
   - `save_data(data=None)` -> TypeError (`None['data']`).
9. Destination: `qicklab/experiments/transmission.py` (`TransmissionProgram`, `Transmission`; keep alias `CavitySpecFF`). Move hanger fit/report block L94-163 to `qicklab/analysis/resonator.py`.
10. Style: star imports; unused imports; `except Exception` broad; matplotlib state-machine API; class name `CavitySpecFF` misleading (no FF).

---------------------------------------------------------------------------
## 2. mSpecSliceFF.py (364 lines)

1. Purpose: two-tone qubit spectroscopy, hardware frequency sweep (RAverager), IQ projection, up to two peaks + Lorentzian fits.
2. Symbols:
   - `QubitSpecSliceFFProg(RAveragerProgram)` — qubit freq register sweep `start`+`step` (MHz -> `freq2reg`). Reads: `res_ch, nqz, mixer_freq, ro_chs[0], qubit_ch, qubit_nqz, readout_length, pulse_freq, start, step, Gauss, sigma (Gauss), qubit_gain, qubit_length (const), res_phase, pulse_gain, length, adc_trig_offset, relax_delay`; update: `f_step` added to `sreg(qubit_ch,"freq")`. Hard-codes readouts/adcs `[0, 1]` and `freq2reg(..., ro_ch=0)`.
   - `QubitSpecSliceFF(ExperimentClass)`: acquire (winding), display (peak pick + Lorentzians), `get_amplitude_slice` (DEAD), save_data.
3. cfg READ: `cavity_winding_freq, pulse_freq, cavity_winding_offset`; display `.get`: `qubit_gain, Gauss, sigma, qubit_length`. WRITTEN: none. Attr: `qubitFreq` (argmax of `project_iq_signal`), program attr `qubit_length_us` (unused).
4. Imports: qick *, ExperimentClass, `utils import *` (uses `project_iq_signal`; `curve_fit` arrives ONLY via the utils star import — implicit dependency). Unused: `gauss`, `datetime`, `tqdm`, `time`. Imported by: mAutoCoherence.py:53, Runners/runs/basic.py:5, charge_parity.py:13, zero_span.py:5. `QubitSpecSliceFFProg` referenced only in a commented line in mOptimizeReadoutandPulse_FF.py:1670.
5. Dead: `get_amplitude_slice` L349-357 (no references anywhere); `self.qubit_length_us` L42/46; L104-106 re-read of x_pts/avgi/avgq; L86 commented kwarg.
6. Lab notes:
   - L108-113 + L194-197: index `[0][0]` = first readout channel, first read; plain argmax flattened both ADC channels and overran x_pts (past bug). Use background-subtracted principal-axis projection, not |I+iQ|: magnitude is dominated by the large noisy background quadrature and buries the qubit feature (dated evidence lives in utils.project_iq_signal docstring: 2026-06-02 Q6 QubitSpecFF feature in I at ~3054 MHz missed for Q-noise spikes at 3038/3069 MHz; 2026-09-02 12:03 CSTQ03/Q2 broad ~3753 MHz response inverted into a dip). -> experiment:qubit_spec.
   - L163-169: Lorentzian accepted only if R^2 >= 0.60, 0 < gamma < window width, centre inside window, >= 6 points in window. -> experiment:qubit_spec (tuning).
   - display defaults: `fit_window_mhz = 3*min_sep`, `prominent_ratio = 0.35` (runners pass 0.5 MHz, 0.1). -> experiment:qubit_spec.
7. Noise: L19, 20, 21, 25, 26, 28 ("### Start fast flux" stale), 29, 31, 34, 57, 58, 69, 70, 73-75, 86-87, 91, 97, 204-206, 243-245, 257-259, 285, 294-296, 316-318.
8. Bugs/suspicious:
   - L21/L61: readouts `[0,1]` hard-coded, ignores `cfg["ro_chs"]`; `avgi` shape (2,1,N) — ADC1 data is acquired and saved but never used.
   - L277 prints "amplitude^2" but the trace is the rotated projection (stale label); L274 OK.
   - L313/L345: `plt.show()` without block, figures always closed; `self.iname` itself never saved (only `_IQ.png`, `_Amp2_LorentzFits.png`).
   - Cavity winding applied with scalar `pulse_freq` (constant phase) — harmless with winding=0.
9. Destination: `qicklab/experiments/qubit_spec.py` (`QubitSpecProgram`, `QubitSpec`; alias `QubitSpecSliceFF`). Move `_lorentzian`, `_fit_lorentzian_near_peak`, peak selection L204-241 to `qicklab/analysis/spectroscopy.py` (next to `project_iq_signal`).
10. Style: star imports (implicit `curve_fit`), nested function defs inside display, bare `except Exception: return None`, misspelling `pulse_qubit_lenth`.

---------------------------------------------------------------------------
## 3. mAmplitudeRabiFF.py (290 lines)

1. Purpose: amplitude Rabi with hardware gain sweep (RAverager) + principal-axis IQ rotation + optional cosine fit.
2. Symbols:
   - `iq_rotation_angle(signal_trace)` — principal-axis angle (rad) of IQ trace. Used internally only.
   - `cos_func(x, y0, A, P, phi)`, `fit_rabi_cosine(x, y)` — simple cosine fit; `pi_gain = P/2`. Shadow the same-named utils functions (utils star import is BEFORE these defs).
   - `AmplitudeRabiFFProg(RAveragerProgram)` — reads `qubit_ch, res_ch, nqz, qubit_nqz, readout_length, pulse_freq, ro_chs[0], f_ge, sigma, flattop_length, start, res_phase, pulse_gain, length, trig_buffer_start, trig_buffer_end, trig_delay, adc_trig_offset, relax_delay, step` (update adds raw `step` to `sreg(qubit_ch,"gain")`). Readouts `[0,1]` hard-coded.
   - `AmplitudeRabiFF(ExperimentClass)`.
3. cfg READ: `cavity_winding_freq, pulse_freq, cavity_winding_offset`. WRITTEN: none. Attrs `fit_i`, `fit_q`.
4. Imports: qick *, ExperimentClass, curve_fit, `utils import *` (nothing from it is actually used — its `cos_func`/`fit_rabi_cosine` are shadowed). Unused: `gauss`, `datetime`, `tqdm`, `time`. Imported by: mAutoCoherence.py:54, Runners/runs/basic.py:7. `iq_rotation_angle`, `cos_func`, `fit_rabi_cosine`, `AmplitudeRabiFFProg`: unused externally.
5. Dead: L113-115 commented const pulse; L139 commented FF pulse; L167 commented program; `self.pulse_qubit_lenth += flattop_length` L116 (never read); prints L100, L103 ('yes!'), L105 (debug).
6. Lab notes:
   - L13-21: rotating by -angle aligns max-variance (g->e) axis with I so Rabi lands in one quadrature; this is a data-driven alternative to `cavity_winding_*`, which is a frequency-dependent cable-delay correction, NOT a quadrature alignment. -> architecture (IQ conventions) + parameters (`cavity_winding_freq/offset`).
   - L112 (also noUpdate L86, T1FF L44, ChiShift L41): flat_top pulse's flat segment does NOT follow the swept gain register (only the ramp `gain` reg is updated; flat part uses `gain2`) -> register-swept Rabi is invalid with flattop; runner uses `AmplitudeRabiFF_N` (software sweep) when `flattop_length` is set (basic.py:276). -> experiment:amplitude_rabi.
   - L184-187: principal-axis rotation is layered on top of winding phase, stored as `iq_rotation_rad`, does not replace the fit. -> experiment:amplitude_rabi.
   - L42-44: period guess `P0 = max(sweep span, 1)` assumes >= ~half an oscillation visible. -> experiment:amplitude_rabi.
7. Noise: L38, 46 (stale "phase guess from first point" — phi0=0), 86, 87, 89, 90, 91, 95, 143, 155, 158-160, 166, 172, 174, 178.
8. Bugs/suspicious:
   - L188: `iq_rotation_angle(np.ravel(signal))` estimates the axis over BOTH ADCs concatenated (shape (2,1,N)); ADC1 content biases the rotation applied to ADC0.
   - L102/131: `!= None` comparisons.
   - display default `plotDisp=True` (blocks) unlike all others.
   - Shadowed utils `fit_rabi_cosine` (robust) is never used here though display L245-261 checks for its `x_fit_dense` key — sign the author expected the utils version. Decide explicitly in refactor (preserve = simple version).
9. Destination: `qicklab/experiments/amplitude_rabi.py` (`AmplitudeRabiProgram`, `AmplitudeRabi`); fits -> `qicklab/analysis/rabi.py`; `iq_rotation_angle` -> `qicklab/analysis/iq.py`.
10. Style: star import shadowing, debug prints, `lenth` typo, `!= None`.

---------------------------------------------------------------------------
## 4. mAmplitudeRabiFF_noUpdate.py (253 lines)

1. Purpose: amplitude Rabi via Python loop over gains (one AveragerProgram per gain) — required for flat-top pulses.
2. Symbols:
   - `cos_func`, `fit_rabi_cosine` — byte-identical copies of mAmplitudeRabiFF.py:30-79.
   - `AmplitudeRabiFFProg(AveragerProgram)` — SAME CLASS NAME as mAmplitudeRabiFF's RAverager program. Reads `res_ch, nqz, qubit_ch, qubit_nqz, readout_length, pulse_freq, ro_chs[0], f_ge, sigma, flattop_length, qubit_gain, trig_buffer_start, trig_buffer_end, trig_delay, res_phase, pulse_gain, length, adc_trig_offset, relax_delay` (+`reps`, `rounds`). Readouts `[0,1]`.
   - `AmplitudeRabiFF_N(ExperimentClass)`.
   - `Amplitude_IQ(I, Q, phase_num_points=500)` — module-level, defined after the class, used in display.
3. cfg READ: `reps, rounds, gain_start, gain_end, gainNumPoints, cavity_winding_freq, pulse_freq, cavity_winding_offset, Qubit_number`. WRITTEN: `reps *= rounds` (L127), `rounds = 1` (L128), `qubit_gain = int(g)` (L135, left at last gain). Attrs `rotation_phase`, `fit_i`, `fit_q`, `fname` (renamed).
4. Imports: qick *, ExperimentClass, curve_fit, tqdm, time. Unused: `gauss`, `datetime`. No utils import. Imported by Runners/runs/basic.py:8. Program, fits, `Amplitude_IQ`: unused externally.
5. Dead: L232 commented print; `self.pulse_qubit_lenth += flattop_length` L87 unused.
6. Lab notes:
   - L86: flat-top flat part does not update with gain (dup of #3). -> experiment:amplitude_rabi.
   - L159-161: `Amplitude_IQ` finds the phase (grid over [0, pi], 500 pts) minimizing Q range; multiplying by exp(i*phase) collapses contrast onto I. -> analysis docs (IQ rotation).
   - L205-207: a failed cosine fit (no visible oscillation) returns a runaway period; drawing its pi marker autoscales x to ~1e9, so the marker is hidden when outside the swept range. -> experiment:amplitude_rabi.
7. Noise: L19, 27, 67, 68, 69, 72, 108, 119-121, 173, 190, 240-247 (docstring: keep one line).
8. Bugs/suspicious:
   - L127-128: mutates `reps`/`rounds` in the experiment cfg (saved config shows the product, rounds=1); calling acquire twice is idempotent only because rounds becomes 1.
   - L129/L135: `x_pts` are float linspace values but the played gain is `int(g)` — axis vs actual gain mismatch < 1 DAC unit.
   - L172-188: fit not guarded; a curve_fit failure raises out of display (AmplitudeRabiFF guards with try).
   - L201-203 plot `fit_i['yfit']` at data points only (coarse).
   - Duplicate Program class name with mAmplitudeRabiFF (import collisions if both star-imported).
9. Destination: merge into `qicklab/experiments/amplitude_rabi.py` as `AmplitudeRabiSoftSweep` (alias `AmplitudeRabiFF_N`), program `AmplitudeRabiPointProgram`; fits -> `analysis/rabi.py`; `Amplitude_IQ` -> `analysis/iq.py`.
10. Style: shadowed builtin `complex` (L248), docstring with empty params, function defined after use.

---------------------------------------------------------------------------
## 5. mChiShift.py (160 lines)

1. Purpose: dispersive shift: transmission sweep with/without a pi pulse; chi = f(|1>) - f(|0>) from argmin.
2. Symbols:
   - `ChiProgram(AveragerProgram)` — reads `res_ch, nqz, mixer_freq, ro_chs, readout_length, pulse_freq, qubit_ch, qubit_nqz, qubit_freq, pulse_gain, length, sigma, flattop_length, pi_gain, pulse_01, adc_trig_offset, cav_relax_delay, relax_delay`. WRITES `cfg["rounds"] = 1` (L15).
   - `ChiShift(ExperimentClass)`.
3. cfg READ (class): `pulse_freq, cavity_shift, TransSpan, TransNumPoints, cavity_LO`. WRITTEN: `pulse_freq` (each point; left at last), `pulse_01` (False/True), `rounds` (via program).
4. Imports: qick *, ExperimentClass, tqdm, time. Unused `gauss`, `datetime`. Commented import L2 (q4diamond socProxy). Imported by Runners/runs/basic.py:6. `ChiProgram`: unused externally.
5. Dead: L2 commented import; `results_12` L82 unused; `start_inital` L86 unused; `pulse_qubit_lenth += flattop_length` L42 unused.
6. Lab notes: L41 flattop note (dup). Sweep is `center = pulse_freq + cavity_shift`, `start = center - span`, `step = 2*span/expts` (half-open, excludes `center+span`), unlike CavitySpecFF (inclusive linspace). -> experiment:chi_shift.
7. Noise: L16, 17, 26, 50, 62, 64-66 ("Transmission Experiment basic" — wrong), 112, 116, 120 ("Find peak frequencies" — finds minima), 138. Trailing blanks L156-160.
8. Bugs/suspicious:
   - Program uses `cfg["qubit_freq"]` while runner (basic.py:248-253) passes `f_ge`; works only because `working_config` also holds `qubit_freq` = same centre. Key mismatch.
   - L15 sets `cfg["rounds"]=1` inside initialize (mutates experiment cfg; qick reads rounds after make_program so it takes effect).
   - No pin-0 trigger fired (Rabi/T1 fire it) — if the trigger gates the drive path, the pi pulse is blocked. Verify hardware role of pin 0.
   - L134-151: figure never closed when `plotDisp=False` (leak); figure `figNum+1`; no `tight_layout`.
   - Chi not stored in data (not saved to h5).
9. Destination: `qicklab/experiments/chi_shift.py` (`ChiShiftProgram`, `ChiShift`).
10. Style: unused vars, `!= None`, misleading docstrings.

---------------------------------------------------------------------------
## 6. mConstantTwoTone.py (88 lines)

1. Purpose: start resonator + qubit tones (near-CW) without readout; fire-and-forget.
2. Symbols: `ConstantTwoToneProg(AveragerProgram)` — reads `res_ch, nqz, qubit_ch, qubit_nqz, pulse_freq, qubit_freq, tone_length, qubit_gain, pulse_gain` (+`reps`). Pulse length `min(us2cycles(tone_length, gen_ch), 65535)`. `ConstantTwoTone(ExperimentClass)`: acquire does `prog.config_all(soc); soc.start_src("internal"); soc.start_tproc()` and prints.
3. cfg READ: above + `.get`: `mixer_freq, cavity_LO, ro_chs` (prints). WRITTEN: none.
4. Imports: qick *, ExperimentClass only. Imported by Runners/runs/basic.py:4. Program: unused externally.
5. Dead: none. display/save_data are no-op stubs.
6. Lab notes: 16-bit pulse-length register caps each tone at 65535 generator cycles (CSTQ03_BFC.py uses `tone_length=151` us, just under the cap). -> experiment:cw_tones (derive cap from soccfg gen f_fabric).
7. Noise: none.
8. Bugs/suspicious: runner (basic.py:15) loops 1e6 times creating a new ExperimentClass (makes dirs) and reprogramming; no stop_tproc; `declare_gen(res_ch)` without `mixer_freq` (OK only for mixer_freq=0); `freq2reg` without `ro_ch`; acquire result not stored in `self.data`; prints debug lines L66-71.
9. Destination: `qicklab/experiments/cw_tones.py` (`ConstantTwoToneProgram`, `ConstantTwoTone`), merged with SingleTone.
10. Style: debug prints.

---------------------------------------------------------------------------
## 7. mSingleTone.py (51 lines)

1. Purpose: brute-force constant resonator tone (100 acquires of 1e5 reps x 1000 rounds).
2. Symbols: `ConstantTone(AveragerProgram)` — WRITES `cfg['reps']=100000`, `cfg['rounds']=1000` (L13-14); reads `res_ch, nqz, mixer_freq, ro_chs[0], pulse_freq, pulse_gain, length`. `SingleTone(ExperimentClass)` — `acquire(self, progress=False)` loops 100x `prog.acquire`, returns None.
3. cfg READ: above. WRITTEN: `reps`, `rounds`.
4. Imports: qick *, ExperimentClass. Unused: `plt`, `np`, `gauss`, `datetime`, `tqdm`, `time`. Imported by Runners/runs/basic.py:3. `ConstantTone`: unused externally (name collides with runner flag `ConstantTone` in CSTQ03_BFC.py:116).
5. Dead: unused imports; `a, b` results discarded.
6. Lab notes: none.
7. Noise: L15, 17, 20, 27, 30-32 ("Transmission Experiment basic").
8. Bugs/suspicious: L25 `print('oh yeah')` inside body() (runs at program build); no readout declared but `prog.acquire` called -> relies on acquire with zero readouts (`AveragerProgram.acquire` with no ro_chs) — verify it doesn't hang; mutates caller cfg reps/rounds; `length` via tProc-clock `us2cycles` (16-bit cap).
9. Destination: `qicklab/experiments/cw_tones.py` (`ConstantToneProgram`, `SingleTone`).
10. Style: unused imports, debug print, misleading docstring.

---------------------------------------------------------------------------
## 8. mT1FF.py (235 lines)

1. Purpose: T1 with hardware wait sweep (RAverager), min-Q-range rotation, single-exponential fit.
2. Symbols:
   - `T1Program(RAveragerProgram)` — reads `qubit_ch, start (raw tProc cycles into r_wait), res_ch, nqz, qubit_nqz, ro_chs, readout_length, pulse_freq, f_ge, sigma, res_phase, pulse_gain, length, flattop_length, pi_gain, trig_buffer_start, trig_buffer_end, trig_delay, adc_trig_offset, relax_delay, step` (update: `r_wait += us2cycles(step)`).
   - `T1FF(ExperimentClass)`; module `Amplitude_IQ(I, Q, phase_num_points=200)`.
3. cfg READ (class): `cavity_winding_freq, pulse_freq, cavity_winding_offset, f_ge, rotation_angle, min_max, Qubit_number`. WRITTEN: none (fname renamed).
4. Imports: qick *, ExperimentClass, curve_fit. Unused: `gauss`, `datetime`, `tqdm`, `time`. Imported by mAutoCoherence.py:56, Runners/runs/coherence.py:2. `T1Program`, `Amplitude_IQ`: unused externally (name `T1Program` also defined in mT1_SS.py).
5. Dead: L32-34 commented set_pulse_registers; L88 commented program; L93 commented kwarg; L180-194 commented Q-fit; L197-198, L200 commented; `pulse_qubit_lenth += flattop_length` L45 unused.
6. Lab notes: L44 flattop (dup). T1 guess: T1 ≈ x where y crosses `a/2.6 + c` (≈1/e). -> analysis docs.
7. Noise: L15, 19, 20, 21, 25, 75 ("update frequency l" — wrong), 78-80, 87, 160, 222-229 (docstring; keep one line).
8. Bugs/suspicious:
   - L17 + qick `get_expt_pts`: register starts at `cfg["start"]` raw cycles, x-axis is `start + i*step` in us -> wrong axis if `start != 0` (runners always pass 0).
   - L127-131: if cfg has `rotation_angle=None`, `np.exp(1j*None)` TypeError (T2E handles None, T1 doesn't).
   - Fit unguarded (curve_fit failure raises); fit result not stored in data/attrs (only in title) -> not saved.
   - `adcs=self.ro_chs` but data indexed `[0][0]`.
   - Wait measured from pulse END (sync_all after pulse), standard for T1.
9. Destination: `qicklab/experiments/t1.py` (`T1Program`, `T1`; alias `T1FF`); fit -> `analysis/coherence.py`.
10. Style: shadowed builtin `complex`, `!= None`.

---------------------------------------------------------------------------
## 9. mT2EFF.py (261 lines)

1. Purpose: Hahn/CPMG echo T2E with `num_pi_pulses` Y-pi pulses, hardware wait sweep.
2. Symbols:
   - `T2EProgram(RAveragerProgram)` — reads `qubit_ch, start, pulse_freq, res_ch, ro_chs, nqz, qubit_nqz, readout_length, res_phase, pulse_gain, length, f_ge, sigma, trig_buffer_start, trig_buffer_end, flattop_length, trig_delay, pi2_gain, num_pi_pulses, pi_gain, adc_trig_offset, relax_delay, step` (update `r_wait += us2cycles(step/(num_pi_pulses+1))`).
   - `T2EMUX(ExperimentClass)` (misnamed; no MUX); module `Amplitude_IQ(..., 200)` (dup).
3. cfg READ (class): `f_ge, rotation_angle, min_max, num_pi_pulses`. WRITTEN: none (fname renamed `_n{num_pi_pulses}`).
4. Imports: qick *, ExperimentClass, curve_fit. Unused `gauss`, `datetime`, `tqdm`, `time`. Imported by mAutoCoherence.py:58, Runners/runs/coherence.py:4.
5. Dead: L19-20, 22, 44-46, 57-60, 91-93, 97-100, 124-125, 138, 222-223 commented code; `if True:` L182 & L205 make else L209-210 unreachable; L144 `print(x_pts, )`.
6. Lab notes: step quantization lives in runner (coherence.py:66,212): `step = 0.00232515*(n+1)*int_steps` so each of the n+1 segments is an integer number of tProc cycles (tProc cycle = 2.32515 ns, 430.08 MHz). -> experiment:t2_echo + architecture (clock). Phase convention: pi/2 at 0°, pi at 90° (CPMG). -> experiment:t2_echo.
7. Noise: L17, 24, 26-28, 114, 123 ("time between two π/2 pulses" — inaccurate), 128-130 ("Basic T2R" — wrong), 137, 198, 248-255.
8. Bugs/suspicious:
   - L146-148: `rotation_angle` is copied only if `cfg['min_max'] != None`; KeyError if `rotation_angle` present without `min_max`.
   - x_pts = `start + i*step` vs programmed total wait `(n+1)*(start + i*us2cycles(step/(n+1)))` -> consistent only for start=0 and quantized step.
   - Gaps are pulse-edge to pulse-edge (sync_all then sync r_wait), not centre-to-centre (cf. memory: MR timing audit 2026-07-28 found the same convention bug in ModifiedRamsey).
   - `flattop_length` local defined only in first branch L65 then reused in loop — fine only because the same condition guards both.
   - No winding applied (unlike T1FF); fit unguarded; fit not stored.
9. Destination: `qicklab/experiments/t2_echo.py` (`T2EchoProgram`, `T2Echo`; alias `T2EMUX`).
10. Style: `if True:` hacks, `!= None`, builtin shadow `complex`.

---------------------------------------------------------------------------
## 10. mT2R.py (477 lines)

1. Purpose: Ramsey T2* (two pi/2 pulses, hardware wait + optional phase advance), FFT-seeded 1- or 2-frequency fit plus envelope fit.
2. Symbols:
   - `rotate_iq(avgi, avgq)` — rotate mean onto +real.
   - `ramsey_1f`, `ramsey_2f`, `envelope_exp`, `envelope_gauss` — models.
   - `find_prominent_fft_peaks(t, y, prominence_frac=0.2)` — rFFT peaks sorted by height.
   - `fit_ramsey_auto(x, avgi, avgq)` — 1f fit, or 2f if >=2 FFT peaks and `rss2 < 0.85*rss1`.
   - `ramsey_func(self, ...)`, `guess_ramsey_params(x, y)`, `fit_ramsey(self, x, y)` — DEAD (module-level functions with `self`, `fit_ramsey` calls `self.guess_ramsey_params`; never referenced).
   - `fit_magnitude_envelope(x, avgi, avgq)` — exp vs gaussian envelope on |IQ|, lower RSS wins.
   - `T2RProgram(RAveragerProgram)` — reads `qubit_ch, start, res_ch, nqz, qubit_nqz, ro_chs, readout_length, pulse_freq, f_ge, sigma, pi2_gain, res_phase, pulse_gain, length, adc_trig_offset, relax_delay, step, phase_step` (update: `r_wait += us2cycles(step)`, `r_phase2 += phase_step`).
   - `T2R(ExperimentClass)`.
3. cfg READ (class): none beyond program. WRITTEN: none. Attrs `osc_fit` (+`perr`, `use_fft_freq`, `dominant_fft_freq`, `f_report`), `env_fit`.
4. Imports: qick *, ExperimentClass, curve_fit, find_peaks. Unused `gauss`, `datetime`, `tqdm`, `time`. Imported by mAutoCoherence.py:57, Runners/runs/coherence.py:3. All module functions: unused externally.
5. Dead: L157-203 (`ramsey_func`, `guess_ramsey_params`, `fit_ramsey`); L315 commented program; L320 commented kwarg; `env_fit` computed but never plotted/saved; unpacked `A, phi, C, A1, A2, phi1, phi2` unused.
6. Lab notes (tuning constants in code, document them): FFT prominence 0.25 of max; 2-tone accepted only if `rss2 < 0.85*rss1`; FFT frequency reported instead of fit when dominant peak > 2.5x second; freq bounds [0, 2] MHz; T2* bounds [1, 1e5] us; runner `phase_step = deg2reg(0)` (no virtual detuning; detuning via `freq_shift`). -> experiment:t2_ramsey.
7. Noise: L50, 59, 77, 97, 111, 142, 168, 171, 213, 220, 250, 259, 263, 266, 284, 289, 291, 299, 301, 306-308 ("Basic T2R"), 314, 340-342, 374-376, 422-424, 445-447.
8. Bugs/suspicious:
   - Ignores `flattop_length` (always arb Gaussian at `pi2_gain`) — if pi2_gain was calibrated for flat-top pulses the rotation is wrong (runners pass flattop_length).
   - No pin-0 trigger (T1/T2E fire it).
   - `rotate_iq` aligns the centroid, not the oscillation axis; oscillation may end up in Q -> poor fit (suspicious).
   - T2* lower bound 1.0 us: decays faster than 1 us cannot be fit.
   - 1f path (L87) unguarded: curve_fit failure raises out of display (AutoCoherence calls display).
   - Same `start` units mismatch as T1; edge-to-edge wait.
   - Fit results only on `self`, not saved to h5. FFT figure uses `figNum+2` (skips +1).
9. Destination: `qicklab/experiments/t2_ramsey.py` (`T2RamseyProgram`, `T2Ramsey`; alias `T2R`); fit functions -> `qicklab/analysis/ramsey.py`; delete dead trio.
10. Style: module functions taking `self`, banners.

---------------------------------------------------------------------------
## 11. mT1_SS.py (142 lines)

1. Purpose: single-shot T1 — Python loop over waits, each an AveragerProgram returning raw shots, thresholded with SingleShot angle/threshold.
2. Symbols:
   - `T1Program(AveragerProgram)` (name clash with mT1FF) — WRITES `cfg['rounds']=1`; reads `qubit_ch, qubit_nqz, res_ch, nqz, pulse_freq, ro_chs, readout_length, res_phase, pulse_gain, length, f_ge, sigma, qubit_gain, variable_wait, adc_trig_offset, relax_delay, reps`. Overrides `acquire(soc, threshold, angle, load_pulses, readouts_per_experiment, save_experiments, start_src, progress)` (ignores most args) -> `collect_shots()` -> `(i (1,reps), q (1,reps))` of ADC index 0, divided by `us2cycles(readout_length, ro_ch=0)`.
   - `T1_SS(ExperimentClass)`.
3. cfg READ (class): `start, step, expts`. WRITTEN: `Excited_PulseT1` (= `excited_pulse`, never read anywhere), `variable_wait` (each point).
4. Imports: qick *, ExperimentClass, tqdm, time, `Helpers.rotate_SS_data import *` (`rotate_data`, `count_percentage`). Unused `gauss`, `datetime`. Imported by Runners/runs/coherence.py:5.
5. Dead: L62, L64 commented timing; `self.q_rp` L16 unused; `excited_pulse` param effect-free; prints L92, L97.
6. Lab notes: none.
7. Noise: L16, 18, 20, 23, 25, 77-79, 122.
8. Bugs/suspicious:
   - Plays `cfg["qubit_gain"]` but runner sets `pi_gain` (coherence.py:271-274); correct only after `rebuild_singleshot_config` (which sets qubit_gain = pi gain). Before rebuild, qubit_gain = spec gain (context.py:198).
   - Ignores `flattop_length` (plain Gaussian) — wrong pi pulse for flat-top devices.
   - Readout length declared as `us2cycles(readout_length)` (tProc clock count used as ADC sample count) but shots normalized by `us2cycles(readout_length, ro_ch=0)`; SingleShotProgram (which calibrates the threshold) declares and normalizes with the ro clock. If tProc f_time != readout f_output the IQ scale differs from the calibration and the threshold is misapplied. PLAUSIBLE (clock-dependent).
   - No pin-0 trigger.
   - `threshold=None` -> `count_percentage` compares to None (TypeError) and `np.array(None)` save issue.
9. Destination: `qicklab/experiments/t1_single_shot.py` (`T1SingleShotProgram`, `T1SingleShot`; alias `T1_SS`); `collect_shots` -> `qicklab/core/shots.py`; `rotate_data`/`count_percentage` -> `qicklab/analysis/single_shot.py`.
10. Style: star import from Helpers, debug prints, name clash.

---------------------------------------------------------------------------
## 12. mChargeDispersion.py (183 lines)

1. Purpose: single-point fixed-wait Ramsey (pi/2 - wait 1/df - pi/2) for charge-parity readout.
2. Symbols: `rotate_iq` (DEAD; dup of mT2R), `ChargeDispersionProgram(AveragerProgram)` — reads `qubit_ch, df, res_ch, nqz, qubit_nqz, ro_chs, readout_length, pulse_freq, f_ge, sigma, pi2_gain, res_phase, pulse_gain, length, adc_trig_offset, relax_delay` (+`reps`, `rounds`); `ChargeDispersion(ExperimentClass)`.
3. cfg READ (class): `df` (display). WRITTEN: none.
4. Imports: qick *, ExperimentClass. Unused `gauss`, `datetime`, `tqdm`, `time`. Imported by Runners/runs/charge_parity.py:3.
5. Dead: `rotate_iq` L11-15.
6. Lab notes: L26-27 + L103-106: `df` in MHz -> wait `1/df` us; fixed-wait Ramsey-style. -> experiment:charge_dispersion.
7. Noise: L31, 32, 81, 85, 88, 92.
8. Bugs/suspicious:
   - Wait = `1/df`. Two parity branches split by `df` accumulate phase difference `2*pi*df*tau`; at tau=1/df that is 2*pi (branches indistinguishable). The ModifiedRamsey path uses `tau = 1/(2*df)` (charge_parity.py:106, CSTQ03_BFC.py:224 "tau = k/(2*df)"). Likely physics bug unless `df` here means something else. Also edge-to-edge gap, not centre-to-centre (MR timing audit 2026-07-28).
   - Ignores `flattop_length` (runner passes it); no winding; no trigger.
   - Runner uses reps=1, rounds=1 -> one shot per program build.
9. Destination: `qicklab/experiments/charge_dispersion.py` (`ChargeDispersionProgram`, `ChargeDispersion`).
10. Style: dead dup helper.

---------------------------------------------------------------------------
## 13. mChargeDispersionQuasiCW.py (151 lines)

1. Purpose: two-tone at fixed qubit frequency, hardware loop; returns shot-resolved raw IQ stream (reps x expts) for telegraph/parity analysis.
2. Symbols: `ChargeDispersionQuasiCWProg(RAveragerProgram)` — body/initialize identical to `QubitSpecSliceFFProg` (minus print and `self.sync_all`); reads `res_ch, nqz, mixer_freq, ro_chs[0], qubit_ch, qubit_nqz, readout_length, pulse_freq, start, step, Gauss, sigma, qubit_gain, qubit_length, res_phase, pulse_gain, length, adc_trig_offset, relax_delay`. `ChargeDispersionQuasiCW(ExperimentClass)` — builds `self.prog` in `__init__`.
3. cfg READ (class): `cavity_winding_freq, pulse_freq, cavity_winding_offset, reps, expts`. WRITTEN: none.
4. Imports: qick *, ExperimentClass, `import datetime` then `from datetime import datetime` (shadow; class used). Unused `plt`, `gauss`, `tqdm`, `time`. Imported by Runners/runs/charge_parity.py:2.
5. Dead: `self.qubit_length_us` L43/47; `debug` param.
6. Lab notes:
   - L71-75: quasi-CW = pulse-measure loop in hardware (cfg reps), rep-resolved data in one acquire. -> experiment:charge_dispersion_quasi_cw.
   - L89-90/L114: averaged return is incidental; `prog.di_buf/dq_buf` carry one entry per hardware shot.
   - L121-123: ordering uncertainty is RESOLVED for qick 0.2.334: `acc_buf` loop_dims `[expts, reps]` (expts outer) so `reshape(expts, reps).T` -> `(reps, expts)` is correct. -> experiment:charge_dispersion_quasi_cw.
7. Noise: L20, 21, 22, 26, 27, 29 ("Start fast flux" stale), 30, 32, 35, 55, 56, 67, 68, 102, 145.
8. Bugs/suspicious:
   - `raw_i/raw_q` are raw accumulator sums (not divided by readout length, no offset removal) while `avgi/avgq` are normalized -> different scales in the same dict.
   - If `rounds > 1`, `di_buf` holds only the LAST round (acc_buf re-filled each round) while averages span all rounds.
   - Return dict lacks `'config'`; no display/save_data override (base `save_data(data)` would try to save the nested dict).
   - Program built in `__init__`: cfg edits after construction are ignored.
   - Duplicate of QubitSpecSliceFFProg (should be the same program).
9. Destination: `qicklab/experiments/charge_dispersion.py` (`ChargeDispersionQuasiCW`) reusing `QubitSpecProgram`; raw-shot extraction -> `core/shots.py`.
10. Style: datetime shadowing, unused imports.

---------------------------------------------------------------------------
## 14. mSingleShotProgramFFMUX.py (921 lines)

1. Purpose: single-shot g/e (or thermal-only) IQ clouds, histogram fidelity/threshold/angle; source of the active-reset threshold calibration. ~60% of the file is dead legacy (FF loopback, AWG compensation).
2. Symbols:
   - `SingleShotProgramWITHUPDATE(RAveragerProgram)` L11-107 — DEAD (no references). Writes `start, step, reps, expts`; passes `debug=` to qick acquire (TypeError in 0.2.334).
   - `SingleShotProgram(AveragerProgram)` L116-264 — reads `shots, sigma, readout_length, ro_chs, adc_trig_offset, relax_delay, qubit_ch, qubit_nqz, res_ch, nqz, pulse_freq, length, res_phase, pulse_gain, trig_buffer_start, trig_buffer_end, flattop_length, Pulse, qubit_gain, f_ge, number_of_pulses, trig_delay`; soccfg `tprocs[0].f_time`, `gens[res_ch].f_fabric`, `readouts[ch].f_output`. WRITES `reps=shots`, `rounds=1`, `length` (setdefault `adc_trig_offset+readout_length`). Validates sigma>0, readout_length>0, ro_chs non-empty, delays>=0, `length >= adc_trig_offset+readout_length` (ValueError). Attrs: `adc_trig_offset_cycles`, `readout_window_cycles` (dict per ro ch), `readout_tone_cycles`, `readout_tone_extension_cycles`, `flattop_length`, `trig_length`. `acquire(...)` -> `collect_shots()` -> `(list per ro ch of (1,reps) I, same Q)` normalized by `us2cycles(readout_length, ro_ch)`.
   - `SingleShotProgramFFMUX(ExperimentClass)` L274-697 — acquire (normal / thermal), display, save_data.
   - `LoopbackProgramSingleShotWorking(RAveragerProgram)` L700-860 — DEAD (FF channels, `FF_list_readout`, `ff_*`, `qubit_pulse_style`, `flat_top_length`; passes `debug=`).
   - `QuadExponentialFit`, `Compensated_AWG`, `DoubleExponentialFit`, `Compensated_AWG_LongTimes`, `v_awg_Q1/Q2/Q4` (module-level arrays of 28800 ones), `Compensated_pulse_list`, `Compensated_Pulse` L864-921 — DEAD (only referenced from commented `acquireUPDATE`).
3. cfg READ (class): `Read_Indeces` (sic), `number_of_pulses` (`.get`, default 1), `thermal_tail_md2_threshold` (6.0), `thermal_tail_sigma_threshold` (2.5), `readout_length` (display title). WRITTEN: `Pulse` (False/True), plus program writes (`reps`, `rounds`, `length`). Attrs: `fid`, `threshold`, `angle` (lists after acquire; overwritten by scalars in display), `data_in_hist`.
4. Imports: qick *, `from qick import helpers` (unused), ExperimentClass, `Helpers.hist_analysis import *` (`hist_process`), tqdm (unused), time, `pickle` L863 (unused), lazy `sklearn.covariance.MinCovDet` (L321). Imported by: mAutoCoherence.py:55 (`SingleShotProgramFFMUX`), mOptimizeReadoutandPulse_FF.py:6 (`SingleShotProgram`), Runners/runs/calibration.py:2, charge_parity.py:15, coherence.py:6, singleshot.py:2. Referenced in comments: mZeroSpanParity.py:389, 701 (collect_shots normalization).
5. Dead: classes/functions above; commented blocks L51, 76, 79, 110-114, 191, 194, 196-200, 206, 218-220, 235, 256, 267-271, 515-537, 539-590 (`acquireUPDATE`), 718, 727-728, 781-783, 814-832, 900-906; display branch L631-633 (`thermal_gmm_means` never written) and `thermal_population_soft` lookup L607-612 (never written); `self.q_rp` L135 unused; `ran` param of display unused; `fid` in thermal mode always nan.
6. Lab notes:
   - L143-147: active-reset thresholds are calibrated by this program and consumed by ModifiedRamsey and ActiveResetVerify; all three must integrate the same physical ADC window and play the same resonator tone: convert each duration with its owning clock (tProc for trig offset, ro clock for window, gen clock for tone) and extend the tone by the minimum gen cycles needed after cross-clock rounding (`ceil(adc_end_tproc * f_fabric / f_time - 1e-12)`). -> architecture (readout timing) + experiment:single_shot.
   - L292-296: thermal mode (`number_of_pulses == 0`): acquire only no-pulse shots, store in same i_g/q_g/i_e/q_e structure. -> experiment:single_shot.
   - L323-375: thermal classifier: MinCovDet (support_fraction 0.75, random_state 0) on main blob; Mahalanobis d^2 > threshold marks tail (95% chi-square for 2D ≈ 5.99; use 6-9 depending on overlap; default 6.0); protrusion axis = mean of farthest max(10, 5%) points minus centre; sigma from MAD*1.4826 along axis; excited if proj > median + k*sigma (k = 2.0-3.0 by aggressiveness; default 2.5); population is conservative (counts only protruding points). -> experiment:single_shot.
   - L675: fidelity display clipped to <= 1.0. Fidelity from `hist_process` is histogram contrast, not (1+C)/2 (memory: MR parity analysis). -> experiment:single_shot.
   - L868/883: AWG compensation used sample step `0.00232515/16` us (tProc cycle / 16 fabric samples) and clipped `analytic_n` at -0.8 (-0.7 long-times) and `v_awg <= 1.5` — only if the FF compensation is ever revived. -> architecture (optional; dead code).
7. Noise (live code only): L135, 139, 141, 184, 211, 275-277, 293, 297, 323, 329, 351, 354, 460-462 (banners/restating comments). L24-25, 27, 30, 38-39, 48, 61, 87-88, 115 sit inside the dead WITHUPDATE class and go with it. Keep condensed versions of L334, 338, 367, 373-374 as lab notes (section 6).
8. Bugs/suspicious:
   - display() overwrites `self.fid/threshold/angle` (lists) with scalars; mAutoCoherence.py:481-485 reads `inst.fid[0]` BEFORE display — order-dependent.
   - display only shows `read_index` 0 (`for read_index in [0]`); works for other Read_Indeces only via the alias keys written at L441-449/L493-497.
   - `SingleShotProgram` omits `mixer_freq` in `declare_gen` (fine with 0.0) — but mOptimizeReadoutandPulse_FF.py:513/746 sets `cfg["mixer_freq"]` expecting an effect; verify which program consumes it there.
   - Thermal fallback on any exception (incl. missing sklearn) silently returns labels all 0, threshold nan.
   - Dead classes would raise TypeError (`debug=` not accepted by qick 0.2.334 `acquire`).
   - `Compensated_pulse_list = [Q1, Q2, Q2, Q4]` uses Q2 for qubit 3 (dead).
   - Module import allocates 3x28800 arrays (dead).
9. Destination: `qicklab/experiments/single_shot.py` (`SingleShotProgram`, `SingleShot`; alias `SingleShotProgramFFMUX`). Move readout-timing block L148-189 to `qicklab/core/readout.py` (shared with ModifiedRamsey/ActiveResetVerify/UndrivenSingleShot); thermal classifier L320-423 -> `qicklab/analysis/single_shot.py::classify_thermal_tail`; delete WITHUPDATE, Loopback, AWG compensation (git history keeps them).
10. Style: `Read_Indeces` misspelling (cfg key used by runners — keep or migrate with alias), `!= None`, broad excepts, `str(read_index)` key building (use nested dicts), unused imports, module-level side effects.

---------------------------------------------------------------------------
## 15. Cross-cutting observations

- Every file star-imports `qick`; three star-import `utils` (implicit `curve_fit`, `datetime` rebinding, and in mAmplitudeRabiFF silent shadowing of `fit_rabi_cosine`).
- Two classes named `AmplitudeRabiFFProg` and two named `T1Program` in different modules.
- Readout channels: `[0,1]` hard-coded in QubitSpecSliceFF, AmplitudeRabiFF, AmplitudeRabiFF_N, QuasiCW; `[0]` in ChiShift measure; `cfg["ro_chs"]`/`self.ro_chs` elsewhere. Unify on `cfg["ro_chs"]` (behavior change for saved array shapes — flag).
- `declare_readout` length uses tProc-clock `us2cycles` everywhere except SingleShotProgram (ro clock). Physical window length therefore = `us2cycles_tproc(readout_length)/f_output_ro`; consistent only if clocks match.
- Pin-0 trigger fired by Rabi/T1/T2E/SingleShot, not by Spec/Chi/T2R/T1_SS/ChargeDispersion/QuasiCW — document what pin 0 drives (switch? scope?) on the architecture page.
- Flat-top support: Rabi (both), Chi, T1FF, T2E, SingleShot honor `flattop_length`; T2R, T1_SS, ChargeDispersion, SpecSlice ignore it.
- Gain/frequency key naming inconsistent: `qubit_freq` (Chi, ConstantTwoTone) vs `f_ge` (others); `qubit_gain` vs `pi_gain` vs `pi2_gain`; T1_SS uses `qubit_gain` as pi gain. Device files should define `pi_gain`, `pi2_gain`, `f_ge` once and experiments should read only those.
- Cavity winding applied in 5 of 14 experiments only.
- Wait-sweep programs load `cfg["start"]` raw into the register but the x-axis treats it as us (all runners pass start=0).
- Fit results for T1/T2E/T2R/Chi are not written to `data['data']` (lost from h5); AutoCoherence must refit.
- Several experiments mutate the caller's cfg (`pulse_freq`, `qubit_gain`, `reps`, `rounds`, `Pulse`, `pulse_01`, `variable_wait`, `length`); `data['config']` aliases it so saved JSON reflects mutated values.
- All `save_data(data=None)` overrides crash on the default argument.
