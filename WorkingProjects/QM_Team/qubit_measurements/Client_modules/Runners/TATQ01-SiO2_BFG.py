"""TATQ01-SiO2 (BFG) — client-facing measurement runner.

Edit the device parameters and per-experiment params below, toggle the RunX
flags, and run this file top-to-bottom. The measurement procedures themselves
live in the `runs/` package (imported via `*` below); this file only selects
what to run. See docs/superpowers/specs/2026-07-02-cstq03-runner-refactor-design.md.

Fridge/cooldown: BFG, 2026-06-27 recooldown.
Device:          "Device 2 KOH + SiOx JJ (2 CLs)".
Data root:       Z:/t1Team/Data/2026-06-27_BFG_recooldown/.../RFSOC/Q<n>/
                 (Q1..Q4 already exist on the drive from earlier sessions;
                  each experiment adds its own <Experiment>/<Experiment>_<date>/
                  subfolder under them, same as every other runner.)
"""

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Runners.runs import *


# ══════════════════════════════════════════════════════════════════════════════
# 1. DEVICE PARAMETERS  (edit every session)
# ══════════════════════════════════════════════════════════════════════════════

# ── Output folder root — edit this one line ────────────────────────────────
_QubitFolderRoot = "Z:/t1Team/Data/2026-06-27_BFG_recooldown/Device 2 KOH + SiOx JJ (2 CLs)/RFSOC"
QubitFolders = {str(q): f"{_QubitFolderRoot}/Q{q}//" for q in range(1, 7)}

