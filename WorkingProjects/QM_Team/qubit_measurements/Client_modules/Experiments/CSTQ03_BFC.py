# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
from utils import *
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Calib.initialize4Q import *
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.socProxy import *
import time
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mTransmissionFF import CavitySpecFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSingleTone import SingleTone

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSpecSliceFF import QubitSpecSliceFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mChargeDispersionQuasiCW import ChargeDispersionQuasiCW
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mAmplitudeRabiFF import AmplitudeRabiFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mAmplitudeRabiFF_noUpdate import AmplitudeRabiFF_N
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mChiShift import ChiShift

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT1FF import T1FF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT2R import T2R
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT2EFF import T2EMUX
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSingleShotProgramFFMUX import SingleShotProgramFFMUX
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT1_SS import T1_SS
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mOptimizeReadoutandPulse_FF import ReadOpt_wSingleShotFF, QubitPulseOpt_wSingleShotFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mConstantTwoTone import ConstantTwoTone
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mChargeDispersion import ChargeDispersion
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mModifiedRamsey import ModifiedRamsey
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
import pyvisa
from scipy.signal import find_peaks, savgol_filter
from datetime import datetime
import matplotlib.dates as mdates
import json
from sklearn.cluster import KMeans
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mAutoCoherence import (
    run_auto_coherence, AUTO_COHERENCE_PARAMS, find_sweet_spot)

# Zero-span charge-parity switching measurement (device-agnostic acquisition +
# offline analysis). pick_parity_drive_freq / chunked_acquire / ramp_to come in
# via `from utils import *` above.
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mZeroSpanParity import ZeroSpanParity
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity import analyze_parity_run
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.validate_ZeroSpanParity import (
    run_static_contrast, run_contrast_vs_qubit_freq, run_modulation_check,
    run_control_suite, run_environment_sweep, build_evidence_report,
)

def _extract_iq_from_singleshot_data(data_ss, state="g"):
    """
    Extracts SingleShotProgramFFMUX IQ arrays.

    state="g" uses ground-prep IQ.
    state="e" uses excited-prep IQ.
    state="thermal" uses thermal IQ if available.
    """
    d = data_ss["data"]

    key_pairs = {
        "g": [
            ("i_g0", "q_g0"),
            ("i_g", "q_g"),
            ("Ig", "Qg"),
        ],
        "e": [
            ("i_e0", "q_e0"),
            ("i_e", "q_e"),
            ("Ie", "Qe"),
        ],
        "thermal": [
            ("i_thermal0", "q_thermal0"),
            ("i_thermal", "q_thermal"),
        ],
    }

    for i_key, q_key in key_pairs.get(state, []):
        if i_key in d and q_key in d:
            return np.ravel(np.array(d[i_key])), np.ravel(np.array(d[q_key]))

    print("[SingleShot MR Calib] Available data keys:", d.keys())
    raise KeyError(f"Could not find raw I/Q arrays for state={state}.")
def get_apriori_separator_from_singleshot(config, soc, soccfg, outerFolder):
    """
    Runs one SingleShot calibration using a pi pulse.
    Uses the returned ground/excited blobs to define a fixed separator.
    Also saves the SingleShot data/config/png through the normal SingleShot methods.
    """

    ss_shots = ModifiedRamsey_params.get("ss_calib_shots", 1000)

    cfg_ss = config.copy()
    cfg_ss["number_of_pulses"] = 1
    cfg_ss["shots"] = ss_shots
    cfg_ss["reps"] = ss_shots
    cfg_ss["qubit_gain"] = qubit_gain
    cfg_ss["f_ge"] = qubit_frequency_center
    cfg_ss["sigma"] = qubit_sigma
    cfg_ss["flattop_length"] = qubit_flattop
    cfg_ss["Qubit_number"] = Qubit_Readout
    cfg_ss["Read_Indeces"] = Qubit_Readout

    inst_ss = SingleShotProgramFFMUX(
        path="SingleShot_MRCalib",
        outerFolder=outerFolder,
        cfg=cfg_ss,
        soc=soc,
        soccfg=soccfg
    )

    data_ss = SingleShotProgramFFMUX.acquire(inst_ss)

    # Save SingleShot data, config, and display png.
    SingleShotProgramFFMUX.display(inst_ss, data_ss, plotDisp=False)
    SingleShotProgramFFMUX.save_data(inst_ss, data_ss)
    SingleShotProgramFFMUX.save_config(inst_ss)

    d = data_ss["data"]

    Ig = np.ravel(np.array(d["i_g0"]))
    Qg = np.ravel(np.array(d["q_g0"]))
    Ie = np.ravel(np.array(d["i_e0"]))
    Qe = np.ravel(np.array(d["q_e0"]))

    g_center = np.array([np.mean(Ig), np.mean(Qg)])
    e_center = np.array([np.mean(Ie), np.mean(Qe)])

    normal = e_center - g_center
    midpoint = 0.5 * (g_center + e_center)

    print("[ModifiedRamsey] A priori separator from saved SingleShot:")
    print(f"  g_center = {g_center}")
    print(f"  e_center = {e_center}")
    print(f"  midpoint = {midpoint}")
    print(f"  normal   = {normal}")
    print(f"  separation = {np.linalg.norm(normal):.6f}")

    return {
        "g_center": g_center,
        "e_center": e_center,
        "normal": normal,
        "midpoint": midpoint,
        "data_ss": data_ss,
    }


# from q4diamond.Client_modules.Experiment_Scripts.mT2R import T2R
# from q4diamond.Client_modules.Experiment_Scripts.mChiShift import ChiShift
# from q4diamond.Client_modules.Experiment_Scripts.mSingleShotProgramFF import SingleShotProgramFF
# from q4diamond.Client_modules.Experiment_Scripts.mOptimizeReadoutandPulse_FF import ReadOpt_wSingleShotFF, QubitPulseOpt_wSingleShotFF

soc, soccfg = makeProxy()

"""
'4': {'Readout': {'Frequency': 7288.505, 'Gain': 1400}, # 1500 is too high # 1250
          'Qubit': {'Frequency': 2306.3, 'Gain': 26060,  "pi2_Gain": 26060 // 2,"sigma": 0.06, "flattop_length": None}, 
          'outerfoldername':"V:/t1Team/Data/2026-3-9_BFC_Cooldown/CSTQ03/RFSOC/Q4//"},
^ with Q4 charge line 
"""

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
# yoko
start_voltage = 0.000 # sets voltage for the entire experiment #0.0059 working for good T2Rs

rm = pyvisa.ResourceManager()
yoko = rm.open_resource('GPIB1::9::INSTR')
# yoko.write("*RST")
yoko.write(":SOUR:FUNC VOLT")
yoko.write(":OUTP ON")
ramp_to(yoko, start_voltage)

yoko_fixed = False # during a charge sweep; lazy way of sweeping two tone spec over time

# Readout

Qubit_Readout = 6
Qubit_Pulse = 6
outerFolder = Qubit_Parameters[str(Qubit_Readout)]['outerfoldername']

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
# relax_delay must be set to >= 3-5 * T1 so the qubit thermalises between shots
# (hardware active reset not available in AveragerProgram; thermal reset is sufficient).
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

    # --- Modified Ramsey settings ---
    # tau is computed automatically as 1 / (2 * peak_sep_MHz)
    # f_ge is set automatically to the higher-frequency peak
    # No relax delay: the measurement collapses the qubit and acts as reset.
    "mr_reps": 40000,             # number of single-shot Ramsey measurements per cycle
    "average_n_shots": 400,
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

cavity_gain = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Gain']
resonator_frequency_center = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Frequency']
qubit_gain = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Gain']
pi2_gain = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['pi2_Gain']
qubit_frequency_center = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency']

qubit_sigma = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['sigma']
qubit_flattop = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['flattop_length']

trans_config = {
    "reps": 1000,  # this will used for all experiements below unless otherwise changed in between trials
    "pulse_style": "const",  # --Fixed
    "readout_length": 15,  # 15 [us]
    "pulse_gain": cavity_gain,  # [DAC units]
    "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
    "TransSpan": Transmission_params['span'],  ### 0.75 MHz, span will be center+/- this parameter
    "TransNumPoints": Transmission_params['num_points'],  ### number of points in the transmission frequecny
    "cav_relax_delay": 30
}
qubit_config = {
    "qubit_pulse_style": "const",
    "qubit_gain": Spec_relevant_params["qubit_gain"],
    "qubit_freq": qubit_frequency_center,
    "qubit_length": Spec_relevant_params["qubit_length"], # 20, 100 # 10 was the best for Q4
    "SpecSpan": Spec_relevant_params["SpecSpan"],  ### MHz, span will be center+/- this parameter
    "SpecNumPoints": Spec_relevant_params["SpecNumPoints"],  ### number of points in the transmission frequecny
    "current_voltage" : start_voltage
}
expt_cfg = {
    "step": 2 * qubit_config["SpecSpan"] / qubit_config["SpecNumPoints"],
    "start": qubit_config["qubit_freq"] - qubit_config["SpecSpan"],
    "expts": qubit_config["SpecNumPoints"]
}

UpdateConfig = trans_config | qubit_config | expt_cfg | tl | ts | charge_params
config = BaseConfig | UpdateConfig  ### note that UpdateConfig will overwrite elements in BaseConfig
print(config)
config["FF_Qubits"] = FF_Qubits

#### update the qubit and cavity attenuation
# cavityAtten.SetAttenuation(config["cav_Atten"], printOut=True)

if Constant2Tone:
    for i in range(1000000):
        Instance_trans = ConstantTwoTone(
            path="ConstantTwoTone",
            cfg=config,
            soc=soc,
            soccfg=soccfg,
            outerFolder=outerFolder
        )
        data_trans = Instance_trans.acquire()

if ConstantTone:
    Instance_trans = SingleTone(path="TransmissionFF", cfg=config, soc=soc, soccfg=soccfg,
                                  outerFolder=outerFolder)
    data_trans = SingleTone.acquire(Instance_trans)

cavity_min = True
config["cavity_min"] = cavity_min  # look for dip, not peak

if RunTransmissionSweep:


    # -------------------- acquire transmission --------------------
    config["reps"] = Transmission_params['reps']
    config["rounds"] = Transmission_params['rounds']

    Instance_trans = CavitySpecFF(
        path="TransmissionFF",
        cfg=config,
        soc=soc,
        soccfg=soccfg,
        outerFolder=outerFolder
    )
    data_trans = CavitySpecFF.acquire(Instance_trans)
    CavitySpecFF.display(Instance_trans, data_trans, plotDisp=True, figNum=1)
    CavitySpecFF.save_data(Instance_trans, data_trans)
    CavitySpecFF.save_config(Instance_trans)

    sig = (
        data_trans['data']['results'][0][0][0]
        + 1j * data_trans['data']['results'][0][0][1]
    )
    x_pts = np.asarray(data_trans['data']['fpts'])

    y_mag = np.abs(sig)
    y_db = 20 * np.log10(y_mag)

    idx_min = np.argmin(y_db)
    center_guess = x_pts[idx_min]

    startpoint = [
        center_guess,   # f0
        4.1e4,          # Qtot
        4.3e4,          # Qext
        1e3,            # asym
        0.0             # offset
    ]

    fit_result = fit_hanger_transmission(
        freq=x_pts,
        amp_db=y_db,
        startpoint=startpoint
    )

    popt = fit_result["popt"]
    perr = fit_result["perr"]

    f0_fit, Qtot_fit, Qext_fit, asym_fit, offset_fit = popt
    df0_fit, dQtot_fit, dQext_fit, dasym_fit, doffset_fit = perr
    Qint_fit = fit_result["Qint"]

    # update config with fitted center frequency
    config["pulse_freq"] = f0_fit

    freq_deviation = f0_fit - resonator_frequency_center
    kappa_mhz = (f0_fit / Qext_fit) / 1e6

    print("Hanger resonator fit:")
    print(f"  f0       = {f0_fit:.6f} ± {df0_fit:.6f}")
    print(f"  Qtot     = {Qtot_fit:.6e} ± {dQtot_fit:.6e}")
    print(f"  Qext     = {Qext_fit:.6e} ± {dQext_fit:.6e}")
    print(f"  Qint     = {Qint_fit:.6e}")
    print(f"  kappa    = {kappa_mhz:.6f} MHz")
    print(f"  asym     = {asym_fit:.6e} ± {dasym_fit:.6e}")
    print(f"  offset   = {offset_fit:.6e} ± {doffset_fit:.6e}")
    print(
        f"  deviation from resonator_frequency_center "
        f"({resonator_frequency_center:.6f}) = {freq_deviation:+.6f}"
    )
    print(f"Cavity frequency found at: {config['pulse_freq']:.6f}")

    # -------------------- plot fit over data --------------------
    x_fit = np.linspace(np.min(x_pts), np.max(x_pts), 2000)
    y_fit = fit_result["model"](x_fit, *popt)

    fit_min_idx = np.argmin(y_fit)
    fit_min_freq = x_fit[fit_min_idx]
    fit_min_val = y_fit[fit_min_idx]

    fig_num_fit = 100
    while plt.fignum_exists(fig_num_fit):
        fig_num_fit += 1

    min_freq = x_pts[idx_min]

    plt.figure(fig_num_fit)
    plt.plot(x_pts, y_db, 'o', label='|sig| data (dB)')
    plt.plot(
        x_fit, y_fit, '-', linewidth=2,
        label=f'Hanger fit\nf0={f0_fit:.6f} ± {df0_fit:.6f}'
    )
    plt.axvline(
        resonator_frequency_center, linestyle='--', color='gray',
        label=f'input center = {resonator_frequency_center:.6f}'
    )
    plt.axvline(
        fit_min_freq, linestyle=':', color='red',
        label=f'fit minimum = {fit_min_freq:.6f}'
    )
    plt.axvline(
        min_freq, linestyle=':', color='blue',
        label=f'min freq = {min_freq:.6f}'
    )
    plt.xlabel("Frequency")
    plt.ylabel("Transmission (dB)")
    plt.title("Transmission sweep with hanger fit")
    plt.legend()
    plt.tight_layout()
    plt.show()


# perform the cavity transmission experiment
if RunTransmissionSweeps:
    config["reps"] = 20  # fast axis number of points
    config["rounds"] = 20  # slow axis number of points
    Instance_trans = CavitySpecFF(path="TransmissionFF", cfg=config, soc=soc, soccfg=soccfg,
                                  outerFolder=outerFolder)
    data_trans = CavitySpecFF.acquire(Instance_trans)
    CavitySpecFF.display(Instance_trans, data_trans, plotDisp=True, figNum=1)
    CavitySpecFF.save_data(Instance_trans, data_trans)
    CavitySpecFF.save_config(Instance_trans)

    # update the transmission frequency to be the peak
    if cavity_min:
        config["pulse_freq"] = Instance_trans.peakFreq_min
    else:
        config["pulse_freq"] = Instance_trans.peakFreq_max
    print("Cavity frequency found at: ", config["pulse_freq"])

