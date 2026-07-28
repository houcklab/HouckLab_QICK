"""CSTQ03_BFC — client-facing measurement runner.

Edit the device parameters and per-experiment params below, toggle the RunX
flags, and run this file top-to-bottom. The measurement procedures themselves
live in the `runs/` package (imported via `*` below); this file only selects
what to run. See docs/superpowers/specs/2026-07-02-cstq03-runner-refactor-design.md.
"""

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Runners.runs import *


# ══════════════════════════════════════════════════════════════════════════════
# 1. DEVICE PARAMETERS  (edit every session)
# ══════════════════════════════════════════════════════════════════════════════
temp_dir_Q4 = "C:/Users/ece-houck-j409/Documents/Data/2026-05-29_BFC_Cooldown/CSTQ03/RFSOC/Q4//"

# ── Output folder root — edit this one line ────────────────────────────────
_QubitFolderRoot = "V:/t1Team/Data/2026-05-29_BFC_Cooldown/CSTQ03/RFSOC"
QubitFolders = {str(q): f"{_QubitFolderRoot}/Q{q}//" for q in range(1, 7)}

############## CSTQ03 (clone of CSTQ02_BFC.py + zero-span parity) ######
Qubit_Parameters = {
    # TODO
    '1': {'Readout': {'Frequency': 6757.94, 'Gain': 200}, # 500 okay, 700 too much 520 maybe too much 530 too much
          'Qubit': {'Frequency': 1752, 'Gain': 5000,  "pi2_Gain": 3975 // 2,"sigma": 0.2, "flattop_length": None},
          'outerfoldername': QubitFolders['1']},

    # TODO
    '2': {'Readout': {'Frequency': 7192.01, 'Gain': 4000}, # coarsely tuned to 4000, seeing behavior at 4500
          'Qubit': {'Frequency': 3052.389307, 'Gain': 2055, "pi2_Gain": 2055 // 2, "sigma": 1 , "flattop_length": None}, # qubit, T1 found
          'outerfoldername': QubitFolders['2']},

    '3': {'Readout': {'Frequency': 6879.490105, 'Gain': 550}, # 600 too much
          'Qubit': {'Frequency': 1746, 'Gain': 5000,  "pi2_Gain": 3975 // 2,"sigma": 1 , "flattop_length": 1}, # qubit found 1719.8273
          'outerfoldername': QubitFolders['3']},

    '4': {'Readout': {'Frequency': 7288.48, 'Gain': 1180}, #7288.48 1180 400 good, 420 too much i think 600 too much. with directional coupler: 1400 good 1500maybe too much
          'Qubit': {'Frequency':    2306.308975, 'Gain': 7009,  "pi2_Gain": 7009 // 2 ,"sigma": 0.22, "flattop_length": None}, # qubit, 7468 was the previous pi pulse with sigma = 0.15, 5396 0.225 6435 2603.33 used for ramsey 7009 // 2
          'outerfoldername': QubitFolders['4']},
    
    # TODO
    '5': {'Readout': {'Frequency': 6970.59, 'Gain': 1500}, # 4500 with directional coupler 1500 good without-
          'Qubit': {'Frequency':  2758.3, 'Gain': 4000, "pi2_Gain": 4000 // 2, "sigma": 1, "flattop_length": None}, #2756.685
          'outerfoldername': QubitFolders['5']}, # qubit, T1 found

    # currently working on
    '6': {'Readout': {'Frequency': 7285.11, 'Gain': 800}, 
          'Qubit': {'Frequency': 3055.2, 'Gain': 4600,  "pi2_Gain": 4750 // 2, "sigma": 0.1 , "flattop_length": None}, # cant find
          'outerfoldername': QubitFolders['6']},
    }
############## End Can D ############################

start_voltage = 0.000 # sets voltage for the entire experiment #0.0059 working for good T2Rs

Qubit_Readout = 6
Qubit_Pulse = 6
yoko_fixed = False  # during a charge sweep; lazy way of sweeping two tone spec over time
cavity_min = True   # look for dip, not peak


# ══════════════════════════════════════════════════════════════════════════════
# 2. WHAT TO RUN  —  toggle flags + per-experiment parameters
# ══════════════════════════════════════════════════════════════════════════════
Constant2Tone = False
tl = {"tone_length": 151}
ConstantTone = False  # determine cavity frequency

RunTransmissionSweep = False # determine cavity frequency
Transmission_params = {'reps': 10, 'rounds': 10, 'num_points' : 101, 'span': 5}

RunTransmissionSweeps = False
ts = {"start_ts_gain": 500, "end_ts_gain": 8000, "ts_step" : 500}

Run2ToneSpec = True
RunSpecGainLengthSweep = False  # nested gain × length sweep (see block below)
RunTrans_QubitSpec = False
RunChargeSweep = False
charge_params = {"voltage_start" : 0.0, "voltage_end" : 0.01, "voltage_step": 0.0005, } # 0.0001 has two periods in it
Spec_relevant_params = {"qubit_gain": 6000, "SpecSpan": 1000, "SpecNumPoints": 101, # 750 works Q5
                        "qubit_length" : 50, # length of 50flattop pulse when gauss = False # 9.5 worked
                        "reps": 20, 'rounds': 10,
                        'Gauss': False, "sigma": 2, "gain": 6000,
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
RunModifiedRamsey = False

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
    # UPPER bound on the accepted doublet separation. tau = 1/(2*sep) must leave
    # room for the pi/2 envelopes: ModifiedRamsey now requires sep < 1/(8*sigma)
    # (no pi) or 1/(16*sigma) (echo) and RAISES otherwise instead of silently
    # running at the wrong effective tau. At sigma=0.1 us that is 1.25 MHz;
    # at sigma=0.22 us only 0.57 MHz. Set this below that limit so a
    # well-separated doublet cannot abort the run mid-cycle. 1.0 leaves headroom
    # at sigma=0.1; LOWER IT to <0.57 if you switch to a sigma=0.22 qubit.
    # (None would mean "full swept span" and can now abort a cycle.)
    "max_sep_MHz": 1.0,
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
    "mr_relax_delay": 0.0,       # us after final readout; separate from search relax_delay
    "mr_reps": 40000,             # number of single-shot Ramsey measurements per cycle
    "average_n_shots": 400,
    # Parity -> computational-state mapping (closing pi/2 phase). Opt-in; default
    # off preserves the original standard-scheme behavior.
    "flip_final_pi2": False,      # add 180 deg to closing pi/2 (swap parity->state)
    "symmetric_ramsey": False,    # drive at midpoint f_avg=f_ge-df/2 instead of upper
    # Hardware active reset to |g> per shot (opt-in). When True, the driver
    # runs calibrate_active_reset_readout() first: it rotates config["res_phase"]
    # so g/e separate ALONG I and derives the I threshold from the rotated
    # SingleShot blobs (requires use_apriori_separator=True). The threshold is
    # re-derived from each ss recalibration. Validate with RunActiveResetVerify
    # before trusting it in long runs.
    "use_active_reset": False,
    # Manual I threshold override (normalized units). None (recommended) ->
    # auto-derived by the calibration above.
    "readout_threshold": None,
    "reset_cycles": 1,
    "reset_ground_below_threshold": True,
    # Delay between the conditioning readout (tone end) and the corrective pi.
    # Must be >= ~6/kappa of THIS readout resonator so the pi fires on a
    # photon-free (un-Stark-shifted) qubit. 5 us = 6/kappa for the TATQ01/BFE
    # Q2 resonator (kappa/2pi = 190 kHz measured 2026-06-06); verify kappa for
    # the CSTQ03 readout and trim if it is wider.
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
    "relax_delay": 3500,  # us between reps (>= 3*T1 to re-thermalise; matches
    #                       the 3-5*T1 convention used by T1/T2E above)
    "plotDisp": True,
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
    "mr_relax_delay": 0.0,       # us after final readout; separate from search relax_delay
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
                         "max_gain": 10000, 'number_of_steps': 101,
                         "reps": 20, 'rounds': 20,
                         'relax_delay': 1500,
                         'fit' : False}  #Always change the max gain if you don't see it, also compare what you get with Transmission data

RunT1 = False
RunT2 = False
T1T2_params = {"T1_step": 50, "T1_expts": 60, "T1_reps": 20, "T1_rounds": 20, # 80 100 30 30
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
SS_params = {"Shots": 1000, "Readout_Time": 15, "ADC_Offset": 1, "Qubit_Pulse": [Qubit_Pulse],
             'number_of_pulses': 1, 'relax_delay': 2500, "pi2_SS": False} # keep at 15

RunT1SS = False
T1SS_params = {"T1_step": 80, "T1_expts": 100,
               "reps": 2000,
               'angle': 0, 'threshold': 0,
               "relax_delay": 8000,
               'calibrate_SS': True,
               'repetitions': 3000}

SingleShot_ReadoutOptimize = False
SS_R_params = {"gain_start": 400, "gain_stop": 2000, "gain_pts": 41, "span": 0.1, "trans_pts": 21}

SingleShot_QubitOptimize = False
SS_Q_params = {"q_gain_span": 250, "q_gain_pts" : 11, "q_freq_span": 2, "q_freq_pts": 21,
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
# Hard constraints (validated fail-fast in ZeroSpanParity.__init__, spec §5.3):
#   sample_period_us >= adc_trig_offset + read_length + 1.0
#   us2cycles(sample_period_us | capture_length_us) <= 65535
#   reps_per_chunk <= soccfg['readouts'][ro_ch]['avg_maxlen']
#   decimated read_length samples <= soccfg['readouts'][ro_ch]['buf_maxlen']
RunZeroSpanParity = False

# Acquisition mode + trigger source
ZSP_RunMode  = "strobe"      # "strobe" (Path A, v1) | "decimated" (Path B, v2)
ZSP_StartSrc = "internal"    # "internal" (spontaneous) | "external" (triggered)

# Recalibration toggles
ZSP_RecalibrateParityFreqs = True   # run a narrow QubitSpecSliceFF first
ZSP_RecalibrateSeparator   = True   # run single-shot pi-pulse g/e calibration

# Calibration cache (used when the matching Recalibrate flag is False)
ZSP_ParityFreqs_Cached = {
    "lower_peak_MHz":  None,
    "higher_peak_MHz": None,
    "which_to_park":   "lower",     # "lower" | "higher"
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

# Strobe-mode params (Path A). sample_period_us floor = adc_trig_offset +
# read_length + 1.0 us; reps_per_chunk capped at avg_maxlen; total record (s) =
# reps_per_chunk * n_chunks * sample_period_us * 1e-6 (~12 s for defaults below).
ZSP_StrobeParams = {
    "sample_period_us": 20.0,
    "reps_per_chunk":   10000,
    "n_chunks":         60,
    "read_length":      5.0,
    "adc_trig_offset":  0.488,
}

# Decimated-mode params (Path B). capture_length_us must cover the readout window
# (adc_trig_offset + read_length) and stay under the 16-bit cycle cap. soft_avgs
# must be 1 unless allow_soft_avgs=True (>1 destroys parity trajectories).
# n_captures>1 concatenates back-to-back captures, marking boundaries in
# gap_indices.
ZSP_DecimatedParams = {
    "capture_length_us": 100.0,
    "soft_avgs":         1,
    "n_captures":        1,
    "read_length":       80.0,
    "adc_trig_offset":   0.488,
    "allow_soft_avgs":   False,
}

# Drive params (mode-independent). qubit_gain/pulse_gain = None -> use the active
# qubit's tuned values (qubit_gain / cavity_gain globals).
ZSP_DriveParams = {
    "qubit_gain": None,
    "pulse_gain": None,
    "res_phase":  0,
}

# Offline-analysis params (see analyze_parity_run docstring).
ZSP_AnalysisParams = {
    "classifier_method":     "apriori",   # "apriori" | "kmeans"
    "window_us":             1000.0,
    "k_sigma":               5.0,
    "step_us":               None,
    "min_burst_duration_us": None,
    "analysis_bin_us":       None,        # set < read_length for decimated apriori
    "save_plots":            True,
}

# ============================ VALIDATION HARNESS (spec 2026-06-01) ============================
# Strobe-only. Each block reuses ZSP_Separator_Cached / ZSP_ParityFreqs_Cached and the
# zsp_cfg already built for ZeroSpanParity. Run order: stage1 -> stage2 -> stage1 refine ->
# stage3 (gate) -> stage4 -> 5/6 -> 8 -> 7 -> 9.  See spec 6.3.
Validate_StaticContrast      = False
Validate_ContrastVsQubitFreq = False
Validate_ModulationCheck     = False     # pipeline-sanity gate -- run first
Validate_ControlSuite        = False
Validate_EnvironmentSweep    = False
Build_EvidenceReport         = False

StaticContrast_params = {"freq_span_mhz": 2.0, "n_points": 41, "reps_per_point": 2000}
ContrastVsQubit_params = {"qfreq_span_mhz": 10.0, "n_points": 81}
Modulation_params = {"modulation_freq_hz": 25, "n_periods": 10}
Control_params = {"variants": ["A", "B", "C", "D"], "detune_mhz": 50.0}
Environment_params = {"param_name": "power_dB", "values": [-10, -8, -6, -4]}

# ══════════════════════════════════════════════════════════════════════════════
# 3. EXECUTE  (don't edit below)
# ══════════════════════════════════════════════════════════════════════════════
ctx = build_context(
    Qubit_Parameters, Qubit_Readout, Qubit_Pulse, start_voltage,
    Transmission_params=Transmission_params,
    Spec_relevant_params=Spec_relevant_params,
    tl=tl, ts=ts, charge_params=charge_params,
    cavity_min=cavity_min, yoko_fixed=yoko_fixed,
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

# ── switch to the single-shot config regime (original top-level rebuild @ old line 2990) ──
rebuild_singleshot_config(ctx, SS_params)

# ── Regime B: single-shot family ──
if SingleShot:                       run_single_shot(ctx, SS_params)
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
        "Validate_ControlSuite": Validate_ControlSuite,
        "Control_params": Control_params,
        "Validate_EnvironmentSweep": Validate_EnvironmentSweep,
        "Environment_params": Environment_params,
        "Build_EvidenceReport": Build_EvidenceReport,
    })

ctx.yoko.close()
