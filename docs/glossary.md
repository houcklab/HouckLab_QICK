# Glossary

Terms as they are used in this code base. Links go to the page that explains them.

## Code and workflow

### Device
One chip in one cooldown: `devices/<NAME>.py` holds a `Device` (qubits, readout windows, data
root, setup). Earlier cooldowns go to `devices/archive/<NAME>_<cooldown>.py`. See
[adding a device](adding_a_device.md).

### Setup
The part of a device that describes the wiring and instruments: RFSoC host, yoko address,
`board_overrides` merged over `BASE_CONFIG`, fast-flux map, TWPA instruments. See
[hardware](hardware.md).

### BASE_CONFIG
Board-level defaults (channels, Nyquist zones, trigger timing, cable winding, default `reps`,
`relax_delay`, `adc_trig_offset`) in `qicklab.hardware.board`. Both config regimes start from it.

### Session
`Session(device, qubit_readout, qubit_pulse, bias_v, ...)`: which qubit is read, which is driven,
the charge bias, and the shared parameter groups for this sitting. See
[running a session](running_a_session.md).

### qubit_readout, qubit_pulse
Qubit whose resonator is read (readout frequency, gain, window, data folder) and qubit that is
driven (frequency, pi gain, sigma). Usually the same. Legacy `Qubit_Readout`, `Qubit_Pulse`.

### Group (session group)
A shared parameter set given once on the `Session` and read by several steps:
`transmission`, `spec`, `tones`, `charge`, `coherence`, `echo`, `single_shot`. The config builders
also read them.

### Recipe
A keyword-only function in `qicklab.runs.recipes` (`R.t1(...)`) with documented parameters and
defaults. It returns a `Step`. Unknown keywords raise `TypeError`.

### Step
One entry of a plan: a named run function, its regime (A or B), the groups it needs and its
parameters. Steps are named in snake_case (`t1`, `t2_echo`, `modified_ramsey`). Registry:
`qicklab.runs.STEPS`.

### Plan
An ordered list of steps, `PLAN = [R.transmission_fit(), R.t1(), R.single_shot()]`. Repeats are
allowed; `run(session, PLAN)` executes it in the written order.

### Precedence
Recipe default < session group < keyword on the step.

### Regime (A, B)
Which of the two config builders produced the config a step sees: A = measurement config,
B = single-shot config. See [config regimes](concepts/config_regimes.md).

### Carry-over
A measured value a step writes back into the persistent config for later steps: `pulse_freq`
(from `transmission_fit` / `transmission_sweep`) and `res_phase` (from the active-reset
calibration). Discarded at every switch to regime B.

### Calibration write-back
Steps that measure a device value append it to `<data_root>/Q{q}/calibrations.jsonl` and print a
paste-ready `Qubit(...)` line for the device file.

### Dry run
`run(session, PLAN, dry_run=True)`: compiles every program against fake hardware
(`qicklab.core.fakes`) and prints the plan and effective parameters; nothing plays.

### Golden (regression golden)
Snapshot of every cfg, compiled tProc program and yoko command the legacy code produced for the
CSTQ03 parameters. Refactor commits must reproduce it. See [architecture](architecture.md).