# qubit spec experiment
if Run2ToneSpec:
    config["reps"] = Spec_relevant_params['reps']
    config["rounds"] = Spec_relevant_params['rounds']
    config["Gauss"] = Spec_relevant_params['Gauss']
    if Spec_relevant_params['Gauss']:
        config['sigma'] = Spec_relevant_params["sigma"]
        config["qubit_gain"] = Spec_relevant_params['gain']
        
    config["qubit_gain"] = Spec_relevant_params['gain']

    config["qubit_length"] = Spec_relevant_params["qubit_length"]
    config["SpecSpan"] = Spec_relevant_params["SpecSpan"]
    config["SpecNumPoints"] = Spec_relevant_params["SpecNumPoints"]
    config["step"] = 2 * config["SpecSpan"] / config["SpecNumPoints"]
    config["start"] = qubit_frequency_center - config["SpecSpan"]
    config["expts"] = config["SpecNumPoints"]
    config['relax_delay'] = Spec_relevant_params['relax_delay']
    display = Spec_relevant_params['display']
    min_sep = Spec_relevant_params['min_sep_MHz']

    Instance_specSlice = QubitSpecSliceFF(
        path="QubitSpecFF",
        cfg=config,
        soc=soc,
        soccfg=soccfg,
        outerFolder=outerFolder
    )
    data_specSlice = QubitSpecSliceFF.acquire(Instance_specSlice)
    QubitSpecSliceFF.display(Instance_specSlice, data_specSlice, plotDisp=display, figNum=2, min_sep=min_sep,
                             fit_window_mhz = 0.5, prominent_ratio = 0.1) # can change to True
    QubitSpecSliceFF.save_data(Instance_specSlice, data_specSlice)
    QubitSpecSliceFF.save_config(Instance_specSlice)

# Nested gain × qubit_length sweep.
# For each length in sweep_lengths, runs a full qubit spec at every gain in sweep_gains.
# qubit_gain and qubit_length appear in every saved plot title for easy identification.
if RunSpecGainLengthSweep:
    sweep_lengths = Spec_relevant_params['sweep_lengths']
    sweep_gains   = Spec_relevant_params['sweep_gains']

    _disp  = Spec_relevant_params['display']
    _minsep = Spec_relevant_params['min_sep_MHz']
    _fw    = Spec_relevant_params.get('fit_window_mhz', 0.5)
    _pr    = Spec_relevant_params.get('prominent_ratio', 0.1)

    for q_length in sweep_lengths:
        for q_gain in sweep_gains:
            print(f"\n=== GainLengthSweep: qubit_length={q_length} µs  qubit_gain={q_gain} ===")

            config["reps"]          = Spec_relevant_params['reps']
            config["rounds"]        = Spec_relevant_params['rounds']
            config["Gauss"]         = Spec_relevant_params['Gauss']
            config["qubit_gain"]    = q_gain
            config["qubit_length"]  = q_length
            config["SpecSpan"]      = Spec_relevant_params["SpecSpan"]
            config["SpecNumPoints"] = Spec_relevant_params["SpecNumPoints"]
            config["step"]          = 2 * config["SpecSpan"] / config["SpecNumPoints"]
            config["start"]         = qubit_frequency_center - config["SpecSpan"]
            config["expts"]         = config["SpecNumPoints"]
            config["relax_delay"]   = Spec_relevant_params['relax_delay']
            if Spec_relevant_params['Gauss']:
                config['sigma'] = Spec_relevant_params["sigma"]

            _inst = QubitSpecSliceFF(
                path="QubitSpecFF",
                cfg=config,
                soc=soc,
                soccfg=soccfg,
                outerFolder=outerFolder,
            )
            _data = QubitSpecSliceFF.acquire(_inst)
            QubitSpecSliceFF.display(_inst, _data, plotDisp=_disp, figNum=2,
                                     min_sep=_minsep, fit_window_mhz=_fw,
                                     prominent_ratio=_pr)
            QubitSpecSliceFF.save_data(_inst, _data)
            QubitSpecSliceFF.save_config(_inst)

if RunChiShift:
    updated_params = {
        "pi_gain": qubit_gain,
        "sigma": qubit_sigma, "f_ge": Amplitude_Rabi_params["qubit_freq"],
        "flattop_length": qubit_flattop
    }
    config = config | ChiShift_params | updated_params
    iChi = ChiShift(path="ChiShift", cfg=config, soc=soc, soccfg=soccfg,
                    outerFolder=outerFolder)
    dChi = ChiShift.acquire(iChi)
    ChiShift.display(iChi, dChi, plotDisp=True, figNum=1)
    ChiShift.save_data(iChi, dChi)
    ChiShift.save_config(iChi)

if Run2ToneChargeDispersionQuasiCW:
    save_dir = os.path.join(outerFolder, "TwoToneChargeDispersion")
    os.makedirs(save_dir, exist_ok=True)

    df_required = TwoToneChargeDispersion_params["df"]
    dV = TwoToneChargeDispersion_params["dV"]
    voltage_min = max(0.0, TwoToneChargeDispersion_params["voltage_min"])
    voltage_max = TwoToneChargeDispersion_params["voltage_max"]
    max_tries = TwoToneChargeDispersion_params["max_voltage_tries"]
    num_cycles = TwoToneChargeDispersion_params["num_cycles"]

    # start each overall experiment from the yoko's current value
    current_voltage = float(yoko.query(":SOUR:LEV?"))
    direction = +1

    cycle_summary = []

    for cycle_idx in range(num_cycles):
        print(f"\n================ Cycle {cycle_idx + 1}/{num_cycles} ================")

        success = False
        chosen_probe_freq = None
        chosen_peak_sep = None

        # ---------- search loop for this cycle ----------
        for attempt_idx in range(max_tries):
            print(
                f"[TwoToneChargeDispersion] Cycle {cycle_idx + 1}/{num_cycles}, "
                f"attempt {attempt_idx + 1}/{max_tries}, V={current_voltage:.6f} V"
            )

            # --- run two-tone spec at current voltage ---
            config["current_voltage"] = current_voltage
            config["reps"] = TwoToneChargeDispersion_params["reps"]
            config["rounds"] = TwoToneChargeDispersion_params["rounds"]
            config["Gauss"] = TwoToneChargeDispersion_params["Gauss"]
            config["relax_delay"] = TwoToneChargeDispersion_params["relax_delay"]

            if config["Gauss"]:
                config["sigma"] = TwoToneChargeDispersion_params["sigma"]
                config["qubit_gain"] = TwoToneChargeDispersion_params["gain"]

            config["qubit_length"] = TwoToneChargeDispersion_params["qubit_length"]
            config["SpecSpan"] = TwoToneChargeDispersion_params["SpecSpan"]
            config["SpecNumPoints"] = TwoToneChargeDispersion_params["SpecNumPoints"]
            config["step"] = 2 * config["SpecSpan"] / config["SpecNumPoints"]
            config["start"] = qubit_frequency_center - config["SpecSpan"]
            config["expts"] = config["SpecNumPoints"]

            Instance_specSlice = QubitSpecSliceFF(
                path="TwoToneChargeDispersion",
                cfg=config,
                soc=soc,
                soccfg=soccfg,
                outerFolder=outerFolder
            )
            data_specSlice = QubitSpecSliceFF.acquire(Instance_specSlice)
            QubitSpecSliceFF.display(
                Instance_specSlice,
                data_specSlice,
                plotDisp=False,
                figNum=2,
                min_sep=Spec_relevant_params["min_sep_MHz"],
                fit_window_mhz=Spec_relevant_params["fit_window_mhz"],
                prominent_ratio=Spec_relevant_params["prominent_ratio"],
            )
            QubitSpecSliceFF.save_data(Instance_specSlice, data_specSlice)
            QubitSpecSliceFF.save_config(Instance_specSlice)

            x_pts = np.array(data_specSlice["data"]["x_pts"])
            avgi = np.array(data_specSlice["data"]["avgi"][0][0])
            avgq = np.array(data_specSlice["data"]["avgq"][0][0])
            # Rotate onto the signal-bearing IQ axis (background-subtracted) instead
            # of the raw magnitude |I+iQ|^2, which is dominated by the large, noisy
            # background quadrature and buries the qubit feature.
            avgamp0 = project_iq_signal(avgi, avgq)

            freq_choice = choose_two_tone_freqs_from_lorentz_or_peaks(
                data_specSlice,
                min_sep_mhz=Spec_relevant_params["min_sep_MHz"],
            )

            peak_info = freq_choice["peak_info_raw"]
            peak_info["peak_freqs"] = freq_choice["freqs"]
            peak_info["peak_sep"] = freq_choice["peak_sep"]
            peak_info["source"] = freq_choice["source"]

            save_base = save_two_tone_plot(
                x_pts=x_pts,
                avgi=avgi,
                avgq=avgq,
                avgamp0=avgamp0,
                peak_info=peak_info,
                attempt_idx=attempt_idx + cycle_idx * max_tries,
                save_dir=save_dir,
                current_voltage=current_voltage
            )

            with open(save_base + "_summary.txt", "w") as f:
                f.write(f"cycle_idx: {cycle_idx}\n")
                f.write(f"attempt_idx: {attempt_idx}\n")
                f.write(f"current_voltage: {current_voltage:.9f}\n")
                f.write(f"peak_freqs: {peak_info['peak_freqs']}\n")
                f.write(f"peak_vals: {peak_info['peak_vals']}\n")
                f.write(f"peak_sep: {peak_info['peak_sep']}\n")
                f.write(f"df_required: {df_required}\n")

            center_peak_tol_mhz = TwoToneChargeDispersion_params.get("center_peak_tol_mhz", 0.05)

            peak_freqs = np.asarray(peak_info.get("peak_freqs", []), dtype=float)

            highest_peak_freq = None
            highest_peak_is_centered = False

            if len(peak_freqs) > 0:
                # Use the largest response in avgamp0 as the "highest peak".
                peak_indices = [int(np.argmin(np.abs(x_pts - f))) for f in peak_freqs]
                peak_heights = np.asarray([avgamp0[idx] for idx in peak_indices])
                highest_peak_freq = float(peak_freqs[int(np.argmax(peak_heights))])

                highest_peak_is_centered = (
                        abs(highest_peak_freq - qubit_frequency_center) <= center_peak_tol_mhz
                )

            if highest_peak_is_centered:
                # Calibration/centered mode: run quasi-CW on the centered strongest peak.
                chosen_probe_freq = highest_peak_freq
                chosen_peak_sep = float(peak_info["peak_sep"]) if peak_info["peak_sep"] is not None else 0.0

                print(
                    f"[TwoToneChargeDispersion] Cycle {cycle_idx + 1}: centered highest peak found, "
                    f"highest_peak={highest_peak_freq:.6f} MHz, "
                    f"center={qubit_frequency_center:.6f} MHz, "
                    f"|diff|={abs(highest_peak_freq - qubit_frequency_center):.6f} MHz <= "
                    f"{center_peak_tol_mhz:.6f} MHz. Running quasi-CW with "
                    f"probe_freq={chosen_probe_freq:.6f} MHz"
                )

                success = True
                break

            elif peak_info["peak_sep"] is not None and peak_info["peak_sep"] >= df_required:
                # Normal mode: require two sufficiently separated peaks.
                if TwoToneChargeDispersion_params["use_upper_peak"]:
                    chosen_probe_freq = float(np.max(peak_info["peak_freqs"]))
                else:
                    chosen_probe_freq = float(np.min(peak_info["peak_freqs"]))

                chosen_peak_sep = float(peak_info["peak_sep"])

                print(
                    f"[TwoToneChargeDispersion] Cycle {cycle_idx + 1}: separated peaks found, "
                    f"peak separation = {chosen_peak_sep:.6f} MHz, "
                    f"probe_freq = {chosen_probe_freq:.6f} MHz"
                )

                success = True
                break

            # --- not separated enough: move voltage ---
            next_voltage, direction = choose_next_voltage(
                current_v=current_voltage,
                dv=dV,
                vmin=voltage_min,
                vmax=voltage_max,
                direction=direction
            )

            if abs(next_voltage - current_voltage) < 1e-15:
                print("[TwoToneChargeDispersion] Voltage step stalled at bounds.")
                break

            ramp_to(yoko, next_voltage)
            current_voltage = next_voltage

        # ---------- if search failed, record and continue to next cycle ----------
        if not success:
            print(f"[TwoToneChargeDispersion] Cycle {cycle_idx + 1}: failed to find sufficient peak separation.")
            cycle_summary.append({
                "cycle_idx": cycle_idx,
                "success": False,
                "final_voltage": current_voltage,
                "chosen_probe_freq": None,
                "peak_sep": None,
            })
            continue

        # ---------- run quasi-CW for this cycle ----------
        ChargeDispersion_params["probe_freq"] = chosen_probe_freq

        config["current_voltage"] = current_voltage
        config["reps"] = TwoToneChargeDispersion_params["qcw_repetitions"]
        config["rounds"] = 1
        config["Gauss"] = Spec_relevant_params["Gauss"]
        config["relax_delay"] = TwoToneChargeDispersion_params["qcw_relax_delay"]

        if config["Gauss"]:
            config["sigma"] = Spec_relevant_params["sigma"]
            config["qubit_gain"] = Spec_relevant_params["gain"]

        config["SpecNumPoints"] = 1
        config["SpecSpan"] = 0
        config["step"] = 0
        config["start"] = ChargeDispersion_params["probe_freq"]
        config["expts"] = 1

        Instance_qcw = ChargeDispersionQuasiCW(
            path="TwoToneChargeDispersion",
            cfg=config,
            soc=soc,
            soccfg=soccfg,
            outerFolder=outerFolder,
        )

        data_qcw = Instance_qcw.acquire(load_pulses=True, print_time=True)

        raw_i = np.ravel(np.array(data_qcw["data"]["raw_i"]))
        raw_q = np.ravel(np.array(data_qcw["data"]["raw_q"]))
        iq = np.column_stack([raw_i, raw_q])

        kmeans = KMeans(n_clusters=2, random_state=0, n_init=20)
        labels = kmeans.fit_predict(iq)
        centers = kmeans.cluster_centers_

        c0 = centers[0]
        c1 = centers[1]
        normal = c1 - c0
        midpoint = 0.5 * (c0 + c1)
        scores = (iq - midpoint) @ normal
        binary_states = (scores > 0).astype(int)

        n0 = np.sum(binary_states == 0)
        n1 = np.sum(binary_states == 1)
        if n1 > n0:
            binary_states = 1 - binary_states
            c0, c1 = c1, c0
            normal = c1 - c0
            midpoint = 0.5 * (c0 + c1)
            scores = (iq - midpoint) @ normal

        rep_period_us = 1.0 + 0.5 + config["readout_length"] + 10 + config["relax_delay"]
        elapsed_s = np.arange(len(raw_i)) * rep_period_us * 1e-6

        timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        base = os.path.join(save_dir, f"Cycle_{cycle_idx:03d}_QuasiCW_{timestamp}")

        I_min, I_max = raw_i.min(), raw_i.max()
        Q_min, Q_max = raw_q.min(), raw_q.max()
        I_pad = 0.05 * (I_max - I_min if I_max > I_min else 1.0)
        Q_pad = 0.05 * (Q_max - Q_min if Q_max > Q_min else 1.0)
        I_line = np.linspace(I_min - I_pad, I_max + I_pad, 400)

        vertical_line = np.abs(normal[1]) < 1e-12
        if not vertical_line:
            Q_line = midpoint[1] - (normal[0] / normal[1]) * (I_line - midpoint[0])

        plt.figure(figsize=(6, 6))
        plt.plot(raw_i, raw_q, ".", alpha=0.35, label="IQ data")
        plt.plot(c0[0], c0[1], "o", markersize=10, label="Blob center 0")
        plt.plot(c1[0], c1[1], "o", markersize=10, label="Blob center 1")
        if vertical_line:
            plt.axvline(midpoint[0], linestyle="--", linewidth=2, label="Separator")
        else:
            plt.plot(I_line, Q_line, "--", linewidth=2, label="Separator")
        plt.xlabel("I")
        plt.ylabel("Q")
        plt.title(
            f"Cycle {cycle_idx + 1}: QuasiCW IQ, V={current_voltage:.6f} V, "
            f"probe={chosen_probe_freq:.6f} MHz"
        )
        plt.xlim(I_min - I_pad, I_max + I_pad)
        plt.ylim(Q_min - Q_pad, Q_max + Q_pad)
        plt.gca().set_aspect("equal", adjustable="box")
        plt.legend()
        plt.tight_layout()
        plt.savefig(base + "_iq_separator.png", dpi=300, bbox_inches="tight")
        plt.close()

        plt.figure(figsize=(6, 6))
        plt.plot(raw_i[binary_states == 0], raw_q[binary_states == 0], ".", alpha=0.5, label="State 0")
        plt.plot(raw_i[binary_states == 1], raw_q[binary_states == 1], ".", alpha=0.5, label="State 1")
        if vertical_line:
            plt.axvline(midpoint[0], linestyle="--", linewidth=2, label="Separator")
        else:
            plt.plot(I_line, Q_line, "--", linewidth=2, label="Separator")
        plt.xlabel("I")
        plt.ylabel("Q")
        plt.title(f"Cycle {cycle_idx + 1}: QuasiCW IQ labeled")
        plt.xlim(I_min - I_pad, I_max + I_pad)
        plt.ylim(Q_min - Q_pad, Q_max + Q_pad)
        plt.gca().set_aspect("equal", adjustable="box")
        plt.legend()
        plt.tight_layout()
        plt.savefig(base + "_iq_labeled.png", dpi=300, bbox_inches="tight")
        plt.close()

        amps = np.abs(raw_i + 1j * raw_q) ** 2
        plt.figure(figsize=(10, 4))
        plt.plot(elapsed_s, amps, "-", linewidth=1)
        plt.xlabel("Time since start (s)")
        plt.ylabel("Amplitude$^2$")
        plt.title(f"Cycle {cycle_idx + 1}: Amplitude over time")
        plt.tight_layout()
        plt.savefig(base + "_amplitude_vs_time.png", dpi=300, bbox_inches="tight")
        plt.close()


        plt.figure(figsize=(10, 4))
        plt.step(elapsed_s, binary_states, where="post", linewidth=1.5)
        plt.plot(elapsed_s, binary_states, "o", markersize=2)
        plt.xlabel("Time since start (s)")
        plt.ylabel("Assigned state")
        plt.yticks([0, 1])
        plt.ylim(-0.1, 1.1)
        plt.title(f"Cycle {cycle_idx + 1}: QuasiCW binary trace")
        plt.tight_layout()
        plt.savefig(base + "_binary.png", dpi=300, bbox_inches="tight")
        plt.close()

        np.savez(
            base + ".npz",
            elapsed_s=np.array(elapsed_s),
            raw_i=np.array(raw_i),
            raw_q=np.array(raw_q),
            scores=np.array(scores),
            binary_states=np.array(binary_states),
            centers=np.array([c0, c1]),
            midpoint=np.array(midpoint),
            normal=np.array(normal),
            chosen_probe_freq=np.array(chosen_probe_freq),
            final_voltage=np.array(current_voltage),
            peak_sep=np.array(chosen_peak_sep),
            cycle_idx=np.array(cycle_idx),
            config=np.array(config, dtype=object),
        )

        with open(base + "_config.json", "w") as f:
            json.dump(config, f, indent=2, default=float)

        cycle_summary.append({
            "cycle_idx": cycle_idx,
            "success": True,
            "final_voltage": current_voltage,
            "chosen_probe_freq": chosen_probe_freq,
            "peak_sep": chosen_peak_sep,
        })

        # after finishing this cycle, restart the search from the current voltage
        # direction is preserved so the voltage walk continues naturally

    # ---------- save summary for all cycles ----------
    summary_path = os.path.join(
        save_dir,
        f"CycleSummary_{datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}.json"
    )
    with open(summary_path, "w") as f:
        json.dump(cycle_summary, f, indent=2, default=float)

