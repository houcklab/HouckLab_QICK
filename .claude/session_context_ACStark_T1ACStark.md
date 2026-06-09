# Session Context: AC Stark Calibration & T1ACStark Experiments
**Date:** 2026-05-29 through 2026-06-01  
**Qubit:** TAT3D02-ADT, Q1 (~6.8 GHz readout, ~3377.4 MHz qubit)  
**Cooldown:** 2026-05-22_BFF_cooldown  
**Outer folder:** `Z:/t1Team/Data/2026-05-22_BFF_cooldown/TAT3D02-ADT/Q1_6p8//`

---

## 1. Key Files

| File | Purpose |
|------|---------|
| `WorkingProjects/QM_Team/qubit_measurements/Client_modules/Experiments/SingleShot_FF.py` | Main experiment runner. Contains all flags, params, and cfg construction. |
| `mACStarkCalibration.py` | Ramsey experiment with AC Stark pulse filling wait time. Single amplitude, sweep wait time. Extracts Ramsey frequency vs wait time. |
| `mACStarkCalibration_2.py` | 2D sweep: outer loop = AC Stark amplitude, inner loop = wait time. Extracts Ramsey frequency vs amplitude. |
| `mT1ACStark.py` | T1 experiment with AC Stark pulse filling the wait time. Outer loop = amplitude, inner loop = wait time. |
| `mT1FF.py` | Reference T1 experiment using RAveragerProgram. Pi pulse → wait (hardware register) → measure. |
| `mT2R.py` | Reference Ramsey (T2R) experiment. |
| `ACStarkCalibration_plot.py` | Standalone script to reconstruct ACStarkCalibration plots from saved .h5 files after interrupted run. |
| `T1ACStark_2D_timeplot.py` | Standalone script: reads overnight T1ACStark sweep, makes 2D color plots (x=time, y=AC Stark freq shift, color=I or Q). |
| `CoreLib/Experiment.py` | ExperimentClass base: constructs filenames as `outerFolder/path/path_YYYY_MM_DD/path_YYYY_MM_DD_HH_MM_SS_prefix.h5` |

---

## 2. Qubit Parameters (Q1)

```python
qubit_frequency_center = 3377.4   # MHz — actual qubit frequency
qubit_gain = 3700                 # pi pulse gain (NOT qubit_gain from base config which is 8000)
qubit_sigma = 0.15                # µs — Gaussian sigma
qubit_flattop = None              # No flat-top pulse used
f_ge (in T1ACStark_cfg) = qubit_frequency_center  # 3377.4 MHz (no freq_shift for T1)
pulse_freq = 6824.33              # MHz — readout resonator
pulse_gain = 8000
pi_gain = 3700
pi2_gain = 1850
```

---

## 3. Experiment Purposes and Pulse Sequences

### 3.1 ACStarkCalibration (`mACStarkCalibration.py`)
**Purpose:** Measure the Ramsey frequency (= AC Stark shift + freq_shift detuning) at a single fixed AC Stark amplitude, sweeping wait time.

**Pulse sequence (Ramsey):**
1. pi/2 pulse (Gaussian, f_ge + freq_shift)
2. AC Stark const pulse (f_ge + ACStark_detuning, gain=ACStark_amplitude) for wait_time µs
3. pi/2 pulse (same frequency)
4. Measure

**Fit:** Decaying cosine → extracts Ramsey frequency (kHz)

**Data saved:** `x_pts` (wait times), `avgi`, `avgq`

### 3.2 ACStarkCalibration_2 (`mACStarkCalibration_2.py`)
**Purpose:** 2D sweep — measures Ramsey frequency as a function of AC Stark amplitude. Calibrates the relationship: amplitude → AC Stark frequency shift.

**Pulse sequence:** Same Ramsey as above, but outer Python loop sweeps `ACStark_amplitude`.

**Data saved:** `x_pts` (wait times), `amp_pts` (amplitudes), `avgi_2D` (shape: n_amps × n_wait_times), `avgq_2D`

**Calibration result (2026-05-31):**
```
Ramsey Frequency (kHz) = 2.5786e-05 * amplitude^2 + 116.5995
```
- Offset 116.5995 kHz ≈ freq_shift (100 kHz) + small residual
- Pure AC Stark shift ≈ 2.5786e-05 * amplitude^2 kHz