############## TATQ01-SiO2 / BFG Device 2 ##############################
# NOTE: these values are carried over verbatim from CSTQ03_BFC.py and have NOT
# been re-measured on this device/cooldown. Re-run transmission -> two-tone ->
# Rabi -> single-shot per qubit and update the entries as you go.
# NOTE: only Q1..Q4 are wired for fast flux on this setup (see FF_Qubits in
# Calib/initialize4Q.py); entries '5'/'6' are kept only to preserve the
# carried-over parameter set.
Qubit_Parameters = {
    # now working on
    '1': {'Readout': {'Frequency': 6627.759, 'Gain': 1500}, # 500 okay, 700 too much 520 maybe too much 530 too much
          'Qubit': {'Frequency': 1319.966169154229, 'Gain': 3841,  "pi2_Gain": 3841 // 2,"sigma": 0.7, "flattop_length": None},
          'outerfoldername': QubitFolders['1']},

    # TODO
    '2': {'Readout': {'Frequency': 7192.01, 'Gain': 4000}, # coarsely tuned to 4000, seeing behavior at 4500
          'Qubit': {'Frequency': 3052.389307, 'Gain': 2055, "pi2_Gain": 2055 // 2, "sigma": 1 , "flattop_length": None}, # qubit, T1 found
          'outerfoldername': QubitFolders['2']},

    # currently working on
    # Imported from QubitSpecFF_2026_07_01_01_20_10_data.json (Q3, BFG 2026-06-27):
    #   readout  pulse_freq = 6818.08 MHz, pulse_gain = 2000
    #   qubit    qubit_freq = 1683.3482587064677 MHz, qubit_gain = 5000
    # pi2_Gain / sigma / flattop_length are not set by that spec run (const pulse)
    # and are still the carried-over values -- re-tune with Rabi.
    # Readout set from SingleShot_OptReadout_2026_07_28_01_57_54 (Q3, BFG 2026-06-27):
    #   best single-shot fidelity 78.1% at gain 2900, pulse_freq 6818.105 MHz
    #   (sweep was gain 1000..3000 x freq 6818.100..6818.200, 1000 shots/point)
    # WARNING: the optimum sits ON the sweep boundary -- fidelity rises
    # monotonically toward high gain AND low frequency, so it is not bracketed.
    # Re-run SingleShot_ReadoutOptimize with gain_start/stop pushed above 3000 and
    # the frequency window extended below 6818.10 to find the true maximum.
    '3': {'Readout': {'Frequency': 6818.105, 'Gain': 2900}, # 600 too much
        #   'Qubit': {'Frequency': 1683.3482587064677, 'Gain': 5000,  "pi2_Gain": 3975 // 2,"sigma": 1 , "flattop_length": 1},
                'Qubit': {'Frequency': 1682.5, 'Gain': 7200,  "pi2_Gain": 7200 // 2,"sigma": 0.09 , "flattop_length": None},
          'outerfoldername': QubitFolders['3']},

    '4': {'Readout': {'Frequency': 7288.48, 'Gain': 1180}, #7288.48 1180 400 good, 420 too much i think 600 too much. with directional coupler: 1400 good 1500maybe too much
          'Qubit': {'Frequency':    2306.308975, 'Gain': 7009,  "pi2_Gain": 7009 // 2 ,"sigma": 0.22, "flattop_length": None}, # qubit, 7468 was the previous pi pulse with sigma = 0.15, 5396 0.225 6435 2603.33 used for ramsey 7009 // 2
          'outerfoldername': QubitFolders['4']},

    # TODO
    '5': {'Readout': {'Frequency': 6970.59, 'Gain': 1500}, # 4500 with directional coupler 1500 good without-
          'Qubit': {'Frequency':  2758.3, 'Gain': 4000, "pi2_Gain": 4000 // 2, "sigma": 1, "flattop_length": None}, #2756.685
          'outerfoldername': QubitFolders['5']}, # qubit, T1 found

    # TODO
    '6': {'Readout': {'Frequency': 7285.11, 'Gain': 800},
          'Qubit': {'Frequency': 3055.2, 'Gain': 4600,  "pi2_Gain": 4750 // 2, "sigma": 0.1 , "flattop_length": None}, # cant find
          'outerfoldername': QubitFolders['6']},
    }
############## End Device 2 ############################

start_voltage = 0.000 # sets voltage for the entire experiment #0.0059 working for good T2Rs

# Charge line (YOKO GS200 over USB / USBTMC). Set False to run without it: the context
# gets a NullYoko stub holding the voltage at start_voltage, so transmission /
# two-tone / Rabi / T1 / T2 / T2E / single-shot all run normally. Any experiment
# that actually steps the voltage (RunChargeSweep, RunChargeDispersion*,
# RunModifiedRamsey*, Run2ToneChargeDispersionQuasiCW) will raise rather than
# silently record data from a voltage that never moved.
UseYoko = True
# USBTMC address of the charge-line yoko: YOKOGAWA,GS210,91T621492,2.02
# (vendor 0x0B21, model 0x0039). Was 'GPIB1::9::INSTR' before the move to USB.
# NOTE: list_resources() also reports a second GS200-class device with serial
# 91s929899 that never accepts a session (VI_ERROR_NCIC) -- a stale enumeration,
# not this box. Match on the serial above, not on position in the list.
# If the box is swapped or re-enumerated, list candidates with:
#   python -c "import pyvisa; print(pyvisa.ResourceManager().list_resources())"
yoko_addr = 'USB0::0x0B21::0x0039::91T621492::0::INSTR'

Qubit_Readout = 3
Qubit_Pulse = 3
yoko_fixed = False  # during a charge sweep; lazy way of sweeping two tone spec over time
cavity_min = True   # look for dip, not peak

# ── Readout window for the NON-single-shot experiments ──────────────────────
# ADC integration window / trigger offset [us] for every experiment that runs
# above the rebuild_singleshot_config() call in section 3: transmission,
# two-tone, chi shift, Rabi, T1/T2/T2E, charge dispersion, ModifiedRamsey and
# ActiveResetVerify. The resonator tone duration is derived automatically as
# ADC_Offset + Readout_Time, so don't set "length" separately.
# Longer window -> better SNR per shot, until it exceeds ~T1 of the qubit (the
# tail of the integration then just averages in decayed |e> population).
# The single-shot family below (SingleShot / T1SS / readout+qubit optimize /
# AutoCoherence / ZeroSpanParity) has its OWN window in SS_params, and
# ZeroSpanParity overrides again via ZSP_*Params["read_length"].
Readout_Time = 30   # us, ADC integration window
ADC_Offset   = 1    # us, delay from tone start to ADC trigger
#                     (None -> keep BaseConfig["adc_trig_offset"])


# ══════════════════════════════════════════════════════════════════════════════
# 2. WHAT TO RUN  —  toggle flags + per-experiment parameters
# ══════════════════════════════════════════════════════════════════════════════
Constant2Tone = False
tl = {"tone_length": 151}
ConstantTone = False  # determine cavity frequency

# First measurement on a fresh cooldown: re-find the cavity before trusting any
# of the carried-over qubit frequencies above.
RunTransmissionSweep = False # determine cavity frequency
Transmission_params = {'reps': 10, 'rounds': 10, 'num_points' : 101, 'span': 0.5}

RunTransmissionSweeps = False
ts = {"start_ts_gain": 500, "end_ts_gain": 3000, "ts_step" : 100}

Run2ToneSpec = False
RunSpecGainLengthSweep = False  # nested gain × length sweep (see block below)
RunTrans_QubitSpec = False
RunChargeSweep = False
charge_params = {"voltage_start" : 0.0, "voltage_end" : 0.001, "voltage_step": 0.0001, } # 0.0001 has two periods in it
Spec_relevant_params = {"qubit_gain": 1000, "SpecSpan": 1.5, "SpecNumPoints": 101, # Q3 2026-07-01 json: qubit_gain 5000
                        "qubit_length" : 30, # length of flattop pulse when gauss = False; Q3 json: 100
                        "reps": 20, 'rounds': 10,
                        'Gauss': False, "sigma": 2, "gain": 1000,  # Q3 json: qubit_pulse_style "const" -> Gauss False
                        'relax_delay' : 1500,
                        "display": True, 'min_sep_MHz':0.2,
                        "fit_window_mhz": 0.5, "prominent_ratio": 0.1, # 500 used for charge sweeps
                        # ── RunSpecGainLengthSweep controls ──────────────────────────────────
                        "sweep_lengths": list(range(10,101,10)),         # qubit_length values to sweep
                        "sweep_gains":   list(range(200, 5001, 100)),  # qubit_gain values to sweep
                        }

StabilizeTwoTone = False

RunChargeDispersionQuasiCW = False
RunChargeDispersionRamsey = False # uses pi and pi /2 pulses; these should already be tuned up. you should also choose the frequency at one of the extrema

# middle frequency: 2306.310396009901
ChargeDispersion_params = {
    "upper_freq": 2306.567327,
    "lower_freq": 2306.032673,
    "probe_freq": 2306.567327,
    "relax_delay": 2000,
    "repetitions": 500,
}

Run2ToneChargeDispersionQuasiCW = False   # new automated mode

# Modified Ramsey for charge-parity switching: two-tone search -> fixed-tau Ramsey.
# tau is automatically set to 1/(2*df) where df is the measured peak separation.
# f_ge is automatically set to the higher-frequency peak.
# ModifiedRamsey_params["relax_delay"] applies only to the two-tone search. The
# fixed-tau Ramsey uses the separate mr_relax_delay below (zero by default);
# enable its hardware active reset when deterministic |g> preparation is required.
RunModifiedRamsey = True

TwoToneChargeDispersion_params = {
    "df": 0.5,                 # required peak separation in MHz
    "dV": 0.0005,                # voltage step in V
    "voltage_min": 0.000,       # absolute lower bound
    "voltage_max": 0.010,       # absolute upper bound
    "max_voltage_tries": 1000,    # max search steps per cycle
    "num_cycles": 1000,           # how many times to repeat: search -> quasiCW -> restart
    "use_upper_peak": True,     # True -> probe higher-frequency peak, False -> lower-frequency peak
    "center_peak_tol_mhz": 0.05,

    # two-tone spec settings used during the search
    "SpecSpan": 1.0,
    "SpecNumPoints": 101,
    "reps": 10,
    "rounds": 10,
    "relax_delay": 850,
    "Gauss": True,
    "sigma": 2,
    "gain": 500,
    "qubit_length": 2,

    # quasi-CW settings once the peaks are separated enough
    "qcw_repetitions": 1000,
    "qcw_relax_delay": 850,
}

ModifiedRamsey_params = {
    # --- fixed-frequency mode: skip the two-tone calibration entirely ---------
    # True  -> no per-cycle spec sweep and no yoko voltage walk. Every cycle runs
    #          the Ramsey at fixed_f_ge with tau = 1/(2*fixed_df).
    # False -> the two-tone doublet search below picks f_ge and df each cycle.
    "skip_two_tone_search": True,
    # Set exactly ONE of fixed_f_center / fixed_f_ge. They differ by df/2, which is
    # exactly where the parity contrast is ZERO -- swapping them gives a dead-flat
    # trace at 0.5 with no error (see the long note in runs/charge_parity.py).
    "fixed_f_center": 1682.47,  # MHz CENTER of the parity doublet
    "fixed_f_ge": None,         # MHz UPPER parity peak (alternative to the centre)
    "fixed_df": 0.12,          # MHz separation that sets tau; None -> center_peak_df_for_tau
    "fixed_voltage": None,     # V one-time yoko move before cycling; None -> hold current V

    # --- periodic two-tone: interleave one spec every N traces -----------------
    # N -> the two-tone spec runs at the START of cycles 0, N, 2N, ... and the
    #      cycles in between go straight to the Ramsey.
    # None / 0 -> old behaviour (every cycle, or never when skip_two_tone_search).
    # With skip_two_tone_search=True the re-check is a SINGLE spec at the held
    # voltage (no yoko walk), so the doublet gets recorded alongside the parity
    # traces and any drift off fixed_f_center shows up as a WARNING in the log.
    "two_tone_every_n_cycles": 10,
    # False (default in fixed mode) -> the re-check is diagnostic: f_ge/df stay at
    #   the fixed values above, so tau is identical for every trace in the run.
    # True -> a resolved doublet re-centres f_ge/df for the following cycles
    #   (tracks drift, but tau then varies between traces).
    "two_tone_recheck_updates_freq": True,

    # --- two-tone search settings (same role as TwoToneChargeDispersion_params) ---
    "df": 0.5,                  # required peak separation in MHz before running Ramsey
    "dV": 0.0005,               # voltage step size [V]
    "voltage_min": 0.000,       # absolute lower voltage bound [V]
    "voltage_max": 0.010,       # absolute upper voltage bound [V]
    "max_voltage_tries": 1000,  # max search steps per cycle
    "num_cycles": 1000,         # how many search -> Ramsey cycles to run
    "use_pi_pulse": False,
    "center_peak_tol_mhz": 0.05,
    "center_peak_df_for_tau": 0.5,
    "use_apriori_separator": True,
    "ss_calib_shots": 1000,
    "ss_recalib_every_n_cycles": 10,

    # two-tone spec settings used during the voltage search
    "SpecSpan": 1.0,
    "SpecNumPoints": 201,
    "reps": 10,
    "rounds": 10,
    "relax_delay": 3500,
    "Gauss": True,
    "sigma": 2,
    "gain": 500,
    "qubit_length": 2,

    # --- parity-doublet peak-finder (utils.find_parity_doublet) ---
    # The voltage search now uses the noise-floor-referenced doublet finder:
    # symmetric-pair-about-center selection with sub-bin Lorentzian refinement.
    "prominence_snr": 5.0,        # peak prominence threshold in units of noise sigma
    "min_sep_MHz": 0.02,          # resolution limit for the doublet (NOT df)
    "max_sep_MHz": None,          # None -> full swept span
    "symmetry_tol_MHz": None,     # None -> half span; tighten to enforce symmetry
    "min_height_balance": 0.3,    # min (weaker/stronger) peak-height ratio
    "smooth_window": 5,           # Savitzky-Golay window (odd; <3 disables)
    "fit_window_mhz": 0.1,        # half-width of the Lorentzian refinement window

    # --- live, non-blocking two-tone plotting (utils.save_two_tone_plot) ---
    "live_display": False,        # True -> refresh a persistent figure each attempt
    "live_pause": 0.05,           # plt.pause() seconds per live refresh

    # --- Modified Ramsey settings ---
    # tau is computed automatically as 1 / (2 * peak_sep_MHz)
    # f_ge is set automatically to the higher-frequency peak
    # No relax delay: the preceding measurement collapses the state, but does
    # not guarantee |g>. Enable use_active_reset for deterministic preparation.
    # us of extra inter-shot idle: after the final readout with reset off, after
    # the corrective flip with reset on. Separate from the search relax_delay.
    "mr_relax_delay": 0.0,
    "mr_reps": 10000,             # number of single-shot Ramsey measurements per cycle
    "average_n_shots": 10,
    # Parity -> computational-state mapping (closing pi/2 phase). Opt-in; default
    # off preserves the original standard-scheme behavior.
    "flip_final_pi2": False,      # add 180 deg to closing pi/2 (swap parity->state)
    "symmetric_ramsey": True,    # drive at midpoint f_avg=f_ge-df/2 instead of upper
    # Hardware active reset to |g> per shot (opt-in). The decision is read off
    # the shot's OWN final Ramsey readout, so at reset_cycles=1 the reset costs no
    # extra readout -- a rep is one readout, as with reset off. When True, the driver
    # runs calibrate_active_reset_readout() first: it rotates config["res_phase"]
    # so g/e separate ALONG I and derives the I threshold from the rotated
    # SingleShot blobs (requires use_apriori_separator=True). The threshold is
    # re-derived from each ss recalibration. Validate with RunActiveResetVerify
    # before trusting it in long runs.
    "use_active_reset": True,
    # Manual I threshold override (normalized units). None (recommended) ->
    # auto-derived by the calibration above.
    "readout_threshold": None,
    "reset_cycles": 1,
    "reset_ground_below_threshold": True,
    # Delay between the conditioning readout (tone end) and the corrective pi.
    # Must be >= ~6/kappa of THIS readout resonator so the pi fires on a
    # photon-free (un-Stark-shifted) qubit. 5 us = 6/kappa for the TATQ01/BFEoo
    # Q2 resonator (kappa/2pi = 190 kHz measured 2026-06-06); verify kappa for
    # this device's readout and trim if it is wider.
    "reset_readout_relax_delay": 5.0,
    "post_reset_wait": 0.0,
}

# ── Active-reset verification ────────────────────────────────────────────────
# Validates the hardware active reset that ModifiedRamsey relies on. First runs
# calibrate_active_reset_readout (rotates res_phase so |g>/|e> separate along I
# and derives the I-threshold), then sweeps prep |g>/|e>  ×  reset off/on plus
# two force-pi diagnostics (unconditional corrective pi -> bare post-readout pi
# fidelity), reading the qubit out n_verify_reads times per shot. A working,
# QND reset gives: prep|e>+reset ON  P(|g>) ≈ prep|g>+reset ON ≈ ground readout
# fidelity, and ≫ the prep|e>+reset OFF control, with P(|g>) flat across the
# repeated reads. Saves per-condition data + an overlay plot + a verdict.
# NOTE: runs under the SAME config as RunModifiedRamsey (the block sits before
# the second UpdateConfig rebuild), so the verdict transfers 1:1 to the Ramsey.
RunActiveResetVerify = False
ActiveResetVerify_params = {
    "n_verify_reads": 5,  # back-to-back readouts after the reset block
    "verify_relax_delay": 5.0,  # us between consecutive verification readouts
    "reps": 2000,  # single shots per condition
    "reset_cycles": 1,  # measure->feedback rounds per shot
    # 5 us >= 6/kappa keeps the corrective pi off the photon-loaded resonator;
    # keep equal to ModifiedRamsey_params["reset_readout_relax_delay"] so ARV
    # validates the same timing the Ramsey uses.
    "reset_readout_relax_delay": 5.0,  # us after each reset readout
    "post_reset_wait": 0.0,  # us settle after the reset block
    "relax_delay": 5000,  # us between reps (>= 3*T1 to re-thermalise; matches
    #                       the 3-5*T1 convention used by T1/T2E above)
    "plotDisp": True,
}

# ── ModifiedRamsey fix-set verification ──────────────────────────────────────
# Regression suite for the ModifiedRamsey fixes (tone coverage, ro_chs keying,
# mr_relax_delay, acquire guards, config validation, sign-safe reset compare,
# the timing model, buffer de-interleave, and the acc_buf shot source). Needs
# NO qubit signal, NO single-shot calibration and NO yoko, so it is the right
# thing to run on a fresh cooldown / after any qick or bitstream change.
# Offline checks first (soccfg only), then the board stages; finishes with one
# fixed-voltage ModifiedRamsey acquisition that exercises the full save path.
# See Experiments/verify_ModifiedRamsey.py for what each check proves.
RunVerifyModifiedRamsey = False
VerifyModifiedRamsey_params = {
    "run_offline": True,        # tier A against the live soccfg first
    "refresh_snapshot": True,   # rewrite the committed soccfg snapshot
    "force": False,             # continue even if an earlier stage failed
    "buffer_reps": 200,
    "raw_i_reps": 1000,
    "rep_period_reps": 5000,    # timing is differential; this is the fit length
    "run_fixed_voltage_ramsey": True,
    "ramsey_params": {
        # f_ge defaults to ctx.qubit_frequency_center; df is arbitrary here --
        # without a charge-parity doublet it only sets tau = 1/(2*df).
        "df": 0.5,
        "mr_reps": 2000,
        "mr_relax_delay": 0.0,
        "use_active_reset": False,
    },
}

RunModifiedRamsey_Control = False  # two-tone search -> half-period step -> sweet-spot interpolation -> Ramsey

ModifiedRamsey_Control_params = {
    # --- two-tone search settings (identical role to ModifiedRamsey_params) ---
    "df": 0.5,                  # required peak separation in MHz to accept V1
    "dV": 0.0005,               # voltage step [V]
    "voltage_min": 0.000,
    "voltage_max": 0.010,
    "max_voltage_tries": 1000,
    "num_cycles": 1000,

    # two-tone spec hardware settings
    "SpecSpan": 1.0,
    "SpecNumPoints": 101,
    "reps": 10,
    "rounds": 10,
    "relax_delay": 1500,
    "Gauss": True,
    "sigma": 2,
    "gain": 700,
    "qubit_length": 2,

    # --- charge-dispersion fit parameters (from independent calibration) ---
    # S(V) ≈ cd_max_mhz * |cos(2π*(V-V0)/T)| where T = cd_period_mv mV
    "cd_max_mhz": 0.682,         # peak charge dispersion from fit [MHz]
    "cd_period_mv": 4.37,        # period of dispersion vs yoko voltage [mV]

    # --- sweet-spot verification ---
    # After moving to V_sweet, a new two-tone is taken.  If the measured
    # separation is below this threshold (or only one peak is found) the
    # sweet spot is flagged as verified.  Either way the Ramsey still runs.
    "sweet_spot_max_df_mhz": 0.1,

    # --- Modified Ramsey settings at the sweet spot ---
    # tau is computed from S1 (the separation found at V1), NOT from S_sweet
    # (which is ~0), so it matches the tau that ModifiedRamsey would use at V1.
    # f_ge is set from the two-tone at V_sweet (average of peaks, or single peak).
    # us of extra inter-shot idle: after the final readout with reset off, after
    # the corrective flip with reset on. Separate from the search relax_delay.
    "mr_relax_delay": 0.0,
    "mr_reps": 500,
    # hysteresis / moving-average: set via setdefault below (same as ModifiedRamsey)
}

RunChiShift = False
ChiShift_params = {"reps": 10,
                    'rounds': 100,# this will used for all experiements below unless otherwise changed in between trials
                    "TransSpan": 1,  ### MHz, span will be center+/- this parameter
                    "TransNumPoints": 101,
                    "cavity_shift": 0.2,
                    "relax_delay": 4000}

RunAmplitudeRabi = False
Amplitude_Rabi_params = {"qubit_freq": Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency'],
                         "max_gain": 30000, 'number_of_steps': 101,
                         "reps": 10, 'rounds': 10,
                         'relax_delay': 5000,
                         'fit' : False}  #Always change the max gain if you don't see it, also compare what you get with Transmission data

RunT1 = False
RunT2 = False
T1T2_params = {"T1_step": 50, "T1_expts": 60, "T1_reps": 10, "T1_rounds": 10, # 80 100 30 30
               "T2_step": 0.25, "T2_expts": 100, "T2_reps": 20, "T2_rounds": 20, "freq_shift": 0.0,
               "relax_delay": 3500, # 5000
               'repetitions': 1000}

RunT1T2E = False

RunT1T2RT2E = False

RunT2E = False
T2E_params = {"T2_max_us": 120, "T2_expts": 121, "T2_reps": 25, "T2_rounds": 25, "freq_shift": 0.0,
               "relax_delay": 3500, 'num_pi_pulses': 1, #need odd number of pulses
              "rotation_angle": None,
              "min_max": None,
              'repetitions': 3000}

SingleShot = False
# NOTE: "Readout_Time"/"ADC_Offset" here are the single-shot regime's own readout
# window (applied by rebuild_singleshot_config in section 3) and are INDEPENDENT of
# the Readout_Time/ADC_Offset globals in section 1, which cover everything above it.
SS_params = {"Shots": 1000, "Readout_Time": 30, "ADC_Offset": 1, "Qubit_Pulse": [Qubit_Pulse],
             'number_of_pulses': 2, 'relax_delay': 5000, "pi2_SS": True} # keep at 15

# Single-shot readout with NO qubit drive: just look at the IQ blobs the readout
# produces on an undriven qubit. Uses the same readout tone/window as SingleShot
# above (Readout_Time / ADC_Offset from SS_params); no qubit pulse is ever played,
# so no readout fidelity is reported. Reports the cloud center/width and, when a
# second blob is resolvable, its population.
RunUndrivenSingleShot = False   # not "UndrivenSingleShot": that name is the imported experiment class
US_params = {"Shots": 5000,            # more shots than SS: a small secondary blob needs statistics
             "relax_delay": 5000,      # us, omit to inherit SS_params['relax_delay']
             "min_separation_sigma": 2.0,  # blobs must be this far apart (combined sigma) to be called two
             "plotDisp": True}

RunT1SS = False
T1SS_params = {"T1_step": 80, "T1_expts": 100,
               "reps": 2000,
               'angle': 0, 'threshold': 0,
               "relax_delay": 8000,
               'calibrate_SS': True,
               'repetitions': 3000}

SingleShot_ReadoutOptimize = False
SS_R_params = {"gain_start": 1000, "gain_stop": 3000, "gain_pts": 21, "span": 0.1, "trans_pts": 21}

SingleShot_QubitOptimize = False
SS_Q_params = {"q_gain_span": 1000, "q_gain_pts" : 41, "q_freq_span": 2, "q_freq_pts": 21,
               'number_of_pulses': 1} # for optimizing pi/2 pulse, set the gain to the half of its value and optimize for n=2

# ── Automated T1 / T2 / T2Echo calibration ──────────────────────────────────
# Set RunAutoCoherence = True to run the full automated calibration pipeline.
# Override any entry in AUTO_COHERENCE_PARAMS by adding it to the dict below.
RunAutoCoherence = False

# Skip the Stage 1 sweet-spot search (two-tone sweep + yoko voltage walk).
# True  -> use the qubit frequency from Qubit_Parameters and hold the current
#          yoko voltage; go straight to Rabi / SingleShot / T1 / T2 / T2E.
# False -> run the full sweet-spot search before calibration.
SkipSweetSpotSearch = True

# Stage 1.5: re-centre f_ge with one two-tone spec at the current voltage
# (no yoko move) before AmplitudeRabi.  Default: run.
CalibrateQubitFreq = True

AutoCoherence_override_params = {
    "skip_sweet_spot_search": SkipSweetSpotSearch,
    "calibrate_qubit_freq":   CalibrateQubitFreq,
    # Examples (uncomment and edit to override defaults):
    # "spec_span":        1.0,    # MHz, ±span for two-tone spec
    # "spec_sigma":       2.0,    # us,  Gaussian sigma for spec drive
    # "rabi_max_gain":    12000,  # max gain for AmplitudeRabi
    # "ss_target_fidelity": 0.70, # minimum SingleShot fidelity
    # "T1_repetitions":   1,
    # "T2_repetitions":   1,
    # "T2E_repetitions":  1,
    # "cd_period_mv":     4.37,   # mV, charge-dispersion period if known

    # "extended_pi_pi2_opt":  False, # use extended pi and pi/2 optimization
    "ss_gain_span_frac": 0.6, # how much of single shot to search
    "ss_gain_pts": 100, # how many points in single shot space to search

    "auto_readout_opt":      True,

        # ── T1 ──────────────────────────────────────────────────────────────────
    # "T1_step":         40,        # us – wait-time step
    # "T1_expts":        60,        # number of time points
    # "T1_reps":         20,
    # "T1_rounds":       20,
    # "T1_relax_delay":  3500,      # us
    "T1_repetitions":  3,         # number of consecutive T1 runs

    # ── T2 Ramsey ───────────────────────────────────────────────────────────
    "T2_step":         0.1,       # us – Ramsey delay step
    "T2_expts":        401,
    # "T2_reps":         20,
    # "T2_rounds":       20,
    # "T2_relax_delay":  3500,      # us
    "T2_repetitions":  3,
    # "T2_freq_shift":   0.0,       # MHz – artificial detuning from f_ge

    # ── T2Echo ──────────────────────────────────────────────────────────────
    "T2E_max_us":       500,      # us – maximum echo time
    # "T2E_expts":        201,
    # "T2E_reps":         25,
    # "T2E_rounds":       25,
    # "T2E_relax_delay":  3500,     # us
    # "T2E_num_pi_pulses": 1,       # must be odd
    "T2E_repetitions":  3,
}

# ── Zero-span charge-parity switching measurement ───────────────────────────
# Device-agnostic acquisition (mZeroSpanParity) + offline analysis
# (analyze_ZeroSpanParity). Full configuration contract:
#   docs/superpowers/specs/2026-05-16-bfc-charge-parity-zero-span-design.md §5
#
# Operates on the currently-selected Qubit_Readout/Qubit_Pulse qubit, reusing the
# resonator/qubit frequencies and gains derived below (resonator_frequency_center,
# qubit_gain, cavity_gain, qubit_frequency_center). Set RunZeroSpanParity = True,
# edit the blocks here, then run this file.
#
# Hard constraints (validated fail-fast in ZeroSpanParity.__init__, spec §5.3).
# Numbers below are for the BFG ZCU216: tProc 430.08 MHz, readout f_output
# 307.2 MHz, avg_maxlen 16384, buf_maxlen 1024. Run
# Experiments/_loopback_check_ZeroSpanParity.py to print the live values.
#   sample_period_us >= adc_trig_offset + read_length + 1.0
#   us2cycles(sample_period_us | capture_length_us) <= 65535  -> <= 152 us
#   reps_per_chunk <= avg_maxlen (16384), unless allow_reps_over_avg_maxlen=True
#   decimated read_length < buf_maxlen / f_output  -> < 3.33 us  (see below)
#
# BEFORE THE FIRST RUN ON A QUBIT: pass the loopback gate
# (Experiments/_loopback_check_ZeroSpanParity.py). It is what verifies the readout
# window, the per-rep cadence, and the I/Q scale against the single-shot
# separator — none of which are visible in the saved data if they are wrong.
RunZeroSpanParity = False

# Acquisition mode + trigger source
ZSP_RunMode  = "strobe"      # "strobe" (Path A, v1) | "decimated" (Path B, v2)
ZSP_StartSrc = "internal"    # "internal" (spontaneous) | "external" (triggered)

# Recalibration toggles
#
# ParityFreqs is OFF for the Q3 pipeline validation: Q3 is not on a charge line, so
# there is no controllable charge-parity doublet to find. 82 narrow two-tone scans
# taken 2026-07-28 across 0.6 -> 480 mV overlay perfectly (the line does not move),
# and find_two_tone_peaks just returns two adjacent noise bins 7-8 steps apart --
# always the same fixed frequencies (1682.3663 / 1682.5743). Running the
# recalibration would park the drive on a noise bin and report a "doublet" that
# isn't one. Park manually at the line centre instead; see the cache below.
ZSP_RecalibrateParityFreqs = False  # run a narrow QubitSpecSliceFF first
ZSP_RecalibrateSeparator   = True   # run single-shot pi-pulse g/e calibration

# Calibration cache (used when the matching Recalibrate flag is False)
#
# No doublet on Q3 (see above): both entries are the single qubit line centre, so
# the drive parks on resonance. That is the right choice for validating the
# pipeline -- on-resonance CW drive gives the largest drive-on/off contrast, which
# is what the stage-3 modulation gate measures -- but it is NOT a parity
# measurement. Expect a unimodal IQ cloud, which is the correct negative result.
ZSP_ParityFreqs_Cached = {
    "lower_peak_MHz":  1682.37,      # Q3 line centre (QubitSpecFF 2026-07-28)
    "higher_peak_MHz": 1682.57,
    "which_to_park":   "higher",     # "lower" | "higher"
}
ZSP_Separator_Cached = {
    "g_center": None, "e_center": None, "normal": None, "midpoint": None,
}

# Narrow two-tone spec used when ZSP_RecalibrateParityFreqs=True (mirrors the
# Run2ToneSpec block; centered on qubit_frequency_center).
ZSP_ParitySpec_params = {
    "SpecSpan": 1.0, "SpecNumPoints": 201,
    "reps": 10, "rounds": 10, "relax_delay": 3500,
    "Gauss": True, "sigma": 2, "gain": 500, "qubit_length": 2,
    "min_sep_MHz": 0.2, "fit_window_mhz": 0.5, "prominent_ratio": 0.1,
}

# Strobe-mode params (Path A). Total record (s) =
# reps_per_chunk * n_chunks * sample_period_us * 1e-6 (~24 s for the values below).
#
# read_length is the SNR knob and it dominates whether parity is resolvable at
# all: per-sample discrimination scales as sqrt(read_length), and the parity
# contrast is only a fraction of the full g/e separation to begin with. Keep it
# equal to SS_params["Readout_Time"] so the g/e separator is calibrated in the
# same readout regime the strobe trace is taken in — otherwise the fidelity you
# measured in SingleShot is not the fidelity you get here.
#
# There is no reason to spend that SNR on a fast cadence: parity lifetimes are
# expected in the ms range, so a 40 us sample period already oversamples by ~75x.
# sample_period_us also sets the const-tone length, so it must clear the rule-1
# floor (adc_trig_offset + read_length + 1.0 = 32 us here) and stay under ~152 us.
ZSP_StrobeParams = {
    "sample_period_us": 40.0,    # >= 32.0 (rule 1), <= 152 (rule 2)
    # SMOKE RUN: 2000 x 1 x 40 us = 0.08 s. Long enough to check shapes, the
    # per-rep cadence, the I/Q scale against the separator and the plots; short
    # enough to iterate on. Restore 10000 / 60 (-> 24 s) for a real record.
    "reps_per_chunk":   20_000_000,    # <= avg_maxlen 16384
    "n_chunks":         1,       # -> 0.08 s total record
    "read_length":      30.0,    # == SS_params["Readout_Time"]
    "adc_trig_offset":  1.0,     # == SS_params["ADC_Offset"]
    # Opt in to reps_per_chunk > avg_maxlen. The accumulated buffer is circular and
    # streamed during the run, so a single long chunk is legal and avoids the real
    # time gap that every chunk boundary puts in the record. It stays opt-in
    # because the run raises if the host cannot keep up — confirm with the loopback
    # gate before using it for a long record.
    "allow_reps_over_avg_maxlen": True,
}

# Decimated-mode params (Path B).
#
# NOT USABLE ON THIS BOARD for a parity telegraph: buf_maxlen is 1024 decimated
# samples at f_output = 307.2 MHz, i.e. a maximum capture of 3.33 us. Path B needs
# a DDR4-streaming path to be useful here; run ZSP_RunMode = "strobe".
# The values below are legal (so the mode can still be smoke-tested) but far too
# short to hold parity dynamics. capture_length_us must cover
# adc_trig_offset + read_length; soft_avgs must be 1 unless allow_soft_avgs=True
# (>1 averages independent captures and destroys the trajectory).
ZSP_DecimatedParams = {
    "capture_length_us": 6.0,
    "soft_avgs":         1,
    "n_captures":        1,
    "read_length":       3.0,    # must be < buf_maxlen / f_output = 3.33 us
    "adc_trig_offset":   1.0,
    "allow_soft_avgs":   False,
}

# Drive params (mode-independent). qubit_gain/pulse_gain = None -> use the active
# qubit's tuned values (qubit_gain / cavity_gain globals). res_phase = None ->
# inherit the session's calibrated ctx.config["res_phase"], which is what the g/e
# separator was measured in; a hard-coded value that disagrees with it rotates the
# strobe IQ relative to the projection axis.
# qubit_gain: do NOT leave this at None (= ctx.qubit_gain = the pi gain, 7200 for a
# 0.09 us Gaussian). The ZSP drive is CW for the whole sample period, so 7200 for
# 40 us is ~440x the pi area: it saturates the transition and power-broadens the
# line far past any doublet splitting, which destroys the parity selectivity the
# measurement depends on. Use a gain matched to a CONST drive of comparable length
# -- 1000 is what the 30 us two-tone used to resolve this line, so it is known to
# give a response without being a hammer. For real parity work this needs its own
# calibration: the drive must stay weak compared to the doublet splitting.
#
# Q3 CW drive response, measured 2026-07-29 (40 us const drive at 1682.5 MHz,
# 30 us readout, 1000 reps/point, projected onto the g->e axis):
#     gain      0 -> -3.2 %      gain   4000 -> +0.3 %
#     gain    500 -> -2.0 %      gain   7200 -> +27.5 %
#     gain   1000 -> +3.9 %      gain  12000 -> +16.0 %
#     gain   2000 -> +10.7 %     gain  20000 -> +35.4 %
# (percent of the way from |g> to |e>; DAC max is ~29500 at maxv_scale 0.9)
# Non-monotonic -- looks like coherent Rabi structure at a fixed 40 us drive time,
# not saturation. 20000 is chosen for the stage-3 modulation gate because it gives
# the largest on/off contrast (38.6 % of g->e -> block-mean SNR ~19 over 500
# samples), which is what makes the gate decisive. It is deliberately hard driving
# and is fine for a PIPELINE test only: for real parity work the drive must be weak
# compared to the doublet splitting or it power-broadens the selectivity away.
ZSP_DriveParams = {
    "qubit_gain": 20000,
    "pulse_gain": None,
    "res_phase":  None,
}

# Offline-analysis params (see analyze_parity_run docstring).
ZSP_AnalysisParams = {
    # "apriori_axis" (default): project onto the g->e axis from the single-shot
    #   calibration, but take the THRESHOLD from the trace's own two-component fit.
    #   Correct for zero-span, which measures a driven steady state: both parity
    #   states sit at small |e> population, so both land on the same side of the
    #   g/e midpoint.
    # "apriori": thresholds at the g/e midpoint. On a driven trace this labels
    #   every sample the same -> zero switches and a nan tau, with no error.
    # "kmeans": cluster the trace itself; needs no separator.
    "classifier_method":     "apriori_axis",
    "window_us":             1000.0,
    "k_sigma":               5.0,
    "step_us":               None,
    "min_burst_duration_us": None,
    "analysis_bin_us":       None,        # set < read_length for decimated apriori
    "save_plots":            True,
    # Dwell-time debouncing. Runs shorter than min_dwell_bins samples are absorbed
    # into a neighbour before the switch rate AND the dwell statistics are
    # computed. Without it a single-sample classification flicker reads as two
    # parity switches, which biases tau low by >2x at only a few percent
    # misclassification and inflates the burst threshold. Set False for the raw
    # numbers.
    "merge_short_segments":  True,
    "min_dwell_bins":        2,
}

# ============================ VALIDATION HARNESS (spec 2026-06-01) ============================
# Strobe-only. Each block reuses ZSP_Separator_Cached / ZSP_ParityFreqs_Cached and the
# zsp_cfg already built for ZeroSpanParity.
#
# Run ONE stage per session, in this order (spec §6.3), reading the printed verdict
# before enabling the next:
#   1  StaticContrast        optimise read_pulse_freq at a rough qubit branch
#   2  ContrastVsQubitFreq   confirm the f+/f- doublet at that probe point
#   1  StaticContrast again  refine the probe point at the chosen branch
#   3  ModulationCheck       *** THE GATE *** — an injected square wave must come
#                            back in the projected trace. If it does not, the
#                            projection axis / demod / timing is wrong and nothing
#                            downstream means anything. Do not proceed.
#   4  Telegraph             the reference record: is it genuinely two-level?
#   5  BinSizeSweep          pick the analysis bin (reprocesses the stage-4 record)
#   6  ThresholdStability    is tau robust to where the threshold sits?
#   8  ControlSuite          A/B/C must kill the contrast; D should flip the sign
#   7  EnvironmentSweep      does the rate respond to the environment?
#   9  Build_EvidenceReport  collate every sidecar into EVIDENCE.md
#
# Stages 5 and 6 only REPROCESS samples, so they do not need stage 4 re-run every
# time. Precedence for the record they analyse:
#   1. Validate_Telegraph on  -> the record stage 4 just acquired
#   2. otherwise              -> the most recent saved 4_telegraph*.h5 sidecar,
#                                loaded from disk (no acquisition -- iterate on
#                                bin_list_us / threshold_list for free)
#   3. nothing saved          -> a fresh Telegraph_params["n_chunks"] trace
# Either way 5 and 6 see the SAME samples, which is the point: a bin-size or
# threshold comparison across two separately-acquired traces also compares drift
# and a different noise realisation. Each run prints which record it used.
Validate_StaticContrast      = False
Validate_ContrastVsQubitFreq = False
Validate_ModulationCheck     = False      # pipeline-sanity gate -- run first
Validate_Telegraph           = True     # stage 4: bimodality + dwell of one record
Validate_BinSizeSweep        = True     # stage 5: reuses the stage-4 record (see above)
Validate_ThresholdStability  = True     # stage 6: reuses the stage-4 record (see above)
Validate_ControlSuite        = False
Validate_EnvironmentSweep    = False
Build_EvidenceReport         = False

StaticContrast_params = {"freq_span_mhz": 2.0, "n_points": 41, "reps_per_point": 2000}
ContrastVsQubit_params = {"qfreq_span_mhz": 10.0, "n_points": 81}
Modulation_params = {"modulation_freq_hz": 25, "n_periods": 10}
# n_chunks for the stage-4 reference record: 10 x 10000 x 40 us = 4 s, long enough
# for a few hundred switches at a ms-scale parity lifetime.
Telegraph_params = {"n_chunks": 10}
# Analysis bins to compare. Keep the largest below the expected parity lifetime:
# a bin that spans several switches averages them away.
BinSize_params = {"bin_list_us": [40, 100, 200, 500, 1000]}
# None -> a valley-centred grid derived from the trace's own two-component fit
# (NOT percentiles, which for well-separated data sit inside the lobes).
Threshold_params = {"threshold_list": None}
Control_params = {"variants": ["A", "B", "C", "D"], "detune_mhz": 50.0}
# NOTE: the stage-7 hook currently sweeps the readout DAC gain, not true power.
# For a real power sweep, point _set_power in runs/zero_span.py at the Vaunix
# attenuator (PythonDrivers/control_atten.py).
Environment_params = {"param_name": "readout_dac_gain", "values": [2900, 4000, 5000, 6000]}

# ══════════════════════════════════════════════════════════════════════════════
# 3. EXECUTE  (don't edit below)
# ══════════════════════════════════════════════════════════════════════════════
ctx = build_context(
    Qubit_Parameters, Qubit_Readout, Qubit_Pulse, start_voltage,
    Transmission_params=Transmission_params,
    Spec_relevant_params=Spec_relevant_params,
    tl=tl, ts=ts, charge_params=charge_params,
    cavity_min=cavity_min, yoko_fixed=yoko_fixed,
    use_yoko=UseYoko, yoko_addr=yoko_addr,
    readout_length_us=Readout_Time, adc_trig_offset_us=ADC_Offset,
)

# ── Regime A: transmission / spectroscopy / charge-parity / coherence / ARV ──
if Constant2Tone:                    run_constant_two_tone(ctx)
if ConstantTone:                     run_constant_tone(ctx)
if RunTransmissionSweep:             run_transmission_fit(ctx, Transmission_params)
if RunTransmissionSweeps:            run_transmission_sweep(ctx, Transmission_params)
if Run2ToneSpec:                     run_two_tone_spec(ctx, Spec_relevant_params)
if RunSpecGainLengthSweep:           run_spec_gain_length_sweep(ctx, Spec_relevant_params)
if RunChiShift:                      run_chi_shift(ctx, ChiShift_params)
if Run2ToneChargeDispersionQuasiCW:  run_two_tone_charge_dispersion_quasicw(ctx, TwoToneChargeDispersion_params, Spec_relevant_params, ChargeDispersion_params)
if RunModifiedRamsey:                run_modified_ramsey(ctx, ModifiedRamsey_params, Spec_relevant_params)
if RunModifiedRamsey_Control:        run_modified_ramsey_control(ctx, ModifiedRamsey_Control_params)
if RunChargeDispersionQuasiCW:       run_charge_dispersion_quasicw(ctx, ChargeDispersion_params, Spec_relevant_params)
if RunChargeDispersionRamsey:        run_charge_dispersion_ramsey(ctx, T1T2_params, ChargeDispersion_params)
if RunAmplitudeRabi:                 run_amplitude_rabi(ctx, Amplitude_Rabi_params)
if RunT1:                            run_t1(ctx, T1T2_params)
if RunT1T2E:                         run_t1_t2e(ctx, T1T2_params, T2E_params)
if RunT1T2RT2E:                      run_t1_t2r_t2e(ctx, T1T2_params, T2E_params)
if RunT2:                            run_t2(ctx, T1T2_params)
if RunT2E:                           run_t2e(ctx, T2E_params)
if RunTrans_QubitSpec:               run_trans_qubit_spec(ctx, Spec_relevant_params, T1T2_params)
if RunChargeSweep:                   run_charge_sweep(ctx, Spec_relevant_params)
if RunActiveResetVerify:             run_active_reset_verify(ctx, ActiveResetVerify_params)
if RunVerifyModifiedRamsey:          run_verify_modified_ramsey(ctx, VerifyModifiedRamsey_params)

# ── switch to the single-shot config regime (original top-level rebuild @ old line 2990) ──
rebuild_singleshot_config(ctx, SS_params)

# ── Regime B: single-shot family ──
if SingleShot:                       run_single_shot(ctx, SS_params)
if RunUndrivenSingleShot:            run_undriven_single_shot(ctx, US_params)
if RunT1SS:                          run_t1_ss(ctx, T1SS_params, SS_params)
if SingleShot_ReadoutOptimize:       run_readout_optimize(ctx, SS_R_params)
if SingleShot_QubitOptimize:         run_qubit_optimize(ctx, SS_Q_params, SS_params)
if RunAutoCoherence:                 run_auto_coherence(ctx, AutoCoherence_override_params)
if RunZeroSpanParity:
    run_zero_span_parity(ctx, {
        "ZSP_RunMode": ZSP_RunMode, "ZSP_StartSrc": ZSP_StartSrc,
        "ZSP_RecalibrateParityFreqs": ZSP_RecalibrateParityFreqs,
        "ZSP_RecalibrateSeparator": ZSP_RecalibrateSeparator,
        "ZSP_ParityFreqs_Cached": ZSP_ParityFreqs_Cached,
        "ZSP_Separator_Cached": ZSP_Separator_Cached,
        "ZSP_ParitySpec_params": ZSP_ParitySpec_params,
        "ZSP_StrobeParams": ZSP_StrobeParams,
        "ZSP_DecimatedParams": ZSP_DecimatedParams,
        "ZSP_DriveParams": ZSP_DriveParams,
        "ZSP_AnalysisParams": ZSP_AnalysisParams,
        "Validate_StaticContrast": Validate_StaticContrast,
        "StaticContrast_params": StaticContrast_params,
        "Validate_ContrastVsQubitFreq": Validate_ContrastVsQubitFreq,
        "ContrastVsQubit_params": ContrastVsQubit_params,
        "Validate_ModulationCheck": Validate_ModulationCheck,
        "Modulation_params": Modulation_params,
        "Validate_Telegraph": Validate_Telegraph,
        "Telegraph_params": Telegraph_params,
        "Validate_BinSizeSweep": Validate_BinSizeSweep,
        "BinSize_params": BinSize_params,
        "Validate_ThresholdStability": Validate_ThresholdStability,
        "Threshold_params": Threshold_params,
        "Validate_ControlSuite": Validate_ControlSuite,
        "Control_params": Control_params,
        "Validate_EnvironmentSweep": Validate_EnvironmentSweep,
        "Environment_params": Environment_params,
        "Build_EvidenceReport": Build_EvidenceReport,
    })

ctx.yoko.close()