if RunModifiedRamsey:
    date_tag_mr = datetime.now().strftime("%Y_%m_%d")
    save_dir_mr = os.path.join(outerFolder, "ModifiedRamsey", date_tag_mr)
    os.makedirs(save_dir_mr, exist_ok=True)

    df_required_mr = ModifiedRamsey_params["df"]
    dV_mr = ModifiedRamsey_params["dV"]
    voltage_min_mr = max(0.0, ModifiedRamsey_params["voltage_min"])
    voltage_max_mr = ModifiedRamsey_params["voltage_max"]
    max_tries_mr = ModifiedRamsey_params["max_voltage_tries"]
    num_cycles_mr = ModifiedRamsey_params["num_cycles"]

    ModifiedRamsey_params.setdefault("hysteresis_low", 0.2)
    ModifiedRamsey_params.setdefault("hysteresis_high", 0.8)
    ModifiedRamsey_params.setdefault("window_ms", 0.05)

    current_voltage_mr = float(yoko.query(":SOUR:LEV?"))
    direction_mr = +1

    cycle_summary_mr = []

    apriori_sep_mr = None

    if ModifiedRamsey_params.get("use_apriori_separator", False):
        apriori_sep_mr = get_apriori_separator_from_singleshot(
            config=config,
            soc=soc,
            soccfg=soccfg,
            outerFolder=outerFolder
        )
    ss_recalib_n_mr = ModifiedRamsey_params.get("ss_recalib_every_n_cycles", None)
    for cycle_idx_mr in range(num_cycles_mr):

        if ModifiedRamsey_params.get("use_apriori_separator", False):
            if apriori_sep_mr is None or (
                    ss_recalib_n_mr is not None
                    and ss_recalib_n_mr > 0
                    and cycle_idx_mr % ss_recalib_n_mr == 0
            ):
                apriori_sep_mr = get_apriori_separator_from_singleshot(
                    config=config,
                    soc=soc,
                    soccfg=soccfg,
                    outerFolder=outerFolder
                )
        print(f"\n================ ModifiedRamsey Cycle {cycle_idx_mr + 1}/{num_cycles_mr} ================")

        success_mr = False
        chosen_probe_freq_mr = None
        chosen_peak_sep_mr = None

        # ---------- two-tone voltage search ----------
        for attempt_idx_mr in range(max_tries_mr):
            print(
                f"[ModifiedRamsey] Cycle {cycle_idx_mr + 1}/{num_cycles_mr}, "
                f"attempt {attempt_idx_mr + 1}/{max_tries_mr}, V={current_voltage_mr:.6f} V"
            )

            config["current_voltage"] = current_voltage_mr
            config["reps"] = ModifiedRamsey_params["reps"]
            config["rounds"] = ModifiedRamsey_params["rounds"]
            config["Gauss"] = ModifiedRamsey_params["Gauss"]
            config["relax_delay"] = ModifiedRamsey_params["relax_delay"]

            if config["Gauss"]:
                config["sigma"] = ModifiedRamsey_params["sigma"]
                config["qubit_gain"] = ModifiedRamsey_params["gain"]

            config["qubit_length"] = ModifiedRamsey_params["qubit_length"]
            config["SpecSpan"] = ModifiedRamsey_params["SpecSpan"]
            config["SpecNumPoints"] = ModifiedRamsey_params["SpecNumPoints"]
            config["step"] = 2 * config["SpecSpan"] / config["SpecNumPoints"]
            config["start"] = qubit_frequency_center - config["SpecSpan"]
            config["expts"] = config["SpecNumPoints"]

            Instance_specSlice_mr = QubitSpecSliceFF(
                path="ModifiedRamsey",
                cfg=config,
                soc=soc,
                soccfg=soccfg,
                outerFolder=outerFolder
            )
            data_specSlice_mr = QubitSpecSliceFF.acquire(Instance_specSlice_mr)
            QubitSpecSliceFF.display(
                Instance_specSlice_mr,
                data_specSlice_mr,
                plotDisp=False,
                figNum=2,
                min_sep=Spec_relevant_params["min_sep_MHz"],
                fit_window_mhz=Spec_relevant_params["fit_window_mhz"],
                prominent_ratio=Spec_relevant_params["prominent_ratio"],
            )
            QubitSpecSliceFF.save_data(Instance_specSlice_mr, data_specSlice_mr)
            QubitSpecSliceFF.save_config(Instance_specSlice_mr)

            x_pts_mr = np.array(data_specSlice_mr["data"]["x_pts"])
            avgi_mr = np.array(data_specSlice_mr["data"]["avgi"][0][0])
            avgq_mr = np.array(data_specSlice_mr["data"]["avgq"][0][0])
            # Rotate onto the signal-bearing IQ axis (background-subtracted) instead
            # of the raw magnitude |I+iQ|^2, which is dominated by the large, noisy
            # background quadrature and buries the qubit feature.
            avgamp0_mr = project_iq_signal(avgi_mr, avgq_mr)

            freq_choice_mr = choose_two_tone_freqs_from_lorentz_or_peaks(
                data_specSlice_mr,
                min_sep_mhz=Spec_relevant_params["min_sep_MHz"],
            )

            peak_info_mr = freq_choice_mr["peak_info_raw"]
            peak_info_mr["peak_freqs"] = freq_choice_mr["freqs"]
            peak_info_mr["peak_sep"] = freq_choice_mr["peak_sep"]
            peak_info_mr["source"] = freq_choice_mr["source"]

            save_base_mr = save_two_tone_plot(
                x_pts=x_pts_mr,
                avgi=avgi_mr,
                avgq=avgq_mr,
                avgamp0=avgamp0_mr,
                peak_info=peak_info_mr,
                current_voltage=current_voltage_mr,
                attempt_idx=attempt_idx_mr + cycle_idx_mr * max_tries_mr,
                save_dir=save_dir_mr
            )

            with open(save_base_mr + "_summary.txt", "w") as f:
                f.write(f"cycle_idx: {cycle_idx_mr}\n")
                f.write(f"attempt_idx: {attempt_idx_mr}\n")
                f.write(f"current_voltage: {current_voltage_mr:.9f}\n")
                f.write(f"peak_freqs: {peak_info_mr['peak_freqs']}\n")
                f.write(f"peak_sep: {peak_info_mr['peak_sep']}\n")
                f.write(f"df_required: {df_required_mr}\n")

            center_peak_tol_mhz = ModifiedRamsey_params.get("center_peak_tol_mhz", 0.05)
            center_peak_df_for_tau = ModifiedRamsey_params.get("center_peak_df_for_tau", df_required_mr)

            peak_freqs_mr = np.asarray(peak_info_mr.get("peak_freqs", []), dtype=float)

            highest_peak_freq_mr = None
            highest_peak_is_centered_mr = False

            if len(peak_freqs_mr) > 0:
                # Use the largest response in avgamp0 as the "highest peak".
                peak_indices_mr = [int(np.argmin(np.abs(x_pts_mr - f))) for f in peak_freqs_mr]
                peak_heights_mr = np.asarray([avgamp0_mr[idx] for idx in peak_indices_mr])
                highest_peak_freq_mr = float(peak_freqs_mr[int(np.argmax(peak_heights_mr))])

                highest_peak_is_centered_mr = (
                        abs(highest_peak_freq_mr - qubit_frequency_center) <= center_peak_tol_mhz
                )

            if highest_peak_is_centered_mr:
                # Calibration mode: run MR even if there is not enough peak splitting.
                chosen_probe_freq_mr = highest_peak_freq_mr
                chosen_peak_sep_mr = float(center_peak_df_for_tau)

                print(
                    f"[ModifiedRamsey] Cycle {cycle_idx_mr + 1}: centered highest peak found, "
                    f"highest_peak={highest_peak_freq_mr:.6f} MHz, "
                    f"center={qubit_frequency_center:.6f} MHz, "
                    f"|diff|={abs(highest_peak_freq_mr - qubit_frequency_center):.6f} MHz <= "
                    f"{center_peak_tol_mhz:.6f} MHz. Running calibration Ramsey with "
                    f"f_ge={chosen_probe_freq_mr:.6f} MHz, "
                    f"df_for_tau={chosen_peak_sep_mr:.6f} MHz, "
                    f"tau={1.0 / (2.0 * chosen_peak_sep_mr):.4f} us"
                )

                success_mr = True
                break

            elif (peak_info_mr["peak_sep"] is not None
                  and peak_info_mr["peak_sep"] >= df_required_mr):
                # Normal parity mode: require two sufficiently separated peaks.
                chosen_probe_freq_mr = float(np.max(peak_info_mr["peak_freqs"]))
                chosen_peak_sep_mr = float(peak_info_mr["peak_sep"])

                print(
                    f"[ModifiedRamsey] Cycle {cycle_idx_mr + 1}: separated peaks found, "
                    f"sep={chosen_peak_sep_mr:.6f} MHz, f_ge={chosen_probe_freq_mr:.6f} MHz, "
                    f"tau={1.0 / (2.0 * chosen_peak_sep_mr):.4f} us"
                )

                success_mr = True
                break

            next_voltage_mr, direction_mr = choose_next_voltage(
                current_v=current_voltage_mr,
                dv=dV_mr,
                vmin=voltage_min_mr,
                vmax=voltage_max_mr,
                direction=direction_mr
            )

            if abs(next_voltage_mr - current_voltage_mr) < 1e-15:
                print("[ModifiedRamsey] Voltage step stalled at bounds.")
                break

            ramp_to(yoko, next_voltage_mr)
            current_voltage_mr = next_voltage_mr

        if not success_mr:
            print(f"[ModifiedRamsey] Cycle {cycle_idx_mr + 1}: failed to find sufficient peak separation.")
            cycle_summary_mr.append({
                "cycle_idx": cycle_idx_mr,
                "success": False,
                "final_voltage": current_voltage_mr,
                "chosen_probe_freq": None,
                "peak_sep": None,
            })
            continue

        # ---------- run Modified Ramsey with auto-computed tau and f_ge ----------
        tau_us_mr = 1.0 / (2.0 * chosen_peak_sep_mr)

        mr_cfg = {
            "f_ge": chosen_probe_freq_mr,
            "df": chosen_peak_sep_mr,
            "pi2_gain": pi2_gain,
            "pi_gain": qubit_gain,
            "use_pi_pulse": ModifiedRamsey_params.get("use_pi_pulse", False),
            "sigma": qubit_sigma,
            "flattop_length": qubit_flattop,
            "reps": ModifiedRamsey_params["mr_reps"],
            "rounds": 1,
            "current_voltage": current_voltage_mr,
            "Qubit_number": Qubit_Readout,
        }
        config_mr = config | mr_cfg

        Instance_mr = ModifiedRamsey(
            path="ModifiedRamsey",
            cfg=config_mr,
            soc=soc,
            soccfg=soccfg,
            outerFolder=outerFolder
        )
        data_mr = ModifiedRamsey.acquire(Instance_mr)
        ModifiedRamsey.display(Instance_mr, data_mr, plotDisp=False, figNum=10)
        ModifiedRamsey.save_data(Instance_mr, data_mr)
        ModifiedRamsey.save_config(Instance_mr)

        # ---------- classify shots and build averaged 0-to-1 trace ----------
        raw_i_mr = np.ravel(np.array(data_mr["data"]["shots_i"]))
        raw_q_mr = np.ravel(np.array(data_mr["data"]["shots_q"]))

        if apriori_sep_mr is None:
            raise RuntimeError("ModifiedRamsey now requires apriori_sep_mr from SingleShot calibration.")

        average_n_shots_mr = ModifiedRamsey_params.get("average_n_shots", 25)

        classification_mr = classify_and_average_iq(
            raw_i=raw_i_mr,
            raw_q=raw_q_mr,
            g_center=apriori_sep_mr["g_center"],
            e_center=apriori_sep_mr["e_center"],
            average_n_shots=average_n_shots_mr,
        )

        binary_states_mr = classification_mr["binary_states"]
        excited_avg_mr = classification_mr["excited_avg"]
        scores_mr = classification_mr["scores"]
        normal_mr = classification_mr["normal"]
        midpoint_mr = classification_mr["midpoint"]

        c0_mr = apriori_sep_mr["g_center"]
        c1_mr = apriori_sep_mr["e_center"]

        pulse_length_us = qubit_sigma * 4
        n_qubit_pulses_mr = 3 if config_mr.get("use_pi_pulse", False) else 2
        rep_period_us = n_qubit_pulses_mr * pulse_length_us + tau_us_mr + 0.05 + config_mr["readout_length"]

        elapsed_ms_mr = np.arange(len(raw_i_mr)) * rep_period_us * 1e-3
        elapsed_avg_ms_mr = (
                np.arange(len(excited_avg_mr)) * average_n_shots_mr * rep_period_us * 1e-3
        )

        timestamp_mr = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        base_mr = os.path.join(save_dir_mr, f"Cycle_{cycle_idx_mr:03d}_MR_{timestamp_mr}")

        I_min_mr, I_max_mr = raw_i_mr.min(), raw_i_mr.max()
        Q_min_mr, Q_max_mr = raw_q_mr.min(), raw_q_mr.max()
        I_pad_mr = 0.05 * (I_max_mr - I_min_mr if I_max_mr > I_min_mr else 1.0)
        Q_pad_mr = 0.05 * (Q_max_mr - Q_min_mr if Q_max_mr > Q_min_mr else 1.0)
        I_line_mr = np.linspace(I_min_mr - I_pad_mr, I_max_mr + I_pad_mr, 400)

        vertical_line_mr = np.abs(normal_mr[1]) < 1e-12
        if not vertical_line_mr:
            Q_line_mr = midpoint_mr[1] - (normal_mr[0] / normal_mr[1]) * (I_line_mr - midpoint_mr[0])

        # IQ scatter with calibrated SingleShot separator
        plt.figure(figsize=(6, 6))
        plt.plot(raw_i_mr[binary_states_mr == 0], raw_q_mr[binary_states_mr == 0],
                 ".", alpha=0.5, label="Assigned 0")
        plt.plot(raw_i_mr[binary_states_mr == 1], raw_q_mr[binary_states_mr == 1],
                 ".", alpha=0.5, label="Assigned 1")
        plt.plot(c0_mr[0], c0_mr[1], "o", markersize=10, label="SingleShot g center")
        plt.plot(c1_mr[0], c1_mr[1], "o", markersize=10, label="SingleShot e center")

        if vertical_line_mr:
            plt.axvline(midpoint_mr[0], linestyle="--", linewidth=2, label="g/e separator")
        else:
            plt.plot(I_line_mr, Q_line_mr, "--", linewidth=2, label="g/e separator")

        plt.xlabel("I")
        plt.ylabel("Q")
        plt.xlim(I_min_mr - I_pad_mr, I_max_mr + I_pad_mr)
        plt.ylim(Q_min_mr - Q_pad_mr, Q_max_mr + Q_pad_mr)
        plt.gca().set_aspect("equal", adjustable="box")
        plt.title(
            f"Cycle {cycle_idx_mr + 1}: Modified Ramsey IQ\n"
            f"V={current_voltage_mr:.6f} V, f_ge={chosen_probe_freq_mr:.6f} MHz, "
            f"tau={tau_us_mr:.4f} us"
        )
        plt.legend()
        plt.tight_layout()
        plt.savefig(base_mr + "_iq_labeled_apriori.png", dpi=300, bbox_inches="tight")
        plt.close()

        # Raw 0/1 shot trace
        plt.figure(figsize=(10, 4))
        plt.step(elapsed_ms_mr, binary_states_mr, where="post", linewidth=1.2)
        plt.plot(elapsed_ms_mr, binary_states_mr, "o", markersize=2)
        plt.xlabel("Time since start (ms)")
        plt.ylabel("Single-shot state")
        plt.yticks([0, 1])
        plt.ylim(-0.1, 1.1)
        plt.title(
            f"Cycle {cycle_idx_mr + 1}: Modified Ramsey single-shot state\n"
            f"tau={tau_us_mr:.4f} us, df={chosen_peak_sep_mr:.4f} MHz"
        )
        plt.tight_layout()
        plt.savefig(base_mr + "_single_shot_binary.png", dpi=300, bbox_inches="tight")
        plt.close()

        # Averaged 0-to-1 population trace
        plt.figure(figsize=(10, 4))
        plt.plot(elapsed_avg_ms_mr, excited_avg_mr, "o-", linewidth=1.5)
        plt.xlabel("Time since start (ms)")
        plt.ylabel("Averaged excited-state population")
        plt.ylim(-0.05, 1.05)
        plt.title(
            f"Cycle {cycle_idx_mr + 1}: Modified Ramsey averaged state\n"
            f"{average_n_shots_mr} shots per point, tau={tau_us_mr:.4f} us"
        )
        plt.tight_layout()
        plt.savefig(base_mr + "_averaged_population.png", dpi=300, bbox_inches="tight")
        plt.close()

        np.savez(
            base_mr + ".npz",
            elapsed_ms=np.array(elapsed_ms_mr),
            elapsed_avg_ms=np.array(elapsed_avg_ms_mr),
            raw_i=np.array(raw_i_mr),
            raw_q=np.array(raw_q_mr),
            scores=np.array(scores_mr),
            binary_states=np.array(binary_states_mr),
            excited_avg=np.array(excited_avg_mr),
            average_n_shots=np.array(average_n_shots_mr),
            g_center=np.array(c0_mr),
            e_center=np.array(c1_mr),
            midpoint=np.array(midpoint_mr),
            normal=np.array(normal_mr),
            chosen_probe_freq=np.array(chosen_probe_freq_mr),
            peak_sep=np.array(chosen_peak_sep_mr),
            tau_us=np.array(tau_us_mr),
            final_voltage=np.array(current_voltage_mr),
            cycle_idx=np.array(cycle_idx_mr),
            config=np.array(config_mr, dtype=object),
        )

        with open(base_mr + "_config.json", "w") as f:
            json.dump(config_mr, f, indent=2, default=float)

        cycle_summary_mr.append({
            "cycle_idx": cycle_idx_mr,
            "success": True,
            "final_voltage": current_voltage_mr,
            "chosen_probe_freq": chosen_probe_freq_mr,
            "peak_sep": chosen_peak_sep_mr,
            "tau_us": tau_us_mr,
        })

    summary_path_mr = os.path.join(
        save_dir_mr,
        f"CycleSummary_{datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}.json"
    )
    with open(summary_path_mr, "w") as f:
        json.dump(cycle_summary_mr, f, indent=2, default=float)