**Saved to:** `ACStarkCalibration_2/ACStarkCalibration_2_2026_05_31/`

**Key params used:**
```python
ACStark_2_params = {
    "T2_step": 1, "T2_expts": 25,      # wait times: 1–25 µs
    "ACStark_amplitude_start": 0,
    "ACStark_amplitude_step": 300,
    "ACStark_amplitude_expts": 11,      # amplitudes: 0–3000
    "freq_shift": 0.1,                  # MHz — intentional Ramsey detuning
    "ACStark_detuning": 50,             # MHz — off-resonant drive detuning
    "relax_delay": 500,
}
```

### 3.3 ACStarkCalibration loop (`RunACStarkCalibration_loop` in SingleShot_FF.py)
**Purpose:** Python-level loop over amplitudes, calling ACStarkCalibration (single Ramsey) for each amplitude. Saves summary JSON + PNG with quadratic fit.

**Saved to:** same directory as individual ACStarkCalibration runs (`os.path.dirname(iACStarkCalibration.iname)`)

**Fit model:** Full quadratic `ax^2 + bx + c` using `np.polyfit`

### 3.4 T1ACStark (`mT1ACStark.py`)
**Purpose:** T1 measurement where the AC Stark pulse fills the wait time between pi pulse and measurement. Outer loop sweeps AC Stark amplitude (= different qubit frequency shifts). Goal: measure how T1 varies with AC Stark-shifted qubit frequency and track fluctuations over time.

**Pulse sequence (T1):**
1. Set pi pulse registers (Gaussian, f_ge, gain=pi_gain) — done at start of EVERY body() call
2. pi pulse (Gaussian)
3. sync_all
4. AC Stark const pulse (f_ge + ACStark_detuning, gain=ACStark_amplitude) for wait_time µs
5. sync_all(0.05 µs)
6. Measure (readout pulse + ADC)

**Data saved:** `x_pts` (wait times), `amp_pts` (amplitudes), `avgi_2D`, `avgq_2D`

**Overnight sweep params (2026-05-31 → 2026-06-01):**
```python
T1ACStark_params = {
    "T1_start": 80, "T1_step": 1, "T1_expts": 1,   # single wait time: 80 µs
    "T1_reps": 50, "T1_rounds": 20,
    "relax_delay": 500,
    "repetitions": 10000000,
    "ACStark_detuning": 50,
    "ACStark_amplitude_start": 0,
    "ACStark_amplitude_step": 50,
    "ACStark_amplitude_expts": 61,                   # amplitudes 0–3000
    "freq_shift": 0.1,  # NOT used in T1ACStark_cfg — f_ge = qubit_frequency_center only
}
```

