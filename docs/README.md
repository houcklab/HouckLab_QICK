# qicklab documentation

qicklab is the Houck Lab QM-team code for measuring superconducting qubits with a Xilinx RFSoC running QICK (tProc v1, client `qick==0.2.334`).
A **device** file holds one chip's measured numbers, a **session** picks the qubit, the bias and the shared settings, and a **plan** is an ordered list of **steps** (`R.t1()`, `R.single_shot()`, ...) that `run()` executes.
Each step wraps an experiment class (`T1FF`, `SingleShotProgramFFMUX`, `ModifiedRamsey`, ...) that compiles a tProc program, acquires, fits and plots, and writes `.h5` + `.png` + `.json` under the device's data folder.
It covers resonator and qubit spectroscopy, Rabi, T1 / T2* / T2E, single-shot readout, active reset and charge-parity switching (Modified Ramsey, undriven single shot, zero-span).
Where code and a page disagree, the code wins and the page needs a fix. The parameter tables (the [parameter reference](parameters.md) and the recipe table at the top of each step page) are generated from the code, so they do not drift.

## Reading path

Work through 1-9 once. After that, use 10-14 as reference. 15 is for people who change the code.

1. **Quickstart** (page not written yet; until then use [the session file](running_a_session.md#the-session-file) and [Running](running_a_session.md#running)): write a three-step plan, run it with `dry_run=True` (every program compiles against fake hardware, nothing plays), then run it on the board.
2. **[Config regimes](concepts/config_regimes.md)**: why every step sees one of two config dicts, what is lost when the plan switches between them, and why `qubit_gain` means two different things.
3. **[Readout window](concepts/readout_window.md)**: `length = adc_trig_offset + readout_length`, the three separate windows, SNR vs T1, clock rounding.
4. **[Averaging](concepts/averaging.md)**: `reps`, `rounds`, `shots`, `soft_avgs`, `repetitions`, `repeat`, `num_cycles`, `cycles`; why to prefer `reps`.
5. **[Timing and units](concepts/timing_and_units.md)**: clocks, `us2cycles` / `freq2reg` / `deg2reg`, MHz vs Hz, DAC gain units, Nyquist zones, edge-to-edge waits, registers.
6. **[IQ conventions](concepts/iq_conventions.md)**: cable winding, principal-axis projection, rotations, separators, what "fidelity" means in the plots.
7. **[Running a session](running_a_session.md)**: the session script, plans, overrides, the REPL, where the data goes.
8. **[Bring-up workflow](bringup_workflow.md)**: characterising a new chip, from cavity to the T1/T2/T2E benchmark.
9. **[Adding a device](adding_a_device.md)**: writing `devices/<NAME>.py`, archiving a cooldown, calibration write-back.
10. **[Experiments](experiments/README.md)**: one page per step (recipe keywords, pulse sequence, parameters, outputs, known issues).
11. **[Parameters](parameters.md)**: every knob with units, default and meaning: the ~20 values most sessions change, then the device file, the session and its groups, every step recipe, and (for developers) the experiment cfg keys. Generated from the parameter registry `qicklab/core/params.py` by `scripts/gen_docs.py`.
12. **[Troubleshooting](troubleshooting.md)**: error message or symptom -> cause -> fix.
13. **[Glossary](glossary.md)**: FF, MUX, SS, regime, recipe, step, plan, carry-over, strobe, parity branch, ...
14. **[Hardware](hardware.md)**: RFSoC endpoint and channel map, trigger pin, yokos, TWPA instruments, attenuator, data paths.
15. **[Architecture](architecture.md)** (developers): package layout and layering, the parameter registry and generated docs, regression harness, QICK facts the code relies on.

Device pages: [devices/](devices/) (one per chip and cooldown, e.g. CSTQ03).

## Conventions used in these pages

- Experiments are named by their **step** (snake_case: `t1`, `t2_echo`, `modified_ramsey`, `undriven_single_shot`) and by their **class** (`T1FF`, `T2EMUX`, `ModifiedRamsey`, `UndrivenSingleShot`). Class names keep their historical suffixes; `FF` and `MUX` in a class name do not mean the experiment uses fast flux or multiplexing (see [glossary](glossary.md#ff)).
- Code locations are given as modules, e.g. "see `qicklab.core.readout`".
- Measured facts carry the device, qubit and date they were measured on, e.g. "CSTQ03 Q2, 2026-08-04". A number without that attribution is a setting, not a measurement.
- cfg key names are the legacy ones (`Read_Indeces`, `qubit_gain`, `pulse_freq`, ...). The refactor keeps them unchanged on purpose.
- Units: MHz for frequencies, us for times, DAC units (0..32767) for gains, unless a page says otherwise. Exceptions are listed in [timing and units](concepts/timing_and_units.md#units).