if RunModifiedRamsey_Control:
    save_dir_mrc = os.path.join(outerFolder, "ModifiedRamsey_Control")
    os.makedirs(save_dir_mrc, exist_ok=True)

    sweet_max_df_mrc  = ModifiedRamsey_Control_params["sweet_spot_max_df_mhz"]
    cd_max_mhz_mrc    = ModifiedRamsey_Control_params["cd_max_mhz"]
    half_period_v_mrc = ModifiedRamsey_Control_params["cd_period_mv"] * 1e-3 / 2.0
    num_cycles_mrc    = ModifiedRamsey_Control_params["num_cycles"]

    ModifiedRamsey_Control_params.setdefault("hysteresis_low",  0.4)
    ModifiedRamsey_Control_params.setdefault("hysteresis_high", 0.6)
    ModifiedRamsey_Control_params.setdefault("window_ms",       0.1)

    current_voltage_mrc = float(yoko.query(":SOUR:LEV?"))
    cycle_summary_mrc = []

    # Parameters forwarded to find_sweet_spot on every cycle.
    # Spec settings and search bounds come directly from ModifiedRamsey_Control_params
    # so the user only has to edit one dict.
    sweet_params_mrc = {
        "spec_span":            ModifiedRamsey_Control_params["SpecSpan"],
        "spec_num_pts":         ModifiedRamsey_Control_params["SpecNumPoints"],
        "spec_reps":            ModifiedRamsey_Control_params["reps"],
        "spec_rounds":          ModifiedRamsey_Control_params["rounds"],
        "spec_relax_delay":     ModifiedRamsey_Control_params["relax_delay"],
        "spec_sigma":           ModifiedRamsey_Control_params["sigma"],
        "spec_gain":            ModifiedRamsey_Control_params["gain"],
        "spec_qubit_length":    ModifiedRamsey_Control_params["qubit_length"],
        "ss_search_df_trigger": ModifiedRamsey_Control_params["df"],
        "ss_accept_sep":        ModifiedRamsey_Control_params["sweet_spot_max_df_mhz"],
        "ss_dV":                ModifiedRamsey_Control_params["dV"],
        "ss_voltage_min":       ModifiedRamsey_Control_params["voltage_min"],
        "ss_voltage_max":       ModifiedRamsey_Control_params["voltage_max"],
        "ss_max_tries":         ModifiedRamsey_Control_params["max_voltage_tries"],
        "cd_period_mv":         ModifiedRamsey_Control_params.get("cd_period_mv"),
    }

    for cycle_idx_mrc in range(num_cycles_mrc):
        print(f"\n================ ModifiedRamsey_Control Cycle {cycle_idx_mrc + 1}/{num_cycles_mrc} ================")

        # ── Sweet-spot search ────────────────────────────────────────────────
        # Uses the two-strategy mAutoCoherence search:
        #   Strategy A (cd_period_mv known): one initial spec + one half-period
        #     jump → typically finds the sweet spot in 1-2 acquisitions.
        #   Strategy B (fallback): incremental walk tracking minimum separation.
        f_ge_mrc, V_sweet_mrc, pki_sw, log_mrc = find_sweet_spot(
            soc=soc, soccfg=soccfg,
            config=config,
            save_folder=save_dir_mrc + "/",
            qubit_freq_center=qubit_frequency_center,
            qubit_readout=Qubit_Readout,
            yoko=yoko,
            sweet_params=sweet_params_mrc,
        )
        if V_sweet_mrc is not None:
            current_voltage_mrc = V_sweet_mrc
        for line_mrc in log_mrc:
            print(f"  {line_mrc}")

        S_sweet_mrc   = float(pki_sw["peak_sep"]) if pki_sw["peak_sep"] is not None else 0.0
        sweet_verified = (pki_sw["peak_sep"] is None or S_sweet_mrc < sweet_max_df_mrc)

        # tau for Ramsey: maximum sensitivity is at tau = 1 / (2 * max_dispersion).
        # We use cd_max_mhz (from the independent calibration) rather than a
        # measured S1, since the search no longer requires a detour to a
        # large-separation voltage.
        tau_mrc = 1.0 / (2.0 * cd_max_mhz_mrc)

        print(
            f"[MRC] Cycle {cycle_idx_mrc + 1}: V_sweet={current_voltage_mrc:.6f} V, "
            f"f_ge={f_ge_mrc:.6f} MHz, S_sweet={S_sweet_mrc:.4f} MHz, "
            f"verified={sweet_verified}, tau={tau_mrc:.4f} us"
        )

        # ── Run Modified Ramsey at the sweet spot ────────────────────────────
        if sweet_verified:
            mr_cfg_mrc = {
                "f_ge":           f_ge_mrc,
                "df":             cd_max_mhz_mrc,
                "pi2_gain":       pi2_gain,
                "sigma":          qubit_sigma,
                "flattop_length": qubit_flattop,
                "reps":           ModifiedRamsey_Control_params["mr_reps"],
                "rounds":         1,
                "current_voltage": current_voltage_mrc,
                "Qubit_number":   Qubit_Readout,
            }
            config_mrc = config | mr_cfg_mrc

            Instance_mrc = ModifiedRamsey(
                path="ModifiedRamsey_Control",
                cfg=config_mrc, soc=soc, soccfg=soccfg, outerFolder=outerFolder
            )
            data_mrc = ModifiedRamsey.acquire(Instance_mrc)
            ModifiedRamsey.display(Instance_mrc, data_mrc, plotDisp=False, figNum=11)
            ModifiedRamsey.save_data(Instance_mrc, data_mrc)
            ModifiedRamsey.save_config(Instance_mrc)

            # ---------- classify shots and build parity trace ----------
            raw_i_mrc = np.ravel(np.array(data_mrc["data"]["shots_i"]))
            raw_q_mrc = np.ravel(np.array(data_mrc["data"]["shots_q"]))
            iq_mrc = np.column_stack([raw_i_mrc, raw_q_mrc])

            kmeans_mrc = KMeans(n_clusters=2, random_state=0, n_init=20)
            kmeans_mrc.fit_predict(iq_mrc)
            centers_mrc = kmeans_mrc.cluster_centers_

            c0_mrc = centers_mrc[0]
            c1_mrc = centers_mrc[1]
            normal_mrc   = c1_mrc - c0_mrc
            midpoint_mrc = 0.5 * (c0_mrc + c1_mrc)
            scores_mrc   = (iq_mrc - midpoint_mrc) @ normal_mrc
            binary_states_mrc = (scores_mrc > 0).astype(int)

            n0_mrc = np.sum(binary_states_mrc == 0)
            n1_mrc = np.sum(binary_states_mrc == 1)
            if n1_mrc > n0_mrc:
                binary_states_mrc = 1 - binary_states_mrc
                c0_mrc, c1_mrc = c1_mrc, c0_mrc
                normal_mrc   = c1_mrc - c0_mrc
                midpoint_mrc = 0.5 * (c0_mrc + c1_mrc)
                scores_mrc   = (iq_mrc - midpoint_mrc) @ normal_mrc

            pulse_length_us_mrc = qubit_sigma * 4
            rep_period_us_mrc   = (2 * pulse_length_us_mrc + tau_mrc
                                    + 0.05 + config_mrc["readout_length"])
            elapsed_ms_mrc = np.arange(len(raw_i_mrc)) * rep_period_us_mrc * 1e-3

            timestamp_mrc = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
            base_mrc = os.path.join(
                save_dir_mrc, f"Cycle_{cycle_idx_mrc:03d}_MRC_{timestamp_mrc}"
            )

            I_min_mrc, I_max_mrc = raw_i_mrc.min(), raw_i_mrc.max()
            Q_min_mrc, Q_max_mrc = raw_q_mrc.min(), raw_q_mrc.max()
            I_pad_mrc = 0.05 * (I_max_mrc - I_min_mrc if I_max_mrc > I_min_mrc else 1.0)
            Q_pad_mrc = 0.05 * (Q_max_mrc - Q_min_mrc if Q_max_mrc > Q_min_mrc else 1.0)
            I_line_mrc = np.linspace(I_min_mrc - I_pad_mrc, I_max_mrc + I_pad_mrc, 400)

            vertical_line_mrc = np.abs(normal_mrc[1]) < 1e-12
            if not vertical_line_mrc:
                Q_line_mrc = (midpoint_mrc[1]
                              - (normal_mrc[0] / normal_mrc[1])
                              * (I_line_mrc - midpoint_mrc[0]))

            # IQ scatter
            plt.figure(figsize=(6, 6))
            plt.plot(raw_i_mrc[binary_states_mrc == 0], raw_q_mrc[binary_states_mrc == 0],
                     ".", alpha=0.5, label="State 0")
            plt.plot(raw_i_mrc[binary_states_mrc == 1], raw_q_mrc[binary_states_mrc == 1],
                     ".", alpha=0.5, label="State 1")
            plt.plot(c0_mrc[0], c0_mrc[1], "o", markersize=10)
            plt.plot(c1_mrc[0], c1_mrc[1], "o", markersize=10)
            if vertical_line_mrc:
                plt.axvline(midpoint_mrc[0], linestyle="--", linewidth=2, label="Separator")
            else:
                plt.plot(I_line_mrc, Q_line_mrc, "--", linewidth=2, label="Separator")
            plt.xlabel("I"); plt.ylabel("Q")
            plt.xlim(I_min_mrc - I_pad_mrc, I_max_mrc + I_pad_mrc)
            plt.ylim(Q_min_mrc - Q_pad_mrc, Q_max_mrc + Q_pad_mrc)
            plt.gca().set_aspect("equal", adjustable="box")
            plt.title(
                f"Cycle {cycle_idx_mrc + 1}: MRC IQ (sweet spot)\n"
                f"V_sweet={current_voltage_mrc:.6f} V, f_ge={f_ge_mrc:.6f} MHz, "
                f"tau={tau_mrc:.4f} us"
            )
            plt.legend(); plt.tight_layout()
            plt.savefig(base_mrc + "_iq_labeled.png", dpi=300, bbox_inches="tight")
            plt.close()

            # raw binary parity trace
            plt.figure(figsize=(10, 4))
            plt.step(elapsed_ms_mrc, binary_states_mrc, where="post", linewidth=1.5)
            plt.plot(elapsed_ms_mrc, binary_states_mrc, "o", markersize=2)
            plt.xlabel("Time since start (ms)")
            plt.ylabel("Parity state")
            plt.yticks([0, 1]); plt.ylim(-0.1, 1.1)
            plt.title(
                f"Cycle {cycle_idx_mrc + 1}: MRC parity trace (sweet spot control)\n"
                f"tau={tau_mrc:.4f} us, S_sweet={S_sweet_mrc:.4f} MHz"
            )
            plt.tight_layout()
            plt.savefig(base_mrc + "_binary.png", dpi=300, bbox_inches="tight")
            plt.close()

            # ---------- moving-average + hysteresis ----------
            window_ms_mrc  = ModifiedRamsey_Control_params["window_ms"]
            dt_ms_mrc      = rep_period_us_mrc * 1e-3
            window_n_mrc   = max(1, int(round(window_ms_mrc / dt_ms_mrc)))
            low_thresh_mrc  = ModifiedRamsey_Control_params["hysteresis_low"]
            high_thresh_mrc = ModifiedRamsey_Control_params["hysteresis_high"]

            state_avg_mrc    = None
            state_hyst_mrc   = None
            switches_hyst_mrc = None
            switch_time_ms_mrc = (elapsed_ms_mrc[1:] if len(elapsed_ms_mrc) > 1
                                   else np.array([]))

            if len(binary_states_mrc) >= 1:
                kernel_mrc    = np.ones(window_n_mrc, dtype=float) / window_n_mrc
                state_avg_mrc = np.convolve(
                    binary_states_mrc.astype(float), kernel_mrc, mode="same"
                )

                state_hyst_mrc   = np.empty_like(binary_states_mrc)
                current_state_mrc = int(binary_states_mrc[0])
                for idx_mrc, val_mrc in enumerate(state_avg_mrc):
                    if val_mrc >= high_thresh_mrc:
                        current_state_mrc = 1
                    elif val_mrc <= low_thresh_mrc:
                        current_state_mrc = 0
                    state_hyst_mrc[idx_mrc] = current_state_mrc

                switches_hyst_mrc = (np.diff(state_hyst_mrc) != 0).astype(int)

                plt.figure(figsize=(10, 4))
                plt.plot(elapsed_ms_mrc, state_avg_mrc, linewidth=1.5,
                         label="Moving average")
                plt.axhline(high_thresh_mrc, linestyle="--", linewidth=1.2,
                            label=f"High threshold = {high_thresh_mrc:.2f}")
                plt.axhline(low_thresh_mrc,  linestyle="--", linewidth=1.2,
                            label=f"Low threshold = {low_thresh_mrc:.2f}")
                plt.xlabel("Time since start (ms)")
                plt.ylabel("Smoothed parity state")
                plt.ylim(-0.05, 1.05)
                plt.title(
                    f"Cycle {cycle_idx_mrc + 1}: MRC moving-average parity trace\n"
                    f"window={window_n_mrc * dt_ms_mrc:.3f} ms, tau={tau_mrc:.4f} us"
                )
                plt.legend(); plt.tight_layout()
                plt.savefig(base_mrc + "_state_moving_avg.png", dpi=300, bbox_inches="tight")
                plt.close()

                plt.figure(figsize=(10, 4))
                plt.step(elapsed_ms_mrc, state_hyst_mrc, where="post",
                         linewidth=1.5, label="Hysteresis state")
                plt.plot(elapsed_ms_mrc, binary_states_mrc, "o", markersize=2,
                         alpha=0.35, label="Raw binary state")
                plt.xlabel("Time since start (ms)")
                plt.ylabel("Parity state")
                plt.yticks([0, 1]); plt.ylim(-0.1, 1.1)
                plt.title(
                    f"Cycle {cycle_idx_mrc + 1}: MRC hysteresis parity trace\n"
                    f"low={low_thresh_mrc:.2f}, high={high_thresh_mrc:.2f}, "
                    f"window={window_n_mrc * dt_ms_mrc:.3f} ms"
                )
                plt.legend(); plt.tight_layout()
                plt.savefig(base_mrc + "_state_hysteresis.png",
                            dpi=300, bbox_inches="tight")
                plt.close()

                if len(switches_hyst_mrc) >= 1:
                    plt.figure(figsize=(10, 4))
                    plt.step(switch_time_ms_mrc, switches_hyst_mrc, where="post",
                             linewidth=1.5)
                    plt.plot(switch_time_ms_mrc, switches_hyst_mrc, "o", markersize=2)
                    plt.xlabel("Time since start (ms)")
                    plt.ylabel("Jump detected")
                    plt.yticks([0, 1]); plt.ylim(-0.1, 1.1)
                    plt.title(
                        f"Cycle {cycle_idx_mrc + 1}: MRC jumps from hysteresis state\n"
                        f"low={low_thresh_mrc:.2f}, high={high_thresh_mrc:.2f}"
                    )
                    plt.tight_layout()
                    plt.savefig(base_mrc + "_state_hysteresis_jumps.png",
                                dpi=300, bbox_inches="tight")
                    plt.close()

            np.savez(
                base_mrc + ".npz",
                elapsed_ms           = np.array(elapsed_ms_mrc),
                raw_i                = np.array(raw_i_mrc),
                raw_q                = np.array(raw_q_mrc),
                scores               = np.array(scores_mrc),
                binary_states        = np.array(binary_states_mrc),
                state_avg            = np.array(state_avg_mrc)  if state_avg_mrc  is not None else np.array([]),
                state_hysteresis     = np.array(state_hyst_mrc) if state_hyst_mrc is not None else np.array([]),
                hysteresis_switches  = np.array(switches_hyst_mrc) if switches_hyst_mrc is not None else np.array([]),
                switch_time_ms       = np.array(switch_time_ms_mrc),
                centers              = np.array([c0_mrc, c1_mrc]),
                midpoint             = np.array(midpoint_mrc),
                normal               = np.array(normal_mrc),
                V_sweet              = np.array(current_voltage_mrc),
                S_sweet_mhz          = np.array(S_sweet_mrc),
                f_ge                 = np.array(f_ge_mrc),
                tau_us               = np.array(tau_mrc),
                half_period_v        = np.array(half_period_v_mrc),
                cycle_idx            = np.array(cycle_idx_mrc),
                hysteresis_low       = np.array(low_thresh_mrc),
                hysteresis_high      = np.array(high_thresh_mrc),
                moving_avg_window_n  = np.array(window_n_mrc),
                moving_avg_window_ms = np.array(window_n_mrc * dt_ms_mrc),
                config               = np.array(config_mrc, dtype=object),
            )

            with open(base_mrc + "_config.json", "w") as fh:
                json.dump(config_mrc, fh, indent=2, default=float)

            cycle_summary_mrc.append({
                "cycle_idx":      cycle_idx_mrc,
                "success":        True,
                "V_sweet":        current_voltage_mrc,
                "S_sweet_mhz":    S_sweet_mrc,
                "sweet_verified": True,
                "f_ge":           f_ge_mrc,
                "tau_us":         tau_mrc,
            })

        else:
            print(
                f"[MRC] Cycle {cycle_idx_mrc + 1}: sweet spot not verified "
                f"(S_sweet={S_sweet_mrc:.4f} MHz >= threshold {sweet_max_df_mrc} MHz). "
                f"Skipping Ramsey run."
            )
            cycle_summary_mrc.append({
                "cycle_idx":      cycle_idx_mrc,
                "success":        False,
                "stage_failed":   "sweet_spot_not_verified",
                "V_sweet":        current_voltage_mrc,
                "S_sweet_mhz":    S_sweet_mrc,
                "sweet_verified": False,
            })

    summary_path_mrc = os.path.join(
        save_dir_mrc,
        f"CycleSummary_{datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}.json"
    )
    with open(summary_path_mrc, "w") as fh:
        json.dump(cycle_summary_mrc, fh, indent=2, default=float)