**Data location:**
- `Z:\t1Team\Data\2026-05-22_BFF_cooldown\TAT3D02-ADT\Q1_6p8\T1ACStark\T1ACStark_2026_05_31\` — files from `T1ACStark_2026_05_31_21_37_24_data.h5` onward
- `Z:\t1Team\Data\2026-05-22_BFF_cooldown\TAT3D02-ADT\Q1_6p8\T1ACStark\T1ACStark_2026_06_01\` — all files

---

## 4. QICK Technical Notes

- **AveragerProgram vs RAveragerProgram:** AveragerProgram requires Python loops for sweeping (recompiles program each iteration). RAveragerProgram uses hardware registers (`r_wait`, `update()`) — compiled once, runs fast.
- **`us2cycles(t)`** without `gen_ch`: uses tproc clock (~430.08 MHz). Max 16-bit pulse = 65535 / 430.08e6 ≈ **152 µs**.
- **`us2cycles(t, gen_ch=ch)`** with gen_ch: uses that generator's fabric clock. For this system, qubit channel f_fabric = **430.08 MHz** (same as tproc). No advantage for longer pulses.
- **16-bit pulse length limit:** `const` style pulses limited to 65535 cycles ≈ 152 µs. Cannot play a single const pulse longer than this.
- **Workaround for >152 µs:** Split into multiple back-to-back `setup_and_pulse` calls (each ≤150 µs). Currently NOT implemented in T1ACStark (max wait = 150 µs to stay safe).
- **`setup_and_pulse`:** Sets AND immediately plays a pulse. Overwrites channel's pulse registers.
- **Pulse register persistence:** In AveragerProgram, pulse registers persist between `body()` repetitions. If `setup_and_pulse` overwrites registers in rep N, rep N+1's `self.pulse()` plays the wrong pulse.

---

## 5. Bugs Encountered and Fixes

### Bug 1: `amp` not used in loop config
**Problem:** `"ACStark_amplitude": ACStark_params["ACStark_amplitude"]` instead of `amp` in the loop.  
**Fix:** Use `"ACStark_amplitude": int(amp)`.

### Bug 2: Unit mismatch in quadratic fit plot
**Problem:** Fitting on MHz data but plotting axis in kHz, so title coefficients were wrong scale.  
**Fix:** Convert `Rfreq_list_kHz = Rfreq_list * 1e3` before `np.polyfit`.

### Bug 3: `import matplotlib as plt`
**Problem:** Should be `import matplotlib.pyplot as plt`. Caused `TypeError: 'module' object is not callable` at `plt.figure()`.  
**Fix:** Correct import.

### Bug 4: List aliasing in avgi_list_2D
**Problem:** `avgi_list = []` was outside the amplitude loop, so all rows of `avgi_list_2D` pointed to the same growing list.  
**Fix:** Move `avgi_list = []` inside the amplitude loop.

### Bug 5: QICK integer gain requirement
**Problem:** `np.arange` returns floats; QICK bit-shifts fail on floats → `TypeError: ufunc 'left_shift' not supported`.  
**Fix:** `amplitude_pts = amplitude_pts.astype(int)` and `int(amp)`.

### Bug 6: Pulse length out of range (68817 cycles)
**Problem:** `T1_step=20, T1_expts=11` → max wait 200 µs → 68817 cycles > 65535 limit.  
**Fix:** Reduce max wait to ≤150 µs (e.g., `T1_step=15, T1_expts=10`).

### Bug 7: `freq_shift` in T1ACStark f_ge
**Problem:** `'f_ge': qubit_frequency_center + T1ACStark_params["freq_shift"]` (inherited from Ramsey params). Makes pi pulse 0.1 MHz off-resonant → qubit not fully inverted → non-monotonic / oscillating data.  
**Fix:** `'f_ge': qubit_frequency_center` (no freq_shift for T1).  
**Location:** `SingleShot_FF.py` line 535. Currently fixed (freq_shift commented out).

### Bug 8: Pulse register overwrite between body() repetitions
**Problem:** `initialize()` sets qubit channel to Gaussian pi pulse. `body()` calls `setup_and_pulse` (AC Stark const pulse), overwriting the registers. In rep 2+, `self.pulse(ch=qubit_ch)` plays the const AC Stark pulse (gain=0) instead of the pi pulse → only 1 of 2000 reps correctly excites qubit → flat data.  
**Fix:** Added `set_pulse_registers` for pi pulse at the **start of `body()`** in `mT1ACStark.py`:
```python
def body(self):
    self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=self.f_ge,
                             phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["pi_gain"],
                             waveform="qubit")
    self.pulse(ch=cfg["qubit_ch"])  # pi pulse
    ...
```

### Bug 9: Missing repetitions loop for T1ACStark
**Problem:** `RunT1ACStark` block had no loop, so ran only once despite `repetitions=10M`.  
**Fix:** `iT1ACStark` created once outside loop; `acquire/display/save` inside `for i in range(T1ACStark_params['repetitions'])`. Also fixed: loop condition checked `T1T2_params['repetitions']` instead of `T1ACStark_params['repetitions']`.

### Bug 10: Wrong data keys in mACStarkCalibration_2 display
**Status: UNFIXED.** `acquire()` saves `avgi_2D`/`avgq_2D` (correct), display reads same keys (correct now). This was fixed during development.

### Bug 11: path collision between ACStarkCalibration and ACStarkCalibration_2
**Problem:** Both used `path="ACStarkCalibration"` → saved to same folder.  
**Fix:** `ACStarkCalibration_2` uses `path="ACStarkCalibration_2"`.

### Bug 12: display() in T1ACStark plotting wrong axis
**Problem:** `avgi_2D[:, 0]` vs `amp_pts` was plotting population at first wait time (correct intent) but the original code had wrong indexing. User rewrote display to plot single wait time population vs amplitude (the intended view).

---

## 6. Current State of Each File

### `mT1ACStark.py` — body() (WORKING)
```python
def body(self):
    cfg = self.cfg
    # re-configure pi pulse each rep (setup_and_pulse overwrites these registers)
    self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=self.f_ge,
                             phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["pi_gain"],
                             waveform="qubit")
    self.pulse(ch=cfg["qubit_ch"])  # pi pulse
    self.sync_all()
    self.setup_and_pulse(ch=cfg["qubit_ch"], style="const", freq=self.f_ACStark,
                         phase=0, gain=cfg["ACStark_amplitude"],
                         length=self.us2cycles(cfg["current_wait"]))
    self.sync_all(self.us2cycles(0.05))
    self.measure(pulse_ch=cfg["res_ch"], adcs=self.ro_chs,
                 adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                 wait=True, syncdelay=self.us2cycles(cfg["relax_delay"]))