### ExperimentClass
Base class of every experiment wrapper (`qicklab.core.experiment`): file naming,
`acquire` / `display` / `save_data` / `save_config`; run functions call the last three
through `finish` ([architecture](architecture.md#display-never-loses-the-record)).

### outerFolder, path
`outerFolder` = `Device.folder(qubit_readout)`; `path` = sub-folder and file stem of an
experiment (`"T1"`). See [hardware: data paths](hardware.md#data-paths).

### Read_Indeces
Misspelled cfg key (kept on purpose) holding the readout qubit index for the single-shot family.

## Class-name suffixes

### FF
"Fast flux". Historical suffix on class names (`CavitySpecFF`, `T1FF`, `AmplitudeRabiFF`,
`SingleShotProgramFFMUX`). No current qicklab experiment plays a fast-flux pulse; the `FF_Qubits`
map is saved as metadata only ([hardware](hardware.md#fast-flux-channels)).

### MUX
"Multiplexed readout". Historical suffix (`T2EMUX`, `SingleShotProgramFFMUX`); these classes read
one resonator.

### SS
Single shot: one IQ point per shot instead of an average. `SS_params` = legacy single-shot
settings; `T1_SS` = single-shot T1.

### _N
`AmplitudeRabiFF_N`: software ("no update") gain sweep, one program per gain, needed for flat-top
pulses.

## Timing, units, hardware

### tProc
The QICK timed processor that runs the compiled program (v1 on the lab board). Clock 430.08 MHz,
one cycle 2.32515 ns. See [timing and units](concepts/timing_and_units.md).

### Generator (gen), readout (ro)
DAC output channel (`res_ch` = 0, `qubit_ch` = 1) and ADC readout channel (`ro_chs` = [0]).

### DAC units
Gain scale 0..32767 (full scale) for `pulse_gain`, `qubit_gain`, `pi_gain`, `pi2_gain`.

### nqz, qubit_nqz
Nyquist zone of the readout and qubit DACs (2 and 1 on the lab board).

### Readout window
`adc_trig_offset` (delay to ADC trigger) + `readout_length` (integration); the tone `length` is
their sum. See [readout window](concepts/readout_window.md).

### Edge-to-edge wait
QICK waits run from the end of one pulse to the start of the next; Ramsey phase accrues centre to
centre. See [timing](concepts/timing_and_units.md#waits-are-between-pulse-edges).

### Rep period
Time from one shot to the next, from the compiled schedule (`scheduled_rep_period_us`); the time
base of shot records.

### Flat-top
Pulse with Gaussian rise and fall (4 sigma total) and a flat segment of `flattop_length` us.

### Pin 0, PMOD trigger
tProc trigger output raised around qubit pulses by some programs ([hardware](hardware.md#trigger-pin-0-pmod)).

### Yoko
Yokogawa GS200 source: `GPIB1::9` for the charge bias (voltage), `GPIB1::12` for the TWPA bias
(current).

### yoko_fixed
Session flag: hold the bias during a "charge sweep", which then repeats two-tone spectroscopy over
time.

### cavity_min
Device flag: the resonator appears as a transmission dip (True) or a peak (False);
`transmission_sweep` carries the minimum or maximum accordingly.

### TWPA
Travelling-wave parametric amplifier on the readout line, biased by a current yoko and pumped by
the Windfreak SynthHD.

### Cooldown
One fridge cycle. Device numbers are per cooldown; data roots carry the date, e.g.
`2026-10-01_BFC_cooldown`.

### BFC
Project label used in branch names and data folders (`2026-10-01_BFC_cooldown`). The code does not
spell it out.

## Averaging words
`reps`, `rounds`, `expts`, `shots`, `soft_avgs`, `repetitions`, `Repeat`, `num_cycles`, `cycles`:
see the table in [averaging](concepts/averaging.md#vocabulary).

## Readout and IQ

### Principal-axis projection
Rotating IQ data onto the direction of largest variation and keeping the real part; used instead
of `|I + iQ|` for spectroscopy. See [IQ conventions](concepts/iq_conventions.md).

### Cable winding
`cavity_winding_freq` / `cavity_winding_offset`: frequency-dependent cable phase correction.
Currently 0 (off).

### Contrast, fidelity
The single-shot "Fidelity" printed by `hist_process` is the contrast C = P(g|g) + P(e|e) - 1.
Assignment fidelity with equal priors is (1 + C)/2.

### Apriori separator
g and e cloud centres (means) from a single-shot calibration with a pi pulse, with
`normal = e - g` and `midpoint`; shots are classified by the perpendicular bisector. Measured
inside `modified_ramsey`, `active_reset_verify` and `zero_span_parity`.

### Bisector classification
`score = (iq - midpoint) . normal`; positive means e.

### Threshold, angle
Output of `single_shot`: rotation angle that puts g->e on I, and the I threshold between the
clouds (in normalised units).

### Thermal tail
Excited-state shots in an undriven cloud, found by the robust (MinCovDet) classifier when
`number_of_pulses` = 0.

### Active reset
Measurement-based reset: read, and fire a corrective pi pulse in hardware only if the shot is
above (or below) a threshold on raw I. Calibrated by rotating `res_phase`.

### QND
Quantum non-demolition: repeated readouts give the same answer. A working QND reset shows flat,
high P(g) across repeated verification reads.

### Undriven single shot
Single-shot readout with the qubit never driven (`undriven_single_shot`, `UndrivenSingleShot`):
cloud statistics plus a time series of shots for switching analysis.

## Charge parity

### Parity, parity switching
Charge parity of the island (even/odd quasiparticle number). Each parity state shifts the qubit
frequency; switching shows up as a random telegraph signal.

### Parity branch, doublet, df
The qubit line splits into two branches (a doublet), one per parity, separated by `df` (MHz).
In `modified_ramsey`, `f_ge` means the **upper** branch; the lower is `f_ge - df`.

### Charge dispersion
Dependence of the branch splitting on the charge bias, modelled as
`S(V) = cd_max_mhz * |cos(2 pi (V - V0) / T)|` with period `T = cd_period_mv` (mV).

### Sweet spot
Charge bias where the dispersion (branch splitting) is smallest. Found by `auto_coherence` and
`modified_ramsey_control` with a two-tone search and yoko walk; accepted when the separation is
below a set limit or only one peak is seen.

### Modified Ramsey (MR)
Fixed-tau Ramsey that maps parity onto qubit state: `tau = k/(2 df)` with odd k, so the two
branches end in opposite states. `ModifiedRamsey`; step `modified_ramsey`.

### Modified Ramsey control (MRC)
Sweet-spot null control for MR (`modified_ramsey_control`).

### Symmetric Ramsey
MR variant that drives at `f_ge - df/2`, midway between the branches, halving each branch's
detuning; closing phase 90 deg instead of 180.

### Echo null, flip_final_pi2, drive_off, drive_detuned, tau_offset
MR validation controls: echo must suppress the telegraph, a flipped final pi/2 must invert the
mapping, the others are informational.

### Telegraph, dwell
A two-level random signal; a dwell is one stay in a state. Rates are `1/mean dwell`.

### HMM, ACF, PSD
Three independent rate estimators used for parity records: a two-state hidden Markov model on the
continuous IQ, the autocorrelation decay (`tau_corr = 1/(2 gamma)`), and the Lorentzian corner of
the power spectrum (`f_c = gamma/pi`).

### Mapping probabilities
`P(e | parity state 0)`, `P(e | parity state 1)` used by the HMM; defaults (0.1, 0.9) are assumed
until measured.

### Quasi-CW
Two-tone at a fixed qubit frequency with the pulse-measure loop in hardware, returning every shot
(`charge_dispersion_quasicw`).

### Zero span (ZSP)
Two-tone parity measurement with continuous readout and parity drive at fixed frequencies
(`zero_span_parity`, `ZeroSpanParity`).

### Strobe, decimated
Zero-span acquisition modes. Strobe (path A, v1): one integrated IQ point per `sample_period_us`,
streamed in chunks. Decimated (path B, v2): the raw decimated ADC trace over `capture_length_us`,
sub-us resolution, short records.

### Apriori mode (zero span)
`classifier_method="apriori"`: classify zero-span samples with a cached or freshly measured
single-shot separator, instead of KMeans clustering of the record itself (`"kmeans"`).