if RunChargeDispersionQuasiCW:
    config["reps"] = ChargeDispersion_params["repetitions"]
    config["rounds"] = 1
    config["Gauss"] = Spec_relevant_params["Gauss"]
    config["relax_delay"] = ChargeDispersion_params["relax_delay"]

    if config["Gauss"]:
        config["sigma"] = Spec_relevant_params["sigma"]
        config["qubit_gain"] = Spec_relevant_params["gain"]

    # one-frequency mode
    config["SpecNumPoints"] = 1
    config["SpecSpan"] = 0
    config["step"] = 0
    config["start"] = ChargeDispersion_params["probe_freq"]
    config["expts"] = 1

    Instance_specSlice = ChargeDispersionQuasiCW(
        path="ChargeDispersion",
        cfg=config,
        soc=soc,
        soccfg=soccfg,
        outerFolder=outerFolder,
    )

    data_specSlice = Instance_specSlice.acquire(load_pulses=True, print_time=True)

    x_pts = np.array(data_specSlice["data"]["x_pts"])

    # repetition-resolved IQ data
    raw_i = np.ravel(np.array(data_specSlice["data"]["raw_i"]))
    raw_q = np.ravel(np.array(data_specSlice["data"]["raw_q"]))

    # stack IQ points
    iq = np.column_stack([raw_i, raw_q])

    # ---------------------------
    # Straight-line blob separation using 2-cluster fit
    # ---------------------------
    kmeans = KMeans(n_clusters=2, random_state=0, n_init=20)
    labels = kmeans.fit_predict(iq)
    centers = kmeans.cluster_centers_

    c0 = centers[0]
    c1 = centers[1]

    # normal vector to separating line = line connecting the centers
    normal = c1 - c0
    midpoint = 0.5 * (c0 + c1)

    # signed distance from perpendicular bisector
    scores = (iq - midpoint) @ normal

    # binary labels from side of line
    binary_amps = (scores > 0).astype(int)

    # optional relabel so state 1 is the less populated blob
    n0 = np.sum(binary_amps == 0)
    n1 = np.sum(binary_amps == 1)
    if n1 > n0:
        binary_amps = 1 - binary_amps
        labels = 1 - labels
        c0, c1 = c1, c0
        normal = c1 - c0
        midpoint = 0.5 * (c0 + c1)
        scores = (iq - midpoint) @ normal

    # amplitude for reference only
    amps = np.abs(raw_i + 1j * raw_q) ** 2

    # approximate time axis per repetition
    rep_period_us = (
        1.0 + 0.5 + config["readout_length"] + 10 + config["relax_delay"]
    )
    elapsed_s = np.arange(len(raw_i)) * rep_period_us * 1e-6

    save_dir = os.path.join(outerFolder, "ChargeDispersion")
    os.makedirs(save_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    base = os.path.join(save_dir, f"ChargeDispersionQuasiCW_{timestamp}")

    # line for plotting: normal dot (x - midpoint) = 0
    # => n_x*(I - I_mid) + n_y*(Q - Q_mid) = 0
    # => Q = Q_mid - (n_x/n_y)*(I - I_mid), unless n_y ~ 0
    I_min, I_max = raw_i.min(), raw_i.max()
    I_pad = 0.05 * (I_max - I_min if I_max > I_min else 1.0)
    I_line = np.linspace(I_min - I_pad, I_max + I_pad, 400)

    vertical_line = np.abs(normal[1]) < 1e-12
    if not vertical_line:
        Q_line = midpoint[1] - (normal[0] / normal[1]) * (I_line - midpoint[0])

    # ---------------------------
    # Plot 1: raw IQ blobs with separating line
    # ---------------------------
    plt.figure(figsize=(6, 6))
    plt.plot(raw_i, raw_q, ".", alpha=0.35, label="IQ data")
    plt.plot(c0[0], c0[1], "o", markersize=10, label="Blob center 0")
    plt.plot(c1[0], c1[1], "o", markersize=10, label="Blob center 1")

    if vertical_line:
        plt.axvline(midpoint[0], linestyle="--", linewidth=2, label="Separator")
    else:
        plt.plot(I_line, Q_line, "--", linewidth=2, label="Separator")

    plt.xlabel("I")
    plt.ylabel("Q")
    plt.title("ChargeDispersionQuasiCW IQ blobs with straight-line separator")

    i_min, i_max = raw_i.min(), raw_i.max()
    q_min, q_max = raw_q.min(), raw_q.max()
    i_pad = 0.05 * (i_max - i_min if i_max > i_min else 1.0)
    q_pad = 0.05 * (q_max - q_min if q_max > q_min else 1.0)

    plt.xlim(i_min - i_pad, i_max + i_pad)
    plt.ylim(q_min - q_pad, q_max + q_pad)
    plt.gca().set_aspect("equal", adjustable="box")

    plt.legend()
    plt.tight_layout()
    plt.show()

    # ---------------------------
    # Plot 2: IQ blobs colored by assigned state
    # ---------------------------
    plt.figure(figsize=(6, 6))
    plt.plot(raw_i[binary_amps == 0], raw_q[binary_amps == 0], ".", alpha=0.5, label="State 0")
    plt.plot(raw_i[binary_amps == 1], raw_q[binary_amps == 1], ".", alpha=0.5, label="State 1")
    plt.plot(c0[0], c0[1], "o", markersize=10)
    plt.plot(c1[0], c1[1], "o", markersize=10)

    if vertical_line:
        plt.axvline(midpoint[0], linestyle="--", linewidth=2, label="Separator")
    else:
        plt.plot(I_line, Q_line, "--", linewidth=2, label="Separator")

    plt.xlabel("I")
    plt.ylabel("Q")
    plt.title("IQ blobs colored by straight-line separation")
    plt.legend()
    plt.tight_layout()
    plt.savefig(base + "_iq_blobs_labeled.png", dpi=300, bbox_inches="tight")
    plt.show()
    plt.close()

    # ---------------------------
    # Plot 3: projection score histogram
    # ---------------------------
    plt.figure(figsize=(7, 5))
    plt.hist(scores, bins=100, alpha=0.7)
    plt.axvline(0.0, linestyle="--", linewidth=2, label="Decision boundary")
    plt.xlabel("Signed distance from separator")
    plt.ylabel("Counts")
    plt.title("Separator score histogram")
    plt.legend()
    plt.tight_layout()
    plt.savefig(base + "_separator_score_hist.png", dpi=300, bbox_inches="tight")
    plt.show()
    plt.close()

    # ---------------------------
    # Plot 4: binary parity trace over time
    # ---------------------------
    plt.figure(figsize=(10, 4))
    plt.plot(elapsed_s, binary_states, "-", linewidth=1.5)
    plt.xlabel("Time since start (s)")
    plt.ylabel("Assigned state")
    plt.yticks([0, 1])
    plt.ylim(-0.1, 1.1)
    plt.title(f"Cycle {cycle_idx + 1}: QuasiCW binary trace")
    plt.tight_layout()
    plt.savefig(base + "_binary.png", dpi=300, bbox_inches="tight")
    plt.close()

    np.savez(
        base + ".npz",
        elapsed_s=np.array(elapsed_s),
        raw_i=np.array(raw_i),
        raw_q=np.array(raw_q),
        amps=np.array(amps),
        scores=np.array(scores),
        binary_amps=np.array(binary_amps),
        centers=np.array([c0, c1]),
        midpoint=np.array(midpoint),
        normal=np.array(normal),
        x_pts=np.array(x_pts),
        config=np.array(config, dtype=object),
    )

    with open(base + "_config.json", "w") as f:
        json.dump(config, f, indent=2, default=float)


if RunChargeDispersionRamsey:
    repetitions = T1T2_params['repetitions']
    for i in range(repetitions):
        cd_cfg = {
            "df": ChargeDispersion_params["df"],
            "reps": 1,
            "rounds": 1,
            "pi2_gain": pi2_gain,
            "sigma": qubit_sigma,
            "flattop_length": qubit_flattop,
            "f_ge": qubit_frequency_center,
            "relax_delay": ChargeDispersion_params["relax_delay"],
            "Qubit_number": Qubit_Readout,
        }

        config_cd = config | cd_cfg
        iCD = ChargeDispersion(
            path="ChargeDispersion",
            cfg=config_cd,
            soc=soc,
            soccfg=soccfg,
            outerFolder=outerFolder
        )
        dCD = ChargeDispersion.acquire(iCD)
        ChargeDispersion.display(iCD, dCD, plotDisp=True, figNum=5)
        ChargeDispersion.save_data(iCD, dCD)
        ChargeDispersion.save_config(iCD)

# Amplitude Rabi
  ### note that UpdateConfig will overwrite elements in BaseConfig

if RunAmplitudeRabi:
    number_of_steps = Amplitude_Rabi_params["number_of_steps"]
    step = int(Amplitude_Rabi_params["max_gain"] / number_of_steps)
    ARabi_config = {'start': 0, 'step': step, "expts": number_of_steps, "reps": Amplitude_Rabi_params['reps'],
                    "rounds": Amplitude_Rabi_params['rounds'],
                    "sigma": qubit_sigma, "f_ge": Amplitude_Rabi_params["qubit_freq"],
                    "relax_delay": Amplitude_Rabi_params["relax_delay"],
                    "flattop_length": qubit_flattop,
                    "Qubit_number": Qubit_Pulse}

    fit = Amplitude_Rabi_params["fit"]

    config = config | ARabi_config
    if qubit_flattop != None:
        ARabi_config = {'gain_start': 0, "gain_end": Amplitude_Rabi_params["max_gain"],
                        'gainNumPoints': number_of_steps,
                        "reps": Amplitude_Rabi_params['reps'],
                        "rounds": Amplitude_Rabi_params['rounds'],
                        "sigma": qubit_sigma, "f_ge": Amplitude_Rabi_params["qubit_freq"],
                        "relax_delay": 8000,
                        "flattop_length": qubit_flattop}
        config = config | ARabi_config  ### note that UpdateConfig will overwrite elements in BaseConfig
        iAmpRabi = AmplitudeRabiFF_N(path="AmplitudeRabi", cfg=config, soc=soc, soccfg=soccfg,
                                   outerFolder=outerFolder)
        dAmpRabi = AmplitudeRabiFF_N.acquire(iAmpRabi)
        AmplitudeRabiFF_N.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2, fit=fit)
        AmplitudeRabiFF_N.save_data(iAmpRabi, dAmpRabi)
        AmplitudeRabiFF_N.save_config(iAmpRabi)
    else:
        iAmpRabi = AmplitudeRabiFF(path="AmplitudeRabi", cfg=config, soc=soc, soccfg=soccfg,
                                   outerFolder=outerFolder)
        dAmpRabi = AmplitudeRabiFF.acquire(iAmpRabi)
        AmplitudeRabiFF.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2, fit=fit)
        AmplitudeRabiFF.save_data(iAmpRabi, dAmpRabi)
        AmplitudeRabiFF.save_config(iAmpRabi)