```

### `SingleShot_FF.py` — T1ACStark block (WORKING)
```python
if RunT1ACStark:
    T1ACStark_cfg = {
        "start": T1ACStark_params["T1_start"],
        "step": T1ACStark_params["T1_step"],
        ...
        'f_ge': qubit_frequency_center,  # NO freq_shift — critical for T1
        ...
    }
    config = config | T1ACStark_cfg
    iT1ACStark = T1ACStark(path="T1ACStark", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    for i in range(T1ACStark_params['repetitions']):
        if T1ACStark_params['repetitions'] > 1:
            plot_disp = False
        else:
            plot_disp = True
        dT1ACStark = T1ACStark.acquire(iT1ACStark)
        T1ACStark.display(iT1ACStark, dT1ACStark, plotDisp=plot_disp, figNum=2)
        T1ACStark.save_data(iT1ACStark, dT1ACStark)
        T1ACStark.save_config(iT1ACStark)
```

### `T1ACStark_2D_timeplot.py` — (WORKING)
Reads all overnight T1ACStark .h5 files, converts amp_pts to frequency via calibration fit, plots 2D color map (x=time in hours, y=AC Stark shift in kHz, color=I or Q). Saves with timestamped + counter filename.

---

## 7. Data File Structure (HDF5)

### ACStarkCalibration (.h5 keys)
- `x_pts`: wait times (µs)
- `avgi`: I quadrature (shape: n_wait_times)
- `avgq`: Q quadrature

### ACStarkCalibration_2 (.h5 keys)
- `x_pts`: wait times (µs)
- `amp_pts`: AC Stark amplitudes (int)
- `avgi_2D`: shape (n_amps, n_wait_times)
- `avgq_2D`: shape (n_amps, n_wait_times)

### T1ACStark (.h5 keys)
- `x_pts`: wait times (µs) — for overnight sweep: [80.0] (single point)
- `amp_pts`: AC Stark amplitudes — [0, 50, 100, ..., 3000] (61 points)
- `avgi_2D`: shape (61, 1) for overnight sweep
- `avgq_2D`: shape (61, 1)

---

## 8. AC Stark Physics Context

- **AC Stark effect:** Off-resonant microwave drive at frequency f_ge + Δ (detuning Δ) shifts the qubit transition frequency by an amount proportional to drive power (amplitude²).
- **ACStark_detuning = 50 MHz** — drive is 50 MHz above qubit frequency.
- **ACStark_amplitude** — QICK integer gain (0–32767). Quadratic relationship to frequency shift.
- **Goal of T1ACStark sweep:** Measure T1 at many different AC-Stark-shifted qubit frequencies simultaneously (outer amplitude loop), repeated many times over hours, to study T1 fluctuations and frequency dependence.
- **Why single wait time (80 µs)?** Instead of a full T1 decay curve each rep, measure just one point at a tau comparable to T1. This maximizes time resolution for tracking fluctuations.
- **mACStarkCalibration uses Ramsey (T2):** freq_shift=0.1 MHz intentional detuning causes Bloch vector to precess → oscillating signal → fit extracts Ramsey frequency = freq_shift + AC Stark shift.
- **mT1ACStark uses T1:** pi pulse must be exactly resonant (f_ge, no freq_shift). AC Stark pulse fills wait time but doesn't drive the qubit transition (50 MHz detuning is far off-resonant).