#
if RunT1:
    for i in range(T1T2_params['repetitions']):
        if T1T2_params['repetitions'] > 1:
            plot_disp = False
        else:
            plot_disp = True
        expt_cfg = {"start": 0, "step": T1T2_params["T1_step"], "expts": T1T2_params["T1_expts"],
                    "reps": T1T2_params["T1_reps"],"Qubit_number": Qubit_Readout,
                    "rounds": T1T2_params["T1_rounds"], "pi_gain": qubit_gain, "relax_delay": T1T2_params["relax_delay"],
                    "sigma": qubit_sigma, "flattop_length": qubit_flattop,
                    "f_ge": qubit_frequency_center
                    }

        config = config | expt_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
        iT1 = T1FF(path="T1", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
        dT1 = T1FF.acquire(iT1)
        T1FF.display(iT1, dT1, plotDisp=plot_disp, figNum=2)
        T1FF.save_data(iT1, dT1)
        T1FF.save_config(iT1)

        time.sleep(10)
        soc.reset_gens()

if RunT1T2E:
    for i in range(T1T2_params['repetitions']):
        # match your plotting behavior
        plot_disp = (T1T2_params['repetitions'] <= 1)

        # -------------------- T1 --------------------
        expt_cfg_T1 = {
            "start": 0,
            "step": T1T2_params["T1_step"],
            "expts": T1T2_params["T1_expts"],
            "reps": T1T2_params["T1_reps"],
            "Qubit_number": Qubit_Readout,
            "rounds": T1T2_params["T1_rounds"],
            "pi_gain": qubit_gain,
            "relax_delay": T1T2_params["relax_delay"],
            "sigma": qubit_sigma,
            "flattop_length": qubit_flattop,
            "f_ge": qubit_frequency_center,
        }

        config_T1 = config | expt_cfg_T1
        iT1 = T1FF(path="T1", cfg=config_T1, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
        dT1 = T1FF.acquire(iT1)
        T1FF.display(iT1, dT1, plotDisp=plot_disp, figNum=2)
        T1FF.save_data(iT1, dT1)
        T1FF.save_config(iT1)

        # -------------------- T2E immediately after --------------------
        num_pulses = T2E_params["num_pi_pulses"]

        # compute time step with your hardware quantization
        int_steps = T2E_params["T2_max_us"] // (0.00232515 * (num_pulses + 1) * T2E_params["T2_expts"])
        if int_steps == 0:
            print("[T2E] Step size is 0! need to increase total time or decrease experiments")
            break

        expt_cfg_T2E = {
            "start": 0,
            "step": 0.00232515 * (num_pulses + 1) * int_steps,
            "expts": T2E_params["T2_expts"],
            "reps": T2E_params["T2_reps"],
            "rounds": T2E_params["T2_rounds"],
            "pi_gain": qubit_gain,
            "pi2_gain": pi2_gain,
            "relax_delay": T2E_params["relax_delay"],
            "f_ge": qubit_frequency_center + T2E_params["freq_shift"],
            "num_pi_pulses": num_pulses,
            "sigma": qubit_sigma,
            "flattop_length": qubit_flattop,
            "Qubit_number": Qubit_Readout,
        }

        # optional display normalization params
        if T2E_params.get("rotation_angle", False) != False:
            expt_cfg_T2E["rotation_angle"] = T2E_params["rotation_angle"]
            expt_cfg_T2E["min_max"] = T2E_params["min_max"]

        config_T2E = config | expt_cfg_T2E
        iT2E = T2EMUX(path="T2E", cfg=config_T2E, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
        dT2E = T2EMUX.acquire(iT2E)
        T2EMUX.display(iT2E, dT2E, plotDisp=plot_disp, figNum=3)
        T2EMUX.save_data(iT2E, dT2E)
        T2EMUX.save_config(iT2E)

        # -------------------- between iterations --------------------
        time.sleep(10)
        soc.reset_gens()

if RunT1T2RT2E:
    def _run_experiment(ExptClass, path, expt_cfg, figNum, plot_disp=False):
        cfg_run = config | expt_cfg
        inst = ExptClass(path=path, cfg=cfg_run, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
        data = ExptClass.acquire(inst)
        ExptClass.display(inst, data, plotDisp=plot_disp, figNum=figNum)
        ExptClass.save_data(inst, data)
        ExptClass.save_config(inst)
        return inst, data

    for i in range(T1T2_params["repetitions"]):
        plot_disp = (T1T2_params["repetitions"] <= 1)

        # -------------------- T1 --------------------
        expt_cfg_T1 = {
            "start": 0,
            "step": T1T2_params["T1_step"],
            "expts": T1T2_params["T1_expts"],
            "reps": T1T2_params["T1_reps"],
            "rounds": T1T2_params["T1_rounds"],
            "Qubit_number": Qubit_Readout,
            "pi_gain": qubit_gain,
            "relax_delay": T1T2_params["relax_delay"],
            "sigma": qubit_sigma,
            "flattop_length": qubit_flattop,
            "f_ge": qubit_frequency_center,
        }
        _run_experiment(T1FF, "T1", expt_cfg_T1, figNum=2, plot_disp=plot_disp)

        # -------------------- T2E --------------------
        num_pulses = T2E_params["num_pi_pulses"]
        int_steps = T2E_params["T2_max_us"] // (
            0.00232515 * (num_pulses + 1) * T2E_params["T2_expts"]
        )
        if int_steps == 0:
            print("[T2E] Step size is 0! need to increase total time or decrease experiments")
            break

        expt_cfg_T2E = {
            "start": 0,
            "step": 0.00232515 * (num_pulses + 1) * int_steps,
            "expts": T2E_params["T2_expts"],
            "reps": T2E_params["T2_reps"],
            "rounds": T2E_params["T2_rounds"],
            "Qubit_number": Qubit_Readout,
            "pi_gain": qubit_gain,
            "pi2_gain": pi2_gain,
            "relax_delay": T2E_params["relax_delay"],
            "f_ge": qubit_frequency_center + T2E_params["freq_shift"],
            "num_pi_pulses": num_pulses,
            "sigma": qubit_sigma,
            "flattop_length": qubit_flattop,
        }
        if T2E_params.get("rotation_angle") is not None:
            expt_cfg_T2E["rotation_angle"] = T2E_params["rotation_angle"]
            expt_cfg_T2E["min_max"] = T2E_params["min_max"]

        _run_experiment(T2EMUX, "T2E", expt_cfg_T2E, figNum=3, plot_disp=plot_disp)

        # -------------------- T2R --------------------
        expt_cfg_T2R = {
            "start": 0,
            "step": T1T2_params["T2_step"],
            "phase_step": soccfg.deg2reg(0 * 360 / 50, gen_ch=2),
            "expts": T1T2_params["T2_expts"],
            "reps": T1T2_params["T2_reps"],
            "rounds": T1T2_params["T2_rounds"],
            "pi_gain": qubit_gain,
            "pi2_gain": pi2_gain,
            "relax_delay": T1T2_params["relax_delay"],
            "f_ge": qubit_frequency_center + T1T2_params["freq_shift"],
            "sigma": qubit_sigma,
            "flattop_length": qubit_flattop,
        }
        _run_experiment(T2R, "T2R", expt_cfg_T2R, figNum=4, plot_disp=plot_disp)

        time.sleep(10)
        soc.reset_gens()


if RunT2:
    T2R_cfg = {"start": 0, "step": T1T2_params["T2_step"], "phase_step": soccfg.deg2reg(0 * 360 / 50, gen_ch=2),
               "expts": T1T2_params["T2_expts"], "reps": T1T2_params["T2_reps"], "rounds": T1T2_params["T2_rounds"],
               "pi_gain": qubit_gain,
               "pi2_gain": pi2_gain, "relax_delay": T1T2_params["relax_delay"],
               'f_ge': qubit_frequency_center + T1T2_params["freq_shift"],
               "sigma": qubit_sigma, "flattop_length": qubit_flattop
               }
    for i in range(T1T2_params['repetitions']):
        config = config | T2R_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
        iT2R = T2R(path="T2R", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
        dT2R = T2R.acquire(iT2R)
        T2R.display(iT2R, dT2R, plotDisp=False, figNum=2)
        T2R.save_data(iT2R, dT2R)
        T2R.save_config(iT2R)
        time.sleep(10)
        soc.reset_gens()


if RunT2E:
    for i in range(T2E_params['repetitions']):
        # match T1 behavior: only show plots if single repetition
        if T2E_params['repetitions'] > 1:
            plot_disp = False
        else:
            plot_disp = True

        num_pulses = T2E_params["num_pi_pulses"]

        # compute time step with your hardware quantization
        int_steps = T2E_params["T2_max_us"] // (0.00232515 * (num_pulses + 1) * T2E_params["T2_expts"])
        print(f"[T2E rep {i}] int_steps={int_steps}, step(us)={0.00232515*(num_pulses+1)*int_steps}, expts={T2E_params['T2_expts']}")

        if int_steps == 0:
            print('Step size is 0! need to increase total time or decrease experiments')
            break  # or continue, but breaking is usually safer
        else:
            T2E_cfg = {
                "start": 0,
                "step": 0.00232515 * (num_pulses + 1) * int_steps,
                "expts": T2E_params["T2_expts"],
                "reps": T2E_params["T2_reps"],
                "rounds": T2E_params["T2_rounds"],
                "pi_gain": qubit_gain,
                "pi2_gain": pi2_gain,
                "relax_delay": T2E_params["relax_delay"],
                "f_ge": qubit_frequency_center + T2E_params["freq_shift"],
                "num_pi_pulses": num_pulses,
                "sigma": qubit_sigma,
                "flattop_length": qubit_flattop,
            }

            # optional display normalization params
            if T2E_params["rotation_angle"] != False:
                T2E_cfg["rotation_angle"] = T2E_params["rotation_angle"]
                T2E_cfg["min_max"] = T2E_params["min_max"]

            config_run = config | T2E_cfg

            # new instance each repetition (like T1)
            iT2E = T2EMUX(path="T2E", cfg=config_run, soc=soc, soccfg=soccfg, outerFolder=outerFolder)

            dT2E = T2EMUX.acquire(iT2E)
            T2EMUX.display(iT2E, dT2E, plotDisp=plot_disp, figNum=2)
            T2EMUX.save_data(iT2E, dT2E)
            T2EMUX.save_config(iT2E)

            time.sleep(10)
            soc.reset_gens()

def sanity_dump(cfg, tag=""):
    keys = ["pulse_freq","qubit_freq","SpecSpan","SpecNumPoints","step","start",
            "qubit_pulse_style","qubit_length","qubit_gain","pulse_gain",
            "readout_length","cavity_min"]
    print(f"\n--- Sanity {tag} ---")
    for k in keys:
        if k in cfg: print(f"{k:>18}: {cfg[k]}")
    # If BaseConfig stores LOs/IFs/NCOs, print them too:
    for k in ["cavity_LO","qubit_LO","cavity_IF","qubit_IF","read_lo","drive_lo"]:
        if k in cfg: print(f"{k:>18}: {cfg[k]}")
    print("-------------------\n")

if RunTrans_QubitSpec:
    sanity_dump(config)
    for i in range(T1T2_params['repetitions']):

        config["reps"] = Spec_relevant_params['reps']  # want more reps and rounds for qubit data
        config["rounds"] = Spec_relevant_params['rounds']
        config["Gauss"] = Spec_relevant_params['Gauss']
        if Spec_relevant_params['Gauss']:
            config['sigma'] = Spec_relevant_params["sigma"]
            config["qubit_gain"] = Spec_relevant_params['gain']
        Instance_specSlice = QubitSpecSliceFF(path="QubitSpecFF", cfg=config, soc=soc, soccfg=soccfg,
                                              outerFolder=outerFolder)
        data_specSlice = QubitSpecSliceFF.acquire(Instance_specSlice)
        QubitSpecSliceFF.display(
            Instance_specSlice,
            data_specSlice,
            plotDisp=False,
            figNum=2,
            min_sep=Spec_relevant_params["min_sep_MHz"],
            fit_window_mhz=Spec_relevant_params["fit_window_mhz"],
            prominent_ratio=Spec_relevant_params["prominent_ratio"],
        )
        QubitSpecSliceFF.save_data(Instance_specSlice, data_specSlice)
        QubitSpecSliceFF.save_config(Instance_specSlice)

if RunChargeSweep:
    sanity_dump(config)
    config["reps"] = Spec_relevant_params['reps']
    config["rounds"] = Spec_relevant_params['rounds']
    config["Gauss"] = Spec_relevant_params['Gauss']

    if Spec_relevant_params['Gauss']:
        config['sigma'] = Spec_relevant_params["sigma"]
        config["qubit_gain"] = Spec_relevant_params['gain']

    voltage_pts = np.arange(config['voltage_start'],
                            config['voltage_end'],
                            config['voltage_step'])
    # will initialize after first acquisition, once x_pts length is known
    avgamp_map = None
    fig = None
    ax = None
    im = None
    cbar = None
    for i, voltage in enumerate(voltage_pts):
        if voltage > 10:
            print("voltage too high")
            break
        if not yoko_fixed:
            ramp_to(yoko, voltage)
        config['current_voltage'] = float(voltage)
        Instance_specSlice = QubitSpecSliceFF(
            path="QubitSpecFF",
            cfg=config,
            soc=soc,
            soccfg=soccfg,
            outerFolder=outerFolder
        )
        data_specSlice = QubitSpecSliceFF.acquire(Instance_specSlice)
        QubitSpecSliceFF.display(
            Instance_specSlice,
            data_specSlice,
            plotDisp=False,
            figNum=2,
            min_sep=Spec_relevant_params["min_sep_MHz"],
            fit_window_mhz=Spec_relevant_params["fit_window_mhz"],
            prominent_ratio=Spec_relevant_params["prominent_ratio"],
        )
        QubitSpecSliceFF.save_data(Instance_specSlice, data_specSlice)
        QubitSpecSliceFF.save_config(Instance_specSlice)
        x_pts = np.array(data_specSlice['data']['x_pts'])
        avgi = np.array(data_specSlice['data']['avgi'][0][0])
        avgq = np.array(data_specSlice['data']['avgq'][0][0])
        # Rotate onto the signal-bearing IQ axis (background-subtracted) instead of
        # the raw magnitude |I+iQ|^2: the magnitude is dominated by the large, noisy
        # background quadrature, which both buries per-slice peaks and washes out the
        # charge-sweep heatmap. The projection gives each slice a ~0 baseline with the
        # qubit feature as a positive bump.
        avgamp0 = project_iq_signal(avgi, avgq)
        # find up to two peaks with a minimum spacing in x-units
        min_spacing = 0.05  # same units as x_pts
        dx = np.mean(np.diff(x_pts))
        min_distance_pts = max(1, int(np.ceil(min_spacing / dx)))

        peak_inds, _ = find_peaks(avgamp0, distance=min_distance_pts)

        # keep the two tallest peaks
        if len(peak_inds) > 0:
            peak_inds = peak_inds[np.argsort(avgamp0[peak_inds])[::-1][:2]]
            peak_inds = peak_inds[np.argsort(x_pts[peak_inds])]  # optional: sort by frequency
            peak_freqs = x_pts[peak_inds]
            peak_vals = avgamp0[peak_inds]
        else:
            peak_freqs = np.array([])
            peak_vals = np.array([])

        print("peak freqs:", peak_freqs)
        # initialize plotting objects once we know x axis length
        if avgamp_map is None:
            avgamp_map = np.full((len(voltage_pts), len(x_pts)), np.nan)
            plt.ion()
            fig, ax = plt.subplots(figsize=(8, 6))
            x_step = x_pts[1] - x_pts[0] if len(x_pts) > 1 else 1
            y_step = voltage_pts[1] - voltage_pts[0] if len(voltage_pts) > 1 else 1

            im = ax.imshow(
                avgamp_map,
                aspect='auto',
                origin='lower',
                interpolation='none',
                extent=[
                    x_pts[0] - x_step / 2,
                    x_pts[-1] + x_step / 2,
                    voltage_pts[0] - y_step / 2,
                    voltage_pts[-1] + y_step / 2
                ]
            )
            cbar = fig.colorbar(im, ax=ax)
            cbar.set_label("rotated IQ projection")

            ax.set_xlabel("Frequency")
            ax.set_ylabel("Voltage")
            ax.set_title("Charge sweep for Qubit Spec")

            plt.show(block=False)
        # store this voltage slice
        avgamp_map[i, :] = avgamp0
        # update heatmap
        im.set_data(avgamp_map)
        # optional: rescale color as data comes in
        im.set_clim(
            np.nanmin(avgamp_map),
            np.nanmax(avgamp_map)
        )
        ax.set_title(f"\nVoltage = {voltage:.4f}")
        fig.canvas.draw_idle()
        plt.pause(0.1)

    fig.savefig(Instance_specSlice.iname[:-4] + "_ChargeSweepHeatmap.png", dpi=300, bbox_inches="tight")
    np.savez(
        Instance_specSlice.fname[:-3] + "_ChargeSweepHeatmap.npz",
        avgamp_map=avgamp_map,
        x_pts=x_pts,
        voltage_pts=voltage_pts,
    )

    plt.ioff()
    plt.close(fig)

#######################################################
qubit_gains = [Qubit_Parameters[str(Q_R)]['Qubit']['Gain'] for Q_R in SS_params["Qubit_Pulse"]]
qubit_frequency_centers = [Qubit_Parameters[str(Q_R)]['Qubit']['Frequency'] for Q_R in SS_params["Qubit_Pulse"]]


UpdateConfig = {
    ###### cavity
    # "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
    "read_pulse_style": "const", # --Fixed
    "readout_length": SS_params["Readout_Time"], # us (length of the pulse applied)
    "adc_trig_offset": SS_params["ADC_Offset"],
    "pi2_SS" : SS_params["pi2_SS"],

    # "pulse_gain": cavity_gain, # [DAC units]
    "pulse_gain": cavity_gain,  # [DAC units]
    "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
    ##### qubit spec parameters
    "qubit_pulse_style": "arb",
    "sigma": qubit_sigma,  ### units us, define a 20ns sigma
    "qubit_gain": qubit_gain,
    "f_ge": qubit_frequency_center,
    "qubit_gains": qubit_gains,
    "f_ges": qubit_frequency_centers,
    ##### define shots
    "shots": SS_params["Shots"], ### this gets turned into "reps"
    "relax_delay": SS_params['relax_delay'],  # us
    "flattop_length": qubit_flattop
}

config = BaseConfig | UpdateConfig
config["FF_Qubits"] = FF_Qubits
config['Read_Indeces'] = Qubit_Readout


if SingleShot:
    config['number_of_pulses'] = SS_params['number_of_pulses']
    if SS_params['pi2_SS']:
        config['qubit_gain'] = pi2_gain
    Instance_SingleShotProgram = SingleShotProgramFFMUX(path="SingleShot", outerFolder=outerFolder, cfg=config, soc=soc,soccfg=soccfg)
    data_SingleShotProgram = SingleShotProgramFFMUX.acquire(Instance_SingleShotProgram)
    # print(data_SingleShotProgram)
    SingleShotProgramFFMUX.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True)

    SingleShotProgramFFMUX.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
    SingleShotProgramFFMUX.save_config(Instance_SingleShotProgram)
    print('Angle: ', data_SingleShotProgram['data']['angle'][0])
    print('threshold: ', data_SingleShotProgram['data']['threshold'][0])

if RunT1SS:
    for i in range(T1SS_params["repetitions"]):
        if T1SS_params["calibrate_SS"]:
            config['number_of_pulses'] = SS_params['number_of_pulses']
            Instance_SingleShotProgram = SingleShotProgramFFMUX(path="SingleShot", outerFolder=outerFolder, cfg=config,
                                                                soc=soc, soccfg=soccfg)
            data_SingleShotProgram = SingleShotProgramFFMUX.acquire(Instance_SingleShotProgram)
            SingleShotProgramFFMUX.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=False)
            SingleShotProgramFFMUX.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
            SingleShotProgramFFMUX.save_config(Instance_SingleShotProgram)
            angle = data_SingleShotProgram['data']['angle'][0]
            threshold = data_SingleShotProgram['data']['threshold'][0]
        else:
            angle = T1SS_params["angle"]
            threshold = T1SS_params["threshold"]
        print(angle, threshold)

        expt_cfg = {"start": 0, "step": T1SS_params["T1_step"], "expts": T1SS_params["T1_expts"],
                    'reps': T1SS_params['reps'],
                    "pi_gain": qubit_gain, "relax_delay": T1SS_params["relax_delay"]
                    }
        config = config | expt_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
        iT1 = T1_SS(path="T1SS", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
        dT1 = T1_SS.acquire(iT1, angle = angle, threshold = threshold)
        T1_SS.display(iT1, dT1, plotDisp=False, figNum=2)
        T1_SS.save_data(iT1, dT1)
        T1_SS.save_config(iT1)

        time.sleep(10)
        soc.reset_gens()


if SingleShot_ReadoutOptimize:
    span = SS_R_params['span']
    cav_gain_start = SS_R_params['gain_start']
    cav_gain_stop = SS_R_params['gain_stop']
    cav_gain_pts = SS_R_params['gain_pts']
    cav_trans_pts = SS_R_params['trans_pts']
    config['number_of_pulses'] = 1
    exp_parameters = {
        ###### cavity
        "cav_gain_Start": cav_gain_start,
        "cav_gain_Stop": cav_gain_stop,
        "cav_gain_Points": cav_gain_pts,
        "trans_freq_start": config["pulse_freq"] - span / 2,
        "trans_freq_stop": config["pulse_freq"] + span / 2,
        "TransNumPoints": cav_trans_pts,
    }
    config = config | exp_parameters
    # Now lets optimize powers and readout frequencies
    Instance_SingleShotOptimize = ReadOpt_wSingleShotFF(path="SingleShot_OptReadout", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
    data_SingleShotProgramOptimize = ReadOpt_wSingleShotFF.acquire(Instance_SingleShotOptimize)
    # print(data_SingleShotProgram)
    ReadOpt_wSingleShotFF.display(Instance_SingleShotOptimize, data_SingleShotProgramOptimize, plotDisp=True)

    ReadOpt_wSingleShotFF.save_data(Instance_SingleShotOptimize, data_SingleShotProgramOptimize)
    ReadOpt_wSingleShotFF.save_config(Instance_SingleShotOptimize)


if SingleShot_QubitOptimize:
    q_gain_span = SS_Q_params['q_gain_span']
    q_gain_pts = SS_Q_params['q_gain_pts']
    q_freq_pts = SS_Q_params['q_freq_pts']
    q_freq_span = SS_Q_params['q_freq_span']
    config['number_of_pulses'] = SS_Q_params['number_of_pulses']
    if config['pi2_SS']:
        config['qubit_gain'] = pi2_gain
    Qubit_Pulse_Index = 0
    exp_parameters = {
        ###### cavity
        "qubit_gain_Start": max([0, int( config['qubit_gain'] - int(q_gain_span))]), # - q_gain_span / 2,
        "qubit_gain_Stop":  min([32767, int( config['qubit_gain']+ int(q_gain_span))]),# *qubit_gains[Qubit_Pulse_Index] + q_gain_span / 2,
        "qubit_gain_Points": q_gain_pts,
        "qubit_freq_start": qubit_frequency_centers[Qubit_Pulse_Index] - q_freq_span,
        "qubit_freq_stop": qubit_frequency_centers[Qubit_Pulse_Index] + q_freq_span,
        "QubitNumPoints": q_freq_pts,
        "number_of_pulses": SS_Q_params["number_of_pulses"]
    }
    print(exp_parameters)
    config = config | exp_parameters
    g0 = qubit_gains[Qubit_Pulse_Index]
    f0 = qubit_frequency_centers[Qubit_Pulse_Index]
    # # Now lets optimize powers and readout frequencies
    Instance_SingleShotOptimize = QubitPulseOpt_wSingleShotFF(path="SingleShot_OptQubit", outerFolder=outerFolder,
                                                                 cfg=config,soc=soc,soccfg=soccfg)
    data_SingleShotProgramOptimize = QubitPulseOpt_wSingleShotFF.acquire(Instance_SingleShotOptimize,
                                                                            Qubit_Sweep_Index = Qubit_Pulse_Index)
    # print(data_SingleShotProgram)
    QubitPulseOpt_wSingleShotFF.display(Instance_SingleShotOptimize, data_SingleShotProgramOptimize, plotDisp=True)
    print(exp_parameters)

    QubitPulseOpt_wSingleShotFF.save_data(Instance_SingleShotOptimize, data_SingleShotProgramOptimize)
    QubitPulseOpt_wSingleShotFF.save_config(Instance_SingleShotOptimize)

# ── Automated T1 / T2 / T2Echo calibration run ──────────────────────────────
if RunAutoCoherence:
    auto_results = run_auto_coherence(
        soc=soc,
        soccfg=soccfg,
        config=config,                    # full config dict built above
        outerFolder=outerFolder,
        qubit_readout=Qubit_Readout,
        qubit_params=Qubit_Parameters,
        yoko=yoko,                        # set to None if no charge line
        auto_params=AutoCoherence_override_params,
    )
    print("[AutoCoherence] Results:", auto_results)

# ── Zero-span charge-parity switching measurement ───────────────────────────
# Step 1 (optional): park the qubit drive at one parity-doublet peak.
# Step 2 (optional): calibrate a g/e single-shot separator for apriori
#                    classification.
# Step 3: build the ZeroSpanParity cfg from BaseConfig channel routing + the
#         active qubit's tuned readout/drive.
# Step 4: acquire (chunked for long strobe records).
# Step 5: offline analysis -> bits, switch rate, bursts, dwell stats, plots.
if RunZeroSpanParity:
    zsp_outerFolder = outerFolder + "ZeroSpanParity/"
    os.makedirs(zsp_outerFolder, exist_ok=True)

    # ---- Step 1: optional parity-doublet frequency pre-calibration ----------
    if ZSP_RecalibrateParityFreqs:
        spec_cfg = config.copy()
        spec_cfg["reps"]              = ZSP_ParitySpec_params["reps"]
        spec_cfg["rounds"]            = ZSP_ParitySpec_params["rounds"]
        spec_cfg["relax_delay"]       = ZSP_ParitySpec_params["relax_delay"]
        spec_cfg["Gauss"]             = ZSP_ParitySpec_params["Gauss"]
        spec_cfg["sigma"]             = ZSP_ParitySpec_params["sigma"]
        spec_cfg["qubit_gain"]        = ZSP_ParitySpec_params["gain"]
        spec_cfg["qubit_length"]      = ZSP_ParitySpec_params["qubit_length"]
        spec_cfg["qubit_pulse_style"] = "const"
        spec_cfg["SpecSpan"]          = ZSP_ParitySpec_params["SpecSpan"]
        spec_cfg["SpecNumPoints"]     = ZSP_ParitySpec_params["SpecNumPoints"]
        spec_cfg["step"]  = 2 * spec_cfg["SpecSpan"] / spec_cfg["SpecNumPoints"]
        spec_cfg["start"] = qubit_frequency_center - spec_cfg["SpecSpan"]
        spec_cfg["expts"] = spec_cfg["SpecNumPoints"]
        spec_cfg.setdefault("current_voltage", start_voltage)

        Instance_paritySpec = QubitSpecSliceFF(
            path="ZeroSpanParity_Spec", cfg=spec_cfg,
            soc=soc, soccfg=soccfg, outerFolder=zsp_outerFolder)
        data_paritySpec = QubitSpecSliceFF.acquire(Instance_paritySpec)
        QubitSpecSliceFF.display(
            Instance_paritySpec, data_paritySpec, plotDisp=False, figNum=2,
            min_sep=ZSP_ParitySpec_params["min_sep_MHz"],
            fit_window_mhz=ZSP_ParitySpec_params["fit_window_mhz"],
            prominent_ratio=ZSP_ParitySpec_params["prominent_ratio"])
        QubitSpecSliceFF.save_data(Instance_paritySpec, data_paritySpec)
        QubitSpecSliceFF.save_config(Instance_paritySpec)

        chosen = pick_parity_drive_freq(
            data_paritySpec, which=ZSP_ParityFreqs_Cached["which_to_park"])
        ZSP_ParityFreqs_Cached["lower_peak_MHz"]  = chosen["lower"]
        ZSP_ParityFreqs_Cached["higher_peak_MHz"] = chosen["higher"]
        parity_drive_freq_MHz = chosen["picked"]
        print(f"[ZeroSpanParity] parity doublet: lower={chosen['lower']:.6f} "
              f"higher={chosen['higher']:.6f} MHz; parking at "
              f"{ZSP_ParityFreqs_Cached['which_to_park']} "
              f"({parity_drive_freq_MHz:.6f} MHz)")
    else:
        which = ZSP_ParityFreqs_Cached["which_to_park"]
        parity_drive_freq_MHz = (ZSP_ParityFreqs_Cached["lower_peak_MHz"]
                                 if which == "lower"
                                 else ZSP_ParityFreqs_Cached["higher_peak_MHz"])
        if parity_drive_freq_MHz is None:
            raise RuntimeError(
                "[ZeroSpanParity] No cached parity freq and "
                "ZSP_RecalibrateParityFreqs=False. Populate ZSP_ParityFreqs_Cached "
                "or set ZSP_RecalibrateParityFreqs=True.")

    # ---- Step 2: optional g/e separator pre-calibration ---------------------
    if ZSP_RecalibrateSeparator:
        sep = get_apriori_separator_from_singleshot(
            config=config, soc=soc, soccfg=soccfg, outerFolder=zsp_outerFolder)
        ZSP_Separator_Cached["g_center"] = sep["g_center"]
        ZSP_Separator_Cached["e_center"] = sep["e_center"]
        ZSP_Separator_Cached["normal"]   = sep["normal"]
        ZSP_Separator_Cached["midpoint"] = sep["midpoint"]
    elif ZSP_AnalysisParams["classifier_method"] == "apriori":
        # Spec §5.3 rule 7: with RecalibrateSeparator=False and apriori
        # classification, all four cached fields must be np.ndarray of shape
        # (2,). Validate fail-fast (a copy-pasted list is coerced; wrong shapes
        # are rejected).
        for _k in ("g_center", "e_center", "normal", "midpoint"):
            _v = ZSP_Separator_Cached[_k]
            if _v is None:
                raise RuntimeError(
                    f"[ZeroSpanParity §5.3 rule 7] ZSP_Separator_Cached['{_k}'] "
                    f"is None and classifier_method='apriori'. Populate "
                    f"ZSP_Separator_Cached, set ZSP_RecalibrateSeparator=True, or "
                    f"use classifier_method='kmeans'.")
            _arr = np.asarray(_v, dtype=float)
            if _arr.shape != (2,):
                raise RuntimeError(
                    f"[ZeroSpanParity §5.3 rule 7] ZSP_Separator_Cached['{_k}'] "
                    f"has shape {_arr.shape}, expected (2,) — an (I, Q) "
                    f"coordinate.")
            ZSP_Separator_Cached[_k] = _arr  # normalize to ndarray

    # ---- Step 3: build the ZeroSpanParity cfg -------------------------------
    zsp_mode_params = (ZSP_StrobeParams if ZSP_RunMode == "strobe"
                       else ZSP_DecimatedParams)
    zsp_qubit_gain = (ZSP_DriveParams["qubit_gain"]
                      if ZSP_DriveParams["qubit_gain"] is not None
                      else qubit_gain)
    zsp_pulse_gain = (ZSP_DriveParams["pulse_gain"]
                      if ZSP_DriveParams["pulse_gain"] is not None
                      else cavity_gain)
    zsp_cfg = {
        # Channel routing sourced from BaseConfig (Calib/initialize4Q.py)
        "res_ch":     config["res_ch"],
        "qubit_ch":   config["qubit_ch"],
        "ro_chs":     config["ro_chs"],
        "nqz":        config["nqz"],
        "qubit_nqz":  config["qubit_nqz"],
        "mixer_freq": config["mixer_freq"],
        # Frequencies (active qubit's tuned readout + picked parity peak)
        "read_pulse_freq":   resonator_frequency_center,
        "parity_drive_freq": parity_drive_freq_MHz,
        # Drive
        "qubit_gain": zsp_qubit_gain,
        "pulse_gain": zsp_pulse_gain,
        "res_phase":  ZSP_DriveParams["res_phase"],
        # Mode + trigger source
        "mode":      ZSP_RunMode,
        "start_src": ZSP_StartSrc,
        # Mode-specific params (read_length, adc_trig_offset, + mode extras)
        **zsp_mode_params,
    }

    # ---- Step 4: run acquisition --------------------------------------------
    zsp_exp = ZeroSpanParity(
        soc=soc, soccfg=soccfg, path="ZeroSpanParity",
        outerFolder=zsp_outerFolder, cfg=zsp_cfg)
    if ZSP_RunMode == "strobe" and ZSP_StrobeParams["n_chunks"] > 1:
        zsp_data = chunked_acquire(
            zsp_exp, n_chunks=ZSP_StrobeParams["n_chunks"], progress=True)
        # Stitched arrays replace exp.data so save_data writes the full record.
        zsp_exp.data = {"data": zsp_data}
    else:
        zsp_data = zsp_exp.acquire(progress=True)
    zsp_exp.save_data()
    zsp_exp.save_config()

    # ---- Step 5: offline analysis -------------------------------------------
    zsp_separator = (ZSP_Separator_Cached
                     if ZSP_AnalysisParams["classifier_method"] == "apriori"
                     else None)
    analyze_parity_run(
        h5_path=zsp_exp.fname,
        separator=zsp_separator,
        window_us=ZSP_AnalysisParams["window_us"],
        k_sigma=ZSP_AnalysisParams["k_sigma"],
        classifier_method=ZSP_AnalysisParams["classifier_method"],
        step_us=ZSP_AnalysisParams["step_us"],
        min_burst_duration_us=ZSP_AnalysisParams["min_burst_duration_us"],
        analysis_bin_us=ZSP_AnalysisParams["analysis_bin_us"],
        save_plots=ZSP_AnalysisParams["save_plots"],
        out_dir=os.path.dirname(zsp_exp.fname),
    )
    print(f"[ZeroSpanParity] complete. Raw data: {zsp_exp.fname}")

    # --- Validation harness execution ---
    _val_out_dir = zsp_exp.outerFolder if hasattr(zsp_exp, "outerFolder") else os.path.dirname(zsp_exp.fname)

    if Validate_StaticContrast:
        if ZSP_Separator_Cached.get("g_center") is None:
            raise RuntimeError("Validate_StaticContrast needs a calibrated separator (set RecalibrateSeparator)")
        _f0 = zsp_cfg["read_pulse_freq"]
        _span = StaticContrast_params["freq_span_mhz"]
        _flist = np.linspace(_f0 - _span / 2, _f0 + _span / 2, StaticContrast_params["n_points"])
        zsp_exp.cfg["reps_per_chunk"] = StaticContrast_params["reps_per_point"]
        _sc = run_static_contrast(zsp_exp, _flist, qubit_gain_on=zsp_cfg["qubit_gain"], out_dir=_val_out_dir)
        print(f"[stage 1] best read_pulse_freq = {_sc['best_freq']:.4f} MHz  (contrast SNR {_sc['contrast_snr']:.1f})")

    if Validate_ContrastVsQubitFreq:
        _q0 = zsp_cfg["parity_drive_freq"]
        _qspan = ContrastVsQubit_params["qfreq_span_mhz"]
        _qlist = np.linspace(_q0 - _qspan / 2, _q0 + _qspan / 2, ContrastVsQubit_params["n_points"])
        _s2 = run_contrast_vs_qubit_freq(zsp_exp, _qlist, out_dir=_val_out_dir)
        print(f"[stage 2] parity peak sep = {_s2['peaks'].get('peak_sep')}")

    if Validate_ModulationCheck:
        _m = run_modulation_check(zsp_exp, separator=zsp_separator,
                                  modulation_freq_hz=Modulation_params["modulation_freq_hz"],
                                  n_periods=Modulation_params["n_periods"], out_dir=_val_out_dir)
        print(f"[stage 3] modulation corr={_m['correlation']:.2f} depth={_m['modulation_depth']:.2f} "
              f"snr={_m['snr']:.2f}  (gate: proceed only if recovered)")

    if Validate_ControlSuite:
        _pf = {"lower": ZSP_ParityFreqs_Cached.get("lower_peak_MHz"),
               "higher": ZSP_ParityFreqs_Cached.get("higher_peak_MHz")}
        _c = run_control_suite(zsp_exp, separator=zsp_separator, variants=tuple(Control_params["variants"]),
                               detune_mhz=Control_params["detune_mhz"], parity_freqs=_pf, out_dir=_val_out_dir)
        print(f"[stage 8] controls: {[(k, v.get('separation_snr', v.get('separation_snr_lower'))) for k, v in _c['variants'].items()]}")

    if Validate_EnvironmentSweep:
        def _set_power(_exp, _val):
            _exp.cfg["pulse_gain"] = _val  # NOTE: replace with attenuator/YOKO call for real power sweep
            _exp.prog = type(_exp.prog)(_exp.soccfg, _exp.cfg)
        _e = run_environment_sweep(zsp_exp, separator=zsp_separator,
                                   param_name=Environment_params["param_name"],
                                   param_values=Environment_params["values"],
                                   set_param=_set_power, out_dir=_val_out_dir)
        print(f"[stage 7] swept {Environment_params['param_name']}: {_e['table']}")

    if Build_EvidenceReport:
        _rep = build_evidence_report(_val_out_dir, os.path.join(_val_out_dir, "EVIDENCE.md"))
        print(f"[stage 9] evidence report written: {_rep}")

# ramp_to(yoko, 0.0)
# yoko.write(":OUTP OFF")
yoko.close()
###############################################`
